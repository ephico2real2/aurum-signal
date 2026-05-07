# FORGE RSI Divergence — Implementation Prompt

> **Self-contained prompt.** Follow every step exactly. No user input needed.
> **Reference:** MQL5 article 17198 — "RSI Sentinel Tool" by Christian Benjamin.
> **Source EA:** `/Users/olasumbo/Downloads/RSI_DIVERGENCE.mq5`

---

## 1. Objective

Add native **RSI Divergence Detection** to FORGE as an entry confirmation
filter, with chart visualization, journal logging, and full data pipeline
(scalper_entry.json → BRIDGE → SCRIBE → Telegram).

Four divergence types are detected:

| Type | Price Action | RSI Action | Usage in FORGE |
|------|-------------|-----------|----------------|
| Regular Bullish | Lower Low | Higher Low | BB_BOUNCE buy confirmation |
| Regular Bearish | Higher High | Lower High | BB_BOUNCE sell confirmation |
| Hidden Bullish | Higher Low | Lower Low | BB_BREAKOUT buy continuation |
| Hidden Bearish | Lower High | Higher High | BB_BREAKOUT sell continuation |

All parameters are hot-reloadable via `scalper_config.json` without
recompilation.

---

## 2. Files to modify (in order)

| File | What changes |
|------|-------------|
| `ea/FORGE.mq5` | Globals, ScalperConfig, InitScalperConfig, ReadScalperConfig, new `DetectRSIDivergence()`, new `DrawDivergenceArrow()`, entry logic, journal log, `market_data.json`, `scalper_entry.json` |
| `config/scalper_config.json` | New keys in `indicators` section |
| `.env.example` | Document new `FORGE_RSI_DIV_*` env variables |
| `scripts/sync_scalper_config_from_env.py` | New MAPPING entries |
| `python/bridge.py` | Flatten divergence from `market_data.json`, pass to SCRIBE, add to Telegram alert |
| `python/lens.py` | Pass `rsi_divergence` through to `log_market_snapshot` |
| `python/scribe.py` | DDL column, migration, `log_market_snapshot` insert |

---

## 3. Step-by-step implementation

### Step 3.1 — FORGE globals

**Location:** After the Fibonacci globals (after `datetime g_fib_last_calc = 0;`).

```mql5
// V2: RSI divergence detection
string   g_rsi_div_type = "NONE";   // NONE | REG_BULL | REG_BEAR | HID_BULL | HID_BEAR
datetime g_rsi_div_last_calc = 0;
datetime g_rsi_div_last_arrow_bar = 0;
```

### Step 3.2 — ScalperConfig struct

**Location:** Inside `struct ScalperConfig { ... }` — add after the Fibonacci
fields (after `int fib_lookback;`):

```mql5
   // V2: RSI divergence
   bool   rsi_div_enabled;
   int    rsi_div_lookback;       // bars to scan for swing points (default 20)
   int    rsi_div_swing_bars;     // left/right bars for swing detection (default 3)
   double rsi_div_min_rsi_diff;   // minimum RSI gap between swings (default 1.0)
   bool   rsi_div_draw_arrows;    // draw chart arrows on trade-relevant divergences
```

### Step 3.3 — InitScalperConfig defaults

**Location:** After `g_sc.fib_lookback = 0;`:

```mql5
   g_sc.rsi_div_enabled = true;
   g_sc.rsi_div_lookback = 20;
   g_sc.rsi_div_swing_bars = 3;
   g_sc.rsi_div_min_rsi_diff = 1.0;
   g_sc.rsi_div_draw_arrows = true;
```

### Step 3.4 — ReadScalperConfig JSON parsing

**Location:** After the Fibonacci parsing block:

```mql5
   // V2 RSI divergence
   if(JsonHasKey(content, "rsi_div_enabled")) {
      v = JsonGetDouble(content, "rsi_div_enabled");
      g_sc.rsi_div_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "rsi_div_lookback")) {
      v = JsonGetDouble(content, "rsi_div_lookback");
      if(v >= 5 && v <= 200) g_sc.rsi_div_lookback = (int)v;
   }
   if(JsonHasKey(content, "rsi_div_swing_bars")) {
      v = JsonGetDouble(content, "rsi_div_swing_bars");
      if(v >= 1 && v <= 10) g_sc.rsi_div_swing_bars = (int)v;
   }
   if(JsonHasKey(content, "rsi_div_min_rsi_diff")) {
      v = JsonGetDouble(content, "rsi_div_min_rsi_diff");
      if(v >= 0.0 && v <= 20.0) g_sc.rsi_div_min_rsi_diff = v;
   }
   if(JsonHasKey(content, "rsi_div_draw_arrows")) {
      v = JsonGetDouble(content, "rsi_div_draw_arrows");
      g_sc.rsi_div_draw_arrows = (v >= 0.5);
   }
```

### Step 3.5 — ReadScalperConfig diagnostics log

**Location:** Add after the existing `FORGE V2 FIB:` PrintFormat:

```mql5
   PrintFormat("FORGE V2 RSI_DIV: enabled=%s lookback=%d swing_bars=%d min_diff=%.1f arrows=%s",
               g_sc.rsi_div_enabled ? "true" : "false",
               g_sc.rsi_div_lookback,
               g_sc.rsi_div_swing_bars,
               g_sc.rsi_div_min_rsi_diff,
               g_sc.rsi_div_draw_arrows ? "true" : "false");
```

### Step 3.6 — New function: `DetectRSIDivergence()`

**Location:** Place after `ComputeFibonacciSwing()`, before `ReadOBZones()`.

This function scans the M5 RSI and price for swing divergences and updates
`g_rsi_div_type`. Throttled to once per M5 bar.

```mql5
// ── V2: RSI divergence detection ────────────────────────────────
void DetectRSIDivergence() {
   if(!g_sc.rsi_div_enabled) { g_rsi_div_type = "NONE"; return; }
   datetime bar_time = iTime(_Symbol, PERIOD_M5, 0);
   if(bar_time == g_rsi_div_last_calc) return;
   g_rsi_div_last_calc = bar_time;

   int lb = g_sc.rsi_div_lookback;
   int sw = g_sc.rsi_div_swing_bars;
   double rsi_buf[], hi_buf[], lo_buf[];
   ArraySetAsSeries(rsi_buf, true);
   ArraySetAsSeries(hi_buf, true);
   ArraySetAsSeries(lo_buf, true);
   if(CopyBuffer(g_mtf[0].h_rsi, 0, 0, lb, rsi_buf) < lb) return;
   if(CopyHigh(_Symbol, PERIOD_M5, 0, lb, hi_buf) < lb) return;
   if(CopyLow(_Symbol, PERIOD_M5, 0, lb, lo_buf) < lb) return;

   // Find two most recent swing lows
   int sl1 = -1, sl2 = -1;
   for(int i = sw; i < lb - sw; i++) {
      bool is_low = true;
      for(int j = 1; j <= sw && is_low; j++) {
         if(lo_buf[i] > lo_buf[i-j] || lo_buf[i] > lo_buf[i+j]) is_low = false;
      }
      if(is_low) {
         if(sl1 < 0) sl1 = i;
         else if(sl2 < 0) { sl2 = i; break; }
      }
   }
   // Find two most recent swing highs
   int sh1 = -1, sh2 = -1;
   for(int i = sw; i < lb - sw; i++) {
      bool is_hi = true;
      for(int j = 1; j <= sw && is_hi; j++) {
         if(hi_buf[i] < hi_buf[i-j] || hi_buf[i] < hi_buf[i+j]) is_hi = false;
      }
      if(is_hi) {
         if(sh1 < 0) sh1 = i;
         else if(sh2 < 0) { sh2 = i; break; }
      }
   }

   double min_diff = g_sc.rsi_div_min_rsi_diff;
   string prev_type = g_rsi_div_type;
   g_rsi_div_type = "NONE";

   // Bullish divergence (swing lows)
   if(sl1 >= 0 && sl2 >= 0) {
      if(lo_buf[sl1] < lo_buf[sl2] && rsi_buf[sl1] > rsi_buf[sl2]
         && (rsi_buf[sl1] - rsi_buf[sl2]) >= min_diff)
         g_rsi_div_type = "REG_BULL";
      else if(lo_buf[sl1] > lo_buf[sl2] && rsi_buf[sl1] < rsi_buf[sl2]
              && (rsi_buf[sl2] - rsi_buf[sl1]) >= min_diff)
         g_rsi_div_type = "HID_BULL";
   }
   // Bearish divergence (swing highs) — only if no bullish already found
   if(g_rsi_div_type == "NONE" && sh1 >= 0 && sh2 >= 0) {
      if(hi_buf[sh1] > hi_buf[sh2] && rsi_buf[sh1] < rsi_buf[sh2]
         && (rsi_buf[sh2] - rsi_buf[sh1]) >= min_diff)
         g_rsi_div_type = "REG_BEAR";
      else if(hi_buf[sh1] < hi_buf[sh2] && rsi_buf[sh1] > rsi_buf[sh2]
              && (rsi_buf[sh1] - rsi_buf[sh2]) >= min_diff)
         g_rsi_div_type = "HID_BEAR";
   }

   if(g_rsi_div_type != prev_type && g_rsi_div_type != "NONE")
      PrintFormat("FORGE RSI_DIV: %s detected (swingLows=%d/%d swingHighs=%d/%d)",
                  g_rsi_div_type, sl1, sl2, sh1, sh2);
}
```

### Step 3.7 — New function: `DrawDivergenceArrow()`

**Location:** Immediately after `DetectRSIDivergence()`.

This draws an arrow on the chart when a divergence contributes to an actual
trade entry. Called from `CheckNativeScalperSetups()` after a trade is opened.

```mql5
void DrawDivergenceArrow(string div_type, double price, datetime time_val) {
   if(!g_sc.rsi_div_draw_arrows || div_type == "NONE") return;
   if(time_val == g_rsi_div_last_arrow_bar) return;
   g_rsi_div_last_arrow_bar = time_val;

   string name = "FORGE_DIV_" + IntegerToString((long)time_val);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int code = 0;
   color clr = clrWhite;

   if(StringFind(div_type, "BULL") >= 0) {
      code = 233;
      clr = clrLime;
      price -= 5.0 * point;
   } else {
      code = 234;
      clr = clrOrangeRed;
      price += 5.0 * point;
   }

   if(ObjectFind(0, name) < 0) {
      ObjectCreate(0, name, OBJ_ARROW, 0, time_val, price);
      ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
      ObjectSetInteger(0, name, OBJPROP_ARROWCODE, code);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
      ObjectSetString(0, name, OBJPROP_TOOLTIP, div_type);
   }
}
```

### Step 3.8 — Call site in OnTimer

**Location:** In the `if(g_cycle % 20 == 0)` block, add after
`ComputeFibonacciSwing();`:

```mql5
      DetectRSIDivergence();
```

### Step 3.9 — Entry logic: divergence as confirmation filter

**Location:** Inside `CheckNativeScalperSetups()`, after the Fibonacci bias
variables (after the `fib_ok_buy` / `fib_ok_sell` block):

```mql5
   // V2 RSI divergence: additional confirmation for bounce/breakout entries
   bool rsi_div_active = g_sc.rsi_div_enabled && (g_rsi_div_type != "NONE");
   bool rsi_div_buy_bounce  = !rsi_div_active || (g_rsi_div_type == "REG_BULL");
   bool rsi_div_sell_bounce = !rsi_div_active || (g_rsi_div_type == "REG_BEAR");
   bool rsi_div_buy_breakout  = true;  // hidden divergence is optional for breakouts
   bool rsi_div_sell_breakout = true;
   if(rsi_div_active) {
      if(g_rsi_div_type == "HID_BULL") rsi_div_buy_breakout = true;
      if(g_rsi_div_type == "HID_BEAR") rsi_div_sell_breakout = true;
   }
```

**Bounce BUY entry** — add `rsi_div_buy_bounce` to the condition:

Find:
```mql5
         && h1_ok_buy && h4_ok_buy && fib_ok_buy && buy_reject && buy_bar0_ok && liquidity_ok) {
```

Replace with:
```mql5
         && h1_ok_buy && h4_ok_buy && fib_ok_buy && rsi_div_buy_bounce && buy_reject && buy_bar0_ok && liquidity_ok) {
```

**Bounce SELL entry** — add `rsi_div_sell_bounce`:

Find:
```mql5
              && h1_ok_sell && h4_ok_sell && fib_ok_sell && sell_reject && sell_bar0_ok && liquidity_ok) {
```

Replace with:
```mql5
              && h1_ok_sell && h4_ok_sell && fib_ok_sell && rsi_div_sell_bounce && sell_reject && sell_bar0_ok && liquidity_ok) {
```

> **Note:** Breakout entries do NOT require divergence — hidden divergence
> is informational for breakouts, not a gate. We log it but don't block.

### Step 3.10 — Draw arrow on trade entry

**Location:** In `CheckNativeScalperSetups()`, right after the trade entry
`Print(...)` block (before the `scalper_entry.json` write), add:

```mql5
   DrawDivergenceArrow(g_rsi_div_type, direction == "BUY" ? ask : bid, iTime(_Symbol, PERIOD_M5, 0));
```

### Step 3.11 — Journal entry log

**Location:** In the trade entry `Print(...)` block, add `RSI_DIV` after the
existing `FIB50` field:

Find:
```mql5
         " FIB50=", DoubleToString(g_fib_50, 2),
         " OB_zones=", IntegerToString(g_ob_zone_count),
```

Replace with:
```mql5
         " FIB50=", DoubleToString(g_fib_50, 2),
         " RSI_DIV=", g_rsi_div_type,
         " OB_zones=", IntegerToString(g_ob_zone_count),
```

### Step 3.12 — `market_data.json` output

**Location:** In `WriteMarketData()`, after the `volume_profile` closing `},`:

```mql5
   j += "\"rsi_divergence\":\"" + g_rsi_div_type + "\",";
```

### Step 3.13 — `scalper_entry.json` output

**Location:** In the scalper_entry.json block, after the `"fib_618"` line:

```mql5
   ej += "\"rsi_divergence\":\"" + g_rsi_div_type + "\",";
```

---

### Step 3.14 — `config/scalper_config.json`

**Location:** In the `"indicators"` section, after `"fib_lookback": 0`:

```json
    "rsi_div_enabled": 1,
    "rsi_div_lookback": 20,
    "rsi_div_swing_bars": 3,
    "rsi_div_min_rsi_diff": 1.0,
    "rsi_div_draw_arrows": 1
```

Remember trailing comma after `"fib_lookback": 0,`.

### Step 3.15 — `.env.example`

**Location:** After the Fibonacci section:

```
# RSI divergence detection (entry confirmation for bounces):
# FORGE_RSI_DIV_ENABLED=1
# FORGE_RSI_DIV_LOOKBACK=20
# FORGE_RSI_DIV_SWING_BARS=3
# FORGE_RSI_DIV_MIN_RSI_DIFF=1.0
# FORGE_RSI_DIV_DRAW_ARROWS=1
```

### Step 3.16 — `scripts/sync_scalper_config_from_env.py`

**Location:** In the `MAPPING` dict, after the Fibonacci entries:

```python
    "FORGE_RSI_DIV_ENABLED": ("indicators", "rsi_div_enabled", "bool01", None, None),
    "FORGE_RSI_DIV_LOOKBACK": ("indicators", "rsi_div_lookback", "int", 5.0, 200.0),
    "FORGE_RSI_DIV_SWING_BARS": ("indicators", "rsi_div_swing_bars", "int", 1.0, 10.0),
    "FORGE_RSI_DIV_MIN_RSI_DIFF": ("indicators", "rsi_div_min_rsi_diff", "float", 0.0, 20.0),
    "FORGE_RSI_DIV_DRAW_ARROWS": ("indicators", "rsi_div_draw_arrows", "bool01", None, None),
```

---

### Step 3.17 — `python/bridge.py`

**Location 1 — `_extract_forge_thresholds()`:** After the Fib fields, add:

```python
        "rsi_divergence": (mt5_data or {}).get("rsi_divergence"),
```

**Location 2 — `_check_forge_scalper_entry()` open_context extras:** After
`"fib_618"`, add:

```python
                    "rsi_divergence": entry.get("rsi_divergence"),
```

**Location 3 — BRIDGE activity log for `FORGE_SCALP_ENTRY`:** After
`"fib_50"`, add:

```python
                "rsi_divergence": entry.get("rsi_divergence"),
```

**Location 4 — Telegram notification (`self.herald.send()`):** Update the
existing `herald.send()` call to include divergence info. Find:

```python
            f"RSI: {entry.get('m5_rsi')} ADX: {entry.get('m5_adx')} "
            f"ATR: {entry.get('m5_atr')}\n"
```

Replace with:

```python
            f"RSI: {entry.get('m5_rsi')} ADX: {entry.get('m5_adx')} "
            f"ATR: {entry.get('m5_atr')}"
            + (f" DIV: {entry.get('rsi_divergence')}" if entry.get("rsi_divergence", "NONE") != "NONE" else "")
            + "\n"
```

### Step 3.18 — `python/lens.py`

**Location:** In the `mt5_data` pass-through dict, after `"fib_618"`:

```python
                    "rsi_divergence": mt5_data.get("rsi_divergence"),
```

### Step 3.19 — `python/scribe.py`

**Location 1 — DDL:** In the `market_snapshots` CREATE TABLE, after
`fib_618 REAL,`:

```sql
    rsi_divergence TEXT,
```

**Location 2 — Migration:** After the `fib_618` migration block:

```python
        if "rsi_divergence" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN rsi_divergence TEXT")
            log.info("SCRIBE migration: added rsi_divergence to market_snapshots")
```

**Location 3 — `log_market_snapshot` INSERT:** Add `rsi_divergence` to the
column list and VALUES placeholders, and add:

```python
                 data.get("rsi_divergence")))
```

after the last `data.get(...)` in the values tuple. Update the `?` count
accordingly.

---

## 4. Verification checklist

1. **Compile:** `make forge-compile` — must succeed.
2. **Config sync:** `python3 scripts/sync_scalper_config_from_env.py` — verify
   `rsi_div_*` fields appear.
3. **Config diff:** `diff config/scalper_config.json MT5/scalper_config.json`
4. **Reload services:** `make reload` — all components healthy.
5. **MT5 reload:** Remove FORGE → re-drag from Navigator.
6. **market_data.json:** Verify `"rsi_divergence"` field present (may be
   `"NONE"` initially — divergences are detected every new M5 bar).
7. **Journal log:** Check for `FORGE RSI_DIV:` and `FORGE V2 RSI_DIV:` lines.
8. **Chart arrows:** When a bounce entry fires with divergence, a green/red
   arrow should appear at the entry bar.
9. **SCRIBE DB:**
   ```sql
   SELECT rsi_divergence FROM market_snapshots
   WHERE rsi_divergence IS NOT NULL AND rsi_divergence != 'NONE'
   ORDER BY id DESC LIMIT 5;
   ```
10. **Telegram:** Next FORGE scalp entry should show `DIV: REG_BULL` (or
    similar) in the notification if divergence was present.

## 5. Runtime management

| What | How |
|------|-----|
| **Disable divergence gate** | `"rsi_div_enabled": 0` in config |
| **Disable chart arrows** | `"rsi_div_draw_arrows": 0` in config |
| **Adjust sensitivity** | `"rsi_div_swing_bars": 5` (stricter) or `1` (looser) |
| **Adjust lookback** | `"rsi_div_lookback": 30` for deeper divergence scan |
| **Tighter RSI gap** | `"rsi_div_min_rsi_diff": 2.0` (fewer, stronger signals) |
| **Override via .env** | `FORGE_RSI_DIV_ENABLED=0` → `make scalper-env-sync` |

## 6. How the divergence filter works in practice

**BB_BOUNCE BUY scenario:**
1. Price touches BB lower band ✓
2. RSI < 45 (oversold zone) ✓
3. H1 trend bullish ✓
4. VWAP above Fib50 (bullish bias) ✓
5. **RSI divergence = REG_BULL** (price made lower low, RSI made higher low) ✓
6. → Entry confirmed with high confidence, divergence logged to SCRIBE +
   arrow drawn on chart + Telegram alert shows "DIV: REG_BULL"

**Without divergence:** If `rsi_div_enabled=1` and divergence is `NONE` or
`REG_BEAR`, the bounce BUY is blocked. This prevents entries where RSI
*agrees* with the downward price movement (no reversal signal).

**BB_BREAKOUT:** Divergence is logged but never blocks. Hidden bullish/bearish
divergence is informational confirmation that the trend has momentum.

---

## 7. Bump VERSION

After implementation, bump the version:

```bash
echo "2.2.0" > VERSION
make forge-compile
```

Update `CHANGELOG.md` with a `[2.2.0]` section documenting RSI divergence.

---

*End of prompt.*
