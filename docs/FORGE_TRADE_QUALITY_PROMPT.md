# FORGE Trade Quality & Survival Improvements — Implementation Prompt

> **Self-contained prompt.** Follow every step exactly. No user input needed.
> **Goal:** Improve trade quality and survival without reducing trade frequency.
> **Context:** Backtesting revealed fast SL hits (4-minute whipsaws) caused by
> tight SL, aggressive ratchet, and missing tester-mode guards.

---

## 1. Objective

Five targeted changes to reduce premature SL hits while keeping the scalper
high-frequency:

| # | Change | Why |
|---|--------|-----|
| 1 | **Configurable session filter in tester** | Avoid choppy low-liquidity hours; user picks which sessions to trade via comma-separated list |
| 2 | **Enable cooldown in tester** | Prevent immediate opposite-direction whipsaw after a loss |
| 3 | **Widen bounce SL default** | 1.2× ATR is too tight for XAU M5; 1.5× gives breathing room |
| 4 | **Increase fast-lock min hold** | 45s → 90s for bounce; let the setup develop before ratcheting |
| 5 | **Directional cooldown** | Prevent BUY→SELL flip within N bars (the 01:50 BUY → 01:54 SELL pattern) |

All parameters are hot-reloadable via `scalper_config.json`.

---

## 2. Files to modify

| File | What changes |
|------|-------------|
| `ea/FORGE.mq5` | Session filter in tester, cooldown in tester, directional cooldown logic |
| `config/scalper_config.json` | New keys + updated defaults |
| `.env.example` | Document new env vars |
| `scripts/sync_scalper_config_from_env.py` | New MAPPING entries |

---

## 3. Step-by-step implementation

### Step 3.1 — Configurable tester session filter

**Problem:** `ScalperSessionOK()` is bypassed entirely in tester mode.
The user wants to trade all sessions but needs the **option** to filter in
tester too, using a configurable comma-separated session list.

**ScalperConfig struct** — add after `int ny_end`:

```mql5
   // Tester session control
   bool   tester_session_filter;       // apply session filter in tester too
   string tester_allowed_sessions;     // comma-separated: "LONDON,NY,ASIAN" or "ALL"
```

**InitScalperConfig defaults:**

```mql5
   g_sc.tester_session_filter = false;
   g_sc.tester_allowed_sessions = "ALL";
```

**ReadScalperConfig JSON parsing** — add after existing session filter block:

```mql5
   if(JsonHasKey(content, "tester_session_filter")) {
      v = JsonGetDouble(content, "tester_session_filter");
      g_sc.tester_session_filter = (v >= 0.5);
   }
   if(JsonHasKey(content, "tester_allowed_sessions")) {
      string ts_val = JsonGetString(content, "tester_allowed_sessions");
      if(StringLen(ts_val) > 0) g_sc.tester_allowed_sessions = ts_val;
   }
```

**New helper function** — add after `ScalperSessionOK()`:

```mql5
bool ScalperTesterSessionOK() {
   if(!g_sc.tester_session_filter) return true;
   string allowed = g_sc.tester_allowed_sessions;
   if(allowed == "ALL" || allowed == "") return true;

   MqlDateTime dt;
   TimeGMT(dt);
   int h = dt.hour;

   string current_session = "OFF_HOURS";
   if(h >= g_sc.london_start && h < g_sc.london_end)
      current_session = "LONDON";
   else if(h >= g_sc.ny_start && h < g_sc.ny_end)
      current_session = "NY";
   else
      current_session = "ASIAN";

   // Check if current session is in the allowed list
   string parts[];
   int count = StringSplit(allowed, ',', parts);
   for(int i = 0; i < count; i++) {
      StringTrimLeft(parts[i]);
      StringTrimRight(parts[i]);
      StringToUpper(parts[i]);
      if(parts[i] == current_session) return true;
   }
   return false;
}
```

**Modify the session gate in `CheckNativeScalperSetups()`:**

Find:
```mql5
   if(MQLInfoInteger(MQL_TESTER) == 0 && !ScalperSessionOK()) {
```

Replace with:
```mql5
   bool session_blocked = false;
   if(MQLInfoInteger(MQL_TESTER) == 0 && !ScalperSessionOK())
      session_blocked = true;
   else if(MQLInfoInteger(MQL_TESTER) != 0 && !ScalperTesterSessionOK())
      session_blocked = true;
   if(session_blocked) {
```

Keep the existing log block and `return;` inside the `if(session_blocked)` body.

**scalper_config.json** — add to `session_filter` section:

```json
    "tester_session_filter": 0,
    "tester_allowed_sessions": "ALL"
```

**`.env.example`:**

```
# Tester session filter (comma-separated: LONDON,NY,ASIAN or ALL):
# FORGE_TESTER_SESSION_FILTER=0
# FORGE_TESTER_ALLOWED_SESSIONS=ALL
```

**sync script MAPPING:**

```python
    "FORGE_TESTER_SESSION_FILTER": ("session_filter", "tester_session_filter", "bool01", None, None),
    "FORGE_TESTER_ALLOWED_SESSIONS": ("session_filter", "tester_allowed_sessions", "string", None, None),
```

Note: The sync script's `_parse_value()` function needs a `"string"` type
handler. Add to `_parse_value()`:

```python
    if kind == "string":
        return raw.strip()
```

---

### Step 3.2 — Enable cooldown in tester

**Problem:** `ScalperCooldownOK()` is bypassed in tester.

**ScalperConfig struct** — add after `int loss_cooldown_sec`:

```mql5
   bool   tester_cooldown_enabled;     // apply loss cooldown in tester
```

**InitScalperConfig:**

```mql5
   g_sc.tester_cooldown_enabled = true;
```

**ReadScalperConfig:**

```mql5
   if(JsonHasKey(content, "tester_cooldown_enabled")) {
      v = JsonGetDouble(content, "tester_cooldown_enabled");
      g_sc.tester_cooldown_enabled = (v >= 0.5);
   }
```

**Modify cooldown gate in `CheckNativeScalperSetups()`:**

Find:
```mql5
   if(MQLInfoInteger(MQL_TESTER) == 0 && !ScalperCooldownOK()) {
```

Replace with:
```mql5
   if((MQLInfoInteger(MQL_TESTER) == 0 || g_sc.tester_cooldown_enabled) && !ScalperCooldownOK()) {
```

**scalper_config.json** — add to `safety` section:

```json
    "tester_cooldown_enabled": 1
```

**`.env.example`:**

```
# Apply loss cooldown in Strategy Tester too (prevents rapid whipsaw):
# FORGE_TESTER_COOLDOWN_ENABLED=1
```

**sync MAPPING:**

```python
    "FORGE_TESTER_COOLDOWN_ENABLED": ("safety", "tester_cooldown_enabled", "bool01", None, None),
```

---

### Step 3.3 — Widen bounce SL default

**Problem:** `sl_atr_mult: 1.2` puts SL only $2.40-4.80 from entry on M5 XAU.

**Change in `scalper_config.json`:**

```json
    "sl_atr_mult": 1.5
```

(was 1.2)

No code changes needed — FORGE already reads this from config. The wider SL
gives ~25% more room. R:R is maintained because TP1 (BB mid) is typically
1.5-2× ATR away.

---

### Step 3.4 — Increase fast-lock min hold for bounce

**Problem:** 45s is too aggressive — the ratchet tightens SL before the
bounce setup has time to play out.

**Change in `scalper_config.json`:**

```json
    "fast_lock_min_hold_sec_bounce": 90
```

(was 45)

No code changes needed — FORGE already reads this. 90s = 1.5 minutes gives
the bounce 1-2 M5 candles to develop before any SL management kicks in.

---

### Step 3.5 — Directional cooldown (anti-whipsaw)

**Problem:** After a BUY group closes, a SELL can open on the next bar (4
minutes later). This flipping pattern loses money in trending markets.

**New globals** — add after `datetime g_scalper_last_entry_bar`:

```mql5
string   g_scalper_last_direction = "";          // last entry direction for anti-whipsaw
datetime g_scalper_last_direction_time = 0;      // when last direction was entered
```

**ScalperConfig struct** — add to safety section:

```mql5
   bool   direction_cooldown_enabled;
   int    direction_cooldown_bars;     // min M5 bars before opposite direction allowed
```

**InitScalperConfig:**

```mql5
   g_sc.direction_cooldown_enabled = true;
   g_sc.direction_cooldown_bars = 6;
```

**ReadScalperConfig:**

```mql5
   if(JsonHasKey(content, "direction_cooldown_enabled")) {
      v = JsonGetDouble(content, "direction_cooldown_enabled");
      g_sc.direction_cooldown_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "direction_cooldown_bars")) {
      v = JsonGetDouble(content, "direction_cooldown_bars");
      if(v >= 0 && v <= 50) g_sc.direction_cooldown_bars = (int)v;
   }
```

**ReadScalperConfig diagnostics** — add to existing safety PrintFormat:

Include `dir_cool=%s/%d` in the output.

**New helper function** — add after `ScalperOnePerBar()`:

```mql5
bool ScalperDirectionCooldownOK(string proposed_direction) {
   if(!g_sc.direction_cooldown_enabled) return true;
   if(g_scalper_last_direction == "" || g_scalper_last_direction == proposed_direction) return true;
   if(g_scalper_last_direction_time == 0) return true;

   int bars_since = iBars(_Symbol, PERIOD_M5, g_scalper_last_direction_time, TimeCurrent()) - 1;
   if(bars_since < 0) bars_since = 0;

   if(bars_since < g_sc.direction_cooldown_bars) {
      datetime m5bar = iTime(_Symbol, PERIOD_M5, 0);
      if(m5bar != g_scalper_last_sesswarn_log_bar) {
         PrintFormat("FORGE SCALPER: skip gate=direction_cooldown last=%s proposed=%s bars_since=%d min=%d",
                     g_scalper_last_direction, proposed_direction, bars_since, g_sc.direction_cooldown_bars);
      }
      return false;
   }
   return true;
}
```

**Add gate after direction is chosen** — in `CheckNativeScalperSetups()`,
after the bounce/breakout blocks set `direction` but before the M1/regime
gates:

```mql5
   // Directional anti-whipsaw cooldown
   if(direction != "" && !ScalperDirectionCooldownOK(direction)) {
      return;
   }
```

**Record direction on entry** — in the trade execution block (after
`g_scalper_last_entry_bar = bar_time;`):

```mql5
   g_scalper_last_direction = direction;
   g_scalper_last_direction_time = TimeCurrent();
```

**scalper_config.json** — add to `safety` section:

```json
    "direction_cooldown_enabled": 1,
    "direction_cooldown_bars": 6
```

**`.env.example`:**

```
# Directional anti-whipsaw cooldown (min M5 bars before opposite direction):
# FORGE_DIRECTION_COOLDOWN_ENABLED=1
# FORGE_DIRECTION_COOLDOWN_BARS=6
```

**sync MAPPING:**

```python
    "FORGE_DIRECTION_COOLDOWN_ENABLED": ("safety", "direction_cooldown_enabled", "bool01", None, None),
    "FORGE_DIRECTION_COOLDOWN_BARS": ("safety", "direction_cooldown_bars", "int", 0.0, 50.0),
```

---

## 4. Summary of config changes

### `scalper_config.json` — updated defaults

| Key | Old | New | Why |
|-----|-----|-----|-----|
| `bb_bounce.sl_atr_mult` | 1.2 | **1.5** | More breathing room |
| `safety.fast_lock_min_hold_sec_bounce` | 45 | **90** | Let bounce develop |
| `safety.tester_cooldown_enabled` | (new) | **1** | Prevent tester whipsaw |
| `safety.direction_cooldown_enabled` | (new) | **1** | Anti-flip guard |
| `safety.direction_cooldown_bars` | (new) | **6** | 30 min M5 cooldown |
| `session_filter.tester_session_filter` | (new) | **0** | Off by default (user trades all markets) |
| `session_filter.tester_allowed_sessions` | (new) | **"ALL"** | Comma-separated: LONDON,NY,ASIAN or ALL |

### New `.env` variables

```
FORGE_TESTER_SESSION_FILTER
FORGE_TESTER_ALLOWED_SESSIONS
FORGE_TESTER_COOLDOWN_ENABLED
FORGE_DIRECTION_COOLDOWN_ENABLED
FORGE_DIRECTION_COOLDOWN_BARS
```

---

## 5. Verification checklist

1. **Compile:** `make forge-compile` — must succeed.
2. **Config sync:** `python3 scripts/sync_scalper_config_from_env.py` — verify
   new fields appear.
3. **Backtest 1 (default):** Run same period as before. Expect:
   - Fewer immediate SL hits (wider SL + longer hold)
   - No BUY→SELL flip within 6 bars (directional cooldown)
   - Cooldown after losses even in tester
4. **Backtest 2 (session filter):** Set `tester_session_filter: 1` and
   `tester_allowed_sessions: "LONDON,NY"`. Expect fewer trades but higher
   quality (no Asian chop).
5. **Journal log:** Look for `skip gate=direction_cooldown` and
   `skip gate=cooldown` entries.

## 6. Runtime tuning

| Want to... | Set... |
|------------|--------|
| Trade all sessions in tester | `tester_session_filter: 0` (default) |
| Trade only London+NY in tester | `tester_session_filter: 1`, `tester_allowed_sessions: "LONDON,NY"` |
| Disable directional cooldown | `direction_cooldown_enabled: 0` |
| Shorter directional cooldown | `direction_cooldown_bars: 3` (15 min) |
| Tighter SL (aggressive) | `sl_atr_mult: 1.2` (original) |
| Wider SL (conservative) | `sl_atr_mult: 2.0` |
| Faster ratchet (aggressive) | `fast_lock_min_hold_sec_bounce: 45` (original) |

## 7. Bump VERSION

After implementation, bump the version:

```bash
echo "2.3.1" > VERSION
make forge-compile
```

Update `CHANGELOG.md` with a `[2.3.1]` section.

---

*End of prompt.*
