import numpy as np
import pandas as pd

class RangeDetector:

    def __init__(self, max_range_width_pct: float = 3.0, min_age_candles: int = 15):
        self.max_range_width_pct = max_range_width_pct
        self.min_age_candles = min_age_candles

    def detect_range_15m(self, df_15m: pd.DataFrame) -> dict:
        """Requirement 2: Primary range detection anchored on the 15M timeframe."""
        if df_15m is None or len(df_15m) < self.min_age_candles:
            return {"is_valid": False, "reason": "Insufficient 15M candles"}

        highs = df_15m["high"].tolist()
        lows = df_15m["low"].tolist()
        closes = df_15m["close"].tolist()

        lookback = min(30, len(closes))
        ceiling = max(highs[-lookback:])
        floor = min(lows[-lookback:])

        if floor <= 0:
            return {"is_valid": False, "reason": "Invalid price boundary"}

        width_pct = ((ceiling - floor) / floor) * 100.0

        # Range Age (candles contained within boundary limits)
        age = 0
        for i in range(len(closes) - 1, -1, -1):
            if lows[i] >= floor * 0.997 and highs[i] <= ceiling * 1.003:
                age += 1
            else:
                break

        is_valid = (width_pct <= self.max_range_width_pct) and (age >= self.min_age_candles)

        return {
            "is_valid": is_valid,
            "width_pct": round(width_pct, 2),
            "age": age,
            "ceiling": ceiling,
            "floor": floor,
            "live_price": closes[-1],
        }

    def evaluate_pressure(self, datasets: dict) -> dict:
        """Requirement 6 & 7: Rich output object based on rules 1-6."""
        df_15m = datasets.get("15m")
        df_5m = datasets.get("5m")
        df_2m = datasets.get("2m")

        reasons = []
        score = 0
        direction = "Neutral"

        if df_15m is None or df_5m is None:
            return {
                "pressure": "BUILDING",
                "score": 0,
                "direction": "Neutral",
                "reasons": ["Missing required timeframe data"],
            }

        range_meta = self.detect_range_15m(df_15m)
        if not range_meta["is_valid"]:
            return {
                "pressure": "BUILDING",
                "score": 0,
                "direction": "Neutral",
                "reasons": ["15M structure does not meet range constraints"],
            }

        # Base Range Score
        score += 20
        reasons.append(f"Mature 15M range (Width: {range_meta['width_pct']}%, Age: {range_meta['age']} bars)")

        # 1. ATR Contraction Check
        tr_15m = np.mean(df_15m["high"] - df_15m["low"])
        tr_5m = np.mean(df_5m["high"][-5:] - df_5m["low"][-5:])
        if tr_15m > 0 and (tr_5m / tr_15m) < 0.65:
            score += 20
            reasons.append("ATR volatility contracting on 5M")

        # 2. Boundary Pressure (5M Grinding Ceiling/Floor)
        live_price = range_meta["live_price"]
        ceiling = range_meta["ceiling"]
        floor = range_meta["floor"]

        dist_ceil = (ceiling - live_price) / ceiling * 100
        dist_floor = (live_price - floor) / floor * 100

        if dist_ceil <= 0.35:
            score += 15
            direction = "Bullish"
            reasons.append("5M price pressing upper ceiling boundary")
        elif dist_floor <= 0.35:
            score += 15
            direction = "Bearish"
            reasons.append("5M price pressing lower floor boundary")

        # 3. 2M Entry Trigger Acceleration
        if df_2m is not None and len(df_2m) >= 3:
            vol_2m = df_2m["volume"].iloc[-1]
            vol_avg = np.mean(df_2m["volume"].iloc[-5:-1]) if len(df_2m) >= 5 else vol_2m
            if vol_avg > 0 and (vol_2m / vol_avg) >= 1.5:
                score += 15
                reasons.append("2M volume acceleration detected")

        # 4. Open Interest Check
        if "open_interest" in df_5m.columns and df_5m["open_interest"].iloc[-1] > 0:
            oi_val = df_5m["open_interest"].iloc[-1]
            score += 10
            reasons.append(f"OI active: {oi_val:,.0f}")

        # 5. Funding Rate Check
        if "funding_rate" in df_5m.columns and df_5m["funding_rate"].iloc[-1] != 0:
            fr = df_5m["funding_rate"].iloc[-1]
            if abs(fr) < 0.0002:
                score += 10
                reasons.append(f"Funding rate neutral ({fr:.4f}%)")

        # 6. Rule 6: CVD Confirmation from Coinalyze
        if "cvd" in df_5m.columns and df_5m["cvd"].iloc[-1] != 0:
            cvd_val = df_5m["cvd"].iloc[-1]
            if direction == "Bullish" and cvd_val > 0:
                score += 10
                reasons.append("CVD confirming bullish delta pressure")
            elif direction == "Bearish" and cvd_val < 0:
                score += 10
                reasons.append("CVD confirming bearish delta pressure")

        # Determine Final Radar Category Status
        pressure_label = "BUILDING"
        if score >= 85:
            pressure_label = "CRITICAL"
        elif score >= 65:
            pressure_label = "ABOUT TO BREAK"
        elif score >= 40:
            pressure_label = "LOADING"

        return {
            "pressure": pressure_label,
            "score": score,
            "direction": direction,
            "reasons": reasons,
            "width": range_meta["width_pct"],
            "age": range_meta["age"],
        }
