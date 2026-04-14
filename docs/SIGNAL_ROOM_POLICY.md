# Signal room priority policy (trade selected rooms, watch the rest)
Use this policy to execute only selected Telegram rooms while still ingesting/logging all monitored channels.

## What it does
- LISTENER still reads every channel in `TELEGRAM_CHANNELS`.
- In `SIGNAL`/`HYBRID`, `ENTRY` signals are dispatched only when the room matches `SIGNAL_TRADE_ROOMS`.
- Non-priority rooms are recorded in SCRIBE as `action_taken='WATCH_ONLY'` with `skip_reason='WATCH_ONLY_ROOM_FILTER'`.
- MANAGEMENT messages continue to be processed so open groups can still be managed.
- At startup, LISTENER logs each resolved channel with its match status and writes it into `python/config/listener_meta.json`.

## Configuration
Set room priority in `.env`:
```bash
SIGNAL_TRADE_ROOMS=-1002034822451,-1001959885205
# or alias:
ACTIVE_SIGNAL_TRADE_ROOMS=-1002034822451,-1001959885205
```
Notes:
- Accepts comma-separated channel **titles** and/or **chat IDs** (any form: `-1001234567890`, `1001234567890`, or bare `1234567890`).
- `SIGNAL_TRADE_ROOMS` and `ACTIVE_SIGNAL_TRADE_ROOMS` are both supported; when both are set, entries are merged.
- Matching: NFKC Unicode normalization + whitespace collapse + lowercase. Handles curly apostrophes, trailing spaces, etc.
- chat_id matching tries all variant forms of the Telethon supergroup ID automatically — no need to get the exact sign/prefix right.
- If empty/unset, behavior is legacy: all monitored rooms are tradable (`match_reason=ALLOWED_ALL`).
- `LISTENER_STALE_THRESHOLD_SEC` (default 600) — LISTENER reports `WARN` status if no message received for this long.

## Current recommended setup
- Trade rooms: `Ben's VIP Club`, `FXM FREE TRADING ROOM`
- Watch-only: every other monitored room

## Startup log to expect
After LISTENER connects you should see one line per channel:
```
LISTENER: channel -100xxxxxxxxx = 'Ben's VIP Club'  trade_room=True (ALLOWED_TITLE_MATCH)
LISTENER: channel -100xxxxxxxxx = 'GARRY'S SIGNALS'  trade_room=False (WATCH_ONLY_ROOM_FILTER)
```
If `trade_room=False` for a room you want to trade, add its title or chat_id to `SIGNAL_TRADE_ROOMS` in `.env` and run `make restart`.

## Check allowlist status via API
```bash
curl -sS http://127.0.0.1:7842/api/channels | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'trade_rooms_active={d[\"signal_trade_rooms_active\"]}  listener_status={d[\"listener_status\"]}')
for ch in d['channels']:
    print(f'  {ch[\"name\"]:30s} is_trade_room={ch[\"is_trade_room\"]} match={ch[\"match_reason\"]} watch_only={ch[\"watch_only\"]}')
"
```

## Verification queries
Confirm watch-only routing:
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT id,timestamp,channel_name,action_taken,skip_reason FROM signals_received ORDER BY id DESC LIMIT 20"}'
```
Expected:
- priority rooms: `action_taken` transitions to `EXECUTED` (or gate skips like `AEGIS_REJECTED:LOW_RR`, `AEGIS_REJECTED:TREND_CONFLICT`, etc.)
- non-priority rooms: `action_taken='WATCH_ONLY'` with `skip_reason='WATCH_ONLY_ROOM_FILTER'`

Confirm policy events:
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT timestamp,event_type,reason,notes FROM system_events WHERE event_type='\''SIGNAL_ROOM_WATCH_ONLY'\'' ORDER BY id DESC LIMIT 20"}'
```
`reason` field will be `WATCH_ONLY_ROOM_FILTER` (structured code, not free-text with room name).

Check for successful dispatches:
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT timestamp,reason,notes FROM system_events WHERE event_type='\''SIGNAL_DISPATCHED'\'' ORDER BY id DESC LIMIT 10"}'
```

Check for parse failures (messages received but not recognized as signals):
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT timestamp,notes FROM system_events WHERE event_type='\''SIGNAL_PARSE_FAILED'\'' ORDER BY id DESC LIMIT 10"}'
```
