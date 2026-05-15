# ICT Killzones — Reference & MT5 Implementation for FORGE (XAUUSD)

> Compiled from publicly cited ICT material (Inner Circle Trader / Michael J. Huddleston)
> plus 2025-2026 gold-specific sources. All times anchored to **New York local time** so
> they shift automatically with US DST.
>
> **Audience**: FORGE EA (XAUUSD scalper). Forex-pair-only sections kept for completeness
> but recommendations are tuned for gold.
>
> **Canonical FORGE surface**: this doc is the ICT-canon research reference. The
> **canonical FORGE killzone surface** (5 windows + 3 Silver Bullet sub-windows, with
> implementation review of `ComputeCurrentKillzoneLabel()` vs. the v2.7.120 `IctLiquidity.mqh`
> helpers) lives in `docs/FORGE_SETUP_ICT_MAP.md §B.2` + `§B.7`. Use this doc for ICT theory,
> citations, and the Approach B MQL5 reference; use §B.7 for the FORGE-specific divergence
> analysis and the v2.7.122 alignment plan.

---

## 1. Background

The killzone framework was popularised by Michael J. Huddleston (ICT). Killzones are time
windows **inside** the major forex sessions where institutional volume, liquidity grabs,
and directional moves cluster. They are not the full sessions — they are the
high-probability sub-windows.

Four standard killzones are referenced consistently across ICT-aligned sources:

1. Asian Killzone
2. London Open Killzone
3. New York Open Killzone
4. London Close Killzone

**Gold-specific note**: most current sources (FXNX, Coinmonks, TMGM) cite only three
killzones for XAUUSD — Asian, London, and a fused NY/London-Close window — because
gold's institutional flow doesn't cleanly separate the NY-open and London-close
intervals the way EUR/USD does. FORGE uses the 4-killzone model and treats the
NY-Open + London-Close pair as the **gold prime window** (07:00 – 12:00 NY).

---

## 2. Standard times (New York local time)

### 2.1 Canonical 4-killzone table (forex baseline)

| Killzone        | NY Time            | GMT (winter / EST) | GMT (summer / EDT) | Best instruments (forex)   |
|-----------------|--------------------|--------------------|--------------------|----------------------------|
| Asian           | 20:00 – 00:00      | 01:00 – 05:00      | 00:00 – 04:00      | AUD, NZD, JPY pairs        |
| London Open     | 02:00 – 05:00      | 07:00 – 10:00      | 06:00 – 09:00      | EUR, GBP, CHF pairs        |
| New York Open   | 07:00 – 10:00      | 12:00 – 15:00      | 11:00 – 14:00      | Major USD pairs            |
| London Close    | 10:00 – 12:00      | 15:00 – 17:00      | 14:00 – 16:00      | Major USD pairs, **gold**  |

### 2.2 XAUUSD-tuned reference (FORGE production)

| Killzone (gold) | NY Time         | What gold typically does                                                | Typical move size               |
|-----------------|-----------------|-------------------------------------------------------------------------|---------------------------------|
| Asian KZ        | 20:00 – 00:00   | Accumulation, false breakouts, Asian-range high/low set                 | Low — < 30 pips most days       |
| London Open KZ  | 02:00 – 05:00   | **Judas Swing** ≈ 02:30 sweeps Asian high/low, then reversal            | 50 – 100 pips per candle        |
| NY Open KZ      | 07:00 – 10:00   | Continuation OR reversal of London move; biggest daily move often here  | 50 – 150 pips during overlap    |
| London Close KZ | 10:00 – 12:00   | Profit-taking, retracement to daily mean, reversal of morning trend     | 30 – 60 pips of retrace         |

**Cited stat — the gold prime window** (London–NY overlap, ≈ 13:00 – 17:00 GMT ≈ 08:00 –
12:00 NY winter / 09:00 – 13:00 NY summer): **60-70% of gold's daily range forms here**
(EBC Financial, TradingView ProjectSyndicate 2025 edition). This is the single highest-edge
window in the day.

### 2.3 Variant: NY Killzone for indices

ICT teaches a separate NY window for index futures (NQ, ES), aligned with US cash-equity
open: **08:30 – 11:00 NY time** (tradingrage.com). FORGE doesn't trade indices so this is
out of scope, but flagging it because some XAUUSD sources (Coinmonks "Three Killzones for
Gold") use the index-aligned window (08:00 – 11:00 NY) for gold instead of the
forex-aligned 07:00 – 10:00. Both interpretations show up in the literature; FORGE uses
the forex-aligned 07:00 – 10:00 because it captures the news-driven gold reaction at the
ICE Gold Fix (10:30 ET).

### 2.4 Asian killzone variance (honest caveat)

Different ICT-aligned sources cite slightly different Asian killzone bounds. This is the
killzone with the most disagreement:

| Variant         | NY time         | Source                                |
|-----------------|-----------------|---------------------------------------|
| 20:00 – 00:00   | broadest        | Trader Theory, ICT Academy, FXNX      |
| 20:00 – 22:00   | tightest        | tradingrage.com                       |
| 19:00 – 23:00   | offset          | writofinance.com                      |
| 19:00 – 03:00   | gold-specific   | Coinmonks "Three Killzones for Gold"  |

The **20:00 – 00:00 window is the broadest defensible default** and is what FORGE uses
below. For XAUUSD specifically, the Coinmonks 19:00 – 03:00 window better captures the
Tokyo-open accumulation pattern that precedes the London Judas Swing — consider
widening if backtest validates.

---

## 3. The Judas Swing — critical pattern during London Open KZ

The single most-cited ICT pattern inside the London Open KZ. Mechanics:

1. **Pre-London setup** (Asian KZ): Asian range establishes a high and a low. Retail
   traders place orders just outside the range (buy-stops above high, sell-stops
   below low).
2. **02:30 NY (London Open KZ)**: institutions push price *into* one of the Asian extremes
   to trigger stop liquidity. Looks like a directional breakout.
3. **02:30 – 03:30 NY**: price reverses sharply away from the swept side. The Judas Swing
   was a head-fake; the day's real direction is the opposite.

**Why FORGE cares**: our MOMENTUM_DUMP setup can fire on the Judas Swing breakout candle
and end up against-market within 30 minutes. Adding "is this within the first 60 min of
London Open KZ?" as a regime atom lets composites add caution or amplify confirmation
filters during this exact window.

**Mitigation pattern** (for later research, not v2.7.36 scope): wait for a structural
confirmation candle (close back inside Asian range) before taking entries in the first
hour of London Open KZ.

(Source: FXNX "Judas Swing on Gold: London Trap" 2025; arongroups.co London KZ analysis.)

---

## 4. DST handling — the actual problem in MT5

Most MT5 brokers run server time on a European/Cyprus timezone (commonly GMT+2 in winter,
GMT+3 in summer, following EU DST). NY time is GMT-5 / GMT-4.

The offset between **broker server time** and **NY time** is *not* constant:

| Period                                          | EU DST | US DST | Broker–NY offset |
|-------------------------------------------------|--------|--------|------------------|
| Most of winter (Nov first Sun → Mar second Sun) | off    | off    | +7 hours         |
| Mid-March transition (US-only DST)              | off    | on     | +6 hours         |
| Summer (late Mar → late Oct)                    | on     | on     | +7 hours         |
| Late-October transition (EU-only off)           | off    | on     | +6 hours         |

So a broker-server-hour-based hardcode is wrong twice a year for ~2 weeks each.

**The fix**: convert to NY time programmatically. Two approaches below.

**The most common implementation bug** (per mql5.com community indicators): aligning
killzone settings to **local PC time or broker server time instead of NY time**.
Verify on backtest startup by printing `TimeGMT()`, `TimeCurrent()`, and your
derived `GetNYTimeNow()` side-by-side; offset should match the table above.

---

## 5. MQL5 implementation

### Approach A — Use `TimeGMT()` (recommended for live)

```cpp
//+------------------------------------------------------------------+
//| US DST detection (Second Sun of March → First Sun of November)   |
//| Input: a datetime in UTC. Returns true if US is on EDT.          |
//+------------------------------------------------------------------+
int FirstSundayOfMonth(int year, int month)
{
   MqlDateTime d;
   d.year = year; d.mon = month; d.day = 1;
   d.hour = 0; d.min = 0; d.sec = 0;
   datetime t = StructToTime(d);
   TimeToStruct(t, d); // refresh day_of_week
   // day_of_week: 0=Sun, 1=Mon, ..., 6=Sat
   return (d.day_of_week == 0) ? 1 : (1 + (7 - d.day_of_week));
}

bool IsUS_DST(datetime utc)
{
   MqlDateTime d;
   TimeToStruct(utc, d);

   if(d.mon < 3 || d.mon > 11) return false;
   if(d.mon > 3 && d.mon < 11) return true;

   if(d.mon == 3)
   {
      int second_sun = FirstSundayOfMonth(d.year, 3) + 7;
      if(d.day  < second_sun) return false;
      if(d.day  > second_sun) return true;
      return d.hour >= 7; // DST flips at 02:00 local = 07:00 UTC
   }
   // d.mon == 11
   int first_sun = FirstSundayOfMonth(d.year, 11);
   if(d.day  < first_sun) return true;
   if(d.day  > first_sun) return false;
   return d.hour < 6; // DST ends at 02:00 EDT = 06:00 UTC
}

datetime GetNYTimeNow()
{
   datetime utc = TimeGMT();
   int offset_sec = IsUS_DST(utc) ? -4 * 3600 : -5 * 3600;
   return utc + offset_sec;
}
```

> **Backtest caveat**: `TimeGMT()` in the Strategy Tester uses simulated time, but its DST
> handling can differ from live. Validate by printing `TimeGMT()` and `TimeCurrent()` at
> the start of a backtest and confirming the offset matches your broker.

### Approach B — Manual broker offset input (backtest-safe fallback)

```cpp
input int BrokerGMTOffsetWinter = 2;  // broker GMT offset when EU is on standard time
input int BrokerGMTOffsetSummer = 3;  // broker GMT offset when EU is on summer time

// EU DST: Last Sunday of March → Last Sunday of October
int LastSundayOfMonth(int year, int month)
{
   MqlDateTime d;
   d.year = year; d.mon = month; d.day = 28;
   d.hour = 0; d.min = 0; d.sec = 0;
   datetime t = StructToTime(d);
   TimeToStruct(t, d);
   // walk forward to the last day of the month, then back to Sunday
   int last_day = 28;
   for(int i = 28; i <= 31; i++)
   {
      d.day = i;
      t = StructToTime(d);
      MqlDateTime check; TimeToStruct(t, check);
      if(check.mon == month) last_day = i;
   }
   d.day = last_day;
   t = StructToTime(d);
   TimeToStruct(t, d);
   return last_day - d.day_of_week; // walk back to Sunday
}

bool IsEU_DST(datetime utc)
{
   MqlDateTime d; TimeToStruct(utc, d);
   if(d.mon < 3 || d.mon > 10) return false;
   if(d.mon > 3 && d.mon < 10) return true;
   if(d.mon == 3)
   {
      int last_sun = LastSundayOfMonth(d.year, 3);
      if(d.day < last_sun)  return false;
      if(d.day > last_sun)  return true;
      return d.hour >= 1; // EU DST flips at 01:00 UTC
   }
   int last_sun = LastSundayOfMonth(d.year, 10);
   if(d.day < last_sun)  return true;
   if(d.day > last_sun)  return false;
   return d.hour < 1;
}

datetime BrokerToNY(datetime broker)
{
   int broker_off = IsEU_DST(broker) ? BrokerGMTOffsetSummer : BrokerGMTOffsetWinter;
   datetime utc   = broker - broker_off * 3600;
   int ny_off     = IsUS_DST(utc) ? -4 : -5;
   return utc + ny_off * 3600;
}
```

This version works identically in live and tester because it doesn't depend on `TimeGMT()`.
**Recommended for FORGE** because we backtest in Strategy Tester where `TimeGMT()` behavior
is less reliable.

---

## 6. Killzone detection — drop-in for FORGE

```cpp
//--- killzone configuration in NY-local time (HH*60 + MM)
input bool   UseAsianKZ        = true;
input bool   UseLondonOpenKZ   = true;
input bool   UseNYOpenKZ       = true;
input bool   UseLondonCloseKZ  = true;

input int    AsianKZ_Start     = 20*60;   // 20:00 NY
input int    AsianKZ_End       = 24*60;   // 00:00 NY (midnight wrap-aware)
input int    LondonOpenKZ_Start= 2*60;    // 02:00 NY
input int    LondonOpenKZ_End  = 5*60;    // 05:00 NY
input int    NYOpenKZ_Start    = 7*60;    // 07:00 NY
input int    NYOpenKZ_End      = 10*60;   // 10:00 NY
input int    LondonCloseKZ_Start= 10*60;  // 10:00 NY
input int    LondonCloseKZ_End  = 12*60;  // 12:00 NY

enum KillzoneID { KZ_NONE, KZ_ASIAN, KZ_LONDON_OPEN, KZ_NY_OPEN, KZ_LONDON_CLOSE };

bool MinuteInWindow(int now_min, int start_min, int end_min)
{
   // end_min == 24*60 means "until midnight" — treat as exclusive
   if(start_min < end_min) return now_min >= start_min && now_min < end_min;
   return now_min >= start_min || now_min < end_min; // wraps midnight
}

KillzoneID GetActiveKillzone()
{
   datetime ny = GetNYTimeNow();          // or BrokerToNY(TimeCurrent())
   MqlDateTime d; TimeToStruct(ny, d);

   // Skip weekends in NY time (Sat=6, Sun=0)
   if(d.day_of_week == 6) return KZ_NONE;
   if(d.day_of_week == 0 && d.hour < 17) return KZ_NONE; // Sun pre-open

   int now_min = d.hour * 60 + d.min;

   if(UseAsianKZ       && MinuteInWindow(now_min, AsianKZ_Start,      AsianKZ_End))      return KZ_ASIAN;
   if(UseLondonOpenKZ  && MinuteInWindow(now_min, LondonOpenKZ_Start, LondonOpenKZ_End)) return KZ_LONDON_OPEN;
   if(UseNYOpenKZ      && MinuteInWindow(now_min, NYOpenKZ_Start,     NYOpenKZ_End))     return KZ_NY_OPEN;
   if(UseLondonCloseKZ && MinuteInWindow(now_min, LondonCloseKZ_Start,LondonCloseKZ_End))return KZ_LONDON_CLOSE;

   return KZ_NONE;
}

string KillzoneName(KillzoneID kz)
{
   switch(kz)
   {
      case KZ_ASIAN:        return "ASIAN_KZ";
      case KZ_LONDON_OPEN:  return "LONDON_OPEN_KZ";
      case KZ_NY_OPEN:      return "NY_OPEN_KZ";
      case KZ_LONDON_CLOSE: return "LONDON_CLOSE_KZ";
   }
   return "OFF_KZ";
}
```

**Note on the 10:00 boundary collision**: NY Open ends and London Close starts at the same
minute. The `if/else if` order above gives NY Open priority over the boundary. For FORGE
gold trading, the 07:00 – 12:00 window is contiguous high-volume (the prime window) so the
boundary precedence rarely matters in practice. If you want them to overlap (10:00 counted
as both), restructure as a bitmask of active zones rather than a single enum.

---

## 7. Integration with the FORGE session tracker

```cpp
struct SessionState
{
   string     active_session;
   KillzoneID active_killzone;
   datetime   session_start;
   datetime   killzone_start;
   datetime   last_day_reset;
   datetime   last_signal_time;
   datetime   last_entry_time;
   int        trades_this_session;
   int        trades_this_killzone;
   int        trades_today;
   bool       broker_open;
};
SessionState g_state;

void TrackKillzone()
{
   KillzoneID current = GetActiveKillzone();

   if(current != g_state.active_killzone)
   {
      g_state.active_killzone     = current;
      g_state.killzone_start      = GetNYTimeNow();
      g_state.trades_this_killzone= 0;

      Print("Killzone change: ", KillzoneName(current),
            " (NY ", TimeToString(g_state.killzone_start, TIME_DATE|TIME_MINUTES), ")");
   }
}

void OnTimer()
{
   CheckDailyReset();
   TrackSession();
   TrackKillzone();
}

void OnTick()
{
   if(g_state.active_killzone == KZ_NONE) return;       // killzone gate
   if(!IsBrokerSessionOpen(_Symbol))      return;       // broker gate
   if(g_state.trades_this_killzone >= MaxTradesPerKZ)   return;
   if(g_state.trades_today        >= MaxTradesPerDay)   return;

   // FORGE entry logic here
}
```

**FORGE integration note**: the canonical home for `active_killzone` in v2.7.37+ is the
`RegimeState` struct (Layer 5), not a separate `SessionState`. See
[`FORGE_REGIME_TAXONOMY.md §11`](../../FORGE_REGIME_TAXONOMY.md) for the authoritative
integration point. This `SessionState` example is preserved as the reference
implementation for non-FORGE use.

---

## 8. Practical recommendations for FORGE (XAUUSD)

### 8.1 Killzone enablement

- **Always enable** `LondonOpenKZ`, `NYOpenKZ`, `LondonCloseKZ` — these are the three
  highest-edge windows for gold and contain the gold prime window (07:00 – 12:00 NY).
- **Conditionally enable** `AsianKZ` — gold is in accumulation; entries are lower-edge.
  Better use: *record the Asian range high/low* for later use by London Open logic
  (Judas Swing target detection), but skip entries inside the Asian window unless we
  build a specific Asian-range-breakout setup.

### 8.2 Killzone-aware composite gating

The killzone becomes a **Layer-5 atom** consumable by every boolean composite. Example
filter chain extensions:

| Composite                  | Killzone amplification / gating                                       |
|----------------------------|-----------------------------------------------------------------------|
| `BULL_DAY_DIP_BUY`         | Amplify lot ×1.5 inside `LONDON_OPEN_KZ` ∪ `NY_OPEN_KZ` (prime window)|
| `INTRADAY_REVERSAL_SELL`   | Only fire inside `NY_OPEN_KZ` ∪ `LONDON_CLOSE_KZ` (institutional flip)|
| `MOMENTUM_DUMP_SELL`       | **Add caution filter** in first 60 min of `LONDON_OPEN_KZ` (Judas Swing risk) |
| `BLOCK_SELL_IN_CHOP`       | Always-on regardless of killzone                                      |
| `CHOP_LADDER_BUY_GRID`     | Disable inside `LONDON_CLOSE_KZ` (institutions square positions — directional reversal risk) |

### 8.3 Trade-count caps per killzone

Adding a `MaxTradesPerKZ` cap (default 3-5 per killzone) prevents over-trading in the same
window. New gate code candidate for `gate_legend.json`: `killzone_trade_cap`.

### 8.4 Killzone + bias filter beats killzone alone

The killzone tells you **when**; the HTF directional bias (D1/H4 BOS or
premium-discount, or `g_regime.htf_label` in FORGE terms) tells you **which side**.
Never gate purely on killzone — always combine with the HTF regime atom.

### 8.5 Log every killzone transition

For backtest forensics: when something looks weird, the first check is whether the EA saw
the correct killzone at the correct moment. Add a log line at every killzone change with
NY time, broker time, and active symbol. Also add `killzone` as a column to SIGNALS in
v2.7.36 schema for retrospective composite validation.

---

## 9. Validation checklist before shipping killzones to FORGE

| # | Check                                                                          | How                                                                      |
|---|--------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| 1 | NY time correct in live + tester                                               | Print `TimeGMT() / TimeCurrent() / GetNYTimeNow()` at OnInit; verify offset matches §4 table for current month |
| 2 | DST flips work both directions                                                 | Run tester across 2nd Sun of March + 1st Sun of Nov; killzone start times stay at same NY minute |
| 3 | Killzone transitions logged                                                    | `grep -E "Killzone change" tester.log \| sort -u` should show exactly 4 transitions per weekday |
| 4 | No off-by-one at boundaries                                                    | At 10:00 NY exactly: verify only one killzone reports active (NY Open per §6 precedence) |
| 5 | Weekend handling                                                               | Saturday + early Sunday: `GetActiveKillzone() == KZ_NONE` always         |
| 6 | Cross-day backtest of FORGE existing TAKEN trades                              | Add `killzone` column to SIGNALS; verify the Mar 31 → Apr 8 case-study entries land in expected killzones (no entries reported as `OFF_KZ` since FORGE only trades during sessions) |

---

## 10. Sources

Cross-confirmed across ≥3 of the following:

- [tradingrage.com — ICT Killzones (2026)](https://tradingrage.com/learn/ict-killzone-explained)
- [icttrading.org — ICT Kill Zones Time Asia London New York (Complete Guide)](https://icttrading.org/ict-kill-zone-time/)
- [innercircletrader.net — Master ICT Kill Zones](https://innercircletrader.net/tutorials/master-ict-kill-zones/)
- writofinance.com — *ICT Trading Sessions and Kill Zones* (Jan 2025)
- [howtotrade.com — Trading ICT Kill Zones in Forex (2025) (PDF)](https://howtotrade.com/wp-content/uploads/2024/08/ICT-Kill-Zones-in-Forex-Trading.pdf)
- [FXNX — ICT Killzones: Master XAUUSD Timing](https://fxnx.com/en/blog/ict-killzones-master-xauusd-timing-maximum-profit) (XAUUSD-specific)
- [FXNX — ICT Judas Swing on Gold: London Trap](https://fxnx.com/en/blog/mastering-ict-judas-swing-gold-trading-london-trap) (XAUUSD Judas Swing)
- [Coinmonks — The Three Killzones Every Gold Trader Should Master](https://medium.com/coinmonks/the-three-killzones-every-gold-trader-should-master-7273874be728) (gold 3-KZ variant)
- [EBC Financial — What Are ICT Killzone Times?](https://www.ebc.com/forex/what-are-ict-killzone-times-simple-trading-hours-guide) (London-NY overlap = 60-70% of gold's range)
- [TradingView — ICT Concepts for FX and GOLD traders: 2025 edition (ProjectSyndicate)](https://www.tradingview.com/chart/EURUSD/4Pwu94h1-ICT-Concepts-for-FX-and-GOLD-traders-2025-edition/)
- [arongroups.co — ICT London Killzone Time & Strategy](https://arongroups.co/forex-articles/ict-london-killzone-time/)
- [LuxAlgo — ICT Killzones Toolkit](https://www.luxalgo.com/library/indicator/ict-killzones-toolkit/) (TradingView indicator reference)
- [mql5.com — Institutional ICT Killzones and Asian Range](https://www.mql5.com/en/code/71073) (MQL5 reference implementation)

The Asian-killzone variance noted in §2.4 is real — different sources publish slightly
different bounds. The 20:00 – 00:00 default is the most common; the Coinmonks 19:00 – 03:00
gold variant is worth backtesting.

---

## 11. Changelog (this doc)

| Date       | Change                                                                                                             |
|------------|--------------------------------------------------------------------------------------------------------------------|
| 2026-05-12 | Initial doc imported from operator's research download. 8 sources cited.                                          |
| 2026-05-12 | Expanded with XAUUSD-specific findings: §2.2 gold-tuned KZ table, §2.4 Asian variance, §3 Judas Swing section, §4 most-common-bug note, §8 killzone-aware composite gating, §9 validation checklist. 13 sources total (added 5 gold-specific). FORGE integration cross-link to `FORGE_REGIME_TAXONOMY.md §11`. |
