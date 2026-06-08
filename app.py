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

def get_mexc_futures_symbols(execution_logs: list):
    try:
        response = requests.get(f"{BASE_URL}/detail", timeout=5).json()
        if response.get("success") and "data" in response:
            return [
                item["name"] for item in response["data"] 
                if item["name"].endswith("_USDT") and item.get("state", 0) == 0
            ]
    except Exception as e:
        print(f"ERROR in get_mexc_futures_symbols: {e}")
        execution_logs.append(f"EXCEPTION in symbol fetch: {str(e)}")
    return ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT"]

def parse_mexc_kline_payload(kd) -> dict:
    """Helper method to normalize variable formats returned by MEXC V1."""
    if isinstance(kd, dict):
        if "close" in kd:
            return {
                "high": kd.get("high", []), "low": kd.get("low", []),
                "close": kd.get("close", []), "vol": kd.get("vol", []),
                "time": kd.get("time", [])
            }
        return {
            "high": kd.get("high", []), "low": kd.get("low", []),
            "close": kd.get("close", []), "vol": kd.get("volume", kd.get("vol", [])),
            "time": kd.get("time", [])
        }
    elif isinstance(kd, list) and len(kd) > 0:
        if isinstance(kd[0], list):
            return {
                "time": [x[0] for x in kd], "close": [x[2] for x in kd],
                "high": [x[3] for x in kd], "low": [x[4] for x in kd],
                "vol": [x[5] for x in kd]
            }
        elif isinstance(kd[0], dict):
            return {
                "high": [x.get("high") for x in kd], "low": [x.get("low") for x in kd],
                "close": [x.get("close") for x in kd], "vol": [x.get("vol", x.get("volume", 0)) for x in kd],
                "time": [x.get("time", 0) for x in kd]
            }
    return {}

def fetch_mexc_live_data(symbol: str, execution_logs: list):
    """
    Fetches 15m, 5m, and 1m intervals independently.
    Synthesizes the 3m dataset dynamically from 1m candles using pandas.
    """
    data_feeds = {}
    quality_flags = {"15m_data": False, "5m_data": False, "3m_data": False}
    
    live_oi = 0.0
    live_funding = 0.0
    
    # Independent context acquisition for live ticker and funding metrics
    try:
        ticker_res = requests.get(f"{BASE_URL}/ticker/{symbol}", timeout=5).json()
        if ticker_res.get("success") and "data" in ticker_res:
            live_oi = float(ticker_res["data"].get("openInterest", 0.0))
    except Exception as e:
        print(f"ERROR fetching ticker stats for {symbol}: {e}")

    try:
        funding_res = requests.get(f"{BASE_URL}/funding_rate/{symbol}", timeout=5).json()
        if funding_res.get("success") and "data" in funding_res:
            live_funding = float(funding_res["data"].get("fundingRate", 0.0))
    except Exception as e:
        print(f"ERROR fetching funding stats for {symbol}: {e}")

    # --- TIME FRAME 1: Anchor 15M ---
    try:
        res_15m = requests.get(f"{BASE_URL}/kline/{symbol}?interval=Min15", timeout=5).json()
        if res_15m.get("success") and "data" in res_15m:
            p_15 = parse_mexc_kline_payload(res_15m["data"])
            if p_15 and len(p_15["close"]) >= 15:
                df15 = pd.DataFrame({
                    "high": pd.to_numeric(p_15["high"]), "low": pd.to_numeric(p_15["low"]),
                    "close": pd.to_numeric(p_15["close"]), "volume": pd.to_numeric(p_15["vol"])
                })
                df15["open_interest"] = live_oi
                df15["funding_rate"] = live_funding
                data_feeds["15m"] = df15
                quality_flags["15m_data"] = True
                execution_logs.append(f"[{symbol}] 15m OK ({len(df15)} bars)")
    except Exception as e:
        print(f"ERROR parsing native 15m timeline for {symbol}: {e}")

    # --- TIME FRAME 2: Trigger 5M ---
    try:
        res_5m = requests.get(f"{BASE_URL}/kline/{symbol}?interval=Min5", timeout=5).json()
        if res_5m.get("success") and "data" in res_5m:
            p_5 = parse_mexc_kline_payload(res_5m["data"])
            if p_5 and len(p_5["close"]) >= 15:
                df5 = pd.DataFrame({
                    "high": pd.to_numeric(p_5["high"]), "low": pd.to_numeric(p_5["low"]),
                    "close": pd.to_numeric(p_5["close"]), "volume": pd.to_numeric(p_5["vol"])
                })
                df5["open_interest"] = live_oi
                df5["funding_rate"] = live_funding
                data_feeds["5m"] = df5
                quality_flags["5m_data"] = True
                execution_logs.append(f"[{symbol}] 5m OK ({len(df5)} bars)")
    except Exception as e:
        print(f"ERROR parsing native 5m timeline for {symbol}: {e}")

    # --- TIME FRAME 3: Early Warning Synthetic 3M Construction ---
    try:
        res_1m = requests.get(f"{BASE_URL}/kline/{symbol}?interval=Min1", timeout=5).json()
        if res_1m.get("success") and "data" in res_1m:
            p_1 = parse_mexc_kline_payload(res_1m["data"])
            if p_1 and len(p_1["close"]) >= 30:
                # Build synthetic datetime index to drive resampling engine
                times = pd.to_datetime(p_1["time"], unit="s") if p_1["time"] else pd.date_range(end=pd.Timestamp.now(), periods=len(p_1["close"]), freq="1min")
                
                df1 = pd.DataFrame({
                    "open": pd.to_numeric(p_1.get("open", p_1["close"])), # fallback to close if open field isn't isolated
                    "high": pd.to_numeric(p_1["high"]), "low": pd.to_numeric(p_1["low"]),
                    "close": pd.to_numeric(p_1["close"]), "volume": pd.to_numeric(p_1["vol"])
                }, index=times)
                
                # Apply pandas resampling calculations to transform 1m bars into synthetic 3m bars
                resampled = df1.resample("3min").agg({
                    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
                }).dropna()
                
                if len(resampled) >= 15:
                    df3 = resampled[["high", "low", "close", "volume"]].copy()
                    df3["open_interest"] = live_oi
                    df3["funding_rate"] = live_funding
                    data_feeds["3m"] = df3.reset_index(drop=True)
                    quality_flags["3m_data"] = True
                    execution_logs.append(f"[{symbol}] 3m SYNTHETIC ({len(df3)} bars)")
    except Exception as e:
        print(f"ERROR processing synthetic 3m matrix for {symbol}: {e}")

    # Fallback confirmation checks
    if not quality_flags["3m_data"]:
        execution_logs.append(f"[{symbol}] 3m unavailable, using fallback")

    if quality_flags["15m_data"] and quality_flags["5m_data"]:
        data_feeds["quality_flags"] = quality_flags
        return data_feeds
        
    execution_logs.append(f"[{symbol}] FETCH FAILED: Core infrastructure (15m or 5m) down.")
    return None

@app.get("/", response_class=HTMLResponse)
def render_mobile_radar_dashboard():
    debug_log = []
    priority_watchlist = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT"]
    raw_scan_results = []
    
    for symbol in priority_watchlist:
        datasets = fetch_mexc_live_data(symbol, debug_log)
        if datasets:
            try:
                metrics = scanner.scan_symbol(symbol, datasets)
                raw_scan_results.append(metrics)
                debug_log.append(f"[{symbol}] SCAN SUCCESS")
            except Exception as e:
                print(f"ERROR running scanner loop on {symbol}: {e}")
                debug_log.append(f"[{symbol}] SCAN CRITICAL FAILURE: {str(e)}")
        time.sleep(0.1)

    if not raw_scan_results:
        log_items_html = "".join([f"<li>{line}</li>" for line in debug_log])
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>body{{font-family:monospace;padding:15px;background:#1a1a1a;color:#ff3333;}}ul{{list-style-type:none;padding:0;}}li{{border-left:3px solid #ff3333;padding-left:8px;margin-bottom:4px;color:#00ff00;}}</style></head>
        <body><h2>CRITICAL TIMELINE FAILURE</h2><ul>{log_items_html}</ul></body>
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
        q = top_candidate.get("quality_flags", {{"15m_data": True, "5m_data": True, "3m_data": False}})
        
        dashboard_text += f"""\n\nTOP CANDIDATE
{top_candidate['symbol']}
Status: {top_candidate['status']}
Data Quality Loops: [15M: {'OK' if q['15m_data'] else 'FAIL'} | 5M: {'OK' if q['5m_data'] else 'FAIL'} | 3M: {'SYNTHETIC' if q['3m_data'] else 'FALLBACK'}]"""

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

    return f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>body{{background-color:#f8f9fa;color:#212529;font-family:monospace;font-size:15px;line-height:1.6;padding:15px;margin:0;white-space:pre-wrap;}}</style>
    </head><body>{dashboard_text}</body></html>"""
