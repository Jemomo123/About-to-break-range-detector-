import numpy as np
import pandas as pd

# =====================================================================
# 1. TREND FILTER (Suppress Range Detection During Active Cascades)
# =====================================================================
def is_actively_trending(df: pd.DataFrame, sma_fast=20, sma_slow=100) -> bool:
    """
    Returns True if the market is in an active directional trend/cascade,
    where range detection must be suppressed.
    """
    if df.empty or len(df) < sma_slow:
        return False

    closes = df['close'].values
    sma20 = df['close'].rolling(sma_fast).mean().values
    sma100 = df['close'].rolling(sma_slow).mean().values

    # Calculate 20 SMA slope over the last 5 candles
    sma20_slope = (sma20[-1] - sma20[-5]) / sma20[-5] * 100.0
    c_price = closes[-1]

    # Strong markdown cascade: Price below steeply falling 20 SMA
    is_markdown = (sma20_slope < -0.25) and (c_price < sma20[-1]) and (sma20[-1] < sma100[-1])
    
    # Strong markup trend: Price above steeply rising 20 SMA
    is_markup = (sma20_slope > 0.25) and (c_price > sma20[-1]) and (sma20[-1] > sma100[-1])

    return is_markdown or is_markup


# =====================================================================
# 2. VALIDATED RANGE DETECTOR (Replaces detect_range_simple & Naive Min/Max)
# =====================================================================
def find_validated_range(df: pd.DataFrame, lookback=40):
    """
    Detects structurally valid ranges while ignoring phantom support levels
    created by falling prices.
    """
    if df.empty or len(df) < lookback:
        return None

    recent_df = df.tail(lookback).copy()
    highs = recent_df['high'].values
    lows = recent_df['low'].values
    closes = recent_df['close'].values

    # Step A: Filter out single isolate wicks using percentiles (4th and 96th)
    p_high = float(np.percentile(highs, 96))
    p_low = float(np.percentile(lows, 4))

    v_high = p_high if np.sum(highs > p_high) <= 1 else float(np.max(highs))
    v_low = p_low if np.sum(lows < p_low) <= 1 else float(np.min(lows))

    r_height = v_high - v_low
    if r_height <= 0:
        return None

    range_width_pct = (r_height / v_low) * 100.0
    if range_width_pct < 0.4 or range_width_pct > 15.0:  # Reject invalid range dimensions
        return None

    # Step B: Enforce TIME-SEPARATED touches (minimum 4 candles apart)
    touch_tolerance = r_height * 0.10
    upper_touches = 0
    lower_touches = 0
    last_upper_idx = -10
    last_lower_idx = -10

    for i in range(len(highs)):
        # Resistance Touch
        if (v_high - highs[i]) <= touch_tolerance:
            if i - last_upper_idx >= 4:  # Require time separation
                upper_touches += 1
                last_upper_idx = i

        # Support Touch
        if (lows[i] - v_low) <= touch_tolerance:
            if i - last_lower_idx >= 4:  # Require time separation
                lower_touches += 1
                last_lower_idx = i

    # Reject if boundaries lack true two-sided defense
    if upper_touches < 2 or lower_touches < 2:
        return None

    # Step C: Containment Check
    containment_tol = r_height * 0.05
    out_of_bounds = np.sum((closes > (v_high + containment_tol)) | (closes < (v_low - containment_tol)))
    containment_pct = (1.0 - (out_of_bounds / lookback)) * 100.0

    if containment_pct < 70.0:  # Must hold price inside 70%+ of the time
        return None

    # Step D: Breakdown / Expansion Disqualification
    c_price = closes[-1]
    if c_price < v_low or c_price > v_high:
        return None  # Already expanded/broken out!

    return {
        'support': v_low,
        'resistance': v_high,
        'support_touches': lower_touches,
        'resistance_touches': upper_touches,
        'range_status': 'VALIDATED',
        'containment_pct': round(containment_pct, 1),
        'range_width_percent': round(range_width_pct, 2)
    }


# =====================================================================
# 3. FIXED SUPPORT BATTLE ENGINE (Stops False "SUPPORT HOLDING" Signals)
# =====================================================================
def evaluate_support_battle_corrected(df: pd.DataFrame, support: float, window=8):
    if df.empty or len(df) < window or support <= 0:
        return {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "Insufficient data."}

    last_row = df.iloc[-1]
    c_price = last_row['close']

    # HARD GUARD: If price closed below support, signal BREAKDOWN immediately!
    if c_price < support:
        return {
            "side": "SELLERS",
            "signal": "BREAKDOWN CONFIRMED",
            "score": 10,
            "reason": f"Price closed at ${c_price:.1f}, below support level (${support:.1f})."
        }

    # Continue with standard candle pressure scoring...
    recent = df.tail(window)
    buyer_score = 0
    seller_score = 0

    for idx, row in recent.iterrows():
        candle_range = row['high'] - row['low']
        if candle_range == 0:
            continue
            
        close_pos = (row['close'] - row['low']) / candle_range
        is_bullish = row['close'] > row['open']

        if is_bullish and close_pos > 0.6:
            buyer_score += 2
        elif not is_bullish and close_pos < 0.4:
            seller_score += 2

    if seller_score > buyer_score:
        return {
            "side": "SELLERS",
            "signal": "BREAKDOWN IMMINENT",
            "score": seller_score,
            "reason": "Sellers maintaining heavy pressure near support."
        }
    elif buyer_score > seller_score:
        return {
            "side": "BUYERS",
            "signal": "SUPPORT HOLDING",
            "score": buyer_score,
            "reason": "Buyers actively defending support floor."
        }
    else:
        return {
            "side": "NEUTRAL",
            "signal": "NO CLEAR SIGNAL",
            "score": 0,
            "reason": "Battle at support is balanced."
        }


# =====================================================================
# 4. UPDATED MAIN ANALYSIS PIPELINE
# =====================================================================
def analyze_level_battle_corrected(df: pd.DataFrame, symbol: str, timeframe: str):
    if df.empty or len(df) < 40:
        return None, "INSUFFICIENT DATA"

    # 1. Trend Filter Check
    if is_actively_trending(df):
        return None, "TRENDING / NO RANGE"

    # 2. Validated Range Detection
    val_range = find_validated_range(df, lookback=40)

    if val_range is None:
        return None, "NO VALID RANGE"

    # 3. Evaluate Support / Resistance Battles safely
    c_price = df.iloc[-1]['close']
    support = val_range['support']
    resistance = val_range['resistance']

    # Evaluate battle based on which boundary price is closest to
    if abs(c_price - support) < abs(c_price - resistance):
        battle_result = evaluate_support_battle_corrected(df, support)
    else:
        battle_result = {"side": "NEUTRAL", "signal": "RANGE MIDPOINT", "score": 0, "reason": "Price in mid-range."}

    return {
        "range_data": val_range,
        "battle": battle_result
    }, "SUCCESS"
