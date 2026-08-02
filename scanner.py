# scanner.py
# =====================================================================
# VERSION 1.2.4 — SCANNER PIPELINE ORCHESTRATOR
# Pure Orchestration Layer: Fetches Market Data & Invokes Engine
# =====================================================================

import numpy as np

# Import Single Source of Truth engines from app.py
from app import (
    get_validated_range,
    calculate_status_engine,
    calculate_battle_engine,
    calculate_location_engine,
    calculate_breakout_readiness,
    generate_compact_evidence
)

def fetch_mexc_klines(symbol, timeframe="1h", limit=100):
    """
    Placeholder/Interface for fetching OHLCV + Taker Buy Volume data from API.
    """
    np.random.seed(42)
    closes = np.cumsum(np.random.randn(limit)) + 100.0
    highs = closes + np.abs(np.random.randn(limit)) * 0.5
    lows = closes - np.abs(np.random.randn(limit)) * 0.5
    volumes = np.random.rand(limit) * 1000.0 + 100.0
    taker_buy_volumes = volumes * (0.45 + np.random.rand(limit) * 0.1)

    return highs, lows, closes, volumes, taker_buy_volumes


def run_scanner_pipeline(symbols, timeframe="1h"):
    """
    Executes the multi-timeframe scanner pipeline across target symbols.
    Calculates sub-engine scores and passes all parameters to app.py.
    """
    results = []

    for symbol in symbols:
        try:
            highs, lows, closes, volumes, taker_buy_vols = fetch_mexc_klines(symbol, timeframe=timeframe)

            # 1. Validate Range Structure
            val_range = get_validated_range(highs, lows, closes, volumes)

            # 2. Execute Sub-Engines
            status = calculate_status_engine(highs, lows, closes, val_range)
            battle = calculate_battle_engine(volumes, taker_buy_volumes=taker_buy_vols)
            location = calculate_location_engine(closes, val_range)

            # 3. Approved Version 1.2.4 Invocation
            readiness = calculate_breakout_readiness(
                status_score=status["status_score"],
                battle_score=battle["battle_score"],
                location_score=location["location_score"],
                val_range=val_range,
                battle_label=battle["battle_label"],
                position_pct=location.get("position_pct", 50.0)
            )

            # 4. Generate Compact Evidence Text
            evidence_text = generate_compact_evidence(
                status, battle, location, readiness, val_range
            )

            curr_price = float(closes[-1])
            res_price = val_range["v_high"] if val_range else curr_price
            sup_price = val_range["v_low"] if val_range else curr_price
            range_size = val_range["r_height"] if val_range else 0.0
            dist_res_val = res_price - curr_price
            dist_sup_val = curr_price - sup_price
            dist_res_pct = round((dist_res_val / curr_price) * 100.0, 2) if curr_price > 0 else 0.0
            dist_sup_pct = round((dist_sup_val / curr_price) * 100.0, 2) if curr_price > 0 else 0.0

            results.append({
                "SYMBOL": symbol,
                "TIMEFRAME": timeframe,
                "STATUS": f"{status['status_label']} ({status['status_score']}%)",
                "BATTLE": battle['battle_label'],
                "LOCATION": location['location_label'],
                "BREAKOUT READINESS": f"{readiness['readiness_score']}% ({readiness['readiness_label']})",
                "READINESS_SCORE": readiness['readiness_score'],
                "DIRECTION": readiness.get("direction", "NEUTRAL"),
                "EVIDENCE": evidence_text,
                "CURRENT_PRICE": f"{curr_price:.4f}",
                "RES_PRICE": f"{res_price:.4f}",
                "SUP_PRICE": f"{sup_price:.4f}",
                "RANGE_SIZE": f"{range_size:.4f}",
                "DIST_RES": f"${dist_res_val:.4f} ({dist_res_pct}%)",
                "DIST_SUP": f"${dist_sup_val:.4f} ({dist_sup_pct}%)"
            })

        except Exception as e:
            results.append({
                "SYMBOL": symbol,
                "TIMEFRAME": timeframe,
                "STATUS": "ERROR",
                "BATTLE": "UNKNOWN",
                "LOCATION": "UNKNOWN",
                "BREAKOUT READINESS": "0% (LOW)",
                "READINESS_SCORE": 0,
                "DIRECTION": "NEUTRAL",
                "EVIDENCE": f"Pipeline Error: {str(e)}",
                "CURRENT_PRICE": "0.0000",
                "RES_PRICE": "0.0000",
                "SUP_PRICE": "0.0000",
                "RANGE_SIZE": "0.0000",
                "DIST_RES": "$0.0000 (0%)",
                "DIST_SUP": "$0.0000 (0%)"
            })

    results.sort(key=lambda x: x["READINESS_SCORE"], reverse=True)
    return results
