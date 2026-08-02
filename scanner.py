# scanner.py
# =====================================================================
# VERSION 1.7 — EXCLUSIVE OKX SCANNER PIPELINE
# =====================================================================

import logging
import numpy as np
import requests
from concurrent.futures import ThreadPoolExecutor
from config import WATCHLIST

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# OKX Timeframe Mapping for 3m, 5m, 15m, 1h, 4h
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
    # Formats standard symbol (e.g., BTCUSDT) into OKX Swap Instrument ID (e.g., BTC-USDT-SWAP)
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
                raw.reverse()  # Reverse to chronological order (oldest -> newest)
                
                highs = np.array([float(k[2]) for k in raw])
                lows = np.array([float(k[3]) for k in raw])
                closes = np.array([float(k[4]) for k in raw])
                volumes = np.array([float(k[5]) for k in raw])
                taker_buy_volumes = volumes * 0.5  # Estimated volume proxy
                
                return highs, lows, closes, volumes, taker_buy_volumes
            else:
                logging.warning(f"OKX returned empty data for {okx_inst_id}")
        else:
            logging.warning(f"OKX HTTP {res.status_code} for {okx_inst_id}")
    except Exception as e:
        logging.error(f"OKX request error for {symbol}: {e}")
        
    return None, None, None, None, None


def process_symbol_data(symbol, timeframe="1h"):
    try:
        highs, lows, closes, volumes, taker_buy = fetch_okx_klines(symbol, interval=timeframe)

        if closes is None or len(closes) < 50:
            logging.warning(f"Skipping {symbol}: Insufficient candle data.")
            return None

        # 1. Range Calculations (Lookback: 50 candles)
        recent_highs = highs[-50:]
        recent_lows = lows[-50:]
        range_high = float(np.max(recent_highs))
        range_low = float(np.min(recent_lows))
        range_height = range_high - range_low
        current_price = float(closes[-1])

        if range_height <= 0:
            return None

        # 2. Compression Ratio (20-period vs 5-period average range)
        window = 20
        ranges = highs[-window:] - lows[-window:]
        avg_range = np.mean(ranges)
        recent_avg_range = np.mean(ranges[-5:])
        compression_ratio = float(recent_avg_range / avg_range) if avg_range > 0 else 1.0

        # 3. Location & Distance Metrics
        position_pct = ((current_price - range_low) / range_height) * 100.0
        dist_to_high = abs(range_high - current_price) / current_price * 100
        dist_to_low = abs(current_price - range_low) / current_price * 100
        distance_to_breakout = round(min(dist_to_high, dist_to_low), 2)

        direction = "BULLISH" if position_pct >= 50.0 else "BEARISH"

        # 4. Engine Scores
        status_score = 90 if compression_ratio < 0.6 else (70 if compression_ratio < 0.8 else 40)
        location_score = 90 if (position_pct >= 80 or position_pct <= 20) else 40

        recent_vol = np.sum(volumes[-5:])
        recent_buy_vol = np.sum(taker_buy[-5:]) if taker_buy is not None else recent_vol * 0.5
        buy_ratio = (recent_buy_vol / recent_vol * 100) if recent_vol > 0 else 50.0
        battle_score = 85 if (buy_ratio >= 58 or buy_ratio <= 42) else 50

        # Weighted Readiness Score
        readiness_score = int(0.4 * status_score + 0.3 * battle_score + 0.3 * location_score)

        if readiness_score >= 80:
            readiness_label = "IMMINENT"
        elif readiness_score >= 65:
            readiness_label = "BUILDING"
        else:
            readiness_label = "DEVELOPING"

        return {
            "symbol": symbol,
            "breakout_readiness": f"{readiness_score}% ({readiness_label})",
            "readiness_display": f"{readiness_score}% ({readiness_label})",
            "readiness_score": readiness_score,
            "direction": direction,
            "resistance": range_high,
            "support": range_low,
            "distance": f"{distance_to_breakout}%",
            "current_price": current_price,
            "buy_ratio": round(buy_ratio, 1),
            "compression_ratio": round(compression_ratio, 2)
        }

    except Exception as e:
        logging.error(f"Error executing scanner for {symbol}: {e}")
        return None


def run_scanner_pipeline(symbols=None, timeframe="1h"):
    if symbols is None:
        symbols = WATCHLIST

    # Execute requests concurrently to keep load times under 2 seconds
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_symbol_data, sym, timeframe) for sym in symbols]
        raw_results = [f.result() for f in futures]

    # Exclude failed or skipped symbols
    valid_results = [r for r in raw_results if r is not None]
    valid_results.sort(key=lambda x: x["readiness_score"], reverse=True)
    
    return valid_results
