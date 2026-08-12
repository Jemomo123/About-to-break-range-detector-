import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import threading

# ===== CONFIGURATION =====
DEBUG = True
PROXIMITY_THRESHOLD = 1.5  # 1.5%
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
    # ... (same fetch code as before, unchanged) ...
    # I'll include it fully in the final file.


# ---- All helper functions (find_swings, cluster_prices, etc.) are unchanged ----
# I'll include them, but we don't need to rewrite them.


def analyze_level_battle(df: pd.DataFrame, symbol: str, timeframe: str):
    if df.empty or len(df) < 30:
        return None, "INSUFFICIENT DATA"

    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    curr_close = float(closes[-1])

    # ---- Detect range ----
    support_struct, resistance_struct, _, _, is_accepted, _, _ = find_structural_levels(
        highs=highs, lows=lows, closes=closes,
        lookback=40, tolerance_pct=0.7, min_touches=2, acceptance_threshold=60.0
    )

    support = None
    resistance = None
    range_status = "NO VALID RANGE"
    pattern_type = "NO CLEAR RANGE"

    if support_struct is not None and resistance_struct is not None and is_accepted:
        support = support_struct
        resistance = resistance_struct
        range_status = "STRUCTURAL"
        pattern_type = classify_pattern(df, support, resistance)
    else:
        support_simple, resistance_simple, pattern_type_simple, valid = detect_range_simple(df, lookback=30)
        if valid and support_simple is not None and resistance_simple is not None:
            support = support_simple
            resistance = resistance_simple
            range_status = "PROVISIONAL"
            pattern_type = pattern_type_simple

    # ---- No range ----
    if support is None or resistance is None or support <= 0 or resistance <= 0:
        last_updated = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        clean_display = symbol.replace("-", "").replace("_", "").upper()
        return {
            "symbol": clean_display,
            "timeframe": timeframe,
            "curr_close": round(curr_close, 6),
            "level_type": "NONE",
            "level_price": 0.0,
            "distance_to_level": 0.0,
            "winner": "NEUTRAL",
            "signal": "NO CLEAR SIGNAL",
            "explanation": "No valid range detected.",
            "support": 0.0,
            "resistance": 0.0,
            "pattern_type": "NO CLEAR RANGE",
            "range_status": "NO VALID RANGE",
            "last_updated": last_updated,
            "penetration_type": "NONE",
            "penetration_explanation": "",
            "previous_support": 0.0,
            "previous_resistance": 0.0,
            "invalidation_direction": "NONE",
            "invalidation_price": 0.0,
            "invalidation_time": ""
        }, None

    # ---- Check if price is inside ----
    if support <= curr_close <= resistance:
        # Range is active
        active_support = support
        active_resistance = resistance
        active_status = range_status
        active_pattern = pattern_type
        invalidation_direction = "NONE"
        invalidation_price = 0.0
        previous_support = 0.0
        previous_resistance = 0.0

        # Battle logic (proximity)
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

        # Penetration detection (optional)
        penetration_type = "NONE"
        penetration_explanation = ""
        last_row = df.iloc[-1]
        if last_row['low'] < active_support and last_row['close'] >= active_support:
            penetration_type = "SUPPORT PENETRATION"
            penetration_explanation = f"Support penetrated: candle low ({last_row['low']:.2f}) traded below active support ({active_support:.2f}) but closed back above it."
        elif last_row['high'] > active_resistance and last_row['close'] <= active_resistance:
            penetration_type = "RESISTANCE PENETRATION"
            penetration_explanation = f"Resistance penetrated: candle high ({last_row['high']:.2f}) traded above active resistance ({active_resistance:.2f}) but closed back below it."

        if DEBUG:
            print(f"RANGE ACTIVE {symbol} {timeframe}: {active_support:.2f} - {active_resistance:.2f}")

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
            "support": round(active_support, 6),
            "resistance": round(active_resistance, 6),
            "pattern_type": active_pattern,
            "range_status": active_status,
            "last_updated": last_updated,
            "penetration_type": penetration_type,
            "penetration_explanation": penetration_explanation,
            "previous_support": 0.0,
            "previous_resistance": 0.0,
            "invalidation_direction": "NONE",
            "invalidation_price": 0.0,
            "invalidation_time": ""
        }, None

    else:
        # Price is outside the range → INVALIDATED immediately
        invalidation_direction = "UPSIDE" if curr_close > resistance else "DOWNSIDE"
        invalidation_price = curr_close
        previous_support = support
        previous_resistance = resistance

        if DEBUG:
            print(f"RANGE INVALIDATED {symbol} {timeframe}: close {curr_close:.2f} outside {support:.2f} - {resistance:.2f}")

        last_updated = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        clean_display = symbol.replace("-", "").replace("_", "").upper()

        return {
            "symbol": clean_display,
            "timeframe": timeframe,
            "curr_close": round(curr_close, 6),
            "level_type": "NONE",
            "level_price": 0.0,
            "distance_to_level": 0.0,
            "winner": "NEUTRAL",
            "signal": "NO CLEAR SIGNAL",
            "explanation": f"Range invalidated. Price closed {invalidation_direction} outside the range.",
            "support": 0.0,
            "resistance": 0.0,
            "pattern_type": "NO CLEAR RANGE",
            "range_status": "INVALIDATED",
            "last_updated": last_updated,
            "penetration_type": "NONE",
            "penetration_explanation": "",
            "previous_support": round(previous_support, 6),
            "previous_resistance": round(previous_resistance, 6),
            "invalidation_direction": invalidation_direction,
            "invalidation_price": round(invalidation_price, 6),
            "invalidation_time": datetime.now(timezone.utc).isoformat()
        }, None


# ---- The rest: evaluate_resistance_battle, evaluate_support_battle, etc. are unchanged ----
