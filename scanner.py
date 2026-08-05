import math
import requests
import pandas as pd
import numpy as np

# MEXC/OKX OHLCV Data Fetcher (Spot/Contract REST API)
def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 100):
    """Fetches pure OHLCV candle data from public REST endpoints."""
    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    
    tf_map_mexc = {"3M": "3m", "5M": "5m", "15M": "15m", "1H": "60m", "4H": "4h"}
    interval = tf_map_mexc.get(timeframe, "15m")
    
    url = f"https://api.mexc.com/api/v3/klines?symbol={clean_sym}&interval={interval}&limit={limit}"
    
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_vol', 'trades', 'tb_base_vol', 'tb_quote_vol', 'ignore'
                ])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                return df
    except Exception:
        pass
    
    return pd.DataFrame()


def analyze_range_structure(df: pd.DataFrame):
    """
    Analyzes consolidation range structure using pure OHLCV data.
    Evaluates both Bullish Breakout Pressure (at Resistance) and 
    Bearish Breakdown Pressure (at Support).
    """
    if df.empty or len(df) < 20:
        return None, "DATA UNAVAILABLE"

    # Identify horizontal Support and Resistance bounds from recent range
    recent_df = df.tail(30).copy()
    resistance = recent_df['high'].max()
    support = recent_df['low'].min()
    range_height = resistance - support

    if range_height <= 0:
        return None, "NO RANGE STRUCTURE"

    curr_close = recent_df['close'].iloc[-1]
    
    # Distance to boundaries (%)
    dist_to_res_pct = (resistance - curr_close) / range_height
    dist_to_sup_pct = (curr_close - support) / range_height

    # Analyze last 10 candles for structure & volume behavior
    tail_candles = recent_df.tail(10)

    # 1. Pure OHLCV Buyer vs Seller Volume Power Calculation
    total_buyer_vol = 0.0
    total_seller_vol = 0.0
    total_vol = 0.0

    for idx, row in tail_candles.iterrows():
        c_range = row['high'] - row['low']
        v = row['volume']
        if c_range > 0:
            b_ratio = (row['close'] - row['low']) / c_range
            s_ratio = (row['high'] - row['close']) / c_range
            total_buyer_vol += v * b_ratio
            total_seller_vol += v * s_ratio
        else:
            total_buyer_vol += v * 0.5
            total_seller_vol += v * 0.5
        total_vol += v

    buyer_power = round((total_buyer_vol / total_vol * 100), 1) if total_vol > 0 else 50.0
    seller_power = round(100.0 - buyer_power, 1)

    # 2. Candle Compression & Slope Analysis
    lows = tail_candles['low'].values
    highs = tail_candles['high'].values
    
    # Higher Lows (Bullish structure check)
    higher_lows_count = sum(1 for i in range(1, len(lows)) if lows[i] >= lows[i-1])
    higher_lows_ratio = higher_lows_count / (len(lows) - 1)

    # Lower Highs (Bearish structure check)
    lower_highs_count = sum(1 for i in range(1, len(highs)) if highs[i] <= highs[i-1])
    lower_highs_ratio = lower_highs_count / (len(highs) - 1)

    # 3. Pullback Depth Analysis
    recent_min_low = tail_candles['low'].min()
    recent_max_high = tail_candles['high'].max()
    
    res_pullback_depth = (resistance - recent_min_low) / range_height  # Shallow pullback = Bullish
    sup_pullback_depth = (recent_max_high - support) / range_height     # Shallow bounce = Bearish

    # Determine Directional Bias & Calculate Readiness Score
    # Check Bullish Setup (At Resistance)
    is_near_res = dist_to_res_pct <= 0.35
    is_near_sup = dist_to_sup_pct <= 0.35

    bullish_readiness = 0
    bearish_readiness = 0

    # Calculate Bullish Score
    if is_near_res:
        proximity_score = max(0, (0.35 - dist_to_res_pct) / 0.35) * 35  # Max 35 pts
        power_score = max(0, (buyer_power - 40) / 60) * 30                # Max 30 pts
        structure_score = (higher_lows_ratio * 20)                        # Max 20 pts
        depth_score = (1.0 - min(1.0, res_pullback_depth)) * 15           # Max 15 pts
        bullish_readiness = int(proximity_score + power_score + structure_score + depth_score)

    # Calculate Bearish Score
    if is_near_sup:
        proximity_score = max(0, (0.35 - dist_to_sup_pct) / 0.35) * 35  # Max 35 pts
        power_score = max(0, (seller_power - 40) / 60) * 30               # Max 30 pts
        structure_score = (lower_highs_ratio * 20)                        # Max 20 pts
        depth_score = (1.0 - min(1.0, sup_pullback_depth)) * 15           # Max 15 pts
        bearish_readiness = int(proximity_score + power_score + structure_score + depth_score)

    # Evaluate Winner
    if bullish_readiness >= bearish_readiness and bullish_readiness > 0:
        break_direction = "BULLISH"
        break_symbol = "▲"
        direction_label = "Bullish Breakout Candidate"
        readiness_score = min(99, max(0, bullish_readiness))
        
        if higher_lows_ratio >= 0.6 and dist_to_res_pct <= 0.15:
            structure_type = "ASCENDING TRIANGLE"
        elif dist_to_res_pct <= 0.1:
            structure_type = "RESISTANCE ABSORPTION"
        else:
            structure_type = "BULLISH COMPRESSION"
            
    elif bearish_readiness > bullish_readiness:
        break_direction = "BEARISH"
        break_symbol = "▼"
        direction_label = "Bearish Breakdown Candidate"
        readiness_score = min(99, max(0, bearish_readiness))
        
        if lower_highs_ratio >= 0.6 and dist_to_sup_pct <= 0.15:
            structure_type = "DESCENDING TRIANGLE"
        elif dist_to_sup_pct <= 0.1:
            structure_type = "SUPPORT ABSORPTION"
        else:
            structure_type = "BEARISH COMPRESSION"
            
    else:
        break_direction = "NEUTRAL"
        break_symbol = "↔"
        direction_label = "Consolidation"
        readiness_score = 15
        structure_type = "RANGE CHOP"

    result = {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "exchange": "MEXC/OKX",
        "curr_close": curr_close,
        "support": round(support, 6),
        "resistance": round(resistance, 6),
        "structure_type": structure_type,
        "direction_label": direction_label,
        "break_direction": break_direction,
        "break_symbol": break_symbol,
        "readiness_score": readiness_score,
        "readiness_display": f"{readiness_score}%",
        "buyer_power": buyer_power,
        "seller_power": seller_power
    }

    return result, None


def _process_symbol_tf(symbol: str, tf: str):
    """Processes a single symbol and timeframe pair using OHLCV data."""
    df = fetch_ohlcv(symbol, tf)
    if df.empty:
        return None, "DATA UNAVAILABLE"
    return analyze_range_structure(df)


def run_scanner_pipeline(symbols: list, timeframe: str = "ALL"):
    """Scans requested symbols using pure OHLCV range detection."""
    results = []
    diagnostics = {"symbols_scanned": len(symbols), "symbols_downloaded": 0, "rejections": {}}

    tfs_to_run = ["3M", "5M", "15M", "1H", "4H"] if timeframe == "ALL" else [timeframe]

    for sym in symbols:
        for tf in tfs_to_run:
            match, err = _process_symbol_tf(sym, tf)
            if match:
                diagnostics["symbols_downloaded"] += 1
                # Filter for candidates meeting the minimum threshold
                if match["readiness_score"] >= 20:
                    results.append(match)
            else:
                diagnostics["rejections"][err] = diagnostics["rejections"].get(err, 0) + 1

    results.sort(key=lambda x: -x["readiness_score"])
    return results, diagnostics
