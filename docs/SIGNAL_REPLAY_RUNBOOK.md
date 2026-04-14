# Signal replay runbook
Use this runbook to replay signals through LISTENER and confirm ingestion path behavior without waiting for live channel timing.
## What this covers
- `scripts/replay_signal_pickup.py` (text signal replay through LISTENER `_handle_message`)
- `scripts/replay_signal_uploads.py` (replay archived signal-room images through VISION)
## 1) Replay text signal and verify pickup
### Safe pickup-only replay (no trade dispatch)
Run in `WATCH` mode first:
```bash
python3 scripts/replay_signal_pickup.py \
  --text "Sell Gold @ 4780-4776 SL 4786 TP1 4772 TP2 4768" \
  --chat-id -1002034822451 \
  --channel-name "Ben's VIP Club" \
  --mode WATCH \
  --expect-action LOGGED_ONLY
```
### Replay from historical SCRIBE row
```bash
python3 scripts/replay_signal_pickup.py \
  --from-signal-id 220 \
  --mode HYBRID \
  --wait-bridge-sec 20
```
### Success criteria
The script prints JSON. Confirm:
- `picked_up=true`
- `signal_row.id` exists
- `signal_row.action_taken` is present (`LOGGED_ONLY`, `WATCH_ONLY`, `SKIPPED`, `EXECUTED`, etc.)
- Optional: `expect_action_met=true` when `--expect-action` is provided
## 2) Replay archived signal-room images
Replay latest archived uploads:
```bash
python3 scripts/replay_signal_uploads.py --limit 5
```
Replay a specific channel:
```bash
python3 scripts/replay_signal_uploads.py --channel "FLAIR FX" --limit 10
```
Replay and notify Telegram bot chat:
```bash
python3 scripts/replay_signal_uploads.py --limit 5 --notify
```
## 3) Post-replay verification queries
Recent signals:
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT id,timestamp,mode,channel_name,message_id,signal_type,action_taken,skip_reason FROM signals_received ORDER BY id DESC LIMIT 20"}'
```
Recent watch-only room filter events:
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT id,timestamp,event_type,reason,notes FROM system_events WHERE event_type='\''SIGNAL_ROOM_WATCH_ONLY'\'' ORDER BY id DESC LIMIT 20"}'
```
Recent dispatched events:
```bash
curl -sS -X POST http://127.0.0.1:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT id,timestamp,event_type,reason,notes FROM system_events WHERE event_type='\''SIGNAL_DISPATCHED'\'' ORDER BY id DESC LIMIT 20"}'
```
## 4) SQLite quick diagnostics (direct SCRIBE access)
From repo root, use SCRIBE DB path from env (or default):
```bash
DB_PATH="${SCRIBE_DB:-python/data/aurum_intelligence.db}"
```
Latest Ben's VIP rows (all signal types):
```bash
sqlite3 -header -column "$DB_PATH" "
SELECT id,timestamp,mode,channel_name,message_id,signal_type,action_taken,skip_reason
FROM signals_received
WHERE channel_name='Ben''s VIP Club'
ORDER BY id DESC
LIMIT 30;
"
```
Ben's VIP ENTRY rows only:
```bash
sqlite3 -header -column "$DB_PATH" "
SELECT id,timestamp,mode,message_id,direction,entry_low,entry_high,sl,tp1,tp2,action_taken,skip_reason
FROM signals_received
WHERE channel_name='Ben''s VIP Club'
  AND signal_type='ENTRY'
ORDER BY id DESC
LIMIT 30;
"
```
Ben's VIP real Telegram rows only (`message_id < 1000000`, excludes replay-generated IDs):
```bash
sqlite3 -header -column "$DB_PATH" "
SELECT id,timestamp,message_id,signal_type,action_taken,skip_reason
FROM signals_received
WHERE channel_name='Ben''s VIP Club'
  AND message_id < 1000000
ORDER BY id DESC
LIMIT 30;
"
```
Recent global action snapshot (use `datetime(timestamp)` to handle ISO timestamps safely):
```bash
sqlite3 -header -column "$DB_PATH" "
SELECT action_taken,COUNT(*) AS n
FROM signals_received
WHERE datetime(timestamp) >= datetime('now','-6 hours')
GROUP BY action_taken
ORDER BY n DESC;
"
```
Recent AEGIS-gated signals:
```bash
sqlite3 -header -column "$DB_PATH" "
SELECT id,timestamp,channel_name,message_id,action_taken,skip_reason
FROM signals_received
WHERE skip_reason LIKE 'AEGIS_REJECTED:%'
ORDER BY id DESC
LIMIT 30;
"
```
## Notes
- Start with `--mode WATCH` for non-trading verification.
- `--mode SIGNAL` or `--mode HYBRID` can trigger full gating/dispatch behavior.
- For allowlist checks, confirm `/api/channels` shows expected `match_reason` (`ALLOWED_ID_MATCH` / `WATCH_ONLY_ROOM_FILTER`).

## Validation results (captured earlier)
### WATCH replay (picked up as LOGGED_ONLY)
```bash
olas-MacBook-Pro:signal_system olasumbo$ python3 /Users/olasumbo/signal_system/scripts/replay_signal_pickup.py \e doctor or npm i -g @anthropic-ai/claude-code
  --text "Sell Gold @ 4780-4776 SL 4786 TP1 4772 TP2 4768" \
  --chat-id -1002034822451 \
  --channel-name "Ben's VIP Club" \
  --mode WATCH \
  --expect-action LOGGED_ONLY
{
  "ok": true,
  "picked_up": true,
  "replay": {
    "source": "raw_text",
    "mode": "WATCH",
    "chat_id": -1002034822451,
    "channel_name": "Ben's VIP Club",
    "message_id": 178717914
  },
  "signal_row": {
    "id": 240,
    "timestamp": "2026-04-14T14:58:39.011772+00:00",
    "mode": "WATCH",
    "channel_name": "Ben's VIP Club",
    "message_id": 178717914,
    "signal_type": "ENTRY",
    "direction": "SELL",
    "entry_low": 4776.0,
    "entry_high": 4780.0,
    "sl": 4786.0,
    "tp1": 4772.0,
    "tp2": 4768.0,
    "tp3": null,
    "action_taken": "LOGGED_ONLY",
    "skip_reason": null,
    "trade_group_id": null
  },
  "bridge_wait": null,
  "events": [],
  "expect_action": "LOGGED_ONLY",
  "expect_action_met": true
}
```

### HYBRID replay (picked up, skipped by orientation gate before new toggle)
```bash
olas-MacBook-Pro:signal_system olasumbo$ python3 /Users/olasumbo/signal_system/scripts/replay_signal_pickup.py \
  --from-signal-id 220 \
  --mode HYBRID \
  --wait-bridge-sec 20
{
  "ok": true,
  "picked_up": true,
  "replay": {
    "source": "signals_received.id=220",
    "mode": "HYBRID",
    "chat_id": -1002034822451,
    "channel_name": "Ben's VIP Club",
    "message_id": 178743004
  },
  "signal_row": {
    "id": 241,
    "timestamp": "2026-04-14T14:59:04.092448+00:00",
    "mode": "HYBRID",
    "channel_name": "Ben's VIP Club",
    "message_id": 178743004,
    "signal_type": "ENTRY",
    "direction": "SELL",
    "entry_low": 4774.6,
    "entry_high": 4784.6,
    "sl": 4788.6,
    "tp1": 4770.6,
    "tp2": 4764.6,
    "tp3": null,
    "action_taken": "SKIPPED",
    "skip_reason": "AEGIS_REJECTED:SIGNAL_SELL_LIMIT_REQUIRED:entry_high=4784.60<=market=4803.30",
    "trade_group_id": null
  },
  "bridge_wait": {
    "waited_sec": 1.01,
    "action_taken": "SKIPPED",
    "skip_reason": "AEGIS_REJECTED:SIGNAL_SELL_LIMIT_REQUIRED:entry_high=4784.60<=market=4803.30",
    "trade_group_id": null,
    "terminal": true
  },
  "events": [
    {
      "id": 2355,
      "timestamp": "2026-04-14T14:59:04.094948+00:00",
      "event_type": "SIGNAL_DISPATCHED",
      "reason": "SIGNAL_DISPATCHED",
      "notes": "channel=Ben's VIP Club chat_id=-1002034822451 signal_id=241 direction=SELL match=ALLOWED_ID_MATCH"
    }
  ]
}
```
