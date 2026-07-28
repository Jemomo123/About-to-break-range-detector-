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

    def determine_market_control(self, dist_ceil_pct, dist_floor_pct, cvd, oi_change, funding_rate):
        """
        Interprets Effort vs. Result inside the range.
        Determines who is actually winning the battle.
        """
        near_ceiling = dist_ceil_pct <= 0.6
        near_floor = dist_floor_pct <= 0.6
        
        # Safely extract scalar numeric values
        try:
            cvd_val = float(cvd) if cvd is not None else None
        except (ValueError, TypeError):
            cvd_val = None

        try:
            funding_val = float(funding_rate) if funding_rate is not None else None
        except (ValueError, TypeError):
            funding_val = None

        cvd_buying = cvd_val is not None and cvd_val > 0
        cvd_selling = cvd_val is not None and cvd_val < 0

        # 1. ABSORPTION (High Taker Effort, Price Fails to Advance)
        if cvd_buying and not near_ceiling:
            return "BUYERS BEING ABSORBED 🛑"
            
        if cvd_selling and not near_floor:
            return "SELLERS BEING ABSORBED 🛑"

        # 2. DOMINANCE (Aggressive Takers Moving Price to Boundaries)
        if cvd_buying and near_ceiling:
            return "BUYERS DOMINATING 📈"
            
        if cvd_selling and near_floor:
            return "SELLERS DOMINATING 📉"

        # 3. TRAP / OVERCROWDED
        if funding_val is not None:
            if funding_val > 0.01 and near_ceiling and cvd_selling:
                return "LONG TRAP BUILDING ⚠️"
            if funding_val < -0.01 and near_floor and cvd_buying:
                return "SHORT TRAP BUILDING ⚠️"

        # 4. BALANCED
        return "BALANCED BATTLE ⚖️"

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
        
        control_state = self.determine_market_control(
            dist_ceil_pct=dist_ceil_pct,
            dist_floor_pct=dist_floor_pct,
            cvd=cvd,
            oi_change=1,
            funding_rate=funding
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
            "control_state": control_state,
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
