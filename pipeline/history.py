"""Long-history check: the frozen rule on 2011-2023, years the model never saw.

Source: an MCX Gold Futures History Book (official MCX Bhavcopy rows,
shared with us with their permission), saved as data/raw/mcx_history_book.csv.

What it does
  1. Compares the book with our own MCX download on every day both cover (Oct 2023 - Sep 2026).
  2. Takes the settings the main build chose on our training years (read from its backtest files,
     so nothing is re-tuned) and runs the same five-check rule, with the same costs,
     on 18 Apr 2011 (first GOLDPETAL day) to the day before our own data starts.
  3. Writes frontend/public/data/history.json for the website.

Only the three pairs that existed back then can be tested: GOLDTEN started in March 2025.
"""
import json
import os
import tempfile
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from pipeline.config import ALERT_RULE, BASE_SLIPPAGE, SLIPPAGE_SCENARIOS
from pipeline.load import load_clean_bhavcopy
from pipeline.carry import compute_reference_carry
from pipeline.pairs import build_pair_series, compute_rolling_z
from pipeline.backtest import prepare_contract_lookup, run_pair_backtest
from pipeline.lifecycle import compute_contract_lifecycle, calendar_check

BOOK_PATH = 'data/raw/mcx_history_book.csv'
OURS_PATH = 'data/raw/gold_bhavcopy_clean.csv'
HISTORY_START = '2011-04-18'          # first trading day of GOLDPETAL, so all three contracts exist
HISTORY_PAIRS = ['M_PETAL', 'M_GUINEA', 'GUINEA_PETAL']
SOURCE = {
    'name': 'MCX Gold Futures History Book',
    'by': 'another team, shared with permission',
    'note': 'Official MCX Bhavcopy rows, shared with us with their permission. Thank you!',
}
CHECK_FIELDS = [('open', 'open'), ('high', 'high'), ('low', 'low'), ('close', 'close'),
                ('prev_close', 'prev_close'), ('volume', 'volume_lots'), ('oi', 'open_interest_lots'),
                ('value_lakh', 'value_lakhs')]


def load_book(path: str = BOOK_PATH) -> pd.DataFrame:
    b = pd.read_csv(path, parse_dates=['date', 'expiry'])
    for c in ['open', 'high', 'low', 'close', 'prev_close', 'volume', 'oi', 'value_lakh']:
        b[c] = pd.to_numeric(b[c], errors='coerce')
    return b


QUOTE = {'GOLDM': (10, 0.995), 'GOLDTEN': (10, 0.999), 'GOLDGUINEA': (8, 0.999), 'GOLDPETAL': (1, 0.999)}


def long_series(book: pd.DataFrame, end: pd.Timestamp) -> Dict[str, Any]:
    """Weekly price of 10 g of pure gold per contract, before our own data starts (for the long charts).
    Each day uses the contract with the most open interest that traded; each week keeps its last trading day."""
    b = book[(book['date'] <= end) & (book['traded'] == 'yes')].copy()
    b['p10'] = [c / QUOTE[s][0] / QUOTE[s][1] * 10 for c, s in zip(b['close'], b['symbol'])]
    best = b.sort_values('oi').groupby(['symbol', 'date']).tail(1)
    best['week'] = best['date'].dt.to_period('W-FRI')
    last = best.sort_values('date').groupby(['symbol', 'week']).tail(1)
    wide = last.pivot_table(index='week', columns='symbol', values='p10', aggfunc='last')
    days = last.groupby('week')['date'].max()
    out: Dict[str, Any] = {'d': [days[w].strftime('%Y-%m-%d') for w in wide.index]}
    for sym in ['GOLDM', 'GOLDTEN', 'GOLDGUINEA', 'GOLDPETAL']:
        col = wide[sym] if sym in wide else pd.Series(index=wide.index, dtype=float)
        out[sym] = [None if pd.isna(v) else int(round(v)) for v in col]
    return out


def tstat(x) -> Optional[float]:
    x = pd.Series(x, dtype=float)
    if len(x) < 3 or x.std(ddof=1) == 0:
        return None
    return round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2)


def cross_check(book: pd.DataFrame, ours: pd.DataFrame) -> Dict[str, Any]:
    """Every row both sources share, compared field by field."""
    o = ours.rename(columns={'expiry_date': 'expiry'})
    lo, hi = o['date'].min(), o['date'].max()
    b = book[(book['date'] >= lo) & (book['date'] <= hi)]
    m = o.merge(b, on=['symbol', 'expiry', 'date'], how='outer', suffixes=('_o', '_b'), indicator=True)
    both = m[m['_merge'] == 'both']
    traded = both[both['traded'] == 'yes']
    mism = 0
    for bf, of in CHECK_FIELDS:
        a = both if bf not in ('open', 'high', 'low') else traded   # no-trade days have no open/high/low in the book
        ca = a[bf + '_b'] if bf + '_b' in a else a[bf]
        cb = a[of + '_o'] if of + '_o' in a else a[of]
        mism += int(((ca - cb).abs() > 0.011).sum())
    only_book = m[m['_merge'] == 'right_only']
    return {
        'from': lo.strftime('%Y-%m-%d'), 'to': hi.strftime('%Y-%m-%d'),
        'shared_rows': int(len(both)), 'mismatches': mism,
        'fields': [f for f, _ in CHECK_FIELDS],
        'only_in_book': int(len(only_book)),
        'only_in_book_contracts': int(only_book.groupby(['symbol', 'expiry']).ngroups),
        'only_in_ours': int((m['_merge'] == 'left_only').sum()),
    }


def frozen_params(output_dir: str) -> Dict[str, Dict[str, float]]:
    """Settings the main build chose on training, read from its backtest files (nothing is re-tuned)."""
    out = {}
    for pid in HISTORY_PAIRS:
        with open(os.path.join(output_dir, f'backtest/{pid}_{BASE_SLIPPAGE}.json'), encoding='utf-8') as f:
            p = json.load(f)['params']
        out[pid] = {k: p[k] for k in ('W', 'ze', 'mh')}
    return out


def history_frame(book: pd.DataFrame, end: pd.Timestamp):
    """The book's rows before our own data starts, loaded and cleaned exactly like our own download."""
    h = book[(book['date'] >= '2011-01-01') & (book['date'] <= end) & (book['symbol'] != 'GOLDTEN')]
    clean = pd.DataFrame({
        'date': h['date'].dt.strftime('%Y-%m-%d'), 'symbol': h['symbol'], 'expiry_date': h['expiry'].dt.strftime('%Y-%m-%d'),
        'open': h['open'].fillna(0), 'high': h['high'].fillna(0), 'low': h['low'].fillna(0),
        'close': h['close'], 'prev_close': h['prev_close'], 'volume_lots': h['volume'],
        'value_lakhs': h['value_lakh'], 'open_interest_lots': h['oi'],
    })
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'history_clean.csv')
        clean.to_csv(path, index=False)
        df, dates, tdi = load_clean_bhavcopy(path)
    carry, _ = compute_reference_carry(df, dates)
    return df, dates, tdi, carry


def run_history(book: pd.DataFrame, end: pd.Timestamp, params: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    """Same rule, same costs, frozen settings, on the book's rows before our own data starts."""
    df, dates, tdi, carry = history_frame(book, end)
    P = prepare_contract_lookup(df)
    start = pd.Timestamp(HISTORY_START)
    out = []
    for pid in HISTORY_PAIRS:
        W, ze, mh = int(params[pid]['W']), float(params[pid]['ze']), int(params[pid]['mh'])
        ps = build_pair_series(df, pid, carry)
        for slip in SLIPPAGE_SCENARIOS:
            t = run_pair_backtest(pid, ps, P, dates, tdi, W, ze, mh, slip_bps=slip, rule=ALERT_RULE)
            if len(t):
                t = t[t['entry'] >= start].copy()
                t['pair'], t['slip'] = pid, slip
                out.append(t)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def r1(v):
    return None if v is None or pd.isna(v) else round(float(v), 1)


def chart_data(book: pd.DataFrame, end: pd.Timestamp, params: Dict[str, Dict[str, float]], T: pd.DataFrame) -> Dict[str, Any]:
    """Daily pair series and every clean-test trade, 2011-2023, so the site's charts can show the whole study.
    Same series, same rolling window and same trades as the clean test above (nothing re-tuned)."""
    df, dates, tdi, carry = history_frame(book, end)
    start = pd.Timestamp(HISTORY_START)
    out: Dict[str, Any] = {'from': HISTORY_START, 'to': end.strftime('%Y-%m-%d'), 'pairs': {}}
    for pid in HISTORY_PAIRS:
        ps = compute_rolling_z(build_pair_series(df, pid, carry), W=int(params[pid]['W']))
        ps = ps[ps['date'] >= start]
        tr = {}
        for slip in SLIPPAGE_SCENARIOS:
            a = T[(T['pair'] == pid) & (T['slip'] == slip)].sort_values('exit')
            tr[str(slip)] = [[pd.Timestamp(t['sig']).strftime('%Y-%m-%d'), pd.Timestamp(t['entry']).strftime('%Y-%m-%d'),
                              pd.Timestamp(t['exit']).strftime('%Y-%m-%d'), int(t['side']), round(float(t['z']), 2),
                              round(float(t['net'])), round(float(t['gross'])), round(float(t['net_bps']), 1), t['reason'], int(t['days']),
                              round(float(t['gross_bps']), 1), round(float(t['spread_pnl'])), round(float(t['gold'])), round(float(t['cost'])),
                              pd.Timestamp(t['expA']).strftime('%Y-%m-%d'), pd.Timestamp(t['expB']).strftime('%Y-%m-%d'), int(t['grams']),
                              round(float(t['cost_entry']), 2), round(float(t['cost_exit']), 2), str(t['lifecycle']), bool(t['forced_fill'])]
                             for _, t in a.iterrows()]
        out['pairs'][pid] = {
            'd': [d.strftime('%Y-%m-%d') for d in ps['date']], 's': [r1(v) for v in ps['spread']],
            'mu': [r1(v) for v in ps['mu']], 'sd': [r1(v) for v in ps['sd']],
            'trades': tr,     # [signal, entry, exit, side, z, net Rs, gross Rs, net bps, reason, days held,
                          #  gross bps, spread P&L Rs, gold P&L Rs, costs Rs, expiry A, expiry B, grams,
                          #  entry costs Rs, exit costs Rs, lifecycle status, forced exit fill], by slippage
        }
    # weekly replay frames (Today page): each week's biggest |spread - normal| per pair, and whether a trade signalled,
    # cut into 5-trading-day blocks ending on the last history day, like the replay of our own data
    days = [d.strftime('%Y-%m-%d') for d in pd.to_datetime(dates) if d >= start]
    dev = {pid: {d: abs(s - m) for d, s, m in zip(out['pairs'][pid]['d'], out['pairs'][pid]['s'], out['pairs'][pid]['mu'])
                 if s is not None and m is not None} for pid in HISTORY_PAIRS}
    sigs = {pid: {t[0] for t in out['pairs'][pid]['trades'][str(BASE_SLIPPAGE)]} for pid in HISTORY_PAIRS}
    ends = list(range(len(days) - 1, -1, -5))[::-1]
    rf, rd, rs = [], [], []
    for k, i in enumerate(ends):
        block = days[(ends[k - 1] + 1 if k else 0):i + 1]
        rf.append([round(max(xs), 1) if (xs := [dev[p][d] for d in block if d in dev[p]]) else None for p in HISTORY_PAIRS])
        rs.append([1 if any(d in sigs[p] for d in block) else 0 for p in HISTORY_PAIRS])
        rd.append(days[i])
    out['replay'] = {'ids': HISTORY_PAIRS, 'd': rd, 'f': rf, 'sig': rs}
    out['tradeFields'] = ['sig', 'entry', 'exit', 'side', 'z', 'net', 'gross', 'net_bps', 'reason', 'days',
                          'gross_bps', 'spread_pnl', 'gold', 'cost', 'expA', 'expB', 'grams', 'cost_entry', 'cost_exit',
                          'lifecycle', 'forced_fill']
    return out


def summarise(T: pd.DataFrame) -> Dict[str, Any]:
    by_slip = {}
    for slip in SLIPPAGE_SCENARIOS:
        a = T[T['slip'] == slip]
        by_slip[str(slip)] = {
            'n': int(len(a)), 'net_rs': round(float(a['net'].sum()), 1),
            'avg_bps': round(float(a['net_bps'].mean()), 1) if len(a) else None,
            'gross_bps': round(float(a['gross_bps'].mean()), 1) if len(a) else None,
            'hit': round(float((a['net'] > 0).mean()), 3) if len(a) else None,
            't': tstat(a['net_bps']),
        }
    a = T[T['slip'] == BASE_SLIPPAGE].copy()
    a['year'] = pd.to_datetime(a['entry']).dt.year
    years = [{'year': int(y), 'n': int(len(g)), 'net_rs': round(float(g['net'].sum()), 1),
              'avg_bps': round(float(g['net_bps'].mean()), 1)} for y, g in a.groupby('year')]
    pairs = {pid: {'n': int(len(g)), 'net_rs': round(float(g['net'].sum()), 1),
                   'avg_bps': round(float(g['net_bps'].mean()), 1), 'gross_bps': round(float(g['gross_bps'].mean()), 1),
                   'hit': round(float((g['net'] > 0).mean()), 3), 't': tstat(g['net_bps'])}
             for pid, g in a.groupby('pair')}
    ranked = a.sort_values('net', ascending=False)
    worst = a.sort_values('net').iloc[0] if len(a) else None
    return {
        'by_slip': by_slip, 'years': years, 'pairs': pairs,
        'years_positive': int(sum(1 for y in years if y['net_rs'] > 0)), 'years_count': len(years),
        'without_best5_rs': round(float(ranked['net'].iloc[5:].sum()), 1) if len(a) > 5 else None,
        'reverted_share': round(float((a['reason'] == 'revert').mean()), 3) if len(a) else None,
        'worst': None if worst is None else {
            'pair': worst['pair'], 'entry': pd.Timestamp(worst['entry']).strftime('%Y-%m-%d'),
            'exit': pd.Timestamp(worst['exit']).strftime('%Y-%m-%d'), 'net_rs': round(float(worst['net']), 1),
            'reason': worst['reason']},
    }


def build(output_dir: str = 'frontend/public/data', book_path: str = BOOK_PATH, ours_path: str = OURS_PATH) -> Dict[str, Any]:
    book = load_book(book_path)
    ours = pd.read_csv(ours_path, parse_dates=['date', 'expiry_date'])
    end = ours['date'].min() - pd.Timedelta(days=1)
    params = frozen_params(output_dir)
    T = run_history(book, end, params)
    cov = {s: {'first': g['date'].min().strftime('%Y-%m-%d'), 'last': g['date'].max().strftime('%Y-%m-%d'),
               'rows': int(len(g)), 'contracts': int(g['expiry'].nunique())} for s, g in book.groupby('symbol')}
    # data quality on the book's clean-test window, measured the same way as on our own download
    hdf_all = history_frame(book, end)[0]
    hdf = hdf_all[hdf_all['date'] >= pd.Timestamp(HISTORY_START)]
    # every clean-test trade checked against its contracts' calendars, the same check as our own download's trades
    calendar = calendar_check(T[T['slip'] == BASE_SLIPPAGE], compute_contract_lifecycle(hdf_all)) if len(T) else None
    quality = {'no_trade': int(hdf['no_trade'].sum()), 'thin': int(hdf['thin'].sum()),   # same definitions as meta.json
               'weekend': sorted({d.strftime('%Y-%m-%d') for d in hdf['date'] if d.weekday() >= 5})}
    res = {
        'source': dict(SOURCE, rows=int(len(book)), contracts=int(book.groupby(['symbol', 'expiry']).ngroups),
                       first=book['date'].min().strftime('%Y-%m-%d'), last=book['date'].max().strftime('%Y-%m-%d'),
                       coverage=cov),
        'check': cross_check(book, ours),
        'window': {'from': HISTORY_START, 'to': end.strftime('%Y-%m-%d'), 'pairs': HISTORY_PAIRS, 'params': params,
                   'slip': BASE_SLIPPAGE,
                   'rows': int(((book['date'] >= HISTORY_START) & (book['date'] <= end)).sum()),   # book prices the clean test ran on
                   'contracts': [f"{s}|{e.strftime('%Y-%m-%d')}" for s, e in sorted(set(zip(
                       book.loc[(book['date'] >= HISTORY_START) & (book['date'] <= end), 'symbol'],
                       book.loc[(book['date'] >= HISTORY_START) & (book['date'] <= end), 'expiry'])))],
                   'days': int(book.loc[(book['date'] >= HISTORY_START) & (book['date'] <= end), 'date'].nunique())},
        'result': summarise(T) if len(T) else None,
        'quality': quality,
        'calendar': calendar,
        'long': long_series(book, end),
    }
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, 'history.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, indent=2)
    # charts: kept in their own file so pages that only need the summary stay light
    with open(os.path.join(output_dir, 'history_charts.json'), 'w', encoding='utf-8') as f:
        json.dump(chart_data(book, end, params, T), f, separators=(',', ':'))
    return res


if __name__ == '__main__':
    r = build()
    s = r['result']['by_slip'][str(BASE_SLIPPAGE)]
    print('check:', r['check'])
    print(f"history {r['window']['from']}..{r['window']['to']}: {s['n']} trades, net Rs {s['net_rs']:,.0f}, t {s['t']}")
