"""Import Bhavcopy CSV files downloaded by hand from the MCX website, then rebuild the clean data.

MCX blocks scripted downloads (see pipeline/download.py), so new data arrives as the CSV files the
"Bhavcopy -> Commodity-wise" page exports (BhavCopyCommodiyWise_*.csv, one contract per file).

What it does
  1. Reads every file given, skips exact duplicate files, and checks each one: one gold symbol, known columns,
     dates parse, high/low consistent with open/close on traded days.
  2. Converts the rows to the endpoint format of data/raw/mcx_bhavcopy_raw_api.csv (the source of truth)
     and merges them with merge_raw(): same row twice is kept once, the same row with different numbers stops
     the import, so stored data is never silently changed.
  3. Keeps a copy of each original file in data/raw/mcx_csv/ (renamed by contract and date range) and adds one
     line per file to data/raw/retrieval_log.csv.
  4. Rebuilds the clean CSV and contract calendar (download.rebuild()).

Usage (from the repo root)
  python -m pipeline.import_csv path/to/BhavCopyCommodiyWise_*.csv
  python -m pipeline.build_site_data            then rebuild the website data as usual
"""
import argparse
import datetime as dt
import hashlib
import os
import shutil
import sys
from typing import List, Tuple

import pandas as pd

from pipeline.config import CONTRACT_SPECS
from pipeline.download import RAW_COLS, RAW_PATH, LOG_PATH, merge_raw, rebuild, load_raw

ARCHIVE = 'data/raw/mcx_csv'
CSV_COLS = ['Date', 'Instrument Name', 'Symbol', 'Expiry Date', 'Option Type', 'Strike Price', 'Open', 'High', 'Low',
            'Close', 'Previous Close', 'Volume(Lots)', "Volume(In 000's)", 'Value(Lacs)', 'Open Interest(Lots)']


def read_site_csv(path: str) -> pd.DataFrame:
    """One MCX website CSV -> rows in the endpoint format (RAW_COLS). Raises ValueError if the file is not as expected."""
    d = pd.read_csv(path, dtype=str, keep_default_na=False)
    d.columns = [c.strip() for c in d.columns]
    missing = [c for c in CSV_COLS if c not in d.columns]
    if missing:
        raise ValueError(f'{os.path.basename(path)}: not an MCX Bhavcopy CSV (missing {missing})')
    fut = d['Instrument Name'].str.strip() == 'FUTCOM'
    rejected = int((~fut).sum())                     # e.g. option rows in the same file: counted, not silently lost
    d = d[fut].copy()
    d['Symbol'] = d['Symbol'].str.strip()
    syms = set(d['Symbol'])
    if len(syms) != 1 or not syms <= set(CONTRACT_SPECS):
        raise ValueError(f'{os.path.basename(path)}: expected one gold contract, found {sorted(syms)}')
    num = lambda c: pd.to_numeric(d[c].str.strip().replace('', '0'), errors='raise')
    dates = pd.to_datetime(d['Date'].str.strip(), format='%d %b %Y')
    expiry = pd.to_datetime(d['Expiry Date'].str.strip(), format='%d%b%Y')
    o, h, l, c = num('Open'), num('High'), num('Low'), num('Close')
    traded = num('Volume(Lots)') > 0
    bad = traded & ((h < o.combine(c, max)) | (l > o.combine(c, min)) | (l > h))
    if bad.any():
        raise ValueError(f'{os.path.basename(path)}: {int(bad.sum())} rows where high/low do not contain open/close')
    if (dates > expiry).any():
        raise ValueError(f'{os.path.basename(path)}: rows dated after the contract expired')
    fmt = lambda x: ('%.2f' % x).rstrip('0').rstrip('.')
    out = pd.DataFrame({
        'Date': dates.dt.strftime('%m/%d/%Y'), 'Symbol': d['Symbol'], 'ExpiryDate': expiry.dt.strftime('%d%b%Y').str.upper(),
        'Open': o.map(fmt), 'High': h.map(fmt), 'Low': l.map(fmt), 'Close': c.map(fmt), 'PreviousClose': num('Previous Close').map(fmt),
        'Volume': num('Volume(Lots)').astype(int).astype(str), 'VolumeInThousands': d["Volume(In 000's)"].str.strip(),
        'Value': num('Value(Lacs)').map(fmt), 'OpenInterest': num('Open Interest(Lots)').astype(int).astype(str),
    })[RAW_COLS].reset_index(drop=True)
    out.attrs['rejected'] = rejected
    return out


def import_files(paths: List[str], retrieved: str = None, archive: bool = True) -> Tuple[int, int]:
    """Merge the files into the raw store. Returns (unique files, new rows)."""
    retrieved = retrieved or dt.datetime.now().strftime('%Y-%m-%d %H:%M')
    seen, frames, logs, copies = set(), [], [], []
    for p in paths:
        h = hashlib.md5(open(p, 'rb').read()).hexdigest()
        if h in seen:
            print(f'skip (same file as another): {os.path.basename(p)}')
            continue
        seen.add(h)
        r = read_site_csv(p)
        frames.append(r)
        sym, exp = r['Symbol'].iloc[0], r['ExpiryDate'].iloc[0]
        d = pd.to_datetime(r['Date'], format='%m/%d/%Y')
        name = f'{sym}_{exp}_{d.min():%Y%m%d}-{d.max():%Y%m%d}.csv'
        copies.append((p, name))
        logs.append({'symbol': sym, 'expiry': pd.to_datetime(exp, format='%d%b%Y').strftime('%Y-%m-%d'),
                     'endpoint': 'MCX website Bhavcopy page, CSV downloaded by the team (' + ARCHIVE + '/' + name + ')',
                     'params': f'InstrumentName=FUTCOM&Symbol={sym}&Expiry={exp}',
                     'requested_from': d.min().strftime('%d/%m/%Y'), 'requested_to': d.max().strftime('%d/%m/%Y'),
                     'retrieved_at_ist': retrieved, 'rows': len(r), 'first_date': d.min().strftime('%Y-%m-%d'),
                     # rows dated after expiry make the whole import fail (read_site_csv), so this is truly 0 here
                     'last_date': d.max().strftime('%Y-%m-%d'), 'rows_outside_range_or_after_expiry': 0,
                     'rows_rejected_not_futures': int(r.attrs.get('rejected', 0))})
    if not frames:
        return 0, 0
    new = pd.concat(frames, ignore_index=True)
    if new.duplicated(['Symbol', 'ExpiryDate', 'Date']).any():
        raise ValueError('two different files contain the same contract and day with different numbers')
    raw = pd.read_csv(RAW_PATH, dtype=str)
    # the supplement (history-book rows) must not be duplicated into the MCX store either
    stored = load_raw().astype(str)
    merge_raw(stored, new)                                    # raises on any conflict with stored rows
    key = lambda x: x['Symbol'].str.strip() + '|' + x['ExpiryDate'].str.strip() + '|' + x['Date']
    add = new[~key(new).isin(set(key(stored)))]
    out = pd.concat([raw, add], ignore_index=True)
    out.to_csv(RAW_PATH, index=False)
    if archive:                                               # originals are kept only once the import has succeeded
        os.makedirs(ARCHIVE, exist_ok=True)
        for src, name in copies:
            shutil.copyfile(src, os.path.join(ARCHIVE, name))
    log = pd.read_csv(LOG_PATH, dtype=str)
    pd.concat([log, pd.DataFrame(logs).astype(str)], ignore_index=True).to_csv(LOG_PATH, index=False)
    return len(frames), len(add)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('files', nargs='+')
    args = ap.parse_args()
    try:
        n, added = import_files(args.files)
        rebuild()
        print(f'{n} files, {added} new rows. Now run: python -m pipeline.build_site_data')
    except Exception as e:
        print(f'Import failed, nothing changed: {e}', file=sys.stderr)
        sys.exit(1)
