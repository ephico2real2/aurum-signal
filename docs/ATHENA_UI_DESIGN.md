# Athena UI Design & Layout Reference

> Living document. Each section covers one UI panel: what it shows, where the data comes from, and which API endpoints + DB tables feed it.

---

## Overview

Athena is a single-page React dashboard served by `python/athena_api.py` (Flask, port 7842).  
Source file: `dashboard/app.js` (single JSX bundle, no build step — loaded directly via CDN React).

The page is split into **three vertical columns**:

| Column | Width | Role |
|--------|-------|------|
| Left sidebar | ~200px | Account, Mode Control, System Health |
| Centre main | flex-grow | Tab content (Groups / Closures / Backtest / etc.) |
| Right panel | ~320px | FORGE live quote, LENS/TradingView indicators |

---

## 🔬 Backtest Panel

**Tab label:** `🔬 Backtest`  
**Activated by:** clicking the tab or navigating directly  
**Refresh cadence:** runs data fetches every 30 s while tab is active

---

### Layout (top → bottom)

```
┌─────────────────────────────────────────────────────────┐
│  Run selector (pill buttons, one per aurum_run_id)       │
│  "N run(s) stored" counter                               │
├─────────────────────────────────────────────────────────┤
│  Run metadata bar                                        │
│  symbol · forge_version · scalper_mode · sim_start       │
│  balance · first_seen_utc                                │
├────────────┬────────────┬────────────────────────────────┤
│  9-cell    │  stat grid │                                │
│  Total P&L │  Win Rate  │  Trades                        │
│  Wins      │  Losses    │  Best Win                      │
│  Worst Loss│  TAKEN     │  Open at End  │  Skipped       │
├─────────────────────────────────────────────────────────┤
│  CUMULATIVE P&L chart (SVG with axes)                    │
│    Y axis: Equity ($)   X axis: Trade #                  │
├─────────────────────────────────────────────────────────┤
│  TAKEN ENTRIES table                                     │
│    TIME | DIR | SESSION | SETUP | OUTCOME | RSI | ADX | P&L │
├─────────────────────────────────────────────────────────┤
│  GATE BREAKDOWN (SKIP) list                              │
└─────────────────────────────────────────────────────────┘
```

---

### Run Selector

**What it does:** Lists all completed/active tester runs. Clicking a pill selects the run and loads its detail.

**API:** `GET /api/backtest/runs`

**DB:** `aurum_tester.db` → `aurum_tester_runs` (joined with `forge_signals` and `forge_journal_trades` via correlated subqueries)

**Key fields returned:**

| Field | Source | Meaning |
|-------|--------|---------|
| `aurum_run_id` | `aurum_tester_runs.aurum_run_id` | Stable AURUM-level run ID (never resets) |
| `forge_version` | `aurum_tester_runs.forge_version` | EA version that generated the run |
| `sim_start` | `aurum_tester_runs.sim_start_time` | Simulation start date |
| `taken` | COUNT from `forge_signals WHERE outcome='TAKEN'` | Signals that entered the market |
| `skipped` | COUNT from `forge_signals WHERE outcome='SKIP'` | Signals blocked by gates |
| `wins` / `losses` | COUNT from `forge_journal_trades WHERE profit>0 / <0` | Closing deals |
| `total_pnl` | SUM from `forge_journal_trades WHERE profit!=0` | Run total P&L |
| `win_rate` | Computed: wins/(wins+losses)×100 | % |
| `wall_time` | `aurum_tester_runs.wall_time` | `GetTickCount64()` at run start — entropy key |

**Note on Cartesian product bug (fixed 2026-05-10):** The original query JOINed both `forge_signals` and `forge_journal_trades` on `aurum_run_id`, causing N×M row inflation. Fixed by correlated subqueries.

---

### Run Metadata Bar

Single line below the run selector. Auto-populates when a run is selected.

**API:** `GET /api/backtest/run/<aurum_run_id>` → `meta` object

**DB:** `aurum_tester_runs` — single row lookup by `aurum_run_id`

---

### Stat Grid (9 cells)

| Cell | Value source | Color |
|------|-------------|-------|
| Total P&L | `performance.total_pnl` | green/red |
| Win Rate | `performance.win_rate` % | green |
| Trades | `performance.total` | white |
| Wins | `performance.wins` | green |
| Losses | `performance.losses` | red |
| Best Win | `performance.best_win` | green |
| Worst Loss | `performance.worst_loss` | red |
| TAKEN | `signals.taken` | gold |
| Open at End | `signals.open_at_end` | amber if >0 |
| Skipped | `signals.skipped` | dim |

**API:** `GET /api/backtest/run/<aurum_run_id>` → `performance` + `signals`

**DB tables:**
- `forge_journal_trades` (WHERE `aurum_run_id=? AND profit IS NOT NULL AND profit!=0`) → wins/losses/P&L
- `forge_signals` (WHERE `aurum_run_id=?`) → taken/skipped counts
- **Open at End:** TAKEN groups with no matching closing deal by magic = still open at backtest end

```sql
-- open_at_end query
SELECT COUNT(*) FROM forge_signals s
WHERE s.aurum_run_id=? AND s.outcome='TAKEN'
  AND NOT EXISTS (
    SELECT 1 FROM forge_journal_trades t
    WHERE t.aurum_run_id = s.aurum_run_id
      AND t.magic = s.magic
      AND t.profit IS NOT NULL AND t.profit != 0
  )
```

---

### Cumulative P&L Chart

SVG chart with labeled axes.

| Axis | Label | Content |
|------|-------|---------|
| Y (left) | `Equity ($)` | Dollar value; shows max, $0 (if range crosses zero), min ticks |
| X (bottom) | `Trade #` | Sequential closing deal number (1 → N) |

**API:** `GET /api/backtest/run/<aurum_run_id>` → `pnl_curve` array

**DB:** `forge_journal_trades WHERE aurum_run_id=? AND profit IS NOT NULL AND profit!=0 ORDER BY time`

Each point: `{t: unix_timestamp, pnl: cumulative_sum_so_far}`

**Chart color:** green if `total_pnl >= 0`, red otherwise.

---

### TAKEN ENTRIES Table

Shows every signal that resulted in a market entry, enriched with trade outcome from closing deals.

**Section 508 compliance:** headers at 9px, color `#D8E4F0` on `#0F1119` background = **14.60:1 contrast ratio** (required minimum: 4.5:1).

**Columns:**

| Column | Source | Notes |
|--------|--------|-------|
| TIME (UTC) | `forge_signals.timestamp_utc` | Entry bar time |
| DIR | `forge_signals.direction` | SELL (red) / BUY (green) |
| SESSION | `forge_signals.session` | LONDON=blue, NY=green, SYDNEY=purple, ASIA=cyan, LON+NY overlap=teal |
| SETUP | `forge_signals.setup_type` | BB_BREAKOUT → BREAKOUT, BB_BOUNCE → BOUNCE |
| OUTCOME | Derived from `forge_journal_trades` | TP1/TP2/TP3/TP4 (gold badge), SL (red badge), OPEN (amber) |
| RSI | `forge_signals.rsi` | At entry bar |
| ADX | `forge_signals.adx` | At entry bar |
| P&L | Derived from `forge_journal_trades` | Per-group realized P&L (see below) |

**How OUTCOME is derived:**

Each TAKEN signal is assigned a rank (1st=G5001, 2nd=G5002…). The group magic is:
```
group_magic = magic_base + 5000 + rank
```
Trade comments like `"SCALP|BB_BREAKOUT|G5001|TP2"` are parsed to find the highest TP reached (partial close deals have `profit=0`). Final outcome is:
- `SL` — any deal with `profit < 0`
- `TPn` — highest TP from partial close comments
- `WIN` — positive profit, no TP comment
- `OPEN` — no closing deals found

**How per-group P&L is calculated:**

```python
# Group magic deals (main position legs)
group_pnl = SUM(profit WHERE magic=group_magic AND profit!=0)

# Base magic deals (L1/L2 limit entry legs close here too)
# Attributed exclusively: base_magic deal → nearest group_magic close within 10s
base_attr = SUM(base_magic deals matched to this group)

total_group_pnl = group_pnl + base_attr
```

Per-group P&Ls sum to the run total exactly.

**API:** `GET /api/backtest/run/<aurum_run_id>` → `taken` array

**DB tables:**
- `forge_signals` (WHERE `aurum_run_id=? AND outcome='TAKEN' ORDER BY time`)
- `forge_journal_trades` (WHERE `aurum_run_id=?`) — all deals, grouped by magic in Python

---

### Gate Breakdown (SKIP)

Bar list of skip reasons sorted by count descending. Shows top 15.

**API:** `GET /api/backtest/run/<aurum_run_id>` → `gates` array

**DB:**
```sql
SELECT gate_reason, COUNT(*) as cnt
FROM forge_signals
WHERE aurum_run_id=? AND outcome='SKIP' AND gate_reason IS NOT NULL
GROUP BY gate_reason ORDER BY cnt DESC LIMIT 15
```

**Common gate reasons:**

| Gate reason | Meaning |
|-------------|---------|
| `entry_quality_direction` | M5 directional bars gate failed |
| `entry_quality_body` | Candle body ratio too small |
| `entry_quality_rsi_buy_ceil` | RSI too high for buy |
| `entry_quality_rsi_sell_floor` | RSI too low for sell |
| `open_groups` | Max concurrent groups reached |
| `entry_quality_atr` | ATR below minimum threshold |
| `no_setup` | Neither BB breakout nor bounce condition met |
| `session_off` | Outside allowed trading session |
| `entry_quality_bb_contraction` | BB not expanding (no momentum) |
| `entry_quality_adx_min_sell` | ADX too low for sell |

---

## Data Flow: Backtest Panel End-to-End

```
MT5 Strategy Tester
  └─ FORGE.ex5 writes
       ├─ SIGNALS table       ─────────────────────┐
       ├─ TRADES table        ─────────────────────┤
       └─ TESTER_RUNS table   ─────────────────────┤
                                                    ↓
                             bridge.py (every 60s)
                               sync_forge_journal()
                               sync_forge_journal_trades()
                               [auto-recovery via ATTACH if gap detected]
                                                    ↓
                             aurum_tester.db
                               ├─ aurum_tester_runs   (stable run registry)
                               ├─ forge_signals       (all entry signals)
                               └─ forge_journal_trades (all closing deals)
                                                    ↓
                             athena_api.py
                               GET /api/backtest/runs        → run selector
                               GET /api/backtest/run/<id>    → full detail
                                                    ↓
                             dashboard/app.js (React)
                               btRuns state  → run selector pills
                               btDetail state → stat grid + chart + tables
                               (30s auto-refresh while Backtest tab active)
```

---

## Key DB Schema (aurum_tester.db)

### `aurum_tester_runs`
```sql
aurum_run_id   INTEGER PRIMARY KEY AUTOINCREMENT  -- stable, never resets
wall_time      INTEGER NOT NULL UNIQUE              -- GetTickCount64() entropy key
source_run_id  INTEGER                             -- run_id inside source DB (resets per agent)
journal_source TEXT                               -- always 'tester'
symbol         TEXT                               -- e.g. 'XAUUSD'
forge_version  TEXT                               -- e.g. '2.7.11'
scalper_mode   TEXT                               -- 'DUAL', 'BREAKOUT', 'BOUNCE'
balance        REAL                               -- account balance at run start
sim_start_time INTEGER                            -- Unix timestamp
magic_base     INTEGER                            -- e.g. 202401
first_seen_utc TEXT                               -- ISO timestamp of first bridge sync
```

### `forge_signals`
```sql
forge_id       INTEGER   -- source SIGNALS.id
aurum_run_id   INTEGER   -- FK → aurum_tester_runs
wall_time      INTEGER   -- same as aurum_tester_runs.wall_time (de-dup key)
time           INTEGER   -- Unix entry bar timestamp
timestamp_utc  TEXT      -- ISO UTC
symbol, direction, outcome, gate_reason
setup_type     TEXT      -- 'BB_BREAKOUT' | 'BB_BOUNCE'
session        TEXT      -- 'LONDON' | 'NEW_YORK' | 'SYDNEY' | 'ASIAN'
magic          INTEGER   -- base magic (202401) — NOT the group magic
rsi, adx, atr, price, spread
bb_upper, bb_lower, bb_mid
macd_histogram, m15_adx, lot_factor
UNIQUE(forge_id, journal_source, wall_time)
```

### `forge_journal_trades`
```sql
deal_ticket    INTEGER   -- MT5 deal ticket
aurum_run_id   INTEGER   -- FK → aurum_tester_runs
wall_time      INTEGER
magic          INTEGER   -- group magic (e.g. 207402 for G5001) or base magic
profit         REAL      -- 0 for partial TP closes, non-zero for final closes
comment        TEXT      -- 'SCALP|BB_BREAKOUT|G5001|TP2' or 'tp 4539.89' or ''
time           INTEGER   -- Unix close timestamp
UNIQUE(deal_ticket, journal_source, wall_time)
```

---

## Sync Reliability

The bridge runs a two-layer recovery every 60s:

1. **wall_time change detection** (`scribe.py`): When `TESTER_RUNS` gets a new `wall_time` for a `run_id`, resets `synced=0` for ALL signals so the full run re-syncs under the new `aurum_run_id`.

2. **ATTACH-based gap recovery** (`bridge.py`): ATTACHes `aurum_tester.db` to the source and resets `synced=0` only for source rows marked `synced=1` that are missing from the destination. Self-heals within one 60s cycle.

See `docs/DATABASE_ARCHITECTURE.md` for the full multi-agent isolation design.
