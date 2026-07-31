# binance_data.py
# =====================================================================
# VERSION 1.0 — RAW MARKET DATA PROVIDER
# =====================================================================

import logging
import requests
import numpy as np

logger = logging.getLogger(__name__)

def fetch_binance_futures_klines(symbol, interval="1h", limit=100):
    """
    Fetches raw futures OHLCV and taker volume data from Binance.
    Performs ZERO scoring, indicator, or range boundary calculations.
    
    Parameters:
        symbol (str): Target trading pair (e.g., "BTCUSDT")
        interval (str): Kline interval (e.g., "1h", "15m")
        limit (int): Number of candles to fetch (default: 100)
        
    Returns:
        dict: Raw price/volume numpy arrays or None if request fails.
    """
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            logger.warning(f"Binance API returned status code {response.status_code} for {symbol}")
            return None

        data = response.json()
        if not isinstance(data, list) or len(data) == 0:
            logger.warning(f"Binance API returned empty payload for {symbol}")
            return None

        # Parse raw OHLCV arrays
        highs = np.array([float(candle[2]) for candle in data], dtype=float)
        lows = np.array([float(candle[3]) for candle in data], dtype=float)
        closes = np.array([float(candle[4]) for candle in data], dtype=float)
        volumes = np.array([float(candle[5]) for candle in data], dtype=float)
        taker_buy_volumes = np.array([float(candle[9]) for candle in data], dtype=float)

        return {
            "highs": highs,
            "lows": lows,
            "closes": closes,
            "volumes": volumes,
            "taker_buy_volumes": taker_buy_volumes
        }

    except Exception as e:
        logger.error(f"Error fetching Binance data for {symbol}: {e}")
        return None
