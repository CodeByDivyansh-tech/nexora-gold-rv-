/*
 * glossary.js — "Words explained": a small button on every page that opens a
 * searchable list of the terms the site uses, each in one plain sentence.
 * Lives outside #app, so page re-renders never touch it. Press "?" to open.
 */
(function () {
  'use strict';
  var TERMS = [
    ['bps (basis point)', '1 bps is 0.01%. On gold at about ₹1,48,000 per 10 g, 1 bps is roughly ₹15.'],
    ['Pure-gold price', 'Each contract\'s price divided by its grams and purity, times 10, so all four are priced per 10 g of pure gold and can be compared.'],
    ['Pair', 'Two of the four contracts compared with each other. Four contracts make six pairs.'],
    ['Gap (spread)', 'How much one contract costs more than the other per pure gram, after adjusting for their different expiry dates. Measured in bps.'],
    ['Normal level', 'The average gap over the previous 10 to 30 trading days (each pair has its own window, chosen on the training years). It only uses past days.'],
    ['z-score', 'How unusual today\'s gap is: the gap from normal divided by its typical daily swing. Beyond ±2 (±2.5 for some pairs) is unusual; 1.5 further out is the stop-loss.'],
    ['Round trip', 'Buying and selling both contracts of a pair: four orders. At our 5 bps slippage it costs 24.4 bps in total.'],
    ['Cost line (hurdle)', 'Twice the round-trip cost, 48.8 bps. The gap from normal must be at least this big before an alert fires, as a safety margin.'],
    ['Slippage', 'The difference between the price you hoped for and the price you actually got. We assume 5 bps per order and show 0, 2 and 10 bps too. Daily data cannot measure it; only real broker fills can.'],
    ['The five checks', 'Enough history, an unusual gap below the stop-loss, a gap above the cost line, liquid contracts, and at least 7 trading days to expiry. All five must pass on the same day.'],
    ['Quiet', 'No pair passes all five checks today, so the site suggests no trade. Most days are quiet, and that is expected.'],
    ['Cost of carry', 'Contracts that expire later cost more, because holding gold ties up money. We measure it from the market (a median of about 8% a year on GOLDPETAL) and remove it before comparing contracts.'],
    ['Expiry and roll', 'Every contract ends on its expiry date. We switch to the next contract using the previous day\'s open interest, so no future information is used.'],
    ['Tender period', 'The delivery window just before expiry. We never enter in the last 7 trading days and always close at least 4 trading days before expiry.'],
    ['Open interest', 'How many contracts are still open at the end of the day. Together with volume, it tells us whether a contract is liquid enough to trade.'],
    ['Bhavcopy', 'MCX\'s official end-of-day file with every contract\'s open, high, low, close, volume and open interest. All our prices are its Close field; we have not verified that it equals the official settlement price in every period.'],
    ['Train/test split', 'Settings are chosen once on two years of data (Oct 2023 – Sep 2025), frozen, then run on the next 12 months (the test year) and on 2011–2023 (the historical holdout). It is one split, not a rolling walk-forward: the settings are never re-fitted. The rule was revised after the test year was first seen, so the holdout is the cleaner check.'],
    ['Training switch', 'A pair trades in the test year only if, with its frozen settings, it made at least 10 trades and a profit in training. Only GOLDM · GOLDPETAL qualified, and only just (close to a coin flip), so it is a weak filter.'],
    ['Clean test', 'The historical holdout, 2011–2023: years never used to choose the settings. The rule was frozen before that data was first used; in Oct 2026 its contract-lifecycle and liquidity checks were corrected after those results were known (to fix the rules, not to change the results), and the settings were re-chosen on training data only.'],
    ['t-statistic', 'How far the average trade result is from zero compared with its noise. Beyond ±2 is the usual bar. The Backtesting page shows it for every period; trades that overlap in time are not fully independent, so the portfolio section also gives a Newey–West version on daily results.'],
    ['95% range (resampling)', 'We redraw the same trades 10,000 times at random to see how much the total could swing by luck. The middle 95% of those totals is the range.'],
    ['Attribution', 'Splitting each trade\'s profit into the part from the gap closing and the part from gold\'s own price move. Gold\'s part is about 1% here, because both legs hold the same grams of gold.'],
    ['Leg', 'One side of a pair trade. We buy one contract and sell the other, holding the same grams of gold on each side.']
  ];

  var css = '' +
    '.gl-x:focus-visible,.gl-q:focus-visible{outline:2px solid var(--grv-gold,#E5B04A);outline-offset:2px}' +
    '.gl-back{position:fixed;inset:0;z-index:60;background:rgba(18,12,4,.5);display:flex;justify-content:flex-end}' +
    '.gl-panel{width:min(440px,100%);height:100%;box-sizing:border-box;background:var(--grv-panel,#1B150C);color:var(--grv-fg,#F6ECD8);border-left:1px solid var(--grv-line,#3A2D1A);display:flex;flex-direction:column;' +
    'font-family:Geist,system-ui,sans-serif;padding:max(20px,env(safe-area-inset-top,0px)) 20px 20px}' +
    '.gl-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}' +
    '.gl-head h2{margin:0;font-size:20px;font-weight:600;letter-spacing:-.01em}' +
    '.gl-x{min-width:44px;min-height:44px;border-radius:12px;border:1px solid var(--grv-line,#3A2D1A);background:var(--grv-raised,#261D11);color:var(--grv-fg,#F6ECD8);font-size:20px;cursor:pointer}' +
    '.gl-q{min-height:44px;padding:0 14px;border-radius:12px;border:1px solid var(--grv-line,#3A2D1A);background:var(--grv-raised,#261D11);color:var(--grv-fg,#F6ECD8);font:500 16px Geist,system-ui,sans-serif;margin-bottom:8px}' +
    '.gl-list{list-style:none;margin:0;padding:0;overflow-y:auto;flex:1}' +
    '.gl-list li{padding:12px 2px;border-bottom:1px solid var(--grv-line,#3A2D1A)}' +
    '.gl-list dt,.gl-t{font-weight:600;font-size:15px;color:var(--grv-gold,#E5B04A);margin-bottom:3px}' +
    '.gl-d{font-size:14px;line-height:1.55;color:var(--grv-fg,#F6ECD8);opacity:.86}' +
    '.gl-none{padding:16px 2px;color:var(--grv-muted,#BBA987);font-size:14px}' +
    '.gl-foot{margin-top:10px;font-size:12px;color:var(--grv-muted,#BBA987)}';

  var st = document.createElement('style');
  st.textContent = css;
  document.head.appendChild(st);


  var back = null, lastFocus = null;

  function close() {
    if (!back) return;
    back.remove();
    back = null;
    document.removeEventListener('keydown', onKey, true);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function onKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); close(); return; }
    if (e.key === 'Tab' && back) {
      var f = back.querySelectorAll('button, input');
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }

  function open(query) {
    if (back) return;
    lastFocus = document.activeElement;
    back = document.createElement('div');
    back.className = 'gl-back';
    back.addEventListener('click', function (e) { if (e.target === back) close(); });
    var panel = document.createElement('div');
    panel.className = 'gl-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-labelledby', 'gl-title');
    panel.innerHTML = '<div class="gl-head"><h2 id="gl-title">Words explained</h2><button type="button" class="gl-x" aria-label="Close">×</button></div>' +
      '<label for="gl-q" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)">Search the words</label>' +
      '<input id="gl-q" class="gl-q" type="search" placeholder="Search, e.g. z-score" autocomplete="off">' +
      '<ul class="gl-list" aria-live="polite"></ul>' +
      '<div class="gl-foot">' + TERMS.length + ' words · press ? on any page to open this</div>';
    back.appendChild(panel);
    document.body.appendChild(back);
    var list = panel.querySelector('.gl-list'), q = panel.querySelector('.gl-q');
    function draw() {
      var v = q.value.trim().toLowerCase();
      list.innerHTML = '';
      var n = 0;
      TERMS.forEach(function (t) {
        if (v && (t[0] + ' ' + t[1]).toLowerCase().indexOf(v) < 0) return;
        n++;
        var li = document.createElement('li');
        var a = document.createElement('div'); a.className = 'gl-t'; a.textContent = t[0];
        var b = document.createElement('div'); b.className = 'gl-d'; b.textContent = t[1];
        li.appendChild(a); li.appendChild(b); list.appendChild(li);
      });
      if (!n) { var e = document.createElement('li'); e.className = 'gl-none'; e.textContent = 'No word matches "' + q.value + '".'; list.appendChild(e); }
    }
    q.addEventListener('input', draw);
    panel.querySelector('.gl-x').addEventListener('click', close);
    if (query) q.value = query;
    draw();
    document.addEventListener('keydown', onKey, true);
    q.focus();
  }

  // Any element with data-term="z-score" opens the list filtered to that word.
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-term]');
    if (t) { e.preventDefault(); open(t.getAttribute('data-term')); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== '?' || back) return;
    var el = document.activeElement, tag = el && el.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || (el && el.isContentEditable)) return;
    e.preventDefault();
    open('');
  });
  window.GRVGlossary = { open: open, terms: TERMS };
})();
