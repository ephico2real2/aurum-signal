#!/usr/bin/env python3
"""
Summarize FORGE journal SQLite files and optional SCRIBE mirror (forge_signals / forge_journal_trades).
Uses the same search roots as BRIDGE on macOS Wine MT5.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path


def _journal_paths() -> list[Path]:
    import platform

    home = Path.home()
    roots: list[Path] = []
    if platform.system() == "Darwin":
        mt5_base = (
            home
            / "Library"
            / "Application Support"
            / "net.metaquotes.wine.metatrader5"
            / "drive_c"
        )
        roots = [
            mt5_base
            / "users"
            / "user"
            / "AppData"
            / "Roaming"
            / "MetaQuotes"
            / "Terminal"
            / "Common"
            / "Files",
            mt5_base / "Program Files" / "MetaTrader 5" / "MQL5" / "Files",
            mt5_base / "Program Files" / "MetaTrader 5",
        ]
    else:
        roots = [
            home / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files",
        ]
    found: list[Path] = []
    for root in roots:
        if root.exists():
            for p in root.rglob("FORGE_journal_*.db"):
                if p.is_file() and p.stat().st_size > 0 and p not in found:
                    found.append(p)
    return sorted(found)


def _q(conn: sqlite3.Connection, sql: str):
    try:
        return conn.execute(sql).fetchall()
    except sqlite3.Error:
        return []


def _summarize_journal(path: Path) -> dict:
    conn = sqlite3.connect(str(path))
    try:
        sig = _q(
            conn,
            "SELECT outcome, gate_reason, COUNT(*) FROM SIGNALS GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 25",
        )
        taken = _q(conn, "SELECT COUNT(*) FROM SIGNALS WHERE outcome='TAKEN'")
        sig_n = _q(conn, "SELECT COUNT(*) FROM SIGNALS")
        tr_n = _q(conn, "SELECT COUNT(*) FROM TRADES")
        runs = _q(conn, "SELECT COUNT(*) FROM TESTER_RUNS")
        unsync_sig = _q(conn, "SELECT COUNT(*) FROM SIGNALS WHERE synced = 0")
        tr_cols = [r[1] for r in conn.execute("PRAGMA table_info(TRADES)").fetchall()]
        if "synced" in tr_cols:
            unsync_tr = _q(conn, "SELECT COUNT(*) FROM TRADES WHERE synced = 0")
        else:
            unsync_tr = []
        return {
            "path": str(path),
            "SIGNALS_total": sig_n[0][0] if sig_n else 0,
            "SIGNALS_TAKEN": taken[0][0] if taken else 0,
            "SIGNALS_unsynced": unsync_sig[0][0] if unsync_sig else 0,
            "TRADES_total": tr_n[0][0] if tr_n else 0,
            "TRADES_unsynced": unsync_tr[0][0] if unsync_tr else None,
            "TESTER_RUNS": runs[0][0] if runs else 0,
            "top_SKIP_reasons": [[a, b, c] for a, b, c in sig],
        }
    finally:
        conn.close()


def _scribe_summary(dbpath: Path) -> dict | None:
    if not dbpath.is_file():
        return None
    conn = sqlite3.connect(str(dbpath))
    try:
        fs = _q(
            conn,
            "SELECT journal_source, outcome, COALESCE(gate_reason,''), COUNT(*) "
            "FROM forge_signals GROUP BY 1,2,3 ORDER BY 4 DESC LIMIT 20",
        )
        fs_tot = _q(conn, "SELECT COUNT(*) FROM forge_signals")
        fjt = _q(conn, "SELECT journal_source, COUNT(*) FROM forge_journal_trades GROUP BY 1")
        fjt_tot = _q(conn, "SELECT COUNT(*) FROM forge_journal_trades")
        return {
            "scribe_db": str(dbpath),
            "forge_signals_total": fs_tot[0][0] if fs_tot else 0,
            "forge_signals_breakdown": fs,
            "forge_journal_trades_total": fjt_tot[0][0] if fjt_tot else 0,
            "forge_journal_trades_by_source": fjt,
        }
    finally:
        conn.close()


def main() -> int:
    raw = os.environ.get("SCRIBE_DB", "python/data/aurum_intelligence.db")
    if raw == "data/aurum_intelligence.db":
        raw = "python/data/aurum_intelligence.db"
    scribe = Path(raw)
    if not scribe.is_absolute():
        scribe = Path(__file__).resolve().parents[1] / scribe

    journals = _journal_paths()
    if not journals:
        print(
            "No FORGE journal files found in search paths. Is MetaTrader 5 installed "
            "and has it written a journal at least once?",
            file=sys.stderr,
        )
    out = {
        "journals_found": len(journals),
        "journals": [_summarize_journal(p) for p in journals],
        "scribe": _scribe_summary(scribe),
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
