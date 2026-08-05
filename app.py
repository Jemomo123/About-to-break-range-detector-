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

# Shared Thread-Safe In-Memory Cache Store
CACHE_STORE = {
    "rows": {
        "ALL": [], "3M": [], "5M": [], "15M": [], "1H": [], "4H": []
    },
    "diagnostics": {
        "ALL": {"symbols_scanned": len(DEFAULT_WATCHLIST), "matches": 0, "rejections": {}},
        "3M": {"symbols_scanned": len(DEFAULT_WATCHLIST), "matches": 0, "rejections": {}},
        "5M": {"symbols_scanned": len(DEFAULT_WATCHLIST), "matches": 0, "rejections": {}},
        "15M": {"symbols_scanned": len(DEFAULT_WATCHLIST), "matches": 0, "rejections": {}},
        "1H": {"symbols_scanned": len(DEFAULT_WATCHLIST), "matches": 0, "rejections": {}},
        "4H": {"symbols_scanned": len(DEFAULT_WATCHLIST), "matches": 0, "rejections": {}}
    },
    "last_updated": 0,
    "is_scanning": False
}

cache_lock = threading.Lock()
start_scanner_event = threading.Event()


def background_scanner_loop():
    """Background thread engine: waits for Flask HTTP socket binding before scanning."""
    global CACHE_STORE
    
    print("[ABOUT TO BREAK RANGE DETECTOR] Engine initialized. Waiting for HTTP port binding...", flush=True)
    start_scanner_event.wait()
    
    # 3-second safety delay after initial request to ensure port binding is verified
    time.sleep(3)
    print("[ABOUT TO BREAK RANGE DETECTOR] Port verified open. Starting scanner loop...", flush=True)

    while True:
        try:
            with cache_lock:
                CACHE_STORE["is_scanning"] = True

            # Single parallel scan pass for all default timeframes
            all_results, all_diag = run_scanner_pipeline(DEFAULT_WATCHLIST, "ALL")

            # Slice results into per-timeframe buckets
            rows_by_tf = {
                "ALL": all_results,
                "5M": [r for r in all_results if r.get("timeframe") == "5M"],
                "15M": [r for r in all_results if r.get("timeframe") == "15M"],
                "1H": [r for r in all_results if r.get("timeframe") == "1H"],
                "3M": [r for r in all_results if r.get("timeframe") == "3M"],
                "4H": [r for r in all_results if r.get("timeframe") == "4H"]
            }

            # Build detailed diagnostics for each timeframe tab
            diag_by_tf = {}
            for tf_key in ["ALL", "3M", "5M", "15M", "1H", "4H"]:
                matching_rows = rows_by_tf.get(tf_key, [])
                diag_by_tf[tf_key] = {
                    "symbols_scanned": len(DEFAULT_WATCHLIST),
                    "symbols_downloaded": all_diag.get("symbols_downloaded", 0),
                    "matches": len(matching_rows),
                    "rejections": all_diag.get("rejections", {})
                }

            # Update cache store atomically
            with cache_lock:
                CACHE_STORE["rows"] = rows_by_tf
                CACHE_STORE["diagnostics"] = diag_by_tf
                CACHE_STORE["last_updated"] = time.time()
                CACHE_STORE["is_scanning"] = False

            print(f"[ABOUT TO BREAK RANGE DETECTOR] Scan complete. Total ALL matches: {len(all_results)}", flush=True)

        except Exception as e:
            print(f"[ERROR] Exception in Background Scanner: {e}", flush=True)
            traceback.print_exc()
            with cache_lock:
                CACHE_STORE["is_scanning"] = False

        # Sleep 45 seconds between scans
        time.sleep(45)


# Start daemon worker thread immediately
scanner_thread = threading.Thread(target=background_scanner_loop, daemon=True)
scanner_thread.start()


@app.before_request
def signal_port_ready():
    """Unblocks the background scanner loop on the first HTTP request (e.g. Render health ping)."""
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
    """Returns cached UI immediately without running blocking network calls."""
    target_tf = request.args.get("tf", "ALL").upper()
    if target_tf not in ["ALL", "3M", "5M", "15M", "1H", "4H"]:
        target_tf = "ALL"

    with cache_lock:
        rows = CACHE_STORE["rows"].get(target_tf, [])
        diagnostics = CACHE_STORE["diagnostics"].get(target_tf, {
            "symbols_scanned": len(DEFAULT_WATCHLIST), 
            "matches": 0, 
            "rejections": {}
        })
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
    """Returns JSON state directly from cache for smooth front-end polling."""
    target_tf = request.args.get("tf", "ALL").upper()
    if target_tf not in ["ALL", "3M", "5M", "15M", "1H", "4H"]:
        target_tf = "ALL"

    with cache_lock:
        return jsonify({
            "success": True,
            "rows": CACHE_STORE["rows"].get(target_tf, []),
            "diagnostics": CACHE_STORE["diagnostics"].get(target_tf, {
                "symbols_scanned": len(DEFAULT_WATCHLIST), 
                "matches": 0, 
                "rejections": {}
            }),
            "last_updated": CACHE_STORE["last_updated"],
            "is_scanning": CACHE_STORE["is_scanning"]
        })


@app.route("/health", methods=["GET"])
def health():
    """Explicit health check endpoint for Render health probes."""
    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
