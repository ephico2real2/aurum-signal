# FORGE Decision Stack Inventory — v2.7.36 extraction

**Source**: `ea/FORGE.mq5` @ #property version "2.106" (VERSION 2.7.36)
**Spec reference**: `FORGE_DECISION_STACK.md` — 5-layer architecture (Setup Trigger → Filter Chain → Boolean Composite → Atoms → Entry Geometry)
**Date**: 2026-05-12
**Methodology**: Every claim cites `file:line`. Filter chains were extracted by walking each setup_type block linearly through its if/else-if cascade. Atoms are the predicates that get NEGATED into gate codes.

---

## §1. Layer 1 — Setup Triggers

FORGE has **5 distinct setup types** spanning 8 setup×direction combinations. The "Setup Trigger" is the raw price/indicator structure check that opens a gate-evaluation block.

| Setup Type | Direction | Trigger condition | Trigger location |
|---|---|---|---|
| **BB_BREAKOUT** | BUY | `prev_close > m5_bb_u + breakout_buffer_points*point && m5_rsi > breakout_rsi_buy_min && m5_bull` | `ea/FORGE.mq5:6434` |
| **BB_BREAKOUT** | SELL | `prev_close < m5_bb_l - breakout_buffer_points*point && m5_rsi < breakout_rsi_sell_max` | `ea/FORGE.mq5:6655` |
| **BB_BREAKOUT_RETEST** | BUY | After a BB_BREAKOUT BUY entry, price returns to within `retest_atr_mult × ATR` of `m5_bb_u` then re-pushes above | `ea/FORGE.mq5:6642` (assigned via `g_retest`) |
| **BB_BREAKOUT_RETEST** | SELL | Mirror: returns to `m5_bb_l` band then re-pushes below | `ea/FORGE.mq5:6958` |
| **BB_BOUNCE** | BUY | `prev_close <= m5_bb_l * (1+bounce_bb_proximity_pct/100) && m5_rsi <= bounce_rsi_buy_max && h1_trend_strength >= bounce_min_h1_trend` | `ea/FORGE.mq5:6263` block entry |
| **BB_BOUNCE** | SELL | `prev_close >= m5_bb_u * (1-bounce_bb_proximity_pct/100) && m5_rsi >= bounce_rsi_sell_min` + symmetric H1 | `ea/FORGE.mq5:6341` block entry |
| **BB_PULLBACK_SCALP** | BUY | Fresh PSAR flip BELOW within `pullback_scalp_fresh_flip_bars`, `m5_adx <= pullback_scalp_max_adx`, cooldown elapsed | `ea/FORGE.mq5:6285-6293` |
| **BB_PULLBACK_SCALP** | SELL | Fresh PSAR flip ABOVE within window, ADX cap, cooldown elapsed | `ea/FORGE.mq5:6358-6366` |
| **MOMENTUM_DUMP** | SELL | `dump_sell_trig = (m5 N-bar move > dump_atr_mult × m5_atr)` + `dump_catch_enabled=1` | `ea/FORGE.mq5:7038` |
| **MOMENTUM_DUMP** | BUY | `dump_buy_trig = (m5 N-bar move < -dump_atr_mult × m5_atr)` + dump_catch_enabled=1 | `ea/FORGE.mq5:7115` block |

**Trigger boolean naming**: only `dump_sell_trig`/`dump_buy_trig` are named `*_trig` explicitly. Other setups use inline `if(...)` block conditions on the structural test. (Convention drift — flag for future rename.)

---

## §2. Layer 2 — Filter Chains

Filter chains are the **if/else-if cascades**. Each rung emits a `JournalRecordSignal("SKIP", "<gate_code>", ...)` and halts the entry. There are **3 chain-groups** in the EA:

### §2.1 Pre-trigger global safety chain (runs FIRST, before any setup evaluation)

Applies to every signal regardless of setup type. Location: `ea/FORGE.mq5:5650-5916`.

| Order | Gate Code | Predicate (what fires it) | File:line |
|---|---|---|---|
| 1 | `entry_quality_news_filter` | News window active (within configured before/after of high/medium/low event) | `:5738` |
| 2 | `entry_quality_direction_cap` | Direction-specific entry cap reached this session | `:5750` |
| 3 | `entry_quality_atr` | `m5_atr * point < entry_quality_atr_min` (insufficient volatility) | `:5758` |
| 4 | `entry_quality_body` | M5[1] body% < `entry_quality_body_pct_min` | `:5789` |
| 5 | `entry_quality_direction` | M5 direction (close vs prev_close) mis-aligned for proposed trade | `:5801` |
| 6 | `entry_quality_bb_contraction` | BB width contracting / squeeze guard | `:5816` |
| 7 | `session_off` | `!ScalperSessionOK()` (LONDON/NY/ASIAN/OFF + KZ gate if enabled) | `:5856` (was `:5611` pre-2.7.36) |
| 8 | `spread` | `spread > max_spread_points` (live only — tester skips) | `:5883` |
| 9 | `open_groups` | `open_groups >= max_open_groups` | `:5891` |
| 10 | `session_trade_cap` | `g_scalper_session_trades >= max_trades_per_session` (live only) | `:5901` |
| 11 | `cooldown` | `(TimeGMT() - g_scalper_last_loss_time) < loss_cooldown_sec` | `:5911` |

### §2.2 Per-setup filter chains (run AFTER trigger passes)

Each setup×direction has its own chain.

#### §2.2.1 BB_BREAKOUT BUY chain — `ea/FORGE.mq5:6447-6620`

| Order | Gate Code | Predicate |
|---|---|---|
| 1 | `entry_quality_daily_bear_block_buy` | `g_daily_bear_bias && daily_direction_gate_enabled` |
| 2 | `entry_quality_rsi_buy_ceil` | `m5_rsi >= breakout_rsi_buy_ceil` (default 78) |
| 3 | `entry_quality_h1_di_buy` | `require_h1_di_buy && h1_di_plus < h1_di_minus && m5_adx < counter_buy_adx_threshold` (default 28) |
| 4 | `entry_quality_h4_rsi_buy_blocked` | `h4_rsi_v` outside acceptable band |
| 5 | `entry_quality_h4_adx_buy_blocked` | `h4_adx_v` indicates H4 bear strength |
| 6 | `entry_quality_h1_macd_buy` | `require_h1_macd_buy && h1_macd_hist <= 0` |
| 7 | `entry_quality_breakout_cooldown` | `(now - g_scalper_last_bb_breakout_buy) < same_dir_cooldown_seconds` |
| 8 | `entry_quality_breakout_failed_samebar` | breakout_failed_same_bar_hard_block && prior atr_ext SKIP in current M5 bar |
| 9 | `entry_quality_breakout_failed` | failed_gate_enabled && RSI dropped from recent peak |
| 10 | `entry_quality_psar_misalign_buy` | `require_psar_align && g_psar_state != "BELOW"` |
| 11 | `entry_quality_news_rsi_tighten` | News-window RSI tightening active |

#### §2.2.2 BB_BREAKOUT SELL chain — `ea/FORGE.mq5:6670-6939`

| Order | Gate Code | Predicate |
|---|---|---|
| 1 | `entry_quality_daily_bull_block_sell` | `g_daily_bull_bias && daily_direction_gate_enabled` |
| 2 | `entry_quality_session_sell_cutoff` | `session_ny_sell_cutoff_utc > 0 && hour >= cutoff` |
| 3 | `entry_quality_adx_extreme_sell` | `m15_adx >= breakout_adx_sell_block_threshold` (default 55) |
| 4 | `entry_quality_adx_min_sell` | `m5_adx < breakout_adx_min_sell && !crash_sell_bypass` |
| 5 | `entry_quality_h1_di_sell` | `require_h1_di_sell && h1_di_plus >= h1_di_minus` (no ADX bypass) |
| 6 | `entry_quality_adx_spike_sell` | ADX from low-base spike rejected (`!crash_sell_bypass`) |
| 7 | `entry_quality_rsi_rising_sell` | M5 RSI rising despite SELL trigger (`!crash_sell_bypass`) |
| 8 | `entry_quality_hid_bull_div_sell` | `block_hid_bull_sell && g_rsi_div_type == "HID_BULL"` |
| 9 | `entry_quality_h1_macd_sell` | `require_h1_macd_sell && h1_macd_hist >= 0` |
| 10 | `entry_quality_m30_not_bearish` | `require_m30_bear_sell && m30_trend_strength > 0` |
| 11 | `entry_quality_h4_rsi_sell_blocked` | H4 RSI not bearish enough |
| 12 | `entry_quality_h4_adx_sell_blocked` | H4 ADX indicates bull strength |
| 13 | `entry_quality_breakout_cooldown` | Same-dir SELL cooldown active |
| 14 | `entry_quality_psar_misalign_sell` | `g_psar_state != "ABOVE"` |
| 15 | `entry_quality_news_rsi_tighten` | News tightening active |

#### §2.2.3 BB_BOUNCE BUY chain — `ea/FORGE.mq5:6263-6302`

| Order | Gate Code | Predicate |
|---|---|---|
| 1 | `entry_quality_daily_bear_block_buy` | Daily bear bias blocks BUY |
| 2 | `entry_quality_psar_misalign_buy` | PSAR not below (when require_psar_align) |

Brief chain — BB_BOUNCE delegates most quality gates to bounce_* config knobs evaluated in the trigger condition itself.

#### §2.2.4 BB_BOUNCE SELL chain — `ea/FORGE.mq5:6341-6375`

| Order | Gate Code | Predicate |
|---|---|---|
| 1 | `entry_quality_daily_bull_block_sell` | Daily bull bias blocks SELL |
| 2 | `entry_quality_psar_misalign_sell` | PSAR not above |

#### §2.2.5 BB_PULLBACK_SCALP BUY chain — `ea/FORGE.mq5:6285-6324`

Trigger-condition incorporates the filter chain. PSAR mis-alignment is the only post-trigger gate. Emits `entry_quality_psar_misalign_buy` with `setup_type="BB_BOUNCE"` (note: setup attribution drift — chain emits BB_BOUNCE label even though it's the pullback path).

#### §2.2.6 BB_PULLBACK_SCALP SELL chain — `ea/FORGE.mq5:6358-6398`

Symmetric to BUY. Emits `entry_quality_psar_misalign_sell` under `setup_type="BB_BOUNCE"`.

#### §2.2.7 MOMENTUM_DUMP SELL chain — `ea/FORGE.mq5:7029-7090`

| Order | Gate Code | Predicate |
|---|---|---|
| 1 | `dump_bar_confirm_missing` | `dump_require_bar_confirm && !bar_confirm_sell` |
| 2 | `dump_h1_trend_block_sell` | `dump_sell_h1_max > 0 && h1_trend_strength >= dump_sell_h1_max` (default 2.0) |
| 3 | `dump_rsi_block` | `m5_rsi >= dump_max_rsi` (default 41 — gold chop fix per memory) |
| 4 | `dump_adx_block` | `m5_adx < dump_min_adx` (default 20) |
| 5 | `dump_psar_block` | `g_psar_state != "ABOVE"` |
| 6 | `dump_d1_bias_block` | `dump_require_d1_bias && d1_open <= d1_close` (no bear D1) |
| 7 | `dump_cooldown` | `(now - g_scalper_last_dump_sell_time) < dump_cooldown_seconds` |
| 8 | `dump_chop_block` | `g_regime_label == "RANGE"` |

#### §2.2.8 MOMENTUM_DUMP BUY chain — `ea/FORGE.mq5:7115-7172`

| Order | Gate Code | Predicate |
|---|---|---|
| 1 | `dump_rsi_buy_ceil` | `m5_rsi >= dump_max_rsi_buy` (default 70) |
| 2 | `dump_rsi_block` | `m5_rsi <= dump_max_rsi` (BUY needs RSI exhaustion ABOVE 41) — mirror |
| 3 | `entry_quality_daily_bear_block_buy` | Daily bear bias |
| 4 | `dump_adx_block` | `m5_adx < dump_min_adx` |
| 5 | `dump_psar_block` | `g_psar_state != "BELOW"` |
| 6 | `dump_d1_bias_block` | `dump_require_d1_bias && d1_open >= d1_close` |
| 7 | `dump_cooldown` | Same-dir dump cooldown |
| 8 | `dump_chop_block` | `g_regime_label == "RANGE"` |

### §2.3 Post-direction global chain (runs AFTER setup_type assigned, BEFORE execution)

Location: `ea/FORGE.mq5:7180-7330`. Applies to every chosen direction regardless of which setup fired.

| Order | Gate Code | Predicate | File:line |
|---|---|---|---|
| 1 | `direction_cooldown` | `direction_cooldown_enabled && bars_since_last_dir < direction_cooldown_bars` | `:7188` |
| 2 | `post_sl_cooldown` | Post-SL cooldown active | `:7192` |
| 3 | `m1` | M1 confirmation gate failed | `:7199` |
| 4 | `regime_countertrend` | regime_apply_policy && regime_confidence>=ct_min_conf && counter-trend direction | `:7207` |
| 5 | `no_setup` | No `setup_type` survived all triggers | `:7233` |
| 6 | `rr_too_low` | Risk/reward of computed geometry below `min_rr` floor | `:7328` |

### §2.4 Execution-failure chain (runs in PlaceOpenGroupLeg)

Location: `ea/FORGE.mq5:7581, 8274-8403`. These fire AFTER all entry decisions pass but order placement fails for broker/structural reasons.

| Gate Code | Predicate |
|---|---|
| `execution_failed` | `OrderSend` returned failure |
| `open_group_<reason>` | Generic group-open failure (broker error, lot rounding, etc.) |
| `open_group_invalid_stops` | SL/TP violates broker stop-level constraints |
| `open_group_missing_stoplimit` | Stop-limit order missing trigger price |
| `open_group_bad_stoplimit_trigger` | Stop-limit trigger price invalid |
| `open_group_bad_stoplimit_price` | Stop-limit limit price invalid |
| `open_group_rr_below_floor` | Computed entry has RR below floor |
| `open_group_unsupported_order_type` | Order type not recognized |

---

## §3. Layer 3 — Boolean Composites (logical-formula equivalents)

Each filter chain has a **TRUE/FALSE composite spec** that captures the full entry rule. The composite is `TRUE` iff every chain rung passes. These are the "if" half of the decision; the "then" half is Entry Geometry.

### §3.1 BB_BREAKOUT_BUY composite

```
BB_BREAKOUT_BUY ≡
   prev_close > m5_bb_u + breakout_buffer_points*point          // trigger
   && m5_rsi > breakout_rsi_buy_min                              // trigger
   && m5_bull                                                    // trigger
   && (!g_daily_bear_bias || !daily_direction_gate_enabled)     // ¬gate1
   && m5_rsi < breakout_rsi_buy_ceil                             // ¬gate2
   && (!require_h1_di_buy || h1_di_plus >= h1_di_minus || m5_adx >= counter_buy_adx_threshold) // ¬gate3
   && h4_rsi_v within band                                       // ¬gate4
   && h4_adx_v within band                                       // ¬gate5
   && (!require_h1_macd_buy || h1_macd_hist > 0)                 // ¬gate6
   && (now - last_bb_breakout_buy) >= same_dir_cooldown_seconds  // ¬gate7
   && !breakout_failed_samebar                                   // ¬gate8
   && !breakout_failed_recent_rsi_drop                           // ¬gate9
   && (!require_psar_align || g_psar_state == "BELOW")           // ¬gate10
   && !news_rsi_tighten_active                                   // ¬gate11
   ;
```

### §3.2 BB_BREAKOUT_SELL composite

```
BB_BREAKOUT_SELL ≡
   prev_close < m5_bb_l - breakout_buffer_points*point           // trigger
   && m5_rsi < breakout_rsi_sell_max                             // trigger
   && (!g_daily_bull_bias || !daily_direction_gate_enabled)     // ¬gate1
   && (session_ny_sell_cutoff_utc == 0 || hour < cutoff)        // ¬gate2
   && m15_adx < breakout_adx_sell_block_threshold                // ¬gate3
   && (m5_adx >= breakout_adx_min_sell || crash_sell_bypass)    // ¬gate4
   && (!require_h1_di_sell || h1_di_plus < h1_di_minus)          // ¬gate5  (asymmetric — no ADX bypass)
   && (!adx_spike_from_flat || crash_sell_bypass)               // ¬gate6
   && (!m5_rsi_rising || crash_sell_bypass)                     // ¬gate7
   && (!block_hid_bull_sell || g_rsi_div_type != "HID_BULL")    // ¬gate8
   && (!require_h1_macd_sell || h1_macd_hist < 0)               // ¬gate9
   && (!require_m30_bear_sell || m30_trend_strength <= 0)       // ¬gate10
   && h4_rsi_v within bear-band                                  // ¬gate11
   && h4_adx_v within bear-band                                  // ¬gate12
   && (now - last_bb_breakout_sell) >= same_dir_cooldown_seconds // ¬gate13
   && (!require_psar_align || g_psar_state == "ABOVE")           // ¬gate14
   && !news_rsi_tighten_active                                   // ¬gate15
   ;
```

### §3.3 BB_BOUNCE_BUY composite

```
BB_BOUNCE_BUY ≡
   prev_close <= m5_bb_l * (1 + bounce_bb_proximity_pct/100)
   && m5_rsi <= bounce_rsi_buy_max
   && h1_trend_strength >= bounce_min_h1_trend
   && (!g_daily_bear_bias || !daily_direction_gate_enabled)
   && (!require_psar_align || g_psar_state == "BELOW")
   && bounce_lot_factor > 0                                      // structural
   ;
```

### §3.4 BB_BOUNCE_SELL composite

```
BB_BOUNCE_SELL ≡
   prev_close >= m5_bb_u * (1 - bounce_bb_proximity_pct/100)
   && m5_rsi >= bounce_rsi_sell_min
   && (h1_trend_strength <= -bounce_min_h1_trend || !block_htf_align)
   && (!g_daily_bull_bias || !daily_direction_gate_enabled)
   && (!require_psar_align || g_psar_state == "ABOVE")
   ;
```

### §3.5 MOMENTUM_DUMP_SELL composite (canonical example from spec)

```
MOMENTUM_DUMP_SELL ≡
   dump_sell_trig                                                // trigger
   && dump_catch_enabled
   && (!dump_require_bar_confirm || bar_confirm_sell)
   && (dump_sell_h1_max <= 0 || h1_trend_strength < dump_sell_h1_max)
   && m5_rsi < dump_max_rsi
   && m5_adx >= dump_min_adx
   && g_psar_state == "ABOVE"
   && (!dump_require_d1_bias || d1_open > d1_close)
   && (now - g_scalper_last_dump_sell_time) >= dump_cooldown_seconds
   && g_regime_label != "RANGE"
   ;
```

### §3.6 MOMENTUM_DUMP_BUY composite

```
MOMENTUM_DUMP_BUY ≡
   dump_buy_trig
   && dump_catch_enabled
   && m5_rsi < dump_max_rsi_buy
   && m5_rsi > dump_max_rsi              // BUY needs RSI exhaustion ABOVE the SELL threshold
   && (!g_daily_bear_bias || !daily_direction_gate_enabled)
   && m5_adx >= dump_min_adx
   && g_psar_state == "BELOW"
   && (!dump_require_d1_bias || d1_open < d1_close)
   && (now - g_scalper_last_dump_buy_time) >= dump_cooldown_seconds
   && g_regime_label != "RANGE"
   ;
```

### §3.7 BB_PULLBACK_SCALP_{BUY,SELL} composites

```
BB_PULLBACK_SCALP_BUY ≡
   pullback_scalp_enabled
   && psar_just_flipped_below_within(pullback_scalp_fresh_flip_bars)
   && m5_adx <= pullback_scalp_max_adx
   && (now - g_pullback_scalp_last_buy_time) >= pullback_scalp_cooldown_seconds
   && (!require_psar_align || g_psar_state == "BELOW")
   ;
```

Symmetric SELL.

### §3.8 BB_BREAKOUT_RETEST composites

Composite = `BB_BREAKOUT_{BUY,SELL}` composite **plus** the retest condition:
```
retest_active && price_within_atr_band(m5_bb_{u,l}, retest_atr_mult) && re_push_confirmed
```
The retest path reuses the breakout filter chain — same atoms, only the trigger differs.

---

## §4. Layer 4 — Atoms (predicates extracted from composites)

Atoms group naturally by indicator category. Every atom below is referenced by ≥1 composite above.

### §4.1 M5 momentum atoms
- `m5_rsi < breakout_rsi_buy_min` (40) / `> ceil` (78)
- `m5_rsi < breakout_rsi_sell_max` (60) / `> floor` (33)
- `m5_rsi <= bounce_rsi_buy_max` (35) / `>= bounce_rsi_sell_min` (65)
- `m5_rsi < dump_max_rsi` (41) / `< dump_max_rsi_buy` (70)
- `m5_adx >= breakout_adx_min` (20) / `>= breakout_adx_min_sell` (25)
- `m5_adx >= dump_min_adx` (20)
- `m5_adx <= pullback_scalp_max_adx` (30)
- `m5_adx < counter_buy_adx_threshold` (28) — bypass condition for H1 DI gate

### §4.2 M5 structure atoms
- `m5_bull` (M5 close > open)
- `prev_close > m5_bb_u + breakout_buffer` (BB upper break)
- `prev_close < m5_bb_l - breakout_buffer` (BB lower break)
- `prev_close <= m5_bb_l * (1+bb_proximity_pct/100)` (near lower band)
- `prev_close >= m5_bb_u * (1-bb_proximity_pct/100)` (near upper band)
- `m5_atr * point >= entry_quality_atr_min` (vol floor)
- `m5_body_pct >= entry_quality_body_pct_min` (rejection candle quality)

### §4.3 HTF (H1) atoms — partial inventory in SIGNALS today
- `h1_trend_strength >= bounce_min_h1_trend` (0.3) — used by BB_BOUNCE BUY
- `h1_trend_strength >= dump_sell_h1_max` (2.0) — blocks dump SELL
- `h1_di_plus < h1_di_minus` — H1 DI gate (NOT logged as columns; only gate decision)
- `h1_macd_hist > 0` / `< 0` — H1 MACD gate (column `macd_histogram` stores this)
- `h1_atr`, `h1_ema20`, `h1_ema50`, `h1_bb_*` — used in trend-strength calc; not journaled individually

### §4.4 HTF (H4) atoms — NOT logged today
- `h4_rsi_v` within bear/bull band
- `h4_adx_v` within bear/bull band
- `h4_trend_strength` — would be a column

### §4.5 M15/M30 atoms — partial
- `m15_adx < breakout_adx_sell_block_threshold` (55) — ADX-extreme block
- `m30_trend_strength <= 0` — m30_not_bearish gate

### §4.6 Daily atoms — NOT logged today
- `d1_open > d1_close` (daily bear) — dump_d1_bias_block SELL
- `d1_open < d1_close` (daily bull) — dump_d1_bias_block BUY
- `g_daily_bull_bias`, `g_daily_bear_bias` (computed at session start)

### §4.7 Pattern/divergence atoms
- `g_rsi_div_type == "HID_BULL"` blocks SELL
- `g_psar_state == "ABOVE"` / `"BELOW"` / `"NONE"`
- `pattern_score >= threshold` (currently logged as 0 — bug)

### §4.8 Regime atoms
- `g_regime_label != "RANGE"` — chop block
- `g_regime_confidence >= ct_min_conf` — countertrend block

### §4.9 Time/session atoms
- `ScalperSessionOK()` (session label not OFF, not skipped)
- `killzones_enabled && killzones_gate_entries → KZ active` (v2.7.36 NEW)
- `(now - last_dir_entry) >= direction_cooldown_bars` — direction cooldown
- `(now - last_loss) >= loss_cooldown_sec` — post-loss cooldown
- `hour < session_ny_sell_cutoff_utc` — SELL cutoff window
- `news_filter_active(direction)` — news guard

### §4.10 Counter / structural atoms
- `open_groups < max_open_groups`
- `session_trades < max_trades_per_session`
- `spread <= max_spread_points`

---

## §5. Layer 5 — Entry Geometry (per setup × direction)

Once a composite returns TRUE, geometry is assigned. Each row = (setup, direction, SL formula, TP1 formula, TP2 formula, lot factor).

### §5.1 BB_BREAKOUT
| Direction | SL | TP1 | TP2 | Notes | File:line |
|---|---|---|---|---|---|
| BUY | `bid - m5_atr * breakout_buy_sl_atr_mult` (fallback to `breakout_sl_atr_mult` if buy override=0) | `ask + m5_atr * tp1_buy_atr_mult` (0.5 default) → fallback `tp1_atr_mult` (0.4) | `ask + m5_atr * tp2_atr_mult` (1.5) | ATR-based; tp3=2.5×ATR registered on entry | `:6648-6650` |
| SELL | `ask + m5_atr * breakout_sl_atr_mult` | `bid - m5_atr * tp1_sell_atr_mult` (0.4) | `bid - m5_atr * tp2_atr_mult` (1.5) | tp3 registered | `:6964-6966` |

### §5.2 BB_BREAKOUT_RETEST
Identical to BB_BREAKOUT but uses `g_retest.{sl,tp1,tp2}` snapshot from the original breakout. Re-entry stays inside ±retest_atr_mult×ATR band. `ea/FORGE.mq5:6187-6189`.

### §5.3 BB_BOUNCE
| Direction | SL | TP1 | TP2 | Notes | File:line |
|---|---|---|---|---|---|
| BUY | `FindStructuralSL(bid - m5_atr*bounce_sl_atr_mult)`, floored by `bid - m5_atr*min_sl_atr_mult` | `m5_bb_m`, adjusted to `poc_price` or `vwap_price` or `fib_382` if within band | `m5_bb_u`, adjusted to `fib_618` | Min 0.4×ATR / 0.8×ATR enforced | `:6307-6327` |
| SELL | Mirror via `FindStructuralSL` | `m5_bb_m` → `poc/vwap/fib_618` | `m5_bb_l` → `fib_382` | Symmetric mins | `:6380-6400` |

### §5.4 BB_PULLBACK_SCALP
| Direction | SL | TP1 | TP2 | File:line |
|---|---|---|---|---|
| BUY | `bid - m5_atr * pullback_scalp_sl_atr_mult` (2.5) | `ask + m5_atr * pullback_scalp_tp1_atr_mult` (0.3) | `ask + m5_atr * pullback_scalp_tp2_atr_mult` (0.7) | `:6288-6294` |
| SELL | `ask + m5_atr * 2.5` | `bid - m5_atr * 0.3` | `bid - m5_atr * 0.7` | `:6361-6367` |

### §5.5 MOMENTUM_DUMP
| Direction | SL | TP1 | TP2 | Notes | File:line |
|---|---|---|---|---|---|
| SELL | `ask + m5_atr * 4.0` | `bid - m5_atr * 0.6` | `bid - m5_atr * 1.0` | Hard-coded multipliers | `:7101-7103` |
| BUY | `bid - m5_atr * 4.0` | `ask + m5_atr * 0.6` | `ask + m5_atr * 1.0` | Hard-coded | `:7177-7179` |

### §5.6 News-window override (applies to any setup when news window active)
`tp1 = bid ± m5_atr * dd_tight_tp_atr` (0.8), `tp2 = 0` (no runners). `ea/FORGE.mq5:7273-7276`.

### §5.7 Lot factor pipeline (combined_lot_factor) — applies to all setups
| Factor | Where | What |
|---|---|---|
| `inside_band_factor` | `:7431` | SELL price above BB_lower → 0.25 |
| `near_floor_factor` | `:7442` | SELL crash-bypass + RSI 20-25 → 0.25 |
| `stack_factor` | `:7449` | First same-dir group = 1.0; stacked = 0.25 |
| `adx_lot_factor` | `:7467` | ADX-tier multiplier (mid=1.0, high=1.0 — confirmed not 0.125 per memory) |
| Setup-specific | `:7474` | bounce_lot_factor (0.25), dump_*_lot_factor, pullback_scalp_lot_factor |
| Regime override | `:7475+` | `regime_h1_override_factor` (2.0) when H1-strong |
| Floor | `:7493` | `max(combined_lot_factor, 0.125)` |

### §5.8 Leg count (ADX-conditional)
- Base: `lot_num_trades` (default 5)
- `m5_adx < 25` → `base_n = max(1, base_n - 1)`
- `m5_adx ≥ 35 && < sell_block_threshold` → `base_n + 2`
- Capped by `forge_resolve_num_trades_max_cap` (5) and gold-SELL cap (10)
- `ea/FORGE.mq5:7372-7421`

---

## §6. Cross-cutting indicators consumed but not journaled

These are referenced in atoms above but missing from the SIGNALS column inventory. The Logging Extension Design v2.7.37 (`docs/FORGE_LOGGING_EXTENSION_DESIGN.md`) proposes adding them.

| Indicator | Used in atoms | Currently in SIGNALS? |
|---|---|---|
| `h1_di_plus`, `h1_di_minus` | H1 DI gate (BUY+SELL) | ✗ NO — only the gate decision |
| `h4_trend_strength` | H4 alignment | ✗ NO |
| `h4_rsi_v`, `h4_adx_v` | H4 RSI/ADX block | ✗ NO |
| `m15_trend_strength` | M15 alignment | ✗ NO |
| `m30_trend_strength` | m30_not_bearish | ✗ NO |
| `d1_open`, `d1_close` | dump_d1_bias_block | ✗ NO |
| `day_high`, `day_low` | (potential composites) | ✗ NO |
| `pattern_score` | entry quality | ✗ logged as 0 (bug) |
| `m5_lh_cascade`, `m5_hl_cascade` | cascade composites | ✗ NO (computed live, not logged) |
| `m5_body_pct` | rejection candle | ✗ NO (computed live) |
| OHLC bar[0]+bar[1] across all TFs | breakout/reversal logic | ✗ NO |
| `h1_atr`, `h4_atr`, `m15_atr`, `m1_atr` | structural calcs | ✗ NO |
| `h1_bb_*`, `h4_bb_*` | structural | ✗ NO |

---

## §7. Trace map — gate_code → atom → composite → file:line

This is the **debugging lookup table**. Use to answer: "When I see `SKIP gate=X` in the journal, what atom failed?"

| Gate Code | Negated Atom | Belongs to Composite | EA line |
|---|---|---|---|
| `entry_quality_news_filter` | `!news_filter_active(direction)` | (pre-trigger, all setups) | `:5738` |
| `entry_quality_atr` | `m5_atr*point >= atr_min` | (pre-trigger) | `:5758` |
| `entry_quality_body` | `m5_body_pct >= body_pct_min` | (pre-trigger) | `:5789` |
| `entry_quality_direction` | M5 dir aligned | (pre-trigger) | `:5801` |
| `entry_quality_bb_contraction` | `bb_width_expanding` | (pre-trigger) | `:5816` |
| `session_off` | `ScalperSessionOK()` | (pre-trigger) | `:5856` |
| `spread` | `spread <= max_spread_points` | (pre-trigger) | `:5883` |
| `open_groups` | `open_groups < max_open_groups` | (pre-trigger) | `:5891` |
| `session_trade_cap` | `session_trades < max_trades_per_session` | (pre-trigger) | `:5901` |
| `cooldown` | `(now-last_loss) >= loss_cooldown_sec` | (pre-trigger) | `:5911` |
| `entry_quality_daily_bear_block_buy` | `!g_daily_bear_bias` | BB_BREAKOUT_BUY, BB_BOUNCE_BUY, MOMENTUM_DUMP_BUY | `:6447, :6263, :7135` |
| `entry_quality_daily_bull_block_sell` | `!g_daily_bull_bias` | BB_BREAKOUT_SELL, BB_BOUNCE_SELL | `:6670, :6341` |
| `entry_quality_rsi_buy_ceil` | `m5_rsi < breakout_rsi_buy_ceil` | BB_BREAKOUT_BUY | `:6456` |
| `entry_quality_h1_di_buy` | `h1_di_plus >= h1_di_minus || m5_adx >= counter_buy_adx_threshold` | BB_BREAKOUT_BUY | `:6467` |
| `entry_quality_h4_rsi_buy_blocked` | H4 RSI in band | BB_BREAKOUT_BUY | `:6501` |
| `entry_quality_h4_adx_buy_blocked` | H4 ADX in band | BB_BREAKOUT_BUY | `:6510` |
| `entry_quality_h1_macd_buy` | `h1_macd_hist > 0` | BB_BREAKOUT_BUY | `:6528` |
| `entry_quality_breakout_cooldown` | `(now-last_breakout_buy) >= same_dir_cooldown` | BB_BREAKOUT_{BUY,SELL} | `:6546, :6915` |
| `entry_quality_breakout_failed_samebar` | No prior atr_ext SKIP this bar | BB_BREAKOUT_BUY | `:6570` |
| `entry_quality_breakout_failed` | No recent RSI peak drop | BB_BREAKOUT_BUY | `:6590` |
| `entry_quality_psar_misalign_buy` | `g_psar_state == "BELOW"` | BB_BREAKOUT_BUY, BB_BOUNCE_BUY, BB_PULLBACK_SCALP_BUY | `:6607, :6302, BB_PULLBACK_SCALP_BUY shares line` |
| `entry_quality_news_rsi_tighten` | `!news_rsi_tighten_active` | BB_BREAKOUT_{BUY,SELL}, BB_BREAKOUT_RETEST | `:6172, :6178, :6617, :6939` |
| `entry_quality_session_sell_cutoff` | `hour < cutoff` | BB_BREAKOUT_SELL | `:6683` |
| `entry_quality_adx_extreme_sell` | `m15_adx < block_threshold` | BB_BREAKOUT_SELL | `:6696` |
| `entry_quality_adx_min_sell` | `m5_adx >= adx_min_sell || crash_sell_bypass` | BB_BREAKOUT_SELL | `:6703` |
| `entry_quality_h1_di_sell` | `h1_di_plus < h1_di_minus` (asymmetric — no ADX bypass) | BB_BREAKOUT_SELL | `:6724` |
| `entry_quality_adx_spike_sell` | No ADX spike from flat (or crash bypass) | BB_BREAKOUT_SELL | `:6778` |
| `entry_quality_rsi_rising_sell` | M5 RSI not rising (or crash bypass) | BB_BREAKOUT_SELL | `:6796` |
| `entry_quality_hid_bull_div_sell` | `g_rsi_div_type != "HID_BULL"` | BB_BREAKOUT_SELL | `:6812` |
| `entry_quality_h1_macd_sell` | `h1_macd_hist < 0` | BB_BREAKOUT_SELL | `:6853` |
| `entry_quality_m30_not_bearish` | `m30_trend_strength <= 0` | BB_BREAKOUT_SELL | `:6875` |
| `entry_quality_h4_rsi_sell_blocked` | H4 RSI in bear band | BB_BREAKOUT_SELL | `:6889` |
| `entry_quality_h4_adx_sell_blocked` | H4 ADX in bear band | BB_BREAKOUT_SELL | `:6901` |
| `entry_quality_psar_misalign_sell` | `g_psar_state == "ABOVE"` | BB_BREAKOUT_SELL, BB_BOUNCE_SELL, BB_PULLBACK_SCALP_SELL | `:6928, :6375` |
| `dump_bar_confirm_missing` | `!dump_require_bar_confirm || bar_confirm_sell` | MOMENTUM_DUMP_SELL | `:7029` |
| `dump_h1_trend_block_sell` | `h1_trend_strength < dump_sell_h1_max` | MOMENTUM_DUMP_SELL | `:7048` |
| `dump_rsi_block` | `m5_rsi < dump_max_rsi` (SELL) / `> dump_max_rsi` (BUY) | MOMENTUM_DUMP_{SELL,BUY} | `:7055, :7124` |
| `dump_rsi_buy_ceil` | `m5_rsi < dump_max_rsi_buy` | MOMENTUM_DUMP_BUY | `:7118` |
| `dump_adx_block` | `m5_adx >= dump_min_adx` | MOMENTUM_DUMP_{SELL,BUY} | `:7062, :7141` |
| `dump_psar_block` | `g_psar_state == "ABOVE"` (SELL) / `"BELOW"` (BUY) | MOMENTUM_DUMP_{SELL,BUY} | `:7068, :7147` |
| `dump_d1_bias_block` | `d1_open > d1_close` (SELL) / `<` (BUY) | MOMENTUM_DUMP_{SELL,BUY} | `:7074, :7153` |
| `dump_cooldown` | `(now-last_dump) >= dump_cooldown_seconds` | MOMENTUM_DUMP_{SELL,BUY} | `:7082, :7161` |
| `dump_chop_block` | `g_regime_label != "RANGE"` | MOMENTUM_DUMP_{SELL,BUY} | `:7090, :7168` |
| `direction_cooldown` | `bars_since_last_dir >= direction_cooldown_bars` | (post-direction, all setups) | `:7188` |
| `post_sl_cooldown` | (post-SL cooldown elapsed) | (post-direction) | `:7192` |
| `m1` | M1 confirmation passed | (post-direction) | `:7199` |
| `regime_countertrend` | Not counter-trend | (post-direction) | `:7207` |
| `no_setup` | (no setup_type assigned) | (post-direction) | `:7233` |
| `rr_too_low` | `rr >= min_rr` | (geometry validation) | `:7328` |
| `execution_failed` | `OrderSend` succeeded | (execution) | `:7581` |
| `open_group_*` | broker stop/lot/order constraints met | (execution) | `:8274+` |

---

## §8. Findings & gaps (versus the Decision Stack spec)

| Finding | Severity | Where | Recommendation |
|---|---|---|---|
| **Setup Trigger naming inconsistency** | Low | Only `dump_{sell,buy}_trig` follow the `*_trig` convention. BB_BREAKOUT/BB_BOUNCE/BB_PULLBACK_SCALP use inline `if(...)`. | Refactor v2.7.37+: introduce `bb_breakout_buy_trig`, `bb_bounce_sell_trig`, etc. for spec parity. |
| **Setup attribution drift in BB_PULLBACK_SCALP** | Low | `entry_quality_psar_misalign_{buy,sell}` from the pullback path emits `setup_type="BB_BOUNCE"` (`:6302, :6375`) | Either rename the gate to `entry_quality_psar_misalign_pullback_*` or pass the correct setup type. |
| **H1 DI gate asymmetric** | Documented | SELL H1 DI gate has no ADX bypass; BUY does (at `counter_buy_adx_threshold=28`) | Confirmed intentional per `FORGE_ENTRY_CONDITIONS.md`; document in §3.2 |
| **Atoms reference globals not in SIGNALS** | Telemetry | `h1_di_plus`, `h1_di_minus`, `h4_trend_strength`, `d1_open/close`, `m5_body_pct`, OHLC for D1/M5[1], etc. | See §6 — Logging Extension Design v2.7.37 closes this. |
| **`pattern_score`, `m15_adx`, `macd_histogram` logged as 0** | Bug | Atlas §3 gap (logging extension §1.1) | 2.7.12 partially fixed `m15_adx`/`macd_histogram` at TAKEN sites; still 0 at SKIP sites — extension closes remaining 52 call sites. |
| **`dump_d1_bias_block` requires inverted boundary** | Reading | BUY uses `d1_open >= d1_close` (no bear day); SELL uses `d1_open <= d1_close` (no bull day) | Intentional — bias gate filters direction-against-daily. |
| **Boolean Composite layer absent in code** | Spec-doc gap | Composites only exist as spec in atlas §5; filter chains are the de-facto implementation | Phase 2 (v2.7.37+ per Decision Stack §9): introduce explicit `composite_*` boolean precomputes if it improves debuggability. Currently the chain IS the implementation per design. |

---

## §9. Inventory totals

| Layer | Count |
|---|---|
| **Setup Triggers** | 5 setup types, 8 direction combinations |
| **Filter Chain rungs (gate codes)** | 58 distinct codes (11 pre-trigger + ~25 per-setup + 6 post-direction + 8 execution-failure + 8 open-group) |
| **Boolean Composites** | 8 (one per setup×direction) |
| **Atoms** | ~45 unique predicates (M5/M15/M30/H1/H4/D1 indicator inequalities + state checks) |
| **Entry Geometry rules** | 8 (one per setup×direction, plus news-override + lot-factor pipeline) |

---

## §10. Cross-references

- **Decision Stack spec**: `FORGE_DECISION_STACK.md` §1-§7
- **Indicator inventory**: `docs/FORGE_INDICATOR_ATLAS.md` §1
- **Boolean Composite registry**: `docs/FORGE_INDICATOR_ATLAS.md` §5
- **Gate dictionary**: `config/gate_legend.json`
- **Entry geometry quick-ref**: `FORGE_SETUP_PLAYBOOK.md` §5
- **Lot sizing reference** (NEW): `docs/FORGE_LOT_SIZING_REFERENCE.md` — full lot pipeline per setup × direction (17 rows), compound penalty scenarios, growth multipliers
- **Logging Extension v2.7.37 plan**: `docs/FORGE_LOGGING_EXTENSION_DESIGN.md`
- **EA source**: `ea/FORGE.mq5` (8460 lines @ v2.7.36)

---

## §11. Changelog

| Date | Change |
|---|---|
| 2026-05-12 | Initial extraction. v2.7.36 baseline. Captures Tier-0 alias fix (NEW_YORK→NY) and full session/killzone refactor in pre-trigger chain (`session_off` now uses `ComputeCurrentSessionLabel`). |
