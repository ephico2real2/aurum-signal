# FORGE Glossary — terms, acronyms, parameters, variables

**Single source of truth** for every name, acronym, parameter, variable, struct field, and config knob that FORGE invents or adapts. If a term is used anywhere in `ea/`, `python/`, `docs/`, `config/`, `.claude/skills/forge-monitor/`, `.env`, or the SIGNALS schema, it MUST appear here.

**Update mandate**: every ship that introduces, renames, or removes a term MUST update this file in the SAME PR. Skill mandate at `.claude/skills/forge-monitor/SKILL.md §I.12` enforces this. The `MANDATORY: Acronym discipline` rule (skill §later) also points here.

**How to read this file**:
- Sections are ordered: ICT canon → FORGE atom catalog → composites → state machines → categories → variables → config → recovery/risk → ops/infrastructure.
- Each entry is **Term — expansion — short definition — where defined**. Long definitions live in the canonical docs cited.
- Synonyms are noted inline (e.g. `KZ = killzone`).

---

## §1 ICT canon — terms we adopt from Inner Circle Trader theory

| Term | Expansion | Definition | Canonical doc |
|---|---|---|---|
| **ICT** | Inner Circle Trader | The trading methodology codified by Michael J. Huddleston. FORGE's design target as of v2.7.118+. | `docs/FORGE_SETUP_ICT_MAP.md §8 Appendix A` |
| **MSS** | Market Structure Shift | A confirmed swing-high (BUY context) or swing-low (SELL context) break with displacement — signals a regime change from the prior trend. | `ea/include/Forge/IctStructure.mqh`; `FORGE_SETUP_ICT_MAP.md §B.8.1` |
| **ChoCH** | Change of Character | An early structure shift — break of the most recent minor swing — that often precedes a full MSS. Less committal than MSS. | `ea/include/Forge/IctLiquidity.mqh` |
| **BOS** | Break of Structure | Continuation print — break of the SAME-direction prior swing extreme (BUY breaks prior swing-high, SELL prior swing-low). Confirms trend, distinct from MSS (which reverses). | ICT canon; not yet a separate FORGE atom |
| **FVG** | Fair Value Gap | A 3-candle imbalance — middle candle's body covers a gap between the first candle's wick and the third candle's wick. Tracked with state (untouched / partially-filled / mitigated / invalidated). | `ea/include/Forge/IctStructure.mqh` FVG state machine |
| **OB** | Order Block | The last opposite-color candle before an impulse leg — institutional accumulation/distribution. Has state (virgin / touched / mitigated / broken). | `ea/include/Forge/IctOrderBlock.mqh` (scaffold; Phase 3) |
| **Breaker** | Breaker Block | An OB that's been traded through and now flips polarity — old support becomes new resistance (or vice versa). Used for retest entries. | `ea/include/Forge/IctOrderBlock.mqh` (scaffold; Phase 3) |
| **PD Array** | Premium / Discount Array | Collection of price levels (OB, FVG, equilibrium) used to identify discount (below 50% of dealing range) for BUY entries and premium (above 50%) for SELL entries. | `FORGE_SETUP_ICT_MAP.md §B.8.2 Category 2` |
| **OTE** | **Optimal Trade Entry** | The 62-79% Fibonacci retracement zone of the most recent impulse leg, in the premium/discount half aligned with HTF bias. The "sweet spot" retrace zone for ICT entries. NOT a price level — a band. | `ea/include/Forge/IctScoring.mqh` `Atom_PullbackInOTE`; `FORGE_SETUP_ICT_MAP.md §B.8.2 Category 2` |
| **Equilibrium (EQ)** | n/a | The 50% midpoint of the dealing range. Above EQ = premium; below = discount. | `FORGE_SETUP_ICT_MAP.md §B.8` |
| **Premium** | n/a | The upper half (above EQ) of the active dealing range. SELL setups want price in premium. | as above |
| **Discount** | n/a | The lower half (below EQ) of the active dealing range. BUY setups want price in discount. | as above |
| **Liquidity Sweep** | n/a | Wick beyond a known liquidity pool (equal H/L, PDH/PDL, PWH/PWL, Asian H/L, session H/L) followed by close back inside — signals stop hunt and likely reversal. | `ea/include/Forge/IctLiquidity.mqh` |
| **Sweep Rejection** | n/a | Magnitude of the wick beyond the swept level relative to the candle body — proxy for rejection quality. Logged as `ict_sweep_rejection_score` (v2.7.123+). | FORGE.mq5 (search `ict_sweep_rejection_score`) |
| **Displacement** | n/a | An impulse leg with body/ATR ratio strong enough to confirm momentum direction. Used to validate MSS prints. | `FORGE_SETUP_ICT_MAP.md §B.8.2 Category 1`; FORGE.mq5 `g_eval_m5_velocity_5bar_signed` |
| **PDH / PDL** | Previous Day High / Low | The high/low of the prior trading day. Common liquidity targets. | `FORGE_SETUP_ICT_MAP.md §B.8` |
| **PWH / PWL** | Previous Week High / Low | Same, one week back. | as above |
| **Asian H / L** | Asian session High / Low | The high/low of the Asian session — frequently swept at London Open. | as above |
| **Killzone (KZ)** | n/a | A time-of-day window when institutional activity concentrates. FORGE uses 5 NY-anchored KZs (see §5 below) + 3 Silver Bullet sub-windows. | `FORGE_SETUP_ICT_MAP.md §B.7`; `docs/research/ICT_KILLZONES.md` |
| **Silver Bullet (SB)** | n/a | A 60-minute hyper-concentrated sub-window within a KZ. Three exist: LONDON_SB (03:00-04:00 NY), AM_SB (10:00-11:00 NY), PM_SB (14:00-15:00 NY). | `FORGE_SETUP_ICT_MAP.md §B.7.3` |
| **HTF** | Higher Time Frame | Frames at or above H1 (typically H1/H4/D1). Used for bias alignment. | `Atom_HTFAligned` in `IctScoring.mqh` |
| **LTF** | Lower Time Frame | Frames at or below M5 (typically M1/M5). Used for entry timing. | n/a |

---

## §2 FORGE entry categories (the canonical 4)

Per `FORGE_SETUP_ICT_MAP.md §B.2`. Every new setup MUST slot into one. No 5th category.

| Code | Full name | What | Atom set | Composite (v2.7.124+) |
|---|---|---|---|---|
| **MSS_CONT** | MSS_CONTINUATION | MSS confirmed by a displacement leg; entry on retrace into the FVG/OB the impulse created | MSS(3) + displacement(2) + FVG_aligned(2) + FVG_unfilled(1) + KZ_favorable(1) + HTF_aligned(1) = 10 | `mss_cont_score_buy` / `mss_cont_score_sell` |
| **OTE_RETRACE** | OTE_RETRACEMENT | Pullback to 62-79% fib in discount (BUY) or premium (SELL) zone, with FVG/OB confluence | pullback_in_ote(3) + premium_discount(2) + FVG_confluence(2) + OB_confluence(1, Phase 3) + KZ_favorable(1) + HTF_aligned(1) = 10 | `ote_retrace_score_buy` / `ote_retrace_score_sell` |
| **LIQ_SWEEP_REV** | LIQUIDITY_SWEEP_REVERSAL | Sweep of equal highs/lows or session H/L followed by ChoCH; entry on first FVG retrace | sweep_detected(3) + sweep_wick_quality(2) + choch_confirmed(2) + FVG_on_reversal_leg(2) + KZ_favorable(1) = 10 | `liq_sweep_rev_score_buy` / `liq_sweep_rev_score_sell` |
| **BREAKER_RETEST** | BREAKER_RETEST | OB that's been traded through, now retests as new S/R, with FVG confluence | ob_broken(3) + breaker_retest(3) + FVG_confluence(2) + KZ_favorable(1) + HTF_aligned(1) = 10 | **Deferred** to Phase 3 (Phase D ship — needs IctOrderBlock.mqh body) |

---

## §3 FORGE atom catalog (current — v2.7.124)

Per `FORGE_SETUP_ICT_MAP.md §B.8.2`. Each atom is a pure function in `ea/include/Forge/*.mqh` and exports a `g_ict_last_atom_*` global. SIGNALS column matches the global name.

| Atom (function) | Module | Direction-aware? | Category-aware? | SIGNALS columns |
|---|---|---|---|---|
| `Atom_KillzoneFavorable(category, direction)` | IctScoring.mqh | yes (symmetric) | yes (4 categories) | `atom_killzone_favorable` (MSS_CONT/BUY legacy v123) + `atom_kz_fav_mss_cont` / `_ote` / `_liq_sweep` / `_breaker` (v124) |
| `Atom_HTFAligned(direction)` | IctScoring.mqh | yes | no | `atom_htf_aligned` (BUY legacy v123) + `atom_htf_aligned_buy` / `atom_htf_aligned_sell` (v124) |
| `Atom_PullbackInOTE(direction)` | IctStructure.mqh | yes | no | `atom_pullback_in_ote` |
| `Atom_PremiumDiscountAligned(direction)` | IctStructure.mqh | yes | no | `atom_premium_discount_aligned` |
| `Atom_FVGOnReversalLeg(direction)` | IctScoring.mqh | yes | no | `atom_fvg_on_reversal_leg` |
| `g_iss_mss` (existing, read by Atom_MSS) | IctStructure.mqh | yes (signed) | n/a | (read by composites; no own column yet) |
| `g_ict_last_liquidity_sweep_recent` | IctLiquidity.mqh | n/a | n/a | (composite-only input) |
| `g_ict_last_sweep_rejection_score` | IctLiquidity.mqh | n/a | n/a | `ict_sweep_rejection_score` |
| `g_ict_last_choch_buy_count` / `_sell_count` | IctLiquidity.mqh | yes (split) | n/a | (composite-only input) |
| `g_ict_last_fvg_count_active` / `g_fvg_ring_count` | IctStructure.mqh | n/a | n/a | (composite-only input) |
| `Forge_GetActiveFVGAlignedWith(direction, price, &zone)` | IctStructure.mqh | yes | n/a | (lookup helper; no own column) |

---

## §4 FORGE composite scoring (Phase B — v2.7.124+)

Unified function: `ComputeCategoryScore(int category, int direction)` in `IctScoring.mqh`. Returns 0-10 weighted sum of relevant atoms.

| Composite | Category code | Active in v2.7.124? | Mode (current) | Enable flag |
|---|---|---|---|---|
| MSS_CONT score | 1 | yes (compute + log) | A — log only | `FORGE_COMPOSITE_MSS_CONT_SCORE_ENABLED` |
| OTE_RETRACE score | 2 | yes (compute + log) | A — log only | `FORGE_COMPOSITE_OTE_RETRACE_SCORE_ENABLED` |
| LIQ_SWEEP_REV score | 3 | yes (compute + log) | A — log only | `FORGE_COMPOSITE_LIQ_SWEEP_REV_SCORE_ENABLED` |
| BREAKER_RETEST score | 4 | **no** (stub returns 0) | n/a until Phase 3 | n/a |

**Mode taxonomy** (per `FORGE_PEMCG_ICT_INTEGRATION.md` 3-mode plan):
- **Mode A** — compute + log only, no gate, no trade-flow impact. Default for new composites.
- **Mode B** — composite logged AND used as a warning derate (lot factor reduction) but does NOT block trades.
- **Mode C** — composite hard-gates trades. Score below threshold → SKIP with canonical SKIP code.

---

## §5 Killzones (the 5 canonical + 3 SB sub-windows)

Per `FORGE_SETUP_ICT_MAP.md §B.7` and `docs/research/ICT_KILLZONES.md`. All times NY-anchored (`America/New_York` with DST). Read from `g_regime.killzone` — DO NOT re-derive from `MqlDateTime`.

| Code | Window (NY local) | Used for |
|---|---|---|
| `ASIAN_KZ` | 19:00-23:00 prior day (Sun-Thu) | Range-bound; sets Asian H/L liquidity pools |
| `LONDON_OPEN_KZ` | 02:00-05:00 | High volatility; sweeps Asian range |
| `NY_AM_KZ` (LONDON Close overlap) | 07:00-10:00 | Highest volatility; primary trend session |
| `LONDON_CLOSE_KZ` | 10:00-12:00 | London exit liquidity; afternoon trend forecast |
| `NY_PM_KZ` | 13:30-16:00 | Afternoon trend continuation or fade |
| `OFF_SESSION` | All other times (incl. 12:00-13:30 gap, 16:00-19:00 gap) | No setups (or relaxed gates depending on policy) |
| `LONDON_SB` | 03:00-04:00 | Silver Bullet sub-window inside LONDON_OPEN_KZ |
| `AM_SB` | 10:00-11:00 | Silver Bullet sub-window straddling NY_AM_KZ / LONDON_CLOSE_KZ boundary |
| `PM_SB` | 14:00-15:00 | Silver Bullet sub-window inside NY_PM_KZ |

Per-category KZ favorability (per `Atom_KillzoneFavorable`):
- **MSS_CONT**: LONDON_OPEN_KZ + NY_AM_KZ
- **OTE_RETRACE**: any non-OFF_SESSION
- **LIQ_SWEEP_REV**: LONDON_OPEN_KZ + LONDON_CLOSE_KZ
- **BREAKER_RETEST**: any non-OFF_SESSION

---

## §6 Legacy / chart-pattern setup names (still in code; pre-ICT-rename)

These are the 28 legacy setups slated for fold under M7-M11 per `FORGE_SETUP_ICT_MAP.md §6`. Recorded here so future operators can map old → new.

| Legacy code | What | Future ICT home |
|---|---|---|
| `BB_BREAKOUT_BUY` / `_SELL` | Bollinger Band breakout | MSS_CONTINUATION |
| `BB_BOUNCE_BUY` / `_SELL` | BB-band rejection bounce | OTE_RETRACEMENT |
| `BB_EXHAUSTION_REVERSAL_BUY` / `_SELL` | BB exhaustion reversal (PEMCG-gated) | LIQUIDITY_SWEEP_REVERSAL |
| `MOMENTUM_DUMP_SELL` | Bearish exhaustion sell | LIQUIDITY_SWEEP_REVERSAL |
| `MOMENTUM_PUMP_BUY` | Bullish exhaustion buy | LIQUIDITY_SWEEP_REVERSAL |
| `DOUBLE_TOP_SELL` / `DOUBLE_BOTTOM_BUY` | Classical double-pattern reversal | LIQUIDITY_SWEEP_REVERSAL |
| `HEAD_SHOULDERS_SELL` / `INV_HS_BUY` | Classical H&S | LIQUIDITY_SWEEP_REVERSAL |
| (others — see ICT Map §6 full table) | | |

---

## §7 PEMCG architecture terms (canonical — `docs/FORGE_PEMCG_ARCHITECTURE.md`)

| Term | Expansion | Definition |
|---|---|---|
| **PEMCG** | Premium-Exhaustion Move Confluence Gate | A 7-atom composite measuring how exhausted current price action is. Each atom contributes ±1 to a per-direction `warning_count`. | `FORGE_PEMCG_ARCHITECTURE.md §2.1` |
| **UMCG** | Unified Multi-Confluence Gate | The PEMCG consumer that blocks BB_EXHAUSTION_REVERSAL trades when reversal warning_count is too high. | `FORGE_PEMCG_ARCHITECTURE.md §3.1` |
| **CVCSM** | Continuation-Violation Cooldown State Machine | Per-direction state machine that blocks counter-direction entries for N bars after a continuation violation (e.g. SELL after a recent BUY MFE > X). | `FORGE_PEMCG_ARCHITECTURE.md §3.2` |
| **Layer 1** | n/a | The 7 PEMCG atoms themselves — `pemcg_buy_reversal_block`, `pemcg_sell_reversal_block`. | `FORGE_PEMCG_ARCHITECTURE.md §3` |
| **Layer 2** | n/a | CVCSM cooldown gates that consume Layer 1 counts. | as above |
| **Layer 3** | n/a | BB_EXHAUSTION_REVERSAL setups that fire when all 3 layers green-light. | as above |
| **ISS** | ICT Structure Score | Multi-atom composite measuring ICT structural alignment. Predecessor to per-category composites; partly absorbed into ComputeCategoryScore. | `FORGE_SETUP_ICT_MAP.md §B.8` |
| **ISS-C** | ISS Continuation | The continuation variant of ISS — bias-aligned trend follow setups. | `IctScoring.mqh` (scaffold) |

---

## §8 Recovery + risk terms

| Term | Expansion | Definition | Doc |
|---|---|---|---|
| **Ratchet stack** | n/a | 4-layer profit-banking architecture engaged AFTER entry: L1 TP1 native fire → L2 `move_be_on_tp1` SL ratchet → L3 TP-trail post-TP1 → L4 conviction-decay partial close. Canonical doc with G5001 case study. | `docs/FORGE_RATCHET_DESIGN.md` |
| **L1 / L2 / L3 / L4** | Ratchet layers | Numbered layers of the ratchet stack (see Ratchet stack above). L1=native TP1, L2=SL→BE, L3=TP tighten, L4=conviction decay. Distinct from PEMCG L1/L2/L3 (those are gate consumers, not exit layers — context disambiguates). | `docs/FORGE_RATCHET_DESIGN.md §2` |
| **move_be_on_tp1** | Move BE on TP1 | The L2 ratchet — when TP1 fires, remaining legs' SL moves to TP1 price (= breakeven on remaining lot weight). Master toggle in scalper_config. Canonical example: G5001 leg2 SL jumped 4559.62 → 4544.80 in 6s after TP1. | `ea/FORGE.mq5:1976`; `docs/FORGE_RATCHET_DESIGN.md §2` |
| **TP-trail / TP tighten** | n/a | The L3 ratchet — pulls TP closer to entry as retracement risk accumulates. Trail-pts formula: `MathMax(12, trigger_pts × 0.80-0.95, m5_atr × 0.90-1.20)` (chooses wider/more-conservative arm). Canonical example: G5001 TP2 4538.58 → 4543.73 (2.85 pts tighter). | `ea/FORGE.mq5:3224,3276`; `docs/FORGE_RATCHET_DESIGN.md §2` |
| **Conviction-decay** | n/a | The L4 ratchet — partial close at L1/L2/L3 MFE-ratio thresholds (0.75/0.50/0.25). Did NOT fire on G5001 (MFE held above 0.75 throughout). | `ea/FORGE.mq5:2998-3052`; `docs/FORGE_RATCHET_DESIGN.md §2` |
| **FMSR** | Fast-Market Sweep Rescue | Multi-phase recovery design for bad-trade states during fast-market moves. Adds same-direction limits on adverse swing extremes to capture retrace. **Distinct from ratchet** — FMSR handles MFE-stays-negative (rescue); ratchet handles MFE-positive (bank). | `docs/FORGE_FAST_MARKET_SWEEP_RESCUE.md` |
| **Track A** | n/a | Stopgap recovery — extends existing FORGE_BUY_LIMIT_RECOVERY / SELL_LIMIT_RECOVERY (post-TP1 ladder) to wider lot/expiry. Live as of v2.7.122. | FMSR §15.1 |
| **Track B** | n/a | New ArmPreTP1Recovery function — fires when primary trade is bad-state pre-TP1. Live as of v2.7.122 (P1). | FMSR §3 |
| **Track C** | n/a | DD-aware lot taper — reduce lot size as drawdown deepens. Deferred. | FMSR §15.2 |
| **P1** | n/a | "Phase 1" of FMSR — minimal pre-TP1 arm (one limit, adverse swing extreme, 40min expiry). The Mode A starting point. | FMSR §3 |
| **bad-trade state** | n/a | Primary trade where `MFE ≤ 0 AND adverse ≥ 1.5×ATR AND TP1 not hit`. The trigger condition for P1. | FMSR §3.2 |
| **TP1 / TP2 / TP3 / TP4 / TP5** | Take-Profit 1-5 | Sequential profit targets — TP1 first/closest, TP5 furthest. FORGE uses multi-leg ladders. | FORGE.mq5 (search `tp1_atr_mult`) |
| **MFE** | Maximum Favorable Excursion | The most-favorable price reached by the trade since entry (in pips or $). | FORGE.mq5 trade state tracking |
| **MAE** / **adverse** | Maximum Adverse Excursion | The most-adverse price reached by the trade since entry. Trigger input for P1. | as above |

---

## §9 Variables — runtime globals (read often during monitoring + design)

| Variable | Module | What |
|---|---|---|
| `g_regime.killzone` | FORGE.mq5 chokepoint | Current NY-anchored killzone label (single source of truth). |
| `g_regime.silver_bullet` | FORGE.mq5 chokepoint | Current SB sub-window label (or empty). |
| `g_regime.h1_trend`, `g_regime.h4_trend`, `g_regime.d1_trend` | FORGE.mq5 | HTF trend signs (signed double). |
| `g_eval_m5_velocity_5bar_signed` | FORGE.mq5 | 5-bar M5 close-to-close delta, normalized by M5 ATR. Used as displacement proxy. |
| `g_iss_mss` | IctStructure.mqh | Most recent MSS event signed (BUY=+, SELL=−). |
| `g_ict_last_*` | various `.mqh` | Per-tick atom-context exports. ALL new atoms write here. |
| `g_pemcg_buy_warning_count` / `g_pemcg_sell_warning_count` | FORGE.mq5 | PEMCG composite counts (0-7). |
| `g_sc.<field>` | FORGE.mq5 | The ScalperConfig struct — all hot-reloadable knobs live here. |
| `g_fvg_ring_count` | IctStructure.mqh | Count of active FVGs in the ring buffer. |
| `g_swing_highs[] / g_swing_lows[]` | IctStructure.mqh | Confirmed swing points used by OTE / PD-array atoms. |

---

## §10 Config knobs — `FORGE_*` env vars (active as of v2.7.124)

Lifecycle: `.env` → `make scalper-env-sync` → `config/scalper_config.json` → EA hot reload every 20 cycles → `g_sc.<field>`. Per `feedback_no_dead_env_vars`, every `FORGE_*` MUST have all 5 wires (sync mapping, defaults.json, .env.example, JsonHasKey, gate-legend if applicable).

| Prefix | Subsystem | Examples |
|---|---|---|
| `FORGE_KILLZONES_ENABLED` | KZ master toggle | flips KZ logic on/off globally |
| `FORGE_ICT_ATOM_*_ENABLED` | Per-atom toggles | KILLZONE_FAVORABLE, HTF_ALIGNED, PULLBACK_IN_OTE, PREMIUM_DISCOUNT_ALIGNED, FVG_ON_REVERSAL_LEG |
| `FORGE_COMPOSITE_*_SCORE_ENABLED` | Per-composite toggles | MSS_CONT_SCORE, OTE_RETRACE_SCORE, LIQ_SWEEP_REV_SCORE |
| `FORGE_RECOVERY_PRE_TP1_ENABLED` | Track B (P1) master | toggles ArmPreTP1Recovery |
| `FORGE_BUY_LIMIT_RECOVERY_*` / `FORGE_SELL_LIMIT_RECOVERY_*` | Post-TP1 ladder recovery (legacy) | lot factor, expiry bars |
| `FORGE_DUMP_MAX_RSI` | MOMENTUM_DUMP_SELL gate | per `feedback_xauusd_chop_retraces_up` |
| `FORGE_DEBUG_LOG_LEVEL` | Logging verbosity | 0-3 |

Full list: `grep ^FORGE_ .env.example` (operator-private `.env` is gitignored).

---

## §11 Ops / infrastructure terms

| Term | Definition |
|---|---|
| **Chokepoint** | The main `FORGE.mq5` file. Hosts orchestration; should NOT host new ICT logic bodies — those live in `.mqh` modules. |
| **Hot reload** | The `FORGE.mq5:2404` mechanism that re-reads `scalper_config.json` every 20 EA cycles. Allows flag flips without recompile. See skill §I.10. |
| **5-layer schema parity** | Mandatory pattern for any new SIGNALS column: CREATE TABLE + ALTER TABLE + JournalRecordSignal INSERT + scribe.py mirror + .env wiring. |
| **TESTER mode / LIVE mode** | The two operating modes of `/forge-monitor` (backtest journal vs live broker via scribe). |
| **SCRIBE** | `python/scribe.py` — the live broker DB mirror writer (writes `aurum_intelligence.db`). |
| **AURUM tester DB** | `python/data/aurum_tester.db` — bridge-synced mirror of MT5 tester journal. 60s lag — DO NOT use for live monitoring. |
| **SUM3API** | Reference architecture from SSRN 6143486 (MQL5 ⇄ ZeroMQ ⇄ Rust + QuestDB). Optional FUTURE external observability layer — NOT brain replacement. See `project_sum3api_vision.md`. |
| **Plug-and-play** | The modular `.mqh` design principle — atoms / composites / state machines are flag-toggleable, swappable, replaceable without touching the rest of FORGE. 8 principles codified in skill §I.8. |
| **Mode A / B / C** | Composite gate progression (log-only / warning-derate / hard-block). See §4. |

---

## §12 Update mandate

Every PR that introduces a new term — atom, composite, env var, struct field, runtime global, doc shorthand — MUST add it here in the SAME PR. Every PR that renames or removes a term MUST update or delete the entry. The skill `.claude/skills/forge-monitor/SKILL.md §I.12` references this file as the canonical glossary; any monitoring session that encounters an unfamiliar term should check here first.

**Anti-pattern**: explaining "MSS" or "OTE" inline in 17 different docs because the glossary doesn't exist or is stale. The glossary IS the explanation; everywhere else cites it.

**Cross-references**:
- `FORGE_SETUP_ICT_MAP.md §B.8` — atom catalog source of truth (this file's §3 mirrors it).
- `FORGE_PEMCG_ARCHITECTURE.md §2.1` — PEMCG atom source of truth (this file's §7 mirrors it).
- `FORGE_FAST_MARKET_SWEEP_RESCUE.md §3` — FMSR/P1 source of truth (this file's §8 mirrors it).
- `.claude/skills/forge-monitor/SKILL.md §I.12` — the update mandate enforcement point.

---

## §13 Changelog

- **2026-05-15** — initial glossary, covering ICT canon, 4 categories, current atom catalog (v2.7.124), composites (Phase B), killzones, PEMCG, FMSR, runtime globals, env-var prefixes, ops terms. Created in response to operator request "what is OTE in OTE_RETRACE" — exposing the need for a canonical lookup surface.
