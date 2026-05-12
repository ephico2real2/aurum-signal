# FORGE Naming Conventions — Config Surface Audit + Policy

**Purpose**: Audit of existing FORGE config knobs (`.env` + `scalper_config.json` + EA struct
fields), identification of naming inconsistencies, and a forward-going policy aligned with
the Decision Stack terminology.

**Created**: 2026-05-12
**Living document**: update when new naming patterns introduced, when inconsistencies are
fixed, or when new categories of knobs emerge. Skill mandates this.

---

## §1. Current state — 146 FORGE_* env knobs

| Setup prefix | Count |
|---|---|
| `FORGE_BREAKOUT_*` | 56 |
| `FORGE_NEWS_*` | 16 |
| `FORGE_DUMP_*` | 11 (+SELL/BUY variants below) |
| `FORGE_SELL_*` | 11 (mixed — some BREAKOUT direction-specific, some SELL_STOP_CONT) |
| `FORGE_PULLBACK_*` | 8 |
| `FORGE_H4_*` | 6 |
| `FORGE_BOUNCE_*` | 6 |
| `FORGE_BUY_*` | 5 (BUY_LIMIT_RECOVERY) |
| Other | balance |

| Suffix pattern | Count | Semantic |
|---|---|---|
| `_MULT` | 19 | multiplier |
| `_ENABLED` | 14 | bool toggle |
| `_FACTOR` | 11 | multiplier |
| `_REQUIRE_*` | 15 | bool requirement (filter chain gate) |
| `_BARS` | 7 | timing |
| `_MIN/MAX/THRESHOLD` | 15 | atom threshold |
| `_PCT` | 4 | percentage |
| `_RSI/_ADX/_PSAR/_MACD` | 10+ | indicator-specific |

---

## §2. Identified inconsistencies

### 2.1 `_MULT` vs `_FACTOR` (synonyms, 30 knobs total)

Both mean "multiplier applied to a base value." No semantic difference, just word choice
inconsistency.

```
FORGE_BREAKOUT_TP1_ATR_MULT          ← MULT
FORGE_BREAKOUT_SELL_LIMIT_LOT_FACTOR ← FACTOR
FORGE_DUMP_LOT_FACTOR                ← FACTOR
FORGE_WAVE_CONFIRMATION_LOT_MULT     ← MULT
```

**Pattern observed**: `_ATR_MULT` (when multiplied by ATR), `_LOT_FACTOR` (when multiplied
by lot). Looks like an emerging convention: MULT for indicator-multipliers, FACTOR for
lot-multipliers. Could be formalized.

### 2.2 `_REQUIRE_*` vs `_BLOCK_*` vs `_ENABLED` (gate toggle inconsistency)

Three different patterns for "is this gate active?":

```
FORGE_DUMP_REQUIRE_PSAR=1              ← REQUIRE (positive — must have)
FORGE_BREAKOUT_BLOCK_HID_BULL_SELL=1   ← BLOCK   (negative — reject if)
FORGE_DAILY_DIRECTION_GATE_ENABLED=1   ← ENABLED (master toggle)
```

These do similar things (gate is on/off) but use 3 different verbs. Hard to scan mentally.

### 2.3 Direction suffix position varies

```
FORGE_BREAKOUT_TP1_BUY_ATR_MULT        ← BUY in middle
FORGE_BREAKOUT_REQUIRE_H1_DI_BUY       ← BUY at end
FORGE_BREAKOUT_BLOCK_HID_BULL_SELL     ← SELL at end
FORGE_DUMP_SELL_H1_MAX                 ← SELL in middle (NEW knob from v2.7.35)
FORGE_DUMP_MAX_RSI_BUY                 ← BUY at end (NEW knob from v2.7.34)
```

Same direction qualifier, 4 different positions. Future readers can't predict where to
look.

### 2.4 Setup-specific vs global knob distinction

No visual hierarchy of scope:

```
FORGE_DAILY_DIRECTION_GATE_ENABLED     ← global (applies to ALL setups)
FORGE_DUMP_CATCH_ENABLED               ← setup-specific (MOMENTUM_DUMP only)
FORGE_BREAKOUT_BUY_SL_ATR_MULT         ← setup + direction-specific
```

Reader can't tell at a glance which is which without context.

### 2.5 `_ENABLED` applied to 3 different things

```
FORGE_DUMP_CATCH_ENABLED               ← whole setup type ON/OFF
FORGE_BREAKOUT_TP2_SL_RATCHET_ENABLED  ← a feature within a setup
FORGE_H4_RSI_GATE_ENABLED              ← a filter chain gate
```

Same suffix, three different things in the Decision Stack hierarchy.

### 2.6 Setup-trigger params vs filter-chain params mixed

```
FORGE_DUMP_LOOKBACK_BARS=3             ← TRIGGER param (when does dump fire?)
FORGE_DUMP_ATR_MULT=1.0                ← TRIGGER param (impulse threshold)
FORGE_DUMP_MAX_RSI=41                  ← FILTER param (gate inside filter chain)
FORGE_DUMP_REQUIRE_PSAR=1              ← FILTER param (gate inside filter chain)
```

No way to tell from the name whether a knob configures the TRIGGER or the FILTER CHAIN.

---

## §3. Decision Stack mapping — what each knob actually configures

Cross-referencing the 5-layer architecture from `FORGE_DECISION_STACK.md`:

| Decision Stack layer | Knob role | Current pattern examples |
|---|---|---|
| **Setup Trigger** (`*_trig` boolean) | Trigger parameters | `FORGE_DUMP_LOOKBACK_BARS`, `FORGE_DUMP_ATR_MULT` |
| **Filter Chain** (gates in if/else-if) | Gate ON/OFF toggle | `FORGE_DUMP_REQUIRE_PSAR`, `FORGE_DAILY_DIRECTION_GATE_ENABLED` |
| **Boolean Composite** (logical formula) | Composite enable/disable | `FORGE_BULL_DAY_DIP_BUY_ENABLED` (planned v2.7.36) |
| **Atom** (predicate) | Threshold values | `FORGE_DUMP_MAX_RSI=41`, `FORGE_BREAKOUT_ADX_MIN=20` |
| **Entry Geometry** | SL/TP/lot multipliers | `FORGE_BREAKOUT_TP1_ATR_MULT`, `FORGE_DUMP_LOT_FACTOR` |
| **Cooldowns / timing** | Time-based | `FORGE_DUMP_COOLDOWN_SECONDS`, `FORGE_PULLBACK_SCALP_FRESH_FLIP_BARS` |
| **Setup Type ENABLE** | Whole setup ON/OFF | `FORGE_DUMP_CATCH_ENABLED`, `FORGE_PULLBACK_SCALP_ENABLED` |
| **System / global** | Account-wide settings | `FORGE_FIXED_LOT`, `FORGE_MAX_NUM_TRADES` |

---

## §4. Going-forward naming policy (apply to NEW knobs)

### 4.1 Standard prefix hierarchy

```
FORGE_<scope>_<setup>_<role>_<param>_<direction?>

scope     ∈ { SETUP, COMPOSITE, GATE, ATOM, GEOMETRY, GLOBAL, TIMING }
setup     ∈ { BREAKOUT, BOUNCE, DUMP, PULLBACK_SCALP, BULL_DAY_DIP, ... } (omit if scope=GLOBAL)
role      ∈ { ENABLE, REQUIRE, BLOCK, MAX, MIN, MULT, FACTOR, PCT, BARS, SECONDS }
param     ∈ indicator/property (RSI, ADX, ATR, PSAR, MACD, H1_TREND, etc.)
direction ∈ { BUY, SELL } (always LAST, optional)
```

**Recommended examples**:

| Purpose | Old name | Proposed pattern (new knobs only) |
|---|---|---|
| Enable a whole setup type | `FORGE_DUMP_CATCH_ENABLED` | `FORGE_SETUP_DUMP_ENABLE` |
| Enable a composite | (v2.7.36 new) | `FORGE_COMPOSITE_BULL_DAY_DIP_BUY_ENABLE` |
| Gate inside filter chain | `FORGE_DUMP_REQUIRE_PSAR` | `FORGE_GATE_DUMP_PSAR_REQUIRE` |
| Atom threshold | `FORGE_DUMP_MAX_RSI` | `FORGE_ATOM_DUMP_RSI_MAX_SELL` |
| Atom threshold (BUY mirror) | `FORGE_DUMP_MAX_RSI_BUY` | `FORGE_ATOM_DUMP_RSI_MAX_BUY` |
| Lot factor | `FORGE_DUMP_LOT_FACTOR` | `FORGE_GEOMETRY_DUMP_LOT_FACTOR` |
| TP ATR multiplier | `FORGE_BREAKOUT_TP1_ATR_MULT` | `FORGE_GEOMETRY_BREAKOUT_TP1_ATR_MULT_BUY` (if needed) |
| Cooldown | `FORGE_DUMP_COOLDOWN_SECONDS` | `FORGE_TIMING_DUMP_COOLDOWN_SECONDS` |

### 4.2 Direction suffix rule

**Direction (BUY/SELL) is always the LAST segment.** No exceptions.

```
✓ FORGE_BREAKOUT_REQUIRE_H1_DI_BUY        ← direction at end ✓
✗ FORGE_BREAKOUT_TP1_BUY_ATR_MULT          ← direction in middle ✗
✗ FORGE_DUMP_SELL_H1_MAX                   ← direction in middle ✗

Future:
✓ FORGE_GEOMETRY_BREAKOUT_TP1_ATR_MULT_BUY
✓ FORGE_ATOM_DUMP_H1_TREND_MAX_SELL
```

### 4.3 `_MULT` vs `_FACTOR` — pick ONE

**Proposed**: keep both, but enforce semantic distinction:
- `_MULT` = multiplier of a price-derived value (ATR, points, pips)
- `_FACTOR` = multiplier of a lot value (lot, position size)

```
✓ FORGE_GEOMETRY_BREAKOUT_TP1_ATR_MULT      (multiplier on ATR)
✓ FORGE_GEOMETRY_DUMP_LOT_FACTOR             (multiplier on lot)
✗ FORGE_BREAKOUT_SELL_LIMIT_ATR_MULT         (current — uses MULT correctly)
✗ FORGE_BREAKOUT_SELL_LIMIT_LOT_FACTOR       (current — uses FACTOR correctly)
```

(Most current knobs already follow this rule — formalize it as policy.)

### 4.4 Gate toggle verbs

Pick ONE verb pattern for gate ON/OFF and stick to it:

**Proposed**: `_ENABLE` for master toggles (setup, composite), `_REQUIRE` for filter-chain
gates (atom must be TRUE), `_BLOCK` only for explicit reject semantics.

```
✓ FORGE_SETUP_DUMP_ENABLE                    ← turn whole setup on/off
✓ FORGE_GATE_DUMP_PSAR_REQUIRE               ← PSAR alignment required to enter
✓ FORGE_GATE_DUMP_H1_TREND_BLOCK_SELL_MAX    ← explicit "block SELL if h1_trend exceeds X"
```

### 4.6 Timeframe vocabulary — HTF / MTF / LTF (not "macro" / "intraday" mix)

When a knob name references a timeframe range, use the canonical MTF (multi-timeframe)
trading vocabulary:

| Abbreviation | Meaning | Use in knob names for |
|---|---|---|
| **HTF** | Higher Time Frame | H1 + H4 — previously called "macro" |
| **MTF** | Middle Time Frame | M15 + M30 |
| **LTF** | Lower Time Frame | M1 + M5 (execution) |

Examples (NEW knobs only — old knobs grandfathered):

```
✓ FORGE_ATOM_HTF_H1_STRONG_FACTOR        (H1 trend strength threshold in HTF context)
✓ FORGE_ATOM_HTF_H4_RSI_MAX_SELL          (H4 RSI sell ceiling)
✓ FORGE_GATE_M5_ADX_HYSTERESIS_ENABLE     (M5-scoped LTF gate)
✓ FORGE_ATOM_DAILY_SLOPE_BLOCK_ATR        (D1 — keep "DAILY" for clarity, no MTF abbreviation)

✗ FORGE_ATOM_MACRO_TREND_THRESHOLD        (macro = ambiguous, borrowed from economics)
✗ FORGE_ATOM_INTRADAY_HTF_TREND           (mixed vocab — pick one)
```

**Why HTF over "macro"**: per `docs/RESEARCH_NOTES_regime_terminology.md`, "macro" in finance
often means macroeconomic data (Fed, GDP, CPI); HTF unambiguously means "higher chart
timeframe." Murphy / Tradeciety / Markets4you / modern intraday literature use HTF/MTF/LTF.

**Note**: For day-1 timeframe (D1), prefer the spelled-out "DAILY" over "HTF" because
"daily" reads cleaner and HTF could include H1-H4 too. The DAILY_ prefix is its own
recognized scope alongside HTF.

Full vocabulary glossary in [`FORGE_REGIME_TAXONOMY.md §2.6`](FORGE_REGIME_TAXONOMY.md).

### 4.7 Gate Code naming policy (`config/gate_legend.json`)

Gate codes are the Decision Stack §2.4 layer — the string emitted as `SIGNALS.gate_reason`
when a filter chain rung blocks an entry. Current state (verified 2026-05-12):

**65 gate codes + 2 meta entries** with several inconsistencies:

| Inconsistency | Examples |
|---|---|
| `_block` vs `_blocked` (5 vs 4) — same meaning, two spellings | `dump_chop_block` vs `entry_quality_h4_adx_buy_blocked` |
| Direction-suffix position varies | `entry_quality_daily_bear_block_buy` (end) vs `entry_quality_h4_adx_buy_blocked` (middle) |
| Threshold verbs scattered: `_ceil` / `_cap` / `_floor` / `_max` / `_min` | `dump_rsi_buy_ceil`, `entry_quality_direction_cap`, `entry_quality_rsi_sell_floor` |
| `entry_quality_*` is generic — used for BB_BREAKOUT, BB_BOUNCE, BB_PULLBACK_SCALP without distinction | `entry_quality_psar_misalign_buy` could be from any setup |
| MOMENTUM_DUMP gets its own `dump_*` prefix, others don't | inconsistent — readers can't tell from a `entry_quality_*` code which SETUP emitted it |

**Going-forward gate code policy** (apply to NEW codes):

```
<setup_or_composite>_<gate_concept>_<direction?>

setup        ∈ { breakout, bounce, dump, pullback_scalp, bull_day_dip_buy, intraday_reversal_sell, ... }
              — explicit setup or composite name (NOT generic "entry_quality_")
gate_concept ∈ what's being checked (rsi_ceil, adx_min, psar_misalign, body, fib_below, etc.)
direction    ∈ { buy, sell } (LAST, optional)
```

**Verb policy**:
- Use `_block` (not `_blocked`) — past-participle short form is the convention
- For threshold violations, use the boundary word that names the threshold (`_max`, `_min`, `_ceil`, `_floor`, `_above`, `_below`) — don't add `_block` redundantly. The fact that a code in `gate_reason` means "blocked" is implicit.

**Examples** (NEW codes — apply to v2.7.36 V3 composites and beyond):

| Composite / setup | Gate code (new style) | What it means |
|---|---|---|
| BULL_DAY_DIP_BUY | `bull_day_dip_buy_rsi_above` | RSI above the 50 dip-zone ceiling |
| BULL_DAY_DIP_BUY | `bull_day_dip_buy_fib_below` | price below Fib 50 − ATR/2 |
| BULL_DAY_DIP_BUY | `bull_day_dip_buy_lh_cascade` | 3-bar lower-highs cascade present |
| INTRADAY_REVERSAL_SELL | `intraday_reversal_sell_rsi_above` | RSI above 40 weakness threshold |
| BLOCK_SELL_IN_CHOP | `block_sell_in_chop` | universal SELL-in-RANGE block |
| FRACTIONAL_SELL_IN_BULL | `fractional_sell_in_bull` (TAKEN path) or `fractional_sell_in_bull_no_setup` (gated) | counter-regime probe outcome |
| BB_BREAKOUT | `breakout_psar_misalign_buy` | PSAR not bullish-aligned for BB_BREAKOUT BUY (NEW style; current `entry_quality_psar_misalign_buy` grandfathered) |
| BB_BOUNCE | `bounce_psar_misalign_buy` | same atom, different setup |
| MOMENTUM_DUMP | `dump_psar_block` | already conforms |

**Migration strategy** (mirror env-knob approach):

- **Default**: existing 65 codes grandfathered (renaming breaks all historical SIGNALS analytics that filter by `gate_reason`)
- **NEW codes** follow §4.7 policy starting v2.7.36
- **Scoped exception**: if a setup/composite is refactored, its gate codes may be renamed in the same PR with `LEGACY_GATE_ALIASES` in `gate_legend.json` `_patterns` section (similar to env-knob aliases)

**Cross-setup convention**: when the same indicator-condition is used as a gate across
multiple setups (e.g., RSI ceiling), each setup gets its own gate code (`bull_day_dip_buy_rsi_above`,
`bounce_rsi_above`, `dump_rsi_buy_ceil`) — NOT a shared `rsi_above` code. Why: post-mortem
queries often want to know which setup tried to fire; the setup name in the gate code
makes that immediately visible in `gate_reason` queries.

### 4.5 `_ATOM_` vs `_GEOMETRY_` prefix distinction

Make it explicit at a glance whether a knob configures a FILTER atom or an ENTRY geometry:

```
FORGE_ATOM_*       — threshold values used in filter chain atoms (RSI, ADX, h1_trend, etc.)
FORGE_GEOMETRY_*   — SL/TP/lot/legs/expiry values for the order itself
FORGE_TRIGGER_*    — setup-trigger parameters (lookback bars, impulse threshold)
FORGE_TIMING_*     — cooldowns, expiry windows
FORGE_SETUP_*      — setup ENABLE toggles
FORGE_COMPOSITE_*  — composite ENABLE toggles
FORGE_GATE_*       — filter-chain gate toggles (REQUIRE/BLOCK)
FORGE_GLOBAL_*     — system-wide (lot fixed, max trades, etc.)
```

### 4.9 Scope precision — choose by primary identity, not secondary effect

When a knob has multiple plausible scopes, pick the one matching its **primary identity**,
not its secondary effect. Many knobs DO multiple things — the scope rule is "what does
it primarily configure?"

| Knob primarily | Scope |
|---|---|
| Enables a new entry trigger (new `setup_type` string) | `SETUP` (even if internally implemented as a composite of atoms) |
| Combines multiple atoms into a TRUE/FALSE rule that gates or amplifies existing setups | `COMPOSITE` |
| Defines a single indicator predicate / threshold (RSI floor, ADX min, etc.) | `ATOM` |
| Adds a single if/else rung that emits a SKIP gate code | `GATE` |
| Computes SL / TP / lot / leg count / order type | `GEOMETRY` |
| Defines a wall-time cooldown, expiry window, or polling interval | `TIMING` |
| System-wide config not tied to any specific setup/gate | `GLOBAL` |

**Concrete examples** (from the v2.7.38 split decision, 2026-05-12):

| Knob | Primary identity | Wrong scope | Right scope |
|---|---|---|---|
| `FORGE_FRACTIONAL_SELL_IN_BULL_ENABLED` | Enables a NEW `setup_type="FRACTIONAL_SELL_IN_BULL"` | `composites.*` (overload) | **`setup.*`** |
| `FORGE_FRACTIONAL_SELL_IN_BULL_LOT_FACTOR` | Lot multiplier for that setup's entries | `composites.*` (overload) | **`geometry.*`** |
| `FORGE_BULL_DAY_DIP_BUY_REENTRY_COOLDOWN_SEC` | Wall-time cooldown between re-entries | `composites.*` (overload) | **`timing.*`** |
| `FORGE_BLOCK_SELL_IN_CHOP_ENABLED` | Multi-atom predicate that gates SELL on RANGE | `safety.*` (legacy) / `gate.*` | **`composites.*`** (multi-atom predicate is the primary identity) |
| `FORGE_INTRADAY_REVERSAL_SELL_LOT_MULT` | Amplifier ON A COMPOSITE; secondary effect is lot | mixed | **`composites.*`** (it's a composite-specific knob; if it were a generic lot factor, `geometry.*`) |

**Why this rule exists**: `composites.*` was overloaded in v2.7.38 — it housed both gate-acting
composites (BLOCK_SELL_IN_CHOP, INTRADAY_REVERSAL_TO_SELL_V3) AND new setup-types
(FRACTIONAL_SELL_IN_BULL, BULL_DAY_DIP_BUY). The latter created their own `setup_type` string
in `JournalRecordSignal` — they are setups, not composites in disguise. Scheduled for split
under Phase 2 rename plan (`FORGE_REGIME_TAXONOMY.md §10.5.1c`).

**Anti-pattern**: NEVER use the legacy `safety.*` section for new knobs. It is a grandfathered
catchall (mixing lot factors + atom thresholds + gate flags + amplifiers) scheduled for migration
per `FORGE_REGIME_TAXONOMY.md §10.5`. Adding to it would entrench the catchall and create
migration debt.

---

## §5. Migration strategy (existing 146 knobs)

**Default rule**: do NOT rename existing knobs. Risk is too high.

| Existing knob | Action |
|---|---|
| Already follows policy | Leave alone (most existing). Update comment in `.env.example` to label its category if helpful. |
| Inconsistent direction-suffix position | Leave alone (functional). Note the inconsistency in this doc §2.3. New knobs follow policy. |
| Inconsistent verb (REQUIRE vs ENABLED for the same kind of gate) | Leave alone unless a future feature needs the gate added/removed. |
| Wholly redundant or unused | Mark for removal in a dedicated cleanup PR (not part of v2.7.36 ship). |

**Net default policy**: new knobs follow §4. Old knobs grandfathered. Document the WHY in this file.

### §5.0.1 Python-contract preservation rule (applies to ANY future rename)

**Hard rule**: any env-knob rename — scoped exception or otherwise — **must preserve the
Python contract**. Three things stay byte-identical when an env-var name changes:

1. **JSON keys** in `config/scalper_config.json` and `config/scalper_config.defaults.json`
   (e.g., `daily_direction_gate_enabled`, `h4_rsi_sell_max`) — Python apps and the EA both
   consume these. Never rename them as part of an env-knob rename.

2. **Validation/screening logic** in `scripts/sync_scalper_config_from_env.py` core
   functions: `_env_raw`, `_env_key_used`, `_load_env`, `_parse_value`, `_clamp`,
   `_atomic_write_json`, `apply_scalper_env_overrides`, `_sync_to_mt5`, `_stamp_version`,
   `main`. Only the **mapping table entries** (the dict that maps env-name → JSON destination)
   change. The validation pipeline stays intact.

3. **Python apps consuming `scalper_config.json`** — `bridge.py`, `aurum.py`, `athena_api.py`,
   and any other reader. Since the JSON keys don't change, these need no updates.

**Pre-rename audit checklist**:

```
1. grep -rl "<env_var_name>" /Users/olasumbo/signal_system/python/
   → expect ZERO matches (only sync mapping should reference it)
2. grep -rl "<lowercase_json_key>" /Users/olasumbo/signal_system/python/
   → if Python reads it, flag — don't proceed without consent
3. Confirm scalper_config.json + defaults.json keys are byte-identical pre/post rename
```

Failure to follow this checklist = silent break in downstream Python consumers. Operator
constraint codified 2026-05-12.

### §5.0.2 Backward-compatible alias pattern (canonical mechanism for all renames)

When renaming env knobs, ship the rename in two phases:

**Phase A (rename PR)** — add a `LEGACY_ALIASES` dict to `sync_scalper_config_from_env.py`:

```python
LEGACY_ALIASES = {
    "OLD_FORGE_NAME":  "NEW_FORGE_NAME",
    # ... one entry per renamed knob
}

# In _load_env() or apply_scalper_env_overrides():
for legacy, new in LEGACY_ALIASES.items():
    if legacy in env and new not in env:
        log.warning(f"Deprecation: {legacy} renamed to {new}. Update your .env.")
        env[new] = env[legacy]
```

Effect: operator's old `.env` keeps working; deprecation warning prompts update.

**Phase B (cleanup PR, ≥1 EA version later)** — remove `LEGACY_ALIASES`. Operators with
un-updated `.env` files now see a hard error pointing to the new name.

This is the strangler-fig pattern at the env-var layer — additive Phase A, cleanup Phase B,
with a grace period in between for operator migration.

### §5.1 Scoped exception — regime knobs renamed alongside `g_regime` struct refactor

The 20 regime/trend/daily/HTF env knobs are an EXCEPTION to the "no rename" rule because:

1. They directly map to `g_regime` struct fields being introduced in Phase 2 (v2.7.37 — see [`FORGE_REGIME_TAXONOMY.md §3`](FORGE_REGIME_TAXONOMY.md))
2. The struct refactor PR will touch the sync mapping anyway — renaming during the same PR is one change, not two
3. Implementation uses **backward-compatible aliases** (legacy names keep working for one EA version)
4. Zero EA code changes — purely at the `.env` → sync-mapping layer

**Full rename mapping** in [`FORGE_REGIME_TAXONOMY.md §10.5`](FORGE_REGIME_TAXONOMY.md) — 20 knobs, all conforming to policy §4 prefix hierarchy (ATOM/GATE prefixes, HTF vocabulary, direction suffix at end).

**Pattern for other future scoped exceptions**: when a structural refactor (e.g., BREAKOUT struct introduction, news-filter rewrite) makes a knob rename cheap, the relevant knob set may be renamed as part of that refactor PR. Document the rename mapping in the doc that owns the refactor. Always use the alias mechanism for one EA-version grace period.

---

## §6. v2.7.36 new knob proposals (apply policy)

Adopting the policy for the v2.7.36 new knobs:

| Composite / fix | Proposed new knob(s) | Pattern |
|---|---|---|
| BULL_DAY_DIP_BUY composite | `FORGE_COMPOSITE_BULL_DAY_DIP_BUY_ENABLE=1` | COMPOSITE prefix |
| INTRADAY_REVERSAL_TO_SELL | `FORGE_COMPOSITE_INTRADAY_REVERSAL_SELL_ENABLE=1` | same |
| BLOCK_SELL_IN_CHOP gate | `FORGE_GATE_BLOCK_SELL_IN_CHOP_ENABLE=1` | GATE prefix |
| FRACTIONAL_SELL_IN_BULL | `FORGE_COMPOSITE_FRACTIONAL_SELL_IN_BULL_ENABLE=1` | same |
| BB_PULLBACK_SCALP direction-split lot | `FORGE_GEOMETRY_PULLBACK_SCALP_LOT_FACTOR_BUY=1.0`, `FORGE_GEOMETRY_PULLBACK_SCALP_LOT_FACTOR_SELL=0.5` | GEOMETRY prefix, direction at END |

**Trade-off**: the new policy gives 4 different setup-prefix categories. Slightly more verbose
but the `_SETUP/COMPOSITE/GATE/GEOMETRY_` segment makes intent visible at scan time.

If this verbosity feels excessive after a few weeks of use, revisit.

---

## §7. Open questions

1. **Should `_REQUIRE_` be inverted globally to `_BLOCK_IF_NOT_`?** Currently a 1/0 toggle.
   Inverted form might be clearer (`FORGE_GATE_DUMP_PSAR_REQUIRED=1` = PSAR required;
   `FORGE_GATE_DUMP_PSAR_BLOCK_IF_NOT=1` = same meaning, different framing).
   Defer until clear consensus.

2. **Should setup-trigger params get `_TRIGGER_` prefix?** Currently:
   `FORGE_DUMP_LOOKBACK_BARS` (trigger param) vs `FORGE_DUMP_MAX_RSI` (filter param).
   Renaming `_TRIGGER_DUMP_LOOKBACK_BARS` would be informative but visually long.

3. **Should `_BUY` / `_SELL` be moved to `_DIRECTION_BUY` / `_DIRECTION_SELL` for clarity?**
   Overkill — current `_BUY`/`_SELL` at end is fine.

4. **Migration of old inconsistent knobs**: do nothing (current rec), or one-time
   migration PR? Defer the decision; not blocking any current work.

5. **Should the `.env.example` doc add category labels** like `# [SETUP]`, `# [COMPOSITE]`,
   `# [GEOMETRY]` as inline comments? Low cost, high readability. Worth doing.

---

## §8. Cross-references

- **Decision Stack** (`FORGE_DECISION_STACK.md`) — terminology this policy maps to
- **Atlas** (`docs/FORGE_INDICATOR_ATLAS.md`) — atom inventory
- **Composite Roadmap** (`FORGE_COMPOSITE_ROADMAP.md`) — new composites needing new knobs
- **Playbook** (`FORGE_SETUP_PLAYBOOK.md`) — current setup catalog
- **Research-Ops** (`FORGE_RESEARCH_OPS.md`) — §8 anti-patterns lists "Loose terminology" as forbidden; this doc operationalizes that

---

## §9. Changelog

| Date | Change |
|---|---|
| 2026-05-12 | Initial audit + policy. 146 FORGE_* knobs inventoried. 6 categories of inconsistency identified. §4 policy proposed. §5 migration strategy: grandfather old, new knobs follow policy. §6 v2.7.36 knob proposals use new prefix scheme. |
| 2026-05-12 | §5.1 scoped exception added — 20 regime/trend/daily/HTF env knobs WILL be renamed in Phase 2 (v2.7.37) alongside the `g_regime` struct introduction. Backward-compatible aliases for one EA version then hard-cut. Full mapping in `FORGE_REGIME_TAXONOMY.md §10.5`. Pattern: scoped exceptions allowed when paired with a structural refactor of the same component. |
| 2026-05-12 | **§4.6 HTF/MTF/LTF timeframe vocabulary** policy added — canonical timeframe references in NEW knobs use HTF (H1+H4), MTF (M15+M30), LTF (M1+M5), and DAILY (D1) prefixes. "macro" deprecated for new knobs (collision with macroeconomics). Glossary in `FORGE_REGIME_TAXONOMY.md §2.6`. |
| 2026-05-12 | **§5.0.1 Python-contract preservation rule** added — promoted from regime-specific concern to global policy. ANY future env rename must preserve JSON keys + screening logic + Python-app consumers. Pre-rename audit checklist included. |
| 2026-05-12 | **§5.0.2 Backward-compatible alias pattern** added — canonical mechanism for all env renames: ship via `LEGACY_ALIASES` dict in sync script (Phase A), remove later (Phase B). Strangler-fig pattern at the env-var layer. |
| 2026-05-12 | **§4.7 Gate Code naming policy** added — `config/gate_legend.json` audit found 65 codes with parallel inconsistencies to env knobs (`_block` vs `_blocked`, direction-suffix position, generic `entry_quality_*` not setup-distinguishable). Forward-going policy: `<setup_or_composite>_<gate_concept>_<direction?>`. New gate codes from v2.7.36 V3 composites onward follow policy; existing 65 grandfathered. Migration via `LEGACY_GATE_ALIASES` in `_patterns` section if forced. |
| 2026-05-12 | **§4.9 Scope precision rule added** — when a knob has multiple plausible scopes, pick by PRIMARY identity not secondary effect. Concrete table: new entry-trigger flag → `SETUP`; multi-atom predicate → `COMPOSITE`; threshold → `ATOM`; SKIP rung → `GATE`; SL/TP/lot → `GEOMETRY`; cooldown/expiry → `TIMING`. Triggered by v2.7.38 `composites.*` overload (lumped 2 gate-composites + 2 setup-types together). Decision: split FRACTIONAL_SELL_IN_BULL + BULL_DAY_DIP_BUY out to `setup.*` / `geometry.*` / `timing.*` per Phase 2 rename plan (`FORGE_REGIME_TAXONOMY.md §10.5.1c` — 9 new aliases, Phase 2 batch grows 36 → 45). Anti-pattern reaffirmed: never add new knobs to `safety.*` (legacy catchall, scheduled for migration). |
