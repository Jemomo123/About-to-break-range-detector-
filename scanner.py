import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import threading

# ===== CONFIGURATION =====
DEBUG = False
# =========================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

UNSUPPORTED_SYMBOLS = set()
UNSUPPORTED_LOCK = threading.Lock()

def is_unsupported(symbol):
    with UNSUPPORTED_LOCK:
        return symbol in UNSUPPORTED_SYMBOLS

def mark_unsupported(symbol):
    with UNSUPPORTED_LOCK:
        UNSUPPORTED_SYMBOLS.add(symbol)


def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 150):
    if is_unsupported(symbol):
        return pd.DataFrame()

    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    if not clean_sym.endswith("USDT"):
        clean_sym += "USDT"

    okx_sym = f"{clean_sym[:-4]}-USDT"
    okx_tf_map = {"5M": "5m", "15M": "15m", "1H": "1H", "4H": "4H"}
    okx_bar = okx_tf_map.get(timeframe, "15m")

    okx_url = f"https://www.okx.com/api/v5/market/candles?instId={okx_sym}&bar={okx_bar}&limit={limit}"
    try:
        resp = requests.get(okx_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            res_json = resp.json()
            code = res_json.get("code")
            data = res_json.get("data", [])
            if code == "0" and isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'volCcy', 'volCcyQuote', 'confirm'
                ])
                df = df.iloc[::-1].reset_index(drop=True)
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                return df
            elif code == "51001":
                mark_unsupported(symbol)
                return pd.DataFrame()
    except Exception:
        pass

    mexc_sym = clean_sym
    mexc_tf_map = {"5M": "5m", "15M": "15m", "1H": "1h", "4H": "4h"}
    mexc_bar = mexc_tf_map.get(timeframe, "15m")
    mexc_url = f"https://api.mexc.com/api/v3/klines?symbol={mexc_sym}&interval={mexc_bar}&limit={limit}"
    try:
        resp = requests.get(mexc_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                parsed = []
                for row in data:
                    if len(row) >= 6:
                        parsed.append(row[:6])
                if parsed:
                    df = pd.DataFrame(parsed, columns=[
                        'timestamp', 'open', 'high', 'low', 'close', 'volume'
                    ])
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)
                    return df
    except Exception:
        pass

    return pd.DataFrame()


def detect_levels(highs, lows, closes, lookback=30):
    """Find support and resistance levels from recent price action."""
    support = np.min(lows[-lookback:])
    resistance = np.max(highs[-lookback:])
    return support, resistance


def analyze_level_battle(df: pd.DataFrame, symbol: str, timeframe: str):
    """
    Determines who is winning at the nearest support/resistance level.
    Returns battle result and signal.
    """
    if df.empty or len(df) < 30:
        return None, "INSUFFICIENT DATA"

    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    volumes = df['volume'].values

    curr_close = float(closes[-1])
    lookback = min(30, len(df) - 1)

    # 1. Identify support and resistance
    support, resistance = detect_levels(highs, lows, closes, lookback)
    range_height = resistance - support
    if range_height <= 0:
        return None, "INVALID RANGE"

    # 2. Determine which level price is nearest to (within 3%)
    dist_to_res = (resistance - curr_close) / curr_close * 100
    dist_to_sup = (curr_close - support) / curr_close * 100
    threshold = 3.0  # within 3% of level

    if dist_to_res < dist_to_sup and dist_to_res < threshold:
        # NEAR RESISTANCE
        level_type = "RESISTANCE"
        level_price = resistance
        distance = dist_to_res
        # Determine who is winning at resistance
        buyer_score, seller_score = compute_battle_score(
            highs, lows, closes, volumes, 
            level=level_price, 
            level_type="RESISTANCE"
        )
        if buyer_score > seller_score + 5:
            winner = "BUYERS"
            signal = "BREAKOUT IMMINENT"
            explanation = "Buyers are absorbing selling pressure near resistance."
        elif seller_score > buyer_score + 5:
            winner = "SELLERS"
            signal = "RESISTANCE HOLDING"
            explanation = "Sellers are defending resistance, rejecting price."
        else:
            winner = "NEUTRAL"
            signal = "NO CLEAR SIGNAL"
            explanation = "Battle at resistance is evenly matched."

    elif dist_to_sup < threshold:
        # NEAR SUPPORT
        level_type = "SUPPORT"
        level_price = support
        distance = dist_to_sup
        buyer_score, seller_score = compute_battle_score(
            highs, lows, closes, volumes,
            level=level_price,
            level_type="SUPPORT"
        )
        if seller_score > buyer_score + 5:
            winner = "SELLERS"
            signal = "BREAKDOWN IMMINENT"
            explanation = "Sellers are overpowering support, price breaking lower."
        elif buyer_score > seller_score + 5:
            winner = "BUYERS"
            signal = "SUPPORT HOLDING"
            explanation = "Buyers are defending support, absorbing selling."
        else:
            winner = "NEUTRAL"
            signal = "NO CLEAR SIGNAL"
            explanation = "Battle at support is evenly matched."

    else:
        # Not near any significant level
        level_type = "NONE"
        level_price = curr_close
        distance = 0.0
        winner = "NEUTRAL"
        signal = "NO CLEAR SIGNAL"
        explanation = "Price is not near a key support or resistance level."

    # Build result
    last_updated = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    clean_display = symbol.replace("-", "").replace("_", "").upper()

    return {
        "symbol": clean_display,
        "timeframe": timeframe,
        "curr_close": round(curr_close, 6),
        "level_type": level_type,
        "level_price": round(level_price, 6),
        "distance_to_level": round(distance, 2),
        "winner": winner,
        "signal": signal,
        "explanation": explanation,
        "support": round(support, 6),
        "resistance": round(resistance, 6),
        "last_updated": last_updated
    }, None


def compute_battle_score(highs, lows, closes, volumes, level, level_type, lookback=5):
    """
    Compute buyer and seller scores from the last `lookback` candles.
    - For RESISTANCE: bullish candles indicate buyers winning, bearish candles with wicks indicate sellers defending.
    - For SUPPORT: bearish candles indicate sellers winning, bullish candles with wicks indicate buyers defending.
    """
    buyer_score = 0
    seller_score = 0

    # Calculate average volume for context
    avg_vol = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)

    for i in range(max(0, len(closes) - lookback), len(closes)):
        candle_high = highs[i]
        candle_low = lows[i]
        candle_open = closes[i-1] if i > 0 else closes[i]
        candle_close = closes[i]
        candle_vol = volumes[i] if i < len(volumes) else 0
        candle_range = candle_high - candle_low

        if candle_range <= 0:
            continue

        # Determine if candle is bullish or bearish
        is_bullish = candle_close > candle_open
        is_bearish = candle_close < candle_open

        # Close position in candle (0 = low, 1 = high)
        close_position = (candle_close - candle_low) / candle_range

        # Check wick lengths
        upper_wick = candle_high - max(candle_open, candle_close)
        lower_wick = min(candle_open, candle_close) - candle_low

        # Volume relative to average
        vol_ratio = candle_vol / avg_vol if avg_vol > 0 else 1.0
        is_high_vol = vol_ratio > 1.2

        if level_type == "RESISTANCE":
            # At resistance, buyers are trying to break through, sellers are defending.
            # Buyers winning: bullish candle closing near high with volume
            if is_bullish and close_position > 0.7:
                buyer_score += 3
                if is_high_vol:
                    buyer_score += 2
            # Sellers winning: bearish candle with long upper wick (rejection)
            if is_bearish and upper_wick / candle_range > 0.3:
                seller_score += 3
                if is_high_vol:
                    seller_score += 2
            # Also check for bullish wick rejection at resistance (if price tried but failed)
            if is_bullish and upper_wick / candle_range > 0.3:
                seller_score += 2  # rejection of resistance

        elif level_type == "SUPPORT":
            # At support, sellers are trying to break down, buyers are defending.
            # Sellers winning: bearish candle closing near low with volume
            if is_bearish and close_position < 0.3:
                seller_score += 3
                if is_high_vol:
                    seller_score += 2
            # Buyers winning: bullish candle with long lower wick (rejection of support)
            if is_bullish and lower_wick / candle_range > 0.3:
                buyer_score += 3
                if is_high_vol:
                    buyer_score += 2
            # Also check for bearish wick rejection at support (if price tried but bounced)
            if is_bearish and lower_wick / candle_range > 0.3:
                buyer_score += 2  # rejection of support

        # Additional volume-weighted points
        if is_high_vol:
            if is_bullish:
                buyer_score += 1  # volume confirms bullish intent
            else:
                seller_score += 1

        # Add points for consecutive candles in same direction (momentum)
        if i > 0:
            prev_close = closes[i-1]
            if is_bullish and candle_close > prev_close:
                buyer_score += 1
            elif is_bearish and candle_close < prev_close:
                seller_score += 1

    return buyer_score, seller_score


def _process_symbol_tf(symbol: str, tf: str):
    if is_unsupported(symbol):
        return None, "UNSUPPORTED"
    df = fetch_ohlcv(symbol, tf)
    if df.empty:
        return None, "DATA UNAVAILABLE"
    return analyze_level_battle(df, symbol, tf)


def run_scanner_pipeline(symbols: list, timeframe: str = "ALL"):
    results = []
    diagnostics = {
        "total_scanned": 0,
        "passed": 0,
        "unsupported": 0,
        "failed_logic": 0,
        "displayed": 0,
        "rejections": {}
    }

    tfs_to_run = ["5M", "15M", "1H", "4H"] if timeframe == "ALL" else [timeframe]

    for sym in symbols:
        for tf in tfs_to_run:
            diagnostics["total_scanned"] += 1
            match, err = _process_symbol_tf(sym, tf)
            if match:
                diagnostics["passed"] += 1
                results.append(match)
            elif err == "UNSUPPORTED":
                diagnostics["unsupported"] += 1
            else:
                diagnostics["failed_logic"] += 1
                diagnostics["rejections"][err] = diagnostics["rejections"].get(err, 0) + 1

    results.sort(key=lambda x: 0 if x.get("winner") == "NEUTRAL" else 1, reverse=True)
    diagnostics["displayed"] = len(results)
    return results, diagnostics
