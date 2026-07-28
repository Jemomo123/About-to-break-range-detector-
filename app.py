import logging
import threading
import time
import pandas as pd
import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from cachetools import TTLCache

import binance_data as coinalyze
from scanner import MarketScanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI()
scanner = MarketScanner()

OKX_BASE_URL = "https://www.okx.com"
okx_cache = TTLCache(maxsize=300, ttl=20)

WATCHLIST = [
    "BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "DOGE-USDT-SWAP",
    "PEPE-USDT-SWAP", "BONK-USDT-SWAP", "SHIB-USDT-SWAP", "FLOKI-USDT-SWAP",
    "WIF-USDT-SWAP", "BRETT-USDT-SWAP", "PENGU-USDT-SWAP", "FARTCOIN-USDT-SWAP",
    "SPX-USDT-SWAP", "USELESS-USDT-SWAP", "POPCAT-USDT-SWAP", "MOG-USDT-SWAP",
    "GOAT-USDT-SWAP", "TURBO-USDT-SWAP", "NEIRO-USDT-SWAP", "MEME-USDT-SWAP"
]

CACHE = {
    "results_dict": {},
    "global_temp": {"temperature": "COLD"},
    "last_updated": "Never",
}

def clean_val(val):
    """Safely unwraps pandas Series or scalar value into a float or None."""
    if val is None:
        return None
    if isinstance(val, pd.Series):
        if val.empty:
            return None
        val = val.iloc[0]
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def fetch_okx_oi(symbol: str) -> float | None:
    cache_key = f"oi_{symbol}"
    if cache_key in okx_cache: return okx_cache[cache_key]
    try:
        url = f"{OKX_BASE_URL}/api/v5/public/open-interest?instId={symbol}"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == "0" and data.get("data"):
                val = float(data["data"][0].get("oi", 0.0))
                okx_cache[cache_key] = val
                return val
    except: pass
    return None

def fetch_okx_funding(symbol: str) -> float | None:
    cache_key = f"funding_{symbol}"
    if cache_key in okx_cache: return okx_cache[cache_key]
    try:
        url = f"{OKX_BASE_URL}/api/v5/public/funding-rate?instId={symbol}"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == "0" and data.get("data"):
                val = float(data["data"][0].get("fundingRate", 0.0))
                okx_cache[cache_key] = val
                return val
    except: pass
    return None

def fetch_okx_cvd(symbol: str) -> float | None:
    cache_key = f"cvd_{symbol}"
    if cache_key in okx_cache: return okx_cache[cache_key]
    try:
        url = f"{OKX_BASE_URL}/api/v5/market/trades?instId={symbol}&limit=100"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == "0" and data.get("data"):
                trades = data["data"]
                buy_vol = sum(float(t.get("sz", 0)) for t in trades if t.get("side") == "buy")
                sell_vol = sum(float(t.get("sz", 0)) for t in trades if t.get("side") == "sell")
                cvd = buy_vol - sell_vol
                okx_cache[cache_key] = cvd
                return cvd
    except: pass
    return None

def format_oi(value) -> str:
    num = clean_val(value)
    if num is None or num == 0: return "N/A"
    if num >= 1e9: return f"${num / 1e9:.2f}B"
    if num >= 1e6: return f"${num / 1e6:.2f}M"
    if num >= 1e3: return f"${num / 1e3:.2f}K"
    return f"${num:.2f}"

def format_funding(value) -> str:
    num = clean_val(value)
    if num is None: return "N/A"
    return f"{num * 100:.4f}%"

def format_cvd(value) -> str:
    num = clean_val(value)
    if num is None or num == 0: return "N/A"
    prefix = "+" if num > 0 else ""
    abs_val = abs(num)
    if abs_val >= 1e9: return f"{prefix}{num / 1e9:.2f}B"
    if abs_val >= 1e6: return f"{prefix}{num / 1e6:.2f}M"
    if abs_val >= 1e3: return f"{prefix}{num / 1e3:.2f}K"
    return f"{prefix}{num:.2f}"

def fetch_okx_candles(symbol: str, bar: str, limit: int = 50) -> pd.DataFrame | None:
    try:
        url = f"{OKX_BASE_URL}/api/v5/market/candles?instId={symbol}&bar={bar}&limit={limit}"
        res = requests.get(url, timeout=4).json()
        if res.get("code") == "0" and "data" in res:
            raw = res["data"]
            if len(raw) >= 15:
                raw.reverse()
                return pd.DataFrame({
                    "high": [float(c[2]) for c in raw],
                    "low": [float(c[3]) for c in raw],
                    "close": [float(c[4]) for c in raw],
                    "volume": [float(c[5]) for c in raw],
                })
    except: pass
    return None

def fetch_progressive_datasets(symbol: str) -> dict | None:
    datasets = {}
    df_15m = fetch_okx_candles(symbol, "15m", limit=50)
    if df_15m is None or not scanner.is_15m_range_valid(df_15m):
        return None

    datasets["15m"] = df_15m
    time.sleep(0.1)
    
    oi = clean_val(coinalyze.get_open_interest(symbol)) or fetch_okx_oi(symbol)
    funding = clean_val(coinalyze.get_funding_rate(symbol)) or fetch_okx_funding(symbol)
    cvd = clean_val(coinalyze.get_cvd(symbol)) or fetch_okx_cvd(symbol)

    for key in datasets:
        datasets[key]["open_interest"] = oi
        datasets[key]["funding_rate"] = funding
        datasets[key]["cvd"] = cvd

    return datasets

def background_worker():
    while True:
        for symbol in WATCHLIST:
            try:
                datasets = fetch_progressive_datasets(symbol)
                if datasets:
                    metrics = scanner.scan_symbol(symbol, datasets)
                    if metrics:
                        CACHE["results_dict"][symbol] = metrics
                    else:
                        CACHE["results_dict"].pop(symbol, None)
                else:
                    CACHE["results_dict"].pop(symbol, None)
            except Exception as e:
                logging.error(f"Error scanning {symbol}: {e}")
            time.sleep(0.25)

        all_results = list(CACHE["results_dict"].values())
        if all_results:
            CACHE["global_temp"] = scanner.calculate_market_temperature(all_results)
            CACHE["last_updated"] = time.strftime("%H:%M:%S UTC")
        time.sleep(4)

threading.Thread(target=background_worker, daemon=True).start()

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def render_radar_dashboard():
    results = sorted(list(CACHE["results_dict"].values()), key=lambda x: x["sort_score"], reverse=True)

    if not results:
        return """
        <!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="refresh" content="5">
        <style>body{font-family:monospace;background:#111;color:#00ff00;padding:20px;text-align:center;}</style></head>
        <body><h3>🛰️ ABOUT TO BREAK RANGE RADAR</h3><p>Scanning For Auction Compression...</p></body></html>
        """

    critical = [r for r in results if r["status"] == "CRITICAL"]
    about_break = [r for r in results if r["status"] == "ABOUT TO BREAK"]
    loading = [r for r in results if r["status"] == "LOADING"]
    building = [r for r in results if r["status"] == "BUILDING"]

    top = results[0]
    oi_disp = format_oi(top['open_interest'])
    funding_disp = format_funding(top['funding_rate'])
    cvd_disp = format_cvd(top['cvd'])

    dashboard_text = f"""=====================================================
🛰️ ABOUT TO BREAK RANGE RADAR
=====================================================
Market Temp:  {CACHE['global_temp']['temperature']}
Sync Time:    {CACHE['last_updated']}

CATEGORIES
🔥 Critical:       {len(critical)}
🟠 About To Break: {len(about_break)}
🟡 Loading:        {len(loading)}
🟢 Building:       {len(building)}
=====================================================

SELECTED TARGET: {top['symbol']}
Status:         {top['status']}
Market Control:
{top['control_state']}

Distance to Breakout:
Current Price:  {top['live_price']}
Upper Boundary: {top['ceiling']} (Distance: {top['dist_ceil_pct']}%)
Lower Boundary: {top['floor']} (Distance: {top['dist_floor_pct']}%)

15M Range Width: {top['width']}%
15M Range Age:   {top['age']} candles

Market Dynamics:
Open Interest:  {oi_disp}
Funding Rate:   {funding_disp}
CVD Metric:     {cvd_disp}

=====================================================
RADAR WATCHLIST MONITOR
"""
    for item in results[:10]:
        icon = "🔥" if item['status'] == "CRITICAL" else "🟠" if item['status'] == "ABOUT TO BREAK" else "🟡" if item['status'] == "LOADING" else "🟢"
        clean_status = item['status'].replace("ABOUT TO BREAK", "ABOUT BREAK")
        dashboard_text += f"{icon} {item['symbol']:15s} | {clean_status}\n   └ {item['control_state']}\n"

    return f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="refresh" content="15">
    <style>body{{background-color:#111;color:#fff;font-family:monospace;font-size:13px;line-height:1.4;padding:12px;margin:0;white-space:pre-wrap;}}</style>
    </head><body>{dashboard_text}</body></html>"""
