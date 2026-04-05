#!/usr/bin/env python3
"""
health.py — Signal System Health Check
Usage:  python3 scripts/health.py
        python3 scripts/health.py --json
        python3 scripts/health.py --watch   (repeat every 10s)

Checks: API reachability, all 11 components, MT5 connection,
        database tables, LENS data, mode, session.
Exit code: 0 = all healthy, 1 = warnings, 2 = errors
"""

import sys, os, json, time, argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "python"))

ATHENA_URL = os.environ.get("ATHENA_URL", "http://localhost:7842")
EXPECTED_COMPONENTS = [
    "BRIDGE","FORGE","LISTENER","LENS","SENTINEL",
    "AEGIS","SCRIBE","HERALD","AURUM","RECONCILER","ATHENA"
]
EXPECTED_TABLES = [
    "system_events","trading_sessions","market_snapshots",
    "signals_received","trade_groups","trade_positions",
    "news_events","aurum_conversations","component_heartbeats"
]


def check_api():
    try:
        import requests
        r = requests.get(f"{ATHENA_URL}/api/health", timeout=5)
        if r.status_code == 200:
            return "OK", r.json()
        return "ERROR", f"HTTP {r.status_code}"
    except Exception as e:
        return "ERROR", str(e)


def check_live():
    try:
        import requests
        r = requests.get(f"{ATHENA_URL}/api/live", timeout=5)
        d = r.json()
        missing = []
        required = ["mode","session","components","aegis",
                    "circuit_breaker","account_type","broker",
                    "mt5_connected","open_groups","performance"]
        for k in required:
            if k not in d:
                missing.append(k)
        if missing:
            return "WARN", f"Missing keys: {missing}"
        return "OK", {
            "mode":         d.get("mode"),
            "session":      d.get("session"),
            "account_type": d.get("account_type"),
            "broker":       d.get("broker"),
            "mt5":          d.get("mt5_connected"),
            "circuit_br":   d.get("circuit_breaker"),
            "components":   len(d.get("components", {})),
        }
    except Exception as e:
        return "ERROR", str(e)


def check_components():
    try:
        import requests
        r = requests.get(f"{ATHENA_URL}/api/components", timeout=5)
        d = r.json()
        names = [c["name"] for c in d.get("components", [])]
        missing = [e for e in EXPECTED_COMPONENTS if e not in names]
        unhealthy = [c["name"] for c in d.get("components", [])
                     if not c.get("ok")]
        if missing:
            return "ERROR", f"Missing components: {missing}"
        if unhealthy:
            return "WARN", f"Unhealthy: {unhealthy}"
        return "OK", f"{d.get('healthy')}/{d.get('total')} healthy"
    except Exception as e:
        return "ERROR", str(e)


def check_scribe():
    try:
        os.chdir(ROOT / "python")
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        from scribe import get_scribe
        s = get_scribe()
        tables = [t["name"] for t in s.query(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        missing = [t for t in EXPECTED_TABLES if t not in tables]
        if missing:
            return "WARN", f"Missing tables: {missing}"
        return "OK", f"{len(tables)} tables present"
    except Exception as e:
        return "ERROR", str(e)


def check_mt5():
    mt5_file = ROOT / "MT5" / "market_data.json"
    try:
        with open(mt5_file) as f:
            d = json.load(f)
        age = time.time() - d.get("timestamp_unix", 0)
        bal = d.get("account", {}).get("balance")
        if age > 300:
            return "ERROR", f"Stale: {age:.0f}s old"
        if age > 120:
            return "WARN", f"Age: {age:.0f}s, balance=${bal:,.2f}" if bal else f"Age: {age:.0f}s"
        return "OK", f"Age: {age:.0f}s, balance=${bal:,.2f}" if bal else f"Age: {age:.0f}s"
    except FileNotFoundError:
        return "WARN", "market_data.json not found (FORGE not running?)"
    except Exception as e:
        return "ERROR", str(e)


def check_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return "ERROR", ".env file not found"
    required = ["ANTHROPIC_API_KEY","TELEGRAM_BOT_TOKEN","LENS_MCP_CMD"]
    content = env_file.read_text()
    missing = [k for k in required if k + "=" not in content]
    if missing:
        return "WARN", f"Missing keys: {missing}"
    for line in content.splitlines():
        if line.startswith("LENS_MCP_CMD="):
            path = line.split("=", 1)[1].replace("node ", "").strip().strip('"')
            if not Path(path).exists():
                return "WARN", f"LENS_MCP_CMD path not found: {path}"
    return "OK", "All required keys present"


CHECKS = [
    ("Flask API",        check_api),
    ("/api/live",        check_live),
    ("Components (11)",  check_components),
    ("SCRIBE DB",        check_scribe),
    ("MT5 data",         check_mt5),
    (".env config",      check_env),
]

ICONS = {"OK": "✅", "WARN": "⚠️ ", "ERROR": "❌"}


def run_once(as_json=False):
    results = []
    overall = "OK"
    for name, fn in CHECKS:
        status, detail = fn()
        results.append({"check": name, "status": status, "detail": detail})
        if status == "ERROR":
            overall = "ERROR"
        elif status == "WARN" and overall == "OK":
            overall = "WARN"

    if as_json:
        print(json.dumps({"overall": overall, "checks": results}, indent=2))
    else:
        print(f"\n{'='*50}")
        print(f"  SIGNAL SYSTEM HEALTH — {time.strftime('%H:%M:%S UTC', time.gmtime())}")
        print(f"{'='*50}")
        for r in results:
            icon = ICONS.get(r["status"], "?")
            detail = r["detail"]
            if isinstance(detail, dict):
                detail = " | ".join(f"{k}={v}" for k, v in detail.items())
            print(f"  {icon} {r['check']:<22} {detail}")
        print(f"{'='*50}")
        print(f"  Overall: {ICONS[overall]} {overall}")
        print()

    exit_code = {"OK": 0, "WARN": 1, "ERROR": 2}.get(overall, 2)
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Signal System Health Check")
    parser.add_argument("--json",  action="store_true")
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()

    if args.watch:
        while True:
            os.system("clear")
            run_once(as_json=args.json)
            time.sleep(10)
    else:
        sys.exit(run_once(as_json=args.json))
