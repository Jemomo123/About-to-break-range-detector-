# detector.py
# =====================================================================
# VERSION 1.0 — DETECTOR CONSUMER MODULE
# =====================================================================

def detect_range_and_structure(val_range, close_price):
    """
    Consumes the single source of truth validated range from app.py.
    Performs zero independent range, ceiling, floor, width, or touch calculations.
    
    Parameters:
        val_range (dict): Validated range output from app.py get_validated_range()
        close_price (float): Current asset close price
        
    Returns:
        dict: Standardized detection metadata mapped directly from val_range
    """
    if val_range is None:
        return {
            "valid": False,
            "v_high": None,
            "v_low": None,
            "r_height": 0.0,
            "containment_pct": 0.0,
            "is_structurally_valid": False,
            "has_already_expanded": True,
            "position_pct": 50.0
        }

    v_high = val_range["v_high"]
    v_low = val_range["v_low"]
    r_height = val_range["r_height"]

    # Position percentage calculation relative to consumed validated range
    if r_height > 0:
        position_pct = round(((close_price - v_low) / r_height) * 100.0, 1)
    else:
        position_pct = 50.0

    return {
        "valid": not val_range["has_already_expanded"],
        "v_high": v_high,
        "v_low": v_low,
        "r_height": r_height,
        "containment_pct": val_range["containment_pct"],
        "upper_touches": val_range["upper_touches"],
        "lower_touches": val_range["lower_touches"],
        "is_structurally_valid": val_range["is_structurally_valid"],
        "has_already_expanded": val_range["has_already_expanded"],
        "lookback_window": val_range["lookback_window"],
        "position_pct": position_pct
    }
