"""Configuration constants for the Gold Relative-Value Intelligence Pipeline."""
import datetime
from typing import Dict, Tuple, NamedTuple

class ContractSpec(NamedTuple):
    symbol: str
    lot_grams: int
    quote_grams: int
    purity: float
    expiry_window: str
    tick_size: float = 1.0

# Section 2.3: Contract Master
CONTRACT_SPECS: Dict[str, ContractSpec] = {
    'GOLDM': ContractSpec(
        symbol='GOLDM',
        lot_grams=100,
        quote_grams=10,
        purity=0.995,
        expiry_window='3rd-5th',
        tick_size=1.0,
    ),
    'GOLDTEN': ContractSpec(
        symbol='GOLDTEN',
        lot_grams=10,
        quote_grams=10,
        purity=0.999,
        expiry_window='27th-31st',
        tick_size=1.0,
    ),
    'GOLDGUINEA': ContractSpec(
        symbol='GOLDGUINEA',
        lot_grams=8,
        quote_grams=8,
        purity=0.999,
        expiry_window='27th-31st',
        tick_size=1.0,
    ),
    'GOLDPETAL': ContractSpec(
        symbol='GOLDPETAL',
        lot_grams=1,
        quote_grams=1,
        purity=0.999,
        expiry_window='27th-31st',
        tick_size=1.0,
    ),
}

# Quick lookup tuple format matching reference: (lot_g, quote_g, purity)
SPEC_TUPLES: Dict[str, Tuple[int, int, float]] = {
    k: (v.lot_grams, v.quote_grams, v.purity) for k, v in CONTRACT_SPECS.items()
}

# Section 4.4: Pairs Specification
# Pair ID -> (Leg A, Leg B, max_gap_days, lot_ratio_str, unit_grams)
class PairSpec(NamedTuple):
    pair_id: str
    symbol_a: str
    symbol_b: str
    max_gap_days: int
    lot_ratio_str: str
    unit_grams: int

PAIRS: Dict[str, PairSpec] = {
    'GUINEA_PETAL': PairSpec('GUINEA_PETAL', 'GOLDGUINEA', 'GOLDPETAL', 0, '1 : 8', 8),
    'TEN_PETAL': PairSpec('TEN_PETAL', 'GOLDTEN', 'GOLDPETAL', 0, '1 : 10', 10),
    'GUINEA_TEN': PairSpec('GUINEA_TEN', 'GOLDGUINEA', 'GOLDTEN', 0, '5 : 4', 40),
    'M_PETAL': PairSpec('M_PETAL', 'GOLDM', 'GOLDPETAL', 25, '1 : 100', 100),
    'M_TEN': PairSpec('M_TEN', 'GOLDM', 'GOLDTEN', 25, '1 : 10', 100),
    'M_GUINEA': PairSpec('M_GUINEA', 'GOLDM', 'GOLDGUINEA', 25, '2 : 25', 200),
}

# Quick lookup format matching reference
PAIR_DEFINITIONS = {
    'GUINEA_PETAL': ('GOLDGUINEA', 'GOLDPETAL', 0),
    'TEN_PETAL': ('GOLDTEN', 'GOLDPETAL', 0),
    'GUINEA_TEN': ('GOLDGUINEA', 'GOLDTEN', 0),
    'M_PETAL': ('GOLDM', 'GOLDPETAL', 25),
    'M_TEN': ('GOLDM', 'GOLDTEN', 25),
    'M_GUINEA': ('GOLDM', 'GOLDGUINEA', 25),
}

# Dates (Section 5.1)
TRAIN_START = '2023-10-10'
TRAIN_END = '2025-09-30'
TEST_START = '2025-10-01'
TEST_END = '2026-09-30'
# Anything after TEST_END (after a data refresh) is the 'forward' period: the frozen rule on data nobody
# had when the rule was written. It is reported on its own and never mixed into the train/test results.


def segment_of(dates):
    """'train' up to TRAIN_END, 'test' up to TEST_END, 'forward' after that (dates: anything pandas can parse)."""
    import numpy as np
    import pandas as pd
    d = pd.to_datetime(pd.Series(dates))
    return np.where(d <= pd.Timestamp(TRAIN_END), 'train', np.where(d <= pd.Timestamp(TEST_END), 'test', 'forward'))

# Trading parameters & thresholds (Sections 5.2, 5.3, 5.4)
TENDER_BUFFER_TD = 4        # LEGACY ONLY (reference study): exit when a leg has <= 4 trading days left
LEGACY_MIN_ENTRY_TD = 7     # LEGACY ONLY (reference study): min trading days to expiry on the signal day

# Contract lifecycle for the current rule (Oct-2026 compliance audit). The old 4-day buffer let exits fill inside a
# 5-day tender window. Now each leg has its own tender window (contract_rules.tender_rule: the conservative 5 trading
# days including expiry, never shorter than any source reports), and:
#   - an open position is closed by the close of the last trading day BEFORE either leg's tender window;
#   - the exit decision is taken EXIT_LEAD_TD trading days before that, so there are EXIT_LEAD_TD chances to fill;
#   - a new position needs both legs to be at least one day clear of that exit decision on its fill day.
# td_to_exp is 0 on expiry day, so a 5-day window covers td_to_exp 0..4 and the last allowed fill is td_to_exp 5.
EXIT_LEAD_TD = 2
from pipeline.contract_rules import CONSERVATIVE_TENDER_TD  # noqa: E402
MIN_ENTRY_TD = CONSERVATIVE_TENDER_TD + EXIT_LEAD_TD + 2    # 9: signal day; the fill day is then >= 8
MIN_VOLUME_LOTS = 25        # Liquidity filter (absolute floor, both legs, signal day and fill day)
MIN_OI_LOTS = 50            # Open-interest screen (both legs). OI is NOT evidence of executable depth.
# Size-aware liquidity (Oct-2026 audit): each leg's intended lots may be at most this share of that contract's
# traded volume on the signal day and on every fill day. Daily Bhavcopy volume cannot show bid-ask depth or
# guarantee execution; this is a screen, not a fill model. 5% is the threshold the old (unused) capacity flag used.
MAX_PARTICIPATION = 0.05
THIN_VOLUME_THRESHOLD = 25  # Volume below which is considered thin
THIN_OI_THRESHOLD = 50      # OI below which is considered thin
NOTIONAL_PER_LEG = 1_000_000 # Target notional in ₹ per leg (~₹10 Lakh)
DEFAULT_CARRY = 0.06        # Default reference carry if none available

# Grid search parameters (Section 5.1)
WINDOW_GRID = [10, 20, 30]
Z_ENTRY_GRID = [1.5, 2.0, 2.5]
Z_EXIT = 0.5
MAX_HOLD_GRID = [5, 10]
SLIPPAGE_SCENARIOS = [0, 2, 5, 10] # bps
BASE_SLIPPAGE = 5                  # bps

# Section 5.7: Statutory & Transaction Cost rates
BROKERAGE_PER_ORDER = 20.0          # Flat ₹20 per order
EXCHANGE_TURNOVER_RATE = 0.000021   # 0.0021% on notional
SEBI_TURNOVER_RATE = 0.000001       # ₹10 per crore (0.0001%)
CTT_RATE = 0.0001                   # 0.01% on sell side
STAMP_DUTY_RATE = 0.00002           # 0.002% on buy side
GST_RATE = 0.18                     # 18% on (brokerage + exchange + sebi)
THIN_SLIPPAGE_MULTIPLIER = 3.0      # 3x slippage when thin

# Section 5.9: one trading rule for both today's alerts and the backtest (audit fix, Oct-2026)
# The backtest used to check only 4 of the 5 alert gates (no cost hurdle), could enter
# beyond its own stop-loss, and could fill on extreme-move days. ALERT_RULE fixes all three.
HURDLE_MULTIPLE = 2.0      # gap from normal must be >= 2 x round-trip cost (at BASE_SLIPPAGE)
STOP_Z_BUFFER = 1.5        # stop-loss at |z| >= z_entry + 1.5; never enter at or beyond it
MAX_FILL_MOVE = 0.06       # no fills on a day either leg moved 6%+ (price may be stuck at the daily limit)
FILL_SEARCH_TD = 10        # trading days to look ahead for the next fillable exit day
MIN_TRAIN_TRADES = 10      # walk-forward switch: a pair is traded in Test only if its chosen
                           # setting made >= 10 trades AND a positive net (after costs) in Train

# Section 5.10: how clean is each out-of-sample test? (Oct-2026 review)
# The original study's test-year table is already in SPEC.md in the earliest commit (7a29bae, 2 Oct 2026).
# The five-check rule was committed on 4 Oct 2026 (1229c37), after those results were known, so the
# 2025-26 test year is NOT a clean out-of-sample test for it. The 2011-2023 history check (step 10) is:
# it ran on 7 Oct 2026 with the rule and settings already frozen, and nothing was changed afterwards.
TEST_YEAR_FIRST_SEEN = '2026-10-02'
RULE_FROZEN_ON = '2026-10-04'
TEST_YEAR_RULE_VERSIONS = 3   # rule versions scored on the test year: original, five checks, five checks + switch

LEGACY_RULE = {'use_hurdle': False, 'entry_band': False, 'max_fill_move': None,      # original study (reference_summary.csv)
               'lifecycle': 'legacy', 'max_participation': None}
ALERT_RULE = {'use_hurdle': True, 'entry_band': True, 'max_fill_move': MAX_FILL_MOVE,  # the rule the site shows
              'lifecycle': 'tender', 'max_participation': MAX_PARTICIPATION}

# Rolling statistics (one policy for alerts, charts and backtest): mean and spread of the previous W observations of
# the carry-adjusted spread (day t excluded). The window runs across contract rolls (the spread is carry-adjusted, so
# consecutive contracts are comparable; entry is blocked on a roll day). A gap of more than ROLLING_GAP_DAYS calendar
# days between observations restarts the window. (No such gap exists in the data as of Oct 2026.)
ROLLING_GAP_DAYS = 10

# Carry reference (pipeline/carry.py): GOLDPETAL calendar spreads whose near contract is inside its tender window
# are not used. A carry estimate outside [CARRY_SANE_LO, CARRY_SANE_HI] a year is flagged as unstable.
CARRY_SANE_LO = 0.0
CARRY_SANE_HI = 0.15
