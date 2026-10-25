"""Precomputes all static JSON datasets for the frontend (Sections 8.1 & 11)."""
import os
import json
import datetime
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional

from pipeline.config import (
    CONTRACT_SPECS,
    SPEC_TUPLES,
    PAIR_DEFINITIONS,
    PAIRS,
    TRAIN_START,
    TRAIN_END,
    TEST_START,
    TEST_END,
    segment_of,
    BASE_SLIPPAGE,
    SLIPPAGE_SCENARIOS,
    NOTIONAL_PER_LEG,
    LEGACY_RULE,
    ALERT_RULE,
    HURDLE_MULTIPLE,
    STOP_Z_BUFFER,
    MAX_FILL_MOVE,
    MIN_TRAIN_TRADES,
    CARRY_SANE_LO,
    CARRY_SANE_HI,
    MIN_ENTRY_TD,
    EXIT_LEAD_TD,
    MAX_PARTICIPATION,
)
from pipeline.contract_rules import CONSERVATIVE_TENDER_TD
from pipeline.load import load_clean_bhavcopy
from pipeline.carry import compute_reference_carry, compute_carry_decomposition
from pipeline.pairs import build_all_pairs, compute_rolling_z
from pipeline.backtest import (
    prepare_contract_lookup,
    run_grid_search,
    run_all_scenarios,
    run_pair_backtest,
    walk_forward_switch,
    hurdle_bps,
)
from pipeline.attribution import (
    calculate_round_trip_cost_bps,
    compute_attribution_metrics,
    compute_t_stat_and_ci,
)
from pipeline.alerts import generate_today_alerts, generate_signals_history
from pipeline.lifecycle import compute_contract_lifecycle, calendar_check

class CustomJSONEncoder(json.JSONEncoder):
    """Encodes numpy and pandas data types safely to standard JSON."""
    def default(self, obj):
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        elif isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (pd.Timestamp, datetime.date, datetime.datetime)):
            return obj.strftime('%Y-%m-%d')
        elif pd.isna(obj):
            return None
        return super().default(obj)

def save_json(filepath: str, data: Any):
    """Writes data to filepath as JSON, ensuring parent directories exist."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, cls=CustomJSONEncoder)

def cross_check_raw_vs_clean(df: pd.DataFrame, raw_path: str = 'data/raw/mcx_bhavcopy_raw_api.csv') -> Dict[str, Any]:
    """Compares every row of the raw MCX download with the cleaned dataset the pipeline uses.
    Replaces an earlier hard-coded 'verified' claim with a check that runs on every build."""
    if not os.path.exists(raw_path):
        return {'raw_rows': 0, 'matched_rows': 0, 'mismatches': None,
                'status': 'Raw file not present in this build; cross-check not run.'}
    raw = pd.read_csv(raw_path)
    sup_path = os.path.join(os.path.dirname(raw_path), 'mcx_bhavcopy_supplement.csv')
    n_sup = 0
    if os.path.exists(sup_path):                     # rows our download missed, from the MCX history book
        sup = pd.read_csv(sup_path)
        n_sup = len(sup)
        raw = pd.concat([raw, sup[[c for c in raw.columns]]], ignore_index=True)
    raw['date'] = pd.to_datetime(raw['Date'], format='%m/%d/%Y')
    raw['expiry'] = pd.to_datetime(raw['ExpiryDate'], format='%d%b%Y')
    raw['symbol'] = raw['Symbol'].astype(str).str.strip()
    m = raw.merge(df[['symbol', 'expiry', 'date', 'open', 'close', 'vol', 'oi']],
                  on=['symbol', 'expiry', 'date'], how='outer', indicator=True)
    both = m[m['_merge'] == 'both']
    bad = ((both['Close'] != both['close']) | (both['Open'] != both['open'])
           | (both['Volume'] != both['vol']) | (both['OpenInterest'] != both['oi']))
    only_raw = int((m['_merge'] == 'left_only').sum())
    only_clean = int((m['_merge'] == 'right_only').sum())
    n_bad = int(bad.sum()) + only_raw + only_clean
    return {
        'raw_rows': int(len(raw)), 'supplement_rows': int(n_sup),
        'matched_rows': int(len(both)),
        'value_mismatches': int(bad.sum()),
        'rows_only_in_raw': only_raw,
        'rows_only_in_clean': only_clean,
        'mismatches': n_bad,
        'fields_compared': ['open', 'close', 'volume_lots', 'open_interest_lots'],
        'status': (f"Raw MCX rows vs cleaned data: {len(both):,} rows compared on open, close, volume and OI "
                   f"({n_sup} of them from the MCX history book, filling gaps in our download), "
                   f"{n_bad} mismatch{'es' if n_bad != 1 else ''}. Runs on every build."),
    }

def supplement_summary(path: str = 'data/raw/mcx_bhavcopy_supplement.csv') -> Dict[str, Any]:
    """What the history-book supplement adds to our MCX download (see pipeline/download.py)."""
    if not os.path.exists(path):
        return {'rows': 0, 'missing_contracts': [], 'extra_days': []}
    s = pd.read_csv(path)
    miss = s[s['Source'].str.contains('missing', case=False)]
    later = s[s['Source'].str.contains('after', case=False)]
    keys = miss.groupby(['Symbol', 'ExpiryDate']).size().reset_index()
    return {
        'rows': int(len(s)), 'missing_rows': int(len(miss)), 'extra_day_rows': int(len(later)),
        'missing_contracts': [f"{r.Symbol} {pd.to_datetime(r.ExpiryDate, format='%d%b%Y').strftime('%b %Y')}" for r in keys.itertuples()],
        'extra_days': sorted(pd.to_datetime(later['Date'], format='%m/%d/%Y').dt.strftime('%Y-%m-%d').unique().tolist()),
    }

CRASH_START, CRASH_END, CRASH_LABEL = '2026-01-01', '2026-03-31', 'Jan–Mar 2026 crash'

def _tstat(x: pd.Series) -> Optional[float]:
    x = pd.Series(x, dtype=float)
    if len(x) < 3 or x.std(ddof=1) == 0:
        return None
    return round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2)

def summarize_rule(trades: pd.DataFrame, switch: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Train/Test totals per slippage, the crash split and (if given) the walk-forward switch result."""
    out: Dict[str, Any] = {}
    for slip in SLIPPAGE_SCENARIOS:
        a = trades[trades['slip'] == slip] if len(trades) else trades
        tr = a[a['seg'] == 'train'] if len(a) else a
        te = a[a['seg'] == 'test'] if len(a) else a
        crash = te[(te['exit'] >= CRASH_START) & (te['exit'] <= CRASH_END)] if len(te) else te
        rest = te.drop(crash.index) if len(te) else te
        fw = a[a['seg'] == 'forward'] if len(a) else a
        row = {
            'train_n': int(len(tr)), 'train_net_rs': round(float(tr['net'].sum()), 1) if len(tr) else 0.0,
            'train_avg_bps': round(float(tr['net_bps'].mean()), 1) if len(tr) else None,
            'test_n': int(len(te)), 'test_net_rs': round(float(te['net'].sum()), 1) if len(te) else 0.0,
            'test_avg_bps': round(float(te['net_bps'].mean()), 1) if len(te) else None,
            'test_t': _tstat(te['net_bps']) if len(te) else None,
            'test_hit': round(float((te['net'] > 0).mean()), 3) if len(te) else None,
            'crash_n': int(len(crash)), 'crash_net_rs': round(float(crash['net'].sum()), 1) if len(crash) else 0.0,
            'ex_crash_n': int(len(rest)), 'ex_crash_net_rs': round(float(rest['net'].sum()), 1) if len(rest) else 0.0,
            'ex_crash_t': _tstat(rest['net_bps']) if len(rest) else None,
            'forward_n': int(len(fw)), 'forward_net_rs': round(float(fw['net'].sum()), 1) if len(fw) else 0.0,
            'forward_t': _tstat(fw['net_bps']) if len(fw) else None,
        }
        if switch is not None:
            on = [k for k, v in switch.items() if v['on']]
            ton = te[te['pair'].isin(on)] if len(te) else te
            row.update({'switched_on_pairs': on, 'switched_on_n': int(len(ton)),
                        'switched_on_net_rs': round(float(ton['net'].sum()), 1) if len(ton) else 0.0})
        out[str(slip)] = row
    return out

def build_all_site_data(output_dir: str = 'frontend/public/data'):
    """Executes the full pipeline and writes all Section 8.1 JSON files."""
    print("--- 1. Loading and normalizing Bhavcopy data ---")
    df, dates, tdi = load_clean_bhavcopy('data/raw/gold_bhavcopy_clean.csv')
    last_date = dates[-1]
    last_date_str = pd.Timestamp(last_date).strftime('%Y-%m-%d')
    P = prepare_contract_lookup(df)
    
    print("--- 2. Computing reference carry & decomposition ---")
    carry_series, chosen_pet_ref = compute_reference_carry(df, dates)
    decomp_df = compute_carry_decomposition(df, carry_series, chosen_pet_ref)
    
    print("--- 3. Constructing pair series ---")
    pairs_dict = build_all_pairs(df, carry_series)
    
    print("--- 4. Running grid search on Train & selecting parameters (same rule as the alerts) ---")
    grid_df, best_params = run_grid_search(pairs_dict, P, dates, tdi, rule=ALERT_RULE)
    print("Chosen parameters on TRAIN (5 bps slippage):")
    print(best_params)
    
    print("--- 5. Simulating walk-forward backtest across slippage scenarios ---")
    all_trades_df, summary_df = run_all_scenarios(pairs_dict, best_params, P, dates, tdi, rule=ALERT_RULE)
    switch = walk_forward_switch(all_trades_df, list(pairs_dict.keys()))
    print("Walk-forward switch (decided on Train only):", {k: v['on'] for k, v in switch.items()})

    # Original study (4 checks, no cost gate) kept only for comparison on the site
    legacy_grid_df, legacy_params = run_grid_search(pairs_dict, P, dates, tdi, rule=LEGACY_RULE)
    legacy_trades_df, _ = run_all_scenarios(pairs_dict, legacy_params, P, dates, tdi, rule=LEGACY_RULE)
    
    print("--- 6. Computing alerts & contract lifecycle ---")
    alerts_today = generate_today_alerts(pairs_dict, best_params, switch=switch)
    signals_history = generate_signals_history(all_trades_df)
    lifecycle_df = compute_contract_lifecycle(df)
    
    print(f"--- 7. Writing JSON files to {output_dir} ---")
    
    # 7.1 meta.json
    weekend_dates = [pd.Timestamp(d).strftime('%Y-%m-%d') for d in dates if pd.Timestamp(d).weekday() >= 5]
    raw_check = cross_check_raw_vs_clean(df)
    # Latest quotes for replacement tape (Section 10.2)
    latest_quotes = []
    for sym in ['GOLDM', 'GOLDTEN', 'GOLDGUINEA', 'GOLDPETAL']:
        sym_df = df[(df['symbol'] == sym) & (df['date'] == last_date)].sort_values('oi', ascending=False)
        if not sym_df.empty:
            row = sym_df.iloc[0]
            # Day change
            prev_row = df[(df['symbol'] == sym) & (df['expiry'] == row['expiry']) & (df['date'] < last_date)].sort_values('date')
            prev_close = prev_row.iloc[-1]['close'] if not prev_row.empty else row['prev_close']
            chg = row['close'] - prev_close
            chg_pct = (chg / prev_close) * 100.0 if prev_close > 0 else 0.0
            latest_quotes.append({
                'symbol': sym,
                'close': float(row['close']),
                'quote_grams': CONTRACT_SPECS[sym].quote_grams,
                'px_per_10g_pure': round(float(row['px_per_10g_pure']), 2),
                'change_rs': round(float(chg), 2),
                'change_pct': round(float(chg_pct), 2),
                'expiry': row['expiry'].strftime('%Y-%m-%d'),
                'vol': int(row['vol']),
                'oi': int(row['oi']),
            })
            
    meta_data = {
        'coverage_start': pd.Timestamp(dates[0]).strftime('%Y-%m-%d'),
        'coverage_end': last_date_str,
        'trading_dates_count': len(dates),
        'rows_count': len(df),
        'contracts_count': len(lifecycle_df),
        'no_trade_rows_count': int(df['no_trade'].sum()),
        'thin_rows_count': int(df['thin'].sum()),
        'weekend_sessions': weekend_dates,
        'raw_cross_check': raw_check,
        'supplement': supplement_summary(),
        'num_contracts': len(CONTRACT_SPECS),
        'num_pairs': len(PAIRS),
        'unseen_test_months': 12,
        'latest_quotes': latest_quotes,
        'build_time': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source': f"MCX Bhavcopy (EOD) · Data to {pd.Timestamp(last_date).strftime('%d-%b-%Y')}",
    }
    save_json(os.path.join(output_dir, 'meta.json'), meta_data)
    
    # 7.2 contracts.json
    contracts_data = {
        'contract_master': {
            sym: {
                'symbol': spec.symbol,
                'lot_grams': spec.lot_grams,
                'quote_grams': spec.quote_grams,
                'purity': spec.purity,
                'expiry_window': spec.expiry_window,
                'tick_size': spec.tick_size,
            }
            for sym, spec in CONTRACT_SPECS.items()
        },
        'lifecycle': lifecycle_df.to_dict(orient='records'),
        # every published trade (5 bps, all periods of our download) checked against its contracts' calendars
        'calendar': calendar_check(all_trades_df[all_trades_df['slip'] == BASE_SLIPPAGE], lifecycle_df),
    }
    save_json(os.path.join(output_dir, 'contracts.json'), contracts_data)
    
    # 7.3 prices/{SYMBOL}.json
    for sym in CONTRACT_SPECS:
        sym_df = df[df['symbol'] == sym].sort_values(['expiry', 'date'])
        # To keep payload compact, format clean records
        price_records = [
            {
                'd': row['date'].strftime('%Y-%m-%d'),
                'e': row['expiry'].strftime('%Y-%m-%d'),
                'c': round(float(row['close']), 2),
                'p': round(float(row['px_per_g_pure']), 2),
                'p10': round(float(row['px_per_10g_pure']), 2),
                'v': int(row['vol']),
                'oi': int(row['oi']),
                'nt': bool(row['no_trade']),
                'th': bool(row['thin']),
                'td': int(row['td_to_exp']),
            }
            for _, row in sym_df.iterrows()
        ]
        save_json(os.path.join(output_dir, f'prices/{sym}.json'), price_records)
        
    # 7.4 curve.json
    ref_carry_records = [
        {'date': d.strftime('%Y-%m-%d'), 'carry_pct': round(float(val) * 100.0, 3)}
        for d, val in carry_series.items()
    ]
    # Sample curves on selected milestone dates
    # The latest curve and one about a month (21 trading days) earlier, for the Market page's term-structure view,
    # plus the older milestone dates; all computed from the data (never typed in)
    month_ago = pd.Timestamp(dates[max(0, len(dates) - 1 - 21)])
    sample_dates = [
        pd.Timestamp('2024-03-28'),
        pd.Timestamp('2024-09-30'),
        pd.Timestamp('2025-03-31'),
        pd.Timestamp('2025-09-30'),
        pd.Timestamp('2026-03-31'),
        month_ago,
        pd.Timestamp(last_date),
    ]
    curve_snapshots = []
    for s_date in sorted(set(sample_dates)):
        snap_df = df[df['date'] == s_date]
        if snap_df.empty:
            continue
        c_items = []
        for _, row in snap_df.sort_values('expiry').iterrows():
            c_items.append({
                'symbol': row['symbol'],
                'expiry': row['expiry'].strftime('%Y-%m-%d'),
                'days_to_exp': int((row['expiry'] - row['date']).days),
                'td_to_exp': int(row['td_to_exp']),
                'px_per_g_pure': round(float(row['px_per_g_pure']), 2),
                'px_per_10g_pure': round(float(row['px_per_10g_pure']), 2),
                'close': round(float(row['close']), 2),
                'oi': int(row['oi']),
                'vol': int(row['vol']),
                'no_trade': bool(row['no_trade']),
                'thin': bool(row['thin']),
                'spec_status': str(row['spec_status']),
            })
        ref = chosen_pet_ref.loc[s_date] if s_date in chosen_pet_ref.index else None
        curve_snapshots.append({
            'date': s_date.strftime('%Y-%m-%d'),
            'reference_carry_pct': round(float(carry_series.get(s_date, 0.06)) * 100.0, 2),
            # which GOLDPETAL calendar spread gave the carry that day (None: carried forward from an earlier day)
            'carry_from': None if ref is None else {'near': ref['expiry_n'].strftime('%Y-%m-%d'), 'far': ref['expiry_f'].strftime('%Y-%m-%d'),
                                                    'unstable': bool(ref['unstable'])},
            'contracts': c_items,
        })
        
    curve_data = {
        'median_carry_pct': round(float(chosen_pet_ref['c'].median() * 100.0), 2),
        'iqr_carry_pct': [
            round(float(chosen_pet_ref['c'].quantile(0.25) * 100.0), 2),
            round(float(chosen_pet_ref['c'].quantile(0.75) * 100.0), 2),
        ],
        'reference_carry_series': ref_carry_records,
        'snapshots': curve_snapshots,
        'latest': pd.Timestamp(last_date).strftime('%Y-%m-%d'),
        'month_ago': month_ago.strftime('%Y-%m-%d'),
        'carry_unstable_days': int(chosen_pet_ref['unstable'].sum()),
        'carry_days': int(len(chosen_pet_ref)),
        'carry_sane_pct': [round(CARRY_SANE_LO * 100, 1), round(CARRY_SANE_HI * 100, 1)],
        # Decomposition of each contract's daily log price change (carry.compute_carry_decomposition), in bps a day.
        # It is an accounting identity: gold + roll-down + curve change + residual = the actual change. It describes
        # where a move came from; it does not show what caused it.
        'decomposition': {
            sym: {
                'rows': int((decomp_df['symbol'] == sym).sum()),
                'mean_abs_bps': {k: round(float(decomp_df.loc[decomp_df['symbol'] == sym, c].abs().mean() * 1e4), 2)
                                 for k, c in (('total', 'd_ln_F'), ('gold', 'gold_move'), ('rolldown', 'rolldown'),
                                              ('curve', 'curve_change'), ('residual', 'residual'))},
                'sum_bps': {k: round(float(decomp_df.loc[decomp_df['symbol'] == sym, c].sum() * 1e4), 1)
                            for k, c in (('total', 'd_ln_F'), ('gold', 'gold_move'), ('rolldown', 'rolldown'),
                                         ('curve', 'curve_change'), ('residual', 'residual'))},
                # identity check: the four parts add back to the total on every row (largest gap, bps)
                'max_identity_gap_bps': round(float((decomp_df.loc[decomp_df['symbol'] == sym, 'd_ln_F']
                                                     - decomp_df.loc[decomp_df['symbol'] == sym, ['gold_move', 'rolldown', 'curve_change', 'residual']].sum(axis=1)).abs().max() * 1e4), 6),
            } for sym in CONTRACT_SPECS if (decomp_df['symbol'] == sym).any()
        },
    }
    save_json(os.path.join(output_dir, 'curve.json'), curve_data)
    
    # 7.5 carry_decomposition/{SYMBOL}.json
    for sym in CONTRACT_SPECS:
        sub_decomp = decomp_df[decomp_df['symbol'] == sym]
        decomp_records = []
        for _, row in sub_decomp.iterrows():
            decomp_records.append({
                'd': row['date'].strftime('%Y-%m-%d'),
                'e': row['expiry'].strftime('%Y-%m-%d'),
                'p': round(float(row['px']), 2),
                'tau': round(float(row['tau']), 4),
                'd_ln_F': round(float(row['d_ln_F']) * 1e4, 2), # in bps
                'gold': round(float(row['gold_move']) * 1e4, 2), # in bps
                'rolldown': round(float(row['rolldown']) * 1e4, 2), # in bps
                'curve': round(float(row['curve_change']) * 1e4, 2), # in bps
                'residual': round(float(row['residual']) * 1e4, 2), # in bps
            })
        save_json(os.path.join(output_dir, f'carry_decomposition/{sym}.json'), decomp_records)
        
    # 7.6 pairs.json & pairs/{PAIR_ID}.json
    scanner_pairs = []
    
    for pair_id, p_df in pairs_dict.items():
        row_params = best_params.loc[pair_id]
        W, ze, mh = int(row_params['W']), float(row_params['ze']), int(row_params['mh'])
        
        # Point-in-time rolling stats
        p_calc = compute_rolling_z(p_df, W=W)
        p_calc['segment'] = segment_of(p_calc['date'].values)
        
        last_row = p_calc.iloc[-1]
        valid_z = p_calc['z'].dropna()
        
        # Empirical percentile and histogram
        curr_z = float(last_row['z'])
        empirical_pctl = float((valid_z <= curr_z).mean() * 100.0)
        
        # Empirical histogram of z (20 bins)
        counts, bin_edges = np.histogram(valid_z, bins=20)
        z_histogram = [
            {'bin_center': round(float((bin_edges[i] + bin_edges[i+1]) / 2.0), 2), 'count': int(counts[i])}
            for i in range(len(counts))
        ]
        
        # Historical evidence for Q3 card
        # Filter trades for this pair at base slippage
        pair_trades = all_trades_df[(all_trades_df['pair'] == pair_id) & (all_trades_df['slip'] == BASE_SLIPPAGE)]
        n_hist_signals = len(pair_trades)
        reverted_count = int((pair_trades['reason'] == 'revert').sum()) if n_hist_signals else 0
        stopped_count = int((pair_trades['reason'] == 'stop').sum()) if n_hist_signals else 0
        timed_out_count = int((pair_trades['reason'] == 'time').sum()) if n_hist_signals else 0
        med_days = float(pair_trades['days'].median()) if n_hist_signals else 0.0
        
        # Matching alert gate record
        alert_info = next(p for p in alerts_today['pairs'] if p['pair_id'] == pair_id)
        
        pair_spec = PAIRS[pair_id]
        scanner_pairs.append({
            'pair_id': pair_id,
            'display_name': f"{pair_spec.symbol_a} − {pair_spec.symbol_b}",
            'symbol_a': pair_spec.symbol_a,
            'symbol_b': pair_spec.symbol_b,
            'close_a': float(last_row['close_a']),
            'close_b': float(last_row['close_b']),
            'quote_grams_a': CONTRACT_SPECS[pair_spec.symbol_a].quote_grams,
            'quote_grams_b': CONTRACT_SPECS[pair_spec.symbol_b].quote_grams,
            'px_per_10g_pure_a': round(float(last_row['px_per_10g_pure_a']), 1),
            'px_per_10g_pure_b': round(float(last_row['px_per_10g_pure_b']), 1),
            'px_per_g_pure_a': round(float(last_row['px_a']), 2),
            'px_per_g_pure_b': round(float(last_row['px_b']), 2),
            'lot_ratio': pair_spec.lot_ratio_str,
            'unit_grams': pair_spec.unit_grams,
            'contracts_label': alert_info['contracts'],
            'expiry_a': alert_info['expiry_a'],
            'expiry_b': alert_info['expiry_b'],
            'spread_bps': round(float(last_row['spread']), 1),
            'spread_rs_10g': round(float(last_row['spread_rs_10g']), 1),
            'mu': round(float(last_row['mu']), 1),
            'sd': round(float(last_row['sd']), 1),
            'z': round(float(last_row['z']), 2),
            'z_needed': ze,
            'percentile': round(empirical_pctl, 1),
            'status': alert_info['status'],
            'failed_gates': alert_info['failed_gates'],
            'gates': alert_info['gates'],
            'vol_a': int(last_row['vol_a']),
            'vol_b': int(last_row['vol_b']),
            'oi_a': int(last_row['oi_a']),
            'oi_b': int(last_row['oi_b']),
            'td_to_exp_a': int(last_row['td_to_exp_a']),
            'td_to_exp_b': int(last_row['td_to_exp_b']),
            'roll_flag': bool(last_row.get('roll', False)),
            'chosen_params': {'W': W, 'ze': ze, 'mh': mh, 'zx': 0.5},
            'z_histogram': z_histogram,
            'historical_evidence': {
                'past_signals_count': n_hist_signals,
                'reverted_count': reverted_count,
                'stopped_count': stopped_count,
                'timed_out_count': timed_out_count,
                'revert_rate_pct': round((reverted_count / n_hist_signals * 100.0) if n_hist_signals else 0.0, 1),
                'median_days_to_revert': round(med_days, 1),
            },
        })
        
        # Save individual pair series
        pair_series_records = [
            {
                'd': r['date'].strftime('%Y-%m-%d'),
                'ea': r['expiry_a'].strftime('%Y-%m-%d'),
                'eb': r['expiry_b'].strftime('%Y-%m-%d'),
                's': round(float(r['spread']), 1),
                's10': round(float(r['spread_rs_10g']), 1),
                'mu': round(float(r['mu']), 1) if pd.notna(r['mu']) else None,
                'sd': round(float(r['sd']), 1) if pd.notna(r['sd']) else None,
                'z': round(float(r['z']), 2) if pd.notna(r['z']) else None,
                'roll': bool(r['roll']),
                'seg': r['segment'],
                'vol_a': int(r['vol_a']),
                'vol_b': int(r['vol_b']),
                'oi_a': int(r['oi_a']),
                'oi_b': int(r['oi_b']),
            }
            for _, r in p_calc.iterrows()
        ]
        save_json(os.path.join(output_dir, f'pairs/{pair_id}.json'), pair_series_records)
        
    save_json(os.path.join(output_dir, 'pairs.json'), scanner_pairs)
    
    # 7.7 signals_today.json & signals_history.json
    save_json(os.path.join(output_dir, 'signals_today.json'), alerts_today)
    save_json(os.path.join(output_dir, 'signals_history.json'), signals_history)
    
    # 7.8 backtest files: backtest/{PAIR_ID}_{SLIP}.json, cost_matrix.json, grid.json
    t_end = pd.Timestamp(TRAIN_END)
    
    # Cost matrix across pairs
    cost_matrix_rows = []
    
    # Pooled correlation & beta to gold across all 6 pairs on test segment at 5 bps base slippage
    pooled_test_5bps = all_trades_df[(all_trades_df['slip'] == BASE_SLIPPAGE) & (all_trades_df['seg'] == 'test')]
    if len(pooled_test_5bps) > 2 and 'gold_ret_bps' in pooled_test_5bps.columns:
        p_strat_ret = pooled_test_5bps['net_bps'].values
        p_gold_ret = pooled_test_5bps['gold_ret_bps'].values
        p_var_gold = np.var(p_gold_ret)
        if p_var_gold > 0:
            p_cov = np.cov(p_strat_ret, p_gold_ret)[0, 1]
            pooled_beta = float(p_cov / p_var_gold)
            pooled_corr = float(np.corrcoef(p_strat_ret, p_gold_ret)[0, 1])
        else:
            pooled_beta, pooled_corr = 0.0, 0.0
    else:
        pooled_beta, pooled_corr = 0.0, 0.0

    gold_share_pooled = (float(pooled_test_5bps['gold'].abs().sum() / pooled_test_5bps['gross'].abs().sum() * 100.0)
                         if len(pooled_test_5bps) and pooled_test_5bps['gross'].abs().sum() > 0 else 0.0)

    for pair_id, row_params in best_params.iterrows():
        W, ze, mh = int(row_params['W']), float(row_params['ze']), int(row_params['mh'])
        p_df = pairs_dict[pair_id]
        
        # For break-even calculation
        slip_trades_test = {}
        
        for slip in SLIPPAGE_SCENARIOS:
            t_df = run_pair_backtest(pair_id, p_df, P, dates, tdi, W, ze, mh, slip_bps=slip, rule=ALERT_RULE)
            if not t_df.empty:
                t_df['seg'] = segment_of(t_df['entry'].values)
                t_train = t_df[t_df['seg'] == 'train']
                t_test = t_df[t_df['seg'] == 'test']
            else:
                t_train = pd.DataFrame()
                t_test = pd.DataFrame()
                
            slip_trades_test[slip] = t_test
            
            # Cumulative equity curve
            equity_curve = []
            cum_net = 0.0
            cum_gross = 0.0
            cum_cost = 0.0
            cum_gold = 0.0
            cum_spread = 0.0
            
            for _, tr in t_df.iterrows():
                cum_net += tr['net']
                cum_gross += tr['gross']
                cum_cost += tr['cost']
                cum_gold += tr['gold']
                cum_spread += tr['spread_pnl']
                equity_curve.append({
                    'date': tr['entry'].strftime('%Y-%m-%d') if hasattr(tr['entry'], 'strftime') else str(tr['entry']),
                    'exit_date': tr['exit'].strftime('%Y-%m-%d') if hasattr(tr['exit'], 'strftime') else str(tr['exit']),
                    'seg': tr['seg'],
                    'net': round(float(cum_net), 1),
                    'gross': round(float(cum_gross), 1),
                    'cost': round(float(cum_cost), 1),
                    'gold': round(float(cum_gold), 1),
                    'spread': round(float(cum_spread), 1),
                    'trade_net_bps': round(float(tr['net_bps']), 1),
                })
                
            # Gold correlation & beta: per-trade strategy net_bps vs gold return over same holding period
            if len(t_test) > 2 and 'gold_ret_bps' in t_test.columns:
                pair_strat_ret = t_test['net_bps'].values
                pair_gold_ret = t_test['gold_ret_bps'].values
                pair_var_gold = np.var(pair_gold_ret)
                if pair_var_gold > 0:
                    pair_cov = np.cov(pair_strat_ret, pair_gold_ret)[0, 1]
                    pair_beta = float(pair_cov / pair_var_gold)
                    pair_corr = float(np.corrcoef(pair_strat_ret, pair_gold_ret)[0, 1])
                else:
                    pair_beta, pair_corr = 0.0, 0.0
            else:
                pair_beta, pair_corr = 0.0, 0.0
                
            trades_list = []
            for _, tr in t_df.iterrows():
                trades_list.append({
                    'pair': tr['pair'],
                    'sig': tr['sig'].strftime('%Y-%m-%d'),
                    'entry': tr['entry'].strftime('%Y-%m-%d'),
                    'exit': tr['exit'].strftime('%Y-%m-%d'),
                    'expA': str(tr['expA']),
                    'expB': str(tr['expB']),
                    'z': tr['z'],
                    'side': tr['side'],
                    'grams': tr['grams'],
                    'notional': tr['notional'],
                    'gross': round(float(tr['gross']), 1),
                    'gold': round(float(tr['gold']), 1),
                    'spread_pnl': round(float(tr['spread_pnl']), 1),
                    'cost': round(float(tr['cost']), 1),
                    'net': round(float(tr['net']), 1),
                    'gross_bps': round(float(tr['gross_bps']), 1),
                    'net_bps': round(float(tr['net_bps']), 1),
                    'reason': tr['reason'],
                    'days': int(tr['days']),
                    'seg': tr['seg'],
                    # Oct-2026 audit: costs by side, size per leg, participation and lifecycle evidence per trade
                    'cost_entry': round(float(tr['cost_entry']), 2),
                    'cost_exit': round(float(tr['cost_exit']), 2),
                    'lots_a': round(float(tr['lots_a']), 3),
                    'lots_b': round(float(tr['lots_b']), 3),
                    'part_entry': tr['part_entry'],
                    'part_exit': tr['part_exit'],
                    'forced_fill': bool(tr['forced_fill']),
                    'td_exit_a': int(tr['td_exit_a']),
                    'td_exit_b': int(tr['td_exit_b']),
                    'tender_td_a': tr['tender_td_a'],
                    'tender_td_b': tr['tender_td_b'],
                    'lifecycle': tr['lifecycle'],
                })
                
            backtest_payload = {
                'pair_id': pair_id,
                'slip_bps': slip,
                'params': {
                    'W': W,
                    'ze': ze,
                    'zx': 0.5,
                    'mh': mh,
                    'notional_per_leg': NOTIONAL_PER_LEG,
                    'hurdle_bps': round(hurdle_bps(), 1),
                    'stop_z': round(ze + STOP_Z_BUFFER, 2),
                    'max_fill_move_pct': round(MAX_FILL_MOVE * 100, 1),
                },
                'switch': switch[pair_id],
                'metrics_all': compute_attribution_metrics(t_df),
                'metrics_train': compute_attribution_metrics(t_train),
                'metrics_test': compute_attribution_metrics(t_test),
                'trades': trades_list,
                'equity_curve': equity_curve,
                'attribution': {
                    'gross_rs': round(float(t_test['gross'].sum()) if len(t_test) else 0.0, 1),
                    'costs_rs': round(float(t_test['cost'].sum()) if len(t_test) else 0.0, 1),
                    'net_rs': round(float(t_test['net'].sum()) if len(t_test) else 0.0, 1),
                    'spread_rs': round(float(t_test['spread_pnl'].sum()) if len(t_test) else 0.0, 1),
                    'gold_rs': round(float(t_test['gold'].sum()) if len(t_test) else 0.0, 1),
                    'direct_gold_pnl_pct': round(float(t_test['gold'].abs().sum() / t_test['gross'].abs().sum() * 100.0), 1) if len(t_test) and t_test['gross'].abs().sum() > 0 else 0.0,
                    'pair_correlation_to_gold': round(pair_corr, 2),
                    'pair_beta_to_gold': round(pair_beta, 2),
                    'pair_n_trades': len(t_test),
                    'pair_note': f"{len(t_test)} trades — unstable",
                    'pooled_correlation_to_gold': round(pooled_corr, 2),
                    'pooled_beta_to_gold': round(pooled_beta, 2),
                    'pooled_n_trades': len(pooled_test_5bps),
                    'summary_text': (f"Equal grams on both legs, so direct gold P&L is small "
                                     f"({gold_share_pooled:.1f}% of gross across all pairs in Test). "
                                     f"Correlation of trade returns with gold moves: {pooled_corr:+.2f} (pooled)."),
                },
            }
            save_json(os.path.join(output_dir, f'backtest/{pair_id}_{slip}.json'), backtest_payload)
            
        # Calculate break-even slippage on Test segment
        t0 = slip_trades_test.get(0, pd.DataFrame())
        t10 = slip_trades_test.get(10, pd.DataFrame())
        a0 = float(t0['net'].sum()) if len(t0) else 0.0
        a10 = float(t10['net'].sum()) if len(t10) else 0.0
        be = round(10.0 * a0 / (a0 - a10), 1) if (a0 > 0 and a0 != a10) else 0.0
        
        # Add to cost matrix
        for slip in SLIPPAGE_SCENARIOS:
            ts = slip_trades_test.get(slip, pd.DataFrame())
            cost_matrix_rows.append({
                'pair_id': pair_id,
                'slip_bps': slip,
                'trades': len(ts),
                'gross_bps': round(float(ts['gross_bps'].mean()) if len(ts) else 0.0, 1),
                'net_bps': round(float(ts['net_bps'].mean()) if len(ts) else 0.0, 1),
                'net_rs': round(float(ts['net'].sum()) if len(ts) else 0.0, 1),
                'hit_rate': round(float((ts['net'] > 0).mean()) if len(ts) else 0.0, 3),
                'breakeven_slip_bps': be,
            })
            
    save_json(os.path.join(output_dir, 'backtest/cost_matrix.json'), cost_matrix_rows)
    
    # Save parameter grid
    grid_records = grid_df.to_dict(orient='records')
    save_json(os.path.join(output_dir, 'backtest/grid.json'), grid_records)
    
    # 7.8b regimes.json: dynamically compute regimes across time splits
    regime_records = []
    for pair_id, p_df in pairs_dict.items():
        pair_spec = PAIRS[pair_id]
        
        # Oct-23 -> Dec-24
        sub_pre = p_df[(p_df['date'] >= '2023-10-10') & (p_df['date'] <= '2024-12-31')]
        if len(sub_pre) > 0:
            pre_mean = round(float(sub_pre['spread'].mean()), 1)
            pre_text = f"{pre_mean:+.1f} bps"
        else:
            pre_mean = None
            pre_text = "No contract (listed 31-Mar-2025)"
            
        # Apr-25 -> Sep-26
        sub_post = p_df[(p_df['date'] >= '2025-04-01') & (p_df['date'] <= '2026-09-30')]
        if len(sub_post) > 0:
            post_mean = round(float(sub_post['spread'].mean()), 1)
            post_text = f"{post_mean:+.1f} bps"
        else:
            post_mean = None
            post_text = "—"
            
        # Q1-2026 (Jan-Mar 2026 crash quarter)
        sub_q1 = p_df[(p_df['date'] >= '2026-01-01') & (p_df['date'] <= '2026-03-31')]
        if len(sub_q1) > 0:
            q1_mean = round(float(sub_q1['spread'].mean()), 1)
            q1_min = round(float(sub_q1['spread'].min()), 1)
            q1_max = round(float(sub_q1['spread'].max()), 1)
            q1_text = f"Mean {q1_mean:+.1f} bps [min {q1_min:+.1f}, max {q1_max:+.1f}]"
        else:
            q1_mean, q1_min, q1_max = None, None, None
            q1_text = "—"
            
        if pair_id in ('GUINEA_PETAL', 'M_PETAL'):
            comment = ("Level shift around Dec-24 → Mar-25: GOLDPETAL moved from cheap to slightly rich. "
                       "Cause not yet confirmed; a move this size usually means a change in contract terms, "
                       "so check MCX circulars for that period.")
        elif 'TEN' in pair_id:
            comment = "Listed Mar-2025; no pre-break history"
        elif pair_id == 'M_GUINEA':
            comment = (f"Fairly stable: GOLDM averaged {float(p_df['spread'].mean()):+.1f} bps vs GOLDGUINEA "
                       f"(carry-adjusted) over the whole period.")
        else:
            comment = "Cross-contract basis dynamics."
            
        regime_records.append({
            'pair_id': pair_id,
            'pair': f"{pair_spec.symbol_a} − {pair_spec.symbol_b}",
            'pre_break_mean': pre_mean,
            'pre_break_text': pre_text,
            'post_break_mean': post_mean,
            'post_break_text': post_text,
            'q1_mean': q1_mean,
            'q1_min': q1_min,
            'q1_max': q1_max,
            'q1_text': q1_text,
            'comment': comment,
        })
    save_json(os.path.join(output_dir, 'regimes.json'), regime_records)
    
    # 7.9 rule_comparison.json + methodology.json (numbers computed, not typed in)
    new_sum = summarize_rule(all_trades_df, switch)
    old_sum = summarize_rule(legacy_trades_df)
    rule_comparison = {
        'crash': {'start': CRASH_START, 'end': CRASH_END, 'label': CRASH_LABEL},
        'hurdle_bps': round(hurdle_bps(), 1),
        'stop_buffer_z': STOP_Z_BUFFER,
        'max_fill_move_pct': round(MAX_FILL_MOVE * 100, 1),
        'min_train_trades': MIN_TRAIN_TRADES,
        'switch': switch,
        'current_rule': {'name': 'All five checks (what the site shows)', 'params': best_params.reset_index().to_dict(orient='records'), 'by_slip': new_sum},
        'original_rule': {'name': 'Original study: 4 checks, no cost line', 'params': legacy_params.reset_index().to_dict(orient='records'), 'by_slip': old_sum},
    }
    save_json(os.path.join(output_dir, 'backtest/rule_comparison.json'), rule_comparison)

    # The verdict needs the cleanest out-of-sample test (2011-2023) and the evidence checks,
    # so both run here, before methodology.json and site-data.json are written.
    print("--- 7b. Long-history check: frozen rule on 2011-2023 (MCX history book) ---")
    from pipeline.history import build as build_history
    hist = build_history(output_dir)
    print("--- 7b2. Explorer grid: the real engine over a grid of settings ('Try your own rule') ---")
    from pipeline.explore import build as build_explore
    build_explore(output_dir)
    print("--- 7c. Evidence checks: test-year status, slippage, multiple testing, switch ---")
    from pipeline.evidence import build as build_evidence
    ev = build_evidence(output_dir)
    pb = ev['petal_break']
    for r in regime_records:      # the break is located from the data (evidence.py), not typed in
        if r['pair_id'] in ('GUINEA_PETAL', 'M_PETAL'):
            r['comment'] = (f"Level shift: GOLDPETAL repriced from cheap to slightly rich, sharpest "
                            f"{pd.Timestamp(pb['start']).strftime('%d %b')}–{pd.Timestamp(pb['end']).strftime('%d %b %Y')}. "
                            f"Cause not confirmed; no MCX notice found.")
    save_json(os.path.join(output_dir, 'regimes.json'), regime_records)

    b = new_sum[str(BASE_SLIPPAGE)]
    o = old_sum[str(BASE_SLIPPAGE)]
    def rs(v: float) -> str:
        """Indian digit grouping: ₹1,13,598."""
        n = str(int(abs(v) + 0.5))  # round half up, same as the website's Math.round
        if len(n) > 3:
            head, tail = n[:-3], n[-3:]
            parts = []
            while len(head) > 2:
                parts.insert(0, head[-2:])
                head = head[:-2]
            if head:
                parts.insert(0, head)
            n = ','.join(parts) + ',' + tail
        return ('−' if v < 0 else '') + '₹' + n
    on_pairs = [k for k, v in switch.items() if v['on']]
    per_pair_n = all_trades_df[(all_trades_df['slip'] == BASE_SLIPPAGE) & (all_trades_df['seg'] == 'test')].groupby('pair').size()
    t_txt = f"t = {b['test_t']:.2f}" if b['test_t'] is not None else 't-stat not available'
    sig_txt = 'below the usual bar of 2' if (b['test_t'] is None or abs(b['test_t']) < 2) else 'above the usual bar of 2'
    if b['test_net_rs'] > 0 and b['crash_net_rs'] >= b['test_net_rs']:
        crash_txt = (f"trades that closed during the {CRASH_LABEL} made {rs(b['crash_net_rs'])}; "
                     f"outside it the rule {'lost ' + rs(-b['ex_crash_net_rs']) if b['ex_crash_net_rs'] < 0 else 'made ' + rs(b['ex_crash_net_rs'])}")
    else:
        crash_txt = f"trades that closed during the {CRASH_LABEL} made {rs(b['crash_net_rs'])}"
    mt = ev['multiple_testing']
    p_txt = (f", p = {mt['p_two_sided']:.2f}, or {mt['p_bonferroni']:.2f} allowing for the {mt['rule_versions_scored_on_test']} "
             f"rule versions scored on that year" if mt['p_two_sided'] is not None else '')
    hr = hist.get('result') or {}
    hs, h0 = hr.get('by_slip', {}).get(str(BASE_SLIPPAGE)), hr.get('by_slip', {}).get('0')
    def made(v: float) -> str:
        return ('made ' if v > 0 else 'lost ') + rs(abs(v))
    hy = f"{hist['window']['from'][:4]}–{hist['window']['to'][:4]}"
    if hs:
        hist_txt = (f"The historical holdout is {hy}: the settings were chosen on training data only and that period was never "
                    f"used to choose them. There the rule {made(hs['net_rs'])} over {hs['n']} trades at {BASE_SLIPPAGE} bps "
                    f"slippage (t = {str(hs['t']).replace('-', '−')})"
                    + (f", and {made(h0['net_rs'])} even with zero slippage. " if h0 and h0['net_rs'] < 0 else ". "))
    else:
        hist_txt = ''
    if b['test_net_rs'] > 0:
        test_txt = (f"Its profit rests on one episode ({crash_txt}), and it is not significant ({t_txt}{p_txt}). ")
    else:
        test_txt = f"It is not significant either way ({t_txt}{p_txt}). "
    honest = (
        f"Cross-contract gold gaps are real and measurable, but no persistent edge is proven after costs. {hist_txt}"
        f"The {TEST_START[:4]}–{TEST_END[2:4]} test year {made(b['test_net_rs'])} over {b['test_n']} trades, but it is not a clean "
        f"test: the five-check rule was written after that year's first results were seen. {test_txt}In training the same rule "
        f"{made(b['train_net_rs'])} over {b['train_n']} trades, and training would have switched on only {len(on_pairs)} of 6 pairs. "
        f"In Oct 2026 the contract-lifecycle and liquidity rules were corrected (tender windows, size-aware volume checks); "
        f"that was done after the earlier version's results on every period were known, to fix the rules, not to change the results."
    )
    methodology_data = {
        'stages': [
            {'step': 1, 'name': 'Load & Validate', 'desc': f'Parse {hist["window"]["rows"] + len(df):,} daily prices: {hist["window"]["rows"]:,} from the MCX history book (2011–2023) and {len(df):,} from our own MCX download (Oct 2023 on). Strip symbols, check primary keys, compare against the raw MCX file and the book, flag no-trade days.'},
            {'step': 2, 'name': 'Normalize', 'desc': 'Divide the Bhavcopy close by the grams it is quoted for and by its purity (from a date-effective specification table) to get a price per gram of pure gold.'},
            {'step': 3, 'name': 'Implied Carry', 'desc': 'Estimate the cost of carry from GOLDPETAL calendar spreads, skipping contracts inside their tender window; forward-fill only. Estimates outside 0–15% a year are flagged as unstable.'},
            {'step': 4, 'name': 'Pair Construction', 'desc': 'Pick contracts using the previous day\'s open interest, so nothing from the future is used.'},
            {'step': 5, 'name': 'Point-in-Time z-scores', 'desc': 'One rolling mean and spread for alerts, charts and backtest, from earlier days only.'},
            {'step': 6, 'name': 'One rule: five checks', 'desc': f'The same five checks drive today\'s alerts and every backtest trade: enough history, an unusual gap that is not already past the stop-loss, a gap bigger than {HURDLE_MULTIPLE:.0f}× the round-trip cost, liquidity sized to the trade (each leg at most {MAX_PARTICIPATION*100:.0f}% of that day\'s volume), and contract life (each leg clear of its own tender window).'},
            {'step': 7, 'name': 'Train/test split and historical holdout', 'desc': f'Settings chosen once on Train ({TRAIN_START[:7]} to {TRAIN_END[:7]}) by highest net after costs, then frozen for the test year ({TEST_START[:7]} to {TEST_END[:7]}) and for the historical holdout ({hist["window"]["from"][:4]}–{hist["window"]["to"][:4]}). There is no separate validation period and no rolling re-fit, so this is a single split, not a rolling walk-forward. A pair is traded in Test only if training gave at least {MIN_TRAIN_TRADES} trades and a profit.'},
            {'step': 8, 'name': 'Costs & Attribution', 'desc': f'Each closed trade is split into spread and gold parts after statutory costs and slippage; every trade is also marked to market daily for portfolio figures. No fills on days a leg moved {MAX_FILL_MOVE*100:.0f}% or more, except a flagged forced exit before a tender window.'},
        ],
        'split_dates': {
            'train_start': TRAIN_START,
            'train_end': TRAIN_END,
            'test_start': TEST_START,
            'test_end': TEST_END,
        },
        'point_in_time_rules': [
            'Rolling z uses only t-1 and earlier observations (shifted window)',
            'Contract pairing selects max min(OI) as of t-1',
            'Parameters tuned strictly on in-sample Train data and frozen; the on/off switch also uses Train only',
            'Signals generated at close t execute at close t+1; exits never fill at the signal\'s own close',
            f'No fills on days either leg moved {MAX_FILL_MOVE*100:.0f}% or more (prices may be stuck at the daily limit)',
            'Carry rate c_t is forward-filled only; never backward-filled',
            f'A position opens only if both legs are at least {MIN_ENTRY_TD} trading days from expiry on the signal day, and is closed by the last trading day before either leg\'s {CONSERVATIVE_TENDER_TD}-day tender window (the calendar is known in advance, so this uses no future data)',
        ],
        'limitations': [
            'Prices are the Bhavcopy close: a daily reference, not an executable fill. We have not verified that it equals MCX\'s official settlement price in every period.',
            'Bhavcopy volume indicates activity but does not measure order-book depth or guarantee execution; the size check '
            f'(each leg at most {MAX_PARTICIPATION*100:.0f}% of the day\'s volume) is a screen, not a fill model. Open interest is only a screen. Slippage is assumed at '
            f'{BASE_SLIPPAGE} bps per order: daily data cannot measure it (see the slippage check), only real broker fills can.',
            f'Tender periods: no MCX circular could be read directly (MCX refuses automated requests). Broker notices report 5 trading days '
            f'(2025) and 3 days (from Feb 2026) for the smaller gold contracts; we apply the longer {CONSERVATIVE_TENDER_TD}-day window to every contract '
            'and year. Contract specifications before Oct 2023 are assumed equal to today\'s (no source found).',
            f"The {TEST_START[:4]}–{TEST_END[2:4]} test year is not a clean out-of-sample test: the five-check rule was written "
            f"on {ev['test_year']['rule_frozen']}, after the original study's test-year results were known. The "
            f"{hist['window']['from'][:4]}–{hist['window']['to'][:4]} historical holdout was never used to choose settings, but the "
            "Oct-2026 lifecycle and liquidity correction was made after the earlier version's results there were known.",
            'GOLDTEN contracts listed only on 31-Mar-2025, offering limited historical depth.',
            f'Test period contains only {int(per_pair_n.min()) if len(per_pair_n) else 0} to {int(per_pair_n.max()) if len(per_pair_n) else 0} trades per pair ({b["test_n"]} in total); small samples preclude high certainty.',
            'GOLDPETAL repriced against the other contracts: ' + pb['summary'],
            f'Trades closed during the {CRASH_LABEL} made {rs(b["crash_net_rs"])} of the test-year result ({rs(b["test_net_rs"])} in total). '
            'The crash window was named after the results were seen, so this split is a check, not a test.',
            'The training switch rests on thin evidence: ' + ev['switch']['note'],
            'When the pair series switches to new contracts, open trades are closed; this adds cost.',
            'Exchange transaction charges and statutory rates should be regularly verified against MCX circulars.',
        ],
        'honest_conclusion': honest,
        'original_rule_note': (
            f"The original study used only four of the five checks (no cost line). Under it: {o['test_n']} test-year trades, "
            f"{rs(o['test_net_rs'])} at {BASE_SLIPPAGE} bps. It is kept on the site for comparison only."
        ),
    }
    
    # 7.10 retrieval_log.json
    retrieval_csv_path = 'data/raw/retrieval_log.csv'
    retrieval_records = []
    if os.path.exists(retrieval_csv_path):
        retrieval_df = pd.read_csv(retrieval_csv_path)
        for _, r_row in retrieval_df.iterrows():
            retrieval_records.append({
                'symbol': str(r_row['symbol']),
                'expiry': str(r_row['expiry']),
                'endpoint': str(r_row.get('endpoint', '')),
                'params': str(r_row.get('params', '')),
                'requested_from': str(r_row['requested_from']),
                'requested_to': str(r_row['requested_to']),
                'retrieved_at_ist': str(r_row.get('retrieved_at_ist', '')),
                'rows': int(r_row['rows']),
                'first_date': str(r_row['first_date']),
                'last_date': str(r_row['last_date']),
                'rows_outside_range_or_after_expiry': int(r_row.get('rows_outside_range_or_after_expiry', 0)),
            })
    save_json(os.path.join(output_dir, 'retrieval_log.json'), retrieval_records)
    methodology_data['retrieval_log'] = retrieval_records
    save_json(os.path.join(output_dir, 'methodology.json'), methodology_data)
    
    print("--- 8. Writing site-data.json for the website ---")
    from pipeline.build_web_data import build_web_data
    build_web_data(output_dir)

    print("--- 9. Extra checks: alert follow-through and 95% ranges ---")
    from pipeline.robustness import build as build_robustness
    build_robustness(output_dir)

    print("--- 10. Portfolio: every trade marked to market daily, all pairs together ---")
    from pipeline.portfolio import build as build_portfolio
    build_portfolio(output_dir)

    print("--- 11. Provenance: raw-file hashes, ingestion counts, contract-rule tables ---")
    from pipeline.provenance import build as build_provenance
    build_provenance(output_dir, carry_chosen=chosen_pet_ref)

    print("--- Build complete! All JSON files written successfully. ---")

if __name__ == '__main__':
    build_all_site_data()
