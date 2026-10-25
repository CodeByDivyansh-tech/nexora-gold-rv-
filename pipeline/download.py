"""Refresh the MCX data: download new Bhavcopy rows, then rebuild the clean CSV and contract calendar.

How the data is laid out
  data/raw/mcx_bhavcopy_raw_api.csv   rows exactly as the MCX endpoint returns them (the source of truth)
  data/raw/mcx_bhavcopy_supplement.csv official MCX rows our first download missed, downloaded from MCX on 21 Oct 2026
                                      (same columns plus Source): the Oct/Nov/Dec-2023 contracts and 1 Oct 2026
  data/raw/gold_bhavcopy_clean.csv    derived from the raw file by raw_to_clean() below
  data/raw/contract_calendar.csv      derived from the clean file by contract_calendar() below
  data/raw/retrieval_log.csv          one line per request

Usage (from the repo root)
  python -m pipeline.download                 fetch new rows for live and newly listed contracts, then rebuild
  python -m pipeline.download --rebuild-only  no network: rebuild the clean CSV and calendar from the raw file
  python -m pipeline.build_site_data          then rebuild the website data as usual

The endpoint (SPEC.md section 2.4) worked from a normal browser session; MCX may block plain scripts or
cloud servers. If the download fails, nothing is written and the command exits with an error, so the
committed data is never half-updated. The conversion code is checked offline by
pipeline/tests/test_download.py, which rebuilds the committed clean CSV and calendar from the raw file.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

import pandas as pd

from pipeline.config import CONTRACT_SPECS, THIN_OI_THRESHOLD, THIN_VOLUME_THRESHOLD

RAW_PATH = 'data/raw/mcx_bhavcopy_raw_api.csv'
SUPPLEMENT_PATH = 'data/raw/mcx_bhavcopy_supplement.csv'   # MCX rows our first download missed (second download), same format + Source
CLEAN_PATH = 'data/raw/gold_bhavcopy_clean.csv'
CAL_PATH = 'data/raw/contract_calendar.csv'
LOG_PATH = 'data/raw/retrieval_log.csv'
PAGE_URL = 'https://www.mcxindia.com/market-data/bhavcopy'
API_URL = 'https://www.mcxindia.com/market-data/bhavcopy/GetCommoditywiseBhavCopy'
RAW_COLS = ['Date', 'Symbol', 'ExpiryDate', 'Open', 'High', 'Low', 'Close', 'PreviousClose', 'Volume',
            'VolumeInThousands', 'Value', 'OpenInterest']
PK = ['symbol', 'expiry_date', 'date']
LOOKBACK_DAYS = 400          # a new contract is requested from expiry - 400 days (how the dataset was built)
PAUSE_S = 0.4                # between requests
HEADERS = {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest',
           'User-Agent': 'Mozilla/5.0 (gold-rv data refresh)', 'Referer': PAGE_URL}


# ------------------------------------------------------------------ raw -> clean (offline, tested)
def raw_to_clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn rows in the MCX endpoint's format into the clean schema (SPEC.md section 2.2)."""
    r = raw.copy()
    out = pd.DataFrame({
        'date': pd.to_datetime(r['Date'], format='%m/%d/%Y').dt.strftime('%Y-%m-%d'),
        'symbol': r['Symbol'].astype(str).str.strip(),
        'expiry_date': pd.to_datetime(r['ExpiryDate'].astype(str).str.strip(), format='%d%b%Y').dt.strftime('%Y-%m-%d'),
    })
    for src, dst in (('Open', 'open'), ('High', 'high'), ('Low', 'low'), ('Close', 'close'), ('PreviousClose', 'prev_close')):
        out[dst] = pd.to_numeric(r[src], errors='coerce').fillna(0).round().astype('int64')
    out['volume_lots'] = pd.to_numeric(r['Volume'], errors='coerce').fillna(0).astype('int64')
    grams_k = r['VolumeInThousands'].astype(str).str.extract(r'([\d.]+)')[0].astype(float).fillna(0.0)
    out['volume_grams'] = (grams_k * 1000).round().astype('int64')
    out['value_lakhs'] = pd.to_numeric(r['Value'], errors='coerce').fillna(0.0)
    out['open_interest_lots'] = pd.to_numeric(r['OpenInterest'], errors='coerce').fillna(0).astype('int64')
    out['lot_grams'] = out['symbol'].map(lambda s: CONTRACT_SPECS[s].lot_grams)
    out['quote_grams'] = out['symbol'].map(lambda s: CONTRACT_SPECS[s].quote_grams)
    out['purity'] = out['symbol'].map(lambda s: CONTRACT_SPECS[s].purity)
    out['px_per_g_pure'] = (out['close'] / out['quote_grams'] / out['purity']).round(4)
    out['days_to_expiry'] = (pd.to_datetime(out['expiry_date']) - pd.to_datetime(out['date'])).dt.days
    out['no_trade_day'] = (out['volume_lots'] == 0) | (out['open'] == 0)
    out['is_thin'] = (out['volume_lots'] < THIN_VOLUME_THRESHOLD) | (out['open_interest_lots'] < THIN_OI_THRESHOLD)
    return out.sort_values(['symbol', 'expiry_date', 'date']).reset_index(drop=True)


def contract_calendar(clean: pd.DataFrame) -> pd.DataFrame:
    """Per-contract lifecycle (SPEC.md section 7): liquid from the first day OI reaches 25% of its peak."""
    rows = []
    for (sym, exp), g in clean.sort_values('date').groupby(['symbol', 'expiry_date']):
        peak = int(g['open_interest_lots'].max())
        i_peak = g['open_interest_lots'].idxmax()
        liquid = g.loc[g['open_interest_lots'] >= 0.25 * peak, 'date']
        rows.append({'symbol': sym, 'expiry_date': exp, 'first_seen': g['date'].min(),
                     'liquid_from': liquid.min() if len(liquid) else None, 'peak_oi_lots': peak,
                     'peak_oi_date': g.loc[i_peak, 'date'], 'last_seen': g['date'].max(),
                     'rows': int(len(g)), 'no_trade_days': int(g['no_trade_day'].sum())})
    return pd.DataFrame(rows).sort_values(['symbol', 'expiry_date']).reset_index(drop=True)


def merge_raw(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Add new raw rows. Same key and same values: kept once. Same key, different values: stop loudly."""
    key = lambda d: (d['Symbol'].astype(str).str.strip() + '|' + d['ExpiryDate'].astype(str).str.strip() + '|' + d['Date'].astype(str))
    a, b = old.copy(), new.copy()
    a['_k'], b['_k'] = key(a), key(b)
    both = a.merge(b, on='_k', suffixes=('', '_new'))
    vals = ['Open', 'High', 'Low', 'Close', 'PreviousClose', 'Volume', 'Value', 'OpenInterest']
    diff = pd.Series(False, index=both.index)
    for c in vals:
        diff |= pd.to_numeric(both[c], errors='coerce').fillna(-1).ne(pd.to_numeric(both[c + '_new'], errors='coerce').fillna(-1))
    if diff.any():
        raise ValueError(f'{int(diff.sum())} downloaded rows conflict with rows already stored, e.g. {both.loc[diff, "_k"].iloc[0]}')
    add = b[~b['_k'].isin(a['_k'])]
    out = pd.concat([a, add], ignore_index=True).drop(columns='_k')
    return out[RAW_COLS]


# ------------------------------------------------------------------ network (needs MCX to allow the request)
def _session():
    import requests                     # only needed for downloading
    s = requests.Session()
    s.headers.update({'User-Agent': HEADERS['User-Agent']})
    return s


def list_expiries(session) -> Dict[str, List[str]]:
    """Expiries per symbol, from the JSON MCX embeds in the Bhavcopy page (element #symbol-data)."""
    html = session.get(PAGE_URL, timeout=30).text
    m = re.search(r'id="symbol-data"[^>]*>(.*?)</', html, re.S)
    if not m:
        raise RuntimeError('Could not find #symbol-data on the MCX Bhavcopy page (page changed or request blocked).')
    items = json.loads(m.group(1).strip())
    out: Dict[str, List[str]] = {}
    for it in items:
        sym = str(it.get('SymbolValue', '')).strip()
        if it.get('InstrumentName') == 'FUTCOM' and sym in CONTRACT_SPECS:
            out.setdefault(sym, []).append(str(it['ExpiryDate']).strip())
    return out


def fetch(session, symbol: str, expiry: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    """One (symbol, expiry) request. Dates go out as DD/MM/YYYY; rows come back with MM/DD/YYYY dates."""
    params = {'InstrumentName': 'FUTCOM', 'Symbol': symbol, 'Expiry': expiry,
              'fromDate': start.strftime('%d/%m/%Y'), 'toDate': end.strftime('%d/%m/%Y')}
    r = session.get(API_URL, params=params, headers=HEADERS, timeout=30)
    if r.status_code != 200 or not r.text.strip().startswith('{'):
        r = session.post(API_URL, data=json.dumps(params), headers=HEADERS, timeout=30)   # some MCX pages POST instead
    r.raise_for_status()
    body = r.json()
    if isinstance(body, dict) and 'd' in body and isinstance(body['d'], dict):
        body = body['d']
    if not body.get('IsSuccess', True):
        raise RuntimeError(f'MCX refused {symbol} {expiry}: {body}')
    df = pd.DataFrame(body.get('Data') or [])
    if df.empty:
        return pd.DataFrame(columns=RAW_COLS)
    df['Symbol'] = df['Symbol'].astype(str).str.strip()
    d = pd.to_datetime(df['Date'], format='%m/%d/%Y')
    exp = pd.to_datetime(expiry, format='%d%b%Y')
    keep = (d >= pd.Timestamp(start)) & (d <= pd.Timestamp(end)) & (d <= exp)     # drop rows outside the request
    out = df.loc[keep, RAW_COLS].reset_index(drop=True)
    out.attrs['dropped'] = int((~keep).sum())       # recorded in the retrieval log (it used to say 0 regardless)
    return out


def plan_requests(raw: pd.DataFrame, expiries: Dict[str, List[str]], today: dt.date) -> List[Tuple[str, str, dt.date, dt.date]]:
    """Live contracts from the day after our last row; new contracts from expiry - LOOKBACK_DAYS."""
    have = raw.assign(sym=raw['Symbol'].astype(str).str.strip(), exp=raw['ExpiryDate'].astype(str).str.strip(),
                      d=pd.to_datetime(raw['Date'], format='%m/%d/%Y'))
    last = have.groupby(['sym', 'exp'])['d'].max()
    plan = []
    for sym, exps in expiries.items():
        for e in exps:
            exp_date = pd.to_datetime(e, format='%d%b%Y').date()
            if exp_date < today - dt.timedelta(days=7):
                continue                                   # long expired: already complete
            start = (last[(sym, e)].date() + dt.timedelta(days=1)) if (sym, e) in last.index else exp_date - dt.timedelta(days=LOOKBACK_DAYS)
            end = min(today, exp_date)
            if start <= end:
                plan.append((sym, e, start, end))
    return plan


def update(today: Optional[dt.date] = None) -> int:
    today = today or dt.date.today()
    raw = pd.read_csv(RAW_PATH, dtype=str)
    s = _session()
    plan = plan_requests(raw, list_expiries(s), today)
    got, log = [], []
    for sym, exp, a, b in plan:
        df = fetch(s, sym, exp, a, b)
        got.append(df)
        d = pd.to_datetime(df['Date'], format='%m/%d/%Y') if len(df) else pd.Series(dtype='datetime64[ns]')
        log.append({'symbol': sym, 'expiry': pd.to_datetime(exp, format='%d%b%Y').strftime('%Y-%m-%d'), 'endpoint': API_URL,
                    'params': f'InstrumentName=FUTCOM&Symbol={sym}&Expiry={exp}', 'requested_from': a.strftime('%d/%m/%Y'),
                    'requested_to': b.strftime('%d/%m/%Y'),
                    'retrieved_at_ist': (dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d %H:%M'),
                    'rows': len(df), 'first_date': d.min().strftime('%Y-%m-%d') if len(df) else '',
                    'last_date': d.max().strftime('%Y-%m-%d') if len(df) else '',
                    'rows_outside_range_or_after_expiry': int(df.attrs.get('dropped', 0))})
        time.sleep(PAUSE_S)
    new = pd.concat(got, ignore_index=True).astype(str) if got else pd.DataFrame(columns=RAW_COLS)
    merged = merge_raw(raw, new)
    added = len(merged) - len(raw)
    # everything downloaded and checked: now write, raw first
    merged.to_csv(RAW_PATH, index=False)
    rebuild()
    if log:
        pd.concat([pd.read_csv(LOG_PATH), pd.DataFrame(log)], ignore_index=True).to_csv(LOG_PATH, index=False)
    print(f'{len(plan)} requests, {added} new rows. Now run: python -m pipeline.build_site_data')
    return added


def load_raw(with_supplement: bool = True) -> pd.DataFrame:
    """The MCX download, plus the supplement rows (never overlapping: a clash stops the build)."""
    raw = pd.read_csv(RAW_PATH)
    if with_supplement and os.path.exists(SUPPLEMENT_PATH):
        sup = pd.read_csv(SUPPLEMENT_PATH)
        merged = merge_raw(raw.astype(str), sup[RAW_COLS].astype(str))
        if len(merged) != len(raw) + len(sup):
            raise ValueError('supplement rows overlap the MCX download')
        raw = pd.concat([raw, sup[RAW_COLS]], ignore_index=True)
    return raw


def rebuild():
    raw = load_raw()
    clean = raw_to_clean(raw)
    dups = clean.duplicated(PK, keep=False)
    if dups.any():
        raise ValueError(f'{int(dups.sum())} duplicate (symbol, expiry, date) rows after conversion')
    clean.to_csv(CLEAN_PATH, index=False)
    contract_calendar(clean).to_csv(CAL_PATH, index=False)
    print(f'clean: {len(clean):,} rows, {clean["date"].min()} to {clean["date"].max()}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rebuild-only', action='store_true', help='no network; rebuild clean CSV and calendar from the raw file')
    args = ap.parse_args()
    try:
        rebuild() if args.rebuild_only else update()
    except Exception as e:                       # nothing has been written if the download failed
        print(f'Data refresh failed: {e}', file=sys.stderr)
        sys.exit(1)
