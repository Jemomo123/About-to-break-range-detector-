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
        Institutional Market Control Engine:
        Evaluates dynamic order flow imbalance across 7 graded states using weighted structural evidence.
        """
        # --- 1. Data Normalization ---
        try: cvd_val = float(cvd) if cvd is not None else 0.0
        except (ValueError, TypeError): cvd_val = 0.0

        try: funding_val = float(funding_rate) if funding_rate is not None else 0.0
        except (ValueError, TypeError): funding_val = 0.0

        try: oi_val = float(oi) if oi is not None else 0.0
        except (ValueError, TypeError): oi_val = 0.0

        # Volume Acceleration Check
        vol_accel = False
        if df_15m is not None and "volume" in df_15m and len(df_15m) >= 5:
            recent_avg_vol = df_15m["volume"].iloc[-6:-1].mean()
            last_vol = df_15m["volume"].iloc[-1]
            if recent_avg_vol > 0 and (last_vol / recent_avg_vol) >= 1.25:
                vol_accel = True

        # Boundary Flags
        at_ceiling_extreme = dist_ceil_pct <= 0.3
        at_floor_extreme = dist_floor_pct <= 0.3
        near_ceiling = dist_ceil_pct <= 0.8
        near_floor = dist_floor_pct <= 0.8

        cvd_positive = cvd_val > 0
        cvd_negative = cvd_val < 0
        funding_bullish_bias = funding_val < -0.005  # Shorts heavy (Bullish tailwind)
        funding_bearish_bias = funding_val > 0.005   # Longs heavy (Bearish risk)

        # --- 2. Weighted Factor Scoring (Base 50 = Perfectly Neutral) ---
        net_score = 50
        evidence_pro = []
        evidence_con = []

        # Factor A: Position Inside Range & Boundary Pressure
        if at_ceiling_extreme:
            net_score += 25
            evidence_pro.append("✔ Price pressing upper boundary extreme")
        elif near_ceiling:
            net_score += 15
            evidence_pro.append("✔ Price near upper resistance")
        else:
            evidence_con.append("✘ Price not at resistance")

        if at_floor_extreme:
            net_score -= 25
            evidence_pro.append("✔ Price pressing lower boundary extreme")
        elif near_floor:
            net_score -= 15
            evidence_pro.append("✔ Price near lower support")
        else:
            evidence_con.append("✘ Price not at support")

        # Factor B: CVD Delta Flow & Divergence
        if cvd_positive:
            net_score += 15
            evidence_pro.append("✔ Positive Taker CVD flow")
        elif cvd_negative:
            net_score -= 15
            evidence_pro.append("✔ Negative Taker CVD flow")
        else:
            evidence_con.append("✘ Neutral Delta flow")

        # Factor C: Volume Acceleration
        if vol_accel:
            if net_score >= 50:
                net_score += 10
            else:
                net_score -= 10
            evidence_pro.append("✔ Volume expansion on 15M bar")
        else:
            evidence_con.append("✘ Weak volume acceleration")

        # Factor D: Funding Bias
        if funding_bullish_bias:
            net_score += 8
            evidence_pro.append("✔ Negative funding (Shorts heavy/squeezable)")
        elif funding_bearish_bias:
            net_score -= 8
            evidence_pro.append("✔ Positive funding (Longs heavy/squeezable)")
        else:
            evidence_pro.append("✔ Neutral funding environment")

        # Factor E: Open Interest Participation
        if oi_val > 0:
            if net_score > 50:
                net_score += 7
            elif net_score < 50:
                net_score -= 7
            evidence_pro.append("✔ Open Interest actively expanding")
        else:
            evidence_con.append("✘ Weak Open Interest participation")

        # Cap score dynamically to 0-100%
        confidence = max(0, min(100, net_score))

        # --- 3. Graded 7-State Classification Engine ---
        
        # Overlay Traps: Absorption & Squeezes
        if (near_ceiling or at_ceiling_extreme) and cvd_negative:
            state = "🟡 BUYER ABSORPTION"
            confidence = max(68, confidence)
            reason = "Price is holding near resistance despite negative CVD. Aggressive limit buy wall absorbing seller supply."
            evidence = [
                "✔ Resistance boundary defended",
                "✔ Negative CVD (Limit absorption active)",
                "✔ Price stability near ceiling",
                "✔ Volume active at ceiling" if vol_accel else "✘ Weak volume acceleration"
            ]
        elif (near_floor or at_floor_extreme) and cvd_positive:
            state = "🟣 SELLER ABSORPTION"
            confidence = max(68, 100 - confidence)
            reason = "Price is holding near support despite positive CVD. Aggressive limit sell wall absorbing buyer demand."
            evidence = [
                "✔ Support boundary defended",
                "✔ Positive CVD (Limit absorption active)",
                "✔ Price stability near floor",
                "✔ Volume active at floor" if vol_accel else "✘ Weak volume acceleration"
            ]
        # Standard Graded Control States
        elif confidence >= 85:
            state = "🟢 BUYERS DOMINATING"
            reason = "Aggressive taker buyers in full control. High positive CVD, boundary pressure, and volume expansion signal imminent breakout."
            evidence = evidence_pro
        elif confidence >= 70:
            state = "🟢 BUYERS GAINING CONTROL"
            reason = "Buyers building structural advantage with expanding CVD and upward price pressure inside the range."
            evidence = evidence_pro
        elif confidence >= 55:
            state = "🟡 SLIGHT BUYER EDGE"
            reason = "Buyers hold a modest edge with mild positive CVD or boundary defense, but lack heavy volume or OI confirmation for strong dominance."
            evidence = evidence_pro + evidence_con
        elif confidence >= 46:
            state = "⚖️ BALANCED BATTLE"
            reason = "Neither buyers nor sellers show structural dominance. Price and order flow remain balanced within the range."
            evidence = [
                "✔ Range compression active",
                "✘ No CVD delta advantage",
                "✘ Neutral boundary proximity",
                "✘ Funding neutral"
            ]
        elif confidence >= 31:
            state = "🟠 SLIGHT SELLER EDGE"
            reason = "Sellers hold a modest edge with mild negative CVD or upper rejection, but lack strong volume or OI confirmation."
            evidence = evidence_pro + evidence_con
        elif confidence >= 16:
            state = "🔴 SELLERS GAINING CONTROL"
            reason = "Sellers building structural advantage with expanding negative CVD and downward price pressure."
            evidence = evidence_pro
        else:
            state = "🔴 SELLERS DOMINATING"
            reason = "Aggressive taker sellers in full control. Heavy market sell flow pressing lower support with volume acceleration."
            evidence = evidence_pro

        return {
            "control_state": state,
            "confidence": confidence,
            "explanation": reason,
            "evidence": evidence
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
            "evidence": control_analysis["evidence"],
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
