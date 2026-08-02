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
    Placeholder/Interface for fetching OHLCV + Taker Buy Volume data from MEXC API.
    Returns simulated/mocked arrays for testing if real API stream is offline.
    """
    # Highs, Lows, Closes, Volumes, Taker Buy Volumes
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

            results.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "status_score": status["status_score"],
                "status_label": status["status_label"],
                "battle_score": round(battle["battle_score"], 1),
                "battle_label": battle["battle_label"],
                "location_score": location["location_score"],
                "location_label": location["location_label"],
                "position_pct": location.get("position_pct", 50.0),
                "readiness_score": readiness["readiness_score"],
                "readiness_label": readiness["readiness_label"],
                "direction": readiness.get("direction", "NEUTRAL"),
                "evidence": evidence_text
            })

        except Exception as e:
            # Safe Fallback per Symbol
            results.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "status_score": 0,
                "status_label": "ERROR",
                "battle_score": 50.0,
                "battle_label": "UNKNOWN",
                "location_score": 50,
                "location_label": "UNKNOWN",
                "position_pct": 50.0,
                "readiness_score": 0,
                "readiness_label": "LOW",
                "direction": "NEUTRAL",
                "evidence": f"Pipeline Error: {str(e)}"
            })

    return results
