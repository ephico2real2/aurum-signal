#!/usr/bin/env python3
"""
write_forge_test_open_group.py — Build BRIDGE-shaped OPEN_GROUP for FORGE
===========================================================================
Writes the same JSON shape as bridge.py → MT5/command.json so you can test
execution without going through SCRIBE/AEGIS.

Usage (repo root):
  python3 scripts/write_forge_test_open_group.py          # print JSON only (dry-run)
  python3 scripts/write_forge_test_open_group.py --write

Requires fresh market_data.json (FORGE running). Each --write uses a new UTC
timestamp so FORGE does not skip as "already processed".

Monitor MT5: Toolbox → Trade (positions / pendings), Experts tab for
  FORGE command: OPEN_GROUP
  FORGE: Opened trade … / Failed trade … error=

See scripts/forge_open_group.example.json for a hand-edited template.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PY = _ROOT / "python"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    for name in (".env", ".env.local"):
        p = _ROOT / name
        if p.is_file():
            load_dotenv(p)


def _under_root(rel: str) -> Path:
    if os.path.isabs(rel):
        return Path(rel)
    return _ROOT / rel


def _cmd_path() -> Path:
    return _under_root(os.environ.get("MT5_CMD_FILE", "MT5/command.json"))


def _market_path() -> Path:
    return _under_root(os.environ.get("MT5_MARKET_FILE", "MT5/market_data.json"))


def _forge_open_group(
    *,
    group_id: int,
    direction: str,
    lot: float,
    sl_points: float,
    tp1_points: float,
    bid: float,
    ask: float,
    ts: str,
) -> dict:
    """
    Prices in instrument units (e.g. USD for XAUUSD). FORGE uses bid/ask vs
    ladder: within ~5 of bid/ask → market, else pending limit.
    """
    direction = direction.upper()
    if direction == "SELL":
        entry = round(bid, 2)
        sl = round(bid + sl_points, 2)
        tp1 = round(bid - tp1_points, 2)
    else:
        entry = round(ask, 2)
        sl = round(ask - sl_points, 2)
        tp1 = round(ask + tp1_points, 2)

    return {
        "action": "OPEN_GROUP",
        "group_id": group_id,
        "direction": direction,
        "entry_ladder": [entry],
        "lot_per_trade": lot,
        "sl": sl,
        "tp1": tp1,
        "tp2": None,
        "tp3": None,
        "tp1_close_pct": float(os.environ.get("TP1_CLOSE_PCT", "70")),
        "tp2_close_pct": float(os.environ.get("TP2_CLOSE_PCT", "20")),
        "move_be_on_tp1": os.environ.get("MOVE_BE_ON_TP1", "true").lower() == "true",
        "timestamp": ts,
    }


def main() -> int:
    _load_dotenv()
    os.chdir(_ROOT)
    sys.path.insert(0, str(_PY))

    ap = argparse.ArgumentParser(description="Write BRIDGE-shaped OPEN_GROUP to command.json")
    ap.add_argument("--write", action="store_true", help="Write command.json (default is dry-run)")
    ap.add_argument("--group-id", type=int, default=99001, help="Magic uses MagicNumber+group_id in FORGE")
    ap.add_argument("--direction", choices=("BUY", "SELL"), default="SELL")
    ap.add_argument("--lots", type=float, default=0.01)
    ap.add_argument(
        "--sl-points",
        type=float,
        default=15.0,
        help="Distance from entry to SL in price (e.g. 15 = $15 on XAUUSD)",
    )
    ap.add_argument(
        "--tp1-points",
        type=float,
        default=10.0,
        help="Distance from entry to TP1 in price",
    )
    ap.add_argument(
        "--stale-sec",
        type=float,
        default=float(os.environ.get("BRIDGE_MT5_STALE", "120")),
        help="Refuse if market_data.json older than this (seconds)",
    )
    args = ap.parse_args()

    mpath = _market_path()
    if not mpath.is_file():
        print("ERROR: missing", mpath.resolve(), "— start FORGE on chart first.", file=sys.stderr)
        return 1
    with open(mpath) as f:
        md = json.load(f)
    tsu = md.get("timestamp_unix")
    if tsu is None:
        print("ERROR: market_data.json has no timestamp_unix", file=sys.stderr)
        return 1
    age = time.time() - float(tsu)
    if age > args.stale_sec:
        print(
            f"ERROR: market_data.json is {age:.0f}s old (limit {args.stale_sec}).",
            file=sys.stderr,
        )
        return 1

    price = md.get("price") or {}
    bid = float(price.get("bid") or 0)
    ask = float(price.get("ask") or 0)
    if bid <= 0 or ask <= 0:
        print("ERROR: bid/ask missing in market_data.json", file=sys.stderr)
        return 1

    sym = md.get("symbol", "?")
    ts = datetime.now(timezone.utc).isoformat()
    cmd = _forge_open_group(
        group_id=args.group_id,
        direction=args.direction,
        lot=args.lots,
        sl_points=args.sl_points,
        tp1_points=args.tp1_points,
        bid=bid,
        ask=ask,
        ts=ts,
    )

    from contracts.aurum_forge import validate_forge_command

    errs = validate_forge_command(cmd)
    if errs:
        print("Contract validation failed:", errs, file=sys.stderr)
        return 1

    out = json.dumps(cmd, indent=2)
    cpath = _cmd_path()
    print(f"# symbol={sym} bid={bid} ask={ask} age={age:.1f}s")
    print(f"# command.json → {cpath.resolve()}")
    print(out)

    if args.write:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        with open(cpath, "w") as f:
            f.write(out)
        print("# wrote OK — watch MT5 Trade tab + Experts within a few timer ticks.", file=sys.stderr)
    else:
        print(
            "\n# dry-run only. Re-run with --write to push to FORGE, or paste JSON into command.json.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
