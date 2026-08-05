import os
import time
import threading
import traceback
from flask import Flask, render_template, request, jsonify
from scanner import run_scanner_pipeline

app = Flask(__name__)

DEFAULT_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT", "NEARUSDT",
    "APTUSDT", "PEPEUSDT", "SHIBUSDT", "DOTUSDT", "LTCUSDT",
    "BCHUSDT", "UNIUSDT", "FETUSDT", "TAOUSDT", "WIFUSDT",
    "ARBUSDT", "OPUSDT", "INJUSDT", "TIAUSDT"
]

CACHE_STORE = {
    "rows": {"ALL": [], "3M": [], "5M": [], "15M": [], "1H": [], "4H": []},
    "diagnostics": {"ALL": {}, "3M": {}, "5M": {}, "15M": {}, "1H": {}, "4H": {}},
    "last_updated": 0,
    "is_scanning": False
}

cache_lock = threading.Lock()
start_scanner_event = threading.Event()


def background_scanner_loop():
    """Background scanner thread."""
    global CACHE_STORE
    
    # Block background scanner until Render binds to port 10000
    print("[ABOUT TO BREAK RANGE DETECTOR] Engine waiting for HTTP port binding...", flush=True)
    start_scanner_event.wait()
    
    # 5-second initial delay after port bind to guarantee Render detects the open port
    time.sleep(5)
    print("[ABOUT TO BREAK RANGE DETECTOR] Port verified open. Starting scanner loop...", flush=True)

    while True:
        try:
            with cache_lock:
                CACHE_STORE["is_scanning"] = True

            # Single scanner execution pass for ALL timeframes
            all_results, all_diag = run_scanner_pipeline(DEFAULT_WATCHLIST, "ALL")

            # Slice matches into individual timeframe buckets for fast filtering
            rows_by_tf = {
                "ALL": all_results,
                "5M": [r for r in all_results if r.get("timeframe") == "5M"],
                "15M": [r for r in all_results if r.get("timeframe") == "15M"],
                "1H": [r for r in all_results if r.get("timeframe") == "1H"],
                "3M": [r for r in all_results if r.get("timeframe") == "3M"],
                "4H": [r for r in all_results if r.get("timeframe") == "4H"]
            }

            diag_by_tf = {
                "ALL": all_diag,
                "5M": {**all_diag, "matches": len(rows_by_tf["5M"])},
                "15M": {**all_diag, "matches": len(rows_by_tf["15M"])},
                "1H": {**all_diag, "matches": len(rows_by_tf["1H"])},
                "3M": {**all_diag, "matches": len(rows_by_tf["3M"])},
                "4H": {**all_diag, "matches": len(rows_by_tf["4H"])}
            }

            with cache_lock:
                CACHE_STORE["rows"] = rows_by_tf
                CACHE_STORE["diagnostics"] = diag_by_tf
                CACHE_STORE["last_updated"] = time.time()
                CACHE_STORE["is_scanning"] = False

            print(f"[ABOUT TO BREAK RANGE DETECTOR] Scan complete. Updated cache with {len(all_results)} matches.", flush=True)

        except Exception as e:
            print(f"[ERROR] Background Scanner Loop Error: {e}", flush=True)
            traceback.print_exc()
            with cache_lock:
                CACHE_STORE["is_scanning"] = False

        # Sleep 45s between background scans
        time.sleep(45)


# Spawn background worker daemon
scanner_thread = threading.Thread(target=background_scanner_loop, daemon=True)
scanner_thread.start()


@app.before_request
def signal_port_ready():
    """Unblocks the background scanner when Render sends its first HTTP health ping."""
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
    if target_tf not in ["ALL", "3M", "5M", "15M", "1H", "4H"]:
        target_tf = "ALL"

    with cache_lock:
        rows = CACHE_STORE["rows"].get(target_tf, [])
        diagnostics = CACHE_STORE["diagnostics"].get(target_tf, {"symbols_scanned": 0, "matches": 0, "rejections": {}})
        last_updated = CACHE_STORE["last_updated"]
        is_scanning = CACHE_STORE["is_scanning"]

    return render_template(
        "index.html",
        rows=rows,
        diagnostics=diagnostics,
        selected_tf=target_tf,
        last_updated=last_updated,
        is_scanning=is_scanning
    )


@app.route("/api/scan", methods=["GET"])
def api_scan():
    target_tf = request.args.get("tf", "ALL").upper()
    if target_tf not in ["ALL", "3M", "5M", "15M", "1H", "4H"]:
        target_tf = "ALL"

    with cache_lock:
        return jsonify({
            "success": True,
            "rows": CACHE_STORE["rows"].get(target_tf, []),
            "diagnostics": CACHE_STORE["diagnostics"].get(target_tf, {}),
            "last_updated": CACHE_STORE["last_updated"],
            "is_scanning": CACHE_STORE["is_scanning"]
        })


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
