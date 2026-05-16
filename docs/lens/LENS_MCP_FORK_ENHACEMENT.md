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

### F7 — Core service separation (aegis, lens, shared-services), post-F6, ours only

**Goal**: split three core concerns out of the bridge/aurum/athena monoliths into their own containers. Each is a separate service in the compose, not a library imported by 3 different host processes. Operator-mandated topology (2026-05-16) — these are core services, not utility libraries.

**Three new containers**:

| Container | Hosts | Rationale |
|---|---|---|
| **aegis** | `python/aegis.py` | Security perimeter. ALL trade-modifying commands (OPEN_GROUP, CLOSE_*, MODIFY_*) flow through aegis validation before reaching FORGE EA. Deserves its own container as a distinct security boundary — restart aegis independently, scope its logs separately, instrument its decisions cleanly. Used by bridge (write path) + athena (read path for UI display of current limits/decisions). |
| **lens** | `python/lens.py` | Data acquisition perimeter. Owns all TradingView data fetching: MCP calls via tv-mcp, indicator parsing, snapshot caching, TV-Brief generation. Deserves its own container because LENS lifecycle is self-contained (poll loop + cache) and the data-shaping logic is the integration substrate for everything downstream. Used by bridge (pulls snapshots for tick decisions) + aurum (queries snapshots for LLM context). |
| **shared-services** | `herald` + `reconciler` + `sentinel` | The remaining low-frequency utilities. Moduliths pattern: ONE container hosting three modules behind HTTP. These don't deserve standalone services because their failure modes + cadence are similar (low-frequency, observability-class). |

**status_report stays bundled with athena_api.py** — it's the per-component status-write helper that the dashboard UI consumes. Logically belongs at the API/UI boundary, not in shared-services.

**Why**: today these modules are duplicated in memory across processes that import them (bridge imports lens + aegis + sentinel + reconciler + herald; aurum imports herald + lens; athena imports aegis + status_report). Splitting them gives:

- **Independent restart cadence** — change aegis rules, restart aegis only. Today: restart bridge + athena simultaneously.
- **Independent failure domain** — lens down doesn't take down bridge's order-management loop (bridge can fall back to cached snapshot or skip the tick).
- **Independent scaling profile** — aegis is stateless validation (can be replicated trivially if ever needed); lens is stateful cache (single-replica only); shared-services is mixed (sentinel is stateful, herald is stateless).
- **Cleaner observability** — aegis decision log per container, lens fetch metrics per container.
- **Cleaner security boundary** — aegis as a separate process makes "all trade commands pass through aegis" a structural guarantee enforced by network topology, not by code review.

#### F7.1 Service split summary

| Module | Current location | F7 target | Frequency | Justification |
|---|---|---|---|---|
| `aegis` | imported by bridge + athena | **own container `aegis`** | Per-command (~1-10/hour during active trading) | Security perimeter; structural enforcement that all commands validate. HTTP overhead negligible at this frequency. |
| `lens` | imported by bridge + aurum | **own container `lens`** | Internal poll loop (~5s WATCH mode); external query on demand | Data acquisition; runs its own clock. Bridge/aurum consume cached snapshots via HTTP. |
| `herald` | imported by bridge + aurum + sentinel | **`shared-services` container** | Low (~1-10 Telegram posts/hour) | Utility-class; bundled with other low-frequency modules |
| `reconciler` | imported by bridge | **`shared-services` container** | Periodic sweeps (~1/min) | Utility-class; can drive its own clock inside shared-services |
| `sentinel` | imported by bridge | **`shared-services` container** | Periodic component checks (~1/30s) | Utility-class; can poll QuestDB independently |
| `status_report` | imported by athena_api | **STAYS with athena container** | ~1/30s heartbeat writes | Per design — consumed by the API to expose the UI. Moving it out adds a network hop on every dashboard render. Keep bundled. |

#### F7.2 HTTP API surface design — three services

Each new container exposes its own Flask app. Endpoints mirror the existing function signatures so caller refactors are mechanical.

##### F7.2a — `aegis` service (port 9101)

`python/aegis_service/app.py`. The security perimeter. Every command-validating call site in bridge + athena moves to HTTP. Aegis is stateless beyond config (`config/aegis_limits.json`), so the container can be replicated trivially if ever needed.

```python
# python/aegis_service/app.py
from flask import Flask, request, jsonify
import aegis

app = Flask(__name__)

# ── Trade-modifying validation (write path — used by bridge) ─────
@app.post("/aegis/validate_open_group")
def validate_open_group():
    """Body: {direction, lot, sl, tp, magic_base, source, ...}
       Returns: {approved: bool, reason: str, risk_score: float}
    """
    body = request.json
    result = aegis.validate_open_group(body)
    return jsonify(result)

@app.post("/aegis/validate_modify")
def validate_modify():
    """Body: {ticket|group_id|tp_stage, new_sl?, new_tp?, ...}"""
    body = request.json
    return jsonify(aegis.validate_modify(body))

@app.post("/aegis/validate_close")
def validate_close():
    """Body: {action: CLOSE_ALL|CLOSE_GROUP|CLOSE_PCT|..., ...}"""
    body = request.json
    return jsonify(aegis.validate_close(body))

# ── Read-only state (used by athena UI for "current limits" panel) ─
@app.get("/aegis/limits")
def get_limits():
    """Return current SL/TP/lot/MAX_GROUPS limits + recent decision counts."""
    return jsonify(aegis.get_active_limits())

@app.get("/aegis/decisions")
def recent_decisions():
    """Recent N validation decisions (last 50 by default). Used by UI."""
    limit = int(request.args.get("limit", 50))
    return jsonify(aegis.get_recent_decisions(limit))

@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "aegis",
                    "decisions_24h": aegis.count_decisions(hours=24)})
```

Aegis is **stateless** other than config + an in-memory decision-history ring buffer (for the UI panel). No background loop needed.

##### F7.2b — `lens` service (port 9102)

`python/lens_service/app.py`. Data acquisition perimeter. Runs its own poll loop independent of bridge tick cycle; bridge/aurum query for the latest snapshot via HTTP.

```python
# python/lens_service/app.py
import threading, time
from flask import Flask, request, jsonify
import lens

app = Flask(__name__)
_lens = lens.Lens()  # the existing lens.Lens class
_lock = threading.Lock()
_last_snapshot = None

# ── Background poll loop ────────────────────────────────────────────
# Replaces bridge.py's `self.lens.fetch_fresh(mode, mt5)` call inside
# the bridge tick. Lens drives its own clock based on mode the bridge
# pushes (via POST /lens/mode).
_current_mode = "WATCH"

def _poll_loop():
    global _last_snapshot
    while True:
        try:
            mt5_data = _fetch_mt5_market_data()  # read /mt5/market_data.json
            snap = _lens.fetch_fresh(_current_mode, mt5_data)
            with _lock:
                _last_snapshot = snap
        except Exception as e:
            log.warning(f"LENS poll failed: {e}")
        time.sleep(_poll_interval_for_mode(_current_mode))

threading.Thread(target=_poll_loop, daemon=True).start()

# ── Read paths (used by bridge + aurum) ────────────────────────────
@app.get("/lens/snapshot")
def get_snapshot():
    """Return the most-recent cached snapshot. <1ms response since it's an
       in-memory read — replaces the per-call MCP roundtrip pattern."""
    with _lock:
        snap = _last_snapshot
    if snap is None:
        return jsonify({"error": "no snapshot yet"}), 503
    return jsonify(snap.to_dict())

@app.post("/lens/refresh")
def force_refresh():
    """Force an immediate fetch (operator override / aurum on-demand)."""
    mt5_data = _fetch_mt5_market_data()
    snap = _lens.fetch_fresh(_current_mode, mt5_data)
    with _lock:
        global _last_snapshot
        _last_snapshot = snap
    return jsonify(snap.to_dict())

# ── Bridge tells lens about mode transitions ──────────────────────
@app.post("/lens/mode")
def set_mode():
    """Body: {mode: WATCH|SIGNAL|SCALPER|HYBRID|OFF}"""
    global _current_mode
    _current_mode = request.json["mode"]
    return jsonify({"mode": _current_mode})

@app.get("/health")
def health():
    with _lock:
        age_sec = (time.time() - _last_snapshot.ts) if _last_snapshot else None
    return jsonify({
        "status": "ok" if (age_sec is not None and age_sec < 60) else "warn",
        "service": "lens",
        "snapshot_age_sec": age_sec,
        "mode": _current_mode,
    })
```

Lens is **stateful** (cache + poll loop). Single-replica only — if you ran two, both would poll TV redundantly and the bridge's snapshot view would oscillate. The F2 write mutex on tv-mcp serializes their writes correctly, but it's wasteful.

##### F7.2c — `shared-services` (port 9100) — herald + reconciler + sentinel

`python/shared_services/app.py`. The moduliths container for the three remaining utility modules.

```python
# python/shared_services/app.py
from flask import Flask, request, jsonify
import herald, reconciler, sentinel

app = Flask(__name__)

# ── Herald (Telegram poster) ────────────────────────────────────────
@app.post("/herald/post")
def herald_post():
    body = request.json
    msg_id = herald.post(body["channel"], body["text"], **body.get("opts", {}))
    return jsonify({"message_id": msg_id})

@app.post("/herald/edit")
def herald_edit():
    body = request.json
    herald.edit(body["channel"], body["message_id"], body["text"])
    return jsonify({"ok": True})

# ── Reconciler (own clock — periodic sweeps) ───────────────────────
@app.get("/reconciler/status")
def reconciler_status():
    return jsonify(reconciler.get_status())

@app.post("/reconciler/trigger")
def reconciler_trigger():
    return jsonify(reconciler.sweep_once())

# ── Sentinel (component heartbeats + health) ───────────────────────
@app.get("/sentinel/heartbeats")
def sentinel_heartbeats():
    return jsonify(sentinel.get_all_heartbeats())

@app.post("/sentinel/heartbeat")
def sentinel_heartbeat():
    body = request.json
    sentinel.record_heartbeat(body["component"], body.get("status", "ok"))
    return jsonify({"ok": True})

@app.get("/health")
def health():
    return jsonify({
        "status": "ok", "service": "shared-services",
        "modules": ["herald", "reconciler", "sentinel"],
    })
```

Background loops (reconciler sweep, sentinel periodic check) start in a daemon thread when shared-services boots.

**status_report is NOT here** — it stays imported directly into `athena_api.py` because the UI consumes it on every dashboard request, and `/api/status` would otherwise become a cross-container chain (UI → athena → shared-services → write). Keeping it bundled with athena removes an unnecessary hop.

#### F7.3 Caller refactor pattern

Three new client wrappers — one per service. Same module-level call surface, HTTP under the hood. Caller code changes only the `import` line.

`python/aegis_client.py`:

```python
import os, requests
BASE = os.environ.get("AEGIS_URL", "http://aegis:9101")
_TIMEOUT = float(os.environ.get("AEGIS_TIMEOUT_SEC", "3"))

def validate_open_group(payload: dict) -> dict:
    r = requests.post(f"{BASE}/aegis/validate_open_group", json=payload, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()

def validate_modify(payload: dict) -> dict:
    r = requests.post(f"{BASE}/aegis/validate_modify", json=payload, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()

def validate_close(payload: dict) -> dict:
    r = requests.post(f"{BASE}/aegis/validate_close", json=payload, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()

def get_active_limits() -> dict:
    return requests.get(f"{BASE}/aegis/limits", timeout=_TIMEOUT).json()
```

`python/lens_client.py`:

```python
import os, requests
BASE = os.environ.get("LENS_URL", "http://lens:9102")
_TIMEOUT = float(os.environ.get("LENS_TIMEOUT_SEC", "5"))

def get_snapshot() -> dict | None:
    """Return latest cached snapshot from the lens service.
       Returns None if lens hasn't polled yet OR the call fails."""
    try:
        r = requests.get(f"{BASE}/lens/snapshot", timeout=_TIMEOUT)
        if r.status_code == 503:
            return None
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None

def force_refresh() -> dict | None:
    r = requests.post(f"{BASE}/lens/refresh", timeout=15)  # MCP roundtrip cost
    return r.json() if r.ok else None

def set_mode(mode: str) -> None:
    requests.post(f"{BASE}/lens/mode", json={"mode": mode}, timeout=_TIMEOUT)
```

`python/shared_services_client.py`:

```python
import os, requests
BASE = os.environ.get("SHARED_SERVICES_URL", "http://shared-services:9100")

def herald_post(channel: str, text: str, **opts) -> int:
    r = requests.post(f"{BASE}/herald/post",
                      json={"channel": channel, "text": text, "opts": opts},
                      timeout=5)
    r.raise_for_status()
    return r.json()["message_id"]

def sentinel_heartbeat(component: str, status: str = "ok") -> None:
    requests.post(f"{BASE}/sentinel/heartbeat",
                  json={"component": component, "status": status},
                  timeout=2)
```

**Refactor at the import site only** — `bridge.py` swaps `from aegis import validate_open_group` → `from aegis_client import validate_open_group`. Same name, same signature. Cleaner than rewriting callers.

**Failure-mode design** (explicit per service):

| Service down | Caller behavior | Reason |
|---|---|---|
| aegis | **Bridge BLOCKS the command** (returns failure to AURUM). | Security perimeter — fail closed, never approve a command without validation. |
| lens | **Bridge SKIPS the tick** (uses last cached snapshot if available, else no-op). | Stale data is better than wrong action. AURUM may answer with "data unavailable" to operator. |
| shared-services | **Caller retries 3× then logs and drops.** | Herald posts can be queued / dropped; reconciler will catch up on next sweep; sentinel heartbeat staleness will eventually alarm. None are critical-path on a single missed call. |

#### F7.4 Migration sequence (per service — ship independently with flag-guarded paths)

Each new service ships independently with a `USE_<SERVICE>=0/1` flag so the cutover is risk-bounded. Order matters: ship the LOW-RISK ones first to learn the pattern, then aegis (security perimeter), then lens (highest coupling risk).

**Ship order**: shared-services → aegis → lens.

**Per-service migration template**:

1. **Build service package** — `python/<service>_service/app.py` + Flask blueprint; reuse the existing module code unchanged (it stays the same, just newly hosted in a Flask process).
2. **Build client wrapper** — `python/<service>_client.py` with same call surface as the original module's exports.
3. **Refactor callers via flag** — every call site gets a `if USE_<SERVICE>: from <service>_client import X else: from <service> import X` guard during the soak period.
4. **Add to compose** — new container, internal-only port, healthcheck, depends_on, env_file.
5. **Test in parallel** with `USE_<SERVICE>=0` (current embedded) vs `=1` (new HTTP). Soak for 1 week per service.
6. **Promote default to 1**. Operator-confirmed before flip.
7. **Remove the guard + embedded import code** after another week of clean operation. Dockerfiles for callers stop copying the now-extracted module's files.

**Why per-service flags, not one master flag**: lets you flip shared-services to HTTP (low-risk) without exposing aegis (security perimeter — higher-risk if buggy) at the same time. Independent rollback per service.

#### F7.5 Compose additions — 3 new containers

Add to the `docker-compose.yml` from F6. All three are internal-only (no host port exposure); inter-service traffic goes through the `signal-net` bridge network.

```yaml
  # ── aegis (validation perimeter, port 9101) ───────────────────────
  aegis:
    build:
      context: .
      dockerfile: docker/Dockerfile.python
    image: signal/aegis:local
    container_name: signal-aegis
    restart: unless-stopped
    networks: [ signal-net ]
    command: ["python", "python/aegis_service/app.py"]
    env_file: .env
    environment:
      QUESTDB_HOST: questdb
      QUESTDB_PG_PORT: "8812"
      AEGIS_PORT: "9101"
      PYTHONUNBUFFERED: "1"
    expose: [ "9101" ]
    volumes:
      - "./config:/app/config:ro"     # aegis_limits.json + scalper_config.json
      - "./logs:/app/logs"
    depends_on:
      questdb: { condition: service_healthy }
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:9101/health || exit 1"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 5s
    logging:
      driver: json-file
      options: { max-size: 20m, max-file: "5" }

  # ── lens (TradingView data acquisition, port 9102) ────────────────
  lens:
    build:
      context: .
      dockerfile: docker/Dockerfile.python
    image: signal/lens:local
    container_name: signal-lens
    restart: unless-stopped
    networks: [ signal-net ]
    command: ["python", "python/lens_service/app.py"]
    env_file: .env
    environment:
      # tv-mcp is the canonical MCP daemon — lens calls it for chart data
      LENS_MCP_TRANSPORT: http
      MCP_HTTP_HOST: tv-mcp
      MCP_HTTP_PORT: "8765"
      # Where lens persists snapshots (also queryable via QuestDB for cross-run analytics)
      QUESTDB_HOST: questdb
      QUESTDB_PG_PORT: "8812"
      LENS_PORT: "9102"
      MT5_COMMON_FILES_DIR: "/mt5"    # lens reads market_data.json for mt5 context
      PYTHONUNBUFFERED: "1"
      TZ: America/New_York
    expose: [ "9102" ]
    volumes:
      - "${MT5_COMMON_FILES_HOST_PATH}:/mt5:ro"  # read-only — only bridge writes back
      - "./logs:/app/logs"
    depends_on:
      tv-mcp: { condition: service_healthy }
      questdb: { condition: service_healthy }
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:9102/health | grep -q ok || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 15s
    logging:
      driver: json-file
      options: { max-size: 30m, max-file: "5" }

  # ── shared-services (herald + reconciler + sentinel, port 9100) ──
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
    expose: [ "9100" ]
    volumes:
      - "aurum-state:/app/python/data/aurum_state"  # herald's Telegram session
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

**Bridge / aurum / athena gain URL env vars** (with USE_* flags during soak):

```yaml
  bridge:
    environment:
      AEGIS_URL: "http://aegis:9101"
      LENS_URL: "http://lens:9102"
      SHARED_SERVICES_URL: "http://shared-services:9100"
      USE_AEGIS: "1"               # 0 = fall back to embedded import
      USE_LENS: "1"
      USE_SHARED_SERVICES: "1"
    depends_on:
      aegis: { condition: service_healthy }
      lens: { condition: service_healthy }
      shared-services: { condition: service_healthy }
      # ... existing depends_on entries

  aurum:
    environment:
      LENS_URL: "http://lens:9102"
      SHARED_SERVICES_URL: "http://shared-services:9100"
      USE_LENS: "1"
      USE_SHARED_SERVICES: "1"
    depends_on:
      lens: { condition: service_healthy }
      shared-services: { condition: service_healthy }

  athena:
    environment:
      AEGIS_URL: "http://aegis:9101"
      USE_AEGIS: "1"
      # status_report stays embedded — no new env needed
    depends_on:
      aegis: { condition: service_healthy }
```

**Total compose post-F7**: 9 services (questdb + tv-mcp + bridge + aurum + athena + listener + aegis + lens + shared-services). 5 of these mirror the launchd topology; 1 is the new F5 MCP daemon; 3 are the new F7 split-outs. Plus questdb is the data backbone — also new vs launchd (lives wherever scribe DB used to be).

#### F7.6 Acceptance criteria (per service)

**Each new service ships with its own checklist before flipping its `USE_*` flag to default-on.**

**aegis acceptance**:
- [ ] `aegis` container up healthy; `/aegis/limits` returns current config
- [ ] With `USE_AEGIS=0`: bridge + athena use embedded `from aegis import ...` (regression baseline)
- [ ] With `USE_AEGIS=1`: every OPEN_GROUP / CLOSE_* / MODIFY_* command in bridge goes through `http://aegis:9101/aegis/validate_*` (verify via aegis access log)
- [ ] Athena UI's "Aegis decisions" panel renders identical content from the new HTTP endpoint vs embedded read
- [ ] **aegis container DOWN**: bridge BLOCKS new commands (fail closed). Verify via `docker compose stop aegis` + Telegram OPEN_GROUP attempt → operator sees rejection
- [ ] Per-call latency `aegis.validate_open_group()` <20ms p99

**lens acceptance**:
- [ ] `lens` container up healthy; `/lens/snapshot` returns recent data after ~5-10s warmup
- [ ] With `USE_LENS=0`: bridge calls `self.lens.fetch_fresh()` embedded (regression baseline)
- [ ] With `USE_LENS=1`: bridge calls `lens_client.get_snapshot()` returning <2ms (cached read) — no MCP roundtrip in bridge tick
- [ ] Lens runs its own poll loop independent of bridge tick cycle; snapshot freshness <60s during active mode
- [ ] Mode transitions: bridge `POST /lens/mode` when mode flips (WATCH→SIGNAL→SCALPER); lens adjusts poll cadence
- [ ] **lens container DOWN**: bridge skips ticks that need fresh data; aurum returns "lens unavailable" for chart queries; AURUM Telegram still works for non-LENS questions
- [ ] AURUM end-to-end: ask "how's gold?" → AURUM calls `lens_client.get_snapshot()` → returns cached data → LLM answers

**shared-services acceptance**:
- [ ] `shared-services` container up healthy
- [ ] With `USE_SHARED_SERVICES=0`: embedded imports work (regression baseline)
- [ ] With `USE_SHARED_SERVICES=1`: every herald/sentinel/reconciler call goes through HTTP (verify via access log)
- [ ] Telegram posts appear with same formatting (herald regression)
- [ ] Component heartbeats in QuestDB at same cadence (sentinel regression)
- [ ] Periodic reconciliation sweeps still run (reconciler regression — check QuestDB markers)
- [ ] **shared-services DOWN**: herald posts dropped with warning log; reconciler/sentinel paused; bridge/aurum continue serving trades (graceful degradation)
- [ ] Per-call HTTP latency <10ms p99

#### F7.7 Rollback (per service, independent)

Each `USE_<SERVICE>` flag is independent:

| Service | Rollback step |
|---|---|
| aegis | `USE_AEGIS=0` in `.env` + `docker compose up -d bridge athena` (containers fall back to embedded). aegis container stays up but idle — no harm. |
| lens | `USE_LENS=0` in `.env` + `docker compose up -d bridge aurum`. lens container stays up idle. |
| shared-services | `USE_SHARED_SERVICES=0` + `docker compose up -d bridge aurum`. |

Independent rollback per service is a deliberate design choice — if lens has a bug post-flip, you can revert lens to embedded without losing the aegis or shared-services HTTP cutover.

#### F7.8 What F7 does NOT do

- **Does not move status_report into a separate container** — stays bundled with `athena_api.py` because the API consumes it on every dashboard render (operator-confirmed 2026-05-16).
- **Does not introduce service mesh / sidecars** — direct HTTP between containers is sufficient at single-host scale.
- **Does not change the QuestDB schema or scribe writes** — same data flow, different process boundary.
- **Does not horizontally scale aegis/lens** — aegis is replicable in principle (stateless) but the bridge would need a load-balancer in front; lens is single-replica only by design (avoid duplicate polling). Both are out of scope.
- **Does not migrate `listener.py`** — already its own launchd service, will be its own compose container in F6. No change in F7.

#### F7.9 Honest payoff at our scale

| Benefit | Real? |
|---|---|
| **Security perimeter** (aegis as separate process) | yes — structural guarantee that all trade commands validate, enforced by network topology not code review |
| **Data acquisition perimeter** (lens as separate process) | yes — lens lifecycle becomes self-contained; bridge tick no longer pays MCP roundtrip cost |
| Independent restart cadence | yes — change herald, restart only shared-services. Change aegis rules, restart only aegis. |
| Independent failure domain | yes, with explicit failure-mode contracts (§F7.3 table). Aegis down = fail closed; lens down = skip ticks; shared-services down = drop optional events. |
| Cleaner observability | yes — per-service logs, per-service metrics endpoints (Prometheus next step) |
| Smaller host service images | yes — bridge image shrinks meaningfully when 5 modules extract |
| Cleaner testing | yes — each service has a clean HTTP contract; can be tested in isolation |

**The payoff is architectural + operational, not raw performance.** At current scale, F7 is a 1-2 week refactor (3 services × ~3-4 days each). Per-call latency goes from 0ms (in-process import) to 5-20ms (HTTP) — but on the LENS path, the win flips: bridge tick stops paying the MCP roundtrip (~50-300ms) because it gets cached snapshots from the lens container.

**Suggested trigger for shipping F7**:
- F6 (containerize) is shipped and stable
- You're adding a new caller for aegis or lens (e.g. a second LLM agent) — second caller is the canonical "extract" signal
- You want to enforce "all trade commands go through aegis" as a network-level guarantee, not a code-review guarantee
- You want to swap the lens implementation (e.g. add a second TV instance, or a non-TradingView data source) without touching bridge/aurum
- You want to add Prometheus metrics + Grafana dashboards per service

Until F6 is stable, F7 is design-only. Don't ship in parallel with F6 — operational risk multiplies.

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
