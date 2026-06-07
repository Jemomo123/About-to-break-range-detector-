import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from scanner import MarketScanner

app = FastAPI()
scanner = MarketScanner()

def generate_radar_mock(symbol: str, target_profile: str):
    np.random.seed(abs(hash(symbol)) % 10000)
    size = 50
    if target_profile == "EXPLOSIVE":
        closes = [100.0 + np.sin(i / 4) * 0.4 for i in range(size)]
        highs = [c + 0.2 for c in closes]
        lows = [c - 0.2 for c in closes]
        volumes = [400 for _ in range(size)]
        oi = [500000 + (i * 4500) for i in range(size)]
        funding = [0.0006 for _ in range(size)]
    elif target_profile == "LOADING":
        closes = [50.0 + np.sin(i / 3) * 0.5 for i in range(size)]
        highs = [c + 0.4 for c in closes]
        lows = [c - 0.4 for c in closes]
        volumes = [700 for _ in range(size)]
        oi = [200000 + (i * 1800) for i in range(size)]
        funding = [0.0001 for _ in range(size)]
    else:
        closes = [20.0 + (i * 0.15) for i in range(size)]
        highs = [c + 1.2 for c in closes]
        lows = [c - 1.2 for c in closes]
        volumes = [3000 for _ in range(size)]
        oi = [100000 for _ in range(size)]
        funding = [0.0001 for _ in range(size)]

    df = pd.DataFrame({"high": highs, "low": lows, "close": closes, "volume": volumes, "open_interest": oi, "funding_rate": funding})
    return {"15m": df, "5m": df, "3m": df}

@app.get("/", response_class=HTMLResponse)
def render_mobile_radar_dashboard():
    market_universe = {
        "BTC_USDT": "EXPLOSIVE", "ETH_USDT": "LOADING", "SOL_USDT": "LOADING",
        "XRP_USDT": "NORMAL", "DOGE_USDT": "NORMAL", "ADA_USDT": "NORMAL", "AVAX_USDT": "NORMAL"
    }
    
    raw_scan_results = []
    for symbol, profile in market_universe.items():
        datasets = generate_radar_mock(symbol, profile)
        metrics = scanner.scan_symbol(symbol, datasets)
        raw_scan_results.append(metrics)

    global_temp = scanner.calculate_market_temperature(raw_scan_results)
    sorted_pool = [r for r in raw_scan_results if r["sort_score"] >= 0]
    sorted_pool = sorted(sorted_pool, key=lambda x: x["sort_score"], reverse=True)
    counts = global_temp["metrics"]
    
    # 1. BUILD THE STRINGS
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

    # 2. WRAP IT IN LIGHTWEIGHT MOBILE HTML FOR CHROME MOBILE
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
                font-size: 14px;
                line-height: 1.5;
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
