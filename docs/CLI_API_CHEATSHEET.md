# CLI API Cheat Sheet — ATHENA Signal System

Base URL: `http://localhost:7842`
Swagger UI: `http://localhost:7842/api/docs/`
Replay workflow: `docs/VISION_CLI_RUNBOOK.md#cli-signal-replay-runbook-execute-a-historical-signal-now`
Signal-room media replay: `python3 scripts/replay_signal_uploads.py --limit 5`

---

## Simulating Trades (Testing)

Simulate a channel ENTRY signal (bypasses Telegram, goes straight to BRIDGE):
```bash
python3 -c "
import json
from datetime import datetime, timezone
from pathlib import Path

signal = {
    'type': 'ENTRY',
    'direction': 'BUY',       # or 'SELL'
    'entry_low': 4663.50,     # bottom of entry zone
    'entry_high': 4664.00,    # top of entry zone
    'sl': 4660.25,            # stop loss
    'tp1': 4669.00,           # take profit 1
    'tp2': 4674.00,           # take profit 2 (optional)
    'tp3': None,
    'tp3_open': True,
    'signal_id': 9999,
    'channel': 'TEST_CHANNEL',
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'edited': False,
}
Path('python/config/parsed_signal.json').write_text(json.dumps(signal, indent=2))
print('Signal written — BRIDGE processes on next tick (~5s)')
print('Uses SIGNAL_LOT_SIZE + SIGNAL_NUM_TRADES from .env')
"
```

## Ask AURUM: “what passes AEGIS now?”

Send directly to AURUM via API:
```bash
curl -sS -X POST http://localhost:7842/api/aurum/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"Based on current /api/live market state, what trade setup is most likely to pass AEGIS right now? Return direction, entry zone, SL, TP1, and why it passes trend/risk gates."}'
```

Recommended Telegram message to AURUM:
```text
Based on live market state right now, give me ONE setup most likely to pass AEGIS.
Include:
- direction (BUY/SELL)
- entry range
- SL
- TP1
- short gate check (trend alignment + risk notes)
If nothing is safe, reply PASS with the exact blocker.
```

Optional: include live context in the same query
```bash
curl -sS http://localhost:7842/api/live | python3 -m json.tool
```
Then send a follow-up:
```text
Using this live snapshot, propose only an AEGIS-pass setup for source=SIGNAL.
If it would fail, explain exact reject reason format (e.g., TREND_CONFLICT...).
```
## How to pass AEGIS decision engine (CLI playbook)
Use this sequence before replaying or sending a live signal.
### 1) Confirm BRIDGE is in executable mode
```bash
curl -sS http://127.0.0.1:7842/api/mode
```
If needed:
```bash
curl -sS -X POST http://127.0.0.1:7842/api/mode \
  -H 'Content-Type: application/json' \
  -d '{"mode":"SIGNAL"}'
sleep 6
curl -sS http://127.0.0.1:7842/api/mode
```
Pass condition:
- `effective_mode` is `SIGNAL` (or `HYBRID` for signal+scalper runs).
### 2) Check live market + guard state
```bash
curl -sS http://127.0.0.1:7842/api/live | python3 -m json.tool
```
Pass conditions:
- `sentinel_active=false`
- `circuit_breaker=false`
- `mt5_connected=true`
- `mt5_fresh=true`
### 3) Pre-check trend alignment for SIGNAL source (M5 → M15 → H1 cascade)
```bash
python3 - <<'PY'
import json
from pathlib import Path
d = json.loads(Path('MT5/market_data.json').read_text())
def bias(tf):
    e20 = (tf or {}).get('ema_20') or (tf or {}).get('ma_20')
    e50 = (tf or {}).get('ema_50') or (tf or {}).get('ma_50')
    if e20 is None or e50 is None: return 'FLAT'
    diff = float(e20) - float(e50)
    if diff > 1: return 'BULL'
    if diff < -1: return 'BEAR'
    return 'FLAT'
for key,name in [('indicators_m5','M5'),('indicators_m15','M15'),('indicators_h1','H1')]:
    print(name, bias(d.get(key, {})))
PY
```
Pass heuristic:
- For `BUY`: prefer `M5` or `M15` as `BULL/FLAT`
- For `SELL`: prefer `M5` or `M15` as `BEAR/FLAT`
- If both M5 and M15 oppose your direction, expect `TREND_CONFLICT` skip.
### 4) Ensure SL/TP is likely to satisfy AEGIS R:R
AEGIS rejects low R:R (`LOW_RR`). Keep TP1 far enough vs SL distance.
- Rule of thumb: TP1 distance should be at least ~1.2× SL distance.
- If borderline, either tighten SL or widen TP1.
### 5) Ask AURUM for a pass-oriented setup (optional but recommended)
```bash
curl -sS -X POST http://127.0.0.1:7842/api/aurum/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"Give one setup most likely to pass AEGIS for source=SIGNAL now. Include direction, entry_low, entry_high, sl, tp1, and gate-check summary. If unsafe, reply PASS with exact blocker."}'
```
### 6) Replay/submit and verify decision immediately
After writing `python/config/parsed_signal.json`, check:
```bash
tail -n 50 logs/bridge.log | grep -iE 'New signal|APPROVED|REJECTED|SKIPPED|TREND_CONFLICT|LOW_RR|OPEN_GROUP'
```
```bash
curl -sS http://127.0.0.1:7842/api/live
```
If rejected, use `skip_reason` as the exact fix target for the next attempt.
### Common AEGIS reject reasons → what to change
- `TREND_CONFLICT:M5=..._M15=..._vs_<DIRECTION>(scalp_cascade)`
  - Change direction to match M5/M15 bias, or wait for M5/M15 to realign.
  - For SIGNAL source, if both M5 and M15 oppose your direction, it will be skipped.
- `LOW_RR:<value><1.2`
  - Tighten SL or widen TP1 so TP1 distance is at least ~1.2× SL distance.
- `SL_TOO_TIGHT:<value><MIN_SL_PIPS`
  - Increase SL distance from entry so it exceeds minimum SL pips threshold.
- `INVALID_SL:SL_BEYOND_ENTRY` / `INVALID_TP1:TP_BEYOND_ENTRY`
  - Fix directional math:
    - BUY: `sl < entry` and `tp1 > entry`
    - SELL: `sl > entry` and `tp1 < entry`
- `MAX_GROUPS:<open>/<limit>`
  - Close or reduce existing open groups, then retry.
- `DAILY_LOSS_LIMIT:$x/$y`
  - Wait for next session reset or lower risk/exposure before retrying.
- `FLOATING_DD:<pct>%>=<limit>%`
  - Reduce current drawdown (close/reduce losing exposure) before opening new group.
- `SLIPPAGE:<value>><max>`
  - Re-issue with a closer/current entry zone; avoid stale entries.

Simulate a MODIFY_TP management command (moves TP on all open positions):
```bash
python3 -c "
import json
from datetime import datetime, timezone
from pathlib import Path

cmd = {
    'type': 'MANAGEMENT',
    'intent': 'MODIFY_TP',     # or MODIFY_SL, CLOSE_ALL, MOVE_BE, CLOSE_PCT
    'tp': 4665.50,             # new TP price (for MODIFY_TP)
    'sl': None,                # new SL price (for MODIFY_SL)
    'pct': None,               # percentage (for CLOSE_PCT)
    'tp_stage': None,
    'signal_id': 9999,
    'timestamp': datetime.now(timezone.utc).isoformat(),
}
Path('python/config/management_cmd.json').write_text(json.dumps(cmd, indent=2))
print('Management command written — BRIDGE → FORGE on next tick')
"
```

Simulate a MODIFY_SL command:
```bash
python3 -c "
import json
from datetime import datetime, timezone
from pathlib import Path
cmd = {'type':'MANAGEMENT','intent':'MODIFY_SL','sl':4662.00,'tp':None,'pct':None,'tp_stage':None,'signal_id':9999,'timestamp':datetime.now(timezone.utc).isoformat()}
Path('python/config/management_cmd.json').write_text(json.dumps(cmd, indent=2))
print('MODIFY_SL → 4662.00 written')
"
```

Verify what happened after a test:
```bash
# Check BRIDGE log for AEGIS approval/rejection
tail -10 logs/bridge.log | grep -iE 'AEGIS|SIGNAL|REJECTED|OPEN_GROUP|TRACKER|MODIFY'

# Check positions
curl -s http://localhost:7842/api/live | python3 -c "
import sys, json
for p in json.load(sys.stdin).get('open_positions') or []:
    print(f'#{p[\"ticket\"]} {p.get(\"type\")} {p[\"lots\"]}lot @ {p[\"open_price\"]} SL={p[\"sl\"]} TP={p[\"tp\"]} pnl={p[\"profit\"]}')
"

# Check SCRIBE for closed trade details
curl -s http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT ticket, direction, entry_price, close_price, pnl, close_reason FROM trade_positions ORDER BY id DESC LIMIT 8"}' \
  | python3 -c "
import sys, json
for r in json.load(sys.stdin)['rows']:
    print(f'#{r[\"ticket\"]} {r[\"direction\"]} entry={r[\"entry_price\"]} close={r[\"close_price\"]} pnl={r[\"pnl\"]} reason={r[\"close_reason\"]}')
"
```

## Signal Lifecycle (Scalping)

```
Signal arrives → 60s to process (or EXPIRED)
    ↓
AEGIS validates (M5→M15→H1 cascade for SIGNAL source)
    ↓
FORGE places orders (market or pending)
    ↓
Pending placed on MT5 = FULFILLED_PENDING
    ↓ (when pending triggers)
Positions tracked in SCRIBE → SL/TP managed by MT5
    ↓ (if pending does NOT trigger within 3600s; non-SIGNAL groups)
Auto-cancel pending-only → Telegram alert "⏰ PENDING EXPIRED"
    ↓ (when all positions close via SL/TP)
Tracker logs P&L → group closed in SCRIBE → Telegram "✅ GROUP CLOSED"
```

Config:
```bash
SIGNAL_EXPIRY_SEC=60             # signal must be fresh (60s)
PENDING_ORDER_TIMEOUT_SEC=3600   # fulfilled-pending orders cancelled after 1h (non-SIGNAL groups)
SIGNAL_LOT_SIZE=0.01             # fixed lot for channel signals
SIGNAL_NUM_TRADES=4              # trades per signal group
```

### Cascade Trend Filter Test (verified 2026-04-06)

```bash
# Market state: H1=BULL  M15=BULL  M5=BEAR
# Old AEGIS: SELL rejected (H1 conflict)
# New cascade: SELL allowed via M5 (scalping TF agrees)

# Place SELL signal:
python3 -c "
import json; from datetime import datetime, timezone; from pathlib import Path
Path('python/config/parsed_signal.json').write_text(json.dumps({
    'type':'ENTRY','direction':'SELL','entry_low':4665.00,'entry_high':4666.00,
    'sl':4670.00,'tp1':4660.00,'tp2':4656.00,
    'signal_id':5001,'channel':'TEST','timestamp':datetime.now(timezone.utc).isoformat(),'edited':False
}, indent=2))
"

# Result from bridge.log:
# AEGIS: SIGNAL allowed via M5 SELL (H1=BULL M15=BULL M5=BEAR)
# AEGIS APPROVED: SELL 4×0.01lot SL=4.5p R:R=1.22 scale=150%
# TRACKER: new position ticket=1121161748 G14 SELL 0.01lot @ 4666.36
# 4 positions filled, SL=4670.0 TP=4660.0
```

Check current TF biases:
```bash
python3 -c "
import json; from pathlib import Path
d=json.loads(Path('MT5/market_data.json').read_text())
for k,l in [('indicators_h1','H1'),('indicators_m15','M15'),('indicators_m5','M5')]:
    tf=d.get(k,{})
    e20=tf.get('ema_20') or tf.get('ma_20',0)
    e50=tf.get('ema_50') or tf.get('ma_50',0)
    bias='BULL' if (e20 or 0)-(e50 or 0)>1 else 'BEAR' if (e20 or 0)-(e50 or 0)<-1 else 'FLAT'
    print(f'{l}: {bias} (EMA20={e20} EMA50={e50})')
"
```

**Notes:**
- Signals require SIGNAL or HYBRID mode (`POST /api/mode {"mode":"SIGNAL"}`)
- AEGIS cascade: M5→M15→H1 for SIGNAL, H1→M15 for AURUM, H1 only for SCALPER
- FLAT (EMA20 ≈ EMA50 within $1) counts as agreement — allows either direction
- Lot sizing uses `SIGNAL_LOT_SIZE` (default 0.01) when `AEGIS_LOT_MODE=fixed`
- Num trades uses `SIGNAL_NUM_TRADES` (default 4)
- MODIFY_SL/MODIFY_TP require FORGE v1.3.0 (reattach after compile)
- TP split: 75% of positions get TP1, 25% get TP2 (controlled by `TP1_CLOSE_PCT`)
- Test parser via API: `POST /api/signals/parse {"text": "SELL Gold @4691..."}`
- Swagger UI: `http://localhost:7842/api/docs/`

## Investigating Trade Groups (SCRIBE)

### Step 1: Find the trade group ID

List recent groups to find the one you want to inspect:
```bash
curl -s http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT id, status, direction, magic_number, num_trades, trades_closed, total_pnl, close_reason, timestamp FROM trade_groups ORDER BY id DESC LIMIT 5"}' \
  | python3 -c "
import sys, json
for r in json.load(sys.stdin)['rows']:
    print(f'G{r[\"id\"]} | magic={r[\"magic_number\"]} | {r[\"direction\"]} | {r[\"status\"]:10s} | trades={r[\"num_trades\"]} closed={r[\"trades_closed\"]} | pnl={r[\"total_pnl\"]} | reason={r[\"close_reason\"] or \"-\"} | {r[\"timestamp\"][:19]}')
"
```

Example output:
```
G9 | magic=202410 | BUY | CLOSED     | trades=4 closed=4 | pnl=22.15  | reason=ALL_CLOSED | 2026-04-06T13:08:16
G8 | magic=202409 | BUY | CLOSED     | trades=4 closed=4 | pnl=-9.88  | reason=ALL_CLOSED | 2026-04-06T13:03:11
G7 | magic=202408 | BUY | CLOSED     | trades=4 closed=4 | pnl=-28.93 | reason=ALL_CLOSED | 2026-04-06T05:54:20
```

**Reading the output:**
- `magic` = FORGE magic number on MT5 (202401 + group_id)
- `status`: OPEN/PARTIAL/CLOSED/CLOSED_ALL
- `trades_closed`: how many individual positions closed (null = no position tracker data)
- `close_reason`: ALL_CLOSED (SL/TP), MGMT_CLOSE_ALL (manual), RECONCILER_NO_MT5_EXPOSURE (orphan cleanup)

### Step 2: Drill into individual positions

Replace `trade_group_id=9` with your group ID:
```bash
curl -s http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT ticket, direction, lot_size, entry_price, close_price, pnl, pips, close_reason, close_time FROM trade_positions WHERE trade_group_id=9 ORDER BY id"}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
total_pnl = 0
for r in d['rows']:
    total_pnl += r['pnl'] or 0
    print(f'#{r[\"ticket\"]} | {r[\"direction\"]} {r[\"lot_size\"]}lot | entry={r[\"entry_price\"]} → close={r[\"close_price\"]} | pnl=\${r[\"pnl\"]:+.2f} | reason={r[\"close_reason\"]}')
print(f'TOTAL: {len(d[\"rows\"])} trades | P&L: \${total_pnl:+.2f}')
"
```

Example output:
```
#1120041582 | BUY 0.01lot | entry=4663.39 → close=4668.95 | pnl=$+5.56 | reason=BROKER
#1120041605 | BUY 0.01lot | entry=4663.41 → close=4668.95 | pnl=$+5.54 | reason=BROKER
#1120041630 | BUY 0.01lot | entry=4663.39 → close=4668.95 | pnl=$+5.56 | reason=BROKER
#1120041654 | BUY 0.01lot | entry=4663.46 → close=4668.95 | pnl=$+5.49 | reason=BROKER
TOTAL: 4 trades | P&L: $+22.15
```

**Interpreting G9:** 4 BUY positions entered at ~$4663.40 (0.01 lot each, from a simulated channel signal). All 4 closed at $4668.95 — just under the original TP of $4669.00. Each trade made ~$5.50 profit. close_reason=BROKER means MT5 closed them (TP hit), not a manual CLOSE_ALL.

### Step 3: Full portfolio summary

All groups with position counts and P&L:
```bash
curl -s http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT g.id, g.direction, g.status, g.num_trades, g.total_pnl, g.close_reason, g.source, COUNT(p.id) as positions FROM trade_groups g LEFT JOIN trade_positions p ON p.trade_group_id = g.id GROUP BY g.id ORDER BY g.id"}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
total = 0
for r in d['rows']:
    pnl = r['total_pnl'] or 0
    total += pnl
    print(f'G{r[\"id\"]} {r[\"direction\"]:4s} | {r[\"status\"]:10s} | src={r[\"source\"]:8s} | positions={r[\"positions\"]} | pnl=\${pnl:+.2f} | {r[\"close_reason\"] or \"-\"}')
print(f'ALL-TIME P&L: \${total:+.2f}')
"
```

Example output:
```
G1 SELL | CLOSED     | src=AURUM    | positions=0 | pnl=$+0.00 | RECONCILER_NO_MT5_EXPOSURE
G6 SELL | CLOSED_ALL | src=AURUM    | positions=8 | pnl=$-0.73 | MGMT_CLOSE_ALL
G7 BUY  | CLOSED     | src=AURUM    | positions=4 | pnl=$-28.93 | ALL_CLOSED
G8 BUY  | CLOSED     | src=SIGNAL   | positions=4 | pnl=$-9.88 | ALL_CLOSED
G9 BUY  | CLOSED     | src=SIGNAL   | positions=4 | pnl=$+22.15 | ALL_CLOSED
ALL-TIME P&L: $-17.39
```

**Interpreting the portfolio:**
- `positions=0` on G1-G5: these were created before the position tracker existed — no individual trade data was captured
- `src=AURUM`: trades placed by AURUM (Claude AI) or the old BRIDGE scalper
- `src=SIGNAL`: trades from Telegram channel signals
- `RECONCILER_NO_MT5_EXPOSURE`: reconciler closed these because FORGE couldn't see them (v1.2.3 bug, now fixed)
- `MGMT_CLOSE_ALL`: manually closed via dashboard or AURUM CLOSE_ALL command
- `ALL_CLOSED`: all positions hit SL or TP naturally

---

## Quick Health Check

```bash
curl -s http://localhost:7842/api/health | python3 -m json.tool
```

## Live System State

Full dashboard data (mode, account, positions, indicators, groups):
```bash
curl -s http://localhost:7842/api/live | python3 -c "
import sys, json
d = json.load(sys.stdin)
acc = d.get('account', {})
print(f'mode: {d.get(\"mode\")}  effective: {d.get(\"effective_mode\")}')
print(f'balance: \${acc.get(\"balance\",0):,.2f}  equity: \${acc.get(\"equity\",0):,.2f}')
print(f'floating: \${acc.get(\"total_floating_pnl\",0):+.2f}  session_pnl: \${acc.get(\"session_pnl\",0):+.2f}')
print(f'positions: {acc.get(\"open_positions_count\",0)}  pending: {len(d.get(\"pending_orders\") or [])}')
print(f'open_groups: {len(d.get(\"open_groups\") or [])}  queued: {len(d.get(\"open_groups_queued\") or [])}')
"
```

## FORGE Version

Via API:
```bash
curl -s http://localhost:7842/api/live | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f'forge_version: {d.get(\"forge_version\")}  ea_cycle: {d.get(\"ea_cycle\")}  mt5: {d.get(\"mt5_connected\")}')
"
```

Via file (when ATHENA is down):
```bash
python3 -c "import json;from pathlib import Path;d=json.loads(Path('MT5/market_data.json').read_text());print(f'forge_version: {d.get(\"forge_version\")} ea_cycle: {d.get(\"ea_cycle\")}')"
```

Full indicator check (all timeframes):
```bash
python3 -c "
import json;from pathlib import Path
d=json.loads(Path('MT5/market_data.json').read_text())
print(f'FORGE {d.get(\"forge_version\")} cycle={d.get(\"ea_cycle\")}')
for tf in ['indicators_h1','indicators_m5','indicators_m15','indicators_m30']:
    v=d.get(tf,{})
    if v and v.get('rsi_14'):
        print(f'  {tf}: RSI={v[\"rsi_14\"]} MACD={v.get(\"macd_hist\")} ADX={v.get(\"adx\")} ATR={v.get(\"atr_14\")} BB=[{v.get(\"bb_lower\")}/{v.get(\"bb_mid\")}/{v.get(\"bb_upper\")}]')
"
```

## Market Data (from FORGE via market_data.json)

```bash
python3 -c "
import json
from pathlib import Path
d = json.loads(Path('MT5/market_data.json').read_text())
p = d.get('price', {})
print(f'bid: {p.get(\"bid\")}  ask: {p.get(\"ask\")}  spread: {p.get(\"spread_points\")}pt')
print(f'forge_version: {d.get(\"forge_version\")}  ea_cycle: {d.get(\"ea_cycle\")}')
for tf in ['indicators_h1', 'indicators_m5', 'indicators_m15', 'indicators_m30']:
    v = d.get(tf, {})
    if v and v.get('rsi_14'):
        print(f'{tf}: RSI={v[\"rsi_14\"]} ATR={v.get(\"atr_14\")} ADX={v.get(\"adx\")} MACD={v.get(\"macd_hist\")}')
"
```

## Positions & Orders

Open positions with P&L:
```bash
curl -s http://localhost:7842/api/live | python3 -c "
import sys, json
d = json.load(sys.stdin)
for p in d.get('open_positions') or []:
    print(f'#{p[\"ticket\"]} {p[\"type\"]} {p[\"lots\"]}lot @ {p[\"open_price\"]} SL={p[\"sl\"]} TP={p[\"tp\"]} pnl={p[\"profit\"]} magic={p[\"magic\"]}')
if not d.get('open_positions'):
    print('No open positions')
"
```

Pending orders:
```bash
curl -s http://localhost:7842/api/live | python3 -c "
import sys, json
d = json.load(sys.stdin)
for o in d.get('pending_orders') or []:
    print(f'#{o[\"ticket\"]} {o[\"order_type\"]} @ {o[\"price\"]} SL={o[\"sl\"]} TP={o[\"tp\"]} magic={o[\"magic\"]} {\"FORGE\" if o.get(\"forge_managed\") else \"\"}')
if not d.get('pending_orders'):
    print('No pending orders')
"
```

## Trade Groups (SCRIBE)

```bash
curl -s http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT id, status, direction, magic_number, num_trades, trades_closed, total_pnl, close_reason FROM trade_groups ORDER BY id DESC LIMIT 10"}' \
  | python3 -c "
import sys, json
for r in json.load(sys.stdin)['rows']:
    print(f'G{r[\"id\"]} magic={r[\"magic_number\"]} {r[\"direction\"]} {r[\"status\"]:10s} closed={r[\"trades_closed\"]} pnl={r[\"total_pnl\"]} reason={r[\"close_reason\"] or \"-\"}')
"
```

## Trade Positions (SCRIBE)

```bash
curl -s http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT ticket, trade_group_id, direction, lot_size, entry_price, status, close_price, pnl, close_reason FROM trade_positions ORDER BY id DESC LIMIT 20"}' \
  | python3 -c "
import sys, json
for r in json.load(sys.stdin)['rows']:
    print(f'#{r[\"ticket\"]} G{r[\"trade_group_id\"]} {r[\"direction\"]} {r[\"lot_size\"]}lot entry={r[\"entry_price\"]} {r[\"status\"]} close={r[\"close_price\"]} pnl={r[\"pnl\"]} reason={r[\"close_reason\"]}')
"
```

## Manual / Unmanaged MT5 Trades (`MANUAL_MT5`)

Latest synthetic manual groups:
```bash
curl -s http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT id, timestamp, status, direction, magic_number, total_pnl, close_reason FROM trade_groups WHERE source='\''MANUAL_MT5'\'' ORDER BY id DESC LIMIT 15"}' \
  | python3 -c "
import sys, json
rows = json.load(sys.stdin)['rows']
for r in rows:
    print(f'G{r[\"id\"]} MANUAL_MT5 {r[\"direction\"] or \"?\":4s} {r[\"status\"]:8s} magic={r[\"magic_number\"]} pnl={r[\"total_pnl\"]} reason={r[\"close_reason\"] or \"-\"}')
if not rows:
    print('No MANUAL_MT5 groups found')
"
```

Open manual positions currently tracked in SCRIBE:
```bash
curl -s http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT p.ticket, p.trade_group_id, p.magic_number, p.direction, p.lot_size, p.entry_price, p.status, g.source FROM trade_positions p JOIN trade_groups g ON g.id=p.trade_group_id WHERE g.source='\''MANUAL_MT5'\'' AND p.status='\''OPEN'\'' ORDER BY p.id DESC LIMIT 20"}' \
  | python3 -c "
import sys, json
rows = json.load(sys.stdin)['rows']
for r in rows:
    print(f'#{r[\"ticket\"]} G{r[\"trade_group_id\"]} {r[\"direction\"]} {r[\"lot_size\"]}lot entry={r[\"entry_price\"]} magic={r[\"magic_number\"]} {r[\"status\"]}')
if not rows:
    print('No OPEN MANUAL_MT5 positions')
"
```

Unmanaged lifecycle audit events:
```bash
curl -s http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT timestamp, event_type, reason, notes FROM system_events WHERE event_type IN ('\''UNMANAGED_POSITION_OPEN'\'','\''UNMANAGED_POSITION_CLOSED'\'') ORDER BY id DESC LIMIT 25"}' \
  | python3 -c "
import sys, json
rows = json.load(sys.stdin)['rows']
for r in rows:
    ts = (r['timestamp'] or '')[:19]
    print(f'{ts} | {r[\"event_type\"]:27s} | {r.get(\"reason\") or \"-\"}')
if not rows:
    print('No unmanaged lifecycle events yet')
"
```
## System Events Log

Recent events:
```bash
curl -s http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT timestamp, event_type, triggered_by, reason, notes FROM system_events ORDER BY id DESC LIMIT 15"}' \
  | python3 -c "
import sys, json
for r in reversed(json.load(sys.stdin)['rows']):
    ts = (r['timestamp'] or '')[:19]
    notes = (r.get('notes') or '')[:100]
    print(f'{ts} | {r[\"event_type\"]:25s} | {r.get(\"triggered_by\") or \"-\":10s} | {notes}')
"
```

## Mode Control

Switch mode:
```bash
# Options: OFF, WATCH, SIGNAL, SCALPER, HYBRID, AUTO_SCALPER
curl -s -X POST http://localhost:7842/api/mode \
  -H 'Content-Type: application/json' \
  -d '{"mode": "AUTO_SCALPER"}'
```

Check current mode:
```bash
curl -s http://localhost:7842/api/mode | python3 -m json.tool
```

## Management Commands

Close all positions + pending orders:
```bash
curl -s -X POST http://localhost:7842/api/management \
  -H 'Content-Type: application/json' \
  -d '{"intent": "CLOSE_ALL"}'
```

Move all SL to breakeven:
```bash
curl -s -X POST http://localhost:7842/api/management \
  -H 'Content-Type: application/json' \
  -d '{"intent": "MOVE_BE"}'
```

Close 70% of positions (all groups):
```bash
curl -s -X POST http://localhost:7842/api/management \
  -H 'Content-Type: application/json' \
  -d '{"intent": "CLOSE_PCT", "pct": 70}'
```

Close a specific group:
```bash
curl -s -X POST http://localhost:7842/api/management \
  -H 'Content-Type: application/json' \
  -d '{"intent": "CLOSE_GROUP", "group_id": 9}'
```

Close 70% of a specific group:
```bash
curl -s -X POST http://localhost:7842/api/management \
  -H 'Content-Type: application/json' \
  -d '{"intent": "CLOSE_GROUP_PCT", "group_id": 9, "pct": 70}'
```

Close only winning positions:
```bash
curl -s -X POST http://localhost:7842/api/management \
  -H 'Content-Type: application/json' \
  -d '{"intent": "CLOSE_PROFITABLE"}'
```

Close only losing positions:
```bash
curl -s -X POST http://localhost:7842/api/management \
  -H 'Content-Type: application/json' \
  -d '{"intent": "CLOSE_LOSING"}'
```

## Ask AURUM (AI)

```bash
curl -s -X POST http://localhost:7842/api/aurum/ask \
  -H 'Content-Type: application/json' \
  -d '{"query": "What do you see on the charts? Should we trade?"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','error'))"
```

## Place a Trade via AURUM

Write aurum_cmd.json directly (BRIDGE picks it up on next tick):
```bash
python3 -c "
import json
from datetime import datetime, timezone
from pathlib import Path

cmd = {
    'action': 'OPEN_GROUP',
    'direction': 'SELL',
    'entry_low': 4670.00,
    'entry_high': 4670.50,
    'sl': 4678.00,
    'tp1': 4664.00,
    'tp2': 4658.00,
    'lot_per_trade': 0.01,
    'num_trades': 4,
    'reason': 'Manual scalp via CLI',
    'timestamp': datetime.now(timezone.utc).isoformat(),
}
Path('python/config/aurum_cmd.json').write_text(json.dumps(cmd, indent=2))
print('Command written — BRIDGE processes next tick (~5s)')
"
```

## Trade Closures (SL/TP Hits)

Recent closures:
```bash
curl -s 'http://localhost:7842/api/closures?days=7&limit=20' | python3 -c "
import sys, json
for c in json.load(sys.stdin):
    print(f'{c[\"timestamp\"][:19]} #{c[\"ticket\"]} G{c[\"trade_group_id\"]} {c[\"direction\"]} {c[\"close_reason\"]:12s} pnl=\${c[\"pnl\"]:+.2f} pips={c[\"pips\"]:+.1f}')
"
```

Closure stats (SL vs TP hit rates):
```bash
curl -s 'http://localhost:7842/api/closure_stats?days=7' | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Total: {d[\"total\"]}  SL: {d[\"sl_hits\"]} ({d[\"sl_rate\"]}%)  TP1: {d[\"tp1_hits\"]}  TP2: {d[\"tp2_hits\"]}  Manual: {d[\"manual\"]}')
print(f'P&L: \${d[\"total_pnl\"]:+.2f}  Avg: \${d[\"avg_pnl\"]:+.2f}  Avg pips: {d[\"avg_pips\"]:+.1f}')
"
```

Query trade_closures directly via SCRIBE:
```bash
curl -s http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT close_reason, COUNT(*) AS n, ROUND(SUM(pnl),2) AS total_pnl FROM trade_closures WHERE timestamp >= datetime(\"now\",\"-7 days\") GROUP BY close_reason ORDER BY n DESC"}' \
  | python3 -c "
import sys, json
for r in json.load(sys.stdin)['rows']:
    print(f'{r[\"close_reason\"]:15s} count={r[\"n\"]} pnl=\${r[\"total_pnl\"]:+.2f}')
"
```

## Performance

```bash
curl -s http://localhost:7842/api/performance?days=7 | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Trades: {d[\"total\"]}  Wins: {d[\"wins\"]}  Win rate: {d.get(\"win_rate\",\"n/a\")}%')
print(f'Total P&L: \${d[\"total_pnl\"]:+.2f}  Avg pips: {d[\"avg_pips\"]:+.1f}')
"
```
Performance tab accuracy contract:
- Window: **Rolling 7 days (UTC)**
- Source rows: `trade_positions` where `status='CLOSED'` in SCRIBE
- Metrics shown:
  - Win Rate
  - Avg Pips
  - Total P&L
  - Trades
  - Wins
  - Losses
Validation tip:
```bash
curl -s http://localhost:7842/api/live | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('performance_window'))
print({k:d.get('performance',{}).get(k) for k in ['total','wins','win_rate','avg_pips','total_pnl']})
"
```

## Component Health

```bash
curl -s http://localhost:7842/api/components | python3 -c "
import sys, json
d = json.load(sys.stdin)
for c in d['components']:
    ok = '✅' if c['ok'] else '❌'
    print(f'{ok} {c[\"name\"]:12s} {c[\"status\"]:6s} | {c.get(\"note\",\"-\")}')
"
```

## Sentinel Override

Temporarily bypass sentinel news guard (for testing or intentional news trading):
```bash
# Override for 5 minutes (300s)
curl -s -X POST http://localhost:7842/api/sentinel/override \
  -H 'Content-Type: application/json' \
  -d '{"duration": 300, "reason": "intentional news trade"}'
```

Response:
```json
{"ok": true, "duration": 300, "reverts_at": "2026-04-06T14:05:00+00:00",
 "hint": "Sentinel bypassed for 300s. Trading allowed during news. Auto-reverts."}
```

**Behaviour:**
- Effective mode changes from WATCH back to your selected mode (SIGNAL/SCALPER/etc.)
- Auto-reverts after the duration — sentinel resumes blocking
- Logged to SCRIBE as `SENTINEL_OVERRIDE_ON` / `SENTINEL_OVERRIDE_EXPIRED`
- Telegram alert sent on override and expiry
- Duration clamped: min 60s, max 3600s (1 hour)
- Default `SENTINEL_OVERRIDE_DURATION_SEC=600` in .env

Check sentinel status + next event:
```bash
curl -s http://localhost:7842/api/live | python3 -c "
import sys, json
d = json.load(sys.stdin)
s = d.get('sentinel', {})
print(f'mode: {d.get(\"mode\")}  effective: {d.get(\"effective_mode\")}')
print(f'sentinel_active: {d.get(\"sentinel_active\")}')
print(f'next_event: {s.get(\"next_event\")} in {s.get(\"next_in_min\")}min ({s.get(\"next_time\",\"?\")})')
if d.get('sentinel_active'):
    print(f'guard_event: {s.get(\"event_name\",\"?\")} — effective mode forced to WATCH')
else:
    print('Clear to trade')
"
```

Example output (during news):
```
mode: SIGNAL  effective: WATCH
sentinel_active: True
next_event: ISM Services PMI in 5min (14:00 UTC)
guard_event: ISM Services PMI — effective mode forced to WATCH
```

Example output (clear):
```
mode: SIGNAL  effective: SIGNAL
sentinel_active: False
next_event: President Trump Speaks in 173min (16:55 UTC)
Clear to trade
```

## Sentinel Event Digest

SENTINEL sends upcoming HIGH-impact events to Telegram every 10 minutes (default).

Override digest interval (for testing):
```bash
# Set to 30s for immediate test
curl -s -X POST http://localhost:7842/api/sentinel/digest \
  -H 'Content-Type: application/json' \
  -d '{"interval": 30}'

# Reset to default 10min
curl -s -X POST http://localhost:7842/api/sentinel/digest \
  -d '{"interval": 600}'
```

Telegram messages:
```
📅 SENTINEL — Upcoming Events
🔴 President Trump Speaks (USD) in 45min — 17:00 UTC

⚠️ Guard activating soon!
📅 President Trump Speaks in 35min
Trading will pause at 5min mark

⚠️ NEWS GUARD ACTIVE
📰 President Trump Speaks in 30min
Trading paused — Mode: SIGNAL → WATCH

✅ NEWS GUARD LIFTED
📰 President Trump Speaks passed
Resuming → SIGNAL
```

Config: `SENTINEL_DIGEST_INTERVAL_SEC=600` in .env (default 10min)

## Smart Close Test Results (verified 2026-04-06)

### Test: CLOSE_GROUP isolates one group
```bash
# Setup: G11 (magic 202412, 4 BUY_LIMIT) + G12 (magic 202413, 4 BUY_LIMIT)
# Close only G11:
curl -s -X POST http://localhost:7842/api/management \
  -H 'Content-Type: application/json' \
  -d '{"intent": "CLOSE_GROUP", "group_id": 11}'

# Result: G11's 4 pending orders cancelled. G12's 4 orders untouched.
# Verified: pendings went from 8 → 4 (all magic 202413 = G12)
```

### Test: MODIFY_TP changes TP on live positions
```bash
# Setup: G9 BUY 4×0.01 at ~4663, original TP=4669
# Modify TP to 4665.50:
python3 -c "
import json; from datetime import datetime, timezone; from pathlib import Path
Path('python/config/management_cmd.json').write_text(json.dumps({
    'type':'MANAGEMENT','intent':'MODIFY_TP','tp':4665.50,
    'timestamp':datetime.now(timezone.utc).isoformat()},indent=2))
"
# Result: TP modified → price already above 4665.50 → all 4 hit TP instantly
# SCRIBE: close_price=4668.95, pnl=$+5.56 each (hit original TP before modify reached FORGE)
```

### Test: Sentinel override during ISM Services PMI
```bash
# Sentinel blocking: effective_mode=WATCH during ISM PMI
curl -s -X POST http://localhost:7842/api/sentinel/override \
  -d '{"duration":300,"reason":"testing smart close"}'
# Result: effective_mode changed to SIGNAL, orders placed successfully
# Auto-reverted after 300s
```

## Signal Channels

Configured channels and their stats:
```bash
curl -s http://localhost:7842/api/channels | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Configured: {d[\"total_configured\"]} channels ({d[\"configured_ids\"]})')
for ch in d.get('channels', []):
    print(f'  {ch[\"channel_name\"]}: {ch[\"total\"]} signals (exec={ch[\"executed\"]} skip={ch[\"skipped\"]}) last={ch.get(\"last_signal\",\"never\")[:19]}')
"
```

Recent messages from all channels (via API — no Telegram lock needed):
```bash
curl -s http://localhost:7842/api/channels/messages | python3 -c "
import sys, json
for ch in json.load(sys.stdin).get('channels', []):
    print(f'=== {ch[\"name\"]} ({ch[\"id\"]}) ===')
    for m in ch.get('messages', [])[:5]:
        print(f'  [{m[\"date\"]}] {m[\"text\"][:100]}')
    print()
"
```

Channel performance (P&L per channel):
```bash
curl -s "http://localhost:7842/api/channel_performance?days=30" | python3 -c "
import sys, json
for ch in json.load(sys.stdin).get('channels', []):
    print(f'{ch[\"channel\"]}: {ch[\"total_signals\"]} signals, {ch[\"executed\"]} executed, P&L \${ch[\"total_pnl\"]:+.2f}, WR {ch.get(\"win_rate\",\"n/a\")}%')
"
```

List configured channels + read recent messages from all (stop LISTENER first):
```bash
# Stop listener to free session lock
launchctl unload ~/Library/LaunchAgents/com.signalsystem.listener.plist

cd signal_system/python && python3 -c "
import asyncio, os
from dotenv import load_dotenv; load_dotenv('../.env')
from telethon import TelegramClient

API_ID = int(os.environ['TELEGRAM_API_ID'])
API_HASH = os.environ['TELEGRAM_API_HASH']
channels = [int(c.strip()) for c in os.environ.get('TELEGRAM_CHANNELS','').split(',') if c.strip()]

async def main():
    c = TelegramClient('config/telegram_session', API_ID, API_HASH)
    await c.start()
    print(f'Channels: {len(channels)}')
    for ch_id in channels:
        entity = await c.get_entity(ch_id)
        name = getattr(entity, 'title', str(ch_id))
        msgs = await c.get_messages(ch_id, limit=5)
        print(f'\n=== {name} ({ch_id}) ===')
        for m in msgs:
            print(f'  [{str(m.date)[:19]}] {(m.message or \"(media)\")[:100]}')
    await c.disconnect()
asyncio.run(main())
"

# Restart listener
launchctl load ~/Library/LaunchAgents/com.signalsystem.listener.plist
```

Example output:
```
Channels: 3

=== Ben's VIP Club (-1002034822451) ===
  [2026-04-06 12:17:11] Round 3 TOUCH AND TP2//160pips✅ Let's CLOSE our trade now...
  [2026-04-06 12:13:12] Let's GOOO @wallstreetben

=== GARRY'S SIGNALS (-1003582676523) ===
  [2026-04-06 12:07:22] Objective cleared! TP 2 crushed for 80 pips! 🔥
  [2026-04-06 12:07:22] Gold buy now

=== FLAIR FX (-1002293626964) ===
  [2026-04-06 14:03:02] https://www.tradingview.com/x/FoLxWNKO/
  [2026-04-02 14:38:05] SL HIT.
```

Read recent messages from a single channel (stop LISTENER first):
```bash
# Stop listener to free session lock
launchctl unload ~/Library/LaunchAgents/com.signalsystem.listener.plist
cd signal_system/python && python3 -c "
import asyncio, os
from dotenv import load_dotenv; load_dotenv('../.env')
from telethon import TelegramClient
async def main():
    c = TelegramClient('config/telegram_session', int(os.environ['TELEGRAM_API_ID']), os.environ['TELEGRAM_API_HASH'])
    await c.start()
    for m in await c.get_messages(-1002034822451, limit=5):
        print(f'[{str(m.date)[:19]}] {(m.message or \"(media)\")[:100]}')
    await c.disconnect()
asyncio.run(main())
"
# Restart listener
launchctl load ~/Library/LaunchAgents/com.signalsystem.listener.plist
```

## Test Signal Parser (Claude Haiku)

Test how LISTENER parses channel messages via API (no Telegram needed):
```bash
# Parse a SELL signal
curl -s -X POST http://localhost:7842/api/signals/parse \
  -H 'Content-Type: application/json' \
  -d '{"text": "SELL Gold @4691-4701\nSl :4706\nTp1 :4687\nTp2:4681"}' | python3 -m json.tool

# Parse a management message  
curl -s -X POST http://localhost:7842/api/signals/parse \
  -d '{"text": "TP1 hit. Secure 70% profit. Hold 30% with breakeven!"}' | python3 -m json.tool

# Parse SL modification
curl -s -X POST http://localhost:7842/api/signals/parse \
  -d '{"text": "Move SL to 4660 for safety"}' | python3 -m json.tool
```

Or test via Python directly:
```bash
cd signal_system/python && python3 -c "
import asyncio, sys; sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv('../.env')
from listener import Listener
l = Listener()

tests = [
    'SELL Gold @4691-4701\nSl :4706\nTp1 :4687\nTp2:4681\nEnter Slowly',
    'Round 4 TOUCH AND TP2//130pips✅\nLet\'s CLOSE our trade now',
    'TP1 hit ✅✅ Secure 70% profit. Hold 30% with breakeven!',
    'Move SL to 4660 for safety',
    'Gold buy now',
    'Happy Easter to the community',
]
for msg in tests:
    r = asyncio.run(l.test_parse(msg))
    t = r.get('type','?')
    if t=='ENTRY':    print(f'✅ ENTRY {r.get(\"direction\")} @ {r.get(\"entry_low\")}-{r.get(\"entry_high\")} SL={r.get(\"sl\")} TP1={r.get(\"tp1\")} TP2={r.get(\"tp2\")}')     
    elif t=='MANAGEMENT': print(f'📋 MGMT {r.get(\"intent\")} pct={r.get(\"pct\")} sl={r.get(\"sl\")} tp={r.get(\"tp\")}')     
    else: print(f'❌ {t}')     
    print(f'   ← {msg[:60]}\n')
"
```

Verified output (2026-04-06):
```
✅ ENTRY SELL @ 4691-4701 SL=4706 TP1=4687 TP2=4681
   ← SELL Gold @4691-4701 Sl :4706 Tp1 :4687 Tp2:4681 Enter Sl

📋 MGMT CLOSE_ALL pct=None sl=None tp=None
   ← Round 4 TOUCH AND TP2//130pips✅ Let's CLOSE our trade now

📋 MGMT CLOSE_PCT pct=70 sl=None tp=None
   ← TP1 hit ✅✅ Secure 70% profit. Hold 30% with breakeven!

📋 MGMT MODIFY_SL pct=None sl=4660 tp=None
   ← Move SL to 4660 for safety

❌ IGNORE
   ← Gold buy now (no SL/TP = not actionable)

❌ IGNORE
   ← Happy Easter to the community (not a signal)
```

Additional test cases verified:
```
📋 MGMT TP_HIT tp_stage=1      ← "TP1 hit! Move SL to entry and let TP2 run"
📋 MGMT CLOSE_PCT pct=75      ← "Close 3 trades, keep 1 running to TP2 with BE"
📋 MGMT MODIFY_TP tp=4680     ← "Move TP to 4680 for all remaining trades"
📋 MGMT CLOSE_PCT pct=50      ← "Close half and trail the rest"
✅ ENTRY SELL SL=4700 TP1=4680 TP2=4670 TP3=4660  ← "SELL XAUUSD now @ market"
✅ ENTRY BUY @ 4650-4655 SL=4640 TP1=4665 TP2=4675 ← "BUY Gold 4650-4655"
```

## Verify FORGE ↔ BRIDGE Path Alignment

```bash
python3 scripts/verify_forge_bridge.py
```

## AUTO_SCALPER Monitoring

Watch AUTO_SCALPER decisions in real time:
```bash
tail -f logs/bridge.log | grep AUTO_SCALPER
```

Check last N polls:
```bash
grep AUTO_SCALPER logs/bridge.log | tail -10
```

## Drawdown Protection Status

```bash
curl -s http://localhost:7842/api/live | python3 -c "
import sys, json
d = json.load(sys.stdin)
acc = d.get('account', {})
eq = acc.get('equity', 0)
bal = acc.get('balance', 0)
flt = acc.get('total_floating_pnl', 0)
print(f'Equity: \${eq:,.2f}  Balance: \${bal:,.2f}  Floating: \${flt:+.2f}')
if bal > 0 and flt < 0:
    print(f'Floating DD: {abs(flt)/bal*100:.2f}% (blocks new trades at 2%)')
else:
    print('Floating: clean')
print(f'Equity DD breaker: closes all at 3% from session peak')
"
```

## Mode Persistence

BRIDGE remembers your mode across restarts (default: enabled).

```bash
# Set mode — persists across restarts
curl -s -X POST http://localhost:7842/api/mode \
  -H 'Content-Type: application/json' \
  -d '{"mode": "SIGNAL"}'

# Disable persistence (use DEFAULT_MODE from .env instead)
# In .env: RESTORE_MODE_ON_RESTART=false
```

Config: `RESTORE_MODE_ON_RESTART=true` (default) in .env

## Web Search (Google News RSS)

Search for live news (free, no API key):
```bash
curl -s "http://localhost:7842/api/search?q=trump+speaking+gold&n=3" | python3 -m json.tool
```

AURUM auto-triggers this when you ask about live events:
```bash
curl -s -X POST http://localhost:7842/api/aurum/ask \
  -H 'Content-Type: application/json' \
  -d '{"query": "Is Trump still speaking? What is the latest gold news?"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','error'))"
```

Trigger keywords: news, speaking, live, right now, trump, powell, fomc, breaking, latest, etc.

## TradingView Brief (full payload)

```bash
# Full persisted brief payload from LENS
curl -s http://localhost:7842/api/brief | python3 -m json.tool

# If unavailable, force one fresh LENS cycle then retry
python3 python/lens.py
curl -s http://localhost:7842/api/brief | python3 -m json.tool
```

## Useful Make Targets

```bash
make reload               # hot-restart all Python processes (fast)
make reload-bridge        # hot-restart BRIDGE only (sentinel/aegis/aurum changes)
make restart              # full restart (re-renders plists from .env)
make stop / make start    # stop / install + start all services
make forge-compile        # compile FORGE.mq5 → .ex5
make forge-reload         # compile + restart MT5 + check if EA auto-loaded
make forge-refresh        # compile + open MT5 (manual reattach)
make forge-verify-live    # poll until forge_version matches source
make forge-refresh-verify # compile + open MT5 + poll 180s
make verify-forge-bridge  # check file bus paths
make start-tradingview    # launch TradingView Desktop with CDP
make check-tradingview    # verify CDP is reachable on :9222
make setup-indicators     # add/repair required TV indicators (including ADX+DI)
make check-indicators     # verify required indicators exist
```

**Note on EA reattach (macOS Wine limitation):**
MT5 on Wine/macOS does NOT auto-restore EAs after restart. `make forge-reload` restarts MT5 and checks — if FORGE isn't writing, you need to manually reattach:
1. Right-click chart → Expert list → Remove FORGE
2. Navigator → Expert Advisors → drag FORGE onto chart
3. Enable Algo Trading (green button)
4. Verify: `make forge-verify-live`

---

## Notes

- All `curl` commands assume ATHENA is running on port 7842 (default)
- SCRIBE query endpoint only allows SELECT statements
- After placing trades via CLI, check BRIDGE logs: `tail -20 logs/bridge.log`
- FORGE changes require reattach in MT5 (remove EA from chart → re-drag)
- Swagger UI for interactive exploration: http://localhost:7842/api/docs/
