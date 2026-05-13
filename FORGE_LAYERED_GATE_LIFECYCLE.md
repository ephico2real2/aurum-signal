# FORGE Layered Gate Lifecycle — Runtime-Constructed SKIP Codes

**Created**: 2026-05-13
**Scope**: 20 gate codes that DO NOT appear as literal strings in `ea/FORGE.mq5` because they are constructed at emission time by the v2.7.43 layered helpers (`Filter_AdxFloor`, `Filter_M15TrendAligned`, `Filter_Cooldown`) or by the warmup gate.
**Why this doc exists**: codex's `/forge-ea-review` on 2026-05-13 flagged all 20 as "stale legend entries" because its grep-for-literal approach couldn't see runtime string construction. They are NOT stale — they are correctly wired and ready to fire. This doc is the reference that explains where/when each one emits.
**Related**: `FORGE_LOGIC_TAXONOMY.md §15`, `FORGE_REGIME_TAXONOMY.md §11.7b`, `config/gate_legend.json`.

---

## All 20 codes — one shared 3-step lifecycle

### Lifecycle

```
EA OnTick → ForgeEvalAtoms() → CheckNativeScalperSetups()
                                       │
                                       ├─ universal gates pass (spread/session/cooldown/warmup)
                                       │
                                       ▼
                            for each enabled setup:
                                       │
                          Step 1 ──► Detector function (DetectXEvent / IsXActive)
                          Step 2 ──► Filter chain (Filter_AdxFloor → Filter_M15TrendAligned → Filter_Cooldown)
                          Step 3 ──► On first-failing Filter, JournalRecordSignal("SKIP", "<constructed>", ...)
```

The 4 `warmup_*` codes use a different (earlier) lifecycle — see §3 below.

---

## §1. Filter_* helper definitions — where the codes are constructed

The 16 setup-specific codes are emitted inside three helper functions. Each helper takes a `setup_lower` argument (e.g. `"ma_crossover"`, `"inside_bar"`) and concatenates the suffix at emission time.

| Helper | Definition | Emits |
|---|---|---|
| `Filter_AdxFloor` | `ea/FORGE.mq5:11416` | `setup_lower + "_adx_below_min"` at line 11422 |
| `Filter_M15TrendAligned` | `ea/FORGE.mq5:11429` | `setup_lower + "_m15_misalign"` at line 11436 |
| `Filter_Cooldown` | `ea/FORGE.mq5:11445` | `setup_lower + "_cooldown"` at line 11456 |

### Helper internals

```cpp
// ea/FORGE.mq5:11416 — Filter_AdxFloor
bool Filter_AdxFloor(const string setup_type, const string setup_lower, const string direction,
                    const double m5_adx, const double threshold,
                    /* ... journal args ... */) {
   if(Atom_M5AdxAbove(threshold) || m5_adx >= threshold) return true;
   JournalRecordSignal("SKIP", setup_lower + "_adx_below_min", setup_type, direction, /*...*/);
   return false;
}

// ea/FORGE.mq5:11429 — Filter_M15TrendAligned
bool Filter_M15TrendAligned(const string setup_type, const string setup_lower, const string direction,
                           const int direction_sign, /* ... journal args ... */) {
   if(Atom_M15TrendAligned(direction_sign)) return true;
   JournalRecordSignal("SKIP", setup_lower + "_m15_misalign", setup_type, direction, /*...*/);
   return false;
}

// ea/FORGE.mq5:11445 — Filter_Cooldown
bool Filter_Cooldown(const string setup_type, const string setup_lower, const string direction,
                    const datetime last_time, const int cooldown_seconds, const double m5_adx,
                    /* ... journal args ... */) {
   datetime now = TimeCurrent();
   bool cool_ok = (cooldown_seconds <= 0
                   || last_time == 0
                   || (now - last_time) >= cooldown_seconds
                   || CooldownBypassActive(direction, setup_type, m5_adx));
   if(cool_ok) return true;
   JournalRecordSignal("SKIP", setup_lower + "_cooldown", setup_type, direction, /*...*/);
   return false;
}
```

The `setup_lower` argument is hardcoded at each call site (`"ma_crossover"`, `"inside_bar"`, etc.). The full code string only exists in RAM mid-call — never as a string constant in source. That's why `grep "ma_crossover_adx_below_min" ea/FORGE.mq5` returns nothing.

---

## §2. The 16 setup-specific codes — emission conditions

Each emits **only if all 4 conditions hold on the current tick**:

1. The setup is **enabled** (`g_sc.<setup>_enabled == true`) — **all default OFF today** for the 14 v2.7.42 setups
2. `Atom_M5AtrPositive(m5_atr)` — m5_atr > 0 (universal entry guard at top of every setup dispatch)
3. The setup's **detector function** returns non-zero (BUY/SELL event detected)
4. The corresponding **Filter_* helper's predicate is false**

### Code → setup → trigger map

| Gate code | Setup | Detector that must fire first | Filter that must fail |
|---|---|---|---|
| `ma_crossover_adx_below_min` | MA_CROSSOVER | `DetectMaCrossoverEvent` (M5 EMA20/50 cross + H1 trend confirmation) | `m5_adx < g_sc.ma_crossover_adx_min` |
| `ma_crossover_m15_misalign` | MA_CROSSOVER | same | M15 EMA20/50 sign disagrees with entry direction |
| `inside_bar_adx_below_min` | INSIDE_BAR | `DetectInsideBarBreakoutEvent` (bar[1] inside bar[2] + close beyond bar[1] extremes) | `m5_adx < g_sc.inside_bar_adx_min` |
| `bb_squeeze_adx_below_min` | BB_SQUEEZE | `DetectBbSqueezeBreakoutEvent` (low-pctile BB bandwidth + breakout ≥`min_breakout_atr × ATR`) | `m5_adx < g_sc.bb_squeeze_adx_min` |
| `orb_adx_below_min` | ORB | `DetectOrbBreakoutEvent` (first close beyond locked NY-window high/low) | `m5_adx < g_sc.orb_adx_min` |
| `double_top_adx_below_min` | DOUBLE_TOP | `DetectDoubleTopEvent` (2 swing highs within tolerance + intermediate swing low + neckline break) | `m5_adx < g_sc.double_pattern_adx_min` |
| `double_top_cooldown` | DOUBLE_TOP | same | `(now − g_double_top_last_time) < g_sc.double_pattern_cooldown_seconds` (and no cooldown bypass) |
| `double_bottom_adx_below_min` | DOUBLE_BOTTOM | `DetectDoubleBottomEvent` (mirror of #5) | `m5_adx < g_sc.double_pattern_adx_min` |
| `double_bottom_cooldown` | DOUBLE_BOTTOM | same | cooldown not elapsed |
| `head_and_shoulders_adx_below_min` | HEAD_AND_SHOULDERS | `DetectHeadAndShouldersEvent` (L–H–LH swing pattern + neckline break) | `m5_adx < g_sc.hs_adx_min` |
| `head_and_shoulders_cooldown` | HEAD_AND_SHOULDERS | same | cooldown not elapsed |
| `inverse_head_and_shoulders_adx_below_min` | INVERSE_HEAD_AND_SHOULDERS | `DetectInverseHeadAndShouldersEvent` (mirror) | `m5_adx < g_sc.hs_adx_min` |
| `inverse_head_and_shoulders_cooldown` | INVERSE_HEAD_AND_SHOULDERS | same | cooldown not elapsed |
| `flag_pennant_adx_below_min` | FLAG_PENNANT | `DetectFlagPennantEvent` (impulse ≥`impulse_min_atr × ATR` + consolidation + breakout) | `m5_adx < g_sc.flag_pennant_adx_min` |
| `trendline_bounce_adx_below_min` | TRENDLINE_BOUNCE | `DetectTrendlineBounceEvent` (algorithmic trendline + bounce in trendline-aligned direction) | `m5_adx < g_sc.trendline_adx_min` |
| `sr_flip_adx_below_min` | SR_FLIP | `DetectSrFlipEvent` (S/R level breaks → retests as opposite role → continues) | `m5_adx < g_sc.sr_flip_adx_min` |

### Per-setup dispatch flow (typical)

The dispatch block for each setup (with INSIDE_BAR as the canonical example) sits inside `CheckNativeScalperSetups`:

```cpp
// ea/FORGE.mq5 — typical layered dispatch (v2.7.43 pattern)
if(direction == "" && g_sc.inside_bar_enabled && Atom_M5AtrPositive(m5_atr)) {
   int ib_event = DetectInsideBarBreakoutEvent(m5_atr);
   if(ib_event != 0) {
      string ib_dir = (ib_event > 0) ? "BUY" : "SELL";
      datetime ib_last = (ib_event > 0) ? g_inside_bar_last_buy_time : g_inside_bar_last_sell_time;
      bool ok = Filter_AdxFloor("INSIDE_BAR","inside_bar", ib_dir, m5_adx, g_sc.inside_bar_adx_min, /*...*/)
             && Filter_Cooldown("INSIDE_BAR","inside_bar", ib_dir, ib_last, g_sc.inside_bar_cooldown_seconds, m5_adx, /*...*/);
      if(ok) {
         direction  = ib_dir;
         setup_type = "INSIDE_BAR";
         // ... geometry + state update ...
      }
   }
}
```

The `Filter_AdxFloor` call constructs `"inside_bar_adx_below_min"` only if its predicate fails; otherwise nothing is emitted.

### Single-direction setups note

For `DOUBLE_TOP`, `DOUBLE_BOTTOM`, `HEAD_AND_SHOULDERS`, `INVERSE_HEAD_AND_SHOULDERS`, the cooldown tracker is a single `g_<setup>_last_time` (not per-direction `_buy_time` / `_sell_time` pair). The `Filter_Cooldown` helper takes the single datetime as `last_time`, so the same helper works for both bidirectional and single-direction setups.

---

## §3. The 4 `warmup_*` codes — different lifecycle

These emit at a completely different stage — top-of-dispatch, BEFORE any setup runs. The dispatch path is:

```cpp
// ea/FORGE.mq5:7935-7948
string warmup_reason = "";
if(!ForgeNativeScalperWarmupOk(warmup_reason)) {
   g_warmup_last_ok = false;
   g_warmup_last_reason = warmup_reason;
   datetime m5bar_w = iTime(_Symbol, PERIOD_M5, 0);
   if(m5bar_w != g_scalper_last_warmup_log_bar) {
      g_scalper_last_warmup_log_bar = m5bar_w;
      JournalRecordSignal("SKIP", "warmup_" + warmup_reason, "", "", /*...*/);
   }
   return;
}
```

`ForgeNativeScalperWarmupOk()` sets `warmup_reason` to a short string describing what's still cold. The four legend entries map 1:1:

| Code | When `warmup_reason` becomes this | What it means |
|---|---|---|
| `warmup_m15_bars` | Live mode: M15 bar count since EA init < `ScalperLiveWarmupM15Bars` (typical 10) | Need ~10 closed M15 bars before live trading; M15 indicator history not yet populated |
| `warmup_h1_bars` | H1 bar history not warm | Same idea, H1 timeframe |
| `warmup_h4_bars` | H4 bar history not warm | Same idea, H4 timeframe |
| `warmup_tester_m5_rollovers` | Strategy Tester: M5 bar rollovers since init < `ScalperTesterWarmupM5Bars` | Tester needs N M5 bars before entries are allowed |

### When they fire

- **Live**: in the first ~10 minutes after EA load (until enough M15 bars close). Once `g_warmup_last_ok = true`, they stop emitting for the rest of the EA session.
- **Tester**: in the first N M5 bar rollovers of every backtest run. Same sticky-once-true behavior.

### gate_legend.json wildcard

These are covered by the `warmup_*` wildcard pattern in `config/gate_legend.json:_patterns`, so the literal entries (`warmup_m15_bars`, `warmup_h1_bars`, `warmup_h4_bars`, `warmup_tester_m5_rollovers`) serve as **human-readable explanations** the dashboard shows, not as completeness guarantees. The wildcard makes the gate-legend check pass even if a new `warmup_*` sub-reason ships without a literal entry.

---

## §4. Why these codes never appear in current production data

### The 16 setup codes

All 14 v2.7.42 setups (MA_CROSSOVER, VWAP_REVERSION, FIB_CONFLUENCE, INSIDE_BAR, BB_SQUEEZE, ORB, GAP_AND_GO, DOUBLE_TOP, DOUBLE_BOTTOM, HEAD_AND_SHOULDERS, INVERSE_HEAD_AND_SHOULDERS, FLAG_PENNANT, TRENDLINE_BOUNCE, SR_FLIP) are **default OFF** in `config/scalper_config.defaults.json:setup.*_enabled = 0`. The dispatch never enters the detector branch → the Filter chain never runs → the codes never emit.

They are **armed but cold**. The moment an operator sets `FORGE_SETUP_<NAME>_ENABLED=1` in `.env`, the corresponding chain becomes active and the codes start flowing for that setup.

### The 4 warmup codes

They emit only at the very start of every backtest or after every EA reload in live. After warmup completes, `g_warmup_last_ok = true` and these codes are silent for the rest of the run.

---

## §5. Validation — verifying a code is correctly wired

To prove that a code like `inside_bar_adx_below_min` will fire when the setup is enabled, audit the chain:

1. **Find the `setup_lower` argument** — grep for the call site:
   ```bash
   grep -nE 'Filter_AdxFloor\("INSIDE_BAR"' ea/FORGE.mq5
   ```
   Should show `Filter_AdxFloor("INSIDE_BAR","inside_bar", ...)`.

2. **Confirm the lowercase tag concatenates to the legend key**:
   `"inside_bar" + "_adx_below_min"` = `"inside_bar_adx_below_min"` — must match the key in `config/gate_legend.json`.

3. **Confirm the helper is called**: the dispatch block for INSIDE_BAR must reach the `Filter_AdxFloor` call when the detector returns non-zero.

4. **Confirm the setup's enable flag is wired**: `g_sc.inside_bar_enabled` must be parsed from `scalper_config.json:setup.inside_bar_enabled`.

5. **Confirm operator opt-in path**: `FORGE_SETUP_INSIDE_BAR_ENABLED=1` in `.env` resolves through `sync_scalper_config_from_env.py` to set the JSON key.

If all 5 steps verify, the code is reachable and the legend entry is real.

---

## §6. Programmatic reachability check ✅ SHIPPED v2.7.52

**Status**: SHIPPED 2026-05-13. Two tests in `tests/api/test_forge_27x_gates.py`:
- `test_gate_legend_entries_reachable_in_EA` — every legend key must be reachable from EA source via one of: direct literal, indirect literal (assigned to a variable like `_qreason`), Filter_*-constructed, or wildcard pattern match
- `test_filter_helper_call_sites_have_legend_coverage` — every Filter_* call site must produce a code that has a legend entry (catches the reverse drift: new setup added but legend entry forgotten)

Both run in `pytest -q` on every commit. Drift between EA emission and legend entries is now a hard CI failure rather than a quarterly review finding.

### Implementation (for reference)

The test covers four reachability classes:

```python
def test_gate_legend_entries_reachable_in_EA(ea_src, gate_legend):
    """Every gate_legend entry must be reachable: either a literal SKIP emission
    OR a Filter_*-constructed code from a call site in EA. Catches stale entries
    early instead of waiting for /forge-ea-review."""
    import re
    literal = set(re.findall(
        r'JournalRecordSignal\(\s*"SKIP"\s*,\s*"([a-z_][a-z0-9_]+)"', ea_src))
    adx  = re.findall(r'Filter_AdxFloor\(\s*"[A-Z_]+"\s*,\s*"([a-z_][a-z0-9_]+)"', ea_src)
    cool = re.findall(r'Filter_Cooldown\(\s*"[A-Z_]+"\s*,\s*"([a-z_][a-z0-9_]+)"', ea_src)
    m15  = re.findall(r'Filter_M15TrendAligned\(\s*"[A-Z_]+"\s*,\s*"([a-z_][a-z0-9_]+)"', ea_src)
    constructed = (
        {f"{s}_adx_below_min" for s in adx}
        | {f"{s}_cooldown" for s in cool}
        | {f"{s}_m15_misalign" for s in m15}
    )
    reachable = literal | constructed
    legend_keys = {k for k in gate_legend if not k.startswith('_')}
    patterns = list(gate_legend.get('_patterns', {}).keys())
    def matches_pattern(code, pats):
        return any(p.endswith('_*') and code.startswith(p[:-1]) for p in pats)
    stale = sorted(k for k in legend_keys
                   if k not in reachable and not matches_pattern(k, patterns))
    assert not stale, f"gate_legend.json has {len(stale)} stale entries: {stale}"
```

This runs every commit. A truly stale legend entry (someone removed a `Filter_AdxFloor` call site but forgot to remove the legend entry) becomes a hard CI failure, not a quarterly review finding.

---

## §7. Implications for `/forge-ea-review`

The 2026-05-13 codex run flagged these 20 codes as a WARNING-class "stale" finding. That's a false positive — the codes are correctly wired and will emit when the upstream conditional gates fire.

The `/forge-ea-review` SKILL.md (Mandatory Check B) was updated on 2026-05-13 to enumerate BOTH literal `JournalRecordSignal` strings AND runtime-constructed codes from Filter_* call sites. Future review runs should not repeat the false positive.

---

## §8. Changelog

| Date | Change |
|---|---|
| 2026-05-13 | Initial doc. Created after `/forge-ea-review` flagged the 20 codes as false-positive WARNING. Documents the v2.7.43 layered-helper code-construction pattern, the warmup gate's wildcard pattern, the 5-step reachability validation, and a recommended pytest test to harden the gate-legend reachability check in CI. |
