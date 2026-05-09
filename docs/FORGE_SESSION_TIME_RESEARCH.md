# FORGE — Session & Time Tracking Research
**Date:** 2026-05-08 | **Status:** RESEARCH — action items at bottom

---

## 1. MQL5 Time Functions — Verified Differences

| Function | Source | Live | Strategy Tester |
|----------|--------|------|-----------------|
| `TimeCurrent()` | Last tick from broker server | Broker server time (e.g. GMT+2/+3) | Simulated server time ✓ |
| `TimeTradeServer()` | Client-estimated server time | Same as `TimeCurrent()` | Same as `TimeCurrent()` |
| `TimeLocal()` | PC clock | PC local time | Same as `TimeCurrent()` |
| `TimeGMT()` | UTC via PC clock + timezone | **Correct if PC timezone is right** | **BROKEN — collapses to `TimeCurrent()`** |
| `TimeGMTOffset()` | PC local → GMT offset (seconds) | Seconds difference: LocalTime - GMT | **Unreliable in tester** |

### Critical Finding: TimeGMT() is broken in Strategy Tester

Confirmed bug in MQL5 community (forum thread 375491, "timegmt() in tester is rubbish"). In the Strategy Tester, `TimeGMT()` returns the simulated server time rather than true UTC. The broker GMT offset is not applied.

**FORGE's current response:** The EA already acknowledges this at lines 3984–3986:
```
// Live: London/NY session window. Tester: skip — simulated TimeGMT() often sits outside 07–20 UTC
// for long stretches of a backtest (or the whole range), which zeroes out entries despite valid setups.
```
This is why `tester_session_filter` exists as a separate config and `ScalperTesterSessionOK()` is a looser filter — but it still calls `TimeGMT(dt)` internally, which may not advance correctly in tester.

---

## 2. FORGE Current Implementation

### Live session gate (`ScalperSessionOK()` — lines 2847–2858)
```mql5
bool ScalperSessionOK() {
    MqlDateTime dt;
    TimeGMT(dt);          // ← Uses TimeGMT() — correct in live IF PC timezone is set correctly
    int h = dt.hour;
    bool is_london = (h >= london_start && h < london_end);  // 07:00–20:00 UTC
    bool is_ny     = (h >= ny_start && h < ny_end);           // 07:00–20:00 UTC
    bool is_asian  = !is_london && !is_ny;
    ...
}
```

### Tester session gate (`ScalperTesterSessionOK()` — lines 2860–2884)
```mql5
bool ScalperTesterSessionOK() {
    TimeGMT(dt);          // ← BROKEN in tester — may not reflect correct UTC
    // ... compares current_session ("LONDON"/"NY") against tester_allowed_sessions
}
```

### Issues identified
1. **Tester**: `TimeGMT()` is unreliable → `ScalperTesterSessionOK()` may misidentify sessions in tester
2. **Live on VPS**: If VPS timezone is misconfigured, `TimeGMT()` returns wrong UTC → sessions misidentified
3. **No London/NY overlap detection**: Both windows set to 07–20 UTC — "LONDON" always wins when both start at 07:00, so "NY" label never fires
4. **No DST handling**: US DST shifts the London/NY overlap by 1 hour for ~3 weeks/year
5. **Session config has `NEW_YORK` vs EA label `NY`**: Fixed on 2026-05-08 ✅

---

## 3. Correct UTC Calculation Patterns

### Pattern A — Broker offset computed at init (recommended for VPS safety)
```mql5
// In OnInit():
static int g_broker_gmt_offset = 0;
// Compute offset: server time minus UTC = broker offset
// This is more reliable than TimeGMTOffset() (which is PC-local, not broker)
g_broker_gmt_offset = (int)MathRound((double)(TimeCurrent() - TimeGMT()) / 3600.0);
// Store as hours; recalculate weekly (DST shifts it by 1 hour twice a year)

// In OnTick() session check:
datetime utc_now = TimeCurrent() - (g_broker_gmt_offset * 3600);
MqlDateTime utc_dt;
TimeToStruct(utc_now, utc_dt);
int h = utc_dt.hour;
```

This is safe on VPS regardless of PC timezone configuration because it derives UTC from the broker server time directly.

### Pattern B — TimeGMT() with VPS guard (current FORGE approach, simpler)
```mql5
MqlDateTime dt;
TimeGMT(dt);  // Works on live if PC timezone correct; broken in tester
int h = dt.hour;
```

### Pattern C — amrali's TimeGMT tester library (full fix)
Open-source library (`mql5.com/en/code/48291`) that intercepts `TimeGMT()` in tester mode, computes broker UTC offset from tick data (XAUUSD reliably captures EU DST), and auto-adjusts for DST transitions. Requires including the library.

---

## 4. Correct Session Boundaries (UTC, Standard Time)

| Session | UTC Open | UTC Close | XAUUSD relevance |
|---------|---------|---------|-----------------|
| Asian/Tokyo | 00:00 | 09:00 | Low volume, thin spreads |
| Sydney | 22:00 (prev) | 07:00 | Minimal for XAU |
| **London** | **08:00** | **17:00** | High volume, directional |
| **New York** | **13:00** | **22:00** | High volume, directional |
| **London/NY Overlap** | **13:00** | **17:00** | **Highest liquidity for XAUUSD** |

**DST impact:** US clocks shift in March and November; UK shifts in late March and October. During the gap (~3 weeks/year), effective NY open is 14:00 UTC instead of 13:00, shrinking the overlap.

### Current FORGE windows (07:00–20:00 both)
- Too broad — includes Asian bleed hours (07:00–08:00)
- Misses late NY session (20:00–22:00) where some valid setups occur
- Both windows identical → "NY" label never assigned (London wins first)

---

## 5. Proposed Session Improvements

### Option A — Tighter distinct windows (breaking change to trade volume)
```json
"session_filter": {
    "london_start_utc": 8,
    "london_end_utc":   13,
    "ny_start_utc":     13,
    "ny_end_utc":       22
}
```
This would:
- Correctly label 08:00–13:00 = LONDON, 13:00–22:00 = NY, 00:00–08:00 = ASIAN
- Enable separate London vs NY behavior (e.g. tighter SL during NY)
- The `tester_allowed_sessions: "LONDON,NY"` fix is now meaningful (both labels fire)

Risk: Some hours currently in session (13:00–20:00 under "LONDON") would move to "NY" label. Any NY-specific config would apply. Run 18 first with current windows.

### Option B — Add broker GMT offset config (VPS safety fix, no window change)
```json
"safety": {
    "broker_gmt_offset_hours": 2
}
```
Use `TimeCurrent() - (broker_offset * 3600)` instead of `TimeGMT()` in session checks. Eliminates VPS timezone dependency. Small code change, no behavior change if offset is correct.

### Option C — Add overlap window detection
```json
"session_filter": {
    "overlap_start_utc": 13,
    "overlap_end_utc":   17
}
```
Identify the London/NY overlap as a distinct named session (`"OVERLAP"`) for trade quality gates (e.g. allow higher ADX threshold during overlap).

---

## 6. MqlDateTime — Verified Field Values

| Field | Values | Example |
|-------|--------|---------|
| `day_of_week` | 0=Sunday, 1=Monday, ..., 6=Saturday | Monday = 1 ✅ (FORGE code confirmed) |
| `hour` | 0–23 (UTC when using `TimeGMT()`) | 14 = 14:00 UTC |
| `day` | 1–31 | Calendar day of month |
| `mon` | 1–12 | Calendar month |

For Monday gap detection: `dt.day_of_week == 1 && dt.hour < 10` (first 3 hours of Monday London session) is the community standard buffer.

---

## 7. Action Items

| Priority | Action | Risk | Effort | Version |
|----------|--------|------|--------|---------|
| ✅ Done | Fix `NEW_YORK` → `NY` in config | Bug fix | Tiny | 2.7.5 |
| HIGH | Add `broker_gmt_offset_hours` config for VPS safety | Low | Small | 2.7.6 |
| HIGH | Implement Monday buffer gate (Part C of prompt) | Low | Small | 2.7.6 |
| MEDIUM | Separate London/NY windows (8–13 / 13–22) + run A/B vs current | Trade impact | Medium | 2.8.x |
| MEDIUM | Fix `ScalperTesterSessionOK()` to derive UTC from server time, not `TimeGMT()` | Tester accuracy | Medium | 2.8.x |
| LOW | Integrate amrali TimeGMT tester library | Correctness | Medium | 2.8.x |
| LOW | Add London/NY overlap window as named session | Enhancement | Small | 2.8.x |

---

*Last updated: 2026-05-08 — based on MQL5 official docs, forum threads 375491/427917, and FORGE.mq5 code audit.*
