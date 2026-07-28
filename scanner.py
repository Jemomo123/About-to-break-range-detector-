import pandas as pd

class MarketScanner:
    def __init__(self):
        pass

    def is_15m_range_valid(self, df_15m):
        """Strict 15M Range Gate Check - only tracks compressed ranges."""
        if df_15m is None or len(df_15m) < 15:
            return False
        
        high = float(df_15m["high"].max())
        low = float(df_15m["low"].min())
        close = float(df_15m["close"].iloc[-1])
        width_pct = ((high - low) / close) * 100
        
        return width_pct <= 3.5  

    def determine_market_control(self, dist_ceil_pct, dist_floor_pct, cvd, oi, funding_rate, df_15m):
        """
        Market Control Engine: Combines boundary proximity, CVD direction, 
        OI expansion/contraction, Funding Rate, and Volume acceleration to detect 
        who is winning the battle before breakout.
        """
        # 1. Clean and convert inputs
        try: cvd_val = float(cvd) if cvd is not None else 0.0
        except (ValueError, TypeError): cvd_val = 0.0

        try: funding_val = float(funding_rate) if funding_rate is not None else 0.0
        except (ValueError, TypeError): funding_val = 0.0

        try: oi_val = float(oi) if oi is not None else 0.0
        except (ValueError, TypeError): oi_val = 0.0

        # 2. Extract Volume Acceleration (Current candle vol vs 5-candle average vol)
        vol_accel = False
        if df_15m is not None and "volume" in df_15m and len(df_15m) >= 5:
            recent_avg_vol = df_15m["volume"].iloc[-6:-1].mean()
            last_vol = df_15m["volume"].iloc[-1]
            if recent_avg_vol > 0 and (last_vol / recent_avg_vol) >= 1.25:
                vol_accel = True

        # 3. Positional & Metric Flags
        near_ceiling = dist_ceil_pct <= 0.8
        near_floor = dist_floor_pct <= 0.8
        cvd_buying = cvd_val > 0
        cvd_selling = cvd_val < 0
        funding_positive = funding_val > 0.005
        funding_negative = funding_val < -0.005

        agreed = []
        conflicted = []

        # Default State
        state = "✅ BALANCED BATTLE"
        confidence = 50
        explanation = "Buyers and sellers are matched with no clear structural absorption or delta dominance."

        # -------------------------------------------------------------
        # ENGINE EVALUATION LOGIC
        # -------------------------------------------------------------

        # CASE A: BUYER ABSORPTION (Sellers hitting market, but Price Holds Near Ceiling / Doesn't drop)
        if near_ceiling and cvd_selling:
            state = "✅ BUYER ABSORPTION"
            explanation = "Price is holding near resistance despite aggressive market selling. Limit buy wall absorbing supply."
            confidence = 85 if vol_accel else 75
            agreed.extend(["Ceiling Proximity", "Negative CVD (Limit Absorbed)"])
            if vol_accel: agreed.append("Volume Acceleration")

        # CASE B: SELLER ABSORPTION (Buyers hitting market, but Price Holds Near Floor / Doesn't push up)
        elif near_floor and cvd_buying:
            state = "✅ SELLER ABSORPTION"
            explanation = "Price is holding near support despite aggressive market buying. Limit sell wall absorbing demand."
            confidence = 85 if vol_accel else 75
            agreed.extend(["Floor Proximity", "Positive CVD (Limit Absorbed)"])
            if vol_accel: agreed.append("Volume Acceleration")

        # CASE C: BUYERS IN CONTROL (Strong CVD + Near Resistance + Volume Expansion)
        elif near_ceiling and cvd_buying:
            state = "✅ BUYERS IN CONTROL"
            explanation = "Aggressive taker buying driving price to upper boundary with expanding momentum."
            confidence = 90 if vol_accel else 80
            agreed.extend(["Ceiling Proximity", "Positive CVD"])
            if vol_accel: agreed.append("Volume Acceleration")
            if funding_positive: agreed.append("Positive Funding Alignment")

        # CASE D: SELLERS IN CONTROL (Strong Negative CVD + Near Support + Volume Expansion)
        elif near_floor and cvd_selling:
            state = "✅ SELLERS IN CONTROL"
            explanation = "Aggressive taker selling pressing price directly into support."
            confidence = 90 if vol_accel else 80
            agreed.extend(["Floor Proximity", "Negative CVD"])
            if vol_accel: agreed.append("Volume Acceleration")
            if funding_negative: agreed.append("Negative Funding Alignment")

        # CASE E: SHORT SQUEEZE RISK (Heavy Negative Funding / Short Overcrowding near Upper Boundary)
        elif funding_negative and (near_ceiling or cvd_buying):
            state = "✅ SHORT SQUEEZE RISK"
            explanation = "Overcrowded short positioning with price pressing resistance or CVD turning positive."
            confidence = 80
            agreed.extend(["Negative Funding (Short Heavy)", "Upward Price/CVD Pressure"])

        # CASE F: LONG SQUEEZE RISK (Heavy Positive Funding / Long Overcrowding near Lower Boundary)
        elif funding_positive and (near_floor or cvd_selling):
            state = "✅ LONG SQUEEZE RISK"
            explanation = "Overcrowded long positioning with price pressing support or CVD turning negative."
            confidence = 80
            agreed.extend(["Positive Funding (Long Heavy)", "Downward Price/CVD Pressure"])

        # -------------------------------------------------------------
        # CONFLICT IDENTIFICATION
        # -------------------------------------------------------------
        if cvd_selling and state in ["✅ BUYERS IN CONTROL", "✅ BUYER ABSORPTION"]:
            conflicted.append("Negative Taker CVD vs Upper Range Price")
        if cvd_buying and state in ["✅ SELLERS IN CONTROL", "✅ SELLER ABSORPTION"]:
            conflicted.append("Positive Taker CVD vs Lower Range Price")
        if funding_positive and "SELLERS" in state:
            conflicted.append("High Positive Funding vs Bearish Control")
        if funding_negative and "BUYERS" in state:
            conflicted.append("High Negative Funding vs Bullish Control")

        if not agreed:
            agreed.append("Range Compression")

        return {
            "control_state": state,
            "confidence": confidence,
            "explanation": explanation,
            "agreed": agreed,
            "conflicted": conflicted if conflicted else ["None"]
        }

    def scan_symbol(self, symbol, datasets):
        df_15m = datasets["15m"]
        live_price = float(df_15m["close"].iloc[-1])
        ceiling = float(df_15m["high"].max())
        floor = float(df_15m["low"].min())
        
        width = round(((ceiling - floor) / live_price) * 100, 2)
        dist_ceil_pct = round(((ceiling - live_price) / live_price) * 100, 2)
        dist_floor_pct = round(((live_price - floor) / live_price) * 100, 2)
        
        oi = df_15m.get("open_interest")
        funding = df_15m.get("funding_rate")
        cvd = df_15m.get("cvd")
        
        control_analysis = self.determine_market_control(
            dist_ceil_pct=dist_ceil_pct,
            dist_floor_pct=dist_floor_pct,
            cvd=cvd,
            oi=oi,
            funding_rate=funding,
            df_15m=df_15m
        )
        
        # Status driven purely by boundary proximity
        if dist_ceil_pct <= 0.3 or dist_floor_pct <= 0.3:
            status = "CRITICAL"
        elif dist_ceil_pct <= 0.8 or dist_floor_pct <= 0.8:
            status = "ABOUT TO BREAK"
        elif width <= 1.5:
            status = "LOADING"
        else:
            status = "BUILDING"

        return {
            "symbol": symbol,
            "status": status,
            "control_state": control_analysis["control_state"],
            "confidence": control_analysis["confidence"],
            "explanation": control_analysis["explanation"],
            "agreed": control_analysis["agreed"],
            "conflicted": control_analysis["conflicted"],
            "live_price": live_price,
            "ceiling": ceiling,
            "floor": floor,
            "dist_ceil_pct": dist_ceil_pct,
            "dist_floor_pct": dist_floor_pct,
            "width": width,
            "age": len(df_15m),
            "open_interest": oi,
            "funding_rate": funding,
            "cvd": cvd,
            "sort_score": round(100 - min(dist_ceil_pct, dist_floor_pct) * 10, 2)
        }

    def calculate_market_temperature(self, results):
        critical_count = sum(1 for r in results if r["status"] == "CRITICAL")
        if critical_count >= 3:
            return {"temperature": "HOT 🔥"}
        elif critical_count >= 1:
            return {"temperature": "WARM 🟠"}
        return {"temperature": "COLD 🟢"}
