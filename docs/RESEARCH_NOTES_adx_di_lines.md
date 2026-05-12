# RESEARCH NOTES — ADX / +DI / −DI (directional movement system)

## §1. Question / Goal

Establish canonical interpretation of the ADX indicator and its component directional indicators (+DI, −DI), the 20/25 trend-strength thresholds, and the strict separation of "trend strength" (ADX) vs "trend direction" (DI balance) — Wilder's intent. FORGE composites use ADX as a regime classifier and DI lines as direction confirmation; we need authoritative grounding before formalizing these gates.

## §2. Methodology

**Search queries used (verbatim):**
- `ADX DI+ DI- directional movement index Wilder trend strength threshold 25`

**Sources surveyed (retrieved 2026-05-11):**
- StockCharts ChartSchool — "Average Directional Index (ADX)" (fetched)
- Fidelity — Average directional index: ADX (referenced via search)
- Wikipedia — "Average directional movement index" (referenced via search)
- TradingView Support — ADX (referenced via search)

**Source-quality filter:**
- StockCharts ChartSchool: primary canonical reference, used in CMT curriculum.
- Fidelity / Wikipedia: cross-validation.
- Rejected: chartguys.com, equiti.com, medium.com authored summaries.

## §3. Findings (cited)

### Finding 1 — ADX measures STRENGTH, not direction

**Claim**: ADX is an undirected magnitude of trend strength. Direction is determined exclusively by the +DI vs −DI relationship.

**Source**: [StockCharts ChartSchool — Average Directional Index (ADX)](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/average-directional-index-adx) (retrieved 2026-05-11)

**Direct quotes**:
- *"it measures the **strength** of the trend (regardless of direction) over time"*
- *"The Average Directional Index (ADX) is used to measure the strength or weakness of a trend, not the actual direction"*

**FORGE application**: This is the canonical rule that an `ADX_STRONG_TREND` atom is NEVER directional by itself. Any composite using ADX must AND it with a DI atom (or another directional indicator) to express direction. We should audit our existing composites to ensure no ADX-only atom is used to gate a directional entry.

**Confidence**: High — direct quote from canonical reference; corroborated by Fidelity and Wikipedia in search snippets.

### Finding 2 — Trend strength thresholds: 20 weak, 25 strong, 20–25 gray zone

**Claim**: ADX < 20 indicates no trend; ADX > 25 indicates a strong trend; 20–25 is a transition/uncertainty zone.

**Source**: [StockCharts ChartSchool — Average Directional Index (ADX)](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/average-directional-index-adx) (retrieved 2026-05-11)

**Direct quotes**:
- *"a strong trend is present when ADX is above 25 and no trend is present when ADX is below 20"*
- *"there is a gray zone between 20 and 25"*
- *"Many technical analysts use 20 as the key level for ADX"*

**FORGE application**: Three regime states for our classifier:
- `ADX_NO_TREND` (ADX < 20) → chop regime; mean-reversion composites preferred.
- `ADX_GRAY` (20 ≤ ADX ≤ 25) → uncertain; reduce position size or skip.
- `ADX_TREND` (ADX > 25) → trend regime; trend-continuation composites preferred.

**Confidence**: High — direct quote; widely used standard threshold.

### Finding 3 — DI relationship determines direction

**Claim**: When +DI > −DI, trend is up; when +DI < −DI, trend is down. The DI cross is the directional signal.

**Source**: [StockCharts ChartSchool — Average Directional Index (ADX)](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/average-directional-index-adx) (retrieved 2026-05-11)

**Direct quotes**:
- *"When +DI is **above** -DI, the trend is up"*
- *"when +DI is **below** -DI, the trend is down"*
- *"the bulls have the edge when +DI is greater than -DI"*
- *"the bears have the edge when -DI is greater"*

**FORGE application**: Define directional atoms:
- `DI_BULL_DOMINANT`: +DI > −DI by a margin (e.g., +DI − (−DI) > 5 to filter near-equal crosses).
- `DI_BEAR_DOMINANT`: −DI > +DI by a margin.
- `DI_CROSS_BULL`: +DI crossed above −DI within the last N bars (event atom).
- `DI_CROSS_BEAR`: −DI crossed above +DI within the last N bars.

**Confidence**: High — multiple direct quotes from canonical reference.

### Finding 4 — Rising ADX reinforces the trend signal

**Claim**: ADX rising while DI alignment holds reinforces the trend strength signal; this is the highest-conviction setup.

**Source**: [StockCharts ChartSchool — Average Directional Index (ADX)](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/average-directional-index-adx) (retrieved 2026-05-11)

**Direct quote**:
- *"This bullish signal is reinforced if/when ADX turns up and the trend strengthens"*

**FORGE application**: We should distinguish two ADX-trend atoms:
- `ADX_TREND_STATIC` (ADX > 25, slope unspecified) — useful regime filter.
- `ADX_TREND_RISING` (ADX > 25 AND ADX_slope > 0) — high-conviction entry filter; trend not just present but accelerating.

The combination (`DI_CROSS_BULL` + `ADX_TREND_RISING`) is canonical Wilder-style trend-following entry.

**Confidence**: High — direct quote; supported by Wilder's original ADX framework.

## §4. Synthesis / Recommended pattern

**Atom set** (MQL5-ready):

```mql5
double adx     = AdxValue(14);                  // standard 14-period
double adx_prev= AdxValueShifted(14, 1);        // 1 bar back
double di_plus = DiPlus(14);
double di_minus= DiMinus(14);

// Regime classification (strength only).
bool ADX_NO_TREND    = adx < 20.0;
bool ADX_GRAY        = adx >= 20.0 && adx <= 25.0;
bool ADX_STRONG      = adx > 25.0;
bool ADX_RISING      = adx > adx_prev;

// Direction (DI balance only).
bool DI_BULL_DOMINANT = di_plus > di_minus + 5.0;  // 5-point margin filters noise
bool DI_BEAR_DOMINANT = di_minus > di_plus + 5.0;

// Canonical Wilder trend-following entry:
bool TREND_LONG_ENTRY  = ADX_STRONG && ADX_RISING && DI_BULL_DOMINANT;
bool TREND_SHORT_ENTRY = ADX_STRONG && ADX_RISING && DI_BEAR_DOMINANT;
```

**Atlas linkage**: §1 should list `ADX`, `ADX_SLOPE`, `DI_PLUS`, `DI_MINUS`, `DI_DELTA` (= +DI − −DI), `ADX_STRONG`, `ADX_RISING`, `DI_BULL_DOMINANT`, `DI_BEAR_DOMINANT`. §8 glossary rule: "ADX is direction-blind; never use as a directional gate. Combine with DI balance for direction, with ADX-slope for conviction."

## §5. Open questions / Followups

1. **DI margin threshold**: 5-point margin is heuristic — empirical tuning needed for XAUUSD M5. Could be ATR-normalized.
2. **ADX period for M5**: Wilder's default is 14; on M5 this is ~70 minutes of context. Should we test ADX(28) for M5 to capture slower regime shifts?
3. **DI-cross history**: an atom `DI_BULL_CROSS_RECENT_N` (within last N bars) would let composites act on a fresh cross rather than long-held DI dominance. Need to log this.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | StockCharts ChartSchool — Average Directional Index (ADX) | https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/average-directional-index-adx | 2026-05-11 |
| 2 | (Referenced) Wikipedia — Average directional movement index | https://en.wikipedia.org/wiki/Average_directional_movement_index | 2026-05-11 |
| 3 | (Referenced) Fidelity — Average directional index: ADX | https://www.fidelity.com/viewpoints/active-investor/average-directional-index-ADX | 2026-05-11 |
| 4 | (Referenced) TradingView Support — Average Directional Index (ADX) | https://www.tradingview.com/support/solutions/43000589099-average-directional-index-adx/ | 2026-05-11 |
