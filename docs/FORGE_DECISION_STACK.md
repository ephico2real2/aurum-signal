# FORGE Decision Stack — ICT-canonical 5-tier reference

**Status**: canonical (created 2026-05-17). This is the **single source of truth** for how a trade decision flows through FORGE — top-down each tick, ICT-aligned end-to-end.

**Scope**: ICT-only. All pre-ICT architecture (PEMCG, UMCG, CVCSM, DTC, legacy chart patterns, MA/BB bespoke triggers) has been retired or is in active retirement per the canonical fold/retire ships (M7-M9 + v2.7.137a tech-debt). Future readers should consult this doc — not legacy refs — for the active design.

**Cross-references**:
- `docs/FORGE_SETUP_ICT_MAP.md §B.2` — the 4 ICT entry categories
- `docs/FORGE_SETUP_ICT_MAP.md §B.7` — killzone substrate
- `docs/FORGE_SETUP_ICT_MAP.md §B.8.2` — atom catalog with weights
- `docs/FORGE_ICT_SETUPS.md` — canonical setup catalog (setup_type ↔ atom set ↔ subtypes)
- `docs/FORGE_ICT_COMMENT_CODES.md` — broker comment grammar (Tier 4 emission shape)
- `.claude/skills/forge-monitor/SKILL.md §J.1` — two-layer composite pattern (atoms vs scores)
- `.claude/skills/forge-monitor/SKILL.md §I.8` — modular plug-and-play principles
- `ea/include/Forge/IctStructure.mqh` / `IctLiquidity.mqh` / `IctOrderBlock.mqh` / `IctScoring.mqh` / `IctComment.mqh` — Tier 1-2 implementation modules

---

## §1 The 5 tiers — one-line summary

| Tier | Name | Role | Lives in |
|---|---|---|---|
| **T1** | Indicators | Raw market state per tick — price, ATR/RSI/ADX/BB, killzone state, htf trend, swing pivots, FVG ring, OB ring | `FORGE.mq5` main tick block + `g_regime.*` + `g_eval_*` + `g_swing_*` + `g_fvg_ring` + `g_ob_ring` |
| **T2** | Atoms | Pure-function boolean predicates over T1 — ICT primitives (MSS confirmed, displacement present, FVG aligned, sweep detected, OB broken, killzone favorable, htf aligned, …) | `ea/include/Forge/Ict*.mqh` — exported via `g_ict_last_atom_*` globals |
| **T3** | Composites | Weighted scores aggregating T2 atoms per ICT category — 4 category composites + ISS general composite, each weighted to max 10 | `IctScoring.mqh::ComputeCategoryScore(category, direction)` — exported as `<cat>_score_<dir>` columns + `iss_score` |
| **T4** | Setup Trigger + Gates | Mode A/B/C decision over composites; on PASS, emit ICT-canonical `setup_type` (MSS_CONTINUATION / OTE_RETRACEMENT / LIQUIDITY_SWEEP_REVERSAL / BREAKER_RETEST) + `setup_subtype` (legacy-trigger identity for ablation) | Fire-site emission in `FORGE.mq5`; gate refusal via `JournalRecordSignal("SKIP", "<reason>", …)` |
| **T5** | Entry Geometry + Management | Structural SL/TP/lot from ICT context; TP ratchet, BE move, cascade arm, time-stop on stale groups | `PlaceOpenGroupLeg` + `PlaceMarketBatch` + `ManageOpenGroups` + `ManageStagedNativeLegs` |

---

## §2 ASCII reference diagram — data flow top-down each tick

```text
   ╔═══════════════════════════════════════════════════════════════════════╗
   ║                  FORGE ICT-CANONICAL DECISION STACK                   ║
   ║                       (one pass per OnTimer tick)                     ║
   ╚═══════════════════════════════════════════════════════════════════════╝

   ┌─────────────────────────────────────────────────────────────────────┐
   │ T1 — INDICATORS (raw market state)                                  │
   ├─────────────────────────────────────────────────────────────────────┤
   │   PRICE        m5_close, bid, ask, spread, m5_high/low, OHLC        │
   │   VOLATILITY   m5_atr, m15_atr, h1_atr                              │
   │   MOMENTUM     m5_rsi, m5_adx, m15_adx, macd_histogram              │
   │   STRUCTURE    g_swing_highs[], g_swing_lows[] (pivot ring)         │
   │                g_fvg_ring[]  (12-slot, mitigation-tracked)          │
   │                g_ob_ring[16] (newest-first, 6h lifespan)            │
   │   REGIME       g_regime.killzone   ← {ASIAN, LDN_OPEN, NY_AM,       │
   │                                       NY_PM, LDN_CLOSE, OFF}        │
   │                g_regime.silver_bullet ← {LDN_SB, AM_SB, PM_SB, ""}  │
   │                g_regime.htf_label  ← {BULL, BEAR, NEUTRAL}          │
   │                g_eval_h1_trend, g_eval_h4_trend (signed strength)   │
   │   ZONES        vwap_price, poc_price, fib_50, m5_bb_upper/mid/lower │
   └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │  ForgeEvalAtoms()  — once per tick,
                                    │  reads T1 globals, sets T2 globals
                                    ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │ T2 — ATOMS (pure-function ICT boolean primitives)                   │
   ├─────────────────────────────────────────────────────────────────────┤
   │   STRUCTURE    atom_mss_confirmed         (swing broken on close)   │
   │                atom_displacement_present  (body ≥ 1.5×ATR)          │
   │                atom_choch_confirmed       (structure shift post-    │
   │                                            sweep)                   │
   │   ZONES        atom_fvg_aligned           (FVG in direction)        │
   │                atom_fvg_unfilled          (FVG not mitigated)       │
   │                atom_fvg_on_reversal_leg   (LIQ_SWEEP context)       │
   │                atom_fvg_confluence        (OTE/BREAKER context)     │
   │                atom_pullback_in_ote       (fib 62-79% retrace)      │
   │                atom_premium_discount      (discount-BUY / prem-SELL)│
   │   LIQUIDITY    atom_sweep_detected        (equal H/L or session H/L │
   │                                            taken)                   │
   │                atom_sweep_wick_quality    (wick_atr_ratio tier;     │
   │                                            R23: binary→0/1/2 fix)   │
   │   ORDER BLOCK  atom_ob_broken             (OB body-closed past      │
   │                                            extreme)                 │
   │                atom_breaker_retest_buy/sell (price in retest zone)  │
   │                atom_ob_confluence_buy/sell  (OB in OTE zone)        │
   │   CONTEXT      atom_killzone_favorable    (g_regime.killzone in     │
   │                                            category's favored set)  │
   │                atom_htf_aligned           (direction matches H1/H4) │
   │                                                                     │
   │   IMPLEMENTATION: each atom = one bool function in Ict*.mqh.        │
   │   No hidden state. Inputs are T1 globals only. Outputs published    │
   │   to g_ict_last_atom_* globals + per-row SIGNALS columns (Mode A    │
   │   audit, all categories).                                           │
   └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │  ComputeCategoryScore(cat, dir)
                                    │  — weighted sum over atoms
                                    ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │ T3 — COMPOSITES (weighted scores; max 10 each)                      │
   ├─────────────────────────────────────────────────────────────────────┤
   │                                                                     │
   │   MSS_CONT_SCORE_<DIR>  = mss(3) + displacement(2) + fvg_aligned(2) │
   │                          + fvg_unfilled(1) + kz_fav(1)              │
   │                          + htf_aligned(1)                = 10       │
   │                                                                     │
   │   OTE_RETRACE_SCORE_<DIR> = pullback_ote(3) + premium_disc(2)       │
   │                          + fvg_confluence(2) + ob_confluence(1)     │
   │                          + kz_fav(1) + htf_aligned(1)    = 10       │
   │                                                                     │
   │   LIQ_SWEEP_REV_SCORE_<DIR> = sweep_detected(3) + wick_qual(2)      │
   │                          + choch_confirmed(2)                       │
   │                          + fvg_on_reversal(2) + kz_fav(1) = 10      │
   │                                                                     │
   │   BREAKER_RETEST_SCORE_<DIR> = ob_broken(3) + breaker_retest(3)     │
   │                          + fvg_confluence(2) + kz_fav(1)            │
   │                          + htf_aligned(1)                = 10       │
   │                                                                     │
   │   ISS (general, direction-agnostic) = mss(5) + fvg(3)               │
   │                          + choch_support(2)              = 10       │
   │   ISS hard gate:  iss_choch_against = 1  →  BLOCK regardless        │
   │                                                                     │
   │   IMPLEMENTATION: ComputeCategoryScore(int cat, int dir) in         │
   │   IctScoring.mqh; columns mss_cont_score_buy/sell,                  │
   │   ote_retrace_score_buy/sell, liq_sweep_rev_score_buy/sell,         │
   │   breaker_retest_score_buy/sell, iss_score in SIGNALS.              │
   └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │  Mode A/B/C threshold check
                                    │  + safety gates (session, KZ cap,
                                    │    cooldown, MagicBaseGate)
                                    ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │ T4 — SETUP TRIGGER + GATES                                          │
   ├─────────────────────────────────────────────────────────────────────┤
   │   GATE ORDER (each gate FAIL → JournalRecordSignal("SKIP", reason)):│
   │     1.  session_off          (outside London/NY session)            │
   │     2.  killzone_cap         (per-KZ trade cap reached)             │
   │     3.  cooldown             (post-SL or post-TP1 throttle)         │
   │     4.  magic_base_mismatch  (R21 — orphan-guard, blocks entries)   │
   │     5.  rr_too_low           (TP/SL ratio below floor 1.5)          │
   │     6.  iss_choch_against    (HARD GATE — ChoCH opposes direction)  │
   │     7.  iss_below_threshold  (iss_score < 5 — v2.7.116+ activation) │
   │     8.  <cat>_score_below_threshold  (Mode C per-category gate —    │
   │                                       v2.7.117+ post-validation)    │
   │                                                                     │
   │   On PASS → SETUP TRIGGER FIRES:                                    │
   │     setup_type    = "MSS_CONTINUATION_BUY"  (or _SELL)              │
   │                   | "OTE_RETRACEMENT_BUY"   (or _SELL)              │
   │                   | "LIQUIDITY_SWEEP_REVERSAL_BUY" (or _SELL)       │
   │                   | "BREAKER_RETEST_BUY"    (or _SELL)              │
   │     setup_subtype = "<legacy_trigger>"  (preserved for ablation)    │
   │                                                                     │
   │   MODES (per FORGE_PEMCG_ICT_INTEGRATION.md 3-mode plan, applied    │
   │   per-composite via enable flag):                                   │
   │     Mode A  →  compute + log only (score recorded, no gate fires)   │
   │     Mode B  →  warning de-rate (score < 5 → lot × 0.7, fires)       │
   │     Mode C  →  HARD BLOCK (score < threshold → SKIP)                │
   │                                                                     │
   │   IMPLEMENTATION: fire-site emission in FORGE.mq5 (8 sites          │
   │   post-M7: BB_BREAKOUT×2, GAP_AND_GO, MOMENTUM_DUMP_COMPOSITE,      │
   │   BB_SQUEEZE, GRINDING_SELL, NY_SESSION_BEARISH_BREAKOUT_SELL,      │
   │   INSIDE_BAR provisional). Plus M8 OTE sites + M9 LIQ_SWEEP sites.  │
   │   Subtype set via g_setup_subtype_for_next_signal global per skill  │
   │   §I.11.1 v2.7.122 F-α anti-pattern (no signature thread to 119     │
   │   call sites).                                                      │
   └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │  PlaceOpenGroupLeg / PlaceMarketBatch
                                    │  — build canonical comment + place
                                    ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │ T5 — ENTRY GEOMETRY + POST-PLACEMENT MANAGEMENT                     │
   ├─────────────────────────────────────────────────────────────────────┤
   │   GEOMETRY (structural, ICT-context aware):                         │
   │     SL   = entry ± (sl_atr_mult × m5_atr),                          │
   │            floor at (sl_floor_mult × m5_atr)                        │
   │            placed beyond invalidation level (swing extreme,         │
   │            opposite FVG boundary, OB extreme)                       │
   │     TP1  = entry ± (tp1_atr_mult × m5_atr)  — scalp ~0.4-0.7×ATR    │
   │     TP2  = entry ± (tp2_atr_mult × m5_atr)  — ~1.0-2.0×ATR          │
   │     TP3/4/5  = ATR multiples or next structural liquidity level     │
   │     LOT  = base × <factor stack: scalper_eff, stack, dump_pyramid,  │
   │            dump_dist, dump_kz, mdct, tcb, tcs, bounce, pullback,    │
   │            intraday_rev, fractional_sell, bull_day_dip, fast_trend, │
   │            near_floor, inside_band, adx_lot, ma_crossover†,         │
   │            vwap_rev, fib_confluence, inside_bar, bb_squeeze, orb†,  │
   │            gap_and_go, double_pattern, hs, flag_pennant,            │
   │            trendline_bounce, sr_flip>                               │
   │            (†retired pending v2.7.137a / M9 reclassify)             │
   │     LEGS = batch_size (PlaceMarketBatch, R27-fixed comment shape)   │
   │            or single g_trade.Buy/Sell; staged-add via               │
   │            ManageStagedNativeLegs                                   │
   │                                                                     │
   │   POST-PLACEMENT (ManageOpenGroups, tick-driven):                   │
   │     TP1 hit  → close tp1_close_pct% + BE move + cascade arm         │
   │                (SELL_STOP_CONT / BUY_LIMIT_RECOV)                   │
   │     TP2 hit  → SL ratchet → TP1 (invariant: BUY raises SL only)     │
   │     TP3 hit  → TP → TP4; SL → TP2                                   │
   │     TP4 hit  → TP → TP5; SL → TP3                                   │
   │     Time-stop → close stale groups after dump_max_hold_seconds      │
   │     Conviction-decay → partial close at score-drop thresholds       │
   │                                                                     │
   │   BROKER COMMENT (R27 canonical 6/7-segment shape):                 │
   │     <ZONE>_<ORDER_TYPE>|<CAT>_<DIR>|G<ID>|<TP_OR_LEG>|              │
   │       <KZ_DETAIL>|<CONV>[|<SK_DETAIL>]                              │
   │     e.g. KZ_MKT|MSS_CONT_B|G5001|TP1|LDN_OPEN_KZ|H                  │
   │     e.g. SK_MKT|OTE_RETR_S|G5002|TP2|NY_PM_KZ|H|PM_SK               │
   │                                                                     │
   │   IMPLEMENTATION: PlaceOpenGroupLeg (FORGE.mq5:17648),              │
   │   PlaceMarketBatch (17414) with Forge_OverrideTpOrLeg (R27),        │
   │   ManageOpenGroups (~13000-15000 area),                             │
   │   ManageStagedNativeLegs (3127), JournalRecordSignal for SIGNALS    │
   │   row write at every SKIP/TAKEN.                                    │
   └─────────────────────────────────────────────────────────────────────┘
```

---

## §3 The 4 ICT entry categories (T4 setup_type domain)

Every TAKEN signal post-M7-M9 has `setup_type` from this set. Categories are mutually exclusive — one trade = one category. The `setup_subtype` column preserves the legacy-trigger identity for ablation studies.

| # | setup_type | When it fires | Driving atoms (T2) | Composite (T3) |
|---|---|---|---|---|
| 1 | `MSS_CONTINUATION_BUY` / `_SELL` | Market Structure Shift confirmed by ≥1.5×ATR displacement leg; entry on retrace into the FVG/OB the impulse created | `atom_mss_confirmed`(3) + `atom_displacement_present`(2) + `atom_fvg_aligned`(2) + `atom_fvg_unfilled`(1) + `atom_killzone_favorable`(1) + `atom_htf_aligned`(1) | `MSS_CONT_SCORE_<DIR>` |
| 2 | `OTE_RETRACEMENT_BUY` / `_SELL` | Pullback to 62-79% fib retracement in discount (BUY) or premium (SELL) zone with FVG/OB confluence | `atom_pullback_in_ote`(3) + `atom_premium_discount_aligned`(2) + `atom_fvg_confluence`(2) + `atom_ob_confluence`(1) + `atom_killzone_favorable`(1) + `atom_htf_aligned`(1) | `OTE_RETRACE_SCORE_<DIR>` |
| 3 | `LIQUIDITY_SWEEP_REVERSAL_BUY` / `_SELL` | Sweep of equal highs/lows or session H/L followed by Change of Character; entry on first FVG retrace on reversal leg | `atom_sweep_detected`(3) + `atom_sweep_wick_quality`(2) + `atom_choch_confirmed`(2) + `atom_fvg_on_reversal_leg`(2) + `atom_killzone_favorable`(1) | `LIQ_SWEEP_REV_SCORE_<DIR>` |
| 4 | `BREAKER_RETEST_BUY` / `_SELL` | OB body-closed past extreme (broken) now retests as opposite-direction S/R; entry on retest tap with FVG confluence (the "Unicorn" pattern) | `atom_ob_broken`(3) + `atom_breaker_retest`(3) + `atom_fvg_confluence`(2) + `atom_killzone_favorable`(1) + `atom_htf_aligned`(1) | `BREAKER_RETEST_SCORE_<DIR>` |

Full atom semantics + spec citations in `docs/FORGE_SETUP_ICT_MAP.md §B.8.2`.

---

## §4 The two-layer composite pattern (skill §J.1) — why both atoms AND scores

```text
   ┌──────────────────────┐         ┌──────────────────────┐
   │   ATOM LAYER (T2)    │         │  SCORE LAYER (T3)    │
   │  bool — yes/no       │         │  int 0-10 — weighted │
   │  AUDIT + ABLATION    │         │  GATE DECISION       │
   ├──────────────────────┤         ├──────────────────────┤
   │  "did MSS confirm?"  │  ────►  │  "should THIS        │
   │  "is FVG aligned?"   │  ────►  │   category fire IN   │
   │  "is KZ favorable?"  │  ────►  │   THIS direction?"   │
   │  "is HTF aligned?"   │  ────►  │                      │
   └──────────────────────┘         └──────────────────────┘
              │                                │
              │                                │
              ▼                                ▼
   per-atom SIGNALS columns         per-composite SIGNALS
   for forensic ablation            columns for histogram
   (which atom held? which          calibration of Mode A
   atom failed?)                    → B → C threshold tuning
```

**Why both layers**:
- **Atoms alone** lose magnitude info — threshold cliffs (3/7 = block, 2/7 = allow) hide near-miss data.
- **Scores alone** lose categorical clarity — for primitives that ARE genuinely yes/no (MSS confirmed or not), boolean is sharper for post-mortem.
- **Two layers together** = atoms for forensics (which one held?) + score for decision (threshold-tunable, magnitude-aware).

This is the canonical pattern for every new ICT composite. Per skill §J.7 the pre-ICT pure-boolean composites have been retired (§9 changelog).

---

## §5 Mode A → B → C gate promotion (per-composite calibration)

```text
   ┌─────────────┐    validate     ┌─────────────┐    validate     ┌─────────────┐
   │   MODE A    │   100+ trades   │   MODE B    │   strong edge   │   MODE C    │
   │  log only   │   ───────────►  │  warning    │   ───────────►  │  hard gate  │
   │ (default)   │   histogram     │  de-rate    │   bimodal       │  SKIP block │
   ├─────────────┤   shows         ├─────────────┤   distribution  ├─────────────┤
   │ score       │   correlation   │ score < 5   │   confirmed     │ score < N   │
   │ recorded;   │                 │  → lot ×    │                 │  → SKIP     │
   │ no gating   │                 │    0.7      │                 │  gate_reason│
   │             │                 │  (trade     │                 │  emitted    │
   │             │                 │   fires)    │                 │             │
   └─────────────┘                 └─────────────┘                 └─────────────┘

   Every new composite ships in Mode A first. Promotion requires empirical
   evidence per `feedback_supermajority_composite_threshold`:
     - histogram score distribution shows winners cluster ≥ N, losers < N
     - the threshold N must catch ≥X% losers AND not block ≥Y% winners
     - operator decision flips enable flag (per-composite, hot-reloadable
       per skill §I.10)
```

---

## §6 The schema-parity 5-layer ship contract

Every new column added to T2 (atom output) or T3 (composite score) must land in **all five layers in the same commit**. This is enforced by `tests/api/test_m7_fold.py` for the M7 `setup_subtype` column and should be added per ship.

```text
   NEW COLUMN  ────►  Layer 1: ea/FORGE.mq5  CREATE TABLE IF NOT EXISTS SIGNALS
                     (fresh-DB schema)
                ────►  Layer 2: ea/FORGE.mq5  ALTER TABLE SIGNALS ADD COLUMN
                     (idempotent migration for existing DBs)
                ────►  Layer 3: ea/FORGE.mq5  JournalRecordSignal()
                     - SQL INSERT column list extended
                     - SQL VALUES bind extended (read from g_ict_last_* global,
                       NOT positional-param thread per skill §I.11.1
                       v2.7.122 F-α anti-pattern)
                ────►  Layer 4: python/scribe.py  sync_forge_journal()
                     - CREATE TABLE IF NOT EXISTS forge_signals
                     - ALTER TABLE forge_signals ADD COLUMN (idempotent)
                     - SELECT from SIGNALS includes new column
                     - INSERT INTO forge_signals column list extended
                     - Placeholder count bumped: ["?"] * (N + …) ← match exactly
                ────►  Layer 5: schemas/aurum_tester.sql (if file exists)
                     mirror Layer 4 changes for cross-tooling consistency

   FAILURE MODE if any layer skipped:
     - Skip Layer 1+2     → column never lands in DB; INSERT may fail or column
                            stays NULL in all rows
     - Skip Layer 3 bind  → column lands as NULL/0 every row
     - Skip Layer 4 mirror → scribe sync errors with "no such column",
                             dashboard panel goes dark
     - Skip placeholder count → "N values for M columns" — INSERT silently
                                fails, bridge log spams sync-recovery
```

Reference incidents (preserved as cautionary tales in skill §"Schema-parity ship"): v2.7.45/47 (5 cols, placeholder count miss, 12-hour dashboard outage); v2.7.112 (5 ISS cols, migration miss); v2.7.118 (9 ICT cols, downstream break) — all fixed retroactively by the v2.7.119 5-layer sweep. Never let it recur.

---

## §7 The two-phase retire pattern (bespoke detector → canonical atom successor)

When a bespoke (pre-ICT) detector has an atom-composed canonical successor, retire follows this pattern. Operator-confirmed 2026-05-17 (MOMENTUM_DUMP v1 → composite; BB_PULLBACK_SCALP → atom_pullback_in_ote).

```text
   PHASE 1 — FOLD (Option A — no logic change)
   ┌────────────────────────────────────────────────────────────┐
   │  bespoke fire site:                                        │
   │    setup_type = "BESPOKE_NAME"                             │
   │  becomes:                                                  │
   │    g_setup_subtype_for_next_signal = "bespoke_name"        │
   │    setup_type = "<ICT_CANONICAL_CATEGORY>_" + direction    │
   │  Trigger logic UNCHANGED — same fire conditions.           │
   │  Subtype preserves identity for ablation.                  │
   └────────────────────────────────────────────────────────────┘
                                │
                                │  parallel validation period
                                │  (Mode A logs both detectors)
                                ▼
   PHASE 2 — VALIDATE (compare canonical vs bespoke fire rates)
   ┌────────────────────────────────────────────────────────────┐
   │  Canonical atom-composed detector fires alongside bespoke. │
   │  Histogram comparison:                                     │
   │    - fire rate (canonical fires ≥ bespoke?)                │
   │    - win rate (canonical wins ≥ bespoke?)                  │
   │    - drawdown (canonical max-DD ≤ bespoke?)                │
   │  If canonical ≥ bespoke on all 3 axes → proceed to Phase 3.│
   │  Else: investigate why; tune canonical atoms; defer retire.│
   └────────────────────────────────────────────────────────────┘
                                │
                                │  operator decision
                                ▼
   PHASE 3 — RETIRE (delete bespoke detector)
   ┌────────────────────────────────────────────────────────────┐
   │  Delete:                                                   │
   │    - bespoke fire sites in FORGE.mq5                       │
   │    - bespoke env knobs the canonical doesn't reuse         │
   │    - bespoke g_sc.<field> not read by canonical            │
   │    - bespoke cooldown timers                               │
   │  Canonical setup_type continues firing — no observable     │
   │  trade-behavior change (assuming Phase 2 validation passed).│
   │  NO migration to setup_subtype (canonical preserves         │
   │  semantics independently).                                 │
   └────────────────────────────────────────────────────────────┘
```

**Open R-list at time of this doc**:
- `MA_CROSSOVER` — Phase 3 only (no canonical successor exists; lagging indicator rejected by ICT canon). Ships as v2.7.137a tech-debt.
- `MOMENTUM_DUMP` v1 → `MOMENTUM_DUMP_COMPOSITE` — Phase 3 (Phase 2 validation done; operator decision 2026-05-17 to retire). Ships as v2.7.137a.
- `BB_PULLBACK_SCALP` → `atom_pullback_in_ote` (Cat 2 OTE) — Phase 1 lands with M8; Phase 2 post-M8 backtest; Phase 3 v2.7.141+ per R33.

---

## §8 Where each module owns its tier

| Module | Tier owned | What it provides |
|---|---|---|
| `FORGE.mq5` (main tick loop + safety gates) | T1 raw state, T4 gate orchestration, T5 placement | g_eval_*, g_regime.*, gate decisions, fire-site emission, geometry placement |
| `ea/include/Forge/IctStructure.mqh` | T1 swing pivots + FVG ring, T2 MSS / FVG atoms | DetectBullish/BearishMSS, FVG ring buffer, Forge_GetActiveFVGAlignedWith() |
| `ea/include/Forge/IctLiquidity.mqh` | T2 sweep / ChoCH / killzone atoms | DetectBuy/SellSideLiquiditySweep, DetectBullish/BearishChOCh, IsKillzoneFor() |
| `ea/include/Forge/IctOrderBlock.mqh` | T1 OB ring (newest-16 per R24), T2 OB / Breaker atoms | OB detection + ring management, Forge_UpdateOBBrokenState, atom_breaker_retest_* |
| `ea/include/Forge/IctScoring.mqh` | T2 shared atoms (kz_fav, htf_aligned), T3 ComputeCategoryScore | Atom_KillzoneFavorable (R22-corrected), Atom_HTFAligned, ComputeCategoryScore(cat, dir) |
| `ea/include/Forge/IctComment.mqh` | T5 broker comment grammar | Forge_BuildScalpComment, Forge_OverrideTpOrLeg (R27), Forge_IctComment_SelfTest |
| `python/scribe.py` | T2+T3 column mirror to scribe DB | sync_forge_journal for forge_signals / forge_journal_trades |

---

## §9 Plug-and-play principles (per skill §I.8)

The 5-tier separation enforces these design properties — every new atom/composite/gate follows them:

1. **Atoms = pure functions** — clean inputs (T1 globals), clean outputs (bool to `g_ict_last_atom_*`). No hidden side effects. Toggleable via per-atom enable flag.
2. **State machines explicit** — FVG state (virgin/touched/mitigated/CE/invalidated), OB state (virgin/touched/mitigated/broken), trade state (IDLE→MAPPED→SWEPT→MSS_OK→ARMED→ENTERED→MANAGING→PARTIAL→EXITED→COOLDOWN).
3. **Output structures clean** — every cross-module struct (`IctSwingPoint`, `FvgZone`, `OrderBlockZone`, `SweepEvent`) has descriptive field names.
4. **Unified setup model parameterized, not branched** — ONE `EvaluateICTSetup(params)` over 4 category-direction param sets, NOT 8 branched fire functions.
5. **Canonical SKIP codes** — `SKIP_NO_SWEEP`, `SKIP_NO_MSS`, `SKIP_WEAK_DISPLACEMENT`, `SKIP_NO_VALID_FVG`, `SKIP_BUY_PREMIUM`, `SKIP_SELL_DISCOUNT`, `SKIP_OUTSIDE_KZ`, `SKIP_SPREAD`, `SKIP_NEWS`, `SKIP_CHOP`, `SKIP_FVG_FILLED`, `SKIP_OB_MITIGATED`, `SKIP_HTF_CONFLICT`.
6. **Anti-lookahead (closed-bar only)** — engines see only completed M5/M15/H1/H4/D1 bars. No intra-bar peek.
7. **Per-component score logging** — every atom = one SIGNALS column (Strategy A). Enables ablation studies + Mode A→B→C threshold tuning.
8. **Validation harness scaffolding** — `tests/api/test_m7_fold.py` pattern (xfail until ship, auto-pass on correct ship) + bar-replay tester + walk-forward window queries + regime-stratified P&L.

---

## §10 Cross-tier read order — when reading code, follow this sequence

If you're new to the codebase or returning after time away, read these in order to internalize the stack:

1. **`docs/FORGE_DECISION_STACK.md` (THIS DOC)** — the 5-tier map you're reading.
2. **`docs/FORGE_SETUP_ICT_MAP.md §B.2 + §B.8.2`** — the 4 categories + atom catalog with weights.
3. **`docs/FORGE_ICT_SETUPS.md`** — canonical setup catalog (setup_type ↔ subtype mapping).
4. **`ea/include/Forge/IctStructure.mqh`** — T1+T2 implementations for MSS / FVG atoms.
5. **`ea/include/Forge/IctScoring.mqh`** — T3 ComputeCategoryScore + shared atoms.
6. **`ea/FORGE.mq5`** ForgeEvalAtoms function — T2 atom evaluation per tick.
7. **`ea/FORGE.mq5`** setup fire sites — T4 trigger emission (post-M7 cleanup).
8. **`ea/FORGE.mq5::PlaceOpenGroupLeg` + `PlaceMarketBatch`** — T5 geometry + placement.
9. **`ea/FORGE.mq5::ManageOpenGroups`** — T5 post-placement ratchet + cascade arm.
10. **`docs/FORGE_ICT_COMMENT_CODES.md`** — T5 broker comment grammar (parsed by scribe.py).

---

## §11 Changelog

- **2026-05-17** — Initial canonical doc. ICT-only 5-tier reference, replaces and supersedes any pre-ICT decision-stack documentation. Adds ASCII reference diagram, two-layer composite pattern, Mode A→B→C promotion, schema-parity 5-layer contract, two-phase retire pattern. Cross-referenced from `docs/FORGE_SETUP_ICT_MAP.md` + `docs/FORGE_ICT_SETUPS.md` + skill §J.1 + skill §I.8.
