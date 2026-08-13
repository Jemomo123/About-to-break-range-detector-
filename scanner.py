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
SCAN_READY = False

def update_cache_job():
    global SCAN_READY
    while True:
        # We only scan 5M, 15M, 1H, 4H in the background
        for tf in ["5M", "15M", "1H", "4H"]:
            # ... (your existing background worker logic)
            pass
        # ... (rest unchanged)

# ... (keep your existing background worker code)

@app.route("/")
def index():
    # ---- FIX: get selected timeframe from URL, default to 15M ----
    selected_tf = request.args.get("tf", "15M").upper()
    print(f"[ROUTE] Selected timeframe = {selected_tf}")

    # ---- FIX: pass the selected timeframe to the scanner ----
    from scanner import run_scanner_pipeline
    results, diagnostics = run_scanner_pipeline(DEFAULT_WATCHLIST, timeframe=selected_tf)

    # Build watchlist rows (existing logic)
    watchlist_rows = []
    is_loading = not SCAN_READY
    # ... (your existing logic to build watchlist_rows from cache)

    return render_template(
        "index.html",
        selected_tf=selected_tf,
        watchlist_rows=watchlist_rows,
        rows=results,
        is_loading=is_loading,
        scan_status=scan_status,
        diagnostics=diagnostics
    )

# ... (keep your other routes and functions)
