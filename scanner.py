import threading
import numpy as np
import pandas as pd
import requests

# ===== CONFIGURATION =====
DEBUG = True
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

UNSUPPORTED_SYMBOLS = set()
UNSUPPORTED_LOCK = threading.Lock()

RANGE_STATE = {}
RANGE_STATE_LOCK = threading.Lock()


def is_unsupported(symbol: str) -> bool:
    with UNSUPPORTED_LOCK:
        return symbol in UNSUPPORTED_SYMBOLS


def mark_unsupported(symbol: str):
    with UNSUPPORTED_LOCK:
        UNSUPPORTED_SYMBOLS.add(symbol)


def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
    """Fetches OHLCV data with strict 3s timeouts and fallback safety."""
    if is_unsupported(symbol):
        return pd.DataFrame()

    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    if not clean_sym.endswith("USDT"):
        clean_sym += "USDT"

    # 1. Primary Attempt: OKX
    okx_sym = f"{clean_sym[:-4]}-USDT"
    okx_tf_map = {"5M": "5m", "15M": "15m", "1H": "1H", "4H": "4H"}
    okx_bar = okx_tf_map.get(timeframe.upper(), "15m")
    okx_url = f"https://www.okx.com/api/v5/market/candles?instId={okx_sym}&bar={okx_bar}&limit={limit}"

    try:
        resp = requests.get(okx_url, headers=HEADERS, timeout=3)
        if resp.status_code == 200:
            res_json = resp.json()
            if res_json.get("code") == "0" and res_json.get("data"):
                df = pd.DataFrame(res_json["data"], columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'volCcy', 'volCcyQuote', 'confirm'
                ])
                df = df.iloc[::-1].reset_index(drop=True)
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                return df
            elif res_json.get("code") == "51001":
                mark_unsupported(symbol)
                return pd.DataFrame()
    except Exception:
        pass

    # 2. Failover Attempt: MEXC
    mexc_sym = clean_sym
    mexc_tf_map = {"5M": "5m", "15M": "15m", "1H": "1h", "4H": "4h"}
    mexc_bar = mexc_tf_map.get(timeframe.upper(), "15m")
    mexc_url = f"https://api.mexc.com/api/v3/klines?symbol={mexc_sym}&interval={mexc_bar}&limit={limit}"

    try:
        resp = requests.get(mexc_url, headers=HEADERS, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                parsed = [row[:6] for row in data if len(row) >= 6]
                if parsed:
                    df = pd.DataFrame(parsed, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)
                    return df
    except Exception:
        pass

    return pd.DataFrame()


def is_actively_trending(df: pd.DataFrame, sma_fast=20, sma_slow=50) -> bool:
    """Safe trend filter that doesn't crash on short DataFrames."""
    try:
        if df.empty or len(df) < sma_slow:
            return False

        closes = df['close']
        sma20 = closes.rolling(sma_fast).mean().dropna().values
        sma50 = closes.rolling(sma_slow).mean().dropna().values

        if len(sma20) < 5 or len(sma50) < 1:
            return False

        sma20_slope = (sma20[-1] - sma20[-5]) / sma20[-5] * 100.0 if sma20[-5] > 0 else 0
        c_price = closes.iloc[-1]

        is_markdown = (sma20_slope < -0.3) and (c_price < sma20[-1]) and (sma20[-1] < sma50[-1])
        is_markup = (sma20_slope > 0.3) and (c_price > sma20[-1]) and (sma20[-1] > sma50[-1])

        return is_markdown or is_markup
    except Exception:
        return False


def find_validated_range(df: pd.DataFrame, lookback=40):
    """Detects ranges safely without index errors."""
    try:
        if df.empty or len(df) < lookback:
            return None

        recent_df = df.tail(lookback).copy()
        highs = recent_df['high'].values
        lows = recent_df['low'].values
        closes = recent_df['close'].values

        p_high = float(np.percentile(highs, 95))
        p_low = float(np.percentile(lows, 5))

        v_high = p_high if np.sum(highs > p_high) <= 1 else float(np.max(highs))
        v_low = p_low if np.sum(lows < p_low) <= 1 else float(np.min(lows))

        r_height = v_high - v_low
        if r_height <= 0 or v_low <= 0:
            return None

        range_width_pct = (r_height / v_low) * 100.0
        if range_width_pct < 0.3 or range_width_pct > 20.0:
            return None

        # Time-separated touch verification
        touch_tolerance = r_height * 0.12
        upper_touches, lower_touches = 0, 0
        last_upper_idx, last_lower_idx = -10, -10

        for i in range(len(highs)):
            if (v_high - highs[i]) <= touch_tolerance and (i - last_upper_idx >= 3):
                upper_touches += 1
                last_upper_idx = i
            if (lows[i] - v_low) <= touch_tolerance and (i - last_lower_idx >= 3):
                lower_touches += 1
                last_lower_idx = i

        if upper_touches < 2 or lower_touches < 2:
            return None

        c_price = closes[-1]
        if c_price < v_low or c_price > v_high:
            return None

        return {
            'support': v_low,
            'resistance': v_high,
            'support_touches': lower_touches,
            'resistance_touches': upper_touches,
            'range_status': 'VALIDATED',
            'range_width_percent': round(range_width_pct, 2)
        }
    except Exception:
        return None


def evaluate_support_battle(df: pd.DataFrame, support: float):
    try:
        if df.empty or support <= 0:
            return {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "No data"}

        c_price = float(df.iloc[-1]['close'])
        if c_price < support:
            return {"side": "SELLERS", "signal": "BREAKDOWN CONFIRMED", "score": 10, "reason": "Price closed below support."}

        recent = df.tail(6)
        buyer_score, seller_score = 0, 0

        for _, row in recent.iterrows():
            c_range = row['high'] - row['low']
            if c_range == 0:
                continue
            close_pos = (row['close'] - row['low']) / c_range
            if row['close'] > row['open'] and close_pos > 0.6:
                buyer_score += 2
            elif row['close'] < row['open'] and close_pos < 0.4:
                seller_score += 2

        if seller_score > buyer_score:
            return {"side": "SELLERS", "signal": "BREAKDOWN IMMINENT", "score": seller_score, "reason": "Selling pressure at support."}
        elif buyer_score > seller_score:
            return {"side": "BUYERS", "signal": "SUPPORT HOLDING", "score": buyer_score, "reason": "Buyers defending support."}

        return {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "Balanced at support."}
    except Exception:
        return {"side": "NEUTRAL", "signal": "ERROR", "score": 0, "reason": "Evaluation failed"}


def evaluate_resistance_battle(df: pd.DataFrame, resistance: float):
    try:
        if df.empty or resistance <= 0:
            return {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "No data"}

        c_price = float(df.iloc[-1]['close'])
        if c_price > resistance:
            return {"side": "BUYERS", "signal": "BREAKOUT CONFIRMED", "score": 10, "reason": "Price closed above resistance."}

        recent = df.tail(6)
        buyer_score, seller_score = 0, 0

        for _, row in recent.iterrows():
            c_range = row['high'] - row['low']
            if c_range == 0:
                continue
            close_pos = (row['close'] - row['low']) / c_range
            if row['close'] > row['open'] and close_pos > 0.6:
                buyer_score += 2
            elif row['close'] < row['open'] and close_pos < 0.4:
                seller_score += 2

        if buyer_score > seller_score:
            return {"side": "BUYERS", "signal": "BREAKOUT IMMINENT", "score": buyer_score, "reason": "Buying pressure at resistance."}
        elif seller_score > buyer_score:
            return {"side": "SELLERS", "signal": "RESISTANCE HOLDING", "score": seller_score, "reason": "Sellers defending resistance."}

        return {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "Balanced at resistance."}
    except Exception:
        return {"side": "NEUTRAL", "signal": "ERROR", "score": 0, "reason": "Evaluation failed"}


def analyze_level_battle(df: pd.DataFrame, symbol: str, timeframe: str):
    """Executes main scanner logic safely."""
    try:
        if df.empty or len(df) < 30:
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
    except Exception:
        return None, "ERROR"


def _process_symbol_tf(symbol: str, timeframe: str):
    """
    Fail-safe worker function. 
    Guarantees returning a (result, status) tuple to prevent unpack errors in app.py.
    """
    try:
        if is_unsupported(symbol):
            return None, "UNSUPPORTED"

        df = fetch_ohlcv(symbol, timeframe)
        if df.empty:
            return None, "FETCH_FAILED"

        result, status = analyze_level_battle(df, symbol, timeframe)
        return result, status
    except Exception as e:
        return None, f"EXCEPTION: {str(e)}"
