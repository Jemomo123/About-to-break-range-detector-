#!/usr/bin/env python3
"""
CURL NETWORK DIAGNOSTIC - OS-Level Connectivity Test
Does NOT use Python requests library
Replaces the old requests-based probe entirely
"""

import subprocess
import time
import os
import sys
from datetime import datetime

def run_curl_diagnostic():
    """Run OS-level curl tests against OKX and Google"""
    
    print(">>> CURL NETWORK DIAGNOSTIC DEPLOYED <<<")
    print(f"[START] {datetime.now().isoformat()}")
    print(f"[PID] {os.getpid()}")
    print(f"[PYTHON] {sys.version}")
    
    # ============================================================
    # TEST 1: OKX API
    # ============================================================
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
    
    print(f"[CURL START] {datetime.now().isoformat()}")
    print(f"[CURL COMMAND] {' '.join(curl_cmd)}")
    
    try:
        start_time = time.time()
        
        # Run curl with 20-second hard timeout
        result = subprocess.run(
            curl_cmd,
            capture_output=True,
            text=True,
            timeout=20
        )
        
        elapsed = time.time() - start_time
        print(f"[CURL COMPLETE] {datetime.now().isoformat()} (elapsed: {elapsed:.2f}s)")
        
        # Combine stdout and stderr (curl outputs to stderr for verbose)
        combined = result.stdout + result.stderr
        
        print("\n--- CURL OUTPUT (filtered) ---")
        
        # Extract key diagnostic lines
        lines = combined.split('\n')
        for line in lines:
            line_lower = line.lower()
            if any(key in line_lower for key in [
                'resolving', 'connected', 'ssl', 'tls', 
                'http/', 'content-length', 'curl', 'error',
                'timed out', 'timeout', 'failed', 'unable',
                'dns', 'certificate', 'handshake'
            ]):
                print(f"[CURL] {line.strip()}")
        
        print("\n--- DIAGNOSTIC SUMMARY ---")
        
        # DNS
        if 'Resolving' in combined or 'resolving' in combined:
            print("[DNS] ✅ DNS resolution attempted")
            for line in lines:
                if 'Resolving' in line or 'resolving' in line:
                    print(f"  {line.strip()}")
        else:
            print("[DNS] ⚠️ DNS not detected in output")
        
        # TCP Connect
        if 'Connected to' in combined:
            print("[TCP CONNECT] ✅ Connection successful")
            for line in lines:
                if 'Connected to' in line:
                    print(f"  {line.strip()}")
        elif 'Failed to connect' in combined or 'Connection refused' in combined:
            print("[TCP CONNECT] ❌ Connection failed")
        else:
            print("[TCP CONNECT] ⚠️ Connection status not detected")
        
        # TLS/SSL
        if 'SSL' in combined or 'TLS' in combined:
            print("[TLS HANDSHAKE] ✅ TLS handshake attempted")
            for line in lines:
                if 'SSL' in line or 'TLS' in line:
                    print(f"  {line.strip()}")
        else:
            print("[TLS HANDSHAKE] ⚠️ TLS not detected in output")
        
        # HTTP Status
        http_found = False
        for line in lines:
            if 'HTTP/' in line:
                print(f"[HTTP STATUS] {line.strip()}")
                http_found = True
        if not http_found:
            print("[HTTP STATUS] ⚠️ HTTP status not detected")
        
        # Response Length
        content_len_found = False
        for line in lines:
            if 'content-length' in line.lower():
                print(f"[RESPONSE LENGTH] {line.strip()}")
                content_len_found = True
        if not content_len_found:
            print("[RESPONSE LENGTH] ⚠️ Content-Length not detected")
        
        print(f"[CURL EXIT CODE] {result.returncode}")
        
        # Interpret exit code
        if result.returncode == 0:
            print("[RESULT] ✅ OKX request SUCCEEDED")
        elif result.returncode == 28:
            print("[RESULT] ❌ CURL TIMEOUT (exit code 28)")
        elif result.returncode == 6:
            print("[RESULT] ❌ DNS RESOLUTION FAILED (exit code 6)")
        elif result.returncode == 7:
            print("[RESULT] ❌ CONNECTION FAILED (exit code 7)")
        elif result.returncode == 35:
            print("[RESULT] ❌ SSL/TLS ERROR (exit code 35)")
        else:
            print(f"[RESULT] ⚠️ Unknown exit code: {result.returncode}")
    
    except subprocess.TimeoutExpired:
        print(f"[CURL HARD TIMEOUT] Subprocess killed after 20 seconds")
        print("[RESULT] ❌ CURL HARD TIMEOUT - process terminated")
        
    except Exception as e:
        print(f"[CURL EXCEPTION] {type(e).__name__}: {e}")
        print("[RESULT] ❌ CURL EXCEPTION")
    
    # ============================================================
    # TEST 2: Google (Control)
    # ============================================================
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
    
    print(f"[CURL START] {datetime.now().isoformat()}")
    print(f"[CURL COMMAND] {' '.join(curl_cmd2)}")
    
    try:
        start_time = time.time()
        
        result2 = subprocess.run(
            curl_cmd2,
            capture_output=True,
            text=True,
            timeout=20
        )
        
        elapsed = time.time() - start_time
        print(f"[CURL COMPLETE] {datetime.now().isoformat()} (elapsed: {elapsed:.2f}s)")
        
        combined2 = result2.stdout + result2.stderr
        
        print("\n--- CURL OUTPUT (filtered) ---")
        lines2 = combined2.split('\n')
        for line in lines2:
            line_lower = line.lower()
            if any(key in line_lower for key in [
                'resolving', 'connected', 'ssl', 'tls', 
                'http/', 'content-length', 'curl', 'error'
            ]):
                print(f"[CURL] {line.strip()}")
        
        print("\n--- DIAGNOSTIC SUMMARY ---")
        
        if 'Connected to' in combined2:
            print("[TCP CONNECT] ✅ Connected to Google")
        
        http_found = False
        for line in lines2:
            if 'HTTP/' in line:
                print(f"[HTTP STATUS] {line.strip()}")
                http_found = True
        if not http_found:
            print("[HTTP STATUS] ⚠️ HTTP status not detected")
        
        print(f"[CURL EXIT CODE] {result2.returncode}")
        
        if result2.returncode == 0:
            print("[RESULT] ✅ Google request SUCCEEDED")
        elif result2.returncode == 28:
            print("[RESULT] ❌ Google TIMEOUT")
        else:
            print(f"[RESULT] ⚠️ Google exit code: {result2.returncode}")
    
    except subprocess.TimeoutExpired:
        print("[CURL HARD TIMEOUT] Google subprocess killed after 20 seconds")
    except Exception as e:
        print(f"[CURL EXCEPTION] {type(e).__name__}: {e}")
    
    print("\n" + "="*80)
    print(">>> CURL NETWORK DIAGNOSTIC COMPLETE <<<")
    print(f"[END] {datetime.now().isoformat()}")

if __name__ == "__main__":
    run_curl_diagnostic()
