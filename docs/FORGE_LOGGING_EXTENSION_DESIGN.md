# FORGE Logging Extension Design — close §3 gaps + add OHLC-derived atoms

**Status**: design — ready to implement after Run 23 completes
**Target version**: FORGE v2.7.36 (post-Run 23)
**Motivation**: Atlas §3 logged-as-zero gap (m15_adx, macd_histogram, pattern_score) + case study §4b V3 OHLC atoms cannot be historically validated. Fix the logging once; every future run produces full atom traces for cross-day validation.

---

## §0. Data availability — VERIFIED from production (2026-05-12)

Before planning ANY new logging, verified what the broker (Vantage International Demo)
actually serves. Sources: `ea/FORGE.mq5` production code + live `market_data.json`.

### §0.1. All planned v2.7.36 atoms — verified available

| Planned atom | Source | Status |
|---|---|---|
| `h4_trend_strength` | `market_data.json indicators_h4.{ema_20, ema_50, atr_14}` | ✓ verified |
| `m15_trend_strength` | `indicators_m15.{ema_20, ema_50, atr_14}` | ✓ verified |
| `m15_adx` | `indicators_m15.adx` | ✓ verified (currently logged as 0 — call-site bug) |
| `macd_histogram` (M5) | `indicators_m5.macd_hist` | ✓ verified (currently logged as 0 — call-site bug) |
| `h1_di_plus`, `h1_di_minus` | `iADX(_Symbol, PERIOD_H1, ..., buffer 1/2)` — FORGE.mq5:5700-5704 confirms working | ✓ verified |
| `iHigh/iLow/iOpen/iClose` on M1/M5/M15/M30/H1/H4/D1 | FORGE.mq5 uses all 7 in production (lines 4173, 4188-4193, 4304, 5524-5527) | ✓ verified |
| `day_high`, `day_low`, `day_open` | `iHigh/iLow/iOpen(_Symbol, PERIOD_D1, 0)` | ✓ verified |
| `m5_lh_cascade` / `m5_hl_cascade` | sequential `iHigh/iLow(_Symbol, PERIOD_M5, 1..3)` | ✓ verified |
| `m5_body_pct` | `iOpen/iClose/iHigh/iLow(_Symbol, PERIOD_M5, 1)` | ✓ verified |
| `poc_price`, `vwap_price`, `fib_50` | `volume_profile` section of market_data.json | ✓ already logged in SIGNALS |

**Net conclusion**: every planned v2.7.36 atom is broker-provided and EA-computable.
No new indicator subscriptions or external data sources required. Implementation can
proceed with confidence that the data layer exists.

### §0.2. What broker does NOT serve (skip these)

| Wanted but unavailable | Why |
|---|---|
| H4 MACD histogram | not in `indicators_h4` section |
| M1 MACD histogram | not in `indicators_m1` section |
| H4/D1 ADX directional indices (DI+/DI−) | not exposed; FORGE only reads H1 DI buffers |
| Volume profile beyond POC + Fib levels | broker doesn't expose Value Area High/Low; would require own computation |
| Order book depth (Level II) | not in feed |
| Tick-level COT / institutional positioning | external data, not broker |

### §0.3. Verification command sequence

```bash
# 1. Confirm FORGE production uses the API for the timeframe in question
grep -nE "iHigh\(_Symbol, PERIOD_D1|iLow\(_Symbol, PERIOD_M5" ea/FORGE.mq5

# 2. Confirm live broker exposes the indicator
cat "/Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/market_data.json" | python3 -m json.tool | grep -A 10 "indicators_h4"

# 3. Confirm broker capabilities for the symbol
cat "/Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/broker_info.json"
```

If a planned atom doesn't show up in steps 1+2, scope it OUT before writing the implementation plan.

---

## §1. Goals

1. **Close §3 gaps**: pass actual values for `m15_adx`, `macd_histogram`, `pattern_score` in all 52 `JournalRecordSignal` call sites where they currently default to 0.
2. **Add new SIGNALS columns**:
   - `h4_trend` (h4_trend_strength)
   - `m15_trend` (m15_trend_strength)
   - `h1_di_balance` (h1_di_plus − h1_di_minus)
   - `day_high`, `day_low`, `day_open` (D1 OHLC)
   - `m5_open_1`, `m5_high_1`, `m5_low_1`, `m5_close_1` (M5 prior-bar OHLC)
   - `m5_lh_cascade` (int 0/1 — 3 consecutive lower-highs)
   - `m5_hl_cascade` (int 0/1 — 3 consecutive higher-lows)
   - `m5_body_pct` (body / range of prior bar)
3. **Scribe mirror**: bridge sync (`bridge.py` or equivalent) auto-picks up new columns; `forge_signals` table in scribe gets new columns via ALTER TABLE migration.
4. **Backward compatible**: existing reads of SIGNALS continue to work; new columns NULL on old runs.

---

## §2. Affected files

| File | Change | Lines |
|---|---|---|
| `ea/FORGE.mq5` — SIGNALS CREATE TABLE (~`:4691`) | Add new columns to `CREATE TABLE IF NOT EXISTS SIGNALS` | ~12 new columns |
| `ea/FORGE.mq5` — JournalRecordSignal signature (`:4868`) | Add new parameters (default 0/NULL for backward compat) | sig change |
| `ea/FORGE.mq5` — JournalRecordSignal INSERT SQL (`:4889+`) | Add columns + values to INSERT statement | ~30 lines |
| `ea/FORGE.mq5` — call sites (52 locations) | Pass actual computed values instead of literal `0` | mechanical |
| `python/bridge*.py` (scribe sync) | ALTER TABLE `forge_signals` to add new columns; map source → scribe | TBD |
| Optionally: ALTER scribe_intelligence.db existing rows | One-time migration script | optional |

---

## §3. New SIGNALS column schema

```sql
ALTER TABLE SIGNALS ADD COLUMN h4_trend REAL DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN m15_trend REAL DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN h1_di_balance REAL DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN day_high REAL DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN day_low REAL DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN day_open REAL DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN m5_open_1 REAL DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN m5_high_1 REAL DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN m5_low_1 REAL DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN m5_close_1 REAL DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN m5_lh_cascade INTEGER DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN m5_hl_cascade INTEGER DEFAULT 0;
ALTER TABLE SIGNALS ADD COLUMN m5_body_pct REAL DEFAULT 0;
```

For the FORGE.mq5 `CreateTableIfNotExists` path: add these to the inline schema definition so fresh DBs are created with the columns; the `ALTER TABLE` lines run as guarded migrations for existing DBs.

---

## §4. New JournalRecordSignal signature

```mql5
void JournalRecordSignal(
   string outcome, string gate_reason,
   string setup_type, string direction,
   double price, double spread_val, double atr,
   double rsi, double adx,
   double bb_u, double bb_l, double bb_m,
   int pattern_score, double h1_trend,
   int high_vol_flag,
   double macd_hist = 0.0,
   double m15_adx_val = 0.0,
   double lot_factor_val = 0.0,
   // NEW v2.7.36 params (all default 0 for backward compat)
   double h4_trend_val = 0.0,
   double m15_trend_val = 0.0,
   double h1_di_bal_val = 0.0,
   double day_high_val = 0.0,
   double day_low_val = 0.0,
   double day_open_val = 0.0,
   double m5_open_1_val = 0.0,
   double m5_high_1_val = 0.0,
   double m5_low_1_val = 0.0,
   double m5_close_1_val = 0.0,
   int m5_lh_cascade_val = 0,
   int m5_hl_cascade_val = 0,
   double m5_body_pct_val = 0.0
) { ... }
```

Backward compat: every existing call site still works (new params default to 0).

---

## §5. Helper function — compute the bar-quality atoms once per tick

```mql5
// Computed in ScalperEvaluate() before any JournalRecordSignal call.
// Cache the values; pass to every JournalRecordSignal in this evaluation cycle.
double g_eval_day_high = iHigh(_Symbol, PERIOD_D1, 0);
double g_eval_day_low  = iLow(_Symbol, PERIOD_D1, 0);
double g_eval_day_open = iOpen(_Symbol, PERIOD_D1, 0);
double g_eval_m5_open_1 = iOpen(_Symbol, PERIOD_M5, 1);
double g_eval_m5_high_1 = iHigh(_Symbol, PERIOD_M5, 1);
double g_eval_m5_low_1  = iLow(_Symbol, PERIOD_M5, 1);
double g_eval_m5_close_1 = iClose(_Symbol, PERIOD_M5, 1);

int g_eval_m5_lh_cascade =
     (iHigh(_Symbol,PERIOD_M5,1) < iHigh(_Symbol,PERIOD_M5,2)
   && iHigh(_Symbol,PERIOD_M5,2) < iHigh(_Symbol,PERIOD_M5,3)) ? 1 : 0;
int g_eval_m5_hl_cascade =
     (iLow(_Symbol,PERIOD_M5,1) > iLow(_Symbol,PERIOD_M5,2)
   && iLow(_Symbol,PERIOD_M5,2) > iLow(_Symbol,PERIOD_M5,3)) ? 1 : 0;

double _m5_body  = MathAbs(g_eval_m5_close_1 - g_eval_m5_open_1);
double _m5_range = g_eval_m5_high_1 - g_eval_m5_low_1;
double g_eval_m5_body_pct = (_m5_range > 0.0) ? (_m5_body / _m5_range) : 0.0;
```

Pass these globals to every `JournalRecordSignal` call. ~13 new args per call but they're already computed (single CopyBuffer/iX call each per tick).

---

## §6. Implementation steps (in order)

1. **Compile-safety prep**: bump VERSION 2.7.35 → 2.7.36 (don't touch until Run 23 ends).
2. **Schema migration in OnInit**: add `ALTER TABLE SIGNALS ADD COLUMN ...` for each new column (wrapped in try/sqlite-ignore-error so re-runs are idempotent).
3. **Helper computation block**: insert the global-eval calculations at the top of `ScalperEvaluate()` so every JournalRecordSignal call has the values ready.
4. **JournalRecordSignal signature**: extend with the 13 new optional params.
5. **JournalRecordSignal INSERT**: add new columns + values to the SQL.
6. **Update existing call sites in priority order** (don't try all 52 at once):
   - Tier A (high-value, must-have): MOMENTUM_DUMP filter chain (~10 calls), BB_PULLBACK_SCALP (~6 calls), BB_BOUNCE (~8 calls), BB_BREAKOUT (~12 calls)
   - Tier B (nice-to-have): cooldown gates, m1 gates, regime gates
   - Tier C (auxiliary): cascade arming logs, retest logs
7. **Sync mapping check**: confirm `scripts/sync_scalper_config_from_env.py` doesn't need changes (it shouldn't — only env vars are synced).
8. **Bridge / scribe migration**: add ALTER TABLE for `forge_signals` in scribe DB. Find the bridge file (likely `python/bridge.py` or `python/sync_journal_to_scribe.py`) and verify it auto-detects new columns via the `PRAGMA table_info(forge_signals)` pattern or manual UPDATE.
9. **Test compile**: `make forge-compile`. Check FORGE.ex5 builds.
10. **Test mode**: launch a 1-day backtest on a fresh DB. Verify new columns are populated (non-zero values where applicable).
11. **Validate cross-day**: re-run §5.1 / §5.7 composites against the new SIGNALS data — should now have m15_trend, h4_trend, day_high, m5_lh_cascade populated.
12. **Update atlas §3** (logging gaps): mark closed for the listed indicators; add §1 row updates marking "✓ logged" for the new columns.
13. **Update atlas §11** (scribe schema): reflect the new forge_signals columns.

---

## §7. Estimated scope

| Item | LOC | Risk |
|---|---|---|
| Schema migration | ~15 lines | Low — ALTER TABLE is well-known SQLite |
| Helper computation block | ~20 lines | Low — straightforward MQL5 |
| JournalRecordSignal signature | ~15 lines (sig + body INSERT) | Medium — touched 52 call sites |
| Call site updates | ~150-200 lines (3-4 per site x 52) | Medium-High — mechanical but error-prone if rushed |
| Bridge / scribe migration | TBD (need to inspect bridge code) | Low if it's `PRAGMA table_info`-driven; Medium if hand-mapped |
| **Total** | **~200-250 lines** | **Medium overall** |

---

## §8. Validation post-implementation

After Run 24 (first run with extended logging) produces data:

1. Query `SELECT COUNT(*), AVG(m15_adx), AVG(macd_histogram), AVG(pattern_score) FROM SIGNALS WHERE run_id=N` — all non-zero (was always 0 before).
2. Query `SELECT m5_lh_cascade, COUNT(*) FROM SIGNALS WHERE run_id=N GROUP BY m5_lh_cascade` — should see ~5-15% of rows with cascade=1 (intraday-bear pockets).
3. Query a known Apr 8 12:00-equivalent in the new run — verify HID_BEAR div + m5_lh_cascade both flag → composite would have fired.
4. Update case study `docs/FORGE_CASE_STUDY_2026_03_31_to_04_08.md` §4b with Layer-1 (validatable) versions of the V3 composites — now possible because OHLC atoms are logged.
5. Atlas §10 changelog entry.

---

## §9. Open questions

1. **Bridge file location**: need to find which Python file syncs source SIGNALS → scribe forge_signals. Search candidates: `bridge.py`, `scribe.py`, `sync_*.py` in `/Users/olasumbo/signal_system/python/`.
2. **scribe historic data**: should old forge_signals rows be backfilled with NULLs (default) or stay as zero-filled? Probably leave zero-filled — new rows from v2.7.36 onward have real values; old rows are clearly identifiable as "pre-logging-extension."
3. **Performance**: 13 new iX calls per ScalperEvaluate tick. On a 1-min M5 tick rate that's negligible, but verify no measurable slowdown in tester.
4. **D1 freshness at session open**: iHigh(_Symbol, PERIOD_D1, 0) at 00:01 UTC = current day's first bar; values will be near OHLC of that single bar. Handle gracefully (atoms still work — day_high == day_low at session open, expanding as day progresses).

---

## §10. Cross-references

- Atlas §3 (logging gaps) — the gaps this design closes
- Atlas §1 (indicator inventory) — destination for "now logged" status updates
- Atlas §11 (scribe schema) — destination for scribe schema updates
- Case study §4b — V3 composites that this enables to validate
- Indicator atlas §5.1 + §5.7 — composites whose Layer-1 versions become validatable

---

## §11. Changelog

| Date | Change |
|---|---|
| 2026-05-12 | Design doc created. To execute post-Run-23. Targets v2.7.36. |
