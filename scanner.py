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
        Evaluates structural imbalance across Price Position, CVD Delta, Funding, 
        Volume Acceleration, and Range Compression to compute dynamic confidence % 
        and evidence lists.
        """
        # --- 1. Data Normalization ---
        try: cvd_val = float(cvd) if cvd is not None else 0.0
        except (ValueError, TypeError): cvd_val = 0.0

        try: funding_val = float(funding_rate) if funding_rate is not None else 0.0
        except (ValueError, TypeError): funding_val = 0.0

        try: oi_val = float(oi) if oi is not None else 0.0
        except (ValueError, TypeError): oi_val = 0.0

        # Volume Acceleration
        vol_accel = False
        if df_15m is not None and "volume" in df_15m and len(df_15m) >= 5:
            recent_avg_vol = df_15m["volume"].iloc[-6:-1].mean()
            last_vol = df_15m["volume"].iloc[-1]
            if recent_avg_vol > 0 and (last_vol / recent_avg_vol) >= 1.25:
                vol_accel = True

        # Position Flags
        near_ceiling = dist_ceil_pct <= 0.8
        near_floor = dist_floor_pct <= 0.8
        at_ceiling_extreme = dist_ceil_pct <= 0.3
        at_floor_extreme = dist_floor_pct <= 0.3

        cvd_positive = cvd_val > 0
        cvd_negative = cvd_val < 0
        funding_bullish_bias = funding_val < -0.005  # Shorts paying longs (Bullish squeeze tailwind)
        funding_bearish_bias = funding_val > 0.005   # Longs paying shorts (Bearish squeeze risk)

        # --- 2. Multi-Factor Scoring Engine ---
        buyer_score = 0
        seller_score = 0
        evidence_pro = []
        evidence_con = []

        # Factor A: Range Boundary Proximity
        if near_ceiling:
            buyer_score += 30
            evidence_pro.append("✔ Price pressing upper boundary")
        else:
            evidence_con.append("✘ Price not at resistance")

        if near_floor:
            seller_score += 30
            evidence_pro.append("✔ Price pressing lower boundary")
        else:
            evidence_con.append("20✘ Price not at support")

        # Factor B: CVD Delta Direction
        if cvd_positive:
            buyer_score += 25
            evidence_pro.append("✔ Positive Taker CVD flow")
        elif cvd_negative:
            seller_score += 25
            evidence_pro.append("✔ Negative Taker CVD flow")
        else:
            evidence_con.append("✘ Flat/Neutral Delta flow")

        # Factor C: Volume Acceleration
        if vol_accel:
            if buyer_score >= seller_score:
                buyer_score += 15
            else:
                seller_score += 15
            evidence_pro.append("✔ Volume expansion on 15M bar")
        else:
            evidence_con.append("✘ Volume below 1.25x average")

        # Factor D: Funding Alignment
        if funding_bullish_bias:
            buyer_score += 15
            evidence_pro.append("✔ Negative funding (Shorts heavy/squeezable)")
        elif funding_bearish_bias:
            seller_score += 15
            evidence_pro.append("✔ Positive funding (Longs heavy/squeezable)")
        else:
            evidence_pro.append("✔ Neutral funding environment")

        # Factor E: Open Interest Presence
        if oi_val > 0:
            if buyer_score > seller_score:
                buyer_score += 10
            elif seller_score > buyer_score:
                seller_score += 10
            evidence_pro.append("✔ Open Interest actively participating")
        else:
            evidence_con.append("✘ Open Interest metric neutral/low")

        # --- 3. Institutional Classification & Dynamic Confidence ---
        
        # Scenario 1: BUYER ABSORPTION (Limit buy wall absorbing market sells at high prices or near ceiling)
        if near_ceiling and cvd_negative:
            state = "🟡 BUYER ABSORPTION"
            confidence = min(92, 70 + (10 if vol_accel else 0) + (12 if at_ceiling_extreme else 0))
            reason = "Price continues pressing resistance despite negative CVD. Aggressive limit buy wall absorbing market sell pressure."
            evidence = [
                "✔ Price at upper boundary",
                "✔ Negative CVD (Limit absorption occurring)",
                "✔ High ceiling price stability",
                "✔ Volume active at boundary" if vol_accel else "✘ Volume neutral"
            ]

        # Scenario 2: SELLER ABSORPTION (Limit sell wall absorbing market buys near floor)
        elif near_floor and cvd_positive:
            state = "🟣 SELLER ABSORPTION"
            confidence = min(92, 70 + (10 if vol_accel else 0) + (12 if at_floor_extreme else 0))
            reason = "Price is pinned near support despite positive CVD. Aggressive limit sell wall absorbing market buy orders."
            evidence = [
                "✔ Price at lower boundary",
                "✔ Positive CVD (Limit absorption occurring)",
                "✔ Floor price rejection holding",
                "✔ Volume active at boundary" if vol_accel else "✘ Volume neutral"
            ]

        # Scenario 3: BUYERS GAINING CONTROL
        elif buyer_score >= 60 and buyer_score > seller_score + 25:
            state = "🟢 BUYERS GAINING CONTROL"
            confidence = min(96, buyer_score + (10 if vol_accel else 0))
            reason = "Price is pressing ceiling with positive CVD and active volume alignment indicating taker buyers leading auction."
            evidence = [
                "✔ Price near upper boundary",
                "✔ Positive CVD taker dominance",
                "✔ Volume acceleration present" if vol_accel else "✘ Volume neutral",
                "✔ Favorable funding tailwind" if funding_bullish_bias else "✔ Neutral funding"
            ]

        # Scenario 4: SELLERS GAINING CONTROL
        elif seller_score >= 60 and seller_score > buyer_score + 25:
            state = "🔴 SELLERS GAINING CONTROL"
            confidence = min(96, seller_score + (10 if vol_accel else 0))
            reason = "Price pressing lower support with negative CVD and aggressive market sells driving range expansion."
            evidence = [
                "✔ Price near lower boundary",
                "✔ Negative CVD taker dominance",
                "✔ Volume acceleration present" if vol_accel else "✘ Volume neutral",
                "✔ Favorable funding tailwind" if funding_bearish_bias else "✔ Neutral funding"
            ]

        # Scenario 5: SHORT SQUEEZE RISK
        elif funding_bullish_bias and (near_ceiling or cvd_positive):
            state = "⚡ SHORT SQUEEZE RISK"
            confidence = 82
            reason = "Overcrowded short positioning with price or CVD moving upward against heavy negative funding."
            evidence = [
                "✔ Heavily negative funding rate",
                "✔ Price/Delta holding upper bias",
                "✔ Squeeze potential elevated"
            ]

        # Scenario 6: LONG SQUEEZE RISK
        elif funding_bearish_bias and (near_floor or cvd_negative):
            state = "⚠️ LONG SQUEEZE RISK"
            confidence = 82
            reason = "Overcrowded long positioning with price or CVD pressing downward against elevated positive funding."
            evidence = [
                "✔ Heavily positive funding rate",
                "✔ Price/Delta holding lower bias",
                "✔ Cascade potential elevated"
            ]

        # Scenario 7: TRUE BALANCED BATTLE
        else:
            diff = abs(buyer_score - seller_score)
            confidence = max(35, min(58, 50 + diff))
            state = "⚖️ TRUE BALANCED BATTLE"
            reason = "Neither buyers nor sellers show structural dominance. Price and order flow remain balanced within the range."
            evidence = [
                "✔ Range compression active",
                "✘ No CVD delta advantage",
                "✘ No boundary proximity dominance",
                "✘ Funding neutral"
            ]

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
