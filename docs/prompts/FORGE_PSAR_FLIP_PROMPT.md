# FORGE Parabolic SAR Flip — Implementation Prompt

> **Self-contained prompt.** Follow every step exactly. No user input needed.
> **Reference:** MQL5 article 17234 — "Parabolic Stop and Reverse Tool" by Christian Benjamin.
> **Source EA:** `/Users/olasumbo/Downloads/Parabolic_SAR.mq5`
> **Mode:** Option B — Informational only (log + data pipeline, no entry gate).

---

## 1. Objective

Add native **Parabolic SAR (PSAR) state tracking** to FORGE as an
informational data signal. PSAR state is logged with every trade entry and
streamed through the full data pipeline for later analysis. It does **not**
gate or block any entries — purely data collection to evaluate whether PSAR
flip correlates with higher win rates before deciding to promote it to a gate.

Five PSAR states are tracked:

| State | Meaning | What it tells you |
|-------|---------|-------------------|
| `FLIP_BULL` | PSAR just flipped from above to below price | Bearish trend ending, bullish reversal |
| `FLIP_BEAR` | PSAR just flipped from below to above price | Bullish trend ending, bearish reversal |
| `BELOW` | PSAR steady below price | Bullish trend continuing |
| `ABOVE` | PSAR steady above price | Bearish trend continuing |
| `NONE` | PSAR disabled or data unavailable | — |

All parameters are hot-reloadable via `scalper_config.json` without
recompilation.

---

## 2. Files to modify (in order)

| File | What changes |
|------|-------------|
| `ea/FORGE.mq5` | Global handle + state, EnsureMTFIndicators, ScalperConfig, InitScalperConfig, ReadScalperConfig, new `DetectPSARState()`, journal log, `market_data.json`, `scalper_entry.json` |
| `config/scalper_config.json` | New keys in `indicators` section |
| `.env.example` | Document new `FORGE_PSAR_*` env variables |
| `scripts/sync_scalper_config_from_env.py` | New MAPPING entries |
| `python/bridge.py` | Flatten psar_state from `market_data.json`, pass to SCRIBE, add to Telegram alert |
| `python/lens.py` | Pass `psar_state` through to `log_market_snapshot` |
| `python/scribe.py` | DDL column, migration, `log_market_snapshot` insert |

---

## 3. Step-by-step implementation

### Step 3.1 — FORGE globals

**Location:** After the RSI divergence globals (after `datetime g_rsi_div_last_arrow_bar = 0;`).

```mql5
// V2: Parabolic SAR state tracking
int      g_h_psar = INVALID_HANDLE;
string   g_psar_state = "NONE";     // NONE | FLIP_BULL | FLIP_BEAR | BELOW | ABOVE
datetime g_psar_last_calc = 0;
```

### Step 3.2 — EnsureMTFIndicators: create iSAR handle

**Location:** At the end of `EnsureMTFIndicators()`, after the `for` loop
closing brace `}`:

```mql5
   if(g_h_psar == INVALID_HANDLE && g_sc.psar_enabled)
      g_h_psar = iSAR(_Symbol, PERIOD_M5, g_sc.psar_step, g_sc.psar_maximum);
```

### Step 3.3 — ScalperConfig struct

**Location:** Inside `struct ScalperConfig { ... }` — add after the RSI
divergence fields (after `bool rsi_div_draw_arrows;`):

```mql5
   // V2: Parabolic SAR
   bool   psar_enabled;
   double psar_step;       // acceleration factor (default 0.02)
   double psar_maximum;    // maximum acceleration (default 0.2)
```

### Step 3.4 — InitScalperConfig defaults

**Location:** After `g_sc.rsi_div_draw_arrows = true;`:

```mql5
   g_sc.psar_enabled = true;
   g_sc.psar_step = 0.02;
   g_sc.psar_maximum = 0.2;
```

### Step 3.5 — ReadScalperConfig JSON parsing

**Location:** After the RSI divergence parsing block (after the
`rsi_div_draw_arrows` block):

```mql5
   // V2 Parabolic SAR
   if(JsonHasKey(content, "psar_enabled")) {
      v = JsonGetDouble(content, "psar_enabled");
      g_sc.psar_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "psar_step")) {
      v = JsonGetDouble(content, "psar_step");
      if(v >= 0.001 && v <= 0.5) g_sc.psar_step = v;
   }
   if(JsonHasKey(content, "psar_maximum")) {
      v = JsonGetDouble(content, "psar_maximum");
      if(v >= 0.01 && v <= 5.0) g_sc.psar_maximum = v;
   }
```

### Step 3.6 — ReadScalperConfig diagnostics log

**Location:** Add after the existing `FORGE V2 RSI_DIV:` PrintFormat:

```mql5
   PrintFormat("FORGE V2 PSAR: enabled=%s step=%.3f max=%.2f",
               g_sc.psar_enabled ? "true" : "false",
               g_sc.psar_step,
               g_sc.psar_maximum);
```

### Step 3.7 — New function: `DetectPSARState()`

**Location:** Place after `DrawDivergenceArrow()`, before `ReadOBZones()`.

Adapted from the author's `CheckForSignal()` (article 17234, lines 73-124)
but simplified: no pending mechanism, no gap threshold, no candlestick
direction check. Pure flip detection from bar[0] vs bar[1].

```mql5
// ── V2: Parabolic SAR state tracking ───────────────────────────
// Ref: MQL5 Article 17234 — "Parabolic Stop and Reverse Tool" by Christian Benjamin
//      https://www.mql5.com/en/articles/17234
void DetectPSARState() {
   if(!g_sc.psar_enabled) { g_psar_state = "NONE"; return; }
   datetime bar_time = iTime(_Symbol, PERIOD_M5, 0);
   if(bar_time == g_psar_last_calc) return;
   g_psar_last_calc = bar_time;

   if(g_h_psar == INVALID_HANDLE) {
      g_h_psar = iSAR(_Symbol, PERIOD_M5, g_sc.psar_step, g_sc.psar_maximum);
      if(g_h_psar == INVALID_HANDLE) return;
   }

   double sar[3], cl[3];
   ArraySetAsSeries(sar, true);
   ArraySetAsSeries(cl, true);
   if(CopyBuffer(g_h_psar, 0, 0, 3, sar) < 3) return;
   if(CopyClose(_Symbol, PERIOD_M5, 0, 3, cl) < 3) return;

   bool cur_below = (sar[0] < cl[0]);   // PSAR below price = bullish
   bool prev_below = (sar[1] < cl[1]);

   string prev_state = g_psar_state;

   if(cur_below && !prev_below)
      g_psar_state = "FLIP_BULL";
   else if(!cur_below && prev_below)
      g_psar_state = "FLIP_BEAR";
   else if(cur_below)
      g_psar_state = "BELOW";
   else
      g_psar_state = "ABOVE";

   if(g_psar_state != prev_state && StringFind(g_psar_state, "FLIP") >= 0)
      PrintFormat("FORGE PSAR: %s (sar0=%.2f cl0=%.2f sar1=%.2f cl1=%.2f)",
                  g_psar_state, sar[0], cl[0], sar[1], cl[1]);
}
```

### Step 3.8 — Call site in OnTimer

**Location:** In the `if(g_cycle % 20 == 0)` block, add after
`DetectRSIDivergence();`:

```mql5
      DetectPSARState();
```

### Step 3.9 — Journal entry log

**Location:** In the trade entry `Print(...)` block, add `PSAR` after the
existing `RSI_DIV` field:

Find:
```mql5
         " RSI_DIV=", g_rsi_div_type,
         " OB_zones=", IntegerToString(g_ob_zone_count),
```

Replace with:
```mql5
         " RSI_DIV=", g_rsi_div_type,
         " PSAR=", g_psar_state,
         " OB_zones=", IntegerToString(g_ob_zone_count),
```

### Step 3.10 — `market_data.json` output

**Location:** In `WriteMarketData()`, after the `rsi_divergence` line:

```mql5
   j += "\"psar_state\":\"" + g_psar_state + "\",";
```

### Step 3.11 — `scalper_entry.json` output

**Location:** In the scalper_entry.json block, after the `rsi_divergence` line:

```mql5
   ej += "\"psar_state\":\"" + g_psar_state + "\",";
```

---

### Step 3.12 — `config/scalper_config.json`

**Location:** In the `"indicators"` section, after `"rsi_div_draw_arrows": 1`:

```json
    "psar_enabled": 1,
    "psar_step": 0.02,
    "psar_maximum": 0.2
```

Remember trailing comma after `"rsi_div_draw_arrows": 1,`.

### Step 3.13 — `.env.example`

**Location:** After the RSI divergence section:

```
# Parabolic SAR state tracking (informational — logged but never gates entries):
# FORGE_PSAR_ENABLED=1
# FORGE_PSAR_STEP=0.02
# FORGE_PSAR_MAXIMUM=0.2
```

### Step 3.14 — `scripts/sync_scalper_config_from_env.py`

**Location:** In the `MAPPING` dict, after the RSI divergence entries:

```python
    "FORGE_PSAR_ENABLED": ("indicators", "psar_enabled", "bool01", None, None),
    "FORGE_PSAR_STEP": ("indicators", "psar_step", "float", 0.001, 0.5),
    "FORGE_PSAR_MAXIMUM": ("indicators", "psar_maximum", "float", 0.01, 5.0),
```

---

### Step 3.15 — `python/bridge.py`

**Location 1 — `_extract_forge_thresholds()`:** After the `rsi_divergence`
line, add:

```python
        "psar_state": (mt5_data or {}).get("psar_state"),
```

**Location 2 — `_check_forge_scalper_entry()` open_context extras:** After
`"rsi_divergence"`, add:

```python
                    "psar_state": entry.get("psar_state"),
```

**Location 3 — BRIDGE activity log for `FORGE_SCALP_ENTRY`:** After
`"rsi_divergence"`, add:

```python
                "psar_state": entry.get("psar_state"),
```

**Location 4 — Telegram notification:** Update the divergence line to also
include PSAR when it's a flip. Find:

```python
            + (f" DIV: {entry.get('rsi_divergence')}" if entry.get("rsi_divergence", "NONE") != "NONE" else "")
```

Replace with:

```python
            + (f" DIV: {entry.get('rsi_divergence')}" if entry.get("rsi_divergence", "NONE") != "NONE" else "")
            + (f" PSAR: {entry.get('psar_state')}" if entry.get("psar_state", "NONE").startswith("FLIP") else "")
```

### Step 3.16 — `python/lens.py`

**Location:** In the `mt5_data` pass-through dict, after `"rsi_divergence"`:

```python
                    "psar_state": mt5_data.get("psar_state"),
```

### Step 3.17 — `python/scribe.py`

**Location 1 — DDL:** In the `market_snapshots` CREATE TABLE, after
`rsi_divergence TEXT,`:

```sql
    psar_state TEXT,
```

**Location 2 — Migration:** After the `rsi_divergence` migration block:

```python
        if "psar_state" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN psar_state TEXT")
            log.info("SCRIBE migration: added psar_state to market_snapshots")
```

**Location 3 — `log_market_snapshot` INSERT:** Add `psar_state` to the
column list and VALUES placeholders. Add:

```python
                 data.get("psar_state")))
```

after the `data.get("rsi_divergence")` in the values tuple. Update the `?`
count accordingly.

---

## 4. Verification checklist

1. **Compile:** `make forge-compile` — must succeed.
2. **Config sync:** `python3 scripts/sync_scalper_config_from_env.py` — verify
   `psar_*` fields appear.
3. **MT5 reload:** Remove FORGE → re-drag from Navigator.
4. **market_data.json:** Verify `"psar_state"` field present.
5. **Journal log:** Check for `FORGE PSAR:` lines on flip events and
   `FORGE V2 PSAR:` on config reload.
6. **SCRIBE DB:**
   ```sql
   SELECT psar_state, COUNT(*) FROM market_snapshots
   WHERE psar_state IS NOT NULL
   GROUP BY psar_state ORDER BY COUNT(*) DESC;
   ```
7. **Telegram:** Next FORGE scalp entry should show `PSAR: FLIP_BULL` (or
   similar) only when a flip is active at entry time.

## 5. Runtime management

| What | How |
|------|-----|
| **Disable PSAR tracking** | `"psar_enabled": 0` in config |
| **Adjust sensitivity** | `"psar_step": 0.05` (faster acceleration) or `0.01` (slower) |
| **Adjust maximum** | `"psar_maximum": 0.4` (tighter trailing) or `0.1` (wider) |
| **Override via .env** | `FORGE_PSAR_ENABLED=0` → `make scalper-env-sync` |

## 6. Future: promoting to a gate

After collecting sufficient data (50+ trades with PSAR state logged), run
this SCRIBE query to evaluate:

```sql
SELECT
  tg.psar_state_at_open,
  COUNT(*) as trades,
  AVG(tc.pips) as avg_pips,
  SUM(CASE WHEN tc.close_reason LIKE 'TP%' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as tp_hit_pct
FROM trade_groups tg
JOIN trade_closures tc ON tc.group_id = tg.id
WHERE tg.source = 'FORGE_NATIVE_SCALP'
GROUP BY tg.psar_state_at_open;
```

If `FLIP_BULL`/`FLIP_BEAR` entries show significantly higher `tp_hit_pct`,
add a one-line gate similar to RSI divergence:

```mql5
bool psar_ok_buy  = !g_sc.psar_gate_enabled || (g_psar_state != "ABOVE" && g_psar_state != "FLIP_BEAR");
bool psar_ok_sell = !g_sc.psar_gate_enabled || (g_psar_state != "BELOW" && g_psar_state != "FLIP_BULL");
```

---

## 7. Bump VERSION

After implementation, bump the version:

```bash
echo "2.3.0" > VERSION
make forge-compile
```

Update `CHANGELOG.md` with a `[2.3.0]` section documenting PSAR tracking.

---

*End of prompt.*
