"""Tests for the Oct-2026 audit fixes (Section 5.9): one rule for alerts and backtest."""
import pytest
import numpy as np
import pandas as pd
from pipeline.load import load_clean_bhavcopy
from pipeline.config import TEST_END   # research snapshot: a data refresh must not change these checks
from pipeline.carry import compute_reference_carry
from pipeline.pairs import build_all_pairs
from pipeline.backtest import (prepare_contract_lookup, run_grid_search, run_all_scenarios,
                               walk_forward_switch, hurdle_bps)
from pipeline.alerts import evaluate_pair_gates
from pipeline.attribution import compute_attribution_metrics, calculate_round_trip_cost_bps
from pipeline.config import (ALERT_RULE, PAIR_DEFINITIONS, STOP_Z_BUFFER, MAX_FILL_MOVE,
                             MIN_TRAIN_TRADES, BASE_SLIPPAGE)

_CACHE = {}

def _run():
    if not _CACHE:
        df, dates, tdi = load_clean_bhavcopy('data/raw/gold_bhavcopy_clean.csv', end=TEST_END)
        carry, _ = compute_reference_carry(df, dates)
        pairs = build_all_pairs(df, carry)
        P = prepare_contract_lookup(df)
        _, best = run_grid_search(pairs, P, dates, tdi, rule=ALERT_RULE)
        trades, _ = run_all_scenarios(pairs, best, P, dates, tdi, rule=ALERT_RULE)
        _CACHE.update(df=df, dates=dates, tdi=tdi, pairs=pairs, P=P, best=best, trades=trades)
    return _CACHE

def test_every_backtest_trade_passed_the_alert_checks():
    """Each trade's signal day had an unusual gap below the stop-loss AND a gap beating the cost line."""
    c = _run()
    h = hurdle_bps()
    assert abs(h - 2 * calculate_round_trip_cost_bps(BASE_SLIPPAGE)) < 1e-9
    t = c['trades'][c['trades']['slip'] == BASE_SLIPPAGE]
    assert len(t) > 0
    for pid, g in t.groupby('pair'):
        W, ze = int(c['best'].loc[pid, 'W']), float(c['best'].loc[pid, 'ze'])
        x = c['pairs'][pid].copy()
        x['mu'] = x['spread'].rolling(W).mean().shift(1)
        x = x.set_index('date')
        for _, tr in g.iterrows():
            row = x.loc[tr['sig']]
            assert ze <= abs(tr['z']) < ze + STOP_Z_BUFFER + 0.01, f"{pid} {tr['sig']} z={tr['z']} outside entry band"
            assert abs(row['spread'] - row['mu']) >= h - 1e-6, f"{pid} {tr['sig']} gap below cost line"

def test_no_fills_on_extreme_move_days_and_no_same_close_exits():
    c = _run()
    P = c['P']
    t = c['trades'][c['trades']['slip'] == BASE_SLIPPAGE]
    for _, tr in t.iterrows():
        a, b, _ = PAIR_DEFINITIONS[tr['pair']]
        for sym, exp in ((a, pd.Timestamp(tr['expA'])), (b, pd.Timestamp(tr['expB']))):
            assert abs(P.loc[(sym, exp, tr['entry']), 'day_move']) < MAX_FILL_MOVE
            # Exception (Oct-2026 lifecycle fix): a position that must be closed before a tender window is closed on
            # the last allowed day even after a big move, and the trade is flagged forced_fill
            if not tr['forced_fill']:
                assert abs(P.loc[(sym, exp, tr['exit']), 'day_move']) < MAX_FILL_MOVE
        assert tr['exit'] > tr['exit_sig'], 'exit filled at the signal close'
        assert tr['entry'] > tr['sig']
    forced = t[t['forced_fill']]
    assert (forced['reason'] == 'tender').all() and len(forced) <= max(1, len(t) // 20), 'forced exits must be rare and calendar-driven'

def test_max_drawdown_counts_an_opening_loss():
    t = pd.DataFrame({'net': [-100.0, 50.0], 'gross': [0.0, 60.0], 'cost': [100.0, 10.0],
                      'spread_pnl': [0.0, 60.0], 'gold': [0.0, 0.0], 'gross_bps': [0.0, 6.0],
                      'net_bps': [-10.0, 5.0], 'days': [1, 1],
                      'exit': pd.to_datetime(['2026-01-02', '2026-01-05'])})
    assert compute_attribution_metrics(t)['max_drawdown_rs'] == 100.0

def test_switch_uses_training_only():
    base = dict(slip=BASE_SLIPPAGE, pair='M_PETAL')
    train = [dict(base, seg='train', net=10.0) for _ in range(MIN_TRAIN_TRADES)]
    test_good = [dict(base, seg='test', net=1e6)]
    test_bad = [dict(base, seg='test', net=-1e6)]
    s1 = walk_forward_switch(pd.DataFrame(train + test_good), ['M_PETAL'])
    s2 = walk_forward_switch(pd.DataFrame(train + test_bad), ['M_PETAL'])
    assert s1 == s2 and s1['M_PETAL']['on'] is True
    few = walk_forward_switch(pd.DataFrame(train[:MIN_TRAIN_TRADES - 1]), ['M_PETAL'])
    assert few['M_PETAL']['on'] is False

def test_alert_refuses_a_gap_already_past_the_stop():
    row = pd.Series({'z': 2.0 + STOP_Z_BUFFER + 0.1, 'mu': 0.0, 'spread': 200.0, 'vol_a': 1000, 'vol_b': 1000,
                     'oi_a': 1000, 'oi_b': 1000, 'td_to_exp_a': 20, 'td_to_exp_b': 20, 'roll': False})
    sig, failed, gates = evaluate_pair_gates(row, W=20, ze=2.0, round_trip_cost_bps=24.4)
    assert not sig and 'extreme' in failed
