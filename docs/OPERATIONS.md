# Signal System — Daily operations

Quick reference for restarting components, checking health, and bootstrapping **AURUM** after a refresh.

---

## What runs (four services)

| Service   | Role (short)                          |
|----------|----------------------------------------|
| **bridge**   | Core loop: mode, FORGE, SCRIBE, commands |
| **listener** | Telegram signal channels → LISTENER    |
| **aurum**    | AURUM agent (Telegram + context)       |
| **athena**   | HTTP API + dashboard (`/`, port **7842**) |

Install path: `services/install_services.py` (see [SETUP.md](SETUP.md) STEP 10).

---

## After editing Python code (sentinel, aegis, bridge, etc.)

Fastest path — hot-restart without re-rendering plists:

```bash
make reload           # kill + relaunch all 4 Python processes
make reload-bridge    # just BRIDGE (sentinel/aegis/aurum changes)
```

Launchd auto-relaunches the killed processes with fresh code. Health check runs after.

## After editing `.env` (full restart needed)

Env changes require re-rendering the plist templates:

```bash
make restart
# or: python3 services/install_services.py --restart
```

Common runtime toggles that require this restart: `REGIME_ENGINE_ENABLED`, `REGIME_ENTRY_MODE`, `REGIME_MIN_CONFIDENCE`, and other `REGIME_*` knobs.

This re-renders `services/macos/rendered/*.plist` from templates + `.env`, then reloads launchd.

**How plists work:** Templates live at `services/macos/*.plist`. The installer renders them (injecting `.env` values) into `services/macos/rendered/`. `~/Library/LaunchAgents/` entries are **symlinks** to the rendered files — not copies — so changes are always traceable from the repo.

**Interpreter:** If `.venv` exists at repo root, launchd uses `.venv/bin/python` automatically. Override with env `SIGNAL_PYTHON=/path/to/python` before install if needed.

**Risk gate:** Trade validation is **AEGIS** — see [AEGIS.md](AEGIS.md). Tuning is via **`AEGIS_*`** env vars; **bridge** must be restarted/reloaded to pick them up.
**Execution latency + mode stability:** `BRIDGE_LOOP_SEC` controls BRIDGE tick frequency (lower = faster signal consumption), and `BRIDGE_PIN_MODE` can lock runtime mode (for example `HYBRID`) to prevent accidental drift.

**News / calendar:** **SENTINEL** — ForexFactory multi-currency calendar + free RSS (FXStreet, Google News, Investing.com forex, optional DailyFX/extras). Extended events (speeches, FOMC) hold the guard for 60min. See [SENTINEL.md](SENTINEL.md).

---

## Stop / start (full cycle)

```bash
make stop    # unload all services
make start   # render plists + symlink + load (full install)
```

## Full stack one-command orchestration

Use these when you want all major runtime dependencies handled in order.

```bash
make system-up
make system-down
```

Dependency order:
- `system-up`: TradingView CDP → MetaTrader 5 app → Python services (`bridge`, `listener`, `aurum`, `athena`)
- `system-down`: Python services → TradingView → MetaTrader 5

Individual app controls:

```bash
make mt5-start
make mt5-stop
```

---

## Verify after restart

```bash
make health
```

Spot-check API (default URL):

```bash
curl -s http://localhost:7842/api/health | python3 -m json.tool
open http://localhost:7842
```

Logs:

```bash
make logs-athena
make logs-aurum
make logs-bridge
```

## Market-hours note (fills vs queued requests)

- If `status.json` / ATHENA shows `session=OFF_HOURS` and MT5 quotes are flat (bid/ask not moving), requests can be queued but not filled until market reopen.
- Friday US close through Sunday Asia open is expected low/no-fill window for XAUUSD.
- Treat this as market-state behavior, not automatically as BRIDGE/FORGE failure.

## SCRIBE database GUI (macOS)

Install once:

```bash
brew install --cask db-browser-for-sqlite
```

Open SCRIBE DB:

```bash
make scribe-gui
```

Database file:

```text
python/data/aurum_intelligence.db
```

Quick query checks for threshold-hardening fields:

```sql
SELECT id, source, pending_entry_threshold_points, trend_strength_atr_threshold, breakout_buffer_points
FROM trade_groups
ORDER BY id DESC
LIMIT 10;
```

```sql
SELECT id, source, pending_entry_threshold_points, trend_strength_atr_threshold, breakout_buffer_points
FROM market_snapshots
ORDER BY id DESC
LIMIT 10;
```

Signal-room media replay/back-analysis:

```bash
python3 scripts/replay_signal_uploads.py --limit 5
python3 scripts/replay_signal_uploads.py --channel "FLAIR FX" --limit 10
python3 scripts/replay_signal_uploads.py --limit 5 --notify
```

Evidence events to monitor in SCRIBE `system_events`:
- `SIGNAL_CHART_RECEIVED`
- `SIGNAL_CHART_SUMMARY_SENT` / `SIGNAL_CHART_SUMMARY_FAILED`
- `SIGNAL_CHART_ARCHIVED`
- `SIGNAL_CHART_REPLAYED`
- `UNMANAGED_POSITION_OPEN`
- `UNMANAGED_POSITION_CLOSED`

---

## Dashboard & Activity log

- **ATHENA UI:** `http://localhost:7842` (served by **athena**).
- **Activity tab:** Events are **oldest at top, newest at bottom**; **Pause** stops auto-scroll-to-bottom (polling still updates data unless you add a freeze feature later).

---

## Tests (optional)

```bash
make verify          # health + curls + API pytest + UI Playwright
make test-api
make test-ui-silent  # needs dashboard + API up
```

---

## AURUM — paste this after a full restart (session prompt)

Copy everything in the block below into **AURUM** (ATHENA chat or your Telegram thread with the bot). Adjust the last line if your mode or goal differs.

```
You are AURUM for the Signal System (XAUUSD). Follow SOUL.md: concise, analytical, honest, non-alarming. Follow SKILL.md for capabilities: status from injected context, SCRIBE SQL when asked, trade/mode commands only via BRIDGE (aurum_cmd.json / parsed JSON / exact MODE_CHANGE phrases — file is deleted after BRIDGE consumes it).

We just restarted all services (bridge, listener, aurum, athena). Confirm you have fresh context: mode, MT5 snapshot, open groups, LENS, SENTINEL, today’s stats. If anything is missing, say what’s missing instead of guessing.

Reply in 2–4 sentences: current mode, whether MT5/context looks connected, and one thing worth watching next. Do not execute trades unless I explicitly ask and risk is clear.
```

For **mode switches** and **command JSON** examples, see repo root **SKILL.md** (sections 4–5).

**After editing `SKILL.md` or `SOUL.md`:** no restart is required for prompt behavior updates — AURUM re-reads them on each query. Restart only if you changed service/env/runtime wiring.

---

## FORGE ↔ BRIDGE (no MT5 fills)

Groups in ATHENA without broker orders almost always means **`command.json` path mismatch**. See **[FORGE_BRIDGE.md](FORGE_BRIDGE.md)** (symlink `MT5/` to Common Files or use absolute `MT5_*_FILE` paths).

---

## Deferred analysis runs

AURUM (or any caller) can queue async analyses via the AEB action `ANALYSIS_RUN`. Each run is identified by a `query_id`; the body is persisted to `logs/analysis/<query_id>.md`, the status to `logs/analysis/<query_id>.json`, and the result is posted to the existing Telegram channel through HERALD.

Monitoring:
```bash
# Newest runs
ls -lt logs/analysis/ | head -10

# Lifecycle audit
grep -E 'ANALYSIS_(QUEUED|DONE|FAILED)' logs/audit/system_events.jsonl | tail -20
```

Configuration (in `.env`):
- `ANALYSIS_LOG_DIR` — override result/status directory (default `logs/analysis/`).
- `ANALYSIS_MAX_CONCURRENCY` — worker thread cap (default 4, clamped 1–32).

Full spec: `docs/ARCHITECTURE.md` § *Deferred Analysis Runs*. CLI examples: `docs/CLI_API_CHEATSHEET.md` § *Deferred Analysis Runs*.

---

## Related docs

- [SETUP.md](SETUP.md) — first-time install, env, Telegram, MT5  
- [FORGE_BRIDGE.md](FORGE_BRIDGE.md) — `command.json` / Common Files alignment  
- [AEGIS.md](AEGIS.md) — full decision logic, rejection codes, env tuning  
- [SENTINEL.md](SENTINEL.md) — calendar currencies, Yahoo/RSS feeds, env  
- [DATA_CONTRACT.md](DATA_CONTRACT.md) — schemas and contracts  
- [SCRIBE_QUERY_EXAMPLES.md](SCRIBE_QUERY_EXAMPLES.md) — example SQL  
