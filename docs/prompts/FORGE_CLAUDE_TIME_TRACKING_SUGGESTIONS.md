# Prompt for Local AI — FORGE.mq5 Time / Session / Killzone Refactor

You are working on `FORGE.mq5`, version 2.75, ~5474 lines. This file is an MT5 Expert
Advisor for forex/index scalping. You will fix the time-tracking and session-detection
code so that it is minute-precise, NY-time anchored (DST-aware), and adds ICT killzone
detection. **Preserve every existing flag and function name unless explicitly told to
remove one.** Do not invent functions, fields, or behaviour beyond what is specified
below. If something is unclear, ask the user — do not guess.

---

## 0. Ground rules

- **Do not rename existing identifiers** unless this prompt says so.
- **Do not change behaviour outside the listed sections.** This is a surgical refactor.
- **Preserve all existing JSON config keys** (`london_start_utc`, `london_end_utc`,
  `ny_start_utc`, `ny_end_utc`, `skip_asian`, `skip_london`, `skip_ny`,
  `tester_session_filter`, `tester_allowed_sessions`). Add new keys alongside them; do
  not break old configs.
- **Preserve all existing globals** named in §2 below.
- If you must add a new flag, prefix it consistently with the existing scheme
  (`g_sc.` for config struct fields, `g_scalper_` for module globals).
- After your edits, the file must compile in MetaEditor without warnings.

---

## 1. Reference: existing code anchors (verified line numbers in v2.75)

These are real locations in the file. Use them to find the code, but tolerate small
line-number drift if the user has edited since.

| What                                          | Line(s)        |
|-----------------------------------------------|----------------|
| `struct ScalperConfig` Session block          | 196 – 206      |
| Session field defaults in `InitScalperConfig` | 2045 – 2051    |
| Session JSON keys read in `ReadScalperConfig` | 2334 – 2352    |
| `ResetScalperSessionStateIfNeeded()`          | 2806 – 2845    |
| `ScalperSessionOK()`                          | 2847 – 2858    |
| `ScalperTesterSessionOK()`                    | 2860 – 2884    |
| `JournalRecordSignal()` session block         | 3578 – 3583    |
| Session-blocked check in `CheckNativeScalperSetups()` | 3997 – 4021 |
| Globals `g_scalper_last_reset_day` etc.       | 117 – 145      |
| Inputs (`InputMode` etc.)                     | 66 – 94        |

---

## 2. Existing identifiers you must preserve

### Config struct fields (`ScalperConfig`, lines 196–206)
- `int  london_start, london_end, ny_start, ny_end`
- `bool skip_asian, skip_london, skip_ny`
- `bool tester_session_filter`
- `string tester_allowed_sessions`

### Globals (lines 117–145)
- `datetime g_scalper_last_reset_day`
- `string   g_scalper_last_session_label`
- `int      g_scalper_session_trades`
- `datetime g_scalper_last_entry_bar`
- `string   g_scalper_last_direction`
- `datetime g_scalper_last_direction_time`
- `double   g_first_buy_entry_price`
- `double   g_first_sell_entry_price`
- `bool     g_scalper_prev_session_blocked`
- `datetime g_forge_init_gmt`
- `datetime g_scalper_last_sesswarn_log_bar`

### Functions (must keep their names and signatures)
- `void ResetScalperSessionStateIfNeeded()`
- `bool ScalperSessionOK()`
- `bool ScalperTesterSessionOK()`
- `void JournalRecordSignal(...)`

---

## 3. Bugs / weaknesses being fixed

Do not exaggerate or rename these — these are the actual issues:

1. **Hour-only precision.** Every session check uses `dt.hour >= start && dt.hour < end`.
   Lines 2812, 2814, 2851–2852, 2870–2872, 3582–3583, 4007. A session ending at hour 12
   actually runs through 12:59, and a session starting at hour 7 fires immediately at
   07:00 UTC even if the intent was 07:30. Fix: switch to minute-resolution `now_min`
   (`dt.hour * 60 + dt.min`) comparisons.

2. **No DST handling.** Windows are stored as UTC hours. When NY DST and EU DST shift
   on different dates (mid-March ~2 weeks; late October ~1 week), the broker–NY offset
   moves from +7h to +6h, so a UTC-anchored "London 07:00–10:00" no longer matches the
   actual NY-time London Open Killzone (02:00–05:00 NY). Fix: add NY-time-anchored mode
   (selectable, default off so existing configs still work).

3. **ASIA is a fallback, not a window.** Lines 2811, 2853, 2869, 3581 — anything not
   London and not NY is labelled ASIAN. The dead zone between sessions (e.g. NY end →
   Asia open) is mis-labelled. Fix: add explicit `asia_start` / `asia_end` fields with
   a fallback that preserves current behaviour when those fields are unset.

4. **Default config is degenerate.** `london_start=0, london_end=24, ny_start=0, ny_end=24`
   (lines 2045–2048) means every hour matches LONDON, so NY and ASIA branches never fire
   on default config. Fix: replace defaults with sensible NY-anchored values. Document
   that JSON must override for UTC-mode users.

5. **No killzone detection.** ICT killzones (sub-windows inside sessions) are not coded.
   Add them as an opt-in layer.

6. **Day rollover uses UTC midnight.** Line 2821: `midnight_utc = (dt.hour == 0 && ...)`.
   When NY-anchored mode is on, day rollover should be at NY midnight (= 05:00 UTC
   winter, 04:00 UTC summer) so daily counters don't reset in the middle of London Open
   killzone. Fix: rollover boundary follows the active anchor.

---

## 4. Required additions

### 4.1 New struct fields (append to `ScalperConfig`, lines 196–206)

```cpp
   // Session — minute precision (additive; integer minute-of-day 0..1439)
   int    london_start_min;       // -1 = use legacy hour-only field
   int    london_end_min;         // -1 = use legacy hour-only field
   int    ny_start_min;           // -1 = use legacy hour-only field
   int    ny_end_min;             // -1 = use legacy hour-only field
   int    asia_start_min;         // -1 = behaves as fallback (current behaviour)
   int    asia_end_min;           // -1 = behaves as fallback

   // Session — NY-time anchoring (DST-aware)
   bool   sessions_ny_anchored;   // false = UTC (legacy); true = NY local time
                                  //   When true, *_min fields are NY-local minute-of-day

   // Killzones (NY-time minute-of-day; -1 = disabled)
   bool   killzones_enabled;
   int    kz_asia_start_min;      // default 19*60+0  (19:00 NY)
   int    kz_asia_end_min;        // default  3*60+0  (03:00 NY, wraps)
   int    kz_london_open_start_min;   // default 2*60+0   (02:00 NY)
   int    kz_london_open_end_min;     // default 5*60+0   (05:00 NY)
   int    kz_ny_open_start_min;       // default 7*60+0   (07:00 NY)
   int    kz_ny_open_end_min;         // default 10*60+0  (10:00 NY)
   int    kz_london_close_start_min;  // default 10*60+0  (10:00 NY)
   int    kz_london_close_end_min;    // default 12*60+0  (12:00 NY)
```

### 4.2 New globals (place near line 145 with the other `g_scalper_*`)

```cpp
string   g_scalper_last_killzone_label = "";   // last killzone label seen
datetime g_scalper_killzone_start_time = 0;    // when current killzone became active (NY time if anchored, GMT otherwise)
int      g_scalper_killzone_trades    = 0;     // entry count inside current killzone
```

### 4.3 New helper functions (add immediately above `ResetScalperSessionStateIfNeeded`)

```cpp
//+------------------------------------------------------------------+
//| US DST: second Sunday of March → first Sunday of November.       |
//| Input: a datetime in UTC. Returns true if EDT (UTC-4).           |
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

bool MinuteInWindow(int now_min, int start_min, int end_min) {
   if(start_min < 0 || end_min < 0) return false;        // disabled / not configured
   if(start_min < end_min) return now_min >= start_min && now_min < end_min;
   return now_min >= start_min || now_min < end_min;     // wraps midnight
}

// Return current "active datetime" used for session decisions. When NY-anchored mode is
// on, this is NY local time; otherwise it remains TimeGMT() to preserve legacy behaviour.
datetime GetSessionAnchorTime() {
   return g_sc.sessions_ny_anchored ? GetNYTimeNow() : TimeGMT();
}

// Resolve effective session window in minute-of-day. If *_min field is < 0, fall back
// to the legacy hour-only field (hour * 60). This keeps old configs working.
void GetEffectiveLondonWindow(int &start_min, int &end_min) {
   start_min = (g_sc.london_start_min >= 0) ? g_sc.london_start_min : g_sc.london_start * 60;
   end_min   = (g_sc.london_end_min   >= 0) ? g_sc.london_end_min   : g_sc.london_end   * 60;
}
void GetEffectiveNYWindow(int &start_min, int &end_min) {
   start_min = (g_sc.ny_start_min >= 0) ? g_sc.ny_start_min : g_sc.ny_start * 60;
   end_min   = (g_sc.ny_end_min   >= 0) ? g_sc.ny_end_min   : g_sc.ny_end   * 60;
}
void GetEffectiveAsiaWindow(int &start_min, int &end_min) {
   // Asia is optional. -1/-1 means "use fallback labelling" (caller handles).
   start_min = g_sc.asia_start_min;
   end_min   = g_sc.asia_end_min;
}

// Compute current session label (ASIAN | LONDON | NY) using effective windows and the
// active anchor time. Priority when overlapping: NY > LONDON > ASIA (matches volume
// dominance during London-NY overlap).
string ComputeCurrentSessionLabel() {
   datetime t = GetSessionAnchorTime();
   MqlDateTime dt; TimeToStruct(t, dt);
   int now_min = dt.hour * 60 + dt.min;

   int ls, le, ns, ne, as_, ae;
   GetEffectiveLondonWindow(ls, le);
   GetEffectiveNYWindow(ns, ne);
   GetEffectiveAsiaWindow(as_, ae);

   if(MinuteInWindow(now_min, ns, ne)) return "NY";
   if(MinuteInWindow(now_min, ls, le)) return "LONDON";
   if(as_ >= 0 && ae >= 0) {
      if(MinuteInWindow(now_min, as_, ae)) return "ASIAN";
      return "OFF";   // explicit Asia configured and we're outside it
   }
   return "ASIAN";    // legacy fallback
}

// Killzone detection. Returns one of:
//   "" (none) | "ASIAN_KZ" | "LONDON_OPEN_KZ" | "NY_OPEN_KZ" | "LONDON_CLOSE_KZ"
// Killzones are always evaluated in NY local time regardless of sessions_ny_anchored,
// because killzones are an ICT concept defined in NY time.
string ComputeCurrentKillzoneLabel() {
   if(!g_sc.killzones_enabled) return "";
   datetime ny = GetNYTimeNow();
   MqlDateTime dt; TimeToStruct(ny, dt);
   if(dt.day_of_week == 6) return "";
   if(dt.day_of_week == 0 && dt.hour < 17) return "";
   int now_min = dt.hour * 60 + dt.min;

   if(MinuteInWindow(now_min, g_sc.kz_ny_open_start_min,      g_sc.kz_ny_open_end_min))      return "NY_OPEN_KZ";
   if(MinuteInWindow(now_min, g_sc.kz_london_open_start_min,  g_sc.kz_london_open_end_min))  return "LONDON_OPEN_KZ";
   if(MinuteInWindow(now_min, g_sc.kz_london_close_start_min, g_sc.kz_london_close_end_min)) return "LONDON_CLOSE_KZ";
   if(MinuteInWindow(now_min, g_sc.kz_asia_start_min,         g_sc.kz_asia_end_min))         return "ASIAN_KZ";
   return "";
}
```

### 4.4 Update `InitScalperConfig` (lines ~2045–2051)

Append after the existing session defaults — **do not remove the existing four lines**:

```cpp
   // Minute-precision fields default to -1 (use legacy hour fields)
   g_sc.london_start_min = -1;
   g_sc.london_end_min   = -1;
   g_sc.ny_start_min     = -1;
   g_sc.ny_end_min       = -1;
   g_sc.asia_start_min   = -1;
   g_sc.asia_end_min     = -1;
   g_sc.sessions_ny_anchored = false;   // default off — preserves v2.75 behaviour

   // Killzones — disabled by default; default windows in NY local time
   g_sc.killzones_enabled        = false;
   g_sc.kz_asia_start_min        = 19*60;
   g_sc.kz_asia_end_min          =  3*60;
   g_sc.kz_london_open_start_min =  2*60;
   g_sc.kz_london_open_end_min   =  5*60;
   g_sc.kz_ny_open_start_min     =  7*60;
   g_sc.kz_ny_open_end_min       = 10*60;
   g_sc.kz_london_close_start_min= 10*60;
   g_sc.kz_london_close_end_min  = 12*60;
```

### 4.5 Update `ReadScalperConfig` (insert after line 2352)

**Keep the existing `london_start_utc` / `london_end_utc` / `ny_start_utc` / `ny_end_utc`
/ `skip_*` readers untouched.** Add new keys *additively*:

```cpp
   // Minute-precision overrides (optional; -1 = ignore)
   if(JsonHasKey(content, "london_start_min")) {
      v = JsonGetDouble(content, "london_start_min");
      if(v >= 0 && v <= 1439) g_sc.london_start_min = (int)v;
   }
   if(JsonHasKey(content, "london_end_min")) {
      v = JsonGetDouble(content, "london_end_min");
      if(v >= 0 && v <= 1440) g_sc.london_end_min = (int)v;
   }
   if(JsonHasKey(content, "ny_start_min")) {
      v = JsonGetDouble(content, "ny_start_min");
      if(v >= 0 && v <= 1439) g_sc.ny_start_min = (int)v;
   }
   if(JsonHasKey(content, "ny_end_min")) {
      v = JsonGetDouble(content, "ny_end_min");
      if(v >= 0 && v <= 1440) g_sc.ny_end_min = (int)v;
   }
   if(JsonHasKey(content, "asia_start_min")) {
      v = JsonGetDouble(content, "asia_start_min");
      if(v >= 0 && v <= 1439) g_sc.asia_start_min = (int)v;
   }
   if(JsonHasKey(content, "asia_end_min")) {
      v = JsonGetDouble(content, "asia_end_min");
      if(v >= 0 && v <= 1440) g_sc.asia_end_min = (int)v;
   }
   if(JsonHasKey(content, "sessions_ny_anchored")) {
      v = JsonGetDouble(content, "sessions_ny_anchored");
      g_sc.sessions_ny_anchored = (v >= 0.5);
   }

   // Killzones (all NY-local minute-of-day)
   if(JsonHasKey(content, "killzones_enabled")) {
      v = JsonGetDouble(content, "killzones_enabled");
      g_sc.killzones_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "kz_asia_start_min"))         { v = JsonGetDouble(content, "kz_asia_start_min");         if(v >= 0 && v <= 1439) g_sc.kz_asia_start_min         = (int)v; }
   if(JsonHasKey(content, "kz_asia_end_min"))           { v = JsonGetDouble(content, "kz_asia_end_min");           if(v >= 0 && v <= 1440) g_sc.kz_asia_end_min           = (int)v; }
   if(JsonHasKey(content, "kz_london_open_start_min"))  { v = JsonGetDouble(content, "kz_london_open_start_min");  if(v >= 0 && v <= 1439) g_sc.kz_london_open_start_min  = (int)v; }
   if(JsonHasKey(content, "kz_london_open_end_min"))    { v = JsonGetDouble(content, "kz_london_open_end_min");    if(v >= 0 && v <= 1440) g_sc.kz_london_open_end_min    = (int)v; }
   if(JsonHasKey(content, "kz_ny_open_start_min"))      { v = JsonGetDouble(content, "kz_ny_open_start_min");      if(v >= 0 && v <= 1439) g_sc.kz_ny_open_start_min      = (int)v; }
   if(JsonHasKey(content, "kz_ny_open_end_min"))        { v = JsonGetDouble(content, "kz_ny_open_end_min");        if(v >= 0 && v <= 1440) g_sc.kz_ny_open_end_min        = (int)v; }
   if(JsonHasKey(content, "kz_london_close_start_min")) { v = JsonGetDouble(content, "kz_london_close_start_min"); if(v >= 0 && v <= 1439) g_sc.kz_london_close_start_min = (int)v; }
   if(JsonHasKey(content, "kz_london_close_end_min"))   { v = JsonGetDouble(content, "kz_london_close_end_min");   if(v >= 0 && v <= 1440) g_sc.kz_london_close_end_min   = (int)v; }
```

### 4.6 Replace `ResetScalperSessionStateIfNeeded` (lines 2806–2845)

Same name, same call sites. New body uses the helpers and adds killzone tracking:

```cpp
void ResetScalperSessionStateIfNeeded() {
   datetime anchor = GetSessionAnchorTime();
   MqlDateTime dt; TimeToStruct(anchor, dt);

   datetime today = StringToTime(StringFormat("%04d.%02d.%02d 00:00", dt.year, dt.mon, dt.day));
   if(today <= 0) return;

   string current_session  = ComputeCurrentSessionLabel();   // ASIAN | LONDON | NY | OFF
   string current_killzone = ComputeCurrentKillzoneLabel();  // "" or *_KZ

   if(g_scalper_last_reset_day == 0) {
      g_scalper_last_reset_day      = today;
      g_scalper_last_session_label  = current_session;
      g_scalper_last_killzone_label = current_killzone;
      return;
   }

   bool day_rolled = (today != g_scalper_last_reset_day);
   if(day_rolled) {
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
      PrintFormat("FORGE SCALPER: daily reset (%s anchor)",
                  g_sc.sessions_ny_anchored ? "NY" : "UTC");
      return;
   }

   if(g_scalper_last_session_label == "") {
      g_scalper_last_session_label = current_session;
   }
   if(current_session != g_scalper_last_session_label) {
      g_scalper_last_session_label = current_session;
      g_first_buy_entry_price      = 0.0;
      g_first_sell_entry_price     = 0.0;
      PrintFormat("FORGE SCALPER: session change → %s (%s %02d:%02d)",
                  current_session,
                  g_sc.sessions_ny_anchored ? "NY" : "UTC",
                  dt.hour, dt.min);
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

### 4.7 Replace `ScalperSessionOK` (lines 2847–2858)

```cpp
bool ScalperSessionOK() {
   string s = ComputeCurrentSessionLabel();
   if(s == "OFF") return false;
   if(s == "LONDON" && g_sc.skip_london) return false;
   if(s == "NY"     && g_sc.skip_ny)     return false;
   if(s == "ASIAN"  && g_sc.skip_asian)  return false;
   return true;
}
```

### 4.8 Replace `ScalperTesterSessionOK` (lines 2860–2884)

Behaviour preserved; only the session-label computation changes:

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
      StringTrimLeft(parts[i]);
      StringTrimRight(parts[i]);
      StringToUpper(parts[i]);
      if(parts[i] == current_session) return true;
   }
   return false;
}
```

### 4.9 Update `JournalRecordSignal` session block (lines 3578–3583)

Replace the five-line block that derives `session` from `dt.hour` with:

```cpp
   string session = ComputeCurrentSessionLabel();
```

The SQL INSERT (line 3585+) is unchanged.

### 4.10 Update `CheckNativeScalperSetups` log line (line ~4015–4016)

The `PrintFormat` currently logs UTC hour bounds. Replace just that PrintFormat with:

```cpp
         PrintFormat("FORGE SCALPER: skip gate=session_off anchor=%s %02d:%02d (no trades)",
                     g_sc.sessions_ny_anchored ? "NY" : "UTC", dt.hour, dt.min);
```

Leave the surrounding logic (`session_blocked`, `g_scalper_last_sesswarn_log_bar`, the
JournalRecordSignal call) untouched.

---

## 5. Optional: expose killzone in JSON output

If you also want the killzone label in `market_data.json` for the dashboard, add this
single line inside `WriteMarketData()` (function starts at line 1749) wherever it fits
the existing structure — for example, right after the existing session-related fields:

```cpp
   j += "\"current_session\":\"" + JsonEscape(ComputeCurrentSessionLabel()) + "\",";
   j += "\"current_killzone\":\"" + JsonEscape(ComputeCurrentKillzoneLabel()) + "\",";
```

This is optional. Skip it if it conflicts with the dashboard's existing schema.

---

## 6. Acceptance criteria

After your edits, all of the following must hold:

1. **Compiles in MetaEditor without warnings** on MQL5 build matching the user's terminal.
2. **Existing config files still load** — a JSON file containing only the legacy keys
   (`london_start_utc` etc.) produces identical session behaviour to v2.75.
3. **`sessions_ny_anchored=false`** (default) makes session detection bit-identical to
   v2.75 except for minute-precision boundaries. If the user sets `*_min` fields to
   `hour*60`, behaviour is exactly identical.
4. **`sessions_ny_anchored=true`** with `*_min` fields set in NY-local minutes produces
   correct session labels across both DST and non-DST periods. Verify by setting
   the system clock to a known DST transition date and confirming a London Open
   killzone (02:00–05:00 NY) starts at the correct UTC hour on either side of the shift.
5. **`killzones_enabled=false`** (default) makes `ComputeCurrentKillzoneLabel()` always
   return `""` and produces no log spam.
6. **Day rollover** still resets `g_scalper_session_trades`, `g_first_buy_entry_price`,
   `g_first_sell_entry_price`, `g_scalper_last_entry_bar`, `g_scalper_last_direction`,
   `g_scalper_last_direction_time` exactly as before. The only change is when the
   rollover fires (NY midnight vs UTC midnight, depending on `sessions_ny_anchored`).
7. **No identifier renamed** beyond what this prompt explicitly authorises.

---

## 7. What NOT to do

- Do **not** remove `london_start`, `london_end`, `ny_start`, `ny_end` or their JSON
  readers. They are the legacy fallback and other parts of the code path may rely on them.
- Do **not** rename `g_scalper_last_session_label`, `g_scalper_last_reset_day`,
  `g_scalper_session_trades`, or `g_scalper_prev_session_blocked`.
- Do **not** add killzone gating inside `ScalperSessionOK()`. Killzones are tracked but
  not enforced unless the user later asks. Adding enforcement now would change live
  trading behaviour silently.
- Do **not** move existing function bodies to new files or namespaces.
- Do **not** touch `g_forge_init_gmt`-based warmup logic (line 554 and friends). Warmup
  is a separate concern.

---

## 8. Reference: ICT killzone times (NY local, used as defaults above)

These are the cross-confirmed times from publicly cited ICT material. Defaults match.

| Killzone        | NY Time         | Minute-of-day        |
|-----------------|-----------------|----------------------|
| Asian           | 19:00 – 03:00   | 1140 – 180 (wraps)   |
| London Open     | 02:00 – 05:00   | 120  – 300           |
| NY Open (forex) | 07:00 – 10:00   | 420  – 600           |
| London Close    | 10:00 – 12:00   | 600  – 720           |

**Asian killzone caveat:** different ICT sources cite 20:00–00:00, 20:00–22:00, or
19:00–23:00. Default uses 19:00–03:00 as the broadest defensible range. User can
narrow via JSON.

---

When done, output a unified diff or a list of (file, line range, replacement) tuples.
Do not output the entire file unless the user asks.