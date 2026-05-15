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
    "FORGE_GATE_M5_ADX_HYSTERESIS_ENABLE": ("safety", "adx_hysteresis_enabled", "bool01", None, None),
    "FORGE_GATE_M5_ADX_HYSTERESIS_APPLY_IN_TESTER": ("safety", "adx_hysteresis_apply_in_tester", "bool01", None, None),
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
    "FORGE_ATOM_M5_ADX_TREND_ENTER": ("safety", "adx_trend_enter", "float", 0.0, 100.0),
    "FORGE_ATOM_M5_ADX_TREND_EXIT": ("safety", "adx_trend_exit", "float", 0.0, 100.0),
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
    # 2.7.53 — Operator's "no mercy in forex" cooldown bypass. When direction is aligned
    # with HTF (h1_trend) OR MTF (m15 trend) per `_m15_or_h1`, bypass cooldown without
    # any TP1 requirement. Catches both Apr 1 H1-led rally AND Apr 8 PM M15-led cascade.
    "FORGE_GATE_COOLDOWN_BYPASS_WITH_TREND_ENABLED":   ("safety", "cooldown_bypass_with_trend_enabled",   "bool01", None, None),
    "FORGE_GATE_COOLDOWN_BYPASS_WITH_TREND_H1_MIN":    ("safety", "cooldown_bypass_with_trend_h1_min",    "float",  0.0,  10.0),
    "FORGE_GATE_COOLDOWN_BYPASS_WITH_TREND_M15_OR_H1": ("safety", "cooldown_bypass_with_trend_m15_or_h1", "bool01", None, None),
    # 2.7.53 — Universal fast-trend lot amplifier. When direction matches HTF/MTF trend
    # AND M5 ADX clears the "fast" floor, multiply combined_lot_factor by `_factor`.
    "FORGE_GEOMETRY_FAST_TREND_LOT_AMPLIFIER_ENABLED": ("safety", "fast_trend_lot_amplifier_enabled", "bool01", None, None),
    "FORGE_GEOMETRY_FAST_TREND_LOT_AMPLIFIER_FACTOR":  ("safety", "fast_trend_lot_amplifier_factor",  "float",  0.5,  10.0),
    "FORGE_GATE_FAST_TREND_LOT_AMPLIFIER_ADX_MIN":     ("safety", "fast_trend_lot_amplifier_adx_min", "float",  0.0,  80.0),
    # 2.7.53 — MOMENTUM_DUMP_COMPOSITE_TEST: parallel composite using the new
    # boolean-composite framework, replicating legacy MOMENTUM_DUMP atoms. Default OFF.
    # Enable for a tester run alongside legacy MOMENTUM_DUMP; compare TAKEN counts to
    # validate that the composite pattern produces identical behavior.
    # v2.7.69 — these 13 keys were duplicated in both safety+composites sections of the
    # generated scalper_config.json; EA's JsonGetDouble returns the FIRST match (safety),
    # so composites overrides were silently ignored. Section flipped composites→safety
    # so .env overrides land where the EA actually reads them.
    # 2.7.121 — Renamed to MOMENTUM_DUMP_COMPOSITE (drop _TEST suffix). Lot factor default 0.7→1.0.
    "FORGE_SETUP_MOMENTUM_DUMP_COMPOSITE_ENABLED":           ("safety",     "momentum_dump_composite_enabled",           "bool01", None, None),
    "FORGE_SETUP_MOMENTUM_DUMP_COMPOSITE_LOOKBACK_BARS":     ("composites", "momentum_dump_composite_lookback_bars",     "int",    1.0,   20.0),
    "FORGE_GATE_MOMENTUM_DUMP_COMPOSITE_ATR_MULT":           ("composites", "momentum_dump_composite_atr_mult",          "float",  0.1,   10.0),
    "FORGE_GATE_MOMENTUM_DUMP_COMPOSITE_MAX_RSI":            ("composites", "momentum_dump_composite_max_rsi",           "float",  0.0,   100.0),
    "FORGE_GATE_MOMENTUM_DUMP_COMPOSITE_MAX_RSI_BUY":        ("composites", "momentum_dump_composite_max_rsi_buy",       "float",  0.0,   100.0),
    "FORGE_GATE_MOMENTUM_DUMP_COMPOSITE_MIN_ADX":            ("composites", "momentum_dump_composite_min_adx",           "float",  0.0,   80.0),
    "FORGE_GEOMETRY_MOMENTUM_DUMP_COMPOSITE_SL_ATR_MULT":    ("composites", "momentum_dump_composite_sl_atr_mult",       "float",  0.3,   10.0),
    "FORGE_GEOMETRY_MOMENTUM_DUMP_COMPOSITE_TP1_ATR_MULT":   ("composites", "momentum_dump_composite_tp1_atr_mult",      "float",  0.1,   5.0),
    "FORGE_GEOMETRY_MOMENTUM_DUMP_COMPOSITE_TP2_ATR_MULT":   ("composites", "momentum_dump_composite_tp2_atr_mult",      "float",  0.1,   5.0),
    "FORGE_TIMING_MOMENTUM_DUMP_COMPOSITE_COOLDOWN_SECONDS": ("safety",     "momentum_dump_composite_cooldown_seconds",  "int",    0.0,   7200.0),
    "FORGE_GATE_MOMENTUM_DUMP_COMPOSITE_CHOP_BLOCK":         ("composites", "momentum_dump_composite_chop_block",        "bool01", None,  None),
    "FORGE_GATE_MOMENTUM_DUMP_COMPOSITE_REQUIRE_PSAR":       ("composites", "momentum_dump_composite_require_psar",      "bool01", None,  None),
    "FORGE_GATE_MOMENTUM_DUMP_COMPOSITE_REQUIRE_D1_BIAS":    ("composites", "momentum_dump_composite_require_d1_bias",   "bool01", None,  None),
    "FORGE_GATE_MOMENTUM_DUMP_COMPOSITE_SELL_H1_MAX":        ("composites", "momentum_dump_composite_sell_h1_max",       "float",  0.0,   10.0),
    "FORGE_GEOMETRY_MOMENTUM_DUMP_COMPOSITE_LOT_FACTOR":     ("composites", "momentum_dump_composite_lot_factor",        "float",  0.1,   2.0),
    # 2.7.55 — BB_LOWER_REVERSION_BUY: aggressive mean-reversion BUY at gold's BB-lower oversold zone.
    # Pairs with dump_below_bbl_block_sell — turn the same SELL-blocking condition into a BUY entry.
    # Default ON (multi-indicator high-conviction setup per operator).
    "FORGE_SETUP_BB_LOWER_REVERSION_BUY_ENABLED":                ("composites", "bb_lower_reversion_buy_enabled",                "bool01", None,  None),
    "FORGE_GATE_BB_LOWER_REVERSION_BUY_MAX_RSI":                 ("composites", "bb_lower_reversion_buy_max_rsi",                "float",  0,     100),
    "FORGE_GATE_BB_LOWER_REVERSION_BUY_MIN_ADX":                 ("composites", "bb_lower_reversion_buy_min_adx",                "float",  0,     80),
    "FORGE_GEOMETRY_BB_LOWER_REVERSION_BUY_SL_ATR_MULT":         ("safety",     "bb_lower_reversion_buy_sl_atr_mult",            "float",  0.1,   5.0),
    "FORGE_GEOMETRY_BB_LOWER_REVERSION_BUY_TP1_OFFSET_ATR_MULT": ("composites", "bb_lower_reversion_buy_tp1_offset_atr_mult",    "float",  0,     5.0),
    "FORGE_GEOMETRY_BB_LOWER_REVERSION_BUY_TP2_OFFSET_ATR_MULT": ("composites", "bb_lower_reversion_buy_tp2_offset_atr_mult",    "float",  0,     5.0),
    "FORGE_TIMING_BB_LOWER_REVERSION_BUY_COOLDOWN_SECONDS":      ("safety",     "bb_lower_reversion_buy_cooldown_seconds",       "int",    0,     7200),
    "FORGE_GEOMETRY_BB_LOWER_REVERSION_BUY_LOT_FACTOR":          ("composites", "bb_lower_reversion_buy_lot_factor",             "float",  0.1,   10.0),
    "FORGE_GATE_BB_LOWER_REVERSION_BUY_H1_MAX":                  ("composites", "bb_lower_reversion_buy_h1_max",                 "float",  0,     10.0),
    "FORGE_GATE_BB_LOWER_REVERSION_BUY_EXTREME_RSI":             ("composites", "bb_lower_reversion_buy_extreme_rsi",            "float",  0,     100),
    "FORGE_GEOMETRY_BB_LOWER_REVERSION_BUY_EXTREME_AMPLIFIER":   ("composites", "bb_lower_reversion_buy_extreme_amplifier",      "float",  1.0,   10.0),
    "FORGE_TIMING_BB_LOWER_REVERSION_BUY_MAX_HOLD_SECONDS":      ("safety",     "bb_lower_reversion_buy_max_hold_seconds",      "int",    0,     7200),
    # v2.7.59 — BLR_BUY falling-knife protection (Apr 2 G5021-G5024 fix)
    "FORGE_GATE_BB_LOWER_REVERSION_BUY_REQUIRE_REVERSAL_CANDLE": ("composites", "bb_lower_reversion_buy_require_reversal_candle","bool01", None,  None),
    "FORGE_GATE_BB_LOWER_REVERSION_BUY_CONSEC_LOSS_MAX":         ("composites", "bb_lower_reversion_buy_consec_loss_max",         "int",    0,     10),
    "FORGE_TIMING_BB_LOWER_REVERSION_BUY_CONSEC_LOSS_WINDOW_SEC":("composites", "bb_lower_reversion_buy_consec_loss_window_sec",  "int",    0,     7200),
    "FORGE_TIMING_BB_LOWER_REVERSION_BUY_CONSEC_LOSS_COOLDOWN_SEC":("composites","bb_lower_reversion_buy_consec_loss_cooldown_sec","int",   0,     7200),
    "FORGE_GATE_BB_LOWER_REVERSION_BUY_H4_MIN":                  ("composites", "bb_lower_reversion_buy_h4_min",                  "float",  -10.0, 10.0),
    # v2.7.69 — ICT market-structure gates (wires v2.7.68 BOS + v2.7.65 velocity into BLR_BUY + BB_BREAKOUT BUY)
    "FORGE_GATE_BLR_BUY_BLOCK_ON_BEARISH_BOS":                   ("safety",     "blr_buy_block_on_bearish_bos",                 "bool01", None,  None),
    "FORGE_GATE_BLR_BUY_MIN_VELOCITY_5BAR_SIGNED":               ("safety",     "blr_buy_min_velocity_5bar_signed",             "float",  -10.0, 10.0),
    # v2.7.80 — BLR capitulation override (Apr 6 03:30 + Apr 14 13:39 V-bottom fix: bypass falling-velocity gate on real flush)
    "FORGE_GATE_BLR_BUY_CAPITULATION_OVERRIDE_ENABLED":          ("safety",     "blr_buy_capitulation_override_enabled",        "bool01", None,  None),
    "FORGE_GATE_BLR_BUY_CAPITULATION_MIN_ATOMS":                 ("safety",     "blr_buy_capitulation_min_atoms",               "int",    1,     5),
    "FORGE_GATE_BLR_BUY_CAPITULATION_RSI_MAX":                   ("safety",     "blr_buy_capitulation_rsi_max",                 "float",  10.0,  40.0),
    "FORGE_GATE_BLR_BUY_CAPITULATION_DISPLACEMENT_MIN_ATR":      ("safety",     "blr_buy_capitulation_displacement_min_atr",    "float",  0.5,   5.0),
    "FORGE_GATE_BLR_BUY_CAPITULATION_ATR_RATIO_MIN":             ("safety",     "blr_buy_capitulation_atr_ratio_min",           "float",  1.0,   3.0),
    "FORGE_GEOMETRY_BLR_BUY_CAPITULATION_LOT":                   ("composites", "blr_buy_capitulation_lot",                     "float",  0.01,  2.0),
    "FORGE_GEOMETRY_BLR_BUY_CAPITULATION_SL_ATR_MULT":           ("composites", "blr_buy_capitulation_sl_atr_mult",             "float",  0.5,   5.0),
    "FORGE_GEOMETRY_BLR_BUY_CAPITULATION_TP1_ATR_MULT":          ("composites", "blr_buy_capitulation_tp1_atr_mult",            "float",  0.1,   3.0),
    "FORGE_GEOMETRY_BLR_BUY_CAPITULATION_TP2_ATR_MULT":          ("composites", "blr_buy_capitulation_tp2_atr_mult",            "float",  0.1,   5.0),
    "FORGE_GATE_BREAKOUT_BUY_EXHAUSTION_RSI":                    ("safety",     "breakout_buy_exhaustion_rsi",                  "float",  0.0,   100.0),
    "FORGE_GATE_BREAKOUT_BUY_BLOCK_EXHAUSTION_WITHOUT_BOS":      ("safety",     "breakout_buy_block_exhaustion_without_bos",    "bool01", None,  None),
    # v2.7.73 — VWAP-distance gates (Run 30 G5005 −$1,694 diagnosis: vwap_dist/atr=2.76 = mean-reversion zone)
    "FORGE_GATE_BREAKOUT_BUY_MAX_VWAP_DIST_ATR":                 ("safety",     "breakout_buy_max_vwap_dist_atr",               "float",  0.0,   20.0),
    "FORGE_GATE_BREAKOUT_SELL_MAX_VWAP_DIST_ATR":                ("safety",     "breakout_sell_max_vwap_dist_atr",              "float",  0.0,   20.0),
    # v2.7.93 — Anti-retest gate: BB_BREAKOUT BUY/SELL must clear band by ≥ this×ATR at entry
    "FORGE_GATE_BB_BREAKOUT_MIN_BREAKOUT_ATR_MULT":              ("safety",     "bb_breakout_min_breakout_atr_mult",            "float",  0.0,   5.0),
    "FORGE_GATE_BB_BREAKOUT_MIN_BREAKDOWN_ATR_MULT":             ("safety",     "bb_breakout_min_breakdown_atr_mult",           "float",  0.0,   5.0),
    # v2.7.74 — BB_BREAKOUT BUY conviction amplifier (fire more legs + lower TP1 close pct when 4+ confirming atoms align)
    "FORGE_SETUP_BREAKOUT_BUY_CONVICTION_ENABLED":               ("safety",     "breakout_buy_conviction_enabled",              "bool01", None,  None),
    "FORGE_GATE_BREAKOUT_BUY_CONVICTION_MIN_ATOMS":              ("safety",     "breakout_buy_conviction_min_atoms",            "int",    0,     10),
    "FORGE_GEOMETRY_BREAKOUT_BUY_CONVICTION_INITIAL_LEGS":       ("safety",     "breakout_buy_conviction_initial_legs",         "int",    1,     30),
    "FORGE_GEOMETRY_BREAKOUT_BUY_CONVICTION_TP1_CLOSE_PCT":      ("safety",     "breakout_buy_conviction_tp1_close_pct",        "float",  0,     100),
    # v2.7.76 — Score velocity gate (Run 31 G5005 −$2,934 fix: avg5 76→63 falling, amp deployed 5 legs)
    "FORGE_GATE_BREAKOUT_BUY_SCORE_VELOCITY_CHECK_ENABLED":      ("safety",     "breakout_buy_score_velocity_check_enabled",    "bool01", None,  None),
    "FORGE_GATE_BREAKOUT_BUY_SCORE_VELOCITY_THRESHOLD":          ("safety",     "breakout_buy_score_velocity_threshold",        "int",    -100,  100),
    # v2.7.77 — Conviction-decay partial close (Nyao Scalper reverse-pyramid pattern)
    "FORGE_SETUP_CONVICTION_DECAY_PARTIAL_CLOSE_ENABLED":        ("safety",     "conviction_decay_partial_close_enabled",       "bool01", None,  None),
    "FORGE_GATE_CONVICTION_DECAY_L1_RATIO":                      ("safety",     "conviction_decay_l1_ratio",                    "float",  0.0,   1.0),
    "FORGE_GATE_CONVICTION_DECAY_L2_RATIO":                      ("safety",     "conviction_decay_l2_ratio",                    "float",  0.0,   1.0),
    "FORGE_GATE_CONVICTION_DECAY_L3_RATIO":                      ("safety",     "conviction_decay_l3_ratio",                    "float",  0.0,   1.0),
    "FORGE_GEOMETRY_CONVICTION_DECAY_L1_CLOSE_PCT":              ("safety",     "conviction_decay_l1_close_pct",                "float",  0.0,   100.0),
    "FORGE_GEOMETRY_CONVICTION_DECAY_L2_CLOSE_PCT":              ("safety",     "conviction_decay_l2_close_pct",                "float",  0.0,   100.0),
    "FORGE_TIMING_CONVICTION_DECAY_GRACE_BARS":                  ("safety",     "conviction_decay_grace_bars",                  "int",    0,     30),
    # v2.7.78 — REVERSE_SELL_IN_BULL (G5005 direction-flip pattern, full 0.5 lot counter-trend SELL)
    "FORGE_SETUP_REVERSE_SELL_IN_BULL_ENABLED":                  ("composites","reverse_sell_in_bull_enabled",                  "bool01", None,  None),
    "FORGE_GEOMETRY_REVERSE_SELL_IN_BULL_LOT_FACTOR":            ("composites","reverse_sell_in_bull_lot_factor",               "float",  0.0,   2.0),
    "FORGE_GATE_REVERSE_SELL_IN_BULL_MIN_RSI":                   ("composites","reverse_sell_in_bull_min_rsi",                  "float",  0.0,   100.0),
    "FORGE_GATE_REVERSE_SELL_IN_BULL_MIN_VWAP_DIST_ATR":         ("composites","reverse_sell_in_bull_min_vwap_dist_atr",        "float",  0.0,   20.0),
    "FORGE_GATE_REVERSE_SELL_IN_BULL_MIN_H1_TREND":              ("composites","reverse_sell_in_bull_min_h1_trend",             "float",  -10.0, 10.0),
    "FORGE_GATE_REVERSE_SELL_IN_BULL_REQUIRE_DI_PLUS_ABOVE_MINUS": ("composites","reverse_sell_in_bull_require_di_plus_above_minus","bool01", None, None),
    "FORGE_GEOMETRY_REVERSE_SELL_IN_BULL_SL_ATR_MULT":           ("composites","reverse_sell_in_bull_sl_atr_mult",              "float",  0.1,   10.0),
    "FORGE_GEOMETRY_REVERSE_SELL_IN_BULL_TP1_ATR_MULT":          ("composites","reverse_sell_in_bull_tp1_atr_mult",             "float",  0.1,   10.0),
    "FORGE_GEOMETRY_REVERSE_SELL_IN_BULL_TP2_ATR_MULT":          ("composites","reverse_sell_in_bull_tp2_atr_mult",             "float",  0.1,   10.0),
    "FORGE_TIMING_REVERSE_SELL_IN_BULL_COOLDOWN_SEC":            ("composites","reverse_sell_in_bull_cooldown_sec",             "int",    0,     7200),
    # v2.7.79 — GRINDING_SELL (Apr 8 between-killzone descent fix)
    "FORGE_SETUP_GRINDING_SELL_ENABLED":                         ("composites","grinding_sell_enabled",                         "bool01", None,  None),
    "FORGE_GEOMETRY_GRINDING_SELL_LOT_FACTOR":                   ("composites","grinding_sell_lot_factor",                      "float",  0.0,   2.0),
    "FORGE_GATE_GRINDING_SELL_MIN_VELOCITY":                     ("composites","grinding_sell_min_velocity",                    "float",  0.0,   10.0),
    "FORGE_GATE_GRINDING_SELL_MAX_RSI":                          ("composites","grinding_sell_max_rsi",                         "float",  0.0,   100.0),
    "FORGE_GATE_GRINDING_SELL_MIN_RSI":                          ("composites","grinding_sell_min_rsi",                         "float",  0.0,   100.0),
    "FORGE_GATE_GRINDING_SELL_ROOM_MIN_ATR":                     ("composites","grinding_sell_room_min_atr",                    "float",  0.0,   10.0),
    "FORGE_GEOMETRY_GRINDING_SELL_SL_ATR_MULT":                  ("composites","grinding_sell_sl_atr_mult",                     "float",  0.1,   10.0),
    "FORGE_GEOMETRY_GRINDING_SELL_TP1_ATR_MULT":                 ("composites","grinding_sell_tp1_atr_mult",                    "float",  0.1,   10.0),
    "FORGE_GEOMETRY_GRINDING_SELL_TP2_ATR_MULT":                 ("composites","grinding_sell_tp2_atr_mult",                    "float",  0.1,   10.0),
    "FORGE_TIMING_GRINDING_SELL_COOLDOWN_SEC":                   ("composites","grinding_sell_cooldown_sec",                    "int",    0,     7200),
    # v2.7.81 — ASIA_CAPITULATION_BUY (Apr 6 03:30 @ 4603 RSI 23 pre-London V-flush; session-agnostic)
    "FORGE_SETUP_ASIA_CAPITULATION_BUY_ENABLED":                 ("composites","asia_capitulation_buy_enabled",                  "bool01", None,  None),
    "FORGE_GATE_ASIA_CAPITULATION_BUY_MIN_ATOMS":                ("composites","asia_capitulation_buy_min_atoms",                "int",    1,     5),
    "FORGE_GATE_ASIA_CAPITULATION_BUY_RSI_MAX":                  ("composites","asia_capitulation_buy_rsi_max",                  "float",  10.0,  40.0),
    "FORGE_GATE_ASIA_CAPITULATION_BUY_DISPLACEMENT_MIN_ATR":     ("composites","asia_capitulation_buy_displacement_min_atr",     "float",  0.5,   5.0),
    "FORGE_GATE_ASIA_CAPITULATION_BUY_ATR_RATIO_MIN":            ("composites","asia_capitulation_buy_atr_ratio_min",            "float",  1.0,   3.0),
    "FORGE_TIMING_ASIA_CAPITULATION_BUY_SESSION_START_UTC":      ("composites","asia_capitulation_buy_session_start_utc",        "int",    0,     23),
    "FORGE_TIMING_ASIA_CAPITULATION_BUY_SESSION_END_UTC":        ("composites","asia_capitulation_buy_session_end_utc",          "int",    0,     23),
    "FORGE_GEOMETRY_ASIA_CAPITULATION_BUY_LOT":                  ("composites","asia_capitulation_buy_lot",                      "float",  0.01,  2.0),
    "FORGE_GEOMETRY_ASIA_CAPITULATION_BUY_SL_ATR_MULT":          ("composites","asia_capitulation_buy_sl_atr_mult",              "float",  0.5,   5.0),
    "FORGE_GEOMETRY_ASIA_CAPITULATION_BUY_TP1_ATR_MULT":         ("composites","asia_capitulation_buy_tp1_atr_mult",             "float",  0.1,   3.0),
    "FORGE_GEOMETRY_ASIA_CAPITULATION_BUY_TP2_ATR_MULT":         ("composites","asia_capitulation_buy_tp2_atr_mult",             "float",  0.1,   5.0),
    "FORGE_TIMING_ASIA_CAPITULATION_BUY_COOLDOWN_SEC":           ("composites","asia_capitulation_buy_cooldown_sec",             "int",    0,     7200),
    # v2.7.84 — 3-layer entry-gating: UMCG + CVCSM + BB_EXHAUSTION_REVERSAL
    # See docs/FORGE_CASE_STUDY_G5006_INFLECTION_POINT.md for full design rationale.
    "FORGE_GATE_UMCG_ENABLED":                                   ("safety",    "umcg_enabled",                                  "bool01", None,  None),
    "FORGE_GATE_UMCG_BUY_BLOCK_THRESHOLD":                       ("safety",    "umcg_buy_block_threshold",                      "int",    1,     7),
    "FORGE_GATE_UMCG_SELL_BLOCK_THRESHOLD":                      ("safety",    "umcg_sell_block_threshold",                     "int",    1,     7),
    "FORGE_GATE_UMCG_PEMCG_RSI_OVERBOUGHT":                      ("safety",    "umcg_pemcg_rsi_overbought",                     "float",  50.0,  90.0),
    "FORGE_GATE_UMCG_PEMCG_RSI_OVERSOLD":                        ("safety",    "umcg_pemcg_rsi_oversold",                       "float",  10.0,  50.0),
    "FORGE_GATE_UMCG_PEMCG_BODY_PCT_MAX_WEAK":                   ("safety",    "umcg_pemcg_body_pct_max_weak",                  "float",  0.1,   1.0),
    "FORGE_GATE_UMCG_PEMCG_ATR_RATIO_MAX_CONTRACT":              ("safety",    "umcg_pemcg_atr_ratio_max_contract",             "float",  0.5,   2.0),
    "FORGE_GATE_UMCG_PEMCG_BB_DIST_ATR_THRESHOLD":               ("safety",    "umcg_pemcg_bb_dist_atr_threshold",              "float",  0.0,   2.0),
    # v2.7.105 — Day-Type Classifier (DTC) + PEMCG modifier + Day-Bias hard block.
    # Validated via Run 36 v2.7.102 monitoring data (11,669 mis-blocked SELLs in 5h bear window).
    # See docs/FORGE_PEMCG_ARCHITECTURE.md §3.4 and docs/FORGE_CORE_LOGIC_DESIGN.md §9 v2.7.105 entry.
    "FORGE_COMPOSITE_DTC_ENABLED":                               ("safety",    "dtc_enabled",                                   "bool01", None,  None),
    "FORGE_COMPOSITE_DTC_PEMCG_MODIFIER_ENABLED":                ("safety",    "dtc_pemcg_modifier_enabled",                    "bool01", None,  None),
    "FORGE_COMPOSITE_DTC_DAY_BIAS_BLOCK_ENABLED":                ("safety",    "dtc_day_bias_block_enabled",                    "bool01", None,  None),
    "FORGE_GATE_DTC_VWAP_DIST_ATR_THRESHOLD":                    ("safety",    "dtc_vwap_dist_atr_threshold",                   "float",  0.0,   10.0),
    "FORGE_GATE_DTC_M15_ADX_MIN":                                ("safety",    "dtc_m15_adx_min",                               "int",    0,     80),
    "FORGE_GATE_DTC_H1_DI_DOMINANCE_MIN":                        ("safety",    "dtc_h1_di_dominance_min",                       "float",  0.0,   50.0),
    "FORGE_GATE_DTC_PEMCG_BYPASS_ATOMS":                         ("safety",    "dtc_pemcg_bypass_atoms",                        "int",    0,     7),
    "FORGE_GATE_DTC_EXEMPT_BUY_SETUPS":                          ("safety",    "dtc_exempt_buy_setups",                         "string", None,  None),
    "FORGE_GATE_DTC_EXEMPT_SELL_SETUPS":                         ("safety",    "dtc_exempt_sell_setups",                        "string", None,  None),
    # v2.7.107 — DTC 5-state classifier (ICT-canonical). Adds H4 trend agreement axis.
    # See docs/FORGE_PEMCG_ARCHITECTURE.md §3.5 and Run 36 G5021/G5026 case studies.
    "FORGE_COMPOSITE_DTC_5STATE_ENABLED":                        ("safety",    "dtc_5state_enabled",                            "bool01", None,  None),
    "FORGE_GATE_DTC_H4_TREND_MIN_AGREEMENT":                     ("safety",    "dtc_h4_trend_min_agreement",                    "float",  0.0,   10.0),
    "FORGE_GATE_DTC_BLOCK_COUNTER_TREND_BUYS":                   ("safety",    "dtc_block_counter_trend_buys",                  "bool01", None,  None),
    "FORGE_GATE_DTC_BLOCK_COUNTER_TREND_SELLS":                  ("safety",    "dtc_block_counter_trend_sells",                 "bool01", None,  None),
    # v2.7.108 — DTC-aware SL/TP geometry widener for cascade orders on TREND_ALIGNED days.
    # Solves the Apr-08 G5024 case: 5 cascade legs SL'd by a 19pt pullback inside a 184pt rally.
    # Industry rule (mql5.com/blogs/769205): swing 1hr ≥ 2.5×ATR; chop ≤ 1.5×ATR.
    "FORGE_COMPOSITE_DTC_GEOMETRY_WIDEN_ENABLED":                ("safety",    "dtc_geometry_widen_enabled",                    "bool01", None,  None),
    "FORGE_GEOMETRY_DTC_TREND_ALIGNED_SL_WIDEN_FACTOR":          ("safety",    "dtc_trend_aligned_sl_widen_factor",             "float",  0.5,   5.0),
    "FORGE_GEOMETRY_DTC_TREND_ALIGNED_TP_WIDEN_FACTOR":          ("safety",    "dtc_trend_aligned_tp_widen_factor",             "float",  0.5,   5.0),
    # v2.7.109 — Exempt-list conditional override (momentum-vs-exhaustion RSI override on TREND_ALIGNED days).
    # Catches the G5028 -$2,488 case: BB_EXHAUSTION_REVERSAL_SELL at RSI 75-80 during a bull rally is fighting momentum, not catching exhaustion.
    "FORGE_COMPOSITE_DTC_EXEMPT_OVERRIDE_ENABLED":               ("safety",    "dtc_exempt_override_enabled",                   "bool01", None,  None),
    "FORGE_GATE_DTC_EXEMPT_OVERRIDE_SELL_RSI_MIN":               ("safety",    "dtc_exempt_override_sell_rsi_min",              "float",  50.0,  90.0),
    "FORGE_GATE_DTC_EXEMPT_OVERRIDE_BUY_RSI_MAX":                ("safety",    "dtc_exempt_override_buy_rsi_max",               "float",  10.0,  50.0),
    "FORGE_GATE_DTC_EXEMPT_OVERRIDE_BUY_SETUPS":                 ("safety",    "dtc_exempt_override_buy_setups",                "string", None,  None),
    "FORGE_GATE_DTC_EXEMPT_OVERRIDE_SELL_SETUPS":                ("safety",    "dtc_exempt_override_sell_setups",               "string", None,  None),
    # v2.7.112 — ISS (ICT Structure Score) — scaffolding only (atoms stubbed, default-OFF).
    # Replaces v2.7.110 CES. Score = MSS(5)+FVG(3)+ChoCH_support(2) on 0-10 scale.
    # See docs/ICT-Structure-Score.md for atom definitions + migration plan.
    "FORGE_COMPOSITE_ISS_ENABLED":                               ("safety",    "iss_enabled",                                   "bool01", None,  None),
    "FORGE_GATE_ISS_MIN_THRESHOLD":                              ("safety",    "iss_min_threshold",                             "int",    0,     10),
    "FORGE_GATE_ISS_BLOCK_BELOW_THRESHOLD":                      ("safety",    "iss_block_below_threshold",                     "bool01", None,  None),
    # v2.7.118+ Mode C reservation per docs/FORGE_PEMCG_ICT_INTEGRATION.md §3.3.
    # When 1: ISS-C HIGH_CONVICTION (≥8) overrides pemcg_*_reversal_block on the matching
    # direction. Underlying ISS-C composite (regime + h1 + m5_adx + m15_adx + vwap + psar
    # + bar-quality + prev-bar hard gate) ships in Phase 4 (v2.7.121+). EA struct field
    # not yet wired — knob exists at config layer only, EA reads default 0 until v2.7.121.
    "FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED":                   ("safety",    "iss_c_override_pemcg_enabled",                  "bool01", None,  None),
    "FORGE_GATE_ISS_WEIGHT_MSS":                                 ("safety",    "iss_weight_mss",                                "int",    0,     10),
    "FORGE_GATE_ISS_WEIGHT_FVG":                                 ("safety",    "iss_weight_fvg",                                "int",    0,     10),
    "FORGE_GATE_ISS_WEIGHT_CHOCH_SUPPORT":                       ("safety",    "iss_weight_choch_support",                      "int",    0,     10),
    "FORGE_TIMING_ISS_FVG_MAX_AGE_BARS":                         ("safety",    "iss_fvg_max_age_bars",                          "int",    1,     60),
    "FORGE_GATE_ISS_FVG_MAX_FILL_PCT":                           ("safety",    "iss_fvg_max_fill_pct",                          "float",  0.0,   1.0),
    # v2.7.118 — ICT Phase 1 modular component (first .mqh module ea/include/Forge/IctStructure.mqh).
    # MSS (Market Structure Shift) + FVG (Fair Value Gap) detection. Default-OFF instrumentation —
    # atoms compute + log to SIGNALS when enabled; SKIP gate fires only when iss_block_below_threshold=1.
    "FORGE_ICT_MSS_ENABLED":                                     ("safety",    "ict_mss_enabled",                               "bool01", None,  None),
    "FORGE_ICT_FVG_ENABLED":                                     ("safety",    "ict_fvg_enabled",                               "bool01", None,  None),
    "FORGE_ICT_SWING_LOOKBACK":                                  ("safety",    "ict_swing_lookback",                            "int",    1,     10),
    "FORGE_ICT_MSS_DISPLACEMENT_ATR_MULT":                       ("safety",    "ict_mss_displacement_atr_mult",                 "float",  0.0,   5.0),
    "FORGE_ICT_FVG_MIN_SIZE_ATR_MULT":                           ("safety",    "ict_fvg_min_size_atr_mult",                     "float",  0.0,   5.0),
    # v2.7.120 — ICT Phase 2 modular component (ea/include/Forge/IctLiquidity.mqh).
    # ChoCH (Change of Character) + liquidity sweep + kill-zone helpers. Default-OFF
    # instrumentation — atoms compute + log to SIGNALS when enabled; no new SKIP gate.
    # Wires real values into g_iss_choch_support / g_iss_choch_against (was stubbed 0).
    "FORGE_ICT_CHOCH_ENABLED":                                   ("safety",    "ict_choch_enabled",                             "bool01", None,  None),
    "FORGE_ICT_LIQUIDITY_SWEEP_ENABLED":                         ("safety",    "ict_liquidity_sweep_enabled",                   "bool01", None,  None),
    "FORGE_ICT_CHOCH_LOOKBACK_BARS":                             ("safety",    "ict_choch_lookback_bars",                       "int",    1,     20),
    "FORGE_ICT_LIQUIDITY_SWEEP_WINDOW_BARS":                     ("safety",    "ict_liquidity_sweep_window_bars",               "int",    1,     20),
    "FORGE_ICT_LIQUIDITY_EQUAL_TOLERANCE_ATR_MULT":              ("safety",    "ict_liquidity_equal_tolerance_atr_mult",        "float",  0.0,   5.0),
    "FORGE_ICT_LIQUIDITY_REJECTION_MIN_WICK_ATR_MULT":           ("safety",    "ict_liquidity_rejection_min_wick_atr_mult",     "float",  0.0,   5.0),
    "FORGE_GATE_CVCSM_ENABLED":                                  ("safety",    "cvcsm_enabled",                                 "bool01", None,  None),
    "FORGE_GATE_CVCSM_RELEASE_THRESHOLD":                        ("safety",    "cvcsm_release_threshold",                       "int",    1,     7),
    "FORGE_TIMING_CVCSM_REQUIRED_CLEAN_BARS":                    ("safety",    "cvcsm_required_clean_bars",                     "int",    1,     20),
    "FORGE_TIMING_CVCSM_MAX_COOLDOWN_SEC":                       ("safety",    "cvcsm_max_cooldown_sec",                        "int",    60,    14400),
    "FORGE_GATE_CVCSM_TRIGGER_ON_SL":                            ("safety",    "cvcsm_trigger_on_sl",                           "bool01", None,  None),
    "FORGE_GATE_CVCSM_TRIGGER_ON_REGIME_FLIP":                   ("safety",    "cvcsm_trigger_on_regime_flip",                  "bool01", None,  None),
    "FORGE_SETUP_BB_EXHAUSTION_REVERSAL_ENABLED":                ("composites","bb_exhaustion_reversal_enabled",                "bool01", None,  None),
    "FORGE_GATE_BB_EXHAUSTION_REVERSAL_MIN_WARNINGS":            ("composites","bb_exhaustion_reversal_min_warnings",            "int",    1,     7),
    "FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_LOT":                 ("composites","bb_exhaustion_reversal_lot",                    "float",  0.01,  2.0),
    "FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_SL_ATR_MULT":         ("composites","bb_exhaustion_reversal_sl_atr_mult",            "float",  0.1,   5.0),
    "FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_TP1_ATR_MULT":        ("composites","bb_exhaustion_reversal_tp1_atr_mult",           "float",  0.0,   5.0),
    "FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_TP2_ATR_MULT":        ("composites","bb_exhaustion_reversal_tp2_atr_mult",           "float",  0.0,   10.0),
    "FORGE_TIMING_BB_EXHAUSTION_REVERSAL_COOLDOWN_SEC":          ("composites","bb_exhaustion_reversal_cooldown_sec",           "int",    0,     14400),
    "FORGE_GATE_BB_EXHAUSTION_REVERSAL_PROXIMITY_ATR":           ("composites","bb_exhaustion_reversal_proximity_atr",          "float",  0.1,   5.0),
    # v2.7.89 — BB_EXHAUSTION_REVERSAL conviction-tier amplifier + legs
    "FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_LOT_AMPLIFIER":           ("composites","bb_exhaustion_reversal_lot_amplifier",            "float",  0.1,   10.0),
    "FORGE_GATE_BB_EXHAUSTION_REVERSAL_HIGH_CONVICTION_WARNINGS":    ("composites","bb_exhaustion_reversal_high_conviction_warnings", "int",    1,     7),
    "FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_HIGH_CONVICTION_LOT_FACTOR": ("composites","bb_exhaustion_reversal_high_conviction_lot_factor", "float",  0.5,   10.0),
    "FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_LEGS_HIGH_CONVICTION":    ("composites","bb_exhaustion_reversal_legs_high_conviction",    "int",    1,     10),
    # v2.7.92 — ADX gate (don't counter-trade strong trends)
    "FORGE_GATE_BB_EXHAUSTION_REVERSAL_MAX_ADX":                     ("composites","bb_exhaustion_reversal_max_adx",                 "float",  0.0,   100.0),
    # v2.7.94 — Wide-Range Bar gate (don't catch falling knife after capitulation spike)
    "FORGE_GATE_BB_EXHAUSTION_REVERSAL_MAX_PREV_BAR_RANGE_ATR_MULT": ("composites","bb_exhaustion_reversal_max_prev_bar_range_atr_mult", "float",  0.0,   20.0),
    # v2.7.79 — BB_PULLBACK_SCALP BUY velocity gate (Apr 8 12:50 knife-catch fix)
    "FORGE_GATE_BB_PULLBACK_BUY_BLOCK_ON_FALLING_VELOCITY":      ("safety",    "bb_pullback_buy_block_on_falling_velocity",     "bool01", None,  None),
    "FORGE_GATE_BB_PULLBACK_BUY_MIN_VELOCITY_5BAR_SIGNED":       ("safety",    "bb_pullback_buy_min_velocity_5bar_signed",      "float",  -10.0, 10.0),
    # v2.7.70 — Pyramid kill on adverse direction (caps G5032-class 8-leg growth)
    "FORGE_GATE_PYRAMID_KILL_ENABLED":                           ("safety",     "pyramid_kill_enabled",                         "bool01", None,  None),
    "FORGE_GATE_PYRAMID_KILL_MAX_LOSS_USD":                      ("safety",     "pyramid_kill_max_loss_usd",                    "float",  0.0,   10000.0),
    "FORGE_GATE_PYRAMID_KILL_VELOCITY_THRESHOLD":                ("safety",     "pyramid_kill_velocity_threshold",              "float",  0.0,   10.0),
    # v2.7.70 — NY_SESSION_BEARISH_BREAKOUT_SELL (captures 220pt+ session-open descents)
    "FORGE_SETUP_NY_SESSION_BEARISH_SELL_ENABLED":               ("safety",     "ny_session_bearish_sell_enabled",              "bool01", None,  None),
    "FORGE_TIMING_NY_SESSION_BEARISH_SELL_KZ_MAX_MIN":           ("safety",     "ny_session_bearish_sell_kz_max_min",           "int",    0,     300),
    "FORGE_GATE_NY_SESSION_BEARISH_SELL_MIN_VELOCITY":           ("safety",     "ny_session_bearish_sell_min_velocity",         "float",  0.0,   10.0),
    "FORGE_GATE_NY_SESSION_BEARISH_SELL_MAX_RSI":                ("safety",     "ny_session_bearish_sell_max_rsi",              "float",  0.0,   100.0),
    "FORGE_GATE_NY_SESSION_BEARISH_SELL_ROOM_MIN_ATR":           ("safety",     "ny_session_bearish_sell_room_min_atr",         "float",  0.0,   10.0),
    "FORGE_GEOMETRY_NY_SESSION_BEARISH_SELL_SL_ATR_MULT":        ("safety",     "ny_session_bearish_sell_sl_atr_mult",          "float",  0.1,   10.0),
    "FORGE_GEOMETRY_NY_SESSION_BEARISH_SELL_TP1_ATR_MULT":       ("safety",     "ny_session_bearish_sell_tp1_atr_mult",         "float",  0.1,   10.0),
    "FORGE_GEOMETRY_NY_SESSION_BEARISH_SELL_TP2_ATR_MULT":       ("safety",     "ny_session_bearish_sell_tp2_atr_mult",         "float",  0.1,   10.0),
    "FORGE_TIMING_NY_SESSION_BEARISH_SELL_COOLDOWN_SEC":         ("safety",     "ny_session_bearish_sell_cooldown_sec",         "int",    0,     7200),
    "FORGE_GEOMETRY_NY_SESSION_BEARISH_SELL_LOT_FACTOR":         ("safety",     "ny_session_bearish_sell_lot_factor",           "float",  0.1,   10.0),
    # 2.7.57 — TREND_CONTINUATION_BUY + SELL (atlas §5.2 canonical, finally shipping)
    "FORGE_SETUP_TREND_CONTINUATION_BUY_ENABLED":               ("composites", "trend_continuation_buy_enabled",              "bool01", None,  None),
    "FORGE_GATE_TREND_CONTINUATION_BUY_H1_MIN":                 ("safety",    "trend_continuation_buy_h1_min",               "float",  0,     10.0),  # v2.7.85 — flipped composites→safety (key-shadowing fix)
    "FORGE_GATE_TREND_CONTINUATION_BUY_RSI_MIN":                ("composites", "trend_continuation_buy_rsi_min",              "float",  0,     100),
    "FORGE_GATE_TREND_CONTINUATION_BUY_RSI_MAX":                ("composites", "trend_continuation_buy_rsi_max",              "float",  0,     100),
    "FORGE_GATE_TREND_CONTINUATION_BUY_ADX_MIN":                ("composites", "trend_continuation_buy_adx_min",              "float",  0,     80),
    "FORGE_GATE_TREND_CONTINUATION_BUY_M15_ADX_MIN":            ("composites", "trend_continuation_buy_m15_adx_min",          "float",  0,     80),
    "FORGE_GATE_TREND_CONTINUATION_BUY_BB_PROXIMITY_ATR":       ("composites", "trend_continuation_buy_bb_proximity_atr",     "float",  0,     5.0),
    "FORGE_GEOMETRY_TREND_CONTINUATION_BUY_SL_ATR_MULT":        ("safety",     "trend_continuation_buy_sl_atr_mult",          "float",  0.1,   5.0),
    "FORGE_GEOMETRY_TREND_CONTINUATION_BUY_TP1_ATR_MULT":       ("safety",     "trend_continuation_buy_tp1_atr_mult",         "float",  0.1,   5.0),
    "FORGE_GEOMETRY_TREND_CONTINUATION_BUY_TP2_ATR_MULT":       ("safety",     "trend_continuation_buy_tp2_atr_mult",         "float",  0.1,   5.0),
    "FORGE_TIMING_TREND_CONTINUATION_BUY_COOLDOWN_SECONDS":     ("safety",     "trend_continuation_buy_cooldown_seconds",     "int",    0,     7200),
    "FORGE_GEOMETRY_TREND_CONTINUATION_BUY_LOT_FACTOR":         ("composites", "trend_continuation_buy_lot_factor",           "float",  0.1,   10.0),
    # v2.7.58 — TC_BUY missing-atom gates
    "FORGE_GATE_TREND_CONTINUATION_BUY_REQUIRE_MACD_POSITIVE":  ("composites", "trend_continuation_buy_require_macd_positive", "bool01", None,  None),
    "FORGE_GATE_TREND_CONTINUATION_BUY_MACD_MIN":               ("composites", "trend_continuation_buy_macd_min",              "float",  -10.0, 10.0),
    "FORGE_GATE_TREND_CONTINUATION_BUY_REQUIRE_ABOVE_VWAP":     ("composites", "trend_continuation_buy_require_above_vwap",    "bool01", None,  None),
    "FORGE_GATE_TREND_CONTINUATION_BUY_MAX_POC_DISTANCE_ATR":   ("composites", "trend_continuation_buy_max_poc_distance_atr",  "float",  0,     10.0),
    "FORGE_GATE_TREND_CONTINUATION_BUY_BLOCK_BEARISH_DIV":      ("composites", "trend_continuation_buy_block_bearish_div",     "bool01", None,  None),
    "FORGE_GATE_TREND_CONTINUATION_BUY_REQUIRE_H4_ALIGNMENT":   ("composites", "trend_continuation_buy_require_h4_alignment",  "bool01", None,  None),
    "FORGE_GATE_TREND_CONTINUATION_BUY_H4_MIN":                 ("composites", "trend_continuation_buy_h4_min",                "float",  -10.0, 10.0),
    "FORGE_SETUP_TREND_CONTINUATION_SELL_ENABLED":              ("composites", "trend_continuation_sell_enabled",             "bool01", None,  None),
    "FORGE_GATE_TREND_CONTINUATION_SELL_H1_MAX":                ("safety",    "trend_continuation_sell_h1_max",              "float",  0,     10.0),  # v2.7.85 — flipped composites→safety (key-shadowing fix)
    "FORGE_GATE_TREND_CONTINUATION_SELL_RSI_MIN":               ("composites", "trend_continuation_sell_rsi_min",             "float",  0,     100),
    "FORGE_GATE_TREND_CONTINUATION_SELL_RSI_MAX":               ("composites", "trend_continuation_sell_rsi_max",             "float",  0,     100),
    "FORGE_GATE_TREND_CONTINUATION_SELL_ADX_MIN":               ("composites", "trend_continuation_sell_adx_min",             "float",  0,     80),
    "FORGE_GATE_TREND_CONTINUATION_SELL_M15_ADX_MIN":           ("composites", "trend_continuation_sell_m15_adx_min",         "float",  0,     80),
    "FORGE_GATE_TREND_CONTINUATION_SELL_BB_PROXIMITY_ATR":      ("composites", "trend_continuation_sell_bb_proximity_atr",    "float",  0,     5.0),
    "FORGE_GEOMETRY_TREND_CONTINUATION_SELL_SL_ATR_MULT":       ("safety",     "trend_continuation_sell_sl_atr_mult",         "float",  0.1,   5.0),
    "FORGE_GEOMETRY_TREND_CONTINUATION_SELL_TP1_ATR_MULT":      ("safety",     "trend_continuation_sell_tp1_atr_mult",        "float",  0.1,   5.0),
    "FORGE_GEOMETRY_TREND_CONTINUATION_SELL_TP2_ATR_MULT":      ("safety",     "trend_continuation_sell_tp2_atr_mult",        "float",  0.1,   5.0),
    "FORGE_TIMING_TREND_CONTINUATION_SELL_COOLDOWN_SECONDS":    ("safety",     "trend_continuation_sell_cooldown_seconds",    "int",    0,     7200),
    "FORGE_GEOMETRY_TREND_CONTINUATION_SELL_LOT_FACTOR":        ("composites", "trend_continuation_sell_lot_factor",          "float",  0.1,   10.0),
    # v2.7.58 — TC_SELL missing-atom gates (mirror)
    "FORGE_GATE_TREND_CONTINUATION_SELL_REQUIRE_MACD_NEGATIVE": ("composites", "trend_continuation_sell_require_macd_negative", "bool01", None,  None),
    "FORGE_GATE_TREND_CONTINUATION_SELL_MACD_MAX":              ("composites", "trend_continuation_sell_macd_max",              "float",  -10.0, 10.0),
    "FORGE_GATE_TREND_CONTINUATION_SELL_REQUIRE_BELOW_VWAP":    ("composites", "trend_continuation_sell_require_below_vwap",    "bool01", None,  None),
    "FORGE_GATE_TREND_CONTINUATION_SELL_MAX_POC_DISTANCE_ATR":  ("composites", "trend_continuation_sell_max_poc_distance_atr",  "float",  0,     10.0),
    "FORGE_GATE_TREND_CONTINUATION_SELL_BLOCK_BULLISH_DIV":     ("composites", "trend_continuation_sell_block_bullish_div",     "bool01", None,  None),
    "FORGE_GATE_TREND_CONTINUATION_SELL_REQUIRE_H4_ALIGNMENT":  ("composites", "trend_continuation_sell_require_h4_alignment",  "bool01", None,  None),
    "FORGE_GATE_TREND_CONTINUATION_SELL_H4_MAX":                ("composites", "trend_continuation_sell_h4_max",                "float",  -10.0, 10.0),
    # v2.7.67 — TC velocity/DI/day-extreme atoms
    "FORGE_GATE_TREND_CONTINUATION_REQUIRE_VELOCITY_CHECK":     ("composites", "trend_continuation_require_velocity_check",     "bool01", None, None),
    "FORGE_GATE_TREND_CONTINUATION_MIN_ADX_DELTA_5BAR":         ("composites", "trend_continuation_min_adx_delta_5bar",         "float", -50.0, 50.0),
    "FORGE_GATE_TREND_CONTINUATION_MIN_VELOCITY_5BAR":          ("composites", "trend_continuation_min_velocity_5bar",          "float", 0.0, 10.0),
    "FORGE_GATE_TREND_CONTINUATION_BUY_MIN_MACD_SLOPE_5BAR":    ("composites", "trend_continuation_buy_min_macd_slope_5bar",    "float", -10.0, 10.0),
    "FORGE_GATE_TREND_CONTINUATION_SELL_MAX_MACD_SLOPE_5BAR":   ("composites", "trend_continuation_sell_max_macd_slope_5bar",   "float", -10.0, 10.0),
    "FORGE_GATE_TREND_CONTINUATION_BUY_MIN_DI_BALANCE":         ("composites", "trend_continuation_buy_min_di_balance",         "float", -100.0, 100.0),
    "FORGE_GATE_TREND_CONTINUATION_SELL_MAX_DI_BALANCE":        ("composites", "trend_continuation_sell_max_di_balance",        "float", -100.0, 100.0),
    "FORGE_GATE_TREND_CONTINUATION_BUY_MAX_DIST_FROM_DAY_HIGH_ATR": ("safety",    "trend_continuation_buy_max_dist_from_day_high_atr", "float", 0.0, 10.0),  # v2.7.85 — flipped composites→safety (key-shadowing fix)
    "FORGE_GATE_TREND_CONTINUATION_SELL_MAX_DIST_FROM_DAY_LOW_ATR": ("safety",    "trend_continuation_sell_max_dist_from_day_low_atr", "float", 0.0, 10.0),  # v2.7.85 — flipped composites→safety (key-shadowing fix)
    "FORGE_MIN_NUM_TRADES": ("lot_sizing", "min_num_trades", "int", 1.0, 30.0),
    "FORGE_MAX_NUM_TRADES": ("lot_sizing", "max_num_trades", "int", 1.0, 30.0),
    "FORGE_GOLD_NATIVE_MAX_SELL_LEGS": ("lot_sizing", "gold_native_max_sell_legs", "int", 0.0, 30.0),
    "FORGE_NATIVE_LEGS_MAX_WHEN_UNCLEAR": ("lot_sizing", "native_legs_max_when_unclear", "int", 0.0, 30.0),
    "FORGE_GEOMETRY_LEGS_CLEAR_TREND_FACTOR": ("lot_sizing", "native_legs_clear_trend_factor", "float", 1.0, 3.0),
    "FORGE_GEOMETRY_STAGED_SCALE_IN_FORCE": ("lot_sizing", "native_force_staged_scale_in", "bool01", None, None),
    "FORGE_STAGED_INITIAL_LEGS":          ("lot_sizing", "staged_initial_legs",          "int",    1.0, 30.0),
    "FORGE_STAGED_ADD_INTERVAL_SEC":      ("lot_sizing", "staged_add_interval_sec",      "int",    5.0, 300.0),
    "FORGE_STAGED_ADD_MIN_FAVORABLE_POINTS": ("lot_sizing", "staged_add_min_favorable_points", "float", 0.0, 5000.0),
    "FORGE_GEOMETRY_WAVE_CONFIRM_LOT_MULT":      ("lot_sizing", "wave_confirmation_lot_mult",      "float", 1.0, 10.0),
    "FORGE_GEOMETRY_NATIVE_USE_LIMIT_ENTRY": ("lot_sizing", "native_scalper_use_limit_entry", "bool01", None, None),
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
    "FORGE_GATE_BREAKOUT_H1_MACD_REQUIRE_BUY":        ("bb_breakout", "require_h1_macd_buy",         "bool01", None, None),
    # BB_BREAKOUT same-direction cooldown in seconds (2.7.17 Run 15 G5002 fix); 0 = disabled
    "FORGE_TIMING_BREAKOUT_SAME_DIR_COOLDOWN_SEC":  ("bb_breakout", "same_dir_cooldown_seconds",   "int",    0.0,  3600.0),
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
    "FORGE_GATE_BREAKOUT_HID_BULL_DIV_BLOCK_SELL":        ("bb_breakout", "block_hid_bull_sell",         "bool01", None, None),
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
    "FORGE_ATOM_BREAKOUT_CRASH_BYPASS_M15_ADX_MIN_SELL": ("bb_breakout", "h1h4_crash_sell_min_m15_adx", "float", 0.0, 80.0),
    "FORGE_BREAKOUT_MIN_H1_BEAR_STRENGTH":     ("bb_breakout", "min_h1_bear_strength",    "float", 0.0, 5.0),
    # SELL STOP continuation (2.7.10 Day 2) — disabled by default; enable to capture second impulse after TP1
    "FORGE_SELL_STOP_CONT_ENABLED":      ("bb_breakout", "sell_stop_cont_enabled",      "bool01", None, None),
    "FORGE_SELL_STOP_CONT_ATR_MULT":     ("bb_breakout", "sell_stop_cont_atr_mult",     "float", 0.1, 3.0),
    "FORGE_GEOMETRY_SELL_STOP_CONT_SL_ATR_MULT":  ("bb_breakout", "sell_stop_cont_sl_atr_mult",  "float", 0.0, 10.0),
    "FORGE_SELL_STOP_CONT_LOT_FACTOR":   ("bb_breakout", "sell_stop_cont_lot_factor",   "float", 0.0, 2.0),
    "FORGE_GEOMETRY_SELL_STOP_CONT_LEGS":         ("bb_breakout", "sell_stop_cont_legs",         "int",   1.0, 7.0),
    "FORGE_SELL_STOP_CONT_EXPIRY_BARS":  ("bb_breakout", "sell_stop_cont_expiry_bars",  "int",   1.0, 50.0),
    "FORGE_SELL_STOP_CONT_TP_ATR_MULT": ("bb_breakout", "sell_stop_cont_tp_atr_mult",  "float", 0.0, 5.0),
    "FORGE_SELL_STOP_CONT_MIN_RSI":      ("bb_breakout", "sell_stop_cont_min_rsi",      "float", 0.0, 50.0),
    "FORGE_ATOM_SELL_STOP_CONT_M5_ADX_MIN":      ("bb_breakout", "sell_stop_cont_min_adx",      "float", 0.0, 80.0),
    "FORGE_GATE_SELL_STOP_CONT_H1_DI_REQUIRE": ("bb_breakout", "sell_stop_cont_require_h1_di", "bool01", None, None),
    # 2.7.21 — Cascade regime guard (Run 15 G5040 -$1119 cascade fix)
    "FORGE_SELL_STOP_CONT_REQUIRE_TREND_REGIME": ("bb_breakout", "sell_stop_cont_require_trend_regime", "bool01", None, None),
    # BUY LIMIT recovery (2.7.10 Day 3) — Cardwell Bull Support entry at crash low after SELL TP1
    # Captures May-1-style parabolic reversals: RSI bounces from 20 back through 35 = recovery confirmed
    "FORGE_BUY_LIMIT_RECOVERY_ENABLED":      ("bb_breakout", "buy_limit_recovery_enabled",      "bool01", None, None),
    "FORGE_BUY_LIMIT_RECOVERY_MIN_RSI":      ("bb_breakout", "buy_limit_recovery_min_rsi",      "float", 20.0, 70.0),
    "FORGE_BUY_LIMIT_RECOVERY_LOT_FACTOR":   ("bb_breakout", "buy_limit_recovery_lot_factor",   "float", 0.0, 1.0),
    "FORGE_BUY_LIMIT_RECOVERY_EXPIRY_BARS":  ("bb_breakout", "buy_limit_recovery_expiry_bars",  "int",   1.0, 20.0),
    "FORGE_BUY_LIMIT_RECOVERY_SL_ATR_MULT":  ("bb_breakout", "buy_limit_recovery_sl_atr_mult",  "float", 0.1, 5.0),
    # ─────────────────────────────────────────────────────────────────────────
    # v2.7.95 — BUY-side cascade mirror (BUY_STOP_CONT). Closes the long-standing
    # asymmetry where SELL setups had 7 post-TP1 cascade legs + 1 counter-trend
    # recovery, but BUY setups had nothing. Default-OFF — operator-mandated big-flaw fix.
    "FORGE_BUY_STOP_CONT_ENABLED":            ("bb_breakout", "buy_stop_cont_enabled",            "bool01", None, None),
    "FORGE_BUY_STOP_CONT_ATR_MULT":           ("bb_breakout", "buy_stop_cont_atr_mult",           "float", 0.1, 3.0),
    "FORGE_GEOMETRY_BUY_STOP_CONT_SL_ATR_MULT": ("bb_breakout", "buy_stop_cont_sl_atr_mult",      "float", 0.0, 10.0),
    "FORGE_BUY_STOP_CONT_LOT_FACTOR":          ("bb_breakout", "buy_stop_cont_lot_factor",        "float", 0.0, 2.0),
    "FORGE_GEOMETRY_BUY_STOP_CONT_LEGS":       ("bb_breakout", "buy_stop_cont_legs",              "int",   1.0, 7.0),
    "FORGE_BUY_STOP_CONT_EXPIRY_BARS":         ("bb_breakout", "buy_stop_cont_expiry_bars",       "int",   1.0, 50.0),
    "FORGE_BUY_STOP_CONT_TP_ATR_MULT":         ("bb_breakout", "buy_stop_cont_tp_atr_mult",       "float", 0.0, 5.0),
    "FORGE_BUY_STOP_CONT_MAX_RSI":             ("bb_breakout", "buy_stop_cont_max_rsi",           "float", 50.0, 100.0),
    "FORGE_ATOM_BUY_STOP_CONT_M5_ADX_MIN":     ("bb_breakout", "buy_stop_cont_min_adx",           "float", 0.0, 80.0),
    "FORGE_GATE_BUY_STOP_CONT_H1_DI_REQUIRE":  ("bb_breakout", "buy_stop_cont_require_h1_di",     "bool01", None, None),
    "FORGE_BUY_STOP_CONT_REQUIRE_TREND_REGIME": ("bb_breakout", "buy_stop_cont_require_trend_regime", "bool01", None, None),
    # v2.7.95 — SELL_LIMIT recovery (mirror of buy_limit_recovery). Captures
    # Cardwell Bear Resistance pullback after BUY TP1 (sells the established rally high).
    "FORGE_SELL_LIMIT_RECOVERY_ENABLED":      ("bb_breakout", "sell_limit_recovery_enabled",      "bool01", None, None),
    "FORGE_SELL_LIMIT_RECOVERY_MAX_RSI":      ("bb_breakout", "sell_limit_recovery_max_rsi",      "float", 30.0, 90.0),
    "FORGE_SELL_LIMIT_RECOVERY_LOT_FACTOR":   ("bb_breakout", "sell_limit_recovery_lot_factor",   "float", 0.0, 1.0),
    "FORGE_SELL_LIMIT_RECOVERY_EXPIRY_BARS":  ("bb_breakout", "sell_limit_recovery_expiry_bars",  "int",   1.0, 20.0),
    "FORGE_SELL_LIMIT_RECOVERY_SL_ATR_MULT":  ("bb_breakout", "sell_limit_recovery_sl_atr_mult",  "float", 0.1, 5.0),
    # v2.7.117 — cascade-recovery safety TP. Default 2.0× ATR. Applied to BUY_LIMIT_RECOV,
    # SELL_LIMIT_RECOVERY, and (fallback) BUY_STOP_CONT / SELL_STOP_CONT when their own
    # tp_atr_mult <= 0. Live-broker requirement: never leave cascade fills open without
    # a broker-side TP (root cause of ticket 1303664415 — SELL_LIMIT fill held open with
    # no TP until manual close).
    "FORGE_GEOMETRY_CASCADE_RECOVERY_TP_ATR_MULT": ("bb_breakout", "cascade_recovery_tp_atr_mult", "float", 0.1, 10.0),
    # ─────────────────────────────────────────────────────────────────────────
    # H4 supplemental gates (2.7.10) — disabled by default in .defaults.json; enable per run for testing
    # H4 RSI gate: block SELL when H4 RSI >= h4_rsi_sell_max (Cardwell Bear Resistance exhaustion on H4)
    #              block BUY  when H4 RSI <= h4_rsi_buy_min  (Cardwell Bull Support exhaustion on H4)
    "FORGE_GATE_HTF_H4_RSI_ENABLE": ("bb_breakout", "h4_rsi_gate_enabled", "bool01", None, None),
    "FORGE_ATOM_HTF_H4_RSI_MAX_SELL":     ("bb_breakout", "h4_rsi_sell_max",     "float", 30.0, 80.0),
    "FORGE_ATOM_HTF_H4_RSI_MIN_BUY":      ("bb_breakout", "h4_rsi_buy_min",      "float", 20.0, 70.0),
    # H4 ADX gate: block entries when H4 ADX < min threshold (H4 trend not directional — ranging H4)
    "FORGE_GATE_HTF_H4_ADX_ENABLE": ("bb_breakout", "h4_adx_gate_enabled", "bool01", None, None),
    "FORGE_ATOM_HTF_H4_ADX_MIN_SELL":     ("bb_breakout", "h4_adx_min_sell",     "float", 0.0, 80.0),
    "FORGE_ATOM_HTF_H4_ADX_MIN_BUY":      ("bb_breakout", "h4_adx_min_buy",      "float", 0.0, 80.0),
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
    # v2.7.96 Set 2 — TP2 banking close (operator-spec'd 25% of remaining at TP2 touch).
    # Master flag default-OFF preserves ratchet-only behavior.
    # Decision in docs/FORGE_CORE_LOGIC_DESIGN.md §9 changelog 2026-05-14.
    "FORGE_GEOMETRY_TP2_CLOSE_ENABLED": ("bb_breakout", "tp2_close_enabled", "bool01", None, None),
    "FORGE_GEOMETRY_BREAKOUT_TP2_CLOSE_PCT": ("bb_breakout", "tp2_close_pct", "float", 0.0, 100.0),
    # v2.7.97 Sets 6+7+8 — Direction Lock state machine + break-condition evaluator + no-auto-flip cooldown.
    # All gated by direction_lock_enabled master flag (default 0 = current behavior preserved).
    # Decision: docs/FORGE_CORE_LOGIC_DESIGN.md §4 Sets 6/7/8.
    "FORGE_SETUP_DIRECTION_LOCK_ENABLED": ("bb_breakout", "direction_lock_enabled", "bool01", None, None),
    "FORGE_GATE_DIRLOCK_STRUCT_BREAK_ATR_MULT": ("bb_breakout", "dirlock_struct_break_atr_mult", "float", 0.0, 5.0),
    "FORGE_GATE_DIRLOCK_FLIP_THRESHOLD": ("bb_breakout", "dirlock_flip_threshold", "int", 1.0, 7.0),
    "FORGE_GATE_DIRLOCK_NEUTRAL_THRESHOLD": ("bb_breakout", "dirlock_neutral_threshold", "int", 1.0, 7.0),
    "FORGE_GATE_DIRLOCK_H1_DISAGREEMENT": ("bb_breakout", "dirlock_h1_disagreement", "float", 0.0, 5.0),
    "FORGE_TIMING_DIRLOCK_BREAK_BILATERAL_COOLDOWN_BARS": ("bb_breakout", "dirlock_break_bilateral_cooldown_bars", "int", 0.0, 50.0),
    "FORGE_TIMING_DIRLOCK_SWING_LOOKBACK_BARS": ("bb_breakout", "dirlock_swing_lookback_bars", "int", 1.0, 50.0),
    # v2.7.98 Set 1 — Multi-leg batch entry infrastructure (helper exists, NOT YET WIRED at setup-trigger sites).
    # At batch_size=1, behavior identical to current single-position. Operator-decided: batch_size=4, Option 1A (literal).
    "FORGE_GEOMETRY_BATCH_SIZE": ("bb_breakout", "batch_size", "int", 1.0, 7.0),
    "FORGE_GEOMETRY_BATCH_MODE": ("bb_breakout", "batch_mode", "int", 0.0, 1.0),
    "FORGE_GEOMETRY_BATCH_SPACING_ATR_MULT": ("bb_breakout", "batch_spacing_atr_mult", "float", 0.0, 5.0),
    "FORGE_GEOMETRY_BATCH_MAX_LEGS": ("bb_breakout", "batch_max_legs", "int", 1.0, 7.0),
    # v2.7.100 Set 3 Option 3C — SL-trail-driven dynamic TP3 (operator pick: literal "using the S/L movement").
    # Decision: docs/FORGE_CORE_LOGIC_DESIGN.md §9 changelog 2026-05-14.
    "FORGE_GEOMETRY_TP3_MODE": ("bb_breakout", "tp3_mode", "int", 0.0, 1.0),
    "FORGE_GEOMETRY_TP3_DIST_FROM_SL_ATR_MULT": ("bb_breakout", "tp3_dist_from_sl_atr_mult", "float", 0.5, 10.0),
    # v2.7.101 Set 4 Option 4B — structural pending cancel (operator pick: "Cool Period NOT a timer").
    # Decision: docs/FORGE_CORE_LOGIC_DESIGN.md §9 changelog 2026-05-14.
    "FORGE_TIMING_COOL_PERIOD_STRUCTURE_CANCEL_ENABLED": ("bb_breakout", "structure_flip_cancel_enabled", "bool01", None, None),
    # v2.7.103 Gap 1 — extend cascade-stack sweep to BB_BREAKOUT L1/L2 (slots 0+1).
    # Default-OFF because some BB_BREAKOUT retraces are intentional. Decision: FORGE_TRADE_FLOW_BUY_SELL.md §8 v2.7.103 entry.
    "FORGE_TIMING_STRUCTURE_CANCEL_INCLUDES_BREAKOUT_L1L2": ("bb_breakout", "structure_cancel_includes_breakout_l1l2", "bool01", None, None),
    # v2.7.103 Gap 2 — walker for per-trigger setup pendings (magic == group_magic, no +20000 offset).
    # Mirrors CancelPendingOnDailyFlip pattern (ea/FORGE.mq5:3449). Default-OFF.
    "FORGE_TIMING_PENDING_PRE_TRIGGER_STRUCT_CANCEL_ENABLED": ("bb_breakout", "pending_pre_trigger_struct_cancel_enabled", "bool01", None, None),
    # v2.7.102 — TP pip-floor hybrid (operator spec TP1=40 pips, TP2=60 pips with ATR adaptation).
    # Each TP tier: actual distance = max(pip_floor × PipSize, atr_mult × ATR). Default 0 = pure ATR (current).
    # PipSize auto-detected: 2-digit XAUUSD pip=point; 3/5-digit broker pip=10×point.
    # Decision: docs/FORGE_CORE_LOGIC_DESIGN.md §9 changelog 2026-05-14 (TP1 hybrid pick).
    "FORGE_GEOMETRY_TP1_PIP_FLOOR": ("bb_breakout", "tp1_pip_floor", "float", 0.0, 1000.0),
    "FORGE_GEOMETRY_TP2_PIP_FLOOR": ("bb_breakout", "tp2_pip_floor", "float", 0.0, 1000.0),
    "FORGE_GEOMETRY_TP3_PIP_FLOOR": ("bb_breakout", "tp3_pip_floor", "float", 0.0, 2000.0),
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
    "FORGE_GATE_DAILY_DIRECTION_ENABLE":  ("safety", "daily_direction_gate_enabled",  "bool01", None, None),
    "FORGE_ATOM_DAILY_SMA_PERIOD":               ("safety", "daily_sma_period",              "int",    2,    200),
    "FORGE_ATOM_DAILY_SMA_LOOKBACK":        ("safety", "daily_sma_lookback_days",       "int",    1,    30),
    "FORGE_ATOM_DAILY_SLOPE_BLOCK_ATR":          ("safety", "daily_slope_block_atr",         "float",  0.0,  5.0),
    "FORGE_ATOM_DAILY_MOVE_BLOCK_ATR":           ("safety", "daily_move_block_atr",          "float",  0.0,  5.0),
    "FORGE_ATOM_DAILY_MOVE_FLIP_HYSTERESIS":     ("safety", "daily_move_flip_hysteresis",    "float",  0.0,  5.0),
    "FORGE_GATE_DAILY_FLIP_CANCEL_PENDING":   ("safety", "daily_cancel_pending_on_flip",  "bool01", None, None),
    "FORGE_GATE_DAILY_FLIP_CANCEL_CASCADE":  ("safety", "daily_cancel_includes_cascade", "bool01", None, None),
    # 2.7.28 — Momentum dump-catch market entry (Run 17 trend-capture gap fix).
    "FORGE_DUMP_CATCH_ENABLED":      ("safety", "dump_catch_enabled",      "bool01", None, None),
    "FORGE_DUMP_LOOKBACK_BARS":      ("safety", "dump_lookback_bars",      "int",    1,    20),
    "FORGE_DUMP_ATR_MULT":           ("safety", "dump_atr_mult",           "float",  0.3,  5.0),
    "FORGE_DUMP_MAX_RSI":            ("safety", "dump_max_rsi",            "float",  0,    100),
    "FORGE_ATOM_DUMP_RSI_MAX_BUY":        ("safety", "dump_max_rsi_buy",        "float",  0,    100),
    "FORGE_DUMP_MIN_ADX":            ("safety", "dump_min_adx",            "float",  0,    100),
    "FORGE_DUMP_REQUIRE_PSAR":       ("safety", "dump_require_psar",       "bool01", None, None),
    "FORGE_DUMP_REQUIRE_D1_BIAS":    ("safety", "dump_require_d1_bias",    "bool01", None, None),
    "FORGE_DUMP_COOLDOWN_SECONDS":   ("safety", "dump_cooldown_seconds",   "int",    0,    7200),
    "FORGE_DUMP_LOT_FACTOR":         ("safety", "dump_lot_factor",         "float",  0.01, 2.0),
    "FORGE_GEOMETRY_DUMP_LOT_FACTOR_BUY":     ("safety", "dump_buy_lot_factor",     "float",  0.0,  2.0),
    "FORGE_GEOMETRY_DUMP_LOT_FACTOR_SELL":    ("safety", "dump_sell_lot_factor",    "float",  0.0,  2.0),
    "FORGE_ATOM_DUMP_H1_TREND_MAX_SELL":        ("safety", "dump_sell_h1_max",        "float",  0.0,  10.0),
    # 2.7.54 — Exit discipline + asymmetric TP1 (operator: "gold is not stocks — no mercy in forex")
    "FORGE_GEOMETRY_DUMP_SL_ATR_MULT_BUY":       ("safety", "dump_sl_atr_mult_buy",     "float",  0.3,  10.0),
    "FORGE_GEOMETRY_DUMP_SL_ATR_MULT_SELL":      ("safety", "dump_sl_atr_mult_sell",    "float",  0.3,  10.0),
    "FORGE_GEOMETRY_DUMP_TP1_ATR_MULT_BUY":      ("safety", "dump_tp1_atr_mult_buy",    "float",  0.1,  5.0),
    "FORGE_GEOMETRY_DUMP_TP1_ATR_MULT_SELL":     ("safety", "dump_tp1_atr_mult_sell",   "float",  0.1,  5.0),
    "FORGE_TIMING_DUMP_MAX_HOLD_SECONDS":        ("safety", "dump_max_hold_seconds",    "int",    0,    7200),
    # 2.7.55 — SELL oversold protection (Run 26 G5003 fix)
    "FORGE_GATE_DUMP_SELL_MIN_RSI":              ("safety", "dump_sell_min_rsi",          "float",  0,    100),
    "FORGE_GATE_DUMP_SELL_BLOCK_BELOW_BB_L":     ("safety", "dump_sell_block_below_bb_l", "bool01", None, None),
    # 2.7.55.1 — Conjoint RSI gate for bbl block — only block when RSI confirms exhaustion (preserves G5001/G5002 winners)
    "FORGE_GATE_DUMP_BELOW_BBL_BLOCK_MAX_RSI":   ("safety", "dump_below_bbl_block_max_rsi", "float",  0,    100),
    # 2.7.56 — Multi-leg pyramid + continuous-fire (operator: "fire 5 legs, 1x→5x escalating, no cooldown, millionaire days")
    "FORGE_SETUP_DUMP_LEGS_PER_GROUP":           ("safety", "dump_legs_per_group",          "int",    0,    30),
    "FORGE_GATE_DUMP_MAX_OPEN_SAME_DIRECTION":   ("safety", "dump_max_open_same_direction", "int",    0,    100),
    "FORGE_SETUP_DUMP_PYRAMID_ENABLED":          ("safety", "dump_pyramid_enabled",         "bool01", None, None),
    "FORGE_GEOMETRY_DUMP_PYRAMID_BASE_FACTOR":   ("safety", "dump_pyramid_base_factor",     "float",  0.1,  10.0),
    "FORGE_GEOMETRY_DUMP_PYRAMID_STEP":          ("safety", "dump_pyramid_step",            "float",  -10.0, 10.0),  # v2.7.66 — negative allowed for DECREASING pyramid
    "FORGE_GEOMETRY_DUMP_PYRAMID_MAX_FACTOR":    ("safety", "dump_pyramid_max_factor",      "float",  0.1,  20.0),
    # v2.7.66 — Decreasing pyramid floor (operator: "5×,4×,3×,2×,1× — big lot at best entry, smaller adds")
    "FORGE_GEOMETRY_DUMP_PYRAMID_MIN_FACTOR":    ("safety", "dump_pyramid_min_factor",      "float",  0.0,  20.0),
    # v2.7.66 — Configurable TP2 (was hardcoded 1.0×ATR; widened to match wide SL)
    "FORGE_GEOMETRY_DUMP_TP2_ATR_MULT_BUY":      ("safety", "dump_tp2_atr_mult_buy",        "float",  0.1,  20.0),
    "FORGE_GEOMETRY_DUMP_TP2_ATR_MULT_SELL":     ("safety", "dump_tp2_atr_mult_sell",       "float",  0.1,  20.0),
    # v2.7.59 — MOMENTUM_DUMP cascade enable (gate the v2.7.28 hardcoded skip)
    "FORGE_GATE_DUMP_CASCADE_ENABLED":           ("safety", "dump_cascade_enabled",         "bool01", None, None),
    # v2.7.60 — MD V2 composite
    "FORGE_GATE_DUMP_V2_ENABLED":                ("safety", "dump_v2_enabled",              "bool01", None, None),
    "FORGE_GATE_DUMP_SELL_H4_MAX":               ("safety", "dump_sell_h4_max",             "float",  -10.0, 10.0),
    "FORGE_GATE_DUMP_BUY_H4_MIN":                ("safety", "dump_buy_h4_min",              "float",  -10.0, 10.0),
    "FORGE_GATE_DUMP_SELL_MACD_MAX":             ("safety", "dump_sell_macd_max",           "float",  -10.0, 10.0),
    "FORGE_GATE_DUMP_BUY_MACD_MIN":              ("safety", "dump_buy_macd_min",            "float",  -10.0, 10.0),
    "FORGE_GATE_DUMP_SELL_VWAP_ATR_MIN":         ("safety", "dump_sell_vwap_atr_min",       "float",  0.0,   5.0),
    "FORGE_GATE_DUMP_BUY_VWAP_ATR_MIN":          ("safety", "dump_buy_vwap_atr_min",        "float",  0.0,   5.0),
    "FORGE_GATE_DUMP_SELL_POC_ATR_MIN":          ("safety", "dump_sell_poc_atr_min",        "float",  0.0,   5.0),
    "FORGE_GATE_DUMP_BUY_POC_ATR_MIN":           ("safety", "dump_buy_poc_atr_min",         "float",  0.0,   5.0),
    "FORGE_GATE_DUMP_MAX_ADX":                   ("safety", "dump_max_adx",                 "float",  0.0,   80.0),
    "FORGE_GATE_DUMP_SELL_LATE_RSI_BLOCK":       ("safety", "dump_sell_late_rsi_block",     "float",  0.0,   100.0),
    "FORGE_GATE_DUMP_BUY_LATE_RSI_BLOCK":        ("safety", "dump_buy_late_rsi_block",      "float",  0.0,   100.0),
    # v2.7.61 — Day-extreme distance gate
    "FORGE_GATE_DUMP_BUY_MAX_DIST_FROM_DAY_HIGH_ATR":  ("safety", "dump_buy_max_dist_from_day_high_atr",  "float", 0.0, 10.0),
    "FORGE_GATE_DUMP_SELL_MAX_DIST_FROM_DAY_LOW_ATR":  ("safety", "dump_sell_max_dist_from_day_low_atr",  "float", 0.0, 10.0),
    # v2.7.62 — Distance amplifier (reward deep-room entries)
    "FORGE_GEOMETRY_DUMP_DIST_AMPLIFIER_ENABLED":              ("safety", "dump_dist_amplifier_enabled",              "bool01", None, None),
    "FORGE_GEOMETRY_DUMP_DIST_AMPLIFIER_THRESHOLD_ATR":        ("safety", "dump_dist_amplifier_threshold_atr",        "float", 0.0, 20.0),
    "FORGE_GEOMETRY_DUMP_DIST_AMPLIFIER_FACTOR":               ("safety", "dump_dist_amplifier_factor",               "float", 0.1, 10.0),
    "FORGE_GEOMETRY_DUMP_DIST_AMPLIFIER_STRONG_THRESHOLD_ATR": ("safety", "dump_dist_amplifier_strong_threshold_atr", "float", 0.0, 20.0),
    "FORGE_GEOMETRY_DUMP_DIST_AMPLIFIER_STRONG_FACTOR":        ("safety", "dump_dist_amplifier_strong_factor",        "float", 0.1, 10.0),
    # v2.7.63 — Killzone-tier amplifier (operator: "kills move fast within secs")
    "FORGE_GATE_DUMP_KZ_AMPLIFIER_ENABLED":      ("safety", "dump_kz_amplifier_enabled", "bool01", None, None),
    "FORGE_TIMING_DUMP_KZ_TIER1_MAX_MIN":        ("safety", "dump_kz_tier1_max_min",     "float", 0.0, 720.0),
    "FORGE_GEOMETRY_DUMP_KZ_TIER1_FACTOR":       ("safety", "dump_kz_tier1_factor",      "float", 0.0, 10.0),
    "FORGE_TIMING_DUMP_KZ_TIER2_MAX_MIN":        ("safety", "dump_kz_tier2_max_min",     "float", 0.0, 720.0),
    "FORGE_GEOMETRY_DUMP_KZ_TIER2_FACTOR":       ("safety", "dump_kz_tier2_factor",      "float", 0.0, 10.0),
    "FORGE_TIMING_DUMP_KZ_TIER3_MAX_MIN":        ("safety", "dump_kz_tier3_max_min",     "float", 0.0, 720.0),
    "FORGE_GEOMETRY_DUMP_KZ_TIER3_FACTOR":       ("safety", "dump_kz_tier3_factor",      "float", 0.0, 10.0),
    "FORGE_TIMING_DUMP_KZ_TIER4_MAX_MIN":        ("safety", "dump_kz_tier4_max_min",     "float", 0.0, 720.0),
    "FORGE_GEOMETRY_DUMP_KZ_TIER4_FACTOR":       ("safety", "dump_kz_tier4_factor",      "float", 0.0, 10.0),
    "FORGE_GEOMETRY_DUMP_KZ_TIER5_FACTOR":       ("safety", "dump_kz_tier5_factor",      "float", 0.0, 10.0),
    "FORGE_GEOMETRY_DUMP_KZ_NO_ZONE_FACTOR":     ("safety", "dump_kz_no_zone_factor",    "float", 0.0, 10.0),
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
    "FORGE_ATOM_HTF_H1_STRONG_FACTOR":  ("safety", "regime_h1_override_factor",  "float", 0.0, 10.0),
    "FORGE_ATOM_HTF_H1_STRONG_ADX_MIN": ("safety", "regime_h1_override_adx_min", "float", 0.0, 100.0),
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
    # 2.7.46 §11.5 — per-killzone trade cap (0=disabled). GATE scope per FORGE_NAMING_CONVENTIONS.md §4.
    "FORGE_GATE_KILLZONE_MAX_TRADES": ("session_filter", "killzones_max_trades_per_kz", "int",    0.0,  99.0),
    # 2.7.52 — KZ warmup gate per arongroups stop-hunt research. Blocks entries in first N min of any active KZ.
    "FORGE_GATE_KZ_WARMUP_MIN":       ("session_filter", "kz_warmup_min",               "int",    0.0,  60.0),
    "FORGE_KZ_ASIA_START_MIN":        ("session_filter", "kz_asia_start_min",         "int",    0.0,  1439.0),
    "FORGE_KZ_ASIA_END_MIN":          ("session_filter", "kz_asia_end_min",           "int",    0.0,  1440.0),
    "FORGE_KZ_LONDON_OPEN_START_MIN": ("session_filter", "kz_london_open_start_min",  "int",    0.0,  1439.0),
    "FORGE_KZ_LONDON_OPEN_END_MIN":   ("session_filter", "kz_london_open_end_min",    "int",    0.0,  1440.0),
    "FORGE_KZ_NY_OPEN_START_MIN":     ("session_filter", "kz_ny_open_start_min",      "int",    0.0,  1439.0),
    "FORGE_KZ_NY_OPEN_END_MIN":       ("session_filter", "kz_ny_open_end_min",        "int",    0.0,  1440.0),
    "FORGE_KZ_LONDON_CLOSE_START_MIN":("session_filter", "kz_london_close_start_min", "int",    0.0,  1439.0),
    "FORGE_KZ_LONDON_CLOSE_END_MIN":  ("session_filter", "kz_london_close_end_min",   "int",    0.0,  1440.0),
    # 2.7.38 Tier 1 Boolean Composites (all default-OFF; see docs/FORGE_INDICATOR_ATLAS.md §5).
    # Composites that GATE/AMPLIFY existing setups stay in composites.* scope.
    "FORGE_BLOCK_SELL_IN_CHOP_ENABLED":       ("composites", "block_sell_in_chop_enabled",       "bool01", None, None),
    "FORGE_INTRADAY_REVERSAL_SELL_ENABLED":   ("composites", "intraday_reversal_sell_enabled",   "bool01", None, None),
    "FORGE_INTRADAY_REVERSAL_SELL_LOT_MULT":  ("composites", "intraday_reversal_sell_lot_mult",  "float",  0.5,   5.0),
    # 2.7.51 §11.4 — killzone-aware composite refinements (FORGE_REGIME_TAXONOMY.md §11.4)
    "FORGE_GATE_INTRADAY_REVERSAL_REQUIRE_PRIME_KZ":  ("composites", "intraday_reversal_require_prime_kz",  "bool01", None, None),
    "FORGE_AMPLIFY_BULL_DAY_DIP_BUY_PRIME_FACTOR":   ("composites", "bull_day_dip_buy_prime_amplifier",     "float",  0.5,  5.0),
    "FORGE_GATE_DUMP_JUDAS_WINDOW_BLOCK":            ("composites", "dump_judas_window_block",              "bool01", None, None),
    # 2.7.42 Phase 2 §10.5.1c composite split — FRACTIONAL_SELL_IN_BULL + BULL_DAY_DIP_BUY
    # emit their own setup_type strings → env names move to SETUP/GEOMETRY/TIMING scopes
    # per FORGE_NAMING_CONVENTIONS.md §4.9. JSON destinations stay in composites.* per the
    # Python-contract preservation rule (§10.5.0.1). Legacy env names still work via
    # ENV_KEY_ALIASES below.
    "FORGE_SETUP_FRACTIONAL_SELL_IN_BULL_ENABLED":         ("composites", "fractional_sell_in_bull_enabled",         "bool01", None, None),
    "FORGE_GEOMETRY_FRACTIONAL_SELL_IN_BULL_LOT_FACTOR":   ("composites", "fractional_sell_in_bull_lot_factor",      "float",  0.05, 1.0),
    "FORGE_GEOMETRY_FRACTIONAL_SELL_IN_BULL_SL_ATR_MULT":  ("composites", "fractional_sell_in_bull_sl_atr_mult",     "float",  0.5,  5.0),
    "FORGE_GEOMETRY_FRACTIONAL_SELL_IN_BULL_TP1_ATR_MULT": ("composites", "fractional_sell_in_bull_tp1_atr_mult",    "float",  0.1,  2.0),
    "FORGE_SETUP_BULL_DAY_DIP_BUY_ENABLED":                ("composites", "bull_day_dip_buy_enabled",                "bool01", None, None),
    "FORGE_GEOMETRY_BULL_DAY_DIP_BUY_LOT_MULT":            ("composites", "bull_day_dip_buy_lot_mult",               "float",  0.1,  10.0),
    "FORGE_GEOMETRY_BULL_DAY_DIP_BUY_SL_ATR_MULT":         ("composites", "bull_day_dip_buy_sl_atr_mult",            "float",  0.3,  5.0),
    "FORGE_GEOMETRY_BULL_DAY_DIP_BUY_TP1_ATR_MULT":        ("composites", "bull_day_dip_buy_tp1_atr_mult",           "float",  0.1,  3.0),
    "FORGE_TIMING_BULL_DAY_DIP_BUY_REENTRY_COOLDOWN_SEC":  ("composites", "bull_day_dip_buy_reentry_cooldown_sec",   "int",    0.0,  3600.0),
    "FORGE_TESTER_COOLDOWN_ENABLED": ("safety", "tester_cooldown_enabled", "bool01", None, None),
    "FORGE_DIRECTION_COOLDOWN_ENABLED": ("safety", "direction_cooldown_enabled", "bool01", None, None),
    "FORGE_DIRECTION_COOLDOWN_BARS": ("safety", "direction_cooldown_bars", "int", 0.0, 50.0),
    "FORGE_JOURNAL_ENABLED": ("journal", "journal_enabled", "bool01", None, None),
    "FORGE_JOURNAL_RECORD_SKIPS": ("journal", "journal_record_skips", "bool01", None, None),
    "FORGE_JOURNAL_IMPORT_TRADES": ("journal", "journal_import_trades", "bool01", None, None),
    "FORGE_JOURNAL_IMPORT_DEPTH_DAYS": ("journal", "journal_import_depth_days", "int", 1.0, 365.0),
    "FORGE_JOURNAL_STATS_INTERVAL_SEC": ("journal", "journal_stats_interval_sec", "int", 60.0, 3600.0),
    # v2.7.111 — SQLite I/O performance (per mql5.com/articles/22009, 3500× speedup from transactions).
    # All three default-OFF; operator-recommended: ALL three = 1 for max performance.
    "FORGE_JOURNAL_SIGNALS_BATCH_TXN": ("journal", "journal_signals_batch_txn", "bool01", None, None),
    "FORGE_JOURNAL_WAL_MODE":          ("journal", "journal_wal_mode",          "bool01", None, None),
    "FORGE_JOURNAL_SYNCHRONOUS_NORMAL":("journal", "journal_synchronous_normal","bool01", None, None),

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

    # ── Swing-point shared infrastructure (Tier 3 reversal/pattern setups consume this) ──
    "FORGE_ATOM_SWING_LOOKBACK_BARS":                 ("atom",     "swing_lookback_bars",                "int",    2.0, 10.0),
    "FORGE_ATOM_SWING_MIN_SIZE_ATR":                  ("atom",     "swing_min_size_atr",                 "float",  0.1, 10.0),

    # ── Double Top / Bottom (Tier 3 — first consumers of swing infra) ──
    "FORGE_SETUP_DOUBLE_TOP_ENABLED":                 ("setup",    "double_top_enabled",                 "bool01", None, None),
    "FORGE_SETUP_DOUBLE_BOTTOM_ENABLED":              ("setup",    "double_bottom_enabled",              "bool01", None, None),
    "FORGE_ATOM_DOUBLE_PATTERN_PEAK_TOLERANCE_ATR":   ("atom",     "double_pattern_peak_tolerance_atr",  "float",  0.05, 2.0),
    "FORGE_ATOM_DOUBLE_PATTERN_MIN_NECKLINE_DROP_ATR":("atom",     "double_pattern_min_neckline_drop_atr","float",  0.1, 10.0),
    "FORGE_ATOM_DOUBLE_PATTERN_ADX_MIN":              ("atom",     "double_pattern_adx_min",             "float",  5.0, 80.0),
    "FORGE_GEOMETRY_DOUBLE_PATTERN_LOT_FACTOR":       ("geometry", "double_pattern_lot_factor",          "float",  0.1, 2.0),
    "FORGE_GEOMETRY_DOUBLE_PATTERN_SL_ATR_MULT":      ("geometry", "double_pattern_sl_atr_mult",         "float",  0.5, 5.0),
    "FORGE_GEOMETRY_DOUBLE_PATTERN_TP1_ATR_MULT":     ("geometry", "double_pattern_tp1_atr_mult",        "float",  0.1, 5.0),
    "FORGE_GEOMETRY_DOUBLE_PATTERN_TP2_ATR_MULT":     ("geometry", "double_pattern_tp2_atr_mult",        "float",  0.1, 10.0),
    "FORGE_TIMING_DOUBLE_PATTERN_COOLDOWN_SECONDS":   ("timing",   "double_pattern_cooldown_seconds",    "int",    0.0, 7200.0),

    # ── H&S / Inverse H&S (Tier 3 — 3-swing reversal pattern with neckline) ──
    "FORGE_SETUP_HEAD_AND_SHOULDERS_ENABLED":         ("setup",    "head_and_shoulders_enabled",         "bool01", None, None),
    "FORGE_SETUP_INVERSE_HEAD_AND_SHOULDERS_ENABLED": ("setup",    "inverse_head_and_shoulders_enabled", "bool01", None, None),
    "FORGE_ATOM_HS_SHOULDER_TOLERANCE_ATR":           ("atom",     "hs_shoulder_tolerance_atr",          "float",  0.05, 2.0),
    "FORGE_ATOM_HS_HEAD_PROMINENCE_ATR":              ("atom",     "hs_head_prominence_atr",             "float",  0.1, 10.0),
    "FORGE_ATOM_HS_ADX_MIN":                          ("atom",     "hs_adx_min",                         "float",  5.0, 80.0),
    "FORGE_GEOMETRY_HS_LOT_FACTOR":                   ("geometry", "hs_lot_factor",                      "float",  0.1, 2.0),
    "FORGE_GEOMETRY_HS_SL_ATR_MULT":                  ("geometry", "hs_sl_atr_mult",                     "float",  0.5, 5.0),
    "FORGE_GEOMETRY_HS_TP1_ATR_MULT":                 ("geometry", "hs_tp1_atr_mult",                    "float",  0.1, 5.0),
    "FORGE_GEOMETRY_HS_TP2_ATR_MULT":                 ("geometry", "hs_tp2_atr_mult",                    "float",  0.1, 10.0),
    "FORGE_TIMING_HS_COOLDOWN_SECONDS":               ("timing",   "hs_cooldown_seconds",                "int",    0.0, 7200.0),

    # ── Flag/Pennant (Tier 3 — impulse + consolidation + breakout, stateless) ──
    "FORGE_SETUP_FLAG_PENNANT_ENABLED":               ("setup",    "flag_pennant_enabled",               "bool01", None, None),
    "FORGE_ATOM_FLAG_PENNANT_IMPULSE_LOOKBACK_BARS":  ("atom",     "flag_pennant_impulse_lookback_bars", "int",    3.0, 30.0),
    "FORGE_ATOM_FLAG_PENNANT_IMPULSE_MIN_ATR":        ("atom",     "flag_pennant_impulse_min_atr",       "float",  0.5, 10.0),
    "FORGE_ATOM_FLAG_PENNANT_CONSOLIDATION_BARS":     ("atom",     "flag_pennant_consolidation_bars",    "int",    2.0, 20.0),
    "FORGE_ATOM_FLAG_PENNANT_CONSOLIDATION_MAX_ATR":  ("atom",     "flag_pennant_consolidation_max_atr", "float",  0.1, 5.0),
    "FORGE_ATOM_FLAG_PENNANT_ADX_MIN":                ("atom",     "flag_pennant_adx_min",               "float",  5.0, 80.0),
    "FORGE_GEOMETRY_FLAG_PENNANT_LOT_FACTOR":         ("geometry", "flag_pennant_lot_factor",            "float",  0.1, 2.0),
    "FORGE_GEOMETRY_FLAG_PENNANT_SL_ATR_MULT":        ("geometry", "flag_pennant_sl_atr_mult",           "float",  0.5, 5.0),
    "FORGE_GEOMETRY_FLAG_PENNANT_TP1_ATR_MULT":       ("geometry", "flag_pennant_tp1_atr_mult",          "float",  0.1, 5.0),
    "FORGE_GEOMETRY_FLAG_PENNANT_TP2_ATR_MULT":       ("geometry", "flag_pennant_tp2_atr_mult",          "float",  0.1, 10.0),
    "FORGE_TIMING_FLAG_PENNANT_COOLDOWN_SECONDS":     ("timing",   "flag_pennant_cooldown_seconds",      "int",    0.0, 7200.0),

    # ── Trendline Bounce (Tier 3 — diagonal trendline through 2 same-direction swings) ──
    "FORGE_SETUP_TRENDLINE_BOUNCE_ENABLED":           ("setup",    "trendline_bounce_enabled",           "bool01", None, None),
    "FORGE_ATOM_TRENDLINE_TOUCH_TOLERANCE_ATR":       ("atom",     "trendline_touch_tolerance_atr",      "float",  0.05, 2.0),
    "FORGE_ATOM_TRENDLINE_ADX_MIN":                   ("atom",     "trendline_adx_min",                  "float",  5.0, 80.0),
    "FORGE_GEOMETRY_TRENDLINE_BOUNCE_LOT_FACTOR":     ("geometry", "trendline_bounce_lot_factor",        "float",  0.1, 2.0),
    "FORGE_GEOMETRY_TRENDLINE_BOUNCE_SL_ATR_MULT":    ("geometry", "trendline_bounce_sl_atr_mult",       "float",  0.5, 5.0),
    "FORGE_GEOMETRY_TRENDLINE_BOUNCE_TP1_ATR_MULT":   ("geometry", "trendline_bounce_tp1_atr_mult",      "float",  0.1, 5.0),
    "FORGE_GEOMETRY_TRENDLINE_BOUNCE_TP2_ATR_MULT":   ("geometry", "trendline_bounce_tp2_atr_mult",      "float",  0.1, 10.0),
    "FORGE_TIMING_TRENDLINE_BOUNCE_COOLDOWN_SECONDS": ("timing",   "trendline_bounce_cooldown_seconds",  "int",    0.0, 7200.0),

    # ── S/R Flip (Tier 3 — broken level retests as opposite role) ──
    "FORGE_SETUP_SR_FLIP_ENABLED":                    ("setup",    "sr_flip_enabled",                    "bool01", None, None),
    "FORGE_ATOM_SR_FLIP_TOLERANCE_ATR":               ("atom",     "sr_flip_tolerance_atr",              "float",  0.05, 2.0),
    "FORGE_ATOM_SR_FLIP_ADX_MIN":                     ("atom",     "sr_flip_adx_min",                    "float",  5.0, 80.0),
    "FORGE_GEOMETRY_SR_FLIP_LOT_FACTOR":              ("geometry", "sr_flip_lot_factor",                 "float",  0.1, 2.0),
    "FORGE_GEOMETRY_SR_FLIP_SL_ATR_MULT":             ("geometry", "sr_flip_sl_atr_mult",                "float",  0.5, 5.0),
    "FORGE_GEOMETRY_SR_FLIP_TP1_ATR_MULT":            ("geometry", "sr_flip_tp1_atr_mult",               "float",  0.1, 5.0),
    "FORGE_GEOMETRY_SR_FLIP_TP2_ATR_MULT":            ("geometry", "sr_flip_tp2_atr_mult",               "float",  0.1, 10.0),
    "FORGE_TIMING_SR_FLIP_COOLDOWN_SECONDS":          ("timing",   "sr_flip_cooldown_seconds",           "int",    0.0, 7200.0),
}

# Screaming-SNAKE env key -> alternate names (camelCase) accepted from .env; first non-empty wins in order listed.
ENV_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "FORGE_NUM_TRADES": ("FORGE_NUM_TRADES", "forgeNumTrades"),
    "FORGE_MIN_NUM_TRADES": ("FORGE_MIN_NUM_TRADES", "forgeMinNumTrades"),
    "FORGE_MAX_NUM_TRADES": ("FORGE_MAX_NUM_TRADES", "forgeMaxNumTrades"),
    # 2.7.42 Phase 2 §10.5.1c composite split — legacy env names continue to resolve
    # for one EA version. Operator-facing migration: switch .env to the new SETUP/
    # GEOMETRY/TIMING-prefixed names; the old names will be removed in a future EA
    # version. JSON keys (composites.fractional_sell_in_bull_*, composites.bull_day_dip_buy_*)
    # are NOT renamed per the Python-contract preservation rule (§10.5.0.1).
    "FORGE_SETUP_FRACTIONAL_SELL_IN_BULL_ENABLED": (
        "FORGE_SETUP_FRACTIONAL_SELL_IN_BULL_ENABLED",      # canonical (preferred)
        "FORGE_FRACTIONAL_SELL_IN_BULL_ENABLED",            # legacy alias (deprecated)
    ),
    "FORGE_GEOMETRY_FRACTIONAL_SELL_IN_BULL_LOT_FACTOR": (
        "FORGE_GEOMETRY_FRACTIONAL_SELL_IN_BULL_LOT_FACTOR",
        "FORGE_FRACTIONAL_SELL_IN_BULL_LOT_FACTOR",
    ),
    "FORGE_GEOMETRY_FRACTIONAL_SELL_IN_BULL_SL_ATR_MULT": (
        "FORGE_GEOMETRY_FRACTIONAL_SELL_IN_BULL_SL_ATR_MULT",
        "FORGE_FRACTIONAL_SELL_IN_BULL_SL_ATR_MULT",
    ),
    "FORGE_GEOMETRY_FRACTIONAL_SELL_IN_BULL_TP1_ATR_MULT": (
        "FORGE_GEOMETRY_FRACTIONAL_SELL_IN_BULL_TP1_ATR_MULT",
        "FORGE_FRACTIONAL_SELL_IN_BULL_TP1_ATR_MULT",
    ),
    "FORGE_SETUP_BULL_DAY_DIP_BUY_ENABLED": (
        "FORGE_SETUP_BULL_DAY_DIP_BUY_ENABLED",
        "FORGE_BULL_DAY_DIP_BUY_ENABLED",
    ),
    "FORGE_GEOMETRY_BULL_DAY_DIP_BUY_LOT_MULT": (
        "FORGE_GEOMETRY_BULL_DAY_DIP_BUY_LOT_MULT",
        "FORGE_BULL_DAY_DIP_BUY_LOT_MULT",
    ),
    "FORGE_GEOMETRY_BULL_DAY_DIP_BUY_SL_ATR_MULT": (
        "FORGE_GEOMETRY_BULL_DAY_DIP_BUY_SL_ATR_MULT",
        "FORGE_BULL_DAY_DIP_BUY_SL_ATR_MULT",
    ),
    "FORGE_GEOMETRY_BULL_DAY_DIP_BUY_TP1_ATR_MULT": (
        "FORGE_GEOMETRY_BULL_DAY_DIP_BUY_TP1_ATR_MULT",
        "FORGE_BULL_DAY_DIP_BUY_TP1_ATR_MULT",
    ),
    "FORGE_TIMING_BULL_DAY_DIP_BUY_REENTRY_COOLDOWN_SEC": (
        "FORGE_TIMING_BULL_DAY_DIP_BUY_REENTRY_COOLDOWN_SEC",
        "FORGE_BULL_DAY_DIP_BUY_REENTRY_COOLDOWN_SEC",
    ),
    # 2.7.42 Phase 2 §10.5.1 + §10.5.1b — regime/HTF/Daily + setup-specific backfill renames.
    # Same legacy-alias pattern as §10.5.1c. Operator's existing .env continues to work;
    # deprecation warning at sync time points at the new canonical name.
    "FORGE_ATOM_HTF_H1_STRONG_FACTOR": (
        "FORGE_ATOM_HTF_H1_STRONG_FACTOR",
        "FORGE_REGIME_H1_OVERRIDE_FACTOR",
    ),
    "FORGE_ATOM_HTF_H1_STRONG_ADX_MIN": (
        "FORGE_ATOM_HTF_H1_STRONG_ADX_MIN",
        "FORGE_REGIME_H1_OVERRIDE_ADX_MIN",
    ),
    "FORGE_GATE_DAILY_DIRECTION_ENABLE": (
        "FORGE_GATE_DAILY_DIRECTION_ENABLE",
        "FORGE_DAILY_DIRECTION_GATE_ENABLED",
    ),
    "FORGE_GATE_DAILY_FLIP_CANCEL_PENDING": (
        "FORGE_GATE_DAILY_FLIP_CANCEL_PENDING",
        "FORGE_DAILY_CANCEL_PENDING_ON_FLIP",
    ),
    "FORGE_GATE_DAILY_FLIP_CANCEL_CASCADE": (
        "FORGE_GATE_DAILY_FLIP_CANCEL_CASCADE",
        "FORGE_DAILY_CANCEL_INCLUDES_CASCADE",
    ),
    "FORGE_ATOM_DAILY_SMA_PERIOD": (
        "FORGE_ATOM_DAILY_SMA_PERIOD",
        "FORGE_DAILY_SMA_PERIOD",
    ),
    "FORGE_ATOM_DAILY_SMA_LOOKBACK": (
        "FORGE_ATOM_DAILY_SMA_LOOKBACK",
        "FORGE_DAILY_SMA_LOOKBACK_DAYS",
    ),
    "FORGE_ATOM_DAILY_SLOPE_BLOCK_ATR": (
        "FORGE_ATOM_DAILY_SLOPE_BLOCK_ATR",
        "FORGE_DAILY_SLOPE_BLOCK_ATR",
    ),
    "FORGE_ATOM_DAILY_MOVE_BLOCK_ATR": (
        "FORGE_ATOM_DAILY_MOVE_BLOCK_ATR",
        "FORGE_DAILY_MOVE_BLOCK_ATR",
    ),
    "FORGE_ATOM_DAILY_MOVE_FLIP_HYSTERESIS": (
        "FORGE_ATOM_DAILY_MOVE_FLIP_HYSTERESIS",
        "FORGE_DAILY_MOVE_FLIP_HYSTERESIS",
    ),
    "FORGE_GATE_HTF_H4_RSI_ENABLE": (
        "FORGE_GATE_HTF_H4_RSI_ENABLE",
        "FORGE_H4_RSI_GATE_ENABLED",
    ),
    "FORGE_ATOM_HTF_H4_RSI_MAX_SELL": (
        "FORGE_ATOM_HTF_H4_RSI_MAX_SELL",
        "FORGE_H4_RSI_SELL_MAX",
    ),
    "FORGE_ATOM_HTF_H4_RSI_MIN_BUY": (
        "FORGE_ATOM_HTF_H4_RSI_MIN_BUY",
        "FORGE_H4_RSI_BUY_MIN",
    ),
    "FORGE_GATE_HTF_H4_ADX_ENABLE": (
        "FORGE_GATE_HTF_H4_ADX_ENABLE",
        "FORGE_H4_ADX_GATE_ENABLED",
    ),
    "FORGE_ATOM_HTF_H4_ADX_MIN_SELL": (
        "FORGE_ATOM_HTF_H4_ADX_MIN_SELL",
        "FORGE_H4_ADX_MIN_SELL",
    ),
    "FORGE_ATOM_HTF_H4_ADX_MIN_BUY": (
        "FORGE_ATOM_HTF_H4_ADX_MIN_BUY",
        "FORGE_H4_ADX_MIN_BUY",
    ),
    "FORGE_GATE_M5_ADX_HYSTERESIS_ENABLE": (
        "FORGE_GATE_M5_ADX_HYSTERESIS_ENABLE",
        "FORGE_ADX_HYSTERESIS_ENABLED",
    ),
    "FORGE_ATOM_M5_ADX_TREND_ENTER": (
        "FORGE_ATOM_M5_ADX_TREND_ENTER",
        "FORGE_ADX_TREND_ENTER",
    ),
    "FORGE_ATOM_M5_ADX_TREND_EXIT": (
        "FORGE_ATOM_M5_ADX_TREND_EXIT",
        "FORGE_ADX_TREND_EXIT",
    ),
    "FORGE_GATE_M5_ADX_HYSTERESIS_APPLY_IN_TESTER": (
        "FORGE_GATE_M5_ADX_HYSTERESIS_APPLY_IN_TESTER",
        "FORGE_ADX_HYSTERESIS_APPLY_IN_TESTER",
    ),
    "FORGE_GATE_BREAKOUT_HID_BULL_DIV_BLOCK_SELL": (
        "FORGE_GATE_BREAKOUT_HID_BULL_DIV_BLOCK_SELL",
        "FORGE_BREAKOUT_BLOCK_HID_BULL_SELL",
    ),
    "FORGE_ATOM_BREAKOUT_CRASH_BYPASS_M15_ADX_MIN_SELL": (
        "FORGE_ATOM_BREAKOUT_CRASH_BYPASS_M15_ADX_MIN_SELL",
        "FORGE_BREAKOUT_H1H4_CRASH_SELL_MIN_M15_ADX",
    ),
    "FORGE_GATE_BREAKOUT_H1_MACD_REQUIRE_BUY": (
        "FORGE_GATE_BREAKOUT_H1_MACD_REQUIRE_BUY",
        "FORGE_BREAKOUT_REQUIRE_H1_MACD_BUY",
    ),
    "FORGE_TIMING_BREAKOUT_SAME_DIR_COOLDOWN_SEC": (
        "FORGE_TIMING_BREAKOUT_SAME_DIR_COOLDOWN_SEC",
        "FORGE_BREAKOUT_SAME_DIR_COOLDOWN_SECONDS",
    ),
    "FORGE_GEOMETRY_SELL_STOP_CONT_LEGS": (
        "FORGE_GEOMETRY_SELL_STOP_CONT_LEGS",
        "FORGE_SELL_STOP_CONT_LEGS",
    ),
    "FORGE_ATOM_SELL_STOP_CONT_M5_ADX_MIN": (
        "FORGE_ATOM_SELL_STOP_CONT_M5_ADX_MIN",
        "FORGE_SELL_STOP_CONT_MIN_ADX",
    ),
    "FORGE_GATE_SELL_STOP_CONT_H1_DI_REQUIRE": (
        "FORGE_GATE_SELL_STOP_CONT_H1_DI_REQUIRE",
        "FORGE_SELL_STOP_CONT_REQUIRE_H1_DI",
    ),
    "FORGE_GEOMETRY_SELL_STOP_CONT_SL_ATR_MULT": (
        "FORGE_GEOMETRY_SELL_STOP_CONT_SL_ATR_MULT",
        "FORGE_SELL_STOP_CONT_SL_ATR_MULT",
    ),
    "FORGE_GEOMETRY_DUMP_LOT_FACTOR_BUY": (
        "FORGE_GEOMETRY_DUMP_LOT_FACTOR_BUY",
        "FORGE_DUMP_BUY_LOT_FACTOR",
    ),
    "FORGE_GEOMETRY_DUMP_LOT_FACTOR_SELL": (
        "FORGE_GEOMETRY_DUMP_LOT_FACTOR_SELL",
        "FORGE_DUMP_SELL_LOT_FACTOR",
    ),
    "FORGE_ATOM_DUMP_H1_TREND_MAX_SELL": (
        "FORGE_ATOM_DUMP_H1_TREND_MAX_SELL",
        "FORGE_DUMP_SELL_H1_MAX",
    ),
    "FORGE_ATOM_DUMP_RSI_MAX_BUY": (
        "FORGE_ATOM_DUMP_RSI_MAX_BUY",
        "FORGE_DUMP_MAX_RSI_BUY",
    ),
    "FORGE_GEOMETRY_STAGED_SCALE_IN_FORCE": (
        "FORGE_GEOMETRY_STAGED_SCALE_IN_FORCE",
        "FORGE_NATIVE_FORCE_STAGED_SCALE_IN",
    ),
    "FORGE_GEOMETRY_LEGS_CLEAR_TREND_FACTOR": (
        "FORGE_GEOMETRY_LEGS_CLEAR_TREND_FACTOR",
        "FORGE_NATIVE_LEGS_CLEAR_TREND_FACTOR",
    ),
    "FORGE_GEOMETRY_NATIVE_USE_LIMIT_ENTRY": (
        "FORGE_GEOMETRY_NATIVE_USE_LIMIT_ENTRY",
        "FORGE_NATIVE_SCALPER_USE_LIMIT_ENTRY",
    ),
    "FORGE_GEOMETRY_WAVE_CONFIRM_LOT_MULT": (
        "FORGE_GEOMETRY_WAVE_CONFIRM_LOT_MULT",
        "FORGE_WAVE_CONFIRMATION_LOT_MULT",
    ),
}


# 2.7.42 Phase 2 §10.5.1c — env names that are deprecated. When _env_raw resolves to
# one of these instead of the canonical name, emit a one-line deprecation warning
# pointing the operator at the new name. (Only deprecations are warned — neutral
# aliases like forgeNumTrades/FORGE_NUM_TRADES are not warned.)
DEPRECATED_ALIASES: set[str] = {
    "FORGE_FRACTIONAL_SELL_IN_BULL_ENABLED",
    "FORGE_FRACTIONAL_SELL_IN_BULL_LOT_FACTOR",
    "FORGE_FRACTIONAL_SELL_IN_BULL_SL_ATR_MULT",
    "FORGE_FRACTIONAL_SELL_IN_BULL_TP1_ATR_MULT",
    "FORGE_BULL_DAY_DIP_BUY_ENABLED",
    "FORGE_BULL_DAY_DIP_BUY_LOT_MULT",
    "FORGE_BULL_DAY_DIP_BUY_SL_ATR_MULT",
    "FORGE_BULL_DAY_DIP_BUY_TP1_ATR_MULT",
    "FORGE_BULL_DAY_DIP_BUY_REENTRY_COOLDOWN_SEC",
    # 2.7.42 Phase 2 §10.5.1 + §10.5.1b legacy names
    "FORGE_REGIME_H1_OVERRIDE_FACTOR",
    "FORGE_REGIME_H1_OVERRIDE_ADX_MIN",
    "FORGE_DAILY_DIRECTION_GATE_ENABLED",
    "FORGE_DAILY_CANCEL_PENDING_ON_FLIP",
    "FORGE_DAILY_CANCEL_INCLUDES_CASCADE",
    "FORGE_DAILY_SMA_PERIOD",
    "FORGE_DAILY_SMA_LOOKBACK_DAYS",
    "FORGE_DAILY_SLOPE_BLOCK_ATR",
    "FORGE_DAILY_MOVE_BLOCK_ATR",
    "FORGE_DAILY_MOVE_FLIP_HYSTERESIS",
    "FORGE_H4_RSI_GATE_ENABLED",
    "FORGE_H4_RSI_SELL_MAX",
    "FORGE_H4_RSI_BUY_MIN",
    "FORGE_H4_ADX_GATE_ENABLED",
    "FORGE_H4_ADX_MIN_SELL",
    "FORGE_H4_ADX_MIN_BUY",
    "FORGE_ADX_HYSTERESIS_ENABLED",
    "FORGE_ADX_TREND_ENTER",
    "FORGE_ADX_TREND_EXIT",
    "FORGE_ADX_HYSTERESIS_APPLY_IN_TESTER",
    "FORGE_BREAKOUT_BLOCK_HID_BULL_SELL",
    "FORGE_BREAKOUT_H1H4_CRASH_SELL_MIN_M15_ADX",
    "FORGE_BREAKOUT_REQUIRE_H1_MACD_BUY",
    "FORGE_BREAKOUT_SAME_DIR_COOLDOWN_SECONDS",
    "FORGE_SELL_STOP_CONT_LEGS",
    "FORGE_SELL_STOP_CONT_MIN_ADX",
    "FORGE_SELL_STOP_CONT_REQUIRE_H1_DI",
    "FORGE_SELL_STOP_CONT_SL_ATR_MULT",
    "FORGE_DUMP_BUY_LOT_FACTOR",
    "FORGE_DUMP_SELL_LOT_FACTOR",
    "FORGE_DUMP_SELL_H1_MAX",
    "FORGE_DUMP_MAX_RSI_BUY",
    "FORGE_NATIVE_FORCE_STAGED_SCALE_IN",
    "FORGE_NATIVE_LEGS_CLEAR_TREND_FACTOR",
    "FORGE_NATIVE_SCALPER_USE_LIMIT_ENTRY",
    "FORGE_WAVE_CONFIRMATION_LOT_MULT",
}
_DEPRECATION_WARNINGS_PRINTED: set[str] = set()


def _env_raw(env: dict[str, str], env_key: str) -> str:
    aliases = ENV_KEY_ALIASES.get(env_key, (env_key,))
    canonical = aliases[0]
    for k in aliases:
        v = env.get(k, "").strip()
        if v:
            if k in DEPRECATED_ALIASES and k not in _DEPRECATION_WARNINGS_PRINTED:
                _DEPRECATION_WARNINGS_PRINTED.add(k)
                print(f"[sync] ⚠ DEPRECATED: .env has {k}=... — use {canonical} instead "
                      f"(legacy alias will be removed in a future EA version)")
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
