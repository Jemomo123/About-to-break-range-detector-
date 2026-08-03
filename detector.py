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
    okx_error_msg = ""
    mexc_error_msg = ""
    timestamp_param = int(time.time() * 1000)

    # 1. Primary: OKX Futures (Fresh Uncached Requests)
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


def validate_range_structure(highs, lows, closes, lookback=25, breakout_threshold_pct=0.25):
    if len(closes) < lookback:
        return None

    w_highs = highs[-lookback:]
    w_lows = lows[-lookback:]
    w_closes = closes[-lookback:]
    
    v_high = float(np.max(w_highs))
    v_low = float(np.min(w_lows))
    r_height = v_high - v_low
    current_close = float(w_closes[-1])
    current_high = float(w_highs[-1])
    current_low = float(w_lows[-1])

    if r_height <= 0 or current_close <= 0:
        return None

    # Requirement 4: Reject Breakouts Beyond Allowed Threshold (0.25%)
    max_allowed_high = v_high * (1.0 + (breakout_threshold_pct / 100.0))
    min_allowed_low = v_low * (1.0 - (breakout_threshold_pct / 100.0))

    if current_close > max_allowed_high or current_close < min_allowed_low:
        return None
    if current_high > max_allowed_high or current_low < min_allowed_low:
        return None

    # Range Height Boundaries (Min 0.8%, Max 3.5%)
    range_pct = (r_height / current_close) * 100.0
    if range_pct < 0.8 or range_pct > 3.5:
        return None

    # Reject Trends/Channels via Slope
    x = np.arange(lookback)
    slope, _ = np.polyfit(x, w_closes, 1)
    if ((abs(slope) / current_close) * 100.0) > 0.12:
        return None

    # Reject V-Shapes
    if (np.std(w_closes) / r_height) > 0.38:
        return None

    # Distinct Touches
    touch_buf = r_height * 0.035
    upper_touch_indices = np.where(w_highs >= (v_high - touch_buf))[0]
    lower_touch_indices = np.where(w_lows <= (v_low + touch_buf))[0]

    def count_separated_touches(indices):
        if len(indices) < 2: return 0
        count, last_idx = 1, indices[0]
        for idx in indices[1:]:
            if idx - last_idx >= 2:
                count += 1
                last_idx = idx
        return count

    if count_separated_touches(upper_touch_indices) < 2 or count_separated_touches(lower_touch_indices) < 2:
        return None

    # Containment Check
    inner_upper = v_high - (r_height * 0.05)
    inner_lower = v_low + (r_height * 0.05)
    inside_count = np.sum((w_closes <= inner_upper) & (w_closes >= inner_lower))
    containment = round(float((inside_count / lookback) * 100.0), 1)

    if containment < 70.0:
        return None

    return {
        "v_high": v_high,
        "v_low": v_low,
        "r_height": r_height,
        "upper_touches": count_separated_touches(upper_touch_indices),
        "lower_touches": count_separated_touches(lower_touch_indices),
        "containment_pct": containment,
        "current_close": current_close
    }


def analyze_order_battle(volumes, closes):
    if len(volumes) < 10: return "BALANCED"
    recent_vol = volumes[-5:]
    avg_vol = np.mean(volumes)
    vol_ratio = np.mean(recent_vol) / avg_vol if avg_vol > 0 else 1.0
    recent_closes = closes[-5:]
    bullish_candles = np.sum(np.diff(recent_closes) > 0)
    buy_ratio = (bullish_candles / 4.0) if len(recent_closes) >= 5 else 0.5

    if buy_ratio >= 0.60 and vol_ratio >= 1.05: return "BUYERS WINNING"
    elif buy_ratio <= 0.40 and vol_ratio >= 1.05: return "SELLERS WINNING"
    return "BALANCED"
