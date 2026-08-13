import time
import threading
from flask import Flask, render_template, request, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from scanner import (
    CACHE, CACHE_LOCK, SCAN_READY,
    start_authoritative_scanner,
    DEFAULT_WATCHLIST,
    _process_symbol_tf
)

app = Flask(__name__)

# ---- Start the single authoritative scanner worker ----
# This runs once when the app starts; does NOT start on every request.
start_authoritative_scanner()

# ---- Watchlist (mirrors scanner's DEFAULT_WATCHLIST) ----
WATCHLIST = [{"symbol": sym, "timeframe": "15M", "pinned": False} for sym in DEFAULT_WATCHLIST]

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
    # Placeholder – keep your existing alignment logic if you have it
    return "Alignment explanation"

@app.route("/")
def index():
    selected_tf = request.args.get("tf", "15M").upper()
    print(f"[ROUTE] Selected timeframe = {selected_tf}")

    active_tf = "15M" if selected_tf == "ALL" else selected_tf

    # ---- Fallback: if active_tf has no data, use first available ----
    with CACHE_LOCK:
        has_data = any(key.endswith(f"_{active_tf}") for key in CACHE)
        if not has_data:
            for tf in ["15M", "5M", "1H", "4H"]:
                if any(key.endswith(f"_{tf}") for key in CACHE):
                    active_tf = tf
                    print(f"[ROUTE] No data for {selected_tf}, falling back to {tf}")
                    break

    watchlist_rows = []
    is_loading = not SCAN_READY   # SCAN_READY is set only after 15M is cached

    with CACHE_LOCK:
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

    scanner_results = watchlist_rows.copy()
    scanner_results = sort_results(scanner_results)

    passed = sum(1 for r in scanner_results if r.get("readiness_score", 0) > 0)
    diagnostics = {
        "total_symbols": len(WATCHLIST),
        "timeframes": 4,
        "passed": passed,
        "unsupported": 0,
        "failed_logic": 0,
        "displayed": len(scanner_results),
        "cache_size": len(CACHE)
    }

    # Build scan_status for the UI
    scan_status = {
        "state": "LIVE" if SCAN_READY else "INITIALIZING",
        "total_symbols": len(WATCHLIST),
        "symbols_scanned": len(CACHE),
        "cache_size": len(CACHE),
        "last_update": datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    }

    return render_template(
        "index.html",
        selected_tf=selected_tf,
        watchlist_rows=watchlist_rows,
        rows=scanner_results,
        is_loading=is_loading,
        scan_status=scan_status,
        diagnostics=diagnostics
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
