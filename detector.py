# =====================================================================
# STAGE 1 — STRUCTURAL RANGE GATEKEEPER
# =====================================================================

class RangeDetectionEngine:
    """
    Stage 1: Pure Price Action Range Gatekeeper.
    Returns ONLY: {is_valid, range_type, support, resistance} or None.
    """

    @staticmethod
    def detect_range(candles: list) -> dict | None:
        if not candles or len(candles) < 30:
            return None

        # 1. Detect structural pivot points
        pivots = RangeDetectionEngine._extract_pivots(candles)
        if len(pivots["highs"]) < 2 or len(pivots["lows"]) < 2:
            return None

        # 2. Build support & resistance boundary zones
        zones = RangeDetectionEngine._build_reaction_zones(pivots, candles)
        if not zones:
            return None
        
        sup_min, sup_max = zones["support_zone"]
        res_min, res_max = zones["resistance_zone"]

        if sup_max >= res_min:
            return None  # Boundaries overlap

        # 3. Confirm at least 2 independent touches on each boundary
        s_touches, r_touches = RangeDetectionEngine._count_touches(
            candles, zones["support_zone"], zones["resistance_zone"]
        )
        if s_touches < 2 or r_touches < 2:
            return None

        # 4. Reject if price has already broken out
        current_close = candles[-1]["close"]
        if current_close > res_max or current_close < sup_min:
            return None

        # 5. Reject obvious trending markets
        if RangeDetectionEngine._is_trending(pivots):
            return None

        # 6. Classify structure
        range_type = RangeDetectionEngine._classify_structure(pivots)
        if not range_type:
            return None

        support_mid = (sup_min + sup_max) / 2
        resistance_mid = (res_min + res_max) / 2

        # Final Strict Return Schema
        return {
            "is_valid": True,
            "range_type": range_type,
            "support": round(support_mid, 6),
            "resistance": round(resistance_mid, 6)
        }

    # -----------------------------------------------------------------
    # STRUCTURAL ALGORITHM HELPERS
    # -----------------------------------------------------------------
    @staticmethod
    def _extract_pivots(candles: list) -> dict:
        highs, lows = [], []
        for i in range(2, len(candles) - 2):
            if candles[i]["high"] > candles[i-1]["high"] and candles[i]["high"] > candles[i-2]["high"] and \
               candles[i]["high"] > candles[i+1]["high"] and candles[i]["high"] > candles[i+2]["high"]:
                highs.append(candles[i]["high"])
                
            if candles[i]["low"] < candles[i-1]["low"] and candles[i]["low"] < candles[i-2]["low"] and \
               candles[i]["low"] < candles[i+1]["low"] and candles[i]["low"] < candles[i+2]["low"]:
                lows.append(candles[i]["low"])
        return {"highs": highs, "lows": lows}

    @staticmethod
    def _build_reaction_zones(pivots: dict, candles: list) -> dict | None:
        total_span = max([c["high"] for c in candles]) - min([c["low"] for c in candles])
        if total_span <= 0:
            return None

        cluster_tolerance = total_span * 0.04

        def find_best_cluster(prices: list):
            clusters = []
            for p in prices:
                matched = [x for x in prices if abs(x - p) <= cluster_tolerance]
                clusters.append({"count": len(matched), "items": matched})
            clusters.sort(key=lambda c: c["count"], reverse=True)
            if not clusters or clusters[0]["count"] < 2:
                return None
            best = clusters[0]["items"]
            return (min(best), max(best))

        res_zone = find_best_cluster(pivots["highs"])
        sup_zone = find_best_cluster(pivots["lows"])

        if not res_zone or not sup_zone:
            return None

        return {"support_zone": sup_zone, "resistance_zone": res_zone}

    @staticmethod
    def _count_touches(candles: list, sup_zone: tuple, res_zone: tuple) -> tuple[int, int]:
        sup_min, sup_max = sup_zone
        res_min, res_max = res_zone
        range_span = res_max - sup_min

        s_touches, r_touches = 0, 0
        in_sup, in_res = False, False

        for c in candles:
            if c["low"] <= sup_max and c["high"] >= sup_min:
                if not in_sup:
                    s_touches += 1
                    in_sup = True
            elif c["low"] > (sup_max + range_span * 0.15):
                in_sup = False

            if c["high"] >= res_min and c["low"] <= res_max:
                if not in_res:
                    r_touches += 1
                    in_res = True
            elif c["high"] < (res_min - range_span * 0.15):
                in_res = False

        return s_touches, r_touches

    @staticmethod
    def _is_trending(pivots: dict) -> bool:
        h, l = pivots["highs"], pivots["lows"]
        if len(h) < 3 or len(l) < 3:
            return False
        is_uptrend = (h[-1] > h[-2] > h[-3]) and (l[-1] > l[-2] > l[-3])
        is_downtrend = (h[-1] < h[-2] < h[-3]) and (l[-1] < l[-2] < l[-3])
        return is_uptrend or is_downtrend

    @staticmethod
    def _classify_structure(pivots: dict) -> str | None:
        h, l = pivots["highs"], pivots["lows"]
        flat_highs = abs(h[-1] - h[-2]) / h[-2] <= 0.006
        flat_lows = abs(l[-1] - l[-2]) / l[-2] <= 0.006
        rising_lows = l[-1] > l[-2] * 1.004
        falling_highs = h[-1] < h[-2] * 0.996

        if flat_highs and flat_lows:
            return "HORIZONTAL"
        elif flat_highs and rising_lows:
            return "ASCENDING_TRIANGLE"
        elif flat_lows and falling_highs:
            return "DESCENDING_TRIANGLE"
        elif rising_lows and falling_highs:
            return "SYMMETRICAL_TRIANGLE"

        return None
