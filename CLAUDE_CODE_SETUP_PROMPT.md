# CLAUDE CODE SETUP PROMPT — Signal System

This document provides the setup prompts and verification steps for configuring
the Signal System from a fresh environment using Claude Code.

## Overview

The Signal System is a XAUUSD scalping automation platform with 10 components:
BRIDGE, FORGE, LISTENER, LENS, SENTINEL, AEGIS, SCRIBE, HERALD, AURUM, ATHENA

**Architecture (API-first):**
Component → SCRIBE/JSON file → Flask API → Dashboard

## Step 1: Clone and enter the repository

```bash
git clone git@github.com:ephico2real2/aurum-signal.git ~/signal_system
cd ~/signal_system
```

## Step 2: Create .env from template

```bash
cp .env.example .env
# Edit with your actual credentials:
nano ~/signal_system/.env
```

Required keys:
- `ANTHROPIC_API_KEY` — Claude API key
- `TELEGRAM_BOT_TOKEN` — Telegram bot token
- `TELEGRAM_CHAT_ID` — Your Telegram chat ID
- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` — For Telethon listener
- `LENS_MCP_CMD` — Path to TradingView MCP server.js

## Step 3: Install Python dependencies

```bash
cd ~/signal_system
pip3 install -r requirements.txt --break-system-packages
```

## Step 4: Verify SCRIBE database

```bash
cd ~/signal_system/python
python3 -c "
import sys; sys.path.insert(0,'.')
from dotenv import load_dotenv; load_dotenv('../.env')
from scribe import get_scribe
s = get_scribe()
tables = [t['name'] for t in s.query(\"SELECT name FROM sqlite_master WHERE type='table'\")]
print('Tables:', tables)
assert 'component_heartbeats' in tables
print('SCRIBE OK ✅')
"
```

## Step 5: Install test framework

```bash
# Python test deps
pip3 install pytest pytest-html pytest-cov requests --break-system-packages

# Playwright
cd ~/signal_system/tests
npm install
npx playwright install chromium

# Verify both
python3 -c "import pytest; print('pytest', pytest.__version__)"
npx playwright --version
```

## Step 6: Start the API and run verification

```bash
cd ~/signal_system/python
python3 athena_api.py &
sleep 3

# Verify all endpoints
curl -s http://localhost:7842/api/health
curl -s http://localhost:7842/api/components | python3 -m json.tool | head -20
```

## Step 7: Run API tests

```bash
cd ~/signal_system
python3 -m pytest tests/api/ -v -m "not slow" --tb=short
```

## Step 8: Run Playwright UI tests

```bash
# ATHENA must be running (Step 6)
cd ~/signal_system/tests
npx playwright test --headed
npx playwright show-report
```

## Step 9: Install services (macOS)

```bash
cd ~/signal_system
python3 services/install_services.py
python3 services/install_services.py --status
```

## Quick reference

```bash
# Health check
python3 ~/signal_system/scripts/health.py

# Run all tests
python3 ~/signal_system/scripts/test_all.py

# Shortcuts (after source ~/.zshrc)
ss-health
ss-test
ss-test-api
ss-test-ui
ss-logs
```

## Architecture notes

- All dashboard data flows through the Flask API — zero hardcoded mock data
- `component_heartbeats` table in SCRIBE tracks all 11 components
- `/api/components` returns real-time health for all components
- `/api/live` returns complete system state in one payload
- `config/` files written by bridge.py in `python/config/` (WorkingDirectory=python/)
- `MT5/` files written by FORGE EA at project root (symlink to MetaQuotes)
