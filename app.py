import time
import threading
from flask import Flask, render_template, request, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
from scanner import _process_symbol_tf

app = Flask(__name__)

# YOUR EXACT 25 WATCHLIST TICKERS
DEFAULT_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT", "BONKUSDT", 
    "SHIBUSDT", "USELESSUSDT", "SPACEUSDT", "MOVEUSDT", "ZECUSDT", 
    "SPXUSDT", "PEOPLEUSDT", "PENGUUSDT", "FARTCOINUSDT", "LINEAUSDT", 
    "MEMEUSDT", "PUMPUSDT", "AIXBTUSDT", "BRETTUSDT", "FOGOUSDT", 
    "GOOGLUSDT", "FLOKIUSDT", "IWMUSDT", "MOODENGUSDT", "NEARUSDT"
]

WATCHLIST = [{"symbol": sym, "timeframe": "15M", "pinned": False} for sym in DEFAULT_WATCHLIST]

# IN-MEMORY CACHE FOR INSTANT PAGE LOADS
CACHE = {}
CACHE_LOCK = threading.Lock()
LAST_UPDATE = 0

def update_cache():
    global LAST_UPDATE
    print("Background Worker: Fetching latest market data...")
    timeframes = ["5M", "15M", "1H", "4H"]
    tasks = [(sym, tf) for sym in DEFAULT_WATCHLIST for tf in timeframes]
    
    new_data = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {executor.submit(_process_symbol_tf, sym, tf): (sym, tf) for sym, tf in tasks}
        for future in as_completed(future_map):
            sym, tf = future_map[future]
            try:
                match, _ = future.result()
                if match:
                    new_data[f"{sym}_{tf}"] = match
            except Exception:
                pass

    with CACHE_LOCK:
        CACHE.update(new_data)
        LAST_UPDATE = time.time()
    print("Background Worker: Cache update complete!")

def background_loop():
    # Initial pause to let Flask initialize
    time.sleep(2)
    while True:
        try:
            update_cache()
        except Exception as e:
            print(f"Background loop error: {e}")
        time.sleep(30)  # Refresh exchange data every 30 seconds

# Start Background Fetcher Thread on Launch
threading.Thread(target=background_loop, daemon=True).start()

@app.route("/")
def index():
    selected_tf = request.args.get("tf", "15M").upper()
    
    watchlist_rows = []
    with CACHE_LOCK:
        for item in WATCHLIST:
            tf = item["timeframe"] if selected_tf == "ALL" else selected_tf
            cache_key = f"{item['symbol']}_{tf}"
            if cache_key in CACHE:
                match = dict(CACHE[cache_key])
                match["pinned"] = item["pinned"]
                watchlist_rows.append(match)
            else:
                watchlist_rows.append({
                    "symbol": item["symbol"],
                    "timeframe": tf,
                    "curr_close": "Loading...",
                    "support": "...",
                    "resistance": "...",
                    "direction_label": "Updating Market Data",
                    "break_direction": "NEUTRAL",
                    "break_symbol": "⏳",
                    "readiness_display": "0%",
                    "buyer_power": 50.0,
                    "seller_power": 50.0,
                    "pinned": item["pinned"]
                })

    # Extract scanner opportunities from cache
    scanner_results = [
        r for r in watchlist_rows 
        if isinstance(r.get("readiness_score"), (int, float)) and r["readiness_score"] >= 40
    ]
    scanner_results.sort(key=lambda x: -x.get("readiness_score", 0))

    return render_template(
        "index.html",
        selected_tf=selected_tf,
        watchlist_rows=watchlist_rows,
        rows=scanner_results
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
