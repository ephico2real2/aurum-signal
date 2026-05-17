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

**Canonical reference case study** (2026-05-16): [`FORGE_CASE_STUDY_2026_03_30_LIQ_SWEEP_REV_PATTERN.md`](FORGE_CASE_STUDY_2026_03_30_LIQ_SWEEP_REV_PATTERN.md) — G5001 win (+$1,212) + G5003 loss (−$3,655) on identical sweep patterns, 49 min apart, same price level. Documents the **entry-pattern vs execution-geometry split**: both are correct LIQ_SWEEP_REV pattern fires (score 9/10), but trend-ride geometry (staged-add + wave-amp) on a chop-reversion scalp turned an identical structural entry into a $4,867 swing. Establishes the **chop-scalp geometry profile** (TP1=0.4×ATR, BE-snap on TP1, staged-add disabled, wave-amp disabled, cooldown=600s) required for the v2.7.125 `LIQUIDITY_SWEEP_REVERSAL_BUY` setup.

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

## §10 Appendix B — Minimal viable ICT category set (confirmed 2026-05-15)

This appendix supersedes §2's 6-category structure. After ICT-canon research (citations §B.6) the operator's bloat concern was validated: 6 entry categories are still too many for what ICT teaches. The clean separation is **entry categories (price action — what)** ⊥ **killzone tags (timing — when)**. Every trade gets ONE entry category + ONE killzone tag. Two orthogonal axes, not seven flat buckets.

### §B.1 Why 4 entry categories, not 6

ICT canon teaches a small set of entry primitives. From the research:

> "The four core strategies: market structure breaks with order blocks, fair value gap trading during kill zones, liquidity sweeps with reversals, and Silver Bullet setups."

The 6-category model in §2 has two redundancies:

| Old category | Verdict | Reason |
|---|---|---|
| MSS_BREAKOUT | **Keep — renamed MSS_CONTINUATION** | Canonical ICT primitive. Folds in DISPLACEMENT (the impulsive move that *creates* an MSS is by definition displacement — they are not separate categories, they are the same event viewed at different scales). |
| OTE_RETRACEMENT | **Keep** | Canonical. 62-79% fib pullback into discount/premium zone. |
| LIQUIDITY_SWEEP_REVERSAL | **Keep** | Canonical. Stop hunt → ChoCH/MSS → entry. |
| BREAKER_BLOCK_RETEST | **Keep — renamed BREAKER_RETEST** | Canonical. Distinct from MSS because the post-break behavior (broken OB acts as new S/R) has different entry mechanics. |
| DISPLACEMENT_ENTRY | **DROP — fold into MSS_CONTINUATION** | Displacement *is* the MSS-confirming impulse. Not its own entry category — it's the leg that creates the structure shift. Setups currently in this bucket (MOMENTUM_DUMP, BB_SQUEEZE breakout, FLAG_PENNANT, INSIDE_BAR break) all fire on the impulse leg of an MSS event. |
| TREND_CONTINUATION | **DROP — split into MSS_CONTINUATION + OTE_RETRACEMENT** | Not an ICT-canonical category. ICT teaches: trend continues via *either* a new MSS (push higher) *or* a pullback retest into OTE/FVG. Setups currently in this bucket are one or the other — there is no "trend continuation entry primitive" separate from MSS or OTE. GRINDING_SELL / NY_SESSION_BEARISH_BREAKOUT_SELL → MSS_CONTINUATION. TREND_CONTINUATION_BUY / FRACTIONAL_SELL_IN_BULL → OTE_RETRACEMENT. |

**Final 4 entry categories:**

1. `MSS_CONTINUATION` — Market Structure Shift confirmed by a displacement leg; entry on retrace into the FVG/OB that the impulse created (absorbs old A + E + half of F)
2. `OTE_RETRACEMENT` — Pullback to 62-79% fib in discount/premium zone, with FVG/OB confluence (absorbs old B + other half of F)
3. `LIQUIDITY_SWEEP_REVERSAL` — Sweep of equal highs/lows or session high/low followed by ChoCH; entry on first FVG retrace (absorbs old C + D)
4. `BREAKER_RETEST` — OB that was traded through and now acts as new S/R; entry on retest with FVG confluence (kept distinct from MSS_CONTINUATION)

### §B.2 Category G — preserved as ICT-canonical killzone dimension

Operator's instinct is correct and matches ICT canon: killzones are not a separate entry category, they are a **time filter applied to all entry models**. From research:

> "Kill Zones are not merely high-volatility time windows; they function as a time filter for all entry models. An FVG that forms at 2:00 PM is not the same trade as an FVG that forms at 2:30 AM during London open."

So Category G becomes a **dimension every trade carries**, not a flat category. The new `setup_type` is the entry category; a new `killzone` column tags the session. ICT-canonical naming for the 5 windows (NY time per ICT teaching):

| Tag | NY time window | Description | When to favor |
|---|---|---|---|
| `ASIAN_KZ` | 20:00 – 00:00 | Asian session — accumulation phase, ranges form | OTE_RETRACEMENT inside the Asian range; LIQUIDITY_SWEEP_REVERSAL of Asian high/low at London Open |
| `LONDON_OPEN_KZ` | 02:00 – 05:00 | London Open — first liquidity grab, often sweeps Asian range | All four entry categories; highest-conviction MSS_CONTINUATION window |
| `NY_AM_KZ` | 07:00 – 10:00 | New York AM — primary directional move of the day | MSS_CONTINUATION, BREAKER_RETEST of London-Open levels |
| `NY_PM_KZ` | 13:30 – 16:00 | New York PM — reversals, profit-taking, second move | LIQUIDITY_SWEEP_REVERSAL of NY-AM high/low |
| `LONDON_CLOSE_KZ` | 10:00 – 12:00 | London Close — bias hand-off, often reverses NY AM | OTE_RETRACEMENT for NY-PM continuation; bias-flip signal |
| `OFF_SESSION` | everything else | Outside any killzone | De-rate lot factor; entries should require ≥1 extra confluence |

**Silver Bullet sub-windows (optional precision tags within a killzone):**

| Tag | NY time | Within killzone | Use |
|---|---|---|---|
| `LONDON_SB` | 03:00 – 04:00 | LONDON_OPEN_KZ | 1-hour high-conviction window; FVG entries only |
| `AM_SB` | 10:00 – 11:00 | LONDON_CLOSE_KZ / NY_AM_KZ overlap | Highest-conviction NY-AM window |
| `PM_SB` | 14:00 – 15:00 | NY_PM_KZ | 1-hour PM-reversal window |

Silver Bullet tags are an OPTIONAL second dimension — most trades won't carry one. When they do, lot factor +0.1 amplifier per ICT canon (high-conviction window).

### §B.3 Combined tag format — colleague-friendly naming

Every trade carries: **`<entry_category>` + `<killzone>` [+ `<silver_bullet>`]**. Examples:

| FORGE tag | Plain-English (colleague-friendly) |
|---|---|
| `MSS_CONTINUATION + LONDON_OPEN_KZ` | "London-open MSS continuation" |
| `OTE_RETRACEMENT + NY_AM_KZ + AM_SB` | "AM Silver Bullet OTE" |
| `LIQUIDITY_SWEEP_REVERSAL + NY_PM_KZ` | "PM sweep reversal" |
| `BREAKER_RETEST + LONDON_CLOSE_KZ` | "London-close breaker retest" |
| `OTE_RETRACEMENT + ASIAN_KZ` | "Asian-range OTE" |

This is the colleague-discussion grammar the operator asked for: two ICT-canonical nouns concatenated, instantly memorable, no internal codenames.

### §B.4 Migration impact relative to Appendix A

Appendix A's milestones M7-M11 collapse to **M7-M9** under this minimal set:

| New milestone | Replaces | Effect |
|---|---|---|
| **M7 — Fold to `MSS_CONTINUATION`** | Old M7 (MSS) + old M10 (DISPLACEMENT) + half of old M11 (TREND_CONTINUATION) | One setup_type covers `BB_BREAKOUT`, `MA_CROSSOVER`, `ORB`, `GAP_AND_GO`, `MOMENTUM_DUMP`, `MOMENTUM_DUMP_COMPOSITE`, `BB_SQUEEZE`, `FLAG_PENNANT`, `INSIDE_BAR`, `GRINDING_SELL`, `NY_SESSION_BEARISH_BREAKOUT_SELL`. Subtype column preserves original-trigger identity. |
| **M8 — Fold to `OTE_RETRACEMENT`** | Old M8 (OTE) + other half of M11 | One setup_type covers `BB_BOUNCE`, `BB_PULLBACK_SCALP`, `BB_LOWER_REVERSION_BUY`, `FIB_CONFLUENCE`, `VWAP_REVERSION`, `BULL_DAY_DIP_BUY`, `TREND_CONTINUATION_BUY`, `FRACTIONAL_SELL_IN_BULL`, `INTRADAY_REVERSAL_SELL`. |
| **M9 — Fold to `LIQUIDITY_SWEEP_REVERSAL`** | Old M9 (LIQUIDITY_SWEEP) | `BB_EXHAUSTION_REVERSAL_*`, post-M2/M3 remnants of chart patterns, `ASIA_CAPITULATION_BUY`. |

(BREAKER_RETEST stays gated behind Phase 3 — M5 in Appendix A is unchanged.)

After M9 the EA has **4 setup_types**, not 6. Subtype column preserves attribution for ablation studies.

### §B.5 New SIGNALS schema columns (per schema-parity mandate)

To represent the entry × session structure end-to-end, two new columns are required (5-layer ship per `.claude/skills/forge-monitor/SKILL.md`):

| Column | Type | Domain | Source |
|---|---|---|---|
| `killzone` | TEXT | `ASIAN_KZ` / `LONDON_OPEN_KZ` / `NY_AM_KZ` / `NY_PM_KZ` / `LONDON_CLOSE_KZ` / `OFF_SESSION` | `g_regime.killzone` (already computed per `FORGE_REGIME_TAXONOMY.md §11`) |
| `silver_bullet` | TEXT | `LONDON_SB` / `AM_SB` / `PM_SB` / `NONE` | new `IsInSilverBulletWindow()` in `Forge/IctLiquidity.mqh` |

The `killzone` atom is already computed and logged per `g_regime` migration; this just promotes it from runtime to schema. `silver_bullet` is new — slot it next to `killzone` in `JournalRecordSignal`.

### §B.6 Citations

- [JadeCap — All Five ICT Entry Models Explained](https://time-price-research-astrofin.blogspot.com/2026/02/all-five-ict-entry-models-explained.html) — confirms ICT canon teaches 5 entry models (MSS, OTE, Liquidity Sweep, OB/Breaker, Unicorn)
- [QuantumAlgo — Complete Guide to ICT Concepts (2026)](https://www.quantum-algo.com/blog/ict-trading-strategy-complete-guide/) — "the four core strategies: market structure breaks with order blocks, fair value gap trading during kill zones, liquidity sweeps with reversals, and Silver Bullet setups"
- [LuxAlgo — ICT Killzones Toolkit](https://www.luxalgo.com/library/indicator/ict-killzones-toolkit/) — confirms killzone is overlay/filter applied to entry models, not a separate entry category
- [TradingFinder — Build an ICT Entry Model: Select Timeframe and Kill Zone](https://tradingfinder.com/education/forex/ict-build-entry-model/) — killzone as time-filter dimension on the entry model
- [TradingWit — ICT Strategy Concepts](https://tradingwit.com/learn-trading/ict-strategy-concepts/) — canonical primitives definitions for MSS/FVG/OTE/OB/Breaker
- [InnerCircleTrader — Unicorn Model](https://innercircletrader.net/tutorials/ict-unicorn-model/) — confirms Unicorn = composite of Breaker + FVG (defers to Phase 4 in FORGE)

### §B.7 Current FORGE killzone implementation — review + ICT-aligned recommendations

FORGE today ships **two parallel killzone implementations** that diverge. This section pulls both verbatim, lists the correctness/divergence issues, and specifies the alignment plan that makes the EA match the §B.2 canonical model.

#### §B.7.1 What's in the code today

**Implementation A — `FORGE.mq5:6977` `ComputeCurrentKillzoneLabel()` (authoritative chokepoint)**

```mql5
string ComputeCurrentKillzoneLabel() {
   if(!g_sc.killzones_enabled) return "";
   datetime ny = GetNYTimeNow();
   MqlDateTime dt; TimeToStruct(ny, dt);
   if(dt.day_of_week == 6) return "";
   if(dt.day_of_week == 0 && dt.hour < 17) return "";
   int now_min = dt.hour * 60 + dt.min;
   if(MinuteInWindow(now_min, g_sc.kz_ny_open_start_min,      g_sc.kz_ny_open_end_min))      return "NY_OPEN_KZ";
   if(MinuteInWindow(now_min, g_sc.kz_london_open_start_min,  g_sc.kz_london_open_end_min))  return "LONDON_OPEN_KZ";
   if(MinuteInWindow(now_min, g_sc.kz_london_close_start_min, g_sc.kz_london_close_end_min)) return "LONDON_CLOSE_KZ";
   if(MinuteInWindow(now_min, g_sc.kz_asia_start_min,         g_sc.kz_asia_end_min))         return "ASIAN_KZ";
   return "";
}
```

- **NY-anchored** via `BrokerToNY()` (FORGE.mq5:6922) — broker time → UTC → NY using broker_gmt_offset + EU/US DST detection
- **Config-driven** windows from `config/scalper_config.defaults.json:208-216` (NY minute-of-day):

  | Field | Value | NY clock |
  |---|---|---|
  | `kz_asia_start_min` / `kz_asia_end_min` | 1140 / 180 | 19:00 → 03:00 next day |
  | `kz_london_open_start_min` / `kz_london_open_end_min` | 120 / 300 | 02:00 → 05:00 |
  | `kz_ny_open_start_min` / `kz_ny_open_end_min` | 420 / 600 | 07:00 → 10:00 |
  | `kz_london_close_start_min` / `kz_london_close_end_min` | 600 / 720 | 10:00 → 12:00 |

- **DST-safe** (Approach B per `docs/research/ICT_KILLZONES.md §5`): `IsEU_DST()` + `IsUS_DST()` + last/first-Sunday helpers (FORGE.mq5:6862-6920)
- **Sunday guard**: closed-market block before 17:00 NY Sunday
- **Writes to**: `g_regime.killzone`, `market_data.json:killzone` (FORGE.mq5:4050), SIGNALS schema `killzone` column, per-killzone trade cap counter, v2.7.63 killzone lot amplifier (FORGE.mq5:807)

**Implementation B — `ea/include/Forge/IctLiquidity.mqh:616-731` (Phase 2 v2.7.120 atoms)**

```mql5
bool IsInLondonKillZone(datetime t)  { return (mt.hour >= 7  && mt.hour < 10); }  // hardcoded UTC 07-10
bool IsInNewYorkKillZone(datetime t) { return (mt.hour >= 12 && mt.hour < 15); }  // hardcoded UTC 12-15
bool IsInSilverBulletWindow(datetime t) { return (mt.hour == 10 || mt.hour == 14); }  // 10-11 + 14-15 UTC
bool IsInKillZone(datetime t) {  // composite
   if(mt.hour >= 7  && mt.hour < 10) return true;
   if(mt.hour >= 12 && mt.hour < 15) return true;
   if(mt.hour >= 15 && mt.hour < 17) return true;  // collapses NY PM + London Close
   return false;
}
int GetSessionContext(datetime t) {  // returns 0..3
   if(mt.hour >= 7  && mt.hour < 10) return 1;   // LONDON_KZ
   if(mt.hour >= 12 && mt.hour < 15) return 2;   // NY_AM_KZ
   if(mt.hour >= 15 && mt.hour < 17) return 3;   // NY_PM / LONDON_CLOSE overlap
   return 0;                                     // ASIAN / DEAD_ZONE
}
```

- **Hardcoded** hours (no config knobs) — not tunable per broker or instrument
- **Treats broker time AS UTC** — comment at IctLiquidity.mqh:606-609 explicitly acknowledges this is wrong for GMT+2/+3 brokers but ships anyway
- **No DST detection** — windows shift by 1 hour winter↔summer
- **No Sunday guard**
- **Collapses NY PM into London Close** (single 15:00-17:00 UTC bucket)
- **Returns ints**, not the `NY_OPEN_KZ` / `LONDON_OPEN_KZ` / etc. strings that the chokepoint writes
- **Silver Bullet hardcoded** to {10, 14} UTC hours; not config-driven; not written to SIGNALS

#### §B.7.2 Divergence + correctness issues

| # | Issue | Impact |
|---|---|---|
| 1 | **Two sources of truth** for "what killzone is it" — chokepoint string vs. ICT-module int. They can disagree at any tick. | A liquidity-sweep atom thinks "NY_AM_KZ active" while the SIGNALS row written by the same tick records `killzone=""`. Cross-DB analysis joins break. |
| 2 | **Implementation B is not DST-safe** — broker time treated as UTC ignores broker GMT offset (+2/+3 typical) AND ignores US DST. London KZ silently shifts 2-3 hours from the intended window. | Phase 2 atoms (ChoCH, Sweep, Order Block) score liquidity events with the wrong session label. Killzone scoring weight applies in the wrong hour. |
| 3 | **No `NY_PM_KZ`** in chokepoint (§B.2 spec: 13:30-16:00 NY). Today's `kz_london_close_*` covers 10:00-12:00 NY (the AM overlap) but nothing covers PM. | The PM-reversal window — historically the second-largest move per ICT canon — is recorded as `killzone=""` (off-session). Setup attribution can't separate PM trades from dead-zone trades. |
| 4 | **NY PM and London Close conflated** in Impl B (single 15:00-17:00 UTC bucket). They are distinct ICT windows with distinct behavior — London Close is bias-handoff; NY PM is reversal/second-move. | Lot amplifier + composite gating can't differentiate the two; loses ICT-canonical signal granularity. |
| 5 | **Silver Bullet not first-class** — hardcoded UTC hours in Impl B, no config knobs, no SIGNALS column. | §B.5 schema-parity mandate not met for `silver_bullet`. Operator can't tune the precision-window definition without recompiling. |
| 6 | **Asian KZ in Impl B is implicit** (= "none of the above") — collapsed with DEAD_ZONE as code 0. | Loss of Asian-range accumulation context; can't score "OTE inside Asian range" or "LIQUIDITY_SWEEP of Asian-high at London Open" cleanly. |

#### §B.7.3 ICT-aligned recommendation

**Single source of truth**: chokepoint owns the killzone label. ICT-module atoms read it via thin wrappers — they do not re-derive from datetime. This eliminates issues #1, #2, and #6 in one move.

**Add the two missing windows**: `NY_PM_KZ` (config-driven) + `silver_bullet` (config-driven). This closes issues #3, #4, #5.

**Final canonical surface (matches §B.2)**:

| Killzone string | NY window | Config knobs (NY minute-of-day) |
|---|---|---|
| `ASIAN_KZ` | 20:00 – 00:00 (operator may extend to 03:00 as today) | `kz_asia_start_min` / `kz_asia_end_min` (existing) |
| `LONDON_OPEN_KZ` | 02:00 – 05:00 | `kz_london_open_start_min` / `kz_london_open_end_min` (existing) |
| `NY_AM_KZ` | 07:00 – 10:00 | `kz_ny_open_start_min` / `kz_ny_open_end_min` (existing — rename to `kz_ny_am_*` optional, alias-tolerated) |
| `LONDON_CLOSE_KZ` | 10:00 – 12:00 | `kz_london_close_start_min` / `kz_london_close_end_min` (existing) |
| **`NY_PM_KZ`** ← NEW | 13:30 – 16:00 | **`kz_ny_pm_start_min=810` / `kz_ny_pm_end_min=960`** (new) |
| `OFF_SESSION` | everything else | (no knob — fallthrough) |

| Silver Bullet string | NY window | Config knobs |
|---|---|---|
| `LONDON_SB` | 03:00 – 04:00 | **`sb_london_start_min=180` / `sb_london_end_min=240`** (new) |
| `AM_SB` | 10:00 – 11:00 | **`sb_am_start_min=600` / `sb_am_end_min=660`** (new) |
| `PM_SB` | 14:00 – 15:00 | **`sb_pm_start_min=840` / `sb_pm_end_min=900`** (new) |

#### §B.7.4 Implementation plan (v2.7.122 candidate ship)

Five-layer per schema-parity mandate:

1. **EA (FORGE.mq5)**:
   - Add 8 new config fields to `ScalperConfig` (kz_ny_pm_* + sb_london_* + sb_am_* + sb_pm_*)
   - Set defaults in `LoadScalperDefaults` per §B.7.3 tables
   - Extend `ComputeCurrentKillzoneLabel()` with the NY_PM check (insert after LONDON_CLOSE; order doesn't matter when ranges don't overlap)
   - Add **`ComputeCurrentSilverBulletLabel()`** mirroring the killzone helper — same NY-anchored time, same Sunday guard, returns `LONDON_SB` / `AM_SB` / `PM_SB` / `""`
   - Add `silver_bullet` field to `RegimeState` (Layer 5 atom)
   - Wire JSON config keys in `LoadScalperConfigFromFile` (JsonHasKey/JsonGetDouble for each new field)
   - Write `silver_bullet` into `market_data.json` next to `killzone`
2. **Retire Impl B** (`IctLiquidity.mqh` killzone helpers):
   - Replace `IsInLondonKillZone(t)` body with `return g_regime.killzone == "LONDON_OPEN_KZ";`
   - Replace `IsInNewYorkKillZone(t)` body with `return g_regime.killzone == "NY_AM_KZ";`
   - Replace `IsInSilverBulletWindow(t)` body with `return g_regime.silver_bullet != "";`
   - Replace `IsInKillZone(t)` body with `return g_regime.killzone != "";`
   - Replace `GetSessionContext(t)` with a lookup of `g_regime.killzone` → int (kept for analytic joins only; ICT-module scoring should consume the string)
   - Drop the `t` parameter from callers (state is per-tick, not arbitrary-time); keep the signature for compat with a deprecation comment
3. **Config defaults** (`config/scalper_config.defaults.json`):
   - Add the 8 new keys with the values from §B.7.3
4. **Env mapping** (`scripts/sync_scalper_config_from_env.py`):
   - Add `FORGE_KZ_NY_PM_START_MIN` / `_END_MIN` + `FORGE_SB_LONDON_START_MIN` / `_END_MIN` / `FORGE_SB_AM_*` / `FORGE_SB_PM_*` env-to-JSON mappings
   - Add commented-out lines to `.env.example` per "no dead env vars" mandate
5. **Schema (5-layer ship)**:
   - `SIGNALS` CREATE TABLE: add `silver_bullet TEXT` (the `killzone` column already exists)
   - `ALTER TABLE` migration in journal init: `ALTER TABLE SIGNALS ADD COLUMN silver_bullet TEXT` (idempotent via PRAGMA check)
   - `JournalRecordSignal`: append `g_regime.silver_bullet` to the placeholder list (bumps count from 139 → 140)
   - `python/scribe.py` `sync_forge_journal`: include `silver_bullet` in the column list + INSERT statement
   - `sql/forge_signals_schema.sql`: add the column to the canonical schema file

**Validation gate (per `docs/research/ICT_KILLZONES.md §9`)** before shipping:
- Tester replay with `killzones_enabled=1`, check that `killzone` and `silver_bullet` populate correctly across DST transitions (run Mar 30 + Apr 7 — week of US DST switch)
- Cross-check `g_regime.killzone == g_ict_last_killzone_active` mapping post-retirement
- Confirm no FORGE_* env knob is dead per `feedback_no_dead_env_vars` mandate

#### §B.7.5 What changes for trading logic (downstream impact)

| Subsystem | Today | Post-v2.7.122 |
|---|---|---|
| v2.7.63 killzone lot amplifier (FORGE.mq5:807) | Keys on 4 zones | Keys on 5 zones + optional SB amplifier overlay (+0.1 lot factor when SB active per §B.2) |
| Per-killzone trade cap (FORGE.mq5:8619) | 4 buckets | 5 buckets (NY PM gets its own cap) |
| §B.2 composite gating | NY_PM_KZ behavior gated as OFF_SESSION today | NY_PM_KZ activates `LIQUIDITY_SWEEP_REVERSAL` favored window per §B.2 |
| Phase 2 ICT atoms (ChoCH/Sweep/OB scoring) | Score with broken UTC-hour bucket | Score with chokepoint-true NY-anchored bucket |
| Athena UI killzone breakdown | 4 columns | 5 + Silver Bullet drill-down |

#### §B.7.6 Cross-references

Authoritative ICT killzone reference is `docs/research/ICT_KILLZONES.md` — see §2 (NY-time table), §5 (Approach B MQL5 implementation already shipped in FORGE.mq5:6862-6989), §8 (practical FORGE recommendations), §9 (validation checklist). This appendix §B.7 supersedes ICT_KILLZONES.md §6 for the **canonical FORGE killzone surface** (5 windows + 3 Silver Bullet sub-windows); ICT_KILLZONES.md remains the authoritative research/citation source for ICT canon itself.

The skill `.claude/skills/forge-monitor/SKILL.md` previously referenced `FORGE_REGIME_TAXONOMY.md §11` as the killzone atom's home doc. That file is no longer in the repo — its content has been absorbed into this appendix §B and into `ICT_KILLZONES.md`. The skill should be updated to redirect to `docs/FORGE_SETUP_ICT_MAP.md §B.2 + §B.7` (out of scope for this appendix; flagged for a follow-up housekeeping ship).

### §B.8 ICT-aligned boolean composite atoms — per-category atom catalog

This section is the **canonical atom catalog** for ICT-aligned boolean composite analysis. Every new ICT setup decision composes from these atoms — do not invent new ones without WebSearch ICT-canon backing and Appendix update.

#### §B.8.1 The pattern — 3-tier architecture (atoms / composites / gates), ISS-aligned

The full picture is **3 tiers**, not 2. ISS is already in production — its design IS the canonical ISS-aligned pattern; the 4 new category composites extend it without competing with it.

```
Tier 1 — Atoms (canonical, single source of truth)
   ~16 unique boolean evaluators in ea/include/Forge/IctScoring.mqh
   atom_mss_confirmed, atom_fvg_aligned, atom_fvg_unfilled,
   atom_choch_confirmed, atom_sweep_detected, atom_sweep_wick_quality,
   atom_ob_broken, atom_breaker_retest, atom_displacement_present,
   atom_pullback_in_ote, atom_premium_discount_aligned, atom_ob_confluence,
   atom_killzone_favorable, atom_htf_aligned, ...
   Logged as SIGNALS columns (Strategy A) or JSON blob (Strategy B per §B.8.4)
        │
        ▼
Tier 2 — Composites (multiple weighted aggregators over the same atoms)
   ┌─ ISS (general "is structure present right now?")
   │     MSS(5) + FVG(3) + ChoCH(2) = 0-10
   │     Shipped v2.7.118-120; operator-judged weights; production
   ├─ MSS_CONT_SCORE_<DIR>      — §B.8.2 Category 1 atoms, 0-10
   ├─ OTE_RETRACE_SCORE_<DIR>   — §B.8.2 Category 2 atoms, 0-10
   ├─ LIQ_SWEEP_REV_SCORE_<DIR> — §B.8.2 Category 3 atoms, 0-10
   └─ BREAKER_RETEST_SCORE_<DIR>— §B.8.2 Category 4 atoms, 0-10
        │
        ▼
Tier 3 — Gates (Mode A/B/C consumers of Tier 2 scores per §B.8.3)
   Mode A: compute + log only
   Mode B: warning de-rate (score < 5 → lot ×0.7)
   Mode C: hard block (score < 7 → gate_reason=<cat>_score_below_threshold)
```

**Why 3 tiers, not 2:**

- **Atoms are canonical.** Each atom is implemented ONCE in `IctScoring.mqh`. Multiple composites read from it — never re-derive.
- **Composites are derived, not canonical.** ISS and the 4 category composites are different *aggregations* over the same atom layer. Same primitives, different weights, different questions answered.
- **Gates are policy.** Mode A/B/C choice is operator policy per composite (start at A, promote with evidence) — not baked into the composite itself.

**Why two atomic layers (atoms + composites) instead of one:**

| Approach | Failure mode |
|---|---|
| Pure boolean composite (flat AND / majority) | Loses magnitude — a 4.99 RSI is the same as a 35 RSI at threshold 30. Creates threshold cliffs. PEMCG works at flat-majority because its atoms are already-thresholded warning bits; ICT atoms have more magnitude content. |
| Pure scored composite (no audit atoms logged) | Loses categorical clarity — "score was 6.4" doesn't tell you WHICH atoms failed. Ablation impossible. |
| **Both layers (atoms + composite)** | Atoms answer "which primitive held?"; composite answers "did enough hold, weighted appropriately?" Audit + decision split cleanly. ISS already proves this in production. |

**Why ISS is not redundant with the 4 category composites:**

ISS answers *"is the market giving us ICT structure right now?"* — a **coarse, general, always-on** signal. Used for: quick filter ("only fire ANY setup when ISS ≥ 5"), dashboard color, lot-factor amplifier on high-ISS bars, and as a Mode B warning for low-ISS bars regardless of category.

The 4 category composites answer *"should THIS specific entry category fire here?"* — a **fine, targeted, decision-layer** signal. Used for: the actual gate that decides if MSS_CONT_BUY or OTE_RETRACE_SELL fires.

Both consume the same atom layer (DRY at Tier 1). They are siblings at Tier 2, not parent-child.

**Composite naming**: prefix with category. `MSS_CONT_SCORE_<DIR>` / `OTE_RETRACE_SCORE_<DIR>` / `LIQ_SWEEP_REV_SCORE_<DIR>` / `BREAKER_RETEST_SCORE_<DIR>` with `<DIR>` ∈ {BUY, SELL}. ISS stays as `iss_score` (no direction suffix — ISS is direction-agnostic; the underlying MSS_BULL / MSS_BEAR atoms encode direction at Tier 1).

**Same atom in different composites with different weights is EXPECTED:** `atom_mss_confirmed` carries weight 5 in ISS (which is *about* structure — MSS dominates) but weight 3 in MSS_CONT_SCORE (where MSS is the precondition but the discriminator is the *other* atoms: displacement quality, FVG alignment, killzone favorability, HTF agreement). The weight is tuned to the question the composite answers. Per-composite weight tuning is the design; do not flatten to "one weight per atom across all composites".

**Weights are calibrated, not invented:** ISS's 5/3/2 was operator judgment per `project_ces_provisional.md` memory (CES was retired and replaced because it couldn't discriminate; ISS weights were chosen to give it discrimination power). The §B.8.2 weights are first-cut and require similar calibration — empirical hit-rate against known winners/losers (per `feedback_supermajority_composite_threshold` memory: calibrate composite thresholds against known winners + check block distributions before promoting from Mode A → B → C).

#### §B.8.2 Atom inventory — per entry category

The weight column shows ISS-style points; total per category = 10. Threshold = 7/10 for hard gate, 5/10 for warning (matches PEMCG supermajority rule per memory `feedback_supermajority_composite_threshold`).

**Category 1 — MSS_CONTINUATION** (entry on retrace into MSS-confirming FVG/OB):

| Atom | Source | Weight | Description |
|---|---|---|---|
| `atom_mss_confirmed` | `IctStructure.mqh` DetectBullish/BearishMSS | 3 | Swing high/low broken on close |
| `atom_displacement_present` | `g_ict_last_displacement_atr_mult ≥ 1.5` | 2 | Impulse leg ≥ 1.5× ATR (the "displacement" that creates the MSS) |
| `atom_fvg_aligned` | `Forge_GetActiveFVGAlignedWith()` | 2 | FVG exists in the MSS direction |
| `atom_fvg_unfilled` | `g_fvg_ring[i].mitigated == false` | 1 | FVG not yet retraced into |
| `atom_killzone_favorable` | `g_regime.killzone ∈ {LONDON_OPEN_KZ, NY_AM_KZ}` | 1 | Inside the institutional flow window for MSS continuation |
| `atom_htf_aligned` | `g_regime.htf_label` matches MSS direction | 1 | H1/H4 trend agreement (anti `feedback_against_market_entries`) |
| **Total** | | **10** | |

**Category 2 — OTE_RETRACEMENT** (pullback to 62-79% fib in discount/premium zone):

| Atom | Source | Weight | Description |
|---|---|---|---|
| `atom_pullback_in_ote` | fib retracement 62-79% of prior leg | 3 | Price inside the OTE band |
| `atom_premium_discount_aligned` | dealing range midpoint check | 2 | Buys in discount, sells in premium |
| `atom_fvg_confluence` | FVG in OTE zone | 2 | Structural confluence boost |
| `atom_ob_confluence` | `IctOrderBlock.mqh` OB in OTE zone (post-Phase 3) | 1 | Additional confluence |
| `atom_killzone_favorable` | `g_regime.killzone != OFF_SESSION` | 1 | Any killzone (OTE is the most session-agnostic category) |
| `atom_htf_aligned` | trend agreement | 1 | OTE is a continuation entry — counter-trend OTE = lower-conviction |
| **Total** | | **10** | |

**Category 3 — LIQUIDITY_SWEEP_REVERSAL** (sweep + ChoCH + FVG retrace):

| Atom | Source | Weight | Description |
|---|---|---|---|
| `atom_sweep_detected` | `IctLiquidity.mqh` DetectBuy/SellSideLiquiditySweep | 3 | Equal highs/lows or session extreme taken |
| `atom_sweep_wick_quality` | wick_atr_ratio ≥ 1.0 | 2 | Sweep with proportional rejection wick (magnitude-scored — use `g_ict_last_sweep_wick_atr_mult`, threshold-tier into 0/1/2) |
| `atom_choch_confirmed` | `IctLiquidity.mqh` DetectBullish/BearishChOCh | 2 | Structure shift after the sweep |
| `atom_fvg_on_reversal_leg` | FVG opposite to sweep direction | 2 | Entry zone on the retrace |
| `atom_killzone_favorable` | `g_regime.killzone ∈ {LONDON_OPEN_KZ, NY_PM_KZ}` | 1 | Sweeps cluster at session opens + PM reversal window |
| **Total** | | **10** | |

**Category 4 — BREAKER_RETEST** (broken OB acts as new S/R):

| Atom | Source | Weight | Description |
|---|---|---|---|
| `atom_ob_broken` | OB traded through with displacement | 3 | Prior OB invalidated by impulse (Phase 3 atom) |
| `atom_breaker_retest` | price retraces to broken OB zone | 3 | Entry trigger — touch the breaker |
| `atom_fvg_confluence` | FVG aligned with retest direction | 2 | Unicorn-pattern boost (Breaker ∩ FVG, per ICT canon) |
| `atom_killzone_favorable` | `g_regime.killzone != OFF_SESSION` | 1 | Any killzone |
| `atom_htf_aligned` | trend agreement | 1 | Breaker continuation in trend |
| **Total** | | **10** | |

#### §B.8.3 Gate decision pattern

Three gate modes per composite (matches `FORGE_PEMCG_ICT_INTEGRATION.md` 3-mode plan):

| Mode | Gate condition | Use case |
|---|---|---|
| **Mode A — Compute + log only** | always pass; score logged | New composite; validation phase; building empirical baseline |
| **Mode B — Warning gate** | `score < 5` → lot factor de-rate (×0.7) but trade fires | Composite that adds value but isn't proven enough to hard-block |
| **Mode C — Hard gate** | `score < 7` → BLOCK with `gate_reason=<category>_score_below_threshold` | Validated composite, supermajority threshold |

Mode B is the right default for a fresh ICT composite — preserve trade flow, attribute the score, ablate after 100+ trades. Promote to Mode C only with evidence.

#### §B.8.4 Schema impact (per schema-parity mandate)

Two strategies depending on cardinality:

**Strategy A — full-column** (use when total atom count across all categories ≤ 24, i.e. plenty of column budget):

Add 1 SIGNALS column per atom (boolean 0/1) + 1 score column per category. ~20-24 new columns. Best for ablation studies.

**Strategy B — selective-column + JSON blob** (use when atom count grows past 24):

Add only the score columns (4 — one per category) + 1 `ict_atoms_passed` TEXT column holding a comma-separated atom list. Per the selective-column rule (skill SKILL.md `selective-column rule for high-cardinality diagnostic data`). Trade ablation precision for column-budget headroom.

**Recommendation**: ship **Strategy A** for v2.7.122 — current atom count = 19 (6+6+5+5 minus overlaps like `atom_killzone_favorable` which collapse to one shared atom). Headroom is fine; ablation precision is worth it during the validation phase.

#### §B.8.5 Atom reuse across categories

Three atoms are shared across multiple categories. Implement once, read everywhere:

| Shared atom | Used by | Shared logic |
|---|---|---|
| `atom_killzone_favorable` | All 4 (with different killzone sets) | Single function `IsKillzoneFavorableFor(category)` in `IctScoring.mqh` |
| `atom_htf_aligned` | MSS_CONT / OTE / BREAKER (not LIQ_SWEEP — sweep entries are by definition counter-trend at the local frame) | Reads `g_regime.htf_label` + direction |
| `atom_fvg_confluence` / `atom_fvg_aligned` / `atom_fvg_on_reversal_leg` | All 4 (with direction variant) | Single `Forge_GetActiveFVGAlignedWith()` parameterized by direction |

#### §B.8.6 Legacy composites still apply (PEMCG / UMCG / CVCSM)

Existing boolean composites are NOT deprecated:

- **PEMCG** (7-atom warning count, supermajority 5/7) — still gates Layer 1/2/3 reversal blocks per `FORGE_PEMCG_ARCHITECTURE.md`
- **UMCG** (Unified Market Condition Gate) — still gates entry direction
- **CVCSM** (Counter-Volume Cooldown State Machine) — still manages SL-only cooldown

These are pure-boolean composites with majority/supermajority thresholds. They predate the ISS scored-composite pattern but solve a similar problem cleanly. **Going-forward rule** (per Mode B above): new ICT composites use the weighted-score pattern; legacy boolean composites stay as-is until a deliberate restructure.

#### §B.8.7 Implementation home

The atom evaluators live in `ea/include/Forge/IctScoring.mqh` (Phase 4, currently scaffolded — body deferred to v2.7.122). Each atom is a function `bool Atom_<name>(int direction)` returning 0/1. The score function `ComputeCategoryScore(category, direction)` sums the weights for atoms returning 1. Mode A/B/C gate selection is a `ScalperConfig.ict_score_mode_<category>` knob (int 0/1/2).

The chokepoint reads `ComputeCategoryScore()` per tick per direction, writes both the score and the atom-by-atom booleans to the SIGNALS row. No re-derivation in setup-trigger code — single computation, multiple readers.

### §B.9 What this appendix changes vs Appendix A

| Item | Appendix A (was) | Appendix B (now) |
|---|---|---|
| Target entry categories | 6 | **4** |
| Killzone treatment | Implicit (per-setup gating) | **Explicit dimension — every trade tagged** |
| Migration milestones | M7 / M8 / M9 / M10 / M11 (5 folds) | **M7 / M8 / M9 (3 folds)** — DISPLACEMENT and TREND_CONTINUATION dissolve |
| SIGNALS schema | (Appendix A silent) | **+2 columns: `killzone`, `silver_bullet`** |
| Naming for ops/colleague discussion | Internal codenames | **ICT-canonical session names** (Asian / London Open / NY AM / NY PM / London Close + Silver Bullet sub-windows) |

§B does not invalidate A — A's strategic frame (FORGE → ICT-canonical IS the design target, not deferred) is preserved verbatim. B refines the target endpoint from 6 to 4 entry categories and codifies the session axis as a first-class dimension.

## §9 Changelog

- **2026-05-15** — Initial catalog. 28 active FORGE setups mapped to 6 ICT-canonical categories. Per-category deep-dive (§3.1-3.6). Full alphabetical inventory (§4). What's missing from ICT canon (§5 — Phase 3-5 work). Consolidation proposal (§6 — NOT recommended today, but rename map is the canonical target for future restructure).
- **2026-05-15** — Appendix A added (§8) capturing operator-confirmed strategic intent. Reverses §6's "don't rename today" recommendation — consolidation IS the active design target. Migration milestones M0-M13 sequence the FORGE → ICT-canonical reorganization alongside Phase 2-5 ICT atom work. Cross-system impact catalog (A.4). Changes next-ship target from "v2.7.122 selective-12 columns" to "M1 Phase 2 validation pass + M2/M3 chart-pattern retirement".
- **2026-05-15** — Appendix B added (§10). Collapses 6 entry categories → 4 ICT-canonical (`MSS_CONTINUATION` / `OTE_RETRACEMENT` / `LIQUIDITY_SWEEP_REVERSAL` / `BREAKER_RETEST`). Drops `DISPLACEMENT_ENTRY` (= MSS impulse leg, not separate) and `TREND_CONTINUATION` (= MSS or OTE depending on structural read, not separate primitive). Preserves operator's Category G as **killzone dimension** with ICT-canonical session names: `ASIAN_KZ` / `LONDON_OPEN_KZ` / `NY_AM_KZ` / `NY_PM_KZ` / `LONDON_CLOSE_KZ` + Silver Bullet sub-windows (`LONDON_SB` / `AM_SB` / `PM_SB`). Migration M7-M11 collapses to M7-M9. New schema columns `killzone` + `silver_bullet` per schema-parity mandate. Citations §B.6 ground category choices in ICT canon.
- **2026-05-15** — Appendix B §B.7 added: current FORGE killzone implementation review + ICT-aligned recommendations. Documents the two-source-of-truth divergence between `FORGE.mq5:6977 ComputeCurrentKillzoneLabel()` (NY-anchored, DST-safe, config-driven, authoritative) and `IctLiquidity.mqh:616-731 IsInLondonKillZone/IsInNewYorkKillZone/...` (hardcoded UTC-hour, no DST, broken for non-UTC brokers). Identifies 6 correctness/divergence issues. Prescribes the v2.7.122 alignment ship: add `NY_PM_KZ` (5th killzone, 13:30-16:00 NY) + 3 Silver Bullet helpers, retire Impl B to thin wrappers reading `g_regime.killzone`, full 5-layer schema-parity ship for new `silver_bullet` column. Cross-references `docs/research/ICT_KILLZONES.md` as authoritative ICT canon source. Flags stale skill reference to `FORGE_REGIME_TAXONOMY.md` (no longer in repo) for housekeeping follow-up.
- **2026-05-15** — Appendix B §B.8 added: ICT-aligned boolean composite atoms — per-category atom catalog. Two-layer pattern (boolean atoms = audit; scored composite = decision). 19 unique atoms across 4 ICT entry categories, ISS-style weights summing to 10/category. 3 shared atoms (`atom_killzone_favorable`, `atom_htf_aligned`, FVG-confluence) implemented once + read across categories. Gate modes A/B/C (compute-only / warning de-rate / hard-block) match `FORGE_PEMCG_ICT_INTEGRATION.md` 3-mode plan. Strategy A schema (full per-atom column) recommended for v2.7.122 — 19 atoms within column budget. Implementation home = `ea/include/Forge/IctScoring.mqh` (Phase 4, currently scaffolded). Legacy PEMCG / UMCG / CVCSM composites preserved; new ICT composites use weighted-score pattern.
- **2026-05-15** — **Phase A ICT atoms shipped (v2.7.123)**: 5 new atoms behind individual enable flags (Mode A — compute + log only, default OFF). `atom_killzone_favorable` (shared per-category; reads `g_regime.killzone`), `atom_htf_aligned` (shared; reads `g_regime.htf_label` + `h1_trend`), `atom_pullback_in_ote` (fib 62-79% retrace per [innercircletrader.net OTE pattern](https://innercircletrader.net/tutorials/ict-optimal-trade-entry-ote-pattern/)), `atom_premium_discount_aligned` (50% equilibrium midpoint per [arongroups equilibrium zones](https://arongroups.co/technical-analyze/ict-equilibrium-zones/)), `atom_fvg_on_reversal_leg` (Phase A simplified wrapper of existing FVG-aligned lookup; full LIQ_SWEEP_REV context comes in Phase B composite). Full 5-layer schema-parity ship: EA CREATE+ALTER+JournalRecordSignal + scribe.py CREATE+ALTER+SELECT+INSERT + placeholder count 141 → 146 + .env.example + sync mappings + defaults.json. IctScoring.mqh body filled (49 → 232 lines). Pure-function evaluators per §I.8 plug-and-play principles. Phase B (composite scoring) is the next ship.
- **2026-05-15** — §B.8.1 refactored from 2-tier to **3-tier architecture** (atoms / composites / gates) to make ISS-aligned design explicit. ISS is now formally placed at Tier 2 alongside the 4 new category composites — siblings, not children, all weighted-score composites aggregating from the same canonical atom layer. Documents why ISS is NOT redundant with category composites (ISS = "is structure present?" coarse general signal; category composites = "should THIS category fire?" fine targeted decision). Clarifies per-composite weight tuning is expected: `atom_mss_confirmed` has weight 5 in ISS but weight 3 in MSS_CONT_SCORE — both correct, tuned to the question each composite answers. Weights are calibrated empirically (per `feedback_supermajority_composite_threshold`), not invented; §B.8.2 first-cut weights require validation before Mode A → B → C promotion.
- **2026-05-15** — New living design doc `docs/FORGE_FAST_MARKET_SWEEP_RESCUE.md` (FMSR) added as v2.7.123 candidate ship. FMSR implements the LIQUIDITY_SWEEP_REVERSAL §B.2 category as a primary-trade-independent opposite-direction pending-order arm — fires on fast-market sweep detection, places OTE retrace limits, INDEPENDENT of any primary-trade TP1 hit. Closes the gap that existing `BUY_LIMIT_RECOVERY` / `SELL_LIMIT_RECOVERY` only fire post-TP1. §15 of that doc is a living design surface for recovery features + both-legs capture (continuation + reversal). Track A stopgap applied same day via operator's `.env` (lot factor 0.25→0.5, expiry 4→8 bars for both recoveries).
- **2026-05-16** — **Canonical case study added for Category 3 (LIQUIDITY_SWEEP_REVERSAL)**: [`FORGE_CASE_STUDY_2026_03_30_LIQ_SWEEP_REV_PATTERN.md`](FORGE_CASE_STUDY_2026_03_30_LIQ_SWEEP_REV_PATTERN.md). Documents 2026-03-30 Asian-session G5001 win (+$1,212) + G5003 loss (−$3,655) on identical sweep+ChoCH+FVG patterns 49 minutes apart at near-identical prices. Establishes the **entry-pattern vs execution-geometry split**: both setups score 9/10 on the §B.8.2 LIQ_SWEEP_REV_SCORE_BUY atoms (correct fires), but the global trend-ride geometry (staged-add @ +300 pts favorable + wave-amp ×2) weaponized the amplifier on a chop-reversion scalp. Documents the chop-scalp geometry profile (TP1=0.4×ATR, BE-snap, staged-add disabled, wave-amp disabled, cooldown=600s) for the v2.7.125 `LIQUIDITY_SWEEP_REVERSAL_BUY` setup. Mode A → B → C ship sequence specified in §6. Per `feedback_chop_scalp_one_tp_fast_sl.md` + `feedback_trade_setup_analysis_framework.md`. Linked from §3.3. Skill mandate added in `forge-monitor/SKILL.md §B5` so future monitoring sessions audit every TAKEN against this pattern.
- **2026-05-17** — **v2.7.136 — ICT canonical naming alignment (pre-M7 cleanup)**. Audit caught naming drift between v2.7.133/134 implementation and §B.8.2 atom catalog. Fixes: SIGNALS column `atom_breaker_present` → `atom_ob_broken` (matches §B.8.2 Cat 4 weight=3 atom verbatim); global rename in IctOrderBlock.mqh. Adds: `atom_ob_confluence_buy` / `_sell` SIGNALS columns + `Forge_HasOBConfluence()` helper — wires §B.8.2 Cat 2 OTE_RETRACE weight-1 atom that was stubbed at `score += 0` in v2.7.124 marked "post-Phase 3". OB ring rebuild order in ForgeEvalAtoms moved BEFORE composite score blocks so OTE Cat 2 reads fresh atom_ob_confluence. Glossary §3 atom catalog gets 6 missing entries per `feedback_glossary_update_mandate`. SIGNALS placeholder count 166 → 168. Schema-parity byte-stable when both flags OFF.
- **2026-05-17** — **v2.7.135 — Phase 3 OB env knobs**. 4 hardcoded params promoted to env-tunable (DISPLACEMENT_MIN_ATR, LOOKBACK_BARS, RETEST_TOLERANCE_ATR, FVG_CONFLUENCE_TOLERANCE_ATR). Full 5-layer wire per feedback_no_dead_env_vars.
- **2026-05-17** — **v2.7.134 Phase 3b — BREAKER_RETEST schema parity 5-layer**. Mirrors F-β.1 v2.7.130 pattern. 7 new SIGNALS columns: atom_breaker_present / atom_breaker_retest_buy / atom_breaker_retest_sell / atom_breaker_fvg_buy / atom_breaker_fvg_sell / breaker_retest_score_buy / breaker_retest_score_sell. EA CREATE TABLE + idempotent ALTER TABLE + JournalRecordSignal INSERT col list + VALUES bind. python/scribe.py CREATE schema + ALTER block + sync_forge_journal SELECT col list + value extract + insert_params + INSERT col list + VALUES placeholder count bump 159 → 166. All-zero rows when `FORGE_COMPOSITE_BREAKER_RETEST_SCORE_ENABLED=0` (default — schema-parity byte-stable vs v2.7.133). Closes the per-atom + per-score observability gap from v2.7.133 (composite computed, but only enable-flag in config — no SIGNALS columns to inspect).
- **2026-05-17** — **v2.7.133 Phase 3 OB body**. `ea/include/Forge/IctOrderBlock.mqh` full body (41-line scaffold → 272 lines): OrderBlockZone struct, 16-slot ring buffer with 6h M5 lifespan, displacement+previous-opposite-candle+FVG-confirmation detection, body-close-past-extreme broken-state tracking, breaker-retest tracking (price within 0.5×ATR of broken OB level), FVG-confluence atom (FVG midpoint within 0.5×ATR of OB level). Exports `g_ict_last_breaker_*` globals consumed by `IctScoring.mqh::ComputeCategoryScore(category=4)` — was stub returning 0. Closes the gap from F-β.1 (3 of 4 categories scoring) to all 4 categories alive. ICT canon via WebSearch citations in module docstring per skill §I.5 + §I.5a (mql5-docs-first mandate). New `composite_breaker_retest_score_enabled` config field + JSON loader + sync mapping + .env.example + defaults.json — full 5-knob wire per `feedback_no_dead_env_vars`. Detection params (displacement_min_atr=1.5, lookback_bars=50, retest_tolerance_atr=0.5, fvg_confluence_tolerance_atr=0.5) hardcoded for v2.7.133 — env knobs deferred to v2.7.135.
- **2026-05-16** — **v2.7.132 ICT zone-leading broker-comment scheme shipped**. New canonical comment shape `<ZONE>_<ORDER_TYPE>|<CAT>_<DIR>|G<ID>|<TP_OR_LEG>|<KZ_DETAIL>|<CONV>[|<SK_DETAIL>]` applied to ALL 11 comment builders in ea/FORGE.mq5 simultaneously (per operator decision "apply to new trades, forget old trades" — single ship, no incremental rollout). Helper module `ea/include/Forge/IctComment.mqh` expanded with 5 helpers + canonical builder + OnInit self-test. Canonical reference doc `docs/FORGE_ICT_COMMENT_CODES.md` captures the 24 zone × order-type prefixes, 4 ICT category codes, killzone/silver-knife detail codes, conviction-tag derivation from composite score, length budget verification, parser implementation notes. Consumer at FORGE.mq5:3529 dual-parses new shapes (KZ_/SK_/OFF_) + legacy SCALP_* for in-flight pre-migration positions. Legacy SCALP_* family becomes dead code from this ship forward.
- **2026-05-16** — **v2.7.131 magic-collision safety**: `SeedScalperGroupCounter()` added to OnInit (FORGE.mq5:16054). Scans PositionsTotal + OrdersTotal across primary/cascade/recovery magic bands, seeds `g_scalper_group_counter` from max observed group_id. Closes latent collision risk on EA reload with open EA-native groups (G5001-G5005). Counter-exhaustion warning at counter ≥ 9900 (within 100 of the 9999 primary-band ceiling). Skill-rule §I.5a (`feedback_google_mql5_before_assumptions`) also shipped same day — mandates WebSearch of mql5.com docs before asserting platform facts.
- **2026-05-16** — **F-β.1 shipped (v2.7.130)**: composite Mode-A logging enable — 6 flag flips in `.env` (3 atoms + 3 composites), zero EA-code change (hot reload picks up via `make scalper-env-sync`). Atoms ON: `FORGE_ICT_ATOM_PULLBACK_IN_OTE_ENABLED` / `..._PREMIUM_DISCOUNT_ALIGNED_ENABLED` / `..._FVG_ON_REVERSAL_LEG_ENABLED` (the remaining 3 swing-array readers; KILLZONE_FAVORABLE + HTF_ALIGNED already ON since v2.7.123). Composites ON: `FORGE_COMPOSITE_MSS_CONT_SCORE_ENABLED` / `..._OTE_RETRACE_SCORE_ENABLED` / `..._LIQ_SWEEP_REV_SCORE_ENABLED`. Mode A — populates SIGNALS columns (`mss_cont_score_buy/sell`, `ote_retrace_score_buy/sell`, `liq_sweep_rev_score_buy/sell`) instead of always-0, ZERO trade-flow change. BREAKER_RETEST composite deferred until Phase 3 `IctOrderBlock.mqh` body (§B.8.7). Validation gate for F-β.2 (Mode B = warning de-rate at score<5): tester replay + histogram against `docs/missed_opportunities/INDEX.md` 9-miss corpus + G5006/G5048 known losers per §B.8.2 — must show clear win/loss bimodality before flipping to Mode B. `.env.example` knob documentation pre-existed (lines 2344-2346, commented = OFF default for production safety per `feedback_no_dead_env_vars`). `defaults.json` stays at 0 — production-safe OFF default; operator's `.env` opts in. Per skill §I.5 (no schema change needed — columns already exist from Phase B scaffolding) + §I.6 (forward path / new ICT work). Unblocks all downstream Mode B/C work on the 3 active categories.
- **2026-05-16** — **F-α shipped (v2.7.122 candidate)**: §B.7.4 killzone alignment ship — adds `NY_PM_KZ` (5th canonical KZ, 13:30-16:00 NY) + 3 Silver Bullet sub-windows (`LONDON_SB` 03:00-04:00, `AM_SB` 10:00-11:00, `PM_SB` 14:00-15:00). Retires `IctLiquidity.mqh:616-731` Impl B helpers (`IsInLondonKillZone` / `IsInNewYorkKillZone` / `IsInSilverBulletWindow` / `IsInKillZone` / `GetSessionContext`) from hardcoded UTC-hour bodies to thin wrappers reading canonical `g_regime.killzone` / `g_regime.silver_bullet` — closes all 6 divergence/correctness issues from §B.7.2 (Impl B was wrong for GMT+2/+3 brokers AND across DST). Full 5-layer schema-parity ship per `feedback_no_dead_env_vars` + macd-bug-class avoidance pattern: EA `ScalperConfig` +8 fields / `LoadScalperDefaults` / `LoadScalperConfigFromFile` JSON loaders / `ComputeCurrentKillzoneLabel()` extended / new `ComputeCurrentSilverBulletLabel()` / `RegimeState` += `silver_bullet` / per-tick assignment / `WriteMarketData` JSON output / `JournalRecordSignal` self-populate (NO signature thread — same anti-bug pattern as v2.7.63 macd_hist) / `CREATE TABLE SIGNALS` +col / INSERT col list +col / VALUES bind +col / ALTER TABLE migration + index; `python/scribe.py` CREATE schema + ALTER block + `sync_forge_journal` SELECT + value extract + insert_params + INSERT col list + VALUES placeholder count 158→159; `config/scalper_config.defaults.json` +8 keys; `scripts/sync_scalper_config_from_env.py` +8 env mappings; `.env.example` +8 commented blocks. Default state: zero trade-behavior change at default knobs (Mode A audit — `silver_bullet` column logs real values, all 4 categories now have CORRECT `atom_killzone_favorable` inputs vs. previously-divergent Impl B). Validation gate post-ship per `research/ICT_KILLZONES.md §9`: tester replay across Mar 30 + Apr 7 (US DST switch week); confirm `killzone` + `silver_bullet` populate correctly through transitions. Unblocks F-β.1 (composite Mode-A logging + histogram against `docs/missed_opportunities/INDEX.md` 9-miss corpus). Path to F-γ (Cell C2 → D2 Mode B promotion) per `FORGE_ICT_PEMCG_COMBINATIONS.md §4.3` is gated on histogram validation.
