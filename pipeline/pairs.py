"""Pair series construction and rolling point-in-time z-scores (Sections 4.4 and 4.5)."""
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
from pipeline.config import PAIR_DEFINITIONS, PAIRS

def build_pair_series(df: pd.DataFrame, 
                      pair_id: str, 
                      carry_series: pd.Series) -> pd.DataFrame:
    """
    Constructs the point-in-time daily pair series for pair_id.
    Selects contracts on date t using highest min(OI_A, OI_B) as of t-1.
    Computes carry-adjusted spread in bps.
    """
    sym_a, sym_b, maxgap = PAIR_DEFINITIONS[pair_id]
    
    cols = ['date', 'expiry', 'close', 'px', 'px_per_10g_pure', 'vol', 'oi', 'oi_prev', 'no_trade', 'thin', 'td_to_exp']
    A = df[df['symbol'] == sym_a][cols].copy()
    B = df[df['symbol'] == sym_b][cols].copy()
    
    # Merge candidates on date
    m = A.merge(B, on='date', suffixes=('_a', '_b'))
    m['gap'] = (m['expiry_a'] - m['expiry_b']).dt.days
    
    # Expiry gap rule
    if maxgap == 0:
        m = m[m['gap'] == 0]
    else:
        m = m[m['gap'].abs() <= maxgap]
        
    # Neither leg can be no_trade_day, and both must have t-1 OI known
    m = m[~m['no_trade_a'] & ~m['no_trade_b']].dropna(subset=['oi_prev_a', 'oi_prev_b'])
    
    if m.empty:
        return pd.DataFrame()
        
    # Choose combination with highest min(OI_a, OI_b) as of t-1
    m['m_oi'] = np.minimum(m['oi_prev_a'], m['oi_prev_b'])
    chosen = m.loc[m.groupby('date')['m_oi'].idxmax()].sort_values('date').reset_index(drop=True)
    
    # Reference carry aligned to date
    chosen['c'] = carry_series.reindex(chosen['date']).values
    
    # Carry-adjusted spread in bps (Section 4.4)
    # spread_bps = (px_A / px_B - 1 - c_t * gap_days / 365) * 10,000
    chosen['spread'] = (chosen['px_a'] / chosen['px_b'] - 1.0 - chosen['c'] * chosen['gap'] / 365.0) * 1e4
    chosen['spread_bps'] = chosen['spread']
    
    # Carry-adjusted spread in ₹ per 10g pure: spread_bps / 10000 * px_b * 10
    chosen['spread_rs_10g'] = (chosen['spread_bps'] / 10000.0) * chosen['px_b'] * 10.0
    
    # Roll flag: true when chosen contract changes
    chosen['roll'] = (chosen['expiry_a'] != chosen['expiry_a'].shift(1)) | (chosen['expiry_b'] != chosen['expiry_b'].shift(1))
    chosen.loc[0, 'roll'] = False
    chosen['roll_flag'] = chosen['roll']
    
    return chosen

def rolling_stats(pair_df: pd.DataFrame, W: int, gap_days: Optional[int] = None) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """The one rolling-statistics definition used by the alerts, the charts and the backtest (Section 4.5).

    mu_t = mean(spread_{t-W} ... spread_{t-1}),  sd_t = std (ddof=1) of the same window,  z_t = (spread_t - mu_t) / sd_t.
    Day t is never in its own window (shift(1)), so nothing from the future is used.
    Policy (config.ROLLING_GAP_DAYS): a gap of more than gap_days calendar days between observations starts a new
    window; the window otherwise runs across contract rolls. gap_days=-1 disables the gap rule (reference study only).
    """
    from pipeline.config import ROLLING_GAP_DAYS
    gap = ROLLING_GAP_DAYS if gap_days is None else gap_days
    s = pair_df['spread']
    breaks = (pair_df['date'].diff().dt.days > gap).fillna(False) if gap_days != -1 else pd.Series(False, index=s.index)
    if breaks.any():
        g = breaks.cumsum()
        mu = s.groupby(g).transform(lambda v: v.rolling(W, min_periods=W).mean().shift(1))
        sd = s.groupby(g).transform(lambda v: v.rolling(W, min_periods=W).std().shift(1))
    else:
        mu = s.rolling(W, min_periods=W).mean().shift(1)
        sd = s.rolling(W, min_periods=W).std().shift(1)
    return mu, sd, (s - mu) / sd


def compute_rolling_z(pair_df: pd.DataFrame, W: int = 20) -> pd.DataFrame:
    """Adds mu, sd and z (rolling_stats) to a copy of the pair series."""
    df = pair_df.copy()
    df['mu'], df['sd'], df['z'] = rolling_stats(df, W)
    return df

def build_all_pairs(df: pd.DataFrame, carry_series: pd.Series) -> Dict[str, pd.DataFrame]:
    """Builds base pair series for all 6 pairs."""
    return {pair_id: build_pair_series(df, pair_id, carry_series) for pair_id in PAIR_DEFINITIONS}
