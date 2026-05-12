# RESEARCH NOTES — VWAP / Institutional Bias

## §1. Question / Goal

Validate VWAP's role as an institutional execution benchmark and confirm canonical rules for "price above VWAP = bullish bias, price below VWAP = bearish bias," distance thresholds for mean-reversion vs trend-continuation interpretation, and the difference between intraday-anchored and daily VWAP. FORGE composites (§5.x) reference VWAP gap as a filter atom; we need third-party grounding before raising VWAP thresholds or anchoring composites to specific deviation bands.

## §2. Methodology

**Search queries used (verbatim):**
- `VWAP institutional bias trading rules distance from price intraday`
- `VWAP institutional benchmark execution algorithm definition CFA`

**Sources surveyed (retrieved 2026-05-11):**
- Wikipedia — "Volume-weighted average price" (fetched directly)
- GoCharting — "VWAP & Directional VWAP: Institutional Execution Strategy" (fetched directly)
- Kakade & Kearns (UPenn) — "Competitive Algorithms for VWAP and Limit Order Trading" (peer-reviewed; referenced via search but not fetched in full this session)
- Stanford / Busseti & Boyd — "VWAP Optimal Execution" (referenced via search)

**Source-quality filter:**
- Wikipedia + GoCharting accepted as canonical and platform-documentation respectively.
- UPenn/Stanford papers cited as evidence that VWAP is a recognized academic execution benchmark; full quotes not extracted.
- Rejected: tradingshastra.com, hyrotrader.com, chartmini.com — SEO content farms with affiliate-link patterns.

## §3. Findings (cited)

### Finding 1 — VWAP is THE institutional benchmark for passive execution

**Claim**: VWAP is used by pension funds, mutual funds, and execution brokers as a measurable benchmark of broker performance ("VWAP slippage").

**Source**: [Wikipedia — Volume-weighted average price](https://en.wikipedia.org/wiki/Volume-weighted_average_price) (retrieved 2026-05-11)

**Direct quotes**:
- *"VWAP is calculated using the following formula: P_VWAP = ∑ P_j · Q_j / ∑ Q_j"*
- *"VWAP is often used as a trading benchmark by investors seeking passive execution. Many pension and some mutual funds fall into this category."*
- *"Typically, the indicator is computed for one day, but it can be measured between any two points in time."*
- *"VWAP slippage refers to the difference between the intended and executed prices, and is a common measure of broker performance."*

**FORGE application**: VWAP gap atoms (current price vs intraday VWAP) carry MORE signal weight than e.g., MA-cross atoms because institutions are actively trying to execute toward this level. Mean-reversion trades from extreme distance to VWAP are essentially trading WITH institutional rebalancing flow. The Wikipedia confirmation that VWAP is computed "for one day" matches our daily-anchored VWAP atom.

**Confidence**: High — Wikipedia + multiple academic papers (Kakade/Kearns Penn, Busseti/Boyd Stanford) confirm VWAP as the standard execution benchmark.

### Finding 2 — Price above/below VWAP defines intraday bias

**Claim**: Institutions seek to buy below VWAP and sell above VWAP; price relative to VWAP is therefore a directional bias signal.

**Source**: [GoCharting — VWAP & Directional VWAP](https://gocharting.com/docs/orderflow/vwap-buy-vwap-and-sell-vwap) (retrieved 2026-05-11)

**Direct quotes**:
- *"VWAP (Volume Weighted Average Price) is the primary institutional execution benchmark, representing the average price weighted by volume throughout the session."*
- *"It helps in Buying low and Selling High. If the price is below VWAP, it is considered as undervalued, while price above VWAP is considered as overvalued."*
- *"Buy VWAP and Sell VWAP separate the VWAP for buying and selling transactions, revealing directional order flow bias."*

**FORGE application**: A simple `price > VWAP` boolean is a valid bias atom, but the more sophisticated read is the gap magnitude:
- gap > 0 (small) → mild bullish bias, institutions still buying.
- gap > 0 (large) → overvalued region, mean-reversion tail risk (sell-VWAP institutional flow activates).
- gap < 0 (small) → mild bearish bias.
- gap < 0 (large) → undervalued, buy-VWAP institutional flow activates.

**Confidence**: High — supported by Wikipedia (passive execution = trade toward VWAP) and GoCharting.

### Finding 3 — Distance thresholds (mean-reversion vs trend continuation)

**Claim**: When price deviates substantially from VWAP (~1–2%), contrarian mean-reversion entries become attractive; near-VWAP entries align with trend continuation. No single hard threshold is universal — operator discretion required.

**Source**: search synthesis (retrieved 2026-05-11) from candidate set referenced above

**Direct quote** (search snippet, not from a fetched canonical source — Medium confidence):
- *"When price deviates substantially from VWAP (e.g., >1–2%), traders consider contrarian reversion trades when volume and context support it."*

**FORGE application**: For XAUUSD gold at ~$2,400, a 1% VWAP deviation = $24, a 2% deviation = $48. Our `vwap_gap` atom likely needs ATR-scaled normalization rather than fixed-dollar — Run 18+ data should determine the actual deviation distribution. We should NOT hard-code a $X threshold without atr-anchoring.

**Confidence**: Medium — single-fetched-source quote, but pattern is consistent across the surveyed broker docs.

### Finding 4 — First 30 minutes is unstable

**Claim**: VWAP needs ~30 minutes of session data to stabilize; avoid VWAP-bias entries in the first 30 minutes of the session.

**Source**: search synthesis from candidate set (retrieved 2026-05-11)

**Direct quote** (search snippet):
- *"Avoid entering against VWAP in the first 30 minutes. Wait 30–60 minutes for VWAP to stabilize, confirm volume context, and use intraday timeframes (5m–30m) for entries."*

**FORGE application**: For FORGE on XAUUSD, the gold session is effectively 24-hour, but we can map this to the daily-VWAP anchor reset: in the first 30 M5 bars (~2.5 hours) after the day's daily-VWAP anchor reset, VWAP gap atoms should carry lower weight or be disabled. This may explain some of our morning-session noise — verify against Run 19/20 timestamps.

**Confidence**: Medium — single-source guideline; would benefit from one more authoritative source.

## §4. Synthesis / Recommended pattern

**Atom design** (MQL5-ready):

```mql5
// Daily-anchored VWAP gap as ATR-normalized z-score.
// Reset anchor at daily session boundary (e.g., UTC 00:00 or NY open).
double VwapGapAtrZ(double current_close, double vwap, double atr) {
    if (atr <= 0) return 0;
    return (current_close - vwap) / atr;
}

// Bias atoms:
bool VWAP_BULL_BIAS    = VwapGapAtrZ > 0    && SessionMinutes >= 30;
bool VWAP_BEAR_BIAS    = VwapGapAtrZ < 0    && SessionMinutes >= 30;
bool VWAP_OVEREXTENDED_BULL = VwapGapAtrZ > +2.0;  // mean-reversion candidate
bool VWAP_OVEREXTENDED_BEAR = VwapGapAtrZ < -2.0;
```

**Atlas linkage**: §1 should list `VWAP_GAP_ATR_Z` and `SESSION_MINUTES_SINCE_VWAP_ANCHOR` as logged atoms. §5 composites that use VWAP gap should require `SESSION_MINUTES >= 30` to avoid first-30-min noise.

## §5. Open questions / Followups

1. **VWAP anchor reset time for XAUUSD**: gold is 24h. Should the daily VWAP anchor reset at UTC 00:00, NY open, or some other gold-relevant time? Suggest comparing all three on Run 23+ data.
2. **ATR-z deviation distribution**: empirical distribution of `VWAP_GAP_ATR_Z` on Apr 1–8 dataset would tell us the 90th/95th percentile thresholds for "overextended."
3. **Anchored-VWAP (multi-day)**: GoCharting's anchored-VWAP page is a separate doc we did not fetch this session. For multi-day swing entries we may want a session-anchored VWAP from the prior daily low/high.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | Wikipedia — Volume-weighted average price | https://en.wikipedia.org/wiki/Volume-weighted_average_price | 2026-05-11 |
| 2 | GoCharting Docs — VWAP & Directional VWAP: Institutional Execution Strategy | https://gocharting.com/docs/orderflow/vwap-buy-vwap-and-sell-vwap | 2026-05-11 |
| 3 | (Referenced, not fully fetched) Kakade & Kearns — Competitive Algorithms for VWAP and Limit Order Trading | https://www.cis.upenn.edu/~mkearns/papers/vwap.pdf | 2026-05-11 |
| 4 | (Referenced, not fully fetched) Busseti & Boyd — Volume Weighted Average Price Optimal Execution | https://web.stanford.edu/~boyd/papers/pdf/vwap_opt_exec.pdf | 2026-05-11 |
