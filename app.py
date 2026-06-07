import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from scanner import MarketScanner

app = FastAPI()
scanner = MarketScanner()

def generate_radar_mock(symbol: str, target_profile: str):
    """Generates synthetic multi-timeframe structural parameters for engine tracking verification."""
    np.random.seed(abs(hash(symbol)) % 10000)
    size = 50
    
    if target_profile == "EXPLOSIVE":
        # Multi-timeframe structural compression profile
        closes = [100.0 + np.sin(i / 4) * 0.4 for i in range(size)]
        highs = [c + 0.2 for c in closes]
        lows = [c - 0.2 for c in closes]
        volumes = [400 for _ in range(size)]
        oi = [500000 + (i * 4500) for i in range(size)] # Fast buildup > 7%
        funding = [0.0006 for _ in range(size)]
    elif target_profile == "LOADING":
        closes = [50.0 + np.sin(i / 3) * 0.5 for i in range(size)]
        highs = [c + 0.4 for c in closes]
        lows = [c - 0.4 for c in closes]
        volumes = [700 for _ in range(size)]
        oi = [200000 + (i * 1800) for i in range(size)] # Buildup > 3%
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

@app.get("/", response_class=PlainTextResponse)
def render_mobile_radar_dashboard():
    # Build a simulated target environment across diverse asset profiles
    market_universe = {
        "BTC_USDT": "EXPLOSIVE", "ETH_USDT": "LOADING", "SOL_USDT": "LOADING",
        "XRP_USDT": "NORMAL", "DOGE_USDT": "NORMAL", "ADA_USDT": "NORMAL", "AVAX_USDT": "NORMAL"
    }
    
    raw_scan_results = []
    for symbol, profile in market_universe.items():
        datasets = generate_radar_mock(symbol, profile)
        metrics = scanner.scan_symbol(symbol, datasets)
        raw_scan_results.append(metrics)

    # Compute operational rankings and temperature indices
    global_temp = scanner.calculate_market_temperature(raw_scan_results)
    sorted_pool = [r for r in raw_scan_results if r["sort_score"] >= 0]
    sorted_pool = sorted(sorted_pool, key=lambda x: x["sort_score"], reverse=True)

    counts = global_temp["metrics"]
    
    # 1. BUILD DYNAMIC RADAR HEADER LAYOUT
    output = f"""MARKET TEMPERATURE
{global_temp['temperature']}
No Range: {counts['NO RANGE']}
Stable Range: {counts['STABLE RANGE']}
Building: {counts['BUILDING']}
Loading: {counts['LOADING']}
About To Break: {counts['ABOUT TO BREAK']}
Critical: {counts['CRITICAL']}
====================================================="""

    if not sorted_pool:
        output += "\n\nNO MATURE COMPRESSIONS DETECTED ACROSS TRACKING CHANNELS."
        return output

    top_candidate = sorted_pool[0]

    # 2. RENDER CURRENT TOP CANDIDATE INTERFACE
    output += f"""\n\nTOP CANDIDATE
{top_candidate['symbol']}
Status: {top_candidate['status']}"""

    # 3. RENDER TOP 5 WATCHLIST GRID MATRIX
    output += "\n\nTOP CANDIDATES\n"
    for idx, item in enumerate(sorted_pool[:5], 1):
        output += f"{idx}. {item['symbol']} -> {item['status']}\n"
    output += "====================================================="

    # 4. PARSE VERBOSE SPECIFIC REPORT CARD FORMAT DETAILS FOR THE LEADING CANDIDATE
    # Apply context interpretation matrices based on structural loads
    if top_candidate['status'] in ['CRITICAL', 'ABOUT TO BREAK']:
        interpretation = "Long-lived compression with rising open interest and contracting volatility. Range appears increasingly unstable."
    elif top_candidate['status'] == 'LOADING':
        interpretation = "Accumulation structures intensifying across inner loops. Multi-timeframe velocity starting to stress range bounds."
    else:
        interpretation = "Structural framework remaining inside standard variance parameters. Low expansion probability near-term."

    output += f"""\n\n{top_candidate['symbol']}

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
    return output
