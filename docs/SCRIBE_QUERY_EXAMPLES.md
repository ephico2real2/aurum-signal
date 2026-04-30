# SCRIBE Query Examples
Practical SQL examples for `POST /api/scribe/query` in ATHENA.

## Purpose
SCRIBE is the audit backbone of the system. This guide exists so operators can quickly answer:
- what the system decided,
- why it decided it,
- what was executed in MT5,
- and how outcomes were recorded.

It also includes newer telemetry paths such as unmanaged/manual MT5 position tracking (`MANUAL_MT5`), broker-first close attribution (with inference fallback), and session/open alert events.

## API contract and guardrails
- Endpoint accepts **read-only SQL** in request body: `{"sql":"SELECT ..."}`.
- Statement must begin with `SELECT` or `WITH` (after trimming), must be single-statement, and runs through read-only SQLite mode + authorizer guardrails.
- Response shape: `{"rows":[...], "count":N, "truncated":bool, "max_rows":int}`.
- Same secure query executor is also used by AEB actions (`aurum_cmd.json` `SCRIBE_QUERY`, and `POST /api/aurum/exec`).

Server controls:
- `SCRIBE_QUERY_MAX_ROWS` (default `500`, max `50000`)
- `SCRIBE_QUERY_BUSY_MS` (SQLite busy timeout, default `5000`)
- Optional protection: `ATHENA_SCRIBE_QUERY_SECRET` via `Authorization: Bearer <secret>` or `X-ATHENA-SCRIBE-TOKEN`.

Source-of-truth references:
- DDL/schema: `python/scribe.py` (`DDL`)
- Machine example list: `schemas/scribe_query_examples.json`
- OpenAPI sync command: `make sync-openapi-scribe`

## Minimal usage example
```bash
curl -sS -X POST "http://localhost:7842/api/scribe/query" \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT 1 AS ok"}' | python3 -m json.tool
```

## AEB HTTP execution path (`/api/aurum/exec`)
Use when BRIDGE/AURUM dispatches via HTTP envelope (same result shape semantics as AEB executor):
```bash
curl -sS -X POST "http://localhost:7842/api/aurum/exec" \
  -H "Content-Type: application/json" \
  -d '{"action":"SCRIBE_QUERY","sql":"SELECT id, event_type, timestamp FROM system_events ORDER BY id DESC LIMIT 5"}' \
  | python3 -m json.tool
```

## Schema snapshot (operator view)
- `system_events`: lifecycle/audit events (mode changes, session changes, alerts, circuit events)
- `trading_sessions`: per-session rollups and boundaries
- `market_snapshots`: periodic market+indicator snapshots
- `market_regimes`: inferred regime snapshots (label, confidence, posterior, model/fallback metadata)
- `signals_received`: parsed signal intake + disposition
- `trade_groups`: logical trade bundles
- `trade_positions`: ticket-level position lifecycle
- `trade_closures`: closure reason ledger (broker-close hints first; SL/TP/manual inference fallback)
- `news_events`: news guard windows and context
- `aurum_conversations`: AI interaction audit
- `component_heartbeats`: per-component liveness
- `vision_extractions`: image extraction lineage and confidence

## Core operational queries
### 1) Recent system events
```sql
SELECT id, timestamp, event_type, prev_mode, new_mode, triggered_by, reason, session
FROM system_events
ORDER BY id DESC
LIMIT 50;
```

### 2) Mode transition audit trail
```sql
SELECT timestamp, prev_mode, new_mode, triggered_by, reason
FROM system_events
WHERE event_type = 'MODE_CHANGE'
ORDER BY id DESC
LIMIT 100;
```

### 3) Component heartbeat monitor
```sql
SELECT component, status, timestamp, last_action, note, error_msg, cycle
FROM component_heartbeats
ORDER BY id DESC
LIMIT 100;
```

### 4) Signals and disposition summary (7d)
```sql
SELECT action_taken, COUNT(*) AS n
FROM signals_received
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY action_taken
ORDER BY n DESC;
```

### 5) Signal → group linkage check
```sql
SELECT
  sr.id AS signal_id,
  sr.timestamp,
  sr.channel_name,
  sr.action_taken,
  sr.skip_reason,
  sr.trade_group_id,
  tg.status AS group_status,
  tg.total_pnl
FROM signals_received sr
LEFT JOIN trade_groups tg ON tg.id = sr.trade_group_id
ORDER BY sr.id DESC
LIMIT 50;
```

## Trade lifecycle and P&L queries
### 6) Open groups and open positions
```sql
SELECT
  tg.id AS group_id,
  tg.source,
  tg.direction,
  tg.status,
  tp.ticket,
  tp.lot_size,
  tp.entry_price,
  tp.sl,
  tp.tp
FROM trade_groups tg
LEFT JOIN trade_positions tp ON tp.trade_group_id = tg.id AND tp.status = 'OPEN'
WHERE tg.status IN ('OPEN','PARTIAL')
ORDER BY tg.id DESC, tp.id DESC;
```

### 7) Recent closed positions (7d)
```sql
SELECT
  id, trade_group_id, ticket, direction, status, close_reason, pnl, pips, close_time
FROM trade_positions
WHERE status = 'CLOSED'
  AND close_time >= datetime('now', '-7 days')
ORDER BY close_time DESC
LIMIT 100;
```

### 8) Closure reason quality view
```sql
SELECT
  close_reason,
  COUNT(*) AS n,
  ROUND(SUM(pnl), 2) AS pnl_total,
  ROUND(AVG(pnl), 2) AS pnl_avg,
  ROUND(AVG(pips), 1) AS pips_avg
FROM trade_closures
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY close_reason
ORDER BY n DESC;
```

### 9) Session-level closure performance
```sql
SELECT
  session,
  COUNT(*) AS closes,
  SUM(CASE WHEN close_reason = 'SL_HIT' THEN 1 ELSE 0 END) AS sl_hits,
  SUM(CASE WHEN close_reason LIKE 'TP%' THEN 1 ELSE 0 END) AS tp_hits,
  ROUND(SUM(pnl), 2) AS total_pnl
FROM trade_closures
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY session
ORDER BY closes DESC;
```

## Manual / unmanaged MT5 tracking queries
### 10) All manual/unmanaged groups created by BRIDGE
```sql
SELECT
  id, timestamp, session, mode, source, direction, status, total_pnl, pips_captured
FROM trade_groups
WHERE source = 'MANUAL_MT5'
ORDER BY id DESC
LIMIT 100;
```

### 11) Ticket-level lifecycle for MANUAL_MT5 groups
```sql
SELECT
  tg.id AS group_id,
  tg.timestamp AS group_opened_at,
  tp.ticket,
  tp.direction,
  tp.entry_price,
  tp.close_price,
  tp.close_reason,
  tp.pnl,
  tp.pips,
  tp.status
FROM trade_groups tg
JOIN trade_positions tp ON tp.trade_group_id = tg.id
WHERE tg.source = 'MANUAL_MT5'
ORDER BY tg.id DESC, tp.id ASC
LIMIT 200;
```

### 12) System events for unmanaged position open/close
```sql
SELECT
  id, timestamp, event_type, reason, notes
FROM system_events
WHERE event_type IN ('UNMANAGED_POSITION_OPEN', 'UNMANAGED_POSITION_CLOSED')
ORDER BY id DESC
LIMIT 100;
```

### 13) Manual/unmanaged closures from closure ledger
```sql
SELECT
  tc.id,
  tc.timestamp,
  tc.trade_group_id,
  tc.ticket,
  tc.direction,
  tc.close_reason,
  tc.pnl,
  tc.pips
FROM trade_closures tc
JOIN trade_groups tg ON tg.id = tc.trade_group_id
WHERE tg.source = 'MANUAL_MT5'
ORDER BY tc.id DESC
LIMIT 100;
```

## Session intelligence and alerts
### 14) Trading session rollups
```sql
SELECT
  id, session_name, session_date, open_time, close_time, mode_at_open,
  signals_received, signals_executed, signals_skipped, groups_opened,
  total_pnl, total_pips, wins, losses, win_rate
FROM trading_sessions
ORDER BY id DESC
LIMIT 30;
```

### 15) Sydney open alert audit trail
```sql
SELECT
  id, timestamp, event_type, session, reason, notes
FROM system_events
WHERE event_type = 'SYDNEY_OPEN_ALERT'
ORDER BY id DESC
LIMIT 30;
```

## Vision and AI lineage queries
### 16) Latest image extraction outcomes
```sql
SELECT
  id, timestamp, caller, source_channel, confidence, downstream_result, error
FROM vision_extractions
ORDER BY id DESC
LIMIT 50;
```

### 17) LISTENER mixed/image signal linkage quality
```sql
SELECT
  sr.id AS signal_id,
  sr.timestamp,
  sr.signal_source_type,
  sr.vision_confidence,
  sr.vision_extraction_id,
  ve.downstream_result,
  ve.error
FROM signals_received sr
LEFT JOIN vision_extractions ve ON ve.id = sr.vision_extraction_id
WHERE sr.signal_source_type IN ('IMAGE','MIXED')
ORDER BY sr.id DESC
LIMIT 100;
```

## Regime diagnostics queries
### 18) Latest inferred regime snapshot
```sql
SELECT
  id, timestamp, mode, session, regime_label, confidence, model_name, model_version,
  stale, age_sec, fallback_reason, entry_mode, apply_entry_policy, entry_gate_reason
FROM market_regimes
ORDER BY id DESC
LIMIT 20;
```

### 19) Regime transition tape (last 24h)
```sql
SELECT
  timestamp,
  regime_label,
  confidence,
  model_name,
  stale,
  entry_mode,
  fallback_reason
FROM market_regimes
WHERE timestamp >= datetime('now', '-24 hours')
ORDER BY timestamp DESC
LIMIT 200;
```

### 20) Closed-group performance by regime (30d)
```sql
SELECT
  COALESCE(regime_label, 'UNKNOWN') AS regime_label,
  COUNT(*) AS groups_closed,
  SUM(CASE WHEN total_pnl > 0 THEN 1 ELSE 0 END) AS wins,
  SUM(CASE WHEN total_pnl < 0 THEN 1 ELSE 0 END) AS losses,
  ROUND(SUM(total_pnl), 2) AS pnl_total,
  ROUND(AVG(total_pnl), 2) AS pnl_avg
FROM trade_groups
WHERE status NOT IN ('OPEN','PARTIAL')
  AND closed_at IS NOT NULL
  AND closed_at >= datetime('now', '-30 days')
GROUP BY COALESCE(regime_label, 'UNKNOWN')
ORDER BY groups_closed DESC;
```

## Query hygiene notes
- Prefer `ORDER BY id DESC` for append-only event tables.
- Use bounded windows (`datetime('now','-7 days')`) to keep response size predictable.
- For large event exports, prefer API endpoints such as `GET /api/events` or `GET /api/events/export`.

## Related docs
- `docs/DATA_CONTRACT.md`
- `docs/ARCHITECTURE.md`
- `schemas/openapi.yaml`
