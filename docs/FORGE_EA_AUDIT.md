# FORGE EA Comprehensive Audit

**EA Version:** 2.7.9 (FORGE_VERSION const; `#property version "2.79"`)
**Audit Date:** 2026-05-09
**Files Audited:** `ea/FORGE.mq5`, `python/bridge.py`, `python/scribe.py`, `config/scalper_config.json`, `docs/FORGE_277_PLAN.md`

---

## Section 1: FORGE EA Input/Output

### Files FORGE Reads

| File | Source | What FORGE Does With It |
|------|--------|------------------------|
| `scalper_config.json` | Python / make sync | Primary config for all scalper parameters — lot sizing, gates, session windows, journal settings. Hot-reloaded every 20 timer cycles (no recompile needed). Read via `ReadScalperConfig()`. |
| `config.json` | BRIDGE (Python) writes | Live mode: reads `effective_mode`, `scalper_mode`, `regime_*` fields. **Tester: intentionally ignored** — stale config.json from live sessions would override EA Inputs and block backtests. |
| `command.json` | BRIDGE (Python) writes | Action queue: OPEN_GROUP, CLOSE_ALL, CLOSE_PCT, CLOSE_GROUP, CANCEL_GROUP_PENDING, CLOSE_GROUP_PCT, CLOSE_PROFITABLE, CLOSE_LOSING, MOVE_BE_ALL, MODIFY_SL, MODIFY_TP. Reads on every `OnTimer()` cycle. |
| `ob_zones.json` | LENS (Python) writes | Order Block zones from LENS analysis. Read every 20 cycles via `ReadOBZones()`. Optional — gracefully ignored if missing. |

### Files FORGE Writes

| File | Primary Readers | Frequency |
|------|----------------|-----------|
| `market_data.json` | BRIDGE, ATHENA | Every `OnTimer()` cycle (default: 1s) |
| `mode_status.json` | ATHENA | Every `OnTimer()` cycle (if not OFF mode) |
| `broker_info.json` | ATHENA | OnInit + every 20 cycles (configurable via `BrokerInfoEveryCycles`) |
| `scalper_entry.json` | BRIDGE | On each native scalper TAKEN entry (live only; skipped in Strategy Tester) |
| `tick_data.json` | ML collection | WATCH mode only, on each `OnTick()` |
| `FORGE_journal_XAUUSD_tester.db` | BRIDGE (if BRIDGE_SYNC_TESTER_JOURNAL=1), monitoring tools | Strategy Tester: always. Live: uses `FORGE_journal_XAUUSD.db` (Common Files). |

---

## Section 2: market_data.json — Field Audit

FORGE writes the following top-level fields and nested blocks to `market_data.json` (see `WriteMarketData()`, lines 1854–2029):

| Field / Block | bridge.py reads | /api/live | Dashboard | ATHENA autoscalper conditions |
|---------------|:--------------:|:---------:|:---------:|:-----------------------------:|
| `forge_version` | Logged (stale check) | ✓ | ✓ | ✗ |
| `symbol` | ✓ | ✓ | ✓ | ✗ |
| `hermes_version` | ✗ | ✓ | ✗ | ✗ |
| `timestamp_utc` / `timestamp_unix` | ✓ (stale gate, age calc) | ✓ | ✓ | ✗ |
| `server_time_unix` | ✗ | ✓ | ✗ | ✗ |
| `strategy_tester` | ✓ (skip certain behavior) | ✓ | ✗ | ✗ |
| `terminal_connected` | ✓ | ✓ | ✓ | ✗ |
| `trade_allowed` | ✓ | ✓ | ✓ | ✗ |
| `ea_cycle` | ✓ | ✓ | ✗ | ✗ |
| `mode` | ✓ | ✓ | ✓ | ✗ |
| `price.bid` / `price.ask` / `price.spread_points` | ✓ | ✓ | ✓ | ✓ |
| `account.balance` / `.equity` / `.margin` / `.free_margin` | ✓ | ✓ | ✓ | ✓ (drawdown check) |
| `account.total_floating_pnl` | ✓ | ✓ | ✓ | ✓ |
| `account.session_start_balance` / `.session_pnl` | ✗ | ✓ | ✗ | ✗ |
| `account.open_positions_count` | ✓ | ✓ | ✓ | ✗ |
| `account.margin_level` | ✗ | ✓ | ✗ | ✗ |
| `forge_config.*` (3 threshold fields) | ✓ (logged to SCRIBE on group open) | ✓ | ✗ | ✗ |
| `volume_profile.poc_price` / `.vwap_price` / `.fib_*` | ✓ (open_context snapshot) | ✓ | ✗ | ✗ |
| `rsi_divergence` / `psar_state` | ✓ (open_context snapshot) | ✓ | ✗ | ✗ |
| `indicators_h1.*` (rsi, ema20/50, atr, bb, macd_hist, adx) | ✓ | ✓ | ✓ | ✓ |
| `indicators_h4.*` (ema20/50, atr only — no RSI/BB/MACD/ADX) | ✗ | ✓ | ✗ | ✗ |
| `indicators_m1.*` (ema20/50, atr only) | ✗ | ✓ | ✗ | ✗ |
| `indicators_m5.*` (full block: rsi, ema, atr, bb, macd_hist, adx) | ✓ | ✓ | ✓ | ✓ |
| `indicators_m15.*` (full block) | ✓ | ✓ | ✓ | ✓ |
| `indicators_m30.*` (full block) | ✗ | ✓ | ✗ | ✗ |
| `open_positions[]` (ticket, type, lots, price, sl, tp, profit, magic, comment, forge_managed) | ✓ (TRACKER uses it) | ✓ | ✓ | ✓ |
| `open_positions_forge_count` | ✓ | ✓ | ✓ | ✗ |
| `pending_orders[]` (ticket, type, volume, price, sl, tp, magic, forge_managed, comment) | ✓ (TRACKER uses it) | ✓ | ✓ | ✗ |
| `pending_orders_forge_count` | ✗ | ✓ | ✗ | ✗ |
| `recent_closed_deals[]` | ✓ (close detection) | ✓ | ✓ | ✗ |

**Notes:**
- `indicators_h4` is written with only 3 fields (ema_20, ema_50, atr_14). No RSI, BB, MACD, or ADX block. If downstream ever needs H4 ADX or RSI, it must add a handle and expand this block.
- `indicators_m1` similarly only has ema_20, ema_50, atr_14. M1 RSI/BB/ADX are not exposed in market_data.json even though the M1 EMA/ATR handles are initialised.
- `account.margin_level` and `session_start_balance` / `session_pnl` fields are written but not consumed by any known Python component currently.

---

## Section 3: FORGE Journal DB — Schema Audit

### SIGNALS Table (tester DB: `FORGE_journal_XAUUSD_tester.db`)

| Column | Type | Description | bridge.py reads | SCRIBE stores |
|--------|------|-------------|:--------------:|:-------------:|
| `id` | INTEGER PK | Auto rowid | as `forge_id` | as `forge_id` |
| `time` | INTEGER | Unix timestamp (TimeCurrent) | ✓ | ✓ |
| `symbol` | TEXT | Chart symbol (e.g. XAUUSD) | ✓ | ✓ |
| `setup_type` | TEXT | BB_BOUNCE / BB_BREAKOUT / BB_BREAKOUT_RETEST | ✓ | ✓ |
| `direction` | TEXT | BUY / SELL | ✓ | ✓ |
| `outcome` | TEXT | TAKEN / SKIP | ✓ | ✓ |
| `gate_reason` | TEXT | e.g. `entry_quality_session_sell_cutoff` | ✓ | ✓ |
| `price` | REAL | Bid or Ask at signal time | ✓ | ✓ |
| `spread` | REAL | Spread in points | ✓ | ✓ |
| `atr` | REAL | M5 ATR(14) | ✓ | ✓ |
| `rsi` | REAL | M5 RSI(14) | ✓ | ✓ |
| `adx` | REAL | M5 ADX(14) | ✓ | ✓ |
| `bb_upper` / `bb_lower` / `bb_mid` | REAL | M5 Bollinger Bands | ✓ | ✓ |
| `poc_price` / `vwap_price` / `fib_50` | REAL | Volume profile / Fibonacci | ✓ | ✓ |
| `rsi_divergence` / `psar_state` | TEXT | RSI divergence type / PSAR state | ✓ | ✓ |
| `pattern_score` | INTEGER | Candle pattern score (0–N) | ✓ | ✓ |
| `h1_trend` | REAL | H1 trend strength (EMA diff/ATR) | ✓ | ✓ |
| `regime_label` / `regime_confidence` | TEXT/REAL | BRIDGE regime snapshot (live only; blank in Tester) | ✓ | ✓ |
| `adx_trend_regime` | INTEGER | ADX hysteresis state (0/1) | ✓ | ✓ |
| `high_vol_trend` | INTEGER | High-vol trend guard active (0/1) | ✓ | ✓ |
| `session` | TEXT | ASIAN / LONDON / NY (computed from UTC hour) | ✓ | ✓ |
| `magic` | INTEGER | **Base** MagicNumber only (not group magic) — see Issue #3 | ✓ | ✓ |
| `synced` | INTEGER | 0 = unsynced; set to 1 after SCRIBE picks up | n/a | n/a |
| `run_id` | INTEGER | TESTER_RUNS.id (0 for live) | ✓ | ✓ |
| `macd_histogram` | REAL | **NEW 2.7.7+** iOsMA(3,10,16) value at signal | ✓ (version-detected) | ✓ (after ALTER) |
| `m15_adx` | REAL | **NEW 2.7.7+** M15 ADX value used for tier decision | ✓ (version-detected) | ✓ (after ALTER) |
| `lot_factor` | REAL | **NEW 2.7.7+** Combined lot factor applied | ✓ (version-detected) | ✓ (after ALTER) |

### TRADES Table

| Column | Type | Description | bridge.py reads | SCRIBE stores |
|--------|------|-------------|:--------------:|:-------------:|
| `id` | INTEGER PK | Auto rowid | as `forge_rowid` | as `forge_rowid` |
| `deal_ticket` | INTEGER | MT5 deal ticket | ✓ | ✓ |
| `order_ticket` | INTEGER | Originating order ticket | ✓ | ✓ |
| `symbol` | TEXT | Chart symbol | ✓ | ✓ |
| `type` | INTEGER | DEAL_TYPE enum | ✓ | ✓ |
| `direction` | INTEGER | 0=IN, 1=OUT, 2=INOUT, 3=OUT_BY | ✓ | ✓ |
| `volume` | REAL | Deal volume | ✓ | ✓ |
| `price` | REAL | Execution price | ✓ | ✓ |
| `profit` | REAL | Deal profit | ✓ | ✓ |
| `swap` | REAL | Swap charge | ✓ | ✓ |
| `commission` | REAL | Commission | ✓ | ✓ |
| `magic` | INTEGER | Group magic (MagicNumber + group_id) | ✓ | ✓ |
| `comment` | TEXT | Position comment (e.g. `SCALP|BB_BREAKOUT|G5001|TP1`) | ✓ | ✓ |
| `time` | INTEGER | Deal close Unix timestamp | ✓ | ✓ |
| `time_msc` | INTEGER | Millisecond timestamp | ✓ | ✓ |
| `synced` | INTEGER | 0 = unsynced (added by BRIDGE if missing) | n/a | n/a |
| `run_id` | INTEGER | Links to TESTER_RUNS.id (0 for live) | ✓ | ✓ |

### TESTER_RUNS Table (Tester only)

Columns: `id`, `wall_time`, `sim_start_time`, `symbol`, `balance`, `forge_version`, `scalper_mode`, `warmup_m5_bars`, `warmup_seconds`, `magic_base`. Not synced to SCRIBE — used for tester session isolation only.

### New 2.7.7+ Columns — SCRIBE Handling

| Column | FORGE writes it | SCRIBE `forge_signals` has it | bridge.py maps it | Fully wired |
|--------|:--------------:|:-----------------------------:|:-----------------:|:-----------:|
| `macd_histogram` | ✓ (line 3693 in CREATE TABLE; line 3923 in INSERT) | ✓ (added via ALTER in `sync_forge_journal`, scribe.py line 759) | ✓ (version-detected, r[29]) | **Yes** |
| `m15_adx` | ✓ (line 3694; line 3924) | ✓ (ALTER, line 760) | ✓ (r[30]) | **Yes** |
| `lot_factor` | ✓ (line 3695; line 3925) | ✓ (ALTER, line 761) | ✓ (r[31]) | **Yes** |

---

## Section 4: FORGE → SCRIBE Data Flow

### Path 1 — Journal DB Sync (primary path for signal analytics)

```
FORGE.mq5 JournalRecordSignal()
  → writes to SIGNALS table in FORGE_journal_XAUUSD[_tester].db
    (every SKIP or TAKEN event, throttled per M5 bar for noisy gates)
  → bridge.py _bridge_cycle() every 60s calls sync_forge_journal()
    (only live journals by default; BRIDGE_SYNC_TESTER_JOURNAL=1 to override)
  → scribe.py sync_forge_journal() reads SIGNALS WHERE synced=0
    → version-detects macd_histogram/m15_adx/lot_factor columns
    → INSERTs into forge_signals in aurum_intelligence.db
    → marks source rows synced=1
  → ATHENA /api/signals reads forge_signals
```

### Path 2 — scalper_entry.json (live trade confirmation path)

```
FORGE.mq5 (live only, not in Tester) writes scalper_entry.json on TAKEN entry
  → bridge.py _check_forge_scalper_entry() polls scalper_entry.json every cycle
    → deduplicates by timestamp
    → validates trades_opened > 0 AND magic in live market_data positions
    → calls scribe.log_trade_group() → trade_groups table
    → NOTE: scalper_entry.json fields NOT in forge_signals — these go to trade_groups only
```

### Fields Lost in Transit / Not in SCRIBE

| Field in FORGE / journal | Ends up in SCRIBE | Where lost |
|--------------------------|:-----------------:|-----------|
| `SIGNALS.magic` stores base MagicNumber, not group magic | `forge_signals.magic` = base magic | FORGE design: group magic = MagicNumber + group_id; SIGNALS always stores the base (line 3921: `IntegerToString((long)MagicNumber)`) |
| `scalper_entry.json` → `lot_base`, `lot_multiplier`, `auto_lot_*` fields | ✗ | Logged to `open_context` JSON blob in `trade_groups` only; not a first-class column |
| `scalper_entry.json` → `m5_atr`, `h1_trend_strength`, `h4_trend_strength` | ✗ | Stored in `open_context` JSON, not extractable by SQL without JSON parsing |
| `scalper_entry.json` → `sentinel_tight`, `staged_entry`, `staged_legs_pending` | ✗ | Only in `open_context` |
| `SIGNALS.adx` = M5 ADX; `SIGNALS.m15_adx` = M15 ADX | Both in `forge_signals` | Fully wired as of 2.7.7 |
| `TRADES.direction` integer (0=IN, 1=OUT, 2=INOUT, 3=OUT_BY) | ✓ as integer | Human-readable label not decoded; queries must use numeric comparison |
| `TESTER_RUNS` table | ✗ | Not synced; tester run metadata not available in SCRIBE |
| `STATS_CACHE` table | ✗ | EA-side computed stats only; not exposed |

---

## Section 5: Logical Workflow Audit

### Common Pre-Entry Gates (all modes — `CheckNativeScalperSetups`, line 4517)

Applied before mode-specific logic, in order:

1. **Session gate** — Live: `ScalperSessionOK()` (London/NY UTC hours). Tester: `ScalperTesterSessionOK()`. Logs `session_off` on block.
2. **Spread gate** — Live only: `spread > g_sc.max_spread_points` (30 pts default). **Tester: skipped** — modeled spread frequently exceeds the cap, which would zero out backtest fills.
3. **Open groups cap** — `open_groups >= g_sc.max_open_groups` (2 default). Logs `open_groups`.
4. **Session trade cap** — Live only: `session_trades >= g_sc.max_trades_per_session`. Logs `session_trade_cap`.
5. **Loss cooldown** — Live always + Tester when `tester_cooldown_enabled=1`. Logs `cooldown`.
6. **Warmup gate** — Required M5 bar rollovers (Tester) or M15 bar rollovers (live) after attach. Logs `warmup_*`.

### BB_BOUNCE Entry Sequence

1. Price must be within `bounce_bb_proximity_pct`% of the lower (BUY) or upper (SELL) BB band.
2. Rejection candle check (if `bounce_require_rejection_candle=1`).
3. H1 trend direction filter (mode: LEGACY / BALANCED / STRICT per `bounce_htf_bias`).
4. Entry quality gates: ATR minimum, body ratio, directional bar count, BB expansion check.
5. Direction cap (`max_open_same_direction`), news filter (if enabled).
6. Entry fires → `JournalRecordSignal("TAKEN", ...)` + `scalper_entry.json` written (live only).

**Tester relaxations for BB_BOUNCE:** ADX cap and H1 direction filter are relaxed by default (`bounce_respect_adx_max_in_tester=0`, `bounce_respect_h1_filter_in_tester=0` in current config) to improve backtest fill rates.

### BB_BREAKOUT Entry Sequence

1. Price must be outside upper (BUY) or lower (SELL) BB band beyond `breakout_buffer_points`.
2. RSI gates: BUY requires RSI > `rsi_buy_min` (40) and < `rsi_buy_ceil` (70); SELL requires RSI < `rsi_sell_max` (60) and > `rsi_sell_floor` (30/36 depending on ADX).
3. H1 alignment check: `h1_ok_buy` / `h1_ok_sell` using EMA trend strength. **H4 alignment** when `NativeScalperH4Align=true`.
4. SELL-specific gates (2.7.7+):
   - Session SELL cutoff (hour >= 17 in NY, `entry_quality_session_sell_cutoff`).
   - ADX extreme block (M15 ADX >= 55, `entry_quality_adx_extreme_sell`).
   - ADX minimum SELL floor (M15 ADX < 25, `entry_quality_adx_min_sell`).
   - RSI floor / weak-ADX stricter floor (`entry_quality_rsi_sell_floor`).
   - ADX spike-from-flat gate (`entry_quality_adx_spike_sell`).
   - RSI rising gate (`entry_quality_rsi_rising_sell`).
   - OsMA 4-quadrant gate (`entry_quality_macd_q0_bull_rising` / `q1` / `q2` / `q3`).
   - M30 bearish confirmation (`entry_quality_m30_not_bearish`).
5. M15 confirmation when `breakout_require_m15=1`.
6. Entry quality gates (shared with BB_BOUNCE).
7. Lot factor computation: base lot × sell_inside_band factor × near-floor factor × ADX-tier factor × same-direction-stack factor = `g_last_combined_lot_factor` (written to `SIGNALS.lot_factor` on TAKEN).
8. Entry fires → `JournalRecordSignal("TAKEN", ...)` with `macd_histogram`, `m15_adx`, `lot_factor` populated.

### DUAL Mode

Runs BB_BOUNCE signal check first. If no BB_BOUNCE setup found, runs BB_BREAKOUT check. Direction variable is shared across both checks — the first to set it wins.

### What Gets Logged

| Event | Journal (SIGNALS) | scalper_entry.json |
|-------|:-----------------:|:-----------------:|
| Pre-entry gate block | SKIP + gate_reason | ✗ |
| Successful entry | TAKEN + indicator snapshot | ✓ (live only) |
| Session blocked (per M5 bar, throttled) | SKIP + `session_off` | ✗ |
| Spread exceeded | SKIP + `spread` | ✗ |
| Warmup in progress | SKIP + `warmup_*` | ✗ |

**Gap:** In Tester mode, the spread gate and session trade cap are not applied, so the journal may show more TAKEN entries than would occur live. This is intentional and documented in EA comments.

---

## Section 6: Issues Found

### Issue 1 — `SIGNALS.magic` stores base magic, not group magic

**Location:** `JournalRecordSignal()`, line 3921: `IntegerToString((long)MagicNumber)`.

**Problem:** The `SIGNALS` table stores the base `MagicNumber` (e.g. 202401) for every row, regardless of which group fired. The actual group magic (`MagicNumber + group_id`, e.g. 207401 for group 5000) is never in `SIGNALS`. This means you cannot directly JOIN `SIGNALS` to `TRADES` by magic number — `TRADES` stores the group magic while `SIGNALS` stores the base. Documented in project memory file `project_magic_number_fix.md`.

**Impact:** Post-analysis queries like "what indicator state preceded this losing trade?" require an approximate time-based join instead of a clean magic-based join.

**Fix:** Pass `group_magic` (or `g_scalper_group_counter + base`) to `JournalRecordSignal` when available at entry time and write it as the `magic` column for TAKEN signals.

---

### Issue 2 — Spread gate silently disabled in Tester

**Location:** `CheckNativeScalperSetups()`, line 4565: `if(MQLInfoInteger(MQL_TESTER) == 0 && spread > g_sc.max_spread_points)`.

**Problem:** The spread gate is entirely skipped in Strategy Tester. Modeled MT5 spreads for XAUUSD frequently exceed the 30-point live cap. This is an intentional design choice (documented in code comments) but means the backtest does not faithfully replicate the live spread filter. A tester could generate TAKEN entries that would be blocked on live.

**Impact:** Win rate inflation on backtests vs. live (some entries that pass in Tester would be blocked live by spread).

**Workaround:** The EA comment suggests this is "by design." If tighter tester fidelity is needed, add a configurable `tester_max_spread_points` cap separate from `max_spread_points`.

---

### Issue 3 — `scalper_entry.json` has richer data than `SIGNALS`; the extra fields go only into `open_context` JSON blob

**Location:** `bridge.py` `_check_forge_scalper_entry()`, lines 4418–4437.

**Problem:** Fields like `lot_base`, `lot_multiplier`, `auto_lot_dir_trend`, `h1_trend_strength`, `h4_trend_strength`, `m1_trend_strength`, `staged_entry`, and `sentinel_tight` are written to `scalper_entry.json` but stored only in `trade_groups.open_context` as a serialized JSON blob, not as first-class queryable columns. This makes SQL-based analysis of these dimensions impossible without JSON parsing.

**Impact:** Cannot answer "what was H4 trend strength for all SELL entries last week?" without unpacking `open_context`.

**Fix:** Promote the most analytically important fields (`h1_trend_strength`, `h4_trend_strength`, `lot_multiplier`, `sentinel_tight`) to first-class columns on `trade_groups` via `ALTER TABLE`.

---

### Issue 4 — Gate reasons from 2.7.7 are not visible in ATHENA `/api/signals` unless journal is synced

**Location:** `bridge.py` line 2781: `if is_tester and not BRIDGE_SYNC_TESTER_JOURNAL: continue`.

**Problem:** By default, the tester journal is NOT synced to SCRIBE/ATHENA (`BRIDGE_SYNC_TESTER_JOURNAL` defaults to 0 / not set). All SKIP and TAKEN rows from the Strategy Tester accumulate in the tester DB but are invisible in the dashboard. Live signals sync normally.

**Impact:** Gate analysis (e.g. "how many times did entry_quality_session_sell_cutoff fire in Run 25?") must be done directly against the tester SQLite DB, not through the ATHENA API. This is the intended workflow (see `FORGE_TESTER_JOURNAL_QUERIES.md`) but can surprise operators expecting the dashboard to reflect tester runs.

---

### Issue 5 — H4 indicators_h4 block is incomplete

**Location:** `WriteMarketData()`, lines 1932–1940.

**Problem:** The `indicators_h4` block in `market_data.json` only exposes `ema_20`, `ema_50`, and `atr_14`. H4 RSI, BB, MACD, and ADX handles are never initialised (no `g_h4_rsi`, `g_h4_bb`, etc.). H4 regime analysis in BRIDGE uses only the EMA trend-strength formula (`h4_ts = (ema20 - ema50) / atr`), which is sufficient for current gates but limits future H4 signal quality checks from Python.

---

### Issue 6 — `TESTER_RUNS` table not synced to SCRIBE

**Location:** `JournalInit()`, lines 3820–3857.

**Problem:** The `TESTER_RUNS` table (which stores `forge_version`, `scalper_mode`, `sim_start_time`, `magic_base`) is local to the tester DB and never read by BRIDGE or synced to SCRIBE. This means SCRIBE cannot answer "what forge version did Run 17 use?" without a direct DB query.

**Impact:** Low severity. Workaround: query the tester DB directly. Docs reference this workflow.

---

### Issue 7 — `session_trade_cap` gate silently disabled in Tester

**Location:** `CheckNativeScalperSetups()`, line 4575: `if(MQLInfoInteger(MQL_TESTER) == 0 && g_scalper_session_trades >= g_sc.max_trades_per_session)`.

**Problem:** Like the spread gate, the per-session trade cap is live-only. In Tester, FORGE can fire unlimited entries in a single simulated session. This is intentional (backtests need full data density) but means `max_trades_per_session=100` has no effect during backtesting.

---

## Summary Table

| # | Issue | Severity | Fix Available | Version |
|---|-------|----------|:-------------:|---------|
| 1 | `SIGNALS.magic` stores base, not group magic | Medium | Partially (planned) | Pre-2.7.7 |
| 2 | Spread gate disabled in Tester | Low (by design) | Configurable opt-in | Pre-2.7.7 |
| 3 | `scalper_entry.json` rich fields only in `open_context` blob | Medium | `ALTER TABLE` trade_groups | Pre-2.7.7 |
| 4 | Tester journal not synced to ATHENA by default | Low (by design) | Set `BRIDGE_SYNC_TESTER_JOURNAL=1` | Pre-2.7.7 |
| 5 | `indicators_h4` block missing RSI/BB/MACD/ADX | Low | Add handles + fields | Pre-2.7.7 |
| 6 | `TESTER_RUNS` not synced to SCRIBE | Low | Add sync path | Pre-2.7.7 |
| 7 | `session_trade_cap` disabled in Tester | Low (by design) | Configurable opt-in | Pre-2.7.7 |

---

*Audit performed against FORGE v2.7.9, bridge.py (as-of 2026-05-09), scribe.py (DDL current), scalper_config.json v2.7.9.*
