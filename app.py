import time
import requests
import pandas as pd
import numpy as np
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    # Large, bold, centered, mobile-responsive text
    return """
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {
                    background-color: #0d1117;
                    color: #58a6ff;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    text-align: center;
                }
                .status-box {
                    border: 2px solid #30363d;
                    padding: 30px;
                    border-radius: 12px;
                    background-color: #161b22;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.5);
                }
                h1 {
                    font-size: 28px;
                    margin: 0 0 10px 0;
                    color: #2ea44f;
                }
                p {
                    font-size: 18px;
                    margin: 0;
                    color: #c9d1d9;
                }
            </style>
        </head>
        <body>
            <div class="status-box">
                <h1>⚡ ENGINE ONLINE</h1>
                <p>Compression Pressure Scanner is actively monitoring MEXC...</p>
            </div>
        </body>
    </html>
    """, 200


def run_web_server():
    # Binds to the port Render expects
    app.run(host='0.0.0.0', port=10000)

# --- PRODUCTION MEXC DATA FETCHER ---
def fetch_mexc_data(symbol="BTC_USDT", interval="Min5"):
    """
    Fetches real-time OHLCV, Open Interest, and Funding data from MEXC Futures API.
    Valid intervals for MEXC Futures include: Min3, Min5, Min15, Min60, Hour4
    """
    try:
        # 1. Fetch Kline/Candlestick records
        url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}"
        params = {"interval": interval, "limit": 100}
        response = requests.get(url, params=params, timeout=10).json()
        
        if not response.get("success", False) or not response.get("data"):
            return None
            
        data = response["data"]
        
        # Structure the individual timeline metrics arrays
        df = pd.DataFrame({
            'time': data.get('time', []),
            'high': data.get('high', []),
            'low': data.get('low', []),
            'close': data.get('close', []),
            'volume': data.get('vol', []),
            'open_interest': data.get('openInterest', [])
        })
        
        if df.empty:
            return None

        # Convert object metrics explicitly to floating numbers
        numeric_cols = ['high', 'low', 'close', 'volume', 'open_interest']
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)

        # 2. Fetch Funding Rate separately
        fund_url = f"https://contract.mexc.com/api/v1/contract/funding_rate/{symbol}"
        fund_res = requests.get(fund_url, timeout=10).json()
        
        funding_rate = 0.0
        if fund_res.get("success") and "data" in fund_res:
            # Convert decimal representation to a clean percent baseline (e.g., 0.0004 -> 0.04)
            funding_rate = float(fund_res["data"].get("fundingRate", 0.0)) * 100
        
        df['funding_rate'] = funding_rate
        return df
    except Exception as e:
        print(f"Error communicating with MEXC API: {e}")
        return None

# --- PRESSURE SCORE LOGIC ENGINE ---
def calculate_pressure_score(df: pd.DataFrame, compression_age: int) -> dict:
    if len(df) < 40:
        return None

    # 1. ATR Contraction Evaluation
    high_low = df['high'] - df['low']
    high_close_prev = (df['high'] - df['close'].shift(1)).abs()
    low_close_prev = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    
    df['atr_14'] = tr.rolling(window=14).mean()
    
    # Calculate baseline using the 20 candles prior to the current candle
    atr_baseline = df['atr_14'].shift(1).iloc[-20:].mean()
    current_atr = df['atr_14'].iloc[-1]
    atr_contraction_pct = ((current_atr - atr_baseline) / atr_baseline) * 100

    # 2. Volume Contraction Evaluation
    current_vol_avg = df['volume'].iloc[-5:].mean()
    # Exclude the last 5 candles to get the true baseline of the 20 preceding candles
    vol_baseline = df['volume'].iloc[-25:-5].mean()
    vol_contraction_pct = ((current_vol_avg - vol_baseline) / vol_baseline) * 100

    # 3. Open Interest Change inside the Range Structure
    oi_window = min(compression_age, len(df))
    historical_oi = df['open_interest'].iloc[-oi_window]
    current_oi = df['open_interest'].iloc[-1]
    oi_change_pct = ((current_oi - historical_oi) / historical_oi) * 100 if historical_oi > 0 else 0.0

    # 4. Crowded Funding evaluation (+/- 0.03%)
    current_funding = df['funding_rate'].iloc[-1]

    # --- SCORE CALCULATION MATRIX ---
    score = 0
    if current_atr < atr_baseline: 
        score += 1
    if compression_age >= 8: 
        score += 1
    if current_vol_avg < vol_baseline: 
        score += 1
    if oi_change_pct >= 3.0: 
        score += 1
    if current_funding > 0.03 or current_funding < -0.03: 
        score += 1

    # --- STATE CLASSIFICATION ---
    if score >= 5:
        status = "LOADED"
    elif score == 4:
        status = "HIGH ALERT"
    elif score == 3:
        status = "WATCH"
    else:
        status = "NORMAL"

    return {
        "age": compression_age,
        "atr_pct": atr_contraction_pct,
        "vol_pct": vol_contraction_pct,
        "oi_pct": oi_change_pct,
        "funding": current_funding,
        "score": score,
        "status": status
    }

# --- ACTIVE SCHEDULER SCAN LOOP ---
def scanner_loop():
    print("Scanner Engine Activated. Watching structural configurations...")
    # Map your execution preferences to native MEXC parameters
    monitored_assets = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]
    intervals = ["Min3", "Min5", "Min15", "Min60"]

    while True:
        for symbol in monitored_assets:
            for tf in intervals:
                df = fetch_mexc_data(symbol=symbol, interval=tf)
                if df is not None:
                    # Dynamically passing a fallback compression window (e.g., 12)
                    metrics = calculate_pressure_score(df, compression_age=12)
                    
                    if metrics and metrics['score'] >= 3:
                        print("\n====================================================")
                        print(f"COMPRESSION PRESSURE | {symbol} ({tf})")
                        print(f"Age: {metrics['age']} candles")
                        print(f"ATR: {metrics['atr_pct']:.1f}%")
                        print(f"Volume: {metrics['vol_pct']:.1f}%")
                        print(f"OI: {metrics['oi_pct']:+.1f}%")
                        print(f"Funding: {metrics['funding']:+.4f}%")
                        print("----------------------------------------------------")
                        print(f"Pressure Score: {metrics['score']}/5")
                        print(f"\nSTATUS:\n{metrics['status']}")
                        print("====================================================")
                        
                        if metrics['score'] >= 4:
                            print("\n🚨 COMPRESSION LOADED.")
                            print("Monitor for Elephant Candle and Expansion Trigger. 🚨\n")
                            
        time.sleep(45)  # Scan interval buffer

if __name__ == "__main__":
    # Prevent Render from killing execution via a parallel listener thread
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()
    
    scanner_loop()
