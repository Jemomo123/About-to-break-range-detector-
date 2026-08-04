# =====================================================================
# STAGE 2 — BREAKOUT ANALYSIS ENGINE
# =====================================================================

class BreakoutAnalysisEngine:
    """
    Stage 2: Breakout Analysis.
    Calculates Price Location %, Buyer/Seller Power %, Direction & Readiness.
    """

    @staticmethod
    def analyze(symbol: str, current_price: float, range_data: dict, order_flow: dict) -> dict:
        support = range_data["support"]
        resistance = range_data["resistance"]
        range_span = resistance - support
        
        # 1. Price Location %
        price_location_pct = round(((current_price - support) / range_span) * 100) if range_span > 0 else 0
        price_location_pct = max(0, min(100, price_location_pct))
        
        # 2. Buyer vs Seller Power
        buyer_vol = order_flow.get("buyer_volume", 0)
        seller_vol = order_flow.get("seller_volume", 0)
        total_vol = buyer_vol + seller_vol
        
        buyer_power = round((buyer_vol / total_vol) * 100) if total_vol > 0 else 50
        seller_power = 100 - buyer_power

        # 3. Direction & Breakout Status Logic
        if price_location_pct >= 80 and buyer_power >= 60:
            direction = "UPSIDE"
            status = "IMMINENT BREAKOUT" if price_location_pct >= 90 else "READY FOR UPSIDE BREAKOUT"
        elif price_location_pct <= 20 and seller_power >= 60:
            direction = "DOWNSIDE"
            status = "IMMINENT BREAKDOWN" if price_location_pct <= 10 else "READY FOR DOWNSIDE BREAKDOWN"
        else:
            direction = "UPSIDE" if buyer_power >= seller_power else "DOWNSIDE"
            status = "BUILDING PRESSURE"

        return {
            "symbol": symbol,
            "range_type": range_data["range_type"],
            "support": support,
            "resistance": resistance,
            "current_price": current_price,
            "price_location_pct": price_location_pct,
            "buyer_power": buyer_power,
            "seller_power": seller_power,
            "direction": direction,
            "status": status
        }
