# scanner.py
from datetime import datetime, timezone
from detector import (
    fetch_market_candles,
    validate_range_structure,
    analyze_buyer_seller_battle,
    calculate_breakout_readiness
)

def run_scanner_pipeline(watchlist, timeframe):
    """
    Runs full backend processing pipeline according to Spec Version 2.0.
    """
    results = []
    qualified_count = 0
    rejected_count = 0
    api_failures_count = 0
    scan_timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    for symbol in watchlist:
        # Step 1: Fetch OHLC Data
        data, exchange_used, failure_reason = fetch_market_candles(symbol, timeframe)
        
        if data is None:
            api_failures_count += 1
            continue

        highs, lows, closes, volumes = data

        # Step 1, 2 & 3: Detect & Validate Range (Reject immediately if invalid)
        range_data = validate_range_structure(highs, lows, closes)
        if range_data is None:
            rejected_count += 1
            continue

        # Step 4: Calculate Battle, Direction, & Readiness ONLY for valid ranges
        battle_data = analyze_buyer_seller_battle(range_data, volumes, closes)
        readiness_data = calculate_breakout_readiness(range_data, battle_data)

        # Assemble Final Response Record
        record = {
            "symbol": symbol,
            "readiness_score": readiness_data["readiness_score"],
            "readiness_label": readiness_data["readiness_label"],
            "readiness_display": readiness_data["readiness_display"],
            "direction": battle_data["direction"],
            "resistance": range_data["resistance"],
            "support": range_data["support"],
            "distance": readiness_data["distance_pct"],
            
            # Additional detail parameters for drill-down view
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

    # Sort Dashboard Results by Breakout Readiness Score (Highest First)
    results.sort(key=lambda x: x["readiness_score"], reverse=True)

    diagnostics = {
        "watchlist_total": len(watchlist),
        "scanned": qualified_count + rejected_count,
        "qualified": qualified_count,
        "rejected": rejected_count,
        "api_failures": api_failures_count,
        "scan_timestamp": scan_timestamp
    }

    return results, diagnostics
