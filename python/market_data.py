"""
market_data.py — Parse MT5 market_data.json (FORGE)
====================================================
Shared by athena_api and aurum so execution quotes match everywhere.
"""

from __future__ import annotations

import os
import time
from typing import Any

from freshness import DATA_FRESHNESS_WINDOWS

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, ".."))

MT5_STALE_SEC = int(os.environ.get("BRIDGE_MT5_STALE", str(DATA_FRESHNESS_WINDOWS["MT5"])))


def safe_float(x):
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def enrich_mt5_for_stale_check(mt5: dict[str, Any], market_file: str) -> dict[str, Any]:
    """
    Strategy Tester writes timestamp_unix from simulated TimeGMT(), not wall clock — BRIDGE would
    see huge age and trip the circuit breaker. When FORGE sets strategy_tester, use file mtime age.
    """
    if not isinstance(mt5, dict) or not mt5.get("strategy_tester"):
        return mt5
    try:
        mtime = os.path.getmtime(market_file)
        age = max(0.0, time.time() - mtime)
        out = dict(mt5)
        out["_age_from_mtime"] = age
        return out
    except OSError:
        return mt5


def mt5_tick_age_sec(mt5: dict) -> float | None:
    """Seconds since FORGE update (wall-clock). Uses _age_from_mtime when set (Strategy Tester)."""
    if not isinstance(mt5, dict):
        return None
    if mt5.get("_age_from_mtime") is not None:
        t0 = safe_float(mt5.get("_age_from_mtime"))
        if t0 is not None:
            return max(0.0, t0)
    ts = mt5.get("timestamp_unix")
    if ts is None:
        return None
    t0 = safe_float(ts)
    if t0 is None:
        return None
    return max(0.0, time.time() - t0)


def fmt_age_short(sec: float | None) -> str:
    if sec is None:
        return "unknown"
    if sec < 90:
        return f"{sec:.0f}s"
    if sec < 3600:
        return f"{sec / 60:.1f}m"
    if sec < 86400:
        return f"{sec / 3600:.1f}h"
    return f"{sec / 86400:.1f}d"


def build_execution_quote(mt5: dict) -> dict:
    """Authoritative MT5 bid/ask only when file is fresh."""
    out: dict = {
        "symbol": mt5.get("symbol") if isinstance(mt5, dict) else None,
        "bid": None,
        "ask": None,
        "mid": None,
        "spread_usd": None,
        "spread_points": None,
        "timestamp_utc": mt5.get("timestamp_utc") if isinstance(mt5, dict) else None,
        "timestamp_unix": mt5.get("timestamp_unix"),
        "age_sec": None,
        "stale": True,
        "usable": False,
        "stale_reason": None,
    }
    if not isinstance(mt5, dict):
        out["stale_reason"] = "no market_data.json"
        return out
    age = mt5_tick_age_sec(mt5)
    out["age_sec"] = round(age, 1) if age is not None else None
    out["stale"] = age is None or age > MT5_STALE_SEC
    if out["stale"]:
        if isinstance(mt5, dict) and mt5.get("strategy_tester"):
            out["stale_reason"] = (
                f"Strategy Tester: market_data age from file mtime {fmt_age_short(age)} "
                f"(limit {MT5_STALE_SEC}s)"
                if age is not None
                else "strategy_tester set but could not compute file age"
            )
        else:
            out["stale_reason"] = (
                f"FORGE data is {fmt_age_short(age)} old (limit {MT5_STALE_SEC}s) — not a live quote"
                if age is not None
                else "missing or invalid timestamp_unix in market_data.json"
            )
    pm = mt5.get("price") or {}
    bid, ask = safe_float(pm.get("bid")), safe_float(pm.get("ask"))
    out["bid"], out["ask"] = bid, ask
    sp = pm.get("spread_points")
    if sp is not None:
        try:
            out["spread_points"] = float(sp)
        except (TypeError, ValueError):
            out["spread_points"] = sp
    if bid is not None and ask is not None:
        out["mid"] = (bid + ask) / 2.0
        out["spread_usd"] = round(ask - bid, 4)
    elif bid is not None:
        out["mid"] = bid
    out["usable"] = bool(not out["stale"] and bid is not None and ask is not None)
    return out
