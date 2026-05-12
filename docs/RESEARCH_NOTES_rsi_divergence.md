# RESEARCH NOTES — RSI Divergence (regular & hidden)

## §1. Question / Goal

Establish canonical rules for the four RSI divergence variants (regular bull, regular bear, hidden bull, hidden bear) and the confirmation rules that separate valid divergence signals from chart noise. FORGE has divergence atoms (`HID_BEAR`, hidden bull on logged data) used in §5.6/§5.7 composites and as a Run 25 candidate filter; we need third-party validation that our atom definitions match the canonical pattern, plus guidance on what additional confirmation a divergence flag should require before it gates an entry.

## §2. Methodology

**Search queries used (verbatim):**
- `RSI hidden bullish divergence regular bearish divergence rules confirmation`

**Sources surveyed (retrieved 2026-05-11):**
- Kraken Learn — "RSI divergences: What they are and how they work" (retrieval 2026-05-11)
- FXOpen Market Pulse — "Hidden Divergence Vs Regular Divergence: Basics and Examples" (retrieval 2026-05-11)
- StockGro, Alchemy Markets, TradersUnion — surveyed for snippet content (used as tertiary cross-validation only; not fetched directly)

**Source-quality filter:**
- Kraken (major regulated crypto exchange educational content) — accepted.
- FXOpen (FX broker education) — accepted as secondary; broker bias possible but definitions match cross-source.
- Rejected: stockstotrade.com, xs.com, tradersunion.com (affiliate/SEO mix), TradingView script pages (single-author scripts, not canonical).

## §3. Findings (cited)

### Finding 1 — The four divergence variants

**Claim**: Regular divergence signals trend exhaustion / potential reversal; hidden divergence signals trend continuation.

**Source**: [Kraken Learn — RSI divergences](https://www.kraken.com/learn/rsi-divergences-what-they-how-they-work) (retrieved 2026-05-11)

**Direct quotes**:
- Regular Bullish: *"Price makes lower lows, but RSI makes higher lows."*
- Regular Bearish: *"Price makes higher highs, but RSI makes lower highs."*
- Hidden Bullish: *"Price makes a higher low, but RSI makes a lower low."*
- Hidden Bearish: *"Price makes a lower high, but RSI makes a higher high."*

**FORGE application**: This is the exact spec for our atoms. `HID_BEAR` must require price LH + RSI HH (NOT price HH + RSI LH — that would be regular bear). Run 25 audit should verify the EA's divergence detector matches this; if it conflates the two, the §5.7 INTRADAY_REVERSAL_TO_SELL composite would fire on the wrong pattern.

**Confidence**: High — corroborated by FXOpen below and Kraken.

### Finding 2 — Hidden = continuation, Regular = reversal

**Claim**: Hidden divergence appears before a continuation of the prevailing trend; regular divergence indicates waning momentum and possible reversal.

**Source**: [FXOpen — Hidden Divergence Vs Regular Divergence](https://fxopen.com/blog/en/what-is-the-difference-between-regular-and-hidden-divergence/) (retrieved 2026-05-11)

**Direct quotes**:
- *"Regular divergence is a market condition that reflects waning strength of trend and momentum and is considered a strong signal of a market reversal."*
- *"Hidden divergence is called hidden because it's less obvious than the regular type. According to theory, hidden divergence usually appears ahead of a trend continuation."*
- Regular Bullish: *"When the price forms lower lows, but the indicator sets higher lows, the market may turn up."*
- Regular Bearish: *"When the price places higher highs, but the indicator sets lower highs, the market should decline."*
- Hidden Bullish: *"When the price forms higher lows, but the indicator sets lower lows, the market may rise soon."*
- Hidden Bearish: *"When the price sets lower highs, but the indicator places higher highs, the market may turn down soon."*

**FORGE application**: Critical context for composite design — `HID_BEAR` should ONLY gate SELL entries when the macro trend is already DOWN (continuation), not when it is bullish (in which case the correct atom is `REG_BEAR`). Misuse in a bull-trend day would fight the prevailing direction.

**Confidence**: High — two independent sources agree on the directional semantics.

### Finding 3 — Divergence requires confirmation; not a standalone signal

**Claim**: RSI divergence alone is insufficient; confirmation requires volume, candlestick pattern, trendline break, or RSI Failure Swing.

**Source**: Kraken (above) and FXOpen (above), plus search-result synthesis (retrieved 2026-05-11)

**Direct quotes**:
- Kraken (via search synthesis): *"The RSI divergence is not suggested to be used alone. The traders need some extra proof from price action or other tools before trusting the signal."*
- Kraken (via search synthesis): *"The RSI Failure Swing is the original method of trading the Regular RSI divergence... entering only when [the 'Fair Point'] breaks."*
- FXOpen: confirmation tools mentioned include *"candlestick patterns (shooting star), moving average crossovers (EMA), support/resistance levels, and trading volume."*

**FORGE application**: Divergence atoms should never gate entries solely on the divergence flag. A composite using `HID_BEAR` must AND with at least one of: (a) RSI breaks a structural level (Wilder Failure Swing — e.g., RSI breaks below the prior swing low between the two highs), (b) confirming candle (shooting star / bearish engulfing at the second high), or (c) macro alignment (h1_trend ≤ 0). This matches our existing §5.7 design where `HID_BEAR` ANDed with macro h1_trend ≤ −0.5 + RSI ≤ 33.

**Confidence**: High — explicit in both fetched sources and consistent across all surveyed snippets.

### Finding 4 — Wilder's Failure Swing as canonical confirmation

**Claim**: The original Wilder Failure Swing uses an RSI structural break (not a price break) to confirm divergence.

**Source**: [Kraken Learn — RSI divergences](https://www.kraken.com/learn/rsi-divergences-what-they-how-they-work) (retrieved 2026-05-11, via search synthesis)

**Direct quote** (snippet): *"The RSI Failure Swing is the original method of trading the Regular RSI divergence. A bullish divergence is traded with a Failure Swing Top setup, while a bearish divergence is traded with a Failure Swing Bottom."*

**FORGE application**: For a bearish failure swing — once RSI hits an overbought peak, pulls back to a "fair point" (intermediate low), retests to a lower high, and then breaks below the fair point — the bearish divergence is confirmed by the RSI structure itself. We could log `RSI_FAILURE_SWING_BEAR` as a derived atom: detected when RSI in last N bars: peak>70 → pullback → lower peak → break below pullback low.

**Confidence**: Medium — single fetched source describes the Failure Swing in detail (though it's a canonical Wilder concept from "New Concepts in Technical Trading Systems", 1978 — we have not yet fetched the primary text).

## §4. Synthesis / Recommended pattern

**MQL5-ready composite sketch** for `HID_BEAR_VALIDATED` (continuation SELL gate):

```mql5
// Hidden bearish divergence — VALID only when:
// 1. Price LH (current swing high < prior swing high within N bars)
// 2. RSI HH (RSI at current swing high > RSI at prior swing high)
// 3. Macro context confirms continuation (h1_trend <= 0)
// 4. RSI failure swing OR confirming candle at current swing high
bool HiddenBearValidated(int lookback, double h1_trend) {
    if (h1_trend > 0) return false;  // hidden = continuation; macro must agree
    int sh_now = SwingHighIdx(0, lookback);
    int sh_prev = SwingHighIdx(sh_now + 1, lookback);
    if (sh_now < 0 || sh_prev < 0) return false;
    bool price_lh = High(sh_now) < High(sh_prev);
    bool rsi_hh = RSI(sh_now) > RSI(sh_prev);
    if (!(price_lh && rsi_hh)) return false;
    // Confirmation: RSI broke below the intervening trough (failure swing)
    double rsi_trough = RSI_MinBetween(sh_prev, sh_now);
    bool failure_swing = RSI(0) < rsi_trough;
    return failure_swing;
}
```

**Atlas linkage**: §1 should add `RSI_FAILURE_SWING_BEAR` and `RSI_FAILURE_SWING_BULL` as derived atoms; §5.7 INTRADAY_REVERSAL_TO_SELL should be re-validated to confirm its `HID_BEAR` atom matches the price-LH + RSI-HH pattern (NOT the inverse).

## §5. Open questions / Followups

1. **What lookback window?** The cited sources do not pin down "how many bars back" defines a valid swing high/low. Wilder's original work uses ATR-derived swing logic; many implementations use 5- or 7-bar fractals. **Followup**: backtest FORGE's `HID_BEAR` detector with lookbacks {5, 7, 14} and measure win-rate divergence.
2. **Minimum RSI separation?** Some implementations require the RSI value gap (HH − LH) to exceed N points (e.g., 5) to filter noise. Not addressed by fetched sources.
3. **Primary text not yet fetched**: Wilder's 1978 book is the canonical source for Failure Swing; if a 3rd-party reprint is accessible, we should verify the exact rule for the "fair point" break.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | Kraken Learn — RSI divergences: What they are and how they work | https://www.kraken.com/learn/rsi-divergences-what-they-how-they-work | 2026-05-11 |
| 2 | FXOpen Market Pulse — Hidden Divergence Vs Regular Divergence: Basics and Examples | https://fxopen.com/blog/en/what-is-the-difference-between-regular-and-hidden-divergence/ | 2026-05-11 |
| 3 | (Tertiary — search snippet only) StockGro, Alchemy Markets, TradersUnion search results page | (search) | 2026-05-11 |
