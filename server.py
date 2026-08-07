# server.py
# Gunicorn entry point for Render.
# The background worker is started automatically on the first HTTP request via app.before_request.

from app import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
