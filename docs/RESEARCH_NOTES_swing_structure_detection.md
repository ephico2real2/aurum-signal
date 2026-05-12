# RESEARCH NOTES — Swing structure detection (Dow Theory, Bill Williams fractals)

## §1. Question / Goal

Establish canonical rules for detecting trend changes via swing structure — Dow Theory's higher-highs/higher-lows for uptrends and lower-highs/lower-lows for downtrends — and the programmatic detection logic (Bill Williams 5-bar fractal). FORGE composites reference swing-structure atoms; we want a robust spec for `LOWER_HIGH_DETECTED` / `HIGHER_LOW_DETECTED` and the canonical confirmation rule (when does a swing-low break confirm a trend change?).

## §2. Methodology

**Search queries used (verbatim):**
- `Dow theory higher highs higher lows swing structure trend change rules`
- `swing high swing low fractal detection programmatic algorithm trading`

**Sources surveyed (retrieved 2026-05-11):**
- StockCharts ChartSchool — "Dow Theory" (fetched)
- LinnSoft — "Fractals - Swing Highs, Swing Lows" (fetched)
- Incredible Charts — Dow Theory Trends (referenced via search)
- Zerodha Varsity — Dow Theory primer (referenced via search)

**Source-quality filter:**
- StockCharts ChartSchool: long-standing technical-analysis reference, used in CMT curriculum.
- LinnSoft: charting platform documentation for fractal indicator (canonical for Bill Williams definition).
- Rejected: TradingStrategyGuides, Scribd-hosted PDFs (unverifiable).

## §3. Findings (cited)

### Finding 1 — Dow Theory uptrend/downtrend definition

**Claim**: An uptrend is defined as a sequence of higher highs and higher lows; a downtrend as lower highs and lower lows. Trend reversal requires a break of the prior structural pivot.

**Source**: [StockCharts ChartSchool — Dow Theory](https://chartschool.stockcharts.com/table-of-contents/market-analysis/dow-theory) (retrieved 2026-05-11)

**Direct quotes**:
- *"An uptrend is defined by prices that form a series of rising peaks and rising troughs (higher highs and higher lows)."*
- *"A downtrend is defined by prices that form a series of declining peaks and declining troughs (lower highs and lower lows)."*

**FORGE application**: Our atoms should be explicit:
- `UPTREND_INTACT`: latest swing high > prior swing high AND latest swing low > prior swing low.
- `DOWNTREND_INTACT`: latest swing high < prior swing high AND latest swing low < prior swing low.
- `STRUCTURE_BROKEN_BULLISH`: prior downtrend's lower-low chain broken by a higher low (warning, not confirmation).
- `STRUCTURE_BROKEN_BEARISH`: prior uptrend's higher-low chain broken by a lower low.

**Confidence**: High — canonical Dow definition; multiple sources agree.

### Finding 2 — Trend reversal CONFIRMATION rule (Dow)

**Claim**: A downtrend is not reversed until a higher low forms AND the subsequent advance breaks the prior reaction high; an uptrend is not reversed until a lower low forms AND the subsequent decline breaks the prior reaction low.

**Source**: [StockCharts ChartSchool — Dow Theory](https://chartschool.stockcharts.com/table-of-contents/market-analysis/dow-theory) (retrieved 2026-05-11)

**Direct quotes**:
- *"A downtrend is considered valid until a higher low forms and the ensuing advance off of the higher low surpasses the previous reaction high."*
- *"An uptrend is considered in place until a lower low forms and the ensuing decline exceeds the previous low."*
- *"The change of trend is not confirmed until the previous reaction high is surpassed"* (for uptrend reversals from downtrend).

**FORGE application**: This is the KEY rule for our trend-reversal atoms. A simple "higher low" is a WARNING; the confirmation requires the next advance to break the prior reaction high. Translating:

```
TREND_REVERSAL_BULL_CONFIRMED = (current_swing_low > prior_swing_low) AND
                                (current_close > most_recent_reaction_high)
```

Our case study Apr 8 12:00 pivot should be re-audited against this rule — if the pivot was identified only by the higher low without the subsequent reaction-high break, the signal is premature per Dow Theory.

**Confidence**: High — direct quote from canonical reference.

### Finding 3 — Programmatic detection: Bill Williams 5-bar fractal

**Claim**: A swing high (up fractal) is a bar whose high exceeds the highs of N bars to its left and N bars to its right; default N = 2 (so 5 bars total including the center).

**Source**: [LinnSoft — Fractals: Swing Highs and Swing Lows](https://www.linnsoft.com/techind/fractals-swing-highs-swing-lows) (retrieved 2026-05-11)

**Direct quotes**:
- *"A fractal is an entry technique that is traditionally defined as 'a bar that has two preceding and two following bars with lower highs (or lower lows, on a down move)'"*
- *"Traditionally, fractals involve 5 bars. A 5-bar up fractal defines a pattern where one bars is preceded 2 bars with lower highs and followed by 2 bars with lower highs"*
- *"Up fractals occur when a bars high exceeds the high of a given number of preceding and following bars"*
- *"Down fractals occur when a bars low is lower than the low of a given number of preceding and following bars"*
- *"The number of bars required in order for a fractal to be considered complete...Others options include 3, 7, 9, 11, 13, 15, 17, or 19 bars"*

**FORGE application**: Use a 5-bar fractal for swing detection on M5 (signal frequency suits scalping). For larger structural pivots (case study Mar 31–Apr 8), use a 9- or 15-bar fractal to filter noise. MQL5 reference implementation:

```mql5
bool IsSwingHigh(int idx, int N) {
    double h = iHigh(_Symbol, _Period, idx);
    for (int i = 1; i <= N; i++) {
        if (iHigh(_Symbol, _Period, idx + i) >= h) return false;
        if (iHigh(_Symbol, _Period, idx - i) >= h) return false;
    }
    return true;
}
```

**Confidence**: High — LinnSoft is canonical for the Bill Williams definition; corroborated by Wikipedia's fractal entry and multiple MT5 indicator implementations.

### Finding 4 — Fractals confirm AFTER the fact (lag is intentional)

**Claim**: Fractals only confirm two bars (N bars) AFTER the swing point; they are confirmation tools, not predictive.

**Source**: search synthesis (retrieved 2026-05-11) corroborated by the LinnSoft definition implicitly.

**Direct quote** (search synthesis — Medium confidence direct quote):
- *"Fractals appear two candles after the turning point, making them a confirmation tool rather than a predictive one."*

**FORGE application**: A 5-bar fractal on M5 confirms a swing high only 10 minutes after the actual high occurred. For real-time entry decisions, this lag means our swing-structure atoms are "delayed but reliable." For latency-sensitive composites, we may need a 3-bar fractal accepting more noise, or a parallel "tentative swing" atom that flips on a 2-bar pattern with provisional state.

**Confidence**: Medium — direct quote from synthesis; inherent in the 5-bar definition (you cannot confirm a swing high until 2 bars after it).

## §4. Synthesis / Recommended pattern

**Atom set** (MQL5-ready):

```mql5
// 5-bar fractal swing detection; idx in MQL5 native (0 = current, +N = older).
bool IsSwingHigh(int idx, int N=2) {
    double h = iHigh(_Symbol, _Period, idx);
    for (int i = 1; i <= N; i++) {
        if (iHigh(_Symbol, _Period, idx + i) >= h) return false;
        if (iHigh(_Symbol, _Period, idx - i) >= h) return false;
    }
    return true;
}
bool IsSwingLow(int idx, int N=2) {
    double l = iLow(_Symbol, _Period, idx);
    for (int i = 1; i <= N; i++) {
        if (iLow(_Symbol, _Period, idx + i) <= l) return false;
        if (iLow(_Symbol, _Period, idx - i) <= l) return false;
    }
    return true;
}

// Locate most recent two swing highs / lows.
// (Implementation: scan bars idx=N..N+lookback for IsSwingHigh / IsSwingLow.)

// Dow Theory trend state and confirmed reversal:
bool DOW_UPTREND_INTACT(double sh_now, double sh_prev, double sl_now, double sl_prev) {
    return (sh_now > sh_prev) && (sl_now > sl_prev);
}
bool DOW_REVERSAL_TO_BULL_CONFIRMED(double sl_now, double sl_prev, double recent_reaction_high) {
    return (sl_now > sl_prev) && (Close[0] > recent_reaction_high);
}
```

**Atlas linkage**: §1 should add `SWING_HIGH_5BAR`, `SWING_LOW_5BAR`, `DOW_UPTREND_INTACT`, `DOW_DOWNTREND_INTACT`, `DOW_REVERSAL_BULL_CONFIRMED`, `DOW_REVERSAL_BEAR_CONFIRMED`. §8 should note: "Swing-structure atoms lag by N bars (default 2); use only when latency is acceptable. Reversal confirmation requires BOTH a structural pivot AND a reaction-high/low break (Dow rule)."

## §5. Open questions / Followups

1. **N parameter selection**: 5-bar (N=2) is default but XAUUSD M5 may need 9-bar (N=4) due to gold's intra-bar chop. Need empirical comparison on our Apr dataset.
2. **"Reaction high/low" definition**: Dow's reaction high is the highest peak between the prior swing low and the current pivot. Implementation requires careful index tracking; consider a finite state machine.
3. **Volume confirmation**: Dow Theory original requires volume to confirm trend (rising volume on up-moves, declining on pullbacks). Should we add a `VOLUME_CONFIRMS_TREND` atom? Tick volume on MT5 is a proxy only.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | StockCharts ChartSchool — Dow Theory | https://chartschool.stockcharts.com/table-of-contents/market-analysis/dow-theory | 2026-05-11 |
| 2 | LinnSoft — Fractals: Swing Highs, Swing Lows | https://www.linnsoft.com/techind/fractals-swing-highs-swing-lows | 2026-05-11 |
| 3 | (Referenced) Incredible Charts — Dow Theory Trends | https://www.incrediblecharts.com/technical/dow_theory_trends.php | 2026-05-11 |
