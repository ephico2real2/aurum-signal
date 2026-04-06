"""
aurum_forge.py — JSON contracts for AURUM → BRIDGE → FORGE
==========================================================
Runtime validators (Python) aligned with JSON Schema under `schemas/files/*.schema.json`.
See **docs/DATA_CONTRACT.md** for the full interchange design (file bus + HTTP API).

BRIDGE: reads `config/aurum_cmd.json`, writes `MT5/command.json`.
FORGE: **ea/FORGE.mq5** — ReadCommandFile / ExecuteOpenGroup / ExecuteCloseAll.
"""

from __future__ import annotations

import math
from typing import Any

# Keep in sync with bridge.VALID_MODES
VALID_MODES = frozenset({"OFF", "WATCH", "SIGNAL", "SCALPER", "HYBRID", "AUTO_SCALPER"})

FORGE_OPEN_GROUP_KEYS = frozenset({
    "action",
    "group_id",
    "direction",
    "entry_ladder",
    "lot_per_trade",
    "sl",
    "tp1",
    "tp1_close_pct",
    "move_be_on_tp1",
    "timestamp",
})
# FORGE also reads tp2, tp3 (optional); entry_low used only if entry_ladder empty


def _num(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def validate_aurum_cmd(cmd: dict) -> list[str]:
    """
    Validate a payload intended for config/aurum_cmd.json (before BRIDGE consumes it).
    Returns a list of human-readable errors (empty if OK).
    """
    errs: list[str] = []
    if not isinstance(cmd, dict):
        return ["command must be a JSON object"]
    action = (cmd.get("action") or "").upper()
    if not action:
        errs.append("missing action")
        return errs
    if cmd.get("timestamp") in (None, ""):
        errs.append("missing timestamp (BRIDGE dedupes on timestamp)")

    if action == "MODE_CHANGE":
        nm = cmd.get("new_mode")
        if nm not in VALID_MODES:
            errs.append(f"MODE_CHANGE.new_mode must be one of {sorted(VALID_MODES)}, got {nm!r}")
        return errs

    if action == "CLOSE_ALL":
        return errs

    if action in ("OPEN_GROUP", "OPEN_TRADE"):
        d = (cmd.get("direction") or "").upper()
        if d not in ("BUY", "SELL"):
            errs.append(f"direction must be BUY or SELL, got {cmd.get('direction')!r}")
        # OPEN_TRADE may fill entry via market — skip strict entry check for that
        if action == "OPEN_GROUP":
            for label, key in (
                ("entry_low", "entry_low"),
                ("sl", "sl"),
                ("tp1", "tp1"),
            ):
                v = _num(cmd.get(key))
                if v is None or v <= 0:
                    errs.append(f"OPEN_GROUP requires positive numeric {label}")
            el = _num(cmd.get("entry_low"))
            eh = _num(cmd.get("entry_high"))
            if el is not None and eh is not None and eh < el:
                errs.append("entry_high must be >= entry_low")
        return errs

    errs.append(f"unknown action {action!r} (expected MODE_CHANGE, CLOSE_ALL, OPEN_GROUP, OPEN_TRADE)")
    return errs


def validate_forge_command(cmd: dict) -> list[str]:
    """
    Validate a payload BRIDGE writes to MT5/command.json for FORGE.mq5.
    """
    errs: list[str] = []
    if not isinstance(cmd, dict):
        return ["command must be a JSON object"]
    action = (cmd.get("action") or "").upper()
    if not action:
        errs.append("missing action")
        return errs

    if action == "CLOSE_ALL":
        if not (cmd.get("timestamp") or "").strip():
            errs.append("CLOSE_ALL should include timestamp string")
        return errs

    if action == "OPEN_GROUP":
        missing = FORGE_OPEN_GROUP_KEYS - set(cmd.keys())
        if missing:
            errs.append(f"OPEN_GROUP missing keys: {sorted(missing)}")

        if _num(cmd.get("group_id")) is None or int(_num(cmd.get("group_id")) or 0) < 1:
            errs.append("OPEN_GROUP.group_id must be a positive integer")

        if (cmd.get("direction") or "").upper() not in ("BUY", "SELL"):
            errs.append("OPEN_GROUP.direction must be BUY or SELL")

        lp = _num(cmd.get("lot_per_trade"))
        if lp is None or lp <= 0:
            errs.append("OPEN_GROUP.lot_per_trade must be positive")

        for label in ("sl", "tp1"):
            v = _num(cmd.get(label))
            if v is None or v <= 0:
                errs.append(f"OPEN_GROUP.{label} must be positive")

        lad = cmd.get("entry_ladder")
        if isinstance(lad, list):
            if not lad:
                el = _num(cmd.get("entry_low"))
                if el is None or el <= 0:
                    errs.append("OPEN_GROUP needs non-empty entry_ladder or positive entry_low")
            else:
                for i, x in enumerate(lad):
                    if _num(x) is None or _num(x) <= 0:
                        errs.append(f"entry_ladder[{i}] must be a positive number")
        else:
            el = _num(cmd.get("entry_low"))
            if el is None or el <= 0:
                errs.append("OPEN_GROUP.entry_ladder must be a list or entry_low set")

        if not (cmd.get("timestamp") or "").strip():
            errs.append("OPEN_GROUP should include timestamp string")

        mbe = cmd.get("move_be_on_tp1")
        if mbe is not None and not isinstance(mbe, (bool, str, int, float)):
            errs.append("move_be_on_tp1 must be bool or string/number FORGE accepts")

        return errs

    errs.append(f"unknown FORGE action {action!r}")
    return errs


def normalize_aurum_open_trade(cmd: dict, market_data: dict | None) -> dict:
    """
    Map AURUM / LLM OPEN_TRADE shape → OPEN_GROUP fields BRIDGE + FORGE understand.
    `market_data` is the same shape as MT5/market_data.json (uses .price.bid/ask).
    """
    out = dict(cmd)
    out["action"] = "OPEN_GROUP"
    entry = out.get("entry")
    if entry == "market" or entry is None:
        pm = (market_data or {}).get("price") or {}
        bid, ask = pm.get("bid"), pm.get("ask")
        mid = None
        if bid is not None and ask is not None:
            mid = (float(bid) + float(ask)) / 2.0
        elif bid is not None:
            mid = float(bid)
        if mid is not None:
            out["entry_low"] = out.get("entry_low") or mid
            out["entry_high"] = out.get("entry_high") or mid
    else:
        try:
            e = float(entry)
            out["entry_low"] = out.get("entry_low", e)
            out["entry_high"] = out.get("entry_high", e)
        except (TypeError, ValueError):
            pass
    if out.get("tp1") is None and out.get("tp") is not None:
        out["tp1"] = out["tp"]
    if out.get("lots") is not None and out.get("lot_per_trade") is None:
        out["lot_per_trade"] = out["lots"]
    return out


def forge_open_group_from_bridge(
    *,
    group_id: int,
    direction: str,
    entry_ladder: list[float],
    lot_per_trade: float,
    sl: float,
    tp1: float,
    tp2: Any,
    tp3: Any,
    tp1_close_pct: float,
    move_be_on_tp1: bool,
    timestamp: str,
) -> dict:
    """Canonical OPEN_GROUP dict matching bridge._dispatch_aurum_open_group / signal paths."""
    return {
        "action": "OPEN_GROUP",
        "group_id": group_id,
        "direction": direction.upper(),
        "entry_ladder": entry_ladder,
        "lot_per_trade": lot_per_trade,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "tp1_close_pct": tp1_close_pct,
        "move_be_on_tp1": move_be_on_tp1,
        "timestamp": timestamp,
    }
