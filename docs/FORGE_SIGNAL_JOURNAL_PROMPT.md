# FORGE Native SQLite Signal Journal — Implementation Prompt

> **Self-contained prompt.** Follow every step exactly. No user input needed.
> **Goal:** Add an EA-side SQLite journal that records every signal FORGE evaluates
> — both taken and skipped — with the gate/reason, market context, and outcome.
> A Python sync script bridges FORGE's journal DB into SCRIBE so all data is
> queryable from ATHENA alongside trade_groups and market_snapshots.
> **Context:** Currently FORGE only writes `scalper_entry.json` for *executed* trades.
> Skipped setups (session, cooldown, spread, direction_cooldown, etc.) are only in
> the Journal log (ephemeral, not queryable). This journal captures that data.
> **Ref:** [MQL5 Article 22009 — "Algorithmic Trading Without the Routine: Quick Trade Analysis in MetaTrader 5 with SQLite"](https://www.mql5.com/en/articles/22009)

---

## 1. Architecture

```
FORGE (MQL5)                           Python pipeline
─────────────                          ──────────────
FORGE_journal_XAUUSD.db               aurum_intelligence.db (SCRIBE)
├─ SIGNALS (taken + skipped)   ──sync──>  forge_signals (new table)
├─ TRADES (MT5 deal history)            ├─ trade_groups (existing)
└─ STATS_CACHE (hourly WR etc)          ├─ trade_closures (existing)
                                        ├─ market_snapshots (existing)
                                        └─ ...
```

**Two databases, clear roles:**
- **FORGE journal** (`FORGE_journal_XAUUSD.db` in Common Files) — EA-side, works
  in tester too, FORGE can self-analyze without Python
- **SCRIBE** (`aurum_intelligence.db`) — single operational DB, BRIDGE/ATHENA
  query here. Sync script copies new signals from FORGE journal → SCRIBE's
  `forge_signals` table so you can JOIN with `trade_groups`

---

## 2. Files to modify

| File | What changes |
|------|-------------|
| `ea/FORGE.mq5` | SQLite journal: init, insert signals, import trades, stats queries |
| `config/scalper_config.json` | New `journal` section |
| `.env.example` | Document new env vars |
| `scripts/sync_scalper_config_from_env.py` | New MAPPING entries |
| `python/scribe.py` | New `forge_signals` table DDL + migration + `sync_forge_journal()` method |
| `python/bridge.py` | Periodic call to `scribe.sync_forge_journal()` |

---

## 3. FORGE-side (MQL5) implementation

### Step 3.1 — ScalperConfig struct additions

**Add new fields** in ScalperConfig struct (after PSAR fields, before `};`):

```mql5
   // V2: Signal Journal (SQLite)
   bool   journal_enabled;
   bool   journal_record_skips;
   bool   journal_import_trades;
   int    journal_import_depth_days;
   int    journal_stats_interval_sec;
```

### Step 3.2 — Global variables

**Add after existing PSAR globals:**

```mql5
// ── Signal Journal (SQLite) ──────────────────────────────────────
int      g_journal_db = INVALID_HANDLE;
datetime g_journal_last_import = 0;
datetime g_journal_last_stats = 0;
int      g_journal_signals_count = 0;
```

### Step 3.3 — InitScalperConfig defaults

**Add after PSAR defaults:**

```mql5
   g_sc.journal_enabled = true;
   g_sc.journal_record_skips = true;
   g_sc.journal_import_trades = true;
   g_sc.journal_import_depth_days = 30;
   g_sc.journal_stats_interval_sec = 300;
```

### Step 3.4 — ReadScalperConfig JSON parsing

**Add after PSAR parsing block:**

```mql5
   if(JsonHasKey(content, "journal_enabled")) {
      v = JsonGetDouble(content, "journal_enabled");
      g_sc.journal_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "journal_record_skips")) {
      v = JsonGetDouble(content, "journal_record_skips");
      g_sc.journal_record_skips = (v >= 0.5);
   }
   if(JsonHasKey(content, "journal_import_trades")) {
      v = JsonGetDouble(content, "journal_import_trades");
      g_sc.journal_import_trades = (v >= 0.5);
   }
   if(JsonHasKey(content, "journal_import_depth_days")) {
      v = JsonGetDouble(content, "journal_import_depth_days");
      if(v >= 1 && v <= 365) g_sc.journal_import_depth_days = (int)v;
   }
   if(JsonHasKey(content, "journal_stats_interval_sec")) {
      v = JsonGetDouble(content, "journal_stats_interval_sec");
      if(v >= 60 && v <= 3600) g_sc.journal_stats_interval_sec = (int)v;
   }
```

### Step 3.5 — ReadScalperConfig diagnostics

**Add after existing QUALITY diagnostics PrintFormat:**

```mql5
   PrintFormat("FORGE V2 JOURNAL: enabled=%s skips=%s import=%s depth=%dd stats=%ds",
               g_sc.journal_enabled ? "true" : "false",
               g_sc.journal_record_skips ? "true" : "false",
               g_sc.journal_import_trades ? "true" : "false",
               g_sc.journal_import_depth_days,
               g_sc.journal_stats_interval_sec);
```

### Step 3.6 — Database initialization and close

**Add new function block** (before `CheckNativeScalperSetups`):

```mql5
// ── Signal Journal: SQLite database ─────────────────────────────
// Ref: MQL5 Article 22009 — "Algorithmic Trading Without the Routine"
//      https://www.mql5.com/en/articles/22009

bool JournalInit() {
   if(!g_sc.journal_enabled) return true;
   if(g_journal_db != INVALID_HANDLE) return true;

   string db_name = "FORGE_journal_" + _Symbol + ".db";
   g_journal_db = DatabaseOpen(db_name, DATABASE_OPEN_READWRITE | DATABASE_OPEN_CREATE
                               | DATABASE_OPEN_COMMON);
   if(g_journal_db == INVALID_HANDLE) {
      PrintFormat("FORGE JOURNAL: failed to open %s — error=%d", db_name, GetLastError());
      return false;
   }

   string sql_signals =
      "CREATE TABLE IF NOT EXISTS SIGNALS ("
      "id INTEGER PRIMARY KEY AUTOINCREMENT, "
      "time INTEGER NOT NULL, "
      "symbol TEXT NOT NULL, "
      "setup_type TEXT, "
      "direction TEXT, "
      "outcome TEXT NOT NULL, "
      "gate_reason TEXT, "
      "price REAL, "
      "spread REAL, "
      "atr REAL, "
      "rsi REAL, "
      "adx REAL, "
      "bb_upper REAL, "
      "bb_lower REAL, "
      "bb_mid REAL, "
      "poc_price REAL, "
      "vwap_price REAL, "
      "fib_50 REAL, "
      "rsi_divergence TEXT, "
      "psar_state TEXT, "
      "pattern_score INTEGER, "
      "h1_trend REAL, "
      "regime_label TEXT, "
      "regime_confidence REAL, "
      "adx_trend_regime INTEGER, "
      "high_vol_trend INTEGER, "
      "session TEXT, "
      "magic INTEGER, "
      "synced INTEGER DEFAULT 0"
      ");";

   string sql_trades =
      "CREATE TABLE IF NOT EXISTS TRADES ("
      "id INTEGER PRIMARY KEY AUTOINCREMENT, "
      "deal_ticket INTEGER UNIQUE, "
      "order_ticket INTEGER, "
      "symbol TEXT NOT NULL, "
      "type INTEGER, "
      "direction INTEGER, "
      "volume REAL, "
      "price REAL, "
      "profit REAL, "
      "swap REAL, "
      "commission REAL, "
      "sl REAL, "
      "tp REAL, "
      "magic INTEGER, "
      "comment TEXT, "
      "time INTEGER, "
      "time_msc INTEGER"
      ");";

   string sql_stats =
      "CREATE TABLE IF NOT EXISTS STATS_CACHE ("
      "id INTEGER PRIMARY KEY AUTOINCREMENT, "
      "computed_at INTEGER, "
      "key TEXT UNIQUE, "
      "value REAL"
      ");";

   if(!DatabaseExecute(g_journal_db, sql_signals)) {
      PrintFormat("FORGE JOURNAL: SIGNALS table error=%d", GetLastError());
      return false;
   }
   if(!DatabaseExecute(g_journal_db, sql_trades)) {
      PrintFormat("FORGE JOURNAL: TRADES table error=%d", GetLastError());
      return false;
   }
   if(!DatabaseExecute(g_journal_db, sql_stats)) {
      PrintFormat("FORGE JOURNAL: STATS_CACHE table error=%d", GetLastError());
      return false;
   }

   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_time ON SIGNALS(time);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_outcome ON SIGNALS(outcome);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_gate ON SIGNALS(gate_reason);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_setup ON SIGNALS(setup_type);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_synced ON SIGNALS(synced);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_trades_time ON TRADES(time);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_trades_magic ON TRADES(magic);");

   PrintFormat("FORGE JOURNAL: database opened — %s", db_name);
   return true;
}

void JournalClose() {
   if(g_journal_db != INVALID_HANDLE) {
      DatabaseClose(g_journal_db);
      g_journal_db = INVALID_HANDLE;
      Print("FORGE JOURNAL: database closed");
   }
}
```

**Note the `synced INTEGER DEFAULT 0` column** in SIGNALS — this is the bridge.
The Python sync script reads rows where `synced=0`, inserts them into SCRIBE's
`forge_signals` table, then marks them `synced=1`. This avoids re-processing.

### Step 3.7 — Signal recording function

**Add after `JournalClose()`:**

```mql5
void JournalRecordSignal(string outcome, string gate_reason,
                         string setup_type, string direction,
                         double price, double spread, double atr,
                         double rsi, double adx,
                         double bb_u, double bb_l, double bb_m,
                         int pattern_score, double h1_trend,
                         int high_vol_trend_flag) {
   if(g_journal_db == INVALID_HANDLE) return;
   if(outcome == "SKIP" && !g_sc.journal_record_skips) return;

   MqlDateTime dt;
   TimeGMT(dt);
   int h = dt.hour;
   string session = "ASIAN";
   if(h >= g_sc.london_start && h < g_sc.london_end) session = "LONDON";
   else if(h >= g_sc.ny_start && h < g_sc.ny_end) session = "NY";

   string sql = "INSERT INTO SIGNALS "
      "(time, symbol, setup_type, direction, outcome, gate_reason, "
      "price, spread, atr, rsi, adx, bb_upper, bb_lower, bb_mid, "
      "poc_price, vwap_price, fib_50, rsi_divergence, psar_state, "
      "pattern_score, h1_trend, regime_label, regime_confidence, "
      "adx_trend_regime, high_vol_trend, session, magic, synced) "
      "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)";

   int stmt = DatabasePrepare(g_journal_db, sql);
   if(stmt == INVALID_HANDLE) return;

   DatabaseBind(stmt, 0, (long)TimeCurrent());
   DatabaseBind(stmt, 1, _Symbol);
   DatabaseBind(stmt, 2, setup_type);
   DatabaseBind(stmt, 3, direction);
   DatabaseBind(stmt, 4, outcome);
   DatabaseBind(stmt, 5, gate_reason);
   DatabaseBind(stmt, 6, price);
   DatabaseBind(stmt, 7, spread);
   DatabaseBind(stmt, 8, atr);
   DatabaseBind(stmt, 9, rsi);
   DatabaseBind(stmt, 10, adx);
   DatabaseBind(stmt, 11, bb_u);
   DatabaseBind(stmt, 12, bb_l);
   DatabaseBind(stmt, 13, bb_m);
   DatabaseBind(stmt, 14, g_poc_price);
   DatabaseBind(stmt, 15, g_vwap_price);
   DatabaseBind(stmt, 16, g_fib_50);
   DatabaseBind(stmt, 17, g_rsi_div_type);
   DatabaseBind(stmt, 18, g_psar_state);
   DatabaseBind(stmt, 19, pattern_score);
   DatabaseBind(stmt, 20, h1_trend);
   DatabaseBind(stmt, 21, g_regime_label);
   DatabaseBind(stmt, 22, g_regime_confidence);
   DatabaseBind(stmt, 23, g_adx_trend_regime ? 1 : 0);
   DatabaseBind(stmt, 24, high_vol_trend_flag);
   DatabaseBind(stmt, 25, session);
   DatabaseBind(stmt, 26, (long)MagicNumber);

   DatabaseRead(stmt);
   DatabaseFinalize(stmt);
   g_journal_signals_count++;
}
```

### Step 3.8 — Trade history import function

**Add after `JournalRecordSignal()`:**

```mql5
void JournalImportTrades() {
   if(g_journal_db == INVALID_HANDLE || !g_sc.journal_import_trades) return;

   datetime now = TimeCurrent();
   if(g_journal_last_import > 0 && (now - g_journal_last_import) < 300) return;
   g_journal_last_import = now;

   datetime from_date = now - g_sc.journal_import_depth_days * 86400;
   if(!HistorySelect(from_date, now)) return;

   int total = HistoryDealsTotal();
   int imported = 0;

   DatabaseExecute(g_journal_db, "BEGIN TRANSACTION;");

   for(int i = 0; i < total; i++) {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0) continue;

      ENUM_DEAL_TYPE dtype = (ENUM_DEAL_TYPE)HistoryDealGetInteger(ticket, DEAL_TYPE);
      if(dtype == DEAL_TYPE_BALANCE || dtype == DEAL_TYPE_CREDIT) continue;

      long magic = HistoryDealGetInteger(ticket, DEAL_MAGIC);
      if(magic < MagicNumber || magic > MagicNumber + 9999) continue;

      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY);
      int dir = 0;
      if(entry == DEAL_ENTRY_OUT) dir = 1;
      else if(entry == DEAL_ENTRY_INOUT) dir = 2;
      else if(entry == DEAL_ENTRY_OUT_BY) dir = 3;

      string sql = "INSERT OR IGNORE INTO TRADES "
         "(deal_ticket, order_ticket, symbol, type, direction, volume, price, "
         "profit, swap, commission, magic, comment, time, time_msc) "
         "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";

      int stmt = DatabasePrepare(g_journal_db, sql);
      if(stmt == INVALID_HANDLE) continue;

      DatabaseBind(stmt, 0, (long)ticket);
      DatabaseBind(stmt, 1, (long)HistoryDealGetInteger(ticket, DEAL_ORDER));
      DatabaseBind(stmt, 2, HistoryDealGetString(ticket, DEAL_SYMBOL));
      DatabaseBind(stmt, 3, (int)dtype);
      DatabaseBind(stmt, 4, dir);
      DatabaseBind(stmt, 5, HistoryDealGetDouble(ticket, DEAL_VOLUME));
      DatabaseBind(stmt, 6, HistoryDealGetDouble(ticket, DEAL_PRICE));
      DatabaseBind(stmt, 7, HistoryDealGetDouble(ticket, DEAL_PROFIT));
      DatabaseBind(stmt, 8, HistoryDealGetDouble(ticket, DEAL_SWAP));
      DatabaseBind(stmt, 9, HistoryDealGetDouble(ticket, DEAL_COMMISSION));
      DatabaseBind(stmt, 10, magic);
      DatabaseBind(stmt, 11, HistoryDealGetString(ticket, DEAL_COMMENT));
      DatabaseBind(stmt, 12, (long)HistoryDealGetInteger(ticket, DEAL_TIME));
      DatabaseBind(stmt, 13, (long)HistoryDealGetInteger(ticket, DEAL_TIME_MSC));

      DatabaseRead(stmt);
      DatabaseFinalize(stmt);
      imported++;
   }

   DatabaseExecute(g_journal_db, "COMMIT;");

   if(imported > 0)
      PrintFormat("FORGE JOURNAL: imported %d deals", imported);
}
```

### Step 3.9 — Stats computation function

**Add after `JournalImportTrades()`:**

```mql5
void JournalComputeStats() {
   if(g_journal_db == INVALID_HANDLE) return;

   datetime now = TimeCurrent();
   if(g_journal_last_stats > 0 &&
      (now - g_journal_last_stats) < g_sc.journal_stats_interval_sec) return;
   g_journal_last_stats = now;

   string sql_hr = "SELECT "
      "CAST(strftime('%H', time, 'unixepoch') AS INTEGER) as hour, "
      "COUNT(*) as trades, "
      "SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins, "
      "SUM(profit + swap + commission) as net_pnl "
      "FROM TRADES WHERE direction IN (1,2,3) "
      "GROUP BY hour ORDER BY hour";

   int stmt = DatabasePrepare(g_journal_db, sql_hr);
   if(stmt != INVALID_HANDLE) {
      DatabaseExecute(g_journal_db, "DELETE FROM STATS_CACHE WHERE key LIKE 'hour_%'");
      while(DatabaseRead(stmt)) {
         int hour_val; double trades_d, wins_d, pnl;
         DatabaseColumnInteger(stmt, 0, hour_val);
         DatabaseColumnDouble(stmt, 1, trades_d);
         DatabaseColumnDouble(stmt, 2, wins_d);
         DatabaseColumnDouble(stmt, 3, pnl);
         double wr = (trades_d > 0) ? (wins_d / trades_d * 100.0) : 0;

         string keys[] = {
            StringFormat("hour_%02d_winrate", hour_val),
            StringFormat("hour_%02d_pnl", hour_val),
            StringFormat("hour_%02d_trades", hour_val)
         };
         double vals[] = { wr, pnl, trades_d };

         for(int k = 0; k < 3; k++) {
            int us = DatabasePrepare(g_journal_db,
               "INSERT OR REPLACE INTO STATS_CACHE (computed_at, key, value) VALUES (?, ?, ?)");
            if(us != INVALID_HANDLE) {
               DatabaseBind(us, 0, (long)now);
               DatabaseBind(us, 1, keys[k]);
               DatabaseBind(us, 2, vals[k]);
               DatabaseRead(us);
               DatabaseFinalize(us);
            }
         }
      }
      DatabaseFinalize(stmt);
   }

   string sql_gates = "SELECT gate_reason, COUNT(*) as cnt "
      "FROM SIGNALS WHERE outcome='SKIP' AND gate_reason != '' "
      "GROUP BY gate_reason ORDER BY cnt DESC";

   stmt = DatabasePrepare(g_journal_db, sql_gates);
   if(stmt != INVALID_HANDLE) {
      DatabaseExecute(g_journal_db, "DELETE FROM STATS_CACHE WHERE key LIKE 'gate_%'");
      while(DatabaseRead(stmt)) {
         string gate; double cnt;
         DatabaseColumnText(stmt, 0, gate);
         DatabaseColumnDouble(stmt, 1, cnt);
         int us = DatabasePrepare(g_journal_db,
            "INSERT OR REPLACE INTO STATS_CACHE (computed_at, key, value) VALUES (?, ?, ?)");
         if(us != INVALID_HANDLE) {
            DatabaseBind(us, 0, (long)now);
            DatabaseBind(us, 1, "gate_" + gate);
            DatabaseBind(us, 2, cnt);
            DatabaseRead(us);
            DatabaseFinalize(us);
         }
      }
      DatabaseFinalize(stmt);
   }

   PrintFormat("FORGE JOURNAL: stats refreshed — %d signals this session", g_journal_signals_count);
}
```

### Step 3.10 — Integration points in FORGE.mq5

**OnInit** — add after `InitScalperConfig();`:
```mql5
   JournalInit();
```

**OnDeinit** — add before final Print:
```mql5
   JournalClose();
```

**OnTimer** — add after `DetectPSARState();`:
```mql5
   if(g_sc.journal_enabled) {
      JournalImportTrades();
      JournalComputeStats();
   }
```

**CheckNativeScalperSetups gate points** — at each gate's `return;`, add a
`JournalRecordSignal()` call before the return. The 8 instrumentation points:

| Gate | outcome | gate_reason | Context available |
|------|---------|-------------|-------------------|
| session_blocked | SKIP | session_off | price, spread only |
| spread | SKIP | spread | price, spread only |
| open_groups | SKIP | open_groups | price, spread only |
| cooldown | SKIP | cooldown | price, spread only |
| direction_cooldown | SKIP | direction_cooldown | full indicators |
| m1 | SKIP | m1 | full indicators |
| regime_countertrend | SKIP | regime_countertrend | full indicators |
| Trade executed | TAKEN | (empty) | full indicators |

Early gates (session, spread, open_groups, cooldown) fire before indicators are
read, so context fields are zeroed. Later gates have full context. Pass `0` for
the `high_vol_trend_flag` at early gates; compute it where available.

### Step 3.11 — Config file updates

**scalper_config.json** — add new `journal` section after `safety`, before `dd_event_tp`:

```json
  "journal": {
    "journal_enabled": 1,
    "journal_record_skips": 1,
    "journal_import_trades": 1,
    "journal_import_depth_days": 30,
    "journal_stats_interval_sec": 300
  },
```

### Step 3.12 — .env.example

**Add after trade quality env vars:**

```
# Native SQLite signal journal (records every setup FORGE evaluates):
# FORGE_JOURNAL_ENABLED=1
# FORGE_JOURNAL_RECORD_SKIPS=1
# FORGE_JOURNAL_IMPORT_TRADES=1
# FORGE_JOURNAL_IMPORT_DEPTH_DAYS=30
# FORGE_JOURNAL_STATS_INTERVAL_SEC=300
```

### Step 3.13 — sync_scalper_config_from_env.py MAPPING

**Add after direction cooldown entries:**

```python
    "FORGE_JOURNAL_ENABLED": ("journal", "journal_enabled", "bool01", None, None),
    "FORGE_JOURNAL_RECORD_SKIPS": ("journal", "journal_record_skips", "bool01", None, None),
    "FORGE_JOURNAL_IMPORT_TRADES": ("journal", "journal_import_trades", "bool01", None, None),
    "FORGE_JOURNAL_IMPORT_DEPTH_DAYS": ("journal", "journal_import_depth_days", "int", 1.0, 365.0),
    "FORGE_JOURNAL_STATS_INTERVAL_SEC": ("journal", "journal_stats_interval_sec", "int", 60.0, 3600.0),
```

---

## 4. Python-side: SCRIBE sync

### Step 4.1 — SCRIBE DDL + migration

**In `python/scribe.py`**, add to the DDL block (after `market_snapshots` CREATE):

```sql
CREATE TABLE IF NOT EXISTS forge_signals (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    forge_id          INTEGER,
    time              INTEGER NOT NULL,
    timestamp_utc     TEXT NOT NULL,
    symbol            TEXT NOT NULL,
    setup_type        TEXT,
    direction         TEXT,
    outcome           TEXT NOT NULL,
    gate_reason       TEXT,
    price             REAL,
    spread            REAL,
    atr               REAL,
    rsi               REAL,
    adx               REAL,
    bb_upper          REAL,
    bb_lower          REAL,
    bb_mid            REAL,
    poc_price         REAL,
    vwap_price        REAL,
    fib_50            REAL,
    rsi_divergence    TEXT,
    psar_state        TEXT,
    pattern_score     INTEGER,
    h1_trend          REAL,
    regime_label      TEXT,
    regime_confidence REAL,
    adx_trend_regime  INTEGER,
    high_vol_trend    INTEGER,
    session           TEXT,
    magic             INTEGER
);
```

**Add migration** in `_run_migrations()` (after psar_state migration):

```python
        # forge_signals table
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "forge_signals" not in tables:
            conn.execute(FORGE_SIGNALS_DDL)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fs_time ON forge_signals(time)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fs_outcome ON forge_signals(outcome)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fs_gate ON forge_signals(gate_reason)")
            log.info("SCRIBE migration: created forge_signals table")
```

### Step 4.2 — SCRIBE sync method

**Add to `class Scribe`:**

```python
    def sync_forge_journal(self, journal_db_path: str) -> int:
        """Read unsynced SIGNALS from FORGE journal DB, insert into forge_signals,
        then mark them synced=1 in the source DB. Returns count of synced rows."""
        if not Path(journal_db_path).exists():
            return 0

        import sqlite3 as _sqlite3
        try:
            src = _sqlite3.connect(journal_db_path, timeout=5)
        except Exception as e:
            log.warning("SCRIBE sync_forge_journal: cannot open %s — %s", journal_db_path, e)
            return 0

        try:
            rows = src.execute(
                "SELECT id, time, symbol, setup_type, direction, outcome, gate_reason, "
                "price, spread, atr, rsi, adx, bb_upper, bb_lower, bb_mid, "
                "poc_price, vwap_price, fib_50, rsi_divergence, psar_state, "
                "pattern_score, h1_trend, regime_label, regime_confidence, "
                "adx_trend_regime, high_vol_trend, session, magic "
                "FROM SIGNALS WHERE synced = 0 ORDER BY id LIMIT 500"
            ).fetchall()

            if not rows:
                return 0

            from datetime import datetime, timezone
            synced_ids = []
            with self._conn() as c:
                for r in rows:
                    ts_utc = datetime.fromtimestamp(r[1], tz=timezone.utc).isoformat()
                    c.execute(
                        "INSERT INTO forge_signals "
                        "(forge_id, time, timestamp_utc, symbol, setup_type, direction, "
                        "outcome, gate_reason, price, spread, atr, rsi, adx, "
                        "bb_upper, bb_lower, bb_mid, poc_price, vwap_price, fib_50, "
                        "rsi_divergence, psar_state, pattern_score, h1_trend, "
                        "regime_label, regime_confidence, adx_trend_regime, "
                        "high_vol_trend, session, magic) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (r[0], r[1], ts_utc, *r[2:])
                    )
                    synced_ids.append(r[0])

            if synced_ids:
                placeholders = ",".join(str(i) for i in synced_ids)
                src.execute(f"UPDATE SIGNALS SET synced = 1 WHERE id IN ({placeholders})")
                src.commit()
                log.info("SCRIBE: synced %d forge journal signals", len(synced_ids))

            return len(synced_ids)
        except Exception as e:
            log.warning("SCRIBE sync_forge_journal error: %s", e)
            return 0
        finally:
            src.close()
```

### Step 4.3 — BRIDGE periodic sync call

**In `python/bridge.py`**, add to the main loop (in the same timer block
that calls `_check_forge_scalper_entry`):

```python
        # Sync FORGE signal journal → SCRIBE (every 60s)
        _now = time.time()
        if _now - getattr(self, "_last_journal_sync", 0) >= 60:
            self._last_journal_sync = _now
            journal_path = self._resolve_forge_journal_path()
            if journal_path:
                synced = self.scribe.sync_forge_journal(journal_path)
                if synced:
                    log.info("BRIDGE: synced %d FORGE journal signals to SCRIBE", synced)
```

**Helper to find the journal DB:**

```python
    def _resolve_forge_journal_path(self) -> str | None:
        """Find FORGE_journal_*.db in MT5 Common Files directory."""
        import glob
        common_dir = os.path.join(
            os.path.expanduser("~/Library/Application Support"),
            "MetaQuotes", "Terminal", "Common", "Files"
        )
        if not os.path.isdir(common_dir):
            return None
        matches = glob.glob(os.path.join(common_dir, "FORGE_journal_*.db"))
        return matches[0] if matches else None
```

---

## 5. Database location

FORGE journal: **MT5 Common Files** directory (`DATABASE_OPEN_COMMON` flag).
File: `FORGE_journal_XAUUSD.db` (symbol-specific).

BRIDGE finds it via glob in `~/Library/Application Support/MetaQuotes/Terminal/Common/Files/`.

---

## 6. Sync flow

```
Every tick (FORGE):
  Gate hit? → JournalRecordSignal("SKIP", gate, ...) → INSERT into SIGNALS (synced=0)
  Trade executed? → JournalRecordSignal("TAKEN", ...) → INSERT into SIGNALS (synced=0)

Every 5 min (FORGE OnTimer):
  JournalImportTrades() → INSERT OR IGNORE into TRADES
  JournalComputeStats() → UPDATE STATS_CACHE

Every 60s (BRIDGE loop):
  scribe.sync_forge_journal(path)
    → SELECT ... FROM SIGNALS WHERE synced=0 LIMIT 500
    → INSERT into SCRIBE forge_signals
    → UPDATE SIGNALS SET synced=1
```

---

## 7. Querying combined data in SCRIBE

Once synced, you can query SCRIBE's single DB:

**Gate hit frequency:**
```sql
SELECT gate_reason, COUNT(*) as cnt,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM forge_signals), 1) as pct
FROM forge_signals WHERE outcome='SKIP'
GROUP BY gate_reason ORDER BY cnt DESC;
```

**Join signals with trade outcomes:**
```sql
SELECT fs.setup_type, fs.direction, fs.session,
       COUNT(*) as taken,
       tg.total_pnl, tg.win_count, tg.loss_count
FROM forge_signals fs
LEFT JOIN trade_groups tg ON tg.source = 'FORGE_SCALP'
  AND ABS(fs.time - CAST(strftime('%s', tg.open_time) AS INTEGER)) < 10
WHERE fs.outcome = 'TAKEN'
GROUP BY fs.setup_type, fs.direction;
```

**Skipped signals that would have been profitable:**
```sql
SELECT fs.gate_reason, fs.direction, fs.setup_type,
       fs.price, fs.atr, fs.session
FROM forge_signals fs
WHERE fs.outcome = 'SKIP'
  AND fs.gate_reason = 'direction_cooldown'
ORDER BY fs.time DESC LIMIT 20;
```

---

## 8. Bump VERSION

After implementation:

```bash
echo "2.4.0" > VERSION
make forge-compile
```

Update `CHANGELOG.md` with a `[2.4.0]` section.

---

## 9. Verification checklist

1. **Compile:** `make forge-compile` — must succeed.
2. **Config sync:** `python3 scripts/sync_scalper_config_from_env.py` — verify
   journal fields appear.
3. **Backtest:** Run a short backtest. After completion:
   - Open MetaEditor → Databases → `FORGE_journal_XAUUSD.db`
   - Run `SELECT outcome, COUNT(*) FROM SIGNALS GROUP BY outcome;`
   - Expect both SKIP and TAKEN rows
4. **Live sync:** Start BRIDGE, wait 60s, then query SCRIBE:
   ```sql
   SELECT COUNT(*) FROM forge_signals;
   ```
5. **Journal logs:** Look for `FORGE JOURNAL: database opened` and
   `FORGE JOURNAL: stats refreshed` in MT5 Journal.
6. **BRIDGE logs:** Look for `BRIDGE: synced N FORGE journal signals to SCRIBE`.

---

*End of prompt.*
