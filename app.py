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
        "ALL": [],
        "3M": [],
        "5M": [],
        "15M": [],
        "1H": [],
        "4H": []
    },
    "diagnostics": {
        "ALL": {"symbols_scanned": 0, "matches": 0, "rejections": {}},
        "5M": {"symbols_scanned": 0, "matches": 0, "rejections": {}},
        "15M": {"symbols_scanned": 0, "matches": 0, "rejections": {}},
        "1H": {"symbols_scanned": 0, "matches": 0, "rejections": {}}
    },
    "last_updated": 0,
    "is_scanning": False
}

cache_lock = threading.Lock()


def background_scanner_worker():
    """Background scanner thread that updates the cache every 45s without blocking Flask."""
    global CACHE_STORE
    print("[ABOUT TO BREAK RANGE DETECTOR] Background Thread Engine Started.", flush=True)

    # Initial brief pause to allow Flask/Gunicorn to fully bind to HTTP port first
    time.sleep(2)

    timeframes = ["ALL", "5M", "15M", "1H"]

    while True:
        try:
            with cache_lock:
                CACHE_STORE["is_scanning"] = True

            print("[ABOUT TO BREAK RANGE DETECTOR] Running Background Scan...", flush=True)

            temp_rows = {}
            temp_diag = {}

            for tf in timeframes:
                rows, diag = run_scanner_pipeline(DEFAULT_WATCHLIST, tf)
                temp_rows[tf] = rows or []
                temp_diag[tf] = diag or {"symbols_scanned": 0, "matches": 0, "rejections": {}}

            # Thread-safe atomic update
            with cache_lock:
                CACHE_STORE["rows"] = temp_rows
                CACHE_STORE["diagnostics"] = temp_diag
                CACHE_STORE["last_updated"] = time.time()
                CACHE_STORE["is_scanning"] = False

            print(f"[ABOUT TO BREAK RANGE DETECTOR] Scan complete. Found {len(temp_rows.get('ALL', []))} matches.", flush=True)

        except Exception as e:
            print(f"[ERROR] Exception in Background Scanner: {e}", flush=True)
            traceback.print_exc()
            with cache_lock:
                CACHE_STORE["is_scanning"] = False

        # Wait 45 seconds before next cycle
        time.sleep(45)


# Start background worker thread
scanner_thread = threading.Thread(target=background_scanner_worker, daemon=True)
scanner_thread.start()


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
    """Returns HTML instantly from cache without waiting for the scanner."""
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
    """Zero-flicker background endpoint for JavaScript updates."""
    target_tf = request.args.get("tf", "ALL").upper()
    if target_tf not in ["ALL", "3M", "5M", "15M", "1H", "4H"]:
        target_tf = "ALL"

    with cache_lock:
        data = {
            "success": True,
            "rows": CACHE_STORE["rows"].get(target_tf, []),
            "diagnostics": CACHE_STORE["diagnostics"].get(target_tf, {}),
            "last_updated": CACHE_STORE["last_updated"],
            "is_scanning": CACHE_STORE["is_scanning"]
        }
    return jsonify(data)


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
