from flask import Flask, render_template, request, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
from scanner import run_scanner_pipeline, _process_symbol_tf

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

@app.route("/")
def index():
    # Default to 15M to prevent Render timeout and API rate limits
    selected_tf = request.args.get("tf", "15M").upper()
    
    watchlist_rows = []
    tasks = [(item, item["timeframe"] if selected_tf == "ALL" else selected_tf) for item in WATCHLIST]

    # Fetch Watchlist Data safely
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {executor.submit(_process_symbol_tf, item["symbol"], tf): (item, tf) for item, tf in tasks}
        
        for future in as_completed(future_map):
            item, tf = future_map[future]
            try:
                # If an exchange fails, catch the error so it doesn't crash the app
                match, _ = future.result()
            except Exception as e:
                print(f"Exchange error for {item['symbol']}: {e}")
                match = None

            if match:
                match["pinned"] = item["pinned"]
                watchlist_rows.append(match)
            else:
                watchlist_rows.append({
                    "symbol": item["symbol"],
                    "timeframe": tf,
                    "curr_close": "ERROR",
                    "support": "N/A",
                    "resistance": "N/A",
                    "direction_label": "API Blocked",
                    "break_direction": "NEUTRAL",
                    "break_symbol": "⚠️",
                    "readiness_display": "0%",
                    "buyer_power": 50.0,
                    "seller_power": 50.0,
                    "pinned": item["pinned"]
                })

    # Restore correct watchlist order
    symbol_order = {sym: i for i, sym in enumerate(DEFAULT_WATCHLIST)}
    watchlist_rows.sort(key=lambda x: symbol_order.get(x["symbol"], 999))

    # Safely fetch scanner data
    try:
        scanner_results, _ = run_scanner_pipeline(DEFAULT_WATCHLIST, selected_tf)
    except Exception as e:
        print(f"Scanner crash caught: {e}")
        scanner_results = []

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
