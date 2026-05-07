# FORGE Native Scalper V2 — Full Implementation Prompt

> **Purpose:** Self-contained instructions for an AI coding agent to implement all 7
> improvements to the FORGE native scalper in `ea/FORGE.mq5`, `config/scalper_config.json`,
> `python/lens.py`, and `python/bridge.py`. No human input required beyond "run this prompt."

---

## Context

FORGE is an MQL5 Expert Advisor at `ea/FORGE.mq5` (~2927 lines). It runs a native scalper
(BB_BOUNCE + BB_BREAKOUT) on XAUUSD M5. Current issues:

- **Bounce entries fire on H1 flat** (no directional conviction) → losers in chop.
- **Single-bar confirmation** — one M5 rejection candle is not enough.
- **No candlestick pattern awareness** — only checks `close > open` (bullish) or `close < open`.
- **No volume context** — treats every BB-band touch equally; no awareness of liquidity zones.
- **Order Block zones from LENS/TradingView** are fetched but never reach FORGE.
- **SL/TP are purely ATR-geometric** — no structural placement.
- **Breakout entries are immediate** — no retest/pullback logic.

---

## Architecture

```
FORGE (MQL5, tick-level)                 LENS (TradingView MCP, ~60s poll)
├── Volume Profile + POC (new)           ├── Order Block zones (already fetched)
│   CopyTickVolume + bins → g_poc_price  │   ob_zones[].high / .low
├── Candle patterns (new)                └── Written to ob_zones.json in Common Files
│   iOpen/iClose bars 1–3                       ↓
├── Multi-candle confirmation (new)      FORGE reads ob_zones.json
├── Stricter H1 filter (new)             via ReadTextFileDual
├── Breakout retest state (new)
└── Uses POC + OB zones for SL/TP
```

---

## File Inventory (read these before editing)

| File | Role |
|------|------|
| `ea/FORGE.mq5` | Main EA — all MQL5 changes go here |
| `config/scalper_config.json` | Runtime config read by FORGE every 20 timer cycles |
| `python/lens.py` | LENS TradingView MCP client — add OB zone JSON write |
| `python/bridge.py` | BRIDGE orchestrator — add OB zone file sync to Common Files |
| `scripts/compile_forge_ea_macos.sh` | Build script — syncs scalper_config.json to Common Files |
| `scripts/sync_scalper_config_from_env.py` | Env→JSON sync — always copies config/ → MT5/ (Common Files) |

---

## Task 1: Stricter H1 Filter for Bounce

### Current behavior (lines ~2142–2145 in FORGE.mq5)
```mql5
bool h1_ok_buy  = in_tester || h1_bull || h1_flat;
bool h1_ok_sell = in_tester || h1_bear || h1_flat;
```
H1 flat allows BOTH buy and sell bounces. This produces entries without directional conviction.

### Required change
Add a configurable flag `bounce_require_h1_direction` (default `true` in live, ignored in tester):
```mql5
// In ScalperConfig struct, add:
bool bounce_require_h1_direction;

// In InitScalperConfig(), add:
g_sc.bounce_require_h1_direction = true;

// In ReadScalperConfig(), add JSON read:
if(JsonHasKey(content, "bounce_require_h1_direction")) {
   v = JsonGetDouble(content, "bounce_require_h1_direction");
   g_sc.bounce_require_h1_direction = (v >= 0.5);
}

// Replace the h1_ok_buy/sell lines in CheckNativeScalperSetups():
bool bounce_h1_strict = (!in_tester) && g_sc.bounce_require_h1_direction;
bool h1_ok_buy  = in_tester || h1_bull || (!bounce_h1_strict && h1_flat);
bool h1_ok_sell = in_tester || h1_bear || (!bounce_h1_strict && h1_flat);
```

### Config addition (`config/scalper_config.json` → `bb_bounce` section)
```json
"bounce_require_h1_direction": 1
```

### Env sync (`scripts/sync_scalper_config_from_env.py`)
```python
"FORGE_BOUNCE_REQUIRE_H1_DIRECTION": ("bb_bounce", "bounce_require_h1_direction", "bool01", None, None),
```

### Journal log
Add to the "FORGE scalper profile" PrintFormat:
```
h1_strict_bounce=%s
```

---

## Task 2: Multi-Candle Confirmation

### Current behavior (lines ~2200–2212)
Only checks **bar 1** (last closed M5) for rejection/reclaim. Current bar (bar 0) is not validated.

### Required change
Add a **bar-0 continuation check**: after bar 1 shows rejection, bar 0's current mid-price must
also be moving AWAY from the band (not pressing back into it). This is the Article 2 "reversal
confirmed" concept.

```mql5
// After buy_reject / sell_reject are computed, add:
// Bar 0 continuation: current price moving away from the band
bool buy_bar0_ok = (mid > m5_bb_l + proximity * 0.5);  // price has cleared the zone
bool sell_bar0_ok = (mid < m5_bb_u - proximity * 0.5);

// Modify entry conditions:
// BUY: add && buy_bar0_ok
if(mid <= m5_bb_l + proximity && m5_rsi < g_sc.bounce_rsi_buy_max
   && h1_ok_buy && h4_ok_buy && buy_reject && buy_bar0_ok) {

// SELL: add && sell_bar0_ok
else if(mid >= m5_bb_u - proximity && m5_rsi > g_sc.bounce_rsi_sell_min
        && h1_ok_sell && h4_ok_sell && sell_reject && sell_bar0_ok) {
```

Also add a configurable `bounce_require_bar0_confirm` (default true) so it can be disabled:
```mql5
// ScalperConfig:
bool bounce_require_bar0_confirm;

// InitScalperConfig:
g_sc.bounce_require_bar0_confirm = true;

// ReadScalperConfig:
if(JsonHasKey(content, "bounce_require_bar0_confirm")) {
   v = JsonGetDouble(content, "bounce_require_bar0_confirm");
   g_sc.bounce_require_bar0_confirm = (v >= 0.5);
}

// Use:
bool buy_bar0_ok = (!g_sc.bounce_require_bar0_confirm) || (mid > m5_bb_l + proximity * 0.5);
bool sell_bar0_ok = (!g_sc.bounce_require_bar0_confirm) || (mid < m5_bb_u - proximity * 0.5);
```

### Config
```json
"bounce_require_bar0_confirm": 1
```

---

## Task 3: Candlestick Pattern Scoring

### Current behavior
Only `m5_c1 > m5_o1` (bullish candle) or `m5_c1 < m5_o1` (bearish) for bounce_require_rejection_candle.

### Required change
Add a function `int ScalperCandlePatternScore(bool is_buy)` that checks bars 1–3 for:

1. **Hammer (buy) / Shooting Star (sell)** — long lower/upper shadow ≥ 2× body, opposite shadow ≤ 30% of body
2. **Bullish/Bearish Engulfing** — bar 1 body engulfs bar 2 body in opposite direction
3. **Pin Bar** — wick ≥ 2× body on the rejection side

Return a score: 0 = no pattern, 1 = basic rejection (current logic), 2 = hammer/pin, 3 = engulfing.

```mql5
int ScalperCandlePatternScore(bool is_buy) {
   double o1 = iOpen(_Symbol, PERIOD_M5, 1);
   double c1 = iClose(_Symbol, PERIOD_M5, 1);
   double h1 = iHigh(_Symbol, PERIOD_M5, 1);
   double l1 = iLow(_Symbol, PERIOD_M5, 1);
   double o2 = iOpen(_Symbol, PERIOD_M5, 2);
   double c2 = iClose(_Symbol, PERIOD_M5, 2);

   double body1 = MathAbs(c1 - o1);
   double range1 = h1 - l1;
   if(range1 <= 0) return 0;

   if(is_buy) {
      double lower_shadow = MathMin(o1, c1) - l1;
      double upper_shadow = h1 - MathMax(o1, c1);
      // Hammer
      if(c1 > o1 && lower_shadow >= 2.0 * body1 && upper_shadow <= body1 * 0.3)
         return 2;
      // Bullish Engulfing
      if(c1 > o1 && c2 < o2 && o1 <= c2 && c1 >= o2)
         return 3;
      // Basic bullish candle
      if(c1 > o1) return 1;
   } else {
      double upper_shadow = h1 - MathMax(o1, c1);
      double lower_shadow = MathMin(o1, c1) - l1;
      // Shooting Star
      if(c1 < o1 && upper_shadow >= 2.0 * body1 && lower_shadow <= body1 * 0.3)
         return 2;
      // Bearish Engulfing
      if(c1 < o1 && c2 > o2 && o1 >= c2 && c1 <= o2)
         return 3;
      // Basic bearish candle
      if(c1 < o1) return 1;
   }
   return 0;
}
```

### Integration
Add a configurable minimum score `bounce_min_candle_score` (default 1, set to 2 for stricter):
```mql5
// ScalperConfig:
int bounce_min_candle_score;

// Replace current buy_candle_ok / sell_candle_ok:
int buy_pattern = ScalperCandlePatternScore(true);
int sell_pattern = ScalperCandlePatternScore(false);
bool buy_candle_ok = (!g_sc.bounce_require_rejection_candle) || (buy_pattern >= g_sc.bounce_min_candle_score);
bool sell_candle_ok = (!g_sc.bounce_require_rejection_candle) || (sell_pattern >= g_sc.bounce_min_candle_score);
```

### Config
```json
"bounce_min_candle_score": 1
```
(Operator can set to 2 for hammer/engulfing-only, or 3 for engulfing-only.)

### Journal log
Include pattern score in the entry log line:
```
pattern_score=%d
```

---

## Task 4: Volume Profile + POC Computation in FORGE

### Overview
Compute a lightweight M5 volume profile over the last 100 bars using `CopyTickVolume`,
`CopyHigh`, `CopyLow`, `CopyClose`. Identify the Point of Control (POC) — the price level
with the highest tick volume. Recompute every 20 timer cycles (same cadence as config reload).

### New globals
```mql5
double g_poc_price = 0.0;          // Point of Control price level
double g_poc_strength = 0.0;       // 0..1 normalized (max bin volume / total volume)
int    g_vp_lookback = 100;        // configurable via JSON
datetime g_vp_last_calc = 0;       // throttle: recompute max every 60s
```

### New function
```mql5
void ComputeVolumeProfile() {
   if(TimeCurrent() - g_vp_last_calc < 60) return;
   g_vp_last_calc = TimeCurrent();

   int lookback = g_vp_lookback;
   double hi[], lo[], cl[];
   long vol[];
   ArraySetAsSeries(hi, true);
   ArraySetAsSeries(lo, true);
   ArraySetAsSeries(cl, true);
   ArraySetAsSeries(vol, true);
   if(CopyHigh(_Symbol, PERIOD_M5, 0, lookback, hi) < lookback) return;
   if(CopyLow(_Symbol, PERIOD_M5, 0, lookback, lo) < lookback) return;
   if(CopyClose(_Symbol, PERIOD_M5, 0, lookback, cl) < lookback) return;
   if(CopyTickVolume(_Symbol, PERIOD_M5, 0, lookback, vol) < lookback) {
      if(CopyRealVolume(_Symbol, PERIOD_M5, 0, lookback, vol) < lookback) return;
   }

   double price_max = hi[ArrayMaximum(hi, 0, lookback)];
   double price_min = lo[ArrayMinimum(lo, 0, lookback)];
   if(price_max <= price_min) return;

   int n_bins = 50;
   double step = (price_max - price_min) / n_bins;
   double bins[];
   ArrayResize(bins, n_bins);
   ArrayInitialize(bins, 0.0);

   double total_vol = 0.0;
   for(int i = 0; i < lookback; i++) {
      int bin_idx = (int)MathFloor((cl[i] - price_min) / step);
      if(bin_idx < 0) bin_idx = 0;
      if(bin_idx >= n_bins) bin_idx = n_bins - 1;
      bins[bin_idx] += (double)vol[i];
      total_vol += (double)vol[i];
   }

   int max_bin = 0;
   for(int i = 1; i < n_bins; i++)
      if(bins[i] > bins[max_bin]) max_bin = i;

   g_poc_price = price_min + (max_bin + 0.5) * step;
   g_poc_strength = (total_vol > 0) ? (bins[max_bin] / total_vol) : 0.0;

   PrintFormat("FORGE VP: POC=%.2f strength=%.3f range=[%.2f,%.2f] bins=%d lookback=%d",
               g_poc_price, g_poc_strength, price_min, price_max, n_bins, lookback);
}
```

### Call site
In `OnTimer()`, after `ReadScalperConfig()` reload block (~line 507):
```mql5
if(g_cycle % 20 == 0) ComputeVolumeProfile();
```

### Config
Add to `config/scalper_config.json` in `indicators` section:
```json
"vp_lookback": 100,
"vp_bins": 50
```
Read in `ReadScalperConfig`:
```mql5
if(JsonHasKey(content, "vp_lookback")) {
   v = JsonGetDouble(content, "vp_lookback");
   if(v >= 20 && v <= 500) g_vp_lookback = (int)v;
}
```

---

## Task 5: LENS OB Zones → JSON → FORGE Bridge

### Python side: `python/lens.py`
After writing `lens_snapshot.json` in `_write_snapshot()` (~line 567), also write
`ob_zones.json` to the **MT5 Common Files directory** (same as where FORGE reads).

Add near the top of `lens.py`:
```python
OB_ZONES_FILE = os.path.join(os.path.dirname(__file__), "..", "MT5", "ob_zones.json")
```

Add a method to `Lens` class:
```python
def _write_ob_zones(self, snap: LensSnapshot):
    zones = snap.order_block_values.get("zones", []) if isinstance(snap.order_block_values, dict) else []
    payload = {
        "zones": zones[:6],
        "timestamp": snap.timestamp,
    }
    try:
        import json as _json
        with open(OB_ZONES_FILE, "w") as f:
            _json.dump(payload, f, indent=2)
    except Exception as e:
        log.warning(f"LENS OB zones write error: {e}")
```

Call it from `_write_snapshot()`:
```python
def _write_snapshot(self, snap: LensSnapshot, mode: str):
    # ... existing code ...
    self._write_ob_zones(snap)
```

### FORGE side: `ea/FORGE.mq5`
Add globals:
```mql5
double g_ob_zones_hi[6];
double g_ob_zones_lo[6];
int    g_ob_zone_count = 0;
string g_ob_zones_snapshot = "";
```

Add reader function:
```mql5
void ReadOBZones() {
   string content = "";
   if(!ReadTextFileDual("ob_zones.json", content)) return;
   if(content == "" || content == g_ob_zones_snapshot) return;
   g_ob_zones_snapshot = content;
   g_ob_zone_count = 0;

   // Parse zones array: [{"high":1234.56,"low":1230.00}, ...]
   int pos = StringFind(content, "\"zones\"");
   if(pos < 0) return;
   int arr_start = StringFind(content, "[", pos);
   if(arr_start < 0) return;

   int p = arr_start + 1;
   while(g_ob_zone_count < 6 && p < StringLen(content)) {
      int obj_start = StringFind(content, "{", p);
      if(obj_start < 0) break;
      int obj_end = StringFind(content, "}", obj_start);
      if(obj_end < 0) break;
      string obj = StringSubstr(content, obj_start, obj_end - obj_start + 1);
      double hi_val = JsonGetDouble(obj, "high");
      double lo_val = JsonGetDouble(obj, "low");
      if(hi_val > 0 && lo_val > 0) {
         g_ob_zones_hi[g_ob_zone_count] = hi_val;
         g_ob_zones_lo[g_ob_zone_count] = lo_val;
         g_ob_zone_count++;
      }
      p = obj_end + 1;
   }
   PrintFormat("FORGE OB zones loaded: count=%d", g_ob_zone_count);
}
```

Call in `OnTimer()` alongside scalper config reload:
```mql5
if(g_cycle % 20 == 0) ReadOBZones();
```

---

## Task 6: Structural SL/TP Using POC + OB Zones

### Bounce SL placement
Instead of `SL = entry ± ATR * sl_mult`, find the nearest **OB zone** or **swing extreme**
beyond the band, and place SL beyond it:

```mql5
double FindStructuralSL(bool is_buy, double entry, double atr_sl, double point) {
   double best_sl = atr_sl;  // fallback to ATR-based

   // Check OB zones for structural level beyond entry
   for(int i = 0; i < g_ob_zone_count; i++) {
      if(is_buy) {
         // Buy SL below: find OB zone low below entry
         if(g_ob_zones_lo[i] < entry && g_ob_zones_lo[i] > 0) {
            double candidate = g_ob_zones_lo[i] - 5.0 * point;
            if(candidate < entry && (best_sl == atr_sl || candidate > best_sl))
               best_sl = candidate;  // tighter but structural
         }
      } else {
         // Sell SL above: find OB zone high above entry
         if(g_ob_zones_hi[i] > entry && g_ob_zones_hi[i] > 0) {
            double candidate = g_ob_zones_hi[i] + 5.0 * point;
            if(candidate > entry && (best_sl == atr_sl || candidate < best_sl))
               best_sl = candidate;
         }
      }
   }
   return NormalizeDouble(best_sl, _Digits);
}
```

### Bounce TP placement using POC
If POC is between entry and BB mid, use POC as TP1 instead of BB mid:

```mql5
// After computing tp1 = BB mid in bounce BUY:
if(g_poc_price > ask && g_poc_price < tp1)
   tp1 = NormalizeDouble(g_poc_price, _Digits);

// After computing tp1 = BB mid in bounce SELL:
if(g_poc_price < bid && g_poc_price > tp1)
   tp1 = NormalizeDouble(g_poc_price, _Digits);
```

### Bounce entry filter: volume zone awareness
Only enter bounce if the BB band touch is near a high-volume zone (within 1 ATR of POC) OR
within an OB zone:

```mql5
bool NearLiquidityZone(double price, double atr) {
   // Near POC?
   if(g_poc_price > 0 && MathAbs(price - g_poc_price) <= atr * 1.5)
      return true;
   // Inside an OB zone?
   for(int i = 0; i < g_ob_zone_count; i++) {
      if(price >= g_ob_zones_lo[i] && price <= g_ob_zones_hi[i])
         return true;
   }
   return false;
}
```

Add to bounce entry conditions (configurable via `bounce_require_liquidity_zone`, default true):
```mql5
bool liquidity_ok = (!g_sc.bounce_require_liquidity_zone) || NearLiquidityZone(mid, m5_atr);
// Add && liquidity_ok to both BUY and SELL bounce conditions
```

### Config
```json
"bounce_require_liquidity_zone": 1
```

---

## Task 7: Breakout Retest State Machine

### Concept
After a BB breakout signal, instead of entering immediately, track the breakout level and wait
for price to **pull back and retest** the broken band. Enter on the retest with confirmed direction.

### State tracking
Add to `TradeGroup` or a new struct:
```mql5
struct BreakoutRetest {
   bool   active;
   string direction;       // BUY or SELL
   double breakout_level;  // BB band that was broken
   double sl;
   double tp1, tp2;
   string setup_type;
   datetime trigger_time;
   int    max_wait_bars;   // expire after N M5 bars
   int    bars_waited;
};
BreakoutRetest g_retest;
```

### Initialize
```mql5
g_retest.active = false;
```

### Logic flow
1. When breakout conditions are met (existing code), instead of opening immediately:
   ```mql5
   if(g_sc.breakout_use_retest) {
      g_retest.active = true;
      g_retest.direction = direction;
      g_retest.breakout_level = (direction == "BUY") ? m5_bb_u : m5_bb_l;
      g_retest.sl = sl;
      g_retest.tp1 = tp1;
      g_retest.tp2 = tp2;
      g_retest.setup_type = "BB_BREAKOUT_RETEST";
      g_retest.trigger_time = TimeCurrent();
      g_retest.max_wait_bars = 6;  // configurable
      g_retest.bars_waited = 0;
      PrintFormat("FORGE SCALPER: breakout %s — waiting for retest at %.2f", direction, g_retest.breakout_level);
      return;  // don't open yet
   }
   ```

2. On subsequent ticks, check for retest:
   ```mql5
   // At the top of CheckNativeScalperSetups, before other logic:
   if(g_retest.active) {
      g_retest.bars_waited++;
      double price = (g_retest.direction == "BUY") ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double level = g_retest.breakout_level;
      double atr = m5_atr;
      bool price_retested = false;
      if(g_retest.direction == "BUY")
         price_retested = (price <= level + atr * 0.3) && (price >= level - atr * 0.5);
      else
         price_retested = (price >= level - atr * 0.3) && (price <= level + atr * 0.5);

      if(price_retested) {
         // Retest confirmed — proceed to open with better R:R
         direction = g_retest.direction;
         sl = g_retest.sl;
         tp1 = g_retest.tp1;
         tp2 = g_retest.tp2;
         setup_type = g_retest.setup_type;
         g_retest.active = false;
         // Fall through to execution block
      } else if(g_retest.bars_waited > g_retest.max_wait_bars) {
         PrintFormat("FORGE SCALPER: retest expired after %d bars", g_retest.bars_waited);
         g_retest.active = false;
         return;
      } else {
         return;  // still waiting
      }
   }
   ```

### Config
```json
"breakout_use_retest": 1,
"breakout_retest_max_bars": 6
```

### ScalperConfig additions
```mql5
bool breakout_use_retest;
int  breakout_retest_max_bars;
```

---

## Post-Implementation Checklist

1. **Compile**: `make forge-compile` must succeed (syncs config JSON + builds .ex5)
2. **Config JSON**: All new keys added to `config/scalper_config.json` with documented defaults
3. **Env sync**: New `FORGE_*` keys added to `scripts/sync_scalper_config_from_env.py`
4. **Journal logs**: Every new feature prints diagnostic info in FORGE Journal on reload
5. **Tester compatibility**: All new gates use `in_tester` bypass where appropriate (volume profile
   and OB zones can be skipped in tester since Common Files may not have fresh data)
6. **No regressions**: Existing scalper_config.json keys and behavior unchanged
7. **`.env.example`**: Document new `FORGE_*` overrides

## Defaults Summary

| Key | Section | Default | Purpose |
|-----|---------|---------|---------|
| `bounce_require_h1_direction` | `bb_bounce` | `1` | H1 bull for buy, H1 bear for sell |
| `bounce_require_bar0_confirm` | `bb_bounce` | `1` | Current bar moving away from band |
| `bounce_min_candle_score` | `bb_bounce` | `1` | 1=basic, 2=hammer/pin, 3=engulfing |
| `bounce_require_liquidity_zone` | `bb_bounce` | `1` | Near POC or inside OB zone |
| `vp_lookback` | `indicators` | `100` | Volume profile bar count |
| `vp_bins` | `indicators` | `50` | Volume profile bin count |
| `breakout_use_retest` | `bb_breakout` | `1` | Wait for pullback after breakout |
| `breakout_retest_max_bars` | `bb_breakout` | `6` | Max M5 bars to wait for retest |
