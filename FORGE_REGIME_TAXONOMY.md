# FORGE Regime Taxonomy — Current State + Unified Model + Migration Plan

**Purpose**: Audit of FORGE's regime/trend concepts (56 variables across 4 categories),
identification of structural overlap, and a phased migration plan to a unified `RegimeState`
struct.

**Created**: 2026-05-12
**Living document**: update when new regime concept added, when a phase of the migration
completes, when industry terminology is adopted, or when a conceptual gap is closed.
Skill mandates this. §11 changelog is append-only.

---

## §1. Current state — ~56 regime/trend variables

### §1.1 Global state vars (`g_*`) — 13

```mql5
// Inline classifier output
string g_regime_label = "";              // "" | TREND_BULL | TREND_BEAR | RANGE | VOLATILE
double g_regime_confidence = 0;
bool   g_regime_apply_policy = false;    // gate flag
double g_regime_ct_min_conf = 0.55;      // counter-trend block threshold

// ADX hysteresis (independent track)
bool g_adx_trend_regime = false;         // M5 ADX enter=35 / exit=28

// Daily bias suite (7 vars for 3 concepts)
datetime g_daily_bias_cache_bar = 0;     // cache marker
double   g_daily_slope_pts     = 0.0;    // D1 SMA slope (signed)
double   g_daily_atr_pts       = 0.0;    // D1 ATR (denominator)
double   g_daily_move_pts      = 0.0;    // D1 intraday cumulative move
bool     g_daily_bear_bias     = false;  // slope < −threshold → block BUY
bool     g_daily_bull_bias     = false;  // slope > +threshold → block SELL
bool     g_daily_intraday_bear = false;  // intraday move bear
bool     g_daily_intraday_bull = false;  // intraday move bull
bool     g_daily_prev_intraday_bear = false;  // hysteresis state
bool     g_daily_prev_intraday_bull = false;  // hysteresis state
bool     g_daily_flip_now      = false;  // one-tick edge flag
```

### §1.2 Indicator handle globals — 6

```mql5
int g_h4_ma20, g_h4_ma50, g_h4_atr, g_h4_rsi, g_h4_bb, g_h4_adx;
int g_m1_ma20, g_m1_ma50, g_m1_atr;
```

(Indicator sources, not state. Counted because they're part of the regime computation pipeline.)

### §1.3 g_sc struct config fields — ~22

```mql5
// Daily-direction gate (8)
bool   daily_direction_gate_enabled;
int    daily_sma_period;
int    daily_sma_lookback_days;
double daily_slope_block_atr;
double daily_move_block_atr;
double daily_move_flip_hysteresis;
bool   daily_cancel_pending_on_flip;
bool   daily_cancel_includes_cascade;

// Regime H1-strong override (2)
double regime_h1_override_factor;
double regime_h1_override_adx_min;

// H4 supplemental gates (6)
bool   h4_rsi_gate_enabled;
double h4_rsi_sell_max;
double h4_rsi_buy_min;
bool   h4_adx_gate_enabled;
double h4_adx_min_sell;
double h4_adx_min_buy;

// Trend strength threshold (1)
double trend_strength_atr_threshold;

// High-vol regime config (10)
bool   high_vol_trend_guard_enabled;
bool   high_vol_apply_in_tester;
double high_vol_adx_min;
double high_vol_trend_strength_min;
bool   high_vol_disable_bounce;
bool   high_vol_require_h1_h4_breakout_align;
double high_vol_breakout_sl_boost;
int    high_vol_fast_lock_extra_hold_sec;
double high_vol_fast_lock_trigger_mult;
double high_vol_fast_lock_trail_mult;

// ADX hysteresis thresholds (2)
double adx_trend_enter;
double adx_trend_exit;
```

### §1.4 Per-tick locals (computed in `ScalperEvaluate()`) — ~15

```mql5
// H1 trend
double h1_trend_strength;
bool   h1_bull, h1_bear, h1_flat;

// H4 trend
double h4_trend_strength;
bool   h4_bull, h4_bear, h4_flat;

// M15 trend
double m15_trend_strength_htf;
bool   m15_bull_htf, m15_bear_htf;

// M1 trend
double m1_trend_strength;
bool   m1_bull, m1_bear, m1_flat;

// Aggregates
bool   high_vol_trend;
bool   trend_dir_agree;
double trend_mag;
```

### §1.5 Total

| Category | Yesterday | After v2.7.36→v2.7.39 (audit 2026-05-12) | Δ | Why |
|---|---|---|---|---|
| Global state vars (regime/daily/ADX) | 13 | 13 | 0 | unchanged |
| Indicator handles (regime path) | 6 | 6 | 0 | unchanged |
| g_sc struct fields (regime-specific) | 22 | 22 | 0 | unchanged — §1.3 inventory stayed pure regime |
| Per-tick locals (regime trend) | 15 | 15 | 0 | unchanged |
| **Regime subtotal** | **~56** | **~56** | **0** | **§1 scope unchanged** |
| — — — — — — — — | | | | |
| Session/killzone g_sc fields (v2.7.36 — NEW category) | 0 | 19 | +19 | minute-precision windows + NY-anchor + KZ atoms |
| Killzone state globals (v2.7.36) | 0 | 3 | +3 | `g_scalper_last_killzone_label`, `g_scalper_killzone_start_time`, `g_scalper_killzone_trades` |
| Atom telemetry globals `g_eval_*` (v2.7.37 — NEW category) | 0 | 70 | +70 | 69 multi-TF/OHLC atoms + 1 `g_eval_last_tick` idempotency guard. Per-tick scope but stored as globals (avoids 52-call-site signature change) |
| Composite g_sc fields (v2.7.38 — NEW category) | 0 | 12 | +12 | 4 enable flags + 8 geometry/lot/cooldown knobs |
| Composite state globals (v2.7.38) | 0 | 4 | +4 | 2 cooldown anchors + 2 log throttles |
| **Extension subtotal** | **0** | **108** | **+108** | new categories from v2.7.36–v2.7.39 |
| | | | | |
| **GRAND TOTAL** | **~56** | **~164** | **+108** | regime core stayed flat; 3 new categories added |

**Key insight**: the regime/trend/daily core (§1.1-§1.4) **did not grow** despite three releases. The +108 came from net-new concept categories (session/KZ, atom telemetry, boolean composites) that didn't exist in the original 56-var inventory. The Phase 2-4 RegimeState consolidation (§3-§5) reduces the regime subset to ~16 fields (-40); env-knob renames (§10.5) clean up naming for 36 of the knobs. Atom telemetry (`g_eval_*`) is intentionally per-tick global by design (single point of computation, 52-call-site avoidance — see v2.7.37 CHANGELOG) and is NOT in scope for the RegimeState consolidation.

---

## §2. Why 56 feels like too many — structural overlap

Same conceptual question answered by 3-4 different variables:

```
Question: "Is H1 bullish?"
  ├─ h1_bull (per-tick local)
  ├─ h1_trend_strength > thr (per-tick numeric)
  ├─ g_regime_label == "TREND_BULL" (global, integrates H1+H4)
  └─ g_daily_bull_bias (global, but actually D1 not H1 — name conflation)

Question: "What is the trend strength?"
  ├─ h1_trend_strength
  ├─ h4_trend_strength
  ├─ m15_trend_strength_htf
  ├─ trend_mag (max of |H1|, |H4|)
  └─ g_sc.adx_trend_enter / adx_trend_exit (thresholds)

Question: "Is the market trending?"
  ├─ g_adx_trend_regime (M5 ADX hysteresis only)
  ├─ g_regime_label != "RANGE" (inline classifier)
  ├─ high_vol_trend (volatility-trend hybrid)
  └─ trend_dir_agree (H1+H4 directional agreement)

Question: "Is daily slope bearish?"
  ├─ g_daily_bear_bias (computed bool)
  ├─ g_daily_slope_pts (raw signed value)
  ├─ g_daily_slope_pts / g_daily_atr_pts (manual ratio)
  └─ regime_label TREND_BEAR (related but different — not D1, it's H1+H4)
```

**Each question has 3-4 valid-but-different answers.** That's an analytical hazard — composites may inadvertently use the wrong one.

---

## §2.6. HTF / MTF / LTF — glossary

Used throughout this document and the `RegimeState` struct. Standard multi-timeframe
trading vocabulary from Murphy, Tradeciety, Markets4you, and most modern intraday
literature.

| Abbreviation | Meaning | In our context |
|---|---|---|
| **HTF** | Higher Time Frame | H1 + H4 (what we previously called "macro") |
| **MTF** | Middle Time Frame | M15 + M30 |
| **LTF** | Lower Time Frame | M1 + M5 (execution) |

**Core idea**: A trader looks at multiple timeframes simultaneously — HTF for context
("which way is the bigger picture moving?"), LTF for execution ("when exactly do I enter?").

**Why we use HTF (not "macro") in the `RegimeState` struct**:

- **Industry-aligned** — anyone reading MTF trading content (Murphy "Technical Analysis of
  the Financial Markets", Tradeciety, Markets4you) sees HTF/MTF/LTF as the canonical terms.
- **Avoids economics confusion** — "macro" in finance often means macroeconomic data (Fed
  policy, GDP, CPI). HTF unambiguously means "higher chart timeframe."
- **Cleaner pairing** — HTF + intraday + LTF reads as a vocabulary set; "macro" was an
  outlier loaned from another field.

When you see `g_regime.htf_*`, read it as "regime state on the H1+H4 timeframes."

---

## §3. Approved unified shape — `RegimeState` struct

**Status**: operator-approved 2026-05-12 as the Phase 2 target. Field NAMES finalized
after industry-terminology research (§9): adopted `htf_*` prefix (HTF/MTF/LTF vocabulary)
and `_counter_htf` suffix (avoiding "_diverged" which canonically means RSI/MACD-vs-price
divergence in trading literature).

**Goal**: one canonical answer per question. Single source of truth queryable via dotted access.

```mql5
struct RegimeState {
   // ──── Layer 1: HTF regime (H1+H4 integrated — Higher Time Frame in MTF vocab) ────
   string htf_label;            // "TREND_BULL" | "TREND_BEAR" | "RANGE" | "VOLATILE" | ""
   double htf_confidence;       // 0–1
   bool   htf_h1_strong;        // h1_trend ≥ override_factor × thr (was inline)
   
   // ──── Layer 2: Intraday regime (NEW — M5+M15 derived) ────
   string intraday_label;       // "TREND_BULL" | "TREND_BEAR" | "RANGE" | "DECLINING" | "RISING"
   double intraday_confidence;
   bool   intraday_counter_htf;       // Apr 8 PM detector — TRUE when intraday counters HTF direction
                                       // (RENAMED twice 2026-05-12 per industry-terminology research:
                                       //   1. `_diverged` → `_counter_*` — "divergence" canonically means
                                       //      RSI/MACD-vs-price divergence in trading literature
                                       //   2. `_macro` → `_htf` — aligns with MTF (HTF/MTF/LTF) vocabulary
                                       //      from Murphy, Tradeciety, Markets4you)
   
   // ──── Layer 3: Daily slope (collapsed from 7 g_daily_* vars to 3) ────
   double daily_slope_atr;      // signed, ATR-normalized (= g_daily_slope_pts / g_daily_atr_pts)
   bool   daily_bear_bias;      // = (daily_slope_atr < -slope_block_atr)
   bool   daily_bull_bias;      // = (daily_slope_atr > +slope_block_atr)
   bool   daily_flip_now;       // edge flag (one-tick)
   
   // ──── Layer 4: Volatility ────
   bool   high_vol;             // = current high_vol_trend
   double m5_adx;               // raw M5 ADX (exposed for composite atom queries)
   
   // ──── Layer 5: Session / news context ────
   string session;              // "ASIA" | "LONDON" | "NY"
   bool   news_active;          // hot from news_filter state
};

RegimeState g_regime;            // single source of truth, populated each tick by RegimeUpdate()
```

**13 fields in 1 struct, replacing ~20 existing globals.**

### §3.1 New concepts introduced

Only **2 of the 13 fields are NEW** (rest are reorganization):

| New field | What it captures | Why we need it |
|---|---|---|
| `intraday_label` | M5+M15 regime independent of HTF H1+H4 | Closes the "Apr 8 PM gap" — intraday declining while HTF stays TREND_BULL |
| `intraday_counter_htf` (was `intraday_vs_macro_diverged`) | Convenience bool — TRUE when intraday counters HTF direction | Composites query directly; powers `INTRADAY_REVERSAL_TO_SELL` natively. Renamed 2026-05-12 from `intraday_vs_macro_diverged`: (1) "divergence" canonically refers to RSI/MACD-vs-price in trading lit, not timeframe conflict; (2) `_macro` → `_htf` aligns with MTF vocabulary. See `docs/RESEARCH_NOTES_regime_terminology.md`. |

Everything else is **reorganization** of existing variables. No new computation, just one canonical place to read.

### §3.2 Code readability — before/after

```mql5
// BEFORE (current code; same condition asked 4 ways):
if (h1_bull
    && (h4_bull || h4_flat)
    && !g_daily_bear_bias
    && g_regime_label == "TREND_BULL"
    && !high_vol_trend) { ... }
// Reader must mentally check: are these 5 vars consistent? Could one be stale?

// AFTER (unified):
if (g_regime.htf_label == "TREND_BULL"
    && !g_regime.daily_bear_bias
    && !g_regime.high_vol) { ... }
// Three dotted reads from one struct. No staleness possible (computed once per tick).
```

Composite specs become directly translatable from atlas §5 to MQL5:

```mql5
bool BULL_DAY_DIP_BUY_V3 =
     (g_regime.htf_label == "TREND_BULL" || g_regime.htf_h1_strong)
  && (!g_regime.daily_bear_bias)
  && (g_regime.session == "LONDON" || g_regime.session == "NY")
  && (!g_regime.intraday_counter_htf)              // ← Apr 8 PM check, one bool
  && (m5_rsi >= 30 && m5_rsi <= 50)
  && (m5_adx >= 12 && m5_adx <= 40)
  && (price <= m5_bb_m + 0.5 * m5_atr)
  && ...;
```

vs the current version which queries 7+ different globals/locals.

---

## §4. Count reduction

| Category | Current | Proposed | Delta |
|---|---|---|---|
| Global state vars | 13 | 1 struct (g_regime) | **−12** globals; +13 fields in struct |
| Indicator handles | 6 | 6 | no change |
| g_sc struct fields (config) | 22 | 22 | no change (config layer, not regime concept) |
| Per-tick locals | ~15 | ~5 (only what's NOT in g_regime) | **−10** locals |
| **TOTAL (fields counted singly)** | **56** | **~33** | **−23 (≈40% reduction)** |
| **TOTAL (struct as 1 var)** | **56** | **~21** | **−35 (≈63% reduction)** |

---

## §5. Phased migration plan (strangler-fig pattern)

### Phase 1 — v2.7.36 (NO refactor; ship V3 composites with current variables)

- Get the trading loop validated end-to-end with new boolean composites
- DO NOT touch the regime variable model
- Phase 1 is about proving the composite framework works, not about refactoring

### Phase 2 — v2.7.37 (introduce `g_regime` ALONGSIDE existing variables)

```mql5
// Add g_regime struct (~13 LOC)
RegimeState g_regime;

// Add RegimeUpdate() function (~80 LOC) called every tick from ScalperEvaluate
//   — populates g_regime from existing variables
//   — adds NEW intraday_label + intraday_counter_htf computation
//   — keeps ALL existing globals updated (no break)
```

NEW composites use `g_regime.*`. OLD code paths keep reading old globals. Both updated each tick from the same source.

### Phase 3 — v2.7.38+ (migrate OLD code paths to `g_regime`)

One-at-a-time migration:
1. BB_BREAKOUT filter chain → `g_regime.htf_label`, `g_regime.daily_bear_bias`
2. BB_BOUNCE filter chain → same
3. MOMENTUM_DUMP filter chain → same (already uses regime_label, easy rename)
4. ScalperEvaluate trend computation → consolidate into `RegimeUpdate()` only
5. Remove `g_daily_*` globals (replaced by `g_regime.daily_*`)
6. Remove `h1_bull` / `h4_bull` per-tick locals (replaced by `g_regime.htf_label`)
7. Remove `g_adx_trend_regime` (replaced by `g_regime.high_vol` or part of `htf_label`)

Each migration step is a small PR with regression validation against a known-good tester run.

### Phase 4 — v2.7.40 (legacy globals removed, `g_regime` is canonical)

```mql5
// All entry logic reads from g_regime.* only
// Old globals deleted
// Migration complete
```

---

## §6. Risk vs reward

| Aspect | Current state | Post-migration | Trade-off |
|---|---|---|---|
| Variable count | 56 | 33 (40% reduction) | Less surface; less code; easier reasoning |
| Composite spec → MQL5 translation | Manual, error-prone | Mechanical (one-to-one) | Wins time on every new composite |
| Apr 8 PM-class bugs | Possible (intraday vs HTF overlap not modeled) | Built-in `intraday_counter_htf` | Structural protection vs case-by-case |
| Phase 2 implementation risk | — | LOW (additive — no removal yet) | Safe to ship alongside existing logic |
| Phase 3 implementation risk | — | MEDIUM (touches ~80 call sites) | Migrate in small PRs with regression tests |
| Phase 4 cleanup risk | — | LOW (mechanical removal) | Just deletion of unused globals |

---

## §7. Open questions

1. ~~**Industry-standard naming** — should `macro_label` / `intraday_label` align with Dow Theory ("primary trend / secondary trend") or multi-timeframe trading terminology (HTF / MTF / LTF)?~~ **CLOSED 2026-05-12**: adopted HTF/MTF/LTF vocabulary (`htf_label` / `intraday_label`). `intraday_label` kept (clearer than Dow "secondary trend" which means months-years). See `docs/RESEARCH_NOTES_regime_terminology.md`.

2. **Should `intraday_label` add values `DECLINING` and `RISING`?** Current `g_regime_label` only has `TREND_BULL` / `TREND_BEAR` / `RANGE` / `VOLATILE`. The Apr 8 PM scenario needs a sustained-decline-but-not-yet-TREND_BEAR concept. Could add new enum values.

3. **`session` as a regime layer or independent?** Currently a per-tick local string. Adding to `g_regime` puts it in the canonical view but might overstuff (session isn't computed from indicators — it's a clock check).

4. **`news_active` integration** — should news be a regime layer or a separate `g_news` struct? Argument for separation: news state is event-driven, not continuous; regime state is continuous.

5. **`g_regime_apply_policy` and `g_regime_ct_min_conf`** — these are policy decisions about USING the regime, not state about WHAT the regime IS. Should they live in `g_sc` config, not `g_regime` state? Probably yes.

6. **Phase 3 testing strategy** — how do we regression-test that the migrated code paths fire the same entries as the pre-migration version? Likely: capture last N days of SIGNALS, replay against both old + new code path, diff outputs.

---

## §8. Cross-references

- **Decision Stack** (`FORGE_DECISION_STACK.md`) — `g_regime` is an atom source for composites
- **Atlas §1** (`docs/FORGE_INDICATOR_ATLAS.md`) — indicator inventory; `g_regime.*` fields become canonical atom sources
- **Composite Roadmap** (`FORGE_COMPOSITE_ROADMAP.md`) — Tier 1 v2.7.36 composites still use current variables; Tier 2 may use `g_regime.*` (Phase 2)
- **Naming Conventions** (`FORGE_NAMING_CONVENTIONS.md`) — `g_regime.*` follows new policy (FORGE_GLOBAL prefix for the related env knobs if we move config in)
- **Research-Ops** (`FORGE_RESEARCH_OPS.md`) — `intraday_counter_htf` is exactly the "structural protection vs case-by-case" pattern §4 cites
- **Case study Mar 31 → Apr 8** (`docs/FORGE_CASE_STUDY_2026_03_31_to_04_08.md`) — Apr 8 12:00 pivot motivated `intraday_counter_htf`
- **Logging extension design** (`docs/FORGE_LOGGING_EXTENSION_DESIGN.md`) — `g_regime` fields should be logged to SIGNALS for cross-day validation

---

## §9. Industry terminology — alignment under research

Background research agent running on canonical regime/trend terminology from:
- Dow Theory (Primary / Secondary / Minor trend)
- Wyckoff (Markup / Distribution / Markdown / Accumulation)
- Elliott Wave (Impulse / Corrective)
- Multi-timeframe trading (HTF / MTF / LTF)
- Volatility regime literature
- Academic regime-switching models (Markov regime, HMM)

**Outcome (research complete 2026-05-12)**: Adopted HTF/MTF/LTF vocabulary. `macro_label` → `htf_label` (and cascade renames: `macro_confidence` → `htf_confidence`, `macro_h1_strong` → `htf_h1_strong`, `intraday_vs_macro_diverged` → `intraday_counter_htf`). Kept: `intraday_label`, `daily_slope_atr`, `high_vol`, all 4 enum values. Full reasoning in `docs/RESEARCH_NOTES_regime_terminology.md`.

If the research finds an industry-standard term that's CLEARER than our proposed name, we adopt it. If not, we keep our descriptive names. The goal is reader-friendliness, not jargon-matching for its own sake.

---

## §10. Cross-reference back to other strategic docs

This document fits the established pattern:

| Strategic doc | Covers | This doc's relation |
|---|---|---|
| FORGE_RESEARCH_OPS.md | Vision + loop + anti-patterns | This taxonomy is a "what's not yet aligned" item (operating-loop §5) being resolved |
| FORGE_DECISION_STACK.md | 5-layer entry-decision terminology | `g_regime` is an atom source; doesn't change the stack model |
| FORGE_COMPOSITE_ROADMAP.md | Composite inventory + shipping plan | Composites consume `g_regime.*` from Phase 2 onward |
| FORGE_NAMING_CONVENTIONS.md | Config knob naming policy | `g_regime.*` field names should follow the same internal-consistency principles |
| FORGE_SETUP_PLAYBOOK.md | Setup catalog | Setups read `g_regime.*` for direction filters |

---

## §10.5. Env-knob rename plan — Phase 2 alongside struct introduction

When `RegimeState` struct ships (Phase 2 = v2.7.37), the underlying `.env` knobs that
configure regime-related atoms/gates should also be renamed to match the new policy
in `FORGE_NAMING_CONVENTIONS.md §4`. This is a controlled, scoped rename — not the
"never rename" rule from naming conventions §5 (which applies to the BREAKOUT / DUMP /
BOUNCE setup-specific knobs that aren't being touched anyway).

**Scope**: only the **20 regime/trend/daily/HTF env knobs** below (14 active in `.env`
+ 6 in `.env.example`-only). All other 126 FORGE_* knobs remain grandfathered.

**Justification**: these 20 knobs are the ones touched by the `g_regime` struct
refactor anyway. Renaming during the same PR is cheap; doing it later is two changes.

### §10.5.1 Proposed rename mapping

Following `FORGE_NAMING_CONVENTIONS.md §4` policy: `FORGE_<scope>_<layer>_<param>_<direction?>`
where scope ∈ {SETUP, COMPOSITE, GATE, ATOM, GEOMETRY, TIMING, GLOBAL}.

| Current | Proposed | Scope | Maps to RegimeState field |
|---|---|---|---|
| `FORGE_REGIME_H1_OVERRIDE_FACTOR` | `FORGE_ATOM_HTF_H1_STRONG_FACTOR` | ATOM | `htf_h1_strong` threshold |
| `FORGE_REGIME_H1_OVERRIDE_ADX_MIN` | `FORGE_ATOM_HTF_H1_STRONG_ADX_MIN` | ATOM | `htf_h1_strong` ADX gate |
| `FORGE_DAILY_DIRECTION_GATE_ENABLED` | `FORGE_GATE_DAILY_DIRECTION_ENABLE` | GATE | `daily_bear_bias` / `daily_bull_bias` activation |
| `FORGE_DAILY_CANCEL_PENDING_ON_FLIP` | `FORGE_GATE_DAILY_FLIP_CANCEL_PENDING` | GATE | `daily_flip_now` behavior |
| `FORGE_DAILY_CANCEL_INCLUDES_CASCADE` | `FORGE_GATE_DAILY_FLIP_CANCEL_CASCADE` | GATE | `daily_flip_now` behavior |
| `FORGE_DAILY_SMA_PERIOD` | `FORGE_ATOM_DAILY_SMA_PERIOD` | ATOM | `daily_slope_atr` computation |
| `FORGE_DAILY_SMA_LOOKBACK_DAYS` | `FORGE_ATOM_DAILY_SMA_LOOKBACK` | ATOM | `daily_slope_atr` computation |
| `FORGE_DAILY_SLOPE_BLOCK_ATR` | `FORGE_ATOM_DAILY_SLOPE_BLOCK_ATR` | ATOM | `daily_bear/bull_bias` threshold |
| `FORGE_DAILY_MOVE_BLOCK_ATR` | `FORGE_ATOM_DAILY_MOVE_BLOCK_ATR` | ATOM | intraday-move threshold |
| `FORGE_DAILY_MOVE_FLIP_HYSTERESIS` | `FORGE_ATOM_DAILY_MOVE_FLIP_HYSTERESIS` | ATOM | `daily_flip_now` edge guard |
| `FORGE_H4_RSI_GATE_ENABLED` | `FORGE_GATE_HTF_H4_RSI_ENABLE` | GATE | H4 RSI filter activation |
| `FORGE_H4_RSI_SELL_MAX` | `FORGE_ATOM_HTF_H4_RSI_MAX_SELL` | ATOM | H4 RSI sell ceiling |
| `FORGE_H4_RSI_BUY_MIN` | `FORGE_ATOM_HTF_H4_RSI_MIN_BUY` | ATOM | H4 RSI buy floor |
| `FORGE_H4_ADX_GATE_ENABLED` | `FORGE_GATE_HTF_H4_ADX_ENABLE` | GATE | H4 ADX filter activation |
| `FORGE_H4_ADX_MIN_SELL` | `FORGE_ATOM_HTF_H4_ADX_MIN_SELL` | ATOM | H4 ADX sell threshold |
| `FORGE_H4_ADX_MIN_BUY` | `FORGE_ATOM_HTF_H4_ADX_MIN_BUY` | ATOM | H4 ADX buy threshold |
| `FORGE_ADX_HYSTERESIS_ENABLED` | `FORGE_GATE_M5_ADX_HYSTERESIS_ENABLE` | GATE | `htf_label` ADX-derived component |
| `FORGE_ADX_TREND_ENTER` | `FORGE_ATOM_M5_ADX_TREND_ENTER` | ATOM | hysteresis enter threshold |
| `FORGE_ADX_TREND_EXIT` | `FORGE_ATOM_M5_ADX_TREND_EXIT` | ATOM | hysteresis exit threshold |
| `FORGE_ADX_HYSTERESIS_APPLY_IN_TESTER` | `FORGE_GATE_M5_ADX_HYSTERESIS_APPLY_IN_TESTER` | GATE | tester-only override |

**20 regime/trend/daily/HTF renames** conform to: `FORGE_<scope>_<HTF|M5|DAILY>_<indicator>_<MIN|MAX|FACTOR|ENABLE|...>_<direction?>`.

### §10.5.1b Additional renames — setup-specific knobs backfilled 2026-05-12

`.env.example` coverage audit on 2026-05-12 surfaced 16 FORGE_* keys that were
mapped in `sync_scalper_config_from_env.py` but had no hint in `.env.example`
(9 of them ACTIVE in `.env`). Backfilled in commit `db10e34` under their current
legacy names. To keep the naming-convention migration coherent these 16 are
included in the Phase 2 rename batch alongside the 20 regime knobs above.

The §5 "never rename" rule in `FORGE_NAMING_CONVENTIONS.md` applies to
setup-specific knobs *that the operator already relies on via documented
muscle memory*. These 16 have ZERO documented operator dependence (they were
literally missing from `.env.example` until the backfill); renaming them now,
with backward-compat aliases per §10.5.2, costs ~nothing.

| Current | Proposed | Scope | Notes |
|---|---|---|---|
| `FORGE_BREAKOUT_BLOCK_HID_BULL_SELL` | `FORGE_GATE_BREAKOUT_HID_BULL_DIV_BLOCK_SELL` | GATE | Blocks SELL when RSI_DIV=HID_BULL |
| `FORGE_BREAKOUT_H1H4_CRASH_SELL_MIN_M15_ADX` | `FORGE_ATOM_BREAKOUT_CRASH_BYPASS_M15_ADX_MIN_SELL` | ATOM | M15 ADX floor for crash-sell bypass eligibility |
| `FORGE_BREAKOUT_REQUIRE_H1_MACD_BUY` | `FORGE_GATE_BREAKOUT_H1_MACD_REQUIRE_BUY` | GATE | Mirror of existing `FORGE_GATE_BREAKOUT_H1_MACD_REQUIRE_SELL` pattern |
| `FORGE_BREAKOUT_SAME_DIR_COOLDOWN_SECONDS` | `FORGE_TIMING_BREAKOUT_SAME_DIR_COOLDOWN_SEC` | TIMING | Wall-time cooldown — TIMING scope |
| `FORGE_SELL_STOP_CONT_LEGS` | `FORGE_GEOMETRY_SELL_STOP_CONT_LEGS` | GEOMETRY | Cascade leg count |
| `FORGE_SELL_STOP_CONT_MIN_ADX` | `FORGE_ATOM_SELL_STOP_CONT_M5_ADX_MIN` | ATOM | M5 ADX gate at arm-time |
| `FORGE_SELL_STOP_CONT_REQUIRE_H1_DI` | `FORGE_GATE_SELL_STOP_CONT_H1_DI_REQUIRE` | GATE | H1 DI alignment requirement |
| `FORGE_SELL_STOP_CONT_SL_ATR_MULT` | `FORGE_GEOMETRY_SELL_STOP_CONT_SL_ATR_MULT` | GEOMETRY | SL = entry + ATR × this |
| `FORGE_DUMP_BUY_LOT_FACTOR` | `FORGE_GEOMETRY_DUMP_LOT_FACTOR_BUY` | GEOMETRY | Mirrors existing `FORGE_GEOMETRY_DUMP_LOT_FACTOR` policy (already in naming-conv §4) |
| `FORGE_DUMP_SELL_LOT_FACTOR` | `FORGE_GEOMETRY_DUMP_LOT_FACTOR_SELL` | GEOMETRY | (same pattern) |
| `FORGE_DUMP_SELL_H1_MAX` | `FORGE_ATOM_DUMP_H1_TREND_MAX_SELL` | ATOM | Already cited in `FORGE_NAMING_CONVENTIONS.md §4` line 173 as the target form |
| `FORGE_DUMP_MAX_RSI_BUY` | `FORGE_ATOM_DUMP_RSI_MAX_BUY` | ATOM | Already cited in `FORGE_NAMING_CONVENTIONS.md §4` line 157 |
| `FORGE_NATIVE_FORCE_STAGED_SCALE_IN` | `FORGE_GEOMETRY_STAGED_SCALE_IN_FORCE` | GEOMETRY | Geometry/lot-pipeline behavior |
| `FORGE_NATIVE_LEGS_CLEAR_TREND_FACTOR` | `FORGE_GEOMETRY_LEGS_CLEAR_TREND_FACTOR` | GEOMETRY | Leg-count amplifier when ForgeResolveNumTrades returns clear-trend |
| `FORGE_NATIVE_SCALPER_USE_LIMIT_ENTRY` | `FORGE_GEOMETRY_NATIVE_USE_LIMIT_ENTRY` | GEOMETRY | Entry order-type toggle |
| `FORGE_WAVE_CONFIRMATION_LOT_MULT` | `FORGE_GEOMETRY_WAVE_CONFIRM_LOT_MULT` | GEOMETRY | Wave-atom-confirmation lot amplifier |

**Combined Phase 2 batch: 36 renames** (20 regime + 16 setup-specific backfill).
All 36 conform to `FORGE_<scope>_<setup|HTF|M5|DAILY>_<indicator|param>_<role>_<direction?>` per `FORGE_NAMING_CONVENTIONS.md §4`. Each ships with backward-compatible alias resolution per §10.5.2.

### §10.5.2 Implementation strategy (Phase 2 — v2.7.37)

**Backward-compatible aliases** — old + new names BOTH read by `sync_scalper_config_from_env.py`
for one EA version. Migration script logs a deprecation warning when the OLD name is set.

```python
# In scripts/sync_scalper_config_from_env.py:
LEGACY_ALIASES = {
    # ── Regime/HTF/Daily group (§10.5.1) — 20 ──
    "FORGE_REGIME_H1_OVERRIDE_FACTOR":     "FORGE_ATOM_HTF_H1_STRONG_FACTOR",
    "FORGE_REGIME_H1_OVERRIDE_ADX_MIN":    "FORGE_ATOM_HTF_H1_STRONG_ADX_MIN",
    "FORGE_DAILY_DIRECTION_GATE_ENABLED":  "FORGE_GATE_DAILY_DIRECTION_ENABLE",
    # ... 17 more regime/HTF/daily entries (full list per §10.5.1 table) ...

    # ── Setup-specific backfill group (§10.5.1b, 2026-05-12) — 16 ──
    "FORGE_BREAKOUT_BLOCK_HID_BULL_SELL":          "FORGE_GATE_BREAKOUT_HID_BULL_DIV_BLOCK_SELL",
    "FORGE_BREAKOUT_H1H4_CRASH_SELL_MIN_M15_ADX":  "FORGE_ATOM_BREAKOUT_CRASH_BYPASS_M15_ADX_MIN_SELL",
    "FORGE_BREAKOUT_REQUIRE_H1_MACD_BUY":          "FORGE_GATE_BREAKOUT_H1_MACD_REQUIRE_BUY",
    "FORGE_BREAKOUT_SAME_DIR_COOLDOWN_SECONDS":    "FORGE_TIMING_BREAKOUT_SAME_DIR_COOLDOWN_SEC",
    "FORGE_SELL_STOP_CONT_LEGS":                   "FORGE_GEOMETRY_SELL_STOP_CONT_LEGS",
    "FORGE_SELL_STOP_CONT_MIN_ADX":                "FORGE_ATOM_SELL_STOP_CONT_M5_ADX_MIN",
    "FORGE_SELL_STOP_CONT_REQUIRE_H1_DI":          "FORGE_GATE_SELL_STOP_CONT_H1_DI_REQUIRE",
    "FORGE_SELL_STOP_CONT_SL_ATR_MULT":            "FORGE_GEOMETRY_SELL_STOP_CONT_SL_ATR_MULT",
    "FORGE_DUMP_BUY_LOT_FACTOR":                   "FORGE_GEOMETRY_DUMP_LOT_FACTOR_BUY",
    "FORGE_DUMP_SELL_LOT_FACTOR":                  "FORGE_GEOMETRY_DUMP_LOT_FACTOR_SELL",
    "FORGE_DUMP_SELL_H1_MAX":                      "FORGE_ATOM_DUMP_H1_TREND_MAX_SELL",
    "FORGE_DUMP_MAX_RSI_BUY":                      "FORGE_ATOM_DUMP_RSI_MAX_BUY",
    "FORGE_NATIVE_FORCE_STAGED_SCALE_IN":          "FORGE_GEOMETRY_STAGED_SCALE_IN_FORCE",
    "FORGE_NATIVE_LEGS_CLEAR_TREND_FACTOR":        "FORGE_GEOMETRY_LEGS_CLEAR_TREND_FACTOR",
    "FORGE_NATIVE_SCALPER_USE_LIMIT_ENTRY":        "FORGE_GEOMETRY_NATIVE_USE_LIMIT_ENTRY",
    "FORGE_WAVE_CONFIRMATION_LOT_MULT":            "FORGE_GEOMETRY_WAVE_CONFIRM_LOT_MULT",
}
# Total: 36 legacy → modern aliases.
# When sync runs:
#   if NEW name is set → use NEW value
#   elif OLD name is set → use OLD value + log deprecation warning
#   else → use defaults
```

This lets us:
1. Ship v2.7.37 with new names in `scalper_config.json` and EA struct fields
2. Old `.env` files keep working (alias resolution)
3. Operator updates `.env` at their pace
4. v2.7.39+: remove legacy alias support (logs become errors)

### §10.5.2b Python-app safety audit (verified 2026-05-12)

**Operator constraint**: "don't touch anything used by the Python apps."

**Audit result: ZERO Python apps touch any of the 36 knobs** (20 regime + 16 setup-specific
backfill). The rename is guaranteed Python-safe. Three independent verification queries
across both groups:

```bash
# Query 1 — any Python file reading the 36 env-var NAMES directly:
for KNOB in <36 knob names>; do
  grep -rl "$KNOB" /Users/olasumbo/signal_system/python/ 2>/dev/null
done
# Result: zero hits in python/ for all 36

# Query 2 — any Python file reading the resulting JSON keys (daily_direction_gate_enabled,
# breakout_block_hid_bull_sell, dump_sell_lot_factor, sell_stop_cont_*, wave_confirmation_*):
grep -rE "daily_direction_gate_enabled|regime_h1_override_factor|h4_rsi_gate_enabled|adx_hysteresis_enabled|adx_trend_enter|block_hid_bull_sell|h1h4_crash_sell_min_m15_adx|require_h1_macd_buy|same_dir_cooldown_seconds|sell_stop_cont_legs|sell_stop_cont_min_adx|dump_buy_lot_factor|dump_sell_lot_factor|dump_sell_h1_max|dump_max_rsi_buy|wave_confirmation_lot_mult" /Users/olasumbo/signal_system/python/
# Result: zero hits

# Query 3 — Python files that DO read scalper_config.json (3 of them):
#   athena_api.py, aurum.py, bridge.py
# Checked each for any of the 36 keys: ZERO matches.
# (They read other sections — lot_sizing.fixed_lot, news_filter, etc. — but not the renamed knobs.)
```

**2026-05-12 second pass** (post-backfill): re-verified the 16 setup-specific
backfill knobs via the same query pattern. All Python-safe. Audit log in
commit `db10e34` and `FORGE_NAMING_CONVENTIONS.md §4` (mirror entries).

**Why this matters**: the rename touches ONLY:
- `.env` (operator's local file)
- `.env.example` (documentation)
- `scripts/sync_scalper_config_from_env.py` (mapping table)

The lowercase JSON keys in `scalper_config.json` (e.g., `daily_direction_gate_enabled`)
**do NOT change**. The EA reads the same JSON keys. Python apps that touch
`scalper_config.json` continue to read whatever they were reading before.

Commands logged to `docs/FORGE_INDICATOR_ATLAS.md §13` for reproducibility.

### §10.5.2c Python-contract preservation — explicit guarantee

Verified 2026-05-12: operator constraint extends to:
- `config/scalper_config.json` (active config — Python apps consume this)
- `config/scalper_config.defaults.json` (defaults — fallback values)
- `scripts/sync_scalper_config_from_env.py` validation/screening logic

**What is guaranteed to STAY THE SAME** (no changes whatsoever):

#### A. `scalper_config.json` keys (lowercase, in `safety` + `bb_breakout` sections)
```
safety section:
  adx_hysteresis_enabled         adx_hysteresis_apply_in_tester
  adx_trend_enter                adx_trend_exit
  daily_direction_gate_enabled   daily_sma_period
  daily_sma_lookback_days        daily_slope_block_atr
  daily_move_block_atr           daily_move_flip_hysteresis
  daily_cancel_pending_on_flip   daily_cancel_includes_cascade
  regime_h1_override_factor      regime_h1_override_adx_min

bb_breakout section:
  h4_rsi_gate_enabled            h4_rsi_sell_max
  h4_rsi_buy_min                 h4_adx_gate_enabled
  h4_adx_min_sell                h4_adx_min_buy
```

#### B. `scalper_config.defaults.json` keys
Identical to above. Defaults stay the same; just the env-var name that POPULATES them changes.

#### C. `sync_scalper_config_from_env.py` core functions (12 of them — unchanged)
```
_env_raw         _env_key_used    _load_env
_parse_value     _clamp           _atomic_write_json
_lot_sizing_drop_num_trades       apply_scalper_env_overrides
_sync_to_mt5     _stamp_version   main
```

#### D. Python apps that read `scalper_config.json`
- `python/bridge.py` — verified does not read any of the 20 keys
- `python/aurum.py` — verified
- `python/athena_api.py` — verified

#### E. The EA reads from `scalper_config.json`
- `JsonHasKey(content, "daily_direction_gate_enabled")` — unchanged
- `JsonGetDouble(content, "regime_h1_override_factor")` — unchanged
- Etc. The EA NEVER sees the env-var name; only the JSON key.

**What CHANGES** (narrowly scoped):

| File | Lines changed | What changes |
|---|---|---|
| `.env` | 14 lines | Env-var name on LEFT of `=` only. Value unchanged. |
| `.env.example` | 20 lines | Same — env-var documentation only. |
| `sync_scalper_config_from_env.py` (mapping table) | 20 lines + 1 new dict | ENV name as dict key changes. The (section, json_key, type, min, max) tuple is **byte-identical**. Add 1 new `LEGACY_ALIASES` dict. |

**No core sync logic, no JSON keys, no Python app code, no EA code is touched.**

### §10.5.3 What does NOT get renamed (grandfathered)

Per `FORGE_NAMING_CONVENTIONS.md §5`, the following are NOT renamed in this iteration:

- All 56 `FORGE_BREAKOUT_*` knobs (would require touching BB_BREAKOUT filter chain — out of scope)
- All `FORGE_BOUNCE_*`, `FORGE_DUMP_*`, `FORGE_PULLBACK_SCALP_*` knobs (setup-specific, not regime-related)
- `FORGE_FIXED_LOT`, `FORGE_MAX_NUM_TRADES`, etc. (system-wide, not regime concept)
- News filter knobs (separate subsystem)

If those need renaming later, it's a separate migration alongside their respective struct
refactor (BREAKOUT struct refactor, news filter refactor, etc.).

### §10.5.4 Phase 2 PR scope

When v2.7.37 ships:

| File | Changes |
|---|---|
| `.env` (active) | Replace 14 active regime knobs with new names; keep old as commented-out for grace period |
| `.env.example` | Replace all 20 with new names; remove old entries; add new `# Renamed in v2.7.37 (was: OLD_NAME)` comment per entry |
| `scripts/sync_scalper_config_from_env.py` | Add 20 NEW mappings + `LEGACY_ALIASES` table |
| `config/scalper_config.json` | Auto-regenerated by sync — keys stay the same (lowercase config keys aren't renamed; only ENV keys change) |
| `ea/FORGE.mq5` | NO changes to JSON-key reads (config keys unchanged); only env-var-name changes via sync |
| `tests/api/test_forge_27x_gates.py` | Update FORGE_ENV_VARS_NOT_IN_SYNC test list with new names |

**Net impact on EA**: ZERO code change. The renames are purely at the `.env` → sync-mapping
layer. The EA still reads `scalper_config.daily_direction_gate_enabled` (lowercase JSON key)
regardless of whether the ENV var is `FORGE_DAILY_DIRECTION_GATE_ENABLED` or
`FORGE_GATE_DAILY_DIRECTION_ENABLE`.

### §10.5.5 Operator workflow during migration

After Phase 2 ships:

1. Operator's existing `.env` keeps working (legacy aliases active)
2. Operator updates `.env` at their pace (find/replace 20 lines)
3. Next `make forge-compile` shows zero deprecation warnings → migration complete for this `.env`
4. v2.7.39: legacy aliases removed; operators with un-updated `.env` see hard error pointing to new names

This is the same strangler-fig pattern as the struct refactor — additive Phase 2, migrate at leisure, cleanup in Phase 4.

---

## §11. Time-of-day classifier — ICT killzones (Layer 5 atom)

**Status**: design approved 2026-05-12. Implementation target: v2.7.37 alongside Phase 2 struct rollout.

**Source-of-truth research doc**: [`docs/research/ICT_KILLZONES.md`](docs/research/ICT_KILLZONES.md) — 13 cross-confirmed sources, MQL5 reference code, validation checklist. Always read that doc before changing killzone behavior.

### §11.1 Why killzones live in Layer 5

The existing Layer 5 field `session` is a broad bucket (LONDON / NY / ASIA / OFF). ICT killzones are the **finer-grained sub-windows inside those sessions** where institutional volume actually clusters. Same conceptual layer, narrower precision. Composites need both: `session` for coarse "are we in NY at all," `killzone` for "are we in the prime 60-70%-of-daily-range window."

### §11.2 Killzone reference table (XAUUSD-tuned)

Anchored to NY-local time so DST is handled by the timezone itself. From research doc §2.2:

| Killzone (gold) | NY Time         | What gold typically does                                                | Typical move size               |
|-----------------|-----------------|-------------------------------------------------------------------------|---------------------------------|
| Asian KZ        | 20:00 – 00:00   | Accumulation, false breakouts, Asian-range high/low set                 | Low — < 30 pips most days       |
| London Open KZ  | 02:00 – 05:00   | **Judas Swing** ≈ 02:30 sweeps Asian high/low, then reversal            | 50 – 100 pips per candle        |
| NY Open KZ      | 07:00 – 10:00   | Continuation OR reversal of London move; biggest daily move often here  | 50 – 150 pips during overlap    |
| London Close KZ | 10:00 – 12:00   | Profit-taking, retracement to daily mean, reversal of morning trend     | 30 – 60 pips of retrace         |

**Gold prime window**: London-NY overlap (≈ 13:00 – 17:00 GMT) carries **60-70% of gold's daily range** (EBC Financial, TradingView ProjectSyndicate 2025 edition). FORGE prioritizes this window.

### §11.3 RegimeState struct extension — Layer 5

Adds 2 fields to the approved `RegimeState` struct (§3):

```mql5
struct RegimeState {
   // ... Layers 1-4 unchanged ...

   // Layer 5: Session / killzone / news context
   string session;              // existing — LONDON, NY, ASIA, OFF
   string killzone;             // NEW — ASIAN_KZ, LONDON_OPEN_KZ, NY_OPEN_KZ, LONDON_CLOSE_KZ, OFF_KZ
   int    minutes_into_kz;      // NEW — minutes since current killzone started (for first-60-min Judas detection)
   bool   news_active;
};
```

Struct grows from 14 → 16 fields. No other layer touched.

**Atom usage examples**:

```mql5
bool in_prime_window = (g_regime.killzone == "NY_OPEN_KZ"
                     || g_regime.killzone == "LONDON_CLOSE_KZ");

bool judas_swing_risk = (g_regime.killzone == "LONDON_OPEN_KZ"
                     && g_regime.minutes_into_kz < 60);

bool gold_active = (g_regime.killzone != "OFF_KZ"
                 && g_regime.killzone != "ASIAN_KZ");
```

### §11.4 Killzone-as-atom in composite specs

Each Tier 1 composite (per `FORGE_COMPOSITE_ROADMAP.md`) gets a killzone-aware refinement:

| Composite                  | Killzone gating / amplification                                             |
|----------------------------|-----------------------------------------------------------------------------|
| `BULL_DAY_DIP_BUY`         | Amplify lot ×1.5 inside prime window (`NY_OPEN_KZ` ∪ `LONDON_CLOSE_KZ`)     |
| `INTRADAY_REVERSAL_SELL`   | Only fire inside `NY_OPEN_KZ` ∪ `LONDON_CLOSE_KZ` (institutional flip)      |
| `MOMENTUM_DUMP_SELL`       | Add caution filter in first 60 min of `LONDON_OPEN_KZ` (Judas Swing risk)   |
| `BLOCK_SELL_IN_CHOP`       | Always-on regardless of killzone                                            |
| `CHOP_LADDER_BUY_GRID`     | Disable inside `LONDON_CLOSE_KZ` (institutions square — reversal risk)      |

### §11.5 Per-killzone trade caps (new gate code candidate)

Adding `MaxTradesPerKZ` as an env knob + `killzone_trade_cap` as a new entry in `gate_legend.json` prevents over-trading the same window. Default 3-5 per killzone. **Defer to v2.7.38** — not v2.7.36 / v2.7.37 scope. Logged here as a known follow-up.

### §11.6 Logging mandate — `killzone` column in SIGNALS

The v2.7.36 SIGNALS schema extension (`docs/FORGE_LOGGING_EXTENSION_DESIGN.md`) should add `killzone TEXT DEFAULT 'OFF_KZ'` as a new column. Mandatory for retrospective composite validation against the Mar 31 → Apr 8 case study — without it, we can't tell whether a given TAKEN entry landed in the prime window or a low-edge bucket.

**Migration**:
```sql
ALTER TABLE SIGNALS ADD COLUMN killzone TEXT DEFAULT 'OFF_KZ';
ALTER TABLE SIGNALS ADD COLUMN minutes_into_kz INTEGER DEFAULT 0;
```

Bridge mirror (`python/bridge.py`):
```sql
ALTER TABLE forge_signals ADD COLUMN killzone TEXT DEFAULT 'OFF_KZ';
ALTER TABLE forge_signals ADD COLUMN minutes_into_kz INTEGER DEFAULT 0;
```

### §11.7 DST handling — reference implementation

Two MQL5 approaches documented in `docs/research/ICT_KILLZONES.md` §5:

- **Approach A** (`TimeGMT()`-based): recommended for live trading. DST detection for US (2nd Sun Mar → 1st Sun Nov) baked in.
- **Approach B** (manual broker-offset inputs + EU DST detection): recommended for FORGE because Strategy Tester's `TimeGMT()` behavior is less reliable than live. Works identically in both environments.

FORGE will adopt **Approach B** by default; Approach A is the live-trading fallback for the eventual live-broker deployment.

### §11.8 Validation checklist (mandatory before v2.7.37 ships)

Mirrored from research doc §9 — must all pass before killzone code merges:

| # | Check                                                                          |
|---|--------------------------------------------------------------------------------|
| 1 | NY time correct in live + tester (print `TimeGMT() / TimeCurrent() / GetNYTimeNow()` at OnInit) |
| 2 | DST flips work both directions (tester across 2nd Sun Mar + 1st Sun Nov)       |
| 3 | Killzone transitions logged (exactly 4 transitions per weekday)                |
| 4 | No off-by-one at boundaries (10:00 NY: only one killzone active)               |
| 5 | Weekend handling (`GetActiveKillzone() == KZ_NONE` Saturday + early Sunday)    |
| 6 | Cross-day backtest of FORGE existing TAKEN trades (Mar 31 → Apr 8 case study)  |

### §11.9 Cross-references

- **Research doc**: `docs/research/ICT_KILLZONES.md` — full citation set, MQL5 reference code, Judas Swing detail
- **Composite Roadmap**: `FORGE_COMPOSITE_ROADMAP.md` — killzone-aware composite gating extensions added per §11.4
- **Logging Design**: `docs/FORGE_LOGGING_EXTENSION_DESIGN.md` — `killzone` column added per §11.6
- **Naming Conventions**: `FORGE_NAMING_CONVENTIONS.md` — `KILLZONE_*` prefix policy slot (open — to be added in next naming-conv update)
- **Decision Stack**: `FORGE_DECISION_STACK.md` — Layer 5 atoms now include `g_regime.killzone`

---

## §12. Changelog

| Date | Change |
|---|---|
| 2026-05-12 | Initial taxonomy created. 56 regime/trend variables inventoried across 4 categories. Structural overlap identified (3-4 answers per question). Proposed `RegimeState` struct with 13 fields collapsing ~20 globals + 10 locals. Phased migration plan (Phase 1 = no refactor, Phase 2 = additive, Phase 3 = migrate callers, Phase 4 = cleanup). Industry terminology research kicked off (open question §7.1 + §9). |
| 2026-05-12 | **§3 RegimeState struct shape APPROVED by operator** — 5 layers, 13 fields, intraday/macro divergence as built-in concept. Field NAMES still pending §9 industry-terminology research outcome. Structure locked: Layer 1 macro (3) + Layer 2 intraday (3 incl. divergence bool) + Layer 3 daily (4) + Layer 4 volatility (2) + Layer 5 session/news (2) = 14 fields total. Phase 2 implementation target = v2.7.37 (after v2.7.36 V3 composites validate the loop). |
| 2026-05-11 | Industry-terminology research complete — see `docs/RESEARCH_NOTES_regime_terminology.md`. Findings: 1 strong rename recommended (`intraday_vs_macro_diverged` -> `intraday_counter_macro`; "divergence" canonically means RSI/MACD-vs-price per Babypips/Elliott/Murphy, not timeframe-conflict — canonical term is "counter-trend"). 1 optional rename (`macro_label` -> `htf_label` for MTF-vocabulary consistency — defer to Phase 2 PR review). 3 fields keep names: `intraday_label`, `daily_slope_atr`, `high_vol` align with Murphy/Weinstein/Bollinger canonical concepts. Closes open question §7.1. |
| 2026-05-12 | **Both renames applied** after operator review. `macro_*` → `htf_*` cascade across 4 fields (`macro_label/confidence/h1_strong` + `intraday_counter_macro`). New §2.6 glossary added explaining HTF/MTF/LTF vocabulary inline for future readers. All §3 code examples + §5 migration steps + §8 cross-references updated. Field names now FROZEN for Phase 2. |
| 2026-05-12 | **§10.5 Env-knob rename plan added** — 20 regime-related FORGE_* knobs in scope for Phase 2 rename (14 active + 6 documented-only). Mapping table aligns each to FORGE_NAMING_CONVENTIONS.md §4 policy (ATOM/GATE prefixes, HTF vocabulary, direction at end). Implementation strategy: backward-compatible aliases for one EA version (v2.7.37) then hard-cut in v2.7.39. NO EA code changes required — purely .env → sync-mapping layer. Cross-referenced from FORGE_NAMING_CONVENTIONS.md §5. |
| 2026-05-12 | **§11 ICT killzones added as Layer 5 atom**. RegimeState struct grows 14 → 16 fields (`killzone` + `minutes_into_kz`). XAUUSD-tuned killzone table (gold prime window = London-NY overlap = 60-70% of daily range per EBC/TradingView ProjectSyndicate). Judas Swing pattern documented (02:30 NY first 60 min of London Open KZ). 5 killzone-aware composite refinements specified (BULL_DAY_DIP_BUY ×1.5 amplifier in prime window; INTRADAY_REVERSAL_SELL gated to NY_OPEN/LONDON_CLOSE; MOMENTUM_DUMP_SELL caution filter in Judas window; CHOP_LADDER_BUY_GRID disabled in London Close; BLOCK_SELL_IN_CHOP always-on). v2.7.36 logging mandate: add `killzone` + `minutes_into_kz` columns to SIGNALS + scribe forge_signals. Implementation target v2.7.37. Per-killzone trade caps deferred to v2.7.38. Full research with 13 sources in `docs/research/ICT_KILLZONES.md`. |
| 2026-05-12 | **§10.5.1b added — Phase 2 rename batch grows 20 → 36 knobs.** `.env.example` coverage audit on 2026-05-12 surfaced 16 FORGE_* keys mapped in `sync_scalper_config_from_env.py` but missing from `.env.example` (9 ACTIVE in `.env`, never documented). Backfilled in commit `db10e34` under legacy names + added to the Phase 2 rename plan. Categories: 4 BB_BREAKOUT additional gates, 4 SELL_STOP_CONT cascade knobs, 4 MOMENTUM_DUMP per-direction overrides, 4 lot-sizing internals. 4 of the 16 use names already cited as canonical examples in `FORGE_NAMING_CONVENTIONS.md §4` (`FORGE_GEOMETRY_DUMP_LOT_FACTOR*`, `FORGE_ATOM_DUMP_RSI_MAX_BUY`, `FORGE_ATOM_DUMP_H1_TREND_MAX_SELL`). Python-safety re-verified — zero hits across all 36. LEGACY_ALIASES dict in §10.5.2 expanded accordingly. SKILL.md gained Mandatory Check C to prevent recurrence. |
