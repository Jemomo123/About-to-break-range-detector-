import subprocess
import time
import shlex
from datetime import datetime

print("=== OS-LEVEL CURL DIAGNOSTIC ===\n")
print(f"[START] {datetime.now().isoformat()}")

# Test 1: OKX endpoint
print("\n" + "="*80)
print("TEST 1: OKX API")
print("="*80)

okx_url = "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=15m&limit=150"
print(f"[URL] {okx_url}")

curl_cmd = [
    "curl",
    "-v",
    "--connect-timeout", "5",
    "--max-time", "15",
    okx_url
]

print(f"[COMMAND] {' '.join(curl_cmd)}")
print(f"\n[EXECUTING] {datetime.now().isoformat()}")

try:
    start_time = time.time()
    result = subprocess.run(
        curl_cmd,
        capture_output=True,
        text=True,
        timeout=20  # Hard timeout for the subprocess
    )
    elapsed = time.time() - start_time
    
    print(f"[COMPLETED] {datetime.now().isoformat()} ({elapsed:.2f}s)")
    print(f"[EXIT CODE] {result.returncode}")
    
    # Parse output for specific markers
    stdout = result.stdout
    stderr = result.stderr
    combined = stdout + stderr
    
    # Extract key diagnostic lines
    lines = combined.split('\n')
    
    print("\n--- RAW OUTPUT ---")
    for line in lines:
        if any(key in line.lower() for key in [
            'dns', 'resolve', 'connected', 'ssl', 'tls', 
            'http', 'content-length', 'curl', 'error',
            'timed out', 'timeout', 'failed', 'unable'
        ]):
            print(f"[CURL] {line}")
    
    print("\n--- DIAGNOSTIC SUMMARY ---")
    
    # Check for DNS
    if 'Resolving' in combined or 'DNS' in combined:
        print("[DNS] ✅ DNS resolution attempted")
        if 'Resolving' in combined:
            for line in lines:
                if 'Resolving' in line or 'DNS' in line:
                    print(f"  {line.strip()}")
    
    # Check for connection
    if 'Connected to' in combined:
        print("[TCP CONNECT] ✅ TCP connection successful")
        for line in lines:
            if 'Connected to' in line:
                print(f"  {line.strip()}")
    elif 'Failed to connect' in combined or 'Connection refused' in combined:
        print("[TCP CONNECT] ❌ Connection failed")
    
    # Check for TLS/SSL
    if 'SSL' in combined or 'TLS' in combined:
        print("[TLS HANDSHAKE] ✅ TLS handshake attempted")
        for line in lines:
            if 'SSL' in line or 'TLS' in line:
                print(f"  {line.strip()}")
    
    # Check for HTTP status
    if 'HTTP/1.1' in combined or 'HTTP/2' in combined:
        print("[HTTP STATUS] ✅ HTTP response received")
        for line in lines:
            if 'HTTP/' in line:
                print(f"  {line.strip()}")
    elif 'No route to host' in combined:
        print("[HTTP STATUS] ❌ No route to host")
    elif 'timed out' in combined.lower():
        print("[HTTP STATUS] ❌ Timeout")
    
    # Check for response length
    if 'content-length' in combined.lower():
        for line in lines:
            if 'content-length' in line.lower():
                print(f"[RESPONSE LENGTH] {line.strip()}")
    
    print(f"[CURL EXIT CODE] {result.returncode}")
    
    if result.returncode == 0:
        print("[RESULT] ✅ OKX request succeeded")
    elif result.returncode == 28:
        print("[RESULT] ❌ CURL timeout (exit code 28)")
    elif result.returncode == 6:
        print("[RESULT] ❌ DNS resolution failed (exit code 6)")
    elif result.returncode == 7:
        print("[RESULT] ❌ Connection failed (exit code 7)")
    elif result.returncode == 35:
        print("[RESULT] ❌ SSL/TLS error (exit code 35)")
    else:
        print(f"[RESULT] ⚠️ Unknown exit code: {result.returncode}")
        
except subprocess.TimeoutExpired:
    print(f"[CURL HARD TIMEOUT] Subprocess terminated after 20 seconds")
    print("[RESULT] ❌ CURL hard timeout - process killed")
except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}")

# Test 2: Google control test
print("\n" + "="*80)
print("TEST 2: Google (Control)")
print("="*80)

google_url = "https://www.google.com"
print(f"[URL] {google_url}")

curl_cmd2 = [
    "curl",
    "-v",
    "--connect-timeout", "5",
    "--max-time", "15",
    google_url
]

print(f"[COMMAND] {' '.join(curl_cmd2)}")
print(f"\n[EXECUTING] {datetime.now().isoformat()}")

try:
    start_time = time.time()
    result2 = subprocess.run(
        curl_cmd2,
        capture_output=True,
        text=True,
        timeout=20
    )
    elapsed = time.time() - start_time
    
    print(f"[COMPLETED] {datetime.now().isoformat()} ({elapsed:.2f}s)")
    print(f"[EXIT CODE] {result2.returncode}")
    
    combined2 = result2.stdout + result2.stderr
    
    # Quick summary for Google
    if 'Connected to' in combined2:
        print("[TCP CONNECT] ✅ Connected to Google")
    if 'HTTP/' in combined2:
        print("[HTTP STATUS] ✅ HTTP response received")
    if 'content-length' in combined2.lower():
        for line in combined2.split('\n'):
            if 'content-length' in line.lower():
                print(f"[RESPONSE LENGTH] {line.strip()}")
    
    print(f"[CURL EXIT CODE] {result2.returncode}")
    
    if result2.returncode == 0:
        print("[RESULT] ✅ Google request succeeded")
    elif result2.returncode == 28:
        print("[RESULT] ❌ Google timeout")
    else:
        print(f"[RESULT] ⚠️ Google exit code: {result2.returncode}")
        
except subprocess.TimeoutExpired:
    print(f"[CURL HARD TIMEOUT] Google subprocess terminated after 20 seconds")
except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}")

print("\n" + "="*80)
print("[DIAGNOSTIC COMPLETE]")
print(f"[END] {datetime.now().isoformat()}")
