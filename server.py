# server.py
# =====================================================================
# GUNICORN / RENDER ENTRY POINT (VERSION 1.0 STABLE)
# =====================================================================

import threading
from app import app, update_cache_job

# Start background scanner thread on app startup
worker_thread = threading.Thread(target=update_cache_job, daemon=True)
worker_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
