# FORGE Setup Playbook — Built-in Native Setup Classifications

> **Current as of**: FORGE v2.7.32 (2026-05-11)
> **Purpose**: Single-pane catalog of every setup type FORGE detects natively, with direction, intent, SL/leg geometry, cascade behavior, and active status. Use this as the canonical reference when reading the EA, configuring `.env`, or analyzing tester runs.

---

## 1. Setup Classification Matrix (5 types × 2 directions = 10 entry signatures)

| # | `setup_type` | Direction | Intent | SL × ATR | Leg cap | Cascade? | Status |
|---|---|---|---|---|---|---|---|
| 1 | **BB_BREAKOUT** | BUY | Strong upward thrust through BB upper band | 3.0× (×1.25 boost in high_vol) | 10 | ✓ SELL STOP CONT + BUY LIMIT recovery | v2.6+ active |
| 2 | **BB_BREAKOUT** | SELL | Strong downward thrust through BB lower band | 2.0× | 10 | ✓ same | v2.6+ active |
| 3 | **BB_BREAKOUT_RETEST** | BUY | Re-entry after BB_BREAKOUT retests band | inherits BREAKOUT | inherits | inherits | v2.7.x active |
| 4 | **BB_BREAKOUT_RETEST** | SELL | Mirror | inherits | inherits | inherits | v2.7.x active |
| 5 | **BB_BOUNCE** | BUY | Mean-reversion at BB lower band (oversold) | 1.5× | 5 (capped `when_unclear`) | ✗ no cascade | v2.6+ active |
| 6 | **BB_BOUNCE** | SELL | Mean-reversion at BB upper band (overbought) | 1.5× | 5 | ✗ | v2.6+ active |
| 7 | **MOMENTUM_DUMP** | SELL | Sharp ≥1.5×ATR drop within N bars (fast scalp) | **4.0×** (v2.7.32) | **2** (hotfix from 5) | ✗ skipped at `:7549` | v2.7.28 added, v2.7.32 hotfixed |
| 8 | **MOMENTUM_DUMP** | BUY | Mirror — sharp upward impulse | 4.0× | 2 | ✗ | same |
| 9 | **BB_PULLBACK_SCALP** | BUY | Fresh-PSAR-flip pullback bottom in bull trend (additive, fires where v2.7.26 PSAR blocks BB_BOUNCE) | 2.5× (env) | 2 | ✗ | v2.7.31 added |
| 10 | **BB_PULLBACK_SCALP** | SELL | Mirror — pullback top in bear trend | 2.5× | 2 | ✗ | v2.7.31 added |

---

## 2. Detection Sites (where each setup is identified in the EA)

```
BB_BOUNCE          — FORGE.mq5:5891 (BUY)   /  :5943 (SELL)
BB_BREAKOUT        — FORGE.mq5:~6188 (BUY)  / :~6509 (SELL)
BB_BREAKOUT_RETEST — FORGE.mq5 retest re-arm logic (post-BREAKOUT TP1 hit)
MOMENTUM_DUMP      — FORGE.mq5:6604 (SELL dump_sell_trig) / :6669 (BUY dump_buy_trig)
BB_PULLBACK_SCALP  — FORGE.mq5:5911 (BUY fork) / :5958 (SELL fork)
                     Fires INSIDE the v2.7.26 PSAR-misalign block when fresh PSAR flip
                     + h1_trend aligned + ADX < 30 (otherwise existing SKIP still fires).
```

---

## 3. Direction-Correctness Lens — Which Setup Catches Which Market

| Market action | Setup that catches |
|---|---|
| Sustained up-trend, breakout | BB_BREAKOUT BUY → 10 legs + TP4/TP5 staging in TREND_BULL |
| Sustained up-trend, pullback to lower band | BB_BOUNCE BUY (if PSAR aligned) OR BB_PULLBACK_SCALP BUY (fresh-flip exception, additive) |
| Sustained down-trend, breakout | BB_BREAKOUT SELL |
| Sustained down-trend, bounce up to upper band | BB_BOUNCE SELL OR BB_PULLBACK_SCALP SELL |
| Sharp counter-impulse (fast dump in bull, fast rip in bear) | MOMENTUM_DUMP SELL / MOMENTUM_DUMP BUY |
| Range / chop | (none — blocked by `dump_chop_block` v2.7.32; leg-cap `native_legs_max_when_unclear=5` for BB) |

---

## 4. Roadmap Setups (designed but NOT YET coded)

| setup_type | Direction | Intent | Proposed | Status |
|---|---|---|---|---|
| **TREND_PULLBACK_SHORT** | SELL | Counter-trend scalp on slow-drift days (counter to confirmed bull, 2-bar pullback signature) | Run 18 Issue 5 | DESIGN ONLY — v2.7.33+ candidate |
| **TREND_PULLBACK_LONG** | BUY | Mirror | Run 18 Issue 5 | DESIGN ONLY |
| **BB_MIDLINE_OSCILLATOR** | BUY/SELL | High-frequency BB midline cross scalper (5-12 fires/day on M5) | Run 18 Issue 6 | DESIGN ONLY — ~300 LOC proposed |

---

## 5. v2.7.32 Geometry Quick Reference

```
                       Initial SL   TP1       TP2       Lot factor   Leg cap   ATR trail
BB_BREAKOUT BUY        3.0×ATR      0.5×ATR   1.5×ATR   1.0          10        post-TP1 ATR ratchet
BB_BREAKOUT SELL       2.0×ATR      0.4×ATR   1.5×ATR   1.0          10        same
BB_BOUNCE BUY/SELL     1.5×ATR      mid       upper/lo  bounce_factor 5         BE-cushion based
MOMENTUM_DUMP BUY/SELL 4.0×ATR ⚠    0.4×ATR   1.0×ATR   0.5          2 ⚠       ATR-trail
BB_PULLBACK_SCALP BUY/SELL  2.5×ATR  0.3×ATR  0.7×ATR   0.5          2         ATR-trail

⚠ = v2.7.32 hotfix values (was 1.5×ATR / 5 legs in v2.7.28-2.7.31)
```

---

## 6. Optional / Default-OFF Gates (Op-In via `.env`)

| Knob | Affects | Purpose | Default |
|---|---|---|---|
| `FORGE_DAILY_DIRECTION_GATE_ENABLED=1` | BB_BREAKOUT + BB_BOUNCE BUY/SELL | Filter 1: block BUYs in daily-bear, SELLs in daily-bull (G5048 fix v2.7.27) | ON (this run) |
| `FORGE_REGIME_H1_OVERRIDE_FACTOR=2.0` | All setups (via regime label) | H1-strong override: unlock TREND_BULL/BEAR when H1 strong + M5 ADX high (v2.7.29) | ON |
| `FORGE_DUMP_CATCH_ENABLED=1` | MOMENTUM_DUMP | Master switch for dump-catch (v2.7.28) | ON |
| `FORGE_PULLBACK_SCALP_ENABLED=1` | BB_PULLBACK_SCALP | Master switch for additive pullback fork (v2.7.31) | ON |
| `FORGE_DUMP_REQUIRE_BAR_CONFIRM=0` | MOMENTUM_DUMP | Option B: require prior closed bar direction confirmation (v2.7.32, DOCUMENTED FOR LATER VALIDATION) | OFF |

---

## 7. SKIP Gate Codes by Setup

| Setup | Common SKIP codes that block it |
|---|---|
| BB_BREAKOUT BUY/SELL | `entry_quality_atr_ext`, `entry_quality_breakout_failed_samebar`, `entry_quality_psar_misalign_*`, `entry_quality_daily_*_block_*`, `entry_quality_breakout_cooldown`, `rr_too_low`, `entry_quality_rsi_buy_ceil`, `entry_quality_rsi_sell_floor`, `entry_quality_adx_min_*`, `entry_quality_bb_contraction` |
| BB_BOUNCE BUY/SELL | `entry_quality_psar_misalign_*` (v2.7.26), `entry_quality_daily_*_block_*` (v2.7.27), `entry_quality_rsi_*`, `entry_quality_body` |
| MOMENTUM_DUMP BUY/SELL | `dump_rsi_block`, `dump_adx_block`, `dump_psar_block`, `dump_d1_bias_block`, `dump_cooldown`, **`dump_chop_block`** (v2.7.32 RANGE regime), **`dump_bar_confirm_missing`** (v2.7.32 Option B, default OFF) |
| BB_PULLBACK_SCALP | Falls through from BB_BOUNCE PSAR-misalign block; gated by `pullback_scalp_enabled` + fresh-PSAR-flip + h1_trend alignment + ADX < `pullback_scalp_max_adx` + cooldown |

Full legend: [`config/gate_legend.json`](config/gate_legend.json).

---

## 8. Version History of Setup Additions

| Version | Setup added | Purpose |
|---|---|---|
| v2.6.x | BB_BREAKOUT BUY/SELL, BB_BOUNCE BUY/SELL | Foundation — Bollinger Band breakout + mean reversion |
| v2.7.x early | BB_BREAKOUT_RETEST BUY/SELL | Re-entry after retesting band post-TP1 |
| **v2.7.28** | **MOMENTUM_DUMP SELL/BUY** | Catch sharp counter-impulses (fast dumps in bull, fast rips in bear) |
| **v2.7.31** | **BB_PULLBACK_SCALP BUY/SELL** | Additive: catches v2.7.26-PSAR-blocked BB_BOUNCEs with stricter own gates (fresh PSAR flip + h1 aligned + ADX < 30) |
| v2.7.32 hotfix | (no new setup) | MOMENTUM_DUMP SL 1.5→4.0×ATR, leg-cap 5→2 for scalps, RANGE regime block, Option B direction-confirm coded default-OFF |

---

## 9. Authoritative Code References

- **EA source**: [`ea/FORGE.mq5`](ea/FORGE.mq5)
- **Active config**: [`config/scalper_config.json`](config/scalper_config.json) (env overrides applied)
- **Default config**: [`config/scalper_config.defaults.json`](config/scalper_config.defaults.json)
- **Env sync mapping**: [`scripts/sync_scalper_config_from_env.py`](scripts/sync_scalper_config_from_env.py)
- **Env cheat sheet**: [`.env.example`](.env.example)
- **Gate legend**: [`config/gate_legend.json`](config/gate_legend.json)
- **Regime predictor design (v2.7.33+ ONNX roadmap)**: [`docs/FORGE_REGIME_PREDICTOR_DESIGN.md`](docs/FORGE_REGIME_PREDICTOR_DESIGN.md)
- **Run analyses**: [`docs/FORGE_RUN17_ANALYSIS.md`](docs/FORGE_RUN17_ANALYSIS.md), [`docs/FORGE_RUN18_ANALYSIS.md`](docs/FORGE_RUN18_ANALYSIS.md), [`docs/FORGE_RUN19_ANALYSIS.md`](docs/FORGE_RUN19_ANALYSIS.md), [`docs/FORGE_RUN20_ANALYSIS.md`](docs/FORGE_RUN20_ANALYSIS.md)

---

## 10. Boolean Composite Design Pattern (going-forward standard for new setups)

Every new setup proposed/implemented for FORGE must follow this design pattern. The pattern is the
canonical bridge between **market observation → composite specification → MQL5 code**.

### Step 1 — Indicator inventory check (mandatory)

Before designing, read [`docs/FORGE_INDICATOR_ATLAS.md`](docs/FORGE_INDICATOR_ATLAS.md) §1
(indicator inventory) and §11 (scribe DB inventory). The atlas lists ~28 FORGE indicators
with `ea/FORGE.mq5:NNNN` cites and SIGNALS-table population status. Reuse atoms from the
~10 already-validated composites in §5 of the atlas where applicable.

### Step 2 — Build the composite as a boolean

Express the entry condition as a single boolean expression using existing globals:

```mql5
bool NEW_SETUP_NAME =
     (h1_trend_strength       >= 0.5)              // existing global (FORGE.mq5:5770)
  && (g_regime_label IN ["TREND_BULL", "VOLATILE"])
  && (m5_rsi >= 30 && m5_rsi <= 50)
  && (price <= m5_bb_m + 0.5 * m5_atr)
  && /* ... */ ;
```

Group atoms by purpose (MACRO / DAILY / DIP-ENTRY / TREND HEALTH / etc.) with comments.
Use 8-12 atoms typical — fewer is fragile, more is over-fit.

### Step 3 — Cross-day validation (mandatory before shipping)

A composite that catches the right entries on ONE day is not a strategy. Validate on 2-3
different days of the same type:
- Run truth-table eval at each candidate hour (see atlas §5.1 for the format)
- Confirm the composite says TAKE at the hours that historically had successful entries
- Confirm the composite says SKIP at the hours that would have been losers

If a single composite doesn't generalize, either narrow scope (multiple composites per day-type)
or relax the strictest atom — DO NOT silently over-fit to one day.

### Step 4 — Map atoms to FORGE source (mandatory)

Every atom must cite `ea/FORGE.mq5:NNNN` for existing globals, or be marked **add** with
proposed location for new state. Atlas §1 has the full inventory.

### Step 5 — Translate to MQL5 (entry trigger or filter chain)

Two patterns for MQL5 translation:

**Pattern A — New setup type (NEW entry trigger function)**

```mql5
// In ScalperEvaluate() around line 5870 (after existing setup triggers)
if (NEW_SETUP_NAME && direction == "") {
    direction  = "BUY";
    setup_type = "NEW_SETUP_NAME";
    sl  = NormalizeDouble(bid - m5_atr * SL_ATR_MULT, _Digits);
    tp1 = NormalizeDouble(ask + m5_atr * TP1_ATR_MULT, _Digits);
    tp2 = NormalizeDouble(ask + m5_atr * TP2_ATR_MULT, _Digits);
}
```

Use this when the setup represents a NEW entry CONDITION not covered by existing triggers
(e.g. `CHOP_IN_BULL_TREND_BUY`, `TREND_CONTINUATION_BUY`).

**Pattern B — Filter insert (block existing setup)**

```mql5
// In existing filter chain (e.g. MOMENTUM_DUMP SELL chain around line 6750)
} else if (BLOCK_COMPOSITE_NAME) {
    JournalRecordSignal("SKIP", "block_reason_code", "MOMENTUM_DUMP", "SELL",
       mid, spread, m5_atr, m5_rsi, m5_adx, m5_bb_u, m5_bb_l, m5_bb_m, 0,
       h1_trend_strength, 0);
}
```

Use this when the composite represents a BLOCK condition (e.g. `BLOCK_SELL_IN_CHOP`,
`FRACTIONAL_SELL_IN_BULL`).

### Step 6 — Wire env knobs + sync mapping

For every NEW setup, add:
- Env knob bundle: `FORGE_<SETUP>_ENABLED=0` (default OFF), tuning knobs (TP, SL, lot factor)
- Struct fields in `g_sc` (ea/FORGE.mq5 ~line 350-450)
- Defaults in defaults block (~line 2900)
- ReadConfig JsonHasKey reads (~line 3300-3500)
- Sync mapping in `scripts/sync_scalper_config_from_env.py`
- New gate codes in `config/gate_legend.json`

### Step 7 — Register in indicator atlas

After ship, append to `docs/FORGE_INDICATOR_ATLAS.md`:
- §5 — composite registry entry with calibration history
- §6 — day-type coverage row
- §10 — changelog one-liner

### Step 8 — Post-mortem hook (when live trades execute)

After a live trade with this setup closes, query scribe (per atlas §12) to evaluate:
- `forge_signals × market_snapshots` — were the indicator values close to what the composite expected?
- `trade_groups` — what was the realized P&L vs the modeled expectation?
- `market_regimes.feature_json` — did the regime classifier agree at trade time?

If post-mortem reveals consistent deviation, re-calibrate the composite (atlas §5
calibration history) — analysis-first, not blindly tune.

---

## 11. Cross-document map

| Document | Purpose |
|---|---|
| [`FORGE_SETUP_PLAYBOOK.md`](FORGE_SETUP_PLAYBOOK.md) (this) | Canonical setup type catalog + composite design pattern |
| [`docs/FORGE_INDICATOR_ATLAS.md`](docs/FORGE_INDICATOR_ATLAS.md) | Indicator inventory + composite registry + scribe schema |
| [`config/gate_legend.json`](config/gate_legend.json) | SKIP-reason codes (gate dictionary) |
| [`docs/FORGE_TESTER_JOURNAL_QUERIES.md`](docs/FORGE_TESTER_JOURNAL_QUERIES.md) | Query cheat sheet for tester DB |
| [`.claude/skills/forge-monitor/SKILL.md`](.claude/skills/forge-monitor/SKILL.md) | Monitoring workflow + analytical protocol |
| `docs/FORGE_RUN<N>_ANALYSIS.md` | Per-run analysis with TAKEN/Losses/Recommendations/Q&A |

---

## 12. Changelog (this document)

| Date | Author | Change |
|------|--------|--------|
| 2026-05-11 | Operator + monitoring agent | Initial draft — 5 setup types × 2 directions × v2.7.32 geometry |
| 2026-05-12 | Boolean composite design pattern (§10) added — mandatory standard for all new setups. Cross-document map (§11) added. References indicator atlas + scribe schema (§11 + §12 in atlas). |
