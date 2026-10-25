# MCX Gold Relative-Value Intelligence Platform

[![Static Site](https://img.shields.io/badge/Architecture-Static%20Site%20(Zero%20Runtime%20Server)-success)](https://gold-rv.vercel.app)
[![Python Pipeline](https://img.shields.io/badge/Pipeline-Python%203.11%2B%20%7C%20Pandas%20%7C%20NumPy-blue)](#3-how-to-run-locally)
[![Frontend](https://img.shields.io/badge/Frontend-Static%20HTML%20%7C%20no%20runtime%20deps-orange)](#3-how-to-run-locally)
[![CI](https://github.com/CodeByDivyansh-tech/nexora-gold-rv-/actions/workflows/ci.yml/badge.svg)](https://github.com/CodeByDivyansh-tech/nexora-gold-rv-/actions/workflows/ci.yml)
[![Pitch Presentation](https://img.shields.io/badge/Pitch-Interactive%203D%20Deck-gold)](https://gold-rv.vercel.app/pitch/)

**Hack in Hills '26 · Problem 03: Commodity Derivatives Intelligence**
A relative-value (RV) research terminal across MCX Gold derivatives (`GOLDM`, `GOLDTEN`, `GOLDGUINEA`, `GOLDPETAL`).
• **Live site**: [gold-rv.vercel.app](https://gold-rv.vercel.app) · **Pitch**: [interactive 3D deck](https://gold-rv.vercel.app/pitch/) (`/pitch/`)

---

## 1. Key Analytical Findings

**Verdict: the gaps between the four contracts are real, but no persistent edge is proven after costs.**
Every number below is computed by the pipeline (`frontend/public/data/`), not typed in. The figures are from the
corrected rule (October 2026 compliance audit, section 1.6); the earlier figures are kept in Git history.

### 1.1 The clean test (historical holdout): 2011–2023 (88 trades)

The settings were chosen on training data only and were never chosen on these years (data: a compiled MCX
Bhavcopy data book, shared with permission). Only the three pairs that existed then can be tested. One caveat
we state openly: the October 2026 lifecycle and liquidity correction was made after the earlier version's results
on these years were known (to fix the contract rules, not to change the result), so this holdout is no longer
strictly unseen.

How we know the book is right: where the book and our own MCX download cover the same days (10 Oct 2023 →
16 Oct 2026), they agree on all **12,021 shared rows**, every field, 0 mismatches (`history.json → check`).
That overlap check is separate from the raw-vs-clean check of our own download (12,507 rows, section 1.5).

| At 5 bps slippage | Trades | Net after costs | t-stat | Losing years |
|---|---|---|---|---|
| GOLDM − GOLDPETAL, GOLDM − GOLDGUINEA, GOLDGUINEA − GOLDPETAL | 88 | **−₹1,30,655** | −2.04 | 9 of 12 |

With **zero** slippage it would have made ₹51,534; it breaks even at about 1.4 bps of slippage per order, so costs
decide it (`history.json`, `evidence.json → slippage.breakeven`).

Even with hindsight: at 5 bps slippage, only **8 of 216** settings in the explorer grid make money on 2011–2023
(the three pairs × 72 settings each; `site-data.json → hindsight`, computed from `explore.json`).

### 1.2 The 2025–26 test year: not a clean test

Settings were chosen once on Train (10-Oct-2023 → 30-Sep-2025, highest net after costs at 5 bps) and frozen for
Test (01-Oct-2025 → 30-Sep-2026), ₹10 lakh per leg, every MCX cost, next-day fills. This is **one train/test
split plus a historical holdout, not a rolling walk-forward**: settings are never re-fitted and there is no
separate validation period. **And** the original study's test-year results were known by 2 Oct 2026, before the
five-check rule was written on 4 Oct 2026, so the test year is **not** a clean out-of-sample test
(`evidence.json → test_year`).

| Rule (5 bps slippage) | Train trades | Train net | Test trades | Test net | t-stat | Closed in Jan–Mar 2026 crash | Test outside crash |
|---|---|---|---|---|---|---|---|
| Five checks, corrected (what the site shows) | 33 | +₹3,775 | 17 | −₹57,003 | 0.40 | −₹33,564 (7 trades) | −₹23,439 (10 trades) |
| Original study (4 checks, no cost line) | 60 | −₹63,801 | 51 | +₹37,318 | 0.09 | +₹1,70,806 | −₹1,33,487 |
| Five checks + training switch | — | — | 3 | +₹14,850 | — | — | — |

- **Significance**: t = 0.40 on 17 trades gives p = 0.69. 108 settings (18 per pair) were tried on training only,
  which is tuning, not testing.
- **Resampling** (10,000 draws): 32% of test-year totals stay above ₹0, 10% without the crash trades, 56% in
  training, 1% in the clean test.
- **Training switch**: only GOLDM − GOLDPETAL qualifies, on +₹19,793 over 14 training trades (t = 0.84): close to a
  coin flip.

### 1.3 Slippage: the number that decides it, and daily data cannot measure it

Slippage (5 bps per order, assumed) is 82% of the 24.4 bps round-trip cost. `pipeline/evidence.py` tries to
measure it from the daily data with two standard estimators (Roll 1984; Corwin & Schultz 2012). Both find no
spread on most contracts and months (it is smaller than a day's price noise); with negative readings set to zero
they give 26–31 bps for every contract alike, which is volatility, not a spread. The hard floor is half a tick,
at most 0.34 bps. Our fills were a median 0.06% of the day's volume (largest 3.1%; none over the 5% cap).

Break-even slippage per order: **training 5.3 bps · test year never (loses at 0) · 2011–2023 1.4 bps**.
Only real broker fills (a forward test) can settle it.

### 1.4 Market structure

- **Normalization**: `₹ per 10 g pure = Bhavcopy close ÷ grams quoted ÷ purity × 10`, purity applied once, using the
  specification in force on each row's date (`pipeline/contract_rules.py`). Lot sizes 1 / 8 / 10 / 100 g;
  purities GOLDM 995, the others 999. These come from broker and exchange-summary sources, **not** an MCX
  document (mcxindia.com refuses automated requests), and before Oct 2023 they are assumed unchanged.
- **GOLDPETAL repriced in November 2024**: GOLDGUINEA − GOLDPETAL fell from +203 to +19 bps between 4 and 11 Nov 2024,
  inside one contract (Nov-2024 expiry). Against GOLDM, GOLDPETAL rose about 249 bps and GOLDGUINEA about 66 bps,
  so most of the move was GOLDPETAL. Median gap +255 bps (May–Nov 2024) vs −29 bps (Feb–Jul 2025). Located by a
  level-shift test in `pipeline/evidence.py`; **cause not confirmed** (no MCX notice found, and no specification
  change was found that would explain it). Because the "normal" level moves, signals use a rolling point-in-time
  window, never a fixed zero or full-sample mean.
- **Carry and term structure**: GOLDPETAL calendar spreads (contracts inside their tender window skipped) imply a
  median 8.0% a year (middle half 6.35–10.51%); 104 of 778 daily estimates are outside 0–15% and flagged unstable.
  The Market page shows the futures curve (latest vs about a month earlier) and the daily decomposition of each
  contract's price change into gold, roll-down, curve change and residual. It is an accounting identity (the parts
  add back exactly), so it shows where a move came from, not why.
- **Gold exposure**: equal grams on both legs. Over all 138 trades, 2011–2026 (5 bps), the gold part is −₹417 against
  +₹1,85,394 gross; the daily portfolio's correlation with gold returns is −0.04 (`portfolio.json`).
- **Contract calendar**: every trade, 2011–2026, sits inside both contracts' calendars and is closed before either
  leg's tender window (`history.json → calendar`, `contracts.json → calendar`).

### 1.5 The data: what we have, what was missing, what we still need

| | |
|### 1.6 October 2026 compliance corrections (and what they changed)

A compliance review against the problem statement found rules that were weaker than they looked. They were fixed in
the pipeline, not in the presentation, and every figure above was rebuilt:

| Correction | Where | Effect on the 2011–2023 holdout (same settings, 5 bps) |
|---|---|---|
| Tender periods: each leg has its own window (`contract_rules.tender_rule`; the conservative 5 trading days incl. expiry, never shorter than any source reports). No entry within 9 trading days of expiry; positions closed by the last day before either leg's window | `contract_rules.py`, `backtest.py`, `alerts.py`, `lifecycle.py` | 151 → 128 trades |
| Size-aware liquidity: each leg's intended lots ≤ 5% of that contract's volume, on the signal day and on every fill day (open interest is only a screen) | `config.MAX_PARTICIPATION`, `lifecycle.size_liquidity_ok` | 151 → 103 trades |
| Carry reference skips GOLDPETAL contracts inside their tender window; estimates outside 0–15% a year flagged | `carry.py` | 151 → 153 trades |
| All corrections together | | 151 trades, −₹5,49,070 → **88 trades, −₹1,30,655**; at zero slippage −₹2,35,391 → **+₹51,534** |

Also: one rolling z-score definition for alerts, charts and backtest (`pairs.rolling_stats`; identical numbers, as
the data has no gap over 10 days); date-effective contract specifications with a verification status per row; a
daily mark-to-market portfolio across all pairs (`portfolio.py`: drawdown, daily Sharpe, Newey–West t, exposure,
gold benchmark); the per-trade "Sharpe" is no longer annualised; a SHA-256 manifest of `data/raw` and real
ingestion drop counts (`provenance.py`); and the site's wording now says "Bhavcopy close", "train/test split" and
"historical holdout" instead of "official settlement", "walk-forward" and "years the rule never saw".

**Not verified**: no MCX circular or specification sheet could be read directly (MCX refuses automated requests).
Tender windows and specifications come from broker notices and exchange summaries; no trade is marked as fully
lifecycle-verified. Margin is not modelled, so no return on capital is reported.

---|---|
| **Coverage (whole study)** | 18 Apr 2011 → 16 Oct 2026: **47,521 daily prices, 599 contracts, 4,138 trading days**, every one the MCX Bhavcopy close (not verified to equal the official settlement price in every period) (`site-data.json → longrun`) |
| **Part 1: MCX history book** | 18 Apr 2011 → 9 Oct 2023: 35,014 daily prices, 457 contracts, 3,359 trading days (the clean test). Shared with us by another team, with permission |
| **Part 2: our own MCX download** | 10 Oct 2023 → 16 Oct 2026: 12,507 daily prices, 150 contracts, 779 trading days (training, test year and after). Every day the history book has in this window is present (a test checks this) |
| **Fixed in Oct 2026** | Our MCX download had skipped 8 contracts: the Oct, Nov and Dec 2023 expiries of GOLDM, GOLDGUINEA and GOLDPETAL (289 traded rows, the busiest contracts in those months). They are now added from the MCX history book, with 1 Oct 2026, in `data/raw/mcx_bhavcopy_supplement.csv`. Effect: training 37 → 38 trades, −₹19,056 → −₹16,514; settings, test year, 2011–2023 check and alerts unchanged |
| **Checked and fine** | No missing days inside any contract's life; no broken high/low/close; the 6%+ days (Jan–Mar 2026, 19 Mar, 13 May 2026) moved all four contracts together, so they are real; GOLDM's Nov-2024 contract expired early, on 31 Oct 2024 |
| **Exchange quirk** | 169 rows where MCX's "previous close" differs from the prior day's close, mostly thin contracts and no-trade days; the pipeline never uses that field for signals |
| **Still missing** | 17 Oct 2026 onward. MCX blocks scripted downloads, so new rows come from Bhavcopy CSVs downloaded by hand (see "Refreshing the data") |
| **Would help most** | Real broker fills or intraday bid/ask, to measure slippage (82% of the cost, and the number that decides the verdict); MCX circulars for Nov 2024 (the GOLDPETAL repricing); MCX's official contract spec sheets (purities, delivery centres) |

---

## 2. Architecture

A fully **static site** (deployed on Vercel from `main`): a Python pipeline precomputes every number into JSON,
and plain HTML/JS pages read it. No server at runtime.

```
gold-rv/
├── SPEC.md                     # Original build spec (maths still current; see its note on what changed)
├── README.md
├── requirements.txt            # pandas, numpy, scipy, pytest, requests
├── .github/workflows/
│   ├── ci.yml                  # tests + build + "committed data matches a fresh run" on every push
│   └── refresh-data.yml        # manual: download new MCX rows, rebuild, test, commit
├── data/raw/
│   ├── mcx_bhavcopy_raw_api.csv   # rows exactly as the MCX endpoint returns them (source of truth)
│   ├── mcx_bhavcopy_supplement.csv # 313 official MCX rows our download missed, from the MCX history book
│   ├── gold_bhavcopy_clean.csv    # 12,507 rows (our download, Oct 2023 on), derived from the raw file + supplement
│   ├── contract_calendar.csv      # contract lifecycles, derived from the clean file
│   ├── mcx_csv/                   # every MCX Bhavcopy CSV imported by hand (pipeline/import_csv.py), kept as received
│   ├── retrieval_log.csv          # one line per MCX request
│   └── mcx_history_book.csv       # 55,457 MCX rows, Nov-2003 → Oct-2026 (compiled data book, shared with permission)
├── reference/                  # reference_check.py + its outputs (the original study's benchmark)
├── pipeline/
│   ├── config.py               # contract master, costs, parameters, split dates, segment_of()
│   ├── download.py             # raw -> clean -> calendar (and a scripted MCX refresh, where MCX allows it)
│   ├── import_csv.py           # the monthly route: merge hand-downloaded MCX Bhavcopy CSVs, refuse conflicts
│   ├── load.py · normalize.py · carry.py · pairs.py
│   ├── backtest.py · attribution.py · alerts.py · lifecycle.py
│   ├── history.py              # frozen rule on 2011–2023 (history.json)
│   ├── evidence.py             # test-year status, slippage check, multiple testing, switch, GOLDPETAL break
│   ├── robustness.py           # alert follow-through and resampled 95% ranges (robustness.json)
│   ├── explore.py              # the real engine over a grid of settings (explore.json); hindsight count
│   ├── build_site_data.py      # runs everything, writes frontend/public/data/*.json
│   ├── build_web_data.py       # site-data.json, the one file the pages read
│   ├── check_data.py           # committed data == a fresh build (CI)
│   └── tests/                  # 78 pytest tests
└── frontend/
    ├── index.html · build.mjs · tests/pages.test.mjs
    └── public/
        ├── app/dc.js           # ~400-line renderer: templates, repeats, conditions, components, DOM morphing
        ├── app/main.js         # hash router: #/ #/today #/market #/pairs #/signals #/backtesting #/explore #/data #/brief
        ├── app/keys.js         # shortcuts 1–9, Ctrl/Cmd+O search, Ctrl/Cmd+P PDF; theme.js, prefs.js, pdf.js, rail.js, glossary.js, explain.js
        ├── pages/*.dc.html     # one file per page; Rail.dc.html and TabBar.dc.html are the shared menus
        ├── pages/Brief.dc.html # "The brief, answered": each line of Problem 03, its status and the page that proves it
        ├── intro/              # the 3D intro shown on a first visit
        ├── pitch/              # the 3D pitch deck
        └── data/               # JSON written by the pipeline (committed)
```

---

## 3. How to Run Locally

Prerequisites: Python 3.11+, Node.js 18+ (no npm packages needed to build or test).

```bash
pip install -r requirements.txt
python -m pipeline.build_site_data      # writes frontend/public/data/ (5–10 min or more; the explorer grid is most of it)
python -m pipeline.check_data           # committed data == fresh build
python -m pytest pipeline/tests/        # 78 tests
cd frontend
npm test                                # page logic against the real data
npm run build                           # writes dist/
python -m http.server 8000 --directory dist
```

Open `http://localhost:8000`. (`npm install && npm run dev` also works, using Vite as a dev server.)

### Refreshing the data

MCX blocks scripted downloads, so new data arrives each month as CSVs downloaded by hand from the MCX website
(Bhavcopy, Commodity-wise, one file per contract) for every live GOLDM, GOLDTEN, GOLDGUINEA and GOLDPETAL expiry,
starting the day after the last data date:

```bash
python -m pipeline.import_csv path/to/BhavCopyCommodiyWise_*.csv   # merges, refuses conflicts, archives originals
python -m pipeline.build_site_data
python -m pipeline.check_data
```

Where MCX does allow it, `python -m pipeline.download` fetches new rows directly.

- Trades entered after 30-Sep-2026 go into a separate **forward** period (the frozen rule on data nobody had
  when it was written). They are never mixed into the training or test-year results, and the site reports them on
  their own.
- Tests that check the published research figures load data only up to 30-Sep-2026, so a refresh doesn't break them.
- MCX may block scripted requests, which is why the download part has not been run from CI yet. If it fails,
  nothing is written. `python -m pipeline.download --rebuild-only` rebuilds the clean CSV and calendar from the raw
  file without the network (CI checks that this reproduces the committed files exactly).
- On GitHub: Actions → **Refresh MCX data** → Run workflow. Once a manual run succeeds, the schedule in
  `.github/workflows/refresh-data.yml` can be switched on.

---

## 4. Deployment

**Vercel (current)**: the live site deploys from `main`. To set it up again: import the repository, set Root
Directory `frontend`, Build Command `npm run build`, Output Directory `dist`.

**Render Static Site (alternative)**: New → Static Site → this repo; Root Directory `frontend`, Build Command
`npm install && npm run build`, Publish Directory `dist`.

When the data changes, re-run the pipeline, commit `frontend/public/data/`, and push. CI fails if the committed data
does not match what the pipeline produces from the committed code.

---

## 5. Verification (pytest, 78 tests)

| Requirement | Test module |
|---|---|
| Normalization fixtures to 0.01; `volume_grams / volume_lots` = lot grams; 0 duplicate keys | `test_load_normalize.py` |
| GOLDPETAL median implied carry within [3%, 12%] (8.03%) | `test_carry.py` |
| Zero look-ahead in rolling z-score and in contract pair selection | `test_pairs.py` |
| Trades inside lifecycle windows; all 6 pairs Quiet on 2026-09-30 | `test_alerts_lifecycle.py` |
| Fills strictly after signals; spread + gold − costs = net; original study reproduces `reference_summary.csv` | `test_backtest.py` |
| Every trade passed the five checks; no fills on 6%+ days; drawdown counts an opening loss; switch uses Train only | `test_rule_fixes.py` |
| Data book matches our MCX download; history uses frozen settings and only earlier days | `test_history.py` |
| Alert follow-through and resampling are repeatable and match the backtest | `test_robustness.py` |
| Verdict leads with the clean test and never calls the test year "unseen"; p-values computed; break-evens fit the scenarios; GOLDPETAL break located from data | `test_evidence.py` |
| Raw MCX file rebuilds the clean CSV and calendar byte for byte; merge refuses conflicts; forward trades never join the test year | `test_download.py` |
| Prohibited strings (`COMEX`, `USD/INR`, `Confidence`, …) absent from the site | `test_frontend_acceptance.py` |
| No position opens or closes inside either leg's tender window; both legs checked independently; forced exits pay exit costs; live gates = backtest; reproducible; carry skips tender-window contracts; one rolling-statistics definition | `test_lifecycle_liquidity.py` |
| Every fill ≤ 5% of each leg's volume; low-volume, missing-volume, low-OI and failed-fill-day cases | `test_lifecycle_liquidity.py` |
| Date-effective specifications (boundaries, unavailable/assumed rows), normalization formula; daily marks add up to each trade; Newey–West; portfolio reconciles; raw-file hashes match Git | `test_specs_portfolio_provenance.py` |
| One published trade (gross, gold part, costs, net, participation) and today's displayed signal (spread, normal level, z) recomputed by hand from the raw MCX rows | `test_reproduce_from_raw.py` |
| "6 of 216" hindsight count matches the explorer grid it summarises | `test_hindsight.py` |

Plus `npm test` (`frontend/tests/pages.test.mjs`): 183 page and menu states rendered against the real data, then
checks on full-history charts, the explorer, the partial-period guard, downloads (CSV, PDF), chart file names and
the Brief page (every row links to a section that exists; every number comes from the data files).

---

## 6. Research Limitations

1. **Closes vs fills**: prices are the Bhavcopy Close field, a daily reference, not an executable fill; we have not verified that it equals the official settlement price in every period.
2. **Volume vs depth**: traded lots show activity, not order-book depth.
3. **Slippage is assumed, not measured** (82% of round-trip cost); daily data cannot measure it (section 1.3).
4. **The test year is not clean**: the five-check rule was written after its first results were seen. The clean test is 2011–2023.
5. **Small test sample**: 17 test-year trades (2–4 per pair that traded).
6. **One crash looms over the test year**: 7 of its 17 trades closed in the Jan–Mar 2026 crash (−₹33,564). The crash window was named after the results were seen, so the split is a check, not a test.
7. **GOLDTEN history**: listed 31-Mar-2025; only 6 months in training, and absent from the 2011–2023 check.
8. **GOLDPETAL repricing (Nov 2024)**: located precisely, cause unconfirmed.
9. **Past fee rates**: the 2011–2023 check charges today's MCX fee rates.
10. **Forced exits on contract switches** add cost.
11. **Tender periods and specifications not verified from MCX documents** (section 1.6); a conservative 5-day window is applied.
12. **No rolling walk-forward**: one train/test split plus a historical holdout; the Oct-2026 correction came after the earlier results were known.
