import os
import requests
import logging
from dotenv import load_dotenv
from cachetools import TTLCache

load_dotenv()

COINALYZE_API_KEY = os.getenv("COINALYZE_API_KEY", "")
BASE_URL = "https://api.coinalyze.net/v1"

# 30-second TTL cache to prevent API rate limit bans
cache = TTLCache(maxsize=100, ttl=30)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _get_headers():
    return {"api_key": COINALYZE_API_KEY} if COINALYZE_API_KEY else {}


def _format_symbol(symbol: str) -> str:
    """
    Converts OKX symbol (e.g., BTC-USDT-SWAP) to Coinalyze perpetual symbol format (BTCUSDT.A).
    """
    clean = symbol.replace("-USDT-SWAP", "USDT")
    return f"{clean}.A"


def get_open_interest(symbol: str) -> float | None:
    cache_key = f"oi_{symbol}"
    if cache_key in cache:
        return cache[cache_key]

    if not COINALYZE_API_KEY:
        logging.warning(f"[Coinalyze] API Key missing in environment for symbol {symbol}")
        return None

    try:
        coinalyze_symbol = _format_symbol(symbol)
        url = f"{BASE_URL}/open-interest?symbols={coinalyze_symbol}"
        res = requests.get(url, headers=_get_headers(), timeout=4)
        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list) and len(data) > 0:
                val = float(data[0].get("value", 0.0))
                cache[cache_key] = val
                logging.info(f"[Coinalyze] Successfully fetched OI for {symbol}: {val}")
                return val
            else:
                logging.warning(f"[Coinalyze] Empty data array for OI: {symbol}")
        else:
            logging.warning(f"[Coinalyze] OI request failed [{res.status_code}]: {res.text}")
    except Exception as e:
        logging.error(f"[Coinalyze] Exception fetching OI for {symbol}: {e}")

    return None


def get_funding_rate(symbol: str) -> float | None:
    cache_key = f"funding_{symbol}"
    if cache_key in cache:
        return cache[cache_key]

    if not COINALYZE_API_KEY:
        return None

    try:
        coinalyze_symbol = _format_symbol(symbol)
        url = f"{BASE_URL}/predicted-funding-rate?symbols={coinalyze_symbol}"
        res = requests.get(url, headers=_get_headers(), timeout=4)
        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list) and len(data) > 0:
                val = float(data[0].get("value", 0.0))
                cache[cache_key] = val
                logging.info(f"[Coinalyze] Successfully fetched Funding for {symbol}: {val}")
                return val
            else:
                logging.warning(f"[Coinalyze] Empty data array for Funding: {symbol}")
        else:
            logging.warning(f"[Coinalyze] Funding request failed [{res.status_code}]: {res.text}")
    except Exception as e:
        logging.error(f"[Coinalyze] Exception fetching Funding for {symbol}: {e}")

    return None


def get_cvd(symbol: str) -> float | None:
    cache_key = f"cvd_{symbol}"
    if cache_key in cache:
        return cache[cache_key]

    if not COINALYZE_API_KEY:
        return None

    try:
        coinalyze_symbol = _format_symbol(symbol)
        url = f"{BASE_URL}/current-cvd?symbols={coinalyze_symbol}"
        res = requests.get(url, headers=_get_headers(), timeout=4)
        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list) and len(data) > 0:
                val = float(data[0].get("value", 0.0))
                cache[cache_key] = val
                logging.info(f"[Coinalyze] Successfully fetched CVD for {symbol}: {val}")
                return val
            else:
                logging.warning(f"[Coinalyze] Empty data array for CVD: {symbol}")
        else:
            logging.warning(f"[Coinalyze] CVD request failed [{res.status_code}]: {res.text}")
    except Exception as e:
        logging.error(f"[Coinalyze] Exception fetching CVD for {symbol}: {e}")

    return None
