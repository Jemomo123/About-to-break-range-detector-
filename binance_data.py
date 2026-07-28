import logging
import requests
from cachetools import TTLCache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Cache results for 20 seconds to prevent hitting API limits
cache = TTLCache(maxsize=300, ttl=20)
OKX_BASE_URL = "https://www.okx.com"


def get_open_interest(symbol: str) -> float | None:
    """Fetches Open Interest directly from OKX API v5 (matches OKX ticker formats)."""
    cache_key = f"oi_{symbol}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        url = f"{OKX_BASE_URL}/api/v5/public/open-interest?instId={symbol}"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == "0" and data.get("data"):
                oi_val = float(data["data"][0].get("oi", 0.0))
                cache[cache_key] = oi_val
                return oi_val
        logging.warning(f"[OKX OI Response Error] {symbol}: {res.text}")
    except Exception as e:
        logging.warning(f"[OKX OI Exception] {symbol}: {e}")

    cache[cache_key] = None
    return None


def get_funding_rate(symbol: str) -> float | None:
    """Fetches real-time Funding Rate directly from OKX API v5."""
    cache_key = f"funding_{symbol}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        url = f"{OKX_BASE_URL}/api/v5/public/funding-rate?instId={symbol}"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == "0" and data.get("data"):
                funding = float(data["data"][0].get("fundingRate", 0.0))
                cache[cache_key] = funding
                return funding
        logging.warning(f"[OKX Funding Response Error] {symbol}: {res.text}")
    except Exception as e:
        logging.warning(f"[OKX Funding Exception] {symbol}: {e}")

    cache[cache_key] = None
    return None


def get_cvd(symbol: str) -> float | None:
    """Estimates taker buy/sell volume imbalance from OKX recent trades."""
    cache_key = f"cvd_{symbol}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        url = f"{OKX_BASE_URL}/api/v5/market/trades?instId={symbol}&limit=100"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == "0" and data.get("data"):
                trades = data["data"]
                buy_vol = sum(float(t.get("sz", 0)) for t in trades if t.get("side") == "buy")
                sell_vol = sum(float(t.get("sz", 0)) for t in trades if t.get("side") == "sell")
                cvd = buy_vol - sell_vol
                cache[cache_key] = cvd
                return cvd
        logging.warning(f"[OKX CVD Response Error] {symbol}: {res.text}")
    except Exception as e:
        logging.warning(f"[OKX CVD Exception] {symbol}: {e}")

    cache[cache_key] = None
    return None
