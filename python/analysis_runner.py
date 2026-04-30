"""
analysis_runner.py — Deferred Analysis Run subsystem
====================================================
Reusable, fire-and-forget async analysis pipeline triggered by the AEB
``ANALYSIS_RUN`` action.

Flow:
    aurum -> aurum_cmd.json -> bridge -> aeb_executor.ANALYSIS_RUN
        -> analysis_runner.submit()  (returns immediately, status=PENDING)
        -> background worker thread runs the registered handler
        -> writes logs/analysis/<query_id>.{json,md}
        -> appends ANALYSIS_QUEUED / ANALYSIS_DONE / ANALYSIS_FAILED to
           logs/audit/system_events.jsonl
        -> herald.post_analysis_from_log() reposts the body to the
           existing Telegram channel (Herald singleton — never a new bot)

The module is intentionally stdlib-only and side-effect-light at import
time so it can be imported by AEB / Aurum / Bridge without bringing up
a Telegram client.

Public API:
    register_analysis(kind)        # decorator
    submit(payload)                # PENDING ack, dispatches worker
    list_pending() -> list[dict]
    list_recent(limit=20) -> list[dict]
    get_status(query_id) -> dict | None
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("analysis_runner")

# ── Paths / env ─────────────────────────────────────────────────────
_PY = Path(__file__).resolve().parent
_ROOT = _PY.parent

_DEFAULT_LOG_DIR = _ROOT / "logs" / "analysis"
_AUDIT_JSONL = _ROOT / "logs" / "audit" / "system_events.jsonl"


def _log_dir() -> Path:
    raw = (os.environ.get("ANALYSIS_LOG_DIR") or "").strip()
    return Path(raw).expanduser().resolve() if raw else _DEFAULT_LOG_DIR


def _max_concurrency() -> int:
    try:
        v = int(os.environ.get("ANALYSIS_MAX_CONCURRENCY", "4"))
    except (TypeError, ValueError):
        v = 4
    return max(1, min(v, 32))


# Ensure the log directory exists at import time (idempotent).
try:
    _log_dir().mkdir(parents=True, exist_ok=True)
except Exception as _e:  # pragma: no cover — extremely defensive
    log.warning("analysis_runner: log dir create failed: %s", _e)


# ── Registry ────────────────────────────────────────────────────────
HandlerFn = Callable[[dict], dict]
_HANDLERS: dict[str, HandlerFn] = {}


def register_analysis(kind: str) -> Callable[[HandlerFn], HandlerFn]:
    """Decorator that registers ``handler(params) -> dict`` for a kind."""

    key = (kind or "").strip().lower()
    if not key:
        raise ValueError("register_analysis: kind must be non-empty")

    def _wrap(fn: HandlerFn) -> HandlerFn:
        _HANDLERS[key] = fn
        return fn

    return _wrap


# ── Audit writer (mirrors scribe._mirror_system_event_audit shape) ──
def _append_audit(event_type: str, notes: dict | str | None = None) -> None:
    try:
        _AUDIT_JSONL.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "id": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "session": None,
            "notes": notes,
        }
        with open(_AUDIT_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        log.warning("analysis_runner: audit append failed: %s", e)


# ── State (in-process) ──────────────────────────────────────────────
_state_lock = threading.Lock()
_pending: dict[str, dict] = {}   # query_id -> {kind, started_at, params}
_executor = ThreadPoolExecutor(
    max_workers=_max_concurrency(),
    thread_name_prefix="analysis-",
)


# ── Helpers ─────────────────────────────────────────────────────────
_SAFE_ID = re.compile(r"[^A-Za-z0-9_\-]")


def _new_query_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"AR-{ts}-{uuid.uuid4().hex[:6]}"


def _sanitize_query_id(qid: str) -> str:
    qid = (qid or "").strip()
    if not qid:
        return _new_query_id()
    qid = _SAFE_ID.sub("-", qid)
    return qid[:80]


def _status_path(qid: str) -> Path:
    return _log_dir() / f"{qid}.json"


def _body_path(qid: str) -> Path:
    return _log_dir() / f"{qid}.md"


def _read_status(qid: str) -> dict | None:
    p = _status_path(qid)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.debug("analysis_runner: read_status %s failed: %s", qid, e)
        return None


def _write_status(qid: str, payload: dict) -> None:
    p = _status_path(qid)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str, ensure_ascii=False)
    except Exception as e:
        log.warning("analysis_runner: write_status %s failed: %s", qid, e)


def _write_body(qid: str, title: str, body_md: str) -> None:
    p = _body_path(qid)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        text = f"# {title}\n\n{body_md.rstrip()}\n"
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as e:
        log.warning("analysis_runner: write_body %s failed: %s", qid, e)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result_envelope(*, ok: bool, summary: str, query_id: str | None = None,
                     status: str | None = None, log_path: str | None = None,
                     error: str | None = None) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "action": "ANALYSIS_RUN",
        "summary": summary,
        "error": error,
        "security_blocked": False,
        "query_id": query_id,
        "status": status,
        "log_path": log_path,
        "rows": [],
        "count": 0,
        "truncated": False,
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "duration_ms": 0,
    }


# ── Public API ──────────────────────────────────────────────────────
def submit(payload: dict) -> dict:
    """Validate + enqueue an ANALYSIS_RUN payload. Returns immediately."""
    if not isinstance(payload, dict):
        return _result_envelope(ok=False, summary="ANALYSIS_RUN invalid payload",
                                error="payload must be an object")

    kind = str(payload.get("kind") or "").strip().lower()
    if not kind:
        return _result_envelope(ok=False, summary="ANALYSIS_RUN missing kind",
                                error="kind is required")
    if kind not in _HANDLERS:
        return _result_envelope(ok=False, summary=f"ANALYSIS_RUN unknown kind={kind}",
                                error=f"no handler registered for kind={kind}")

    qid_raw = str(payload.get("query_id") or "").strip()
    qid = _sanitize_query_id(qid_raw) if qid_raw else _new_query_id()

    params = payload.get("params") or {}
    if not isinstance(params, dict):
        return _result_envelope(ok=False, summary="ANALYSIS_RUN invalid params",
                                error="params must be an object")

    notify = payload.get("notify") or {}
    if not isinstance(notify, dict):
        notify = {}

    # Idempotency: client-supplied id that's already pending
    with _state_lock:
        if qid_raw and qid in _pending:
            return _result_envelope(
                ok=False,
                summary="ANALYSIS_RUN duplicate query_id",
                error=f"query_id {qid} is already PENDING",
                query_id=qid,
                status="PENDING",
                log_path=str(_body_path(qid).relative_to(_ROOT)),
            )
        # Soft queue cap: don't accept if pending count is huge.
        cap = _max_concurrency() * 2
        if len(_pending) >= cap:
            return _result_envelope(
                ok=False,
                summary="ANALYSIS_RUN queue full",
                error=f"too many pending runs ({len(_pending)} >= {cap})",
            )

        started_at = _now_iso()
        _pending[qid] = {
            "query_id": qid,
            "kind": kind,
            "params": dict(params),
            "started_at": started_at,
        }

    status_payload = {
        "query_id": qid,
        "kind": kind,
        "status": "PENDING",
        "params": params,
        "notify": notify,
        "reason": payload.get("reason"),
        "started_at": started_at,
        "finished_at": None,
        "summary": None,
        "has_result": False,
    }
    _write_status(qid, status_payload)
    _append_audit("ANALYSIS_QUEUED", {
        "query_id": qid, "kind": kind, "started_at": started_at,
        "params": params,
    })

    # Hand off to the executor — handler runs in a daemon thread.
    try:
        _executor.submit(_run_worker, qid, kind, dict(params), notify, payload.get("reason"))
    except RuntimeError as e:
        # Executor was shut down (e.g., interpreter teardown) — degrade gracefully.
        with _state_lock:
            _pending.pop(qid, None)
        log.warning("analysis_runner: executor unavailable: %s", e)
        return _result_envelope(ok=False, summary="ANALYSIS_RUN executor unavailable",
                                error=str(e), query_id=qid)

    return _result_envelope(
        ok=True,
        summary=f"ANALYSIS_RUN queued kind={kind}",
        query_id=qid,
        status="PENDING",
        log_path=f"logs/analysis/{qid}.md",
    )


def list_pending() -> list[dict]:
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    with _state_lock:
        snap = list(_pending.values())
    for row in snap:
        try:
            started = datetime.fromisoformat(str(row.get("started_at")).replace("Z", "+00:00"))
            age = max(0, int((now - started).total_seconds()))
        except Exception:
            age = -1
        out.append({
            "query_id": row.get("query_id"),
            "kind": row.get("kind"),
            "started_at": row.get("started_at"),
            "age_sec": age,
        })
    return out


def list_recent(limit: int = 20) -> list[dict]:
    try:
        limit_i = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        limit_i = 20
    rows: list[dict] = []
    try:
        for p in _log_dir().glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                if data.get("status") in ("DONE", "FAILED"):
                    rows.append(data)
            except Exception:
                continue
    except Exception as e:
        log.debug("analysis_runner: list_recent failed: %s", e)
        return []
    rows.sort(key=lambda r: str(r.get("finished_at") or r.get("started_at") or ""), reverse=True)
    return rows[:limit_i]


def get_status(query_id: str) -> dict | None:
    qid = _sanitize_query_id(query_id)
    with _state_lock:
        if qid in _pending:
            return dict(_pending[qid], status="PENDING")
    return _read_status(qid)


# ── Worker ──────────────────────────────────────────────────────────
def _run_worker(qid: str, kind: str, params: dict, notify: dict, reason: str | None) -> None:
    handler = _HANDLERS.get(kind)
    started_at = _now_iso()
    status: dict = {
        "query_id": qid,
        "kind": kind,
        "status": "PENDING",
        "params": params,
        "notify": notify,
        "reason": reason,
        "started_at": started_at,
        "finished_at": None,
        "summary": None,
        "has_result": False,
    }

    title = f"{kind} {qid}"
    body_md = ""
    summary = ""

    try:
        if handler is None:
            raise RuntimeError(f"no handler registered for kind={kind}")
        result = handler(params) or {}
        title = str(result.get("title") or title)
        body_md = str(result.get("body_md") or "")
        summary = str(result.get("summary") or "").strip() or "(no summary)"
        metadata = result.get("metadata") or {}

        _write_body(qid, title, body_md)
        status.update({
            "status": "DONE",
            "finished_at": _now_iso(),
            "summary": summary,
            "has_result": True,
            "title": title,
            "metadata": metadata,
        })
        _write_status(qid, status)
        _append_audit("ANALYSIS_DONE", {
            "query_id": qid, "kind": kind, "summary": summary,
            "finished_at": status["finished_at"],
        })
    except Exception as e:
        tb = traceback.format_exc()
        body_md = (
            f"**Status:** FAILED\n\n"
            f"**Error:** `{e}`\n\n"
            f"```\n{tb}\n```\n"
        )
        summary = f"FAILED: {e}"[:200]
        title = f"{kind} {qid} (FAILED)"
        _write_body(qid, title, body_md)
        status.update({
            "status": "FAILED",
            "finished_at": _now_iso(),
            "summary": summary,
            "has_result": False,
            "error": str(e),
            "title": title,
        })
        _write_status(qid, status)
        _append_audit("ANALYSIS_FAILED", {
            "query_id": qid, "kind": kind, "error": str(e),
            "finished_at": status["finished_at"],
        })
    finally:
        with _state_lock:
            _pending.pop(qid, None)

    # Telegram notify (uses existing Herald singleton — no new bot)
    if bool(notify.get("telegram", True)):
        try:
            from herald import post_analysis_from_log  # lazy import
            post_analysis_from_log(
                qid,
                header=notify.get("header"),
                footer=notify.get("footer"),
                chat_id=notify.get("chat_id"),
            )
        except Exception as e:
            log.warning("analysis_runner: herald notify failed for %s: %s", qid, e)


# ════════════════════════════════════════════════════════════════════
# Built-in handler: trade_group_review
# ════════════════════════════════════════════════════════════════════
_BRIDGE_LOG = _ROOT / "logs" / "bridge.log"
_DEFAULT_DB = _PY / "data" / "aurum_intelligence.db"


def _ro_sqlite(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _scrape_bridge_log_for_group(group_id: int, max_lines: int = 200) -> list[str]:
    if not _BRIDGE_LOG.exists():
        return []
    needle = re.compile(rf"\bG{int(group_id)}\b")
    keep_re = re.compile(r"\b(SIGNAL\|OPEN_GROUP|TRACKER\|FILL|TRACKER\|CLOSE|MGMT\|CLOSE|TRACKER:)\b")
    out: list[str] = []
    try:
        with open(_BRIDGE_LOG, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not needle.search(line):
                    continue
                if keep_re.search(line) is None:
                    continue
                out.append(line.rstrip())
                if len(out) >= max_lines:
                    break
    except Exception as e:
        log.debug("analysis_runner: bridge log scrape failed: %s", e)
    return out


def _safe_select(conn: sqlite3.Connection, sql: str, params: tuple,
                 schema_misses: list[str]) -> list[sqlite3.Row]:
    try:
        cur = conn.execute(sql, params)
        return cur.fetchall()
    except sqlite3.OperationalError as e:
        msg = str(e)
        m = re.search(r"no such column: (\S+)", msg)
        if m:
            schema_misses.append(m.group(1))
        else:
            schema_misses.append(msg)
        return []


@register_analysis("trade_group_review")
def _handler_trade_group_review(params: dict) -> dict:
    try:
        group_id = int(params.get("group_id"))
    except (TypeError, ValueError):
        raise ValueError("trade_group_review requires integer params.group_id")

    db_path_raw = params.get("db_path") or os.environ.get("SCRIBE_DB") or str(_DEFAULT_DB)
    db_path = Path(db_path_raw)
    schema_misses: list[str] = []
    group_row: sqlite3.Row | None = None
    signal_text = ""
    signal_meta: dict = {}
    aegis_line = ""
    fills: list[sqlite3.Row] = []
    closures: list[sqlite3.Row] = []

    if db_path.exists():
        try:
            with _ro_sqlite(db_path) as conn:
                rows = _safe_select(
                    conn,
                    "SELECT * FROM trade_groups WHERE id = ? LIMIT 1",
                    (group_id,),
                    schema_misses,
                )
                if rows:
                    group_row = rows[0]
                sig_rows = _safe_select(
                    conn,
                    """SELECT raw_text, channel_name, signal_type, direction,
                              entry_low, entry_high, sl, tp1, tp2, tp3,
                              skip_reason, action_taken, regime_label,
                              regime_confidence
                       FROM signals_received
                       WHERE id = (SELECT signal_id FROM trade_groups WHERE id = ?)
                       LIMIT 1""",
                    (group_id,),
                    schema_misses,
                )
                signal_meta = dict(sig_rows[0]) if sig_rows else {}
                if signal_meta:
                    signal_text = (signal_meta.get("raw_text") or "")[:1000]
                fills = _safe_select(
                    conn,
                    """SELECT ticket, direction, lot_size, entry_price, sl, tp,
                              status, close_reason, close_price, close_time,
                              pnl, pips, tp_stage
                       FROM trade_positions
                       WHERE trade_group_id = ?
                       ORDER BY ticket ASC""",
                    (group_id,),
                    schema_misses,
                )
                closures = _safe_select(
                    conn,
                    """SELECT ticket, direction, lot_size, entry_price,
                              close_price, close_reason, pnl, pips,
                              duration_seconds
                       FROM trade_closures
                       WHERE trade_group_id = ?
                       ORDER BY ticket ASC""",
                    (group_id,),
                    schema_misses,
                )
        except Exception as e:
            schema_misses.append(f"db_error: {e}")
    else:
        schema_misses.append(f"db_missing: {db_path}")

    bridge_lines = _scrape_bridge_log_for_group(group_id)

    # Compose body
    parts: list[str] = []
    parts.append(f"**Group ID:** G{group_id}")
    if group_row is not None:
        parts.append("")
        parts.append("## Group meta")
        for key in ("direction", "source", "num_trades", "lot_per_trade",
                    "entry_low", "entry_high", "sl", "tp1", "tp2", "tp3",
                    "status", "close_reason", "total_pnl", "pips_captured",
                    "trades_opened", "trades_closed", "regime_label",
                    "regime_confidence", "regime_policy"):
            try:
                v = group_row[key]
            except (IndexError, KeyError):
                continue
            if v is None:
                continue
            parts.append(f"- **{key}**: {v}")

        # Configuration section — entry-zone / placement metadata captured at OPEN.
        cfg_lines: list[str] = []
        for key in ("entry_zone_pips", "trades_filled", "entry_type", "entry_cluster"):
            try:
                v = group_row[key]
            except (IndexError, KeyError):
                continue
            if v is None:
                continue
            cfg_lines.append(f"- **{key}**: {v}")
        if cfg_lines:
            parts.append("")
            parts.append("## Configuration")
            parts.extend(cfg_lines)

    if signal_meta:
        parts.append("")
        parts.append("## Signal meta")
        for key in ("channel_name", "signal_type", "direction", "entry_low",
                    "entry_high", "sl", "tp1", "tp2", "tp3", "action_taken",
                    "skip_reason", "regime_label", "regime_confidence"):
            v = signal_meta.get(key)
            if v is None or v == "":
                continue
            parts.append(f"- **{key}**: {v}")

    if signal_text:
        parts.append("")
        parts.append("## Signal text")
        parts.append("```")
        parts.append(signal_text.strip())
        parts.append("```")

    # AEGIS line — scan a sliding window of the bridge log immediately
    # preceding the first OPEN_GROUP G<id> line. AEGIS logs the approval/reject
    # ~10–20 lines before the OPEN_GROUP marker for the same signal.
    aegis_pat = re.compile(r"AEGIS\s+(APPROVED|REJECT|REJECTED|REJECT_REASON|allowed)", re.IGNORECASE)
    open_marker = re.compile(rf"\[SIGNAL\|OPEN_GROUP\]\s+G{int(group_id)}\b")
    if _BRIDGE_LOG.exists():
        try:
            with open(_BRIDGE_LOG, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            # find first OPEN_GROUP for this group
            anchor = -1
            for i, line in enumerate(all_lines):
                if open_marker.search(line):
                    anchor = i
                    break
            if anchor >= 0:
                window = all_lines[max(0, anchor - 80):anchor + 1]
                for line in reversed(window):
                    if aegis_pat.search(line):
                        aegis_line = line.rstrip()
                        break
        except Exception as e:
            log.debug("analysis_runner: AEGIS scope scan failed: %s", e)
    if aegis_line:
        parts.append("")
        parts.append("## AEGIS decision")
        parts.append(f"`{aegis_line}`")

    # Fills + closes
    parts.append("")
    parts.append("## Positions (from SCRIBE `trade_positions`)")
    if fills:
        for r in fills:
            try:
                parts.append(
                    f"- #{r['ticket']} {r['direction']} {r['lot_size']}lot "
                    f"entry@{r['entry_price']} SL={r['sl']} TP={r['tp']} "
                    f"status={r['status']} close_reason={r['close_reason']} "
                    f"close@{r['close_price']} pnl={r['pnl']} pips={r['pips']} "
                    f"tp_stage={r['tp_stage']}"
                )
            except Exception:
                continue
    else:
        parts.append("_no rows from `trade_positions` for this group_")

    if closures:
        parts.append("")
        parts.append("## Closures (from SCRIBE `trade_closures`)")
        for r in closures:
            try:
                parts.append(
                    f"- #{r['ticket']} {r['direction']} {r['lot_size']}lot "
                    f"entry@{r['entry_price']} close@{r['close_price']} "
                    f"reason={r['close_reason']} pnl={r['pnl']} pips={r['pips']} "
                    f"dur={r['duration_seconds']}s"
                )
            except Exception:
                continue

    parts.append("")
    parts.append("## Bridge log events")
    if bridge_lines:
        parts.append("```")
        for line in bridge_lines[:50]:
            parts.append(line)
        parts.append("```")
    else:
        parts.append("_no matching lines in `logs/bridge.log`_")

    # Fill ratio + realised PnL — prefer trade_positions, fall back to closures.
    realised_pnl = 0.0
    filled = 0
    closed = 0
    total = 0
    intended_n = None
    canonical_filled = None  # from trades_filled column when present
    if group_row is not None:
        try:
            intended_n = int(group_row["num_trades"]) if group_row["num_trades"] is not None else None
        except Exception:
            intended_n = None
        try:
            tf = group_row["trades_filled"]
            canonical_filled = int(tf) if tf is not None else None
        except (IndexError, KeyError):
            canonical_filled = None
    if fills:
        for r in fills:
            total += 1
            try:
                if r["status"] in ("OPEN", "CLOSED", "FILLED"):
                    filled += 1
                if r["status"] == "CLOSED":
                    closed += 1
                if r["pnl"] is not None:
                    realised_pnl += float(r["pnl"] or 0)
            except Exception:
                continue
    if closures and realised_pnl == 0.0:
        for r in closures:
            try:
                if r["pnl"] is not None:
                    realised_pnl += float(r["pnl"] or 0)
            except Exception:
                continue
    # Also infer from bridge log when DB rows are missing
    if total == 0 and bridge_lines:
        for line in bridge_lines:
            if "TRACKER|FILL" in line:
                filled += 1
                total += 1
            elif "TRACKER|CLOSE" in line and "pnl=" in line:
                closed += 1
                m = re.search(r"pnl=\$([+-]?\d+(?:\.\d+)?)", line)
                if m:
                    try:
                        realised_pnl += float(m.group(1))
                    except ValueError:
                        pass

    # Prefer trades_filled column when populated; fall back to legacy counts.
    effective_filled = canonical_filled if canonical_filled is not None else filled
    denom = intended_n if intended_n else total
    fill_ratio = (effective_filled / denom) if denom else 0.0
    parts.append("")
    parts.append("## Summary")
    if intended_n is not None and intended_n != effective_filled:
        parts.append(
            f"- Filled: {effective_filled}/{intended_n} intended  (positions row count {total}, ratio {fill_ratio:.0%})"
        )
    else:
        parts.append(f"- Filled: {effective_filled}/{denom}  (ratio {fill_ratio:.0%})")
    parts.append(f"- Closed: {closed}")
    parts.append(f"- Realised PnL: ${realised_pnl:+.2f}")

    # "Why partial fill" advisory line for closed groups with unfilled legs.
    try:
        group_status = group_row["status"] if group_row is not None else None
    except (IndexError, KeyError):
        group_status = None
    if (intended_n is not None and effective_filled < intended_n
            and (group_status or "").upper() in ("CLOSED", "CLOSED_ALL")):
        parts.append(
            "\n_Layered limit ladder: only the leading leg(s) filled; price did not retrace into upper ladder slots before the group closed (CHANNEL_CLOSE/TP1_HIT). This is normal limit-order behaviour on directional moves._"
        )

    if schema_misses:
        parts.append("")
        parts.append("## Schema notes")
        for m in schema_misses:
            parts.append(f"- schema_missing: {m}")

    body_md = "\n".join(parts)
    summary = f"G{group_id} fills={filled}/{total} pnl=${realised_pnl:+.2f}"
    return {
        "title": f"Trade Group G{group_id} review",
        "body_md": body_md,
        "summary": summary,
        "metadata": {
            "group_id": group_id,
            "fill_ratio": fill_ratio,
            "pnl": realised_pnl,
            "schema_misses": schema_misses,
        },
    }


# Keep an explicit __all__ for clarity.
__all__ = [
    "register_analysis",
    "submit",
    "list_pending",
    "list_recent",
    "get_status",
]
