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

def fetch_single_safe(sym, tf):
    try:
        match, _ = _process_symbol_tf(sym, tf)
        return match
    except Exception as e:
        print(f"Fetch error for {sym} {tf}: {e}")
        return None

def update_cache_job():
    print(">>> Background cache worker started in this process.")
    while True:
        for tf in ["5M", "15M", "1H", "4H"]:
            tasks = [sym for sym in DEFAULT_WATCHLIST]
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_map = {executor.submit(fetch_single_safe, sym, tf): sym for sym in tasks}
                for future in as_completed(future_map):
                    sym = future_map[future]
                    res = future.result()
                    if res:
                        with CACHE_LOCK:
                            CACHE[f"{sym}_{tf}"] = res
            time.sleep(2)
        time.sleep(15)

@app.before_request
def start_background_worker():
    global _worker_thread_started
    if not _worker_thread_started:
        thread = threading.Thread(target=update_cache_job, daemon=True)
        thread.start()
        _worker_thread_started = True
        print(">>> Background worker thread launched by web request.")

def sort_results(items):
    """Sort by: Readiness DESC, then Timeframe priority (5M > 15M > 1H > 4H)."""
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
    is_loading = False

    with CACHE_LOCK:
        for item in WATCHLIST:
            key = f"{item['symbol']}_{active_tf}"
            if key in CACHE:
                match = dict(CACHE[key])
                match["pinned"] = item["pinned"]
                watchlist_rows.append(match)
            else:
                is_loading = True
                watchlist_rows.append({
                    "symbol": item["symbol"],
                    "timeframe": active_tf,
                    "curr_close": "Loading...",
                    "support": "...",
                    "resistance": "...",
                    "direction_label": "Fetching...",
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
