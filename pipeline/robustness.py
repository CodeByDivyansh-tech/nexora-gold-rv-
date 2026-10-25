"""Two extra checks on the published results (run after build_site_data):

1. Alert follow-through: after a signal fires, does the gap from normal actually close?
   Compared with days that did not fire, using each pair's own daily series, over every year we have:
   the clean test 2011-2023 (MCX history book, the three pairs that existed) plus our own download.
2. How sure can we be: a bootstrap 95% range for the unseen-year result, by resampling
   the closed trades (10,000 draws, fixed seed so the numbers never change), for the clean test,
   training and the test year.

Reads only files in frontend/public/data and writes frontend/public/data/robustness.json.
Run: python -m pipeline.robustness
"""
import json
import os
import random
import statistics

PAIRS = ['M_TEN', 'M_PETAL', 'M_GUINEA', 'TEN_PETAL', 'GUINEA_TEN', 'GUINEA_PETAL']
HORIZON = 10                    # trading days
CRASH = ('2026-01-01', '2026-03-31')
SEED, DRAWS = 7, 10000


def _load(data_dir, p):
    with open(os.path.join(data_dir, p), encoding='utf-8') as f:
        return json.load(f)


def follow_through(series, i, horizon=HORIZON):
    """Gap from normal on day i, and what it did over the next `horizon` trading days
    while the same two contracts are held (stops at a contract change).
    Returns (gap0_bps, closed_halfway, bps_closed, days_to_half) or None."""
    r0 = series[i]
    if r0['mu'] is None or r0['z'] is None:
        return None
    g0 = r0['s'] - r0['mu']
    if abs(g0) < 1e-9:
        return None
    half_day, last = None, None
    for k in range(1, horizon + 1):
        if i + k >= len(series):
            break
        r = series[i + k]
        if r['ea'] != r0['ea'] or r['eb'] != r0['eb'] or r['mu'] is None:
            break
        g = r['s'] - r['mu']
        last = g
        # closed at least halfway: gap now no more than half its size on the same side (or crossed)
        if half_day is None and g * g0 <= 0.5 * g0 * g0:
            half_day = k
    if last is None:
        return None
    return g0, half_day is not None, abs(g0) - abs(last), half_day


def why_not_measured(series, i, horizon=HORIZON):
    """Reason a signal day has no follow-through figure (mirrors follow_through's early returns)."""
    r0 = series[i]
    if r0['mu'] is None or r0['z'] is None:
        return 'no normal level yet on the signal day'
    if abs(r0['s'] - r0['mu']) < 1e-9:
        return 'gap exactly at normal'
    if i + 1 >= len(series):
        return 'signal on the last day of data'
    r = series[i + 1]
    if r['ea'] != r0['ea'] or r['eb'] != r0['eb']:
        return 'the pair switched to new contracts the next day'
    return 'no later day on the same contracts'


def summarise(rows):
    if not rows:
        return dict(n=0)
    n = len(rows)
    halfway = sum(1 for r in rows if r[1])
    closed = sorted(r[2] for r in rows)
    days = [r[3] for r in rows if r[3] is not None]
    return dict(n=n, halfway_pct=round(100 * halfway / n), median_closed_bps=round(statistics.median(closed), 1),
                mean_closed_bps=round(statistics.fmean(closed), 1),
                median_gap_bps=round(statistics.median(abs(r[0]) for r in rows), 1),
                median_days_to_half=(statistics.median(days) if days else None))


def bootstrap(values, rng, draws=DRAWS):
    n = len(values)
    if n == 0:
        return None
    totals = sorted(sum(rng.choice(values) for _ in range(n)) for _ in range(draws))
    lo, hi = totals[int(0.025 * draws)], totals[int(0.975 * draws) - 1]
    return dict(n=n, total=round(sum(values), 1), lo=round(lo, 1), hi=round(hi, 1),
                above_zero_pct=round(100 * sum(1 for t in totals if t > 0) / draws))


def _history_series(data_dir):
    """The clean-test years (2011-2023) as daily pair series in the same shape as pairs/{p}.json, plus the
    clean-test signal days, so follow-through is measured the same way on every year we have."""
    import pandas as pd
    from pipeline.history import HISTORY_PAIRS, HISTORY_START, BOOK_PATH, OURS_PATH, history_frame, load_book
    from pipeline.pairs import build_pair_series, compute_rolling_z
    book = load_book(BOOK_PATH)
    end = pd.read_csv(OURS_PATH, parse_dates=['date'])['date'].min() - pd.Timedelta(days=1)
    df, dates, tdi, carry = history_frame(book, end)
    hc = _load(data_dir, 'history_charts.json')
    out, sigs = {}, {}
    for p in HISTORY_PAIRS:
        W = _load(data_dir, f'backtest/{p}_5.json')['params']['W']
        x = compute_rolling_z(build_pair_series(df, p, carry), W=int(W))
        x = x[x['date'] >= pd.Timestamp(HISTORY_START)]
        out[p] = [dict(d=r.date.strftime('%Y-%m-%d'), ea=r.expiry_a.strftime('%Y-%m-%d'), eb=r.expiry_b.strftime('%Y-%m-%d'),
                       s=float(r.spread), mu=None if pd.isna(r.mu) else float(r.mu), z=None if pd.isna(r.z) else float(r.z))
                  for r in x.itertuples()]
        sigs[p] = {t[0]: t[5] for t in hc['pairs'][p]['trades']['5']}
    return out, sigs


def build(data_dir='frontend/public/data'):
    history = _load(data_dir, 'signals_history.json')
    rt_cost = round(_load(data_dir, 'site-data.json')['rt'], 2) if os.path.exists(os.path.join(data_dir, 'site-data.json')) else 24.38
    sig_days = {(h['pair'], h['date']): h for h in history}

    groups = {'alert': [], 'alert_clean': [], 'alert_test': [], 'alert_train': [], 'alert_forward': [], 'unusual_small': [], 'ordinary': []}
    per_alert = []
    excluded = []          # trades whose signal day has no follow-through figure, with the reason (alerts != trades)
    hist, hsig = _history_series(data_dir)
    for p, series in hist.items():
        ze = _load(data_dir, f'backtest/{p}_5.json')['params']['ze']
        for i, r in enumerate(series):
            ft = follow_through(series, i)
            if ft is None:
                if r['d'] in hsig[p]:
                    excluded.append(dict(pair=p, date=r['d'], period='clean', reason=why_not_measured(series, i)))
                continue
            if r['d'] in hsig[p]:
                groups['alert'].append(ft)
                groups['alert_clean'].append(ft)
            elif abs(r['z']) >= ze:
                groups['unusual_small'].append(ft)
            elif abs(r['z']) < 1.0:
                groups['ordinary'].append(ft)
    for p in PAIRS:
        ze = _load(data_dir, f'backtest/{p}_5.json')['params']['ze']
        series = _load(data_dir, f'pairs/{p}.json')
        for i, r in enumerate(series):
            ft = follow_through(series, i)
            key = (p, r['d'])
            if ft is None:
                if key in sig_days:
                    excluded.append(dict(pair=p, date=r['d'], period=sig_days[key]['seg'], reason=why_not_measured(series, i)))
                continue
            if key in sig_days:
                h = sig_days[key]
                groups['alert'].append(ft)
                groups['alert_' + h['seg']].append(ft)
                per_alert.append(dict(pair=p, date=r['d'], seg=h['seg'], z=r['z'], gap_bps=round(ft[0], 1),
                                      halfway_10d=ft[1], closed_bps=round(ft[2], 1), days_to_half=ft[3],
                                      trade_net_rs=h['net_rs']))
            elif abs(r['z']) >= ze:
                groups['unusual_small'].append(ft)
            elif abs(r['z']) < 1.0:
                groups['ordinary'].append(ft)
    alerts = {k: summarise(v) for k, v in groups.items()}

    rng = random.Random(SEED)
    boot = {}
    for slip in (0, 2, 5, 10):
        trades = []
        for p in PAIRS:
            trades += [t for t in _load(data_dir, f'backtest/{p}_{slip}.json')['trades'] if t['seg'] == 'test']
        nets = [t['net'] for t in trades]
        crash = [t['net'] for t in trades if CRASH[0] <= t['exit'] <= CRASH[1]]
        other = [t['net'] for t in trades if not (CRASH[0] <= t['exit'] <= CRASH[1])]
        boot[str(slip)] = dict(all=bootstrap(nets, rng), crash=dict(n=len(crash), total=round(sum(crash), 1)),
                               without_crash=bootstrap(other, rng))
    # Use the exact totals the backtest reports (trade-level nets are rounded to 0.1, so their sum can differ by ₹1).
    by_slip = _load(data_dir, 'backtest/rule_comparison.json')['current_rule']['by_slip']
    for slip, b in boot.items():
        o = by_slip[slip]
        b['all']['total'], b['crash']['total'], b['without_crash']['total'] = o['test_net_rs'], o['crash_net_rs'], o['ex_crash_net_rs']
    train5 = []
    for p in PAIRS:
        train5 += [t['net'] for t in _load(data_dir, f'backtest/{p}_5.json')['trades'] if t['seg'] == 'train']
    boot['train_5'] = bootstrap(train5, rng)
    boot['train_5']['total'] = by_slip['5']['train_net_rs']
    hc = _load(data_dir, 'history_charts.json')
    clean5 = [t[5] for p in hc['pairs'].values() for t in p['trades']['5']]
    boot['clean_5'] = bootstrap(clean5, rng)
    boot['clean_5']['total'] = _load(data_dir, 'history.json')['result']['by_slip']['5']['net_rs']

    # Alerts and trades are different populations: every trade starts from an alert (its signal day), but the
    # follow-through figure needs at least one later day on the same two contracts. The difference is listed here.
    n_trades = len(history) + sum(len(p['trades']['5']) for p in hc['pairs'].values())
    reconcile = dict(trades=n_trades, alerts_measured=alerts['alert']['n'], not_measured=len(excluded),
                     adds_up=(alerts['alert']['n'] + len(excluded) == n_trades),
                     excluded=sorted(excluded, key=lambda e: e['date']),
                     definition=('Alert: a day all five checks passed and a trade was signalled. Trade: the position that followed, '
                                 'filled at the next close. Follow-through is measured over the next ' + str(HORIZON) + ' trading days '
                                 'while the same two contracts are held, so a signal with no later day on those contracts has no figure.'))
    out = dict(horizon_days=HORIZON, round_trip_cost_bps=rt_cost, alerts=alerts, groups_from=hc['from'], reconcile=reconcile,
               alert_list=sorted(per_alert, key=lambda a: a['date'], reverse=True),
               bootstrap=boot, seed=SEED, draws=DRAWS, crash_window=list(CRASH))
    with open(os.path.join(data_dir, 'robustness.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    return out


if __name__ == '__main__':
    o = build()
    print(json.dumps(o['alerts'], indent=1))
    print(json.dumps(o['bootstrap'], indent=1))
