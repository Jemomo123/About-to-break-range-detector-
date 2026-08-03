# app.py
from flask import Flask, render_template, request
import threading
import time
import logging
from config import WATCHLIST, SUPPORTED_TIMEFRAMES, DEFAULT_TIMEFRAME
from scanner import run_scanner_pipeline

app = Flask(__name__)
DATA_CACHE = {tf: [] for tf in SUPPORTED_TIMEFRAMES}

def cache_worker():
    while True:
        for tf in SUPPORTED_TIMEFRAMES:
            try:
                DATA_CACHE[tf] = run_scanner_pipeline(WATCHLIST, tf)
            except Exception as e:
                logging.error(f"Worker Error on {tf}: {e}")
        time.sleep(15)

threading.Thread(target=cache_worker, daemon=True).start()

@app.route("/")
def index():
    selected_tf = request.args.get("tf", DEFAULT_TIMEFRAME)
    if selected_tf not in SUPPORTED_TIMEFRAMES:
        selected_tf = DEFAULT_TIMEFRAME

    rows = DATA_CACHE.get(selected_tf, [])
    if not rows:
        rows = run_scanner_pipeline(WATCHLIST, selected_tf)
        DATA_CACHE[selected_tf] = rows

    return render_template("index.html", rows=rows, selected_tf=selected_tf, supported_tfs=SUPPORTED_TIMEFRAMES)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
