# FORGE Entry Conditions — Codex Validation Review
**Date**: 2026-05-15
**EA version**: FORGE v2.7.123 (from scalper_config.json)
**Reviewer**: Codex (automated, read-only)
**Methodology**: every claim cited file:line. UNVERIFIED = code not found. Active config = scalper_config.json.

## Validation Summary
- Gates checked: 103 emitted gate codes + 23 BB_BREAKOUT intent gates
- PASS: 572  |  WARNING: 3  |  FAIL: 17  |  UNVERIFIED: 0
- Mandatory Check A: PASS
- Mandatory Check B: PASS
- Mandatory Check C: FAIL
- Mandatory Check D: PASS

## Mandatory Check A — Dead FORGE_* env vars
**Result**: PASS. Every active `FORGE_*` in `.env` is sync-mapped or whitelisted; no lowercase config-looking bypass keys were found.

| .env line | FORGE_ Variable | Sync target | In sync script | Whitelisted | Active config value | Status |
|---:|---|---|---|---|---|---|
| 133 | `FORGE_KILLZONES_ENABLED` | `session_filter.killzones_enabled` | yes | no | `1` | PASS |
| 185 | `FORGE_SCALPER_MODE` | `whitelist` | no | yes | `n/a` | PASS |
| 186 | `FORGE_FAST_LOCK_MIN_HOLD_SEC_BREAKOUT` | `safety.fast_lock_min_hold_sec_breakout` | yes | no | `25` | PASS |
| 187 | `FORGE_FAST_LOCK_MIN_PROFIT_POINTS` | `safety.fast_lock_min_profit_points` | yes | no | `5` | PASS |
| 188 | `FORGE_BOUNCE_MIN_TP1_ATR_MULT` | `bb_bounce.min_tp1_atr_mult` | yes | no | `0.4` | PASS |
| 189 | `FORGE_BOUNCE_MIN_TP2_ATR_MULT` | `bb_bounce.min_tp2_atr_mult` | yes | no | `0.8` | PASS |
| 191 | `FORGE_BREAKOUT_TP1_ATR_MULT` | `bb_breakout.tp1_atr_mult` | yes | no | `0.4` | PASS |
| 194 | `FORGE_BREAKOUT_TP1_BUY_ATR_MULT` | `bb_breakout.tp1_buy_atr_mult` | yes | no | `0.5` | PASS |
| 195 | `FORGE_BREAKOUT_TP1_SELL_ATR_MULT` | `bb_breakout.tp1_sell_atr_mult` | yes | no | `0.4` | PASS |
| 196 | `FORGE_BREAKOUT_TP1_CLOSE_PCT` | `bb_breakout.tp1_close_pct` | yes | no | `70` | PASS |
| 197 | `FORGE_FIXED_LOT` | `lot_sizing.fixed_lot` | yes | no | `0.25` | PASS |
| 204 | `FORGE_MIN_NUM_TRADES` | `lot_sizing.min_num_trades` | yes | no | `2` | PASS |
| 206 | `FORGE_MAX_NUM_TRADES` | `lot_sizing.max_num_trades` | yes | no | `30` | PASS |
| 208 | `FORGE_GOLD_NATIVE_MAX_SELL_LEGS` | `lot_sizing.gold_native_max_sell_legs` | yes | no | `10` | PASS |
| 210 | `FORGE_NATIVE_LEGS_MAX_WHEN_UNCLEAR` | `lot_sizing.native_legs_max_when_unclear` | yes | no | `5` | PASS |
| 223 | `FORGE_STAGED_ADD_MIN_FAVORABLE_POINTS` | `lot_sizing.staged_add_min_favorable_points` | yes | no | `300` | PASS |
| 229 | `FORGE_GEOMETRY_WAVE_CONFIRM_LOT_MULT` | `lot_sizing.wave_confirmation_lot_mult` | yes | no | `2` | PASS |
| 232 | `FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR` | `bb_breakout.sell_inside_band_lot_factor` | yes | no | `0.25` | PASS |
| 233 | `FORGE_BREAKOUT_MAX_REENTRY_ATR_EXT` | `bb_breakout.max_reentry_atr_ext` | yes | no | `2` | PASS |
| 235 | `FORGE_BREAKOUT_ADX_MIN` | `bb_breakout.adx_min` | yes | no | `20` | PASS |
| 237 | `FORGE_BREAKOUT_ADX_MIN_SELL` | `bb_breakout.adx_min_sell` | yes | no | `25.0` | PASS |
| 239 | `FORGE_BREAKOUT_REQUIRE_RSI_DECLINING_SELL` | `bb_breakout.require_rsi_declining_sell` | yes | no | `1` | PASS |
| 242 | `FORGE_GATE_BREAKOUT_HID_BULL_DIV_BLOCK_SELL` | `bb_breakout.block_hid_bull_sell` | yes | no | `1` | PASS |
| 246 | `FORGE_BREAKOUT_REQUIRE_H1_DI_BUY` | `bb_breakout.require_h1_di_buy` | yes | no | `1` | PASS |
| 248 | `FORGE_BREAKOUT_REQUIRE_H1_DI_SELL` | `bb_breakout.require_h1_di_sell` | yes | no | `1` | PASS |
| 257 | `FORGE_TIMING_BREAKOUT_SAME_DIR_COOLDOWN_SEC` | `bb_breakout.same_dir_cooldown_seconds` | yes | no | `0` | PASS |
| 262 | `FORGE_BREAKOUT_FAILED_GATE_ENABLED` | `bb_breakout.failed_gate_enabled` | yes | no | `1` | PASS |
| 266 | `FORGE_BREAKOUT_FAILED_MIN_PEAK_RSI` | `bb_breakout.failed_min_peak_rsi` | yes | no | `68` | PASS |
| 267 | `FORGE_BREAKOUT_FAILED_MIN_RSI_DROP` | `bb_breakout.failed_min_rsi_drop` | yes | no | `3.0` | PASS |
| 271 | `FORGE_BREAKOUT_FAILED_SAME_BAR_HARD_BLOCK` | `bb_breakout.failed_same_bar_hard_block` | yes | no | `1` | PASS |
| 275 | `FORGE_BREAKOUT_REQUIRE_PSAR_ALIGN` | `bb_breakout.require_psar_align` | yes | no | `1` | PASS |
| 277 | `FORGE_BREAKOUT_COUNTER_BUY_ADX_THRESHOLD` | `bb_breakout.counter_buy_adx_threshold` | yes | no | `28.0` | PASS |
| 285 | `FORGE_SESSION_NY_SELL_CUTOFF_UTC` | `safety.session_ny_sell_cutoff_utc` | yes | no | `0` | PASS |
| 290 | `FORGE_BREAKOUT_RSI_SELL_FLOOR` | `bb_breakout.rsi_sell_floor` | yes | no | `33` | PASS |
| 294 | `FORGE_BREAKOUT_REQUIRE_MACD_BUY` | `bb_breakout.require_macd_buy` | yes | no | `1` | PASS |
| 304 | `FORGE_BREAKOUT_ADX_LOT_FACTOR_MID` | `safety.breakout_adx_lot_factor_mid` | yes | no | `1` | PASS |
| 305 | `FORGE_BREAKOUT_ADX_LOT_FACTOR_HIGH` | `safety.breakout_adx_lot_factor_high` | yes | no | `0.5` | PASS |
| 307 | `FORGE_BREAKOUT_ADX_SELL_BLOCK_THRESHOLD` | `bb_breakout.adx_sell_block_threshold` | yes | no | `55` | PASS |
| 309 | `FORGE_BREAKOUT_RSI_BUY_CEIL` | `bb_breakout.rsi_buy_ceil` | yes | no | `78` | PASS |
| 315 | `FORGE_SELL_STOP_CONT_ENABLED` | `bb_breakout.sell_stop_cont_enabled` | yes | no | `0` | PASS |
| 339 | `FORGE_BUY_LIMIT_RECOVERY_ENABLED` | `bb_breakout.buy_limit_recovery_enabled` | yes | no | `1` | PASS |
| 340 | `FORGE_BUY_LIMIT_RECOVERY_MIN_RSI` | `bb_breakout.buy_limit_recovery_min_rsi` | yes | no | `35.0` | PASS |
| 344 | `FORGE_BUY_LIMIT_RECOVERY_LOT_FACTOR` | `bb_breakout.buy_limit_recovery_lot_factor` | yes | no | `0.5` | PASS |
| 345 | `FORGE_BUY_LIMIT_RECOVERY_EXPIRY_BARS` | `bb_breakout.buy_limit_recovery_expiry_bars` | yes | no | `8` | PASS |
| 346 | `FORGE_SELL_STOP_CONT_ATR_MULT` | `bb_breakout.sell_stop_cont_atr_mult` | yes | no | `0.4` | PASS |
| 351 | `FORGE_GEOMETRY_SELL_STOP_CONT_SL_ATR_MULT` | `bb_breakout.sell_stop_cont_sl_atr_mult` | yes | no | `3.5` | PASS |
| 357 | `FORGE_BREAKOUT_BUY_SL_ATR_MULT` | `bb_breakout.buy_sl_atr_mult` | yes | no | `3` | PASS |
| 366 | `FORGE_BREAKOUT_BE_CUSHION_ATR_MULT` | `bb_breakout.be_cushion_atr_mult` | yes | no | `1.5` | PASS |
| 372 | `FORGE_BREAKOUT_TP2_SL_RATCHET_ENABLED` | `bb_breakout.tp2_sl_ratchet_enabled` | yes | no | `1` | PASS |
| 378 | `FORGE_BREAKOUT_ATR_TRAIL_ENABLED` | `bb_breakout.atr_trail_enabled` | yes | no | `1` | PASS |
| 381 | `FORGE_SELL_STOP_CONT_MIN_RSI` | `bb_breakout.sell_stop_cont_min_rsi` | yes | no | `25.0` | PASS |
| 382 | `FORGE_ATOM_SELL_STOP_CONT_M5_ADX_MIN` | `bb_breakout.sell_stop_cont_min_adx` | yes | no | `25.0` | PASS |
| 386 | `FORGE_SELL_STOP_CONT_REQUIRE_TREND_REGIME` | `bb_breakout.sell_stop_cont_require_trend_regime` | yes | no | `1` | PASS |
| 392 | `FORGE_ATOM_HTF_H4_RSI_MAX_SELL` | `bb_breakout.h4_rsi_sell_max` | yes | no | `60.0` | PASS |
| 393 | `FORGE_ATOM_HTF_H4_RSI_MIN_BUY` | `bb_breakout.h4_rsi_buy_min` | yes | no | `40.0` | PASS |
| 396 | `FORGE_ATOM_HTF_H4_ADX_MIN_SELL` | `bb_breakout.h4_adx_min_sell` | yes | no | `20.0` | PASS |
| 397 | `FORGE_ATOM_HTF_H4_ADX_MIN_BUY` | `bb_breakout.h4_adx_min_buy` | yes | no | `20.0` | PASS |
| 403 | `FORGE_ATOM_BREAKOUT_CRASH_BYPASS_M15_ADX_MIN_SELL` | `bb_breakout.h1h4_crash_sell_min_m15_adx` | yes | no | `25.0` | PASS |
| 406 | `FORGE_BOUNCE_ADX_MAX` | `bb_bounce.adx_max` | yes | no | `30` | PASS |
| 408 | `FORGE_BOUNCE_LOT_FACTOR` | `bb_bounce.bounce_lot_factor` | yes | no | `0.25` | PASS |
| 413 | `FORGE_ATOM_M5_ADX_TREND_ENTER` | `safety.adx_trend_enter` | yes | no | `54.0` | PASS |
| 414 | `FORGE_ATOM_M5_ADX_TREND_EXIT` | `safety.adx_trend_exit` | yes | no | `47.0` | PASS |
| 446 | `FORGE_MIN_ENTRY_ATR` | `safety.min_entry_atr` | yes | no | `1` | PASS |
| 449 | `FORGE_MIN_DIRECTIONAL_BARS` | `safety.min_directional_bars` | yes | no | `1` | PASS |
| 451 | `FORGE_MIN_BODY_RATIO` | `safety.min_body_ratio` | yes | no | `0.25` | PASS |
| 453 | `FORGE_REQUIRE_BB_EXPANSION` | `safety.require_bb_expansion` | yes | no | `0` | PASS |
| 456 | `FORGE_GATE_DAILY_DIRECTION_ENABLE` | `safety.daily_direction_gate_enabled` | yes | no | `1` | PASS |
| 458 | `FORGE_ATOM_HTF_H1_STRONG_FACTOR` | `safety.regime_h1_override_factor` | yes | no | `2` | PASS |
| 459 | `FORGE_DUMP_CATCH_ENABLED` | `safety.dump_catch_enabled` | yes | no | `1` | PASS |
| 460 | `FORGE_DUMP_REQUIRE_D1_BIAS` | `safety.dump_require_d1_bias` | yes | no | `0` | PASS |
| 461 | `FORGE_DUMP_LOT_FACTOR` | `safety.dump_lot_factor` | yes | no | `0.5` | PASS |
| 465 | `FORGE_DUMP_MIN_ADX` | `safety.dump_min_adx` | yes | no | `20` | PASS |
| 470 | `FORGE_DUMP_ATR_MULT` | `safety.dump_atr_mult` | yes | no | `1` | PASS |
| 475 | `FORGE_DUMP_MAX_RSI` | `safety.dump_max_rsi` | yes | no | `41` | PASS |
| 479 | `FORGE_ATOM_DUMP_H1_TREND_MAX_SELL` | `safety.dump_sell_h1_max` | yes | no | `2` | PASS |
| 483 | `FORGE_GEOMETRY_DUMP_LOT_FACTOR_BUY` | `safety.dump_buy_lot_factor` | yes | no | `1` | PASS |
| 484 | `FORGE_GEOMETRY_DUMP_LOT_FACTOR_SELL` | `safety.dump_sell_lot_factor` | yes | no | `0.5` | PASS |
| 489 | `FORGE_ATOM_DUMP_RSI_MAX_BUY` | `safety.dump_max_rsi_buy` | yes | no | `70` | PASS |
| 494 | `FORGE_GATE_DUMP_SELL_LATE_RSI_BLOCK` | `safety.dump_sell_late_rsi_block` | yes | no | `37` | PASS |
| 499 | `FORGE_GATE_BLR_BUY_BLOCK_ON_BEARISH_BOS` | `safety.blr_buy_block_on_bearish_bos` | yes | no | `1` | PASS |
| 500 | `FORGE_GATE_BLR_BUY_MIN_VELOCITY_5BAR_SIGNED` | `safety.blr_buy_min_velocity_5bar_signed` | yes | no | `-1` | PASS |
| 503 | `FORGE_GATE_BLR_BUY_CAPITULATION_OVERRIDE_ENABLED` | `safety.blr_buy_capitulation_override_enabled` | yes | no | `1` | PASS |
| 504 | `FORGE_GATE_BLR_BUY_CAPITULATION_MIN_ATOMS` | `safety.blr_buy_capitulation_min_atoms` | yes | no | `3` | PASS |
| 505 | `FORGE_GATE_BLR_BUY_CAPITULATION_RSI_MAX` | `safety.blr_buy_capitulation_rsi_max` | yes | no | `28` | PASS |
| 506 | `FORGE_GATE_BLR_BUY_CAPITULATION_DISPLACEMENT_MIN_ATR` | `safety.blr_buy_capitulation_displacement_min_atr` | yes | no | `1.5` | PASS |
| 507 | `FORGE_GATE_BLR_BUY_CAPITULATION_ATR_RATIO_MIN` | `safety.blr_buy_capitulation_atr_ratio_min` | yes | no | `1.3` | PASS |
| 508 | `FORGE_GEOMETRY_BLR_BUY_CAPITULATION_LOT` | `composites.blr_buy_capitulation_lot` | yes | no | `0.3` | PASS |
| 509 | `FORGE_GEOMETRY_BLR_BUY_CAPITULATION_SL_ATR_MULT` | `composites.blr_buy_capitulation_sl_atr_mult` | yes | no | `1.5` | PASS |
| 510 | `FORGE_GEOMETRY_BLR_BUY_CAPITULATION_TP1_ATR_MULT` | `composites.blr_buy_capitulation_tp1_atr_mult` | yes | no | `0.5` | PASS |
| 511 | `FORGE_GEOMETRY_BLR_BUY_CAPITULATION_TP2_ATR_MULT` | `composites.blr_buy_capitulation_tp2_atr_mult` | yes | no | `1.5` | PASS |
| 514 | `FORGE_GATE_BREAKOUT_BUY_EXHAUSTION_RSI` | `safety.breakout_buy_exhaustion_rsi` | yes | no | `72` | PASS |
| 515 | `FORGE_GATE_BREAKOUT_BUY_BLOCK_EXHAUSTION_WITHOUT_BOS` | `safety.breakout_buy_block_exhaustion_without_bos` | yes | no | `1` | PASS |
| 522 | `FORGE_GATE_BREAKOUT_BUY_MAX_VWAP_DIST_ATR` | `safety.breakout_buy_max_vwap_dist_atr` | yes | no | `2.5` | PASS |
| 523 | `FORGE_GATE_BREAKOUT_SELL_MAX_VWAP_DIST_ATR` | `safety.breakout_sell_max_vwap_dist_atr` | yes | no | `2.5` | PASS |
| 530 | `FORGE_SETUP_BREAKOUT_BUY_CONVICTION_ENABLED` | `safety.breakout_buy_conviction_enabled` | yes | no | `1` | PASS |
| 531 | `FORGE_GATE_BREAKOUT_BUY_CONVICTION_MIN_ATOMS` | `safety.breakout_buy_conviction_min_atoms` | yes | no | `4` | PASS |
| 532 | `FORGE_GEOMETRY_BREAKOUT_BUY_CONVICTION_INITIAL_LEGS` | `safety.breakout_buy_conviction_initial_legs` | yes | no | `5` | PASS |
| 533 | `FORGE_GEOMETRY_BREAKOUT_BUY_CONVICTION_TP1_CLOSE_PCT` | `safety.breakout_buy_conviction_tp1_close_pct` | yes | no | `50` | PASS |
| 539 | `FORGE_GATE_BREAKOUT_BUY_SCORE_VELOCITY_CHECK_ENABLED` | `safety.breakout_buy_score_velocity_check_enabled` | yes | no | `1` | PASS |
| 540 | `FORGE_GATE_BREAKOUT_BUY_SCORE_VELOCITY_THRESHOLD` | `safety.breakout_buy_score_velocity_threshold` | yes | no | `-5` | PASS |
| 547 | `FORGE_SETUP_CONVICTION_DECAY_PARTIAL_CLOSE_ENABLED` | `safety.conviction_decay_partial_close_enabled` | yes | no | `1` | PASS |
| 548 | `FORGE_GATE_CONVICTION_DECAY_L1_RATIO` | `safety.conviction_decay_l1_ratio` | yes | no | `0.75` | PASS |
| 549 | `FORGE_GATE_CONVICTION_DECAY_L2_RATIO` | `safety.conviction_decay_l2_ratio` | yes | no | `0.5` | PASS |
| 550 | `FORGE_GATE_CONVICTION_DECAY_L3_RATIO` | `safety.conviction_decay_l3_ratio` | yes | no | `0.25` | PASS |
| 551 | `FORGE_GEOMETRY_CONVICTION_DECAY_L1_CLOSE_PCT` | `safety.conviction_decay_l1_close_pct` | yes | no | `25` | PASS |
| 552 | `FORGE_GEOMETRY_CONVICTION_DECAY_L2_CLOSE_PCT` | `safety.conviction_decay_l2_close_pct` | yes | no | `50` | PASS |
| 553 | `FORGE_TIMING_CONVICTION_DECAY_GRACE_BARS` | `safety.conviction_decay_grace_bars` | yes | no | `2` | PASS |
| 560 | `FORGE_SETUP_REVERSE_SELL_IN_BULL_ENABLED` | `composites.reverse_sell_in_bull_enabled` | yes | no | `1` | PASS |
| 561 | `FORGE_GEOMETRY_REVERSE_SELL_IN_BULL_LOT_FACTOR` | `composites.reverse_sell_in_bull_lot_factor` | yes | no | `0.5` | PASS |
| 562 | `FORGE_GATE_REVERSE_SELL_IN_BULL_MIN_RSI` | `composites.reverse_sell_in_bull_min_rsi` | yes | no | `72` | PASS |
| 563 | `FORGE_GATE_REVERSE_SELL_IN_BULL_MIN_VWAP_DIST_ATR` | `composites.reverse_sell_in_bull_min_vwap_dist_atr` | yes | no | `2` | PASS |
| 564 | `FORGE_GATE_REVERSE_SELL_IN_BULL_MIN_H1_TREND` | `composites.reverse_sell_in_bull_min_h1_trend` | yes | no | `1` | PASS |
| 565 | `FORGE_GATE_REVERSE_SELL_IN_BULL_REQUIRE_DI_PLUS_ABOVE_MINUS` | `composites.reverse_sell_in_bull_require_di_plus_above_minus` | yes | no | `1` | PASS |
| 566 | `FORGE_GEOMETRY_REVERSE_SELL_IN_BULL_SL_ATR_MULT` | `composites.reverse_sell_in_bull_sl_atr_mult` | yes | no | `2` | PASS |
| 567 | `FORGE_GEOMETRY_REVERSE_SELL_IN_BULL_TP1_ATR_MULT` | `composites.reverse_sell_in_bull_tp1_atr_mult` | yes | no | `1` | PASS |
| 568 | `FORGE_GEOMETRY_REVERSE_SELL_IN_BULL_TP2_ATR_MULT` | `composites.reverse_sell_in_bull_tp2_atr_mult` | yes | no | `2` | PASS |
| 569 | `FORGE_TIMING_REVERSE_SELL_IN_BULL_COOLDOWN_SEC` | `composites.reverse_sell_in_bull_cooldown_sec` | yes | no | `300` | PASS |
| 576 | `FORGE_SETUP_GRINDING_SELL_ENABLED` | `composites.grinding_sell_enabled` | yes | no | `1` | PASS |
| 577 | `FORGE_GEOMETRY_GRINDING_SELL_LOT_FACTOR` | `composites.grinding_sell_lot_factor` | yes | no | `0.5` | PASS |
| 578 | `FORGE_GATE_GRINDING_SELL_MIN_VELOCITY` | `composites.grinding_sell_min_velocity` | yes | no | `0.5` | PASS |
| 579 | `FORGE_GATE_GRINDING_SELL_MAX_RSI` | `composites.grinding_sell_max_rsi` | yes | no | `55` | PASS |
| 580 | `FORGE_GATE_GRINDING_SELL_MIN_RSI` | `composites.grinding_sell_min_rsi` | yes | no | `30` | PASS |
| 581 | `FORGE_GATE_GRINDING_SELL_ROOM_MIN_ATR` | `composites.grinding_sell_room_min_atr` | yes | no | `0.3` | PASS |
| 582 | `FORGE_GEOMETRY_GRINDING_SELL_SL_ATR_MULT` | `composites.grinding_sell_sl_atr_mult` | yes | no | `2.5` | PASS |
| 583 | `FORGE_GEOMETRY_GRINDING_SELL_TP1_ATR_MULT` | `composites.grinding_sell_tp1_atr_mult` | yes | no | `0.7` | PASS |
| 584 | `FORGE_GEOMETRY_GRINDING_SELL_TP2_ATR_MULT` | `composites.grinding_sell_tp2_atr_mult` | yes | no | `1.5` | PASS |
| 585 | `FORGE_TIMING_GRINDING_SELL_COOLDOWN_SEC` | `composites.grinding_sell_cooldown_sec` | yes | no | `600` | PASS |
| 589 | `FORGE_SETUP_ASIA_CAPITULATION_BUY_ENABLED` | `composites.asia_capitulation_buy_enabled` | yes | no | `1` | PASS |
| 595 | `FORGE_GATE_ASIA_CAPITULATION_BUY_MIN_ATOMS` | `composites.asia_capitulation_buy_min_atoms` | yes | no | `2` | PASS |
| 596 | `FORGE_GATE_ASIA_CAPITULATION_BUY_RSI_MAX` | `composites.asia_capitulation_buy_rsi_max` | yes | no | `28` | PASS |
| 597 | `FORGE_GATE_ASIA_CAPITULATION_BUY_DISPLACEMENT_MIN_ATR` | `composites.asia_capitulation_buy_displacement_min_atr` | yes | no | `1` | PASS |
| 598 | `FORGE_GATE_ASIA_CAPITULATION_BUY_ATR_RATIO_MIN` | `composites.asia_capitulation_buy_atr_ratio_min` | yes | no | `1.1` | PASS |
| 599 | `FORGE_TIMING_ASIA_CAPITULATION_BUY_SESSION_START_UTC` | `composites.asia_capitulation_buy_session_start_utc` | yes | no | `22` | PASS |
| 600 | `FORGE_TIMING_ASIA_CAPITULATION_BUY_SESSION_END_UTC` | `composites.asia_capitulation_buy_session_end_utc` | yes | no | `7` | PASS |
| 601 | `FORGE_GEOMETRY_ASIA_CAPITULATION_BUY_LOT` | `composites.asia_capitulation_buy_lot` | yes | no | `0.2` | PASS |
| 602 | `FORGE_GEOMETRY_ASIA_CAPITULATION_BUY_SL_ATR_MULT` | `composites.asia_capitulation_buy_sl_atr_mult` | yes | no | `1.5` | PASS |
| 608 | `FORGE_GEOMETRY_ASIA_CAPITULATION_BUY_TP1_ATR_MULT` | `composites.asia_capitulation_buy_tp1_atr_mult` | yes | no | `1` | PASS |
| 609 | `FORGE_GEOMETRY_ASIA_CAPITULATION_BUY_TP2_ATR_MULT` | `composites.asia_capitulation_buy_tp2_atr_mult` | yes | no | `2.5` | PASS |
| 610 | `FORGE_TIMING_ASIA_CAPITULATION_BUY_COOLDOWN_SEC` | `composites.asia_capitulation_buy_cooldown_sec` | yes | no | `1800` | PASS |
| 615 | `FORGE_GATE_UMCG_ENABLED` | `safety.umcg_enabled` | yes | no | `1` | PASS |
| 619 | `FORGE_GATE_UMCG_BUY_BLOCK_THRESHOLD` | `safety.umcg_buy_block_threshold` | yes | no | `5` | PASS |
| 620 | `FORGE_GATE_UMCG_SELL_BLOCK_THRESHOLD` | `safety.umcg_sell_block_threshold` | yes | no | `5` | PASS |
| 625 | `FORGE_GATE_UMCG_PEMCG_RSI_OVERBOUGHT` | `safety.umcg_pemcg_rsi_overbought` | yes | no | `65.0` | PASS |
| 626 | `FORGE_GATE_UMCG_PEMCG_RSI_OVERSOLD` | `safety.umcg_pemcg_rsi_oversold` | yes | no | `35.0` | PASS |
| 627 | `FORGE_GATE_UMCG_PEMCG_BODY_PCT_MAX_WEAK` | `safety.umcg_pemcg_body_pct_max_weak` | yes | no | `0.5` | PASS |
| 628 | `FORGE_GATE_UMCG_PEMCG_ATR_RATIO_MAX_CONTRACT` | `safety.umcg_pemcg_atr_ratio_max_contract` | yes | no | `1.0` | PASS |
| 629 | `FORGE_GATE_UMCG_PEMCG_BB_DIST_ATR_THRESHOLD` | `safety.umcg_pemcg_bb_dist_atr_threshold` | yes | no | `0.3` | PASS |
| 630 | `FORGE_GATE_CVCSM_ENABLED` | `safety.cvcsm_enabled` | yes | no | `1` | PASS |
| 631 | `FORGE_GATE_CVCSM_RELEASE_THRESHOLD` | `safety.cvcsm_release_threshold` | yes | no | `2` | PASS |
| 632 | `FORGE_TIMING_CVCSM_REQUIRED_CLEAN_BARS` | `safety.cvcsm_required_clean_bars` | yes | no | `2` | PASS |
| 633 | `FORGE_TIMING_CVCSM_MAX_COOLDOWN_SEC` | `safety.cvcsm_max_cooldown_sec` | yes | no | `1800` | PASS |
| 634 | `FORGE_GATE_CVCSM_TRIGGER_ON_SL` | `safety.cvcsm_trigger_on_sl` | yes | no | `1` | PASS |
| 635 | `FORGE_GATE_CVCSM_TRIGGER_ON_REGIME_FLIP` | `safety.cvcsm_trigger_on_regime_flip` | yes | no | `1` | PASS |
| 636 | `FORGE_SETUP_BB_EXHAUSTION_REVERSAL_ENABLED` | `composites.bb_exhaustion_reversal_enabled` | yes | no | `1` | PASS |
| 637 | `FORGE_GATE_BB_EXHAUSTION_REVERSAL_MIN_WARNINGS` | `composites.bb_exhaustion_reversal_min_warnings` | yes | no | `4` | PASS |
| 638 | `FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_LOT` | `composites.bb_exhaustion_reversal_lot` | yes | no | `0.1` | PASS |
| 639 | `FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_SL_ATR_MULT` | `composites.bb_exhaustion_reversal_sl_atr_mult` | yes | no | `1.0` | PASS |
| 640 | `FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_TP1_ATR_MULT` | `composites.bb_exhaustion_reversal_tp1_atr_mult` | yes | no | `0.0` | PASS |
| 641 | `FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_TP2_ATR_MULT` | `composites.bb_exhaustion_reversal_tp2_atr_mult` | yes | no | `0.0` | PASS |
| 642 | `FORGE_TIMING_BB_EXHAUSTION_REVERSAL_COOLDOWN_SEC` | `composites.bb_exhaustion_reversal_cooldown_sec` | yes | no | `0` | PASS |
| 643 | `FORGE_GATE_BB_EXHAUSTION_REVERSAL_PROXIMITY_ATR` | `composites.bb_exhaustion_reversal_proximity_atr` | yes | no | `1.5` | PASS |
| 649 | `FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_LOT_AMPLIFIER` | `composites.bb_exhaustion_reversal_lot_amplifier` | yes | no | `1.5` | PASS |
| 650 | `FORGE_GATE_BB_EXHAUSTION_REVERSAL_HIGH_CONVICTION_WARNINGS` | `composites.bb_exhaustion_reversal_high_conviction_warnings` | yes | no | `6` | PASS |
| 651 | `FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_HIGH_CONVICTION_LOT_FACTOR` | `composites.bb_exhaustion_reversal_high_conviction_lot_factor` | yes | no | `2.0` | PASS |
| 652 | `FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_LEGS_HIGH_CONVICTION` | `composites.bb_exhaustion_reversal_legs_high_conviction` | yes | no | `4` | PASS |
| 657 | `FORGE_GATE_BB_EXHAUSTION_REVERSAL_MAX_ADX` | `composites.bb_exhaustion_reversal_max_adx` | yes | no | `35.0` | PASS |
| 664 | `FORGE_GATE_BB_EXHAUSTION_REVERSAL_MAX_PREV_BAR_RANGE_ATR_MULT` | `composites.bb_exhaustion_reversal_max_prev_bar_range_atr_mult` | yes | no | `2.0` | PASS |
| 670 | `FORGE_GATE_BB_BREAKOUT_MIN_BREAKOUT_ATR_MULT` | `safety.bb_breakout_min_breakout_atr_mult` | yes | no | `0.1` | PASS |
| 671 | `FORGE_GATE_BB_BREAKOUT_MIN_BREAKDOWN_ATR_MULT` | `safety.bb_breakout_min_breakdown_atr_mult` | yes | no | `0.1` | PASS |
| 677 | `FORGE_GATE_TREND_CONTINUATION_BUY_H1_MIN` | `safety.trend_continuation_buy_h1_min` | yes | no | `1` | PASS |
| 678 | `FORGE_GATE_TREND_CONTINUATION_SELL_H1_MAX` | `safety.trend_continuation_sell_h1_max` | yes | no | `1` | PASS |
| 679 | `FORGE_GATE_TREND_CONTINUATION_BUY_MAX_DIST_FROM_DAY_HIGH_ATR` | `safety.trend_continuation_buy_max_dist_from_day_high_atr` | yes | no | `3` | PASS |
| 680 | `FORGE_GATE_TREND_CONTINUATION_SELL_MAX_DIST_FROM_DAY_LOW_ATR` | `safety.trend_continuation_sell_max_dist_from_day_low_atr` | yes | no | `3` | PASS |
| 684 | `FORGE_GATE_BB_PULLBACK_BUY_BLOCK_ON_FALLING_VELOCITY` | `safety.bb_pullback_buy_block_on_falling_velocity` | yes | no | `1` | PASS |
| 685 | `FORGE_GATE_BB_PULLBACK_BUY_MIN_VELOCITY_5BAR_SIGNED` | `safety.bb_pullback_buy_min_velocity_5bar_signed` | yes | no | `-1` | PASS |
| 691 | `FORGE_BREAKOUT_TP2_ATR_MULT` | `bb_breakout.tp2_atr_mult` | yes | no | `1` | PASS |
| 692 | `FORGE_BREAKOUT_TP3_ATR_MULT` | `bb_breakout.tp3_atr_mult` | yes | no | `5` | PASS |
| 696 | `FORGE_GATE_PYRAMID_KILL_ENABLED` | `safety.pyramid_kill_enabled` | yes | no | `1` | PASS |
| 697 | `FORGE_GATE_PYRAMID_KILL_MAX_LOSS_USD` | `safety.pyramid_kill_max_loss_usd` | yes | no | `50` | PASS |
| 698 | `FORGE_GATE_PYRAMID_KILL_VELOCITY_THRESHOLD` | `safety.pyramid_kill_velocity_threshold` | yes | no | `0.5` | PASS |
| 702 | `FORGE_SETUP_NY_SESSION_BEARISH_SELL_ENABLED` | `safety.ny_session_bearish_sell_enabled` | yes | no | `1` | PASS |
| 705 | `FORGE_TIMING_NY_SESSION_BEARISH_SELL_KZ_MAX_MIN` | `safety.ny_session_bearish_sell_kz_max_min` | yes | no | `120` | PASS |
| 706 | `FORGE_GATE_NY_SESSION_BEARISH_SELL_MIN_VELOCITY` | `safety.ny_session_bearish_sell_min_velocity` | yes | no | `1` | PASS |
| 707 | `FORGE_GATE_NY_SESSION_BEARISH_SELL_MAX_RSI` | `safety.ny_session_bearish_sell_max_rsi` | yes | no | `50` | PASS |
| 708 | `FORGE_GATE_NY_SESSION_BEARISH_SELL_ROOM_MIN_ATR` | `safety.ny_session_bearish_sell_room_min_atr` | yes | no | `1` | PASS |
| 709 | `FORGE_GEOMETRY_NY_SESSION_BEARISH_SELL_SL_ATR_MULT` | `safety.ny_session_bearish_sell_sl_atr_mult` | yes | no | `3.5` | PASS |
| 710 | `FORGE_GEOMETRY_NY_SESSION_BEARISH_SELL_TP1_ATR_MULT` | `safety.ny_session_bearish_sell_tp1_atr_mult` | yes | no | `1` | PASS |
| 711 | `FORGE_GEOMETRY_NY_SESSION_BEARISH_SELL_TP2_ATR_MULT` | `safety.ny_session_bearish_sell_tp2_atr_mult` | yes | no | `2.5` | PASS |
| 712 | `FORGE_TIMING_NY_SESSION_BEARISH_SELL_COOLDOWN_SEC` | `safety.ny_session_bearish_sell_cooldown_sec` | yes | no | `0` | PASS |
| 713 | `FORGE_GEOMETRY_NY_SESSION_BEARISH_SELL_LOT_FACTOR` | `safety.ny_session_bearish_sell_lot_factor` | yes | no | `1` | PASS |
| 716 | `FORGE_PULLBACK_SCALP_ENABLED` | `safety.pullback_scalp_enabled` | yes | no | `1` | PASS |
| 717 | `FORGE_PULLBACK_SCALP_FRESH_FLIP_BARS` | `safety.pullback_scalp_fresh_flip_bars` | yes | no | `3` | PASS |
| 718 | `FORGE_PULLBACK_SCALP_LOT_FACTOR` | `safety.pullback_scalp_lot_factor` | yes | no | `0.5` | PASS |
| 719 | `FORGE_PULLBACK_SCALP_SL_ATR_MULT` | `safety.pullback_scalp_sl_atr_mult` | yes | no | `2.5` | PASS |
| 725 | `FORGE_DUMP_REQUIRE_BAR_CONFIRM` | `safety.dump_require_bar_confirm` | yes | no | `1` | PASS |
| 726 | `FORGE_PULLBACK_SCALP_TP1_ATR_MULT` | `safety.pullback_scalp_tp1_atr_mult` | yes | no | `0.3` | PASS |
| 727 | `FORGE_PULLBACK_SCALP_TP2_ATR_MULT` | `safety.pullback_scalp_tp2_atr_mult` | yes | no | `0.7` | PASS |
| 728 | `FORGE_PULLBACK_SCALP_COOLDOWN_SECONDS` | `safety.pullback_scalp_cooldown_seconds` | yes | no | `0` | PASS |
| 729 | `FORGE_PULLBACK_SCALP_MAX_ADX` | `safety.pullback_scalp_max_adx` | yes | no | `30` | PASS |
| 734 | `FORGE_NEWS_FILTER_ENABLED` | `safety.news_filter_enabled` | yes | no | `1` | PASS |
| 744 | `FORGE_SETUP_MA_CROSSOVER_ENABLED` | `setup.ma_crossover_enabled` | yes | no | `1` | PASS |
| 745 | `FORGE_ATOM_MA_CROSSOVER_ADX_MIN` | `atom.ma_crossover_adx_min` | yes | no | `20.0` | PASS |
| 746 | `FORGE_GEOMETRY_MA_CROSSOVER_LOT_FACTOR` | `geometry.ma_crossover_lot_factor` | yes | no | `0.5` | PASS |
| 747 | `FORGE_GEOMETRY_MA_CROSSOVER_SL_ATR_MULT` | `geometry.ma_crossover_sl_atr_mult` | yes | no | `1.5` | PASS |
| 748 | `FORGE_GEOMETRY_MA_CROSSOVER_TP1_ATR_MULT` | `geometry.ma_crossover_tp1_atr_mult` | yes | no | `0.5` | PASS |
| 749 | `FORGE_GEOMETRY_MA_CROSSOVER_TP2_ATR_MULT` | `geometry.ma_crossover_tp2_atr_mult` | yes | no | `1.5` | PASS |
| 750 | `FORGE_TIMING_MA_CROSSOVER_COOLDOWN_SECONDS` | `timing.ma_crossover_cooldown_seconds` | yes | no | `0` | PASS |
| 753 | `FORGE_SETUP_VWAP_REVERSION_ENABLED` | `setup.vwap_reversion_enabled` | yes | no | `1` | PASS |
| 754 | `FORGE_ATOM_VWAP_REVERSION_MIN_DEVIATION_ATR` | `atom.vwap_reversion_min_deviation_atr` | yes | no | `1.0` | PASS |
| 755 | `FORGE_ATOM_VWAP_REVERSION_MAX_DEVIATION_ATR` | `atom.vwap_reversion_max_deviation_atr` | yes | no | `3.0` | PASS |
| 756 | `FORGE_ATOM_VWAP_REVERSION_MIN_EXTENSION_BARS` | `atom.vwap_reversion_min_extension_bars` | yes | no | `5` | PASS |
| 757 | `FORGE_GEOMETRY_VWAP_REVERSION_LOT_FACTOR` | `geometry.vwap_reversion_lot_factor` | yes | no | `0.5` | PASS |
| 758 | `FORGE_GEOMETRY_VWAP_REVERSION_SL_ATR_MULT` | `geometry.vwap_reversion_sl_atr_mult` | yes | no | `1.2` | PASS |
| 759 | `FORGE_GEOMETRY_VWAP_REVERSION_TP1_ATR_MULT` | `geometry.vwap_reversion_tp1_atr_mult` | yes | no | `0.4` | PASS |
| 760 | `FORGE_GEOMETRY_VWAP_REVERSION_TP2_ATR_MULT` | `geometry.vwap_reversion_tp2_atr_mult` | yes | no | `1.0` | PASS |
| 761 | `FORGE_TIMING_VWAP_REVERSION_COOLDOWN_SECONDS` | `timing.vwap_reversion_cooldown_seconds` | yes | no | `0` | PASS |
| 764 | `FORGE_SETUP_FIB_CONFLUENCE_ENABLED` | `setup.fib_confluence_enabled` | yes | no | `1` | PASS |
| 765 | `FORGE_ATOM_FIB_CONFLUENCE_MIN_CONFLUENCES` | `atom.fib_confluence_min_confluences` | yes | no | `1` | PASS |
| 766 | `FORGE_ATOM_FIB_CONFLUENCE_TOLERANCE_ATR` | `atom.fib_confluence_tolerance_atr` | yes | no | `0.3` | PASS |
| 767 | `FORGE_ATOM_FIB_CONFLUENCE_MIN_SWING_ATR` | `atom.fib_confluence_min_swing_atr` | yes | no | `2.0` | PASS |
| 768 | `FORGE_GEOMETRY_FIB_CONFLUENCE_LOT_FACTOR` | `geometry.fib_confluence_lot_factor` | yes | no | `0.5` | PASS |
| 769 | `FORGE_GEOMETRY_FIB_CONFLUENCE_SL_ATR_MULT` | `geometry.fib_confluence_sl_atr_mult` | yes | no | `1.5` | PASS |
| 770 | `FORGE_GEOMETRY_FIB_CONFLUENCE_TP1_ATR_MULT` | `geometry.fib_confluence_tp1_atr_mult` | yes | no | `0.5` | PASS |
| 771 | `FORGE_GEOMETRY_FIB_CONFLUENCE_TP2_ATR_MULT` | `geometry.fib_confluence_tp2_atr_mult` | yes | no | `1.3` | PASS |
| 772 | `FORGE_TIMING_FIB_CONFLUENCE_COOLDOWN_SECONDS` | `timing.fib_confluence_cooldown_seconds` | yes | no | `0` | PASS |
| 775 | `FORGE_SETUP_INSIDE_BAR_ENABLED` | `setup.inside_bar_enabled` | yes | no | `1` | PASS |
| 776 | `FORGE_ATOM_INSIDE_BAR_MIN_OUTER_ATR` | `atom.inside_bar_min_outer_atr` | yes | no | `1.0` | PASS |
| 777 | `FORGE_ATOM_INSIDE_BAR_ADX_MIN` | `atom.inside_bar_adx_min` | yes | no | `20.0` | PASS |
| 778 | `FORGE_GEOMETRY_INSIDE_BAR_LOT_FACTOR` | `geometry.inside_bar_lot_factor` | yes | no | `0.5` | PASS |
| 779 | `FORGE_GEOMETRY_INSIDE_BAR_SL_ATR_MULT` | `geometry.inside_bar_sl_atr_mult` | yes | no | `1.0` | PASS |
| 780 | `FORGE_GEOMETRY_INSIDE_BAR_TP1_ATR_MULT` | `geometry.inside_bar_tp1_atr_mult` | yes | no | `0.5` | PASS |
| 781 | `FORGE_GEOMETRY_INSIDE_BAR_TP2_ATR_MULT` | `geometry.inside_bar_tp2_atr_mult` | yes | no | `1.5` | PASS |
| 782 | `FORGE_TIMING_INSIDE_BAR_COOLDOWN_SECONDS` | `timing.inside_bar_cooldown_seconds` | yes | no | `0` | PASS |
| 785 | `FORGE_SETUP_BB_SQUEEZE_ENABLED` | `setup.bb_squeeze_enabled` | yes | no | `1` | PASS |
| 786 | `FORGE_ATOM_BB_SQUEEZE_LOOKBACK_BARS` | `atom.bb_squeeze_lookback_bars` | yes | no | `100` | PASS |
| 787 | `FORGE_ATOM_BB_SQUEEZE_PCTILE_THRESHOLD` | `atom.bb_squeeze_pctile_threshold` | yes | no | `20.0` | PASS |
| 788 | `FORGE_ATOM_BB_SQUEEZE_MIN_BREAKOUT_ATR` | `atom.bb_squeeze_min_breakout_atr` | yes | no | `0.3` | PASS |
| 789 | `FORGE_ATOM_BB_SQUEEZE_ADX_MIN` | `atom.bb_squeeze_adx_min` | yes | no | `15.0` | PASS |
| 790 | `FORGE_GEOMETRY_BB_SQUEEZE_LOT_FACTOR` | `geometry.bb_squeeze_lot_factor` | yes | no | `0.5` | PASS |
| 791 | `FORGE_GEOMETRY_BB_SQUEEZE_SL_ATR_MULT` | `geometry.bb_squeeze_sl_atr_mult` | yes | no | `1.5` | PASS |
| 792 | `FORGE_GEOMETRY_BB_SQUEEZE_TP1_ATR_MULT` | `geometry.bb_squeeze_tp1_atr_mult` | yes | no | `0.5` | PASS |
| 793 | `FORGE_GEOMETRY_BB_SQUEEZE_TP2_ATR_MULT` | `geometry.bb_squeeze_tp2_atr_mult` | yes | no | `2.0` | PASS |
| 794 | `FORGE_TIMING_BB_SQUEEZE_COOLDOWN_SECONDS` | `timing.bb_squeeze_cooldown_seconds` | yes | no | `0` | PASS |
| 798 | `FORGE_SETUP_ORB_ENABLED` | `setup.orb_enabled` | yes | no | `1` | PASS |
| 799 | `FORGE_ATOM_ORB_WINDOW_START_MIN` | `atom.orb_window_start_min` | yes | no | `120` | PASS |
| 800 | `FORGE_ATOM_ORB_WINDOW_END_MIN` | `atom.orb_window_end_min` | yes | no | `150` | PASS |
| 801 | `FORGE_ATOM_ORB_MIN_RANGE_ATR` | `atom.orb_min_range_atr` | yes | no | `1.0` | PASS |
| 802 | `FORGE_ATOM_ORB_MIN_BREAKOUT_ATR` | `atom.orb_min_breakout_atr` | yes | no | `0.3` | PASS |
| 803 | `FORGE_ATOM_ORB_ADX_MIN` | `atom.orb_adx_min` | yes | no | `15.0` | PASS |
| 804 | `FORGE_GEOMETRY_ORB_LOT_FACTOR` | `geometry.orb_lot_factor` | yes | no | `0.5` | PASS |
| 805 | `FORGE_GEOMETRY_ORB_SL_ATR_MULT` | `geometry.orb_sl_atr_mult` | yes | no | `1.5` | PASS |
| 806 | `FORGE_GEOMETRY_ORB_TP1_ATR_MULT` | `geometry.orb_tp1_atr_mult` | yes | no | `0.5` | PASS |
| 807 | `FORGE_GEOMETRY_ORB_TP2_ATR_MULT` | `geometry.orb_tp2_atr_mult` | yes | no | `2.0` | PASS |
| 808 | `FORGE_TIMING_ORB_COOLDOWN_SECONDS` | `timing.orb_cooldown_seconds` | yes | no | `0` | PASS |
| 811 | `FORGE_SETUP_GAP_AND_GO_ENABLED` | `setup.gap_and_go_enabled` | yes | no | `1` | PASS |
| 812 | `FORGE_ATOM_GAP_AND_GO_MIN_TIME_SKIP_SECONDS` | `atom.gap_and_go_min_time_skip_seconds` | yes | no | `3600` | PASS |
| 813 | `FORGE_ATOM_GAP_AND_GO_MIN_GAP_ATR` | `atom.gap_and_go_min_gap_atr` | yes | no | `0.5` | PASS |
| 814 | `FORGE_ATOM_GAP_AND_GO_MAX_GAP_ATR` | `atom.gap_and_go_max_gap_atr` | yes | no | `3.0` | PASS |
| 815 | `FORGE_GEOMETRY_GAP_AND_GO_LOT_FACTOR` | `geometry.gap_and_go_lot_factor` | yes | no | `0.5` | PASS |
| 816 | `FORGE_GEOMETRY_GAP_AND_GO_SL_ATR_MULT` | `geometry.gap_and_go_sl_atr_mult` | yes | no | `1.5` | PASS |
| 817 | `FORGE_GEOMETRY_GAP_AND_GO_TP1_ATR_MULT` | `geometry.gap_and_go_tp1_atr_mult` | yes | no | `0.5` | PASS |
| 818 | `FORGE_GEOMETRY_GAP_AND_GO_TP2_ATR_MULT` | `geometry.gap_and_go_tp2_atr_mult` | yes | no | `1.5` | PASS |
| 819 | `FORGE_TIMING_GAP_AND_GO_COOLDOWN_SECONDS` | `timing.gap_and_go_cooldown_seconds` | yes | no | `0` | PASS |
| 822 | `FORGE_ATOM_SWING_LOOKBACK_BARS` | `atom.swing_lookback_bars` | yes | no | `3` | PASS |
| 823 | `FORGE_ATOM_SWING_MIN_SIZE_ATR` | `atom.swing_min_size_atr` | yes | no | `0.5` | PASS |
| 826 | `FORGE_SETUP_DOUBLE_TOP_ENABLED` | `setup.double_top_enabled` | yes | no | `1` | PASS |
| 827 | `FORGE_SETUP_DOUBLE_BOTTOM_ENABLED` | `setup.double_bottom_enabled` | yes | no | `1` | PASS |
| 828 | `FORGE_ATOM_DOUBLE_PATTERN_PEAK_TOLERANCE_ATR` | `atom.double_pattern_peak_tolerance_atr` | yes | no | `0.3` | PASS |
| 829 | `FORGE_ATOM_DOUBLE_PATTERN_MIN_NECKLINE_DROP_ATR` | `atom.double_pattern_min_neckline_drop_atr` | yes | no | `1.0` | PASS |
| 830 | `FORGE_ATOM_DOUBLE_PATTERN_ADX_MIN` | `atom.double_pattern_adx_min` | yes | no | `15.0` | PASS |
| 831 | `FORGE_GEOMETRY_DOUBLE_PATTERN_LOT_FACTOR` | `geometry.double_pattern_lot_factor` | yes | no | `0.5` | PASS |
| 832 | `FORGE_GEOMETRY_DOUBLE_PATTERN_SL_ATR_MULT` | `geometry.double_pattern_sl_atr_mult` | yes | no | `1.5` | PASS |
| 833 | `FORGE_GEOMETRY_DOUBLE_PATTERN_TP1_ATR_MULT` | `geometry.double_pattern_tp1_atr_mult` | yes | no | `0.5` | PASS |
| 834 | `FORGE_GEOMETRY_DOUBLE_PATTERN_TP2_ATR_MULT` | `geometry.double_pattern_tp2_atr_mult` | yes | no | `1.5` | PASS |
| 835 | `FORGE_TIMING_DOUBLE_PATTERN_COOLDOWN_SECONDS` | `timing.double_pattern_cooldown_seconds` | yes | no | `0` | PASS |
| 838 | `FORGE_SETUP_HEAD_AND_SHOULDERS_ENABLED` | `setup.head_and_shoulders_enabled` | yes | no | `1` | PASS |
| 839 | `FORGE_SETUP_INVERSE_HEAD_AND_SHOULDERS_ENABLED` | `setup.inverse_head_and_shoulders_enabled` | yes | no | `1` | PASS |
| 840 | `FORGE_ATOM_HS_SHOULDER_TOLERANCE_ATR` | `atom.hs_shoulder_tolerance_atr` | yes | no | `0.3` | PASS |
| 841 | `FORGE_ATOM_HS_HEAD_PROMINENCE_ATR` | `atom.hs_head_prominence_atr` | yes | no | `0.8` | PASS |
| 842 | `FORGE_ATOM_HS_ADX_MIN` | `atom.hs_adx_min` | yes | no | `15.0` | PASS |
| 843 | `FORGE_GEOMETRY_HS_LOT_FACTOR` | `geometry.hs_lot_factor` | yes | no | `0.5` | PASS |
| 844 | `FORGE_GEOMETRY_HS_SL_ATR_MULT` | `geometry.hs_sl_atr_mult` | yes | no | `1.5` | PASS |
| 845 | `FORGE_GEOMETRY_HS_TP1_ATR_MULT` | `geometry.hs_tp1_atr_mult` | yes | no | `0.5` | PASS |
| 846 | `FORGE_GEOMETRY_HS_TP2_ATR_MULT` | `geometry.hs_tp2_atr_mult` | yes | no | `1.5` | PASS |
| 847 | `FORGE_TIMING_HS_COOLDOWN_SECONDS` | `timing.hs_cooldown_seconds` | yes | no | `0` | PASS |
| 850 | `FORGE_SETUP_FLAG_PENNANT_ENABLED` | `setup.flag_pennant_enabled` | yes | no | `1` | PASS |
| 851 | `FORGE_ATOM_FLAG_PENNANT_IMPULSE_LOOKBACK_BARS` | `atom.flag_pennant_impulse_lookback_bars` | yes | no | `10` | PASS |
| 852 | `FORGE_ATOM_FLAG_PENNANT_IMPULSE_MIN_ATR` | `atom.flag_pennant_impulse_min_atr` | yes | no | `2.0` | PASS |
| 853 | `FORGE_ATOM_FLAG_PENNANT_CONSOLIDATION_BARS` | `atom.flag_pennant_consolidation_bars` | yes | no | `5` | PASS |
| 854 | `FORGE_ATOM_FLAG_PENNANT_CONSOLIDATION_MAX_ATR` | `atom.flag_pennant_consolidation_max_atr` | yes | no | `0.8` | PASS |
| 855 | `FORGE_ATOM_FLAG_PENNANT_ADX_MIN` | `atom.flag_pennant_adx_min` | yes | no | `15.0` | PASS |
| 856 | `FORGE_GEOMETRY_FLAG_PENNANT_LOT_FACTOR` | `geometry.flag_pennant_lot_factor` | yes | no | `0.5` | PASS |
| 857 | `FORGE_GEOMETRY_FLAG_PENNANT_SL_ATR_MULT` | `geometry.flag_pennant_sl_atr_mult` | yes | no | `1.5` | PASS |
| 858 | `FORGE_GEOMETRY_FLAG_PENNANT_TP1_ATR_MULT` | `geometry.flag_pennant_tp1_atr_mult` | yes | no | `0.5` | PASS |
| 859 | `FORGE_GEOMETRY_FLAG_PENNANT_TP2_ATR_MULT` | `geometry.flag_pennant_tp2_atr_mult` | yes | no | `2.0` | PASS |
| 860 | `FORGE_TIMING_FLAG_PENNANT_COOLDOWN_SECONDS` | `timing.flag_pennant_cooldown_seconds` | yes | no | `0` | PASS |
| 863 | `FORGE_SETUP_TRENDLINE_BOUNCE_ENABLED` | `setup.trendline_bounce_enabled` | yes | no | `1` | PASS |
| 864 | `FORGE_ATOM_TRENDLINE_TOUCH_TOLERANCE_ATR` | `atom.trendline_touch_tolerance_atr` | yes | no | `0.3` | PASS |
| 865 | `FORGE_ATOM_TRENDLINE_ADX_MIN` | `atom.trendline_adx_min` | yes | no | `15.0` | PASS |
| 866 | `FORGE_GEOMETRY_TRENDLINE_BOUNCE_LOT_FACTOR` | `geometry.trendline_bounce_lot_factor` | yes | no | `0.5` | PASS |
| 867 | `FORGE_GEOMETRY_TRENDLINE_BOUNCE_SL_ATR_MULT` | `geometry.trendline_bounce_sl_atr_mult` | yes | no | `1.5` | PASS |
| 868 | `FORGE_GEOMETRY_TRENDLINE_BOUNCE_TP1_ATR_MULT` | `geometry.trendline_bounce_tp1_atr_mult` | yes | no | `0.5` | PASS |
| 869 | `FORGE_GEOMETRY_TRENDLINE_BOUNCE_TP2_ATR_MULT` | `geometry.trendline_bounce_tp2_atr_mult` | yes | no | `1.5` | PASS |
| 870 | `FORGE_TIMING_TRENDLINE_BOUNCE_COOLDOWN_SECONDS` | `timing.trendline_bounce_cooldown_seconds` | yes | no | `0` | PASS |
| 873 | `FORGE_SETUP_SR_FLIP_ENABLED` | `setup.sr_flip_enabled` | yes | no | `1` | PASS |
| 874 | `FORGE_ATOM_SR_FLIP_TOLERANCE_ATR` | `atom.sr_flip_tolerance_atr` | yes | no | `0.3` | PASS |
| 875 | `FORGE_ATOM_SR_FLIP_ADX_MIN` | `atom.sr_flip_adx_min` | yes | no | `15.0` | PASS |
| 876 | `FORGE_GEOMETRY_SR_FLIP_LOT_FACTOR` | `geometry.sr_flip_lot_factor` | yes | no | `0.5` | PASS |
| 877 | `FORGE_GEOMETRY_SR_FLIP_SL_ATR_MULT` | `geometry.sr_flip_sl_atr_mult` | yes | no | `1.5` | PASS |
| 878 | `FORGE_GEOMETRY_SR_FLIP_TP1_ATR_MULT` | `geometry.sr_flip_tp1_atr_mult` | yes | no | `0.5` | PASS |
| 879 | `FORGE_GEOMETRY_SR_FLIP_TP2_ATR_MULT` | `geometry.sr_flip_tp2_atr_mult` | yes | no | `1.5` | PASS |
| 880 | `FORGE_TIMING_SR_FLIP_COOLDOWN_SECONDS` | `timing.sr_flip_cooldown_seconds` | yes | no | `0` | PASS |
| 883 | `FORGE_SETUP_FRACTIONAL_SELL_IN_BULL_ENABLED` | `composites.fractional_sell_in_bull_enabled` | yes | no | `1` | PASS |
| 884 | `FORGE_SETUP_BULL_DAY_DIP_BUY_ENABLED` | `composites.bull_day_dip_buy_enabled` | yes | no | `1` | PASS |
| 890 | `FORGE_GEOMETRY_TREND_CONTINUATION_BUY_SL_ATR_MULT` | `safety.trend_continuation_buy_sl_atr_mult` | yes | no | `2.5` | PASS |
| 891 | `FORGE_GEOMETRY_TREND_CONTINUATION_SELL_SL_ATR_MULT` | `safety.trend_continuation_sell_sl_atr_mult` | yes | no | `2.5` | PASS |
| 893 | `FORGE_TIMING_TREND_CONTINUATION_BUY_COOLDOWN_SECONDS` | `safety.trend_continuation_buy_cooldown_seconds` | yes | no | `0` | PASS |
| 894 | `FORGE_TIMING_TREND_CONTINUATION_SELL_COOLDOWN_SECONDS` | `safety.trend_continuation_sell_cooldown_seconds` | yes | no | `0` | PASS |
| 904 | `FORGE_SETUP_MOMENTUM_DUMP_COMPOSITE_ENABLED` | `safety.momentum_dump_composite_enabled` | yes | no | `1` | PASS |
| 913 | `FORGE_SETUP_DUMP_LEGS_PER_GROUP` | `safety.dump_legs_per_group` | yes | no | `10` | PASS |
| 915 | `FORGE_BREAKOUT_TP1_CLOSE_PCT` | `bb_breakout.tp1_close_pct` | yes | no | `70` | PASS |
| 918 | `FORGE_STAGED_INITIAL_LEGS` | `lot_sizing.staged_initial_legs` | yes | no | `3` | PASS |
| 922 | `FORGE_TIMING_DUMP_MAX_HOLD_SECONDS` | `safety.dump_max_hold_seconds` | yes | no | `0` | PASS |
| 923 | `FORGE_TIMING_BB_LOWER_REVERSION_BUY_MAX_HOLD_SECONDS` | `safety.bb_lower_reversion_buy_max_hold_seconds` | yes | no | `0` | PASS |
| 927 | `FORGE_DUMP_COOLDOWN_SECONDS` | `safety.dump_cooldown_seconds` | yes | no | `0` | PASS |
| 928 | `FORGE_TIMING_BB_LOWER_REVERSION_BUY_COOLDOWN_SECONDS` | `safety.bb_lower_reversion_buy_cooldown_seconds` | yes | no | `0` | PASS |
| 929 | `FORGE_TIMING_MOMENTUM_DUMP_COMPOSITE_COOLDOWN_SECONDS` | `safety.momentum_dump_composite_cooldown_seconds` | yes | no | `0` | PASS |
| 930 | `FORGE_TIMING_BREAKOUT_SAME_DIR_COOLDOWN_SEC` | `bb_breakout.same_dir_cooldown_seconds` | yes | no | `0` | PASS |
| 931 | `FORGE_PULLBACK_SCALP_COOLDOWN_SECONDS` | `safety.pullback_scalp_cooldown_seconds` | yes | no | `0` | PASS |
| 932 | `FORGE_TIMING_BULL_DAY_DIP_BUY_REENTRY_COOLDOWN_SEC` | `composites.bull_day_dip_buy_reentry_cooldown_sec` | yes | no | `0` | PASS |
| 933 | `FORGE_TIMING_MA_CROSSOVER_COOLDOWN_SECONDS` | `timing.ma_crossover_cooldown_seconds` | yes | no | `0` | PASS |
| 934 | `FORGE_TIMING_VWAP_REVERSION_COOLDOWN_SECONDS` | `timing.vwap_reversion_cooldown_seconds` | yes | no | `0` | PASS |
| 935 | `FORGE_TIMING_FIB_CONFLUENCE_COOLDOWN_SECONDS` | `timing.fib_confluence_cooldown_seconds` | yes | no | `0` | PASS |
| 936 | `FORGE_TIMING_INSIDE_BAR_COOLDOWN_SECONDS` | `timing.inside_bar_cooldown_seconds` | yes | no | `0` | PASS |
| 937 | `FORGE_TIMING_BB_SQUEEZE_COOLDOWN_SECONDS` | `timing.bb_squeeze_cooldown_seconds` | yes | no | `0` | PASS |
| 938 | `FORGE_TIMING_ORB_COOLDOWN_SECONDS` | `timing.orb_cooldown_seconds` | yes | no | `0` | PASS |
| 939 | `FORGE_TIMING_GAP_AND_GO_COOLDOWN_SECONDS` | `timing.gap_and_go_cooldown_seconds` | yes | no | `0` | PASS |
| 940 | `FORGE_TIMING_DOUBLE_PATTERN_COOLDOWN_SECONDS` | `timing.double_pattern_cooldown_seconds` | yes | no | `0` | PASS |
| 941 | `FORGE_TIMING_HS_COOLDOWN_SECONDS` | `timing.hs_cooldown_seconds` | yes | no | `0` | PASS |
| 942 | `FORGE_TIMING_FLAG_PENNANT_COOLDOWN_SECONDS` | `timing.flag_pennant_cooldown_seconds` | yes | no | `0` | PASS |
| 943 | `FORGE_TIMING_TRENDLINE_BOUNCE_COOLDOWN_SECONDS` | `timing.trendline_bounce_cooldown_seconds` | yes | no | `0` | PASS |
| 944 | `FORGE_TIMING_SR_FLIP_COOLDOWN_SECONDS` | `timing.sr_flip_cooldown_seconds` | yes | no | `0` | PASS |
| 949 | `FORGE_TIMING_DUMP_KZ_TIER1_MAX_MIN` | `safety.dump_kz_tier1_max_min` | yes | no | `5` | PASS |
| 950 | `FORGE_GEOMETRY_DUMP_KZ_TIER1_FACTOR` | `safety.dump_kz_tier1_factor` | yes | no | `2` | PASS |
| 951 | `FORGE_TIMING_DUMP_KZ_TIER2_MAX_MIN` | `safety.dump_kz_tier2_max_min` | yes | no | `15` | PASS |
| 952 | `FORGE_GEOMETRY_DUMP_KZ_TIER2_FACTOR` | `safety.dump_kz_tier2_factor` | yes | no | `2` | PASS |
| 953 | `FORGE_TIMING_DUMP_KZ_TIER3_MAX_MIN` | `safety.dump_kz_tier3_max_min` | yes | no | `30` | PASS |
| 954 | `FORGE_GEOMETRY_DUMP_KZ_TIER3_FACTOR` | `safety.dump_kz_tier3_factor` | yes | no | `1.5` | PASS |
| 955 | `FORGE_TIMING_DUMP_KZ_TIER4_MAX_MIN` | `safety.dump_kz_tier4_max_min` | yes | no | `60` | PASS |
| 956 | `FORGE_GEOMETRY_DUMP_KZ_TIER4_FACTOR` | `safety.dump_kz_tier4_factor` | yes | no | `1` | PASS |
| 957 | `FORGE_GEOMETRY_DUMP_KZ_TIER5_FACTOR` | `safety.dump_kz_tier5_factor` | yes | no | `0.85` | PASS |
| 958 | `FORGE_GEOMETRY_DUMP_KZ_NO_ZONE_FACTOR` | `safety.dump_kz_no_zone_factor` | yes | no | `0.5` | PASS |
| 962 | `FORGE_GEOMETRY_DUMP_SL_ATR_MULT_BUY` | `safety.dump_sl_atr_mult_buy` | yes | no | `3.5` | PASS |
| 963 | `FORGE_GEOMETRY_DUMP_SL_ATR_MULT_SELL` | `safety.dump_sl_atr_mult_sell` | yes | no | `3.5` | PASS |
| 964 | `FORGE_GEOMETRY_BB_LOWER_REVERSION_BUY_SL_ATR_MULT` | `safety.bb_lower_reversion_buy_sl_atr_mult` | yes | no | `2.5` | PASS |
| 971 | `FORGE_GEOMETRY_DUMP_TP1_ATR_MULT_BUY` | `safety.dump_tp1_atr_mult_buy` | yes | no | `0.7` | PASS |
| 972 | `FORGE_GEOMETRY_DUMP_TP1_ATR_MULT_SELL` | `safety.dump_tp1_atr_mult_sell` | yes | no | `0.7` | PASS |
| 973 | `FORGE_GEOMETRY_DUMP_TP2_ATR_MULT_BUY` | `safety.dump_tp2_atr_mult_buy` | yes | no | `2.5` | PASS |
| 974 | `FORGE_GEOMETRY_DUMP_TP2_ATR_MULT_SELL` | `safety.dump_tp2_atr_mult_sell` | yes | no | `2.5` | PASS |
| 975 | `FORGE_GEOMETRY_TREND_CONTINUATION_BUY_TP1_ATR_MULT` | `safety.trend_continuation_buy_tp1_atr_mult` | yes | no | `0.7` | PASS |
| 976 | `FORGE_GEOMETRY_TREND_CONTINUATION_BUY_TP2_ATR_MULT` | `safety.trend_continuation_buy_tp2_atr_mult` | yes | no | `1.4` | PASS |
| 977 | `FORGE_GEOMETRY_TREND_CONTINUATION_SELL_TP1_ATR_MULT` | `safety.trend_continuation_sell_tp1_atr_mult` | yes | no | `0.7` | PASS |
| 978 | `FORGE_GEOMETRY_TREND_CONTINUATION_SELL_TP2_ATR_MULT` | `safety.trend_continuation_sell_tp2_atr_mult` | yes | no | `1.4` | PASS |
| 983 | `FORGE_GEOMETRY_DUMP_PYRAMID_BASE_FACTOR` | `safety.dump_pyramid_base_factor` | yes | no | `5` | PASS |
| 984 | `FORGE_GEOMETRY_DUMP_PYRAMID_STEP` | `safety.dump_pyramid_step` | yes | no | `-1` | PASS |
| 985 | `FORGE_GEOMETRY_DUMP_PYRAMID_MAX_FACTOR` | `safety.dump_pyramid_max_factor` | yes | no | `5.0` | PASS |
| 986 | `FORGE_GEOMETRY_DUMP_PYRAMID_MIN_FACTOR` | `safety.dump_pyramid_min_factor` | yes | no | `1` | PASS |
| 992 | `FORGE_STAGED_ADD_INTERVAL_SEC` | `lot_sizing.staged_add_interval_sec` | yes | no | `5` | PASS |
| 997 | `FORGE_STAGED_ADD_MIN_FAVORABLE_POINTS` | `lot_sizing.staged_add_min_favorable_points` | yes | no | `300` | PASS |
| 1006 | `FORGE_SETUP_DIRECTION_LOCK_ENABLED` | `bb_breakout.direction_lock_enabled` | yes | no | `1` | PASS |
| 1007 | `FORGE_TIMING_DIRLOCK_BREAK_BILATERAL_COOLDOWN_BARS` | `bb_breakout.dirlock_break_bilateral_cooldown_bars` | yes | no | `2` | PASS |
| 1010 | `FORGE_TIMING_COOL_PERIOD_STRUCTURE_CANCEL_ENABLED` | `bb_breakout.structure_flip_cancel_enabled` | yes | no | `1` | PASS |
| 1013 | `FORGE_GEOMETRY_TP2_CLOSE_ENABLED` | `bb_breakout.tp2_close_enabled` | yes | no | `1` | PASS |
| 1016 | `FORGE_GEOMETRY_TP1_PIP_FLOOR` | `bb_breakout.tp1_pip_floor` | yes | no | `40` | PASS |
| 1017 | `FORGE_GEOMETRY_TP2_PIP_FLOOR` | `bb_breakout.tp2_pip_floor` | yes | no | `60` | PASS |
| 1020 | `FORGE_GEOMETRY_BATCH_SIZE` | `bb_breakout.batch_size` | yes | no | `4` | PASS |
| 1024 | `FORGE_GEOMETRY_TP3_MODE` | `bb_breakout.tp3_mode` | yes | no | `1` | PASS |
| 1025 | `FORGE_GEOMETRY_TP3_DIST_FROM_SL_ATR_MULT` | `bb_breakout.tp3_dist_from_sl_atr_mult` | yes | no | `2.0` | PASS |
| 1046 | `FORGE_BUY_STOP_CONT_ENABLED` | `bb_breakout.buy_stop_cont_enabled` | yes | no | `0` | PASS |
| 1047 | `FORGE_SELL_LIMIT_RECOVERY_ENABLED` | `bb_breakout.sell_limit_recovery_enabled` | yes | no | `1` | PASS |
| 1049 | `FORGE_SELL_LIMIT_RECOVERY_LOT_FACTOR` | `bb_breakout.sell_limit_recovery_lot_factor` | yes | no | `0.5` | PASS |
| 1050 | `FORGE_SELL_LIMIT_RECOVERY_EXPIRY_BARS` | `bb_breakout.sell_limit_recovery_expiry_bars` | yes | no | `8` | PASS |
| 1057 | `FORGE_RECOVERY_PRE_TP1_ENABLED` | `bb_breakout.recovery_pre_tp1_enabled` | yes | no | `1` | PASS |
| 1058 | `FORGE_RECOVERY_PRE_TP1_MIN_ADVERSE_ATR` | `bb_breakout.recovery_pre_tp1_min_adverse_atr` | yes | no | `1.5` | PASS |
| 1059 | `FORGE_RECOVERY_PRE_TP1_MAX_LEGS_PER_GROUP` | `bb_breakout.recovery_pre_tp1_max_legs_per_group` | yes | no | `1` | PASS |
| 1060 | `FORGE_RECOVERY_PRE_TP1_COOLDOWN_SECONDS` | `bb_breakout.recovery_pre_tp1_cooldown_seconds` | yes | no | `600` | PASS |
| 1063 | `FORGE_GEOMETRY_CASCADE_RECOVERY_TP_ATR_MULT` | `bb_breakout.cascade_recovery_tp_atr_mult` | yes | no | `2.0` | PASS |
| 1084 | `FORGE_COMPOSITE_DTC_ENABLED` | `safety.dtc_enabled` | yes | no | `1` | PASS |
| 1085 | `FORGE_COMPOSITE_DTC_PEMCG_MODIFIER_ENABLED` | `safety.dtc_pemcg_modifier_enabled` | yes | no | `1` | PASS |
| 1086 | `FORGE_COMPOSITE_DTC_DAY_BIAS_BLOCK_ENABLED` | `safety.dtc_day_bias_block_enabled` | yes | no | `1` | PASS |
| 1087 | `FORGE_COMPOSITE_DTC_5STATE_ENABLED` | `safety.dtc_5state_enabled` | yes | no | `1` | PASS |
| 1090 | `FORGE_GATE_DTC_H4_TREND_MIN_AGREEMENT` | `safety.dtc_h4_trend_min_agreement` | yes | no | `0.5` | PASS |
| 1091 | `FORGE_GATE_DTC_BLOCK_COUNTER_TREND_BUYS` | `safety.dtc_block_counter_trend_buys` | yes | no | `1` | PASS |
| 1092 | `FORGE_GATE_DTC_BLOCK_COUNTER_TREND_SELLS` | `safety.dtc_block_counter_trend_sells` | yes | no | `1` | PASS |
| 1096 | `FORGE_GATE_DTC_VWAP_DIST_ATR_THRESHOLD` | `safety.dtc_vwap_dist_atr_threshold` | yes | no | `1.5` | PASS |
| 1098 | `FORGE_GATE_DTC_M15_ADX_MIN` | `safety.dtc_m15_adx_min` | yes | no | `25` | PASS |
| 1100 | `FORGE_GATE_DTC_H1_DI_DOMINANCE_MIN` | `safety.dtc_h1_di_dominance_min` | yes | no | `5.0` | PASS |
| 1102 | `FORGE_GATE_DTC_PEMCG_BYPASS_ATOMS` | `safety.dtc_pemcg_bypass_atoms` | yes | no | `2` | PASS |
| 1104 | `FORGE_GATE_DTC_EXEMPT_BUY_SETUPS` | `safety.dtc_exempt_buy_setups` | yes | no | `BB_EXHAUSTION_REVERSAL_BUY` | PASS |
| 1106 | `FORGE_GATE_DTC_EXEMPT_SELL_SETUPS` | `safety.dtc_exempt_sell_setups` | yes | no | `FRACTIONAL_SELL_IN_BULL,BB_EXHAUSTION_REVERSAL_SELL` | PASS |
| 1116 | `FORGE_TIMING_STRUCTURE_CANCEL_INCLUDES_BREAKOUT_L1L2` | `bb_breakout.structure_cancel_includes_breakout_l1l2` | yes | no | `1` | PASS |
| 1118 | `FORGE_TIMING_PENDING_PRE_TRIGGER_STRUCT_CANCEL_ENABLED` | `bb_breakout.pending_pre_trigger_struct_cancel_enabled` | yes | no | `1` | PASS |
| 1129 | `FORGE_COMPOSITE_DTC_GEOMETRY_WIDEN_ENABLED` | `safety.dtc_geometry_widen_enabled` | yes | no | `1` | PASS |
| 1131 | `FORGE_GEOMETRY_DTC_TREND_ALIGNED_SL_WIDEN_FACTOR` | `safety.dtc_trend_aligned_sl_widen_factor` | yes | no | `2` | PASS |
| 1133 | `FORGE_GEOMETRY_DTC_TREND_ALIGNED_TP_WIDEN_FACTOR` | `safety.dtc_trend_aligned_tp_widen_factor` | yes | no | `3` | PASS |
| 1141 | `FORGE_BREAKOUT_TP4_STAGING_ENABLED` | `bb_breakout.tp4_staging_enabled` | yes | no | `1` | PASS |
| 1143 | `FORGE_BREAKOUT_TP4_MIN_ADX` | `bb_breakout.tp4_min_adx` | yes | no | `25` | PASS |
| 1144 | `FORGE_BREAKOUT_TP5_STAGING_ENABLED` | `bb_breakout.tp5_staging_enabled` | yes | no | `1` | PASS |
| 1146 | `FORGE_BREAKOUT_TP5_MIN_ADX` | `bb_breakout.tp5_min_adx` | yes | no | `30` | PASS |
| 1159 | `FORGE_COMPOSITE_DTC_EXEMPT_OVERRIDE_ENABLED` | `safety.dtc_exempt_override_enabled` | yes | no | `1` | PASS |
| 1161 | `FORGE_GATE_DTC_EXEMPT_OVERRIDE_SELL_RSI_MIN` | `safety.dtc_exempt_override_sell_rsi_min` | yes | no | `75.0` | PASS |
| 1163 | `FORGE_GATE_DTC_EXEMPT_OVERRIDE_BUY_RSI_MAX` | `safety.dtc_exempt_override_buy_rsi_max` | yes | no | `25.0` | PASS |
| 1164 | `FORGE_GATE_DTC_EXEMPT_OVERRIDE_BUY_SETUPS` | `safety.dtc_exempt_override_buy_setups` | yes | no | `BB_EXHAUSTION_REVERSAL_BUY` | PASS |
| 1165 | `FORGE_GATE_DTC_EXEMPT_OVERRIDE_SELL_SETUPS` | `safety.dtc_exempt_override_sell_setups` | yes | no | `BB_EXHAUSTION_REVERSAL_SELL` | PASS |
| 1179 | `FORGE_COMPOSITE_ISS_ENABLED` | `safety.iss_enabled` | yes | no | `1` | PASS |
| 1181 | `FORGE_GATE_ISS_MIN_THRESHOLD` | `safety.iss_min_threshold` | yes | no | `5` | PASS |
| 1183 | `FORGE_GATE_ISS_BLOCK_BELOW_THRESHOLD` | `safety.iss_block_below_threshold` | yes | no | `0` | PASS |
| 1187 | `FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED` | `safety.iss_c_override_pemcg_enabled` | yes | no | `0` | PASS |
| 1189 | `FORGE_GATE_ISS_WEIGHT_MSS` | `safety.iss_weight_mss` | yes | no | `5` | PASS |
| 1191 | `FORGE_GATE_ISS_WEIGHT_FVG` | `safety.iss_weight_fvg` | yes | no | `3` | PASS |
| 1193 | `FORGE_GATE_ISS_WEIGHT_CHOCH_SUPPORT` | `safety.iss_weight_choch_support` | yes | no | `2` | PASS |
| 1195 | `FORGE_TIMING_ISS_FVG_MAX_AGE_BARS` | `safety.iss_fvg_max_age_bars` | yes | no | `12` | PASS |
| 1197 | `FORGE_GATE_ISS_FVG_MAX_FILL_PCT` | `safety.iss_fvg_max_fill_pct` | yes | no | `0.5` | PASS |
| 1212 | `FORGE_ICT_MSS_ENABLED` | `safety.ict_mss_enabled` | yes | no | `1` | PASS |
| 1216 | `FORGE_ICT_FVG_ENABLED` | `safety.ict_fvg_enabled` | yes | no | `1` | PASS |
| 1218 | `FORGE_ICT_SWING_LOOKBACK` | `safety.ict_swing_lookback` | yes | no | `3` | PASS |
| 1221 | `FORGE_ICT_MSS_DISPLACEMENT_ATR_MULT` | `safety.ict_mss_displacement_atr_mult` | yes | no | `0.5` | PASS |
| 1224 | `FORGE_ICT_FVG_MIN_SIZE_ATR_MULT` | `safety.ict_fvg_min_size_atr_mult` | yes | no | `0.15` | PASS |
| 1230 | `FORGE_ICT_CHOCH_ENABLED` | `safety.ict_choch_enabled` | yes | no | `1` | PASS |
| 1231 | `FORGE_ICT_LIQUIDITY_SWEEP_ENABLED` | `safety.ict_liquidity_sweep_enabled` | yes | no | `1` | PASS |
| 1236 | `FORGE_ICT_ATOM_KILLZONE_FAVORABLE_ENABLED` | `safety.ict_atom_killzone_favorable_enabled` | yes | no | `1` | PASS |
| 1237 | `FORGE_ICT_ATOM_HTF_ALIGNED_ENABLED` | `safety.ict_atom_htf_aligned_enabled` | yes | no | `1` | PASS |
| 1249 | `FORGE_JOURNAL_SIGNALS_BATCH_TXN` | `journal.journal_signals_batch_txn` | yes | no | `1` | PASS |
| 1251 | `FORGE_JOURNAL_WAL_MODE` | `journal.journal_wal_mode` | yes | no | `1` | PASS |
| 1253 | `FORGE_JOURNAL_SYNCHRONOUS_NORMAL` | `journal.journal_synchronous_normal` | yes | no | `1` | PASS |

## Mandatory Check B — Gate legend completeness
**Result**: PASS. Enumerated 0 literal codes and 103 Filter_* constructed codes; all emitted codes have a legend key or wildcard pattern.

| Gate code | Source class | EA file:line | Legend match | Status |
|---|---|---|---|---|
| `asia_capitulation_buy_atoms_below_min` | literal | ea/FORGE.mq5:12012 | key | PASS |
| `asia_capitulation_buy_cooldown` | literal | ea/FORGE.mq5:12015 | key | PASS |
| `bb_breakout_buy_below_band` | literal | ea/FORGE.mq5:12348 | key | PASS |
| `bb_breakout_buy_exhaustion_no_bos` | literal | ea/FORGE.mq5:12152 | key | PASS |
| `bb_breakout_buy_vwap_overextended` | literal | ea/FORGE.mq5:12170 | key | PASS |
| `bb_breakout_sell_above_band` | literal | ea/FORGE.mq5:12709 | key | PASS |
| `bb_breakout_sell_vwap_overextended` | literal | ea/FORGE.mq5:12458 | key | PASS |
| `bb_pullback_buy_falling_velocity_block` | literal | ea/FORGE.mq5:11796 | key | PASS |
| `bb_squeeze_adx_below_min` | Filter_AdxFloor | ea/FORGE.mq5:13650 | key | PASS |
| `bb_squeeze_cooldown` | Filter_Cooldown | ea/FORGE.mq5:13652 | key | PASS |
| `blr_buy_bearish_bos_block` | literal | ea/FORGE.mq5:13201 | key | PASS |
| `blr_buy_falling_velocity_block` | literal | ea/FORGE.mq5:13206 | key | PASS |
| `cooldown` | literal | ea/FORGE.mq5:11373 | key | PASS |
| `direction_cooldown` | literal | ea/FORGE.mq5:14129 | key | PASS |
| `double_bottom_adx_below_min` | Filter_AdxFloor | ea/FORGE.mq5:13951 | key | PASS |
| `double_bottom_cooldown` | Filter_Cooldown | ea/FORGE.mq5:13953 | key | PASS |
| `double_top_adx_below_min` | Filter_AdxFloor | ea/FORGE.mq5:13924 | key | PASS |
| `double_top_cooldown` | Filter_Cooldown | ea/FORGE.mq5:13926 | key | PASS |
| `dump_adx_block` | literal | ea/FORGE.mq5:12834 | key | PASS |
| `dump_bar_confirm_missing` | literal | ea/FORGE.mq5:12801 | key | PASS |
| `dump_below_bbl_block_sell` | literal | ea/FORGE.mq5:12887 | key | PASS |
| `dump_chop_block` | literal | ea/FORGE.mq5:12862 | key | PASS |
| `dump_cooldown` | literal | ea/FORGE.mq5:12854 | key | PASS |
| `dump_d1_bias_block` | literal | ea/FORGE.mq5:12846 | key | PASS |
| `dump_h1_trend_block_sell` | literal | ea/FORGE.mq5:12820 | key | PASS |
| `dump_judas_window` | literal | ea/FORGE.mq5:12901 | key | PASS |
| `dump_psar_block` | literal | ea/FORGE.mq5:12840 | key | PASS |
| `dump_rsi_block` | literal | ea/FORGE.mq5:12827 | key | PASS |
| `dump_rsi_buy_ceil` | literal | ea/FORGE.mq5:12983 | key | PASS |
| `dump_rsi_floor_sell` | literal | ea/FORGE.mq5:12873 | key | PASS |
| `entry_quality_adx_extreme_sell` | literal | ea/FORGE.mq5:12439 | key | PASS |
| `entry_quality_adx_min_sell` | literal | ea/FORGE.mq5:12446 | key | PASS |
| `entry_quality_adx_spike_sell` | literal | ea/FORGE.mq5:12533 | key | PASS |
| `entry_quality_atr` | literal | ea/FORGE.mq5:11100 | key | PASS |
| `entry_quality_atr_ext` | literal | ea/FORGE.mq5:14647 | key | PASS |
| `entry_quality_bb_contraction` | literal | ea/FORGE.mq5:11158 | key | PASS |
| `entry_quality_body` | literal | ea/FORGE.mq5:11131 | key | PASS |
| `entry_quality_breakout_cooldown` | literal | ea/FORGE.mq5:12261 | key | PASS |
| `entry_quality_breakout_failed` | literal | ea/FORGE.mq5:12305 | key | PASS |
| `entry_quality_breakout_failed_samebar` | literal | ea/FORGE.mq5:12285 | key | PASS |
| `entry_quality_chop_block_sell` | literal | ea/FORGE.mq5:11845 | key | PASS |
| `entry_quality_daily_bear_block_buy` | literal | ea/FORGE.mq5:11749 | key | PASS |
| `entry_quality_daily_bull_block_sell` | literal | ea/FORGE.mq5:11853 | key | PASS |
| `entry_quality_direction` | literal | ea/FORGE.mq5:11143 | key | PASS |
| `entry_quality_direction_cap` | literal | ea/FORGE.mq5:11092 | key | PASS |
| `entry_quality_h1_di_buy` | literal | ea/FORGE.mq5:12181 | key | PASS |
| `entry_quality_h1_di_sell` | literal | ea/FORGE.mq5:12479 | key | PASS |
| `entry_quality_h1_macd_buy` | literal | ea/FORGE.mq5:12242 | key | PASS |
| `entry_quality_h1_macd_sell` | literal | ea/FORGE.mq5:12608 | key | PASS |
| `entry_quality_h4_adx_buy_blocked` | literal | ea/FORGE.mq5:12224 | key | PASS |
| `entry_quality_h4_adx_sell_blocked` | literal | ea/FORGE.mq5:12656 | key | PASS |
| `entry_quality_h4_rsi_buy_blocked` | literal | ea/FORGE.mq5:12215 | key | PASS |
| `entry_quality_h4_rsi_sell_blocked` | literal | ea/FORGE.mq5:12644 | key | PASS |
| `entry_quality_hid_bull_div_sell` | literal | ea/FORGE.mq5:12567 | key | PASS |
| `entry_quality_intraday_reversal_buy_block` | literal | ea/FORGE.mq5:11741 | key | PASS |
| `entry_quality_m30_not_bearish` | literal | ea/FORGE.mq5:12630 | key | PASS |
| `entry_quality_news_filter` | literal | ea/FORGE.mq5:11069 | key | PASS |
| `entry_quality_news_rsi_tighten` | literal | ea/FORGE.mq5:11648 | key | PASS |
| `entry_quality_psar_misalign_buy` | literal | ea/FORGE.mq5:11803 | key | PASS |
| `entry_quality_psar_misalign_sell` | literal | ea/FORGE.mq5:11888 | key | PASS |
| `entry_quality_rsi_buy_ceil` | literal | ea/FORGE.mq5:12130 | key | PASS |
| `entry_quality_rsi_rising_sell` | literal | ea/FORGE.mq5:12551 | key | PASS |
| `entry_quality_session_sell_cutoff` | literal | ea/FORGE.mq5:12426 | key | PASS |
| `execution_failed` | literal | ea/FORGE.mq5:15350 | key | PASS |
| `fib_confluence_cooldown` | Filter_Cooldown | ea/FORGE.mq5:13581 | key | PASS |
| `flag_pennant_adx_below_min` | Filter_AdxFloor | ea/FORGE.mq5:14031 | key | PASS |
| `flag_pennant_cooldown` | Filter_Cooldown | ea/FORGE.mq5:14033 | key | PASS |
| `gap_and_go_cooldown` | Filter_Cooldown | ea/FORGE.mq5:13722 | key | PASS |
| `head_and_shoulders_adx_below_min` | Filter_AdxFloor | ea/FORGE.mq5:13977 | key | PASS |
| `head_and_shoulders_cooldown` | Filter_Cooldown | ea/FORGE.mq5:13979 | key | PASS |
| `inside_bar_adx_below_min` | Filter_AdxFloor | ea/FORGE.mq5:13613 | key | PASS |
| `inside_bar_cooldown` | Filter_Cooldown | ea/FORGE.mq5:13616 | key | PASS |
| `inverse_head_and_shoulders_adx_below_min` | Filter_AdxFloor | ea/FORGE.mq5:14003 | key | PASS |
| `inverse_head_and_shoulders_cooldown` | Filter_Cooldown | ea/FORGE.mq5:14005 | key | PASS |
| `killzone_trade_cap` | literal | ea/FORGE.mq5:11302 | key | PASS |
| `kz_warmup` | literal | ea/FORGE.mq5:11319 | key | PASS |
| `m1` | literal | ea/FORGE.mq5:14140 | key | PASS |
| `ma_crossover_adx_below_min` | Filter_AdxFloor | ea/FORGE.mq5:13509 | key | PASS |
| `ma_crossover_cooldown` | Filter_Cooldown | ea/FORGE.mq5:13514 | key | PASS |
| `ma_crossover_m15_misalign` | Filter_M15TrendAligned | ea/FORGE.mq5:13512 | key | PASS |
| `no_setup` | literal | ea/FORGE.mq5:14628 | key | PASS |
| `open_group_` | literal | ea/FORGE.mq5:16997 | pattern `open_group_*` | PASS |
| `open_group_bad_stoplimit_price` | literal | ea/FORGE.mq5:17142 | pattern `open_group_*` | PASS |
| `open_group_bad_stoplimit_trigger` | literal | ea/FORGE.mq5:17137 | pattern `open_group_*` | PASS |
| `open_group_invalid_stops` | literal | ea/FORGE.mq5:17054 | key | PASS |
| `open_group_missing_stoplimit` | literal | ea/FORGE.mq5:17131 | pattern `open_group_*` | PASS |
| `open_group_rr_below_floor` | literal | ea/FORGE.mq5:17047 | key | PASS |
| `open_group_unsupported_order_type` | literal | ea/FORGE.mq5:17009 | pattern `open_group_*` | PASS |
| `open_groups` | literal | ea/FORGE.mq5:11353 | key | PASS |
| `orb_adx_below_min` | Filter_AdxFloor | ea/FORGE.mq5:13686 | key | PASS |
| `orb_cooldown` | Filter_Cooldown | ea/FORGE.mq5:13688 | key | PASS |
| `post_sl_cooldown` | literal | ea/FORGE.mq5:14133 | key | PASS |
| `regime_countertrend` | literal | ea/FORGE.mq5:14148 | key | PASS |
| `rr_too_low` | literal | ea/FORGE.mq5:14740 | key | PASS |
| `session_off` | literal | ea/FORGE.mq5:11283 | key | PASS |
| `session_trade_cap` | literal | ea/FORGE.mq5:11363 | key | PASS |
| `spread` | literal | ea/FORGE.mq5:11345 | key | PASS |
| `sr_flip_adx_below_min` | Filter_AdxFloor | ea/FORGE.mq5:14101 | key | PASS |
| `sr_flip_cooldown` | Filter_Cooldown | ea/FORGE.mq5:14103 | key | PASS |
| `trendline_bounce_adx_below_min` | Filter_AdxFloor | ea/FORGE.mq5:14067 | key | PASS |
| `trendline_bounce_cooldown` | Filter_Cooldown | ea/FORGE.mq5:14069 | key | PASS |
| `vwap_reversion_cooldown` | Filter_Cooldown | ea/FORGE.mq5:13549 | key | PASS |
| `warmup_` | literal | ea/FORGE.mq5:11387 | pattern `warmup_*` | PASS |

## Mandatory Check C — Sync mapping ↔ .env.example parity
**Result**: FAIL. Mapping count=697; .env.example count=702.

| Direction | Key | Status | Evidence |
|---|---|---|---|
| sync→example | `FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED` | FAIL | mapped at `scripts/sync_scalper_config_from_env.py:259`; no `# FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED=` in `.env.example` |
| example→sync | `FORGE_MAGIC_MAX` | WARNING | documented in `.env.example`; consumed outside sync or MT5/bridge direct (`python/bridge.py:121-122,169,340-341`; whitelist at `tests/api/test_forge_27x_gates.py:324`) |
| example→sync | `FORGE_MAGIC_NUMBER` | WARNING | documented in `.env.example`; consumed outside sync or MT5/bridge direct (`python/bridge.py:121-122,169,340-341`; whitelist at `tests/api/test_forge_27x_gates.py:324`) |
| example→sync | `FORGE_NUM_TRADES` | WARNING | documented in `.env.example`; consumed outside sync or MT5/bridge direct (`python/bridge.py:121-122,169,340-341`; whitelist at `tests/api/test_forge_27x_gates.py:324`) |
| example→sync | `FORGE_QUEUE_ACK_TIMEOUT_SEC` | WARNING | documented in `.env.example`; consumed outside sync or MT5/bridge direct (`python/bridge.py:121-122,169,340-341`; whitelist at `tests/api/test_forge_27x_gates.py:324`) |
| example→sync | `FORGE_QUEUE_MAX_RETRIES` | WARNING | documented in `.env.example`; consumed outside sync or MT5/bridge direct (`python/bridge.py:121-122,169,340-341`; whitelist at `tests/api/test_forge_27x_gates.py:324`) |
| example→sync | `FORGE_SCALPER_MODE` | WARNING | documented in `.env.example`; consumed outside sync or MT5/bridge direct (`python/bridge.py:121-122,169,340-341`; whitelist at `tests/api/test_forge_27x_gates.py:324`) |

## Mandatory Check D — SIGNALS schema ↔ aurum_tester ↔ scribe sync parity
**Result**: PASS. `forge_signals INSERT: column_list=158 placeholder_count=158 match=True`.

| Check | Evidence | Status | Notes |
|---|---|---|---|
| EA SIGNALS schema | `ea/FORGE.mq5:9591-9704` | PASS | CREATE TABLE includes current SIGNALS columns, including v2.7.123/v2.7.124 atom/score columns. |
| scribe CREATE TABLE | `python/scribe.py:119-280` | PASS | Fresh `forge_signals` schema mirrors current atom columns. |
| scribe ALTER migrations | `python/scribe.py:784-1030` | PASS | macd_histogram, m15_adx, lot_factor, RegimeState, ICT, atom and score migrations exist. |
| scribe INSERT columns/placeholders | `python/scribe.py:1706-1797` | PASS | 158 columns and 158 placeholders. SQLite requires the values count to match the explicit column list: https://www.sqlite.org/lang_insert.html. |
| JournalRecordSignal signature | `ea/FORGE.mq5:9710-9779` | PASS | Active signature feeds the SIGNALS INSERT path and scribe SELECT/INSERT lists include appended telemetry. |

## Section 1 — BB_BREAKOUT BUY Gates
| # | Gate | EA file:line | Config key=value | Status | Notes |
|---:|---|---|---|---|---|
| 1 | BB close above upper band | ea/FORGE.mq5:12101-12104 | n/a | PASS | prev_close > m5_bb_u + breakout_buffer |
| 2 | M5 RSI > rsi_buy_min | ea/FORGE.mq5:12101-12104 | bb_breakout.rsi_buy_min=40 | PASS | active config line 36 |
| 3 | M5 RSI < rsi_buy_ceil | ea/FORGE.mq5:12124-12131 | bb_breakout.rsi_buy_ceil=78 | PASS | doc matches active config |
| 4 | M5 trend bullish | ea/FORGE.mq5:12085,12103-12104 | EMA trend threshold | PASS | m5_bull required |
| 5 | M15 flat or bullish | ea/FORGE.mq5:12087-12091,12103-12104 | bb_breakout.require_m15_agree=true | PASS | m15_ok_buy required |
| 6 | H1/H4/high-vol alignment | ea/FORGE.mq5:12092-12094,12103-12104 | high_vol_require_h1_h4_breakout_align=1 | PASS | doc only mentions H1; active also requires H4 in high-vol |
| 7 | H1 DI BUY weak-ADX gate | ea/FORGE.mq5:12174-12182 | require_h1_di_buy=1; counter_buy_adx_threshold=28 | PASS | DI+ must exceed DI- when ADX<28 |
| 8 | OsMA Q0 BUY gate | ea/FORGE.mq5:12187-12204 | require_macd_buy=1 | PASS | positive and rising only |
| 9 | Re-entry ATR extension | ea/FORGE.mq5:14633-14648 | max_reentry_atr_ext=2 | PASS | logs entry_quality_atr_ext |

## Section 2 — BB_BREAKOUT SELL Gates
| # | Gate | EA file:line | Config key=value | Status | Notes |
|---:|---|---|---|---|---|
| 1 | BB close below lower band | ea/FORGE.mq5:12388-12395 | n/a | PASS | prev_close < lower band - buffer |
| 2 | M5 RSI < rsi_sell_max | ea/FORGE.mq5:12388-12395 | bb_breakout.rsi_sell_max=60 | PASS | doc matches active |
| 3 | M5 RSI floor | ea/FORGE.mq5:12495-12518 | rsi_sell_floor=33; weak floor default 36 | WARNING | intent doc says base 30; active config is 33 |
| 4 | SELL ADX floor | ea/FORGE.mq5:12430-12448 | adx_min_sell=25 | PASS | M5 ADX floor |
| 5 | ADX lookback spike gate | ea/FORGE.mq5:12523-12535 | lookback=6 | PASS | skipped by crash bypass |
| 6 | M15 ADX extreme block | ea/FORGE.mq5:12430-12440 | adx_sell_block_threshold=55 | PASS | uses M15 ref when available |
| 7 | H1 DI SELL gate | ea/FORGE.mq5:12470-12480 | require_h1_di_sell=1 | PASS | no ADX bypass |
| 8 | M5/M15/H1/H4 trend alignment | ea/FORGE.mq5:12388-12395 | require_m15_agree=true; min_h1_bear_strength=0.2 | PASS | SELL requires bear trend stack |
| 9 | OsMA Q2 SELL gate | ea/FORGE.mq5:12572-12589 | require_macd_sell=1 | PASS | negative and falling only |
| 10 | M30 bearish confirmation | ea/FORGE.mq5:12615-12631 | require_m30_bear_sell=1; m30_bear_adx_min=25 | PASS | EMA20 < EMA50 |
| 11 | RSI declining SELL | ea/FORGE.mq5:12539-12552 | require_rsi_declining_sell=1 | PASS | auto-off at ADX>=40 or strong H1 bear |
| 12 | H1 MACD SELL optional | ea/FORGE.mq5:12595-12610 | require_h1_macd_sell=0 | PASS | disabled active |
| 13 | HID_BULL block | ea/FORGE.mq5:12557-12568 | block_hid_bull_sell=1 | PASS | active bb_breakout section is 1 |
| 14 | SELL session cutoff | ea/FORGE.mq5:12417-12427 | session_ny_sell_cutoff_utc=0 | WARNING | implemented but disabled active |

## Section 3 — Full Lot Path
| Factor | BUY ADX=38 | SELL ADX=38 | EA line | Status |
|---|---|---|---|---|
| `inside_band_factor` | 1.0 | 1.0 only if price remains below BB lower; else 0.25 | `ea/FORGE.mq5:14851-14857`; config `config/scalper_config.json:165` | PASS |
| `near_floor_factor` | 1.0 | 0.25 only in crash-bypass RSI 20-25 zone | `ea/FORGE.mq5:14859-14867`; config `config/scalper_config.json:347` | PASS |
| `stack_factor` | 1.0 first group; 0.25 additional same-dir | same | `ea/FORGE.mq5:14869-14875`; config `config/scalper_config.json:348` | PASS |
| `adx_lot_factor` | 1.0 | M15 ADX 38 uses mid factor 1.0; M15 ADX >=45 uses 0.5 | `ea/FORGE.mq5:14877-14892`; config `config/scalper_config.json:351-355` | PASS |
| `bounce_factor` | n/a for breakout | n/a for breakout | `ea/FORGE.mq5:14894-14896` | PASS |
| combined floor | min 0.125 factor | min 0.125 factor | `ea/FORGE.mq5:15128-15129` | PASS |

## Section 4 — ADX-Conditional Leg Count
| Check | EA file:line | Status | Notes |
|---|---|---|---|
| ADX <25 trims base_n by 1 | `ea/FORGE.mq5:14786-14794` | PASS | Matches intent. |
| ADX 35 to sell-block threshold adds 2 | `ea/FORGE.mq5:14791-14797` | PASS | Uses active `adx_sell_block_threshold=55`. |
| Breakout setup bonus in resolver | `ea/FORGE.mq5:17228-17231` | PASS | Adds one for setup name containing BREAKOUT. |
| HTF unclear cap | `ea/FORGE.mq5:14811-14840` | PASS | Active cap `native_legs_max_when_unclear=5`. |
| Gold SELL cap | `ea/FORGE.mq5:14841-14847` | PASS | Active `gold_native_max_sell_legs=10`. |
| Initial staging n-1 bug | `ea/FORGE.mq5:15270-15287` | PASS | `wave1=MathMin(init_cap,n)`; no forced n-1 holdback. |

## Section 5 — TP3 Live Staging
| Check | EA file:line | Status | Notes |
|---|---|---|---|
| TP3 registered on breakout groups | `ea/FORGE.mq5:15373-15382` | PASS | Active `tp3_atr_mult=5`; doc still says 2.5, WARNING drift from intent. |
| TP2 hit promotes runners to TP3 | `ea/FORGE.mq5:3513-3600` | PASS | Sets `tp2_hit=true` after promotion. |
| TP3 mode dynamic extension | `ea/FORGE.mq5:3741-3756` | PASS | Active `tp3_mode=1` extends TP with SL trail. |

## Section 6 — Direction-Split TP1
| Check | EA file:line | Status | Notes |
| BUY TP1 multiplier | `ea/FORGE.mq5:12365-12367` | PASS | Uses `tp1_buy_atr_mult=0.5`, fallback to generic. |
| SELL TP1 multiplier | `ea/FORGE.mq5:12720-12722` | PASS | Uses `tp1_sell_atr_mult=0.4`, fallback to generic. |
| Active TP1 close pct | `ea/FORGE.mq5:15203-15204`; `config/scalper_config.json:56` | WARNING | Active is 70, while `.env:196` says 60; config wins at runtime. |

## Section 7 — Crash-Sell Bypass
| Condition | EA file:line | Config key=value | Status |
| H1 and H4 bearish | `ea/FORGE.mq5:12495` | computed trend booleans | PASS |
| RSI > 20 | `ea/FORGE.mq5:12495-12497` | `h1h4_crash_sell_rsi_min=20` | PASS |
| M5 ADX <= 40 | `ea/FORGE.mq5:12495-12498` | `h1h4_crash_sell_adx_max=40` | PASS |
| M15 ADX >= 25 | `ea/FORGE.mq5:12489-12498` | `h1h4_crash_sell_min_m15_adx=25` | PASS |
| H1 DI SELL still applies | `ea/FORGE.mq5:12470-12484` | `require_h1_di_sell=1` | PASS |

## Section 8 — Variable Integrity
**Result**: FAIL. All 435 active `FORGE_*` vars are mapped/whitelisted, but 16 mapped `.env` values do not match the active runtime config. Active runtime is still `config/scalper_config.json`.

| FORGE_ Variable | In sync script | In .env.example | Config value (active) | Default value | Status |
|---|---|---|---|---|---|
| `FORGE_BOUNCE_ADX_MAX` | yes | yes | `30` | `50` | PASS |
| `FORGE_BOUNCE_LOT_FACTOR` | yes | yes | `0.25` | `1.0` | PASS |
| `FORGE_BREAKOUT_ADX_MIN` | yes | yes | `20` | `14` | PASS |
| `FORGE_BREAKOUT_ADX_SELL_BLOCK_THRESHOLD` | yes | yes | `55` | `None` | PASS |
| `FORGE_BREAKOUT_ATR_TRAIL_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_GEOMETRY_BATCH_SIZE` | yes | yes | `4` | `1` | PASS |
| `FORGE_BREAKOUT_BE_CUSHION_ATR_MULT` | yes | yes | `1.5` | `0.0` | PASS |
| `FORGE_GATE_BREAKOUT_HID_BULL_DIV_BLOCK_SELL` | yes | yes | `1` | `None` | PASS |
| `FORGE_BUY_LIMIT_RECOVERY_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_BUY_LIMIT_RECOVERY_EXPIRY_BARS` | yes | yes | `8` | `4` | PASS |
| `FORGE_BUY_LIMIT_RECOVERY_LOT_FACTOR` | yes | yes | `0.5` | `0.25` | PASS |
| `FORGE_BREAKOUT_BUY_SL_ATR_MULT` | yes | yes | `3` | `0.0` | PASS |
| `FORGE_SETUP_DIRECTION_LOCK_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_TIMING_DIRLOCK_BREAK_BILATERAL_COOLDOWN_BARS` | yes | yes | `2` | `0` | PASS |
| `FORGE_BREAKOUT_FAILED_GATE_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_BREAKOUT_FAILED_MIN_PEAK_RSI` | yes | yes | `68` | `75.0` | PASS |
| `FORGE_BREAKOUT_FAILED_SAME_BAR_HARD_BLOCK` | yes | yes | `1` | `0` | PASS |
| `FORGE_BREAKOUT_MAX_REENTRY_ATR_EXT` | yes | yes | `2` | `0.0` | PASS |
| `FORGE_TIMING_PENDING_PRE_TRIGGER_STRUCT_CANCEL_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_RECOVERY_PRE_TP1_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_BREAKOUT_REQUIRE_H1_DI_BUY` | yes | yes | `1` | `0` | PASS |
| `FORGE_BREAKOUT_REQUIRE_H1_DI_SELL` | yes | yes | `1` | `0` | PASS |
| `FORGE_BREAKOUT_REQUIRE_MACD_BUY` | yes | yes | `1` | `0` | PASS |
| `FORGE_BREAKOUT_REQUIRE_PSAR_ALIGN` | yes | yes | `1` | `0` | PASS |
| `FORGE_BREAKOUT_REQUIRE_RSI_DECLINING_SELL` | yes | yes | `1` | `None` | PASS |
| `FORGE_BREAKOUT_RSI_BUY_CEIL` | yes | yes | `78` | `70` | PASS |
| `FORGE_BREAKOUT_RSI_SELL_FLOOR` | yes | yes | `33` | `30` | PASS |
| `FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR` | yes | yes | `0.25` | `None` | PASS |
| `FORGE_SELL_LIMIT_RECOVERY_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_SELL_LIMIT_RECOVERY_EXPIRY_BARS` | yes | yes | `8` | `4` | PASS |
| `FORGE_SELL_LIMIT_RECOVERY_LOT_FACTOR` | yes | yes | `0.5` | `0.25` | PASS |
| `FORGE_SELL_STOP_CONT_REQUIRE_TREND_REGIME` | yes | yes | `1` | `0` | PASS |
| `FORGE_GEOMETRY_SELL_STOP_CONT_SL_ATR_MULT` | yes | yes | `3.5` | `1.5` | PASS |
| `FORGE_TIMING_STRUCTURE_CANCEL_INCLUDES_BREAKOUT_L1L2` | yes | yes | `1` | `0` | PASS |
| `FORGE_TIMING_COOL_PERIOD_STRUCTURE_CANCEL_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_BREAKOUT_TP1_ATR_MULT` | yes | yes | `0.4` | `1.0` | PASS |
| `FORGE_BREAKOUT_TP1_BUY_ATR_MULT` | yes | yes | `0.5` | `0.0` | PASS |
| `FORGE_BREAKOUT_TP1_CLOSE_PCT` | yes | yes | `70` | `40` | PASS |
| `FORGE_GEOMETRY_TP1_PIP_FLOOR` | yes | yes | `40` | `0.0` | PASS |
| `FORGE_BREAKOUT_TP1_SELL_ATR_MULT` | yes | yes | `0.4` | `0.0` | PASS |
| `FORGE_BREAKOUT_TP2_ATR_MULT` | yes | yes | `1` | `1.5` | PASS |
| `FORGE_GEOMETRY_TP2_CLOSE_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_GEOMETRY_TP2_PIP_FLOOR` | yes | yes | `60` | `0.0` | PASS |
| `FORGE_BREAKOUT_TP2_SL_RATCHET_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_BREAKOUT_TP3_ATR_MULT` | yes | yes | `5` | `2.5` | PASS |
| `FORGE_GEOMETRY_TP3_MODE` | yes | yes | `1` | `0` | PASS |
| `FORGE_BREAKOUT_TP4_STAGING_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_BREAKOUT_TP5_STAGING_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_GATE_ASIA_CAPITULATION_BUY_ATR_RATIO_MIN` | yes | yes | `1.1` | `None` | PASS |
| `FORGE_TIMING_ASIA_CAPITULATION_BUY_COOLDOWN_SEC` | yes | yes | `1800` | `None` | PASS |
| `FORGE_GATE_ASIA_CAPITULATION_BUY_DISPLACEMENT_MIN_ATR` | yes | yes | `1` | `None` | PASS |
| `FORGE_SETUP_ASIA_CAPITULATION_BUY_ENABLED` | yes | yes | `1` | `None` | PASS |
| `FORGE_GEOMETRY_ASIA_CAPITULATION_BUY_LOT` | yes | yes | `0.2` | `None` | PASS |
| `FORGE_GATE_ASIA_CAPITULATION_BUY_MIN_ATOMS` | yes | yes | `2` | `None` | PASS |
| `FORGE_GATE_ASIA_CAPITULATION_BUY_RSI_MAX` | yes | yes | `28` | `None` | PASS |
| `FORGE_TIMING_ASIA_CAPITULATION_BUY_SESSION_END_UTC` | yes | yes | `7` | `None` | PASS |
| `FORGE_TIMING_ASIA_CAPITULATION_BUY_SESSION_START_UTC` | yes | yes | `22` | `None` | PASS |
| `FORGE_GEOMETRY_ASIA_CAPITULATION_BUY_SL_ATR_MULT` | yes | yes | `1.5` | `None` | PASS |
| `FORGE_GEOMETRY_ASIA_CAPITULATION_BUY_TP1_ATR_MULT` | yes | yes | `1` | `None` | PASS |
| `FORGE_GEOMETRY_ASIA_CAPITULATION_BUY_TP2_ATR_MULT` | yes | yes | `2.5` | `None` | PASS |
| `FORGE_GEOMETRY_BLR_BUY_CAPITULATION_LOT` | yes | yes | `0.3` | `None` | PASS |
| `FORGE_GEOMETRY_BLR_BUY_CAPITULATION_SL_ATR_MULT` | yes | yes | `1.5` | `None` | PASS |
| `FORGE_GEOMETRY_BLR_BUY_CAPITULATION_TP1_ATR_MULT` | yes | yes | `0.5` | `None` | PASS |
| `FORGE_GEOMETRY_BLR_BUY_CAPITULATION_TP2_ATR_MULT` | yes | yes | `1.5` | `None` | PASS |
| `FORGE_SETUP_BULL_DAY_DIP_BUY_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_TIMING_BULL_DAY_DIP_BUY_REENTRY_COOLDOWN_SEC` | yes | yes | `0` | `300` | PASS |
| `FORGE_SETUP_FRACTIONAL_SELL_IN_BULL_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_TIMING_GRINDING_SELL_COOLDOWN_SEC` | yes | yes | `600` | `None` | PASS |
| `FORGE_SETUP_GRINDING_SELL_ENABLED` | yes | yes | `1` | `None` | PASS |
| `FORGE_GEOMETRY_GRINDING_SELL_LOT_FACTOR` | yes | yes | `0.5` | `None` | PASS |
| `FORGE_GATE_GRINDING_SELL_MAX_RSI` | yes | yes | `55` | `None` | PASS |
| `FORGE_GATE_GRINDING_SELL_MIN_RSI` | yes | yes | `30` | `None` | PASS |
| `FORGE_GATE_GRINDING_SELL_MIN_VELOCITY` | yes | yes | `0.5` | `None` | PASS |
| `FORGE_GATE_GRINDING_SELL_ROOM_MIN_ATR` | yes | yes | `0.3` | `None` | PASS |
| `FORGE_GEOMETRY_GRINDING_SELL_SL_ATR_MULT` | yes | yes | `2.5` | `None` | PASS |
| `FORGE_GEOMETRY_GRINDING_SELL_TP1_ATR_MULT` | yes | yes | `0.7` | `None` | PASS |
| `FORGE_GEOMETRY_GRINDING_SELL_TP2_ATR_MULT` | yes | yes | `1.5` | `None` | PASS |
| `FORGE_TIMING_REVERSE_SELL_IN_BULL_COOLDOWN_SEC` | yes | yes | `300` | `None` | PASS |
| `FORGE_SETUP_REVERSE_SELL_IN_BULL_ENABLED` | yes | yes | `1` | `None` | PASS |
| `FORGE_GEOMETRY_REVERSE_SELL_IN_BULL_LOT_FACTOR` | yes | yes | `0.5` | `None` | PASS |
| `FORGE_GATE_REVERSE_SELL_IN_BULL_MIN_H1_TREND` | yes | yes | `1` | `None` | PASS |
| `FORGE_GATE_REVERSE_SELL_IN_BULL_MIN_RSI` | yes | yes | `72` | `None` | PASS |
| `FORGE_GATE_REVERSE_SELL_IN_BULL_MIN_VWAP_DIST_ATR` | yes | yes | `2` | `None` | PASS |
| `FORGE_GATE_REVERSE_SELL_IN_BULL_REQUIRE_DI_PLUS_ABOVE_MINUS` | yes | yes | `1` | `None` | PASS |
| `FORGE_GEOMETRY_REVERSE_SELL_IN_BULL_SL_ATR_MULT` | yes | yes | `2` | `None` | PASS |
| `FORGE_GEOMETRY_REVERSE_SELL_IN_BULL_TP1_ATR_MULT` | yes | yes | `1` | `None` | PASS |
| `FORGE_GEOMETRY_REVERSE_SELL_IN_BULL_TP2_ATR_MULT` | yes | yes | `2` | `None` | PASS |
| `FORGE_JOURNAL_SIGNALS_BATCH_TXN` | yes | yes | `1` | `0` | PASS |
| `FORGE_JOURNAL_SYNCHRONOUS_NORMAL` | yes | yes | `1` | `0` | PASS |
| `FORGE_JOURNAL_WAL_MODE` | yes | yes | `1` | `0` | PASS |
| `FORGE_FIXED_LOT` | yes | yes | `0.25` | `0.02` | PASS |
| `FORGE_GOLD_NATIVE_MAX_SELL_LEGS` | yes | yes | `10` | `2` | PASS |
| `FORGE_MIN_NUM_TRADES` | yes | yes | `2` | `1` | PASS |
| `FORGE_NATIVE_LEGS_MAX_WHEN_UNCLEAR` | yes | yes | `5` | `3` | PASS |
| `FORGE_STAGED_ADD_INTERVAL_SEC` | yes | yes | `5` | `25` | PASS |
| `FORGE_STAGED_ADD_MIN_FAVORABLE_POINTS` | yes | yes | `300` | `35` | PASS |
| `FORGE_STAGED_INITIAL_LEGS` | yes | yes | `3` | `1` | PASS |
| `FORGE_GEOMETRY_WAVE_CONFIRM_LOT_MULT` | yes | yes | `2` | `None` | PASS |
| `FORGE_TIMING_BB_LOWER_REVERSION_BUY_COOLDOWN_SECONDS` | yes | yes | `0` | `180` | PASS |
| `FORGE_TIMING_BB_LOWER_REVERSION_BUY_MAX_HOLD_SECONDS` | yes | yes | `0` | `1800` | PASS |
| `FORGE_GEOMETRY_BB_LOWER_REVERSION_BUY_SL_ATR_MULT` | yes | yes | `2.5` | `1.5` | PASS |
| `FORGE_GATE_BB_PULLBACK_BUY_BLOCK_ON_FALLING_VELOCITY` | yes | yes | `1` | `None` | PASS |
| `FORGE_GATE_BB_PULLBACK_BUY_MIN_VELOCITY_5BAR_SIGNED` | yes | yes | `-1` | `None` | PASS |
| `FORGE_GATE_BLR_BUY_BLOCK_ON_BEARISH_BOS` | yes | yes | `1` | `None` | PASS |
| `FORGE_GATE_BLR_BUY_CAPITULATION_ATR_RATIO_MIN` | yes | yes | `1.3` | `None` | PASS |
| `FORGE_GATE_BLR_BUY_CAPITULATION_DISPLACEMENT_MIN_ATR` | yes | yes | `1.5` | `None` | PASS |
| `FORGE_GATE_BLR_BUY_CAPITULATION_MIN_ATOMS` | yes | yes | `3` | `None` | PASS |
| `FORGE_GATE_BLR_BUY_CAPITULATION_OVERRIDE_ENABLED` | yes | yes | `1` | `None` | PASS |
| `FORGE_GATE_BLR_BUY_CAPITULATION_RSI_MAX` | yes | yes | `28` | `None` | PASS |
| `FORGE_GATE_BLR_BUY_MIN_VELOCITY_5BAR_SIGNED` | yes | yes | `-1` | `None` | PASS |
| `FORGE_BREAKOUT_ADX_LOT_FACTOR_HIGH` | yes | yes | `0.5` | `0.125` | PASS |
| `FORGE_BREAKOUT_ADX_LOT_FACTOR_MID` | yes | yes | `1` | `0.25` | PASS |
| `FORGE_GATE_BREAKOUT_BUY_BLOCK_EXHAUSTION_WITHOUT_BOS` | yes | yes | `1` | `None` | PASS |
| `FORGE_SETUP_BREAKOUT_BUY_CONVICTION_ENABLED` | yes | yes | `1` | `None` | PASS |
| `FORGE_GEOMETRY_BREAKOUT_BUY_CONVICTION_INITIAL_LEGS` | yes | yes | `5` | `None` | PASS |
| `FORGE_GATE_BREAKOUT_BUY_CONVICTION_MIN_ATOMS` | yes | yes | `4` | `None` | PASS |
| `FORGE_GEOMETRY_BREAKOUT_BUY_CONVICTION_TP1_CLOSE_PCT` | yes | yes | `50` | `None` | PASS |
| `FORGE_GATE_BREAKOUT_BUY_EXHAUSTION_RSI` | yes | yes | `72` | `None` | PASS |
| `FORGE_GATE_BREAKOUT_BUY_MAX_VWAP_DIST_ATR` | yes | yes | `2.5` | `None` | PASS |
| `FORGE_GATE_BREAKOUT_BUY_SCORE_VELOCITY_CHECK_ENABLED` | yes | yes | `1` | `None` | PASS |
| `FORGE_GATE_BREAKOUT_BUY_SCORE_VELOCITY_THRESHOLD` | yes | yes | `-5` | `None` | PASS |
| `FORGE_GATE_BREAKOUT_SELL_MAX_VWAP_DIST_ATR` | yes | yes | `2.5` | `None` | PASS |
| `FORGE_TIMING_CONVICTION_DECAY_GRACE_BARS` | yes | yes | `2` | `None` | PASS |
| `FORGE_GEOMETRY_CONVICTION_DECAY_L1_CLOSE_PCT` | yes | yes | `25` | `None` | PASS |
| `FORGE_GATE_CONVICTION_DECAY_L1_RATIO` | yes | yes | `0.75` | `None` | PASS |
| `FORGE_GEOMETRY_CONVICTION_DECAY_L2_CLOSE_PCT` | yes | yes | `50` | `None` | PASS |
| `FORGE_GATE_CONVICTION_DECAY_L2_RATIO` | yes | yes | `0.5` | `None` | PASS |
| `FORGE_GATE_CONVICTION_DECAY_L3_RATIO` | yes | yes | `0.25` | `None` | PASS |
| `FORGE_SETUP_CONVICTION_DECAY_PARTIAL_CLOSE_ENABLED` | yes | yes | `1` | `None` | PASS |
| `FORGE_GATE_DAILY_DIRECTION_ENABLE` | yes | yes | `1` | `0` | PASS |
| `FORGE_COMPOSITE_DTC_5STATE_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_GATE_DTC_BLOCK_COUNTER_TREND_BUYS` | yes | yes | `1` | `0` | PASS |
| `FORGE_GATE_DTC_BLOCK_COUNTER_TREND_SELLS` | yes | yes | `1` | `0` | PASS |
| `FORGE_COMPOSITE_DTC_DAY_BIAS_BLOCK_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_COMPOSITE_DTC_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_COMPOSITE_DTC_EXEMPT_OVERRIDE_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_COMPOSITE_DTC_GEOMETRY_WIDEN_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_COMPOSITE_DTC_PEMCG_MODIFIER_ENABLED` | yes | yes | `1` | `0` | PASS |
| `FORGE_GEOMETRY_DTC_TREND_ALIGNED_SL_WIDEN_FACTOR` | yes | yes | `2` | `1.0` | PASS |
| `FORGE_GEOMETRY_DTC_TREND_ALIGNED_TP_WIDEN_FACTOR` | yes | yes | `3` | `1.0` | PASS |

Mapped `.env` overrides that are not reflected in active config:

| .env line | FORGE_ Variable | Sync target | .env value | Active config value | Status |
|---:|---|---|---|---|---|
| 196 | `FORGE_BREAKOUT_TP1_CLOSE_PCT` | `bb_breakout.tp1_close_pct` | `60` | `70` | FAIL |
| 223 | `FORGE_STAGED_ADD_MIN_FAVORABLE_POINTS` | `lot_sizing.staged_add_min_favorable_points` | `500` | `300` | FAIL |
| 257 | `FORGE_TIMING_BREAKOUT_SAME_DIR_COOLDOWN_SEC` | `bb_breakout.same_dir_cooldown_seconds` | `900` | `0` | FAIL |
| 728 | `FORGE_PULLBACK_SCALP_COOLDOWN_SECONDS` | `safety.pullback_scalp_cooldown_seconds` | `600` | `0` | FAIL |
| 750 | `FORGE_TIMING_MA_CROSSOVER_COOLDOWN_SECONDS` | `timing.ma_crossover_cooldown_seconds` | `600` | `0` | FAIL |
| 761 | `FORGE_TIMING_VWAP_REVERSION_COOLDOWN_SECONDS` | `timing.vwap_reversion_cooldown_seconds` | `600` | `0` | FAIL |
| 772 | `FORGE_TIMING_FIB_CONFLUENCE_COOLDOWN_SECONDS` | `timing.fib_confluence_cooldown_seconds` | `600` | `0` | FAIL |
| 782 | `FORGE_TIMING_INSIDE_BAR_COOLDOWN_SECONDS` | `timing.inside_bar_cooldown_seconds` | `600` | `0` | FAIL |
| 794 | `FORGE_TIMING_BB_SQUEEZE_COOLDOWN_SECONDS` | `timing.bb_squeeze_cooldown_seconds` | `900` | `0` | FAIL |
| 808 | `FORGE_TIMING_ORB_COOLDOWN_SECONDS` | `timing.orb_cooldown_seconds` | `1800` | `0` | FAIL |
| 819 | `FORGE_TIMING_GAP_AND_GO_COOLDOWN_SECONDS` | `timing.gap_and_go_cooldown_seconds` | `14400` | `0` | FAIL |
| 835 | `FORGE_TIMING_DOUBLE_PATTERN_COOLDOWN_SECONDS` | `timing.double_pattern_cooldown_seconds` | `1200` | `0` | FAIL |
| 847 | `FORGE_TIMING_HS_COOLDOWN_SECONDS` | `timing.hs_cooldown_seconds` | `1200` | `0` | FAIL |
| 860 | `FORGE_TIMING_FLAG_PENNANT_COOLDOWN_SECONDS` | `timing.flag_pennant_cooldown_seconds` | `1200` | `0` | FAIL |
| 870 | `FORGE_TIMING_TRENDLINE_BOUNCE_COOLDOWN_SECONDS` | `timing.trendline_bounce_cooldown_seconds` | `1200` | `0` | FAIL |
| 880 | `FORGE_TIMING_SR_FLIP_COOLDOWN_SECONDS` | `timing.sr_flip_cooldown_seconds` | `1200` | `0` | FAIL |

## Section 9 — scribe.py / regime.py / schemas/ Cross-Check
| Check | File:line | Status | Notes |
|---|---|---|---|
| `forge_signals` schema mirrors live journal | `python/scribe.py:119-280`; `ea/FORGE.mq5:9591-9704` | PASS | Current scribe table includes v2.7.123/124 atom columns. |
| Additive migrations for new signal columns | `python/scribe.py:784-1030` | PASS | Existing DBs get ALTERs for MACD, M15 ADX, lot_factor, RegimeState and ICT atoms. |
| Regime labels | `python/regime.py:320-345,530-549`; `ea/FORGE.mq5:17223-17227,3609-3612` | PASS | EA consumes `RANGE`, `TREND_BULL`, `TREND_BEAR`, `VOLATILE`; regime.py emits same labels or RANGE fallback. |
| EA-anchored session/killzone readers | `python/trading_session.py`; `python/bridge.py:5334-5340`; `python/aurum.py:443-458` | PASS | Bridge exports EA session state and Aurum reads session context. |
| Plaintext secret handling | `.gitignore:2,70-71`; git ls-files empty | PASS | Accepted local trade-off remains gitignored and untracked. |

## Section 10 — Dashboard / API Consistency
| Check | dashboard:line | api:line | Status | Notes |
|---|---|---|---|---|
| `btDetail.taken` rendered | `dashboard/app.js:1744-1776` | `python/athena_api.py:1948-1978` | PASS | API returns `taken`, UI consumes it. |
| `trade_outcome`, `pnl`, `cascade_pnl` | `dashboard/app.js:1770-1819` | `python/athena_api.py:1938-1953` | PASS | API shape matches UI fields. |
| Legs math | `dashboard/app.js:1794-1796` | `python/athena_api.py:1927-1935` | PASS | API counts TP1 markers, fallback SL/profit deals; volume selected for lot. |
| Cascade P&L +20000..+20009 | `dashboard/app.js:1813-1819` | `python/athena_api.py:1855-1916` | PASS | API assigns cascade owners across offsets 20000..20009 and includes cascade P&L. |
| Run isolation | `dashboard/app.js:1572-1578` | `python/athena_api.py:1733-1810,1963-1965` | PASS | Queries use `aurum_run_id=?`; UI guards stale detail with `btSelRun===meta.aurum_run_id`. |
| Gate legend endpoint | `dashboard/app.js:618,1863-1869` | `python/athena_api.py:1985-2015` | PASS | UI uses API-provided legend map. |

## Section 11 — Scripts / Tests Consistency
| Check | File:line | Status | Notes |
|---|---|---|---|
| Dead env whitelist | `tests/api/test_forge_27x_gates.py:324` | PASS | `FORGE_SCALPER_MODE` is whitelisted as bridge/MT5-direct. |
| Sync mapping coverage test target | `scripts/sync_scalper_config_from_env.py:27-714` | FAIL | Mapping contains `FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED` but `.env.example` has no matching line. |
| Gate legend literal+constructed audit | `ea/FORGE.mq5:17415-17449`; `config/gate_legend.json:3-20` | PASS | Filter_* constructed codes included; no missing legend keys. |
| Backtest compare run isolation | `python/backtest_compare.py:62-97,283` | PASS | Uses run-specific breakdowns for killzone/regime comparisons. |

## Issues Found (Consolidated)
| # | Severity | Section | Description | Action |
|---:|---|---|---|---|
| 1 | FAIL | Mandatory C | Sync-mapped key(s) missing from .env.example: FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED | Add documented # KEY= line(s). |
| 2 | FAIL | Variable Integrity | 16 mapped .env overrides do not match active scalper_config.json | Run make scalper-env-sync / forge-compile or update .env/config inventory. |

## Recommendations & Proposed Fixes
### Issue 1 — sync mapping missing from `.env.example`
- Evidence: `scripts/sync_scalper_config_from_env.py:259` maps `FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED`; `.env.example` has no matching `# FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED=` line.
- Root cause: config knob added at sync layer without operator-facing cheat-sheet entry.
- Industry pattern: keep env config explicit and discoverable; Twelve-Factor config guidance treats env vars as the deploy-time config surface: https://www.12factor.net/config.
- Option A: add a commented `.env.example` line near ISS/ICT knobs. Risk: none.
- Option B: remove mapping until the EA consumes it. Risk: loses reserved knob continuity.
- Preferred: Option A. Backward compatibility: default-off `# FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED=0`.

### Issue 2 — mapped `.env` overrides not reflected in active config
- Evidence: 16 mapped active `.env` keys differ from `config/scalper_config.json`; see Section 8 mismatch table.
- Root cause: generated runtime config appears stale relative to `.env`, or `.env` is carrying non-runtime inventory values without a sync run.
- Industry pattern: generated runtime artifacts need deterministic regeneration from source-of-truth inputs; SQLite/scribe parity similarly depends on explicit counts matching explicit columns: https://www.sqlite.org/lang_insert.html.
- Option A: run `make scalper-env-sync` and review the diff in `config/scalper_config.json`. Risk: runtime behavior changes to match `.env`.
- Option B: edit `.env` comments/values to match current active config where the active config is intentional. Risk: loses aspirational inventory unless comments preserve it.
- Preferred: Option A for mapped runtime knobs; keep default-off behavior by commenting out knobs that are documentation-only.

## Overall Verdict
The EA implementation and dashboard/API bridge are broadly coherent: BB_BREAKOUT BUY/SELL gates are implemented with cited code paths, gate legend completeness passes including runtime-constructed Filter_* codes, and the critical SIGNALS schema/scribe placeholder parity passes at 158/158. The main problems are configuration hygiene: one sync-mapped knob is undiscoverable in `.env.example`, and 16 active mapped `.env` overrides do not match the active generated runtime config. Confidence: high for mandatory checks and BB_BREAKOUT validation; medium for broad scripts/tests drift because the repository contains generated test artifacts and node_modules-like files under `tests/`, which were excluded from issue severity.
