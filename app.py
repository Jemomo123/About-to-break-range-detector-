# =====================================================================
# STAGE 3 — API ROUTER & SERVER ENTRY POINT
# =====================================================================
from flask import Flask, jsonify, render_template
from config import WATCHLIST, TIMEFRAME, CANDLE_LIMIT
from coinalyze import fetch_candles, fetch_order_flow
from detector import RangeDetectionEngine
from scanner import BreakoutAnalysisEngine

app = Flask(__name__)

@app.route("/")
def index():
    """Renders the frontend dashboard template."""
    return render_template("index.html")

@app.route("/api/scan", methods=["GET"])
def run_scan():
    """Pipeline Executor: Fetches data, runs Stage 1 -> Stage 2 -> Emits JSON."""
    results = []
    
    print(f"Starting scan across {len(WATCHLIST)} active watchlist symbols...")

    for symbol in WATCHLIST:
        # Fetch Data Layer
        candles = fetch_candles(symbol, timeframe=TIMEFRAME, limit=CANDLE_LIMIT)
        if not candles:
            continue

        # STAGE 1: Gatekeeper Check
        range_data = RangeDetectionEngine.detect_range(candles)
        if not range_data or not range_data.get("is_valid"):
            continue  # Stop immediately if Stage 1 fails

        # STAGE 2: Breakout Analysis
        current_price = candles[-1]["close"]
        order_flow = fetch_order_flow(symbol)
        analysis = BreakoutAnalysisEngine.analyze(symbol, current_price, range_data, order_flow)

        # STAGE 3: Zero-Calculation Payload Formatting
        loc_pct = analysis["price_location_pct"]
        location_text = f"{loc_pct}% toward resistance" if loc_pct >= 50 else f"{100 - loc_pct}% above support"

        payload = {
            "symbol": analysis["symbol"],
            "range_type": analysis["range_type"],
            "support": analysis["support"],
            "resistance": analysis["resistance"],
            "current_price": analysis["current_price"],
            "price_location_pct": analysis["price_location_pct"],
            "price_location_text": location_text,
            "buyer_power": analysis["buyer_power"],
            "seller_power": analysis["seller_power"],
            "direction": analysis["direction"],
            "status": analysis["status"]
        }
        
        results.append(payload)

    return jsonify({"status": "success", "data": results})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
