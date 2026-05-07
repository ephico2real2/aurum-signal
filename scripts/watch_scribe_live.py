#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TextIO


ROOT = Path(__file__).resolve().parents[1]
_SCRIBE_DEFAULT_REL = "python/data/aurum_intelligence.db"
DEFAULT_DB = ROOT / _SCRIBE_DEFAULT_REL


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _emit(msg: str, log_fp: TextIO | None = None) -> None:
    print(msg, flush=True)
    if log_fp is not None:
        log_fp.write(msg + "\n")
        log_fp.flush()


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live SCRIBE watcher for backtesting and live trading."
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to aurum_intelligence.db (default: SCRIBE_DB or repo python/data/aurum_intelligence.db).",
    )
    parser.add_argument(
        "--interval-sec",
        type=float,
        default=2.0,
        help="Polling interval in seconds (default: 2.0).",
    )
    parser.add_argument(
        "--show-events",
        action="store_true",
        help="Also print new rows from system_events.",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Optional path to append watcher output for later review.",
    )
    args = parser.parse_args()

    try:
        db_path = resolve_db_path(args.db)
    except Exception as exc:
        print(f"[watch-scribe] {exc}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    log_fp: TextIO | None = None
    if args.log_file:
        log_path = Path(args.log_file).expanduser()
        if not log_path.is_absolute():
            log_path = ROOT / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fp = log_path.open("a", encoding="utf-8")

    last_group_id = cur.execute("select ifnull(max(id),0) from trade_groups").fetchone()[0]
    last_close_id = cur.execute("select ifnull(max(id),0) from trade_closures").fetchone()[0]
    last_event_id = 0
    if args.show_events:
        last_event_id = cur.execute("select ifnull(max(id),0) from system_events").fetchone()[0]

    _emit(
        f"[{_now()}] watching db={db_path} "
        f"(group_id>{last_group_id}, closure_id>{last_close_id})",
        log_fp,
    )
    if log_fp is not None:
        _emit(f"[{_now()}] appending log file={log_fp.name}", log_fp)

    idle_ticks = 0
    try:
        while True:
            groups = cur.execute(
                """
                select id,timestamp,source,direction,status,close_reason,total_pnl,
                       num_trades,lot_per_trade,trades_opened,trades_closed,magic_number
                from trade_groups
                where id > ?
                order by id asc
                """,
                (last_group_id,),
            ).fetchall()
            closes = cur.execute(
                """
                select id,timestamp,trade_group_id,direction,close_reason,pnl,pips,
                       duration_seconds,mode
                from trade_closures
                where id > ?
                order by id asc
                """,
                (last_close_id,),
            ).fetchall()

            events: list[sqlite3.Row] = []
            if args.show_events:
                events = cur.execute(
                    """
                    select id,timestamp,event_type,new_mode,reason,notes
                    from system_events
                    where id > ?
                    order by id asc
                    """,
                    (last_event_id,),
                ).fetchall()

            if groups or closes or events:
                idle_ticks = 0
            else:
                idle_ticks += 1
                if idle_ticks % 10 == 0:
                    _emit(f"[{_now()}] waiting for new rows...", log_fp)

            for row in groups:
                _emit(
                    "[GROUP] "
                    f"id={row['id']} ts={row['timestamp']} src={row['source']} "
                    f"dir={row['direction']} status={row['status']} "
                    f"pnl={row['total_pnl']} n={row['num_trades']} lot={row['lot_per_trade']} "
                    f"opened={row['trades_opened']} closed={row['trades_closed']} "
                    f"magic={row['magic_number']} reason={row['close_reason']}",
                    log_fp,
                )
                last_group_id = row["id"]

            for row in closes:
                _emit(
                    "[CLOSE] "
                    f"id={row['id']} ts={row['timestamp']} gid={row['trade_group_id']} "
                    f"dir={row['direction']} reason={row['close_reason']} "
                    f"pnl={row['pnl']} pips={row['pips']} dur_s={row['duration_seconds']} "
                    f"mode={row['mode']}",
                    log_fp,
                )
                last_close_id = row["id"]

            for row in events:
                _emit(
                    "[EVENT] "
                    f"id={row['id']} ts={row['timestamp']} type={row['event_type']} "
                    f"mode={row['new_mode']} reason={row['reason']} notes={row['notes']}",
                    log_fp,
                )
                last_event_id = row["id"]

            time.sleep(max(0.25, args.interval_sec))
    except KeyboardInterrupt:
        _emit(f"\n[{_now()}] stopped", log_fp)
        return 0
    finally:
        if log_fp is not None:
            log_fp.close()


if __name__ == "__main__":
    raise SystemExit(main())
