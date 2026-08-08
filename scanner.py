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
    Determines who is winning at the nearest support/resistance level
    using candle behavior and volume confirmation.
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

    # 2. Determine which level price is nearest to (within 5%)
    dist_to_res = (resistance - curr_close) / curr_close * 100
    dist_to_sup = (curr_close - support) / curr_close * 100
    threshold = 5.0

    if dist_to_res < dist_to_sup and dist_to_res < threshold:
        level_type = "RESISTANCE"
        level_price = resistance
        distance = dist_to_res
        winner, signal, explanation = evaluate_battle_at_resistance(
            highs, lows, closes, volumes, level_price
        )
    elif dist_to_sup < threshold:
        level_type = "SUPPORT"
        level_price = support
        distance = dist_to_sup
        winner, signal, explanation = evaluate_battle_at_support(
            highs, lows, closes, volumes, level_price
        )
    else:
        level_type = "NONE"
        level_price = curr_close
        distance = 0.0
        winner = "NEUTRAL"
        signal = "NO CLEAR SIGNAL"
        explanation = "Price is not near a key support or resistance level."

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


def evaluate_battle_at_resistance(highs, lows, closes, volumes, resistance, lookback=10):
    """
    Evaluate the battle at a resistance level.
    - BUYERS winning: price is repeatedly testing resistance with bullish closes,
      higher highs, less rejection, increasing volume on up-moves.
    - SELLERS winning: price is being rejected with bearish closes,
      long upper wicks, decreasing volume on up-moves.
    """
    # Focus on candles near the resistance level (within 0.5% of resistance)
    near_resistance = []
    for i in range(max(0, len(closes) - lookback), len(closes)):
        if (resistance - highs[i]) / resistance < 0.005 or (resistance - closes[i]) / resistance < 0.005:
            near_resistance.append(i)

    if len(near_resistance) < 2:
        # Not enough tests of the level – wait for more data
        return "NEUTRAL", "NO CLEAR SIGNAL", "Insufficient tests of resistance to determine winner."

    buyer_score = 0
    seller_score = 0
    tests = 0
    rejections = 0

    for i in near_resistance:
        candle_high = highs[i]
        candle_low = lows[i]
        candle_open = closes[i-1] if i > 0 else closes[i]
        candle_close = closes[i]
        candle_vol = volumes[i] if i < len(volumes) else 0
        candle_range = candle_high - candle_low

        if candle_range <= 0:
            continue

        tests += 1

        # 1. Is the candle bullish or bearish?
        is_bullish = candle_close > candle_open
        is_bearish = candle_close < candle_open
        close_position = (candle_close - candle_low) / candle_range

        # 2. Is there a rejection wick at resistance?
        upper_wick = candle_high - max(candle_open, candle_close)
        rejection = upper_wick / candle_range if candle_range > 0 else 0

        # 3. Volume confirmation
        avg_vol = np.mean(volumes) if len(volumes) > 0 else 1
        vol_ratio = candle_vol / avg_vol if avg_vol > 0 else 1

        # 4. Score the candle
        if is_bullish and close_position > 0.65:
            # Bullish close near the high – buyers pushing into resistance
            buyer_score += 3
            if vol_ratio > 1.2:
                buyer_score += 2  # volume confirms buying pressure
            if rejection < 0.2:
                # Little rejection – buyers are absorbing
                buyer_score += 2

        if is_bearish and rejection > 0.3:
            # Bearish rejection at resistance – sellers defending
            seller_score += 3
            if vol_ratio > 1.2:
                seller_score += 2  # volume confirms selling pressure

        # 5. Consecutive behavior: higher highs / higher lows
        if i > 0:
            prev_high = highs[i-1]
            prev_close = closes[i-1]
            if is_bullish and candle_high > prev_high:
                buyer_score += 1  # buyers pushing higher
            if is_bearish and candle_close < prev_close:
                seller_score += 1  # sellers pushing lower

        # 6. Accumulating rejections – sellers getting stronger
        if rejection > 0.4:
            rejections += 1

    # 7. If multiple rejections (≥2) and sellers have higher score
    if rejections >= 2 and seller_score > buyer_score:
        return "SELLERS", "RESISTANCE HOLDING", "Resistance is holding strong with repeated rejections and sellers dominating the closes."

    # 8. If buyers are repeatedly testing with bullish closes and less rejection
    if tests >= 3 and buyer_score > seller_score + 5:
        return "BUYERS", "BREAKOUT IMMINENT", "Buyers are absorbing selling pressure near resistance with bullish closes, breakout is imminent."

    # 9. Edge case: mixed signals
    if buyer_score > seller_score:
        return "BUYERS", "BREAKOUT IMMINENT", "Buyers are showing strength near resistance."
    elif seller_score > buyer_score:
        return "SELLERS", "RESISTANCE HOLDING", "Sellers are defending resistance effectively."
    else:
        return "NEUTRAL", "NO CLEAR SIGNAL", "Battle at resistance is evenly matched."


def evaluate_battle_at_support(highs, lows, closes, volumes, support, lookback=10):
    """
    Evaluate the battle at a support level.
    - SELLERS winning: price is repeatedly attacking support with bearish closes,
      lower lows, less rejection, increasing volume on down-moves.
    - BUYERS winning: price is being defended with bullish closes,
      long lower wicks, decreasing volume on down-moves.
    """
    near_support = []
    for i in range(max(0, len(closes) - lookback), len(closes)):
        if (lows[i] - support) / support < 0.005 or (closes[i] - support) / support < 0.005:
            near_support.append(i)

    if len(near_support) < 2:
        return "NEUTRAL", "NO CLEAR SIGNAL", "Insufficient tests of support to determine winner."

    buyer_score = 0
    seller_score = 0
    tests = 0
    defenses = 0

    for i in near_support:
        candle_high = highs[i]
        candle_low = lows[i]
        candle_open = closes[i-1] if i > 0 else closes[i]
        candle_close = closes[i]
        candle_vol = volumes[i] if i < len(volumes) else 0
        candle_range = candle_high - candle_low

        if candle_range <= 0:
            continue

        tests += 1

        is_bullish = candle_close > candle_open
        is_bearish = candle_close < candle_open
        close_position = (candle_close - candle_low) / candle_range

        lower_wick = min(candle_open, candle_close) - candle_low
        defense = lower_wick / candle_range if candle_range > 0 else 0

        avg_vol = np.mean(volumes) if len(volumes) > 0 else 1
        vol_ratio = candle_vol / avg_vol if avg_vol > 0 else 1

        # Score the candle
        if is_bearish and close_position < 0.35:
            # Bearish close near the low – sellers pushing through support
            seller_score += 3
            if vol_ratio > 1.2:
                seller_score += 2
            if defense < 0.2:
                # Little defense – sellers overpowering
                seller_score += 2

        if is_bullish and defense > 0.3:
            # Bullish rejection at support – buyers defending
            buyer_score += 3
            if vol_ratio > 1.2:
                buyer_score += 2

        # Consecutive behavior
        if i > 0:
            prev_low = lows[i-1]
            prev_close = closes[i-1]
            if is_bearish and candle_low < prev_low:
                seller_score += 1
            if is_bullish and candle_close > prev_close:
                buyer_score += 1

        # Accumulating defenses – buyers getting stronger
        if defense > 0.4:
            defenses += 1

    if defenses >= 2 and buyer_score > seller_score:
        return "BUYERS", "SUPPORT HOLDING", "Support is holding strong with repeated bullish rejections and buyers defending the level."

    if tests >= 3 and seller_score > buyer_score + 5:
        return "SELLERS", "BREAKDOWN IMMINENT", "Sellers are overpowering support with bearish closes, breakdown is imminent."

    if seller_score > buyer_score:
        return "SELLERS", "BREAKDOWN IMMINENT", "Sellers are showing strength near support."
    elif buyer_score > seller_score:
        return "BUYERS", "SUPPORT HOLDING", "Buyers are defending support effectively."
    else:
        return "NEUTRAL", "NO CLEAR SIGNAL", "Battle at support is evenly matched."


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

    # Sort by priority: BUYERS/SELLERS winning first, then NEUTRAL
    def sort_key(item):
        if item.get("winner") == "BUYERS":
            return 1
        elif item.get("winner") == "SELLERS":
            return 0
        else:
            return -1
    results.sort(key=sort_key, reverse=True)
    diagnostics["displayed"] = len(results)
    return results, diagnostics
