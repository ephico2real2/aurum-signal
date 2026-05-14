# FORGE PEMCG / UMCG / CVCSM / Layer 3 — Architecture Reference

**Status**: Living document. Updated whenever a PEMCG composite, atom, layer consumer, or related gate ships.
**Purpose**: Authoritative source-of-truth for how the 7-atom PEMCG composite is computed, who consumes it, what each consumer does, and where in `ea/FORGE.mq5` to find each piece.
**Cross-references**: `docs/FORGE_CASE_STUDY_G5006_INFLECTION_POINT.md` (origin), `docs/FORGE_DECISION_STACK.md` (5-layer model), forge-monitor SKILL.md (operational use).

---

## §0 The operator question that motivated this document

> **Operator** (2026-05-14): "so are you using any of the state machine and PEMCG so far? just a personal question — how are they related"

This was a watershed question — the answer revealed that PEMCG is a **composite** (a computed integer), not a gate, and that three different gates **consume** it for three different purposes. Most "PEMCG" discussions before this point conflated the signal with its consumers. The verbatim Q&A is preserved in §6 below.

---

## §1 Short answer (the one-paragraph version)

- **PEMCG** is a computed integer (0-7) updated every M5 close — the SIGNAL.
- **UMCG (Layer 1)** uses PEMCG ≥ threshold to BLOCK setups at trigger time.
- **CVCSM (Layer 2)** uses PEMCG to decide when to RELEASE direction from cooldown after an SL.
- **Layer 3 BB_EXHAUSTION_REVERSAL** uses PEMCG ≥ min_warnings to FIRE counter-trades.
- **v2.7.93/94** are setup-specific gates that do NOT use PEMCG (independent geometry/volatility checks).

All four are related by sharing the same PEMCG composite as input — they're different consumers of one signal.

---

## §1A Acronym dictionary + how the layers relate (v2.7.97 update)

### §1A.1 Acronyms and what they actually mean

| Acronym | Expansion | Type | Role |
|---|---|---|---|
| **PEMCG** | **P**re-**E**ntry **M**arket **C**ondition **G**ate | computed integer pair (0-7 each) | The SIGNAL — counts how many reversal-warning atoms are firing per direction |
| **UMCG** | **U**niversal **M**arket **C**ondition **G**ate | layer-1 boolean check at setup-trigger time | The BLOCKER — if PEMCG ≥ threshold, refuses to fire the setup |
| **CVCSM** | **C**onditional **V**olatility **C**ooldown **S**tate **M**achine | layer-2 per-direction state (OPEN/COOLDOWN/RETRYING) | The COOLDOWN — locks out same direction after an SL hit, releases when PEMCG clears for N M5 bars |
| **DLV** | **D**irection **L**ock **V**erdict | enum (VALID/INVALID/NEUTRAL/PROFIT_TARGET) | The VERDICT — what `EvaluateDirectionLock()` returns per group every M5 close (v2.7.97 NEW) |
| **DLS** | **D**irection **L**ock **S**tate | per-direction enum (IDLE/ARMED/COOLDOWN_REEVAL/DISCARDED) | The STATE — what direction is currently committed; managed by `UpdateDirLockState()` (v2.7.97 NEW) |

**Why three operator-coined acronyms and two AI-created ones?** The first three (PEMCG/UMCG/CVCSM) were operator-coined during the v2.7.84 design conversation on 2026-05-13 — see `docs/FORGE_CASE_STUDY_G5006_INFLECTION_POINT.md` for the original framing. DLV and DLS were introduced in v2.7.97 (this session, 2026-05-14) as part of Sets 6+7+8 — the operator-mandated direction-lock layer that complements (but does NOT replace) the CVCSM cooldown. Naming follows the existing PEMCG/UMCG/CVCSM 4-5-letter pattern + the operator-mandated `<setup_or_composite>_<gate_concept>_<direction?>` rule from `FORGE_NAMING_CONVENTIONS.md §4.7`.

### §1A.2 What each acronym holds (indicator values, thresholds, booleans grouped together)

#### PEMCG — the SIGNAL

```
INDICATORS (raw inputs, per-tick)
   m5_rsi              RSI (14) on M5
   m5_body_pct         (|close - open|) / (high - low) of the latest M5 bar
   m5_strong_bar       boolean: high-volatility + body% > threshold + direction-agnostic
   m5_range_expanding  boolean: ATR rising past prior 5-bar avg
   bb_upper / bb_lower BB ±2σ on M5
   m5_atr / m5_atr_5bar M5 ATR + 5-bar ratio
   macd_histogram      MACD(3,10,16) histogram on M5
   m5_close vs m5_close_1  current bar close vs prior bar close

THRESHOLDS (knobs that turn indicator values → boolean atoms)
   umcg_pemcg_rsi_overbought = 65.0     ← A1 BUY-trap threshold
   umcg_pemcg_rsi_oversold   = 35.0     ← A1 SELL-trap threshold
   umcg_pemcg_body_pct_max_weak = 0.5   ← A2 threshold
   umcg_pemcg_atr_ratio_max_contract = 1.0  ← A6 threshold
   umcg_pemcg_bb_dist_atr_threshold = 0.3   ← A5 threshold

BOOLEAN ATOMS (one bit each, summed 0..7)
   A1 = (BUY: rsi ≥ ob)  / (SELL: rsi ≤ os)        ← directional, NOT mirrored
   A2 = body_pct < weak                              ← direction-agnostic
   A3 = strong_bar == 0                              ← direction-agnostic
   A4 = range_expanding == 0                         ← direction-agnostic
   A5 = (BUY: close − bb_upper) / atr < 0.3          ← directional
        (SELL: bb_lower − close) / atr < 0.3
   A6 = atr_5bar ratio < contract                    ← direction-agnostic
   A7 = (BUY: macd_hist < 0 AND close < close_1)     ← directional (divergence)
        (SELL: macd_hist > 0 AND close > close_1)

OUTPUTS (the SIGNAL — consumed by every layer below)
   g_pemcg_buy_warning_count  ∈ [0..7]
   g_pemcg_sell_warning_count ∈ [0..7]
```

#### UMCG — the BLOCKER (layer 1)

```
INDICATORS — uses PEMCG outputs directly (not raw atoms)

THRESHOLDS
   umcg_buy_block_threshold  = 5       ← BUY blocked if pemcg_buy_warning ≥ this
   umcg_sell_block_threshold = 5       ← SELL blocked if pemcg_sell_warning ≥ this
   umcg_enabled              = bool    ← master flag

BOOLEAN OUTPUT
   per-direction: "block this setup-trigger fire" (bool)

CODE LOCATION
   ea/FORGE.mq5:~12734  setup-trigger chokepoint
   Emits SKIP gate_reason: pemcg_buy_reversal_block / pemcg_sell_reversal_block
```

#### CVCSM — the COOLDOWN STATE MACHINE (layer 2)

```
TRIGGER (state transition into COOLDOWN)
   SL hit on a group in this direction → state = COOLDOWN
   (TP firing does NOT trigger — operator-mandated)

INDICATORS — uses PEMCG outputs to decide release

THRESHOLDS
   cvcsm_release_threshold      = 2    ← PEMCG warnings < this allows transition to RETRYING
   cvcsm_required_clean_bars    = 2    ← N M5 bars in RETRYING with clean PEMCG → OPEN
   cvcsm_max_cooldown_sec       = 1800 ← safety hard timeout (30 min) regardless of PEMCG state
   cvcsm_trigger_on_sl          = 1    ← bool master: SL events trigger cooldown
   cvcsm_trigger_on_regime_flip = 1    ← bool optional: regime flip also triggers
   cvcsm_enabled                = bool ← master flag

PER-DIRECTION STATE
   g_cvcsm_state_buy   ∈ {0=OPEN, 1=COOLDOWN, 2=RETRYING}
   g_cvcsm_state_sell  (mirror)
   g_cvcsm_cooldown_start_buy/sell    (timestamps for safety timeout)
   g_cvcsm_clean_bars_buy/sell        (counter for RETRYING → OPEN)

BOOLEAN OUTPUT
   per-direction: "block this setup-trigger fire" (bool, when state != OPEN)

CODE LOCATION
   ea/FORGE.mq5:~6951  M5-bar-close evaluator
   Emits SKIP gate_reason: cvcsm_cooldown_block_buy / cvcsm_cooldown_block_sell
```

#### Direction Lock (DLV + DLS) — the DIRECTION COMMITMENT (layer 1B — v2.7.97 NEW)

This is a NEW layer added in v2.7.97. It is **independent from CVCSM** (which is post-SL-only). Direction Lock activates at every Leg 1 placement and re-evaluates every M5 close.

```
PER-GROUP STATE (added in v2.7.97)
   g_groups[gi].direction_lock_broken  ∈ {false, true}
   g_groups[gi].entry_swing_high       (computed at entry, last N M5 bars high)
   g_groups[gi].entry_swing_low        (computed at entry, last N M5 bars low)

PER-DIRECTION STATE MACHINE (DLS = Direction Lock State)
   g_dirlock_state_buy   ∈ {0=IDLE, 1=ARMED, 2=COOLDOWN_REEVAL, 3=DISCARDED}
   g_dirlock_state_sell  (mirror)
   g_dirlock_armed_time_buy/sell        (timestamps)
   g_dirlock_active_group_buy/sell      (group index that armed this direction)
   g_dirlock_last_break_time            (timestamp of last lock break)

INDICATORS (per-tick, all pre-existing)
   m5_close   (latest CLOSED M5 bar, NOT current bar)
   atr        (M5 ATR via h_atr handle)
   pemcg_buy_warning_count, pemcg_sell_warning_count
   g_eval_h1_trend        (cached h1 trend strength)

THRESHOLDS (4 + 1 swing-lookback)
   dirlock_struct_break_atr_mult = 0.5   ← body-close beyond entry_swing ± atr × this → INVALID
   dirlock_flip_threshold        = 5     ← opposite-direction PEMCG ≥ this → INVALID
   dirlock_neutral_threshold     = 3     ← bilateral PEMCG ≥ this on both sides → NEUTRAL
   dirlock_h1_disagreement       = 0.5   ← |h1_trend| disagrees with locked dir by ≥ this → INVALID
   dirlock_swing_lookback_bars   = 5     ← bars to scan for entry_swing high/low
   dirlock_break_bilateral_cooldown_bars = 2  ← M5 bars to block BOTH dirs after break
   direction_lock_enabled        = bool ← master flag

VERDICT ENUM (DLV = Direction Lock Verdict)
   DLV_VALID         = 0    ← keep ARMED, continue trading
   DLV_INVALID       = 1    ← structural break or PEMCG flip or HTF disagreement
   DLV_NEUTRAL       = 2    ← bilateral PEMCG high — both directions look chopped
   DLV_PROFIT_TARGET = 3    ← group's TP3 hit or all positions closed (clean exit)

BOOLEAN OUTPUTS
   IsDirLockBlocked(direction) — used at setup-trigger fire
   CancelPendingOnStructureFlip() — used at every M5 close (kills cascade pendings on break)

CODE LOCATION
   ea/FORGE.mq5:~14213  EvaluateDirectionLock()
   ea/FORGE.mq5:~14282  CancelPendingOnStructureFlip()
   ea/FORGE.mq5:~14310  UpdateDirLockState()
   Emits SKIP gate_reason: dirlock_block_buy / dirlock_block_sell
```

### §1A.3 How the layers fire in sequence (single setup-trigger tick)

```
                Setup composite fires (e.g., BB_BREAKOUT BUY)
                                  │
                                  ▼
       ┌──────────────────────────────────────────────────┐
       │  Layer 1 — UMCG (BLOCKER, PEMCG-driven)          │
       │   pemcg_<dir>_warning_count ≥ umcg_threshold?    │
       └──────────────────────┬───────────────────────────┘
                              │  No
                              ▼
       ┌──────────────────────────────────────────────────┐
       │  Layer 2 — CVCSM (BLOCKER, SL-cooldown)          │
       │   g_cvcsm_state_<dir> != 0 (OPEN)?               │
       └──────────────────────┬───────────────────────────┘
                              │  No
                              ▼
       ┌──────────────────────────────────────────────────┐
       │  Layer 1B — Direction Lock (BLOCKER, bilateral)  │  v2.7.97 NEW
       │   IsDirLockBlocked(dir)?                         │
       │   = state == DISCARDED?                          │
       │   OR bilateral cooldown active (since last break)│
       └──────────────────────┬───────────────────────────┘
                              │  No
                              ▼
       ┌──────────────────────────────────────────────────┐
       │  Layer 3 — entry execution                       │
       │   PlaceOpenGroupLeg / PlaceMarketBatch           │
       │   → 4 market positions (v2.7.99 batch)           │
       │   → dirlock_state_<dir> IDLE → ARMED             │
       └──────────────────────────────────────────────────┘

                Then every M5 close, in parallel:
       ┌──────────────────────────────────────────────────┐
       │  Layer 0 — PEMCG (the SIGNAL)                    │
       │   Recompute g_pemcg_<dir>_warning_count          │
       │   from 7 atoms (RSI, body, strong bar, range,    │
       │   BB-prox, ATR-contract, MACD divergence)        │
       │   These outputs feed UMCG/CVCSM/DirLock above    │
       └──────────────────────────────────────────────────┘
       ┌──────────────────────────────────────────────────┐
       │  Layer 1B — UpdateDirLockState (for each dir)    │
       │   for each ARMED group:                          │
       │     verdict = EvaluateDirectionLock(dir, gi)     │
       │     if verdict == DLV_VALID: keep ARMED          │
       │     else: state → DISCARDED                      │
       │           bilateral cooldown engages             │
       │   CancelPendingOnStructureFlip() — kills stale   │
       │   cascade pendings whose group's lock broke      │
       └──────────────────────────────────────────────────┘
       ┌──────────────────────────────────────────────────┐
       │  Layer 2 — CVCSM eval (post-SL cooldown)         │
       │   COOLDOWN → RETRYING when pemcg_<dir> clears    │
       │   RETRYING → OPEN after N clean bars             │
       └──────────────────────────────────────────────────┘
```

### §1A.4 What "indicator values, thresholds, booleans grouped together" means

The system is **layered**, where each layer takes the lower layer's output as input:

```
┌────────────────────────────────────────────────────────────────┐
│  RAW INDICATORS (per-tick)                                     │
│   M5: rsi, atr, body_pct, strong_bar, range_expanding,         │
│       bb_upper/lower, macd_hist, close vs close_1              │
│   H1: di+ / di- / h1_trend_strength                            │
│   Regime: g_regime_label (TREND_BULL / TREND_BEAR / RANGE / …) │
└────────────────────────────────┬───────────────────────────────┘
                                 │
                       (compared to thresholds)
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────┐
│  ATOMS (boolean per atom, computed every M5 close)             │
│   PEMCG 7 atoms ×2 directions = 14 booleans                    │
│   Direction-lock atoms (M5 close vs swing, h1_trend, …)        │
└────────────────────────────────┬───────────────────────────────┘
                                 │
                       (summed into counts)
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────┐
│  PEMCG COUNTS (the SIGNAL — 2 integers per tick)               │
│   g_pemcg_buy_warning_count  ∈ [0..7]                          │
│   g_pemcg_sell_warning_count ∈ [0..7]                          │
└────────────────────────────────┬───────────────────────────────┘
                                 │
                  (compared to LAYER-level thresholds)
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
   UMCG (layer 1)         CVCSM (layer 2)        Direction Lock (1B)
   block at trigger       cooldown after SL      lock at Leg 1 fire
   threshold ≥ 5/7        threshold < 2/7        threshold ≥ 5/7
   gate: pemcg_*_block    gate: cvcsm_cooldown_  gate: dirlock_block_
                            block_*                *

                                 ▼
              ALL three feed the same setup-trigger chokepoint;
              ANY ONE returning "block" = SKIP this entry.
```

The grouping is:
- **Indicators** = raw numeric values from MT5 (RSI, ATR, prices).
- **Thresholds** = config knobs (`umcg_pemcg_rsi_overbought=65`, `dirlock_struct_break_atr_mult=0.5`, etc.) that turn numeric values into binary tests.
- **Atoms** = booleans produced by `indicator ⊕ threshold` (e.g., `rsi ≥ 65` is one atom).
- **Counts** = sum of atom booleans for the direction (PEMCG_BUY = sum of 7 BUY-trap atoms).
- **Layer verdicts** = a boolean per layer (UMCG, CVCSM, DirLock) decided by comparing counts to LAYER-thresholds (e.g., `pemcg_buy ≥ umcg_buy_block_threshold` → block).
- **Final entry decision** = any-layer-blocks logical OR.

---



PEMCG is **two integers** computed in `ForgeEvalAtoms()` once per M5 bar close:

| Global | Range | Meaning |
|---|---|---|
| `g_pemcg_buy_warning_count` | 0-7 | "How many BUY-trap atoms are firing right now" |
| `g_pemcg_sell_warning_count` | 0-7 | Mirror for SELL-trap |

**Code location**: `ea/FORGE.mq5:6621-6663` (computation block inside `ForgeEvalAtoms`).

### §2.1 The 7 atoms (current values, v2.7.94)

| # | Atom | BUY-trap condition | SELL-trap condition (mirror) | Knob (default) | Version |
|---|---|---|---|---|---|
| A1 | RSI extreme | `m5_rsi ≥ 65` | `m5_rsi ≤ 35` | `umcg_pemcg_rsi_overbought=65` / `_oversold=35` | v2.7.88 widened from 70/30 |
| A2 | Weak candle | `m5_body_pct < 0.5` | (same — direction-agnostic) | `umcg_pemcg_body_pct_max_weak=0.5` | v2.7.84 |
| A3 | No strong bar | `m5_strong_bar == 0` | (same) | (hardcoded boolean) | v2.7.84 |
| A4 | Range contracting | `m5_range_expanding == 0` | (same) | (hardcoded boolean) | v2.7.84 |
| A5 | Close near BB band | `abs(close − bb_upper) / atr < 0.3` | `abs(bb_lower − close) / atr < 0.3` | `umcg_pemcg_bb_dist_atr_threshold=0.3` | v2.7.87 fixed sign bug |
| A6 | ATR contracting | `m5_atr_ratio_5bar < 1.0` | (same) | `umcg_pemcg_atr_ratio_max_contract=1.0` | v2.7.84 |
| A7 | MACD divergence | `macd < 0 AND close > prev_close` | `macd > 0 AND close < prev_close` | (hardcoded relational) | v2.7.84 |

**Important**: Atoms A2/A3/A4/A6 are **direction-agnostic** — they fire for both BUY and SELL composites on the same bar. Only A1, A5, A7 are direction-specific.

### §2.2 Why "warning count" not "boolean"

The composite produces a count (0-7) rather than a binary so consumers can apply **different thresholds**:
- Layer 1 UMCG uses ≥ 5/7 (supermajority) — strict block
- Layer 3 reversal uses ≥ 4/7 (majority-minus-one) — fire counter-trade
- CVCSM release uses < 2/7 — clean-bar threshold

One signal, three thresholds, three semantic meanings.

---

## §3 The three layers that CONSUME PEMCG

### §3.1 Layer 1 — UMCG (Universal Market Condition Gate)

**File:line**: `ea/FORGE.mq5:12456-12492` (refreshed 2026-05-14 per codex review)
**Statefulness**: Stateless. Re-evaluated at every setup trigger.
**Operation**:

```
At every setup trigger (any setup, any direction):
  IF direction == "BUY" AND g_pemcg_buy_warning_count >= umcg_buy_block_threshold (5):
     emit gate_reason: pemcg_buy_reversal_block
     direction = "", setup_type = ""   (clears so Layer 3 can evaluate)
  IF direction == "SELL" AND g_pemcg_sell_warning_count >= umcg_sell_block_threshold (5):
     emit gate_reason: pemcg_sell_reversal_block
     direction = "", setup_type = ""
```

**Knobs**:
| Knob | Default | Meaning |
|---|---|---|
| `umcg_enabled` | 1 | Master switch |
| `umcg_buy_block_threshold` | 5 (v2.7.86) | Atoms needed to block BUY |
| `umcg_sell_block_threshold` | 5 (v2.7.86) | Mirror |

### §3.2 Layer 2 — CVCSM (Conditional Cooldown State Machine)

**File:line**: `ea/FORGE.mq5:6725-6777` (state update) + `:12472-12482` (gate enforcement) — refreshed 2026-05-14
**Statefulness**: Two independent state machines (BUY + SELL), each in `OPEN | COOLDOWN | RETRYING`.
**Operation**:

```
TRIGGER → COOLDOWN: SL fires in that direction (via OnTradeTransaction hook)
At every M5 close:
  IF state == COOLDOWN:
     IF pemcg_count < cvcsm_release_threshold (2):
        state = RETRYING, clean_bars = 1
     ELSE IF (now − cooldown_start) ≥ max_cooldown_sec (1800):
        state = OPEN (safety release)
  IF state == RETRYING:
     IF pemcg_count < cvcsm_release_threshold:
        clean_bars++
        IF clean_bars ≥ required_clean_bars (2):
           state = OPEN
     ELSE:
        state = COOLDOWN, clean_bars = 0   (re-trapped)

At every setup trigger:
  IF state != OPEN for that direction:
     emit gate_reason: cvcsm_cooldown_block_<dir>
     direction = "", setup_type = ""
```

**Knobs**:
| Knob | Default | Meaning |
|---|---|---|
| `cvcsm_enabled` | 1 | Master switch |
| `cvcsm_release_threshold` | 2 | PEMCG count below this = "clean" bar |
| `cvcsm_required_clean_bars` | 2 | Consecutive clean bars needed to release |
| `cvcsm_max_cooldown_sec` | 1800 | Safety timeout (30 min) |
| `cvcsm_trigger_on_sl` | 1 | Enter COOLDOWN when SL fires |
| `cvcsm_trigger_on_regime_flip` | 1 | Enter COOLDOWN when regime changes against existing direction |

**Important**: TP firing does NOT trigger cooldown — only SL. This was the operator-mandated design: "TPs don't trigger cooldown — only SLs."

### §3.3 Layer 3 — BB_EXHAUSTION_REVERSAL (counter-trade capture)

**File:line**: `ea/FORGE.mq5:12494-12624` (SELL block 12494-12568, BUY mirror 12570-12624) — refreshed 2026-05-14
**Statefulness**: Stateless trigger — fires whenever conditions align.
**Operation**:

```
SELL counter-trade (fires when BUY direction is in trap):
  IF direction == "" (cleared by UMCG or no setup):
     IF g_pemcg_buy_warning_count >= bb_exhaustion_reversal_min_warnings (4):
        IF NOT (m5_rsi ≤ oversold AND |bb_lower − mid|/atr < 0.3):  // v2.7.90 directional opposite check
           IF m5_adx < bb_exhaustion_reversal_max_adx (35):           // v2.7.92 ADX gate
              IF prev_bar_range/atr < max_prev_bar_range_atr_mult (2.0):  // v2.7.94 WRB gate
                 IF cvcsm_state_sell == OPEN:
                    IF no existing SELL within proximity_atr (1.5) × ATR:
                       IF cooldown elapsed (default 0 = always re-fire):
                          FIRE BB_EXHAUSTION_REVERSAL_SELL @ current bid
                          (tier-based: HIGH if pemcg≥6, BASE otherwise — v2.7.89)

BUY counter-trade: full mirror with PEMCG_SELL, BB upper, m5_rsi ≥ overbought, etc.
```

**Knobs** (v2.7.89/90/91/92/94 — extensive):
| Knob | Default | Purpose |
|---|---|---|
| `bb_exhaustion_reversal_enabled` | 1 | Master |
| `bb_exhaustion_reversal_min_warnings` | 4 | PEMCG threshold to fire |
| `bb_exhaustion_reversal_lot` | 0.10 | Base lot |
| `bb_exhaustion_reversal_lot_amplifier` | 1.5 | BASE-tier multiplier (v2.7.89/91) |
| `bb_exhaustion_reversal_high_conviction_warnings` | 6 | PEMCG threshold for HIGH tier |
| `bb_exhaustion_reversal_high_conviction_lot_factor` | 2.0 | HIGH-tier additional lot factor |
| `bb_exhaustion_reversal_legs_high_conviction` | 4 | HIGH-tier leg count (BASE=1) |
| `bb_exhaustion_reversal_max_adx` | 35.0 | v2.7.92 ADX gate (don't counter strong trend) |
| `bb_exhaustion_reversal_max_prev_bar_range_atr_mult` | 2.0 | v2.7.94 WRB gate (don't catch falling knife) |
| `bb_exhaustion_reversal_proximity_atr` | 1.5 | Throttle: skip if existing same-dir within this×ATR |
| `bb_exhaustion_reversal_cooldown_sec` | 0 (v2.7.91) | Time cooldown disabled — proximity is the throttle |

### §3.4 Layer 4 — DTC (Day-Type Classifier) — PEMCG modifier + Day-Bias hard block (v2.7.105)

**File:line**: `ea/FORGE.mq5` PEMCG-block (computation) + UMCG enforcement block (hard-block check).
**Statefulness**: Stateless per-tick — recomputed at every M5 close from live indicators.
**Origin**: Run 36 v2.7.102 monitoring 2026-05-14. PEMCG_SELL fired **63,716** times during a 140-pt bear move (Apr-01 22:00 → Apr-02 23:59) while ZERO SELL setups were TAKEN. Mirror PEMCG_BUY fired only **5,494** times — **12× asymmetry**. Root cause: PEMCG_SELL atoms A1 (RSI≤35) and A5 (close near BB_lower) fire by definition in ANY sustained bear leg; combined with A2/A3/A4/A6 firing opportunistically on small consolidation bars, the warning count reaches 5/7 even when the signal is direction-correct trend-continuation.

**Indicator triad** (validated against 11,669-sample blocked-SELL window 10:00-15:00 Apr-02):

| Indicator | Bear-day threshold | Bull-day threshold | Rationale |
|---|---|---|---|
| VWAP-distance (in ATR) | ≤ −1.5 | ≥ +1.5 | Run 36 bear-window avg: −4.18 ATR. VWAP is the canonical intraday sentiment line (mql5.com/blogs/767595). |
| M15 ADX | ≥ 25 | ≥ 25 | Industry rule: ADX ≥ 25 means trending regime; RSI overbought/oversold loses reliability as reversal signal and gains reliability as continuation (volity.io RSI guide). |
| H1 DI dominance | DI− − DI+ ≥ 5 | DI+ − DI− ≥ 5 | Direction-of-trend even when h1_trend_strength lags (Run 36 showed h1_trend was still +0.42 during active bear; DI+/DI− leads). |
| Daily-bias guard | NOT `g_daily_bull_bias` | NOT `g_daily_bear_bias` | Avoid firing against the macro daily context. |

**Notably absent from the triad**: `h1_trend_strength`. Run 36 data proved it was still +0.42 (POSITIVE) during the active 140-pt bear — the H1 EMA-based trend strength lags 1+ hour on fresh reversals. **VWAP + M15 ADX + H1 DI is the correct intraday-bias detector**.

**Two consequences when day-type confirmed** (both default-OFF; activated independently via sub-flags):

#### §3.4a — PEMCG modifier (`dtc_pemcg_modifier_enabled`)
When `g_dtc_bear_day_intraday` AND direction == SELL → subtract `dtc_pemcg_bypass_atoms` (default 2) from `g_pemcg_sell_warning_count` (clamped to 0). Lowers the chance of false reversal-trap block on direction-correct continuation SELLs.

Mirror: `g_dtc_bull_day_intraday` AND direction == BUY → subtract from `g_pemcg_buy_warning_count`.

#### §3.4b — Day-Bias hard block (`dtc_day_bias_block_enabled`)
When day-type OPPOSES setup direction AND setup NOT in exempt list → emit hard SKIP gate:
- `bear_day_buy_block` when `g_dtc_bear_day_intraday` AND direction == BUY
- `bull_day_sell_block` when `g_dtc_bull_day_intraday` AND direction == SELL

Exemption lists (comma-separated strings) protect intentional counter-regime setups:
- `dtc_exempt_buy_setups` default = `"BB_EXHAUSTION_REVERSAL_BUY"` (the §3.3 reversal-capture setup)
- `dtc_exempt_sell_setups` default = `"FRACTIONAL_SELL_IN_BULL,BB_EXHAUSTION_REVERSAL_SELL"` (operator's intentional bull-day SELL probe + §3.3 mirror)

**Knobs**:
| Knob | Default | Meaning |
|---|---|---|
| `dtc_enabled` | 0 | Master switch (false = no DTC computation; behaves like pre-v2.7.105) |
| `dtc_pemcg_modifier_enabled` | 0 | Apply §3.4a de-weighting on day-type match |
| `dtc_day_bias_block_enabled` | 0 | Apply §3.4b hard block on day-type oppose |
| `dtc_vwap_dist_atr_threshold` | 1.5 | VWAP-distance threshold (ATR units, absolute) |
| `dtc_m15_adx_min` | 25 | M15 ADX minimum |
| `dtc_h1_di_dominance_min` | 5.0 | H1 |DI+ − DI−| minimum |
| `dtc_pemcg_bypass_atoms` | 2 | Atoms subtracted when day-type matches |
| `dtc_exempt_buy_setups` | "BB_EXHAUSTION_REVERSAL_BUY" | Bear-day BUY-block exempt list |
| `dtc_exempt_sell_setups` | "FRACTIONAL_SELL_IN_BULL,BB_EXHAUSTION_REVERSAL_SELL" | Bull-day SELL-block exempt list |

**Layer ordering** (in UMCG enforcement block):
1. UMCG (Layer 1 — PEMCG threshold) — but PEMCG count already modified by §3.4a if enabled
2. CVCSM (Layer 2 — cooldown state)
3. DirLock (v2.7.97 — direction lock state)
4. **DTC Day-Bias hard block (§3.4b — new, v2.7.105)** ← inserted here
5. Setup fires only if all 4 layers pass

This makes DTC the OUTERMOST gate when day-type opposes direction — fast-rejects knife-catches even when UMCG/CVCSM/DirLock all pass.

**Cross-references**:
- `config/gate_legend.json` entries: `bear_day_buy_block`, `bull_day_sell_block`
- `scripts/sync_scalper_config_from_env.py` mappings: `FORGE_COMPOSITE_DTC_*` + `FORGE_GATE_DTC_*`
- `.env.example` block: search `FORGE_COMPOSITE_DTC_ENABLED`
- Industry research log: see §9 v2.7.105 entry below

**Validation evidence** (Run 36 v2.7.102 backtest, 11,669-sample blocked-SELL window):
```
Avg ATR              10.08
Avg VWAP-distance    -43.51 pts = -4.18 ATR (target threshold: -1.5 ATR → ALL 11,669 caught)
Avg M15 ADX          28.7 (target: ≥ 25 → ALL caught)
Avg H1 DI balance    < -5 (confirmed bear DI dominance)
Avg RSI              47.1 (NOT oversold — confirms PEMCG was over-firing on non-A1 atoms)
Avg h1_trend         +0.42 (POSITIVE — proves h1_trend is unreliable for fresh reversals)
```

### §3.5 Layer 4 (continued) — DTC 5-state classifier (v2.7.107 ICT-canonical)

v2.7.105 binary day-type was a partial fix. Run 36 produced TWO additional knife-catch losses that v2.7.105 cannot block because the **intraday triad alone is ambiguous between trend-continuation and corrective-retracement**:

- **G5021 Apr-06 17:35: MOMENTUM_DUMP BUY @ 4697.86, RSI 65.9, M5 ADX 32.1, M15 ADX 22.2, h1_trend +0.28, VWAP_dist_atr +1.60.** M15 ADX 22.2 < v2.7.105's 25 threshold → `g_dtc_bull_day_intraday = false` → v2.7.105 DOES NOT BLOCK. But H4 trend by Apr-06 had been declining 4 days (4780 → 4630) — clearly bear. The intraday "bull" was a corrective bounce that the bear macro crushed. Cascade lost **−$498.60** across 4 legs.
- **G5026 Apr-07 07:40**: BB_EXHAUSTION_REVERSAL_SELL @ 4658.5 (exempt setup, not relevant to fix).

The fix is H4 trend agreement as a **fourth axis** layered on the intraday triad, producing **5 states**:

| State | Intraday triad | H4 trend | ICT class | Default behaviour |
|---|---|---|---|---|
| `BULL_TREND_ALIGNED` | bull | ≥ +0.5 | Trend-aligned bull | de-weight pemcg_buy + block SELLs |
| `BEAR_TREND_ALIGNED` | bear | ≤ −0.5 | Trend-aligned bear | de-weight pemcg_sell + block BUYs |
| `COUNTER_TREND_BULL` | bull | ≤ −0.5 | Corrective bounce in bear macro | optionally block BUYs (`dtc_block_counter_trend_buys`) |
| `COUNTER_TREND_BEAR` | bear | ≥ +0.5 | Corrective dip in bull macro (**OTE setup at H4 demand**) | optionally block SELLs (`dtc_block_counter_trend_sells`); BUYs at deep oversold remain ALLOWED |
| `NEUTRAL` | not confirmed | any | No bias decided | pre-DTC behaviour |

**Critical asymmetry**: counter-trend states do NOT trigger PEMCG modifier. The PEMCG composite stays fully strict in those states because counter-trend retracements are high-failure-rate (H4 macro re-asserts). Only TREND_ALIGNED states de-weight PEMCG warnings.

**G5016 case (Apr-02 08:34 BB_LOWER_REVERSION_BUY @ 4640, lost −$111.90)** fits `COUNTER_TREND_BEAR` (bear intraday inside still-bull H4 from Apr-01 rally). The 5-state design **correctly LETS THIS FIRE** — BB_LOWER_REVERSION_BUY at deep oversold (VWAP_dist −9.68 ATR is extreme) near H4 demand is the canonical ICT OTE setup. The −$112 loss is bad-luck-on-OTE, not structural. The structural fix is a separate "weak bar at deep oversold" atom (operator's prior G5006 inflection-point mandate), not a DTC block.

**ICT framework alignment** (per `tradeciety.com/multiple-time-frame-analysis` + ICT 2024 lectures):
> "Trade only in direction of H4 bias unless confirmed MSS. Counter-bias trades at most fractional sizing. OTE re-entries at H4 premium/discount are the canonical setup."

The 5-state design implements this verbatim:
- Trend-aligned = full DTC (block opposite-direction knife-catches, amplify trend-aligned)
- Counter-trend = optional block of knife-catch entries (operator-configurable per direction)
- OTE = always allowed (intraday counter-trend dip inside bull H4 macro = canonical OTE — never blocked)

**Knobs** (v2.7.107 adds 4 to v2.7.105's 9):

| Knob | Default | Meaning |
|---|---|---|
| `dtc_5state_enabled` | 0 | Master: 0 = v2.7.105 binary; 1 = v2.7.107 5-state |
| `dtc_h4_trend_min_agreement` | 0.5 | \|h4_trend_strength\| ≥ this for H4 bias to be "decided" |
| `dtc_block_counter_trend_buys` | 0 | Block BUYs in COUNTER_TREND_BULL state |
| `dtc_block_counter_trend_sells` | 0 | Block SELLs in COUNTER_TREND_BEAR state |

**Two new gate codes**:
- `counter_bull_day_buy_block` (catches G5021-class corrective-bounce knife-catch BUYs)
- `counter_bear_day_sell_block` (mirror — corrective-dip knife-catch SELLs)

**Backward compatibility**: when `dtc_5state_enabled = 0` (default), the EA falls back to v2.7.105 binary behaviour exactly. v2.7.106 binary-H4-agreement was skipped — operator went straight from v2.7.105 (binary intraday) to v2.7.107 (5-state) per "Option 2 wins" ICT-canonical decision.

---

## §4 Side gates that DO NOT use PEMCG

These are setup-specific quality checks. They co-fire alongside the PEMCG stack but use their own logic.

| Gate | Version | What it checks | Cite |
|---|---|---|---|
| `bb_breakout_buy_below_band` | v2.7.93 | BB_BREAKOUT BUY only fires when `(mid − bb_upper)/atr ≥ 0.1` (real breakout, not retest) | `ea/FORGE.mq5:10781-10798` |
| `bb_breakout_sell_above_band` | v2.7.93 | Mirror | `ea/FORGE.mq5:11156-11173` |

These were shipped after PEMCG kept missing G5006-class trades because PEMCG atoms flipped during the retest bar. The fix is at the setup level, not the composite level.

---

## §5 ASCII workflow — single-tick decision flow

```
                   M5 close at time T
                          │
                          ▼
            ╔══════════════════════════════╗
            ║   ForgeEvalAtoms() runs      ║
            ║                              ║
            ║   COMPUTES:                  ║
            ║   • g_pemcg_buy_warning_count║
            ║   • g_pemcg_sell_warning_count║
            ║   • Bar atoms (strong_bar,   ║
            ║     range_expanding, etc.)   ║
            ╚══════════════════════════════╝
                          │
                          ▼
         ┌─────────────────────────────────────┐
         │  Layer 2 (CVCSM) bar-close update   │
         │                                     │
         │  For each direction (BUY, SELL):    │
         │    • state COOLDOWN → RETRYING?     │
         │    • state RETRYING → OPEN?         │
         │    • Safety timeout?                │
         │                                     │
         │  Updates g_cvcsm_state_{buy,sell}   │
         └─────────────────────────────────────┘
                          │
                          ▼
          ╔═══════════════════════════════════╗
          ║  Setup triggers run               ║
          ║  (BB_BREAKOUT, ORB, MOMENTUM_DUMP,║
          ║   FRACTIONAL_SELL, etc.)          ║
          ║                                   ║
          ║  Output: direction = "BUY"/"SELL" ║
          ║          setup_type = "..."       ║
          ╚═══════════════════════════════════╝
                          │
                          ▼
       ┌──────────────────────────────────────┐
       │   v2.7.93 anti-retest gate          │
       │   (BB_BREAKOUT only)                 │
       │                                      │
       │   BUY: (mid−bb_upper)/atr < 0.1? ───┼──► SKIP
       │   SELL: (bb_lower−mid)/atr < 0.1? ──┼──► bb_breakout_*_band
       └──────────────────────────────────────┘
                          │ pass
                          ▼
       ┌──────────────────────────────────────┐
       │   Layer 1: UMCG block check          │
       │                                      │
       │   pemcg_<dir>_count ≥ 5? ───────────┼──► SKIP pemcg_*_reversal_block
       └──────────────────────────────────────┘     direction = "", setup_type = ""
                          │ pass
                          ▼
       ┌──────────────────────────────────────┐
       │   Layer 2: CVCSM block check         │
       │                                      │
       │   cvcsm_state_<dir> != OPEN? ───────┼──► SKIP cvcsm_cooldown_block_*
       └──────────────────────────────────────┘     direction = "", setup_type = ""
                          │ pass
                          ▼
          ┌───────────────────────────────────┐
          │  Place order with setup_type +    │
          │  direction + sl + tp1 + tp2       │
          └───────────────────────────────────┘
                          │
   ┌──────────────────────┘
   │ ELSE (direction == "" because UMCG or CVCSM blocked, OR no setup fired)
   ▼
┌────────────────────────────────────────────────────────────┐
│   Layer 3: BB_EXHAUSTION_REVERSAL counter-trade evaluation │
│                                                            │
│   SELL counter (fires when BUY direction was trap):        │
│     pemcg_buy_count ≥ 4? ──┐                              │
│     RSI not oversold AND   │  AND                          │
│       close not near bb_l? │  AND                          │
│     m5_adx < 35?           │  AND                          │
│     prev_bar_range/atr<2?  │  AND  (all checks pass)       │
│     cvcsm_state_sell=OPEN? │  AND                          │
│     No existing SELL near? │  AND                          │
│     cooldown elapsed?      │                              │
│                            ▼                              │
│        FIRE BB_EXHAUSTION_REVERSAL_SELL                    │
│        (tier-based: HIGH if pemcg≥6, BASE otherwise)       │
│                                                            │
│   BUY counter: full mirror (PEMCG_SELL ≥ 4, RSI ≤ 35,etc.) │
└────────────────────────────────────────────────────────────┘
                          │
                          ▼
                     Next tick
```

---

## §5b ASCII — CVCSM state machine

```
                        ┌─────────────┐
              ┌────────►│    OPEN     │◄────────────┐
              │         │             │             │
              │         │ Trades fire │             │
              │         │ normally    │             │
              │         └──────┬──────┘             │
              │                │                    │
              │      SL fires  │                    │
              │   in this dir  │                    │
              │                ▼                    │
              │         ┌─────────────┐             │
              │         │  COOLDOWN   │             │
              │         │             │             │
              │         │ All entries │             │
              │         │ blocked     │             │
              │         └──────┬──────┘             │
              │                │                    │
              │     PEMCG < 2  │   max_cooldown_sec │
              │     for 1 bar  │   elapsed (1800s)  │
              │                ▼                    │
              │         ┌─────────────┐             │
              │         │  RETRYING   │             │
              │         │             │             │
              │         │ Counting    │             │
              │         │ clean bars  │             │
              │         └──────┬──────┘             │
              │                │                    │
              │  2 consecutive │  PEMCG ≥ 2         │
              │  clean bars    │  again (re-trapped)│
              │  (release)     │                    │
              └────────────────┘                    │
                                                    │
                          PEMCG ≥ 2 → back to COOLDOWN
```

---

## §6 The verbatim Q&A (preserved as canonical reference)

> **Operator** (2026-05-14): "so are you using any of the state machine and PEMCG so far? just a personal question — how are they related"

**Answer (paraphrased verbatim from the chat)**:

The architecture has **5 components organized as 3 layers + 1 composite + 2 side gates**.

### The composite (the SIGNAL)

PEMCG — Pre-Entry Market Condition Gate — is a **7-atom warning composite**, computed every M5 close. It's NOT a gate itself. It produces two integers:
- `g_pemcg_buy_warning_count` (0-7) — "how many BUY-trap atoms are firing right now"
- `g_pemcg_sell_warning_count` (0-7) — mirror

The 7 atoms (under current v2.7.94):
1. RSI extreme (BUY: ≥ 65, SELL: ≤ 35) — v2.7.88 widening
2. Weak candle body (< 0.5)
3. `m5_strong_bar == 0`
4. `m5_range_expanding == 0`
5. Close near BB band (absolute distance < 0.3 ATR) — v2.7.87 fix
6. ATR contracting (< 1.0× 5-bar avg)
7. MACD divergence

### The three layers that USE PEMCG

```
┌─ Layer 1: UMCG (Universal Market Condition Gate) ─────────────────────┐
│  Stateless. Fires at EVERY setup trigger (any direction, any setup). │
│  IF pemcg_count ≥ 5/7 → BLOCK with pemcg_*_reversal_block             │
│  Status this run: 56,786 BUY blocks + 323 SELL blocks ← ACTIVELY WORKING│
└────────────────────────────────────────────────────────────────────────┘

┌─ Layer 2: CVCSM (Conditional Cooldown State Machine) ─────────────────┐
│  Stateful per direction. OPEN ↔ COOLDOWN ↔ RETRYING.                 │
│  TRIGGER → COOLDOWN: SL fires in that direction                       │
│  COOLDOWN → RETRYING: pemcg_count < 2 for 1 bar                       │
│  RETRYING → OPEN: pemcg_count < 2 for 2 consecutive bars              │
│  IF state != OPEN → BLOCK with cvcsm_cooldown_block_*                 │
│  Status this run: 0 fires (no SL has happened, machine never left OPEN)│
└────────────────────────────────────────────────────────────────────────┘

┌─ Layer 3: BB_EXHAUSTION_REVERSAL counter-trade ───────────────────────┐
│  Stateless. Fires when:                                                │
│   - direction == "" (no setup OR setup just blocked by UMCG)           │
│   - pemcg_count ≥ 4 (high reversal confidence)                         │
│   - opposite direction not in OWN trap (v2.7.90 directional gate)      │
│   - M5 ADX < 35 (v2.7.92 — not in strong trend)                        │
│   - prev_bar_range/atr < 2.0 (v2.7.94 — not after capitulation spike)  │
│   - CVCSM opposite state == OPEN                                       │
│   - cooldown_sec=0 (v2.7.91 — re-fire allowed)                         │
│   - no existing opposite-direction position within 1.5×ATR             │
│  Status this run: 0 fires (UMCG hasn't blocked a BUY YET at right tick)│
└────────────────────────────────────────────────────────────────────────┘
```

### The two NEW gates v2.7.93 + v2.7.94 sit OUTSIDE the PEMCG stack

These don't use PEMCG at all — they're separate setup-specific filters:

- **v2.7.93** (`bb_breakout_buy_below_band`): pure price-vs-BB geometry check at BB_BREAKOUT entry. Independent of PEMCG.
- **v2.7.94** (WRB gate on BB_EXHAUSTION_REVERSAL): pure prev-bar-range/ATR check. Adds to Layer 3 conditions but doesn't use PEMCG.

### Why CVCSM hasn't fired yet in this run

CVCSM only enters COOLDOWN when an SL fires. **Run 9 has zero losses so far** → SL has never triggered → all CVCSM states are still OPEN → no `cvcsm_cooldown_block_*` events. **That's the design** — the better the upstream gates work, the less the cooldown state machine needs to do.

### Short answer

- **PEMCG**: a computed value (number of warnings 0-7) — the SIGNAL
- **UMCG (Layer 1)**: uses PEMCG to BLOCK setups at trigger
- **CVCSM (Layer 2)**: uses PEMCG to determine when to release from cooldown
- **Layer 3 reversal**: uses PEMCG ≥ 4 to fire counter-trade
- **v2.7.93/94**: independent of PEMCG — they're setup-specific quality checks

They're related because **all three layers consume the same PEMCG composite as their decision signal**, just for different purposes (block / cooldown / counter-trade). PEMCG is the input; the layers are different consumers.

---

## §7 Live evidence — current Run activity

**Last updated**: 2026-05-14 (Run 9, FORGE v2.7.94, sim Apr 1 19:44)

| Component | Activity in current run |
|---|---|
| PEMCG composite | Computed ~165,901× this run (every signal evaluation, every direction) |
| **Layer 1 UMCG BUY** | **83,909 blocks** — actively working |
| **Layer 1 UMCG SELL** | **3,538 blocks** |
| Layer 2 CVCSM BUY | 0 fires (no SL yet) |
| Layer 2 CVCSM SELL | 0 fires |
| Layer 3 BB_EXHAUSTION_REVERSAL | 0 TAKEN (counter-trade hasn't aligned all conditions yet) |
| **v2.7.93 `bb_breakout_buy_below_band`** | **4,234 blocks** ← G5006-class retest BUYs blocked |
| v2.7.94 WRB gate | 0 fires (BB_EXHAUSTION_REVERSAL hasn't triggered) |

This section is auto-refreshed whenever the forge-monitor /resume tick lands.

---

## §8 Update protocol

This document MUST be updated when:

1. **A PEMCG atom changes** (new atom added, atom logic changed, threshold tuned)
   → Update §2.1 atom table + add §11 changelog entry
2. **A new consumer of PEMCG ships** (new layer, new gate using `g_pemcg_*_warning_count`)
   → Update §3 with new layer + ASCII diagram in §5
3. **CVCSM state machine changes** (new state, trigger, release condition)
   → Update §3.2 + §5b state diagram
4. **Layer 3 conditions change** (new gate added/removed)
   → Update §3.3 conditions + §5 single-tick flow
5. **Side gate adds/removes PEMCG dependency**
   → Move between §3 (consumer) and §4 (independent)
6. **Any v2.7.X ship touches the PEMCG/UMCG/CVCSM/Layer 3 stack**
   → Add §11 changelog one-liner with what changed
7. **Live evidence section** (§7) — refresh every forge-monitor tick where these numbers move

---

## §9 References

### Internal docs
- `docs/FORGE_CASE_STUDY_G5006_INFLECTION_POINT.md` — origin case study (G5006 -$1,793 loss that motivated PEMCG + UMCG)
- `docs/FORGE_DECISION_STACK.md` — 5-layer decision architecture
- `docs/FORGE_NAMING_CONVENTIONS.md` — knob naming policy
- `docs/FORGE_CORE_LOGIC_DESIGN.md` — v2.7.95-2.7.102 multi-leg cool-period redesign tracker (where DLV/DLS were defined)
- `docs/FORGE_v2.7.95-2.7.102_ROLLOUT_PLAN.md` — phase-by-phase activation guide
- `docs/FORGE_TRADE_FLOW_BUY_SELL.md` — BUY + SELL full-lifecycle ASCII walkthrough

### Code locations
- `ea/FORGE.mq5:6621-6663` — PEMCG computation
- `ea/FORGE.mq5:12362-12557` — Layer 1/2/3 enforcement (UMCG + CVCSM at chokepoint, plus v2.7.97 DirLock check)
- `ea/FORGE.mq5:10781-10798` + `:11156-11173` — v2.7.93 anti-retest gates
- `ea/FORGE.mq5:~14213` — `EvaluateDirectionLock()` (DLV producer, v2.7.97)
- `ea/FORGE.mq5:~14282` — `CancelPendingOnStructureFlip()` (DLV consumer #1, stack-based, v2.7.101; Gap 1 in v2.7.103 extends slot range to 0+1 behind `structure_cancel_includes_breakout_l1l2`)
- `ea/FORGE.mq5` (immediately below) — `CancelStrayPendingsOnStructureFlip()` (DLV consumer #2, OrdersTotal walker for core-range pendings, v2.7.103 Gap 2)
- `ea/FORGE.mq5:~14310` — `UpdateDirLockState()` (DLS transitions, v2.7.97)
- `config/scalper_config.json` — runtime knob values
- `.env` — operator overrides

### Industry articles used in the v2.7.95-2.7.102 redesign (cited verbatim where applicable)

The new acronyms (DLV / DLS) and the layered re-evaluation pattern were informed by these external sources surfaced during WebSearch on 2026-05-14:

| Topic | Source |
|---|---|
| ICT Market Structure Shift (MSS) — body-close validation pattern feeding **Trigger 1** of `EvaluateDirectionLock` | [tradethepool: Market Structure Shift](https://tradethepool.com/technical-skill/ict-market-structure-shift/) |
| ICT validation by ATR — "checks whether price closes beyond the deviation range defined by a 17-period ATR" → calibration of `dirlock_struct_break_atr_mult` | [LuxAlgo: ICT Anchored Market Structures with Validation](https://www.luxalgo.com/library/indicator/ict-anchored-market-structures-with-validation/) |
| Post-SL re-entry rule — "previous closed candle must make a new higher high (BUY) / lower low (SELL) compared to all candles since original signal" → the *fresh signal* requirement after DLS DISCARDED → IDLE | [Triple MA EA Strategy (Dec 30 2025)](https://www.mql5.com/en/blogs/post/766574) |
| MT5 hedge mode + magic-number convention — "each order can have different magic numbers... hedging system opens new position per deal" → DLS state per-direction independence + DLV per-group | [MQL5 forum 446630](https://www.mql5.com/en/forum/446630), [forum 431285](https://www.mql5.com/en/forum/431285) |
| Pending order cancel pattern via OnTradeTransaction / per-cycle status check → `CancelPendingOnStructureFlip()` design | [MQL5 docs OnTradeTransaction](https://www.mql5.com/en/docs/event_handlers/ontradetransaction), [forum 388433](https://www.mql5.com/en/forum/388433) |
| ICT MSS body-close invalidation of resting limit-order entries → both v2.7.103 cancel-sweep extensions (Gap 1 + Gap 2) | [tradethepool ICT MSS Guide](https://tradethepool.com/technical-skill/ict-market-structure-shift/), [LuxAlgo MSS in ICT Trading](https://www.luxalgo.com/blog/market-structure-shifts-mss-in-ict-trading/), [innercircletrader.net ICT MSS Complete Guide](https://innercircletrader.net/tutorials/ict-market-structure-shift/), [equiti MSS vs BOS](https://www.equiti.com/sc-en/news/trading-ideas/mss-vs-bos-the-ultimate-guide-to-mastering-market-structure/) |
| MT5 magic-range filter pattern (mirror of `CancelPendingOnDailyFlip`) used by v2.7.103 `CancelStrayPendingsOnStructureFlip` | [MQL5 forum 377826 — iterate OrdersTotal()-1 → 0](https://www.mql5.com/en/forum/377826) |
| Adaptive risk management with context-aware stop placement and zone-flip detection | [MQL5 Article 21759: Adaptive Risk Management for Liquidity Strategies](https://www.mql5.com/en/articles/21759) |
| Trade-discipline state persistence ("global variables and file operations to persist risk states across restarts") | [MQL5 Article 20587: Automating Trade Discipline with Risk Enforcement EA](https://www.mql5.com/en/articles/20587) |
| Pyramid spacing — "0.5×ATR, max 4 pyramid positions; each position independent" → `batch_max_legs` cap + spacing knob | [MSX AI SuperTrend v3.90 (May 2026)](https://www.mql5.com/en/blogs/post/769821), [Pyramid MT5 EA](https://www.mql5.com/en/market/product/103169) |
| TP tier semantics — Triple-Scale Method "TP1 50% / TP2 25% / TP3 25%" → operator's spec, validated industry-canonical | [eazypips: What Are TP1, TP2, and TP3](https://www.eazypips.com/what-are-tp1-tp2-and-tp3-and-how-to-trade-them/) |
| XAUUSD pip convention — confirmed broker convention (1 pip = $0.10, 10 points on 2-digit) | [defcofx XAUUSD Pips and Lot Size](https://www.defcofx.com/xauusd-pips-and-lot-size/), [tradersunion XAUUSD pip guide](https://tradersunion.com/trading-glossary/what-is-xauusd/how-to-calculate-pips/) |
| XAUUSD scalping ATR-based SL + trailing stop on first +10 pips | [FXNX XAUUSD Scalping](https://fxnx.com/en/blog/master-xauusd-scalping-for-quick-gold-gains), [The Best way to Scalp Gold XAUUSD M1](https://www.mql5.com/en/blogs/post/764883) |

---

## §10 Operational tie-in (forge-monitor)

When `/forge-monitor` runs:
1. **Always count** `gate_reason IN ('pemcg_buy_reversal_block', 'pemcg_sell_reversal_block', 'cvcsm_cooldown_block_buy', 'cvcsm_cooldown_block_sell', 'bb_breakout_buy_below_band', 'bb_breakout_sell_above_band')` and report in tick summary.
2. **Update §7** if any count moves significantly (>500 since last tick).
3. **Flag in tick output** when CVCSM transitions OPEN → COOLDOWN (a fresh SL just happened) or RETRYING → OPEN (recovery).

---

## §11 Changelog

- 2026-05-14 — **doc created** after operator question "are you using any of the state machine and PEMCG so far?" surfaced the need for a single authoritative reference. Includes verbatim Q&A in §6 (canonical).
- 2026-05-14 — v2.7.86 calibration recorded: UMCG threshold 3 → 5 (§3.1)
- 2026-05-14 — v2.7.87 recorded: PEMCG A5 absolute distance fix (§2.1)
- 2026-05-14 — v2.7.88 recorded: A1 RSI thresholds 70→65 / 30→35 (§2.1)
- 2026-05-14 — v2.7.89/90/91/92/94 recorded: Layer 3 enhancements (§3.3)
- 2026-05-14 — v2.7.93 recorded as independent side gate (§4)
- 2026-05-14 — v2.7.103 recorded: DLV consumers now plural — stack-based `CancelPendingOnStructureFlip` (slot-range knob added) + new walker-based `CancelStrayPendingsOnStructureFlip` (core-range pendings). Both default-OFF. ICT MSS sources added to §9 references.
- 2026-05-14 — v2.7.105 recorded: **§3.4 Layer 4 — DTC (Day-Type Classifier) added** as a fourth consumer of the PEMCG signal AND a new outermost gate. Solves 12× SELL-block asymmetry observed in Run 36 v2.7.102 (63,716 PEMCG_SELL blocks during a 140-pt bear move). Triad: VWAP-distance + M15 ADX + H1 DI dominance — deliberately excludes h1_trend_strength (proven lagging during fresh reversals). Two new gate codes: `bear_day_buy_block`, `bull_day_sell_block`. Industry citations: volity.io (ADX gates RSI continuation/reversal), mql5.com/blogs/767595 (VWAP intraday sentiment), alchemymarkets hidden-divergence (continuation pattern). All knobs default-OFF behind `FORGE_COMPOSITE_DTC_ENABLED`.
- 2026-05-14 — v2.7.107 recorded: **§3.5 DTC 5-state classifier added** (layered on §3.4). Adds H4 trend agreement as a fourth axis, producing 5 states: BULL_TREND_ALIGNED, BEAR_TREND_ALIGNED, COUNTER_TREND_BULL, COUNTER_TREND_BEAR, NEUTRAL. Catches the G5021 −$498.60 case (counter-H4 BUY during corrective bounce inside bear H4 macro) that v2.7.105's binary intraday detector could not catch because M15 ADX was 22.2 (just below threshold). Counter-trend states DO NOT trigger PEMCG modifier (asymmetric design — PEMCG stays strict on counter-trend to filter trap entries). Two new gate codes: `counter_bull_day_buy_block`, `counter_bear_day_sell_block`. ICT framework alignment: "Trade only in direction of H4 bias unless confirmed MSS; OTE re-entries at H4 demand are canonical" (tradeciety multi-TF). Operator decision: skipped v2.7.106 binary-H4 intermediate; went direct to v2.7.107 5-state per "Option 2 wins". Backup: backups/v2.7.107/FORGE.mq5.pre-5state-dtc.
- 2026-05-14 — **§1A added** — acronym dictionary (PEMCG / UMCG / CVCSM + new DLV / DLS introduced in v2.7.97), layer relationship diagram, and explicit grouping of *indicators → thresholds → atoms → counts → layer verdicts*. Operator request after asking "add meaning of PEMCG, UMCG and CVCSM how they all related together how indicators values, thresholds, bool are groups". DLV (Direction Lock Verdict) + DLS (Direction Lock State) are new in v2.7.97 — naming follows the existing 4-5 letter pattern + FORGE_NAMING_CONVENTIONS §4.7.
- 2026-05-14 — **§9 References expanded** — added 12 industry article citations used during the v2.7.95-2.7.102 redesign (ICT MSS, LuxAlgo validation, Triple MA EA re-entry rule, MQL5 hedge-mode docs, OnTradeTransaction patterns, MQL5 Articles 21759 + 20587, pyramid systems, Triple-Scale TP method, XAUUSD pip convention sources). These informed Sets 1/4/6/7/8 design.
- 2026-05-14 — Live evidence §7 first populated: Run 9 v2.7.94, sim Apr 1 19:44, 4,234 v2.7.93 blocks confirming G5006 retest trap caught
