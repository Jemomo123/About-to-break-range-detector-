import time
import threading
import requests
import logging
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from scanner import MarketScanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI()
scanner = MarketScanner()

# Unified endpoints targeting MEXC Contract and OKX Public V5 infrastructures
MEXC_BASE_URL = "https://contract.mexc.com/api/v1/contract"
OKX_BASE_URL = "https://www.okx.com/api/v5"

CACHE = {
    "results_dict": {},
    "global_temp": {"temperature": "COLD", "metrics": {"NO RANGE": 0, "STABLE RANGE": 0, "BUILDING": 0, "LOADING": 0, "ABOUT TO BREAK": 0, "CRITICAL": 0}},
    "last_updated": "Never",
    "worker_status": "Starting 1H-15M-5M Fusion Matrix Engine..."
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

def to_okx_symbol(mexc_symbol: str) -> str:
    return mexc_symbol.replace("_", "-") + "-SWAP"

def fetch_from_okx_fallback(mexc_symbol: str):
    """
    Automated Backup Route: Pulls Min60, Min15, and Min5 candlesticks from OKX 
    if MEXC triggers rate limit drops. Transforms data structure arrays natively.
    """
    okx_symbol = to_okx_symbol(mexc_symbol)
    data_feeds = {}
    
    # 2. Strict endpoint maps: Only pulling 1H, 15M, and 5M data matrices
    intervals = {"5m": "5m", "15m": "15m", "1h": "1H"}
    
    try:
        live_oi, live_funding = 0.0, 0.0
        # Light historical parameters lookup
        for key, okx_bar in intervals.items():
            url = f"{OKX_BASE_URL}/market/candles?instId={okx_symbol}&bar={okx_bar}&limit=100"
            res = requests.get(url, timeout=3).json()
            
            if res.get("code") == "0" and "data" in res:
                raw_candles = res["data"]
                if len(raw_candles) >= 15:
                    raw_candles.reverse() # Direct alignment matching chronological loops
                    data_feeds[key] = pd.DataFrame({
                        "high": [float(c[2]) for c in raw_candles],
                        "low": [float(c[3]) for c in raw_candles],
                        "close": [float(c[4]) for c in raw_candles],
                        "volume": [float(c[5]) for c in raw_candles]
                    })
            time.sleep(0.15)
            
        if "1h" in data_feeds and "15m" in data_feeds and "5m" in data_feeds:
            return data_feeds
    except Exception:
        pass
    return None

def fetch_single_symbol_safely(symbol: str):
    """
    Primary API Connection Route targeting clean MEXC Min60, Min15, and Min5 data layers.
    """
    data_feeds = {}
    try:
        # 1H Fetch Line (Min60)
        res_1h = requests.get(f"{MEXC_BASE_URL}/kline/{symbol}?interval=Min60", timeout=3).json()
        if res_1h.get("success") and "data" in res_1h:
            p_1h = parse_mexc_kline_payload(res_1h["data"])
            if p_1h and len(p_1h["close"]) >= 15:
                data_feeds["1h"] = pd.DataFrame({"high": p_1h["high"], "low": p_1h["low"], "close": p_1h["close"], "volume": p_1h["vol"]})
        time.sleep(0.15)

        # 15M Fetch Line (Min15)
        res_15m = requests.get(f"{MEXC_BASE_URL}/kline/{symbol}?interval=Min15", timeout=3).json()
        if res_15m.get("success") and "data" in res_15m:
            p_15 = parse_mexc_kline_payload(res_15m["data"])
            if p_15 and len(p_15["close"]) >= 15:
                data_feeds["15m"] = pd.DataFrame({"high": p_15["high"], "low": p_15["low"], "close": p_15["close"], "volume": p_15["vol"]})
        time.sleep(0.15)

        # 5M Fetch Line (Min5)
        res_5m = requests.get(f"{MEXC_BASE_URL}/kline/{symbol}?interval=Min5", timeout=3).json()
        if res_5m.get("success") and "data" in res_5m:
            p_5 = parse_mexc_kline_payload(res_5m["data"])
            if p_5 and len(p_5["close"]) >= 15:
                data_feeds["5m"] = pd.DataFrame({"high": p_5["high"], "low": p_5["low"], "close": p_5["close"], "volume": p_5["vol"]})

        if "1h" in data_feeds and "15m" in data_feeds and "5m" in data_feeds:
            return data_feeds
    except Exception:
        pass
    return None

def background_scan_worker():
    # 📋 Complete clean 25 watchlist profile matrix
    watchlist = [
        "BTC_USDT", "ETH_USDT", "SOL_USDT", "PEPE_USDT", "BONK_USDT",
        "SHIB_USDT", "USELESS_USDT", "SPACE_USDT", "MOVE_USDT", "ZEC_USDT",
        "SPX_USDT", "PEOPLE_USDT", "PENGU_USDT", "FARTCOIN_USDT", "LINEA_USDT",
        "MEME_USDT", "PUMP_USDT", "AIXBT_USDT", "BRETT_USDT", "FOGO_USDT",
        "GOOGL_USDT", "FLOKI_USDT", "IWM_USDT", "MOODENG_USDT", "NEAR_USDT"
    ]
    
    batch_size = 5
    batches = [watchlist[i:i + batch_size] for i in range(0, len(watchlist), batch_size)]
    
    while True:
        for batch_idx, batch in enumerate(batches, 1):
            for symbol in batch:
                CACHE["worker_status"] = f"Scanning batch {batch_idx}/{len(batches)}: {symbol}..."
                
                datasets = fetch_single_symbol_safely(symbol)
                
                # Active Fallback Triggers using the OKX mapping infrastructure
                if not datasets:
                    datasets = fetch_from_okx_fallback(symbol)
                    
                if datasets:
                    try:
                        metrics = scanner.scan_symbol(symbol, datasets)
                        if metrics:
                            CACHE["results_dict"][symbol] = metrics
                        else:
                            # If the structural filter returns None, remove from candidate list safely
                            CACHE["results_dict"].pop(symbol, None)
                    except Exception:
                        pass
                time.sleep(0.4)
                
            all_current_results = list(CACHE["results_dict"].values())
            if all_current_results:
                CACHE["global_temp"] = scanner.calculate_market_temperature(all_current_results)
                CACHE["last_updated"] = time.strftime("%H:%M:%S UTC")
                
            time.sleep(4)

threading.Thread(target=background_scan_worker, daemon=True).start()

@app.get("/", response_class=HTMLResponse)
def render_mobile_radar_dashboard():
    raw_scan_results = sorted(list(CACHE["results_dict"].values()), key=lambda x: x["sort_score"], reverse=True)
    
    if not raw_scan_results:
        return """
        <!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="refresh" content="5">
        <style>body{font-family:monospace;padding:20px;background:#111;color:#00ff00;text-align:center;}</style></head>
        <body><h3>Refactoring to 1H/15M/5M Core...</h3><p>Compiling new multi-timeframe matrices. Standby...</p></body></html>
        """

    global_temp = CACHE["global_temp"]
    counts = global_temp["metrics"]
    
    dashboard_text = f"""MARKET TEMPERATURE
{global_temp['temperature']}
No Range Rejected: [Active Structural Filter]
Building: {counts.get('BUILDING', 0)}
Loading: {counts.get('LOADING', 0)}
About To Break: {counts.get('ABOUT TO BREAK', 0)}
Critical: {counts.get('CRITICAL', 0)}
Sync Time: {CACHE['last_updated']} (1H Structural Architecture)
====================================================="""

    top_candidate = raw_scan_results[0]
    dashboard_text += f"""\n\nTOP CANDIDATE
{top_candidate['symbol']}
Status: {top_candidate['status']}"""

    dashboard_text += "\n\nTOP 10 RADAR CANDIDATES\n"
    for idx, item in enumerate(raw_scan_results[:10], 1):
        dashboard_text += f"{idx:02d}. {item['symbol']:12s} -> {item['status']}\n"
    dashboard_text += "====================================================="

    # 6. High-Visibility Multi-Timeframe Dashboard Metrics Presentation Layer
    dashboard_text += f"""\n\n{top_candidate['symbol']} Multi-Timeframe Pressure:

1H Pressure (Structure):  [{top_candidate.get('p_1h', 'N/A')}]
15M Pressure (Build-up): [{top_candidate.get('p_15m', 'N/A')}]
5M Pressure (Trigger):   [{top_candidate.get('p_5m', 'N/A')}]

Vitals:
Status:          {top_candidate.get('status', 'N/A')}
Confidence:      {top_candidate.get('confidence', 'MEDIUM')}
1H Box Width:    {top_candidate.get('width', 0.0)}%
1H Box Age:      {top_candidate.get('age', 0)} candles

Interpretation:
{top_candidate.get('interpretation', '')}
====================================================="""

    return f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="refresh" content="15">
    <style>body{{background-color:#111;color:#fff;font-family:monospace;font-size:15px;line-height:1.6;padding:15px;margin:0;white-space:pre-wrap;}}</style>
    </head><body>{dashboard_text}</body></html>"""
