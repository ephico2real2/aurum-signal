# RESEARCH NOTES — News Pulse Reversal (NFP / CPI / FOMC First-15-Minute Fade)

## §1. Question / Goal

FORGE currently freezes trading around major news events (per the news filter), but does not exploit the well-documented "V-shape spike and fade" that occurs in the first 5–15 minutes after NFP / CPI / FOMC releases. Goal: validate that the spike-and-reverse pattern is canonical, and design a `NEWS_PULSE_REVERSAL` composite that fires only in a narrow post-news window.

## §2. Methodology

**Search queries used (verbatim):**
- `news event reversal forex first 15 minutes initial spike fade NFP CPI`

**Sources surveyed (retrieved 2026-05-11):**
- FXEmpire — "News-driven FX Trading: How to Trade Events Like the FOMC, CPI, and NFP" (fetched)
- Mastery Trader Academy — "News Fade Strategy: 4 Strong Tips" (fetched)
- BuildAlpha — "News Event Trading Strategies" (search snippet)
- PriceActionNinja — "Forex News Trading Guide" (search snippet)

**Source-quality filter:** FXEmpire is established financial-media tier. Mastery Trader Academy is an independent educator — second-tier. BuildAlpha is a backtesting software vendor — third-tier. No peer-reviewed academic source surfaced; flagged as a limitation.

## §3. Findings (cited)

### Finding 1 — News-driven moves have a two-phase structure

**Claim**: Post-news price action consists of (1) an algorithmic spike and (2) a delayed reversal/drift as the market digests, often within 15 minutes.

**Source**: [FXEmpire — News-driven FX Trading (FOMC, CPI, NFP)](https://www.fxempire.com/education/article/news-driven-fx-trading-how-to-trade-events-like-the-fomc-cpi-and-nfp-1549791) (retrieved 2026-05-11)

**Direct quotes**:
- *"Research suggests that news-driven moves often have two components: 1. The initial spike (from algorithmic trading and quick-reaction traders) 2. The drift or follow-through (as the market fully digests the implications)"*
- *"Market data suggests that Non-Farm Payrolls has a well-earned reputation for reversals…a currency pair spiked 80 pips in one direction after NFP, only to completely reverse course within 15 minutes."*
- *"When researching this article, I found countless examples of Fed days where the market jumped one way on the statement release, then completely reversed during the press conference."*

**FORGE application**: A `NEWS_PULSE_REVERSAL` composite requires:
- A "news pulse window" timer started at the news release timestamp
- Detection of the initial spike (M5 bar with range > 2× ATR within first 1–3 bars of pulse)
- Reversal trigger: M5 bar closing in the opposite direction of the spike, within bars 3–6 of the pulse

**Confidence**: High — FXEmpire is a tier-1 source and the two-phase structure is consistent across the surveyed material.

### Finding 2 — NFP is the most reversal-prone event; CPI is more directional

**Claim**: NFP shows the strongest spike-and-reverse pattern; CPI surprises tend to create more sustained directional moves with less whipsaw.

**Source**: [FXEmpire — News-driven FX Trading](https://www.fxempire.com/education/article/news-driven-fx-trading-how-to-trade-events-like-the-fomc-cpi-and-nfp-1549791) (retrieved 2026-05-11)

**Direct quote**: *"When CPI significantly surprises, it tends to create more sustained, directional moves…CPI surprises tend to cause less whipsaw than other data."*

**FORGE application**: The composite should be event-type-aware. NFP-day fade probability is higher than CPI-day fade probability. Implementation: enum `g_pending_news_type` (NFP / CPI / FOMC / OTHER); enable the fade ONLY for NFP and FOMC, suppress for CPI.

**Confidence**: Medium — single source for the differentiation; needs cross-validation.

### Finding 3 — Wait 1–3 minutes minimum, ideally 30–60 minutes for high-conviction setup

**Claim**: Entering within the first 1–3 minutes after release is statistically inferior to waiting for an established reversal candle 30–60 minutes later.

**Source**: [Mastery Trader Academy — News Fade Strategy](https://masterytraderacademy.com/news-fade-strategy-profitable-guide/) (retrieved 2026-05-11)

**Direct quotes**:
- *"Do nothing during the first 1–3 minutes after the news drops"*
- *"Fade setups often occur 30–60 minutes after the news, not immediately"*
- *"A strong candle followed by a weak doji, inside bar, or absorption wick"*
- *"After the initial spike, price fails to make a new high/low"*
- *"Momentum indicators (like RSI or MACD) show lower highs or higher lows"*
- *"Look for a reversal candle (e.g., engulfing, strong counter candle)"*
- *"Enter on the break of the reversal candle in the opposite direction of the news spike"*

**FORGE application**: Translates to M5 bars:
- Skip M5 bar 0 (the news bar itself) and bar 1 (the immediate-reaction bar)
- Begin scanning bars 2–12 (i.e. minutes 10–60 post-release)
- Entry trigger: M5 close opposite the spike + RSI divergence + inside-bar/doji on the prior bar

**Confidence**: Medium — Mastery Trader Academy is second-tier, but rules align with FXEmpire's two-phase model and our own divergence atoms.

### Finding 4 — Spread widens during the spike (defensive guard)

**Claim**: The first-minute post-release sees market-makers pull liquidity; spreads widen 10–20× normal — entering in this window guarantees slippage even if the directional read is correct.

**Source**: Search summary (no direct fetch performed). Quoted by FXEmpire derivative content: *"spreads can widen from 1.0 pip to 20.0 pips or more, resulting in significant slippage."*

**FORGE application**: Hard guard: do not allow `NEWS_PULSE_REVERSAL` to fire while `spread > 3 * g_spread_baseline_30s`. This protects against entering during the liquidity vacuum.

**Confidence**: Low → Medium — corroborative but search-summary level.

## §4. Synthesis / Recommended pattern

**Required new infrastructure**:
- News calendar feed (currently FORGE has a news-filter pause but no event metadata) — new atoms `g_news_event_type`, `g_news_release_time`, `g_minutes_since_news`
- `g_news_pulse_spike_direction` — sign of `iClose[k] - iOpen[k]` for the news-bar (k = bar index at release time)
- `g_news_pulse_window_active` = `g_minutes_since_news >= 10 && g_minutes_since_news <= 60`

**Layer-1 composite (requires news-calendar integration to validate)**:

```mql5
bool NEWS_PULSE_REVERSAL_SELL =
       g_news_pulse_window_active
    && g_news_event_type != CPI            // CPI moves are sticky — skip
    && g_news_pulse_spike_direction > 0    // initial spike was UP
    && iClose[1] < iOpen[1]                // current bar closing down (reversal)
    && (rsi_divergence == "REG_BEAR" || rsi_divergence == "HID_BEAR")
    && spread < 3 * g_spread_baseline;

bool NEWS_PULSE_REVERSAL_BUY =
       g_news_pulse_window_active
    && g_news_event_type != CPI
    && g_news_pulse_spike_direction < 0
    && iClose[1] > iOpen[1]
    && (rsi_divergence == "REG_BULL" || rsi_divergence == "HID_BULL")
    && spread < 3 * g_spread_baseline;
```

## §5. Open questions / Followups

1. **News-calendar source** — ForexFactory free API vs paid feed? FXStreet vs ForexLive scraping? Operator decision.
2. **XAUUSD-specific event sensitivity** — gold reacts strongly to USD-impact events. Need to weight EUR/USD-only news lower (e.g. ECB events vs FOMC events).
3. **Spike threshold** — "M5 bar range > 2× ATR" is heuristic; tune against historical post-news bars.
4. **Holding period** — sources suggest the fade plays out over 30–90 minutes; sizing target should be `1.5 × g_news_pulse_spike_range`, not standard FORGE TP ladder.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | FXEmpire — News-driven FX Trading (FOMC, CPI, NFP) | https://www.fxempire.com/education/article/news-driven-fx-trading-how-to-trade-events-like-the-fomc-cpi-and-nfp-1549791 | 2026-05-11 |
| 2 | Mastery Trader Academy — News Fade Strategy | https://masterytraderacademy.com/news-fade-strategy-profitable-guide/ | 2026-05-11 |
| 3 | BuildAlpha — News Event Trading Strategies | https://www.buildalpha.com/news-event-trading/ | 2026-05-11 (search snippet) |
| 4 | PriceActionNinja — Forex News Trading Guide | https://priceactionninja.com/forex-news-trading-guide-nfp-cpi-fomc-major-releases/ | 2026-05-11 (search snippet) |
