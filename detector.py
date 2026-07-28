import numpy as np
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class RangeDetector:

    def __init__(self, max_range_width_pct: float = 3.0, min_age_candles: int = 15):
        self.max_range_width_pct = max_range_width_pct
        self.min_age_candles = min_age_candles

    def detect_range_15m(self, df_15m: pd.DataFrame) -> dict:
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

        age = 0
        for i in range(len(closes) - 1, -1, -1):
            if lows[i] >= floor * 0.997 and highs[i] <= ceiling * 1.003:
                age += 1
            else:
                break

        is_valid = (width_pct <= self.max_range_width_pct) and (age >= self.min_age_candles)

        live_price = closes[-1]
        dist_ceil_pct = max(0.0, ((ceiling - live_price) / live_price) * 100.0)
        dist_floor_pct = max(0.0, ((live_price - floor) / live_price) * 100.0)

        return {
            "is_valid": is_valid,
            "width_pct": round(width_pct, 2),
            "age": age,
            "ceiling": ceiling,
            "floor": floor,
            "live_price": live_price,
            "dist_ceil_pct": round(dist_ceil_pct, 2),
            "dist_floor_pct": round(dist_floor_pct, 2),
        }

    def evaluate_pressure(self, datasets: dict) -> dict:
        df_15m = datasets.get("15m")
        df_5m = datasets.get("5m")
        df_2m = datasets.get("2m")

        score_breakdown = {
            "Range Quality": 0,
            "Open Interest": 0,
            "CVD": 0,
            "ATR Compression": 0,
            "Funding": 0,
            "Volume": 0,
        }

        reasons = []

        if df_15m is None or df_5m is None:
            return {
                "pressure": "BUILDING",
                "score": 0,
                "bullish_prob": 50,
                "bearish_prob": 50,
                "reasons": ["Missing timeframe data"],
                "breakdown": score_breakdown,
            }

        range_meta = self.detect_range_15m(df_15m)
        if not range_meta["is_valid"]:
            return {
                "pressure": "BUILDING",
                "score": 0,
                "bullish_prob": 50,
                "bearish_prob": 50,
                "reasons": ["15M structure fails range constraints"],
                "breakdown": score_breakdown,
            }

        # 1. RANGE QUALITY (30% Max Weight)
        range_q_points = 15  # Base valid range points
        if range_meta["width_pct"] <= 1.5:
            range_q_points += 10
        elif range_meta["width_pct"] <= 2.5:
            range_q_points += 5

        if range_meta["age"] >= 30:
            range_q_points += 5

        score_breakdown["Range Quality"] = range_q_points
        reasons.append(f"Range Quality: +{range_q_points} (Width: {range_meta['width_pct']}%, Age: {range_meta['age']} bars)")

        # 2. ATR COMPRESSION (15% Max Weight)
        tr_15m = np.mean(df_15m["high"] - df_15m["low"])
        tr_5m = np.mean(df_5m["high"][-5:] - df_5m["low"][-5:])
        if tr_15m > 0:
            atr_ratio = tr_5m / tr_15m
            if atr_ratio < 0.50:
                score_breakdown["ATR Compression"] = 15
                reasons.append("ATR Compression: +15 (5M ATR highly compressed)")
            elif atr_ratio < 0.65:
                score_breakdown["ATR Compression"] = 10
                reasons.append("ATR Compression: +10 (5M ATR contracting)")

        # 3. VOLUME ACCELERATION (5% Max Weight)
        if df_2m is not None and len(df_2m) >= 5:
            vol_2m = df_2m["volume"].iloc[-1]
            vol_avg = np.mean(df_2m["volume"].iloc[-5:-1])
            if vol_avg > 0 and (vol_2m / vol_avg) >= 1.5:
                score_breakdown["Volume"] = 5
                reasons.append("Volume: +5 (2M trigger volume spike)")

        # Directional Probability Logic
        bullish_bias_points = 0
        bearish_bias_points = 0

        # Boundary Proximity Check
        dist_ceil = range_meta["dist_ceil_pct"]
        dist_floor = range_meta["dist_floor_pct"]

        if dist_ceil <= 0.35:
            bullish_bias_points += 2
            reasons.append("Price grinding against upper ceiling")
        elif dist_floor <= 0.35:
            bearish_bias_points += 2
            reasons.append("Price grinding against lower floor")

        # 4. OPEN INTEREST (25% Max Weight)
        oi_val = df_5m["open_interest"].iloc[-1] if "open_interest" in df_5m.columns else None
        if oi_val is not None and oi_val > 0:
            score_breakdown["Open Interest"] = 25
            reasons.append("Open Interest: +25 (Active OI confirmation)")
            bullish_bias_points += 1
        else:
            reasons.append("Open Interest: N/A (Using technical fallback)")

        # 5. FUNDING RATE (5% Max Weight)
        funding_val = df_5m["funding_rate"].iloc[-1] if "funding_rate" in df_5m.columns else None
        if funding_val is not None:
            score_breakdown["Funding"] = 5
            reasons.append("Funding: +5 (Predicted funding available)")
            if funding_val < 0:
                bullish_bias_points += 1  # Short squeeze bias
            elif funding_val > 0:
                bearish_bias_points += 1
        else:
            reasons.append("Funding: N/A")

        # 6. CVD CONFIRMATION (20% Max Weight)
        cvd_val = df_5m["cvd"].iloc[-1] if "cvd" in df_5m.columns else None
        if cvd_val is not None and cvd_val != 0:
            score_breakdown["CVD"] = 20
            reasons.append("CVD: +20 (Delta volume confirming setup)")
            if cvd_val > 0:
                bullish_bias_points += 2
            else:
                bearish_bias_points += 2
        else:
            reasons.append("CVD: N/A")

        # Total Dynamic Weighted Score (0 to 100)
        final_score = min(100, sum(score_breakdown.values()))

        # Probability Calculations
        total_bias = bullish_bias_points + bearish_bias_points
        if total_bias == 0:
            bullish_prob = 50
            bearish_prob = 50
        else:
            bullish_prob = int((bullish_bias_points / total_bias) * 100)
            bearish_prob = 100 - bullish_prob

        # Category Filtering Thresholds
        if final_score >= 80:
            pressure_label = "CRITICAL"
        elif final_score >= 65:
            pressure_label = "ABOUT TO BREAK"
        elif final_score >= 45:
            pressure_label = "LOADING"
        else:
            pressure_label = "BUILDING"

        return {
            "pressure": pressure_label,
            "score": final_score,
            "bullish_prob": bullish_prob,
            "bearish_prob": bearish_prob,
            "reasons": reasons,
            "breakdown": score_breakdown,
            "width": range_meta["width_pct"],
            "age": range_meta["age"],
            "ceiling": range_meta["ceiling"],
            "floor": range_meta["floor"],
            "live_price": range_meta["live_price"],
            "dist_ceil_pct": range_meta["dist_ceil_pct"],
            "dist_floor_pct": range_meta["dist_floor_pct"],
        }
