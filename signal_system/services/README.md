# Signal System Services

## What runs as a service (4 processes only)

| Service | File | Role |
|---------|------|------|
| BRIDGE  | bridge.py | Orchestrator — drives all internal modules |
| LISTENER | listener.py | Telegram signal reader |
| AURUM | aurum.py --telegram | AI agent Telegram bot |
| ATHENA | athena_api.py | Flask dashboard API |

## What is NOT a separate service

scribe, herald, aegis, sentinel, lens are Python modules
imported internally by bridge.py. They are not separate processes.

## Install (Claude Code runs this automatically)

```bash
make start
# or: python3 services/install_services.py
```

The installer:
1. Renders plist templates (`services/macos/*.plist`) with `.env` values → `services/macos/rendered/`
2. Creates **symlinks** from `~/Library/LaunchAgents/` → rendered files in the repo
3. Loads all 4 services via `launchctl`

Because LaunchAgents entries are **symlinks** (not copies), the running configuration is always traceable from the source base directory.

**Python interpreter:** Plists use **`PROJECT/.venv/bin/python`** when that file exists. Otherwise **`SIGNAL_PYTHON`** from the environment, or **`python3`** on `PATH`. Re-run `make start` after creating `.venv`.

**PATH (macOS):** The installer injects a `PATH` that includes Homebrew (`/opt/homebrew/bin`, `/usr/local/bin`) plus `node`/`npx` directories (required for LENS / TradingView MCP).

Detects macOS vs Linux automatically. Replaces YOUR_USERNAME with
your real username. Enables auto-start on login/boot.

## Commands

```bash
# Full install (render plists + symlink + load)
make start

# Check all services are running
make status

# Hot-restart after editing Python code (fast — no plist re-render)
make reload            # all 4 processes
make reload-bridge     # just BRIDGE (sentinel/aegis/aurum changes)

# Full restart after editing .env (re-renders plists)
make restart

# Stop everything
make stop

# View logs
make logs-bridge
make logs-athena
```

## macOS: manual launchctl commands

```bash
# Verify symlinks (should show -> services/macos/rendered/...)
ls -la ~/Library/LaunchAgents/com.signalsystem.*

# Stop one service
launchctl unload ~/Library/LaunchAgents/com.signalsystem.bridge.plist

# Start one service
launchctl load ~/Library/LaunchAgents/com.signalsystem.bridge.plist

# Check if running
launchctl list com.signalsystem.bridge

# View live log
tail -f ~/signal_system/logs/bridge.log
```

## Linux: manual systemctl commands

```bash
# Status
sudo systemctl status signal-bridge

# Stop/start one
sudo systemctl stop signal-bridge
sudo systemctl start signal-bridge

# View live logs
journalctl -u signal-bridge -f
```

## Log files (macOS)

~/signal_system/logs/
  bridge.log          bridge.error.log
  listener.log        listener.error.log
  aurum.log           aurum.error.log
  athena.log          athena.error.log

## Service startup order

bridge starts first (ThrottleInterval=10s).
listener, aurum, athena start 15s later —
enough time for bridge to initialise SCRIBE and write status.json.
