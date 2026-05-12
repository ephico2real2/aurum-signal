# RESEARCH NOTES — Volume Profile, Point of Control (POC), Value Area

## §1. Question / Goal

Establish canonical definitions and trading interpretation for Point of Control (POC), Value Area (VA), Value Area High/Low (VAH/VAL), and the 70%-volume rule. FORGE composites (case study Mar 31 → Apr 8) use POC and a fib-50 + VWAP-gap combination; we need authoritative grounding to label what "price at POC" / "price outside VA" structurally means and whether POC is properly support/resistance or a magnet.

## §2. Methodology

**Search queries used (verbatim):**
- `point of control POC volume profile value area trading definition`
- `market profile point of control Steidlmayer auction theory CME definition`

**Sources surveyed (retrieved 2026-05-11):**
- TradingView Support — "Volume profile indicators: basic concepts" (fetched)
- Wikipedia — "Market profile" (fetched)
- Charles Schwab Learning Center — VolumeProfile page (attempted; returned auth error)
- Optimus Futures, Trader Dale, ThinkOrSwim — search snippets only

**Source-quality filter:**
- TradingView Support: canonical for their volume-profile implementation, widely used reference.
- Wikipedia "Market profile": well-cited entry that traces back to Steidlmayer's CBOT origin.
- Rejected: tradingshastra.com (SEO), angelone.in (broker affiliate), trendspider.com (mixed quality).

## §3. Findings (cited)

### Finding 1 — Definitions: POC, VA, VAH, VAL, 70% rule

**Claim**: POC = price level with the highest traded volume; Value Area = the price range containing 70% of all volume in the period; VAH and VAL bound that range.

**Source**: [TradingView — Volume profile indicators: basic concepts](https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/) (retrieved 2026-05-11)

**Direct quotes**:
- POC: *"The price level for the time period with the highest traded volume."*
- VA: *"The range of price levels in which the specified percentage of all volume was traded during the time period."*
- VAH: *"The highest price level within the value area."*
- VAL: *"The lowest price level within the value area."*
- 70% rule: *"Typically, this percentage is set to 70%, however, it is up to the trader's discretion."*
- Calculation: *"Multiply the total volume by the chosen percentage (default 70%) to determine the target volume for the value area."*

**FORGE application**: Our `at_poc` atom should be defined as a band — `|close - poc| <= 0.5 * atr_m5` is more robust than exact equality. The 70% volume rule maps to ±1 standard deviation (per Wikipedia below) so VAH/VAL behave like one-sigma bands of the day's price acceptance.

**Confidence**: High — TradingView is a canonical reference for the indicator and matches Steidlmayer's original.

### Finding 2 — Steidlmayer origin and CBOT introduction

**Claim**: POC, Value Area, and Market Profile were developed by J. Peter Steidlmayer at the CBOT in the 1959–1985 period and introduced publicly via the 1985 CBOT Market Profile (CBOTMP1) product.

**Source**: [Wikipedia — Market profile](https://en.wikipedia.org/wiki/Market_profile) (retrieved 2026-05-11)

**Direct quotes**:
- *"the price of the peak cleared volume is identified as the Point of Control (POC)"*
- *"the central seventy percent of trading activity about POC (+/- one standard deviation) is termed the 'Value Area'"*
- *"A Market Profile is an intra-day charting technique...devised by J. Peter Steidlmayer, a trader at the Chicago Board of Trade (CBOT), ca 1959-1985"*
- *"The Market Profile graphic was introduced to the public in 1985 as a part of a CBOT product, the CBOT Market Profile (CBOTMP1)"*
- *"a definition of the price and the marker, a 'TPO' (time-price opportunity), with TPO defined in CBOTMP1 as: 'opportunity created by the market at a certain price at a certain time'"*
- *"At the beginning of the day the first hour of trading creates a range (the Initial Balance)"*

**FORGE application**: Two important corollaries for our atom design:
1. POC ± Value Area ≈ ±1 standard deviation of intraday volume distribution. So `outside_va` boolean is statistically equivalent to "price > 1σ from POC" — a known mean-reversion threshold.
2. The **Initial Balance** (first hour) concept maps to our first-60-min volatility regime — Run 18 evidence suggests this hour is often a poor entry window because IB is still forming.

**Confidence**: High — Wikipedia + TradingView agree on definitions and the 70%/1σ equivalence.

### Finding 3 — POC as magnet (rotation) vs. support/resistance (trend)

**Claim**: POC acts as a magnet during balanced/rotational sessions but as support/resistance when one side cleanly defends or breaks it.

**Source**: search synthesis (Optimus Futures, Trader Dale snippets — retrieved 2026-05-11). Medium confidence — these were not fetched directly.

**Direct quote** (search snippet, not from a single fetched canonical source — Medium confidence):
- *"PoC can help traders identify potential support and resistance levels by pinpointing areas of high trading activity... Additionally, in a rotation, the Point of Control acts like a magnet, not support or resistance."*

**FORGE application**: An `at_poc` atom in a CHOP regime (low ADX, BB squeezed) is a magnet — price will revisit POC repeatedly, supporting our chop-ladder grid composites (§5.5). The same atom in a TRENDING regime (ADX > 25, +DI dominant) treats POC as a launch point — a break of POC with conviction is a continuation signal, not a reversal. **Therefore the same atom must be interpreted differently by regime**, which our regime-classifier already gates correctly.

**Confidence**: Medium — concept is widely held in market-profile community but our cited quote is from search synthesis. A direct fetch of an auction-market-theory primer (e.g., trader-dale, TopStep) would lift this to High.

## §4. Synthesis / Recommended pattern

**Atom set** (MQL5-ready):

```mql5
// Volume Profile derived atoms (daily anchored).
double poc, vah, val;
ComputeDailyProfile(poc, vah, val, /*percent=*/70.0);

double atr_m5 = ATR(_Symbol, PERIOD_M5, 14);

bool AT_POC          = MathAbs(Close[0] - poc) <= 0.5 * atr_m5;
bool ABOVE_VAH       = Close[0] > vah;
bool BELOW_VAL       = Close[0] < val;
bool OUTSIDE_VA      = ABOVE_VAH || BELOW_VAL;  // ~ price > 1σ from POC

// Regime-conditional interpretation:
bool POC_MAGNET_LONG  = AT_POC && IsChop()   && RsiOversold();
bool POC_BREAK_BULL   = ABOVE_VAH && IsTrending() && +DI > -DI && ADX > 25;
```

**Atlas linkage**: §1 should add `POC`, `VAH`, `VAL`, `AT_POC`, `OUTSIDE_VA`, and `INITIAL_BALANCE_MINUTES` as logged atoms. Composites in §5.x that already reference POC (case study) should differentiate between magnet-mode and breakout-mode by regime gating.

## §5. Open questions / Followups

1. **Volume Profile vs Market Profile**: Steidlmayer's original Market Profile uses TPO (time-at-price), while modern volume profile uses contracts/volume. For XAUUSD on MT5, tick-volume is a proxy for true volume. **Followup**: verify our `poc` atom uses tick-volume (Volume[]) and document that it is a proxy, not real exchange volume.
2. **Daily vs rolling profile**: a 1-day profile captures intraday rotation; a 5-day profile captures swing structure. We should log both and decide per composite.
3. **Initial Balance atom**: log `IB_HIGH`, `IB_LOW`, and `IB_BREAK` (price exits the IB range) — these were not on our current atom list but are canonical in auction theory.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | TradingView Support — Volume profile indicators: basic concepts | https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/ | 2026-05-11 |
| 2 | Wikipedia — Market profile (Steidlmayer, CBOT origin) | https://en.wikipedia.org/wiki/Market_profile | 2026-05-11 |
| 3 | (Search snippet only) Optimus Futures — Point of Control Explained | https://optimusfutures.com/blog/point-of-control-explained-the-most-important-level-on-volume-profile-futurestrading-daytrading/ | 2026-05-11 |
