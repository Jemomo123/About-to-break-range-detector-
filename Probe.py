import requests
import time
import socket

print("=== OKX CONNECTIVITY PROBE ===\n")

# 1. DNS Test
print("1. DNS Resolution...")
try:
    ip = socket.gethostbyname("www.okx.com")
    print(f"   ✅ OK: {ip}")
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    exit()

# 2. TCP Test
print("\n2. TCP Connection...")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    start = time.time()
    sock.connect(("www.okx.com", 443))
    elapsed = time.time() - start
    sock.close()
    print(f"   ✅ OK: {elapsed:.2f}s")
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    exit()

# 3. HTTP Test
print("\n3. HTTP Request...")
url = "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=15m&limit=10"
try:
    start = time.time()
    print("   [ENTER] Sending request...")
    r = requests.get(url, timeout=10)
    print(f"   [RETURN] Status: {r.status_code}")
    print(f"   ✅ OK: {time.time()-start:.2f}s")
    print(f"   Candles: {len(r.json()['data'])}")
except Exception as e:
    print(f"   ❌ FAILED: {e}")

print("\n=== PROBE COMPLETE ===")
