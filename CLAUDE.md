## FORGE monitoring — TESTER mode vs LIVE mode

Two modes share the same skill file at `.claude/skills/forge-monitor/SKILL.md`. The trigger phrase determines which mode the agent enters.

### TESTER mode (default — backtest journal monitoring)

Trigger: `/forge-monitor` (no args), "forge-monitor", "monitor the forge tester", "watch the backtest", "tail the journal", or similar.

Key paths:
- Journal DB: `$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/.../FORGE_journal_*_tester.db`
- Query reference (writable): `docs/FORGE_TESTER_JOURNAL_QUERIES.md`
- Per-run analysis output: `docs/FORGE_RUN<aurum_run_id>_ANALYSIS.md`

### LIVE mode (live broker monitoring via scribe)

Trigger: any message containing the word `live` (case-insensitive) AND a monitor-related token (`monitor`, `mon`, `forge-monitor`, `tail`, `watch`, `tick`). Recognised forms include `/forge-monitor live`, `live /forge-monitor`, `live forge-monitor`, `live mon`, `live monitor`, `live monitors`, `live-mon`, `monitor live`, "watch the live broker", "tail live FORGE", or similar. The intent signal is `live` + monitor-noun adjacency — don't over-narrow on exact phrasing.

Key paths:
- Scribe DB: `python/data/aurum_intelligence.db` (read with `sqlite3 "file:${DB}?mode=ro&immutable=1"` to bypass WAL locks)
- Live broker state: `~/Library/Application Support/.../Common/Files/market_data.json`
- Per-day analysis output: `docs/FORGE_LIVE_<YYYY-MM-DD>_ANALYSIS.md`

Full LIVE mode protocol (data sources, replacement queries, mandatory checks, reporting differences) is in `.claude/skills/forge-monitor/SKILL.md` → "LIVE MODE — monitor the live broker EA instead of the tester" section. Both modes use the same housekeeping checks, PEMCG asymmetry audit, GFM-mandatory output rules, and recommendations pattern.

The CLI command `.claude/commands/forge-monitor.md` delegates to the same skill file — pass `live` as the arg to enter LIVE mode.

### Cheat sheet (TESTER-mode only)

The cheat sheet `docs/FORGE_TESTER_JOURNAL_QUERIES.md` is a living document. New tables and refined queries discovered during TESTER-mode monitoring sessions are auto-appended under `## Discovered Queries (auto-added by /forge-monitor)` and `## Query revisions (auto-added by /forge-monitor)`. Hand-curated entries above those sections are never modified.

## Service operations — ALWAYS use Makefile targets

`Makefile` is at the repo root: `/Users/olasumbo/signal_system/Makefile`. Before
restarting, reloading, or compiling anything in this project, **check `make help`
first** — there is almost certainly a target for it. Do NOT reach for raw
`kill <pid>`, `launchctl unload/load`, `pkill`, or `pgrep loops` — those break
because the launchd `KeepAlive.Crashed=true` policy ignores clean SIGTERM exits,
and the Makefile targets already encode the correct unload/load sequence + a
post-restart health probe.

### Most-used service / EA targets

| When you want to… | Run |
|---|---|
| Reload ATHENA after editing `python/athena_api.py` or config | `make reload-athena` (port :7842 health check) |
| Reload BRIDGE after editing `python/bridge.py` / sentinel / aegis / aurum | `make reload-bridge` |
| Reload ALL Python services (bridge + listener + aurum + athena) | `make reload` (alias: `make reload-all`) |
| Full reinstall + reload all (re-renders launchd plists) | `make restart` (alias: `make services-restart`) |
| Install/start services first time | `make start` |
| Stop all services | `make stop` |
| Status of all services | `make status` |
| **Compile FORGE.mq5 → FORGE.ex5** after editing the EA | `make forge-compile` (regens scalper_config first, then triggers MetaEditor compile) |
| Same + open MetaTrader 5 | `make forge-refresh` |
| forge-compile + restart MT5 + verify new version is live | `make forge-reload` |
| Sync config without recompiling EA | `make scalper-env-sync` |
| Copy-only config sync to MT5 Common Files | `make scalper-config-sync` |
| Verify FORGE is live | `make forge-verify-live` |

### Logs

| Service | Target |
|---|---|
| All services, last 30 lines | `make logs` |
| Errors only | `make logs-errors` |
| BRIDGE / LISTENER / AURUM / ATHENA live tail | `make logs-bridge` / `make logs-listener` / `make logs-aurum` / `make logs-athena` |
| SCRIBE trade writes live | `make scribe-watch` |
| FORGE SKIP rollup (24h) | `make monitor-forge-skips` |

### Tests

| Slice | Target |
|---|---|
| Full sweep | `make test` |
| API only | `make test-api` |
| Journal-focused | `make test-journal` |
| Contracts (OpenAPI / JSON Schema) | `make test-contracts` |
| Fast bisect baseline | `make test-phase1-baseline` |
| Health + key API curls + pytest + Playwright | `make verify` |

### Journal / tester DB management

| Task | Target |
|---|---|
| Summary of FORGE journal DBs + SCRIBE mirror | `make journal-diagnose` |
| List all run_ids with signals/deals/P&L | `make journal-list` |
| Purge one run | `make journal-reset-run RUN=N` |
| Keep specific runs, purge rest | `make journal-keep-runs RUNS=N,M` |
| Wipe `aurum_tester.db` entirely | `make tester-db-reset` |

Run `make help` to see the full list (698-line Makefile). When in doubt about a
target, grep the Makefile for it — every `.PHONY` block has a header comment
explaining what it does.
