---
name: forge-monitor
description: Monitor an MT5/MQL5 FORGE EA backtest by polling tester journal DBs every 45s. Reports new signals, skips, taken trades, gate deltas, and SELL STOP continuation / BUY LIMIT recovery arming. Cross-references the source tester DB (SIGNALS/TRADES/TESTER_RUNS) against aurum_tester.db (forge_signals / forge_journal_trades / aurum_tester_runs). Writes a per-run analysis doc and keeps the query cheat sheet current. Invoke when the user asks to "monitor the forge tester", "watch the backtest", "tail the journal", "monitor", "now monitor", or "/forge-monitor".
---

# /forge-monitor — FORGE tester journal monitor

You are debugging an MT5/MQL5 backtesting session. Be skeptical — flag suspicious
patterns rather than reporting them as normal: atr=0, identical prices, P&L moving
without trade count changing, unknown gate_reason values, all-skip runs, cascade
magics firing unexpectedly.

The source DB is read-only. aurum_tester.db is also read-only (bridge manages it).
The cheat sheet and analysis docs are writable.

---

## DB ARCHITECTURE (updated 2026-05-10)

### Source journal DB (written by FORGE EA during backtest)
MT5 Strategy Tester writes to agent-specific paths. Check ALL agents:

```
Agent-127.0.0.1-3000:
  /Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/Agent-127.0.0.1-3000/MQL5/Files/FORGE_journal_XAUUSD_tester.db

Agent-127.0.0.1-3001:
  /Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/Agent-127.0.0.1-3001/MQL5/Files/FORGE_journal_XAUUSD_tester.db
```

Auto-discover all agents:
```bash
find "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5" \
  -name "FORGE_journal_XAUUSD_tester.db" 2>/dev/null
```

Use the most recently modified DB (check mtime).

**Source DB tables** (TESTER_RUNS, SIGNALS, TRADES, STATS_CACHE):
- `TESTER_RUNS(id, wall_time, sim_start_time, symbol, balance, forge_version, scalper_mode, warmup_m5_bars, warmup_seconds, magic_base)`
- `SIGNALS(id, time, symbol, setup_type, direction, outcome, gate_reason, price, spread, atr, rsi, adx, bb_upper, bb_lower, bb_mid, poc_price, vwap_price, fib_50, rsi_divergence, psar_state, pattern_score, h1_trend, regime_label, regime_confidence, adx_trend_regime, high_vol_trend, session, magic, synced, macd_histogram, m15_adx, lot_factor, run_id)`
- `TRADES(id, deal_ticket, order_ticket, symbol, type, direction, volume, price, profit, swap, commission, magic, comment, time, time_msc, synced, run_id)` — UNIQUE(deal_ticket, run_id)

**Key columns:**
- `SIGNALS.outcome`: `'TAKEN'` or `'SKIP'`
- `SIGNALS.gate_reason`: populated when outcome='SKIP' (see config/gate_legend.json for all 34 codes)
- `TRADES.comment`: `'SCALP|BB_BREAKOUT|G5001|TP1'` (partial closes, profit=0) or `'tp 4539.89'` (final close)
- `TRADES.magic`: group magic (e.g., 207402 for G5001 = magic_base+5001) or base magic for final closes
- `SIGNALS.run_id`: matches `TESTER_RUNS.id` — always filter by `run_id=(SELECT MAX(id) FROM TESTER_RUNS)`

### AURUM tester DB (written by BRIDGE sync — 60s cadence)
```
/Users/olasumbo/signal_system/python/data/aurum_tester.db
```

**Key tables:**
- `aurum_tester_runs(aurum_run_id, wall_time, source_run_id, journal_source, symbol, forge_version, scalper_mode, balance, sim_start_time, magic_base, first_seen_utc)`
  - `wall_time`: GetTickCount64() at run start — unique entropy key per real run, survives source DB wipes
  - `aurum_run_id`: stable AURUM sequential ID (AUTOINCREMENT, never resets)
  - `source_run_id`: run_id from TESTER_RUNS (resets to 1 on each source DB wipe)
- `forge_signals(id, forge_id, time, timestamp_utc, symbol, setup_type, direction, outcome, gate_reason, price, spread, atr, rsi, adx, bb_upper, bb_lower, bb_mid, poc_price, vwap_price, fib_50, rsi_divergence, psar_state, pattern_score, h1_trend, regime_label, regime_confidence, adx_trend_regime, high_vol_trend, session, magic, journal_source, run_id, wall_time, aurum_run_id, macd_histogram, m15_adx, lot_factor)`
- `forge_journal_trades(id, forge_rowid, deal_ticket, order_ticket, symbol, type, direction, volume, price, profit, swap, commission, magic, comment, time, time_msc, journal_source, run_id, wall_time, aurum_run_id)`

**UNIQUE constraints:**
- `forge_signals`: `UNIQUE(forge_id, journal_source, wall_time)` — prevents duplicate syncs across runs
- `forge_journal_trades`: `UNIQUE(deal_ticket, journal_source, wall_time)` — same protection

**CRITICAL: sync lag** — BRIDGE syncs source DB → aurum_tester.db every 60s in batches of 5000. During an active run, aurum_tester.db may lag by 1–3 minutes. **Always query the source SIGNALS/TRADES tables for live monitoring.** Use aurum_tester.db only for cross-run analysis.

**Sync recovery:** If aurum_tester.db lags significantly, BRIDGE auto-detects the gap using ATTACH and resets `synced=0` on missing rows within one 60s cycle (logged as `BRIDGE: sync-recovery` in bridge.log). MT5 never clears SIGNALS between runs — BRIDGE uses wall_time to distinguish runs.

**Multi-agent design:** When MT5 assigns a new tester run to Agent-3001 while Agent-3000 has an older run, both DBs are monitored simultaneously. Each gets its own `aurum_run_id`.

### Live AURUM DB (NOT for backtest monitoring)
```
/Users/olasumbo/signal_system/python/data/aurum_intelligence.db
```
This is the live trading SCRIBE DB. Do NOT query it for backtest data.

---

## SETUP (run once per monitoring session)

**Step 1** — Find the active tester DB:
```bash
find "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5" \
  -name "FORGE_journal_XAUUSD_tester.db" 2>/dev/null \
  | xargs ls -lt 2>/dev/null | head -5
```
Set `DB` to the most recently modified path.

**Step 2** — Read the cheat sheet:
`/Users/olasumbo/signal_system/docs/FORGE_TESTER_JOURNAL_QUERIES.md`

**Step 3** — Capture baseline (tick 0):
```bash
DB="<path from step 1>"
sqlite3 -readonly "$DB" "
SELECT r.id as run_id, r.wall_time, r.forge_version, r.scalper_mode,
       datetime(r.sim_start_time,'unixepoch') as sim_start,
       r.magic_base,
       COUNT(s.id) as total_signals,
       SUM(CASE WHEN s.outcome='TAKEN' THEN 1 ELSE 0 END) as taken,
       SUM(CASE WHEN s.synced=1 THEN 1 ELSE 0 END) as synced_to_aurum
FROM TESTER_RUNS r LEFT JOIN SIGNALS s ON s.run_id=r.id
GROUP BY r.id ORDER BY r.id DESC LIMIT 1;"
```

**Step 4** — Find or create the analysis doc. First get the aurum_run_id:
```bash
python3 -c "
import sqlite3
src_db = '$DB'
aurum_db = '/Users/olasumbo/signal_system/python/data/aurum_tester.db'
wt = sqlite3.connect(src_db).execute('SELECT wall_time FROM TESTER_RUNS ORDER BY id DESC LIMIT 1').fetchone()
if wt:
    row = sqlite3.connect(aurum_db).execute('SELECT aurum_run_id FROM aurum_tester_runs WHERE wall_time=?', wt).fetchone()
    print('aurum_run_id:', row[0] if row else 'NOT YET SYNCED — wait 60s and retry')
else:
    print('No TESTER_RUNS found — tester not started yet')
"
```

Ensure analysis doc: `/Users/olasumbo/signal_system/docs/FORGE_RUN<aurum_run_id>_ANALYSIS.md`

**Step 5** — Report baseline: run_id, wall_time, FORGE version, scalper_mode, sim_start, signal count, taken count.

---

## LOOP (every 45s)

### Q1 — Sim progress
```bash
sqlite3 -readonly "$DB" "
SELECT datetime(MAX(time),'unixepoch') as latest_sim_time,
       COUNT(*) as total_signals,
       SUM(CASE WHEN outcome='TAKEN' THEN 1 ELSE 0 END) as taken
FROM SIGNALS WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS);"
```

### Q2 — TAKEN signals
```bash
sqlite3 -readonly "$DB" "
SELECT datetime(time,'unixepoch') as sim_time, magic, setup_type, direction,
       ROUND(price,2) as price, ROUND(atr,2) as atr,
       ROUND(rsi,1) as rsi, ROUND(adx,1) as adx, session
FROM SIGNALS WHERE outcome='TAKEN'
  AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
ORDER BY time;"
```

### Q3 — Gate breakdown
```bash
sqlite3 -readonly "$DB" "
SELECT gate_reason, COUNT(*) as cnt
FROM SIGNALS
WHERE outcome='SKIP' AND gate_reason IS NOT NULL AND gate_reason!=''
  AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
GROUP BY gate_reason ORDER BY cnt DESC LIMIT 15;"
```

### Q4 — Trades and P&L
```bash
# Recent trades
sqlite3 -readonly "$DB" "
SELECT deal_ticket, magic, ROUND(profit,2) as profit, comment,
       datetime(time,'unixepoch') as sim_time
FROM TRADES WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
ORDER BY time DESC LIMIT 15;"

# Summary
sqlite3 -readonly "$DB" "
SELECT COUNT(*) as total_trades,
       SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) as wins,
       SUM(CASE WHEN profit<0 THEN 1 ELSE 0 END) as losses,
       ROUND(SUM(profit),2) as total_pnl
FROM TRADES WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
  AND profit IS NOT NULL AND profit!=0;"
```

### Q5 — SELL STOP CONT + BUY LIMIT cascade arming (FORGE 2.7.10+)
Check MT5 tester log for cascade arming events:
```bash
LOGDIR="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/Agent-127.0.0.1-3000/logs"
grep -E "ArmPostTP1Ladder|SELL STOP CONT|BUY LIMIT|slot\[2\]|slot\[3\]|slot\[4\]|exhausted|RSI.*<.*min_rsi" \
  "$LOGDIR"/*.log 2>/dev/null | sort -u | tail -20
```

**Cascade magic formula** (FORGE 2.7.10+):
- Group rank 1 (G5001): `magic_base + 5001` = 207402 for magic_base=202401
- SELL STOP slot[2]: `group_magic + 20002` = 227404
- SELL STOP slot[3]: `group_magic + 20003` = 227405 (true scaling, second group)
- BUY LIMIT slot[4]: `group_magic + 20004` = 227406

RSI gate: SELL STOP only arms when `RSI > sell_stop_cont_min_rsi` (default 25.0)
BUY LIMIT only arms when `RSI > buy_limit_recovery_min_rsi` (default 35.0)

**Known bug fixed in 2.7.11**: When native TP fires before ManageOpenGroups tick (0.01 min-lot groups), ArmPostTP1Ladder was skipped. Fixed: `total==0` path now calls ArmPostTP1Ladder.

### Q6 — Losses
```bash
sqlite3 -readonly "$DB" "
SELECT deal_ticket, magic, ROUND(profit,2) as profit, comment,
       datetime(time,'unixepoch') as sim_time
FROM TRADES WHERE profit<0
  AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
ORDER BY profit ASC;"
```

### Q7 — STATS_CACHE (hourly P&L breakdown)
```bash
sqlite3 -readonly "$DB" "
SELECT metric, ROUND(value,2) as value
FROM STATS_CACHE
WHERE metric LIKE 'hour_%'
ORDER BY metric;"
```

### Q8 — Sync lag check
```bash
python3 -c "
import sqlite3
src_db = '$DB'
aurum_db = '/Users/olasumbo/signal_system/python/data/aurum_tester.db'
src_cnt = sqlite3.connect(src_db).execute('SELECT COUNT(*) FROM SIGNALS WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)').fetchone()[0]
wt = sqlite3.connect(src_db).execute('SELECT wall_time FROM TESTER_RUNS ORDER BY id DESC LIMIT 1').fetchone()
if wt:
    row = sqlite3.connect(aurum_db).execute('SELECT aurum_run_id, COUNT(*) FROM forge_signals WHERE wall_time=? GROUP BY aurum_run_id', wt).fetchone()
    dst_cnt = row[1] if row else 0
    aid = row[0] if row else '?'
    print(f'Source SIGNALS: {src_cnt} | aurum_tester.db run {aid}: {dst_cnt} | lag: {src_cnt-dst_cnt}')
    if src_cnt - dst_cnt > 5000:
        print('WARNING: large lag — bridge sync-recovery may be running')
"
```

---

## WHAT TO REPORT (changes only vs prev tick)

1. **Sim time progress** and total signal count delta
2. **New TAKEN groups**: direction, session, RSI, ADX, entry price, ATR
3. **Gate changes**: new gate_reason seen for first time, or count jumping >500
4. **New trades**: TP1/TP2/TP3/TP4 partial closes (profit=0, has comment), final closes (profit>0)
5. **ArmPostTP1Ladder events** from MT5 log: slot, RSI at time, expiry, armed vs skipped (exhausted)
6. **Losses**: any profit < 0 — magic, amount, comment
7. **Sync lag** if aurum_tester.db is >5000 behind source

**Silence is valid**: "No new signals since last tick (N total)."

---

## STOP CONDITIONS

Stop after **3 consecutive ticks with no new signals** — run is complete. Before stopping:
1. Write final summary to `FORGE_RUN<aurum_run_id>_ANALYSIS.md`
2. Report: total TAKEN, total P&L, win rate, all cascade arm events observed
3. Cross-check with Athena backtest tab: `http://localhost:7842/api/backtest/run/<aurum_run_id>`
4. Append new gate_reason codes to `docs/FORGE_TESTER_JOURNAL_QUERIES.md`

---

## CHEAT SHEET EXPANSION

If you discover a table/column not in `FORGE_TESTER_JOURNAL_QUERIES.md`:
- Test your query, then append under `## Discovered Queries (auto-added by /forge-monitor)`
- If an existing query fails, append a working replacement under `## Query revisions (auto-added by /forge-monitor)`
- Never edit existing entries — append only

---

## ANALYSIS DOC TEMPLATE

```markdown
# FORGE Run <aurum_run_id> — Tester Analysis

**EA version**: FORGE vX.Y.Z  
**Symbol**: XAUUSD  
**Sim period**: YYYY-MM-DD → YYYY-MM-DD  
**Scalper mode**: DUAL  
**Balance**: $10,000  
**aurum_run_id**: N  
**wall_time**: NNNNNNNNNN  
**source_run_id**: N (TESTER_RUNS.id)

## Summary
- Total signals: N
- TAKEN: N  |  Skipped: N
- Total P&L: $N.NN
- Win rate: N% (W wins / L losses)

## TAKEN Groups
| Sim Time (UTC) | Group | Direction | Session | RSI | ADX | TP reached | P&L |
|----------------|-------|-----------|---------|-----|-----|-----------|-----|

## Gate Breakdown (top 10 SKIP reasons)
| Gate Reason | Count | Human Label |
|-------------|-------|-------------|

## SELL STOP CONT / BUY LIMIT Events
| Event | Group | Slot | RSI | Price | Expiry | Result |
|-------|-------|------|-----|-------|--------|--------|

## Losses
| Deal | Magic | Profit | Comment | Sim Time |
|------|-------|--------|---------|----------|

## Observations & Anomalies

## Session Log
```

---

## GATE LEGEND QUICK REFERENCE

Full 34-gate legend: `config/gate_legend.json` | API: `GET http://localhost:7842/api/gate_legend`

Common tester gates:

| gate_reason | Meaning |
|-------------|---------|
| `entry_quality_direction` | Not enough M5 bars moving in trade direction (need 2+) |
| `entry_quality_body` | Candle body too small — indecision candle |
| `entry_quality_rsi_sell_floor` | RSI below sell floor (oversold, default 33) |
| `entry_quality_rsi_sell_adx_floor` | Stricter RSI floor when ADX is weak |
| `entry_quality_adx_min_sell` | ADX too low for breakout sell (default 20) |
| `entry_quality_bb_contraction` | BB squeezing — no momentum |
| `entry_quality_atr` | ATR too low — market too quiet |
| `entry_quality_atr_ext` | Post-setup ATR too small for viable trade |
| `open_groups` | Max concurrent groups reached (default 2) |
| `rr_too_low` | Risk:Reward below minimum (default 1.5×) |
| `no_setup` | Neither BB Breakout nor BB Bounce conditions met |
| `session_off` | Outside London/NY session |
| `warmup_tester_m5_rollovers` | M5 indicator buffers not ready at backtest start |
