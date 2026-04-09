# ATHENA dashboard — UI audit handoff for Claude Code

Review and update the Signal System dashboard using the facts below.

## How this was produced

- Playwright spec `tests/ui/test_athena_audit.spec.js`
- Screenshots: `tests/results/athena-ui/screens/{groups,activity,signals,perf}.png`

## API snapshot at audit time (`/api/live` subset)

```json
{
  "mode": "WATCH",
  "effective_mode": "WATCH",
  "session": "OFF_HOURS",
  "mt5_connected": true,
  "mt5_quote_stale": false,
  "execution_usable": true,
  "execution_symbol": "XAUUSD",
  "execution_age_sec": 0.7,
  "chart_symbol": "XAUUSD",
  "open_groups_count": 0,
  "balance": 100001.93,
  "performance_total": 0
}
```

## Console errors (filtered)

```
(none)
```

## Per-tab text snippets (truncated in JSON; open screenshots for pixels)

### Tab `groups`

```
⚒ ATHENA
SIGNAL SYSTEM · XAUUSD
WATCH
DEMO
23:33:52 UTC
OFF_HOURS
LIVE
Cycle 97
⬡ ACCOUNT · MT5 LIVE
$100,001.93
BALANCE (from market_data.json)
EQUITY
$100,001.93
MRG LVL
0%
POSITIONS
0
SESSION
+0.00
P&L today
⬡ MODE CONTROL
OFF
Dormant
WATCH
Data only
SIGNAL
Signals
SCALPER
Self-scalp
HYBRID
Both active
BRIDGE → FORGE via config.json
✓ SENTINEL
CLEAR TO TRADE
Next: ISM Services PMI
14:00 UTC
in 14h 26m
⬡ SYSTEM HEALTH
BRIDGE
Cycle 97 effective=WATCH
FORGE
DEMO @ VantageInternational-Demo
LISTENER
monitoring 3 channels
LENS
RSI=34.2 snapshot_age=0s
SENTINEL
Next: ISM Services PMI in 866min
AEGIS
risk=2.0% trades=8
SCRIBE
SQLite datastore
HERALD
bot active
AURUM
tokens=2770
RECONCILER
CLEAN mt5=0 scribe=0
ATHENA
API serving
GROUPS
ACTIVITY
SIGNALS
PERFORMANCE
No open groups
◆ FORGE · EXECUTION QUOTE
SELL (bid)
$4609.82
BUY (ask)
$4610.08
XAUUSD · file age 3s · spread $0.26 (~26 pt)
FORGE 2026.04.05 23:33:50Z
🔭 TRADINGVIEW · INDICATORS
$4609.90
last (FX)
5m · snapshot 0m 0s ago
RSI 14
34.2
MACD
-6.71000
BB Rtg
-3
ADX
0.0
EMA20
$4634.3
EMA50
$4634.3
TV suggest: 0
⚡ AURUM · TELEGRAM + DASHBOARD
P&L today?
Open groups?
LENS reading?
All clear?
AURUM ◆AURUM online · WATCH · Balance $100,001.93 · 0 open · MT5 4609.82 / 4610.08. What do you need?
SEND
Also on Telegram — same AURUM, same live context
ATHENA · /api/live: execution + tradingview · FORGE + TV MCP · SCRIBE
Tick 0 · 3s poll
```

### Tab `activity`

```
⚒ ATHENA
SIGNAL SYSTEM · XAUUSD
WATCH
DEMO
23:33:53 UTC
OFF_HOURS
LIVE
Cycle 97
⬡ ACCOUNT · MT5 LIVE
$100,001.93
BALANCE (from market_data.json)
EQUITY
$100,001.93
MRG LVL
0%
POSITIONS
0
SESSION
+0.00
P&L today
⬡ MODE CONTROL
OFF
Dormant
WATCH
Data only
SIGNAL
Signals
SCALPER
Self-scalp
HYBRID
Both active
BRIDGE → FORGE via config.json
✓ SENTINEL
CLEAR TO TRADE
Next: ISM Services PMI
14:00 UTC
in 14h 26m
⬡ SYSTEM HEALTH
BRIDGE
Cycle 97 effective=WATCH
FORGE
DEMO @ VantageInternational-Demo
LISTENER
monitoring 3 channels
LENS
RSI=34.2 snapshot_age=0s
SENTINEL
Next: ISM Services PMI in 866min
AEGIS
risk=2.0% trades=8
SCRIBE
SQLite datastore
HERALD
bot active
AURUM
tokens=2770
RECONCILER
CLEAN mt5=0 scribe=0
ATHENA
API serving
GROUPS
ACTIVITY
SIGNALS
PERFORMANCE
ALL
--:--:--
BRIDGE
23:33:50
FORGE
23:33:50
LISTENER
23:33:27
LENS
23:33:50
SENTINEL
23:33:45
AEGIS
23:25:27
SCRIBE
23:33:50
HERALD
23:25:28
AURUM
23:26:53
RECONCILER
23:25:28
ATHENA
23:33:52
ALL
INFO
WARN
ERROR
62 events
⏸ PAUSE
23:25:28
RECONCILIATION
INFO
RECONCILIATION status=CLEAN issues=0 mt5=0 scribe=0
23:25:27
USER
INFO
STARTUP
23:21:42
RECONCILIATION
INFO
RECONCILIATION status=CLEAN issues=0 mt5=0 scribe=0
23:21:41
USER
INFO
STARTUP
23:16:22
RECONCILIATION
INFO
RECONCILIATION status=CLEAN issues=0 mt5=0 scribe=0
23:16:21
USER
INFO
STARTUP
23:15:22
RECONCILIATION
INFO
RECONCILIATION status=CLEAN issues=0 mt5=0 scribe=0
23:15:21
USER
INFO
STARTUP
23:08:35
RECONCILIATION
INFO
RECONCILIATION status=CLEAN issues=0 mt5=0 scribe=0
23:08:34
USER
INFO
STARTUP
23:03:13
RECONCILIATION
INFO
RECONCILIATION status=CLEAN issues=0 mt5=0 scribe=0
23:03:12
USER
INFO
STARTUP
23:02:15
RECONCILIATION
INFO
RECONCILIATION status=CLEAN issues=0 mt5=0 scribe=0
23:02:14
USER
INFO
STARTUP
22:33:20
AURUM
INFO
MODE_CHANGE
22:33:15
BRIDGE
INFO
CIRCUIT_BREAKER_ON MT5 market_data.json stale: 4586780s > 120s
22:33:09
AURUM
INFO
MODE_CHANGE
22:31:57
RECONCILIATION
INFO
RECONCILIATION status=CLEAN issues=0 mt5=0 scribe=0
22:31:55
USER
INFO
STARTUP
22:30:40
RECONCILIATION
INFO
RECONCILIATION status=CLEAN issues=0 mt5=0 scribe=0
22:30:39
USER
INFO
STARTUP
22:17:14
AURUM
INFO
MODE_CHANGE
22:16:13
AURUM
INFO
MODE_CHANGE
22:16:13
BRIDGE
INFO
CIRCUIT_BREAKER_ON MT5 market_data.json stale: 9999s > 120s
22:16:08
AURUM
INFO
MODE_CHANGE
22:13:45
USER
INFO
STARTUP
22:01:30
BRIDGE
INFO
SESSION_CHANGE NEW_YORK → OFF_HOURS
20:03:45
BRIDGE
INFO
SESSION_CHANGE OFF_HOURS → NEW_YORK
20:03:44
USER
INFO
STARTUP
19:32:21
AURUM
INFO
MODE_CHANGE
19:32:15
AURUM
INFO
MODE_CHANGE
17:00:00
BRIDGE
INFO
SESSION_CHANGE LONDON_NY → NEW_YORK
13:38:34
BRIDGE
INFO
SESSION_CHANGE OFF_HOURS → LONDON_NY
13:38:29
USER
INFO
STARTUP
13:00:04
BRIDGE
INFO
SESSION_CHANGE LONDON → LONDON_NY
08:00:01
BRIDGE
INFO
SESSION_CHANGE ASIAN → LONDON
07:24:24
BRIDGE
INFO
SESSION_CHANGE OFF_HOURS → ASIAN
07:24:23
USER
INFO
STARTUP
06:19:55
BRIDGE
INFO
SESSION_CHANGE OFF_HOURS → ASIAN
06:19:54
USER
INFO
STARTUP
06:05:35
BRIDGE
INFO
CIRCUIT_BREAKER_ON MT5 market_data.json stale: 9999s > 120s
06:05:30
AURUM
INFO
MODE_CHANGE
06:04:34
BRIDGE
INFO
SESSION_CHANGE OFF_HOURS → ASIAN
06:04:33
USER
INFO
STARTUP
06:03:55
BRIDGE
INFO
SESSION_CHANGE OFF_HOURS → ASIAN
06:03:54
USER
INFO
STARTUP
05:22:42
AURUM
INFO
MODE_CHANGE
04:54:26
AURUM
INFO
MODE_CHANGE
04:53:21
AURUM
INFO
MODE_CHANGE
04:53:10
AURUM
INFO
MODE_CHANGE
04:53:05
BRIDGE
INFO
CIRCUIT_BREAKER_ON MT5 market_data.json stale: 9999s > 120s
04:52:59
AURUM
INFO
MODE_CHANGE
04:52:39
AURUM
INFO
MODE_CHANGE
04:52:33
AURU
…
```

### Tab `signals`

**Findings:**
- Likely static Signals demo (G047 / 3181 band) — verify against SCRIBE/API.

```
⚒ ATHENA
SIGNAL SYSTEM · XAUUSD
WATCH
DEMO
23:33:54 UTC
OFF_HOURS
LIVE
Cycle 97
⬡ ACCOUNT · MT5 LIVE
$100,001.93
BALANCE (from market_data.json)
EQUITY
$100,001.93
MRG LVL
0%
POSITIONS
0
SESSION
+0.00
P&L today
⬡ MODE CONTROL
OFF
Dormant
WATCH
Data only
SIGNAL
Signals
SCALPER
Self-scalp
HYBRID
Both active
BRIDGE → FORGE via config.json
✓ SENTINEL
CLEAR TO TRADE
Next: ISM Services PMI
14:00 UTC
in 14h 26m
⬡ SYSTEM HEALTH
BRIDGE
Cycle 97 effective=WATCH
FORGE
DEMO @ VantageInternational-Demo
LISTENER
monitoring 3 channels
LENS
RSI=34.2 snapshot_age=0s
SENTINEL
Next: ISM Services PMI in 866min
AEGIS
risk=2.0% trades=8
SCRIBE
SQLite datastore
HERALD
bot active
AURUM
tokens=2770
RECONCILER
CLEAN mt5=0 scribe=0
ATHENA
API serving
GROUPS
ACTIVITY
SIGNALS
PERFORMANCE
5
Received
3
Executed
1
Skipped
1
Expired
14:22
BUY
3181–3185
EXECUTED
G047 · 8 trades
12:51
SELL
3198–3202
EXECUTED
G046 · 8 trades
11:34
BUY
3165–3169
SKIPPED
SLIPPAGE +22pips
10:17
SELL
3225–3229
EXECUTED
G044 · 8 trades
09:02
BUY
3148–3152
EXPIRED
NEWS_GUARD
◆ FORGE · EXECUTION QUOTE
SELL (bid)
$4609.82
BUY (ask)
$4610.08
XAUUSD · file age 3s · spread $0.26 (~26 pt)
FORGE 2026.04.05 23:33:50Z
🔭 TRADINGVIEW · INDICATORS
$4609.90
last (FX)
5m · snapshot 0m 0s ago
RSI 14
34.2
MACD
-6.71000
BB Rtg
-3
ADX
0.0
EMA20
$4634.3
EMA50
$4634.3
TV suggest: 0
⚡ AURUM · TELEGRAM + DASHBOARD
P&L today?
Open groups?
LENS reading?
All clear?
AURUM ◆AURUM online · WATCH · Balance $100,001.93 · 0 open · MT5 4609.82 / 4610.08. What do you need?
SEND
Also on Telegram — same AURUM, same live context
ATHENA · /api/live: execution + tradingview · FORGE + TV MCP · SCRIBE
Tick 2 · 3s poll
```

### Tab `perf`

**Findings:**
- Sparkline uses fixed placeholder array in app.js (not live series).

```
⚒ ATHENA
SIGNAL SYSTEM · XAUUSD
WATCH
DEMO
23:33:54 UTC
OFF_HOURS
LIVE
Cycle 97
⬡ ACCOUNT · MT5 LIVE
$100,001.93
BALANCE (from market_data.json)
EQUITY
$100,001.93
MRG LVL
0%
POSITIONS
0
SESSION
+0.00
P&L today
⬡ MODE CONTROL
OFF
Dormant
WATCH
Data only
SIGNAL
Signals
SCALPER
Self-scalp
HYBRID
Both active
BRIDGE → FORGE via config.json
✓ SENTINEL
CLEAR TO TRADE
Next: ISM Services PMI
14:00 UTC
in 14h 26m
⬡ SYSTEM HEALTH
BRIDGE
Cycle 97 effective=WATCH
FORGE
DEMO @ VantageInternational-Demo
LISTENER
monitoring 3 channels
LENS
RSI=34.2 snapshot_age=0s
SENTINEL
Next: ISM Services PMI in 866min
AEGIS
risk=2.0% trades=8
SCRIBE
SQLite datastore
HERALD
bot active
AURUM
tokens=2770
RECONCILER
CLEAN mt5=0 scribe=0
ATHENA
API serving
GROUPS
ACTIVITY
SIGNALS
PERFORMANCE
0%
Win Rate
+0
Avg Pips
$0.00
Total P&L
0
Trades
0
Wins
0
Losses
TODAY'S P&L CURVE
◆ FORGE · EXECUTION QUOTE
SELL (bid)
$4609.82
BUY (ask)
$4610.08
XAUUSD · file age 3s · spread $0.26 (~26 pt)
FORGE 2026.04.05 23:33:50Z
🔭 TRADINGVIEW · INDICATORS
$4609.90
last (FX)
5m · snapshot 0m 0s ago
RSI 14
34.2
MACD
-6.71000
BB Rtg
-3
ADX
0.0
EMA20
$4634.3
EMA50
$4634.3
TV suggest: 0
⚡ AURUM · TELEGRAM + DASHBOARD
P&L today?
Open groups?
LENS reading?
All clear?
AURUM ◆AURUM online · WATCH · Balance $100,001.93 · 0 open · MT5 4609.82 / 4610.08. What do you need?
SEND
Also on Telegram — same AURUM, same live context
ATHENA · /api/live: execution + tradingview · FORGE + TV MCP · SCRIBE
Tick 2 · 3s poll
```

## Mock / static UI flagged by audit

- **signals**: Hardcoded Received/Executed tiles and row list in dashboard source — `dashboard/app.js — tab==='signals' block`
- **performance**: Sparkline data=[0,0,12,...] is mock — `dashboard/app.js — Sparkline in perf tab`

## Suggested tasks

- Replace Signals tab with API-driven rows (e.g. extend athena_api + SCRIBE query for signals_received).
- When no data, show explicit "No signals today" instead of demo rows.
- Drive Performance sparkline from scribe performance history or hide chart until real series exists.
- Add data-testid on major panels if more granular Playwright asserts are needed.

---

**Instruction for Claude:** Prioritize replacing demo Signals rows and mock sparkline with real SCRIBE/API data; keep layout and theme; add empty states when no data.
