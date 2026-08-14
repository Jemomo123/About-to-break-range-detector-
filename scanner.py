# ===== scanner.py – PROXY CONNECTIVITY PROBE =====

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import sys

# ===== CONFIGURATION =====
DEBUG = True
PROXIMITY_THRESHOLD = 1.5
# =========================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json'
}

UNSUPPORTED_SYMBOLS = set()
UNSUPPORTED_LOCK = threading.Lock()
RANGE_STATE = {}
RANGE_STATE_LOCK = threading.Lock()

# ---- Shared cache ----
CACHE = {}
CACHE_LOCK = threading.Lock()
SCAN_READY = False

# ---- FULL WATCHLIST (kept for reference) ----
DEFAULT_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT", "BONKUSDT", 
    "SHIBUSDT", "USELESSUSDT", "SPACEUSDT", "MOVEUSDT", "ZECUSDT", 
    "SPXUSDT", "PEOPLEUSDT", "PENGUUSDT", "FARTCOINUSDT", "LINEAUSDT", 
    "MEMEUSDT", "PUMPUSDT", "AIXBTUSDT", "BRETTUSDT", "FOGOUSDT", 
    "GOOGLUSDT", "FLOKIUSDT", "IWMUSDT", "MOODENGUSDT", "NEARUSDT"
]

# =============================================================
# CONNECTIVITY PROBE – PROXY PASS THROUGH
# =============================================================
def connectivity_probe():
    print("[PROBE] Starting connectivity probe (PROXY MODE)...")
    
    url = "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=15m&limit=150"
    proxy_url = f"https://corsproxy.io/?{url}"
    
    print(f"[PROBE] PROXY URL: {proxy_url}")
    print(f"[PROBE] Timeout: 30 seconds")
    
    try:
        print("[PROBE BEFORE REQUEST]")
        resp = requests.get(proxy_url, headers=HEADERS, timeout=30)
        print(f"[PROBE AFTER REQUEST] status={resp.status_code}")
        
        if resp.status_code == 200:
            try:
                data = resp.json()
                print(f"[PROBE] JSON parsed. Keys: {list(data.keys())}")
                if isinstance(data, dict) and data.get("code") == "0":
                    candles = data.get("data", [])
                    print(f"[PROBE] Candle count: {len(candles)}")
                    if len(candles) > 0:
                        print("[PROBE] SUCCESS – OKX data received via Proxy!")
                        return True, 200
                    else:
                        print("[PROBE] ERROR – Empty data array.")
                        return False, "empty_data"
                else:
                    print(f"[PROBE] ERROR – Unexpected JSON code: {data.get('code')}")
                    return False, "json_error"
            except Exception as e:
                print(f"[PROBE] JSON parse error: {e}")
                return False, "json_parse_error"
        else:
            print(f"[PROBE] HTTP error: {resp.status_code}")
            return False, f"http_{resp.status_code}"
            
    except requests.exceptions.Timeout as e:
        print(f"[PROBE TIMEOUT] {e}")
        return False, "timeout"
    except requests.exceptions.ConnectionError as e:
        print(f"[PROBE CONNECTION ERROR] {e}")
        return False, "connection_error"
    except Exception as e:
        print(f"[PROBE UNEXPECTED ERROR] {e}")
        return False, f"exception_{e}"

# ---- WORKER WITH ISOLATED TEST ----
def _process_symbol_tf(symbol: str, tf: str):
    return None, "DISABLED"

def update_cache_job():
    global SCAN_READY
    print(">>> BACKGROUND SCANNER STARTED (PROXY DIAGNOSTIC)")
    print(">>> RUNNING ISOLATED CONNECTIVITY PROBE...")
    
    success, result = connectivity_probe()
    
    if success:
        print(">>> PROBE RESULT: SUCCESS – Proxy Bypass Works!")
        SCAN_READY = True
        while True:
            time.sleep(60)
    else:
        print(f">>> PROBE RESULT: FAILED – {result}")
        SCAN_READY = False
        while True:
            time.sleep(60)

# ---- Start function for app.py ----
def start_authoritative_scanner():
    thread = threading.Thread(target=update_cache_job, daemon=True)
    thread.start()
    print(">>> Authoritative scanner started (proxy diagnostic mode).")
