#!/usr/bin/env python3
"""Emit config/scalper_config.json from scalper_config.defaults.json + VERSION + optional .env FORGE_* keys.

Reads:  config/scalper_config.defaults.json, VERSION, .env (optional)
Writes: config/scalper_config.json; copies to MT5/scalper_config.json when that dir exists.

Do not use scalper_config.json as the hand-edited source — it is overwritten. See docs/SCALPER_CONFIG_PIPELINE.md.
"""
from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
VERSION_PATH = ROOT / "VERSION"
# Editable baseline (commit this). Generated runtime file is SCALPER_CONFIG_PATH.
SCALPER_DEFAULTS_PATH = ROOT / "config" / "scalper_config.defaults.json"
SCALPER_CONFIG_PATH = ROOT / "config" / "scalper_config.json"

# env_key -> (section, key, type, min, max)
# Leg count: FORGE_MIN_NUM_TRADES / FORGE_MAX_NUM_TRADES or camelCase forgeMinNumTrades / forgeMaxNumTrades.
# Legacy FORGE_NUM_TRADES or forgeNumTrades (if neither min nor max is set) writes both bounds to the same value.
MAPPING: dict[str, tuple[str, str, str, float | None, float | None]] = {
    "FORGE_BOUNCE_RECLAIM_PCT": ("bb_bounce", "bounce_reclaim_pct", "float", 0.0, 100.0),
    "FORGE_BOUNCE_REQUIRE_REJECTION_CANDLE": ("bb_bounce", "bounce_require_rejection_candle", "bool01", None, None),
    "FORGE_FAST_LOCK_MIN_HOLD_SEC_BOUNCE": ("safety", "fast_lock_min_hold_sec_bounce", "int", 0.0, None),
    "FORGE_FAST_LOCK_MIN_HOLD_SEC_BREAKOUT": ("safety", "fast_lock_min_hold_sec_breakout", "int", 0.0, None),
    "FORGE_FAST_LOCK_BREATH_MULT": ("safety", "fast_lock_breath_mult", "float", 0.75, 2.5),
    "FORGE_FAST_LOCK_MIN_PROFIT_POINTS": ("safety", "fast_lock_min_profit_points", "float", 0.0, None),
    "FORGE_BOUNCE_MIN_TP1_ATR_MULT": ("bb_bounce", "min_tp1_atr_mult", "float", 0.0, 5.0),
    "FORGE_BOUNCE_MIN_TP2_ATR_MULT": ("bb_bounce", "min_tp2_atr_mult", "float", 0.0, 10.0),
    "FORGE_ADX_HYSTERESIS_ENABLED": ("safety", "adx_hysteresis_enabled", "bool01", None, None),
    "FORGE_ADX_HYSTERESIS_APPLY_IN_TESTER": ("safety", "adx_hysteresis_apply_in_tester", "bool01", None, None),
    # Native news filter
    "FORGE_NEWS_FILTER_ENABLED": ("safety", "news_filter_enabled", "bool01", None, None),
    "FORGE_NEWS_FILTER_CURRENCIES": ("safety", "news_filter_currencies", "string", None, None),
    "FORGE_NEWS_FILTER_LOW_BEFORE": ("safety", "news_filter_low_before", "int", 0.0, 240.0),
    "FORGE_NEWS_FILTER_LOW_AFTER": ("safety", "news_filter_low_after", "int", 0.0, 240.0),
    "FORGE_NEWS_FILTER_MEDIUM_BEFORE": ("safety", "news_filter_medium_before", "int", 0.0, 240.0),
    "FORGE_NEWS_FILTER_MEDIUM_AFTER": ("safety", "news_filter_medium_after", "int", 0.0, 240.0),
    "FORGE_NEWS_FILTER_HIGH_BEFORE": ("safety", "news_filter_high_before", "int", 0.0, 240.0),
    "FORGE_NEWS_FILTER_HIGH_AFTER": ("safety", "news_filter_high_after", "int", 0.0, 240.0),
    "FORGE_NEWS_FILTER_SPECIAL": ("safety", "news_filter_special", "string", None, None),
    "FORGE_NEWS_FILTER_HARD_FLOOR_MIN": ("safety", "news_filter_hard_floor_min", "int", 0.0, 60.0),
    "FORGE_NEWS_FILTER_TIGHTEN_PCT": ("safety", "news_filter_tighten_pct", "float", 0.0, 1.0),
    "FORGE_NEWS_FILTER_BLOCK_PCT": ("safety", "news_filter_block_pct", "float", 0.0, 1.0),
    "FORGE_NEWS_FILTER_TIGHTEN_RSI_BUY": ("safety", "news_filter_tighten_rsi_buy", "float", 50.0, 70.0),
    "FORGE_NEWS_FILTER_TIGHTEN_RSI_SELL": ("safety", "news_filter_tighten_rsi_sell", "float", 30.0, 50.0),
    "FORGE_NEWS_FILTER_REFRESH_SEC": ("safety", "news_filter_refresh_sec", "int", 60.0, None),
    "FORGE_NEWS_FILTER_APPLY_IN_TESTER": ("safety", "news_filter_apply_in_tester", "bool01", None, None),
    "FORGE_ADX_TREND_ENTER": ("safety", "adx_trend_enter", "float", 0.0, 100.0),
    "FORGE_ADX_TREND_EXIT": ("safety", "adx_trend_exit", "float", 0.0, 100.0),
    "FORGE_SELL_LOSS_GRACE_SEC": ("safety", "sell_loss_grace_sec", "int", 0.0, None),
    "FORGE_SELL_LOSS_GRACE_ADVERSE_POINTS": ("safety", "sell_loss_grace_adverse_points", "float", 0.0, None),
    "FORGE_INPUTS_OVERRIDE_LOT_SIZING": ("lot_sizing", "inputs_override_lot_sizing", "bool01", None, None),
    "FORGE_LOT_SIZING_SOURCE": ("lot_sizing", "lot_sizing_source", "lot_source", None, None),
    "FORGE_FIXED_LOT": ("lot_sizing", "fixed_lot", "float", 0.01, None),
    # 2.7.40 — Global lot multiplier on fixed_lot. Env-side mirror of MT5 input ScalperLotFactor.
    # 1.0 = no-op (default). 0.5 = half-sizing (de-risk). 2.0 = double (size-up day).
    # MT5 input wins when != 1.0; this env value wins when MT5 input stays at default 1.0.
    "FORGE_GLOBAL_SCALPER_LOT_FACTOR": ("lot_sizing", "scalper_lot_factor", "float", 0.05, 10.0),
    # 2.7.41 — Comma-separated setup_type list that BYPASSES max_open_same_direction.
    # Risk-1 setups (BB_BREAKOUT_RETEST, BUY_LIMIT_RECOVERY) bypass the per-direction
    # concurrent-open cap so high-confidence signals are not throttled.
    "FORGE_MAX_OPEN_SAME_DIRECTION_BYPASS_SETUPS": ("safety", "max_open_same_direction_bypass_setups", "string", None, None),
    # 2.7.41 — Regime-aware cooldown bypass. When a per-setup cooldown (BB_BREAKOUT same-dir,
    # BB_PULLBACK_SCALP, BULL_DAY_DIP_BUY reentry) is active, allow the entry if the last
    # group in this direction WON TP1 recently AND direction matches g_regime_label AND M5
    # ADX confirms trend. Bypasses do NOT apply after a loss (loss cooldown still respected).
    "FORGE_COOLDOWN_BYPASS_ON_TP_WITH_TREND": ("safety", "cooldown_bypass_on_tp_with_trend", "bool01", None, None),
    "FORGE_COOLDOWN_BYPASS_WINDOW_SEC":       ("safety", "cooldown_bypass_window_sec",       "int",   30.0, 7200.0),
    "FORGE_COOLDOWN_BYPASS_MIN_ADX":          ("safety", "cooldown_bypass_min_adx",          "float", 0.0, 80.0),
    "FORGE_COOLDOWN_BYPASS_MIN_REFIRE_SEC":   ("safety", "cooldown_bypass_min_refire_sec",   "int",   0.0, 600.0),
    "FORGE_COOLDOWN_BYPASS_SETUPS":           ("safety", "cooldown_bypass_setups",           "string", None, None),
    "FORGE_MIN_NUM_TRADES": ("lot_sizing", "min_num_trades", "int", 1.0, 30.0),
    "FORGE_MAX_NUM_TRADES": ("lot_sizing", "max_num_trades", "int", 1.0, 30.0),
    "FORGE_GOLD_NATIVE_MAX_SELL_LEGS": ("lot_sizing", "gold_native_max_sell_legs", "int", 0.0, 30.0),
    "FORGE_NATIVE_LEGS_MAX_WHEN_UNCLEAR": ("lot_sizing", "native_legs_max_when_unclear", "int", 0.0, 30.0),
    "FORGE_NATIVE_LEGS_CLEAR_TREND_FACTOR": ("lot_sizing", "native_legs_clear_trend_factor", "float", 1.0, 3.0),
    "FORGE_NATIVE_FORCE_STAGED_SCALE_IN": ("lot_sizing", "native_force_staged_scale_in", "bool01", None, None),
    "FORGE_STAGED_INITIAL_LEGS":          ("lot_sizing", "staged_initial_legs",          "int",    1.0, 30.0),
    "FORGE_STAGED_ADD_INTERVAL_SEC":      ("lot_sizing", "staged_add_interval_sec",      "int",    5.0, 300.0),
    "FORGE_STAGED_ADD_MIN_FAVORABLE_POINTS": ("lot_sizing", "staged_add_min_favorable_points", "float", 0.0, 5000.0),
    "FORGE_WAVE_CONFIRMATION_LOT_MULT":      ("lot_sizing", "wave_confirmation_lot_mult",      "float", 1.0, 10.0),
    "FORGE_NATIVE_SCALPER_USE_LIMIT_ENTRY": ("lot_sizing", "native_scalper_use_limit_entry", "bool01", None, None),
    "FORGE_BOUNCE_REQUIRE_H1_DIRECTION": ("bb_bounce", "bounce_require_h1_direction", "bool01", None, None),
    "FORGE_BOUNCE_HTF_BIAS": ("bb_bounce", "bounce_htf_bias", "bounce_htf_bias", None, None),
    "FORGE_BOUNCE_BLOCK_HTF_TREND_ALIGN": ("bb_bounce", "bounce_block_htf_trend_align", "bool01", None, None),
    "FORGE_BOUNCE_RESPECT_ADX_MAX_IN_TESTER": ("bb_bounce", "bounce_respect_adx_max_in_tester", "bool01", None, None),
    "FORGE_BOUNCE_RESPECT_H1_FILTER_IN_TESTER": ("bb_bounce", "bounce_respect_h1_filter_in_tester", "bool01", None, None),
    "FORGE_BREAKOUT_ADX_MIN": ("bb_breakout", "adx_min", "float", 5.0, 80.0),
    "FORGE_BOUNCE_REQUIRE_BAR0_CONFIRM": ("bb_bounce", "bounce_require_bar0_confirm", "bool01", None, None),
    "FORGE_BOUNCE_MIN_CANDLE_SCORE": ("bb_bounce", "bounce_min_candle_score", "int", 0.0, 3.0),
    "FORGE_BOUNCE_REQUIRE_LIQUIDITY_ZONE": ("bb_bounce", "bounce_require_liquidity_zone", "bool01", None, None),
    "FORGE_VP_LOOKBACK": ("indicators", "vp_lookback", "int", 20.0, 500.0),
    "FORGE_VP_BINS": ("indicators", "vp_bins", "int", 10.0, 200.0),
    "FORGE_BREAKOUT_USE_RETEST": ("bb_breakout", "breakout_use_retest", "bool01", None, None),
    "FORGE_BREAKOUT_RETEST_MAX_BARS": ("bb_breakout", "breakout_retest_max_bars", "int", 1.0, 20.0),
    "FORGE_BREAKOUT_RSI_BUY_CEIL": ("bb_breakout", "rsi_buy_ceil", "float", 50.0, 100.0),
    "FORGE_BREAKOUT_RSI_SELL_FLOOR": ("bb_breakout", "rsi_sell_floor", "float", 0.0, 50.0),
    "FORGE_BREAKOUT_H1H4_CRASH_SELL": ("bb_breakout", "h1h4_crash_sell", "bool01", None, None),
    "FORGE_BREAKOUT_H1H4_CRASH_SELL_RSI_MIN": ("bb_breakout", "h1h4_crash_sell_rsi_min", "float", 10.0, 35.0),
    # ── Fast-moving / rising-price scalping gates (v2.7.6) ────────────────
    # Stricter ADX floor for SELL entries only (SELL breakouts fail more at weak ADX than BUYs)
    "FORGE_BREAKOUT_ADX_MIN_SELL":               ("bb_breakout", "adx_min_sell",                "float", 10.0, 80.0),
    # Bars back to check for ADX spike-from-flat before allowing a SELL (0=disabled; 6=30min window)
    "FORGE_BREAKOUT_ADX_MIN_SELL_LOOKBACK_BARS": ("bb_breakout", "adx_min_sell_lookback_bars",  "int",   0.0,  20.0),
    # H1 Wilder DI+/DI- gate: block BUY when H1 DI- > DI+ (bearish directional imbalance)
    "FORGE_BREAKOUT_REQUIRE_H1_DI_BUY":          ("bb_breakout", "require_h1_di_buy",           "bool01", None, None),
    # H1 DI gate for SELL: block SELL when H1 DI+ >= DI- (H1 is bullish — no ADX bypass)
    "FORGE_BREAKOUT_REQUIRE_H1_DI_SELL":         ("bb_breakout", "require_h1_di_sell",          "bool01", None, None),
    # H1 MACD histogram gate for SELL: block SELL when H1 MACD hist >= 0 (H1 bullish momentum; Run 12+)
    "FORGE_BREAKOUT_REQUIRE_H1_MACD_SELL":       ("bb_breakout", "require_h1_macd_sell",        "bool01", None, None),
    # H1 MACD histogram gate for BUY (2.7.17 Run 15 G5002 fix): block BUY when H1 MACD hist < 0
    "FORGE_BREAKOUT_REQUIRE_H1_MACD_BUY":        ("bb_breakout", "require_h1_macd_buy",         "bool01", None, None),
    # BB_BREAKOUT same-direction cooldown in seconds (2.7.17 Run 15 G5002 fix); 0 = disabled
    "FORGE_BREAKOUT_SAME_DIR_COOLDOWN_SECONDS":  ("bb_breakout", "same_dir_cooldown_seconds",   "int",    0.0,  3600.0),
    # 2.7.19 — Failed-breakout-pullback gate (Run 15 G5013/G5015 fix); 0 = disabled
    "FORGE_BREAKOUT_FAILED_GATE_ENABLED":        ("bb_breakout", "failed_gate_enabled",         "bool01", None, None),
    "FORGE_BREAKOUT_FAILED_LOOKBACK_BARS":       ("bb_breakout", "failed_lookback_bars",        "int",    1.0,  20.0),
    "FORGE_BREAKOUT_FAILED_MIN_PEAK_RSI":        ("bb_breakout", "failed_min_peak_rsi",         "float",  50.0, 90.0),
    "FORGE_BREAKOUT_FAILED_MIN_RSI_DROP":        ("bb_breakout", "failed_min_rsi_drop",         "float",  0.0,  30.0),
    # 2.7.20 — same-bar hard block + PSAR alignment
    "FORGE_BREAKOUT_FAILED_SAME_BAR_HARD_BLOCK": ("bb_breakout", "failed_same_bar_hard_block",  "bool01", None, None),
    "FORGE_BREAKOUT_REQUIRE_PSAR_ALIGN":         ("bb_breakout", "require_psar_align",          "bool01", None, None),
    # ADX ceiling above which the H1 DI gate auto-disables (strong trend overrides the DI check)
    "FORGE_BREAKOUT_COUNTER_BUY_ADX_THRESHOLD":  ("bb_breakout", "counter_buy_adx_threshold",   "float", 0.0,  80.0),
    # Max ATR multiples price can extend from first entry before re-entry is blocked (0=disabled)
    "FORGE_BREAKOUT_MAX_REENTRY_ATR_EXT":        ("bb_breakout", "max_reentry_atr_ext",         "float", 0.0,  10.0),
    # M30 EMA bearish confirmation gate (2.7.9 Feature 3)
    "FORGE_BREAKOUT_REQUIRE_M30_BEAR_SELL":      ("bb_breakout", "require_m30_bear_sell",      "bool01", None, None),
    "FORGE_BREAKOUT_REQUIRE_RSI_DECLINING_SELL": ("bb_breakout", "require_rsi_declining_sell", "bool01", None, None),
    "FORGE_BREAKOUT_BLOCK_HID_BULL_SELL":        ("bb_breakout", "block_hid_bull_sell",         "bool01", None, None),
    "FORGE_BREAKOUT_RSI_DECL_SELL_ADX_THRESHOLD":("bb_breakout", "rsi_decl_sell_adx_threshold","float",  10.0, 80.0),
    "FORGE_BREAKOUT_M30_BEAR_ADX_MIN":      ("bb_breakout", "m30_bear_adx_min",      "float", 0.0, 80.0),
    # OsMA(fast,slow,signal) histogram gate — MACD Histogram MC 4-quadrant approach
    "FORGE_BREAKOUT_REQUIRE_MACD_SELL": ("bb_breakout", "require_macd_sell", "bool01", None, None),
    "FORGE_BREAKOUT_REQUIRE_MACD_BUY":  ("bb_breakout", "require_macd_buy",  "bool01", None, None),
    "FORGE_BREAKOUT_MACD_FAST":         ("bb_breakout", "macd_fast",   "int", 1.0, 50.0),
    "FORGE_BREAKOUT_MACD_SLOW":         ("bb_breakout", "macd_slow",   "int", 1.0, 100.0),
    "FORGE_BREAKOUT_MACD_SIGNAL":       ("bb_breakout", "macd_signal", "int", 1.0, 50.0),
    # SELL LIMIT L1 — pending SELL above entry to catch RSI bounce toward Bear Resistance
    "FORGE_BREAKOUT_SELL_LIMIT_ENABLED":       ("bb_breakout", "sell_limit_enabled",       "bool01", None, None),
    "FORGE_BREAKOUT_SELL_LIMIT_ATR_MULT":      ("bb_breakout", "sell_limit_atr_mult",      "float", 0.0, 5.0),
    "FORGE_BREAKOUT_SELL_LIMIT_LOT_FACTOR":    ("bb_breakout", "sell_limit_lot_factor",    "float", 0.0, 1.0),
    "FORGE_BREAKOUT_SELL_LIMIT_EXPIRY_BARS":   ("bb_breakout", "sell_limit_expiry_bars",   "int",   1.0, 50.0),
    # SELL LIMIT L2 — second cascade level (2.7.10); in .env for hot-reload control
    "FORGE_BREAKOUT_SELL_LIMIT_L2_ENABLED":    ("bb_breakout", "sell_limit_l2_enabled",    "bool01", None, None),
    "FORGE_BREAKOUT_SELL_LIMIT_L2_ATR_MULT":   ("bb_breakout", "sell_limit_l2_atr_mult",   "float", 0.0, 5.0),
    "FORGE_BREAKOUT_SELL_LIMIT_L2_LOT_FACTOR": ("bb_breakout", "sell_limit_l2_lot_factor", "float", 0.0, 1.0),
    # Inside-band lot reduction and ADX SELL block threshold
    "FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR": ("bb_breakout", "sell_inside_band_lot_factor", "float", 0.0, 1.0),
    "FORGE_BREAKOUT_ADX_SELL_BLOCK_THRESHOLD": ("bb_breakout", "adx_sell_block_threshold", "float", 0.0, 100.0),
    # H1+H4 crash SELL — max ADX cap and min H1 bear strength
    "FORGE_BREAKOUT_H1H4_CRASH_SELL_ADX_MAX":  ("bb_breakout", "h1h4_crash_sell_adx_max", "float", 0.0, 100.0),
    "FORGE_BREAKOUT_H1H4_CRASH_SELL_MIN_M15_ADX": ("bb_breakout", "h1h4_crash_sell_min_m15_adx", "float", 0.0, 80.0),
    "FORGE_BREAKOUT_MIN_H1_BEAR_STRENGTH":     ("bb_breakout", "min_h1_bear_strength",    "float", 0.0, 5.0),
    # SELL STOP continuation (2.7.10 Day 2) — disabled by default; enable to capture second impulse after TP1
    "FORGE_SELL_STOP_CONT_ENABLED":      ("bb_breakout", "sell_stop_cont_enabled",      "bool01", None, None),
    "FORGE_SELL_STOP_CONT_ATR_MULT":     ("bb_breakout", "sell_stop_cont_atr_mult",     "float", 0.1, 3.0),
    "FORGE_SELL_STOP_CONT_SL_ATR_MULT":  ("bb_breakout", "sell_stop_cont_sl_atr_mult",  "float", 0.0, 10.0),
    "FORGE_SELL_STOP_CONT_LOT_FACTOR":   ("bb_breakout", "sell_stop_cont_lot_factor",   "float", 0.0, 2.0),
    "FORGE_SELL_STOP_CONT_LEGS":         ("bb_breakout", "sell_stop_cont_legs",         "int",   1.0, 7.0),
    "FORGE_SELL_STOP_CONT_EXPIRY_BARS":  ("bb_breakout", "sell_stop_cont_expiry_bars",  "int",   1.0, 50.0),
    "FORGE_SELL_STOP_CONT_TP_ATR_MULT": ("bb_breakout", "sell_stop_cont_tp_atr_mult",  "float", 0.0, 5.0),
    "FORGE_SELL_STOP_CONT_MIN_RSI":      ("bb_breakout", "sell_stop_cont_min_rsi",      "float", 0.0, 50.0),
    "FORGE_SELL_STOP_CONT_MIN_ADX":      ("bb_breakout", "sell_stop_cont_min_adx",      "float", 0.0, 80.0),
    "FORGE_SELL_STOP_CONT_REQUIRE_H1_DI": ("bb_breakout", "sell_stop_cont_require_h1_di", "bool01", None, None),
    # 2.7.21 — Cascade regime guard (Run 15 G5040 -$1119 cascade fix)
    "FORGE_SELL_STOP_CONT_REQUIRE_TREND_REGIME": ("bb_breakout", "sell_stop_cont_require_trend_regime", "bool01", None, None),
    # BUY LIMIT recovery (2.7.10 Day 3) — Cardwell Bull Support entry at crash low after SELL TP1
    # Captures May-1-style parabolic reversals: RSI bounces from 20 back through 35 = recovery confirmed
    "FORGE_BUY_LIMIT_RECOVERY_ENABLED":      ("bb_breakout", "buy_limit_recovery_enabled",      "bool01", None, None),
    "FORGE_BUY_LIMIT_RECOVERY_MIN_RSI":      ("bb_breakout", "buy_limit_recovery_min_rsi",      "float", 20.0, 70.0),
    "FORGE_BUY_LIMIT_RECOVERY_LOT_FACTOR":   ("bb_breakout", "buy_limit_recovery_lot_factor",   "float", 0.0, 1.0),
    "FORGE_BUY_LIMIT_RECOVERY_EXPIRY_BARS":  ("bb_breakout", "buy_limit_recovery_expiry_bars",  "int",   1.0, 20.0),
    "FORGE_BUY_LIMIT_RECOVERY_SL_ATR_MULT":  ("bb_breakout", "buy_limit_recovery_sl_atr_mult",  "float", 0.1, 5.0),
    # H4 supplemental gates (2.7.10) — disabled by default in .defaults.json; enable per run for testing
    # H4 RSI gate: block SELL when H4 RSI >= h4_rsi_sell_max (Cardwell Bear Resistance exhaustion on H4)
    #              block BUY  when H4 RSI <= h4_rsi_buy_min  (Cardwell Bull Support exhaustion on H4)
    "FORGE_H4_RSI_GATE_ENABLED": ("bb_breakout", "h4_rsi_gate_enabled", "bool01", None, None),
    "FORGE_H4_RSI_SELL_MAX":     ("bb_breakout", "h4_rsi_sell_max",     "float", 30.0, 80.0),
    "FORGE_H4_RSI_BUY_MIN":      ("bb_breakout", "h4_rsi_buy_min",      "float", 20.0, 70.0),
    # H4 ADX gate: block entries when H4 ADX < min threshold (H4 trend not directional — ranging H4)
    "FORGE_H4_ADX_GATE_ENABLED": ("bb_breakout", "h4_adx_gate_enabled", "bool01", None, None),
    "FORGE_H4_ADX_MIN_SELL":     ("bb_breakout", "h4_adx_min_sell",     "float", 0.0, 80.0),
    "FORGE_H4_ADX_MIN_BUY":      ("bb_breakout", "h4_adx_min_buy",      "float", 0.0, 80.0),
    "FORGE_FIB_BIAS_ENABLED": ("indicators", "fib_bias_enabled", "bool01", None, None),
    "FORGE_FIB_TP_ENABLED": ("indicators", "fib_tp_enabled", "bool01", None, None),
    "FORGE_FIB_LOOKBACK": ("indicators", "fib_lookback", "int", 0.0, 500.0),
    "FORGE_RSI_DIV_ENABLED": ("indicators", "rsi_div_enabled", "bool01", None, None),
    "FORGE_RSI_DIV_LOOKBACK": ("indicators", "rsi_div_lookback", "int", 5.0, 200.0),
    "FORGE_RSI_DIV_SWING_BARS": ("indicators", "rsi_div_swing_bars", "int", 1.0, 10.0),
    "FORGE_RSI_DIV_MIN_RSI_DIFF": ("indicators", "rsi_div_min_rsi_diff", "float", 0.0, 20.0),
    "FORGE_RSI_DIV_DRAW_ARROWS": ("indicators", "rsi_div_draw_arrows", "bool01", None, None),
    "FORGE_MIN_SL_ATR_MULT": ("safety", "min_sl_atr_mult", "float", 0.3, 3.0),
    "FORGE_MIN_RR": ("safety", "min_rr", "float", 0.1, 5.0),
    "FORGE_NATIVE_SL_EXTRA_BUFFER_POINTS": ("safety", "native_sl_extra_buffer_points", "float", 0.0, 500.0),
    "FORGE_MIN_ENTRY_ATR": ("safety", "min_entry_atr", "float", 0.0, 50.0),
    "FORGE_ENTRY_QUALITY_BARS": ("safety", "entry_quality_bars", "int", 1.0, 20.0),
    "FORGE_MIN_BODY_RATIO": ("safety", "min_body_ratio", "float", 0.0, 1.0),
    "FORGE_MIN_DIRECTIONAL_BARS": ("safety", "min_directional_bars", "int", 0.0, 20.0),
    "FORGE_REQUIRE_BB_EXPANSION": ("safety", "require_bb_expansion", "bool01", None, None),
    "FORGE_SESSION_NY_SELL_CUTOFF_UTC": ("safety", "session_ny_sell_cutoff_utc", "int", 0.0, 23.0),
    "FORGE_SESSION_LONDON_SELL_CUTOFF_UTC": ("safety", "session_london_sell_cutoff_utc", "int", 0.0, 23.0),
    "FORGE_MAX_OPEN_SAME_DIRECTION": ("safety", "max_open_same_direction", "int", 0.0, 10.0),
    "FORGE_BOUNCE_ADX_MAX": ("bb_bounce", "adx_max", "int", 10.0, 100.0),
    "FORGE_BOUNCE_LOT_FACTOR": ("bb_bounce", "bounce_lot_factor", "float", 0.01, 1.0),
    "FORGE_BOUNCE_SL_ATR_MULT": ("bb_bounce", "sl_atr_mult", "float", 0.5, 5.0),
    "FORGE_BREAKOUT_SL_ATR_MULT":      ("bb_breakout", "sl_atr_mult",      "float", 0.5, 5.0),
    "FORGE_BREAKOUT_BUY_SL_ATR_MULT":  ("bb_breakout", "buy_sl_atr_mult",  "float", 0.0, 6.0),
    # 2.7.23 — BE-trail cushion (Run 17 G5002 ATR=7.59 fix). 0 = legacy tight BE+. >0 = SL∓mult×ATR.
    "FORGE_BREAKOUT_BE_CUSHION_ATR_MULT": ("bb_breakout", "be_cushion_atr_mult", "float", 0.0, 3.0),
    # 2.7.24 — TP2 SL ratchet to TP1 (Milestone 2 per FORGE_RATCHET_LOGIC_IDEAS.md).
    "FORGE_BREAKOUT_TP2_SL_RATCHET_ENABLED": ("bb_breakout", "tp2_sl_ratchet_enabled", "bool01", None, None),
    # 2.7.25 — ATR trail (FORGE_RATCHET_LOGIC_IDEAS.md spec). Continuous SL trail at peak∓mult×ATR after TP1.
    "FORGE_BREAKOUT_ATR_TRAIL_ENABLED": ("bb_breakout", "atr_trail_enabled", "bool01", None, None),
    "FORGE_BREAKOUT_ATR_TRAIL_MULT": ("bb_breakout", "atr_trail_mult", "float", 0.3, 5.0),
    # 2.7.27 — Extended TP4/TP5 staging (Run 17 G5040 captured only 12pts of 53pt dump after TP3).
    "FORGE_BREAKOUT_TP4_STAGING_ENABLED": ("bb_breakout", "tp4_staging_enabled", "bool01", None, None),
    "FORGE_BREAKOUT_TP4_MIN_ADX":         ("bb_breakout", "tp4_min_adx",         "int",    0,    100),
    "FORGE_BREAKOUT_TP5_STAGING_ENABLED": ("bb_breakout", "tp5_staging_enabled", "bool01", None, None),
    "FORGE_BREAKOUT_TP5_MIN_ADX":         ("bb_breakout", "tp5_min_adx",         "int",    0,    100),
    "FORGE_BREAKOUT_TP5_ATR_MULT":        ("bb_breakout", "tp5_atr_mult",        "float",  3.0,  10.0),
    # 2.7.27 — Daily Direction Gate (Filters 1+2+3) — Run 17 G5048 -$1,666 fix.
    "FORGE_DAILY_DIRECTION_GATE_ENABLED":  ("safety", "daily_direction_gate_enabled",  "bool01", None, None),
    "FORGE_DAILY_SMA_PERIOD":               ("safety", "daily_sma_period",              "int",    2,    200),
    "FORGE_DAILY_SMA_LOOKBACK_DAYS":        ("safety", "daily_sma_lookback_days",       "int",    1,    30),
    "FORGE_DAILY_SLOPE_BLOCK_ATR":          ("safety", "daily_slope_block_atr",         "float",  0.0,  5.0),
    "FORGE_DAILY_MOVE_BLOCK_ATR":           ("safety", "daily_move_block_atr",          "float",  0.0,  5.0),
    "FORGE_DAILY_MOVE_FLIP_HYSTERESIS":     ("safety", "daily_move_flip_hysteresis",    "float",  0.0,  5.0),
    "FORGE_DAILY_CANCEL_PENDING_ON_FLIP":   ("safety", "daily_cancel_pending_on_flip",  "bool01", None, None),
    "FORGE_DAILY_CANCEL_INCLUDES_CASCADE":  ("safety", "daily_cancel_includes_cascade", "bool01", None, None),
    # 2.7.28 — Momentum dump-catch market entry (Run 17 trend-capture gap fix).
    "FORGE_DUMP_CATCH_ENABLED":      ("safety", "dump_catch_enabled",      "bool01", None, None),
    "FORGE_DUMP_LOOKBACK_BARS":      ("safety", "dump_lookback_bars",      "int",    1,    20),
    "FORGE_DUMP_ATR_MULT":           ("safety", "dump_atr_mult",           "float",  0.3,  5.0),
    "FORGE_DUMP_MAX_RSI":            ("safety", "dump_max_rsi",            "float",  0,    100),
    "FORGE_DUMP_MAX_RSI_BUY":        ("safety", "dump_max_rsi_buy",        "float",  0,    100),
    "FORGE_DUMP_MIN_ADX":            ("safety", "dump_min_adx",            "float",  0,    100),
    "FORGE_DUMP_REQUIRE_PSAR":       ("safety", "dump_require_psar",       "bool01", None, None),
    "FORGE_DUMP_REQUIRE_D1_BIAS":    ("safety", "dump_require_d1_bias",    "bool01", None, None),
    "FORGE_DUMP_COOLDOWN_SECONDS":   ("safety", "dump_cooldown_seconds",   "int",    0,    7200),
    "FORGE_DUMP_LOT_FACTOR":         ("safety", "dump_lot_factor",         "float",  0.01, 2.0),
    "FORGE_DUMP_BUY_LOT_FACTOR":     ("safety", "dump_buy_lot_factor",     "float",  0.0,  2.0),
    "FORGE_DUMP_SELL_LOT_FACTOR":    ("safety", "dump_sell_lot_factor",    "float",  0.0,  2.0),
    "FORGE_DUMP_SELL_H1_MAX":        ("safety", "dump_sell_h1_max",        "float",  0.0,  10.0),
    # 2.7.32 — Option B (default OFF) direction-confirmation gate
    "FORGE_DUMP_REQUIRE_BAR_CONFIRM": ("safety", "dump_require_bar_confirm", "bool01", None, None),
    # 2.7.31 — BB_PULLBACK_SCALP additive setup (Run 19 Issue 4 / Task #53)
    "FORGE_PULLBACK_SCALP_ENABLED":            ("safety", "pullback_scalp_enabled",            "bool01", None, None),
    "FORGE_PULLBACK_SCALP_FRESH_FLIP_BARS":    ("safety", "pullback_scalp_fresh_flip_bars",    "int",    1,    20),
    "FORGE_PULLBACK_SCALP_LOT_FACTOR":         ("safety", "pullback_scalp_lot_factor",         "float",  0.01, 2.0),
    "FORGE_PULLBACK_SCALP_SL_ATR_MULT":        ("safety", "pullback_scalp_sl_atr_mult",        "float",  0.2,  5.0),
    "FORGE_PULLBACK_SCALP_TP1_ATR_MULT":       ("safety", "pullback_scalp_tp1_atr_mult",       "float",  0.1,  3.0),
    "FORGE_PULLBACK_SCALP_TP2_ATR_MULT":       ("safety", "pullback_scalp_tp2_atr_mult",       "float",  0.2,  5.0),
    "FORGE_PULLBACK_SCALP_COOLDOWN_SECONDS":   ("safety", "pullback_scalp_cooldown_seconds",   "int",    0,    7200),
    "FORGE_PULLBACK_SCALP_MAX_ADX":            ("safety", "pullback_scalp_max_adx",            "float",  0,    100),
    # 2.7.29 — Regime H1-strong override (Run 18 Issue 1 fix). 0 = disabled, 2.0 typical when enabled.
    "FORGE_REGIME_H1_OVERRIDE_FACTOR":  ("safety", "regime_h1_override_factor",  "float", 0.0, 10.0),
    "FORGE_REGIME_H1_OVERRIDE_ADX_MIN": ("safety", "regime_h1_override_adx_min", "float", 0.0, 100.0),
    "FORGE_BREAKOUT_TP1_ATR_MULT":      ("bb_breakout", "tp1_atr_mult",      "float", 0.1, 5.0),
    "FORGE_BREAKOUT_TP1_BUY_ATR_MULT":  ("bb_breakout", "tp1_buy_atr_mult",  "float", 0.1, 5.0),
    "FORGE_BREAKOUT_TP1_SELL_ATR_MULT": ("bb_breakout", "tp1_sell_atr_mult", "float", 0.1, 5.0),
    "FORGE_BREAKOUT_TP1_CLOSE_PCT":    ("bb_breakout", "tp1_close_pct",    "int",   10.0, 100.0),
    "FORGE_BREAKOUT_TP2_ATR_MULT":          ("bb_breakout", "tp2_atr_mult",              "float", 0.1, 10.0),
    "FORGE_BREAKOUT_TP3_ATR_MULT":          ("bb_breakout", "tp3_atr_mult",              "float", 0.1, 20.0),
    # 2.7.27 codex-review fix: tp4_atr_mult was an orphan key — present in defaults.json
    # but no sync mapping. Adding so FORGE_BREAKOUT_TP4_ATR_MULT can override the 4.0×ATR default.
    "FORGE_BREAKOUT_TP4_ATR_MULT":          ("bb_breakout", "tp4_atr_mult",              "float", 0.1, 20.0),
    # ADX lot reduction factors — set to 1.0 to disable (strong trend = full lot per leg)
    "FORGE_BREAKOUT_ADX_LOT_MID_THRESHOLD":  ("safety",     "breakout_adx_lot_mid_threshold",  "float", 10.0, 100.0),
    "FORGE_BREAKOUT_ADX_LOT_HIGH_THRESHOLD": ("safety",     "breakout_adx_lot_high_threshold", "float", 10.0, 100.0),
    "FORGE_BREAKOUT_ADX_LOT_FACTOR_MID":     ("safety",     "breakout_adx_lot_factor_mid",     "float", 0.0,  1.0),
    "FORGE_BREAKOUT_ADX_LOT_FACTOR_HIGH":    ("safety",     "breakout_adx_lot_factor_high",    "float", 0.0,  1.0),
    "FORGE_BREAKOUT_ADX_LOT_USE_M15":        ("safety",     "breakout_adx_lot_use_m15",        "bool01", None, None),
    "FORGE_PSAR_ENABLED": ("indicators", "psar_enabled", "bool01", None, None),
    "FORGE_PSAR_STEP": ("indicators", "psar_step", "float", 0.001, 0.5),
    "FORGE_PSAR_MAXIMUM": ("indicators", "psar_maximum", "float", 0.01, 5.0),
    "FORGE_TESTER_SESSION_FILTER": ("session_filter", "tester_session_filter", "bool01", None, None),
    "FORGE_TESTER_ALLOWED_SESSIONS": ("session_filter", "tester_allowed_sessions", "string", None, None),
    # 2.7.36 — Session minute-precision + NY anchor + broker offsets + killzones
    "FORGE_SESSIONS_NY_ANCHORED":     ("session_filter", "sessions_ny_anchored",      "bool01", None,  None),
    "FORGE_BROKER_GMT_OFFSET_WINTER": ("session_filter", "broker_gmt_offset_winter",  "int",   -12.0, 14.0),
    "FORGE_BROKER_GMT_OFFSET_SUMMER": ("session_filter", "broker_gmt_offset_summer",  "int",   -12.0, 14.0),
    "FORGE_LONDON_START_MIN":         ("session_filter", "london_start_min",          "int",    None, 1439.0),
    "FORGE_LONDON_END_MIN":           ("session_filter", "london_end_min",            "int",    None, 1440.0),
    "FORGE_NY_START_MIN":             ("session_filter", "ny_start_min",              "int",    None, 1439.0),
    "FORGE_NY_END_MIN":               ("session_filter", "ny_end_min",                "int",    None, 1440.0),
    "FORGE_ASIA_START_MIN":           ("session_filter", "asia_start_min",            "int",    None, 1439.0),
    "FORGE_ASIA_END_MIN":             ("session_filter", "asia_end_min",              "int",    None, 1440.0),
    "FORGE_KILLZONES_ENABLED":        ("session_filter", "killzones_enabled",         "bool01", None,  None),
    "FORGE_KILLZONES_GATE_ENTRIES":   ("session_filter", "killzones_gate_entries",    "bool01", None,  None),
    "FORGE_KZ_ASIA_START_MIN":        ("session_filter", "kz_asia_start_min",         "int",    0.0,  1439.0),
    "FORGE_KZ_ASIA_END_MIN":          ("session_filter", "kz_asia_end_min",           "int",    0.0,  1440.0),
    "FORGE_KZ_LONDON_OPEN_START_MIN": ("session_filter", "kz_london_open_start_min",  "int",    0.0,  1439.0),
    "FORGE_KZ_LONDON_OPEN_END_MIN":   ("session_filter", "kz_london_open_end_min",    "int",    0.0,  1440.0),
    "FORGE_KZ_NY_OPEN_START_MIN":     ("session_filter", "kz_ny_open_start_min",      "int",    0.0,  1439.0),
    "FORGE_KZ_NY_OPEN_END_MIN":       ("session_filter", "kz_ny_open_end_min",        "int",    0.0,  1440.0),
    "FORGE_KZ_LONDON_CLOSE_START_MIN":("session_filter", "kz_london_close_start_min", "int",    0.0,  1439.0),
    "FORGE_KZ_LONDON_CLOSE_END_MIN":  ("session_filter", "kz_london_close_end_min",   "int",    0.0,  1440.0),
    # 2.7.38 Tier 1 Boolean Composites (all default-OFF; see docs/FORGE_INDICATOR_ATLAS.md §5)
    "FORGE_BLOCK_SELL_IN_CHOP_ENABLED":       ("composites", "block_sell_in_chop_enabled",       "bool01", None, None),
    "FORGE_INTRADAY_REVERSAL_SELL_ENABLED":   ("composites", "intraday_reversal_sell_enabled",   "bool01", None, None),
    "FORGE_INTRADAY_REVERSAL_SELL_LOT_MULT":  ("composites", "intraday_reversal_sell_lot_mult",  "float",  0.5,   5.0),
    "FORGE_FRACTIONAL_SELL_IN_BULL_ENABLED":  ("composites", "fractional_sell_in_bull_enabled",  "bool01", None, None),
    "FORGE_FRACTIONAL_SELL_IN_BULL_LOT_FACTOR": ("composites", "fractional_sell_in_bull_lot_factor", "float", 0.05, 1.0),
    "FORGE_FRACTIONAL_SELL_IN_BULL_SL_ATR_MULT": ("composites", "fractional_sell_in_bull_sl_atr_mult", "float", 0.5,  5.0),
    "FORGE_FRACTIONAL_SELL_IN_BULL_TP1_ATR_MULT": ("composites", "fractional_sell_in_bull_tp1_atr_mult", "float", 0.1, 2.0),
    "FORGE_BULL_DAY_DIP_BUY_ENABLED":         ("composites", "bull_day_dip_buy_enabled",         "bool01", None, None),
    "FORGE_BULL_DAY_DIP_BUY_LOT_MULT":        ("composites", "bull_day_dip_buy_lot_mult",        "float",  0.1,  10.0),
    "FORGE_BULL_DAY_DIP_BUY_SL_ATR_MULT":     ("composites", "bull_day_dip_buy_sl_atr_mult",     "float",  0.3,   5.0),
    "FORGE_BULL_DAY_DIP_BUY_TP1_ATR_MULT":    ("composites", "bull_day_dip_buy_tp1_atr_mult",    "float",  0.1,   3.0),
    "FORGE_BULL_DAY_DIP_BUY_REENTRY_COOLDOWN_SEC": ("composites", "bull_day_dip_buy_reentry_cooldown_sec", "int", 0.0, 3600.0),
    "FORGE_TESTER_COOLDOWN_ENABLED": ("safety", "tester_cooldown_enabled", "bool01", None, None),
    "FORGE_DIRECTION_COOLDOWN_ENABLED": ("safety", "direction_cooldown_enabled", "bool01", None, None),
    "FORGE_DIRECTION_COOLDOWN_BARS": ("safety", "direction_cooldown_bars", "int", 0.0, 50.0),
    "FORGE_JOURNAL_ENABLED": ("journal", "journal_enabled", "bool01", None, None),
    "FORGE_JOURNAL_RECORD_SKIPS": ("journal", "journal_record_skips", "bool01", None, None),
    "FORGE_JOURNAL_IMPORT_TRADES": ("journal", "journal_import_trades", "bool01", None, None),
    "FORGE_JOURNAL_IMPORT_DEPTH_DAYS": ("journal", "journal_import_depth_days", "int", 1.0, 365.0),
    "FORGE_JOURNAL_STATS_INTERVAL_SEC": ("journal", "journal_stats_interval_sec", "int", 60.0, 3600.0),

    # ══════════════════════════════════════════════════════════════════════
    # Phase 1 — new setups (MA_CROSSOVER, VWAP_REVERSION, FIB_CONFLUENCE)
    # ══════════════════════════════════════════════════════════════════════
    # Config skeleton only — EA dispatch ships in Phase 2. All default-OFF.
    # Env prefixes follow FORGE_NAMING_CONVENTIONS.md §4 (SETUP / ATOM /
    # GEOMETRY / TIMING). JSON sections mirror scope per §10.5.1c.

    # ── MA Crossover (EMA20 × EMA50 event-triggered entry) ──
    "FORGE_SETUP_MA_CROSSOVER_ENABLED":              ("setup",    "ma_crossover_enabled",              "bool01", None, None),
    "FORGE_ATOM_MA_CROSSOVER_ADX_MIN":               ("atom",     "ma_crossover_adx_min",              "float",  5.0, 80.0),
    "FORGE_GEOMETRY_MA_CROSSOVER_LOT_FACTOR":        ("geometry", "ma_crossover_lot_factor",           "float",  0.1, 2.0),
    "FORGE_GEOMETRY_MA_CROSSOVER_SL_ATR_MULT":       ("geometry", "ma_crossover_sl_atr_mult",          "float",  0.5, 5.0),
    "FORGE_GEOMETRY_MA_CROSSOVER_TP1_ATR_MULT":      ("geometry", "ma_crossover_tp1_atr_mult",         "float",  0.1, 5.0),
    "FORGE_GEOMETRY_MA_CROSSOVER_TP2_ATR_MULT":      ("geometry", "ma_crossover_tp2_atr_mult",         "float",  0.1, 10.0),
    "FORGE_TIMING_MA_CROSSOVER_COOLDOWN_SECONDS":    ("timing",   "ma_crossover_cooldown_seconds",     "int",    0.0, 7200.0),

    # ── VWAP Reversion (pullback-to-VWAP in trend direction) ──
    "FORGE_SETUP_VWAP_REVERSION_ENABLED":             ("setup",    "vwap_reversion_enabled",             "bool01", None, None),
    "FORGE_ATOM_VWAP_REVERSION_MIN_DEVIATION_ATR":    ("atom",     "vwap_reversion_min_deviation_atr",   "float",  0.1, 10.0),
    "FORGE_ATOM_VWAP_REVERSION_MAX_DEVIATION_ATR":    ("atom",     "vwap_reversion_max_deviation_atr",   "float",  0.5, 20.0),
    "FORGE_ATOM_VWAP_REVERSION_MIN_EXTENSION_BARS":   ("atom",     "vwap_reversion_min_extension_bars",  "int",    1.0, 50.0),
    "FORGE_GEOMETRY_VWAP_REVERSION_LOT_FACTOR":       ("geometry", "vwap_reversion_lot_factor",          "float",  0.1, 2.0),
    "FORGE_GEOMETRY_VWAP_REVERSION_SL_ATR_MULT":      ("geometry", "vwap_reversion_sl_atr_mult",         "float",  0.5, 5.0),
    "FORGE_GEOMETRY_VWAP_REVERSION_TP1_ATR_MULT":     ("geometry", "vwap_reversion_tp1_atr_mult",        "float",  0.1, 5.0),
    "FORGE_GEOMETRY_VWAP_REVERSION_TP2_ATR_MULT":     ("geometry", "vwap_reversion_tp2_atr_mult",        "float",  0.1, 10.0),
    "FORGE_TIMING_VWAP_REVERSION_COOLDOWN_SECONDS":   ("timing",   "vwap_reversion_cooldown_seconds",    "int",    0.0, 7200.0),

    # ── Fib Confluence (retrace to fib level + reference overlap) ──
    "FORGE_SETUP_FIB_CONFLUENCE_ENABLED":             ("setup",    "fib_confluence_enabled",             "bool01", None, None),
    "FORGE_ATOM_FIB_CONFLUENCE_MIN_CONFLUENCES":      ("atom",     "fib_confluence_min_confluences",     "int",    1.0, 5.0),
    "FORGE_ATOM_FIB_CONFLUENCE_TOLERANCE_ATR":        ("atom",     "fib_confluence_tolerance_atr",       "float",  0.05, 2.0),
    "FORGE_ATOM_FIB_CONFLUENCE_MIN_SWING_ATR":        ("atom",     "fib_confluence_min_swing_atr",       "float",  0.5, 20.0),
    "FORGE_GEOMETRY_FIB_CONFLUENCE_LOT_FACTOR":       ("geometry", "fib_confluence_lot_factor",          "float",  0.1, 2.0),
    "FORGE_GEOMETRY_FIB_CONFLUENCE_SL_ATR_MULT":      ("geometry", "fib_confluence_sl_atr_mult",         "float",  0.5, 5.0),
    "FORGE_GEOMETRY_FIB_CONFLUENCE_TP1_ATR_MULT":     ("geometry", "fib_confluence_tp1_atr_mult",        "float",  0.1, 5.0),
    "FORGE_GEOMETRY_FIB_CONFLUENCE_TP2_ATR_MULT":     ("geometry", "fib_confluence_tp2_atr_mult",        "float",  0.1, 10.0),
    "FORGE_TIMING_FIB_CONFLUENCE_COOLDOWN_SECONDS":   ("timing",   "fib_confluence_cooldown_seconds",    "int",    0.0, 7200.0),

    # ── Inside Bar Breakout (Tier 1 — trivial 2-bar pattern, no new state) ──
    "FORGE_SETUP_INSIDE_BAR_ENABLED":                 ("setup",    "inside_bar_enabled",                 "bool01", None, None),
    "FORGE_ATOM_INSIDE_BAR_MIN_OUTER_ATR":            ("atom",     "inside_bar_min_outer_atr",           "float",  0.1, 10.0),
    "FORGE_ATOM_INSIDE_BAR_ADX_MIN":                  ("atom",     "inside_bar_adx_min",                 "float",  5.0, 80.0),
    "FORGE_GEOMETRY_INSIDE_BAR_LOT_FACTOR":           ("geometry", "inside_bar_lot_factor",              "float",  0.1, 2.0),
    "FORGE_GEOMETRY_INSIDE_BAR_SL_ATR_MULT":          ("geometry", "inside_bar_sl_atr_mult",             "float",  0.5, 5.0),
    "FORGE_GEOMETRY_INSIDE_BAR_TP1_ATR_MULT":         ("geometry", "inside_bar_tp1_atr_mult",            "float",  0.1, 5.0),
    "FORGE_GEOMETRY_INSIDE_BAR_TP2_ATR_MULT":         ("geometry", "inside_bar_tp2_atr_mult",            "float",  0.1, 10.0),
    "FORGE_TIMING_INSIDE_BAR_COOLDOWN_SECONDS":       ("timing",   "inside_bar_cooldown_seconds",        "int",    0.0, 7200.0),

    # ── BB Squeeze (Tier 1 — volatility contraction → directional expansion) ──
    "FORGE_SETUP_BB_SQUEEZE_ENABLED":                 ("setup",    "bb_squeeze_enabled",                 "bool01", None, None),
    "FORGE_ATOM_BB_SQUEEZE_LOOKBACK_BARS":            ("atom",     "bb_squeeze_lookback_bars",           "int",    10.0, 200.0),
    "FORGE_ATOM_BB_SQUEEZE_PCTILE_THRESHOLD":         ("atom",     "bb_squeeze_pctile_threshold",        "float",  1.0, 50.0),
    "FORGE_ATOM_BB_SQUEEZE_MIN_BREAKOUT_ATR":         ("atom",     "bb_squeeze_min_breakout_atr",        "float",  0.05, 2.0),
    "FORGE_ATOM_BB_SQUEEZE_ADX_MIN":                  ("atom",     "bb_squeeze_adx_min",                 "float",  5.0, 80.0),
    "FORGE_GEOMETRY_BB_SQUEEZE_LOT_FACTOR":           ("geometry", "bb_squeeze_lot_factor",              "float",  0.1, 2.0),
    "FORGE_GEOMETRY_BB_SQUEEZE_SL_ATR_MULT":          ("geometry", "bb_squeeze_sl_atr_mult",             "float",  0.5, 5.0),
    "FORGE_GEOMETRY_BB_SQUEEZE_TP1_ATR_MULT":         ("geometry", "bb_squeeze_tp1_atr_mult",            "float",  0.1, 5.0),
    "FORGE_GEOMETRY_BB_SQUEEZE_TP2_ATR_MULT":         ("geometry", "bb_squeeze_tp2_atr_mult",            "float",  0.1, 10.0),
    "FORGE_TIMING_BB_SQUEEZE_COOLDOWN_SECONDS":       ("timing",   "bb_squeeze_cooldown_seconds",        "int",    0.0, 7200.0),

    # ── ORB — Opening Range Breakout (Tier 2 — single configurable window) ──
    # window_start/end_min are NY-local minutes of day. Defaults = 120/150 = London Open
    # (02:00-02:30 NY = 07:00-07:30 GMT winter). Operator can switch to NY Open (570/585
    # = 09:30-09:45 NY) or Asia (e.g. 1140/1170 = 19:00-19:30 NY) per backtest.
    "FORGE_SETUP_ORB_ENABLED":                        ("setup",    "orb_enabled",                        "bool01", None, None),
    "FORGE_ATOM_ORB_WINDOW_START_MIN":                ("atom",     "orb_window_start_min",               "int",    0.0, 1440.0),
    "FORGE_ATOM_ORB_WINDOW_END_MIN":                  ("atom",     "orb_window_end_min",                 "int",    0.0, 1440.0),
    "FORGE_ATOM_ORB_MIN_RANGE_ATR":                   ("atom",     "orb_min_range_atr",                  "float",  0.1, 10.0),
    "FORGE_ATOM_ORB_MIN_BREAKOUT_ATR":                ("atom",     "orb_min_breakout_atr",               "float",  0.05, 2.0),
    "FORGE_ATOM_ORB_ADX_MIN":                         ("atom",     "orb_adx_min",                        "float",  5.0, 80.0),
    "FORGE_GEOMETRY_ORB_LOT_FACTOR":                  ("geometry", "orb_lot_factor",                     "float",  0.1, 2.0),
    "FORGE_GEOMETRY_ORB_SL_ATR_MULT":                 ("geometry", "orb_sl_atr_mult",                    "float",  0.5, 5.0),
    "FORGE_GEOMETRY_ORB_TP1_ATR_MULT":                ("geometry", "orb_tp1_atr_mult",                   "float",  0.1, 5.0),
    "FORGE_GEOMETRY_ORB_TP2_ATR_MULT":                ("geometry", "orb_tp2_atr_mult",                   "float",  0.1, 10.0),
    "FORGE_TIMING_ORB_COOLDOWN_SECONDS":              ("timing",   "orb_cooldown_seconds",               "int",    0.0, 7200.0),

    # ── Gap-and-Go (Tier 2 — bar-time-skip + price-jump detection) ──
    # Stateless: a gap is a bar whose start time skips ≥ min_time_skip_seconds from the
    # previous bar's close AND whose open price differs from prior close by ≥ min_gap_atr × ATR.
    # On forex/XAUUSD, this fires at the Sunday/Monday week open after a news-impacting weekend.
    "FORGE_SETUP_GAP_AND_GO_ENABLED":                 ("setup",    "gap_and_go_enabled",                 "bool01", None, None),
    "FORGE_ATOM_GAP_AND_GO_MIN_TIME_SKIP_SECONDS":    ("atom",     "gap_and_go_min_time_skip_seconds",   "int",    300.0, 172800.0),
    "FORGE_ATOM_GAP_AND_GO_MIN_GAP_ATR":              ("atom",     "gap_and_go_min_gap_atr",             "float",  0.1, 10.0),
    "FORGE_ATOM_GAP_AND_GO_MAX_GAP_ATR":              ("atom",     "gap_and_go_max_gap_atr",             "float",  0.5, 20.0),
    "FORGE_GEOMETRY_GAP_AND_GO_LOT_FACTOR":           ("geometry", "gap_and_go_lot_factor",              "float",  0.1, 2.0),
    "FORGE_GEOMETRY_GAP_AND_GO_SL_ATR_MULT":          ("geometry", "gap_and_go_sl_atr_mult",             "float",  0.5, 5.0),
    "FORGE_GEOMETRY_GAP_AND_GO_TP1_ATR_MULT":         ("geometry", "gap_and_go_tp1_atr_mult",            "float",  0.1, 5.0),
    "FORGE_GEOMETRY_GAP_AND_GO_TP2_ATR_MULT":         ("geometry", "gap_and_go_tp2_atr_mult",            "float",  0.1, 10.0),
    "FORGE_TIMING_GAP_AND_GO_COOLDOWN_SECONDS":       ("timing",   "gap_and_go_cooldown_seconds",        "int",    0.0, 86400.0),
}

# Screaming-SNAKE env key -> alternate names (camelCase) accepted from .env; first non-empty wins in order listed.
ENV_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "FORGE_NUM_TRADES": ("FORGE_NUM_TRADES", "forgeNumTrades"),
    "FORGE_MIN_NUM_TRADES": ("FORGE_MIN_NUM_TRADES", "forgeMinNumTrades"),
    "FORGE_MAX_NUM_TRADES": ("FORGE_MAX_NUM_TRADES", "forgeMaxNumTrades"),
}


def _env_raw(env: dict[str, str], env_key: str) -> str:
    for k in ENV_KEY_ALIASES.get(env_key, (env_key,)):
        v = env.get(k, "").strip()
        if v:
            return v
    return ""


def _env_key_used(env: dict[str, str], env_key: str) -> str:
    """Which alias was actually set (for log messages)."""
    for k in ENV_KEY_ALIASES.get(env_key, (env_key,)):
        v = env.get(k, "").strip()
        if v:
            return k
    return env_key


def _load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        out[key] = value
    return out


def _parse_value(raw: str, kind: str) -> int | float | str:
    if kind == "int":
        return int(float(raw))
    if kind == "float":
        return float(raw)
    if kind == "bool01":
        low = raw.strip().lower()
        if low in {"1", "true", "yes", "on"}:
            return 1
        if low in {"0", "false", "no", "off"}:
            return 0
        raise ValueError("expected one of 0/1/true/false/yes/no/on/off")
    if kind == "string":
        return raw.strip()
    if kind == "lot_source":
        src = raw.strip().upper()
        if src in {"AUTO", "INPUTS", "CONFIG"}:
            return src
        raise ValueError("expected one of AUTO/INPUTS/CONFIG")
    if kind == "bounce_htf_bias":
        u = raw.strip().upper()
        if u in {"LEGACY", "BALANCED", "STRICT"}:
            return u
        raise ValueError("expected one of LEGACY/BALANCED/STRICT")
    raise ValueError(f"unsupported type: {kind}")


def _clamp(value: int | float, min_v: float | None, max_v: float | None) -> int | float:
    if min_v is not None and value < min_v:
        value = min_v
    if max_v is not None and value > max_v:
        value = max_v
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tmp:
        json.dump(payload, tmp, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _lot_sizing_drop_num_trades(cfg: dict[str, Any]) -> bool:
    """Remove deprecated single key so min/max are the only leg-count source."""
    lot = cfg.get("lot_sizing")
    if isinstance(lot, dict) and "num_trades" in lot:
        del lot["num_trades"]
        return True
    return False


def apply_scalper_env_overrides(
    env: dict[str, str],
    config: dict[str, Any],
    *,
    emit: Callable[[str], None] | None = None,
) -> int:
    """
    Merge FORGE_* / forge* keys from a parsed env dict into ``config`` (mutates in place).
    Returns a monotonic **updated** counter (same semantics as CLI: number of logical sync operations).
    """
    _emit = emit or (lambda _m: None)
    updated = 0

    leg_raw = _env_raw(env, "FORGE_NUM_TRADES")
    has_min_env = bool(_env_raw(env, "FORGE_MIN_NUM_TRADES"))
    has_max_env = bool(_env_raw(env, "FORGE_MAX_NUM_TRADES"))
    if leg_raw and not has_min_env and not has_max_env:
        v = int(_clamp(_parse_value(leg_raw, "int"), 1.0, 20.0))
        lot = config.setdefault("lot_sizing", {})
        if not isinstance(lot, dict):
            raise TypeError("Section 'lot_sizing' must be an object")
        changed = False
        if lot.get("min_num_trades") != v:
            lot["min_num_trades"] = v
            changed = True
        if lot.get("max_num_trades") != v:
            lot["max_num_trades"] = v
            changed = True
        if _lot_sizing_drop_num_trades(config):
            changed = True
        if changed:
            updated += 1
            src = _env_key_used(env, "FORGE_NUM_TRADES")
            _emit(
                f"[sync] {src} (legacy) -> lot_sizing.min_num_trades="
                f"lot_sizing.max_num_trades={v} (dropped num_trades if present)"
            )

    for env_key, (section, key, kind, min_v, max_v) in MAPPING.items():
        raw = _env_raw(env, env_key)
        if raw == "":
            continue
        parsed = _parse_value(raw, kind)
        parsed = _clamp(parsed, min_v, max_v)
        section_obj = config.setdefault(section, {})
        if not isinstance(section_obj, dict):
            raise TypeError(f"Section '{section}' must be an object")
        row_changed = False
        if section_obj.get(key) != parsed:
            section_obj[key] = parsed
            row_changed = True
            src = _env_key_used(env, env_key)
            _emit(f"[sync] {src} -> {section}.{key} = {parsed}")
        if section == "lot_sizing" and key in ("min_num_trades", "max_num_trades"):
            if _lot_sizing_drop_num_trades(config):
                row_changed = True
                _emit("[sync] removed deprecated lot_sizing.num_trades")
        if row_changed:
            updated += 1

    return updated


MT5_SCALPER_CONFIG = ROOT / "MT5" / "scalper_config.json"


def _sync_to_mt5(source: Path) -> None:
    """Copy scalper_config.json to MT5/ (Common Files symlink) so FORGE picks it up without recompile."""
    dst = MT5_SCALPER_CONFIG
    if not dst.parent.exists():
        return
    import shutil
    shutil.copy2(str(source), str(dst))
    print(f"[sync] copied {source.name} → {dst.parent.name}/{dst.name}")


def _stamp_version(config: dict[str, Any]) -> bool:
    """Stamp version from VERSION file into config; returns True if changed."""
    if not VERSION_PATH.exists():
        return False
    ver = VERSION_PATH.read_text(encoding="utf-8").strip()
    if not ver:
        return False
    if config.get("version") != ver:
        config["version"] = ver
        return True
    return False


def main() -> int:
    env = _load_env(ENV_PATH)
    if not SCALPER_DEFAULTS_PATH.exists():
        raise FileNotFoundError(
            f"Missing defaults template: {SCALPER_DEFAULTS_PATH}\n"
            "Edit config/scalper_config.defaults.json (or FORGE_* in .env); "
            "do not create scalper_config.json by hand."
        )

    config = json.loads(SCALPER_DEFAULTS_PATH.read_text(encoding="utf-8"))
    version_changed = _stamp_version(config)
    if version_changed:
        print(f"[sync] stamped version={config['version']} from VERSION file")

    updated = apply_scalper_env_overrides(env, config, emit=print)

    if updated == 0 and not version_changed:
        print("[sync] no overrides found in .env")
    if updated > 0 or version_changed:
        _atomic_write_json(SCALPER_CONFIG_PATH, config)
        print(f"[sync] wrote {SCALPER_CONFIG_PATH} ({updated} env override(s){', version stamped' if version_changed else ''})")

    _sync_to_mt5(SCALPER_CONFIG_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
