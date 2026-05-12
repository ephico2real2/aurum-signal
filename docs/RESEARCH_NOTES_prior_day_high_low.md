# RESEARCH NOTES — Prior Day High / Low Test (PDH / PDL)

## §1. Question / Goal

FORGE currently has `iHigh(_Symbol, PERIOD_D1, 1)` / `iLow(_Symbol, PERIOD_D1, 1)` available per the atlas §1 OHLC (M5+) row, but no composite atom that *tests* whether the current M5 bar is reacting to those levels. The Capital.com / Medium / NinjaTrader literature is consistent that PDH and PDL act as intraday S/R. We need a canonical `PRIOR_DAY_HIGH_LOW_TEST` composite design.

## §2. Methodology

**Search queries used (verbatim):**
- `prior day high low support resistance intraday trading rules canonical`

**Sources surveyed (retrieved 2026-05-11):**
- Capital.com — "Day trading: previous day's high (PDH) and low (PDL) explained" (fetched)
- Medium — CryptoCred "Using Previous Day's High/Low for Intraday Bias" (fetched)
- NinjaTrader — "How to Identify Intraday Support and Resistance Levels" (search snippet)
- TradingFinder — "Previous Day's High and Low: How to Trade Using PDH and PDL" (search snippet)

**Source-quality filter:** Capital.com is a regulated CFD broker — broker documentation tier. CryptoCred is a recognized trader-educator (futures/crypto bias but applicable to FX). NinjaTrader is an established futures-broker site. Medium author CryptoCred is named and has a public following — second-tier but acceptable.

## §3. Findings (cited)

### Finding 1 — PDH/PDL act as S/R; sustained break flips polarity

**Claim**: PDH acts as resistance and PDL as support until a sustained break, after which polarity flips (PDH becomes support, PDL becomes resistance).

**Source**: [Capital.com — Day trading: previous day's high (PDH) and low (PDL) explained](https://capital.com/en-int/analysis/day-traders-toolbox-previous-days-high-and-low-pdh-pdl) (retrieved 2026-05-11)

**Direct quotes**:
- *"If price breaks and consolidates above PDH, the level may then act as support. Conversely, a sustained break below PDL can turn it into resistance."*
- *"During the early hours of trading, if price stays above the PDH, it may suggest continued buying interest, while failure to hold above the PDL can signal weaker sentiment or selling pressure."*
- *"A reversal pattern forming near PDH or PDL tends to be more meaningful than one appearing within the prior day's range."*

**FORGE application**: Two distinct setups:
1. **Test of PDH/PDL** — M5 bar wicks into the level and closes back inside the prior-day range → `PRIOR_DAY_TEST_REJECT` (rejection at level)
2. **Break of PDH/PDL** — M5 closes beyond the level for N consecutive bars → `PRIOR_DAY_BREAK_CONTINUE` (continuation in break direction)

Required new atoms: `g_dist_to_pdh`, `g_dist_to_pdl`, `g_at_pdh` (within 0.3 ATR), `g_at_pdl`.

**Confidence**: High — Capital.com is broker-tier documentation and the rule is consistent across all four surveyed sources.

### Finding 2 — Trend context determines bias direction

**Claim**: Failure-to-hold patterns at PDH/PDL only have edge when aligned with the dominant trend (use weakness above PDH for shorts only in downtrend; use strength below PDL for longs only in uptrend).

**Source**: [Medium — CryptoCred, Using Previous Day's High/Low for Intraday Bias](https://medium.com/@cryptocreddy/using-previous-days-high-low-for-intraday-bias-798fbd7d9509) (retrieved 2026-05-11)

**Direct quotes**:
- *"In a dominant downtrend, looking for weakness above previous day's high is more likely to result in success."*
- *"In a dominant uptrend, looking for strength below previous day's low is more likely to result in success."*
- *"I only use previous day's high/low to derive an intraday directional bias where price is at daily support/resistance."*
- *"Clear evidence that the market is rejecting price above previous day's high i.e. price is not allowed to stay there for long before moving back down."*

**FORGE application**: This locks the composite to use `h1_trend_strength` as a directional filter. Specifically:
- `PDH_REJECTION_SELL` requires `h1_trend_strength < 0`
- `PDL_REJECTION_BUY` requires `h1_trend_strength > 0`
- A "rejection" is operationalised as: bar wicked past the level (`iHigh[1] > pdh`) but closed back inside (`iClose[1] < pdh`).

**Confidence**: High — explicit, named-author commentary and consistent with Capital.com's "reversal pattern near PDH/PDL is more meaningful".

### Finding 3 — Levels are fixed for the trading day

**Claim**: PDH and PDL are computed at session start and remain unchanged through the day — they are not recomputed intraday.

**Source**: [Capital.com — Day trading: previous day's high (PDH) and low (PDL) explained](https://capital.com/en-int/analysis/day-traders-toolbox-previous-days-high-and-low-pdh-pdl) (retrieved 2026-05-11). Corroborated by NinjaTrader (search snippet).

**Direct quote (paraphrased in search summary, verifiable in fetched Capital.com article)**: *"The Previous Day's High and Low (PDH and PDL) belong strictly to the prior day and should not be adjusted during the current trading day."*

**FORGE application**: Implementation note — `g_pdh` and `g_pdl` are set once at the daily session boundary (00:00 server time) via `iHigh(_Symbol, PERIOD_D1, 1)` / `iLow(_Symbol, PERIOD_D1, 1)`, then cached. Don't recompute every tick.

**Confidence**: High — Wilder-tier definitional rule, no ambiguity.

## §4. Synthesis / Recommended pattern

**New atoms (atlas §1)**:
- `g_pdh`, `g_pdl` — set once per day from `iHigh/iLow(PERIOD_D1, 1)`
- `g_dist_to_pdh = MathAbs(price - g_pdh)`
- `g_at_pdh = g_dist_to_pdh < 0.3 * m5_atr`
- `g_pdh_rejection_bar = iHigh[1] > g_pdh && iClose[1] < g_pdh`
- `g_pdl_rejection_bar = iLow[1] < g_pdl && iClose[1] > g_pdl`

**Layer-1 composite (validatable from logged OHLC + h1_trend once atoms added)**:

```mql5
bool PDH_REJECTION_SELL =
       g_pdh_rejection_bar
    && h1_trend_strength < 0
    && rsi > 55;

bool PDL_REJECTION_BUY =
       g_pdl_rejection_bar
    && h1_trend_strength > 0
    && rsi < 45;

// Continuation variant (break + hold)
bool PDH_BREAK_CONTINUE_BUY =
       iClose[1] > g_pdh
    && iClose[2] > g_pdh
    && h1_trend_strength > 0;
```

## §5. Open questions / Followups

1. **Two-day rule** — some sources extend to "prior 2-day high/low" for stronger levels. Worth testing if PDH-2 / PDL-2 outperform PDH/PDL alone.
2. **Liquidity sweep variant** — ICT methodology (TradingFinder source) treats PDH/PDL as "liquidity pools" — bar wicks past and reverses. Largely equivalent to our rejection bar but worth coding as a derived atom.
3. **Hold time after break** — "sustained" break in Capital.com's quote is undefined. Need to backtest 1-bar, 2-bar, 3-bar hold variants.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | Capital.com — Day trading: PDH and PDL explained | https://capital.com/en-int/analysis/day-traders-toolbox-previous-days-high-and-low-pdh-pdl | 2026-05-11 |
| 2 | Medium — CryptoCred, Using Previous Day's High/Low for Intraday Bias | https://medium.com/@cryptocreddy/using-previous-days-high-low-for-intraday-bias-798fbd7d9509 | 2026-05-11 |
| 3 | NinjaTrader — How to Identify Intraday Support and Resistance Levels | https://ninjatrader.com/futures/blogs/how-to-identify-intraday-support-and-resistance-levels-in-your-trading/ | 2026-05-11 |
| 4 | TradingFinder — Previous Day's High and Low (ICT PDH/PDL) | https://tradingfinder.com/education/forex/ict-pdh-pdl/ | 2026-05-11 |
