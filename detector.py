import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple

class RangeDetector:
    """
    Project: About To Break Range Detector
    Handles structural range condition validation and asset stress categorization.
    """
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {
            "max_width_pct": 3.0,        # Maximum high-to-low width boundary limit
            "min_age_candles": 12,       # Minimum age required to form a valid structural range
            "atr_period": 14,            # Historical volatility lookback
            "funding_threshold": 0.0005, # 0.05% absolute funding crowdedness marker
            "oi_lookback": 5,            # Lookback frame for calculating open interest delta
        }

    def detect_range(self, df: pd.DataFrame) -> Dict[str, Any]:
        """STEP 1: DETECT RANGE FIRST"""
        if len(df) < self.config["min_age_candles"]:
            return {"status": "NO RANGE", "width": 0.0, "age": 0, "atr_contract": 0.0}

        # Determine structural coordinates using current window length
        window = df.tail(self.config["min_age_candles"])
        highest_high = window["high"].max()
        lowest_low = window["low"].min()

        range_width_pct = ((highest_high - lowest_low) / lowest_low) * 100

        if range_width_pct > self.config["max_width_pct"]:
            return {"status": "NO RANGE", "width": range_width_pct, "age": 0, "atr_contract": 0.0}

        # Compute volatility metrics and contraction percentages
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=self.config["atr_period"]).mean()

        current_atr = atr.iloc[-1]
        historical_atr_avg = atr.tail(self.config["min_age_candles"] * 2).mean()
        
        atr_contraction = (
            ((historical_atr_avg - current_atr) / historical_atr_avg) * 100
            if historical_atr_avg > 0 else 0.0
        )

        # Backtest duration boundaries 
        age = 0
        for i in range(1, len(df) + 1):
            idx = -i
            if (df["high"].iloc[idx] <= highest_high) and (df["low"].iloc[idx] >= lowest_low):
                age += 1
            else:
                break

        if age < self.config["min_age_candles"]:
            return {"status": "NO RANGE", "width": range_width_pct, "age": age, "atr_contract": atr_contraction}

        return {
            "status": "VALID",
            "width": round(range_width_pct, 2),
            "age": age,
            "atr_contract": round(atr_contraction, 2),
            "current_atr": current_atr,
            "historical_atr": historical_atr_avg,
        }

    def calculate_pressure(self, df: pd.DataFrame, range_meta: Dict[str, Any]) -> str:
        """STEP 2: CALCULATE PRESSURE SCORE"""
        if range_meta["status"] == "NO RANGE":
            return "NORMAL"

        score = 0

        # Rule 1: Volatility Contraction
        if range_meta["current_atr"] < range_meta["historical_atr"]:
            score += 1

        # Rule 2: Volume Exhaustion
        recent_vol = df["volume"].tail(5).mean()
        hist_vol_avg = df["volume"].tail(self.config["min_age_candles"] * 2).mean()
        if recent_vol < hist_vol_avg:
            score += 1

        # Rule 3: Advanced Open Interest Scoring
        oi_growth_pct = 0.0
        if "open_interest" in df.columns and len(df) >= self.config["oi_lookback"]:
            oi_start = df["open_interest"].iloc[-self.config["oi_lookback"]]
            oi_end = df["open_interest"].iloc[-1]
            if oi_start > 0:
                oi_growth_pct = ((oi_end - oi_start) / oi_start) * 100
            
            if oi_growth_pct > 7.0:
                score += 2
            elif oi_growth_pct > 3.0:
                score += 1

        # Rule 4: Funding Crowd Positioning
        if "funding_rate" in df.columns:
            abs_funding = abs(df["funding_rate"].iloc[-1])
            if abs_funding >= self.config["funding_threshold"]:
                score += 1

        # Rule 5: Range Age Bonus Integration
        age = range_meta["age"]
        if age > 40:
            score += 2
        elif age > 20:
            score += 1

        # Map complete aggregated score framework
        classification = {
            0: "NORMAL", 1: "NORMAL", 2: "BUILDING", 
            3: "LOADING", 4: "HIGH PRESSURE", 5: "HIGH PRESSURE", 6: "HIGH PRESSURE"
        }
        return classification.get(score, "NORMAL")

    @staticmethod
    def fuse_timeframes(p_15m: str, p_5m: str, p_3m: str) -> Tuple[str, str]:
        """STEP 3: MULTI-TIMEFRAME FUSION"""
        states = {"NORMAL": 0, "BUILDING": 1, "LOADING": 2, "HIGH PRESSURE": 3}
        s_15, s_5, s_3 = states[p_15m], states[p_5m], states[p_3m]

        # Critical triggers
        if s_15 >= 2 and s_5 == 3 and s_3 >= 2: return "CRITICAL", "HIGH"
        if s_15 == 3 and s_5 == 3 and s_3 == 1: return "CRITICAL", "HIGH"

        # About to Break triggers
        if s_15 == 2 and s_5 == 2 and s_3 == 1: return "ABOUT TO BREAK", "HIGH"
        if s_15 >= 2 and s_5 >= 2 and s_3 >= 1: return "ABOUT TO BREAK", "MEDIUM"

        # Loading / Building matrices
        if s_15 == 2 or (s_5 == 2 and s_3 == 2): return "LOADING", "MEDIUM"
        if s_15 == 1 or s_5 == 1 or s_5 == 2 or s_3 == 2: return "BUILDING", "LOW"
        if s_15 == 0 and s_5 == 0 and s_3 == 0: return "STABLE RANGE", "LOW"
        return "IGNORE", "LOW"
