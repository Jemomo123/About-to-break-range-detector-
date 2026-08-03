# app.py
from flask import Flask, render_template, request
import threading
import time
import logging
from config import WATCHLIST, SUPPORTED_TIMEFRAMES, DEFAULT_TIMEFRAME
from scanner import run_scanner_pipeline

app = Flask(__name__)

# Startup Log
print("\n==========================================", flush=True)
print(f"Loaded Watchlist ({len(WATCHLIST)}):", flush=True)
for s in WATCHLIST:
    print(f"{s}", flush=True)
print("==========================================\n", flush=True)

DATA_CACHE = {tf: {"rows": [], "diagnostics": {}} for tf in SUPPORTED_TIMEFRAMES}

def cache_worker():
    while True:
        for tf in SUPPORTED_TIMEFRAMES:
            try:
                rows, diagnostics = run_scanner_pipeline(WATCHLIST, tf)
                DATA_CACHE[tf] = {"rows": rows, "diagnostics": diagnostics}
            except Exception as e:
                logging.error(f"Worker Error on {tf}: {e}")
        time.sleep(15)

threading.Thread(target=cache_worker, daemon=True).start()

@app.route("/")
def index():
    selected_tf = request.args.get("tf", DEFAULT_TIMEFRAME)
    if selected_tf not in SUPPORTED_TIMEFRAMES:
        selected_tf = DEFAULT_TIMEFRAME

    cache_item = DATA_CACHE.get(selected_tf, {"rows": [], "diagnostics": {}})
    rows = cache_item.get("rows", [])
    diagnostics = cache_item.get("diagnostics", {})

    if not rows and not diagnostics:
        rows, diagnostics = run_scanner_pipeline(WATCHLIST, selected_tf)
        DATA_CACHE[selected_tf] = {"rows": rows, "diagnostics": diagnostics}

    return render_template(
        "index.html", 
        rows=rows, 
        diagnostics=diagnostics, 
        selected_tf=selected_tf, 
        supported_tfs=SUPPORTED_TIMEFRAMES
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
