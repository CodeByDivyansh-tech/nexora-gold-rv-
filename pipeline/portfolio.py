"""Portfolio-level reporting (Oct-2026 compliance audit, Priority 6): every trade marked to market each day.

What it does
  Each trade (all six pairs, 2011 to today, at BASE_SLIPPAGE) is valued every trading day from the settlement
  closes of the two exact contracts it held. Entry costs are booked on the entry day, exit costs on the exit day.
  Summing all trades gives one daily portfolio P&L, so overlapping positions in different pairs are counted together
  (and are not treated as independent bets).

Capital basis (stated, not invented)
  Positions are sized at about NOTIONAL_PER_LEG of gold per leg. P&L is reported in rupees. The only denominator
  used is gross notional (both legs, all open trades); margin is not modelled because historical MCX margin rates
  were not collected. A return on gross notional is NOT a return on capital.

Statistics
  Daily Sharpe = mean / sd of daily P&L x sqrt(252), over every trading day in the period (flat days count as 0).
  Because P&L is in rupees, this equals the Sharpe of daily returns on any FIXED capital amount.
  Significance uses a Newey-West (HAC) t-statistic on daily P&L, so autocorrelation from multi-day and overlapping
  positions is allowed for. Trade-level figures (win rate, bps per trade) are kept separate and labelled as such.

Gold benchmark: GOLDM, the contract with the most open interest the day before, close-to-close in the same contract
(so a roll is not counted as a price move); per gram of pure gold.

Writes frontend/public/data/portfolio.json.
"""
import json
import os
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from pipeline.config import BASE_SLIPPAGE, NOTIONAL_PER_LEG, PAIR_DEFINITIONS, TEST_END, TEST_START, TRAIN_END, TRAIN_START

HAC_LAGS = 10            # trading days (the longest holding limit in the settings grid is 10-20 days)


def _closes(P: pd.DataFrame, sym: str, exp: pd.Timestamp, days: List[pd.Timestamp]) -> pd.Series:
    """Settlement close of one contract on each day (last known close carried forward on a missing day)."""
    try:
        s = P.loc[(sym, exp)]['close']
    except KeyError:
        return pd.Series(np.nan, index=days)
    return s.reindex(days).ffill()


def daily_trade_pnl(trades: List[Dict[str, Any]], P: pd.DataFrame, dates: np.ndarray) -> pd.DataFrame:
    """One row per (trade, day held): gross mark-to-market, gold part, costs, open notional.

    trades: dicts with pair, entry, exit, side, grams, expA, expB, cost_entry, cost_exit (dates as Timestamps)."""
    tdi = {pd.Timestamp(d): i for i, d in enumerate(dates)}
    out = []
    for k, t in enumerate(trades):
        a, b, _ = PAIR_DEFINITIONS[t['pair']]
        i0, i1 = tdi[pd.Timestamp(t['entry'])], tdi[pd.Timestamp(t['exit'])]
        days = [pd.Timestamp(d) for d in dates[i0:i1 + 1]]
        ca = _closes(P, a, pd.Timestamp(t['expA']), days)
        cb = _closes(P, b, pd.Timestamp(t['expB']), days)
        ra = P.loc[(a, pd.Timestamp(t['expA']), days[0])]
        rb = P.loc[(b, pd.Timestamp(t['expB']), days[0])]
        qa, qb = float(ra['quote_grams']), float(rb['quote_grams'])
        pa, pb = float(ra['purity']), float(rb['purity'])
        side, g = float(t['side']), float(t['grams'])
        # same attribution as the backtest: gold part = net pure grams x change in leg B's pure-gold price
        net_pure = side * g * pa - side * g * pb
        pxb = cb / qb / pb
        da, db = ca.diff().fillna(0.0), cb.diff().fillna(0.0)
        gross = side * g * da / qa - side * g * db / qb
        gold = net_pure * pxb.diff().fillna(0.0)
        cost = pd.Series(0.0, index=days)
        cost.iloc[0] += float(t['cost_entry'])
        cost.iloc[-1] += float(t['cost_exit'])
        notional = g * (ca / qa + cb / qb)          # both legs, at that day's close
        held = pd.Series(1.0, index=days)
        held.iloc[0] = 0.0                           # opened at the entry close: no overnight exposure that day
        for j, d in enumerate(days):
            out.append((k, d, float(gross.iloc[j]), float(gold.iloc[j]), float(cost.iloc[j]),
                        float(notional.iloc[j]) * held.iloc[j], held.iloc[j]))
    return pd.DataFrame(out, columns=['trade', 'date', 'gross', 'gold', 'cost', 'gross_notional', 'open'])


def gold_benchmark(df: pd.DataFrame) -> pd.Series:
    """Daily GOLDM return, same contract close-to-close; the contract is the one with the most OI the day before."""
    g = df[df['symbol'] == 'GOLDM'][['date', 'expiry', 'close', 'oi_prev']].dropna(subset=['oi_prev'])
    pick = g.loc[g.groupby('date')['oi_prev'].idxmax()].set_index('date')
    full = df[df['symbol'] == 'GOLDM'].set_index(['expiry', 'date'])['close']
    rets = {}
    for d, r in pick.iterrows():
        s = full.loc[r['expiry']]
        prev = s[s.index < d]
        if len(prev):
            rets[d] = r['close'] / prev.iloc[-1] - 1.0
    return pd.Series(rets).sort_index()


def nw_tstat(x: np.ndarray, lags: int = HAC_LAGS) -> float:
    """Newey-West t-statistic for the mean of x (Bartlett weights)."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 3 or np.allclose(x, 0):
        return float('nan')
    e = x - x.mean()
    v = e @ e / n
    for L in range(1, min(lags, n - 1) + 1):
        v += 2 * (1 - L / (lags + 1)) * (e[L:] @ e[:-L]) / n
    return float(x.mean() / np.sqrt(v / n)) if v > 0 else float('nan')


def summarise(day: pd.DataFrame, trades: List[Dict[str, Any]], gold: pd.Series, start: str, end: str) -> Dict[str, Any]:
    """Portfolio figures for [start, end], every trading day counted (flat days = 0)."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    d = day[(day.index >= s) & (day.index <= e)]
    tr = [t for t in trades if s <= pd.Timestamp(t['entry']) <= e]
    if not len(d):
        return {'days': 0, 'n_trades': len(tr)}
    pnl = d['net'].values
    cum = np.cumsum(pnl)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum)) if len(cum) else 0.0
    sd = float(np.std(pnl, ddof=1)) if len(pnl) > 1 else 0.0
    g = gold.reindex(d.index)
    both = pd.DataFrame({'p': d['net'], 'g': g}).dropna()
    corr = float(both['p'].corr(both['g'])) if len(both) > 2 and both['p'].std() > 0 else None
    beta = float(np.cov(both['p'], both['g'])[0, 1] / np.var(both['g'], ddof=1)) if len(both) > 2 and both['g'].var() > 0 else None
    peak = float(d['gross_notional'].max())
    wins = sum(1 for t in tr if t['net'] > 0)
    r = lambda v: None if v is None or not np.isfinite(v) else round(float(v), 3)
    return {
        'from': d.index[0].strftime('%Y-%m-%d'), 'to': d.index[-1].strftime('%Y-%m-%d'), 'days': int(len(d)),
        'n_trades': len(tr), 'wins': wins,
        'win_rate': round(wins / len(tr), 3) if tr else None,          # denominator: trades entered in the period
        'gross_rs': round(float(d['gross'].sum()), 1), 'cost_rs': round(float(d['cost'].sum()), 1),
        'net_rs': round(float(d['net'].sum()), 1),
        'gold_part_rs': round(float(d['gold'].sum()), 1), 'spread_part_rs': round(float(d['gross'].sum() - d['gold'].sum()), 1),
        'max_drawdown_rs': round(dd, 1),
        'sharpe_daily_annualised': r(pnl.mean() / sd * np.sqrt(252)) if sd > 0 else None,
        'nw_t': r(nw_tstat(pnl)),
        'days_with_position': int((d['open'] > 0).sum()),
        'max_open_trades': int(d['open'].max()),
        'days_two_or_more_open': int((d['open'] >= 2).sum()),
        'peak_gross_notional_rs': round(peak, 0),
        'net_on_peak_gross_notional_pct': round(float(d['net'].sum()) / peak * 100, 2) if peak > 0 else None,
        'gold_return_pct': round(float((1 + g.fillna(0)).prod() - 1) * 100, 1),
        'corr_daily_pnl_gold': r(corr), 'beta_rs_per_gold_return': round(beta, 0) if beta is not None and np.isfinite(beta) else None,
    }


def build(output_dir: str = 'frontend/public/data') -> Dict[str, Any]:
    from pipeline.backtest import prepare_contract_lookup
    from pipeline.history import BOOK_PATH, HISTORY_START, OURS_PATH, history_frame, load_book
    from pipeline.load import load_clean_bhavcopy

    J = lambda p: json.load(open(os.path.join(output_dir, p), encoding='utf-8'))
    df, dates, _ = load_clean_bhavcopy(OURS_PATH)
    P = prepare_contract_lookup(df)
    book = load_book(BOOK_PATH)
    end = pd.Timestamp(dates[0]) - pd.Timedelta(days=1)
    hdf, hdates, _, _ = history_frame(book, end)
    HP = prepare_contract_lookup(hdf)
    hdates = np.array([d for d in hdates if pd.Timestamp(d) >= pd.Timestamp(HISTORY_START)])

    hc = J('history_charts.json')
    f = hc['tradeFields']
    ix = {k: f.index(k) for k in f}
    clean = [dict(pair=p, entry=pd.Timestamp(t[ix['entry']]), exit=pd.Timestamp(t[ix['exit']]), side=t[ix['side']],
                  grams=t[ix['grams']], expA=t[ix['expA']], expB=t[ix['expB']], cost_entry=t[ix['cost_entry']],
                  cost_exit=t[ix['cost_exit']], net=t[ix['net']])
             for p in hc['pairs'] for t in hc['pairs'][p]['trades'][str(BASE_SLIPPAGE)]]
    ours = []
    for p in PAIR_DEFINITIONS:
        for t in J(f'backtest/{p}_{BASE_SLIPPAGE}.json')['trades']:
            ours.append(dict(pair=p, entry=pd.Timestamp(t['entry']), exit=pd.Timestamp(t['exit']), side=t['side'],
                             grams=t['grams'], expA=t['expA'], expB=t['expB'], cost_entry=t['cost_entry'],
                             cost_exit=t['cost_exit'], net=t['net']))

    parts = []
    for trades, PP, dd in ((clean, HP, hdates), (ours, P, dates)):
        rows = daily_trade_pnl(trades, PP, dd)
        day = rows.groupby('date')[['gross', 'gold', 'cost', 'gross_notional', 'open']].sum()
        day = day.reindex(pd.DatetimeIndex(dd)).fillna(0.0)
        parts.append(day)
    day = pd.concat(parts)
    day['net'] = day['gross'] - day['cost']
    gold = pd.concat([gold_benchmark(hdf[hdf['date'] >= HISTORY_START]), gold_benchmark(df)]).sort_index()
    gold = gold[~gold.index.duplicated()]
    trades = clean + ours

    periods = {
        'clean': (HISTORY_START, end.strftime('%Y-%m-%d')),
        'train': (TRAIN_START, TRAIN_END), 'test': (TEST_START, TEST_END),
        'forward': ((pd.Timestamp(TEST_END) + pd.Timedelta(days=1)).strftime('%Y-%m-%d'), pd.Timestamp(dates[-1]).strftime('%Y-%m-%d')),
        'all': (HISTORY_START, pd.Timestamp(dates[-1]).strftime('%Y-%m-%d')),
    }
    out = {
        'slip_bps': BASE_SLIPPAGE, 'notional_per_leg_rs': NOTIONAL_PER_LEG, 'hac_lags': HAC_LAGS,
        'basis': ('P&L in rupees. Each trade holds about ₹{:,} of gold per leg (equal grams on both legs). '
                  'The only denominator shown is gross notional (both legs of every open trade); margin is not modelled, '
                  'so no return on capital is reported.').format(NOTIONAL_PER_LEG),
        'periods': {k: summarise(day, trades, gold, a, b) for k, (a, b) in periods.items()},
        # daily series for the chart (rupees, rounded): portfolio cumulative net, gold cumulative return %, open trades
        'daily': {'d': [x.strftime('%Y-%m-%d') for x in day.index],
                  'cum': [round(v) for v in day['net'].cumsum()],
                  'gold_cum_pct': [round(v, 2) for v in ((1 + gold.reindex(day.index).fillna(0)).cumprod() - 1) * 100],
                  'open': [int(v) for v in day['open']]},
        'check': {'trades': len(trades),
                  'sum_of_daily_net_rs': round(float(day['net'].sum()), 1),
                  'sum_of_trade_net_rs': round(float(sum(t['net'] for t in trades)), 1)},
    }
    with open(os.path.join(output_dir, 'portfolio.json'), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, separators=(',', ':'), ensure_ascii=False)
    return out


if __name__ == '__main__':
    o = build()
    print(json.dumps(o['periods'], indent=1))
    print(o['check'])
