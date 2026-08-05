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

CACHE = {}
CACHE_LOCK = threading.Lock()

def fetch_single_safe(sym, tf):
    try:
        match, _ = _process_symbol_tf(sym, tf)
        return match
    except Exception as e:
        print(f"Error fetching {sym} {tf}: {e}")
        return None

def bg_update_tf(tf):
    tasks = [sym for sym in DEFAULT_WATCHLIST]
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {executor.submit(fetch_single_safe, sym, tf): sym for sym in tasks}
        for future in as_completed(future_map):
            sym = future_map[future]
            res = future.result()
            if res:
                with CACHE_LOCK:
                    CACHE[f"{sym}_{tf}"] = res

def background_worker():
    time.sleep(1)
    while True:
        for tf in ["15M", "5M", "1H", "4H"]:
            try:
                bg_update_tf(tf)
            except Exception as e:
                print(f"BG worker loop error: {e}")
            time.sleep(2)
        time.sleep(20)

# Start background auto-refresh thread
threading.Thread(target=background_worker, daemon=True).start()

@app.route("/")
def index():
    selected_tf = request.args.get("tf", "15M").upper()
    active_tf = "15M" if selected_tf == "ALL" else selected_tf

    # Identify missing symbols in CACHE for requested TF
    missing_symbols = []
    with CACHE_LOCK:
        for item in WATCHLIST:
            key = f"{item['symbol']}_{active_tf}"
            if key not in CACHE:
                missing_symbols.append(item["symbol"])

    # On-demand fast fetch for missing cache (takes ~1.5s)
    if missing_symbols:
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_map = {executor.submit(fetch_single_safe, sym, active_tf): sym for sym in missing_symbols}
            for future in as_completed(future_map):
                sym = future_map[future]
                res = future.result()
                if res:
                    with CACHE_LOCK:
                        CACHE[f"{sym}_{active_tf}"] = res

    watchlist_rows = []
    is_still_loading = False

    with CACHE_LOCK:
        for item in WATCHLIST:
            cache_key = f"{item['symbol']}_{active_tf}"
            if cache_key in CACHE:
                match = dict(CACHE[cache_key])
                match["pinned"] = item["pinned"]
                watchlist_rows.append(match)
            else:
                is_still_loading = True
                watchlist_rows.append({
                    "symbol": item["symbol"],
                    "timeframe": active_tf,
                    "curr_close": "N/A",
                    "support": "N/A",
                    "resistance": "N/A",
                    "direction_label": "Fetching...",
                    "break_direction": "NEUTRAL",
                    "break_symbol": "⏳",
                    "readiness_display": "0%",
                    "buyer_power": 50.0,
                    "seller_power": 50.0,
                    "pinned": item["pinned"]
                })

    # Restore default symbol ordering
    symbol_order = {sym: i for i, sym in enumerate(DEFAULT_WATCHLIST)}
    watchlist_rows.sort(key=lambda x: symbol_order.get(x["symbol"], 999))

    # Scanner results filtered from active candidates
    scanner_results = [
        r for r in watchlist_rows 
        if isinstance(r.get("readiness_score"), (int, float)) and r["readiness_score"] >= 40
    ]
    scanner_results.sort(key=lambda x: -x.get("readiness_score", 0))

    return render_template(
        "index.html",
        selected_tf=selected_tf,
        watchlist_rows=watchlist_rows,
        rows=scanner_results,
        is_still_loading=is_still_loading
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
