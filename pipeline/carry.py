"""Implied carry and term structure decomposition according to Sections 4.2 and 4.3."""
import pandas as pd
import numpy as np
from typing import Tuple, Dict
from pipeline.config import DEFAULT_CARRY

def compute_reference_carry(df: pd.DataFrame, dates: np.ndarray, exclude_tender: bool = True) -> Tuple[pd.Series, pd.DataFrame]:
    """
    Computes daily reference carry c_t from GOLDPETAL calendar spreads (Section 4.2).
    c_t = ln(F_far / F_near) * 365 / (calendar days between the two expiries), per year, from that day's closes.
    The pair used each day is the one with the highest min(open interest) as of t-1, so the choice uses nothing
    from day t onwards. Days with no usable pair carry the last estimate forward (never backward).

    exclude_tender: skip pairs whose near contract is inside its tender window (contract_rules.tender_rule), where the
        price reflects delivery, not carry (Oct-2026 audit). False reproduces the original study's choice.
    Returns:
        carry: pd.Series indexed by date with daily reference carry rate
        chosen_pairs: pd.DataFrame with details of chosen GOLDPETAL contract pair per date, incl. 'unstable'
            (estimate outside [CARRY_SANE_LO, CARRY_SANE_HI] a year)
    """
    from pipeline.config import CARRY_SANE_LO, CARRY_SANE_HI
    from pipeline.contract_rules import tender_rule
    # GOLDPETAL traded rows
    cols = ['date', 'expiry', 'px', 'oi_prev'] + (['td_to_exp'] if 'td_to_exp' in df.columns else [])
    pet = df[(df['symbol'] == 'GOLDPETAL') & ~df['no_trade_day']][cols].copy()

    # Pairwise merge on date
    cc = pet.merge(pet, on='date', suffixes=('_n', '_f'))
    cc = cc[cc['expiry_f'] > cc['expiry_n']].dropna(subset=['oi_prev_n', 'oi_prev_f', 'px_n', 'px_f'])
    if exclude_tender and 'td_to_exp_n' in cc.columns:
        win = cc['expiry_n'].map(lambda e: tender_rule('GOLDPETAL', e)['applied_td'])
        cc = cc[cc['td_to_exp_n'] >= win]
    
    # Calendar days difference
    cc['gap_days'] = (cc['expiry_f'] - cc['expiry_n']).dt.days
    cc = cc[cc['gap_days'] > 0]
    
    # Implied annualized carry
    cc['c'] = np.log(cc['px_f'] / cc['px_n']) * 365.0 / cc['gap_days']
    
    # Choose pair with highest min(OI_prev) on t-1
    cc['m'] = np.minimum(cc['oi_prev_n'], cc['oi_prev_f'])
    chosen = cc.loc[cc.groupby('date')['m'].idxmax()].copy().set_index('date')
    chosen['unstable'] = (chosen['c'] < CARRY_SANE_LO) | (chosen['c'] > CARRY_SANE_HI)

    # Build complete daily carry series
    carry_series = pd.Series(index=pd.DatetimeIndex(dates), dtype=float)
    carry_series.loc[chosen.index] = chosen['c']
    carry_series = carry_series.ffill().fillna(DEFAULT_CARRY)
    
    return carry_series, chosen

def compute_carry_decomposition(df: pd.DataFrame, carry_series: pd.Series, chosen_ref: pd.DataFrame) -> pd.DataFrame:
    """
    Computes roll-down vs genuine curve change decomposition per contract (Section 4.3).
    Identity:
    Δln F_i = Δln S_t (gold price move)
            + c_{t-1} * (tau_t - tau_{t-1}) (mechanical roll-down)
            + (c_t - c_{t-1}) * tau_t (genuine curve change)
            + residual (noise)
    """
    # Compute spot proxy S_t from chosen reference GOLDPETAL near contract
    ref_df = chosen_ref[['expiry_n', 'px_n']].copy()
    ref_df['c_t'] = carry_series.reindex(ref_df.index).values
    ref_df['tau_ref'] = (ref_df['expiry_n'] - ref_df.index).dt.days / 365.0
    ref_df['ln_S'] = np.log(ref_df['px_n']) - ref_df['c_t'] * ref_df['tau_ref']
    
    # Align to all dates
    dates_idx = carry_series.index
    spot_series = ref_df['ln_S'].reindex(dates_idx).ffill()
    d_ln_S = spot_series.diff()
    
    c_prev = carry_series.shift(1)
    d_c = carry_series.diff()
    
    decomp_rows = []
    
    # Process each contract
    for (sym, exp), g in df.groupby(['symbol', 'expiry']):
        g = g.sort_values('date').copy()
        g['tau'] = (pd.Timestamp(exp) - g['date']).dt.days / 365.0
        g['ln_F'] = np.log(g['px'])
        g['d_ln_F'] = g['ln_F'].diff()
        
        # Merge series values
        g['d_ln_S'] = g['date'].map(d_ln_S)
        g['c_prev'] = g['date'].map(c_prev)
        g['d_c'] = g['date'].map(d_c)
        g['d_tau'] = g['tau'].diff() # negative as time to expiry shrinks
        
        # Rolldown: c_{t-1} * (tau_t - tau_{t-1})
        g['rolldown'] = g['c_prev'] * g['d_tau']
        # Genuine curve change: (c_t - c_{t-1}) * tau_t
        g['curve_change'] = g['d_c'] * g['tau']
        # Gold move
        g['gold_move'] = g['d_ln_S']
        # Residual
        g['residual'] = g['d_ln_F'] - (g['gold_move'] + g['rolldown'] + g['curve_change'])
        
        # Keep non-empty rows
        valid = g.dropna(subset=['d_ln_F', 'gold_move', 'rolldown', 'curve_change', 'residual'])
        decomp_rows.append(valid[['symbol', 'expiry', 'date', 'px', 'tau', 'd_ln_F', 'gold_move', 'rolldown', 'curve_change', 'residual']])
        
    if decomp_rows:
        return pd.concat(decomp_rows, ignore_index=True)
    return pd.DataFrame()
