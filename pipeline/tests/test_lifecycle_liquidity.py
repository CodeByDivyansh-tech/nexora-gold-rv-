"""Oct-2026 compliance audit: tender-period protection and size-aware liquidity (Priorities 1, 2, 7).

Unit tests use small synthetic frames so each rule is checked on its own; the integration tests run the real rule
on our MCX download up to the end of the test year (TEST_END), so a data refresh cannot change what they check."""
import numpy as np
import pandas as pd
import pytest

import pipeline.contract_rules as CR
from pipeline.alerts import evaluate_pair_gates
from pipeline.backtest import prepare_contract_lookup, run_all_scenarios, run_grid_search, run_pair_backtest
from pipeline.carry import compute_reference_carry
from pipeline.config import (ALERT_RULE, BASE_SLIPPAGE, EXIT_LEAD_TD, MAX_PARTICIPATION, MIN_OI_LOTS, MIN_VOLUME_LOTS,
                             PAIR_DEFINITIONS, TEST_END)
from pipeline.lifecycle import entry_timing_ok, intended_lots, min_entry_td, size_liquidity_ok
from pipeline.load import load_clean_bhavcopy
from pipeline.pairs import build_all_pairs, compute_rolling_z, rolling_stats

_C = {}


def _real():
    if not _C:
        df, dates, tdi = load_clean_bhavcopy('data/raw/gold_bhavcopy_clean.csv', end=TEST_END)
        carry, chosen = compute_reference_carry(df, dates)
        pairs = build_all_pairs(df, carry)
        P = prepare_contract_lookup(df)
        _, best = run_grid_search(pairs, P, dates, tdi, rule=ALERT_RULE)
        trades, _ = run_all_scenarios(pairs, best, P, dates, tdi, rule=ALERT_RULE)
        _C.update(df=df, dates=dates, tdi=tdi, pairs=pairs, P=P, best=best, trades=trades, chosen=chosen)
    return _C


# ------------------------------------------------------------------ synthetic pair (GOLDGUINEA vs GOLDPETAL)
def _synthetic(n=40, spike_day=28, vol=10_000, oi=10_000, fill_vol=None, exp_offset=60, exp_b_offset=None):
    """A pair series and contract lookup for one GOLDGUINEA / GOLDPETAL contract pair. The spread is flat noise
    with one unusual day (spike_day), so the rule signals exactly once. fill_vol overrides volume on the fill day."""
    dates = pd.bdate_range('2025-01-01', periods=n)
    tdi = {d: i for i, d in enumerate(dates)}
    ea = dates[0] + pd.Timedelta(days=exp_offset) if exp_offset < 10_000 else None
    eb = dates[0] + pd.Timedelta(days=exp_b_offset if exp_b_offset is not None else exp_offset)
    ea = ea if ea is not None else eb
    noise = np.array([1.0 if k % 2 else -1.0 for k in range(n)])
    spread = noise.copy()
    spread[spike_day] = 3.0
    rows, ser = [], []
    for k, d in enumerate(dates):
        td_a = int(np.busday_count(d.date(), ea.date()))
        td_b = int(np.busday_count(d.date(), eb.date()))
        pxa, pxb = 13_000.0 * (1 + spread[k] / 1e4), 13_000.0
        v = fill_vol if (fill_vol is not None and k == spike_day + 1) else vol
        for sym, exp, px, td, lot in (('GOLDGUINEA', ea, pxa, td_a, 8), ('GOLDPETAL', eb, pxb, td_b, 1)):
            q = 8 if sym == 'GOLDGUINEA' else 1
            rows.append(dict(symbol=sym, expiry=exp, date=d, close=px * q * 0.999, px=px, no_trade=False, day_move=0.0,
                             vol=v, oi=oi, thin=False, td_to_exp=td, lot_grams=lot, quote_grams=q, purity=0.999))
        ser.append(dict(date=d, expiry_a=ea, expiry_b=eb, spread=spread[k], px_a=pxa, px_b=pxb, vol_a=vol, vol_b=vol,
                        oi_a=oi, oi_b=oi, td_to_exp_a=td_a, td_to_exp_b=td_b, roll=False))
    P = pd.DataFrame(rows).set_index(['symbol', 'expiry', 'date'])
    return pd.DataFrame(ser), P, np.array(dates), tdi


RULE = dict(ALERT_RULE, use_hurdle=False)   # synthetic spreads are tiny; the cost line is tested elsewhere


def test_synthetic_pair_trades_once_when_everything_passes():
    ps, P, dates, tdi = _synthetic()
    t = run_pair_backtest('GUINEA_PETAL', ps, P, dates, tdi, W=10, ze=2.0, mh=5, slip_bps=5, rule=RULE)
    assert len(t) == 1 and t.iloc[0]['sig'] == dates[28]


def test_fill_day_that_fails_liquidity_blocks_the_trade():
    ps, P, dates, tdi = _synthetic(fill_vol=20)        # signal day fine, fill day below the volume floor
    assert len(run_pair_backtest('GUINEA_PETAL', ps, P, dates, tdi, W=10, ze=2.0, mh=5, slip_bps=5, rule=RULE)) == 0
    # enough volume for the floor but the order would be over MAX_PARTICIPATION of it
    grams, la, lb = intended_lots('GOLDGUINEA', 'GOLDPETAL', 13_000.0)
    v = int(lb / MAX_PARTICIPATION) - 5
    assert v >= MIN_VOLUME_LOTS
    ps, P, dates, tdi = _synthetic(fill_vol=v)
    assert len(run_pair_backtest('GUINEA_PETAL', ps, P, dates, tdi, W=10, ze=2.0, mh=5, slip_bps=5, rule=RULE)) == 0


def test_low_volume_on_the_signal_day_blocks_the_trade():
    ps, P, dates, tdi = _synthetic(vol=MIN_VOLUME_LOTS - 1)
    assert len(run_pair_backtest('GUINEA_PETAL', ps, P, dates, tdi, W=10, ze=2.0, mh=5, slip_bps=5, rule=RULE)) == 0


def test_size_liquidity_screen_unit_cases():
    assert size_liquidity_ok(10, 1000, 1000) == (True, 0.01)
    assert size_liquidity_ok(10, 100, 1000)[0] is False              # 10% of volume > 5%
    assert size_liquidity_ok(1, MIN_VOLUME_LOTS - 1, 1000)[0] is False   # below the volume floor
    assert size_liquidity_ok(1, 1000, MIN_OI_LOTS - 1)[0] is False       # open interest screen
    assert size_liquidity_ok(1, float('nan'), 1000) == (False, float('inf'))   # missing volume
    assert size_liquidity_ok(1, 0, 1000)[0] is False
    assert size_liquidity_ok(1, 1000, None)[0] is False


def test_lots_differ_by_leg_because_contract_sizes_differ():
    grams, la, lb = intended_lots('GOLDM', 'GOLDPETAL', 13_000.0)
    assert grams == 100 and la == 1 and lb == 100
    grams, la, lb = intended_lots('GOLDM', 'GOLDGUINEA', 13_000.0)
    assert grams % 200 == 0 and la == grams / 100 and lb == grams / 8


def test_no_position_opens_close_to_a_tender_window():
    # the only unusual day is 8 trading days before expiry: too close (the rule needs MIN_ENTRY_TD = 9)
    ps, P, dates, tdi = _synthetic()
    sig_td = int(ps.loc[28, 'td_to_exp_a'])
    off = 0
    while sig_td >= min_entry_td('GOLDGUINEA', ps.loc[0, 'expiry_a']):
        off += 1
        ps2, P2, d2, t2 = _synthetic(exp_offset=60 - off)
        sig_td = int(ps2.loc[28, 'td_to_exp_a'])
    t = run_pair_backtest('GUINEA_PETAL', ps2, P2, d2, t2, W=10, ze=2.0, mh=5, slip_bps=5, rule=RULE)
    assert len(t) == 0


def test_open_position_is_closed_before_the_tender_window_with_exit_costs():
    # a long holding limit and an expiry soon after entry: the calendar closes the trade, not the z-score
    ps, P, dates, tdi = _synthetic(n=60, spike_day=28, exp_offset=None or 60)
    # find an expiry that lets the trade open and then forces it out
    for off in range(0, 25):
        ps, P, dates, tdi = _synthetic(n=60, spike_day=28, exp_offset=60 - off)
        ps.loc[29:, 'spread'] = 3.0          # gap never closes, so only the calendar (or time) can end it
        t = run_pair_backtest('GUINEA_PETAL', ps, P, dates, tdi, W=10, ze=2.0, mh=40, slip_bps=5,
                              rule=dict(RULE, entry_band=False))
        if len(t) and t.iloc[0]['reason'] == 'tender':
            break
    tr = t.iloc[0]
    assert tr['reason'] == 'tender'
    assert tr['td_exit_a'] >= tr['tender_td_a'] and tr['td_exit_b'] >= tr['tender_td_b']
    assert tr['cost_exit'] > 0 and abs(tr['net'] - (tr['gross'] - tr['cost_entry'] - tr['cost_exit'])) < 1e-6


def test_both_legs_are_checked_independently(monkeypatch):
    real = CR.tender_rule

    def longer_for_petal(sym, exp):
        r = dict(real(sym, exp))
        if sym == 'GOLDPETAL':
            r['applied_td'] = 12
        return r
    monkeypatch.setattr(CR, 'tender_rule', longer_for_petal)
    e = pd.Timestamp('2025-06-30')
    # leg A is far enough from its window; leg B (with its own, longer window) is not
    assert entry_timing_ok('GOLDGUINEA', e, 15, 'GOLDPETAL', e, 15) is False
    assert entry_timing_ok('GOLDGUINEA', e, 15, 'GOLDPETAL', e, 16) is True
    assert entry_timing_ok('GOLDGUINEA', e, 8, 'GOLDPETAL', e, 30) is False


def test_every_contract_has_its_own_tender_rule_lookup():
    for sym in ('GOLDM', 'GOLDTEN', 'GOLDGUINEA', 'GOLDPETAL'):
        r = CR.tender_rule(sym, '2026-02-27')
        assert r['applied_td'] >= (r['reported_td'] or 0) and r['applied_td'] == CR.CONSERVATIVE_TENDER_TD
    # what the sources report differs by contract and by period, and the table keeps those differences
    assert CR.tender_rule('GOLDPETAL', '2026-02-27')['reported_td'] == 3
    assert CR.tender_rule('GOLDPETAL', '2025-10-31')['reported_td'] == 5
    assert CR.tender_rule('GOLDM', '2026-02-05')['status'] == 'unverified'
    assert not any(r.status == 'official' for r in CR.TENDER_REPORTED), 'nothing was read in an MCX document'


# ------------------------------------------------------------------ the real rule on our download
def test_real_trades_never_open_or_close_inside_a_tender_window():
    c = _real()
    t = c['trades'][c['trades']['slip'] == BASE_SLIPPAGE]
    assert len(t) > 0
    P = c['P']
    for _, tr in t.iterrows():
        a, b, _ = PAIR_DEFINITIONS[tr['pair']]
        for sym, exp, tw in ((a, pd.Timestamp(tr['expA']), tr['tender_td_a']), (b, pd.Timestamp(tr['expB']), tr['tender_td_b'])):
            td_in = P.loc[(sym, exp, tr['entry']), 'td_to_exp']
            td_out = P.loc[(sym, exp, tr['exit']), 'td_to_exp']
            assert td_in >= tw + EXIT_LEAD_TD + 1, f'{tr["pair"]} {tr["entry"]}: opened {td_in} days before {sym} expiry'
            assert td_out >= tw, f'{tr["pair"]} {tr["exit"]}: still open inside the {sym} tender window'
    assert set(t['lifecycle']) <= {'official', 'conservative-secondary', 'conservative-unverified'}


def test_real_fills_respect_the_participation_cap_on_both_legs():
    c = _real()
    t = c['trades'][c['trades']['slip'] == BASE_SLIPPAGE]
    P = c['P']
    for _, tr in t.iterrows():
        a, b, _ = PAIR_DEFINITIONS[tr['pair']]
        for sym, exp, lots in ((a, pd.Timestamp(tr['expA']), tr['lots_a']), (b, pd.Timestamp(tr['expB']), tr['lots_b'])):
            assert lots / P.loc[(sym, exp, tr['entry']), 'vol'] <= MAX_PARTICIPATION + 1e-12
            if not tr['forced_fill']:
                assert lots / P.loc[(sym, exp, tr['exit']), 'vol'] <= MAX_PARTICIPATION + 1e-12
    assert t['part_entry'].max() <= MAX_PARTICIPATION


def test_live_gates_and_backtest_agree_on_every_signal_day():
    c = _real()
    t = c['trades'][c['trades']['slip'] == BASE_SLIPPAGE]
    for pid, g in t.groupby('pair'):
        W, ze = int(c['best'].loc[pid, 'W']), float(c['best'].loc[pid, 'ze'])
        x = compute_rolling_z(c['pairs'][pid], W).set_index('date')
        a, b, _ = PAIR_DEFINITIONS[pid]
        for _, tr in g.iterrows():
            row = x.loc[tr['sig']]
            assert abs(row['z'] - tr['z']) < 0.006, 'backtest and chart z-scores differ'
            sig, failed, gates = evaluate_pair_gates(row, W=W, ze=ze, round_trip_cost_bps=24.38, sym_a=a, sym_b=b)
            assert gates['lifecycle'] and gates['extreme'] and gates['edge_beats_cost'], (pid, tr['sig'], failed)


def test_backtest_is_reproducible():
    c = _real()
    pid = 'M_PETAL'
    W, ze, mh = int(c['best'].loc[pid, 'W']), float(c['best'].loc[pid, 'ze']), int(c['best'].loc[pid, 'mh'])
    one = run_pair_backtest(pid, c['pairs'][pid], c['P'], c['dates'], c['tdi'], W, ze, mh, slip_bps=5, rule=ALERT_RULE)
    two = run_pair_backtest(pid, c['pairs'][pid], c['P'], c['dates'], c['tdi'], W, ze, mh, slip_bps=5, rule=ALERT_RULE)
    pd.testing.assert_frame_equal(one, two)


def test_one_rolling_statistics_definition():
    c = _real()
    for pid, x in c['pairs'].items():
        if x.empty:
            continue
        mu, sd, z = rolling_stats(x, 20)
        plain = x['spread'].rolling(20).mean().shift(1)
        assert np.allclose(mu.dropna(), plain.dropna()), 'no >10-day gaps in the data, so both policies must agree'
        # no look-ahead: the statistics for day t do not change if day t's spread changes
        y = x.copy()
        y.loc[y.index[-1], 'spread'] += 1e6
        mu2, sd2, _ = rolling_stats(y, 20)
        assert mu2.iloc[-1] == mu.iloc[-1] and sd2.iloc[-1] == sd.iloc[-1]
    # a long gap restarts the window
    d = pd.DataFrame({'date': list(pd.bdate_range('2024-01-01', periods=5)) + list(pd.bdate_range('2024-03-01', periods=5)),
                      'spread': np.arange(10.0)})
    mu, _, _ = rolling_stats(d, 3)
    assert mu.iloc[5:8].isna().all() and not np.isnan(mu.iloc[8])


def test_carry_reference_skips_contracts_in_their_tender_window():
    c = _real()
    ch = c['chosen']
    win = ch['expiry_n'].map(lambda e: CR.tender_rule('GOLDPETAL', e)['applied_td'])
    assert (ch['td_to_exp_n'] >= win).all()
    assert 'unstable' in ch.columns
