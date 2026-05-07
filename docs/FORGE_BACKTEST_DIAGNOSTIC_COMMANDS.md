# FORGE Backtest Diagnostic Commands

Quick-reference for verifying warmup, mode, and signal flow during Strategy Tester runs.
All commands run from the repo root (`/Users/olasumbo/signal_system`).

---

## 1. Warmup + mode snapshot (single line)

```bash
python3 -c "import json; ms=json.loads(open('MT5/mode_status.json').read()); print(ms.get('warmup_ok'), ms.get('warmup_reason'), ms.get('scalper_mode'))"
```

Expected when healthy: `True  DUAL`
Blocked example: `False m5_macd_buf DUAL`

---

## 2. Full mode_status.json — all fields

```bash
python3 -c "
import json; ms=json.loads(open('MT5/mode_status.json').read())
for k,v in ms.items(): print(f'  {k}: {v}')
"
```

Key fields to check:
- `warmup_ok` — must be `True` before any entries fire
- `warmup_reason` — exact sub-reason when `warmup_ok=False`
- `scalper_mode` — must be `DUAL`, `BB_BOUNCE`, or `BB_BREAKOUT` (never `NONE`)
- `mode` — must be `SCALPER` or `HYBRID` (never `WATCH`)
- `cycle` — confirm the EA is actively ticking

---

## 3. market_data.json key fields

```bash
python3 -c "
import json, time
from pathlib import Path
md = json.loads(Path('MT5/market_data.json').read_text())
for k in ['forge_version','strategy_tester','mode','ea_cycle','psar_state']:
    if k in md: print(f'  {k}: {md[k]}')
"
```

- `strategy_tester: True` confirms the tester is running (not live)
- `forge_version` must match `VERSION` file after recompile
- `ea_cycle` rising = EA is ticking

---

## 4. scalper_config.json — tester gate checks

```bash
python3 -c "
import json
sc = json.loads(open('MT5/scalper_config.json').read())
bb = sc.get('bb_bounce', {}); sa = sc.get('safety', {})
print('bounce_respect_adx_max_in_tester:', bb.get('bounce_respect_adx_max_in_tester'))
print('bounce_respect_h1_filter_in_tester:', bb.get('bounce_respect_h1_filter_in_tester'))
print('high_vol_apply_in_tester:', sa.get('high_vol_apply_in_tester'))
print('adx_hysteresis_enabled:', sa.get('adx_hysteresis_enabled'))
print('adx_hysteresis_apply_in_tester:', sa.get('adx_hysteresis_apply_in_tester'))
"
```

All three tester gates should be `0` (relaxed) for maximum tester trades:
- `bounce_respect_adx_max_in_tester: 0`
- `bounce_respect_h1_filter_in_tester: 0`
- `high_vol_apply_in_tester: 0`

---

## 5. Active tester journal — signal breakdown

```bash
python3 -c "
import sqlite3, glob, os, time
from pathlib import Path

dbs = sorted(glob.glob(
    '/Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/**/FORGE_journal_*_tester.db',
    recursive=True), key=os.path.getmtime, reverse=True)

if not dbs:
    print('No tester journal found')
else:
    db = dbs[0]
    print(f'DB: {Path(db).parent.parent.name} | age={time.time()-os.path.getmtime(db):.0f}s | size={os.path.getsize(db)}b')
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    cur = con.cursor()
    cur.execute('SELECT COUNT(*) FROM SIGNALS'); print(f'Total SIGNALS: {cur.fetchone()[0]}')
    cur.execute(\"SELECT outcome, COALESCE(gate_reason,''), COUNT(*) n FROM SIGNALS GROUP BY outcome, gate_reason ORDER BY n DESC LIMIT 15\")
    for r in cur.fetchall(): print(f'  {r[0]:8} | {r[1]:30} | {r[2]}')
    cur.execute(\"SELECT COUNT(*) FROM SIGNALS WHERE outcome='TAKEN'\"); print(f'TAKEN total: {cur.fetchone()[0]}')
    con.close()
"
```

### What to look for

| Pattern | Meaning |
|---|---|
| Only `warmup_*` rows | EA is stuck in warmup — check `warmup_reason` in mode_status.json |
| `no_setup` rows growing | Warmup passed, evaluating setups, no valid BB touch yet |
| `rr_too_low` rows | Setups found but SL/TP geometry failing minimum R:R (1.0 in tester) |
| `direction_cooldown` rows | Anti-whipsaw gate firing — normal after entries |
| `TAKEN > 0` | Entries confirmed ✓ |

---

## 6. Last 5 signals with timestamps

```bash
python3 -c "
import sqlite3, glob, os
dbs = sorted(glob.glob(
    '/Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/**/FORGE_journal_*_tester.db',
    recursive=True), key=os.path.getmtime, reverse=True)
if dbs:
    con = sqlite3.connect(f'file:{dbs[0]}?mode=ro', uri=True)
    cur = con.cursor()
    cur.execute(\"SELECT id, datetime(time,'unixepoch') utc, outcome, gate_reason, setup_type, direction FROM SIGNALS ORDER BY time DESC LIMIT 5\")
    for r in cur.fetchall(): print(f'  id={r[0]} {r[1]} {r[2]:6} gate={r[3]:22} {r[4]:12} {r[5]}')
    con.close()
"
```

---

## 7. TESTER_RUNS — run history with warmup inputs

```bash
python3 -c "
import sqlite3, glob, os
dbs = sorted(glob.glob(
    '/Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/**/FORGE_journal_*_tester.db',
    recursive=True), key=os.path.getmtime, reverse=True)
if dbs:
    con = sqlite3.connect(f'file:{dbs[0]}?mode=ro', uri=True)
    cur = con.cursor()
    cur.execute('SELECT id, datetime(start_time,\"unixepoch\") start, scalper_mode, warmup_m5_bars, warmup_seconds FROM TESTER_RUNS ORDER BY id DESC LIMIT 5')
    cols = [d[0] for d in cur.description]
    for r in cur.fetchall(): print(dict(zip(cols, r)))
    con.close()
"
```

---

## 8. Full state snapshot (all JSON + journal combined)

```bash
python3 -c "
import json, sqlite3, glob, os, time
from pathlib import Path

ms = json.loads(Path('MT5/mode_status.json').read_text())
md = json.loads(Path('MT5/market_data.json').read_text())
print('=== mode_status ===')
for k in ['mode','scalper_mode','warmup_ok','warmup_reason','cycle','timestamp']: print(f'  {k}: {ms.get(k)}')
print('=== market_data ===')
for k in ['forge_version','strategy_tester','ea_cycle','psar_state']: print(f'  {k}: {md.get(k)}')

dbs = sorted(glob.glob(
    '/Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/**/FORGE_journal_*_tester.db',
    recursive=True), key=os.path.getmtime, reverse=True)
if dbs:
    db=dbs[0]; print(f'=== journal ({Path(db).parent.parent.name}, age={time.time()-os.path.getmtime(db):.0f}s) ===')
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True); cur = con.cursor()
    cur.execute('SELECT COUNT(*) FROM SIGNALS'); print(f'  total_signals: {cur.fetchone()[0]}')
    cur.execute(\"SELECT COUNT(*) FROM SIGNALS WHERE outcome='TAKEN'\"); print(f'  TAKEN: {cur.fetchone()[0]}')
    cur.execute(\"SELECT outcome, COALESCE(gate_reason,''), COUNT(*) n FROM SIGNALS GROUP BY outcome, gate_reason ORDER BY n DESC LIMIT 8\")
    for r in cur.fetchall(): print(f'  {r[0]:8} | {r[1]:25} | {r[2]}')
    con.close()
"
```

---

## 9. rr_too_low geometry analysis

When entries are being skipped for `rr_too_low`, use this to inspect the actual ATR, BB range,
distance to mid, and estimated R:R for each rejected setup.

```bash
python3 -c "
import sqlite3, glob, os

dbs = sorted(glob.glob(
    '/Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/**/FORGE_journal_*_tester.db',
    recursive=True), key=os.path.getmtime, reverse=True)

con = sqlite3.connect(f'file:{dbs[0]}?mode=ro', uri=True)
cur = con.cursor()

print('--- rr_too_low detail (last 15) ---')
cur.execute(\"\"\"SELECT datetime(time,'unixepoch') utc, direction, price,
       atr, bb_upper, bb_lower, bb_mid, rsi, adx
    FROM SIGNALS WHERE gate_reason='rr_too_low'
    ORDER BY time DESC LIMIT 15\"\"\")
print(f'  {\"time\":20} {\"dir\":5} {\"price\":8} {\"atr\":6} {\"bb_rng\":7} {\"dist_mid\":9} {\"sl_est\":7} {\"rr_est\":6}')
for r in cur.fetchall():
    utc, direction, price, atr, bb_u, bb_l, bb_m, rsi, adx = r
    bb_range = (bb_u - bb_l) if bb_u and bb_l else 0
    dist_to_mid = (bb_m - price) if direction == 'BUY' else (price - bb_m) if bb_m else 0
    sl_est = atr * 1.5 if atr else 0  # bounce_sl_atr_mult default
    rr_est = (dist_to_mid / sl_est) if sl_est > 0 and dist_to_mid > 0 else 0
    print(f'  {utc:20} {direction:5} {price:8.2f} {atr:6.2f} {bb_range:7.2f} {dist_to_mid:9.2f} {sl_est:7.2f} {rr_est:6.2f}')

print()
cur.execute(\"SELECT AVG(atr), AVG(bb_upper-bb_lower) FROM SIGNALS WHERE gate_reason='rr_too_low'\")
r = cur.fetchone()
if r[0]: print(f'Avg ATR on rr_too_low rows: {r[0]:.2f}, Avg BB range: {r[1]:.2f}')
cur.execute(\"SELECT AVG(atr), AVG(bb_upper-bb_lower) FROM SIGNALS WHERE gate_reason='no_setup'\")
r = cur.fetchone()
if r[0]: print(f'Avg ATR on no_setup rows:   {r[0]:.2f}, Avg BB range: {r[1]:.2f}')
con.close()
"
```

### R:R interpretation

| `rr_est` | Meaning |
|---|---|
| < 1.0 | Correctly rejected — SL wider than distance to TP1 |
| ≥ 1.0 but still skipped | TP1 was tightened by POC/VWAP/Fib to be closer than BB_MID |
| Consistently low | BB bands are narrow for this period — try a more volatile date range |

**R:R formula (tester minimum = 1.0):**
```
reward = |TP1 - entry_price|   (TP1 = BB_MID, adjusted by POC/VWAP/Fib)
risk   = |entry_price - SL|   (SL = entry ± bounce_sl_atr_mult × ATR)
R:R    = reward / risk  — must be ≥ 1.0 in tester
```

**Common fix for persistent rr_too_low:** The market period is too calm (narrow BB range).
Either let the backtest run longer into a volatile session, or extend the test date range.

---

## 10. AURUM DB — synced tester signals

```bash
python3 -c "
import sqlite3
db = 'python/data/aurum_intelligence.db'
con = sqlite3.connect(db)
cur = con.cursor()
cur.execute(\"SELECT journal_source, outcome, COALESCE(gate_reason,''), COUNT(*) n FROM forge_signals GROUP BY journal_source, outcome, gate_reason ORDER BY n DESC LIMIT 15\")
for r in cur.fetchall(): print(f'  [{r[0]:6}] {r[1]:8} | {r[2]:25} | {r[3]}')
cur.execute(\"SELECT COUNT(*) FROM forge_signals WHERE outcome='TAKEN' AND journal_source='tester'\"); print(f'TAKEN (tester): {cur.fetchone()[0]}')
con.close()
"
```

---

## 11. Make targets for operations

```bash
make journal-diagnose          # JSON report: journal DBs + SCRIBE totals + top skip reasons
make monitor-forge-skips       # Read-only skip analysis from journal
make forge-compile             # Recompile FORGE.mq5 after code changes
make scalper-env-sync          # Regenerate scalper_config.json from .env + defaults
make scalper-config-sync       # Copy scalper_config.json → MT5 Common Files (no recompile)
make mt5-stop                  # Stop MT5 + Wine processes
make mt5-start                 # Start MT5 app
```

---

## Common warmup blockers and fixes

| `warmup_reason` | Cause | Fix |
|---|---|---|
| `m5_macd_buf` | iMACD buffer 2 doesn't exist in MT5 | Fixed in code — remove probe |
| `h4_bars` | < 70 H4 bars available | Download H4 history in MT5 Data Center |
| `m5_unsynced` | Series not synchronized | Wait, or set `ScalperTesterWarmupM5Bars=0` |
| `tester_m5_rollovers` | Waiting for M5 bar rollover count | Normal — wait for N×5 simulated minutes |
| `psar_buf` | PSAR indicator not computed | Disable PSAR or wait one M5 bar |

---

## Input checklist for zero-trade backtests

In Strategy Tester → Expert Properties → Inputs:

| Input | Required value |
|---|---|
| `InputMode` | `SCALPER` or `HYBRID` (never `WATCH`) |
| `ScalperMode` | `DUAL`, `BB_BOUNCE`, or `BB_BREAKOUT` (never `NONE`) |
| `ScalperTesterWarmupM5Bars` | `2` = wait 2 M5 rollovers; `0` = skip bar checks, fire on indicator readiness |
| `ScalperTesterWarmupSimCapMinutes` | `0` = no time-based shortcut (use actual rollovers) |

Save inputs as a `.set` file to avoid re-entering after reattach.
