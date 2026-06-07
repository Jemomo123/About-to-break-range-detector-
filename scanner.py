import pandas as pd
from typing import Dict, List, Any
from detector import RangeDetector

class MarketScanner:
    """
    Coordinates multi-timeframe structural fusion and calculates 
    asymmetric watchlist prioritization index metrics.
    """
    def __init__(self, config: Dict[str, Any] = None):
        self.detector = RangeDetector(config)

    def scan_symbol(self, symbol: str, tf_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Processes cross-timeframe datasets without strict single-layer rejections."""
        # Check structural statuses across all targets simultaneously
        meta_15m = self.detector.detect_range(tf_data["15m"])
        meta_5m = self.detector.detect_range(tf_data["5m"])
        meta_3m = self.detector.detect_range(tf_data["3m"])

        # Calculate localized structural load indexes
        p_15m = self.detector.calculate_pressure(tf_data["15m"], meta_15m)
        p_5m = self.detector.calculate_pressure(tf_data["5m"], meta_5m)
        p_3m = self.detector.calculate_pressure(tf_data["3m"], meta_3m)

        # Process Multi-Timeframe Fusion Core logic
        final_status, confidence = self.detector.fuse_timeframes(p_15m, p_5m, p_3m)

        # Set default structures if anchor context returns null
        is_valid_range = meta_15m["status"] == "VALID" or meta_5m["status"] == "VALID"
        if not is_valid_range and final_status in ["IGNORE", "STABLE RANGE"]:
            return {"symbol": symbol, "status": "NO RANGE", "sort_score": -1.0}

        # Extract normalized analytics using available timeframe data
        anchor_meta = meta_15m if meta_15m["status"] == "VALID" else (meta_5m if meta_5m["status"] == "VALID" else meta_3m)
        width = anchor_meta["width"]
        age = anchor_meta["age"]
        atr_contract = anchor_meta["atr_contract"]

        # Calculate percentage open interest variance across 15M lookback frames
        oi_growth = 0.0
        df_15m = tf_data["15m"]
        if "open_interest" in df_15m.columns and len(df_15m) >= 5:
            oi_start = df_15m["open_interest"].iloc[-5]
            oi_end = df_15m["open_interest"].iloc[-1]
            if oi_start > 0:
                oi_growth = round(((oi_end - oi_start) / oi_start) * 100, 2)

        # Absolute Priority Multi-Factor Watchlist Sorting Equation
        status_weights = {
            "CRITICAL": 500, "ABOUT TO BREAK": 400, "LOADING": 300, 
            "BUILDING": 200, "STABLE RANGE": 100, "NO RANGE": 0
        }
        
        width_bonus = max(0.0, (3.0 - width) * 20.0)
        
        sort_score = (
            status_weights.get(final_status, 0)
            + (age * 2.0)
            + (oi_growth * 0.5)
            + (atr_contract * 0.5)
            + width_bonus
        )

        return {
            "symbol": symbol, "status": final_status, "confidence": confidence,
            "width": width, "age": age, "oi_growth": oi_growth, "atr_contract": atr_contract,
            "p_15m": p_15m, "p_5m": p_5m, "p_3m": p_3m, "sort_score": sort_score
        }

    @staticmethod
    def calculate_market_temperature(results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculates global structural velocity indexes across all processed symbols."""
        counts = {"NO RANGE": 0, "STABLE RANGE": 0, "BUILDING": 0, "LOADING": 0, "ABOUT TO BREAK": 0, "CRITICAL": 0}
        
        for r in results:
            status = r.get("status", "NO RANGE")
            if status in counts:
                counts[status] += 1
            else:
                counts["NO RANGE"] += 1

        # Categorize global thermal market metrics
        if counts["ABOUT TO BREAK"] + counts["CRITICAL"] >= 3:
            temp = "EXPLOSIVE"
        elif counts["LOADING"] >= 4:
            temp = "HOT"
        elif counts["BUILDING"] >= 5:
            temp = "WARM"
        else:
            temp = "COLD"

        return {"temperature": temp, "metrics": counts}
