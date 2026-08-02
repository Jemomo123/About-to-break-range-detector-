# app.py
# =====================================================================
# VERSION 1.2 — TIMEFRAME UPGRADE & SINGLE SOURCE OF TRUTH
# =====================================================================

import numpy as np
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Operational Constants
SUPPORTED_TIMEFRAMES = ["2m", "5m", "15m"]
DEFAULT_TIMEFRAME = "5m"
TARGET_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


# =====================================================================
# FLASK ROUTES
# =====================================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scan")
def scan():
    # Parse timeframe query parameter; default to 5m
    tf = request.args.get("timeframe", DEFAULT_TIMEFRAME)
    if tf not in SUPPORTED_TIMEFRAMES:
        tf = DEFAULT_TIMEFRAME

    data = run_scanner(timeframe=tf)
    return jsonify({"timeframe": tf, "results": data})


def run_scanner(timeframe=DEFAULT_TIMEFRAME):
    """
    Executes scan across TARGET_SYMBOLS for the selected timeframe.
    app.py performs ALL indicator and metrics calculations.
    """
    results = []
    
    for symbol in TARGET_SYMBOLS:
        # Fetch Binance OHLCV data using the selected timeframe interval
        highs, lows, closes, volumes, taker_buy_vols = fetch_binance_klines(symbol, interval=timeframe)
        
        if len(closes) < 50:
            continue

        # Single Source of Truth Engine Execution
        val_range = get_validated_range(highs, lows, closes, volumes)
        status = calculate_status_engine(highs, lows, closes, val_range)
        battle = calculate_battle_engine(volumes, taker_buy_vols)
        location = calculate_location_engine(closes, val_range)
        readiness = calculate_breakout_readiness(
            status["status_score"], battle["battle_score"], location["location_score"], val_range
        )
        evidence = generate_compact_evidence(status, battle, location, readiness, val_range)

        results.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "status": status["status_label"],
            "battle": battle["battle_label"],
            "location": location["location_label"],
            "readiness": readiness["readiness_label"],
            "evidence": evidence
        })

    return results


def fetch_binance_klines(symbol, interval="5m", limit=100):
    """
    Placeholder/Helper for Binance Klines fetching logic.
    Returns: highs, lows, closes, volumes, taker_buy_volumes as numpy arrays.
    """
    # Replace with your production Binance API call passing standard interval=interval
    # e.g., https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=2m&limit=100
    return np.array([]), np.array([]), np.array([]), np.array([]), np.array([])


# =====================================================================
# 1. RANGE ENGINE (SINGLE SOURCE OF TRUTH)
# =====================================================================

def get_validated_range(highs, lows, closes, volumes, lookback_window=50):
    """
    Absolute sole engine for range boundary calculations across the repository.
    Calculates v_high, v_low, height, touches, containment, and expansion status.
    """
    if len(closes) < lookback_window:
        return None

    window_highs = highs[-lookback_window:]
    window_lows = lows[-lookback_window:]
    window_closes = closes[-lookback_window:]

    v_high = float(np.max(window_highs))
    v_low = float(np.min(window_lows))
    r_height = v_high - v_low

    if r_height <= 0:
        return None

    # Calculate touches near boundaries (within 1.5% buffer of height)
    touch_buffer = r_height * 0.015
    upper_touches = int(np.sum(window_highs >= (v_high - touch_buffer)))
    lower_touches = int(np.sum(window_lows <= (v_low + touch_buffer)))

    # Calculate containment percentage (closes inside inner 90% boundary)
    inner_upper = v_high - (r_height * 0.05)
    inner_lower = v_low + (r_height * 0.05)
    contained_count = np.sum((window_closes <= inner_upper) & (window_closes >= inner_lower))
    containment_pct = round(float((contained_count / lookback_window) * 100.0), 1)

    # Structural validity and expansion checks
    is_structurally_valid = containment_pct >= 70.0 and upper_touches >= 2 and lower_touches >= 2
    
    current_close = closes[-1]
    has_already_expanded = current_close > v_high or current_close < v_low

    return {
        "v_high": v_high,
        "v_low": v_low,
        "r_height": r_height,
        "upper_touches": upper_touches,
        "lower_touches": lower_touches,
        "containment_pct": containment_pct,
        "is_structurally_valid": is_structurally_valid,
        "has_already_expanded": has_already_expanded,
        "lookback_window": lookback_window
    }


# =====================================================================
# 2. STATUS ENGINE (UPDATED TO COMPACT STATUS LABELS)
# =====================================================================

def calculate_status_engine(highs, lows, closes, val_range):
    """
    Evaluates market containment state within the validated range.
    Uses compact labels to prevent status UI blowout on mobile/small screens.
    """
    if val_range is None:
        return {"status_score": 0, "status_label": "NO RANGE"}

    if val_range["has_already_expanded"]:
        return {"status_score": 10, "status_label": "EXPANDED"}

    containment = val_range["containment_pct"]
    
    if containment >= 85.0:
        status_score = 90
        status_label = "HIGH COMP"
    elif containment >= 70.0:
        status_score = 75
        status_label = "COMP"
    else:
        status_score = 40
        status_label = "LOOSE COMP"

    return {
        "status_score": status_score,
        "status_label": status_label
    }


# =====================================================================
# 3. BATTLE ENGINE
# =====================================================================

def calculate_battle_engine(volumes, taker_buy_volumes=None, open_interest=None, funding_rates=None):
    """
    Evaluates buyer vs. seller control and volume effort.
    """
    if volumes is None or len(volumes) < 20:
        return {"battle_score": 50, "battle_label": "NEUTRAL"}

    recent_vol = volumes[-5:]
    avg_vol = np.mean(volumes[-20:])
    vol_ratio = np.mean(recent_vol) / avg_vol if avg_vol > 0 else 1.0

    if taker_buy_volumes is not None and len(taker_buy_volumes) >= 5:
        buy_ratio = np.sum(taker_buy_volumes[-5:]) / np.sum(recent_vol) if np.sum(recent_vol) > 0 else 0.5
    else:
        buy_ratio = 0.5

    if buy_ratio > 0.55 and vol_ratio > 1.2:
        battle_score = 85
        battle_label = "BULL DOMINANCE"
    elif buy_ratio < 0.45 and vol_ratio > 1.2:
        battle_score = 15
        battle_label = "BEAR DOMINANCE"
    else:
        battle_score = 50
        battle_label = "BALANCED"

    return {
        "battle_score": battle_score,
        "battle_label": battle_label
    }


# =====================================================================
# 4. LOCATION ENGINE
# =====================================================================

def calculate_location_engine(closes, val_range):
    """
    Evaluates position of current close price within the validated range.
    """
    if val_range is None or val_range["r_height"] <= 0:
        return {"location_score": 50, "location_label": "MID RANGE", "position_pct": 50.0}

    current_close = closes[-1]
    v_low = val_range["v_low"]
    r_height = val_range["r_height"]

    position_pct = round(((current_close - v_low) / r_height) * 100.0, 1)

    if position_pct >= 80.0:
        location_score = 90
        location_label = "UPPER RESISTANCE"
    elif position_pct <= 20.0:
        location_score = 90
        location_label = "LOWER SUPPORT"
    else:
        location_score = 40
        location_label = "MID RANGE"

    return {
        "location_score": location_score,
        "location_label": location_label,
        "position_pct": position_pct
    }


# =====================================================================
# 5. BREAKOUT READINESS ENGINE
# =====================================================================

def calculate_breakout_readiness(status_score, battle_score, location_score, val_range):
    """
    Synthesizes Status, Battle, and Location engines into a final readiness score.
    """
    if val_range is None or val_range["has_already_expanded"]:
        return {"readiness_score": 0, "readiness_label": "INACTIVE"}

    # Weighted score calculation
    readiness_score = int(round((status_score * 0.40) + (battle_score * 0.30) + (location_score * 0.30)))

    if readiness_score >= 80:
        readiness_label = "IMMINENT"
    elif readiness_score >= 60:
        readiness_label = "BUILDING"
    else:
        readiness_label = "LOW"

    return {
        "readiness_score": readiness_score,
        "readiness_label": readiness_label
    }


# =====================================================================
# 6. EVIDENCE SYNTHESIS ENGINE
# =====================================================================

def generate_compact_evidence(status, battle, location, readiness, val_range):
    """
    Generates structured, human-readable trader evidence string for UI rendering.
    Maps evidence interpretation cleanly to approved containment terminology.
    """
    if val_range is None:
        return "NO_DATA"

    containment = val_range.get("containment_pct", 0.0)
    u_touches = val_range.get("upper_touches", 0)
    l_touches = val_range.get("lower_touches", 0)
    
    # Extract order flow label in title case
    battle_label = battle.get("battle_label", "BALANCED").title() if isinstance(battle, dict) else str(battle).title()
    
    # Calculate distance relative to boundary
    position_pct = location.get("position_pct", 50.0) if isinstance(location, dict) else 50.0
    dist_from_resistance = round(100.0 - position_pct, 1)
    dist_from_support = round(position_pct, 1)

    if position_pct >= 50.0:
        position_text = f"{dist_from_resistance}% below resistance"
    else:
        position_text = f"{dist_from_support}% above support"

    # Contextual interpretation based on containment level
    status_str = status.get("status_label", "") if isinstance(status, dict) else str(status)
    if "HIGH COMP" in status_str:
        if position_pct >= 80.0:
            interpretation = "High range containment near upper boundary.\nWatching for breakout confirmation."
        elif position_pct <= 20.0:
            interpretation = "High range containment near lower boundary.\nWatching for breakdown confirmation."
        else:
            interpretation = "High range containment coiled at mid-range.\nAwaiting direction signal."
    elif "COMP" in status_str:
        interpretation = "Active containment within validated range boundaries."
    else:
        interpretation = "Price operating within loose range distribution."

    return (
        f"Range Quality: {containment:.0f}%\n\n"
        f"Price Position:\n{position_text}\n\n"
        f"Range Touches:\nUpper: {u_touches}\nLower: {l_touches}\n\n"
        f"Order Flow:\n{battle_label}\n\n"
        f"Interpretation:\n{interpretation}"
    )
