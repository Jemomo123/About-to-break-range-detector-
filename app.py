# --- GLOBAL ENDPOINT POOL FOR FAILOVER ---
MEXC_ENDPOINTS = [
    "https://contract.mexc.com",
    "https://api.mexc.com",  # Alternate primary routing line
    "https://wapi.mexc.com"   # Backup web routing interface
]

def fetch_mexc_data(symbol="BTC_USDT", interval="Min5"):
    """
    Fetches real-time market metrics from MEXC Futures with a 3-tier API failover protocol.
    If an endpoint fails, the scanner immediately falls back to the next available mirror line.
    """
    global MEXC_ENDPOINTS
    
    # Try each mirror server sequentially
    for base_url in MEXC_ENDPOINTS:
        try:
            # 1. Fetch Candlestick Records
            kline_url = f"{base_url}/api/v1/contract/kline/{symbol}"
            params = {"interval": interval, "limit": 100}
            
            response = requests.get(kline_url, params=params, timeout=5)
            
            # If server throws a bad gateway (5xx) or rate-limit error, skip to next line
            if response.status_code != 200:
                print(f"⚠️ Server alert on {base_url} (Status {response.status_code}). Switching mirror...")
                continue
                
            res_json = response.json()
            if not res_json.get("success", False) or not res_json.get("data"):
                continue
                
            data = res_json["data"]
            
            # Structure timeline metrics
            df = pd.DataFrame({
                'high': data.get('high', []),
                'low': data.get('low', []),
                'close': data.get('close', []),
                'volume': data.get('vol', []),
                'open_interest': data.get('openInterest', [])
            })
            
            if df.empty:
                continue

            # Force numeric conversion for clean math processing
            numeric_cols = ['high', 'low', 'close', 'volume', 'open_interest']
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)

            # 2. Fetch Funding Rate (using the matching functional server line)
            fund_url = f"{base_url}/api/v1/contract/funding_rate/{symbol}"
            fund_res = requests.get(fund_url, timeout=5).json()
            
            funding_rate = 0.0
            if fund_res.get("success") and "data" in fund_res:
                funding_rate = float(fund_res["data"].get("fundingRate", 0.0)) * 100
            
            df['funding_rate'] = funding_rate
            
            # Rotate working server to the front of the list to speed up future requests
            if base_url != MEXC_ENDPOINTS[0]:
                MEXC_ENDPOINTS.remove(base_url)
                MEXC_ENDPOINTS.insert(0, base_url)
                
            return df

        except (requests.exceptions.RequestException, Exception) as e:
            print(f"❌ Connection timeout/failure on {base_url}. Activating failover link...")
            continue
            
    print(f"🚨 CRITICAL: All MEXC API failover routes exhausted for {symbol}.")
    return None
