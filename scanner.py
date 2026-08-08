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
    support = np.min(lows[-lookback:])
    resistance = np.max(highs[-lookback:])
    return support, resistance


def calculate_candle_pressure(row):
    """Extract pressure metrics from a single candle row."""
    body = abs(row['close'] - row['open'])
    candle_range = row['high'] - row['low']
    if candle_range == 0:
        return {
            'body_ratio': 0,
            'close_position': 0.5,
            'upper_wick': 0,
            'lower_wick': 0,
            'is_bullish': row['close'] > row['open'],
            'is_bearish': row['close'] < row['open']
        }
    body_ratio = body / candle_range
    close_position = (row['close'] - row['low']) / candle_range
    upper_wick = row['high'] - max(row['open'], row['close'])
    lower_wick = min(row['open'], row['close']) - row['low']
    return {
        'body_ratio': body_ratio,
        'close_position': close_position,
        'upper_wick': upper_wick,
        'lower_wick': lower_wick,
        'is_bullish': row['close'] > row['open'],
        'is_bearish': row['close'] < row['open']
    }


def get_volume_confirmation(volumes, idx, lookback=20):
    """Volume relative to recent average."""
    if len(volumes) < lookback:
        return 1.0
    avg_vol = np.mean(volumes[max(0, idx-lookback):idx])
    if avg_vol == 0:
        return 1.0
    return volumes[idx] / avg_vol


def evaluate_resistance_battle(df, resistance, window=8):
    """
    Score buyers vs sellers at a resistance level using recent candles.
    Returns dict with side, signal, score, reason.
    """
    if df.empty or len(df) < window:
        return {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "Insufficient data."}

    # Use the last `window` candles (they should be near resistance due to proximity check)
    recent = df.tail(window)
    closes = df['close'].values
    volumes = df['volume'].values

    buyer_score = 0
    seller_score = 0
    total_weight = 0

    for idx, row in recent.iterrows():
        pressure = calculate_candle_pressure(row)
        vol_ratio = get_volume_confirmation(volumes, idx)

        # Base points for bullish/bearish pressure
        if pressure['is_bullish']:
            # Bullish candle: buyers are pushing up
            buyer_score += 2
            # Strong body (body > 0.5 of range) adds
            if pressure['body_ratio'] > 0.5:
                buyer_score += 1
            # Close near high (close_position > 0.7)
            if pressure['close_position'] > 0.7:
                buyer_score += 2
            # Weak upper wick (small rejection) – buyers absorbing
            if pressure['upper_wick'] / (row['high'] - row['low']) < 0.2:
                buyer_score += 1
            # Volume confirmation: high volume on bullish candle
            if vol_ratio > 1.2:
                buyer_score += 2
        elif pressure['is_bearish']:
            # Bearish candle: sellers pushing down
            seller_score += 2
            # Strong body
            if pressure['body_ratio'] > 0.5:
                seller_score += 1
            # Close near low (close_position < 0.3)
            if pressure['close_position'] < 0.3:
                seller_score += 2
            # Strong upper wick (rejection at resistance)
            if pressure['upper_wick'] / (row['high'] - row['low']) > 0.3:
                seller_score += 2
            # Volume confirmation
            if vol_ratio > 1.2:
                seller_score += 2

        # Additional: repeated tests of resistance (price high near resistance)
        if row['high'] >= resistance * 0.995:
            buyer_score += 1  # buyers testing
            # If rejected (close far from high), sellers get extra
            if pressure['close_position'] < 0.5:
                seller_score += 1

        total_weight += 1

    # Normalize scores? We'll keep raw totals and compare.
    # Threshold: we require a minimum score difference to declare a winner
    diff = buyer_score - seller_score
    threshold = 3  # minimum margin

    if diff >= threshold:
        return {
            "side": "BUYERS",
            "signal": "BREAKOUT IMMINENT",
            "score": buyer_score,
            "reason": "Buyers are absorbing selling pressure near resistance."
        }
    elif -diff >= threshold:
        return {
            "side": "SELLERS",
            "signal": "RESISTANCE REJECTING",
            "score": seller_score,
            "reason": "Sellers are defending resistance."
        }
    else:
        return {
            "side": "NEUTRAL",
            "signal": "NO CLEAR SIGNAL",
            "score": max(buyer_score, seller_score),
            "reason": "Battle at resistance is evenly matched."
        }


def evaluate_support_battle(df, support, window=8):
    """
    Score sellers vs buyers at a support level using recent candles.
    Returns dict with side, signal, score, reason.
    """
    if df.empty or len(df) < window:
        return {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "Insufficient data."}

    recent = df.tail(window)
    closes = df['close'].values
    volumes = df['volume'].values

    buyer_score = 0
    seller_score = 0
    total_weight = 0

    for idx, row in recent.iterrows():
        pressure = calculate_candle_pressure(row)
        vol_ratio = get_volume_confirmation(volumes, idx)

        if pressure['is_bearish']:
            # Bearish candle: sellers pushing down
            seller_score += 2
            if pressure['body_ratio'] > 0.5:
                seller_score += 1
            if pressure['close_position'] < 0.3:
                seller_score += 2
            # Weak lower wick – sellers overpowering
            if pressure['lower_wick'] / (row['high'] - row['low']) < 0.2:
                seller_score += 1
            if vol_ratio > 1.2:
                seller_score += 2
        elif pressure['is_bullish']:
            # Bullish candle: buyers defending
            buyer_score += 2
            if pressure['body_ratio'] > 0.5:
                buyer_score += 1
            if pressure['close_position'] > 0.7:
                buyer_score += 2
            # Strong lower wick – rejection of support
            if pressure['lower_wick'] / (row['high'] - row['low']) > 0.3:
                buyer_score += 2
            if vol_ratio > 1.2:
                buyer_score += 2

        # Repeated tests of support (price low near support)
        if row['low'] <= support * 1.005:
            seller_score += 1  # sellers attacking
            if pressure['close_position'] > 0.5:
                buyer_score += 1  # buyers rejected the attack

        total_weight += 1

    diff = seller_score - buyer_score
    threshold = 3

    if diff >= threshold:
        return {
            "side": "SELLERS",
            "signal": "BREAKDOWN IMMINENT",
            "score": seller_score,
            "reason": "Sellers are overpowering support with bearish closes."
        }
    elif -diff >= threshold:
        return {
            "side": "BUYERS",
            "signal": "SUPPORT HOLDING",
            "score": buyer_score,
            "reason": "Buyers are defending support."
        }
    else:
        return {
            "side": "NEUTRAL",
            "signal": "NO CLEAR SIGNAL",
            "score": max(buyer_score, seller_score),
            "reason": "Battle at support is evenly matched."
        }


def analyze_level_battle(df: pd.DataFrame, symbol: str, timeframe: str):
    """
    Determines who is winning at the nearest support/resistance level.
    Uses the new scoring logic.
    """
    if df.empty or len(df) < 30:
        return None, "INSUFFICIENT DATA"

    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    curr_close = float(closes[-1])
    lookback = min(30, len(df) - 1)

    support, resistance = detect_levels(highs, lows, closes, lookback)
    range_height = resistance - support
    if range_height <= 0:
        return None, "INVALID RANGE"

    dist_to_res = (resistance - curr_close) / curr_close * 100
    dist_to_sup = (curr_close - support) / curr_close * 100
    threshold = 5.0  # 5% proximity

    if dist_to_res < dist_to_sup and dist_to_res < threshold:
        level_type = "RESISTANCE"
        level_price = resistance
        distance = dist_to_res
        result = evaluate_resistance_battle(df, resistance)
    elif dist_to_sup < threshold:
        level_type = "SUPPORT"
        level_price = support
        distance = dist_to_sup
        result = evaluate_support_battle(df, support)
    else:
        level_type = "NONE"
        level_price = curr_close
        distance = 0.0
        result = {
            "side": "NEUTRAL",
            "signal": "NO CLEAR SIGNAL",
            "score": 0,
            "reason": "Price is not near a key support or resistance level."
        }

    last_updated = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    clean_display = symbol.replace("-", "").replace("_", "").upper()

    return {
        "symbol": clean_display,
        "timeframe": timeframe,
        "curr_close": round(curr_close, 6),
        "level_type": level_type,
        "level_price": round(level_price, 6),
        "distance_to_level": round(distance, 2),
        "winner": result["side"],
        "signal": result["signal"],
        "explanation": result["reason"],
        "support": round(support, 6),
        "resistance": round(resistance, 6),
        "last_updated": last_updated
    }, None


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

    # Sort: BUYERS/SELLERS first, then NEUTRAL
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
