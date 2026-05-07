# Prompt — fix **zero trades** while **Strategy Tester** is running (FORGE EA)

Copy everything **below** the horizontal rule into Warp / another assistant **during** a backtest. No full repo is required if you paste **Experts** lines and **Inputs** screenshots or text.

---

**Context:** MetaTrader 5 **Strategy Tester**, Expert **FORGE** from repo **signal_system** (`ea/FORGE.mq5`). Native scalper path: `OnTick` → `CheckNativeScalperSetups()` → possible market orders (comments like `SCALP|BB_BOUNCE|G<id>|TP1`). **`MQL_TESTER` is true** — session/spread caps behave differently than live; **`config.json` `effective_mode` / `scalper_mode`** must **not** override EA Inputs in tester (FORGE ignores those for mode).

**Symptom:** Backtest runs (bars advance, journal may grow) but **History** shows **0 deals** / **no positions**, or Experts never prints a successful open line.

---

## 1. Stop-the-line checks (Expert **Inputs** — same run)

| Input | Required for native scalper |
|--------|----------------------------|
| **InputMode** | **`SCALPER`**, **`HYBRID`**, or **`SIGNAL`** — **not** **`WATCH`** / **`OFF`** (`OnTick` returns before scalper on `WATCH`). |
| **ScalperMode** | **`DUAL`**, **`BB_BOUNCE`**, or **`BB_BREAKOUT`** — **not** **`NONE`**. |

On attach, tester should log **`FORGE TESTER:`** if `ScalperMode` or `InputMode` block the scalper — read **Experts** from the **start** of the test.

---

## 2. Warmup (blocks **all** entries until pass)

In **`ForgeNativeScalperWarmupOk`**: enough **history** (≥70 bars M5/M15/M30/H1/H4), **sync**, **indicator buffers** (reasons like **`h4_ema20_buf`**, **`h1_bars`**), then **optional**:

- **`ScalperTesterWarmupM5Bars`** — M5 bar rollovers after init (**`0` = off**; also skips bar-count + sync checks — fastest path to first trade when indicators are ready).
- **`ScalperTesterWarmupSimCapMinutes`** — waived M5 rollover wait after N **simulated** minutes (**only if** `ScalperTesterWarmupM5Bars > 0`; **if M5 bars = 0, SimCap does nothing**).
- **`ScalperWarmupSeconds`** — extra delay (**simulated** seconds in tester).

**Log:** `FORGE SCALPER: skip gate=warmup reason=...` — fix the **reason** first; entries cannot fire until warmup passes.

**New (v2.5.1):** warmup state is exposed in **`MT5/mode_status.json`**:
```bash
python3 -c "import json; ms=json.loads(open('MT5/mode_status.json').read()); print(ms.get('warmup_ok'), ms.get('warmup_reason'), ms.get('scalper_mode'))"
```
Expected healthy output: `True  DUAL`. If `warmup_ok=False`, `warmup_reason` gives the exact sub-reason.

**⚠️ Known bug (fixed in v2.5.1): `m5_macd_buf` permanently fails**
MT5's built-in `iMACD` only has **2 buffers** (0=MACD main, 1=signal). Buffer 2 (histogram) does not exist — `CopyBuffer(h_macd, 2, ...)` always returns `-1`. The warmup probe on this buffer caused warmup to block permanently on every tick, producing zero TAKEN for the **entire** backtest. The probe was removed. If you see `warmup_reason: m5_macd_buf` on an older build, recompile with `make forge-compile`.

---

## 3. Config JSON (`scalper_config.json`) — tester can be **stricter**

Loaded from MT5 **Common Files** (and repo sync copy). If **no** `TAKEN` but many **`SKIP|no_setup`** in the journal:

- **`bounce_respect_adx_max_in_tester`** / **`bounce_respect_h1_filter_in_tester`** — when **`true`**, tester bounce obeys ADX cap and H1-style filter (fewer fades vs relaxed tester defaults).
- **`bounce_htf_bias`**, **`bounce_require_h1_direction`**, **`bounce_block_htf_trend_align`** — see **`docs/WARP_FORGE_VERIFY_PROMPT.md`** addendum for `no_setup`.
- **ADX hysteresis** — if stuck in **trend** regime, bounce may be skipped (`adx_trend_regime_bounce`).
- **`rr_too_low`** — SL/TP geometry fails minimum R:R (`skip gate` / journal `gate_reason`).

Regenerate JSON: **`make scalper-env-sync`** / **`make forge-recompile`** and ensure FORGE in tester sees the updated file.

---

## 4. Ground truth: **tester journal** (not only AURUM)

Path pattern (macOS Wine):

`~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/Agent-127.0.0.1-*/MQL5/Files/FORGE_journal_<SYMBOL>_tester.db`

Use the **Agent** folder MT5 is **actually writing** (e.g. `3000` vs `3001`). In SQLite, table **`SIGNALS`**:

```sql
SELECT outcome, COALESCE(gate_reason,''), COUNT(*) n
FROM SIGNALS GROUP BY outcome, gate_reason ORDER BY n DESC;

SELECT id, datetime(time,'unixepoch') AS utc, outcome, gate_reason, setup_type, direction
FROM SIGNALS ORDER BY time DESC LIMIT 25;

SELECT COUNT(*) FROM SIGNALS WHERE outcome='TAKEN';
```

- **`ORDER BY time DESC`** = current **simulated** time frontier (**`id` may not match time order**).
- If **`TAKEN > 0`** but MT5 **History** empty, suspect **agent vs chart** confusion or **non-trading rights** in tester settings — re-check **Expert properties** and **model**.

**AURUM `forge_signals`** (`python/data/aurum_intelligence.db`) **lags** unless **BRIDGE** is running — for a **live** backtest diagnosis, prefer the **`.db` on disk** above.

---

## 5. Ask the assistant to deliver

1. **Binary checklist:** Inputs → warmup → dominant `gate_reason` from **`SIGNALS`** → JSON flags.  
2. **Map** last 5 **Experts** `skip gate=` / `no setup` lines to **code/config** (cite **`CheckNativeScalperSetups`** / **`ForgeNativeScalperWarmupOk`**).  
3. **Minimal change** to get **at least one** `TAKEN` in a short window (e.g. relax **one** gate or set **`ScalperTesterWarmupM5Bars=0`** for isolation).  
4. **Not** spend time on **`no_mt5_exposure_for_magic`** unless **BRIDGE + scalper_entry** path is in scope for this run.

---

## 6. Remote diagnostic commands (v2.5.1+)

All run from repo root. See full reference: **`docs/FORGE_BACKTEST_DIAGNOSTIC_COMMANDS.md`**

```bash
# 1. Warmup + mode one-liner
python3 -c "import json; ms=json.loads(open('MT5/mode_status.json').read()); print(ms.get('warmup_ok'), ms.get('warmup_reason'), ms.get('scalper_mode'))"

# 2. Journal signal breakdown (finds active agent DB automatically)
python3 -c "
import sqlite3, glob, os, time
dbs = sorted(glob.glob('/Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/**/FORGE_journal_*_tester.db', recursive=True), key=os.path.getmtime, reverse=True)
if dbs:
    con = sqlite3.connect(f'file:{dbs[0]}?mode=ro', uri=True); cur = con.cursor()
    cur.execute(\"SELECT outcome, COALESCE(gate_reason,''), COUNT(*) n FROM SIGNALS GROUP BY outcome, gate_reason ORDER BY n DESC LIMIT 10\")
    [print(f'  {r[0]:8} | {r[1]:30} | {r[2]}') for r in cur.fetchall()]
    cur.execute(\"SELECT COUNT(*) FROM SIGNALS WHERE outcome='TAKEN'\"); print(f'TAKEN: {cur.fetchone()[0]}')
    con.close()
"

# 3. make targets
make journal-diagnose      # JSON summary of all journal DBs + SCRIBE totals
make monitor-forge-skips   # read-only skip analysis
```

---

## 7. Repo pointers (optional)

| Topic | Location |
|-------|----------|
| Scalper gate order | `ea/FORGE.mq5` — `CheckNativeScalperSetups`, `ForgeNativeScalperWarmupOk` |
| Wider verify + BRIDGE | `docs/WARP_FORGE_VERIFY_PROMPT.md` |
| Config pipeline | `docs/SCALPER_CONFIG_PIPELINE.md` |
| Compile + stamp VERSION | `make forge-recompile` |
