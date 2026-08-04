# app.py
from flask import Flask, render_template, request, jsonify
from config import SUPPORTED_TIMEFRAMES, DEFAULT_WATCHLIST
from scanner import run_scanner_pipeline

app = Flask(__name__)

@app.route("/")
def index():
    selected_tf = request.args.get("tf", "ALL")
    if selected_tf not in SUPPORTED_TIMEFRAMES and selected_tf != "ALL":
        selected_tf = "ALL"

    rows, diagnostics = run_scanner_pipeline(DEFAULT_WATCHLIST, selected_tf if selected_tf != "ALL" else None)
    
    return render_template(
        "index.html",
        rows=rows,
        diagnostics=diagnostics,
        supported_tfs=SUPPORTED_TIMEFRAMES,
        selected_tf=selected_tf
    )

@app.route("/api/scan")
def api_scan():
    selected_tf = request.args.get("tf", "ALL")
    rows, diagnostics = run_scanner_pipeline(DEFAULT_WATCHLIST, selected_tf if selected_tf != "ALL" else None)
    return jsonify({"results": rows, "diagnostics": diagnostics})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
