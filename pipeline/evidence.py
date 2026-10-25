"""How much weight each result can bear (added after the Oct-2026 review).

Writes frontend/public/data/evidence.json with four parts:

1. test_year: the 2025-26 test year was looked at before the five-check rule was
   written (the original study's results were known first), so it is not a clean
   out-of-sample test. The 2011-2023 check is: the rule was frozen before that data
   was used. Dates come from config.py.
2. slippage: what daily (EOD) data can and cannot say about slippage.
   - Floor: half a tick per order, from the tick size in config.py.
   - Two standard spread estimators run on the daily highs, lows and closes
     (Roll 1984 on each contract's close-to-close changes; Corwin & Schultz 2012 on
     two-day high/low ranges). On liquid futures that move ~1% a day both are far
     noisier than a spread of a few bps, so they mostly return zero.
   - Trade size against that day's traded volume, for every backtest trade.
   - Break-even slippage for training, the test year and 2011-2023. Each trade set is
     fixed (the cost line is set at the 5 bps base), and slippage is a fixed share of
     notional, so net P&L is a straight line in slippage; we check that, then solve.
3. multiple_testing: how many rule versions were scored on the test year, and the
   test-year p-value with a Bonferroni adjustment for that count.
4. switch: how weak the training evidence is for the one pair the switch turns on.

Run after build_site_data's step 7 and the history check (it reads their JSON files).
"""
import json
import os
import random
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.special import stdtr   # t-distribution CDF; t.sf(x, df) == stdtr(df, -x). scipy.stats is not needed

from pipeline import config as C
from pipeline.load import load_clean_bhavcopy

PAIRS = ['M_TEN', 'M_PETAL', 'M_GUINEA', 'TEN_PETAL', 'GUINEA_TEN', 'GUINEA_PETAL']
SLIPS = [0, 2, 5, 10]


def _load(data_dir: str, p: str):
    with open(os.path.join(data_dir, p), encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------- slippage estimators
def roll_spreads(df: pd.DataFrame, min_obs: int = 30) -> pd.DataFrame:
    """Roll (1984) effective spread per contract from consecutive-day log close changes,
    liquid (not thin, traded) days only. Positive serial covariance -> no spread detectable (0)."""
    rows = []
    ok = df[~df['no_trade'] & ~df['thin']].sort_values(['symbol', 'expiry', 'date'])
    for (sym, exp), g in ok.groupby(['symbol', 'expiry']):
        r = np.log(g['close'].to_numpy(dtype=float))
        ti = g['ti'].to_numpy()
        d = np.diff(r)
        consec = np.diff(ti) == 1
        pairs = consec[1:] & consec[:-1]          # both changes span one trading day
        x, y = d[1:][pairs], d[:-1][pairs]
        if len(x) < min_obs:
            continue
        cov = float(np.cov(x, y)[0, 1])
        rows.append({'symbol': sym, 'expiry': exp, 'n': int(len(x)),
                     'spread_bps': 2.0 * np.sqrt(-cov) * 1e4 if cov < 0 else 0.0})
    return pd.DataFrame(rows)


def corwin_schultz(df: pd.DataFrame) -> pd.DataFrame:
    """Corwin & Schultz (2012) two-day high/low spread estimate, liquid consecutive days only.
    Returns one row per day with the raw (unclipped) estimate in bps."""
    ok = df[~df['no_trade'] & ~df['thin'] & (df['high'] > 0) & (df['low'] > 0)].sort_values(['symbol', 'expiry', 'date']).copy()
    g = ok.groupby(['symbol', 'expiry'])
    ok['h1'], ok['l1'], ok['ti1'] = g['high'].shift(-1), g['low'].shift(-1), g['ti'].shift(-1)
    ok = ok[ok['ti1'] == ok['ti'] + 1]
    k = 3.0 - 2.0 * np.sqrt(2.0)
    beta = np.log(ok['high'] / ok['low']) ** 2 + np.log(ok['h1'] / ok['l1']) ** 2
    gamma = np.log(np.maximum(ok['high'], ok['h1']) / np.minimum(ok['low'], ok['l1'])) ** 2
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    ok['cs_bps'] = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha)) * 1e4
    return ok[['symbol', 'expiry', 'date', 'cs_bps']]


def tick_floor(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Half a tick per order, in bps of the latest liquid close: the least slippage can be."""
    out = {}
    last = df['date'].max()
    for sym, spec in C.CONTRACT_SPECS.items():
        g = df[(df['symbol'] == sym) & (df['date'] == last) & ~df['no_trade']]
        if not len(g):
            continue
        close = float(g.sort_values('oi')['close'].iloc[-1])
        out[sym] = {'tick_rs': spec.tick_size, 'quote_grams': spec.quote_grams, 'close': close,
                    'half_tick_bps': round(0.5 * spec.tick_size / close * 1e4, 3)}
    return out


def participation(df: pd.DataFrame, data_dir: str) -> Dict[str, Any]:
    """Lots traded per leg as a share of that contract's volume on the fill day (entry and exit)."""
    vol = df.set_index(['symbol', 'expiry', 'date'])['vol']
    shares: List[float] = []
    for p in PAIRS:
        bt = _load(data_dir, f'backtest/{p}_{C.BASE_SLIPPAGE}.json')
        a, b = C.PAIRS[p].symbol_a, C.PAIRS[p].symbol_b
        for t in bt['trades']:
            for sym, exp in ((a, t['expA']), (b, t['expB'])):
                lots = t['grams'] / C.CONTRACT_SPECS[sym].lot_grams
                for day in (t['entry'], t['exit']):
                    v = vol.get((sym, pd.Timestamp(exp), pd.Timestamp(day)))
                    if v and v > 0:
                        shares.append(100.0 * lots / float(v))
    s = pd.Series(shares, dtype=float)
    return {'fills': int(len(s)), 'median_pct': round(float(s.median()), 2), 'p90_pct': round(float(s.quantile(0.9)), 2),
            'max_pct': round(float(s.max()), 1), 'over_5pct': int((s > 5).sum())}


# ---------------------------------------------------------------- break-even from a straight line
def breakeven(net_by_slip: Dict[int, float]) -> Dict[str, Any]:
    """net(s) = a + b*s. Check the line fits all four scenarios, then solve net(s) = 0."""
    s = np.array(sorted(net_by_slip), dtype=float)
    n = np.array([net_by_slip[int(x)] for x in s], dtype=float)
    b, a = np.polyfit(s, n, 1)
    worst = float(np.max(np.abs(a + b * s - n)))
    assert worst < 5.0, f'net P&L is not linear in slippage (max gap Rs {worst:.1f})'
    be = None if b >= 0 else (-a / b)
    return {'net_at_0': round(float(a), 1), 'per_bps': round(float(b), 1),
            'breakeven_bps': None if be is None or be < 0 else round(float(be), 1),
            'loses_even_at_0': bool(a < 0)}


def _sgn(v: float) -> str:
    """2-decimal number with a real minus sign, as the website writes it."""
    return f"{v:.2f}".replace('-', '−')


def _boot_share_above_zero(x: List[float], seed: int = 7, draws: int = 10000) -> Optional[int]:
    if not x:
        return None
    rng = random.Random(seed)
    n = len(x)
    above = sum(1 for _ in range(draws) if sum(rng.choice(x) for _ in range(n)) > 0)
    return round(100 * above / draws)


def _bps(v: float) -> str:
    return f"{float(v):+.0f} bps".replace('-', '−')


def petal_break(data_dir: str, window: int = 5, span: int = 60) -> Dict[str, Any]:
    """Locate the GOLDPETAL level shift from the data instead of typing dates in.
    1. The break is where the median gap over the `span` observations before and after differs most.
    2. Within `span` observations of it, the sharpest `window`-day fall in GOLDGUINEA - GOLDPETAL marks the days.
    GOLDM - GOLDGUINEA over the same days shows which contract moved (flat -> GOLDPETAL repriced)."""
    def series(p):
        x = pd.DataFrame(_load(data_dir, f'pairs/{p}.json'))
        x['d'] = pd.to_datetime(x['d'])
        return x.set_index('d')
    gp, mg, mp = series('GUINEA_PETAL'), series('M_GUINEA'), series('M_PETAL')
    s = gp['s'].to_numpy(dtype=float)
    shift = [np.median(s[i - span:i]) - np.median(s[i:i + span]) for i in range(span, len(s) - span)]
    k = span + int(np.argmax(shift))
    chg = gp['s'] - gp['s'].shift(window)
    near = chg.iloc[max(window, k - span):k + span]
    end = near.idxmin()
    start = gp.index[gp.index.get_loc(end) - window]
    same_contract = bool(gp.loc[start, 'ea'] == gp.loc[end, 'ea'])
    mg_chg = float(mg['s'].asof(end) - mg['s'].asof(start))
    mp_chg = float(mp['s'].asof(end) - mp['s'].asof(start))
    i_end = gp.index.get_loc(end)
    before = gp['s'].iloc[max(0, i_end - window - 2 * span):i_end - window]
    after = gp['s'].iloc[i_end + span:i_end + 3 * span]          # skip the unsettled months right after
    fd = lambda d: pd.Timestamp(d).strftime('%d %b %Y')
    fm = lambda d: pd.Timestamp(d).strftime('%b %Y')
    return {
        'start': start.strftime('%Y-%m-%d'), 'end': end.strftime('%Y-%m-%d'),
        'gap_start_bps': round(float(gp.loc[start, 's']), 1), 'gap_end_bps': round(float(gp.loc[end, 's']), 1),
        'same_contract': same_contract, 'contract_expiry': gp.loc[end, 'ea'],
        'm_guinea_change_bps': round(mg_chg, 1), 'm_petal_change_bps': round(mp_chg, 1),
        'before': {'from': before.index[0].strftime('%Y-%m-%d'), 'to': before.index[-1].strftime('%Y-%m-%d'),
                   'median_bps': round(float(before.median()), 1)},
        'after': {'from': after.index[0].strftime('%Y-%m-%d'), 'to': after.index[-1].strftime('%Y-%m-%d'),
                  'median_bps': round(float(after.median()), 1)},
        'cause_confirmed': False,
        'summary': (
            f"GOLDGUINEA − GOLDPETAL fell from {_bps(gp.loc[start, 's'])[:-4]} to {_bps(gp.loc[end, 's'])} between {fd(start)} and "
            f"{fd(end)}" + (f", inside one contract (expiry {fm(gp.loc[end, 'ea'])})" if same_contract else '')
            + f". Against GOLDM over the same days, GOLDPETAL rose about {-mp_chg:.0f} bps and GOLDGUINEA about {-mg_chg:.0f} bps, "
            f"so most of the move was GOLDPETAL repricing. "
            f"The gap swung back part-way for a few weeks, then settled: median {_bps(before.median())} from "
            f"{fm(before.index[0])} to {fm(before.index[-1])}, {_bps(after.median())} from {fm(after.index[0])} to "
            f"{fm(after.index[-1])}. We found no MCX notice explaining it, so the cause is not confirmed."
        ),
    }


def build(data_dir: str = 'frontend/public/data', csv_path: str = 'data/raw/gold_bhavcopy_clean.csv') -> Dict[str, Any]:
    df, _, _ = load_clean_bhavcopy(csv_path)
    rc = _load(data_dir, 'backtest/rule_comparison.json')
    cur = rc['current_rule']['by_slip']
    hist = _load(data_dir, 'history.json')

    # 1. test-year status
    test_year = {
        'first_results_seen': C.TEST_YEAR_FIRST_SEEN,
        'rule_frozen': C.RULE_FROZEN_ON,
        'clean': False,
        'reason': (f"The original study's test-year results were known by {C.TEST_YEAR_FIRST_SEEN}; the five-check rule "
                   f"was written on {C.RULE_FROZEN_ON}, after that. So the test year helped shape the rule and is not a "
                   f"clean out-of-sample test."),
        'clean_check': {'from': hist['window']['from'], 'to': hist['window']['to'],
                        'reason': 'The settings were chosen on 2023-2025 training only and never on these years. The tender and liquidity rules were tightened on 25 Oct 2026, after this period\'s first results were known (to fix the contract rules, not to change the result), so it is a historical holdout, not a strictly unseen test.'},
    }

    # 2. slippage evidence
    roll = roll_spreads(df)
    cs = corwin_schultz(df)
    floor = tick_floor(df)
    by_sym = {}
    for sym in C.CONTRACT_SPECS:
        r = roll[roll['symbol'] == sym]
        c = cs[cs['symbol'] == sym].copy()
        c['m'] = c['date'].dt.to_period('M')
        monthly = c.groupby('m')['cs_bps'].mean()
        by_sym[sym] = {
            'half_tick_bps': floor.get(sym, {}).get('half_tick_bps'),
            'roll_contracts': int(len(r)),
            'roll_zero_share_pct': round(100 * float((r['spread_bps'] == 0).mean())) if len(r) else None,
            'roll_median_bps': round(float(r['spread_bps'].median()), 1) if len(r) else None,
            'cs_days': int(len(c)),
            'cs_negative_share_pct': round(100 * float((c['cs_bps'] <= 0).mean())) if len(c) else None,
            'cs_monthly_median_bps': round(max(0.0, float(monthly.median())), 1) if len(monthly) else None,
            'cs_clipped_mean_bps': round(float(c['cs_bps'].clip(lower=0).mean()), 1) if len(c) else None,
        }
    clipped = [v['cs_clipped_mean_bps'] for v in by_sym.values() if v['cs_clipped_mean_bps'] is not None]
    be_train = breakeven({s: cur[str(s)]['train_net_rs'] for s in SLIPS})
    be_test = breakeven({s: cur[str(s)]['test_net_rs'] for s in SLIPS})
    be_hist = breakeven({s: hist['result']['by_slip'][str(s)]['net_rs'] for s in SLIPS}) if hist.get('result') else None
    part = participation(df, data_dir)
    floor_max = max(v['half_tick_bps'] for v in floor.values())
    slippage = {
        'assumed_bps': C.BASE_SLIPPAGE,
        'assumed_share_of_cost_pct': None,   # filled in build_web_data from the cost table
        'by_symbol': by_sym,
        'floor_max_bps': floor_max,
        'cs_clipped_range_bps': [min(clipped), max(clipped)] if clipped else None,
        'participation': part,
        'breakeven': {'train': be_train, 'test': be_test, 'history': be_hist},
        'measurable_from_eod': False,
        'summary': (
            f"Daily data cannot measure slippage. Both standard estimators find no spread on most contracts and months "
            f"(it is smaller than a normal day's price noise), and with negative readings set to zero they give "
            f"{min(clipped):.0f}–{max(clipped):.0f} bps for every contract alike, which is the day's volatility, not a spread. "
            f"The hard floor is half a tick: at most {floor_max:.2f} bps. Our trades were a median {part['median_pct']:.2f}% of the "
            f"day's volume. Training breaks even at {be_train['breakeven_bps']} bps per order"
            + (f", the test year at {be_test['breakeven_bps']} bps" if be_test['breakeven_bps'] is not None else '')
            + (", and 2011–2023 loses money even with zero slippage." if be_hist and be_hist['loses_even_at_0'] else '.')
            + " Only real broker fills (a forward test) can settle the number."
        ),
    }

    # 3. multiple testing on the test year
    b5 = cur[str(C.BASE_SLIPPAGE)]
    n, t = b5['test_n'], b5['test_t']
    p_two = float(2 * stdtr(n - 1, -abs(t))) if (t is not None and n > 1) else None
    versions = C.TEST_YEAR_RULE_VERSIONS
    grid_combos = len(C.WINDOW_GRID) * len(C.Z_ENTRY_GRID) * len(C.MAX_HOLD_GRID)
    multiple = {
        'rule_versions_scored_on_test': versions,
        'settings_tried_on_training': grid_combos * len(PAIRS),
        'grid_per_pair': grid_combos,
        't': t, 'n': n, 'p_two_sided': None if p_two is None else round(p_two, 3),
        'p_bonferroni': None if p_two is None else round(min(1.0, p_two * versions), 3),
        'note': (f"{grid_combos} settings × {len(PAIRS)} pairs = {grid_combos * len(PAIRS)} were tried on training only (that is "
                 f"tuning, not testing). On the test year, {versions} rule versions were scored (original study, five checks, "
                 f"five checks + switch). t = {_sgn(t)} on {n} trades gives p = {p_two:.3f} (two-sided); allowing for "
                 f"{versions} looks, p = {min(1.0, p_two * versions):.2f}. Not significant either way."),
    }

    # 4. the training switch
    on = [k for k, v in rc['switch'].items() if v['on']]
    sw = {}
    for p in on:
        tr = [x['net'] for x in _load(data_dir, f'backtest/{p}_{C.BASE_SLIPPAGE}.json')['trades'] if x['seg'] == 'train']
        bps = [x['net_bps'] for x in _load(data_dir, f'backtest/{p}_{C.BASE_SLIPPAGE}.json')['trades'] if x['seg'] == 'train']
        s = pd.Series(bps, dtype=float)
        tt = float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))) if len(s) > 2 and s.std(ddof=1) > 0 else None
        sw[p] = {'train_n': len(tr), 'train_net_rs': round(float(sum(tr)), 1), 'train_t': None if tt is None else round(tt, 2),
                 'boot_above_zero_pct': _boot_share_above_zero(tr)}
    switch = {
        'on_pairs': on, 'detail': sw,
        'note': ' '.join(
            f"{C.PAIRS[p].symbol_a} · {C.PAIRS[p].symbol_b}: training made {'+' if v['train_net_rs'] >= 0 else '−'}₹{abs(v['train_net_rs']):,.0f} over {v['train_n']} trades "
            f"(t = {_sgn(v['train_t'])}; {v['boot_above_zero_pct']}% of resamples above zero), close to a coin flip, so the switch "
            f"is a weak filter, not proof." for p, v in sw.items()),
    }

    out = {'test_year': test_year, 'slippage': slippage, 'multiple_testing': multiple, 'switch': switch,
           'petal_break': petal_break(data_dir)}
    with open(os.path.join(data_dir, 'evidence.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    return out


if __name__ == '__main__':
    o = build()
    print(o['slippage']['summary'])
    print(o['multiple_testing']['note'])
    print(o['switch']['note'])
