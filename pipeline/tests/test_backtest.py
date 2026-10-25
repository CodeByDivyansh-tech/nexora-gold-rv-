"""Tests for pipeline/backtest.py reproducing reference_summary.csv (Section 12)."""
import pytest
import os
import numpy as np
import pandas as pd
from pipeline.load import load_clean_bhavcopy
from pipeline.config import TEST_END   # research snapshot: a data refresh must not change these checks
from pipeline.carry import compute_reference_carry
from pipeline.pairs import build_all_pairs
from pipeline.backtest import prepare_contract_lookup, run_grid_search, run_all_scenarios
from pipeline.config import LEGACY_RULE

def test_backtest_reproduces_reference_summary():
    """The ORIGINAL study (LEGACY_RULE: 4 checks, no cost line) must still reproduce
    reference/reference_summary.csv: trade counts exact; mean bps within ±1."""
    ref_summary_path = 'reference/reference_summary.csv'
    assert os.path.exists(ref_summary_path), f"Reference summary not found at {ref_summary_path}"
    ref_df = pd.read_csv(ref_summary_path).set_index(['pair', 'slip', 'seg'])
    
    # Load and run pipeline backtest on the rows the original study used (no history-book supplement)
    df, dates, tdi = load_clean_bhavcopy('data/raw/gold_bhavcopy_clean.csv', end=TEST_END, original_only=True)
    carry_series, _ = compute_reference_carry(df, dates, exclude_tender=False)   # the original study's carry choice
    pairs = build_all_pairs(df, carry_series)
    P = prepare_contract_lookup(df)
    
    grid_df, best_params = run_grid_search(pairs, P, dates, tdi, rule=LEGACY_RULE)
    all_trades, summary_df = run_all_scenarios(pairs, best_params, P, dates, tdi, rule=LEGACY_RULE)
    
    # Verify index match
    assert len(summary_df) == len(ref_df), f"Summary rows count mismatch: {len(summary_df)} vs {len(ref_df)}"
    
    for idx, ref_row in ref_df.iterrows():
        assert idx in summary_df.index, f"Missing row {idx} in pipeline summary!"
        calc_row = summary_df.loc[idx]
        
        # Trade count must be EXACT
        assert calc_row['n'] == ref_row['n'], f"{idx} trade count mismatch: expected {ref_row['n']}, got {calc_row['n']}"
        
        # Gross bps and Net bps within ±1.0
        assert abs(calc_row['gross_bps'] - ref_row['gross_bps']) <= 1.0, f"{idx} gross_bps mismatch: expected {ref_row['gross_bps']}, got {calc_row['gross_bps']}"
        assert abs(calc_row['net_bps'] - ref_row['net_bps']) <= 1.0, f"{idx} net_bps mismatch: expected {ref_row['net_bps']}, got {calc_row['net_bps']}"

def test_trade_attribution_and_timing():
    """Verify fill dates strictly after signal dates, and attribution identity holds."""
    df, dates, tdi = load_clean_bhavcopy('data/raw/gold_bhavcopy_clean.csv', end=TEST_END)
    carry_series, _ = compute_reference_carry(df, dates)
    pairs = build_all_pairs(df, carry_series)
    P = prepare_contract_lookup(df)
    
    grid_df, best_params = run_grid_search(pairs, P, dates, tdi)
    all_trades, summary_df = run_all_scenarios(pairs, best_params, P, dates, tdi)
    
    assert not all_trades.empty
    
    # 1. Every fill date strictly after its signal date
    assert (all_trades['entry'] > all_trades['sig']).all(), "Fill date is not strictly after signal date!"
    
    # 2. Attribution identity: spread_pnl + gold - cost == net to the rupee
    recon_net = all_trades['spread_pnl'] + all_trades['gold'] - all_trades['cost']
    diff = np.abs(all_trades['net'] - recon_net)
    assert np.all(diff < 1e-4), f"Attribution identity failed: max diff = {diff.max()}"
