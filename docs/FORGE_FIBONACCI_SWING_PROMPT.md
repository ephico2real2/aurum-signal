# FORGE Fibonacci Swing Levels — Implementation Prompt

> **Self-contained prompt.** Follow every step exactly. No user input needed.

---

## 1. Objective

Add native **Fibonacci Swing Retracement** levels to FORGE, computed from the
same M5 lookback window used by the Volume Profile / VWAP. The feature provides:

1. **Directional bias gate** — VWAP position relative to Fib 50% confirms
   bullish/bearish bias (optional filter alongside existing H1/H4 checks).
2. **Structural TP targets** — Fib 38.2% and 61.8% serve as intermediate TP
   candidates alongside POC and VWAP.
3. **Full hot-reload** — all parameters are readable from `scalper_config.json`
   at runtime without recompilation. `.env` overrides flow through the existing
   sync pipeline.

---

## 2. Files to modify (in order)

| File | What changes |
|------|-------------|
| `ea/FORGE.mq5` | Globals, ScalperConfig struct, InitScalperConfig, ReadScalperConfig, new `ComputeFibonacciSwing()`, entry logic, TP logic, journal logs, `market_data.json`, `scalper_entry.json` |
| `config/scalper_config.json` | New keys in `indicators` and `bb_bounce` sections |
| `.env.example` | Document new `FORGE_FIB_*` env variables |
| `scripts/sync_scalper_config_from_env.py` | New MAPPING entries for Fib params |
| `python/bridge.py` | Flatten `fibonacci` from `market_data.json`, pass to SCRIBE |
| `python/lens.py` | Pass `fib_50`, `fib_382`, `fib_618` through to `log_market_snapshot` |
| `python/scribe.py` | DDL columns, migration, `log_market_snapshot` insert |

---

## 3. Step-by-step implementation

### Step 3.1 — FORGE globals

**Location:** After the existing VP globals (~line 229-233 area, right after
`datetime g_vp_last_calc = 0;`).

Add:

```mql5
// V2: Fibonacci swing retracement levels from M5 lookback
double   g_fib_high = 0.0;
double   g_fib_low  = 0.0;
double   g_fib_50   = 0.0;     // midpoint — directional bias reference
double   g_fib_382  = 0.0;     // 38.2% retracement
double   g_fib_618  = 0.0;     // 61.8% retracement
datetime g_fib_last_calc = 0;
```

### Step 3.2 — ScalperConfig struct

**Location:** Inside `struct ScalperConfig { ... }` — add after the existing
`int vp_bins;` line (~line 197):

```mql5
   // V2: Fibonacci swing levels
   bool   fib_bias_enabled;       // use VWAP-vs-Fib50 as directional confirmation
   bool   fib_tp_enabled;         // use Fib 38.2/61.8 as TP candidates
   int    fib_lookback;           // bars for swing high/low (0 = reuse vp_lookback)
```

### Step 3.3 — InitScalperConfig defaults

**Location:** Inside `InitScalperConfig()` — add after
`g_sc.vp_bins = 50;` (~line 1651):

```mql5
   g_sc.fib_bias_enabled = true;
   g_sc.fib_tp_enabled = true;
   g_sc.fib_lookback = 0;  // 0 means reuse vp_lookback
```

### Step 3.4 — ReadScalperConfig JSON parsing

**Location:** Inside `ReadScalperConfig()` — add after the `vp_bins` parsing
block (~after line 1917):

```mql5
   // V2 Fibonacci swing
   if(JsonHasKey(content, "fib_bias_enabled")) {
      v = JsonGetDouble(content, "fib_bias_enabled");
      g_sc.fib_bias_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "fib_tp_enabled")) {
      v = JsonGetDouble(content, "fib_tp_enabled");
      g_sc.fib_tp_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "fib_lookback")) {
      v = JsonGetDouble(content, "fib_lookback");
      if(v >= 0 && v <= 500) g_sc.fib_lookback = (int)v;
   }
```

### Step 3.5 — ReadScalperConfig diagnostics log

**Location:** Update the `PrintFormat("FORGE V2: ...")` line at the end of
`ReadScalperConfig()` (~line 1985) to include Fibonacci params. Add a second
PrintFormat line after the existing one:

```mql5
   PrintFormat("FORGE V2 FIB: fib_bias=%s fib_tp=%s fib_lookback=%d (effective=%d)",
               g_sc.fib_bias_enabled ? "true" : "false",
               g_sc.fib_tp_enabled ? "true" : "false",
               g_sc.fib_lookback,
               g_sc.fib_lookback > 0 ? g_sc.fib_lookback : g_sc.vp_lookback);
```

### Step 3.6 — New function: `ComputeFibonacciSwing()`

**Location:** Place immediately after `ComputeVolumeProfile()` (after its
closing `}`, before the `ReadOBZones()` function).

```mql5
// ── V2: Fibonacci swing levels from M5 high/low ────────────────
void ComputeFibonacciSwing() {
   if(TimeCurrent() - g_fib_last_calc < 60) return;
   g_fib_last_calc = TimeCurrent();

   int lookback = (g_sc.fib_lookback > 0) ? g_sc.fib_lookback : g_sc.vp_lookback;
   double hi[], lo[];
   ArraySetAsSeries(hi, true);
   ArraySetAsSeries(lo, true);
   if(CopyHigh(_Symbol, PERIOD_M5, 0, lookback, hi) < lookback) return;
   if(CopyLow(_Symbol, PERIOD_M5, 0, lookback, lo) < lookback) return;

   double swing_high = hi[ArrayMaximum(hi, 0, lookback)];
   double swing_low  = lo[ArrayMinimum(lo, 0, lookback)];
   if(swing_high <= swing_low) return;

   double range = swing_high - swing_low;
   g_fib_high = swing_high;
   g_fib_low  = swing_low;
   g_fib_50   = swing_low + range * 0.500;
   g_fib_382  = swing_low + range * 0.382;
   g_fib_618  = swing_low + range * 0.618;

   PrintFormat("FORGE FIB: high=%.2f low=%.2f fib50=%.2f fib382=%.2f fib618=%.2f lookback=%d",
               g_fib_high, g_fib_low, g_fib_50, g_fib_382, g_fib_618, lookback);
}
```

**Design notes:**

- Same 60-second throttle as `ComputeVolumeProfile()`.
- Reuses `vp_lookback` by default (`fib_lookback=0`), so config is minimal.
- Levels are measured from swing low upward (standard Fibonacci convention):
  `swing_low + range * ratio`.

### Step 3.7 — Call site in OnTimer

**Location:** Inside `OnTimer()`, in the `if(g_cycle % 20 == 0)` block (~line
550-554), add after `ReadOBZones();`:

```mql5
      ComputeFibonacciSwing();
```

### Step 3.8 — Directional bias gate in entry logic

**Location:** Inside `CheckNativeScalperSetups()`, after the H4 alignment
section and before the `// V2 Task 1: stricter H1 filter` comment (~line 2398-
2403 area). Add a Fibonacci VWAP bias check:

```mql5
   // V2 Fibonacci: VWAP-vs-Fib50 directional bias (optional gate)
   // When VWAP < Fib50 → bearish volume weighting → favours sell / discourages buy
   // When VWAP > Fib50 → bullish volume weighting → favours buy / discourages sell
   bool fib_bias_active = g_sc.fib_bias_enabled && (g_fib_50 > 0) && (g_vwap_price > 0);
   bool fib_ok_buy  = in_tester || !fib_bias_active || (g_vwap_price >= g_fib_50);
   bool fib_ok_sell = in_tester || !fib_bias_active || (g_vwap_price <= g_fib_50);
```

Then update the **bounce BUY** entry condition (currently ~line 2511):

**Before:**
```mql5
      if(mid <= m5_bb_l + proximity && m5_rsi < g_sc.bounce_rsi_buy_max
         && h1_ok_buy && h4_ok_buy && buy_reject && buy_bar0_ok && liquidity_ok) {
```

**After:**
```mql5
      if(mid <= m5_bb_l + proximity && m5_rsi < g_sc.bounce_rsi_buy_max
         && h1_ok_buy && h4_ok_buy && fib_ok_buy && buy_reject && buy_bar0_ok && liquidity_ok) {
```

And the **bounce SELL** entry condition (currently ~line 2530):

**Before:**
```mql5
      else if(mid >= m5_bb_u - proximity && m5_rsi > g_sc.bounce_rsi_sell_min
              && h1_ok_sell && h4_ok_sell && sell_reject && sell_bar0_ok && liquidity_ok) {
```

**After:**
```mql5
      else if(mid >= m5_bb_u - proximity && m5_rsi > g_sc.bounce_rsi_sell_min
              && h1_ok_sell && h4_ok_sell && fib_ok_sell && sell_reject && sell_bar0_ok && liquidity_ok) {
```

**Breakout entries** do NOT get this gate — breakouts trade with momentum
regardless of VWAP-vs-Fib position. The Fib bias is a mean-reversion filter
only.

### Step 3.9 — Fibonacci TP targeting in bounce entries

**Location:** In the bounce BUY TP logic (after existing POC/VWAP TP
adjustments, ~line 2518-2521):

After:
```mql5
         if(g_vwap_price > ask && g_vwap_price < tp1)
            tp1 = NormalizeDouble(g_vwap_price, _Digits);
```

Add:
```mql5
         if(g_sc.fib_tp_enabled && g_fib_382 > ask && g_fib_382 < tp1)
            tp1 = NormalizeDouble(g_fib_382, _Digits);
         if(g_sc.fib_tp_enabled && g_fib_618 > ask && g_fib_618 < tp2 && g_fib_618 > tp1)
            tp2 = NormalizeDouble(g_fib_618, _Digits);
```

In the bounce SELL TP logic (after existing POC/VWAP TP adjustments,
~line 2538-2540):

After:
```mql5
         if(g_vwap_price < bid && g_vwap_price > tp1)
            tp1 = NormalizeDouble(g_vwap_price, _Digits);
```

Add:
```mql5
         if(g_sc.fib_tp_enabled && g_fib_618 < bid && g_fib_618 > tp1)
            tp1 = NormalizeDouble(g_fib_618, _Digits);
         if(g_sc.fib_tp_enabled && g_fib_382 < bid && g_fib_382 > tp2 && g_fib_382 < tp1)
            tp2 = NormalizeDouble(g_fib_382, _Digits);
```

**Logic:** For BUY bounces, Fib 38.2% is a conservative TP1 target (closer to
the low), Fib 61.8% is a higher TP2 target. For SELL bounces the levels are
flipped — Fib 61.8% is closer to current sell price, Fib 38.2% is a deeper
target. The existing `min_tp1` / `min_tp2` guards still enforce minimum ATR-
based distances, so Fib targets never produce dangerously close TPs.

### Step 3.10 — Journal entry log

**Location:** In the trade entry `Print(...)` block (~line 2776-2785 area),
add `FIB50` after the existing `VWAP` field:

Find:
```mql5
         " VWAP=", DoubleToString(g_vwap_price, 2),
         " OB_zones=", IntegerToString(g_ob_zone_count),
```

Replace with:
```mql5
         " VWAP=", DoubleToString(g_vwap_price, 2),
         " FIB50=", DoubleToString(g_fib_50, 2),
         " OB_zones=", IntegerToString(g_ob_zone_count),
```

### Step 3.11 — `market_data.json` output

**Location:** In `WriteMarketData()`, find the existing `volume_profile` block:

```mql5
   j += "\"volume_profile\":{";
   j += "\"poc_price\":" + DoubleToString(g_poc_price, 2) + ",";
   j += "\"poc_strength\":" + DoubleToString(g_poc_strength, 3) + ",";
   j += "\"vwap_price\":" + DoubleToString(g_vwap_price, 2);
   j += "},";
```

Replace with:
```mql5
   j += "\"volume_profile\":{";
   j += "\"poc_price\":" + DoubleToString(g_poc_price, 2) + ",";
   j += "\"poc_strength\":" + DoubleToString(g_poc_strength, 3) + ",";
   j += "\"vwap_price\":" + DoubleToString(g_vwap_price, 2) + ",";
   j += "\"fib_high\":" + DoubleToString(g_fib_high, 2) + ",";
   j += "\"fib_low\":" + DoubleToString(g_fib_low, 2) + ",";
   j += "\"fib_50\":" + DoubleToString(g_fib_50, 2) + ",";
   j += "\"fib_382\":" + DoubleToString(g_fib_382, 2) + ",";
   j += "\"fib_618\":" + DoubleToString(g_fib_618, 2);
   j += "},";
```

### Step 3.12 — `scalper_entry.json` output

**Location:** In the scalper_entry.json block, after the existing
`"vwap_price"` line:

```mql5
   ej += "\"fib_50\":" + DoubleToString(g_fib_50, 2) + ",";
   ej += "\"fib_382\":" + DoubleToString(g_fib_382, 2) + ",";
   ej += "\"fib_618\":" + DoubleToString(g_fib_618, 2) + ",";
```

---

### Step 3.13 — `config/scalper_config.json`

**Location:** In the `"indicators"` section, after `"vp_bins": 50`:

```json
    "fib_bias_enabled": 1,
    "fib_tp_enabled": 1,
    "fib_lookback": 0
```

Remember to add the trailing comma after `"vp_bins": 50,` so the JSON remains
valid.

### Step 3.14 — `.env.example`

**Location:** After the existing V2 section (after `FORGE_BREAKOUT_RETEST_MAX_BARS`):

```
# Fibonacci swing levels (VWAP-vs-Fib50 directional bias + Fib TP targets):
# FORGE_FIB_BIAS_ENABLED=1
# FORGE_FIB_TP_ENABLED=1
# FORGE_FIB_LOOKBACK=0
```

### Step 3.15 — `scripts/sync_scalper_config_from_env.py`

**Location:** In the `MAPPING` dict, after the
`"FORGE_BREAKOUT_RETEST_MAX_BARS"` entry:

```python
    "FORGE_FIB_BIAS_ENABLED": ("indicators", "fib_bias_enabled", "bool01", None, None),
    "FORGE_FIB_TP_ENABLED": ("indicators", "fib_tp_enabled", "bool01", None, None),
    "FORGE_FIB_LOOKBACK": ("indicators", "fib_lookback", "int", 0.0, 500.0),
```

---

### Step 3.16 — `python/bridge.py`

**Location 1:** In `_extract_forge_thresholds()`, the `vp` dict already
extracts from `volume_profile`. Add Fib fields:

After:
```python
        "vwap_price": vp.get("vwap_price"),
```

Add:
```python
        "fib_50": vp.get("fib_50"),
        "fib_382": vp.get("fib_382"),
        "fib_618": vp.get("fib_618"),
```

**Location 2:** In `_check_forge_scalper_entry()`, in the `open_context` extras
dict (where `poc_price`, `vwap_price`, `pattern_score` are passed), add:

```python
                    "fib_50": entry.get("fib_50"),
                    "fib_382": entry.get("fib_382"),
                    "fib_618": entry.get("fib_618"),
```

**Location 3:** In the BRIDGE activity log for `FORGE_SCALP_ENTRY` (the
`json.dumps` block), add after the `"vwap_price"` line:

```python
                "fib_50": entry.get("fib_50"),
```

### Step 3.17 — `python/lens.py`

**Location:** In the `mt5_data` pass-through dict (where `poc_price`,
`vwap_price` are already forwarded to `log_market_snapshot`), add:

```python
                    "fib_50": mt5_data.get("fib_50"),
                    "fib_382": mt5_data.get("fib_382"),
                    "fib_618": mt5_data.get("fib_618"),
```

### Step 3.18 — `python/scribe.py`

**Location 1 — DDL:** In the `market_snapshots` CREATE TABLE, after the
`vwap_price REAL,` line:

```sql
    fib_50 REAL,
    fib_382 REAL,
    fib_618 REAL,
```

**Location 2 — Migration:** In the migration section (after the existing
`vwap_price` migration block), add:

```python
        if "fib_50" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN fib_50 REAL")
            log.info("SCRIBE migration: added fib_50 to market_snapshots")
        if "fib_382" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN fib_382 REAL")
            log.info("SCRIBE migration: added fib_382 to market_snapshots")
        if "fib_618" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN fib_618 REAL")
            log.info("SCRIBE migration: added fib_618 to market_snapshots")
```

**Location 3 — `log_market_snapshot` INSERT:** Add `fib_50`, `fib_382`,
`fib_618` to both the column list and the VALUES placeholders, and add the
corresponding `data.get(...)` calls:

```python
                 poc_price,vwap_price,
                 fib_50,fib_382,fib_618)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
```

And in the values tuple, after `data.get("vwap_price")`:

```python
                 data.get("fib_50"),
                 data.get("fib_382"),
                 data.get("fib_618")))
```

---

## 4. Verification checklist

After implementation, run these checks:

1. **Compile:** `make forge-compile` — must succeed with no errors.
2. **Config sync:** `python3 scripts/sync_scalper_config_from_env.py` — verify
   `fib_bias_enabled`, `fib_tp_enabled`, `fib_lookback` appear in output.
3. **Config diff:** `diff config/scalper_config.json MT5/scalper_config.json` —
   must show no differences.
4. **Reload services:** `make reload` — all 11 components healthy.
5. **MT5 reload:** Remove FORGE from chart → re-drag from Navigator.
6. **market_data.json:** Verify `volume_profile` section contains `fib_high`,
   `fib_low`, `fib_50`, `fib_382`, `fib_618` with non-zero values.
7. **SCRIBE DB:** Run:
   ```sql
   SELECT fib_50, fib_382, fib_618 FROM market_snapshots
   ORDER BY id DESC LIMIT 3;
   ```
   All three columns should have values.
8. **Journal log:** Check MT5 Experts tab for:
   - `FORGE FIB: high=... low=... fib50=... fib382=... fib618=...`
   - `FORGE V2 FIB: fib_bias=true fib_tp=true ...`

## 5. Runtime management (no recompilation needed)

| What | How |
|------|-----|
| **Disable Fib bias gate** | Set `"fib_bias_enabled": 0` in `config/scalper_config.json` → FORGE hot-reloads every 20 timer cycles |
| **Disable Fib TP targeting** | Set `"fib_tp_enabled": 0` in config |
| **Change Fib lookback** | Set `"fib_lookback": 200` in config (0 = reuse `vp_lookback`) |
| **Override via .env** | Set `FORGE_FIB_BIAS_ENABLED=0` in `.env` → run `make scalper-env-sync` (or `python3 scripts/sync_scalper_config_from_env.py`) |
| **Verify config reached MT5** | `diff config/scalper_config.json MT5/scalper_config.json` should match |

All Fibonacci parameters follow the same hot-reload pattern as existing V2
features: FORGE reads `scalper_config.json` every 20 OnTimer cycles (~20
seconds) and applies the new values immediately. No recompilation or MT5 restart
required for parameter changes.

---

## 6. Architecture summary

```
                    ┌──────────────────────────────────────┐
  .env overrides ──▶│ sync_scalper_config_from_env.py       │
                    │   MAPPING: FORGE_FIB_* → indicators.* │
                    └──────────────┬───────────────────────┘
                                   │ writes
                    ┌──────────────▼───────────────────────┐
                    │ config/scalper_config.json            │
                    │   indicators.fib_bias_enabled: 1      │
                    │   indicators.fib_tp_enabled: 1        │
                    │   indicators.fib_lookback: 0          │
                    └──────────────┬───────────────────────┘
                                   │ copied to MT5/
                    ┌──────────────▼───────────────────────┐
                    │ FORGE.mq5 (ReadScalperConfig)        │
                    │   g_sc.fib_bias_enabled = true        │
                    │   g_sc.fib_tp_enabled = true          │
                    │   g_sc.fib_lookback = 0 (→100)        │
                    │                                       │
                    │ ComputeFibonacciSwing() every 60s     │
                    │   g_fib_high, g_fib_low               │
                    │   g_fib_50, g_fib_382, g_fib_618      │
                    │                                       │
                    │ CheckNativeScalperSetups()            │
                    │   fib_ok_buy / fib_ok_sell (bias)     │
                    │   Fib TP targeting (bounce only)      │
                    │                                       │
                    │ market_data.json → volume_profile.*   │
                    │ scalper_entry.json → fib_50/382/618   │
                    └──────────────┬───────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
         BRIDGE                 LENS               SCRIBE
    _extract_forge_       pass-through       market_snapshots
    thresholds()          to log_market_     fib_50, fib_382,
    flattens vp.*         snapshot()         fib_618 columns
```

---

*End of prompt.*
