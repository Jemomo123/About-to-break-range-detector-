import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import threading
from collections import defaultdict

# ===== CONFIGURATION =====
DEBUG = True
PROXIMITY_THRESHOLD = 1.5
# =========================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

UNSUPPORTED_SYMBOLS = set()
UNSUPPORTED_LOCK = threading.Lock()
RANGE_STATE = {}
RANGE_STATE_LOCK = threading.Lock()
CACHE = {}
CACHE_LOCK = threading.Lock()
SCAN_READY = False

DEFAULT_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT", "BONKUSDT", 
    "SHIBUSDT", "USELESSUSDT", "SPACEUSDT", "MOVEUSDT", "ZECUSDT", 
    "SPXUSDT", "PEOPLEUSDT", "PENGUUSDT", "FARTCOINUSDT", "LINEAUSDT", 
    "MEMEUSDT", "PUMPUSDT", "AIXBTUSDT", "BRETTUSDT", "FOGOUSDT", 
    "GOOGLUSDT", "FLOKIUSDT", "IWMUSDT", "MOODENGUSDT", "NEARUSDT"
]


def is_unsupported(symbol):
    with UNSUPPORTED_LOCK:
        return symbol in UNSUPPORTED_SYMBOLS


def mark_unsupported(symbol):
    with UNSUPPORTED_LOCK:
        UNSUPPORTED_SYMBOLS.add(symbol)


def get_existing_range(symbol, timeframe):
    key = f"{symbol}_{timeframe}"
    with RANGE_STATE_LOCK:
        return RANGE_STATE.get(key, None)


def set_range(symbol, timeframe, range_data):
    key = f"{symbol}_{timeframe}"
    with RANGE_STATE_LOCK:
        RANGE_STATE[key] = range_data


def get_timeframe_seconds(timeframe: str) -> int:
    mapping = {"5M": 300, "15M": 900, "1H": 3600, "4H": 14400}
    return mapping.get(timeframe, 900)


def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 150):
    if is_unsupported(symbol):
        return pd.DataFrame()

    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    if not clean_sym.endswith("USDT"):
        clean_sym += "USDT"

    okx_tf_map = {"5M": "5m", "15M": "15m", "1H": "1H", "4H": "4H"}
    okx_bar = okx_tf_map.get(timeframe, "15m")

    # ---- OKX Spot ----
    okx_spot_sym = f"{clean_sym[:-4]}-USDT"
    okx_spot_url = f"https://www.okx.com/api/v5/market/candles?instId={okx_spot_sym}&bar={okx_bar}&limit={limit}"
    print(f"[OKX SPOT] {symbol} {timeframe}: {okx_spot_url}")
    try:
        resp = requests.get(okx_spot_url, headers=HEADERS, timeout=8)
        print(f"[OKX SPOT] {symbol} {timeframe} HTTP {resp.status_code}")
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
                df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                df = df.dropna(subset=['timestamp'])
                if df.empty:
                    print(f"[TIMESTAMP DEBUG] {symbol} {timeframe} all timestamps non-numeric")
                    return pd.DataFrame()
                df['timestamp_dt'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True, errors='coerce')
                valid_count = df['timestamp_dt'].notna().sum()
                invalid_count = df['timestamp_dt'].isna().sum()
                print(f"[TIMESTAMP DEBUG] {symbol} {timeframe} valid={valid_count} invalid={invalid_count}")
                df = df.dropna(subset=['timestamp_dt'])
                if df.empty:
                    print(f"[TIMESTAMP DEBUG] {symbol} {timeframe} all timestamps invalid, dropping")
                    return pd.DataFrame()
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                print(f"[OKX SPOT] {symbol} {timeframe} SUCCESS, {len(df)} candles")
                return df
            else:
                print(f"[OKX SPOT] {symbol} {timeframe} empty or code {code}")
        else:
            print(f"[OKX SPOT] {symbol} {timeframe} HTTP error")
    except Exception as e:
        print(f"[OKX SPOT] {symbol} {timeframe} exception: {e}")

    # ---- OKX Swap ----
    okx_swap_sym = f"{clean_sym[:-4]}-USDT-SWAP"
    okx_swap_url = f"https://www.okx.com/api/v5/market/candles?instId={okx_swap_sym}&bar={okx_bar}&limit={limit}"
    print(f"[OKX SWAP] {symbol} {timeframe}: {okx_swap_url}")
    try:
        resp = requests.get(okx_swap_url, headers=HEADERS, timeout=8)
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
                df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                df = df.dropna(subset=['timestamp'])
                if df.empty:
                    return pd.DataFrame()
                df['timestamp_dt'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True, errors='coerce')
                df = df.dropna(subset=['timestamp_dt'])
                if df.empty:
                    return pd.DataFrame()
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                print(f"[OKX SWAP] {symbol} {timeframe} SUCCESS, {len(df)} candles")
                return df
            else:
                print(f"[OKX SWAP] {symbol} {timeframe} empty or code {code}")
        else:
            print(f"[OKX SWAP] {symbol} {timeframe} HTTP error")
    except Exception as e:
        print(f"[OKX SWAP] {symbol} {timeframe} exception: {e}")

    # ---- MEXC Fallback ----
    mexc_tf_map = {"5M": "5m", "15M": "15m", "1H": "60m", "4H": "4h"}
    mexc_bar = mexc_tf_map.get(timeframe, "15m")
    mexc_url = f"https://api.mexc.com/api/v3/klines?symbol={clean_sym}&interval={mexc_bar}&limit={limit}"
    print(f"[MEXC] {symbol} {timeframe}: {mexc_url}")
    try:
        resp = requests.get(mexc_url, headers=HEADERS, timeout=8)
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
                    df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                    df = df.dropna(subset=['timestamp'])
                    if df.empty:
                        return pd.DataFrame()
                    df['timestamp_dt'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True, errors='coerce')
                    df = df.dropna(subset=['timestamp_dt'])
                    if df.empty:
                        return pd.DataFrame()
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)
                    print(f"[MEXC] {symbol} {timeframe} SUCCESS, {len(df)} candles")
                    return df
            else:
                print(f"[MEXC] {symbol} {timeframe} empty data")
        else:
            print(f"[MEXC] {symbol} {timeframe} HTTP error")
    except Exception as e:
        print(f"[MEXC] {symbol} {timeframe} exception: {e}")

    print(f"[WARN] All sources failed for {symbol} {timeframe}")
    return pd.DataFrame()


def get_completed_candle_index(df: pd.DataFrame, timeframe: str):
    if df.empty or 'timestamp_dt' not in df.columns:
        return len(df) - 1

    now = datetime.now(timezone.utc)
    tf_seconds = get_timeframe_seconds(timeframe)

    for i in range(len(df) - 1, -1, -1):
        open_time = df['timestamp_dt'].iloc[i]
        close_time = open_time + timedelta(seconds=tf_seconds)
        if close_time <= now:
            return i
    return len(df) - 1


def find_swings(highs, lows, lookback=5):
    swing_highs = []
    swing_lows = []
    n = len(highs)
    for i in range(lookback, n - lookback):
        if highs[i] == max(highs[i-lookback:i+lookback+1]):
            swing_highs.append((i, highs[i]))
        if lows[i] == min(lows[i-lookback:i+lookback+1]):
            swing_lows.append((i, lows[i]))
    return swing_highs, swing_lows


def cluster_prices(prices, tolerance_pct=0.7):
    if not prices:
        return []
    prices = sorted(prices)
    clusters = []
    current_cluster = [prices[0]]
    for price in prices[1:]:
        if abs(price - current_cluster[-1]) / current_cluster[-1] * 100 <= tolerance_pct:
            current_cluster.append(price)
        else:
            clusters.append({
                'level': np.mean(current_cluster),
                'count': len(current_cluster),
                'points': current_cluster
            })
            current_cluster = [price]
    clusters.append({
        'level': np.mean(current_cluster),
        'count': len(current_cluster),
        'points': current_cluster
    })
    return clusters


def calculate_acceptance_rate(closes, support, resistance, lookback=40):
    if support is None or resistance is None or support >= resistance:
        return 0.0
    n = min(len(closes), lookback)
    recent_closes = closes[-n:]
    inside_count = 0
    for price in recent_closes:
        if support <= price <= resistance:
            inside_count += 1
    return (inside_count / n) * 100.0


def find_structural_levels(highs, lows, closes, lookback=40, tolerance_pct=0.7,
                           min_touches=2, acceptance_threshold=60.0):
    n = min(len(highs), lookback)
    if n < 20:
        return None, None, 0, 0, False, 0.0, False

    recent_highs = highs[-n:]
    recent_lows = lows[-n:]
    recent_closes = closes[-n:]

    swing_highs, swing_lows = find_swings(recent_highs, recent_lows, lookback=5)

    low_prices = [price for _, price in swing_lows]
    low_clusters = cluster_prices(low_prices, tolerance_pct)

    high_prices = [price for _, price in swing_highs]
    high_clusters = cluster_prices(high_prices, tolerance_pct)

    if not low_clusters or not high_clusters:
        return None, None, 0, 0, False, 0.0, False

    low_clusters.sort(key=lambda x: (-x['count'], x['level']))
    high_clusters.sort(key=lambda x: (-x['count'], -x['level']))

    curr_price = recent_closes[-1]
    best_support = None
    best_support_touches = 0
    for cluster in low_clusters:
        if cluster['count'] >= min_touches:
            if abs(cluster['level'] - curr_price) / curr_price < 0.2:
                best_support = cluster['level']
                best_support_touches = cluster['count']
                break

    best_resistance = None
    best_resistance_touches = 0
    for cluster in high_clusters:
        if cluster['count'] >= min_touches:
            if abs(cluster['level'] - curr_price) / curr_price < 0.2:
                best_resistance = cluster['level']
                best_resistance_touches = cluster['count']
                break

    if best_support is not None and best_resistance is not None:
        if best_support > best_resistance:
            best_support, best_resistance = best_resistance, best_support
            best_support_touches, best_resistance_touches = best_resistance_touches, best_support_touches

        range_width = (best_resistance - best_support) / best_support * 100 if best_support > 0 else 100
        if 0.3 < range_width < 25:
            acceptance = calculate_acceptance_rate(closes, best_support, best_resistance, lookback)
            is_accepted = acceptance >= acceptance_threshold
            return (best_support, best_resistance,
                    best_support_touches, best_resistance_touches,
                    is_accepted, acceptance, is_accepted)
    return None, None, 0, 0, False, 0.0, False


def detect_range_simple(df, lookback=30):
    if df.empty or len(df) < lookback:
        return None, None, "N/A", False

    recent_df = df.tail(lookback).copy()
    resistance = float(recent_df['high'].max())
    support = float(recent_df['low'].min())
    range_height = resistance - support

    if range_height <= 0:
        return None, None, "N/A", False

    curr_close = float(recent_df['close'].iloc[-1])
    avg_price = (resistance + support) / 2.0
    range_pct = (range_height / avg_price) * 100.0 if avg_price > 0 else 0

    highs = recent_df['high'].values
    lows = recent_df['low'].values
    window = len(recent_df)
    first_half_high = max(highs[:window//2])
    second_half_high = max(highs[window//2:])
    first_half_low = min(lows[:window//2])
    second_half_low = min(lows[window//2:])

    pattern_type = "RECTANGLE"
    if second_half_low > first_half_low * 1.002 and abs(second_half_high - first_half_high) / avg_price < 0.005:
        pattern_type = "ASCENDING TRIANGLE"
    elif second_half_high < first_half_high * 0.998 and abs(second_half_low - first_half_low) / avg_price < 0.005:
        pattern_type = "DESCENDING TRIANGLE"
    elif range_pct < 2.0:
        pattern_type = "RECTANGLE"
    else:
        pattern_type = "CONSOLIDATION"

    return support, resistance, pattern_type, True


def calculate_candle_pressure(row):
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
    if len(volumes) < lookback:
        return 1.0
    avg_vol = np.mean(volumes[max(0, idx-lookback):idx])
    if avg_vol == 0:
        return 1.0
    return volumes[idx] / avg_vol


def evaluate_resistance_battle(df, resistance, window=8):
    if df.empty or len(df) < window:
        return {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "Insufficient data."}

    recent = df.tail(window)
    closes = df['close'].values
    volumes = df['volume'].values

    buyer_score = 0
    seller_score = 0

    for idx, row in recent.iterrows():
        pressure = calculate_candle_pressure(row)
        vol_ratio = get_volume_confirmation(volumes, idx)

        if pressure['is_bullish']:
            buyer_score += 2
            if pressure['body_ratio'] > 0.5:
                buyer_score += 1
            if pressure['close_position'] > 0.7:
                buyer_score += 2
            if pressure['upper_wick'] / (row['high'] - row['low']) < 0.2:
                buyer_score += 1
            if vol_ratio > 1.2:
                buyer_score += 2
        elif pressure['is_bearish']:
            seller_score += 2
            if pressure['body_ratio'] > 0.5:
                seller_score += 1
            if pressure['close_position'] < 0.3:
                seller_score += 2
            if pressure['upper_wick'] / (row['high'] - row['low']) > 0.3:
                seller_score += 2
            if vol_ratio > 1.2:
                seller_score += 2

        if row['high'] >= resistance * 0.995:
            buyer_score += 1
            if pressure['close_position'] < 0.5:
                seller_score += 1

    diff = buyer_score - seller_score
    threshold = 3

    if diff >= threshold:
        return {
            "side": "BUYERS",
            "signal": "BREAKOUT IMMINENT",
            "score": buyer_score,
            "reason": "Buyers are winning at resistance; breakout pressure is building."
        }
    elif -diff >= threshold:
        return {
            "side": "SELLERS",
            "signal": "RESISTANCE HOLDING",
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
    if df.empty or len(df) < window:
        return {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "Insufficient data."}

    recent = df.tail(window)
    closes = df['close'].values
    volumes = df['volume'].values

    buyer_score = 0
    seller_score = 0

    for idx, row in recent.iterrows():
        pressure = calculate_candle_pressure(row)
        vol_ratio = get_volume_confirmation(volumes, idx)

        if pressure['is_bearish']:
            seller_score += 2
            if pressure['body_ratio'] > 0.5:
                seller_score += 1
            if pressure['close_position'] < 0.3:
                seller_score += 2
            if pressure['lower_wick'] / (row['high'] - row['low']) < 0.2:
                seller_score += 1
            if vol_ratio > 1.2:
                seller_score += 2
        elif pressure['is_bullish']:
            buyer_score += 2
            if pressure['body_ratio'] > 0.5:
                buyer_score += 1
            if pressure['close_position'] > 0.7:
                buyer_score += 2
            if pressure['lower_wick'] / (row['high'] - row['low']) > 0.3:
                buyer_score += 2
            if vol_ratio > 1.2:
                buyer_score += 2

        if row['low'] <= support * 1.005:
            seller_score += 1
            if pressure['close_position'] > 0.5:
                buyer_score += 1

    diff = seller_score - buyer_score
    threshold = 3

    if diff >= threshold:
        return {
            "side": "SELLERS",
            "signal": "BREAKDOWN IMMINENT",
            "score": seller_score,
            "reason": "Sellers are winning at support; breakdown pressure is building."
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


def classify_pattern(df, support, resistance):
    if support is None or resistance is None:
        return "NO CLEAR RANGE"
    recent_df = df.tail(30)
    highs = recent_df['high'].values
    lows = recent_df['low'].values
    avg_price = (resistance + support) / 2.0
    range_height = resistance - support
    range_width_pct = (range_height / avg_price) * 100 if avg_price > 0 else 100
    window = len(recent_df)
    first_half_high = max(highs[:window//2])
    second_half_high = max(highs[window//2:])
    first_half_low = min(lows[:window//2])
    second_half_low = min(lows[window//2:])

    if second_half_low > first_half_low * 1.002 and abs(second_half_high - first_half_high) / avg_price < 0.005:
        return "ASCENDING TRIANGLE"
    elif second_half_high < first_half_high * 0.998 and abs(second_half_low - first_half_low) / avg_price < 0.005:
        return "DESCENDING TRIANGLE"
    elif range_width_pct < 2.0:
        return "RECTANGLE"
    else:
        return "CONSOLIDATION"


def analyze_level_battle(df: pd.DataFrame, symbol: str, timeframe: str):
    print(f"[RANGE ENTRY] {symbol} {timeframe} rows={len(df)}")

    if df.empty or len(df) < 30:
        return None, "INSUFFICIENT DATA"

    completed_idx = get_completed_candle_index(df, timeframe)
    if completed_idx < 0 or completed_idx >= len(df):
        completed_idx = len(df) - 1

    selected_candle_time = df['timestamp_dt'].iloc[completed_idx]
    curr_close = float(df['close'].iloc[completed_idx])
    last_row = df.iloc[completed_idx]

    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values

    support_struct, resistance_struct, sup_touches, res_touches, is_accepted, acceptance_rate, _ = find_structural_levels(
        highs=highs, lows=lows, closes=closes,
        lookback=40, tolerance_pct=0.7, min_touches=2, acceptance_threshold=60.0
    )

    candidate = None
    source = None
    if support_struct is not None and resistance_struct is not None and is_accepted:
        range_width = (resistance_struct - support_struct) / support_struct * 100 if support_struct > 0 else 0
        candidate = {
            'support': support_struct,
            'resistance': resistance_struct,
            'support_touches': sup_touches,
            'resistance_touches': res_touches,
            'range_status': 'STRUCTURAL',
            'range_width_percent': range_width,
            'pattern_type': classify_pattern(df, support_struct, resistance_struct),
            'acceptance_rate': acceptance_rate,
        }
        source = "STRUCTURAL"
    else:
        support_simple, resistance_simple, pattern_type_simple, valid = detect_range_simple(df, lookback=30)
        if valid and support_simple is not None and resistance_simple is not None:
            range_width = (resistance_simple - support_simple) / support_simple * 100 if support_simple > 0 else 0
            acceptance = calculate_acceptance_rate(closes, support_simple, resistance_simple, lookback=30)
            candidate = {
                'support': support_simple,
                'resistance': resistance_simple,
                'support_touches': 1,
                'resistance_touches': 1,
                'range_status': 'PROVISIONAL',
                'range_width_percent': range_width,
                'pattern_type': pattern_type_simple,
                'acceptance_rate': acceptance,
            }
            source = "PROVISIONAL"
        else:
            candidate = None
            source = "NONE"

    print(f"[RANGE SOURCE] {symbol} {timeframe} = {source}")

    is_valid = False
    if candidate is not None:
        support_val = candidate['support']
        resistance_val = candidate['resistance']
        if support_val > 0 and resistance_val > 0 and resistance_val > support_val:
            range_width_pct = ((resistance_val - support_val) / support_val) * 100
            if range_width_pct > 0.000001:
                is_valid = True
            else:
                print(f"[RANGE INVALID] {symbol} {timeframe} width too small: {range_width_pct:.8f}%")
        else:
            print(f"[RANGE INVALID] {symbol} {timeframe} non-positive or inverted range: support={support_val:.8f}, resistance={resistance_val:.8f}")

    if not is_valid:
        candidate = None
        source = "INVALID_RANGE"

    existing = get_existing_range(symbol, timeframe)
    active_support = 0.0
    active_resistance = 0.0
    active_status = "NO VALID RANGE"
    active_pattern = "NO CLEAR RANGE"
    invalidation_direction = "NONE"
    invalidation_price = 0.0
    previous_support = 0.0
    previous_resistance = 0.0

    if existing is None:
        if candidate is not None:
            candidate['range_start_index'] = completed_idx
            candidate['range_age'] = 0
            candidate['last_processed_candle_index'] = completed_idx
            candidate['consecutive_outside_closes'] = 0
            candidate['invalidation_info'] = None
            set_range(symbol, timeframe, candidate)
            active_support = candidate['support']
            active_resistance = candidate['resistance']
            active_status = candidate['range_status']
            active_pattern = candidate['pattern_type']
        else:
            active_support = 0.0
            active_resistance = 0.0
            active_status = "NO VALID RANGE"
            active_pattern = "NO CLEAR RANGE"
    else:
        support = existing['support']
        resistance = existing['resistance']
        range_status = existing.get('range_status', 'STRUCTURAL')
        invalidation_info = existing.get('invalidation_info')

        if range_status == 'INVALIDATED':
            invalidation_candle = invalidation_info.get('candle_index', 0) if invalidation_info else 0
            if completed_idx > invalidation_candle + 1:
                if candidate is not None and candidate.get('range_status') == 'STRUCTURAL':
                    candidate['range_start_index'] = completed_idx
                    candidate['range_age'] = 0
                    candidate['last_processed_candle_index'] = completed_idx
                    candidate['consecutive_outside_closes'] = 0
                    candidate['invalidation_info'] = None
                    set_range(symbol, timeframe, candidate)
                    active_support = candidate['support']
                    active_resistance = candidate['resistance']
                    active_status = candidate['range_status']
                    active_pattern = candidate['pattern_type']
                else:
                    active_support = 0.0
                    active_resistance = 0.0
                    active_status = "INVALIDATED"
                    active_pattern = "NO CLEAR RANGE"
            else:
                active_support = 0.0
                active_resistance = 0.0
                active_status = "INVALIDATED"
                active_pattern = "NO CLEAR RANGE"
        else:
            if support <= curr_close <= resistance:
                active_support = support
                active_resistance = resistance
                active_status = range_status
                active_pattern = existing.get('pattern_type', 'CONSOLIDATION')
                last_processed = existing.get('last_processed_candle_index', -1)
                if completed_idx != last_processed:
                    existing['range_age'] = existing.get('range_age', 0) + 1
                    existing['last_processed_candle_index'] = completed_idx
                existing['range_last_validated'] = completed_idx
                set_range(symbol, timeframe, existing)
            else:
                invalidation_direction = "UPSIDE" if curr_close > resistance else "DOWNSIDE"
                invalidation_price = curr_close
                previous_support = support
                previous_resistance = resistance

                existing['range_status'] = "INVALIDATED"
                existing['invalidation_info'] = {
                    'direction': invalidation_direction,
                    'price': invalidation_price,
                    'candle_index': completed_idx,
                    'time': datetime.now(timezone.utc).isoformat()
                }
                set_range(symbol, timeframe, existing)

                active_support = 0.0
                active_resistance = 0.0
                active_status = "INVALIDATED"
                active_pattern = "NO CLEAR RANGE"

    penetration_type = "NONE"
    penetration_explanation = ""
    if active_status != "INVALIDATED" and active_support > 0 and active_resistance > 0:
        if last_row['low'] < active_support and last_row['close'] >= active_support:
            penetration_type = "SUPPORT PENETRATION"
            penetration_explanation = f"Support penetrated: candle low ({last_row['low']:.8f}) traded below active support ({active_support:.8f}) but closed back above it."
        elif last_row['high'] > active_resistance and last_row['close'] <= active_resistance:
            penetration_type = "RESISTANCE PENETRATION"
            penetration_explanation = f"Resistance penetrated: candle high ({last_row['high']:.8f}) traded above active resistance ({active_resistance:.8f}) but closed back below it."

    if active_support > 0 and active_resistance > 0:
        dist_to_res = (active_resistance - curr_close) / curr_close * 100
        dist_to_sup = (curr_close - active_support) / curr_close * 100
        threshold = PROXIMITY_THRESHOLD

        if dist_to_res < dist_to_sup and dist_to_res < threshold:
            level_type = "RESISTANCE"
            level_price = active_resistance
            distance = dist_to_res
            result = evaluate_resistance_battle(df, active_resistance)
        elif dist_to_sup < threshold:
            level_type = "SUPPORT"
            level_price = active_support
            distance = dist_to_sup
            result = evaluate_support_battle(df, active_support)
        else:
            level_type = "NONE"
            level_price = curr_close
            distance = 0.0
            result = {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "Price not near boundary."}
    else:
        level_type = "NONE"
        level_price = curr_close
        distance = 0.0
        result = {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "No active range."}

    range_width_pct = ((active_resistance - active_support) / active_support * 100) if active_support > 0 and active_resistance > 0 else 0

    print(f"[RANGE DECISION] {symbol} {timeframe}")
    print(f"  source={source if source else 'NONE'}")
    print(f"  selected_candle={selected_candle_time.isoformat()}")
    print(f"  range_low={active_support:.8f}")
    print(f"  range_high={active_resistance:.8f}")
    print(f"  current_close={curr_close:.8f}")
    print(f"  width_pct={range_width_pct:.4f}%")
    print(f"  status={active_status}")
    print(f"  pattern={active_pattern.replace(' ', '_') if active_pattern else 'NONE'}")
    print(f"  penetration={penetration_type}")
    if penetration_explanation:
        print(f"  penetration_detail={penetration_explanation}")
    if invalidation_direction != "NONE":
        print(f"  invalidation={invalidation_direction} at {invalidation_price:.8f}")
    print("---")

    print(f"[FINAL SIGNAL] {symbol} {timeframe}")
    print(f"  range_low={active_support:.8f}")
    print(f"  range_high={active_resistance:.8f}")
    print(f"  current_close={curr_close:.8f}")
    print(f"  support={active_support:.8f}")
    print(f"  resistance={active_resistance:.8f}")
    print(f"  penetration={penetration_type}")
    print(f"  battle={result['side']}")
    print(f"  decision={result['signal']}")
    print(f"  alert={result['reason']}")
    print("---")

    last_updated = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    clean_display = symbol.replace("-", "").replace("_", "").upper()

    result_dict = {
        "symbol": clean_display,
        "timeframe": timeframe,
        "curr_close": round(curr_close, 6),
        "level_type": level_type,
        "level_price": round(level_price, 6),
        "distance_to_level": round(distance, 2),
        "winner": result["side"],
        "signal": result["signal"],
        "explanation": result["reason"],
        "support": round(active_support, 6) if active_support else 0.0,
        "resistance": round(active_resistance, 6) if active_resistance else 0.0,
        "pattern_type": active_pattern,
        "range_status": active_status,
        "last_updated": last_updated,
        "penetration_type": penetration_type,
        "penetration_explanation": penetration_explanation,
        "previous_support": round(previous_support, 6) if previous_support else 0.0,
        "previous_resistance": round(previous_resistance, 6) if previous_resistance else 0.0,
        "invalidation_direction": invalidation_direction,
        "invalidation_price": round(invalidation_price, 6) if invalidation_price else 0.0,
        "invalidation_time": existing.get('invalidation_info', {}).get('time', '') if existing and existing.get('invalidation_info') else ''
    }

    print(f"[API RESULT] {symbol} {timeframe}")
    print(f"  price={result_dict['curr_close']:.6f}")
    print(f"  support={result_dict['support']:.6f}")
    print(f"  resistance={result_dict['resistance']:.6f}")
    print(f"  decision={result_dict['signal']}")
    print(f"  alert={result_dict['explanation']}")
    print(f"  range_low={result_dict['support']:.6f}")
    print(f"  range_high={result_dict['resistance']:.6f}")
    print(f"  range_status={result_dict['range_status']}")
    print(f"  range_source={source if source else 'NONE'}")
    print("---")

    return result_dict, None


def _process_symbol_tf(symbol: str, tf: str):
    if is_unsupported(symbol):
        return None, "UNSUPPORTED"
    df = fetch_ohlcv(symbol, tf)
    if df.empty:
        return None, "DATA UNAVAILABLE"
    return analyze_level_battle(df, symbol, tf)


def update_cache_job():
    global SCAN_READY
    print(">>> BACKGROUND SCANNER STARTED")
    first_cycle = True
    while True:
        try:
            # ---- 15M SCANNED FIRST ----
            for tf in ["15M", "5M", "1H", "4H"]:
                print(f">>> Scanning {tf}...")
                tasks = [sym for sym in DEFAULT_WATCHLIST]
                with ThreadPoolExecutor(max_workers=10) as executor:
                    future_map = {executor.submit(_process_symbol_tf, sym, tf): sym for sym in tasks}
                    for future in as_completed(future_map):
                        sym = future_map[future]
                        res = future.result()
                        if res:
                            with CACHE_LOCK:
                                CACHE[f"{sym}_{tf}"] = res
                                print(f"[CACHE] Stored {sym} {tf}")
                print(f">>> Completed {tf}")
                if first_cycle and tf == "15M":
                    SCAN_READY = True
                    print(">>> SCAN_READY = True (15M data ready)")
                time.sleep(1)
            first_cycle = False
            print(">>> Cycle complete. Sleeping 15s...")
            time.sleep(15)
        except Exception as e:
            print(f"!!! Worker exception: {e}")
            time.sleep(5)
