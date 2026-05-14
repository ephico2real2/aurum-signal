# ICT Structure Score (ISS) — Canonical Standard

**Status**: Canonical standard for FORGE entry-score evaluation
**First specified**: 2026-05-14 (v2.7.112 scaffolding)
**Implementation phases**: v2.7.112 scaffolding → v2.7.113 swing tracker → v2.7.114 ChoCH → v2.7.115 FVG → v2.7.116+ gate activation
**Cross-references**:
- `docs/research/ICT_KILLZONES.md` — adjacent ICT research (killzone integration)
- `.claude/skills/forge-monitor/SKILL.md` — monitor consumes `iss_*` columns

---

## §1. Purpose

ISS is **FORGE's canonical entry-score framework**. It produces a 0–10 boolean-weighted score per setup-trigger fire, derived from three ICT-canonical structure atoms. The score quantifies whether a structural setup is actually present (MSS), how cleanly the entry timing is set (FVG retracement zone), and whether the regime context supports the trade (ChoCH confluence).

ISS sits as the final scoring layer **after** the existing gate stack (UMCG, CVCSM, DTC, DLV/DLS). The gates above ISS filter by indicator-composite criteria; ISS adds discrimination on the **price-action structure axis** — a signal independent of any indicator-derived composite, because it operates on swing pivots and 3-candle imbalances rather than RSI/ADX/MACD ranges.

The score:
- **Defaults OFF** — atoms log as 0 until v2.7.113-115 wires real detection
- **Logs always** — populated as 0/1/score on every TAKEN signal row
- **Gates optionally** — `iss_block_below_threshold=1` activates the score as a hard SKIP gate
- **Uses encoded thresholds, not calibrated** — ≥8 high-conviction / ≥5 standard / <5 SKIP comes directly from ICT entry methodology (MSS mandatory, FVG+ChoCH = full conviction)

---

## §2. FORGE entry-gating architecture (where ISS fits)

ISS is **Layer 5** — the final score evaluated after all upstream gates pass. The full stack:

| Layer | Component | Atom domain | Role | Decision shape |
|---|---|---|---|---|
| 1 | **UMCG** | PEMCG 7-atom composite (bar-quality + indicator extremes) | Universal market-condition gate — blocks inducement-style entries | Stateless filter per BUY/SELL |
| 2 | **CVCSM** | Smart cooldown state machine | SL-only-triggered cooldown with bidirectional retry | Per-direction state machine |
| 3 | **DTC** | 5-state day-type classifier (BULL_TREND_ALIGNED / BEAR_TREND_ALIGNED / NEUTRAL / COUNTER_TREND_BULL / COUNTER_TREND_BEAR) | Day-type bias filter with exempt-overrides | Stateless filter + exempt-list overrides |
| 4 | **DLV → DLS** | Direction lock evaluator + state machine | No-auto-flip direction discipline | Per-direction state |
| 5 | **ISS** (this doc) | MSS + ChoCH + FVG structure atoms | Entry-score — discriminates by price-action structure | 0-10 weighted score + optional gate |

Each layer is **independent**: a signal must pass every preceding layer before reaching ISS. ISS itself reports a score and (when gate-mode enabled) blocks below threshold; otherwise it is purely instrumented.

---

## §3. The ICT framework (full toolkit reference)

This section documents the eight ICT concepts that inform FORGE's structure-based reasoning. Three of them feed the ISS score directly (MSS, ChoCH, FVG); the remaining five inform adjacent gates or are already encoded elsewhere in the FORGE stack.

### 3.1 Market Structure Shift (MSS)

**Definition**: A confirmed structural break — price closes **past a recent swing high (BUY) or swing low (SELL)** with a full-bodied candle, not just a wick. Distinguishes genuine continuation/reversal from liquidity grabs.

**Bullish MSS**: HL-HH-HL sequence breaks the most recent swing high by a full-body close.
**Bearish MSS**: HH-LH-HH sequence breaks the most recent swing low by a full-body close.

**Validation rule**: `(close - swing) ≥ 0.30 × ATR` enforces displacement; wick-only crossings are rejected as liquidity grabs.

### 3.2 Change of Character (ChoCH)

**Definition**: First sign that an established trend is breaking down. Within an existing trending sequence, price closes **past the most recent counter-trend swing pivot**, contradicting the continuation pattern.

| Trend | ChoCH signal |
|---|---|
| Uptrend (HH-HL-HH-HL) | Price closes BELOW the most recent HL |
| Downtrend (LH-LL-LH-LL) | Price closes ABOVE the most recent LH |

**Earlier and weaker than MSS** — ChoCH warns of trend exhaustion; MSS confirms the new direction. ChoCH **in the same direction as the trade** is supportive (regime turning into our direction). ChoCH **against the trade** is a kill signal (the trend we're entering into is dying).

### 3.3 Fair Value Gap (FVG)

**Definition**: A 3-candle imbalance pattern. Middle candle displaces price impulsively; candles 1 and 3 leave an unfilled range that institutions tend to retrace into for "fair value" entries.

```
Bullish FVG:                    Bearish FVG:
    ┃ candle 3 low                  ┃ candle 1 low
    ┃                               ┃
GAP ┃                          GAP  ┃
    ┃                               ┃
    ┃ candle 1 high                 ┃ candle 3 high
```

Predicates:
- **Bullish FVG**: `m5_high[2] < m5_low[0]` (gap between candle-2 high and candle-0 low)
- **Bearish FVG**: `m5_low[2] > m5_high[0]` (gap between candle-2 low and candle-0 high)

**FVG lifecycle**:
- **Created** at 3-candle imbalance detection on M5 close
- **Active** until age > `iss_fvg_max_age_bars` (default 12) OR fill% ≥ `iss_fvg_max_fill_pct` (default 50%) OR opposite MSS invalidates the regime
- **Entry trigger**: price retraces INTO an active FVG aligned with trade direction

### 3.4 Order Block (OB)

**Definition**: The **last opposite-direction candle** before a strong directional move. Institutions accumulated/distributed here; price often revisits and bounces.

| Type | Marked by | Retest behavior |
|---|---|---|
| Bullish OB | Last bearish candle before strong rally | Acts as support on retest |
| Bearish OB | Last bullish candle before strong drop | Acts as resistance on retest |
| Breaker block | Failed OB on opposite side | Polarity flip — old support → new resistance |

**FORGE status**: Order-block prices already computed by LENS (H4 swings) and consumed by FORGE via `ob_zones.json` → `g_ob_zones_hi[6]` globals. The atoms exist but are not currently wired into setup-gating logic.

### 3.5 Premium / Discount arrays

**Definition**: Splits the last swing range into halves; institutions buy at discount (lower 50%) and sell at premium (upper 50%).

| Zone | Range | Trade bias |
|---|---|---|
| Premium | Upper 50% of swing | SELL zone |
| Equilibrium | 50% line | Neutral — await direction |
| Discount | Lower 50% of swing | BUY zone |

**FORGE status**: `fib_50` is computed and logged in SIGNALS. Atom available but not consumed by setup gating.

### 3.6 Balanced Price Range (BPR)

**Definition**: The overlap zone where a bullish FVG and a bearish FVG intersect on the chart. Highest-confluence entry — institutional buying AND selling pressure converged.

**FORGE status**: Derived from FVG detector; depends on FVG atom (v2.7.115).

### 3.7 Buy-Side / Sell-Side Liquidity (BSL/SSL)

**Definition**: Where retail stop orders cluster.

| Liquidity zone | Location | Mechanism |
|---|---|---|
| BSL (buy-side) | Stops ABOVE prior swing highs | Shorts get stopped out; buys trigger |
| SSL (sell-side) | Stops BELOW prior swing lows | Longs get stopped out; sells trigger |

Institutions sweep BSL/SSL **before** the real MSS move, providing the liquidity for their fill.

**FORGE status**: `day_high` / `day_low` (logged in SIGNALS) approximate intraday BSL/SSL. Distance metrics `dist_to_BSL = day_high - price` and `dist_to_SSL = price - day_low` are trivially derivable.

### 3.8 Inducement / liquidity grab

**Definition**: The deceptive move before the real one. Smart money pushes price just past a swing level → triggers retail stops + counter-entries → reverses hard. Retail traders provide liquidity for the actual institutional move.

**FORGE status**: This is precisely what **PEMCG** (Layer 1 atom composite consumed by UMCG) detects. The 7-atom PEMCG composite checks for inducement signatures: high RSI, weak body, BB-proximity without breakout, negative MACD at extremes, long upper/lower wick rejection. Battle-tested in production with 59K+ blocks recorded in Run #2 alone.

### 3.9 Power of Three (PO3)

**Definition**: Three phases of a daily institutional candle:

| Phase | Window | Behavior |
|---|---|---|
| Accumulation | Asia session | Narrow range, institutions building positions |
| Manipulation | London open | Fake move against true direction, sweeps overnight stops |
| Distribution | NY session | True intended direction — the actual profitable move |

**FORGE status**: Sessions and killzones are already encoded (`session = 'ASIAN'/'LONDON'/'NY'`, `g_regime.killzone = LONDON_OPEN/NY_OPEN`). The conceptual machinery to distinguish manipulation from distribution (Asia-range tracking + BSL/SSL sweep detection) is a future addition; the time-window labels exist.

---

## §4. Mapping ICT framework → FORGE atoms

The full ICT toolkit maps onto existing FORGE infrastructure as follows. Bold entries are **fed directly into the ISS score**; non-bold are already-active gates or untapped data.

| ICT concept | FORGE component | Status | Role in FORGE today |
|---|---|---|---|
| **MSS** | Swing-pivot tracker (v2.7.113) | NEW | ISS atom — primary score weight 5 |
| **ChoCH** | Swing-pivot tracker (v2.7.114) | NEW | ISS atom — supporting weight 2 + hard-gate against |
| **FVG** | 3-candle imbalance detector (v2.7.115) | NEW | ISS atom — entry precision weight 3 |
| Order Block | `g_ob_zones_hi[6]` via `ob_zones.json` | EXISTING | Not consumed by setup logic yet (future enhancement candidate) |
| Premium/Discount | `fib_50` in SIGNALS + market_data.json | EXISTING | Available as atom, not consumed by setup gating |
| Balanced Price Range | Derived from FVG detector | NEW (v2.7.115+) | Future BPR atom once FVG ships |
| BSL/SSL | `day_high`, `day_low`, `m5_high_1/low_1` | EXISTING | Distance metrics derivable from logged data |
| Inducement | **PEMCG → UMCG** | EXISTING | Layer 1 gate — proven 59K+ blocks in Run #2 |
| Power of Three | `session`, `g_regime.killzone`, `minutes_into_kz` | EXISTING (v2.7.36) | Session/killzone labels present; sweep-detection logic future |
| Structural SL | (current FORGE uses ATR-mult SL) | GAP | Future: SL below pre-MSS swing low (BUY) / above swing high (SELL) |
| Structural TP | (current FORGE uses ATR-mult TP) | GAP | Future: TP at next liquidity pool / prior swing extreme |

The ISS score consumes the three NEW atoms (MSS, ChoCH, FVG). The other ICT concepts are either already active elsewhere in the FORGE gate stack (Inducement via PEMCG; killzone-aware lot sizing via v2.7.36) or available as data ready to wire into future atoms.

---

## §5. The three ISS score atoms

### 5.1 `iss_mss` — Market Structure Shift

**Weight**: 5 (dominant — structural confirmation is mandatory for any entry)

**Predicates**:
```mql5
// BUY:
iss_mss = (m5_close[0] > prior_swing_high
         && m5_close[0] - max(m5_open[0], prior_swing_high) >= 0.30 * m5_atr_0
         && m5_strong_bar == 1)

// SELL:
iss_mss = (m5_close[0] < prior_swing_low
         && min(m5_open[0], prior_swing_low) - m5_close[0] >= 0.30 * m5_atr_0
         && m5_strong_bar == 1)
```

The `(close - swing) ≥ 0.30 × ATR` threshold rejects wick-only crossings (liquidity grabs). The `m5_strong_bar == 1` predicate is the existing FORGE bar-quality atom — already logged.

**Required from FORGE**: swing-pivot tracker (spec in §14).

### 5.2 `iss_choch_support` and `iss_choch_against` — Change of Character

**Weight (support)**: 2 (confluence boost when present)
**Hard gate (against)**: SKIP with `gate_reason=iss_choch_against_block` (NOT scored)

**For a BUY setup**:
```mql5
iss_choch_support = (downtrend was active for >= 3 prior M5 swings
                  && current m5_close > most_recent_lower_high
                  → early reversal signal favoring our BUY)

iss_choch_against = (uptrend was active for >= 3 prior M5 swings
                  && current m5_close < most_recent_higher_low
                  → trend dying against our BUY)
```

**For SELL**: mirror — `choch_support` = uptrend breaking down via HL violation; `choch_against` = downtrend breaking up via LH violation.

**Architectural role**:
- `iss_choch_support` adds +2 to the score (confluence)
- `iss_choch_against` is **NOT** subtracted from the score — it is a hard gate. If present, SKIP regardless of MSS or FVG. A reversal-warning against trade direction is an architectural NO, not a numeric weight.

**Required from FORGE**: same swing-pivot tracker as MSS — produces the swing high/low sequence ChoCH evaluates.

### 5.3 `iss_fvg` — Fair Value Gap retracement entry

**Weight**: 3 (entry precision — defines the high-conviction tier)

**Predicate**:
```mql5
// BUY (price retracing into bullish FVG):
iss_fvg = (active_bullish_fvg_exists
         && fvg_low <= price <= fvg_high
         && fvg_age_bars <= iss_fvg_max_age_bars     // default 12 M5 bars
         && fvg_fill_pct <= iss_fvg_max_fill_pct)    // default 0.50

// SELL: mirror with active_bearish_fvg
```

**FVG state lifecycle** (managed by tracker, spec in §15):
- **Created**: 3-candle imbalance pattern detected on M5 close → push to active list
- **Active**: age ≤ max_age, fill_pct < threshold, no opposite-direction MSS invalidating regime
- **Mitigated** (consumed): price retraced ≥ `iss_fvg_max_fill_pct` (default 50%) into the gap
- **Stale**: age > `iss_fvg_max_age_bars`
- **Invalidated**: opposite-direction MSS flips the regime

**Required from FORGE**: 3-candle imbalance detector + active-FVG state tracker (spec in §15).

---

## §6. Score formula

```
ISS_score = 
    (iss_mss             ? iss_weight_mss            : 0)   // default 5
  + (iss_fvg             ? iss_weight_fvg            : 0)   // default 3
  + (iss_choch_support   ? iss_weight_choch_support  : 0)   // default 2

Range: 0 to 10
```

`iss_choch_against` is NOT in this arithmetic — it is evaluated as a separate hard gate before the score is consulted.

---

## §7. Hard gates (outside the score)

### 7.1 `iss_choch_against_block`

```
if (iss_block_below_threshold && iss_choch_against)
   → SKIP with gate_reason = "iss_choch_against_block"
```

ChoCH against trade direction = architectural NO. No amount of MSS + FVG confluence makes the entry valid if structural reversal is signaling the other way.

### 7.2 `iss_below_threshold`

```
if (iss_block_below_threshold
    && !iss_choch_against
    && iss_score < iss_min_threshold)
   → SKIP with gate_reason = "iss_below_threshold"
```

Default `iss_min_threshold = 5` (exactly the MSS weight — threshold means "MSS is mandatory").

Both gates are evaluated only when `iss_block_below_threshold = 1`. With the default `0`, ISS is instrumentation-only and never skips a setup based on its own score.

---

## §8. Decision tiers

The score maps to three ICT-canonical conviction tiers:

| ISS score | Tier | Action | Conditions present |
|---|---|---|---|
| **≥ 8** | **High-conviction** | Full position, TP1+TP2 stage | MSS + FVG retracement entry + supporting ChoCH (all three) |
| **5–7** | **Standard** | Reduced size, TP1 priority | MSS alone, or MSS + one confluence atom |
| **< 5** | **SKIP** | `iss_below_threshold` (when gate enabled) | No structural confirmation (MSS absent) |

These tiers are not calibrated against backtest curves — they directly encode the ICT entry hierarchy: MSS mandatory, FVG defines high-conviction, ChoCH support is the confluence boost.

---

## §9. Mirror direction (BUY/SELL symmetry)

Every atom ships with explicit BUY and SELL evaluations:

```mql5
For BUY:
  iss_mss           = (m5_close[0] > prior_swing_high && full-body && m5_strong_bar)
  iss_fvg           = (price ∈ active bullish FVG, age < 12, fill < 50%)
  iss_choch_support = (recent downtrend broken via HL/LH violation → BULL reversal confirmed)
  iss_choch_against = (recent uptrend broken via HL violation → bull-exhaustion warning)

For SELL: mirror with prior_swing_low, bearish FVG, uptrend-violation patterns.
```

The mirror is enforced architecturally — no atom has BUY-only evaluation; SELL evaluation must be present and tested before any version ships.

---

## §10. Threshold rationale

**Why 5 and 8 specifically**:

| Threshold | Derivation | Meaning |
|---|---|---|
| **5** | Exactly the MSS weight | "MSS is mandatory" — anything ≥5 has MSS, anything <5 doesn't |
| **8** | MSS (5) + FVG (3) | Minimum score that includes the FVG retracement entry; defines high-conviction tier where ICT teaches full-position sizing |

These come from ICT methodology, not backtest tuning. Adjusting the weights re-derives the thresholds automatically (operator could tune `iss_weight_mss=4, iss_weight_fvg=4`; thresholds 4/8 follow the same logic).

This gives a **meaningful default-ON gate from day one of v2.7.116** — no calibration phase required, no statistical pipeline needed before activation.

---

## §11. Schema specification

### 11.1 SIGNALS table — 5 new columns (v2.7.112)

```sql
ALTER TABLE SIGNALS ADD COLUMN iss_score INTEGER DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN iss_mss INTEGER DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN iss_fvg INTEGER DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN iss_choch_support INTEGER DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN iss_choch_against INTEGER DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_sig_iss_score ON SIGNALS(iss_score);
```

### 11.2 Column meanings

| Column | Type | Range | Meaning |
|---|---|---|---|
| `iss_score` | INTEGER | 0–10 | Weighted-boolean total |
| `iss_mss` | INTEGER | 0 or 5 | Weight-multiplied MSS predicate result |
| `iss_fvg` | INTEGER | 0 or 3 | Weight-multiplied FVG predicate result |
| `iss_choch_support` | INTEGER | 0 or 2 | Weight-multiplied ChoCH-support predicate |
| `iss_choch_against` | INTEGER | 0 or 1 | Boolean atom only (NOT weighted, NOT scored) — drives hard gate |

### 11.3 Scribe mirror

`python/data/aurum_tester.db` `forge_signals` table mirrors the SIGNALS schema. The `scribe.py::sync_forge_journal` INSERT placeholder count must include the 5 ISS columns.

---

## §12. Knob surface

### 12.1 Struct fields (`ScalperConfig` in ea/FORGE.mq5)

```mql5
bool   iss_enabled;                 // default false — master flag
int    iss_min_threshold;           // default 5  (= MSS-mandatory bar)
bool   iss_block_below_threshold;   // default false — gate-mode toggle
int    iss_weight_mss;              // default 5
int    iss_weight_fvg;              // default 3
int    iss_weight_choch_support;    // default 2
int    iss_fvg_max_age_bars;        // default 12 (M5 bars)
double iss_fvg_max_fill_pct;        // default 0.50
```

### 12.2 Env var → JSON mappings (`scripts/sync_scalper_config_from_env.py`)

```python
"FORGE_COMPOSITE_ISS_ENABLED":         ("safety", "iss_enabled",               "bool01", None, None),
"FORGE_GATE_ISS_MIN_THRESHOLD":        ("safety", "iss_min_threshold",         "int",    0,    10),
"FORGE_GATE_ISS_BLOCK_BELOW_THRESHOLD":("safety", "iss_block_below_threshold", "bool01", None, None),
"FORGE_GATE_ISS_WEIGHT_MSS":           ("safety", "iss_weight_mss",            "int",    0,    10),
"FORGE_GATE_ISS_WEIGHT_FVG":           ("safety", "iss_weight_fvg",            "int",    0,    10),
"FORGE_GATE_ISS_WEIGHT_CHOCH_SUPPORT": ("safety", "iss_weight_choch_support",  "int",    0,    10),
"FORGE_TIMING_ISS_FVG_MAX_AGE_BARS":   ("safety", "iss_fvg_max_age_bars",      "int",    1,    60),
"FORGE_GATE_ISS_FVG_MAX_FILL_PCT":     ("safety", "iss_fvg_max_fill_pct",      "float",  0.0,  1.0),
```

### 12.3 Defaults (`config/scalper_config.defaults.json`, `safety` section)

```json
"iss_enabled": 0,
"iss_min_threshold": 5,
"iss_block_below_threshold": 0,
"iss_weight_mss": 5,
"iss_weight_fvg": 3,
"iss_weight_choch_support": 2,
"iss_fvg_max_age_bars": 12,
"iss_fvg_max_fill_pct": 0.5
```

---

## §13. Implementation roadmap

| Version | Scope | Trigger to ship |
|---|---|---|
| **v2.7.112** | Design doc + EA scaffolding + schema + knob surface. Atoms stubbed at 0. | ✅ Shipped 2026-05-14 (commit `5958dcb`) |
| v2.7.113 | Swing-pivot tracker (3 or 5-bar fractal, TF TBD) + `iss_mss` real detection | Operator decision on fractal size + TF coverage |
| v2.7.114 | `iss_choch_support` + `iss_choch_against` real detection (uses swing tracker from v2.7.113) | After v2.7.113 swing tracker validated |
| v2.7.115 | FVG 3-candle imbalance detector + active-FVG state tracker → `iss_fvg` real detection | After v2.7.114 ChoCH validated |
| v2.7.116+ | Activate gates (`iss_block_below_threshold=1`) once monitoring confirms threshold tiers discriminate | Empirical — at least 100 TAKEN signals across diverse day-types confirming the tier behavior |

Each version ships **default-OFF**. Operator approval gates each promotion.

---

## §14. Swing-pivot tracker specification (v2.7.113 scope)

### 14.1 Requirements

- **Fractal size**: 3-bar (Williams) or 5-bar (ICT-standard) — operator decision per ship
- **Timeframe coverage**: M5 minimum; M5+M15 for multi-TF; M5+M15+H1 for full ICT hierarchy
- **Rolling state**: last N=10-20 swing highs + N swing lows per tracked TF
- **Update cadence**: on M5 bar close (not per-tick — too noisy)
- **Cost**: ~100-150 lines of MQL5 per fractal+TF combination

### 14.2 Reference predicate

```mql5
// Williams 3-bar fractal (most common ICT swing definition):
bool IsSwingHigh(int shift) {
   double h = iHigh(_Symbol, PERIOD_M5, shift);
   return (h > iHigh(_Symbol, PERIOD_M5, shift-1)
        && h > iHigh(_Symbol, PERIOD_M5, shift+1));
}

bool IsSwingLow(int shift) {
   double l = iLow(_Symbol, PERIOD_M5, shift);
   return (l < iLow(_Symbol, PERIOD_M5, shift-1)
        && l < iLow(_Symbol, PERIOD_M5, shift+1));
}

// On M5 close: scan shift=1 (just-closed-bar); append confirmed swing to rolling arrays.
```

### 14.3 Storage layout

Two rolling buffers in a new `g_swing_state` struct (or extension of `g_regime`):

```mql5
struct SwingPivot {
   double  price;
   datetime time;
   int     bar_age;     // updated on each M5 close
};

SwingPivot g_swing_highs[10];   // last 10 confirmed M5 swing highs
SwingPivot g_swing_lows[10];    // last 10 confirmed M5 swing lows
int        g_swing_highs_count = 0;
int        g_swing_lows_count = 0;
```

Push on detection; drop oldest when buffer is full.

### 14.4 What this enables

Once shipped, the swing tracker unlocks:
- `iss_mss` real predicate evaluation
- `iss_choch_support` and `iss_choch_against` evaluation (same tracker, different question)
- Future: structural SL placement (below pre-MSS swing low)
- Future: structural TP placement (next swing extreme)
- Future: BSL/SSL distance metrics (`day_high` is the rough proxy; swing-based is sharper)

---

## §15. FVG state tracker specification (v2.7.115 scope)

### 15.1 Active FVG state

```mql5
struct ActiveFvg {
   double  zone_high;
   double  zone_low;
   datetime created_time;
   int     direction;       // +1 = bullish FVG, -1 = bearish
   double  initial_size;    // for fill_pct calculation
};

ActiveFvg g_active_fvgs[8];   // up to 8 active FVGs tracked at once
int       g_active_fvg_count = 0;
```

### 15.2 Lifecycle hooks

| Event | Action |
|---|---|
| M5 close | Check candle[0/1/2] for 3-bar imbalance; append new FVG if detected |
| Every tick | Check if price entered any active FVG zone; update fill_pct |
| M5 close (separate pass) | Expire FVGs older than `iss_fvg_max_age_bars`; consume mitigated FVGs (fill_pct ≥ threshold) |
| Opposite-direction MSS | Invalidate (regime flip — drop all active FVGs opposite to new direction) |

### 15.3 Predicate evaluation

```mql5
bool FvgActiveInDirection(string direction) {
   for(int i = 0; i < g_active_fvg_count; i++) {
      ActiveFvg fvg = g_active_fvgs[i];
      // BUY needs bullish FVG; SELL needs bearish FVG
      if(direction == "BUY"  && fvg.direction != +1) continue;
      if(direction == "SELL" && fvg.direction != -1) continue;
      // Price must be inside the FVG zone
      double price = (SymbolInfoDouble(_Symbol, SYMBOL_BID) + SymbolInfoDouble(_Symbol, SYMBOL_ASK)) / 2;
      if(price >= fvg.zone_low && price <= fvg.zone_high) return true;
   }
   return false;
}
```

---

## §16. Monitoring contract (post-v2.7.112)

The `/forge-monitor` skill consumes ISS columns via Q2:

```sql
SELECT ..., iss_score, iss_mss, iss_fvg, iss_choch_support, iss_choch_against
FROM SIGNALS WHERE outcome='TAKEN' AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
ORDER BY time;
```

Every TAKEN row in tick reports + analysis-doc TAKEN tables MUST show `iss_score` and the atom breakdown. The reporting format:

```
ISS score: 8/10 (MSS +5, FVG +3, ChoCH+ 0, ChoCH− 0)
```

**v2.7.112 expectation**: all atoms log as 0 — pipeline is wired, real detection lands v2.7.113+. Do not flag zero-everywhere as a bug pre-v2.7.115.

**Post-v2.7.115 expectation**: scores distributed across the tier range. Look for:
- High-conviction (≥8) entries — should be highest win-rate
- Standard (5-7) entries — moderate win-rate
- Skipped-or-low (<5) — would-have-been blocked when gate activates

When activation (v2.7.116) is on, `iss_below_threshold` and `iss_choch_against_block` appear in the gate breakdown — their precision can be audited against TAKEN winners on the other side of the threshold.

---

## §17. Glossary

| Term | Definition |
|---|---|
| **ICT** | Inner Circle Trader — a trading methodology emphasizing institutional order flow, structure, and liquidity |
| **MSS** | Market Structure Shift — confirmed structural break (full-body close past prior swing) |
| **ChoCH** | Change of Character — early reversal warning (close past counter-trend swing within existing trend) |
| **BOS** | Break of Structure — continuation confirmation (synonymous with MSS in some literature; FORGE treats MSS as the stricter full-body variant) |
| **FVG** | Fair Value Gap — 3-candle imbalance pattern with unfilled range in candle 2 |
| **OB** | Order Block — last opposite-direction candle before strong directional impulse |
| **BPR** | Balanced Price Range — overlap of bullish and bearish FVGs (high-confluence zone) |
| **BSL** | Buy-Side Liquidity — retail short stops clustered above prior swing highs |
| **SSL** | Sell-Side Liquidity — retail long stops clustered below prior swing lows |
| **PO3** | Power of Three — daily institutional cycle (accumulation → manipulation → distribution) |
| **HTF** | Higher Time Frame (H1 + H4) |
| **MTF** | Middle Time Frame (M15 + M30) |
| **LTF** | Lower Time Frame (M1 + M5, execution) |
| **HH / HL / LH / LL** | Higher High / Higher Low / Lower High / Lower Low (swing-pivot pattern naming) |
| **PEMCG** | FORGE 7-atom reversal-warning composite (Layer 1 atom input to UMCG) — the inducement-detection mechanism |
| **UMCG** | Universal Market Condition Gate — Layer 1 stateless filter consuming PEMCG composite |
| **CVCSM** | Conditional Cooldown State Machine — Layer 2 SL-only cooldown with bidirectional retry |
| **DTC** | Day-Type Classifier — Layer 3 5-state day classifier with exempt-override semantics |
| **DLV / DLS** | Direction Lock Validator + State machine — Layer 4 no-auto-flip direction discipline |
| **ISS** | ICT Structure Score — Layer 5 weighted-boolean score (this document) |

---

## §18. Changelog

- **2026-05-14** — Initial canonical standard. ICT framework (8 concepts) documented; 3 ISS score atoms specified (MSS, ChoCH, FVG) with weights 5/3/2; threshold tiers 5/8 derived from methodology; full schema + knob surface; swing-tracker + FVG-tracker future-version specs; monitoring contract.
- **2026-05-14** — Reframed from migration doc to standalone standard per operator mandate. Architecture context (§2) and full ICT toolkit mapping (§4) added.
