"""Alert engine and gate evaluation (Section 6)."""
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Tuple
from pipeline.config import (
    BASE_SLIPPAGE,
    MIN_ENTRY_TD,
    MIN_VOLUME_LOTS,
    MIN_OI_LOTS,
    HURDLE_MULTIPLE,
    STOP_Z_BUFFER,
)
from pipeline.attribution import calculate_round_trip_cost_bps
from pipeline.config import PAIR_DEFINITIONS
from pipeline.lifecycle import entry_timing_ok, intended_lots, min_entry_td, size_liquidity_ok
from pipeline.pairs import rolling_stats

def evaluate_pair_gates(
    row: pd.Series,
    W: int,
    ze: float,
    round_trip_cost_bps: float,
    sym_a: str = None,
    sym_b: str = None,
) -> Tuple[bool, List[str], Dict[str, bool]]:
    """
    Evaluates 5 gates from Section 6 for a given pair row:
    1. Enough history: >= W prior observations
    2. Extreme: z_entry <= |z| < z_entry + STOP_Z_BUFFER (unusual, but not already past the stop-loss)
    3. Edge beats cost: |spread - mu| >= 2 * round_trip_cost_bps
    4. Liquidity: each leg's intended lots <= MAX_PARTICIPATION x its volume, volume >= 25 lots, OI >= 50, not thin
    5. Lifecycle: each leg >= its own min entry days (tender window + exit lead + 2), not a roll day
    """
    gates = {}
    failed_reasons = []
    
    # Gate 1: Enough history
    z = row.get('z', np.nan)
    mu = row.get('mu', np.nan)
    has_history = not np.isnan(z) and not np.isnan(mu)
    gates['enough_history'] = has_history
    if not has_history:
        failed_reasons.append('history')
        
    # Gate 2: Extreme
    is_extreme = has_history and (abs(z) >= ze) and (abs(z) < ze + STOP_Z_BUFFER)
    gates['extreme'] = is_extreme
    if not is_extreme:
        failed_reasons.append('extreme')
        
    # Gate 3: Edge beats cost
    deviation_bps = abs(row['spread'] - mu) if has_history else 0.0
    hurdle_bps = HURDLE_MULTIPLE * round_trip_cost_bps
    edge_beats_cost = has_history and (deviation_bps >= hurdle_bps)
    gates['edge_beats_cost'] = edge_beats_cost
    if not edge_beats_cost:
        failed_reasons.append('edge')
        
    # Gate 4: Liquidity, sized to the trade: each leg's intended lots against that leg's own volume and OI
    # (lifecycle.size_liquidity_ok, the same check the backtest makes on the signal day and on every fill day)
    if sym_a and 'px_a' in row.index:
        _, lots_a, lots_b = intended_lots(sym_a, sym_b, float(row['px_a']))
        ok_a, _ = size_liquidity_ok(lots_a, row['vol_a'], row['oi_a'])
        ok_b, _ = size_liquidity_ok(lots_b, row['vol_b'], row['oi_b'])
        size_ok = ok_a and ok_b
    else:
        size_ok = (row['vol_a'] >= MIN_VOLUME_LOTS) and (row['vol_b'] >= MIN_VOLUME_LOTS) and \
                  (row['oi_a'] >= MIN_OI_LOTS) and (row['oi_b'] >= MIN_OI_LOTS)
    not_thin = not bool(row.get('thin_a', False)) and not bool(row.get('thin_b', False))
    liquidity_ok = bool(size_ok and not_thin)
    gates['liquidity'] = liquidity_ok
    if not liquidity_ok:
        failed_reasons.append('liquidity')
        
    # Gate 5: Lifecycle: each leg far enough from its own tender window (lifecycle.entry_timing_ok, same as backtest)
    if sym_a and 'expiry_a' in row.index:
        td_ok = entry_timing_ok(sym_a, row['expiry_a'], row['td_to_exp_a'], sym_b, row['expiry_b'], row['td_to_exp_b'])
    else:
        td_ok = (row['td_to_exp_a'] >= MIN_ENTRY_TD) and (row['td_to_exp_b'] >= MIN_ENTRY_TD)
    not_roll = not bool(row.get('roll', False)) and not bool(row.get('roll_flag', False))
    lifecycle_ok = td_ok and not_roll
    gates['lifecycle'] = lifecycle_ok
    if not lifecycle_ok:
        failed_reasons.append('lifecycle')
        
    is_signal = all(gates.values())
    return is_signal, failed_reasons, gates

def generate_today_alerts(
    pairs_dict: Dict[str, pd.DataFrame],
    best_params: pd.DataFrame,
    as_of_date: pd.Timestamp = None,
    switch: Dict[str, Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluates alerts across all pairs for the latest date (Section 6).
    switch: walk-forward on/off per pair (backtest.walk_forward_switch). A pair that training
    switched off never signals, even if all five market checks pass.
    """
    rt_cost_bps = calculate_round_trip_cost_bps(slip_bps=BASE_SLIPPAGE)
    hurdle_bps = HURDLE_MULTIPLE * rt_cost_bps
    
    pairs_alerts = []
    
    for pair_id, row in best_params.iterrows():
        W, ze, mh = int(row['W']), float(row['ze']), int(row['mh'])
        p_df = pairs_dict[pair_id].copy()
        
        # Calculate rolling stats with chosen W
        p_df['mu'], p_df['sd'], p_df['z'] = rolling_stats(p_df, W)   # same definition as the backtest and charts
        
        if as_of_date is not None:
            sub = p_df[p_df['date'] <= as_of_date]
        else:
            sub = p_df
            
        last_row = sub.iloc[-1]
        dt = last_row['date']
        
        sym_a, sym_b, _ = PAIR_DEFINITIONS[pair_id]
        is_signal, failed_reasons, gates = evaluate_pair_gates(
            last_row, W=W, ze=ze, round_trip_cost_bps=rt_cost_bps, sym_a=sym_a, sym_b=sym_b
        )
        grams_now, lots_a_now, lots_b_now = intended_lots(sym_a, sym_b, float(last_row['px_a']))
        sw = (switch or {}).get(pair_id, {'on': True, 'reason': 'no switch applied'})
        if not sw['on']:
            is_signal = False
            failed_reasons = failed_reasons + ['training']
        sd_now = float(last_row['sd']) if not np.isnan(last_row['sd']) else float('nan')
        hurdle_z = (hurdle_bps / sd_now) if sd_now and not np.isnan(sd_now) else float('nan')
        
        exp_a_str = last_row['expiry_a'].strftime('%b-%y') if hasattr(last_row['expiry_a'], 'strftime') else str(last_row['expiry_a'])
        exp_b_str = last_row['expiry_b'].strftime('%b-%y') if hasattr(last_row['expiry_b'], 'strftime') else str(last_row['expiry_b'])
        
        pairs_alerts.append({
            'pair_id': pair_id,
            'date': dt.strftime('%Y-%m-%d'),
            'contracts': f"{exp_a_str} / {exp_b_str}",
            'expiry_a': last_row['expiry_a'].strftime('%Y-%m-%d') if hasattr(last_row['expiry_a'], 'strftime') else str(last_row['expiry_a']),
            'expiry_b': last_row['expiry_b'].strftime('%Y-%m-%d') if hasattr(last_row['expiry_b'], 'strftime') else str(last_row['expiry_b']),
            'spread_bps': round(float(last_row['spread']), 1),
            'spread_rs_10g': round(float(last_row.get('spread_rs_10g', (last_row['spread'] / 10000.0) * last_row['px_b'] * 10.0)), 1),
            'mu': round(float(last_row['mu']), 1) if not np.isnan(last_row['mu']) else None,
            'sd': round(float(last_row['sd']), 1) if not np.isnan(last_row['sd']) else None,
            'z': round(float(last_row['z']), 2) if not np.isnan(last_row['z']) else None,
            'z_needed': ze,
            'stop_z': round(ze + STOP_Z_BUFFER, 2),
            'hurdle_z': round(hurdle_z, 1) if not np.isnan(hurdle_z) else None,
            'can_signal_now': bool(not np.isnan(hurdle_z) and hurdle_z < ze + STOP_Z_BUFFER),
            'pair_on': bool(sw['on']),
            'pair_switch_reason': sw['reason'],
            'deviation_bps': round(abs(float(last_row['spread'] - last_row['mu'])), 1) if not np.isnan(last_row['mu']) else 0.0,
            'hurdle_bps': round(hurdle_bps, 1),
            'round_trip_cost_bps': round(rt_cost_bps, 1),
            'status': 'SIGNAL' if is_signal else 'QUIET',
            'failed_gates': failed_reasons,
            'gates': gates,
            'vol_a': int(last_row['vol_a']),
            'vol_b': int(last_row['vol_b']),
            'oi_a': int(last_row['oi_a']),
            'oi_b': int(last_row['oi_b']),
            'lots_a': round(lots_a_now, 2),
            'lots_b': round(lots_b_now, 2),
            'part_a': round(lots_a_now / last_row['vol_a'], 4) if last_row['vol_a'] > 0 else None,
            'part_b': round(lots_b_now / last_row['vol_b'], 4) if last_row['vol_b'] > 0 else None,
            'min_entry_td_a': min_entry_td(sym_a, last_row['expiry_a']),
            'min_entry_td_b': min_entry_td(sym_b, last_row['expiry_b']),
            'td_to_exp_a': int(last_row['td_to_exp_a']),
            'td_to_exp_b': int(last_row['td_to_exp_b']),
            'roll_flag': bool(last_row.get('roll', False)),
        })
        
    all_quiet = all(p['status'] == 'QUIET' for p in pairs_alerts)
    headline = "No meaningful signal today" if all_quiet else "RV Divergence Signals Detected"
    
    return {
        'as_of_date': pairs_alerts[0]['date'] if pairs_alerts else '',
        'headline': headline,
        'all_quiet': all_quiet,
        'round_trip_cost_bps': round(rt_cost_bps, 1),
        'pairs': pairs_alerts,
    }

def generate_signals_history(
    all_trades_df: pd.DataFrame,
) -> List[Dict[str, Any]]:
    """
    Extracts every historical signal and its outcome from the executed trades (at base slippage).
    """
    if all_trades_df.empty:
        return []
        
    base_trades = all_trades_df[all_trades_df['slip'] == BASE_SLIPPAGE].copy()
    history = []
    
    for _, t in base_trades.iterrows():
        history.append({
            'date': t['sig'].strftime('%Y-%m-%d') if hasattr(t['sig'], 'strftime') else str(t['sig']),
            'pair': t['pair'],
            'entry_date': t['entry'].strftime('%Y-%m-%d') if hasattr(t['entry'], 'strftime') else str(t['entry']),
            'exit_date': t['exit'].strftime('%Y-%m-%d') if hasattr(t['exit'], 'strftime') else str(t['exit']),
            'expA': str(t['expA']),
            'expB': str(t['expB']),
            'z': t['z'],
            'direction': 'Long A / Short B' if t['side'] > 0 else 'Short A / Long B',
            'outcome': t['reason'],
            'net_bps': round(float(t['net_bps']), 1),
            'net_rs': round(float(t['net']), 1),
            'holding_days': int(t['days']),
            'seg': str(t.get('seg', 'test')),
        })
        
    # Sort descending by date
    history.sort(key=lambda x: x['date'], reverse=True)
    return history
