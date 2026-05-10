# Signal System — Database Architecture

**Last updated:** 2026-05-10

---

## Overview

The system uses four SQLite databases split across two layers:

- **Source layer** — written directly by FORGE EA (MQL5); raw tick-level data
- **AURUM layer** — written by the Python stack (BRIDGE); structured analytics data read by ATHENA

---

## Source Databases (written by FORGE EA)

| DB | Written by | Location | Contains |
|----|-----------|----------|---------|
| `FORGE_journal_XAUUSD.db` | Live EA | MT5 Terminal Common Files | Raw SIGNALS, TRADES for live trading |
| `FORGE_journal_XAUUSD_tester.db` | Tester EA | MT5 Tester Agent MQL5/Files | Raw SIGNALS, TRADES, TESTER_RUNS for backtests |

**Key tables in source DBs:**

| Table | Purpose |
|-------|---------|
| `SIGNALS` | Every setup evaluated — TAKEN and SKIP — with RSI, ADX, gate_reason, run_id |
| `TRADES` | Every MT5 deal (open + close) with profit, magic, comment |
| `TESTER_RUNS` | One row per tester run: `wall_time` (entropy), `sim_start_time`, `forge_version`, `magic_base` |

**Important:** The tester journal DB may be wiped when the MT5 agent restarts. `run_id` inside the source DB resets to 1 on each wipe. This is handled at the AURUM layer via `wall_time` + `aurum_run_id` (see below).

---

## AURUM Databases (used by Python stack / ATHENA)

| DB | Fed from | Used for |
|----|----------|---------|
| `python/data/aurum_intelligence.db` | Live journal + live MT5 positions | ATHENA dashboard, live analytics, performance |
| `python/data/aurum_tester.db` | Tester journal(s) | Backtest analytics, run comparison, ATHENA Backtest tab |

**BRIDGE routing:** BRIDGE detects `strategy_tester=true` in `market_data.json` and routes all journal syncs to `aurum_tester.db` via `_active_scribe(is_tester)`. Live data always goes to `aurum_intelligence.db`.

---

## BRIDGE Routing — How Each Journal Reaches the Right AURUM DB

BRIDGE detects whether a journal path is tester by checking if `"_tester"` is in the filename.
All routing is done via `_active_scribe(is_tester)` which returns either `self.scribe` (live) or `self.tester_scribe` (tester).

```
EA writes                   BRIDGE detects          AURUM destination
─────────────────────────   ─────────────────────   ──────────────────────────────
Common/Files/               "_tester" NOT in name   aurum_intelligence.db
  FORGE_journal_XAUUSD.db   → is_tester = False     (live analytics, Athena)
                            → scribe

Agent-3000/MQL5/Files/      "_tester" in name       aurum_tester.db
  FORGE_journal_             → is_tester = True      (backtest analytics, Backtest tab)
  XAUUSD_tester.db          → tester_scribe

Agent-3001/MQL5/Files/      "_tester" in name       aurum_tester.db
  FORGE_journal_             → is_tester = True      (same tester DB, multiple agents)
  XAUUSD_tester.db          → tester_scribe
```

**Enforcement via `BRIDGE_SYNC_TESTER_JOURNAL=1`** in `.env` — tester syncs are opt-in so accidental backtest runs don't fill `aurum_tester.db` unexpectedly in live mode.

**Contamination fix (2026-05-10):** 45,996 tester signals that were previously written to `aurum_intelligence.db` (before isolation was complete) were purged. All `journal_source='tester'` rows deleted. `aurum_intelligence.db` now contains only `journal_source='live'` rows.

### Sync Performance (post-optimisation)

| Metric | Before | After |
|--------|--------|-------|
| Batch size | 500 rows | 5,000 rows (tester) / 500 (live) |
| De-dup method | 1 SELECT per row (N queries) | 1 bulk SELECT → Python set lookup O(1) |
| INSERT method | 1 INSERT per row | executemany (1 round-trip) |
| Path discovery | rglob on every 60s cycle | glob("Agent-*/MQL5/Files") + 300s cache |
| Throughput | ~1,000 rows/cycle | ~10,000 rows/cycle (10×) |

---

## Run Identity in aurum_tester.db

The tester source DB (`FORGE_journal_XAUUSD_tester.db`) can be wiped between sessions, causing `run_id` and `deal_ticket` to reset to 1. To prevent data loss and de-dup false positives in `aurum_tester.db`, the system uses **wall_time entropy**:

```
TESTER_RUNS.wall_time = GetTickCount64() at run start
                      = real-clock milliseconds, always unique per actual run
```

### aurum_tester_runs — the stable run registry

```sql
CREATE TABLE aurum_tester_runs (
    aurum_run_id   INTEGER PRIMARY KEY AUTOINCREMENT,  -- never resets
    wall_time      INTEGER NOT NULL UNIQUE,             -- entropy from EA
    source_run_id  INTEGER DEFAULT 0,                  -- for cross-ref only (can repeat)
    journal_source TEXT DEFAULT 'tester',
    symbol         TEXT,
    forge_version  TEXT,
    scalper_mode   TEXT,
    balance        REAL,
    sim_start_time INTEGER,
    magic_base     INTEGER,
    first_seen_utc TEXT NOT NULL
);
```

**Rule:** Always use `aurum_run_id` for filtering and grouping in AURUM queries. `run_id` in `forge_signals`/`forge_journal_trades` is kept for source-journal cross-reference only — it is unreliable across source DB resets.

### How run_id vs aurum_run_id differ

```
Source journal DB (can be wiped):          aurum_tester.db (persists forever):
  TESTER_RUNS                                aurum_tester_runs
  ├── id=1, wall_time=447473969  ──────────► ├── aurum_run_id=1, wall_time=447473969 (Run 1)
  ├── id=2, wall_time=447480001  ──────────► ├── aurum_run_id=2, wall_time=447480001 (Run 2)
  [DB wiped, resets]
  ├── id=1, wall_time=447511234  ──────────► ├── aurum_run_id=3, wall_time=447511234 (Run 3 ✓)
  └── id=2, wall_time=447520000  ──────────► └── aurum_run_id=4, wall_time=447520000 (Run 4 ✓)
```

### UNIQUE constraints (prevent silent data loss)

| Table | Old constraint | New constraint |
|-------|---------------|---------------|
| `forge_journal_trades` | `UNIQUE(deal_ticket, journal_source, run_id)` | `UNIQUE(deal_ticket, journal_source, wall_time)` |
| `forge_signals` de-dup | `forge_id + time + symbol + journal_source` | `forge_id + time + symbol + journal_source + wall_time` |

---

## MT5 Tester Agents

Two tester agents run in parallel. Both write to separate source DBs but feed into the same `aurum_tester.db`:

| Agent | Source DB | Size (approx) |
|-------|-----------|---------------|
| Agent-127.0.0.1-3000 | `FORGE_journal_XAUUSD_tester.db` | ~16M (primary) |
| Agent-127.0.0.1-3001 | `FORGE_journal_XAUUSD_tester.db` | ~3.5M (secondary) |

---

## ATHENA API Endpoints

### Live (aurum_intelligence.db)
| Endpoint | Description |
|----------|-------------|
| `GET /api/performance` | Live trade performance (rolling days) |
| `GET /api/pnl_curve` | Cumulative P&L curve |
| `GET /api/signals` | Recent live signals |

### Backtest (aurum_tester.db)
| Endpoint | Description |
|----------|-------------|
| `GET /api/backtest/runs` | All registered runs with summary stats |
| `GET /api/backtest/run/<aurum_run_id>` | Full run detail: performance, gates, TAKEN entries, P&L curve |

---

## Make Targets

| Target | Action |
|--------|--------|
| `make tester-db-reset` | Wipes `aurum_tester.db` (source journal DBs untouched) |
| `make journal-reset-run RUN=N` | Purge one run_id from source journal (surgical) |

---

## Useful Queries

### All runs with P&L (AURUM)
```sql
SELECT r.aurum_run_id, r.forge_version, r.scalper_mode,
       COUNT(CASE WHEN t.profit>0 THEN 1 END) as wins,
       COUNT(CASE WHEN t.profit<0 THEN 1 END) as losses,
       ROUND(SUM(CASE WHEN t.profit!=0 THEN t.profit END),2) as pnl
FROM aurum_tester_runs r
LEFT JOIN forge_journal_trades t ON t.aurum_run_id = r.aurum_run_id
GROUP BY r.aurum_run_id ORDER BY r.aurum_run_id DESC;
```

### Gate breakdown for a specific run
```sql
SELECT gate_reason, COUNT(*) as cnt
FROM forge_signals
WHERE aurum_run_id = <N> AND outcome = 'SKIP'
GROUP BY gate_reason ORDER BY cnt DESC;
```

### TAKEN entries for a specific run
```sql
SELECT timestamp_utc, direction, ROUND(rsi,1) as rsi, ROUND(adx,1) as adx, setup_type
FROM forge_signals
WHERE aurum_run_id = <N> AND outcome = 'TAKEN'
ORDER BY time;
```
