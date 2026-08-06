import requests
import pandas as pd
from datetime import datetime, timezone

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 100):
    """
    PRIMARY: OKX REST API
    FAILOVER: MEXC REST API
    """
    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    if not clean_sym.endswith("USDT"):
        clean_sym += "USDT"

    okx_sym = clean_sym[:-4] + "-USDT"
    mexc_sym = clean_sym

    okx_tf_map = {"5M": "5m", "15M": "15m", "1H": "1H", "4H": "4H"}
    mexc_tf_map = {"5M": "5m", "15M": "15m", "1H": "1h", "4H": "4h"}

    okx_bar = okx_tf_map.get(timeframe, "15m")
    mexc_bar = mexc_tf_map.get(timeframe, "15m")

    # 1. PRIMARY: OKX
    okx_url = f"https://www.okx.com/api/v5/market/candles?instId={okx_sym}&bar={okx_bar}&limit={limit}"
    try:
        resp = requests.get(okx_url, headers=HEADERS, timeout=4)
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
                return df
    except Exception:
        pass

    # 2. FAILOVER: MEXC
    mexc_url = f"https://api.mexc.com/api/v3/klines?symbol={mexc_sym}&interval={mexc_bar}&limit={limit}"
    try:
        resp = requests.get(mexc_url, headers=HEADERS, timeout=4)
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


def analyze_range_structure(df: pd.DataFrame, symbol: str, timeframe: str):
    """Analyzes range structure using pure OHLCV price & volume dynamics."""
    if df.empty or len(df) < 20:
        return None, "DATA UNAVAILABLE"

    recent_df = df.tail(30).copy()
    resistance = float(recent_df['high'].max())
    support = float(recent_df['low'].min())
    range_height = resistance - support

    if range_height <= 0:
        return None, "NO RANGE STRUCTURE"

    curr_close = float(recent_df['close'].iloc[-1])

    dist_to_res_pct = (resistance - curr_close) / range_height if range_height > 0 else 0
    dist_to_sup_pct = (curr_close - support) / range_height if range_height > 0 else 0

    # Distance to levels (as percentage of price)
    dist_to_res_price_pct = ((resistance - curr_close) / curr_close) * 100
    dist_to_sup_price_pct = ((curr_close - support) / curr_close) * 100

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

    # Volume Trend: Compare last 5 candles vs previous 5
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

    lows = tail_candles['low'].values
    highs = tail_candles['high'].values

    higher_lows_count = sum(1 for i in range(1, len(lows)) if lows[i] >= lows[i-1])
    higher_lows_ratio = higher_lows_count / (len(lows) - 1) if len(lows) > 1 else 0

    lower_highs_count = sum(1 for i in range(1, len(highs)) if highs[i] <= highs[i-1])
    lower_highs_ratio = lower_highs_count / (len(highs) - 1) if len(highs) > 1 else 0

    recent_min_low = float(tail_candles['low'].min())
    recent_max_high = float(tail_candles['high'].max())

    res_pullback_depth = (resistance - recent_min_low) / range_height if range_height > 0 else 0
    sup_pullback_depth = (recent_max_high - support) / range_height if range_height > 0 else 0

    proximity_bull = max(0, (0.50 - dist_to_res_pct) / 0.50) * 40
    power_bull = max(0, (buyer_power - 30) / 70) * 30
    struct_bull = higher_lows_ratio * 15
    depth_bull = (1.0 - min(1.0, res_pullback_depth)) * 15
    bullish_readiness = int(proximity_bull + power_bull + struct_bull + depth_bull)

    proximity_bear = max(0, (0.50 - dist_to_sup_pct) / 0.50) * 40
    power_bear = max(0, (seller_power - 30) / 70) * 30
    struct_bear = lower_highs_ratio * 15
    depth_bear = (1.0 - min(1.0, sup_pullback_depth)) * 15
    bearish_readiness = int(proximity_bear + power_bear + struct_bear + depth_bear)

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
    df = fetch_ohlcv(symbol, tf)
    if df.empty:
        return None, "DATA UNAVAILABLE"
    return analyze_range_structure(df, symbol, tf)


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
