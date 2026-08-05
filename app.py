import os
import time
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

    try:
        raw_rows, diagnostics = run_scanner_pipeline(DEFAULT_WATCHLIST, target_tf)
    except Exception as e:
        print(f"[ERROR] Engine Exception: {e}", flush=True)
        traceback.print_exc()
        raw_rows, diagnostics = [], {"symbols_scanned": 0, "matches": 0, "rejections": {}}

    return render_template(
        "index.html",
        rows=raw_rows,
        diagnostics=diagnostics,
        selected_tf=target_tf
    )


@app.route("/api/scan", methods=["GET"])
def api_scan():
    """Background endpoint for zero-flicker client auto-refreshes."""
    target_tf = request.args.get("tf", "ALL").upper()
    if target_tf not in ["ALL", "3M", "5M", "15M", "1H", "4H"]:
        target_tf = "ALL"

    try:
        raw_rows, diagnostics = run_scanner_pipeline(DEFAULT_WATCHLIST, target_tf)
        return jsonify({
            "success": True,
            "rows": raw_rows,
            "diagnostics": diagnostics,
            "timestamp": time.time()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
