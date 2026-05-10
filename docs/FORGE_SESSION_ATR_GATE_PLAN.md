# FORGE — Session-Based ATR Entry Quality Gate

> Status: PLANNED — not yet implemented
> Motivation: `entry_quality_atr` blocked 98% of signals on a Apr-29 backtest because
> Asian session ATR (1.5–3.0 pts) is structurally below the global floor of 3.5.
> A single global threshold either chokes quiet sessions or under-protects volatile ones.

---

## Problem

The current gate at `FORGE.mq5:4586`:

```mql5
if(g_sc.min_entry_atr > 0.0 && atr < g_sc.min_entry_atr) {
    JournalRecordSignal("SKIP", "entry_quality_atr", ...);
}
```

Uses a single global floor (`min_entry_atr = 3.5`). On XAUUSD:

| Session | Typical ATR range | With 3.5 floor |
|---|---|---|
| ASIAN | 1.5 – 3.0 pts | ~100% blocked |
| SYDNEY | 1.0 – 2.5 pts | ~100% blocked |
| LONDON | 3.0 – 8.0 pts | Passes most of the time |
| LONDON_NY | 5.0 – 12.0 pts | Almost never blocked |
| NEW_YORK | 2.5 – 6.0 pts | Partially blocked |

Lowering the global floor to fix Asian session risks accepting low-quality entries
during volatile London/NY conditions where higher ATR is the norm.

---

## Proposed Solution — Per-Session ATR Floors

### 1. New scalper_config fields

Add four new optional fields to the `ScalperConfig` struct in `ea/FORGE.mq5`.
A value of `0.0` means "inherit from global `min_entry_atr`" — preserves
full backward compatibility.

```mql5
// In struct ScalperConfig (near line 352)
double min_entry_atr;            // global floor — fallback for all sessions
double min_entry_atr_asian;      // ASIAN override (0 = use global)
double min_entry_atr_london;     // LONDON override (0 = use global)
double min_entry_atr_london_ny;  // LONDON_NY overlap override (0 = use global)
double min_entry_atr_ny;         // NEW_YORK override (0 = use global)
```

### 2. Default values (scalper_config.defaults.json)

```json
"min_entry_atr":            1.0,
"min_entry_atr_asian":      1.0,
"min_entry_atr_london":     2.5,
"min_entry_atr_london_ny":  3.5,
"min_entry_atr_ny":         2.0
```

Rationale:
- `asian = 1.0` — accepts quiet Gold conditions; RSI/body/BB gates still apply
- `london = 2.5` — London open picks up; moderate protection
- `london_ny = 3.5` — overlap is the most volatile; restore the original 3.5 floor
- `ny = 2.0` — NY afternoon quiets down; intermediate threshold

### 3. FORGE.mq5 gate change (line 4586)

```mql5
// Session-aware ATR floor
double atr_floor = g_sc.min_entry_atr;  // global fallback
if(g_current_session == SESSION_ASIAN && g_sc.min_entry_atr_asian > 0.0)
    atr_floor = g_sc.min_entry_atr_asian;
else if(g_current_session == SESSION_LONDON && g_sc.min_entry_atr_london > 0.0)
    atr_floor = g_sc.min_entry_atr_london;
else if(g_current_session == SESSION_LONDON_NY && g_sc.min_entry_atr_london_ny > 0.0)
    atr_floor = g_sc.min_entry_atr_london_ny;
else if(g_current_session == SESSION_NEW_YORK && g_sc.min_entry_atr_ny > 0.0)
    atr_floor = g_sc.min_entry_atr_ny;

if(atr_floor > 0.0 && atr < atr_floor) {
    JournalRecordSignal("SKIP", "entry_quality_atr", "", direction, ...);
    return false;
}
```

### 4. JSON parser additions (near line 2929)

```mql5
if(JsonHasKey(content, "min_entry_atr")) {
    v = JsonGetDouble(content, "min_entry_atr");
    if(v >= 0.0 && v <= 50.0) g_sc.min_entry_atr = v;
}
if(JsonHasKey(content, "min_entry_atr_asian")) {
    v = JsonGetDouble(content, "min_entry_atr_asian");
    if(v >= 0.0 && v <= 50.0) g_sc.min_entry_atr_asian = v;
}
if(JsonHasKey(content, "min_entry_atr_london")) {
    v = JsonGetDouble(content, "min_entry_atr_london");
    if(v >= 0.0 && v <= 50.0) g_sc.min_entry_atr_london = v;
}
if(JsonHasKey(content, "min_entry_atr_london_ny")) {
    v = JsonGetDouble(content, "min_entry_atr_london_ny");
    if(v >= 0.0 && v <= 50.0) g_sc.min_entry_atr_london_ny = v;
}
if(JsonHasKey(content, "min_entry_atr_ny")) {
    v = JsonGetDouble(content, "min_entry_atr_ny");
    if(v >= 0.0 && v <= 50.0) g_sc.min_entry_atr_ny = v;
}
```

### 5. Default initialisation (near line 2333)

```mql5
g_sc.min_entry_atr           = 1.0;
g_sc.min_entry_atr_asian     = 1.0;
g_sc.min_entry_atr_london    = 2.5;
g_sc.min_entry_atr_london_ny = 3.5;
g_sc.min_entry_atr_ny        = 2.0;
```

### 6. Sync script additions (sync_scalper_config_from_env.py)

```python
"FORGE_MIN_ENTRY_ATR":            ("safety", "min_entry_atr",            "float", 0.0, 50.0),
"FORGE_MIN_ENTRY_ATR_ASIAN":      ("safety", "min_entry_atr_asian",      "float", 0.0, 50.0),
"FORGE_MIN_ENTRY_ATR_LONDON":     ("safety", "min_entry_atr_london",     "float", 0.0, 50.0),
"FORGE_MIN_ENTRY_ATR_LONDON_NY":  ("safety", "min_entry_atr_london_ny",  "float", 0.0, 50.0),
"FORGE_MIN_ENTRY_ATR_NY":         ("safety", "min_entry_atr_ny",         "float", 0.0, 50.0),
```

### 7. .env variables

```bash
# Global floor — fallback when no session override is set (0 = disabled)
FORGE_MIN_ENTRY_ATR=1.0

# Per-session ATR floors (0 = use global FORGE_MIN_ENTRY_ATR)
FORGE_MIN_ENTRY_ATR_ASIAN=1.0        # Asian: 1.5–3.0 pts typical
FORGE_MIN_ENTRY_ATR_LONDON=2.5       # London open: 3–8 pts typical
FORGE_MIN_ENTRY_ATR_LONDON_NY=3.5    # Overlap: most volatile, 5–12 pts typical
FORGE_MIN_ENTRY_ATR_NY=2.0           # NY: 2.5–6 pts typical
```

---

## Backward Compatibility

- All session fields default to `0.0` in the struct init.
- If a session field is `0.0`, the global `min_entry_atr` is used — **existing configs
  with no session fields work identically to today**.
- Setting any session field to `0.0` in the JSON explicitly disables that override.

---

## Testing Plan

1. Run a backtest covering Apr 29–May 7 (LONDON + ASIAN sessions both present).
2. Before: `entry_quality_atr` count by session (expect ~98% in ASIAN).
3. After: `entry_quality_atr` count should drop dramatically in ASIAN.
4. Confirm LONDON_NY still has the 3.5 floor — `entry_quality_atr` should still fire
   when ATR is genuinely low during London/NY overlap.
5. Check gate breakdown in Athena Backtest tab: `entry_quality_atr` should no longer
   dominate; next tier of gates (body, direction, BB contraction) should surface.

---

## Files to Change

| File | Change |
|---|---|
| `ea/FORGE.mq5` | Struct fields, defaults init (~2333), JSON parser (~2929), gate logic (~4586) |
| `scripts/sync_scalper_config_from_env.py` | 4 new env→config mappings |
| `config/scalper_config.defaults.json` | 4 new fields with recommended defaults |
| `.env` | 4 new `FORGE_MIN_ENTRY_ATR_*` vars |
| `.env.example` | Document all 5 vars with session ATR ranges |

---

## References

- `ea/FORGE.mq5:352` — ScalperConfig struct
- `ea/FORGE.mq5:2333` — default init block
- `ea/FORGE.mq5:2929` — JSON parser (ReadScalperConfig)
- `ea/FORGE.mq5:4586` — current ATR gate
- `docs/FORGE_SESSION_TIME_PRODUCTION.md` — session definitions and UTC hours
- `config/gate_legend.json` → `entry_quality_atr` gate legend entry
