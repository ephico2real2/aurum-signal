# FORGE Lot Sizing Reference

**Status**: living document — auto-regenerated from `config/scalper_config.json` after every release
**Last audit**: 2026-05-12 (against `VERSION` 2.7.39, `#property version "2.109"`)
**Source of truth**: `ea/FORGE.mq5` lot pipeline at lines `~8094-8270` (`PlaceOpenGroupLeg` / `combined_lot_factor`)

> This doc is the canonical reference for "what lot does setup X fire at?" — covers
> the full pipeline from `ScalperLot` MT5 input → `fixed_lot` config → per-setup
> factors → final per-leg lot. Updated alongside any FORGE_* lot-knob change.

---

## §0. The pipeline (one-line summary)

```
lot_per_leg = NormalizeLot(base_lot × lot_mult × combined_lot_factor)
n_legs      = ForgeResolveNumTrades(...)  →  capped by gold/unclear/recovery rules
total_per_signal = lot_per_leg × n_legs   (each leg is opened separately)
```

Where (v2.7.40+):
- **`base_lot`** = `lot_sizing.fixed_lot` (JSON config) — **the single absolute source of truth**. Set via `FORGE_FIXED_LOT` in `.env`. MT5 input no longer overrides this; it's a pure multiplier (see below).
- **`lot_mult`** = 1.0 by default; raised to 1.0–5.0 when `NativeScalperAutoLotByTrend=true` (BB_BREAKOUT only by default)
- **`combined_lot_factor`** = product of **11** multipliers (was 10), floored at **0.125**. The new 11th is `scalper_lot_factor` at the top — see §1.1.

### Half-sizing / double-sizing (v2.7.40)

Operators no longer change `fixed_lot` for temporary scale adjustments. Use **`ScalperLotFactor`** (MT5 input) or **`FORGE_GLOBAL_SCALPER_LOT_FACTOR`** (env):

| `ScalperLotFactor` | `fixed_lot=0.25` → effective | Use case |
|---:|:---:|---|
| **0.1** | 0.025 | Emergency halt-size (high-impact news) |
| **0.5** | 0.125 | Half-sizing / risk-off |
| **1.0** | 0.25  | Default no-op (full size) |
| **2.0** | 0.50  | Double-sizing / size-up validated day |

MT5 input wins when `!=1.0`; env value wins when MT5 input stays at default. Both default 1.0.

---

## §1. All lot-related knobs (with section prefix)

### §1.1 `lot_sizing.*` — global base + leg count + staging

| Knob | Default | Role |
|---|---|---|
| `lot_sizing.fixed_lot` | 0.25 | **Absolute base lot per leg — the single source of truth (v2.7.40+).** |
| `lot_sizing.scalper_lot_factor` | 1.0 | **Global multiplier on `fixed_lot`** (env-side mirror of MT5 input `ScalperLotFactor`). 0.5=half, 2.0=double. Sits at top of `combined_lot_factor`. |
| `lot_sizing.min_num_trades` | 2 | Minimum legs per signal |
| `lot_sizing.max_num_trades` | 30 | Maximum legs per signal |
| `lot_sizing.staged_entry_enabled` | 1 | 1 = stage legs over time / 0 = fire all at entry |
| `lot_sizing.staged_initial_legs` | 1 | Legs fired at entry; remainder staged |
| `lot_sizing.staged_add_interval_sec` | 25 | Min seconds between staged-add events |
| `lot_sizing.staged_add_min_favorable_points` | 500 | Favorable price move (pts) required for leg 2+ to add |
| `lot_sizing.gold_native_max_sell_legs` | 10 | XAUUSD SELL leg cap (gold-specific) |
| `lot_sizing.native_legs_max_when_unclear` | 5 | Leg cap when H1/H4 trend unclear |
| `lot_sizing.native_legs_clear_trend_factor` | 1.35 | Leg-count multiplier when trend clear |
| `lot_sizing.wave_confirmation_lot_mult` | 2 | Lot multiplier on staged legs 2+ |
| `lot_sizing.recovery_leg_boost_enabled` | 1 | Boost legs on drawdown recovery |
| `lot_sizing.recovery_leg_boost_extra` | 2 | +N legs in recovery mode |

### §1.2 `safety.*` — per-setup reducers/amplifiers

| Knob | Default | Applies to |
|---|---|---|
| `safety.dump_lot_factor` | 0.5 | MOMENTUM_DUMP default (per-direction overrides win) |
| `safety.dump_buy_lot_factor` | 1.0 | MOMENTUM_DUMP BUY override |
| `safety.dump_sell_lot_factor` | 0.5 | MOMENTUM_DUMP SELL override |
| `safety.pullback_scalp_lot_factor` | 0.5 | BB_PULLBACK_SCALP (any direction) |
| `safety.same_direction_stack_lot_factor` | 0.25 | 2nd concurrent same-direction group |
| `safety.breakout_adx_lot_factor_mid` | 1.0 | BB_BREAKOUT, M15 ADX 35-44 |
| `safety.breakout_adx_lot_factor_high` | 0.5 | BB_BREAKOUT, M15 ADX ≥ 45 |
| `safety.breakout_adx_lot_use_m15` | 1 | Use M15 ADX (1) vs M5 ADX (0) for tier decision |
| `safety.regime_h1_override_factor` | 2.0 | `n_legs` × this when H1 strong (leg-count amplifier, NOT per-leg lot) |
| `safety.regime_h1_override_adx_min` | 30 | Min M5 ADX for H1-strong override to fire |

### §1.3 `bb_breakout.*` — BB_BREAKOUT-specific

| Knob | Default | Applies to |
|---|---|---|
| `bb_breakout.sell_inside_band_lot_factor` | 0.25 | BB_BREAKOUT SELL when price > bb_lower (degraded breakout) |
| `bb_breakout.near_floor_lot_factor` | null (=1.0) | BB_BREAKOUT SELL crash-bypass + RSI 20-25 (Cardwell near-floor zone) |
| `bb_breakout.sell_stop_cont_lot_factor` | 1.0 | SELL STOP cascade leg (post-TP1 continuation) |
| `bb_breakout.sell_stop_cont_legs` | 5 | Cascade leg count |
| `bb_breakout.buy_limit_recovery_enabled` | 1 | BUY LIMIT recovery after SELL TP1 |

### §1.4 `bb_bounce.*` — BB_BOUNCE-specific

| Knob | Default | Applies to |
|---|---|---|
| `bb_bounce.bounce_lot_factor` | 0.25 | BB_BOUNCE (any direction; mean-reversion = smaller probe) |

### §1.5 `composites.*` — v2.7.38 boolean composites (all default-OFF)

| Knob | Default | Applies to |
|---|---|---|
| `composites.intraday_reversal_sell_lot_mult` | 2.0 | MOMENTUM_DUMP SELL × this when INTRADAY_REVERSAL_TO_SELL_V3 composite active |
| `composites.fractional_sell_in_bull_lot_factor` | 0.25 | FRACTIONAL_SELL_IN_BULL probe size (counter-regime overbought) |
| `composites.bull_day_dip_buy_lot_mult` | 1.0 | BULL_DAY_DIP_BUY amplifier (operator-tunable) |

---

## §2. Per-setup lot sizing — complete table

> **Assumption row**: `ScalperLot=0` (so `base_lot = fixed_lot = 0.25`), first concurrent group (no stack reduction), M15 ADX mid tier (factor=1.0), `lot_mult=1.0` (auto-lot off).

| # | Setup | Direction | Factors applied (×) | Combined factor | Lot/leg | n_legs typical | n_legs max | Total per signal |
|---|---|---|---|---|---|---|---|---|
| 1 | BB_BREAKOUT | BUY | adx_mid=1.0 | 1.000 | **0.2500** | 2-5 | 30 (auto) | 0.50 – 1.25 |
| 2 | BB_BREAKOUT | SELL (below bb_l) | adx_mid=1.0 | 1.000 | **0.2500** | 2-5 | 10 (gold cap) | 0.50 – 2.50 |
| 3 | BB_BREAKOUT | SELL (inside band) | inside_band=0.25 | 0.250 | **0.0625** | 2-5 | 10 | 0.125 – 0.625 |
| 4 | BB_BREAKOUT | SELL (M15 ADX ≥ 45) | adx_high=0.5 | 0.500 | **0.1250** | 2-5 | 10 | 0.25 – 1.25 |
| 5 | BB_BREAKOUT_RETEST | BUY | adx_mid=1.0 | 1.000 | **0.2500** | 2-5 | 30 | 0.50 – 1.25 |
| 6 | BB_BREAKOUT_RETEST | SELL | adx_mid=1.0 | 1.000 | **0.2500** | 2-5 | 10 | 0.50 – 1.25 |
| 7 | BB_BOUNCE | BUY | bounce=0.25 | 0.250 | **0.0625** | 2-3 | 5 | 0.125 – 0.3125 |
| 8 | BB_BOUNCE | SELL | bounce=0.25 | 0.250 | **0.0625** | 2-3 | 5 | 0.125 – 0.3125 |
| 9 | BB_PULLBACK_SCALP | BUY | pullback=0.5 | 0.500 | **0.1250** | 1-2 | 3 | 0.125 – 0.375 |
| 10 | BB_PULLBACK_SCALP | SELL | pullback=0.5 | 0.500 | **0.1250** | 1-2 | 3 | 0.125 – 0.375 |
| 11 | MOMENTUM_DUMP | BUY | dump_buy=1.0 | 1.000 | **0.2500** | 2-3 | 5 | 0.50 – 1.25 |
| 12 | MOMENTUM_DUMP | SELL (composite OFF) | dump_sell=0.5 | 0.500 | **0.1250** | 2-3 | 10 (gold cap) | 0.25 – 1.25 |
| 13 | MOMENTUM_DUMP | SELL + INTRADAY_REVERSAL ON | dump_sell=0.5 × intraday_rev=2.0 | 1.000 | **0.2500** | 2-3 | 10 | 0.50 – 2.50 |
| 14 | FRACTIONAL_SELL_IN_BULL (v2.7.38) | SELL | fractional=0.25 | 0.250 | **0.0625** | 1 | 1 | 0.0625 |
| 15 | BULL_DAY_DIP_BUY (v2.7.38) | BUY | bull_dip=1.0 | 1.000 | **0.2500** | 1-2 | 3 | 0.25 – 0.75 |
| 16 | SELL_STOP_CONT (post-TP1 cascade) | SELL | sell_stop_cont_lot_factor=1.0 | 1.000 | **0.2500** | 5 | 5 | 1.25 |
| 17 | BUY_LIMIT_RECOVERY (post-TP1) | BUY | (no special factor) | 1.000 | **0.2500** | 1 | 1 | 0.25 |

---

## §3. Compound-penalty scenarios

Multiple penalty factors multiply together. The `combined_lot_factor` floor of **0.125** catches the worst cases.

| Scenario | Math | Per-leg lot |
|---|---|---|
| BB_BREAKOUT SELL inside-band + 2nd same-dir + M15 ADX ≥45 | 0.25 × 0.25 × 0.25 × 0.5 = 0.0078 → floor → 0.25 × 0.125 = 0.0313 | **0.0313** |
| BB_BOUNCE + 2nd same-dir | 0.25 × 0.25 × 0.25 = 0.0156 → floor → 0.25 × 0.125 = 0.0313 | **0.0313** |
| MOMENTUM_DUMP SELL + 2nd same-dir | 0.25 × 0.5 × 0.25 = 0.0313 (above floor) | **0.0313** |
| MOMENTUM_DUMP SELL + 2nd same-dir + INTRADAY_REVERSAL ON | 0.25 × 0.5 × 0.25 × 2.0 = 0.0625 | **0.0625** |
| BB_PULLBACK_SCALP + 2nd same-dir | 0.25 × 0.5 × 0.25 = 0.0313 | **0.0313** |

---

## §4. Multipliers that GROW lot (vs reduce)

| Factor | Multiplier | Applies when | Notes |
|---|---|---|---|
| `composites.intraday_reversal_sell_lot_mult` | **2.0×** | MOMENTUM_DUMP SELL with INTRADAY_REVERSAL_TO_SELL_V3 composite active | v2.7.38 — currently default-OFF |
| `composites.bull_day_dip_buy_lot_mult` | 1.0× (default) | BULL_DAY_DIP_BUY trigger fires | v2.7.38 — operator-tunable to ≥1.0 |
| `lot_sizing.wave_confirmation_lot_mult` | **2.0×** | Staged legs 2+ via `ManageStagedNativeLegs` | Currently never fires (`staged_add_min_favorable_points=500` unreachable before TP1) |
| `safety.regime_h1_override_factor` | **2.0×** | H1 trend strength ≥ threshold AND M5 ADX ≥ `regime_h1_override_adx_min=30` | Affects **`n_legs` count**, NOT per-leg lot — doubles total exposure |

---

## §5. What's "off the menu" today (configured but not firing)

| Reason | Effect | How to fix |
|---|---|---|
| MT5 input `ScalperLot=0.08` (legacy, pre-v2.7.40) absolute override | Every setup's lot/leg reduced ~12.5× from §2 (0.08 × 0.125 floor = 0.01) | **Fixed in v2.7.40** — `ScalperLot` renamed to `ScalperLotFactor` (multiplier, default 1.0). Old `.set` entries silently ignored. |
| `lot_sizing.staged_initial_legs=1` + `staged_add_min_favorable_points=500` | Only 1 leg fires per signal — `wave_confirmation_lot_mult=2` never amplifies | Set `FORGE_STAGED_INITIAL_LEGS=N` (fire N at entry) OR lower threshold to ~20 pts |
| All 4 v2.7.38 composites default-OFF | INTRADAY_REVERSAL amplifier, FRACTIONAL_SELL probe, BULL_DAY_DIP not contributing | Set `FORGE_*_ENABLED=1` per composite |
| `safety.regime_h1_override_adx_min=30` | Skipped on lower-ADX setups; only fires on a few entries | Lower if you want broader regime-amplifier coverage |
| `bb_breakout.near_floor_lot_factor=null` | RSI 20-25 crash-bypass entries don't apply near-floor reduction | Set value (e.g. 0.25) if you want it |

---

## §6. Run 24 audit — actuals vs configured (validation evidence)

From `forge_signals` + `TRADES` for Run 24 (aurum_run_id=24, v2.7.39):

| Setup observed | Configured per §2 | Actual lot/leg | Gap |
|---|---|---|---|
| MOMENTUM_DUMP SELL (Mar 31, Apr 2) | 0.125 | **0.01** | 12.5× small |
| MOMENTUM_DUMP BUY (Apr 1, Apr 2, Apr 6) | 0.25 | **0.02** | 12.5× small |
| BB_BREAKOUT BUY (G5007 Apr 1, G5017 Apr 6) | 0.25 | **0.02** | 12.5× small |
| BB_PULLBACK_SCALP BUY (G5014 Apr 2) | 0.125 | **0.01** | 12.5× small |

**Constant 12.5× reduction across all setups** is now explained:
- MT5 input `ScalperLot=0.08` (legacy absolute, pre-v2.7.40) overrode `fixed_lot=0.25` to `0.08`.
- Then `combined_lot_factor` hit the `MathMax(0.125, ...)` floor: `0.08 × 0.125 = 0.01`.

**v2.7.40 fix**: `ScalperLot` renamed to `ScalperLotFactor` (multiplier, default 1.0). Old `.set` entries no longer load — MT5 silently uses the new input's default. Effective lot now = `fixed_lot (0.25) × ScalperLotFactor (1.0) × combined_lot_factor` = full configured size.

Plus: every TAKEN fires only 1 leg (per `staged_initial_legs=1` + unreachable `staged_add_min_favorable_points=500`). **Staging bug separate** — see §7 Step 2.

---

## §7. How to size up

To go from current run state (≈0.01-0.02 per leg, 1 leg per signal) to configured table values (0.0625-0.25 per leg, 2-10 legs per signal):

### Step 1 — Restore base_lot (v2.7.40 — auto-fixed by rename)

The v2.7.40 rename `ScalperLot → ScalperLotFactor` already restores base_lot to `fixed_lot=0.25`:
- MT5 input `ScalperLotFactor=1.0` (new default) — no override → `g_sc.lot_fixed=0.25` used directly
- Old `.set` files with `ScalperLot=0.08` are silently ignored (the input no longer exists)
- Verify in MT5 panel: `ScalperLotFactor` should show `1.0`; `NativeScalperInputsOverrideLotSizing=false`

For ad-hoc scaling without redeploying config:
- **De-risk a session**: set `ScalperLotFactor=0.5` (halves every per-leg lot)
- **Size-up validated day**: set `ScalperLotFactor=2.0` (doubles every per-leg lot)
- **Permanent base change**: edit `FORGE_FIXED_LOT` in `.env`, redeploy

This alone scales every TAKEN by 12.5× vs the pre-v2.7.40 0.01-lot trap.

### Step 2 — Enable multi-leg simultaneous

Three options for `.env`:

**Option A** — Disable staging entirely (fire all `n_legs` at entry):
```bash
FORGE_STAGED_ENTRY_ENABLED=0
```
Then `make scalper-env-sync` + reload EA.

**Option B** — Lower staged threshold so leg 2 adds quickly:
```bash
FORGE_STAGED_ADD_MIN_FAVORABLE_POINTS=20   # ~25% to TP1 triggers leg 2
```
Keeps staging on but makes leg 2+ reachable before TP1.

**Option C** — Fire N legs at entry, stage the rest:
```bash
FORGE_STAGED_INITIAL_LEGS=2   # 2 legs at entry, rest staged via ManageStagedNativeLegs
```

### Step 3 — Optional: tune per-setup factor

To raise specific setup risk after validation:
```bash
FORGE_DUMP_SELL_LOT_FACTOR=1.0          # match BUY size on SELL
FORGE_BOUNCE_LOT_FACTOR=0.5             # 2× BB_BOUNCE (currently 0.25)
FORGE_PULLBACK_SCALP_LOT_FACTOR=0.75    # 1.5× BB_PULLBACK_SCALP
FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR=0.5  # 2× degraded-breakout SELL
```

### Step 4 — Optional: enable v2.7.38 composite amplifiers
After validating each composite's gating accuracy:
```bash
FORGE_BLOCK_SELL_IN_CHOP_ENABLED=1                # gate only — safe
FORGE_INTRADAY_REVERSAL_SELL_ENABLED=1            # amp + gate — needs validation
FORGE_FRACTIONAL_SELL_IN_BULL_ENABLED=1           # new trigger — needs validation
FORGE_BULL_DAY_DIP_BUY_ENABLED=1                  # new trigger — needs validation
```

---

## §8. Naming convention alignment (Phase 2 rename plan)

The lot-related knob sections (`lot_sizing.*`, `safety.*`, `bb_breakout.*`, `bb_bounce.*`)
are legacy and grandfathered per `FORGE_REGIME_TAXONOMY.md §10.5`. Only `composites.*`
follows the modern `FORGE_<scope>_*` convention.

Per `FORGE_NAMING_CONVENTIONS.md §4` + taxonomy §10.5.1b, the Phase 2 rename batch
includes the following lot-related knobs (currently legacy → proposed canonical):

| Current | Proposed | Scope |
|---|---|---|
| `safety.dump_buy_lot_factor` | `geometry.dump_lot_factor_buy` | GEOMETRY |
| `safety.dump_sell_lot_factor` | `geometry.dump_lot_factor_sell` | GEOMETRY |
| `lot_sizing.wave_confirmation_lot_mult` | `geometry.wave_confirm_lot_mult` | GEOMETRY |
| `lot_sizing.staged_*` | `geometry.staged_*` | GEOMETRY |
| `lot_sizing.native_legs_clear_trend_factor` | `geometry.legs_clear_trend_factor` | GEOMETRY |

These ship with backward-compatible aliases per §10.5.2 LEGACY_ALIASES.

---

## §9. Cross-references

- **EA source**: `ea/FORGE.mq5:~8094-8270` (lot pipeline in `PlaceOpenGroupLeg` / `ScalperEvaluate`)
- **Active config**: `config/scalper_config.json` (auto-generated; do not hand-edit)
- **Defaults**: `config/scalper_config.defaults.json`
- **Env overrides**: `.env` (consumed via `scripts/sync_scalper_config_from_env.py`)
- **Documentation cheat sheet**: `.env.example`
- **Decision-stack inventory**: `docs/FORGE_DECISION_STACK_INVENTORY.md §5 Entry Geometry` — geometry-side rules per setup
- **Setup playbook**: `FORGE_SETUP_PLAYBOOK.md §5` — TP/SL geometry per setup
- **Indicator atlas**: `docs/FORGE_INDICATOR_ATLAS.md §5` — composite registry (incl. lot multipliers)
- **Naming conventions**: `FORGE_NAMING_CONVENTIONS.md §4` — going-forward `FORGE_<scope>_*` policy
- **Regime taxonomy**: `FORGE_REGIME_TAXONOMY.md §10.5` — env-knob rename plan (Phase 2 batch: 45 + v2.7.40 MT5-input rename in §10.5.1d)
- **Validation evidence**: `docs/FORGE_RUN24_ANALYSIS.md` — Run 24 actuals confirming 12.5× lot shrinkage

---

## §10. Changelog

| Date | Change |
|---|---|
| 2026-05-12 | Initial doc created. Captures complete lot pipeline post-v2.7.39: 30 lot-related knobs across 5 sections (lot_sizing, safety, bb_breakout, bb_bounce, composites), per-setup table for 17 setup×direction combinations, compound-penalty scenarios, growth multipliers, and "off the menu" gap analysis. Validated against Run 24 actuals — constant 12.5× shrinkage confirmed `ScalperLot` MT5 input override. Cross-referenced from FORGE_NAMING_CONVENTIONS.md, FORGE_REGIME_TAXONOMY.md §10.5, FORGE_DECISION_STACK_INVENTORY.md §5. |
| 2026-05-12 | **v2.7.40 — `ScalperLot` → `ScalperLotFactor`.** Lot pipeline unified: `lot_sizing.fixed_lot` is now the SINGLE absolute base. The MT5 input is no longer an absolute override; it's a multiplier at the top of `combined_lot_factor` (default 1.0 = no-op). New env knob `FORGE_GLOBAL_SCALPER_LOT_FACTOR` mirrors it for headless/CI control. Old `.set` lines with `ScalperLot=0.08` are silently ignored — clean break, no LEGACY_ALIASES needed (rename = safe default fallback). §0 pipeline summary updated, §1.1 adds `scalper_lot_factor` row, §6 audit explains the 12.5× shrinkage as `0.08 × 0.125 floor = 0.01`, §7 Step 1 updated to reflect auto-fix. Half/double-sizing scenarios documented (0.5 / 1.0 / 2.0 / 0.1 emergency). |
