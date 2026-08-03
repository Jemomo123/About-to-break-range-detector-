# scanner.py
# =====================================================================
# VERSION 1.8 — EXCLUSIVE OKX SCANNER WITH DIRECT APP.PY INTEGRATION
# =====================================================================

import logging
import numpy as np
import requests
from concurrent.futures import ThreadPoolExecutor
from config import WATCHLIST

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OKX_TF_MAP = {
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1H",
    "4h": "4H"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
}


def fetch_okx_klines(symbol, interval="1h", limit=100):
    coin_prefix = symbol.replace("USDT", "")
    okx_inst_id = f"{coin_prefix}-USDT-SWAP"
    bar = OKX_TF_MAP.get(interval, "1H")
    url = f"https://www.okx.com/api/v5/market/candles?instId={okx_inst_id}&bar={bar}&limit={limit}"
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=4)
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
            else:
                logging.warning(f"OKX returned empty data for {okx_inst_id}")
        else:
            logging.warning(f"OKX HTTP {res.status_code} for {okx_inst_id}")
    except Exception as e:
        logging.error(f"OKX request error for {symbol}: {e}")
        
    return None, None, None, None, None


def process_symbol_data(symbol, timeframe="1h"):
    # Import engines locally inside function to avoid circular import issues
    from app import (
        get_validated_range,
        calculate_status_engine,
        calculate_battle_engine,
        calculate_location_engine,
        calculate_breakout_readiness,
        generate_compact_evidence
    )

    try:
        highs, lows, closes, volumes, taker_buy = fetch_okx_klines(symbol, interval=timeframe)

        if closes is None or len(closes) < 50:
            logging.warning(f"Skipping {symbol}: Insufficient candle data.")
            return None

        # Execute app.py processing pipeline
        val_range = get_validated_range(highs, lows, closes, volumes, lookback_window=50)
        if val_range is None:
            return None

        status = calculate_status_engine(highs, lows, closes, val_range)
        battle = calculate_battle_engine(volumes, taker_buy_volumes=taker_buy)
        location = calculate_location_engine(closes, val_range)

        readiness = calculate_breakout_readiness(
            status["status_score"],
            battle["battle_score"],
            location["location_score"],
            val_range,
            battle_label=battle.get("battle_label", "BALANCED"),
            position_pct=location.get("position_pct", 50.0)
        )

        evidence = generate_compact_evidence(status, battle, location, readiness, val_range)

        # Distance calculation
        current_price = closes[-1]
        dist_to_high = abs(val_range["v_high"] - current_price) / current_price * 100
        dist_to_low = abs(current_price - val_range["v_low"]) / current_price * 100
        min_dist = round(min(dist_to_high, dist_to_low), 2)

        # Format exact UPPERCASE keys expected by index.html
        return {
            "SYMBOL": symbol,
            "BREAKOUT_READINESS": f"{readiness['readiness_score']}% ({readiness['readiness_label']})",
            "DIRECTION": readiness["direction"],
            "RESISTANCE": f"{val_range['v_high']:.4f}".rstrip('0').rstrip('.'),
            "SUPPORT": f"{val_range['v_low']:.4f}".rstrip('0').rstrip('.'),
            "DISTANCE": f"{min_dist}%",
            "EVIDENCE": evidence,
            "READINESS_SCORE": readiness["readiness_score"]
        }

    except Exception as e:
        logging.error(f"Error executing scanner for {symbol}: {e}")
        return None


def run_scanner_pipeline(symbols=None, timeframe="1h"):
    if symbols is None:
        symbols = WATCHLIST

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_symbol_data, sym, timeframe) for sym in symbols]
        raw_results = [f.result() for f in futures]

    valid_results = [r for r in raw_results if r is not None]
    valid_results.sort(key=lambda x: x["READINESS_SCORE"], reverse=True)
    
    return valid_results
