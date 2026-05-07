#!/usr/bin/env python3
"""
Summarize FORGE journal SQLite files and optional SCRIBE mirror (forge_signals / forge_journal_trades).
Uses the same search roots as BRIDGE on macOS Wine MT5.
"""
from __future__ import annotations

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

        # Per-run breakdown (only when run_id column exists)
        sig_cols = [r[1] for r in conn.execute("PRAGMA table_info(SIGNALS)").fetchall()]
        per_run: list = []
        if "run_id" in sig_cols:
            run_ids = _q(conn, "SELECT DISTINCT run_id FROM SIGNALS ORDER BY run_id")
            for (rid,) in run_ids:
                taken_r = _q(
                    conn,
                    f"SELECT COUNT(*) FROM SIGNALS WHERE outcome='TAKEN' AND run_id={rid}",
                )
                total_r = _q(
                    conn, f"SELECT COUNT(*) FROM SIGNALS WHERE run_id={rid}"
                )
                skips_r = _q(
                    conn,
                    f"SELECT gate_reason, COUNT(*) FROM SIGNALS "
                    f"WHERE outcome='SKIP' AND run_id={rid} GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
                )
                run_entry: dict = {
                    "run_id": rid,
                    "signals_total": total_r[0][0] if total_r else 0,
                    "signals_taken": taken_r[0][0] if taken_r else 0,
                    "top_skip_reasons": [[g, n] for g, n in skips_r],
                }
                if "run_id" in tr_cols:
                    tr_r = _q(
                        conn,
                        f"SELECT COUNT(*), ROUND(SUM(profit),2), "
                        f"SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END), "
                        f"SUM(CASE WHEN profit<0 THEN 1 ELSE 0 END) "
                        f"FROM TRADES WHERE direction IN (1,2,3) AND run_id={rid}",
                    )
                    if tr_r and tr_r[0][0]:
                        run_entry["trades_deals"] = tr_r[0][0]
                        run_entry["trades_pnl"] = tr_r[0][1]
                        run_entry["trades_wins"] = tr_r[0][2]
                        run_entry["trades_losses"] = tr_r[0][3]
                per_run.append(run_entry)

        return {
            "path": str(path),
            "SIGNALS_total": sig_n[0][0] if sig_n else 0,
            "SIGNALS_TAKEN": taken[0][0] if taken else 0,
            "SIGNALS_unsynced": unsync_sig[0][0] if unsync_sig else 0,
            "TRADES_total": tr_n[0][0] if tr_n else 0,
            "TRADES_unsynced": unsync_tr[0][0] if unsync_tr else None,
            "TESTER_RUNS": runs[0][0] if runs else 0,
            "top_SKIP_reasons": [[a, b, c] for a, b, c in sig],
            "per_run": per_run,
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
        # Per-run P&L in AURUM (tester source only)
        fjt_per_run = _q(
            conn,
            "SELECT run_id, COUNT(*), ROUND(SUM(profit),2), "
            "SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN profit<0 THEN 1 ELSE 0 END) "
            "FROM forge_journal_trades WHERE journal_source='tester' "
            "GROUP BY run_id ORDER BY run_id",
        )
        return {
            "scribe_db": str(dbpath),
            "forge_signals_total": fs_tot[0][0] if fs_tot else 0,
            "forge_signals_breakdown": fs,
            "forge_journal_trades_total": fjt_tot[0][0] if fjt_tot else 0,
            "forge_journal_trades_by_source": fjt,
            "forge_journal_trades_tester_per_run": [
                {"run_id": r, "deals": d, "pnl": p, "wins": w, "losses": l}
                for r, d, p, w, l in fjt_per_run
            ],
        }
    finally:
        conn.close()


W = 70  # table width


def _bar(n: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return ""
    filled = int(round(n / total * width))
    return "\u2588" * filled


def _fmt(n) -> str:
    if n is None:
        return "n/a"
    return f"{int(n):,}" if isinstance(n, int) or (isinstance(n, float) and n == int(n)) else f"{n:,.2f}"


def _print_run(run: dict, total_signals: int) -> None:
    rid = run["run_id"]
    sig_total = run["signals_total"]
    taken = run["signals_taken"]
    skipped = sig_total - taken
    label = f"run_id={rid}" if rid != 0 else "run_id=0 (live)"

    deals = run.get("trades_deals")
    pnl   = run.get("trades_pnl")
    wins  = run.get("trades_wins", 0)
    losses= run.get("trades_losses", 0)

    # Header row
    trade_str = ""
    if deals:
        pnl_sign = "+" if (pnl or 0) >= 0 else ""
        wr = round(wins / deals * 100) if deals else 0
        trade_str = f"  trades={_fmt(deals)}  P&L={pnl_sign}${pnl:,.2f}  W/L={wins}/{losses} ({wr}%)"
    print(f"  {'─'*66}")
    print(f"  {label:<20}  signals={_fmt(sig_total)}  taken={_fmt(taken)}  skipped={_fmt(skipped)}{trade_str}")
    print(f"  {'─'*66}")

    # Skip reasons table
    skips = run.get("top_skip_reasons", [])
    if not skips:
        print("    (no skip data)")
        return
    max_n   = max(s[1] for s in skips) if skips else 1
    col_w   = max(len(s[0]) for s in skips) if skips else 20
    for gate, cnt in skips:
        bar = _bar(cnt, max_n, 24)
        print(f"    {gate:<{col_w}}  {_fmt(cnt):>7}  {bar}")


def _print_journal(j: dict) -> None:
    name = Path(j["path"]).name
    is_tester = "_tester" in name
    tag = "[TESTER]" if is_tester else "[LIVE]"
    print()
    print("=" * W)
    print(f"  {tag}  {name}")
    print(f"  signals={_fmt(j['SIGNALS_total'])}  taken={_fmt(j['SIGNALS_TAKEN'])}  "
          f"unsynced={_fmt(j['SIGNALS_unsynced'])}  "
          f"trades={_fmt(j['TRADES_total'])}  runs={_fmt(j['TESTER_RUNS'])}")
    print("=" * W)

    per_run = j.get("per_run", [])
    if per_run:
        for run in per_run:
            _print_run(run, j["SIGNALS_total"])
    else:
        # Fallback: no run_id column (legacy)
        print("  (no run_id breakdown — old schema)")
        skips = [[b, c, ct] for b, c, ct in j["top_SKIP_reasons"]]
        if skips:
            max_n = max(s[2] for s in skips)
            col_w = max(len(str(s[1] or "")) for s in skips)
            for outcome, gate, cnt in skips:
                bar = _bar(cnt, max_n, 24)
                lbl = f"{outcome}/{gate}" if gate else outcome
                print(f"    {lbl:<{col_w+8}}  {_fmt(cnt):>7}  {bar}")
    print()


def _print_scribe(s: dict) -> None:
    print()
    print("=" * W)
    print(f"  SCRIBE AURUM  {Path(s['scribe_db']).name}")
    print(f"  forge_signals={_fmt(s['forge_signals_total'])}  "
          f"forge_journal_trades={_fmt(s['forge_journal_trades_total'])}")
    print("=" * W)

    # Trades by source
    by_src = s.get("forge_journal_trades_by_source", [])
    if by_src:
        print("  forge_journal_trades by source:")
        for src, cnt in by_src:
            print(f"    {src:<12}  {_fmt(cnt):>7}")

    # Tester per-run P&L
    per_run = s.get("forge_journal_trades_tester_per_run", [])
    if per_run:
        print()
        print("  forge_journal_trades (tester) per run:")
        print(f"    {'run_id':<8}  {'deals':>6}  {'P&L':>10}  {'W':>4}  {'L':>4}  {'WR%':>5}")
        print(f"    {'─'*8}  {'─'*6}  {'─'*10}  {'─'*4}  {'─'*4}  {'─'*5}")
        for r in per_run:
            wr = round(r['wins'] / r['deals'] * 100) if r['deals'] else 0
            pnl_sign = "+" if (r['pnl'] or 0) >= 0 else ""
            print(f"    {r['run_id']:<8}  {_fmt(r['deals']):>6}  "
                  f"{pnl_sign}${r['pnl']:>8,.2f}  {r['wins']:>4}  {r['losses']:>4}  {wr:>4}%")
    else:
        print()
        print("  (no tester runs synced to AURUM yet or all at run_id=0 from old schema)")

    # forge_signals breakdown
    fs = s.get("forge_signals_breakdown", [])
    if fs:
        print()
        print("  forge_signals breakdown (source / outcome / gate_reason):")
        max_n = max(r[3] for r in fs) if fs else 1
        col_w = max(len(f"{r[0]}/{r[1]}/{r[2]}") for r in fs)
        for src, outcome, gate, cnt in fs:
            lbl = f"{src}/{outcome}/{gate}" if gate else f"{src}/{outcome}"
            bar = _bar(cnt, max_n, 20)
            print(f"    {lbl:<{col_w}}  {_fmt(cnt):>7}  {bar}")
    print()


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
            "No FORGE journal files found. Is MetaTrader 5 installed "
            "and has it written a journal at least once?",
            file=sys.stderr,
        )

    for j in journals:
        _print_journal(_summarize_journal(j))

    sc = _scribe_summary(scribe)
    if sc:
        _print_scribe(sc)
    else:
        print(f"\n  SCRIBE DB not found: {scribe}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
