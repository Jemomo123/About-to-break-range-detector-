import numpy as np
import pandas as pd
from datetime import datetime, timezone

def find_pivots(df, window=3):
    """Identifies local swing highs and swing lows."""
    df = df.copy()
    df['pivot_high'] = False
    df['pivot_low'] = False
    
    for i in range(window, len(df) - window):
        high_window = df['high'].iloc[i - window : i + window + 1]
        low_window = df['low'].iloc[i - window : i + window + 1]
        
        if df['high'].iloc[i] == high_window.max():
            df.loc[df.index[i], 'pivot_high'] = True
            
        if df['low'].iloc[i] == low_window.min():
            df.loc[df.index[i], 'pivot_low'] = True
            
    return df

def analyze_symbol_structure(df_raw, symbol, timeframe):
    """
    Analyzes price structure for:
    1. Pure Range (Flat Support + Flat Resistance)
    2. Ascending Triangle (Flat Resistance + Higher Lows)
    3. Descending Triangle (Flat Support + Lower Highs)
    """
    if df_raw is None or len(df_raw) < 30:
        return None
        
    df = find_pivots(df_raw.copy())
    recent = df.tail(40)
    
    current_price = float(recent['close'].iloc[-1])
    
    # Get recent pivot points
    pivot_highs = recent[recent['pivot_high']]
    pivot_lows = recent[recent['pivot_low']]
    
    # Default levels based on maximum extremes
    support_level = float(recent['low'].min())
    resistance_level = float(recent['high'].max())
    
    side = "NEUTRAL"
    signal = "RANGE BOUND"
    reason = "Price is consolidating inside horizontal boundaries."
    
    # 1. Check for Flat Horizontal Resistance (Ceiling)
    flat_resistance = False
    if len(pivot_highs) >= 2:
        high_vals = pivot_highs['high'].values[-3:]
        max_h, min_h = np.max(high_vals), np.min(high_vals)
        # If peaks are within 0.4% tolerance, resistance is flat
        if (max_h - min_h) / max_h <= 0.004:
            flat_resistance = True
            resistance_level = float(np.mean(high_vals))

    # 2. Check for Flat Horizontal Support (Floor)
    flat_support = False
    if len(pivot_lows) >= 2:
        low_vals = pivot_lows['low'].values[-3:]
        max_l, min_l = np.max(low_vals), np.min(low_vals)
        # If troughs are within 0.4% tolerance, support is flat
        if (max_l - min_l) / min_l <= 0.004:
            flat_support = True
            support_level = float(np.mean(low_vals))

    # Pattern Detection & Battle Logic
    if flat_resistance and len(pivot_lows) >= 2:
        low_vals = pivot_lows['low'].values
        # Check for Higher Lows -> Ascending Triangle
        if len(low_vals) >= 2 and low_vals[-1] > low_vals[0]:
            side = "BUYERS"
            signal = "BREAKOUT IMMINENT"
            reason = "Buyers are winning at resistance; breakout pressure is building."
            support_level = float(low_vals[-1]) # Set support to latest higher low

    elif flat_support and len(pivot_highs) >= 2:
        high_vals = pivot_highs['high'].values
        # Check for Lower Highs -> Descending Triangle
        if len(high_vals) >= 2 and high_vals[-1] < high_vals[0]:
            side = "SELLERS"
            signal = "BREAKDOWN IMMINENT"
            reason = "Sellers pressing support; breakdown pressure is building."
            resistance_level = float(high_vals[-1]) # Set resistance to latest lower high

    elif flat_resistance or flat_support:
        # Standard horizontal range close to boundary
        if abs(current_price - resistance_level) < abs(current_price - support_level):
            side = "BUYERS"
            signal = "TESTING RESISTANCE"
            reason = "Price is pressing flat resistance ceiling."
        else:
            side = "BUYERS"
            signal = "SUPPORT HOLDING"
            reason = "Price is holding flat support floor."

    # Distance calculations
    dist_to_res = abs(current_price - resistance_level)
    dist_to_sup = abs(current_price - support_level)
    
    if dist_to_res < dist_to_sup:
        testing_level = "RESISTANCE"
        level_price = resistance_level
        distance_pct = round((dist_to_res / current_price) * 100, 2)
    else:
        testing_level = "SUPPORT"
        level_price = support_level
        distance_pct = round((dist_to_sup / current_price) * 100, 2)

    # Format decimals based on price scale
    decimals = 4 if current_price < 1 else 2

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "price": round(current_price, decimals),
        "support": round(support_level, decimals),
        "resistance": round(resistance_level, decimals),
        "testing_level": testing_level,
        "level_price": round(level_price, decimals),
        "distance_pct": distance_pct,
        "updated_at": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "battle": {
            "side": side,
            "signal": signal,
            "reason": reason
        }
    }
