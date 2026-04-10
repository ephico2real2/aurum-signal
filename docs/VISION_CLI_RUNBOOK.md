# VISION CLI Runbook (LISTENER + AURUM + SCRIBE Proof)
This runbook captures the exact CLI workflow used to validate screenshot extraction, signal linkage, and Telegram image-processing behavior.
## Goal
- Verify image ingestion works for both:
  - LISTENER (scraped channel path)
  - AURUM (direct Telegram bot image path)
- Prove writes in SCRIBE:
  - `vision_extractions`
  - `signals_received.signal_source_type` and `vision_extraction_id`
- Confirm extracted numeric chart levels (e.g., pinned levels like `4754.54`) when visible.
## Sample files used
- `/Users/olasumbo/Downloads/screenshot_tradingview_charts.jpg`
- `/Users/olasumbo/Downloads/screenshot_from_bens_vip.png`
## Command-by-command flow
### 1) Verify sample file exists
```bash
ls ~/Downloads/screenshot_from_bens_vip.png
```
What it does:
- Ensures the replay target file exists before running the pipeline.
Expected result:
- Prints full path if present.
### 2) Restart services cleanly
```bash
make restart
```
What it does:
- Reloads all launchd services: BRIDGE, LISTENER, AURUM, ATHENA.
- Re-renders service plist files and reloads LaunchAgents.
Expected result:
- `✓ Loaded: com.signalsystem.<component>` for each service.
### 3) Confirm API/brief endpoint response
```bash
curl -sS http://127.0.0.1:7842/api/brief
```
What it does:
- Confirms ATHENA is serving persisted TradingView brief payload.
Expected result:
- JSON payload from brief store (or unavailable payload if not yet generated).
### 4) Replay screenshot through LISTENER + AURUM
```bash
python3 - <<'PY'
# (uses a small replay harness)
# - loads .env
# - simulates LISTENER message with text+image (MIXED)
# - calls AURUM image handler for direct-bot style path
PY
```
What it does:
- Exercises production code paths without waiting for live Telegram traffic.
- Writes runtime records through normal logging flow.
Expected result:
- LISTENER path logs signal + vision extraction.
- AURUM path logs vision extraction and returns summary/low-confidence response.
### 5) Query SCRIBE proof rows
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT id,timestamp,caller,source_channel,confidence,extracted_text,structured_data,downstream_result,linked_signal_id FROM vision_extractions ORDER BY id DESC LIMIT 10"}'
```
What it does:
- Shows latest VISION extraction records and payloads.
Expected result:
- New rows for `LISTENER` and `HERALD`/`AURUM` callers.
- `confidence`, `extracted_text`, and `structured_data` visible.
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT id,timestamp,channel_name,signal_source_type,vision_extraction_id,vision_confidence,action_taken FROM signals_received ORDER BY id DESC LIMIT 10"}'
```
What it does:
- Proves non-text signal rows and linkage IDs are being captured.
Expected result:
- `signal_source_type` = `MIXED` or `IMAGE` where applicable.
- `vision_extraction_id` populated.
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT sr.id AS signal_id,sr.signal_source_type,sr.vision_extraction_id,ve.id AS vision_id,ve.caller,ve.confidence,ve.downstream_result,ve.linked_signal_id FROM signals_received sr JOIN vision_extractions ve ON sr.vision_extraction_id=ve.id ORDER BY sr.id DESC LIMIT 10"}'
```
What it does:
- Confirms cross-table linkage correctness.
Expected result:
- `sr.vision_extraction_id == ve.id`
- `ve.linked_signal_id == sr.id` for LISTENER-linked rows.
## Service-mode reliability verification commands (launchd)
Use these when validating real runtime behavior (not only replay harnesses).
### A) Restart all services with rendered plists
```bash
make restart
```
What it does:
- Re-renders service plists and reloads `com.signalsystem.{bridge,listener,aurum,athena}`.
- Prints the interpreter path selected for services.
Expected result:
- `Python for services: /Users/<user>/signal_system/.venv/bin/python`
- `✓ Loaded: com.signalsystem.<component>` for all four services.
### B) Confirm launchd process health
```bash
launchctl list | grep com.signalsystem
```
What it does:
- Shows PID/exit-code for each service.
Expected result:
- Non-`-` PID and exit code `0` for listener, bridge, aurum, athena.
### C) Confirm component heartbeat API
```bash
curl -sS http://127.0.0.1:7842/api/components
```
What it does:
- Returns consolidated heartbeat state for all components.
Expected result:
- `LISTENER` and `AURUM` status `OK`.
- Overall healthy count includes all components.
### D) Run system health summary
```bash
make health
```
What it does:
- Runs built-in project health checks against API/live/components/DB/MT5/.env.
Expected result:
- `Overall: ✅ OK`.
### E) Syntax-check critical modules
```bash
.venv/bin/python -m py_compile python/listener.py python/herald.py python/vision.py services/install_services.py
```
What it does:
- Catches syntax/runtime import issues in changed service-critical modules.
Expected result:
- No output, exit code `0`.
### F) Run focused regression tests
```bash
.venv/bin/python -m pytest tests/services/test_resolve_signal_python.py tests/api/test_vision_listener_aurum.py -v -m unit --tb=short
```
What it does:
- Verifies service interpreter selection + LISTENER/AURUM image integration behavior.
Expected result:
- All tests pass.
## CLI signal replay runbook (execute a historical signal now)
Use this to replay an earlier Telegram signal through BRIDGE/FORGE in real service mode.
### 1) Pick a historical signal payload
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT id,timestamp,channel_name,signal_type,direction,entry_low,entry_high,sl,tp1,tp2,tp3,tp3_open,substr(raw_text,1,180) AS raw_text FROM signals_received WHERE channel_name LIKE '\''%Ben%'\'' AND signal_type='\''ENTRY'\'' ORDER BY id DESC LIMIT 20"}'
```
What it does:
- Returns candidate historical `ENTRY` rows (example: Ben's channel signals).
Expected result:
- Pick one row with complete `direction/entry/sl/tp1`.
### 2) Ensure BRIDGE is in execution mode
```bash
curl -sS -X POST http://127.0.0.1:7842/api/mode \
  -H 'Content-Type: application/json' \
  -d '{"mode":"SIGNAL"}'
sleep 6
curl -sS http://127.0.0.1:7842/api/mode
```
What it does:
- Queues mode change and verifies `effective_mode` for execution.
Expected result:
- `mode` and `effective_mode` are `SIGNAL`.
### 3) Write replay payload to parsed_signal.json with a fresh timestamp
```bash
python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
payload = {
  "signal_id": 82,
  "direction": "SELL",
  "entry_low": 4724.5,
  "entry_high": 4734.5,
  "sl": 4738.5,
  "tp1": 4720.5,
  "tp2": 4716.0,
  "tp3": None,
  "tp3_open": True,
  "channel": "Ben's VIP Club",
  "edited": False,
  "timestamp": datetime.now(timezone.utc).isoformat()
}
Path("python/config/parsed_signal.json").write_text(json.dumps(payload, indent=2))
print(json.dumps(payload, indent=2, default=str))
PY
```
What it does:
- Injects one replay command into BRIDGE's normal signal file-bus input.
Expected result:
- BRIDGE consumes the payload on next loop tick (~5s).
### 4) Verify execution outcome
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT id,timestamp,signal_type,direction,entry_low,entry_high,sl,tp1,tp2,action_taken,skip_reason,trade_group_id FROM signals_received WHERE id=82"}'
```
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT id,timestamp,mode,source,signal_id,direction,status,entry_low,entry_high,sl,tp1,tp2,tp3,magic_number FROM trade_groups WHERE signal_id=82 ORDER BY id DESC LIMIT 5"}'
```
```bash
curl -sS http://127.0.0.1:7842/api/live
```
What it does:
- Confirms whether BRIDGE executed or skipped the replay and whether a `trade_group` exists.
Expected result:
- If executed: `action_taken=EXECUTED`, `trade_group_id` populated, group visible in live/open group feeds.
- If skipped: `action_taken=SKIPPED` with a concrete gate reason (e.g., trend conflict).
## Step-by-step extraction notes from ben_vip screenshot
### Initial behavior (before reliability fixes)
- Integration worked (rows/logging/linkage), but extraction quality often returned:
  - `confidence=LOW`
  - `structured_data={"type":"IGNORE"}`
### Improvements applied
1. **Structured Claude output** via `output_config.format` JSON schema.
2. **Chart-focused extraction prompt** emphasizing pinned price labels.
3. **Second pass** on right-side price axis when first pass is low/empty.
4. **Optional OCR numeric hints** using OpenCV + pytesseract.
5. **MIME fix** for extensionless temp media (`*.img`) from Telegram download path.
### Post-fix result pattern
- LISTENER and AURUM paths can now produce `confidence=HIGH` on sample screenshot.
- `structured_data` includes:
  - `instrument` (e.g., `XAUUSD`)
  - `timeframe` (e.g., `M1`)
  - `pinned_levels` including visible chart ladder prices and pinned level.
### Latest verified outcomes
- Services running under launchd with `.venv` interpreter selection.
- `make health` reports `Overall: ✅ OK`.
- Focused regressions pass (`11 passed`) for vision/listener/aurum + service interpreter resolution.
- DB linkage verified with rows where:
  - `signals_received.signal_source_type='MIXED'`
  - `signals_received.vision_extraction_id = vision_extractions.id`
  - `vision_extractions.linked_signal_id = signals_received.id`
- Direct AURUM/HERALD image path verified via `vision_extractions.caller='HERALD'` and `source_channel='direct'`.
## Troubleshooting
### LISTENER extraction shows `VALIDATION_ERROR:unsupported media type: application/octet-stream`
Cause:
- Telegram temp file had no meaningful extension and MIME was guessed incorrectly.
Fix:
- Use content-based MIME detection via Pillow format inspection.
### AURUM/HERALD error: `asyncio.run() cannot be called from a running event loop`
Cause:
- `herald.send()` sync wrapper called from async context.
Impact:
- Notification send fails in that call path; extraction/logging may still succeed.
Action:
- Refactor `Herald.send` usage in async paths to avoid nested `asyncio.run`.
## Quick verification script (when no new live signals)
Use this script to verify the LISTENER vision pipeline state from SCRIBE without waiting for fresh channel traffic.
```bash
python3 - <<'PY'
import sqlite3
db='/Users/olasumbo/signal_system/python/data/aurum_intelligence.db'
c=sqlite3.connect(db); c.row_factory=sqlite3.Row
print('events:')
for r in c.execute("SELECT timestamp,event_type,notes FROM system_events WHERE event_type LIKE 'SIGNAL_CHART_%' ORDER BY id DESC LIMIT 5"): print(dict(r))
print('signals:')
for r in c.execute("SELECT timestamp,channel_name,signal_source_type,action_taken,vision_confidence,substr(raw_text,1,80) raw FROM signals_received ORDER BY id DESC LIMIT 5"): print(dict(r))
print('vision:')
for r in c.execute("SELECT timestamp,source_channel,confidence,downstream_result,error FROM vision_extractions WHERE caller='LISTENER' ORDER BY id DESC LIMIT 5"): print(dict(r))
PY
```
Expected:
- `events` shows recent `SIGNAL_CHART_RECEIVED` / `SIGNAL_CHART_DOWNLOAD_FAILED` entries if media hit LISTENER.
- `signals` shows `signal_source_type` (`IMAGE`/`MIXED`) and `action_taken` (e.g., `LOGGED_ONLY` in WATCH mode).
- `vision` shows the latest LISTENER extraction outcome (`confidence`, `downstream_result`, `error`).
## Replay most recent signal-room uploads from local archive
LISTENER archives signal-room media to `data/signal_media_archive/` (configurable with `LISTENER_SIGNAL_MEDIA_ARCHIVE_DIR`).
Re-run analysis on recent uploads:
```bash
python3 scripts/replay_signal_uploads.py --limit 5
```
Replay and also send summaries to your Telegram bot chat:
```bash
python3 scripts/replay_signal_uploads.py --limit 5 --notify
```
Replay only a specific channel:
```bash
python3 scripts/replay_signal_uploads.py --channel "FLAIR FX" --limit 10
```
## Related docs
- `docs/SETUP.md` (setup and service lifecycle)
- `docs/CLI_API_CHEATSHEET.md` (quick command/API usage)
- `docs/SCRIBE_QUERY_EXAMPLES.md` (query patterns)
