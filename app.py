from flask import Flask, render_template, request, jsonify
from scanner import run_scanner_pipeline, _process_symbol_tf

app = Flask(__name__)

# YOUR EXACT 25 WATCHLIST TICKERS
DEFAULT_WATCHLIST = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "PEPEUSDT",
    "BONKUSDT",
    "SHIBUSDT",
    "USELESSUSDT",
    "SPACEUSDT",
    "MOVEUSDT",
    "ZECUSDT",
    "SPXUSDT",
    "PEOPLEUSDT",
    "PENGUUSDT",
    "FARTCOINUSDT",
    "LINEAUSDT",
    "MEMEUSDT",
    "PUMPUSDT",
    "AIXBTUSDT",
    "BRETTUSDT",
    "FOGOUSDT",
    "GOOGLUSDT",
    "FLOKIUSDT",
    "IWMUSDT",
    "MOODENGUSDT",
    "NEARUSDT"
]

# Initialize Watchlist state with all 25 coins
WATCHLIST = [{"symbol": sym, "timeframe": "15M", "pinned": False} for sym in DEFAULT_WATCHLIST]

@app.route("/")
def index():
    selected_tf = request.args.get("tf", "ALL").upper()
    
    # 1. Fetch Permanent Watchlist Rows for all 25 coins
    watchlist_rows = []
    for item in WATCHLIST:
        tf = item["timeframe"] if selected_tf == "ALL" else selected_tf
        match, _ = _process_symbol_tf(item["symbol"], tf)
        if match:
            match["pinned"] = item["pinned"]
            watchlist_rows.append(match)
        else:
            watchlist_rows.append({
                "symbol": item["symbol"],
                "timeframe": tf,
                "curr_close": "N/A",
                "support": "N/A",
                "resistance": "N/A",
                "direction_label": "Loading...",
                "break_direction": "NEUTRAL",
                "break_symbol": "↔",
                "readiness_display": "0%",
                "buyer_power": 50.0,
                "seller_power": 50.0,
                "pinned": item["pinned"]
            })

    # 2. Run Scanner across all 25 tickers
    scanner_results, _ = run_scanner_pipeline(DEFAULT_WATCHLIST, selected_tf)

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
