# FORGE Entry Conditions — Codex Validation Review
**Date**: 2026-05-12
**EA version**: FORGE v2.7.38 (#property "2.108"; scalper_config.json "version": "2.7.38")
**Reviewer**: Codex (automated, read-only)
**Methodology**: Every claim cited with file:line. UNVERIFIED = code not found. Active config = scalper_config.json. Accepted-items rules per SKILL.md.

## Validation Summary

**Overall verdict: FAIL for v2.7.38 new-entry execution readiness.** The v2.7.38 plumbing is mostly present, default-OFF, and mapped through config/env/legend, but both new setup types (`FRACTIONAL_SELL_IN_BULL`, `BULL_DAY_DIP_BUY`) are likely blocked by the existing `rr_too_low` gate when enabled. Their shipped geometry is intentionally sub-1.0 R:R (`0.3/1.5 = 0.20`, `0.65/1.0 = 0.65`), while active config requires `min_rr = 1.5` and `min_rr_floor = 1.5` (`config/scalper_config.json:213-214`). The R:R bypass only exempts `MOMENTUM_DUMP` and `BB_PULLBACK_SCALP`, not the two new setup types (`ea/FORGE.mq5:8055-8063`).

**PASS:** EA version and active config version are v2.7.38 (`ea/FORGE.mq5:58`, `ea/FORGE.mq5:63`, `config/scalper_config.json:2`).

**PASS:** The 12 composite config fields are declared, defaulted, read from JSON, present in active/default configs, mapped from env, and documented in `.env.example` (`ea/FORGE.mq5:608-621`, `ea/FORGE.mq5:3056-3069`, `ea/FORGE.mq5:3672-3685`, `config/scalper_config.json:323-336`, `config/scalper_config.defaults.json:309-326`, `scripts/sync_scalper_config_from_env.py:289-302`, `.env.example:774-819`).

**PASS:** The two new gate codes are logged by the EA and present in `gate_legend.json` (`ea/FORGE.mq5:6904-6909`, `ea/FORGE.mq5:6993-6998`, `ea/FORGE.mq5:7108-7113`, `ea/FORGE.mq5:7341-7346`, `ea/FORGE.mq5:7798-7803`, `config/gate_legend.json:184-193`).

**WARNING:** `SYSTEM_VERSION 1.10.1` was not found in `ea/FORGE.mq5`; the file exposes `#property version "2.108"` and `FORGE_VERSION = "2.7.38"` only (`ea/FORGE.mq5:58`, `ea/FORGE.mq5:63`).

## Section 1-16 — Carryover from v2.7.37 review (concise updates only)

Carryover infrastructure from v2.7.36/v2.7.37 remains in place:

- `InitScalperConfig()` precedes `WriteBrokerInfo()` in `OnInit()` (`ea/FORGE.mq5:995-1000`).
- `ForgeEvalAtoms()` is called at the top of `CheckNativeScalperSetups()` before early SKIP paths (`ea/FORGE.mq5:6457-6465`), and the later comment confirms the call is intentionally not repeated for pre-trigger SKIPs (`ea/FORGE.mq5:6579-6581`).
- EA `SIGNALS` schema contains v2.7.37 Layer-4 atom telemetry as 24 cols plus Group 3 full inventory as 45 cols, totaling 69 telemetry columns (`ea/FORGE.mq5:5378-5417`).
- `JournalRecordSignal()` inserts those same 69 telemetry values from `g_eval_*` globals (`ea/FORGE.mq5:5683-5710`, `ea/FORGE.mq5:5744-5814`).
- Scribe destination schema mirrors 24 + 45 telemetry columns (`python/scribe.py:152-222`), migration adds them idempotently with duplicate-column handling (`python/scribe.py:668-735`), and v37 indexes always run for fresh DBs (`python/scribe.py:736-741`).

## Section 17 — v2.7.38 Tier 1 Composite Plumbing

**PASS:** `ScalperConfig` includes the 12 new fields after `kz_london_close_end_min`: `block_sell_in_chop_enabled`, `intraday_reversal_sell_enabled`, `intraday_reversal_sell_lot_mult`, `fractional_sell_in_bull_enabled`, `fractional_sell_in_bull_lot_factor`, `fractional_sell_in_bull_sl_atr_mult`, `fractional_sell_in_bull_tp1_atr_mult`, `bull_day_dip_buy_enabled`, `bull_day_dip_buy_lot_mult`, `bull_day_dip_buy_sl_atr_mult`, `bull_day_dip_buy_tp1_atr_mult`, `bull_day_dip_buy_reentry_cooldown_sec` (`ea/FORGE.mq5:608-621`).

**PASS:** `InitScalperConfig()` defaults all 12 fields after `kz_london_close_end_min = 12*60`; enabled flags default false/0 and numeric defaults match active config (`ea/FORGE.mq5:3056-3069`, `config/scalper_config.json:323-336`).

**PASS:** `ReadScalperConfig()` has `JsonHasKey()` readers for all 12 fields after `kz_london_close_end_min` (`ea/FORGE.mq5:3672-3685`).

**PASS:** `config/scalper_config.defaults.json` and active `config/scalper_config.json` both include a `composites` section with all 12 keys default-OFF where applicable (`config/scalper_config.defaults.json:309-326`, `config/scalper_config.json:323-336`).

**PASS:** `scripts/sync_scalper_config_from_env.py` maps the 12 new `FORGE_*` env vars to `composites.*` after `FORGE_KZ_LONDON_CLOSE_END_MIN` and before `FORGE_TESTER_COOLDOWN_ENABLED` (`scripts/sync_scalper_config_from_env.py:287-302`).

**PASS:** `.env.example` documents the Tier 1 Boolean Composites section and all 12 commented hints (`.env.example:774-819`).

**PASS:** New state globals are declared: `g_last_chop_buy_exit_time`, `g_last_fractional_sell_in_bull_time`, `g_last_intraday_reversal_log_bar`, and `g_last_chop_block_sell_log_bar` (`ea/FORGE.mq5:322-325`).

**WARNING:** `SYSTEM_VERSION 1.10.1` was not found; only `#property version "2.108"` and `FORGE_VERSION = "2.7.38"` are present (`ea/FORGE.mq5:58`, `ea/FORGE.mq5:63`).

## Section 18 — Composite Helper Function Integrity

**PASS:** `IsBlockSellInChopActive()` is defined and guarded by `g_sc.block_sell_in_chop_enabled`; it requires `RANGE`, `h1_trend_strength > 0.5`, and bypasses when `IsFractionalSellInBullActive()` is true (`ea/FORGE.mq5:4544-4551`).

**PASS:** `IsIntradayReversalSellActive()` is defined and guarded by `g_sc.intraday_reversal_sell_enabled`; it reads M5 closes at shifts 0/6/12, checks decline/cascade, `m5_rsi <= 40`, divergence or below BB mid, VWAP confirmation, and `g_eval_m5_lh_cascade == 1` (`ea/FORGE.mq5:4561-4583`).

**PASS:** `IsFractionalSellInBullActive()` is defined and guarded by `g_sc.fractional_sell_in_bull_enabled`; atoms match atlas §5.3: `TREND_BULL`, H1 >= 1.0, PSAR above, RSI 60-75, ADX >= 30, bar-over-bar bearish, and price near/above BB upper (`ea/FORGE.mq5:4589-4608`, `docs/FORGE_INDICATOR_ATLAS.md:547-568`).

**PASS:** `IsBullDayDipBuyActive()` is defined and guarded by `g_sc.bull_day_dip_buy_enabled`; it includes macro bull, not daily bear, RSI zone, ADX band, BB middle/lower position, POC/Fib/VWAP soft checks, bear-divergence rejection, V3 OHLC atoms `dist_high_atr`, `!m5_lh_cascade`, `long_lower_wick`, session, and re-entry cooldown (`ea/FORGE.mq5:4617-4647`).

**WARNING:** Atlas §5.1 says the re-entry anchor should be set when the position closes via TP1 (`docs/FORGE_INDICATOR_ATLAS.md:503-512`), but the EA sets `g_last_chop_buy_exit_time = TimeCurrent()` at entry with an in-code note calling this a simplification (`ea/FORGE.mq5:7911-7916`).

**WARNING:** Atlas §5.1 is still titled `CHOP_IN_BULL_TREND_BUY`, while v2.7.38 implementation uses `BULL_DAY_DIP_BUY` as the setup type (`docs/FORGE_INDICATOR_ATLAS.md:439-444`, `ea/FORGE.mq5:7903-7907`).

## Section 19 — Filter chain integration

**PASS:** `BLOCK_SELL_IN_CHOP` is inserted at the top of the `BB_BOUNCE` SELL chain and emits `entry_quality_chop_block_sell` with per-M5-bar throttle via `g_last_chop_block_sell_log_bar` (`ea/FORGE.mq5:6983-7000`).

**PASS:** `BLOCK_SELL_IN_CHOP` is inserted at the top of the `BB_BREAKOUT` SELL chain and emits the same gate with the same throttle global (`ea/FORGE.mq5:7332-7348`).

**PASS:** `INTRADAY_REVERSAL_TO_SELL_V3` is inserted at the top of `BB_BOUNCE` BUY, `BB_BREAKOUT` BUY, and `MOMENTUM_DUMP` BUY chains and emits `entry_quality_intraday_reversal_buy_block` with per-M5-bar throttle via `g_last_intraday_reversal_log_bar` (`ea/FORGE.mq5:6892-6911`, `ea/FORGE.mq5:7100-7115`, `ea/FORGE.mq5:7791-7804`).

**PASS:** `MOMENTUM_DUMP` BUY uses an `else if` cascade after the reversal check, and `buy_rsi_min` is declared before the new reversal block (`ea/FORGE.mq5:7791-7814`). No `continue` was found in this chain.

**PASS:** `FRACTIONAL_SELL_IN_BULL` and `BULL_DAY_DIP_BUY` top-level trigger blocks are present after `MOMENTUM_DUMP`; both are guarded by `direction == ""`, their enabled flags, `m5_atr > 0.0`, and their helper functions (`ea/FORGE.mq5:7880-7896`, `ea/FORGE.mq5:7898-7920`).

**PASS:** Lot pipeline includes `intraday_reversal_factor` scoped to `MOMENTUM_DUMP` SELL, `fractional_sell_factor` scoped to `FRACTIONAL_SELL_IN_BULL` SELL, and `bull_day_dip_factor` scoped to `BULL_DAY_DIP_BUY` BUY; all feed `combined_lot_factor` (`ea/FORGE.mq5:8229-8255`).

**FAIL:** New setup geometry is likely unreachable after trigger because the R:R gate excludes only `MOMENTUM_DUMP` and `BB_PULLBACK_SCALP` from `rr_too_low` (`ea/FORGE.mq5:8055-8063`). `FRACTIONAL_SELL_IN_BULL` ships TP1 0.3 ATR, SL 1.5 ATR, no TP2 (`ea/FORGE.mq5:7890-7892`; `.env.example:800-808`), and `BULL_DAY_DIP_BUY` ships TP1 0.65 ATR, SL 1.0 ATR, no TP2 (`ea/FORGE.mq5:7909-7911`; `.env.example:810-819`). Active config requires `min_rr = 1.5` and `min_rr_floor = 1.5` (`config/scalper_config.json:213-214`), so their expected R:R of 0.20 and 0.65 is below the floor.

## Section 20 — Carry-over invariants

**PASS:** `InitScalperConfig()` precedes `WriteBrokerInfo()` in `OnInit()` (`ea/FORGE.mq5:995-1000`).

**PASS:** EA `SIGNALS` schema has 69 v2.7.37 telemetry columns: 24 Layer-4 columns and 45 Group 3 columns (`ea/FORGE.mq5:5378-5417`).

**PASS:** `g_eval_*` globals are declared for telemetry (`ea/FORGE.mq5:246-316`), populated by `ForgeEvalAtoms()` (`ea/FORGE.mq5:4352-4522`), and called at the top of `CheckNativeScalperSetups()` (`ea/FORGE.mq5:6457-6465`).

**PASS:** Scribe migration is concurrency-safe for duplicate-column races (`python/scribe.py:695-704`, `python/scribe.py:727-735`).

**PASS:** Fresh DBs get v37 indexes because `CREATE INDEX IF NOT EXISTS` is executed unconditionally after the column loops (`python/scribe.py:736-741`).

## Section 21 — Atlas/inventory currency

**PASS with warnings:** Atlas §5.3, §5.4, and §5.7 match the implemented helper atoms closely (`docs/FORGE_INDICATOR_ATLAS.md:547-595`, `docs/FORGE_INDICATOR_ATLAS.md:599-623`, `ea/FORGE.mq5:4544-4583`, `ea/FORGE.mq5:4589-4608`).

**WARNING:** Atlas §5.1 is not fully currency-clean for v2.7.38 naming: it titles the composite `CHOP_IN_BULL_TREND_BUY`, while roadmap and EA use `BULL_DAY_DIP_BUY_V3` / `BULL_DAY_DIP_BUY` (`docs/FORGE_INDICATOR_ATLAS.md:439-444`, `FORGE_COMPOSITE_ROADMAP.md:75`, `ea/FORGE.mq5:7903-7907`).

**WARNING:** `FORGE_DECISION_STACK_INVENTORY.md` remains a v2.7.36 extraction and does not describe the v2.7.38 composites or updated lot pipeline (`docs/FORGE_DECISION_STACK_INVENTORY.md:1-6`, `docs/FORGE_DECISION_STACK_INVENTORY.md:407-416`). It needs v2.7.38 regeneration.

## Mandatory Check A — Dead FORGE_* env vars

Command run: `grep -nE '^FORGE_[A-Z0-9_]+=' .env`.

**Active `.env` FORGE keys found:** 84 keys, spanning `.env:182-470`. The active keys are:

`FORGE_SCALPER_MODE`, `FORGE_FAST_LOCK_MIN_HOLD_SEC_BREAKOUT`, `FORGE_FAST_LOCK_MIN_PROFIT_POINTS`, `FORGE_BOUNCE_MIN_TP1_ATR_MULT`, `FORGE_BOUNCE_MIN_TP2_ATR_MULT`, `FORGE_BREAKOUT_TP1_ATR_MULT`, `FORGE_BREAKOUT_TP1_BUY_ATR_MULT`, `FORGE_BREAKOUT_TP1_SELL_ATR_MULT`, `FORGE_BREAKOUT_TP1_CLOSE_PCT`, `FORGE_FIXED_LOT`, `FORGE_MIN_NUM_TRADES`, `FORGE_MAX_NUM_TRADES`, `FORGE_GOLD_NATIVE_MAX_SELL_LEGS`, `FORGE_NATIVE_LEGS_MAX_WHEN_UNCLEAR`, `FORGE_STAGED_ADD_MIN_FAVORABLE_POINTS`, `FORGE_WAVE_CONFIRMATION_LOT_MULT`, `FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR`, `FORGE_BREAKOUT_MAX_REENTRY_ATR_EXT`, `FORGE_BREAKOUT_ADX_MIN`, `FORGE_BREAKOUT_ADX_MIN_SELL`, `FORGE_BREAKOUT_REQUIRE_RSI_DECLINING_SELL`, `FORGE_BREAKOUT_BLOCK_HID_BULL_SELL`, `FORGE_BREAKOUT_REQUIRE_H1_DI_BUY`, `FORGE_BREAKOUT_REQUIRE_H1_DI_SELL`, `FORGE_BREAKOUT_SAME_DIR_COOLDOWN_SECONDS`, `FORGE_BREAKOUT_FAILED_GATE_ENABLED`, `FORGE_BREAKOUT_FAILED_MIN_PEAK_RSI`, `FORGE_BREAKOUT_FAILED_MIN_RSI_DROP`, `FORGE_BREAKOUT_FAILED_SAME_BAR_HARD_BLOCK`, `FORGE_BREAKOUT_REQUIRE_PSAR_ALIGN`, `FORGE_BREAKOUT_COUNTER_BUY_ADX_THRESHOLD`, `FORGE_SESSION_NY_SELL_CUTOFF_UTC`, `FORGE_BREAKOUT_RSI_SELL_FLOOR`, `FORGE_BREAKOUT_REQUIRE_MACD_BUY`, `FORGE_BREAKOUT_ADX_LOT_FACTOR_MID`, `FORGE_BREAKOUT_ADX_LOT_FACTOR_HIGH`, `FORGE_BREAKOUT_ADX_SELL_BLOCK_THRESHOLD`, `FORGE_BREAKOUT_RSI_BUY_CEIL`, `FORGE_SELL_STOP_CONT_ENABLED`, `FORGE_BUY_LIMIT_RECOVERY_ENABLED`, `FORGE_BUY_LIMIT_RECOVERY_MIN_RSI`, `FORGE_SELL_STOP_CONT_ATR_MULT`, `FORGE_SELL_STOP_CONT_SL_ATR_MULT`, `FORGE_BREAKOUT_BUY_SL_ATR_MULT`, `FORGE_BREAKOUT_BE_CUSHION_ATR_MULT`, `FORGE_BREAKOUT_TP2_SL_RATCHET_ENABLED`, `FORGE_BREAKOUT_ATR_TRAIL_ENABLED`, `FORGE_SELL_STOP_CONT_MIN_RSI`, `FORGE_SELL_STOP_CONT_MIN_ADX`, `FORGE_SELL_STOP_CONT_REQUIRE_TREND_REGIME`, `FORGE_H4_RSI_SELL_MAX`, `FORGE_H4_RSI_BUY_MIN`, `FORGE_H4_ADX_MIN_SELL`, `FORGE_H4_ADX_MIN_BUY`, `FORGE_BREAKOUT_H1H4_CRASH_SELL_MIN_M15_ADX`, `FORGE_BOUNCE_ADX_MAX`, `FORGE_BOUNCE_LOT_FACTOR`, `FORGE_ADX_TREND_ENTER`, `FORGE_ADX_TREND_EXIT`, `FORGE_MIN_ENTRY_ATR`, `FORGE_MIN_DIRECTIONAL_BARS`, `FORGE_MIN_BODY_RATIO`, `FORGE_REQUIRE_BB_EXPANSION`, `FORGE_DAILY_DIRECTION_GATE_ENABLED`, `FORGE_REGIME_H1_OVERRIDE_FACTOR`, `FORGE_DUMP_CATCH_ENABLED`, `FORGE_DUMP_REQUIRE_D1_BIAS`, `FORGE_DUMP_LOT_FACTOR`, `FORGE_DUMP_MIN_ADX`, `FORGE_DUMP_ATR_MULT`, `FORGE_DUMP_MAX_RSI`, `FORGE_DUMP_SELL_H1_MAX`, `FORGE_DUMP_BUY_LOT_FACTOR`, `FORGE_DUMP_SELL_LOT_FACTOR`, `FORGE_DUMP_MAX_RSI_BUY`, `FORGE_PULLBACK_SCALP_ENABLED`, `FORGE_PULLBACK_SCALP_FRESH_FLIP_BARS`, `FORGE_PULLBACK_SCALP_LOT_FACTOR`, `FORGE_PULLBACK_SCALP_SL_ATR_MULT`, `FORGE_DUMP_REQUIRE_BAR_CONFIRM`, `FORGE_PULLBACK_SCALP_TP1_ATR_MULT`, `FORGE_PULLBACK_SCALP_TP2_ATR_MULT`, `FORGE_PULLBACK_SCALP_COOLDOWN_SECONDS`, `FORGE_PULLBACK_SCALP_MAX_ADX`.

**PASS:** All active `FORGE_*` keys are either mapped in `scripts/sync_scalper_config_from_env.py` or accepted by protocol as whitelist-only (`FORGE_SCALPER_MODE`). The v2.7.38 composite mappings are present in the sync script (`scripts/sync_scalper_config_from_env.py:289-302`).

**PASS:** No active v2.7.38 composite env vars are present in `.env`; the composite documentation exists only as commented hints in `.env.example` (`.env.example:782-819`).

**PASS:** No lowercase config-looking active keys were found by `rg -n '^[a-z][a-z0-9_]*=' .env`.

## Mandatory Check B — Gate legend completeness

Command run: `grep -oE 'JournalRecordSignal\("SKIP","[a-z0-9_]+' ea/FORGE.mq5 | sort -u`.

**Gate codes found:** 60 literal/static prefixes: `cooldown`, `direction_cooldown`, `dump_adx_block`, `dump_bar_confirm_missing`, `dump_chop_block`, `dump_cooldown`, `dump_d1_bias_block`, `dump_h1_trend_block_sell`, `dump_psar_block`, `dump_rsi_block`, `dump_rsi_buy_ceil`, `entry_quality_adx_extreme_sell`, `entry_quality_adx_min_sell`, `entry_quality_adx_spike_sell`, `entry_quality_atr`, `entry_quality_bb_contraction`, `entry_quality_body`, `entry_quality_breakout_cooldown`, `entry_quality_breakout_failed`, `entry_quality_breakout_failed_samebar`, `entry_quality_chop_block_sell`, `entry_quality_daily_bear_block_buy`, `entry_quality_daily_bull_block_sell`, `entry_quality_direction`, `entry_quality_direction_cap`, `entry_quality_h1_di_buy`, `entry_quality_h1_di_sell`, `entry_quality_h1_macd_buy`, `entry_quality_h1_macd_sell`, `entry_quality_h4_adx_buy_blocked`, `entry_quality_h4_adx_sell_blocked`, `entry_quality_h4_rsi_buy_blocked`, `entry_quality_h4_rsi_sell_blocked`, `entry_quality_hid_bull_div_sell`, `entry_quality_intraday_reversal_buy_block`, `entry_quality_m30_not_bearish`, `entry_quality_news_filter`, `entry_quality_news_rsi_tighten`, `entry_quality_psar_misalign_buy`, `entry_quality_psar_misalign_sell`, `entry_quality_rsi_buy_ceil`, `entry_quality_rsi_rising_sell`, `entry_quality_session_sell_cutoff`, `execution_failed`, `m1`, `no_setup`, `open_group_`, `open_group_bad_stoplimit_price`, `open_group_bad_stoplimit_trigger`, `open_group_invalid_stops`, `open_group_missing_stoplimit`, `open_group_rr_below_floor`, `open_group_unsupported_order_type`, `open_groups`, `post_sl_cooldown`, `regime_countertrend`, `rr_too_low`, `session_off`, `session_trade_cap`, `spread`.

**PASS:** Every gate code is covered by an explicit `config/gate_legend.json` entry or the `_patterns.open_group_*` wildcard (`config/gate_legend.json:9-11`). The two new v2.7.38 gate codes have explicit entries (`config/gate_legend.json:184-193`).

## Issues Found (Consolidated)

1. **FAIL — New setup types likely cannot pass active R:R gate.** `FRACTIONAL_SELL_IN_BULL` and `BULL_DAY_DIP_BUY` are intended single-TP scalp/probe entries with R:R below 1.0 (`ea/FORGE.mq5:7890-7892`, `ea/FORGE.mq5:7909-7911`, `.env.example:800-819`), but active `min_rr`/`min_rr_floor` are 1.5 (`config/scalper_config.json:213-214`) and the R:R bypass excludes only `MOMENTUM_DUMP` and `BB_PULLBACK_SCALP` (`ea/FORGE.mq5:8055-8063`).

2. **WARNING — `SYSTEM_VERSION 1.10.1` not found.** The requested metadata is not present in the EA; only `#property version "2.108"` and `FORGE_VERSION = "2.7.38"` were found (`ea/FORGE.mq5:58`, `ea/FORGE.mq5:63`).

3. **WARNING — Bull-day cooldown starts at entry, not TP1 exit.** Atlas says the cooldown anchor is TP1 close time (`docs/FORGE_INDICATOR_ATLAS.md:503-512`), while EA sets it at entry and documents the simplification (`ea/FORGE.mq5:7911-7916`).

4. **WARNING — Atlas/inventory need regeneration.** Atlas §5.1 still uses the older `CHOP_IN_BULL_TREND_BUY` title while EA uses `BULL_DAY_DIP_BUY` (`docs/FORGE_INDICATOR_ATLAS.md:439-444`, `ea/FORGE.mq5:7903-7907`), and the decision-stack inventory is still a v2.7.36 extraction (`docs/FORGE_DECISION_STACK_INVENTORY.md:1-6`).

## Recommendations & Proposed Fixes

1. Add the two new setup types to the R:R bypass or give them a setup-specific R:R policy:
   `if(setup_type != "MOMENTUM_DUMP" && setup_type != "BB_PULLBACK_SCALP" && setup_type != "FRACTIONAL_SELL_IN_BULL" && setup_type != "BULL_DAY_DIP_BUY" && ...)`.

2. If `SYSTEM_VERSION` is required by downstream tooling, add an explicit constant or documented output field; otherwise remove it from release validation criteria.

3. Move `g_last_chop_buy_exit_time` assignment to the TP1-close branch for `BULL_DAY_DIP_BUY`, or rename the variable/comment to reflect entry-time cooldown behavior.

4. Regenerate `docs/FORGE_DECISION_STACK_INVENTORY.md` for v2.7.38 and normalize Atlas §5.1 naming to `BULL_DAY_DIP_BUY_V3`.

## Overall Verdict

**FAIL.** The default-OFF v2.7.38 plumbing, helper guards, env sync, active config, gate legend, and carryover telemetry infrastructure are largely present. The release should not be considered execution-ready for the two new setup types until the R:R gate is updated, because enabling either composite is expected to create `rr_too_low` skips instead of executable entries under active config.
