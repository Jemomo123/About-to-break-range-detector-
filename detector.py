# detector.py - Backend Range Detection Engine Version 2.0
import requests
import numpy as np
import time
from config import OKX_CANDLE_URL, MEXC_CANDLE_URL, OKX_TF_MAP, MEXC_TF_MAP

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache"
}

def fetch_market_candles(symbol, timeframe, limit=100):
    """Fetches real-time uncached market data. Primary: OKX, Fallback: MEXC."""
    okx_error_msg, mexc_error_msg = "", ""
    timestamp_param = int(time.time() * 1000)

    # 1. Primary: OKX Futures
    try:
        inst_id = f"{symbol[:-4]}-USDT-SWAP" if symbol.endswith("USDT") else f"{symbol}-SWAP"
        bar = OKX_TF_MAP.get(timeframe, "1H")
        params = {"instId": inst_id, "bar": bar, "limit": limit, "_t": timestamp_param}
        res = requests.get(OKX_CANDLE_URL, params=params, headers=HEADERS, timeout=3.0)
        
        if res.status_code == 200:
            body = res.json()
            if body.get("code") == "0" and body.get("data"):
                data = list(reversed(body["data"]))
                highs = np.array([float(c[2]) for c in data])
                lows = np.array([float(c[3]) for c in data])
                closes = np.array([float(c[4]) for c in data])
                volumes = np.array([float(c[5]) for c in data])
                if len(closes) > 0:
                    return (highs, lows, closes, volumes), "OKX", None
            else:
                okx_error_msg = f"OKX API returned code={body.get('code')}"
        else:
            okx_error_msg = f"OKX HTTP {res.status_code}"
    except Exception as e:
        okx_error_msg = f"OKX Exception: {str(e)}"

    # 2. Fallback: MEXC Futures
    try:
        mexc_symbol = f"{symbol[:-4]}_USDT" if symbol.endswith("USDT") else symbol
        tf_str = MEXC_TF_MAP.get(timeframe, "Min60")
        params = {"interval": tf_str, "_t": timestamp_param}
        res = requests.get(f"{MEXC_CANDLE_URL}{mexc_symbol}", params=params, headers=HEADERS, timeout=3.0)
        
        if res.status_code == 200:
            body = res.json()
            if body.get("success") and body.get("data"):
                d = body["data"]
                highs = np.array(d["high"][-limit:], dtype=float)
                lows = np.array(d["low"][-limit:], dtype=float)
                closes = np.array(d["close"][-limit:], dtype=float)
                volumes = np.array(d["vol"][-limit:], dtype=float)
                if len(closes) > 0:
                    return (highs, lows, closes, volumes), "MEXC", None
            else:
                mexc_error_msg = f"MEXC API returned code={body.get('code')}"
        else:
            mexc_error_msg = f"MEXC HTTP {res.status_code}"
    except Exception as e:
        mexc_error_msg = f"MEXC Exception: {str(e)}"

    failure_reason = f"{symbol} -> OKX: {okx_error_msg} | MEXC: {mexc_error_msg}"
    print(failure_reason, flush=True)
    return None, "NONE", failure_reason


def extract_swing_pivots(highs, lows, window=2):
    """Extracts raw local swing highs and swing lows strictly from candle wicks."""
    swing_highs = []
    swing_lows = []
    n = len(highs)
    
    for i in range(window, n - window):
        if all(highs[i] >= highs[i - j] for j in range(1, window + 1)) and \
           all(highs[i] >= highs[i + j] for j in range(1, window + 1)):
            swing_highs.append((i, highs[i]))
            
        if all(lows[i] <= lows[i - j] for j in range(1, window + 1)) and \
           all(lows[i] <= lows[i + j] for j in range(1, window + 1)):
            swing_lows.append((i, lows[i]))
            
    return swing_highs, swing_lows


def validate_range_structure(highs, lows, closes, lookback=25):
    """
    STEP 1 & STEP 2: Detect & Validate REAL Price Ranges using Price Action.
    Returns structured range data if valid, or None (Instant Reject).
    """
    if len(closes) < lookback:
        return None

    w_highs = highs[-lookback:]
    w_lows = lows[-lookback:]
    w_closes = closes[-lookback:]
    curr_close = float(w_closes[-1])
    curr_high = float(w_highs[-1])
    curr_low = float(w_lows[-1])

    # 1. Pivot Swing Analysis
    s_highs, s_lows = extract_swing_pivots(w_highs, w_lows, window=2)
    
    # Needs at least 2 distinct swing high tests and 2 distinct swing low tests
    if len(s_highs) < 2 or len(s_lows) < 2:
        return None

    sh_prices = [p for _, p in s_highs]
    sl_prices = [p for _, p in s_lows]

    # Calculate cluster boundaries (ignoring outlier single-wick spikes)
    resistance = float(np.percentile(sh_prices, 85))
    support = float(np.percentile(sl_prices, 15))
    
    # Anchor check: Resistance must be strictly greater than support
    r_height = resistance - support
    if r_height <= 0 or curr_close <= 0:
        return None

    # Range Height Boundaries: Height must be between 0.6% and 3.5% of current price
    range_pct = (r_height / curr_close) * 100.0
    if range_pct < 0.6 or range_pct > 3.5:
        return None

    # 2. STEP 3 REJECTION CHECKS
    # Reject Already Broken Out Markets (Strict 0.15% clearance guard)
    max_allowed = resistance * 1.0015
    min_allowed = support * 0.9985
    if curr_close > max_allowed or curr_close < min_allowed:
        return None
    if curr_high > (resistance * 1.003) or curr_low < (support * 0.997):
        return None

    # Reject Strong Trends (Higher Highs + Higher Lows OR Lower Highs + Lower Lows)
    rising_highs = all(sh_prices[i] < sh_prices[i+1] for i in range(len(sh_prices)-1))
    rising_lows = all(sl_prices[i] < sl_prices[i+1] for i in range(len(sl_prices)-1))
    falling_highs = all(sh_prices[i] > sh_prices[i+1] for i in range(len(sh_prices)-1))
    falling_lows = all(sl_prices[i] > sl_prices[i+1] for i in range(len(sl_prices)-1))

    if (rising_highs and rising_lows) or (falling_highs and falling_lows):
        return None

    # Reject Expanding / Widening Structures (Lower Lows + Higher Highs)
    if falling_lows and rising_highs:
        return None

    # Reject Linear Slopes (No strong trending channels)
    x = np.arange(lookback)
    slope, _ = np.polyfit(x, w_closes, 1)
    if ((abs(slope) / curr_close) * 100.0) > 0.10:
        return None

    # 3. Containment Test: At least 70% of candle closes must trade inside support/resistance
    inside_count = np.sum((w_closes <= (resistance * 1.001)) & (w_closes >= (support * 0.999)))
    containment = round(float((inside_count / lookback) * 100.0), 1)
    
    if containment < 70.0:
        return None

    # Determine Range Quality Score
    touch_count = len(s_highs) + len(s_lows)
    quality_score = min(int((containment * 0.6) + (touch_count * 8)), 100)

    return {
        "support": support,
        "resistance": resistance,
        "r_height": r_height,
        "r_height_pct": round(range_pct, 2),
        "curr_close": curr_close,
        "upper_touches": len(s_highs),
        "lower_touches": len(s_lows),
        "containment_pct": containment,
        "range_quality": quality_score
    }


def analyze_buyer_seller_battle(range_data, volumes, closes):
    """
    STEP 4: Evaluate Price Position & Order Flow Battle (Executed ONLY for valid ranges).
    """
    curr_close = range_data["curr_close"]
    support = range_data["support"]
    resistance = range_data["resistance"]
    r_height = range_data["r_height"]

    # 1. Calculate Price Position (0% = Support, 100% = Resistance)
    price_position = float(np.clip(((curr_close - support) / r_height) * 100.0, 0.0, 100.0))

    # 2. Measure Buyer vs Seller Power via recent candle dynamics & volume
    recent_closes = closes[-5:]
    bullish_candles = np.sum(np.diff(recent_closes) > 0)
    
    avg_vol = np.mean(volumes[:-5]) if len(volumes) > 5 else 1.0
    recent_vol = np.mean(volumes[-5:])
    vol_ratio = (recent_vol / avg_vol) if avg_vol > 0 else 1.0

    buyer_power = int(np.clip((bullish_candles / 4.0) * 100 * (1.1 if vol_ratio > 1.05 else 0.9), 10, 95))
    seller_power = 100 - buyer_power

    # 3. Categorize Battle Dynamics & Direction according to Spec V2.0
    if price_position >= 70.0:
        if buyer_power >= 55:
            direction = "UPSIDE"
            interpretation = "Buyers dominating near resistance. High likelihood of upward breakout."
        else:
            direction = "REJECTION RISK"
            interpretation = "Price near resistance, but sellers showing rejection pressure."
    elif price_position <= 30.0:
        if seller_power >= 55:
            direction = "DOWNSIDE"
            interpretation = "Sellers dominating near support. High likelihood of downward breakdown."
        else:
            direction = "ABSORPTION RISK"
            interpretation = "Price near support, but buyers actively absorbing sell pressure."
    else:
        direction = "BALANCED"
        interpretation = "Price trading near range equilibrium. Consolidating prior to next move."

    return {
        "price_position": round(price_position, 1),
        "buyer_power": buyer_power,
        "seller_power": seller_power,
        "direction": direction,
        "interpretation": interpretation
    }


def calculate_breakout_readiness(range_data, battle_data):
    """
    STEP 4: Calculates Breakout Readiness score and maps to official label rankings.
    """
    curr_close = range_data["curr_close"]
    support = range_data["support"]
    resistance = range_data["resistance"]
    pos = battle_data["price_position"]
    direction = battle_data["direction"]
    quality = range_data["range_quality"]

    # Calculate distance to nearest boundary
    dist_to_res = ((resistance - curr_close) / curr_close) * 100.0
    dist_to_sup = ((curr_close - support) / curr_close) * 100.0
    distance_pct = round(min(abs(dist_to_res), abs(dist_to_sup)), 2)

    # Readiness Score Calculation based on Compression, Position, & Battle
    boundary_proximity = max(pos, 100.0 - pos)  # Higher near 0% or 100%
    decisiveness = 25 if direction in ["UPSIDE", "DOWNSIDE"] else 10

    raw_score = (quality * 0.25) + (boundary_proximity * 0.50) + decisiveness
    readiness_score = int(np.clip(raw_score, 10, 98))

    # Spec V2.0 Mapping
    if readiness_score >= 90: label = "IMMINENT"
    elif readiness_score >= 82: label = "VERY HIGH"
    elif readiness_score >= 75: label = "HIGH"
    elif readiness_score >= 65: label = "BUILDING"
    elif readiness_score >= 50: label = "DEVELOPING"
    elif readiness_score >= 35: label = "WATCH"
    else: label = "LOW"

    return {
        "readiness_score": readiness_score,
        "readiness_label": label,
        "readiness_display": f"{readiness_score}% ({label})",
        "distance_pct": distance_pct
    }
