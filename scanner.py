import time
import threading
from flask import Flask, render_template, request, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
from scanner import _process_symbol_tf
from datetime import datetime, timezone
from collections import defaultdict

app = Flask(__name__)

DEFAULT_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT", "BONKUSDT", 
    "SHIBUSDT", "USELESSUSDT", "SPACEUSDT", "MOVEUSDT", "ZECUSDT", 
    "SPXUSDT", "PEOPLEUSDT", "PENGUUSDT", "FARTCOINUSDT", "LINEAUSDT", 
    "MEMEUSDT", "PUMPUSDT", "AIXBTUSDT", "BRETTUSDT", "FOGOUSDT", 
    "GOOGLUSDT", "FLOKIUSDT", "IWMUSDT", "MOODENGUSDT", "NEARUSDT"
]

WATCHLIST = [{"symbol": sym, "timeframe": "15M", "pinned": False} for sym in DEFAULT_WATCHLIST]

CACHE = {}
CACHE_LOCK = threading.Lock()
_worker_thread_started = False
SCAN_READY = False

scan_status = {
    "state": "INITIALIZING",
    "current_symbol": "",
    "current_timeframe": "",
    "last_update": "",
    "symbols_scanned": 0,
    "total_symbols": len(DEFAULT_WATCHLIST),
    "recently_scanned": [],
    "cache_size": 0
}

def fetch_single_safe(sym, tf):
    global scan_status
    try:
        scan_status["current_symbol"] = sym
        scan_status["current_timeframe"] = tf
        match, err = _process_symbol_tf(sym, tf)
        if match:
            print(f"[CACHE] ✅ {sym} {tf} - Score: {match.get('readiness_score')}%")
            return match
        else:
            print(f"[CACHE] ❌ {sym} {tf} - Unsupported ({err})")
            return {
                "symbol": sym,
                "timeframe": tf,
                "curr_close": "Unsupported",
                "support": "N/A",
                "resistance": "N/A",
                "range_width": 0.0,
                "pattern_type": "N/A",
                "direction_label": "Unsupported",
                "break_direction": "NEUTRAL",
                "break_symbol": "⏳",
                "readiness_score": 0,
                "readiness_display": "0%",
                "distance_to_resistance": 0.0,
                "distance_to_support": 0.0,
                "volume_label": "N/A",
                "confidence": "N/A",
                "status_label": "N/A",
                "touches": 0,
                "last_updated": "--:--:-- UTC"
            }
    except Exception as e:
        print(f"[CACHE] ⚠️ {sym} {tf} - Exception: {e}")
        return None

def update_cache_job():
    global SCAN_READY, scan_status
    print(">>> BACKGROUND SCANNER STARTED")
    scan_status["state"] = "SCANNING"
    first_data_received = False
    scanned_in_cycle = []
    
    while True:
        try:
            for tf in ["5M", "15M", "1H", "4H"]:
                print(f">>> Scanning {tf}...")
                scan_status["current_timeframe"] = tf
                tasks = [sym for sym in DEFAULT_WATCHLIST]
                with ThreadPoolExecutor(max_workers=10) as executor:
                    future_map = {executor.submit(fetch_single_safe, sym, tf): sym for sym in tasks}
                    for future in as_completed(future_map):
                        sym = future_map[future]
                        res = future.result()
                        if res:
                            with CACHE_LOCK:
                                CACHE[f"{sym}_{tf}"] = res
                                scan_status["symbols_scanned"] += 1
                                scan_status["current_symbol"] = sym
                                scan_status["last_update"] = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                                scan_status["cache_size"] = len(CACHE)
                                
                                scanned_in_cycle.append(sym)
                                if len(scanned_in_cycle) > 10:
                                    scanned_in_cycle.pop(0)
                                scan_status["recently_scanned"] = scanned_in_cycle.copy()
                                
                                if not first_data_received:
                                    first_data_received = True
                                    SCAN_READY = True
                                    scan_status["state"] = "LIVE"
                                    print(f">>> SCAN_READY = True (first data: {sym} {tf})")
                                print(f"[CACHE] Stored {sym} {tf} (Cache size: {len(CACHE)})")
                print(f">>> Completed {tf}")
                time.sleep(1)  # faster cycle
            
            print(">>> Cycle complete. Sleeping 15s...")
            time.sleep(15)
        except Exception as e:
            print(f"!!! Worker exception: {e}")
            time.sleep(5)

@app.before_request
def start_background_worker():
    global _worker_thread_started
    if not _worker_thread_started:
        thread = threading.Thread(target=update_cache_job, daemon=True)
        thread.start()
        _worker_thread_started = True
        print(">>> Background worker thread launched.")

def sort_results(items):
    tf_priority = {"5M": 0, "15M": 1, "1H": 2, "4H": 3}
    def sort_key(item):
        readiness = item.get("readiness_score", 0)
        tf = item.get("timeframe", "15M")
        if readiness is None or not isinstance(readiness, (int, float)):
            readiness = -1
        return (-readiness, tf_priority.get(tf, 99))
    return sorted(items, key=sort_key)

def generate_alignment_explanation(symbol, active_tf):
    # (unchanged from previous version – kept for completeness)
    tf_scores = {}
    for tf in ["5M", "15M", "1H"]:
        key = f"{symbol}_{tf}"
        if key in CACHE:
            cached = CACHE[key]
            if cached.get("break_direction") in ["BULLISH", "BEARISH"]:
                tf_scores[tf] = {
                    "direction": cached["break_direction"],
                    "readiness": cached.get("readiness_score", 0)
                }
    if len(tf_scores) < 2:
        return "Insufficient data for alignment analysis."
    directions = [v["direction"] for v in tf_scores.values() if v["direction"] in ["BULLISH", "BEARISH"]]
    bullish_count = directions.count("BULLISH")
    bearish_count = directions.count("BEARISH")
    total_tfs = len(tf_scores)
    if bullish_count > bearish_count:
        primary = "▲ BULLISH"
        reasons = ["✓ Trend is Up"]
        key = f"{symbol}_{active_tf}"
        if key in CACHE and CACHE[key].get("distance_to_resistance", 100) < 3.0:
            reasons.append("✓ Price is Near Resistance")
        if "1H" in tf_scores and tf_scores["1H"]["direction"] == "BULLISH":
            reasons.append("✓ Momentum is Bullish")
        elif "15M" in tf_scores and tf_scores["15M"]["direction"] == "BULLISH":
            reasons.append("✓ Momentum is Bullish")
        else:
            reasons.append("○ Momentum is Building")
    elif bearish_count > bullish_count:
        primary = "▼ BEARISH"
        reasons = ["✓ Trend is Down"]
        key = f"{symbol}_{active_tf}"
        if key in CACHE and CACHE[key].get("distance_to_support", 100) < 3.0:
            reasons.append("✓ Price is Near Support")
        if "1H" in tf_scores and tf_scores["1H"]["direction"] == "BEARISH":
            reasons.append("✓ Momentum is Bearish")
        elif "15M" in tf_scores and tf_scores["15M"]["direction"] == "BEARISH":
            reasons.append("✓ Momentum is Bearish")
        else:
            reasons.append("○ Momentum is Building")
    else:
        primary = "● MIXED"
        reasons = []
        if bullish_count > 0:
            reasons.append(f"✓ {bullish_count} timeframe(s) Bullish")
        if bearish_count > 0:
            reasons.append(f"✓ {bearish_count} timeframe(s) Bearish")
        key = f"{symbol}_{active_tf}"
        if key in CACHE:
            if CACHE[key].get("distance_to_resistance", 100) < 3.0:
                reasons.append("✓ Price is Near Resistance")
            if CACHE[key].get("distance_to_support", 100) < 3.0:
                reasons.append("✓ Price is Near Support")
    summary = f"Alignment: {bullish_count}/{total_tfs} Bullish, {bearish_count}/{total_tfs} Bearish"
    display_lines = [primary] + reasons + [summary]
    return "\n".join(display_lines)

@app.route("/")
def index():
    selected_tf = request.args.get("tf", "15M").upper()
    active_tf = "15M" if selected_tf == "ALL" else selected_tf

    print(f"[ROUTE] Selected TF: {selected_tf}, Active TF: {active_tf}")
    print(f"[ROUTE] SCAN_READY: {SCAN_READY}, CACHE size: {len(CACHE)}")

    watchlist_rows = []
    is_loading = not SCAN_READY

    with CACHE_LOCK:
        # --- Build watchlist rows for the active timeframe (for watchlist display) ---
        for item in WATCHLIST:
            key = f"{item['symbol']}_{active_tf}"
            if key in CACHE:
                match = dict(CACHE[key])
                match["pinned"] = item["pinned"]
                match["alignment_explanation"] = generate_alignment_explanation(item["symbol"], active_tf)
                watchlist_rows.append(match)
            else:
                watchlist_rows.append({
                    "symbol": item["symbol"],
                    "timeframe": active_tf,
                    "curr_close": "Loading..." if not SCAN_READY else "Unavailable",
                    "support": "...",
                    "resistance": "...",
                    "range_width": 0.0,
                    "pattern_type": "N/A",
                    "direction_label": "Fetching..." if not SCAN_READY else "Unavailable",
                    "break_direction": "NEUTRAL",
                    "break_symbol": "⏳",
                    "readiness_score": 0,
                    "readiness_display": "0%",
                    "distance_to_resistance": 0.0,
                    "distance_to_support": 0.0,
                    "volume_label": "N/A",
                    "confidence": "N/A",
                    "status_label": "N/A",
                    "touches": 0,
                    "pinned": item["pinned"],
                    "last_updated": "--:--:-- UTC",
                    "alignment_explanation": "Waiting for data..."
                })

    watchlist_rows = sort_results(watchlist_rows)

    # --- Build scanner results ---
    if selected_tf == "ALL":
        # Aggregate all timeframes
        all_results = []
        for key, data in CACHE.items():
            # key format: "SYMBOL_TF"
            parts = key.rsplit("_", 1)
            if len(parts) == 2:
                sym, tf = parts[0], parts[1]
                if tf in ["5M", "15M", "1H", "4H"]:
                    # Only include if score > 0
                    if data.get("readiness_score", 0) > 0:
                        entry = dict(data)
                        entry["pinned"] = any(w["symbol"] == sym and w["pinned"] for w in WATCHLIST)
                        all_results.append(entry)
        scanner_results = sort_results(all_results)
    else:
        # Specific timeframe: use watchlist_rows but filter those with score > 0
        scanner_results = [r for r in watchlist_rows if r.get("readiness_score", 0) > 0]
        scanner_results = sort_results(scanner_results)

    print(f"[ROUTE] Total results: {len(scanner_results)}")

    return render_template(
        "index.html",
        selected_tf=selected_tf,
        watchlist_rows=watchlist_rows,
        rows=scanner_results,
        is_loading=is_loading,
        scan_status=scan_status
    )

@app.route("/api/watchlist/add", methods=["POST"])
def add_watchlist():
    data = request.json or {}
    sym = data.get("symbol", "").upper().strip()
    tf = data.get("timeframe", "15M")
    if sym and not any(w["symbol"] == sym for w in WATCHLIST):
        WATCHLIST.append({"symbol": sym, "timeframe": tf, "pinned": False})
    return jsonify({"status": "ok"})

@app.route("/api/watchlist/remove", methods=["POST"])
def remove_watchlist():
    data = request.json or {}
    sym = data.get("symbol", "").upper().strip()
    global WATCHLIST
    WATCHLIST = [w for w in WATCHLIST if w["symbol"] != sym]
    return jsonify({"status": "ok"})

@app.route("/api/watchlist/pin", methods=["POST"])
def pin_watchlist():
    data = request.json or {}
    sym = data.get("symbol", "").upper().strip()
    for w in WATCHLIST:
        if w["symbol"] == sym:
            w["pinned"] = not w["pinned"]
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
