# LENS MCP — Fork & Enhancement Plan

**Status**: F1 shipped + F2 PR open ([upstream #42](https://github.com/LewisWJackson/tradingview-mcp-jackson/pull/42)); F4 committed local-only on `feat/cdp-reconnect` ([fork branch](https://github.com/ephico2real2/tradingview-mcp-aurum/tree/feat/cdp-reconnect)) — awaiting PR #42 maintainer feedback before upstream submission; F3 + F5 pending
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
