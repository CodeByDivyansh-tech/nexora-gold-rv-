"""Checks for pipeline/evidence.py and the honesty of the published verdict (Oct-2026 review)."""
import json
import os

import numpy as np
import pandas as pd
import pytest
from scipy.special import stdtr   # t-distribution CDF; t.sf(x, df) == stdtr(df, -x). scipy.stats is not needed

from pipeline import config as C
from pipeline.evidence import breakeven, roll_spreads, corwin_schultz
from pipeline.history import load_book

DATA = 'frontend/public/data'


def _j(p):
    return json.load(open(os.path.join(DATA, p), encoding='utf-8'))


def test_breakeven_solves_a_straight_line_and_rejects_a_curve():
    r = breakeven({0: 100.0, 2: 60.0, 5: 0.0, 10: -100.0})
    assert r['breakeven_bps'] == 5.0 and not r['loses_even_at_0']
    assert breakeven({0: -10.0, 2: -30.0, 5: -60.0, 10: -110.0})['loses_even_at_0']
    with pytest.raises(AssertionError):
        breakeven({0: 100.0, 2: 0.0, 5: 90.0, 10: -100.0})


def test_roll_recovers_a_known_bid_ask_bounce():
    # flat true price, closes bounce between bid and ask: spread 10 bps
    rng = np.random.default_rng(0)
    n = 400
    side = rng.choice([-1, 1], size=n)
    close = 10000 * np.exp(side * 0.0005)
    df = pd.DataFrame({'symbol': 'GOLDM', 'expiry': pd.Timestamp('2030-01-01'), 'date': pd.bdate_range('2025-01-01', periods=n),
                       'close': close, 'ti': np.arange(n), 'no_trade': False, 'thin': False})
    r = roll_spreads(df)
    assert abs(r['spread_bps'].iloc[0] - 10.0) < 1.5


def test_corwin_schultz_is_zero_when_there_is_no_spread_and_positive_with_one():
    n = 300
    rng = np.random.default_rng(1)
    mid = 10000 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    base = pd.DataFrame({'symbol': 'GOLDM', 'expiry': pd.Timestamp('2030-01-01'), 'date': pd.bdate_range('2025-01-01', periods=n),
                         'ti': np.arange(n), 'no_trade': False, 'thin': False})
    wide = base.assign(high=mid * 1.0010, low=mid * 0.9990)      # every day's range is 20 bps around the mid
    cs = corwin_schultz(wide)['cs_bps']
    assert cs.clip(lower=0).mean() > 0


def test_evidence_file_matches_the_backtest_and_history():
    e = _j('evidence.json')
    cur = _j('backtest/rule_comparison.json')['current_rule']['by_slip']
    h = _j('history.json')['result']['by_slip']
    be = e['slippage']['breakeven']
    for key, src in (('train', {s: cur[str(s)]['train_net_rs'] for s in (0, 2, 5, 10)}),
                     ('test', {s: cur[str(s)]['test_net_rs'] for s in (0, 2, 5, 10)}),
                     ('history', {s: h[str(s)]['net_rs'] for s in (0, 2, 5, 10)})):
        a, b = be[key]['net_at_0'], be[key]['per_bps']
        for s, v in src.items():                           # the straight line goes through every scenario
            assert abs(a + b * s - v) < 5
        if be[key]['breakeven_bps'] is not None:           # and crosses zero at the published break-even
            assert abs(a + b * be[key]['breakeven_bps']) < abs(b) * 0.1
    floor = e['slippage']['floor_max_bps']
    assert 0 < floor < C.BASE_SLIPPAGE          # half a tick is far below the assumption


def test_test_year_is_labelled_as_not_clean_and_dates_are_in_order():
    e = _j('evidence.json')['test_year']
    assert e['clean'] is False
    assert C.TEST_START < e['first_results_seen'] <= e['rule_frozen']
    assert e['clean_check']['to'] < C.TRAIN_START          # the clean check never touches tuning data


def test_multiple_testing_p_value_is_computed_not_typed():
    e = _j('evidence.json')['multiple_testing']
    p = 2 * stdtr(e['n'] - 1, -abs(e['t']))
    assert abs(e['p_two_sided'] - round(p, 3)) < 1e-9
    assert abs(e['p_bonferroni'] - round(min(1, p * e['rule_versions_scored_on_test']), 3)) < 1e-9
    assert e['settings_tried_on_training'] == len(C.WINDOW_GRID) * len(C.Z_ENTRY_GRID) * len(C.MAX_HOLD_GRID) * 6


def test_verdict_leads_with_the_clean_test_and_never_calls_the_test_year_unseen():
    m = _j('methodology.json')
    v = m['honest_conclusion']
    h = _j('history.json')
    assert v.index('historical holdout') < v.index('test year')
    assert 'not a clean' in v and 'unseen' not in v.lower()
    # Oct-2026 audit: a single train/test split is not a rolling walk-forward, and the rule correction is disclosed
    assert 'walk-forward' not in v.lower() and 'walk forward' not in v.lower()
    assert 'corrected' in v and 'after the earlier version' in v
    stages = ' '.join(s['name'] + ' ' + s['desc'] for s in m['stages']).lower()
    assert 'not a rolling walk-forward' in stages
    assert f"{h['result']['by_slip']['5']['n']} trades" in v
    site = _j('site-data.json')
    assert site['conclusion'] == v
    assert site['evidence']['slippage']['assumed_share_of_cost_pct'] > 50


def test_petal_break_is_located_from_the_data():
    pb = _j('evidence.json')['petal_break']
    assert pb['start'] < pb['end'] and pb['gap_start_bps'] - pb['gap_end_bps'] > 100
    assert pb['before']['median_bps'] > 150 and pb['after']['median_bps'] < 0      # cheap before, slightly rich after
    assert abs(pb['m_petal_change_bps']) > abs(pb['m_guinea_change_bps'])          # GOLDPETAL moved most
    assert pb['cause_confirmed'] is False
    site = _j('site-data.json')
    assert site['events']['petalStart'] == pb['start'] and site['events']['petalEnd'] == pb['end']


def test_home_counts_add_up_from_the_data():
    """Home's one-line summary: prices used and trades are the sum of the book part and our own part."""
    site, h = _j('site-data.json'), _j('history.json')
    book = load_book()
    win = (book['date'] >= h['window']['from']) & (book['date'] <= h['window']['to'])
    assert site['longrun']['rows'] == int(win.sum()) == h['window']['rows']
    assert site['meta']['rows'] == len(pd.read_csv('data/raw/gold_bhavcopy_clean.csv'))
    cur = site['rule']['current']['5']
    assert site['longrun']['n'] == h['result']['by_slip']['5']['n']
    assert cur['test_n'] == site['pooled']['5']['n']
    assert site['longrun']['checked'] == h['check']['shared_rows'] and site['longrun']['checkMismatches'] == 0


def test_history_chart_file_matches_the_clean_test():
    """The 2011-2023 part of the charts is the clean test itself: same trades, same total, same dates."""
    hc, h = _j('history_charts.json'), _j('history.json')
    assert hc['from'] == h['window']['from'] and hc['to'] == h['window']['to']
    for slip in ('0', '2', '5', '10'):
        trades = [t for p in hc['pairs'].values() for t in p['trades'][slip]]
        assert len(trades) == h['result']['by_slip'][slip]['n']
        assert abs(sum(t[5] for t in trades) - h['result']['by_slip'][slip]['net_rs']) <= 0.5 * len(trades)   # each trade rounded to the rupee
    for p in hc['pairs'].values():
        assert len(p['d']) == len(p['s']) == len(p['mu']) == len(p['sd']) and p['d'] == sorted(p['d'])
        assert hc['from'] <= p['d'][0] and p['d'][-1] <= hc['to']
    r = hc['replay']
    assert len(r['d']) == len(r['f']) == len(r['sig']) and r['d'][-1] == hc['to']


def test_explorer_grid_reproduces_the_published_rule():
    """'Try your own rule' runs the real engine; its cell for the frozen settings must equal the published results."""
    e, site, h = _j('explore.json'), _j('site-data.json'), _j('history.json')
    for pid, p in site['pairs'].items():
        pr = p['params']
        c = e['pairs'][pid][f"{pr['W']}|{pr['ze']}|{pr['mh']}|5|1"]
        tr, te = site['backtest'][pid]['5']['train'], site['backtest'][pid]['5']['test']
        assert c[3] == tr['n_trades'] and abs(c[4] - tr['net_rs']) <= 1
        assert c[6] == te['n_trades'] and abs(c[7] - te['net_rs']) <= 1
        hp = h['result']['pairs'].get(pid)
        if hp:
            assert c[0] == hp['n'] and abs(c[1] - hp['net_rs']) <= 1
        else:
            assert c[0] == 0
        assert abs(sum(c[12:]) - (c[1] + c[4] + c[7] + c[10])) <= len(e['years'])   # years add up to the periods
    assert len(e['pairs']['M_PETAL']) == len(e['grid']['W']) * len(e['grid']['ze']) * len(e['grid']['mh']) * len(e['grid']['slip']) * 2


def test_whole_study_counts_and_checks_cover_2011_on():
    """Dataset size, alert follow-through and the luck check include the clean-test years, not only our download."""
    site, h, r = _j('site-data.json'), _j('history.json'), _j('robustness.json')
    L, m = site['longrun'], site['meta']
    assert L['allRows'] == L['rows'] + m['rows'] and L['allDays'] == L['days'] + m['days']
    assert m['contracts'] < L['allContracts'] <= L['contracts'] + m['contracts']
    assert r['alerts']['alert_clean']['n'] > r['alerts']['alert_test']['n'] + r['alerts']['alert_train']['n']
    assert r['bootstrap']['clean_5']['n'] == h['result']['by_slip']['5']['n']
    assert abs(r['bootstrap']['clean_5']['total'] - h['result']['by_slip']['5']['net_rs']) < 1
    assert site['stages'][0]['desc'].startswith(f"Parse {L['allRows']:,} daily prices")
