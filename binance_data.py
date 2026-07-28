import logging
import requests
from cachetools import TTLCache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# 20-second cache prevents hitting Binance rate limits on scan cycles
cache = TTLCache(maxsize=300, ttl=20)
BINANCE_BASE_URL = "https://fapi.binance.com"


def _clean_symbol(symbol: str) -> str:
    """Converts OKX symbol format (e.g. BTC-USDT-SWAP or BTC-USDT) to Binance format (BTCUSDT)."""
    return symbol.replace("-USDT-SWAP", "USDT").replace("-", "").strip().upper()


def get_open_interest(symbol: str) -> float | None:
    """Fetches Open Interest in USD value directly from Binance Futures (Free, No Key)."""
    clean_sym = _clean_symbol(symbol)
    cache_key = f"oi_{clean_sym}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        url = f"{BINANCE_BASE_URL}/fapi/v1/openInterest?symbol={clean_sym}"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            data = res.json()
            # Open interest in contract units
            oi_contracts = float(data.get("openInterest", 0.0))
            cache[cache_key] = oi_contracts
            return oi_contracts
    except Exception as e:
        logging.warning(f"[Binance OI Fetch Error] {symbol}: {e}")

    cache[cache_key] = None
    return None


def get_funding_rate(symbol: str) -> float | None:
    """Fetches real-time estimated Funding Rate directly from Binance Futures (Free, No Key)."""
    clean_sym = _clean_symbol(symbol)
    cache_key = f"funding_{clean_sym}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        url = f"{BINANCE_BASE_URL}/fapi/v1/premiumIndex?symbol={clean_sym}"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            data = res.json()
            funding = float(data.get("lastFundingRate", 0.0))
            cache[cache_key] = funding
            return funding
    except Exception as e:
        logging.warning(f"[Binance Funding Fetch Error] {symbol}: {e}")

    cache[cache_key] = None
    return None


def get_cvd(symbol: str, period: str = "15m", limit: int = 15) -> float | None:
    """
    Calculates true Cumulative Volume Delta (CVD) over the requested window 
    using exact Taker Buy vs Taker Sell volume from Binance Futures.
    """
    clean_sym = _clean_symbol(symbol)
    cache_key = f"cvd_{clean_sym}_{period}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        url = f"{BINANCE_BASE_URL}/futures/data/takerlongshortRatio?pair={clean_sym}&period={period}&limit={limit}"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                # Sum exact taker buy and sell volumes across candles
                total_buy = sum(float(item.get("buyVol", 0)) for item in data)
                total_sell = sum(float(item.get("sellVol", 0)) for item in data)
                
                # Net CVD = Taker Buy Volume - Taker Sell Volume
                cvd = total_buy - total_sell
                cache[cache_key] = cvd
                return cvd
    except Exception as e:
        logging.warning(f"[Binance CVD Fetch Error] {symbol}: {e}")

    cache[cache_key] = None
    return None
