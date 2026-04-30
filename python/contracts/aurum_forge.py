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
    "lot_per_trade",
    "sl",
    "tp1",
    "tp1_close_pct",
    "move_be_on_tp1",
    "timestamp",
})
# FORGE also reads tp2, tp3 (optional); entry_low used only if entry_ladder empty
FORGE_ORDER_TYPES = frozenset({
    "AUTO",
    "BUY_LIMIT",
    "SELL_LIMIT",
    "BUY_STOP",
    "SELL_STOP",
    "BUY_STOP_LIMIT",
    "SELL_STOP_LIMIT",
})


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


def _normalize_order_type(v: Any) -> str:
    s = str(v or "").strip().upper()
    if not s:
        return "AUTO"
    if s == "BUY_STOPLIMIT":
        return "BUY_STOP_LIMIT"
    if s == "SELL_STOPLIMIT":
        return "SELL_STOP_LIMIT"
    return s


def normalize_entry_legs(raw_legs: Any) -> list[dict]:
    """
    Canonicalize entry_legs items and drop invalid legs.
    """
    out: list[dict] = []
    if not isinstance(raw_legs, list):
        return out
    for leg in raw_legs:
        if not isinstance(leg, dict):
            continue
        ep = _num(leg.get("entry_price"))
        if ep is None or ep <= 0:
            continue
        row: dict[str, Any] = {
            "order_type": _normalize_order_type(leg.get("order_type")),
            "entry_price": float(ep),
        }
        slp = _num(leg.get("stoplimit_price"))
        if slp is not None and slp > 0:
            row["stoplimit_price"] = float(slp)
        tp = _num(leg.get("tp"))
        if tp is not None and tp > 0:
            row["tp"] = float(tp)
        out.append(row)
    return out


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

    if action == "SCRIBE_QUERY":
        sql = cmd.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            errs.append("SCRIBE_QUERY.sql must be a non-empty string")
        return errs

    if action == "SHELL_EXEC":
        program = cmd.get("program")
        args = cmd.get("args")
        legacy_cmd = cmd.get("cmd")
        if program is None and legacy_cmd is None:
            errs.append("SHELL_EXEC requires either program+args or cmd")
            return errs
        if program is not None and not isinstance(program, str):
            errs.append("SHELL_EXEC.program must be a string")
        if args is not None and not isinstance(args, list):
            errs.append("SHELL_EXEC.args must be a list")
        if legacy_cmd is not None and not isinstance(legacy_cmd, str):
            errs.append("SHELL_EXEC.cmd must be a string")
        return errs

    if action == "AURUM_EXEC":
        payload = cmd.get("payload")
        endpoint = cmd.get("endpoint")
        if not isinstance(payload, dict):
            errs.append("AURUM_EXEC.payload must be an object")
            return errs
        nested_action = (payload.get("action") or "").upper()
        if nested_action not in {"SCRIBE_QUERY", "SHELL_EXEC", "HEALTH_CHECK"}:
            errs.append("AURUM_EXEC.payload.action must be SCRIBE_QUERY, SHELL_EXEC, or HEALTH_CHECK")
        if endpoint is not None and not isinstance(endpoint, str):
            errs.append("AURUM_EXEC.endpoint must be a string when provided")
        return errs

    if action == "ANALYSIS_RUN":
        kind = cmd.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            errs.append("ANALYSIS_RUN.kind must be a non-empty string")
        params = cmd.get("params")
        if params is not None and not isinstance(params, dict):
            errs.append("ANALYSIS_RUN.params must be an object when provided")
        notify = cmd.get("notify")
        if notify is not None and not isinstance(notify, dict):
            errs.append("ANALYSIS_RUN.notify must be an object when provided")
        qid = cmd.get("query_id")
        if qid is not None and not isinstance(qid, str):
            errs.append("ANALYSIS_RUN.query_id must be a string when provided")
        return errs

    if action in ("OPEN_GROUP", "OPEN_TRADE"):
        d = (cmd.get("direction") or "").upper()
        if d not in ("BUY", "SELL"):
            errs.append(f"direction must be BUY or SELL, got {cmd.get('direction')!r}")
        # OPEN_TRADE may fill entry via market — skip strict entry check for that
        if action == "OPEN_GROUP":
            for label, key in (("sl", "sl"), ("tp1", "tp1")):
                v = _num(cmd.get(key))
                if v is None or v <= 0:
                    errs.append(f"OPEN_GROUP requires positive numeric {label}")
            legs = normalize_entry_legs(cmd.get("entry_legs"))
            if legs:
                for i, leg in enumerate(legs):
                    ot = _normalize_order_type(leg.get("order_type"))
                    if ot not in FORGE_ORDER_TYPES:
                        errs.append(f"OPEN_GROUP entry_legs[{i}].order_type invalid: {ot!r}")
                    if ot in ("BUY_STOP_LIMIT", "SELL_STOP_LIMIT") and _num(leg.get("stoplimit_price")) is None:
                        errs.append(f"OPEN_GROUP entry_legs[{i}].stoplimit_price required for {ot}")
            else:
                el = _num(cmd.get("entry_low"))
                eh = _num(cmd.get("entry_high"))
                if el is None or el <= 0:
                    errs.append("OPEN_GROUP requires positive numeric entry_low (or valid entry_legs)")
                if el is not None and eh is not None and eh < el:
                    errs.append("entry_high must be >= entry_low")
        return errs

    errs.append(
        f"unknown action {action!r} (expected MODE_CHANGE, CLOSE_ALL, OPEN_GROUP, OPEN_TRADE, "
        "SCRIBE_QUERY, SHELL_EXEC, AURUM_EXEC, ANALYSIS_RUN)"
    )
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

    if action == "CANCEL_GROUP_PENDING":
        mg = _num(cmd.get("magic"))
        if mg is None or int(mg) < 1:
            errs.append("CANCEL_GROUP_PENDING.magic must be a positive integer")
        if not (cmd.get("timestamp") or "").strip():
            errs.append("CANCEL_GROUP_PENDING should include timestamp string")
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
        legs = cmd.get("entry_legs")
        has_ladder = isinstance(lad, list) and len(lad) > 0
        has_legs = isinstance(legs, list) and len(legs) > 0
        if not has_ladder and not has_legs:
            el = _num(cmd.get("entry_low"))
            if el is None or el <= 0:
                errs.append("OPEN_GROUP requires non-empty entry_ladder or entry_legs (or positive entry_low fallback)")
        if has_ladder:
            for i, x in enumerate(lad):
                if _num(x) is None or _num(x) <= 0:
                    errs.append(f"entry_ladder[{i}] must be a positive number")
        if has_legs:
            for i, leg in enumerate(legs):
                if not isinstance(leg, dict):
                    errs.append(f"entry_legs[{i}] must be an object")
                    continue
                ot = _normalize_order_type(leg.get("order_type"))
                if ot not in FORGE_ORDER_TYPES:
                    errs.append(f"entry_legs[{i}].order_type invalid: {ot!r}")
                ep = _num(leg.get("entry_price"))
                if ep is None or ep <= 0:
                    errs.append(f"entry_legs[{i}].entry_price must be a positive number")
                if ot in ("BUY_STOP_LIMIT", "SELL_STOP_LIMIT"):
                    slp = _num(leg.get("stoplimit_price"))
                    if slp is None or slp <= 0:
                        errs.append(f"entry_legs[{i}].stoplimit_price required for {ot}")
                tpp = _num(leg.get("tp"))
                if tpp is not None and tpp <= 0:
                    errs.append(f"entry_legs[{i}].tp must be positive when provided")

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
    if isinstance(out.get("entry_legs"), list):
        out["entry_legs"] = normalize_entry_legs(out.get("entry_legs"))
        if out["entry_legs"] and (out.get("entry_low") is None or out.get("entry_high") is None):
            prices = [float(x["entry_price"]) for x in out["entry_legs"]]
            out["entry_low"] = out.get("entry_low", min(prices))
            out["entry_high"] = out.get("entry_high", max(prices))
        if out["entry_legs"] and out.get("num_trades") is None and out.get("trades") is None:
            out["num_trades"] = len(out["entry_legs"])
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
    entry_legs: list[dict] | None = None,
) -> dict:
    """Canonical OPEN_GROUP dict matching bridge._dispatch_aurum_open_group / signal paths."""
    out = {
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
    if entry_legs:
        out["entry_legs"] = normalize_entry_legs(entry_legs)
    return out
