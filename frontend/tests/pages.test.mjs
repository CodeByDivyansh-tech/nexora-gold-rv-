// Runs every page's logic against the real site-data.json in many UI states.
// No dependencies: `node tests/pages.test.mjs` (or `npm test`) from frontend/.
import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'

globalThis.window = globalThis; new Function(readFileSync('public/app/theme.js', 'utf8'))()   // shared themes, as in the browser
const D = JSON.parse(readFileSync('public/data/site-data.json', 'utf8'))
const R = JSON.parse(readFileSync('public/data/robustness.json', 'utf8'))
const H = JSON.parse(readFileSync('public/data/history.json', 'utf8'))
const HC = JSON.parse(readFileSync('public/data/history_charts.json', 'utf8'))
const E = JSON.parse(readFileSync('public/data/explore.json', 'utf8'))
const CV0 = JSON.parse(readFileSync('public/data/curve.json', 'utf8'))
const PF0 = JSON.parse(readFileSync('public/data/portfolio.json', 'utf8'))
const PV0 = JSON.parse(readFileSync('public/data/provenance.json', 'utf8'))
const PAIRS = ['M_TEN', 'M_PETAL', 'M_GUINEA', 'TEN_PETAL', 'GUINEA_TEN', 'GUINEA_PETAL']
const SLIPS = ['0', '2', '5', '10']

class DCLogic { setState(o) { this.state = { ...(this.state || {}), ...(typeof o === 'function' ? o(this.state) : o) } } }

function load(name) {
  const src = readFileSync(`public/pages/${name}.dc.html`, 'utf8')
  const code = src.match(/<script type="text\/x-dc" data-dc-script[^>]*>([\s\S]*?)<\/script>/)[1]
  assert.ok(!/_blob\//.test(src), `${name}: still points at a design-canvas data file`)
  return new Function('DCLogic', code + '\nreturn Component;')(DCLogic)
}

const states = {
  Home: [{}, { range: '1M', hover: 5 }, { range: '3Y', hover: 100 }, { dark: false }, { H, range: '10Y', hover: 200 }, { H, range: 'All', hover: 900 }, { range: 'All' }],
  Today: [{}, { ri: 0 }, { ri: 60 }, { ri: 120, speed: 2 }, { HC }, { HC, ri: 0 }, { HC, ri: 400 }, { HC, rspan: 'ours', ri: 10 }],
  Market: [{}, { range: '3M', hover: 10 }, { range: '3Y', hover: 150 }, { H, range: '10Y', hover: 100 }, { H, range: 'All', hover: 1000 }, { range: '10Y' }, { HC }, { HC, vspan: 'ours' }, { CV: CV0 }, { CV: CV0, tsCmp: '2024-03-28', tsOff: ['GOLDM', 'GOLDTEN'] }, { CVfail: true }],
  Pairs: PAIRS.flatMap((pair) => [{ pair }, { pair, hover: 20, allTrades: true }, { pair, HC, allTrades: true }, { pair, HC, span: 'ours' }, { pair, HC, story: D.pairs[pair].trades.length ? D.pairs[pair].trades[0].sig + '|' + D.pairs[pair].trades[0].e : null }]),
  Signals: PAIRS.map((pair) => ({ pair, allPast: true })).concat([{ R }, { R, cs: '0', cb: '0', cz: '1' }, { R, cs: '', cb: 'abc', cz: '0' }, { cs: '10', cb: '50', cz: '25' }]),
  Backtesting: PAIRS.flatMap((pair) => SLIPS.map((slip) => ({ pair, slip, hover: 0 }))).concat([{ R }, { R, H }, { H, pair: 'GUINEA_TEN', slip: '10' }]).concat(PAIRS.flatMap((pair) => SLIPS.map((slip) => ({ pair, slip, HC })))).concat([{ HC, espan: 'ours' }, { HC, PF: PF0 }, { PFfail: true }]),
  Data: [{}, { all: true }, { H }, { H, all: true }, { H, PV: PV0 }],
  Brief: [{}, { HC }, { HCfail: true }, { dark: false, HC }],
  Explore: [{ E }, { E, xpair: 'M_TEN' }, { E, xpair: 'GUINEA_PETAL', slip: '0' }, { E, pub: '0', ze: '3.0', W: '10', mh: '20', h: '0' },
    { E, xpair: 'ALL', pub: '0', ze: '1.5' }, ...PAIRS.flatMap((xpair) => ['0', '10'].map((slip) => ({ E, xpair, slip, pub: '0' })))],
  DownloadPanel: ['today', 'prices', 'trades', 'backtest', 'report'].flatMap((what) =>
    ['3m', '3y', 'all', 'test', 'custom'].map((period) => ({ what, period, pair: 'ALL', H, HC }))),
}

let runs = 0
for (const [name, list] of Object.entries(states)) {
  const C = load(name)
  for (const st of list) {
    const c = new C()
    c.props = name === 'DownloadPanel' ? { dark: true, onClose: () => {} } : {}
    c.state = { D, ...st }
    const v = c.renderVals()
    assert.ok(v && v.ready !== false, `${name} ${JSON.stringify(st)} did not reach the ready state`)
    const text = JSON.stringify(v, (k, x) => (typeof x === 'function' ? undefined : x))
    assert.ok(!/\bNaN\b|undefined|\[object Object\]/.test(text), `${name} ${JSON.stringify(st)} shows NaN/undefined`)
    runs++
  }
  // loading and failed states draw too
  const c = new C(); c.props = {}; c.state = {}
  assert.ok(c.renderVals(), `${name} loading state`)
}

// The headline answer follows all five checks, not just the cost line
{
  const C = load('Home'); const c = new C(); c.props = {}; c.state = { D }
  const signals = D.today.filter((p) => p.status === 'SIGNAL').length
  assert.equal(c.renderVals().answer.word === 'No.', signals === 0)
}
// The cost calculator reproduces the site's own round trip at our defaults
{
  const C = load('Signals'); const c = new C(); c.props = {}; c.state = { D, R }
  const v = c.renderVals()
  assert.equal(v.calc.rt, D.costTotal.toFixed(2))
  assert.equal(v.calc.count, D.today.filter((p) => p.dev >= 2 * D.rt).length + ' of ' + D.today.length)
  assert.ok(v.ft.show && v.ft.rows.length === 5 && /clean test/.test(v.ft.rows[0].name), 'follow-through starts with the clean test')
}
// Shared menus: exactly one item is marked as the current page, on every page
for (const name of ['Rail', 'TabBar']) {
  const C = load(name)
  for (const cur of ['Home', 'Today', 'Market', 'Pairs', 'Signals', 'Backtesting', 'Explore', 'Data', 'Brief']) {
    const c = new C(); c.props = { current: cur }; c.state = {}
    const v = c.renderVals()
    assert.deepEqual(Object.keys(v.nav).filter((k) => v.nav[k].cur === 'page'), [cur], `${name} highlights ${cur}`)
    runs++
  }
}
// Every page uses the shared menus instead of its own copy
for (const name of ['Home', 'Today', 'Market', 'Pairs', 'Signals', 'Backtesting', 'Explore', 'Data', 'Brief']) {
  const src = readFileSync(`public/pages/${name}.dc.html`, 'utf8')
  assert.ok(src.includes(`<dc-import name="Rail" current="${name}">`) && src.includes(`<dc-import name="TabBar" current="${name}">`), `${name} uses the shared menus`)
  assert.ok(!src.includes('<aside class="rail"') && !src.includes('<nav class="tabbar"'), `${name} still has its own menu copy`)
}
console.log(`pages ok: ${runs} page states rendered against site-data.json`)

// The long-history section shows the history file's own numbers, and the Data page credits the source
{
  const C = load('Backtesting'); const c = new C(); c.props = {}; c.state = { D, H }
  const v = c.renderVals(), s5 = H.result.by_slip['5']
  assert.equal(v.hist.show, true)
  assert.equal(v.hist.kpis[0].value, String(s5.n))
  assert.equal(v.hist.years.length, H.result.years.length)
  assert.equal(v.hist.pairs.length, 3)
  const D2 = new (load('Data'))(); D2.props = {}; D2.state = { D, H }
  const w = D2.renderVals()
  assert.equal(w.hx.show, true)
  assert.equal(w.hx.facts[2].value, String(H.check.mismatches))
  assert.match(w.hx.intro, /we downloaded from MCX's Bhavcopy service, one contract at a time/)
  assert.equal(w.hx.facts[1].value, String(H.source.contracts))
}

// Long charts: All starts at the first week of the shared book, 10Y about ten years back, and both end on our last day
{
  const first = (s) => { const [y, m, d] = s.split('-'); return +d + ' ' + ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+m - 1] + ' ' + y }
  const Hm = new (load('Home'))(); Hm.props = {}; Hm.state = { D, H, range: 'All' }
  const a = Hm.renderVals().chart
  assert.equal(a.start, first(H.long.d[0])); assert.equal(a.end, first(D.asOf)); assert.equal(a.hasNote, true)
  const Mk = new (load('Market'))(); Mk.props = {}; Mk.state = { D, H, range: '10Y' }
  const f = Mk.renderVals().four
  assert.ok(+f.start.slice(-4) === +D.asOf.slice(0, 4) - 10, '10Y starts ten years back: ' + f.start)
  assert.equal(f.end, first(D.asOf))
  const M0 = new (load('Market'))(); M0.props = {}; M0.state = { D, range: 'All' }
  assert.equal(M0.renderVals().ranges.length, 3)   // without the history file the long ranges are hidden
}

// Full-history views: every chart that has a 2011-2023 part starts on the book's first day and ends on our last day,
// and the clean-test part adds up to the published clean-test result
{
  const L = D.longrun
  let total = 0
  for (const pair of ['M_PETAL', 'M_GUINEA', 'GUINEA_PETAL']) {
    const p = new (load('Pairs'))(); p.props = {}; p.state = { D, HC, pair }
    const ch = p.renderVals().chart
    assert.equal(ch.dates[0], HC.pairs[pair].d[0]); assert.equal(ch.dates[ch.dates.length - 1], D.asOf)
    assert.equal(ch.markers.length, HC.pairs[pair].trades['5'].length + D.pairs[pair].trades.length)
    const b = new (load('Backtesting'))(); b.props = {}; b.state = { D, HC, pair, slip: '5' }
    const eq = b.renderVals().eq
    assert.equal(eq.dates[0], HC.from)
    const clean = HC.pairs[pair].trades['5'].reduce((a, t) => a + t[5], 0)
    const ours = D.backtest[pair]['5'].curve.reduce((a, c) => a + c[2], 0)
    assert.ok(Math.abs(eq.series[0].values[eq.series[0].values.length - 1] - (clean + ours)) < 2, pair + ' running total carries on from the clean test')
    total += clean
  }
  assert.ok(Math.abs(total - L.net) < 80, 'clean-test trades add up to the published result: ' + total + ' vs ' + L.net)
  const g = new (load('Pairs'))(); g.props = {}; g.state = { D, HC, pair: 'M_TEN' }
  const gv = g.renderVals().chart
  assert.equal(gv.hasSpans, false); assert.match(gv.spanNote, /first trading day/)
  const m = new (load('Market'))(); m.props = {}; m.state = { D, HC }
  const vs = m.renderVals().vsm
  assert.ok(vs.dates[0] <= '2011-04-19' && vs.dates[vs.dates.length - 1] === D.asOf)
  assert.ok(vs.series[0].values.slice(0, 100).every((v) => v == null), 'GOLDTEN has no line before it was listed')
  const t = new (load('Today'))(); t.props = {}; t.state = { D, HC }
  const r = t.renderVals().replay
  assert.equal(r.max, HC.replay.d.length + D.replay.d.length - 1)
  assert.match(r.title, /Replay 15 years/)
}
console.log('full-history charts ok')

// Try your own rule: the published setting for all pairs adds up to the published results, period by period
{
  const x = new (load('Explore'))(); x.props = {}; x.state = { D, E }
  const v = x.renderVals()
  const cur = D.rule.current['5'], L = D.longrun
  const want = L.net + Object.keys(D.backtest).reduce((a, p) => a + D.backtest[p]['5'].train.net_rs + D.backtest[p]['5'].test.net_rs + D.backtest[p]['5'].fwd.net_rs, 0)
  const got = +v.res.total.replace(/[^0-9]/g, '') * (v.res.total.startsWith('−') ? -1 : 1)
  assert.ok(Math.abs(got - want) <= 12, 'published total ' + got + ' vs ' + want)
  assert.equal(v.modeLabel, 'Published rule')
  assert.match(v.periods[0].detail, new RegExp('^' + L.n + ' trades'))
  assert.equal(v.years.n, E.years.length)
  const c = new (load('Explore'))(); c.props = {}; c.state = { D, E, pub: '0', ze: '3.0' }
  const w = c.renderVals()
  assert.equal(w.modeLabel, 'Your settings'); assert.match(w.res.compare, /published rule/)
  const g = new (load('Explore'))(); g.props = {}; g.state = { D, E, xpair: 'M_TEN' }
  assert.equal(g.renderVals().periods[0].net, 'GOLDTEN not listed yet')
}
console.log('explorer ok')

// ---------------------------------------------------------------------------------------------
// Guard: a part of the study must never stand in for the whole (Oct-2026 review, twice reported).
// The study runs 2011 to today. The 12-month test year and our own 3-year MCX download are parts of it:
// they may be shown, but always named as parts, never as the headline result or the dataset size.
{
  const PAGES = ['Home', 'Today', 'Market', 'Pairs', 'Signals', 'Backtesting', 'Explore', 'Data', 'Brief', 'DownloadPanel']
  // 1) phrases that presented a part as the whole, in the page files themselves
  const BANNED = [/On the 12-month test year/, /Trades in the test year/, /Results on the test year/, /Training period, for comparison/,
    /tested it on the next twelve months/, /'daily settlements checked'/, /'Everything'\]/, /Backtest on the test year/]
  for (const name of PAGES) {
    const src = readFileSync(`public/pages/${name}.dc.html`, 'utf8')
    for (const re of BANNED) assert.ok(!re.test(src), `${name}: still says ${re}`)
  }
  // 2) rendered text: our download's row count may appear only where it is named as our download / the raw MCX file
  const ours = D.meta.rows.toLocaleString('en-IN'), L = D.longrun
  const S = { D, H, HC, R, E }
  for (const name of PAGES) {
    const c = new (load(name))(); c.props = name === 'DownloadPanel' ? { dark: true, onClose: () => {} } : {}; c.state = { ...S }
    const strs = []
    JSON.stringify(c.renderVals(), (k, x) => { if (typeof x === 'string') strs.push(x); return typeof x === 'function' ? undefined : x })
    for (const t of strs) {
      if (t === ours || t.includes(ours + ' daily') || t.includes(ours + ' rows')) {
        assert.ok(/download|MCX file|raw MCX|our own|Oct 2023/i.test(t), `${name}: shows ${ours} (our download only) without saying so: "${t.slice(0, 120)}"`)
      }
      assert.ok(!/^\d+ trades in the test year$/.test(t), `${name}: test-year trade count used as a headline: "${t}"`)
    }
  }
  // 3) the headline numbers themselves cover every year
  const dv = new (load('Data'))(); dv.props = {}; dv.state = { D, H }
  const dvals = dv.renderVals()
  assert.equal(dvals.big[0].value, L.allRows.toLocaleString('en-IN'), 'Data page leads with every daily price since 2011')
  assert.equal(dvals.big[2].value, L.allDays.toLocaleString('en-IN'))
  assert.match(dvals.big[0].note, new RegExp(L.rows.toLocaleString('en-IN') + '.*' + ours))
  for (const pair of ['M_PETAL', 'M_GUINEA', 'GUINEA_PETAL']) {
    const pg = new (load('Pairs'))(); pg.props = {}; pg.state = { D, HC, pair }
    const v = pg.renderVals()
    assert.match(v.sumTitle, /^This pair, Apr 2011 – Oct 2026$/)
    const n = HC.pairs[pair].trades['5'].length + D.pairs[pair].trades.length
    assert.equal(v.testKpis[0].value, String(n), pair + ': headline trade count covers every year')
    assert.equal(v.periods[0].name, 'Clean test')
    const b = new (load('Backtesting'))(); b.props = {}; b.state = { D, HC, pair, slip: '5' }
    const k = b.renderVals().kpis
    assert.equal(k[0].label, 'Trades, 2011–2026'); assert.equal(k[0].value, String(HC.pairs[pair].trades['5'].length + D.backtest[pair]['5'].train.n_trades + D.backtest[pair]['5'].test.n_trades + D.backtest[pair]['5'].fwd.n_trades))
  }
  // without the 2011-2023 file the totals wait ("…"); they never fall back to the test year alone
  const pw = new (load('Pairs'))(); pw.props = {}; pw.state = { D, pair: 'M_PETAL' }
  assert.equal(pw.renderVals().testKpis[0].value, '…')
  const bw = new (load('Backtesting'))(); bw.props = {}; bw.state = { D, pair: 'M_PETAL' }
  assert.equal(bw.renderVals().kpis[0].value, '…')
  console.log('partial-period guard ok')
}

// New features: trade story, compare periods, compare pairs, next step, how we know
{
  const pg = new (load('Pairs'))(); pg.props = {}; pg.state = { D, HC, pair: 'M_PETAL' }
  const t0 = HC.pairs.M_PETAL.trades['5'][0]
  pg.state.story = t0[0] + '|' + t0[1]
  const sv = pg.renderVals().story
  assert.equal(sv.on, true); assert.equal(sv.steps.length, 4); assert.ok(sv.dates.length > 10 && sv.markers.length === 2)
  assert.match(sv.sub, /clean test/)
  const ours = D.pairs.M_PETAL.trades[0]; pg.state.story = ours.sig + '|' + ours.e
  assert.equal(pg.renderVals().story.on, true)
  const b = new (load('Backtesting'))(); b.props = {}; b.state = { D, HC, R, cmpA: 'clean', cmpB: 'exc', mpSel: 'M_PETAL,M_TEN' }
  const v = b.renderVals()
  assert.equal(v.cmp.rows[0].a, String(L_N()))
  assert.equal(v.cmp.nameB, 'Test year without the crash')
  assert.equal(v.cmp.rows[0].b, String(D.rule.current['5'].ex_crash_n))
  assert.equal(v.mp.series.length, 2); assert.equal(v.mp.dates[0], HC.from)
  const mpl = v.mp.series[0].values; assert.ok(Math.abs(mpl[mpl.length - 1] - (HC.pairs.M_PETAL.trades['5'].reduce((a, t) => a + t[5], 0) + D.backtest.M_PETAL['5'].curve.reduce((a, c) => a + c[2], 0))) < 3)
  const tv = new (load('Today'))(); tv.props = {}; tv.state = { D, HC }
  const nx = tv.renderVals().next
  assert.match(nx.fresh, /not a live feed/); assert.match(nx.text, /Since Apr 2011/)
  const dv = new (load('Data'))(); dv.props = {}; dv.state = { D, H }
  const hw = dv.renderVals().how
  assert.equal(hw[0].value, D.longrun.allRows.toLocaleString('en-IN')); assert.ok(hw.length >= 5)
  console.log('new features ok')
}
function L_N() { return D.longrun.n }

// Downloads: a custom date range is respected, kept inside the data, and a reversed range downloads nothing
{
  const mk = (st) => { const c = new (load('DownloadPanel'))(); c.props = { dark: true, onClose: () => {} }; c.state = { D, H, HC, ...st }; return c }
  const c = mk({ what: 'prices', period: 'custom', cFrom: '2015-01-01', cTo: '2015-12-31' })
  const v = c.renderVals(), tb = c.table(D, 'prices', 'ALL', 'custom', H, HC, '2015-01-01', '2015-12-31')
  assert.ok(v.custom.on && tb.rows.length > 40 && tb.rows.every((r) => r[0] >= '2015-01-01' && r[0] <= '2015-12-31'))
  assert.match(v.filename, /2015-01-01-to-2015-12-31/)
  const tr = c.table(D, 'trades', 'ALL', 'custom', H, HC, '2026-01-01', '2026-03-31')
  assert.ok(tr.rows.length > 0 && tr.rows.every((r) => r[0] >= '2026-01-01' && r[0] <= '2026-03-31'))
  const r = mk({ what: 'prices', period: 'custom', cFrom: '2020-05-01', cTo: '2019-01-01' }).renderVals()
  assert.match(r.custom.note, /start date is after the end date/)
  assert.match(r.preview.count, /No rows/)
  const cl = mk({ what: 'prices', period: 'custom', cFrom: '2001-01-01', cTo: '2099-01-01' }).renderVals()
  assert.equal(cl.custom.from, D.longrun.start); assert.equal(cl.custom.to, D.asOf); assert.match(cl.custom.note, /Moved inside/)
  const t = mk({ what: 'trades', period: 'test' })
  assert.ok(t.table(D, 'trades', 'ALL', 'test', H, HC).rows.every((x) => x[0] >= D.split.test_start && x[0] <= D.split.test_end), 'test year stops at its end')
  console.log('custom download range ok')
}

// PDF downloads: every choice offers a PDF, and the file is a well-formed PDF with the right contents
{
  new Function(readFileSync('public/app/pdf.js', 'utf8'))()
  const mk = (st) => { const c = new (load('DownloadPanel'))(); c.props = { dark: true, onClose: () => {} }; c.state = { D, H, HC, ...st }; return c }
  const latin = (b) => Array.from(b, (x) => String.fromCharCode(x)).join('')
  for (const what of ['today', 'prices', 'trades', 'backtest', 'report']) {
    const c = mk({ what, period: 'all', pair: 'ALL', format: 'pdf' })
    const v = c.renderVals()
    assert.ok(v.formats.some((f) => f.label === 'PDF'), what + ': PDF offered')
    assert.match(v.filename, /\.pdf$/)
    const tb = c.table(D, what, 'ALL', 'all', H, HC)
    const s = latin(GRVPdf.make(c.doc(D, what, 'ALL', 'Everything since 2011', tb)))
    assert.ok(s.startsWith('%PDF-1.4') && s.trimEnd().endsWith('%%EOF'), what + ': PDF header and end')
    // every object starts exactly where the cross-reference table says
    const xref = +s.match(/startxref\n(\d+)/)[1]
    const offs = s.slice(xref).split('\n').slice(3).filter((l) => / 00000 n $/.test(l)).map((l) => +l.slice(0, 10))
    offs.forEach((o, i) => assert.equal(s.slice(o, o + String(i + 1).length + 6), (i + 1) + ' 0 obj', what + ': object ' + (i + 1) + ' offset'))
    const pages = +s.match(/\/Count (\d+)/)[1]
    assert.ok(pages >= 1 && s.includes('(Page ' + pages + ' of ' + pages + ')'), what + ': page numbers')
    assert.ok(!/\bNaN\b|undefined|\[object Object\]/.test(s), what + ': no broken values in the PDF')
  }
  // the PDF carries the same rows as the spreadsheet
  const c = mk({ what: 'trades', period: 'all', pair: 'ALL' })
  const tb = c.table(D, 'trades', 'ALL', 'all', H, HC)
  const s = latin(GRVPdf.make(c.doc(D, 'trades', 'ALL', 'Everything since 2011', tb)))
  assert.equal((s.match(/\(\d{4}-\d\d-\d\d\) Tj/g) || []).length, 2 * tb.rows.length, 'one PDF row per trade (entry and exit dates)')
  const net = tb.rows.reduce((a, r) => a + r[7], 0)
  assert.ok(s.includes('(' + c.rs(net) + ')'), 'statement total in the PDF')
  // the rupee sign is written "Rs" (standard PDF fonts have no rupee glyph); other text is kept
  assert.equal(GRVPdf.enc('₹10 lakh · 2011–2023'), 'Rs 10 lakh \xB7 2011\x962023')
  // defaults: the report starts as a PDF, other choices as a spreadsheet; the printable page stays for statements
  assert.match(mk({ what: 'report' }).renderVals().filename, /\.pdf$/)
  assert.match(mk({ what: 'prices' }).renderVals().filename, /\.csv$/)
  assert.match(mk({ what: 'trades', format: 'html' }).renderVals().filename, /\.html$/)
  assert.match(mk({ what: 'prices', format: 'html' }).renderVals().filename, /\.csv$/, 'no printable page for prices')
  const html = c.statement(D, 'trades', 'ALL', 'Everything since 2011', tb)
  assert.ok(html.includes('<b>' + c.rs(net) + '</b>') && (html.match(/<tr>/g) || []).length === tb.rows.length + 1, 'printable page unchanged')
  // Ctrl/Cmd+P: keys.js opens the panel with PDF chosen, or downloads when it is open
  const keys = readFileSync('public/app/keys.js', 'utf8')
  assert.ok(/e\.key === 'p' \|\| e\.key === 'P'/.test(keys) && /grv:pdf/.test(keys) && /GRVWantPdf/.test(keys))
  for (const name of ['Home', 'Today', 'Market', 'Pairs', 'Signals', 'Backtesting', 'Explore', 'Data', 'Brief'])
    assert.ok(readFileSync(`public/pages/${name}.dc.html`, 'utf8').includes('data-dl="1" onClick="{{openDl}}"'), name + ': download button reachable by Ctrl+P')
  globalThis.GRVWantPdf = true
  const p = mk({}); p.componentDidMount = p.componentDidMount; globalThis.fetch = () => new Promise(() => {}); globalThis.addEventListener = () => {}
  p.componentDidMount(); assert.equal(p.state.format, 'pdf'); assert.equal(globalThis.GRVWantPdf, false)
  console.log('pdf downloads ok')
}

// Chart downloads are named from the chart title in whole words (Oct-2026 live check: names were cut mid-number)
{
  const C = load('LineChart')
  const name = (label) => { const c = new C(); c.props = { label }; return c.slug() }
  assert.equal(name('Gold per 10 g of pure gold since Nov 2003: from ₹5,925 to ₹1,47,161. Move across it'), 'gold-per-10-g-of-pure-gold-since-nov-2003')
  assert.equal(name('Spread of GOLDGUINEA · GOLDPETAL in basis points from 11 Oct 2023 to 16 Oct 2026'), 'spread-of-goldguinea-goldpetal-in-basis-points')
  for (const l of ['Price of 10 g of pure gold for GOLDM, GOLDTEN, GOLDGUINEA and GOLDPETAL from 18 Apr 2011', 'Running total after costs for GOLDM · GOLDPETAL from 10 Oct 2023', '', 'x'.repeat(200)]) {
    const n = name(l)
    assert.ok(n.length <= 60 && !/-$/.test(n) && !/-(and|of|for|from|to|\d{1,2}|oct)$/.test(n), `chart file name "${n}"`)
  }
  console.log('chart file names ok')
}

// The brief, answered: one row per line of the problem statement, each proved by a real page section,
// and every number read from the data files (Oct-2026 request)
{
  const sentence = (h) => 'At ' + h.slip + ' bps slippage, only ' + h.profitable + ' of ' + h.total + ' settings make money on ' + h.start.slice(0, 4) + '–' + h.end.slice(0, 4) + ', even picked with hindsight.'
  // the "N of M" count matches the explorer grid it summarises
  const fi = E.fields.indexOf('clean_n'), fn = E.fields.indexOf('clean_net')
  let tot = 0, pos = 0
  for (const p of D.longrun.pairs) for (const [k, v] of Object.entries(E.pairs[p])) if (+k.split('|')[3] === D.hindsight.slip) { tot++; if (v[fi] > 0 && v[fn] > 0) pos++ }
  assert.deepEqual([D.hindsight.profitable, D.hindsight.total], [pos, tot])
  const want = sentence(D.hindsight)
  assert.match(want, /^At 5 bps slippage, only \d+ of \d+ settings make money on 2011–2023, even picked with hindsight\.$/)
  const hm = new (load('Home'))(); hm.props = {}; hm.state = { D }
  assert.equal(hm.renderVals().brief[1].note, want, 'Home: the sentence sits under the 15-year headline')
  const bt = new (load('Backtesting'))(); bt.props = {}; bt.state = { D, H }
  assert.equal(bt.renderVals().hindsight, want, 'Backtesting: the sentence sits in the clean test')

  const C = load('Brief')
  const c = new C(); c.props = {}; c.state = { D, HC }
  const v = c.renderVals()
  const lines = v.rows.filter((r) => r.line)
  assert.equal(lines.length, 10); assert.equal(v.rows.filter((r) => r.group).length, 1)
  assert.deepEqual(lines.map((r) => r.num), ['1', '2', '3', '4', '5', '6.1', '6.2', '6.3', '6.4', '6.5'])
  assert.equal(v.verdict.hindsight, want)
  // Oct-2026 audit: no blanket "Done". Each line carries one of four statuses and says why; lifecycle (tender rules not
  // verified from MCX), the backtest method (one split, not rolling walk-forward) and "unseen history" are partial.
  const STATUSES = ['Implemented and verified', 'Implemented, not independently verified', 'Partly implemented', 'Not implemented']
  const by = Object.fromEntries(lines.map((r) => [r.num, r.status]))
  assert.equal(by['3'], 'Partly implemented'); assert.equal(by['5'], 'Partly implemented'); assert.equal(by['6.2'], 'Partly implemented')
  assert.equal(by['2'], 'Implemented, not independently verified')
  assert.ok(!lines.some((r) => r.status === 'Done'))
  assert.ok(!/walk-forward backtesting/i.test(lines.find((r) => r.num === '3').title))
  for (const r of lines) {
    assert.ok(STATUSES.includes(r.status), r.num + ': status ' + r.status)
    assert.ok(r.why && r.why.length > 30, r.num + ': says why')
    assert.ok(r.show.length > 40 && r.links.length >= 1, r.num + ': says what we show and links to its proof')
    for (const l of r.links) {
      const m = /^([A-Za-z]+)\.dc\.html(?:#([a-z0-9-]+))?$/.exec(l.href)
      assert.ok(m, r.num + ': link ' + l.href)
      const src = readFileSync(`public/pages/${m[1]}.dc.html`, 'utf8')
      if (m[2]) assert.ok(src.includes(`id="${m[2]}"`), r.num + ': ' + l.href + ' points at a section that exists')
    }
  }
  // the numbers on the page are the data files' numbers
  const L = D.longrun, inr = (x) => (x < 0 ? '−' : '') + '₹' + Math.abs(Math.round(x)).toLocaleString('en-IN')
  const r62 = lines.find((r) => r.num === '6.2').show
  assert.ok(r62.includes(L.n + ' trades') && r62.includes(inr(L.net)), r62)
  const K = D.brief.calendar
  assert.equal(K.clean.inside, K.clean.n, 'every clean-test trade sits inside its contracts\' calendars')
  assert.equal(K.ours.inside, K.ours.n, 'every trade on our download sits inside its contracts\' calendars')
  assert.ok(lines.find((r) => r.num === '5').show.includes((K.clean.n + K.ours.n).toLocaleString('en-IN') + ' trades, ' + L.start.slice(0, 4) + '–' + D.asOf.slice(0, 4)))
  assert.equal(K.clean.n, L.n, 'the calendar check covers every clean-test trade')
  assert.match(lines.find((r) => r.num === '6.4').show, /% of the gross result over all [\d,]+ trades, 2011–20\d\d/)
  // headline covers every year; the carry figures are named as our own download
  assert.equal(v.verdict.kicker, 'The answer, ' + L.start.slice(0, 4) + '–' + D.asOf.slice(0, 4))
  assert.match(lines.find((r) => r.num === '2').show, /On our own MCX download \(/)
  // without the 2011-2023 trades the all-years attribution waits; it never falls back to our years alone
  const w = new C(); w.props = {}; w.state = { D }
  assert.match(w.renderVals().rows.find((r) => r.num === '6.4').show, /…/)
  // route, menus, keyboard and search
  assert.match(readFileSync('public/app/main.js', 'utf8'), /brief: 'Brief'/)
  const keys = readFileSync('public/app/keys.js', 'utf8')
  assert.ok(keys.includes("['9', 'The brief, answered', '#/brief'") && keys.includes('/^[1-9]$/'), 'key 9 and the search list open the brief')
  assert.ok(readFileSync('public/pages/Rail.dc.html', 'utf8').includes('href="Brief.dc.html"') && readFileSync('public/pages/TabBar.dc.html', 'utf8').includes('href="Brief.dc.html"'))
  console.log('brief ok')
}

// Pair Explorer: a pair the model never traded says so instead of showing an empty table (Oct-2026 report)
{
  for (const pair of Object.keys(D.pairs)) {
    const p = new (load('Pairs'))(); p.props = {}; p.state = { D, HC, pair }
    const v = p.renderVals()
    const none = D.pairs[pair].trades.length === 0
    assert.equal(v.hasTrades, !none, pair + ': table shown only when there are trades')
    assert.equal(v.noTrades.show, none, pair + ': empty-state message shown only when there are no trades')
    if (none) assert.match(v.noTrades.text, /never traded .+ from \d+ \w+ \d{4} to \d+ \w+ \d{4}/)
  }
  assert.ok(Object.values(D.pairs).some((x) => x.trades.length === 0), 'at least one pair (GOLDM · GOLDTEN) has no trades today')
  console.log('pair empty state ok')
}

// no book names on the site: page templates, scripts and the data they show (Oct-2026 request)
{
  const fs2 = await import('node:fs'), path2 = await import('node:path'), { fileURLToPath } = await import('node:url')
  const root = path2.resolve(path2.dirname(fileURLToPath(import.meta.url)), '../public')
  const files = []
  const walk = (d) => { for (const f of fs2.readdirSync(d, { withFileTypes: true })) { const p = path2.join(d, f.name); if (f.isDirectory()) { if (f.name !== 'vendor') walk(p) } else if (/\.(html|js|json)$/.test(f.name)) files.push(p) } }
  walk(root)
  for (const f of files) {
    const t = fs2.readFileSync(f, 'utf8').replace(/order[- ]book|book fill|only_in_book\w*|SRC_BOOK|load_book|BOOK_PATH/gi, '')
    assert.doesNotMatch(t, /\bdata book\b|\bhistory book\b|\bthe book\b|\bbook\b/i, path2.relative(root, f) + ' mentions a book')
    // every price is our own MCX download (Oct 2026): no page may name anything else as the source
    if (!/[\/]data[\/]/.test(f)) assert.doesNotMatch(t, /\barchive\b|shared with permission|with their permission/i, path2.relative(root, f) + ' credits another data source')
  }
  console.log('no book names ok')
}

// Downloads credit the data (CLAUDE.md rule 4): every price is MCX Bhavcopy, downloaded by us from MCX
{
  const mk = (st) => { const c = new (load('DownloadPanel'))(); c.props = { dark: true, onClose: () => {} }; c.state = { D, H, HC, ...st }; return c }
  for (const what of ['today', 'prices', 'trades', 'backtest', 'report']) {
    const c = mk({ what, period: 'all', pair: 'ALL' })
    const d = c.doc(D, what, 'ALL', 'Everything since 2011', c.table(D, what, 'ALL', 'all', H, HC))
    assert.match(d.foot, /MCX Bhavcopy closes \(not verified to equal the official settlement price\), .+ all downloaded by us from MCX/, what + ": PDF and printable page credit MCX")
    assert.doesNotMatch(d.foot, /archive|shared with/i)
  }
  const tr = mk({}).table(D, 'trades', 'ALL', 'all', H, HC)
  assert.equal(tr.head[11], 'Data source')
  assert.ok(tr.rows.every((r) => (r[10] === 'Clean test') === /2011–2023/.test(r[11]) && /Our MCX download/.test(r[11])), 'every trade is credited to our MCX download, with its part of the study')
  const bt = mk({}).table(D, 'backtest', 'ALL', 'all', H, HC)
  assert.ok(bt.rows.filter((r) => D.longrun.pairs.includes(Object.keys(D.pairs).find((k) => D.pairs[k].label === r[0]))).every((r) => /Our MCX download, 2011–2023/.test(r[13])))
  console.log('download credit ok')
}

// Oct-2026 compliance audit: new views show the pipeline's numbers, labels follow the data
{
  const CV = JSON.parse(readFileSync('public/data/curve.json', 'utf8'))
  const PF = JSON.parse(readFileSync('public/data/portfolio.json', 'utf8'))
  const PV = JSON.parse(readFileSync('public/data/provenance.json', 'utf8'))
  const RB = JSON.parse(readFileSync('public/data/robustness.json', 'utf8'))
  const inr = (x) => '₹' + Math.round(x).toLocaleString('en-IN')
  // Term structure: rows are the latest snapshot's contracts, prices straight from curve.json, filters and dates react
  const mk = (st) => { const c = new (load('Market'))(); c.props = {}; c.state = { D, CV, ...st }; return c.renderVals().ts }
  const ts = mk({})
  const latest = CV.snapshots.find((s) => s.date === CV.latest)
  assert.equal(ts.show, true); assert.equal(ts.rows.length, latest.contracts.length)
  const first = latest.contracts.slice().sort((a, b) => (a.expiry < b.expiry ? -1 : a.expiry > b.expiry ? 1 : a.symbol < b.symbol ? -1 : 1))[0]
  assert.equal(ts.rows[0].px, first.no_trade ? '–' : inr(first.px_per_10g_pure))
  assert.ok(ts.title.includes(ts.legendCmp) && ts.hasCmp, 'compares with the snapshot about a month earlier')
  const other = CV.snapshots.find((s) => s.date !== CV.latest && s.date !== CV.month_ago)
  assert.notEqual(mk({ tsCmp: other.date }).legendCmp, ts.legendCmp, 'picking another date changes the comparison')
  const noPetal = mk({ tsOff: ['GOLDPETAL'] })
  assert.ok(noPetal.rows.every((r) => r.sym !== 'GOLDPETAL') && noPetal.rows.length < ts.rows.length)
  assert.match(ts.carry.now, /% a year$/); assert.match(ts.decNote, /accounting identity/)
  assert.ok(ts.decRows.every((r) => r.gap === '< 0.001'), 'decomposition parts add back exactly')
  assert.equal(mk({ CV: undefined }).show, false)
  // Backtesting: forward period starts the day after the test year; portfolio table = portfolio.json
  const b = new (load('Backtesting'))(); b.props = {}; b.state = { D, H, HC, R, PF }
  const bv = b.renderVals()
  const day1 = new Date(Date.parse(D.split.test_end + 'T00:00:00Z') + 864e5).toISOString().slice(0, 10)
  assert.ok(bv.cmp.optsA.some((o) => o.label === 'After the test year (from ' + (+day1.slice(8)) + ' Oct ' + day1.slice(0, 4) + ')'), 'forward period label starts on ' + day1)
  const all = bv.pf.rows.find((r) => r.name === 'All years')
  assert.equal(all.n, String(PF.periods.all.n_trades))
  assert.equal(all.net, (PF.periods.all.net_rs < 0 ? '−' : '') + '₹' + Math.abs(Math.round(PF.periods.all.net_rs)).toLocaleString('en-IN'))
  assert.ok(bv.pf.notes.some((n) => /out of the trades ENTERED/.test(n)) && bv.pf.notes.some((n) => /not a per-trade figure annualised/.test(n)))
  assert.match(bv.pf.intro, /margin is not modelled/)
  assert.ok(!/walk-forward/i.test(JSON.stringify(bv, (k, x) => (typeof x === 'function' ? undefined : x)).replace(/not a rolling walk-forward|one split, not a rolling walk-forward/g, '')))
  // Data page: the specification and tender tables and the file manifest are the pipeline's
  const dv = new (load('Data'))(); dv.props = {}; dv.state = { D, H, PV }
  const dd = dv.renderVals()
  assert.equal(dd.spec.rows.length, D.lifecycleRule.tables.specs.length); assert.equal(dd.spec.tender.length, D.lifecycleRule.tables.tender_reported.length)
  assert.ok(dd.spec.rows.every((r) => r.status !== 'official'))
  assert.equal(dd.prov.files.length, PV.files.length); assert.match(dd.prov.priceField, /not verified/)
  // Signals: alerts and trades are reconciled, not forced to match
  assert.equal(RB.reconcile.adds_up, true)
  const sg = new (load('Signals'))(); sg.props = {}; sg.state = { D, R: RB }
  assert.match(sg.renderVals().ft.reconcile, new RegExp(RB.reconcile.trades + ' trades'))
  // Pitch: every figure marked data-pitch is filled by pitch/data.js from the data (no stale hand-typed results)
  const pitch = readFileSync('public/pitch/index.html', 'utf8'), pjs = readFileSync('public/pitch/data.js', 'utf8')
  const keys = [...pitch.matchAll(/data-pitch="([a-z_]+)"/g)].map((m) => m[1])
  assert.ok(keys.length >= 15)
  for (const k of keys) assert.ok(pjs.includes("'" + k + "'"), 'pitch/data.js fills ' + k)
  assert.ok(pitch.includes('<script type="module" src="data.js"></script>') && !/Honest Test \(Walk-Forward\)/.test(pitch))
  console.log('audit views ok')
}

// Every classic script the site loads must parse (Oct-2026: a "/" in a Goldie regex broke explain.js and no test noticed)
{
  const { readdirSync } = await import('node:fs')
  for (const dir of ['public/app', 'public/intro']) {
    for (const f of readdirSync(dir).filter((x) => x.endsWith('.js'))) {
      const src = readFileSync(dir + '/' + f, 'utf8')
      if (/^\s*import |\bawait\b[^\n]*fetch/m.test(src)) continue          // ES modules are checked by node --check in CI
      assert.doesNotThrow(() => new Function(src), dir + '/' + f + ' does not parse')
    }
  }
  console.log('scripts parse ok')
}
