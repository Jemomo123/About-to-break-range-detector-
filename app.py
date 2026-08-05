import os
import time
import traceback
from flask import Flask, render_template, request
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
    start_time = time.time()
    target_tf = request.args.get("tf", "ALL").upper()
    if target_tf not in ["ALL", "3M", "5M", "15M", "1H", "4H"]:
        target_tf = "ALL"

    try:
        raw_rows, diagnostics = run_scanner_pipeline(DEFAULT_WATCHLIST, target_tf)
    except Exception as e:
        print(f"[ERROR] Engine Exception: {e}", flush=True)
        traceback.print_exc()
        raw_rows, diagnostics = [], {"symbols_scanned": 0, "matches": 0, "rejections": {}}

    elapsed = time.time() - start_time
    print(f"[PERF LOG] Total Scan Completed in {elapsed:.2f} seconds. Matches: {len(raw_rows)}", flush=True)

    try:
        rendered_html = render_template(
            "index.html",
            rows=raw_rows,
            diagnostics=diagnostics,
            selected_tf=target_tf
        )
        return rendered_html
    except Exception as e:
        print(f"[RENDER ERROR] Failed rendering index.html: {e}", flush=True)
        traceback.print_exc()
        return f"<h1>Template Render Error</h1><pre>{e}</pre>", 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
