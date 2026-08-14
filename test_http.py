import requests
import time

URL = "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=15m&limit=150"

print("=== ISOLATED HTTP TEST ===\n")
print(f"URL: {URL}")
print("[HTTP TEST BEFORE]")

try:
    print("[HTTP] Executing requests.get()...")
    start_time = time.time()
    
    response = requests.get(
        URL,
        timeout=(5, 10),
        headers={"User-Agent": "Mozilla/5.0"}
    )
    
    elapsed = time.time() - start_time
    print(f"[HTTP TEST RETURNED] (after {elapsed:.2f}s)")
    print(f"[HTTP STATUS] {response.status_code}")
    print(f"[HTTP RESPONSE LENGTH] {len(response.text)} bytes")
    
    if response.status_code == 200:
        print("[RESULT] ✅ Request succeeded - HTTP 200 OK")
    else:
        print(f"[RESULT] ⚠️ HTTP {response.status_code}")
        
except requests.exceptions.Timeout as e:
    elapsed = time.time() - start_time
    print(f"[HTTP TEST RETURNED] Timeout after {elapsed:.2f}s")
    print("[HTTP EXCEPTION] Timeout")
    print(f"[EXCEPTION MESSAGE] {str(e)}")
    print("[RESULT] ❌ Request timed out")
    
except requests.exceptions.ConnectionError as e:
    elapsed = time.time() - start_time
    print(f"[HTTP TEST RETURNED] ConnectionError after {elapsed:.2f}s")
    print("[HTTP EXCEPTION] ConnectionError")
    print(f"[EXCEPTION MESSAGE] {str(e)}")
    print("[RESULT] ❌ Connection error")
    
except Exception as e:
    elapsed = time.time() - start_time
    print(f"[HTTP TEST RETURNED] Exception after {elapsed:.2f}s")
    print(f"[HTTP EXCEPTION] {type(e).__name__}")
    print(f"[EXCEPTION MESSAGE] {str(e)}")
    print("[RESULT] ❌ Unexpected error")

print("\n=== TEST COMPLETE ===")
