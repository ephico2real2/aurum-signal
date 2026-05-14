# ICT Structure Score (ISS) — Design Reference

**Version**: v2.7.112 (scaffolding only — atoms stubbed, score logged but not enforced)
**Author**: operator + Claude pair-design session 2026-05-14
**Status**: Design + instrumentation scaffold. Real atom detection (MSS/ChoCH/FVG swing-pivot tracker) is a future ship.
**Cross-references**:
- `docs/research/ICT_KILLZONES.md` — adjacent ICT research already in repo (killzone integration)
- `docs/FORGE_CES_DESIGN.md` — retired CES historical reference (do not delete; decision record)
- `.claude/skills/forge-monitor/SKILL.md` — monitor pulls `iss_*` columns per Q2

---

## §1. Why ISS replaces CES

### The empirical case for retirement

CES (v2.7.110 Option C) shipped 6 weighted-boolean atoms summed to a 0–10 score:
- `ces_dtc` (weight 3) — DTC aligned with trade direction
- `ces_pemcg` (weight 2) — PEMCG warnings clean
- `ces_momentum` (weight 2) — momentum candle (m5_strong_bar + range_expanding)
- `ces_rsi` (weight 1) — RSI in trend zone
- `ces_vwap` (weight 1) — VWAP confirmation
- `ces_di` (weight 1) — H1 DI dominance

Run #2 of v2.7.111 produced **7 TAKEN entries with CES scores 2 / 6 / 2 / 6 / 6 / 4 / 7 and a 100% win rate**. The single loss (−$33.24) was a cascade ladder rung with no CES (cascade fills don't emit SIGNALS rows). Net: zero correlation between CES score and trade outcome because the upstream gate stack — **UMCG (PEMCG composite), CVCSM (cooldown), DTC (day-type), DLV/DLS (direction lock)** — had already pre-filtered the TAKEN pool to wins.

**CES wasn't wrong, it was redundant.** Adding weighted atoms downstream of heavy filtering produces a number with no decision power.

### The theoretical case for ICT replacement

The 6 CES atoms are all **derived from existing FORGE atoms that already gate elsewhere in the pipeline** (PEMCG composite, DTC classifier, ADX indicator, VWAP). They measure the same axes that UMCG/DTC/DLV already check.

MSS, ChoCH, and FVG operate on a **different axis entirely**: price-action structure (swing pivots and imbalances). They detect signals **invisible to any existing FORGE atom**. That's the only way to add discriminating power downstream of the existing gate stack.

### What stays vs. what goes

| Layer | Component | Status |
|---|---|---|
| 1 | **UMCG** (consumes PEMCG 7-atom composite) | KEEP |
| 2 | **CVCSM** (SL-only cooldown with bidirectional retry) | KEEP |
| 3 | **DTC** (5-state day-type classifier with exempt overrides) | KEEP |
| 4 | **DLV → DLS** (direction lock evaluator + state machine) | KEEP |
| 5 | **CES** (v2.7.110, 6-atom Confluence Entry Score) | **REMOVED** |
| 5 (new) | **ISS** (3-atom ICT Structure Score) | **NEW** — scaffolded in v2.7.112, atoms stubbed |

---

## §2. The three ISS atoms

### Atom 1 — MSS (Market Structure Shift)

**Definition**: Confirmed structural break of a recent swing high (for BUY) or swing low (for SELL) by a **full-bodied candle close**, not just a wick.

**Why it matters**: ICT canonical signal that the prior structural pattern (higher-highs / higher-lows or lower-highs / lower-lows) has been disrupted in a direction-confirming way. Distinguishes genuine continuation/reversal from liquidity grabs.

**Operational predicate**:
```
For BUY:
  iss_mss = (m5_close[0] > prior_swing_high
            && m5_close[0] - max(m5_open[0], prior_swing_high) >= 0.30 * m5_atr_0
            && m5_strong_bar == 1)

For SELL:
  iss_mss = (m5_close[0] < prior_swing_low
            && min(m5_open[0], prior_swing_low) - m5_close[0] >= 0.30 * m5_atr_0
            && m5_strong_bar == 1)
```

Where `prior_swing_high` / `prior_swing_low` come from a **swing-pivot tracker** (NOT YET IMPLEMENTED — see §6 for swing tracker spec).

**Required from FORGE**: swing-pivot tracker (new MQL5 function ~100-150 lines).
**Existing data used**: `m5_close[0]` (already in SIGNALS as `m5_close_0`), `m5_strong_bar` (logged), `m5_atr` (logged).

**Anti-pattern guarded against**: wick-only breach. ICT calls this a "Liquidity Grab" — price spikes past a swing level on a single wick, retail traders interpret as breakout and enter, smart money reverses hard. The `(close - swing) >= 0.30 * ATR` predicate enforces full-body displacement.

### Atom 2 — ChoCH (Change of Character)

**Definition**: First sign that an established trend is breaking down — price closes **past the most recent counter-trend swing pivot** within an existing trending sequence. Earlier and weaker than MSS; precedes confirmed reversal.

**Why it matters**: ICT pre-MSS warning. A ChoCH **in the same direction as the trade** is supportive (reversal-into-our-direction starting). A ChoCH **against the trade direction** is a hard kill signal (the trend we're entering into is dying).

**Operational predicates**:

```
For a BUY setup:
  iss_choch_support = (downtrend was active for >= 3 prior M5 swings
                       && current m5_close > most_recent_lower_high
                       && early reversal signal favoring our BUY)

  iss_choch_against = (uptrend was active for >= 3 prior M5 swings
                       && current m5_close < most_recent_higher_low
                       && trend dying against our BUY)

For a SELL setup: mirror — choch_support = uptrend breaking down via HL violation;
                  choch_against = downtrend breaking up via LH violation
```

**Required from FORGE**: same swing-pivot tracker as MSS — produces the swing high/low sequence ChoCH evaluates.

**Architectural role of ChoCH atoms**:
- `iss_choch_support` (+2 to score) — confluence boost
- `iss_choch_against` — **HARD GATE**, not score-subtraction. If present, SKIP with `gate_reason=iss_choch_against_block`.

The reason ChoCH-against is a gate rather than a negative weight: a reversal-warning signal opposite to our direction is architecturally a "no", not a "smaller yes". No amount of MSS + FVG confluence makes the entry valid if structural reversal is signaling the other way.

### Atom 3 — FVG (Fair Value Gap)

**Definition**: A 3-candle imbalance pattern where the middle candle has unfilled range. Specifically:

- **Bullish FVG**: `m5_high[2] < m5_low[0]` — gap between candle-2's high and candle-0's low; the body of candle-1 spans this unfilled zone. Price returning into this zone = "fair value retracement entry".
- **Bearish FVG**: `m5_low[2] > m5_high[0]` — gap between candle-2's low and candle-0's high.

**Why it matters**: ICT canonical entry zone. Institutions left an imbalance during impulsive moves; price typically retraces to fill that gap before the real move resumes. Entering at the FVG = entering at "fair value" rather than chasing the breakout.

**Operational predicate**:
```
For BUY (price retracing into bullish FVG):
  iss_fvg = (active_bullish_fvg_exists
            && fvg_low <= price <= fvg_high
            && fvg_age_bars <= iss_fvg_max_age_bars     // default 12 M5 bars
            && fvg_fill_pct <= iss_fvg_max_fill_pct)    // default 0.50

For SELL: mirror with active_bearish_fvg
```

**FVG lifecycle**:
- **Created** when 3 consecutive M5 closes form the imbalance pattern
- **Active** until fill_pct ≥ threshold OR age exceeds max bars OR opposite-direction MSS invalidates the regime
- **Mitigated** (consumed) when price has retraced ≥ `iss_fvg_max_fill_pct` (default 50%) into the gap
- **Stale** (expired) when age > `iss_fvg_max_age_bars`

**Required from FORGE**: 3-candle imbalance detector (~10-20 lines) + active-FVG state tracker (~30 lines).
**Existing data used**: `m5_high[0/1/2]`, `m5_low[0/1/2]` (rolling 3-bar history — needs new state, current SIGNALS columns only have [0] and [1]).

---

## §3. The ISS score — boolean evaluation

### Score formula

```
ISS_score = 
    (iss_mss             ? 5 : 0)   // structural confirmation — primary, mandatory for entry
  + (iss_fvg             ? 3 : 0)   // entry precision — retracement at fair value
  + (iss_choch_support   ? 2 : 0)   // confluence boost — recent ChoCH confirms regime turn

Range: 0 to 10 (matches CES scale for easy schema migration)
```

`iss_choch_against` is NOT in the score arithmetic — it's a **separate hard gate** evaluated before the score.

### Decision tiers (encoded thresholds — derived from ICT methodology, not calibrated)

| ISS score | Action | ICT meaning |
|---|---|---|
| `≥ 8` | **High-conviction** — full position, TP1+TP2 stage | MSS + FVG retracement + ChoCH support (all three) |
| `5–7` | **Standard** — reduced size, TP1-priority | MSS alone, or MSS + one confluence atom |
| `< 5` | **SKIP** with `gate_reason=iss_below_threshold` | No structural confirmation — no setup |

**Why 5 / 8 specifically**:
- **5** = exactly the MSS weight. Threshold of 5 means "MSS is mandatory" — anything ≥5 has MSS, anything <5 doesn't.
- **8** = MSS (5) + FVG (3). Minimum score that includes the FVG retracement entry. Defines the high-conviction tier where ICT teaches full-position sizing.

These thresholds aren't arbitrary calibration — they directly encode the ICT entry hierarchy (MSS mandatory, FVG defines high-conviction, ChoCH confluence boost).

### Hard gate (NOT score-based)

```
if (iss_choch_against)
   → SKIP with gate_reason = "iss_choch_against_block"
```

Evaluated **before** the score. ChoCH against direction is an architectural NO, not a numeric weight.

---

## §4. v2.7.112 scope — instrumentation-only scaffolding

This ship lands the **schema, knobs, globals, score-compute infrastructure, and logging plumbing** — but NOT the MSS/ChoCH/FVG atom detection. Atom predicates return `0` for now. The reason: operator wants to **log the (currently always-zero) score and continuously monitor**, then decide when to wire the swing-pivot tracker + FVG detector in a follow-up ship.

### What v2.7.112 adds

**SIGNALS schema** — 5 new columns (all default 0):
```sql
ALTER TABLE SIGNALS ADD COLUMN iss_score INTEGER DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN iss_mss INTEGER DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN iss_choch_support INTEGER DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN iss_choch_against INTEGER DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN iss_fvg INTEGER DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_sig_iss_score ON SIGNALS(iss_score);
```

**Struct fields** (in `ScalperConfig`):
```mql5
bool   iss_enabled;                 // default 0 — entire ISS module
int    iss_min_threshold;           // default 5  (= MSS-mandatory bar)
bool   iss_block_below_threshold;   // default 0 — gate-mode toggle; instrumentation-only when 0
int    iss_fvg_max_age_bars;        // default 12 (M5 bars)
double iss_fvg_max_fill_pct;        // default 0.50
```

**Globals** (per-tick state):
```mql5
int   g_iss_score = 0;
int   g_iss_mss = 0;
int   g_iss_choch_support = 0;
int   g_iss_choch_against = 0;
int   g_iss_fvg = 0;
```

**ComputeIssScore() stub function** (added but returns zeros until real detection lands):
```mql5
void ComputeIssScore(string direction) {
   // v2.7.112: SCAFFOLDING ONLY — real atom detection ships in v2.7.113+
   // Real implementation requires:
   //   - swing-pivot tracker (3/5/7-bar fractal, TF + size operator-decided)
   //   - 3-candle FVG detector + active-zone state tracker
   //   - direction-aware ChoCH support/against evaluation
   // For v2.7.112, all atoms return 0 → iss_score=0 logged in every SIGNALS row
   g_iss_mss = 0;
   g_iss_choch_support = 0;
   g_iss_choch_against = 0;
   g_iss_fvg = 0;
   g_iss_score = 0;
}
```

**JournalRecordSignal** — appended 5 columns + values to the INSERT path.

### What v2.7.112 removes

**Everything CES-related** from `ea/FORGE.mq5`:
- Struct fields: `ces_enabled`, `ces_min_threshold`, `ces_block_below_threshold`, `ces_weight_dtc_aligned`, `ces_weight_pemcg_clean`, `ces_weight_momentum_candle`, `ces_weight_rsi_trend_zone`, `ces_weight_vwap_confirm`, `ces_weight_di_dominance`
- Globals: `g_ces_score`, `g_ces_component_dtc`, `g_ces_component_pemcg`, `g_ces_component_momentum`, `g_ces_component_rsi`, `g_ces_component_vwap`, `g_ces_component_di`
- JsonHasKey loader entries for all 9 CES keys
- JournalRecordSignal INSERT columns + values for `ces_score`, `ces_dtc`, `ces_pemcg`, `ces_momentum`, `ces_rsi`, `ces_vwap`, `ces_di`
- ALTER TABLE migration that added the 7 CES columns
- `idx_sig_ces_score` CREATE INDEX
- All CES compute logic

**From `config/scalper_config.defaults.json`** — 9 CES keys in safety section.

**From `scripts/sync_scalper_config_from_env.py`** — 9 `FORGE_CES_*` mapping entries.

**From `.env.example`** — CES documentation block.

**From `.env`** — active CES knobs (if operator had set any).

**The CES SCHEMA columns themselves** (`ces_score`, `ces_dtc`, etc.) are **NOT** dropped from existing DBs. SQLite ALTER TABLE DROP COLUMN is a recent feature, and the dropping operation risks data loss. The new FORGE.mq5 simply stops INSERT-ing into those columns; they remain in the schema as dead nullable fields. A future ship may add a clean migration if desired.

### What v2.7.112 does NOT do

- **Real MSS / ChoCH / FVG detection** — deferred to v2.7.113+ (operator approval needed for swing-tracker scope)
- **Update `python/scribe.py` `sync_forge_journal`** — its placeholder count + column list must match the SIGNALS schema. Defer the scribe update until operator reloads MT5 with v2.7.112 binary, so BRIDGE keeps syncing the currently-running v2.7.111 run (which still writes CES columns)
- **`make forge-compile`** — do NOT compile during the active backtest. The current run #2 must complete on v2.7.111 first

---

## §5. Migration plan (multi-ship)

| Version | Scope | Trigger to ship |
|---|---|---|
| **v2.7.112** (this ship) | Design doc + EA scaffolding + config purge + skill update | Once written + tested, commit & push (no MT5 reload during active run) |
| v2.7.113 | Swing-pivot tracker (3 or 5-bar fractal, TF TBD) + MSS atom real detection | Operator decision on fractal size + which TFs |
| v2.7.114 | ChoCH atom real detection (uses swing tracker from .113) | After MSS validated in monitoring |
| v2.7.115 | FVG atom real detection + active-zone state tracker | After ChoCH validated |
| v2.7.116+ | Set `iss_block_below_threshold=1` (activate the gate) once monitoring shows score discriminates winners from losers | Empirical — at least 100 TAKEN signals across diverse day-types |

Each version ships **default-OFF** until the prior version is validated. No swing-tracker / atom detection lands without empirical justification.

---

## §6. The swing-pivot tracker (future ship — v2.7.113 scope)

NOT IMPLEMENTED in v2.7.112. Specification for the future implementation:

### Requirements

- **Fractal size**: 3-bar (Williams) or 5-bar (ICT-standard) — operator decision
- **Timeframe**: M5 minimum; M5+M15 for multi-TF; M5+M15+H1 for full ICT hierarchy
- **State**: rolling array of last N swing highs + N swing lows (N=10-20)
- **Update cadence**: on M5 bar close
- **Cost**: ~100-150 lines of MQL5, single iCustom call per TF tracked

### Reference implementation pattern (MQL5 community)

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

// On M5 close: check shift=1 (just-closed-bar), append to swing arrays
```

### Storage strategy

- Two rolling buffers in `g_regime` struct (or new dedicated struct): `g_swing_highs[10]`, `g_swing_lows[10]`
- Each entry: `{price, time, age_bars}`
- Push on new swing detection, drop oldest when buffer fills

---

## §7. The FVG state tracker (future ship — v2.7.115 scope)

NOT IMPLEMENTED in v2.7.112. Spec for future implementation:

### Active FVG state

```mql5
struct ActiveFvg {
   double  zone_high;
   double  zone_low;
   datetime created_time;
   int     direction;       // +1 = bullish FVG, -1 = bearish
   double  initial_size;    // for fill_pct calculation
};

ActiveFvg g_active_fvgs[8];   // up to 8 active FVGs tracked
int       g_active_fvg_count = 0;
```

### Lifecycle hooks

- **On M5 close**: detect new 3-bar imbalance; append to `g_active_fvgs`
- **On every tick**: check if price entered any active FVG zone; update fill_pct
- **On bar close**: expire FVGs older than `iss_fvg_max_age_bars`
- **On opposite-direction MSS**: invalidate (regime flip)

---

## §8. Why ISS is computable without backtest calibration

Unlike CES (whose threshold was supposed to come from empirical W/L correlation we couldn't measure), **ISS thresholds are derived from ICT methodology itself**:

- MSS mandatory → threshold ≥ 5 (matches MSS weight)
- High-conviction = MSS + FVG → threshold ≥ 8 (matches MSS + FVG weights)
- ChoCH-against = architectural NO (gate, not weight)

These come from how ICT teaches entry sizing. We're not picking numbers from backtest curves; we're encoding the methodology into the weights. That gives us a **meaningful default-ON gate from day one of v2.7.116** (whereas CES Option A could never activate because we had no calibration data).

---

## §9. Cross-references in the SIGNALS schema (after v2.7.112)

| Column | Meaning | Populated by |
|---|---|---|
| `iss_score` | 0–10 weighted-boolean total | `ComputeIssScore()` (stubbed at 0 in v2.7.112) |
| `iss_mss` | 0/1 — MSS confirmed in trade direction | stubbed at 0 |
| `iss_choch_support` | 0/1 — supportive ChoCH recent | stubbed at 0 |
| `iss_choch_against` | 0/1 — counter-direction ChoCH (HARD GATE if 1) | stubbed at 0 |
| `iss_fvg` | 0/1 — price inside active FVG aligned with direction | stubbed at 0 |

CES columns (`ces_score`, `ces_dtc`, `ces_pemcg`, `ces_momentum`, `ces_rsi`, `ces_vwap`, `ces_di`) remain in the schema for historical compatibility but receive only DEFAULT 0 values on v2.7.112+ INSERTs.

---

## §10. Operator monitoring contract (post-v2.7.112)

The `/forge-monitor` skill's Q2 query (TAKEN-signals row) will pull `iss_*` columns alongside `rsi`, `adx`, `session`. Every monitoring tick displays:

| Column | Value |
|---|---|
| `iss_score` | 0 (until v2.7.113+ atoms wire) |
| `iss_mss` | 0 |
| `iss_choch_support` | 0 |
| `iss_choch_against` | 0 |
| `iss_fvg` | 0 |

Once v2.7.113-115 wire the real detectors, those will populate naturally with no further plumbing changes. The monitor will start showing the actual score distribution and operator can decide when to flip `iss_block_below_threshold=1`.

---

## §11. Changelog

- **2026-05-14** — Initial doc. CES retirement rationale (Run #2 evidence), 3-atom ISS design (MSS + ChoCH + FVG), weights 5/3/2, threshold tiers 5/8, hard gate for choch_against, v2.7.112 scaffolding spec (instrumentation-only), multi-ship migration plan v2.7.113-116.
