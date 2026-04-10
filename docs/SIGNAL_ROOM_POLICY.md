# Signal room priority policy (trade selected rooms, watch the rest)
Use this policy to execute only selected Telegram rooms while still ingesting/logging all monitored channels.
## What it does
- LISTENER still reads every channel in `TELEGRAM_CHANNELS`.
- In `SIGNAL`/`HYBRID`, `ENTRY` signals are dispatched only when the room matches `SIGNAL_TRADE_ROOMS`.
- Non-priority rooms are recorded in SCRIBE as `action_taken='WATCH_ONLY'` with `skip_reason='ROOM_NOT_PRIORITY:<room>'`.
- MANAGEMENT messages continue to be processed so open groups can still be managed.
## Configuration
Set room priority in `.env`:
```bash
SIGNAL_TRADE_ROOMS=Ben's VIP Club,FXM FREE TRADING ROOM
```
Notes:
- Accepts comma-separated channel titles and/or chat IDs.
- Matching is exact after lowercase/trim normalization.
- If empty/unset, behavior is legacy (all monitored rooms tradable).
## Current recommended setup
- Trade rooms: `Ben's VIP Club`, `FXM FREE TRADING ROOM`
- Watch-only: every other monitored room
## Verification queries
Confirm watch-only routing:
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT id,timestamp,channel_name,action_taken,skip_reason FROM signals_received ORDER BY id DESC LIMIT 20"}'
```
Expected:
- priority rooms: `action_taken` transitions to `EXECUTED` (or concrete gate skips like `LOW_RR`, `TREND_CONFLICT`, etc.)
- non-priority rooms: `action_taken='WATCH_ONLY'` with `ROOM_NOT_PRIORITY:*`
Confirm policy events:
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT timestamp,event_type,reason,notes FROM system_events WHERE event_type='\''SIGNAL_ROOM_WATCH_ONLY'\'' ORDER BY id DESC LIMIT 20"}'
```
