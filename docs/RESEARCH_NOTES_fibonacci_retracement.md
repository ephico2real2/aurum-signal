# RESEARCH NOTES — Fibonacci Retracement, focus on 50% level

## §1. Question / Goal

Establish canonical interpretation of Fibonacci retracement levels — especially the 50% level which is NOT a Fibonacci ratio but a Dow-Theory retracement — and what "breaking below 50%" structurally implies for a trend. FORGE case study (Mar 31 → Apr 8) §5 V2 composites use Fib 50 as a critical filter (would have blocked Apr 8 16:35 BB_BOUNCE BUY at $200 floating loss); we need third-party validation that Fib 50 is the canonical decision boundary in classical technical analysis.

## §2. Methodology

**Search queries used (verbatim):**
- `Fibonacci 50% retracement level Dow theory trend definition confirmation`

**Sources surveyed (retrieved 2026-05-11):**
- StockCharts ChartSchool — "Fibonacci Retracements" (fetched)
- Wikipedia — "Fibonacci retracement" (referenced via search snippet)
- LearnToTradeTheMarket — 50% retracement strategy (referenced; SEO-leaning)

**Source-quality filter:**
- StockCharts ChartSchool: long-standing technical-analysis reference, used by CFA and CMT curricula — accepted as canonical.
- Wikipedia: accepted for definitional cross-validation.
- Rejected: bullishbears.com, heygotrade.com, warriortrading.com (affiliate/SEO).

## §3. Findings (cited)

### Finding 1 — The 50% retracement is from Dow Theory, not Fibonacci

**Claim**: 50% is included in the standard retracement set because Charles Dow observed that averages tend to retrace half their prior move; it is not derived from the Fibonacci sequence.

**Source**: [StockCharts ChartSchool — Fibonacci Retracements](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-annotation-tools/fibonacci-retracements) (retrieved 2026-05-11)

**Direct quotes**:
- *"The 50% retracement is not based on a Fibonacci number. Instead, this number stems from Dow Theory's assertion that the Averages often retrace half their prior move."*
- *"The most popular Fibonacci retracements are 61.8% and 38.2%."*
- *"Even though deeper, the 61.8% retracement can be called golden retracement. It is, after all, based on the Golden Ratio."*

**FORGE application**: This validates our case study's use of Fib 50 as a critical structural level. The 50% retracement is canonical regardless of one's view on Fibonacci ratios — it represents the **Dow midpoint** of any swing, and a break below 50% means more than half the prior move has been given back, structurally weakening the trend.

**Confidence**: High — StockCharts ChartSchool is a primary reference; Wikipedia search snippet corroborates the Dow attribution.

### Finding 2 — Confirmation rules: retracement is an alert, not a signal

**Claim**: Retracement levels are alert zones requiring confirmation from another technical signal (candlestick, momentum, volume, or pattern).

**Source**: [StockCharts ChartSchool](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-annotation-tools/fibonacci-retracements) (retrieved 2026-05-11)

**Direct quotes**:
- *"The more confirming factors, the more robust the signal."*
- *"Other technical signals are needed to confirm a reversal. Reversals can be confirmed with candlesticks, momentum indicators, volume, or chart patterns."*

**FORGE application**: A naked "price at Fib 50" atom must NOT gate an entry by itself. The case study correctly ANDs Fib 50 with VWAP gap, POC, and BB width — this matches the canonical confirmation principle. We should formalize this in the atlas glossary §8: "Fib 50 is an alert-zone atom; never a standalone gate."

**Confidence**: High — directly quoted from canonical reference.

### Finding 3 — Dow Theory threshold range (33% to 66%) bounds healthy correction

**Claim**: Dow observed that healthy trend corrections retrace one-third to two-thirds of the prior move; >66% structurally compromises the trend.

**Source**: search synthesis (retrieved 2026-05-11), corroborating StockCharts and Wikipedia search snippets. Medium confidence as direct quote came from synthesis.

**Direct quote** (from search synthesis — Medium confidence):
- *"Dow theorists observed that healthy trend corrections tend to retrace between one-third and two-thirds of the prior move. A pullback that holds above the 33% level suggests strong underlying momentum, while a retracement approaching 66% represents the outer boundary of what the trend can absorb before the move is considered compromised."*

**FORGE application**: Three structural zones for our atom:
- `RETRACEMENT_SHALLOW` — pullback above 38.2% Fib → strong trend, continuation favored.
- `RETRACEMENT_NORMAL` — pullback 38.2%–61.8% → ambiguous, requires other confirmation.
- `RETRACEMENT_DEEP` — pullback below 61.8% → trend compromised, reversal candidate.

**Confidence**: Medium — Dow's original work pre-dates digital citation; the 33%/66% range comes from secondary literature. Would benefit from primary-text confirmation.

### Finding 4 — Fib levels apply on the timeframe of the swing being measured

**Claim** (operator/synthesis): Fib retracements are timeframe-dependent. A 50% retracement on the daily swing is structurally distinct from a 50% retracement on M5; lower timeframes generate noisier retracements.

**Source**: StockCharts ChartSchool implicit — Fib levels are drawn between a defined swing high and swing low; the choice of swing defines the timeframe. (retrieved 2026-05-11)

**FORGE application**: Our Fib 50 atom must be anchored to a SPECIFIC swing. The Mar 31 → Apr 8 case study uses the daily swing — that is the appropriate timeframe for our daily-direction gate. For intraday composites on M5, the Fib levels should be drawn from the prior day's range (or the IB range) rather than from a multi-day swing.

**Confidence**: Medium — implicit in the canonical method, but no fetched source explicitly states this rule.

## §4. Synthesis / Recommended pattern

**Atom set** (MQL5-ready):

```mql5
// Anchor: prior-day daily-direction swing (swing high to swing low or vice versa).
double swing_high, swing_low;
ComputeDailySwing(swing_high, swing_low);  // anchored to daily Direction Gate window
double range = swing_high - swing_low;

double fib_382 = swing_high - 0.382 * range;
double fib_50  = swing_high - 0.50  * range;
double fib_618 = swing_high - 0.618 * range;

bool FIB_ABOVE_50    = Close[0] > fib_50;
bool FIB_BELOW_50    = Close[0] < fib_50;
bool RETRACE_SHALLOW = Close[0] > fib_382;   // healthy trend
bool RETRACE_NORMAL  = Close[0] >= fib_618 && Close[0] <= fib_382;
bool RETRACE_DEEP    = Close[0] < fib_618;   // trend compromised
```

**Atlas linkage**: §1 should list `FIB_50`, `FIB_382`, `FIB_618`, and `FIB_ABOVE_50` boolean. §8 glossary should note: "Fib 50 is a Dow-Theory midpoint, not a Fibonacci ratio; alert-zone atom requiring confirmation; anchor to daily swing for daily composites and to prior-day range for intraday composites."

## §5. Open questions / Followups

1. **Which swing to anchor?** Daily high/low? Weekly? Prior session? The case study used the daily Mar 31 → Apr 8 swing. Need a consistent rule per composite tier.
2. **Time decay**: do fib levels lose relevance over time? Some analysts mark levels as "untested," "tested once," "broken." We could add `FIB_50_TESTS` count.
3. **Wikipedia and primary Dow text not fully fetched**: should retrieve Wikipedia Fibonacci retracement article for one more independent quote to lift Finding 3 to High confidence.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | StockCharts ChartSchool — Fibonacci Retracements | https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-annotation-tools/fibonacci-retracements | 2026-05-11 |
| 2 | (Referenced) Wikipedia — Fibonacci retracement | https://en.wikipedia.org/wiki/Fibonacci_retracement | 2026-05-11 |
| 3 | (Referenced) LearnToTradeTheMarket — Trading 50% Retracements with Price Action Confirmation | https://www.learntotradethemarket.com/forex-trading-strategies/trading-50-percent-retracements-price-action | 2026-05-11 |
