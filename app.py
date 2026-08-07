import time
import threading
from flask import Flask, render_template, request, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
from scanner import _process_symbol_tf
from datetime import datetime, timezone

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

# Live status tracking
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
            print(f"[CACHE] ✅ {sym} {tf} - Storing (Score: {match.get('readiness_score')}%)")
            return match
        else:
            print(f"[CACHE] ❌ {sym} {tf} - Unsupported ({err})")
            return {
                "symbol": sym,
                "timeframe": tf,
                "curr_close": "Unsupported",
                "support": "N/A",
                "resistance": "N/A",
                "structure_type": "N/A",
                "direction_label": "Unsupported",
                "break_direction": "NEUTRAL",
                "break_symbol": "⏳",
                "readiness_score": 0,
                "readiness_display": "0%",
                "buyer_power": 0.0,
                "seller_power": 0.0,
                "distance_to_resistance": 0.0,
                "distance_to_support": 0.0,
                "volume_trend": "N/A",
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
                with ThreadPoolExecutor(max_workers=5) as executor:
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
                time.sleep(2)
            
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

@app.route("/")
def index():
    selected_tf = request.args.get("tf", "15M").upper()
    active_tf = "15M" if selected_tf == "ALL" else selected_tf

    print(f"[ROUTE] Selected TF: {selected_tf}, Active TF: {active_tf}")
    print(f"[ROUTE] SCAN_READY: {SCAN_READY}, CACHE size: {len(CACHE)}")
    
    if len(CACHE) > 0:
        # Log a sample of what's in the cache
        sample_keys = list(CACHE.keys())[:3]
        for key in sample_keys:
            val = CACHE[key]
            print(f"[ROUTE] Cache sample: {key} -> Score: {val.get('readiness_score', 'N/A')}%")

    watchlist_rows = []
    is_loading = not SCAN_READY

    with CACHE_LOCK:
        for item in WATCHLIST:
            key = f"{item['symbol']}_{active_tf}"
            if key in CACHE:
                match = dict(CACHE[key])
                match["pinned"] = item["pinned"]
                watchlist_rows.append(match)
                print(f"[ROUTE] Found in cache: {key}")
            else:
                print(f"[ROUTE] NOT in cache: {key}")
                watchlist_rows.append({
                    "symbol": item["symbol"],
                    "timeframe": active_tf,
                    "curr_close": "Loading..." if not SCAN_READY else "Unavailable",
                    "support": "...",
                    "resistance": "...",
                    "direction_label": "Fetching..." if not SCAN_READY else "Unavailable",
                    "break_direction": "NEUTRAL",
                    "break_symbol": "⏳",
                    "readiness_score": 0,
                    "readiness_display": "0%",
                    "buyer_power": 50.0,
                    "seller_power": 50.0,
                    "pinned": item["pinned"],
                    "distance_to_resistance": 0.0,
                    "distance_to_support": 0.0,
                    "volume_trend": "Neutral",
                    "last_updated": "--:--:-- UTC"
                })

    watchlist_rows = sort_results(watchlist_rows)

    # Show ALL symbols with their actual scores
    scanner_results = watchlist_rows.copy()
    scanner_results = sort_results(scanner_results)
    
    active_results = [r for r in scanner_results if r.get("readiness_score", 0) > 0]
    print(f"[ROUTE] Total results: {len(scanner_results)}, Active (score>0): {len(active_results)}")

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
