# =========================================================
# Stage 1: Range Detection Engine (detector.py)
# FROZEN ARCHITECTURE - DO NOT MODIFY CORE DETECTION LOGIC
# =========================================================

def calculate_boundary_readiness(curr_close, support, resistance):
    """Calculates true readiness score based on proximity to nearest boundary."""
    range_span = max(float(resistance) - float(support), 1e-9)
    
    dist_to_res = abs(float(resistance) - float(curr_close)) / range_span
    dist_to_supp = abs(float(curr_close) - float(support)) / range_span
    
    # Distance from center of range (0 = center, 1 = touching support/resistance)
    min_dist_to_edge = min(dist_to_res, dist_to_supp)
    proximity_pct = max(0.0, min(1.0, 1.0 - (2.0 * min_dist_to_edge)))
    
    # Scale score smoothly
    readiness_score = int(round(proximity_pct * 100))
    
    if readiness_score >= 85:
        label = f"{readiness_score}% (IMMINENT)"
    elif readiness_score >= 60:
        label = f"{readiness_score}% (BUILDING)"
    else:
        label = f"{readiness_score}% (DEVELOPING)"

    return readiness_score, label


def analyze_buyer_seller_battle(range_data, volumes, closes):
    """Calculates order flow volume battle per symbol without stale static defaults."""
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

    # Sum buy vs sell volume based on close-to-close progression
    for i in range(1, len(closes)):
        vol = float(volumes[i]) if i < len(volumes) else 0.0
        if closes[i] > closes[i - 1]:
            buying_vol += vol
        elif closes[i] < closes[i - 1]:
            selling_vol += vol
        else:
            buying_vol += vol * 0.5
            selling_vol += vol * 0.5

    total_vol = buying_vol + selling_vol
    if total_vol > 0:
        buyer_power = int(round((buying_vol / total_vol) * 100))
        buyer_power = max(5, min(95, buyer_power))  # Cap extreme bounds
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
    Your main Stage 1 range detection logic remains untouched below this line.
    """
    # ... KEEP YOUR EXISTING STAGE 1 DETECTOR CODE AS IS ...
    pass
