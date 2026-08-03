# scanner.py
import numpy as np
from detector import fetch_market_candles, validate_range_structure, analyze_order_battle

def calculate_readiness_data(val_range, battle_label):
    current_close = val_range["current_close"]
    v_high = val_range["v_high"]
    v_low = val_range["v_low"]
    r_height = val_range["r_height"]

    position_pct = float(np.clip(((current_close - v_low) / r_height) * 100.0, 0.0, 100.0))
    dist_to_res = ((v_high - current_close) / current_close) * 100.0
    dist_to_sup = ((current_close - v_low) / current_close) * 100.0
    distance = round(min(dist_to_res, dist_to_sup), 2)

    if position_pct >= 75.0:
        direction = "UPSIDE" if battle_label == "BUYERS WINNING" else ("DOWNSIDE" if battle_label == "SELLERS WINNING" else "BALANCED")
    elif position_pct <= 25.0:
        direction = "DOWNSIDE" if battle_label == "SELLERS WINNING" else ("UPSIDE" if battle_label == "BUYERS WINNING" else "BALANCED")
    else:
        direction = "BALANCED"

    score = int(round((val_range["containment_pct"] * 0.3) + (max(position_pct, 100 - position_pct) * 0.4) + (30 if battle_label != "BALANCED" else 15)))
    score = int(np.clip(score, 0, 100))

    if score >= 90: label = "IMMINENT"
    elif score >= 82: label = "VERY HIGH"
    elif score >= 75: label = "HIGH"
    elif score >= 68: label = "BUILDING"
    elif score >= 60: label = "DEVELOPING"
    elif score >= 50: label = "WATCH"
    else: label = "LOW"

    return {
        "readiness_score": score,
        "readiness_label": label,
        "direction": direction,
        "resistance": v_high,
        "support": v_low,
        "distance": distance,
        "containment_pct": val_range["containment_pct"],
        "upper_touches": val_range["upper_touches"],
        "lower_touches": val_range["lower_touches"],
        "battle_label": battle_label
    }

def run_scanner_pipeline(watchlist, timeframe):
    results = []
    for symbol in watchlist:
        data = fetch_market_candles(symbol, timeframe)
        if data is None:
            continue

        highs, lows, closes, volumes = data
        val_range = validate_range_structure(highs, lows, closes)
        if val_range is None:
            continue

        battle_label = analyze_order_battle(volumes, closes)
        readiness = calculate_readiness_data(val_range, battle_label)
        readiness["symbol"] = symbol
        results.append(readiness)

    results.sort(key=lambda x: x["readiness_score"], reverse=True)
    return results
