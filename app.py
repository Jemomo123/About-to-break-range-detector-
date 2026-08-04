import os
import traceback
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Safe module imports
try:
    from scanner import run_scanner_pipeline
    from config import SUPPORTED_TIMEFRAMES, DEFAULT_WATCHLIST
except ImportError:
    SUPPORTED_TIMEFRAMES = ["5M", "15M", "1H"]
    DEFAULT_WATCHLIST = []
    def run_scanner_pipeline(watchlist, tf):
        return [], {"error": "Import failed"}

def format_smart_price(val):
    """Formats price dynamically based on asset scale instead of fixed decimals."""
    if val is None:
        return "0.00"
    try:
        val = float(val)
    except (ValueError, TypeError):
        return "0.00"

    if val == 0:
        return "0.00"

    abs_val = abs(val)
    if abs_val >= 1000:
        return f"{val:,.2f}"      # BTC: 64,218.61
    elif abs_val >= 1:
        return f"{val:.4f}"       # ETH / TAO / RENDER: 1.3510
    elif abs_val >= 0.01:
        return f"{val:.5f}"       # DOGE: 0.18654
    else:
        return f"{val:.8f}"       # PEPE / SHIB: 0.00001234

# Register Jinja2 Filter
app.jinja_env.filters['smart_price'] = format_smart_price

def sanitize_scan_results(results):
    """Ensures raw engine output contains valid non-null numerical values."""
    sanitized = []
    for item in (results or []):
        if not isinstance(item, dict):
            continue
        sanitized.append({
            "symbol": str(item.get("symbol", "UNKNOWN")),
            "timeframe": str(item.get("timeframe", "5M")),
            "structure_type": str(item.get("structure_type", "HORIZONTAL")),
            "curr_close": float(item.get("curr_close") or 0.0),
            "readiness_score": int(item.get("readiness_score") or 0),
            "readiness_display": str(item.get("readiness_display") or item.get("readiness_label") or "BUILDING PRESSURE"),
            "support": float(item.get("support") or 0.0),
            "resistance": float(item.get("resistance") or 0.0),
            "buyer_power": int(item.get("buyer_power") if item.get("buyer_power") is not None else 50),
            "seller_power": int(item.get("seller_power") if item.get("seller_power") is not None else 50)
        })
    return sanitized

@app.route("/")
def index():
    selected_tf = request.args.get("tf", "ALL").upper()
    if selected_tf not in SUPPORTED_TIMEFRAMES and selected_tf != "ALL":
        selected_tf = "ALL"

    target_tf = None if selected_tf == "ALL" else selected_tf
    
    try:
        raw_rows, diagnostics = run_scanner_pipeline(DEFAULT_WATCHLIST, target_tf)
        rows = sanitize_scan_results(raw_rows)
    except Exception as e:
        print(f"[ERROR] Engine Exception: {e}", flush=True)
        traceback.print_exc()
        rows = []
        diagnostics = {"error": str(e)}

    return render_template(
        "index.html",
        rows=rows,
        diagnostics=diagnostics,
        selected_tf=selected_tf
    )

@app.route("/api/scan", methods=["GET"])
def api_scan():
    selected_tf = request.args.get("tf", "ALL").upper()
    if selected_tf not in SUPPORTED_TIMEFRAMES and selected_tf != "ALL":
        selected_tf = "ALL"

    target_tf = None if selected_tf == "ALL" else selected_tf

    try:
        raw_rows, diagnostics = run_scanner_pipeline(DEFAULT_WATCHLIST, target_tf)
        sanitized = sanitize_scan_results(raw_rows)
        return jsonify({
            "status": "success",
            "selected_timeframe": selected_tf,
            "results": sanitized,
            "diagnostics": diagnostics or {}
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "selected_timeframe": selected_tf,
            "results": [],
            "error": str(e)
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
