import logging
from detector import RangeDetector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class MarketScanner:

    def __init__(self):
        self.detector = RangeDetector(max_range_width_pct=3.0, min_age_candles=15)

    def is_15m_range_valid(self, df_15m) -> bool:
        if df_15m is None:
            return False
        res = self.detector.detect_range_15m(df_15m)
        return res["is_valid"]

    def scan_symbol(self, symbol: str, datasets: dict) -> dict | None:
        if not datasets or "15m" not in datasets or "5m" not in datasets:
            return None

        pressure_obj = self.detector.evaluate_pressure(datasets)

        df_5m = datasets["5m"]
        oi_val = df_5m["open_interest"].iloc[-1] if "open_interest" in df_5m.columns else None
        funding_val = df_5m["funding_rate"].iloc[-1] if "funding_rate" in df_5m.columns else None
        cvd_val = df_5m["cvd"].iloc[-1] if "cvd" in df_5m.columns else None

        logging.info(
            f"[Scan Result] Symbol: {symbol} | Status: {pressure_obj['pressure']} | "
            f"Score: {pressure_obj['score']} | Bullish: {pressure_obj['bullish_prob']}% | "
            f"OI: {'N/A' if oi_val is None else oi_val} | "
            f"Funding: {'N/A' if funding_val is None else funding_val} | "
            f"CVD: {'N/A' if cvd_val is None else cvd_val}"
        )

        return {
            "symbol": symbol,
            "status": pressure_obj["pressure"],
            "sort_score": pressure_obj["score"],
            "bullish_prob": pressure_obj["bullish_prob"],
            "bearish_prob": pressure_obj["bearish_prob"],
            "width": pressure_obj["width"],
            "age": pressure_obj["age"],
            "ceiling": pressure_obj["ceiling"],
            "floor": pressure_obj["floor"],
            "live_price": pressure_obj["live_price"],
            "dist_ceil_pct": pressure_obj["dist_ceil_pct"],
            "dist_floor_pct": pressure_obj["dist_floor_pct"],
            "open_interest": oi_val,
            "funding_rate": funding_val,
            "cvd": cvd_val,
            "reasons": pressure_obj["reasons"],
            "breakdown": pressure_obj["breakdown"],
        }

    def calculate_market_temperature(self, scan_results: list) -> dict:
        counts = {"BUILDING": 0, "LOADING": 0, "ABOUT TO BREAK": 0, "CRITICAL": 0}
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
        
