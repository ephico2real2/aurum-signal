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

**After editing `SKILL.md` or `SOUL.md`:** restart the **aurum** service (or `make restart`) so the running process reloads them — they are read once at AURUM startup.

---

## FORGE ↔ BRIDGE (no MT5 fills)

Groups in ATHENA without broker orders almost always means **`command.json` path mismatch**. See **[FORGE_BRIDGE.md](FORGE_BRIDGE.md)** (symlink `MT5/` to Common Files or use absolute `MT5_*_FILE` paths).

---

## Related docs

- [SETUP.md](SETUP.md) — first-time install, env, Telegram, MT5  
- [FORGE_BRIDGE.md](FORGE_BRIDGE.md) — `command.json` / Common Files alignment  
- [AEGIS.md](AEGIS.md) — full decision logic, rejection codes, env tuning  
- [SENTINEL.md](SENTINEL.md) — calendar currencies, Yahoo/RSS feeds, env  
- [DATA_CONTRACT.md](DATA_CONTRACT.md) — schemas and contracts  
- [SCRIBE_QUERY_EXAMPLES.md](SCRIBE_QUERY_EXAMPLES.md) — example SQL  
