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
    "FORGE_MIN_NUM_TRADES": ("lot_sizing", "min_num_trades", "int", 1.0, 30.0),
    "FORGE_MAX_NUM_TRADES": ("lot_sizing", "max_num_trades", "int", 1.0, 30.0),
    "FORGE_GOLD_NATIVE_MAX_SELL_LEGS": ("lot_sizing", "gold_native_max_sell_legs", "int", 0.0, 30.0),
    "FORGE_NATIVE_LEGS_MAX_WHEN_UNCLEAR": ("lot_sizing", "native_legs_max_when_unclear", "int", 0.0, 30.0),
    "FORGE_NATIVE_LEGS_CLEAR_TREND_FACTOR": ("lot_sizing", "native_legs_clear_trend_factor", "float", 1.0, 3.0),
    "FORGE_NATIVE_FORCE_STAGED_SCALE_IN": ("lot_sizing", "native_force_staged_scale_in", "bool01", None, None),
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
    # OsMA(fast,slow,signal) histogram gate — MACD Histogram MC 4-quadrant approach
    "FORGE_BREAKOUT_REQUIRE_MACD_SELL": ("bb_breakout", "require_macd_sell", "bool01", None, None),
    "FORGE_BREAKOUT_REQUIRE_MACD_BUY":  ("bb_breakout", "require_macd_buy",  "bool01", None, None),
    "FORGE_BREAKOUT_MACD_FAST":         ("bb_breakout", "macd_fast",   "int", 1.0, 50.0),
    "FORGE_BREAKOUT_MACD_SLOW":         ("bb_breakout", "macd_slow",   "int", 1.0, 100.0),
    "FORGE_BREAKOUT_MACD_SIGNAL":       ("bb_breakout", "macd_signal", "int", 1.0, 50.0),
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
    "FORGE_MAX_OPEN_SAME_DIRECTION": ("safety", "max_open_same_direction", "int", 0.0, 10.0),
    "FORGE_BOUNCE_SL_ATR_MULT": ("bb_bounce", "sl_atr_mult", "float", 0.5, 5.0),
    "FORGE_BREAKOUT_SL_ATR_MULT": ("bb_breakout", "sl_atr_mult", "float", 0.5, 5.0),
    "FORGE_PSAR_ENABLED": ("indicators", "psar_enabled", "bool01", None, None),
    "FORGE_PSAR_STEP": ("indicators", "psar_step", "float", 0.001, 0.5),
    "FORGE_PSAR_MAXIMUM": ("indicators", "psar_maximum", "float", 0.01, 5.0),
    "FORGE_TESTER_SESSION_FILTER": ("session_filter", "tester_session_filter", "bool01", None, None),
    "FORGE_TESTER_ALLOWED_SESSIONS": ("session_filter", "tester_allowed_sessions", "string", None, None),
    "FORGE_TESTER_COOLDOWN_ENABLED": ("safety", "tester_cooldown_enabled", "bool01", None, None),
    "FORGE_DIRECTION_COOLDOWN_ENABLED": ("safety", "direction_cooldown_enabled", "bool01", None, None),
    "FORGE_DIRECTION_COOLDOWN_BARS": ("safety", "direction_cooldown_bars", "int", 0.0, 50.0),
    "FORGE_JOURNAL_ENABLED": ("journal", "journal_enabled", "bool01", None, None),
    "FORGE_JOURNAL_RECORD_SKIPS": ("journal", "journal_record_skips", "bool01", None, None),
    "FORGE_JOURNAL_IMPORT_TRADES": ("journal", "journal_import_trades", "bool01", None, None),
    "FORGE_JOURNAL_IMPORT_DEPTH_DAYS": ("journal", "journal_import_depth_days", "int", 1.0, 365.0),
    "FORGE_JOURNAL_STATS_INTERVAL_SEC": ("journal", "journal_stats_interval_sec", "int", 60.0, 3600.0),
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
