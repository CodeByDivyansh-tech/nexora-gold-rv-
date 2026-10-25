/*
 * pitch/data.js — fills the deck's result figures from the pipeline's JSON (../data/site-data.json), so the pitch,
 * the site and the data never contradict each other (Oct-2026 audit: the deck had hand-typed figures that went stale).
 *
 *   [data-pitch="key"]  text (or a counter's data-target / data-prefix) set from the data below
 *   slides 10-12        their hand-drawn charts were drawn from an earlier data build; a visible note under the title
 *                       gives the current figures instead of silently showing old bars
 *   narration           the result lines Goldie speaks and the presenter notes are rebuilt from the same numbers
 */
const D = await fetch('../data/site-data.json', { cache: 'no-cache' }).then((r) => r.json()).catch(() => null);

if (D) {
  const rs = (v) => (v < 0 ? '−' : '+') + '₹' + Math.round(Math.abs(v)).toLocaleString('en-IN');   // half-up on the size, as the site
  const words = (v) => Math.round(Math.abs(v)).toLocaleString('en-IN') + ' rupees';
  const sg = (v, d) => (v < 0 ? '−' : '') + Math.abs(v).toFixed(d);
  const C = D.rule.current['5'], O = D.rule.original['5'], L = D.longrun;
  const PAIRS = Object.keys(D.backtest);
  const label = (p) => D.pairs[p].label;
  const on = PAIRS.filter((p) => D.rule.switch[p] && D.rule.switch[p].on);

  const set = (key, text) => document.querySelectorAll('[data-pitch="' + key + '"]').forEach((el) => { el.textContent = text; });
  const counter = (key, v, decimals) => document.querySelectorAll('[data-pitch="' + key + '"]').forEach((el) => {
    el.dataset.target = String(Math.abs(v));
    if (el.dataset.prefix !== undefined) el.dataset.prefix = (v < 0 ? '−' : '+') + '₹';
    else if (decimals) el.dataset.prefix = v < 0 ? '−' : '';
    el.classList.toggle('green', v >= 0 && el.dataset.indian === 'true');
    el.classList.toggle('red', v < 0 && el.dataset.indian === 'true');
  });

  counter('test_n', C.test_n);
  counter('test_net', C.test_net_rs);
  set('test_bps', (C.test_avg_bps >= 0 ? '+' : '') + sg(C.test_avg_bps, 1) + ' bps per trade (₹10L/leg)');
  counter('test_t', C.test_t == null ? 0 : C.test_t, 2);
  set('test_t_desc', C.test_t != null && Math.abs(C.test_t) >= 2 ? 'Beyond ±2, but not a clean test' : 'Between −2 and +2: could be luck');
  counter('clean_net', L.net);
  set('clean_desc', L.n + ' trades, settings never chosen on it, t = ' + sg(L.t, 2));
  set('orig_train', O.train_n + ' tr: ' + rs(O.train_net_rs));
  set('orig_test', O.test_n + ' tr: ' + rs(O.test_net_rs));
  set('orig_t', O.test_t == null ? '—' : sg(O.test_t, 2));
  set('cur_train', C.train_n + ' tr: ' + rs(C.train_net_rs));
  set('cur_test', C.test_n + ' tr: ' + rs(C.test_net_rs));
  set('cur_t', C.test_t == null ? '—' : sg(C.test_t, 2));
  set('sw_test', C.switched_on_n + ' tr: ' + rs(C.switched_on_net_rs));
  set('clean_row', L.n + ' tr: ' + rs(L.net));
  set('clean_t', sg(L.t, 2));
  set('switch_on', on.length ? 'Only ' + on.map(label).join(', ') + ' qualified.' : 'No pair qualified.');
  set('verdict', 'Honest verdict: the test year ' + (C.test_net_rs >= 0 ? 'made ' : 'lost ') + rs(C.test_net_rs).slice(1) +
    ' but is not a clean test (rule revised after a first look); the ' + L.start.slice(0, 4) + '–' + L.end.slice(0, 4) +
    ' historical holdout ' + (L.net < 0 ? 'loses ' : 'makes ') + rs(L.net).slice(1) + '. No persistent edge is proven after costs.');

  // slides whose charts were hand-drawn from an earlier build: say so, and give the current figures
  const sumTest = (k) => PAIRS.reduce((a, p) => a + D.backtest[p]['5'].test[k], 0);
  const perPair = PAIRS.map((p) => ({ p, n: D.backtest[p]['5'].test.n_trades, net: D.backtest[p]['5'].test.net_rs }))
    .sort((a, b) => b.net - a.net);
  const note = (slide, html) => {
    const inner = document.querySelector('#slide-' + slide + ' .slide-inner');
    if (!inner) return;
    const box = document.createElement('div');
    box.className = 'grv-current-note';
    box.setAttribute('role', 'note');
    box.style.cssText = 'border:1px solid var(--line-gold,#5a4520);background:rgba(242,169,59,.08);border-radius:8px;padding:7px 14px;font-size:12px;line-height:1.5;margin:4px 0 8px';
    box.innerHTML = html;
    const h = inner.querySelector('.keynote-h1');
    if (h && h.nextSibling) inner.insertBefore(box, h.nextSibling); else inner.prepend(box);
  };
  const old = '<b>The chart below was drawn from an earlier data build</b> (before the Oct-2026 contract-lifecycle and liquidity correction). Current figures: ';
  note(10, old + perPair.map((x) => label(x.p) + ' ' + rs(x.net) + ' (' + x.n + ' trades)').join(' · ') + '. Test year, 5 bps slippage.');
  note(11, old + 'test year ' + rs(C.test_net_rs) + ' over ' + C.test_n + ' trades: ' + C.crash_n + ' trades closed in the ' + D.events.crashShort +
    ' made ' + rs(C.crash_net_rs) + ', the other ' + C.ex_crash_n + ' made ' + rs(C.ex_crash_net_rs) + '. Spread part ' + rs(sumTest('spread_rs')) +
    ', gold part ' + rs(sumTest('gold_rs')) + ', costs ' + rs(-sumTest('cost_rs')) + '.');
  note(12, old + ['0', '2', '5', '10'].map((s) => s + ' bps: test year ' + rs(D.rule.current[s].test_net_rs) + ', training ' + rs(D.rule.current[s].train_net_rs)).join(' · ') + '.');

  // what Goldie says and the presenter notes, from the same numbers
  const P = window.GRV_PITCH;
  if (P) {
    const ty = 'the test year';
    P.spokenLines[8] = 'Step five: one honest split. We choose the settings on twenty-four months, lock them, and run them on the next twelve months and on ' + L.years + ' earlier years that were never used to choose them. Signals at today\'s close only execute tomorrow, and every position is closed before either contract\'s tender period.';
    P.spokenLines[9] = 'The test year ' + (C.test_net_rs >= 0 ? 'made ' : 'lost ') + words(C.test_net_rs) + ' over ' + C.test_n + ' trades, and it is not a clean test. On ' + L.start.slice(0, 4) + ' to ' + L.end.slice(0, 4) + ', the historical holdout, the rule ' + (L.net < 0 ? 'lost ' : 'made ') + words(L.net) + ' over ' + L.n + ' trades. So no, it is not a proven edge.';
    P.spokenLines[10] = 'By pair, results are small and mixed: ' + perPair.filter((x) => x.n).slice(0, 3).map((x) => label(x.p).replace(' · ', ' versus ') + ' ' + (x.net >= 0 ? 'made ' : 'lost ') + words(x.net)).join(', ') + '. With a handful of trades each, none of this is significant.';
    P.spokenLines[11] = 'Where did ' + ty + '\'s result come from? ' + C.crash_n + ' trades closed during the crash and made ' + words(C.crash_net_rs) + '; the other ' + C.ex_crash_n + ' ' + (C.ex_crash_net_rs >= 0 ? 'made ' : 'lost ') + words(C.ex_crash_net_rs) + '.';
    const pl = (v) => (v >= 0 ? 'a profit of ' : 'a loss of ') + words(v);
    P.spokenLines[12] = 'Slippage decides it, and daily data cannot measure it. At zero slippage the test year shows ' + pl(D.rule.current['0'].test_net_rs) + '; at ten basis points, ' + pl(D.rule.current['10'].test_net_rs) + '. On the historical holdout the rule ' + (L.net0 < 0 ? 'loses money even with zero slippage.' : 'makes money only before slippage.');
    P.spokenLines[14] = 'Zero runtime servers. A Python pipeline rebuilds every number from ' + L.allRows.toLocaleString('en-IN') + ' daily MCX prices, checked by automated tests, into static JSON. Nothing can crash during the demo.';
    P.speakerNotes[8] = 'One train/test split plus a historical holdout, not a rolling walk-forward: settings chosen once on training (' + D.split.train_start + ' to ' + D.split.train_end + ') by net after costs, frozen for the test year (' + D.split.test_start + ' to ' + D.split.test_end + ') and for ' + L.start.slice(0, 4) + '–' + L.end.slice(0, 4) + '. No separate validation period. Safeguards: t+1 fills, point-in-time statistics, size-aware liquidity on signal and fill days, and every position closed before either leg\'s tender window. Caveats: the five-check rule was written after the test year was first seen, and the Oct-2026 lifecycle correction came after every period\'s earlier results were known.';
    P.speakerNotes[9] = 'Test year: ' + C.test_n + ' trades, ' + rs(C.test_net_rs) + ' (' + sg(C.test_avg_bps, 1) + ' bps a trade), t = ' + (C.test_t == null ? 'n/a' : sg(C.test_t, 2)) + '. Training: ' + C.train_n + ' trades, ' + rs(C.train_net_rs) + '. Historical holdout ' + L.start.slice(0, 4) + '–' + L.end.slice(0, 4) + ': ' + L.n + ' trades, ' + rs(L.net) + ' (t = ' + sg(L.t, 2) + '), ' + rs(L.net0) + ' even at zero slippage. No persistent edge is proven after costs.';
    P.speakerNotes[10] = 'Per pair, test year at 5 bps: ' + perPair.map((x) => label(x.p) + ' ' + rs(x.net) + ' (' + x.n + ')').join('; ') + '. The bars on this slide are from an earlier build; these are the current figures.';
    P.speakerNotes[11] = 'Crash split, test year: ' + C.crash_n + ' trades closed in the ' + D.events.crashShort + ' made ' + rs(C.crash_net_rs) + '; the other ' + C.ex_crash_n + ' made ' + rs(C.ex_crash_net_rs) + '. Spread ' + rs(sumTest('spread_rs')) + ', gold ' + rs(sumTest('gold_rs')) + ', costs ' + rs(-sumTest('cost_rs')) + '. The crash window was named after the results were seen, so this is a check, not a test.';
    P.speakerNotes[12] = 'Slippage per order vs results: ' + ['0', '2', '5', '10'].map((s) => s + ' bps: test ' + rs(D.rule.current[s].test_net_rs) + ', training ' + rs(D.rule.current[s].train_net_rs)).join('; ') + '. The bars on this slide are from an earlier build.';
    P.speakerNotes[14] = 'Static architecture: a Python pipeline rebuilds every number from ' + L.allRows.toLocaleString('en-IN') + ' MCX daily prices (' + L.allContracts + ' contracts, ' + L.start + ' to ' + D.asOf + '); CI checks the committed data equals a fresh build.';
  }
}
