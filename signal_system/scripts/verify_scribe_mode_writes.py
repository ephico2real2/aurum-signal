#!/usr/bin/env python3
"""
verify_scribe_mode_writes.py
============================
Code-path audit: which BRIDGE modes lead to which SCRIBE (SQLite) writes.

Run from repo root:
  python3 scripts/verify_scribe_mode_writes.py
  SCRIBE_DB=/path/to/aurum_intelligence.db python3 scripts/verify_scribe_mode_writes.py

With a DB path, prints row counts grouped by `mode` for key tables (last 7 days).
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB = ROOT / "data" / "aurum_intelligence.db"

AUDIT = """
══════════════════════════════════════════════════════════════════════════════
SCRIBE SQLite — writes vs BRIDGE mode (effective_mode at time of write)
══════════════════════════════════════════════════════════════════════════════

Shared prefix (runs EVERY tick, including OFF and WATCH):
  • Circuit breaker: log_system_event only when leaving/returning from trading
    modes (not when already OFF/WATCH and MT5 stale).
  • Sentinel: in-memory override only (SCRIBE via sentinel.py on news events).
  • Reconciler (hourly): log_system_event RECONCILIATION, close_trade_position,
    component_heartbeats — runs in OFF too.
  • Session UTC change: close/open trading_sessions, SESSION_CHANGE in system_events
    — runs in OFF too.
  • AURUM command file: MODE_CHANGE, OPEN_GROUP, CLOSE_ALL paths → system_events,
    trade_groups, etc. — runs in OFF too (BRIDGE still reads aurum_cmd.json).
  • _write_status: component_heartbeats for BRIDGE + SCRIBE — every tick, all modes.
  • _heartbeat_passive_components: LENS heartbeat from lens_snapshot.json — OFF/WATCH.

OFF (early return after the prefix above):
  • Does NOT call LENS MCP fetch_fresh → no NEW market_snapshots rows from LENS
    for that tick (stale cache / file may still exist).
  • Does NOT run _process_signal, _scalper_logic, _process_mgmt_command → no
    trade_groups / bridge-driven signal execution from those paths.

WATCH:
  • LENS fetch on LENS_WATCH_REFRESH_SEC → market_snapshots + LENS heartbeat.
  • No signal / scalper / mgmt from bridge.

SIGNAL:
  • LENS on LENS_INTERVAL → market_snapshots.
  • Telegram-driven signal file + mgmt → trade_groups, signals updates, etc.

SCALPER:
  • LENS + autonomous scalper → trade_groups when AEGIS approves.

HYBRID:
  • SIGNAL branch + SCALPER branch + LENS.

Other processes (not gated by BRIDGE OFF):
  • LISTENER: log_signal + update_signal_action for every parsed signal, including
    OFF/WATCH (LOGGED_ONLY) — Telegram audit trail always persisted.
  • AURUM: log_aurum_conversation when chatting (uses AURUM’s current mode).
  • ATHENA: optional heartbeat rows when API receives POST /heartbeat.

CONCLUSION
  • “Trading loop” data (LENS snapshots from MCP, bridge signal/scalper) is not
    written in OFF.
  • Operational / audit data (heartbeats, reconciliation, sessions, Telegram signals,
    AURUM commands) can still write to SQLite while BRIDGE mode is OFF.

If you need strict “no SQLite while OFF”, that requires additional gating in
bridge.py, reconciler, listener, etc. (not implemented by this script).
══════════════════════════════════════════════════════════════════════════════
"""


def _db_path() -> Path:
    env = os.environ.get("SCRIBE_DB", "").strip()
    if env:
        return Path(env).expanduser()
    return _DEFAULT_DB


def _counts(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    tables = [
        ("market_snapshots", "mode", "timestamp"),
        ("signals_received", "mode", "timestamp"),
        ("trade_groups", "mode", "timestamp"),
        ("component_heartbeats", "mode", "timestamp"),
    ]
    print("\n── Row counts by mode (last 7 days, where table has mode + timestamp) ──\n")
    for table, mode_col, ts_col in tables:
        try:
            cur.execute(
                f"""
                SELECT {mode_col} AS m, COUNT(*) AS n
                FROM {table}
                WHERE datetime({ts_col}) >= datetime('now', '-7 days')
                GROUP BY {mode_col}
                ORDER BY n DESC
                """
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError as e:
            print(f"  {table}: (skip — {e})")
            continue
        if not rows:
            print(f"  {table}: no rows in window")
            continue
        print(f"  {table}:")
        for m, n in rows:
            print(f"    {m!r}: {n}")


def main() -> int:
    print(AUDIT)
    db = _db_path()
    if not db.is_file():
        print(f"DB not found: {db}\n(Set SCRIBE_DB or create data/aurum_intelligence.db)\n")
        return 0
    print(f"Using DB: {db}\n")
    conn = sqlite3.connect(str(db))
    try:
        _counts(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
