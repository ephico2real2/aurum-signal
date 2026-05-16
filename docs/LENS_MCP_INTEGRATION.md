# LENS ↔ TradingView MCP Integration

**Last updated**: 2026-05-16
**Scope**: how the FORGE Signal System reads live chart state from TradingView via the Model Context Protocol (MCP) server, with two consumers — the LENS poll loop (BRIDGE-side, ~60s cadence) and AURUM (on-demand, agent-driven).

## TL;DR

1. **MCP server** — local Node process forked from [LewisWJackson/tradingview-mcp-jackson](https://github.com/LewisWJackson/tradingview-mcp-jackson), checked out at `$HOME/tradingview-mcp-jackson`. Connects to a Chrome instance on CDP port `:9222` that has TradingView Desktop loaded.
2. **MCP tools** — chart navigation, indicator queries, Pine box/line reads, screenshot capture, watchlist mgmt (full module list below).
3. **LENS** (`python/lens.py`) — spawns the MCP per-poll, fetches a curated snapshot, writes `config/lens_snapshot.json` for BRIDGE / Athena / Aurum context injection.
4. **AURUM** (SKILL.md §1b) — on-demand MCP calls (`chart_get_state`, `quote_get`, `data_get_study_values`, `capture_screenshot`, etc.) for both daily Q&A and AI-backed trade decisions.
5. **Rules** — single source of truth in `config/tradingview_rules.json`, symlinked into the MCP repo on every `make update-lens-mcp`. Currently a "Gold Intraday Bias & Pullback" XAUUSD strategy.
6. **Make targets** — `make update-lens-mcp` pulls upstream + verifies; `make clean-mcp-git-stash` removes the routine `rules.json` auto-stashes the update script leaves behind.

## Stack

```
┌────────────────────────────────┐
│   TradingView Desktop          │
│   (Chrome wrapper, CDP :9222)  │
└──────────────┬─────────────────┘
               │ CDP (Chrome DevTools Protocol)
               │ — page eval, screenshots, layout queries
               ▼
┌────────────────────────────────┐
│   TradingView MCP server       │      $HOME/tradingview-mcp-jackson/
│   (Node, MCP stdio transport)  │      src/server.js
│   modules: chart, data,        │
│   indicators, capture, pine,   │
│   morning, alerts, watchlist…  │
└──────┬──────────────────┬──────┘
       │                  │
       │ stdio (per-call) │ stdio (per-poll)
       ▼                  ▼
┌─────────────────┐   ┌─────────────────────────────────┐
│  AURUM          │   │  LENS (python/lens.py)          │
│  SKILL.md §1b   │   │  poll every ~60s, write         │
│  on-demand      │   │  config/lens_snapshot.json      │
│  tool calls     │   └──────────────┬──────────────────┘
└─────────────────┘                  │
                                     ▼
                       BRIDGE / Athena read snapshot
                       AURUM prompt context reads it
```

## File layout

| Path | Purpose |
|---|---|
| `$HOME/tradingview-mcp-jackson/` | MCP fork checkout (gitignored from our repo) |
| `$HOME/tradingview-mcp-jackson/src/server.js` | MCP server entry — what `npx tradingview-mcp-jackson` / `node src/server.js` runs |
| `$HOME/tradingview-mcp-jackson/src/core/` | Tool implementations: `alerts`, `batch`, `capture`, `chart`, `data`, `drawing`, `health`, `indicators`, `morning`, `pane`, `pine`, `replay`, `stream`, `tab`, `ui`, `watchlist` |
| `$HOME/tradingview-mcp-jackson/rules.json` | **Symlink** → `config/tradingview_rules.json` (refreshed by `make update-lens-mcp`) |
| `config/tradingview_rules.json` | Canonical rules — operator-edited; survives MCP updates |
| `python/lens.py` | LENS poll loop + snapshot writer |
| `python/mcp_client.py` | MCP stdio client wrapper |
| `config/lens_snapshot.json` | Latest LENS snapshot (BRIDGE / Athena / AURUM read this) |

## Active rules config (current)

`config/tradingview_rules.json` carries the **"Gold Intraday Bias & Pullback"** strategy:

- **Watchlist**: `["XAUUSD"]`
- **Default timeframe**: `5` (minute)
- **Primary indicators**: EMA(20/50) trend filter, RSI(14) momentum, MACD histogram, ADX/DI strength
- **Bias criteria** (bullish): EMA20 > EMA50 AND RSI 50–70 AND MACD histogram > 0 AND DI+ > DI-
- **Bias criteria** (bearish): mirror
- **Neutral** (skip): ADX < 15 OR RSI > 72 / < 28 OR EMA flat/crossing

AURUM reads this file directly via MCP `data_get_study_values` and applies it to chart state to produce a bias label.

## LENS poll loop

`python/lens.py:255-260` documents the model:

> Spawn MCP server, send one request, read response, kill process.

Each LENS tick:

1. Builds an argv from `LENS_MCP_CMD` env var (default `npx tradingview-mcp-jackson`).
2. Opens a fresh subprocess via `MCPSession` (stdio transport, MCP JSON-RPC).
3. Issues the configured tool calls — typically `chart_get_state` + `data_get_study_values` + `quote_get`.
4. Normalizes the response into a `LensSnapshot` dataclass.
5. Writes `config/lens_snapshot.json` + logs a `LENS_MCP` market snapshot to SCRIBE.
6. Closes the MCP subprocess.

Cadence: tied to the BRIDGE tick cycle (~60s nominal, can stretch under heavy scribe sync). Health is exposed via `/api/live` → `tradingview_age_sec` and `lens_age_sec` in the dashboard.

**Why spawn-per-call** (rather than long-running session): isolation. A wedged MCP call doesn't block the next tick, and Chrome/CDP reconnection gets a fresh handshake each time. Cost is ~200–400ms of subprocess startup per poll — acceptable for 60s cadence.

## AURUM consumer

SKILL.md §1b instructs AURUM to call MCP tools directly when chart state is needed:

| MCP tool | When AURUM uses it |
|---|---|
| `chart_get_state` | "what symbol / timeframe is the chart on?" |
| `quote_get` | latest tick, gold price answers |
| `data_get_study_values` | reading the configured indicator values into the bias criteria |
| `data_get_pine_boxes` / `data_get_pine_lines` | reading custom Pine script overlays (S/R levels, fib zones) |
| `chart_set_symbol` / `chart_set_timeframe` | navigating before a query if the operator asked about a different symbol |
| `chart_manage_indicator` | rare — adding/removing an indicator |
| `capture_screenshot` | vision queries; operator asks "what does this chart look like right now" |

Results are stamped to scribe `system_events` as `AURUM_MCP_RESULT_CAPTURED` (visible in dashboard activity log). The CVD proxy logic in `python/aurum.py:1248` normalises `data_get_study_values` output for divergence hints.

## Make targets

### `make update-lens-mcp`

Pulls the upstream MCP, runs `npm install`, verifies the server starts, and re-symlinks `rules.json`. Run after a hardware change or when a new upstream feature is needed. Detail: `Makefile:591-620`.

**Side-effect**: at line 598, the script runs `git -C "$LENS_MCP_DIR" stash --include-untracked` before pulling. This auto-stash exists to handle the case where the operator was hacking on the MCP fork — but it ALSO fires every time on a clean tree, leaving a stale stash whose only "change" is the routine `rules.json` symlink-overwrite (or sometimes an empty stash from `--include-untracked` on a clean tree). Over months, these accumulate.

Output ends with:

```
  Version: <git short-sha> <commit subject>
  Path:    $HOME/tradingview-mcp-jackson/src/server.js
✅ LENS MCP updated. BRIDGE picks up changes on next LENS fetch cycle.
```

### `make clean-mcp-git-stash`

Drops the stale `rules.json` auto-stashes left by `update-lens-mcp`. Safety-checked: refuses to drop any stash that touches a file other than `rules.json`, so legitimate WIP on the MCP fork is never lost.

Logic:

1. Aborts if `$LENS_MCP_DIR/.git` is missing.
2. Lists every stash.
3. For each stash: reads `git stash show --name-only`. Accepts:
   - **Empty stash** (no tracked changes — `--include-untracked` artifact on a clean tree).
   - **`rules.json` only** (the routine symlink-overwrite artifact).
4. Aborts with a manual-review message if any stash touches additional files.
5. Drops all stashes when safe.
6. Idempotent — re-running on a clean state prints `✅ No MCP stashes to clean.`

Reference: `Makefile:623-664`.

## Operational notes

- **Chrome CDP port**: TradingView Desktop must be launched with `--remote-debugging-port=9222` (handled by `make start-tradingview`). Verify with `make check-tradingview`.
- **Health signal**: `/api/live` returns `tradingview_age_sec` and `lens_age_sec` — both should stay under ~120s during active polling. `> 600s` flags as WARN in `make health` and almost always indicates one of: BRIDGE down, TradingView Desktop closed, MCP server broken (npm dep regression, port not listening).
- **MCP feedback loop logging**: every tool result is captured to runtime context via the `AURUM_MCP_RESULT_CAPTURED` system_event. `python/aurum.py` exposes `MCP FEEDBACK LOOP` blocks in prompt context with tool name, timestamp, summary, freshness.
- **`data_get_study_values` normalisation**: CVD divergence detection requires the `up`/`down` study output; AURUM's normalizer (`python/aurum.py`) emits `cvd_divergence_hint` ∈ `{BUYING_PRESSURE_RISING, SELLING_PRESSURE_RISING, FLAT, UNKNOWN}`.

## Recent updates

| Commit | Change | Impact |
|---|---|---|
| `5d6d7bc` (2026-05-15) | `capture.js` adds `sanitiseFilename()` — strips path separators, parent-dir refs, control chars. Allows only `[A-Za-z0-9._-]`. | **Security hardening** — prevents path traversal via maliciously-crafted filenames in `capture_screenshot` calls. No effect on default-filename behaviour. |
| `1ada068` | gitignore `.env`, lock npm audit fixes | Cleaner repo hygiene upstream |
| `1725605` | validate user-supplied paths and dates | Security |
| `01c193a` | Fix asset locking — retry sell with lock-aware error parsing | Upstream-only path (their reference scalper), no effect on our FORGE-driven flow |
| `3b448c8` | Add VWAP+RSI(3)+EMA(8) 10s scalper, rules.json scalping strategy | Upstream sample; our `tradingview_rules.json` is the canonical operator file via symlink |
| `bc8a60f` | Add morning brief workflow | Used by `morning.js` — exposed as a tool AURUM could call |

## Troubleshooting

| Symptom | First check |
|---|---|
| `/api/live` `lens_age_sec > 600` | `make check-tradingview` — is CDP up? `tail logs/bridge.log` — any MCP spawn errors? |
| `make update-lens-mcp` fails at `npm install` | Node version mismatch — MCP requires Node ≥ 20. `node --version` |
| `make update-lens-mcp` adds yet another stale stash | Run `make clean-mcp-git-stash` post-update |
| AURUM says "TradingView MCP unavailable" | Same as stale snapshot — fix the CDP / MCP path before debugging AURUM logic |
| MCP server starts then dies | `node $HOME/tradingview-mcp-jackson/src/server.js` directly — read stderr |
| `rules.json` no longer symlinked | `ls -la $HOME/tradingview-mcp-jackson/rules.json` — should show `→ <repo>/config/tradingview_rules.json`. Re-run `make update-lens-mcp` to restore. |

## Changelog

| Date | Change |
|---|---|
| 2026-05-16 | Added `make clean-mcp-git-stash` target; created this doc. |
| 2026-05-15 | Pulled upstream `5d6d7bc` — `sanitiseFilename()` security fix. |
