# RESEARCH NOTES — Asian Range Breakout at London Open (XAUUSD)

## §1. Question / Goal

FORGE's existing four setups (BB_BREAKOUT, BB_BOUNCE, MOMENTUM_DUMP, BB_PULLBACK_SCALP) all react to *intra-session* structure. They do not exploit the well-documented session-handoff phenomenon where the Asian session establishes an accumulation range and the London open (07:00–08:00 GMT) breaks out of it with directional bias. We want canonical rules for an `ASIA_RANGE_BREAKOUT_LONDON_OPEN` composite expressed as a boolean over atlas §1 atoms.

## §2. Methodology

**Search queries used (verbatim):**
- `Asian session range breakout London open strategy XAUUSD gold canonical rules`
- `Asian range breakout XAUUSD M5 high low rules pip statistics 65% London`

**Sources surveyed (retrieved 2026-05-11):**
- mql5.com — "The London Session Gold Strategy" Traders' Blog post 768254 (fetched)
- Medium — FXM Brand "Asian Session Gold Strategy" (search snippet)
- LiquidityFinder — "Asian Session Secrets: Will It Consolidate or Break Out? (SMC Blueprint)" (search snippet)
- ACY — "Asian Session Secrets: How Smart Money Uses Accumulation & Fake Breakouts" (search snippet)

**Source-quality filter:** mql5.com is the canonical MQL5/MetaTrader community source. The Medium / SMC sources are corroborative but lower-tier; treated as Low confidence on quantitative claims. Quantified Strategies blocked by bot wall — flagged for follow-up.

## §3. Findings (cited)

### Finding 1 — Asian session is an accumulation phase that London breaks

**Claim**: Gold trades in tight ranges during Asia as institutions accumulate, and the London open is the primary breakout window.

**Source**: [mql5.com — The London Session Gold Strategy (2026-03-19)](https://www.mql5.com/en/blogs/post/768254) (retrieved 2026-05-11)

**Direct quotes**:
- *"The period between 08:00 and 12:00 GMT consistently produces the largest intraday moves in XAUUSD, the highest liquidity"*
- *"The Asian session before it is characterized by accumulation — price moves in tight ranges as institutions quietly build positions."*
- *"Be ready at 07:45 GMT — 15 minutes before London open. Mark the Asian range (high and low from 00:00–07:00 GMT)"*

**FORGE application**: Atomically this means our composite needs (a) a pre-computed Asian high/low for the bars in window 00:00–07:00 GMT, (b) a "London window" flag (08:00–12:00 GMT), and (c) an atom for "first M5 close beyond the Asian extreme during the London window". Atlas §1 already has `session` (LONDON/NY/ASIA) and OHLC access — the new derived atoms are `g_asia_high`, `g_asia_low`, computed on the H1[ASIA→LONDON] transition.

**Confidence**: Medium — single canonical-tier source (mql5.com community blog); needs second-source cross-check before promoting to High.

### Finding 2 — Directional success rate ~65–70%

**Claim**: When the London breakout occurs in a given direction, the day continues in that direction roughly 65–70% of the time.

**Source**: [mql5.com — The London Session Gold Strategy](https://www.mql5.com/en/blogs/post/768254) (retrieved 2026-05-11)

**Direct quote**: *"The direction of the London breakout is correct for the day approximately 65-70% of the time based on historical data."*

**FORGE application**: A 65–70% directional bias is enough to justify a setup if we add a 1.5× ATR target (positive expectancy). The "correct for the day" framing suggests holding to NY close, but FORGE M5 scalping would size the target to 2× Asian range or 1× M5 ATR(14) — whichever is tighter — to avoid running into the NY-session reversal noise.

**Confidence**: Low → Medium — only one source provides the percentage. Flagged for verification with a XAUUSD-specific backtest on our own data.

### Finding 3 — Beware the Judas swing / liquidity sweep

**Claim**: A common pattern is for London to break the Asian high/low briefly, sweep stops, then reverse — entering on the initial break without a candle close confirmation is a documented failure mode.

**Source**: [mql5.com — The London Session Gold Strategy](https://www.mql5.com/en/blogs/post/768254) (retrieved 2026-05-11). Corroborated by the Medium FXM Brand post (search snippet, lower confidence).

**Direct quote (mql5)**: *"London institutional desks often engineer a 'Judas Swing'—a false move that breaks the Asian Range high or low to trigger stops, only for the price to reverse and head in the true direction of the day."* (paraphrased from the search summary; verbatim text in the article describes the same mechanic).

**FORGE application**: Entry condition must be a **closed-bar** break, not an intra-bar wick. Implementation: `iClose(_Symbol, PERIOD_M5, 1) > g_asia_high` (bar 1 = the just-closed candle), AND `iLow(_Symbol, PERIOD_M5, 1) > g_asia_high - 0.3*ATR` (the candle did not wick back deeply into the range — anti-Judas filter).

**Confidence**: Medium — the head-fake mechanic is also a canonical Bollinger Band concept (see `RESEARCH_NOTES_bollinger_squeeze.md` §3 Head Fakes), so the same engineering applies here.

## §4. Synthesis / Recommended pattern

**Atom additions to atlas §1** (new derived atoms):
- `g_asia_high`, `g_asia_low` — recomputed at session transition ASIA → LONDON
- `g_asia_range_atr` — `g_asia_high - g_asia_low` normalized by M5 ATR(14)
- `g_in_london_breakout_window` — `session==LONDON && TimeHour < 12`

**Layer-1 boolean composite (validatable from logged columns once Asia high/low are added to SIGNALS)**:

```mql5
bool ASIA_BREAKOUT_BUY  =
       g_in_london_breakout_window
    && iClose(_Symbol, PERIOD_M5, 1) > g_asia_high
    && iLow(_Symbol, PERIOD_M5, 1)   > g_asia_high - 0.3*m5_atr   // anti-Judas
    && g_asia_range_atr > 0.8                                     // skip dead-Asia days
    && h1_trend_strength >= 0;                                    // don't long into bear macro

bool ASIA_BREAKOUT_SELL =
       g_in_london_breakout_window
    && iClose(_Symbol, PERIOD_M5, 1) < g_asia_low
    && iHigh(_Symbol, PERIOD_M5, 1)  < g_asia_low + 0.3*m5_atr
    && g_asia_range_atr > 0.8
    && h1_trend_strength <= 0;
```

**Setup integration**: Register as a new FORGE setup type `ASIA_BREAKOUT` (Tier 2) — gated by `g_in_london_breakout_window` so it can only fire 08:00–12:00 GMT.

## §5. Open questions / Followups

1. **Statistical edge specific to XAUUSD M5** — the 65–70% figure is from a single mql5 community blog; needs validation against our Apr 1–8 tester data plus 2026 YTD.
2. **Window for Asia range** — sources disagree (00:00–07:00 GMT vs 00:00–08:00 GMT vs Tokyo open 00:00–03:00). Operator preference + data should resolve.
3. **DST handling** — London opens at 07:00 GMT in winter, 06:00 GMT in summer (BST). Need a session-aware time check, not a hard hour.
4. **Interaction with DD news filter** — if NFP/CPI hits at 12:30 GMT, the breakout may already be invalid. Should this composite suspend during the 30 min before high-impact events?

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | The London Session Gold Strategy — mql5.com Traders' Blog | https://www.mql5.com/en/blogs/post/768254 | 2026-05-11 |
| 2 | Asian Session Gold Trading Strategy (Medium / FXM Brand) | https://medium.com/@fxmbrand/asian-session-gold-strategy-how-to-trade-xauusd-like-a-pro-before-london-opens-8614172d4e06 | 2026-05-11 |
| 3 | Asian Session Secrets — LiquidityFinder | https://liquidityfinder.com/news/asian-session-secrets-will-it-consolidate-or-break-out-smc-blueprint-e34b9 | 2026-05-11 |
| 4 | Asian Session Secrets (ACY) | https://acy.com/en/market-news/education/market-education-asian-session-usdjpy-volatility-trading-strategy-j-o-20250818-092018/ | 2026-05-11 |
