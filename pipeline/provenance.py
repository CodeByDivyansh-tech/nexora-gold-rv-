"""Data provenance and reproducibility record (Oct-2026 compliance audit, Priority 8).

Writes frontend/public/data/provenance.json with:
  files       every file under data/raw: SHA-256, bytes, data rows, and whether it is a raw source or derived from one.
              A hash proves a file is byte-for-byte the same file (identity / integrity); it does NOT prove where the
              data came from or that it is correct (authenticity).
  ingestion   rows the download/import steps dropped or rejected, summed from the retrieval log (not assumed to be 0)
  price_field which Bhavcopy field the study uses, stated plainly
  rules       the date-effective specification and tender-period tables (pipeline/contract_rules.py)
  carry       how often the carry reference was flagged as unstable

Reads files only; it never changes anything under data/raw.
"""
import hashlib
import json
import os
from typing import Any, Dict

import pandas as pd

RAW_DIR = 'data/raw'

ROLES = {
    'mcx_bhavcopy_raw_api.csv': ('raw', 'Our MCX rows exactly as received (MCX endpoint and hand-downloaded Bhavcopy CSVs). Source of truth for Oct 2023 on.'),
    'mcx_bhavcopy_2003_2023.csv': ('raw', 'Our MCX download of every 2004-2023 GOLDM, GOLDGUINEA and GOLDPETAL contract; used for 2011-2023 and the long charts.'),
    'mcx_bhavcopy_archive.csv': ('reference', 'A second copy of MCX Bhavcopy rows; used only as a cross-check, never for a result.'),
    'mcx_bhavcopy_supplement.csv': ('raw', 'Rows our first download missed, downloaded from MCX on 21 Oct 2026 (Oct-Dec 2023 contracts, 1 Oct 2026).'),
    'retrieval_log.csv': ('raw', 'One line per MCX request or imported file: what was asked for and what came back.'),
    'gold_bhavcopy_clean.csv': ('derived', 'Built from the raw file + supplement by pipeline/download.py (rebuild reproduces it byte for byte).'),
    'contract_calendar.csv': ('derived', 'Built from the clean file by pipeline/download.py.'),
}


def _sha256(path: str) -> str:
    """SHA-256 of the file as stored in Git: text files with LF line ends (a Windows checkout has CRLF), so the
    manifest is the same on every machine."""
    with open(path, 'rb') as f:
        data = f.read()
    if path.endswith(('.csv', '.txt', '.json')):
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def _rows(path: str) -> int:
    with open(path, 'rb') as f:
        return max(0, sum(1 for _ in f) - 1)     # minus the header line


def manifest(raw_dir: str = RAW_DIR) -> list:
    out = []
    for root, _, files in os.walk(raw_dir):
        for name in sorted(files):
            p = os.path.join(root, name)
            rel = os.path.relpath(p, raw_dir).replace(os.sep, '/')
            role, what = ROLES.get(name, ('raw', 'Original MCX Bhavcopy CSV as downloaded by the team (archived by import_csv).')
                                   if rel.startswith('mcx_csv/') else ('other', ''))
            with open(p, 'rb') as fh:
                size = len(fh.read().replace(b'\r\n', b'\n')) if name.endswith('.csv') else os.path.getsize(p)
            out.append({'file': 'data/raw/' + rel, 'role': role, 'what': what, 'sha256': _sha256(p),
                        'bytes': size, 'rows': _rows(p) if name.endswith('.csv') else None})
    return out


def build(output_dir: str = 'frontend/public/data', raw_dir: str = RAW_DIR, carry_chosen: pd.DataFrame = None) -> Dict[str, Any]:
    from pipeline.contract_rules import table_for_site
    log = pd.read_csv(os.path.join(raw_dir, 'retrieval_log.csv'), dtype=str)
    num = lambda c: int(pd.to_numeric(log[c], errors='coerce').fillna(0).sum()) if c in log.columns else 0
    out = {
        'files': manifest(raw_dir),
        'hash_note': 'SHA-256 shows each file is byte-for-byte the file the site was built from (identity and integrity). '
                     'It does not show where the data came from or that it is correct.',
        'ingestion': {
            'requests_or_files': int(len(log)),
            'rows_received': num('rows'),
            'rows_outside_range_or_after_expiry': num('rows_outside_range_or_after_expiry'),
            'rows_rejected_not_futures': num('rows_rejected_not_futures'),
            'note': 'Counts as recorded in data/raw/retrieval_log.csv. Entries logged before Oct 2026 were written with 0 for '
                    'dropped rows by the old code; the true number for those requests was not kept.',
        },
        'price_field': ('Every price is the "Close" field of MCX\'s daily Bhavcopy for that contract. We have not verified that this '
                        'field equals MCX\'s official daily settlement price in every period, so the site calls it the Bhavcopy close.'),
        'rules': table_for_site(),
    }
    if carry_chosen is not None and len(carry_chosen):
        out['carry'] = {'days': int(len(carry_chosen)), 'unstable_days': int(carry_chosen['unstable'].sum()),
                        'median_pct': round(float(carry_chosen['c'].median()) * 100, 2)}
    with open(os.path.join(output_dir, 'provenance.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    return out


if __name__ == '__main__':
    o = build()
    print(len(o['files']), 'files;', o['ingestion'])
