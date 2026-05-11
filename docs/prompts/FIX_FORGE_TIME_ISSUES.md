# Local-AI Prompt — Cross-Stack Session/Time/Killzone Refactor (v3 — FINAL)

You are working on the **ATHENA / FORGE** trading system. This prompt supersedes any
prior version. Files in scope:

| File                              | Lines | Role                                              |
|-----------------------------------|-------|---------------------------------------------------|
| `ea/FORGE.mq5`                    | 5474  | MT5 Expert Advisor (entry/exit, journal)          |
| `python/trading_session.py`       | 125   | Python session-label module                       |
| `python/bridge.py`                | 4910  | Orchestrator: MT5 ↔ SCRIBE ↔ ATHENA               |
| `python/scribe.py`                | 1854  | SQLite DB layer                                   |
| `python/athena_api.py`            | 1442  | Flask API for dashboard                           |
| `dashboard/app.js`                | 1515  | React dashboard (inline Babel)                    |
| `scripts/sync_scalper_config_from_env.py` | 337 | env+defaults → scalper_config.json builder |
| `config/scalper_config.defaults.json` | (data) | **Editable** baseline — do NOT edit `scalper_config.json` |
| `schemas/files/status.schema.json`        | (data) | BRIDGE → ATHENA status contract       |
| `schemas/files/market_data.schema.json`   | (data) | FORGE → BRIDGE market contract        |
| `schemas/openapi.yaml`            | 1181  | HTTP API contract (ATHENA)                        |
| `schemas/scribe_query_examples.json` | (data) | Documented SCRIBE query examples              |

Out of scope (verified no relevant content): `index.html`, `dep_map.jsx`,
`management_cmd.schema.json`, `aurum_cmd.schema.json`, `forge_command.schema.json`,
`reconciler_last.json`, `manifest.json`.

After your edits:
- `FORGE.mq5` line 58: `#property version "2.xy"` - bump me
- `VERSION` file (repo root): bump patch (e.g. `2.7.x` → `2.7.y`). - bump me
  `sync_scalper_config_from_env.py` `_stamp_version` helper auto-stamps it into
  `scalper_config.json`.
- `athena_api.py` `_SYSTEM_VERSION`: bump patch.

The work is split into **Parts A–H**. **Part A is mandatory.** B–H are strongly
recommended; if you skip any, list which and why at the top of your output.

---

## 0. Critical pipeline facts — read before touching any config file

### 0.1 `scalper_config.json` is GENERATED, not hand-edited

Verified at `sync_scalper_config_from_env.py:21-22, 304-333`. The flow is:

```
config/scalper_config.defaults.json   (commit-controlled baseline)
                +
.env (FORGE_* keys, optional)
                ↓
        sync_scalper_config_from_env.py
                ↓
config/scalper_config.json   (GENERATED — do not edit by hand)
                ↓ (copied via _sync_to_mt5 helper)
MT5/scalper_config.json      (FORGE reads this, hot-reloads on change)
```

Triggered by:
- `make scalper-env-sync` — regenerate JSON only
- `make forge-compile` — depends on `scalper-env-sync`, also recompiles `.ex5`

**Therefore:** all config additions in this prompt go in
`config/scalper_config.defaults.json`. The user runs `make scalper-env-sync` after.
Adding to `config/scalper_config.json` directly will be silently overwritten on next
sync.

### 0.2 FORGE's JSON parser is a flat text searcher, not a tree parser

Verified at `FORGE.mq5:5410-5447`. `JsonHasKey(json, key)` does:

```cpp
return StringFind(json, "\"" + key + "\"") >= 0;
```

It finds the key **anywhere** in the document — top-level or nested. `JsonGetDouble`
parses the value following the **first** occurrence. Consequence:

- Nesting in JSON (e.g. `"session_filter": {"london_start_utc": 7}`) does not require
  FORGE to extract the nested object first. `JsonHasKey(content, "london_start_utc")`
  on the whole document still works.
- **Risk:** if the same key name appears in two sections, the parser returns the first.
  Choose unique key names. The `kz_*` and `*_min` suffixes used in this prompt are
  unique to the new config; no collision risk.

### 0.3 Two parallel session systems exist by design

FORGE.mq5 (3 labels: ASIAN/LONDON/NY/OFF) drives **entry gating + journal columns**.
Python `trading_session.py` (6 labels: SYDNEY/ASIAN/LONDON/LONDON_NY/NEW_YORK/OFF_HOURS)
drives **status, AURUM prompts, SCRIBE rollover**. **Do not unify them.** They have
different jobs. Killzones go on both sides as a parallel layer.

### 0.4 Naming convention for fresh-vs-persisted state

Verified at `athena_api.py:477-478` and `app.js:723-724` (literal:
`{D.session_utc||D.session}`). Convention:

- `<field>` = persisted (last value BRIDGE wrote to status.json)
- `<field>_utc` = freshly computed by a `trading_session.py` function

New killzone fields **must** follow this: `killzone` (persisted), `killzone_utc` (fresh).

---

## 1. Naming conventions — match what each file uses

- **MQL5:** `PascalCase` functions, `g_sc.<snake>` config struct fields, globals
  `g_*` / `g_scalper_*` / `g_forge_*`, log-throttle globals
  `g_scalper_last_<topic>_log_bar`, log prefixes `FORGE: …` / `FORGE SCALPER: …` /
  `FORGE TESTER: …` / `FORGE JOURNAL: …`. JSON output keys with `forge_` prefix when
  introducing FORGE-specific top-level keys (matches existing `forge_version`,
  `forge_config`).
- **Python:** snake_case; module constants `UPPER_SNAKE`; env vars `SESSION_*` /
  `AEGIS_*` / `BRIDGE_*` / `FORGE_*` / `KILLZONES_*`; loggers
  `logging.getLogger(<name>)`; instance attrs `self._<snake>`.
- **JS/React:** camelCase locals; `T.<color>` from theme; `D.<field>` for live data.
- **JSON keys:** snake_case, e.g. `kz_ny_open_start_min`.
- **DB columns:** snake_case; additive migrations via `ALTER TABLE … ADD COLUMN`.
- **JSON Schema:** `additionalProperties: true` at the top level remains so unless
  the existing schema sets it false. Add new properties to `properties:` block; do
  not change existing types.
- **OpenAPI:** match existing camelCase / snake_case decisions per response.
- **Scalper config sections:** existing `bb_bounce`, `bb_breakout`, `indicators`,
  `session_filter`, `safety`, `journal`, `dd_event_tp`, `lot_sizing`. New killzone
  keys go in **`session_filter`** (not a new section) since they're session-related;
  this minimises schema drift.

---

# PART A — FORGE.mq5 (mandatory)

## A.1 Reference: existing code anchors (verified line numbers in v2.75) - might change - so verify.

| What                                                  | Line(s)        |
|-------------------------------------------------------|----------------|
| `#property version`                                   | 58             |
| Module globals (`g_scalper_*`)                        | 110 – 145      |
| `struct ScalperConfig` Session block                  | 196 – 206      |
| Session field defaults in `InitScalperConfig`         | 2045 – 2051    |
| Session JSON keys read in `ReadScalperConfig`         | 2334 – 2358    |
| `ResetScalperSessionStateIfNeeded()`                  | 2806 – 2845    |
| `ScalperSessionOK()`                                  | 2847 – 2858    |
| `ScalperTesterSessionOK()`                            | 2860 – 2884    |
| `ScalperDirectionCooldownOK()` (has bug)              | 2942 – 2959    |
| Journal SIGNALS schema                                | ~3370 – 3394   |
| Journal indices & migrations (good place for ALTER)   | ~3442 – 3456   |
| `JournalRecordSignal()` session block                 | 3578 – 3583    |
| Session-blocked check in `CheckNativeScalperSetups()` | 3997 – 4021    |
| `open_groups` gate (no throttle)                      | 4047 – 4051    |
| `session_trade_cap` gate (no throttle)                | 4052 – 4057    |
| `cooldown` gate (correctly throttled — reference)     | 4058 – 4067    |
| `WriteMarketData()`                                   | 1749 – 1820    |
| `WriteBrokerInfo()`                                   | 1963 – 1984    |
| `JsonHasKey`, `JsonGetDouble`, `JsonGetString`        | 5410 – 5447    |

## A.2 Bugs being fixed in FORGE.mq5

1. **Hour-only precision** — every session check uses `dt.hour >= start && dt.hour < end`
   (lines 2812, 2814, 2851–2852, 2870–2872, 3582–3583, 4007). No minute resolution.
2. **No DST handling** — windows stored as UTC hours; broker–NY offset shifts twice
   a year between +7h and +6h.
3. **ASIA is a fallback, not a window** — anything not LONDON/NY becomes ASIAN.
4. **Default config is degenerate** — `london_start=0, london_end=24` (lines 2045–2048)
   means every hour matches LONDON, so NY/ASIA branches never fire. Other code paths
   (e.g. `JournalRecordSignal`) silently mislabel signals as LONDON until JSON loads.
5. **No killzone detection.**
6. **Day rollover uses UTC midnight** (line 2821) regardless of anchor.
7. **`ScalperDirectionCooldownOK` log throttle is broken** (line 2952) — uses
   `g_scalper_last_sesswarn_log_bar` (the wrong global) and never updates it.
8. **`open_groups` and `session_trade_cap` gates have no throttle** (lines 4047–4051,
   4052–4057) — log + insert SIGNALS rows every tick while at the cap.

## A.3 Tier 1 — MANDATORY: Session/Time/Killzone Refactor

### A.3.1 New struct fields (append to `ScalperConfig` after line 206)

```cpp
   // Session — minute precision (additive; integer minute-of-day 0..1440)
   int    london_start_min;       // -1 = use legacy hour-only field
   int    london_end_min;
   int    ny_start_min;
   int    ny_end_min;
   int    asia_start_min;         // -1 = behaves as fallback (current behaviour)
   int    asia_end_min;

   // Session — NY-time anchoring (DST-aware)
   bool   sessions_ny_anchored;   // false = UTC (legacy); true = NY local

   // Killzones (NY-time minute-of-day; killzones are always NY-anchored)
   bool   killzones_enabled;
   bool   killzones_gate_entries; // false = track only (default); true = require active KZ
   int    kz_asia_start_min;
   int    kz_asia_end_min;
   int    kz_london_open_start_min;
   int    kz_london_open_end_min;
   int    kz_ny_open_start_min;
   int    kz_ny_open_end_min;
   int    kz_london_close_start_min;
   int    kz_london_close_end_min;
```

### A.3.2 New globals (place at end of `g_scalper_*` block, ~line 145)

```cpp
string   g_scalper_last_killzone_label = "";
datetime g_scalper_killzone_start_time = 0;
int      g_scalper_killzone_trades    = 0;
```

### A.3.3 New helper functions (insert above `ResetScalperSessionStateIfNeeded`)

```cpp
int FirstSundayOfMonth(int year, int month) {
   MqlDateTime d;
   d.year = year; d.mon = month; d.day = 1;
   d.hour = 0; d.min = 0; d.sec = 0;
   datetime t = StructToTime(d);
   TimeToStruct(t, d);
   return (d.day_of_week == 0) ? 1 : (1 + (7 - d.day_of_week));
}

bool IsUS_DST(datetime utc) {
   MqlDateTime d; TimeToStruct(utc, d);
   if(d.mon < 3 || d.mon > 11) return false;
   if(d.mon > 3 && d.mon < 11) return true;
   if(d.mon == 3) {
      int second_sun = FirstSundayOfMonth(d.year, 3) + 7;
      if(d.day < second_sun) return false;
      if(d.day > second_sun) return true;
      return d.hour >= 7;        // 02:00 EST → 07:00 UTC
   }
   int first_sun = FirstSundayOfMonth(d.year, 11);
   if(d.day < first_sun) return true;
   if(d.day > first_sun) return false;
   return d.hour < 6;             // 02:00 EDT → 06:00 UTC
}

datetime GetNYTimeNow() {
   datetime utc = TimeGMT();
   int off_sec  = IsUS_DST(utc) ? -4 * 3600 : -5 * 3600;
   return utc + off_sec;
}

datetime GetSessionAnchorTime() {
   return g_sc.sessions_ny_anchored ? GetNYTimeNow() : TimeGMT();
}

bool MinuteInWindow(int now_min, int start_min, int end_min) {
   if(start_min < 0 || end_min < 0) return false;
   if(start_min < end_min) return now_min >= start_min && now_min < end_min;
   return now_min >= start_min || now_min < end_min;     // wraps midnight
}

void GetEffectiveLondonWindow(int &start_min, int &end_min) {
   start_min = (g_sc.london_start_min >= 0) ? g_sc.london_start_min : g_sc.london_start * 60;
   end_min   = (g_sc.london_end_min   >= 0) ? g_sc.london_end_min   : g_sc.london_end   * 60;
}
void GetEffectiveNYWindow(int &start_min, int &end_min) {
   start_min = (g_sc.ny_start_min >= 0) ? g_sc.ny_start_min : g_sc.ny_start * 60;
   end_min   = (g_sc.ny_end_min   >= 0) ? g_sc.ny_end_min   : g_sc.ny_end   * 60;
}
void GetEffectiveAsiaWindow(int &start_min, int &end_min) {
   start_min = g_sc.asia_start_min;
   end_min   = g_sc.asia_end_min;
}

string ComputeCurrentSessionLabel() {
   datetime t = GetSessionAnchorTime();
   MqlDateTime dt; TimeToStruct(t, dt);
   int now_min = dt.hour * 60 + dt.min;
   int ls, le, ns, ne, asn, ae;
   GetEffectiveLondonWindow(ls, le);
   GetEffectiveNYWindow(ns, ne);
   GetEffectiveAsiaWindow(asn, ae);
   if(MinuteInWindow(now_min, ns, ne)) return "NY";
   if(MinuteInWindow(now_min, ls, le)) return "LONDON";
   if(asn >= 0 && ae >= 0) {
      if(MinuteInWindow(now_min, asn, ae)) return "ASIAN";
      return "OFF";
   }
   return "ASIAN";    // legacy fallback
}

string ComputeCurrentKillzoneLabel() {
   if(!g_sc.killzones_enabled) return "";
   datetime ny = GetNYTimeNow();
   MqlDateTime dt; TimeToStruct(ny, dt);
   if(dt.day_of_week == 6) return "";                          // Saturday
   if(dt.day_of_week == 0 && dt.hour < 17) return "";          // Sun pre-open
   int now_min = dt.hour * 60 + dt.min;
   if(MinuteInWindow(now_min, g_sc.kz_ny_open_start_min,      g_sc.kz_ny_open_end_min))      return "NY_OPEN_KZ";
   if(MinuteInWindow(now_min, g_sc.kz_london_open_start_min,  g_sc.kz_london_open_end_min))  return "LONDON_OPEN_KZ";
   if(MinuteInWindow(now_min, g_sc.kz_london_close_start_min, g_sc.kz_london_close_end_min)) return "LONDON_CLOSE_KZ";
   if(MinuteInWindow(now_min, g_sc.kz_asia_start_min,         g_sc.kz_asia_end_min))         return "ASIAN_KZ";
   return "";
}

int ForgeBrokerGMTOffsetSec() { return (int)(TimeTradeServer() - TimeGMT()); }
```

### A.3.4 Update `InitScalperConfig` (append after line 2051)

```cpp
   g_sc.london_start_min = -1;  g_sc.london_end_min = -1;
   g_sc.ny_start_min     = -1;  g_sc.ny_end_min     = -1;
   g_sc.asia_start_min   = -1;  g_sc.asia_end_min   = -1;
   g_sc.sessions_ny_anchored     = false;
   g_sc.killzones_enabled        = false;
   g_sc.killzones_gate_entries   = false;
   g_sc.kz_asia_start_min        = 19*60;
   g_sc.kz_asia_end_min          =  3*60;
   g_sc.kz_london_open_start_min =  2*60;
   g_sc.kz_london_open_end_min   =  5*60;
   g_sc.kz_ny_open_start_min     =  7*60;
   g_sc.kz_ny_open_end_min       = 10*60;
   g_sc.kz_london_close_start_min= 10*60;
   g_sc.kz_london_close_end_min  = 12*60;
```

### A.3.5 Update `ReadScalperConfig` (insert after line 2358)

Keep existing readers untouched. Add additively:

```cpp
   if(JsonHasKey(content, "london_start_min")) { v=JsonGetDouble(content,"london_start_min"); if(v>=0&&v<=1439) g_sc.london_start_min=(int)v; }
   if(JsonHasKey(content, "london_end_min"))   { v=JsonGetDouble(content,"london_end_min");   if(v>=0&&v<=1440) g_sc.london_end_min  =(int)v; }
   if(JsonHasKey(content, "ny_start_min"))     { v=JsonGetDouble(content,"ny_start_min");     if(v>=0&&v<=1439) g_sc.ny_start_min    =(int)v; }
   if(JsonHasKey(content, "ny_end_min"))       { v=JsonGetDouble(content,"ny_end_min");       if(v>=0&&v<=1440) g_sc.ny_end_min      =(int)v; }
   if(JsonHasKey(content, "asia_start_min"))   { v=JsonGetDouble(content,"asia_start_min");   if(v>=0&&v<=1439) g_sc.asia_start_min  =(int)v; }
   if(JsonHasKey(content, "asia_end_min"))     { v=JsonGetDouble(content,"asia_end_min");     if(v>=0&&v<=1440) g_sc.asia_end_min    =(int)v; }
   if(JsonHasKey(content, "sessions_ny_anchored")) { v=JsonGetDouble(content,"sessions_ny_anchored"); g_sc.sessions_ny_anchored=(v>=0.5); }
   if(JsonHasKey(content, "killzones_enabled"))    { v=JsonGetDouble(content,"killzones_enabled");    g_sc.killzones_enabled=(v>=0.5); }
   if(JsonHasKey(content, "killzones_gate_entries")){v=JsonGetDouble(content,"killzones_gate_entries");g_sc.killzones_gate_entries=(v>=0.5); }
   if(JsonHasKey(content, "kz_asia_start_min"))         { v=JsonGetDouble(content,"kz_asia_start_min");         if(v>=0&&v<=1439) g_sc.kz_asia_start_min        =(int)v; }
   if(JsonHasKey(content, "kz_asia_end_min"))           { v=JsonGetDouble(content,"kz_asia_end_min");           if(v>=0&&v<=1440) g_sc.kz_asia_end_min          =(int)v; }
   if(JsonHasKey(content, "kz_london_open_start_min"))  { v=JsonGetDouble(content,"kz_london_open_start_min");  if(v>=0&&v<=1439) g_sc.kz_london_open_start_min =(int)v; }
   if(JsonHasKey(content, "kz_london_open_end_min"))    { v=JsonGetDouble(content,"kz_london_open_end_min");    if(v>=0&&v<=1440) g_sc.kz_london_open_end_min   =(int)v; }
   if(JsonHasKey(content, "kz_ny_open_start_min"))      { v=JsonGetDouble(content,"kz_ny_open_start_min");      if(v>=0&&v<=1439) g_sc.kz_ny_open_start_min     =(int)v; }
   if(JsonHasKey(content, "kz_ny_open_end_min"))        { v=JsonGetDouble(content,"kz_ny_open_end_min");        if(v>=0&&v<=1440) g_sc.kz_ny_open_end_min       =(int)v; }
   if(JsonHasKey(content, "kz_london_close_start_min")) { v=JsonGetDouble(content,"kz_london_close_start_min"); if(v>=0&&v<=1439) g_sc.kz_london_close_start_min=(int)v; }
   if(JsonHasKey(content, "kz_london_close_end_min"))   { v=JsonGetDouble(content,"kz_london_close_end_min");   if(v>=0&&v<=1440) g_sc.kz_london_close_end_min  =(int)v; }
```

### A.3.6 Replace `ResetScalperSessionStateIfNeeded` body (lines 2806–2845)

```cpp
void ResetScalperSessionStateIfNeeded() {
   datetime anchor = GetSessionAnchorTime();
   MqlDateTime dt; TimeToStruct(anchor, dt);
   datetime today = StringToTime(StringFormat("%04d.%02d.%02d 00:00", dt.year, dt.mon, dt.day));
   if(today <= 0) return;

   string current_session  = ComputeCurrentSessionLabel();
   string current_killzone = ComputeCurrentKillzoneLabel();

   if(g_scalper_last_reset_day == 0) {
      g_scalper_last_reset_day      = today;
      g_scalper_last_session_label  = current_session;
      g_scalper_last_killzone_label = current_killzone;
      return;
   }

   if(today != g_scalper_last_reset_day) {
      g_scalper_last_reset_day      = today;
      g_scalper_session_trades      = 0;
      g_scalper_killzone_trades     = 0;
      g_scalper_last_entry_bar      = 0;
      g_scalper_last_direction      = "";
      g_scalper_last_direction_time = 0;
      g_first_buy_entry_price       = 0.0;
      g_first_sell_entry_price      = 0.0;
      g_scalper_last_session_label  = current_session;
      g_scalper_last_killzone_label = current_killzone;
      PrintFormat("FORGE SCALPER: daily reset (anchor=%s)",
                  g_sc.sessions_ny_anchored ? "NY" : "UTC");
      return;
   }

   if(g_scalper_last_session_label == "") g_scalper_last_session_label = current_session;
   if(current_session != g_scalper_last_session_label) {
      g_scalper_last_session_label = current_session;
      g_first_buy_entry_price      = 0.0;
      g_first_sell_entry_price     = 0.0;
      PrintFormat("FORGE SCALPER: session change → %s (%s %02d:%02d)",
                  current_session, g_sc.sessions_ny_anchored ? "NY" : "UTC", dt.hour, dt.min);
   }

   if(current_killzone != g_scalper_last_killzone_label) {
      g_scalper_last_killzone_label = current_killzone;
      g_scalper_killzone_start_time = anchor;
      g_scalper_killzone_trades     = 0;
      if(StringLen(current_killzone) > 0) {
         PrintFormat("FORGE SCALPER: killzone → %s (NY %02d:%02d)",
                     current_killzone, dt.hour, dt.min);
      }
   }
}
```

### A.3.7 Replace `ScalperSessionOK` (lines 2847–2858)

```cpp
bool ScalperSessionOK() {
   string s = ComputeCurrentSessionLabel();
   if(s == "OFF") return false;
   if(s == "LONDON" && g_sc.skip_london) return false;
   if(s == "NY"     && g_sc.skip_ny)     return false;
   if(s == "ASIAN"  && g_sc.skip_asian)  return false;
   if(g_sc.killzones_enabled && g_sc.killzones_gate_entries) {
      if(StringLen(ComputeCurrentKillzoneLabel()) == 0) return false;
   }
   return true;
}
```

### A.3.8 Replace `ScalperTesterSessionOK` body (lines 2860–2884)

```cpp
bool ScalperTesterSessionOK() {
   if(!g_sc.tester_session_filter) return true;
   string allowed = g_sc.tester_allowed_sessions;
   if(allowed == "ALL" || allowed == "") return true;
   string current_session = ComputeCurrentSessionLabel();
   if(current_session == "OFF") return false;
   string parts[];
   int count = StringSplit(allowed, ',', parts);
   for(int i = 0; i < count; i++) {
      StringTrimLeft(parts[i]); StringTrimRight(parts[i]); StringToUpper(parts[i]);
      if(parts[i] == current_session) return true;
   }
   return false;
}
```

### A.3.9 Update `JournalRecordSignal` session block (lines 3578–3583)

Replace those five lines with:

```cpp
   string session  = ComputeCurrentSessionLabel();
   string killzone = ComputeCurrentKillzoneLabel();
```

In the SQL column list (line 3590) add `killzone` between `session` and `magic`. In
the VALUES list (line 3616) add `+ "'" + killzone + "', "` in the matching slot.
Requires the schema migration in A.6.

### A.3.10 Update session_off log (line ~4015–4016)

```cpp
         PrintFormat("FORGE SCALPER: skip gate=session_off anchor=%s %02d:%02d (no trades)",
                     g_sc.sessions_ny_anchored ? "NY" : "UTC", dt.hour, dt.min);
```

## A.4 Tier 2 — Log throttle bug fixes

Add three new globals near line 145:

```cpp
datetime g_scalper_last_dircool_log_bar = 0;
datetime g_scalper_last_opengroups_log_bar = 0;
datetime g_scalper_last_sesscap_log_bar = 0;
```

**`ScalperDirectionCooldownOK` (lines 2950–2957):**

```cpp
   if(bars_since < g_sc.direction_cooldown_bars) {
      datetime m5bar = iTime(_Symbol, PERIOD_M5, 0);
      if(m5bar != g_scalper_last_dircool_log_bar) {
         g_scalper_last_dircool_log_bar = m5bar;
         PrintFormat("FORGE SCALPER: skip gate=direction_cooldown last=%s proposed=%s bars_since=%d min=%d",
                     g_scalper_last_direction, proposed_direction, bars_since, g_sc.direction_cooldown_bars);
      }
      return false;
   }
```

**`open_groups` gate (lines 4047–4051):** mirror the `cooldown` pattern at line 4061
using `g_scalper_last_opengroups_log_bar`.

**`session_trade_cap` gate (lines 4052–4057):** same with `g_scalper_last_sesscap_log_bar`.

## A.5 Tier 3 — JSON output visibility

### A.5.1 `WriteMarketData` (line 1749)

**IMPORTANT NAMING:** The schema `market_data.schema.json` already declares
`session: { type: string }` at the top level. Adding a nested `session: {…}` would
break the schema. Use `forge_session_state` instead — matches the existing
`forge_config`, `forge_version` prefix pattern.

After the `forge_config` block (~line 1791), add:

```cpp
   j += "\"forge_session_state\":{";
   j += "\"label\":\""           + JsonEscape(ComputeCurrentSessionLabel())  + "\",";
   j += "\"killzone\":\""        + JsonEscape(ComputeCurrentKillzoneLabel()) + "\",";
   j += "\"anchor_mode\":\""     + (g_sc.sessions_ny_anchored ? "NY" : "UTC") + "\",";
   j += "\"killzones_enabled\":" + IntegerToString(g_sc.killzones_enabled ? 1 : 0) + ",";
   j += "\"killzones_gate_entries\":" + IntegerToString(g_sc.killzones_gate_entries ? 1 : 0) + ",";
   j += "\"trades_this_session\":"  + IntegerToString(g_scalper_session_trades)  + ",";
   j += "\"trades_this_killzone\":" + IntegerToString(g_scalper_killzone_trades);
   j += "},";
```

### A.5.2 `WriteBrokerInfo` (line 1963)

After `gmt_time` (line 1975):

```cpp
   j += "\"gmt_offset_sec\":" + IntegerToString(ForgeBrokerGMTOffsetSec()) + ",";
   j += "\"is_us_dst\":"      + IntegerToString(IsUS_DST(TimeGMT()) ? 1 : 0) + ",";
```

## A.6 Tier 4 — Journal SIGNALS schema migration

After line 3456:

```cpp
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN killzone TEXT DEFAULT '';");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_killzone ON SIGNALS(killzone);");
```

(Required by A.3.9.)

---

# PART B — `python/trading_session.py`

## B.1 Add killzone defaults at module top (after line 24)

```python
# ICT killzones — minute-of-day in NY local time. Cross-confirmed standard windows.
_KZ_DEFAULTS = {
    "ASIAN":        (19 * 60,  3 * 60),   # 19:00 – 03:00 NY (wraps)
    "LONDON_OPEN":  ( 2 * 60,  5 * 60),   # 02:00 – 05:00 NY
    "NY_OPEN":      ( 7 * 60, 10 * 60),   # 07:00 – 10:00 NY (forex)
    "LONDON_CLOSE": (10 * 60, 12 * 60),   # 10:00 – 12:00 NY
}
```

## B.2 New helpers at module level

```python
def _minute_in_window(now_min: int, start_min: int, end_min: int) -> bool:
    if start_min < 0 or end_min < 0:
        return False
    if start_min < end_min:
        return start_min <= now_min < end_min
    return now_min >= start_min or now_min < end_min  # wraps midnight


def _kz_window(name: str) -> tuple[int, int]:
    s_def, e_def = _KZ_DEFAULTS[name]
    s = int(os.environ.get(f"SESSION_KZ_{name}_START_MIN", str(s_def)))
    e = int(os.environ.get(f"SESSION_KZ_{name}_END_MIN",   str(e_def)))
    return s, e
```

## B.3 Add `get_current_killzone_utc` (after `get_trading_session_utc`)

```python
def get_current_killzone_utc(now: datetime | None = None) -> str:
    """
    Return ICT killzone label or '' (none).
    Labels: '' | 'ASIAN_KZ' | 'LONDON_OPEN_KZ' | 'NY_OPEN_KZ' | 'LONDON_CLOSE_KZ'
    Always evaluated in NY local time. Returns '' on weekends or when disabled
    via KILLZONES_ENABLED=0 (default: enabled).
    """
    if os.environ.get("KILLZONES_ENABLED", "1") not in ("1", "true", "True"):
        return ""
    now = now or datetime.now(timezone.utc)
    ny_now = now.astimezone(_NY_TZ)
    if ny_now.weekday() == 5:                       # Saturday
        return ""
    if ny_now.weekday() == 6 and ny_now.hour < 17:  # Sunday pre-open
        return ""
    now_min = ny_now.hour * 60 + ny_now.minute
    s, e = _kz_window("NY_OPEN")
    if _minute_in_window(now_min, s, e): return "NY_OPEN_KZ"
    s, e = _kz_window("LONDON_OPEN")
    if _minute_in_window(now_min, s, e): return "LONDON_OPEN_KZ"
    s, e = _kz_window("LONDON_CLOSE")
    if _minute_in_window(now_min, s, e): return "LONDON_CLOSE_KZ"
    s, e = _kz_window("ASIAN")
    if _minute_in_window(now_min, s, e): return "ASIAN_KZ"
    return ""
```

## B.4 Extend `session_clock_summary()` (line 105)

Append a killzone summary line at the end of the existing return string. Replace
the return statement with:

```python
    kz_a  = _kz_window("ASIAN")
    kz_lo = _kz_window("LONDON_OPEN")
    kz_ny = _kz_window("NY_OPEN")
    kz_lc = _kz_window("LONDON_CLOSE")
    return (
        f"Kill zones: ASIAN(UTC) {a0}–{a1} ({wrap}), "
        f"LONDON(local) {lo0}–{lo1} {_LONDON_TZ.key}, "
        f"LONDON_NY(local NY) {mx0}–{mx1} {_NY_TZ.key}, "
        f"NEW_YORK(local) {ny0}–{ny1} {_NY_TZ.key}, "
        f"SYDNEY(local) {sy0}–{sy1} {_SYDNEY_TZ.key}; "
        f"daily P&L roll {trading_day_reset_hour_utc():02d}:00 UTC. "
        f"ICT killzones (NY min-of-day): "
        f"ASIAN {kz_a[0]}–{kz_a[1]}, "
        f"LONDON_OPEN {kz_lo[0]}–{kz_lo[1]}, "
        f"NY_OPEN {kz_ny[0]}–{kz_ny[1]}, "
        f"LONDON_CLOSE {kz_lc[0]}–{kz_lc[1]}"
    )
```

---

# PART C — `python/bridge.py`

## C.1 Update import (line 27)

```python
from trading_session import (
    get_trading_session_utc,
    sydney_open_alert_info,
    get_current_killzone_utc,
)
```

## C.2 New helper near `_session()` (after line 580)

```python
def _killzone() -> str:
    """Return current ICT killzone label or '' (none)."""
    return get_current_killzone_utc()
```

## C.3 New instance attrs in `__init__` (after line 935)

```python
        self._current_killzone   = ""
        self._killzone_start_ts  = None
```

## C.4 Killzone transition detection (insert after line 2729)

```python
        # ── 3b. KILLZONE TRANSITION DETECTION ──────────────────────
        new_kz = _killzone()
        if new_kz != self._current_killzone:
            self._on_killzone_change(new_kz)
```

## C.5 New method `_on_killzone_change` (after `_on_session_change`, ~line 2895)

```python
    def _on_killzone_change(self, new_killzone: str) -> None:
        """Track ICT killzone transitions. Lighter than _on_session_change:
        no SCRIBE row open/close, just an event log + optional Herald ping."""
        prev = self._current_killzone
        self._current_killzone   = new_killzone
        self._killzone_start_ts  = datetime.now(timezone.utc).isoformat() if new_killzone else None

        log.info(f"BRIDGE: Killzone transition {prev or 'NONE'} → {new_killzone or 'NONE'}")

        self.scribe.log_system_event(
            "KILLZONE_CHANGE",
            triggered_by="BRIDGE",
            session=self._current_session,
            notes=f"{prev or 'NONE'} → {new_killzone or 'NONE'}",
        )

        if new_killzone and os.environ.get("HERALD_KILLZONE_ALERTS", "0") in ("1", "true", "True"):
            self.herald.send(f"⏱ <b>KILLZONE: {new_killzone}</b>")
```

## C.6 Status payload — add killzone fields

In `_write_status` (around line 4839), after the existing `"session":` line:

```python
            "killzone":          self._current_killzone,
            "killzone_start_ts": self._killzone_start_ts,
```

---

# PART D — `python/scribe.py`

## D.1 Schema definition update (`forge_signals`, ~line 119–155)

Append `killzone TEXT,` to the column list (after `regime_confidence REAL,` is fine).

## D.2 Migration call alongside existing ALTERs

Find by `grep "ALTER TABLE forge_signals"` — there's already a similar pattern. Add:

```python
        try:
            with self._conn() as c:
                c.execute("ALTER TABLE forge_signals ADD COLUMN killzone TEXT DEFAULT ''")
                c.execute("CREATE INDEX IF NOT EXISTS idx_forge_sig_killzone ON forge_signals(killzone)")
        except Exception:
            pass
```

## D.3 Update `sync_forge_journal` column list (lines 763–771)

Mirror the existing `has_run_id` detection pattern (lines 760–761):

```python
            src_cols     = {r[1] for r in src.execute("PRAGMA table_info(SIGNALS)").fetchall()}
            has_run_id   = "run_id"   in src_cols
            has_killzone = "killzone" in src_cols

            select_sql = (
                "SELECT id, time, symbol, setup_type, direction, outcome, gate_reason, "
                "price, spread, atr, rsi, adx, bb_upper, bb_lower, bb_mid, "
                "poc_price, vwap_price, fib_50, rsi_divergence, psar_state, "
                "pattern_score, h1_trend, regime_label, regime_confidence, "
                f"adx_trend_regime, high_vol_trend, session, magic"
                + (", run_id"   if has_run_id   else "")
                + (", killzone" if has_killzone else "")
                + f" FROM SIGNALS WHERE synced = 0 ORDER BY id LIMIT {max(1, int(batch_size))}"
            )
```

In the row processing loop (~line 782), extend:

```python
                    base_end = 28
                    run_id   = r[base_end] if has_run_id else 0
                    kz_idx   = base_end + (1 if has_run_id else 0)
                    killzone = r[kz_idx] if has_killzone else ""
```

Add `killzone` to the INSERT column list and VALUES tuple at lines 793–801.

---

# PART E — `python/athena_api.py`

## E.1 Update import (line 25)

```python
from trading_session import (
    get_trading_session_utc,
    trading_day_reset_hour_utc,
    get_current_killzone_utc,
)
```

## E.2 Dashboard endpoint (after line 478)

```python
        "session":           status.get("session", "OFF_HOURS"),
        "session_utc":       get_trading_session_utc(),
        "killzone":          status.get("killzone", ""),
        "killzone_utc":      get_current_killzone_utc(),
        "killzone_start_ts": status.get("killzone_start_ts"),
        "session_id":        status.get("session_id"),
```

---

# PART F — `dashboard/app.js`

## F.1 Replace session badge (lines 723–724)

```jsx
        <span style={{display:'flex',alignItems:'center',gap:6,fontSize:9,color:T.text,fontFamily:T.mono}}>
          <span title="session_utc = UTC kill-zone clock; session = last BRIDGE write">
            {D.session_utc||D.session}</span>
          {(D.killzone_utc||D.killzone) && (
            <span style={{padding:'1px 5px',borderRadius:2,
              background:'rgba(245,158,11,0.12)',
              border:`1px solid ${T.amber||'#F59E0B'}`,
              color:T.amber||'#F59E0B'}}
              title="ICT killzone (NY-anchored). killzone_utc = freshly computed; killzone = last BRIDGE write">
              {D.killzone_utc||D.killzone}
            </span>
          )}
        </span>
```

If `T.amber` isn't defined, grep for `amber` in app.js to find the existing token.

## F.2 Update default `liveData` shape (line ~614)

```javascript
    session:'UNKNOWN', session_utc:'', killzone:'', killzone_utc:'',
    cycle:0,
```

---

# PART G — `config/scalper_config.defaults.json` (config pipeline)

**Reminder from §0.1:** edit the **defaults** file. After your edit, the user runs
`make scalper-env-sync` to regenerate `config/scalper_config.json` and
`MT5/scalper_config.json`. Do not edit those two files directly.

## G.1 Extend the `session_filter` section

Add the new keys inside the existing `session_filter` block. Final shape:

```json
"session_filter": {
  "enabled": true,
  "london_start_utc": 7,
  "london_end_utc": 20,
  "ny_start_utc": 7,
  "ny_end_utc": 20,
  "skip_asian": 1,
  "skip_london": 0,
  "skip_ny": 0,
  "tester_session_filter": 1,
  "tester_allowed_sessions": "LONDON,NY",

  "london_start_min": -1,
  "london_end_min":   -1,
  "ny_start_min":     -1,
  "ny_end_min":       -1,
  "asia_start_min":   -1,
  "asia_end_min":     -1,
  "sessions_ny_anchored": 0,

  "killzones_enabled": 0,
  "killzones_gate_entries": 0,
  "kz_asia_start_min":         1140,
  "kz_asia_end_min":            180,
  "kz_london_open_start_min":   120,
  "kz_london_open_end_min":     300,
  "kz_ny_open_start_min":       420,
  "kz_ny_open_end_min":         600,
  "kz_london_close_start_min":  600,
  "kz_london_close_end_min":    720
}
```

The `-1` sentinels mean "use legacy hour fields", and the killzone flags default off,
so existing behaviour is preserved.

---

# PART H — Schemas + OpenAPI + scripts (data contracts)

## H.1 `schemas/files/status.schema.json`

Add to `properties:` (preserve the alphabetical-ish ordering):

```json
    "killzone":          { "type": "string" },
    "killzone_start_ts": { "type": ["string", "null"] },
```

`additionalProperties: true` is already set, so this is a forward-compatible addition.

## H.2 `schemas/files/market_data.schema.json`

Add to `properties:`:

```json
    "forge_session_state": {
      "type": "object",
      "properties": {
        "label":                 { "type": "string" },
        "killzone":              { "type": "string" },
        "anchor_mode":           { "type": "string", "enum": ["UTC", "NY"] },
        "killzones_enabled":     { "type": "integer", "enum": [0, 1] },
        "killzones_gate_entries":{ "type": "integer", "enum": [0, 1] },
        "trades_this_session":   { "type": "integer" },
        "trades_this_killzone":  { "type": "integer" }
      },
      "additionalProperties": true
    }
```

Also extend the existing `account` block's properties to acknowledge new broker_info
fields read by BRIDGE — but note that broker_info has its own implicit schema, not a
formal file. The new `gmt_offset_sec` and `is_us_dst` from A.5.2 do not need a schema
change here.

## H.3 `schemas/openapi.yaml`

### H.3.1 Live response schema (~line 1002–1005)

Add after `session_id: {}`:

```yaml
        killzone: { type: string }
        killzone_utc: { type: string }
        killzone_start_ts: { type: string, nullable: true }
```

### H.3.2 Health response schema (~line 900)

Add after `session_utc: { type: string }`:

```yaml
        killzone_utc: { type: string }
```

(Only if the `/api/health` endpoint already calls `get_trading_session_utc()`. If
not, skip — adding the field without the implementation would be misleading.)

### H.3.3 ModeReadResponse (~line 1129)

Add after `session: {}`:

```yaml
        killzone: {}
```

## H.4 `schemas/scribe_query_examples.json`

Add three new examples to the `examples` array. Place them near
`forge_signals_recent` to keep related queries grouped:

```json
    {
      "id": "forge_signals_killzone_breakdown",
      "summary": "FORGE signals grouped by killzone (last 7 days)",
      "sql": "SELECT killzone, outcome, COUNT(*) AS n FROM forge_signals WHERE timestamp_utc >= datetime('now', '-7 days') GROUP BY killzone, outcome ORDER BY killzone, n DESC"
    },
    {
      "id": "killzone_change_events_recent",
      "summary": "Recent killzone transitions logged by BRIDGE",
      "sql": "SELECT timestamp, session, notes FROM system_events WHERE event_type = 'KILLZONE_CHANGE' ORDER BY id DESC LIMIT 25"
    },
    {
      "id": "trading_sessions_with_killzone_pnl",
      "summary": "Trading sessions joined with their per-killzone signal count",
      "sql": "SELECT ts.id, ts.session_name, ts.session_date, ts.total_pnl, fs.killzone, COUNT(fs.id) AS signals FROM trading_sessions ts LEFT JOIN forge_signals fs ON fs.timestamp_utc BETWEEN ts.open_time AND COALESCE(ts.close_time, datetime('now')) GROUP BY ts.id, fs.killzone ORDER BY ts.id DESC LIMIT 30"
    }
```

## H.5 `scripts/sync_scalper_config_from_env.py` — OPTIONAL env mapping

If you want users to override killzone settings via `.env` (matching the existing
FORGE_* convention), append to the `MAPPING` dict (after line 109):

```python
    "FORGE_SESSIONS_NY_ANCHORED":     ("session_filter", "sessions_ny_anchored",      "bool01", None, None),
    "FORGE_KILLZONES_ENABLED":        ("session_filter", "killzones_enabled",         "bool01", None, None),
    "FORGE_KILLZONES_GATE_ENTRIES":   ("session_filter", "killzones_gate_entries",    "bool01", None, None),
    "FORGE_KZ_ASIA_START_MIN":        ("session_filter", "kz_asia_start_min",         "int", 0.0, 1439.0),
    "FORGE_KZ_ASIA_END_MIN":          ("session_filter", "kz_asia_end_min",           "int", 0.0, 1440.0),
    "FORGE_KZ_LONDON_OPEN_START_MIN": ("session_filter", "kz_london_open_start_min",  "int", 0.0, 1439.0),
    "FORGE_KZ_LONDON_OPEN_END_MIN":   ("session_filter", "kz_london_open_end_min",    "int", 0.0, 1440.0),
    "FORGE_KZ_NY_OPEN_START_MIN":     ("session_filter", "kz_ny_open_start_min",      "int", 0.0, 1439.0),
    "FORGE_KZ_NY_OPEN_END_MIN":       ("session_filter", "kz_ny_open_end_min",        "int", 0.0, 1440.0),
    "FORGE_KZ_LONDON_CLOSE_START_MIN":("session_filter", "kz_london_close_start_min", "int", 0.0, 1439.0),
    "FORGE_KZ_LONDON_CLOSE_END_MIN":  ("session_filter", "kz_london_close_end_min",   "int", 0.0, 1440.0),
    "FORGE_LONDON_START_MIN":         ("session_filter", "london_start_min",          "int", -1.0, 1439.0),
    "FORGE_LONDON_END_MIN":           ("session_filter", "london_end_min",            "int", -1.0, 1440.0),
    "FORGE_NY_START_MIN":             ("session_filter", "ny_start_min",              "int", -1.0, 1439.0),
    "FORGE_NY_END_MIN":               ("session_filter", "ny_end_min",                "int", -1.0, 1440.0),
    "FORGE_ASIA_START_MIN":           ("session_filter", "asia_start_min",            "int", -1.0, 1439.0),
    "FORGE_ASIA_END_MIN":             ("session_filter", "asia_end_min",              "int", -1.0, 1440.0),
```

The min/max for `*_min` overrides accept `-1` (sentinel) up to 1440. If the script's
`_clamp` rejects `-1`, drop the lower bound (set to `None`) instead.

## H.6 `manifest.json` — no change needed

`scribe_query_examples.json` is not in the manifest's `files` list (verified). The
new schema additions (H.1–H.3) all modify existing files, not new ones.

---

# 2. Acceptance criteria

After all edits:

1. **FORGE.mq5 compiles** in MetaEditor without warnings; `#property version "2.76"`.
2. **`make scalper-env-sync` succeeds** and produces a `scalper_config.json` containing
   the new keys with the documented defaults.
3. **`make forge-compile` succeeds** end-to-end.
4. **All Python files import cleanly** (`python -c "import trading_session, scribe,
   bridge, athena_api"`).
5. **app.js renders** without React console errors.
6. **`KILLZONES_ENABLED=0`** makes `get_current_killzone_utc()` always return `""`
   and bridge produces no killzone log spam; dashboard hides the badge.
7. **`g_sc.killzones_enabled=false`** (FORGE config) makes
   `ComputeCurrentKillzoneLabel()` always return `""`.
8. **`g_sc.sessions_ny_anchored=false`** (default) makes FORGE session detection
   bit-identical to v2.75 except for minute-precision boundaries when `*_min`
   overrides are set.
9. **Existing FORGE configs still load** — JSON containing only legacy session keys
   produces identical behaviour.
10. **Existing SCRIBE databases keep working.** `killzone` column added via
    `ALTER TABLE`, defaults to `''` for old rows. No data loss.
11. **Existing dashboards keep working.** New fields default to `''` in React state.
12. **OpenAPI is internally consistent**: every field added to `LiveResponse` is
    actually returned by `athena_api.py` and validated by tests.
13. **No identifier renamed** beyond what this prompt explicitly authorises.

---

# 3. What NOT to do

- **Do not edit `config/scalper_config.json` or `MT5/scalper_config.json` directly.**
  They are generated; edit `scalper_config.defaults.json` and run
  `make scalper-env-sync`.
- **Do not unify FORGE's session label set with Python's.** Different jobs.
- **Do not rename** `session` to anything new; keep it for backward compatibility.
  Only **add** `killzone`, `killzone_utc`, `killzone_start_ts`.
- **Do not put a nested `session: {…}` block in `market_data.json`.** It would
  collide with `market_data.schema.json` declaring `session: {type: string}`. Use
  `forge_session_state` as instructed in A.5.1.
- **Do not auto-enable `killzones_gate_entries`** — would silently change live
  trading behaviour.
- **Do not auto-enable `HERALD_KILLZONE_ALERTS`** — 4× daily Telegram notifications.
- **Do not invent new SCRIBE tables.** The existing `system_events` captures
  killzone transitions via the new `KILLZONE_CHANGE` event type.
- **Do not touch warmup logic** (`g_forge_init_gmt`) — separate concern.
- **Do not modify the bridge tick loop's existing section ordering** (`── N. … ──`
  comments). Insert the new killzone block after section 3 as shown in C.4.
- **Do not change `JsonHasKey`/`JsonGetDouble` in FORGE.mq5.** They're flat text
  searchers by design; a tree-aware rewrite is out of scope and would be a much
  larger change.

---

# 4. Output format

When done, output one of:

1. A unified diff per file (`diff -u file.orig file > file.patch`), or
2. A list of `(file, line_range, replacement)` tuples mapping cleanly to the
   section numbers in this prompt.

Do **not** output entire files. Keep the patch reviewable. If you skip Tier 2/3/4
(FORGE) or any of Parts B–H, state which and why at the top of the output.

---

# 5. Reference: ICT killzone times (NY local, used as defaults)

| Killzone        | NY Time         | Min-of-day             |
|-----------------|-----------------|------------------------|
| Asian           | 19:00 – 03:00   | 1140 – 180 (wraps)     |
| London Open     | 02:00 – 05:00   | 120  – 300             |
| NY Open (forex) | 07:00 – 10:00   | 420  – 600             |
| London Close    | 10:00 – 12:00   | 600  – 720             |

Asian-killzone caveat: ICT sources cite 20:00–00:00, 20:00–22:00, or 19:00–23:00.
Default uses 19:00–03:00 (broadest defensible). Override via `SESSION_KZ_*` env or
the JSON fields in `scalper_config.defaults.json`.

---

# 6. Addendum (2026-05-09) — FORGE EA quick audit checklist

Short **agent brief** aligned with **`docs/FORGE_SESSION_TIME_PRODUCTION.md`** and **`docs/prompts/FORGE_MONDAY_DI_SESSION_PROMPT.md`**. Use with Part C (FORGE) above; does not replace Tier 2 Python/BRIDGE work.

## Goals

1. **One canonical policy clock** for session rules (FORGE already favors **`TimeGMT()`** for scalper hour buckets; avoid **`TimeLocal()`** for gating).
2. **Tester allowlist** matches EA session tokens (`LONDON` / `NY` / `ASIAN`).
3. **Journal replay** semantics documented where schema is unchanged.

## Issue A — `tester_allowed_sessions` token mismatch (bug)

`ScalperTesterSessionOK()` compares CSV tokens to **`"NY"`**. Config often has **`"LONDON,NEW_YORK"`** — **`NEW_YORK` ≠ `NY`**.

**Fix:** Defaults → **`LONDON,NY`**, or MQL alias **`NEW_YORK` → `NY`** after `StringToUpper`.

## Issue B — Overlapping London / NY windows

If London and NY UTC ranges are identical, **`LONDON` wins** in `if` order; **`NY` label never applies** for those hours. Document or stagger windows.

## Issue C — Hour-only vs minute windows

Native scalper uses **`dt.hour` only**. Sub-hour killzones need an extension (see **`FORGE_SESSION_TIME_PRODUCTION.md` §1).

## Issue D — Journal `time` vs `session`

**`SIGNALS.session`** from **`TimeGMT`** hour; **`SIGNALS.time`** insert uses **`TimeCurrent()`**. Document for analytics (see **`FORGE_MONDAY_DI_SESSION_PROMPT.md` Part A.4).

## Issue E — Daily vs session-string resets

`ResetScalperSessionStateIfNeeded()` resets on UTC day + session label changes; add explicit **`trades_today`** / **`daily_pnl`** only if product requires it, using **`TimeGMT`** date parts consistently.

## Issue F — `TimeLocal` grep audit

Ensure no **gating** uses **`TimeLocal()`**; tester must use simulated **`TimeCurrent()`** / **`TimeGMT()`**.

## Deliverables (FORGE-only pass)

- [ ] Token fix + optional NY window doc note
- [ ] `docs/FORGE_JOURNAL_SQL.md` caveat if `time` column unchanged
- [ ] `CHANGELOG` + `VERSION` if behavior changes