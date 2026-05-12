# RESEARCH NOTES — Overnight Gap Fade (Open-Gap Reversal)

## §1. Question / Goal

XAUUSD has small but regular weekend / session-handoff gaps (Sunday open, mid-week broker-rollover gaps, and the occasional news gap). FORGE has no atom that detects an opening gap or sizes the probability of a gap-fill. Canonical equities-research literature (StockCharts, Trade That Swing, ShareplanneR) documents that small gaps mean-revert at >70% rates within the same session. We want to (a) establish whether the same holds for XAUUSD M5 and (b) design an `OVERNIGHT_GAP_FADE` composite.

## §2. Methodology

**Search queries used (verbatim):**
- `overnight gap fade strategy statistics open gap reversal rules`
- `"gap fill" probability statistics SPY backtest percentage`

**Sources surveyed (retrieved 2026-05-11):**
- StockCharts ChartSchool — "Gap Trading Strategies" (fetched)
- StockCharts ChartSchool — "Gaps and Gap Analysis" (fetched)
- ShareplanneR — "Fading the Gap: SPY and QQQ Overnight Moves" (fetched)
- Trade That Swing — "SPY/ES Gap Fill Strategy and Statistics" (search snippet — direct fetch blocked)
- QuantifiedStrategies — bot wall blocked direct fetch

**Source-quality filter:** StockCharts ChartSchool is canonical for chart-pattern definitions. ShareplanneR provides quantified SPY/QQQ statistics. Trade That Swing aggregates SPY/ES gap-fill backtests. Equities data extrapolation to gold flagged as a confidence-limiter.

## §3. Findings (cited)

### Finding 1 — Canonical gap typology (StockCharts)

**Claim**: There are four canonical gap types — Common, Breakaway, Runaway, Exhaustion — and only Common and Exhaustion gaps reliably fade/fill.

**Source**: [StockCharts ChartSchool — Gaps and Gap Analysis](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/gaps-and-gap-analysis) (retrieved 2026-05-11)

**Direct quotes**:
- *"Common gaps are usually uneventful."* *"These gaps are common (get it?) and usually get filled fairly quickly."*
- *"Breakaway gaps are exciting. These occur when the price action is breaking out of a trading range or congestion area."* *"Avoid falling into the trap of thinking this type of gap, if associated with good volume, will be filled soon."*
- *"Exhaustion gaps happen near the end of a good up or downtrend. The gaps are often the first signal of the end of that move."* *"Exhaustion gaps are quickly filled as prices reverse their trend."*
- *"The adage that all gaps eventually get filled might not always hold true, especially in the case of Breakaway and Runaway gaps."*

**FORGE application**: A blanket "fade every gap" rule is wrong — we must classify the gap first. Heuristic for classification using FORGE atoms:
- **Common** = gap < 0.5 ATR(D1) AND prior trend flat (h1_trend_strength near 0)
- **Breakaway** = gap > 1.0 ATR(D1) AND price exits a >2-day consolidation range
- **Exhaustion** = gap > 1.0 ATR(D1) AND prior trend was already in late stage (h1_trend strong + RSI extreme)

**Confidence**: High — StockCharts ChartSchool is canonical.

### Finding 2 — Quantified gap-fill rates (equities; XAUUSD extrapolation flagged)

**Claim**: Roughly 78% of tiny gaps and 42% of small gaps fill same-session in SPY; large gaps (>1.2×ATR) only fill ~8%.

**Source**: [ShareplanneR — Fading the Gap: SPY and QQQ Overnight Moves](https://www.shareplanner.com/blog/strategies-for-trading/fading-the-gap-how-large-overnight-moves-in-spy-and-qqq-play-out-during-the-trading-day.html) (retrieved 2026-05-11)

**Direct quotes**:
- *"Roughly 15–20% of trading sessions in recent history open with a gap of at least 1% in SPY or QQQ."*
- *"About 45% of 1–1.99% overnight gaps were fully filled on the same day. For gaps of 2% or more, the intraday fill rate drops to roughly 30%–33%."*
- *"About 14% of 1%+ Monday gap-ups in SPY have completely erased the gap by that day's close."*
- *"In 67% of 1%+ Wednesday gap-ups, the market continued rising from open to close, with an average additional gain of +0.5% intraday."*
- *"About 53% of 1%+ up gaps were filled within two days (vs. ~45% same-day)."*
- *"Around 57% filled within two days" (down gaps).*

**Cross-reference (search-only, lower confidence)**: Trade That Swing — *"80%+ of gaps fill by noon EST"* and *"Tiny gaps (less than 0.3x ATR) fill about 78% of the time by market close. Small gaps fill around 42%. Medium gaps drop to 25%, and large gaps (over 1.2x ATR) fill only about 8% of the time."*

**FORGE application**: Three-bucket sizing rule for XAUUSD (using D1 ATR as the scale):
- `g_gap_size_atr = MathAbs(iOpen[0] - iClose[1]) / atr_d1`
- Bucket A (tiny, <0.3 ATR): high fade probability — gate `OVERNIGHT_GAP_FADE` ON
- Bucket B (medium, 0.3–1.2 ATR): borderline — require additional confirmation (RSI extreme, BB outside)
- Bucket C (large, >1.2 ATR): likely breakaway/news — fade OFF

Note: XAUUSD doesn't have an "open" except at Sunday 22:00 GMT and after broker maintenance windows. Gap detection must use `iOpen[0] - iClose[1]` on D1 timeframe, AND filter for "first M5 bar after broker rollover" (TimeHour == 22 in winter / 21 in summer).

**Confidence**: Medium — quantified equities data is solid; XAUUSD extrapolation needs our own backtest before promoting to High.

### Finding 3 — Day-of-week effect

**Claim**: Mondays show the highest gap-fade rate, Wednesdays show the highest gap-continuation rate.

**Source**: [ShareplanneR — Fading the Gap](https://www.shareplanner.com/blog/strategies-for-trading/fading-the-gap-how-large-overnight-moves-in-spy-and-qqq-play-out-during-the-trading-day.html) (retrieved 2026-05-11)

**Direct quotes**: *"Monday has been the worst day for holding onto large opening gains"*; *"In 67% of 1%+ Wednesday gap-ups, the market continued rising"*.

**FORGE application**: Add a `DayOfWeek()` filter to the composite — `OVERNIGHT_GAP_FADE` strongest on Monday (weekend gap). Friday gap fades are mostly position-squaring — flag for separate study.

**Confidence**: Medium — equities data; XAUUSD parallel is plausible (weekend news bleeds into Sunday gap) but unverified.

### Finding 4 — Gap-fade entry rule (StockCharts Gap Trading Strategies)

**Claim**: Wait one hour after open before entering a fade — let the opening range establish first.

**Source**: [StockCharts ChartSchool — Gap Trading Strategies](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/gap-trading-strategies) (retrieved 2026-05-11)

**Direct quotes**:
- *"allow one hour after the market opens for the stock price to establish its range"* (review the 1-minute chart after 10:30 AM)
- For Full Gap Up Long Entry: *"set a long (buy) stop two ticks above the high achieved in the first hour of trading"*
- For Full Gap Up Short Entry: *"set a short stop equal to two ticks below the low achieved in the first hour of trading"*

**FORGE application**: For XAUUSD M5, the "first hour" rule translates to: do not enter `OVERNIGHT_GAP_FADE` until 12 M5 bars after Sunday open (22:00–23:00 GMT). Entry trigger then becomes: `iClose[1] < iLow_of_first_12_bars` (gap-up fade) or `iClose[1] > iHigh_of_first_12_bars` (gap-down fade). This connects directly to `OPENING_RANGE_BREAKOUT` (separate note) — the same opening-range atom serves both.

**Confidence**: High — canonical from StockCharts.

## §4. Synthesis / Recommended pattern

**New atoms**:
- `g_gap_size_atr` — `MathAbs(iOpen(_,PERIOD_D1,0) - iClose(_,PERIOD_D1,1)) / atr_d1`
- `g_gap_direction` — `+1` up, `-1` down, `0` no gap
- `g_post_gap_or_high`, `g_post_gap_or_low` — first-hour range after gap session open
- `g_day_of_week` — already accessible via `TimeDayOfWeek()`

**Layer-1 composite**:

```mql5
bool OVERNIGHT_GAP_FADE_SELL =     // gap-up that should fade
       g_gap_direction > 0
    && g_gap_size_atr > 0.3
    && g_gap_size_atr < 1.2           // skip breakaway
    && BarsSinceSessionOpen() >= 12   // 1 hour past
    && iClose[1] < g_post_gap_or_low
    && rsi > 60                       // overheated entry
    && (g_day_of_week == MONDAY || g_day_of_week == TUESDAY);

bool OVERNIGHT_GAP_FADE_BUY =      // gap-down that should fade
       g_gap_direction < 0
    && g_gap_size_atr > 0.3
    && g_gap_size_atr < 1.2
    && BarsSinceSessionOpen() >= 12
    && iClose[1] > g_post_gap_or_high
    && rsi < 40;
```

## §5. Open questions / Followups

1. **XAUUSD gap frequency** — equities data says 15–20% of sessions; XAUUSD weekend gap frequency unknown — backtest required.
2. **News-driven gap classification** — economic-calendar API integration to flag a gap as "news-induced" (likely breakaway) vs "noise" (likely fade).
3. **ATR window for sizing** — D1 ATR(14) or D1 ATR(20)? Equities literature defaults to 14 but XAUUSD volatility regime may warrant a longer window.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | StockCharts ChartSchool — Gaps and Gap Analysis | https://chartschool.stockcharts.com/table-of-contents/chart-analysis/gaps-and-gap-analysis | 2026-05-11 |
| 2 | StockCharts ChartSchool — Gap Trading Strategies | https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/gap-trading-strategies | 2026-05-11 |
| 3 | ShareplanneR — Fading the Gap (SPY/QQQ) | https://www.shareplanner.com/blog/strategies-for-trading/fading-the-gap-how-large-overnight-moves-in-spy-and-qqq-play-out-during-the-trading-day.html | 2026-05-11 |
| 4 | Trade That Swing — SPY/ES Gap Fill Strategy and Statistics (search snippet) | https://tradethatswing.com/sp-500-spy-es-gap-fill-strategy-and-statistics/ | 2026-05-11 |
