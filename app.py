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

CACHE = {
    "results": [],
    "global_temp": {"temperature": "COLD", "metrics": {"NO RANGE": 0, "STABLE RANGE": 0, "BUILDING": 0, "LOADING": 0, "ABOUT TO BREAK": 0, "CRITICAL": 0}},
    "last_updated": "Never",
    "worker_status": "Starting..."
}

def parse_mexc_kline_payload(kd) -> dict:
    try:
        if isinstance(kd, dict) and all(k in kd for k in ["high", "low", "close", "vol"]):
            return {
                "high": [float(x) for x in kd["high"]],
                "low": [float(x) for x in kd["low"]],
                "close": [float(x) for x in kd["close"]],
                "vol": [float(x) for x in kd["vol"]]
            }
    except Exception:
        pass
    return {}

def fetch_single_symbol_safely(symbol: str):
    data_feeds = {}
    live_oi, live_funding = 0.0, 0.0
    
    try:
        ticker_res = requests.get(f"{BASE_URL}/ticker/{symbol}", timeout=4).json()
        if ticker_res.get("success") and "data" in ticker_res:
            live_oi = float(ticker_res["data"].get("openInterest", 0.0))
        time.sleep(0.2)

        funding_res = requests.get(f"{BASE_URL}/funding_rate/{symbol}", timeout=4).json()
        if funding_res.get("success") and "data" in funding_res:
            live_funding = float(funding_res["data"].get("fundingRate", 0.0))
        time.sleep(0.2)
        
        # 1H
        res_1h = requests.get(f"{BASE_URL}/kline/{symbol}?interval=Min60", timeout=4).json()
        if res_1h.get("success") and "data" in res_1h:
            p_1h = parse_mexc_kline_payload(res_1h["data"])
            if p_1h and len(p_1h["close"]) >= 15:
                df1h = pd.DataFrame({"high": p_1h["high"], "low": p_1h["low"], "close": p_1h["close"], "volume": p_1h["vol"]})
                df1h["open_interest"] = live_oi; df1h["funding_rate"] = live_funding
                data_feeds["1h"] = df1h
        time.sleep(0.2)

        # 15M
        res_15m = requests.get(f"{BASE_URL}/kline/{symbol}?interval=Min15", timeout=4).json()
        if res_15m.get("success") and "data" in res_15m:
            p_15 = parse_mexc_kline_payload(res_15m["data"])
            if p_15 and len(p_15["close"]) >= 15:
                df15 = pd.DataFrame({"high": p_15["high"], "low": p_15["low"], "close": p_15["close"], "volume": p_15["vol"]})
                df15["open_interest"] = live_oi; df15["funding_rate"] = live_funding
                data_feeds["15m"] = df15
        time.sleep(0.2)

        # 5M
        res_5m = requests.get(f"{BASE_URL}/kline/{symbol}?interval=Min5", timeout=4).json()
        if res_5m.get("success") and "data" in res_5m:
            p_5 = parse_mexc_kline_payload(res_5m["data"])
            if p_5 and len(p_5["close"]) >= 15:
                df5 = pd.DataFrame({"high": p_5["high"], "low": p_5["low"], "close": p_5["close"], "volume": p_5["vol"]})
                df5["open_interest"] = live_oi; df5["funding_rate"] = live_funding
                data_feeds["5m"] = df5

        if "1h" in data_feeds and "15m" in data_feeds and "5m" in data_feeds:
            return data_feeds
    except Exception:
        pass
    return None

def background_scan_worker():
    watchlist = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT"]
    while True:
        fresh_results = []
        for symbol in watchlist:
            CACHE["worker_status"] = f"Scanning {symbol}..."
            datasets = fetch_single_symbol_safely(symbol)
            if datasets:
                try:
                    metrics = scanner.scan_symbol(symbol, datasets)
                    if metrics:
                        fresh_results.append(metrics)
                except Exception:
                    pass
            time.sleep(0.4)
            
        if fresh_results:
            CACHE["results"] = sorted(fresh_results, key=lambda x: x["sort_score"], reverse=True)
            CACHE["global_temp"] = scanner.calculate_market_temperature(fresh_results)
            CACHE["last_updated"] = time.strftime("%H:%M:%S UTC")
            CACHE["worker_status"] = "Idle."
            
        time.sleep(15)

threading.Thread(target=background_scan_worker, daemon=True).start()

@app.get("/", response_class=HTMLResponse)
def render_mobile_radar_dashboard():
    raw_scan_results = CACHE["results"]
    
    if not raw_scan_results:
        return """
        <!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="refresh" content="5">
        <style>body{font-family:monospace;padding:20px;background:#111;color:#00ff00;text-align:center;}</style></head>
        <body><h3>Building Matrix Cache Pool...</h3></body></html>
        """

    global_temp = CACHE["global_temp"]
    counts = global_temp["metrics"]
    
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

    # Added explicit fallbacks to catch exact key names from detector parameters
    dashboard_text += f"""\n\n{top_candidate['symbol']}

Status:
{top_candidate.get('status', 'N/A')}

Confidence:
{top_candidate.get('confidence', 'MEDIUM')}

Range Width:
{top_candidate.get('width', 0.0)}%

Range Age:
{top_candidate.get('age', 0)} candles

ATR Contraction:
{int(top_candidate.get('atr_contract', 0))}%

OI Growth:
{top_candidate.get('oi_growth', 0.0)}%

1H Pressure:
{top_candidate.get('p_1h', 'N/A')}

15M Pressure:
{top_candidate.get('p_15m', 'N/A')}

5M Pressure:
{top_candidate.get('p_5m', 'N/A')}

Interpretation:
{interpretation}
====================================================="""

    return f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="refresh" content="15">
    <style>body{{background-color:#111;color:#fff;font-family:monospace;font-size:15px;line-height:1.6;padding:15px;margin:0;white-space:pre-wrap;}}</style>
    </head><body>{dashboard_text}</body></html>"""
        
