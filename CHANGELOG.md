# SIGNAL SYSTEM — CHANGELOG

## [1.4.0] — 2026-04-06

### FORGE Native Scalper Engine
- New `ScalperMode` input: `NONE` | `BB_BOUNCE` | `BB_BREAKOUT` | `DUAL`
- **BB Bounce** (ADX<20): buy at BB lower + RSI<35, sell at BB upper + RSI>65, H1 trend filter
- **BB Breakout** (ADX>25): breakout above/below BB + RSI + M5/M15 EMA alignment
- ATR-based SL/TP (1.2x for bounce, 1.5x for breakout), multi-TP with partial closes
- Safety guards: session filter (London+NY), spread<25pt, max 2 groups, loss cooldown
- DD event TP tightening: reads sentinel_status.json, tight TP at 0.8x ATR near news
- R:R minimum 1.2 enforced before every native entry
- Writes `scalper_entry.json` for BRIDGE to log to SCRIBE
- Fully backtestable in MT5 Strategy Tester
- `FORGE_SCALPER_MODE` controllable via `.env` → config.json (no reattach needed)

### Shared Scalper Config
- New `config/scalper_config.json` — BB bounce + breakout rules, session filter, safety guards
- Read by FORGE (MQL5) and AURUM (Python) for strategy consistency
- `make scalper-config-sync` copies config to MT5 Common Files

### AUTO_SCALPER Intelligence
- `format_for_aurum()` now includes BB position %, EMA distance, RSI momentum hints
- AUTO_SCALPER prompt includes decision framework (BUY/SELL/PASS criteria)
- BB squeeze detection (M5 BB range < 1.5x ATR = breakout imminent)
- AURUM context includes scalper_config.json parameters for consistency with FORGE

### Live Floating P&L on Dashboard
- Group tiles show real-time floating P&L from MT5 `open_positions[]` (3s refresh)
- Individual position boxes show entry price + per-position P&L
- Gold `LIVE` badge on groups with active MT5 positions
- Source badges: cyan `FORGE` / gold `AURUM` / orange `SIGNAL`

### BRIDGE Integration
- `_check_forge_scalper_entry()` reads scalper_entry.json from FORGE
- Native scalper trades logged to SCRIBE with `source=FORGE_NATIVE_SCALP`
- Herald Telegram alerts for native scalper entries with setup type + indicators

### Bug Fixes
- AURUM welcome message no longer stuck on "waiting for live data" after page load
- `_normalize_aurum_open_trade` method signature restored after edit corruption
- `AUTO_SCALPER` added to `contracts/aurum_forge.py` VALID_MODES + JSON Schema

---

## [1.3.1] — 2026-04-06

### SL/TP Hit Logging (trade_closures)
- New `trade_closures` SCRIBE table logs every position closure with full context
- `close_reason` inferred by BRIDGE: `SL_HIT`, `TP1_HIT`, `TP2_HIT`, `TP3_HIT`, `MANUAL_CLOSE`, `RECONCILER`, `UNKNOWN`
- BRIDGE `_infer_close_reason()` compares close price to SL/TP levels ($0.50 tolerance for XAUUSD)
- BRIDGE `_match_tp_stage()` resolves TP1/TP2/TP3 from trade_group record
- HERALD `tp_hit()` and `position_closed()` now called per position on SL/TP detection
- RECONCILER ghost positions logged to `trade_closures` with reason `RECONCILER`
- New API: `GET /api/closures?days=7&limit=50` — recent closures with reason
- New API: `GET /api/closure_stats?days=7` — aggregated SL vs TP hit rates
- `/api/live` extended with `recent_closures` (last 5, 24h) and `closure_stats` (7d)
- New ATHENA dashboard **Closures** tab with color-coded SL/TP tags and summary stat tiles
- `POSITION_MODIFIED` events categorized as TRADE in Activity panel (was hidden in SYSTEM)
- AURUM context includes last 5 closures and 7d SL/TP hit rate stats
- SCRIBE methods: `log_trade_closure()`, `get_recent_closures()`, `get_closure_stats()`, `get_open_positions_by_group()`
- Tab bar compacted for 5-tab fit; group position grid boxes reduced
- AURUM chat textarea auto-expands with word wrap (Shift+Enter for newlines)
- Agent.md added (gitignored) for AI tool project context
- Fixed pre-existing em-dash syntax error in scribe.py docstring
- Fixed DDL string split that left component_heartbeats outside the DDL block

### Documentation Updated
- `SKILL.md` — closure queries, closure context in injected state
- `SOUL.md` — trade closure detection knowledge, closure context awareness
- `docs/CLI_API_CHEATSHEET.md` — /api/closures, /api/closure_stats curl examples, SCRIBE closure queries
- `docs/SCRIBE_QUERY_EXAMPLES.md` — trade_closures table + 4 new example queries (#15–#18)
- `docs/DATA_CONTRACT.md` — trade_closures in persistence layer
- `CHANGELOG.md` — this entry

---

## [1.3.0] — 2026-04-06

### AUTO_SCALPER Mode
- New `AUTO_SCALPER` mode — AURUM (Claude) as autonomous decision engine
- BRIDGE polls AURUM every `AUTO_SCALPER_POLL_INTERVAL` (default 120s) with structured multi-TF prompt
- Pre-filters: H1 direction gate, RSI neutral screen, sentinel/max groups, loss cooldown
- AURUM responds with `OPEN_GROUP` JSON or `PASS: <reason>`
- Configurable: `AUTO_SCALPER_LOT_SIZE`, `AUTO_SCALPER_NUM_TRADES`, `AUTO_SCALPER_POLL_INTERVAL`, `AUTO_SCALPER_MAX_GROUPS`
- Dashboard mode button (green, "AURUM auto")

### Multi-Timeframe Indicators (FORGE)
- FORGE now exports `indicators_m5`, `indicators_m15`, `indicators_m30` alongside `indicators_h1`
- Each timeframe: RSI(14), EMA20, EMA50, ATR(14), BB upper/mid/lower, MACD histogram, ADX
- H1 expanded: added BB bands, MACD histogram, ADX (previously only RSI/EMA/ATR)
- New `market_view.py` module — unified MarketView combining FORGE + LENS data
- AURUM context now includes full multi-TF data with bias labels (BULL/BEAR/FLAT)

### Position Tracker (BRIDGE)
- BRIDGE now tracks individual position fills and closes from `market_data.json`
- New positions → `scribe.log_trade_position()` with ticket, magic, direction, lots, entry, SL/TP
- Disappeared positions → `scribe.close_trade_position()` with last-known P&L and estimated pips
- Group auto-rollup: when all positions/pendings gone → `update_trade_group()` with totals
- Seed from SCRIBE on startup to prevent duplicate logging after restarts
- Dedup guard: checks SCRIBE for existing ticket before inserting

### Drawdown Protection
- **Equity DD breaker** (BRIDGE): tracks session peak equity, CLOSE ALL + force WATCH if equity drops `DD_EQUITY_CLOSE_ALL_PCT` (default 3%) from peak. Telegram alert.
- **Floating P&L guard** (AEGIS): blocks new groups if floating loss ≥ `DD_FLOATING_BLOCK_PCT` (default 2%) of balance
- **Loss cooldown** (AUTO_SCALPER): pauses `DD_LOSS_COOLDOWN_SEC` (default 300s) after any position closes at a loss

### AEGIS Enhancements
- **H1 trend hard filter**: rejects BUY when H1 EMA20 < EMA50 (bearish), SELL when bullish. `AEGIS_H1_TREND_FILTER=true`
- **Per-signal `num_trades` override**: signals can include `num_trades` or `trades` (1–20) to override default 8
- **Lot override for AURUM/AUTO_SCALPER**: uses signal's `lot_per_trade` directly instead of risk-based sizing
- All previously hardcoded values now configurable: `AEGIS_MIN_LOT`, `AEGIS_PIP_VALUE_PER_LOT`, `AEGIS_MIN_SL_PIPS`
- `mt5_data` parameter added to `validate()` for H1 trend + floating DD checks

### Explicit Magic Number (SCRIBE)
- `magic_number` column added to `trade_groups` table
- BRIDGE stores `FORGE_MAGIC_BASE + group_id` explicitly (single source of truth)
- Reconciler and ATHENA read stored magic instead of computing `base + id`
- Auto-migration for existing databases
- `update_trade_group_magic()` method added to SCRIBE

### FORGE Bug Fixes
- `ExecuteCloseAll()` now cancels pending orders (limits/stops) in addition to closing filled positions
- Previously only iterated `PositionsTotal()`, missed `OrdersTotal()`

### BRIDGE Bug Fixes
- AURUM CLOSE_ALL now updates SCRIBE groups + clears cache (was missing, only wrote FORGE command)
- `num_trades`/`trades` from AURUM commands now passed through to AEGIS (was silently ignored)
- AURUM dispatch now accepts AUTO_SCALPER as valid effective_mode

### Reconciler Improvements
- FORGE version guard: skips stale-group close if `forge_version` < 1.2.4 (pending_orders not exported before that)
- Uses stored `magic_number` from SCRIBE instead of computing `base + id`

### AURUM Enhancements
- Context now includes full multi-TF indicators (M5/M15/M30/H1) with BB bands, MACD, ADX, EMA levels
- Context includes MT5 H1 ATR with sizing guidance ("use 1.5×ATR for SL")
- SKILL.md: scalping TP distance rules ($2–$5 for TP1, $5–$10 for TP2, never $10+ for scalps)
- SKILL.md: H1 alignment rule (never scalp against H1 EMA direction)
- SKILL.md: AUTO_SCALPER tick response format
- SOUL.md: AUTO_SCALPER role section (decision engine vs rules engine)
- Hot-reload: AURUM re-reads SKILL.md + SOUL.md from disk on every query (no restart needed)

### New Files
- `python/market_view.py` — unified FORGE + LENS market data object
- `docs/CLI_API_CHEATSHEET.md` — curl + python one-liners for all API endpoints

### Mode Persistence Across Restarts
- BRIDGE now restores previous mode from `status.json` on restart (default: enabled)
- `RESTORE_MODE_ON_RESTART=true` (default) — reads saved mode from status.json
- `RESTORE_MODE_ON_RESTART=false` — uses FORGE `requested_mode` or `DEFAULT_MODE` from .env
- Mode changes via API (`POST /api/mode`) write directly to status.json for immediate persistence
- CLI `--mode` from launchd plist only used as fallback when no saved state exists

### TP Split at Order Placement
- FORGE now splits TP targets at open: 75% of positions get TP1, 25% get TP2
- Split ratio controlled by `TP1_CLOSE_PCT` (default 70%)
- When TP1 hits (broker-side): 75% close automatically, remaining positions get SL→BE + TP→TP2
- Comment field shows TP target: `FORGE|G14|0|TP1` or `FORGE|G14|3|TP2`
- No more "all positions close at TP1" problem

### Signal Parser API
- New `POST /api/signals/parse` — test Claude Haiku parser via API without Telegram
- Input: `{"text": "SELL Gold @4691-4701 SL:4706 TP1:4687"}` → returns structured JSON
- Supports ENTRY, MANAGEMENT (CLOSE_ALL, CLOSE_PCT, MODIFY_SL, MODIFY_TP, TP_HIT), and IGNORE

### OpenAPI Spec v1.3.0
- 7 new endpoints added to `schemas/openapi.yaml`
- Management examples expanded with all 9 intents
- Swagger UI at `/api/docs/` fully updated

### Signal Lifecycle (Scalping)
- Signal expiry: `SIGNAL_EXPIRY_SEC=60` — stale signals rejected as EXPIRED
- Pending order timeout: `PENDING_ORDER_TIMEOUT_SEC=120` — unfilled limit orders auto-cancelled after 2min
- Telegram alert `⏰ PENDING EXPIRED` sent when orders timeout
- Full lifecycle: signal → AEGIS → FORGE → fill/timeout → SL/TP → SCRIBE → Telegram close alert

### Scalping-Aware Trend Cascade
- AEGIS trend filter now source-aware with multi-TF cascade
- **SIGNAL source** (channel scalps): M5 → M15 → H1. M5 is primary — if M5 agrees (or is FLAT), trade passes even if H1 disagrees
- **AURUM/AUTO_SCALPER**: H1 → M15 cascade (conservative)
- **SCALPER** (BRIDGE): H1 only (strictest)
- FLAT (EMA20 ≈ EMA50 within $1) counts as agreement — allows entry in either direction
- Replaces the old single-H1 filter that was too strict for scalping signals

### FORGE Reload Make Target
- New `make forge-reload` — compile + restart MT5 + auto-detect if EA loaded
- If FORGE auto-loads: prints ✅ and version. If not: prints reattach instructions
- Note: MT5 on Wine/macOS does NOT reliably auto-restore EAs after restart
- Manual reattach still required in most cases (Wine limitation)

### FORGE Architecture Comments
- Comprehensive architecture overview added to FORGE.mq5 header (50+ lines)
- Documents: data flow, command actions, market data output, TP split, magic numbers
- Section comments on: input parameters, globals, indicator handles, group tracking, symbol matching

### Sentinel Pre-Alert
- New Telegram warning when HIGH-impact event is ≤35min away but guard not yet active
- Message: `⚠️ Guard activating soon! {event} in {min}min`
- Fires with the 10-min adaptive digest cycle

### Sentinel Event Digest (Adaptive)
- SENTINEL sends upcoming HIGH-impact events to Telegram with adaptive timing
- **> 30 min away**: digest every 30 min. **≤ 30 min**: every 10 min. **Guard active**: immediate alerts
- Shows event name, currency, minutes away, and guard status
- Only sends when HIGH-impact events are within 4 hours
- Override interval via `POST /api/sentinel/digest {"interval": 30}` (reverts on restart)

### Telegram Close Alerts
- HERALD now sends `GROUP CLOSED` notifications with P&L summary when groups close
- Fires from both paths: position tracker (SL/TP) and management commands (manual close)
- `trade_group_closed()` and `position_closed()` templates added to HERALD

### Sentinel Override
- New `POST /api/sentinel/override` endpoint — temporarily bypass sentinel news guard
- Configurable duration (60s–3600s), defaults to `SENTINEL_OVERRIDE_DURATION_SEC=600`
- Auto-reverts after timeout — logged as `SENTINEL_OVERRIDE_EXPIRED` in SCRIBE
- BRIDGE handles `SENTINEL_OVERRIDE` action via aurum_cmd.json
- Telegram alert on override and expiry

### Smart Position Closing
- New FORGE commands: `CLOSE_GROUP`, `CLOSE_GROUP_PCT`, `CLOSE_PROFITABLE`, `CLOSE_LOSING`
- Group-targeted: close/partial-close only one group's positions by magic number
- Profit/loss filtering: close only winners or only losers across all groups
- BRIDGE resolves group_id → magic_number via SCRIBE for all group commands
- `POST /api/management` now accepts `group_id` parameter for group-targeted commands
- Dashboard group tile buttons now group-specific (Close Group / Close 70% target the specific group, not all)

### Signal Channels (LISTENER)
- Fixed: channel IDs parsed as integers (was strings → Telethon `ValueError`)
- Signals now logged to SCRIBE in ALL modes (not just SIGNAL/HYBRID) — only dispatch is gated
- New `GET /api/channels` endpoint — configured channels with Telethon-resolved names + signal stats
- New `GET /api/channels/messages` endpoint — recent messages from all channels (cached by LISTENER)
- LISTENER resolves channel names on connect → writes `config/channel_names.json`
- LISTENER caches last 10 messages per channel → `config/channel_messages.json` (refreshes every 5min)
- Dashboard signals tab redesigned: channel name badge on each row, channel filter strip, two-line card layout

### Documentation Updated
- `SOUL.md` — AUTO_SCALPER role, multi-TF context, drawdown protection
- `SKILL.md` — complete context spec, scalping rules, AUTO_SCALPER tick format
- `docs/AEGIS.md` — new guards table, per-signal overrides, DD env vars
- `docs/FORGE_BRIDGE.md` — multi-TF indicators, position tracker, CLI cheat sheet link
- `docs/CLI_API_CHEATSHEET.md` — channel polling commands, all curl examples
- `CHANGELOG.md` — this entry

---

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
