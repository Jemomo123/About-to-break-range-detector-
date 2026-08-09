import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import threading
from collections import defaultdict

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


def find_swings(highs, lows, lookback=5):
    """
    Identify swing highs and swing lows using local extrema.
    Returns lists of (index, price) for swings.
    """
    swing_highs = []
    swing_lows = []
    n = len(highs)
    for i in range(lookback, n - lookback):
        # Swing high: higher than both sides
        if highs[i] == max(highs[i-lookback:i+lookback+1]):
            swing_highs.append((i, highs[i]))
        # Swing low: lower than both sides
        if lows[i] == min(lows[i-lookback:i+lookback+1]):
            swing_lows.append((i, lows[i]))
    return swing_highs, swing_lows


def cluster_prices(prices, tolerance_pct=0.5):
    """
    Cluster price points that are within tolerance_pct % of each other.
    Returns list of clusters, each cluster is a dict with:
        - 'level': average price of cluster
        - 'count': number of points in cluster
        - 'points': list of prices
    """
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


def find_structural_levels(highs, lows, closes, lookback=40, tolerance_pct=0.7, min_touches=2):
    """
    Detect structural support and resistance using swing points and clustering.
    Returns (support, resistance, support_touches, resistance_touches, is_valid)
    """
    # Use a longer lookback for structural analysis
    n = min(len(highs), lookback)
    if n < 20:
        return None, None, 0, 0, False

    recent_highs = highs[-n:]
    recent_lows = lows[-n:]
    recent_closes = closes[-n:]

    # Find swing points
    swing_highs, swing_lows = find_swings(recent_highs, recent_lows, lookback=5)

    # Cluster the swing lows (support candidates)
    low_prices = [price for _, price in swing_lows]
    low_clusters = cluster_prices(low_prices, tolerance_pct)

    # Cluster the swing highs (resistance candidates)
    high_prices = [price for _, price in swing_highs]
    high_clusters = cluster_prices(high_prices, tolerance_pct)

    # Select the best support: cluster with most touches (count) and at the lowest price region?
    # For support, we want a cluster that is not too low (recent) and has multiple touches.
    # We'll choose the cluster with the highest count, but ensure it's not an extreme outlier.
    if not low_clusters or not high_clusters:
        return None, None, 0, 0, False

    # Sort clusters by count descending, then by level
    low_clusters.sort(key=lambda x: (-x['count'], x['level']))
    high_clusters.sort(key=lambda x: (-x['count'], -x['level']))

    # Pick the best support: cluster with highest count, and level not too far from current price
    curr_price = recent_closes[-1]
    best_support = None
    best_support_touches = 0
    for cluster in low_clusters:
        if cluster['count'] >= min_touches:
            # Check if level is within reasonable range of current price (e.g., not 50% away)
            if abs(cluster['level'] - curr_price) / curr_price < 0.2:  # within 20%
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

    # If we have both support and resistance, ensure they are correctly ordered
    if best_support is not None and best_resistance is not None:
        if best_support > best_resistance:
            # swap if inverted
            best_support, best_resistance = best_resistance, best_support
            best_support_touches, best_resistance_touches = best_resistance_touches, best_support_touches

        # Validate range width: between 0.5% and 20%
        range_width = (best_resistance - best_support) / best_support * 100 if best_support > 0 else 100
        if 0.5 < range_width < 20:
            return best_support, best_resistance, best_support_touches, best_resistance_touches, True
        else:
            return best_support, best_resistance, best_support_touches, best_resistance_touches, False

    return None, None, 0, 0, False


def detect_structural_range(df, lookback=40, tolerance_pct=0.7, min_touches=2):
    """
    Main function to detect a structural range from a DataFrame.
    Returns (support, resistance, support_touches, resistance_touches, is_valid)
    """
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    return find_structural_levels(highs, lows, closes, lookback, tolerance_pct, min_touches)


# ---- The rest: battle evaluation, volume, etc. are unchanged ----
# I'll include them here for completeness, but they are the same as before.

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


def analyze_level_battle(df: pd.DataFrame, symbol: str, timeframe: str):
    if df.empty or len(df) < 30:
        return None, "INSUFFICIENT DATA"

    # ---- STRUCTURAL RANGE DETECTION ----
    support, resistance, sup_touches, res_touches, is_valid = detect_structural_range(
        df, lookback=40, tolerance_pct=0.7, min_touches=2
    )

    if not is_valid or support is None or resistance is None:
        # Fallback: if structural detection fails, use simple min/max (but we want to avoid that)
        # Instead, return NEUTRAL with a message
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "curr_close": round(df['close'].iloc[-1], 6),
            "level_type": "NONE",
            "level_price": 0,
            "distance_to_level": 0,
            "winner": "NEUTRAL",
            "signal": "NO CLEAR SIGNAL",
            "explanation": "No stable structural range detected.",
            "support": 0,
            "resistance": 0,
            "last_updated": datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        }, "NO_STRUCTURAL_RANGE"

    curr_close = df['close'].iloc[-1]
    dist_to_res = (resistance - curr_close) / curr_close * 100
    dist_to_sup = (curr_close - support) / curr_close * 100
    threshold = 5.0

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
            "reason": "Price is not near a key structural support or resistance level."
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
