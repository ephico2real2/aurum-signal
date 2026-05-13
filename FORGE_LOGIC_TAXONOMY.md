# FORGE Logic Taxonomy

> **What this doc is**: a catalog of the **reusable logic patterns** that show up across the FORGE EA — how filters block trades, how bypasses re-allow them, how amplifiers scale exposure, how state-tracking globals talk to gates. This is the *grammar* of FORGE's decision code, separate from the *vocabulary* (atoms, composites, gate codes) catalogued in `FORGE_DECISION_STACK.md` and `FORGE_INDICATOR_ATLAS.md`.
>
> **Audience**: anyone adding a new gate, bypass, amplifier, or cooldown. Use this doc to pick the right pattern before writing code, so the codebase stays internally consistent.
>
> **Cross-references**: `FORGE_DECISION_STACK.md` (5-layer entry architecture), `FORGE_NAMING_CONVENTIONS.md` §4 (env-knob naming), `FORGE_REGIME_TAXONOMY.md` (regime state), `docs/FORGE_INDICATOR_ATLAS.md` (atoms + composites), `README.md`.

---

## §1. The 7 logic patterns at a glance

| # | Pattern | Role | Output | Example in FORGE |
|---|---------|------|--------|------------------|
| 1 | **Filter / Gate** | Block trades that fail a condition | bool (true = allowed) | `entry_quality_atr` (M5 ATR floor) |
| 2 | **Bypass** | Conditional escape hatch from a filter | bool (true = bypass gate) | `cooldown_bypass_on_tp_with_trend` |
| 3 | **Amplifier** | Scale exposure (lot or legs) when conditions met | multiplier (float) | `intraday_reversal_sell_lot_mult=2.0` |
| 4 | **Composite** | Multi-atom boolean predicate gating/amplifying a setup | bool | `IsIntradayReversalSellActive()` |
| 5 | **State tracker** | Global updated on event, queried later | timestamp / counter | `g_scalper_last_tp1_buy_time` |
| 6 | **Cooldown** | Time-based block after an event | bool (true = blocked) | `pullback_scalp_cooldown_seconds=600` |
| 7 | **Bypass list** | Per-setup-type whitelist that escapes a filter | string (comma-list) + helper | `cooldown_bypass_setups` |

Each pattern has a recognizable code shape — see §2-§8.

---

## §2. Filter / Gate pattern

**Purpose**: hard-block trades that fail a condition. Single-direction: pass-or-skip.

### Code shape

```cpp
// Gate: <one-line reason this exists, citing the regression it prevents>
if (cond_should_block) {
    JournalRecordSignal("SKIP", "<gate_code>", setup_type, direction,
                        mid, spread, atr, rsi, adx, bb_u, bb_l, bb_m, ...);
    return false;  // (or `return;` if the function is void)
}
```

### Required parts

1. **Block condition** — boolean expression
2. **SKIP journal record** — with a unique `<gate_code>` registered in `config/gate_legend.json`
3. **Early return** — caller MUST stop processing this signal

### Naming the gate_code

Per `FORGE_NAMING_CONVENTIONS.md` §4.7:

```
<setup_or_composite>_<gate_concept>_<direction?>
```

Examples: `entry_quality_atr`, `entry_quality_direction_cap`, `breakout_h4_rsi_buy_blocked`, `intraday_reversal_buy_block`.

Existing 65 codes are grandfathered (some violate the policy — e.g. `_blocked` instead of `_block`). New codes from v2.7.36 onward MUST follow the policy.

### Where to insert a new gate

Almost always inside `CheckEntryQuality()` (FORGE.mq5:6380) for direction-neutral / setup-neutral gates, OR inside the BUY/SELL setup branch in `CheckNativeScalperSetups()` for setup-specific gates. Order matters — cheaper checks first.

### Gate vs filter terminology

The terms are used interchangeably in FORGE. "Filter" usually = boolean predicate. "Gate" = the same predicate seen as a checkpoint in the decision flow. Same code shape.

---

## §3. Bypass pattern

**Purpose**: conditional escape hatch from a Filter/Gate (§2). When SOME condition warrants letting a normally-blocked trade through.

### Code shape

```cpp
// Gate (with bypass): block UNLESS bypass conditions met
if (cond_should_block && !BypassActive(direction, setup_type, indicators)) {
    JournalRecordSignal("SKIP", "<gate_code>", ...);
    return false;
}
```

### Bypass helper structure

```cpp
// Brief docblock: bypass conditions, default behavior, intended use case
bool BypassActive(const string direction, const string setup_type, ...) {
    // (a) Unconditional whitelist (bypass list — see §8)
    if (SetupInBypassList(setup_type, g_sc.bypass_setups)) return true;
    // (b) Master switch
    if (!g_sc.bypass_enabled) return false;
    // (c) Stateful conditions — last event, regime, indicators
    if (StaleOrAbsent(last_event_time)) return false;
    if (RegimeMismatch(direction, g_regime_label)) return false;
    if (IndicatorFails(adx, threshold)) return false;
    // (d) Anti-flicker / refire floor
    if (TooSoonSinceLastFire(min_refire_sec)) return false;
    return true;
}
```

### Required parts

1. **Master toggle** — bool env knob (e.g. `cooldown_bypass_on_tp_with_trend`)
2. **Stateful condition(s)** — usually reference a state-tracker global (§6)
3. **Indicator confirmation** — typically ADX / regime / RSI to ensure conditions still favor the bypass
4. **Anti-flicker** — minimum time between fires to prevent same-tick duplicates
5. **Bypass list (optional)** — string knob for unconditional setup-type whitelist (§8)

### When to use a bypass vs loosening the gate

| Symptom | Right pattern |
|---------|--------------|
| Gate is correct in most cases but wrong in a specific regime | **Bypass** (this pattern) |
| Gate threshold is just too tight | Loosen the threshold knob |
| Gate is correct for some setups but wrong for others | **Bypass list** (§8) — or split the gate per-setup |

### Live examples

| Bypass | What it lets through | Conditions |
|--------|---------------------|------------|
| `max_open_same_direction_bypass_setups` (v2.7.41) | Risk-1 setups stack past the per-direction concurrent-open cap | Setup in whitelist |
| `cooldown_bypass_on_tp_with_trend` (v2.7.41) | Re-entry during strong trend after a win | Recent TP1 + regime match + ADX ≥ 25 + refire floor |

---

## §4. Amplifier pattern

**Purpose**: scale exposure (lot, legs, SL/TP width) when conditions favor amplification. Inverse of a throttle — instead of blocking, it BOOSTS.

### Code shape — lot amplifier

```cpp
double amplifier_factor = 1.0;  // 1.0 = no-op, must be safe default
if (setup_type == "X" && direction == "Y" && IsCompositeActive(...)
    && g_sc.<amplifier>_mult > 1.0) {
    amplifier_factor = g_sc.<amplifier>_mult;  // e.g. 2.0 = double exposure
}
// Folded into combined_lot_factor:
combined_lot_factor = MathMax(floor, base * amplifier_factor * ...);
```

### Code shape — leg-count amplifier

```cpp
int n_legs_amplified = base_n;
if (CompositeAmplifies(...) && g_sc.regime_h1_override_factor > 1.0) {
    n_legs_amplified = (int)(base_n * g_sc.regime_h1_override_factor);
}
n_legs_amplified = MathMin(MAX_LEGS_CEILING, n_legs_amplified);
```

### Required parts

1. **Safe default** = 1.0 (no-op). Always.
2. **Composite or atom gate** — amplifier only fires when conditions confirm
3. **Hard ceiling** — `MathMin` cap to prevent runaway scaling
4. **Knob name follows GEOMETRY scope** per §4.9 (`FORGE_GEOMETRY_*_LOT_MULT`)

### Live examples

| Amplifier | Effect | Gate |
|-----------|--------|------|
| `intraday_reversal_sell_lot_mult=2.0` | Doubles lot on MOMENTUM_DUMP SELL when composite active | INTRADAY_REVERSAL_TO_SELL_V3 composite |
| `wave_confirmation_lot_mult=2.0` | Doubles lot on staged-add legs (legs 2+) after favorable-excursion threshold | `staged_add_min_favorable_points` met |
| `regime_h1_override_factor=2.0` | Doubles leg COUNT when H1 strongly aligned + ADX confirms | H1 trend strength + ADX |
| `bull_day_dip_buy_lot_mult` | Operator-tunable amplifier on BULL_DAY_DIP_BUY | Composite active |
| `ScalperLotFactor` (v2.7.40) | Global lot multiplier on `fixed_lot` (MT5 input or env) | Always-on, default 1.0 |

### Inverse amplifiers (per-setup lot throttles — same code shape, default < 1.0)

The lot-factor code pattern (safe default 1.0 in the local variable, conditional bump to
the env knob value) ALSO accommodates **throttles** where the env knob defaults below
1.0. Mechanically identical to amplifiers; only the default direction differs. The 11
v2.7.42 setups all use this shape with `geometry.<setup>_lot_factor=0.5` default
(conservative per-leg sizing on new setups until backtest validates).

| Throttle | Effect | Gate |
|---|---|---|
| `geometry.ma_crossover_lot_factor=0.5` | 0.5× lot on MA_CROSSOVER (crossovers lag) | `setup_type == "MA_CROSSOVER"` |
| `geometry.vwap_reversion_lot_factor=0.5` | 0.5× lot on VWAP_REVERSION | `setup_type == "VWAP_REVERSION"` |
| `geometry.fib_confluence_lot_factor=0.5` | 0.5× lot on FIB_CONFLUENCE | `setup_type == "FIB_CONFLUENCE"` |
| `geometry.inside_bar_lot_factor=0.5` | 0.5× lot on INSIDE_BAR | `setup_type == "INSIDE_BAR"` |
| `geometry.bb_squeeze_lot_factor=0.5` | 0.5× lot on BB_SQUEEZE | `setup_type == "BB_SQUEEZE"` |
| `geometry.orb_lot_factor=0.5` | 0.5× lot on ORB | `setup_type == "ORB"` |
| `geometry.gap_and_go_lot_factor=0.5` | 0.5× lot on GAP_AND_GO | `setup_type == "GAP_AND_GO"` |
| `geometry.double_pattern_lot_factor=0.5` | 0.5× lot on DOUBLE_TOP / DOUBLE_BOTTOM (shared) | `setup_type in {DOUBLE_TOP, DOUBLE_BOTTOM}` |
| `geometry.hs_lot_factor=0.5` | 0.5× lot on HEAD_AND_SHOULDERS / INVERSE_H&S (shared) | `setup_type in {HEAD_AND_SHOULDERS, INVERSE_HEAD_AND_SHOULDERS}` |
| `geometry.flag_pennant_lot_factor=0.5` | 0.5× lot on FLAG_PENNANT | `setup_type == "FLAG_PENNANT"` |
| `geometry.trendline_bounce_lot_factor=0.5` | 0.5× lot on TRENDLINE_BOUNCE | `setup_type == "TRENDLINE_BOUNCE"` |
| `geometry.sr_flip_lot_factor=0.5` | 0.5× lot on SR_FLIP | `setup_type == "SR_FLIP"` |

All 11 default-OFF in `setup.*_enabled=0`. When operator flips a setup ON, the throttle
is automatically applied — explicit step to size up requires raising the lot_factor knob.

---

## §5. Composite pattern

**Purpose**: multi-atom boolean predicate. Combines 2+ indicator atoms (RSI, ADX, EMA, H1 DI, etc.) into a single named condition that gates or amplifies a setup.

### Code shape

```cpp
// Composite helper: returns true when all atoms agree on the named pattern
bool Is<CompositeName>Active(
    const double h1_trend, const double rsi, const double price, const double bb_mid) {
    // Master toggle
    if (!g_sc.<composite>_enabled) return false;
    // Atom 1: <indicator predicate>
    if (h1_trend < g_sc.<composite>_min_h1_trend) return false;
    // Atom 2: ...
    if (rsi > g_sc.<composite>_max_rsi) return false;
    // Atom 3: ...
    if (price < bb_mid) return false;
    return true;
}
```

### Required parts

1. **Master toggle** — `_enabled` knob (default-OFF for new composites)
2. **2+ atom predicates** — each citing the indicator + threshold knob
3. **Pure function** — no side effects, queried freely
4. **Named after the named pattern** — `IsIntradayReversalSellActive`, `IsBlockSellInChopActive`, etc.

### Composite categories (per Decision Stack Layer 3)

| Category | Role | Example |
|----------|------|---------|
| **Gate composite** | Blocks/allows existing setups | `BLOCK_SELL_IN_CHOP` |
| **Amplifier composite** | Scales exposure on existing setups | `INTRADAY_REVERSAL_TO_SELL_V3` (lot × 2.0) |
| **Setup composite** | A NEW setup_type defined by the composite | `FRACTIONAL_SELL_IN_BULL`, `BULL_DAY_DIP_BUY` |

The scope split for env knobs follows §4.9:
- Gate composite → `composites.*`
- Amplifier composite → `composites.*` (but check §4.9 if it's becoming a setup)
- Setup composite → `setup.* + geometry.* + timing.*` (per v2.7.38 split §10.5.1c)

### Live registry

See `docs/FORGE_INDICATOR_ATLAS.md` §5 — composite registry with calibration history.

### v2.7.42 setup composites (11 new ones)

Per §5 categories, the **Setup composite** subtype (a multi-atom predicate that defines
a new `setup_type`) describes all 11 v2.7.42 entries shipped this session. Each has a
`Detect<Name>Event()` helper that returns `1 = BUY signal / -1 = SELL signal / 0 = no
event` — a direction-aware variant of the §5 bool-returning shape. Sample:

```cpp
int DetectMaCrossoverEvent() {
    if (!g_sc.ma_crossover_enabled) return 0;  // master toggle
    double ema20_buf[2], ema50_buf[2];
    if (CopyBuffer(g_mtf[0].h_ma20, 0, 1, 2, ema20_buf) != 2) return 0;
    if (CopyBuffer(g_mtf[0].h_ma50, 0, 1, 2, ema50_buf) != 2) return 0;
    double diff_now  = ema20_buf[0] - ema50_buf[0];
    double diff_prev = ema20_buf[1] - ema50_buf[1];
    if (diff_prev <= 0.0 && diff_now > 0.0) return 1;   // BUY cross
    if (diff_prev >= 0.0 && diff_now < 0.0) return -1;  // SELL cross
    return 0;
}
```

| Setup composite (Det*Event helper) | Setup_type string | Returns 1 | Returns -1 |
|---|---|---|---|
| `DetectMaCrossoverEvent` | `MA_CROSSOVER` | EMA20 crosses above EMA50 | EMA20 crosses below EMA50 |
| `DetectVwapReversionEvent` | `VWAP_REVERSION` | Pullback to VWAP in H1 uptrend | Pullback to VWAP in H1 downtrend |
| `DetectFibConfluenceEvent` | `FIB_CONFLUENCE` | H1 bull + price near fib + ≥N references | H1 bear + same |
| `DetectInsideBarBreakoutEvent` | `INSIDE_BAR` | Inside-bar + breakout above bar[1] high | Inside-bar + breakout below bar[1] low |
| `DetectBbSqueezeBreakoutEvent` | `BB_SQUEEZE` | Squeeze + break above bb_u + min_breakout | Squeeze + break below bb_l |
| `DetectOrbBreakoutEvent` | `ORB` | Locked range + break above range_high | Locked range + break below range_low |
| `DetectGapAndGoEvent` | `GAP_AND_GO` | Gap up ≥ min_gap_atr | Gap down ≥ min_gap_atr |
| `DetectDoubleTopEvent` | `DOUBLE_TOP` | — (SELL only) | Two-highs + neckline-break |
| `DetectDoubleBottomEvent` | `DOUBLE_BOTTOM` | Two-lows + ridge-break | — (BUY only) |
| `DetectHeadAndShouldersEvent` | `HEAD_AND_SHOULDERS` | — (SELL only) | 3-high H&S + neckline-break |
| `DetectInverseHeadAndShouldersEvent` | `INVERSE_HEAD_AND_SHOULDERS` | 3-low IH&S + neckline-break | — (BUY only) |
| `DetectFlagPennantEvent` | `FLAG_PENNANT` | Bullish impulse + consolidation + break-up | Bearish impulse + consolidation + break-down |
| `DetectTrendlineBounceEvent` | `TRENDLINE_BOUNCE` | Rising-lows line + touch + reject up | Falling-highs line + touch + reject down |
| `DetectSrFlipEvent` | `SR_FLIP` | Broken resistance bounces as support | Broken support rejects as resistance |

All 11 follow the §5 "Setup composite" pattern: master toggle + multi-atom predicate
chain + pure function (no side effects). Each is paired with a `<setup>_lot_factor` in
the GEOMETRY scope (§4 amplifier shape), a `<setup>_*_cooldown_seconds` in the TIMING
scope (§7), per-direction cooldown trackers in §6, and SKIP gate codes in §2.

---

## §6. State-tracker pattern

**Purpose**: global variable updated on event, queried by gates/bypasses/amplifiers later. The "memory" of the EA.

### Code shape — state update

```cpp
// On event X, update tracker
if (event_fired) {
    g_scalper_<event>_time_<dimension> = TimeCurrent();
    // Optional: log
    PrintFormat("FORGE: <event> at %s — tracker updated", TimeToString(...));
}
```

### Code shape — state query

```cpp
// Tracker query — used in gates/bypasses
if (g_scalper_<event>_time_<dimension> > 0
    && (TimeCurrent() - g_scalper_<event>_time_<dimension>) < g_sc.<duration_knob>) {
    // Within window — apply cooldown / bypass / amplifier
}
```

### Naming convention

```
g_scalper_<event>_<dimension>      — generic native scalper trackers
g_<setup_lower>_last_<event>_time  — setup-specific trackers
```

### Live registry

| Tracker | Updated when | Queried by |
|---------|--------------|-----------|
| `g_scalper_last_loss_time` | Position closed with negative P&L | `ScalperCooldownOK()` |
| `g_scalper_last_tp1_buy_time` (v2.7.41) | BUY group hits TP1 | `CooldownBypassActive()` |
| `g_scalper_last_tp1_sell_time` (v2.7.41) | SELL group hits TP1 | `CooldownBypassActive()` |
| `g_pullback_scalp_last_buy_time` | BB_PULLBACK_SCALP BUY fires | Pullback BUY cooldown |
| `g_pullback_scalp_last_sell_time` | BB_PULLBACK_SCALP SELL fires | Pullback SELL cooldown |
| `g_scalper_last_bb_breakout_buy` | BB_BREAKOUT BUY fires | Breakout BUY same-dir cooldown |
| `g_scalper_last_bb_breakout_sell` | BB_BREAKOUT SELL fires | Breakout SELL same-dir cooldown |
| `g_last_chop_buy_exit_time` | BULL_DAY_DIP_BUY TP1 exit | BULL_DAY_DIP_BUY reentry cooldown |
| `g_scalper_last_direction` | Any entry | `ScalperDirectionCooldownOK()` (anti-flip-flop) |
| `g_groups[gi].tp1_hit` | TP1 close fires | Group lifecycle, post-TP1 ladder arming |
| **v2.7.42 — Phase 2 / C-extended setup cooldown trackers (28 total)** | | |
| `g_ma_crossover_last_buy_time` / `_sell_time` | MA_CROSSOVER fires | MA_CROSSOVER per-direction cooldown |
| `g_vwap_reversion_last_buy_time` / `_sell_time` | VWAP_REVERSION fires | VWAP_REVERSION per-direction cooldown |
| `g_fib_confluence_last_buy_time` / `_sell_time` | FIB_CONFLUENCE fires | FIB_CONFLUENCE per-direction cooldown |
| `g_inside_bar_last_buy_time` / `_sell_time` | INSIDE_BAR fires | INSIDE_BAR per-direction cooldown |
| `g_bb_squeeze_last_buy_time` / `_sell_time` | BB_SQUEEZE fires | BB_SQUEEZE per-direction cooldown |
| `g_orb_last_buy_time` / `_sell_time` | ORB fires | ORB per-direction cooldown |
| `g_gap_and_go_last_buy_time` / `_sell_time` | GAP_AND_GO fires | GAP_AND_GO per-direction cooldown |
| `g_flag_pennant_last_buy_time` / `_sell_time` | FLAG_PENNANT fires | FLAG_PENNANT per-direction cooldown |
| `g_trendline_bounce_last_buy_time` / `_sell_time` | TRENDLINE_BOUNCE fires | TRENDLINE_BOUNCE per-direction cooldown |
| `g_sr_flip_last_buy_time` / `_sell_time` | SR_FLIP fires | SR_FLIP per-direction cooldown |
| `g_double_top_last_time` | DOUBLE_TOP fires (SELL-only) | DOUBLE_TOP single-pattern cooldown |
| `g_double_bottom_last_time` | DOUBLE_BOTTOM fires (BUY-only) | DOUBLE_BOTTOM single-pattern cooldown |
| `g_head_and_shoulders_last_time` | HEAD_AND_SHOULDERS fires (SELL-only) | H&S single-pattern cooldown |
| `g_inverse_head_and_shoulders_last_time` | INVERSE_H&S fires (BUY-only) | IH&S single-pattern cooldown |
| **v2.7.42 — Multi-value state trackers (non-cooldown)** | | |
| `g_swings[64]`, `g_swings_count`, `g_swings_next_idx`, `g_swings_last_update_bar` | New confirmed swing on M5 close | Tier 3 setups (Double Top/Bottom, H&S, IH&S, Trendline Bounce, S/R Flip) via `GetRecentSwings()` |
| `g_orb_window_high`, `g_orb_window_low`, `g_orb_window_locked`, `g_orb_window_day_stamp` | Each tick inside ORB window; reset on NY-local day change | `DetectOrbBreakoutEvent` |

### Pitfall: state lifecycle

State trackers must be:
- **Initialized to 0/empty** at OnInit
- **Updated synchronously** at the exact moment of the event (not retroactively from journal)
- **Queried with the 0/empty guard** — `if (tracker > 0 && ...)`

---

## §7. Cooldown pattern

**Purpose**: time-based block on re-firing the same thing too soon. A specialized Filter (§2) that uses a State tracker (§6) for the time anchor.

### Code shape

```cpp
// Cooldown: <reason — what failure mode this prevents>
if (g_sc.<setup>_cooldown_sec > 0
    && g_scalper_<setup>_last_time > 0
    && (TimeCurrent() - g_scalper_<setup>_last_time) < g_sc.<setup>_cooldown_sec
    && !CooldownBypassActive(direction, setup_type, m5_adx)) {  // v2.7.41 bypass hook
    JournalRecordSignal("SKIP", "<setup>_cooldown", ...);
    return false;
}
```

### Cooldown types in FORGE

| Type | Trigger | Anchor | Scope |
|------|---------|--------|-------|
| **Loss cooldown** (`loss_cooldown_sec`) | SL hit | `g_scalper_last_loss_time` | All setups, all directions |
| **Direction flip cooldown** (`direction_cooldown_bars`) | Direction-flip entry | `g_scalper_last_direction_time` | Cross-direction only |
| **Same-direction setup cooldown** (`breakout_same_dir_cooldown_seconds`) | Setup repeat fire | per-setup `last_buy/sell_time` | Single setup, same direction |
| **Setup-specific re-entry cooldown** (`pullback_scalp_cooldown_seconds`, `bull_day_dip_buy_reentry_cooldown_sec`) | Setup-specific completion | per-setup `last_time` | Single setup |

### Loss cooldown ≠ Win cooldown

Loss cooldowns SHOULD exist. Win cooldowns SHOULD NOT — wins are validation, not noise. v2.7.41 added the regime-aware bypass (§3) to neutralize win-driven cooldowns on trend days.

### Anti-pattern: rigid cooldown blocking trend continuation

Pre-v2.7.41, `pullback_scalp_cooldown_seconds=600` would block continuation BB_PULLBACK_SCALP BUY signals during a 70-min bull rally even when every prior leg won — exactly the case where re-firing is correct. The bypass pattern (§3) is the fix.

---

## §8. Bypass-list pattern

**Purpose**: per-setup-type whitelist that escapes a filter unconditionally. Used when a filter is correct for most setups but wrong for a specific high-confidence set.

### Code shape — helper

```cpp
// Returns true if setup_type is in the comma-separated bypass list.
// Match is whole-token (commas as delimiters), case-sensitive.
bool SetupInBypassList(const string setup_type, const string bypass_list_csv) {
    if (StringLen(bypass_list_csv) == 0) return false;
    if (StringLen(setup_type) == 0) return false;
    string padded_list  = "," + bypass_list_csv + ",";
    string padded_setup = "," + setup_type      + ",";
    return (StringFind(padded_list, padded_setup) >= 0);
}
```

### Code shape — gate integration

```cpp
// Filter with bypass-list:
if (cond_should_block && !SetupInBypassList(setup_type, g_sc.<filter>_bypass_setups)) {
    JournalRecordSignal("SKIP", "<gate_code>", setup_type, direction, ...);
    return false;
}
```

### Required parts

1. **String knob** — comma-separated list (`""` default = no bypass)
2. **Whole-token match** — wrap both sides in `,` to prevent prefix matches (`BB_BREAKOUT` shouldn't match `BB_BREAKOUT_RETEST`)
3. **Length guards** — empty-string short-circuits

### Live registry

| Bypass list | What it bypasses | Default value |
|-------------|------------------|---------------|
| `max_open_same_direction_bypass_setups` (v2.7.41) | Concurrent-open direction cap | `""` (empty) |
| `cooldown_bypass_setups` (v2.7.41) | Per-setup cooldowns (unconditional, ignores regime/ADX) | `""` (empty) |

Operators typically populate these with risk-1 setups: `"BB_BREAKOUT_RETEST,BUY_LIMIT_RECOVERY"`.

---

## §9. Knob design patterns

### Three knob shapes

| Shape | Pattern | Example | Naming |
|-------|---------|---------|--------|
| **Boolean toggle** | `_enabled` / `_required` | `breakout_use_retest`, `daily_direction_gate_enabled` | `_enabled` for opt-in features, `_required` for hard gates |
| **Numeric threshold** | `_min_X` / `_max_X` / `_X_mult` | `cooldown_bypass_min_adx`, `dump_buy_lot_factor` | Direction in suffix (`_buy`/`_sell`) always last |
| **String list** | `_setups` / `_currencies` / `_aliases` | `cooldown_bypass_setups`, `news_filter_currencies` | Comma-separated, no spaces |

### Default values — design principle

| Default | When to use |
|---------|------------|
| `0` (off / disabled) | New features. Opt-in by operator. Backward-compatible. |
| `1` (on) | Features replacing an existing default. Document the change in CHANGELOG. |
| **Safe-no-op value** (e.g. `1.0` for a multiplier) | Amplifiers where 1.0 = no effect. |

Examples:
- `cooldown_bypass_on_tp_with_trend=1` — DEFAULT ON because the old behavior is a known regression on trend days; safer to enable than disable
- `intraday_reversal_sell_enabled=0` — DEFAULT OFF because new mechanism, needs operator validation
- `scalper_lot_factor=1.0` — DEFAULT NO-OP because it's a multiplier

### Default-OFF feature checklist

Per `FORGE_NAMING_CONVENTIONS.md` §5.0.1:

1. New env knob present in `.env.example` with explanation
2. Sync mapping in `scripts/sync_scalper_config_from_env.py`
3. JSON parse in `ea/FORGE.mq5`
4. Defaults entry in `config/scalper_config.defaults.json`
5. ScalperConfig struct field initialized to safe default
6. Gate code (if introduces a new SKIP) in `config/gate_legend.json`
7. Test in `tests/api/test_forge_27x_gates.py` if it's a wired-to-Python knob

---

## §10. Anti-patterns

### 10.1 — Filter without SKIP log

```cpp
// BAD: silent block — no journal record, no observability
if (cond_block) return false;

// GOOD:
if (cond_block) {
    JournalRecordSignal("SKIP", "<gate_code>", ...);
    return false;
}
```

### 10.2 — Bypass without conditions

```cpp
// BAD: blanket bypass — defeats the gate
if (cond_block && g_sc.bypass_enabled) {
    return true;  // wrong: bypass always wins
}

// GOOD: bypass only when SPECIFIC conditions favor it
if (cond_block && !BypassActive(direction, setup_type, indicators)) {
    return false;
}
```

### 10.3 — Amplifier without safe default

```cpp
// BAD: silently doubles lot when knob set wrong
double factor = g_sc.amplifier_mult;  // if 2.0 in JSON, always 2.0
combined_lot_factor *= factor;

// GOOD: 1.0 default, conditional bump
double factor = 1.0;
if (CompositeActive() && g_sc.amplifier_mult > 1.0) {
    factor = g_sc.amplifier_mult;
}
combined_lot_factor *= factor;
```

### 10.4 — State tracker queried without 0 guard

```cpp
// BAD: cooldown active even at OnInit (tracker=0, now=huge → diff huge but < cooldown_sec)
if ((TimeCurrent() - g_tracker) < cooldown_sec) return false;

// GOOD:
if (g_tracker > 0 && (TimeCurrent() - g_tracker) < cooldown_sec) return false;
```

### 10.5 — Cooldown for wins

```cpp
// BAD (pre-v2.7.41 BB_PULLBACK_SCALP): cooldown fires regardless of outcome
g_pullback_scalp_last_buy_time = TimeCurrent();  // updated on entry

// GOOD (v2.7.41 with bypass): cooldown still fires on entry, but bypass kicks in on win
&& !CooldownBypassActive(direction, "BB_PULLBACK_SCALP", m5_adx);
```

### 10.6 — Bypass-list prefix match

```cpp
// BAD: StringFind("BB_BREAKOUT_RETEST,FOO", "BB_BREAKOUT") returns 0 = match (wrong!)
if (StringFind(bypass_list, setup_type) >= 0) return true;

// GOOD: wrap with commas for whole-token match
string padded_list = "," + bypass_list + ",";
string padded_setup = "," + setup_type + ",";
return (StringFind(padded_list, padded_setup) >= 0);
```

### 10.7 — Knob bypassing safe default to test "what if"

```cpp
// BAD: hardcode test value, ship to production
g_sc.lot_fixed = 0.5;  // test override left in

// GOOD: env-controlled with safe default
g_sc.lot_fixed = 0.02;  // safe seed; real value from JSON via sync from .env
```

---

## §11. Decision flow — how the patterns compose

```
Tick → Setup Trigger (Layer 1)
       └─ atoms fire: RSI, ADX, EMA, BB structure, PSAR …
          └─ Setup match? → YES → go to Layer 2

Setup match → Filter Chain (Layer 2)
              ├─ Filter/Gate (§2): block if cond → SKIP, return
              │  ├─ Cooldown (§7): time-based filter
              │  └─ Direction-cap, news-filter, ATR-floor, etc.
              ├─ Bypass (§3) checks: can a recent state escape any filter?
              │  └─ State tracker (§6) queried: last TP1, last loss, etc.
              └─ Bypass-list (§8): is setup_type whitelisted?

All filters pass → Composite Predicate (Layer 3)
                   └─ Composite (§5): multi-atom AND chain
                      └─ Gate composite blocks? OR amplifier composite confirms?

Geometry resolution (Layer 5)
   ├─ Lot computation: base × ScalperLotFactor × Σ(amplifiers §4) × floor
   ├─ Leg count: base_n × regime_h1_override (amplifier §4) × caps
   └─ SL/TP: ATR × geometry knobs

Place orders → State tracker updates (§6)
                ├─ g_scalper_last_<direction>_time
                ├─ g_<setup>_last_time
                └─ g_groups[gi].tp1_hit (later, on close)
```

---

## §12. When to use which pattern — decision tree

```
You want to add a new logic check. Ask:

1. Does it BLOCK a trade if a condition is true?
   YES → Filter/Gate (§2)
   NO  → continue

2. Does it ESCAPE an existing gate when a special condition holds?
   YES → Bypass (§3)  OR  Bypass-list (§8) if just a setup-type whitelist

3. Does it SCALE exposure (lot/legs) when a condition favors it?
   YES → Amplifier (§4)
   NO  → continue

4. Does it COMBINE multiple atoms into a named predicate?
   YES → Composite (§5)
   NO  → continue

5. Does it remember WHEN an event last happened?
   YES → State tracker (§6)
   NO  → continue

6. Does it block based on TIME since an event?
   YES → Cooldown (§7) — pair with a State tracker

7. None of the above?
   → You probably have a NEW pattern. Document it here.
```

---

## §13. Cross-references

- `FORGE_DECISION_STACK.md` — 5-layer entry architecture (Setup / Filter / Composite / Atoms / Geometry)
- `FORGE_NAMING_CONVENTIONS.md` — §4 env-knob naming, §4.9 scope precision
- `FORGE_REGIME_TAXONOMY.md` — regime state used by bypass conditions (§3) and amplifiers (§4)
- `docs/FORGE_INDICATOR_ATLAS.md` — atom + composite registry (§5 here)
- `docs/FORGE_LOT_SIZING_REFERENCE.md` — pipeline of amplifiers (§4 here) into final lot
- `docs/FORGE_TRAILING_ADD_LADDER_FEATURE.md` — future trailing-add ladder (combines §3, §4, §6, §7 patterns)
- `config/gate_legend.json` — gate code registry (Filter/Gate pattern §2)
- `README.md` — Documentation index

---

## §15. Layered helpers (v2.7.43)

The patterns above describe *what* shape each layer takes when inlined into a setup
dispatcher. v2.7.43 extracts the most common idioms as reusable helper functions in
`ea/FORGE.mq5`, letting a dispatch block compose layers 4 → 5 → 6 → 9 → 8 explicitly
instead of inlining each as ad-hoc code. The helpers are forward-declared near
line 1117 and defined near line 11055 (above the JsonHasKey utility block).

### Layer 4 — Atom helpers (5)

| Helper | Returns | What it asks |
|---|---|---|
| `Atom_M5AdxAbove(threshold)` | bool | Is current M5 ADX ≥ threshold? |
| `Atom_M15TrendAligned(direction, strict=false)` | bool | Is M15 EMA20–EMA50 sign aligned with direction (+1=BUY, -1=SELL)? `strict=true` rejects ties. |
| `Atom_H1TrendAligned(h1_trend_strength, direction, min_strength)` | bool | Is H1 trend strength aligned with direction AND magnitude ≥ min_strength? |
| `Atom_M5AtrPositive(m5_atr)` | bool | Sanity check: m5_atr > 0 (guard before ATR-multiplier arithmetic) |
| `Atom_M5RsiInRange(m5_rsi, lo, hi)` | bool | Is M5 RSI in [lo, hi]? |

### Layer 5 — Filter helpers (3)

Each combines an atom check with a SKIP-log emission. Caller idiom: `if(!Filter_X(...)) return;` or `bool ok = Filter_A(...) && Filter_B(...) && Filter_C(...);`

| Helper | Emits on fail | Bypass-hook |
|---|---|---|
| `Filter_AdxFloor(setup, setup_lower, dir, m5_adx, threshold, ...journal_args)` | `<setup_lower>_adx_below_min` | n/a |
| `Filter_M15TrendAligned(setup, setup_lower, dir, dir_sign, ...journal_args)` | `<setup_lower>_m15_misalign` | n/a |
| `Filter_Cooldown(setup, setup_lower, dir, last_time, cool_sec, m5_adx, ...journal_args)` | `<setup_lower>_cooldown` | calls `CooldownBypassActive(dir, setup, m5_adx)` internally per §3 |

`setup_lower` is the setup_type lowercased (e.g. `"ma_crossover"`); caller passes it
rather than runtime-lowercasing for clarity in code review.

### Layer 6 — Scoring helper (1, informational)

`Score_SetupConfidence(direction_sign, m5_adx, adx_floor, h1_trend_strength, h1_strong_threshold)` → `int` 0..100.

Weighted sum of independent atom evaluations (sum=100):
- +30 ADX ≥ floor
- +25 ADX ≥ floor + 10 (strongly above)
- +25 M15 trend aligned
- +20 H1 trend aligned with magnitude

First cut is **informational only** — logged via `PrintFormat` on TAKEN; no score-gate
yet. Future versions may add `atom.<setup>_min_score` knobs to block low-confidence
entries after operator observes score distributions in run journals.

### Layer 8 — Risk helper (1, semantic wrapper)

`Risk_ApproveLot(base_lot, combined_lot_factor_product)` → `double`.

Wraps `NormalizeLot(base_lot * combined_lot_factor)`. v2.7.43 first cut is a pure
semantic rename — no behavior change. Future versions can absorb `max_daily_drawdown`
checks, `risk_per_trade` calculation, or correlation guardrails inside this function.

### Reference implementations

v2.7.43 migrates **2 of the 14 setups** to the new helpers as reference: `MA_CROSSOVER`
(uses all three filters: AdxFloor + M15TrendAligned + Cooldown) and `INSIDE_BAR`
(AdxFloor + Cooldown only — no M15 filter). The remaining 12 setups (BB_BREAKOUT,
BB_BOUNCE, BB_PULLBACK_SCALP, MOMENTUM_DUMP, BB_BREAKOUT_RETEST, VWAP_REVERSION,
FIB_CONFLUENCE, BB_SQUEEZE, ORB, GAP_AND_GO, DOUBLE_TOP/BOTTOM, H&S/IH&S, FLAG_PENNANT,
TRENDLINE_BOUNCE, SR_FLIP, FRACTIONAL_SELL_IN_BULL, BULL_DAY_DIP_BUY) stay monolithic
for now; their migration follows the same pattern when touched.

The MA_CROSSOVER dispatch shrank from ~30 lines to ~16 lines. Net code WAS NOT smaller
(the helpers added ~150 lines) but the dispatch is now LEGIBLE in terms of the 12-layer
model: every line reads as a layer.

---

## §14. Changelog

| Date | Change |
|------|--------|
| 2026-05-12 | Initial doc. 7 core patterns catalogued (Filter, Bypass, Amplifier, Composite, State tracker, Cooldown, Bypass-list). §9 knob design. §10 anti-patterns. §11 decision flow showing pattern composition. §12 pattern selection decision tree. Cross-referenced from Decision Stack, Naming Conventions, Regime Taxonomy, Lot Sizing Reference, Trailing-Add Ladder feature doc. |
| 2026-05-12 | v2.7.42 backfill of 11 new C-extended setups (commits `04c166c`..`7d42a10`) + Phase 2 naming-convention renames (commits `21b5b8d`, `5acd97f`): §4 amplifier registry adds 12 setup-specific lot throttles (inverse-amplifier subsection); §5 composite registry adds 11 new setup-composite Det*Event helpers + setup_type strings; §6 state-tracker registry adds 28 cooldown trackers + multi-value swing-buffer + ORB-window state. All audited against §2/§3/§4/§7 patterns: 100% conformance (3+ SKIP codes each → gate_legend, CooldownBypassActive hooked per setup, safe-default 1.0 fold for all lot factors, 0-guarded cooldown queries). |
| 2026-05-12 | v2.7.43 — §15 added. Extracts Layer 4 atoms (5 helpers: `Atom_M5AdxAbove`, `Atom_M15TrendAligned`, `Atom_H1TrendAligned`, `Atom_M5AtrPositive`, `Atom_M5RsiInRange`), Layer 5 filters (3 helpers with auto-emitted SKIP codes: `Filter_AdxFloor`, `Filter_M15TrendAligned`, `Filter_Cooldown` with internal `CooldownBypassActive` hook), Layer 6 scoring (`Score_SetupConfidence` weighted sum 0..100, informational only), Layer 8 risk wrapper (`Risk_ApproveLot` semantic rename). MA_CROSSOVER + INSIDE_BAR migrated as reference implementations; other 12 setups stay monolithic for now. Tests updated to assert dispatch uses Filter_* helpers + gate codes exist in legend. |
