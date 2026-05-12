# FORGE Composite Roadmap — Inventory, Coverage, Shipping Plan

**Purpose**: Living plan for what boolean composites exist, what they cover, and what we
ship in each FORGE EA version. Distinct from `docs/FORGE_INDICATOR_ATLAS.md §5` (which is
the static spec/registry) — this doc is the **planning view**.

**Maintenance rule**: every time a composite is designed, validated, shipped, deferred,
or superseded — update this doc. Skill mandates it. §6 changelog is append-only.

**Created**: 2026-05-12

---

## §1. Current composite inventory (8 designed — atlas §5.1-§5.8)

| # | Composite | Day-types caught | Direction | Status |
|---|---|---|---|---|
| §5.1 | **BULL_DAY_DIP_BUY** | Mar 31, Apr 1 morning, Apr 8 morning | BUY | V1 validated, V2 (POC/Fib/VWAP) ready, V3 (+OHLC) drafted |
| §5.2 | **TREND_CONTINUATION_BUY** | Apr 1 NY rally, Apr 8 morning extension | BUY | Initial design — not validated |
| §5.3 | **FRACTIONAL_SELL_IN_BULL** | Overbought counter-probe in confirmed bull | SELL (fractional) | Design only |
| §5.4 | **BLOCK_SELL_IN_CHOP** | Universal SELL gate when RANGE+bull macro | gate (no trade) | Design only |
| §5.5 | **CHOP_LADDER_BUY_GRID** | Apr 6, Apr 7 pure-range days | BUY-biased grid | Design only |
| §5.6 | **INTRADAY_BEAR_IN_BULL** | Apr 8 PM (early version) | gate→SELL | Superseded by §5.7 |
| §5.7 | **INTRADAY_REVERSAL_TO_SELL** | Apr 2 09:00 crash, Apr 8 12:00 pivot | gate→SELL | V1 + V2 + V3 designed |
| §5.8 | **NO_TREND_DAY** | Apr 6, Apr 7 flat days | gate (no directional) | Design only |

---

## §2. Day-type coverage (from case study Mar 31 → Apr 8)

| Day | Character | Primary composite | Secondary |
|---|---|---|---|
| Mar 31 | chop-in-bull (+$150) | BULL_DAY_DIP_BUY | — |
| Apr 1 | clean bull (+$86) | BULL_DAY_DIP_BUY | TREND_CONTINUATION_BUY (NY rally) |
| Apr 2 | reversal day (−$85, $228 range) | INTRADAY_REVERSAL_TO_SELL (09:00) | BULL_DAY_DIP_BUY (recovery 17:00+) |
| Apr 6 | flat (−$2) | NO_TREND_DAY → CHOP_LADDER_BUY_GRID | — |
| Apr 7 | disguised-bear-walk-up | NO_TREND_DAY → CHOP_LADDER_BUY_GRID | — |
| Apr 8 | bull→reversal | BULL_DAY_DIP_BUY (morning) | INTRADAY_REVERSAL_TO_SELL (12:00) |

**6 day-types analyzed. 3-4 core composites cover all of them.** Apr 3-5 weekend gap (Good Friday + weekend).

**Days not yet analyzed** (Run 23 has data through Apr 9; later dates require Run 25):
- Apr 9, Apr 10, Apr 13 (data exists, no case study yet)
- Apr 14, Apr 15, Apr 16 (Run 18 reached, but case study needed)
- Multi-week patterns (April overall, Q2 patterns)

---

## §3. Key insight — composites are FILTERS, not new setups

FORGE has **4 setup triggers in production**: BB_BREAKOUT, BB_BOUNCE, MOMENTUM_DUMP, BB_PULLBACK_SCALP.

Most composites are **negative-space filters** on these existing triggers — they BLOCK wrong entries or ALLOW the right ones. They don't add new entry detection mechanisms (with two exceptions: CHOP_LADDER_BUY_GRID and TREND_CONTINUATION_BUY).

| Composite | Acts on which existing setups |
|---|---|
| BULL_DAY_DIP_BUY | Quality filter on MOMENTUM_DUMP BUY + BB_PULLBACK_SCALP BUY |
| INTRADAY_REVERSAL_TO_SELL | **Blocks all BUY setups** + amplifies MOMENTUM_DUMP SELL |
| BLOCK_SELL_IN_CHOP | Extends `dump_chop_block` to BB_BREAKOUT/BB_BOUNCE/BB_PULLBACK_SCALP SELL chains |
| FRACTIONAL_SELL_IN_BULL | **NEW entry pattern (small)** — only one that adds new firing |
| NO_TREND_DAY | Blocks directional setups |
| CHOP_LADDER_BUY_GRID | **NEW setup type** — 4-leg BUY LIMIT grid (basket kill switches) |
| TREND_CONTINUATION_BUY | **NEW setup type** — when BB_BREAKOUT cooldown blocks legitimate continuations |

This framing is important: most of our work tightens the existing engine rather than building new engines. Filter work is faster to ship and validate than new setup-trigger work.

---

## §4. v2.7.36 shipping plan — Tier 1 (4 composites)

These ship together as a coordinated bundle in v2.7.36.

| # | Composite | Why ship now | Setups it acts on |
|---|---|---|---|
| 1 | **BULL_DAY_DIP_BUY_V3** | Catches Mar 31 + Apr 1 + Apr 8 AM dip buys correctly; OHLC atoms (Fib 50 + cascade + wick) block the Apr 8 16:35 −$200 disaster | MOMENTUM_DUMP BUY, BB_PULLBACK_SCALP BUY |
| 2 | **INTRADAY_REVERSAL_TO_SELL_V3** | THE Apr 2 crash + Apr 8 PM pivot detector; flips direction when macro lags intraday | ALL BUY setups (gate); amplifies MOMENTUM_DUMP SELL |
| 3 | **BLOCK_SELL_IN_CHOP** | Extends existing chop-block to all SELL setups; cheap (1 gate, applies to 4 setups) | BB_BREAKOUT SELL, BB_BOUNCE SELL, BB_PULLBACK_SCALP SELL |
| 4 | **FRACTIONAL_SELL_IN_BULL** | Optional overbought-counter probe; high-value when it fires (rare) | NEW entry trigger (small lot) |

### Implementation scope estimate

```
ea/FORGE.mq5 changes:
  + 4 boolean composite definitions
  + filter chain inserts in 5 trigger blocks (BB_BREAKOUT/BB_BOUNCE/BB_PULLBACK_SCALP/MOMENTUM_DUMP × BUY+SELL)
  + helper computation block for OHLC atoms (day_high, m5_lh_cascade, body_pct)
  + new gate codes: entry_quality_bull_day_dip_buy_block_*, entry_quality_intraday_reversal_sell_*, entry_quality_chop_block_sell, fractional_sell_*
  + BB_PULLBACK_SCALP BUY/SELL lot factor split
  + logging gap fix (pass m15_adx + macd_histogram + pattern_score to 52 call sites)
  ≈ 250 LOC

config/gate_legend.json:
  + 5-6 new gate entries

.env / scalper_config.json:
  + 4 ENABLED knobs + 2 lot-factor knobs
```

---

## §5. v2.7.37+ Tier 2 (deferred)

| # | Composite | Why defer |
|---|---|---|
| 5 | NO_TREND_DAY | Pairs with CHOP_LADDER_BUY_GRID which is structural work |
| 6 | CHOP_LADDER_BUY_GRID | New setup type with basket kill switches — meaningful new mechanism, needs its own validation cycle (kill-switch design open: regime change exit, time expiry, basket-DD cap) |
| 7 | TREND_CONTINUATION_BUY | Refinement of BB_BREAKOUT; can wait until v2.7.36 ships and we measure how often BB_BREAKOUT's `entry_quality_atr_ext` gate blocks legitimate continuations |
| 8 | INTRADAY_BEAR_IN_BULL (§5.6) | Superseded by §5.7 — keep in registry as a "historical" entry; do not implement |

---

## §6. Candidate composites to research (operator-prompted: "see if we can improve this list")

Background research agent will Google for canonical XAUUSD M5 scalping patterns not yet
covered by our 8 composites. Results stored in `docs/RESEARCH_NOTES_<topic>.md` per skill.

**Candidate patterns to investigate** (each = potential new composite):

| Candidate | Hypothesized day-types covered | Why this might matter |
|---|---|---|
| **ASIA_RANGE_BREAKOUT_LONDON_OPEN** | Days where London-open price breaks the Asia-session range with conviction | XAUUSD typically has low-vol Asia + high-vol London; range-breakout is a well-known pattern that BB_BREAKOUT may miss if Asia range is narrow |
| **ROUND_NUMBER_REJECTION** | Reactions at psychological levels ($4500, $4750, $4800, $4850) | Gold has strong institutional reactions at round numbers; not currently atomized in FORGE |
| **PRIOR_DAY_HIGH_LOW_TEST** | Reactions at prior-day's high/low | Common reversal levels; FORGE has no atom for this today |
| **OVERNIGHT_GAP_FADE** | Gap-up/gap-down at session open that gets faded | Common in 24h markets when overnight liquidity moves price away from value |
| **VOLATILITY_BREAKOUT_FROM_SQUEEZE** | BB squeeze (low bb_width) followed by expansion | BollingerBands.com canonical; we have BB squeeze atom but no setup that fires specifically on the expansion |
| **NEWS_PULSE_REVERSAL** | First minutes after a major news event reverse | NFP/CPI/FOMC patterns; FORGE has news_filter but only as a block, not as a setup |
| **FAILED_BREAKOUT_REVERSE** | Price breaks BB upper/lower then closes back inside on the same bar | FORGE has `entry_quality_breakout_failed_samebar` as a gate but no setup that PROFITS from this |
| **TREND_DAY_OPENING_DRIVE** | Strong directional move in the first 30-60 min of London/NY that continues all session | Different from BB_BREAKOUT (anchored to session open, not BB level) |

These are HYPOTHESES — research will confirm/refute their statistical edge and adjust priority.

---

## §7. Composite design heuristics (from this iteration's learnings)

1. **Filter > New Setup**: when you can express the pattern as a filter on an existing trigger, do that. New setups need their own filter chain, gate codes, validation, and risk profile. Filters compose into existing infrastructure.

2. **Atoms before composites**: every new composite must use atoms already in atlas §1. If you need a new atom, add it to atlas §1 first with §13 command-log entry to verify availability.

3. **Cross-day validation > clever theory**: a composite that works on one day is a hypothesis. A composite that works on 3-5 similar days is a strategy. A composite that works on every day is over-fit.

4. **3 layers max in one composite**: macro (h1_trend / daily) + indicator (RSI / ADX / etc.) + structure (BB / OHLC / Fib). More than 3 layers = composite is doing too much; split into two.

5. **Symmetry where possible**: every BUY-direction composite should have a SELL mirror. Asymmetry between BUY and SELL is a flag (e.g., we DON'T have a CHOP_LADDER_SELL_GRID — because gold retraces UP in chop, so SELL grids fail there; that asymmetry is intentional).

6. **One direction per composite**: don't have a single composite that can fire BUY or SELL. Split. Easier to reason about, debug, and validate.

7. **Counter-trend = fractional, with-trend = full**: composites that fight the macro direction (e.g., FRACTIONAL_SELL_IN_BULL) get probe-sized lots. With-trend composites get full or amplified lots.

8. **Gate codes mirror composite negation**: if your composite is `(A && B && C)`, your filter chain has 3 gate codes (`!A_block`, `!B_block`, `!C_block`). Each rung of the filter chain emits ONE named gate code.

---

## §8. Status dashboard

| Composite | v2.7.36 Tier 1 ship | v2.7.37 Tier 2 ship | Validated? |
|---|---|---|---|
| BULL_DAY_DIP_BUY (V1) | — | — | ✓ Mar 31 + Apr 1 |
| BULL_DAY_DIP_BUY_V3 (with OHLC) | ✓ ship | — | will validate Run 25 |
| INTRADAY_REVERSAL_TO_SELL_V3 | ✓ ship | — | will validate Run 25 (Apr 2 + Apr 8 PM checks) |
| BLOCK_SELL_IN_CHOP | ✓ ship | — | will validate Run 25 |
| FRACTIONAL_SELL_IN_BULL | ✓ ship | — | will validate Run 25 |
| TREND_CONTINUATION_BUY | — | ✓ defer | not validated |
| NO_TREND_DAY | — | ✓ defer | not validated |
| CHOP_LADDER_BUY_GRID | — | ✓ defer | not validated |
| INTRADAY_BEAR_IN_BULL | — | — | superseded by §5.7 |
| (research candidates §6 above) | — | depending on research | TBD |

---

## §9. Cross-references

- **Atlas §5** (`docs/FORGE_INDICATOR_ATLAS.md`) — full composite spec registry (canonical source)
- **Decision Stack** (`FORGE_DECISION_STACK.md`) — terminology for what "composite" means
- **Research-Ops** (`FORGE_RESEARCH_OPS.md`) — the WHY this roadmap matters
- **Playbook** (`FORGE_SETUP_PLAYBOOK.md`) — current setup triggers (the ones our composites filter)
- **Case study** (`docs/FORGE_CASE_STUDY_2026_03_31_to_04_08.md`) — where composites were derived and validated
- **Logging extension** (`docs/FORGE_LOGGING_EXTENSION_DESIGN.md`) — v2.7.36 plan

---

## §10. Changelog

| Date | Change |
|---|---|
| 2026-05-12 | Initial roadmap created. 8 composites inventoried. Day-type coverage 6 days. Tier 1 (4 composites) for v2.7.36 + Tier 2 (3 composites) deferred. §6 candidate composites for research (8 hypotheses). §7 design heuristics codified. Status dashboard. |
| 2026-05-11 | **Candidate-composite research COMPLETE — 8 pattern notes** ([`asia_range_breakout`](docs/RESEARCH_NOTES_asia_range_breakout.md), [`round_number_levels`](docs/RESEARCH_NOTES_round_number_levels.md), [`prior_day_high_low`](docs/RESEARCH_NOTES_prior_day_high_low.md), [`overnight_gap_fade`](docs/RESEARCH_NOTES_overnight_gap_fade.md), [`bb_squeeze_breakout`](docs/RESEARCH_NOTES_bb_squeeze_breakout.md), [`news_pulse_reversal`](docs/RESEARCH_NOTES_news_pulse_reversal.md), [`failed_breakout_fade`](docs/RESEARCH_NOTES_failed_breakout_fade.md), [`opening_range_breakout`](docs/RESEARCH_NOTES_opening_range_breakout.md)). **Tier-2 ship-priority verdict**: `FAILED_BREAKOUT_FADE` (High confidence — Bulkowski + John Bollinger canonical, 28–44% failure rate = positive expectancy fade), `PRIOR_DAY_HIGH_LOW_TEST` (High — Capital.com broker-tier doc + named-author trend-context rule), and `ASIA_RANGE_BREAKOUT_LONDON_OPEN` (Medium-High — mql5 community canonical + 65–70% directional bias) are the three with the strongest canonical edge. `OPENING_RANGE_BREAKOUT` (40–60% WR, needs R:R ≥ 1.5) and `OVERNIGHT_GAP_FADE` (XAUUSD extrapolation from equities) are Tier-2 deferred pending backtest. `ROUND_NUMBER_REJECTION`, `NEWS_PULSE_REVERSAL`, `BB_SQUEEZE_BREAKOUT` are filters/sub-atoms best combined with the above primary setups. |
