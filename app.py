# app.py
# =====================================================================
# VERSION 1.2.4 — SINGLE SOURCE OF TRUTH & FLASK APPLICATION
# =====================================================================

from flask import Flask, render_template, request
import numpy as np

app = Flask(__name__)

DEFAULT_TIMEFRAME = "1h"
SUPPORTED_TIMEFRAMES = ["3m", "5m", "15m", "1h", "4h"]
TARGET_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def get_validated_range(highs, lows, closes, volumes, lookback_window=50):
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

    touch_buffer = r_height * 0.015
    upper_touches = int(np.sum(window_highs >= (v_high - touch_buffer)))
    lower_touches = int(np.sum(window_lows <= (v_low + touch_buffer)))

    inner_upper = v_high - (r_height * 0.05)
    inner_lower = v_low + (r_height * 0.05)
    contained_count = np.sum((window_closes <= inner_upper) & (window_closes >= inner_lower))
    containment_pct = round(float((contained_count / lookback_window) * 100.0), 1)

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


def calculate_status_engine(highs, lows, closes, val_range):
    if val_range is None:
        return {"status_score": 0, "status_label": "NO_RANGE"}

    if val_range["has_already_expanded"]:
        return {"status_score": 10, "status_label": "EXPANDED"}

    containment = val_range["containment_pct"]
    
    if containment >= 85.0:
        status_score = 90
        status_label = "HIGH CONSOLIDATION"
    elif containment >= 70.0:
        status_score = 75
        status_label = "CONSOLIDATION"
    else:
        status_score = 40
        status_label = "WEAK CONSOLIDATION"

    return {"status_score": status_score, "status_label": status_label}


def calculate_battle_engine(volumes, taker_buy_volumes=None, open_interest=None, funding_rates=None):
    if volumes is None or len(volumes) < 20:
        return {"battle_score": 50.0, "battle_label": "NEUTRAL"}

    recent_vol = volumes[-5:]
    avg_vol = np.mean(volumes[-20:])
    vol_ratio = np.mean(recent_vol) / avg_vol if avg_vol > 0 else 1.0

    if taker_buy_volumes is not None and len(taker_buy_volumes) >= 5:
        buy_ratio = np.sum(taker_buy_volumes[-5:]) / np.sum(recent_vol) if np.sum(recent_vol) > 0 else 0.5
    else:
        buy_ratio = 0.5

    # Direct real-data scaling (no static replacement)
    battle_score = float(np.clip(buy_ratio * 100.0, 0.0, 100.0))

    if buy_ratio >= 0.55 and vol_ratio > 1.2:
        battle_label = "BULL DOMINANCE"
    elif buy_ratio <= 0.45 and vol_ratio > 1.2:
        battle_label = "BEAR DOMINANCE"
    else:
        battle_label = "BALANCED"

    return {"battle_score": battle_score, "battle_label": battle_label}


def calculate_location_engine(closes, val_range):
    if val_range is None or val_range["r_height"] <= 0:
        return {"location_score": 50, "location_label": "MID_RANGE", "position_pct": 50.0}

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

    return {"location_score": location_score, "location_label": location_label, "position_pct": position_pct}


def calculate_breakout_readiness(status_score, battle_score, location_score, val_range, battle_label="BALANCED", position_pct=50.0):
    """
    VERSION 1.2.4 — DIRECTIONAL ALIGNMENT ENGINE
    - 50% Battle, 30% Structure, 20% Location
    - Real market battle scores used directly
    - 45%-55% Neutral Zone for Battle Power
    - Multipliers: 1.12x Reward (Alignment), 0.75x Penalty (Misalignment)
    """
    if val_range is None or val_range.get("has_already_expanded", False):
        return {"readiness_score": 0, "readiness_label": "LOW", "direction": "NEUTRAL"}

    bull_power = float(battle_score)
    bear_power = 100.0 - bull_power

    # Neutral Battle Zone Thresholding (45% - 55%)
    buyers_in_control = bull_power >= 55.0
    sellers_in_control = bear_power >= 55.0

    # Boundary Context
    near_resistance = position_pct >= 75.0
    near_support = position_pct <= 25.0

    REWARD_MULT = 1.12
    PENALTY_MULT = 0.75

    alignment_multiplier = 1.0
    direction = "NEUTRAL"

    if near_resistance:
        if buyers_in_control:
            alignment_multiplier = REWARD_MULT
            direction = "UPSIDE"
            effective_battle = bull_power * alignment_multiplier
        elif sellers_in_control:
            alignment_multiplier = PENALTY_MULT
            direction = "REJECTION_RISK"
            effective_battle = bull_power * alignment_multiplier
        else:
            direction = "RESISTANCE_BALANCED"
            effective_battle = bull_power

    elif near_support:
        if sellers_in_control:
            alignment_multiplier = REWARD_MULT
            direction = "DOWNSIDE"
            effective_battle = bear_power * alignment_multiplier
        elif buyers_in_control:
            alignment_multiplier = PENALTY_MULT
            direction = "ABSORPTION_RISK"
            effective_battle = bear_power * alignment_multiplier
        else:
            direction = "SUPPORT_BALANCED"
            effective_battle = bear_power

    else:
        # Mid-Range: Preserve full dominant strength
        direction = "MID_RANGE"
        effective_battle = max(bull_power, bear_power)

    # Aggregation: Battle (50%), Structure (30%), Location (20%)
    structure_component = status_score * 0.30
    battle_component = min(effective_battle, 100.0) * 0.50
    location_component = location_score * 0.20

    readiness_score = int(round(structure_component + battle_component + location_component))
    readiness_score = min(max(readiness_score, 0), 100)

    # Scale Mapping
    if readiness_score >= 95:
        readiness_label = "IMMINENT"
    elif readiness_score >= 90:
        readiness_label = "VERY HIGH"
    elif readiness_score >= 80:
        readiness_label = "HIGH"
    elif readiness_score >= 70:
        readiness_label = "BUILDING"
    elif readiness_score >= 60:
        readiness_label = "DEVELOPING"
    elif readiness_score >= 40:
        readiness_label = "WATCH"
    else:
        readiness_label = "LOW"

    return {
        "readiness_score": readiness_score,
        "readiness_label": readiness_label,
        "direction": direction
    }


def generate_compact_evidence(status, battle, location, readiness, val_range):
    if val_range is None:
        return "NO_DATA"

    containment = val_range.get("containment_pct", 0.0)
    u_touches = val_range.get("upper_touches", 0)
    l_touches = val_range.get("lower_touches", 0)
    battle_label = battle.get("battle_label", "BALANCED").title() if isinstance(battle, dict) else str(battle).title()
    
    position_pct = location.get("position_pct", 50.0) if isinstance(location, dict) else 50.0
    dist_from_resistance = round(100.0 - position_pct, 1)
    dist_from_support = round(position_pct, 1)

    if position_pct >= 50.0:
        position_text = f"{dist_from_resistance}% below resistance"
    else:
        position_text = f"{dist_from_support}% above support"

    status_str = status.get("status_label", "") if isinstance(status, dict) else str(status)
    if "HIGH CONSOLIDATION" in status_str:
        if position_pct >= 80.0:
            interpretation = "High range containment near upper boundary. Watching for breakout confirmation."
        elif position_pct <= 20.0:
            interpretation = "High range containment near lower boundary. Watching for breakdown confirmation."
        else:
            interpretation = "High range containment coiled at mid-range. Awaiting direction signal."
    elif "CONSOLIDATION" in status_str:
        interpretation = "Active containment within validated range boundaries."
    else:
        interpretation = "Price operating within loose range distribution."

    return (
        f"Range Quality: {containment:.0f}%\n"
        f"Price Position: {position_text}\n"
        f"Range Touches: Upper ({u_touches}), Lower ({l_touches})\n"
        f"Order Flow: {battle_label}\n"
        f"Interpretation: {interpretation}"
    )


@app.route("/")
def index():
    selected_tf = request.args.get("tf", DEFAULT_TIMEFRAME)
    if selected_tf not in SUPPORTED_TIMEFRAMES:
        selected_tf = DEFAULT_TIMEFRAME

    from scanner import run_scanner_pipeline

    rows = run_scanner_pipeline(TARGET_SYMBOLS, timeframe=selected_tf)

    return render_template(
        "index.html",
        rows=rows,
        selected_tf=selected_tf,
        supported_tfs=SUPPORTED_TIMEFRAMES
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
