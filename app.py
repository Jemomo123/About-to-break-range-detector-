import time
import threading
import requests
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from scanner import MarketScanner

app = FastAPI()
scanner = MarketScanner()

BASE_URL = "https://contract.mexc.com/api/v1/contract"

# Global Server RAM Memory Cache
CACHE = {
    "results": [],
    "global_temp": {"temperature": "COLD", "metrics": {"NO RANGE": 0, "STABLE RANGE": 0, "BUILDING": 0, "LOADING": 0, "ABOUT TO BREAK": 0, "CRITICAL": 0}},
    "last_updated": "Never"
}

def parse_mexc_kline_payload(kd) -> dict:
    try:
        if isinstance(kd, list) and len(kd) > 0:
            if isinstance(kd[0], list):
                return {
                    "high": [float(x[3]) for x in kd],
                    "low": [float(x[4]) for x in kd],
                    "close": [float(x[2]) for x in kd],
                    "vol": [float(x[5]) for x in kd]
                }
    except Exception as e:
        print(f"Error parsing klines: {e}")
    return {}

def fetch_single_symbol_safely(symbol: str):
    """Fetches 1h, 15m, and 5m data for a single token with pacing gaps to dodge firewalls."""
    data_feeds = {}
    live_oi, live_funding = 0.0, 0.0
    
    try:
        ticker_res = requests.get(f"{BASE_URL}/ticker/{symbol}", timeout=4).json()
        if ticker_res.get("success") and "data" in ticker_res:
            live_oi = float(ticker_res["data"].get("openInterest", 0.0))
        time.sleep(0.2) # Firewall protection delay

        funding_res = requests.get(f"{BASE_URL}/funding_rate/{symbol}", timeout=4).json()
        if funding_res.get("success") and "data" in funding_res:
            live_funding = float(funding_res["data"].get("fundingRate", 0.0))
        time.sleep(0.2)
        
        # --- Timeframe 1: 1H Macro ---
        res_1h = requests.get(f"{BASE_URL}/kline/{symbol}?interval=Min60", timeout=4).json()
        if res_1h.get("success") and "data" in res_1h:
            p_1h = parse_mexc_kline_payload(res_1h["data"])
            if p_1h and len(p_1h["close"]) >= 15:
                df1h = pd.DataFrame({"high": p_1h["high"], "low": p_1h["low"], "close": p_1h["close"], "volume": p_1h["vol"]})
                df1h["open_interest"] = live_oi
                df1h["funding_rate"] = live_funding
                data_feeds["1h"] = df1h
        time.sleep(0.2)

        # --- Timeframe 2: 15M Anchor ---
        res_15m = requests.get(f"{BASE_URL}/kline/{symbol}?interval=Min15", timeout=4).json()
        if res_15m.get("success") and "data" in res_15m:
            p_15 = parse_mexc_kline_payload(res_15m["data"])
            if p_15 and len(p_15["close"]) >= 15:
                df15 = pd.DataFrame({"high": p_15["high"], "low": p_15["low"], "close": p_15["close"], "volume": p_15["vol"]})
                df15["open_interest"] = live_oi
                df15["funding_rate"] = live_funding
                data_feeds["15m"] = df15
        time.sleep(0.2)

        # --- Timeframe 3: 5M Trigger ---
        res_5m = requests.get(f"{BASE_URL}/kline/{symbol}?interval=Min5", timeout=4).json()
        if res_5m.get("success") and "data" in res_5m:
            p_5 = parse_mexc_kline_payload(res_5m["data"])
            if p_5 and len(p_5["close"]) >= 15:
                df5 = pd.DataFrame({"high": p_5["high"], "low": p_5["low"], "close": p_5["close"], "volume": p_5["vol"]})
                df5["open_interest"] = live_oi
                df5["funding_rate"] = live_funding
                data_feeds["5m"] = df5

        if "1h" in data_feeds and "15m" in data_feeds and "5m" in data_feeds:
            return data_feeds
    except Exception as e:
        print(f"Network error on {symbol}: {e}")
    return None

def background_scan_worker():
    """Runs continuously inside the server RAM memory space, completely decoupled from page views."""
    watchlist = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT"]
    while True:
        fresh_results = []
        for symbol in watchlist:
            datasets = fetch_single_symbol_safely(symbol)
            if datasets:
                try:
                    metrics = scanner.scan_symbol(symbol, datasets)
                    if metrics:
                        fresh_results.append(metrics)
                except Exception as e:
                    print(f"Scanning error on memory processing step: {e}")
            time.sleep(0.4) # Strict pacing interval to maintain pristine IP reputation
            
        if fresh_results:
            CACHE["results"] = sorted(fresh_results, key=lambda x: x["sort_score"], reverse=True)
            CACHE["global_temp"] = scanner.calculate_market_temperature(fresh_results)
            CACHE["last_updated"] = time.strftime("%H:%M:%S UTC")
            
        time.sleep(15) # Wait 15 seconds before starting the next background cycle

# Spin up the background thread immediately upon app startup
threading.Thread(target=background_scan_worker, daemon=True).start()

@app.get("/", response_class=HTMLResponse)
def render_mobile_radar_dashboard():
    raw_scan_results = CACHE["results"]
    global_temp = CACHE["global_temp"]
    counts = global_temp["metrics"]
    
    # Fallback to a clean loading loop screen only if the server hasn't finished its very first pass yet
    if not raw_scan_results:
        return """
        <!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="refresh" content="5">
        <style>body{font-family:monospace;padding:20px;background:#1a1a1a;color:#00ff00;text-align:center;}</style></head>
        <body><h3>Initializing Background Engine Matrix...</h3><p>Building rate-limit proof cache layer. Auto-refreshing in 5s...</p></body></html>
        """

    dashboard_text = f"""MARKET TEMPERATURE
{global_temp['temperature']}
No Range: {counts['NO RANGE']}
Stable Range: {counts['STABLE RANGE']}
Building: {counts['BUILDING']}
Loading: {counts['LOADING']}
About To Break: {counts['ABOUT TO BREAK']}
Critical: {counts['CRITICAL']}
Sync Time: {CACHE['last_updated']}
====================================================="""

    top_candidate = raw_scan_results[0]
    dashboard_text += f"""\n\nTOP CANDIDATE
{top_candidate['symbol']}
Status: {top_candidate['status']}"""

    dashboard_text += "\n\nTOP CANDIDATES\n"
    for idx, item in enumerate(raw_scan_results[:5], 1):
        dashboard_text += f"{idx}. {item['symbol']} -> {item['status']}\n"
    dashboard_text += "====================================================="

    if top_candidate['status'] in ['CRITICAL', 'ABOUT TO BREAK']:
        interpretation = "Long-lived compression with rising open interest and contracting volatility. Range appears increasingly unstable."
    elif top_candidate['status'] == 'LOADING':
        interpretation = "Accumulation structures intensifying across inner loops. Multi-timeframe velocity starting to stress range bounds."
    else:
        interpretation = "Structural framework remaining inside standard variance parameters. Low expansion probability near-term."

    dashboard_text += f"""\n\n{top_candidate['symbol']}

Status:
{top_candidate['status']}

Confidence:
{top_candidate['confidence']}

Range Width:
{top_candidate['width']}%

Range Age:
{top_candidate['age']} candles

ATR Contraction:
{int(top_candidate['atr_contract'])}%

OI Growth:
{top_candidate['oi_growth']}%

1H Pressure:
{top_candidate['p_1h']}

15M Pressure:
{top_candidate['p_15m']}

5M Pressure:
{top_candidate['p_5m']}

Interpretation:
{interpretation}
====================================================="""

    return f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="refresh" content="15">
    <style>body{{background-color:#f8f9fa;color:#212529;font-family:monospace;font-size:15px;line-height:1.6;padding:15px;margin:0;white-space:pre-wrap;}}</style>
    </head><body>{dashboard_text}</body></html>"""
    
