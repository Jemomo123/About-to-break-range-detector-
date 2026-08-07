import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 150):
    """
    PRIMARY: OKX REST API
    FALLBACK: MEXC REST API
    """
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
            data = res_json.get("data", [])
            if isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'volCcy', 'volCcyQuote', 'confirm'
                ])
                df = df.iloc[::-1].reset_index(drop=True)
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                print(f"[OKX][{symbol}][{timeframe}] ✓ Downloaded {len(df)} candles")
                return df
            else:
                print(f"[OKX][{symbol}] Empty data. Code: {res_json.get('code')}")
        else:
            print(f"[OKX][{symbol}] HTTP {resp.status_code}")
    except Exception as e:
        print(f"[OKX][{symbol}] Exception: {e}")

    # FALLBACK: MEXC
    mexc_sym = clean_sym
    mexc_tf_map = {"5M": "5m", "15M": "15m", "1H": "1h", "4H": "4h"}
    mexc_bar = mexc_tf_map.get(timeframe, "15m")
    mexc_url = f"https://api.mexc.com/api/v3/klines?symbol={mexc_sym}&interval={mexc_bar}&limit={limit}"
    try:
        resp = requests.get(mexc_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_vol', 'trades', 'tb_base_vol', 'tb_quote_vol', 'ignore'
                ])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                print(f"[MEXC][{symbol}][{timeframe}] ✓ Downloaded {len(df)} candles")
                return df
            else:
                print(f"[MEXC][{symbol}] Empty data.")
        else:
            print(f"[MEXC][{symbol}] HTTP {resp.status_code}")
    except Exception as e:
        print(f"[MEXC][{symbol}] Exception: {e}")

    print(f"[{symbol}][{timeframe}] ✗ FAILED")
    return pd.DataFrame()


def detect_support_resistance(highs, lows, closes, lookback=30):
    """
    Identifies key support and resistance levels using local peaks and troughs.
    Returns: (support, resistance) as (level, number_of_touches)
    """
    # Use rolling windows to find local highs and lows
    # For simplicity, we'll use percentile-based levels for now
    # But we can implement more advanced clustering later
    
    # For this iteration, we use the min/max of the lookback period
    # and count touches within a tolerance of 0.5%
    support = np.min(lows[-lookback:])
    resistance = np.max(highs[-lookback:])
    
    # Count touches
    tolerance = 0.005  # 0.5%
    support_touches = 0
    resistance_touches = 0
    for i in range(len(closes) - lookback, len(closes)):
        price = closes[i]
        if abs(price - support) / support < tolerance:
            support_touches += 1
        if abs(price - resistance) / resistance < tolerance:
            resistance_touches += 1
    
    # For bullish: resistance is the breakout level, for bearish: support is the breakdown level
    # But we'll return both with touch counts
    return support, resistance, support_touches, resistance_touches


def analyze_range_structure(df: pd.DataFrame, symbol: str, timeframe: str):
    """
    Advanced breakout detection with improved range, volume, and scoring.
    """
    print(f"[DEBUG][{symbol}][{timeframe}] === STARTING ANALYSIS ===")
    
    # --- DATA VALIDATION ---
    if df.empty or len(df) < 30:
        print(f"[DEBUG][{symbol}][{timeframe}] ❌ Insufficient candles")
        return None, "DATA UNAVAILABLE"
    
    # --- EXTRACT PRICE DATA ---
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    volumes = df['volume'].values
    
    curr_close = float(closes[-1])
    curr_high = float(highs[-1])
    curr_low = float(lows[-1])
    
    # --- 1. IMPROVED RANGE DETECTION ---
    # Use dynamic lookback (20-40 candles) based on volatility
    # Calculate ATR over 14 periods to estimate volatility
    tr = np.maximum(highs[1:] - lows[1:], 
                    np.abs(highs[1:] - closes[:-1]),
                    np.abs(lows[1:] - closes[:-1]))
    atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)
    
    # Lookback proportional to volatility: higher volatility -> longer lookback
    base_lookback = 30
    vol_factor = atr / curr_close if curr_close > 0 else 0
    lookback = min(40, max(20, int(base_lookback * (1 + vol_factor * 10))))
    lookback = min(lookback, len(df) - 1)
    
    print(f"[DEBUG][{symbol}][{timeframe}] Dynamic lookback: {lookback} candles")
    
    # Identify support and resistance with touch counts
    support, resistance, support_touches, resistance_touches = detect_support_resistance(
        highs, lows, closes, lookback
    )
    
    range_height = resistance - support
    range_mid = (resistance + support) / 2
    range_width_pct = (range_height / range_mid) * 100 if range_mid > 0 else 100
    
    print(f"[DEBUG][{symbol}][{timeframe}] Range: S={support:.6f}, R={resistance:.6f}, Width={range_width_pct:.2f}%")
    print(f"[DEBUG][{symbol}][{timeframe}] Touches: Support={support_touches}, Resistance={resistance_touches}")
    
    # --- VALIDATE RANGE ---
    if range_height <= 0:
        print(f"[DEBUG][{symbol}][{timeframe}] ❌ Invalid range")
        return None, "NO RANGE"
    
    # Range must be narrow enough (< 15% for alts, < 8% for majors)
    # We'll use a moderate threshold: width < 12% for all
    if range_width_pct > 12.0:
        print(f"[DEBUG][{symbol}][{timeframe}] ❌ Range too wide: {range_width_pct:.2f}%")
        return None, "RANGE TOO WIDE"
    
    # Range must have at least 2 touches on the breakout side
    # Determine breakout direction based on proximity
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
    
    # Minimum touches: at least 2 for a valid level
    if touches < 2:
        print(f"[DEBUG][{symbol}][{timeframe}] ❌ Breakout level has only {touches} touch(es)")
        return None, "INSUFFICIENT_TOUCHES"
    
    print(f"[DEBUG][{symbol}][{timeframe}] Breakout level: {breakout_level:.6f} ({touches} touches)")
    
    # --- 2. IMPROVED VOLUME CONTRACTION ---
    # Calculate volume trend over last 10 candles
    vol_ma20 = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
    vol_ma5 = np.mean(volumes[-5:]) if len(volumes) >= 5 else 0
    vol_trend = np.polyfit(range(10), volumes[-10:], 1)[0] if len(volumes) >= 10 else 0
    
    # Determine volume label
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
    
    print(f"[DEBUG][{symbol}][{timeframe}] Volume: {volume_label} (score={volume_score})")
    
    # --- 3. PROXIMITY SCORE (35 points) ---
    # Closer = higher score
    max_distance = 5.0  # 5% away max
    proximity_score = max(0, min(35, 35 * (1 - min(distance_to_breakout, max_distance) / max_distance)))
    print(f"[DEBUG][{symbol}][{timeframe}] Proximity Score: {proximity_score:.1f}/35")
    
    # --- 4. PATTERN MATURITY (20 points) ---
    # Touches increase maturity
    pattern_maturity = min(20, touches * 5)  # each touch = 5 points, max 20
    print(f"[DEBUG][{symbol}][{timeframe}] Pattern Maturity: {pattern_maturity:.1f}/20")
    
    # --- 5. RANGE TIGHTNESS (10 points) ---
    if range_width_pct < 2.0:
        tightness_score = 10
    elif range_width_pct < 3.0:
        tightness_score = 7
    elif range_width_pct < 5.0:
        tightness_score = 4
    else:
        tightness_score = 0
    print(f"[DEBUG][{symbol}][{timeframe}] Tightness Score: {tightness_score:.1f}/10")
    
    # --- 6. CANDLE BEHAVIOR (10 points) ---
    # Look at last 5 candles: are they compressing or rejecting?
    candle_score = 0
    for i in range(max(0, len(closes)-6), len(closes)-1):
        candle_range = highs[i] - lows[i]
        if candle_range > 0:
            # Check if candle is inside the upper/lower third
            if primary_direction == "BULLISH":
                close_position = (closes[i] - lows[i]) / candle_range
                if close_position > 0.7:
                    candle_score += 2
                # Also check for wick above resistance
                if highs[i] - breakout_level < 0.001:
                    candle_score += 1
            else:
                close_position = (closes[i] - lows[i]) / candle_range
                if close_position < 0.3:
                    candle_score += 2
                if breakout_level - lows[i] < 0.001:
                    candle_score += 1
    candle_score = min(10, candle_score)
    print(f"[DEBUG][{symbol}][{timeframe}] Candle Score: {candle_score:.1f}/10")
    
    # --- CALCULATE TOTAL READINESS (0-100) ---
    readiness_score = int(round(proximity_score + volume_score + pattern_maturity + tightness_score + candle_score))
    readiness_score = max(0, min(100, readiness_score))
    
    print(f"[DEBUG][{symbol}][{timeframe}] Total Readiness: {readiness_score}%")
    
    # --- PATTERN TYPE ---
    # Check for ascending/descending triangle based on HL/LL patterns
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
    
    print(f"[DEBUG][{symbol}][{timeframe}] Pattern: {pattern_type}")
    
    # --- CONFIDENCE LEVEL ---
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
    
    # --- STATUS ---
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
    print(f"[DEBUG][{symbol}][{tf}] >>> Starting scan")
    df = fetch_ohlcv(symbol, tf)
    if df.empty:
        print(f"[DEBUG][{symbol}][{tf}] ❌ No data from fetch")
        return None, "DATA UNAVAILABLE"
    result, err = analyze_range_structure(df, symbol, tf)
    if result:
        print(f"[DEBUG][{symbol}][{tf}] ✅ PASSED - Readiness: {result['readiness_score']}%")
    else:
        print(f"[DEBUG][{symbol}][{tf}] ❌ FAILED - {err}")
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
