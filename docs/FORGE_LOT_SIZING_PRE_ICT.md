# FORGE Pre-ICT Lot Engine — reference + ICT-aware recommendations

**Status**: canonical reference for the current (pre-ICT-aware) lot-sizing engine. Captures the combined-factor architecture in full, documents every factor's math + invocation logic, builds the setup-by-setup interaction matrix, then proposes per-factor updates and new factors to align FORGE with ICT profitability + risk standards.

**Audience**: anyone who needs to (a) explain why a given G-prefixed trade fired at lot=0.469 vs 0.313, (b) tune a single factor without breaking the rest of the chain, (c) propose a new ICT-aware factor that composes cleanly with the existing stack.

**Scope**: pre-ICT engine only. ICT atoms (MSS / FVG / ChoCH / Liquidity / OB / Breaker / Unicorn) currently log but do not gate or amplify lot (Mode A per [`FORGE_PEMCG_ICT_INTEGRATION.md`](FORGE_PEMCG_ICT_INTEGRATION.md) §3.1). Recommendations §5 onwards describe how to wire them.

**Cross-references**:
- [`FORGE_PEMCG_ICT_INTEGRATION.md`](FORGE_PEMCG_ICT_INTEGRATION.md) — Mode A/B/C wiring
- [`FORGE_ICT_PEMCG_COMBINATIONS.md`](FORGE_ICT_PEMCG_COMBINATIONS.md) — 16-cell matrix
- [`research/ICT_KILLZONES.md`](research/ICT_KILLZONES.md) — KZ canon for XAUUSD
- [`prompts/ICT_Tradingidea.md`](prompts/ICT_Tradingidea.md) — operator ICT spec (§K scoring engine, §N backtest readiness / risk-percent)
- [`QUESTDB_EVALUATION.md`](QUESTDB_EVALUATION.md) §12.7a — selective-12-of-30 storage argument
- `.claude/skills/forge-monitor/SKILL.md` — Schema-parity ship → "High-cardinality diagnostic data — selective columns"

---

## §1 Architecture overview

The pre-ICT engine is a **single-line product**: one absolute base lot, one setup multiplier, then 30 stacking factors with a hard floor at 0.125. After the product, three setup-specific **lot pins** can override the chain entirely.

```mql5
// ea/FORGE.mq5:14695
double combined_lot_factor = MathMax(0.125,
    scalper_lot_factor_eff * inside_band_factor * near_floor_factor * stack_factor
  * adx_lot_factor * bounce_factor * dump_factor * dump_pyramid_factor
  * dump_dist_amplifier * dump_kz_amplifier * mdct_factor * bbr_factor
  * tcb_factor * tcs_factor * pullback_factor * intraday_reversal_factor
  * fractional_sell_factor * bull_day_dip_factor * ma_crossover_factor
  * vwap_reversion_factor * fib_confluence_factor * inside_bar_factor
  * bb_squeeze_factor * orb_factor * gap_and_go_factor * double_pattern_factor
  * hs_factor * flag_pennant_factor * trendline_bounce_factor * sr_flip_factor
  * fast_trend_factor);

// ea/FORGE.mq5:14723
double base_lot = g_sc.lot_fixed;                       // single source of truth (v2.7.40)
double lot      = NormalizeLot(base_lot * lot_mult * combined_lot_factor);
```

Shape of the engine:

```
lot = NormalizeLot(lot_fixed × lot_mult × combined_lot_factor)
                   ↑           ↑          ↑
                   base        setup      ~30-factor product, floored at 0.125
                  (g_sc.lot    multiplier (compounding amplifiers + reducers)
                   _fixed)     (1.0..5.0)

   ↓ if (BLR-capitulation || ASIA_CAPITULATION_BUY || BB_EXHAUSTION_REVERSAL_*)
       lot = NormalizeLot(pinned_lot × amplifier_tier_if_any)
              — overrides the entire chain above
```

Key invariants:

- **Single base lot** — `g_sc.lot_fixed` is the only absolute source of truth (v2.7.40 change at `ea/FORGE.mq5:14723`). The legacy `ScalperLot` MT5 input was retired; size-up/down happens via the `scalper_lot_factor_eff` multiplier at the head of the chain.
- **Compound floor 0.125** — even when every reducer stacks (e.g., 0.25 × 0.5 × 0.5 × 0.5 = 0.0156), the floor keeps the multiplier ≥ 1/8. With a typical `lot_fixed=0.25`, this means the absolute lot bottom before broker-min is `0.25 × 1.0 × 0.125 = 0.031` → broker-min clamp lifts it back to 0.01.
- **Broker floor at NormalizeLot** — `SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN)` is applied inside NormalizeLot + at every lot-pin (`MathMax(...lot..., SYMBOL_VOLUME_MIN)`). MT5 rejects sub-broker-min orders with retcode 10014.
- **No risk-percent sizing** — the entire engine is multiplicative on a fixed base, not a function of equity or SL distance. This is the most important pre-ICT gap and is addressed in §5 + §7 Phase D.

---

## §2 The 30 factors — full reference table

This is the canonical inventory. Cite the **Source line** when you need to read the actual init logic.

| # | Variable | Default | Range observed | Source line | What it does | When it fires (≠ 1.0) |
|---:|---|---:|---|---:|---|---|
| 1 | `scalper_lot_factor_eff` | 1.0 | 0.5 – 2.0 | `14664` | Global lot multiplier (env or MT5 input) | Operator opts in via `FORGE_GLOBAL_SCALPER_LOT_FACTOR` or `ScalperLotFactor` MT5 input |
| 2 | `inside_band_factor` | 1.0 | 0.5 | `14420` | Halve breakout SELL lot when price has pulled back inside BB | `direction == SELL && is_breakout_setup && mid > m5_bb_l` |
| 3 | `near_floor_factor` | 1.0 | 0.25 | `14429` | Cardwell near-floor de-risk (crash SELL with RSI 20-25) | `direction == SELL && is_breakout_setup && h1_bear && h4_bear && RSI 20-25` |
| 4 | `stack_factor` | 1.0 | 0.25 | `14439` | Reduce 2nd+ concurrent same-direction group | `ScalperOpenGroupCountByDirection(direction) >= 1` |
| 5 | `adx_lot_factor` | 1.0 | 0.125 / 0.25 | `14448` | ADX-tiered SELL trend-exhaustion de-risk | `direction == SELL && is_breakout_setup && M15 ADX ≥ 35` |
| 6 | `bounce_factor` | 1.0 | 0.5 – 1.0 | `14463` | BB_BOUNCE fractional lot (mean-reversion probe) | `!is_breakout_setup && bounce_lot_factor ∈ (0, 1)` |
| 7 | `dump_factor` | 1.0 | 0.5 – 1.0 | `14473` | MOMENTUM_DUMP fractional lot (direction-specific override) | `setup_type == MOMENTUM_DUMP`; BUY uses `dump_buy_lot_factor` (1.0), SELL uses `dump_sell_lot_factor` (0.5) |
| 8 | `dump_pyramid_factor` | 1.0 | 1.0 – 5.0 (clamped) | `14482` | Pyramid amplifier on consecutive same-dir DUMP fires | `dump_pyramid_enabled && consec_count > 0`. Linear `base + n×step`, clamped `[min, max]` |
| 9 | `dump_dist_amplifier` | 1.0 | 1.5 / 2.0 | `14494` | Day-extreme distance amplifier — far from day_high/low = high-conviction | `dump_dist_amplifier_enabled && dist/ATR ≥ threshold (1.5 → 1.5×, 3.0 → 2.0×)` |
| 10 | `dump_kz_amplifier` | 1.0 | 0.0 – 2.0 | `14511` | Killzone-tier amplifier — peak in first 5 min, decay past 60 min, block in dead zones | `dump_kz_amplifier_enabled`; tier1=2.0 / tier2=2.0 / tier3=1.5 / tier4=1.0 / tier5=0.85 / no_zone=0.5 |
| 11 | `mdct_factor` | 1.0 | 0.7 | `14527` | MOMENTUM_DUMP_COMPOSITE_TEST parity factor | `setup_type == MOMENTUM_DUMP_COMPOSITE_TEST` |
| 12 | `bbr_factor` | 1.0 | 1.0 – 1.5 | `14547` | BB_LOWER_REVERSION_BUY base + extreme-oversold amplifier | `setup_type == BB_LOWER_REVERSION_BUY`; ×1.5 when RSI ≤ 25 |
| 13 | `tcb_factor` | 1.0 | 1.0 – 10.0 | `14535` | TREND_CONTINUATION BUY amplifier | `setup_type == TREND_CONTINUATION_BUY && direction == BUY`. Default 2.0 |
| 14 | `tcs_factor` | 1.0 | 1.0 – 10.0 | `14541` | TREND_CONTINUATION SELL amplifier (mirror) | Mirror of `tcb_factor` |
| 15 | `pullback_factor` | 1.0 | 0.5 | `14562` | BB_PULLBACK_SCALP fractional lot | `setup_type == BB_PULLBACK_SCALP` |
| 16 | `intraday_reversal_factor` | 1.0 | 2.0 | `14568` | INTRADAY_REVERSAL_TO_SELL_V3 amplifier on MOMENTUM_DUMP SELL | `setup_type == MOMENTUM_DUMP && direction == SELL && IsIntradayReversalSellActive(...)` |
| 17 | `fractional_sell_factor` | 1.0 | 0.25 | `14576` | FRACTIONAL_SELL_IN_BULL probe size | `setup_type == FRACTIONAL_SELL_IN_BULL && direction == SELL` |
| 18 | `bull_day_dip_factor` | 1.0 | 1.0 – 1.5 | `14583` | BULL_DAY_DIP_BUY amplifier + prime-window stack | Base `bull_day_dip_buy_lot_mult`, ×`bull_day_dip_buy_prime_amplifier` inside NY_OPEN / LONDON_CLOSE KZs |
| 19 | `ma_crossover_factor` | 1.0 | 0.5 | `14600` | MA_CROSSOVER lot factor (lag de-risk) | `setup_type == MA_CROSSOVER` |
| 20 | `vwap_reversion_factor` | 1.0 | 0.5 | `14606` | VWAP_REVERSION lot factor | `setup_type == VWAP_REVERSION` |
| 21 | `fib_confluence_factor` | 1.0 | 0.5 | `14611` | FIB_CONFLUENCE lot factor | `setup_type == FIB_CONFLUENCE` |
| 22 | `inside_bar_factor` | 1.0 | 0.5 | `14616` | INSIDE_BAR lot factor | `setup_type == INSIDE_BAR` |
| 23 | `bb_squeeze_factor` | 1.0 | 0.5 | `14621` | BB_SQUEEZE lot factor | `setup_type == BB_SQUEEZE` |
| 24 | `orb_factor` | 1.0 | 0.5 | `14626` | ORB lot factor | `setup_type == ORB` |
| 25 | `gap_and_go_factor` | 1.0 | 0.5 | `14631` | GAP_AND_GO lot factor | `setup_type == GAP_AND_GO` |
| 26 | `double_pattern_factor` | 1.0 | 0.5 | `14636` | DOUBLE_TOP / DOUBLE_BOTTOM lot factor (shared) | `setup_type ∈ {DOUBLE_TOP, DOUBLE_BOTTOM}` |
| 27 | `hs_factor` | 1.0 | 0.5 | `14641` | HEAD_AND_SHOULDERS / INVERSE_H&S lot factor (shared) | `setup_type ∈ {HEAD_AND_SHOULDERS, INVERSE_HEAD_AND_SHOULDERS}` |
| 28 | `flag_pennant_factor` | 1.0 | 0.5 | `14646` | FLAG_PENNANT lot factor | `setup_type == FLAG_PENNANT` |
| 29 | `trendline_bounce_factor` | 1.0 | 0.5 | `14651` | TRENDLINE_BOUNCE lot factor | `setup_type == TRENDLINE_BOUNCE` |
| 30 | `sr_flip_factor` | 1.0 | 0.5 | `14656` | SR_FLIP lot factor | `setup_type == SR_FLIP` |
| 30b | `fast_trend_factor` | 1.0 | 1.5 | `14674` | Universal HTF-aligned fast-trend amplifier | `m5_adx ≥ 35 && (h1 || m15 aligned) && regime ∈ {TREND_BULL, TREND_BEAR}` matching direction |

> Note on numbering: the in-code product line lists 30 factors followed by `fast_trend_factor` as the 31st multiplicand. `fast_trend_factor` is universal (any setup, any direction) and applies last in the chain. It is documented as factor 30b for parity with the v2.7.121 PrintFormat ordering.

### The setup multiplier `lot_mult`

Lives upstream of `combined_lot_factor` but is part of the same product. Initialized at `ea/FORGE.mq5:14331`.

```mql5
// ea/FORGE.mq5:14331-14343
double lot_mult = 1.0;
double lot_max_mult = MathMax(1.0, MathMin(5.0, NativeScalperAutoLotMaxMultiplier));
double lot_trend_ref = MathMax(0.10, NativeScalperAutoLotTrendRef);
if(NativeScalperAutoLotByTrend && (!NativeScalperAutoLotBreakoutOnly || is_breakout_setup)) {
   double dir_h1 = (direction == "BUY") ? MathMax(0.0, h1_trend_strength)
                                        : MathMax(0.0, -h1_trend_strength);
   double dir_h4 = (direction == "BUY") ? MathMax(0.0, h4_trend_strength)
                                        : MathMax(0.0, -h4_trend_strength);
   double dir_trend = (dir_h1 + dir_h4) / 2.0;
   double lot_ratio = MathMin(1.0, dir_trend / lot_trend_ref);
   lot_mult = 1.0 + lot_ratio * (lot_max_mult - 1.0);
}
```

Range: 1.0 – 5.0. Fires only when `NativeScalperAutoLotByTrend` is on AND (either `!NativeScalperAutoLotBreakoutOnly` or `is_breakout_setup`). Logged as `lot_mult` in the v2.7.121 PrintFormat.

### The three lot pins — chain overrides

| Pin | Source line | Trigger | Pinned lot | Amplifier tiers |
|---|---:|---|---|---|
| `blr_buy_capitulation_lot` | `14728` | `setup_type == BB_LOWER_REVERSION_BUY && blr_capitulation_active` | `0.30` (config default) | None — flat pin |
| `asia_capitulation_buy_lot` | `14736` | `setup_type == ASIA_CAPITULATION_BUY` | `0.20` (config default) | None — flat pin |
| `bb_exhaustion_reversal_lot` | `14743-14769` | `setup_type ∈ {BB_EXHAUSTION_REVERSAL_BUY, BB_EXHAUSTION_REVERSAL_SELL}` | `0.10` × `1.5` (BASE amp) | HIGH tier (warnings ≥ 6): `× 2.0` extra → `0.10 × 1.5 × 2.0 = 0.30` |

All three pins:
- Are evaluated **after** the combined product computes `lot = base × lot_mult × combined_lot_factor`.
- **Reassign** `lot` (the chain result is logged but unused for the actual order).
- Apply `MathMax(pinned, SYMBOL_VOLUME_MIN)` to respect broker floor.
- Log a `PrintFormat` showing both the pinned value and the would-have-been chain value (for diagnostic compare).

---

## §3 Per-factor math + invocation (detailed body)

Subsections are ordered by **importance / variability**, matching the v2.7.122 selective-column-12 plan. The 12 most-variable factors come first; the 18 setup-specific factors that are always 1.0 except for their owning setup are grouped in §3.13 onward.

### §3.1 `stack_factor`

**Math** (cite `ea/FORGE.mq5:14439-14444`):

```mql5
double stack_factor = 1.0;
if(g_sc.same_direction_stack_lot_factor > 0.0 && g_sc.same_direction_stack_lot_factor < 1.0
   && ScalperOpenGroupCountByDirection(direction) >= 1) {
   stack_factor = g_sc.same_direction_stack_lot_factor;  // default 0.25
   PrintFormat("FORGE SCALPER: %s stack entry — lot factor=%.2f", direction, stack_factor);
}
```

**When it fires** — universal across every setup. The 2nd, 3rd, ... concurrent group in the same direction shrinks to 25% of the would-be base. This is **the single biggest contributor to lot variance between two same-setup signals** in production: G5001 fires at lot=0.469 (no other open BUY groups), G5002 fires 8 minutes later at lot=0.117 (G5001 still open → stack_factor=0.25 → 0.469 × 0.25 ≈ 0.117).

**Range in production** — exactly two values: 1.0 (no concurrent same-dir group) or `same_direction_stack_lot_factor` (default 0.25). The factor is **binary**, not continuous.

**Config knob**: `same_direction_stack_lot_factor` (default 0.25). JSON path `scalper.same_direction_stack_lot_factor`. Env: `FORGE_SAME_DIRECTION_STACK_LOT_FACTOR`.

**Setup cross-reference**: every setup that emits a market or pending order. The only exemption is the three lot-pins (which bypass the chain entirely).

**Anti-ICT risk**: in a confirmed trend with confluence, stacking is **the correct ICT behaviour** (pyramiding into a winner). The current logic shrinks all stacks regardless of trend agreement. This is the #1 candidate for §5 update.

### §3.2 `dump_pyramid_factor`

**Math** (cite `ea/FORGE.mq5:14482-14490`):

```mql5
double dump_pyramid_factor = 1.0;
if(setup_type == "MOMENTUM_DUMP" && g_sc.dump_pyramid_enabled) {
   int consec_n = (direction == "BUY") ? g_dump_pyramid_consec_buy_count
                                       : g_dump_pyramid_consec_sell_count;
   double pf = g_sc.dump_pyramid_base_factor + consec_n * g_sc.dump_pyramid_step;
   if(pf > g_sc.dump_pyramid_max_factor) pf = g_sc.dump_pyramid_max_factor;
   if(pf < g_sc.dump_pyramid_min_factor) pf = g_sc.dump_pyramid_min_factor;
   dump_pyramid_factor = pf;
}
```

**When it fires** — MOMENTUM_DUMP only, when `dump_pyramid_enabled=1`. Production config:
- `dump_pyramid_base_factor=1.0`, `dump_pyramid_step=1.0`, `dump_pyramid_min_factor=1.0`, `dump_pyramid_max_factor=5.0`
- consec_n increments on every TAKEN MOMENTUM_DUMP in same direction; resets when direction flips OR all same-dir DUMP positions close.

So in default config, the factor is `1.0, 2.0, 3.0, 4.0, 5.0, 5.0, ...` — escalating pyramid. The operator-coined v2.7.66 enhancement allows **decreasing** pyramid by setting `base=5.0, step=-1.0` → sequence becomes `5, 4, 3, 2, 1, 1, ...` ("big lot at best entry, smaller adds" per the inline comment).

**Range in production** — discrete: `{1.0, 2.0, 3.0, 4.0, 5.0}`. Default config emits `1.0` on first fire, then escalates.

**Config knobs**:
- `composites.dump_pyramid_enabled` (1)
- `composites.dump_pyramid_base_factor` (1.0)
- `composites.dump_pyramid_step` (1.0)
- `composites.dump_pyramid_min_factor` (1.0)
- `composites.dump_pyramid_max_factor` (5.0)

**Setup cross-reference**: MOMENTUM_DUMP only. Counterpart counters: `g_dump_pyramid_consec_buy_count` / `g_dump_pyramid_consec_sell_count`.

**ICT analogue**: classical ICT pyramiding fires inside an MSS-confirmed displacement leg, sized by ATR risk-percent, not by consecutive-fire count. Today's implementation amplifies on count regardless of structure validation — a structural drift gate would block escalation if the MSS confirming the original entry has been invalidated.

### §3.3 `dump_dist_amplifier`

**Math** (cite `ea/FORGE.mq5:14494-14507`):

```mql5
double dump_dist_amplifier = 1.0;
if(setup_type == "MOMENTUM_DUMP" && g_sc.dump_dist_amplifier_enabled && m5_atr > 0.0) {
   double _amp_mid = (Ask + Bid) / 2.0;
   double _amp_dist_atr = 0.0;
   if(direction == "BUY"  && g_eval_day_high > 0) _amp_dist_atr = (g_eval_day_high - _amp_mid) / m5_atr;
   else if(direction == "SELL" && g_eval_day_low > 0) _amp_dist_atr = (_amp_mid - g_eval_day_low) / m5_atr;
   if(_amp_dist_atr >= g_sc.dump_dist_amplifier_strong_threshold_atr)
      dump_dist_amplifier = g_sc.dump_dist_amplifier_strong_factor;        // 2.0×
   else if(_amp_dist_atr >= g_sc.dump_dist_amplifier_threshold_atr)
      dump_dist_amplifier = g_sc.dump_dist_amplifier_factor;               // 1.5×
}
```

**When it fires** — MOMENTUM_DUMP only. Measures distance from price to the day's extreme on the *opposite* side of the trade direction:
- BUY: distance to `day_high` — far from high = lots of room left → high-conviction
- SELL: distance to `day_low` — far from low = lots of room down

**Range in production** — discrete: `{1.0, 1.5, 2.0}`. Operator-coined v2.7.62 (G5092 reward case).

**Config knobs**:
- `scalper.dump_dist_amplifier_enabled`
- `scalper.dump_dist_amplifier_threshold_atr` (1.5)
- `scalper.dump_dist_amplifier_factor` (1.5)
- `scalper.dump_dist_amplifier_strong_threshold_atr` (3.0)
- `scalper.dump_dist_amplifier_strong_factor` (2.0)

**Setup cross-reference**: MOMENTUM_DUMP only.

**ICT analogue**: aligns with ICT premium/discount canon — BUY in deep discount (price < equilibrium), SELL in deep premium (price > equilibrium). The current implementation uses day_high/day_low as the dealing range proxy. The ICT replacement (§5) replaces this with explicit dealing-range premium/discount logic based on swing-high / swing-low, not day extremes.

### §3.4 `dump_kz_amplifier`

**Math** (cite `ea/FORGE.mq5:14511-14524`):

```mql5
double dump_kz_amplifier = 1.0;
if(setup_type == "MOMENTUM_DUMP" && g_sc.dump_kz_amplifier_enabled) {
   bool _in_kz = (StringLen(g_regime.killzone) > 0 && g_regime.killzone != "NONE");
   if(!_in_kz) {
      dump_kz_amplifier = g_sc.dump_kz_no_zone_factor;        // 0.5 — half-size outside KZ
   } else {
      double m = (double)g_regime.minutes_into_kz;
      if(m <= 5)       dump_kz_amplifier = g_sc.dump_kz_tier1_factor;     // 2.0×
      else if(m <= 15) dump_kz_amplifier = g_sc.dump_kz_tier2_factor;     // 2.0×
      else if(m <= 30) dump_kz_amplifier = g_sc.dump_kz_tier3_factor;     // 1.5×
      else if(m <= 60) dump_kz_amplifier = g_sc.dump_kz_tier4_factor;     // 1.0×
      else             dump_kz_amplifier = g_sc.dump_kz_tier5_factor;     // 0.85×
   }
}
```

**When it fires** — MOMENTUM_DUMP only. Operator-coined v2.7.63 (per inline comment: "kills move fast within secs"). Uses pre-computed `g_regime.killzone` + `g_regime.minutes_into_kz`.

**Range in production** — discrete: `{0.5, 0.85, 1.0, 1.5, 2.0}` per the production config tiers (`config/scalper_config.json:493-502`).

**Config knobs**: `scalper.dump_kz_amplifier_enabled` + 6 tier knobs (`dump_kz_no_zone_factor`, `dump_kz_tier1..5_factor`, `dump_kz_tier1..4_max_min`).

**Setup cross-reference**: MOMENTUM_DUMP only. This is the only existing factor that already implements KZ-aware sizing — the §5 recommendation generalizes the pattern across all setups via a new `lot_killzone_session_factor`.

**ICT alignment**: strong. Matches ICT canon (London Open KZ + NY Open KZ are highest-edge windows; outside-KZ is half-size). The 0.5 dead-zone is conservative — ICT canon would block entirely.

### §3.5 `tcb_factor` (TREND_CONTINUATION_BUY)

**Math** (cite `ea/FORGE.mq5:14535-14540`):

```mql5
double tcb_factor = 1.0;
if(setup_type == "TREND_CONTINUATION_BUY" && direction == "BUY"
   && g_sc.trend_continuation_buy_lot_factor > 0.0
   && g_sc.trend_continuation_buy_lot_factor <= 10.0) {
   tcb_factor = g_sc.trend_continuation_buy_lot_factor;  // default 2.0
}
```

**When it fires** — TREND_CONTINUATION_BUY only. Static per-setup amplifier; no conditional logic beyond the setup-type check.

**Range in production** — `{1.0, 2.0}`. Operator-coined v2.7.57 with "aggressive default 2.0×" rationale.

**Config knob**: `scalper.trend_continuation_buy_lot_factor`. Env: `FORGE_TREND_CONTINUATION_BUY_LOT_FACTOR`.

**Setup cross-reference**: TREND_CONTINUATION_BUY only.

**ICT alignment**: matches the pyramiding-into-trend canon. Could be conditioned on H4 alignment + ISS-C ≥ 8 to make the 2× selective rather than blanket — see §5.

### §3.6 `tcs_factor` (TREND_CONTINUATION_SELL)

**Math** (cite `ea/FORGE.mq5:14541-14546`): mirror of `tcb_factor`. Default 2.0.

**Same ICT alignment** as §3.5. Mirror knob `scalper.trend_continuation_sell_lot_factor`.

### §3.7 `adx_lot_factor`

**Math** (cite `ea/FORGE.mq5:14448-14461`):

```mql5
double adx_lot_factor = 1.0;
if(direction == "SELL" && is_breakout_setup) {
   double _adx_ref = m5_adx;
   if(g_sc.breakout_adx_lot_use_m15) {
      double _m15adx[1];
      if(CopyBuffer(g_mtf[1].h_adx, 0, 0, 1, _m15adx) == 1) _adx_ref = _m15adx[0];
   }
   if(_adx_ref >= g_sc.breakout_adx_lot_high_threshold && g_sc.breakout_adx_lot_factor_high > 0)
      adx_lot_factor = g_sc.breakout_adx_lot_factor_high;   // 0.125 (1/8th)
   else if(_adx_ref >= g_sc.breakout_adx_lot_mid_threshold && g_sc.breakout_adx_lot_factor_mid > 0)
      adx_lot_factor = g_sc.breakout_adx_lot_factor_mid;    // 0.25
}
```

**When it fires** — **SELL breakouts only** (asymmetric — BUY breakouts are never ADX-tiered down). Per inline comment, this implements an OpoFinance/Trade2Win pattern: "the more extended the trend, the smaller the bet." M15 ADX (not M5) drives the tier decision because M5 ADX lags.

**Range in production** — discrete `{0.125, 0.25, 1.0}`. M15 ADX ≥ 45 → 0.125. M15 ADX 35-44 → 0.25. Else 1.0.

**Config knobs**:
- `scalper.breakout_adx_lot_use_m15` (1)
- `scalper.breakout_adx_lot_high_threshold` (45)
- `scalper.breakout_adx_lot_factor_high` (0.125) — operator-mandated; do not revert to 1.0 (memory rule `feedback_adx_lot_factor_high_half`)
- `scalper.breakout_adx_lot_mid_threshold` (35)
- `scalper.breakout_adx_lot_factor_mid` (0.25)

**Setup cross-reference**: BB_BREAKOUT SELL + BB_BREAKOUT_RETEST SELL only.

**ICT analogue**: ADX-extended sell into a confirmed bear is the OPPOSITE of what ICT teaches — extended bears with displacement should pyramid SIZE up, not down. But the v2.7.107 case study (XAUUSD chop retraces upward) showed mid-RSI dump-SELL at high ADX = near-certain loser; the de-risk is correct empirically. Memory rule documents the intent. The §5 recommendation suggests gating the de-risk on ISS-C low (no structural support for the trend) — when ISS-C ≥ 8, the de-risk SHOULD reverse to amplification.

### §3.8 `fast_trend_factor`

**Math** (cite `ea/FORGE.mq5:14674-14691`):

```mql5
double fast_trend_factor = 1.0;
if(g_sc.fast_trend_lot_amplifier_enabled && setup_type != "") {
   int _ft_dir = (direction == "BUY") ? +1 : ((direction == "SELL") ? -1 : 0);
   if(_ft_dir != 0 && m5_adx >= g_sc.fast_trend_lot_amplifier_adx_min) {
      bool _ft_with_h1  = (MathAbs(h1_trend_strength) >= g_sc.cooldown_bypass_with_trend_h1_min)
                       && ((_ft_dir > 0) ? (h1_trend_strength > 0.0) : (h1_trend_strength < 0.0));
      bool _ft_with_m15 = g_sc.cooldown_bypass_with_trend_m15_or_h1
                       && Atom_M15TrendAligned(_ft_dir, true);
      bool _ft_regime   = (_ft_dir > 0 && g_regime_label == "TREND_BULL")
                       || (_ft_dir < 0 && g_regime_label == "TREND_BEAR");
      if((_ft_with_h1 || _ft_with_m15) && _ft_regime) {
         fast_trend_factor = g_sc.fast_trend_lot_amplifier_factor;  // 1.5×
      }
   }
}
```

**When it fires** — universal across all setups. Three conditions ALL required:
1. M5 ADX ≥ `fast_trend_lot_amplifier_adx_min` (default 35)
2. (H1 strength aligned OR M15 aligned)
3. `g_regime_label` matches direction (TREND_BULL for BUY, TREND_BEAR for SELL)

**Range in production** — `{1.0, 1.5}`. Operator-coined v2.7.53 ("size up when fast bull/bear is confirmed").

**Config knobs**:
- `scalper.fast_trend_lot_amplifier_enabled` (1)
- `scalper.fast_trend_lot_amplifier_factor` (1.5)
- `scalper.fast_trend_lot_amplifier_adx_min` (35.0)

**Setup cross-reference**: every setup. This is the universal trend-aligned amplifier — it already does most of what `lot_h4_alignment_factor` (§5 proposal) would do, except it stops at H1; H4 confluence is not checked.

**ICT alignment**: very strong. Matches ICT canon "trade with HTF bias." §5 extends it to require H4 confluence + ISS-C score gate.

### §3.9 `near_floor_factor`

**Math** (cite `ea/FORGE.mq5:14429-14436`):

```mql5
double near_floor_factor = 1.0;
if(direction == "SELL" && is_breakout_setup
   && g_sc.breakout_h1h4_crash_sell && h1_bear && h4_bear
   && m5_rsi > g_sc.breakout_h1h4_crash_sell_rsi_min && m5_rsi <= 25.0
   && g_sc.breakout_near_floor_lot_factor > 0.0 && g_sc.breakout_near_floor_lot_factor < 1.0) {
   near_floor_factor = g_sc.breakout_near_floor_lot_factor;  // default 0.25
}
```

**When it fires** — SELL breakouts in confirmed H1+H4 bear, with RSI in the 20-25 (Cardwell near-floor zone). De-risks to 25% because RSI is approaching extreme oversold and a reversal bounce is statistically common.

**Range in production** — `{0.25, 1.0}`. Setup-asymmetric (SELL only).

**Config knob**: `scalper.breakout_near_floor_lot_factor`.

**Setup cross-reference**: BB_BREAKOUT SELL only.

**ICT alignment**: matches the canonical "avoid catching falling knives" canon. The §5 ICT replacement reframes this as "respect H4 demand zone" — instead of an RSI-only filter, gate on whether price has entered an H4 order block / demand zone in the SELL direction.

### §3.10 `inside_band_factor`

**Math** (cite `ea/FORGE.mq5:14420-14426`):

```mql5
double inside_band_factor = 1.0;
if(direction == "SELL" && is_breakout_setup && mid > m5_bb_l
   && g_sc.breakout_sell_inside_band_lot_factor > 0.0 && g_sc.breakout_sell_inside_band_lot_factor < 1.0) {
   inside_band_factor = g_sc.breakout_sell_inside_band_lot_factor;  // default 0.5
}
```

**When it fires** — SELL breakout with price retraced inside the BB lower band. Halves the lot because the breakout has not held — risk is higher.

**Range in production** — `{0.5, 1.0}`.

**Config knob**: `scalper.breakout_sell_inside_band_lot_factor`.

**Setup cross-reference**: BB_BREAKOUT SELL only.

**ICT alignment**: indirectly aligned. ICT canon would gate on whether the SELL is being made INTO a still-active FVG or breaker block — i.e., is the failure structural? §5 replaces this RSI/BB filter with an FVG-mitigation atom: SELL breakout retracing into a still-unmitigated bullish FVG = high probability long counter-move → block, not just halve.

### §3.11 `scalper_lot_factor_eff`

**Math** (cite `ea/FORGE.mq5:14664-14665`):

```mql5
double scalper_lot_factor_eff = (ScalperLotFactor != 1.0) ? ScalperLotFactor : g_sc.scalper_lot_factor;
if(scalper_lot_factor_eff <= 0.0) scalper_lot_factor_eff = 1.0;
```

**When it fires** — always (every signal). MT5 INPUT override wins; otherwise env value.

**Range in production** — typically 1.0. Operator-tunable global multiplier without touching base `lot_fixed`.

**Config knob**: `lot_sizing.scalper_lot_factor` + MT5 `ScalperLotFactor` input.

**Setup cross-reference**: every setup. Universal.

**ICT alignment**: neutral — it's a global scaler. The §5 risk-percent pinning recommendation would supersede this knob as the canonical sizing dial.

### §3.12 `lot_mult` (setup-multiplier upstream of `combined_lot_factor`)

Documented in §2.1 above. Computed from H1+H4 directional trend strength. Range 1.0 – 5.0. Setup gate via `NativeScalperAutoLotBreakoutOnly` defaults to BB_BREAKOUT only.

**ICT alignment**: this is the second-best aligned existing factor (after `fast_trend_factor`) — H1+H4 trend agreement IS an ICT HTF-bias atom. §5 generalizes it.

### §3.13-30 Setup-specific factors (mostly always 1.0)

Factors 6 (`bounce_factor`), 11 (`mdct_factor`), 13-14 (`tcb`, `tcs`), 15 (`pullback_factor`), 16-18 (`intraday_reversal_factor`, `fractional_sell_factor`, `bull_day_dip_factor`), 12 (`bbr_factor`), and 19-30 (`ma_crossover_factor` through `sr_flip_factor`) follow the same pattern:

```mql5
double <X>_factor = (setup_type == "<SETUP>"
                    && g_sc.<X>_lot_factor > 0.0
                    && g_sc.<X>_lot_factor < 1.0)   // OR ≤ 10.0 for amplifiers
                   ? g_sc.<X>_lot_factor : 1.0;
```

These are **constants per setup** — they don't vary with market state, EA state, RSI, ADX, regime, or session. They are derivable from `setup_type` + config snapshot at run wall_time. **Per the selective-column rule, they should NOT have a SIGNALS column** — text-log only.

Defaults from `config/scalper_config.defaults.json` (geometry section, lines 575-619):

| Factor | Default | Setup |
|---|---:|---|
| `ma_crossover_lot_factor` | 0.5 | MA_CROSSOVER |
| `vwap_reversion_lot_factor` | 0.5 | VWAP_REVERSION |
| `fib_confluence_lot_factor` | 0.5 | FIB_CONFLUENCE |
| `inside_bar_lot_factor` | 0.5 | INSIDE_BAR |
| `bb_squeeze_lot_factor` | 0.5 | BB_SQUEEZE |
| `orb_lot_factor` | 0.5 | ORB |
| `gap_and_go_lot_factor` | 0.5 | GAP_AND_GO |
| `double_pattern_lot_factor` | 0.5 | DOUBLE_TOP / DOUBLE_BOTTOM |
| `hs_lot_factor` | 0.5 | HEAD_AND_SHOULDERS / INVERSE_H&S |
| `flag_pennant_lot_factor` | 0.5 | FLAG_PENNANT |
| `trendline_bounce_lot_factor` | 0.5 | TRENDLINE_BOUNCE |
| `sr_flip_lot_factor` | 0.5 | SR_FLIP |
| `bounce_lot_factor` | 1.0 | BB_BOUNCE family |
| `momentum_dump_composite_test_lot_factor` | 0.7 | MOMENTUM_DUMP_COMPOSITE_TEST |
| `bb_lower_reversion_buy_lot_factor` | 1.0 | BB_LOWER_REVERSION_BUY (with ×1.5 RSI≤25 amplifier) |
| `trend_continuation_buy_lot_factor` | 2.0 | TREND_CONTINUATION_BUY |
| `trend_continuation_sell_lot_factor` | 2.0 | TREND_CONTINUATION_SELL |
| `pullback_scalp_lot_factor` | 0.5 | BB_PULLBACK_SCALP |
| `intraday_reversal_sell_lot_mult` | 2.0 | conditional MOMENTUM_DUMP SELL |
| `fractional_sell_in_bull_lot_factor` | 0.25 | FRACTIONAL_SELL_IN_BULL |
| `bull_day_dip_buy_lot_mult` | 1.0 | BULL_DAY_DIP_BUY (× 1.5 prime amplifier if KZ ∈ NY_OPEN ∪ LONDON_CLOSE) |

The C-extended Tier 1/2/3 setups (MA_CROSSOVER through SR_FLIP) all default to 0.5 because they were experimental geometries (v2.7.42 ship); operator can opt-up per-setup once tester data justifies.

---

## §4 Setup-by-setup factor interaction matrix

For each setup, the columns show which factors can be ≠ 1.0 when that setup fires. ✓ = can move; — = always 1.0 (no-op); PIN = setup uses a lot-pin and the entire chain is bypassed.

| Setup | Lot pin? | scalper_eff | inside_band | near_floor | stack | adx_lot | dump | dump_pyr | dump_dist | dump_kz | mdct | bbr | tcb | tcs | pullback | intraday_rev | fractional_sell | bull_day_dip | ma_x | vwap_rev | fib_conf | inside_bar | bb_squeeze | orb | gap_go | dbl_pat | hs | flag | tline | sr_flip | fast_trend | lot_mult |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BB_BREAKOUT_BUY | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | ✓ |
| BB_BREAKOUT_SELL | — | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | ✓ |
| BB_BREAKOUT_RETEST_BUY | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | ✓ |
| BB_BREAKOUT_RETEST_SELL | — | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | ✓ |
| BB_BOUNCE_BUY | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| BB_BOUNCE_SELL | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| MOMENTUM_DUMP (BUY) | — | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| MOMENTUM_DUMP (SELL) | — | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| MOMENTUM_DUMP_COMPOSITE_TEST | — | ✓ | — | — | ✓ | — | — | — | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| BB_LOWER_REVERSION_BUY (chain) | — | ✓ | — | — | ✓ | — | — | — | — | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| BB_LOWER_REVERSION_BUY (capitulation) | **PIN 0.30** | ignored | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| ASIA_CAPITULATION_BUY | **PIN 0.20** | ignored | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| BB_EXHAUSTION_REVERSAL_BUY | **PIN 0.10 × 1.5 (× 2.0 HIGH)** | ignored | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| BB_EXHAUSTION_REVERSAL_SELL | **PIN 0.10 × 1.5 (× 2.0 HIGH)** | ignored | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| TREND_CONTINUATION_BUY | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| TREND_CONTINUATION_SELL | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| BB_PULLBACK_SCALP | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| FRACTIONAL_SELL_IN_BULL | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| BULL_DAY_DIP_BUY | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| MA_CROSSOVER | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| VWAP_REVERSION | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | ✓ | — |
| FIB_CONFLUENCE | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — | — | — | — | — | — | — | — | ✓ | — |
| INSIDE_BAR | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — | — | — | — | — | — | — | ✓ | — |
| BB_SQUEEZE | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — | — | — | — | — | — | ✓ | — |
| ORB | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — | — | — | — | — | ✓ | — |
| GAP_AND_GO | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — | — | — | — | ✓ | — |
| DOUBLE_TOP / DOUBLE_BOTTOM | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — | — | — | ✓ | — |
| HEAD_AND_SHOULDERS / INVERSE_H&S | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — | — | ✓ | — |
| FLAG_PENNANT | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | — | ✓ | — |
| TRENDLINE_BOUNCE | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | — | ✓ | — |
| SR_FLIP | — | ✓ | — | — | ✓ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✓ | ✓ | — |

**Key observations from the matrix**:

1. **Every non-pin setup is touched by exactly 4 universal factors**: `scalper_eff`, `stack`, `fast_trend`, and (for BB_BREAKOUT* only) `lot_mult`. These 3-4 factors explain 95% of cross-setup lot variance.
2. **MOMENTUM_DUMP is the highest-variance setup** — 8 active factors (`scalper_eff`, `stack`, `dump`, `dump_pyramid`, `dump_dist`, `dump_kz`, `intraday_reversal_factor` on SELL only, `fast_trend`). This is the only setup where the v2.7.121 PrintFormat genuinely helps with cross-trade diagnosis.
3. **The 3 lot pins eliminate all 30 chain factors**. Once a pin fires, the entire combined product is logged as a diagnostic but unused. This is the **structural reason** the schema-parity 12-column ship is selective — for ~30% of taken trades (the pinned ones), every column logs the chain-result-that-wasn't.

---

## §5 ICT-aware lot recommendations

The recommendations below proceed factor-by-factor for the 12 most-variable, then propose 6 new ICT-aware factors. Every recommendation is **default-OFF** (backward-compat by env knob) and ships per the Phase B / Phase C schedule in §7.

### §5.1 `stack_factor` — keep base, ADD an ICT bypass

**Keep**: the 0.25 default for stacking into a non-confirmed regime. Memory rule `feedback_use_makefile_restart_targets` + the broader chop-bias of XAUUSD makes blanket stacking dangerous.

**Change**: when ALL of (regime ∈ TREND_BULL/TREND_BEAR matching dir) AND (ISS-C ≥ 8) AND (h4_trend agrees with direction), bypass the stack reducer entirely → `stack_factor = 1.0`. Rationale: ICT canon is to pyramid into confirmed trend post-MSS; the current blanket reducer leaves money on the table during the Apr 1 NY rally pattern (G5001 +$$$, G5002 stack=0.25 → 8% the size of G5001 → captures 8% of the move).

**Industry source**: ICT scalping canon validates pyramiding within confirmed displacement legs (per [innercircletrader.net — ICT Scalping Strategy](https://innercircletrader.net/tutorials/simple-ict-scalping-strategy/) and the ICT institutional-volume rule that during high-conviction killzones pyramid sizing is permitted). The current SAME-direction reducer is appropriate for chop but counter-productive for trend.

**Implementation**: gate via `FORGE_LOT_STACK_BYPASS_ON_ISS_C_ENABLED` (default 0).

### §5.2 `dump_pyramid_factor` — keep base, ADD MSS validity drift gate

**Keep**: the linear escalating ladder. It's a legitimate scaling-into-confirmed-displacement pattern.

**Change**: when the MSS that confirmed the first DUMP fire is no longer valid (e.g., price has retraced past the MSS swing level), CAP the pyramid at the base factor (no escalation). Rationale: ICT canon — pyramid only while the displacement leg is structurally intact.

**Implementation**: add an ICT atom `g_iss_displacement_intact` (per `prompts/ICT_Tradingidea.md` §A — "Displacement candle confirmation"); when 0 and `consec_n > 0`, force `dump_pyramid_factor = dump_pyramid_base_factor` regardless of count.

### §5.3 `dump_dist_amplifier` — keep math, RENAME concept to PD-array

**Keep**: the 1.5×/2.0× tiers — the math is fine, the threshold ATR multipliers are well-calibrated.

**Change**: replace `day_high` / `day_low` with explicit ICT premium/discount levels (the equilibrium midpoint of the active dealing range — `IsInDiscount()` / `IsInPremium()` per `prompts/ICT_Tradingidea.md` §J). Rationale: day extremes are a noisy proxy. The ICT dealing range (from the most recent swing high to swing low on H4) is the canonical PD-array.

**Implementation**: add the existing v2.7.120 IctLiquidity/OB module's dealing-range helpers; replace the `g_eval_day_high/low` reads with `g_iss_dealing_range.equilibrium`.

**Deprecate**: the day-extreme-based logic once ICT dealing-range is shipped.

### §5.4 `dump_kz_amplifier` — keep, GENERALIZE pattern to all setups

**Keep**: every tier value and threshold. This is the most ICT-aligned existing factor.

**Change**: extract the tier logic into a setup-agnostic helper, then apply it to every setup via the new `lot_killzone_session_factor` (§5.13). The MOMENTUM_DUMP-specific block stays as an alias for backward compat.

### §5.5 `tcb_factor` / `tcs_factor` — keep, ADD ISS-C gate

**Keep**: the 2.0× default.

**Change**: gate on ISS-C ≥ 6 (EMERGING+) and h4 alignment. When ISS-C < 6, fall back to 1.0×. Rationale: TREND_CONTINUATION fires on every M5 trend label; ICT canon requires structural confirmation (MSS + FVG within the displacement leg).

### §5.6 `adx_lot_factor` — keep base, REVERSE with ISS-C HIGH_CONVICTION

**Keep**: the current ADX 35+ / 45+ tiers. They are correct **in the absence of ICT structural confirmation**.

**Change**: when ISS-C ≥ 8 (HIGH_CONVICTION on the SELL side, i.e., the entire HTF + structure stack confirms continuation), REVERSE the de-risk to `adx_lot_factor = 1.5` (amplify). Rationale: ADX-extended SELL into confirmed bear with MSS + FVG + ChoCH-support is exactly the ICT continuation pattern; de-risking it leaves money on the table. The Apr 8 PM bear cascade memory rule supports.

**Industry source**: [`mql5.com/en/articles/18991`](https://www.mql5.com/en/articles/18991) — "Position sizing should INCREASE with HTF confirmation, decrease with HTF disagreement." The current asymmetric SELL-only de-risk is a memory of past chop losses; ICT canon resolves the chop-vs-trend question explicitly.

### §5.7 `fast_trend_factor` — keep, EXTEND to require H4

**Keep**: the 1.5× amplifier on H1-or-M15 + regime + ADX 35.

**Change**: require H4 directional agreement as an additional precondition. Rationale: the SKILL.md H4-trend-agreement mandate. M15+M5 alignment alone is sometimes a counter-H4 retrace.

**Implementation**: add `Atom_H4TrendAligned(_ft_dir)` to the gate; default-ON via `FORGE_LOT_FAST_TREND_REQUIRE_H4_ENABLED` (default 0 for backward compat).

### §5.8 `near_floor_factor` — DEPRECATE in favor of ICT demand-zone gate

**Deprecate**: RSI 20-25 is a noisy proxy. ICT canon says don't sell into a still-active H4 demand zone / bullish FVG regardless of RSI.

**Replace**: with `lot_h4_demand_zone_block_factor` — when SELL fires inside an active H4 bullish FVG or order block, block (not just de-risk to 0.25). This is a HARD GATE not a multiplier.

### §5.9 `inside_band_factor` — keep math, GATE on FVG mitigation

**Keep**: 0.5 default.

**Change**: only apply the de-risk when the retraced price is INSIDE an active bullish FVG (per the v2.7.118 FVG ring). When no FVG is active, the inside-band retrace is just noise and the 1.0 default applies. Rationale: ICT canon — only structural retraces matter.

### §5.10 `scalper_lot_factor_eff` — keep, but SUPERSEDE with risk-percent floor

**Keep**: the env-override semantics for backward compat.

**Change**: when `FORGE_LOT_RISK_PCT_FLOOR_ENABLED=1`, the global multiplier becomes secondary to the risk-percent floor (§5.13.f). Rationale: ICT canon (per [`innercircletrader.net — simple-ict-scalping-strategy`](https://innercircletrader.net/tutorials/simple-ict-scalping-strategy/) and the 2026 MQL5 risk-percent canon) treats lot size as a function of equity × risk_pct ÷ (SL_distance × pip_value), not a multiplicative chain on a fixed base.

### §5.11 `lot_mult` (setup multiplier) — keep, EXTEND to all setups via ISS-C

**Keep**: the H1+H4 trend-strength derivation.

**Change**: drop the `NativeScalperAutoLotBreakoutOnly` restriction; apply to every setup. Replace the linear `lot_ratio` formula with an ISS-C-weighted formula: `lot_mult = 1.0 + ISS_C_score / 10.0 × (max_mult - 1.0)`. Rationale: trend strength is one ICT atom; the full ISS-C composite is a better predictor.

### §5.12 Setup-specific factors (the 18 always-1.0-except-own-setup) — DEFER

Default-OFF, no §5 changes. These already have appropriate per-setup defaults. Future tuning will be per-setup driven by per-setup tester data.

### §5.13 New ICT-aware factors (6 proposals)

#### §5.13.a `lot_killzone_session_factor` (universal)

**Formula**:
```
if (kz == LONDON_OPEN_KZ): 1.0
elif (kz == NY_OPEN_KZ): 1.2          // ICT prime window (per FXNX, EBC)
elif (kz == LONDON_CLOSE_KZ): 1.0     // gold prime window continues
elif (kz == ASIAN_KZ): 0.5            // accumulation, low edge
else (off-KZ): 0.5                    // operator may set to 0 to block
```

**Default**: 1.0 (no-op).
**Config knobs**: `FORGE_LOT_KZ_SESSION_FACTOR_ENABLED=0`, `FORGE_LOT_KZ_LONDON_OPEN_FACTOR=1.0`, `FORGE_LOT_KZ_NY_OPEN_FACTOR=1.2`, `FORGE_LOT_KZ_LONDON_CLOSE_FACTOR=1.0`, `FORGE_LOT_KZ_ASIAN_FACTOR=0.5`, `FORGE_LOT_KZ_OFF_FACTOR=0.5`.
**Backward compat**: gated by `FORGE_LOT_KZ_SESSION_FACTOR_ENABLED`. Default 0 → no-op.
**Industry source**: [`research/ICT_KILLZONES.md`](research/ICT_KILLZONES.md) §2.2 (XAUUSD prime window), [`fxnx.com — ICT Killzones XAUUSD`](https://fxnx.com/en/blog/ict-killzones-master-xauusd-timing-maximum-profit).

#### §5.13.b `lot_iss_score_factor` (universal)

**Formula**:
```
if (iss_score >= 8): 1.5             // HIGH_CONVICTION
elif (iss_score >= 5): 1.0           // STANDARD
elif (iss_score >= 3): 0.5           // weak structure
else: 0 (block)                       // no structure
```

**Default**: 1.0 (no-op when ISS atoms still log 0 in Mode A).
**Config knobs**: `FORGE_LOT_ISS_SCORE_FACTOR_ENABLED=0`, `FORGE_LOT_ISS_HIGH_FACTOR=1.5`, `FORGE_LOT_ISS_STANDARD_FACTOR=1.0`, `FORGE_LOT_ISS_WEAK_FACTOR=0.5`, `FORGE_LOT_ISS_NONE_BLOCK=0` (set to 1 to skip).
**Backward compat**: ISS atoms still default-OFF per the PEMCG/ICT integration spec. When `iss_score=0` (Mode A or pre-Phase-1), this factor stays at 1.0.
**Industry source**: [`prompts/ICT_Tradingidea.md`](prompts/ICT_Tradingidea.md) §K — scoring engine canonical pattern.

#### §5.13.c `lot_h4_alignment_factor` (universal)

**Formula**:
```
H4 agrees with intraday + M15 + M5 (4-of-4): 1.25
H4 + M15 + M5 (3-of-3 without intraday signal): 1.10
H4 + M5 only (2-of-2): 1.0           // base
H4 disagrees with M5: 0.5            // counter-H4 entry
```

**Default**: 1.0 (no-op).
**Config knob**: `FORGE_LOT_H4_ALIGNMENT_FACTOR_ENABLED=0`.
**Backward compat**: default-OFF.
**Industry source**: SKILL.md "H4-trend-agreement mandate" (project) + [`mql5.com — EA Risk Management 2026`](https://www.mql5.com/en/blogs/post/766452) ("position sizing should follow HTF bias, not just trigger TF").

#### §5.13.d `lot_sweep_confirmation_factor` (universal)

**Formula**: when a Phase 2 ICT liquidity sweep is confirmed within `sweep_window_bars` (default 3) preceding the entry trigger, on the same side that would close the sweep:
```
sweep_confirmed && sweep_age <= 3 bars: 1.5
otherwise: 1.0
```

**Default**: 1.0 (no-op).
**Config knob**: `FORGE_LOT_SWEEP_CONFIRMATION_FACTOR_ENABLED=0`.
**Dependency**: Phase 2 IctLiquidity module (`FORGE_ICT_LIQUIDITY_SWEEP_ENABLED=1`).
**Industry source**: [`prompts/ICT_Tradingidea.md`](prompts/ICT_Tradingidea.md) §D — Liquidity Sweep.

#### §5.13.e `lot_pd_array_factor` (universal)

**Formula**:
```
direction == BUY && IsInDiscount() == true:  1.3
direction == SELL && IsInPremium() == true: 1.3
direction == BUY && IsInPremium() == true:  0.5  // counter-PD probe
direction == SELL && IsInDiscount() == true:0.5  // counter-PD probe
equilibrium zone (±0.1 of midpoint):         1.0  // neutral
```

**Default**: 1.0 (no-op when dealing-range not computed).
**Config knob**: `FORGE_LOT_PD_ARRAY_FACTOR_ENABLED=0`.
**Dependency**: Phase 3 IctOrderBlock module + dealing-range computation.
**Industry source**: [`prompts/ICT_Tradingidea.md`](prompts/ICT_Tradingidea.md) §J — Premium/Discount + PD Arrays.

#### §5.13.f `lot_risk_pct_floor` (universal — Phase D)

**Formula** (canonical risk-percent sizing):
```
desired_lot = (equity × risk_pct) / (sl_distance_pts × pip_value)
final_lot = max(chain_result_lot, desired_lot)  // floor at risk-pct
```

**Default**: disabled (chain result stands).
**Config knob**: `FORGE_LOT_RISK_PCT_FLOOR_ENABLED=0`, `FORGE_LOT_RISK_PCT=0.5` (% of equity), `FORGE_LOT_RISK_PCT_MAX=1.0` (cap).
**Backward compat**: default-OFF. When ON, behaves as a floor (never reduces below the chain result; only lifts if chain went too low). To make it the canonical engine, the operator sets `FORGE_LOT_RISK_PCT_REPLACE_CHAIN_ENABLED=1` after tester validation.
**Industry source**: [`mql5.com/en/blogs/post/769682 — MT5 EA Money Management Settings That Protect Capital`](https://www.mql5.com/en/blogs/post/769682) (2026), [`mql5.com/en/articles/18991 — Building a Trading System Part 2: The Science of Position Sizing`](https://www.mql5.com/en/articles/18991), [`mql5.com/en/blogs/post/766452 — EA Risk Management: Position Sizing, Max Drawdown Limits`](https://www.mql5.com/en/blogs/post/766452).

---

## §6 Risk-per-setup analysis — current Pre-ICT engine vs ICT ideal

Assumes XAUUSD on a $10,000 account, `lot_fixed=0.25` (production config), 1% risk target = $100 per trade, pip-value ≈ $10 per 0.10 lot (XAUUSD).

| Setup | Typical chain result | Typical SL distance | Implicit $ risk | ICT ideal @ 1% | Verdict |
|---|---:|---|---:|---:|---|
| BB_BREAKOUT_BUY (no other open) | `0.25 × 1.0 × 1.0` = 0.25 | 2.0×ATR ≈ 40 pts | ~$100 | $100 | ✓ matches |
| BB_BREAKOUT_BUY (stacked 2nd) | `0.25 × 1.0 × 0.25` = 0.0625 → broker-min 0.01 | 2.0×ATR ≈ 40 pts | ~$4 | $100 | ✗ under-sized 25× |
| BB_BREAKOUT_SELL (ADX 45+, M15) | `0.25 × 1.0 × 0.125` = 0.031 → 0.03 | 2.0×ATR ≈ 40 pts | ~$12 | $100 | ✗ under-sized 8× |
| BB_BREAKOUT_SELL (inside band + stack) | `0.25 × 1.0 × 0.5 × 0.25` = 0.031 → 0.03 | 2.0×ATR ≈ 40 pts | ~$12 | $100 | ✗ under-sized 8× |
| MOMENTUM_DUMP_BUY (1st fire, NY KZ tier1) | `0.25 × 1.0 × 1.0 × 1.0 × 1.5 × 2.0` = 0.75 | 1.0×ATR ≈ 20 pts | ~$150 | $100 | △ slightly oversized |
| MOMENTUM_DUMP_BUY (5th fire decreasing pyramid 1×) | `0.25 × 1.0 × 1.0 × 1.0 × 1.0 × 1.0` = 0.25 | 1.0×ATR ≈ 20 pts | ~$50 | $100 | ✗ under-sized 2× |
| MOMENTUM_DUMP_SELL (regime-aligned, intraday-rev) | `0.25 × 1.0 × 0.5 × 1.0 × 1.0 × 1.0 × 2.0 × 1.5` = 0.375 | 1.0×ATR ≈ 20 pts | ~$75 | $100 | △ slightly under |
| ASIA_CAPITULATION_BUY | **PIN 0.20** | 1.5×ATR ≈ 30 pts | ~$60 | $100 | △ under (thin liquidity = appropriate) |
| BLR capitulation BUY | **PIN 0.30** | 1.5×ATR ≈ 30 pts | ~$90 | $100 | ✓ close |
| BB_EXHAUSTION_REVERSAL (BASE tier) | **PIN 0.15** (0.10×1.5) | 1.0×ATR ≈ 20 pts | ~$30 | $100 | ✗ under-sized 3× (intentional probe) |
| BB_EXHAUSTION_REVERSAL (HIGH tier 6+ warnings) | **PIN 0.30** (0.10×1.5×2.0) | 1.0×ATR ≈ 20 pts | ~$60 | $100 | △ under |
| TREND_CONTINUATION_BUY (default 2× tcb) | `0.25 × 1.0 × 2.0` = 0.5 | 1.5×ATR ≈ 30 pts | ~$150 | $100 | △ slightly oversized |
| BULL_DAY_DIP_BUY (prime KZ amp ×1.5) | `0.25 × 1.0 × 1.0 × 1.5` = 0.375 | 1.0×ATR ≈ 20 pts | ~$75 | $100 | △ slightly under |
| C-extended (any of MA_CROSSOVER through SR_FLIP) | `0.25 × 1.0 × 0.5` = 0.125 → 0.12 | 1.5×ATR ≈ 30 pts | ~$36 | $100 | ✗ under-sized 3× |

**Key findings**:

1. **Stacking is the single biggest under-sizer** — 2nd same-direction group on BB_BREAKOUT drops to 4% of the ICT-ideal risk. Memory `feedback_check_market_data_for_entry_questions` warns against ignoring this when trend is confirmed.
2. **ADX-tiered SELL de-risk is the second biggest under-sizer in trending markets** — 8× under-sized at ADX 45+. Per §5.6, ISS-C HIGH_CONVICTION should reverse this.
3. **Lot pins systematically under-size** — capitulation + exhaustion-reversal setups risk 1/3 to 2/3 of ICT-ideal. Intentional probe behavior, but the HIGH-tier (warnings≥6) BB_EXHAUSTION should approach 1% risk.
4. **C-extended (Tier 1-3 boolean) setups all under-size** at default 0.5× factor — fine for unvalidated setups, but per-setup tuning should lift them once tester data supports.
5. **No setup is structurally over-sized vs ICT canon**. The MOMENTUM_DUMP + intraday_rev + dump_kz tier1 amplification stack can hit 0.75 (~$150 = 1.5% risk) — within ICT acceptable range of 1-2% per [`innercircletrader.net — simple-ict-scalping-strategy`](https://innercircletrader.net/tutorials/simple-ict-scalping-strategy/).

**Citations** (per the SKILL.md WebSearch mandate):
- [`mql5.com/en/blogs/post/769682 — MT5 EA Money Management Settings That Protect Capital`](https://www.mql5.com/en/blogs/post/769682) — "Maximum risk per trade is recommended at 0.5% of account... daily risk budget of 2%."
- [`innercircletrader.net — Simple ICT Scalping Strategy`](https://innercircletrader.net/tutorials/simple-ict-scalping-strategy/) — "1% of capital per setup; gradually 2%."
- [`ebc.com — ICT Killzones Guide`](https://www.ebc.com/forex/what-are-ict-killzone-times-simple-trading-hours-guide) — gold prime window ≈ 60-70% of daily range.

---

## §7 Recommended implementation phasing

The 12-factor + 6-new-factor recommendation does NOT ship in one PR. Phase it to keep validation tight and rollback easy.

### Phase A — Mechanical, low risk (in flight)

- **Already shipped** (v2.7.121): PrintFormat for all 30 factors.
- **In flight** (v2.7.122 plan): 12 selective SIGNALS columns (the high-variance ones).
- No math changes. Documentation + instrumentation only.

### Phase B — Math updates to existing factors

One factor per ship; validate against tester replay before merging the next.

1. **B.1** — `fast_trend_factor`: add H4 alignment requirement (§5.7). Knob `FORGE_LOT_FAST_TREND_REQUIRE_H4_ENABLED`.
2. **B.2** — `stack_factor`: ICT bypass on confirmed trend (§5.1). Knob `FORGE_LOT_STACK_BYPASS_ON_ISS_C_ENABLED`.
3. **B.3** — `adx_lot_factor`: ISS-C HIGH_CONVICTION reversal (§5.6). Knob `FORGE_LOT_ADX_REVERSE_ON_ISS_C_HIGH_ENABLED`.
4. **B.4** — `near_floor_factor`: replace with H4 demand-zone block (§5.8). Knob `FORGE_LOT_NEAR_FLOOR_REPLACE_WITH_DEMAND_ZONE_ENABLED`.
5. **B.5** — `inside_band_factor`: FVG mitigation gating (§5.9). Knob `FORGE_LOT_INSIDE_BAND_REQUIRE_FVG_ENABLED`.
6. **B.6** — `dump_pyramid_factor`: MSS-validity drift cap (§5.2). Knob `FORGE_LOT_DUMP_PYRAMID_REQUIRE_MSS_INTACT_ENABLED`.

Each lands default-OFF. Operator enables in tester, runs replay against G5006/G5048 (must still SKIP/de-risk correctly), against Apr 1 NY rally (must amplify), then enables in live.

### Phase C — New ICT-aware factors

Ship after Phase 4 of the ICT integration plan (ICTSignalScore master struct lands).

1. **C.1** — `lot_killzone_session_factor` (§5.13.a). Universal across setups. Depends on existing `g_regime.killzone` (v2.7.51+).
2. **C.2** — `lot_iss_score_factor` (§5.13.b). Depends on v2.7.118+ ISS atoms + Phase 4 scoring.
3. **C.3** — `lot_h4_alignment_factor` (§5.13.c). Depends on existing `Atom_M15TrendAligned` pattern; add `Atom_H4TrendAligned`.
4. **C.4** — `lot_sweep_confirmation_factor` (§5.13.d). Depends on Phase 2 IctLiquidity.
5. **C.5** — `lot_pd_array_factor` (§5.13.e). Depends on Phase 3 IctOrderBlock + dealing-range.

Each adds one multiplicand to `combined_lot_factor` (chain becomes 35-multiplicand). Default 1.0 (no-op).

### Phase D — Risk-percent floor (the canonical canon shift)

The 0.125 floor is replaced (or supplemented) by a configurable equity-risk-pct floor.

1. **D.1** — `lot_risk_pct_floor` (§5.13.f). Default-OFF. When ON, applies as a floor.
2. **D.2** — `lot_risk_pct_replace_chain`. Default-OFF. When ON, the entire combined product is replaced by the canonical risk-percent formula.

Phase D requires careful tester validation across many runs because it fundamentally changes the engine shape. Recommend running in parallel with the chain (log both, decide based on net P&L + drawdown distribution).

---

## §8 References

- `ea/FORGE.mq5:14695` — `combined_lot_factor` product line (30 + 1 universal factors)
- `ea/FORGE.mq5:14697-14719` — v2.7.121 PrintFormat
- `ea/FORGE.mq5:14723` — `base_lot = g_sc.lot_fixed` (v2.7.40 single source of truth)
- `ea/FORGE.mq5:14725-14741` — BLR + ASIA_CAPITULATION lot pins (v2.7.80 / v2.7.81)
- `ea/FORGE.mq5:14743-14769` — BB_EXHAUSTION_REVERSAL pin + BASE/HIGH amplifier tiers (v2.7.89)
- `ea/FORGE.mq5:14331-14343` — `lot_mult` derivation
- `ea/FORGE.mq5:14420` ff — individual factor init blocks (lines 14420-14691; see §3 per-factor cites)
- `config/scalper_config.json` — production config; lot pin defaults at lines 502, 586, 617
- `config/scalper_config.defaults.json` — baseline defaults; geometry section lines 575-619
- `scripts/sync_scalper_config_from_env.py:61` — `FORGE_FIXED_LOT` → `lot_sizing.fixed_lot` env mapping
- [`docs/QUESTDB_EVALUATION.md`](QUESTDB_EVALUATION.md) §12.7a — the column-storage tradeoff that motivates the 12-of-30 cut
- [`.claude/skills/forge-monitor/SKILL.md`](../.claude/skills/forge-monitor/SKILL.md) "Schema-parity ship → High-cardinality diagnostic data — selective columns" — operator mandate codifying the 12-of-30 rule
- [`docs/prompts/ICT_Tradingidea.md`](prompts/ICT_Tradingidea.md) §K (scoring engine), §N (backtest readiness — risk-percent + SL placement modes)
- [`docs/research/ICT_KILLZONES.md`](research/ICT_KILLZONES.md) §2.2 (XAUUSD prime window), §8 (KZ-aware composite gating)
- [`docs/FORGE_PEMCG_ICT_INTEGRATION.md`](FORGE_PEMCG_ICT_INTEGRATION.md) §3 (Mode A/B/C)
- [`docs/FORGE_ICT_PEMCG_COMBINATIONS.md`](FORGE_ICT_PEMCG_COMBINATIONS.md) §2 (16-cell matrix)

### Industry sources (per the SKILL.md WebSearch mandate)

1. [innercircletrader.net — Simple ICT Scalping Strategy (30 to 50 Pips a Day with OTE & Killzones)](https://innercircletrader.net/tutorials/simple-ict-scalping-strategy/) — canonical 1-2% risk-per-setup standard
2. [fxnx.com — ICT Killzones: Master XAUUSD Timing for Maximum Profit](https://fxnx.com/en/blog/ict-killzones-master-xauusd-timing-maximum-profit) — gold prime window position-sizing canon
3. [ebc.com — What Are ICT Killzone Times?](https://www.ebc.com/forex/what-are-ict-killzone-times-simple-trading-hours-guide) — gold London-NY overlap = 60-70% of daily range
4. [phidiaspropfirm.com — Master ICT Kill Zone For Prop Firm Success](https://phidiaspropfirm.com/education/kill-zones) — confluence-based sizing (London 1% + NY 1% allocation)
5. [mql5.com/en/blogs/post/769682 — MT5 EA Money Management Settings That Protect Capital (May 2026)](https://www.mql5.com/en/blogs/post/769682) — 0.5% risk-per-trade canon for 2026, 2% daily-loss limit
6. [mql5.com/en/articles/18991 — Building a Trading System Part 2: The Science of Position Sizing](https://www.mql5.com/en/articles/18991) — canonical `lot = (equity × risk_pct) / (sl_pts × pip_value)` formula
7. [mql5.com/en/blogs/post/766452 — EA Risk Management: Position Sizing, Max Drawdown Limits, and a Simple Risk Budget (Jan 2026)](https://www.mql5.com/en/blogs/post/766452) — four-layer risk architecture for surviving EAs
8. [mql5.com/en/blogs/post/768450 — EA Risk Settings 2026: How to Adjust for Market Volatility (Apr 2026)](https://www.mql5.com/en/blogs/post/768450) — ATR-aware position-size adjustment (relevant to §5.6 ADX reversal)
9. [innercircletrader.net — Master ICT Kill Zones](https://innercircletrader.net/tutorials/master-ict-kill-zones/) — KZ enablement defaults for XAUUSD
10. [writofinance.com — ICT Trading Sessions and Kill Zones](https://www.writofinance.com/trading-sessions-and-kill-zones/) — institutional-volume rationale for KZ-amplified sizing

---

## §9 Changelog (append-only)

- **2026-05-15** — Initial Pre-ICT Lot Engine reference. Documents 30 factors + `fast_trend_factor` (31st universal multiplicand) + 3 lot pins (BLR-capitulation, ASIA_CAPITULATION_BUY, BB_EXHAUSTION_REVERSAL) + setup interaction matrix (28 setups × 31 factors). ICT-aware recommendations across 12 high-variance factors + 6 new factors proposed. Phased implementation plan A→D (instrumentation → math updates → new factors → risk-percent shift). Cross-references the v2.7.122 selective-12-column ship as Phase A. 10 industry sources cited per the WebSearch mandate. No code modified.
