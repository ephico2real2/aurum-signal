# FORGE 2.7.3 → Run 17 Plan
**Date:** 2026-05-08 | **Status:** READY TO RUN | **EA:** 2.7.3 | **Period:** Apr 14–May 7

---

## What Changed vs Run 16 (2.7.2)

| Change | Value | Effect |
|--------|-------|--------|
| `bb_breakout.adx_min` (BUY) | 25 → reverted **20** | BUY wins in 20-25 zone preserved (+$267 in Run 16) |
| `bb_breakout.adx_min_sell` (SELL) | new **25** | Blocks SELL breakouts at weak ADX; BUY unaffected |
| Tester ADX floor | `min(adx_min, 15)` → `adx_min` | Tester = live; eliminates G5018-class artifacts |
| ADX gate diagnostic log | new | `FORGE ADX gate: adx=X buy_min=Y sell_min=Z buy=PASS|BLOCKED sell=PASS|BLOCKED` per M5 bar |

**Run 16 final confirmed:** BUY **+$1,053** / SELL **-$490** net. SELL is net negative despite 71.9% win rate — average loss (-$72) overwhelms average win (+$21). `adx_min_sell=25` is a necessary first step but the Run 18 gate suite is essential to fix the SELL side.

**Rationale for BUY/SELL split:** Run 16 data showed the ADX 20-25 zone is asymmetric:
- BUY wins: +$164 (G5005 ADX 23.4) + +$103 (G5022 ADX 23.0) = **+$267**
- SELL wins: +$6.74 + $10.50 + $8.46 = **+$26** (small, 3 trades)

SELL entries in weak ADX are more error-prone (RSI floor bounces, fading moves). BUY momentum persists even at moderate ADX.

---

## Expected Run 17 vs Run 16 Delta

| Trade | ADX | Direction | Run 16 | At adx_min_sell=25 |
|-------|-----|-----------|--------|---------------------|
| G5005 (Apr 15 BUY) | 23.4 | BUY | WIN +$164.08 | **PRESERVED** (BUY floor=20) |
| G5022 (Apr 30 BUY) | 23.0 | BUY | WIN +$103.12 | **PRESERVED** (BUY floor=20) |
| G5013 (Apr 22 SELL) | 23.3 | SELL | WIN +$6.74 | BLOCKED (SELL floor=25) |
| G5014 (Apr 22 SELL) | 24.9 | SELL | WIN +$10.50 | BLOCKED (SELL floor=25) |
| G5021 (Apr 29 SELL) | 21.4 | SELL | WIN +$8.46 | BLOCKED (SELL floor=25) |
| G5018 (Apr 28 SELL) | 16.2 | SELL | LOSS -$237 (tester artifact) | BLOCKED ✅ |

Net expected: -$25.70 (3 small SELL wins blocked) vs +$267 BUY wins preserved = net improvement.

---

## Full SELL Loss Analysis from Run 16 — Three Distinct Categories

### Category A: RSI floor bounce (G5007, G5023) — ADX 25-30
- **G5007** (Apr 17, SELL ADX 26.8, RSI 39.5 rising from 35.2): -$38
- **G5023** (Apr 30, SELL ADX 28.8, RSI 36.1 after BUY rally): -$40
- **Pattern:** ADX falling at entry + RSI rising off the floor → fading SELL into a reversal
- **Fix:** RSI-declining gate (Priority 1 below)

### Category B: BB_BOUNCE against strong trend (G5009) — ADX > 40
- **G5009** (Apr 20, BB_BOUNCE SELL ADX 43.1): -$59
- **Pattern:** Counter-trend bounce against very strong momentum
- **Fix:** `bounce_adx_max: 40` (Priority 2 below)

### Category C: ADX spike from flat base (G960901 / G5024) — ADX 30-40
- **G5024** (May 4 17:10, SELL ADX 37.4, SL in 8 min): -$238
- **What happened:**
  - ADX was **13.1** at 16:25 (ranging/flat)
  - ADX spiked to **37.4** in 45 minutes (13→15→22→28→31→37)
  - At entry: price (4555.11) was 0.36 pts below BB lower (4555.47) → OUTSIDE band → full lot 0.08 fired
  - `sell_inside_band_lot_factor=0.25` did NOT apply — price was genuinely outside band at entry tick
  - Price reversed +15pts within 8 minutes, both legs SL'd at 4569.55
- **Root cause:** ADX "spike from flat" — rapid expansion from ADX < 15 (ranging) to 37 in one session created a genuine-looking BB breakdown with no lasting momentum. The ADX was too fresh/new to trust.
- **Why inside-band protection missed it:** The 0.25× lot factor activates when `mid > bb_lower` (price has pulled back inside). G5024's price was still below the band at entry — the protection is designed for pullback entries, not immediate reversals.
- **Fix:** ADX duration gate (Priority 3 below)

### Category D: Tester ADX floor artifact (G5018) — ADX < 20
- **G5018** (Apr 28 11:06, SELL ADX 16.2): -$237 (tester only)
- Already blocked in live at old `adx_min=20`. Fixed permanently by removing tester floor relaxation (done in 2.7.3 ✅)

---

## Fixes Deferred to Run 18 (implement after Run 17 completes)

All gates are **fully automated** using MQL5 built-in indicator handles — zero external tools. Prior-bar values are tracked in real-time by reading `CopyBuffer` with a bar offset against the existing initialized handles (`g_mtf[0].h_rsi` for RSI, `g_mtf[0].h_adx` for ADX). No pre-computation or third-party data needed.

---

### Priority 1 — RSI-declining SELL gate (auto-switching, internal tracking)
**Evidence:** G5007 (-$38) + G5023 (-$40) = -$78. Both entered SELL while RSI was rising bar-over-bar off the floor.

**How it tracks automatically:**
- Current bar RSI: `CopyBuffer(g_mtf[0].h_rsi, 0, 0, 1, buf)` → bar[0] — already computed as `m5_rsi`
- Prior bar RSI: `CopyBuffer(g_mtf[0].h_rsi, 0, 1, 1, buf)` → bar[1] — one bar back, fully internal
- Gate: if `m5_rsi > rsi_prev` (RSI rising) AND ADX < 35 → block SELL, journal `entry_quality_rsi_rising_sell`
- Auto-off in strong ADX (≥ 35): reuses existing `breakout_adx_sell_floor_threshold` — no new config threshold

**Config items needed:**
- `ScalperConfig` field: `bool breakout_require_rsi_declining_sell` (default `false`)
- Config key: `bb_breakout.require_rsi_declining_sell: false`
- Env: `FORGE_BREAKOUT_REQUIRE_RSI_DECLINING_SELL=0` (set to 1 for Run 18 activation)
- New journal gate reason: `entry_quality_rsi_rising_sell`
- New throttle global: `g_scalper_last_rsidecl_log_bar`

---

### Priority 2 — ADX duration gate — auto-tracks prior ADX, blocks spike-from-flat
**Evidence:** G5024/G960901 (-$238): ADX 13→37 in 45 min. Entry looked valid at ADX 37 but had no momentum history. Inside-band 0.25× lot missed it because price was 0.36pts outside the band at entry.

**How it tracks automatically:**
- ADX N bars ago: `CopyBuffer(g_mtf[0].h_adx, 0, N, 1, buf)` → bar[N] — fully internal, uses existing M5 ADX handle
- Default N=6 (6 × 5min = 30 min lookback)
- Gate: if ADX[6_bars_ago] < `adx_min_sell` (25) → current ADX reading is a spike from flat → block SELL, journal `entry_quality_adx_spike_sell`

**Validation from Run 16:**
- G5024 (17:10): ADX at bar[6] = 16:40 = **16.8** < 25 → BLOCKED ✅
- G5017 (valid SELL, ADX 50.3): ADX at bar[6] rising from 30+ → PASSES ✅

**Config items needed:**
- `ScalperConfig` field: `int breakout_adx_min_sell_lookback_bars` (default `6`)
- Config key: `bb_breakout.adx_min_sell_lookback_bars: 6`
- Env: `FORGE_BREAKOUT_ADX_MIN_SELL_LOOKBACK_BARS=6`
- New journal gate reason: `entry_quality_adx_spike_sell`
- New throttle global: `g_scalper_last_adxdur_log_bar`

---

### Priority 3 — `bounce_adx_max: 40` (config-only, no code)
**Evidence:** G5009 (-$59): BB_BOUNCE SELL at ADX 43.1. Field already exists in `ScalperConfig` and `ReadScalperConfig`.

**Config items needed:**
- `bb_bounce.bounce_adx_max: 40` in JSON/defaults
- Env: `FORGE_BOUNCE_ADX_MAX=40`
- Sync script mapping: `"FORGE_BOUNCE_ADX_MAX": ("bb_bounce", "bounce_adx_max", "float", 0.0, 99.0)`

---

### Priority 4 — Friday entry cutoff (auto via MqlDateTime.day_of_week)
**Rationale:** `sell_cutoff_utc=17` blocks all days. Friday-specific gate frees Mon-Thu evenings.

**How it tracks automatically:**
- `MqlDateTime.day_of_week` already populated by every `TimeGMT(dt)` call in the EA — no new variables
- `day_of_week == 5` = Friday; block when `dt.hour >= friday_cutoff_utc_hour`
- New journal gate reason: `session_off_friday`

**Config items needed:**
- `ScalperConfig` field: `int friday_cutoff_utc_hour` (default `16`)
- Config key: `safety.friday_cutoff_utc_hour: 16`
- Env: `FORGE_FRIDAY_CUTOFF_UTC_HOUR=16`

Defer until Run 17 data shows Mon-Thu evening entry profitability.

---

## Run 17 Monitoring Focus

1. **ADX gate log** — confirm `FORGE ADX gate: ... sell=BLOCKED` fires for SELL at ADX 20-25; BUY in same zone shows `buy=PASS`
2. **G5007/G5023 RSI pattern** — for each SELL loss, check prior-bar RSI (rising or falling). Builds calibration dataset for RSI-declining gate.
3. **G5024 ADX spike pattern** — for any SELL loss at ADX > 30, check ADX 6 bars before entry. If < 25, confirms Duration gate is needed.
4. **BUY 20-25 zone** — confirm G5005/G5022 equivalents are still taken (BUY floor=20 intact).

---

## Automated Tracking Summary — All Patterns Internally Trackable

All gates use existing initialized MQL5 handles — zero external tools, zero pre-computation.

| Pattern | What to track | Internal mechanism | Gate reason |
|---------|--------------|-------------------|-------------|
| RSI rising off floor (G5007, G5023) | Prior bar RSI | `CopyBuffer(g_mtf[0].h_rsi, 0, 1, 1, buf)` → bar[1] | `entry_quality_rsi_rising_sell` |
| ADX spike from flat (G5024) | ADX N bars ago | `CopyBuffer(g_mtf[0].h_adx, 0, 6, 1, buf)` → bar[6] | `entry_quality_adx_spike_sell` |
| Strong-trend bounce (G5009) | Current ADX vs ceiling | `m5_adx` already computed — compare to `bounce_adx_max` | existing bounce gate |
| Friday gap risk | Day of week | `MqlDateTime.day_of_week` — already populated by every `TimeGMT(dt)` call | `session_off_friday` |
| **BUY H1 counter-trend (G8, Monday)** | **H1 trend direction + ADX** | **`h1_trend_strength` already computed; `m5_adx` already computed; `dt.day_of_week` for Monday boost** | **`entry_quality_h1_counter_buy`** |

### Additional factors from loss review — also fully trackable internally

**G5008 (BUY Monday, ADX 26.4) — H1 trend alignment:**
- `adx_min=20` for BUY already covers the zone. Complementary check: was H1 trend reversing at entry?
- `h1_trend_strength` is already computed in FORGE — a BUY entry when `h1_trend_strength < 0` (H1 bearish) combined with weak ADX (20-28) is the higher-risk scenario
- No new handles needed — `h1_trend_strength` passed directly to the gate check
- Gate candidate: `entry_quality_h1_counter_buy` — block BUY when `h1_trend_strength < 0 && m5_adx < threshold`

**G5023/G5007 (RSI bounce) — spread as liquidity signal:**
- G5023 had spread=23.0 pts at entry — high spread indicates thin liquidity, higher false-breakout probability
- `spread` is already computed and journalled on every signal — no new tracking needed
- Gate candidate: `entry_quality_spread_sell` — block SELL when `spread > max_spread_sell_pts`
- Config: `bb_breakout.max_spread_sell_pts: 20` (or derived as `N × ATR` for adaptive threshold)
- Tracks automatically: `spread` variable already in scope at entry gate

**G5024 (ADX spike) — ATR expansion rate:**
- The ADX duration gate covers the primary failure. Complementary signal: ATR jump bar-over-bar
- If ATR expanded significantly in 1 bar, the move may be climactic (exhausted, about to reverse)
- `atr_prev = CopyBuffer(g_mtf[0].h_atr, 0, 1, 1, buf)` — bar[1], fully internal
- Gate candidate: block SELL when `m5_atr / atr_prev > atr_expansion_ratio_max` (e.g., 1.5×)
- Config: `bb_breakout.max_atr_expansion_ratio_sell: 1.5`

### Priority 5 (new) — Spread gate for SELL entries
**Evidence:** G5023 spread=23.0 at entry. High spread = low liquidity = false breakout risk.

**How it tracks automatically:**
- `spread` already computed before any gate check — zero new infrastructure
- Compare against configurable threshold (absolute pts or ratio of ATR)
- New journal gate reason: `entry_quality_spread_sell`

**Config items needed:**
- `ScalperConfig` field: `double breakout_max_spread_sell` (default `0` = disabled)
- Config key: `bb_breakout.max_spread_sell: 20`
- Env: `FORGE_BREAKOUT_MAX_SPREAD_SELL=20`

### Priority 6 (new) — ATR expansion rate gate
**Evidence:** G5024 — sharp price move in last bar correlated with immediate reversal.

**How it tracks automatically:**
- Prior bar ATR: `CopyBuffer(g_mtf[0].h_atr, 0, 1, 1, buf)` → bar[1], fully internal
- `m5_atr / atr_prev > ratio_max` → move is climactic → block SELL
- New journal gate reason: `entry_quality_atr_expansion_sell`

**Config items needed:**
- `ScalperConfig` field: `double breakout_max_atr_expansion_sell` (default `0` = disabled)
- Config key: `bb_breakout.max_atr_expansion_sell: 1.5`
- Env: `FORGE_BREAKOUT_MAX_ATR_EXPANSION_SELL=1.5`

---

### Priority 7 — BUY H1 counter-trend gate (BUY-specific, fully automated)
**Evidence:** G8 (Run 17, Apr 20 Monday): BUY @ 4802.96, ADX 26.4, RSI 66.1 → -$269.36 (3 legs). Monday morning false breakout — BUY entry at weak ADX into a potentially H1-bearish trend. G8 is the single largest loss in Run 17, accounting for most of the BUY delta vs Run 16 (-$314 total, of which G8 = -$269.36). The ADX-duration gate (Priority 2, Run 18) does not cover BUY entries — the gate is SELL-only. A dedicated BUY gate is needed.

**Root cause detail:**
- ADX 26.4: moderate — above the 20 BUY floor but not strong conviction
- Monday open: gap openings create false directional momentum on the first London bars
- H1 trend at entry: unknown but if `h1_trend_strength < 0` (H1 bearish), BUY is counter-trend
- Pattern: BUY breakout on M5 while H1 is still declining = fade trade masquerading as breakout

**How it tracks automatically:**
- `h1_trend_strength` is already computed in `CheckNativeScalperSetups()` via `CalcH1TrendStrength()` — available as a local variable at the BUY gate check
- `m5_adx` already computed — compare to configurable ADX threshold (weak-ADX zone)
- Day-of-week: `MqlDateTime.day_of_week` already populated via `TimeGMT(dt)` at function start — `dt.day_of_week == 1` = Monday
- No new handles, no new CopyBuffer calls required

**Gate logic (in BUY breakout path, before direction = "BUY"):**
```mq5
// BUY H1 counter-trend gate: block weak-ADX BUY when H1 trend is bearish
if(g_sc.breakout_require_h1_aligned_buy && m5_adx < g_sc.breakout_counter_buy_adx_threshold) {
    if(h1_trend_strength < 0) {
        datetime _h1ctbuy_bar = iTime(_Symbol, PERIOD_M5, 0);
        if(_h1ctbuy_bar != g_scalper_last_h1ctbuy_log_bar) {
            g_scalper_last_h1ctbuy_log_bar = _h1ctbuy_bar;
            JournalRecordSignal("SKIP","entry_quality_h1_counter_buy","BB_BREAKOUT","BUY",
               mid,spread,m5_atr,m5_rsi,m5_adx,...,h1_trend_strength,0);
        }
        // don't set direction = "BUY"
        goto skip_buy_entry;  // or use flag pattern matching existing BUY else block
    }
}
```

**Gate parameters:**
- `breakout_require_h1_aligned_buy`: enable/disable flag (default `false` — enabled when evidence warrants)
- `breakout_counter_buy_adx_threshold`: ADX ceiling for the counter-trend check (default `28` — covers the G8/G5022 ADX 20-28 zone)
- Auto-off at ADX ≥ threshold: strong-trend BUY (ADX > 28) doesn't require H1 alignment — momentum is self-evident

**Validation from Run 17 data:**
- G8 (Monday BUY ADX 26.4): H1 trend unknown — need to verify `h1_trend_strength` at Apr 20 10:20
- G5 (BUY ADX 23.4, Apr 15): was a WIN — if H1 was bullish, this would PASS the gate ✓
- G5022 (Run 16 BUY ADX 23.0, Apr 30): was a WIN +$103 — must ensure this passes (H1 bullish)

**Monday-specific enhancement (optional, layered on top):**
```mq5
// Additional Monday factor: tighten ADX threshold on Mondays
double counter_buy_adx_eff = g_sc.breakout_counter_buy_adx_threshold;
if(dt.day_of_week == 1)  // Monday
    counter_buy_adx_eff = MathMin(counter_buy_adx_eff + 5.0, 35.0);  // e.g. 28 → 33 on Mondays
```
This tightens the H1-counter-trend check on Mondays without requiring a separate Monday gate.

**Config items needed:**
- `ScalperConfig` field: `bool breakout_require_h1_aligned_buy` (default `false`)
- `ScalperConfig` field: `double breakout_counter_buy_adx_threshold` (default `28.0`)
- Config keys: `bb_breakout.require_h1_aligned_buy: 0`, `bb_breakout.counter_buy_adx_threshold: 28`
- Env: `FORGE_BREAKOUT_REQUIRE_H1_ALIGNED_BUY=1`, `FORGE_BREAKOUT_COUNTER_BUY_ADX_THRESHOLD=28`
- New journal gate reason: `entry_quality_h1_counter_buy`
- New throttle global: `g_scalper_last_h1ctbuy_log_bar`

**Suggested version:** FORGE 2.7.5 (Run 19 gate sprint — BUY-side quality)

**Risk of over-blocking:** G5 (ADX 23.4, BUY, WIN +$164 in R16) is in the same ADX zone. Only blocked if H1 is bearish. If H1 was bullish on Apr 15 (which is likely given the sustained BUY rally Apr 14-15), G5 would pass. The H1 alignment check is the discriminator — not just ADX alone.

---

## Run 17 Config Snapshot

```
adx_min (BUY):          20
adx_min_sell (SELL):    25
adx_min_sell_lookback:  N/A (not yet implemented)
max_reentry_atr_ext:    1.25
rsi_sell_floor:         33
rsi_sell_floor_weak_adx: 36
adx_sell_floor_threshold: 35
bounce_htf_bias:        STRICT
fixed_lot:              0.08
sell_inside_band_lot_factor: 0.25
```

*Last updated: 2026-05-08*
