# scanner.py
# =====================================================================
# VERSION 1.0 — ORCHESTRATION LAYER
# =====================================================================

from binance_data import fetch_binance_futures_klines
from coinalyze import fetch_open_interest
from app import (
    get_validated_range,
    calculate_status_engine,
    calculate_battle_engine,
    calculate_location_engine,
    calculate_breakout_readiness,
    generate_compact_evidence,
    TARGET_SYMBOLS,
    DEFAULT_TIMEFRAME
)

def run_scanner_pipeline():
    """
    Pure orchestration function.
    Performs ZERO scoring, range boundary, or market control calculations.
    Strict execution sequence:
    Fetch Data -> Validated Range -> Status -> Battle -> Location -> Readiness -> Evidence -> Reporting Table
    """
    rows = []

    for sym in TARGET_SYMBOLS:
        # 1. Fetch Market Data
        kline_data = fetch_binance_futures_klines(sym, interval=DEFAULT_TIMEFRAME, limit=100)
        if kline_data is None:
            continue

        oi_data = fetch_open_interest(sym)

        # 2. Single Source of Truth: Validated Range (app.py)
        val_range = get_validated_range(
            kline_data["highs"], 
            kline_data["lows"], 
            kline_data["closes"], 
            kline_data["volumes"]
        )

        # 3. Status Engine (app.py)
        status = calculate_status_engine(
            kline_data["highs"], 
            kline_data["lows"], 
            kline_data["closes"], 
            val_range
        )

        # 4. Battle Engine (app.py)
        battle = calculate_battle_engine(
            volumes=kline_data["volumes"],
            taker_buy_volumes=kline_data.get("taker_buy_volumes"),
            open_interest=oi_data,
            funding_rates=None
        )

        # 5. Location Engine (app.py)
        location = calculate_location_engine(
            kline_data["closes"], 
            val_range
        )

        # 6. Breakout Readiness Engine (app.py)
        readiness = calculate_breakout_readiness(
            status["status_score"], 
            battle["battle_score"], 
            location["location_score"], 
            val_range
        )

        # 7. Evidence Engine (app.py)
        evidence = generate_compact_evidence(
            status, 
            battle, 
            location, 
            readiness, 
            val_range
        )

        # 8. Output Formatting (Mapped to 7-Column Layout)
        rows.append({
            "SYMBOL": sym,
            "TIMEFRAME": DEFAULT_TIMEFRAME,
            "STATUS": f"{status['status_label']} ({status['status_score']})",
            "BATTLE": f"{battle['battle_label']} ({battle['battle_score']})",
            "LOCATION": f"{location['location_label']} ({location['position_pct']}%)",
            "BREAKOUT READINESS": f"{readiness['readiness_score']} {readiness['readiness_label']}",
            "EVIDENCE": evidence,
            "_s_readiness": readiness["readiness_score"],
            "_s_status": status["status_score"],
            "_s_battle": battle["battle_score"]
        })

    # Sort Table: Primary (Breakout Readiness) -> Secondary (Status) -> Tertiary (Battle)
    return sorted(rows, key=lambda x: (x["_s_readiness"], x["_s_status"], x["_s_battle"]), reverse=True)
