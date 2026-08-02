# scanner.py
# =====================================================================
# VERSION 1.2 — MULTI-EXCHANGE FETCH (OKX -> MEXC FALLBACK)
# =====================================================================

import urllib.request
import json
import numpy as np
from app import (
    get_validated_range,
    calculate_status_engine,
    calculate_battle_engine,
    calculate_location_engine,
    calculate_breakout_readiness,
    generate_compact_evidence
)

# Timeframe mapping for OKX and MEXC APIs
OKX_TF_MAP = {"3m": "3m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H"}
MEXC_TF_MAP = {"3m": "Min3", "5m": "Min5", "15m": "Min15", "1h": "Min60", "4h": "Hour4"}

def fetch_okx_klines(symbol, interval="1h", limit=100):
    """
    Primary Fetch: OKX Perpetual Futures Klines
    """
    okx_inst_id = f"{symbol.replace('USDT', '')}-USDT-SWAP"
    bar = OKX_TF_MAP.get(interval, "1H")
    url = f"https://www.okx.com/api/v5/market/candles?instId={okx_inst_id}&bar={bar}&limit={limit}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                if data.get("code") == "0" and data.get("data"):
                    raw = data["data"]
                    raw.reverse() # Sort oldest to newest
                    highs = np.array([float(k[2]) for k in raw])
                    lows = np.array([float(k[3]) for k in raw])
                    closes = np.array([float(k[4]) for k in raw])
                    volumes = np.array([float(k[5]) for k in raw])
                    taker_buy_volumes = volumes * 0.5
                    return highs, lows, closes, volumes, taker_buy_volumes
    except Exception as e:
        print(f"OKX Fetch Failed for {symbol} ({interval}): {e}")
        
    return None, None, None, None, None


def fetch_mexc_klines(symbol, interval="1h", limit=100):
    """
    Fallback Fetch: MEXC Contract/Futures Klines
    """
    mexc_symbol = f"{symbol.replace('USDT', '')}_USDT"
    interval_param = MEXC_TF_MAP.get(interval, "Min60")
    url = f"https://contract.mexc.com/api/v1/contract/kline/{mexc_symbol}?interval={interval_param}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            if response.status == 200:
                res = json.loads(response.read().decode('utf-8'))
                if res.get("success") and res.get("data"):
                    data = res["data"]
                    highs = np.array([float(x) for x in data["high"][-limit:]])
                    lows = np.array([float(x) for x in data["low"][-limit:]])
                    closes = np.array([float(x) for x in data["close"][-limit:]])
                    volumes = np.array([float(x) for x in data["vol"][-limit:]])
                    taker_buy_volumes = volumes * 0.5
                    return highs, lows, closes, volumes, taker_buy_volumes
    except Exception as e:
        print(f"MEXC Fetch Failed for {symbol} ({interval}): {e}")
        
    return None, None, None, None, None


def fetch_klines_with_fallback(symbol, interval="1h", limit=100):
    """
    Fetches data from OKX Futures first; automatically falls back to MEXC Futures.
    """
    highs, lows, closes, volumes, taker_buy = fetch_okx_klines(symbol, interval, limit)
    
    if closes is not None and len(closes) > 0:
        return highs, lows, closes, volumes, taker_buy, "OKX"

    print(f"Switching to MEXC Fallback for {symbol}...")
    highs, lows, closes, volumes, taker_buy = fetch_mexc_klines(symbol, interval, limit)
    
    if closes is not None and len(closes) > 0:
        return highs, lows, closes, volumes, taker_buy, "MEXC"

    return None, None, None, None, None, "NONE"


def run_scanner_pipeline(symbols, timeframe="1h"):
    rows = []
    
    for symbol in symbols:
        highs, lows, closes, volumes, taker_buy_vols, exchange_used = fetch_klines_with_fallback(symbol, interval=timeframe)
        
        if closes is None:
            continue

        val_range = get_validated_range(highs, lows, closes, volumes)
        status = calculate_status_engine(highs, lows, closes, val_range)
        battle = calculate_battle_engine(volumes, taker_buy_vols)
        location = calculate_location_engine(closes, val_range)
        readiness = calculate_breakout_readiness(
            status["status_score"],
            battle["battle_score"],
            location["location_score"],
            val_range
        )
        evidence = generate_compact_evidence(status, battle, location, readiness, val_range)

        curr_price = float(closes[-1])
        res_price = val_range["v_high"] if val_range else curr_price
        sup_price = val_range["v_low"] if val_range else curr_price
        range_size = val_range["r_height"] if val_range else 0.0
        dist_res_val = res_price - curr_price
        dist_sup_val = curr_price - sup_price
        dist_res_pct = round((dist_res_val / curr_price) * 100.0, 2) if curr_price > 0 else 0.0
        dist_sup_pct = round((dist_sup_val / curr_price) * 100.0, 2) if curr_price > 0 else 0.0

        rows.append({
            "SYMBOL": symbol,
            "TIMEFRAME": timeframe,
            "STATUS": f"{status['status_label']} ({status['status_score']}%)",
            "BATTLE": battle['battle_label'],
            "LOCATION": location['location_label'],
            "BREAKOUT READINESS": f"{readiness['readiness_score']}% ({readiness['readiness_label']})",
            "READINESS_SCORE": readiness['readiness_score'],
            "EVIDENCE": evidence,
            "EXCHANGE": exchange_used,
            "CURRENT_PRICE": f"{curr_price:.4f}",
            "RES_PRICE": f"{res_price:.4f}",
            "SUP_PRICE": f"{sup_price:.4f}",
            "RANGE_SIZE": f"{range_size:.4f}",
            "DIST_RES": f"${dist_res_val:.4f} ({dist_res_pct}%)",
            "DIST_SUP": f"${dist_sup_val:.4f} ({dist_sup_pct}%)"
        })

    rows.sort(key=lambda x: x["READINESS_SCORE"], reverse=True)
    return rows

fetch_and_process_market_data = run_scanner_pipeline
