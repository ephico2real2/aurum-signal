# FORGE SL Placement Fix + Trade Frequency Tuning

## Problem Statement

Backtesting reveals that FORGE correctly identifies entry points (BB_BOUNCE BUY at
the right time and price) but sets the stop-loss dangerously tight. Trades get stopped
out 4 minutes after entry, and price subsequently reaches TP1/TP2.

**Observed example (2026.04.06 01:50 XAUUSD):**
- Entry (ask): ~4642.85
- SL set: 4638.62 (**only 4.23 points** below entry)
- ATR(14): 10.59
- Expected SL (1.5× ATR): ~4627 (**15.9 points** below — 3.8× wider)
- TP1: 4652.72, TP2: 4656.24 — price reached these after the SL hit
- Result: all legs stopped out in 4 minutes, full move missed

## Root Causes (3 compounding issues)

### 1. `FindStructuralSL()` pulls SL CLOSER instead of FURTHER (primary)

**File:** `ea/FORGE.mq5`, function `FindStructuralSL()` (~line 2656)

For BUY trades, the function iterates OB zones and picks `candidate > best_sl` —
i.e., it selects the **highest** (nearest to entry) structural level. An OB zone
with `low ≈ 4638.67` produces `candidate = 4638.62`, overriding the ATR SL of ~4627.

The design intent was "place SL beyond structural support" but the implementation
picks the **tightest** structural level, not the one that provides the most protection.

**Current logic (flawed):**
```mql5
// BUY: picks highest zone below entry → tightest SL
if(candidate < entry && (best_sl == atr_sl || candidate > best_sl))
   best_sl = candidate;
```

**Fix:** The structural SL should only **widen** the stop (further from entry), never
tighten it. If no OB zone provides a wider stop than ATR, use the ATR SL as-is.
Additionally, enforce a minimum floor so the SL can never be closer than `min_sl_atr_mult × ATR`.

### 2. `bounce_sl_atr_mult` never parsed from `scalper_config.json`

**File:** `ea/FORGE.mq5`, function `ReadScalperConfig()` (~line 1822+)

The JSON config has `"sl_atr_mult": 1.5` under `bb_bounce`, but there is **no parsing
code** that reads this key into `g_sc.bounce_sl_atr_mult`. It's stuck at the hardcoded
default of **1.2** (line 1661). Same issue likely affects `breakout_sl_atr_mult`.

**Fix:** Add JSON parsing for `sl_atr_mult` from both `bb_bounce` and `bb_breakout`
sections.

### 3. No minimum SL distance floor

**File:** `ea/FORGE.mq5`, function `CheckNativeScalperSetups()` (~line 3267+)

TP has minimum distance guards:
```mql5
double min_tp1 = ask + (m5_atr * 0.40);  // min 0.4× ATR
double min_tp2 = ask + (m5_atr * 0.80);  // min 0.8× ATR
```

But SL has **no equivalent floor**. A trade can open with SL just 4 points from entry
when ATR is 10+.

**Fix:** Add configurable `min_sl_atr_mult` (default 0.8) that enforces a minimum
SL distance of `min_sl_atr_mult × ATR` from entry, regardless of what
`FindStructuralSL()` returns.

---

## Implementation Steps

### Step 1: Fix `FindStructuralSL()` — structural SL should only WIDEN

Change the OB zone selection logic so structural levels can only push the SL
**further** from entry (wider protection), never closer.

For BUY: structural SL must be ≤ ATR SL (lower = further from entry).
For SELL: structural SL must be ≥ ATR SL (higher = further from entry).

If an OB zone provides wider protection, use it; otherwise, keep the ATR SL.

**Updated function:**
```mql5
double FindStructuralSL(bool is_buy, double entry, double atr_sl, double point) {
   double best_sl = atr_sl;
   for(int i = 0; i < g_ob_zone_count; i++) {
      if(is_buy) {
         if(g_ob_zones_lo[i] < entry && g_ob_zones_lo[i] > 0) {
            double candidate = g_ob_zones_lo[i] - 5.0 * point;
            // Only use if it WIDENS the stop (further from entry)
            if(candidate < best_sl && candidate > 0)
               best_sl = candidate;
         }
      } else {
         if(g_ob_zones_hi[i] > entry && g_ob_zones_hi[i] > 0) {
            double candidate = g_ob_zones_hi[i] + 5.0 * point;
            // Only use if it WIDENS the stop (further from entry)
            if(candidate > best_sl)
               best_sl = candidate;
         }
      }
   }
   return NormalizeDouble(best_sl, _Digits);
}
```

### Step 2: Parse `sl_atr_mult` from JSON config

In `ReadScalperConfig()`, add parsing for both bounce and breakout SL multipliers.
Read from the `bb_bounce` and `bb_breakout` JSON sections respectively.

**Add to `ReadScalperConfig()` after the existing bounce/breakout parsing block:**
```mql5
// Parse SL ATR multipliers from config
string bounce_json = JsonExtractBracedObject(content, "bb_bounce");
if(bounce_json != "") {
   if(JsonHasKey(bounce_json, "sl_atr_mult")) {
      v = JsonGetDouble(bounce_json, "sl_atr_mult");
      if(v >= 0.5 && v <= 5.0) g_sc.bounce_sl_atr_mult = v;
   }
}
string breakout_json = JsonExtractBracedObject(content, "bb_breakout");
if(breakout_json != "") {
   if(JsonHasKey(breakout_json, "sl_atr_mult")) {
      v = JsonGetDouble(breakout_json, "sl_atr_mult");
      if(v >= 0.5 && v <= 5.0) g_sc.breakout_sl_atr_mult = v;
   }
}
```

### Step 3: Add minimum SL distance floor

Add a new config parameter `min_sl_atr_mult` (default 0.8) to enforce a minimum
SL distance as a fraction of ATR.

**ScalperConfig struct addition:**
```mql5
double min_sl_atr_mult;  // minimum SL distance = min_sl_atr_mult × ATR
```

**Default in `InitScalperConfig()`:**
```mql5
g_sc.min_sl_atr_mult = 0.8;
```

**JSON parsing in `ReadScalperConfig()`:**
```mql5
if(JsonHasKey(content, "min_sl_atr_mult")) {
   v = JsonGetDouble(content, "min_sl_atr_mult");
   if(v >= 0.3 && v <= 3.0) g_sc.min_sl_atr_mult = v;
}
```

**Enforcement after `FindStructuralSL()` in `CheckNativeScalperSetups()` —
for BB_BOUNCE BUY (and mirror for SELL):**
```mql5
direction = "BUY";
double atr_sl_buy = NormalizeDouble(bid - m5_atr * g_sc.bounce_sl_atr_mult, _Digits);
sl = FindStructuralSL(true, bid, atr_sl_buy, point);
// Enforce minimum SL distance floor
double min_sl_dist = m5_atr * g_sc.min_sl_atr_mult;
double sl_floor_buy = NormalizeDouble(bid - min_sl_dist, _Digits);
if(sl > sl_floor_buy) sl = sl_floor_buy;
```

**For BB_BOUNCE SELL:**
```mql5
direction = "SELL";
double atr_sl_sell = NormalizeDouble(ask + m5_atr * g_sc.bounce_sl_atr_mult, _Digits);
sl = FindStructuralSL(false, ask, atr_sl_sell, point);
// Enforce minimum SL distance floor
double min_sl_dist = m5_atr * g_sc.min_sl_atr_mult;
double sl_ceil_sell = NormalizeDouble(ask + min_sl_dist, _Digits);
if(sl < sl_ceil_sell) sl = sl_ceil_sell;
```

**Apply the same floor logic to BB_BREAKOUT BUY/SELL entries.**

### Step 4: Add to `scalper_config.json`

Add `min_sl_atr_mult` to the `safety` section:
```json
"safety": {
    ...
    "min_sl_atr_mult": 0.8
}
```

### Step 5: Add `.env` support

**`.env.example`:**
```ini
# Minimum SL distance as a fraction of ATR (floor — structural/fast-lock cannot tighten below this):
# FORGE_MIN_SL_ATR_MULT=0.8
# SL ATR multiplier overrides (default: bounce=1.5, breakout=1.5):
# FORGE_BOUNCE_SL_ATR_MULT=1.5
# FORGE_BREAKOUT_SL_ATR_MULT=1.5
```

**`scripts/sync_scalper_config_from_env.py` MAPPING additions:**
```python
"FORGE_MIN_SL_ATR_MULT": ("safety", "min_sl_atr_mult", "float", 0.3, 3.0),
"FORGE_BOUNCE_SL_ATR_MULT": ("bb_bounce", "sl_atr_mult", "float", 0.5, 5.0),
"FORGE_BREAKOUT_SL_ATR_MULT": ("bb_breakout", "sl_atr_mult", "float", 0.5, 5.0),
```

### Step 6: Add diagnostic logging

Add a PrintFormat in the trade entry section so we can verify SL calculation in logs:
```mql5
PrintFormat("FORGE SL CALC: setup=%s dir=%s entry=%.2f atr_sl=%.2f structural_sl=%.2f "
            "min_floor=%.2f final_sl=%.2f atr=%.2f sl_mult=%.2f min_sl_mult=%.2f",
            setup_type, direction,
            direction=="BUY" ? bid : ask,
            direction=="BUY" ? atr_sl_buy : atr_sl_sell,
            sl_before_floor, sl_floor, sl,
            m5_atr,
            is_breakout_setup ? g_sc.breakout_sl_atr_mult : g_sc.bounce_sl_atr_mult,
            g_sc.min_sl_atr_mult);
```

### Step 7: Trade frequency tuning — remove artificial caps

A scalper should take every valid setup it sees. The `max_trades_per_session` cap
is an artificial limit that prevents the bot from executing valid signals. Other
gates (max_open_groups, cooldown, spread, direction cooldown) already prevent
reckless overlap, so the session cap is redundant.

**`config/scalper_config.json` changes:**
```json
"safety": {
    "max_open_groups": 3,            // was 2 — allow more concurrent groups
    "max_trades_per_session": 100,   // was 3 — effectively uncapped (trade every valid setup)
    "loss_cooldown_sec": 120,        // was 300 — 2 min recovery (scalper pace)
    "direction_cooldown_bars": 3,    // was 6  — 15 min (was 30 min) before opposite direction
}
```

**`bb_bounce` entry filter relaxation (more setups seen):**
```json
"bb_bounce": {
    "adx_max": 35,                   // was 30 — allow bounces in slightly trendier markets
    "rsi_buy_max": 48,               // was 45 — slightly wider buy RSI window
    "rsi_sell_min": 52,              // was 55 — slightly wider sell RSI window
    "bb_proximity_pct": 25,          // was 20 — wider entry zone near BB bands
    "bounce_min_candle_score": 0,    // was 1  — other filters are strong enough
}
```

These changes are **config-only** (no EA code changes needed) and are all
hot-reloadable via `.env` overrides.

### Step 8: Update `CHANGELOG.md` and version

Bump patch version and document the SL quality fix + trade frequency tuning.

---

## Expected Outcome

### SL quality:
Using the observed backtest example:
- **Before fix:** SL = 4638.62 (4.23 pts from entry, OB zone override)
- **After fix:** SL = max(ATR SL, structural SL wider than ATR, floor)
  - ATR SL: 4642.85 − (10.59 × 1.5) = **4627.0** (15.9 pts — proper room)
  - Floor: 4642.85 − (10.59 × 0.8) = **4634.4** (minimum 8.5 pts)
  - Structural: only used if it's BELOW 4627.0 (further protection)
  - Final SL: **~4627** — trade survives the dip and hits TP1/TP2

### Trade frequency:
- Session cap removed → bot trades every valid setup
- 3 concurrent groups (was 2) → more throughput
- Faster cooldown (2 min vs 5 min) → quicker recovery
- Wider entry filters → more setups qualify
- Direction cooldown halved (15 min vs 30 min) → more reversals allowed

## Files Modified
- `ea/FORGE.mq5` — `FindStructuralSL()`, `ReadScalperConfig()`, `CheckNativeScalperSetups()`, `ScalperConfig` struct
- `config/scalper_config.json` — add `min_sl_atr_mult`, tune safety + bounce params
- `.env.example` — add `FORGE_MIN_SL_ATR_MULT`, `FORGE_BOUNCE_SL_ATR_MULT`, `FORGE_BREAKOUT_SL_ATR_MULT`
- `scripts/sync_scalper_config_from_env.py` — add MAPPING entries
- `CHANGELOG.md` — document fix
- `VERSION` — bump patch
