import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 100):
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
        print(f"[OKX][{symbol}][{timeframe}] Fetching...")
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
        print(f"[MEXC][{symbol}][{timeframe}] Fallback...")
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


def analyze_range_structure(df: pd.DataFrame, symbol: str, timeframe: str):
    """
    Advanced range/breakout detection with weighted readiness score.
    Returns comprehensive breakout metrics.
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
    
    # --- DETECT RANGE (LOOKBACK 30 CANDLES) ---
    lookback = min(30, len(df))
    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]
    
    resistance = float(np.max(recent_highs))
    support = float(np.min(recent_lows))
    range_height = resistance - support
    range_mid = (resistance + support) / 2
    range_width_pct = (range_height / range_mid) * 100
    
    print(f"[DEBUG][{symbol}][{timeframe}] Range: S={support:.6f}, R={resistance:.6f}, Width={range_width_pct:.2f}%")
    print(f"[DEBUG][{symbol}][{timeframe}] Current Close: {curr_close:.6f}")
    
    # --- VALIDATE RANGE ---
    if range_height <= 0:
        print(f"[DEBUG][{symbol}][{timeframe}] ❌ Invalid range")
        return None, "NO RANGE"
    
    if range_width_pct > 20:
        print(f"[DEBUG][{symbol}][{timeframe}] ❌ Range too wide: {range_width_pct:.2f}%")
        return None, "RANGE TOO WIDE"
    
    # --- DISTANCE TO BOUNDARIES ---
    dist_to_resistance_pct = ((resistance - curr_close) / curr_close) * 100
    dist_to_support_pct = ((curr_close - support) / curr_close) * 100
    dist_to_resistance_range = (resistance - curr_close) / range_height
    dist_to_support_range = (curr_close - support) / range_height
    
    print(f"[DEBUG][{symbol}][{timeframe}] Dist to R: {dist_to_resistance_pct:.2f}%, Dist to S: {dist_to_support_pct:.2f}%")
    
    # Determine primary breakout direction
    if dist_to_resistance_range < dist_to_support_range:
        primary_direction = "BULLISH"
        distance_to_breakout = dist_to_resistance_pct
        breakout_level = resistance
    else:
        primary_direction = "BEARISH"
        distance_to_breakout = dist_to_support_pct
        breakout_level = support
    
    print(f"[DEBUG][{symbol}][{timeframe}] Primary direction: {primary_direction}, Distance: {distance_to_breakout:.2f}%")
    
    # --- 1. PROXIMITY SCORE (0-25) ---
    # Closer to breakout = higher score
    max_distance = 5.0  # 5% away is the max we care about
    proximity_score = max(0, min(25, 25 * (1 - min(distance_to_breakout, max_distance) / max_distance)))
    print(f"[DEBUG][{symbol}][{timeframe}] Proximity Score: {proximity_score:.1f}/25")
    
    # --- 2. PATTERN MATURITY (0-20) ---
    # How many times has price tested the breakout level?
    # Look back 20 candles for touches within 0.5% of the level
    tolerance = 0.005  # 0.5%
    touches = 0
    for i in range(max(0, len(closes)-30), len(closes)-1):
        test_price = closes[i]
        if primary_direction == "BULLISH":
            if (breakout_level - test_price) / breakout_level < tolerance:
                touches += 1
        else:
            if (test_price - breakout_level) / breakout_level < tolerance:
                touches += 1
    
    pattern_maturity = min(20, touches * 4)  # Each touch = 4 points, max 20
    print(f"[DEBUG][{symbol}][{timeframe}] Pattern Maturity: {pattern_maturity:.1f}/20 ({touches} touches)")
    
    # --- 3. RANGE WIDTH SCORE (0-15) ---
    # Narrower ranges = higher breakout probability
    if range_width_pct < 1.0:
        width_score = 15
    elif range_width_pct < 2.0:
        width_score = 12
    elif range_width_pct < 3.0:
        width_score = 8
    elif range_width_pct < 5.0:
        width_score = 5
    else:
        width_score = 0
    print(f"[DEBUG][{symbol}][{timeframe}] Width Score: {width_score:.1f}/15")
    
    # --- 4. VOLUME ANALYSIS (0-20) ---
    # Volume drying up = higher score (breakout building)
    last_20_vol = volumes[-20:]
    last_5_vol = volumes[-5:]
    vol_avg_20 = np.mean(last_20_vol) if len(last_20_vol) > 0 else 0
    vol_avg_5 = np.mean(last_5_vol) if len(last_5_vol) > 0 else 0
    
    if vol_avg_20 > 0:
        vol_ratio = vol_avg_5 / vol_avg_20
    else:
        vol_ratio = 1.0
    
    # Volume drying up = ratio < 0.8 = higher score
    if vol_ratio < 0.6:
        volume_score = 20
        volume_label = "Drying Up"
    elif vol_ratio < 0.8:
        volume_score = 15
        volume_label = "Drying Up"
    elif vol_ratio < 0.9:
        volume_score = 10
        volume_label = "Picking Up"
    elif vol_ratio < 1.2:
        volume_score = 5
        volume_label = "Picking Up"
    elif vol_ratio < 1.5:
        volume_score = 8
        volume_label = "Expanding"
    else:
        volume_score = 3
        volume_label = "Exploding"
    
    print(f"[DEBUG][{symbol}][{timeframe}] Volume Score: {volume_score:.1f}/20 ({volume_label}, ratio={vol_ratio:.2f})")
    
    # --- 5. CANDLE BEHAVIOR (0-20) ---
    # Look at the last 5 candles near the boundary
    candle_score = 0
    for i in range(max(0, len(closes)-6), len(closes)-1):
        candle_high = highs[i]
        candle_low = lows[i]
        if primary_direction == "BULLISH":
            # Bullish candles: closing near high, wicks rejecting the level
            body_high = max(closes[i], closes[i+1] if i+1 < len(closes) else closes[i])
            body_low = min(closes[i], closes[i+1] if i+1 < len(closes) else closes[i])
            candle_range = candle_high - candle_low
            if candle_range > 0:
                close_position = (closes[i] - candle_low) / candle_range
                if close_position > 0.7:
                    candle_score += 4  # Bullish close
                if (candle_high - max(closes[i], closes[i+1] if i+1 < len(closes) else closes[i])) / candle_range > 0.3:
                    candle_score += 2  # Wick rejection
        else:
            # Bearish candles: closing near low, wicks rejecting support
            body_high = max(closes[i], closes[i+1] if i+1 < len(closes) else closes[i])
            body_low = min(closes[i], closes[i+1] if i+1 < len(closes) else closes[i])
            candle_range = candle_high - candle_low
            if candle_range > 0:
                close_position = (closes[i] - candle_low) / candle_range
                if close_position < 0.3:
                    candle_score += 4  # Bearish close
                if (min(closes[i], closes[i+1] if i+1 < len(closes) else closes[i]) - candle_low) / candle_range > 0.3:
                    candle_score += 2  # Wick rejection
    
    candle_score = min(20, candle_score)
    print(f"[DEBUG][{symbol}][{timeframe}] Candle Score: {candle_score:.1f}/20")
    
    # --- CALCULATE TOTAL READINESS SCORE (0-100) ---
    readiness_score = int(round(proximity_score + pattern_maturity + width_score + volume_score + candle_score))
    readiness_score = max(0, min(100, readiness_score))
    
    print(f"[DEBUG][{symbol}][{timeframe}] Total Readiness: {readiness_score}%")
    
    # --- DETERMINE PATTERN TYPE ---
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
    
    # --- DETERMINE CONFIDENCE LEVEL ---
    # Based on readiness and pattern quality
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
    
    # --- STATUS LABEL ---
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
    
    print(f"[DEBUG][{symbol}][{timeframe}] Confidence: {confidence}, Status: {status_label}")
    
    # --- MULTI-TIMEFRAME ALIGNMENT ---
    # We'll calculate this in the frontend by looking at all timeframes
    # For now, store the readiness for each timeframe
    # The frontend will handle the alignment display
    
    last_updated = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    clean_display = symbol.replace("-", "").replace("_", "").upper()
    
    # Determine direction label
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
        "distance_to_resistance": round(dist_to_resistance_pct, 2),
        "distance_to_support": round(dist_to_support_pct, 2),
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
