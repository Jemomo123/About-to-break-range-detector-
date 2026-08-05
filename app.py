import os
import json
import time
import threading
import traceback
from flask import Flask, render_template, request, jsonify
from scanner import run_scanner_pipeline, _process_symbol_tf
import config

# Project Name: ABOUT TO BREAK RANGE DETECTOR
# Scanner pool is strictly locked to DEFAULT_WATCHLIST in config.py
SCANNER_WATCHLIST = config.DEFAULT_WATCHLIST
TIMEFRAMES = getattr(config, "TIMEFRAMES", ["3M", "5M", "15M", "1H", "4H"])

WATCHLIST_FILE = "watchlist_db.json"
file_lock = threading.Lock()

# --- Embedded Persistent Watchlist Storage ---
def get_watchlist():
    with file_lock:
        if not os.path.exists(WATCHLIST_FILE):
            return []
        try:
            with open(WATCHLIST_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []

def save_watchlist(data):
    with file_lock:
        try:
            with open(WATCHLIST_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[ERROR] Could not save watchlist: {e}")

def add_symbol_to_watchlist(symbol: str, timeframe: str = "15M"):
    clean_sym = symbol.replace("_", "").replace("-", "").strip().upper()
    if not clean_sym.endswith("USDT") and not clean_sym.endswith("USDC"):
        clean_sym += "USDT"

    items = get_watchlist()
    for item in items:
        if item["symbol"] == clean_sym and item["timeframe"] == timeframe:
            return items

    items.append({"symbol": clean_sym, "timeframe": timeframe, "pinned": False})
    save_watchlist(items)
    return items

def remove_symbol_from_watchlist(symbol: str, timeframe: str):
    items = get_watchlist()
    items = [i for i in items if not (i["symbol"] == symbol and i["timeframe"] == timeframe)]
    save_watchlist(items)
    return items

def toggle_pin_watchlist(symbol: str, timeframe: str):
    items = get_watchlist()
    for item in items:
        if item["symbol"] == symbol and item["timeframe"] == timeframe:
            item["pinned"] = not item.get("pinned", False)
            break
    
    items.sort(key=lambda x: (not x.get("pinned", False), x["symbol"]))
    save_watchlist(items)
    return items

# --- Flask Web Application ---
app = Flask(__name__)

CACHE_STORE = {
    "scanner_rows": {tf: [] for tf in ["ALL"] + TIMEFRAMES},
    "watchlist_rows": [],
    "diagnostics": {tf: {"symbols_scanned": 25, "matches": 0, "rejections": {}} for tf in ["ALL"] + TIMEFRAMES},
    "last_updated": 0,
    "is_scanning": False
}

cache_lock = threading.Lock()
start_scanner_event = threading.Event()


def evaluate_watchlist_items():
    """Scans user personal watchlist items without removing any symbols."""
    user_watchlist = get_watchlist()
    enriched_watchlist = []

    for item in user_watchlist:
        symbol = item["symbol"]
        tf = item.get("timeframe", "15M")
        pinned = item.get("pinned", False)

        match, err_code = _process_symbol_tf(symbol, tf)
        if match:
            match["pinned"] = pinned
            enriched_watchlist.append(match)
        else:
            status_text = err_code if err_code else "DATA UNAVAILABLE"
            enriched_watchlist.append({
                "symbol": symbol,
                "timeframe": tf,
                "exchange": "MEXC/OKX",
                "structure_type": status_text,
                "curr_close": 0.0,
                "support": 0.0,
                "resistance": 0.0,
                "readiness_score": 0,
                "readiness_display": "N/A",
                "buyer_power": 0,
                "seller_power": 0,
                "break_direction": "NEUTRAL",
                "break_symbol": "⚠",
                "pinned": pinned
            })

    enriched_watchlist.sort(key=lambda x: (not x.get("pinned", False), -x.get("readiness_score", 0)))
    return enriched_watchlist


def background_scanner_loop():
    global CACHE_STORE
    
    start_scanner_event.wait()
    time.sleep(2)

    while True:
        try:
            with cache_lock:
                CACHE_STORE["is_scanning"] = True

            # 1. Update Persistent Watchlist Metrics
            wl_results = evaluate_watchlist_items()

            # 2. Run Scanner Engine using the mandatory 25 coins from config.py
            all_results, all_diag = run_scanner_pipeline(SCANNER_WATCHLIST, "ALL")

            rows_by_tf = {"ALL": all_results}
            for tf in TIMEFRAMES:
                rows_by_tf[tf] = [r for r in all_results if r.get("timeframe") == tf]

            diag_by_tf = {}
            for tf_key in ["ALL"] + TIMEFRAMES:
                matching_rows = rows_by_tf.get(tf_key, [])
                diag_by_tf[tf_key] = {
                    "symbols_scanned": len(SCANNER_WATCHLIST),
                    "symbols_downloaded": all_diag.get("symbols_downloaded", 0),
                    "matches": len(matching_rows),
                    "rejections": all_diag.get("rejections", {})
                }

            with cache_lock:
                CACHE_STORE["scanner_rows"] = rows_by_tf
                CACHE_STORE["watchlist_rows"] = wl_results
                CACHE_STORE["diagnostics"] = diag_by_tf
                CACHE_STORE["last_updated"] = time.time()
                CACHE_STORE["is_scanning"] = False

        except Exception as e:
            print(f"[ERROR] Scanner Loop Error: {e}", flush=True)
            traceback.print_exc()
            with cache_lock:
                CACHE_STORE["is_scanning"] = False

        time.sleep(30)


threading.Thread(target=background_scanner_loop, daemon=True).start()


@app.before_request
def signal_port_ready():
    if not start_scanner_event.is_set():
        start_scanner_event.set()


@app.template_filter("smart_price")
def smart_price(value):
    try:
        value = float(value)
    except (ValueError, TypeError):
        return "0.00"
    if value >= 100:
        return f"{value:,.2f}"
    elif value >= 1:
        return f"{value:.4f}"
    elif value >= 0.01:
        return f"{value:.6f}"
    else:
        return f"{value:.8f}"


@app.route("/", methods=["GET"])
def index():
    target_tf = request.args.get("tf", "ALL").upper()
    if target_tf not in ["ALL"] + TIMEFRAMES:
        target_tf = "ALL"

    with cache_lock:
        scanner_rows = CACHE_STORE["scanner_rows"].get(target_tf, [])
        watchlist_rows = CACHE_STORE["watchlist_rows"]
        diagnostics = CACHE_STORE["diagnostics"].get(target_tf, {"symbols_scanned": 25, "matches": 0})
        last_updated = CACHE_STORE["last_updated"]
        is_scanning = CACHE_STORE["is_scanning"]

    return render_template(
        "index.html",
        rows=scanner_rows,
        watchlist_rows=watchlist_rows,
        diagnostics=diagnostics,
        selected_tf=target_tf,
        last_updated=last_updated,
        is_scanning=is_scanning,
        timeframes=TIMEFRAMES
    )


@app.route("/api/scan", methods=["GET"])
def api_scan():
    target_tf = request.args.get("tf", "ALL").upper()
    if target_tf not in ["ALL"] + TIMEFRAMES:
        target_tf = "ALL"

    with cache_lock:
        return jsonify({
            "success": True,
            "rows": CACHE_STORE["scanner_rows"].get(target_tf, []),
            "watchlist_rows": CACHE_STORE["watchlist_rows"],
            "diagnostics": CACHE_STORE["diagnostics"].get(target_tf, {"symbols_scanned": 25, "matches": 0}),
            "last_updated": CACHE_STORE["last_updated"],
            "is_scanning": CACHE_STORE["is_scanning"]
        })


@app.route("/api/watchlist/add", methods=["POST"])
def api_watchlist_add():
    data = request.json or {}
    symbol = data.get("symbol", "").strip()
    timeframe = data.get("timeframe", "15M").strip().upper()

    if not symbol:
        return jsonify({"success": False, "error": "Symbol is required"}), 400

    add_symbol_to_watchlist(symbol, timeframe)
    threading.Thread(target=evaluate_watchlist_items, daemon=True).start()
    return jsonify({"success": True, "watchlist": get_watchlist()})


@app.route("/api/watchlist/remove", methods=["POST"])
def api_watchlist_remove():
    data = request.json or {}
    symbol = data.get("symbol", "").strip()
    timeframe = data.get("timeframe", "15M").strip().upper()

    updated = remove_symbol_from_watchlist(symbol, timeframe)
    return jsonify({"success": True, "watchlist": updated})


@app.route("/api/watchlist/pin", methods=["POST"])
def api_watchlist_pin():
    data = request.json or {}
    symbol = data.get("symbol", "").strip()
    timeframe = data.get("timeframe", "15M").strip().upper()

    updated = toggle_pin_watchlist(symbol, timeframe)
    return jsonify({"success": True, "watchlist": updated})


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
