# RESEARCH NOTES — Bollinger Band Squeeze / BandWidth

## §1. Question / Goal

Establish canonical definitions for the Bollinger Band Squeeze, BandWidth (BBW) thresholds, John Bollinger's own framing, and how the squeeze relates to volatility regime detection. FORGE uses BB width as a chop-vs-trend regime input (§5.x); we need third-party validation that our squeeze threshold (currently relative percentile of recent BBW) matches the canonical "near six-month low" rule.

## §2. Methodology

**Search queries used (verbatim):**
- `Bollinger Band squeeze BBWidth definition John Bollinger volatility expansion`

**Sources surveyed (retrieved 2026-05-11):**
- StockCharts ChartSchool — "Bollinger Band Squeeze" (fetched)
- StockCharts ChartSchool — "Bollinger BandWidth" (fetched)
- BollingerBands.com (John Bollinger's official site) — "Bollinger Band Rules" (fetched)
- TradingView Support — "Bollinger BandWidth (BBW)" (search snippet)

**Source-quality filter:**
- John Bollinger's own site (BollingerBands.com) is the primary canonical source.
- StockCharts ChartSchool corroborates with practical implementation.
- TradingView referenced for cross-validation.

## §3. Findings (cited)

### Finding 1 — Squeeze definition (canonical, from John Bollinger)

**Claim**: The Squeeze is the most popular use of BandWidth and identifies a period when volatility has fallen to a low level (bands have narrowed) before an expected expansion.

**Source**: [BollingerBands.com — Bollinger Band Rules](https://www.bollingerbands.com/bollinger-band-rules) (retrieved 2026-05-11)

**Direct quotes**:
- *"BandWidth has many uses. Its most popular use is to identify 'The Squeeze'"*
- *"BandWidth tells us how wide the Bollinger Bands are. The raw width is normalized using the middle band."*
- *"Tags of the bands are just that, tags not signals. A tag of the upper Bollinger Band is NOT in-and-of-itself a sell signal. A tag of the lower Bollinger Band is NOT in-and-of-itself a buy signal."*
- *"Bollinger Bands can be used in pattern recognition to define/clarify pure price patterns such as 'M' tops and 'W' bottoms, momentum shifts, etc."*

**FORGE application**: This is the primary author confirming the squeeze concept. Critically, the "tags are not signals" quote validates our composite-design rule that a BB touch must always be ANDed with another atom (RSI, divergence, structure) — never used standalone. The M-top/W-bottom rule is a canonical Bollinger pattern we could log as derived atoms.

**Confidence**: High — direct from John Bollinger.

### Finding 2 — Squeeze operational definition (StockCharts)

**Claim**: The Squeeze occurs when bands narrow due to decreased volatility; BandWidth should be near the low end of its six-month range; ~4% of price is a narrowness threshold.

**Source**: [StockCharts ChartSchool — Bollinger Band Squeeze](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/bollinger-band-squeeze) (retrieved 2026-05-11)

**Direct quotes**:
- *"A condition that occurs when the Bollinger Bands narrow due to decreased volatility."*
- *"Ideally, BandWidth should be near the low end of its six-month range."*
- *"Periods of low volatility are often followed by periods of high volatility. Therefore, a volatility contraction or narrowing of the bands can foreshadow a significant advance or decline."*
- *"An upside band break is bullish, while a downside band break is bearish."*
- *"narrowing bands do not provide any directional clues"*

**FORGE application**: Two crucial design rules emerge:
1. **Squeeze threshold should be relative, not absolute** — "near low end of 6-month range" means we should compute BBW percentile over the last ~180 days, not hard-code a single number. Our current implementation likely needs auditing.
2. **Squeeze is directional-agnostic** — BBW squeeze alone does NOT predict break direction. Our composite must NOT include `BBW_SQUEEZE` as a directional gate; only as a regime classifier ("expansion expected, direction TBD").

**Confidence**: High — corroborated by BollingerBands.com and StockCharts BandWidth page.

### Finding 3 — BandWidth formula (relative percentage)

**Claim**: BandWidth = (Upper Band − Lower Band) / Middle Band * 100; it is a percentage of price.

**Source**: [StockCharts ChartSchool — Bollinger BandWidth](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/bollinger-bandwidth) (retrieved 2026-05-11)

**Direct quotes**:
- *"The Bollinger BandWidth measures the percentage difference between the upper and lower band."*
- *"The Squeeze occurs when volatility falls to a low level, as evidenced by the narrowing bands."*
- *"An eight- to 12-month chart will show BandWidth highs and lows over a significant timeframe."*
- *"Narrow BandWidth is relative. BandWidth values should be gauged relative to prior BandWidth values over a period of time."*

**FORGE application**: BBW is already normalized by the middle band, so it is comparable across price levels (gold at $1900 and $2400 produce comparable BBW values). We should use a percentile-based threshold:
- `BBW_PCTL_180D < 10` → tight squeeze (bottom decile of last 180 days)
- `BBW_PCTL_180D > 90` → expanded (top decile, mean-reversion candidate)

**Confidence**: High — two StockCharts sources agree, and the formula is well-defined.

### Finding 4 — Low volatility precedes high volatility (Bollinger's law)

**Claim**: A documented characteristic of Bollinger Bands is that quiet markets precede volatile ones; this is the basis for the squeeze.

**Source**: [StockCharts ChartSchool — Bollinger Band Squeeze](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/bollinger-band-squeeze) (retrieved 2026-05-11). Note: BollingerBands.com page did not contain this quote in the section fetched.

**Direct quote**:
- *"Periods of low volatility are often followed by periods of high volatility."*

**FORGE application**: This is the canonical justification for treating a sustained squeeze as a pre-breakout signal. For FORGE, after detecting `BBW_PCTL_180D < 10` for N consecutive bars, the next breakout atom (band break with volume confirmation) gets elevated priority.

**Confidence**: High — directly quoted from canonical reference; widely repeated in Bollinger's own materials.

## §4. Synthesis / Recommended pattern

**Atom set** (MQL5-ready):

```mql5
// BandWidth, percentile-based squeeze detection.
double bbw = (UpperBand - LowerBand) / MiddleBand * 100.0;
double bbw_pctl_180d = PercentRank(bbw, 180 * BarsPerDay);  // ~6 months

bool BBW_SQUEEZE     = bbw_pctl_180d < 10.0;  // tight band
bool BBW_EXPANDED    = bbw_pctl_180d > 90.0;  // widened band, mean-reversion candidate
bool BBW_BREAKOUT_UP   = BBW_SQUEEZE_PRIOR && Close[0] > UpperBand;
bool BBW_BREAKOUT_DOWN = BBW_SQUEEZE_PRIOR && Close[0] < LowerBand;
```

**Atlas linkage**: §1 should list `BBW`, `BBW_PCTL_180D`, `BBW_SQUEEZE`, `BBW_EXPANDED`. §8 glossary should state: "BBW squeeze is direction-agnostic. Never use BBW squeeze as a directional entry gate; it is a regime indicator only. Direction comes from confirmed band-break + volume."

## §5. Open questions / Followups

1. **Lookback window for percentile**: BollingerBands.com / StockCharts cite 6 months as the canonical reference. For XAUUSD on M5, this is ~17,000 bars — feasible but memory-heavy. Alternative: 30 days (~8,640 bars) may suffice given gold's faster regime turnover.
2. **W-bottom / M-top detection**: Bollinger's own pattern recognition for `M_TOP` and `W_BOTTOM` is not in our atom list. Should be added as a derived atom; canonical rule (per Bollinger's book "Bollinger on Bollinger Bands") uses lower-band tag + non-confirming RSI for W-bottom.
3. **Threshold tuning**: 10/90 percentiles are convention but not gold-specific. Should be empirically tuned against our Apr 1–8 dataset to find the percentile that best separates chop from trend regimes.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | BollingerBands.com — Bollinger Band Rules (John Bollinger's site) | https://www.bollingerbands.com/bollinger-band-rules | 2026-05-11 |
| 2 | StockCharts ChartSchool — Bollinger Band Squeeze | https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/bollinger-band-squeeze | 2026-05-11 |
| 3 | StockCharts ChartSchool — Bollinger BandWidth | https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/bollinger-bandwidth | 2026-05-11 |
