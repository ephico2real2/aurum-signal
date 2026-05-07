# FORGE ↔ BRIDGE — why Groups show in ATHENA but MT5 has no orders

## How MT5 data reaches ATHENA (no HTTP from MT5)

1. **FORGE.mq5** runs on your chart, `OnTimer` → **`WriteMarketData()`** → writes **`market_data.json`** under MT5 **Common Files** (or terminal-local `MQL5/Files` fallback).
2. That file must be the **same path** Python uses: repo **`MT5/`** symlink or **`MT5_MARKET_FILE`** in `.env`.
3. **ATHENA** (`athena_api.py`) **`GET /api/live`** reads **`MARKET_FILE`** (default `signal_system/MT5/market_data.json`) with normal filesystem reads — **no socket from MT5**.
4. **Pending limits/stops** are listed in **`pending_orders`** inside that JSON (FORGE **v1.2.4+**: all pendings for the chart symbol, with **`forge_managed`** when magic matches the EA range). **Balance / equity / open positions** come from the same file.

If pendings exist in the terminal but ATHENA shows **0**, the usual causes are: **wrong `MT5/` path**, **stale file**, or **FORGE not recompiled** to v1.2.4+.

**After `make forge-compile`**, MetaTrader may still run the **previous** `.ex5` in memory. **`market_data.json` `forge_version`** will not change until you **remove FORGE from the chart and attach it again** (or restart MT5). Check with: `python3 scripts/poll_mt5_feed.py` or `make forge-verify-live`.

---


ATHENA **Groups** come from **SCRIBE** (Python logged the trade group after **AEGIS** approved). **Orders** only appear in MetaTrader if **FORGE.mq5** runs `ReadAndExecuteCommand()` and successfully places tickets.

There is **no HTTP callback** into the EA. FORGE **polls a file**: `command.json` in the MT5 **Files** directory (Common or terminal-local — see below).

All config and file-bus JSON writes (to `MT5/command.json`, `config/*.json`) now use an atomic temp-file + `os.replace` pattern so partial writes can never corrupt a reader.

Channel-origin `MODIFY_SL`/`MODIFY_TP` commands (originating from a Telegram signal room rather than AURUM or the ATHENA dashboard) are dropped by BRIDGE if no scope (`group_id`, `ticket`, or `tp_stage`) is resolved. A WARNING is logged and no FORGE command is written. AURUM and dashboard MODIFY commands are unaffected — they can still issue global modifies by explicit intent.

---

## 1. One shared folder (most common failure)

**BRIDGE** writes:

- `command.json` — `MT5_CMD_FILE` (default: repo `MT5/command.json` resolved to an absolute path)
- `config.json` — `MT5_CONFIG_FILE` (refreshed **every BRIDGE loop** together with `status.json`, including **`regime_*`** keys for FORGE **v1.6.0+** native scalper — no BRIDGE restart needed for regime updates)
- Reads `market_data.json`, `broker_info.json`, etc.

**FORGE** reads/writes the **same filenames** via MQL5 `FileOpen`:

- Prefer **`FILE_COMMON`** ( **Terminal → Common → Files** )
- Falls back to **terminal-local** `MQL5/Files` (v1.2.1+ also tries local for `command.json` / `config.json` if Common misses)

If your repo folder **`signal_system/MT5/`** is a **normal directory** and **not** the same place as MT5 Common Files, then:

- BRIDGE writes `…/signal_system/MT5/command.json`
- FORGE reads `…/Common/Files/command.json`  
→ **different files** → **no execution**, while SCRIBE still has groups and the dashboard looks “queued”.

### Fix

**Option A — Symlink (recommended in SETUP)**  
Make `signal_system/MT5` a **symlink** to:

`~/Library/Application Support/MetaQuotes/Terminal/Common/Files/`

(on macOS native MT5). Then relative `MT5/command.json` in `.env` is correct.

**Option B — Absolute paths in `.env`**  
Set all of these to the **same** Common Files directory:

```bash
MT5_CMD_FILE=/full/path/to/MetaQuotes/Terminal/Common/Files/command.json
MT5_CONFIG_FILE=/full/path/to/.../config.json
MT5_MARKET_FILE=/full/path/to/.../market_data.json
MT5_BROKER_FILE=/full/path/to/.../broker_info.json
```

Restart **bridge** after changing `.env`.

**Option C — Mirror only `command.json` + `config.json` (escape hatch)**  
If you must keep a non-symlinked repo `MT5/` for some tools but FORGE reads **Common Files**, set:

```bash
MT5_CMD_FILE_MIRROR=/full/path/to/MetaQuotes/Terminal/Common/Files/command.json
```

BRIDGE writes the **same** `OPEN_GROUP` JSON to the primary `MT5_CMD_FILE` **and** to the mirror path. It also writes `config.json` next to the mirror command (same directory). You should still point `MT5_MARKET_FILE` (and ideally `MT5_CMD_FILE`) at the Common Files folder so **market_data** age and **command** stay consistent; the mirror fixes the most common “SCRIBE logs, MT5 silent” split when only command was wrong.

---

## 2. Verify quickly

0. From repo root: **`python3 scripts/verify_forge_bridge.py`** — fails if `command.json` and `market_data.json` resolve to different directories; shows `forge_version` / `ea_cycle` / age.
1. **BRIDGE log** (after restart): lines  
   `BRIDGE MT5 file paths … command.json → /absolute/path`  
   and **`MT5 file bus: FORGE → market_data`** (same folder hint; macOS symlink warning if applicable).  
2. **After TRADE_QUEUED**:  
   `BRIDGE: wrote OPEN_GROUP command.json → /same/absolute/path`
3. In **Finder** (or shell), open that path — `command.json` should exist and contain `"action":"OPEN_GROUP"`.
4. In MT5: **File → Open Data Folder** → confirm **Common → Files** (or terminal Files) is **that same directory** (or symlink target).
5. **Experts** tab: look for `FORGE command: OPEN_GROUP` and any `Failed trade … error=` (AutoTrading off, invalid stops, etc.).

---

## 3. FORGE checklist

- EA **attached** to the **XAUUSD** chart (symbol must match ladder logic).
- **AutoTrading** enabled (toolbar + EA “Allow Algo Trading”).
- **Timer** running (`OnTimer` every few seconds) — not in Strategy Tester unless you use tester file IO.
- Recompile **FORGE** after pulling v1.2.2+ (dual read + pretty JSON parsing).

---

## 4. Pretty-printed `command.json` (Python `indent=2`)

FORGE **v1.2.2+** parses JSON with spaces after colons and multi-line `entry_ladder` arrays. Older EAs expected minified `"key":"value"` and **silently skipped** commands (`timestamp` / `action` parsed empty, `entry_ladder` never found).

**v1.2.3+** prints a **Journal** message every ~20 timer cycles if `command.json` cannot be opened from Common or terminal-local Files (path mismatch hint).

## 5. No “endpoint” required

The design is **file-based**: BRIDGE is not supposed to call an HTTP endpoint on FORGE. If paths align, the EA picks up `command.json` on the next timer tick.

---

## 6. Multi-timeframe indicators (v1.2.4+)

FORGE exports indicators for 4 timeframes in `market_data.json`:

- `indicators_h1`: RSI(14), EMA20, EMA50, ATR(14), BB upper/mid/lower, MACD histogram, ADX
- `indicators_m5`, `indicators_m15`, `indicators_m30`: same fields

These update every 3 seconds (OnTimer). Python reads them via `market_view.py` (unified MarketView object) or directly from the JSON.

**Note:** After recompiling FORGE, you must **reattach** the EA in MT5 for new indicators to appear. If `indicators_m5` shows all zeros, the old .ex5 is still loaded.

## 7. Scalper JSON — defaults, generated file, Make targets

Native scalper parameters live in JSON consumed by FORGE (hot-reloaded) and by Python (**`python/bridge.py`**, etc.).

| Step | Artifact |
|------|----------|
| **Edit (source)** | **`config/scalper_config.defaults.json`** — committed baseline; optional **`.env`** **`FORGE_*`** keys merged per **`MAPPING`** in this repo’s sync script. |
| **Generate** | **`make scalper-env-sync`** or **`make forge-compile`** runs **`scripts/sync_scalper_config_from_env.py`** → writes **`config/scalper_config.json`** (stamps **`version`** from **`VERSION`**) and copies to **`MT5/`** when present. |
| **Copy only** | **`make scalper-config-sync`** — pushes **existing** `config/scalper_config.json` to Wine **Common Files** without regenerating. |

Do not hand-edit **`config/scalper_config.json`** as the source of truth; sync will overwrite it. Full rationale and tradeoffs: **`docs/SCALPER_CONFIG_PIPELINE.md`**.

## 8. Threshold hardening (v1.4.0+)

FORGE native execution now supports threshold-hardening parameters that are runtime-configurable and persisted downstream:

- `pending_entry_threshold_points`
- `trend_strength_atr_threshold`
- `breakout_buffer_points`

### Where values come from

1. FORGE defaults (`input` values in `FORGE.mq5`)
2. Generated `scalper_config.json` (from `scalper_config.defaults.json` + `.env` + `VERSION`; hot-reloaded) — see §7 above
3. BRIDGE `config.json` overrides (`MT5/config.json`)

### Where values appear

- `MT5/market_data.json` → top-level `forge_config` object
- `MT5/mode_status.json` → threshold fields for quick status reads
- `MT5/scalper_entry.json` (native entries) → threshold fields + derived metrics
- SCRIBE persistence:
  - `trade_groups.pending_entry_threshold_points`
  - `trade_groups.trend_strength_atr_threshold`
  - `trade_groups.breakout_buffer_points`
  - `market_snapshots.pending_entry_threshold_points`
  - `market_snapshots.trend_strength_atr_threshold`
  - `market_snapshots.breakout_buffer_points`

### Quick verification

```sql
SELECT id,timestamp,source,direction,pending_entry_threshold_points,trend_strength_atr_threshold,breakout_buffer_points
FROM trade_groups
WHERE source='FORGE_NATIVE_SCALP'
ORDER BY id DESC
LIMIT 10;
```

```sql
SELECT id,timestamp,source,pending_entry_threshold_points,trend_strength_atr_threshold,breakout_buffer_points
FROM market_snapshots
ORDER BY id DESC
LIMIT 10;
```

If older rows show `NULL`, that usually means they were written before BRIDGE/SCRIBE was reloaded with the threshold-forwarding code.

## 9. Weekend / OFF_HOURS behavior

If `status.json` shows `session=OFF_HOURS` and MT5 quotes are flat (bid/ask not moving), orders may queue but not fill until market reopen.
Treat this as market-state behavior, not automatically as FORGE/BRIDGE failure.

## 10. Position tracker

BRIDGE tracks individual position fills and closes by diffing `open_positions` and `pending_orders` against SCRIBE each tick.
- `forge_managed=true` positions follow standard strategy lifecycle:
  - New tickets → `log_trade_position()`
  - Disappeared tickets → `close_trade_position()` using broker close-deal metadata first (`recent_closed_deals`) and SL/TP inference fallback when broker hints are unavailable
  - Group totals auto-rollup when all exposure is gone
- `forge_managed=false` positions (manual/non-FORGE) are still logged:
  - synthetic `trade_groups.source='MANUAL_MT5'`
  - `trade_positions` + `trade_closures` rows
  - `UNMANAGED_POSITION_OPEN` / `UNMANAGED_POSITION_CLOSED` audit events in `system_events`

## 11. FORGE journal → SCRIBE (live vs tester)

BRIDGE periodically (**~60s**) calls **`Scribe.sync_forge_journal()`** and **`sync_forge_journal_trades()`** for every path returned by **`_resolve_forge_journal_paths()`** (live Common Files + recursive **MetaTrader 5** tree, including Strategy Tester **Agent-*/MQL5/Files**).

| Source | Path hint | Synced to AURUM by default? |
|--------|-----------|------------------------------|
| **Live** | `FORGE_journal_<SYMBOL>.db` (no `_tester` in filename) | **Yes** — rows go to **`forge_signals`** / **`forge_journal_trades`** with **`journal_source='live'`**. |
| **Tester** | `FORGE_journal_<SYMBOL>_tester.db` | **No** — skipped unless **`BRIDGE_SYNC_TESTER_JOURNAL=1`** in **`.env`**. Tester DBs are **ML/backtest ground truth**; query them directly with **`sqlite3`** (see **`docs/FORGE_TESTER_JOURNAL_QUERIES.md`**, **`make journal-diagnose`**). Syncing them into the same SCRIBE DB as live can **pollute** analytics and duplicate keys across runs. |

**Override (debug only):** set **`BRIDGE_SYNC_TESTER_JOURNAL=1`** (`true` / `yes` / `on`) and **`make reload-bridge`**. Synced tester rows use **`journal_source='tester'`** and a per-run **`run_id`** (from FORGE **`SIGNALS.run_id`** / **`TRADES.run_id`**) so **`UNIQUE(deal_ticket, journal_source, run_id)`** on **`forge_journal_trades`** can admit the same broker deal index across different backtest runs.

**SCRIBE contract:** **`forge_signals`** and **`forge_journal_trades`** both support **`run_id`** (live rows keep **`run_id=0`**). See **`docs/DATA_CONTRACT.md`** and **`docs/SCRIBE_QUERY_EXAMPLES.md`**.

## Related

- [SETUP.md](SETUP.md) — MT5 paths, symlink, `make forge-ea`
- [OPERATIONS.md](OPERATIONS.md) — `make restart` after `.env`
- [CLI_API_CHEATSHEET.md](CLI_API_CHEATSHEET.md) — curl + python one-liners for all API endpoints
