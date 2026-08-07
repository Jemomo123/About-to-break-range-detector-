import time
import threading
from flask import Flask, render_template, request, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
from scanner import _process_symbol_tf

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
SCAN_READY_TIMESTAMP = 0

def fetch_single_safe(sym, tf):
    try:
        match, err = _process_symbol_tf(sym, tf)
        if match:
            return match
        else:
            # Store placeholder for unavailable symbol
            return {
                "symbol": sym,
                "timeframe": tf,
                "curr_close": "Unavailable",
                "support": "N/A",
                "resistance": "N/A",
                "structure_type": "N/A",
                "direction_label": "Unavailable",
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
        print(f"Fetch error for {sym} {tf}: {e}")
        return None

def update_cache_job():
    global SCAN_READY, SCAN_READY_TIMESTAMP
    print(">>> Background cache worker started.")
    cycle_completed = False
    
    while True:
        try:
            for tf in ["5M", "15M", "1H", "4H"]:
                print(f">>> Scanning batch: {tf}")
                tasks = [sym for sym in DEFAULT_WATCHLIST]
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_map = {executor.submit(fetch_single_safe, sym, tf): sym for sym in tasks}
                    for future in as_completed(future_map):
                        sym = future_map[future]
                        res = future.result()
                        if res:
                            with CACHE_LOCK:
                                CACHE[f"{sym}_{tf}"] = res
                                print(f"[CACHE] Stored {sym} {tf} (Score: {res.get('readiness_score')})")
                print(f">>> Finished batch: {tf}. Sleeping 2s...")
                time.sleep(2)
            
            # Mark first cycle complete
            if not cycle_completed:
                cycle_completed = True
                SCAN_READY = True
                SCAN_READY_TIMESTAMP = time.time()
                print(">>> FIRST SCAN CYCLE COMPLETE. Scanner is now READY.")
            
            print(">>> Full cycle complete. Sleeping 15s...")
            time.sleep(15)
        except Exception as e:
            print(f"!!! Worker exception: {e}")
            # If worker crashes, restart it by continuing the loop
            time.sleep(5)

@app.before_request
def start_background_worker():
    global _worker_thread_started, SCAN_READY
    if not _worker_thread_started:
        thread = threading.Thread(target=update_cache_job, daemon=True)
        thread.start()
        _worker_thread_started = True
        print(">>> Background worker thread launched.")
        # Set a safety timeout: if SCAN_READY isn't true after 30 seconds, force it
        def safety_timer():
            global SCAN_READY
            time.sleep(30)
            if not SCAN_READY:
                SCAN_READY = True
                print(">>> SAFETY TIMEOUT: SCAN_READY forced to True.")
        timer_thread = threading.Thread(target=safety_timer, daemon=True)
        timer_thread.start()

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

    watchlist_rows = []
    is_loading = not SCAN_READY

    with CACHE_LOCK:
        for item in WATCHLIST:
            key = f"{item['symbol']}_{active_tf}"
            if key in CACHE:
                match = dict(CACHE[key])
                match["pinned"] = item["pinned"]
                watchlist_rows.append(match)
            else:
                # If SCAN_READY is True but symbol missing, show as loading
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

    scanner_results = [
        r for r in watchlist_rows 
        if isinstance(r.get("readiness_score"), (int, float)) and r["readiness_score"] >= 40
    ]
    scanner_results = sort_results(scanner_results)

    return render_template(
        "index.html",
        selected_tf=selected_tf,
        watchlist_rows=watchlist_rows,
        rows=scanner_results,
        is_loading=is_loading
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
