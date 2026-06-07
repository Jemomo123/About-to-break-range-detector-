import time
import requests
import pandas as pd
from flask import Flask
from threading import Thread

# Create a tiny web server so Render knows the service is alive and healthy
app = app = Flask(__name__)


@app.route('/')
def home():
    Return "Compression Engine is active and scanning.", 200

Def run_web_server():
    App.run(host='0.0.0.0', port=10000)

# --- MEXC DATA FETCHING ---
DEF fetch_mexc_data(symbol="BTCUSDT", interval="5m"):
    """Fetches recent OHLCV data from MEXC public API."""
    Try:
        # MEXC API endpoint for Spot/Futures klines
        Url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}"
        Params = {"interval": interval, "limit": 60}
        Response = requests.get(url, params=params, timeout=10).json()
        
        If not response.get("success", False):
            Return None
            
        Data = response["data"]
        
        # Format into a clean DataFrame
        Df = pd.DataFrame({
            'high': data['high'],
            'low': data['low'],
            'close': data['close'],
            'volume': data['vol'],
            'open_interest': data['openInterest']
        })
        
        # Fetch funding rate separately
        Fund_url = f"https://contract.mexc.com/api/v1/contract/funding_rate/{symbol}"
        Fund_res = requests.get(fund_url, timeout=10).json()
        Funding_rate = fund_res["data"]["fundingRate"] if fund_res.get("success") else 0.0
        
        Df['funding_rate'] = funding_rate
        Return df
    Except Exception as e:
        Print(f"Error fetching data: {e}")
        Return None

# --- ENGINE LOGIC ---
DEF calculate_pressure_score(df, compression_age=10):
    If len(df) < 35:
        Return None

    # 1. ATR Contraction
    High_low = df['high'] - df['low']
    High_close_prev = (df['high'] - df['close'].shift(1)).abs()
    Low_close_prev = (df['low'] - df['close'].shift(1)).abs()
    Tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    Df['atr_14'] = tr.rolling(window=14).mean()
    
    Atr_baseline = df['atr_14'].shift(1).rolling(window=20).mean().iloc[-1]
    Current_atr = df['atr_14'].iloc[-1]
    Atr_contraction_pct = ((current_atr - atr_baseline) / atr_baseline) * 100

    # 2. Volume Contraction
    Current_vol_avg = df['volume'].iloc[-5:].mean()
    Vol_baseline = df['volume'].iloc[-25:-5].mean()
    Vol_contraction_pct = ((current_vol_avg - vol_baseline) / vol_baseline) * 100

    # 3. Open Interest Change
    Oi_window = min(compression_age, len(df))
    Historical_oi = df['open_interest'].iloc[-oi_window]
    Current_oi = df['open_interest'].iloc[-1]
    Oi_change_pct = ((current_oi - historical_oi) / historical_oi) * 100 if historical_oi > 0 else 0

    # 4. Funding Condition
    Current_funding = df['funding_rate'].iloc[-1]

    # Scoring Matrix
    Score = 0
    If current_atr < atr_baseline: score += 1
    If compression_age >= 8: score += 1
    If current_vol_avg < vol_baseline: score += 1
    If oi_change_pct >= 3.0: score += 1
    If current_funding > 0.03 or current_funding < -0.03: score += 1

    Status = "NORMAL"
    If score >= 5: status = "LOADED"
    Elif score == 4: status = "HIGH ALERT"
    Elif score == 3: status = "WATCH"

    Return {
        "age": compression_age, "atr": atr_contraction_pct, "vol": vol_contraction_pct,
        "oi": oi_change_pct, "funding": current_funding, "score": score, "status": status
    }

# --- SCANNER ENGINE LOOP ---
DEF scanner_loop():
    Print("Starting Compression Pressure Loop...")
    While True:
        # Loop over your focus configurations
        For symbol in ["BTC_USDT", "ETH_USDT"]: 
            Df = fetch_mexc_data(symbol, interval="5m")
            If df is not None:
                Metrics = calculate_pressure_score(df, compression_age=12) # Example static age
                
                If metrics:
                    Print(f"\n=== {symbol} === ")
                    Print(f"Age: {metrics['age']} candles | ATR: {metrics['atr']:.1f}% | Vol: {metrics['vol']:.1f}%")
                    Print(f"OI: {metrics['oi']:+.1f}% | Funding: {metrics['funding']:+.4f}%")
                    Print(f"Score: {metrics['score']}/5 -> STATUS: {metrics['status']}")
                    
                    If metrics['score'] >= 4:
                        Print("🚨 ALERT: COMPRESSION LOADED. Monitor for Elephant Candle / Expansion.")
        
        Time.sleep(60) # Scan every 60 seconds

If __name__ == "__main__":
    # Start the web server thread so Render stays happy
    Web_thread = Thread(target=run_web_server)
    Web_thread.daemon = True
    Web_thread.start()
    
    # Run the continuous scanner loop
    Scanner_loop()
