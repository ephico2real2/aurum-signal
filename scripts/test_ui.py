#!/usr/bin/env python3
"""
test_ui.py — Signal System Playwright UI Test Runner
Usage:
  python3 scripts/test_ui.py                  # headless
  python3 scripts/test_ui.py --headed         # watch Chrome run tests
  python3 scripts/test_ui.py --debug          # pause at each step
  python3 scripts/test_ui.py --record         # record new tests by clicking
  python3 scripts/test_ui.py --report         # open last HTML report
  python3 scripts/test_ui.py --file dashboard # run one spec file
        python3 scripts/test_ui.py --grep "AURUM"   # run tests matching pattern
        python3 scripts/test_ui.py --slow 500       # slow motion ms
        python3 scripts/test_ui.py --audit        # full tab walk + screenshots + results JSON

Requires: ATHENA dashboard running at localhost:7842
          npm install && npx playwright install chromium
          (in ~/signal_system/tests/)
"""

import sys, os, subprocess, argparse
from pathlib import Path

ROOT      = Path(__file__).parent.parent
TESTS_DIR = ROOT / "tests"
ATHENA_URL = os.environ.get("ATHENA_URL", "http://localhost:7842")


def playwright_subprocess_env() -> dict:
    """
    Env for npx/playwright child processes — avoids noisy warnings from inherited
    shell/IDE variables (npm unknown config; Node NO_COLOR vs FORCE_COLOR).
    """
    env = os.environ.copy()
    # npm 10+ warns: Unknown env config "devdir" (often NPM_CONFIG_DEVDIR from Homebrew/tools)
    for key in list(env):
        if key.upper() == "NPM_CONFIG_DEVDIR" or key.lower() == "npm_config_devdir":
            env.pop(key, None)
    # Node warns when both env vars exist; FORCE_COLOR wins — drop NO_COLOR for the child.
    # (Cursor/CI often set FORCE_COLOR to values outside "1"/"true"/"2"/"3".)
    if "FORCE_COLOR" in env and "NO_COLOR" in env:
        env.pop("NO_COLOR", None)
    elif env.get("NO_COLOR", "").strip():
        env.pop("FORCE_COLOR", None)
    return env


def check_playwright():
    result = subprocess.run(
        ["npx", "playwright", "--version"],
        cwd=str(TESTS_DIR),
        capture_output=True, text=True,
        env=playwright_subprocess_env(),
    )
    return result.returncode == 0


def check_athena_running():
    try:
        import urllib.request
        urllib.request.urlopen(f"{ATHENA_URL}/api/health", timeout=3)
        return True
    except Exception:
        return False


def run(args):
    if not TESTS_DIR.exists():
        print(f"❌ Tests directory not found: {TESTS_DIR}")
        sys.exit(1)

    if args.report:
        subprocess.run(
            ["npx", "playwright", "show-report"],
            cwd=str(TESTS_DIR),
            env=playwright_subprocess_env(),
        )
        return

    if args.record:
        print(f"🎥 Recording mode — interact with Chrome to generate tests")
        subprocess.run(
            ["npx", "playwright", "codegen", ATHENA_URL],
            cwd=str(TESTS_DIR),
            env=playwright_subprocess_env(),
        )
        return

    if not check_playwright():
        print("❌ Playwright not installed")
        print("   Fix: cd ~/signal_system/tests && npm install && npx playwright install chromium")
        sys.exit(1)

    if not check_athena_running():
        print(f"❌ ATHENA not reachable at {ATHENA_URL}")
        print("   Start: cd ~/signal_system/python && python3 athena_api.py")
        sys.exit(1)

    cmd = ["npx", "playwright", "test"]
    child_env = playwright_subprocess_env()

    if args.file:
        spec = TESTS_DIR / "ui" / f"test_{args.file}.spec.js"
        if not spec.exists():
            spec = TESTS_DIR / "ui" / f"{args.file}.spec.js"
        if not spec.exists():
            print(f"❌ Spec file not found for: {args.file}")
            sys.exit(1)
        cmd.append(str(spec.relative_to(TESTS_DIR)))

    if args.headed:
        cmd.append("--headed")
    if args.debug:
        cmd.append("--debug")
    if args.grep:
        cmd += ["--grep", args.grep]
    if args.slow:
        child_env["PLAYWRIGHT_SLOW_MO"] = str(args.slow)

    cmd += ["--reporter=html,list"]

    print(f"\n🎭 Running Playwright UI tests...")
    print(f"   Target: {ATHENA_URL}")
    print(f"   Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=str(TESTS_DIR), env=child_env)

    if result.returncode == 0:
        print("\n✅ All UI tests passed")
        print(f"   Report: cd ~/signal_system/tests && npx playwright show-report")
    else:
        print(f"\n❌ Tests failed — open report:")
        print(f"   cd ~/signal_system/tests && npx playwright show-report")

    sys.exit(result.returncode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Playwright UI tests")
    parser.add_argument("--headed", action="store_true",
                        help="Run in headed mode (watch Chrome)")
    parser.add_argument("--debug",  action="store_true",
                        help="Debug mode — pauses at each step")
    parser.add_argument("--record", action="store_true",
                        help="Record new tests by clicking")
    parser.add_argument("--report", action="store_true",
                        help="Open last HTML test report")
    parser.add_argument("--file",   type=str,
                        help="Run one spec file (e.g. --file dashboard)")
    parser.add_argument("--grep",   type=str,
                        help="Run tests matching pattern")
    parser.add_argument("--slow",   type=int,
                        help="Slow motion in ms (e.g. --slow 500)")
    parser.add_argument("--audit", action="store_true",
                        help="Run ATHENA full UI audit (tabs + screenshots + results JSON)")
    args = parser.parse_args()
    if args.audit:
        args.file = "athena_audit"
    run(args)
