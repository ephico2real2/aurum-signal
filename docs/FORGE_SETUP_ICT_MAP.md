# FORGE Setup Catalog — ICT-Canonical Map

**Status**: canonical reference for the 28+ active FORGE setups and how they map to ICT primitives. Serves as the **single source of truth** for the operator's setup-naming mental model and as the **rename target** if/when the FORGE namespace consolidates onto ICT-canonical names. Lot sizing / math intentionally OUT of scope (see [`FORGE_LOT_SIZING_PRE_ICT.md`](FORGE_LOT_SIZING_PRE_ICT.md)).

## §1 Purpose

FORGE has accumulated 28 setup names over multiple ship cycles. Many map to the same ICT primitive (e.g., `BB_BREAKOUT`, `MA_CROSSOVER`, `ORB`, `GAP_AND_GO` are all "MSS structural break" in ICT canon — just differently triggered). The setup namespace is hard to hold in working memory.

This doc:

1. Catalogs every active setup with trigger condition, regime context, session focus, and direction
2. Groups them under 6 **ICT-canonical categories**
3. Flags **what FORGE is missing from full ICT canon** (Order Block, Breaker, Unicorn, CRT, Venom, Bread & Butter, RDRB, Seek and Destroy Friday — the Phase 3-5 work)
4. Provides a **consolidation rename map** for future restructure (cosmetic only — each setup keeps its trigger logic)

Cross-references:
- [`docs/prompts/ICT_Tradingidea.md`](prompts/ICT_Tradingidea.md) — operator-supplied ICT spec
- [`docs/MQL5_MODULAR_EA_DESIGN.md`](MQL5_MODULAR_EA_DESIGN.md) — modular FORGE convention
- [`docs/FORGE_PEMCG_ICT_INTEGRATION.md`](FORGE_PEMCG_ICT_INTEGRATION.md) — 3-mode PEMCG↔ICT integration
- [`docs/FORGE_ICT_PEMCG_COMBINATIONS.md`](FORGE_ICT_PEMCG_COMBINATIONS.md) — 16-cell ICT×PEMCG state matrix
- [`docs/research/ICT_KILLZONES.md`](research/ICT_KILLZONES.md) — kill-zone framework
- [`docs/FORGE_LOT_SIZING_PRE_ICT.md`](FORGE_LOT_SIZING_PRE_ICT.md) — Pre-ICT Lot Engine

## §2 The 6 ICT-canonical categories

| # | ICT Category | FORGE setups mapped | ICT primitive |
|---|---|---|---|
| 1 | **MSS_BREAKOUT** | BB_BREAKOUT, BB_BREAKOUT_RETEST, MA_CROSSOVER, ORB, GAP_AND_GO | Market Structure Shift — body-close break of recent swing |
| 2 | **OTE_RETRACEMENT** | BB_BOUNCE, BB_PULLBACK_SCALP, BB_LOWER_REVERSION_BUY, FIB_CONFLUENCE, VWAP_REVERSION, BULL_DAY_DIP_BUY | Optimal Trade Entry — retracement at 0.62-0.79 fib zone / FVG midpoint |
| 3 | **LIQUIDITY_SWEEP_REVERSAL** | BB_EXHAUSTION_REVERSAL_BUY/SELL, ASIA_CAPITULATION_BUY, DOUBLE_TOP, DOUBLE_BOTTOM, HEAD_AND_SHOULDERS, INVERSE_HEAD_AND_SHOULDERS | Sweep of equal highs/lows + ChoCH reversal |
| 4 | **BREAKER_BLOCK_RETEST** | SR_FLIP, TRENDLINE_BOUNCE | Order Block that fails → becomes breaker → retest entry |
| 5 | **DISPLACEMENT_ENTRY** | MOMENTUM_DUMP, MOMENTUM_DUMP_COMPOSITE, BB_SQUEEZE, FLAG_PENNANT, INSIDE_BAR | Displacement candle entry / FVG-creation precursor |
| 6 | **TREND_CONTINUATION** | TREND_CONTINUATION_BUY/SELL, GRINDING_SELL, NY_SESSION_BEARISH_BREAKOUT_SELL, FRACTIONAL_SELL_IN_BULL (counter-trend variant), INTRADAY_REVERSAL_SELL | HTF-aligned continuation entry on aligned day |

6 categories vs 28 names. The operator can think "MSS_BREAKOUT" as the family and not have to remember which of 5 variants fired.

## §3 Per-category deep-dive

### §3.1 MSS_BREAKOUT — Market Structure Shift (5 FORGE setups)

ICT definition: A body-close break of the most recent confirmed swing high/low with displacement (body ≥ 0.5×ATR per FORGE convention). Indicates the trend has shifted (or continued).

| FORGE setup | Direction | Trigger condition | Regime expected | Session |
|---|---|---|---|---|
| `BB_BREAKOUT` | BUY / SELL | M5 close beyond BB upper/lower + ADX ≥ min + RSI ceiling/floor filter | TREND_BULL / TREND_BEAR | LONDON / NY |
| `BB_BREAKOUT_RETEST` | BUY / SELL | BB_BREAKOUT signal + price returns to limit-price within `retest_max_bars` | TREND_* | LONDON / NY |
| `MA_CROSSOVER` | BUY / SELL | M5 fast EMA crosses slow EMA + ADX threshold + M15 alignment | TREND_* | LONDON / NY |
| `ORB` | BUY / SELL | Price breaks above/below opening-range high/low | TREND_* / VOLATILE | first 1h of LONDON/NY open |
| `GAP_AND_GO` | BUY / SELL | Session-open gap + ADX-confirmed continuation in gap direction | VOLATILE / TREND_* | NY open / post-news |

ICT mapping note: BB_BREAKOUT and MA_CROSSOVER both trigger on the same canonical event (structural break) but use different indicator proxies. ORB is ICT's "Bread and Butter" London Open Range model. GAP_AND_GO trades the gap as an imbalance.

### §3.2 OTE_RETRACEMENT — Optimal Trade Entry (6 FORGE setups)

ICT definition: After a structural break, price retraces to the 0.62-0.79 fib zone of the impulse leg (or FVG midpoint, OB top, premium/discount equilibrium). Entry at the retracement zone with the original direction.

| FORGE setup | Direction | Trigger condition | Regime expected | Session |
|---|---|---|---|---|
| `BB_BOUNCE` | BUY / SELL | Touch BB lower/upper + RSI confirmation + ADX_max filter | RANGE / mild trend | any |
| `BB_PULLBACK_SCALP` | BUY / SELL | Price retraces to BB mid after breakout-then-pullback | TREND_* (after first push) | LONDON / NY |
| `BB_LOWER_REVERSION_BUY` | BUY | M5 close ≤ BB lower + RSI ≤ max + ADX ≥ min + session ∈ {LON, NY} | NEUTRAL / mild bull | LONDON / NY |
| `VWAP_REVERSION` | BUY / SELL | Price extends ≥ X×ATR from VWAP + RSI extreme | RANGE / VOLATILE | LONDON / NY |
| `FIB_CONFLUENCE` | BUY / SELL | Price taps fib_50 / 0.618 / 0.786 + indicator confluence | TREND_* | any |
| `BULL_DAY_DIP_BUY` | BUY | Confirmed bull day + intraday dip + dip-quality confluence | TREND_BULL (intraday) | LONDON / NY |

ICT mapping note: `FIB_CONFLUENCE` is the closest to canonical OTE (fib-zone retracement entry). `BB_PULLBACK_SCALP` is the v2.7.31 setup designed for this exact pattern. `BB_LOWER_REVERSION_BUY` extends OTE into deep oversold (RSI ≤ max threshold) — ICT premium/discount in mean-reversion context.

### §3.3 LIQUIDITY_SWEEP_REVERSAL (6 FORGE setups)

ICT definition: Stop-hunt wick beyond a recent equal-highs / equal-lows cluster (the "liquidity pool"), followed by body-close back inside the prior range. Sweep + rejection + ChoCH = canonical reversal entry.

| FORGE setup | Direction | Trigger condition | Regime expected | Session |
|---|---|---|---|---|
| `BB_EXHAUSTION_REVERSAL_BUY` | BUY | PEMCG_SELL warnings ≥ 4 + no existing BUY position nearby | trap / late TREND_BEAR | LONDON / NY |
| `BB_EXHAUSTION_REVERSAL_SELL` | SELL | Mirror: PEMCG_BUY warnings ≥ 4 | trap / late TREND_BULL | LONDON / NY |
| `ASIA_CAPITULATION_BUY` | BUY | M5 RSI ≤ 28 + displacement ≥ 1.0×ATR + ATR-ratio ≥ 1.1 during Asia hours | ASIAN range bottom | ASIAN (22-07 UTC) |
| `DOUBLE_TOP` | SELL | 2 swing highs within tolerance + neckline break | TREND_BULL exhaustion | any |
| `DOUBLE_BOTTOM` | BUY | Mirror | TREND_BEAR exhaustion | any |
| `HEAD_AND_SHOULDERS` | SELL | 3-peak pattern + neckline break | TREND_BULL exhaustion | any |
| `INVERSE_HEAD_AND_SHOULDERS` | BUY | Mirror | TREND_BEAR exhaustion | any |

ICT mapping note: `DOUBLE_TOP/BOTTOM` and `H&S/INVERSE_H&S` are pre-ICT chart patterns that ICT framework reclassifies as "liquidity sweep at equal highs/lows + bearish/bullish ChoCH" — the v2.7.120 Phase 2 ChoCH + sweep atoms detect this directly, **which means these legacy pattern setups may become redundant** once Phase 2 atoms validate. `ASIA_CAPITULATION_BUY` is the ICT-closest setup name but currently fires WITHOUT sweep / ChoCH confirmation — Phase 2 ChoCH-support atom is the structural fix for the operator-flagged "Asia is always risky" pattern.

### §3.4 BREAKER_BLOCK_RETEST (2 FORGE setups)

ICT definition: An Order Block that fails (price breaks through it instead of holding) → it becomes a "breaker block" → on retest in the opposite direction, the broken OB acts as new S/R.

| FORGE setup | Direction | Trigger condition | Regime expected | Session |
|---|---|---|---|---|
| `SR_FLIP` | BUY / SELL | Recent resistance becomes support (or reverse) with retest | TREND_* | any |
| `TRENDLINE_BOUNCE` | BUY / SELL | Touch of recent trendline + rejection candle | TREND_* | any |

ICT mapping note: `SR_FLIP` is the **textbook breaker pattern** — when prior resistance flips to support after the structural break. `TRENDLINE_BOUNCE` is similar but uses a diagonal level. Phase 3 v2.7.121 (planned) Order Block + Breaker Block module will add structural OB/Breaker primitives, potentially making these setups more rigorous.

### §3.5 DISPLACEMENT_ENTRY (5 FORGE setups)

ICT definition: The candle that CREATES the imbalance (FVG) — a high-volume / wide-range / strong-body bar that signals institutional participation. Entry on the displacement bar itself (vs the FVG retracement which is OTE).

| FORGE setup | Direction | Trigger condition | Regime expected | Session |
|---|---|---|---|---|
| `MOMENTUM_DUMP` | BUY / SELL | M5 displacement candle ≥ N×ATR over lookback + ADX ≥ min + RSI gates | VOLATILE / fast-moving | LONDON / NY |
| `MOMENTUM_DUMP_COMPOSITE` | BUY / SELL | (v2.7.121 renamed; v2.7.122 will get own atoms) — currently same triggers as MOMENTUM_DUMP via shared filter chain | same as MOMENTUM_DUMP | same |
| `BB_SQUEEZE` | BUY / SELL | BB-width contracts below threshold + then expands in direction | NEUTRAL → VOLATILE | LONDON / NY |
| `FLAG_PENNANT` | BUY / SELL | Consolidation after impulse + breakout in impulse direction | TREND_* with pause | any |
| `INSIDE_BAR` | BUY / SELL | M5 bar fully inside prior bar's range + ADX min | compression → expansion | any |

ICT mapping note: `MOMENTUM_DUMP` is the closest to ICT displacement — explicitly looks for the wide-range candle that creates an FVG. `BB_SQUEEZE` / `INSIDE_BAR` are PRECURSORS to displacement (compression before expansion). `FLAG_PENNANT` is a continuation displacement.

### §3.6 TREND_CONTINUATION (5 FORGE setups)

ICT definition: After confirmed HTF bias (H4 trend, day-bias), entry on intraday-aligned signals that ride the trend. Distinguished from MSS_BREAKOUT by being POST-structural-break — confirmation that trend is established, not just starting.

| FORGE setup | Direction | Trigger condition | Regime expected | Session |
|---|---|---|---|---|
| `TREND_CONTINUATION_BUY` | BUY | Confirmed bull regime + multi-TF alignment + dip+resume pattern | TREND_BULL | any (favors LONDON/NY) |
| `TREND_CONTINUATION_SELL` | SELL | Mirror | TREND_BEAR | any |
| `GRINDING_SELL` | SELL | Slow downward drift + RSI 30-55 + macd<0 + room ≥ 0.5×ATR to day-low | slow TREND_BEAR | LONDON / NY |
| `NY_SESSION_BEARISH_BREAKOUT_SELL` | SELL | NY-session-specific bearish breakout with room-to-day-low ≥ X×ATR | TREND_BEAR | NY session only |
| `FRACTIONAL_SELL_IN_BULL` | SELL | Confirmed bull day + RSI overbought + bar-quality weak | TREND_BULL (top) | LONDON / NY |
| `INTRADAY_REVERSAL_SELL` | SELL | Intraday-reversal composite (h1+m15 turn against day-bias) | day-bias flip | LONDON / NY |

ICT mapping note: `FRACTIONAL_SELL_IN_BULL` is a **counter-trend** entry inside a TREND_BULL — ICT framework would call this a "bearish OTE" at premium zone with reduced size (matches FORGE's `fractional_sell_factor` lot reducer). `INTRADAY_REVERSAL_SELL` is an early-detection cousin (intraday ChoCH).

## §4 Full 28-setup alphabetical inventory

| # | FORGE Setup | Direction | ICT Category | Currently Enabled |
|---|---|---|---|---|
| 1 | `ASIA_CAPITULATION_BUY` | BUY | LIQUIDITY_SWEEP_REVERSAL | ✓ |
| 2 | `BB_BOUNCE` | BUY/SELL | OTE_RETRACEMENT | ✓ |
| 3 | `BB_BREAKOUT` | BUY/SELL | MSS_BREAKOUT | ✓ |
| 4 | `BB_BREAKOUT_RETEST` | BUY/SELL | MSS_BREAKOUT | ✓ |
| 5 | `BB_EXHAUSTION_REVERSAL_BUY` | BUY | LIQUIDITY_SWEEP_REVERSAL | ✓ |
| 6 | `BB_EXHAUSTION_REVERSAL_SELL` | SELL | LIQUIDITY_SWEEP_REVERSAL | ✓ |
| 7 | `BB_LOWER_REVERSION_BUY` | BUY | OTE_RETRACEMENT | ✓ |
| 8 | `BB_PULLBACK_SCALP` | BUY/SELL | OTE_RETRACEMENT | ✓ |
| 9 | `BB_SQUEEZE` | BUY/SELL | DISPLACEMENT_ENTRY | ✓ |
| 10 | `BULL_DAY_DIP_BUY` | BUY | OTE_RETRACEMENT | ✓ |
| 11 | `DOUBLE_BOTTOM` | BUY | LIQUIDITY_SWEEP_REVERSAL | ✓ |
| 12 | `DOUBLE_TOP` | SELL | LIQUIDITY_SWEEP_REVERSAL | ✓ |
| 13 | `FIB_CONFLUENCE` | BUY/SELL | OTE_RETRACEMENT | ✓ |
| 14 | `FLAG_PENNANT` | BUY/SELL | DISPLACEMENT_ENTRY | ✓ |
| 15 | `FRACTIONAL_SELL_IN_BULL` | SELL | TREND_CONTINUATION (counter) | ✓ |
| 16 | `GAP_AND_GO` | BUY/SELL | MSS_BREAKOUT | ✓ |
| 17 | `GRINDING_SELL` | SELL | TREND_CONTINUATION | ✓ |
| 18 | `HEAD_AND_SHOULDERS` | SELL | LIQUIDITY_SWEEP_REVERSAL | ✓ |
| 19 | `INSIDE_BAR` | BUY/SELL | DISPLACEMENT_ENTRY | ✓ |
| 20 | `INTRADAY_REVERSAL_SELL` | SELL | TREND_CONTINUATION (early flip) | ✓ |
| 21 | `INVERSE_HEAD_AND_SHOULDERS` | BUY | LIQUIDITY_SWEEP_REVERSAL | ✓ |
| 22 | `MA_CROSSOVER` | BUY/SELL | MSS_BREAKOUT | ✓ |
| 23 | `MOMENTUM_DUMP` | BUY/SELL | DISPLACEMENT_ENTRY | ✓ |
| 24 | `MOMENTUM_DUMP_COMPOSITE` | BUY/SELL | DISPLACEMENT_ENTRY | ✓ (renamed v2.7.121) |
| 25 | `NY_SESSION_BEARISH_BREAKOUT_SELL` | SELL | TREND_CONTINUATION | ✓ |
| 26 | `ORB` | BUY/SELL | MSS_BREAKOUT | ✓ |
| 27 | `SR_FLIP` | BUY/SELL | BREAKER_BLOCK_RETEST | ✓ |
| 28 | `TRENDLINE_BOUNCE` | BUY/SELL | BREAKER_BLOCK_RETEST | ✓ |
| 29 | `TREND_CONTINUATION_BUY` | BUY | TREND_CONTINUATION | ✓ |
| 30 | `TREND_CONTINUATION_SELL` | SELL | TREND_CONTINUATION | ✓ |
| 31 | `VWAP_REVERSION` | BUY/SELL | OTE_RETRACEMENT | ✓ |

31 setup variants total when BUY/SELL pairs are counted separately (28 unique setup names — BB_BOUNCE BUY/SELL counts as one row above for brevity).

## §5 What FORGE is MISSING from full ICT canon

These ICT primitives have NO direct FORGE setup today — they're Phase 2-5 of the ICT integration:

| ICT primitive | Description | Phase | Status |
|---|---|---|---|
| **Order Block (OB)** | Last opposite candle before displacement; retest acts as institutional S/R | Phase 3 (v2.7.121 module) | Scaffolded — `ea/include/Forge/IctOrderBlock.mqh` empty body |
| **Breaker Block (BB)** | Failed OB → on retest acts as opposite-direction S/R | Phase 3 | Scaffolded — same module |
| **Unicorn Model** | Confluence: sweep + MSS + FVG + breaker overlap | Phase 4 (v2.7.122) | Scaffolded — `IctScoring.mqh` |
| **Candle Range Theory (CRT)** | Range manipulation + reclaim + expansion away | Phase 5 (v2.7.123) | Scaffolded — `IctIntradayModel.mqh` |
| **Venom Model** | 2025 ICT intraday model — specific HTF + LTF confluence | Phase 5 | Scaffolded — same |
| **Bread and Butter** | London-Open range retest with bias confirmation (closer than current `ORB`) | Phase 5 | Scaffolded — same |
| **RDRB** (Redelivered / Rebalanced Price Range) | Re-test of mitigated FVG zone with renewed displacement | Phase 5 | Scaffolded — same |
| **Seek and Destroy Friday** | Friday-specific stop-hunt with reversal | Phase 5 | Scaffolded — same |
| **Institutional Order Flow drill** | Multi-step entry sequence with confluence stacking | Phase 5 | Scaffolded — same |

Once Phase 3-5 ship, the FORGE setup catalog roughly doubles. The 6-category ICT structure in §2 absorbs the new setups cleanly:

- **OB / Breaker** → BREAKER_BLOCK_RETEST category expands
- **Unicorn** → cross-category meta-setup (uses MSS + FVG + sweep)
- **CRT / Venom / Bread & Butter / RDRB / Seek-and-Destroy** → LIQUIDITY_SWEEP_REVERSAL or DISPLACEMENT_ENTRY depending on which primitive dominates

## §6 Consolidation proposal — 28 → 6 ICT-canonical names

If you want to collapse the setup namespace (cosmetic rename, each setup keeps its trigger logic), the natural mapping is:

| ICT-canonical name | FORGE setups mapped today | Rationale |
|---|---|---|
| **`MSS_BREAKOUT_BUY/SELL`** | BB_BREAKOUT, BB_BREAKOUT_RETEST, MA_CROSSOVER, ORB, GAP_AND_GO | All trigger on structural break, just different indicators |
| **`OTE_RETRACEMENT_BUY/SELL`** | BB_BOUNCE, BB_PULLBACK_SCALP, BB_LOWER_REVERSION_BUY, FIB_CONFLUENCE, VWAP_REVERSION, BULL_DAY_DIP_BUY | All trigger on retracement to a retest zone |
| **`LIQUIDITY_SWEEP_BUY/SELL`** | BB_EXHAUSTION_REVERSAL_*, ASIA_CAPITULATION_BUY, DOUBLE_TOP, DOUBLE_BOTTOM, H&S, INVERSE_H&S | All trigger on sweep of pre-existing liquidity (equal H/L cluster) |
| **`BREAKER_RETEST_BUY/SELL`** | SR_FLIP, TRENDLINE_BOUNCE | Retest of failed prior S/R level |
| **`DISPLACEMENT_BUY/SELL`** | MOMENTUM_DUMP, MOMENTUM_DUMP_COMPOSITE, BB_SQUEEZE, FLAG_PENNANT, INSIDE_BAR | All trigger on or around displacement-candle creation |
| **`TREND_CONTINUATION_BUY/SELL`** | TREND_CONTINUATION_*, GRINDING_SELL, NY_SESSION_BEARISH_BREAKOUT_SELL, FRACTIONAL_SELL_IN_BULL, INTRADAY_REVERSAL_SELL | All trigger on HTF-aligned continuation (or counter-trend variant) |

Operational impact of the rename:

- 28 names → 12 canonical names (6 × BUY/SELL pairs)
- Each "trigger logic" stays the same — only the **emitted `setup_type` string** changes
- A `setup_subtype` column could be added to SIGNALS to preserve the original-trigger identity (e.g., `setup_type = "MSS_BREAKOUT_BUY"`, `setup_subtype = "BB_BREAKOUT_RETEST"`)
- Operator's lot-knob namespace gets MUCH simpler — 6 setup-family lot factors instead of 28 individual ones
- Analytical queries get easier — "all MSS_BREAKOUT wins" is one filter instead of UNION of 5

Cost: large refactor — touches ~150+ env knobs, ~30+ struct fields, ~50+ string literals across FORGE.mq5 + scripts + config + .env. Comparable in size to the v2.7.121 MOMENTUM_DUMP_COMPOSITE rename (161 references) × 6.

Recommendation: **DON'T** rename today. The 6-category mental model is the operator's structuring layer (this doc serves that). The underlying setup names stay as they are. If the operator later wants to consolidate (e.g., when reaching ~40 setups after Phase 3-5), the rename map in this section is the canonical target.

## §7 How this doc gets used

- **Onboarding** — new analyst reads §2 + §4 to understand the setup landscape in 10 minutes
- **Naming new setups** — when designing a new boolean composite, refer to §2 to pick which category it belongs to (consistency with naming + lot-factor stacking)
- **Backtest analysis** — group TAKEN signals by ICT category for cross-category P&L analysis (rather than per-individual-setup-name, which fragments small samples)
- **Phase 3-5 ICT atoms** — when ICT primitives (OB, Breaker, Unicorn) land, the corresponding setups slot into existing categories per §5
- **Killzone-aware sizing** — when ICT killzone-amplifier ships (per `FORGE_LOT_SIZING_PRE_ICT.md` §5), it can be applied per category (e.g., OTE_RETRACEMENT at NY-AM KZ → +0.25× amplifier)

## §8 Appendix A — Strategic intent (confirmed 2026-05-15)

This appendix records the operator's **strategic intent** for the FORGE → ICT consolidation, confirmed during the v2.7.121 ship discussions. §1-§7 catalog the CURRENT state; this appendix sets the DESIGN TARGET. Where §6 ("consolidation proposal") recommends not renaming today, this appendix supersedes that recommendation — the consolidation IS the active design target, not a deferred future.

### A.1 What we're after — the strategic frame

1. **The 28-setup catalog is historical accretion, not designed coherence.** It accumulated as new patterns were discovered and shipped as named setups. The result: overlapping triggers, fragmented analytics, mental overhead just remembering what fires when.

2. **ICT gives a clean ontology.** Six categories cover the entire trading universe — MSS / OTE / LIQUIDITY_SWEEP / BREAKER / DISPLACEMENT / TREND_CONTINUATION. There is no "leftover" category. Every pattern worth trading fits one of these primitives.

3. **FORGE should BE that ontology, not have it as a layer on top.** The 6-category structure in §2 is not a documentation convenience — it is the **target architecture**.

4. **Retire redundant setups, not stack more.** When Phase 2 ChoCH + Sweep atoms land (v2.7.120, already shipped), `DOUBLE_TOP` / `DOUBLE_BOTTOM` / `HEAD_AND_SHOULDERS` / `INVERSE_HEAD_AND_SHOULDERS` become STRUCTURALLY redundant — the underlying atoms detect what those chart patterns proxied. The legacy pattern setups get RETIRED, not kept firing in parallel. Same logic applies as each Phase 3-5 module lands.

5. **Phase 2-5 ICT modules aren't additive — they're the new core.** Today they're scaffolded as "atoms that score" alongside existing setups (Mode A baseline per `FORGE_PEMCG_ICT_INTEGRATION.md`). The endgame: **ICT primitives ARE the setups**. MSS → `BB_BREAKOUT` folds into `MSS_BREAKOUT_*`. FVG retest → `BB_BOUNCE` folds into `OTE_RETRACEMENT_*`. Liquidity sweep → `ASIA_CAPITULATION_BUY` folds into `LIQUIDITY_SWEEP_BUY`.

6. **Result**: 6-12 setup_type values in the EA. Each one ICT-canonical. Each one wired to ICT primitives directly (not via 5 different legacy triggers). Operator's mental model = system's reality.

### A.2 Why §6 was conservatively wrong

§6 recommends "DON'T rename today, defer until you have ~40 setups". That tactic protects against namespace churn in a growing codebase. But it **misses the strategic frame**: this isn't about managing growing complexity — it's about **shrinking** complexity by consolidating onto ICT. The 6-category structure is the **active design target**, not a managed-for-later future state.

§6 stays in the doc as the **rename map** (the technical specification of which legacy setup folds into which ICT-canonical name). It does NOT stay as a "don't do it" recommendation — that gets reversed by this appendix.

### A.3 Migration milestones (north-star sequence)

This is a multi-month structural reorganization, not a single ship. The milestones below sequence ICT-canonical consolidation alongside the in-flight Phase 2-5 ICT atom work.

| Milestone | Description | Status |
|---|---|---|
| **M0 — Phase 2 ICT atoms** | ChoCH + Liquidity Sweep + Kill Zone detection live with logging | ✅ shipped v2.7.120 |
| **M1 — Phase 2 validation** | Tester replay confirms ChoCH detects what `DOUBLE_TOP` / `H&S` / `ASIA_CAPITULATION_BUY` proxy. Sweep detector confirms equal-highs/lows clusters. | pending tester run |
| **M2 — Retire `DOUBLE_TOP` / `DOUBLE_BOTTOM`** | Once Phase 2 atoms validate at parity, disable these setups (`*_enabled=0`). Logged-only for a tester window to confirm zero missed entries. Then delete the trigger code. | post-M1 |
| **M3 — Retire `H&S` / `INVERSE_H&S`** | Same as M2 — these are compound liquidity-sweep clusters, native ICT detection. | post-M2 |
| **M4 — Phase 3 (Order Block + Breaker + PD-array, v2.7.121)** | Ship `Forge/IctOrderBlock.mqh` real impl. | scaffolded, body deferred |
| **M5 — Retire `SR_FLIP` / `TRENDLINE_BOUNCE`** | Phase 3 Breaker Block detector replaces these. | post-M4 |
| **M6 — Phase 4 (Unicorn + ICT Scoring, v2.7.122)** | Master `ICTSignalScore` struct. ISS-C continuation composite. | scaffolded |
| **M7 — Folded MSS setups** | Migrate `BB_BREAKOUT` / `MA_CROSSOVER` / `ORB` / `GAP_AND_GO` to fire under one `MSS_BREAKOUT_*` setup_type with `setup_subtype` column preserving original-trigger identity. | post-M6 |
| **M8 — Folded OTE setups** | Migrate `BB_BOUNCE` / `BB_PULLBACK_SCALP` / `BB_LOWER_REVERSION_BUY` / `FIB_CONFLUENCE` / `VWAP_REVERSION` / `BULL_DAY_DIP_BUY` to one `OTE_RETRACEMENT_*` setup_type. | post-M7 |
| **M9 — Folded LIQUIDITY_SWEEP setups** | Migrate `BB_EXHAUSTION_REVERSAL_*` / `ASIA_CAPITULATION_BUY` (remaining post-M2/M3) to one `LIQUIDITY_SWEEP_*` setup_type. | post-M8 |
| **M10 — Folded DISPLACEMENT setups** | Migrate `MOMENTUM_DUMP` / `MOMENTUM_DUMP_COMPOSITE` / `BB_SQUEEZE` / `FLAG_PENNANT` / `INSIDE_BAR` to one `DISPLACEMENT_*` setup_type. | post-M9 |
| **M11 — Folded TREND_CONTINUATION setups** | Migrate `TREND_CONTINUATION_*` / `GRINDING_SELL` / `NY_SESSION_BEARISH_BREAKOUT_SELL` / `FRACTIONAL_SELL_IN_BULL` / `INTRADAY_REVERSAL_SELL` to one `TREND_CONTINUATION_*` setup_type. | post-M10 |
| **M12 — Phase 5 (CRT + Venom + B&B + S&D, v2.7.123)** | Ship `Forge/IctIntradayModel.mqh` real impl. New setups slot into existing 6 categories per §5. | scaffolded |
| **M13 — Lot engine restructure (Phase D)** | Replace per-28-setup lot factors with per-6-category factors + equity-% risk sizing. Per `FORGE_LOT_SIZING_PRE_ICT.md` §7. | post-M12 |

### A.4 Cross-system impact

The consolidation cascades into several other systems:

- **`config/scalper_config.json`** — `<setup_name>_enabled` knobs collapse from 28 to 6 master flags + sub-knobs per ICT category
- **`config/gate_legend.json`** — gate codes prefixed with setup name (e.g., `bb_breakout_buy_below_band`) get renamed to ICT-canonical (e.g., `mss_breakout_buy_below_band`)
- **`scripts/sync_scalper_config_from_env.py`** — ~150 env mappings collapse to ~30-50
- **`docs/FORGE_LOT_SIZING_PRE_ICT.md`** — §4 setup-by-factor matrix collapses to 6 rows
- **Athena UI** — per-setup TAKEN-entries / P&L panels reorganize around 6 categories with subtype drill-down
- **`docs/FORGE_LIVE_*_ANALYSIS.md`** — tick-report TAKEN tables show category-level groupings
- **The 12-of-30 selective-column rule** (per `.claude/skills/forge-monitor/SKILL.md`) — most setup-specific factors collapse into category-aware factors, reducing column count further
- **QuestDB migration** (`docs/QUESTDB_EVALUATION.md`) — column-oriented storage makes the lot-factor breakdown query-friendly per category

### A.5 What this appendix changes about the next ship

Previously queued: **v2.7.122 selective-12 lot-factor columns** (per `FORGE_LOT_SIZING_PRE_ICT.md` §7 Phase A). That ship adds 12 columns under the assumption of 28-setup namespace permanence.

**Under the strategic intent above**, the next ship should instead be:

- **M1 — Phase 2 validation pass** (no code change, tester-replay validation that ChoCH + sweep atoms detect chart-pattern setups at parity)
- **M2/M3 — Retire chart-pattern legacy setups** once M1 validates

The selective-12 columns ship may still happen, but BEFORE the M7-M11 folding (when 28 setups still exist). After folding, the column count and rationale change.

### A.6 What stays the same

- The `FORGE_LOT_SIZING_PRE_ICT.md` Pre-ICT Lot Engine doc — still the canonical lot-factor reference; its §7 Phase D (equity-% sizing) is the M13 milestone
- The Phase 2-5 ICT module scaffolds in `ea/include/Forge/` — those are exactly the design target
- The schema-parity 5-layer ship discipline (`.claude/skills/forge-monitor/SKILL.md`) — unchanged
- The PEMCG / ICT 3-mode integration plan (`FORGE_PEMCG_ICT_INTEGRATION.md`) — Mode A (Phase 2 atoms compute + log) remains the validation gate before Mode B / Mode C flips

## §9 Changelog

- **2026-05-15** — Initial catalog. 28 active FORGE setups mapped to 6 ICT-canonical categories. Per-category deep-dive (§3.1-3.6). Full alphabetical inventory (§4). What's missing from ICT canon (§5 — Phase 3-5 work). Consolidation proposal (§6 — NOT recommended today, but rename map is the canonical target for future restructure).
- **2026-05-15** — Appendix A added (§8) capturing operator-confirmed strategic intent. Reverses §6's "don't rename today" recommendation — consolidation IS the active design target. Migration milestones M0-M13 sequence the FORGE → ICT-canonical reorganization alongside Phase 2-5 ICT atom work. Cross-system impact catalog (A.4). Changes next-ship target from "v2.7.122 selective-12 columns" to "M1 Phase 2 validation pass + M2/M3 chart-pattern retirement".
