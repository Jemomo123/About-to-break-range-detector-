# =====================================================================
# EXCHANGE & ORDER FLOW DATA FETCHER
# =====================================================================
import requests

def fetch_candles(symbol: str, timeframe: str = "15m", limit: int = 50) -> list:
    """Fetches raw OHLCV candles from exchange."""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
        res = requests.get(url, timeout=5)
        data = res.json()
        
        candles = []
        for c in data:
            candles.append({
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5])
            })
        return candles
    except Exception as e:
        print(f"Error fetching candles for {symbol}: {e}")
        return []

def fetch_order_flow(symbol: str) -> dict:
    """Fetches buyer and seller volume data."""
    try:
        candles = fetch_candles(symbol, timeframe="15m", limit=10)
        buyer_vol = sum(c["volume"] for c in candles if c["close"] >= c["open"])
        seller_vol = sum(c["volume"] for c in candles if c["close"] < c["open"])
        return {"buyer_volume": buyer_vol, "seller_volume": seller_vol}
    except Exception as e:
        print(f"Error fetching order flow for {symbol}: {e}")
        return {"buyer_volume": 50, "seller_volume": 50}
