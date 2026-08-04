import sys
import traceback
from detector import detect_range, analyze_buyer_seller_battle, calculate_boundary_readiness

def run_scanner_pipeline(watchlist, target_tf=None):
    timeframes_to_scan = ["5M", "15M", "1H"] if not target_tf or target_tf == "ALL" else [target_tf]
    
    results = []
    diagnostics = {
        "symbols_downloaded": 0,
        "symbols_scanned": 0,
        "rejections": {},
        "matches": 0
    }

    print("\n==================================================", flush=True)
    print(f"[SCANNER START] Scanning {len(watchlist)} symbols across TFs: {timeframes_to_scan}", flush=True)
    print("==================================================", flush=True)

    for symbol in watchlist:
        for tf in timeframes_to_scan:
            diagnostics["symbols_scanned"] += 1
            
            # --- STEP 1: API DATA FETCH ---
            candles = fetch_klines(symbol, tf)  # Replace with your actual kline fetcher function
            
            if not candles or len(candles) < 20:
                reason = "FETCH_FAILED_OR_EMPTY"
                diagnostics["rejections"][reason] = diagnostics["rejections"].get(reason, 0) + 1
                print(f"[{symbol} | {tf}] REJECTED: Fetch failed or insufficient bars (Count: {len(candles) if candles else 0})", flush=True)
                continue

            diagnostics["symbols_downloaded"] += 1

            # --- STEP 2: STAGE 1 DETECTOR ---
            try:
                range_result = detect_range(candles, tf)
            except Exception as e:
                reason = "DETECTOR_EXCEPTION"
                diagnostics["rejections"][reason] = diagnostics["rejections"].get(reason, 0) + 1
                print(f"[{symbol} | {tf}] REJECTED: Exception during detect_range(): {e}", flush=True)
                continue

            if not range_result or not range_result.get("is_valid_range", False):
                reason = range_result.get("rejection_reason", "NO_RANGE_DETECTED") if isinstance(range_result, dict) else "NO_RANGE_DETECTED"
                diagnostics["rejections"][reason] = diagnostics["rejections"].get(reason, 0) + 1
                print(f"[{symbol} | {tf}] REJECTED Stage 1: Reason = '{reason}'", flush=True)
                continue

            # --- STEP 3: STAGE 2 FILTERING & METRICS ---
            curr_close = range_result.get("curr_close", candles[-1]["close"])
            support = range_result.get("support")
            resistance = range_result.get("resistance")

            if support is None or resistance is None or support >= resistance:
                reason = "INVALID_SUPPORT_RESISTANCE"
                diagnostics["rejections"][reason] = diagnostics["rejections"].get(reason, 0) + 1
                print(f"[{symbol} | {tf}] REJECTED Stage 2: Invalid S/R levels (Supp: {support}, Res: {resistance})", flush=True)
                continue

            # Calculate readiness & order flow
            readiness_score, readiness_label = calculate_boundary_readiness(curr_close, support, resistance)
            
            # Extract volumes and closes for order flow battle
            volumes = [c.get("volume", 0) for c in candles]
            closes = [c.get("close", 0) for c in candles]
            battle = analyze_buyer_seller_battle(range_result, volumes, closes)

            # Match Candidate
            match = {
                "symbol": symbol,
                "timeframe": tf,
                "structure_type": range_result.get("structure_type", "HORIZONTAL"),
                "curr_close": curr_close,
                "support": support,
                "resistance": resistance,
                "readiness_score": readiness_score,
                "readiness_display": readiness_label,
                "buyer_power": battle.get("buyer_power", 50),
                "seller_power": battle.get("seller_power", 50)
            }
            
            results.append(match)
            print(f"[{symbol} | {tf}] >>> MATCH ACCEPTED <<< (Readiness: {readiness_score}%, Structure: {match['structure_type']})", flush=True)

    diagnostics["matches"] = len(results)
    print("==================================================", flush=True)
    print(f"[SCANNER COMPLETE] Total Matches: {len(results)} | Summary: {diagnostics['rejections']}", flush=True)
    print("==================================================\n", flush=True)

    return results, diagnostics
