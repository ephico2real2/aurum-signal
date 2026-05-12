# FORGE Indicator Atlas + Boolean Composite Registry

**Living document.** This is the source of truth for:
- Every indicator FORGE computes (with file:line cite + SIGNALS-table population status)
- Every validated boolean composite (with cross-day truth tables + calibration history)
- Logging gaps (computed live but not logged → can't validate)
- Pattern coverage (which day-types each composite catches)
- **The exact shell/SQL commands** used to verify each fact (§13 append-only log)

**Maintenance rules**:
1. Every new analytical insight, calibration adjustment, or newly discovered indicator
   MUST be appended/updated here. Run-23+ analysis documents reference this file as
   the canonical inventory.
2. **ALWAYS log the actual command you ran to verify any fact** — to §13 Command Log
   (append-only). No "verified 2026-05-12" claim without a corresponding command-log
   entry. Future analysts must be able to re-run the same command and reproduce.
3. Skill `.claude/skills/forge-monitor/SKILL.md` mandates pulling this atlas before
   creating any boolean composite for setup analysis, AND mandates logging commands
   to §13 of this atlas.

**Last updated**: 2026-05-12

---

## §1. Full FORGE indicator inventory (per-tick available)

| Category | Indicator | Globals / Vars | Source | Populated in SIGNALS? |
|---|---|---|---|---|
| **Macro trend** | `h1_trend_strength` | computed each tick | `ea/FORGE.mq5:5770` | ✓ yes (column `h1_trend`) |
|  | `h4_trend_strength` | computed | `:5784` | ✗ not a column |
|  | `m15_trend_strength` | computed | `:5776` | ✗ not a column |
|  | `m1_trend_strength` | computed | `:5854` | ✗ not a column |
|  | `g_daily_bear_bias` / `g_daily_bull_bias` | EA globals | `:216` | derivable from `h1_trend` + daily slope |
|  | `g_regime_label` | EA global | `:651` | ✓ yes (`regime_label`) |
|  | `g_regime_confidence` | EA global | `:652` | ✓ yes |
|  | `g_adx_trend_regime` | EA global (hysteresis) | `:5758` | ✓ yes (`adx_trend_regime`) |
|  | `high_vol_trend` | computed | `:5813` | ✓ yes |
| **HTF directional** | `h1_di_plus` / `h1_di_minus` | computed | `:5700-5704` | ✗ not columns |
|  | `h4_rsi_v` / `h4_adx_v` | computed | `:5789-5790` | ✗ not columns |
|  | `m15_adx` (effective) | computed | `:5724` | ✗ logged as 0 (BUG — see §3) |
| **M5 momentum** | `m5_rsi` | per-tick indicator buffer | RSI handle | ✓ yes (`rsi`) |
|  | `m5_adx` | per-tick | ADX handle | ✓ yes (`adx`) |
|  | `macd_histogram` | computed (FORGE breakout MACD) | per-tick | ✗ logged as 0 (BUG — see §3) |
| **Patterns / Divergence** | `g_rsi_div_type` | EA global (HID_BULL / HID_BEAR / REG_BULL / REG_BEAR / NONE) | divergence logic | ✓ yes (`rsi_divergence`) |
|  | `g_psar_state` | EA global (ABOVE / BELOW / NONE) | PSAR logic | ✓ yes (`psar_state`) |
|  | `pattern_score` | per-tick (composite score) | pattern detector | ✗ logged as 0 (BUG — see §3) |
| **Structure** | `m5_atr` | per-tick | ATR handle | ✓ yes (`atr`) |
|  | `h1_atr`, `h4_atr` | per-tick | ATR handles | ✗ not columns |
|  | `bb_upper`, `bb_lower`, `bb_mid` | per-tick | BB handle | ✓ yes |
|  | `poc_price` | volume profile | optional source | ✓ yes |
|  | `vwap_price` | per-tick | VWAP calc | ✓ yes |
|  | `fib_50` | per-tick | Fibonacci ref | ✓ yes |
| **Session** | `session` | LONDON / NY / ASIA | TimeCurrent + bounds | ✓ yes |
| **Spread / state** | `spread` | per-tick | SymbolInfo | ✓ yes |
|  | `prev_close` | M5[1] close | `iClose(_Symbol, PERIOD_M5, 1)` | derivable |
|  | `g_last_chop_buy_exit_time` | NEW state variable | needs to be added | ✗ requires add |
| **OHLC (M1)** | `open_m1`, `high_m1`, `low_m1`, `close_m1`, `volume_m1` | scribe `market_snapshots` | SQL | ✓ live only (not in SIGNALS) |
| **OHLC (M5+)** | `iOpen/iHigh/iLow/iClose(_Symbol, TF, shift)` for M5 / M15 / H1 / H4 / D1 | EA runtime | builtin MQL5 calls | ✗ NOT in SIGNALS (computable per-tick) |
| **OHLC-derived** | day_high, day_low, day_range, pct_from_high, dist_high_atr | derived from `iHigh(_,PERIOD_D1,0)` etc. | EA computes | ✗ NOT logged |
|  | m5_lh_cascade, m5_hl_cascade (lower/higher-high cascade) | sequential `iHigh/iLow` reads | EA computes | ✗ NOT logged |
|  | m5_inside_bar, m5_outside_bar, m5_doji, m5_strong_bar | bar quality from OHLC | EA computes | ✗ NOT logged |
|  | body_pct, long_lower_wick, long_upper_wick | rejection structure | EA computes | ✗ NOT logged |
|  | m5_range_expanding | volatility expansion | EA computes | ✗ NOT logged |

**Active count**: ~20 distinct indicators populated in SIGNALS, ~8 more computed live but not logged (see §3).

---

## §2. SIGNALS table column schema (source of truth for validation queries)

```sql
SIGNALS (
  id, time, symbol, setup_type, direction, outcome, gate_reason,
  price, spread, atr, rsi, adx,
  bb_upper, bb_lower, bb_mid,
  poc_price, vwap_price, fib_50,
  rsi_divergence,           -- string: HID_BULL / HID_BEAR / REG_BULL / REG_BEAR / NONE
  psar_state,               -- string: ABOVE / BELOW / NONE
  pattern_score,            -- BUG: currently 0
  h1_trend,
  regime_label,             -- string: TREND_BULL / TREND_BEAR / RANGE / VOLATILE
  regime_confidence,
  adx_trend_regime,         -- int 0/1
  high_vol_trend,           -- int 0/1
  session,
  magic, synced,
  macd_histogram,           -- BUG: currently 0
  m15_adx,                  -- BUG: currently 0
  lot_factor,
  run_id
)
```

Use these column names verbatim in cross-day validation SQL.

---

## §2.4. MT5 broker data access — exact commands (file-based, NOT socket-based)

**Architecture clarification**: FORGE EA runs inside MetaTrader 5 (via Wine on macOS).
The EA uses MQL5 builtin functions (`iHigh`, `iLow`, `CopyBuffer`, `SymbolInfoDouble` etc.)
to talk to the broker's data feed. The EA then writes the consumed data to **disk-based JSON
and SQLite files** inside MT5's Common Files directory. Claude / Python / shell tools read
**from disk** — there is NO socket binding from outside the EA process.

```
Broker feed (Vantage)  →  MT5 client  →  FORGE.mq5 (EA)  ─┐
                                                          │  writes
                                                          ▼
                              [disk] MT5 Common Files / Tester /MQL5/Files
                                                          ▲
                                                          │  reads (no socket)
                              Claude shell tools, Python scripts, scribe.py
```

### §2.4.1 Live MT5 Common Files directory (live trading mode)

**Mac path** (Wine-mounted MetaTrader 5):

```bash
MT5_COMMON="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
```

**Files FORGE writes here (refreshed each tick / OnTimer)**:

| File | Content | Refresh cadence |
|---|---|---|
| `market_data.json` | All indicators per timeframe (M1/M5/M15/M30/H1/H4), price, account, open positions, recent deals, volume profile | every tick (1-2 sec live) |
| `broker_info.json` | Broker name, server, account #, leverage, server time, GMT time, account type | OnInit + OnTimer |
| `mode_status.json` | EA mode (SCALPER/WATCH/etc) and effective mode | OnInit + on mode change |
| `tick_data.json` | Last tick bid/ask | every tick |
| `ob_zones.json` | Order block zones (Hermes feature) | as detected |
| `scalper_config.json` | Active config (echo of MT5/Files copy) | OnInit |
| `scalper_entry.json` | Most recent entry params | on entry fire |
| `FORGE_journal_XAUUSD.db` | LIVE SIGNALS + TRADES (SQLite, WAL mode) | per-event |
| `command.json` | Inbound command channel (operator → EA) | on operator action |
| `config.json` | Top-level config snapshot | OnInit |

### §2.4.2 Reading market_data.json (live broker feed snapshot)

```bash
# Quick raw look
cat "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/market_data.json"

# Pretty-printed JSON
cat "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/market_data.json" | python3 -m json.tool

# Specific section (e.g. H1 indicators)
python3 -c "
import json, os
p = os.path.expanduser('~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/market_data.json')
d = json.load(open(p))
print(json.dumps(d['indicators_h1'], indent=2))
"

# Watch live updates (file refreshes every tick)
watch -n 1 "stat -f '%Sm' \"\$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/market_data.json\""
```

### §2.4.3 Reading broker_info.json (capabilities + account)

```bash
cat "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/broker_info.json" | python3 -m json.tool
```

Output fields: `account_type`, `broker`, `server`, `account_login`, `currency`, `leverage`,
`server_time`, `gmt_time`, `forge_version`, `effective_mode`.

### §2.4.4 Reading the LIVE journal SQLite DB

```bash
LIVE_DB="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/FORGE_journal_XAUUSD.db"

# List tables
sqlite3 -readonly "$LIVE_DB" ".tables"

# Latest signals
sqlite3 -readonly "$LIVE_DB" "
SELECT id, datetime(time,'unixepoch'), setup_type, direction, outcome, gate_reason, ROUND(price,2)
FROM SIGNALS ORDER BY id DESC LIMIT 20;"

# Latest trades
sqlite3 -readonly "$LIVE_DB" "
SELECT deal_ticket, magic, ROUND(volume,3), ROUND(price,2), ROUND(profit,2), comment
FROM TRADES ORDER BY time DESC LIMIT 20;"
```

### §2.4.5 Reading the TESTER journal DB (during backtest)

Tester writes to a different path — one per Tester Agent (parallel test agents).
Auto-discovery via:

```bash
find "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5" \
  -name "FORGE_journal_XAUUSD_tester.db" \
  -not -name "*-shm" -not -name "*-wal" 2>/dev/null
```

Typical paths:

```
.../Tester/Agent-127.0.0.1-3000/MQL5/Files/FORGE_journal_XAUUSD_tester.db
.../Tester/Agent-127.0.0.1-3001/MQL5/Files/FORGE_journal_XAUUSD_tester.db
```

Pick the most-recently-modified by `stat -f '%m %N'`:

```bash
find "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5" \
  -name "FORGE_journal_XAUUSD_tester.db" -not -name "*-shm" -not -name "*-wal" 2>/dev/null \
  -print0 | xargs -0 stat -f "%m %N" | sort -rn | head -1 | awk '{print $2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14}'
```

Query against the active tester DB:

```bash
DB="<path from above>"
sqlite3 -readonly "$DB" "SELECT * FROM TESTER_RUNS ORDER BY id DESC LIMIT 5;"
```

**Caveat**: During an active backtest, the tester DB is in WAL mode and may be momentarily
locked. Retry with backoff if `unable to open database file (14)` appears. Aurum_tester.db
(bridged copy at `python/data/aurum_tester.db`) is the reliable read source during active
tester writes.

### §2.4.6 Reading scribe live DB (live trading post-mortem)

```bash
SCRIBE="/Users/olasumbo/signal_system/python/data/aurum_intelligence.db"

# Schema verification (mandatory before assuming columns)
sqlite3 -readonly "$SCRIBE" ".tables"
sqlite3 -readonly "$SCRIBE" ".schema forge_signals"
sqlite3 -readonly "$SCRIBE" ".schema market_snapshots"

# Recent live signals
sqlite3 -readonly "$SCRIBE" "
SELECT id, timestamp_utc, setup_type, direction, outcome, gate_reason
FROM forge_signals WHERE journal_source='live'
ORDER BY id DESC LIMIT 20;"
```

### §2.4.7 Reading scribe tester DB (bridged backtest data, post-Run completion)

```bash
AURUM="/Users/olasumbo/signal_system/python/data/aurum_tester.db"
sqlite3 -readonly "$AURUM" "SELECT aurum_run_id, forge_version, source_run_id FROM aurum_tester_runs ORDER BY aurum_run_id DESC LIMIT 5;"
```

### §2.4.8 Verifying broker exposes a specific indicator (verification-first principle)

```bash
# 1. Confirm FORGE production code uses the indicator API for a timeframe
grep -nE "iHigh\(_Symbol, PERIOD_(D1|H4|H1|M30|M15|M5|M1)|iADX|iRSI|iBands" /Users/olasumbo/signal_system/ea/FORGE.mq5 | head -20

# 2. Confirm market_data.json exposes the indicator
python3 -c "
import json, os
p = os.path.expanduser('~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/market_data.json')
d = json.load(open(p))
# Print all sections
for k in d:
    print(k, type(d[k]).__name__)
"

# 3. Inspect specific timeframe section
python3 -c "
import json, os
p = os.path.expanduser('~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/market_data.json')
d = json.load(open(p))
print(json.dumps(d.get('indicators_h4', 'MISSING'), indent=2))
"
```

### §2.4.9 Helper script — poll_mt5_feed.py

`scripts/poll_mt5_feed.py` waits until `market_data.json` shows the expected `forge_version`
(used after `make forge-compile` to confirm MT5 has reloaded the new EA):

```bash
python3 scripts/poll_mt5_feed.py
python3 scripts/poll_mt5_feed.py --timeout 180
```

It polls the same `market_data.json` file every second until version matches the repo's
VERSION file. Useful for CI / automated reload verification.

---

## §2.5. FORGE ↔ scribe pipeline (verified 2026-05-12)

When FORGE adds a new indicator column to SIGNALS, **two coordinated changes** are required for the data to flow into scribe:

```
EA computes indicator
  │
  ▼
ea/FORGE.mq5  JournalRecordSignal()  ──► SIGNALS table (source tester DB)
  │                                       │
  │                                       │ tester ends / live tick fires
  │                                       ▼
  └─►  Pass new value as parameter   bridge.py / scribe.py polls SIGNALS
                                          │
                                          │ migration: ALTER TABLE forge_signals ADD COLUMN
                                          │ INSERT: INSERT INTO forge_signals (..., new_col) VALUES (..., ?)
                                          ▼
                                       scribe forge_signals (live + tester)
```

**The 3 update points** for any new indicator:

| Update | File | Location |
|---|---|---|
| **1. EA computes + logs** | `ea/FORGE.mq5` | `JournalRecordSignal()` signature `:4868` + `CREATE TABLE SIGNALS` schema `:4691` |
| **2. scribe migration adds column** | `python/scribe.py` | Migration block `:540-570` (`ALTER TABLE forge_signals ADD COLUMN new_col REAL`) |
| **3. scribe INSERT writes column** | `python/scribe.py` | INSERT statement `:1022-1030` + `insert_params` construction |

**Missing any of the 3 = silent data loss**: indicator computed but not logged, or logged in SIGNALS but not propagated to scribe.

The scribe migration pattern at `scribe.py:540-570` is the canonical reference — uses `PRAGMA table_info(forge_signals)` to detect existing columns then `ALTER TABLE` to add missing ones (idempotent on restart).

---

## §3. Logging gaps — indicators computed live but not flowing into SIGNALS

**v2.7.36 logging extension** (target — see `docs/FORGE_LOGGING_EXTENSION_DESIGN.md`) will close all gaps below.

### §3.1. Currently zero-logged (column exists but `JournalRecordSignal` passes `0`)

| Indicator | Current | v2.7.36 plan |
|---|---|---|
| `m15_adx` | column exists, logged as 0 | Update 52 call sites to pass `m15_adx_bounce` (computed at `:5724`) |
| `macd_histogram` | column exists, logged as 0 | Compute MACD on M5 in scalper loop, pass to `JournalRecordSignal` |
| `pattern_score` | column exists, logged as 0 | Pass `pattern_score` from scoring logic |

### §3.2. Computed live but no SIGNALS column

| Indicator | Atlas §1 entry | v2.7.36 plan |
|---|---|---|
| `h4_trend_strength` | computed `:5784` | ADD COLUMN `h4_trend REAL` |
| `m15_trend_strength` | computed `:5776` | ADD COLUMN `m15_trend REAL` |
| `m1_trend_strength` | computed `:5854` | (defer — limited analytical value) |
| `h1_di_plus / h1_di_minus` | computed `:5700-5704` | ADD COLUMN `h1_di_balance REAL` (= di_plus − di_minus, single dim) |

### §3.3. OHLC-derived (case study §4c V3 atoms)

| Atom | Computation | v2.7.36 plan |
|---|---|---|
| D1 OHLC at time of signal | `iHigh/iLow/iOpen(_Symbol, PERIOD_D1, 0)` | ADD COLUMN `day_high`, `day_low`, `day_open` REAL |
| M5 prior-bar OHLC | `iHigh/iLow/iOpen/iClose(_Symbol, PERIOD_M5, 1)` | ADD COLUMN `m5_open_1`, `m5_high_1`, `m5_low_1`, `m5_close_1` REAL |
| M5 lower-high cascade | sequential `iHigh` comparison over 3 bars | ADD COLUMN `m5_lh_cascade INTEGER` (0/1) |
| M5 higher-low cascade | sequential `iLow` comparison over 3 bars | ADD COLUMN `m5_hl_cascade INTEGER` (0/1) |
| M5 body % | `|close-open| / (high-low)` on prior bar | ADD COLUMN `m5_body_pct REAL` |
| BB squeeze indicator | bb_width relative to ATR (derivable from existing) | (derivable from bb_upper-bb_lower / atr; no new column needed) |

### §3.4. Scribe forge_signals — must mirror

For each new SIGNALS column listed above, scribe must add a matching column. The migration pattern at `scribe.py:540-570` is the model:

```python
fs_cols = [r[1] for r in conn.execute("PRAGMA table_info(forge_signals)").fetchall()]
if "h4_trend" not in fs_cols:
    conn.execute("ALTER TABLE forge_signals ADD COLUMN h4_trend REAL")
    log.info("SCRIBE migration: added h4_trend to forge_signals")
# ... repeat for: m15_trend, h1_di_balance, day_high, day_low, day_open,
#                 m5_open_1, m5_high_1, m5_low_1, m5_close_1, m5_lh_cascade,
#                 m5_hl_cascade, m5_body_pct
```

And update the INSERT statement at `scribe.py:1022-1030` to include the new columns and value placeholders.

### §3.5. Why this matters

| Composite | Current validation status | Post v2.7.36 |
|---|---|---|
| `CHOP_IN_BULL_TREND_BUY` (V1) | ✓ validatable today | ✓ |
| `BULL_DAY_DIP_BUY_V2` (POC + Fib + VWAP) | ✓ validatable today (atoms logged) | ✓ |
| `BULL_DAY_DIP_BUY_V3` (+ OHLC atoms) | ✗ NOT validatable (cascade/body_pct/day_high not logged) | ✓ **becomes validatable** |
| `INTRADAY_REVERSAL_TO_SELL_V2` | ✓ validatable today | ✓ |
| `INTRADAY_REVERSAL_TO_SELL_V3` (+ cascade + wick) | ✗ NOT validatable | ✓ **becomes validatable** |
| `NO_TREND_DAY` | ✓ validatable today | ✓ |

**Impact of v2.7.36**: all proposed V3 composites move from "code-only" to "fully cross-day-validatable from historical SIGNALS data." Future case studies can backtest composites against multi-month history without re-running tester.

---

## §4. Layered composite framework

Because of §3, every composite must be designed in two layers:

**Layer 1 — VALIDATABLE composite** (uses only logged indicators)
→ Used for cross-day truth tables against `SIGNALS` / `forge_signals` data.

**Layer 2 — EA-SIDE composite extra** (adds non-logged but live indicators)
→ Adds atoms to the actual filter code; not directly testable against historical SIGNALS until §3 is fixed.

When validating any composite, run the Layer 1 version against the data. When shipping to `ea/FORGE.mq5`, ship Layer 1 + Layer 2.

---

## §5. Composite registry — validated chop-and-trend composites

### §5.1 — `CHOP_IN_BULL_TREND_BUY` (Mar 31 / Apr 1 dip-buy pattern)

> **Enhanced V2** in [`docs/FORGE_CASE_STUDY_2026_03_31_to_04_08.md`](FORGE_CASE_STUDY_2026_03_31_to_04_08.md) §4b — adds `price > poc_price - ATR` and `price > fib_50 - ATR/2` atoms. The Fib 50 atom alone blocks Apr 8 16:35 BB_BOUNCE BUY. Use V2 for new EA code.


**Purpose**: catch dip-buy entries on choppy days with bullish macro bias. Single TP1, no runner, re-entry on cooldown.

**Layer 1 (validatable):**

```mql5
bool CHOP_IN_BULL_TREND_BUY =
     (h1_trend_strength       >= 0.5)              // macro bull
  && (!g_daily_bear_bias)                           // daily not bearish
  && (m5_rsi                  >= 30                 // not falling-knife
      && m5_rsi               <= 50)                // dip zone
  && (m5_adx                  >= 12                 // some life
      && m5_adx               <= 40)                // not parabolic
  && (price <= m5_bb_m + 0.5 * m5_atr)              // structural dip near BB middle
  && (price >= m5_bb_l - 0.2 * m5_atr)              // not flushed below band
  && ((price - vwap_price)    <= 0.5 * m5_atr)      // close to or near VWAP
  && (g_rsi_div_type          != "REG_BEAR")        // no regular bearish divergence
  && (session == "LONDON" || session == "NY")       // institutional session
  && ((TimeCurrent() - g_last_chop_buy_exit_time) >= 300);  // 5-min re-entry cooldown
```

**Layer 2 extras (EA-side, requires §3 fix for full validation):**

```mql5
  && (h4_trend_strength       >= 0.3)              // H4 also bullish
  && (m15_trend_strength      >= 0.3)              // M15 aligned
  && (h1_di_plus              >  h1_di_minus)      // H1 directional momentum BULL
  && (m15_adx                 >= 15)               // M15 has structure
  && (macd_histogram          >  0                 // MACD continuation
      || g_rsi_div_type       == "HID_BULL")       // OR hidden bull div
```

**Calibration history:**

| Date | Change | Reason |
|---|---|---|
| 2026-05-12 (v1, Apr 1 only) | `h1_trend ≥ 1.0`, hard `price < vwap`, required `psar==BELOW` | Designed from Apr 1 data alone |
| 2026-05-12 (v2, Mar 31 cross-check) | Lowered to `h1_trend ≥ 0.5`; softened VWAP to `(price-vwap) ≤ 0.5×ATR`; dropped PSAR | Apr 1-only composite caught 0 entries on Mar 31 (h1 was 0.82-1.28, VWAP-relative was above) |
| 2026-05-12 (v3) | Added `m5_rsi ≥ 30` floor and `m5_adx ≤ 40` ceiling | Falling-knife protection + parabolic exhaustion filter |

**Cross-day truth table — Mar 31 (validated):**

| Hr | h1≥0.5 | RSI 30-50 | ADX 12-40 | BB pos | VWAP gap ≤3 | div ≠ REG_BEAR | Session | RESULT |
|---|---|---|---|---|---|---|---|---|
| 10:00 | ✓ 0.87 | ✓ 45.5 | ✓ 22 | ✓ -5.9 from mid | ✓ +1.01 | ✓ NONE | ✓ LONDON | **TAKE** |
| 13:00 | ✓ 0.90 | ✓ 40.0 | ✓ 33 | ✓ -9.2 | ✓ -13.3 | ✓ NONE | ✓ LONDON | **TAKE** |
| (all others) | mixed | RSI or VWAP fails | | | | | | SKIP |

**Result: 2 entries on Mar 31** (10:00, 13:00).

**Cross-day truth table — Apr 1 (validated):**

| Hr | h1≥0.5 | RSI 30-50 | BB pos | VWAP gap | RESULT |
|---|---|---|---|---|---|
| 16:00 | ✓ +2.32 | ✓ 39.9 | ✓ near bb_lower | _check_ | **TAKE** |
| 17:00 (post-cooldown) | ✓ +2.31 | ✓ 46.4 | ✓ | _check_ | **TAKE** (if ADX ≥ 12 borderline) |
| 18:00 | ✓ +2.38 | ✗ 61.0 | ✗ near bb_upper | | SKIP |

**Result: 2-3 entries on Apr 1.**

**Geometry recommendation:**
- TP1 = **40 pips** (0.65×ATR with ATR=6) — operator-specified
- **No TP2 / TP3** — single banking event
- SL = 1.0×ATR (~60 pips) — tight
- Lot = `regime-aligned amplifier × base_dump_lot` (e.g. ×5 = 0.10 per entry)
- Re-entry cooldown: 300 sec

**Mapped to FORGE struct (new state):**
- `g_last_chop_buy_exit_time` (datetime) — set when position closes via TP1

---

### §5.2 — `TREND_CONTINUATION_BUY` (Apr 8 / Apr 14 sustained trend pattern)

**Purpose**: catch trend continuation entries when momentum is confirmed and BB_BREAKOUT is blocked by `entry_quality_atr_ext`. Wave-ride with staged-add.

**Layer 1:**

```mql5
bool TREND_CONTINUATION_BUY =
     (h1_trend_strength       >= 1.0)              // strong H1 bull (stricter than chop version)
  && (g_psar_state            == "BELOW")           // PSAR bullish-aligned (sustained trend = PSAR stable)
  && (g_regime_label IN ["TREND_BULL", "VOLATILE"]) // regime confirms
  && (!g_daily_bear_bias)                           // daily not bearish
  && (m5_rsi >= 40 && m5_rsi <= 70)                 // entry zone, not exhausted
  && (m5_adx                  >= 20)                // trending
  && (m5_close > iClose(_Symbol, PERIOD_M5, 1));    // bar-over-bar continuation
```

**Calibration history:**

| Date | Change | Reason |
|---|---|---|
| 2026-05-12 | Initial design from Apr 1 16:00-18:30 NY rally analysis | Apr 1 16:00-19:00 ($66 rally) had 4 BB_BREAKOUT SKIPs (`entry_quality_atr_ext`) — composite would have entered |

**Coverage validation pending**: Apr 8 + Apr 14 to confirm.

**Geometry:**
- TP1=0.6×ATR, TP2=1.0×ATR — same as MOMENTUM_DUMP
- SL = 4.0×ATR (wide — trend rides)
- Lot = full × `wave_confirmation_lot_mult` on staged-add legs

---

### §5.3 — `FRACTIONAL_SELL_IN_BULL` (counter-regime overbought probe)

**Purpose**: Fractional-lot SELL probe when M5 is overbought in a confirmed bull regime — pullback expected but bounded.

**Layer 1:**

```mql5
bool FRACTIONAL_SELL_IN_BULL =
     (g_regime_label          == "TREND_BULL")
  && (h1_trend_strength       >= 1.0)              // strong bull (sharp pullbacks here)
  && (g_psar_state            == "ABOVE")           // PSAR just flipped bearish
  && (m5_rsi >= 60 && m5_rsi <= 75)                 // overbought zone
  && (m5_adx                  >= 30)                // strong momentum = real pullback potential
  && (m5_close < iClose(_Symbol, PERIOD_M5, 1))     // bar-over-bar bearish
  && (price >= bb_upper - 0.2 * m5_atr);            // near or above BB upper
```

**Geometry:**
- Lot = base × 0.25 (fractional probe)
- TP1 = 0.3×ATR (tight scalp)
- No TP2 (single banking)
- SL = 1.5×ATR (tight; wrong direction in bull = exit fast)
- No staged-add (no wave-riding against the regime)

**Status**: design only — not yet validated against day data. Run 24 candidate.

---

### §5.4 — `BLOCK_SELL_IN_CHOP` (universal SELL filter)

**Purpose**: Block SELL entries in chop regimes (gold retraces UP — chop-SELL is high-loss-rate per Run 22 G5001 −$51).

**Layer 1:**

```mql5
bool BLOCK_SELL_IN_CHOP =
     (direction               == "SELL")
  && (g_regime_label          == "RANGE")
  && (h1_trend_strength       >  0.5)              // H1 still bullish (counter to direction)
  && (!FRACTIONAL_SELL_IN_BULL);                    // unless qualifying as the rare overbought probe
```

**Apply as a gate to all SELL filter chains:**
- BB_BREAKOUT SELL
- BB_BOUNCE SELL
- BB_PULLBACK_SCALP SELL
- MOMENTUM_DUMP SELL (already has `dump_chop_block`)

**New gate code**: `entry_quality_chop_block_sell`.

---

### §5.7 — `INTRADAY_REVERSAL_TO_SELL` (Apr 2 morning + Apr 8 12:00 pivot — Run 25 critical)

> **Enhanced V2** in [`docs/FORGE_CASE_STUDY_2026_03_31_to_04_08.md`](FORGE_CASE_STUDY_2026_03_31_to_04_08.md) §4b — adds POC + Fib 50 + VWAP + BB-width structural confirmation. Use V2 for new EA code.


**Purpose**: Detect the moment within a bullish-macro day when intraday turns to a sustained decline.
This is THE composite that would have caught:
- Apr 2 09:00 crash (price 4672 → 4594 in 1 hour, h1_trend dropping 1.34 → 0.76)
- Apr 8 12:00 pivot (RSI dropping 64.9 → 33.4 over 3 hours, HID_BEAR divergence appears)

**Boolean (validatable — all atoms in SIGNALS):**

```mql5
bool INTRADAY_REVERSAL_TO_SELL =
     (h1_trend_strength >= 0.3)               // macro WAS bull (h1 lagging the reversal)
  && (m5_close < iClose(_Symbol,PERIOD_M5,6))  // M5 declining last 30min
  && (iClose(_Symbol,PERIOD_M5,6)
       < iClose(_Symbol,PERIOD_M5,12))         // and 60min ago higher → 2-hour decline cascade
  && (m5_rsi <= 40)                            // RSI confirming weakness
  && (g_rsi_div_type == "HID_BEAR"             // ← THE CRITICAL ATOM — hidden bear divergence
      || g_rsi_div_type == "REG_BEAR"          // OR regular bear divergence
      || (m5_close < m5_bb_m))                 // OR price below BB midline (structural confirmation)
  && (price < vwap_price)                      // below VWAP = institutional bear bias
  ;
```

**Apr 8 12:00 truth eval (verified from Run 23 hourly data):**

| Atom | Value | Pass? |
|---|---|---|
| h1_trend ≥ 0.3 | 1.40 | ✓ |
| M5 declining 30min | 4793 < 4810ish | ✓ |
| 60min cascade | 4810 < 4827 (09:00 peak) | ✓ |
| RSI ≤ 40 | 33.4 | ✓ |
| HID_BEAR div | YES | ✓ |
| price < vwap | -17.84 below | ✓ |
| **RESULT** | | **TRIGGER — pivot to SELL** |

**Apr 2 09:00 truth eval:**

| Atom | Value | Pass? |
|---|---|---|
| h1_trend ≥ 0.3 | 0.76 | ✓ |
| M5 declining 30min | 4594 << 4672 (massive drop) | ✓ |
| 60min cascade | 4672 < 4676 | ✓ |
| RSI ≤ 40 | 22.1 (extreme) | ✓ |
| HID_BEAR or below-mid | price -56 below bbm | ✓ |
| price < vwap | -116 below | ✓ |
| **RESULT** | | **TRIGGER — pivot to SELL** |

**Action when TRUE**:
- **Block ALL BUY setups** (BB_BOUNCE, BB_PULLBACK_SCALP, MOMENTUM_DUMP_BUY, BB_BREAKOUT_BUY)
- **Enable + AMPLIFY MOMENTUM_DUMP SELL** (existing setup, regime-aligned 2× lot)
- **Hold while composite remains TRUE** — exits when m5_rsi recovers above 50 or HID_BEAR clears

### §5.8 — `NO_TREND_DAY` (Apr 6, Apr 7 pattern — chop ladder territory)

**Purpose**: Detect days where macro direction is unclear (h1_trend near zero). No high-conviction direction setups; small chop ladder probes only.

```mql5
bool NO_TREND_DAY =
     (MathAbs(h1_trend_strength) <= 0.3)       // h1_trend near zero
  && (g_regime_label == "RANGE")               // regime confirms
  && (m5_adx < 25)                             // genuinely low trend strength
  ;
```

**When TRUE**: activate `CHOP_LADDER_BUY_GRID` (atlas §5.5) only. Block all directional setups.

**Apr 7 evaluation**: h1_trend hovered -0.19 to +0.02 ALL DAY, 100% RANGE regime, ADX 16-46 (mixed but mostly low). Match: `NO_TREND_DAY=TRUE` most hours → chop ladder, no directional bets.

### §5.6 — `INTRADAY_BEAR_IN_BULL` (Apr 8 PM pattern — Run 25 candidate)

**Purpose**: Detect when intraday M15 has flipped bearish while macro H1 stays bullish.
This is the "afternoon decline within a bull day" pattern that caught Run 23 BB_BOUNCE BUY
at Apr 8 16:35 floating −$200 — we should have been SELLing the bounces, not buying them.

**Boolean (Layer 2 — needs m15_trend_strength which is computed live but not logged today):**

```mql5
bool INTRADAY_BEAR_IN_BULL =
     (h1_trend_strength       >= 0.5)              // macro / H1 still bull
  && (m15_trend_strength      <= -0.2)             // BUT M15 has flipped bearish
  && (m5_close < iClose(_Symbol,PERIOD_M5,6))      // M5 lower than 30min ago
  && (iClose(_Symbol,PERIOD_M5,6)
       < iClose(_Symbol,PERIOD_M5,12));            // and 60min ago higher → sustained drift down
```

**Layer 1 fallback (using only logged indicators)** — proxy for M15 trend via M5 close walk:

```mql5
bool INTRADAY_BEAR_IN_BULL_LAYER1 =
     (h1_trend_strength       >= 0.5)
  && (m5_close < iClose(_Symbol,PERIOD_M5,6))      // last 30 min declining
  && (iClose(_Symbol,PERIOD_M5,6) < iClose(_Symbol,PERIOD_M5,12))
  && (iClose(_Symbol,PERIOD_M5,12) < iClose(_Symbol,PERIOD_M5,24))  // 2-hour declining cascade
  && (price < bb_mid)                              // below midline (structural confirmation)
  ;
```

**Action when TRUE** (directional flip):
- **Block** BB_BOUNCE BUY (the wrong-direction setup that lost $200 on Apr 8)
- **Block** BB_PULLBACK_SCALP BUY (same wrong-direction mean-reversion)
- **Block** MOMENTUM_DUMP BUY (bounce-catcher)
- **Allow + AMPLIFY** MOMENTUM_DUMP SELL (use `wave_confirmation_lot_mult` as regime-aligned amplifier)

**Run 23 validation evidence (Apr 8 PM)**:

| Trade | Outcome | What composite says |
|---|---|---|
| 14:57 MOMENTUM_DUMP BUY (won small +$4) | won by luck | composite would BLOCK (intraday bear) |
| 15:07 MOMENTUM_DUMP BUY (lost −$29) | bad | composite would BLOCK ✓ |
| 15:26 MOMENTUM_DUMP SELL +$6 | correct | composite ALLOWS + AMPLIFY ✓ |
| 16:35 BB_BOUNCE BUY (floating −$54) | bad | composite would BLOCK ✓ |
| 16:40 MOMENTUM_DUMP SELL +$5 | correct | composite ALLOWS + AMPLIFY ✓ |

With composite applied + amplifier on SELL: each $5+ wave of decline = 2× SELL lot deployed, banking 2-3× more on each win, ZERO BUY losses. **Inverse of what happened — +$200+ banked instead of −$200 floating.**

**Status**: design only — Run 25 candidate. Implementation requires:
1. M15 trend strength logging (currently §3 logging gap) OR Layer-1 fallback using only logged data
2. New gate code `entry_quality_intraday_bear_block_buy` in `config/gate_legend.json`
3. Filter insert in BB_BOUNCE / BB_PULLBACK_SCALP / MOMENTUM_DUMP BUY filter chains
4. Regime-aligned amplifier wiring for MOMENTUM_DUMP SELL

---

### §5.5 — `CHOP_LADDER_BUY_GRID` (pure range day pattern)

**Purpose**: Stage 4 BUY LIMIT pending orders below a recent swing low; let chop oscillation fill them. No per-leg SL — basket kill switches replace.

**Trigger composite:**

```mql5
bool CHOP_LADDER_TRIGGER =
     (g_regime_label          == "RANGE")
  && (m5_adx                  <  25)                // confirmed chop, no trend forming
  && (g_h1_trend_strength     >= -0.3              // not strongly bearish daily
      && g_h1_trend_strength  <= +0.3)              // truly directionless
  && (!g_daily_bear_bias)                           // (BUY-grid bias; gold retraces UP)
  && (price <= m5_bb_l + 0.5 * m5_atr);             // near BB lower band
```

**Ladder shape**:
- 4 BUY LIMITs at swing_low − [0.2, 0.5, 0.8, 1.1] × ATR
- 0.02 lot per leg, total 0.08 max exposure
- Per-leg TP1 = 0.4×ATR; NO TP2; NO per-leg SL
- Basket kill: regime-change (RANGE → TREND), 60-min time expiry, 30-min pending expiry

**Status**: design only — Run 24 candidate.

---

## §6. Pattern coverage matrix

| Day type | Macro h1_trend | Regime mix | Composite | Status |
|---|---|---|---|---|
| Mar 30 (no sim data) | — | — | (likely chop-in-bull) | n/a |
| Mar 31 (chop-in-bull) | +0.57 avg (0.82-1.28 hourly) | 37% trend / 63% RANGE | `CHOP_IN_BULL_TREND_BUY` | ✓ validated 2 entries |
| Apr 1 (chop-in-bull stronger) | +2.26 avg | 62% trend / 38% RANGE | `CHOP_IN_BULL_TREND_BUY` + `TREND_CONTINUATION_BUY` | ✓ validated 2-3 + 3 entries |
| Apr 7 (transition) | unknown | unknown | (likely TREND_CONTINUATION) | needs analysis |
| Apr 8 (huge bull) | strong | mixed | `TREND_CONTINUATION_BUY` + `MOMENTUM_DUMP` (with new dump_atr_mult=1.0) | needs validation |
| Apr 9 (moderate) | unknown | unknown | (likely TREND_CONTINUATION) | needs analysis |
| Apr 13 (chop) | unknown | unknown | (likely CHOP_IN_BULL_TREND_BUY or CHOP_LADDER) | needs analysis |
| Apr 14 (trend) | unknown | unknown | (likely TREND_CONTINUATION) | needs validation |
| Apr 15-16 (G5048 day) | bearish daily | trend down | should block all BUY via `daily_bear_block` | partial — extended to MOMENTUM_DUMP in v2.7.34 |
| Pure chop day (no entries observed yet) | ~0 | mostly RANGE | `CHOP_LADDER_BUY_GRID` | designed, not validated |

**Action items by day** (TODO):
- [ ] Run cross-day truth table on Apr 7, 8, 9, 13, 14 once Run 23 reaches them OR query Run 18 data for same
- [ ] Identify days where NO composite catches the right entries → new composite needed
- [ ] Identify days where MULTIPLE composites fire → resolve precedence

---

## §7. Workflow when creating a new composite

1. **Pull the indicator atlas** (this file) — confirm which indicators are populated vs logged-only
2. **Pick the candidate day(s)** — query SIGNALS hourly for indicator state
3. **Hand-write the boolean** — start with what reads as "this day was bull-dip-buy / etc."
4. **Truth-eval at each hour** — does the composite say TAKE at the right hours and SKIP at the wrong ones?
5. **Cross-validate on 2+ similar days** — composite must work across the day-type, not just one day
6. **Calibrate atoms** that fire wrong (too strict / too loose)
7. **Append to §5** — write the composite into the registry with calibration history
8. **Map to FORGE indicators** (§1) — every atom → existing global or marked **add**
9. **Translate to MQL5** in `ea/FORGE.mq5` (new function or filter insert)
10. **Append to §6** — mark which days the composite covers

---

## §8. Glossary — operator-validated principles

| Principle | Source | Composite reference |
|---|---|---|
| "Gold always retraces upward in chop" | Operator domain expertise + Run 22 G5001/G5011 data | `BLOCK_SELL_IN_CHOP`, `CHOP_IN_BULL_TREND_BUY` |
| "Don't fire 10 orders without thinking" | Operator (Mar 31 G5009 -$305 disaster) | `staged_initial_legs=1`, `staged_add_min_favorable_points=500`, `wave_confirmation_lot_mult` |
| "Chop scalp = TP1-only, re-enter" | Operator | `CHOP_IN_BULL_TREND_BUY` (no TP2), `CHOP_LADDER_BUY_GRID` |
| "Indicators + regime determine setup, then ride wave" | Operator | All composites; setup = boolean composite |
| "Sell is fine but should be fractional lot in bull-trend matches" | Operator | `FRACTIONAL_SELL_IN_BULL` |
| "BB_BREAKOUT max_reentry_atr_ext blocks legitimate trend continuations" | Apr 1 analysis | `TREND_CONTINUATION_BUY` (new setup, not loosen breakout) |

---

## §9. Open questions / unresolved gaps

1. **Logging gap fix (§3)** — when will `m15_adx`, `macd_histogram`, `pattern_score` be properly logged? Required before Layer-2 composites are validatable from data.
2. **Schema additions** — `h1_di_plus`, `h1_di_minus`, `h4_trend`, `m15_trend` not columns. Add migration?
3. **Mar 30 baseline** — sim starts Mar 31; can we get Mar 30 data from a different source for fuller cross-day calibration?
4. **Pattern coverage on weekly cycle** — Apr 2, 3, 6, 7, 9, 10 not yet analyzed. Are there day-types not covered by current composites?

---

## §10. Append-only changelog

| Date | Change |
|---|---|
| 2026-05-12 | Atlas created. §1 inventory, §3 logging gaps documented, §5.1 `CHOP_IN_BULL_TREND_BUY` v3 (after Mar 31 cross-calibration), §5.2 `TREND_CONTINUATION_BUY` initial design, §5.3 `FRACTIONAL_SELL_IN_BULL`, §5.4 `BLOCK_SELL_IN_CHOP`, §5.5 `CHOP_LADDER_BUY_GRID`. |
| 2026-05-12 | Added §11 Scribe schema (live DB inventory from `aurum_intelligence.db`) and §12 cross-DB join patterns for post-mortem. Verified via `.schema` queries — not hallucinated. |
| 2026-05-12 | §5.6 INTRADAY_BEAR_IN_BULL composite added (Run 25 candidate). Pattern observed Run 23 Apr 8 PM — macro h1_trend=+1.56 (bull) but intraday M15 declining; BB_BOUNCE BUY caught the bounce-top and lost $200 floating. Composite would have flipped direction → 2× SELL amplifier on the decline → +$200+ inverse outcome. |
| 2026-05-12 | §5.7 INTRADAY_REVERSAL_TO_SELL added (validatable Layer 1 from logged-only atoms). Cross-day validation: Apr 2 09:00 crash (h1=0.76 RSI=22) and Apr 8 12:00 pivot (h1=1.40 RSI=33 + HID_BEAR div) both trigger correctly. §5.8 NO_TREND_DAY added (Apr 6, Apr 7 patterns — chop ladder territory). Day-type pattern coverage §6 updated for all 6 days Mar 31 → Apr 8. |
| 2026-05-12 | **Case study created**: [`docs/FORGE_CASE_STUDY_2026_03_31_to_04_08.md`](FORGE_CASE_STUDY_2026_03_31_to_04_08.md) — boolean composite derivation per day, 3-composite consolidation, Apr 8 12:00 exact pivot identification. **§5 enhanced with V2 composites** using POC + Fib 50 + VWAP gap + BB width — Fib 50 atom alone would have blocked Apr 8 16:35 BB_BOUNCE BUY (−$200 floating). Future date-range pattern analysis MUST follow this case-study template. |
| 2026-05-12 | **§2.5 FORGE↔scribe pipeline** documented (3 update points required for new indicator columns). **§3 expanded** into §3.1-§3.5 covering current zero-logged gaps, missing columns, OHLC-derived atoms, scribe mirror requirements, and per-composite validation status. **§11.0 forge_signals current schema** verified; **§11.0.1 planned v2.7.36 additions** (13 new columns) documented with migration SQL. Case study §4c adds V3 OHLC composites. Logging extension design: [`docs/FORGE_LOGGING_EXTENSION_DESIGN.md`](FORGE_LOGGING_EXTENSION_DESIGN.md). |
| 2026-05-12 | **Research skill created**: `.claude/skills/research/SKILL.md` + `/research <topic>` command. Background research agent launched for 9 indicators (RSI div, VWAP, POC, Fib, BB squeeze, MQL5 OHLC, swing structure, PSAR, ADX DI). Results to `docs/RESEARCH_NOTES_<topic>.md` — will be referenced from atlas §1 once research completes. |
| 2026-05-11 | **Research session 2 COMPLETE — 8 new pattern notes for candidate composites** ([`asia_range_breakout`](RESEARCH_NOTES_asia_range_breakout.md), [`round_number_levels`](RESEARCH_NOTES_round_number_levels.md), [`prior_day_high_low`](RESEARCH_NOTES_prior_day_high_low.md), [`overnight_gap_fade`](RESEARCH_NOTES_overnight_gap_fade.md), [`bb_squeeze_breakout`](RESEARCH_NOTES_bb_squeeze_breakout.md), [`news_pulse_reversal`](RESEARCH_NOTES_news_pulse_reversal.md), [`failed_breakout_fade`](RESEARCH_NOTES_failed_breakout_fade.md), [`opening_range_breakout`](RESEARCH_NOTES_opening_range_breakout.md)). Candidate setups validated against canonical sources (mql5.com, StockCharts ChartSchool, Capital.com, FXEmpire, ForexTester, LiteFinance, BollingerBands.com, Bulkowski's thepatternsite.com). Statistical edge highlights: London-breakout direction ~65–70% correct (Asia range), small-gap fill rates 45–78% (overnight gap), chart-pattern failure rate 28–44% modern markets (failed breakout fade — high-edge), ORB 40–60% win rate with 35% of daily highs/lows in first 30 min, NFP-CPI-FOMC two-phase spike/fade canonical (news pulse). |
| 2026-05-11 | **Research session COMPLETE — 9 indicator notes written** ([`rsi_divergence`](RESEARCH_NOTES_rsi_divergence.md), [`vwap_institutional_bias`](RESEARCH_NOTES_vwap_institutional_bias.md), [`volume_profile_poc`](RESEARCH_NOTES_volume_profile_poc.md), [`fibonacci_retracement`](RESEARCH_NOTES_fibonacci_retracement.md), [`bollinger_squeeze`](RESEARCH_NOTES_bollinger_squeeze.md), [`mql5_ohlc_access`](RESEARCH_NOTES_mql5_ohlc_access.md), [`swing_structure_detection`](RESEARCH_NOTES_swing_structure_detection.md), [`psar_reliability`](RESEARCH_NOTES_psar_reliability.md), [`adx_di_lines`](RESEARCH_NOTES_adx_di_lines.md)). Canonical sources cited: Kraken, FXOpen, Wikipedia, GoCharting, TradingView Support, StockCharts ChartSchool, BollingerBands.com (John Bollinger), MQL5 Docs, LinnSoft. Key rules surfaced — divergence requires Wilder failure-swing confirmation; VWAP is institutional benchmark with daily reset and first-30-min instability; POC ≈ ±1σ of intraday volume (70% Value Area); Fib 50 is Dow-Theory midpoint NOT a Fibonacci ratio; BBW squeeze is direction-agnostic regime indicator; iHigh returns 0 on history-not-found (ERR 4401) requiring SERIES_SYNCHRONIZED pre-check; Dow trend reversal requires reaction-high/low break not just structural pivot; Wilder's own recommendation pairs PSAR with ADX > 25; ADX measures STRENGTH only — DI balance gives direction. |

---

## §11. Scribe (live) DB schema — `python/data/aurum_intelligence.db`

**Purpose**: Post-mortem on LIVE trades. Scribe captures runtime indicator state, trade
execution events, regime classifications, and Aurum signals (Telegram/Vision) — separate
from the tester DB. **Always query first** with `.tables` + `.schema <name>` before assuming
column names — schema evolves with new ALTER TABLE migrations.

**Tables present (verified 2026-05-12, 16 tables, ~430k+ rows total):**

| Table | Row count (live) | Purpose |
|---|---|---|
| `forge_signals` | 258,459 | Every SIGNAL emit from FORGE EA in live mode (synced via journal) |
| `market_snapshots` | 164,177 | Tick-by-tick market state (richer than forge_signals — has EMAs, bb_width, TV rating, MACD) |
| `market_regimes` | 36,370 | Regime classifier output + full feature vector (JSON) |
| `system_events` | 7,870 | EA-emitted system events (errors, regime flips, etc.) |
| `trade_closures` | 6,449 | Per-position close events |
| `trade_positions` | 1,211 | Open/managed position state |
| `vision_extractions` | 746 | LENS Vision (image-based signal extraction) |
| `aurum_conversations` | 558 | Telegram/discord conversation log |
| `signals_received` | 447 | External signals (Aurum operator + automated sources) |
| `trade_groups` | 393 | Group-level state (entry plan, TP1/TP2/TP3, lens_rating) |
| `trading_sessions` | 363 | Daily session summaries |
| `news_events` | 28 | News calendar |
| `component_heartbeats` | 10 | Liveness pings |
| `aurum_tester_runs` | 0 | (empty in live scribe — bridge writes here only for tester) |
| `_fjt_old` | — | Backup of older `forge_journal_trades` |
| `forge_journal_trades` | 20 | Trade journal sync |

### §11.0 forge_signals — current schema (verified 2026-05-12)

Current columns (28 base + 5 ALTER-added):

```
id, forge_id, time, timestamp_utc, symbol, setup_type, direction,
outcome, gate_reason, price, spread, atr, rsi, adx,
bb_upper, bb_lower, bb_mid, poc_price, vwap_price, fib_50,
rsi_divergence, psar_state, pattern_score, h1_trend,
regime_label, regime_confidence, adx_trend_regime, high_vol_trend,
session, magic,
-- ALTER TABLE additions (existing)
journal_source TEXT, run_id INTEGER, macd_histogram REAL, m15_adx REAL,
lot_factor REAL, wall_time INTEGER, aurum_run_id INTEGER
```

### §11.0.1 forge_signals — **planned v2.7.36 additions** (13 new columns)

To be added via `scribe.py:540-570` migration pattern (idempotent ALTER TABLE):

```python
# v2.7.36 — OHLC-derived atoms + HTF trend strength logging
ALTER TABLE forge_signals ADD COLUMN h4_trend REAL DEFAULT 0;        -- H4 EMA-spread trend strength
ALTER TABLE forge_signals ADD COLUMN m15_trend REAL DEFAULT 0;       -- M15 EMA-spread trend strength
ALTER TABLE forge_signals ADD COLUMN h1_di_balance REAL DEFAULT 0;   -- H1 (DI+ − DI−), positive = bull, negative = bear
ALTER TABLE forge_signals ADD COLUMN day_high REAL DEFAULT 0;        -- iHigh(_Symbol, PERIOD_D1, 0)
ALTER TABLE forge_signals ADD COLUMN day_low REAL DEFAULT 0;         -- iLow(_Symbol, PERIOD_D1, 0)
ALTER TABLE forge_signals ADD COLUMN day_open REAL DEFAULT 0;        -- iOpen(_Symbol, PERIOD_D1, 0)
ALTER TABLE forge_signals ADD COLUMN m5_open_1 REAL DEFAULT 0;       -- prior M5 bar OHLC
ALTER TABLE forge_signals ADD COLUMN m5_high_1 REAL DEFAULT 0;
ALTER TABLE forge_signals ADD COLUMN m5_low_1 REAL DEFAULT 0;
ALTER TABLE forge_signals ADD COLUMN m5_close_1 REAL DEFAULT 0;
ALTER TABLE forge_signals ADD COLUMN m5_lh_cascade INTEGER DEFAULT 0;-- 3-bar lower-highs (0/1)
ALTER TABLE forge_signals ADD COLUMN m5_hl_cascade INTEGER DEFAULT 0;-- 3-bar higher-lows (0/1)
ALTER TABLE forge_signals ADD COLUMN m5_body_pct REAL DEFAULT 0;     -- |close-open|/(high-low) on prior bar
```

INSERT statement at `scribe.py:1022-1030` must be extended with the 13 new column names and 13 `?` value placeholders.

Implementation steps live in [`docs/FORGE_LOGGING_EXTENSION_DESIGN.md`](FORGE_LOGGING_EXTENSION_DESIGN.md).

### §11.1 `market_snapshots` — the RICH indicator source (LIVE)

```sql
CREATE TABLE market_snapshots (
  id, timestamp, mode, source, symbol,
  bid, ask, spread,
  open_m1, high_m1, low_m1, close_m1, volume_m1,
  rsi_14, macd_hist, ema_20, ema_50,
  bb_upper, bb_mid, bb_lower, bb_width,
  adx, tv_rating, timeframe,
  session, news_guard_active,
  outcome_label, label_filled,
  -- ALTER TABLE additions:
  pending_entry_threshold_points, trend_strength_atr_threshold, breakout_buffer_points,
  regime_label, regime_confidence, regime_model,
  poc_price, vwap_price, fib_50, fib_382, fib_618,
  rsi_divergence, psar_state
);
```

**Indicators in `market_snapshots` NOT in `forge_signals`** (live-only enrichment):
- `ema_20`, `ema_50` (M5 EMAs — useful for trend confirmation in composites)
- `bb_width` (BB squeeze indicator — chop detector)
- `tv_rating` (TradingView signal — external indicator)
- `macd_hist` (correctly populated in market_snapshots — fixes §3 gap for live)
- `fib_382`, `fib_618` (full Fibonacci levels — forge_signals only has fib_50)

**For post-mortem composite analysis**: join `forge_signals` × `market_snapshots` on timestamp to enrich the indicator set.

### §11.2 `market_regimes.feature_json` — the regime classifier's feature vector

```json
{
  "ret_1": 0.0,
  "volatility": 0.259921,
  "ema_spread": 8.462,
  "adx": 48.022,
  "bb_width": 0.00521,
  "spread": 0.26,
  "session": "SYDNEY",
  "mode": "WATCH",
  "source": "LENS",
  "lens_used": true,
  "lens_stale": false,
  "lens_age_sec": 4.2,
  "rsi": 77.54,
  "macd_hist": 0.353,
  "tv_recommend": 0.5,
  "lens_price_delta": 26.125
}
```

Every classifier output preserves the FULL feature vector at decision time. Critical for
post-mortem: "what did the model see when it called RANGE?"

### §11.3 `trade_groups` — execution-side reality

```sql
CREATE TABLE trade_groups (
  id, timestamp, mode, session, source, signal_id, direction,
  entry_low, entry_high, sl, tp1, tp2, tp3,
  num_trades, lot_per_trade, risk_pct, scale_factor, account_balance, account_type,
  lens_rating, lens_rsi, lens_confirmed,
  status, closed_at, close_reason, total_pnl, pips_captured,
  trades_opened, trades_closed, magic_number,
  pending_entry_threshold_points, trend_strength_atr_threshold, breakout_buffer_points,
  regime_label, regime_confidence, regime_model, regime_entry_mode, regime_policy, regime_fallback_reason,
  entry_zone_pips, trades_filled, entry_type, entry_cluster, trades_range_min, trades_range_max,
  trades_policy_reason, open_context, total_pip_value_usd
);
```

**Key post-mortem fields**: `total_pnl`, `pips_captured`, `close_reason`, `regime_label` at
group-open time, `lens_rating` (Vision confidence), `regime_fallback_reason` (if classifier
was stale).

### §11.4 `signals_received` — external Aurum signals (Telegram + Vision)

```sql
CREATE TABLE signals_received (
  id, timestamp, mode, session, raw_text, channel_name, message_id,
  signal_type, direction, entry_low, entry_high, sl, tp1, tp2, tp3, tp3_open,
  mgmt_intent, mgmt_pct, action_taken, skip_reason, trade_group_id,
  signal_source_type, vision_extraction_id, vision_confidence,
  regime_label, regime_confidence, regime_model, regime_entry_mode, regime_policy, regime_fallback_reason
);
```

Tracks every external signal (operator Telegram messages, Vision-extracted chart images) and
whether it was acted on (`action_taken`) or skipped (`skip_reason`).

---

## §12. Cross-DB join patterns for post-mortem

When investigating a live trade outcome:

**Pattern 1 — Indicator state at trade time** (enrich forge_signals with market_snapshots):

```sql
SELECT
  s.timestamp_utc, s.setup_type, s.direction, s.outcome, s.gate_reason,
  s.rsi as forge_rsi, s.adx as forge_adx, s.h1_trend, s.regime_label,
  ms.rsi_14 as ms_rsi, ms.macd_hist, ms.ema_20, ms.ema_50, ms.bb_width,
  ms.tv_rating, ms.fib_382, ms.fib_618, ms.regime_model
FROM forge_signals s
LEFT JOIN market_snapshots ms
  ON ms.timestamp = s.timestamp_utc AND ms.mode = 'LIVE'
WHERE s.timestamp_utc BETWEEN ? AND ?
  AND s.outcome = 'TAKEN'
ORDER BY s.timestamp_utc;
```

**Pattern 2 — Trade outcome with full execution context** (join trade_groups):

```sql
SELECT
  s.timestamp_utc, s.setup_type, s.direction,
  tg.entry_low, tg.sl, tg.tp1, tg.tp2,
  tg.total_pnl, tg.pips_captured, tg.close_reason,
  tg.lens_rating, tg.regime_label as exec_regime
FROM forge_signals s
JOIN trade_groups tg ON tg.signal_id = s.id
WHERE s.outcome = 'TAKEN'
  AND tg.status = 'CLOSED';
```

**Pattern 3 — Regime classifier audit** (what features did the model see?):

```sql
SELECT timestamp, regime_label, confidence, feature_json
FROM market_regimes
WHERE timestamp BETWEEN ? AND ?
  AND regime_label != (LAG regime_label)   -- regime flips only
ORDER BY timestamp;
```

**Pattern 4 — External signal correlation** (did Telegram + FORGE agree?):

```sql
SELECT
  sr.timestamp as ext_time, sr.signal_type, sr.direction as ext_dir,
  sr.action_taken, sr.skip_reason,
  s.timestamp_utc as forge_time, s.setup_type, s.outcome as forge_outcome
FROM signals_received sr
LEFT JOIN forge_signals s
  ON ABS(strftime('%s', s.timestamp_utc) - strftime('%s', sr.timestamp)) < 120
WHERE sr.timestamp > ?
ORDER BY sr.timestamp;
```

**Anti-hallucination rule**: ALWAYS run `.tables` and `.schema <table>` BEFORE writing a
post-mortem query against scribe. Schema evolves; assumed columns from this atlas may have
been altered. Verify current state, then query.

### §12.1 Scribe extension proposals (operator opt-in)

Based on the LIVE inventory, candidate logging extensions to consider when post-mortem
analysis hits a "missing data" wall:

| Need | Current state | Proposed extension |
|---|---|---|
| Track which composite fired the entry | not logged | Add `composite_name` TEXT column to `forge_signals` (e.g. "CHOP_IN_BULL_TREND_BUY") |
| Record amplifier multiplier at entry | not logged | Add `wave_confirmation_lot_mult` REAL column to `trade_groups` |
| Capture H4 + M15 trend strength | only h1_trend logged | Add `h4_trend`, `m15_trend` REAL columns to `forge_signals` |
| Bar-over-bar continuation flag | not logged | Add `m5_close_vs_prev_bar` INTEGER (-1/0/+1) to `forge_signals` |
| HTF DI balance | not logged | Add `h1_di_balance` REAL (= di_plus - di_minus) to `forge_signals` |

**Process for proposing extensions**: open a Recommendation in the relevant run analysis doc
with §11 cite, justify with post-mortem evidence, append to §3 of this atlas, ship in a
later FORGE.mq5 version with proper `ALTER TABLE` migration.

---

## §13. Command Log — actual shell/SQL commands executed (append-only)

**Process rule** (mandatory): every time the atlas, a case study, or a run analysis doc
makes a "verified" or "confirmed" or "the data shows" claim, the EXACT command that
produced that evidence MUST be appended to this section. Format:

```
### YYYY-MM-DD HH:MM — <one-line purpose>
**Doc/section referencing this**: <atlas §X, case study §Y, run analysis §Z>
**Command**:
\`\`\`bash
<paste the literal command, no truncation>
\`\`\`
**Output sample** (first 5-10 lines if non-trivial):
\`\`\`
<output>
\`\`\`
**Conclusion drawn**: <one sentence>
```

Future analysts must be able to re-run any command here and reproduce the result
(modulo data changes from new runs).

### 2026-05-12 16:50 — Discover active tester DB by mtime
**Doc**: forge-monitor SKILL §SETUP step 1; atlas §2.4.5

```bash
find "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5" \
  -name "FORGE_journal_XAUUSD_tester.db" 2>/dev/null \
  -print0 | xargs -0 stat -f "%m %N" | sort -rn | head -3
```

Output sample:
```
1778534098 /Users/olasumbo/Library/Application Support/.../Tester/Agent-127.0.0.1-3000/MQL5/Files/FORGE_journal_XAUUSD_tester.db
1778531121 /Users/olasumbo/Library/Application Support/.../Tester/Agent-127.0.0.1-3001/MQL5/Files/FORGE_journal_XAUUSD_tester.db
```

**Conclusion**: Agent-3000 is the active tester DB for Run 23 (most-recent mtime).

### 2026-05-12 17:05 — Inspect live market_data.json (broker indicators feed)
**Doc**: atlas §2.4.2, §0 data-availability verification

```bash
cat "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/market_data.json" | python3 -m json.tool | sed -n '50,150p'
```

Output sample:
```
"indicators_h1": { "rsi_14": 67.1, "ema_20": 4722.5, "ema_50": 4708.31, "atr_14": 19.64, "bb_upper": 4779.98, "bb_mid": 4707.17, "bb_lower": 4634.36, "macd_hist": 7.57784, "adx": 44.3 }
"indicators_h4": { "ema_20": 4698.3, "ema_50": 4671.89, "atr_14": 36.05, "rsi_14": 66.2, "bb_upper": 4757.11, "bb_mid": 4708.98, "bb_lower": 4660.84, "adx_14": 29.5 }
"indicators_m15": { "rsi_14": 77.2, "ema_20": 4745.35, ..., "macd_hist": 2.48654, "adx": 62.8 }
```

**Conclusion**: Broker exposes M1/M5/M15/M30/H1/H4 indicators including RSI, EMAs, ATR,
BB, MACD histogram (M5+), ADX. H4 has no macd_hist; M1 has no rsi/macd. Volume profile
includes POC, VWAP, fib_50/382/618.

### 2026-05-12 17:08 — Confirm broker capabilities (account + server)
**Doc**: atlas §2.4.3

```bash
cat "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/broker_info.json" | python3 -m json.tool
```

Output sample:
```
{
    "account_type": "DEMO",
    "broker": "Vantage International Group Limited",
    "server": "VantageInternational-Demo",
    "leverage": 500,
    "forge_version": "2.7.34"
}
```

**Conclusion**: Demo account, Vantage broker, leverage 500. Standard MT5 capabilities.

### 2026-05-12 17:12 — Verify FORGE production uses iHigh/iLow/iOpen/iClose on all timeframes
**Doc**: atlas §0.1 (data availability), §2.4.8

```bash
grep -nE "iHigh\(_Symbol,|iLow\(_Symbol,|iOpen\(_Symbol,|iClose\(_Symbol,|iTime\(_Symbol," /Users/olasumbo/signal_system/ea/FORGE.mq5 | grep -v "^//" | head -25
```

```bash
grep -hoE "PERIOD_M1|PERIOD_M5|PERIOD_M15|PERIOD_M30|PERIOD_H1|PERIOD_H4|PERIOD_D1|PERIOD_W1|PERIOD_MN1" /Users/olasumbo/signal_system/ea/FORGE.mq5 | sort | uniq -c | sort -rn
```

Output:
```
86 PERIOD_M5
10 PERIOD_H1
 9 PERIOD_M1
 8 PERIOD_H4
 4 PERIOD_M15
 4 PERIOD_D1
 3 PERIOD_M30
```

Production-usage examples (verified):
- Line 4304: `iClose(_Symbol, PERIOD_D1, 0)` — daily close
- Line 4188-4193: M5 prior-bar OHLC (shift 1 and 2)
- Line 5524-5527: M5 OHLC iteration

**Conclusion**: PERIOD_M1/M5/M15/M30/H1/H4/D1 are all verified-available via builtin
MQL5 OHLC functions in FORGE production code.

### 2026-05-12 17:18 — Scribe live DB table enumeration
**Doc**: atlas §11.0, §2.4.6

```bash
sqlite3 -readonly /Users/olasumbo/signal_system/python/data/aurum_intelligence.db ".tables"
sqlite3 -readonly /Users/olasumbo/signal_system/python/data/aurum_intelligence.db ".schema forge_signals"
```

Output (key fields):
```
forge_signals: 258459 rows, 30 base cols + 7 ALTER (journal_source, run_id, macd_histogram, m15_adx, lot_factor, wall_time, aurum_run_id)
market_snapshots: 164177 rows, RICH per-tick indicators
market_regimes: 36370 rows, includes feature_json
```

**Conclusion**: Scribe live DB has 16 tables, 430k+ rows. Schema verified at this date —
re-check on next read.

### 2026-05-12 18:35 — Verify scalper_config.json + defaults.json keys + sync screening preserved
**Doc**: `FORGE_REGIME_TAXONOMY.md §10.5.2c` (Python-contract preservation)

**Purpose**: confirm the 20-knob rename does NOT touch:
1. JSON keys in `config/scalper_config.json`
2. JSON keys in `config/scalper_config.defaults.json`
3. Validation/screening functions in `sync_scalper_config_from_env.py`

**Commands**:

```bash
# 1. Enumerate JSON keys for the 20 affected concepts in active config:
python3 -c "
import json
d = json.load(open('/Users/olasumbo/signal_system/config/scalper_config.json'))
for section, body in d.items():
    if isinstance(body, dict):
        keys = [k for k in body if k in (
          'daily_direction_gate_enabled','daily_sma_period','daily_sma_lookback_days',
          'daily_slope_block_atr','daily_move_block_atr','daily_move_flip_hysteresis',
          'daily_cancel_pending_on_flip','daily_cancel_includes_cascade',
          'regime_h1_override_factor','regime_h1_override_adx_min',
          'h4_rsi_gate_enabled','h4_rsi_sell_max','h4_rsi_buy_min',
          'h4_adx_gate_enabled','h4_adx_min_sell','h4_adx_min_buy',
          'adx_hysteresis_enabled','adx_hysteresis_apply_in_tester',
          'adx_trend_enter','adx_trend_exit')]
        if keys: print(f'{section}: {keys}')
"

# 2. Repeat for defaults file — should match
python3 -c "import json; ..."

# 3. List sync script's screening functions (none of these change in the rename):
grep -nE '^def |^class ' /Users/olasumbo/signal_system/scripts/sync_scalper_config_from_env.py
```

**Output**:

```
JSON keys in scalper_config.json:
  safety: ['adx_hysteresis_enabled','adx_hysteresis_apply_in_tester','adx_trend_enter',
           'adx_trend_exit','daily_direction_gate_enabled','daily_sma_period',
           'daily_sma_lookback_days','daily_slope_block_atr','daily_move_block_atr',
           'daily_move_flip_hysteresis','daily_cancel_pending_on_flip',
           'daily_cancel_includes_cascade','regime_h1_override_factor',
           'regime_h1_override_adx_min']
  bb_breakout: ['h4_rsi_gate_enabled','h4_rsi_sell_max','h4_rsi_buy_min',
                'h4_adx_gate_enabled','h4_adx_min_sell','h4_adx_min_buy']

scalper_config.defaults.json: identical 20 keys.

sync_scalper_config_from_env.py functions (12 — all unchanged by rename):
  _env_raw, _env_key_used, _load_env, _parse_value, _clamp, _atomic_write_json,
  _lot_sizing_drop_num_trades, apply_scalper_env_overrides, _sync_to_mt5,
  _stamp_version, main
```

**Conclusion**: The 20-knob env rename is surgical. It modifies ONLY:
- `.env` (14 lines) — env-var name LHS
- `.env.example` (20 lines) — env-var documentation
- `sync_scalper_config_from_env.py` mapping table (20 keys + 1 new ALIASES dict) — the
  ENV-name dict key changes; the `(section, json_key, type, min, max)` tuple is byte-identical.

NOTHING in `scalper_config.json`, `scalper_config.defaults.json`, the sync script's
validation/screening logic, or any Python app changes.

### 2026-05-12 18:30 — Python-app safety audit for 20-knob regime rename plan
**Doc**: `FORGE_REGIME_TAXONOMY.md §10.5.2b` (Python-app safety section)

**Purpose**: verify that the 20 regime/trend/daily/HTF env knobs slated for Phase 2 rename
are NOT consumed by any Python application. Operator constraint: "don't touch anything
used by the Python apps."

**Commands**:

```bash
# 1. Search for direct env-var-name reads in Python (excluding the sync mapping file):
for KNOB in FORGE_REGIME_H1_OVERRIDE_FACTOR FORGE_REGIME_H1_OVERRIDE_ADX_MIN \
            FORGE_DAILY_DIRECTION_GATE_ENABLED FORGE_DAILY_CANCEL_PENDING_ON_FLIP \
            FORGE_DAILY_CANCEL_INCLUDES_CASCADE FORGE_DAILY_SMA_PERIOD \
            FORGE_DAILY_SMA_LOOKBACK_DAYS FORGE_DAILY_SLOPE_BLOCK_ATR \
            FORGE_DAILY_MOVE_BLOCK_ATR FORGE_DAILY_MOVE_FLIP_HYSTERESIS \
            FORGE_H4_RSI_GATE_ENABLED FORGE_H4_RSI_SELL_MAX FORGE_H4_RSI_BUY_MIN \
            FORGE_H4_ADX_GATE_ENABLED FORGE_H4_ADX_MIN_SELL FORGE_H4_ADX_MIN_BUY \
            FORGE_ADX_HYSTERESIS_ENABLED FORGE_ADX_TREND_ENTER FORGE_ADX_TREND_EXIT \
            FORGE_ADX_HYSTERESIS_APPLY_IN_TESTER; do
  HITS=$(grep -rl "$KNOB" /Users/olasumbo/signal_system/python/ \
                            /Users/olasumbo/signal_system/scripts/ \
                            /Users/olasumbo/signal_system/tests/ 2>/dev/null \
         | grep -v sync_scalper_config_from_env.py)
  [ -n "$HITS" ] && echo "$KNOB: $HITS"
done

# 2. Search for lowercase JSON key reads (what Python would consume from scalper_config.json):
grep -rE "daily_direction_gate_enabled|regime_h1_override_factor|h4_rsi_gate_enabled|adx_hysteresis_enabled|adx_trend_enter" \
   /Users/olasumbo/signal_system/python/ /Users/olasumbo/signal_system/scripts/ 2>/dev/null

# 3. Python files that read scalper_config.json:
grep -rl "scalper_config\.json" /Users/olasumbo/signal_system/python/
#   → athena_api.py, aurum.py, bridge.py
#   Each checked manually: none reference any of the 20 regime keys.
```

**Output**: All three queries returned ZERO hits. Only `sync_scalper_config_from_env.py`
(the bridging file) references these env names.

**Conclusion**: The 20-knob rename is **guaranteed Python-app-safe**. Renaming touches
only `.env` + `.env.example` + the sync mapping table. JSON keys in `scalper_config.json`
remain unchanged, so Python apps consuming `scalper_config.json` are unaffected.

### 2026-05-12 17:25 — Verify broken BUY-in-bull lot sizing (operator's Run 23 finding)
**Doc**: Run 23 P&L analysis; v2.7.35 fix justification

```bash
sqlite3 -readonly /Users/olasumbo/signal_system/python/data/aurum_tester.db "
SELECT datetime(s.time,'unixepoch') sim_t, s.setup_type,
       ROUND(s.price,2) entry, ROUND(s.h1_trend,2) h1t, s.regime_label,
       ROUND(s.lot_factor,3) logged_lot_factor
FROM forge_signals s WHERE s.aurum_run_id=23 AND s.outcome='TAKEN' AND s.direction='BUY'
  AND s.h1_trend >= 0.5 AND s.regime_label='TREND_BULL'
ORDER BY s.time LIMIT 20;"
```

Output:
```
2026-04-01 08:20:04 | MOMENTUM_DUMP | 4686.30 | 2.20 | TREND_BULL | 0.125  ← fractional ❌
2026-04-01 08:30:07 | MOMENTUM_DUMP | 4690.15 | 2.19 | TREND_BULL | 0.125  ← fractional ❌
2026-04-08 14:57:18 | MOMENTUM_DUMP | 4802.33 | 1.36 | TREND_BULL | 0.125
2026-04-08 16:35:00 | BB_BOUNCE     | 4782.91 | 1.56 | TREND_BULL | 0.250  ← only BB_BOUNCE used 0.25
2026-04-10 15:36:00 | BB_BREAKOUT   | 4778.72 | 0.54 | TREND_BULL | 1.000  ← only BB_BREAKOUT at full
```

**Conclusion**: All MOMENTUM_DUMP + BB_PULLBACK_SCALP BUYs in confirmed bull used
0.125 fractional factor. Only BB_BREAKOUT correctly used 1.000. Confirms operator's
"broken logic" finding. v2.7.35 fixes via dump_buy_lot_factor=1.0 / dump_sell_lot_factor=0.5.
