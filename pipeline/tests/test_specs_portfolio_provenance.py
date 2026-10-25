"""Oct-2026 compliance audit: date-effective specifications (Priority 3), portfolio reporting (Priority 6) and
provenance (Priority 8)."""
import hashlib
import json
import os
import subprocess

import numpy as np
import pandas as pd

import pipeline.contract_rules as CR
from pipeline.backtest import prepare_contract_lookup, run_pair_backtest
from pipeline.carry import compute_reference_carry
from pipeline.config import ALERT_RULE, TEST_END
from pipeline.load import load_clean_bhavcopy
from pipeline.pairs import build_all_pairs
from pipeline.portfolio import daily_trade_pnl, nw_tstat
from pipeline.provenance import manifest

DATA = 'frontend/public/data'


# ------------------------------------------------------------------ specifications
def test_spec_effective_date_boundaries():
    assert CR.spec_for('GOLDM', '2023-10-09')[1] == 'assumed'
    assert CR.spec_for('GOLDM', '2023-10-10')[1] == 'secondary'
    assert CR.spec_for('GOLDTEN', '2025-03-30') == (None, 'unavailable')
    r, s = CR.spec_for('GOLDTEN', '2025-03-31')
    assert s == 'secondary' and (r.lot_grams, r.quote_grams, r.purity) == (10, 10, 0.999)
    r, _ = CR.spec_for('GOLDPETAL', '2012-01-02')
    assert (r.quote_grams, r.purity) == (1, 0.999) and r.status == 'assumed'
    assert not any(r.status == 'official' for r in CR.SPEC_TABLE), 'no MCX document was read'
    # every symbol's rows cover time without overlap
    for sym in ('GOLDM', 'GOLDGUINEA', 'GOLDPETAL', 'GOLDTEN'):
        rows = CR.spec_rows(sym)
        for a, b in zip(rows, rows[1:]):
            assert pd.Timestamp(a.end) < pd.Timestamp(b.start)


def test_apply_specs_marks_rows_and_keeps_every_row():
    df = pd.DataFrame({'symbol': ['GOLDTEN', 'GOLDTEN', 'GOLDM', 'GOLDM'],
                       'date': pd.to_datetime(['2025-01-02', '2025-04-01', '2015-06-01', '2026-01-02'])})
    out = CR.apply_specs(df)
    assert len(out) == 4
    assert list(out['spec_status']) == ['unavailable', 'secondary', 'assumed', 'secondary']


def test_normalisation_divides_by_quote_grams_and_purity_once():
    df, _, _ = load_clean_bhavcopy('data/raw/gold_bhavcopy_clean.csv', end=TEST_END)
    r = df[df['symbol'] == 'GOLDM'].iloc[0]
    assert abs(r['px_per_g_pure'] - r['close'] / 10 / 0.995) < 1e-9
    r = df[df['symbol'] == 'GOLDPETAL'].iloc[0]
    assert abs(r['px_per_g_pure'] - r['close'] / 1 / 0.999) < 1e-9
    assert set(df['spec_status']) == {'secondary'}       # our download period


def test_history_rows_are_marked_assumed_not_verified():
    from pipeline.history import BOOK_PATH, OURS_PATH, history_frame, load_book
    book = load_book(BOOK_PATH)
    end = pd.read_csv(OURS_PATH, parse_dates=['date'])['date'].min() - pd.Timedelta(days=1)
    hdf = history_frame(book, end)[0]
    assert set(hdf['spec_status']) == {'assumed'}


# ------------------------------------------------------------------ portfolio
def test_daily_mark_to_market_adds_up_to_each_trade():
    df, dates, tdi = load_clean_bhavcopy('data/raw/gold_bhavcopy_clean.csv', end=TEST_END)
    carry, _ = compute_reference_carry(df, dates)
    pairs = build_all_pairs(df, carry)
    P = prepare_contract_lookup(df)
    t = run_pair_backtest('M_PETAL', pairs['M_PETAL'], P, dates, tdi, 30, 2.0, 10, slip_bps=5, rule=ALERT_RULE)
    assert len(t) > 3
    trades = t.to_dict('records')
    rows = daily_trade_pnl(trades, P, dates)
    for k, tr in enumerate(trades):
        r = rows[rows['trade'] == k]
        assert abs(r['gross'].sum() - tr['gross']) < 0.01, 'daily marks must add up to the trade result'
        assert abs(r['gold'].sum() - tr['gold']) < 0.01
        assert abs(r['cost'].sum() - tr['cost']) < 1e-6
        assert r['open'].iloc[0] == 0 and r['open'].iloc[1:].eq(1).all()


def test_newey_west_t_is_smaller_than_naive_for_overlapping_pnl():
    rng = np.random.default_rng(0)
    e = rng.normal(0.1, 1, 2000)
    x = np.convolve(e, np.ones(10), mode='valid')      # 10-day overlapping sums: strongly autocorrelated
    naive = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    assert abs(nw_tstat(x)) < abs(naive)


def test_portfolio_file_reconciles_with_the_trades():
    p = json.load(open(os.path.join(DATA, 'portfolio.json'), encoding='utf-8'))
    c = p['check']
    assert abs(c['sum_of_daily_net_rs'] - c['sum_of_trade_net_rs']) < 1.0 * c['trades']   # trade nets are rounded to 0.1
    allp = p['periods']['all']
    assert allp['n_trades'] == c['trades']
    parts = sum(p['periods'][k]['n_trades'] for k in ('clean', 'train', 'test', 'forward'))
    assert parts == allp['n_trades']
    assert 'margin is not modelled' in p['basis']
    assert len(p['daily']['d']) == len(p['daily']['cum']) == len(p['daily']['open'])


# ------------------------------------------------------------------ provenance
def test_manifest_hashes_match_the_files_in_git():
    files = {m['file']: m for m in manifest()}
    for name in ('data/raw/retrieval_log.csv', 'data/raw/mcx_bhavcopy_supplement.csv'):
        blob = subprocess.check_output(['git', 'show', f'HEAD:{name}'])
        assert files[name]['sha256'] == hashlib.sha256(blob).hexdigest()
    roles = {m['role'] for m in files.values()}
    assert {'raw', 'derived'} <= roles
    assert files['data/raw/gold_bhavcopy_clean.csv']['role'] == 'derived'


def test_provenance_file_states_the_limits_plainly():
    p = json.load(open(os.path.join(DATA, 'provenance.json'), encoding='utf-8'))
    assert 'does not show where the data came from' in p['hash_note']
    assert '"Close" field' in p['price_field'] and 'not verified' in p['price_field']
    assert p['rules']['conservative_tender_td'] == CR.CONSERVATIVE_TENDER_TD
