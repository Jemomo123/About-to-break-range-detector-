import pandas as pd
from typing import Dict, List, Any
from detector import RangeDetector

class MarketScanner:
    def __init__(self, config: Dict[str, Any] = None):
        self.detector = RangeDetector(config)

    def scan_symbol(self, symbol: str, tf_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        meta_15m = self.detector.detect_range(tf_data["15m"])
        meta_5m = self.detector.detect_range(tf_data["5m"])

        p_15m = self.detector.calculate_pressure(tf_data["15m"], meta_15m)
        p_5m = self.detector.calculate_pressure(tf_data["5m"], meta_5m)

        # Clean Dual-Timeframe Fusion Logic Mapping
        if p_15m == "LOADING" and p_5m in ["HIGH PRESSURE", "ACCUMULATION"]:
            final_status, confidence = "ABOUT TO BREAK", "HIGH"
        elif p_15m == "LOADING" or p_5m == "HIGH PRESSURE":
            final_status, confidence = "LOADING", "MEDIUM"
        elif p_15m == "STABLE RANGE" and p_5m == "STABLE RANGE":
            final_status, confidence = "STABLE RANGE", "HIGH"
        elif p_15m == "BUILDING" or p_5m == "BUILDING":
            final_status, confidence = "BUILDING", "MEDIUM"
        else:
            final_status, confidence = "NO RANGE", "LOW"

        is_valid_range = meta_15m["status"] == "VALID" or meta_5m["status"] == "VALID"
        if not is_valid_range or final_status in ["IGNORE", "NO RANGE"]:
            return {
                "symbol": symbol, "status": "NO RANGE", "confidence": "LOW",
                "width": 0.0, "age": 0, "oi_growth": 0.0, "atr_contract": 0.0,
                "p_15m": p_15m, "p_5m": p_5m, "sort_score": 0.0
            }

        anchor_meta = meta_15m if meta_15m["status"] == "VALID" else meta_5m
        width = anchor_meta["width"]
        age = anchor_meta["age"]
        atr_contract = anchor_meta["atr_contract"]

        oi_growth = 0.0
        df_15m = tf_data["15m"]
        if "open_interest" in df_15m.columns and len(df_15m) >= 5:
            oi_start = df_15m["open_interest"].iloc[-5]
            oi_end = df_15m["open_interest"].iloc[-1]
            if oi_start > 0:
                oi_growth = round(((oi_end - oi_start) / oi_start) * 100, 2)

        status_weights = {
            "CRITICAL": 500, "ABOUT TO BREAK": 400, "LOADING": 300, 
            "BUILDING": 200, "STABLE RANGE": 100, "NO RANGE": 0
        }
        
        width_bonus = max(0.0, (3.0 - width) * 20.0)
        sort_score = (status_weights.get(final_status, 0) + (age * 2.0) + (oi_growth * 0.5) + (atr_contract * 0.5) + width_bonus)

        return {
            "symbol": symbol, "status": final_status, "confidence": confidence,
            "width": width, "age": age, "oi_growth": oi_growth, "atr_contract": atr_contract,
            "p_15m": p_15m, "p_5m": p_5m, "sort_score": sort_score
        }

    @staticmethod
    def calculate_market_temperature(results: List[Dict[str, Any]]) -> Dict[str, Any]:
        counts = {"NO RANGE": 0, "STABLE RANGE": 0, "BUILDING": 0, "LOADING": 0, "ABOUT TO BREAK": 0, "CRITICAL": 0}
        for r in results:
            status = r.get("status", "NO RANGE")
            if status in counts:
                counts[status] += 1
            else:
                counts["NO RANGE"] += 1

        if counts["ABOUT TO BREAK"] + counts["CRITICAL"] >= 3:
            temp = "EXPLOSIVE"
        elif counts["LOADING"] >= 4:
            temp = "HOT"
        elif counts["BUILDING"] >= 5:
            temp = "WARM"
        else:
            temp = "COLD"

        return {"temperature": temp, "metrics": counts}
