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

> **Full legend with plain-English explanations:** see [`config/gate_legend.json`](../config/gate_legend.json) and the Gate Legend section below.

---

## Gate Legend System

### Purpose

Gate reason codes are internal FORGE identifiers (e.g. `entry_quality_direction`). Without context they are opaque to anyone not reading the EA source. The gate legend system adds human-readable explanations everywhere they appear — without duplicating the text across files.

### Single Source of Truth

**`config/gate_legend.json`** — the only file to edit when adding or changing gate explanations.

Each entry has three fields:

| Field | Purpose |
|-------|---------|
| `label` | Short title (one line, ≤60 chars) shown as line 2 in the UI (green, `↳` prefix) |
| `explanation` | Full plain-English sentence(s) shown as line 3 in the UI |
| `category` | Grouping: Entry Quality / Indicators / Position Limits / Session / Risk Management / System |

Example entry:
```json
"entry_quality_direction": {
  "label": "Direction — not enough aligned bars",
  "explanation": "Too few M5 candles are moving in the trade direction. FORGE requires at least 2 consecutive bars confirming the direction before entry.",
  "category": "Entry Quality"
}
```

### How It Flows

```
config/gate_legend.json          ← edit here to add/change explanations
       │
       ├─ GET /api/gate_legend   ← athena_api.py serves it (cached in-process)
       │        │
       │        └─ dashboard/app.js
       │               gateLegend state — fetched once on first Backtest tab open
       │               Gate Breakdown rows:
       │                 Line 1: gate_reason code          + skip count (amber)
       │                 Line 2: legend[code].label        (green, ↳ prefix)
       │                 Line 3: legend[code].explanation  (dim, sans-serif)
       │
       └─ docs/ATHENA_UI_DESIGN.md   ← full legend table below (keep in sync)
          docs/DATABASE_ARCHITECTURE.md  ← same table
```

### How to Add a New Gate

1. In `config/gate_legend.json`, add a new key matching the exact `gate_reason` string FORGE writes.
2. Fill in `label`, `explanation`, `category`.
3. Restart Athena (or the in-process cache clears on next deploy) — the UI picks it up automatically.
4. Update the legend tables in `docs/ATHENA_UI_DESIGN.md` and `docs/DATABASE_ARCHITECTURE.md`.
5. No code changes required.

### Complete Gate Legend Table

| gate_reason | Label | Category | Plain-English Explanation |
|-------------|-------|----------|--------------------------|
| `entry_quality_direction` | Direction — not enough aligned bars | Entry Quality | Too few M5 candles moving in trade direction. Requires 2+ consecutive bars confirming direction. |
| `entry_quality_body` | Candle body too small | Entry Quality | Entry candle's body (open→close) is too small vs full range (high→low). Means indecision, not a clean directional move. |
| `entry_quality_rsi_buy_ceil` | RSI too high for a buy | Entry Quality | RSI above buy ceiling (default 70). Buying when overbought risks entering at the top of a move. |
| `entry_quality_rsi_sell_floor` | RSI too low for a sell | Entry Quality | RSI below sell floor (default 30). Selling when deeply oversold risks entering exhaustion (Cardwell reversal zone). |
| `entry_quality_adx_min_sell` | ADX too low for breakout sell | Entry Quality | ADX below minimum for sell breakout (default 20). Not enough trending momentum. |
| `entry_quality_adx_min_buy` | ADX too low for breakout buy | Entry Quality | ADX below minimum for buy breakout. Market too range-bound for a breakout entry. |
| `entry_quality_atr` | ATR (volatility) too low | Entry Quality | Average True Range below minimum. Market too quiet — spread eats too much of the potential move. |
| `entry_quality_bb_contraction` | Bollinger Bands contracting | Entry Quality | BB squeezing inward. Breakout requires expanding bands — contracting means no momentum building. |
| `entry_quality_bb_expansion` | Bollinger Bands not expanding enough | Entry Quality | BB width has not expanded enough from recent low. Required for breakout confirmation. |
| `entry_quality_m30_not_bearish` | M30 not confirming bearish | Entry Quality | 30-min timeframe not showing bearish structure. M30 must agree with M5 sell signal. |
| `entry_quality_macd_q0` | MACD Q0 — neutral rising | Indicators | MACD positive and rising. Required for buys on some setups. Blocks sells (momentum is bullish). |
| `entry_quality_macd_q1` | MACD Q1 — neutral falling | Indicators | MACD positive but falling. Required for sells. Blocks buys. |
| `entry_quality_macd_q2` | MACD Q2 — bearish falling | Indicators | MACD negative and falling. Required for strong sells. Blocks buys. |
| `entry_quality_macd_q3` | MACD Q3 — bearish rising | Indicators | MACD negative but recovering. Blocks both aggressive sells and buys — market transitioning. |
| `entry_quality_h4_rsi_sell_blocked` | H4 RSI blocked sell | Indicators | 4-hour RSI already oversold. Selling here risks piling into an exhausted H4 move. |
| `entry_quality_h4_rsi_buy_blocked` | H4 RSI blocked buy | Indicators | 4-hour RSI already overbought. Buying risks chasing an extended H4 move. |
| `entry_quality_h4_adx_sell_blocked` | H4 ADX blocked sell | Indicators | 4-hour ADX below minimum. No strong H4 trend to support M5 sell signal. |
| `entry_quality_session_sell_cutoff` | Sell cutoff time reached | Session / Time | Sells blocked after configurable UTC hour (default NY 17:00, London 00:00). Avoids overnight short exposure. |
| `open_groups` | Maximum open positions reached | Position Limits | At the group limit (default 2 concurrent). No new entries until an existing group closes. |
| `max_open_same_direction` | Too many positions same direction | Position Limits | At max concurrent SELLs (or BUYs). Prevents over-exposure in one direction. |
| `no_setup` | No valid pattern detected | Market Conditions | Neither BB Breakout nor BB Bounce conditions met. Market didn't reach a BB or show qualifying move. |
| `session_off` | Outside trading session | Session / Time | Bar outside allowed sessions (London / New York). Asian session typically excluded for thin liquidity. |
| `spread_too_wide` | Spread exceeds maximum | Market Conditions | Bid-ask spread wider than max (default 30 pts XAUUSD). Entry uneconomical — cost too high vs target profit. |
| `min_rr` | Risk:Reward ratio too low | Risk Management | Distance entry→TP1 not large enough vs SL distance. Requires minimum R:R (default 1.5×). |
| `min_entry_atr` | ATR too small at entry bar | Risk Management | ATR at the specific entry bar is below minimum. Checks actual-bar ATR, not just recent average. |
| `high_vol_trend_guard` | High-volatility trend guard | Risk Management | ADX very high AND H1/H4 trend not fully aligned. Requires both TFs to agree in explosive conditions. |
| `adx_hysteresis` | ADX cooling down | Risk Management | ADX recently exceeded trend-enter threshold; not yet below trend-exit. Waits for ADX to cool — avoids chasing decelerating trend. |
| `sell_loss_grace` | Post-loss cooldown (sell) | Risk Management | A sell recently hit SL. Cooldown period (default 90s) before new sells. Prevents revenge-trading. |
| `loss_cooldown` | Post-loss cooldown (any) | Risk Management | Any trade hit SL. Brief cooldown before any new entry. |
| `direction_cooldown` | Same-direction cooldown | Risk Management | Recent entry in same direction. Short bar-count cooldown to avoid stacking entries too quickly. |
| `warmup_tester_m5_rollovers` | Tester warmup | System | M5 indicator buffers lack enough history at backtest start. Signals discarded — they'd be based on incomplete data. |
| `news_filter_blocked` | News event blackout | Risk Management | High-impact news event imminent or just released. Entries blocked within configurable windows (e.g. NFP: 30 min before, 60 min after). |
| `news_filter_tighten` | News event tightened criteria | Risk Management | Near medium-impact news. Entries allowed but stricter RSI conditions apply. Signal failed tightened criteria. |
| `dd_equity_close_all` | Drawdown breaker — equity too low | Risk Management | Equity dropped below drawdown threshold (default 3% from session high). New entries suspended until equity recovers. |

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

---

## Playwright Test Suite

All Athena UI changes MUST pass the full Playwright suite before commit. Tests live in `tests/ui/`.

### Test files

| File | Coverage |
|------|---------|
| `test_athena_backtest.spec.js` | **Primary** — 20 tests covering backtest tab, indicators tab, 508 compliance, API wiring, auto-refresh |
| `test_dashboard.spec.js` | Dashboard load, header, mode badge, left/right panels, tab nav, no JS errors |
| `test_panels.spec.js` | Right panel (TV/LENS, OsMA, AUTO_SCALPER), activity log, mode buttons, AURUM chat, performance, groups, SENTINEL |
| `test_closures.spec.js` | Closures tab visibility, switching, API help text, stats tiles |
| `test_athena_audit.spec.js` | Full tab walk + screenshot + JSON report for manual review |

### Make targets

```bash
make test-ui           # Run all UI tests (Playwright, all files)
make test-ui-backtest  # Run only backtest + 508 suite (fast, use after every dashboard change)
make test-ui-508       # Run only 508 compliance tests
make test-ui-audit     # Full audit with screenshots → tests/results/athena-ui-audit.json
```

### 508 compliance test coverage

`test_athena_backtest.spec.js` includes:
- **TAKEN ENTRIES header cells**: font ≥ 9px, contrast ≥ 4.5:1 (computed via alpha-compositing)
- **GATE BREAKDOWN header**: font ≥ 9px, contrast ≥ 4.5:1
- **All 8 tab buttons**: font ≥ 9px (verified via `getComputedStyle`)

Use the audit script in SKILL.md for a full-page 508 scan before committing new panels.

### When to add tests

For every new tab, panel, or API endpoint added to Athena:
1. Add tab ID to `ALL_TABS` in `test_athena_backtest.spec.js`
2. Add panel render test (header text visible, key labels)
3. Add API structure test if new endpoint
4. Add 508 test for any new header row
