/*
 * explain.js — Goldie explains the page for first-time visitors.
 * Double-click (double-tap) any row, number, card or chart: Goldie explains that exact item, using its own numbers.
 * It only reads the page (never changes #app), so page re-renders cannot break it.
 * Links, buttons and inputs keep working normally while it is on.
 */
(function () {
  'use strict';
  // [pattern matched against the start of a box's text, title, note]
  var NOTES = [
    // Try your own rule (Explore)
    [/^For exploring only/, 'Why "for exploring only"', 'If you try many settings and keep the best one, you will always find something that looked good in the past. The published rule was picked on the training years only, so its later results are a fair test. Yours are not.'],
    [/^Settings\s/, 'The settings', 'Each button picks one value for the backtest. Every combination was run in advance with the real engine, so the result on the right is a genuine backtest, not an estimate.'],
    [/^Year by year, after costs/, 'Year by year', 'One bar per calendar year: green made money after costs, red lost. Tap a bar to read its number. Most years lose, which is why one good year does not prove an edge.'],
    [/^Does any setting work\?/, 'Does any setting work?', 'We count how many of the 36 combinations of window, entry and hold lose money at your slippage. Then we take the one that looked best in training and show what it did afterwards.'],
    [/^(All six pairs|GOLD\w+ · GOLD\w+), \d{4}–\d{4}, at \d+ bps slippage/, 'Your result', 'The total after every cost over all the years we have, then split into the clean test, the training years and the test year. The clean test counts most: those are years no version of the rule had seen.'],
    // Home
    [/^Same gold\.\s*Four prices\./, 'Same gold, four prices', 'MCX sells the same gold in four sizes: a 100 g bar, a 10 g bar, an 8 g coin and a 1 g piece. We check whether they all cost the same per gram.'],
    [/^GOLD(M|TEN|GUINEA|PETAL)\n(Gold|GOLD)/, 'One gold contract', 'The big number is this contract\'s price; the wavy line is how it moved this year. The bottom number turns it into the price of 10 g of pure gold, so all four cards can be compared.'],
    [/^Is any gap between them worth trading today\?/, 'Today\'s answer', 'Each bar is how far apart two contracts are. The gold line is the cost of trading. No bar crosses it, so the answer today is "No".'],
    [/^Gold price, per 10 g of pure gold/, 'Gold\'s price', 'This is simply the price of gold over time. Use 1M, 3M, 1Y or 3Y to look at a shorter or longer stretch.'],
    [/^Want to go deeper\?/, 'Where to go next', 'Shortcuts to the other pages. Pick whichever you are curious about.'],
    [/^[\d,]+\s*\n\s*official MCX daily prices/, 'The project in four numbers', 'How many prices we checked, over how long, and how the test went, in one line.'],
    // Today
    [/^Is any gap worth trading today\?/, 'Today', 'This page answers one question every day: is any price gap big enough to be worth trading?'],
    [/^Pairs above the cost line/, 'Pairs above the line', 'How many of the six pairs have a gap bigger than the cost of trading. When it is 0, we wait.'],
    [/^Biggest gap from normal/, 'Biggest gap', 'The largest difference we found today. It is still smaller than the cost line.'],
    [/^Cost line/, 'The cost line', 'Trading costs money, like a ticket. We ask for a gap twice as big as the ticket, to be safe.'],
    [/^The hurdle/, 'The hurdle', 'Think of a high-jump bar. Each grey bar is a gap and the gold line is the bar it must clear. None clear it today.'],
    [/^Replay (\d+|three) years/, 'Time machine', 'Press play or drag the slider to travel back and watch the gaps week by week. "All data" starts in 2011 (three pairs back then); "Since Oct 2023" shows our own download with all six pairs.'],
    [/^Replay every week of gaps since 2011/, 'Time machine', 'Opens the Today page replay: every week since 2011, with each pair\'s biggest gap from normal against the cost line.'],
    [/^All six pairs, in numbers/, 'The full table', 'The same six pairs with every number, and which of the five checks each one failed.'],
    // Market
    [/^Same gold, four prices/, 'Comparing the four', 'All four contracts are the same gold, so their lines should sit on top of each other. This page shows how close they really are.'],
    [/^Price of 10 g of pure gold, by contract/, 'Four lines, one gold', 'One coloured line per contract. They almost overlap, because it is the same gold.'],
    [/^Gap to GOLDTEN today/, 'Gaps today', 'How much more each contract costs than GOLDTEN today, before we adjust for their different end dates.'],
    [/^How far each contract sits from GOLDM/, 'Cheap or expensive?', 'Zero means "same price as GOLDM"; above zero means dearer. See GOLDPETAL switch from cheap to dear around early 2025.'],
    [/^Normal is not fixed/, 'Normal moves', 'The usual gap changes over time, so we keep updating what "normal" means instead of using one fixed number.'],
    [/^The four contracts/, 'ID cards', 'Each contract\'s size, purity, end date and how much it is traded.'],
    [/^How we make them comparable/, 'The conversion', 'The small sum that turns every price into the price of 10 g of pure gold, with two worked examples.'],
    // Pair Explorer
    [/^Pair Explorer/, 'Pair Explorer', 'Pick any two contracts and see their whole story since 2023.'],
    [/^GOLD\S+ · GOLD\S+\ngap today/, 'Pick a pair', 'Tap a pair to switch everything below to it.'],
    [/^GOLD\S+ · GOLD\S+: \w+ \d{4} to/, 'The gap over time', 'The brown line is the gap between the two contracts. Each dot is a trade: green made money, red lost money.'],
    [/^Every trade the model took/, 'Trade list', 'Every trade: when it started, why it ended, and how much it made or lost after costs.'],
    [/^This pair, \w+ \d{4} – \w+ \d{4}/, 'This pair, every year', 'All of this pair\'s trades from its first year to today, then the same split by period. The clean test counts most: those years were never used to build the rule.'],
    // Signals
    [/^Why is it quiet\?/, 'Why quiet?', 'A signal is like a green traffic light. It only turns green when all five checks pass at once. Today they do not.'],
    [/^GOLD\S+ · GOLD\S+\nQuiet/, 'Pick a pair', 'Tap a pair to see its five checks.'],
    [/^GOLD\S+ · GOLD\S+ · contracts/, 'Short answer', 'How many of the five checks this pair failed today. One failed check is enough to stay quiet.'],
    [/^Check \d/, 'One of the five checks', '"Pass" means this part is fine; "Fail" says what is missing.'],
    [/^Does the gap beat the cost\?/, 'Gap vs cost', 'The grey bar is today\'s gap; the gold line is what we need. The bar is too short, so no trade.'],
    [/^What one round trip costs/, 'All the fees', 'Every fee for buying and selling once, added up. The biggest part is slippage: the small price you lose each time you trade.'],
    [/^Work out your own cost/, 'Your own cost', 'Type in your own fees to see whether any pair would be worth it for you. Try the buttons to see how much costs matter.'],
    [/^After an alert, does the gap close\?/, 'Do alerts work?', 'After an alert, did the gap really shrink? Green means it shrank by more than the cost.'],
    [/^Every trade the backtest took for this pair/, 'Past trades', 'All the practice trades this pair made in the past, with the result of each.'],
    // Backtesting
    [/^Did it make money\?/, 'The test', 'We practised on two years of real prices, froze the rules and tested on the next year. The clean test is the earlier years 2011–2023, never used to choose the settings.'],
    [/^The verdict|^No persistent edge proven after costs/, 'The final answer', 'We could not prove the idea makes money reliably. Saying "no" honestly, with proof, is a real result.'],
    [/^Test year: take out one crash and it loses/, 'The storm', 'Gold bars are trades during the Jan–Mar 2026 gold crash; grey bars are all the others. At our 5 bps cost, everything outside the crash adds up to a loss.'],
    [/^How sure can we be\?/, 'Luck check', 'We reshuffled the trades 10,000 times to see how much luck matters. A long bar means "not sure".'],
    [/^One rule for alerts and backtest/, 'One rule', 'The same five checks decide today\'s alerts and the past test, so nothing is hidden.'],
    [/^GOLDM · GOLDPETAL\nGOLDM · GOLD/, 'Choose what to test', 'Pick a pair and a slippage level. Every number below changes.'],
    [/^(Trades, \d{4}–\d{4}|Won\n|Average per trade|Total after costs|t-statistic)/, 'Score card', 'This pair over every year we have, in five numbers. Read them together: few trades means the score is shaky.'],
    [/^GOLD\S+ · GOLD\S+ at \d+ bps slippage/, 'Money over time', 'The running total, trade after trade. The shaded part is the test year.'],
    [/^Same trades, different costs/, 'Cheaper or dearer trading', 'The same trades with cheaper or dearer trading. More slippage means less profit.'],
    [/^Where the result came from/, 'Where the money came from', 'Did it come from the gap closing (what we bet on) or from gold\'s price moving? Almost all of it came from the gap.'],
    [/^The clean test: \d+ years never used to choose the settings/, 'The clean test', 'The same frozen settings run on 2011–2023, years never used to choose them. Far more trades than the test year, and it loses money after costs: no lasting edge.'],
    [/^Can daily data measure slippage\?/, 'Slippage', 'Slippage is the price you lose each time you buy or sell. It is most of our cost, but daily prices are too coarse to measure it, so the real number needs real broker fills.'],
    [/^Read this year with care/, 'Why the test year is not clean', 'We looked at this year\'s results before we wrote the final rule. A clean test uses data nobody has looked at yet, which is why 2011–2023 counts for more.'],
    [/^How many looks\?/, 'Many tries', 'The more versions of a rule you score on the same data, the more likely one looks good by luck. This adjusts for that.'],
    [/^Settings for /, 'The frozen settings', 'The exact rules this pair used, fixed before the test year started.'],
    // Data
    [/^Where the numbers come from/, 'Our data', 'Every number on this site comes from MCX\'s official end-of-day price files.'],
    [/^([\d,]+)\s*\n\s*(daily prices|daily closes|contracts|trading days|mismatches)/, 'Data in numbers', 'Quick facts about our data. "0 mismatches" means our copy matches MCX\'s files exactly.'],
    [/^How we cleaned it/, 'Cleaning', 'Days with no trading were removed, thin days were flagged, and special weekend sessions were kept.'],
    [/^From raw files to this website/, 'Eight steps', 'The eight steps our Python code follows, from MCX files to the charts you see.'],
    [/^How we avoid peeking at the future/, 'A fair exam', 'The model only uses past days, never tomorrow\'s answers, like an exam without the answer key.'],
    [/^What this data cannot tell you/, 'Honest limits', 'What our data cannot show. Good research says what it does not know.'],
    [/^2003 to 2023, downloaded from MCX/, 'The older years', 'We downloaded every older gold contract from MCX\'s Bhavcopy service, one request per contract, going back to 2003. These years drive the long-history check and the long charts.'],
    [/^Download log/, 'Receipts', 'A record of every file we downloaded, so anyone can check our work.'],
    [/^Check it yourself/, 'Check it yourself', 'All our code and data are public on GitHub, so anyone can run it again.']
  ];

  // ---- Item notes: explain the exact row, card or number that was double-clicked, using its own numbers.
  // Each pattern is matched against the item's whole text (spaces collapsed). Checked before the section notes.
  var CON = {
    GOLDM: 'Gold Mini: one lot is 100 g of 995-purity gold, priced per 10 g. It is the most traded of the four.',
    GOLDTEN: 'Gold Ten: one lot is 10 g of 999-purity gold, priced per 10 g. It only started trading in March 2025.',
    GOLDGUINEA: 'Gold Guinea: one lot is an 8 g coin of 999-purity gold, priced per 8 g.',
    GOLDPETAL: 'Gold Petal: one lot is just 1 g of 999-purity gold, priced per 1 g. The smallest and cheapest way in.'
  };
  var WHY = {
    'Back to normal': 'the gap went back near its normal level, which is what we bet on',
    'Time limit': 'it reached the 10-day limit',
    'Stop-loss': 'the gap kept growing, so the stop-loss closed it to limit the loss',
    'Contract roll': 'one contract was close to expiry, so the trade was closed before switching to the next month'
  };
  var CHECK = {
    'Enough history': 'We need enough past days to know what "normal" looks like for this pair.',
    'Extreme gap': 'The gap must be unusual (z of about 2 or more), but not so extreme that it is already at the stop-loss.',
    'Beats costs': 'The gap must be bigger than the cost line, so a trade could pay for all its fees.',
    'Liquidity': 'Both contracts must be traded enough that we could really buy and sell them.',
    'Timing': 'Not too close to expiry or a contract switch, so a trade does not get stuck in the delivery period.'
  };
  var FEE = {
    'Slippage': 'the small amount you lose because you rarely trade at exactly the listed price',
    'Commodity transaction tax': 'a government tax on commodity futures, charged when you sell',
    'Exchange fees': 'what MCX charges for using the exchange',
    'Brokerage': 'what your broker charges for each order',
    'Stamp duty': 'a state tax, charged when you buy',
    'GST': 'Goods and Services Tax on the brokerage and fees',
    'SEBI fee': 'a tiny fee paid to SEBI, the market regulator'
  };
  var STEP = {
    '1': 'Read the MCX files and check every row: dates, prices, no duplicates.',
    '2': 'Turn every price into the price of pure gold, so the four contracts can be compared.',
    '3': 'Adjust for different expiry dates: a later contract normally costs a little more.',
    '4': 'Build the six pairs and the price gap (spread) of each one.',
    '5': 'Measure how unusual each gap is (the z-score), using only earlier days.',
    '6': 'Apply the five checks that decide both the alerts and the backtest trades.',
    '7': 'Tune on two years, freeze the settings, test on the next year, then check 2011–2023, which was never used to choose the settings.',
    '8': 'Subtract every MCX cost, then split the result into spread moves, gold price moves and costs.'
  };
  var GROUP = {
    'Alerts, test year': 'Days in the test year when all five checks passed (an alert).',
    'Alerts, clean test': 'Days in 2011–2023 when all five checks passed (an alert): the biggest and cleanest sample.',
    'Alerts, training years': 'Alert days in the two training years.',
    'Unusual gap, no alert': 'Days with an unusual gap that still failed another check, so no alert.',
    'Ordinary days': 'Normal days with nothing unusual, for comparison.'
  };
  var MONEY = {
    'Spread moves (what we bet on)': 'Money made or lost because the gap between the two contracts changed. This is the part the strategy is betting on.',
    'Gold price moves (leftover exposure)': 'Money from gold\'s own price moving. The two legs almost cancel out, so this should be close to zero.',
    'Costs and slippage': 'Everything paid in fees and slippage on these trades.',
    'Result after costs': 'What was left after adding everything up.'
  };
  function n(s) { return parseFloat(String(s).replace(/[₹,+L%]/g, '').replace('−', '-')); }
  function pc(bps) { return (Math.abs(n(bps)) / 100).toFixed(2) + '%'; }
  function money(s) { return n(s) >= 0 ? 'made ' + s.replace(/^[+]/, '') : 'lost ' + s.replace(/^[−-]/, ''); }
  function costLine() { var m = (document.querySelector('#app main') || document.body).innerText.match(/(\d+\.\d) bps(?:\s*\n?\s*2 × | \(cost line\)|\)\.?\s*$)/m) || document.body.innerText.match(/cost line \((\d+\.\d) bps\)/); return m ? m[1] : '48.8'; }
  function near(el) { for (var i = 0; el && i < 4; i++, el = el.parentElement) { var m = (el.innerText || '').match(/\b(GOLDM|GOLDTEN|GOLDGUINEA|GOLDPETAL)\b/); if (m) return m[1]; } return 'This contract'; }
  function pairOnPage() { var m = ((document.querySelector('#app main') || {}).innerText || '').match(/(GOLD\w+ · GOLD\w+)(?=: \w+ \d{4} to| at \d+ bps| · contracts)/); return m ? m[1] : 'this pair'; }
  var P = '(GOLD\\w+) · (GOLD\\w+)';
  var ITEMS = [
    [/^(Clean test|Training|Test year|After the test year) (.+?) ([−+]₹[\d,]+|No trades|GOLDTEN not listed yet)(?: (\d+) trades?, (\d+)% made money)?$/, function (m) {
      if (!m[4]) return [m[1], m[3] === 'No trades' ? 'These settings made no trades in this period: no gap passed every check.' : 'GOLDTEN only started trading in 2025, so pairs with it have no 2011–2023 years.'];
      return [m[1], m[2].charAt(0).toUpperCase() + m[2].slice(1) + '. With these settings the rule made ' + m[4] + ' trades here and ' + money(m[3]) + ' after costs; ' + m[5] + '% of trades made money.'];
    }],
    // Long history (Backtesting) and the 2004-2023 download (Data)
    [/^Trades (\d+) (\d+ \w+ \d{4}) – (\d+ \w+ \d{4})$/, function (m) { return ['A longer history', 'The same rule, with its settings fixed in training, made ' + m[1] + ' trades between ' + m[2] + ' and ' + m[3] + ', years never used to choose the settings. That is many more trades than our test year, so the answer is much more certain.']; }],
    [/^After costs ([−+-]₹[\d,]+) at (\d+) bps slippage, (\d+)% won$/, function (m) { return ['After costs, 13 years', 'Added up over all those trades, the rule ' + money(m[1]) + ' after paying every cost, at ' + m[2] + ' bps slippage. Only ' + m[3] + '% of trades made money.']; }],
    [/^Losing years (\d+) of (\d+) (.+)$/, function (m) { return ['Losing years', 'The rule lost money in ' + m[1] + ' of ' + m[2] + ' years; it ' + m[3] + '. A real edge would win in most years.']; }],
    [/^(\d{4}): ([−+-]₹[\d,]+), (\d+) trades$/, function (m) { return ['The year ' + m[1], 'In ' + m[1] + ' the rule made ' + m[3] + ' trades and ' + money(m[2]) + ' after costs. Green bars are years that made money; red bars lost.']; }],
    [new RegExp('^' + P + ' (\\d+) trades before costs ([−+-][\\d.]+) bps a trade ([−+-]₹[\\d,]+) after costs$'), function (m) { return [m[1] + ' vs ' + m[2] + ', 2011–2023', m[3] + ' trades. Before costs the average trade made ' + m[4] + ' bps, which is about zero: the gap does come back, but not by more than the cost of trading. After costs it ' + money(m[5]) + '.']; }],

    [/^(\d+) contracts, one request each (.+)$/, function (m) { return [m[1] + ' contracts', 'Every monthly contract from 2004 to 2023, each with its own expiry date. We asked MCX for each one separately, and every request is in the download log.']; }],
    [/^(\d+) mismatches with a second copy ([\d,]+) rows (.+)$/, function (m) { return ['A second check', 'Another team shared their copy of the same MCX prices with us. On the ' + m[2] + ' rows both copies have, we compared every number: ' + m[1] + ' differences.']; }],
    [/^(\d+) contracts our first download missed (.+)$/, function (m) { return ['What we had missed', 'Our first download left out ' + m[1] + ' near-month contracts from Oct–Dec 2023. We downloaded them from MCX later. They only touch the first weeks of training, not the test year.']; }],
    // Home: contract cards
    [/^(GOLDM|GOLDTEN|GOLDGUINEA|GOLDPETAL) Gold \w+ · (\d+ g) lot$/, function (m) { return [m[1], CON[m[1]]]; }],
    [/^₹([\d,]+) per (\d+) g$/, function (m, el) { return ['Today\'s price', near(el) + '\'s official closing price today: ₹' + m[1] + ' for ' + m[2] + ' g. Each contract is quoted for a different weight, so these raw prices cannot be compared directly.']; }],
    [/^([▲▼]) ₹([\d,]+) \(([−+-]?[\d.]+)%\) Prev\. ₹([\d,]+)$/, function (m, el) { return ['Change since yesterday', near(el) + ' went ' + (m[1] === '▲' ? 'up' : 'down') + ' by ₹' + m[2] + ' (' + m[3].replace(/^[−-]/, '') + '%) from yesterday\'s closing price of ₹' + m[4] + '.']; }],
    [/^Per 10 g pure gold ₹([\d,]+)$/, function (m, el) { return ['Price of 10 g of pure gold', 'We turn ' + near(el) + '\'s price into the price of 10 g of 100% pure gold: ₹' + m[1] + '. Now all four contracts can be compared fairly.']; }],
    [new RegExp('^' + P + ' ([\\d.]+) bps$'), function (m) { var c = costLine(), g = n(m[3]); return [m[1] + ' vs ' + m[2], 'The price gap between ' + m[1] + ' and ' + m[2] + ' is ' + m[3] + ' bps (' + pc(m[3]) + ') away from its normal level. To be worth trading it must pass the cost line of ' + c + ' bps' + (g < n(c) ? ', so it is ' + (n(c) - g).toFixed(1) + ' bps short.' : '. It does.')]; }],
    [/^([\d,]+) official MCX daily prices: ([\d,]+) for 2011–2023, ([\d,]+) since Oct 2023$/, function (m) { return ['Prices used', m[1] + ' official end-of-day prices, one per contract per trading day, all downloaded by us from MCX: ' + m[2] + ' for 2011–2023 and ' + m[3] + ' since October 2023.']; }],
    [/^(\d+) years tested, (.+) to (.+)$/, function (m) { return ['How long we tested', m[1] + ' years of gold prices, from ' + m[2] + ' (the first day all three older contracts traded) to ' + m[3] + '.']; }],
    [/^([\d,]+) trades (\d+) in (\d{4})–(\d{4}), (\d+) in training, (\d+) in the test year(?:, \d+ after it)?$/, function (m) { return ['Every trade', 'The rule made ' + m[1] + ' trades in total: ' + m[2] + ' in the clean test (' + m[3] + '–' + m[4] + '), ' + m[5] + ' in the two training years and ' + m[6] + ' in the 12-month test year. Only a few trades a year pass all five checks.']; }],
    [/^([−+-]?₹[\d,]+) the clean test, (\d{4})–(\d{4}), after costs: (\d+) of (\d+) years lost money$/, function (m) { return ['The clean test', 'On ' + m[2] + '–' + m[3] + ', years no version of the rule had seen, it ' + money(m[1]) + ' after costs, and ' + m[4] + ' of ' + m[5] + ' years lost money. This is the most trustworthy result.']; }],
    [/^([−+-]?₹[\d,]+) the 12-month test year, but ([−+-]?₹[\d,]+) without the (.+) crash$/, function (m) { return ['The test year', 'In the 12 months after training the rule ' + money(m[1]) + ', but almost all of it came from the ' + m[3] + ' crash. Without it, it ' + money(m[2]) + '. The rule was revised after its first results there were seen, so this year is not a clean test.']; }],
    // Today
    [/^Pairs above the cost line (\d+) of (\d+) (.+)$/, function (m) { return ['Pairs above the line', m[1] + ' of the ' + m[2] + ' pairs have a gap bigger than the cost line today. ' + (m[1] === '0' ? 'So nothing is worth trading; we wait.' : 'Those are worth a closer look on the Signals page.')]; }],
    [new RegExp('^Biggest gap from normal ([\\d.]+) bps ' + P + '$'), function (m) { var c = costLine(); return ['Biggest gap', 'The largest gap today is ' + m[1] + ' bps, between ' + m[2] + ' and ' + m[3] + '. The cost line is ' + c + ' bps, so even the biggest gap is ' + (n(m[1]) < n(c) ? (n(c) - n(m[1])).toFixed(1) + ' bps short.' : 'above it.')]; }],
    [/^Cost line ([\d.]+) bps 2 × ([\d.]+) bps round trip$/, function (m) { return ['The cost line', 'Buying and selling both contracts once costs about ' + m[2] + ' bps. To be safe we ask for twice that: ' + m[1] + ' bps. A gap smaller than this is not worth trading.']; }],
    [new RegExp('^' + P + ' Contracts (\\S+) / (\\S+) · z ([−+-]?[\\d.]+), needs ±([\\d.]+) Gap Cost line Short by ([\\d.]+) ([\\d.]+) ([\\d.]+) (\\w+)$'), function (m) {
      return [m[1] + ' vs ' + m[2], 'Today their gap is ' + m[7] + ' bps from normal. It must reach the cost line of ' + m[8] + ' bps, so it is ' + m[9] + ' bps short. Its z-score (how unusual the gap is) is ' + m[5].replace('−', '-') + '; it needs ±' + m[6] + '. Status: ' + m[10] + (m[10] === 'Quiet' ? ', so no trade.' : '.')]; }],
    [/^(\d+ \w+ \d{4}) Weeks so far with a gap above the line: (\d+) of (\d+) Weeks the model actually traded: (\d+) of (\d+)$/, function (m) { return ['Up to ' + m[1], m[2] + ' of ' + m[3] + ' weeks had at least one gap above the cost line, but the model traded in only ' + m[4] + ' weeks, because the other four checks must pass too.']; }],
    [new RegExp('^' + P + ' ([\\d.]+)$'), function (m) { return [m[1] + ' vs ' + m[2], 'In the week picked on the slider, the biggest gap from normal for this pair was ' + m[3] + ' bps. The gold line is the cost line it must pass.']; }],
    [/^Drag to any week (.+)$/, function () { return ['The slider', 'Drag it to any week (since 2011 with "All data", or since October 2023), or press Replay. The bars above change to that week.']; }],
    [new RegExp('^' + P + ' ([−+-]?[\\d.]+) bps ([−+-]?₹[\\d,]+) ([−+-]?[\\d.]+) bps ([\\d.]+) bps ([−+-]?[\\d.]+) \\(([\\d.]+)\\) ?(.*)$'), function (m) {
      return [m[1] + ' vs ' + m[2], 'Spread now: ' + m[1] + ' is ' + m[3].replace(/^[+−-]/, '') + ' bps ' + (n(m[3]) < 0 ? 'cheaper' : 'dearer') + ' than ' + m[2] + ' (about ' + m[4].replace(/^[+−-]/, '') + ' per 10 g). Its normal level is ' + m[5] + ' bps, so the gap from normal is ' + m[6] + ' bps. z = ' + m[7].replace('−', '-') + ', needs ' + m[8] + '.' + (m[9] ? ' Checks failed: ' + m[9] + '.' : ' All checks passed.')]; }],
    [/^Pair Spread now In ₹ per 10 g Normal level Gap from normal z \(needed\) Checks failed$/, function () { return ['The columns', 'Spread now: today\'s price difference. Normal level: its usual value. Gap from normal: how far today is from usual. z: how unusual that is. Checks failed: what stopped a trade.']; }],
    // Market
    [/^GOLDM ₹([\d,]+) GOLDTEN ₹([\d,]+) GOLDGUINEA ₹([\d,]+) GOLDPETAL ₹([\d,]+)$/, function (m) { var v = [m[1], m[2], m[3], m[4]].map(n); return ['Today, per 10 g of pure gold', 'All four contracts priced the same way. The dearest and the cheapest are only ₹' + (Math.max.apply(0, v) - Math.min.apply(0, v)).toLocaleString('en-IN') + ' apart, because it is the same gold.']; }],
    [/^(GOLD\w+) ₹([\d,]+) per 10 g pure ([−+-]₹[\d,]+) ([−+-][\d.]+) bps$/, function (m) { return [m[1] + ' vs GOLDTEN', m[1] + ' costs ₹' + m[2] + ' for 10 g of pure gold, ' + m[3].replace(/^[+−-]/, '') + ' ' + (n(m[3]) >= 0 ? 'more' : 'less') + ' than GOLDTEN (' + m[4].replace(/^[+−-]/, '') + ' bps). This is before adjusting for their different expiry dates.']; }],
    [/^GOLDTEN ₹([\d,]+) per 10 g pure Reference$/, function (m) { return ['GOLDTEN, the reference', 'GOLDTEN costs ₹' + m[1] + ' for 10 g of pure gold. The other three are compared with it.']; }],
    [/^GOLDTEN now ([−+-][\d.]+) bps GOLDGUINEA now ([−+-][\d.]+) bps GOLDPETAL now ([−+-][\d.]+) bps$/, function (m) { return ['Compared with GOLDM today', 'After adjusting for expiry: GOLDTEN is ' + m[1] + ', GOLDGUINEA ' + m[2] + ' and GOLDPETAL ' + m[3] + ' bps compared with GOLDM. Above zero means dearer than GOLDM.']; }],
    [new RegExp('^' + P + ' (not listed|[−+-]?[\\d.]+ bps) ([−+-]?[\\d.]+ bps) ([−+-]?[\\d.]+ bps) (.+)$'), function (m) { return [m[1] + ' vs ' + m[2], 'Its usual spread: ' + (m[3] === 'not listed' ? 'no data in Oct 2023 – Dec 2024' : m[3] + ' in Oct 2023 – Dec 2024') + ', ' + m[4] + ' in Apr 2025 – Sep 2026, and ' + m[5] + ' during the Jan–Mar 2026 crash. ' + m[6]]; }],
    [/^(GOLD\w+) Gold \w+ (\d+ g) (\d+ g) (\d+) (.+?) · now (\d+ \w+ \d{4}) ([\d,]+) ([\d,]+)$/, function (m) { return [m[1], 'One lot is ' + m[2] + ', priced per ' + m[3] + ', purity ' + m[4] + ' out of 1000. It expires on the ' + m[5].charAt(0).toLowerCase() + m[5].slice(1) + '; the current contract ends ' + m[6] + '. On the last day ' + m[7] + ' lots traded and ' + m[8] + ' were still open.']; }],
    [/^Contract Lot Priced per Purity Expires Volume \(lots\) Open interest$/, function () { return ['The columns', 'Lot: how much gold one contract is. Purity 999: 99.9% pure. Volume: lots traded that day. Open interest: contracts still open at the end of the day.']; }],
    [/^price ÷ grams quoted ÷ purity × 10 = ₹ per 10 g of pure gold$/, function () { return ['The formula', 'Divide by the grams the price is for (to get 1 g), divide by purity (to get pure gold), then multiply by 10. Every contract ends up as "₹ per 10 g of pure gold".']; }],
    [/^(GOLD\w+), (.+?) ₹([\d,]+) ÷ (\d+) ÷ ([\d.]+) × 10 = ₹([\d,]+)$/, function (m) { return [m[1] + ' worked example', 'Price ₹' + m[3] + ' is for ' + m[4] + ' g, so divide by ' + m[4] + ' for 1 g, divide by ' + m[5] + ' for pure gold, then × 10: ₹' + m[6] + ' per 10 g of pure gold.']; }],
    // Pair Explorer
    [/^Contracts now (\S+) \/ (\S+)$/, function (m) { return ['Contracts now', pairOnPage() + ' uses the ' + m[1] + ' and ' + m[2] + ' contracts right now. We always use the month with the most open interest.']; }],
    [/^Spread today ([−+-]?[\d.]+) bps$/, function (m) { var p = pairOnPage().split(' · '); return ['Spread today', (p[1] ? p[0] + ' is ' + m[1].replace(/^[+−-]/, '') + ' bps (' + pc(m[1]) + ') ' + (n(m[1]) < 0 ? 'cheaper' : 'dearer') + ' than ' + p[1] : 'The spread is ' + m[1] + ' bps') + ', after adjusting for expiry.']; }],
    [/^Normal level ([−+-]?[\d.]+) bps$/, function (m) { return ['Normal level', 'The usual spread for ' + pairOnPage() + ' over the last 30 trading days: ' + m[1] + ' bps. A trade bets on the spread coming back to this.']; }],
    [/^History since (.+)$/, function (m) { return ['History', 'We have prices for this pair from ' + m[1] + ' to today.']; }],
    [/^Model settings \(tuned on training data\) (\d+)-day window · enter at \|z\| ≥ ([\d.]+) · exit at \|z\| ≤ ([\d.]+) · hold ≤ (\d+) days$/, function (m) { return ['The rules', '"Normal" is measured over the last ' + m[1] + ' trading days. A trade starts when the gap is unusual (z ' + m[2] + ' or more), ends when it is back near normal (z ' + m[3] + ' or less), and never lasts more than ' + m[4] + ' days.']; }],
    [/^(\d+ \w+ \d{4}) (Buy|Sell) (GOLD\w+), (buy|sell) (GOLD\w+) ([−+-][\d.]+) (\d+) (.+?) ([−+-]₹[\d,]+) ([−+-][\d.]+) bps (Test year|Training)$/, function (m) {
      return ['Trade on ' + m[1], 'The model ' + (m[2] === 'Buy' ? 'bought ' : 'sold ') + m[3] + ' and ' + (m[4] === 'buy' ? 'bought ' : 'sold ') + m[5] + ' because the gap was unusual (z = ' + m[6].replace('−', '-') + '). It held ' + m[7] + (m[7] === '1' ? ' day' : ' days') + ' and closed because ' + (WHY[m[8]] || m[8].toLowerCase()) + '. After costs it ' + money(m[9]) + ' (' + m[10] + ' bps). ' + (m[11] === 'Training' ? 'This was in the training years.' : 'This was in the test year.')]; }],
    [/^Entered Trade z Days Why it closed Result Period$/, function () { return ['The columns', 'Entered: start date. Trade: what was bought and sold. z: how unusual the gap was. Days: how long it was held. Result: profit or loss after costs.']; }],
    // Score cards (Pair Explorer and Backtesting)
    [/^Trades (\d+)$|^Trades, (\d{4}–\d{4}) (\d+) ?(.*)$/, function (m) { var k = m[1] || m[3]; return ['Number of trades', k + ' trades' + (m[2] ? ' from ' + m[2] + (m[4] ? ': ' + m[4] : '') : '') + '. With fewer than about 30, results are shaky and can easily be luck.']; }],
    [/^Won (\d+)%( after costs)?$/, function (m) { return ['Won', m[1] + '% of the trades made money after costs.']; }],
    [/^Average per trade ([−+-][\d.]+) bps(?: every trade counts equally · before costs ([−+-][\d.]+) bps)?$/, function (m) { return ['Average per trade', 'Each trade made ' + m[1] + ' bps on average (' + pc(m[1]) + ' of one leg) after costs' + (m[2] ? '; before costs it was ' + m[2] + ' bps.' : '.')]; }],
    [/^Total after costs ([−+-]?₹[\d,]+)(?: bigger trades count more · costs paid ₹([\d,]+))?$/, function (m) { return ['Total after costs', 'All the trades together ' + money(m[1]) + ' after paying every fee' + (m[2] ? ' (₹' + m[2] + ' in costs).' : '.')]; }],
    [/^t-statistic ([−+-]?[\d.]+)(.*)$/, function (m) { return ['t-statistic', 'This says whether a result is more than luck. Ours is ' + m[1].replace('−', '-') + '. You usually need beyond ±2, so ' + (n(m[1]) >= 2 ? 'this profit is strong evidence.' : n(m[1]) <= -2 ? 'this loss is strong evidence, not bad luck.' : 'this result is not proven.')]; }],
    [/^Not statistically significant t-statistic ([−+-]?[\d.]+)/, function (m) { return ['Could it be luck?', 'The t-statistic is ' + m[1].replace('−', '-') + ', below the usual bar of about 2. With so few trades, this result could easily be luck.']; }],
    [/^(Clean test|Training|Test year|After the test year) (.+?) ([−+]₹[\d,]+|No trades|Not listed yet|Loading…|Did not load) ?(.*)$/, function (m) { return [m[1], m[2].charAt(0).toUpperCase() + m[2].slice(1) + ': ' + (/₹/.test(m[3]) ? 'this pair ' + money(m[3]) + ' after costs' + (m[4] ? ' (' + m[4] + ').' : '.') : m[3].toLowerCase() + (m[4] ? ', ' + m[4].toLowerCase() : '') + '.')]; }],
    // Signals
    [new RegExp('^' + P + ' · contracts (\\S+) / (\\S+) Quiet: (\\d) of 5 checks failed'), function (m) { return [m[1] + ' vs ' + m[2], m[5] + ' of the 5 checks failed today. All 5 must pass on the same day for a signal, so this pair stays quiet.']; }],
    [/^Check (\d) (Pass|Fail) (Enough history|Extreme gap|Beats costs|Liquidity|Timing) (.+)$/, function (m) { return ['Check ' + m[1] + ': ' + m[3] + ' (' + m[2] + ')', CHECK[m[3]] + ' Today: ' + m[4].split(/\. (?=[A-Z])/)[0].replace(/\.$/, '') + '.']; }],
    [/^Gap from normal ([\d.]+) bps about ₹([\d,]+) per 10 g of pure gold Needed to trade ([\d.]+) bps 2 × ([\d.]+) bps round trip$/, function (m) { var d = n(m[3]) - n(m[1]); return ['Gap vs cost', 'The gap is ' + m[1] + ' bps (about ₹' + m[2] + ' per 10 g). It needs ' + m[3] + ' bps, so it is ' + (d > 0 ? d.toFixed(1) + ' bps short. No trade.' : 'enough.')]; }],
    [/^(Slippage|Commodity transaction tax|Exchange fees|Brokerage|Stamp duty|GST|SEBI fee) (.+) ([\d.]+)$/, function (m) { return [m[1], FEE[m[1]].charAt(0).toUpperCase() + FEE[m[1]].slice(1) + '. Here: ' + m[2] + '. It adds ' + m[3] + ' bps to one round trip.']; }],
    [/^Total round trip ([\d.]+) bps$/, function (m) { return ['Total cost', 'All the fees for buying and selling both legs once: ' + m[1] + ' bps, about ₹' + Math.round(n(m[1]) * 100).toLocaleString('en-IN') + ' on ₹10 lakh.']; }],
    [/^Slippage per order, bps Brokerage per order, ₹ Size of each leg, ₹ lakh$/, function () { return ['Your numbers', 'Type your own slippage, brokerage and trade size. Everything below updates.']; }],
    [/^Our assumption: (.+)$/, function () { return ['Quick presets', 'Shortcuts: our own assumption, perfect fills, a busy market or a thin market. Try them to see how much costs matter.']; }],
    [/^Your round trip ([\d.]+) bps about ₹([\d,]+) on ₹([\d.]+) lakh a leg$/, function (m) { return ['Your round trip', 'With your numbers, buying and selling both legs once costs ' + m[1] + ' bps, about ₹' + m[2] + ' on ₹' + m[3] + ' lakh a leg.']; }],
    [/^Your cost line ([\d.]+) bps (.+)$/, function (m) { return ['Your cost line', 'Twice your round-trip cost, as a safety margin: ' + m[1] + ' bps. A gap must be bigger than this to be worth trading.']; }],
    [/^Pairs above your line today (\d+) of 6 with our ([\d.]+) bps line: (\d+) of 6$/, function (m) { return ['Pairs above your line', 'With your costs, ' + m[1] + ' of 6 pairs would be worth trading today. With our ' + m[2] + ' bps line it is ' + m[3] + ' of 6.']; }],
    [new RegExp('^' + P + ' ([\\d.]+) bps · (short by|above by|over by) ([\\d.]+)$'), function (m) { return [m[1] + ' vs ' + m[2], 'Today\'s gap is ' + m[3] + ' bps. Compared with your cost line it is ' + m[4] + ' ' + m[5] + ' bps' + (m[4] === 'short by' ? ', so not worth trading.' : ', so it would be worth a look.')]; }],
    [/^(Alerts, clean test \d{4}–\d{4}|Alerts, test year|Alerts, training years|Unusual gap, no alert|Ordinary days) (.+?) · median gap ([\d.]+) bps (shrank|grew) ([\d.]+) bps (\d+)% closed at least halfway$/, function (m) { return [m[1], GROUP[m[1].replace(/ \d{4}–\d{4}$/, '')] + ' ' + m[2] + '. The typical gap was ' + m[3] + ' bps; 10 trading days later it had ' + (m[4] === 'shrank' ? 'shrunk' : 'grown') + ' by ' + m[5] + ' bps (one round trip costs 24.4 bps). ' + m[6] + '% closed at least halfway.']; }],
    [/^Signal Held Trade z Outcome Result Period$/, function () { return ['The columns', 'Signal: the day it fired. Held: days in the trade. z: how unusual the gap was. Result: profit or loss after costs.']; }],
    // Backtesting
    [/^Closed during the Jan–Mar 2026 crash Every other trade$/, function () { return ['The two colours', 'Gold bars: trades that closed during the Jan–Mar 2026 gold crash. Grey bars: all the other trades.']; }],
    [/^at (\d+) bps( \(ours\))? ([−+-]₹[\d.]+L) ([−+-]₹[\d.]+L)$/, function (m) { return ['At ' + m[1] + ' bps slippage' + (m[2] ? ' (ours)' : ''), 'Trades that closed during the crash ' + money(m[3]) + '; all other trades ' + money(m[4]) + '. L means lakh (₹1,00,000).']; }],
    [/^(Test year, all trades|Test year, without the crash|Training years) (.+?) ([−+-]₹[\d,]+) 95% range ([−+-]₹[\d,]+) to ([−+-]₹[\d,]+) (\d+)% of resamples above ₹0$/, function (m) { return [m[1], m[2] + ': the result was ' + m[3] + '. Reshuffling these trades 10,000 times, 95% of results fell between ' + m[4] + ' and ' + m[5] + '. ' + m[6] + '% were above zero, so ' + (n(m[6]) >= 95 ? 'it is fairly solid.' : 'we cannot rule out luck.')]; }],
    [/^95% range of resampled results/, function () { return ['How to read the bars', 'Each bar is the range where 95% of the reshuffled results fell. The dot is the real result. A bar crossing ₹0 means it could be a loss.']; }],
    [/^(Five checks: what this site shows|Original study: four checks, no cost line|Five checks \+ training switch \(.+?\)) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+)$/, function (m) { function v(x) { return x === '–' ? 'not tested' : x; } return [m[1].replace(/:.*/, ''), 'Training: ' + v(m[2]) + ' trades, ' + v(m[3]) + '. Test year: ' + v(m[4]) + ' trades, ' + v(m[5]) + '. Outside the crash: ' + v(m[6]) + '. t-statistic: ' + v(m[7]) + ' (needs about 2).']; }],
    [/^Rule Training trades Training result Test-year trades Test-year result Outside the crash t-statistic$/, function () { return ['The columns', 'Each row is one version of the rule, scored on the training years and on the test year. "Outside the crash" leaves out Jan–Mar 2026.']; }],
    [new RegExp('^' + P + ' · (On|Off) (.+)$'), function (m) { return [m[1] + ' vs ' + m[2] + ': ' + m[3], 'Training switch ' + m[3].toLowerCase() + ': ' + m[4].charAt(0).toLowerCase() + m[4].slice(1) + '. A pair is only traded in the test year if it had at least 10 training trades and made money in training.']; }],
    [/^Slippage per order 0 bps/, function () { return ['Slippage', 'Pick how much you lose per order to slippage. Everything below is recalculated.']; }],
    [/^(\d+) bps( \(our assumption\))? (\d+) ([−+-][\d.]+) bps ([−+-][\d.]+) bps ([−+-]₹[\d,]+) (\d+)%$/, function (m) { return ['At ' + m[1] + ' bps slippage', m[3] + ' trades. Average ' + m[4] + ' bps before costs and ' + m[5] + ' bps after. In total they ' + money(m[6]) + '; ' + m[7] + '% won.']; }],
    [/^Slippage per order Trades Before costs After costs Total ₹ Won$/, function () { return ['The columns', 'Each row is the same trades with a different slippage. The more you lose per order, the smaller the profit.']; }],
    [/^(Spread moves \(what we bet on\)|Gold price moves \(leftover exposure\)|Costs and slippage|Result after costs) ([−+-]₹[\d,]+)$/, function (m) { return [m[1].replace(/ \(.*\)/, ''), MONEY[m[1]] + ' Here: ' + m[2] + '.']; }],
    [/^Pair Oct 2023 – Dec 2024 Apr 2025 – Sep 2026 Jan–Mar 2026 crash What happened$/, function () { return ['The columns', 'The usual spread for each pair in three periods. If "normal" moves this much, a fixed average would mislead, so we use a rolling one.']; }],
    [/^Download Data to (.+?) · not live Search(?: Ctrl O| ⌘ O)? \?$/, function (m) { return ['The top bar', 'Download the data, see the date of the latest prices (' + m[1] + '; we add new MCX files by hand, so it is not live), Search to jump to any page (Ctrl O), switch dark or light, and ? for the meaning of words.']; }],
    // Data
    [/^([\d,]+) daily prices (.+)$/, function (m) { return [m[1] + ' prices', 'One official closing price per contract for every trading day since 2011: ' + m[1] + ' in all. ' + m[2]]; }],
    [/^([\d,]+) daily settlements downloaded (.+)$/, function (m) { return ['2004 to 2023', m[1] + ' official MCX daily prices we downloaded for the older contracts. ' + m[2]]; }],
    [/^(\d+) contracts (.+)$/, function (m) { return [m[1] + ' contracts', 'Each month has its own contract for each symbol. We have every one in the period: ' + m[1] + ' in total.']; }],
    [/^(\d+) trading days (.+)$/, function (m) { return [m[1] + ' trading days', 'Days when MCX was open: ' + m[2]]; }],
    [/^0 mismatches (.+)$/, function () { return ['0 mismatches', 'Two checks, row by row: our cleaned data against the raw MCX files, and our download against a second copy of the same MCX prices. Not a single number differs.']; }],
    [/^(\d+) days with no trades removed/, function (m) { return [m[1] + ' days removed', 'On these days a contract had zero trades, so its "price" was not real. We left them out.']; }],
    [/^(\d+) thin days flagged/, function (m) { return [m[1] + ' thin days', 'Very little trading on these days. We take no new signals then, and assume 3× slippage if a trade is already open.']; }],
    [/^(\d+) weekend sessions kept (.+)$/, function (m) { return [m[1] + ' weekend sessions', 'MCX sometimes opens at the weekend: every Saturday until early 2014, and later only for Diwali Muhurat and Union Budget days. Those were real trading days, so we kept them. ' + m[2]]; }],
    [/^([1-8]) (Load & Validate|Normalize|Implied Carry|Pair Construction|Point-in-Time z-scores|One rule: five checks|Walk-Forward Test|Train\/test split and historical holdout|Costs & Attribution)( .*)?$/, function (m) { return ['Step ' + m[1] + ': ' + m[2], STEP[m[1]]]; }],
    [/^(GOLD\w+) (\d+ \w+ \d{4}) (\d+ \w+ \d{4}) to (\d+ \w+ \d{4}) (\d+) (\d+ \w+ \d{4}) to (\d+ \w+ \d{4})$/, function (m) { return ['One download', 'The ' + m[1] + ' contract that expired on ' + m[2] + '. We asked MCX for ' + m[3] + ' to ' + m[4] + ' and got ' + m[5] + ' daily prices, from ' + m[6] + ' to ' + m[7] + '.']; }],
    [/^Contract Expiry Requested range Rows First to last trading day$/, function () { return ['The columns', 'One row per file we downloaded from MCX: which contract, what dates we asked for, and how many daily prices came back.']; }]
  ];
  function findItem(el) {
    var t = (el.innerText || '').replace(/\s+/g, ' ').trim();
    if (!t && el.getAttribute && el.getAttribute('role') === 'img') t = el.getAttribute('aria-label') || '';
    if (!t || t.length > 700) return null;
    for (var i = 0; i < ITEMS.length; i++) {
      var m = t.match(ITEMS[i][0]);
      if (m) { try { var r = ITEMS[i][1](m, el); if (r && r[1]) return { el: el, title: r[0], text: r[1] }; } catch (err) { return null; } }
    }
    return null;
  }

  var GOLDIE = '<svg viewBox="0 0 48 40" width="40" height="34" aria-hidden="true"><path d="M6 14L9 5H35L38 14Z" fill="#E5B04A"/><path d="M12 33L15 24H41L44 33Z" fill="#B98428"/>' +
    '<circle cx="18" cy="10" r="3.2" fill="#fff"/><circle cx="26" cy="10" r="3.2" fill="#fff"/><circle cx="18.8" cy="10.4" r="1.5" fill="#1B1305"/><circle cx="26.8" cy="10.4" r="1.5" fill="#1B1305"/></svg>';

  var css = '' +
    '.xp-x:focus-visible{outline:2px solid var(--grv-gold,#E5B04A);outline-offset:2px}' +
    '#app main{touch-action:manipulation}' +
    '.xp-ring{position:fixed;z-index:45;pointer-events:none;border:2px solid var(--grv-gold,#E5B04A);border-radius:18px;box-shadow:0 0 0 4px rgba(229,176,74,.18);transition:all .15s ease}' +
    '.xp-tip{cursor:pointer;position:fixed;z-index:50;width:min(330px,calc(100vw - 32px));box-sizing:border-box;background:var(--grv-panel,#1B150C);color:var(--grv-fg,#F6ECD8);border:1px solid var(--grv-gold,#E5B04A);border-radius:16px;' +
    'padding:12px 14px 14px;box-shadow:0 18px 50px rgba(18,12,4,.45);font-family:Geist,system-ui,sans-serif;display:flex;gap:10px;align-items:flex-start}' +
    '.xp-tip .xp-body{flex:1;min-width:0}.xp-tip .xp-t{font-weight:600;font-size:15px;color:var(--grv-gold,#E5B04A);margin:2px 0 4px}' +
    '.xp-tip .xp-d{font-size:14px;line-height:1.55;color:var(--grv-fg,#F6ECD8)}' +
    '.xp-x{flex:none;min-width:36px;min-height:36px;border-radius:10px;border:1px solid var(--grv-line,#3A2D1A);background:var(--grv-raised,#261D11);color:var(--grv-fg,#F6ECD8);font-size:18px;cursor:pointer}' +
    '@media (prefers-reduced-motion:reduce){.xp-ring{transition:none}}';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  // Goldie explains a box when someone double-clicks it (double-taps on a phone). No mode to switch on.
  var ring = null, tip = null, shownEl = null, closedAt = 0, shownAt = 0;
  function clearTip() { if (tip) { tip.remove(); tip = null; } if (ring) { ring.remove(); ring = null; } shownEl = null; }

  function find(el) {
    var main = document.querySelector('#app main');
    if (!main || !el || !main.contains(el)) return null;
    // 1) The exact item (row, card, number) under the pointer, with its own numbers
    for (var e = el; e && e !== main; e = e.parentElement) { var item = findItem(e); if (item) return item; }
    // 2) Otherwise the note for the section it sits in
    for (; el && el !== document.body; el = el.parentElement) {
      if (main && !main.contains(el)) return null;
      var txt = (el.innerText || '').trim().slice(0, 200);
      if (!txt) continue;
      for (var i = 0; i < NOTES.length; i++) if (NOTES[i][0].test(txt)) return { el: el, title: NOTES[i][1], text: NOTES[i][2] };
      if (el === main) break;
    }
    return null;
  }

  function show(hit, x, y) {
    clearTip();
    shownEl = hit.el; shownAt = Date.now();
    var r = hit.el.getBoundingClientRect();
    ring = document.createElement('div'); ring.className = 'xp-ring';
    ring.style.left = (r.left - 4) + 'px'; ring.style.top = (r.top - 4) + 'px';
    ring.style.width = (r.width + 8) + 'px'; ring.style.height = (r.height + 8) + 'px';
    document.body.appendChild(ring);
    tip = document.createElement('div'); tip.className = 'xp-tip'; tip.setAttribute('role', 'dialog'); tip.setAttribute('aria-live', 'polite');
    tip.setAttribute('aria-label', hit.title);
    tip.innerHTML = GOLDIE + '<div class="xp-body"><div class="xp-t"></div><div class="xp-d"></div></div><button type="button" class="xp-x" aria-label="Close (or tap anywhere on this bubble)">×</button>';
    tip.querySelector('.xp-t').textContent = hit.title;
    tip.querySelector('.xp-d').textContent = hit.text;
    document.body.appendChild(tip);
    var w = tip.offsetWidth, h = tip.offsetHeight, vw = innerWidth, vh = innerHeight;
    var left = Math.min(Math.max(16, x + 14), vw - w - 16);
    var top = y + 18 + h > vh - 16 ? y - h - 18 : y + 18;
    top = Math.min(Math.max(16, top), vh - h - 16);
    tip.style.left = left + 'px'; tip.style.top = top + 'px';
  }

  var SKIP = 'a, button, input, select, textarea, label, [role="slider"], [data-grv], .gl-back, .km-back, .km-tip';
  function explainAt(target, x, y) {
    if (!target || !target.closest || target.closest(SKIP)) return false;
    if (Date.now() - closedAt < 600) return false;       // 2nd click of a double-click on the bubble
    if (Date.now() - shownAt < 250) return true;         // phone: our double-tap and the browser's dblclick
    var hit = find(target);
    if (!hit) return false;
    try { var sel = getSelection(); if (sel) sel.removeAllRanges(); } catch (err) {}
    show(hit, x, y);
    return true;
  }

  // Stop the browser selecting a word when someone double-clicks a box
  document.addEventListener('mousedown', function (e) {
    if (e.detail > 1 && !e.target.closest(SKIP) && find(e.target)) e.preventDefault();
  }, true);
  document.addEventListener('dblclick', function (e) {
    if (explainAt(e.target, e.clientX, e.clientY)) { e.preventDefault(); e.stopPropagation(); }
  }, true);
  // Double-tap on touch screens (not every phone browser sends dblclick)
  var lastTap = { t: 0, x: 0, y: 0 };
  document.addEventListener('pointerup', function (e) {
    if (e.pointerType !== 'touch') return;
    var now = Date.now();
    if (now - lastTap.t < 350 && Math.abs(e.clientX - lastTap.x) < 30 && Math.abs(e.clientY - lastTap.y) < 30) {
      lastTap.t = 0;
      if (explainAt(e.target, e.clientX, e.clientY)) e.preventDefault();
    } else lastTap = { t: now, x: e.clientX, y: e.clientY };
  }, true);

  // One click on the bubble closes it; a click anywhere else also closes it but still does its normal job
  document.addEventListener('click', function (e) {
    if (!tip) return;
    if (tip.contains(e.target)) { e.preventDefault(); e.stopPropagation(); clearTip(); closedAt = Date.now(); return; }
    if (Date.now() - shownAt > 250) clearTip();
  }, true);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && tip) clearTip(); });
  window.addEventListener('scroll', clearTip, { passive: true });
  window.addEventListener('hashchange', clearTip);
  window.GRVExplain = { show: show, clear: clearTip, notes: NOTES, items: ITEMS, find: find };
})();
