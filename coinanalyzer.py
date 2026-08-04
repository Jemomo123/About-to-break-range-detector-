import time
import requests

OKX_BASE_URL = "https://www.okx.com/api/v5/market/candles"
MEXC_BASE_URL = "https://contract.mexc.com/api/v1/contract/kline"

OKX_TF_MAP = {"3M": "3m", "5M": "5m", "15M": "15m", "1H": "1H", "4H": "4H", "3m": "3m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H"}
MEXC_TF_MAP = {"3M": "Min3", "5M": "Min5", "15M": "Min15", "1H": "Min60", "4H": "Hour4", "3m": "Min3", "5m": "Min5", "15m": "Min15", "1h": "Min60", "4h": "Hour4"}

def fetch_okx_klines(symbol: str, timeframe: str, limit: int = 150) -> list:
    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    inst_id = f"{clean_sym[:-4]}-USDT-SWAP" if clean_sym.endswith("USDT") else f"{clean_sym}-USDT-SWAP"
    bar = OKX_TF_MAP.get(timeframe, "5m")
    params = {"instId": inst_id, "bar": bar, "limit": str(limit)}

    try:
        res = requests.get(OKX_BASE_URL, params=params, timeout=6)
        res.raise_for_status()
        data = res.json()

        if data.get("code") != "0" or "data" not in data or not data["data"]:
            spot_inst_id = f"{clean_sym[:-4]}-USDT" if clean_sym.endswith("USDT") else clean_sym
            params["instId"] = spot_inst_id
            res = requests.get(OKX_BASE_URL, params=params, timeout=6)
            data = res.json()

        if data.get("code") != "0" or "data" not in data or not data["data"]:
            return []

        candles = []
        for item in reversed(data["data"]):
            candles.append({
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5])
            })
        return candles
    except Exception:
        return []

def fetch_mexc_klines(symbol: str, timeframe: str, limit: int = 150) -> list:
    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    formatted_symbol = f"{clean_sym[:-4]}_USDT" if clean_sym.endswith("USDT") else clean_sym
    interval = MEXC_TF_MAP.get(timeframe, "Min5")
    end_time = int(time.time())
    
    minutes = 5
    if "3" in interval: minutes = 3
    elif "15" in interval: minutes = 15
    elif "60" in interval: minutes = 60
    elif "Hour4" in interval: minutes = 240
    
    start_time = end_time - (minutes * 60 * limit)
    url = f"{MEXC_BASE_URL}/{formatted_symbol}"
    params = {"interval": interval, "start": start_time, "end": end_time}

    try:
        res = requests.get(url, params=params, timeout=6)
        res.raise_for_status()
        data = res.json()
        if not data.get("success", False) or "data" not in data:
            return []

        kline_data = data["data"]
        opens, highs, lows, closes, volumes = (
            kline_data.get("open", []), kline_data.get("high", []),
            kline_data.get("low", []), kline_data.get("close", []), kline_data.get("vol", [])
        )
        length = min(len(opens), len(highs), len(lows), len(closes), len(volumes))
        
        candles = []
        for i in range(length):
            candles.append({
                "open": float(opens[i]), "high": float(highs[i]),
                "low": float(lows[i]), "close": float(closes[i]), "volume": float(volumes[i])
            })
        return candles
    except Exception:
        return []

def fetch_klines(symbol: str, timeframe: str, limit: int = 150) -> list:
    # 1. Primary: OKX
    candles = fetch_okx_klines(symbol, timeframe, limit)
    if candles and len(candles) >= 20:
        print(f"[{symbol}][{timeframe}] Downloaded {len(candles)} candles (Source: OKX)", flush=True)
        return candles

    # 2. Fallback: MEXC
    print(f"[{symbol}][{timeframe}] OKX fetch failed or empty. Trying MEXC fallback...", flush=True)
    candles = fetch_mexc_klines(symbol, timeframe, limit)
    if candles and len(candles) >= 20:
        print(f"[{symbol}][{timeframe}] Downloaded {len(candles)} candles (Source: MEXC)", flush=True)
        return candles

    print(f"[{symbol}][{timeframe}] Download failed: Both OKX and MEXC returned no data", flush=True)
    return []
