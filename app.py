import logging
import threading
import time
import pandas as pd
import requests
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from cachetools import TTLCache

# Module imports
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
    "global_temp": {
        "temperature": "COLD",
        "metrics": {"BUILDING": 0, "LOADING": 0, "ABOUT TO BREAK": 0, "CRITICAL": 0},
    },
    "last_updated": "Never",
}


# --- OKX Native Fallback Data Fetchers (Bypasses Shared-IP Rate Limits) ---

def fetch_okx_oi(symbol: str) -> float | None:
    cache_key = f"oi_{symbol}"
    if cache_key in okx_cache:
        return okx_cache[cache_key]
    try:
        url = f"{OKX_BASE_URL}/api/v5/public/open-interest?instId={symbol}"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == "0" and data.get("data"):
                val = float(data["data"][0].get("oi", 0.0))
                okx_cache[cache_key] = val
                return val
    except Exception as e:
        logging.debug(f"[OKX OI Error] {symbol}: {e}")
    return None


def fetch_okx_funding(symbol: str) -> float | None:
    cache_key = f"funding_{symbol}"
    if cache_key in okx_cache:
        return okx_cache[cache_key]
    try:
        url = f"{OKX_BASE_URL}/api/v5/public/funding-rate?instId={symbol}"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            data = res.json()
            if data.get("code") == "0" and data.get("data"):
                val = float(data["data"][0].get("fundingRate", 0.0))
                okx_cache[cache_key] = val
                return val
    except Exception as e:
        logging.debug(f"[OKX Funding Error] {symbol}: {e}")
    return None


def fetch_okx_cvd(symbol: str) -> float | None:
    cache_key = f"cvd_{symbol}"
    if cache_key in okx_cache:
        return okx_cache[cache_key]
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
    except Exception as e:
        logging.debug(f"[OKX CVD Error] {symbol}: {e}")
    return None


# --- Formatters ---

def format_oi(value: float | None) -> str:
    if value is None or value == 0:
        return "N/A"
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:.2f}M"
    if value >= 1e3:
        return f"${value / 1e3:.2f}K"
    return f"${value:.2f}"


def format_funding(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.4f}%"


def format_cvd(value: float | None) -> str:
    if value is None or value == 0:
        return "N/A"
    prefix = "+" if value > 0 else ""
    abs_val = abs(value)
    if abs_val >= 1e9:
        return f"{prefix}{value / 1e9:.2f}B"
    if abs_val >= 1e6:
        return f"{prefix}{value / 1e6:.2f}M"
    if abs_val >= 1e3:
        return f"{prefix}{value / 1e3:.2f}K"
    return f"{prefix}{value:.2f}"


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
    except Exception as e:
        logging.warning(f"[OKX API Error] {symbol} ({bar}): {e}")
    return None


def fetch_progressive_datasets(symbol: str) -> dict | None:
    datasets = {}

    # 1. 15M Range Gate Check
    df_15m = fetch_okx_candles(symbol, "15m", limit=50)
    if df_15m is None or not scanner.is_15m_range_valid(df_15m):
        logging.info(f"[Scanner Pipeline] {symbol} rejected: No valid 15M range")
        return None

    datasets["15m"] = df_15m
    time.sleep(0.1)

    # 2. 5M Pressure Check
    df_5m = fetch_okx_candles(symbol, "5m", limit=50)
    if df_5m is None:
        return None
    datasets["5m"] = df_5m
    time.sleep(0.1)

    # 3. 2M Trigger Acceleration
    df_2m = fetch_okx_candles(symbol, "2m", limit=50)
    datasets["2m"] = df_2m if df_2m is not None else df_5m

    # 4. Fetch metrics with automatic fallback to OKX API if Binance rate limits hit
    oi = coinalyze.get_open_interest(symbol) or fetch_okx_oi(symbol)
    funding = coinalyze.get_funding_rate(symbol) or fetch_okx_funding(symbol)
    cvd = coinalyze.get_cvd(symbol) or fetch_okx_cvd(symbol)

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


# --- Health check endpoint for Render ---
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# --- Primary Route: Handles HEAD and GET to satisfy Render Health Checks ---
@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def render_radar_dashboard():
    results = sorted(list(CACHE["results_dict"].values()), key=lambda x: x["sort_score"], reverse=True)

    if not results:
        return """
        <!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="refresh" content="5">
        <style>body{font-family:monospace;background:#111;color:#00ff00;padding:20px;text-align:center;}</style></head>
        <body><h3>🛰️ ABOUT TO BREAK RANGE RADAR</h3><p>Progressive 15M->5M->2M Scanning Active...</p></body></html>
        """

    critical = [r for r in results if r["status"] == "CRITICAL"]
    about_break = [r for r in results if r["status"] == "ABOUT TO BREAK"]
    loading = [r for r in results if r["status"] == "LOADING"]
    building = [r for r in results if r["status"] == "BUILDING"]

    top = results[0]
    bd = top["breakdown"]

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
Status:              {top['status']}
Bullish Probability: {top['bullish_prob']}%
Bearish Probability: {top['bearish_prob']}%
Final Score:         {top['sort_score']} / 100

Distance to Breakout:
Current Price:       {top['live_price']}
Upper Boundary:      {top['ceiling']} (Distance: {top['dist_ceil_pct']}%)
Lower Boundary:      {top['floor']} (Distance: {top['dist_floor_pct']}%)

15M Range Width:     {top['width']}%
15M Range Age:       {top['age']} candles

Market Dynamics:
Open Interest:       {oi_disp}
Funding Rate:        {funding_disp}
CVD Metric:          {cvd_disp}

Score Breakdown:
• Range Quality:     +{bd['Range Quality']} / 30
• Open Interest:     +{bd['Open Interest']} / 25
• CVD Confirmation:  +{bd['CVD']} / 20
• ATR Compression:   +{bd['ATR Compression']} / 15
• Funding Rate:      +{bd['Funding']} / 5
• Volume Spike:      +{bd['Volume']} / 5

=====================================================
RADAR WATCHLIST MONITOR
"""
    for item in results[:10]:
        icon = "🔥" if item['status'] == "CRITICAL" else "🟠" if item['status'] == "ABOUT TO BREAK" else "🟡" if item['status'] == "LOADING" else "🟢"
        dashboard_text += f"{icon} {item['symbol']:18s} | {item['status']:14s} | Bull: {item['bullish_prob']}% | Score: {item['sort_score']}\n"

    return f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="refresh" content="15">
    <style>body{{background-color:#111;color:#fff;font-family:monospace;font-size:14px;line-height:1.5;padding:15px;margin:0;white-space:pre-wrap;}}</style>
    </head><body>{dashboard_text}</body></html>"""
