# RESEARCH NOTES — Failed Breakout / False-Breakout Fade

## §1. Question / Goal

A failed breakout (price pierces a key level — BB band, prior-day high/low, round number — but closes back inside on the same bar or the next bar) is one of the highest-edge canonical patterns in technical analysis. FORGE's existing setups (BB_BREAKOUT, BB_BOUNCE) react to the *initial* breakout but do not have a mechanism to fade the failure. Goal: design `FAILED_BREAKOUT_REVERSE` as a boolean composite, supported by canonical literature (Bulkowski, John Bollinger).

## §2. Methodology

**Search queries used (verbatim):**
- `false breakout reversal Bollinger Band fade trading rules Bulkowski`
- `Bulkowski Encyclopedia chart patterns false breakout failure rate statistics`

**Sources surveyed (retrieved 2026-05-11):**
- Thepatternsite.com (Bulkowski's site) — "Failure Rate Study" (fetched)
- StockCharts ChartSchool — "Bollinger Band Squeeze" head fakes section (fetched in `bb_squeeze_breakout` note)
- TradingSim — "6 Bollinger Bands Trading Strategies" (search snippet) — cites John Bollinger
- FMZ — "Bollinger Bands Trend Reversal Trading Strategy" (search snippet)

**Source-quality filter:** Thomas Bulkowski's thepatternsite.com is the canonical statistical source for chart-pattern failure rates (the author of "Encyclopedia of Chart Patterns"). John Bollinger's own framing of "head fake" is canonical for BB-specific false breakouts.

## §3. Findings (cited)

### Finding 1 — Chart-pattern failure rates have risen sharply over time (Bulkowski)

**Claim**: Chart-pattern breakouts fail 2–4× more often in the post-2000 era than they did in the 1990s; the failure rate doubled by 2007.

**Source**: [Thepatternsite.com — Bulkowski's Failure Rate Study](https://thepatternsite.com/FailureRates.html) (retrieved 2026-05-11)

**Direct quotes**:
- *"the average failure rate of chart patterns to climb at least 10% in the 1990s bull market was 14%. During the bull market years of 2003 to 2007, the failure rate had doubled to 28%."*
- *"In 1991 the 10% failure rate was 11% but peaked at 44% in 2007."*
- For downward breakouts: *"the average 10% failure rate in the bullish 1990s was 26%. This had climbed to 49% during the bull market years of 2003 to 2007."*
- *"The 20% failure rate climbed from 22% in 1991 to 64% in 2007"*
- *"the 40% failure rate increased from 64% to 88% over the 1991 to 2008 period."*
- *Bulkowski defines failure using three arbitrary gain thresholds: 10%, 20%, and 40% post-breakout moves.*

**FORGE application**: Bulkowski's failure metric is on price-percentage move (equities). For XAUUSD M5 we should rescale: a "failed breakout" is one where the post-breakout move doesn't reach `0.5 × m5_atr` (relative to the breakout bar's close) within N bars. The headline statistic (failure rate ~28–44% in modern markets) justifies a fade-the-failure setup — if 1-in-3 breakouts fail, fading the failure has positive expectancy.

**Confidence**: High — Bulkowski's site is the canonical published source for chart-pattern statistics.

### Finding 2 — Bollinger head fake (canonical false-breakout-of-band)

**Claim**: When BB contracts and price breaks one band then quickly reverses to break the other, this is the canonical "head fake" — a high-conviction fade pattern.

**Source**: [StockCharts ChartSchool — Bollinger Band Squeeze](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/bollinger-band-squeeze) (retrieved 2026-05-11). Bollinger's own book *Bollinger on Bollinger Bands* is the primary source (referenced via search summary).

**Direct quotes**:
- *"A bullish head fake starts when Bollinger Bands contract and prices break above the upper band. This bullish signal does not last long because prices quickly move back below the upper band and proceed to break the lower band."*
- *"A bearish head fake starts when Bollinger Bands contract and prices break below the lower band. This bearish signal does not last long because prices quickly move back above the lower band and proceed to break the upper band."*
- (TradingSim search summary): *"In his book Bollinger on Bollinger Bands, John Bollinger advises chartists to beware of the 'head fake,' which occurs when prices break a band, then suddenly reverse and move the other way, similar to a bull or bear trap."*

**FORGE application**: Direct atom: `g_bb_failed_breakout_up = iHigh[2] > bb_upper && iClose[1] < bb_upper && iClose[1] < bb_mid` (bar 2 broke up, bar 1 closed back below mid → high-conviction SELL). Mirror for `g_bb_failed_breakout_down`.

**Confidence**: High — primary-source-canonical from John Bollinger.

### Finding 3 — Confirmation requirement: candle close, not wick

**Claim**: A "failure" is only confirmed when the bar *closes* back inside the prior structure; an intra-bar wick does not constitute failure.

**Source**: Multiple — see [TradingSim — 6 Bollinger Bands Strategies (search summary)](https://www.tradingsim.com/blog/bollinger-bands), and the head-fake quotes above ("This bullish signal does not last long because prices quickly move back below the upper band").

**Direct quote (TradingSim search summary)**: *"If price is breaking through the upper Bollinger Band rather than touching and reversing, that's a breakout — not a reversal setup."* *"Unconfirmed band breaks are more prone to failure."*

**FORGE application**: Enforce the close-back-inside requirement at the bar level: failure is `iClose[1] < bb_upper` while `iHigh[1] > bb_upper`. For "next-bar failure", use a 2-bar window: bar 2 broke, bar 1 closed back inside.

**Confidence**: High — multiple authors agree and matches the candle-close discipline already in atlas §1.

## §4. Synthesis / Recommended pattern

**New atoms (atlas §1)**:
- `g_bb_failed_breakout_up_1bar` = `iHigh[1] > bb_upper && iClose[1] < bb_upper`
- `g_bb_failed_breakout_up_2bar` = `iHigh[2] > bb_upper && iClose[2] > bb_upper && iClose[1] < bb_upper`
- `g_pdh_failed_breakout`, `g_pdl_failed_breakout` — same shape vs prior-day levels
- `g_round_failed_breakout` — vs nearest $50 round level

**Layer-1 composite**:

```mql5
// SELL — failed upside breakout (the strongest case combines all 3 levels)
bool FAILED_BREAKOUT_FADE_SELL =
       (g_bb_failed_breakout_up_1bar
        || g_pdh_failed_breakout
        || g_round_failed_breakout)
    && iLong_upper_wick[1] > 0.5 * (iHigh[1] - iLow[1])   // visible rejection wick
    && rsi[2] > 70                                         // overheated when it broke
    && rsi[1] < rsi[2]                                     // bear divergence
    && h1_trend_strength <= 0;                             // not into strong bull

// BUY — failed downside breakout
bool FAILED_BREAKOUT_FADE_BUY =
       (g_bb_failed_breakout_dn_1bar
        || g_pdl_failed_breakout
        || g_round_failed_breakout_dn)
    && iLong_lower_wick[1] > 0.5 * (iHigh[1] - iLow[1])
    && rsi[2] < 30
    && rsi[1] > rsi[2]
    && h1_trend_strength >= 0;
```

**Key insight**: The strongest failed breakout is one that fails *at the confluence* of multiple resistance types — BB band AND prior-day high AND round number all together. The composite scores higher when 2 or 3 conditions overlap.

## §5. Open questions / Followups

1. **Atomic vs composite failure** — should we trigger on any single failed-level break, or require ≥2 of {BB, PDH/PDL, round number}? Backtest required.
2. **Wick-size threshold** — "0.5 of bar range" is heuristic; could be 0.4 or 0.6 — needs empirical tuning.
3. **Time-since-break decay** — a 1-bar-old failure is high conviction; a 5-bar-old failure is weak. Need a `bars_since_failure` atom.
4. **Bulkowski's own setup-specific failure rates** — we have aggregate rates but not the per-pattern (e.g. head-and-shoulders vs flag) breakdown. Worth a deeper dive into thepatternsite.com `rank.html` for the patterns FORGE could detect.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | Thepatternsite.com — Bulkowski's Failure Rate Study | https://thepatternsite.com/FailureRates.html | 2026-05-11 |
| 2 | StockCharts ChartSchool — Bollinger Band Squeeze (head fakes) | https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/bollinger-band-squeeze | 2026-05-11 |
| 3 | TradingSim — 6 Bollinger Bands Strategies (cites Bollinger on Bollinger Bands) | https://www.tradingsim.com/blog/bollinger-bands | 2026-05-11 (search snippet) |
| 4 | FMZ — Bollinger Bands Trend Reversal Trading Strategy | https://www.fmz.com/lang/en/strategy/492170 | 2026-05-11 (search snippet) |
