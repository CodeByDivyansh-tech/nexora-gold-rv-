"""Contract lifecycle calculations and Gantt timeline data (Section 7)."""
from pipeline.contract_rules import tender_rule
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple

def min_entry_td(symbol: str, expiry) -> int:
    """Fewest trading days to expiry a leg may have on a SIGNAL day under the current rule.

    The exit decision comes EXIT_LEAD_TD days before the last day the leg may be held (the day before its tender
    window), and the fill day (signal + 1) must still be at least one day before that decision."""
    from pipeline.config import EXIT_LEAD_TD
    from pipeline.contract_rules import tender_rule
    return int(tender_rule(symbol, expiry)['applied_td']) + EXIT_LEAD_TD + 2


def entry_timing_ok(sym_a: str, exp_a, td_a: int, sym_b: str, exp_b, td_b: int) -> bool:
    """Both legs, checked independently, are far enough from their own tender windows to open a position.
    Used by the live alerts (alerts.evaluate_pair_gates) and the backtest (backtest.run_pair_backtest)."""
    return td_a >= min_entry_td(sym_a, exp_a) and td_b >= min_entry_td(sym_b, exp_b)


def intended_lots(sym_a: str, sym_b: str, px_a: float):
    """Lots per leg a signal would trade (Section 5.4 sizing: equal grams, ~NOTIONAL_PER_LEG, whole lots)."""
    import numpy as np
    from pipeline.config import NOTIONAL_PER_LEG, SPEC_TUPLES
    la, lb = SPEC_TUPLES[sym_a][0], SPEC_TUPLES[sym_b][0]
    g = (la * lb) // np.gcd(la, lb)
    grams = int(g * max(1, round(NOTIONAL_PER_LEG / (g * px_a))))
    return grams, grams / la, grams / lb


def size_liquidity_ok(lots: float, vol, oi) -> Tuple[bool, float]:
    """One leg's size-aware liquidity screen: volume and OI floors, and lots <= MAX_PARTICIPATION x volume.
    Returns (ok, participation); participation is inf when volume is missing or zero."""
    from pipeline.config import MAX_PARTICIPATION, MIN_OI_LOTS, MIN_VOLUME_LOTS
    if vol is None or oi is None or pd.isna(vol) or pd.isna(oi) or vol <= 0:
        return False, float('inf')
    part = float(lots) / float(vol)
    return bool(vol >= MIN_VOLUME_LOTS and oi >= MIN_OI_LOTS and part <= MAX_PARTICIPATION), part


def compute_contract_lifecycle(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recomputes contract calendar with lifecycle windows (Section 7):
    - first_seen
    - liquid_from: first date OI >= 25% of peak OI
    - peak_oi_lots, peak_oi_date
    - last_seen
    - entry_allowed_window: liquid_from -> (expiry - 7 TD)
    - forced_exit_date: (expiry - 4 TD)
    """
    records = []
    
    for (sym, exp), g in df.groupby(['symbol', 'expiry']):
        g = g.sort_values('date').reset_index(drop=True)
        first_seen = g['date'].min()
        last_seen = g['date'].max()
        rows_count = len(g)
        no_trade_count = int(g['no_trade'].sum())
        
        peak_idx = g['oi'].idxmax()
        peak_oi = int(g.loc[peak_idx, 'oi'])
        peak_date = g.loc[peak_idx, 'date']
        
        # liquid_from: first date OI >= 25% of peak OI
        if peak_oi > 0:
            liq_sub = g[g['oi'] >= 0.25 * peak_oi]
            liquid_from = liq_sub['date'].min() if not liq_sub.empty else first_seen
        else:
            liquid_from = first_seen
            
        # Current rule (contract_rules.tender_rule): the last signal day a new position may open, the last day a
        # position may still be held (the day before the tender window) and the first day of the tender window
        rule = tender_rule(sym, exp)
        tw = int(rule['applied_td'])
        ent = g[g['td_to_exp'] >= min_entry_td(sym, exp)]
        entry_allowed_end = ent['date'].max() if not ent.empty else last_seen
        held = g[g['td_to_exp'] >= tw]
        forced_exit_date = held['date'].max() if not held.empty else first_seen
        win = g[g['td_to_exp'] < tw]
        tender_start = win['date'].min() if not win.empty else None
        
        records.append({
            'symbol': sym,
            'expiry_date': exp.strftime('%Y-%m-%d') if hasattr(exp, 'strftime') else str(exp),
            'first_seen': first_seen.strftime('%Y-%m-%d'),
            'liquid_from': liquid_from.strftime('%Y-%m-%d'),
            'peak_oi_lots': peak_oi,
            'peak_oi_date': peak_date.strftime('%Y-%m-%d'),
            'last_seen': last_seen.strftime('%Y-%m-%d'),
            'entry_allowed_start': liquid_from.strftime('%Y-%m-%d'),
            'entry_allowed_end': entry_allowed_end.strftime('%Y-%m-%d') if pd.notna(entry_allowed_end) else last_seen.strftime('%Y-%m-%d'),
            'forced_exit_date': forced_exit_date.strftime('%Y-%m-%d') if pd.notna(forced_exit_date) else last_seen.strftime('%Y-%m-%d'),
            'tender_window_td': tw,
            'tender_start': tender_start.strftime('%Y-%m-%d') if tender_start is not None else None,
            'tender_rule_status': rule['status'],
            'rows': rows_count,
            'no_trade_days': no_trade_count,
        })
        
    return pd.DataFrame(records).sort_values(['symbol', 'expiry_date']).reset_index(drop=True)


def calendar_check(trades: pd.DataFrame, lifecycle_df: pd.DataFrame) -> Dict[str, Any]:
    """Every trade must sit inside both contracts' calendars: entered on a day both were listed, closed on or
    before the last day either traded and never after expiry. Also counts trades the calendar closed early
    (a contract roll or the approach of expiry and its tender period)."""
    from pipeline.config import PAIR_DEFINITIONS
    lc = lifecycle_df.set_index(['symbol', 'expiry_date'])
    ds = lambda v: pd.Timestamp(v).strftime('%Y-%m-%d')
    inside = 0
    for _, t in trades.iterrows():
        a, b, _ = PAIR_DEFINITIONS[t['pair']]
        e, x = ds(t['entry']), ds(t['exit'])
        ok = True
        for sym, exp in ((a, ds(t['expA'])), (b, ds(t['expB']))):
            if (sym, exp) not in lc.index:
                ok = False
                break
            c = lc.loc[(sym, exp)]
            ok = ok and c['first_seen'] <= e <= c['last_seen'] and e <= x <= c['last_seen'] and x <= exp
        inside += bool(ok)
    reasons = trades['reason'].value_counts() if len(trades) else pd.Series(dtype=int)
    out = {'n': int(len(trades)), 'inside': int(inside),
           'closed_roll': int(reasons.get('roll', 0)),
           # 'tender' (current rule) and 'expiry' (legacy buffer) are both the calendar closing a trade early
           'closed_expiry': int(reasons.get('expiry', 0)) + int(reasons.get('tender', 0))}
    if len(trades) and 'td_exit_a' in trades.columns:
        # exit fill before BOTH legs' tender windows (each leg checked against its own window)
        ok = (trades['td_exit_a'] >= trades['tender_td_a']) & (trades['td_exit_b'] >= trades['tender_td_b'])
        out['before_tender'] = int(ok.sum())
        out['min_td_at_exit'] = int(min(trades['td_exit_a'].min(), trades['td_exit_b'].min()))
        out['forced_fills'] = int(trades['forced_fill'].sum()) if 'forced_fill' in trades.columns else 0
        out['lifecycle_status'] = {str(k): int(v) for k, v in trades['lifecycle'].value_counts().items()} if 'lifecycle' in trades.columns else {}
        out['verified_official'] = int((trades['lifecycle'] == 'official').sum()) if 'lifecycle' in trades.columns else 0
    return out
