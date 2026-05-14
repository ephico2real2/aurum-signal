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

## §2 The composite — PEMCG (Pre-Entry Market Condition Gate)

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

- `docs/FORGE_CASE_STUDY_G5006_INFLECTION_POINT.md` — origin case study (G5006 -$1,793 loss that motivated PEMCG + UMCG)
- `docs/FORGE_DECISION_STACK.md` — 5-layer decision architecture
- `docs/FORGE_NAMING_CONVENTIONS.md` — knob naming policy
- `ea/FORGE.mq5:6621-6663` — PEMCG computation
- `ea/FORGE.mq5:12362-12557` — Layer 1/2/3 enforcement
- `ea/FORGE.mq5:10781-10798` + `:11156-11173` — v2.7.93 anti-retest gates
- `config/scalper_config.json` — runtime knob values
- `.env` — operator overrides

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
- 2026-05-14 — Live evidence §7 first populated: Run 9 v2.7.94, sim Apr 1 19:44, 4,234 v2.7.93 blocks confirming G5006 retest trap caught
