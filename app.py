import time
import requests
import pandas as pd
import numpy as np
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
    except Exception:
        pass
    return ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT"]

def fetch_mexc_live_data(symbol: str):
    data_feeds = {}
    tf_map = {"15m": "Min15", "5m": "Min5", "3m": "Min3"}
    try:
        ticker_res = requests.get(f"{BASE_URL}/ticker/{symbol}", timeout=5).json()
        funding_res = requests.get(f"{BASE_URL}/funding_rate/{symbol}", timeout=5).json()
        live_oi, live_funding = 0.0, 0.0
        
        if ticker_res.get("success") and "data" in ticker_res:
            live_oi = float(ticker_res["data"].get("openInterest", 0.0))
        if funding_res.get("success") and "data" in funding_res:
            live_funding = float(funding_res["data"].get("fundingRate", 0.0))
            
        for tf_label, mexc_tf in tf_map.items():
            kline_res = requests.get(f"{BASE_URL}/kline/{symbol}?interval={mexc_tf}", timeout=5).json()
            if not kline_res.get("success") or "data" not in kline_res:
                return None
            kd = kline_res["data"]
            
            if isinstance(kd, dict) and "close" in kd:
                high_arr, low_arr, close_arr = kd.get("high", []), kd.get("low", []), kd.get("close", [])
                vol_arr = kd.get("vol", [])
            elif isinstance(kd, list) and len(kd) > 0 and isinstance(kd[0], list):
                high_arr = [x[3] for x in kd]
                low_arr = [x[4] for x in kd]
                close_arr = [x[2] for x in kd]
                vol_arr = [x[5] for x in kd]
            elif isinstance(kd, list) and len(kd) > 0 and isinstance(kd[0], dict):
                high_arr = [x.get("high") for x in kd]
                low_arr = [x.get("low") for x in kd]
                close_arr = [x.get("close") for x in kd]
                vol_arr = [x.get("vol", x.get("volume", 0)) for x in kd]
            else:
                return None
                
            if not close_arr or len(close_arr) < 15:
                return None
                
            df = pd.DataFrame({
                "high": pd.to_numeric(high_arr),
                "low": pd.to_numeric(low_arr),
                "close": pd.to_numeric(close_arr),
                "volume": pd.to_numeric(vol_arr)
            })
            df["open_interest"] = live_oi
            df["funding_rate"] = live_funding
            data_feeds[tf_label] = df
        return data_feeds
    except Exception:
        return None

@app.get("/", response_class=HTMLResponse)
def render_mobile_radar_dashboard():
    priority_watchlist = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT"]
    raw_scan_results = []
    
    for symbol in priority_watchlist:
        datasets = fetch_mexc_live_data(symbol)
        if datasets:
            metrics = scanner.scan_symbol(symbol, datasets)
            raw_scan_results.append(metrics)
        time.sleep(0.1)

    if not raw_scan_results:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta http-equiv="refresh" content="5">
            <style>body { font-family: monospace; padding: 20px; background: #f8f9fa; color:#333; }</style>
        </head>
        <body>
            <h3>Connecting to MEXC Engine Feeds...</h3>
            <p>Syncing tracking vectors. The radar page will refresh itself automatically in 5s.</p>
        </body>
        </html>
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

15M:
{top_candidate['p_15m']}

5M:
{top_candidate['p_5m']}

3M:
{top_candidate['p_3m']}

Interpretation:
{interpretation}
====================================================="""

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                background-color: #f8f9fa;
                color: #212529;
                font-family: monospace;
                font-size: 15px;
                line-height: 1.6;
                padding: 15px;
                margin: 0;
                white-space: pre-wrap;
            }}
        </style>
    </head>
    <body>{dashboard_text}</body>
    </html>
    """
    return html_content
        
