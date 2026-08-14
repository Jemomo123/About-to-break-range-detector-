import requests
import socket
import ssl
import time
import threading
from datetime import datetime

URL = "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=15m&limit=150"
HOST = "www.okx.com"
PORT = 443

print("=== DIAGNOSTIC PROBE WITH WATCHDOG ===\n")
print(f"[START] {datetime.now().isoformat()}")
print(f"[URL] {URL}")
print(f"[HOST] {HOST}")
print(f"[PORT] {PORT}")

# Watchdog thread
watchdog_running = True

def watchdog():
    """Print a heartbeat every 2 seconds while probe is running"""
    count = 0
    while watchdog_running:
        time.sleep(2)
        count += 1
        print(f"[WATCHDOG] Still running... {count * 2}s elapsed")
        if count >= 10:
            print("[WATCHDOG] 20 seconds elapsed - request may be hanging")

print("\n[WATCHDOG] Starting watchdog thread...")
watchdog_thread = threading.Thread(target=watchdog, daemon=True)
watchdog_thread.start()
time.sleep(0.1)

try:
    # ===== STAGE 1: DNS RESOLUTION =====
    print(f"\n[DNS START] {datetime.now().isoformat()}")
    dns_start = time.time()
    
    try:
        ip = socket.gethostbyname(HOST)
        dns_elapsed = time.time() - dns_start
        print(f"[DNS END] {datetime.now().isoformat()} ({dns_elapsed:.3f}s)")
        print(f"[DNS RESULT] {HOST} -> {ip}")
    except Exception as e:
        dns_elapsed = time.time() - dns_start
        print(f"[DNS END] {datetime.now().isoformat()} ({dns_elapsed:.3f}s)")
        print(f"[DNS ERROR] {type(e).__name__}: {e}")
        watchdog_running = False
        exit()

    # ===== STAGE 2: TCP CONNECTION =====
    print(f"\n[TCP START] {datetime.now().isoformat()}")
    tcp_start = time.time()
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((ip, PORT))
        tcp_elapsed = time.time() - tcp_start
        print(f"[TCP END] {datetime.now().isoformat()} ({tcp_elapsed:.3f}s)")
        print(f"[TCP RESULT] Connected to {ip}:{PORT}")
    except Exception as e:
        tcp_elapsed = time.time() - tcp_start
        print(f"[TCP END] {datetime.now().isoformat()} ({tcp_elapsed:.3f}s)")
        print(f"[TCP ERROR] {type(e).__name__}: {e}")
        watchdog_running = False
        sock.close()
        exit()

    # ===== STAGE 3: TLS/SSL HANDSHAKE =====
    print(f"\n[TLS START] {datetime.now().isoformat()}")
    tls_start = time.time()
    
    try:
        context = ssl.create_default_context()
        tls_sock = context.wrap_socket(sock, server_hostname=HOST)
        tls_elapsed = time.time() - tls_start
        print(f"[TLS END] {datetime.now().isoformat()} ({tls_elapsed:.3f}s)")
        print(f"[TLS RESULT] SSL handshake complete")
        print(f"[TLS VERSION] {tls_sock.version()}")
        print(f"[TLS CIPHER] {tls_sock.cipher()}")
    except Exception as e:
        tls_elapsed = time.time() - tls_start
        print(f"[TLS END] {datetime.now().isoformat()} ({tls_elapsed:.3f}s)")
        print(f"[TLS ERROR] {type(e).__name__}: {e}")
        watchdog_running = False
        sock.close()
        exit()

    # ===== STAGE 4: HTTP REQUEST =====
    print(f"\n[HTTP REQUEST START] {datetime.now().isoformat()}")
    http_start = time.time()
    
    # Build HTTP request manually
    request = f"GET {URL.split('https://www.okx.com')[1] if URL.startswith('https://') else '/'} HTTP/1.1\r\n"
    request += f"Host: {HOST}\r\n"
    request += "User-Agent: Mozilla/5.0\r\n"
    request += "Accept: application/json\r\n"
    request += "Connection: close\r\n"
    request += "\r\n"
    
    print(f"[HTTP REQUEST] Sending...")
    
    try:
        tls_sock.settimeout(10)
        tls_sock.send(request.encode())
        
        # Receive response
        print(f"[HTTP RESPONSE READING] {datetime.now().isoformat()}")
        response_data = b""
        while True:
            try:
                chunk = tls_sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
            except socket.timeout:
                print(f"[HTTP READ TIMEOUT] {datetime.now().isoformat()}")
                break
            except Exception as e:
                print(f"[HTTP READ ERROR] {type(e).__name__}: {e}")
                break
        
        http_elapsed = time.time() - http_start
        print(f"[HTTP REQUEST END] {datetime.now().isoformat()} ({http_elapsed:.3f}s)")
        
        # Parse response
        if response_data:
            response_str = response_data.decode('utf-8', errors='ignore')
            status_line = response_str.split('\r\n')[0] if response_str else ''
            print(f"[HTTP STATUS LINE] {status_line}")
            
            # Extract status code
            if 'HTTP/1.1' in status_line or 'HTTP/1.0' in status_line:
                parts = status_line.split()
                if len(parts) >= 2:
                    print(f"[HTTP STATUS] {parts[1]}")
            
            # Check for body
            if '\r\n\r\n' in response_str:
                body = response_str.split('\r\n\r\n', 1)[1]
                print(f"[HTTP RESPONSE LENGTH] {len(body)} bytes")
                if len(body) > 0:
                    print(f"[HTTP RESPONSE PREVIEW] {body[:200]}...")
        else:
            print("[HTTP RESPONSE] No data received")
            
    except socket.timeout as e:
        http_elapsed = time.time() - http_start
        print(f"[HTTP REQUEST END] {datetime.now().isoformat()} ({http_elapsed:.3f}s)")
        print(f"[HTTP TIMEOUT] Socket timeout: {e}")
    except Exception as e:
        http_elapsed = time.time() - http_start
        print(f"[HTTP REQUEST END] {datetime.now().isoformat()} ({http_elapsed:.3f}s)")
        print(f"[HTTP EXCEPTION] {type(e).__name__}: {e}")
    finally:
        tls_sock.close()
        sock.close()

except Exception as e:
    print(f"\n[UNEXPECTED ERROR] {type(e).__name__}: {e}")

finally:
    watchdog_running = False
    time.sleep(0.5)
    print(f"\n[DONE] {datetime.now().isoformat()}")
    print("=== DIAGNOSTIC PROBE COMPLETE ===")
