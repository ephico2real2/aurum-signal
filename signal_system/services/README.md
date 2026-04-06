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
python3 services/install_services.py
```

**Python interpreter:** Plists/units use **`PROJECT/.venv/bin/python`** when that file exists (same deps as `make test-contracts` after `make venv`). Otherwise **`SIGNAL_PYTHON`** from the environment when you run the installer, or **`python3`** on `PATH`. Re-run **`python3 services/install_services.py`** (or **`make restart`**) after creating `.venv`.

**PATH (macOS):** LaunchAgents get a minimal environment. The installer injects a `PATH` that includes Homebrew (`/opt/homebrew/bin`, `/usr/local/bin`) plus the directory of your `node`/`npx` (required for LENS / TradingView MCP). If you use nvm, add `PATH=...` to `.env`; it is **prepended** to that base.

Detects macOS vs Linux automatically. Replaces YOUR_USERNAME with
your real username. Enables auto-start on login/boot.

## Commands

```bash
# Check all services are running
python3 services/install_services.py --status

# View logs for a service
python3 services/install_services.py --logs bridge
python3 services/install_services.py --logs listener
python3 services/install_services.py --logs aurum
python3 services/install_services.py --logs athena

# Stop everything
python3 services/install_services.py --stop

# Restart everything
python3 services/install_services.py --restart
```

## macOS: manual launchctl commands

```bash
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
