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

## MT5 Tester Agents — Multi-Run Isolation

MT5 Strategy Tester assigns agents in round-robin. Each run gets its own agent directory and source DB. The bridge monitors all agents in parallel every 60s via `glob("Agent-*/MQL5/Files")`.

### Agent assignment per run

```
Run X → MT5 assigns Agent-3000
         └─ FORGE_journal_XAUUSD_tester.db (wall_time=T1)
              └─ Bridge syncs → aurum_run_id=X in aurum_tester.db

Run Y → MT5 assigns Agent-3001
         └─ FORGE_journal_XAUUSD_tester.db (wall_time=T2)
              └─ Bridge syncs → aurum_run_id=Y in aurum_tester.db

Both synced simultaneously — Agent-3000 data for Run X is
preserved and queryable while Run Y is actively running on Agent-3001.
```

### Agent reuse (same agent, new wall_time)

When MT5 reuses an agent (e.g., Run Z starts on Agent-3000 after Run X finishes):

- **MT5 does NOT clear `SIGNALS` between runs** — old Run X rows persist with `synced=1`
- Only the new Run Z rows have `synced=0`; `TESTER_RUNS` gets a new `wall_time`
- Without mitigation the bridge would only sync the delta rows (e.g., 3,275 of 64,102)

**How the bridge handles this (auto-recovery, no manual action needed):**

1. **wall_time change detection** (`scribe.py`): When `TESTER_RUNS` gets a new `wall_time` for a known `run_id`, scribe resets `synced=0` for ALL signals in that `run_id`. The full run re-syncs under the new `aurum_run_id`.

2. **ATTACH-based gap recovery** (`bridge.py`): Every 60s cycle, the bridge ATTACHes `aurum_tester.db` to the source and resets `synced=0` for any source rows marked `synced=1` that are missing from the destination. Fires within one cycle of a gap being detected.

| Agent | Source DB | Notes |
|-------|-----------|-------|
| Agent-127.0.0.1-3000 | `FORGE_journal_XAUUSD_tester.db` | Primary agent (first run) |
| Agent-127.0.0.1-3001 | `FORGE_journal_XAUUSD_tester.db` | Secondary agent (second run) |
| Agent-127.0.0.1-300N | `FORGE_journal_XAUUSD_tester.db` | Additional agents auto-discovered |

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

---

## Gate Legend — `forge_signals.gate_reason` Field Reference

The `gate_reason` column in `forge_signals` uses internal FORGE codes. The full human-readable mapping is maintained in **`config/gate_legend.json`** and served via `GET /api/gate_legend`.

> **How to update:** Edit `config/gate_legend.json` only. The Athena UI and this table should stay in sync — see `docs/ATHENA_UI_DESIGN.md` for the full legend table and the system design.

### `gate_reason` Quick Reference

| gate_reason | Category | What it means (plain English) |
|-------------|----------|-------------------------------|
| `entry_quality_direction` | Entry Quality | Not enough M5 bars moving in trade direction (need 2+ aligned bars) |
| `entry_quality_body` | Entry Quality | Candle body too small — indecision candle, not a clean directional move |
| `entry_quality_rsi_buy_ceil` | Entry Quality | RSI above 70 — overbought; buying here risks entering at the top |
| `entry_quality_rsi_sell_floor` | Entry Quality | RSI below 30 — oversold (Cardwell exhaustion); selling here risks reversal |
| `entry_quality_adx_min_sell` | Entry Quality | ADX too low for a breakout sell; not enough trending momentum |
| `entry_quality_adx_min_buy` | Entry Quality | ADX too low for a breakout buy; market too range-bound |
| `entry_quality_atr` | Entry Quality | ATR (volatility) too low — spread eats too much of the potential move |
| `entry_quality_bb_contraction` | Entry Quality | Bollinger Bands squeezing inward — no momentum building for a breakout |
| `entry_quality_bb_expansion` | Entry Quality | BB not expanding enough from recent low — breakout confirmation missing |
| `entry_quality_m30_not_bearish` | Entry Quality | M30 timeframe not confirming bearish direction required for sell |
| `entry_quality_macd_q0` | Indicators | MACD in Q0 (positive, rising) — blocks sells; momentum is bullish |
| `entry_quality_macd_q1` | Indicators | MACD in Q1 (positive, falling) — blocks buys; momentum fading |
| `entry_quality_macd_q2` | Indicators | MACD in Q2 (negative, falling) — blocks buys; momentum clearly bearish |
| `entry_quality_macd_q3` | Indicators | MACD in Q3 (negative, rising) — market transitioning; blocks both directions |
| `entry_quality_h4_rsi_sell_blocked` | Indicators | H4 RSI already oversold — selling risks piling into exhausted H4 move |
| `entry_quality_h4_rsi_buy_blocked` | Indicators | H4 RSI already overbought — buying risks chasing extended H4 move |
| `entry_quality_h4_adx_sell_blocked` | Indicators | H4 ADX below minimum — no strong H4 trend to support M5 sell |
| `entry_quality_session_sell_cutoff` | Session / Time | Sells blocked after cutoff hour (NY 17:00, London 00:00 UTC) |
| `open_groups` | Position Limits | Max concurrent trade groups reached (default 2) |
| `max_open_same_direction` | Position Limits | Max concurrent SELLs (or BUYs) reached — prevents directional over-exposure |
| `no_setup` | Market Conditions | Neither BB Breakout nor BB Bounce conditions met on this bar |
| `session_off` | Session / Time | Outside allowed trading sessions (London / New York) |
| `spread_too_wide` | Market Conditions | Bid-ask spread exceeds maximum (default 30 pts XAUUSD) |
| `min_rr` | Risk Management | Risk:Reward ratio below minimum (default 1.5×) — TP1 too close to entry vs SL |
| `min_entry_atr` | Risk Management | ATR at entry bar specifically below minimum |
| `high_vol_trend_guard` | Risk Management | Explosive ADX AND H1/H4 trend not both aligned — avoids spike reversal |
| `adx_hysteresis` | Risk Management | ADX recently exceeded trend-enter level; waiting to cool below trend-exit |
| `sell_loss_grace` | Risk Management | Sell hit SL recently — 90s cooldown before new sells (no revenge trading) |
| `loss_cooldown` | Risk Management | Any trade hit SL — brief cooldown before any new entry |
| `direction_cooldown` | Risk Management | Recent entry in same direction — short cooldown to avoid rapid stacking |
| `warmup_tester_m5_rollovers` | System | Backtest start: M5 indicator buffers not yet filled; signals discarded |
| `news_filter_blocked` | Risk Management | High-impact news blackout window active (e.g. NFP ±30/60 min) |
| `news_filter_tighten` | Risk Management | Near medium-impact news — tightened RSI criteria applied, signal failed |
| `dd_equity_close_all` | Risk Management | Equity drawdown breaker triggered — new entries suspended |
