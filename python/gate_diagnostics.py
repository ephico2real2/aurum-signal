"""
gate_diagnostics.py
===================
Unified environment + regime snapshot for the LISTENER→SIGNAL path in BRIDGE.

Aligned with `autoscalper_condition_service` (MT5 freshness, sentinel, H1 bias)
but omits AUTO_SCALPER–specific G47/G48 pattern checks. Read-only / advisory;
does not change execution decisions unless the caller (BRIDGE) enables writes.

Defaults: all wiring in BRIDGE is behind GATE_DIAGNOSTICS_ENABLED=0.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_nonzero(*values: Any) -> float | None:
    for val in values:
        f = _safe_float(val)
        if f is not None and abs(f) > 1e-9:
            return f
    return None


def _infer_h1_bias(ind_h1: dict, flat_threshold: float = 1.0) -> str:
    """Same ATR-free EMA spread rule as autoscalper_condition_service."""
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_signal_gate_diagnostics(
    *,
    status: dict | None,
    sentinel: dict | None,
    mt5: dict | None,
    regime_context: dict | None,
    bridge_mode: str | None,
    trading_session_label: str | None,
    mt5_stale_sec: int | None = None,
    h1_flat_threshold: float = 1.0,
    signal_id: str | None = None,
    direction: str | None = None,
    reject_gate: str | None = None,
    reject_reason: str | None = None,
) -> dict:
    """
    Build a structured snapshot for observability (ATHENA / optional Herald).

    When reject_gate / reject_reason are set, the snapshot records the veto that
    just occurred; environment_* fields describe the world state at that moment.
    """
    mt5_stale_sec = int(mt5_stale_sec or int(os.environ.get("BRIDGE_MT5_STALE", "120")))
    status = status or {}
    sentinel = sentinel or {}

    now = time.time()
    ts_unix = _safe_float(mt5.get("timestamp_unix")) if mt5 else None
    mt5_age_sec = (now - ts_unix) if ts_unix is not None else None
    mt5_available = bool(mt5)
    mt5_fresh = bool(mt5_available and mt5_age_sec is not None and mt5_age_sec < mt5_stale_sec)

    sentinel_block = bool(status.get("sentinel_active")) or bool(sentinel.get("block_trading"))

    h1 = (mt5.get("indicators_h1") or {}) if mt5 else {}
    h1_bias = _infer_h1_bias(h1, flat_threshold=h1_flat_threshold)

    rc = regime_context or {}
    regime_public = {
        "label": rc.get("label"),
        "confidence": rc.get("confidence"),
        "entry_mode": rc.get("entry_mode"),
        "apply_entry_policy": rc.get("apply_entry_policy"),
        "entry_gate_reason": rc.get("entry_gate_reason"),
        "stale": rc.get("stale"),
        "age_sec": rc.get("age_sec"),
        "model_name": rc.get("model_name"),
    }

    environment_ok = bool(
        not sentinel_block and mt5_available and mt5_fresh
    )
    failed_environment: list[str] = []
    if sentinel_block:
        failed_environment.append("sentinel_block")
    if not mt5_available:
        failed_environment.append("mt5_missing")
    elif not mt5_fresh:
        failed_environment.append("mt5_stale")

    out: dict[str, Any] = {
        "schema": "signal_gate_diagnostics/v1",
        "timestamp": _now_iso(),
        "signal": {
            "signal_id": signal_id,
            "direction": direction,
        },
        "bridge": {
            "mode": bridge_mode,
        },
        "trading_session": {
            "label": trading_session_label,
        },
        "regime": regime_public,
        "environment": {
            "sentinel_block": sentinel_block,
            "status_sentinel_active": bool(status.get("sentinel_active")),
            "sentinel_file_block_trading": bool(sentinel.get("block_trading")),
            "mt5_available": mt5_available,
            "mt5_fresh": mt5_fresh,
            "mt5_age_sec": None if mt5_age_sec is None else round(mt5_age_sec, 1),
            "mt5_stale_sec": mt5_stale_sec,
            "environment_ok": environment_ok,
            "failed_checks": failed_environment,
        },
        "indicators_quick": {
            "h1_bias": h1_bias,
            "h1_bias_tradeable": h1_bias not in ("FLAT", "UNKNOWN"),
        },
        "reject": {
            "gate": reject_gate,
            "reason": reject_reason,
        },
        "note": (
            "For AUTO_SCALPER G47/G48-style readiness, use GET /api/autoscalper/conditions."
        ),
    }
    return out


def format_gate_diagnostics_herald_line(diag: dict | None, max_len: int = 350) -> str | None:
    """One-line HTML-safe-ish summary for Telegram (caller may wrap in <code>)."""
    if not diag or not isinstance(diag, dict):
        return None
    env = diag.get("environment") or {}
    fc = env.get("failed_checks") or []
    reg = diag.get("regime") or {}
    rej = diag.get("reject") or {}
    parts: list[str] = []
    if fc:
        parts.append("env:" + ",".join(str(x) for x in fc))
    else:
        parts.append("env:ok")
    egr = reg.get("entry_gate_reason")
    if egr:
        parts.append(f"reg:{egr}")
    gate = rej.get("gate")
    reason = rej.get("reason")
    if gate:
        r = (reason or "")[:200]
        parts.append(f"reject:{gate}:{r}")
    line = " | ".join(parts)
    if len(line) > max_len:
        return line[: max_len - 3] + "..."
    return line
