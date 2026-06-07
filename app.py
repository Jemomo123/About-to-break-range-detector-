import os
import time
import threading
import requests
import pandas as pd
import numpy as np
from flask import Flask

# 1. Initialize the application server
app = Flask(__name__)

# --- GLOBAL ENDPOINT POOL FOR FAILOVER ---
MEXC_ENDPOINTS = [
    "https://contract.mexc.com",
    "https://api.mexc.com",
    "https://wapi.mexc.com"
]

def fetch_mexc_data(symbol="BTC_USDT", interval="Min5"):
    global MEXC_ENDPOINTS
    for base_url in MEXC_ENDPOINTS:
        try:
            kline_url = f"{base_url}/api/v1/contract/kline/{symbol}"
            params = {"interval": interval, "limit": 100}
            response = requests.get(kline_url, params=params, timeout=5)
            if response.status_code != 200:
                continue
            res_json = response.json()
            if not res_json.get("success", False) or not res_json.get("data"):
                continue
            data = res_json["data"]
            df = pd.DataFrame({
                'high': data.get('high', []),
                'low': data.get('low', []),
                'close': data.get('close', []),
                'volume': data.get('vol', []),
                'open_interest': data.get('openInterest', [])
            })
            if df.empty:
                continue
            numeric_cols = ['high', 'low', 'close', 'volume', 'open_interest']
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)
            fund_url = f"{base_url}/api/v1/contract/funding_rate/{symbol}"
            fund_res = requests.get(fund_url, timeout=5).json()
            funding_rate = 0.0
            if fund_res.get("success") and "data" in fund_res:
                funding_rate = float(fund_res["data"].get("fundingRate", 0.0)) * 100
            df['funding_rate'] = funding_rate
            if base_url != MEXC_ENDPOINTS[0]:
                MEXC_ENDPOINTS.remove(base_url)
                MEXC_ENDPOINTS.insert(0, base_url)
            return df
        except Exception:
            continue
    return None

def calculate_compression_score(df):
    if df is None or len(df) < 35:
        return 0
    try:
        # Calculate ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(14).mean()
        
        # Rule 1: Volatility Contraction
        current_atr = atr.iloc[-1]
        historical_atr = atr.iloc[-21:-1].mean()
        v_score = 1 if current_atr < historical_atr else 0
        
        # Rule 2: Volume Exhaustion
        current_vol = df['volume'].iloc[-5:].mean()
        historical_vol = df['volume'].iloc[-25:-5].mean()
        vol_score = 1 if current_vol < historical_vol else 0
        
        # Rule 3: Open Interest Build-up
        oi_start = df['open_interest'].iloc[-10]
        oi_end = df['open_interest'].iloc[-1]
        oi_change = ((oi_end - oi_start) / oi_start) * 100 if oi_start != 0 else 0
        oi_score = 1 if oi_change >= 3.0 else 0
        
        # Rule 4: Crowded Funding
        current_funding = abs(df['funding_rate'].iloc[-1])
        funding_score = 1 if current_funding >= 0.03 else 0
        
        total_score = v_score + vol_score + oi_score + funding_score
        return total_score
    except Exception:
        return 0

def scanner_loop():
    symbols = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]
    timeframes = {"3m": "Min3", "5m": "Min5", "15m": "Min15", "1h": "Hour1", "4h": "Hour4"}
    
    print("=== Compression Engine is active and scanning ===")
    while True:
        try:
            for symbol in symbols:
                for tf_name, tf_code in timeframes.items():
                    df = fetch_mexc_data(symbol, tf_code)
                    score = calculate_compression_score(df)
                    
                    status = "NORMAL"
                    if score == 3:
                        status = "WATCH"
                    elif score == 4:
                        status = "HIGH ALERT"
                    elif score == 5:
                        status = "LOADED"
                        
                    if score >= 3:
                        print(f"[{symbol} - {tf_name}] Score: {score}/4 | Status: {status}")
            time.sleep(45)
        except Exception as e:
            print(f"Scanner Loop Error: {e}")
            time.sleep(10)

# Start background work
threading.Thread(target=scanner_loop, daemon=True).start()

# 2. Beautiful display layout route
@app.route('/')
def home():
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
