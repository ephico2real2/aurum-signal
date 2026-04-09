# SCRIBE SQL examples for `POST /api/scribe/query`

ATHENA exposes **read-only** SQL: the body must be `{"sql": "SELECT ..."}`. Anything that does not start with `SELECT` (after trimming) is rejected.

**Canonical machine list:** `schemas/scribe_query_examples.json` (same statements are offered as **Examples** in Swagger UI for `/api/scribe/query`).

**Keep OpenAPI in sync:** after editing the JSON, run **`make sync-openapi-scribe`** (regenerates the marked block in `schemas/openapi.yaml`). CI checks idempotency via `test_sync_openapi_scribe_script_idempotent`.

**Server limits (ATHENA):** responses include `truncated` and `max_rows`. Env: **`SCRIBE_QUERY_MAX_ROWS`** (default 500, max 50000), **`SCRIBE_QUERY_BUSY_MS`** (SQLite `busy_timeout`, default 5000). Optional: **`ATHENA_SCRIBE_QUERY_SECRET`** — if set, send **`Authorization: Bearer <secret>`** or header **`X-ATHENA-SCRIBE-TOKEN`**.

**Ground-truth DDL:** `python/scribe.py` → variable `DDL` (table and column names below match it).

---

## Tables (quick reference)

| Table | Purpose |
|--------|---------|
| `system_events` | Audit trail: mode changes, startup/shutdown, reconciliation, etc. |
| `trading_sessions` | Session windows with rolled-up stats when closed |
| `market_snapshots` | Optional periodic indicator / price snapshots |
| `signals_received` | Parsed Telegram / signal messages and disposition |
| `trade_groups` | Logical groups opened from signals |
| `trade_positions` | Individual tickets / legs |
| `news_events` | News guard / calendar context |
| `aurum_conversations` | AURUM query/response log |
| `component_heartbeats` | BRIDGE, LISTENER, FORGE, … liveness |
| `trade_closures` | SL/TP hit logging — every position closure with inferred reason |

---

## Usage

```bash
curl -sS -X POST "http://localhost:7842/api/scribe/query" \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT 1 AS ok"}' | python3 -m json.tool
```

Response shape: `{ "rows": [ ... ], "count": N }`. Each row is a JSON object (column names → values).

---

## Examples (basic → mid)

### 1. Ping

```sql
SELECT 1 AS ok
```

### 2. Latest system events

```sql
SELECT id, timestamp, event_type, prev_mode, new_mode, triggered_by, reason
FROM system_events
ORDER BY id DESC
LIMIT 20
```

### 3. Mode changes only

Common `event_type` values include `MODE_CHANGE`, `STARTUP`, `SHUTDOWN`, `RECONCILIATION` (see `bridge.py` / `reconciler.py` / `sentinel.py`).

```sql
SELECT timestamp, prev_mode, new_mode, triggered_by, reason, session
FROM system_events
WHERE event_type = 'MODE_CHANGE'
ORDER BY id DESC
LIMIT 50
```

### 4. Component heartbeats

```sql
SELECT component, status, timestamp, note, last_action, cycle
FROM component_heartbeats
ORDER BY id DESC
LIMIT 30
```

### 5. Recent signals

```sql
SELECT id, timestamp, mode, channel_name, direction, action_taken, skip_reason, trade_group_id
FROM signals_received
ORDER BY id DESC
LIMIT 25
```

### 6. Signal disposition counts (last 7 days)

```sql
SELECT action_taken, COUNT(*) AS n
FROM signals_received
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY action_taken
ORDER BY n DESC
```

### 7. Open trade groups

```sql
SELECT id, timestamp, direction, status, num_trades, total_pnl, pips_captured
FROM trade_groups
WHERE status = 'OPEN'
ORDER BY id DESC
```

### 8. Open positions

```sql
SELECT tp.id, tp.trade_group_id, tp.ticket, tp.direction, tp.lot_size, tp.entry_price, tp.status
FROM trade_positions tp
WHERE tp.status = 'OPEN'
ORDER BY tp.id DESC
```

### 9. Recent closed P&L

```sql
SELECT id, trade_group_id, ticket, direction, pnl, pips, close_time, close_reason
FROM trade_positions
WHERE status = 'CLOSED' AND close_time >= datetime('now', '-7 days')
ORDER BY close_time DESC
LIMIT 50
```

### 10. Trading session history

```sql
SELECT id, session_name, session_date, open_time, close_time, mode_at_open, total_pnl, win_rate
FROM trading_sessions
ORDER BY id DESC
LIMIT 15
```

### 11. AURUM conversations (truncated text)

```sql
SELECT id, timestamp, mode, source,
       substr(query, 1, 120) AS query_preview,
       substr(response, 1, 120) AS response_preview,
       tokens_used
FROM aurum_conversations
ORDER BY id DESC
LIMIT 15
```

### 12. News events

```sql
SELECT id, timestamp, event_name, impact, currency, guard_start, guard_end, mode_before
FROM news_events
ORDER BY id DESC
LIMIT 15
```

### 13. Market snapshots (if populated)

```sql
SELECT id, timestamp, mode, source, symbol, bid, ask, rsi_14, macd_hist, session
FROM market_snapshots
ORDER BY id DESC
LIMIT 10
```

### 14. Join signals to trade groups

```sql
SELECT sr.id AS signal_id, sr.timestamp, sr.channel_name, sr.action_taken,
       tg.id AS group_id, tg.status AS group_status, tg.total_pnl
FROM signals_received sr
LEFT JOIN trade_groups tg ON sr.trade_group_id = tg.id
ORDER BY sr.id DESC
LIMIT 30
```

### 15. Recent trade closures (SL/TP hits)

```sql
SELECT id, timestamp, ticket, trade_group_id, direction, close_reason, pnl, pips, close_price, session, mode
FROM trade_closures
ORDER BY id DESC
LIMIT 20
```

### 16. SL vs TP hit rate (last 7 days)

```sql
SELECT
    close_reason,
    COUNT(*) AS count,
    ROUND(SUM(pnl), 2) AS total_pnl,
    ROUND(AVG(pnl), 2) AS avg_pnl,
    ROUND(AVG(pips), 1) AS avg_pips
FROM trade_closures
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY close_reason
ORDER BY count DESC
```

### 17. Closure breakdown by session

```sql
SELECT
    session,
    SUM(CASE WHEN close_reason = 'SL_HIT' THEN 1 ELSE 0 END) AS sl_hits,
    SUM(CASE WHEN close_reason LIKE 'TP%' THEN 1 ELSE 0 END) AS tp_hits,
    ROUND(SUM(pnl), 2) AS total_pnl,
    COUNT(*) AS total
FROM trade_closures
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY session
ORDER BY total DESC
```

### 18. Closures for a specific group

```sql
SELECT ticket, direction, close_reason, entry_price, close_price, pnl, pips, lot_size
FROM trade_closures
WHERE trade_group_id = 19
ORDER BY id
```

---

## Tips

- Prefer `ORDER BY id DESC` or `ORDER BY timestamp DESC` for time-ordered tables; `id` is monotonic.
- SQLite `datetime('now', '-7 days')` is interpreted in UTC wall-clock style suitable for rough windows; align with how timestamps are stored (ISO strings from SCRIBE).
- For large exports of `system_events`, consider **`GET /api/events`** or **`GET /api/events/export`** instead of ad-hoc SQL.

---

## Related

- `docs/DATA_CONTRACT.md` — HTTP vs file bus
- `schemas/openapi.yaml` — Swagger **Examples** dropdown on `/api/scribe/query`
