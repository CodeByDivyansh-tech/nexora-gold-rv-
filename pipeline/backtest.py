"""Walk-forward backtesting engine (Sections 5.1–5.8)."""
import itertools
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional
from pipeline.config import (
    SPEC_TUPLES,
    PAIR_DEFINITIONS,
    NOTIONAL_PER_LEG,
    TENDER_BUFFER_TD,
    LEGACY_MIN_ENTRY_TD,
    EXIT_LEAD_TD,
    MIN_ENTRY_TD,
    MIN_VOLUME_LOTS,
    MIN_OI_LOTS,
    TRAIN_START,
    TRAIN_END,
    TEST_START,
    TEST_END,
    segment_of,
    WINDOW_GRID,
    Z_ENTRY_GRID,
    Z_EXIT,
    MAX_HOLD_GRID,
    SLIPPAGE_SCENARIOS,
    BASE_SLIPPAGE,
    HURDLE_MULTIPLE,
    STOP_Z_BUFFER,
    FILL_SEARCH_TD,
    MIN_TRAIN_TRADES,
    ALERT_RULE,
)
from pipeline.attribution import calculate_leg_cost, compute_attribution_metrics, calculate_round_trip_cost_bps
from pipeline.contract_rules import tender_rule
from pipeline.lifecycle import entry_timing_ok, intended_lots, size_liquidity_ok
from pipeline.pairs import rolling_stats


def hurdle_bps() -> float:
    """Cost hurdle used by both the alerts and the backtest: 2 x round-trip cost at base slippage."""
    return HURDLE_MULTIPLE * calculate_round_trip_cost_bps(slip_bps=BASE_SLIPPAGE)

def prepare_contract_lookup(df: pd.DataFrame) -> pd.DataFrame:
    """Prepares dataframe indexed by (symbol, expiry, date) for fast lookup.
    Adds day_move: the contract's close-to-close change, used to avoid fills on extreme days."""
    d = df.sort_values(['symbol', 'expiry', 'date']).copy()
    d['day_move'] = d.groupby(['symbol', 'expiry'])['close'].pct_change().fillna(0.0)
    return d.set_index(['symbol', 'expiry', 'date'])

def run_pair_backtest(
    pair_id: str,
    pair_series: pd.DataFrame,
    P: pd.DataFrame,
    dates: np.ndarray,
    tdi: Dict[pd.Timestamp, int],
    W: int,
    ze: float,
    mh: int,
    slip_bps: float,
    zx: float = Z_EXIT,
    start: Optional[pd.Timestamp] = None,
    end: Optional[pd.Timestamp] = None,
    rule: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """
    Simulates walk-forward backtest for a pair series (Sections 5.1–5.5, 5.9).

    rule (see config.ALERT_RULE / LEGACY_RULE):
      use_hurdle    -- also require |spread - mu| >= hurdle_bps() (the alerts' cost gate)
      entry_band    -- only enter when z_entry <= |z| < z_entry + STOP_Z_BUFFER (below the stop)
      max_fill_move -- skip entry / postpone exit when a leg moved this much on the fill day
    """
    rule = ALERT_RULE if rule is None else rule
    use_hurdle = bool(rule.get('use_hurdle', False))
    entry_band = bool(rule.get('entry_band', False))
    max_move = rule.get('max_fill_move')
    tender = rule.get('lifecycle', 'legacy') == 'tender'
    max_part = rule.get('max_participation')
    hurdle = hurdle_bps() if use_hurdle else 0.0
    stop_z = ze + STOP_Z_BUFFER
    sym_a, sym_b, _ = PAIR_DEFINITIONS[pair_id]
    x = pair_series.copy()

    # Point-in-time rolling statistics (strictly past observations only), the same definition the alerts and
    # charts use (pairs.rolling_stats). The reference study used a plain window (gap rule off); identical on our data.
    x['mu'], x['sd'], x['z'] = rolling_stats(x, W, gap_days=None if tender else -1)
    min_entry_td = MIN_ENTRY_TD if tender else LEGACY_MIN_ENTRY_TD
    
    if start is not None:
        x = x[x['date'] >= start]
    if end is not None:
        x = x[x['date'] <= end]
        
    x = x.reset_index(drop=True)
    n = len(x)
    trades: List[Dict[str, Any]] = []
    i = 0
    
    def get_row(sym: str, exp: pd.Timestamp, d: pd.Timestamp):
        try:
            return P.loc[(sym, exp, d)]
        except KeyError:
            return None

    def fillable(r) -> bool:
        if r is None or r['no_trade']:
            return False
        if max_move is not None and abs(float(r.get('day_move', 0.0))) >= max_move:
            return False
        return True

    def specs(r, sym):
        """Lot, quote grams and purity in force for this row (date-effective table), else the symbol's current spec."""
        if r is not None and 'quote_grams' in r.index and r['quote_grams']:
            return int(r['lot_grams']), int(r['quote_grams']), float(r['purity'])
        return SPEC_TUPLES[sym]

    def size_grams(px: float, lot_a: int, lot_b: int) -> int:
        """Section 5.4: equal grams on both legs, a whole number of lots of each, about NOTIONAL_PER_LEG per leg."""
        g = (lot_a * lot_b) // np.gcd(lot_a, lot_b)
        return int(g * max(1, round(NOTIONAL_PER_LEG / (g * px))))

    def participation(lots: float, r) -> float:
        """Intended lots as a share of the contract's traded volume that day (inf when volume is missing or zero)."""
        if r is None:
            return float('inf')
        v = r['vol']
        if v is None or pd.isna(v) or v <= 0:
            return float('inf')
        return float(lots) / float(v)

    def liquid(r, lots: float) -> bool:
        """Fill-day liquidity for one leg (current rule): volume and OI floors, and the participation cap."""
        if max_part is None:
            return True
        if r is None or pd.isna(r['vol']) or pd.isna(r['oi']):
            return False
        return r['vol'] >= MIN_VOLUME_LOTS and r['oi'] >= MIN_OI_LOTS and participation(lots, r) <= max_part

    # Each leg's tender window (contract_rules.tender_rule), looked up separately; legacy: the old 4-day buffer
    def tw(sym, exp):
        return tender_rule(sym, exp)['applied_td'] if tender else None

    while i < n - 1:
        z = x.at[i, 'z']
        ea_i, eb_i = x.at[i, 'expiry_a'], x.at[i, 'expiry_b']

        # Section 5.2: Entry conditions decided at close of t
        ok = (
            not np.isnan(z)
            and abs(z) >= ze
            and x.at[i, 'vol_a'] >= MIN_VOLUME_LOTS
            and x.at[i, 'vol_b'] >= MIN_VOLUME_LOTS
            and x.at[i, 'oi_a'] >= MIN_OI_LOTS
            and x.at[i, 'oi_b'] >= MIN_OI_LOTS
            and (entry_timing_ok(sym_a, ea_i, x.at[i, 'td_to_exp_a'], sym_b, eb_i, x.at[i, 'td_to_exp_b']) if tender
                 else (x.at[i, 'td_to_exp_a'] >= min_entry_td and x.at[i, 'td_to_exp_b'] >= min_entry_td))
            and not x.at[i, 'roll']
            and (not entry_band or abs(z) < stop_z)
            and (not use_hurdle or abs(x.at[i, 'spread'] - x.at[i, 'mu']) >= hurdle)
        )
        if ok and max_part is not None:
            # Signal-day size check (same helper as the live alerts): the lots this signal would trade, at that
            # day's price, against that day's volume and OI, each leg on its own
            _, la_n, lb_n = intended_lots(sym_a, sym_b, float(x.at[i, 'px_a']))
            ok = (size_liquidity_ok(la_n, x.at[i, 'vol_a'], x.at[i, 'oi_a'])[0]
                  and size_liquidity_ok(lb_n, x.at[i, 'vol_b'], x.at[i, 'oi_b'])[0])
        if not ok:
            i += 1
            continue

        ea = ea_i
        eb = eb_i
        sig_date = x.at[i, 'date']
        tw_a, tw_b = tw(sym_a, ea), tw(sym_b, eb)

        # Section 5.5: Fill at close of t+1
        curr_ti = tdi[sig_date]
        if curr_ti + 1 >= len(dates):
            break
        d1 = dates[curr_ti + 1]

        ra = get_row(sym_a, ea, d1)
        rb = get_row(sym_b, eb, d1)
        if not fillable(ra) or not fillable(rb):
            # Skip if t+1 is a no-trade day (or, under ALERT_RULE, an extreme-move day)
            i += 1
            continue
        lot_g_a, quote_g_a, purity_a = specs(ra, sym_a)
        lot_g_b, quote_g_b, purity_b = specs(rb, sym_b)
        grams = size_grams(float(ra['px']), lot_g_a, lot_g_b)
        lots_a, lots_b = grams / lot_g_a, grams / lot_g_b
        if tender and (ra['td_to_exp'] < tw_a + EXIT_LEAD_TD + 1 or rb['td_to_exp'] < tw_b + EXIT_LEAD_TD + 1):
            # the fill day must be clear of the forced-exit decision on both legs (never open into a tender window)
            i += 1
            continue
        if not (liquid(ra, lots_a) and liquid(rb, lots_b)):
            # fill day fails the liquidity check on either leg: no trade (a later signal day may still qualify)
            i += 1
            continue

        side = -np.sign(z)  # z > 0 -> short A, long B (side = -1); z < 0 -> long A, short B (side = +1)

        # Walk forward on series rows while same contracts
        j_match = x.index[x['date'] == d1]
        j = j_match[0] if len(j_match) > 0 else i + 1
        k_ = j
        reason = 'end'

        while True:
            if k_ >= n - 1:
                reason = 'data_end'
                break
            if x.at[k_, 'expiry_a'] != ea or x.at[k_, 'expiry_b'] != eb:
                k_ -= 1
                reason = 'roll'
                break
            zz = x.at[k_, 'z']
            if tender:
                # decide to exit EXIT_LEAD_TD trading days before the last day either leg may still be held
                if (x.at[k_, 'td_to_exp_a'] - tw_a <= EXIT_LEAD_TD) or (x.at[k_, 'td_to_exp_b'] - tw_b <= EXIT_LEAD_TD):
                    reason = 'tender'
                    break
            elif min(x.at[k_, 'td_to_exp_a'], x.at[k_, 'td_to_exp_b']) <= TENDER_BUFFER_TD:
                reason = 'expiry'
                break
            if not np.isnan(zz) and abs(zz) <= zx:
                reason = 'revert'
                break
            if not np.isnan(zz) and abs(zz) >= stop_z:
                reason = 'stop'
                break
            if tdi[x.at[k_, 'date']] - tdi[d1] >= mh:
                reason = 'time'
                break
            k_ += 1

        k_ = max(k_, j)

        # Exit fill at close of k+1 (or k if k+1 no-trade / end)
        exit_sig_date = x.at[k_, 'date']
        exit_ti = tdi[exit_sig_date]
        fill_delay = 0
        forced_fill = False
        if max_move is None:
            # Original behaviour (kept for the reference study)
            dx = dates[exit_ti + 1] if exit_ti + 1 < len(dates) else exit_sig_date
            xa = get_row(sym_a, ea, dx)
            xb = get_row(sym_b, eb, dx)
            if xa is None or xb is None or xa['no_trade'] or xb['no_trade']:
                dx = exit_sig_date
                xa = get_row(sym_a, ea, dx)
                xb = get_row(sym_b, eb, dx)
        else:
            def allowed(ca, cb):
                # current rule: a fill may never be inside either leg's tender window
                return not tender or (ca is not None and cb is not None and ca['td_to_exp'] >= tw_a and cb['td_to_exp'] >= tw_b)
            # Never fill at the signal's own close; walk forward to the next fillable day
            dx, xa, xb = None, None, None
            for step in range(1, FILL_SEARCH_TD + 1):
                if exit_ti + step >= len(dates):
                    break
                cand = dates[exit_ti + step]
                ca, cb = get_row(sym_a, ea, cand), get_row(sym_b, eb, cand)
                if tender and ca is not None and cb is not None and not allowed(ca, cb):
                    break
                if fillable(ca) and fillable(cb) and liquid(ca, lots_a) and liquid(cb, lots_b):
                    dx, xa, xb, fill_delay = cand, ca, cb, step - 1
                    break
            if dx is None and tender:
                # No day passed every check before the tender window: close on the first allowed day both legs
                # quote, even if thin or after a big move, and flag it (a forced exit, not a normal fill)
                for step in range(1, FILL_SEARCH_TD + 1):
                    if exit_ti + step >= len(dates):
                        break
                    cand = dates[exit_ti + step]
                    ca, cb = get_row(sym_a, ea, cand), get_row(sym_b, eb, cand)
                    if ca is not None and cb is not None and allowed(ca, cb) and not ca['no_trade'] and not cb['no_trade']:
                        dx, xa, xb, fill_delay, forced_fill = cand, ca, cb, step - 1, True
                        break
            if dx is None:
                # No fillable day found (data end / contract end): last day both legs quote
                for back in range(0, FILL_SEARCH_TD + 1):
                    cand_ti = min(exit_ti + FILL_SEARCH_TD, len(dates) - 1) - back
                    if cand_ti < tdi[d1]:
                        break
                    cand = dates[cand_ti]
                    ca, cb = get_row(sym_a, ea, cand), get_row(sym_b, eb, cand)
                    if ca is not None and cb is not None and (not tender or allowed(ca, cb) or cand_ti <= exit_ti):
                        dx, xa, xb, fill_delay = cand, ca, cb, max(0, cand_ti - exit_ti - 1)
                        forced_fill = bool(tender)
                        break
            if dx is None:
                break

        # Section 5.4: Sizing (equal grams, ~NOTIONAL_PER_LEG per leg); legacy sizes with the symbol's current spec
        if not tender:
            lot_g_a, quote_g_a, purity_a = SPEC_TUPLES[sym_a]
            lot_g_b, quote_g_b, purity_b = SPEC_TUPLES[sym_b]
            grams = size_grams(float(ra['px']), lot_g_a, lot_g_b)
            lots_a, lots_b = grams / lot_g_a, grams / lot_g_b

        # P&L in ₹ (Section 5.8)
        pnl_a = side * grams * (xa['close'] - ra['close']) / quote_g_a
        pnl_b = -side * grams * (xb['close'] - rb['close']) / quote_g_b
        gross = pnl_a + pnl_b

        # Gold attribution: net pure grams * ref change
        net_pure = side * grams * purity_a - side * grams * purity_b
        gold = net_pure * (xb['px'] - rb['px'])
        spread_pnl = gross - gold

        notA = grams * ra['px'] * purity_a
        notB = grams * rb['px'] * purity_b

        # Section 5.7: Costs for both legs, entry and exit kept apart (a forced exit pays its own exit costs)
        cost_entry = (calculate_leg_cost(notA, side_buy=(side > 0), slip_bps=slip_bps, is_thin=ra['thin'])
                      + calculate_leg_cost(notB, side_buy=(side < 0), slip_bps=slip_bps, is_thin=rb['thin']))
        cost_exit = (calculate_leg_cost(notA, side_buy=(side < 0), slip_bps=slip_bps, is_thin=xa['thin'])
                     + calculate_leg_cost(notB, side_buy=(side > 0), slip_bps=slip_bps, is_thin=xb['thin']))
        cost = cost_entry + cost_exit
        net = gross - cost

        gross_bps = (gross / notA) * 1e4
        net_bps = (net / notA) * 1e4
        holding_days = tdi[dx] - tdi[d1]

        part_in = max(participation(lots_a, ra), participation(lots_b, rb))
        part_out = max(participation(lots_a, xa), participation(lots_b, xb))
        cap_flag = (lots_a > 0.05 * x.at[i, 'vol_a']) or (lots_b > 0.05 * x.at[i, 'vol_b'])
        gold_ret_bps = (xb['px'] / rb['px'] - 1.0) * 1e4
        td_exit_a, td_exit_b = int(xa['td_to_exp']), int(xb['td_to_exp'])
        if tender:
            in_window = td_exit_a < tw_a or td_exit_b < tw_b
            ra_s, rb_s = tender_rule(sym_a, ea)['status'], tender_rule(sym_b, eb)['status']
            # 'official' only if both legs' tender rules were read in an MCX document (none are, as of Oct 2026)
            lifecycle = 'breach' if in_window else ('official' if ra_s == rb_s == 'official' else
                                                    'conservative-' + ('secondary' if 'unverified' not in (ra_s, rb_s) else 'unverified'))
        else:
            lifecycle = 'legacy'

        trades.append({
            'pair': pair_id,
            'sig': sig_date,
            'entry': d1,
            'exit_sig': exit_sig_date,
            'exit': dx,
            'expA': ea.date() if hasattr(ea, 'date') else ea,
            'expB': eb.date() if hasattr(eb, 'date') else eb,
            'z': round(float(z), 2),
            'side': int(side),
            'grams': int(grams),
            'lots_a': float(lots_a),
            'lots_b': float(lots_b),
            'notional': round(float(notA)),
            'gross': float(gross),
            'gold': float(gold),
            'spread_pnl': float(spread_pnl),
            'cost': float(cost),
            'cost_entry': float(cost_entry),
            'cost_exit': float(cost_exit),
            'net': float(net),
            'gross_bps': float(gross_bps),
            'net_bps': float(net_bps),
            'gold_ret_bps': float(gold_ret_bps),
            'reason': reason,
            'days': int(holding_days),
            'capacity_flag': bool(cap_flag),
            'part_entry': round(part_in, 5) if np.isfinite(part_in) else None,
            'part_exit': round(part_out, 5) if np.isfinite(part_out) else None,
            'fill_delay': int(fill_delay),
            'forced_fill': bool(forced_fill),
            'td_exit_a': td_exit_a,
            'td_exit_b': td_exit_b,
            'tender_td_a': tw_a,
            'tender_td_b': tw_b,
            'lifecycle': lifecycle,
        })

        if max_move is None:
            # Original behaviour: resume scanning after exit signal date
            i = x.index[x['date'] == exit_sig_date][0] + 1
        else:
            # Resume after the exit fill, so a new trade never overlaps a postponed exit
            nxt = x.index[x['date'] > max(exit_sig_date, dx)]
            if len(nxt) == 0:
                break
            i = int(nxt[0])

    return pd.DataFrame(trades)

def run_grid_search(
    pairs_dict: Dict[str, pd.DataFrame],
    P: pd.DataFrame,
    dates: np.ndarray,
    tdi: Dict[pd.Timestamp, int],
    train_end: str = TRAIN_END,
    rule: Optional[Dict[str, Any]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Evaluates parameter grid on Train and Test segments.
    Selects best parameters per pair on Train at 5 bps slippage.
    """
    t_end = pd.Timestamp(train_end)
    grid = list(itertools.product(WINDOW_GRID, Z_ENTRY_GRID, MAX_HOLD_GRID))
    res: List[Dict[str, Any]] = []
    
    for pair_id, p_df in pairs_dict.items():
        for W, ze, mh in grid:
            t = run_pair_backtest(pair_id, p_df, P, dates, tdi, W, ze, mh, slip_bps=BASE_SLIPPAGE, rule=rule)
            if not t.empty:
                t_train = t[t['entry'] <= t_end]
                t_test = t[(t['entry'] > t_end) & (t['entry'] <= pd.Timestamp(TEST_END))]   # never the forward period
            else:
                t_train = pd.DataFrame()
                t_test = pd.DataFrame()
                
            res.append({
                'pair': pair_id,
                'W': W,
                'ze': ze,
                'mh': mh,
                'seg': 'train',
                'n': len(t_train),
                'net': float(t_train['net'].sum()) if len(t_train) else 0.0,
                'net_bps': float(t_train['net_bps'].mean()) if len(t_train) else np.nan,
            })
            res.append({
                'pair': pair_id,
                'W': W,
                'ze': ze,
                'mh': mh,
                'seg': 'test',
                'n': len(t_test),
                'net': float(t_test['net'].sum()) if len(t_test) else 0.0,
                'net_bps': float(t_test['net_bps'].mean()) if len(t_test) else np.nan,
            })
            
    grid_df = pd.DataFrame(res)
    
    # Best per pair on Train by total net ₹
    best_df = (
        grid_df[grid_df['seg'] == 'train']
        .sort_values('net', ascending=False)
        .groupby('pair')
        .head(1)
        .set_index('pair')[['W', 'ze', 'mh']]
    )
    
    return grid_df, best_df

def run_all_scenarios(
    pairs_dict: Dict[str, pd.DataFrame],
    best_params: pd.DataFrame,
    P: pd.DataFrame,
    dates: np.ndarray,
    tdi: Dict[pd.Timestamp, int],
    train_end: str = TRAIN_END,
    rule: Optional[Dict[str, Any]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Runs best configuration per pair across all slippage scenarios (0, 2, 5, 10 bps).
    Returns (all_trades_df, summary_df).
    """
    t_end = pd.Timestamp(train_end)
    all_trades: List[pd.DataFrame] = []
    
    for pair_id, row in best_params.iterrows():
        W, ze, mh = int(row['W']), float(row['ze']), int(row['mh'])
        p_df = pairs_dict[pair_id]
        
        for slip in SLIPPAGE_SCENARIOS:
            t = run_pair_backtest(pair_id, p_df, P, dates, tdi, W, ze, mh, slip_bps=slip, rule=rule)
            if not t.empty:
                t['seg'] = segment_of(t['entry'].values) if t_end == pd.Timestamp(TRAIN_END) else np.where(t['entry'] <= t_end, 'train', 'test')
                t['slip'] = slip
                all_trades.append(t)
                
    if not all_trades:
        return pd.DataFrame(), pd.DataFrame()
        
    all_trades_df = pd.concat(all_trades, ignore_index=True)
    
    # Aggregated summary matching reference_summary.csv
    summary_df = (
        all_trades_df.groupby(['pair', 'slip', 'seg'])
        .agg(
            n=('net', 'size'),
            gross_bps=('gross_bps', 'mean'),
            net_bps=('net_bps', 'mean'),
            net_rs=('net', 'sum'),
            gold_rs=('gold', 'sum'),
            spread_rs=('spread_pnl', 'sum'),
            cost_rs=('cost', 'sum'),
            hit=('net', lambda s: (s > 0).mean()),
        )
        .round(1)
    )
    
    return all_trades_df, summary_df


def walk_forward_switch(all_trades_df: pd.DataFrame, pairs: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Section 5.9: decide, using Train only, which pairs are traded in Test.
    A pair is ON only if its chosen setting made >= MIN_TRAIN_TRADES trades and a positive
    net (after costs, at BASE_SLIPPAGE) in Train. Otherwise Train gave no evidence it works.
    """
    out: Dict[str, Dict[str, Any]] = {}
    base = all_trades_df[(all_trades_df['slip'] == BASE_SLIPPAGE) & (all_trades_df['seg'] == 'train')] \
        if len(all_trades_df) else pd.DataFrame(columns=['pair', 'net'])
    for pid in pairs:
        t = base[base['pair'] == pid]
        n = int(len(t))
        net = float(t['net'].sum()) if n else 0.0
        if n < MIN_TRAIN_TRADES:
            on, why = False, f'only {n} training trade{"s" if n != 1 else ""}, needs {MIN_TRAIN_TRADES}'
        elif net <= 0:
            on, why = False, 'lost money in training'
        else:
            on, why = True, 'made money in training'
        out[pid] = {'on': on, 'train_trades': n, 'train_net_rs': round(net, 1), 'reason': why}
    return out
