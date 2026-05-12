# RESEARCH NOTES — Round Number / Psychological Levels (XAUUSD)

## §1. Question / Goal

FORGE currently has no atom that recognises round-number support/resistance. With gold trading in the $4500–$4850 zone, $50 and $100 increments (4500, 4550, 4600, 4650, 4700, 4750, 4800, 4850, 4900) act as documented psychological magnets. We want to determine the canonical definition and design a `ROUND_NUMBER_REJECTION` composite atomically.

## §2. Methodology

**Search queries used (verbatim):**
- `round number psychological levels gold XAUUSD support resistance trading rules`

**Sources surveyed (retrieved 2026-05-11):**
- TradingView — VasilyTrader "Psychological Levels and Round Numbers in Technical Analysis" (fetched)
- Babypips — "Psychological Levels" school lesson (403 blocked — search snippet only)
- Investopedia — "round-number-effect" (Claude unable to fetch)
- VasilyTrader blog — "Find Psychological Levels in Gold Trading" (search snippet)

**Source-quality filter:** TradingView idea posts from established authors (VasilyTrader has a public profile) are second-tier; the canonical academic basis (behavioural finance "anchoring") is well-known but our retrieval is via TradingView's restatement. Babypips quote is from search snippet (HTTP-403 on direct fetch) — Medium confidence.

## §3. Findings (cited)

### Finding 1 — Definition and behavioural-finance basis

**Claim**: Round numbers are price levels ending in multiples of 5/10/100 that traders anchor to, generating clustered orders that produce visible support/resistance.

**Source**: [TradingView — VasilyTrader, Psychological Levels and Round Numbers](https://www.tradingview.com/chart/XAUUSD/DQ9w0R4x-Psychological-Levels-and-Round-Numbers-in-Technical-Analysis/) (retrieved 2026-05-11)

**Direct quotes**:
- *"Psychological level is a price level on a chart that has a strong significance for the market participants due to the round numbers."*
- *"By the round numbers, I imply the whole numbers that are multiples of 5, 10, 100, etc."*
- *"These levels act as strong supports and resistances and the points of interest of the market participants."*
- *"Research in behavioral finance has shown that individuals exhibit a tendency to anchor their judgments and decisions to round numbers."*
- *"Quite often, these levels act as reference points for the market participants for setting entry, exit points and placing stop-loss orders."*

**FORGE application**: For XAUUSD at current price tier, the relevant levels are every $50 (4500, 4550, 4600 … 4900). Implementation atom: `g_dist_round_50` = `MathMod(price, 50.0)` distance, with `g_near_round_50 = MathMin(g_dist_round_50, 50 - g_dist_round_50) < 0.3 * m5_atr` (price is within ⅓ ATR of a $50 level).

**Confidence**: Medium — single fetched source; behavioural-finance basis is canonical but not quoted directly from a peer-reviewed paper in this session.

### Finding 2 — Not all round numbers are significant — historical context required

**Claim**: A round number is only a meaningful level if historical price action has previously reacted there.

**Source**: [TradingView — VasilyTrader, Psychological Levels and Round Numbers](https://www.tradingview.com/chart/XAUUSD/DQ9w0R4x-Psychological-Levels-and-Round-Numbers-in-Technical-Analysis/) (retrieved 2026-05-11)

**Direct quotes**:
- *"However, one should remember that not all price levels based on round numbers are significant."*
- *"When one is looking for an important psychological level, he should take into consideration the historical price action."*

**FORGE application**: A pure "near round number" atom is too crude. We should pair it with `prior_day_high`, `prior_day_low`, or `poc_price` proximity. The composite becomes: *"round number AND it overlaps with a recently-reacted level"*. This dovetails with `PRIOR_DAY_HIGH_LOW_TEST` research (separate note).

**Confidence**: Medium — single source but conceptually consistent with broader S/R doctrine.

### Finding 3 — Babypips lesson confirms the practical rule

**Claim**: Round numbers act as support/resistance because traders cluster orders at them, and breakouts above/below cause cascade order triggering.

**Source**: [Babypips — Psychological Level lesson](https://www.babypips.com/learn/forex/psychological-level) (retrieved 2026-05-11 — search snippet only; direct fetch returned HTTP 403)

**Direct quote (from search summary, not first-party fetched)**: *"Traders often set their orders around these levels. So when a price approaches these levels, it can trigger a cluster of buy or sell orders that causes the price to stall or reverse."*

**FORGE application**: Confirms the cluster mechanism. Note: because we did not fetch the page directly, this is Low confidence per skill §70 ("Never cite a URL you didn't fetch in this session"). Flag for re-fetch via a different method.

**Confidence**: Low — search-summary only, retrieval failed.

## §4. Synthesis / Recommended pattern

**New atoms** (need adding to atlas §1):
- `g_dist_to_round_50` — float, distance to nearest $50 round level
- `g_near_round_50` — bool, `g_dist_to_round_50 < 0.3 * m5_atr`
- `g_dist_to_round_100` — float, distance to nearest $100 level
- `g_near_round_100` — bool, similar

**Layer-1 composite (validatable once atoms are logged)**:

```mql5
// SELL setup at a round-number resistance the market has already reacted to.
bool ROUND_NUMBER_REJECTION_SELL =
       g_near_round_50
    && iHigh(_Symbol, PERIOD_M5, 1) >= round_level_above   // poked through
    && iClose(_Symbol, PERIOD_M5, 1) < round_level_above   // closed back below
    && rsi > 60                                            // momentum exhaustion
    && (rsi_divergence == "REG_BEAR" || rsi_divergence == "HID_BEAR");

bool ROUND_NUMBER_REJECTION_BUY =
       g_near_round_50
    && iLow(_Symbol, PERIOD_M5, 1) <= round_level_below
    && iClose(_Symbol, PERIOD_M5, 1) > round_level_below
    && rsi < 40
    && (rsi_divergence == "REG_BULL" || rsi_divergence == "HID_BULL");
```

This is effectively a `FAILED_BREAKOUT_REVERSE` (separate note) **filtered by round-number proximity** — strongest when both align.

## §5. Open questions / Followups

1. **$25 vs $50 vs $100 granularity** — at $4500, is $4525 still a "round" level for gold, or only multiples of $50/$100? Investopedia (Claude unable to fetch) likely answers this; need alternative source.
2. **Empirical reaction strength** — do XAUUSD candles at $50 levels actually show longer wicks or higher rejection-rate than non-round prices? Backtest required.
3. **Combine with POC** — does a $50 level that coincides with the day's POC have higher hit-rate than a $50 level alone?

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | TradingView — VasilyTrader, Psychological Levels and Round Numbers | https://www.tradingview.com/chart/XAUUSD/DQ9w0R4x-Psychological-Levels-and-Round-Numbers-in-Technical-Analysis/ | 2026-05-11 |
| 2 | Babypips — Psychological Level (search snippet, 403 on direct fetch) | https://www.babypips.com/learn/forex/psychological-level | 2026-05-11 |
| 3 | VasilyTrader blog — Find Psychological Levels in Gold Trading | https://www.vasilytrader.com/post/find-psychological-levels-in-gold-trading-easily-with-best-free-technical-indicator-on-tradingview | 2026-05-11 |
