"""Attribution and cost calculations according to Section 5.7 and 5.8."""
import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any
from pipeline.config import (
    BROKERAGE_PER_ORDER,
    EXCHANGE_TURNOVER_RATE,
    SEBI_TURNOVER_RATE,
    CTT_RATE,
    STAMP_DUTY_RATE,
    GST_RATE,
    THIN_SLIPPAGE_MULTIPLIER,
)

def calculate_leg_cost(notional: float, side_buy: bool, slip_bps: float, is_thin: bool, n_orders: int = 1) -> float:
    """
    Computes statutory and slippage costs for one leg execution (entry or exit).
    Section 5.7:
    - Brokerage: ₹20 per order
    - Exchange turnover: 0.0021% of notional
    - SEBI fee: ₹10 per crore (0.000001)
    - GST: 18% on (brokerage + exchange + SEBI)
    - CTT: 0.01% on sell side
    - Stamp duty: 0.002% on buy side
    - Slippage: slip_bps (x3 if thin)
    """
    brok = BROKERAGE_PER_ORDER * n_orders
    exch = notional * EXCHANGE_TURNOVER_RATE
    sebi = notional * SEBI_TURNOVER_RATE
    gst = GST_RATE * (brok + exch + sebi)
    ctt = (notional * CTT_RATE) if not side_buy else 0.0
    stamp = (notional * STAMP_DUTY_RATE) if side_buy else 0.0
    
    multiplier = THIN_SLIPPAGE_MULTIPLIER if is_thin else 1.0
    slip = notional * (slip_bps * multiplier) / 10000.0
    
    return brok + exch + sebi + gst + ctt + stamp + slip

def calculate_round_trip_cost_bps(slip_bps: float = 5.0, notional: float = 1_000_000.0) -> float:
    """
    Computes standard round-trip cost in bps across both legs (4 orders total).
    Used in alerts (Section 6) and overview.
    """
    # Leg A: buy + sell
    cost_a = calculate_leg_cost(notional, side_buy=True, slip_bps=slip_bps, is_thin=False) + \
             calculate_leg_cost(notional, side_buy=False, slip_bps=slip_bps, is_thin=False)
    # Leg B: sell + buy
    cost_b = calculate_leg_cost(notional, side_buy=False, slip_bps=slip_bps, is_thin=False) + \
             calculate_leg_cost(notional, side_buy=True, slip_bps=slip_bps, is_thin=False)
             
    total_cost = cost_a + cost_b
    return (total_cost / notional) * 10000.0

def compute_t_stat_and_ci(net_bps_array: np.ndarray, n_boot: int = 5000, seed: int = 0) -> Tuple[float, Tuple[float, float]]:
    """
    Computes 1-sample t-statistic against 0 and bootstrap 95% CI without scipy dependency.
    """
    arr = np.asarray(net_bps_array, dtype=float)
    n = len(arr)
    if n < 2:
        return 0.0, (0.0, 0.0)
        
    mean = np.mean(arr)
    s = np.std(arr, ddof=1)
    if s == 0.0:
        t_stat = 0.0
    else:
        t_stat = mean / (s / np.sqrt(n))
        
    rng = np.random.default_rng(seed)
    # Vectorized bootstrap resampling
    samples = rng.choice(arr, size=(n_boot, n), replace=True)
    boot_means = np.mean(samples, axis=1)
    ci_lower = float(np.percentile(boot_means, 2.5))
    ci_upper = float(np.percentile(boot_means, 97.5))
    
    return float(t_stat), (ci_lower, ci_upper)

def compute_attribution_metrics(trades_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Computes performance and attribution metrics from trades dataframe.
    """
    if trades_df.empty:
        return {
            'n_trades': 0,
            'hit_rate': 0.0,
            'gross_rs': 0.0,
            'cost_rs': 0.0,
            'net_rs': 0.0,
            'spread_rs': 0.0,
            'gold_rs': 0.0,
            'gross_bps': 0.0,
            'net_bps': 0.0,
            'max_drawdown_rs': 0.0,
            'avg_holding_days': 0.0,
            'sharpe_per_trade': 'n/a (too few trades)',
            't_stat': 0.0,
            'ci_95': [0.0, 0.0],
        }
        
    n = len(trades_df)
    hit_rate = float((trades_df['net'] > 0).mean())
    gross_rs = float(trades_df['gross'].sum())
    cost_rs = float(trades_df['cost'].sum())
    net_rs = float(trades_df['net'].sum())
    spread_rs = float(trades_df['spread_pnl'].sum())
    gold_rs = float(trades_df['gold'].sum())
    gross_bps = float(trades_df['gross_bps'].mean())
    net_bps = float(trades_df['net_bps'].mean())
    avg_days = float(trades_df['days'].mean())
    
    # Closed-trade equity curve for max drawdown, in exit order, starting from zero
    # (fix: the old curve started at the first trade, so an opening loss was not counted)
    ordered = trades_df.sort_values('exit') if 'exit' in trades_df.columns else trades_df
    cum_net = np.concatenate([[0.0], ordered['net'].cumsum().values])
    cum_max = np.maximum.accumulate(cum_net)
    drawdowns = cum_max - cum_net
    max_dd = float(drawdowns.max()) if len(drawdowns) else 0.0
    
    # Per-trade mean / standard deviation of net bps (n >= 20). Deliberately NOT annualised: trades overlap and have
    # different lengths, so this is not a daily portfolio Sharpe ratio (that one is in portfolio.json, Oct-2026 audit).
    if n >= 20:
        std_bps = trades_df['net_bps'].std(ddof=1)
        sharpe = round(net_bps / std_bps, 3) if std_bps > 0 else 0.0
    else:
        sharpe = 'n/a (too few trades)'
        
    t_stat, ci = compute_t_stat_and_ci(trades_df['net_bps'].values)
    
    return {
        'n_trades': n,
        'hit_rate': round(hit_rate, 3),
        'gross_rs': round(gross_rs, 1),
        'cost_rs': round(cost_rs, 1),
        'net_rs': round(net_rs, 1),
        'spread_rs': round(spread_rs, 1),
        'gold_rs': round(gold_rs, 1),
        'gross_bps': round(gross_bps, 1),
        'net_bps': round(net_bps, 1),
        'max_drawdown_rs': round(max_dd, 1),
        'avg_holding_days': round(avg_days, 1),
        'sharpe_per_trade': sharpe,
        't_stat': round(t_stat, 2),
        'ci_95': [round(ci[0], 1), round(ci[1], 1)],
    }
