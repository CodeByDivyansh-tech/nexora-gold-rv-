"""Data loader and validator for MCX Bhavcopy EOD data."""
import os
import pandas as pd
import numpy as np
from typing import Tuple, Dict
from pipeline.config import THIN_VOLUME_THRESHOLD, THIN_OI_THRESHOLD
from pipeline.contract_rules import apply_specs

def load_clean_bhavcopy(csv_path: str = 'data/raw/gold_bhavcopy_clean.csv', end: str = None,
                        original_only: bool = False) -> Tuple[pd.DataFrame, np.ndarray, Dict[pd.Timestamp, int]]:
    """
    Loads and preprocesses gold_bhavcopy_clean.csv.
    end: if given (YYYY-MM-DD), rows after this date are dropped first. Tests that check the published
         research figures pass end=TEST_END, so a data refresh cannot change what they check.
    original_only: drop the rows that came from the MCX history book supplement (data/raw/mcx_bhavcopy_supplement.csv),
         giving the dataset the original study (reference/reference_summary.csv) was computed on.
    Returns:
        df: preprocessed dataframe sorted by (symbol, expiry, date)
        dates: array of sorted unique trading dates
        tdi: mapping of trading date to trading date index
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Clean bhavcopy dataset not found at {csv_path}")

    df = pd.read_csv(csv_path, parse_dates=['date', 'expiry_date'])
    if end is not None:
        df = df[df['date'] <= pd.Timestamp(end)].copy()
    sup_path = os.path.join(os.path.dirname(csv_path), 'mcx_bhavcopy_supplement.csv')
    if original_only and os.path.exists(sup_path):
        sup = pd.read_csv(sup_path)
        keys = set(zip(sup['Symbol'].str.strip(), pd.to_datetime(sup['ExpiryDate'], format='%d%b%Y'),
                       pd.to_datetime(sup['Date'], format='%m/%d/%Y')))
        df = df[[k not in keys for k in zip(df['symbol'].str.strip(), df['expiry_date'], df['date'])]].copy()
    
    # Rename columns to standard names if needed
    if 'expiry_date' in df.columns and 'expiry' not in df.columns:
        df['expiry'] = df['expiry_date']
    if 'volume_lots' in df.columns and 'vol' not in df.columns:
        df['vol'] = df['volume_lots']
    if 'open_interest_lots' in df.columns and 'oi' not in df.columns:
        df['oi'] = df['open_interest_lots']

    # Strip symbols
    df['symbol'] = df['symbol'].astype(str).str.strip()

    # Verify primary key: (symbol, expiry, date)
    pk_cols = ['symbol', 'expiry', 'date']
    dups = df.duplicated(subset=pk_cols, keep=False)
    if dups.any():
        dup_rows = df[dups]
        raise ValueError(f"Found {len(dup_rows)} duplicate primary key rows in dataset: {pk_cols}")

    # Contract specs in force on each row's date (contract_rules.SPEC_TABLE), with spec_status
    # ('secondary' / 'assumed' / 'unavailable'). No row is dropped for an uncertain specification.
    df = apply_specs(df)

    # Normalized prices: rupees per gram of pure gold. The quoted price is for quote_grams of gold at the stated
    # purity, so dividing by both gives the pure-gold price; purity is applied exactly once.
    df['px_per_g_pure'] = df['close'] / df['quote_grams'] / df['purity']
    df['px_per_10g_pure'] = df['px_per_g_pure'] * 10.0
    df['px'] = df['px_per_g_pure'] # alias matching reference

    # Flags
    # no_trade: volume = 0 or open blank/0
    df['no_trade'] = (df['vol'] == 0) | df['open'].isna() | (df['open'] == 0)
    df['no_trade_day'] = df['no_trade']
    
    # thin: volume < 25 or OI < 50
    df['thin'] = (df['vol'] < THIN_VOLUME_THRESHOLD) | (df['oi'] < THIN_OI_THRESHOLD)
    df['is_thin'] = df['thin']

    # Sort strictly by symbol, expiry, date
    df = df.sort_values(['symbol', 'expiry', 'date']).reset_index(drop=True)

    # Trading date indices
    dates = np.array(sorted(df['date'].unique()))
    tdi = {d: i for i, d in enumerate(dates)}
    df['ti'] = df['date'].map(tdi)

    # Trading days to expiry (count of trading dates in data; beyond last date, count weekdays)
    last_date = dates[-1]
    last_d64 = np.datetime64(pd.Timestamp(last_date).strftime('%Y-%m-%d'), 'D')

    def calc_td_to_exp(row):
        exp_d64 = np.datetime64(pd.Timestamp(row['expiry']).strftime('%Y-%m-%d'), 'D')
        if exp_d64 <= last_d64:
            # np.searchsorted returns index where exp_d64 can be inserted to maintain order
            pos = np.searchsorted(dates, np.datetime64(row['expiry']), side='right')
            return pos - row['ti'] - 1
        else:
            busdays = int(np.busday_count(last_d64 + np.timedelta64(1, 'D'), exp_d64 + np.timedelta64(1, 'D')))
            return (len(dates) - 1 - row['ti']) + busdays

    df['td_to_exp'] = df.apply(calc_td_to_exp, axis=1)

    # Previous OI on contract level (t-1)
    df['oi_prev'] = df.groupby(['symbol', 'expiry'])['oi'].shift(1)

    return df, dates, tdi
