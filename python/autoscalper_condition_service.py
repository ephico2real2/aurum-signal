"""
autoscalper_condition_service.py
================================
Structured diagnostics for AUTO_SCALPER trigger readiness.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _indicator_nonzero(value) -> bool:
    f = _safe_float(value)
    return f is not None and abs(f) > 1e-9


def _tf_has_indicator_data(tf: dict) -> bool:
    keys = (
        "rsi_14",
        "ema_20",
        "ema_50",
        "bb_lower",
        "bb_mid",
        "bb_upper",
        "adx",
        "macd_hist",
        "atr_14",
    )
    return any(_indicator_nonzero((tf or {}).get(k)) for k in keys)


def _first_nonzero(*values):
    for val in values:
        if _indicator_nonzero(val):
            return _safe_float(val)
    return None


def _infer_h1_bias(ind_h1: dict, flat_threshold: float = 1.0) -> str:
    ema20 = _first_nonzero((ind_h1 or {}).get("ema_20"), (ind_h1 or {}).get("ma_20"))
    ema50 = _first_nonzero((ind_h1 or {}).get("ema_50"), (ind_h1 or {}).get("ma_50"))
    if ema20 is None or ema50 is None:
        return "UNKNOWN"
    diff = ema20 - ema50
    if diff > flat_threshold:
        return "BULL"
    if diff < -flat_threshold:
        return "BEAR"
    return "FLAT"


def _parse_iso(ts: str):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _classify_autoscalper_response(resp: str) -> str:
    text = (resp or "").upper()
    if "OPEN_GROUP" in text:
        return "OPEN_GROUP"
    if text.strip().startswith("PASS"):
        return "PASS"
    return "OTHER"


def build_autoscalper_condition_report(
    *,
    status_path: str,
    sentinel_path: str,
    market_path: str,
    db_path: str,
    responses_limit: int = 3,
    h1_flat_threshold: float = 1.0,
    mt5_stale_sec: int | None = None,
    loss_cooldown_sec: int | None = None,
    max_groups: int | None = None,
    neutral_rsi_min: float = 45.0,
    neutral_rsi_max: float = 55.0,
    upper_bb_threshold_pct: float = 90.0,
) -> dict:
    mt5_stale_sec = int(mt5_stale_sec or int(os.environ.get("BRIDGE_MT5_STALE", "120")))
    loss_cooldown_sec = int(loss_cooldown_sec or int(os.environ.get("DD_LOSS_COOLDOWN_SEC", "300")))
    max_groups = int(max_groups or int(os.environ.get("AUTO_SCALPER_MAX_GROUPS", "2")))
    responses_limit = max(1, min(int(responses_limit), 20))

    status = _read_json(status_path)
    sentinel = _read_json(sentinel_path)
    mt5 = _read_json(market_path)

    now = time.time()
    ts_unix = _safe_float(mt5.get("timestamp_unix")) if mt5 else None
    mt5_age_sec = (now - ts_unix) if ts_unix is not None else None
    mt5_available = bool(mt5)
    mt5_fresh = bool(mt5_available and mt5_age_sec is not None and mt5_age_sec < mt5_stale_sec)

    sentinel_block = bool(status.get("sentinel_active")) or bool(sentinel.get("block_trading"))

    open_groups = 0
    last_loss_close_time = None
    recent_reasoning = []
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM trade_groups WHERE status IN ('OPEN','PARTIAL')")
        open_groups = int(cur.fetchone()[0] or 0)

        cur.execute(
            "SELECT close_time, pnl FROM trade_positions "
            "WHERE status='CLOSED' AND pnl < 0 ORDER BY close_time DESC LIMIT 1"
        )
        row = cur.fetchone()
        last_loss_close_time = row[0] if row else None

        cur.execute(
            "SELECT id, timestamp, response "
            "FROM aurum_conversations WHERE source='AUTO_SCALPER' "
            "ORDER BY id DESC LIMIT ?",
            (responses_limit,),
        )
        rows = cur.fetchall()
        for r in rows:
            resp = r[2] or ""
            recent_reasoning.append(
                {
                    "id": int(r[0]),
                    "timestamp": r[1],
                    "decision": _classify_autoscalper_response(resp),
                    "response_preview": str(resp)[:240],
                }
            )
    finally:
        conn.close()

    cooldown_active = None
    cooldown_remaining_sec = None
    if last_loss_close_time:
        dt = _parse_iso(last_loss_close_time)
        if dt is not None:
            elapsed = now - dt.timestamp()
            cooldown_active = elapsed < loss_cooldown_sec
            cooldown_remaining_sec = max(0, int(loss_cooldown_sec - elapsed))

    h1 = (mt5.get("indicators_h1") or {}) if mt5 else {}
    m15 = (mt5.get("indicators_m15") or {}) if mt5 else {}
    m5 = (mt5.get("indicators_m5") or {}) if mt5 else {}
    price = (mt5.get("price") or {}) if mt5 else {}

    bid = _safe_float(price.get("bid"))
    ask = _safe_float(price.get("ask"))
    mid = (bid + ask) / 2.0 if bid is not None and ask is not None and bid > 0 and ask > 0 else None

    h1_bias = _infer_h1_bias(h1, flat_threshold=h1_flat_threshold)
    h1_bias_ok = h1_bias not in ("FLAT", "UNKNOWN")

    rsi_m5 = _safe_float(m5.get("rsi_14"))
    rsi_m15 = _safe_float(m15.get("rsi_14"))
    valid_rsis = [r for r in (rsi_m5, rsi_m15) if r is not None and r > 0]
    lower_tf_rsis_available = bool(valid_rsis)
    lower_tf_all_neutral = (
        all(neutral_rsi_min <= r <= neutral_rsi_max for r in valid_rsis)
        if lower_tf_rsis_available
        else None
    )
    lower_tf_not_all_neutral = (
        (not lower_tf_all_neutral) if lower_tf_all_neutral is not None else None
    )

    bb_lower = _safe_float(m15.get("bb_lower"))
    bb_upper = _safe_float(m15.get("bb_upper"))
    bb_pos_pct = None
    near_upper_bb = None
    near_lower_bb = None
    if (
        mid is not None
        and bb_lower is not None
        and bb_upper is not None
        and bb_upper > bb_lower
    ):
        bb_pos_pct = (mid - bb_lower) / (bb_upper - bb_lower) * 100.0
        near_upper_bb = bb_pos_pct >= upper_bb_threshold_pct
        near_lower_bb = bb_pos_pct <= (100.0 - upper_bb_threshold_pct)

    indicators_available = {
        "h1": _tf_has_indicator_data(h1),
        "m15": _tf_has_indicator_data(m15),
        "m5": _tf_has_indicator_data(m5),
    }
    indicator_data_quality = "ok" if all(indicators_available.values()) else "missing_or_zero"

    open_groups_below_max = open_groups < max_groups

    prefilter_pass = all(
        [
            not sentinel_block,
            cooldown_active is False or cooldown_active is None,
            open_groups_below_max,
            mt5_available,
            mt5_fresh,
            h1_bias_ok,
            lower_tf_not_all_neutral is True,
        ]
    )

    g47_g48_sell_pattern_match = all(
        [
            prefilter_pass,
            h1_bias == "BEAR",
            near_upper_bb is True,
        ]
    )

    failed_checks = []
    if sentinel_block:
        failed_checks.append("sentinel_block")
    if cooldown_active is True:
        failed_checks.append("loss_cooldown_active")
    if not open_groups_below_max:
        failed_checks.append("open_groups_limit")
    if not mt5_available:
        failed_checks.append("mt5_missing")
    if not mt5_fresh:
        failed_checks.append("mt5_stale")
    if not h1_bias_ok:
        failed_checks.append("h1_bias_not_tradeable")
    if lower_tf_not_all_neutral is not True:
        failed_checks.append("lower_tf_rsis_neutral_or_missing")
    if near_upper_bb is not True:
        failed_checks.append("m15_not_near_upper_bb")

    summary = (
        "AUTO_SCALPER trigger conditions are aligned with the G47/G48-style SELL pattern."
        if g47_g48_sell_pattern_match
        else "AUTO_SCALPER trigger conditions are not fully aligned with the G47/G48-style SELL pattern."
    )

    return {
        "timestamp": _now_iso(),
        "config": {
            "mt5_stale_sec": mt5_stale_sec,
            "loss_cooldown_sec": loss_cooldown_sec,
            "max_groups": max_groups,
            "h1_flat_threshold": h1_flat_threshold,
            "neutral_rsi_min": neutral_rsi_min,
            "neutral_rsi_max": neutral_rsi_max,
            "upper_bb_threshold_pct": upper_bb_threshold_pct,
            "responses_limit": responses_limit,
        },
        "data_sources": {
            "status_path": status_path,
            "sentinel_path": sentinel_path,
            "market_path": market_path,
            "db_path": db_path,
        },
        "bridge_prefilters": {
            "sentinel_block": sentinel_block,
            "loss_cooldown_active": cooldown_active,
            "loss_cooldown_remaining_sec": cooldown_remaining_sec,
            "open_groups": open_groups,
            "max_groups": max_groups,
            "open_groups_below_max": open_groups_below_max,
            "mt5_available": mt5_available,
            "mt5_fresh": mt5_fresh,
            "mt5_age_sec": None if mt5_age_sec is None else round(mt5_age_sec, 1),
            "h1_bias": h1_bias,
            "h1_bias_ok": h1_bias_ok,
            "rsi_m5": rsi_m5,
            "rsi_m15": rsi_m15,
            "lower_tf_rsis_available": lower_tf_rsis_available,
            "lower_tf_all_neutral": lower_tf_all_neutral,
            "lower_tf_not_all_neutral": lower_tf_not_all_neutral,
            "prefilter_pass": prefilter_pass,
        },
        "setup_snapshot": {
            "mid": mid,
            "m15_bb_upper_proximity_pct": None if bb_pos_pct is None else round(bb_pos_pct, 1),
            "near_upper_bb": near_upper_bb,
            "near_lower_bb": near_lower_bb,
            "indicator_data_quality": indicator_data_quality,
            "indicators_available": indicators_available,
        },
        "latest_autoscalper_responses": recent_reasoning,
        "overall": {
            "g47_g48_sell_pattern_match": g47_g48_sell_pattern_match,
            "summary": summary,
            "failed_checks": failed_checks,
        },
    }


if __name__ == "__main__":
    _HERE = Path(__file__).resolve().parent
    _ROOT = _HERE.parent
    status_file = str(_HERE / os.environ.get("BRIDGE_STATUS_FILE", "config/status.json"))
    sentinel_file = str(_HERE / os.environ.get("SENTINEL_STATUS_FILE", "config/sentinel_status.json"))
    market_file = str(_ROOT / os.environ.get("MT5_MARKET_FILE", "MT5/market_data.json"))
    db_file = str(_HERE / "data" / "aurum_intelligence.db")
    report = build_autoscalper_condition_report(
        status_path=status_file,
        sentinel_path=sentinel_file,
        market_path=market_file,
        db_path=db_file,
    )
    print(json.dumps(report, indent=2, default=str))
