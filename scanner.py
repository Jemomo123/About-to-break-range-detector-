# scanner.py
from datetime import datetime, timezone
from config import SUPPORTED_TIMEFRAMES, DEFAULT_WATCHLIST
from detector import (
    fetch_market_candles,
    validate_range_structure,
    analyze_buyer_seller_battle,
    calculate_breakout_readiness
)

def run_scanner_pipeline(watchlist=None, selected_tf=None):
    """
    Scans Watchlist across 5M, 15M, and 1H.
    If selected_tf is passed, filters results while maintaining timeframe identities.
    """
    if watchlist is None:
        watchlist = DEFAULT_WATCHLIST

    results = []
    qualified_count = 0
    rejected_count = 0
    api_failures_count = 0
    scanned_total = 0
    scan_timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    # Determine timeframes to process (Only 5M, 15M, 1H allowed)
    target_tfs = [selected_tf] if selected_tf in SUPPORTED_TIMEFRAMES else SUPPORTED_TIMEFRAMES

    for symbol in watchlist:
        for tf in target_tfs:
            scanned_total += 1
            data, exchange_used, failure_reason = fetch_market_candles(symbol, tf)
            
            if data is None:
                api_failures_count += 1
                continue

            highs, lows, closes, volumes = data

            # Stage 1: Range Validation
            range_data = validate_range_structure(highs, lows, closes)
            if range_data is None:
                rejected_count += 1
                continue

            # Stage 2 & 3: Battle + Readiness Calculation
            battle_data = analyze_buyer_seller_battle(range_data, volumes, closes)
            readiness_data = calculate_breakout_readiness(range_data, battle_data)

            record = {
                "symbol": symbol,
                "timeframe": tf,  # <--- Timeframe identity preserved through all stages
                "structure_type": range_data["structure_type"],
                "readiness_score": readiness_data["readiness_score"],
                "readiness_label": readiness_data["readiness_label"],
                "readiness_display": readiness_data["readiness_display"],
                "direction": battle_data["direction"],
                "resistance": range_data["resistance"],
                "support": range_data["support"],
                "distance": readiness_data["distance_pct"],
                
                # Extended details
                "curr_close": range_data["curr_close"],
                "range_height": range_data["r_height"],
                "range_height_pct": range_data["r_height_pct"],
                "price_position": battle_data["price_position"],
                "buyer_power": battle_data["buyer_power"],
                "seller_power": battle_data["seller_power"],
                "range_quality": range_data["range_quality"],
                "interpretation": battle_data["interpretation"],
                "exchange": exchange_used
            }

            results.append(record)
            qualified_count += 1

    # Sort results by Readiness Score (Highest First)
    results.sort(key=lambda x: x["readiness_score"], reverse=True)

    diagnostics = {
        "watchlist_total": len(watchlist),
        "scanned": scanned_total,
        "qualified": qualified_count,
        "rejected": rejected_count,
        "api_failures": api_failures_count,
        "scan_timestamp": scan_timestamp
    }

    return results, diagnostics
