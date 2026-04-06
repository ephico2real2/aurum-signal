#!/usr/bin/env python3
"""
install_services.py
===================
Run by Claude Code during setup.
Detects macOS vs Linux and installs the appropriate service files.
Replaces YOUR_USERNAME with the real username throughout.
Creates logs directory. Enables and starts all 4 services.

Usage:
    python3 install_services.py
    python3 install_services.py --stop
    python3 install_services.py --status
    python3 install_services.py --logs bridge
"""

import os, sys, shutil, subprocess, platform
from pathlib import Path


def resolve_signal_python(project: Path) -> str:
    """
    Interpreter for launchd/systemd: .venv if present, else SIGNAL_PYTHON env, else python3 on PATH.
    """
    override = (os.environ.get("SIGNAL_PYTHON") or "").strip()
    if override:
        return str(Path(override).expanduser().resolve())
    venv_py = project / ".venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py.resolve())
    w = shutil.which("python3")
    return w or "/usr/bin/python3"


def inject_signal_python(content: str, project: Path) -> str:
    return content.replace("__SIGNAL_PYTHON__", resolve_signal_python(project))

USERNAME  = os.environ.get("USER") or os.environ.get("USERNAME") or os.popen("whoami").read().strip()
HOME      = Path.home()
# Repo root: this file lives at <root>/services/install_services.py
_PROJECT_FROM_SCRIPT = Path(__file__).resolve().parent.parent
if (_PROJECT_FROM_SCRIPT / "python" / "bridge.py").is_file():
    PROJECT = _PROJECT_FROM_SCRIPT
else:
    PROJECT = HOME / "signal_system"
LOGS_DIR  = PROJECT / "logs"
SERVICES  = ["bridge", "listener", "aurum", "athena"]
IS_MACOS  = platform.system() == "Darwin"
IS_LINUX  = platform.system() == "Linux"

MACOS_LAUNCH_AGENTS = HOME / "Library" / "LaunchAgents"
LINUX_SYSTEMD       = Path("/etc/systemd/system")

def run(cmd, check=True):
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout.strip():
        print(f"    {result.stdout.strip()}")
    if result.returncode != 0 and check:
        print(f"  ERROR: {result.stderr.strip()}")
    return result

def replace_username(text):
    return text.replace("YOUR_USERNAME", USERNAME)

def default_launchd_path() -> str:
    """
    PATH for launchd jobs: Homebrew (Apple Silicon + Intel), common Node locations,
    then system paths. LENS MCP needs node/npx in PATH.
    """
    parts: list[str] = []
    for cmd in ("npx", "node", "npm"):
        w = shutil.which(cmd)
        if w:
            d = str(Path(w).resolve().parent)
            if d not in parts:
                parts.append(d)
    for d in (
        "/opt/homebrew/bin",
        "/usr/local/bin",
        str(HOME / ".local" / "bin"),
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ):
        if d not in parts:
            parts.append(d)
    return ":".join(parts)


def load_env_vars():
    """Parse <PROJECT>/.env and return dict of key=value pairs."""
    env_file = PROJECT / ".env"
    env = {}
    if not env_file.exists():
        print(f"  ⚠ .env not found at {env_file}")
        return env
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def inject_env_vars(plist_text, env_vars):
    """Inject .env key/value pairs into the plist EnvironmentVariables dict."""
    inject = ""
    for k, v in env_vars.items():
        inject += f"        <key>{k}</key>\n        <string>{v}</string>\n"
    # Insert before the closing </dict> of EnvironmentVariables
    return plist_text.replace(
        "        <key>PYTHONUNBUFFERED</key>\n        <string>1</string>",
        "        <key>PYTHONUNBUFFERED</key>\n        <string>1</string>\n" + inject
    )

def ensure_logs():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✓ Logs directory: {LOGS_DIR}")

# ── macOS launchd ─────────────────────────────────────────────────
def install_macos():
    MACOS_LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    src_dir = PROJECT / "services" / "macos"
    env_vars = load_env_vars()

    for svc in SERVICES:
        plist_name = f"com.signalsystem.{svc}.plist"
        src  = src_dir / plist_name
        dest = MACOS_LAUNCH_AGENTS / plist_name

        if not src.exists():
            print(f"  ✗ Missing: {src}")
            continue

        merged = dict(env_vars)
        base_p = default_launchd_path()
        if "PATH" in merged and merged["PATH"].strip():
            merged["PATH"] = base_p + ":" + merged["PATH"].strip()
        else:
            merged["PATH"] = base_p

        content = src.read_text()
        content = replace_username(content)
        content = inject_signal_python(content, PROJECT)
        content = inject_env_vars(content, merged)
        dest.write_text(content)
        print(f"✓ Installed: {dest}")

        # Unload first if already loaded
        run(f"launchctl unload {dest} 2>/dev/null", check=False)
        result = run(f"launchctl load {dest}")
        if result.returncode == 0:
            print(f"✓ Loaded: com.signalsystem.{svc}")
        else:
            print(f"  ✗ Failed to load {plist_name}: {result.stderr}")

def stop_macos():
    for svc in SERVICES:
        plist = MACOS_LAUNCH_AGENTS / f"com.signalsystem.{svc}.plist"
        run(f"launchctl unload {plist} 2>/dev/null", check=False)
        print(f"✓ Stopped: com.signalsystem.{svc}")

def status_macos():
    print("\nService Status (macOS launchd):")
    for svc in SERVICES:
        result = run(f"launchctl list com.signalsystem.{svc}", check=False)
        if result.returncode == 0:
            pid_line = [l for l in result.stdout.splitlines() if '"PID"' in l]
            pid = pid_line[0].strip() if pid_line else "unknown"
            print(f"  ✅ com.signalsystem.{svc} — {pid}")
        else:
            print(f"  ❌ com.signalsystem.{svc} — not running")

def logs_macos(svc):
    log_file = LOGS_DIR / f"{svc}.log"
    err_file = LOGS_DIR / f"{svc}.error.log"
    print(f"\n=== {svc}.log (last 30 lines) ===")
    run(f"tail -30 {log_file}", check=False)
    print(f"\n=== {svc}.error.log ===")
    run(f"tail -10 {err_file}", check=False)

# ── Linux systemd ─────────────────────────────────────────────────
def install_linux():
    src_dir = PROJECT / "services" / "linux"

    for svc in SERVICES:
        unit_name = f"signal-{svc}.service"
        src  = src_dir / unit_name
        dest = LINUX_SYSTEMD / unit_name

        if not src.exists():
            print(f"  ✗ Missing: {src}")
            continue

        content = src.read_text()
        content = replace_username(content)
        content = inject_signal_python(content, PROJECT)

        # Write to systemd (needs sudo)
        tmp = PROJECT / "services" / "linux" / f"_{unit_name}"
        tmp.write_text(content)
        run(f"sudo cp {tmp} {dest}")
        tmp.unlink()
        print(f"✓ Installed: {dest}")

    run("sudo systemctl daemon-reload")
    for svc in SERVICES:
        run(f"sudo systemctl enable signal-{svc}.service")
        run(f"sudo systemctl start signal-{svc}.service")
        print(f"✓ Started: signal-{svc}")

def stop_linux():
    for svc in SERVICES:
        run(f"sudo systemctl stop signal-{svc}.service", check=False)
        print(f"✓ Stopped: signal-{svc}")

def status_linux():
    print("\nService Status (systemd):")
    for svc in SERVICES:
        result = run(f"systemctl is-active signal-{svc}.service", check=False)
        status = result.stdout.strip()
        icon = "✅" if status == "active" else "❌"
        print(f"  {icon} signal-{svc} — {status}")

def logs_linux(svc):
    run(f"journalctl -u signal-{svc} -n 50 --no-pager")

# ── Entrypoint ────────────────────────────────────────────────────
def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "--install"

    print(f"\nSignal System Service Manager")
    print(f"Platform: {'macOS' if IS_MACOS else 'Linux'}")
    print(f"Username: {USERNAME}")
    print(f"Project:  {PROJECT}\n")

    ensure_logs()

    if arg == "--install":
        print("Installing services...\n")
        print(f"  Python for services: {resolve_signal_python(PROJECT)}\n")
        if IS_MACOS:   install_macos()
        elif IS_LINUX: install_linux()
        else: print("Unsupported platform"); sys.exit(1)
        print("\n✅ All services installed.")
        print("   Services start automatically on login/boot.")
        print(f"   Logs: {LOGS_DIR}/")
        print("\n   To check status:  python3 install_services.py --status")
        print("   To view logs:     python3 install_services.py --logs bridge")

    elif arg == "--stop":
        print("Stopping services...\n")
        if IS_MACOS:   stop_macos()
        elif IS_LINUX: stop_linux()

    elif arg == "--status":
        if IS_MACOS:   status_macos()
        elif IS_LINUX: status_linux()

    elif arg == "--logs":
        svc = sys.argv[2] if len(sys.argv) > 2 else "bridge"
        if svc not in SERVICES:
            print(f"Valid services: {', '.join(SERVICES)}")
            sys.exit(1)
        if IS_MACOS:   logs_macos(svc)
        elif IS_LINUX: logs_linux(svc)

    elif arg == "--restart":
        print("Restarting services...\n")
        print(f"  Python for services: {resolve_signal_python(PROJECT)}\n")
        if IS_MACOS:
            stop_macos()
            import time; time.sleep(2)
            install_macos()
        elif IS_LINUX:
            for svc in SERVICES:
                run(f"sudo systemctl restart signal-{svc}.service")

    else:
        print(f"Unknown argument: {arg}")
        print("Usage: python3 install_services.py [--install|--stop|--status|--logs <svc>|--restart]")


if __name__ == "__main__":
    main()
