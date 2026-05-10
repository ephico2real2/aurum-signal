# ATHENA API Design Reference

> Source of truth for every HTTP endpoint served by `python/athena_api.py`.
> Update this file whenever a route is added, removed, or its response schema changes.
> See `SKILL.md → ATHENA API Design` for the maintenance protocol.

---

## 1. Flask App Fundamentals

### Entry point

`python/athena_api.py` — started by launchd (`com.signalsystem.athena.plist`), default port 7842.

```bash
python athena_api.py                       # http://127.0.0.1:7842 (default)
ATHENA_HOST=0.0.0.0 python athena_api.py   # bind all interfaces
ATHENA_PORT=8000 python athena_api.py      # custom port
```

### Key file paths (read by routes)

| Variable | Default path | Written by |
|----------|-------------|------------|
| `MARKET_FILE` | `MT5/market_data.json` | FORGE EA (every tick) |
| `MODE_FILE` | `MT5/mode_status.json` | BRIDGE |
| `BROKER_FILE` | `MT5/broker_info.json` | FORGE EA |
| `STATUS_FILE` | `python/config/status.json` | BRIDGE |
| `LENS_FILE` | `python/config/lens_snapshot.json` | LENS |
| `LENS_BRIEF_FILE` | `python/config/lens_brief.json` | LENS |
| `SENTINEL_FILE` | `python/config/sentinel_status.json` | SENTINEL |
| `AURUM_CMD_FILE` | `python/config/aurum_cmd.json` | ATHENA, AURUM |
| `MGMT_FILE` | `python/config/management_cmd.json` | ATHENA |
| `RECON_FILE` | `config/reconciler_last.json` | RECONCILER |
| `SCALPER_CONFIG_FILE` | `config/scalper_config.json` | operator / make scalper-env-sync |
| `GATE_DIAGNOSTICS_LAST_FILE` | `python/config/gate_diagnostics_last.json` | BRIDGE |

All paths resolve relative to the project root — safe regardless of launch directory.

### CORS

`flask_cors.CORS(app)` — all origins, all methods. The service is local-only by default.

### Authentication

| Env var | Scope | Header |
|---------|-------|--------|
| `ATHENA_SECRET` | All state-mutating routes (POST/PUT) | `X-Athena-Token: <secret>` |
| `ATHENA_SCRIBE_QUERY_SECRET` | `POST /api/scribe/query` | `Authorization: Bearer <secret>` |
| `ATHENA_AURUM_EXEC_SECRET` | `POST /api/aurum/exec` | `Authorization: Bearer <secret>` |

All are empty string by default (open). Unauthenticated mutations return `403 {"error":"forbidden"}` when a secret is set.

### Swagger UI

Interactive docs at `http://localhost:7842/api/docs/`. Spec served at `GET /api/openapi.yaml` from `schemas/openapi.yaml`.

### Static file serving (React SPA)

`DASHBOARD_DIR` env (default `dashboard/`). Catch-all route: known files served directly, everything else → `index.html` (React router). Source: `dashboard/app.js` — single CDN-React JSX bundle, no build step.

---

## 2. Data Flow

```
FORGE EA (MT5)                                  LENS (lens.py)
  └─ market_data.json (every tick)               └─ lens_snapshot.json
  └─ broker_info.json                            └─ lens_brief.json
  └─ mode_status.json
                                                SENTINEL
SCRIBE (aurum_intelligence.db)                  └─ sentinel_status.json
  └─ trade_groups / trade_positions
  └─ trade_closures / signals_received           BRIDGE writes every ~5s
  └─ component_heartbeats / system_events        └─ status.json (mode, session)
  └─ trading_sessions / aurum_conversations
  └─ regime_snapshots / regime_transitions      BRIDGE syncs tester every 60s
                                                └─ aurum_tester.db
athena_api.py (Flask, port 7842)                    ├─ aurum_tester_runs
  ├─ reads all JSON files above                     ├─ forge_signals
  ├─ queries aurum_intelligence.db                  └─ forge_journal_trades
  ├─ queries aurum_tester.db
  └─ serves JSON → React dashboard (dashboard/app.js)
       └─ polls /api/live every ~10s
       └─ polls /api/backtest/* every 30s (when backtest tab open)
```

---

## 3. Endpoint Reference

All endpoints return `Content-Type: application/json` unless noted. Base: `http://localhost:7842`.

### 3.1 Health · `GET /api/health`

Liveness check. No auth, no DB. Returns `{"status":"ok","timestamp":"...","mt5_connected":bool,...}`.

---

### 3.2 Live Dashboard · `GET /api/live`

**The primary endpoint** — single large JSON object polled every ~10s by the React app. Also records an ATHENA heartbeat to SCRIBE on each call.

**Sources:** `MARKET_FILE`, `STATUS_FILE`, `LENS_FILE`, `BROKER_FILE`, `SENTINEL_FILE`, `RECON_FILE`, `SCALPER_CONFIG_FILE` + SCRIBE (trade_positions, component_heartbeats, trade_groups, performance, closures, regime).

**Key response sections:**

| Section | Description |
|---------|-------------|
| `mode`, `effective_mode`, `session`, `cycle` | BRIDGE state |
| `account` | balance, equity, margin_level |
| `execution` | bid/ask/spread (usable=false when market_data.json stale) |
| `tradingview` | TradingView indicators from LENS |
| `open_positions` / `pending_orders` | current MT5 positions and orders |
| `open_groups` | SCRIBE groups whose FORGE magic appears in MT5 exposure |
| `open_groups_queued` | groups SCRIBE has logged but FORGE hasn't placed yet |
| `performance` | rolling 7d stats |
| `recent_closures` | last 5 closed trades |
| `aegis` | win/loss streak, scale_factor, session_pnl |
| `regime` | current regime label + confidence + config |
| `scalper_gates` | OsMA gate state (require_macd_sell, osma_m5, sell_osma_pass, ...) |
| `components` | BRIDGE, FORGE, LISTENER, etc. heartbeats |
| `sentinel` | next news event, time to event |
| `reconciler` | last reconciliation result |

**UI panels:** all dashboard panels.

---

### 3.3 Regime · `/api/regime/*`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/regime/current` | Current label, confidence, config, 24h transitions, 30d P&L |
| GET | `/api/regime/history?limit=120&hours=72` | Regime snapshot history |
| GET | `/api/regime/performance?days=30` | P&L breakdown by regime label |

**DB tables:** `regime_snapshots`, `regime_transitions` (aurum_intelligence.db).

---

### 3.4 AUTO_SCALPER · `GET /api/autoscalper/conditions`

Evaluates BRIDGE pre-filter conditions for AUTO_SCALPER mode.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `responses` | 3 | Recent AURUM AUTO_SCALPER responses to include |
| `h1_flat_threshold` | 1.0 | EMA20–EMA50 diff threshold for "flat" H1 |
| `upper_bb_threshold_pct` | 90.0 | Percentile for "near upper BB" |

**DB tables:** `aurum_conversations` (for recent responses).

---

### 3.5 Signal Gate Diagnostics · `GET /api/signal_gate/diagnostics`

Last BRIDGE gate snapshot. Only populated when `GATE_DIAGNOSTICS_ENABLED=1`. Returns `404` when file absent.

---

### 3.6 Components · `/api/components`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/components` | Full system health grid (11 components) |
| GET | `/api/components/heartbeat` | Lists valid heartbeat fields |
| POST | `/api/components/heartbeat` | Record a component heartbeat |

**POST body:** `{"component":"BRIDGE","status":"OK","note":"...","mode":null,"last_action":null,"error_msg":null}`

**DB tables:** `component_heartbeats`.

---

### 3.7 Reconciler · `GET /api/reconciler`

Last reconciler run from `config/reconciler_last.json`. Returns `{"status":"NEVER_RUN",...}` if absent.

---

### 3.8 AURUM · `/api/aurum/*`

| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/aurum/ask` | `{"query":"..."}` | Natural-language query to AURUM AI |
| POST | `/api/aurum/exec` | `{"action":"SCRIBE_QUERY","sql":"..."}` | AEB action (optional secret auth) |

AURUM may emit commands to `aurum_cmd.json` as part of `ask` responses; BRIDGE processes them on the next tick.

---

### 3.9 Mode · `/api/mode`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/mode` | Current mode from `status.json` |
| POST | `/api/mode` | Queue mode change via `aurum_cmd.json` → BRIDGE |

**Valid modes:** `OFF`, `WATCH`, `SIGNAL`, `SCALPER`, `HYBRID`, `AUTO_SCALPER`

**POST body:** `{"mode":"SIGNAL"}`

BRIDGE is the source of truth. ATHENA queues the request; BRIDGE applies it on the next tick.

---

### 3.10 Management Commands · `POST /api/management`

Writes `management_cmd.json` (validated against `schemas/files/management_cmd.schema.json`). BRIDGE reads and forwards to FORGE.

**Valid intents:**

| Intent | Extra fields | Description |
|--------|-------------|-------------|
| `CLOSE_ALL` | — | Close all positions + pending orders |
| `MOVE_BE` | — | Move all SL to breakeven |
| `CLOSE_PCT` | `pct` (0–100, default 70) | Close % of all positions |
| `CLOSE_GROUP` | `group_id` | Close one group |
| `CLOSE_GROUP_PCT` | `group_id`, `pct` | Close % of one group |
| `CLOSE_PROFITABLE` | — | Close winning positions only |
| `CLOSE_LOSING` | — | Close losing positions only |
| `MODIFY_SL` | `sl` (price) | Modify stop loss |
| `MODIFY_TP` | `tp` (price) | Modify take profit |

---

### 3.11 Sessions · `/api/sessions`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/sessions?limit=20` | Session history |
| GET | `/api/sessions/current` | Active session |

**DB tables:** `trading_sessions`.

---

### 3.12 Sentinel · `/api/sentinel/*`

| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/sentinel/override` | `{"duration":300,"reason":"..."}` | Bypass news guard (60–3600s) |
| POST | `/api/sentinel/digest` | `{"interval":30}` | Override digest interval (30–3600s) |

---

### 3.13 Channels · `/api/channel*`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/channels` | Configured Telegram channels + SCRIBE signal stats |
| GET | `/api/channels/messages` | Recent message cache from LISTENER |
| GET | `/api/channel_performance?days=30` | P&L per channel |

**DB tables:** `signals_received` (joined with `trade_groups` for channel_performance).

---

### 3.14 AEGIS · `GET /api/aegis_state`

Win/loss streak from last 10 closed trades. Full state also embedded in `/api/live → aegis`.

**DB tables:** `trade_positions` (last 10 closed).

---

### 3.15 Signals · `/api/signals`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/signals?limit=20&days=7&session=current&stats=0` | Signal history |
| POST | `/api/signals/parse` | Test signal parser without Telegram |

**DB tables:** `signals_received`.

---

### 3.16 Trade Closures · `/api/closures`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/closures?limit=50&days=7` | Recent SL/TP closures |
| GET | `/api/closure_stats?days=7` | Aggregated SL/TP rates |

**DB tables:** `trade_closures`.

---

### 3.17 Performance · `/api/performance` and `/api/pnl_curve`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/performance?days=7` | Rolling win rate / P&L summary |
| GET | `/api/pnl_curve?days=1` | Cumulative P&L data points for chart |

**DB tables:** `trade_positions` (performance), `trade_closures` (pnl_curve).

---

### 3.18 SCRIBE Query · `POST /api/scribe/query`

Run a raw SELECT on `aurum_intelligence.db`. Non-SELECT is blocked. Optional auth via `ATHENA_SCRIBE_QUERY_SECRET`.

**Body:** `{"sql":"SELECT id FROM trade_groups ORDER BY id DESC LIMIT 10"}`

**Response:** `{"rows":[...],"count":10,"truncated":false,"max_rows":500}`

---

### 3.19 Events · `/api/events`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/events?limit=200` | Recent system events |
| GET | `/api/events/export?limit=5000` | NDJSON download (oldest-first) |

**DB tables:** `system_events`.

---

### 3.20 Backtest (aurum_tester.db) · `/api/backtest/*`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/backtest/runs` | All registered tester runs with summary stats |
| GET | `/api/backtest/run/<aurum_run_id>` | Full detail: meta, performance, gates, TAKEN entries, P&L curve |

**DB:** `aurum_tester.db` (separate from live SCRIBE). Tables: `aurum_tester_runs`, `forge_signals`, `forge_journal_trades`.

**Key response fields for `/api/backtest/run/<id>`:**

| Field | Description |
|-------|-------------|
| `performance.total_pnl` | Sum of all closing deal profits |
| `performance.win_rate` | wins/(wins+losses)×100 |
| `signals.open_at_end` | TAKEN groups with no closing deal = still open at backtest end |
| `taken[].trade_outcome` | TP1/TP2/TP3/TP4/SL/WIN/OPEN (derived from trade comments) |
| `taken[].pnl` | Per-group P&L including base magic legs |
| `gates[]` | Top 15 skip gate reasons by count |
| `pnl_curve[]` | `{t: unix_ts, pnl: cumulative}` — one point per closing deal |

**Sync recovery:** if `aurum_tester.db` has fewer signals than the source tester DB, BRIDGE auto-resets `synced=0` on missing rows and re-syncs within 60s. See `docs/DATABASE_ARCHITECTURE.md`.

---

### 3.21 Legend Endpoints

| Method | Path | Source file | Description |
|--------|------|------------|-------------|
| GET | `/api/gate_legend` | `config/gate_legend.json` | gate_reason → {label, explanation, category} |
| GET | `/api/indicator_legend` | `config/indicator_legend.json` | acronym → {full_name, forge_usage, ...} |

Both are cached in-process (`_gate_legend_cache`, `_indicator_legend_cache`). Cache clears on restart.

**How to add a new gate:** Add an entry to `config/gate_legend.json`, restart Athena — no code change.

---

### 3.22 TradingView Brief · `GET /api/brief`

Full LENS brief payload from `config/lens_brief.json`. Returns `404` when LENS hasn't produced a brief yet.

---

### 3.23 Web Search · `GET /api/search?q=<query>&n=5`

On-demand search used by AURUM. Returns `400` if `q` missing.

---

### 3.24 OpenAPI · `GET /api/openapi.yaml` and `GET /api/docs/`

Serves `schemas/openapi.yaml` and Swagger UI. Always available regardless of auth.

---

## 4. Error Handling Summary

| Concern | Behaviour |
|---------|-----------|
| JSON file read failure | `_read_json()` returns `{}` — routes degrade gracefully |
| MT5 quote stale | `execution.usable=false`, `execution.stale=true` in `/api/live` |
| Backtest run not found | `404 {"error":"aurum_run_id=N not found"}` |
| Gate/indicator legends missing | `500 {"error":"..."}` if JSON file absent |
| Management schema invalid | `400 {"error":"validation_failed","details":[...]}` |
| Non-SELECT SCRIBE query | `400 {"error":"..."}` |

---

## 5. UI Panel → Endpoint Mapping

| UI Panel | Endpoint(s) |
|----------|-------------|
| Left sidebar: Account / Balance / Mode | `/api/live` |
| Left sidebar: System Health | `/api/components` |
| Centre: Open Groups | `/api/live → open_groups` |
| Centre: Closures tab | `/api/closures`, `/api/closure_stats` |
| Centre: Signals tab | `/api/signals` |
| Centre: Performance tab | `/api/performance`, `/api/pnl_curve` |
| Centre: Backtest — run selector | `/api/backtest/runs` |
| Centre: Backtest — detail panel | `/api/backtest/run/<id>`, `/api/gate_legend`, `/api/indicator_legend` |
| Centre: Indicators tab | `/api/indicator_legend` |
| Right panel: FORGE quote | `/api/live → execution` |
| Right panel: TradingView indicators | `/api/live → tradingview` |
| Right panel: OsMA gate | `/api/live → scalper_gates` |
| Right panel: AUTO_SCALPER | `/api/autoscalper/conditions` |
| Right panel: Regime Engine | `/api/regime/current` |
| AURUM chat widget | `/api/aurum/ask` |
| Mode buttons | `GET/POST /api/mode` |
| Management buttons | `POST /api/management` |
| Sentinel override | `POST /api/sentinel/override` |
| Signal channels | `/api/channels`, `/api/channel_performance` |

---

## 6. DB Tables Quick Reference

### aurum_intelligence.db

| Table | Key endpoints |
|-------|-------------|
| `trade_groups` | `/api/live`, `/api/scribe/query` |
| `trade_positions` | `/api/live`, `/api/performance`, `/api/aegis_state` |
| `trade_closures` | `/api/closures`, `/api/closure_stats`, `/api/pnl_curve` |
| `signals_received` | `/api/signals`, `/api/channels`, `/api/channel_performance` |
| `component_heartbeats` | `/api/components`, `/api/live` |
| `system_events` | `/api/events` |
| `trading_sessions` | `/api/sessions` |
| `aurum_conversations` | `/api/autoscalper/conditions` |
| `regime_snapshots` | `/api/regime/*` |
| `regime_transitions` | `/api/regime/current` |

### aurum_tester.db

| Table | Key endpoints |
|-------|-------------|
| `aurum_tester_runs` | `/api/backtest/runs`, `/api/backtest/run/<id>` |
| `forge_signals` | `/api/backtest/run/<id>` — gate breakdown + TAKEN list |
| `forge_journal_trades` | `/api/backtest/run/<id>` — outcomes + P&L |
