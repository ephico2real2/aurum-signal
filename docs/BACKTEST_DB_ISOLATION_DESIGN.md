# Backtest DB Isolation — Design Specification

**Date:** 2026-05-09  
**Status:** PROPOSED — requires implementation  
**Problem:** MT5 Strategy Tester runs write their synced journal data (SIGNALS, TRADES) into the main `aurum_intelligence.db` (SCRIBE), mixing tester/backtest data with live/demo trading data. This corrupts performance metrics, session P&L, win-rate statistics, and any analytics that span the full history.

---

## Problem Statement

When BRIDGE detects a Strategy Tester run (`strategy_tester=true` in `market_data.json`), it calls `scribe.sync_forge_journal()` which inserts rows tagged `source='tester'` into **the same tables** as live data (`forge_signals`, `forge_journal_trades`). The `trade_closures` table receives tester-synced closes. The `trade_positions` table also receives tester positions.

**Result:** Every tester backtest run pollutes:
- `trade_closures` → session P&L, performance metrics, scale factor all read tester P&L
- `forge_signals` → AURUM context windows include tester signal history
- Performance panel shows combined live+tester stats
- Scale factor may scale up/down based on tester wins/losses, affecting live sizing

---

## Design Options Considered

### Option A — Separate SCRIBE instance (`tester_scribe`)
Create a second `Scribe` instance pointing to `python/data/aurum_tester.db`. All tester writes go to the tester DB; live writes go to the main DB.

**Pros:** Clean separation, zero risk of contamination, existing code unchanged for live path.  
**Cons:** BRIDGE must instantiate two Scribe objects; every write call must route to the right one based on `strategy_tester` flag.

### Option B — `source` column gating on all queries
Keep one DB. Add `WHERE source NOT IN ('tester')` to every query that should exclude backtest data.

**Pros:** Single DB, no code duplication.  
**Cons:** Every performance query must be updated (large blast radius); easy to miss one → silent data contamination resumes. Already partially in place but incomplete.

### Option C — Separate DB file, switchable Scribe (recommended)
Scribe accepts a `db_path` parameter at init time. BRIDGE creates two Scribe instances:
- `self.scribe` → `aurum_intelligence.db` (live/demo)  
- `self.tester_scribe` → `aurum_tester.db` (backtest)

All writes that originate from a tester-detected context route to `self.tester_scribe`. All reads for live analytics use `self.scribe`. Athena API exposes a separate `/backtest/*` namespace that reads from `aurum_tester.db`.

**Pros:** Zero contamination by design. No query-level guards needed. Backtest DB can be wiped between runs without affecting live data.  
**Cons:** Requires routing logic in BRIDGE for tester detection.

---

## Recommended Approach: Option C (Separate Tester DB)

### Architecture

```
BRIDGE (bridge.py)
├── self.scribe       → aurum_intelligence.db   ← LIVE / DEMO
└── self.tester_scribe → aurum_tester.db         ← BACKTEST ONLY

ATHENA API (athena_api.py)
├── /api/live          → reads from scribe (live DB)
├── /api/performance   → reads from scribe (live DB)
├── /api/backtest/live → reads from tester_scribe
└── /api/backtest/performance → reads from tester_scribe

DASHBOARD (app.js)
├── Default view       → live data (aurum_intelligence.db)
└── /backtest tab      → tester data (aurum_tester.db via /api/backtest/*)
```

### Tester Detection

BRIDGE already has:
```python
strategy_tester = bool(status.get("strategy_tester") or (mt5 or {}).get("strategy_tester"))
```

Use this flag to route all SCRIBE writes:
```python
active_scribe = self.tester_scribe if strategy_tester else self.scribe
```

### What goes to tester DB
- `sync_forge_journal()` (SIGNALS rows)
- `sync_forge_journal_trades()` (TRADES rows)
- `log_trade_closure()` for tester-detected closes
- `log_trade_position()` for tester-detected positions
- `log_trade_group()` for tester groups
- All regime snapshots generated during tester run

### What stays in live DB
- Everything above when `strategy_tester=False`
- Component heartbeats (always live)
- AURUM conversations (always live)
- Trading sessions (always live)
- Sentinel events (always live)

### Tester DB lifecycle
- `aurum_tester.db` is created on first tester run (same schema as `aurum_intelligence.db`)
- Reset between runs via `make tester-db-reset` → `rm aurum_tester.db`
- Athena `/backtest/*` endpoints read from the tester DB

---

## API Design

### New endpoints (prefix `/api/backtest/`)

| Endpoint | Description |
|----------|-------------|
| `GET /api/backtest/live` | Same structure as `/api/live` but MT5 + tester_scribe data |
| `GET /api/backtest/performance` | Performance from `aurum_tester.db trade_closures` |
| `GET /api/backtest/pnl_curve` | P&L curve from tester DB |
| `GET /api/backtest/signals` | SIGNALS from tester DB |
| `GET /api/backtest/closures` | trade_closures from tester DB |
| `GET /api/backtest/runs` | TESTER_RUNS table (run_id, forge_version, period, P&L) |

### New flag in `/api/live`

```json
"tester_db_available": true,
"tester_db_path": "python/data/aurum_tester.db"
```

---

## Dashboard Design

### `/backtest` tab in ATHENA

Add a **BACKTEST** tab to the main navigation (alongside Groups, Closures, Activity, Signals, Performance).

When active:
- Fetches from `/api/backtest/*` endpoints
- Shows TESTER_RUNS table (run_id, forge_version, scalper_mode, period, P&L, WR)
- Shows performance panel reading from tester DB
- Shows P&L sparkline from tester DB
- Shows SIGNALS table with gate_reason breakdown
- Shows OsMA gate diagnostics (macd_histogram, m15_adx, lot_factor columns)
- Header banner: `🔬 BACKTEST VIEW — aurum_tester.db`

TradingView panel remains unchanged (live feed, not tester-dependent).

---

## Implementation Plan

### Phase 1 — Separate tester DB (core isolation)
1. `scribe.py`: Add `db_path` param to `Scribe.__init__`; `get_scribe()` returns live Scribe; add `get_tester_scribe()` returning Scribe pointing at `aurum_tester.db`
2. `bridge.py`: Initialize `self.tester_scribe = get_tester_scribe()` at startup; create routing helper `_active_scribe(is_tester: bool)` 
3. `bridge.py`: All `sync_forge_journal*` calls use `self.tester_scribe` when tester detected
4. `bridge.py`: All tracker close/position log calls use `_active_scribe(strategy_tester)`

### Phase 2 — Backtest API endpoints
5. `athena_api.py`: Add `TESTER_SCRIBE_DB` path constant; add `/api/backtest/*` routes
6. `athena_api.py`: `_build_scalper_gates()` and autoscalper conditions can be tester-aware

### Phase 3 — Dashboard backtest tab
7. `dashboard/app.js`: Add BACKTEST tab; fetch from `/api/backtest/*`; show TESTER_RUNS table; add `🔬 BACKTEST VIEW` header

### Phase 4 — Makefile integration
8. `Makefile`: Add `tester-db-reset` target (wipes `aurum_tester.db`)
9. `Makefile`: Add `tester-db-stats` target (quick summary of latest tester run)

---

## Migration

**Existing contaminated data in `aurum_intelligence.db`:**
- Rows with `source='tester'` in `forge_signals` / `forge_journal_trades` should be purged
- `trade_closures` rows from tester periods (identifiable by tester sim timestamps like 2026-04-29 to 2026-05-04) should be purged or tagged
- One-time cleanup SQL provided in implementation

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| BRIDGE fails to detect tester mode → live data contaminated | Keep `strategy_tester` detection in both `status.json` and `market_data.json`; log explicitly at each routing decision |
| Tester DB grows unbounded | `make tester-db-reset` before each run; add size warning to Athena if >100MB |
| Backtest API reads stale tester DB | Tester DB is read-only from Athena; writes only from BRIDGE during active tester runs |
| Schema divergence between live and tester DBs | Both use same `_init_db()` schema; migrations run on both at startup |

---

*Design: 2026-05-09 | Status: PROPOSED | Next: Phase 1 implementation sprint*
