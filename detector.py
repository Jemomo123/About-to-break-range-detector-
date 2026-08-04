# detector.py
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


def find_swing_points(highs, lows, window=2):
    """Identifies pivot highs and pivot lows strictly from price wicks."""
    swing_highs = []
    swing_lows = []
    n = len(highs)
    
    for i in range(window, n - window):
        # Local Max High
        if all(highs[i] >= highs[i - j] for j in range(1, window + 1)) and \
           all(highs[i] >= highs[i + j] for j in range(1, window + 1)):
            swing_highs.append((i, highs[i]))
            
        # Local Min Low
        if all(lows[i] <= lows[i - j] for j in range(1, window + 1)) and \
           all(lows[i] <= lows[i + j] for j in range(1, window + 1)):
            swing_lows.append((i, lows[i]))
            
    return swing_highs, swing_lows


def validate_range_structure(highs, lows, closes, lookback=25):
    """Pure Price Action Structure Validator."""
    if len(closes) < lookback:
        return None

    w_highs = highs[-lookback:]
    w_lows = lows[-lookback:]
    w_closes = closes[-lookback:]
    curr_close = float(w_closes[-1])

    # 1. Extract Swings
    s_highs, s_lows = find_swing_points(w_highs, w_lows, window=2)
    
    # Must have at least 2 distinct swing highs and 2 distinct swing lows
    if len(s_highs) < 2 or len(s_lows) < 2:
        return None

    sh_prices = [p for _, p in s_highs]
    sl_prices = [p for _, p in s_lows]

    # Calculate Flatness Tolerance (within 0.3% price variance)
    max_h, min_h = max(sh_prices), min(sh_prices)
    max_l, min_l = max(sl_prices), min(sl_prices)

    is_flat_top = ((max_h - min_h) / curr_close) * 100.0 <= 0.35
    is_flat_bottom = ((max_l - min_l) / curr_close) * 100.0 <= 0.35

    # Determine Swing Slopes (Progression)
    rising_lows = all(sl_prices[i] < sl_prices[i+1] for i in range(len(sl_prices)-1))
    falling_highs = all(sh_prices[i] > sh_prices[i+1] for i in range(len(sh_prices)-1))
    rising_highs = all(sh_prices[i] < sh_prices[i+1] for i in range(len(sh_prices)-1))
    falling_lows = all(sl_prices[i] > sl_prices[i+1] for i in range(len(sl_prices)-1))

    # Reject Strong Trends (Higher Highs + Higher Lows OR Lower Highs + Lower Lows)
    if (rising_highs and rising_lows) or (falling_highs and falling_lows):
        return None

    # Reject Expanding Structures (Lower Lows + Higher Highs)
    if falling_lows and rising_highs:
        return None

    # Identify the 3 Specific Valid Price Action Structures
    structure_type = None

    if is_flat_top and is_flat_bottom:
        structure_type = "HORIZONTAL_RANGE"
        res_level = max_h
        sup_level = min_l
    elif is_flat_top and rising_lows:
        structure_type = "FLAT_RESISTANCE_RISING_LOWS"
        res_level = max_h
        sup_level = sl_prices[-1]  # Active trendline support anchor
    elif is_flat_bottom and falling_highs:
        structure_type = "FLAT_SUPPORT_FALLING_HIGHS"
        res_level = sh_prices[-1]  # Active trendline resistance anchor
        sup_level = min_l
    else:
        return None  # Unstructured or noisy price action

    r_height = res_level - sup_level
    if r_height <= 0:
        return None

    # 2. Strict Breakout Guard
    # Drop immediately if price has broken out past resistance or support (+0.1% tolerance)
    if curr_close > (res_level * 1.001) or curr_close < (sup_level * 0.999):
        return None

    # Containment: At least 75% of candle bodies must trade inside the boundary
    inside_count = np.sum((w_closes <= (res_level * 1.0005)) & (w_closes >= (sup_level * 0.9995)))
    containment = round(float((inside_count / lookback) * 100.0), 1)
    
    if containment < 75.0:
        return None

    return {
        "v_high": res_level,
        "v_low": sup_level,
        "r_height": r_height,
        "upper_touches": len(s_highs),
        "lower_touches": len(s_lows),
        "containment_pct": containment,
        "current_close": curr_close,
        "structure_type": structure_type
    }


def analyze_order_battle(volumes, closes):
    """Pure Price Action Volume & Candle Body Battle Check."""
    if len(volumes) < 10: return "BALANCED"
    
    # Check body direction of last 5 candles
    recent_closes = closes[-5:]
    bullish_count = np.sum(np.diff(recent_closes) > 0)
    
    avg_vol = np.mean(volumes[:-5])
    recent_vol = np.mean(volumes[-5:])
    vol_building = recent_vol > avg_vol if avg_vol > 0 else False

    if bullish_count >= 4 and vol_building:
        return "BUYERS WINNING"
    elif bullish_count <= 1 and vol_building:
        return "SELLERS WINNING"
    return "BALANCED"
