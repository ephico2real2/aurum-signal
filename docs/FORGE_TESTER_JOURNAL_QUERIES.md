# FORGE Tester Journal — Operational Query Reference

DB location (macOS Wine):
```
$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/
  drive_c/Program Files/MetaTrader 5/Tester/Agent-127.0.0.1-3000/MQL5/Files/
  FORGE_journal_XAUUSD_tester.db
```

Set the DB variable once before running any query:
```bash
DB=$(find "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5" \
  -name "FORGE_journal_*_tester.db" 2>/dev/null | head -1)
```

---

## Workflow

```bash
# 1. Reset before a fresh test series
make journal-reset-tester

# 2. Re-attach FORGE in MT5, run backtest

# 3. Verify after backtest
```

---

## Run Identification

```bash
# All runs — wall_time is real clock (unique per run), sim_start_time is backtest period start
sqlite3 "$DB" "SELECT id, wall_time, datetime(sim_start_time,'unixepoch') as sim_start,
  scalper_mode, warmup_m5_bars, magic_base FROM TESTER_RUNS;"
```

---

## Signal Counts

```bash
# Total signals per run broken down by outcome
sqlite3 "$DB" "SELECT run_id, outcome, COUNT(*) as cnt
  FROM SIGNALS GROUP BY run_id, outcome ORDER BY run_id, outcome;"

# TAKEN entries only (trades actually opened)
sqlite3 "$DB" "SELECT run_id, COUNT(*) as taken
  FROM SIGNALS WHERE outcome='TAKEN' GROUP BY run_id;"
```

---

## Latest Signals — with Price and Indicators

```bash
# Last 10 signals with price, RSI, ADX (use during or after backtest)
sqlite3 "$DB" "SELECT id, run_id, datetime(time,'unixepoch') as ts,
  outcome, gate_reason, setup_type, direction, price, rsi, adx
  FROM SIGNALS ORDER BY id DESC LIMIT 10;"
```

---

## Skip Reason Breakdown

```bash
# Skip reasons for the latest run
sqlite3 "$DB" "SELECT gate_reason, COUNT(*) as cnt
  FROM SIGNALS
  WHERE outcome='SKIP' AND run_id = (SELECT MAX(id) FROM TESTER_RUNS)
  GROUP BY gate_reason ORDER BY cnt DESC;"
```

---

## TAKEN Entries Detail

```bash
# All TAKEN entries for the latest run
sqlite3 "$DB" "SELECT id, datetime(time,'unixepoch') as ts, setup_type,
  direction, price, rsi, adx, session
  FROM SIGNALS
  WHERE outcome='TAKEN' AND run_id = (SELECT MAX(id) FROM TESTER_RUNS)
  ORDER BY time;"
```

---

## Trade Results (Closed Deals)

```bash
# Closed deals for the latest run (requires journal_import_trades=true in scalper_config)
sqlite3 "$DB" "SELECT run_id, COUNT(*) as deals,
  SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
  SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losses,
  ROUND(SUM(profit),2) as total_pnl
  FROM TRADES WHERE direction IN (1,2,3)
  AND run_id = (SELECT MAX(id) FROM TESTER_RUNS);"
```

---

## Cross-Run Comparison

```bash
# Compare TAKEN counts across all runs
sqlite3 "$DB" "SELECT r.id, r.wall_time, r.scalper_mode, r.warmup_m5_bars,
  COUNT(CASE WHEN s.outcome='TAKEN' THEN 1 END) as taken,
  COUNT(*) as total_signals
  FROM TESTER_RUNS r
  LEFT JOIN SIGNALS s ON s.run_id = r.id
  GROUP BY r.id ORDER BY r.id;"
```

---

## AURUM Sync Verification (after BRIDGE picks up the journal)

```bash
# Check synced signals in AURUM
sqlite3 python/data/aurum_intelligence.db \
  "SELECT run_id, outcome, COUNT(*) as cnt
   FROM forge_signals WHERE journal_source='tester'
   GROUP BY run_id, outcome ORDER BY run_id, outcome;"

# Check synced trades in AURUM — per-run P&L
sqlite3 python/data/aurum_intelligence.db \
  "SELECT run_id, COUNT(*) as deals,
   SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
   SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losses,
   ROUND(SUM(profit),2) as total_pnl
   FROM forge_journal_trades WHERE journal_source='tester'
   GROUP BY run_id ORDER BY run_id;"
```
