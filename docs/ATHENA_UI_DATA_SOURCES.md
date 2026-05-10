# Athena UI — Panel Data Sources

> Reference for developers. Maps every dashboard panel to the exact file, API endpoint,
> database table, or Python module that provides its data.
> Updated: 2026-05-10

---

## Layout Overview (3-column grid)

```
┌──────────────────┬───────────────────────────────────────┬─────────────────────┐
│  LEFT COLUMN     │  CENTER COLUMN                        │  RIGHT COLUMN       │
│  (186px default) │  (flex)                               │  (258px default)    │
│  resizable ↔     │                                       │  resizable ↔        │
│                  │  [Groups][Closures][Activity]         │                     │
│  Account/MT5     │  [Signals][Uploads][Performance]      │  FORGE quote        │
│  Cumul P&L (7d)  │  [Backtest][Indicators]               │  OsMA Gate          │
│  Mode Control    │                                       │  TradingView/LENS   │
│  Sentinel        │                                       │  AUTO_SCALPER       │
│  System Health   │  ─────────────────────────────────── │  Regime Engine      │
│                  │  AURUM Chat (resizable height ↕)      │                     │
└──────────────────┴───────────────────────────────────────┴─────────────────────┘
```

All three columns are resizable horizontally via drag handles. The AURUM chat panel
at the bottom of the center column is resizable vertically.

---

## Left Column (186px default, resizable 140–320px)

### Account · MT5 Live

| Attribute | Value |
|-----------|-------|
| **Source file** | `MT5/market_data.json` |
| **Written by** | FORGE EA — writes on every MT5 tick |
| **Refresh cadence** | Every tick (~1s when market open); ATHENA polls `/api/live` every 3s |
| **API endpoint** | `GET /api/live` → `account`, `execution`, `pending_orders` fields |
| **Key fields** | `balance`, `equity`, `margin_level`, `open_positions_count`, `session_pnl`, `pending_orders[]` |

Notes:
- Balance/equity/positions come from `market_data.json → account` block.
- Pending orders list comes from `market_data.json → pending_orders[]`.
- The stale-quote amber banner fires when `execution.stale=true` (file age > threshold).
- "FORGE pendings" count is a separate field (`pending_orders_forge_count`) tracking only FORGE-managed pending orders.

---

### Cumulative P&L (7d) mini chart

| Attribute | Value |
|-----------|-------|
| **Source file** | SCRIBE SQLite DB (`python/data/aurum_intelligence.db`) |
| **Table** | `trade_positions` (status=CLOSED, last 7d UTC) |
| **Written by** | SCRIBE — records every closed trade from BRIDGE |
| **Refresh cadence** | 3s poll interval (`/api/pnl_curve`) |
| **API endpoint** | `GET /api/pnl_curve?days=7` → `[{cumulative: float}]` |
| **Key fields** | `cumulative` (running sum of closed PnL), sparkline color from final value sign |

Notes:
- `PERF_ROLLING_DAYS=7` constant in `app.js` controls the window.
- The SESSION P&L box (red/green pill below the balance) comes from `account.session_pnl` in `market_data.json`, not from SCRIBE.

---

### Mode Control

| Attribute | Value |
|-----------|-------|
| **Source file** | `MT5/config.json` (current mode) + `config/aurum_cmd.json` (queued commands) |
| **Written by** | BRIDGE writes `config.json`; mode changes queue via `aurum_cmd.json` |
| **Refresh cadence** | Current mode shown from `/api/live → mode` (3s poll) |
| **API endpoint** | `GET /api/live` (read); `POST /api/mode {"mode":"SCALPER"}` (write) |
| **Key fields** | `mode` (OFF/WATCH/SIGNAL/SCALPER/HYBRID/AUTO_SCALPER), `effective_mode` |

Notes:
- Clicking a mode button POSTs to `/api/mode`, which writes `aurum_cmd.json`; BRIDGE reads it on next cycle.
- Available modes: `OFF`, `WATCH`, `SIGNAL`, `SCALPER`, `HYBRID`, `AUTO_SCALPER`.
- Mode persists across restarts when `RESTORE_MODE_ON_RESTART=true`.

---

### Sentinel

| Attribute | Value |
|-----------|-------|
| **Source file** | `config/sentinel_status.json` |
| **Written by** | SENTINEL component — writes every cycle (~60s) after RSS poll and ForexFactory calendar check |
| **Refresh cadence** | ~60s SENTINEL write cycle; ATHENA exposes via `/api/live → sentinel` (3s poll) |
| **API endpoint** | `GET /api/live` → `sentinel` block |
| **Key fields** | `active` (bool), `next_event`, `next_in_min`, `next_time`, `news_feeds` (RSS buckets), `calendar_currencies` |

Notes:
- Headlines rendered by `SentinelHeadlines` component from `sentinel.news_feeds` buckets: `fxstreet`, `google_news`, `investing_forex`, `dailyfx`, `extra`.
- When `active=true`, the panel goes red and TRADING PAUSED. BRIDGE blocks entries.
- Guard activates ≤30min before HIGH-impact news events.
- See `docs/SENTINEL.md` for the full event lifecycle.

---

### System Health

| Attribute | Value |
|-----------|-------|
| **Source file** | SCRIBE SQLite DB (`component_heartbeats` table) |
| **Written by** | Each component (BRIDGE, LISTENER, LENS, SENTINEL, AEGIS, FORGE, SCRIBE, HERALD, AURUM) writes its own heartbeat row |
| **Refresh cadence** | Per-component write cadence varies (1–60s); `/api/components` polled every 3s |
| **API endpoint** | `GET /api/components` → `{components: [{name, ok, note, timestamp}]}` |
| **Key fields** | `name`, `ok` (bool → green/red dot), `note` (last status line), `timestamp` |

Notes:
- Component colors defined by `CC` map in `app.js` (BRIDGE=teal, LISTENER=orange, LENS=cyan, SENTINEL=red, AEGIS=green, FORGE=amber, SCRIBE=purple, HERALD=blue, AURUM=gold).
- A red dot means no heartbeat within the component's expected interval.

---

## Center Column (flex, resizable within 3-column grid)

### Groups tab

| Attribute | Value |
|-----------|-------|
| **Source** | SCRIBE `trade_groups` + MT5 `open_positions` (via `market_data.json`) |
| **Written by** | SCRIBE (group records); FORGE EA (live position data via `market_data.json`) |
| **Refresh cadence** | 3s poll (`/api/live`) |
| **API endpoint** | `GET /api/live` → `open_groups[]`, `open_groups_queued[]`, `open_positions[]` |
| **Key fields** | `id`, `direction`, `num_trades`, `lot_per_trade`, `entry_low/high`, `sl`, `tp1/2/3`, `trades_closed`, `total_pnl`, `magic_number`, `source` |

Notes:
- Groups matched to live MT5 positions by `magic_number`. Live floating P&L comes from MT5, not SCRIBE.
- Groups with `open_groups_queued` are SCRIBE-only — FORGE magic not yet confirmed in MT5.
- Management buttons (Close Group, Move BE, Close 70%) POST to `/api/management` → `aurum_cmd.json` → BRIDGE → FORGE.
- `source` badge: `FORGE_NATIVE_SCALP` (cyan FORGE badge), `AUTO_SCALPER` (gold AURUM badge), `SIGNAL` (orange SIGNAL badge).

---

### Closures tab

| Attribute | Value |
|-----------|-------|
| **Source** | SCRIBE `trade_positions` (status=CLOSED, last 24h) |
| **Written by** | SCRIBE — writes close record when BRIDGE confirms closed trade from FORGE |
| **Refresh cadence** | 3s poll (`/api/live → recent_closures`) |
| **API endpoint** | `GET /api/live` → `recent_closures[]`, `closure_stats` |
| **Key fields** | `ticket`, `trade_group_id`, `direction`, `pnl`, `pips`, `close_reason` (SL_HIT/TP1_HIT/TP2_HIT/TP3_HIT/MANUAL_CLOSE), `timestamp` |

Notes:
- Shows last 24h only. Full history: `GET /api/closures?days=7`.
- Stat tiles (SL Hits, TP1 Hits, TP2 Hits, Manual, Total P&L) from `closure_stats` rolling window.

---

### Activity tab

| Attribute | Value |
|-----------|-------|
| **Source** | SCRIBE `system_events` table; disk audit at `logs/audit/system_events.jsonl` |
| **Written by** | All components write events via SCRIBE logging API |
| **Refresh cadence** | 3s poll (`/api/events?limit=500`) |
| **API endpoint** | `GET /api/events?limit=500`; export `GET /api/events/export?limit=10000` |
| **Key fields** | `id`, `timestamp`, `event_type`, `triggered_by`, `prev_mode/new_mode`, `reason`, `notes`, `session` |

Notes:
- Events normalized by `normalizeActivityEvent()` into: timestamp, component, category (MODE/TRADE/RISK/AURUM/SYSTEM), level (INFO/WARN/ERROR), message.
- Footer shows "LIVE — SCRIBE system_events; disk audit logs/audit/system_events.jsonl".
- The activity log auto-scrolls to newest events unless the user scrolls up (pause mode).

---

### Signals tab

| Attribute | Value |
|-----------|-------|
| **Source** | SCRIBE `signals_received` table |
| **Written by** | LISTENER — writes every parsed Telegram signal (entry + management) |
| **Refresh cadence** | 3s poll (`/api/signals`) |
| **API endpoint** | `GET /api/signals?limit=50&session=current&stats=1` |
| **Key fields** | `id`, `timestamp`, `channel_name`, `signal_type`, `direction`, `entry_low/high`, `sl`, `tp1/2/3`, `action_taken` (EXECUTED/SKIPPED/EXPIRED/PENDING), `skip_reason`, `trade_group_id` |

Notes:
- Stats tiles (Received, Executed, Skipped, Expired) from `stats` block in API response.
- Channel filter strip built from `channel_name` values in current session's signals.
- Management signals (signal_type=MANAGEMENT) shown as subtle purple-bordered rows.

---

### Uploads tab

| Attribute | Value |
|-----------|-------|
| **Source** | SCRIBE `signal_media` table (via `system_events` upload/chart event types) |
| **Written by** | LISTENER — writes upload events when chart media arrives in Telegram |
| **Refresh cadence** | 3s poll (filtered from `/api/events`) |
| **API endpoint** | `GET /api/events?limit=500` — client-side filtered for `_UPLOAD_` / `SIGNAL_CHART_` event types |
| **Key fields** | `event_type`, `triggered_by`, `reason`, `notes`, `timestamp` |

Notes:
- Uploads are not fetched from a dedicated endpoint — they are filtered client-side from the events list using `isUploadEvent()`.
- Event types matched: contains `_UPLOAD_` or starts with `SIGNAL_CHART_`.

---

### Performance tab

| Attribute | Value |
|-----------|-------|
| **Source** | SCRIBE `trade_positions` (rolling 7d UTC) |
| **Written by** | SCRIBE — closed trade records from BRIDGE |
| **Refresh cadence** | 3s poll (`/api/live → performance`, `/api/pnl_curve?days=7`) |
| **API endpoint** | `GET /api/live` → `performance`, `performance_window`; `GET /api/pnl_curve?days=7` |
| **Key fields** | `total_pnl`, `total` (trade count), `wins`, `losses`, `win_rate`, `avg_pips`, `avg_pip_value_usd` |

Notes:
- Rolling window controlled by `PERF_ROLLING_DAYS=7` constant.
- Cumulative P&L chart uses the same `/api/pnl_curve` sparkline data as the left-column mini chart, but at larger size (w=420 h=70).

---

### Backtest tab — Stat Cards

| Attribute | Value |
|-----------|-------|
| **Source** | `aurum_tester.db` — `forge_signals` + `forge_journal_trades` tables |
| **Written by** | FORGE EA (Strategy Tester mode); BRIDGE syncs to `aurum_tester.db` (~60s) |
| **Refresh cadence** | 30s poll on backtest tab |
| **API endpoint** | `GET /api/backtest/runs`; `GET /api/backtest/run/:id` |
| **Key fields** | `total_pnl`, `win_rate`, `total` (trades), `wins`, `losses`, `best_win`, `worst_loss`, `signals.taken`, `signals.skipped`, `signals.open_at_end` |

Notes:
- Run selector buttons built from `/api/backtest/runs` list.
- Stat cards from `/api/backtest/run/:id → performance` block.
- `TAKEN ENTRIES` table from `btDetail.taken[]` — forge_signals rows where action=TAKEN.
- `GATE BREAKDOWN` from `btDetail.gates[]` — gate_reason counts from forge_signals.

---

### Backtest tab — CUMULATIVE P&L Chart

Already has source footer in UI. Source: `forge_journal_trades` (aurum_tester.db).
Served by `GET /api/backtest/run/:id → pnl_curve[]`.

---

### Backtest tab — RUN ANALYSIS

| Attribute | Value |
|-----------|-------|
| **Source** | `aurum_tester.db` — last two runs compared by `/api/backtest/compare` |
| **Written by** | `python/backtest_compare.py` — computes deltas, scores, gate diffs |
| **Refresh cadence** | Fetched once on backtest tab open and when run list updates |
| **API endpoint** | `GET /api/backtest/compare` |
| **Key fields** | `run_a`, `run_b`, `winner`, `deltas`, `gate_diff`, `note`, `score` per run |

Notes:
- Gate diff highlights which gate_reason counts changed most between runs.
- Deltas displayed as green (positive) or red (negative) for each metric.

---

### Indicators tab

| Attribute | Value |
|-----------|-------|
| **Source** | `config/indicator_legend.json` |
| **Written by** | Developer-maintained JSON — add entries when FORGE adds new indicators |
| **Refresh cadence** | Fetched once on first Indicators tab open |
| **API endpoint** | `GET /api/indicator_legend` |
| **Key fields** | Per-indicator: `full_name`, `acronym`, `forge_params`, `timeframes`, `range`, `category`, `what_it_measures`, `reading_guide`, `forge_usage`, `color` |

Notes:
- See `docs/SKILL.md` "Indicator Legend System — Maintenance Guide" for how to add new indicators.

---

## Right Column (258px default, resizable 180–420px)

The right column is split vertically into two sections (both resizable):
- **TOP**: FORGE execution quote + OsMA Gate (default 280px height)
- **BOTTOM**: TradingView indicators + AUTO_SCALPER + Regime Engine (flex)

---

### FORGE Execution Quote

| Attribute | Value |
|-----------|-------|
| **Source file** | `MT5/market_data.json` — `price` / `execution` block |
| **Written by** | FORGE EA — writes on every MT5 tick |
| **Refresh cadence** | Every tick (~1s); ATHENA polls every 3s |
| **API endpoint** | `GET /api/live` → `execution` block |
| **Key fields** | `bid`, `ask`, `mid`, `spread_usd`, `spread_points`, `symbol`, `age_sec`, `timestamp_utc`, `usable`, `stale`, `stale_reason` |

Notes:
- When `usable=false`, shows amber "NO LIVE BROKER QUOTE" with `stale_reason`.
- File age shown as human-readable string (e.g. "2.3s").
- Spread shown in USD and points.

---

### OsMA Gate

| Attribute | Value |
|-----------|-------|
| **Source file** | `MT5/market_data.json` — `indicators_m5` block (iOsMA) |
| **Written by** | FORGE EA — computes OsMA on M5 bar and writes to market_data.json |
| **Refresh cadence** | Every tick; ATHENA polls every 3s |
| **API endpoint** | `GET /api/live` → `scalper_gates` block |
| **Key fields** | `osma_m5`, `osma_bias` (bull/bear/flat), `require_macd_sell`, `require_macd_buy`, `sell_osma_pass`, `buy_osma_pass`, `macd_fast/slow/signal`, `session_ny_sell_cutoff`, `adx_sell_block` |

Notes:
- OsMA parameters shown as `OsMA(fast,slow,signal) M5` where defaults are `OsMA(3,10,16) M5`.
- Bias classification: positive OsMA → bull, negative → bear, near-zero → flat.
- Gate pass/fail displayed as ✓/✗ per direction.

---

### TradingView / LENS Indicators

| Attribute | Value |
|-----------|-------|
| **Source file** | `config/lens_snapshot.json` |
| **Written by** | LENS component — TV MCP poller writes snapshot on each successful chart read (~60s) |
| **Refresh cadence** | ~60s LENS write; ATHENA polls every 3s |
| **API endpoint** | `GET /api/live` → `tradingview` block |
| **Key fields** | `last` (TV price), `timeframe`, `age_seconds`, `rsi`, `macd_hist`, `bb_rating`, `adx`, `di_plus`, `di_minus`, `ema_20`, `ema_50`, `dmi_present`, `dmi_study`, `order_block_present`, `order_block_values`, `tv_recommend`, `tv_brief` |

Notes:
- TV `last` is not the broker fill price — use MT5 `execution.bid/ask` for order placement.
- `divergence_from_mt5_usd` shown as warning when both sources are available and differ.
- `tv_brief` is a compact narrative summary from LENS/TV analysis.
- DMI study and Order Block Detector detect whether the relevant TradingView studies are loaded on the chart.

---

### AUTO_SCALPER Readiness

| Attribute | Value |
|-----------|-------|
| **Source** | `python/bridge.py` — AUTO_SCALPER condition evaluation |
| **Written by** | BRIDGE — runs on every tick in AUTO_SCALPER mode |
| **Refresh cadence** | 3s poll |
| **API endpoint** | `GET /api/autoscalper/conditions?responses=5` |
| **Key fields** | `overall.pattern_ready`, `overall.direction_ready`, `bridge_prefilters` (h1_bias, prefilter_pass, mt5_fresh, open_groups, max_groups), `setup_snapshot` (near_upper/lower_bb, indicator_data_quality), `lens_indicators` (rsi, macd_hist, adx, bb_rating, di_plus/minus), `latest_autoscalper_responses[]` |

Notes:
- `READY`/`BLOCKED` tag shows whether AURUM auto-scalper would fire.
- `failed_checks[]` list shows which prefilters are blocking.
- "STRATEGY TESTER" banner appears when `strategy_tester=true` (MT5 timestamps are simulated).
- TV LENS sub-panel shows the LENS indicators as AURUM sees them during the auto-scalper evaluation.

---

### Regime Engine

| Attribute | Value |
|-----------|-------|
| **Source file** | `config/status.json` (regime snapshot written by bridge) |
| **Module** | `python/regime.py` — HMM inference engine |
| **Written by** | BRIDGE calls `RegimeEngine.infer()` every tick; persists to `config/status.json` |
| **Refresh cadence** | Every tick; ATHENA polls every 3s |
| **API endpoint** | `GET /api/live` → `regime` block |
| **Key fields** | `current.label` (TREND_BULL/TREND_BEAR/VOLATILE/RANGE/UNKNOWN), `current.confidence`, `current.model_name`, `current.age_sec`, `current.stale`, `config.entry_mode` (off/shadow/active), `config.min_confidence`, `transitions_24h[]`, `performance_30d.by_regime[]` |

Notes:
- Three sub-cards: main regime status, TRANSITIONS (24H), REGIME METRICS (30D).
- `entry_mode` ACTIVE means regime gates entries (AEGIS enforces). SHADOW = log only. OFF = disabled.
- Posterior probability distribution shown when `current.posterior` has values.
- `features.source` shows whether LENS or MT5 provided the feature data.
- HMM has no persistence — model lost on every BRIDGE restart (2-min cold-start each restart).
- See `docs/REGIME_ENGINE_REVIEW.md` for full architecture.

---

## AURUM Chat Panel (resizable height, 140–600px, default 280px)

| Attribute | Value |
|-----------|-------|
| **Source** | Claude API via `python/athena_api.py` backend |
| **Written by** | AURUM — `/api/aurum/ask` POSTs query to Claude with full live context injected |
| **Refresh cadence** | On-demand (user sends message) |
| **API endpoint** | `POST /api/aurum/ask {"query": "..."}` → `{"response": "..."}` |
| **Key fields** | Query text, response text; context injected server-side from `/api/live` |

Notes:
- NEVER call Anthropic directly from the browser — all queries route through ATHENA backend.
- The backend injects live account, LENS, sentinel, performance, and recent closure context before calling Claude.
- Same AURUM instance also available via Telegram bot (identical context injection).
- Quick-action buttons ("P&L today?", "Open groups?", "LENS reading?", "All clear?") pre-fill the input.
- `Also on Telegram` footer note — responses are identical.

---

## Global Footer

The ATHENA global footer (bottom bar) shows:
- `ATHENA · /api/live: execution + tradingview · FORGE + TV MCP · SCRIBE`
- LIVE/DEMO connection status
- Tick counter + poll interval

---

## Source Summary Table

| Panel | Primary Source | API Endpoint |
|-------|---------------|--------------|
| Account · MT5 Live | `MT5/market_data.json` | `/api/live` |
| Cumulative P&L (7d) mini | SCRIBE `trade_positions` | `/api/pnl_curve?days=7` |
| Mode Control | `MT5/config.json` + `aurum_cmd.json` | `/api/live` (read) · `/api/mode` (write) |
| Sentinel | `config/sentinel_status.json` | `/api/live` |
| System Health | SCRIBE `component_heartbeats` | `/api/components` |
| Groups tab | SCRIBE `trade_groups` + MT5 positions | `/api/live` |
| Closures tab | SCRIBE `trade_positions` (CLOSED) | `/api/live` · `/api/closures` |
| Activity tab | SCRIBE `system_events` | `/api/events` |
| Signals tab | SCRIBE `signals_received` | `/api/signals` |
| Uploads tab | SCRIBE `signal_media` (via events) | `/api/events` (filtered) |
| Performance tab | SCRIBE `trade_positions` (7d) | `/api/live` · `/api/pnl_curve` |
| Backtest — Stats | `aurum_tester.db` forge tables | `/api/backtest/run/:id` |
| Backtest — P&L Chart | `aurum_tester.db` `forge_journal_trades` | `/api/backtest/run/:id` |
| Backtest — Run Analysis | `aurum_tester.db` (compare) | `/api/backtest/compare` |
| Indicators tab | `config/indicator_legend.json` | `/api/indicator_legend` |
| FORGE Execution Quote | `MT5/market_data.json` (price block) | `/api/live` |
| OsMA Gate | `MT5/market_data.json` (indicators_m5) | `/api/live` |
| TradingView / LENS | `config/lens_snapshot.json` | `/api/live` |
| AUTO_SCALPER Readiness | `python/bridge.py` conditions | `/api/autoscalper/conditions` |
| Regime Engine | `config/status.json` → `python/regime.py` | `/api/live` |
| AURUM Chat | Claude API via ATHENA backend | `/api/aurum/ask` |
