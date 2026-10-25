# CLAUDE.md: working on Gold RV Intelligence

Read this first. It is the project guide for Claude Code (and anyone else) working in this repo.
The README explains the research; SPEC.md is the original build spec (data, formulas, backtest mechanics).

## What this is

- **Gold RV Intelligence**: a relative-value research site for MCX's four gold futures contracts
  (GOLDM 100 g, GOLDTEN 10 g, GOLDGUINEA 8 g, GOLDPETAL 1 g). Hack in Hills '26, Problem 03, Team NEXORA.
- Live: https://gold-rv.vercel.app (Vercel deploys `main` automatically on every push).
  3D intro: `/intro/`. 3D pitch deck: `/pitch/`.
- Verdict: the gaps between the contracts are real, but **no persistent edge is proven after costs**.
  Lead with the 2011–2023 historical holdout (settings never chosen on it; tender and liquidity rules tightened
  25 Oct 2026, after its first results were known): 88 trades, −₹1,30,655 at 5 bps slippage, t −2.04, 9 of 12
  years lost; at zero slippage it makes +₹51,534, so costs decide it. Never say it loses even at zero slippage.

## Layout

| Path | What |
|---|---|
| `pipeline/` | Python: data cleaning, carry, pairs, backtest, robustness, explorer, site data (`build_site_data.py`) |
| `pipeline/tests/` | pytest suite |
| `data/raw/` | `mcx_bhavcopy_raw_api.csv` (our MCX rows, source of truth), `gold_bhavcopy_clean.csv`, `contract_calendar.csv`, `retrieval_log.csv`, archived MCX CSVs (`mcx_csv/`), `mcx_bhavcopy_2003_2023.csv` (our MCX download of every 2004–2023 contract; used for 2011–2023 and the long charts), `mcx_bhavcopy_supplement.csv` (rows our first download missed, downloaded from MCX later), `mcx_bhavcopy_archive.csv` (a second copy of MCX rows, shared by another team; used only as a check) |
| `frontend/public/` | The static site: `pages/*.dc.html` (one per page), `app/*.js`, `data/*.json` (built by the pipeline) |
| `frontend/public/app/` | `dc.js` renderer, `theme.js` colours, `keys.js` shortcuts, `prefs.js`, `pdf.js` PDF writer, `rail.js` lit-glass menu, `glossary.js`, `explain.js` (Goldie) |
| `frontend/public/demo/` | Pitch video page (`gold-rv-pitch-video-2026-10-25.mp4` + `.webm`, captions and music) with chapters; the older walkthrough (`gold-rv-demo-video.*`) is kept |
| `frontend/public/intro/` | 3D intro (three.js r160 + GSAP, vendored in `public/pitch/vendor/`) and the halftone footer |
| `frontend/tests/pages.test.mjs` | Page logic tests against the real data (incl. the partial-period guard) |
| `frontend/build.mjs` | Copies `index.html` + `public/` into `dist/` (no bundler, no runtime dependencies) |

## Commands

```bash
pip install -r requirements.txt            # Python 3.11+
python -m pipeline.build_site_data         # rebuild ALL website data (5–10 min); commit the changed JSON
python -m pipeline.check_data              # committed data == fresh build (CI runs this)
python -m pytest pipeline/tests/ -q        # Python tests
cd frontend && npm test                    # page tests
cd frontend && npm run build               # -> frontend/dist
cd frontend/dist && npx serve -l 8765      # or: python -m http.server 8765  -> http://localhost:8765/
```

On Windows, if a clone fails with "Filename too long": `git config --global core.longpaths true`.

## Adding new MCX data (monthly)

MCX blocks scripted downloads, so new data arrives as CSVs downloaded by hand from the MCX website
(Bhavcopy, Commodity-wise, one file per contract: `BhavCopyCommodiyWise_*.csv`). For each live contract of
GOLDM, GOLDTEN, GOLDGUINEA, GOLDPETAL (6 expiries each), download from the day after the last data date.

```bash
python -m pipeline.import_csv path/to/BhavCopyCommodiyWise_*.csv   # merges, refuses conflicts, archives originals
python -m pipeline.build_site_data
python -m pipeline.check_data
```
Duplicate files are skipped; a stored row with different numbers stops the import (nothing changes).
Holidays have no rows; that is normal. Then branch, PR, wait for CI, merge (see Deploying).

## Rules (these came from real mistakes; do not break them)

1. **Never present a part of the study as the whole.** The study runs 18 Apr 2011 → latest date.
   Headlines, totals and dataset sizes cover every year (47,596 daily prices, 599 contracts, 4,141 days as of
   21 Oct 2026). The 12-month test year and our own 3-year download may be shown, but always named as parts.
   `frontend/tests/pages.test.mjs` has a guard test for this; keep it passing and extend it, never weaken it.
2. **The test year (Oct 2025–Sep 2026) is not a clean test**: the five-check rule was written after its
   first results were seen. The clean test is 2011–2023. Data after 30 Sep 2026 is "after the test year".
3. **Every number on the site comes from the pipeline** (`frontend/public/data/*.json`), never typed in.
   After any pipeline or data change: rebuild, run `check_data`, commit the JSON with the code.
4. **Credit the data**: every price is an official MCX Bhavcopy settlement that we downloaded from MCX's
   Bhavcopy service (2004–2023 contracts on 21 Oct 2026; Oct 2023 onward from Oct 2026), one logged request per
   contract. Say so on the Data page and in downloads. Never name another source for the prices; the second copy
   (`mcx_bhavcopy_archive.csv`) is only a check. A page test guards this. The intro's last card shows only the verdict (no team names, no buttons); Team NEXORA,
   the members, Enter the site and Watch demo video are in the Meet the team section below it, by the team's request.
5. Scope is gold only (no silver). Research, not investment advice.
6. No handover zip files; the GitHub repo is the hand-over.

## Design

- Font: Geist (+ Geist Mono for small data labels). Dark "vault" and light "champagne" themes from
  `app/theme.js`; gold `#E5B04A` (dark) / `#8F5B00` (light). Contract colours (same everywhere, incl. charts
  and the intro): GOLDM `#BC8424`, GOLDTEN `#2193E0`, GOLDGUINEA `#CD6199`, GOLDPETAL `#7D4DAD`.
- Left menu: "lit glass" (frosted panel, gold light from the top, sliding hover highlight, 1–8 badges).
- Motion: respect `prefers-reduced-motion`; no cursor effects on touch screens.
- Must work at phone width (390 px and 320 px) with no sideways scroll; check light and dark.
- Keyboard: 1–8 pages, Ctrl/Cmd+O search, Ctrl/Cmd+P PDF, `?` glossary, double-click a box for Goldie.

## Deploying

1. Work on a branch (`feature/...`, `fix/...`, `data/...`), never directly on `main`.
2. Run the checks above (page tests; pipeline + `check_data` if data or pipeline changed).
3. Push, open a PR, wait for the `test` check (GitHub Actions) to pass, then merge.
   Merging to `main` deploys to gold-rv.vercel.app within a minute or two.
4. Vercel preview links for PRs need a sign-in to the project's Vercel account.
5. Big visual changes: show a preview first and deploy only after the team says yes.
6. After deploying, open the live site and check the changed pages (no console errors, numbers right).

## Commit messages

Plain, specific subject; what changed and why in the body.
