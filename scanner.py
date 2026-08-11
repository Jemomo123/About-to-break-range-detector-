def analyze_level_battle(df: pd.DataFrame, symbol: str, timeframe: str):
    if df.empty or len(df) < 30:
        return None, "INSUFFICIENT DATA"

    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    curr_close = float(closes[-1])
    last_row = df.iloc[-1]

    support_struct, resistance_struct, sup_touches, res_touches, is_accepted, acceptance_rate, _ = find_structural_levels(
        highs=highs, lows=lows, closes=closes,
        lookback=40, tolerance_pct=0.7, min_touches=2, acceptance_threshold=60.0
    )

    candidate = None
    if support_struct is not None and resistance_struct is not None and is_accepted:
        range_width = (resistance_struct - support_struct) / support_struct * 100 if support_struct > 0 else 0
        candidate = {
            'support': support_struct,
            'resistance': resistance_struct,
            'support_touches': sup_touches,
            'resistance_touches': res_touches,
            'range_status': 'STRUCTURAL',
            'range_width_percent': range_width,
            'pattern_type': classify_pattern(df, support_struct, resistance_struct),
            'acceptance_rate': acceptance_rate,
            'is_accepted': True,
        }
    else:
        support_simple, resistance_simple, pattern_type, valid = detect_range_simple(df, lookback=30)
        if valid and support_simple is not None and resistance_simple is not None:
            range_width = (resistance_simple - support_simple) / support_simple * 100 if support_simple > 0 else 0
            acceptance = calculate_acceptance_rate(closes, support_simple, resistance_simple, lookback=30)
            candidate = {
                'support': support_simple,
                'resistance': resistance_simple,
                'support_touches': 1,
                'resistance_touches': 1,
                'range_status': 'PROVISIONAL',
                'range_width_percent': range_width,
                'pattern_type': pattern_type,
                'acceptance_rate': acceptance,
                'is_accepted': False,
            }
        else:
            candidate = None

    existing = get_existing_range(symbol, timeframe)

    # ---- State Machine ----
    active_support = 0.0
    active_resistance = 0.0
    active_status = "NO VALID RANGE"
    active_pattern = "NO CLEAR RANGE"
    decision = None
    reason = None
    range_invalidated = False
    invalidation_direction = "NONE"
    invalidation_price = 0.0
    previous_support = 0.0
    previous_resistance = 0.0

    if existing is None:
        if candidate is not None:
            candidate['range_start_index'] = len(df) - 1
            candidate['range_age'] = 0
            candidate['range_last_validated'] = len(df) - 1
            candidate['consecutive_outside_closes'] = 0
            candidate['invalidation_info'] = None
            set_range(symbol, timeframe, candidate)
            active_support = candidate['support']
            active_resistance = candidate['resistance']
            active_status = candidate['range_status']
            active_pattern = candidate['pattern_type']
            decision = "STORED"
            reason = "new range established"
        else:
            active_support = 0.0
            active_resistance = 0.0
            active_status = "NO VALID RANGE"
            active_pattern = "NO CLEAR RANGE"
            decision = "NONE"
            reason = "no candidate"
    else:
        invalidated, direction, price = is_range_invalidated(existing, df)
        range_invalidated = invalidated

        if invalidated:
            previous_support = existing['support']
            previous_resistance = existing['resistance']
            invalidation_direction = direction
            invalidation_price = price

            existing['range_status'] = "INVALIDATED"
            existing['invalidation_info'] = {
                'direction': direction,
                'price': price,
                'candle_index': len(df) - 1,
                'time': datetime.now(timezone.utc).isoformat()
            }
            set_range(symbol, timeframe, existing)

            active_support = 0.0
            active_resistance = 0.0
            active_status = "INVALIDATED"
            active_pattern = "NO CLEAR RANGE"
            decision = "INVALIDATED"
            reason = f"range invalidated, direction {direction} at price {price:.2f}"
        else:
            if existing['range_status'] == 'PROVISIONAL' and candidate is not None and candidate['range_status'] == 'STRUCTURAL':
                if (candidate['support_touches'] >= 3 and
                    candidate['resistance_touches'] >= 3 and
                    candidate.get('is_accepted', False)):
                    candidate['range_age'] = existing.get('range_age', 0)
                    candidate['range_start_index'] = existing.get('range_start_index', len(df) - 1)
                    candidate['range_last_validated'] = len(df) - 1
                    candidate['consecutive_outside_closes'] = 0
                    candidate['invalidation_info'] = None
                    set_range(symbol, timeframe, candidate)
                    active_support = candidate['support']
                    active_resistance = candidate['resistance']
                    active_status = 'STRUCTURAL'
                    active_pattern = candidate['pattern_type']
                    decision = "UPGRADED"
                    reason = "provisional upgraded to structural"
                else:
                    active_support = existing['support']
                    active_resistance = existing['resistance']
                    active_status = existing['range_status']
                    active_pattern = existing.get('pattern_type', 'CONSOLIDATION')
                    decision = "KEPT"
                    reason = "existing provisional remains"
            else:
                active_support = existing['support']
                active_resistance = existing['resistance']
                active_status = existing['range_status']
                active_pattern = existing.get('pattern_type', 'CONSOLIDATION')
                decision = "KEPT"
                reason = f"existing {active_status} range still valid"

            if decision in ['KEPT', 'UPGRADED']:
                stored = get_existing_range(symbol, timeframe)
                if stored is not None:
                    stored['range_age'] = stored.get('range_age', 0) + 1
                    stored['range_last_validated'] = len(df) - 1
                    set_range(symbol, timeframe, stored)

    # --- FORCE INVALIDATION: if price closed outside the active range ---
    if active_support and active_resistance and active_support > 0 and active_resistance > 0:
        if last_row['close'] > active_resistance:
            if existing is not None:
                existing['range_status'] = "INVALIDATED"
                existing['invalidation_info'] = {
                    'direction': 'UPSIDE',
                    'price': last_row['close'],
                    'candle_index': len(df) - 1,
                    'time': datetime.now(timezone.utc).isoformat()
                }
                set_range(symbol, timeframe, existing)
            # Clear active range
            previous_support = active_support
            previous_resistance = active_resistance
            invalidation_direction = "UPSIDE"
            invalidation_price = last_row['close']
            active_support = 0.0
            active_resistance = 0.0
            active_status = "INVALIDATED"
            active_pattern = "NO CLEAR RANGE"
            decision = "FORCE_INVALIDATED"
            reason = "price closed above resistance"
        elif last_row['close'] < active_support:
            if existing is not None:
                existing['range_status'] = "INVALIDATED"
                existing['invalidation_info'] = {
                    'direction': 'DOWNSIDE',
                    'price': last_row['close'],
                    'candle_index': len(df) - 1,
                    'time': datetime.now(timezone.utc).isoformat()
                }
                set_range(symbol, timeframe, existing)
            previous_support = active_support
            previous_resistance = active_resistance
            invalidation_direction = "DOWNSIDE"
            invalidation_price = last_row['close']
            active_support = 0.0
            active_resistance = 0.0
            active_status = "INVALIDATED"
            active_pattern = "NO CLEAR RANGE"
            decision = "FORCE_INVALIDATED"
            reason = "price closed below support"

    # --- Try to establish new range after invalidation ---
    stored = get_existing_range(symbol, timeframe)
    if stored is not None and stored.get('range_status') == 'INVALIDATED':
        invalidation_info = stored.get('invalidation_info')
        if invalidation_info is not None:
            invalidation_candle = invalidation_info.get('candle_index', 0)
            if len(df) - 1 > invalidation_candle:
                if candidate is not None and candidate.get('range_status') == 'STRUCTURAL':
                    candidate['range_start_index'] = len(df) - 1
                    candidate['range_age'] = 0
                    candidate['range_last_validated'] = len(df) - 1
                    candidate['consecutive_outside_closes'] = 0
                    candidate['invalidation_info'] = None
                    set_range(symbol, timeframe, candidate)
                    active_support = candidate['support']
                    active_resistance = candidate['resistance']
                    active_status = candidate['range_status']
                    active_pattern = candidate['pattern_type']
                    decision = "NEW_RANGE"
                    reason = "new structural range after invalidation"
                else:
                    active_support = 0.0
                    active_resistance = 0.0
                    active_status = "INVALIDATED"
                    active_pattern = "NO CLEAR RANGE"

    # --- Penetration detection (unchanged) ---
    penetration_type = "NONE"
    penetration_explanation = ""
    if active_support is not None and active_support > 0 and active_resistance is not None and active_resistance > 0:
        if active_status != "INVALIDATED":
            if last_row['low'] < active_support and last_row['close'] >= active_support:
                penetration_type = "SUPPORT PENETRATION"
                penetration_explanation = (f"Support penetrated: candle low ({last_row['low']:.2f}) traded below "
                                           f"active support ({active_support:.2f}) but closed back above it.")
            elif last_row['high'] > active_resistance and last_row['close'] <= active_resistance:
                penetration_type = "RESISTANCE PENETRATION"
                penetration_explanation = (f"Resistance penetrated: candle high ({last_row['high']:.2f}) traded above "
                                           f"active resistance ({active_resistance:.2f}) but closed back below it.")

    # --- Logging ---
    if DEBUG:
        print(f"RANGE DECISION {symbol} {timeframe}")
        print(f"  Candidate: {candidate['support'] if candidate else None} / {candidate['resistance'] if candidate else None} ({candidate['range_status'] if candidate else 'NONE'})")
        print(f"  Existing:  {existing['support'] if existing else None} / {existing['resistance'] if existing else None} ({existing['range_status'] if existing else 'NONE'})")
        print(f"  Decision:  {decision}")
        print(f"  Reason:    {reason}")
        print(f"  Final range: {active_support} / {active_resistance}")
        print(f"  Status:    {active_status}")
        print(f"  Penetration: {penetration_type}")
        if penetration_explanation:
            print(f"  Explanation: {penetration_explanation}")
        if invalidation_direction != "NONE":
            print(f"  Invalidation: {invalidation_direction} at {invalidation_price:.2f}")
        print("---")

    # --- Battle logic (runs only when active range exists) ---
    if active_support and active_resistance and active_support > 0 and active_resistance > 0:
        # Only run battle logic if price is near the boundary
        dist_to_res = (active_resistance - curr_close) / curr_close * 100
        dist_to_sup = (curr_close - active_support) / curr_close * 100
        # --- CHANGE: proximity threshold from 5.0 to 1.5 ---
        threshold = 1.5

        if dist_to_res < dist_to_sup and dist_to_res < threshold:
            level_type = "RESISTANCE"
            level_price = active_resistance
            distance = dist_to_res
            result = evaluate_resistance_battle(df, active_resistance)
        elif dist_to_sup < threshold:
            level_type = "SUPPORT"
            level_price = active_support
            distance = dist_to_sup
            result = evaluate_support_battle(df, active_support)
        else:
            level_type = "NONE"
            level_price = curr_close
            distance = 0.0
            result = {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "Price not near boundary."}
    else:
        level_type = "NONE"
        level_price = curr_close
        distance = 0.0
        result = {"side": "NEUTRAL", "signal": "NO CLEAR SIGNAL", "score": 0, "reason": "No active range."}

    last_updated = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    clean_display = symbol.replace("-", "").replace("_", "").upper()

    return {
        "symbol": clean_display,
        "timeframe": timeframe,
        "curr_close": round(curr_close, 6),
        "level_type": level_type,
        "level_price": round(level_price, 6),
        "distance_to_level": round(distance, 2),
        "winner": result["side"],
        "signal": result["signal"],
        "explanation": result["reason"],
        "support": round(active_support, 6) if active_support is not None else 0.0,
        "resistance": round(active_resistance, 6) if active_resistance is not None else 0.0,
        "pattern_type": active_pattern,
        "range_status": active_status,
        "last_updated": last_updated,
        "penetration_type": penetration_type,
        "penetration_explanation": penetration_explanation,
        "previous_support": round(previous_support, 6) if previous_support else 0.0,
        "previous_resistance": round(previous_resistance, 6) if previous_resistance else 0.0,
        "invalidation_direction": invalidation_direction,
        "invalidation_price": round(invalidation_price, 6) if invalidation_price else 0.0,
        "invalidation_time": stored.get('invalidation_info', {}).get('time', '') if stored and stored.get('invalidation_info') else ''
    }, None
