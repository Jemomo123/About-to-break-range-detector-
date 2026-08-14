# ===== scanner.py – HTTP CALL DIAGNOSTIC + 15M FIRST =====
# Adds explicit HTTP call logs and changes scan order to 15M -> 5M -> 1H -> 4H.
# All detection logic unchanged.

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

# ---- FULL WATCHLIST ----
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

# =============================================================
# FETCH WITH EXPLICIT HTTP CALL LOGGING
# =============================================================
def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 150):
    if is_unsupported(symbol):
        return pd.DataFrame()

    print(f"[FETCH START] {symbol} {timeframe}")

    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    if not clean_sym.endswith("USDT"):
        clean_sym += "USDT"

    okx_tf_map = {"5M": "5m", "15M": "15m", "1H": "1H", "4H": "4H"}
    okx_bar = okx_tf_map.get(timeframe, "15m")

    # ---- 1. OKX Spot ----
    okx_spot_sym = f"{clean_sym[:-4]}-USDT"
    okx_spot_url = f"https://www.okx.com/api/v5/market/candles?instId={okx_spot_sym}&bar={okx_bar}&limit={limit}"
    print(f"[OKX SPOT URL] {symbol} {timeframe}: {okx_spot_url}")

    try:
        # ---- LOG HTTP TIMEOUT CONFIG ----
        print(f"[HTTP TIMEOUT CONFIG] {symbol} {timeframe} (5, 10)")
        # ---- LOG ENTER ----
        print(f"[HTTP CALL ENTER] {symbol} {timeframe}")
        resp = requests.get(okx_spot_url, headers=HEADERS, timeout=(5, 10))
        # ---- LOG RETURN ----
        print(f"[HTTP CALL RETURN] {symbol} {timeframe}")
        print(f"[HTTP RESPONSE] {symbol} {timeframe} status={resp.status_code}")

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
                    print(f"[FETCH ERROR] {symbol} {timeframe} all timestamps non-numeric")
                    return pd.DataFrame()
                df['timestamp_dt'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True, errors='coerce')
                valid_count = df['timestamp_dt'].notna().sum()
                if valid_count == 0:
                    print(f"[FETCH ERROR] {symbol} {timeframe} all timestamps invalid")
                    return pd.DataFrame()
                df = df.dropna(subset=['timestamp_dt'])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                print(f"[FETCH SUCCESS] {symbol} {timeframe} candles={len(df)}")
                return df
            else:
                print(f"[FETCH ERROR] {symbol} {timeframe} empty or code {code}")
                # fall through to swap
        else:
            print(f"[FETCH ERROR] {symbol} {timeframe} HTTP {resp.status_code}")
    except requests.exceptions.Timeout as e:
        print(f"[HTTP CALL TIMEOUT] {symbol} {timeframe}: {repr(e)}")
        print(f"[OKX TIMEOUT] {symbol} {timeframe} -> trying swap...")
    except requests.exceptions.RequestException as e:
        print(f"[HTTP REQUEST ERROR] {symbol} {timeframe}: {repr(e)}")
        print(f"[OKX REQUEST ERROR] {symbol} {timeframe} -> trying swap...")
    except Exception as e:
        print(f"[HTTP UNEXPECTED ERROR] {symbol} {timeframe}: {repr(e)}")
        print(f"[FETCH ERROR] {symbol} {timeframe}: {e}")

    # ---- 2. OKX Swap ----
    okx_swap_sym = f"{clean_sym[:-4]}-USDT-SWAP"
    okx_swap_url = f"https://www.okx.com/api/v5/market/candles?instId={okx_swap_sym}&bar={okx_bar}&limit={limit}"
    print(f"[OKX SWAP URL] {symbol} {timeframe}: {okx_swap_url}")

    try:
        print(f"[HTTP TIMEOUT CONFIG] {symbol} {timeframe} (SWAP) (5, 10)")
        print(f"[HTTP CALL ENTER] {symbol} {timeframe} (SWAP)")
        resp = requests.get(okx_swap_url, headers=HEADERS, timeout=(5, 10))
        print(f"[HTTP CALL RETURN] {symbol} {timeframe} (SWAP)")
        print(f"[HTTP RESPONSE SWAP] {symbol} {timeframe} status={resp.status_code}")
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
                    print(f"[FETCH ERROR] {symbol} {timeframe} all timestamps non-numeric")
                    return pd.DataFrame()
                df['timestamp_dt'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True, errors='coerce')
                valid_count = df['timestamp_dt'].notna().sum()
                if valid_count == 0:
                    print(f"[FETCH ERROR] {symbol} {timeframe} all timestamps invalid")
                    return pd.DataFrame()
                df = df.dropna(subset=['timestamp_dt'])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                print(f"[FETCH SUCCESS] {symbol} {timeframe} candles={len(df)}")
                return df
            else:
                print(f"[FETCH ERROR] {symbol} {timeframe} empty or code {code}")
        else:
            print(f"[FETCH ERROR] {symbol} {timeframe} HTTP {resp.status_code}")
    except requests.exceptions.Timeout as e:
        print(f"[HTTP CALL TIMEOUT] {symbol} {timeframe} (SWAP): {repr(e)}")
        print(f"[OKX SWAP TIMEOUT] {symbol} {timeframe} -> trying MEXC...")
    except requests.exceptions.RequestException as e:
        print(f"[HTTP REQUEST ERROR] {symbol} {timeframe} (SWAP): {repr(e)}")
        print(f"[OKX SWAP REQUEST ERROR] {symbol} {timeframe} -> trying MEXC...")
    except Exception as e:
        print(f"[HTTP UNEXPECTED ERROR] {symbol} {timeframe} (SWAP): {repr(e)}")
        print(f"[FETCH ERROR] {symbol} {timeframe}: {e}")

    # ---- 3. MEXC Fallback ----
    mexc_tf_map = {"5M": "5m", "15M": "15m", "1H": "60m", "4H": "4h"}
    mexc_bar = mexc_tf_map.get(timeframe, "15m")
    mexc_url = f"https://api.mexc.com/api/v3/klines?symbol={clean_sym}&interval={mexc_bar}&limit={limit}"
    print(f"[MEXC URL] {symbol} {timeframe}: {mexc_url}")

    try:
        print(f"[HTTP TIMEOUT CONFIG] {symbol} {timeframe} (MEXC) (5, 10)")
        print(f"[HTTP CALL ENTER] {symbol} {timeframe} (MEXC)")
        resp = requests.get(mexc_url, headers=HEADERS, timeout=(5, 10))
        print(f"[HTTP CALL RETURN] {symbol} {timeframe} (MEXC)")
        print(f"[HTTP RESPONSE MEXC] {symbol} {timeframe} status={resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                parsed = []
                for row in data:
                    if len(row) >= 6:
                        parsed.append(row[:6])
                if parsed:
                    df = pd.DataFrame(parsed, columns=[
                        'timestamp', 'open', 'high', 'low', 'close', 'volume'
                    ])
                    df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                    df = df.dropna(subset=['timestamp'])
                    if df.empty:
                        return pd.DataFrame()
                    df['timestamp_dt'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True, errors='coerce')
                    df = df.dropna(subset=['timestamp_dt'])
                    if df.empty:
                        return pd.DataFrame()
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)
                    print(f"[FETCH SUCCESS] {symbol} {timeframe} candles={len(df)}")
                    return df
            else:
                print(f"[FETCH ERROR] {symbol} {timeframe} empty data")
        else:
            print(f"[FETCH ERROR] {symbol} {timeframe} HTTP {resp.status_code}")
    except requests.exceptions.Timeout as e:
        print(f"[HTTP CALL TIMEOUT] {symbol} {timeframe} (MEXC): {repr(e)}")
        print(f"[MEXC TIMEOUT] {symbol} {timeframe}")
    except requests.exceptions.RequestException as e:
        print(f"[HTTP REQUEST ERROR] {symbol} {timeframe} (MEXC): {repr(e)}")
        print(f"[MEXC REQUEST ERROR] {symbol} {timeframe}")
    except Exception as e:
        print(f"[HTTP UNEXPECTED ERROR] {symbol} {timeframe} (MEXC): {repr(e)}")
        print(f"[FETCH ERROR] {symbol} {timeframe}: {e}")

    print(f"[FETCH FAILED] {symbol} {timeframe} all sources failed")
    return pd.DataFrame()

# ---- The rest of the helper functions (unchanged) ----
# find_swings, cluster_prices, calculate_acceptance_rate,
# find_structural_levels, detect_range_simple, calculate_candle_pressure,
# get_volume_confirmation, evaluate_resistance_battle, evaluate_support_battle,
# classify_pattern, analyze_level_battle, _process_symbol_tf
# They are identical to the original scanner.py. For brevity, they are not repeated here.

# ---- WORKER WITH 15M FIRST ----
def _process_symbol_tf(symbol: str, tf: str):
    print(f"[PROCESSING START] {symbol} {tf}")
    if is_unsupported(symbol):
        return None, "UNSUPPORTED"
    df = fetch_ohlcv(symbol, tf)
    if df.empty:
        return None, "DATA UNAVAILABLE"
    result, err = analyze_level_battle(df, symbol, tf)
    if result:
        print(f"[PROCESSING COMPLETE] {symbol} {tf}")
    else:
        print(f"[PROCESSING ERROR] {symbol} {tf}: {err}")
    return result, err

def update_cache_job():
    global SCAN_READY
    print(">>> BACKGROUND SCANNER STARTED")
    # ---- 15M FIRST ----
    print(">>> SCAN ORDER: 15M -> 5M -> 1H -> 4H")
    first_data_received = False
    while True:
        try:
            for tf in ["15M", "5M", "1H", "4H"]:
                print(f">>> Scanning {tf}...")
                tasks = [sym for sym in DEFAULT_WATCHLIST]
                with ThreadPoolExecutor(max_workers=10) as executor:
                    future_map = {executor.submit(_process_symbol_tf, sym, tf): sym for sym in tasks}
                    for future in as_completed(future_map):
                        sym = future_map[future]
                        res, err = future.result()
                        if res:
                            with CACHE_LOCK:
                                CACHE[f"{sym}_{tf}"] = res
                                print(f"[CACHE] Stored {sym} {tf}")
                                if not first_data_received:
                                    first_data_received = True
                                    SCAN_READY = True
                                    print(">>> SCAN_READY = True")
                        else:
                            print(f"[CACHE] Failed {sym} {tf}: {err}")
                print(f">>> Completed {tf}")
                time.sleep(1)
            print(">>> Cycle complete. Sleeping 15s...")
            time.sleep(15)
        except Exception as e:
            print(f"!!! Worker exception: {e}")
            time.sleep(5)

# ---- Start function for app.py ----
def start_authoritative_scanner():
    thread = threading.Thread(target=update_cache_job, daemon=True)
    thread.start()
    print(">>> Authoritative scanner started.")
