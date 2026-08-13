# ===== scanner.py – FINAL DIAGNOSTIC =====
# Only BTCUSDT, ETHUSDT, SOLUSDT on 15M are scanned.
# Uses ONLY OKX Futures (Swap) – no fallback.
# Hard timeouts and detailed logging added.
# All detection logic untouched.

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

UNSUPPORTED_SYMBOLS = set()
UNSUPPORTED_LOCK = threading.Lock()
RANGE_STATE = {}
RANGE_STATE_LOCK = threading.Lock()

# ---- Shared cache ----
CACHE = {}
CACHE_LOCK = threading.Lock()
SCAN_READY = False

# ---- FULL WATCHLIST (required for app.py) ----
DEFAULT_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT", "BONKUSDT", 
    "SHIBUSDT", "USELESSUSDT", "SPACEUSDT", "MOVEUSDT", "ZECUSDT", 
    "SPXUSDT", "PEOPLEUSDT", "PENGUUSDT", "FARTCOINUSDT", "LINEAUSDT", 
    "MEMEUSDT", "PUMPUSDT", "AIXBTUSDT", "BRETTUSDT", "FOGOUSDT", 
    "GOOGLUSDT", "FLOKIUSDT", "IWMUSDT", "MOODENGUSDT", "NEARUSDT"
]

# ---- DIAGNOSTIC SCOPE (only these are scanned) ----
DIAG_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
DIAG_TIMEFRAMES = ["15M"]

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

# =============================================================
# DIAGNOSTIC FETCH – ONLY OKX FUTURES, NO FALLBACK
# =============================================================
def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 150):
    if is_unsupported(symbol):
        return pd.DataFrame()

    print(f"[OKX FUTURES REQUEST START] {symbol} {timeframe}")

    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    if not clean_sym.endswith("USDT"):
        clean_sym += "USDT"

    okx_tf_map = {"5M": "5m", "15M": "15m", "1H": "1H", "4H": "4H"}
    okx_bar = okx_tf_map.get(timeframe, "15m")

    okx_swap_sym = f"{clean_sym[:-4]}-USDT-SWAP"
    okx_swap_url = f"https://www.okx.com/api/v5/market/candles?instId={okx_swap_sym}&bar={okx_bar}&limit={limit}"
    print(f"[OKX FUTURES URL] {symbol} {timeframe}: {okx_swap_url}")

    try:
        resp = requests.get(okx_swap_url, headers=HEADERS, timeout=(5, 10))
        print(f"[OKX FUTURES REQUEST SENT] {symbol} {timeframe}")
        print(f"[OKX FUTURES RESPONSE] {symbol} {timeframe} status={resp.status_code}")
        print(f"[OKX FUTURES RESPONSE LENGTH] {symbol} {timeframe} bytes={len(resp.content)}")

        if resp.status_code == 200:
            try:
                res_json = resp.json()
                print(f"[OKX FUTURES JSON PARSED] {symbol} {timeframe}")
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
                        print(f"[OKX FUTURES ERROR] {symbol} {timeframe} all timestamps non-numeric")
                        return pd.DataFrame()
                    df['timestamp_dt'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True, errors='coerce')
                    valid_count = df['timestamp_dt'].notna().sum()
                    if valid_count == 0:
                        print(f"[OKX FUTURES ERROR] {symbol} {timeframe} all timestamps invalid")
                        return pd.DataFrame()
                    df = df.dropna(subset=['timestamp_dt'])
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)
                    print(f"[OKX FUTURES CANDLE COUNT] {symbol} {timeframe} candles={len(df)}")
                    print(f"[OKX FUTURES SUCCESS] {symbol} {timeframe}")
                    return df
                else:
                    print(f"[OKX FUTURES ERROR] {symbol} {timeframe} empty or code {code}")
                    return pd.DataFrame()
            except Exception as e:
                print(f"[OKX FUTURES JSON ERROR] {symbol} {timeframe}: {e}")
                return pd.DataFrame()
        else:
            print(f"[OKX FUTURES HTTP ERROR] {symbol} {timeframe} status={resp.status_code}")
            return pd.DataFrame()
    except requests.exceptions.Timeout as e:
        print(f"[OKX FUTURES TIMEOUT] {symbol} {timeframe}: {e}")
        return pd.DataFrame()
    except requests.exceptions.ConnectionError as e:
        print(f"[OKX FUTURES CONNECTION ERROR] {symbol} {timeframe}: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"[OKX FUTURES ERROR] {symbol} {timeframe}: {e}")
        return pd.DataFrame()

# ---- The rest of the helper functions (unchanged from your original) ----
# They are identical to the original scanner.py. For brevity, they are not repeated here,
# but they must be present in the final file. This includes:
# find_swings, cluster_prices, calculate_acceptance_rate,
# find_structural_levels, detect_range_simple, calculate_candle_pressure,
# get_volume_confirmation, evaluate_resistance_battle, evaluate_support_battle,
# classify_pattern, analyze_level_battle, _process_symbol_tf.
#
# They remain exactly as they were in your production version.

# ---- WORKER WITH DIAGNOSTIC SCOPE ----
def _process_symbol_tf(symbol: str, tf: str):
    print(f"[PROCESSING START] {symbol} {tf}")
    if is_unsupported(symbol):
        print(f"[PROCESSING ERROR] {symbol} {tf} unsupported")
        return None, "UNSUPPORTED"
    df = fetch_ohlcv(symbol, tf)
    if df.empty:
        print(f"[PROCESSING ERROR] {symbol} {tf} no data")
        return None, "DATA UNAVAILABLE"
    result, err = analyze_level_battle(df, symbol, tf)
    if result:
        print(f"[PROCESSING COMPLETE] {symbol} {tf}")
    else:
        print(f"[PROCESSING ERROR] {symbol} {tf}: {err}")
    return result, err

def update_cache_job():
    global SCAN_READY
    print(">>> BACKGROUND SCANNER STARTED (DIAGNOSTIC)")
    print(">>> SYMBOLS: BTCUSDT, ETHUSDT, SOLUSDT")
    print(">>> TIMEFRAMES: 15M")
    total_symbols = len(DIAG_SYMBOLS)
    processed = 0

    while True:
        try:
            for tf in DIAG_TIMEFRAMES:
                print(f">>> Scanning {tf}...")
                tasks = [sym for sym in DIAG_SYMBOLS]
                with ThreadPoolExecutor(max_workers=3) as executor:
                    future_map = {executor.submit(_process_symbol_tf, sym, tf): sym for sym in tasks}
                    for future in as_completed(future_map):
                        sym = future_map[future]
                        processed += 1
                        res, err = future.result()
                        if res:
                            with CACHE_LOCK:
                                CACHE[f"{sym}_{tf}"] = res
                                print(f"[CACHE WRITE] {sym}_{tf}")
                        else:
                            print(f"[CACHE SKIP] {sym}_{tf}: {err}")
                        print(f"[PROGRESS] {tf} {processed}/{total_symbols} symbols processed")
                        if not SCAN_READY and res:
                            SCAN_READY = True
                            print(">>> SCAN_READY = True")
                print(f">>> Completed {tf}")
                time.sleep(2)
            print(">>> DIAGNOSTIC CYCLE COMPLETE. Sleeping 15s...")
            time.sleep(15)
        except Exception as e:
            print(f"!!! Worker exception: {e}")
            time.sleep(5)

# ---- Start function for app.py ----
def start_authoritative_scanner():
    """Start the diagnostic scanner. This matches the signature expected by app.py."""
    thread = threading.Thread(target=update_cache_job, daemon=True)
    thread.start()
    print(">>> Authoritative scanner started (diagnostic mode).")
