# FORGE — session & time hardening (production notes)

This document collects **production-oriented refinements** for session detection, daily resets, time sources, and broker schedules. It mixes **general patterns** (usable in MQL5 or pseudocode) with a **FORGE-specific appendix** that matches how **`ea/FORGE.mq5`** behaves today so you do not fight the existing model.

---

## 1. Hour-only session detection misses minutes

If you only compare **`dt.hour`**, a window that is meant to end at **12:00** effectively includes **12:00–12:59** when “end” is implemented as “hour &lt; end_hour” without minutes — or the opposite bug can appear depending on implementation.

For **prop-firm rules**, **news blackouts**, or **sub-hour killzones**, use **minute precision** on the same clock you use for trading policy.

```cpp
// Pseudocode / sketch — adapt types to MQL5 (MqlDateTime, etc.)
bool IsTimeBetween(const MqlDateTime &dt, int startH, int startM, int endH, int endM)
{
   int now   = dt.hour * 60 + dt.min;
   int start = startH * 60 + startM;
   int end   = endH   * 60 + endM;

   if(start < end)
      return (now >= start && now < end);

   // Window crosses midnight
   return (now >= start || now < end);
}
```

**FORGE today:** native scalper **`ScalperSessionOK()`** and labels use **`TimeGMT(dt)`** and **`dt.hour` only** (see `ResetScalperSessionStateIfNeeded`, `ScalperTesterSessionOK`). Any move to minute-level blackouts is a **deliberate extension**, not a behavior change “for free.”

---

## 2. Daily reset must be explicit

Counters such as **`trades_this_session = 0`** tied only to a **session string** change behave correctly when the session label flips (e.g. ASIAN → LONDON). They do **not** automatically cover:

- **“Trades per calendar day”** independent of session name.
- **A single `ACTIVE` bucket** that spans midnight.
- **Daily P&L / risk limits** that roll at a fixed **UTC** (or broker) day boundary.

Pattern: track **`last_day_reset`** and compare **date parts** (day/month/year) on your canonical clock.

```cpp
datetime last_day_reset = 0;

bool IsNewTradingDay()
{
   MqlDateTime now, prev;
   TimeToStruct(TimeCurrent(), now);
   TimeToStruct(last_day_reset, prev);
   if(last_day_reset == 0) return true;
   return (now.day != prev.day || now.mon != prev.mon || now.year != prev.year);
}

void CheckDailyReset()
{
   if(IsNewTradingDay())
   {
      trades_today   = 0;
      daily_pnl      = 0.0;
      last_day_reset = TimeCurrent();
      Print("Daily reset at ", TimeToString(TimeCurrent()));
   }
}
```

**FORGE today:** `ResetScalperSessionStateIfNeeded()` resets several scalper counters on **`today != g_scalper_last_reset_day`** (UTC date from **`TimeGMT`**) and on **session label** changes (first-entry anchors). That is **not** the same as a generic **`trades_today`** struct unless you add it.

**Clock choice:** FORGE’s **session policy** is anchored in **`TimeGMT()`**. For **daily** limits, prefer **`TimeGMT`** for the “trading day” definition **or** document explicitly that **`TimeCurrent()`** (server) defines the day — **do not mix both half-and-half** without documenting which wins.

---

## 3. Backtest-safe time source

In the Strategy Tester:

- **`TimeLocal()`** follows the **PC** clock and **does not** simulate the test period.
- **`TimeCurrent()`** advances with **simulated** market time (what you want for bar-aligned logic).
- **`TimeGMT()`** is used widely in FORGE for **UTC hour** session classification; in tester it follows **simulated** time in the platform model — still prefer it over **`TimeLocal()`** for **policy**.

**Rule of thumb:** use **`TimeCurrent()`** or **`TimeGMT()`** (per policy) for **gating**; reserve **`TimeLocal()`** for **human** log captions if needed.

---

## 4. Broker session / maintenance (`SymbolInfoSessionTrade`)

Wiring **broker trading sessions** avoids arming logic when the symbol cannot trade (maintenance, holiday sessions, partial schedules).

Sketch (API details vary by build — **verify in MetaEditor Help** for exact overloads and whether `from`/`to` are **seconds-since-midnight** or **full `datetime`**):

```cpp
bool IsBrokerSessionOpen(const string symbol)
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   ENUM_DAY_OF_WEEK dow = (ENUM_DAY_OF_WEEK)dt.day_of_week;

   datetime from, to;
   datetime now_seconds = (dt.hour * 3600) + (dt.min * 60) + dt.sec;

   for(uint i = 0; ; i++)
   {
      if(!SymbolInfoSessionTrade(symbol, dow, i, from, to))
         break;
      if(now_seconds >= from && now_seconds < to)
         return true;
   }
   return false;
}
```

**Caveat:** `SymbolInfoSessionTrade` return semantics and `from`/`to` encoding are easy to get wrong—**read the official MQL5 reference** for your build. If `from`/`to` are **`datetime`**, compare using **`TimeCurrent()`** windows instead of `now_seconds`.

**FORGE today:** native scalper does **not** gate on **`SymbolInfoSessionTrade`**; it uses **`session_filter`** + **`skip_*`** + spread and other guards.

---

## 5. Suggested consolidated state (crash-friendly)

Loose globals are harder to persist after a crash or restart. A small struct can be **serialized** (e.g. to a file in `FilesPath`) if you need recovery.

```cpp
struct SessionState
{
   string   active_session;
   datetime session_start;
   datetime last_day_reset;
   datetime last_signal_time;
   datetime last_entry_time;
   int      trades_this_session;
   int      trades_today;
   bool     broker_open;

   void Reset()
   {
      active_session        = "OFF_SESSION";
      session_start         = 0;
      trades_this_session   = 0;
   }
};

SessionState g_state;
```

**FORGE today:** session-ish state is spread across **`g_scalper_*`** globals plus **`ScalperConfig`**; **`mode_status.json`** exposes a subset. A refactor to a struct would be **incremental** and should not change JSON contracts without updating **`docs/DATA_CONTRACT.md`**.

---

## 6. `OnTimer()` vs `OnTick()`

| Responsibility | Suggested hook |
|----------------|----------------|
| Session state, **daily** resets, **broker session** check, **dashboard** / `mode_status` refresh | **`OnTimer`** (e.g. 1–60 s) |
| Signal evaluation, entries/exits, **tick-sensitive** management | **`OnTick`** |

**Why:** on thin markets or weekends, ticks may **stall**; timers still run — good for **housekeeping**. If **entries** are evaluated only on timer, you can **miss** intrabar behavior your strategy assumes.

**FORGE today:** confirm where **`CheckNativeScalperSetups`** and **`WriteModeStatus`** are invoked relative to tick vs timer in your chart template—keep the split intentional when adding new session logic.

---

## 7. Killzones and DST (ICT-style windows)

Classic **killzones** are often defined in **New York local time** (e.g. London KZ **02:00–05:00 NY**, New York KZ **07:00–10:00 NY**), not in **integer UTC hours**.

- **DST** shifts the **UTC offset** twice per year if you convert from NY.
- **Broker server time** may be **GMT+2/+3** (or other) and **not** equal to NY or UTC.

**Pragmatic options:**

1. **Inputs in server time** — document “these hours are **broker server** hours” and **update inputs** when DST changes if the broker does not follow US rules.
2. **Inputs in NY time** — convert using an explicit offset (or a small TZ table) and **document** the assumption.

FORGE’s **`session_filter`** uses **`london_start_utc` / `london_end_utc` / `ny_*`** in config (UTC **hour** indices). Killzones finer than that need **new keys** (hours **and** minutes) and a documented timezone baseline.

---

## Appendix A — FORGE session model (current code, audit summary)

Use this when deciding where new logic plugs in:

| Topic | Current behavior (high level) |
|--------|------------------------------|
| Session clock | **`TimeGMT(dt)`** + **`dt.hour`** for London / NY / residual “Asian” |
| Live vs tester | Different gates: **`ScalperSessionOK()`** vs **`ScalperTesterSessionOK()`** in **`CheckNativeScalperSetups()`** |
| Journal | **`session`** column label from **UTC hour**; **`time`** insert uses **`TimeCurrent()`** — align replay docs to that |
| Config | **`config/scalper_config.defaults.json`** → `session_filter`; tester allowlist tokens **`LONDON`**, **`NY`**, **`ASIAN`** (avoid **`NEW_YORK`** unless EA accepts alias) |

Related prompts: **`docs/prompts/FORGE_MONDAY_DI_SESSION_PROMPT.md`**.

---

## Appendix B — Open design questions

- Should **minute-level** windows reuse **`TimeGMT`** exclusively, or **server** time for broker alignment?
- Should **daily** risk resets follow **UTC 00:00**, **London 00:00**, **NY 00:00**, or **broker midnight**?
- Should **`SymbolInfoSessionTrade`** block **only** new entries, or also **management** (SL/TP)?

Answer these in **config + docs** before merging production hardening.

---

*Document version: 2026-05-08 — production refinements + FORGE appendix; example code is illustrative until wired and tested in `FORGE.mq5`.*
