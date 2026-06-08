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
    """Fetches valid USDT contract listings trading on MEXC with explicit error tracking."""
    try:
        execution_logs.append("Fetching active contract list from detail endpoint...")
        response = requests.get(f"{BASE_URL}/detail", timeout=5).json()
        if response.get("success") and "data" in response:
            symbols = [
                item["name"] for item in response["data"] 
                if item["name"].endswith("_USDT") and item.get("state", 0) == 0
            ]
            execution_logs.append(f"Successfully retrieved {len(symbols)} active pairs.")
            return symbols
        execution_logs.append(f"Detail API failed or bad structure. Response: {str(response)[:200]}")
    except Exception as e:
        print(f"ERROR in get_mexc_futures_symbols: {e}")
        execution_logs.append(f"EXCEPTION in get_mexc_futures_symbols: {str(e)}")
    return ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT"]

def fetch_mexc_live_data(symbol: str, execution_logs: list):
    """
    Fetches real-time market data from MEXC with explicit visibility constraints.
    Tracks, verifies, and logs the structural morphology of every incoming payload.
    """
    data_feeds = {}
    tf_map = {"15m": "Min15", "5m": "Min5", "3m": "Min3"}
    
    execution_logs.append(f"[{symbol}] Starting fetch pipeline...")
    try:
        # 1. Fetch live Open Interest metric data
        ticker_url = f"{BASE_URL}/ticker/{symbol}"
        execution_logs.append(f"[{symbol}] Requesting ticker data from: {ticker_url}")
        ticker_res = requests.get(ticker_url, timeout=5).json()
        execution_logs.append(f"[{symbol}] Ticker raw success key: {ticker_res.get('success')}")
        
        # 2. Fetch live Funding metric data
        funding_url = f"{BASE_URL}/funding_rate/{symbol}"
        execution_logs.append(f"[{symbol}] Requesting funding rate from: {funding_url}")
        funding_res = requests.get(funding_url, timeout=5).json()
        execution_logs.append(f"[{symbol}] Funding raw success key: {funding_res.get('success')}")
        
        live_oi = 0.0
        live_funding = 0.0
        
        if ticker_res.get("success") and "data" in ticker_res:
            live_oi = float(ticker_res["data"].get("openInterest", 0.0))
            execution_logs.append(f"[{symbol}] Parsed Open Interest: {live_oi}")
        else:
            execution_logs.append(f"[{symbol}] WARNING: Ticker payload missing or success=False")
            
        if funding_res.get("success") and "data" in funding_res:
            live_funding = float(funding_res["data"].get("fundingRate", 0.0))
            execution_logs.append(f"[{symbol}] Parsed Funding Rate: {live_funding}")
        else:
            execution_logs.append(f"[{symbol}] WARNING: Funding payload missing or success=False")
            
        # 3. Fetch Multi-Timeframe Historical Data Arrays
        for tf_label, mexc_tf in tf_map.items():
            kline_url = f"{BASE_URL}/kline/{symbol}?interval={mexc_tf}"
            execution_logs.append(f"[{symbol}] Requesting {tf_label} klines from: {kline_url}")
            kline_res = requests.get(kline_url, timeout=5).json()
            
            if not kline_res.get("success") or "data" not in kline_res:
                execution_logs.append(f"[{symbol}] RETURN NONE: {tf_label} failed API confirmation layer. Payload: {str(kline_res)[:200]}")
                return None
                
            kd = kline_res["data"]
            execution_logs.append(f"[{symbol}] {tf_label} raw data type discovered: {type(kd)}")
            
            # Identify array layout pattern mutations
            if isinstance(kd, dict):
                execution_logs.append(f"[{symbol}] {tf_label} dict keys visible: {list(kd.keys())}")
                if "close" in kd:
                    high_arr = kd.get("high", [])
                    low_arr = kd.get("low", [])
                    close_arr = kd.get("close", [])
                    vol_arr = kd.get("vol", [])
                else:
                    high_arr = kd.get("high", [])
                    low_arr = kd.get("low", [])
                    close_arr = kd.get("close", [])
                    vol_arr = kd.get("volume", kd.get("vol", []))
            elif isinstance(kd, list):
                execution_logs.append(f"[{symbol}] {tf_label} data list length: {len(kd)}")
                if len(kd) > 0:
                    execution_logs.append(f"[{symbol}] {tf_label} head sample object type: {type(kd[0])}")
                    if isinstance(kd[0], list):
                        execution_logs.append(f"[{symbol}] {tf_label} list element sample: {kd[0]}")
                        high_arr = [x[3] for x in kd]
                        low_arr = [x[4] for x in kd]
                        close_arr = [x[2] for x in kd]
                        vol_arr = [x[5] for x in kd]
                    elif isinstance(kd[0], dict):
                        execution_logs.append(f"[{symbol}] {tf_label} dict elements sample: {list(kd[0].keys())}")
                        high_arr = [x.get("high") for x in kd]
                        low_arr = [x.get("low") for x in kd]
                        close_arr = [x.get("close") for x in kd]
                        vol_arr = [x.get("vol", x.get("volume", 0)) for x in kd]
                    else:
                        execution_logs.append(f"[{symbol}] RETURN NONE: Unsupported nested element layout matrix type.")
                        return None
                else:
                    execution_logs.append(f"[{symbol}] RETURN NONE: Data list payload returned completely empty.")
                    return None
            else:
                execution_logs.append(f"[{symbol}] RETURN NONE: Unparseable global structural canvas type layout.")
                return None
                
            execution_logs.append(f"[{symbol}] Unpacked {tf_label} arrays. high count: {len(high_arr)}, low count: {len(low_arr)}, close count: {len(close_arr)}")
            
            if not close_arr or len(close_arr) < 15:
                execution_logs.append(f"[{symbol}] RETURN NONE: {tf_label} close vector contains insufficient bars (Length: {len(close_arr) if close_arr else 0})")
                return None
                
            df = pd.DataFrame({
                "high": pd.to_numeric(high_arr),
                "low": pd.to_numeric(low_arr),
                "close": pd.to_numeric(close_arr),
                "volume": pd.to_numeric(vol_arr)
            })
            
            df["open_interest"] = live_oi
            df["funding_rate"] = live_funding
            
            execution_logs.append(f"[{symbol}] DataFrame successfully mounted for {tf_label}. Row count: {len(df)}")
            data_feeds[tf_label] = df
            
        execution_logs.append(f"[{symbol}] FETCH SUCCESS: Multi-timeframe structures compiled fully.")
        return data_feeds
    except Exception as e:
        print(f"ERROR in fetch_mexc_live_data: {e}")
        execution_logs.append(f"EXCEPTION raised in fetch loop for {symbol}: {str(e)}")
        return None

@app.get("/", response_class=HTMLResponse)
def render_mobile_radar_dashboard():
    debug_log = []
    debug_log.append("Executing live telemetry diagnostic sequence...")
    
    priority_watchlist = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT"]
    raw_scan_results = []
    
    for symbol in priority_watchlist:
        datasets = fetch_mexc_live_data(symbol, debug_log)
        
        if datasets is not None:
            debug_log.append(f"[{symbol}] FETCH SUCCESS")
            try:
                metrics = scanner.scan_symbol(symbol, datasets)
                if metrics:
                    raw_scan_results.append(metrics)
                    debug_log.append(f"[{symbol}] SCAN SUCCESS -> Resulting Score: {metrics.get('sort_score')}, Status: {metrics.get('status')}")
                else:
                    debug_log.append(f"[{symbol}] SCAN FAILED: Engine evaluated empty metrics return state.")
            except Exception as e:
                print(f"ERROR in scanner routing layout: {e}")
                debug_log.append(f"[{symbol}] SCAN FAILED: Raised critical exception inside calculation matrix: {str(e)}")
        else:
            debug_log.append(f"[{symbol}] FETCH FAILED")
            
        time.sleep(0.1)

    # Telemetry Guard Hook: Expose the system parameters on-screen if processing falls through
    if not raw_scan_results:
        log_items_html = "".join([f"<li>{line}</li>" for line in debug_log])
        fallback_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: monospace; padding: 15px; background: #1a1a1a; color: #00ff00; line-height: 1.4; }}
                h2 {{ color: #ff3333; border-bottom: 1px solid #ff3333; padding-bottom: 5px; }}
                ul {{ list-style-type: none; padding-left: 0; }}
                li {{ margin-bottom: 6px; border-left: 3px solid #00ff00; padding-left: 8px; white-space: pre-wrap; word-break: break-all; }}
            </style>
        </head>
        <body>
            <h2>DIAGNOSTIC CRITICAL FAILURE: NO RUNTIME METRICS PRODUCED</h2>
            <p><strong>Reason:</strong> raw_scan_results tracking list remained empty after evaluation loop completed.</p>
            <h3>Live Telemetry Execution Chain Logs:</h3>
            <ul>{log_items_html}</ul>
        </body>
        </html>
        """
        return fallback_html

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

        if top_candidate.get('status') in ['CRITICAL', 'ABOUT TO BREAK']:
            interpretation = "Long-lived compression with rising open interest and contracting volatility. Range appears increasingly unstable."
        elif top_candidate.get('status') == 'LOADING':
            interpretation = "Accumulation structures intensifying across inner loops. Multi-timeframe velocity starting to stress range bounds."
        else:
            interpretation = "Structural framework remaining inside standard variance parameters. Low expansion probability near-term."

        dashboard_text += f"""\n\n{top_candidate.get('symbol')}

Status:
{top_candidate.get('status')}

Confidence:
{top_candidate.get('confidence')}

Range Width:
{top_candidate.get('width')}%

Range Age:
{top_candidate.get('age')} candles

ATR Contraction:
{int(top_candidate.get('atr_contract', 0))}%

OI Growth:
{top_candidate.get('oi_growth')}%

15M:
{top_candidate.get('p_15m')}

5M:
{top_candidate.get('p_5m')}

3M:
{top_candidate.get('p_3m')}

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
    
