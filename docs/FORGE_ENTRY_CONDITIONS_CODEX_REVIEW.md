# FORGE Entry Conditions — Codex Validation Review

**Date**: 2026-05-11
**EA version**: FORGE v2.7.27 (from scalper_config.json)
**Reviewer**: Codex (automated, read-only)
**Methodology**: Every claim cited with file:line. UNVERIFIED = code not found. Active config = scalper_config.json (not defaults).

## Validation Summary
- Gates checked: 47 rows covering 53 literal/dynamic SKIP families
- PASS: 58  |  WARNING: 12  |  FAIL: 0  |  UNVERIFIED: 0
- Mandatory Check A (dead env vars): PASS
- Mandatory Check B (gate legend completeness): PASS
- v2.7.27 Filter 1 wiring: PASS with WARNING (active config disabled; shared one-log-per-bar throttle)
- v2.7.27 Filter 3 cancel-pending: PASS with WARNING (active config disabled; cascade opt-out branch unreachable for +20000 magics under current magic range)
- v2.7.27 TP4/TP5 staging: PASS with WARNING (`tp4_atr_mult` is present in JSON but not parsed/mapped)

## Mandatory Check A — Dead FORGE_* env vars
| .env key | sync mapping found? | Whitelisted? | Status |
|---|---:|---:|---|
| `FORGE_ADX_HYSTERESIS_APPLY_IN_TESTER` | Yes | No | PASS |
| `FORGE_ADX_HYSTERESIS_ENABLED` | Yes | No | PASS |
| `FORGE_ADX_TREND_ENTER` | Yes | No | PASS |
| `FORGE_ADX_TREND_EXIT` | Yes | No | PASS |
| `FORGE_BOUNCE_ADX_MAX` | Yes | No | PASS |
| `FORGE_BOUNCE_LOT_FACTOR` | Yes | No | PASS |
| `FORGE_BOUNCE_MIN_TP1_ATR_MULT` | Yes | No | PASS |
| `FORGE_BOUNCE_MIN_TP2_ATR_MULT` | Yes | No | PASS |
| `FORGE_BOUNCE_RECLAIM_PCT` | Yes | No | PASS |
| `FORGE_BOUNCE_REQUIRE_REJECTION_CANDLE` | Yes | No | PASS |
| `FORGE_BREAKOUT_ADX_LOT_FACTOR_HIGH` | Yes | No | PASS |
| `FORGE_BREAKOUT_ADX_LOT_FACTOR_MID` | Yes | No | PASS |
| `FORGE_BREAKOUT_ADX_LOT_HIGH_THRESHOLD` | Yes | No | PASS |
| `FORGE_BREAKOUT_ADX_LOT_MID_THRESHOLD` | Yes | No | PASS |
| `FORGE_BREAKOUT_ADX_LOT_USE_M15` | Yes | No | PASS |
| `FORGE_BREAKOUT_ADX_MIN` | Yes | No | PASS |
| `FORGE_BREAKOUT_ADX_MIN_SELL` | Yes | No | PASS |
| `FORGE_BREAKOUT_ADX_MIN_SELL_LOOKBACK_BARS` | Yes | No | PASS |
| `FORGE_BREAKOUT_ADX_SELL_BLOCK_THRESHOLD` | Yes | No | PASS |
| `FORGE_BREAKOUT_ATR_TRAIL_ENABLED` | Yes | No | PASS |
| `FORGE_BREAKOUT_ATR_TRAIL_MULT` | Yes | No | PASS |
| `FORGE_BREAKOUT_BE_CUSHION_ATR_MULT` | Yes | No | PASS |
| `FORGE_BREAKOUT_BLOCK_HID_BULL_SELL` | Yes | No | PASS |
| `FORGE_BREAKOUT_BUY_SL_ATR_MULT` | Yes | No | PASS |
| `FORGE_BREAKOUT_COUNTER_BUY_ADX_THRESHOLD` | Yes | No | PASS |
| `FORGE_BREAKOUT_FAILED_GATE_ENABLED` | Yes | No | PASS |
| `FORGE_BREAKOUT_FAILED_LOOKBACK_BARS` | Yes | No | PASS |
| `FORGE_BREAKOUT_FAILED_MIN_PEAK_RSI` | Yes | No | PASS |
| `FORGE_BREAKOUT_FAILED_MIN_RSI_DROP` | Yes | No | PASS |
| `FORGE_BREAKOUT_FAILED_SAME_BAR_HARD_BLOCK` | Yes | No | PASS |
| `FORGE_BREAKOUT_H1H4_CRASH_SELL` | Yes | No | PASS |
| `FORGE_BREAKOUT_H1H4_CRASH_SELL_ADX_MAX` | Yes | No | PASS |
| `FORGE_BREAKOUT_H1H4_CRASH_SELL_MIN_M15_ADX` | Yes | No | PASS |
| `FORGE_BREAKOUT_H1H4_CRASH_SELL_RSI_MIN` | Yes | No | PASS |
| `FORGE_BREAKOUT_M30_BEAR_ADX_MIN` | Yes | No | PASS |
| `FORGE_BREAKOUT_MACD_FAST` | Yes | No | PASS |
| `FORGE_BREAKOUT_MACD_SIGNAL` | Yes | No | PASS |
| `FORGE_BREAKOUT_MACD_SLOW` | Yes | No | PASS |
| `FORGE_BREAKOUT_MAX_REENTRY_ATR_EXT` | Yes | No | PASS |
| `FORGE_BREAKOUT_MIN_H1_BEAR_STRENGTH` | Yes | No | PASS |
| `FORGE_BREAKOUT_REQUIRE_H1_DI_BUY` | Yes | No | PASS |
| `FORGE_BREAKOUT_REQUIRE_H1_DI_SELL` | Yes | No | PASS |
| `FORGE_BREAKOUT_REQUIRE_H1_MACD_BUY` | Yes | No | PASS |
| `FORGE_BREAKOUT_REQUIRE_H1_MACD_SELL` | Yes | No | PASS |
| `FORGE_BREAKOUT_REQUIRE_M30_BEAR_SELL` | Yes | No | PASS |
| `FORGE_BREAKOUT_REQUIRE_MACD_BUY` | Yes | No | PASS |
| `FORGE_BREAKOUT_REQUIRE_MACD_SELL` | Yes | No | PASS |
| `FORGE_BREAKOUT_REQUIRE_PSAR_ALIGN` | Yes | No | PASS |
| `FORGE_BREAKOUT_REQUIRE_RSI_DECLINING_SELL` | Yes | No | PASS |
| `FORGE_BREAKOUT_RSI_BUY_CEIL` | Yes | No | PASS |
| `FORGE_BREAKOUT_RSI_DECL_SELL_ADX_THRESHOLD` | Yes | No | PASS |
| `FORGE_BREAKOUT_RSI_SELL_FLOOR` | Yes | No | PASS |
| `FORGE_BREAKOUT_SAME_DIR_COOLDOWN_SECONDS` | Yes | No | PASS |
| `FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR` | Yes | No | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_ATR_MULT` | Yes | No | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_ENABLED` | Yes | No | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_EXPIRY_BARS` | Yes | No | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_L2_ATR_MULT` | Yes | No | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_L2_ENABLED` | Yes | No | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_L2_LOT_FACTOR` | Yes | No | PASS |
| `FORGE_BREAKOUT_SELL_LIMIT_LOT_FACTOR` | Yes | No | PASS |
| `FORGE_BREAKOUT_TP1_ATR_MULT` | Yes | No | PASS |
| `FORGE_BREAKOUT_TP1_BUY_ATR_MULT` | Yes | No | PASS |
| `FORGE_BREAKOUT_TP1_CLOSE_PCT` | Yes | No | PASS |
| `FORGE_BREAKOUT_TP1_SELL_ATR_MULT` | Yes | No | PASS |
| `FORGE_BREAKOUT_TP2_SL_RATCHET_ENABLED` | Yes | No | PASS |
| `FORGE_BUY_LIMIT_RECOVERY_ENABLED` | Yes | No | PASS |
| `FORGE_BUY_LIMIT_RECOVERY_EXPIRY_BARS` | Yes | No | PASS |
| `FORGE_BUY_LIMIT_RECOVERY_LOT_FACTOR` | Yes | No | PASS |
| `FORGE_BUY_LIMIT_RECOVERY_MIN_RSI` | Yes | No | PASS |
| `FORGE_BUY_LIMIT_RECOVERY_SL_ATR_MULT` | Yes | No | PASS |
| `FORGE_FAST_LOCK_MIN_HOLD_SEC_BOUNCE` | Yes | No | PASS |
| `FORGE_FAST_LOCK_MIN_HOLD_SEC_BREAKOUT` | Yes | No | PASS |
| `FORGE_FAST_LOCK_MIN_PROFIT_POINTS` | Yes | No | PASS |
| `FORGE_FIXED_LOT` | Yes | No | PASS |
| `FORGE_GOLD_NATIVE_MAX_SELL_LEGS` | Yes | No | PASS |
| `FORGE_H4_ADX_GATE_ENABLED` | Yes | No | PASS |
| `FORGE_H4_ADX_MIN_BUY` | Yes | No | PASS |
| `FORGE_H4_ADX_MIN_SELL` | Yes | No | PASS |
| `FORGE_H4_RSI_BUY_MIN` | Yes | No | PASS |
| `FORGE_H4_RSI_GATE_ENABLED` | Yes | No | PASS |
| `FORGE_H4_RSI_SELL_MAX` | Yes | No | PASS |
| `FORGE_INPUTS_OVERRIDE_LOT_SIZING` | Yes | No | PASS |
| `FORGE_LOT_SIZING_SOURCE` | Yes | No | PASS |
| `FORGE_MAX_NUM_TRADES` | Yes | No | PASS |
| `FORGE_MIN_BODY_RATIO` | Yes | No | PASS |
| `FORGE_MIN_DIRECTIONAL_BARS` | Yes | No | PASS |
| `FORGE_MIN_ENTRY_ATR` | Yes | No | PASS |
| `FORGE_MIN_NUM_TRADES` | Yes | No | PASS |
| `FORGE_NATIVE_LEGS_MAX_WHEN_UNCLEAR` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_APPLY_IN_TESTER` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_BLOCK_PCT` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_CURRENCIES` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_ENABLED` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_HARD_FLOOR_MIN` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_HIGH_AFTER` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_HIGH_BEFORE` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_LOW_AFTER` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_LOW_BEFORE` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_MEDIUM_AFTER` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_MEDIUM_BEFORE` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_REFRESH_SEC` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_SPECIAL` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_TIGHTEN_PCT` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_TIGHTEN_RSI_BUY` | Yes | No | PASS |
| `FORGE_NEWS_FILTER_TIGHTEN_RSI_SELL` | Yes | No | PASS |
| `FORGE_REQUIRE_BB_EXPANSION` | Yes | No | PASS |
| `FORGE_SCALPER_MODE` | No | Yes | PASS |
| `FORGE_SELL_STOP_CONT_ATR_MULT` | Yes | No | PASS |
| `FORGE_SELL_STOP_CONT_ENABLED` | Yes | No | PASS |
| `FORGE_SELL_STOP_CONT_EXPIRY_BARS` | Yes | No | PASS |
| `FORGE_SELL_STOP_CONT_LEGS` | Yes | No | PASS |
| `FORGE_SELL_STOP_CONT_LOT_FACTOR` | Yes | No | PASS |
| `FORGE_SELL_STOP_CONT_MIN_ADX` | Yes | No | PASS |
| `FORGE_SELL_STOP_CONT_MIN_RSI` | Yes | No | PASS |
| `FORGE_SELL_STOP_CONT_REQUIRE_H1_DI` | Yes | No | PASS |
| `FORGE_SELL_STOP_CONT_REQUIRE_TREND_REGIME` | Yes | No | PASS |
| `FORGE_SELL_STOP_CONT_SL_ATR_MULT` | Yes | No | PASS |
| `FORGE_SELL_STOP_CONT_TP_ATR_MULT` | Yes | No | PASS |
| `FORGE_SESSION_LONDON_SELL_CUTOFF_UTC` | Yes | No | PASS |
| `FORGE_SESSION_NY_SELL_CUTOFF_UTC` | Yes | No | PASS |
| `FORGE_STAGED_ADD_MIN_FAVORABLE_POINTS` | Yes | No | PASS |
| `FORGE_STAGED_INITIAL_LEGS` | Yes | No | PASS |

[Lowercase leaks table]
| .env key | .env file:line | Status |
|---|---|---|
| None found | `.env:1-437` checked; lowercase FORGE-looking active assignments absent | PASS |

## Mandatory Check B — Gate legend completeness
| EA gate code | EA file:line | In gate_legend.json? | Wildcard match? | Status |
|---|---|---:|---:|---|
| `cooldown` | ea/FORGE.mq5:5416 | Yes | No | PASS |
| `direction_cooldown` | ea/FORGE.mq5:6406 | Yes | No | PASS |
| `entry_quality_adx_extreme_sell` | ea/FORGE.mq5:6125 | Yes | No | PASS |
| `entry_quality_adx_min_sell` | ea/FORGE.mq5:6132 | Yes | No | PASS |
| `entry_quality_adx_spike_sell` | ea/FORGE.mq5:6207 | Yes | No | PASS |
| `entry_quality_atr` | ea/FORGE.mq5:5272 | Yes | No | PASS |
| `entry_quality_atr_ext` | ea/FORGE.mq5:6470 | Yes | No | PASS |
| `entry_quality_bb_contraction` | ea/FORGE.mq5:5330 | Yes | No | PASS |
| `entry_quality_body` | ea/FORGE.mq5:5303 | Yes | No | PASS |
| `entry_quality_breakout_cooldown` | ea/FORGE.mq5:5975,6344 | Yes | No | PASS |
| `entry_quality_breakout_failed` | ea/FORGE.mq5:6019 | Yes | No | PASS |
| `entry_quality_breakout_failed_samebar` | ea/FORGE.mq5:5999 | Yes | No | PASS |
| `entry_quality_daily_bear_block_buy` | ea/FORGE.mq5:5746,5876 | Yes | No | PASS |
| `entry_quality_daily_bull_block_sell` | ea/FORGE.mq5:5796,6099 | Yes | No | PASS |
| `entry_quality_direction` | ea/FORGE.mq5:5315 | Yes | No | PASS |
| `entry_quality_direction_cap` | ea/FORGE.mq5:5264 | Yes | No | PASS |
| `entry_quality_h1_di_buy` | ea/FORGE.mq5:5896 | Yes | No | PASS |
| `entry_quality_h1_di_sell` | ea/FORGE.mq5:6153 | Yes | No | PASS |
| `entry_quality_h1_macd_buy` | ea/FORGE.mq5:5957 | Yes | No | PASS |
| `entry_quality_h1_macd_sell` | ea/FORGE.mq5:6282 | Yes | No | PASS |
| `entry_quality_h4_adx_buy_blocked` | ea/FORGE.mq5:5939 | Yes | No | PASS |
| `entry_quality_h4_adx_sell_blocked` | ea/FORGE.mq5:6330 | Yes | No | PASS |
| `entry_quality_h4_rsi_buy_blocked` | ea/FORGE.mq5:5930 | Yes | No | PASS |
| `entry_quality_h4_rsi_sell_blocked` | ea/FORGE.mq5:6318 | Yes | No | PASS |
| `entry_quality_hid_bull_div_sell` | ea/FORGE.mq5:6241 | Yes | No | PASS |
| `entry_quality_m30_not_bearish` | ea/FORGE.mq5:6304 | Yes | No | PASS |
| `entry_quality_macd_q* dynamic` | ea/FORGE.mq5:5917,6262 | Yes | No | PASS |
| `entry_quality_news_filter` | ea/FORGE.mq5:5252 | Yes | No | PASS |
| `entry_quality_news_rsi_tighten` | ea/FORGE.mq5:5655,5661,6046,6368 | Yes | No | PASS |
| `entry_quality_psar_misalign_buy` | ea/FORGE.mq5:5758,6036 | Yes | No | PASS |
| `entry_quality_psar_misalign_sell` | ea/FORGE.mq5:5805,6357 | Yes | No | PASS |
| `entry_quality_rsi_buy_ceil` | ea/FORGE.mq5:5885 | Yes | No | PASS |
| `entry_quality_rsi_sell_floor / entry_quality_rsi_sell_adx_floor dynamic` | ea/FORGE.mq5:6191 | Yes | No | PASS |
| `entry_quality_rsi_rising_sell` | ea/FORGE.mq5:6225 | Yes | No | PASS |
| `entry_quality_session_sell_cutoff` | ea/FORGE.mq5:6112 | Yes | No | PASS |
| `execution_failed` | ea/FORGE.mq5:6756 | Yes | No | PASS |
| `m1` | ea/FORGE.mq5:6417 | Yes | No | PASS |
| `no_setup` | ea/FORGE.mq5:6451 | Yes | No | PASS |
| `open_group_* dynamic` | ea/FORGE.mq5:7445-7612 | Partial | Yes | PASS |
| `open_groups` | ea/FORGE.mq5:5401 | Yes | No | PASS |
| `post_sl_cooldown` | ea/FORGE.mq5:6410 | Yes | No | PASS |
| `regime_countertrend` | ea/FORGE.mq5:6425 | Yes | No | PASS |
| `rr_too_low` | ea/FORGE.mq5:6540 | Yes | No | PASS |
| `session_off` | ea/FORGE.mq5:5369 | Yes | No | PASS |
| `session_trade_cap` | ea/FORGE.mq5:5407 | Yes | No | PASS |
| `spread` | ea/FORGE.mq5:5396 | Yes | No | PASS |
| `warmup_* dynamic` | ea/FORGE.mq5:5430 | Partial | Yes | PASS |

## v2.7.27-specific checks
### Filter 1 wiring
| Check | Evidence | Status |
|---|---|---|
| `ComputeDailyBias()` exists and uses D1 SMA close | `iMA(_Symbol, PERIOD_D1, sma_period, 0, MODE_SMA, PRICE_CLOSE)` at `ea/FORGE.mq5:4061` | PASS |
| D1 SMA handle released | `IndicatorRelease(ma_handle)` at `ea/FORGE.mq5:4064` | PASS |
| Uses D1 ATR(14) | `iATR(_Symbol, PERIOD_D1, 14)` at `ea/FORGE.mq5:4073` | PASS |
| D1 ATR handle released | `IndicatorRelease(atr_handle)` at `ea/FORGE.mq5:4076` | PASS |
| Called once per tick from native setup path when enabled | `CheckNativeScalperSetups()` calls `ComputeDailyBias()` and `CancelPendingOnDailyFlip()` behind `g_sc.daily_direction_gate_enabled` at `ea/FORGE.mq5:5341-5348` | PASS |
| Per-M5-bar cache key | `iTime(_Symbol, PERIOD_M5, 0)` and `g_daily_bias_cache_bar` at `ea/FORGE.mq5:4048-4051` | PASS |
| Slope threshold and bull/bear flags | `slope_thresh = daily_slope_block_atr * g_daily_atr_pts`; bear `< -threshold`, bull `> threshold` at `ea/FORGE.mq5:4080-4083` | PASS |
| Hysteresis only on opposite-bias transition | `was_bull ? hyst : 0.0` and `was_bear ? hyst : 0.0` at `ea/FORGE.mq5:4091-4099` | PASS |
| BUY block inserted in BB_BOUNCE and BB_BREAKOUT | BB_BOUNCE BUY at `ea/FORGE.mq5:5741-5747`; BB_BREAKOUT BUY at `ea/FORGE.mq5:5872-5877` | PASS |
| SELL block inserted in BB_BOUNCE and BB_BREAKOUT | BB_BOUNCE SELL at `ea/FORGE.mq5:5791-5797`; BB_BREAKOUT SELL at `ea/FORGE.mq5:6095-6100` | PASS |
| Shared throttle | All four sites write `g_scalper_last_dailybias_log_bar` at `ea/FORGE.mq5:5743-5746`, `5793-5796`, `5873-5876`, `6096-6099` | WARNING: at most one daily-bias SKIP row per M5 bar across both setup types and directions, so diagnostics can undercount simultaneous blocked candidates |
| Active runtime config | `daily_direction_gate_enabled=0` at `config/scalper_config.json:233` | WARNING: shipped code is wired but inactive in active config |

### Filter 3 cancel-pending
| Check | Evidence | Status |
|---|---|---|
| Function exists | `CancelPendingOnDailyFlip()` starts at `ea/FORGE.mq5:2016` | PASS |
| Called after daily bias compute | `ComputeDailyBias(); CancelPendingOnDailyFlip();` at `ea/FORGE.mq5:5345-5347` | PASS |
| Guarded by feature/cancel/flip flags | `daily_direction_gate_enabled`, `daily_cancel_pending_on_flip`, `g_daily_flip_now` guards at `ea/FORGE.mq5:2017-2019` | PASS |
| Iterate-down order loop | `for(int i = OrdersTotal() - 1; i >= 0; i--)` at `ea/FORGE.mq5:2022` | PASS |
| Magic range check | `om < MagicNumber || om >= MagicNumber + 10000` at `ea/FORGE.mq5:2026-2027` | PASS |
| Pending type filter complete | BUY/SELL LIMIT, STOP, STOP_LIMIT covered at `ea/FORGE.mq5:2034-2040` | PASS |
| Cascade include toggle | `if(!daily_cancel_includes_cascade)` then `slot_offset >= 20000` skip at `ea/FORGE.mq5:2030-2032` | WARNING: the preceding `< MagicNumber+10000` check at `ea/FORGE.mq5:2027` excludes magics offset by `+20000`, so cascade pending orders cannot reach this toggle unless the magic-range policy changes |
| Active runtime config | `daily_cancel_pending_on_flip=1`, `daily_cancel_includes_cascade=1` at `config/scalper_config.json:239-240`, but master gate is `0` at `config/scalper_config.json:233` | WARNING |

### TP4/TP5 staging
| Check | Evidence | Status |
|---|---|---|
| `TradeGroup` has `tp4`, `tp5`, `tp3_hit`, `tp4_hit` | `ea/FORGE.mq5:621-631` | PASS |
| BRIDGE init zeroes new fields | `tp4=0`, `tp5=0`, `tp4_hit=false` at `ea/FORGE.mq5:1249-1255`; `tp3_hit=false` is in same init block immediately above existing group flags | PASS |
| Native scalper init zeroes flags and computes levels | TP3/TP4/TP5 at `ea/FORGE.mq5:6773-6792`; flags false at `ea/FORGE.mq5:6794-6797` | PASS |
| RebuildGroups zeroes new fields | `tp4=0`, `tp5=0`, `tp3_hit=false`, `tp4_hit=false` at `ea/FORGE.mq5:7072-7079` | PASS |
| TP4 computed at entry when enabled | `breakout_tp4_staging_enabled && breakout_tp4_atr_mult > 0.0` at `ea/FORGE.mq5:6780-6787`; active config `tp4_staging_enabled=0`, `tp4_atr_mult=4.0` at `config/scalper_config.json:45,55` | PASS |
| TP5 computed at entry when enabled | `breakout_tp5_staging_enabled && breakout_tp5_atr_mult > 0.0` at `ea/FORGE.mq5:6788-6791`; active config `tp5_staging_enabled=0`, `tp5_atr_mult=5.5` at `config/scalper_config.json:46,49` | PASS |
| TP3 to TP4 gates | Regime in `TREND_BULL/TREND_BEAR/VOLATILE` and M5 ADX >= `breakout_tp4_min_adx` at `ea/FORGE.mq5:1752-1763`; active min ADX 25 at `config/scalper_config.json:47` | PASS |
| TP4 to TP5 gates | Same regime set and M5 ADX >= `breakout_tp5_min_adx` at `ea/FORGE.mq5:1801-1812`; active min ADX 30 at `config/scalper_config.json:48` | PASS |
| SL invariant direction-aware | TP3->TP4 BUY raises / SELL lowers SL to TP2 at `ea/FORGE.mq5:1780-1783`; TP4->TP5 BUY raises / SELL lowers SL to TP3 at `ea/FORGE.mq5:1827-1831` | PASS |
| Promotion flags set | `tp3_hit=true` at `ea/FORGE.mq5:1789`; `tp4_hit=true` at `ea/FORGE.mq5:1837` | PASS |
| TP4 multiplier config parse | `tp4_atr_mult` exists in JSON at `config/scalper_config.json:55` and struct/default at `ea/FORGE.mq5:271,2618`, but no `JsonHasKey(..."tp4_atr_mult")` or `FORGE_BREAKOUT_TP4_ATR_MULT` mapping was found (`rg` found only `.env.example:385`) | WARNING |

### 13 new env vars wiring
| FORGE_ Variable | Struct field | Struct field cite | Default set | JSON parse | .env.example | sync.py | defaults.json | Status |
|---|---|---|---|---|---|---|---|---|
| `FORGE_DAILY_DIRECTION_GATE_ENABLED` | `daily_direction_gate_enabled` | ea/FORGE.mq5:284 | ea/FORGE.mq5:2628 | ea/FORGE.mq5:3193 | .env.example:367-383 | scripts/sync_scalper_config_from_env.py:212 | config/scalper_config.defaults.json:229 / config/scalper_config.json:233 | PASS |
| `FORGE_DAILY_SMA_PERIOD` | `daily_sma_period` | ea/FORGE.mq5:285 | ea/FORGE.mq5:2629 | ea/FORGE.mq5:3194 | .env.example:367-383 | scripts/sync_scalper_config_from_env.py:213 | defaults:230 / active:234 | PASS |
| `FORGE_DAILY_SMA_LOOKBACK_DAYS` | `daily_sma_lookback_days` | ea/FORGE.mq5:286 | ea/FORGE.mq5:2630 | ea/FORGE.mq5:3195 | .env.example:367-383 | scripts/sync_scalper_config_from_env.py:214 | defaults:231 / active:235 | PASS |
| `FORGE_DAILY_SLOPE_BLOCK_ATR` | `daily_slope_block_atr` | ea/FORGE.mq5:287 | ea/FORGE.mq5:2631 | ea/FORGE.mq5:3196 | .env.example:367-383 | scripts/sync_scalper_config_from_env.py:215 | defaults:232 / active:236 | PASS |
| `FORGE_DAILY_MOVE_BLOCK_ATR` | `daily_move_block_atr` | ea/FORGE.mq5:288 | ea/FORGE.mq5:2632 | ea/FORGE.mq5:3197 | .env.example:367-383 | scripts/sync_scalper_config_from_env.py:216 | defaults:233 / active:237 | PASS |
| `FORGE_DAILY_MOVE_FLIP_HYSTERESIS` | `daily_move_flip_hysteresis` | ea/FORGE.mq5:289 | ea/FORGE.mq5:2633 | ea/FORGE.mq5:3198 | .env.example:367-383 | scripts/sync_scalper_config_from_env.py:217 | defaults:234 / active:238 | PASS |
| `FORGE_DAILY_CANCEL_PENDING_ON_FLIP` | `daily_cancel_pending_on_flip` | ea/FORGE.mq5:290 | ea/FORGE.mq5:2634 | ea/FORGE.mq5:3199 | .env.example:367-383 | scripts/sync_scalper_config_from_env.py:218 | defaults:235 / active:239 | PASS |
| `FORGE_DAILY_CANCEL_INCLUDES_CASCADE` | `daily_cancel_includes_cascade` | ea/FORGE.mq5:291 | ea/FORGE.mq5:2635 | ea/FORGE.mq5:3200 | .env.example:367-383 | scripts/sync_scalper_config_from_env.py:219 | defaults:236 / active:240 | PASS |
| `FORGE_BREAKOUT_TP4_STAGING_ENABLED` | `breakout_tp4_staging_enabled` | ea/FORGE.mq5:296 | ea/FORGE.mq5:2637 | ea/FORGE.mq5:3001-3003 | .env.example:384-392 | scripts/sync_scalper_config_from_env.py:206 | defaults:45 / active:45 | PASS |
| `FORGE_BREAKOUT_TP4_MIN_ADX` | `breakout_tp4_min_adx` | ea/FORGE.mq5:298 | ea/FORGE.mq5:2639 | ea/FORGE.mq5:3009-3011 | .env.example:384-392 | scripts/sync_scalper_config_from_env.py:207 | defaults:47 / active:47 | PASS |
| `FORGE_BREAKOUT_TP5_STAGING_ENABLED` | `breakout_tp5_staging_enabled` | ea/FORGE.mq5:299 | ea/FORGE.mq5:2640 | ea/FORGE.mq5:3013-3015 | .env.example:384-392 | scripts/sync_scalper_config_from_env.py:208 | defaults:46 / active:46 | PASS |
| `FORGE_BREAKOUT_TP5_MIN_ADX` | `breakout_tp5_min_adx` | ea/FORGE.mq5:300 | ea/FORGE.mq5:2641 | ea/FORGE.mq5:3017-3019 | .env.example:384-392 | scripts/sync_scalper_config_from_env.py:209 | defaults:48 / active:48 | PASS |
| `FORGE_BREAKOUT_TP5_ATR_MULT` | `breakout_tp5_atr_mult` | ea/FORGE.mq5:297 | ea/FORGE.mq5:2638 | ea/FORGE.mq5:3005-3007 | .env.example:384-392 | scripts/sync_scalper_config_from_env.py:210 | defaults:49 / active:49 | PASS |

### New gate legend entries
| Gate | gate_legend.json evidence | Category | Status |
|---|---|---|---|
| `entry_quality_daily_bear_block_buy` | `config/gate_legend.json:284-288` | Regime | PASS |
| `entry_quality_daily_bull_block_sell` | `config/gate_legend.json:289-293` | Regime | PASS |

## Section 1 — BB_BREAKOUT BUY Gates
| Gate / parameter | EA evidence | Active config | Env mapping/doc | Status |
|---|---|---|---|---|
| BB close above upper band | `prev_close > (m5_bb_u + breakout_buffer)` at `ea/FORGE.mq5:5865-5868` | BB period/deviation `20/2.0` at `config/scalper_config.json:128-129` | Core indicator config, no FORGE_ override found | PASS |
| RSI floor | `m5_rsi > g_sc.breakout_rsi_buy_min` at `ea/FORGE.mq5:5867`; default `40` at `ea/FORGE.mq5:2583` | `rsi_buy_min=40` at `config/scalper_config.json:36` | No active FORGE_ mapping for `rsi_buy_min` found | WARNING |
| RSI ceiling | `m5_rsi >= breakout_rsi_buy_ceil` skip at `ea/FORGE.mq5:5879-5885` | `rsi_buy_ceil=78` at `config/scalper_config.json:63` | `FORGE_BREAKOUT_RSI_BUY_CEIL` mapped at `scripts/sync_scalper_config_from_env.py:85`, active `.env:269` | PASS |
| M5/M15/H1/H4 alignment | Entry predicate uses `m5_bull`, `m15_ok_buy`, `h1_ok_buy`, `h4_ok_buy` at `ea/FORGE.mq5:5867-5868` | `require_m15_agree=true` at `config/scalper_config.json:38` | Partially config-driven | PASS |
| H1 DI BUY gate | Skip `entry_quality_h1_di_buy` at `ea/FORGE.mq5:5889-5896` | `require_h1_di_buy=1`, threshold 28 at `config/scalper_config.json:72-73` | `FORGE_BREAKOUT_REQUIRE_H1_DI_BUY` and `FORGE_BREAKOUT_COUNTER_BUY_ADX_THRESHOLD` mapped at `scripts/sync_scalper_config_from_env.py:95,113`; `.env:198,232` | PASS |
| OsMA BUY gate | Dynamic `_qreason` skip at `ea/FORGE.mq5:5902-5917` | `require_macd_buy=1`, OsMA `3/10/16` at `config/scalper_config.json:89-92` | Mapped at `scripts/sync_scalper_config_from_env.py:123-127`; `.env:253-256` | PASS |
| H1 MACD BUY gate | Skip `entry_quality_h1_macd_buy` at `ea/FORGE.mq5:5944-5957` | `require_h1_macd_buy=0` at `config/scalper_config.json:76` | Mapped at `scripts/sync_scalper_config_from_env.py:101`; `.env:207` | PASS |
| Re-entry extension | `max_reentry_atr_ext` gate at `ea/FORGE.mq5:5975-6019` | `max_reentry_atr_ext=2` at `config/scalper_config.json:84` | Mapped at `scripts/sync_scalper_config_from_env.py:115`; `.env:183` | PASS |
| Daily bear block | `entry_quality_daily_bear_block_buy` at `ea/FORGE.mq5:5872-5877` | master disabled at `config/scalper_config.json:233` | New env mapping at `scripts/sync_scalper_config_from_env.py:212-219` | WARNING |

## Section 2 — BB_BREAKOUT SELL Gates
| Gate / parameter | EA evidence | Active config | Env mapping/doc | Status |
|---|---|---|---|---|
| BB close below lower band | SELL predicate is the mirror breakout block starting at `ea/FORGE.mq5:6090-6095` | BB `20/2.0` at `config/scalper_config.json:128-129` | Core indicator config | PASS |
| Session cutoff | Skip `entry_quality_session_sell_cutoff` at `ea/FORGE.mq5:6103-6112` | active cutoff disabled: `session_ny_sell_cutoff_utc=0`, `session_london_sell_cutoff_utc=0` at `config/scalper_config.json:224-225` | Mapped at `scripts/sync_scalper_config_from_env.py:190-191`; `.env:240-241` | PASS |
| ADX min and extreme | Skips at `ea/FORGE.mq5:6125-6132` | `adx_min_sell=25`, block 55 at `config/scalper_config.json:70,125` | Mapped at `scripts/sync_scalper_config_from_env.py:91,139`; `.env:187,267` | PASS |
| H1 DI SELL | Skip at `ea/FORGE.mq5:6153` | `require_h1_di_sell=1` at `config/scalper_config.json:74` | Mapped at `scripts/sync_scalper_config_from_env.py:97`; `.env:200` | PASS |
| Crash bypass | Requires H1/H4 bear, RSI floor, ADX cap, M15 ADX at `ea/FORGE.mq5:6160-6168` | `h1h4_crash_sell=1`, RSI 20, ADX max 40, M15 ADX 25 at `config/scalper_config.json:65-69` | Mapped at `scripts/sync_scalper_config_from_env.py:87-88,141-143`; `.env:351-359` | PASS |
| RSI sell floor dynamic gate | `floor_gate` skip at `ea/FORGE.mq5:6191` | `rsi_sell_floor=33`, weak/rising threshold 40 at `config/scalper_config.json:64,67` | Mapped at `scripts/sync_scalper_config_from_env.py:86,120`; `.env:194,246` | PASS |
| ADX duration spike | Skip at `ea/FORGE.mq5:6207` | lookback 6 at `config/scalper_config.json:71` | Mapped at `scripts/sync_scalper_config_from_env.py:93`; `.env:196` | PASS |
| RSI rising and HID_BULL | Skips at `ea/FORGE.mq5:6225,6241` | `require_rsi_declining_sell=1`, `block_hid_bull_sell=1` at `config/scalper_config.json:122-123` | Mapped at `scripts/sync_scalper_config_from_env.py:118-119`; `.env:189,192` | PASS |
| OsMA SELL and H1 MACD | Dynamic OsMA skip at `ea/FORGE.mq5:6246-6262`; H1 MACD skip at `ea/FORGE.mq5:6269-6282` | OsMA required, H1 MACD disabled at `config/scalper_config.json:75,88,90-92` | Mapped at `scripts/sync_scalper_config_from_env.py:99,123-127`; `.env:202,251-256` | PASS |
| M30/H4/PSAR/cooldown | Skips at `ea/FORGE.mq5:6304,6318,6330,6344,6357` | active values at `config/scalper_config.json:77,83,86-87,111-116` | Mapped in sync at `scripts/sync_scalper_config_from_env.py:103,111,117,167-173` | PASS |
| Daily bull block | `entry_quality_daily_bull_block_sell` at `ea/FORGE.mq5:6095-6100` | master disabled at `config/scalper_config.json:233` | New env mapping at `scripts/sync_scalper_config_from_env.py:212-219` | WARNING |

## Section 3 — Full Lot Path
| Factor | EA evidence | Active config | Status |
|---|---|---|---|
| Base fixed lot | `lot_fixed` parsed from lot sizing and used in native open path at `ea/FORGE.mq5:6675` | `fixed_lot=0.25` at `config/scalper_config.json:259` | PASS |
| Inside-band SELL reduction | `inside_band_factor = breakout_sell_inside_band_lot_factor` at `ea/FORGE.mq5:6626-6627` | `0.25` at `config/scalper_config.json:124` | PASS |
| Near-floor crash reduction | `near_floor_factor` at `ea/FORGE.mq5:6637-6638` | `0.25` at `config/scalper_config.json:222` | PASS |
| Same-direction stack reduction | `stack_factor` at `ea/FORGE.mq5:6644-6646` | `0.25` at `config/scalper_config.json:223` | PASS |
| ADX lot factor | high threshold checked before mid at `ea/FORGE.mq5:6652-6664` | use M15=1, mid 35 factor 1, high 45 factor 0.5 at `config/scalper_config.json:226-230` | PASS |
| Bounce factor | `bounce_factor` at `ea/FORGE.mq5:6667-6668` | `bounce_lot_factor=0.25` at `config/scalper_config.json:8` | PASS |
| Combined factor floor | `MathMax(0.125, ...)` at `ea/FORGE.mq5:6672` | Code-defined floor | PASS |

## Section 4 — ADX-Conditional Leg Count
`ForgeResolveNumTrades()` is the resolver for native leg count at `ea/FORGE.mq5:7616-7620`. The native open path fixes the prior staged-initial n-1 bug by using `wave1 = MathMin(init_cap, n)` and `open_first = MathMax(1, MathMin(n, open_first))` at `ea/FORGE.mq5:6679-6693`. Active config sets `min_num_trades=2`, `max_num_trades=30`, `native_legs_max_when_unclear=5`, and `staged_initial_legs=10` at `config/scalper_config.json:260-267`; corresponding `.env` values are at `.env:169-177` and sync mappings at `scripts/sync_scalper_config_from_env.py:62-70`.

## Section 5 — TP3 Live Staging (extended to TP4/TP5 in v2.7.27)
The flag chain is present: TP2 reached promotes to TP3 and sets `tp2_hit=true` at `ea/FORGE.mq5:1695-1737`; TP3 reached promotes to TP4 and sets `tp3_hit=true` at `ea/FORGE.mq5:1752-1789`; TP4 reached promotes to TP5 and sets `tp4_hit=true` at `ea/FORGE.mq5:1801-1837`. SL ratchets are direction-aware at `ea/FORGE.mq5:1725-1729`, `1780-1783`, and `1827-1831`. Active TP4/TP5 staging is disabled by config at `config/scalper_config.json:45-46`.

## Section 6 — Direction-Split TP1
BUY TP1 uses `breakout_tp1_buy_atr_mult` when >0, otherwise `breakout_tp1_atr_mult`, at `ea/FORGE.mq5:6061-6063`; SELL mirrors this with `breakout_tp1_sell_atr_mult` at `ea/FORGE.mq5:6377-6379`. Active config sets fallback `tp1_atr_mult=0.4`, BUY `0.5`, SELL `0.4`, and `tp1_close_pct=60` at `config/scalper_config.json:50-56`; mappings are at `scripts/sync_scalper_config_from_env.py:220-223` and active `.env:154-159`.

## Section 7 — Crash-Sell Bypass
Crash bypass is implemented in the SELL breakout path: M15 ADX is read at `ea/FORGE.mq5:6164-6168`, and the crash floor/adx logic is the dynamic `floor_gate` block at `ea/FORGE.mq5:6191`. Active config requires `h1h4_crash_sell=1`, `h1h4_crash_sell_rsi_min=20`, `h1h4_crash_sell_adx_max=40`, and `h1h4_crash_sell_min_m15_adx=25` at `config/scalper_config.json:65-69`; `.env` documents those active overrides at `.env:351-359`.

## Section 8 — Variable Integrity
| Config key differing from defaults | Default | Active | Status |
|---|---:|---:|---|
| `bb_bounce.adx_max` | 50 | 30 | PASS |
| `bb_bounce.bounce_lot_factor` | 1.0 | 0.25 | PASS |
| `bb_breakout.adx_min` | 14 | 20 | PASS |
| `bb_breakout.atr_trail_enabled` | 0 | 1 | PASS |
| `bb_breakout.be_cushion_atr_mult` | 0.0 | 1.5 | PASS |
| `bb_breakout.buy_limit_recovery_enabled` | 0 | 1 | PASS |
| `bb_breakout.buy_sl_atr_mult` | 0.0 | 3 | PASS |
| `bb_breakout.failed_gate_enabled` | 0 | 1 | PASS |
| `bb_breakout.failed_min_peak_rsi` | 75.0 | 68 | PASS |
| `bb_breakout.failed_same_bar_hard_block` | 0 | 1 | PASS |
| `bb_breakout.max_reentry_atr_ext` | 0.0 | 2 | PASS |
| `bb_breakout.require_h1_di_buy` | 0 | 1 | PASS |
| `bb_breakout.require_h1_di_sell` | 0 | 1 | PASS |
| `bb_breakout.require_macd_buy` | 0 | 1 | PASS |
| `bb_breakout.require_psar_align` | 0 | 1 | PASS |
| `bb_breakout.rsi_buy_ceil` | 70 | 78 | PASS |
| `bb_breakout.rsi_sell_floor` | 30 | 33 | PASS |
| `bb_breakout.same_dir_cooldown_seconds` | 0 | 900 | PASS |
| `bb_breakout.sell_stop_cont_enabled` | 0 | 1 | PASS |
| `bb_breakout.sell_stop_cont_require_trend_regime` | 0 | 1 | PASS |
| `bb_breakout.sell_stop_cont_sl_atr_mult` | 1.5 | 3.5 | PASS |
| `bb_breakout.tp1_atr_mult` | 1.0 | 0.4 | PASS |
| `bb_breakout.tp1_buy_atr_mult` | 0.0 | 0.5 | PASS |
| `bb_breakout.tp1_close_pct` | 40 | 60 | PASS |
| `bb_breakout.tp1_sell_atr_mult` | 0.0 | 0.4 | PASS |
| `bb_breakout.tp2_sl_ratchet_enabled` | 0 | 1 | PASS |
| `lot_sizing.fixed_lot` | 0.02 | 0.25 | PASS |
| `lot_sizing.gold_native_max_sell_legs` | 2 | 10 | PASS |
| `lot_sizing.min_num_trades` | 1 | 2 | PASS |
| `lot_sizing.native_legs_max_when_unclear` | 3 | 5 | PASS |
| `lot_sizing.staged_add_min_favorable_points` | 35 | 5 | PASS |
| `lot_sizing.staged_initial_legs` | 1 | 10 | PASS |
| `safety.breakout_adx_lot_factor_high` | 0.125 | 0.5 | PASS |
| `safety.breakout_adx_lot_factor_mid` | 0.25 | 1 | PASS |
| `safety.fast_lock_min_hold_sec_breakout` | 50 | 25 | PASS |
| `safety.fast_lock_min_profit_points` | 12.0 | 5 | PASS |
| `safety.min_body_ratio` | 0.4 | 0.25 | PASS |
| `safety.min_directional_bars` | 2 | 1 | PASS |
| `safety.min_entry_atr` | 3.5 | 1 | PASS |
| `safety.require_bb_expansion` | 1 | 0 | PASS |
| `safety.session_ny_sell_cutoff_utc` | 17 | 0 | PASS |

Full FORGE_* sweep result: 123 active `.env` FORGE_* variables were enumerated. All 122 config-bound variables have sync mappings; `FORGE_SCALPER_MODE` is intentionally whitelisted in `tests/api/test_forge_27x_gates.py:260-262`. No lowercase active FORGE-looking keys were found. One adjacent warning remains: `.env.example:385` refers to `FORGE_BREAKOUT_TP4_ATR_MULT`, but sync.py has no such mapping and the EA does not parse `tp4_atr_mult` from JSON (`rg` evidence: `config/scalper_config.json:55`, `ea/FORGE.mq5:271,2618,6783-6786`, no parser hit).

## Section 9 — scribe.py / regime.py / schemas/ Cross-Check
| Area | Evidence | Status |
|---|---|---|
| `forge_signals` base schema | CREATE TABLE has core columns at `python/scribe.py:119-151`; migration-created table at `python/scribe.py:522-538` | PASS |
| `macd_histogram`, `m15_adx`, `lot_factor` migrations | ALTER migrations at `python/scribe.py:558-569`; source select/insert at `python/scribe.py:968-1030`; EA writes fields at `ea/FORGE.mq5:4464-4466,4648-4696,6993-6996` | PASS |
| `forge_journal_trades` run isolation columns | CREATE/upgrade includes `run_id`, `wall_time`, unique `(deal_ticket,journal_source,wall_time)` at `python/scribe.py:578-646`; `aurum_run_id` migration at `python/scribe.py:656-658` | PASS |
| Import run ID guard | Signals map wall_time to aurum_run_id at `python/scribe.py:1001-1013`; trades reuse/build map at `python/scribe.py:1078-1121` | PASS |
| Regime labels | `regime.py` emits `TREND_BULL`, `TREND_BEAR`, `VOLATILE`, `RANGE` at `python/regime.py:529-549`; TP4/TP5 gates accept `TREND_BULL/TREND_BEAR/VOLATILE` at `ea/FORGE.mq5:1752-1755,1801-1804` | PASS |
| Schemas coverage | File-bus schemas are JSON/OpenAPI only; manifest lists file schemas/openapi at `schemas/manifest.json:1-12`; no SQL DB schema definitions found under `schemas/` | WARNING: DB schema source of truth is `python/scribe.py`, not `schemas/` |
| Management TP stage schema | `tp_stage` enum only `[1,2,3]` at `schemas/files/management_cmd.schema.json:31-35` | WARNING: if manual management of TP4/TP5 stages is introduced, schema must expand |

## Section 10 — Dashboard / API Consistency
| Area | Evidence | Status |
|---|---|---|
| Backtest run isolation | `/api/backtest/run/<aurum_run_id>` loads metadata with `aurum_run_id=?` at `python/athena_api.py:1703-1708`; performance, signals, gates, taken, trades, curve all filter `aurum_run_id=?` at `python/athena_api.py:1711-1778,1928-1933` | PASS |
| TAKEN entries response fields | API emits `trade_outcome`, `pnl`, `cascade_pnl`, `legs`, `lot_per_leg` at `python/athena_api.py:1916-1926`; dashboard consumes these at `dashboard/app.js:1670-1721` | PASS |
| Legs math | API counts `|TP1` markers with SL/nonzero fallbacks at `python/athena_api.py:1895-1899` | PASS |
| lot_per_leg | API uses first non-zero volume at `python/athena_api.py:1901-1903`; dashboard renders `legs x lot` at `dashboard/app.js:1693-1697` | PASS |
| Cascade P&L | API attributes offsets `20000..20009` at `python/athena_api.py:1822-1835` and includes cascade pnl in group pnl at `python/athena_api.py:1880-1884`; dashboard tooltip shows cascade at `dashboard/app.js:1713-1721` | PASS |
| New gates in dashboard | Dashboard fetches `/api/gate_legend` at `dashboard/app.js:608-611`; API serves `config/gate_legend.json` at `python/athena_api.py:1971-1983`; new gate entries are at `config/gate_legend.json:284-293` | PASS |
| Stale API comment | Comment says cascade positions are excluded from journal by EA magic filter at `python/athena_api.py:1731-1732`, but later code explicitly handles cascade deals at `python/athena_api.py:1822-1884` | WARNING: comment is stale, behavior is correct |

## Section 11 — Scripts / Tests Consistency
| Area | Evidence | Status |
|---|---|---|
| Dead env var test | `FORGE_ENV_VARS_NOT_IN_SYNC` only whitelists `FORGE_SCALPER_MODE` at `tests/api/test_forge_27x_gates.py:257-262`; dead-var assertion at `tests/api/test_forge_27x_gates.py:265-280` | PASS |
| Gate legend test | Literal gate regex and wildcard prefix checks at `tests/api/test_forge_27x_gates.py:187-221` | PASS with limitation: regex misses dynamic `_qreason`, `floor_gate`, and concatenated `open_group_` sites, but manual review covers them |
| v2.7.27 tests | Current suite covers v2.7.13/14/15 and general wiring but has no explicit assertions for daily gate, cancel-on-flip, or TP4/TP5 staging (`tests/api/test_forge_27x_gates.py:129-180`) | WARNING |
| Pytest result | `pytest -q tests/api/test_forge_27x_gates.py` returned `28 passed in 0.08s` | PASS |

## Issues Found (Consolidated)
| # | Severity | Section | Description | Action |
|---:|---|---|---|---|
| 1 | Medium | Filter 3 | `CancelPendingOnDailyFlip()` checks `om < MagicNumber+10000` before the `slot_offset >= 20000` cascade toggle, so +20000 cascade magics cannot be cancelled by this function even when `daily_cancel_includes_cascade=1` (`ea/FORGE.mq5:2026-2032`). | Widen the magic range or compute cascade ownership before the `< MagicNumber+10000` filter. |
| 2 | Medium | TP4/TP5 | `tp4_atr_mult` exists in active/default JSON but is not parsed from JSON and has no `FORGE_BREAKOUT_TP4_ATR_MULT` sync mapping; `.env.example:385` references that env var name in prose. | Add JSON parser + sync mapping/doc or remove the config key/reference if TP4 is intentionally fixed at 4.0. |
| 3 | Low | Filter 1 | Daily bias SKIPs share one throttle variable, so only one of four insertion sites can log per M5 bar (`ea/FORGE.mq5:5743-5746,5793-5796,5873-5876,6096-6099`). | Use per-site/per-direction throttle vars if gate-frequency analytics need full counts. |
| 4 | Low | Runtime config | v2.7.27 daily gate and TP4/TP5 staging are shipped but disabled in active config (`config/scalper_config.json:45-46,233`). | Treat as inactive until backtest/run config explicitly enables them. |
| 5 | Low | Tests | Tests do not explicitly assert v2.7.27 daily/cancel/TP4/TP5 wiring, and the gate regex does not see dynamic gate strings (`tests/api/test_forge_27x_gates.py:187-221`). | Add focused v2.7.27 invariants and dynamic gate extraction checks. |
| 6 | Low | Dashboard/API | API comment about cascade journal exclusion is stale while behavior includes cascade deals (`python/athena_api.py:1731-1732` vs `1822-1884`). | Update the comment to avoid future regressions. |

## Overall Verdict
FORGE v2.7.27 is structurally wired for the shipped Daily Direction Gate and extended TP4/TP5 staging. The EA code computes D1 SMA slope/ATR with released handles, applies daily BUY/SELL blocks in both BB_BOUNCE and BB_BREAKOUT, cancels pending orders on daily flip, and stages runners TP3->TP4->TP5 with regime/ADX gates and direction-aware SL ratchets.

The main correctness caveat is Filter 3 cascade cancellation: under the current `MagicNumber+10000` range, +20000 cascade pending orders are excluded before the cascade include toggle can matter. The main config integrity caveat is `tp4_atr_mult`: it is present in JSON and used by code default, but not parsed or env-mapped. Active runtime config also leaves daily direction and TP4/TP5 staging disabled, so the v2.7.27 behavior is shipped but not active unless config is changed.

Confidence level: high for code-path validation and env/gate legend integrity; medium for runtime trading impact because the newest features are inactive in `scalper_config.json` and were not backtest-executed in this read-only review.
