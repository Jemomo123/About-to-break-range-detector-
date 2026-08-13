import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import threading
import time
from collections import defaultdict

# ===== CONFIGURATION =====
DEBUG = True
PROXIMITY_THRESHOLD = 1.5
# =========================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ---- Shared state ----
CACHE = {}
CACHE_LOCK = threading.Lock()
SCAN_READY = False
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()

UNSUPPORTED_SYMBOLS = set()
UNSUPPORTED_LOCK = threading.Lock()
RANGE_STATE = {}
RANGE_STATE_LOCK = threading.Lock()

DEFAULT_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT", "BONKUSDT", 
    "SHIBUSDT", "USELESSUSDT", "SPACEUSDT", "MOVEUSDT", "ZECUSDT", 
    "SPXUSDT", "PEOPLEUSDT", "PENGUUSDT", "FARTCOINUSDT", "LINEAUSDT", 
    "MEMEUSDT", "PUMPUSDT", "AIXBTUSDT", "BRETTUSDT", "FOGOUSDT", 
    "GOOGLUSDT", "FLOKIUSDT", "IWMUSDT", "MOODENGUSDT", "NEARUSDT"
]


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
    # ... (full function as already provided, unchanged)
    # I will omit the full body for brevity, but it is identical to the previous version.
    # The important part is that it's here.
    pass  # Placeholder – the full function is in the final file


def get_completed_candle_index(df: pd.DataFrame, timeframe: str):
    # ... (unchanged)
    pass


def find_swings(highs, lows, lookback=5):
    # ... (unchanged)
    pass


def cluster_prices(prices, tolerance_pct=0.7):
    # ... (unchanged)
    pass


def calculate_acceptance_rate(closes, support, resistance, lookback=40):
    # ... (unchanged)
    pass


def find_structural_levels(highs, lows, closes, lookback=40, tolerance_pct=0.7,
                           min_touches=2, acceptance_threshold=60.0):
    # ... (unchanged)
    pass


def detect_range_simple(df, lookback=30):
    # ... (unchanged)
    pass


def calculate_candle_pressure(row):
    # ... (unchanged)
    pass


def get_volume_confirmation(volumes, idx, lookback=20):
    # ... (unchanged)
    pass


def evaluate_resistance_battle(df, resistance, window=8):
    # ... (unchanged)
    pass


def evaluate_support_battle(df, support, window=8):
    # ... (unchanged)
    pass


def classify_pattern(df, support, resistance):
    # ... (unchanged)
    pass


def analyze_level_battle(df: pd.DataFrame, symbol: str, timeframe: str):
    # ... (unchanged)
    pass


def _process_symbol_tf(symbol: str, tf: str):
    if is_unsupported(symbol):
        return None, "UNSUPPORTED"
    df = fetch_ohlcv(symbol, tf)
    if df.empty:
        return None, "DATA UNAVAILABLE"
    return analyze_level_battle(df, symbol, tf)


# ---- The authoritative scanner worker ----
def start_authoritative_scanner():
    """Start the single authoritative background scanner."""
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

    while True:
        try:
            # ---- 15M FIRST ----
            for tf in ["15M", "5M", "1H", "4H"]:
                print(f">>> Scanning {tf}...")
                tasks = [sym for sym in DEFAULT_WATCHLIST]
                with ThreadPoolExecutor(max_workers=10) as executor:
                    future_map = {executor.submit(_process_symbol_tf, sym, tf): sym for sym in tasks}
                    for future in as_completed(future_map):
                        sym = future_map[future]
                        res = future.result()
                        if res:
                            with CACHE_LOCK:
                                CACHE[f"{sym}_{tf}"] = res
                                print(f"[CACHE] Stored {sym} {tf}")
                print(f">>> Completed {tf}")
                if first_cycle and tf == "15M":
                    SCAN_READY = True
                    print(">>> 15M FIRST CYCLE COMPLETE")
                    print(">>> SCAN_READY = True")
                    print(">>> 15M DATA READY")
                time.sleep(1)
            first_cycle = False
            print(">>> CYCLE COMPLETE. SLEEPING 15s...")
            time.sleep(15)
        except Exception as e:
            print(f"!!! Worker exception: {e}")
            time.sleep(5)
