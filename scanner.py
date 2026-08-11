import threading
import numpy as np
import pandas as pd
import requests

# ===== CONFIGURATION =====
DEBUG = True
PROXIMITY_THRESHOLD = 1.5          # 1.5% – battle logic only runs within this %
INVALIDATION_WAIT_CANDLES = 1      # number of candles to stay invalidated before new range accepted
# =========================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

UNSUPPORTED_SYMBOLS = set()
UNSUPPORTED_LOCK = threading.Lock()

# ===== RANGE STATE – PERSISTENT STORAGE =====
RANGE_STATE = {}
RANGE_STATE_LOCK = threading.Lock()


def is_unsupported(symbol: str) -> bool:
    with UNSUPPORTED_LOCK:
        return symbol in UNSUPPORTED_SYMBOLS


def mark_unsupported(symbol: str):
    with UNSUPPORTED_LOCK:
        UNSUPPORTED_SYMBOLS.add(symbol)


def get_existing_range(symbol: str, timeframe: str):
    key = f"{symbol}_{timeframe}"
    with RANGE_STATE_LOCK:
        return RANGE_STATE.get(key, None)


def set_range(symbol: str, timeframe: str, range_data):
    key = f"{symbol}_{timeframe}"
    with RANGE_STATE_LOCK:
        RANGE_STATE[key] = range_data


def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 150) -> pd.DataFrame:
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
                parsed = [row[:6] for row in data if len(row) >= 6]
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


# =====================================================================
# TREND FILTER & VALIDATED RANGE DETECTION
# =====================================================================
def is_actively_trending(df: pd.DataFrame, sma_fast=20, sma_slow=100) -> bool:
    """Suppresses range detection during active directional trends / dumps."""
    if df.empty or len(df) < sma_slow:
        return False

    closes = df['close'].values
    sma20 = df['close'].rolling(sma_fast).mean().values
    sma100 = df['close'].rolling(sma_slow).mean().values

    sma20_slope = (sma20[-1] - sma20[-5]) / sma20[-5] * 100.0 if sma20[-5] > 0 else 0
    c_price = closes[-1]

    is_markdown = (sma20_slope < -0.25) and (c_price < sma20[-1]) and (sma20[-1] < sma100[-1])
    is_markup = (sma20_slope > 0.25) and (c_price > sma20[-1]) and (sma20[-1] > sma100[-1])

    return is_markdown or is_markup


def find_validated_range(df: pd.DataFrame, lookback=40):
    """Detects structurally valid ranges with time-separated touch verification."""
    if df.empty or len(df) < lookback:
        return None

    recent_df = df.tail(lookback).copy()
    highs = recent_df['high'].values
    lows = recent_df['low'].values
    closes = recent_df['close'].values

    # Percentile filter to eliminate single isolated spike wicks
    p_high = float(np.percentile(highs, 96))
    p_low = float(np.percentile(lows, 4))

    v_high = p_high if np.sum(highs > p_high) <= 1 else float(np.max(highs))
    v_low = p_low if np.sum(lows < p_low) <= 1 else float(np.min(lows))

    r_height = v_high - v_low
    if r_height <= 0:
        return None

    range_width_pct = (r_height / v_low) * 100.0 if v_low > 0 else 100.0
    if range_width_pct < 0.4 or range_width_pct > 15.0:
        return None

    # Time-Separated Touches (minimum 4 candles apart)
    touch_tolerance = r_height * 0.10
    upper_touches = 0
    lower_touches = 0
    last_upper_idx = -10
    last_lower_idx = -10

    for i in range(len(highs)):
        if (v_high - highs[i]) <= touch_tolerance:
            if i - last_upper_idx >= 4:
                upper_touches += 1
                last_upper_idx = i

        if (lows[i] - v_low) <= touch_tolerance:
            if i - last_lower_idx >= 4:
                lower_touches += 1
                last_lower_idx = i

    if upper_touches < 2 or lower_touches < 2:
        return None

    # Containment
    containment_tol = r_height * 0.05
    out_of_bounds = np.sum((closes > (v_high + containment_tol)) | (closes < (v_low - containment_tol)))
    containment_pct = (1.0 - (out_of_bounds / lookback)) * 100.0

    if containment_pct < 70.0:
        return None

    # Expansion Disqualification
    c_price = closes[-1]
    if c_price < v_low or c_price > v_high:
        return None

    return {
        'support': v_low,
        'resistance': v_high,
        'support_touches': lower_touches,
        'resistance_touches': upper_touches,
        'range_status': 'VALIDATED',
        'containment_pct': round(containment_pct, 1),
        'range_width_percent': round(range_width_pct, 2),
        'pattern_type': 'RECTANGLE'
    }


# =====================================================================
# ORDER FLOW & BATTLE EVALUATION
# =====================================================================
def calculate_candle_pressure(row):
    body = abs(row['close'] - row['open'])
    candle_range = row['high'] - row['low']
    if candle_range == 0:
        return {
            'body_ratio': 0, 'close_position': 0.5, 'upper_wick': 0,
            'lower_wick': 0, 'is_bullish': row['close'] > row['open'],
            'is_bearish': row['close'] < row['open']
        }
    return {
        'body_ratio': body / candle_range,
        'close_position': (row['close'] - row['low']) / candle_range,
        'upper_wick': row['high'] - max(row['open'], row['close']),
        'lower_wick': min(row['open'], row['close']) - row['low'],
        'is_bullish': row['close'] > row['open'],
        'is_bearish': row['close'] < row['open']
    }


def get_volume_confirmation(volumes, idx, lookback=20):
    if len(volumes) < lookback:
        return 1.0
    avg_vol = np.mean(volumes[max(0, idx - lookback):idx])
    return volumes[idx] / avg_vol if avg_vol > 0 else 1.0


def evaluate_support_battle(df: pd.DataFrame, support: float, window=8):
    if df.empty or len(df) < window or support <= 0:
        return {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "Insufficient data."}

    c_price = df.iloc[-1]['close']

    # Guard: Immediate breakdown if closed below support
    if c_price < support:
        return {
            "side": "SELLERS",
            "signal": "BREAKDOWN CONFIRMED",
            "score": 10,
            "reason": f"Price closed at ${c_price:.2f}, below support level (${support:.2f})."
        }

    recent = df.tail(window)
    buyer_score = 0
    seller_score = 0

    for idx, row in recent.iterrows():
        pressure = calculate_candle_pressure(row)
        if pressure['is_bearish'] and pressure['close_position'] < 0.4:
            seller_score += 2
        elif pressure['is_bullish'] and pressure['close_position'] > 0.6:
            buyer_score += 2

    if seller_score > buyer_score:
        return {"side": "SELLERS", "signal": "BREAKDOWN IMMINENT", "score": seller_score, "reason": "Sellers building breakdown pressure."}
    elif buyer_score > seller_score:
        return {"side": "BUYERS", "signal": "SUPPORT HOLDING", "score": buyer_score, "reason": "Buyers actively defending support floor."}

    return {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "Battle at support is balanced."}


def evaluate_resistance_battle(df: pd.DataFrame, resistance: float, window=8):
    if df.empty or len(df) < window or resistance <= 0:
        return {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "Insufficient data."}

    c_price = df.iloc[-1]['close']

    if c_price > resistance:
        return {
            "side": "BUYERS",
            "signal": "BREAKOUT CONFIRMED",
            "score": 10,
            "reason": f"Price closed at ${c_price:.2f}, above resistance level (${resistance:.2f})."
        }

    recent = df.tail(window)
    buyer_score = 0
    seller_score = 0

    for idx, row in recent.iterrows():
        pressure = calculate_candle_pressure(row)
        if pressure['is_bullish'] and pressure['close_position'] > 0.6:
            buyer_score += 2
        elif pressure['is_bearish'] and pressure['close_position'] < 0.4:
            seller_score += 2

    if buyer_score > seller_score:
        return {"side": "BUYERS", "signal": "BREAKOUT IMMINENT", "score": buyer_score, "reason": "Buyers building breakout pressure."}
    elif seller_score > buyer_score:
        return {"side": "SELLERS", "signal": "RESISTANCE HOLDING", "score": seller_score, "reason": "Sellers defending resistance level."}

    return {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "Battle at resistance is balanced."}


# =====================================================================
# MAIN PIPELINE & WORKER ENTRY POINT (App.py Import Target)
# =====================================================================
def analyze_level_battle(df: pd.DataFrame, symbol: str, timeframe: str):
    """Executes range detection and battle evaluation pipeline."""
    if df.empty or len(df) < 40:
        return None, "INSUFFICIENT DATA"

    if is_actively_trending(df):
        return None, "TRENDING / NO RANGE"

    val_range = find_validated_range(df, lookback=40)
    if val_range is None:
        return None, "NO VALID RANGE"

    c_price = float(df.iloc[-1]['close'])
    support = val_range['support']
    resistance = val_range['resistance']

    if abs(c_price - support) < abs(c_price - resistance):
        battle_res = evaluate_support_battle(df, support)
    else:
        battle_res = evaluate_resistance_battle(df, resistance)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "price": c_price,
        "support": support,
        "resistance": resistance,
        "range_data": val_range,
        "battle": battle_res
    }, "SUCCESS"


def _process_symbol_tf(symbol: str, timeframe: str):
    """
    Worker function imported by app.py to fetch data and run analysis 
    for a single symbol/timeframe pair.
    """
    if is_unsupported(symbol):
        return None

    df = fetch_ohlcv(symbol, timeframe)
    if df.empty:
        return None

    result, status = analyze_level_battle(df, symbol, timeframe)
    if status == "SUCCESS" and result is not None:
        return result

    return None
