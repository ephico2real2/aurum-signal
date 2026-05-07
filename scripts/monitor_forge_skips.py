#!/usr/bin/env python3
"""Monitor SCRIBE forge_signals for SKIP rows (and optional TAKEN counts)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCRIBE_DEFAULT_REL = "python/data/aurum_intelligence.db"
DEFAULT_DB = ROOT / _SCRIBE_DEFAULT_REL


def resolve_db_path(explicit_path: str | None) -> Path:
    if explicit_path:
        p = Path(explicit_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"DB file not found: {p}")
        return p

    raw = os.environ.get("SCRIBE_DB", "").strip()
    if raw == "data/aurum_intelligence.db":
        raw = _SCRIBE_DEFAULT_REL
    if raw:
        p = Path(raw).expanduser()
        p = p.resolve() if p.is_absolute() else (ROOT / p).resolve()
        if not p.exists():
            raise FileNotFoundError(f"SCRIBE_DB path not found: {p}")
        return p

    if not DEFAULT_DB.exists():
        raise FileNotFoundError(
            f"No SCRIBE DB at {DEFAULT_DB} (set SCRIBE_DB or pass --db)"
        )
    return DEFAULT_DB


def _connect_ro(path: Path) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def report_snapshot(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    hours: int,
    tail: int,
    top: int,
    json_out: bool,
) -> dict:
    now = int(datetime.now(timezone.utc).timestamp())
    since = now - max(1, hours) * 3600

    cur = conn.cursor()
    cur.execute(
        """
        SELECT journal_source, COALESCE(gate_reason, ''), COUNT(*) AS n
        FROM forge_signals
        WHERE outcome = 'SKIP' AND time >= ?
        GROUP BY journal_source, gate_reason
        ORDER BY n DESC
        """,
        (since,),
    )
    skip_window = [{"journal_source": a, "gate_reason": b, "n": c} for a, b, c in cur.fetchall()]

    cur.execute(
        """
        SELECT journal_source, COALESCE(gate_reason, ''), COUNT(*) AS n
        FROM forge_signals
        WHERE outcome = 'SKIP'
        GROUP BY journal_source, gate_reason
        ORDER BY n DESC
        LIMIT ?
        """,
        (top,),
    )
    skip_alltime_top = [{"journal_source": a, "gate_reason": b, "n": c} for a, b, c in cur.fetchall()]

    cur.execute(
        """
        SELECT journal_source, outcome, COUNT(*) FROM forge_signals
        WHERE time >= ? GROUP BY journal_source, outcome
        """,
        (since,),
    )
    outcome_window = [{"journal_source": a, "outcome": b, "n": c} for a, b, c in cur.fetchall()]

    cur.execute(
        """
        SELECT datetime(time, 'unixepoch') AS ts_utc, journal_source, gate_reason,
               COALESCE(setup_type, ''), COALESCE(direction, ''),
               adx, rsi
        FROM forge_signals
        WHERE outcome = 'SKIP'
        ORDER BY time DESC
        LIMIT ?
        """,
        (tail,),
    )
    tail_rows = [
        {
            "ts_utc": r[0],
            "journal_source": r[1],
            "gate_reason": r[2],
            "setup_type": r[3],
            "direction": r[4],
            "adx": r[5],
            "rsi": r[6],
        }
        for r in cur.fetchall()
    ]

    payload = {
        "db_path": str(db_path),
        "since_unix": since,
        "hours": hours,
        "outcome_window": outcome_window,
        "skip_by_reason_window": skip_window,
        "skip_alltime_top": skip_alltime_top,
        "tail_skip_rows": tail_rows,
    }
    if json_out:
        print(json.dumps(payload, indent=2))
    else:
        print(f"[monitor-forge-skips] since={hours}h (unix>={since})")
        print("--- outcome mix (window) ---")
        for row in outcome_window:
            print(f"  {row['journal_source']:8} {row['outcome']:8} {row['n']}")
        print("--- SKIP by reason (window) ---")
        if not skip_window:
            print("  (none)")
        for row in skip_window:
            print(f"  {row['journal_source']:8} {row['gate_reason'] or '(empty)':24} {row['n']}")
        print(f"--- SKIP all-time top {top} (source + reason) ---")
        for row in skip_alltime_top:
            print(f"  {row['journal_source']:8} {row['gate_reason'] or '(empty)':24} {row['n']}")
        print(f"--- last {tail} SKIP rows ---")
        for r in tail_rows:
            adx = f"{r['adx']:.1f}" if r["adx"] is not None else ""
            rsi = f"{r['rsi']:.1f}" if r["rsi"] is not None else ""
            print(
                f"  {r['ts_utc']} | {r['journal_source']} | {r['gate_reason'] or '-':18} | "
                f"{r['setup_type'] or '-':12} | {r['direction'] or '-':4} | adx={adx} rsi={rsi}"
            )
    return payload


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=None, help="Path to aurum_intelligence.db (else SCRIBE_DB or default).")
    p.add_argument("--hours", type=int, default=24, help="Rolling window for rollup (default 24).")
    p.add_argument("--tail", type=int, default=20, help="How many recent SKIP rows to print (default 20).")
    p.add_argument("--top", type=int, default=12, help="All-time top N skip reason groups (default 12).")
    p.add_argument("--watch", action="store_true", help="Re-run every --interval-sec until Ctrl-C.")
    p.add_argument("--interval-sec", type=float, default=60.0, help="Poll interval with --watch (default 60).")
    p.add_argument("--json", action="store_true", help="Emit one JSON object per snapshot.")
    args = p.parse_args()

    try:
        db_path = resolve_db_path(args.db)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2

    tick = 0
    try:
        while True:
            tick += 1
            if args.watch and not args.json:
                print(f"\n=== snapshot #{tick} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
            conn = _connect_ro(db_path)
            try:
                report_snapshot(
                    conn,
                    db_path=db_path,
                    hours=args.hours,
                    tail=args.tail,
                    top=args.top,
                    json_out=args.json,
                )
            finally:
                conn.close()
            if not args.watch:
                break
            time.sleep(max(5.0, args.interval_sec))
    except KeyboardInterrupt:
        if not args.json:
            print("\n[monitor-forge-skips] stopped")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
