import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import threading

# ===== CONFIGURATION =====
DEBUG = False  # Set to True for detailed scoring logs
# =========================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Unsupported symbol cache (thread-safe)
UNSUPPORTED_SYMBOLS = set()
UNSUPPORTED_LOCK = threading.Lock()

def is_unsupported(symbol):
    with UNSUPPORTED_LOCK:
        return symbol in UNSUPPORTED_SYMBOLS

def mark_unsupported(symbol):
    with UNSUPPORTED_LOCK:
        UNSUPPORTED_SYMBOLS.add(symbol)
        print(f"[UNSUPPORTED] {symbol} added to unsupported cache")


def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 150):
    """
    PRIMARY: OKX REST API
    FALLBACK: MEXC REST API
    """
    if is_unsupported(symbol):
        print(f"[SKIP] {symbol} {timeframe} - unsupported")
        return pd.DataFrame()

    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    if not clean_sym.endswith("USDT"):
        clean_sym += "USDT"

    okx_sym = f"{clean_sym[:-4]}-USDT"
    okx_tf_map = {"5M": "5m", "15M": "15m", "1H": "1H", "4H": "4H"}
    okx_bar = okx_tf_map.get(timeframe, "15m")

    # 1. OKX
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
                print(f"[OKX][{symbol}][{timeframe}] ✓ Downloaded {len(df)} candles")
                return df
            elif code == "51001":
                print(f"[OKX][{symbol}] Unsupported instrument (51001)")
                mark_unsupported(symbol)
                return pd.DataFrame()
            else:
                print(f"[OKX][{symbol}] Empty data. Code: {code}")
        else:
            print(f"[OKX][{symbol}] HTTP {resp.status_code}")
    except Exception as e:
        print(f"[OKX][{symbol}] Exception: {e}")

    # 2. MEXC fallback
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
                    print(f"[MEXC][{symbol}][{timeframe}] ✓ Downloaded {len(df)} candles")
                    return df
                else:
                    print(f"[MEXC][{symbol}] No valid rows")
            else:
                print(f"[MEXC][{symbol}] Empty data")
        else:
            print(f"[MEXC][{symbol}] HTTP {resp.status_code}")
    except Exception as e:
        print(f"[MEXC][{symbol}] Exception: {e}")

    print(f"[{symbol}][{timeframe}] ✗ FAILED")
    return pd.DataFrame()


def detect_support_resistance(highs, lows, closes, lookback=30):
    support = np.min(lows[-lookback:])
    resistance = np.max(highs[-lookback:])
    tolerance = 0.005
    support_touches = 0
    resistance_touches = 0
    for i in range(len(closes) - lookback, len(closes)):
        price = closes[i]
        if abs(price - support) / support < tolerance:
            support_touches += 1
        if abs(price - resistance) / resistance < tolerance:
            resistance_touches += 1
    return support, resistance, support_touches, resistance_touches


def analyze_range_structure(df: pd.DataFrame, symbol: str, timeframe: str):
    if df.empty or len(df) < 30:
        if DEBUG:
            print(f"[DEBUG][{symbol}][{timeframe}] ❌ Insufficient candles")
        return None, "DATA UNAVAILABLE"

    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    volumes = df['volume'].values

    curr_close = float(closes[-1])

    tr = np.maximum(highs[1:] - lows[1:], 
                    np.abs(highs[1:] - closes[:-1]),
                    np.abs(lows[1:] - closes[:-1]))
    atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)
    vol_factor = atr / curr_close if curr_close > 0 else 0
    lookback = min(40, max(20, int(30 * (1 + vol_factor * 10))))
    lookback = min(lookback, len(df) - 1)

    support, resistance, support_touches, resistance_touches = detect_support_resistance(
        highs, lows, closes, lookback
    )

    range_height = resistance - support
    range_mid = (resistance + support) / 2
    range_width_pct = (range_height / range_mid) * 100 if range_mid > 0 else 100

    if DEBUG:
        print(f"[DEBUG][{symbol}][{timeframe}] Range: S={support:.6f}, R={resistance:.6f}, Width={range_width_pct:.2f}%")
        print(f"[DEBUG][{symbol}][{timeframe}] Touches: Support={support_touches}, Resistance={resistance_touches}")

    if range_height <= 0:
        return None, "NO RANGE"

    if range_width_pct > 12.0:
        if DEBUG:
            print(f"[DEBUG][{symbol}][{timeframe}] ❌ Range too wide: {range_width_pct:.2f}%")
        return None, "RANGE TOO WIDE"

    dist_to_resistance = (resistance - curr_close) / curr_close * 100
    dist_to_support = (curr_close - support) / curr_close * 100

    if dist_to_resistance < dist_to_support:
        primary_direction = "BULLISH"
        breakout_level = resistance
        distance_to_breakout = dist_to_resistance
        touches = resistance_touches
    else:
        primary_direction = "BEARISH"
        breakout_level = support
        distance_to_breakout = dist_to_support
        touches = support_touches

    if touches < 2:
        if DEBUG:
            print(f"[DEBUG][{symbol}][{timeframe}] ❌ Breakout level has only {touches} touch(es)")
        return None, "INSUFFICIENT_TOUCHES"

    vol_ma20 = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
    vol_ma5 = np.mean(volumes[-5:]) if len(volumes) >= 5 else 0
    vol_trend = np.polyfit(range(10), volumes[-10:], 1)[0] if len(volumes) >= 10 else 0

    if vol_ma5 < vol_ma20 * 0.6 and vol_trend < 0:
        volume_label = "Drying Up"
        volume_score = 25
    elif vol_ma5 < vol_ma20 * 0.8 and vol_trend < 0:
        volume_label = "Drying Up"
        volume_score = 20
    elif vol_ma5 < vol_ma20 * 0.9:
        volume_label = "Picking Up"
        volume_score = 15
    elif vol_ma5 < vol_ma20 * 1.2:
        volume_label = "Picking Up"
        volume_score = 10
    elif vol_ma5 < vol_ma20 * 1.8:
        volume_label = "Expanding"
        volume_score = 8
    else:
        volume_label = "Exploding"
        volume_score = 5

    if DEBUG:
        print(f"[DEBUG][{symbol}][{timeframe}] Volume: {volume_label} (score={volume_score})")

    max_distance = 5.0
    proximity_score = max(0, min(35, 35 * (1 - min(distance_to_breakout, max_distance) / max_distance)))
    if DEBUG:
        print(f"[DEBUG][{symbol}][{timeframe}] Proximity Score: {proximity_score:.1f}/35")

    pattern_maturity = min(20, touches * 5)
    if DEBUG:
        print(f"[DEBUG][{symbol}][{timeframe}] Pattern Maturity: {pattern_maturity:.1f}/20")

    if range_width_pct < 2.0:
        tightness_score = 10
    elif range_width_pct < 3.0:
        tightness_score = 7
    elif range_width_pct < 5.0:
        tightness_score = 4
    else:
        tightness_score = 0
    if DEBUG:
        print(f"[DEBUG][{symbol}][{timeframe}] Tightness Score: {tightness_score:.1f}/10")

    candle_score = 0
    for i in range(max(0, len(closes)-6), len(closes)-1):
        candle_range = highs[i] - lows[i]
        if candle_range > 0:
            if primary_direction == "BULLISH":
                close_position = (closes[i] - lows[i]) / candle_range
                if close_position > 0.7:
                    candle_score += 2
                if highs[i] - breakout_level < 0.001:
                    candle_score += 1
            else:
                close_position = (closes[i] - lows[i]) / candle_range
                if close_position < 0.3:
                    candle_score += 2
                if breakout_level - lows[i] < 0.001:
                    candle_score += 1
    candle_score = min(10, candle_score)
    if DEBUG:
        print(f"[DEBUG][{symbol}][{timeframe}] Candle Score: {candle_score:.1f}/10")

    readiness_score = int(round(proximity_score + volume_score + pattern_maturity + tightness_score + candle_score))
    readiness_score = max(0, min(100, readiness_score))

    if DEBUG:
        print(f"[DEBUG][{symbol}][{timeframe}] Total Readiness: {readiness_score}%")

    last_10_lows = lows[-10:]
    last_10_highs = highs[-10:]
    higher_lows = all(last_10_lows[i] >= last_10_lows[i-1] for i in range(1, len(last_10_lows)))
    lower_highs = all(last_10_highs[i] <= last_10_highs[i-1] for i in range(1, len(last_10_highs)))

    if higher_lows and primary_direction == "BULLISH":
        pattern_type = "ASCENDING TRIANGLE"
    elif lower_highs and primary_direction == "BEARISH":
        pattern_type = "DESCENDING TRIANGLE"
    elif range_width_pct < 2.0:
        pattern_type = "RECTANGLE"
    else:
        pattern_type = "CONSOLIDATION"

    if DEBUG:
        print(f"[DEBUG][{symbol}][{timeframe}] Pattern: {pattern_type}")

    if readiness_score >= 80 and pattern_type in ["ASCENDING TRIANGLE", "RECTANGLE"]:
        confidence = "Very High"
    elif readiness_score >= 65:
        confidence = "High"
    elif readiness_score >= 45:
        confidence = "Medium"
    elif readiness_score >= 25:
        confidence = "Low"
    else:
        confidence = "Very Low"

    if readiness_score >= 80:
        status_label = "Almost Ready"
    elif readiness_score >= 65:
        status_label = "Building"
    elif readiness_score >= 45:
        status_label = "Developing"
    elif readiness_score >= 25:
        status_label = "Early"
    else:
        status_label = "Waiting"

    last_updated = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    clean_display = symbol.replace("-", "").replace("_", "").upper()

    if primary_direction == "BULLISH":
        direction_label = "Bullish Breakout Candidate"
        break_symbol = "▲"
    else:
        direction_label = "Bearish Breakdown Candidate"
        break_symbol = "▼"

    if DEBUG:
        print(f"[DEBUG][{symbol}][{timeframe}] ✅ FINAL: {primary_direction} {readiness_score}%")
        print(f"[DEBUG][{symbol}][{timeframe}] === ANALYSIS COMPLETE ===")

    return {
        "symbol": clean_display,
        "timeframe": timeframe,
        "curr_close": round(curr_close, 6),
        "support": round(support, 6),
        "resistance": round(resistance, 6),
        "range_width": round(range_width_pct, 2),
        "pattern_type": pattern_type,
        "direction_label": direction_label,
        "break_direction": primary_direction,
        "break_symbol": break_symbol,
        "readiness_score": readiness_score,
        "readiness_display": f"{readiness_score}%",
        "distance_to_resistance": round(dist_to_resistance, 2),
        "distance_to_support": round(dist_to_support, 2),
        "volume_label": volume_label,
        "confidence": confidence,
        "status_label": status_label,
        "touches": touches,
        "last_updated": last_updated
    }, None


def _process_symbol_tf(symbol: str, tf: str):
    """Process a single symbol/timeframe combination."""
    print(f"[SCAN][{symbol}][{tf}] Starting...")
    df = fetch_ohlcv(symbol, tf)
    if df.empty:
        print(f"[SCAN][{symbol}][{tf}] ❌ No data")
        return None, "DATA UNAVAILABLE"
    result, err = analyze_range_structure(df, symbol, tf)
    if result:
        print(f"[SCAN][{symbol}][{tf}] ✅ PASSED - Readiness: {result['readiness_score']}%")
    else:
        print(f"[SCAN][{symbol}][{tf}] ❌ FAILED - {err}")
    return result, err


def run_scanner_pipeline(symbols: list, timeframe: str = "ALL"):
    results = []
    diagnostics = {"symbols_scanned": len(symbols), "symbols_downloaded": 0, "rejections": {}}

    tfs_to_run = ["5M", "15M", "1H", "4H"] if timeframe == "ALL" else [timeframe]

    for sym in symbols:
        for tf in tfs_to_run:
            match, err = _process_symbol_tf(sym, tf)
            if match:
                diagnostics["symbols_downloaded"] += 1
                results.append(match)
            else:
                diagnostics["rejections"][err] = diagnostics["rejections"].get(err, 0) + 1

    results.sort(key=lambda x: -x["readiness_score"])
    return results, diagnostics
