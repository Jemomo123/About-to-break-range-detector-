# scanner.py
# =====================================================================
# VERSION 1.5 — ZERO-FAIL RESILIENT SCANNER PIPELINE
# =====================================================================

import logging
import numpy as np
import requests
from concurrent.futures import ThreadPoolExecutor
from config import WATCHLIST

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

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
    except Exception as e:
        logging.debug(f"OKX fetch error for {symbol}: {e}")
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
    except Exception as e:
        logging.debug(f"MEXC fetch error for {symbol}: {e}")
    return None, None, None, None, None


def fetch_klines_with_fallback(symbol, interval="1h", limit=100):
    # Try OKX
    highs, lows, closes, volumes, taker = fetch_okx_klines(symbol, interval, limit)
    if closes is not None and len(closes) >= 50:
        return highs, lows, closes, volumes, taker

    logging.info(f"OKX: {symbol} unavailable. Trying MEXC...")

    # Fallback to MEXC
    highs, lows, closes, volumes, taker = fetch_mexc_klines(symbol, interval, limit)
    if closes is not None and len(closes) >= 50:
        return highs, lows, closes, volumes, taker

    logging.warning(f"MEXC unavailable. Skipping {symbol}.")
    return None, None, None, None, None


def process_symbol_data(symbol, timeframe="1h"):
    try:
        highs, lows, closes, volumes, taker_buy = fetch_klines_with_fallback(symbol, interval=timeframe)

        if closes is None or len(closes) < 50:
            return None  # Skip symbol smoothly without sending invalid schema to UI

        # 1. Range Calculations
        recent_highs = highs[-50:]
        recent_lows = lows[-50:]
        range_high = float(np.max(recent_highs))
        range_low = float(np.min(recent_lows))
        range_height = range_high - range_low
        current_price = float(closes[-1])

        if range_height <= 0:
            return None

        # 2. Compression Calculation
        window = 20
        ranges = highs[-window:] - lows[-window:]
        avg_range = np.mean(ranges)
        recent_avg_range = np.mean(ranges[-5:])
        compression_ratio = float(recent_avg_range / avg_range) if avg_range > 0 else 1.0

        # 3. Location & Distance Calculations
        position_pct = ((current_price - range_low) / range_height) * 100.0
        
        # Distance to closest range boundary
        dist_to_high = abs(range_high - current_price) / current_price * 100
        dist_to_low = abs(current_price - range_low) / current_price * 100
        distance_to_breakout = round(min(dist_to_high, dist_to_low), 2)

        # Direction logic
        direction = "BULLISH" if position_pct >= 50.0 else "BEARISH"

        # 4. Readiness Score Matrix
        status_score = 90 if compression_ratio < 0.6 else (70 if compression_ratio < 0.8 else 40)
        location_score = 90 if (position_pct >= 80 or position_pct <= 20) else 40
        
        recent_vol = np.sum(volumes[-5:])
        recent_buy_vol = np.sum(taker_buy_volumes[-5:]) if taker_buy_volumes is not None else recent_vol * 0.5
        buy_ratio = (recent_buy_vol / recent_vol * 100) if recent_vol > 0 else 50.0
        battle_score = 85 if (buy_ratio >= 58 or buy_ratio <= 42) else 50

        readiness_score = int(0.4 * status_score + 0.3 * battle_score + 0.3 * location_score)
        
        if readiness_score >= 80:
            readiness_label = "IMMINENT"
        elif readiness_score >= 65:
            readiness_label = "BUILDING"
        else:
            readiness_label = "DEVELOPING"

        # Complete Schema required by UI
        return {
            "symbol": symbol,
            "breakout_readiness": f"{readiness_score}% ({readiness_label})",
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
        logging.error(f"Error processing {symbol}: {e}")
        return None


def run_scanner_pipeline(symbols=None, timeframe="1h"):
    if symbols is None:
        symbols = WATCHLIST

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_symbol_data, sym, timeframe) for sym in symbols]
        raw_results = [f.result() for f in futures]

    # Filter out None entries (skipped/failed symbols)
    valid_results = [r for r in raw_results if r is not None]

    # Sort descending by breakout readiness score
    valid_results.sort(key=lambda x: x["readiness_score"], reverse=True)
    return valid_results
