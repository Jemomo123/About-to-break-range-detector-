import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ===== CONFIGURATION =====
DEBUG = True
PROXIMITY_THRESHOLD = 1.5
# =========================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ---- SHARED STATE (exported to app.py) ----
CACHE = {}
CACHE_LOCK = threading.Lock()
SCAN_READY = False
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()

# ---- UNSUPPORTED SYMBOLS CACHE ----
UNSUPPORTED_SYMBOLS = set()
UNSUPPORTED_LOCK = threading.Lock()

# ---- RANGE STATE ----
RANGE_STATE = {}
RANGE_STATE_LOCK = threading.Lock()

# ---- DEFAULT WATCHLIST ----
DEFAULT_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT", "BONKUSDT", 
    "SHIBUSDT", "USELESSUSDT", "SPACEUSDT", "MOVEUSDT", "ZECUSDT", 
    "SPXUSDT", "PEOPLEUSDT", "PENGUUSDT", "FARTCOINUSDT", "LINEAUSDT", 
    "MEMEUSDT", "PUMPUSDT", "AIXBTUSDT", "BRETTUSDT", "FOGOUSDT", 
    "GOOGLUSDT", "FLOKIUSDT", "IWMUSDT", "MOODENGUSDT", "NEARUSDT"
]

# ---- HELPER FUNCTIONS (unchanged) ----
def is_unsupported(symbol):
    with UNSUPPORTED_LOCK:
        return symbol in UNSUPPORTED_SYMBOLS

def mark_unsupported(symbol):
    with UNSUPPORTED_LOCK:
        UNSUPPORTED_SYMBOLS.add(symbol)

def get_existing_range(symbol, timeframe):
    key = f"{symbol}_{timeframe}"
    with RANGE_STATE_LOCK:
        return RANGE_STATE.get(key, None)

def set_range(symbol, timeframe, range_data):
    key = f"{symbol}_{timeframe}"
    with RANGE_STATE_LOCK:
        RANGE_STATE[key] = range_data

def get_timeframe_seconds(timeframe: str) -> int:
    mapping = {"5M": 300, "15M": 900, "1H": 3600, "4H": 14400}
    return mapping.get(timeframe, 900)

def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 150):
    """
    Fetch OHLCV data with explicit timeout (connect=5s, read=15s).
    Returns DataFrame or empty DataFrame on failure.
    """
    if is_unsupported(symbol):
        return pd.DataFrame()

    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    if not clean_sym.endswith("USDT"):
        clean_sym += "USDT"

    okx_tf_map = {"5M": "5m", "15M": "15m", "1H": "1H", "4H": "4H"}
    okx_bar = okx_tf_map.get(timeframe, "15m")

    # ---- OKX Spot ----
    okx_spot_sym = f"{clean_sym[:-4]}-USDT"
    okx_spot_url = f"https://www.okx.com/api/v5/market/candles?instId={okx_spot_sym}&bar={okx_bar}&limit={limit}"
    print(f"[FETCH] {symbol} {timeframe} -> {okx_spot_url}")
    try:
        resp = requests.get(okx_spot_url, headers=HEADERS, timeout=(5, 15))   # connect, read timeout
        print(f"[FETCH] {symbol} {timeframe} status={resp.status_code}")
        if resp.status_code == 200:
            res_json = resp.json()
            code = res_json.get("code")
            data = res_json.get("data", [])
            if code == "0" and isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'volCcy', 'volCcyQuote', 'confirm'
                ])
                df = df.iloc[::-1].reset_index(drop=True)
                df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                df = df.dropna(subset=['timestamp'])
                if df.empty:
                    print(f"[FETCH] {symbol} {timeframe} all timestamps non-numeric")
                    return pd.DataFrame()
                df['timestamp_dt'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True, errors='coerce')
                valid_count = df['timestamp_dt'].notna().sum()
                if valid_count == 0:
                    print(f"[FETCH] {symbol} {timeframe} all timestamps invalid")
                    return pd.DataFrame()
                df = df.dropna(subset=['timestamp_dt'])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                print(f"[FETCH] {symbol} {timeframe} SUCCESS, {len(df)} candles")
                return df
            else:
                print(f"[FETCH] {symbol} {timeframe} empty or code {code}")
                return pd.DataFrame()
        else:
            print(f"[FETCH] {symbol} {timeframe} HTTP {resp.status_code}")
            return pd.DataFrame()
    except requests.exceptions.Timeout as e:
        print(f"[FETCH] {symbol} {timeframe} TIMEOUT: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"[FETCH] {symbol} {timeframe} EXCEPTION: {e}")
        return pd.DataFrame()

# ---- The rest of the helper functions (unchanged) ----
# ... (keep all existing helpers: find_swings, cluster_prices, etc.)
# I will include them in the final file; for brevity I'll skip them here.

def _process_symbol_tf(symbol: str, tf: str):
    """
    Process a single symbol/timeframe with full error handling.
    Returns (result_dict, error_string) or (None, error_string).
    """
    print(f"[PROCESS] START {symbol} {tf}")
    try:
        if is_unsupported(symbol):
            print(f"[PROCESS] {symbol} {tf} UNSUPPORTED")
            return None, "UNSUPPORTED"
        df = fetch_ohlcv(symbol, tf)
        if df.empty:
            print(f"[PROCESS] {symbol} {tf} NO DATA")
            return None, "DATA UNAVAILABLE"
        result, err = analyze_level_battle(df, symbol, tf)
        if result:
            print(f"[PROCESS] {symbol} {tf} COMPLETE (readiness={result.get('readiness_score',0)})")
        else:
            print(f"[PROCESS] {symbol} {tf} FAILED: {err}")
        return result, err
    except Exception as e:
        print(f"[PROCESS] {symbol} {tf} EXCEPTION: {e}")
        return None, str(e)

# ---- The authoritative scanner worker ----
def start_authoritative_scanner():
    """Start the single authoritative background scanner with detailed logging."""
    global _WORKER_STARTED, SCAN_READY
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            print(">>> BACKGROUND SCANNER ALREADY STARTED — SKIPPING")
            return
        _WORKER_STARTED = True

    print(">>> BACKGROUND SCANNER STARTED — AUTHORITATIVE")
    print(">>> SCAN ORDER: 15M -> 5M -> 1H -> 4H")
    print(">>> DEFAULT TIMEFRAME: 15M")

    first_cycle = True

    def run_scan_cycle():
        nonlocal first_cycle
        while True:
            try:
                for tf in ["15M", "5M", "1H", "4H"]:
                    print(f"\n>>> BEGIN {tf} SCAN")
                    total_symbols = len(DEFAULT_WATCHLIST)
                    processed = 0
                    completed_count = 0
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        future_map = {executor.submit(_process_symbol_tf, sym, tf): sym for sym in DEFAULT_WATCHLIST}
                        for future in as_completed(future_map):
                            sym = future_map[future]
                            processed += 1
                            try:
                                res, err = future.result(timeout=0)  # result is already available
                            except Exception as e:
                                print(f"[WORKER] {sym} {tf} future exception: {e}")
                                res = None
                                err = str(e)
                            if res:
                                with CACHE_LOCK:
                                    CACHE[f"{sym}_{tf}"] = res
                                    completed_count += 1
                                    if first_cycle and tf == "15M" and not SCAN_READY:
                                        SCAN_READY = True
                                        print(">>> SCAN_READY = True (first 15M result)")
                                print(f"[CACHE] Stored {sym} {tf} (Cache size: {len(CACHE)})")
                            else:
                                print(f"[CACHE] Failed {sym} {tf}: {err}")
                            print(f"[PROGRESS] {tf} {processed}/{total_symbols} symbols processed")
                            # Update scan_status if needed (handled in app.py via CACHE size)
                    print(f">>> COMPLETED {tf} — {processed}/{total_symbols} symbols processed")
                    print(f">>> CACHE SIZE: {len(CACHE)}")
                    if first_cycle and tf == "15M":
                        print(">>> 15M FIRST CYCLE COMPLETE — 15M DATA READY")
                    time.sleep(1)
                first_cycle = False
                print(">>> FULL CYCLE COMPLETE. SLEEPING 15s...")
                time.sleep(15)
            except Exception as e:
                print(f"!!! Worker exception: {e}")
                time.sleep(5)

    thread = threading.Thread(target=run_scan_cycle, daemon=True)
    thread.start()

# ---- The rest of the helper functions (unchanged) ----
# They are identical to your previous version; I'll include them in the final file.
