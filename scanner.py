import time
import requests
from detector import detect_range, analyze_buyer_seller_battle, calculate_boundary_readiness

OKX_BASE_URL = "https://www.okx.com/api/v5/market/candles"
MEXC_BASE_URL = "https://contract.mexc.com/api/v1/contract/kline"

OKX_TF_MAP = {"3M": "3m", "5M": "5m", "15M": "15m", "1H": "1H", "4H": "4H"}
MEXC_TF_MAP = {"3M": "Min3", "5M": "Min5", "15M": "Min15", "1H": "Min60", "4H": "Hour4"}

def fetch_okx_klines(symbol: str, timeframe: str, limit: int = 150):
    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    inst_id = f"{clean_sym[:-4]}-USDT-SWAP" if clean_sym.endswith("USDT") else f"{clean_sym}-USDT-SWAP"
    bar = OKX_TF_MAP.get(timeframe.upper(), "5m")
    params = {"instId": inst_id, "bar": bar, "limit": str(limit)}

    try:
        res = requests.get(OKX_BASE_URL, params=params, timeout=6)
        res.raise_for_status()
        data = res.json()
        if data.get("code") != "0" or "data" not in data or not data["data"]:
            spot_inst_id = f"{clean_sym[:-4]}-USDT" if clean_sym.endswith("USDT") else clean_sym
            params["instId"] = spot_inst_id
            res = requests.get(OKX_BASE_URL, params=params, timeout=6)
            data = res.json()

        if data.get("code") != "0" or "data" not in data or not data["data"]:
            return [], None

        candles = []
        for item in reversed(data["data"]):
            candles.append({
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5])
            })
        return candles, "OKX"
    except Exception:
        return [], None


def fetch_mexc_klines(symbol: str, timeframe: str, limit: int = 150):
    clean_sym = symbol.replace("_", "").replace("-", "").upper()
    formatted_symbol = f"{clean_sym[:-4]}_USDT" if clean_sym.endswith("USDT") else clean_sym
    interval = MEXC_TF_MAP.get(timeframe.upper(), "Min5")
    end_time = int(time.time())
    
    minutes = 5
    if "3" in interval: minutes = 3
    elif "15" in interval: minutes = 15
    elif "60" in interval: minutes = 60
    elif "Hour4" in interval: minutes = 240
    
    start_time = end_time - (minutes * 60 * limit)
    url = f"{MEXC_BASE_URL}/{formatted_symbol}"
    params = {"interval": interval, "start": start_time, "end": end_time}

    try:
        res = requests.get(url, params=params, timeout=6)
        res.raise_for_status()
        data = res.json()
        if not data.get("success", False) or "data" not in data:
            return [], None

        kline_data = data["data"]
        opens, highs, lows, closes, volumes = (
            kline_data.get("open", []), kline_data.get("high", []),
            kline_data.get("low", []), kline_data.get("close", []), kline_data.get("vol", [])
        )
        length = min(len(opens), len(highs), len(lows), len(closes), len(volumes))
        candles = []
        for i in range(length):
            candles.append({
                "open": float(opens[i]), "high": float(highs[i]),
                "low": float(lows[i]), "close": float(closes[i]), "volume": float(volumes[i])
            })
        return candles, "MEXC"
    except Exception:
        return [], None


def fetch_klines(symbol: str, timeframe: str, limit: int = 150):
    candles, source = fetch_okx_klines(symbol, timeframe, limit)
    if candles and len(candles) >= 20:
        return candles, source

    candles, source = fetch_mexc_klines(symbol, timeframe, limit)
    if candles and len(candles) >= 20:
        return candles, source

    return [], None


def run_scanner_pipeline(watchlist, target_tf=None):
    timeframes_to_scan = ["5M", "15M", "1H"] if not target_tf or target_tf == "ALL" else [target_tf]

    results = []
    diagnostics = {
        "symbols_downloaded": 0,
        "symbols_scanned": 0,
        "rejections": {},
        "matches": 0
    }

    print("\n==================================================", flush=True)
    print(f"[ABOUT TO BREAK RANGE DETECTOR] Scanning {len(watchlist)} symbols: {timeframes_to_scan}", flush=True)
    print("==================================================", flush=True)

    for symbol in watchlist:
        for tf in timeframes_to_scan:
            diagnostics["symbols_scanned"] += 1
            candles, source = fetch_klines(symbol, tf)

            if not candles or len(candles) < 20:
                reason = "FETCH_FAILED_OR_INSUFFICIENT_BARS"
                diagnostics["rejections"][reason] = diagnostics["rejections"].get(reason, 0) + 1
                continue

            diagnostics["symbols_downloaded"] += 1

            try:
                range_result = detect_range(candles, tf)
            except Exception as e:
                reason = "DETECTOR_EXCEPTION"
                diagnostics["rejections"][reason] = diagnostics["rejections"].get(reason, 0) + 1
                continue

            if not range_result or not range_result.get("is_valid_range", False):
                reason = range_result.get("rejection_reason", "NO_RANGE_DETECTED")
                diagnostics["rejections"][reason] = diagnostics["rejections"].get(reason, 0) + 1
                continue

            curr_close = range_result.get("curr_close", candles[-1]["close"])
            support = float(range_result.get("support"))
            resistance = float(range_result.get("resistance"))

            if support >= resistance:
                reason = "INVALID_SUPPORT_RESISTANCE"
                diagnostics["rejections"][reason] = diagnostics["rejections"].get(reason, 0) + 1
                continue

            readiness_score, readiness_label = calculate_boundary_readiness(curr_close, support, resistance)

            # Skip or deprioritize setups under 20%
            if readiness_score < 20:
                reason = "READINESS_BELOW_THRESHOLD"
                diagnostics["rejections"][reason] = diagnostics["rejections"].get(reason, 0) + 1
                continue

            # Calculate distance percentages
            dist_to_res_pct = round(((resistance - curr_close) / curr_close) * 100.0, 2)
            dist_to_supp_pct = round(((curr_close - support) / curr_close) * 100.0, 2)

            volumes = [c["volume"] for c in candles]
            closes = [c["close"] for c in candles]
            battle = analyze_buyer_seller_battle(range_result, volumes, closes)

            buyer_p = battle.get("buyer_power", 50)
            seller_p = battle.get("seller_power", 50)

            # Determine Break Direction
            if buyer_p >= 58:
                break_direction = "BULLISH"
                break_symbol = "▲"
            elif seller_p >= 58:
                break_direction = "BEARISH"
                break_symbol = "▼"
            else:
                break_direction = "NEUTRAL"
                break_symbol = "↔"

            # Calculate Confidence Score
            if readiness_score >= 85 and abs(buyer_p - seller_p) >= 20:
                confidence = "HIGH"
            elif readiness_score >= 60:
                confidence = "MEDIUM"
            else:
                confidence = "LOW"

            # Dynamic badge setup
            badge_status = None
            if readiness_score >= 95:
                badge_status = "IMMENSE"
            elif readiness_score >= 80:
                badge_status = "NEAR"

            # Explanation generation
            struct_type = range_result.get("structure_type", "HORIZONTAL")
            if struct_type == "ASCENDING TRIANGLE":
                explanation = "Higher lows pressing against horizontal resistance. Dynamic bullish pressure building for an upward breakout."
            elif struct_type == "DESCENDING TRIANGLE":
                explanation = "Lower highs pressing against horizontal support. Heavy sell pressure threatening a breakdown."
            else:
                explanation = "Tight sideways consolidation between key support and resistance boundaries. Volatility compression detected."

            pattern_age = len(candles)
            last_candle_change = round(((candles[-1]["close"] - candles[-2]["close"]) / candles[-2]["close"]) * 100, 2)
            vol_avg = sum(volumes[-5:]) / 5.0
            vol_trend = "EXPANDING" if volumes[-1] > vol_avg else "CONTRACTING"
            risk_reward = round((resistance - curr_close) / max((curr_close - support), 1e-6), 2)

            match = {
                "symbol": symbol,
                "timeframe": tf,
                "exchange": source or "OKX",
                "structure_type": struct_type,
                "curr_close": curr_close,
                "support": support,
                "resistance": resistance,
                "dist_res_pct": dist_to_res_pct,
                "dist_supp_pct": dist_to_supp_pct,
                "readiness_score": readiness_score,
                "readiness_display": readiness_label,
                "badge_status": badge_status,
                "buyer_power": buyer_p,
                "seller_power": seller_p,
                "break_direction": break_direction,
                "break_symbol": break_symbol,
                "confidence": confidence,
                "explanation": explanation,
                "pattern_age": pattern_age,
                "last_change": last_candle_change,
                "vol_trend": vol_trend,
                "risk_reward": risk_reward
            }
            results.append(match)

    # SORT BY READINESS SCORE (HIGHEST FIRST)
    results.sort(key=lambda x: x["readiness_score"], reverse=True)

    # Assign Rank Numbers #1, #2, #3...
    for index, item in enumerate(results, 1):
        item["rank"] = f"#{index}"

    diagnostics["matches"] = len(results)
    print(f"[ABOUT TO BREAK RANGE DETECTOR] Scanner complete. Found {len(results)} ranked matches.", flush=True)
    return results, diagnostics
