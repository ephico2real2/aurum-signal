#!/usr/bin/env python3
"""
setup_tests.py — Install all test framework dependencies
Usage:
  python3 scripts/setup_tests.py
  python3 scripts/setup_tests.py --check   # check only, don't install

Installs:
  - pytest + plugins (Python API tests)
  - Playwright + Chromium (UI tests)

Platform: macOS and Linux
"""

import sys, os, subprocess
from pathlib import Path

ROOT      = Path(__file__).parent.parent
TESTS_DIR = ROOT / "tests"
PYTHON    = sys.executable


def run(cmd, cwd=None, check=True):
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd or ROOT),
        capture_output=False
    )
    if check and result.returncode != 0:
        print(f"  ❌ Command failed (exit {result.returncode})")
        return False
    return True


def check_installed(module):
    result = subprocess.run(
        [PYTHON, "-c", f"import {module}; print(getattr({module}, '__version__', 'ok'))"],
        capture_output=True, text=True
    )
    return result.returncode == 0, result.stdout.strip()


def check_playwright():
    result = subprocess.run(
        ["npx", "playwright", "--version"],
        cwd=str(TESTS_DIR),
        capture_output=True, text=True
    )
    return result.returncode == 0, result.stdout.strip()


def setup(check_only=False):
    print("\n" + "═"*50)
    print("  SIGNAL SYSTEM — TEST SETUP")
    print("═"*50)

    all_ok = True

    print("\n📦 Python test dependencies:")
    py_deps = [
        ("pytest",       "pytest"),
        ("requests",     "requests"),
        ("dotenv",       "python-dotenv"),
        ("pytest_html",  "pytest-html"),
        ("pytest_cov",   "pytest-cov"),
        ("jsonschema",   "jsonschema"),
    ]
    for module, package in py_deps:
        ok, ver = check_installed(module)
        if ok:
            print(f"  ✅ {package} ({ver})")
        else:
            print(f"  ❌ {package} — not installed")
            if not check_only:
                success = run([
                    PYTHON, "-m", "pip", "install",
                    package, "--break-system-packages", "-q"
                ])
                if success:
                    print(f"     ✅ Installed")
                else:
                    all_ok = False

    print("\n📦 Node.js dependencies:")
    result = subprocess.run(["node", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  ✅ node {result.stdout.strip()}")
    else:
        print("  ❌ node not found — install from nodejs.org")
        all_ok = False

    pkg_json = TESTS_DIR / "package.json"
    if pkg_json.exists():
        print(f"  ✅ tests/package.json exists")
        if not check_only:
            print("  Installing npm deps...")
            run(["npm", "install"], cwd=TESTS_DIR)
    else:
        print("  ❌ tests/package.json missing")
        all_ok = False

    ok, ver = check_playwright()
    if ok:
        print(f"  ✅ Playwright {ver}")
    else:
        print("  ❌ Playwright not installed")
        if not check_only:
            print("  Installing Playwright...")
            run(["npx", "playwright", "install", "chromium"], cwd=TESTS_DIR)
            ok, ver = check_playwright()
            if ok:
                print(f"  ✅ Playwright {ver}")
            else:
                all_ok = False

    print("\n📁 Test files:")
    test_files = [
        TESTS_DIR / "conftest.py",
        TESTS_DIR / "playwright.config.js",
        TESTS_DIR / "api" / "test_live.py",
        TESTS_DIR / "api" / "test_endpoints.py",
        TESTS_DIR / "api" / "test_components.py",
        TESTS_DIR / "api" / "test_aurum.py",
        TESTS_DIR / "ui"  / "test_dashboard.spec.js",
        TESTS_DIR / "ui"  / "test_panels.spec.js",
    ]
    for f in test_files:
        exists = f.exists()
        icon = "✅" if exists else "❌"
        print(f"  {icon} {f.relative_to(ROOT)}")
        if not exists:
            all_ok = False

    print("\n" + "═"*50)
    if all_ok:
        print("  ✅ All test dependencies ready")
        print("\n  Run tests:")
        print("    python3 scripts/test_api.py      # API tests")
        print("    python3 scripts/test_ui.py        # UI tests")
        print("    python3 scripts/test_all.py       # everything")
    else:
        print("  ❌ Some dependencies missing — re-run without --check")
    print("═"*50 + "\n")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    check_only = "--check" in sys.argv
    setup(check_only=check_only)
