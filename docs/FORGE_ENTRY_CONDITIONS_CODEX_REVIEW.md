# FORGE Entry Conditions — Codex Validation Review

**Date**: 2026-05-11  
**EA version**: FORGE v2.7.21 (from scalper_config.json)  
**Reviewer**: Codex (automated, read-only)  
**Methodology**: Every claim cited with file:line. UNVERIFIED = code not found. Active config = scalper_config.json (not defaults).

## Validation Summary
- Gates checked: 76
- PASS: 62  |  WARNING: 9  |  FAIL: 5  |  UNVERIFIED: 0
- Mandatory Check A (Dead env vars): PASS
- Mandatory Check B (Gate legend completeness): PASS

## Mandatory Check A — Dead FORGE_* env vars
**Status**: PASS
| .env key | sync mapping found? | Whitelisted (FORGE_ENV_VARS_NOT_IN_SYNC)? | Status |
|----------|---------------------|-------------------------------------------|--------|
| FORGE_SCALPER_MODE (.env:145) | No | Yes, tests/api/test_forge_27x_gates.py:260-261 | PASS |
| FORGE_BOUNCE_RECLAIM_PCT through FORGE_NEWS_FILTER_APPLY_IN_TESTER (.env:146-415) | Yes, scripts/sync_scalper_config_from_env.py:28-222 | No | PASS |

Lowercase config-looking keys (must be empty for PASS):
| .env line | key | Reason flagged |
|-----------|-----|----------------|
| - | - | None found; all active config-looking FORGE overrides use uppercase FORGE_* keys. |

## Mandatory Check B — Gate legend completeness
**Status**: PASS
| EA gate code | EA file:line | In gate_legend.json? | Matches _patterns wildcard? | Status |
|--------------|--------------|----------------------|------------------------------|--------|
| entry_quality_atr | ea/FORGE.mq5:4795 | config/gate_legend.json:34 | No | PASS |
| entry_quality_body | ea/FORGE.mq5:4826 | config/gate_legend.json:29 | No | PASS |
| entry_quality_direction | ea/FORGE.mq5:4838 | config/gate_legend.json:19 | No | PASS |
| entry_quality_bb_contraction | ea/FORGE.mq5:4853 | config/gate_legend.json:44 | No | PASS |
| session_off / spread / open_groups / session_trade_cap / cooldown | ea/FORGE.mq5:4884-4931 | config/gate_legend.json:204,209,194,199,219 | No | PASS |
| entry_quality_news_filter / entry_quality_news_rsi_tighten | ea/FORGE.mq5:4775,5500,5811 | config/gate_legend.json:184,189 | No | PASS |
| entry_quality_rsi_buy_ceil | ea/FORGE.mq5:5339 | config/gate_legend.json:49 | No | PASS |
| entry_quality_h1_di_buy / entry_quality_h1_di_sell | ea/FORGE.mq5:5350,5596 | config/gate_legend.json:104,109 | No | PASS |
| entry_quality_macd_q1_bull_fading / q2_bear_str / q3_bear_fading | ea/FORGE.mq5:5366-5371 | config/gate_legend.json:89,94,99 | No | PASS |
| entry_quality_macd_q0_bull_rising / q1_bull_fading / q3_bear_fading | ea/FORGE.mq5:5700-5705 | config/gate_legend.json:84,89,99 | No | PASS |
| entry_quality_h1_macd_buy / entry_quality_h1_macd_sell | ea/FORGE.mq5:5411,5725 | config/gate_legend.json:119,114 | No | PASS |
| entry_quality_breakout_cooldown | ea/FORGE.mq5:5429,5787 | config/gate_legend.json:124 | No | PASS |
| entry_quality_breakout_failed / entry_quality_breakout_failed_samebar | ea/FORGE.mq5:5473,5453 | config/gate_legend.json:129,134 | No | PASS |
| entry_quality_psar_misalign_buy / entry_quality_psar_misalign_sell | ea/FORGE.mq5:5490,5800 | config/gate_legend.json:139,144 | No | PASS |
| entry_quality_session_sell_cutoff | ea/FORGE.mq5:5555 | config/gate_legend.json:179 | No | PASS |
| entry_quality_adx_extreme_sell / adx_min_sell / adx_spike_sell | ea/FORGE.mq5:5568,5575,5650 | config/gate_legend.json:74,69,79 | No | PASS |
| entry_quality_rsi_sell_floor / entry_quality_rsi_sell_adx_floor | ea/FORGE.mq5:5632-5634 | config/gate_legend.json:54,59 | No | PASS |
| entry_quality_rsi_rising_sell / entry_quality_hid_bull_div_sell | ea/FORGE.mq5:5668,5684 | config/gate_legend.json:64,149 | No | PASS |
| entry_quality_m30_not_bearish | ea/FORGE.mq5:5747 | config/gate_legend.json:174 | No | PASS |
| entry_quality_h4_rsi_buy_blocked / h4_adx_buy_blocked / h4_rsi_sell_blocked / h4_adx_sell_blocked | ea/FORGE.mq5:5384,5393,5761,5773 | config/gate_legend.json:164,169,154,159 | No | PASS |
| m1 / regime_countertrend / no_setup / entry_quality_atr_ext / rr_too_low / execution_failed | ea/FORGE.mq5:5859,5867,5893,5912,5974,6190 | config/gate_legend.json:234,239,14,39,214,244 | No | PASS |
| open_group_* dynamic reasons | ea/FORGE.mq5:6857-7024 | No | config/gate_legend.json:11 | PASS |
| warmup_* dynamic reasons | ea/FORGE.mq5:4945 | No | config/gate_legend.json:10 | PASS |

## Section 1 — BB_BREAKOUT BUY Gates
| # | Gate | EA file:line | Config key=value (scalper_config.json) | Status | Notes |
|---|------|-------------|---------------------------------------|--------|-------|
| 1 | Previous M5 close above upper BB | ea/FORGE.mq5:5329-5332 | indicators.bb_period=20, bb_deviation=2.0 (config/scalper_config.json:119-120) | PASS | Implements doc gate 1. |
| 2 | RSI > 40 | ea/FORGE.mq5:5331 | bb_breakout.rsi_buy_min=40 (config/scalper_config.json:36) | PASS | Matches doc. |
| 3 | RSI < 78 | ea/FORGE.mq5:5333-5340 | bb_breakout.rsi_buy_ceil=78 (config/scalper_config.json:54) | PASS | Matches doc. |
| 4 | M5 trend bullish | ea/FORGE.mq5:5318,5332 | EMA 20/50 periods in config/scalper_config.json:122-123 | PASS | Uses m5_trend_strength > threshold. |
| 5 | M15 flat or bullish | ea/FORGE.mq5:5320-5324,5332 | bb_breakout.require_m15_agree=true (config/scalper_config.json:38) | PASS | Matches doc. |
| 6 | H1 not strongly bearish | ea/FORGE.mq5:5332 | min_h1_bear_strength is SELL-only at ea/FORGE.mq5:5544-5545 | WARNING | BUY uses h1_ok_buy from earlier MTF logic; exact assignment is outside this excerpt and not independently decomposed in the intent doc. |
| 7 | H1 DI+ >= DI- when M5 ADX < 28 | ea/FORGE.mq5:5343-5354 | require_h1_di_buy=1, counter_buy_adx_threshold=28 (config/scalper_config.json:63-64) | PASS | Matches doc. |
| 8 | OsMA positive and rising | ea/FORGE.mq5:5356-5375 | require_macd_buy=1, macd=3/10/16 (config/scalper_config.json:80-83) | PASS | Matches doc. |
| 9 | Re-entry ATR extension <= 2.0 | ea/FORGE.mq5:5898-5922 | max_reentry_atr_ext=2 (config/scalper_config.json:75) | PASS | Matches doc. |

## Section 2 — BB_BREAKOUT SELL Gates
| # | Gate | EA file:line | Config key=value (scalper_config.json) | Status | Notes |
|---|------|-------------|---------------------------------------|--------|-------|
| 1 | Previous M5 close below lower BB | ea/FORGE.mq5:5538-5543 | indicators.bb_period=20, bb_deviation=2.0 (config/scalper_config.json:119-120) | PASS | Implements doc gate 1. |
| 2 | RSI < 60 | ea/FORGE.mq5:5542 | rsi_sell_max=60 (config/scalper_config.json:37) | PASS | Matches doc. |
| 3 | RSI floor | ea/FORGE.mq5:5621-5635 | rsi_sell_floor=33 (config/scalper_config.json:55) | FAIL | Intent doc still says rsi_sell_floor=30 at docs/FORGE_ENTRY_CONDITIONS.md:125. Active v2.7.21 is 33. |
| 4 | ADX >= 25 for SELL | ea/FORGE.mq5:5571-5576 | adx_min_sell=25 (config/scalper_config.json:61) | PASS | Matches doc. |
| 5 | ADX lookback >= 25 six bars ago | ea/FORGE.mq5:5641-5651 | adx_min_sell_lookback_bars=6 (config/scalper_config.json:62) | PASS | Matches doc. |
| 6 | M15 ADX < 55 extreme block | ea/FORGE.mq5:5559-5568 | safety.breakout_adx_sell_block_threshold=55 and bb_breakout.adx_sell_block_threshold=55 (config/scalper_config.json:116,222) | PASS | Code reads breakout sell block threshold into g_sc; active JSON duplicates the key. |
| 7 | H1 DI- > DI+ with no ADX bypass | ea/FORGE.mq5:5587-5599 | require_h1_di_sell=1 (config/scalper_config.json:65) | PASS | Matches doc and known asymmetry. |
| 8 | M5 trend bearish | ea/FORGE.mq5:5319,5543 | EMA 20/50 periods in config/scalper_config.json:122-123 | PASS | Matches doc. |
| 9 | M15 flat or bearish | ea/FORGE.mq5:5321-5324,5543 | require_m15_agree=true (config/scalper_config.json:38) | PASS | Matches doc. |
| 10 | H1 trend <= -0.2 | ea/FORGE.mq5:5544-5545 | min_h1_bear_strength=0.2 (config/scalper_config.json:76) | PASS | Matches doc. |
| 11 | OsMA negative and falling | ea/FORGE.mq5:5689-5709 | require_macd_sell=1, macd=3/10/16 (config/scalper_config.json:79-83) | PASS | Matches doc. |
| 12 | M30 bearish when ADX >= 25 | ea/FORGE.mq5:5732-5748 | require_m30_bear_sell=1, m30_bear_adx_min=25 (config/scalper_config.json:77-78) | PASS | Matches doc. |
| 13 | RSI not rising when ADX < 40 | ea/FORGE.mq5:5656-5669 | require_rsi_declining_sell=1, rsi_decl_sell_adx_threshold=40 (config/scalper_config.json:58,113) | PASS | Matches doc. |
| 14 | H1 MACD sell disabled | ea/FORGE.mq5:5712-5727 | require_h1_macd_sell=0 (config/scalper_config.json:66) | PASS | Disabled as documented. |
| 15 | Hidden bullish divergence blocks SELL | ea/FORGE.mq5:5674-5685 | block_hid_bull_sell=1 (config/scalper_config.json:114) | PASS | Matches doc. |
| 16 | Re-entry ATR extension <= 2.0 | ea/FORGE.mq5:5898-5922 | max_reentry_atr_ext=2 (config/scalper_config.json:75) | PASS | Matches doc. |

## Section 3 — Full Lot Path
For each factor in combined_lot_factor:
| Factor | BUY ADX=38 | SELL ADX=38 | EA line | Status |
|--------|------------|-------------|---------|--------|
| inside_band_factor | 1.0 | 1.0 if below lower BB; 0.25 if inside band | ea/FORGE.mq5:6057-6063 | PASS |
| near_floor_factor | 1.0 | 0.25 only on crash bypass with RSI <=25 | ea/FORGE.mq5:6065-6073 | PASS |
| stack_factor | 1.0 for first same-direction group | 0.25 for second same-direction open group | ea/FORGE.mq5:6075-6081 | PASS |
| adx_lot_factor | 1.0 | Uses M15 ADX when enabled; at ADX=38 mid factor=1.0 | ea/FORGE.mq5:6083-6098 | PASS |
| bounce_factor | 1.0 for breakout | 1.0 for breakout | ea/FORGE.mq5:6100-6106 | PASS |
| active full lot value | fixed_lot=0.25, not 0.08 | fixed_lot=0.25, not 0.08 | config/scalper_config.json:240-243 | FAIL |

## Section 4 — ADX-Conditional Leg Count
EA adjusts breakout base_n by ADX at ea/FORGE.mq5:6016-6028, resolves final count at ea/FORGE.mq5:6029-6031, caps unclear H1/H4 at ea/FORGE.mq5:6032-6045, and caps XAU SELL at ea/FORGE.mq5:6047-6053. Active config is min_num_trades=2, max_num_trades=30, staged_initial_legs=10, native_legs_max_when_unclear=5, gold_native_max_sell_legs=10 (config/scalper_config.json:243-254). **Status: WARNING** because docs/FORGE_ENTRY_CONDITIONS.md:96-106 still describes a narrower v2.7.15-era table and staged_initial_legs=8.

## Section 5 — TP3 Live Staging
TP3 runner staging is implemented: group TP3 is set for breakout groups at ea/FORGE.mq5:6207-6213 and live promotion from TP2 to TP3 is at ea/FORGE.mq5:1614-1650. Active tp3_atr_mult=2.5 (config/scalper_config.json:45). **Status: PASS**.

## Section 6 — Direction-Split TP1
BUY TP1 uses tp1_buy_atr_mult at ea/FORGE.mq5:5515-5517 and SELL TP1 uses tp1_sell_atr_mult at ea/FORGE.mq5:5820-5822. Active config has tp1_buy_atr_mult=0.5 and tp1_sell_atr_mult=0.4 (config/scalper_config.json:42-43). **Status: PASS**.

## Section 7 — Crash-Sell Bypass
Crash bypass requires H1 bear, H4 bear, RSI > crash min, ADX <= max, and M15 ADX >= min at ea/FORGE.mq5:5602-5615. Active values are h1h4_crash_sell=1, rsi_min=20, adx_max=40, min_m15_adx=25 (config/scalper_config.json:56-60). **Status: PASS**.

## Section 8 — Variable Integrity
| FORGE_ Variable | In sync script | In .env.example | Config value (active) | Default value | Status |
|-----------------|----------------|-----------------|-----------------------|---------------|--------|
| FORGE_FIXED_LOT | scripts/sync_scalper_config_from_env.py:61 | .env.example:214-215 | 0.25 | 0.02 | PASS |
| FORGE_MIN_NUM_TRADES / FORGE_MAX_NUM_TRADES | scripts/sync_scalper_config_from_env.py:62-63 | .env.example:216-222 | 2 / 30 | 1 / 30 | PASS |
| FORGE_GOLD_NATIVE_MAX_SELL_LEGS | scripts/sync_scalper_config_from_env.py:64 | .env.example:224-226 | 10 | 2 | PASS |
| FORGE_NATIVE_LEGS_MAX_WHEN_UNCLEAR | scripts/sync_scalper_config_from_env.py:65 | .env.example:228-230 | 5 | 3 | PASS |
| FORGE_STAGED_INITIAL_LEGS | scripts/sync_scalper_config_from_env.py:68 | .env.example:232-235 | 10 | 1 | PASS |
| FORGE_STAGED_ADD_MIN_FAVORABLE_POINTS | scripts/sync_scalper_config_from_env.py:70 | .env.example:239-241 | 5 | 35 | PASS |
| FORGE_BREAKOUT_RSI_BUY_CEIL / RSI_SELL_FLOOR | scripts/sync_scalper_config_from_env.py:85-86 | .env.example:300-303 | 78 / 33 | 70 / 30 | PASS |
| FORGE_BREAKOUT_REQUIRE_H1_DI_BUY / SELL | scripts/sync_scalper_config_from_env.py:95-97 | .env.example:313-318 | 1 / 1 | 0 / 0 | PASS |
| FORGE_BREAKOUT_REQUIRE_H1_MACD_BUY | scripts/sync_scalper_config_from_env.py:101 | .env.example:319-322 | 0 | 0 | PASS |
| FORGE_BREAKOUT_SAME_DIR_COOLDOWN_SECONDS | scripts/sync_scalper_config_from_env.py:103 | .env.example:323-325 | 900 | 0 | PASS |
| FORGE_BREAKOUT_FAILED_* | scripts/sync_scalper_config_from_env.py:105-110 | .env.example:327-339 | enabled, 4, 68, 3.0, samebar=1 | disabled, 4, 75, 3.0, samebar=0 | PASS |
| FORGE_BREAKOUT_REQUIRE_PSAR_ALIGN | scripts/sync_scalper_config_from_env.py:111 | .env.example:341-344 | 1 | 0 | PASS |
| FORGE_BREAKOUT_REQUIRE_MACD_BUY | scripts/sync_scalper_config_from_env.py:124 | .env.example:377-379 | 1 | 0 | PASS |
| FORGE_BREAKOUT_BUY_SL_ATR_MULT | scripts/sync_scalper_config_from_env.py:197 | .env.example:389-392 | 3.0 | 0.0 | PASS |
| FORGE_BREAKOUT_TP1_* | scripts/sync_scalper_config_from_env.py:198-201 | .env.example:393-399 | 0.4 / BUY 0.5 / SELL 0.4 / close 60 | 1.0 / 0 / 0 / close 40 | PASS |
| FORGE_BREAKOUT_ADX_LOT_* | scripts/sync_scalper_config_from_env.py:205-209 | .env.example:418-424 | use_m15=1, mid=35/high=45, factors=1/0.5 | use_m15=1, factors=0.25/0.125 | PASS |
| FORGE_SELL_STOP_CONT_* | scripts/sync_scalper_config_from_env.py:145-156 | .env.example:456-483 | enabled, SL mult 3.5, regime guard 1 | disabled, SL mult 1.5, regime guard 0 | PASS |
| FORGE_BUY_LIMIT_RECOVERY_* | scripts/sync_scalper_config_from_env.py:159-163 | .env.example:486-494 | enabled, RSI 35, lot factor 0.25 | disabled, RSI 35, lot factor 0.25 | PASS |
| FORGE_MIN_ENTRY_ATR / BODY / DIRECTION / BB_EXPANSION | scripts/sync_scalper_config_from_env.py:185-189 | .env.example:516-524 | 1.0 / 0.25 / 1 / 0 | 3.5 / 0.4 / 2 / 1 | PASS |
| FORGE_SESSION_NY_SELL_CUTOFF_UTC | scripts/sync_scalper_config_from_env.py:190 | .env.example:529-532 | 0 | 17 | PASS |

## Section 9 — scribe.py / regime.py / schemas/ Cross-Check
| Check | File:line | Status | Notes |
|-------|-----------|--------|-------|
| forge_signals CREATE includes current columns | python/scribe.py:119-148 | PASS | Includes macd_histogram, m15_adx, lot_factor in base schema. |
| ALTER migrations for macd_histogram/m15_adx/lot_factor | python/scribe.py:558-568 | PASS | Known schema gap is now addressed. |
| sync reads optional source columns | python/scribe.py:867-876,971-976,1022-1029 | PASS | Handles older journals with NULL fallback. |
| forge_journal_trades carries aurum_run_id | python/scribe.py:578-599,657-658 | PASS | Backtest isolation available. |
| Regime labels | python/regime.py:320-345,530-549 | PASS | Uses RANGE, TREND_BULL, TREND_BEAR, VOLATILE; EA cascade guard checks RANGE/blank at ea/FORGE.mq5:6571-6575. |
| OpenAPI examples | schemas/openapi.yaml:828-839 | WARNING | Examples do not include macd_histogram/m15_adx/lot_factor, but this is documentation incompleteness, not runtime breakage. |

## Section 10 — Dashboard / API Consistency
| Check | dashboard:line | api:line | Status | Notes |
|-------|----------------|----------|--------|-------|
| Backtest selected run guard | dashboard/app.js:1472-1478 | python/athena_api.py:1697-1708 | PASS | UI renders detail only when btSelRun===btDetail.meta.aurum_run_id. |
| Run list fields | dashboard/app.js:1425-1457 | python/athena_api.py:1630-1664 | PASS | aurum_run_id, taken, skipped, win_rate_pct, total_pnl align. |
| TAKEN ENTRIES detail shape | dashboard/app.js:1644-1695 | python/athena_api.py:1916-1927 | PASS | UI expects legs, lot_per_leg, pnl, result; API returns them. |
| TAKEN ENTRIES leg math | dashboard/app.js:1694-1695 | python/athena_api.py:1895-1903 | PASS | API derives legs from |TP1 comments and lot_per_leg from non-zero volume. |
| Cascade P&L attribution | dashboard/app.js:1684-1695 | python/athena_api.py:1822-1881 | PASS | API scans offsets 20000..20009 and sums cascade/base attributed P&L. |
| Run ID WHERE filters | dashboard/app.js:643-647 | python/athena_api.py:1704-1933 | PASS | Detail endpoint uses aurum_run_id=? on meta, trades, signals, gates, taken, and pnl curve queries. |
| Gate legend API | dashboard/app.js:608-615,1763-1778 | python/athena_api.py:1973-1982 | PASS | Dashboard code and API shape align. |

## Section 11 — Scripts / Tests Consistency
| Check | File:line | Status | Notes |
|-------|-----------|--------|-------|
| Dead FORGE env test | tests/api/test_forge_27x_gates.py:257-279 | PASS | Matches mandatory check A and has whitelist for FORGE_SCALPER_MODE. |
| Lowercase FORGE-like env test | tests/api/test_forge_27x_gates.py:229-253 | PASS | Protects against lowercase config-looking dead vars. |
| Required new config keys tests | tests/api/test_forge_27x_gates.py:134-152 | PASS | Covers block_hid_bull_sell, h1h4_crash_sell_min_m15_adx, require_h1_di_sell, breakout_adx_lot_use_m15. |
| Stale docs in analysis/research | docs/FORGE_ENTRY_CONDITIONS.md:1-6,96-106,115,125,218-222,256 | FAIL | Intent doc still asserts v2.7.15, 0.08 full lot, session cutoff 18, rsi floor 30, staged_initial_legs=8, slots [2..8] max 7. |
| Research docs mention old line numbers | docs/research/FORGE_ENHANCEMENT_FROM_MQL5_ARTICLES.md:23,114,246-248 | WARNING | Stale line references only; not runtime behavior. |

## Issues Found (Consolidated)
| # | Severity | Section | Description | Action |
|---|----------|---------|-------------|--------|
| 1 | High | Sections 1-2, 11 | FORGE_ENTRY_CONDITIONS.md is stale: it says v2.7.15 while active config and EA are v2.7.21 (config/scalper_config.json:2, ea/FORGE.mq5:63, docs/FORGE_ENTRY_CONDITIONS.md:1-6). | Update intent doc version and changelog through v2.7.21. |
| 2 | High | Sections 2, 7 | SELL RSI floor in doc is 30, active config is 33 (docs/FORGE_ENTRY_CONDITIONS.md:125, config/scalper_config.json:55). | Update SELL gate table and quick reference. |
| 3 | High | Section 3 | Full lot doc says 0.08 per leg, active fixed_lot is 0.25 (docs/FORGE_ENTRY_CONDITIONS.md:46, config/scalper_config.json:242). | Rewrite lot examples to active config or explicitly mark historical. |
| 4 | Medium | Sections 2, 11 | Session cutoff doc says SELL blocked after 18:00 UTC, active config disables cutoff with 0 (docs/FORGE_ENTRY_CONDITIONS.md:115, config/scalper_config.json:215). | Update session section to disabled/current behavior. |
| 5 | Medium | Sections 4, 11 | Leg-count doc still references staged_initial_legs=8 and old leg table; active staged_initial_legs=10 and min/max range is 2/30 (docs/FORGE_ENTRY_CONDITIONS.md:96-106, config/scalper_config.json:243-254). | Recompute table from active config. |
| 6 | Medium | Sections 5, 6 | BUY SL override exists and is active at 3.0 but intent doc still lists BUY SL as 2.0x ATR (docs/FORGE_ENTRY_CONDITIONS.md:87, config/scalper_config.json:39-40, ea/FORGE.mq5:5505-5514). | Add v2.7.18 BUY-only SL override to trade parameters. |
| 7 | Low | Section 9 | OpenAPI/examples omit newer forge_signals analysis columns even though schema/migrations support them. | Refresh examples if operators use OpenAPI for SQL snippets. |

## Overall Verdict
Runtime code/config validation is mostly healthy: v2.7.21 gates are present in the EA, FORGE_* env overrides are mapped/documented, gate legend coverage is complete, schema migrations cover the known macd_histogram/m15_adx/lot_factor gap, and dashboard/API backtest math now includes run ID guards plus cascade offsets. The main problem is documentation drift in FORGE_ENTRY_CONDITIONS.md: it is still a v2.7.15 intent document and no longer matches active risk, lot, session, RSI, BUY-SL, and staging parameters.
