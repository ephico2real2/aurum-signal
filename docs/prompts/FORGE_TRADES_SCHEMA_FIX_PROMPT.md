# FORGE TRADES Schema Fix — `UNIQUE(deal_ticket, run_id)` Impact Prompt

## Problem Statement

The `TRADES` table in the FORGE journal DB was created with `deal_ticket INTEGER UNIQUE`.
A `run_id INTEGER DEFAULT 0` column was added later via `ALTER TABLE ADD COLUMN`, but
SQLite cannot add a new column to an existing UNIQUE constraint. The old constraint on
`deal_ticket` alone is still in effect.

**Impact**: In the Strategy Tester, MT5 assigns deal tickets sequentially starting at 1
for every new backtest run. With `deal_ticket UNIQUE` and `INSERT OR IGNORE`, every run
after the first silently loses all trades whose ticket numbers collide with run 1 (i.e.,
almost all of them). Trade P&L data is effectively only stored for the first run that
ever populates the DB.

The AURUM mirror table `forge_journal_trades` has the same problem:
`UNIQUE(deal_ticket, journal_source)` means tester deal ticket 1 from run 2 conflicts
with tester deal ticket 1 from run 1, so SCRIBE silently discards run 2 onward.

---

## Live Journal Path — End-to-End Review

### Flow
```
FORGE (ea/FORGE.mq5)
  JournalImportTrades()
    HistorySelect() → INSERT OR IGNORE INTO TRADES (deal_ticket UNIQUE)
    g_tester_run_id = 0 for live → run_id = 0 on all rows
    DB: FORGE_journal_XAUUSD.db  (DATABASE_OPEN_COMMON → MT5 Common Files)

BRIDGE (python/bridge.py, line 2745–2755)
  Every 60s: _resolve_forge_journal_paths()
    Finds FORGE_journal_XAUUSD.db (live) and FORGE_journal_XAUUSD_tester.db (tester)
    Calls scribe.sync_forge_journal(path, source='live'|'tester')
    Calls scribe.sync_forge_journal_trades(path, source='live'|'tester')

SCRIBE (python/scribe.py)
  sync_forge_journal_trades()
    Reads FORGE TRADES WHERE synced=0
    INSERT OR IGNORE INTO forge_journal_trades UNIQUE(deal_ticket, journal_source)
    Marks synced=1 in source journal
```

### Live vs Tester key differences
| | Live | Tester |
|---|---|---|
| DB file | `FORGE_journal_XAUUSD.db` | `FORGE_journal_XAUUSD_tester.db` |
| DB flags | `DATABASE_OPEN_COMMON` (visible to BRIDGE) | Agent-local `MQL5/Files/` |
| `run_id` | Always `0` | Sequential per run (1, 2, 3…) |
| Deal ticket source | Broker-assigned (globally unique, never resets) | MT5 tester (restarts from 1 each run) |
| `deal_ticket UNIQUE` safe? | ✅ Yes — broker tickets never collide | ❌ No — tickets repeat every run |

**For live trading, `deal_ticket UNIQUE` was never a problem.** The fix must handle
both modes: keep deduplication for live (broker tickets truly unique within `run_id=0`)
while enabling multi-run accumulation for tester.

---

## Complete File Impact

### 1. `ea/FORGE.mq5`

**Problem**: `CREATE TABLE IF NOT EXISTS TRADES` uses `deal_ticket INTEGER UNIQUE`.
The `run_id` column was added via `ALTER TABLE ADD COLUMN` but cannot extend the
UNIQUE constraint.

**Fix required**: Table migration in `JournalInit()`. Since SQLite cannot alter a
UNIQUE constraint, the table must be recreated:

```
1. Check if TRADES has correct constraint via sqlite_master
2. If old schema (unique on deal_ticket alone):
   a. RENAME TABLE TRADES TO _TRADES_old
   b. CREATE new TRADES with UNIQUE(deal_ticket, run_id)
   c. INSERT INTO TRADES SELECT ... FROM _TRADES_old (set run_id=0 for old rows)
   d. DROP TABLE _TRADES_old
```

New TRADES DDL:
```sql
CREATE TABLE IF NOT EXISTS TRADES (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_ticket  INTEGER NOT NULL,
    order_ticket INTEGER,
    symbol       TEXT NOT NULL,
    type         INTEGER,
    direction    INTEGER,
    volume       REAL,
    price        REAL,
    profit       REAL,
    swap         REAL,
    commission   REAL,
    magic        INTEGER,
    comment      TEXT,
    time         INTEGER,
    time_msc     INTEGER,
    synced       INTEGER DEFAULT 0,
    run_id       INTEGER DEFAULT 0,
    UNIQUE(deal_ticket, run_id)
);
```

Migration detection query:
```sql
SELECT sql FROM sqlite_master
WHERE type='table' AND name='TRADES'
  AND sql LIKE '%deal_ticket INTEGER UNIQUE%';
```
If this returns a row, run the table recreation.

---

### 2. `python/scribe.py`

**Problem A**: DDL constant (lines 153–172) defines `forge_journal_trades` with:
```sql
UNIQUE(deal_ticket, journal_source)
```
Must become:
```sql
UNIQUE(deal_ticket, journal_source, run_id)
```

**Problem B**: `_migrate()` executescript (lines 517–540) also creates `forge_journal_trades`
with the same old constraint. Since it uses `CREATE TABLE IF NOT EXISTS`, existing
deployments are never updated.

**Fix**: Add migration in `_migrate()` to detect old schema and recreate table:
```python
fjt_cols = [r[1] for r in conn.execute("PRAGMA table_info(forge_journal_trades)").fetchall()]
if "run_id" not in fjt_cols or not _has_run_id_in_unique(conn, "forge_journal_trades"):
    # Recreate forge_journal_trades with UNIQUE(deal_ticket, journal_source, run_id)
    conn.executescript("""
        ALTER TABLE forge_journal_trades RENAME TO _fjt_old;
        CREATE TABLE forge_journal_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            forge_rowid INTEGER NOT NULL,
            deal_ticket INTEGER NOT NULL,
            order_ticket INTEGER,
            symbol TEXT NOT NULL,
            type INTEGER,
            direction INTEGER,
            volume REAL,
            price REAL,
            profit REAL,
            swap REAL,
            commission REAL,
            magic INTEGER,
            comment TEXT,
            time INTEGER NOT NULL,
            time_msc INTEGER,
            journal_source TEXT DEFAULT 'live',
            run_id INTEGER DEFAULT 0,
            UNIQUE(deal_ticket, journal_source, run_id)
        );
        INSERT INTO forge_journal_trades SELECT *, 0 FROM _fjt_old;
        DROP TABLE _fjt_old;
        CREATE INDEX IF NOT EXISTS idx_fjt_time ON forge_journal_trades(time);
        CREATE INDEX IF NOT EXISTS idx_fjt_magic ON forge_journal_trades(magic);
        CREATE INDEX IF NOT EXISTS idx_fjt_run ON forge_journal_trades(run_id);
    """)
```

Helper to check unique constraint:
```python
def _has_run_id_in_unique(conn, table):
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return sql and "run_id" in sql[0]
```

**Problem C**: `sync_forge_journal_trades()` already passes `run_id` (added in previous
fix), but the `INSERT OR IGNORE` dedup still uses the old unique constraint in existing
AURUM DBs until the migration runs.

---

### 3. `tests/services/test_scribe_forge_journal.py`

**Problem**: `_create_journal()` creates a TRADES table without `run_id` and inserts
a row with positional VALUES. Both will fail or behave incorrectly after schema changes.

**Fix A**: Update TRADES schema in `_create_journal()`:
```python
conn.execute("""
    CREATE TABLE TRADES (
        id INTEGER PRIMARY KEY,
        deal_ticket INTEGER NOT NULL,
        ...
        synced INTEGER DEFAULT 0,
        run_id INTEGER DEFAULT 0,
        UNIQUE(deal_ticket, run_id)
    )
""")
```

**Fix B**: Update INSERT to include `run_id`:
```python
conn.execute("""
    INSERT INTO TRADES (id, deal_ticket, order_ticket, symbol, type, direction,
        volume, price, profit, swap, commission, magic, comment, time, time_msc, synced, run_id)
    VALUES (20, 777001, 888001, 'XAUUSD', 0, 0, 0.01, 2200.0, 1.5, 0.0, 0.0, 202401,
            'SCALP|G1', 1710000100, 1710000100000, 0, 0)
""")
```

**Fix C**: Add a second test verifying that two runs with the same deal_ticket but
different `run_id` values are both stored (not silently dropped).

---

### 4. `schemas/openapi.yaml` (line 785)

**Current**:
```sql
SELECT id, journal_source, deal_ticket, magic, profit, comment, time
FROM forge_journal_trades ORDER BY id DESC LIMIT 40
```

**Update to include `run_id`**:
```sql
SELECT id, journal_source, run_id, deal_ticket, magic, profit, comment, time
FROM forge_journal_trades ORDER BY id DESC LIMIT 40
```

---

### 5. `schemas/scribe_query_examples.json` (line 87)

Same SQL as openapi.yaml example. Update to include `run_id`.

---

### 6. `docs/SCRIBE_QUERY_EXAMPLES.md` (lines 402–406)

Update the `forge_journal_trades` example query to include `run_id` and add a
per-run P&L breakdown query:

```sql
-- By source and run
SELECT journal_source, run_id, COUNT(*) AS deals,
  SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) AS wins,
  ROUND(SUM(profit), 2) AS total_pnl
FROM forge_journal_trades
GROUP BY journal_source, run_id
ORDER BY journal_source, run_id;
```

---

### 7. `docs/FORGE_TESTER_JOURNAL_QUERIES.md`

Update trade result queries to join on `run_id` from `TESTER_RUNS` for clarity.

---

## Migration Safety Analysis

### Backward Compatibility

| Scenario | Impact |
|---|---|
| Existing live FORGE journal | Migration adds `run_id=0` to all rows; `UNIQUE(deal_ticket, 0)` = effectively `UNIQUE(deal_ticket)` → same behavior as before |
| Existing tester FORGE journal | Old rows get `run_id=0`; new rows get correct `run_id`. Cross-run dedup now works. |
| Existing AURUM `forge_journal_trades` | Old rows get `run_id=0`; re-sync from reset tester journal now stores distinct runs |
| No data in DB | Tables created fresh with correct schema; no migration needed |

### Live trading is not disrupted

For live, `run_id` is always `0`. The new constraint `UNIQUE(deal_ticket, 0)` is
logically identical to the old `UNIQUE(deal_ticket)`. No live data is affected.

### Atomicity

Both migrations (FORGE EA and SCRIBE) use SQLite's built-in `RENAME TABLE` +
`DROP TABLE` pattern which is atomic on any SQLite 3.x. If the process crashes
mid-migration, the `_TRADES_old` / `_fjt_old` shadow table remains and can be
detected on next startup to resume.

---

## Recommended Implementation Order

1. `python/scribe.py` — DDL + `_migrate()` table recreation for `forge_journal_trades`
2. `ea/FORGE.mq5` — TRADES table migration in `JournalInit()`; update `CREATE TABLE IF NOT EXISTS` for fresh DBs
3. `tests/services/test_scribe_forge_journal.py` — update `_create_journal()` + add multi-run dedup test
4. `schemas/openapi.yaml` + `schemas/scribe_query_examples.json` — update example SQL
5. `docs/SCRIBE_QUERY_EXAMPLES.md` — update query examples
6. `docs/FORGE_TESTER_JOURNAL_QUERIES.md` — update trade queries
7. `make journal-reset-tester` + `make forge-recompile` — apply to live environment
8. Run `make test-journal` to confirm tests pass

---

## Verification Queries After Fix

```bash
# Tester journal — confirm new schema
DB=$(find "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5" \
  -name "FORGE_journal_*_tester.db" 2>/dev/null | head -1)
sqlite3 "$DB" ".schema TRADES"
# Expect: UNIQUE(deal_ticket, run_id) — not deal_ticket INTEGER UNIQUE

# Confirm trades are isolated per run
sqlite3 "$DB" "SELECT run_id, COUNT(*) as deals, ROUND(SUM(profit),2) as pnl
  FROM TRADES WHERE direction IN (1,2,3)
  GROUP BY run_id;"

# AURUM — confirm new schema
sqlite3 python/data/aurum_intelligence.db ".schema forge_journal_trades"
# Expect: UNIQUE(deal_ticket, journal_source, run_id)

# AURUM — confirm tester runs are not deduplicated across runs
sqlite3 python/data/aurum_intelligence.db \
  "SELECT journal_source, run_id, COUNT(*) as deals
   FROM forge_journal_trades
   GROUP BY journal_source, run_id;"
```
