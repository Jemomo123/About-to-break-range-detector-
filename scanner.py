import logging
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class MarketScanner:
    def __init__(self):
        # High precision tuning parameters aligned with horizontal channels
        self.config = {
            "max_range_width_pct": 2.8,
            "min_candles": 15
        }

    def _analyze_single_timeframe(self, df: pd.DataFrame, timeframe_label: str) -> dict:
        """
        Helper method to extract pure horizontal channel geometries, age maturity, 
        and boundary compression metrics out of individual timeframe dataframes.
        """
        if df is None or len(df) < 15:
            return {"status": "NO RANGE", "width": 0.0, "age": 0, "pressure": "MID-RANGE"}
            
        highs = df["high"].tolist()
        lows = df["low"].tolist()
        closes = df["close"].tolist()
        live_price = closes[-1]
        
        # Lookback frame to calculate structural channel bounds
        lookback = min(24, len(closes))
        ceiling = max(highs[-lookback:])
        floor = min(lows[-lookback:])
        
        range_width = ((ceiling - floor) / floor) * 100
        
        # Calculate Range Age (candles tracking cleanly inside current limits)
        age = 0
        for i in range(len(closes) - 1, -1, -1):
            if lows[i] >= floor * 0.998 and highs[i] <= ceiling * 1.002:
                age += 1
            else:
                break
                
        # Bound Edge Pressure calculations
        dist_to_ceil = (ceiling - live_price) / ceiling * 100
        dist_to_floor = (live_price - floor) / floor * 100
        
        pressure = "MID-RANGE"
        if dist_to_ceil <= 0.35:
            pressure = "UPPER CEILING LOADING"
        elif dist_to_floor <= 0.35:
            pressure = "LOWER FLOOR LOADING"
            
        status = "NO RANGE"
        if range_width <= self.config["max_range_width_pct"]:
            status = "BUILDING"
            if age >= self.config["min_candles"]:
                status = "LOADING"
                
        return {
            "status": status,
            "width": round(range_width, 2),
            "age": age,
            "pressure": pressure
        }

    def scan_symbol(self, symbol: str, datasets: dict) -> dict:
        """
        Jeremiah Edge Architecture Law: Multi-Timeframe Core Fusion
        1H  = Structural Compression (Hard Filter Gateway)
        15M = Pressure Build-Up
        5M  = Trigger Acceleration
        """
        # 10. Explicit structural logging verifications
        if "1h" in datasets and datasets["1h"] is not None:
            logging.info(f"[{symbol}] 1H dataframe successfully loaded. Shape: {datasets['1h'].shape}")
        if "15m" in datasets and datasets["15m"] is not None:
            logging.info(f"[{symbol}] 15M dataframe successfully loaded. Shape: {datasets['15m'].shape}")
        if "5m" in datasets and datasets["5m"] is not None:
            logging.info(f"[{symbol}] 5M dataframe successfully loaded. Shape: {datasets['5m'].shape}")

        if not datasets or not all(k in datasets for k in ["1h", "15m", "5m"]):
            logging.warning(f"[{symbol}] Missing required dataframe layers. Scan rejected.")
            return None

        # Analyze separate structural timeline behaviors
        meta_1h = self._analyze_single_timeframe(datasets["1h"], "1H")
        meta_15m = self._analyze_single_timeframe(datasets["15m"], "15M")
        meta_5m = self._analyze_single_timeframe(datasets["5m"], "5M")

        # 4. Strict Structural Filter Rule: Reject symbol instantly if 1H macro has NO RANGE
        if meta_1h["status"] == "NO RANGE":
            logging.info(f"[{symbol}] Structural filter applied: 1H has NO RANGE. Asset skipped.")
            return None

        # Extract pressure tracking strings for fusion logic evaluations
        p_1h = meta_1h["status"]      # Building or Loading macro structures
        p_15m = meta_15m["status"]    # Intermediate trend tightening status
        p_5m = meta_5m["status"]      # Fine trigger loop micro contraction

        # 5. Core Multi-Timeframe Fusion Logic Engine Matrices
        final_status = "BUILDING"
        sort_score = 10.0 + meta_1h["age"]

        if p_1h == "LOADING":
            final_status = "LOADING"
            sort_score = 50.0 + meta_1h["age"] + meta_15m["age"]
            
            # Check if intermediate and micro-coils match setup parameters
            if p_15m in ["BUILDING", "LOADING"] and p_5m in ["BUILDING", "LOADING"]:
                final_status = "ABOUT TO BREAK"
                sort_score = 100.0 + meta_15m["age"] + meta_5m["age"]
                
                # Maximize priority if live micro candles grind bounds directly
                if meta_5m["pressure"] in ["UPPER CEILING LOADING", "LOWER FLOOR LOADING"]:
                    final_status = "CRITICAL"
                    sort_score = 200.0 + meta_5m["age"]

        # Formulate metrics payload keeping dashboard items fully aligned
        return {
            "symbol": symbol,
            "status": final_status,
            "sort_score": sort_score,
            "confidence": "HIGH" if final_status in ["ABOUT TO BREAK", "CRITICAL"] else "MEDIUM",
            "width": meta_1h["width"],
            "age": meta_1h["age"],
            "atr_contract": meta_15m["age"] * 2,  # Approximation metric proxy
            "oi_growth": 0.0,
            "p_1h": p_1h,
            "p_15m": p_15m,
            "p_5m": p_5m,
            "interpretation": f"1H structure is {p_1h} ({meta_1h['width']}% width). 15M building layer reports {p_15m}. 5M trigger layer exhibits {meta_5m['pressure']} edge acceleration."
        }

    def calculate_market_temperature(self, scan_results: list) -> dict:
        counts = {"NO RANGE": 0, "STABLE RANGE": 0, "BUILDING": 0, "LOADING": 0, "ABOUT TO BREAK": 0, "CRITICAL": 0}
        for item in scan_results:
            st = item.get("status", "NO RANGE")
            if st in counts:
                counts[st] += 1
                
        # Determine global matrix temperature status
        active_heavy = counts["ABOUT TO BREAK"] + counts["CRITICAL"]
        if active_heavy >= 3:
            temp = "BOILING"
        elif active_heavy >= 1 or counts["LOADING"] >= 4:
            temp = "WARM"
        else:
            temp = "COLD"
            
        return {"temperature": temp, "metrics": counts}
