#!/usr/bin/env python3
"""
test_all.py — Run complete Signal System test suite
Usage:
  python3 scripts/test_all.py           # API + UI tests
  python3 scripts/test_all.py --api     # API tests only
  python3 scripts/test_all.py --ui      # UI tests only
  python3 scripts/test_all.py --html    # save HTML reports
  python3 scripts/test_all.py --ci      # CI mode (headless, verbose output)

Exit code: 0 = all passed, 1 = some failed
"""

import sys, os, subprocess, time, argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "scripts"


def run_script(script, extra_args=None):
    cmd = [sys.executable, str(SCRIPTS / script)] + (extra_args or [])
    result = subprocess.run(cmd, cwd=str(ROOT))
    return result.returncode


def run(args):
    results = {}
    start = time.time()

    print("\n" + "═"*60)
    print("  SIGNAL SYSTEM — COMPLETE TEST SUITE")
    print("═"*60)

    print("\n📋 Running health check...")
    code = run_script("health.py")
    results["health"] = code
    if code == 2:
        print("❌ System not healthy — aborting test run")
        sys.exit(2)

    if args.api or not args.ui:
        print("\n🧪 Running API tests...")
        api_args = []
        if args.html:
            api_args.append("--html")
        if args.ci:
            api_args.append("--verbose")
        code = run_script("test_api.py", api_args)
        results["api"] = code

    if args.ui or not args.api:
        print("\n🎭 Running UI tests...")
        ui_args = []
        code = run_script("test_ui.py", ui_args)
        results["ui"] = code

    elapsed = time.time() - start
    print("\n" + "═"*60)
    print("  TEST RESULTS SUMMARY")
    print("═"*60)
    icons = {0: "✅", 1: "⚠️ ", 2: "❌"}
    for suite, code in results.items():
        icon = icons.get(code, "❌")
        if suite == "health":
            # health.py: 0=OK, 1=WARN (still runnable), 2=ERROR (aborted earlier)
            passed = code in (0, 1)
            status = "PASSED" if passed else "FAILED"
            if code == 1:
                icon = "⚠️ "
        else:
            status = "PASSED" if code == 0 else "FAILED"
        print(f"  {icon} {suite:<12} {status}")
    print(f"\n  ⏱  Total time: {elapsed:.1f}s")
    print("═"*60 + "\n")

    h = results.get("health", 0)
    api_ok = results.get("api", 0) == 0
    ui_ok = results.get("ui", 0) == 0
    # WARN health is acceptable when API + UI tests pass
    overall = 0 if h <= 1 and api_ok and ui_ok else 1
    sys.exit(overall)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run all tests")
    parser.add_argument("--api",  action="store_true", help="API tests only")
    parser.add_argument("--ui",   action="store_true", help="UI tests only")
    parser.add_argument("--html", action="store_true", help="Save HTML reports")
    parser.add_argument("--ci",   action="store_true", help="CI mode")
    run(parser.parse_args())
