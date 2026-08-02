# scanner.py
# =====================================================================
# VERSION 1.2.1 — BINANCE FETCH & PIPELINE EXECUTOR
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

def fetch_binance_klines(symbol, interval="1h", limit=100):
    """
    Fetches spot/futures klines from Binance API for the requested interval.
    """
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                highs = np.array([float(k[2]) for k in data])
                lows = np.array([float(k[3]) for k in data])
                closes = np.array([float(k[4]) for k in data])
                volumes = np.array([float(k[5]) for k in data])
                taker_buy_volumes = np.array([float(k[9]) for k in data])
                return highs, lows, closes, volumes, taker_buy_volumes
    except Exception as e:
        print(f"Error fetching {symbol} on {interval}: {e}")
        
    return None, None, None, None, None


def run_scanner_pipeline(symbols, timeframe="1h"):
    """
    Executes core engine pipeline for the specified symbols and timeframe parameter.
    Module-level function required by server.py / app.py.
    """
    rows = []
    
    for symbol in symbols:
        highs, lows, closes, volumes, taker_buy_vols = fetch_binance_klines(symbol, interval=timeframe)
        
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

        rows.append({
            "SYMBOL": symbol,
            "TIMEFRAME": timeframe,
            "STATUS": f"{status['status_label']} ({status['status_score']})",
            "BATTLE": battle['battle_label'],
            "LOCATION": location['location_label'],
            "BREAKOUT READINESS": f"{readiness['readiness_score']} ({readiness['readiness_label']})",
            "EVIDENCE": evidence
        })

    return rows

# Alias for backward compatibility across modules
fetch_and_process_market_data = run_scanner_pipeline
