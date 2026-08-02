# scanner.py
# =====================================================================
# VERSION 1.2 — SCANNER PIPELINE & WATCHLIST INTEGRATION
# =====================================================================

import urllib.request
import json
import numpy as np
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

def fetch_okx_klines(symbol, interval="1h", limit=100):
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
    except Exception:
        pass
    return None, None, None, None, None

def fetch_klines_with_fallback(symbol, interval="1h", limit=100):
    highs, lows, closes, volumes, taker_buy = fetch_okx_klines(symbol, interval, limit)
    if closes is not None and len(closes) > 0:
        return highs, lows, closes, volumes, taker_buy

    highs, lows, closes, volumes, taker_buy = fetch_mexc_klines(symbol, interval, limit)
    if closes is not None and len(closes) > 0:
        return highs, lows, closes, volumes, taker_buy

    return None, None, None, None, None

def run_scanner_pipeline(symbols=None, timeframe="1h"):
    if symbols is None:
        symbols = WATCHLIST

    results = []

    for symbol in symbols:
        try:
            highs, lows, closes, volumes, taker_buy_vols = fetch_klines_with_fallback(symbol, interval=timeframe)
            if closes is None:
                continue

            val_range = get_validated_range(highs, lows, closes, volumes)
            status = calculate_status_engine(highs, lows, closes, val_range)
            battle = calculate_battle_engine(volumes, taker_buy_volumes=taker_buy_vols)
            location = calculate_location_engine(closes, val_range)

            readiness = calculate_breakout_readiness(
                status_score=status["status_score"],
                battle_score=battle["battle_score"],
                location_score=location["location_score"],
                val_range=val_range,
                battle_label=battle["battle_label"],
                position_pct=location.get("position_pct", 50.0)
            )

            evidence_text = generate_compact_evidence(status, battle, location, readiness, val_range)

            curr_price = float(closes[-1])
            res_price = val_range["v_high"] if val_range else curr_price
            sup_price = val_range["v_low"] if val_range else curr_price

            dist_res_pct = ((res_price - curr_price) / curr_price) * 100.0 if curr_price > 0 else 0.0
            dist_sup_pct = ((curr_price - sup_price) / curr_price) * 100.0 if curr_price > 0 else 0.0
            nearest_distance_pct = min(abs(dist_res_pct), abs(dist_sup_pct))

            raw_dir = readiness.get("direction", "NEUTRAL").upper()
            if "UPSIDE" in raw_dir:
                clean_direction = "UPSIDE"
            elif "DOWNSIDE" in raw_dir:
                clean_direction = "DOWNSIDE"
            else:
                clean_direction = "BALANCED"

            results.append({
                "SYMBOL": symbol,
                "BREAKOUT_READINESS": f"{readiness['readiness_score']}% ({readiness['readiness_label']})",
                "READINESS_SCORE": readiness['readiness_score'],
                "DIRECTION": clean_direction,
                "RESISTANCE": f"{res_price:.4f}",
                "SUPPORT": f"{sup_price:.4f}",
                "DISTANCE": f"{nearest_distance_pct:.2f}%",
                "EVIDENCE": evidence_text,
                "STATUS_LABEL": status['status_label'],
                "BATTLE_LABEL": battle['battle_label'],
                "LOCATION_LABEL": location['location_label']
            })

        except Exception:
            continue

    results.sort(key=lambda x: x["READINESS_SCORE"], reverse=True)
    return results
