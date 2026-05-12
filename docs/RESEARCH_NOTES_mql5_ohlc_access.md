# RESEARCH NOTES — MQL5 OHLC access patterns (iHigh, iLow, iOpen, iClose, CopyRates)

## §1. Question / Goal

Establish canonical MQL5 patterns for retrieving OHLC bars across timeframes — particularly the PERIOD_D1 freshness gotchas at session open that have bitten FORGE in the past — and recommend a robust wrapper for daily-direction-gate access. The Daily Direction Gate (v2.7.27) reads daily high/low/open/close at session start; if iHigh/iLow return 0 due to history not loaded, the gate falsely passes or fails. We need official `mql5.com/docs` confirmation of the synchronization rules.

## §2. Methodology

**Search queries used (verbatim):**
- `mql5 iHigh iLow iClose PERIOD_D1 daily bar refresh CopyRates site:mql5.com`
- `mql5 forum iHigh PERIOD_D1 daily open returns zero new bar synchronization`

**Sources surveyed (retrieved 2026-05-11):**
- mql5.com/docs/series/ihigh — official iHigh reference (fetched)
- mql5.com/docs/series/copyrates — official CopyRates reference (fetched)
- mql5.com/en/forum/384591 — "iHigh and iLow returns 0.0 [Solved]" (fetched)
- mql5.com/en/forum/432961, 311826, 220592 — related forum threads (search snippets)

**Source-quality filter:**
- Per skill rules: official mql5.com/docs is canonical for MQL5. Used as primary.
- mql5.com forums = community knowledge with operator validation; accepted with caution.

## §3. Findings (cited)

### Finding 1 — iHigh always re-requests timeseries (no local cache)

**Claim**: iHigh requests the timeseries on every call; it does NOT cache. Return value is 0 on error.

**Source**: [MQL5 Docs — iHigh](https://www.mql5.com/en/docs/series/ihigh) (retrieved 2026-05-11)

**Direct quotes**:
- Signature: *"double  iHigh(const string symbol, ENUM_TIMEFRAMES timeframe, int shift);"*
- *"timeframe [in] Period. It can be one of the values of the ENUM_TIMEFRAMES enumeration. 0 means the current chart period."*
- *"shift [in] The index of the received value from the timeseries (backward shift by specified number of bars relative to the current bar)."*
- Return: *"The High price of the bar (indicated by the 'shift' parameter) on the corresponding chart or 0 in case of an error."*
- *"The function always returns actual data. For this purpose it performs a request to the timeseries for the specified symbol/period during each call."*
- *"The function does not store previous calls results, and there is no local cache for quick value return."*

**FORGE application**: Three rules emerge:
1. **Always check for 0** — a zero return is an error, not a valid price. Our Daily Direction Gate must explicitly test `daily_high <= 0` and bail with a clear log entry.
2. **iHigh is "expensive"** — every call hits the timeseries engine. Cache the daily H/L/O/C at the start of OnTick once per day, do not call per tick.
3. **shift=0 returns the bar still forming** — for the prior completed daily bar, use shift=1.

**Confidence**: High — official MQL5 documentation.

### Finding 2 — CopyRates is the modern alternative; data may need to download

**Claim**: CopyRates triggers history download when the terminal lacks data locally; returns -1 on error.

**Source**: [MQL5 Docs — CopyRates](https://www.mql5.com/en/docs/series/copyrates) (retrieved 2026-05-11)

**Direct quotes**:
- Signature: *"int CopyRates(string symbol_name, ENUM_TIMEFRAMES timeframe, int start_pos, int count, MqlRates rates_array[]);"*
- *"Returns the number of copied elements or -1 in case of an error"*
- *"The elements ordering of the copied data is from present to the past, i.e., starting position of 0 means the current bar."*
- *"Data will be copied so that the oldest element will be located at the start of the physical memory allocated for the array."*
- *"If the whole interval of requested data is out of the available data on the server, the function returns -1. If data outside TERMINAL_MAXBARS is requested, the function will also return -1."*
- *"When requesting data from an Expert Advisor or script, downloading from the server will be initiated, if the terminal does not have these data locally."*

**FORGE application**: For batch daily-bar access (e.g., the Direction Gate needs N prior days of D1 bars), CopyRates is preferred over a loop of `iHigh(_Symbol, PERIOD_D1, shift)` calls. The auto-download trigger is helpful but slow — should NOT be invoked in OnTick; must be done in OnInit with retry logic.

**Confidence**: High — official MQL5 documentation.

### Finding 3 — Symbol must be synchronized for cross-timeframe access

**Claim**: For symbols whose chart is not currently open, history may not be downloaded yet; iHigh/CopyRates can return zero/-1 until synchronization completes.

**Source**: [MQL5 Forum — iHigh and iLow returns 0.0 [Solved]](https://www.mql5.com/en/forum/384591) (retrieved 2026-05-11)

**Direct quote** (Ferhat Mutlu in the thread):
- *"Those symbols don't have candlestick data. That is one of the issues of the MT4-MT5. Make sure you open that charts manually and candlesticks there."*

**Reported error code**:
- *"ERR_HISTORY_NOT_FOUND (4401) - Requested history not found"*

**FORGE application**: For FORGE running on XAUUSD M5 reading XAUUSD D1 — same symbol, different timeframe. The official documentation notes this should typically be synchronized, but at session boundary or after a long pause it MAY return 0. Our Daily Direction Gate should:
1. Pre-warm in OnInit with `SeriesInfoInteger(_Symbol, PERIOD_D1, SERIES_SYNCHRONIZED)` check.
2. On the first OnTick of each new day, force a CopyRates(PERIOD_D1, 0, N, ...) and gate the EA from trading until it returns > 0.

**Confidence**: Medium — official docs are clear about the error code (4401) but the explicit pattern "open the chart manually first" is community advice, not official rule.

### Finding 4 — Indexing direction: present-to-past (shift=0 is current)

**Claim**: Standard MT5 indexing: `shift=0` is the bar currently forming, `shift=1` is the most recently completed bar.

**Source**: [MQL5 Docs — iHigh](https://www.mql5.com/en/docs/series/ihigh) (retrieved 2026-05-11) and [MQL5 Docs — CopyRates](https://www.mql5.com/en/docs/series/copyrates) (retrieved 2026-05-11)

**Direct quote**: *"The elements ordering of the copied data is from present to the past, i.e., starting position of 0 means the current bar."*

**FORGE application**: This is well-known but worth re-stating as a rule because mixing MQL4-style as-series arrays with MQL5 non-series patterns is a bug source. Recommended pattern for FORGE: always use `ArraySetAsSeries(arr, true)` immediately after CopyRates, so `arr[0]` is the current bar (matching iHigh shift=0).

**Confidence**: High — official documentation.

## §4. Synthesis / Recommended pattern

**Robust daily-bar wrapper** (MQL5-ready):

```mql5
// Cached daily OHLC, refreshed once per new daily bar.
struct DailyBars {
    datetime last_refresh_time;
    double high, low, open, close;
    bool valid;
};
DailyBars g_daily;

bool RefreshDailyBars() {
    // Verify synchronization first.
    if (!(bool)SeriesInfoInteger(_Symbol, PERIOD_D1, SERIES_SYNCHRONIZED)) {
        Print("FORGE: PERIOD_D1 not synchronized; skipping refresh");
        g_daily.valid = false;
        return false;
    }
    MqlRates rates[];
    ArraySetAsSeries(rates, true);
    int copied = CopyRates(_Symbol, PERIOD_D1, 0, 2, rates);
    if (copied < 2) {
        Print("FORGE: CopyRates(D1) returned ", copied, " err=", GetLastError());
        g_daily.valid = false;
        return false;
    }
    g_daily.open  = rates[0].open;   // today's open (still forming)
    g_daily.high  = rates[0].high;
    g_daily.low   = rates[0].low;
    g_daily.close = rates[1].close;  // yesterday's close (completed bar)
    g_daily.last_refresh_time = TimeCurrent();
    g_daily.valid = true;
    return true;
}

// Call in OnTick; only refreshes when a new day starts.
void MaybeRefreshDaily() {
    static datetime last_day = 0;
    datetime now = TimeCurrent();
    MqlDateTime mdt; TimeToStruct(now, mdt);
    datetime day_start = StructToTime((MqlDateTime){mdt.year, mdt.mon, mdt.day, 0, 0, 0});
    if (day_start != last_day) {
        if (RefreshDailyBars()) last_day = day_start;
    }
}
```

**Atlas linkage**: §8 glossary should include a rule: "Daily-bar access requires (a) SERIES_SYNCHRONIZED check, (b) zero/-1 error handling, (c) cache once per day; do NOT call iHigh(PERIOD_D1) per tick."

## §5. Open questions / Followups

1. **Best practice for OnInit warm-up**: should we loop CopyRates with sleep until SERIES_SYNCHRONIZED returns true, or just bail OnInit and let OnTick retry?
2. **Forex symbols with weekend gap**: on Sunday open, the previous "completed daily bar" is Friday's; some brokers offer a Sunday partial bar. Our cached `g_daily.close` (rates[1]) may not be Friday's true close depending on broker. Need broker-specific test.
3. **iHigh vs CopyRates performance**: a single iHigh call vs a 2-bar CopyRates — empirically which is faster in tester? Run a microbench.

## §6. References list

| # | Title | URL | Retrieved |
|---|---|---|---|
| 1 | MQL5 Docs — iHigh / Timeseries and Indicators Access | https://www.mql5.com/en/docs/series/ihigh | 2026-05-11 |
| 2 | MQL5 Docs — CopyRates / Timeseries and Indicators Access | https://www.mql5.com/en/docs/series/copyrates | 2026-05-11 |
| 3 | MQL5 Forum — iHigh and iLow returns 0.0 [Solved] | https://www.mql5.com/en/forum/384591 | 2026-05-11 |
| 4 | (Search snippet) MQL5 Forum — Wrong value of current iOpen(PERIOD_D1) | https://www.mql5.com/en/forum/311826 | 2026-05-11 |
| 5 | (Search snippet) MQL5 Forum — Getting Previous Day High and Low on Hour and minute timeframe | https://www.mql5.com/en/forum/220592 | 2026-05-11 |
