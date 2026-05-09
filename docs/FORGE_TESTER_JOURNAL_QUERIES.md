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
# Last 10 signals with all indicators (use during or after backtest)
sqlite3 -header -column "$DB" "SELECT id, run_id, datetime(time,'unixepoch') as ts,
  outcome, gate_reason, setup_type, direction,
  ROUND(price,2) as px, ROUND(rsi,1) as rsi, ROUND(adx,1) as adx, ROUND(atr,2) as atr,
  ROUND(spread,1) as spread, session, ROUND(h1_trend,3) as h1_trend
  FROM SIGNALS ORDER BY id DESC LIMIT 10;"
```

---

## Skip Reason Breakdown

```bash
# Skip reasons for the latest run — all gates
sqlite3 -header -column "$DB" "SELECT gate_reason, COUNT(*) as cnt
  FROM SIGNALS
  WHERE outcome='SKIP' AND run_id = (SELECT MAX(id) FROM TESTER_RUNS)
  GROUP BY gate_reason ORDER BY cnt DESC;"
```

### Known Gate Reasons (FORGE 2.7.3)

| Gate reason | Trigger | Added |
|-------------|---------|-------|
| `entry_quality_atr` | ATR < min_entry_atr (3.5) | 2.6.x |
| `entry_quality_direction` | HTF trend not aligned | 2.6.x |
| `entry_quality_body` | Candle body ratio < 0.40 | 2.6.5 |
| `entry_quality_rsi_buy_ceil` | RSI ≥ 70 on BUY breakout | 2.6.7 |
| `entry_quality_rsi_sell_floor` | RSI ≤ 33 on SELL breakout | 2.6.7 |
| `entry_quality_rsi_sell_adx_floor` | RSI ≤ 36 on SELL when ADX < 35 | 2.6.8 |
| `entry_quality_direction_cap` | max_open_same_direction=1 reached | 2.6.6 |
| `entry_quality_atr_ext` | Re-entry extension > max_reentry_atr_ext | 2.7.1 |
| `entry_quality_bb_contraction` | BB bands contracting (no expansion) | 2.6.x |
| `entry_quality_adx_min_sell` | **SELL ADX < adx_min_sell (25)** | **2.7.3** |
| `session_off` | Outside trading window | 2.6.x |
| `session_off_friday` | Friday cutoff hour (planned Run 18) | — |
| `rr_too_low` | RR < min_rr | 2.6.x |
| `cooldown` | Direction cooldown between entries | 2.6.x |
| `no_setup` | No BB setup pattern matched | 2.6.x |
| `warmup_tester_m5_rollovers` | Warmup bars not complete | 2.6.x |
| `entry_quality_rsi_rising_sell` | RSI rising bar-over-bar on SELL (planned Run 18) | — |
| `entry_quality_adx_spike_sell` | ADX was flat N bars ago (planned Run 18) | — |
| `entry_quality_spread_sell` | Spread too wide for SELL (planned Run 18) | — |
| `entry_quality_atr_expansion_sell` | ATR expanded too fast bar-over-bar (planned Run 18) | — |

---

## ADX Gate Validation (FORGE 2.7.3)

```bash
# Check new adx_min_sell gate is firing (SELL blocked at ADX 20-25)
sqlite3 -header -column "$DB" "SELECT gate_reason, COUNT(*) as cnt
  FROM SIGNALS
  WHERE outcome='SKIP' AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
    AND gate_reason LIKE 'entry_quality_adx%'
  GROUP BY gate_reason ORDER BY cnt DESC;"

# SELL entries blocked by adx_min_sell — see ADX values
sqlite3 -header -column "$DB" "SELECT id, datetime(time,'unixepoch') as ts,
  ROUND(adx,1) as adx, ROUND(rsi,1) as rsi, ROUND(price,2) as px, ROUND(atr,2) as atr
  FROM SIGNALS
  WHERE outcome='SKIP' AND gate_reason='entry_quality_adx_min_sell'
    AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
  ORDER BY id DESC LIMIT 20;"

# Verify BUY still fires in ADX 20-25 zone (BUY floor=20, SELL floor=25)
sqlite3 -header -column "$DB" "SELECT direction, ROUND(adx,1) as adx,
  datetime(time,'unixepoch') as ts, setup_type, ROUND(price,2) as px
  FROM SIGNALS
  WHERE outcome='TAKEN' AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
    AND adx BETWEEN 20 AND 25
  ORDER BY time;"
```

---

## BUY vs SELL P&L Breakdown

**MT5 deal type mapping (confirmed from live data):**
| type | direction | Meaning |
|------|-----------|---------|
| 0 | 0 | BUY open (profit=0) |
| 1 | 1 | **BUY close** ← BUY P&L |
| 1 | 0 | SELL open (profit=0) |
| 0 | 1 | **SELL close** ← SELL P&L |

```bash
# Net P&L by direction — correct close-deal filter
# BUY closes: type=1,direction=1 | SELL closes: type=0,direction=1
sqlite3 -header -column "$DB" "
SELECT
  CASE WHEN type=1 AND direction=1 THEN 'BUY'
       WHEN type=0 AND direction=1 THEN 'SELL'
  END as pos_direction,
  COUNT(*) as deals,
  SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) as wins,
  SUM(CASE WHEN profit<0 THEN 1 ELSE 0 END) as losses,
  ROUND(100.0*SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END)/COUNT(*),1) as win_pct,
  ROUND(AVG(CASE WHEN profit>0 THEN profit END),2) as avg_win,
  ROUND(AVG(CASE WHEN profit<0 THEN profit END),2) as avg_loss,
  ROUND(SUM(profit),2) as pnl
FROM TRADES
WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
  AND ((type=1 AND direction=1) OR (type=0 AND direction=1))
GROUP BY type, direction;"

# Group counts by direction (from SIGNALS)
sqlite3 -header -column "$DB" "SELECT direction, COUNT(*) as groups
  FROM SIGNALS WHERE outcome='TAKEN' AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
  GROUP BY direction;"

# All 4 deal classes — sanity check
sqlite3 -header -column "$DB" "
SELECT
  CASE WHEN type=1 AND direction=1 THEN 'BUY_close'
       WHEN type=0 AND direction=1 THEN 'SELL_close'
       WHEN type=0 AND direction=0 THEN 'BUY_open'
       WHEN type=1 AND direction=0 THEN 'SELL_open'
  END as deal_class,
  COUNT(*) as deals, ROUND(SUM(profit),2) as pnl
FROM TRADES WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
GROUP BY type, direction ORDER BY type, direction;"
```

---

## TAKEN Entries Detail

```bash
# All TAKEN entries for the latest run with full indicator context
sqlite3 -header -column "$DB" "SELECT id, datetime(time,'unixepoch') as ts, setup_type,
  direction, ROUND(price,2) as px, ROUND(rsi,1) as rsi, ROUND(adx,1) as adx,
  ROUND(atr,2) as atr, ROUND(spread,1) as spread, session, ROUND(h1_trend,3) as h1_trend,
  CASE WHEN adx < 25 THEN '<25 (SELL floor)' WHEN adx < 20 THEN '<20 (BUY floor)' ELSE 'OK' END as adx_zone
  FROM SIGNALS
  WHERE outcome='TAKEN' AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
  ORDER BY time;"

# SELL entries only — for gate quality analysis
sqlite3 -header -column "$DB" "SELECT id, datetime(time,'unixepoch') as ts,
  ROUND(price,2) as px, ROUND(rsi,1) as rsi, ROUND(adx,1) as adx,
  ROUND(atr,2) as atr, ROUND(spread,1) as spread, session
  FROM SIGNALS
  WHERE outcome='TAKEN' AND direction='SELL'
    AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
  ORDER BY time;"
```

---

## Trade Results (Closed Deals)

```bash
# Closed deals summary for the latest run
sqlite3 -header -column "$DB" "SELECT COUNT(*) as deals,
  SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
  SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losses,
  ROUND(SUM(profit),2) as total_pnl,
  ROUND(AVG(CASE WHEN profit>0 THEN profit END),2) as avg_win,
  ROUND(AVG(CASE WHEN profit<0 THEN profit END),2) as avg_loss,
  ROUND(MIN(volume),2) as min_vol, ROUND(MAX(volume),2) as max_vol
  FROM TRADES WHERE direction IN (1,2,3)
  AND run_id = (SELECT MAX(id) FROM TESTER_RUNS);"

# Per-group P&L (by magic offset)
sqlite3 -header -column "$DB" "SELECT magic,
  COUNT(*) as legs,
  SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) as wins,
  ROUND(SUM(profit),2) as pnl,
  ROUND(MIN(price),2) as entry_px
  FROM TRADES WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS) AND direction IN (1,2,3)
  GROUP BY magic ORDER BY magic;"
```

---

## SELL Loss Investigation

```bash
# All SELL losses — ADX, RSI, spread at entry for pattern analysis
sqlite3 -header -column "$DB" "
SELECT s.id, datetime(s.time,'unixepoch') as ts,
  ROUND(s.adx,1) as adx, ROUND(s.rsi,1) as rsi,
  ROUND(s.spread,1) as spread, ROUND(s.atr,2) as atr,
  ROUND(s.h1_trend,3) as h1_trend,
  COUNT(t.id) as legs, ROUND(SUM(t.profit),2) as pnl
FROM SIGNALS s
JOIN TRADES t ON t.run_id=s.run_id
  AND t.magic=(SELECT MAX(t2.magic) FROM TRADES t2 WHERE t2.run_id=s.run_id AND t2.time >= s.time AND t2.time <= s.time + 3600)
WHERE s.outcome='TAKEN' AND s.direction='SELL'
  AND s.run_id=(SELECT MAX(id) FROM TESTER_RUNS)
GROUP BY s.id
HAVING SUM(t.profit) < 0
ORDER BY pnl ASC;"

# Check RSI direction for SELL losses (detect rising RSI pattern — G5007/G5023 class)
# Run manually after run completes — requires cross-bar RSI comparison via prior signal id
sqlite3 -header -column "$DB" "
SELECT s.id, datetime(s.time,'unixepoch') as ts,
  ROUND(s.adx,1) as adx, ROUND(s.rsi,1) as rsi,
  (SELECT ROUND(rsi,1) FROM SIGNALS s2 WHERE s2.run_id=s.run_id AND s2.id < s.id ORDER BY s2.id DESC LIMIT 1) as rsi_prev_signal,
  ROUND(s.spread,1) as spread, ROUND(SUM(t.profit),2) as pnl
FROM SIGNALS s
JOIN TRADES t ON t.run_id=s.run_id
  AND t.magic=(SELECT MAX(t2.magic) FROM TRADES t2 WHERE t2.run_id=s.run_id AND t2.time >= s.time AND t2.time <= s.time + 3600)
WHERE s.outcome='TAKEN' AND s.direction='SELL'
  AND s.run_id=(SELECT MAX(id) FROM TESTER_RUNS)
GROUP BY s.id HAVING SUM(t.profit) < 0 ORDER BY pnl ASC;"
```

---

## Cross-Run Comparison

```bash
# Compare TAKEN counts and P&L across all runs
sqlite3 -header -column "$DB" "SELECT r.id, datetime(r.wall_time,'unixepoch') as started,
  r.scalper_mode,
  COUNT(CASE WHEN s.outcome='TAKEN' THEN 1 END) as taken,
  COUNT(CASE WHEN s.outcome='SKIP' THEN 1 END) as skipped,
  COUNT(*) as total_signals
  FROM TESTER_RUNS r
  LEFT JOIN SIGNALS s ON s.run_id = r.id
  GROUP BY r.id ORDER BY r.id;"

# P&L per run
sqlite3 -header -column "$DB" "SELECT run_id,
  COUNT(*) as deals,
  SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) as wins,
  SUM(CASE WHEN profit<0 THEN 1 ELSE 0 END) as losses,
  ROUND(SUM(profit),2) as pnl,
  ROUND(MIN(volume),2) as lot
  FROM TRADES WHERE direction IN (1,2,3)
  GROUP BY run_id ORDER BY run_id;"
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
