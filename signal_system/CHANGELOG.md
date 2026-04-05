# SIGNAL SYSTEM — CHANGELOG

## [1.2.0] — 2026-04-05

### Architecture: API-First Dashboard
All data displayed in ATHENA now flows through the Flask API.
No hardcoded mock data remains in the dashboard.

**Rule enforced:**
Component → SCRIBE/JSON file → Flask endpoint → Dashboard

### Added
- `SCRIBE.component_heartbeats` table — one row per component,
  upserted on every cycle, tracks status/note/last_action/error
- `Scribe.heartbeat()` method — upsert current component state
- `Scribe.get_component_heartbeats()` method — read all heartbeats
- `GET /api/components` — dedicated component health endpoint,
  returns all 11 components including FORGE (synthesised from
  MT5 JSON) and ATHENA (self-reported)
- `GET /api/reconciler` — exposes last reconciler run result
- `GET /api/signals` — signal history endpoint (fixed missing route)
- Heartbeat calls in: bridge, sentinel, lens, aegis, listener,
  herald, aurum, reconciler
- `reconciler.py` writes `config/reconciler_last.json` after
  each run for the API to serve
- DEMO/LIVE account type badge in ATHENA header
- Circuit breaker warning banner in ATHENA left column
- Null-safe rendering for all numeric values (shows '—' not crash)
- `aegis` block in `/api/live` — scale_factor, streak, session_pnl
- `components` dict in `/api/live` — latest heartbeat per component
- `reconciler` block in `/api/live` — last reconciler result
- `account_type`, `broker`, `server` in `/api/live` from broker_info.json
- `circuit_breaker` boolean in `/api/live`

### Changed
- `/api/live` — expanded to include all system state in one payload
- `dashboard/app.js` — now fetches `/api/components` and `/api/events`
- `dashboard/app.js` — COMP_STATUS and MOCK_EVENTS removed
- `dashboard/app.js` — ActivityLog accepts `events` and `components`
  as props instead of internal mock state
- `dashboard/app.js` — System Health panel driven by live API data
- `dashboard/app.js` — fallback D object uses null values not zeros
- `athena_api.py` — all file paths now absolute (resolve correctly
  regardless of working directory)

### Fixed
- LENS_MCP_CMD path in .env verified correct
- MT5 symlink at project root verified working
- Path mismatch: config/ files correctly resolved to python/config/
  (WorkingDirectory=python/), MT5/ files resolved to project root
- Missing `@app.route` decorator on `api_signals` function

### Added: Test Framework
- `tests/api/test_live.py` — 12 tests for /api/live
- `tests/api/test_endpoints.py` — health, sessions, performance, mode, events
- `tests/api/test_components.py` — /api/components all 11 present
- `tests/api/test_aurum.py` — AURUM chat endpoint (marked slow)
- `tests/conftest.py` — shared fixtures, base URL config
- `tests/requirements-test.txt` — pytest, requests, python-dotenv
- `tests/playwright.config.js` — Chrome, localhost:7842, HTML report
- `tests/package.json` — Playwright dev dependency
- `tests/ui/test_dashboard.spec.js` — dashboard load, panels
- `tests/ui/test_panels.spec.js` — activity log, trade groups,
  AURUM chat, mode control, LENS panel

### Added: Scripts and Shortcuts

**scripts/ directory (all Python, platform-agnostic):**

| Script | Purpose | Key flags |
|--------|---------|-----------|
| `health.py` | System health check | `--watch` `--json` |
| `test_api.py` | Run pytest API tests | `--file` `--all` `--html` |
| `test_ui.py` | Run Playwright tests | `--headed` `--debug` `--record` `--report` |
| `test_all.py` | Run all tests | `--api` `--ui` `--ci` |
| `logs.py` | View service logs | `--follow` `--errors` `--lines N` |
| `setup_tests.py` | Install test deps | `--check` |

**Makefile targets:**
`make help`, `make health`, `make test`, `make test-api`,
`make test-ui`, `make logs`, `make logs-bridge`, `make start`,
`make stop`, `make restart`, `make setup-tests`

**Shell aliases (added to ~/.zshrc):**
`ss-health`, `ss-watch`, `ss-status`, `ss-test`, `ss-test-api`,
`ss-test-ui`, `ss-test-silent`, `ss-report`, `ss-record`,
`ss-logs`, `ss-logs-bridge`, `ss-logs-listener`, `ss-logs-aurum`,
`ss-logs-errors`, `ss-start`, `ss-stop`, `ss-restart`, `ss`

---

## [1.1.0] — Earlier

### Added
- `RECONCILER` component — hourly position audit
- `trading_sessions` table in SCRIBE
- Session column on all SCRIBE tables
- `FORGE.WriteBrokerInfo()` — writes broker_info.json on startup
- `InputMode` parameter in FORGE EA dialog
- `BRIDGE._on_session_change()` — session transition detection
- `/api/sessions` and `/api/sessions/current` endpoints
- `/api/channel_performance` endpoint
- `/api/aegis_state` endpoint
- Circuit breaker in BRIDGE for MT5 staleness
- Dynamic lot scaling in AEGIS (scale down after losses)
- Session-aligned daily loss reset in AEGIS
- AURUM conversation memory from SCRIBE
- macOS launchd services for all 4 processes
- Linux systemd service files

## [1.0.0] — Initial Release

### Components
- BRIDGE, FORGE, LISTENER, LENS, SENTINEL, AEGIS,
  SCRIBE, HERALD, AURUM, ATHENA

### Core Features
- Signal room following via Telegram (Telethon)
- Claude API parsing of any signal format
- Layered entry: N trades across price zone
- TP1 partial close + SL to breakeven
- TradingView MCP integration (LewisWJackson)
- 5 operating modes: OFF/WATCH/SIGNAL/SCALPER/HYBRID
- SQLite database with 8 tables
- Flask API + React dashboard
