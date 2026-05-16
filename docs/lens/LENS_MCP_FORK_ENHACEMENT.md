# LENS MCP — Fork & Enhancement Plan

**Status** (2026-05-16): F1 shipped + F2 PR open ([upstream #42](https://github.com/LewisWJackson/tradingview-mcp-jackson/pull/42)) + F3 committed local on `feat/streamable-http` ([fork branch](https://github.com/ephico2real2/tradingview-mcp-aurum/tree/feat/streamable-http)) + F4 committed local on `feat/cdp-reconnect` ([fork branch](https://github.com/ephico2real2/tradingview-mcp-aurum/tree/feat/cdp-reconnect)) + **F5 SHIPPED live** (launchd tv-mcp daemon + Python HTTP client cutover, signal_system commit `da08e72`). F6 + F7 designed (post-QuestDB containerization + shared-services moduliths) — see §F6 + §F7. Awaiting PR #42 maintainer feedback before upstream submission of F3/F4.
**Owner**: operator (`ephico2real2`)
**Created**: 2026-05-16
**Companion doc**: [`docs/LENS_MCP_INTEGRATION.md`](../LENS_MCP_INTEGRATION.md) (current architecture as of pre-fork)

## Goal

Replace the dual-MCP-process / dual-CDP-attachment pattern (one MCP per Python consumer — LENS + AURUM) with a **single MCP service shared across all consumers**, write-correct under concurrent access, owned by us, with three enhancements that are also strong upstream PR candidates.

End-state shape (per [`docs/LENS_MCP_INTEGRATION.md` § Stack diagram]):

```
TradingView Desktop (Chrome CDP :9222)
              ▲
              │ 1× CDP attachment (was: 2×)
              │
      ┌───────┴───────┐
      │  Our MCP fork │   one launchd-managed Node process
      │  (HTTP +      │   listens on localhost:NNNN
      │   stdio,      │
      │   write-mutex,│
      │   CDP-reconn) │
      └───┬───────┬───┘
          │       │  Streamable HTTP (multi-client)
          │       │
        LENS    AURUM
```

## Repo layout (planned)

| Path | Role |
|---|---|
| `https://github.com/ephico2real2/tradingview-mcp-aurum` (operator to create) | Our fork — public so we can PR back to upstream |
| `/Users/olasumbo/tradingview-mcp-aurum/` | Local clone of the fork. Sibling to `/Users/olasumbo/tradingview-mcp-jackson/` until the cutover; both can coexist. |
| `/Users/olasumbo/tradingview-mcp-jackson/` | Kept around as the upstream-clean reference. Used only for `git diff fork..upstream` sanity checks. Eventually removed. |
| `/Users/olasumbo/signal_system/Makefile` `LENS_MCP_DIR` | Currently `$(HOME)/tradingview-mcp-jackson`. Becomes `$(HOME)/tradingview-mcp-aurum` after F1. |
| `/Users/olasumbo/signal_system/Makefile` clone URL | Currently `https://github.com/LewisWJackson/tradingview-mcp-jackson.git`. Becomes our fork URL after F1. |

We **do not** make the fork a git submodule of `signal_system` — keeps the fork's git history clean for upstream PRs and avoids the well-known submodule UX pain.

## Phase plan

Each phase is independently reversible. Don't start F2 until F1 lands; everything after F2 can ship in any order.

### F1 — Fork setup and Makefile cutover (≤30 min, ours) ✅ SHIPPED 2026-05-16

**Goal**: clone our fork locally + point `make update-lens-mcp` at it. Zero functional change to the MCP itself; the fork at HEAD is byte-identical to upstream.

Steps:
1. Operator forks `LewisWJackson/tradingview-mcp-jackson` on GitHub to `ephico2real2/tradingview-mcp-aurum` (or chosen name).
2. Operator provides the fork URL to this session.
3. We `git clone <fork-url> /Users/olasumbo/tradingview-mcp-aurum`.
4. We update `signal_system/Makefile`:
   - `LENS_MCP_DIR = $(HOME)/tradingview-mcp-aurum`
   - Clone URL in the `update-lens-mcp` target → our fork.
5. Run `make update-lens-mcp` against the new path to validate (symlink, npm install, server-start probe).
6. Run `make clean-mcp-git-stash` against the new path (validates the existing target works with the renamed dir).
7. Run `make health` to confirm LENS still polls successfully.

Acceptance:
- `make update-lens-mcp` reports `Path: /Users/olasumbo/tradingview-mcp-aurum/src/server.js`.
- `/api/live` `tradingview_age_sec < 60` after a poll cycle.
- `git -C ~/tradingview-mcp-aurum log --oneline -1` matches upstream HEAD.

Rollback: revert the Makefile diff, re-clone upstream. No data loss possible.

### F2 — Write-tool async mutex (1–2h, ours then upstream PR) ✅ SHIPPED 2026-05-16

**Goal**: serialize write tool handlers inside the MCP so concurrent HTTP/stdio clients can't race on shared Chrome state. Read tools stay unblocked.

Design:
- Add `async-mutex` (or in-tree minimal Promise-based mutex) to `src/connection.js`.
- Export `evaluateWrite(expression, opts)` that runs under the mutex; existing `evaluate(...)` stays unlocked for reads.
- Classify every tool in `src/core/` as READ or WRITE. Concrete starting catalog:
  - **READ** (no mutex): `chart_get_state`, `quote_get`, `data_get_ohlcv`, `data_get_study_values`, `data_get_pine_*`, `capture_screenshot`, `symbol_info`, `symbol_search`, `chart_get_visible_range`, `pane_list`, `tab_list`, `pine_get_*`, `health_*`.
  - **WRITE** (mutex): `chart_set_symbol`, `chart_set_timeframe`, `chart_set_type`, `chart_manage_indicator`, `chart_set_visible_range`, `chart_scroll_to_date`, `indicator_set_inputs`, `draw_shape`, `alert_create`, `alert_delete`, `pane_set_layout`, `pane_focus`, `pane_set_symbol`, `tab_new`, `tab_close`, `tab_switch`, `pine_set_source`, `pine_smart_compile`, `replay_*`, `batch_run`.
  - Audit during implementation — anything that calls `evaluate(...)` with a state-mutating JS expression goes in the WRITE bucket.
- Add a test that fires 5 concurrent `chart_set_symbol` calls and asserts the final state is exactly one of the requested symbols (proves serialization, no torn state).

Files touched:
- `src/connection.js` — add mutex + `evaluateWrite()`.
- `src/core/chart.js`, `src/core/drawing.js`, `src/core/alerts.js`, `src/core/pane.js`, `src/core/tab.js`, `src/core/pine.js`, `src/core/replay.js`, `src/core/batch.js`, `src/core/indicators.js` — swap `evaluate(...)` → `evaluateWrite(...)` in write paths.
- `package.json` — add `async-mutex` dep (or commit the in-tree minimal impl, ~15 lines, no dep).
- New test under `tests/` (if the fork already has tests) or `tests/concurrency.test.js`.

Acceptance:
- 5 concurrent `chart_set_symbol` calls land in arrival order; final state matches the last one.
- Read tools run concurrently with writes without blocking (assert via timing test).
- No regression on existing tool behaviour.

Upstream PR: yes — small, defensive, generic. Open an issue first describing the race, link [MCP spec on Streamable HTTP multi-client semantics](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), propose the mutex approach. Get maintainer sign-off before opening the PR.

### F3 — Native Streamable HTTP transport (2–3h, ours then upstream PR)

**Goal**: add Streamable HTTP transport alongside stdio. Drops the need for `mcp-proxy`.

Design:
- Add `StreamableHTTPServerTransport` from `@modelcontextprotocol/sdk` to `src/server.js`.
- Env-flag selection: `MCP_TRANSPORT=stdio` (default, current behaviour) or `MCP_TRANSPORT=http`.
- HTTP port via `MCP_HTTP_PORT` (default `8765`).
- Bind to `127.0.0.1` only (no external exposure — single-machine deployment).
- Session affinity via `Mcp-Session-Id` header per spec.
- Handle 404 on stale session: client re-initialises.

Files touched:
- `src/server.js` — branch on `MCP_TRANSPORT`.
- `package.json` — already has `@modelcontextprotocol/sdk`; verify version supports Streamable HTTP server transport.
- `README.md` — document the new transport mode.
- Optional: new `cli` entry point that exposes `--transport stdio|http --port N`.

Acceptance:
- `MCP_TRANSPORT=http MCP_HTTP_PORT=8765 node src/server.js` starts an HTTP listener.
- `curl -X POST http://127.0.0.1:8765/mcp` with a valid initialise + tool call returns the expected response.
- Stdio mode unchanged (regression-tested with our `python/mcp_client.py` stdio path).

Upstream PR: yes — pure transport feature, MCP-spec aligned. Probably wants design discussion before code (worth opening an issue).

### F4 — CDP reconnect-on-disconnect hardening (1h, ours then upstream PR)

**Goal**: handle Chrome restart cleanly. Current `getClient()` does a liveness ping but doesn't subscribe to `client.on('disconnect')` — a lost connection only surfaces on the next tool call, often as a confusing error.

Design:
- In `src/connection.js`, after `await CDP(...)`, register `client.on('disconnect', () => { client = null; targetInfo = null; })`.
- Add a watchdog: every N seconds, ping the client; reconnect if dead.
- Expose connection state via a new `health_cdp_status` tool (returns `{ connected: bool, target_id, last_ping_ms_ago }`). Useful for `make health` integration.

Files touched:
- `src/connection.js` — disconnect handler + watchdog.
- `src/core/health.js` — new `cdp_status` tool.
- `src/tools/health.js` — register the new tool.

Acceptance:
- Kill Chrome while MCP is running → MCP auto-reconnects on Chrome restart within N seconds.
- `health_cdp_status` reports accurate state.

Upstream PR: yes — pure robustness fix, every user benefits.

### F5 — launchd service + Python HTTP client (≤2h, ours only)

**Goal**: deploy the MCP as a launchd-managed service; switch `python/mcp_client.py` to HTTP transport.

Steps (signal_system side):
1. Render `services/macos/com.signalsystem.tv-mcp.plist.tmpl`:
   - `ProgramArguments`: `["node", "/Users/olasumbo/tradingview-mcp-aurum/src/server.js"]`.
   - `EnvironmentVariables`: `MCP_TRANSPORT=http`, `MCP_HTTP_PORT=8765`.
   - `KeepAlive`: `{ "Crashed": true }`.
   - `StandardOut/Error`: signal_system logs dir.
2. Wire into the service-render pipeline (`services/macos/render_plists.py` or equivalent — needs lookup).
3. Add Make targets: `start-mcp`, `stop-mcp`, `reload-mcp`, `restart-mcp`, `mcp-status`, `mcp-logs`. Pattern-match the existing bridge/aurum targets.
4. Add `MCPHttpSession` class to `python/mcp_client.py` alongside `MCPSession` (keep stdio path for tests). Same `call()` API surface so consumers are agnostic.
5. Flip `python/lens.py` to HTTP behind `LENS_MCP_TRANSPORT=http` env (default `http` after stable).
6. Flip `python/aurum.py` to HTTP.
7. Run `make system-down && make system-up` — verify all four services + MCP daemon come up cleanly.
8. `make health` should show MCP daemon healthy.

Acceptance:
- `launchctl list | grep tv-mcp` → loaded + PID.
- `curl http://127.0.0.1:8765/health` (or equivalent) returns 200.
- LENS poll succeeds via HTTP — no stdio subprocess spawned per cycle.
- AURUM tool calls succeed via HTTP.
- Killing the Node MCP process → launchd respawns within seconds.

Rollback: set env back to `LENS_MCP_TRANSPORT=stdio`, unload the launchd plist. Bridge/Aurum revert to per-process stdio MCPSession.

### F6 — Containerize the daemon-plus-services stack (post-QuestDB, ours only)

**Goal**: replace launchd + the Makefile service stack with `docker-compose` (or `podman-compose`) so the whole runtime is portable, reproducible, and version-pinned. Single-host single-replica — no horizontal scaling claim.

**Hard prerequisites — do NOT start F6 before these**:

1. **QuestDB migration** (per [`QUESTDB_EVALUATION.md §12`](../QUESTDB_EVALUATION.md)) — scribe writes go to QuestDB ILP, dashboard queries hit QuestDB HTTP. Removes the SQLite shared-volume requirement and the macOS-Docker-Desktop `flock()` flakiness concern.
2. **F5 shipped** (✅ done 2026-05-16) — gives us the HTTP service contract that compose needs.

**What ships under F6**:

- `Dockerfile` for the signal_system Python services (bridge / aurum / athena share one image; entrypoint args differ per service).
- `Dockerfile` for the MCP daemon (uses the `tradingview-mcp-aurum` fork directory; node:lts base; copies src/ + node_modules).
- `docker-compose.yml` at repo root: 5 services (tv-mcp, bridge, aurum, athena, questdb), 2 named volumes (questdb-data, parquet-archive), 1 default docker network.
- New Make targets: `compose-up`, `compose-down`, `compose-logs SERVICE=…`, `compose-build`. The existing launchd targets stay for the legacy path until F6 is the default.
- `.env.example` updates: containerized paths (`MT5_COMMON_FILES`), service-name hostnames (`MCP_HTTP_HOST=tv-mcp`, `QUESTDB_HOST=questdb`).
- Path translation: bridge.py reads `MT5_COMMON_FILES_DIR` env (already env-overridable, or one-line change) instead of hardcoded Wine path.

**Host constraints (irreducible)**:

- TradingView Desktop runs **native on the host** (no headless / server-side equivalent). The tv-mcp container reaches it via `CDP_HOST=host.docker.internal` on macOS/Windows, or `--network host` on Linux. F4's `CDP_HOST` env override (already shipped) supports this without code change.
- MT5 Desktop runs **native on the host**. The bridge container reads/writes the Common Files dir via bind mount (`/mt5` inside container ↔ host MT5 Common Files path).

**End-state diagram**:

```
┌─── Host (Windows or macOS) ────────────────────────┐
│                                                    │
│  TradingView Desktop ── CDP :9222                  │
│  MetaTrader 5 Desktop ── Common Files/             │
│                          │  ▲                      │
│                          │  │ bind mount           │
└──────────────────────────│──│──────────────────────┘
                           ▼  │
┌─── Docker network "signal-net" ────────────────────┐
│                                                    │
│  ┌──────────┐  ┌─────────┐  ┌────────┐ ┌────────┐ │
│  │ tv-mcp   │  │ bridge  │  │ aurum  │ │ athena │ │
│  │ :8765    │←─│         │←─│        │ │ :7842  │ │
│  │ MCP HTTP │  │         │  │        │ │        │ │
│  └────┬─────┘  └────┬────┘  └───┬────┘ └───┬────┘ │
│       │ host.docker│             │          │     │
│       │ .internal  │  ILP +HTTP  │          │     │
│       │ :9222      ▼  reads      ▼          ▼     │
│       │       ┌──────────────────────────────┐    │
│       │       │ QuestDB (hot store)          │    │
│       │       │ :9009 ILP / :9000 web        │    │
│       │       └──────────────────────────────┘    │
└───────┘                                            │
                                                     │
        bind mount: parquet-archive (cold path)      │
        bind mount: MT5 Common Files (host)          │
```

#### Full production compose (detailed)

Single-host, single-replica, designed for the macOS/Windows-developer-workstation + Linux-server cases. Path: `docker-compose.yml` at the signal_system repo root.

```yaml
# docker-compose.yml — signal_system runtime
# Replaces launchd + the Makefile service stack with a single declarative manifest.
# Single-replica per service (F2 mutex is per-process; horizontal scaling needs
# a distributed lock — out of scope here). Designed for one Chrome target +
# one MT5 instance on the host.

name: signal-system

# ─── Networks ────────────────────────────────────────────────────────
# One bridge network for inter-service DNS. Container names resolve to
# their IPs automatically: `http://tv-mcp:8765`, `http://athena:7842`,
# `http://questdb:9000`, etc.
networks:
  signal-net:
    driver: bridge

# ─── Volumes ─────────────────────────────────────────────────────────
# Named volumes (kernel-managed, fast, container-portable):
#   - questdb-data: hot store, time-series + relational tables.
#   - parquet-archive: cold store, daily-partitioned zstd archives.
#   - aurum-state: persistent AURUM state (telegram sessions, prompt cache).
# Host bind mounts (host-path → container-path, defined per-service):
#   - MT5 Common Files (read+write, ${MT5_COMMON_FILES} from .env)
#   - FORGE journal dir (read-only, for bridge to sync into QuestDB)
volumes:
  questdb-data:
  parquet-archive:
  aurum-state:

# ─── Services ────────────────────────────────────────────────────────
services:

  # ── QuestDB (hot store) ──────────────────────────────────────────
  questdb:
    image: questdb/questdb:8.1.0          # pin specific version; bump deliberately
    container_name: signal-questdb
    restart: unless-stopped
    networks: [ signal-net ]
    ports:
      - "127.0.0.1:9000:9000"             # web console — localhost only
      - "127.0.0.1:9009:9009"             # ILP TCP for ingest — localhost only
      - "127.0.0.1:8812:8812"             # PostgreSQL wire protocol — for SQL queries
    volumes:
      - "questdb-data:/var/lib/questdb"
    environment:
      QDB_CAIRO_COMMIT_LAG: "1000"        # write batching
      QDB_PG_USER: signal                 # change if exposing PG port
      QDB_PG_PASSWORD: "${QUESTDB_PG_PASSWORD:-signal_local}"
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:9000/exec?query=select+1 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
    logging:
      driver: json-file
      options: { max-size: 10m, max-file: "3" }

  # ── tv-mcp (Streamable HTTP MCP daemon) ──────────────────────────
  # Builds from sibling repo: ../tradingview-mcp-aurum
  # F2 mutex + F3 HTTP transport + F4 reconnect all live here.
  tv-mcp:
    build:
      context: ../tradingview-mcp-aurum
      dockerfile: Dockerfile
    image: signal/tv-mcp:local
    container_name: signal-tv-mcp
    restart: unless-stopped
    networks: [ signal-net ]
    ports:
      - "127.0.0.1:8765:8765"             # MCP endpoint — localhost only
    environment:
      MCP_TRANSPORT: http
      MCP_HTTP_HOST: "0.0.0.0"            # bind container interface, not loopback
      MCP_HTTP_PORT: "8765"
      MCP_HTTP_PATH: "/mcp"
      MCP_TRACE_FILE: "/var/log/mcp/trace.log"   # mounted volume for tracer
      CDP_HOST: "host.docker.internal"    # macOS/Windows escape; on Linux use --network host
      CDP_PORT: "9222"
      CDP_WATCHDOG_INTERVAL_MS: "30000"
    volumes:
      - "./logs/mcp:/var/log/mcp"         # tracer + stdout/stderr surface
    # macOS / Windows Docker Desktop: host.docker.internal works out of box.
    # Linux: uncomment the extra_hosts line OR run with `network_mode: host`.
    extra_hosts:
      - "host.docker.internal:host-gateway"
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:8765/health || exit 1"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 5s
    logging:
      driver: json-file
      options: { max-size: 10m, max-file: "5" }

  # ── bridge (orchestrator + LENS host) ────────────────────────────
  # Reads MT5 Common Files; writes back commands; syncs FORGE journal
  # into QuestDB; runs LENS polling loop (which goes through tv-mcp).
  bridge:
    build:
      context: .
      dockerfile: docker/Dockerfile.python
    image: signal/bridge:local
    container_name: signal-bridge
    restart: unless-stopped
    networks: [ signal-net ]
    command: ["python", "python/bridge.py", "--mode", "WATCH"]
    env_file: .env                        # .env still the source of secrets/config
    environment:
      LENS_MCP_TRANSPORT: http
      MCP_HTTP_HOST: tv-mcp               # docker DNS → tv-mcp container
      MCP_HTTP_PORT: "8765"
      QUESTDB_HOST: questdb               # docker DNS → questdb container
      QUESTDB_ILP_PORT: "9009"
      QUESTDB_PG_PORT: "8812"
      MT5_COMMON_FILES_DIR: "/mt5"        # path inside container
      FORGE_JOURNAL_DIR: "/mt5/tester"    # path inside container
      PYTHONUNBUFFERED: "1"
      TZ: America/New_York                # match the trading session calendar
    volumes:
      - "${MT5_COMMON_FILES_HOST_PATH}:/mt5"      # bind mount, read+write
      - "parquet-archive:/app/data/parquet"       # cold path
      - "./logs:/app/logs"                        # bridge.log + bridge.error.log
    depends_on:
      tv-mcp: { condition: service_healthy }
      questdb: { condition: service_healthy }
    healthcheck:
      # bridge doesn't expose HTTP; use a marker file the main loop touches
      test: ["CMD-SHELL", "test -f /tmp/bridge_alive && find /tmp/bridge_alive -mmin -1 | grep -q ."]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s                   # allow time for FORGE journal sync
    logging:
      driver: json-file
      options: { max-size: 50m, max-file: "10" }

  # ── aurum (LLM agent + Telegram bot) ─────────────────────────────
  # Calls tv-mcp for chart context, calls Anthropic API for reasoning,
  # writes events to QuestDB.
  aurum:
    build:
      context: .
      dockerfile: docker/Dockerfile.python
    image: signal/aurum:local
    container_name: signal-aurum
    restart: unless-stopped
    networks: [ signal-net ]
    command: ["python", "python/aurum.py", "--telegram"]
    env_file: .env
    environment:
      LENS_MCP_TRANSPORT: http
      MCP_HTTP_HOST: tv-mcp
      MCP_HTTP_PORT: "8765"
      QUESTDB_HOST: questdb
      QUESTDB_PG_PORT: "8812"
      PYTHONUNBUFFERED: "1"
      TZ: America/New_York
    volumes:
      - "aurum-state:/app/python/data/aurum_state"  # telegram sessions, prompt cache
      - "./logs:/app/logs"
    depends_on:
      bridge: { condition: service_healthy }
    logging:
      driver: json-file
      options: { max-size: 20m, max-file: "5" }

  # ── athena (Flask API + React dashboard server) ──────────────────
  # Read-only access to QuestDB for the dashboard.
  athena:
    build:
      context: .
      dockerfile: docker/Dockerfile.python
    image: signal/athena:local
    container_name: signal-athena
    restart: unless-stopped
    networks: [ signal-net ]
    command: ["python", "python/athena_api.py"]
    env_file: .env
    environment:
      QUESTDB_HOST: questdb
      QUESTDB_PG_PORT: "8812"
      ATHENA_PORT: "7842"
      ATHENA_READ_ONLY: "1"               # belt-and-suspenders: refuses writes
      PYTHONUNBUFFERED: "1"
    ports:
      - "127.0.0.1:7842:7842"             # dashboard — localhost only
    volumes:
      - "./logs:/app/logs"
    depends_on:
      questdb: { condition: service_healthy }
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:7842/api/health || exit 1"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 15s
    logging:
      driver: json-file
      options: { max-size: 20m, max-file: "5" }

  # ── listener (Telegram channel scraper) ──────────────────────────
  # Tails the Telegram signal channels, writes parsed signals to QuestDB.
  # Not exposed externally — internal service.
  listener:
    build:
      context: .
      dockerfile: docker/Dockerfile.python
    image: signal/listener:local
    container_name: signal-listener
    restart: unless-stopped
    networks: [ signal-net ]
    command: ["python", "python/listener.py"]
    env_file: .env
    environment:
      QUESTDB_HOST: questdb
      QUESTDB_PG_PORT: "8812"
      PYTHONUNBUFFERED: "1"
    volumes:
      - "aurum-state:/app/python/data/aurum_state"  # shared telegram session with aurum
      - "./logs:/app/logs"
    depends_on:
      questdb: { condition: service_healthy }
    logging:
      driver: json-file
      options: { max-size: 20m, max-file: "5" }
```

#### Required `.env` additions (compose-specific keys)

```bash
# Host path to MT5 Common Files — varies by OS:
#   macOS Wine:    /Users/<user>/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files
#   Windows:       C:\Users\<user>\AppData\Roaming\MetaQuotes\Terminal\Common\Files
#   Linux Wine:    ~/.wine/drive_c/users/$USER/AppData/Roaming/MetaQuotes/Terminal/Common/Files
MT5_COMMON_FILES_HOST_PATH=/Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files

# QuestDB Postgres-wire password (used by Python clients for SQL queries)
QUESTDB_PG_PASSWORD=signal_local_dev
```

#### Two Dockerfiles

**`tradingview-mcp-aurum/Dockerfile`** (the MCP daemon):

```dockerfile
FROM node:22-bookworm-slim
WORKDIR /app
# Production deps only — async-mutex, @modelcontextprotocol/sdk, chrome-remote-interface, dotenv
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev && npm cache clean --force
COPY src/ ./src/
# rules.json is a make-update-lens-mcp symlink artifact; copy if present for the CLI
COPY rules.json* ./
EXPOSE 8765
# Run as non-root for defense in depth (node 22 image has a `node` user)
RUN mkdir -p /var/log/mcp && chown -R node:node /var/log/mcp /app
USER node
# Health probe is wget against /health (busybox wget is in -slim images)
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD wget -qO- http://localhost:8765/health || exit 1
ENTRYPOINT ["node", "src/server.js"]
```

**`signal_system/docker/Dockerfile.python`** (one image, three services via `command:`):

```dockerfile
FROM python:3.13-slim-bookworm
WORKDIR /app
# System deps for sqlite (transitional, kept until QuestDB cutover complete) + healthcheck wget
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 libsqlite3-dev curl wget tzdata \
    && rm -rf /var/lib/apt/lists/*
# Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# App code
COPY python/ ./python/
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY schemas/ ./schemas/
COPY dashboard/ ./dashboard/
COPY services/ ./services/
# Logs dir — bound to host volume in compose
RUN mkdir -p /app/logs /app/python/data /app/python/data/aurum_state
# Bridge writes /tmp/bridge_alive for the healthcheck
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/python
# Note: command is set per-service in compose, not here.
```

#### Operational targets (replace the launchd Make targets)

```makefile
# ── F6: docker compose stack ────────────────────────────────────────────
COMPOSE = docker compose

compose-build:
	@$(COMPOSE) build

compose-up:
	@$(COMPOSE) up -d
	@sleep 5
	@$(MAKE) compose-health

compose-down:
	@$(COMPOSE) down

compose-restart:
	@$(COMPOSE) down
	@$(COMPOSE) up -d --build
	@sleep 5
	@$(MAKE) compose-health

compose-logs:
	@$(COMPOSE) logs -f --tail=100 $(SERVICE)

compose-ps:
	@$(COMPOSE) ps

compose-health:
	@echo "── Compose service health ──"
	@$(COMPOSE) ps --format "table {{.Name}}\t{{.Status}}\t{{.Health}}"
	@curl -sf http://127.0.0.1:8765/health  > /dev/null 2>&1 && echo "  ✓ tv-mcp" || echo "  ✗ tv-mcp"
	@curl -sf http://127.0.0.1:7842/api/health > /dev/null 2>&1 && echo "  ✓ athena" || echo "  ✗ athena"
	@curl -sf "http://127.0.0.1:9000/exec?query=select%201" > /dev/null 2>&1 && echo "  ✓ questdb" || echo "  ✗ questdb"
```

#### Platform notes

| Platform | CDP networking | MT5 bind mount | Notes |
|---|---|---|---|
| **macOS Docker Desktop** | `host.docker.internal:9222` works out of box. `extra_hosts: host-gateway` is a safety belt for older versions. | bind from `~/Library/Application Support/.../Common/Files` works. macOS gRPC FUSE has occasional `flock()` quirks — moot here because QuestDB owns the hot path. | TradingView Desktop + MT5 (Wine) both on host. Containers are in Docker Desktop's Linux VM. |
| **Windows Docker Desktop (WSL2 backend)** | Same: `host.docker.internal:9222`. | bind from `C:\Users\<user>\AppData\Roaming\MetaQuotes\...`. WSL2 path translation works automatically. | Easiest deployment — both apps native, both file paths native. |
| **Linux server (no Docker Desktop)** | Use `network_mode: host` on tv-mcp instead of bridge network. Or set `CDP_HOST` to the host's reachable IP. `host.docker.internal` does NOT work on bare Linux. | bind from `~/.wine/drive_c/users/$USER/AppData/Roaming/...` (Wine on Linux). | No native TradingView/MT5 for Linux; Wine is the only path. |
| **Apple Silicon (M1/M2/M3)** | Compose works; `node:22-bookworm-slim` and `python:3.13-slim-bookworm` are multi-arch (linux/amd64 + linux/arm64). | Same as macOS Docker Desktop. | No special config needed. |

#### Bring-up sequence (first time)

```bash
# 1. Build images
make compose-build

# 2. Verify host prerequisites — TradingView + MT5 must be running on host
make start-tradingview                    # via the existing native Make target
# (operator manually starts MT5 + opens chart)

# 3. Bring up the compose stack
make compose-up

# 4. Verify
make compose-health
# Expected output:
#   NAME              STATUS          HEALTH
#   signal-questdb    Up X minutes    healthy
#   signal-tv-mcp     Up X minutes    healthy
#   signal-bridge     Up X minutes    healthy
#   signal-aurum      Up X minutes    running
#   signal-athena     Up X minutes    healthy
#   signal-listener   Up X minutes    running
#   ✓ tv-mcp
#   ✓ athena
#   ✓ questdb

# 5. Open dashboard
open http://127.0.0.1:7842/
```

#### Production checklist (before flipping default)

- [ ] All 6 services show `healthy` for 24h continuous
- [ ] LENS polls succeed (QuestDB query: `SELECT count(*) FROM forge_signals WHERE ts > dateadd('h', -1, now())` returns increasing)
- [ ] AURUM responds to Telegram messages end-to-end
- [ ] Athena dashboard loads with real data
- [ ] `docker compose down && docker compose up -d` recovers state from named volumes
- [ ] QuestDB volume backup pipeline tested (`docker run --rm -v signal_system_questdb-data:/data ...`)
- [ ] Restart-after-crash recovery: kill any service with `docker compose kill SERVICE`, verify `restart: unless-stopped` brings it back
- [ ] Resource ceiling under load (if needed): add `deploy.resources.limits.memory` per service
- [ ] Migration runbook documented (rollback path: `docker compose down` → `make system-up` reverts to launchd)

#### What's deliberately NOT in this compose

- **No reverse proxy / TLS termination.** Localhost-only binds; if exposing externally, add Caddy or Traefik in front.
- **No secrets manager.** `.env` file is the source. For production-grade secrets, swap to Docker Secrets or Vault.
- **No log aggregation.** json-file rotation per service. For multi-host: ship to Loki / ELK / CloudWatch.
- **No metrics export.** Add Prometheus + Grafana sidecars if SLO monitoring is needed.
- **No horizontal scaling.** Single-replica per service (see hard prereq #2 — F2 mutex is per-process).
- **No Chrome/TradingView in containers.** These remain native on the host — irreducible per the design.

**What containerization does NOT solve**:

- Horizontal scaling — single-replica only. F2 mutex is per-process; running 2 tv-mcp containers re-introduces the cross-process race. Sticky routing OR Redis-backed lock are the only fixes; both add infrastructure for a problem this deployment doesn't have.
- TradingView / MT5 native dependency — the host still needs both apps running. Containerization is for the Python + Node services, not the broker / charting clients.
- Chrome CDP single-attachment — Chrome typically allows one CDP attach per target. The F4 reconnect logic handles disconnects, but two MCP processes attaching simultaneously is undefined.

**Acceptance criteria**:

- `docker compose up -d` brings all 5 services up.
- `curl http://localhost:8765/health` returns 200.
- `curl http://localhost:7842/api/health` returns 200.
- LENS poll cycle succeeds (visible in QuestDB queries against the `forge_signals` table).
- AURUM Telegram → tv-mcp HTTP works (smoke test: ask AURUM "how's gold?").
- `docker compose down` shuts down cleanly; restart preserves QuestDB state via the named volume.

**Rollback**: launchd targets remain functional for the duration of F6's bake-in period. `make system-down && make system-up` reverts to the pre-container deployment without losing state (QuestDB data + Parquet archive are independent of the deployment-method choice).

**Upstream PR**: none. F6 is signal_system deployment; not relevant to the MCP fork.

### F7 — `shared-services` consolidation (moduliths pattern, post-F6, ours only)

**Goal**: extract the **shared library modules** (`herald`, `reconciler`, `sentinel`, plus optional `aegis`/`status_report`) that are currently imported by 2-3 of the main services into a single new container called **`shared-services`**. This is the moduliths pattern: one HTTP-exposed service hosts multiple logical modules, callers HTTP into it instead of importing.

**Why**: today these modules are duplicated in memory across processes that import them (bridge imports all 5; aurum imports herald; athena imports aegis). Consolidating them into one container means:

- One restart point when any of those modules changes (today: restart 2-3 services to pick up a herald.py edit)
- One log destination for module-level events
- One place to instrument (metrics, tracing) — currently scattered
- Smaller host service images (bridge/aurum/athena no longer carry herald/reconciler/sentinel code)
- Cleaner failure domain — herald going down doesn't crash bridge

**Why NOT a full microservices split per module**: per-module HTTP overhead × per-call frequency = death by 1000 cuts on hot paths. Moduliths gives 80% of the architectural benefit at 20% of the operational complexity.

#### F7.1 Modules to consolidate (empirically chosen by call frequency)

| Module | Current frequency | Consolidate? | Why |
|---|---|---|---|
| `herald` | ~1-10 Telegram posts per hour | ✅ yes | Low frequency, HTTP overhead is noise |
| `reconciler` | Periodic sweeps (~1/min in bridge) | ✅ yes | Low frequency; reconciler-as-service can drive its own clock independently |
| `sentinel` | Periodic component-health checks (~1/30s) | ✅ yes | Low frequency; service can poll QuestDB directly |
| `status_report` | ~1/30s heartbeat writes | ✅ yes | Already a write-path utility, fits the consolidated service |
| `aegis` | **Per-signal validation — HIGH frequency** | ⚠️ **defer** | A signal-firing decision can't pay a 5-50ms HTTP roundtrip per validate. Keep aegis embedded in bridge + athena until benchmarked. Reconsider if/when aegis logic grows beyond pure validation. |
| `lens` | Polls every ~5s in WATCH mode | ⚠️ **defer / separate F7.5** | Lens lifecycle is tightly coupled to bridge state (mode transitions, mt5_data). Splitting it cleanly is a separate effort. |

So F7 v1 scope: **herald + reconciler + sentinel + status_report** → consolidated into `shared-services`. aegis and lens stay embedded for now.

#### F7.2 HTTP API surface design

Single Flask (or FastAPI) app at `python/shared_services/app.py`. One blueprint per module. Endpoints mirror the existing function signatures so refactor is mechanical.

```python
# python/shared_services/app.py
from flask import Flask, request, jsonify
import herald, reconciler, sentinel, status_report

app = Flask(__name__)

# ── Herald (Telegram poster) ────────────────────────────────────────
@app.post("/herald/post")
def herald_post():
    """Body: {channel, text, parse_mode?, reply_to?}"""
    body = request.json
    msg_id = herald.post(body["channel"], body["text"], **body.get("opts", {}))
    return jsonify({"message_id": msg_id})

@app.post("/herald/edit")
def herald_edit():
    body = request.json
    herald.edit(body["channel"], body["message_id"], body["text"])
    return jsonify({"ok": True})

# ── Reconciler (periodic sweeps) ────────────────────────────────────
# Reconciler doesn't get called from outside — it runs on its OWN clock
# inside shared-services. Exposes a /reconciler/status endpoint for
# health probes + a /reconciler/trigger endpoint for manual sweeps.
@app.get("/reconciler/status")
def reconciler_status():
    return jsonify(reconciler.get_status())

@app.post("/reconciler/trigger")
def reconciler_trigger():
    """Manually fire a reconciliation sweep (operator override)."""
    result = reconciler.sweep_once()
    return jsonify(result)

# ── Sentinel (component health checks) ──────────────────────────────
@app.get("/sentinel/heartbeats")
def sentinel_heartbeats():
    """Return current per-component last-seen timestamps."""
    return jsonify(sentinel.get_all_heartbeats())

@app.post("/sentinel/heartbeat")
def sentinel_heartbeat():
    """Component reports liveness."""
    body = request.json
    sentinel.record_heartbeat(body["component"], body.get("status", "ok"))
    return jsonify({"ok": True})

# ── Status report (per-component health writes) ────────────────────
@app.post("/status/report")
def status_report_endpoint():
    body = request.json
    status_report.report_component_status(body["component"], body["payload"])
    return jsonify({"ok": True})

# ── Health probe ────────────────────────────────────────────────────
@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "shared-services",
        "modules": ["herald", "reconciler", "sentinel", "status_report"],
        "uptime_sec": time.time() - START_TIME,
    })
```

**Background loops** (reconciler sweep, sentinel periodic check) start in a background thread when shared-services boots — same lifecycle as launching `bridge.py` with reconciler+sentinel imports today, but now in a dedicated process.

#### F7.3 Caller refactor pattern

Replace import-and-call with HTTP-and-call. New Python helper `python/shared_services_client.py`:

```python
import os, requests

BASE_URL = os.environ.get("SHARED_SERVICES_URL", "http://shared-services:9100")

def herald_post(channel, text, **opts):
    r = requests.post(f"{BASE_URL}/herald/post",
                      json={"channel": channel, "text": text, "opts": opts},
                      timeout=5)
    r.raise_for_status()
    return r.json()["message_id"]

def sentinel_heartbeat(component, status="ok"):
    requests.post(f"{BASE_URL}/sentinel/heartbeat",
                  json={"component": component, "status": status},
                  timeout=2)
```

Then in `bridge.py` / `aurum.py`:

```python
# BEFORE:
# from herald import post as herald_post
# herald_post("trade_room", "G5001 +$1212")

# AFTER:
from shared_services_client import herald_post
herald_post("trade_room", "G5001 +$1212")
```

Same call site shape, just a different import. Failure mode changes: HTTP timeout / 5xx instead of in-process exception. Wrap with retries + circuit-breaker if needed.

#### F7.4 Migration sequence (lockstep refactor — can't ship in halves)

1. **Build `python/shared_services/` package** — copy herald/reconciler/sentinel/status_report modules into a new directory; wire them behind Flask endpoints; write a Dockerfile.
2. **Write `python/shared_services_client.py`** — HTTP wrapper exposing the same call surface as the original modules.
3. **Refactor callers** — `bridge.py`, `aurum.py`, `athena_api.py` switch from `from herald import ...` to `from shared_services_client import herald_*`. Same for sentinel/reconciler/status_report imports.
4. **Add `shared-services` to compose** — new container, port 9100 (internal docker network only), same `signal-net`.
5. **Test in parallel**: keep both code paths available behind `USE_SHARED_SERVICES=1` env flag. Default 0 = current embedded; 1 = HTTP via shared-services. Soak each path for a week.
6. **Promote default** — flip default to 1. Remove the embedded import path after another week.
7. **Delete the duplicate module files from non-shared-services containers** — bridge/aurum/athena Dockerfiles stop copying herald/reconciler/sentinel/status_report.

#### F7.5 Compose addition

Add to the `docker-compose.yml` from F6:

```yaml
  shared-services:
    build:
      context: .
      dockerfile: docker/Dockerfile.python
    image: signal/shared-services:local
    container_name: signal-shared-services
    restart: unless-stopped
    networks: [ signal-net ]
    command: ["python", "python/shared_services/app.py"]
    env_file: .env
    environment:
      QUESTDB_HOST: questdb
      QUESTDB_PG_PORT: "8812"
      SHARED_SERVICES_PORT: "9100"
      PYTHONUNBUFFERED: "1"
    # No external port — internal-only
    expose: [ "9100" ]
    volumes:
      - "aurum-state:/app/python/data/aurum_state"  # for Telegram session state used by herald
      - "./logs:/app/logs"
    depends_on:
      questdb: { condition: service_healthy }
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:9100/health || exit 1"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 10s
    logging:
      driver: json-file
      options: { max-size: 20m, max-file: "5" }
```

And callers gain one env var:

```yaml
  bridge:
    environment:
      SHARED_SERVICES_URL: "http://shared-services:9100"
      USE_SHARED_SERVICES: "1"   # 0 to fall back to embedded imports

  aurum:
    environment:
      SHARED_SERVICES_URL: "http://shared-services:9100"
      USE_SHARED_SERVICES: "1"

  athena:
    environment:
      SHARED_SERVICES_URL: "http://shared-services:9100"
      USE_SHARED_SERVICES: "1"
```

#### F7.6 Acceptance criteria

- [ ] `docker compose up -d` brings shared-services up healthy.
- [ ] With `USE_SHARED_SERVICES=0` (default during soak): system behaves identically to F6 — bridge/aurum/athena use embedded imports. Shared-services container runs idle.
- [ ] With `USE_SHARED_SERVICES=1`: every herald/sentinel/reconciler/status_report call goes through HTTP. Verify via shared-services access log.
- [ ] Telegram posts still appear with same formatting (herald regression check).
- [ ] Component heartbeats still appear in QuestDB at same cadence (sentinel regression check).
- [ ] Periodic reconciliation sweeps still run (verify via reconciler logs or QuestDB markers).
- [ ] **Shared-services down** = herald posts queue and retry, OR fail loudly. Define behavior explicitly per module — don't leave it implicit.
- [ ] Per-call HTTP latency to shared-services <10ms p99 (over localhost docker network).

#### F7.7 Rollback

- Set `USE_SHARED_SERVICES=0` in `.env`, `docker compose up -d` rerolls.
- Containers fall back to embedded imports.
- Shared-services container stays up (idle) — no harm.

#### F7.8 What F7 does NOT do

- **Does not split aegis** — high-frequency per-signal validation; keep embedded. Future F7.x if aegis logic grows enough to warrant HTTP cost.
- **Does not split lens** — coupled to bridge mode state; needs separate effort.
- **Does not introduce service mesh / sidecars** — single HTTP service is enough at this scale.
- **Does not change the QuestDB schema or scribe writes** — same data flow, different process boundary.

#### F7.9 Honest payoff at our scale

| Benefit | Real? |
|---|---|
| Cleaner architecture | yes, but cosmetic at single-machine scale |
| One restart point for shared logic | yes — useful when iterating on herald/reconciler |
| Smaller host service images | yes — bridge image shrinks by ~maybe 200KB; not a meaningful cost saver |
| Independent failure domain (herald down ≠ bridge down) | yes, BUT requires explicit per-call failure mode design (queue? fail? retry?) — work, not free |
| Easier to instrument | yes — single Prometheus exporter per module |
| Easier to test in isolation | yes — shared-services has a clean HTTP contract |

**The payoff is architectural, not performance.** At current scale, F7 is a 2-3 day refactor that buys you cleaner boundaries. Don't ship F7 unless you have a concrete reason — same rule as the original microservices-vs-mutex decision in F2.

**Suggested trigger for shipping F7**:
- You hit a herald.py change that requires restarting bridge + aurum + sentinel simultaneously, and it's painful, OR
- You want to add Prometheus metrics to herald and don't want to instrument it in 3 places, OR
- You start adding a second LLM-driven module that also wants herald — fourth caller is the tipping point.

Until one of those fires, F6 (containerize the embedded topology) is sufficient.

## Upstream PR sequencing (post-F1)

| Phase | Upstream issue first | PR rank | Why this order |
|---|---|---|---|
| **F2** | Yes — describe race + propose mutex | **1st** | Smallest defensive correctness fix; maintainer-friendly. |
| **F4** | Yes — describe disconnect race | **2nd** | Orthogonal to F2; pure robustness. Independent merge. |
| **F3** | Yes — propose transport addition | **3rd** | Bigger, opinionated, needs design discussion. Worth doing last when we have credibility from F2/F4 merges. |

Each PR includes:
- Minimal repro / failure recording.
- The fix.
- Tests that assert the new invariant.
- No drive-by refactors.

If a PR merges, we `git pull` upstream into our fork and drop the matching commits. Fork stays thin — ideally just a few commits ahead at any moment.

## Honest payoff summary (2026-05-16 — operator-requested honest assessment)

The operator asked for an unhyped readout of what F1-F5 actually buy. This is the canonical version. Replaces any "ship this and everything changes" framing in earlier sections.

### Why each phase exists

| Phase | What it adds | Real benefit | Honest scope limit |
|---|---|---|---|
| **F1** Fork + Makefile cutover | Our own copy of the MCP server we can edit | Without this we can't ship F2/F3/F4 — that's the only reason | Zero new behavior |
| **F2** Write mutex + NDJSON tracer | Serializes write-class tool calls in-process. Optional tracer for observability. | Prevents two concurrent write evaluates from racing on Chrome's JS thread. Tracer gives per-call latency + queue wait visibility. | **Per-process only.** In the current spawn-per-call AURUM setup, there's only ever ONE writer per process — the mutex mostly idles. Becomes meaningful only when F3+F5 land. |
| **F4** CDP reconnect + drain | Auto-detects Chrome disconnect via watchdog, reconnects. `trace.drain()` makes pre-throw events SIGKILL-safe. New `tv_cdp_status` tool. | Resilience: Chrome restart / TV close → automatic recovery instead of confusing errors mid-tool-call. | **Per-process only.** Short-lived AURUM spawn processes rarely live long enough for the watchdog to tick. Earns its keep once F3+F5 give us a long-lived process. |
| **F3** Streamable HTTP transport | One MCP process serves N consumers via HTTP instead of N stdio subprocesses. | The unlock: makes F2+F4 actually do work. Removes per-spawn overhead (Chrome attach + tool registration ~200-500ms × every AURUM call). One CDP attachment shared by all consumers. | **Until F5 flips consumers to HTTP, nothing changes in production.** The HTTP server is shipped but unused by current services. |
| **F5** launchd plist + Python HTTP client | Deploys the HTTP MCP as a launchd-managed daemon + flips `python/mcp_client.py` to HTTP. | **Activates F2+F3+F4 in production.** Replaces N short-lived processes with 1 persistent daemon. Per-call latency drops from ~300ms to ~5ms (no spawn cost). | Pure deployment plumbing — no new MCP capability. |

### The actual chain of value

Without F5, **F2/F4 don't do meaningful work in the deployed system today**. The mutex protects against intra-process races that the spawn-per-call pattern doesn't have. The watchdog needs process lifetime to tick.

F3 is the transport switch. F5 is the deployment glue. Together they convert F2+F4 from "committed but idling" into "actually running."

### What it doesn't solve (limits)

- Doesn't help if TradingView Desktop isn't running with `--remote-debugging-port=9222` — `make start-tradingview` still required.
- Doesn't affect FORGE EA / MT5 side — that's a separate process, separate journal DB.
- Doesn't change the LENS broker-data path (MT5 → `market_data.json` → AURUM, no MCP involved).
- Doesn't help if AURUM's LLM logic decides wrong things — MCP is a data plumbing layer, not a decision layer.

### What it costs

- ~700 lines of fork code we now own + must maintain when `@modelcontextprotocol/sdk` upgrades. Currently sitting on `^1.12.1`, installed `1.27.1`.
- PR #42 may not merge upstream → we carry the fork indefinitely (acceptable per `project_aurum_ai_backed_trading.md`).
- One more service to monitor (`make mcp-status` after F5) — a 5th process alongside bridge/listener/aurum/athena.

### Honest payoff at current scale

Per-call latency reduction (~300ms → ~5ms) × AURUM's polling cadence (every ~30s) = saves ~1 minute per hour of CPU spawn time. Not huge.

The real win is **architectural**: when scaling to multiple Telegram conversations or adding LENS as a second consumer, the F2 mutex and F4 watchdog become load-bearing rather than dormant. Today they're insurance not yet needed; F5 makes them insurance actually held.

**If F5 ships**: cleaner ops, slightly faster polling, safety nets activate.
**If F5 doesn't ship**: F2/F3/F4 are committed code that doesn't change anything in production.

---

## Open questions

1. **Fork name** — `tradingview-mcp-aurum` matches our naming, or do we want something more generic like `tradingview-mcp-streamable`? (Operator decides; affects branding of upstream PRs.)
2. **HTTP port** — `8765` is a guess. Anything we need to coordinate with another service? Check `.env` + Athena `:7842`.
3. **Auth on HTTP** — bind to `127.0.0.1` is sufficient for single-machine; do we want a bearer token anyway for defense in depth? (Probably no, but flag.)
4. **Test coverage in upstream** — does the fork have a test harness today? If not, F2's concurrency test is the first one we add. Worth confirming before writing it.

## Operator action checklist (do before F1 starts)

- [ ] Create empty fork on GitHub (`ephico2real2/tradingview-mcp-aurum` or chosen name)
- [ ] Provide fork URL to this session
- [ ] (Optional) Star/watch `LewisWJackson/tradingview-mcp-jackson` to track upstream
- [ ] Decide on the fork name (above) — affects PR branding

## Decision log

| Date | Decision | Rationale | Source |
|---|---|---|---|
| 2026-05-16 | Fork instead of using `mcp-proxy` | Mcp-proxy doesn't fix the write-race; we need the mutex in the MCP itself. Forking also gives us a clean upstream-PR path for the three generic improvements (F2/F3/F4). | this session |
| 2026-05-16 | Don't make the fork a git submodule | Submodule UX pain + dirties the fork history for upstream PRs. Plain sibling clone is cleaner. | this session |
| 2026-05-16 | Bind HTTP to 127.0.0.1 only | Single-machine deployment, no need for external network exposure. Reduces attack surface. | this session |
| 2026-05-16 | F5 (launchd + Python HTTP client) stays in signal_system | Deployment-specific (macOS launchd, our Python client). Not relevant upstream. | this session |

## Changelog

| Date | Change |
|---|---|
| 2026-05-16 | Initial plan. Awaiting operator's fork URL to begin F1. |
| 2026-05-16 | F1 shipped. Fork cloned at `/Users/olasumbo/tradingview-mcp-aurum/` (HEAD `5d6d7bc`, byte-identical to upstream). `upstream` git remote added for future rebases. `Makefile` `LENS_MCP_DIR` + clone URL flipped to our fork. `make update-lens-mcp` + `make clean-mcp-git-stash` validated against new path. `make health` Overall ✅ OK. The legacy `/Users/olasumbo/tradingview-mcp-jackson/` clone is kept on disk as the upstream reference for `git diff` sanity checks — will be removed after F2/F3/F4 stabilise. Next: F2 write-tool async mutex. |
| 2026-05-16 | **F4 committed local-only** on `feat/cdp-reconnect` (fork commit `986ca77`, branched off `feat/write-mutex` so it inherits the F2 tracer). New disconnect handler: `client.on('disconnect')` nulls the cached client/targetInfo immediately, emits `cdp.disconnected` tracer event. New watchdog: `setInterval` ping every `CDP_WATCHDOG_INTERVAL_MS` (default 30000, 0 to disable). On ping failure or null client, `reconnectFromWatchdog(reason)` fires `cdp.reconnect_attempt` → `connect()` → `cdp.reconnect_ok` (with `dur_ms`, `reconnect_count`) or `cdp.reconnect_failed` (with error). Reconnects serialize via `reconnectInFlight` flag so stacked watchdog ticks can't double-reconnect. New `tv_cdp_status` MCP tool returns no-roundtrip snapshot: `{connected, target_id, target_url, last_ping_ms_ago, reconnect_count, watchdog_enabled, watchdog_interval_ms, reconnect_in_flight}`. New `getConnectionStatus()` export from `src/connection.js`, `cdpStatus()` in `src/core/health.js`. Test coverage: `tests/reconnect.test.js` 5/5 pass (module exports, default state shape, env config, core function); F2 concurrency + tracer regressions clean. `node src/server.js` boots clean. Live integration test (close+reopen TradingView → tracer events fire on long-lived server) DEFERRED — per-call MCP spawn pattern doesn't naturally exercise the watchdog path, will validate during upstream PR prep. Per operator option 3: pushed to fork origin ONLY, NO upstream PR opened — sitting on F4 until PR #42 maintainer response tells us the right shape. |
| 2026-05-16 | **F2 PR opened upstream**: [LewisWJackson/tradingview-mcp-jackson#42](https://github.com/LewisWJackson/tradingview-mcp-jackson/pull/42) — *Write-tool mutex for state isolation + optional NDJSON tracer*. Two commits on `feat/write-mutex`: `ccf66a0` (mutex + 10 module migrations) and `8e2a209` (NDJSON tracer + bench harness + docs). Validated live via the tracer against running TradingView Desktop: 261 read pairs, 7 `evaluateWrite` lifecycle triplets (wait_ms 0.06–0.60ms, work_ms 1.7–504ms), 1 `withWriteLock` triplet on `chart_manage_indicator` (wait_ms=6.08, work_ms=1679.86 with 3 nested evaluate pairs inside the lock window — tool attribution preserved through AsyncLocalStorage across nested async hops). PR framing: correctness + TradingView rate-limit cooperation + state isolation; speed numbers in appendix only. Next: monitor PR #42 maintainer response before opening F4 upstream issue. |
| 2026-05-16 | F2 implemented on `feat/write-mutex` branch in the fork. `async-mutex` (operator-confirmed dep choice) added at `^0.5.0`. New exports in `src/connection.js`: `evaluateWrite(expression, opts)` runs single-statement writes under a process-wide mutex; `withWriteLock(fn)` wraps multi-step write sequences (handler receives a `evalInside` callback so reads+writes inside the critical section don't re-lock). ~30 write handlers across 9 `src/core/` modules now serialize: chart.js (setSymbol/setTimeframe/setType/manageIndicator/setVisibleRange/scrollToDate), drawing.js (drawShape/removeOne/clearAll), alerts.js (create/deleteAlerts), pane.js (setLayout/focus/setSymbol), indicators.js (setInputs/toggleVisibility), pine.js (setSource/compile/save/smartCompile/newScript/openScript — `ensurePineEditorOpen` left unlocked as idempotent open-or-noop), replay.js (start/step/autoplay/stop/trade), batch.js (per-iteration symbol/tf switch lock), watchlist.js (add), ui.js (click/openPanel/fullscreen/layoutSwitch/keyboard/typeText/hover/scroll/mouseClick/uiEvaluate). New `tests/concurrency.test.js` with 4 tests: arrival-order serialization, withWriteLock multi-step atomicity, exports-check, reads-not-blocked-by-writes — all pass. Pre-existing tests (29) still pass. Server starts clean. `make health` shows LENS polling fork at 4.1s freshness — no regression. Not yet committed/pushed; awaiting operator review. Next: open upstream issue describing the multi-client race, then PR `feat/write-mutex`. |
