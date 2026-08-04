# =========================================================
# Stage 1: Range Detection Engine (detector.py)
# FROZEN ARCHITECTURE - DATA QUALITY & FIXES ONLY
# =========================================================

def normalize_candles(candles):
    """
    Ensures candles are in a consistent dictionary format regardless of input source.
    Handles dicts, lists, and tuples gracefully.
    """
    normalized = []
    if not candles:
        return normalized

    for c in candles:
        if isinstance(c, dict):
            normalized.append({
                "open": float(c.get("open") or c.get("o") or 0.0),
                "high": float(c.get("high") or c.get("h") or 0.0),
                "low": float(c.get("low") or c.get("l") or 0.0),
                "close": float(c.get("close") or c.get("c") or 0.0),
                "volume": float(c.get("volume") or c.get("vol") or c.get("v") or 0.0)
            })
        elif isinstance(c, (list, tuple)) and len(c) >= 5:
            # Standard array format: [time, open, high, low, close, volume]
            normalized.append({
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]) if len(c) > 5 else 0.0
            })
    return normalized


def calculate_boundary_readiness(curr_close, support, resistance):
    """
    Calculates readiness score based on proximity to nearest boundary (Support/Resistance)
    without saturating all scores near 100%.
    """
    try:
        curr_close = float(curr_close)
        support = float(support)
        resistance = float(resistance)
    except (TypeError, ValueError):
        return 0, "0% (INVALID)"

    range_span = max(resistance - support, 1e-9)
    if range_span <= 0:
        return 0, "0% (INVALID)"

    # Fractional distance to support and resistance
    dist_to_res = abs(resistance - curr_close) / range_span
    dist_to_supp = abs(curr_close - support) / range_span

    # Normalized distance to closest edge (0.0 at center, 1.0 at support/resistance)
    min_dist_to_edge = min(dist_to_res, dist_to_supp)
    proximity_pct = max(0.0, min(1.0, 1.0 - (2.0 * min_dist_to_edge)))

    readiness_score = int(round(proximity_pct * 100))

    if readiness_score >= 85:
        label = f"{readiness_score}% (IMMINENT)"
    elif readiness_score >= 60:
        label = f"{readiness_score}% (BUILDING)"
    else:
        label = f"{readiness_score}% (DEVELOPING)"

    return readiness_score, label


def analyze_buyer_seller_battle(range_data, volumes, closes):
    """
    Calculates dynamic order flow volume pressure per symbol.
    Provides neutral 50/50 fallback if volume data is empty or invalid.
    """
    if not volumes or not closes or len(closes) < 2 or sum(volumes) == 0:
        return {
            "buyer_power": 50,
            "seller_power": 50,
            "direction": "NEUTRAL",
            "price_position": 50,
            "interpretation": "BALANCED VOLUME"
        }

    buying_vol = 0.0
    selling_vol = 0.0

    # Accumulate volume based on bar close-to-close progression
    for i in range(1, len(closes)):
        vol = float(volumes[i]) if i < len(volumes) else 0.0
        c_curr = float(closes[i])
        c_prev = float(closes[i - 1])

        if c_curr > c_prev:
            buying_vol += vol
        elif c_curr < c_prev:
            selling_vol += vol
        else:
            buying_vol += vol * 0.5
            selling_vol += vol * 0.5

    total_vol = buying_vol + selling_vol
    if total_vol > 0:
        buyer_power = int(round((buying_vol / total_vol) * 100))
        # Keep within standard bound limits
        buyer_power = max(5, min(95, buyer_power))
        seller_power = 100 - buyer_power
    else:
        buyer_power = 50
        seller_power = 50

    return {
        "buyer_power": buyer_power,
        "seller_power": seller_power,
        "direction": "BULLISH" if buyer_power > 50 else "BEARISH",
        "price_position": buyer_power,
        "interpretation": "BUYER DOMINANT" if buyer_power > 50 else "SELLER DOMINANT"
    }


def detect_range(candles, timeframe):
    """
    Main Stage 1 Range Detection Function.
    Evaluates price consolidation and boundaries across candles.
    """
    norm_candles = normalize_candles(candles)

    if not norm_candles or len(norm_candles) < 20:
        return {
            "is_valid_range": False,
            "rejection_reason": "INSUFFICIENT_CANDLES"
        }

    closes = [c["close"] for c in norm_candles]
    highs = [c["high"] for c in norm_candles]
    lows = [c["low"] for c in norm_candles]

    curr_close = closes[-1]

    # Evaluate boundaries on recent window
    window = min(len(norm_candles), 40)
    recent_highs = highs[-window:]
    recent_lows = lows[-window:]

    resistance = max(recent_highs)
    support = min(recent_lows)

    if resistance <= support or curr_close <= 0:
        return {
            "is_valid_range": False,
            "rejection_reason": "INVALID_BOUNDARIES"
        }

    avg_price = (resistance + support) / 2.0
    range_span = resistance - support
    range_pct = (range_span / avg_price) * 100.0

    # Ensure range height is within realistic consolidation thresholds
    if range_pct < 0.2 or range_pct > 25.0:
        return {
            "is_valid_range": False,
            "rejection_reason": f"RANGE_SPAN_OUT_OF_BOUNDS_{range_pct:.1f}%"
        }

    # Classify pattern structure
    first_half_high = max(highs[-window:-window//2])
    second_half_high = max(highs[-window//2:])
    first_half_low = min(lows[-window:-window//2])
    second_half_low = min(lows[-window//2:])

    structure_type = "HORIZONTAL"
    if second_half_low > first_half_low * 1.002 and abs(second_half_high - first_half_high) / avg_price < 0.005:
        structure_type = "ASCENDING TRIANGLE"
    elif second_half_high < first_half_high * 0.998 and abs(second_half_low - first_half_low) / avg_price < 0.005:
        structure_type = "DESCENDING TRIANGLE"

    return {
        "is_valid_range": True,
        "support": support,
        "resistance": resistance,
        "curr_close": curr_close,
        "structure_type": structure_type,
        "rejection_reason": None
    }
