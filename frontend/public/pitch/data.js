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

  set('rows_clean', L.allRows.toLocaleString('en-IN') + ' daily prices');
  set('rows_step', '• 1. Collect & validate ' + L.allRows.toLocaleString('en-IN') + ' rows');
  set('data_line', L.allRows.toLocaleString('en-IN') + ' daily prices · ' + L.allContracts + ' contracts · ' + L.allDays.toLocaleString('en-IN') + ' trading days, ' +
    L.start + ' to ' + D.asOf + ' · raw MCX rows vs cleaned data: ' + D.meta.mismatches + ' mismatches on every build');
  set('test_line', C.test_n + ' trades · ' + rs(C.test_net_rs) + ' · ' + Math.round(C.test_hit * C.test_n) + ' of ' + C.test_n + ' trades won (' + Math.round(C.test_hit * 100) + '%)');
  const setHtml = (key, html) => document.querySelectorAll('[data-pitch="' + key + '"]').forEach((el) => { el.innerHTML = html; });
  setHtml('risk_line', '<strong>Small samples:</strong> the test year has ' + C.test_n + ' trades (' + rs(C.test_net_rs) + ', t = ' + (C.test_t == null ? 'n/a' : sg(C.test_t, 2)) +
    '); ' + C.crash_n + ' of them closed in the ' + D.events.crashShort + ' (' + rs(C.crash_net_rs) + '). The ' + L.start.slice(0, 4) + '–' + L.end.slice(0, 4) +
    ' holdout ' + (L.net < 0 ? 'lost ' : 'made ') + rs(L.net).slice(1) + ' over ' + L.n + ' trades. No persistent edge is proven after costs.');

  // slides 10-12: their charts are redrawn here from the data (they were hand-drawn from an earlier build)
  const sumTest = (k) => PAIRS.reduce((a, p) => a + D.backtest[p]['5'].test[k], 0);
  const perPair = PAIRS.map((p) => ({ p, n: D.backtest[p]['5'].test.n_trades, net: D.backtest[p]['5'].test.net_rs }))
    .sort((a, b) => b.net - a.net);
  const GREEN = '#4FD1A1', RED = '#FF8F85', MUTED = '#93A3B4', MONO = "font-family=\"'Geist Mono', monospace\"";
  const svgIn = (slide, i) => document.querySelectorAll('#slide-' + slide + ' .chart-svg-wrap svg')[i || 0];
  const short = (p) => label(p).replace(/GOLD(?=GUINEA|TEN|PETAL)/g, '').replace(/^GOLDM/, 'M');
  const li = (slide, items) => { const ul = document.querySelector('#slide-' + slide + ' .how-to-read-list'); if (ul) ul.innerHTML = items.map((t) => '<li>' + t + '</li>').join(''); };
  const head = (slide, sel, text) => { const el = document.querySelector('#slide-' + slide + ' ' + sel); if (el) el.textContent = text; };

  // slide 10: net result per pair, test year, 5 bps (bars left of the axis are losses)
  { const svg = svgIn(10);
    if (svg) {
      const mx = Math.max(1, ...perPair.map((x) => Math.abs(x.net))), zero = 380, half = 200;
      let h = '<line x1="' + zero + '" y1="6" x2="' + zero + '" y2="139" stroke="rgba(255,255,255,0.25)"/>';
      perPair.forEach((x, i) => {
        const y = 10 + i * 21, w = Math.max(2, Math.abs(x.net) / mx * half), col = x.n ? (x.net >= 0 ? GREEN : RED) : MUTED;
        const bx = x.net >= 0 ? zero : zero - w;
        h += '<text x="150" y="' + (y + 11) + '" text-anchor="end" fill="#EAF0F6" font-size="10.5" font-weight="700">' + short(x.p) + '</text>';
        h += '<rect class="svg-bar" x="' + bx.toFixed(1) + '" y="' + y + '" width="' + w.toFixed(1) + '" height="14" rx="3" fill="' + col + '"/>';
        const tx = x.net >= 0 ? zero + w + 8 : zero + 8, anchor = 'start';
        h += '<text x="' + tx.toFixed(1) + '" y="' + (y + 11) + '" text-anchor="' + anchor + '" fill="' + col + '" font-size="10.5" font-weight="700" ' + MONO + '>' +
          (x.n ? rs(x.net) : '₹0') + ' <tspan fill="#93A3B4" font-weight="400">(' + x.n + ' trade' + (x.n === 1 ? '' : 's') + ')</tspan></text>';
      });
      svg.innerHTML = h;
    }
    const pos = perPair.filter((x) => x.n && x.net > 0).length, traded = perPair.filter((x) => x.n).length;
    head(10, '.chart-card-cinematic .mono', pos + ' of ' + traded + ' traded pairs made money');
    head(10, '.chart-card-cinematic span', 'Net result per pair (₹10 lakh per leg, after all costs)');
    li(10, ['Each pair has only ' + Math.min(...perPair.map((x) => x.n)) + '–' + Math.max(...perPair.map((x) => x.n)) + ' trades, too few to prove anything on its own.',
      'Bars to the right made money, bars to the left lost money, on ₹10 lakh per leg after all costs.']);
  }

  // slide 11: the crash split (3D columns read window.GRV_CRASH) and a waterfall from spread and gold to net
  window.GRV_CRASH = { crash: C.crash_net_rs, other: C.ex_crash_net_rs };
  { const items = document.querySelectorAll('#slide-11 .crash-legend-item');
    if (items[0]) items[0].innerHTML = '<span class="mono" style="color: ' + (C.crash_net_rs >= 0 ? 'var(--green)' : 'var(--red)') + '; font-size: 13.5px; font-weight: 800;">' + rs(C.crash_net_rs) +
      '</span><span style="font-size: 10.5px; color: var(--text-muted);">' + C.crash_n + ' trades closed in the ' + D.events.crashShort + '</span>';
    if (items[1]) items[1].innerHTML = '<span class="mono" style="color: ' + (C.ex_crash_net_rs >= 0 ? 'var(--green)' : 'var(--red)') + '; font-size: 13.5px; font-weight: 800;">' + rs(C.ex_crash_net_rs) +
      '</span><span style="font-size: 10.5px; color: var(--text-muted);">' + C.ex_crash_n + ' other trades</span>';
    const crashCarries = C.test_net_rs > 0 && C.ex_crash_net_rs < 0;
    head(11, '.keynote-h1', C.test_net_rs >= 0 ? 'Where Did The Profit Come From?' : 'Where Did The Result Come From?');
    head(11, '.crash-card-header strong', crashCarries ? '"One Crash Carries The Profit"' : '"Crash Trades vs The Rest"');
    head(11, '.crash-card-header span', 'Columns to scale');
    const sp = sumTest('spread_rs'), gd = sumTest('gold_rs'), co = sumTest('cost_rs'), gr = sp + gd, nt = gr - co;
    const svg = svgIn(11);
    if (svg) {
      const steps = [['Spread', sp], ['Gold', gd], ['Gross', gr], ['Costs', -co], ['Net', nt]];
      let cum = 0; const lv = [0];
      steps.forEach(([name, v]) => { if (name === 'Gross' || name === 'Net') lv.push(v); else { cum += v; lv.push(cum); } });
      const hi = Math.max(0, ...lv), lo = Math.min(0, ...lv), sc = 88 / Math.max(1, hi - lo), base = 22 + hi * sc;
      let h = '<line x1="20" y1="' + base.toFixed(1) + '" x2="410" y2="' + base.toFixed(1) + '" stroke="rgba(255,255,255,0.2)"/>', run = 0;
      steps.forEach(([name, v], i) => {
        const x = 40 + i * 74, total = name === 'Gross' || name === 'Net';
        const from = total ? 0 : run, to = total ? v : run + v;
        if (!total) run += v;
        const y0 = base - Math.max(from, to) * sc, hgt = Math.max(2, Math.abs(to - from) * sc);
        const col = name === 'Net' ? (v >= 0 ? '#F2A93B' : RED) : name === 'Gross' ? '#F2A93B' : (v >= 0 ? GREEN : RED);
        h += '<rect class="svg-bar" x="' + x + '" y="' + y0.toFixed(1) + '" width="40" height="' + hgt.toFixed(1) + '" rx="3" fill="' + col + '"/>';
        const ly = v >= 0 ? y0 - 5 : y0 + hgt + 11;
        h += '<text x="' + (x + 20) + '" y="' + ly.toFixed(1) + '" text-anchor="middle" fill="' + col + '" font-size="9" font-weight="700" ' + MONO + '>' + rs(v) + '</text>';
        h += '<text x="' + (x + 20) + '" y="152" text-anchor="middle" fill="' + (name === 'Net' ? '#F2A93B' : '#93A3B4') + '" font-size="9.5"' + (name === 'Net' ? ' font-weight="700"' : '') + '>' + name + '</text>';
      });
      svg.innerHTML = h;
    }

    li(11, [crashCarries ? 'Take out the crash and the rule loses money.' : 'The ' + C.crash_n + ' crash trades ' + (C.crash_net_rs < 0 ? 'lost ' : 'made ') + rs(C.crash_net_rs).slice(1) + '; the other ' + C.ex_crash_n + ' ' + (C.ex_crash_net_rs < 0 ? 'lost ' : 'made ') + rs(C.ex_crash_net_rs).slice(1) + '.',
      'Gold price moves added ' + rs(gd) + ' and costs took ' + rs(-co).slice(1) + ': with equal grams on both legs the trade barely depends on gold, so costs decide it.']);
  }

  // slide 12: training vs test year at each slippage level
  { const S = ['0', '2', '5', '10'], R = D.rule.current, svg = svgIn(12);
    if (svg) {
      const vals = S.flatMap((s) => [R[s].train_net_rs, R[s].test_net_rs]), hi = Math.max(0, ...vals), lo = Math.min(0, ...vals);
      const sc = 92 / Math.max(1, hi - lo), z = 18 + hi * sc;
      let h = '<line x1="40" y1="' + z + '" x2="660" y2="' + z + '" stroke="rgba(255,255,255,0.25)"/><text x="35" y="' + (z + 3) + '" text-anchor="end" fill="#93A3B4" font-size="9" ' + MONO + '>₹0</text>';
      S.forEach((s, g) => {
        const gx = 75 + g * 145, ours = s === '5';
        [[R[s].train_net_rs, '#93A3B4', 0], [R[s].test_net_rs, '#F2A93B', 46]].forEach(([v, c, dx]) => {
          const hh = Math.max(2, Math.abs(v) * sc), y = v >= 0 ? z - hh : z, col = v >= 0 ? (c === '#93A3B4' ? GREEN : c) : RED;
          h += '<rect class="svg-bar" x="' + (gx + dx) + '" y="' + y.toFixed(1) + '" width="26" height="' + hh.toFixed(1) + '" rx="2" fill="' + (v >= 0 ? c : RED) + '"/>';
          h += '<text x="' + (gx + dx + 13) + '" y="' + (v >= 0 ? y - 5 : y + hh + 11).toFixed(1) + '" text-anchor="middle" fill="' + col + '" font-size="8.5" ' + MONO + '>' + rs(v) + '</text>';
        });
        h += '<text x="' + (gx + 36) + '" y="147" text-anchor="middle" fill="' + (ours ? '#F2A93B' : '#EAF0F6') + '" font-size="10" font-weight="' + (ours ? 800 : 700) + '">' + s + ' bps' + (ours ? ' (ours)' : '') + '</text>';
      });
      svg.innerHTML = h;
    }
    document.querySelectorAll('#slide-12 .chart-card-cinematic span').forEach((el) => {
      const t = el.lastChild;
      if (!t || t.nodeType !== 3) return;
      if (/^Training \(/.test(t.textContent)) t.textContent = 'Training (' + C.train_n + ' trades)';
      else if (/^Test year \(/.test(t.textContent)) t.textContent = 'Test year (' + C.test_n + ' trades)';
    });
    const be = D.evidence && D.evidence.slippage && D.evidence.slippage.breakeven;
    const kt = document.querySelector('#slide-12 .slide-inner > div[style*="text-align: center"]');
    if (kt && be) kt.innerHTML = '<strong style="color: var(--gold);">Key threshold:</strong> training breaks even at about <strong>' + be.train.breakeven_bps + ' bps</strong>, the 2011–2023 holdout at <strong>' +
      be.history.breakeven_bps + ' bps</strong>; the test year ' + (be.test.loses_even_at_0 ? 'loses even at 0' : 'breaks even at ' + be.test.breakeven_bps + ' bps') + '. We assume <strong>5</strong>.';
    li(12, ['Grey bars are training, gold bars the test year; red bars below zero are losses.', 'Small changes in slippage move the result a lot, so slippage is the number to measure next.']);
  }

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
    P.speakerNotes[10] = 'Per pair, test year at 5 bps: ' + perPair.map((x) => label(x.p) + ' ' + rs(x.net) + ' (' + x.n + ')').join('; ') + '.';
    P.speakerNotes[11] = 'Crash split, test year: ' + C.crash_n + ' trades closed in the ' + D.events.crashShort + ' made ' + rs(C.crash_net_rs) + '; the other ' + C.ex_crash_n + ' made ' + rs(C.ex_crash_net_rs) + '. Spread ' + rs(sumTest('spread_rs')) + ', gold ' + rs(sumTest('gold_rs')) + ', costs ' + rs(-sumTest('cost_rs')) + '. The crash window was named after the results were seen, so this is a check, not a test.';
    P.speakerNotes[12] = 'Slippage per order vs results: ' + ['0', '2', '5', '10'].map((s) => s + ' bps: test ' + rs(D.rule.current[s].test_net_rs) + ', training ' + rs(D.rule.current[s].train_net_rs)).join('; ') + '.';
    P.speakerNotes[4] = 'Slide 4 shows the GOLDM-GOLDPETAL gap over time around its rolling normal level, with a 2-sigma band. In the test year ' + C.crash_n + ' trades closed during the ' + D.events.crashShort + ' (' + rs(C.crash_net_rs) + ') and ' + C.ex_crash_n + ' outside it (' + rs(C.ex_crash_net_rs) + ').';
    P.speakerNotes[14] = 'Static architecture: a Python pipeline rebuilds every number from ' + L.allRows.toLocaleString('en-IN') + ' MCX daily prices (' + L.allContracts + ' contracts, ' + L.start + ' to ' + D.asOf + '); CI checks the committed data equals a fresh build.';
  }
}
