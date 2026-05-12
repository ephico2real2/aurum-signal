# Local-AI Prompt — Cross-Stack Session/Time/Killzone Refactor (v4 — 2026-05-12)

You are working on the **ATHENA / FORGE** trading system. This prompt supersedes v3.
Files in scope (line counts verified 2026-05-12 at HEAD `8b5c5c6`):

| File                              | Lines | Role                                              |
|-----------------------------------|-------|---------------------------------------------------|
| `ea/FORGE.mq5`                    | 8311  | MT5 Expert Advisor (entry/exit, journal)          |
| `python/trading_session.py`       | 125   | Python session-label module                       |
| `python/bridge.py`                | 5100  | Orchestrator: MT5 ↔ SCRIBE ↔ ATHENA               |
| `python/scribe.py`                | 2135  | SQLite DB layer                                   |
| `python/athena_api.py`            | 1999  | Flask API for dashboard                           |
| `dashboard/app.js`                | 2284  | React dashboard (inline Babel)                    |
| `scripts/sync_scalper_config_from_env.py` | 490 | env+defaults → scalper_config.json builder |
| `config/scalper_config.defaults.json` | (data) | **Editable** baseline — do NOT edit `scalper_config.json` |
| `schemas/files/status.schema.json`        | (data) | BRIDGE → ATHENA status contract       |
| `schemas/files/market_data.schema.json`   | (data) | FORGE → BRIDGE market contract        |
| `schemas/openapi.yaml`            | 1545  | HTFTP API contract (ATHENA)                       |
| `schemas/scribe_query_examples.json` | (data) | Documented SCRIBE query examples              |

Out of scope (verified no relevant content): `index.html`, `dep_map.jsx`,
`management_cmd.schema.json`, `aurum_cmd.schema.json`, `forge_command.schema.json`,
`reconciler_last.json`, `manifest.json`.

After your edits:
- `FORGE.mq5` line 58: `#property version "2.xy"` — bump me
- `VERSION` file (repo root): bump patch (e.g. `2.7.35` → `2.7.36`). — bump me
  `sync_scalper_config_from_env.py` `_stamp_version` helper auto-stamps it into
  `scalper_config.json`.
- `athena_api.py` `_SYSTEM_VERSION`: bump patch.

The work is split into **Parts A–H plus a new Tier 0 hotfix**. **Tier 0 + Part A are mandatory.**
B–H are strongly recommended; if you skip any, list which and why at the top of your output.

---

## 0. Critical pipeline facts — read before touching any config file

### 0.1 `scalper_config.json` is GENERATED, not hand-edited

Verified at `sync_scalper_config_from_env.py:21-22, ~330-490`. The flow is:

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
Adding to `config/scalper_config.json` directly will be silently overwritten on next sync.

### 0.2 FORGE's JSON parser is a flat text searcher, not a tree parser

Verified at `FORGE.mq5:~6890-6935` (was at 5410-5447 in v2.75). `JsonHasKey(json, key)` does:

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

Verified at `athena_api.py:~620-660` and `app.js:~990-1020` (literal:
`{D.session_utc||D.session}`). Convention:

- `<field>` = persisted (last value BRIDGE wrote to status.json)
- `<field>_utc` = freshly computed by a `trading_session.py` function

New killzone fields **must** follow this: `killzone` (persisted), `killzone_utc` (fresh).

### 0.5 🚨 CRITICAL — `TimeGMT()` is BROKEN in the MT5 Strategy Tester

**This invalidates v3's Approach A and is the reason this prompt is v4.**

Per [MQL5 community forum (verified 2026-05-12)](https://www.mql5.com/en/forum/427917)
and [MQL5 docs](https://www.mql5.com/en/docs/dateandtime/timegmt):

> "During testing in the strategy tester, `TimeGMT()` is always equal to `TimeTradeServer()`
> simulated server time. `TimeLocal()` is always equal to `TimeTradeServer()`. The server
> time is always equal to `TimeGMT()`. **All four functions return the same value during
> testing**."

For a typical broker (Vantage = GMT+2 winter / GMT+3 summer), this means a naive
`TimeGMT() + (-5h or -4h)` would put "NY time" **5-7 hours off** during backtest.

**Therefore the v3 Approach A (`GetNYTimeNow() = TimeGMT() + dst_offset`) is wrong for
FORGE because we live in the tester.** Approach B (manual broker GMT offset inputs + EU-DST
detection to switch between them) is the only correct implementation that works
**identically in live and tester**. This prompt v4 ships Approach B as the canonical
implementation. Approach A is documented in `docs/research/ICT_KILLZONES.md §5` as a
live-only alternative (or via `amrali`'s TimeGMT library hook).

---

## 1. Naming conventions — match what each file uses

- **MQL5:** `PascalCase` functions, `g_sc.<snake>` config struct fields, globals
  `g_*` / `g_scalper_*` / `g_forge_*`, log-throttle globals
  `g_scalper_last_<topic>_log_bar`, log prefixes `FORGE: …` / `FORGE SCALPER: …` /
  `FORGE TESTER: …` / `FORGE JOURNAL: …`.
- **Python:** snake_case; module constants `UPPER_SNAKE`; env vars `SESSION_*` /
  `AEGIS_*` / `BRIDGE_*` / `FORGE_*` / `KILLZONES_*`.
- **JS/React:** camelCase locals; `T.<color>` from theme; `D.<field>` for live data.
- **JSON keys:** snake_case, e.g. `kz_ny_open_start_min`.
- **DB columns:** snake_case; additive migrations via `ALTER TABLE … ADD COLUMN`.
- **Scalper config sections:** new killzone keys go in **`session_filter`** (not a new section).

---

# 🔥 TIER 0 — Mandatory hotfix (ship FIRST, regardless of A-H scope)

**Single-line fix that unblocks every NY trade in tester.** Currently `scalper_config.defaults.json`
has `"tester_allowed_sessions": "LONDON,NEW_YORK"` but `ScalperTesterSessionOK()` labels
the session as `"NY"`. After `StringToUpper`, `"NEW_YORK" != "NY"` → **NY trades silently
rejected by the tester filter today**.

## T0.1 Fix `scalper_config.defaults.json`

```diff
- "tester_allowed_sessions": "LONDON,NEW_YORK"
+ "tester_allowed_sessions": "LONDON,NY"
```

## T0.2 Defensive alias in `ScalperTesterSessionOK` (current line 4036)

After `StringToUpper(parts[i]);` add a synonym normalization so future operators don't
hit this trap again:

```cpp
      StringTrimLeft(parts[i]); StringTrimRight(parts[i]); StringToUpper(parts[i]);
      if(parts[i] == "NEW_YORK") parts[i] = "NY";          // NEW: backward-compat alias
      if(parts[i] == "ASIA")     parts[i] = "ASIAN";       // NEW: backward-compat alias
      if(parts[i] == current_session) return true;
```

## T0.3 Run `make scalper-env-sync && make forge-compile`

Verify in tester that NY-window trades fire after the fix.

---

# PART A — FORGE.mq5 (mandatory)

## A.1 Reference: existing code anchors (verified 2026-05-12, FORGE.mq5 at 8311 lines)

| What                                                  | v3 line  | **v4 line (current)** |
|-------------------------------------------------------|----------|-----------------------|
| `#property version`                                   | 58       | **58** (unchanged)    |
| Module globals (`g_scalper_*` block end)              | 110-145  | **155-220**           |
| `struct ScalperConfig` (start)                        | 196      | **250**               |
| `struct ScalperConfig` Session block                  | 196-206  | (find `// Session` comment near 270 — verify by signature) |
| `InitScalperConfig`                                   | 2045     | **2706**              |
| Session field defaults inside InitScalperConfig       | 2045-2051| (immediately after `InitScalperConfig` opening) |
| `ReadScalperConfig`                                   | 2334     | **3051**              |
| Session JSON readers in ReadScalperConfig             | 2334-2358| (search for `london_start_utc` reader)         |
| `ResetScalperSessionStateIfNeeded`                    | 2806     | **3982**              |
| `ScalperSessionOK`                                    | 2847     | **4023**              |
| `ScalperTesterSessionOK`                              | 2860     | **4036**              |
| `ScalperDirectionCooldownOK` (broken throttle)        | 2942     | (grep for function name — has moved) |
| Journal SIGNALS schema (CREATE TABLE)                 | ~3370    | (grep `CREATE TABLE IF NOT EXISTS SIGNALS`)    |
| Journal indices & migrations                          | ~3442    | (grep `ALTER TABLE SIGNALS`)                   |
| `JournalRecordSignal()` signature                     | 3578-3583| **4881**              |
| Session-blocked check in entry path                   | 3997     | **5599-5601**         |
| `open_groups` gate                                    | 4047     | (grep `gate=open_groups`)                       |
| `session_trade_cap` gate                              | 4052     | (grep `gate=session_trade_cap`)                |
| `cooldown` gate (correctly throttled — reference)     | 4058     | (grep `g_scalper_last_cooldown_log_bar`)       |
| `WriteMarketData`                                     | 1749     | **2442**              |
| `WriteBrokerInfo`                                     | 1963     | **2666**              |
| `JsonHasKey`, `JsonGetDouble`, `JsonGetString`        | 5410     | (grep `bool JsonHasKey`)                       |

**Rule for implementer**: whenever a v3 line number is given, **grep for the function/marker
signature instead** to find the current location. Code has grown +52% since v3 was written;
exact line offsets will drift further between this prompt and execution.

## A.2 Bugs being fixed in FORGE.mq5

1. **Hour-only precision** — session checks use `dt.hour >= start && dt.hour < end`. No minute resolution.
2. **No DST handling** — windows stored as UTC hours; broker-NY offset shifts twice
   a year between +7h and +6h.
3. **ASIA is a fallback, not a window** — anything not LONDON/NY becomes ASIAN.
4. **Default config is degenerate AND overlapping** — `london_start_utc=7, london_end_utc=20`
   AND `ny_start_utc=7, ny_end_utc=20`. **Identical 13-hour overlap**; LONDON wins for every
   hour in `if/else-if` order, so the NY label never fires in production. (Issue B from v3
   addendum, now elevated to top-level bug.)
5. **No killzone detection.**
6. **Day rollover uses UTC midnight** regardless of anchor.
7. **`ScalperDirectionCooldownOK` log throttle is broken** — uses
   `g_scalper_last_sesswarn_log_bar` (wrong global) and never updates it.
8. **`open_groups` and `session_trade_cap` gates have no throttle** — log + insert SIGNALS rows every tick while at the cap.
9. **🆕 `TimeGMT()` returns broker time in tester** (per §0.5). Approach A would silently miscompute NY time by 5-7 hours. **Mitigation**: use Approach B (manual broker GMT offset inputs) below.

## A.3 Tier 1 — MANDATORY: Session/Time/Killzone Refactor

### A.3.1 New struct fields (append to `ScalperConfig` Session block, current ~270)

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

   // 🆕 Broker GMT offset for Approach B (manual offset — works in tester)
   int    broker_gmt_offset_winter;   // typical Vantage: 2 (broker = UTC+2 in EU winter)
   int    broker_gmt_offset_summer;   // typical Vantage: 3 (broker = UTC+3 in EU summer)

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

### A.3.2 New globals (place at end of `g_scalper_*` block, current ~220)

```cpp
string   g_scalper_last_killzone_label = "";
datetime g_scalper_killzone_start_time = 0;
int      g_scalper_killzone_trades    = 0;
```

### A.3.3 New helper functions — **Approach B (manual broker offset)** [REPLACES v3 Approach A]

Insert above `ResetScalperSessionStateIfNeeded` (current line 3982).

```cpp
//+------------------------------------------------------------------+
//| EU DST detection — Last Sunday of March → Last Sunday of October |
//| Used to know which broker GMT offset to apply.                   |
//+------------------------------------------------------------------+
int LastSundayOfMonth(int year, int month) {
   MqlDateTime d;
   d.year = year; d.mon = month; d.day = 28;
   d.hour = 0; d.min = 0; d.sec = 0;
   datetime t = StructToTime(d);
   TimeToStruct(t, d);
   int last_day = 28;
   for(int i = 28; i <= 31; i++) {
      d.day = i;
      t = StructToTime(d);
      MqlDateTime check; TimeToStruct(t, check);
      if(check.mon == month) last_day = i;
   }
   d.day = last_day;
   t = StructToTime(d);
   TimeToStruct(t, d);
   return last_day - d.day_of_week;   // walk back to Sunday
}

bool IsEU_DST(datetime broker_time) {
   MqlDateTime d; TimeToStruct(broker_time, d);
   if(d.mon < 3 || d.mon > 10) return false;
   if(d.mon > 3 && d.mon < 10) return true;
   if(d.mon == 3) {
      int last_sun = LastSundayOfMonth(d.year, 3);
      if(d.day < last_sun) return false;
      if(d.day > last_sun) return true;
      return d.hour >= 3;   // EU DST flips at 01:00 UTC = 03:00 broker-winter
   }
   int last_sun = LastSundayOfMonth(d.year, 10);
   if(d.day < last_sun) return true;
   if(d.day > last_sun) return false;
   return d.hour < 4;       // EU DST ends at 01:00 UTC = 04:00 broker-summer
}

//+------------------------------------------------------------------+
//| US DST detection — Second Sunday of March → First Sunday of Nov  |
//| Input MUST be true UTC (after subtracting broker offset).        |
//+------------------------------------------------------------------+
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
      return d.hour >= 7;     // 02:00 EST → 07:00 UTC
   }
   int first_sun = FirstSundayOfMonth(d.year, 11);
   if(d.day < first_sun) return true;
   if(d.day > first_sun) return false;
   return d.hour < 6;          // 02:00 EDT → 06:00 UTC
}

//+------------------------------------------------------------------+
//| Convert broker-server time → NY-local time using manual offsets. |
//| Works in BOTH live and Strategy Tester (TimeGMT is unreliable    |
//| in tester per MQL5 docs — see docs/research/ICT_KILLZONES.md §5).|
//+------------------------------------------------------------------+
datetime BrokerToNY(datetime broker) {
   int broker_off = IsEU_DST(broker)
                       ? g_sc.broker_gmt_offset_summer
                       : g_sc.broker_gmt_offset_winter;
   datetime utc = broker - broker_off * 3600;
   int ny_off   = IsUS_DST(utc) ? -4 : -5;
   return utc + ny_off * 3600;
}

datetime GetNYTimeNow() {
   // In tester, TimeCurrent() and TimeGMT() both return broker time. Use TimeCurrent
   // for consistency with how the EA already times all bar lookups.
   return BrokerToNY(TimeCurrent());
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
   // NY checked FIRST so when ranges overlap (legacy default), NY wins for the
   // overlap window instead of LONDON always winning (Bug #4 fix).
   if(MinuteInWindow(now_min, ns, ne)) return "NY";
   if(MinuteInWindow(now_min, ls, le)) return "LONDON";
   if(asn >= 0 && ae >= 0) {
      if(MinuteInWindow(now_min, asn, ae)) return "ASIAN";
      return "OFF";
   }
   return "ASIAN";    // legacy fallback when asia_*_min < 0
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

int ForgeBrokerGMTOffsetSec() {
   // For diagnostics. In live, TimeTradeServer() - TimeGMT() is correct.
   // In tester both return the same value, so we use the configured offset.
   if(MQLInfoInteger(MQL_TESTER) != 0) {
      datetime now = TimeCurrent();
      int hr = IsEU_DST(now) ? g_sc.broker_gmt_offset_summer : g_sc.broker_gmt_offset_winter;
      return hr * 3600;
   }
   return (int)(TimeTradeServer() - TimeGMT());
}
```

### A.3.4 Update `InitScalperConfig` (insert defaults after existing session defaults, current ~2750)

```cpp
   g_sc.london_start_min = -1;  g_sc.london_end_min = -1;
   g_sc.ny_start_min     = -1;  g_sc.ny_end_min     = -1;
   g_sc.asia_start_min   = -1;  g_sc.asia_end_min   = -1;
   g_sc.sessions_ny_anchored     = false;

   // Approach B broker offsets — defaults for Vantage / Cyprus brokers.
   // Verify your broker by running `make forge-broker-offset-check` after the first run.
   g_sc.broker_gmt_offset_winter = 2;
   g_sc.broker_gmt_offset_summer = 3;

   g_sc.killzones_enabled        = false;
   g_sc.killzones_gate_entries   = false;
   g_sc.kz_asia_start_min        = 19*60;   // 19:00 NY (wraps to 03:00)
   g_sc.kz_asia_end_min          =  3*60;
   g_sc.kz_london_open_start_min =  2*60;
   g_sc.kz_london_open_end_min   =  5*60;
   g_sc.kz_ny_open_start_min     =  7*60;
   g_sc.kz_ny_open_end_min       = 10*60;
   g_sc.kz_london_close_start_min= 10*60;
   g_sc.kz_london_close_end_min  = 12*60;
```

### A.3.5 Update `ReadScalperConfig` (current ~3051; insert after existing session readers)

Keep existing readers untouched. Add additively:

```cpp
   if(JsonHasKey(content, "london_start_min")) { v=JsonGetDouble(content,"london_start_min"); if(v>=-1&&v<=1439) g_sc.london_start_min=(int)v; }
   if(JsonHasKey(content, "london_end_min"))   { v=JsonGetDouble(content,"london_end_min");   if(v>=-1&&v<=1440) g_sc.london_end_min  =(int)v; }
   if(JsonHasKey(content, "ny_start_min"))     { v=JsonGetDouble(content,"ny_start_min");     if(v>=-1&&v<=1439) g_sc.ny_start_min    =(int)v; }
   if(JsonHasKey(content, "ny_end_min"))       { v=JsonGetDouble(content,"ny_end_min");       if(v>=-1&&v<=1440) g_sc.ny_end_min      =(int)v; }
   if(JsonHasKey(content, "asia_start_min"))   { v=JsonGetDouble(content,"asia_start_min");   if(v>=-1&&v<=1439) g_sc.asia_start_min  =(int)v; }
   if(JsonHasKey(content, "asia_end_min"))     { v=JsonGetDouble(content,"asia_end_min");     if(v>=-1&&v<=1440) g_sc.asia_end_min    =(int)v; }
   if(JsonHasKey(content, "sessions_ny_anchored")) { v=JsonGetDouble(content,"sessions_ny_anchored"); g_sc.sessions_ny_anchored=(v>=0.5); }
   if(JsonHasKey(content, "broker_gmt_offset_winter")) { v=JsonGetDouble(content,"broker_gmt_offset_winter"); if(v>=-12&&v<=14) g_sc.broker_gmt_offset_winter=(int)v; }
   if(JsonHasKey(content, "broker_gmt_offset_summer")) { v=JsonGetDouble(content,"broker_gmt_offset_summer"); if(v>=-12&&v<=14) g_sc.broker_gmt_offset_summer=(int)v; }
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

### A.3.6 Replace `ResetScalperSessionStateIfNeeded` body (current line 3982)

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

### A.3.7 Replace `ScalperSessionOK` (current line 4023)

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

### A.3.8 Replace `ScalperTesterSessionOK` body (current line 4036)

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
      if(parts[i] == "NEW_YORK") parts[i] = "NY";          // T0.2 backward-compat alias
      if(parts[i] == "ASIA")     parts[i] = "ASIAN";       // T0.2 backward-compat alias
      if(parts[i] == current_session) return true;
   }
   return false;
}
```

### A.3.9 Update `JournalRecordSignal` session block (current line 4881; find the session var assignment)

Replace the existing TimeGMT-hour-derived session line(s) with:

```cpp
   string session  = ComputeCurrentSessionLabel();
   string killzone = ComputeCurrentKillzoneLabel();
```

In the SQL column list add `killzone` between `session` and `magic`. In the VALUES list
add `+ "'" + killzone + "', "` in the matching slot. Requires the schema migration in A.6.

### A.3.10 Update session_off log (find `gate=session_off` print)

```cpp
         PrintFormat("FORGE SCALPER: skip gate=session_off anchor=%s %02d:%02d (no trades)",
                     g_sc.sessions_ny_anchored ? "NY" : "UTC", dt.hour, dt.min);
```

## A.4 Tier 2 — Log throttle bug fixes

Add three new globals near the existing `g_scalper_last_*_log_bar` block (current ~155-220):

```cpp
datetime g_scalper_last_dircool_log_bar = 0;
datetime g_scalper_last_opengroups_log_bar = 0;
datetime g_scalper_last_sesscap_log_bar = 0;
```

**`ScalperDirectionCooldownOK`** (grep for function name):

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

**`open_groups` gate** (grep `gate=open_groups`): mirror the `cooldown` pattern using `g_scalper_last_opengroups_log_bar`.

**`session_trade_cap` gate** (grep `gate=session_trade_cap`): same with `g_scalper_last_sesscap_log_bar`.

## A.5 Tier 3 — JSON output visibility

### A.5.1 `WriteMarketData` (current line 2442)

**IMPORTANT NAMING:** The schema `market_data.schema.json` already declares
`session: { type: string }` at the top level. Adding a nested `session: {…}` would
break the schema. Use `forge_session_state` instead — matches the existing
`forge_config`, `forge_version` prefix pattern.

After the `forge_config` block (search for `"forge_config"` literal in WriteMarketData), add:

```cpp
   j += "\"forge_session_state\":{";
   j += "\"label\":\""           + JsonEscape(ComputeCurrentSessionLabel())  + "\",";
   j += "\"killzone\":\""        + JsonEscape(ComputeCurrentKillzoneLabel()) + "\",";
   j += "\"anchor_mode\":\""     + (g_sc.sessions_ny_anchored ? "NY" : "UTC") + "\",";
   j += "\"killzones_enabled\":" + IntegerToString(g_sc.killzones_enabled ? 1 : 0) + ",";
   j += "\"killzones_gate_entries\":" + IntegerToString(g_sc.killzones_gate_entries ? 1 : 0) + ",";
   j += "\"broker_gmt_offset_winter\":" + IntegerToString(g_sc.broker_gmt_offset_winter) + ",";
   j += "\"broker_gmt_offset_summer\":" + IntegerToString(g_sc.broker_gmt_offset_summer) + ",";
   j += "\"trades_this_session\":"  + IntegerToString(g_scalper_session_trades)  + ",";
   j += "\"trades_this_killzone\":" + IntegerToString(g_scalper_killzone_trades);
   j += "},";
```

### A.5.2 `WriteBrokerInfo` (current line 2666)

After `gmt_time` (search for `"gmt_time"` literal):

```cpp
   j += "\"gmt_offset_sec\":" + IntegerToString(ForgeBrokerGMTOffsetSec()) + ",";
   j += "\"is_us_dst\":"      + IntegerToString(IsUS_DST(TimeGMT()) ? 1 : 0) + ",";
   j += "\"is_eu_dst\":"      + IntegerToString(IsEU_DST(TimeCurrent()) ? 1 : 0) + ",";
   j += "\"broker_gmt_offset_winter\":" + IntegerToString(g_sc.broker_gmt_offset_winter) + ",";
   j += "\"broker_gmt_offset_summer\":" + IntegerToString(g_sc.broker_gmt_offset_summer) + ",";
```

## A.6 Tier 4 — Journal SIGNALS schema migration

In the existing journal migration block (grep `ALTER TABLE SIGNALS`):

```cpp
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN killzone TEXT DEFAULT '';");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_killzone ON SIGNALS(killzone);");
```

Also add `killzone` to the `CREATE TABLE IF NOT EXISTS SIGNALS` schema definition so
fresh DBs are created with the column.

## A.7 Diagnostic helper — operator verification at OnInit

Add to `OnInit()` after `WriteBrokerInfo()` (current line 870-893 area):

```cpp
   PrintFormat("FORGE TIME CHECK: TimeCurrent=%s TimeGMT=%s TimeTradeServer=%s",
               TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
               TimeToString(TimeGMT(),     TIME_DATE|TIME_SECONDS),
               TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS));
   PrintFormat("FORGE TIME CHECK: BrokerToNY=%s (EU_DST=%d offset=%dh)",
               TimeToString(BrokerToNY(TimeCurrent()), TIME_DATE|TIME_SECONDS),
               IsEU_DST(TimeCurrent()) ? 1 : 0,
               IsEU_DST(TimeCurrent()) ? g_sc.broker_gmt_offset_summer : g_sc.broker_gmt_offset_winter);
```

In tester, TimeCurrent == TimeGMT == TimeTradeServer. In live, TimeGMT should be ~2-3h
before TimeCurrent. Use this output to verify the broker offset is correct before
shipping killzone gating.

---

# PART B — `python/trading_session.py` (file unchanged, 125 lines)

Python uses `zoneinfo.ZoneInfo("America/New_York")` which is OS-DST-aware — **no
Approach-B-equivalent is needed on the Python side**. Killzone logic flows from real UTC
through OS-tz to NY local time correctly without any manual offset.

## B.1 Add killzone defaults at module top (after line 24, where `_NY_TZ` is defined)

```python
# ICT killzones — minute-of-day in NY local time. Cross-confirmed standard windows.
# See docs/research/ICT_KILLZONES.md for source citations.
_KZ_DEFAULTS = {
    "ASIAN":        (19 * 60,  3 * 60),   # 19:00 – 03:00 NY (wraps)
    "LONDON_OPEN":  ( 2 * 60,  5 * 60),   # 02:00 – 05:00 NY
    "NY_OPEN":      ( 7 * 60, 10 * 60),   # 07:00 – 10:00 NY (forex)
    "LONDON_CLOSE": (10 * 60, 12 * 60),   # 10:00 – 12:00 NY
}
```

## B.2 New helpers at module level (after `get_trading_session_utc`, current line 36)

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

## B.3 Add `get_current_killzone_utc` (insert before `trading_day_reset_hour_utc`, current line 70)

```python
def get_current_killzone_utc(now: datetime | None = None) -> str:
    """
    Return ICT killzone label or '' (none).
    Labels: '' | 'ASIAN_KZ' | 'LONDON_OPEN_KZ' | 'NY_OPEN_KZ' | 'LONDON_CLOSE_KZ'
    Always evaluated in NY local time via zoneinfo (OS-DST-aware).
    Returns '' on weekends or when disabled via KILLZONES_ENABLED=0.
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

## B.4 Extend `session_clock_summary()` (current line 105)

Append a killzone summary block at the end of the existing return string per v3 §B.4
(structure unchanged, no line-number shift here).

---

# PART C — `python/bridge.py` (5100 lines)

## C.1 Update import (current line 27 area; grep `from trading_session import`)

```python
from trading_session import (
    get_trading_session_utc,
    sydney_open_alert_info,
    get_current_killzone_utc,
)
```

## C.2 New helper near `_session()` (current line 578)

```python
def _killzone() -> str:
    """Return current ICT killzone label or '' (none)."""
    return get_current_killzone_utc()
```

## C.3 New instance attrs in `__init__` (after `self._current_session = "OFF_HOURS"` at current line 970)

```python
        self._current_killzone   = ""
        self._killzone_start_ts  = None
```

## C.4 Killzone transition detection — insert after the section-3 session-change block

Grep for the existing `_on_session_change` call in the tick loop. **Insert immediately
after it** (one tick loop iteration covers both):

```python
        # ── 3b. KILLZONE TRANSITION DETECTION ──────────────────────
        new_kz = _killzone()
        if new_kz != self._current_killzone:
            self._on_killzone_change(new_kz)
```

## C.5 New method `_on_killzone_change` (after `_on_session_change`, current line 3026)

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

In `_write_status` (current line 5016), after the existing `"session":` line:

```python
            "killzone":          self._current_killzone,
            "killzone_start_ts": self._killzone_start_ts,
```

---

# PART D — `python/scribe.py` (2135 lines)

## D.1 Schema definition update (`forge_signals`, current line 119 module-level + line 522 in `__init__`)

Append `killzone TEXT,` to BOTH column lists (module top declarative + the in-init
`CREATE TABLE IF NOT EXISTS forge_signals`). Place after `regime_confidence REAL,`.

## D.2 Migration call alongside existing ALTERs

The existing ALTER pattern is at line ~542-551. Add:

```python
        if "killzone" not in fs_cols:
            conn.execute("ALTER TABLE forge_signals ADD COLUMN killzone TEXT DEFAULT ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fs_killzone ON forge_signals(killzone)")
            log.info("SCRIBE migration: added killzone to forge_signals")
```

(Use the existing `if "<col>" not in fs_cols:` pattern — see line 541 for the reference.)

## D.3 Update `sync_forge_journal` column list (grep `def sync_forge_journal`)

Mirror the existing `has_run_id` detection pattern. Add `has_killzone` check and include
`killzone` in the SELECT + INSERT column lists per v3 §D.3 (logic unchanged).

---

# PART E — `python/athena_api.py` (1999 lines)

## E.1 Update import (current line 25 area; grep `from trading_session import`)

```python
from trading_session import (
    get_trading_session_utc,
    trading_day_reset_hour_utc,
    get_current_killzone_utc,
)
```

## E.2 Dashboard endpoint (grep for the `"session_utc"` literal — current ~line 620)

```python
        "session":           status.get("session", "OFF_HOURS"),
        "session_utc":       get_trading_session_utc(),
        "killzone":          status.get("killzone", ""),
        "killzone_utc":      get_current_killzone_utc(),
        "killzone_start_ts": status.get("killzone_start_ts"),
        "session_id":        status.get("session_id"),
```

---

# PART F — `dashboard/app.js` (2284 lines)

## F.1 Replace session badge (grep `D.session_utc||D.session` — current ~line 990)

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

## F.2 Update default `liveData` shape (grep `session:'UNKNOWN'` — current ~line 870)

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
  "london_end_utc": 12,
  "ny_start_utc": 12,
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

  "broker_gmt_offset_winter": 2,
  "broker_gmt_offset_summer": 3,

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

**Two changes from v3**:
1. `tester_allowed_sessions` → `"LONDON,NY"` (T0.1 hotfix).
2. London/NY UTC windows **de-overlapped**: London 7-12 UTC (morning EU), NY 12-20 UTC
   (afternoon US). Restores the NY label which was permanently masked by London under v3.
3. Added `broker_gmt_offset_winter` / `broker_gmt_offset_summer` for Approach B.

The `-1` sentinels mean "use legacy hour fields", and the killzone flags default off,
so existing behaviour is preserved on first ship.

---

# PART H — Schemas + OpenAPI + scripts (data contracts)

## H.1 `schemas/files/status.schema.json`

Add to `properties:` (preserve the alphabetical-ish ordering):

```json
    "killzone":          { "type": "string" },
    "killzone_start_ts": { "type": ["string", "null"] },
```

## H.2 `schemas/files/market_data.schema.json`

Add to `properties:`:

```json
    "forge_session_state": {
      "type": "object",
      "properties": {
        "label":                    { "type": "string" },
        "killzone":                 { "type": "string" },
        "anchor_mode":              { "type": "string", "enum": ["UTC", "NY"] },
        "killzones_enabled":        { "type": "integer", "enum": [0, 1] },
        "killzones_gate_entries":   { "type": "integer", "enum": [0, 1] },
        "broker_gmt_offset_winter": { "type": "integer" },
        "broker_gmt_offset_summer": { "type": "integer" },
        "trades_this_session":      { "type": "integer" },
        "trades_this_killzone":     { "type": "integer" }
      },
      "additionalProperties": true
    }
```

## H.3 `schemas/openapi.yaml` (1545 lines)

Anchor lines in v3 (1002, 900, 1129) are off by ~360. **Grep for the field names instead:**

### H.3.1 Live response schema (grep `session_id: \{\}` or `LiveResponse:`)

Add after `session_id: {}`:

```yaml
        killzone: { type: string }
        killzone_utc: { type: string }
        killzone_start_ts: { type: string, nullable: true }
```

### H.3.2 Health response schema (grep `session_utc: \{ type: string \}` inside `Health`)

Add after that line:

```yaml
        killzone_utc: { type: string }
```

(Only if `/api/health` calls `get_trading_session_utc()`. Otherwise skip.)

### H.3.3 ModeReadResponse (grep `ModeReadResponse:`)

Add after `session: {}`:

```yaml
        killzone: {}
```

## H.4 `schemas/scribe_query_examples.json` — same as v3 §H.4 (three new examples).

## H.5 `scripts/sync_scalper_config_from_env.py` — env mapping (current ~line 109)

Append to the `MAPPING` dict. Includes the new broker GMT offset env vars:

```python
    "FORGE_SESSIONS_NY_ANCHORED":     ("session_filter", "sessions_ny_anchored",      "bool01", None, None),
    "FORGE_BROKER_GMT_OFFSET_WINTER": ("session_filter", "broker_gmt_offset_winter",  "int", -12.0, 14.0),
    "FORGE_BROKER_GMT_OFFSET_SUMMER": ("session_filter", "broker_gmt_offset_summer",  "int", -12.0, 14.0),
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

If the script's `_clamp` rejects negative bounds, drop the lower bound for `*_min` fields (set to `None`).

---

# 2. Acceptance criteria

After all edits:

1. **FORGE.mq5 compiles** in MetaEditor without warnings; `#property version "2.7.36"`.
2. **`make scalper-env-sync` succeeds** and produces a `scalper_config.json` containing
   the new keys with the documented defaults.
3. **`make forge-compile` succeeds** end-to-end.
4. **All Python files import cleanly** (`python -c "import trading_session, scribe, bridge, athena_api"`).
5. **app.js renders** without React console errors.
6. **`KILLZONES_ENABLED=0`** makes `get_current_killzone_utc()` always return `""`.
7. **`g_sc.killzones_enabled=false`** (FORGE config) makes `ComputeCurrentKillzoneLabel()` always return `""`.
8. **`g_sc.sessions_ny_anchored=false`** (default) makes FORGE session detection
   bit-identical to v2.7.35 **except** for the de-overlapped London/NY windows in G.1
   (now London 7-12 UTC, NY 12-20 UTC) — call this out in the v2.7.36 release notes.
9. **🆕 `BrokerToNY(TimeCurrent())` returns true NY time in tester** — verify via the A.7
   diagnostic print on a known timestamp (e.g. when broker-server reports 14:00 UTC+2 in
   winter, BrokerToNY should report 07:00 NY).
10. **Existing FORGE configs still load** — JSON containing only legacy session keys produces correct behaviour (with the de-overlapped windows note).
11. **Existing SCRIBE databases keep working.** `killzone` column added via `ALTER TABLE`, defaults to `''` for old rows.
12. **Existing dashboards keep working.** New fields default to `''` in React state.
13. **OpenAPI is internally consistent**: every field added to `LiveResponse` is actually returned by `athena_api.py`.
14. **No identifier renamed** beyond what this prompt explicitly authorises.
15. **🆕 T0.1 hotfix** — tester runs containing the NY window report `current_session = "NY"`, not `"ASIAN"` fallback.

---

# 3. What NOT to do

- **Do not edit `config/scalper_config.json` or `MT5/scalper_config.json` directly.**
- **Do not unify FORGE's session label set with Python's.** Different jobs.
- **Do not rename** `session` to anything new; only **add** `killzone`, `killzone_utc`, `killzone_start_ts`.
- **Do not put a nested `session: {…}` block in `market_data.json`.** Use `forge_session_state`.
- **Do not auto-enable `killzones_gate_entries`** — would silently change live trading behaviour.
- **Do not auto-enable `HERALD_KILLZONE_ALERTS`** — 4× daily Telegram notifications.
- **Do not invent new SCRIBE tables.** Existing `system_events` captures killzone transitions.
- **Do not touch warmup logic** (`g_forge_init_gmt`) — separate concern.
- **Do not change `JsonHasKey`/`JsonGetDouble`.** Flat text searchers by design.
- **🆕 Do not ship the v3 `TimeGMT()`-based GetNYTimeNow.** It's broken in tester per §0.5.
- **🆕 Do not rely on `TimeGMT()` in any new code path that needs true UTC** unless
  guarded by `MQLInfoInteger(MQL_TESTER) == 0`. Use `BrokerToNY(TimeCurrent())` instead.

---

# 4. Output format

When done, output one of:

1. A unified diff per file (`diff -u file.orig file > file.patch`), or
2. A list of `(file, line_range, replacement)` tuples mapping cleanly to the section
   numbers in this prompt.

Do **not** output entire files. Keep the patch reviewable. If you skip Tier 2/3/4
(FORGE) or any of Parts B-H, state which and why at the top of the output.

---

# 5. Reference: ICT killzone times (NY local, used as defaults)

| Killzone        | NY Time         | Min-of-day             |
|-----------------|-----------------|------------------------|
| Asian           | 19:00 – 03:00   | 1140 – 180 (wraps)     |
| London Open     | 02:00 – 05:00   | 120  – 300             |
| NY Open (forex) | 07:00 – 10:00   | 420  – 600             |
| London Close    | 10:00 – 12:00   | 600  – 720             |

Source of truth + ICT canonical citations: `docs/research/ICT_KILLZONES.md` (13 sources,
gold-prime-window finding: London-NY overlap = 60-70% of XAUUSD daily range per EBC
Financial + TradingView ProjectSyndicate 2025).

---

# 6. Addendum — FORGE EA quick audit checklist (carry-over from v3)

The v3 addendum (Issues A-F) is still relevant. Status update:

| Issue | v3 finding | v4 status |
|---|---|---|
| A — `NEW_YORK` ≠ `NY` token mismatch | bug | **Promoted to Tier 0** (§T0.1/T0.2) — ship immediately |
| B — Overlapping London/NY UTC windows | bug | **Promoted to Bug #4 in §A.2** — fixed in G.1 (London 7-12, NY 12-20) |
| C — Hour-only vs minute windows | gap | Fixed in §A.3.1 (`*_min` fields) |
| D — Journal `time` vs `session` consistency | doc-only | Still doc-only — add to `docs/FORGE_JOURNAL_SQL.md` after this lands |
| E — Daily vs session-string resets | minor | Addressed in §A.3.6 (anchor-based today + explicit current_session) |
| F — `TimeLocal()` grep audit | verify | Verified — only safe usages of `TimeCurrent`/`TimeGMT`. Add §A.7 diagnostic to make the audit visible per run. |

---

# 7. Changelog (this prompt)

| Date       | Version | Change |
|------------|---------|--------|
| 2026-05-09 | v1 | Initial draft (single-file FORGE focus) |
| 2026-05-10 | v2 | Cross-stack (Python + dashboard added) |
| 2026-05-11 | v3 | Approach A (`TimeGMT()`-based) helpers + Parts A-H structure |
| 2026-05-12 | **v4** | **Critical fix**: Approach A is broken in Strategy Tester per MQL5 docs (`TimeGMT() == TimeTradeServer()` in tester). Swapped to Approach B (manual broker offset + EU DST detection). Added Tier 0 hotfix for `NEW_YORK`/`NY` token mismatch (Issue A, production-impacting). De-overlapped default London/NY UTC windows in G.1. Remapped all v3 line numbers against current 8311-line FORGE.mq5 (+52% growth). Added §A.7 OnInit time-diagnostic helper. Cross-referenced `docs/research/ICT_KILLZONES.md` as authoritative research source. |
