#!/usr/bin/env python3
"""
logs.py — Signal System Log Viewer
Usage:
  python3 scripts/logs.py                    # show last 30 lines all services
  python3 scripts/logs.py bridge             # bridge only
  python3 scripts/logs.py bridge --follow    # tail -f bridge log
  python3 scripts/logs.py --errors           # only error lines across all
  python3 scripts/logs.py --since 30         # last 30 minutes

Services: bridge, listener, aurum, athena
"""

import sys, os, subprocess, argparse
from pathlib import Path

ROOT     = Path(__file__).parent.parent
LOGS_DIR = ROOT / "logs"

SERVICES = ["bridge", "listener", "aurum", "athena"]
LOG_FILES = {
    s: {
        "out": LOGS_DIR / f"{s}.log",
        "err": LOGS_DIR / f"{s}.error.log",
    }
    for s in SERVICES
}


def tail_file(path, n=30, errors_only=False):
    if not path.exists():
        return []
    lines = path.read_text(errors="replace").splitlines()
    if errors_only:
        lines = [l for l in lines if any(
            w in l.upper() for w in ["ERROR", "CRITICAL", "EXCEPTION", "TRACEBACK"]
        )]
    return lines[-n:]


def run(args):
    services = [args.service] if args.service else SERVICES

    if args.follow and len(services) == 1:
        log_path = LOG_FILES[services[0]]["out"]
        if not log_path.exists():
            print(f"❌ Log not found: {log_path}")
            sys.exit(1)
        print(f"📋 Following {log_path} (Ctrl+C to stop)\n")
        subprocess.run(["tail", "-f", str(log_path)])
        return

    for svc in services:
        files = LOG_FILES.get(svc, {})
        out_path = files.get("out")
        err_path = files.get("err")

        print(f"\n{'─'*60}")
        print(f"  {svc.upper()}")
        print(f"{'─'*60}")

        if out_path and out_path.exists():
            lines = tail_file(out_path, n=args.lines, errors_only=args.errors)
            if lines:
                for line in lines:
                    print(f"  {line}")
            else:
                print("  (no matching lines)")
        else:
            print(f"  Log not found: {out_path}")

        if err_path and err_path.exists():
            err_lines = tail_file(err_path, n=10)
            if err_lines:
                print(f"\n  ── stderr ──")
                for line in err_lines[-5:]:
                    print(f"  ⚠ {line}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="View service logs")
    parser.add_argument("service", nargs="?",
                        choices=SERVICES,
                        help="Service to show (default: all)")
    parser.add_argument("--follow",  "-f", action="store_true",
                        help="Follow log in real-time (single service)")
    parser.add_argument("--errors",  "-e", action="store_true",
                        help="Show only error lines")
    parser.add_argument("--lines",   "-n", type=int, default=30,
                        help="Number of lines to show (default: 30)")
    parser.add_argument("--since",   type=int,
                        help="Show entries from last N minutes")
    run(parser.parse_args())
