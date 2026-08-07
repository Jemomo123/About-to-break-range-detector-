import requests
import pandas as pd
from datetime import datetime, timezone

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 100):
    """
    PRIMARY: OKX REST API (Your watchlist is built for OKX)
    FALLBACK: MEXC REST API (Only if OKX fails)
    """
    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    if not clean_sym.endswith("USDT"):
        clean_sym += "USDT"

    okx_sym = f"{clean_sym[:-4]}-USDT"
    okx_tf_map = {"5M": "5m", "15M": "15m", "1H": "1H", "4H": "4H"}
    okx_bar = okx_tf_map.get(timeframe, "15m")

    # 1. PRIMARY: OKX
    okx_url = f"https://www.okx.com/api/v5/market/candles?instId={okx_sym}&bar={okx_bar}&limit={limit}"
    try:
        print(f"[OKX][{symbol}][{timeframe}] Fetching...")
        resp = requests.get(okx_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            res_json = resp.json()
            data = res_json.get("data", [])
            if isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'volCcy', 'volCcyQuote', 'confirm'
                ])
                df = df.iloc[::-1].reset_index(drop=True)
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                print(f"[OKX][{symbol}][{timeframe}] ✓ Downloaded {len(df)} candles")
                return df
            else:
                print(f"[OKX][{symbol}] Empty data. Code: {res_json.get('code')}")
        else:
            print(f"[OKX][{symbol}] HTTP {resp.status_code}")
    except requests.exceptions.Timeout:
        print(f"[OKX][{symbol}] TIMEOUT - Request took >10s")
    except Exception as e:
        print(f"[OKX][{symbol}] Exception: {e}")

    # 2. FALLBACK: MEXC
    mexc_sym = clean_sym
    mexc_tf_map = {"5M": "5m", "15M": "15m", "1H": "1h", "4H": "4h"}
    mexc_bar = mexc_tf_map.get(timeframe, "15m")
    mexc_url = f"https://api.mexc.com/api/v3/klines?symbol={mexc_sym}&interval={mexc_bar}&limit={limit}"
    try:
        print(f"[MEXC][{symbol}][{timeframe}] Fallback...")
        resp = requests.get(mexc_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_vol', 'trades', 'tb_base_vol', 'tb_quote_vol', 'ignore'
                ])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                print(f"[MEXC][{symbol}][{timeframe}] ✓ Downloaded {len(df)} candles")
                return df
            else:
                print(f"[MEXC][{symbol}] Empty data.")
        else:
            print(f"[MEXC][{symbol}] HTTP {resp.status_code}")
    except requests.exceptions.Timeout:
        print(f"[MEXC][{symbol}] TIMEOUT - Request took >10s")
    except Exception as e:
        print(f"[MEXC][{symbol}] Exception: {e}")

    print(f"[{symbol}][{timeframe}] ✗ FAILED (OKX + MEXC)")
    return pd.DataFrame()


def analyze_range_structure(df: pd.DataFrame, symbol: str, timeframe: str):
    """
    Analyzes range structure using pure OHLCV price & volume dynamics.
    LOGGING: Every step is logged so we can see exactly where symbols are filtered.
    """
    print(f"[DEBUG][{symbol}][{timeframe}] === STARTING ANALYSIS ===")
    
    # Step 1: Check if we have enough data
    if df.empty or len(df) < 20:
        print(f"[DEBUG][{symbol}][{timeframe}] ❌ REJECTED: Insufficient candles (got {len(df) if not df.empty else 0})")
        return None, "DATA UNAVAILABLE"
    print(f"[DEBUG][{symbol}][{timeframe}] ✓ Data available: {len(df)} candles")

    # Step 2: Calculate range boundaries
    recent_df = df.tail(30).copy()
    resistance = float(recent_df['high'].max())
    support = float(recent_df['low'].min())
    range_height = resistance - support
    curr_close = float(recent_df['close'].iloc[-1])
    
    print(f"[DEBUG][{symbol}][{timeframe}] Range: Support=${support:.6f}, Resistance=${resistance:.6f}, Height=${range_height:.6f}")
    print(f"[DEBUG][{symbol}][{timeframe}] Current Close: ${curr_close:.6f}")

    # Step 3: Validate range height
    if range_height <= 0:
        print(f"[DEBUG][{symbol}][{timeframe}] ❌ REJECTED: Invalid range (height <= 0)")
        return None, "NO RANGE STRUCTURE"
    
    # Step 4: Calculate distance to boundaries
    dist_to_res_pct = (resistance - curr_close) / range_height if range_height > 0 else 0
    dist_to_sup_pct = (curr_close - support) / range_height if range_height > 0 else 0
    dist_to_res_price_pct = ((resistance - curr_close) / curr_close) * 100
    dist_to_sup_price_pct = ((curr_close - support) / curr_close) * 100
    
    print(f"[DEBUG][{symbol}][{timeframe}] Distance to Resistance: {dist_to_res_pct:.2%} of range, {dist_to_res_price_pct:.2f}%")
    print(f"[DEBUG][{symbol}][{timeframe}] Distance to Support: {dist_to_sup_pct:.2%} of range, {dist_to_sup_price_pct:.2f}%")

    # Step 5: Volume analysis (Buyer/Seller Power)
    tail_candles = recent_df.tail(10)
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
    
    print(f"[DEBUG][{symbol}][{timeframe}] Buyer Power: {buyer_power}%, Seller Power: {seller_power}%")

    # Step 6: Volume Trend
    volumes = df['volume'].values
    if len(volumes) >= 10:
        recent_avg = sum(volumes[-5:]) / 5
        prev_avg = sum(volumes[-10:-5]) / 5
        if recent_avg > prev_avg * 1.05:
            volume_trend = "Increasing"
        elif recent_avg < prev_avg * 0.95:
            volume_trend = "Decreasing"
        else:
            volume_trend = "Neutral"
    else:
        volume_trend = "Neutral"
    
    print(f"[DEBUG][{symbol}][{timeframe}] Volume Trend: {volume_trend}")

    # Step 7: Candle structure analysis (higher lows / lower highs)
    lows = tail_candles['low'].values
    highs = tail_candles['high'].values

    higher_lows_count = sum(1 for i in range(1, len(lows)) if lows[i] >= lows[i-1])
    higher_lows_ratio = higher_lows_count / (len(lows) - 1) if len(lows) > 1 else 0

    lower_highs_count = sum(1 for i in range(1, len(highs)) if highs[i] <= highs[i-1])
    lower_highs_ratio = lower_highs_count / (len(highs) - 1) if len(highs) > 1 else 0
    
    print(f"[DEBUG][{symbol}][{timeframe}] Higher Lows Ratio: {higher_lows_ratio:.2f}, Lower Highs Ratio: {lower_highs_ratio:.2f}")

    # Step 8: Pullback depth
    recent_min_low = float(tail_candles['low'].min())
    recent_max_high = float(tail_candles['high'].max())

    res_pullback_depth = (resistance - recent_min_low) / range_height if range_height > 0 else 0
    sup_pullback_depth = (recent_max_high - support) / range_height if range_height > 0 else 0
    
    print(f"[DEBUG][{symbol}][{timeframe}] Resistance Pullback: {res_pullback_depth:.2f}, Support Pullback: {sup_pullback_depth:.2f}")

    # Step 9: Calculate Readiness (Bullish)
    proximity_bull = max(0, (0.50 - dist_to_res_pct) / 0.50) * 40
    power_bull = max(0, (buyer_power - 30) / 70) * 30
    struct_bull = higher_lows_ratio * 15
    depth_bull = (1.0 - min(1.0, res_pullback_depth)) * 15
    bullish_readiness = int(proximity_bull + power_bull + struct_bull + depth_bull)
    
    print(f"[DEBUG][{symbol}][{timeframe}] Bullish Components: Proximity={proximity_bull:.1f}, Power={power_bull:.1f}, Structure={struct_bull:.1f}, Depth={depth_bull:.1f}")
    print(f"[DEBUG][{symbol}][{timeframe}] Bullish Readiness: {bullish_readiness}")

    # Step 10: Calculate Readiness (Bearish)
    proximity_bear = max(0, (0.50 - dist_to_sup_pct) / 0.50) * 40
    power_bear = max(0, (seller_power - 30) / 70) * 30
    struct_bear = lower_highs_ratio * 15
    depth_bear = (1.0 - min(1.0, sup_pullback_depth)) * 15
    bearish_readiness = int(proximity_bear + power_bear + struct_bear + depth_bear)
    
    print(f"[DEBUG][{symbol}][{timeframe}] Bearish Readiness: {bearish_readiness}")

    # Step 11: Determine direction and final score
    clean_display = symbol.replace("-", "").replace("_", "").upper()
    last_updated = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    if bullish_readiness >= bearish_readiness:
        break_direction = "BULLISH"
        break_symbol = "▲"
        direction_label = "Bullish Breakout Candidate"
        readiness_score = min(99, max(10, bullish_readiness))
        if higher_lows_ratio >= 0.6 and dist_to_res_pct <= 0.15:
            structure_type = "ASCENDING TRIANGLE"
        elif dist_to_res_pct <= 0.10:
            structure_type = "RESISTANCE ABSORPTION"
        else:
            structure_type = "BULLISH COMPRESSION"
    else:
        break_direction = "BEARISH"
        break_symbol = "▼"
        direction_label = "Bearish Breakdown Candidate"
        readiness_score = min(99, max(10, bearish_readiness))
        if lower_highs_ratio >= 0.6 and dist_to_sup_pct <= 0.15:
            structure_type = "DESCENDING TRIANGLE"
        elif dist_to_sup_pct <= 0.10:
            structure_type = "SUPPORT ABSORPTION"
        else:
            structure_type = "BEARISH COMPRESSION"
    
    print(f"[DEBUG][{symbol}][{timeframe}] ✅ FINAL: Direction={break_direction}, Readiness={readiness_score}%, Structure={structure_type}")
    print(f"[DEBUG][{symbol}][{timeframe}] === ANALYSIS COMPLETE ===")

    return {
        "symbol": clean_display,
        "timeframe": timeframe,
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
        "seller_power": seller_power,
        "distance_to_resistance": round(dist_to_res_price_pct, 2),
        "distance_to_support": round(dist_to_sup_price_pct, 2),
        "volume_trend": volume_trend,
        "last_updated": last_updated
    }, None


def _process_symbol_tf(symbol: str, tf: str):
    print(f"[DEBUG][{symbol}][{tf}] >>> Starting scan")
    df = fetch_ohlcv(symbol, tf)
    if df.empty:
        print(f"[DEBUG][{symbol}][{tf}] ❌ No data from fetch")
        return None, "DATA UNAVAILABLE"
    result, err = analyze_range_structure(df, symbol, tf)
    if result:
        print(f"[DEBUG][{symbol}][{tf}] ✅ PASSED - Readiness: {result['readiness_score']}%")
    else:
        print(f"[DEBUG][{symbol}][{tf}] ❌ FAILED - {err}")
    return result, err


def run_scanner_pipeline(symbols: list, timeframe: str = "ALL"):
    results = []
    diagnostics = {"symbols_scanned": len(symbols), "symbols_downloaded": 0, "rejections": {}}

    tfs_to_run = ["5M", "15M", "1H", "4H"] if timeframe == "ALL" else [timeframe]

    for sym in symbols:
        for tf in tfs_to_run:
            match, err = _process_symbol_tf(sym, tf)
            if match:
                diagnostics["symbols_downloaded"] += 1
                results.append(match)
            else:
                diagnostics["rejections"][err] = diagnostics["rejections"].get(err, 0) + 1

    results.sort(key=lambda x: -x["readiness_score"])
    return results, diagnostics
