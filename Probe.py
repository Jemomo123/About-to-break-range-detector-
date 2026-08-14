#!/usr/bin/env python3
"""
FIXED CONNECTIVITY PROBE - Guaranteed to produce a definitive result
Uses explicit try/except blocks and hard timeouts
"""

import requests
import time
import threading
import sys
from datetime import datetime

# Global flag to track probe completion
probe_complete = False
probe_result = None

def run_probe_with_timeout():
    """Run the probe with a hard timeout to prevent indefinite blocking"""
    global probe_complete, probe_result
    
    try:
        # ===== PROBE CONFIGURATION =====
        URL = "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=15m&limit=150"
        TIMEOUT_CONNECT = 5
        TIMEOUT_READ = 10
        
        print(f"[PROBE] Starting connectivity probe...")
        print(f"[PROBE] URL: {URL}")
        print(f"[PROBE] Timeout: ({TIMEOUT_CONNECT}, {TIMEOUT_READ})")
        print(f"[PROBE] PID: {threading.current_thread().ident}")
        
        # ===== EXECUTE REQUEST WITH EXPLICIT EXCEPTION HANDLING =====
        print(f"[PROBE BEFORE REQUEST] {datetime.now().isoformat()}")
        start_time = time.time()
        
        try:
            # Make the HTTP request
            response = requests.get(
                URL,
                timeout=(TIMEOUT_CONNECT, TIMEOUT_READ),
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            
            # ===== REQUEST SUCCEEDED =====
            elapsed = time.time() - start_time
            print(f"[PROBE AFTER REQUEST] {datetime.now().isoformat()}")
            print(f"[PROBE] HTTP_STATUS={response.status_code}")
            print(f"[PROBE] ELAPSED={elapsed:.2f}s")
            print(f"[PROBE] RESPONSE_LENGTH={len(response.text)} bytes")
            
            # Check if we got valid JSON
            try:
                data = response.json()
                if 'data' in data and data['data']:
                    print(f"[PROBE] CANDLE_COUNT={len(data['data'])}")
                    print(f"[PROBE] FIRST_CANDLE={data['data'][0]}")
                    probe_result = "SUCCESS"
                else:
                    print(f"[PROBE] INVALID_RESPONSE - No data field or empty")
                    probe_result = "INVALID_RESPONSE"
            except Exception as json_err:
                print(f"[PROBE] JSON_PARSE_ERROR: {type(json_err).__name__}: {json_err}")
                print(f"[PROBE] RESPONSE_PREVIEW: {response.text[:200]}")
                probe_result = "INVALID_RESPONSE"
                
        except requests.exceptions.Timeout as e:
            # ===== TIMEOUT =====
            elapsed = time.time() - start_time
            print(f"[PROBE AFTER REQUEST] {datetime.now().isoformat()}")
            print(f"[PROBE] ELAPSED={elapsed:.2f}s")
            print(f"[PROBE TIMEOUT] {type(e).__name__}: {e}")
            print(f"[PROBE] TIMEOUT_DETAIL: connect={TIMEOUT_CONNECT}s, read={TIMEOUT_READ}s")
            probe_result = "TIMEOUT"
            
        except requests.exceptions.ConnectionError as e:
            # ===== CONNECTION ERROR =====
            elapsed = time.time() - start_time
            print(f"[PROBE AFTER REQUEST] {datetime.now().isoformat()}")
            print(f"[PROBE] ELAPSED={elapsed:.2f}s")
            print(f"[PROBE CONNECTION ERROR] {type(e).__name__}: {e}")
            probe_result = "CONNECTION_ERROR"
            
        except requests.exceptions.RequestException as e:
            # ===== REQUESTS ERROR =====
            elapsed = time.time() - start_time
            print(f"[PROBE AFTER REQUEST] {datetime.now().isoformat()}")
            print(f"[PROBE] ELAPSED={elapsed:.2f}s")
            print(f"[PROBE REQUEST ERROR] {type(e).__name__}: {e}")
            probe_result = "HTTP_ERROR"
            
        except Exception as e:
            # ===== UNEXPECTED EXCEPTION =====
            elapsed = time.time() - start_time
            print(f"[PROBE AFTER REQUEST] {datetime.now().isoformat()}")
            print(f"[PROBE] ELAPSED={elapsed:.2f}s")
            print(f"[PROBE EXCEPTION] {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            probe_result = "EXCEPTION"
            
    except Exception as outer_e:
        print(f"[PROBE] FATAL_ERROR: {type(outer_e).__name__}: {outer_e}")
        probe_result = "FATAL"
    
    finally:
        probe_complete = True
        print(f"[PROBE RESULT] {probe_result}")
        print(f"[PROBE] Completed at {datetime.now().isoformat()}")

def run_diagnostic():
    """Run the probe with a hard timeout wrapper to prevent hanging"""
    print(">>> FIXED CONNECTIVITY PROBE DEPLOYED <<<")
    print(f"[PROBE] Starting at {datetime.now().isoformat()}")
    
    # Start probe in a separate thread with hard timeout
    probe_thread = threading.Thread(target=run_probe_with_timeout)
    probe_thread.daemon = True  # Don't block Gunicorn
    probe_thread.start()
    
    # Wait for completion with hard timeout
    max_wait = 25  # 25 seconds max (enough for 15s request + buffer)
    wait_interval = 0.5
    waited = 0
    
    print(f"[PROBE] Waiting up to {max_wait}s for completion...")
    
    while not probe_complete and waited < max_wait:
        time.sleep(wait_interval)
        waited += wait_interval
        if int(waited) % 5 == 0:  # Log every 5 seconds
            print(f"[PROBE] Still waiting... {waited:.1f}s elapsed")
    
    if not probe_complete:
        print(f"[PROBE] HARD TIMEOUT - Probe did not complete within {max_wait}s")
        print(f"[PROBE RESULT] HARD_TIMEOUT")
    else:
        print(f"[PROBE] Probe completed in {waited:.1f}s")
    
    print(f"[PROBE] Diagnostic complete at {datetime.now().isoformat()}")

if __name__ == "__main__":
    run_diagnostic()
