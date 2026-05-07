# FORGE Tester Journal DB — Design Findings & Solution Prompt

## Summary

The Strategy Tester journal database (`FORGE_journal_XAUUSD_tester.db`) has several
design defects that make it impossible to isolate, compare, or cleanly analyse individual
backtest runs. This document describes every confirmed defect, its root cause, and the
complete set of changes required to fix the design.

---

## Status: FIXED (2026-05-07)

All changes have been implemented and verified. See `docs/FORGE_TESTER_JOURNAL_QUERIES.md`
for the operational query reference. The section below is preserved as a record of what
was broken and why.

---

## Confirmed Problems

### 1. `start_time` in TESTER_RUNS captures simulated time, not wall clock

**Root cause**: `JournalInit()` recorded `start_time = TimeGMT()`. Inside the Strategy
Tester `TimeGMT()` returns the *simulated* backtest clock — the start of the backtest
date range, not the real wall-clock time of the run.

**Effect**: All runs over the same backtest period share identical `start_time` values.
The old DB showed:
```
id=1 | 2026-04-14 00:00:00 | DUAL | warmup=2 | balance=10000
id=2 | 2026-04-14 00:00:00 | DUAL | warmup=2 | balance=10000
id=3 | 2026-04-14 00:00:00 | DUAL | warmup=2 | balance=10000
```
Three runs were indistinguishable. After the fix, each run has a unique `wall_time`
(`GetTickCount64()`) and the old `start_time` is preserved as `sim_start_time`.

**Verified**: First clean run after fix showed `wall_time=224891143` (unique real clock).

---

### 2. No `run_id` column in SIGNALS or TRADES

**Root cause**: `SIGNALS` and `TRADES` have no foreign-key back to `TESTER_RUNS`.

**Effect**: Signals from every run are mixed into the same table. The only available
proxy is `time >= start_time` — which collapses to "all signals since the backtest
start date" because all runs share the same `start_time`. Any query that attempts to
isolate "this run's signals" silently returns the full history:

```sql
-- Intended: signals from the latest run only
-- Actual: all 22,107 signals since 2026-04-14
SELECT * FROM SIGNALS WHERE time >= (SELECT start_time FROM TESTER_RUNS WHERE id=3);
```

The result: TAKEN counts, skip-reason breakdowns, and win-rate statistics are
contaminated by every previous run.

---

### 3. `deal_ticket INTEGER UNIQUE` causes silent data loss across runs

**Root cause**: The Strategy Tester assigns deal tickets sequentially starting at 1 for
each new backtest run. With `deal_ticket UNIQUE`, `JournalImportTrades()` uses
`INSERT OR IGNORE`, which silently discards every deal from run 2 onward whose ticket
number matches a deal already recorded from run 1.

**Effect**: TRADES data from all runs except the first is silently incomplete or missing.

---

### 4. `STATS_CACHE` aggregates contaminate every new run

**Root cause**: `JournalComputeStats()` deletes `gate_%` and `hour_%` rows and
recomputes from the entire SIGNALS/TRADES history, not just the current run.

**Effect**: Stats displayed in Experts log represent a blend of all historical runs.
After 3 runs of the same config, "win rate by hour" appears 3× more confident than
it actually is for the latest run alone.

---

### 5. `g_journal_db != INVALID_HANDLE` early exit can skip TESTER_RUNS insert

**Root cause**: `JournalInit()` returns early if `g_journal_db != INVALID_HANDLE`.
In certain agent configurations the MT5 Strategy Tester reuses the EA instance
across consecutive runs in the same agent session. If `JournalClose()` in `OnDeinit`
is not fully flushed before the next `OnInit()` fires, `g_journal_db` may already
be set when `JournalInit()` is called for the new run.

**Effect**: A new TESTER_RUNS row is never inserted, but signals keep being written
to the open handle — making the DB appear to have only N−1 run records while actually
containing N runs of signal data (observed in the latest backtest: 3 TESTER_RUNS rows
but signal growth from ~21,909 to ~22,107).

---

### 6. Magic number reuse across runs (secondary issue)

**Root cause**: `g_scalper_group_counter` is initialised to `5000` at EA startup.
Every backtest run opens groups starting at `MagicNumber + 5001`. The same magic
numbers repeat in every run.

**Effect**: When `JournalImportTrades` tries to filter deals by magic range, a deal
from group G5001 in run 1 is indistinguishable from G5001 in run 2. Combined with
the `deal_ticket UNIQUE` conflict, trade attribution is unreliable.

---

## Proposed Solution

### Approach: `run_id` isolation + Makefile reset target

The recommended fix is a two-layer approach:

1. **Structural**: Add `run_id` to SIGNALS and TRADES, use `GetTickCount64()` (real
   wall-clock ms since boot) as the unique run identifier stored in TESTER_RUNS.
2. **Operational**: Add a `make journal-reset-tester` Makefile target that purges the
   tester DB before a clean run.

---

### Change 1: `TESTER_RUNS` — add `wall_time` and `sim_start_time`

Replace `start_time` with two columns:
- `wall_time INTEGER` — `GetTickCount64()` at OnInit (real clock, unique per run)
- `sim_start_time INTEGER` — `TimeGMT()` at OnInit (backtest period start, for reference)

The existing `start_time` column maps to the new `sim_start_time`.

```sql
CREATE TABLE IF NOT EXISTS TESTER_RUNS (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    wall_time       INTEGER NOT NULL,   -- GetTickCount64() = real wall clock ms
    sim_start_time  INTEGER,            -- TimeGMT() = simulated backtest start
    symbol          TEXT,
    balance         REAL,
    forge_version   TEXT,
    scalper_mode    TEXT,
    warmup_m5_bars  INTEGER,
    warmup_seconds  INTEGER,
    magic_base      INTEGER             -- MagicNumber used for this run
);
```

---

### Change 2: `SIGNALS` and `TRADES` — add `run_id`

Add `run_id INTEGER DEFAULT 0` to both tables. Migration via `ALTER TABLE ADD COLUMN`
works on existing DBs without data loss.

New global in FORGE.mq5:
```cpp
int g_tester_run_id = 0;  // set in JournalInit; 0 = live/unknown
```

After the TESTER_RUNS INSERT, read back the newly created id:
```cpp
int stmt = DatabasePrepare(g_journal_db, "SELECT last_insert_rowid()");
if(DatabaseRead(stmt)) {
    DatabaseColumnInteger(stmt, 0, g_tester_run_id);
}
DatabaseFinalize(stmt);
```

Pass `run_id` into every `JournalRecordSignal` INSERT and every `JournalImportTrades`
INSERT.

---

### Change 3: Fix `deal_ticket UNIQUE` collision

Remove the hard `UNIQUE` constraint from `deal_ticket` and enforce uniqueness on the
composite key `(deal_ticket, run_id)` instead. SQLite cannot alter existing constraints,
so the TRADES table must be recreated during the migration.

Migration in `JournalInit()`:
```sql
-- Detect old schema (unique on deal_ticket alone)
-- If old, rename table, recreate with new schema, copy data, drop old
```

New schema:
```sql
CREATE TABLE IF NOT EXISTS TRADES (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER DEFAULT 0,
    deal_ticket  INTEGER NOT NULL,
    ...
    UNIQUE(deal_ticket, run_id)
);
```

---

### Change 4: `STATS_CACHE` — scope to current `run_id`

`JournalComputeStats()` should filter SIGNALS and TRADES to `WHERE run_id = g_tester_run_id`
(in tester mode) so stats reflect the current run only.

---

### Change 5: `JournalInit()` — force re-init guard in tester

The early exit guard `if(g_journal_db != INVALID_HANDLE) return true;` is correct for
live trading but unsafe in the tester. Add an explicit close + reopen path for tester:

```cpp
bool JournalInit() {
   if(!g_sc.journal_enabled) return true;
   bool in_tester = (MQLInfoInteger(MQL_TESTER) != 0);
   // In tester: always close previous handle and reopen fresh
   if(in_tester && g_journal_db != INVALID_HANDLE) {
      DatabaseClose(g_journal_db);
      g_journal_db = INVALID_HANDLE;
   }
   if(!in_tester && g_journal_db != INVALID_HANDLE) return true;
   // ... rest of init
```

---

### Change 6: Makefile `journal-reset-tester` target

```makefile
journal-reset-tester:
	@find "$(HOME)/Library/Application Support/net.metaquotes.wine.metatrader5" \
		-name "FORGE_journal_*_tester.db" -delete 2>/dev/null
```

The actual path is `$HOME/Library/Application Support/net.metaquotes.wine.metatrader5`
(macOS Wine). The target also prints next-step instructions including the verification
queries to run after the backtest.

---

### Change 7: SCRIBE `sync_forge_journal` — propagate `run_id`

Update `sync_forge_journal` and `sync_forge_journal_trades` in `python/scribe.py` to:
- Read `run_id` from each SIGNALS/TRADES row
- Pass it into the `forge_signals` and `forge_journal_trades` INSERT in AURUM
- Add `run_id INTEGER DEFAULT 0` to both AURUM tables via migration

Deduplication key becomes `(forge_id, run_id, journal_source)` instead of
`(forge_id, time, symbol, journal_source)`.

---

## Summary of Files to Change

| File | Change |
|------|--------|
| `ea/FORGE.mq5` | Add `g_tester_run_id` global; fix `JournalInit` reopen path; update TESTER_RUNS schema; migrate SIGNALS/TRADES with `run_id`; fix TRADES composite unique; pass `run_id` in all INSERTs; scope STATS_CACHE to run |
| `python/scribe.py` | Read/pass `run_id` in both sync functions; update AURUM table migrations |
| `Makefile` | Add `journal-reset-tester` target |

---

## Completed Migration Steps

1. ✅ `make journal-reset-tester` — deleted contaminated DB
2. ✅ EA code changes applied and compiled (`make forge-recompile`)
3. ✅ Clean backtest run — new DB created with correct schema
4. ✅ Verified: `TESTER_RUNS.wall_time=224891143` (unique); `SIGNALS.run_id=1` on all rows
5. ✅ SCRIBE `sync_forge_journal` updated to propagate `run_id` to AURUM

See `docs/FORGE_TESTER_JOURNAL_QUERIES.md` for all operational queries.

---

## Pending Improvement

Increase `gold_native_max_sell_legs` from 2 → 3 in
`config/scalper_config.defaults.json` and run `make forge-recompile` to allow
more staged SELL legs per group on XAUUSD. Do this after confirming TAKEN entries
are recording cleanly in a full backtest.
