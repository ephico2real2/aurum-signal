# SIGNAL SYSTEM — Mode Architecture & Workflow

This document defines how each operating mode behaves at runtime, which component owns trade entry, where AEGIS applies, and how FORGE native scalping is activated.

## Mode ownership model
- `BRIDGE` owns global mode state (`mode`, `effective_mode`) and writes `MT5/config.json`.
- `FORGE` executes orders in MT5 and can run native price-action scalping when `scalper_mode != NONE`.
- `AEGIS` gates all BRIDGE-originated entries (SIGNAL, BRIDGE SCALPER, AUTO_SCALPER/AURUM commands).
- `SENTINEL` + circuit breaker can force `effective_mode=WATCH` regardless of requested mode.

## Runtime mode matrix
- `OFF`
  - Purpose: pause trading logic.
  - BRIDGE behavior: minimal loop; writes status.
  - FORGE behavior: receives `effective_mode=OFF`; no entries.
  - AEGIS: not used for new entries.
  - Native FORGE scalper mode: `NONE`.
- `WATCH`
  - Purpose: observe/collect state, no entry logic.
  - BRIDGE behavior: keeps heartbeat + status + lens refresh.
  - FORGE behavior: runs data export only.
  - AEGIS: not used for new entries.
  - Native FORGE scalper mode: `NONE`.
- `SIGNAL`
  - Purpose: execute Telegram/LISTENER parsed signals.
  - Entry path: LISTENER -> BRIDGE `_process_signal` -> AEGIS -> FORGE `OPEN_GROUP`.
  - Room priority: when `SIGNAL_TRADE_ROOMS` is set, only listed rooms dispatch; others are logged `WATCH_ONLY`.
  - AEGIS: required.
  - Native FORGE scalper mode: `NONE`.
- `SCALPER`
  - Purpose: scalping mode with both BRIDGE and FORGE scalper capability available.
  - Entry path A: BRIDGE `_scalper_logic` -> FORGE `OPEN_GROUP` (direct, no AEGIS gate).
  - Entry path B: FORGE native `CheckNativeScalperSetups` (price action) -> direct MT5 orders.
  - AEGIS: not in SCALPER entry path.
  - AEGIS does not pre-approve or close SCALPER/FORGE-native entries.
  - Native FORGE scalper mode: `FORGE_SCALPER_MODE` (e.g. `BB_BOUNCE|BB_BREAKOUT|DUAL`).
- `HYBRID`
  - Purpose: combine signal-following plus scalping.
  - Entry paths:
    - LISTENER signal path (AEGIS gated).
    - BRIDGE scalper path (direct, no AEGIS gate).
    - FORGE native scalper path (direct in EA when setup triggers).
  - AEGIS: applies to SIGNAL (and other BRIDGE non-scalper request paths), not the scalper sub-path.
  - In HYBRID, AEGIS can still reject SIGNAL requests, but does not gate scalper sub-paths (BRIDGE scalper or FORGE-native).
  - Native FORGE scalper mode: `FORGE_SCALPER_MODE`.
- `AUTO_SCALPER`
  - Purpose: autonomous AURUM-driven strategy polling.
  - Entry path: BRIDGE `_auto_scalper_tick` -> AURUM command -> BRIDGE `_dispatch_aurum_open_group` -> AEGIS -> FORGE `OPEN_GROUP`.
  - AEGIS: required for AURUM/BRIDGE path.
  - Native FORGE scalper mode: `NONE` unless mode is changed to `SCALPER`/`HYBRID`.

## Mode to FORGE config mapping
BRIDGE writes `MT5/config.json` every tick. `scalper_mode` is mapped as:
- mode in (`SCALPER`, `HYBRID`) -> `scalper_mode = FORGE_SCALPER_MODE`
- all other modes -> `scalper_mode = NONE`

This ensures FORGE native scalping is explicitly active only in modes that include scalping behavior.
For DB/query separation, BRIDGE direct scalper opens are tagged as `SCALPER_SUBPATH_DIRECT`
in `trade_groups.source` and `system_events` trade-queued notes/reason.

## Effective mode overrides
Even when requested mode is trading-enabled, BRIDGE can force WATCH behavior:
- SENTINEL active: `effective_mode=WATCH`
- MT5 stale/circuit breaker: `effective_mode=WATCH`
- Equity DD breaker event: closes exposure and moves mode to `WATCH`
- Mode pin: if `BRIDGE_PIN_MODE` is set (for example `HYBRID`), BRIDGE blocks mode changes away from that value (`MODE_CHANGE_BLOCKED` in `system_events`).

In all these cases, FORGE receives `effective_mode=WATCH`; native scalper setup checks are not executed.
## Manual / unmanaged MT5 positions
- `market_data.json` exports all account positions and tags each position with `forge_managed`.
- BRIDGE tracking is split by this flag:
  - `forge_managed=true`: normal FORGE strategy lifecycle.
  - `forge_managed=false`: unmanaged/manual lifecycle.
- Unmanaged/manual positions are persisted in SCRIBE as synthetic groups (`trade_groups.source='MANUAL_MT5'`) and audited with `UNMANAGED_POSITION_OPEN` / `UNMANAGED_POSITION_CLOSED`.
## Sydney kill-zone and daily open alert
- BRIDGE session logic now emits a distinct `SYDNEY` session label using `Australia/Sydney` local hours (`SESSION_SYDNEY_LOCAL_START/END`), so DST shifts are handled automatically.
- Daily Sydney-open alert is also DST-aware and fires once per Sydney local date (`SYDNEY_OPEN_ALERT_ENABLED`).
- Audit event: `SYDNEY_OPEN_ALERT` in `system_events`.

## Per-mode ASCII diagrams
### OFF mode
```
Operator/ATHENA -> BRIDGE mode=OFF
                    |
                    +-> writes status/config (effective_mode=OFF)
                    |
                    +-> no signal path
                    +-> no scalper path
                    +-> no AURUM auto-scaler path
                                      |
                                      v
                                 FORGE mode=OFF
                               (data export only)
```
Use when you want the stack alive but trade entry paused.

### WATCH mode
```
Operator/ATHENA -> BRIDGE mode=WATCH
                    |
                    +-> heartbeat + status + lens refresh
                    +-> skip LISTENER execution
                    +-> skip BRIDGE scalper execution
                    +-> skip AUTO_SCALPER polling
                    +-> config.scalper_mode=NONE
                                      |
                                      v
                                 FORGE mode=WATCH
                           Write market_data / mode_status
                           No native scalper entries
```
Use for observability, feed checks, and dry-run monitoring.

### SIGNAL mode
```
Telegram channel
   |
   v
LISTENER parse -> parsed_signal.json -> BRIDGE _process_signal
                                          |
                                          v
                                      AEGIS validate
                                   approved | rejected
                                           / \
                                          v   v
                         command.json OPEN_GROUP   SCRIBE/HERALD reject log
                                   |
                                   v
                              FORGE executes
                         (native scalper disabled)
```
Signal execution is AEGIS-gated and FORGE native scalper is OFF.

### SCALPER mode
```
                    BRIDGE mode=SCALPER
                     /               \
                    v                 v
        BRIDGE _scalper_logic      config.scalper_mode=FORGE_SCALPER_MODE
                |                                  |
                v                                  v
          FORGE OPEN_GROUP                    FORGE native scalper
        (direct, no AEGIS)                  CheckNativeScalperSetups
                |                                  |
                +------------------+---------------+
                          (both paths can fire)
```
BRIDGE scalper path is direct (no AEGIS); FORGE native path is EA-side logic.
AEGIS does not gate or close scalper entries.

### HYBRID mode (SIGNAL + SCALPER)
```
                         BRIDGE mode=HYBRID
                  _____________|____________________
                 /             |                    \
                v              v                     v
      LISTENER signal path  BRIDGE scalper path      FORGE native path
      _process_signal       _scalper_logic           CheckNativeScalperSetups
             |                    |                          |
             v                    v                          v
           AEGIS          FORGE OPEN_GROUP            EA safety filters
             |            (direct, no AEGIS)                 |
             +----------------------+-------------------------+
                                    |
                                    v
                              FORGE executions
```
HYBRID runs both signal-following and scalping workflows together.
Signal path can be AEGIS-rejected; scalper paths are governed by BRIDGE/FORGE setup + safety filters.

### AUTO_SCALPER mode
```
BRIDGE _auto_scalper_tick (interval poll)
            |
            v
      AURUM strategy reply
            |
            v
   BRIDGE _dispatch_aurum_open_group
            |
            v
         AEGIS validate
      approved | rejected
              / \
             v   v
   command.json OPEN_GROUP   SCRIBE/HERALD reject log
             |
             v
        FORGE executes
 (native scalper mapping remains NONE in AUTO_SCALPER mode)
```
AUTO_SCALPER is autonomous, but still AEGIS-gated before execution.

## End-to-end workflow examples
### 1) SIGNAL mode trade
1. LISTENER parses signal and writes `parsed_signal.json`.
2. BRIDGE reads signal and calls AEGIS.
3. If approved, BRIDGE writes `command.json` `OPEN_GROUP`.
4. FORGE opens ladder trades; BRIDGE tracks/records lifecycle in SCRIBE.

### 2) SCALPER/HYBRID native FORGE trade
1. BRIDGE writes `config.json` with `scalper_mode=FORGE_SCALPER_MODE`.
2. FORGE `OnTick` runs `CheckNativeScalperSetups`.
3. If setup + safety checks pass, FORGE places trades directly.
4. FORGE writes `scalper_entry.json`; BRIDGE logs the group in SCRIBE and emits notifications.

### 3) AUTO_SCALPER trade
1. BRIDGE polls AURUM with multi-timeframe context.
2. AURUM emits `OPEN_GROUP` intent.
3. BRIDGE validates with AEGIS.
4. On approval, BRIDGE sends command to FORGE for execution.
