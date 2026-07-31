# server.py
# =====================================================================
# VERSION 1.0 — FLASK SERVER & WEB ROUTING ENGINE
# =====================================================================

import logging
from flask import Flask, render_template
from scanner import run_scanner_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route("/")
def index():
    """
    Renders the market scanner dashboard.
    Consumes rows directly from scanner.py pipeline.
    """
    try:
        rows = run_scanner_pipeline()
        return render_template("index.html", rows=rows)
    except Exception as e:
        logger.error(f"Error rendering scanner dashboard: {e}")
        return render_template("index.html", rows=[])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
