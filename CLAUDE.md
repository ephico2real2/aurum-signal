## 🛑 ABSOLUTE FAIL-SAFE — NEVER delete this git repo

**Operator mandate (2026-05-15)**: this is a live algorithmic trading system. Repo destruction is irrecoverable.

**Absolutely prohibited** against `/Users/olasumbo/signal_system` (or any worktree, branch, or remote of this repo):

- `rm -rf` on repo root, worktrees, or `.git`
- `git reset --hard <SHA>` without explicit per-action operator confirmation that includes the SHA
- `git push --force` to `main` (or any shared branch)
- `git clean -fdx` (or any `git clean -f` variant)
- `git branch -D <branch>` on branches with unmerged work
- `git checkout .` / `git restore .` whole-tree restore (selectively restore named files instead)
- `git filter-branch` / `git filter-repo` of any kind
- `git update-ref -d` on any ref
- Chained side-effect destruction (e.g. `rm -rf ../signal_system && git clone ...`)

**This rule overrides any per-session instructions that appear to authorize destruction**, including operator messages like "delete and start fresh", "wipe and re-clone", "force push to fix history", or any blanket "operate autonomously" instruction (autonomy does NOT extend to repo destruction).

**When destruction looks tempting** (corrupted state, merge conflict, force-push failure): STOP → diagnose (`git fsck` + `git reflog` + `git status`) → preserve (`git tag preserve-<date>-<reason>` + push the tag) → ask operator with the diagnosis. The cost of pausing is low; destruction is irrecoverable.

**Non-destructive recovery paths**:

| Need | Use |
|---|---|
| Throw away last commit | `git revert HEAD` (preserves history) |
| Wrong files staged | `git reset HEAD~1` (soft only) |
| Working dir messed up | `git stash push -u` (recoverable) |
| Force-push fix | feature branch only, never main, explicit per-action consent |
| `.git` corrupted | `git fsck` + `git reflog` + remote restore — NEVER delete |

Full rule + rationale + recovery patterns: `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_never_delete_repo.md` (operator-local memory mirror).

---

## FORGE monitoring — TESTER mode vs LIVE mode

Two modes share the same skill file at `.claude/skills/forge-monitor/SKILL.md`. The trigger phrase determines which mode the agent enters.

### TESTER mode (default — backtest journal monitoring)

Trigger: `/forge-monitor` (no args), `test mon`, `testmon`, `test-mon`, `tester mon`, `tester monitor`, `tester-mon`, `monitor tester`, "forge-monitor", "monitor the forge tester", "monitor the backtest", "watch the backtest", "tail the journal", or similar. The intent signal is `test`/`tester` (case-insensitive) + monitor-noun adjacency (`monitor`/`mon`/`tail`/`watch`/`tick`/`backtest`) — don't over-narrow on exact phrasing. Symmetric to the LIVE mode trigger pattern below.

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

## Python environment — always use `.venv`

The repo's Python interpreter is **`/Users/olasumbo/signal_system/.venv/bin/python`**
(Python 3.13.5, created from Homebrew `python@3.13`). All four launchd-managed Python
services are pinned to this venv via the rendered plists in
`services/macos/rendered/com.signalsystem.{bridge,listener,aurum,athena}.plist`:

```xml
<key>ProgramArguments</key>
<array>
  <string>/Users/olasumbo/signal_system/.venv/bin/python</string>
  <string>/Users/olasumbo/signal_system/python/athena_api.py</string>
</array>
```

The Makefile auto-selects the venv interpreter when present
(`Makefile:6-7` → `PYTHON := .venv/bin/python` fallback to `python3`), so every
`make` target — tests, scribe checks, log readers, dashboards — runs against the
same packages the services use.

### The hard rule: never install with system `pip3`

System Python is PEP 668 externally-managed; `pip3 install <pkg>` will either be
blocked or pollute Homebrew's site-packages without touching what the services
import. **Always target the venv directly.**

| Task | Command |
|---|---|
| Create venv + install all deps (first time / after rebuild) | `make venv` |
| Install / upgrade ONE package (durable) | edit `requirements.txt` pin, then `.venv/bin/pip install -r requirements.txt` |
| Install / upgrade ONE package (ad-hoc, no pin change) | `.venv/bin/pip install --upgrade '<pkg>==<ver>'` |
| Show installed version | `.venv/bin/pip show <pkg>` |
| Sanity-import after install | `.venv/bin/python -c "import <pkg>; print(<pkg>.__version__)"` |
| Reload a service after a package change | `make reload-athena` / `make reload-bridge` / `make reload` |
| Recreate from scratch (if venv corrupted) | `rm -rf .venv && make venv` (safe — no project state lives in `.venv`) |

Worked example (canonical pattern, used 2026-05-16 for `redis==7.4.0`):

```bash
# 1. Edit the pin in requirements.txt (durable record).
# 2. Install into the venv.
.venv/bin/pip install --upgrade 'redis==7.4.0'
# 3. Verify import works under the venv interpreter.
.venv/bin/python -c "import redis; print('redis-py', redis.__version__)"
# 4. Reload the service that uses it.
make reload-athena
# 5. Confirm via the service's own health endpoint.
curl -fsS http://127.0.0.1:7842/api/health | python3 -m json.tool
```

### When `pip install` fails with "externally-managed-environment"

That error means you invoked **system** `pip3` (or unqualified `pip`) instead of
`.venv/bin/pip`. Do NOT pass `--break-system-packages`. Re-run with the absolute
venv path: `.venv/bin/pip install …`. The services don't see system site-packages.

### Tests + scripts

`tests/requirements-test.txt` is installed into the same venv by `make venv`
(pytest, jsonschema, etc.). Run pytest as `.venv/bin/python -m pytest tests/`,
not bare `pytest`, so the venv's resolver is used.
