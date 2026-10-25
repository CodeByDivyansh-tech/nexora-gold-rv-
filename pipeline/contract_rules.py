"""Date-effective contract specifications and tender-period rules, with their sources and verification status.

Why this file exists (Oct-2026 compliance audit): the pipeline used one set of specifications per symbol for every
year, and a fixed 4-trading-day expiry buffer that was never checked against MCX's tender-period rules. Both are
now tables with an effective period, a source and a verification status, so a reader can see exactly what is
known, what is assumed, and what is missing.

Verification status (same words everywhere):
  official    read in an MCX circular or MCX contract-specification document          (none so far, see below)
  secondary   stated by broker notices / exchange-summary pages, not read in an MCX document
  assumed     no source for this period: today's specification is carried back unchanged
  unavailable the contract did not trade (or we hold no rows) in this period

MCX's website (mcxindia.com, mcxccl.com) refuses automated requests (HTTP 403), so no MCX document could be read
directly when this table was written. Nothing here is marked 'official' for that reason. Replace a 'secondary'
row with 'official' only after reading the MCX document named in its source.
"""
from typing import Dict, List, NamedTuple, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------------------------- specifications
class SpecRow(NamedTuple):
    symbol: str
    start: Optional[str]      # first date this row applies to (None: from the first row we hold)
    end: Optional[str]        # last date (None: still in force)
    lot_grams: int            # trading unit
    quote_grams: int          # price is quoted per this many grams
    purity: float             # fineness the quoted price refers to
    status: str
    source: str


# Our own MCX download starts on 10 Oct 2023. The current specifications are supported by secondary sources for that
# period; for earlier years (the compiled MCX data book) no source was found, so they are carried back as 'assumed'.
OURS_FROM = '2023-10-10'
_SRC_GOLDM = ('Broker/contract summaries: ICICI Direct "How to trade gold in commodity derivatives" (Gold Mini deliverable '
              '995 purity, quoted per 10 g); MCX Gold Mini product summary as returned by web search. Not read in an MCX document.')
_SRC_SMALL = ('Broker/contract summaries: ICICI Direct (Gold Ten, Gold Guinea, Gold Petal at 999 purity); MCX Gold Petal product '
              'summary "delivery 999 purity" as returned by web search; Gold Ten launch reports (HDFC Securities, Angel One, '
              'Mar 2025: 10 g unit, ₹1 per 10 g tick). Not read in an MCX document.')
_SRC_ASSUMED = 'No source found for this period. Today\'s specification is carried back unchanged (assumption, not evidence).'

SPEC_TABLE: List[SpecRow] = [
    SpecRow('GOLDM', None, '2023-10-09', 100, 10, 0.995, 'assumed', _SRC_ASSUMED),
    SpecRow('GOLDM', OURS_FROM, None, 100, 10, 0.995, 'secondary', _SRC_GOLDM),
    SpecRow('GOLDGUINEA', None, '2023-10-09', 8, 8, 0.999, 'assumed', _SRC_ASSUMED),
    SpecRow('GOLDGUINEA', OURS_FROM, None, 8, 8, 0.999, 'secondary', _SRC_SMALL),
    SpecRow('GOLDPETAL', None, '2023-10-09', 1, 1, 0.999, 'assumed', _SRC_ASSUMED),
    SpecRow('GOLDPETAL', OURS_FROM, None, 1, 1, 0.999, 'secondary', _SRC_SMALL),
    # GOLDTEN launched on MCX in 2025 (first row we hold: 31 Mar 2025); nothing exists before it
    SpecRow('GOLDTEN', '2025-03-31', None, 10, 10, 0.999, 'secondary', _SRC_SMALL),
]


def spec_rows(symbol: str) -> List[SpecRow]:
    return [r for r in SPEC_TABLE if r.symbol == symbol]


def spec_for(symbol: str, date) -> Tuple[Optional[SpecRow], str]:
    """The specification row in force for `symbol` on `date`, and its status ('unavailable' when no row covers it)."""
    d = pd.Timestamp(date)
    for r in spec_rows(symbol):
        if (r.start is None or d >= pd.Timestamp(r.start)) and (r.end is None or d <= pd.Timestamp(r.end)):
            return r, r.status
    return None, 'unavailable'


def apply_specs(df: pd.DataFrame, date_col: str = 'date') -> pd.DataFrame:
    """Adds lot_grams, quote_grams, purity and spec_status to every row from the date-effective table.

    Rows no table row covers keep the nearest row's numbers (so no raw row is dropped) but are marked 'unavailable';
    analysis code can exclude or qualify them with spec_status."""
    out = df.copy()
    out['lot_grams'] = 0
    out['quote_grams'] = 0
    out['purity'] = 0.0
    out['spec_status'] = 'unavailable'
    for sym in out['symbol'].unique():
        rows = spec_rows(sym)
        if not rows:
            raise KeyError(f'No specification rows for {sym}')
        m = out['symbol'] == sym
        d = out.loc[m, date_col]
        filled = pd.Series(False, index=d.index)
        for r in rows:
            sel = pd.Series(True, index=d.index)
            if r.start is not None:
                sel &= d >= pd.Timestamp(r.start)
            if r.end is not None:
                sel &= d <= pd.Timestamp(r.end)
            idx = sel[sel].index
            out.loc[idx, ['lot_grams', 'quote_grams', 'purity', 'spec_status']] = [r.lot_grams, r.quote_grams, r.purity, r.status]
            filled |= sel
        if (~filled).any():
            near = rows[0]
            idx = filled[~filled].index
            out.loc[idx, ['lot_grams', 'quote_grams', 'purity']] = [near.lot_grams, near.quote_grams, near.purity]
    out['lot_grams'] = out['lot_grams'].astype(int)
    out['quote_grams'] = out['quote_grams'].astype(int)
    return out


# ---------------------------------------------------------------------------------------------- tender periods
class TenderRow(NamedTuple):
    symbol: str
    expiry_from: str          # applies to contracts expiring in [expiry_from, expiry_to]
    expiry_to: str
    reported_td: int          # tender window length reported by the source: last N trading days incl. expiry day
    status: str
    source: str


# What sources report. The windows differ by contract and by period, so they are kept per symbol and per expiry.
TENDER_REPORTED: List[TenderRow] = [
    TenderRow('GOLDM', '2025-08-01', '2025-08-31', 5, 'secondary',
              'FYERS notice "Precious metals expiry 5th August 2025: compulsory delivery contracts" (Gold, Gold Mini: staggered '
              'delivery tender period 5 days before expiry). No MCX circular cited.'),
    TenderRow('GOLDPETAL', '2025-10-01', '2025-11-30', 5, 'secondary',
              'FYERS notices for the 31 Oct 2025 and 28 Nov 2025 expiries (Gold Petal, Gold Guinea, Gold Ten: compulsory delivery, '
              'tender period 5 days before expiry). No MCX circular cited.'),
    TenderRow('GOLDGUINEA', '2025-10-01', '2025-11-30', 5, 'secondary', 'As GOLDPETAL, same FYERS notices.'),
    TenderRow('GOLDTEN', '2025-10-01', '2025-11-30', 5, 'secondary', 'As GOLDPETAL, same FYERS notices.'),
    TenderRow('GOLDPETAL', '2026-02-01', '2026-02-28', 3, 'secondary',
              'FYERS notice for the 27 Feb 2026 expiry (Gold Petal, Gold Guinea, Gold Ten: staggered delivery tender period '
              'starting 3 days before expiry). MCX circular MCX/TRD/040/2026 (27 Jan 2026) sets a 3-day staggered delivery '
              'period for the 1 kg GOLD contract; its text was seen only as a search excerpt.'),
    TenderRow('GOLDGUINEA', '2026-02-01', '2026-02-28', 3, 'secondary', 'As GOLDPETAL, same FYERS notice.'),
    TenderRow('GOLDTEN', '2026-02-01', '2026-02-28', 3, 'secondary', 'As GOLDPETAL, same FYERS notice.'),
]

# The rule actually applied: the longest window any source reports (5 trading days including expiry day), for every
# contract and every year. A longer assumed window can only make positions close earlier, never later, so it is the
# safe fallback while most periods are unverified. Change only with an MCX document in hand.
CONSERVATIVE_TENDER_TD = 5


def tender_rule(symbol: str, expiry) -> Dict[str, object]:
    """Applied tender window for one contract (both legs of a pair are looked up separately).

    applied_td   the last `applied_td` trading days up to and including expiry are treated as the tender window
    reported_td  what a source reports for this contract (None if nothing found)
    status       'secondary' if a source covers this expiry, else 'unverified'"""
    e = pd.Timestamp(expiry)
    for r in TENDER_REPORTED:
        if r.symbol == symbol and pd.Timestamp(r.expiry_from) <= e <= pd.Timestamp(r.expiry_to):
            return {'applied_td': max(CONSERVATIVE_TENDER_TD, r.reported_td), 'reported_td': r.reported_td,
                    'status': r.status, 'source': r.source}
    return {'applied_td': CONSERVATIVE_TENDER_TD, 'reported_td': None, 'status': 'unverified',
            'source': 'No source found for this contract month; the conservative 5-trading-day window is applied.'}


def table_for_site() -> Dict[str, object]:
    """Both tables as plain data for the website (Data page) and the tests."""
    return {
        'specs': [dict(r._asdict()) for r in SPEC_TABLE],
        'tender_reported': [dict(r._asdict()) for r in TENDER_REPORTED],
        'conservative_tender_td': CONSERVATIVE_TENDER_TD,
        'note': ('No row is marked official: MCX\'s website refuses automated requests, so no MCX circular or specification '
                 'sheet could be read directly. Secondary means broker notices or exchange summaries; assumed means no source '
                 'was found and today\'s specification is carried back.'),
    }
