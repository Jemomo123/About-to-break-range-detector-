import time
import requests
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from scanner import MarketScanner

app = FastAPI()
scanner = MarketScanner()

BASE_URL = "https://contract.mexc.com/api/v1/contract"

def get_mexc_futures_symbols():
    try:
        response = requests.get(f"{BASE_URL}/detail", timeout=5).json()
        if response.get("success") and "data" in response:
            return [
                item["name"] for item in response["data"] 
                if item["name"].endswith("_USDT") and item.get("state", 0) == 0
            ]
    except Exception as e:
        print(f"Symbol fetch error: {e}")
    return ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT"]

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
            elif isinstance(kd[0], dict):
                return {
                    "high": [float(x.get("high", 0)) for x in kd],
                    "low": [float(x.get("low", 0)) for x in kd],
                    "close": [float(x.get("close", 0)) for x in kd],
                    "vol": [float(x.get("vol", x.get("volume", 0))) for x in kd]
                }
    except Exception as e:
        print(f"Error parsing klines: {e}")
    return {}

def fetch_mexc_live_data(symbol: str):
    data_feeds = {}
    live_oi, live_funding = 0.0, 0.0
    
    try:
        ticker_res = requests.get(f"{BASE_URL}/ticker/{symbol}", timeout=5).json()
        if ticker_res.get("success") and "data" in ticker_res:
            live_oi = float(ticker_res["data"].get("openInterest", 0.0))
    except Exception:
        pass

    try:
        funding_res = requests.get(f"{BASE_URL}/funding_rate/{symbol}", timeout=5).json()
        if funding_res.get("success") and "data" in funding_res:
            live_funding = float(funding_res["data"].get("fundingRate", 0.0))
    except Exception:
        pass

    # --- TIMEFRAME 1: 15M Anchor ---
    try:
        res_15m = requests.get(f"{BASE_URL}/kline/{symbol}?interval=Min15", timeout=5).json()
        if res_15m.get("success") and "data" in res_15m:
            p_15 = parse_mexc_kline_payload(res_15m["data"])
            if p_15 and len(p_15["close"]) >= 15:
                df15 = pd.DataFrame({
                    "high": pd.to_numeric(p_15["high"]),
                    "low": pd.to_numeric(p_15["low"]),
                    "close": pd.to_numeric(p_15["close"]),
                    "volume": pd.to_numeric(p_15["vol"])
                })
                df15["open_interest"] = live_oi
                df15["funding_rate"] = live_funding
                data_feeds["15m"] = df15
    except Exception as e:
        print(f"15m parse error for {symbol}: {e}")

    # --- TIMEFRAME 2: 5M Trigger ---
    try:
        res_5m = requests.get(f"{BASE_URL}/kline/{symbol}?interval=Min5", timeout=5).json()
        if res_5m.get("success") and "data" in res_5m:
            p_5 = parse_mexc_kline_payload(res_5m["data"])
            if p_5 and len(p_5["close"]) >= 15:
                df5 = pd.DataFrame({
                    "high": pd.to_numeric(p_5["high"]),
                    "low": pd.to_numeric(p_5["low"]),
                    "close": pd.to_numeric(p_5["close"]),
                    "volume": pd.to_numeric(p_5["vol"])
                })
                df5["open_interest"] = live_oi
                df5["funding_rate"] = live_funding
                data_feeds["5m"] = df5
    except Exception as e:
        print(f"5m parse error for {symbol}: {e}")

    # Verify both essential timelines exist before running the scanner
    if "15m" in data_feeds and "5m" in data_feeds:
        return data_feeds
    return None

@app.get("/", response_class=HTMLResponse)
def render_mobile_radar_dashboard():
    priority_watchlist = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT"]
    raw_scan_results = []
    
    for symbol in priority_watchlist:
        datasets = fetch_mexc_live_data(symbol)
        if datasets:
            try:
                metrics = scanner.scan_symbol(symbol, datasets)
                if metrics:
                    raw_scan_results.append(metrics)
            except Exception as e:
                print(f"Scanner error on {symbol}: {e}")
        time.sleep(0.05)

    if not raw_scan_results:
        return """
        <!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="refresh" content="5">
        <style>body{font-family:monospace;padding:20px;background:#1a1a1a;color:#ff3333;}</style></head>
        <body><h3>Connecting to MEXC Engine Feeds...</h3><p>Syncing tracking vectors.</p></body></html>
        """

    global_temp = scanner.calculate_market_temperature(raw_scan_results)
    sorted_pool = sorted(raw_scan_results, key=lambda x: x["sort_score"], reverse=True)
    counts = global_temp["metrics"]
    
    dashboard_text = f"""MARKET TEMPERATURE
{global_temp['temperature']}
No Range: {counts['NO RANGE']}
Stable Range: {counts['STABLE RANGE']}
Building: {counts['BUILDING']}
Loading: {counts['LOADING']}
About To Break: {counts['ABOUT TO BREAK']}
Critical: {counts['CRITICAL']}
====================================================="""

    if sorted_pool:
        top_candidate = sorted_pool[0]
        dashboard_text += f"""\n\nTOP CANDIDATE
{top_candidate['symbol']}
Status: {top_candidate['status']}"""

        dashboard_text += "\n\nTOP CANDIDATES\n"
        for idx, item in enumerate(sorted_pool[:5], 1):
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

15M Pressure:
{top_candidate['p_15m']}

5M Pressure:
{top_candidate['p_5m']}

Interpretation:
{interpretation}
====================================================="""

    return f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>body{{background-color:#f8f9fa;color:#212529;font-family:monospace;font-size:15px;line-height:1.6;padding:15px;margin:0;white-space:pre-wrap;}}</style>
    </head><body>{dashboard_text}</body></html>"""
                    
