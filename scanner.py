import numpy as np
import pandas as pd
import requests
from datetime import datetime, timezone

# Required exports for app.py
UNSUPPORTED_SYMBOLS = set()

def is_unsupported(symbol):
    return symbol in UNSUPPORTED_SYMBOLS

def fetch_klines(symbol, timeframe="15m", limit=60):
    """Fetches market candles from public REST API."""
    tf_map = {
        "5M": "5m", "15M": "15m", "1H": "1h", "4H": "4h",
        "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h"
    }
    interval = tf_map.get(timeframe, "15m")
    
    # Try Futures endpoint first
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            df = pd.DataFrame(data, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
            ])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            return df
    except Exception:
        pass

    # Fallback to Spot endpoint
    url_spot = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        resp = requests.get(url_spot, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            df = pd.DataFrame(data, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
            ])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            return df
    except Exception:
        pass

    return None

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
    if df_raw is None or len(df_raw) < 20:
        return None
        
    df = find_pivots(df_raw)
    recent = df.tail(40)
    
    current_price = float(recent['close'].iloc[-1])
    
    pivot_highs = recent[recent['pivot_high']]
    pivot_lows = recent[recent['pivot_low']]
    
    support_level = float(recent['low'].min())
    resistance_level = float(recent['high'].max())
    
    side = "NEUTRAL"
    signal = "RANGE BOUND"
    reason = "Price is consolidating inside horizontal boundaries."
    
    # Check for Flat Horizontal Resistance Ceiling
    flat_resistance = False
    if len(pivot_highs) >= 2:
        high_vals = pivot_highs['high'].values[-3:]
        max_h, min_h = np.max(high_vals), np.min(high_vals)
        if (max_h - min_h) / max_h <= 0.005:
            flat_resistance = True
            resistance_level = float(np.mean(high_vals))

    # Check for Flat Horizontal Support Floor
    flat_support = False
    if len(pivot_lows) >= 2:
        low_vals = pivot_lows['low'].values[-3:]
        max_l, min_l = np.max(low_vals), np.min(low_vals)
        if (max_l - min_l) / max_l <= 0.005:
            flat_support = True
            support_level = float(np.mean(low_vals))

    # Ascending Triangle: Flat Resistance Ceiling + Higher Lows
    if flat_resistance and len(pivot_lows) >= 2:
        low_vals = pivot_lows['low'].values
        if len(low_vals) >= 2 and low_vals[-1] > low_vals[0]:
            side = "BUYERS"
            signal = "BREAKOUT IMMINENT"
            reason = "Buyers are winning at resistance; breakout pressure is building."
            support_level = float(low_vals[-1])

    # Descending Triangle: Flat Support Floor + Lower Highs
    elif flat_support and len(pivot_highs) >= 2:
        high_vals = pivot_highs['high'].values
        if len(high_vals) >= 2 and high_vals[-1] < high_vals[0]:
            side = "SELLERS"
            signal = "BREAKDOWN IMMINENT"
            reason = "Sellers pressing support; breakdown pressure is building."
            resistance_level = float(high_vals[-1])

    elif flat_resistance or flat_support:
        if abs(current_price - resistance_level) < abs(current_price - support_level):
            side = "BUYERS"
            signal = "TESTING RESISTANCE"
            reason = "Price is pressing flat resistance ceiling."
        else:
            side = "BUYERS"
            signal = "SUPPORT HOLDING"
            reason = "Price is holding flat support floor."

    # Level & distance math
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

    decimals = 4 if current_price < 1 else 2
    c_price = round(current_price, decimals)
    s_level = round(support_level, decimals)
    r_level = round(resistance_level, decimals)
    l_price = round(level_price, decimals)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        # Supply both keys so frontend template reads price cleanly
        "price": c_price,
        "current_price": c_price,
        "support": s_level,
        "resistance": r_level,
        "testing_level": testing_level,
        "level_price": l_price,
        "distance_pct": distance_pct,
        "dist_pct": distance_pct,
        "updated_at": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        # Top-level battle attributes
        "side": side,
        "signal": signal,
        "reason": reason,
        # Nested battle attribute dictionary
        "battle": {
            "side": side,
            "signal": signal,
            "reason": reason
        }
    }

def _process_symbol_tf(symbol, timeframe):
    """Main worker entrypoint expected by app.py (returns tuple: data, error)."""
    try:
        df = fetch_klines(symbol, timeframe)
        if df is None or df.empty:
            return None, f"Failed to fetch klines for {symbol}"
            
        result = analyze_symbol_structure(df, symbol, timeframe)
        if result is None:
            return None, f"Structure analysis failed for {symbol}"
            
        return result, None
    except Exception as e:
        return None, str(e)
