# RESEARCH NOTES — Opening Range Breakout (ORB) / Trend-Day Opening Drive

## §1. Question / Goal

The Opening Range Breakout (ORB) is a foundational intraday strategy across futures and FX: mark the first 15/30/60 minutes' high and low after session open, then trade a candle-close break of that range. On XAUUSD this maps to the London open (07:00 GMT) and NY open (12:30 GMT). FORGE has no ORB-specific atom or trigger. Goal: design `TREND_DAY_OPENING_DRIVE` / `ORB_BREAKOUT` composites grounded in canonical ORB literature.

## §2. Methodology

**Search queries used (verbatim):**
- `opening range breakout strategy ORB intraday rules first 30 minutes statistics`

**Sources surveyed (retrieved 2026-05-11):**
- LiteFinance — "Opening Range Breakout (ORB) Strategy: Rules, Indicator & Success Rate" (fetched)
- ForexTester — "Opening Range Breakout (ORB) Trading Strategy" (fetched)
- HighStrike — "Opening Range Breakout Strategy" (HTTP 503 blocked)
- OptionAlpha — "Opening Range Breakout Trading Strategy" (search snippet)
- TradersMastermind — "Opening Range Breakout Strategy: Rules & Settings (2026)" (search snippet)

**Source-quality filter:** LiteFinance is a regulated broker — broker-documentation tier. ForexTester is a recognised backtesting-platform vendor — second-tier. ORB is one of the most-published strategy patterns; search results consistently agree on the core mechanic.

## §3. Findings (cited)

### Finding 1 — Canonical ORB definition (range + close break)

**Claim**: The opening range is the high–low envelope of the session's first 5/15/30/60 minutes; entry is a candle close beyond that envelope.

**Source**: [ForexTester — Opening Range Breakout (ORB) Trading Strategy](https://forextester.com/blog/opening-range-breakout-trading-strategies/) (retrieved 2026-05-11)

**Direct quotes**:
- *"The opening range is the highest high and lowest low made in the first block of time after the session opens – often 5, 15, or 30 minutes."*
- *"Bullish ORB: price closes above the range high. Bearish ORB: price closes below the range low."*
- *"Wait for a candle to close outside the opening range."*
- *"Wicks alone are not enough. Wait for a candle close to reduce fake breaks."*

**FORGE application**: For XAUUSD M5 with a 15-minute range, that's 3 M5 bars after session open. Atoms needed:
- `g_or_high_london`, `g_or_low_london` — high/low of M5 bars 0–2 after 07:00 GMT
- `g_or_high_ny`, `g_or_low_ny` — same for 12:30 GMT
- `g_or_window_active` — true on bars 3–24 (i.e. first 2 hours after open)
- Trigger: `iClose[1] > g_or_high_london && g_or_window_active`

**Confidence**: High — multiple canonical sources agree on the basic mechanic.

### Finding 2 — Quantified success rate (LiteFinance)

**Claim**: ORB win rate is 40–60% depending on regime, with proper risk management it can be net positive.

**Source**: [LiteFinance — Opening Range Breakout (ORB) Strategy](https://www.litefinance.org/blog/for-beginners/trading-strategies/opening-range-breakout-strategy/) (retrieved 2026-05-11)

**Direct quotes**:
- *"The success rate ranges from 40% to 60%, depending on market volatility, trend direction."*
- *"With proper risk management and consistent execution, it can generate stable results over time."*
- *"The main drawback of the method is a high number of false breakouts when strategy is used pure form."*

**FORGE application**: 40–60% win rate is borderline — requires R:R ≥ 1.5:1 for positive expectancy. Implementation: target = 1.5–2× the OR width; stop at the opposite OR edge or 0.5× ATR, whichever is tighter.

**Confidence**: Medium — single source for the percentage; cross-validation needed against FX/gold-specific data.

### Finding 3 — Confirmation rules: candle body, RVOL, VWAP, EMA

**Claim**: A clean ORB break requires candle body fully outside the range, relative volume > 1.5×, price on the right side of VWAP, and 20-EMA sloping with the break.

**Source**: [ForexTester — Opening Range Breakout (ORB) Trading Strategy](https://forextester.com/blog/opening-range-breakout-trading-strategies/) (retrieved 2026-05-11) and [LiteFinance — ORB](https://www.litefinance.org/blog/for-beginners/trading-strategies/opening-range-breakout-strategy/).

**Direct quotes**:
- *"Bullish ORB = close above range high and RVOL > 1.5 and price above VWAP and 20-EMA rising."*
- *"A 5-minute candle must close above the range high or below the range low."*
- *"The candle's range should exceed the average of the previous five candles."*
- *"Its body must fully close outside the range."*
- *"If the breakout candle forms but most of its body remains inside the range, wait for next candle."*

**FORGE application**: Confirmation atoms already partially present:
- `vwap_price` (atlas §1) — for "price above VWAP" check
- M5 ATR via `m5_atr` for range comparison
- Need a `g_breakout_body_pct = (iClose[1] - g_or_high_london) / (iHigh[1] - iLow[1])` atom for body-outside-range check
- No RVOL atom currently — volume data is available via M1 volume in scribe but not logged

**Confidence**: High — multiple sources agree, and the body-close rule is the foundational ORB discipline.

### Finding 4 — 35% of daily highs/lows occur in first 30 min (search summary)

**Claim**: Roughly 35% of a day's high or low is set within the first 30 minutes — the opening drive is statistically significant.

**Source**: Search summary citing multiple ORB strategy articles (BabyPips, OptionAlpha — direct fetches not performed for these in this session).

**FORGE application**: This is the *statistical core* of the ORB edge — early-session price action is information-dense. The implication for FORGE is that a confirmed break of the opening range has materially higher hold-probability than a mid-session break.

**Confidence**: Low → Medium — search-summary level only; verify with primary-source backtest before promoting.

## §4. Synthesis / Recommended pattern

**New atoms (atlas §1)**:
- `g_or_high_london`, `g_or_low_london` — captured at 07:15 GMT (after 3 M5 bars)
- `g_or_high_ny`, `g_or_low_ny` — captured at 12:45 GMT
- `g_or_width_london = g_or_high_london - g_or_low_london`
- `g_or_window_active = (bars 3–24 after session open)`
- `g_breakout_body_outside = body of bar 1 is entirely beyond OR edge`

**Layer-1 composite**:

```mql5
bool ORB_BREAKOUT_BUY =
       g_or_window_active
    && iClose[1] > g_or_high_london
    && (iClose[1] - g_or_high_london) > 0.3 * m5_atr   // body outside, not a wick
    && price > vwap_price                              // VWAP confirmation
    && h1_trend_strength >= 0                          // align with macro
    && g_or_width_london > 0.5 * atr_d1                // skip dead-open days
    && g_or_width_london < 2.0 * atr_d1;               // skip already-overextended

bool ORB_BREAKOUT_SELL =
       g_or_window_active
    && iClose[1] < g_or_low_london
    && (g_or_low_london - iClose[1]) > 0.3 * m5_atr
    && price < vwap_price
    && h1_trend_strength <= 0
    && g_or_width_london > 0.5 * atr_d1
    && g_or_width_london < 2.0 * atr_d1;
```

**Key insight**: ORB shares state with `ASIA_RANGE_BREAKOUT_LONDON_OPEN` (different range source, same break mechanic). The two composites should be kept separate but share `g_breakout_body_outside` and the candle-close confirmation idiom.

## §5. Open questions / Followups

1. **15-min vs 30-min OR for XAUUSD** — equities ORB uses 15 min; XAUUSD's shorter trading day (24h with quiet zones) may benefit from 30 min. Empirical test.
2. **London OR vs NY OR overlap** — both fire 4–6 hours apart; should we suppress one when the other has fired and held?
3. **Volume / RVOL substitute** — without true volume on gold, use M5 range or tick-volume as proxy for "RVOL > 1.5".
4. **Failed ORB → fade** — when ORB breaks then closes back inside the range, that's a `FAILED_BREAKOUT_FADE` (separate note). The two composites are direction-opposed and should never fire same-bar.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | ForexTester — Opening Range Breakout (ORB) Trading Strategy | https://forextester.com/blog/opening-range-breakout-trading-strategies/ | 2026-05-11 |
| 2 | LiteFinance — ORB Strategy: Rules, Indicator & Success Rate | https://www.litefinance.org/blog/for-beginners/trading-strategies/opening-range-breakout-strategy/ | 2026-05-11 |
| 3 | OptionAlpha — Opening Range Breakout Trading Strategy | https://optionalpha.com/blog/opening-range-breakout-0dte-options-trading-strategy-explained | 2026-05-11 (search snippet) |
| 4 | TradersMastermind — ORB Strategy: Rules & Settings (2026) | https://tradersmastermind.com/trading-strategy-opening-range-breakout/ | 2026-05-11 (search snippet) |
| 5 | Companion FORGE note | docs/RESEARCH_NOTES_asia_range_breakout.md (local) | 2026-05-11 |
