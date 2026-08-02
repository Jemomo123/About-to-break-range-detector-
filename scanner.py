# scanner.py
# =====================================================================
# VERSION 1.3 — PARALLEL MULTI-THREADED SCANNER PIPELINE
# =====================================================================

import json
import numpy as np
import requests
from concurrent.futures import ThreadPoolExecutor
from config import WATCHLIST
from app import (
    get_validated_range,
    calculate_status_engine,
    calculate_battle_engine,
    calculate_location_engine,
    calculate_breakout_readiness,
    generate_compact_evidence
)

OKX_TF_MAP = {"3m": "3m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H"}
MEXC_TF_MAP = {"3m": "Min3", "5m": "Min5", "15m": "Min15", "1h": "Min60", "4h": "Hour4"}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
}


def fetch_okx_klines(symbol, interval="1h", limit=100):
    okx_inst_id = f"{symbol.replace('USDT', '')}-USDT-SWAP"
    bar = OKX_TF_MAP.get(interval, "1H")
    url = f"https://www.okx.com/api/v5/market/candles?instId={okx_inst_id}&bar={bar}&limit={limit}"
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=3)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == "0" and data.get("data"):
                raw = data["data"]
                raw.reverse()
                highs = np.array([float(k[2]) for k in raw])
                lows = np.array([float(k[3]) for k in raw])
                closes = np.array([float(k[4]) for k in raw])
                volumes = np.array([float(k[5]) for k in raw])
                taker_buy_volumes = volumes * 0.5
                return highs, lows, closes, volumes, taker_buy_volumes
    except Exception:
        pass
    return None, None, None, None, None


def fetch_mexc_klines(symbol, interval="1h", limit=100):
    mexc_symbol = f"{symbol.replace('USDT', '')}_USDT"
    interval_param = MEXC_TF_MAP.get(interval, "Min60")
    url = f"https://contract.mexc.com/api/v1/contract/kline/{mexc_symbol}?interval={interval_param}"
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=3)
        if res.status_code == 200:
            data = res.json()
            if data.get("success") and data.get("data"):
                kdata = data["data"]
                highs = np.array([float(x) for x in kdata["high"][-limit:]])
                lows = np.array([float(x) for x in kdata["low"][-limit:]])
                closes = np.array([float(x) for x in kdata["close"][-limit:]])
                volumes = np.array([float(x) for x in kdata["vol"][-limit:]])
                taker_buy_volumes = volumes * 0.5
                return highs, lows, closes, volumes, taker_buy_volumes
    except Exception:
        pass
    return None, None, None, None, None


def fetch_klines_with_fallback(symbol, interval="1h", limit=100):
    highs, lows, closes, volumes, taker = fetch_okx_klines(symbol, interval, limit)
    if closes is not None and len(closes) >= 50:
        return highs, lows, closes, volumes, taker

    highs, lows, closes, volumes, taker = fetch_mexc_klines(symbol, interval, limit)
    if closes is not None and len(closes) >= 50:
        return highs, lows, closes, volumes, taker

    return None, None, None, None, None


def process_symbol_data(symbol, timeframe="1h"):
    highs, lows, closes, volumes, taker_buy = fetch_klines_with_fallback(symbol, interval=timeframe)

    if closes is None or len(closes) < 50:
        return {
            "symbol": symbol,
            "readiness_display": "N/A",
            "direction": "NO DATA",
            "status_label": "NO DATA",
            "battle_label": "NO DATA",
            "location_label": "NO DATA",
            "evidence": "Market data unavailable for this symbol.",
            "readiness_score": -1
        }

    val_range = get_validated_range(highs, lows, closes, volumes, lookback_window=50)
    status = calculate_status_engine(highs, lows, closes, val_range)
    battle = calculate_battle_engine(volumes, taker_buy_volumes=taker_buy)
    location = calculate_location_engine(closes, val_range)

    readiness = calculate_breakout_readiness(
        status["status_score"],
        battle["battle_score"],
        location["location_score"],
        val_range,
        battle_label=battle["battle_label"],
        position_pct=location.get("position_pct", 50.0)
    )

    evidence = generate_compact_evidence(status, battle, location, readiness, val_range)

    return {
        "symbol": symbol,
        "readiness_display": f"{readiness['readiness_score']}% ({readiness['readiness_label']})",
        "direction": readiness["direction"],
        "status_label": status["status_label"],
        "battle_label": battle["battle_label"],
        "location_label": location["location_label"],
        "evidence": evidence,
        "readiness_score": readiness["readiness_score"]
    }


def run_scanner_pipeline(symbols=None, timeframe="1h"):
    if symbols is None:
        symbols = WATCHLIST

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_symbol_data, sym, timeframe) for sym in symbols]
        results = [f.result() for f in futures]

    results.sort(key=lambda x: x["readiness_score"], reverse=True)
    return results
