"""Oct-2026 audit: one published trade and one displayed signal recomputed by hand from the RAW MCX file
(data/raw/mcx_bhavcopy_raw_api.csv), with plain arithmetic and no pipeline function, so the site's numbers can be
traced to source rows. Uses a test-year trade and today's GOLDM · GOLDPETAL row."""
import json
import math

import pandas as pd

from pipeline.config import (BROKERAGE_PER_ORDER, CTT_RATE, EXCHANGE_TURNOVER_RATE, GST_RATE, SEBI_TURNOVER_RATE,
                             STAMP_DUTY_RATE, THIN_OI_THRESHOLD, THIN_SLIPPAGE_MULTIPLIER, THIN_VOLUME_THRESHOLD)

RAW = pd.read_csv('data/raw/mcx_bhavcopy_raw_api.csv', dtype={'Close': float, 'Volume': float, 'OpenInterest': float})
RAW['d'] = pd.to_datetime(RAW['Date'], format='%m/%d/%Y').dt.strftime('%Y-%m-%d')
RAW['e'] = pd.to_datetime(RAW['ExpiryDate'].str.strip(), format='%d%b%Y').dt.strftime('%Y-%m-%d')
RAW['Symbol'] = RAW['Symbol'].str.strip()
J = lambda p: json.load(open('frontend/public/data/' + p, encoding='utf-8'))
QUOTE, PURITY = {'GOLDM': 10, 'GOLDPETAL': 1}, {'GOLDM': 0.995, 'GOLDPETAL': 0.999}


def row(sym, exp, day):
    r = RAW[(RAW['Symbol'] == sym) & (RAW['e'] == exp) & (RAW['d'] == day)]
    assert len(r) == 1, (sym, exp, day)
    return r.iloc[0]


def leg_cost(notional, buy, slip_bps, thin):
    """Section 5.7 written out again: brokerage, exchange, SEBI, GST on those, CTT on sells, stamp duty on buys, slippage."""
    fees = BROKERAGE_PER_ORDER + notional * EXCHANGE_TURNOVER_RATE + notional * SEBI_TURNOVER_RATE
    tax = (notional * STAMP_DUTY_RATE) if buy else (notional * CTT_RATE)
    return fees * (1 + GST_RATE) + tax + notional * slip_bps * (THIN_SLIPPAGE_MULTIPLIER if thin else 1) / 1e4


def thin(r):
    return r['Volume'] < THIN_VOLUME_THRESHOLD or r['OpenInterest'] < THIN_OI_THRESHOLD


def test_a_published_trade_from_raw_rows():
    trades = [t for t in J('backtest/M_PETAL_5.json')['trades'] if t['seg'] == 'test']
    t = trades[0]
    a0, a1 = row('GOLDM', t['expA'], t['entry']), row('GOLDM', t['expA'], t['exit'])
    b0, b1 = row('GOLDPETAL', t['expB'], t['entry']), row('GOLDPETAL', t['expB'], t['exit'])
    g, s = t['grams'], t['side']
    gross = s * g * (a1['Close'] - a0['Close']) / 10 - s * g * (b1['Close'] - b0['Close']) / 1
    pxb = lambda r: r['Close'] / QUOTE['GOLDPETAL'] / PURITY['GOLDPETAL']
    gold = (s * g * 0.995 - s * g * 0.999) * (pxb(b1) - pxb(b0))
    na = g * a0['Close'] / 10 / 0.995 * 0.995
    nb = g * b0['Close'] / 1 / 0.999 * 0.999
    cost = (leg_cost(na, s > 0, 5, thin(a0)) + leg_cost(nb, s < 0, 5, thin(b0))
            + leg_cost(na, s < 0, 5, thin(a1)) + leg_cost(nb, s > 0, 5, thin(b1)))
    assert abs(gross - t['gross']) < 0.06
    assert abs(gold - t['gold']) < 0.06
    assert abs(cost - t['cost']) < 0.06
    assert abs((gross - cost) - t['net']) < 0.06
    assert abs((gross - gold) - t['spread_pnl']) < 0.06
    # size per leg and participation from the raw volumes
    assert t['lots_a'] == g / 100 and t['lots_b'] == g / 1
    assert abs(max(t['lots_a'] / a0['Volume'], t['lots_b'] / b0['Volume']) - t['part_entry']) < 1e-5


def test_todays_displayed_signal_from_raw_rows():
    today = [p for p in J('signals_today.json')['pairs'] if p['pair_id'] == 'M_PETAL'][0]
    a = row('GOLDM', today['expiry_a'], today['date'])
    b = row('GOLDPETAL', today['expiry_b'], today['date'])
    pxa, pxb = a['Close'] / 10 / 0.995, b['Close'] / 1 / 0.999
    carry = {r['date']: r['carry_pct'] / 100 for r in J('curve.json')['reference_carry_series']}[today['date']]
    gap_days = (pd.Timestamp(today['expiry_a']) - pd.Timestamp(today['expiry_b'])).days
    spread = (pxa / pxb - 1 - carry * gap_days / 365) * 1e4
    assert abs(spread - today['spread_bps']) < 0.06 + abs(gap_days) / 365 * 1e4 * 5e-6   # carry is stored to 0.001%
    # z from the previous W days of the published series (the same days the rule used), day t excluded
    W = J('backtest/M_PETAL_5.json')['params']['W']
    ser = [r for r in J('pairs/M_PETAL.json') if r['d'] < today['date']][-W:]
    s = [r['s'] for r in ser]
    mu = sum(s) / W
    sd = math.sqrt(sum((x - mu) ** 2 for x in s) / (W - 1))
    assert abs(mu - today['mu']) < 0.06 and abs(sd - today['sd']) < 0.06
    assert abs((today['spread_bps'] - mu) / sd - today['z']) < 0.01
    # size-aware liquidity on the raw volumes
    assert abs(today['lots_b'] / b['Volume'] - today['part_b']) < 1e-4
