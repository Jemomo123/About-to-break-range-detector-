# detector.py
import requests
import numpy as np
import logging
from config import OKX_CANDLE_URL, MEXC_CANDLE_URL, OKX_TF_MAP, MEXC_TF_MAP

HEADERS = {"User-Agent": "Mozilla/5.0"}

def fetch_market_candles(symbol, timeframe, limit=100):
    # OKX Primary
    try:
        inst_id = f"{symbol[:-4]}-USDT-SWAP" if symbol.endswith("USDT") else f"{symbol}-SWAP"
        bar = OKX_TF_MAP.get(timeframe, "1H")
        res = requests.get(OKX_CANDLE_URL, params={"instId": inst_id, "bar": bar, "limit": limit}, headers=HEADERS, timeout=3.5)
        if res.status_code == 200 and res.json().get("code") == "0":
            data = list(reversed(res.json()["data"]))
            highs = np.array([float(c[2]) for c in data])
            lows = np.array([float(c[3]) for c in data])
            closes = np.array([float(c[4]) for c in data])
            volumes = np.array([float(c[5]) for c in data])
            return highs, lows, closes, volumes
    except Exception as e:
        logging.warning(f"OKX error for {symbol}: {e}")

    # MEXC Fallback
    try:
        mexc_symbol = f"{symbol[:-4]}_USDT" if symbol.endswith("USDT") else symbol
        tf_str = MEXC_TF_MAP.get(timeframe, "Min60")
        res = requests.get(f"{MEXC_CANDLE_URL}{mexc_symbol}", params={"interval": tf_str}, headers=HEADERS, timeout=3.5)
        if res.status_code == 200 and res.json().get("success"):
            d = res.json()["data"]
            return (
                np.array(d["high"][-limit:], dtype=float),
                np.array(d["low"][-limit:], dtype=float),
                np.array(d["close"][-limit:], dtype=float),
                np.array(d["vol"][-limit:], dtype=float)
            )
    except Exception as e:
        logging.warning(f"MEXC error for {symbol}: {e}")

    return None

def validate_range_structure(highs, lows, closes, lookback=50):
    if len(closes) < lookback:
        return None

    w_highs, w_lows, w_closes = highs[-lookback:], lows[-lookback:], closes[-lookback:]
    v_high, v_low = float(np.max(w_highs)), float(np.min(w_lows))
    r_height = v_high - v_low

    if r_height <= 0:
        return None

    touch_buffer = r_height * 0.015
    upper_touches = int(np.sum(w_highs >= (v_high - touch_buffer)))
    lower_touches = int(np.sum(w_lows <= (v_low + touch_buffer)))

    inner_upper, inner_lower = v_high - (r_height * 0.05), v_low + (r_height * 0.05)
    containment = round(float((np.sum((w_closes <= inner_upper) & (w_closes >= inner_lower)) / lookback) * 100.0), 1)

    current_close = float(closes[-1])
    has_expanded = current_close > v_high or current_close < v_low

    if containment < 70.0 or upper_touches < 2 or lower_touches < 2 or has_expanded:
        return None

    return {
        "v_high": v_high,
        "v_low": v_low,
        "r_height": r_height,
        "upper_touches": upper_touches,
        "lower_touches": lower_touches,
        "containment_pct": containment,
        "current_close": current_close
    }

def analyze_order_battle(volumes, closes):
    if len(volumes) < 20:
        return "BALANCED"

    recent_vol = volumes[-5:]
    avg_vol = np.mean(volumes[-20:])
    vol_ratio = np.mean(recent_vol) / avg_vol if avg_vol > 0 else 1.0

    recent_closes = closes[-5:]
    bullish_candles = np.sum(np.diff(recent_closes) > 0)
    buy_ratio = (bullish_candles / 4.0) if len(recent_closes) >= 5 else 0.5

    if buy_ratio >= 0.60 and vol_ratio >= 1.1:
        return "BUYERS WINNING"
    elif buy_ratio <= 0.40 and vol_ratio >= 1.1:
        return "SELLERS WINNING"
    return "BALANCED"
