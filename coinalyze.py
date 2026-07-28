import logging
import os
from cachetools import TTLCache
from dotenv import load_dotenv
import requests

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

COINALYZE_API_KEY = os.getenv("COINALYZE_API_KEY", "").strip()
BASE_URL = "https://api.coinalyze.net/v1"

# 45-second cache to honor rate limits and prevent spam
cache = TTLCache(maxsize=200, ttl=45)

# Requirement 1 & 2: Startup key check with SINGLE log entry
IS_CONFIGURED = bool(COINALYZE_API_KEY)

if IS_CONFIGURED:
    logging.info("[Coinalyze] Integration initialized with valid API Key.")
else:
    logging.warning("[Coinalyze] Coinalyze API key not configured in environment variables.")


def _get_headers():
    return {"api_key": COINALYZE_API_KEY} if IS_CONFIGURED else {}


def _format_symbol(symbol: str) -> str:
    """Converts OKX format (e.g. BTC-USDT-SWAP) to Coinalyze perpetual ticker format (BTCUSDT.A)."""
    clean = symbol.replace("-USDT-SWAP", "USDT")
    return f"{clean}.A"


def get_open_interest(symbol: str) -> float | None:
    if not IS_CONFIGURED:
        return None

    cache_key = f"oi_{symbol}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        coinalyze_symbol = _format_symbol(symbol)
        url = f"{BASE_URL}/open-interest?symbols={coinalyze_symbol}"
        res = requests.get(url, headers=_get_headers(), timeout=4)

        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list) and len(data) > 0:
                val = float(data[0].get("value", 0.0))
                cache[cache_key] = val
                return val
            else:
                logging.info(f"[Coinalyze] Symbol not supported for OI: {symbol}")
        elif res.status_code in [400, 404]:
            logging.info(f"[Coinalyze] Symbol not supported: {symbol}")
        else:
            logging.warning(f"[Coinalyze] OI fetch failed [{res.status_code}] for {symbol}")
    except Exception as e:
        logging.error(f"[Coinalyze] Network error fetching OI for {symbol}: {e}")

    cache[cache_key] = None
    return None


def get_funding_rate(symbol: str) -> float | None:
    if not IS_CONFIGURED:
        return None

    cache_key = f"funding_{symbol}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        coinalyze_symbol = _format_symbol(symbol)
        url = f"{BASE_URL}/predicted-funding-rate?symbols={coinalyze_symbol}"
        res = requests.get(url, headers=_get_headers(), timeout=4)

        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list) and len(data) > 0:
                val = float(data[0].get("value", 0.0))
                cache[cache_key] = val
                return val
            else:
                logging.info(f"[Coinalyze] Symbol not supported for Funding: {symbol}")
        elif res.status_code in [400, 404]:
            logging.info(f"[Coinalyze] Symbol not supported: {symbol}")
        else:
            logging.warning(f"[Coinalyze] Funding fetch failed [{res.status_code}] for {symbol}")
    except Exception as e:
        logging.error(f"[Coinalyze] Network error fetching Funding for {symbol}: {e}")

    cache[cache_key] = None
    return None


def get_cvd(symbol: str) -> float | None:
    if not IS_CONFIGURED:
        return None

    cache_key = f"cvd_{symbol}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        coinalyze_symbol = _format_symbol(symbol)
        url = f"{BASE_URL}/current-cvd?symbols={coinalyze_symbol}"
        res = requests.get(url, headers=_get_headers(), timeout=4)

        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list) and len(data) > 0:
                val = float(data[0].get("value", 0.0))
                cache[cache_key] = val
                return val
            else:
                logging.info(f"[Coinalyze] Symbol not supported for CVD: {symbol}")
        elif res.status_code in [400, 404]:
            logging.info(f"[Coinalyze] Symbol not supported: {symbol}")
        else:
            logging.warning(f"[Coinalyze] CVD fetch failed [{res.status_code}] for {symbol}")
    except Exception as e:
        logging.error(f"[Coinalyze] Network error fetching CVD for {symbol}: {e}")

    cache[cache_key] = None
    return None
