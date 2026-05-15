# FORGE Fast-Market Sweep Rescue (FMSR) — Design

> **Status**: Design doc (operator-approved 2026-05-15). Code not yet shipped.
> **Target ship**: v2.7.123 (post-v2.7.122 killzone alignment).
> **ICT category**: `LIQUIDITY_SWEEP_REVERSAL` (per `FORGE_SETUP_ICT_MAP.md §B.2`).
> **Module home**: `ea/include/Forge/IctLiquidity.mqh` (extends Phase 2).
> **Schema-parity**: 5-layer ship mandatory per `.claude/skills/forge-monitor/SKILL.md §I.5`.

---

## §1 Problem statement — the gap

When price moves fast against an active primary trade, FORGE has **no mechanism** that arms opposite-direction pending orders to capture the eventual retracement and net the bad-trade loss. Every existing recovery/cascade mechanism requires the primary trade to first hit TP1:

| Existing mechanism | Precondition | What it does |
|---|---|---|
| `breakout_sell_limit` L1/L2 | `BB_BREAKOUT_SELL` primary fills | Arms SELL LIMITs above crash entry |
| `sell_stop_cont` (default OFF) | Primary TP1 hits | SELL STOPs below for continuation |
| `buy_limit_recovery` (operator: ON) | **Primary TP1 hits** | BUY LIMITs at crash low |
| `sell_limit_recovery` (operator: ON) | **Primary TP1 hits** | SELL LIMITs at peak |
| `buy_stop_cont` (default OFF) | Primary TP1 hits | BUY STOPs above for continuation |

**The uncovered case** (operator's "bad trade state"):

```
T0:   BUY primary fills at 2050
T1:   Price dumps fast — −3 ATR in 5 bars
T2:   BUY is −$X underwater, never hit TP1
T3:   Price continues to −5 ATR sweep low
T4:   Reversal begins, price retraces toward 2045
T5:   Primary stop-out OR closes near low for max loss

Nothing in current code arms SELL_STOPs at T1-T3 (capture continued dump)
nor BUY_LIMITs at OTE retrace zones at T3-T4 (catch reversal at deeper level)
that would offset the primary BUY's loss.
```

FMSR closes this gap with a **standalone, ICT-aligned, primary-trade-independent** opposite-direction-pending-order arm.

---

## §2 ICT mapping

FMSR IS a `LIQUIDITY_SWEEP_REVERSAL` setup, fired by sweep detection rather than by a primary-trade TP1 event. Maps directly to `FORGE_SETUP_ICT_MAP.md §B.8.2 Category 3` atoms:

| FMSR step | ICT atom (existing) | Source |
|---|---|---|
| Detect fast move | `atom_displacement_present` (`g_eval_m5_velocity_5bar_signed`) | `FORGE.mq5:273` |
| Identify sweep | `atom_sweep_detected` (DetectBuy/SellSideLiquiditySweep) | `IctLiquidity.mqh` |
| Wait for wick rejection | `atom_sweep_wick_quality` (wick_atr_ratio ≥ 1.0) | `IctLiquidity.mqh` |
| Compute OTE retrace zone | new helper `ComputeOTEBand(sweep_low, sweep_high, direction)` | new in `IctLiquidity.mqh` |
| Arm reversal pendings | new `Forge_ArmFastMarketSweepRescue(...)` | new in `IctLiquidity.mqh` |
| Killzone gate | `atom_killzone_favorable` (LONDON_OPEN_KZ, NY_PM_KZ) | `g_regime.killzone` |

The FMSR composite score uses the same Category 3 weights from §B.8.2 (sweep=3 + wick_quality=2 + choch=2 + fvg=2 + killzone=1 = 10). Default gate Mode B (score < 5 → arm at reduced lot factor; score ≥ 5 → arm at full).

---

## §3 Detection — when FMSR arms

Three conditions ALL true at tick close:

1. **Fast move present**: `|g_eval_m5_velocity_5bar_signed| ≥ fmsr_velocity_threshold` (default 2.0×ATR over 5 M5 bars)
2. **Sweep detected**: `atom_sweep_detected = true` for the direction OPPOSITE to the fast move (a fast DUMP = sell-side sweep of the prior low; a fast RIP = buy-side sweep of the prior high)
3. **Not in cooldown**: `g_fmsr_last_arm_time + fmsr_cooldown_seconds ≤ TimeCurrent()` (default 600s = 10 min) — prevents re-arming during sustained one-way moves

When all three hold, arm the rescue. Direction logic:

| Fast move direction | Sweep direction | Rescue pending direction | Rationale |
|---|---|---|---|
| DOWN (signed velocity < −threshold) | Sell-side sweep (prior LOW taken) | **BUY_LIMIT** at OTE retrace above | Catch the bounce |
| UP (signed velocity > +threshold) | Buy-side sweep (prior HIGH taken) | **SELL_LIMIT** at OTE retrace below | Catch the reversal |

---

## §4 Pricing — OTE retrace anchors

The rescue limits price at fib retracement of the sweep leg. Sweep leg = move from sweep anchor (prior swing extreme that got taken) to the sweep extreme (the wick low/high of the sweep candle).

```
For DOWN sweep (sell-side liquidity grab):
   sweep_anchor = prior swing high (recent pivot before the dump)
   sweep_extreme = sweep candle low (the wick low)
   sweep_range = sweep_anchor - sweep_extreme   (always positive)

   BUY_LIMIT L1 price = sweep_extreme + sweep_range × 0.62   (62% retrace = OTE upper)
   BUY_LIMIT L2 price = sweep_extreme + sweep_range × 0.79   (79% retrace = OTE lower)

For UP sweep (buy-side liquidity grab):
   sweep_anchor = prior swing low
   sweep_extreme = sweep candle high
   sweep_range = sweep_extreme - sweep_anchor

   SELL_LIMIT L1 price = sweep_extreme - sweep_range × 0.62
   SELL_LIMIT L2 price = sweep_extreme - sweep_range × 0.79
```

L1 and L2 fill independently — one or both may trigger. L2 deeper = smaller probability but better R:R when it fills.

Config knobs:
- `fmsr_l1_fib_retrace = 0.62` (default — OTE upper bound)
- `fmsr_l2_fib_retrace = 0.79` (default — OTE lower bound)
- `fmsr_l3_enabled = 0` (optional 3rd leg at 0.88 for liquidity-grab targeting; default off)

---

## §5 SL / TP / expiry geometry

Each rescue leg has independent geometry:

| Element | BUY_LIMIT (DOWN sweep rescue) | SELL_LIMIT (UP sweep rescue) |
|---|---|---|
| **Entry** | At fib retrace (62% or 79%) | At fib retrace (62% or 79%) |
| **SL** | sweep_extreme − fmsr_sl_atr_mult × ATR | sweep_extreme + fmsr_sl_atr_mult × ATR |
| | (default `fmsr_sl_atr_mult = 1.0` — 1 ATR beyond the wick) | |
| **TP1** | sweep_anchor − sweep_range × 0.20 | sweep_anchor + sweep_range × 0.20 |
| | (~80% retrace back toward original level — "fair value") | |
| **TP2** | sweep_anchor (full retrace to anchor) | sweep_anchor (full retrace to anchor) |
| **Expiry** | `fmsr_expiry_bars × 5min` (default 6 bars = 30 min) | same |

Per memory `feedback_rsi_exhaustion_gate`: SL must be a real structural SL beyond the sweep wick. Per `feedback_chop_scalp_one_tp_fast_sl`: fast BE-snap on TP1 + ATR-trail post-TP2.

---

## §6 Risk caps (mandatory — this is the martingale boundary)

FMSR is martingale-shaped without these caps. All four are non-negotiable:

| Cap | Default | Behavior on breach |
|---|---|---|
| **Max legs per sweep** | `fmsr_max_legs = 2` (L1 + L2 only) | L3+ silently skipped |
| **Daily DD kill** | `fmsr_daily_dd_pct = 2.0%` of starting equity | All FMSR pendings cancelled; FMSR disabled until next session reset |
| **Loss-streak kill** | `fmsr_max_consecutive_losses = 3` | FMSR disabled until next manual reset OR daily reset |
| **Cooldown after loss** | `fmsr_post_loss_cooldown_seconds = 1800` (30 min) | No new FMSR arms during cooldown |
| **Concurrent open** | `fmsr_max_concurrent_legs = 4` (across all FMSR groups) | New arms blocked when at cap |

Per `feedback_chop_grid_no_per_leg_sl` memory: even though FMSR legs HAVE per-leg SL, the basket caps above replace the grid-style "no per-leg SL" pattern with structural protection.

---

## §7 Bad-trade netting accounting

When a rescue leg fills and an opposite-direction primary is in loss state:

1. **Telemetry** — log `fmsr_offset_primary_ticket` linking the rescue leg to the underwater primary (for post-mortem)
2. **TP recommendation** — if rescue is netting an open primary loss, suggest closing primary at rescue-fill price + 0.5×ATR (operator-controlled via `fmsr_auto_close_primary_on_offset = 0` default OFF — never auto-modify primary trades)
3. **Lot sizing** — rescue lot = MIN(primary_underwater_lot, fmsr_max_lot_per_leg) — rescue lot capped at primary's lot so net exposure can't grow

Lot config:
- `fmsr_l1_lot_factor = 0.5` (default — half of primary's lot per leg)
- `fmsr_l2_lot_factor = 0.5`
- `fmsr_max_lot_per_leg = 0.25` (absolute cap regardless of primary lot)

---

## §8 Module home + function signatures

Extends `ea/include/Forge/IctLiquidity.mqh`:

```mql5
// ─── Fast-Market Sweep Rescue (v2.7.123) ────────────────────────────────────

struct FMSRArmRequest {
   int direction;              // 1=BUY_LIMIT (down-sweep rescue), -1=SELL_LIMIT (up-sweep)
   double sweep_anchor;
   double sweep_extreme;
   double l1_price;
   double l2_price;
   double sl_price;
   double tp1_price;
   double tp2_price;
   datetime expiry;
   double composite_score;     // §B.8.2 Category 3 score 0-10
};

// Returns false if any §3 condition fails or §6 cap breached.
bool Forge_EvalFastMarketSweepRescue(FMSRArmRequest &out);

// Computes OTE retrace band given sweep anchor + extreme.
void Forge_ComputeOTEBand(double anchor, double extreme, int direction,
                          double l1_fib, double l2_fib,
                          double &l1_price, double &l2_price);

// Per-tick housekeeping: expire stale pendings, update DD counters,
// enforce cooldowns. Called from CheckScalperEntry top.
void Forge_FMSRHousekeeping();

// Telemetry accessor for chokepoint logging.
string Forge_FMSRStatus();   // human-readable JSON: "{armed_legs: 2, daily_dd_pct: 1.2, ...}"
```

The chokepoint `FORGE.mq5` calls `Forge_EvalFastMarketSweepRescue()` once per M5 close, after the existing primary-setup evaluation. If it returns true, the chokepoint places L1 + L2 pending orders via the standard `OrderSend()` path — FMSR does NOT touch order-send directly (separation of concerns: module decides, chokepoint executes).

---

## §9 Config knobs (full list)

All under `g_sc.fmsr_*` in `ScalperConfig`. Defaults in `LoadScalperDefaults` per §3-§7 above.

| Knob | Default | Range | Purpose |
|---|---|---|---|
| `fmsr_enabled` | `false` | bool | Master toggle (default OFF — opt-in via `.env`) |
| `fmsr_velocity_threshold` | 2.0 | 1.0-5.0 | ATR multiple over 5 M5 bars |
| `fmsr_l1_fib_retrace` | 0.62 | 0.5-0.8 | OTE upper |
| `fmsr_l2_fib_retrace` | 0.79 | 0.7-0.9 | OTE lower |
| `fmsr_l3_enabled` | 0 | bool | Optional 3rd leg |
| `fmsr_l3_fib_retrace` | 0.88 | 0.85-0.95 | L3 deep retrace |
| `fmsr_sl_atr_mult` | 1.0 | 0.5-3.0 | SL beyond sweep wick |
| `fmsr_tp1_retrace_pct` | 0.20 | 0.1-0.4 | TP1 partial retrace |
| `fmsr_expiry_bars` | 6 | 2-20 | M5 bars before cancel |
| `fmsr_max_legs` | 2 | 1-3 | Per-sweep cap |
| `fmsr_max_concurrent_legs` | 4 | 1-10 | Across all sweeps |
| `fmsr_daily_dd_pct` | 2.0 | 0.5-5.0 | Daily kill switch |
| `fmsr_max_consecutive_losses` | 3 | 2-10 | Streak kill |
| `fmsr_post_loss_cooldown_seconds` | 1800 | 300-7200 | Cooldown |
| `fmsr_cooldown_seconds` | 600 | 60-3600 | Re-arm cooldown |
| `fmsr_l1_lot_factor` | 0.5 | 0.1-2.0 | Per-leg lot mult |
| `fmsr_l2_lot_factor` | 0.5 | 0.1-2.0 | Per-leg lot mult |
| `fmsr_max_lot_per_leg` | 0.25 | 0.01-1.0 | Absolute lot cap |
| `fmsr_killzone_required` | 1 | bool | If 1: only arm in LONDON_OPEN_KZ / NY_PM_KZ (per §B.2 high-probability sweep windows) |
| `fmsr_auto_close_primary_on_offset` | 0 | bool | If 1: close primary at rescue-fill (default OFF — never auto-modify primary) |
| `fmsr_min_composite_score` | 5 | 0-10 | Mode B warning gate; ≥5 = full lot, <5 = ×0.5 lot |

`.env` mapping (per `feedback_no_dead_env_vars`): one `FORGE_FMSR_*` env var per knob, full `.env.example` block, sync mapping in `scripts/sync_scalper_config_from_env.py`, EA `JsonHasKey` in `LoadScalperConfigFromFile`.

---

## §10 Schema additions (5-layer ship)

Per `.claude/skills/forge-monitor/SKILL.md §I.5` schema-parity mandate. Six new SIGNALS columns:

| Column | Type | Notes |
|---|---|---|
| `fmsr_armed` | INTEGER | 0/1 — FMSR evaluated and armed this tick |
| `fmsr_direction` | INTEGER | 1=BUY_LIMIT, -1=SELL_LIMIT, 0=not armed |
| `fmsr_l1_price` | REAL | L1 entry price (0 if not armed) |
| `fmsr_l2_price` | REAL | L2 entry price (0 if not armed) |
| `fmsr_composite_score` | REAL | §B.8.2 Category 3 score 0-10 |
| `fmsr_offset_primary_ticket` | INTEGER | Ticket of underwater primary being netted (0 = standalone arm) |

Plus one new `gate_reason` enum entry: `fmsr_score_below_threshold` (Mode C, if promoted later).

5-layer changes: CREATE TABLE → ALTER TABLE migration → JournalRecordSignal placeholders (140 → 146) → `python/scribe.py sync_forge_journal` column list → `sql/forge_signals_schema.sql`.

---

## §11 Validation plan (before ship)

Per `docs/research/ICT_KILLZONES.md §9` checklist style. Tester replay scenarios:

| Scenario | Source data | Expected outcome |
|---|---|---|
| Bad-BUY-in-fast-dump | Apr 1 12:00 missed-bidirectional case (per memory `feedback_trade_decision_table_format`) | L1/L2 BUY_LIMITs arm at 62%/79% retrace of dump; both fill on bounce; net offsets primary loss |
| Bad-SELL-in-fast-rip | Apr 8 PM cascade window | L1/L2 SELL_LIMITs arm; one fills; primary loss reduced |
| One-way dump (no retrace) | A run with sustained −5 ATR move and no bounce | L1/L2 expire unfilled; SL on partial fill protects; daily DD cap engages if losses accumulate |
| Chop-grid trap | Any RANGE-regime period | FMSR should NOT arm (sweep + displacement won't both fire in chop); verify zero FMSR arms |
| DST boundary | Mar 30 / Apr 7 (US DST switch week) | FMSR killzone gate uses `g_regime.killzone` (per §B.7 single source of truth) — should not misfire across DST |

Promotion path: ship at `fmsr_enabled=0` default + `Mode A` (compute + log only, no real arms). Monitor 100+ tester ticks of would-fire decisions. Promote to `fmsr_enabled=1` + `Mode B` after the composite score histogram shows discrimination (per `feedback_supermajority_composite_threshold`).

---

## §12 Open questions (operator decisions needed before code)

1. **Default `fmsr_enabled`**: stay OFF until tester validation (recommended) or ON-Mode-A immediately for live data collection?
2. **`fmsr_killzone_required` default**: only arm in `LONDON_OPEN_KZ` + `NY_PM_KZ` (per §B.2) OR allow any killzone except `OFF_SESSION` OR allow `OFF_SESSION` too? (Stricter = fewer false arms; looser = more learning data.)
3. **`fmsr_auto_close_primary_on_offset`**: stay OFF (operator's standing preference per `feedback_dont_overask` — never auto-modify primary)? Or expose as toggle for advanced use?
4. **Composite-score threshold for arming**: Mode B at score ≥ 5 (current proposal) or Mode A only (always arm, log score) for initial validation?
5. **L1+L2 fill independence**: each leg has independent SL/TP (current proposal) or shared basket SL? Independent = cleaner accounting; basket = more drawdown-survival per `feedback_chop_grid_no_per_leg_sl`.

---

## §13 Cross-references

- `docs/FORGE_SETUP_ICT_MAP.md §B.2` — entry category (LIQUIDITY_SWEEP_REVERSAL)
- `docs/FORGE_SETUP_ICT_MAP.md §B.7` — killzone single-source-of-truth (FMSR reads `g_regime.killzone`)
- `docs/FORGE_SETUP_ICT_MAP.md §B.8.2 Category 3` — atom catalog + weights for the composite score
- `docs/FORGE_LOT_SIZING_PRE_ICT.md` — existing lot factor math (FMSR plugs in via `fmsr_l1_lot_factor` × existing `combined_lot_factor` pipeline)
- `docs/research/ICT_KILLZONES.md §5` — Approach B time handling (FMSR inherits via `g_regime`)
- `.claude/skills/forge-monitor/SKILL.md §I` + `§J` — modular + composite mandates this design conforms to
- `ea/include/Forge/IctLiquidity.mqh` — host module (Phase 2)

---

## §15 Living design considerations — recovery features + both-legs capture

This doc is a **living design surface** for the ICT refactoring's recovery + bidirectional-capture features. New ideas accumulate here under §15 as they arise during operations; promoted to §1-§13 specifications when they enter the v2.7.123 ship scope. Treat §15 as a working scratchpad, §1-§13 as the canonical spec.

### §15.1 Both-legs capture (operator-confirmed 2026-05-15)

The bidirectional pattern operator described — "open multiple buy/sell to do a stop or limit at that point to capture retract" — has two distinct legs that should be designed together, not bolted on separately:

| Leg | Direction (vs primary) | Purpose | Order type | ICT mapping |
|---|---|---|---|---|
| **Continuation leg** | Same as fast move (away from primary) | Capture continued momentum if sweep extends | STOP order beyond current price | `MSS_CONTINUATION` (per §B.2) |
| **Reversal leg** | Against fast move (toward primary) | Capture retracement when sweep exhausts | LIMIT order at OTE retrace | `LIQUIDITY_SWEEP_REVERSAL` (per §B.2) |

FMSR §1-§13 above specifies the **reversal leg** (LIMIT-at-OTE). The **continuation leg** is intentionally NOT in the v2.7.123 scope because:

1. The existing `SELL_STOP_CONT` / `BUY_STOP_CONT` mechanism (FORGE.mq5) IS the continuation leg, but it gates on primary-TP1 hit (same precondition flaw as the recoveries — see §1)
2. A primary-trade-independent continuation leg would mirror FMSR but for STOPs not LIMITs — a v2.7.124+ candidate after FMSR validates
3. Shipping both legs at once would double the test surface and amplify martingale risk if caps fail

**Design constraint**: when both legs ship, they share the same composite-score, same daily-DD kill, same loss-streak cap. The total exposure ceiling (primary + continuation + reversal) must be bounded by `fmsr_max_total_lot` (TBD knob, candidate default 3× primary lot).

### §15.2 Recovery features — design-consideration backlog (not yet specified)

Captured here as ideas to incorporate when scope opens for a Track C ship:

| Idea | Origin | Status |
|---|---|---|
| **Drawdown-aware lot taper** — recoveries reduce lot factor when account is in cumulative DD (e.g., −5% → ×0.5, −10% → pause) | Memory `feedback_lot_broker_minimum` extension + operator's 2026-05-15 lot-sizing question | candidate for Track C / Phase D (M13 in Appendix A) |
| **Bad-trade-state detection signal** — `g_regime.in_bad_trade_state` boolean computed from open-group MFE/MAE: true when oldest open primary is < −1×SL_dist away from entry without TP1 hit | Operator's 2026-05-15 ask, §1 gap | candidate for Track B v2.7.123 ship (no schema change beyond §10) |
| **Primary-close-on-rescue-fill** | §12 open question #3 | deferred — operator standing preference is "never auto-modify primary" per `feedback_dont_overask`; revisit if explicit policy flip |
| **Killzone amplifier on rescue lot** — within LONDON_OPEN_KZ or NY_PM_KZ, rescue lot ×1.3 (per §B.2 high-conviction KZ rule) | §B.7 killzone canon + v2.7.63 lot amplifier pattern | candidate for v2.7.123 if §10 schema column count permits |
| **Composite-score lot amplifier** — if FMSR composite score ≥ 8, lot factor ×1.2 (high-conviction sweep) | §B.8.3 Mode-B variant + §B.8 weight system | candidate for v2.7.123 |
| **OB-as-rescue-anchor** — when Phase 3 (`IctOrderBlock.mqh`) ships, use OB level as rescue anchor instead of/in addition to fib retrace | Phase 3 / M4 in Appendix A | candidate for v2.7.124 (post-OB-module ship) |
| **Time-of-day attenuation** — outside killzones, rescue lot ×0.5 (low-conviction window) | §B.7 killzone canon | candidate for v2.7.123 |
| **Anti-news kill** — FMSR disabled in news window (existing `news_filter_*` config) | Existing news filter | candidate for v2.7.123 — easy bolt-on |

### §15.3 Track A stopgap — recovery audit findings codified (applied 2026-05-15)

From the 2026-05-15 audit of existing `BUY_LIMIT_RECOVERY` + `SELL_LIMIT_RECOVERY`:

| `.env` change | From → To | Effect |
|---|---|---|
| `FORGE_BUY_LIMIT_RECOVERY_LOT_FACTOR` | 0.25 → 0.5 | Offset ratio ~25% → ~50% of primary loss |
| `FORGE_SELL_LIMIT_RECOVERY_LOT_FACTOR` | 0.25 → 0.5 | Mirror |
| `FORGE_BUY_LIMIT_RECOVERY_EXPIRY_BARS` | 4 → 8 | 20 min → 40 min retrace window |
| `FORGE_SELL_LIMIT_RECOVERY_EXPIRY_BARS` | 4 → 8 | Mirror |

These are NOT included in Track B v2.7.123 ship (already applied via env). Tracked here so the Track B implementation can verify they remain consistent post-ship.

### §15.4 Append-only policy

Future "while ops surfaces a recovery/capture idea" entries get appended to §15.2 with origin + status. Do NOT modify §1-§13 specs from a §15 entry — promote §15 ideas to §1-§13 only via explicit ship-scope opening.

---

## §14 Changelog

- **2026-05-15** — Initial design (operator-approved Track B per stopgap-first + design-doc-second plan). v2.7.123 candidate ship. No code yet.
- **2026-05-15** — §15 added as living design surface for recovery features + both-legs capture. §15.1 codifies continuation-leg vs reversal-leg split (FMSR §1-§13 = reversal leg only; continuation leg is v2.7.124+ candidate). §15.2 backlog of 7 recovery-feature ideas with origin + status. §15.3 records Track A stopgap `.env` tweaks (lot 0.25→0.5, expiry 4→8 bars) applied same day. §15.4 append-only policy.
