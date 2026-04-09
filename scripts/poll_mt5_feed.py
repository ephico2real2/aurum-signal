#!/usr/bin/env python3
"""
poll_mt5_feed.py — Wait until market_data.json shows expected FORGE version
============================================================================
After `make forge-compile`, MT5 often keeps the OLD EA in memory until you
remove FORGE from the chart and attach it again (or restart MetaTrader).

Usage (repo root):
  python3 scripts/poll_mt5_feed.py
  python3 scripts/poll_mt5_feed.py --timeout 180
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _expected_version_from_mq5(mq5_path: Path) -> str:
    text = mq5_path.read_text(encoding="utf-8", errors="replace")
    # First occurrence in WriteMarketData JSON builder
    # MQL5 source: j += "\"forge_version\":\"1.2.4\",";
    m = re.search(r'\\"forge_version\\":\\"([0-9.]+)\\"', text)
    return m.group(1) if m else ""


def _market_path(root: Path) -> Path:
    rel = os.environ.get("MT5_MARKET_FILE", "MT5/market_data.json")
    p = Path(rel)
    return p if p.is_absolute() else (root / rel)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=_root())
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--interval", type=float, default=4.0)
    ap.add_argument("--expected", default="", help="Override FORGE version (default: parse ea/FORGE.mq5)")
    args = ap.parse_args()

    root = args.repo_root.resolve()
    mq5 = root / "ea" / "FORGE.mq5"
    expected = args.expected.strip() or _expected_version_from_mq5(mq5)
    if not expected:
        print("ERROR: could not parse expected forge_version from", mq5, file=sys.stderr)
        return 2

    mpath = _market_path(root)
    deadline = time.monotonic() + args.timeout
    print(f"Polling {mpath.resolve()} for forge_version={expected!r} (timeout {args.timeout}s)", flush=True)
    print(
        "If this times out: in MT5, remove FORGE from the chart → attach FORGE again (or restart MT5).",
        flush=True,
    )

    last_ver = None
    while time.monotonic() < deadline:
        if mpath.is_file():
            try:
                data = json.loads(mpath.read_text())
            except json.JSONDecodeError:
                data = {}
            ver = data.get("forge_version")
            last_ver = ver
            pend = len(data.get("pending_orders") or [])
            pfc = data.get("pending_orders_forge_count")
            if ver == expected:
                print(
                    f"OK — forge_version={ver!r} pending_orders={pend} "
                    f"pending_orders_forge_count={pfc!r}",
                    flush=True,
                )
                return 0
        time.sleep(args.interval)

    print(
        f"TIMEOUT — last forge_version={last_ver!r}, expected={expected!r}. "
        "Reattach FORGE on the chart or restart MetaTrader, then rerun this script.",
        flush=True,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
