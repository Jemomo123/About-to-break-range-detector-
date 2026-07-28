import logging
from detector import RangeDetector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class MarketScanner:

    def __init__(self):
        # Dedicated analysis instance
        self.detector = RangeDetector(max_range_width_pct=3.0, min_age_candles=15)

    def is_15m_range_valid(self, df_15m) -> bool:
        """Gatekeeper check used by app.py to halt API requests early."""
        if df_15m is None:
            return False
        res = self.detector.detect_range_15m(df_15m)
        return res["is_valid"]

    def scan_symbol(self, symbol: str, datasets: dict) -> dict | None:
        """Requirement 1: Calls RangeDetector without duplicating analytical logic."""
        if not datasets or "15m" not in datasets or "5m" not in datasets:
            return None

        pressure_obj = self.detector.evaluate_pressure(datasets)

        df_5m = datasets["5m"]
        oi_val = df_5m["open_interest"].iloc[-1] if "open_interest" in df_5m.columns else 0.0
        funding_val = df_5m["funding_rate"].iloc[-1] if "funding_rate" in df_5m.columns else 0.0
        cvd_val = df_5m["cvd"].iloc[-1] if "cvd" in df_5m.columns else 0.0

        return {
            "symbol": symbol,
            "status": pressure_obj["pressure"],
            "sort_score": pressure_obj["score"],
            "confidence": "HIGH" if pressure_obj["pressure"] in ["CRITICAL", "ABOUT TO BREAK"] else "MEDIUM",
            "width": pressure_obj.get("width", 0.0),
            "age": pressure_obj.get("age", 0),
            "direction": pressure_obj.get("direction", "Neutral"),
            "open_interest": oi_val,
            "funding_rate": funding_val,
            "cvd": cvd_val,
            "reasons": pressure_obj.get("reasons", []),
        }

    def calculate_market_temperature(self, scan_results: list) -> dict:
        counts = {
            "BUILDING": 0,
            "LOADING": 0,
            "ABOUT TO BREAK": 0,
            "CRITICAL": 0,
        }
        for item in scan_results:
            st = item.get("status", "BUILDING")
            if st in counts:
                counts[st] += 1

        active = counts["CRITICAL"] + counts["ABOUT TO BREAK"]
        if active >= 3:
            temp = "BOILING"
        elif active >= 1 or counts["LOADING"] >= 3:
            temp = "WARM"
        else:
            temp = "COLD"

        return {"temperature": temp, "metrics": counts}
