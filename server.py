# server.py
# =====================================================================
# GUNICORN / RENDER ENTRY POINT (VERSION 1.2.1)
# =====================================================================

from flask import request, render_template
from app import app, DEFAULT_TIMEFRAME, SUPPORTED_TIMEFRAMES, TARGET_SYMBOLS
from scanner import run_scanner_pipeline


@app.route("/")
def index():
    # Capture timeframe from query parameter, defaulting to '1h'
    selected_tf = request.args.get("tf", DEFAULT_TIMEFRAME)
    if selected_tf not in SUPPORTED_TIMEFRAMES:
        selected_tf = DEFAULT_TIMEFRAME

    # Execute scanner pipeline with the requested timeframe
    rows = run_scanner_pipeline(TARGET_SYMBOLS, timeframe=selected_tf)

    return render_template(
        "index.html",
        rows=rows,
        selected_tf=selected_tf,
        supported_tfs=SUPPORTED_TIMEFRAMES
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
