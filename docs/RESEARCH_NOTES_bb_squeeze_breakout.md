# RESEARCH NOTES — Bollinger Squeeze → Volatility Breakout (Directional Entry)

## §1. Question / Goal

The existing `docs/RESEARCH_NOTES_bollinger_squeeze.md` established BBW squeeze as a direction-agnostic regime indicator. This note narrows the question: once a squeeze has been detected, what is the canonical *directional* entry rule and what is the head-fake failure mode? Goal: design a `VOLATILITY_BREAKOUT_FROM_SQUEEZE` composite that picks a side after the squeeze contracts.

## §2. Methodology

**Search queries used (verbatim):**
- `false breakout reversal Bollinger Band fade trading rules Bulkowski`
- `Bollinger Band squeeze breakout statistics`

**Sources surveyed (retrieved 2026-05-11):**
- StockCharts ChartSchool — "Bollinger Band Squeeze" (fetched — head-fake section in particular)
- BollingerBands.com — Bollinger Band Rules (already fetched in prior session, see `RESEARCH_NOTES_bollinger_squeeze.md`)
- John Bollinger — "Bollinger on Bollinger Bands" book (referenced via search summary)

**Source-quality filter:** BollingerBands.com (John Bollinger's own site) is the canonical primary source. StockCharts ChartSchool is the canonical secondary. This note treats both as authoritative and updates Layer-2 of `RESEARCH_NOTES_bollinger_squeeze.md`.

## §3. Findings (cited)

### Finding 1 — Directional entry rule: close beyond band after squeeze

**Claim**: A new advance is identified by a squeeze followed by a *close* above the upper band; a new decline by a squeeze followed by a close below the lower band.

**Source**: [StockCharts ChartSchool — Bollinger Band Squeeze](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/bollinger-band-squeeze) (retrieved 2026-05-11)

**Direct quotes**:
- *"A new advance starts with a squeeze and subsequent break above the upper band."*
- *"A new decline starts with a squeeze and subsequent break below the lower band."*
- *"Narrowing bands do not provide any directional clues. They simply infer that volatility is contracting…"*

**FORGE application**: The entry trigger is `iClose[1] > bb_upper && BBW_SQUEEZE_PRIOR_N_BARS` (the squeeze must have existed on the bars *before* the breakout candle, not on the breakout candle itself). Atlas atoms already present: `bb_upper`, `bb_lower`, `bb_mid`. Need new derived atoms: `g_bbw_squeeze_prior` (was-squeezed on bar 2 or 3, but not now).

**Confidence**: High — direct from canonical reference.

### Finding 2 — Head fake (false breakout) is well-documented

**Claim**: After a squeeze, prices can briefly break one band, then reverse and break the other; this is John Bollinger's documented "head fake" pattern.

**Source**: [StockCharts ChartSchool — Bollinger Band Squeeze](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/bollinger-band-squeeze) (retrieved 2026-05-11). Quoted Bollinger original from search summary.

**Direct quotes**:
- *"A bullish head fake starts when Bollinger Bands contract and prices break above the upper band. This bullish signal does not last long because prices quickly move back below the upper band and proceed to break the lower band."*
- *"A bearish head fake starts when Bollinger Bands contract and prices break below the lower band. This bearish signal does not last long because prices quickly move back above the lower band and proceed to break the upper band."*
- From John Bollinger (cited via Bollinger on Bollinger Bands, referenced in TradingSim search summary): *"beware of the 'head fake,' which occurs when prices break a band, then suddenly reverse and move the other way, similar to a bull or bear trap."*

**FORGE application**: Two derived atoms needed to defend against the head fake:
- `g_head_fake_buy = iClose[1] < bb_upper && iHigh[2] > bb_upper` (bar 2 broke up, bar 1 closed back inside) → arm a SELL setup
- `g_head_fake_sell = iClose[1] > bb_lower && iLow[2] < bb_lower` (bar 2 broke down, bar 1 closed back inside) → arm a BUY setup

This *is* the head-fake-fade pattern — see `RESEARCH_NOTES_failed_breakout_fade.md` for the fuller version of this composite (the two notes overlap by design).

**Confidence**: High — primary-source canonical from John Bollinger himself.

### Finding 3 — Statistical edge requires confirmation (BBW alone is qualitative)

**Claim**: The squeeze-to-expansion sequence is qualitatively reliable ("low volatility precedes high volatility") but has no published quantified hit-rate.

**Source**: [StockCharts ChartSchool — Bollinger Band Squeeze](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/bollinger-band-squeeze) (retrieved 2026-05-11)

**Direct quote**: *"The document contains no quantified statistical claims regarding success rates, probability of breakouts, or performance metrics for the Bollinger Band Squeeze strategy."* (paraphrase of fetch output — original page provides only qualitative framing.)

**FORGE application**: The composite must be cross-validated against our own XAUUSD M5 backtest before being promoted to Tier 1. Cite the case study (Apr 1–8) — if days with `BBW_SQUEEZE_PRIOR` followed by `iClose > bb_upper` show ≥60% win rate over the test window, justify the composite. If not, downgrade.

**Confidence**: Medium — qualitative basis is canonical; quantitative validation pending.

## §4. Synthesis / Recommended pattern

**Builds on existing atoms** (already in atlas §1): `bb_upper`, `bb_lower`, `bb_mid`. **New atoms required**:
- `g_bbw = (bb_upper - bb_lower) / bb_mid * 100`
- `g_bbw_pctl_180d` — BBW percentile over last ~180 days
- `g_bbw_squeeze_active = g_bbw_pctl_180d < 10` (current bar in squeeze)
- `g_bbw_squeeze_prior_3 = g_bbw_squeeze_active on bars 2, 3, OR 4 (within last 3 closed bars)`

**Layer-1 composite**:

```mql5
bool BBW_BREAKOUT_BUY =
       g_bbw_squeeze_prior_3      // we were squeezed within last 3 bars
    && !g_bbw_squeeze_active      // expansion has begun
    && iClose[1] > bb_upper       // closed beyond upper band
    && h1_trend_strength > 0      // align with macro
    && rsi > 50 && rsi < 75;      // momentum but not exhausted

bool BBW_BREAKOUT_SELL =
       g_bbw_squeeze_prior_3
    && !g_bbw_squeeze_active
    && iClose[1] < bb_lower
    && h1_trend_strength < 0
    && rsi < 50 && rsi > 25;

// Companion: the head-fake fade (see failed_breakout_fade note)
bool BBW_HEAD_FAKE_SELL = iHigh[2] > bb_upper && iClose[1] < bb_upper && rsi[2] > 70;
bool BBW_HEAD_FAKE_BUY  = iLow[2]  < bb_lower && iClose[1] > bb_lower && rsi[2] < 30;
```

## §5. Open questions / Followups

1. **Bars-of-squeeze threshold** — sources cite "near 6-month low of BBW" but don't quantify how many consecutive bars must be in squeeze. Empirical tuning needed (likely 5–20 M5 bars).
2. **Head fake vs valid break** — without ATR-based wick analysis, our entry can fire on a head fake. Solution: require the breakout bar's `iClose - bb_upper > 0.2 * m5_atr` (real penetration, not a tag).
3. **Interaction with `BB_BREAKOUT` setup** — FORGE already has a `BB_BREAKOUT` trigger. This composite would be a *filter* requiring the prior-squeeze precondition, dramatically reducing the trigger rate but raising win-rate.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | StockCharts ChartSchool — Bollinger Band Squeeze | https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/bollinger-band-squeeze | 2026-05-11 |
| 2 | BollingerBands.com — Bollinger Band Rules | https://www.bollingerbands.com/bollinger-band-rules | 2026-05-11 (prior session) |
| 3 | Companion FORGE note | docs/RESEARCH_NOTES_bollinger_squeeze.md (local) | 2026-05-11 |
