# FORGE v2.7.16 — M1 Indicator Logging (Reading A)

**Status**: PLAN (not yet implemented)
**Target version**: FORGE v2.7.16
**Scope**: Diagnostic forensics only — log M1 RSI + M1 ADX in SIGNALS, no entry-gate behavior change
**Estimated effort**: ~55 lines code, 1 compile cycle, 1 short verification run (~45 min total)
**Risk**: LOW — additive change, no gate logic touched, pattern proven by m15_adx + macd_histogram + lot_factor migrations

---

## 1. Goal

Add `m1_rsi` and `m1_adx` columns to the SIGNALS table (and its AURUM mirror) so post-run analysis can answer questions like:
- "Was M1 momentum already reversing when M5 fired the SELL?"
- "Did the M1 RSI confirm or contradict the M5 RSI at TAKEN entries?"
- "What M1 ADX pattern preceded the May 4 18:16 ADX-spike block?"

The data is **never read by an entry gate**. It is purely diagnostic, for SQL queries against finished runs.

---

## 2. Why M1 (and not just M5/M15/H1/H4)

The current SIGNALS table already logs:
- `rsi`, `adx`, `atr` — M5 (primary)
- `m15_adx` — M15 (confirmation)
- `h1_trend` — H1 (trend filter via DI- vs DI+)
- `macd_histogram` — H1 MACD (momentum confirmation)

M1 is the only timeframe missing, and it's the most granular pre-entry signal. Useful for:
- Detecting micro-reversals 1–3 minutes before M5 fires
- Validating whether the M5 ADX spike (a key gate at `entry_quality_adx_spike_sell`) originated on M1 first
- Future research into whether M1 confirmation could be added as an entry filter — but **only after we have data to study**

**Decision: log first, gate later (if at all).** Reading B (use M1 as an entry filter) is explicitly out of scope here.

---

## 3. Implementation pattern — fetch-inside-function

The function `JournalRecordSignal()` at `ea/FORGE.mq5:4084` is called from **61 call sites** across the EA. Threading two new parameters through every call site is unnecessary work AND error-prone.

Better: fetch M1 values **inside** `JournalRecordSignal` using `CopyBuffer` once per call. M1 values aren't direction- or setup-specific, so they can be fetched from globals (`g_h_m1_rsi`, `g_h_m1_adx`) at journal-time without passing through the call chain.

```cpp
// Inside JournalRecordSignal (after existing variable setup):
double m1_rsi = 0.0, m1_adx = 0.0;
double _m1buf[1];
if(g_h_m1_rsi != INVALID_HANDLE && CopyBuffer(g_h_m1_rsi, 0, 0, 1, _m1buf) == 1)
    m1_rsi = _m1buf[0];
if(g_h_m1_adx != INVALID_HANDLE && CopyBuffer(g_h_m1_adx, 0, 0, 1, _m1buf) == 1)
    m1_adx = _m1buf[0];
```

Cost per call: 2 CopyBuffer reads (~µs each). JournalRecordSignal already does similar reads for VP/Fib state. Negligible overhead.

**Note**: pre-warmup returns `0.0` gracefully (same pattern m15_adx already follows). M1 ADX(14) needs 14 M1 bars (~14 minutes) to stabilize.

---

## 4. Step-by-step changes

### Step 4.1 — `ea/FORGE.mq5` (~35 lines, ALL changes here)

#### 4.1.a — Add globals near existing indicator-handle declarations

Find the block near `g_h_osma_scalp` (or wherever existing handles live) and add:

```cpp
// M1 diagnostic indicators (2.7.16) — logged in SIGNALS, NOT used by entry gates.
int g_h_m1_rsi = INVALID_HANDLE;
int g_h_m1_adx = INVALID_HANDLE;
```

#### 4.1.b — Initialize in `OnInit`

After existing indicator-handle inits (around the `g_mtf[]` loop or similar):

```cpp
g_h_m1_rsi = iRSI(_Symbol, PERIOD_M1, 14, PRICE_CLOSE);
g_h_m1_adx = iADX(_Symbol, PERIOD_M1, 14);
if(g_h_m1_rsi == INVALID_HANDLE || g_h_m1_adx == INVALID_HANDLE)
   Print("FORGE: M1 indicator init failed (m1_rsi=", g_h_m1_rsi,
         " m1_adx=", g_h_m1_adx, ") — m1_rsi/m1_adx will log 0.0");
```

Non-fatal — same approach as other optional handles.

#### 4.1.c — Release in `OnDeinit`

```cpp
IndicatorRelease(g_h_m1_rsi);
IndicatorRelease(g_h_m1_adx);
```

#### 4.1.d — Add columns to CREATE TABLE at `FORGE.mq5:3877`

Find the existing `CREATE TABLE IF NOT EXISTS SIGNALS (...)` statement and add to the column list:

```sql
m1_rsi REAL DEFAULT 0,
m1_adx REAL DEFAULT 0,
```

Position them next to `m15_adx` for consistency.

#### 4.1.e — Add ALTER TABLE migrations after the existing run_id migration at `FORGE.mq5:3969`

```cpp
DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m1_rsi REAL DEFAULT 0;");
DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m1_adx REAL DEFAULT 0;");
```

`DatabaseExecute` returns false silently when the column already exists — idempotent.

#### 4.1.f — Update `JournalRecordSignal` body at `FORGE.mq5:4084`

Two edits inside the function:

1. **Fetch M1 values** at function entry (after the `g_journal_db` check):
```cpp
double m1_rsi = 0.0, m1_adx = 0.0;
double _m1buf[1];
if(g_h_m1_rsi != INVALID_HANDLE && CopyBuffer(g_h_m1_rsi, 0, 0, 1, _m1buf) == 1) m1_rsi = _m1buf[0];
if(g_h_m1_adx != INVALID_HANDLE && CopyBuffer(g_h_m1_adx, 0, 0, 1, _m1buf) == 1) m1_adx = _m1buf[0];
```

2. **Add to the INSERT SQL** at `FORGE.mq5:4102` — column list AND VALUES:
```cpp
// In the column list:
"macd_histogram, m15_adx, lot_factor, m1_rsi, m1_adx) VALUES ("
// In the VALUES bind block (after lot_factor):
+ DoubleToString(m1_rsi, 2) + ", "
+ DoubleToString(m1_adx, 2) + ", "
```

#### 4.1.g — Signature unchanged

No callers need updating. The 61 `JournalRecordSignal(...)` call sites stay as-is.

#### 4.1.h — Bump VERSION

```bash
echo "2.7.16" > VERSION
```

#### 4.1.i — Build

```bash
make forge-compile
```

Per the BUILD-BEFORE-COMMIT rule in `.claude/skills/forge-monitor/SKILL.md`, this MUST succeed before staging. If errors, fix them; do not commit a broken `.mq5`.

---

### Step 4.2 — `python/scribe.py` (~10 lines)

Mirror the pattern already used for `macd_histogram` + `m15_adx` + `lot_factor`.

#### 4.2.a — Add ALTER TABLE migrations (after line ~568)

```python
if "m1_rsi" not in fs_cols:
    # m1_rsi — M1 RSI at signal time (added in FORGE 2.7.16, diagnostic only).
    conn.execute("ALTER TABLE forge_signals ADD COLUMN m1_rsi REAL")
    log.info("SCRIBE migration: added m1_rsi to forge_signals")
if "m1_adx" not in fs_cols:
    # m1_adx — M1 ADX at signal time (added in FORGE 2.7.16, diagnostic only).
    conn.execute("ALTER TABLE forge_signals ADD COLUMN m1_adx REAL")
    log.info("SCRIBE migration: added m1_adx to forge_signals")
```

#### 4.2.b — Add to column-existence detection (line ~867)

```python
has_m1_rsi = "m1_rsi" in src_cols
has_m1_adx = "m1_adx" in src_cols
```

#### 4.2.c — Add to SELECT (line ~974)

```python
+ (", m1_rsi"  if has_m1_rsi  else ", NULL")
+ (", m1_adx"  if has_m1_adx  else ", NULL")
```

#### 4.2.d — Add to INSERT column list (line ~1029)

```python
"macd_histogram, m15_adx, lot_factor, m1_rsi, m1_adx, wall_time, aurum_run_id) "
```

---

### Step 4.3 — `python/bridge.py` (~10 lines)

The bridge maintains the `aurum_tester.db` mirror. Same additive pattern.

Find the existing `forge_signals` schema migration / INSERT in `bridge.py` (search for `m15_adx` to locate the pattern) and apply the same two-column extension:
- ALTER TABLE migrations for `m1_rsi` + `m1_adx` (idempotent)
- INSERT column list updated

The bridge has its own `forge_signals` CREATE TABLE elsewhere — add `m1_rsi REAL` + `m1_adx REAL` to that too (so fresh DBs get the columns directly).

---

### Step 4.4 — `schemas/` (if applicable)

| File | Change required? |
|------|------------------|
| `schemas/openapi.yaml` | YES if it documents the SIGNALS schema — add m1_rsi + m1_adx fields |
| `schemas/scribe_query_examples.json` | Only if it shows column-by-column examples |

Inspect both files; add the two columns only where the schema is exhaustively documented.

---

### Step 4.5 — `tests/api/test_forge_27x_gates.py` (~5 lines)

Add a one-line check in the existing schema-coverage test confirming the columns exist after sync. Mirrors the pattern for `m15_adx`:

```python
def test_v2716_m1_columns_present_in_active_db(...):
    """v2.7.16 added m1_rsi + m1_adx for diagnostic forensics."""
    # query columns of forge_signals or SIGNALS, assert both present
```

---

### Step 4.6 — Docs

| File | Change |
|------|--------|
| `docs/FORGE_ENTRY_CONDITIONS.md` | Append a "SIGNALS table — diagnostic columns" section listing m1_rsi + m1_adx, note they're **not** used by gates |
| `docs/FORGE_TESTER_JOURNAL_QUERIES.md` | (Optional) Add one example query joining M1 vs M5 values for SKIPs/TAKENs |

---

## 5. Edge cases

| Case | Behaviour |
|------|-----------|
| Tester start with `warmup_m5_bars=2` — M1 ADX not yet warm | `CopyBuffer` returns 0 fills → m1_rsi=0.0 / m1_adx=0.0 logged. No trade-decision impact. |
| M1 handle init fails (rare) | Log warning at OnInit; m1_rsi/m1_adx always 0.0. Run proceeds normally. |
| Existing tester DB has no m1 columns | ALTER TABLE migrations add them on next EA load. Old rows have DEFAULT 0. |
| Existing aurum_tester.db has no m1 columns | Bridge runs its migration on first sync after deploy. |
| Bridge syncs from EA with m1 columns to AURUM without them | scribe.py / bridge.py ALTER TABLE adds them; INSERT path falls back to NULL until then. |

---

## 6. Verification flow (after implementation)

1. `make forge-compile` — must succeed
2. Reload `FORGE.ex5` in MT5 (remove from chart → re-add)
3. Start a short backtest run (~15 sim minutes is enough)
4. Query the source tester DB:
```sql
SELECT datetime(time,'unixepoch'), direction, rsi, adx, m15_adx, m1_rsi, m1_adx
FROM SIGNALS
WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
  AND outcome='TAKEN'
ORDER BY time;
```
Expect non-zero `m1_rsi` and `m1_adx` after the first ~15 sim minutes.

5. After bridge sync (60s), cross-check `aurum_tester.db`:
```sql
SELECT aurum_run_id, m1_rsi, m1_adx FROM forge_signals
WHERE aurum_run_id=N AND outcome='TAKEN';
```
Same values.

6. Confirm Athena UI is unaffected (no field added, no breakage).

---

## 7. What this enables (future analyses)

Once the data starts accumulating, queries like these become possible:

```sql
-- Did M1 RSI confirm M5 RSI at every TAKEN?
SELECT direction, ROUND(AVG(rsi - m1_rsi),2) as m5_vs_m1_rsi_gap
FROM SIGNALS WHERE outcome='TAKEN' AND m1_rsi>0
GROUP BY direction;

-- M1 ADX vs M15 ADX vs M5 ADX at every TAKEN — full TF stack
SELECT direction, ROUND(AVG(m1_adx),1) as m1, ROUND(AVG(adx),1) as m5,
       ROUND(AVG(m15_adx),1) as m15
FROM SIGNALS WHERE outcome='TAKEN' AND m1_adx>0
GROUP BY direction;

-- Were M1 reversals (drop ≥10 pts in M1 RSI) preceding TAKEN SELLs?
-- (needs raw M1 history, not just SIGNALS, but the column gives us the anchor)
```

After 2-3 runs of data accumulation, we can decide whether Reading B (use M1 as an entry filter) is worth pursuing — and what threshold to use, backed by real numbers instead of guesswork.

---

## 8. Order of operations on the day of implementation

1. Verify Run 14 has fully completed (no in-flight tester writes to disturb)
2. Edit `ea/FORGE.mq5` per Step 4.1 (all changes a-h)
3. Edit `VERSION` → `2.7.16`
4. Run `make forge-compile` — fix any errors before moving on
5. Edit `python/scribe.py` per Step 4.2
6. Edit `python/bridge.py` per Step 4.3
7. Edit `schemas/openapi.yaml` (and maybe scribe_query_examples) per Step 4.4
8. Add the smoke test per Step 4.5
9. Update `docs/FORGE_ENTRY_CONDITIONS.md` per Step 4.6
10. Run `pytest tests/api/test_forge_27x_gates.py -q` — must pass
11. Reload `FORGE.ex5` in MT5 and start a short verification backtest
12. Confirm columns populate via the queries in Step 6
13. `git add ea/FORGE.mq5 VERSION config/scalper_config.json python/scribe.py python/bridge.py schemas/ tests/api/test_forge_27x_gates.py docs/`
14. Commit with message documenting v2.7.16 m1 logging
15. Push to origin/main

---

## 9. Out of scope (explicit non-goals for this change)

- **Reading B** — using M1 values to gate entries. Defer until ≥2 runs of data are collected.
- **M1 bar throttle** — JournalRecordSignal is already gate-protected by per-bar throttles upstream; M1 fetch happens at journaling time only.
- **Dashboard / Athena UI display** — no UI change. The columns are SQL-queryable for post-run forensics, which is sufficient.
- **Backfilling old runs** — m1_rsi/m1_adx are 0 for rows logged before the migration. We don't retroactively compute them.
- **M30 / H4 RSI logging** — already covered by M30 EMA gate and H4 regime fields. Not adding more TF columns in this change.

---

## 10. Decision needed before starting

Before I implement, please confirm:

1. **Do we want M1 logging now**, or wait until after Run 15 / 16 to see if the v2.7.15 status quo holds?
2. **Bump to v2.7.16** is the right version label (vs. e.g. v2.7.15.1)?
3. **Schema doc updates** in `schemas/openapi.yaml` — do you maintain that file or skip?

Once these are confirmed I'll execute Steps 4.1 → 4.6 in order, following the BUILD-BEFORE-COMMIT skill rule throughout.
