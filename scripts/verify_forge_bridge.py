#!/usr/bin/env python3
"""
verify_forge_bridge.py — Check BRIDGE ↔ FORGE file-bus alignment
================================================================
SCRIBE can log groups while MT5 shows nothing if command.json and
market_data.json are not in the same place FORGE uses (Common Files).

Run from repo root:  python3 scripts/verify_forge_bridge.py
Loads .env from repo root if python-dotenv is installed (optional).
"""

from __future__ import annotations

import json
import os
import sys
import time
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


def main() -> int:
    _load_dotenv()
    os.chdir(_ROOT)

    cmd = _under_root(os.environ.get("MT5_CMD_FILE", "MT5/command.json"))
    cfg = _under_root(os.environ.get("MT5_CONFIG_FILE", "MT5/config.json"))
    mkt = _under_root(os.environ.get("MT5_MARKET_FILE", "MT5/market_data.json"))
    brk = _under_root(os.environ.get("MT5_BROKER_FILE", "MT5/broker_info.json"))
    mirror_raw = os.environ.get("MT5_CMD_FILE_MIRROR", "").strip()
    mirror = None
    if mirror_raw:
        mirror = Path(mirror_raw) if os.path.isabs(mirror_raw) else _ROOT / mirror_raw

    print("FORGE ↔ BRIDGE path check")
    print("─" * 60)
    print("command.json     ", cmd.resolve())
    print("config.json      ", cfg.resolve())
    print("market_data.json ", mkt.resolve())
    print("broker_info.json ", brk.resolve())
    if mirror:
        print("command (mirror) ", mirror.resolve())

    mt5_dir = _ROOT / "MT5"
    if sys.platform == "darwin" and mt5_dir.exists():
        print("─" * 60)
        print("MT5/ is symlink:", mt5_dir.is_symlink())
        if mt5_dir.is_symlink():
            print("  →", os.readlink(mt5_dir))

    cdir = cmd.resolve().parent
    mdir = mkt.resolve().parent
    print("─" * 60)
    if cdir == mdir:
        print("OK: command.json and market_data.json share the same directory.")
    else:
        print("FAIL: command dir != market_data dir — FORGE will not see BRIDGE commands.")
        print("  command parent:", cdir)
        print("  market parent: ", mdir)
        print("  Fix: symlink MT5/ to Terminal Common Files, or set MT5_*_FILE / mirror.")
        return 1

    if mkt.is_file():
        try:
            with open(mkt) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print("WARN: market_data.json is not valid JSON:", e)
            return 1
        ts = data.get("timestamp_unix")
        try:
            age = time.time() - float(ts) if ts is not None else None
        except (TypeError, ValueError):
            age = None
        fv = data.get("forge_version") or data.get("hermes_version", "?")
        cyc = data.get("ea_cycle", "?")
        print("─" * 60)
        print(f"market_data: forge_version={fv} ea_cycle={cyc}")
        if age is not None:
            stale = int(os.environ.get("BRIDGE_MT5_STALE", "120"))
            flag = "OK" if age < stale else "STALE"
            print(f"  age {age:.0f}s ({flag}; BRIDGE_MT5_STALE={stale})")
        else:
            print("  (could not compute age from timestamp_unix)")
    else:
        print("─" * 60)
        print("WARN: market_data.json missing — FORGE not writing to this path (EA off / wrong folder).")

    if cmd.is_file():
        try:
            with open(cmd) as f:
                cj = json.load(f)
            print("─" * 60)
            print('command.json action:', cj.get("action"), '| timestamp:', cj.get("timestamp"))
        except json.JSONDecodeError as e:
            print("WARN: command.json invalid JSON:", e)
    else:
        print("─" * 60)
        print("No command.json yet (normal until the next OPEN_GROUP).")

    if mirror and mirror.is_file():
        print("─" * 60)
        print("Mirror command.json exists at", mirror.resolve())

    print("─" * 60)
    print("Compare MT5 Experts log: FORGE prints commonpath= on init.")
    print("That folder’s Files area must match the directory above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
