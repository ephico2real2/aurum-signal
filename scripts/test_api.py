#!/usr/bin/env python3
"""
test_api.py — Signal System API Test Runner
Usage:
  python3 scripts/test_api.py              # all tests except slow
  python3 scripts/test_api.py --all        # include slow (AURUM)
  python3 scripts/test_api.py --file live  # run test_live.py only
  python3 scripts/test_api.py --verbose    # extra output
  python3 scripts/test_api.py --html       # save HTML report

Requires: Flask API running at ATHENA_URL (default localhost:7842)
          pip3 install pytest pytest-html requests
"""

import sys, os, subprocess, argparse
from pathlib import Path

ROOT    = Path(__file__).parent.parent
TESTS   = ROOT / "tests" / "api"
PYTHON  = sys.executable


def check_api_running():
    try:
        import requests
        url = os.environ.get("ATHENA_URL", "http://localhost:7842")
        requests.get(f"{url}/api/health", timeout=3)
        return True
    except Exception:
        return False


def run(args):
    if not TESTS.exists():
        print(f"❌ Test directory not found: {TESTS}")
        print("   Run setup first: python3 scripts/setup_tests.py")
        sys.exit(1)

    if not check_api_running():
        print("❌ Flask API not reachable at localhost:7842")
        print("   Start it: cd ~/signal_system/python && python3 athena_api.py")
        sys.exit(1)

    cmd = [PYTHON, "-m", "pytest"]

    if args.file:
        target = TESTS / f"test_{args.file}.py"
        if not target.exists():
            print(f"❌ File not found: {target}")
            sys.exit(1)
        cmd.append(str(target))
    else:
        cmd.append(str(TESTS))

    if not args.all:
        cmd += ["-m", "not slow"]
    if args.verbose:
        cmd.append("-v")
    else:
        cmd += ["-v", "--tb=short"]

    if args.html:
        report = ROOT / "tests" / "api_report.html"
        cmd += [f"--html={report}", "--self-contained-html"]
        print(f"📄 HTML report will be saved to: {report}")

    print(f"\n🧪 Running API tests...")
    print(f"   Command: {' '.join(str(c) for c in cmd)}\n")

    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode == 0:
        print("\n✅ All API tests passed")
    else:
        print(f"\n❌ Tests failed (exit code {result.returncode})")

    sys.exit(result.returncode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run API tests")
    parser.add_argument("--all",     action="store_true",
                        help="Include slow tests (calls Claude API)")
    parser.add_argument("--file",    type=str,
                        help="Run single test file (e.g. --file live)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--html",    action="store_true",
                        help="Save HTML report")
    run(parser.parse_args())
