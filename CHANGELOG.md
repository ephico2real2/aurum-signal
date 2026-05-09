# SIGNAL SYSTEM — CHANGELOG

## [System 1.9.5] — 2026-05-09 (FORGE 2.7.7 — Session cutoff · OsMA 4-quadrant gate · ADX tiers · SELL LIMIT cascade)

### Strategy basis — OsMA (Oscillator of a Moving Average) — MACD Histogram

OsMA is the difference between the MACD line and its signal line:

```
OsMA = MACD_line − Signal_line
     = (EMA_fast − EMA_slow) − SMA(MACD_line, signal_period)
```

In MT5, `iOsMA()` returns this as buffer 0 directly. The `iMACD()` indicator has only buffers
0 (MACD line) and 1 (signal line) — there is no buffer 2. The histogram you see drawn on the
chart in MT5 is actually the MACD line itself (buffer 0), not OsMA. OsMA requires either manual
subtraction or the dedicated `iOsMA()` handle.

#### MACD Histogram MC 4-quadrant framework (AK20 / traderak20@gmail.com, MQL5 #65050)

The MACD Histogram MC indicator classifies the histogram into four momentum states, each with a
distinct color. FORGE 2.7.7 adopts this framework for gate logic and DB diagnostics:

| Quadrant | Histogram | Direction | Color (MC) | SELL gate | BUY gate |
|----------|-----------|-----------|------------|-----------|----------|
| **Q0** | positive + rising | Strong bull momentum | LimeGreen | **BLOCK** | **PASS** |
| **Q1** | positive + falling | Bull momentum fading | Dark red | **BLOCK** | BLOCK |
| **Q2** | negative + falling | Strong bear momentum | Red | **PASS** ✓ | BLOCK |
| **Q3** | negative + rising | Bear momentum fading | Dark green | **BLOCK** | BLOCK |

**SELL entries are only allowed in Q2** — the histogram must be both negative (bearish bias) and
falling (momentum is accelerating downward). This is the one quadrant where a short scalp has
full MACD confirmation. Any weakening (Q3) or crossover (Q0/Q1) is a block.

**BUY entries are only allowed in Q0** — histogram positive and rising (bullish momentum
accelerating). Gate is `breakout_require_macd_buy`, **off by default** — experimental, enable
only when a longer backtest validates it doesn't over-filter valid BUY breakouts.

#### When to use OsMA in scalping

OsMA is most useful during **active, fast momentum** — exactly the condition FORGE targets:

- **Fast bull move (BUY gate):** OsMA positive and rising confirms EMA fast > EMA slow AND
  MACD is above its own signal line — double layer of bullish confirmation. Absent in choppy
  markets or fading rallies.

- **Fast bear move (SELL gate):** OsMA negative and falling confirms EMA fast < EMA slow
  (downtrend) AND momentum is accelerating lower (histogram expanding below zero). Stops
  the EA from selling into a bear exhaustion (Q3) where the move has already peaked.

**It is NOT a trend-entry indicator.** Do not use it to detect the start of a new trend — the
MACD lags by construction. Use it exclusively as a momentum confirmation for an existing
breakout signal already identified by BB + RSI + ADX.

**Parameters used: OsMA(3, 10, 16)**
- Fast EMA = 3: extremely responsive, designed for M5 scalp timing (not 12/26)
- Slow EMA = 10: short-horizon trend reference
- Signal SMA = 16: slightly longer smoothing to avoid tick noise on the histogram
- Source: arXiv:2206.12282 — RSI + MACD(3,10,16) dual gate = 84-86% win rate

#### MQL5 code — iOsMA single buffer read (the correct approach)

```mql5
// Single buffer, no subtraction needed — buffer 0 = MACD_line - Signal_line
double _hist[2];
if(CopyBuffer(g_h_osma_scalp, 0, 0, 2, _hist) == 2) {
   double _h0 = _hist[0];  // current bar OsMA value
   double _h1 = _hist[1];  // previous bar OsMA value

   // 4-quadrant classification:
   if(_h0 >= 0.0 && _h0 > _h1) // Q0: positive + rising → strong bull
   if(_h0 >= 0.0 && _h0 < _h1) // Q1: positive + falling → bull fading
   // _h0 < 0.0 && _h0 < _h1   // Q2: negative + falling → strong bear (SELL PASS)
   if(_h0 < 0.0 && _h0 > _h1)  // Q3: negative + rising → bear fading
}

// Initialise handle (once, in indicator refresh):
g_h_osma_scalp = iOsMA(_Symbol, PERIOD_M5, 3, 10, 16, PRICE_CLOSE);

// Wrong (iMACD buffer 2 does not exist — always returns -1):
// CopyBuffer(g_h_macd_scalp, 2, 0, 2, _hist);  ← DO NOT USE
```

#### Research sources

- arXiv:2206.12282 — RSI + MACD dual gate: 84-86% WR backtest
- MACD Histogram MC indicator by AK20 (MQL5 #65050, traderak20@gmail.com) — 4-quadrant logic
- MT5 official docs — iMACD has 2 buffers only (0=main, 1=signal); iOsMA buffer 0 = OsMA
- TradingView MACD MetaTrader Style (vrzDxjSE) — MT5 uses SMA signal, not EMA (OsMA result differs from TradingView standard MACD)

---

### Added

- **Session SELL cutoff (`session_ny_sell_cutoff_utc: 17`)** — blocks new SELL entries at or after 17:00 UTC. Post-17:00 UTC XAUUSD is lower liquidity, wider spreads, and prone to Asia-transition reversals. BUY entries continue. Gate reason: `entry_quality_session_sell_cutoff`. Config: `safety.session_ny_sell_cutoff_utc`, `session_london_sell_cutoff_utc`. Env: `SESSION_NY_SELL_CUTOFF_UTC`.
  - Run 25 validation: G5011 (17:10 UTC, -$238) + G5013 (18:25, -$83) both blocked. Net improvement: **+$321** vs Run 23.

- **OsMA(3,10,16) SELL gate (`breakout_require_macd_sell: 1`)** — replaces the broken iMACD buffer-2 approach. Uses `iOsMA()` handle; buffer 0 = MACD−Signal directly. Applies 4-quadrant classification: SELL only passes in Q2 (histogram negative AND falling). Gate reasons in DB: `entry_quality_macd_q0_bull_rising`, `entry_quality_macd_q1_bull_fading`, `entry_quality_macd_q3_bear_fading`. The histogram value is logged in `SIGNALS.macd_histogram` for every gate-fire event for post-run diagnostics.

- **Bug fix — iMACD buffer 2 (2.7.7c)** — Previous implementation read `CopyBuffer(g_h_macd_scalp, 2, ...)` which always returns -1 (buffer 2 does not exist in iMACD). The gate was silently fully disabled. Fixed by replacing iMACD with `iOsMA` and reading buffer 0. Also fixed the TAKEN signal log which had the same buffer-2 bug.

- **OsMA BUY gate (`breakout_require_macd_buy: 0`, off by default)** — symmetric gate for BUY entries, passes only in Q0 (histogram positive AND rising). Enable with `FORGE_BREAKOUT_REQUIRE_MACD_BUY=1` to test on a longer backtest once SELL gate is validated. Journal reasons: `entry_quality_macd_q1_bull_fading`, `entry_quality_macd_q2_bear_str`, `entry_quality_macd_q3_bear_fading`.

- **ADX-tiered lot factors + BLOCK** (`breakout_adx_lot_*`) — Protects SELL entries at extended ADX levels. Uses M15 ADX (less lag than M5 per OpoFinance/Trade2Win). Three outcomes:
  | M15 ADX | Factor | Lot at 0.08 base |
  |---------|--------|-----------------|
  | < 35 | 1.0× (full) | 0.08 |
  | 35–44 | 0.25× | 0.02 |
  | 45–54 | 0.125× | **0.01 (broker min)** |
  | ≥ 55 | **BLOCK** | — |
  Gate reason: `entry_quality_adx_extreme_sell`. Config: `breakout_adx_lot_mid_threshold`, `breakout_adx_lot_high_threshold`, `breakout_adx_lot_factor_mid`, `breakout_adx_lot_factor_high`, `breakout_adx_sell_block_threshold`.

- **Cardwell SELL LIMIT cascade (`breakout_sell_limit_enabled: 1`)** — After a crash SELL market order, places a pending SELL LIMIT at `bid + ATR × 0.4` to catch the Cardwell Bear Resistance bounce-and-fail re-short. Lot: `0.125× base` (1/8th, danger-zone sizing). Expiry: 6 M5 bars via `ORDER_TIME_SPECIFIED`. Cancelled automatically in `OnTradeTransaction` when the parent market SELL hits SL. State tracked in `g_sell_limit_stack[2]` (up to 2 slots). Config: `breakout_sell_limit_enabled`, `breakout_sell_limit_atr_mult`, `breakout_sell_limit_lot_factor`, `breakout_sell_limit_expiry_bars`. Env: `FORGE_BREAKOUT_SELL_LIMIT_*`.

- **Three new SIGNALS columns** (`macd_histogram`, `m15_adx`, `lot_factor`) — `JournalRecordSignal()` extended with 3 default parameters (backwards-compatible). TAKEN records populate all three. MACD gate SKIP records populate `macd_histogram` with the actual OsMA value at gate-fire time. SCRIBE `aurum_intelligence.db` migrated with `ALTER TABLE ADD COLUMN`.

### Gate execution order — SELL breakout path (full, as of 2.7.7)

1. BB condition: `prev_close < BB_lower − buffer` + M5/M15/H1/H4 bear alignment
2. **Cardwell Bear Resistance ceiling**: `m5_rsi < rsi_sell_max (60)` ← 2.7.6
3. **Session SELL cutoff**: `hour < session_ny_sell_cutoff_utc (17)` ← **2.7.7**
4. **ADX extreme block**: `m15_adx < 55` ← **2.7.7**
5. ADX min SELL: `m5_adx ≥ 25` ← 2.7.3
6. H1+H4 crash bypass check: `h1_bear && h4_bear && rsi > 20` ← 2.7.6
7. Two-tier RSI floor (base 30 + weak-ADX 36) — skipped on crash bypass
8. ADX spike-from-flat (6-bar lookback) — skipped on crash bypass
9. RSI-declining gate (rising RSI, auto-off ADX ≥ 40) ← 2.7.4/2.7.5
10. **OsMA Q2 gate**: histogram negative AND falling ← **2.7.7**
11. News RSI tighten ← 2.7.6
12. Direction = SELL → `CheckEntryQuality()` → Gate −1 (news BLOCK)

### Gate execution order — BUY breakout path (full, as of 2.7.7)

1. BB condition: `prev_close > BB_upper + buffer` + M5/M15/H1/H4 bull alignment
2. **Cardwell Bull Support floor**: `m5_rsi > rsi_buy_min (40)` ← 2.7.6
3. RSI buy ceiling: `m5_rsi < rsi_buy_ceil (70)` ← 2.6.7
4. H1 DI directional gate (Wilder DI+/DI−) ← 2.7.5
5. **OsMA Q0 gate (optional, off by default)**: histogram positive AND rising ← **2.7.7**
6. News RSI tighten ← 2.7.6
7. Direction = BUY → `CheckEntryQuality()` → Gate −1 (news BLOCK)

### How to use

- **OsMA SELL gate**: `FORGE_BREAKOUT_REQUIRE_MACD_SELL=1` (on). Set `0` to disable. DB column `macd_histogram` shows OsMA value at gate-fire; quadrant is visible in `gate_reason`. In a fast bear move, Q2 fires when momentum is accelerating — check `gate_reason LIKE 'macd_q%'` in SIGNALS to audit.
- **OsMA BUY gate**: `FORGE_BREAKOUT_REQUIRE_MACD_BUY=0` (off). Enable with `=1` to require Q0 (strong bull) for BUY entries. Start with a 2-week tester run before enabling in live — BUY breakouts are already filtered by RSI+H1+DI and adding OsMA may over-filter in ranging conditions.
- **OsMA params**: `FORGE_BREAKOUT_MACD_FAST=3`, `FORGE_BREAKOUT_MACD_SLOW=10`, `FORGE_BREAKOUT_MACD_SIGNAL=16`. These are now live in the sync pipeline (`make scalper-env-sync` picks them up).
- **ADX tiers**: set `FORGE_BREAKOUT_ADX_SELL_BLOCK_THRESHOLD=55` (default). Lower to 50 to add protection at high ADX without needing the mid/high tiers. Mid/high thresholds can be tuned via `FORGE_BREAKOUT_ADX_LOT_MID_THRESHOLD` / `FORGE_BREAKOUT_ADX_LOT_HIGH_THRESHOLD`.
- **SELL LIMIT**: `FORGE_BREAKOUT_SELL_LIMIT_ENABLED=1` (on). Disable with `=0` if the bounce pattern isn't active in the current regime. Monitor `SIGNALS.gate_reason = 'SELL_LIMIT_PLACED'` in the DB.

---

## [System 1.9.4] — 2026-05-09 (FORGE 2.7.6 — Cardwell RSI zones + H1+H4 crash SELL bypass)

### Strategy basis — Andrew Cardwell RSI Zone Theory

Andrew Cardwell (CMT curriculum, the most cited developer of Wilder's original RSI work) defines
two distinct RSI trading ranges depending on market regime:

| Regime | RSI Range | Entry zone | Entry signal |
|--------|-----------|------------|--------------|
| **Uptrend** | 40–80 | Bull Support: RSI **40** | Long re-entry on RSI dip to 40 |
| **Downtrend** | 20–60 | Bear Resistance: RSI **60** | Short re-entry on RSI bounce to 60 |

The standard 70/30 Wilder thresholds apply only in ranging markets. In trending markets, the range
shifts and the midline roles invert. Below RSI 20 in a downtrend is exhaustion territory — not a
sell signal. RSI 60 rejection in a downtrend is the ideal second short entry (sell-the-bounce).

Sources:
- [TradingView — Cardwell RSI Zones indicator (v6JlR98g)](https://www.tradingview.com/script/v6JlR98g/)
- [Alchemy Markets — RSI Education](https://alchemymarkets.com/education/indicators/relative-strength-index/)
- [Andrew Cardwell — Using the RSI (Scribd)](https://www.scribd.com/document/489489408/Andrew-Cardwell-Using-the-RSI)
- [StockCharts ChartSchool — RSI](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/relative-strength-index-rsi)

### Added

- **`rsi_sell_max`: 50 → 60 (Cardwell Bear Resistance ceiling)** — SELL breakout now fires when RSI is up to 60, not just below 50. In a confirmed downtrend (H1+H4 bear), RSI 50–60 is the Bear Resistance zone — the ideal re-short after price bounces from the initial crash low. The previous `rsi_sell_max=50` was blocking every Cardwell Bear Resistance entry. Config: `bb_breakout.rsi_sell_max`, env: (config-only). EA default updated to 60.

- **`rsi_buy_min`: 50 → 40 (Cardwell Bull Support floor)** — BUY breakout now fires when RSI is as low as 40, not just above 50. In a confirmed uptrend (H1+H4 bull), RSI 40–50 is the Bull Support zone — the ideal re-buy after a dip within a rally. The previous `rsi_buy_min=50` was blocking every Cardwell Bull Support entry. Config: `bb_breakout.rsi_buy_min`, env: (config-only). EA default updated to 40.

- **H1+H4 crash SELL bypass (`breakout_h1h4_crash_sell: true`)** — When H1 EMA20 < EMA50 AND H4 EMA20 < EMA50 (confirmed multi-TF bear), the `rsi_sell_floor` and `adx_spike_sell` gates are bypassed. Allows crash-day SELL entries at RSI 20–30 (early crash momentum) while standard gates remain active for non-crash conditions. `h1_bear && h4_bear` is the crash detector — no new indicator. Config: `bb_breakout.h1h4_crash_sell`, env: `FORGE_BREAKOUT_H1H4_CRASH_SELL`.

- **Cardwell RSI 20 crash floor (`breakout_h1h4_crash_sell_rsi_min: 20`)** — Hard RSI lower bound applied even when crash bypass is active. Cardwell defines RSI 20 as the extreme-oversold floor in a downtrend (below this = exhaustion, not momentum). Prevents G5002-class losses (RSI 16, ADX 47, crash bypass active → SL hit). RSI 20–30 entries allowed; RSI < 20 blocked. Config: `bb_breakout.h1h4_crash_sell_rsi_min`, env: `FORGE_BREAKOUT_H1H4_CRASH_SELL_RSI_MIN`.

- **`max_open_same_direction`: 1 → 2** — Allows two concurrent groups in the same direction. Enables the Cardwell two-entry pattern: initial crash SELL (RSI 20–30) + Bear Resistance re-short (RSI 50–60 on bounce), both open simultaneously. Config: `safety.max_open_same_direction`.

- **`rsi_sell_adx_floor` per-bar throttle** (`g_scalper_last_rsisellfloor_log_bar`) — fixes tick-spam: previously fired on every tick within the same M5 bar (30+ rows at 15:55 in Run 21). Now logs once per bar, consistent with `adx_min_sell`, `adx_spike_sell`, `rsi_rising_sell`, `h1_di_buy`.

- **News filter linear RSI slide** — TIGHTEN zone now slides proportionally from baseline (70/33) to max-tighten (65/38) as proximity increases, instead of jumping immediately to max at the tighten threshold. Formula: `slide = (p − tighten_pct) / (block_pct − tighten_pct)`.

- **News filter config-robust baselines** — `ScalperNewsCheck()` resets now use `g_sc.breakout_rsi_buy_ceil` / `g_sc.breakout_rsi_sell_floor` instead of hardcoded 70.0/33.0. Prevents spurious news-tighten skips if RSI floors are changed in config.

- **BB_BREAKOUT_RETEST news tighten coverage** — Confirmed retest entries now check `entry_quality_news_rsi_tighten` before committing `direction`. Previously bypassed because retest set `direction` before the BB_BREAKOUT block (which contains the tighten check). Fix: added BUY/SELL guard in the retest confirmation path with `g_nf_eff_rsi_*` already primed by the pre-BB call.

- **`tighten_pct < block_pct` cross-validation** — After JSON parsing of both fields, enforces `tighten_pct < block_pct`. If inverted, silently resets `tighten_pct = block_pct * 0.5`. Prevents TIGHTEN zone collapse or unreachable BLOCK on bad config.

### Gate execution order — SELL breakout path (full, as of 2.7.6)

1. BB condition: `prev_close < BB_lower − buffer` + M5/M15/H1/H4 bear alignment
2. **Cardwell Bear Resistance ceiling**: `m5_rsi < rsi_sell_max (60)` ← **2.7.6**
3. ADX min SELL: `m5_adx ≥ 25`
4. H1+H4 crash bypass check: `h1_bear && h4_bear && rsi > 20` ← **2.7.6**
5. Two-tier RSI floor (base 30 + weak-ADX 36) — skipped on crash bypass
6. ADX spike-from-flat (6-bar lookback) — skipped on crash bypass
7. RSI-declining gate (rising RSI bar-over-bar) ← 2.7.4
8. News RSI tighten — last line of defence ← 2.7.6
9. Direction = SELL → `CheckEntryQuality()` → Gate −1 (news BLOCK)

### Gate execution order — BUY breakout path (full, as of 2.7.6)

1. BB condition: `prev_close > BB_upper + buffer` + M5/M15/H1/H4 bull alignment
2. **Cardwell Bull Support floor**: `m5_rsi > rsi_buy_min (40)` ← **2.7.6**
3. RSI buy ceiling: `m5_rsi < rsi_buy_ceil (70)` ← 2.6.7
4. H1 DI directional gate (Wilder DI+/DI−) ← 2.7.5
5. News RSI tighten ← 2.7.6
6. Direction = BUY → `CheckEntryQuality()` → Gate −1 (news BLOCK)

### Reference documentation

- `docs/FORGE_NEWS_FILTER_GATE_FLOW.md` — complete signal gate flow ASCII diagram
- `docs/FORGE_NEWS_FILTER_REVIEW.md` — Codex gate review + expert triage
- `docs/FORGE_APR29_SELL_REJECTION_ANALYSIS.md` — crash SELL rejection root-cause + options

---

## [System 1.9.3] — 2026-05-08 (FORGE 2.7.6 — Native MT5 Calendar news filter)

### Added

- **Native news filter** — queries MT5 Economic Calendar (`CalendarValueHistory` + `CalendarEventById`) natively inside FORGE. No SENTINEL dependency, no WebRequest. Works in Strategy Tester and on VPS.
- **Per-impact windows**: separate before/after minutes for LOW (5/5), MEDIUM (10/15), HIGH (20/30).
- **Keyword overrides** (`news_filter_special`): `"KEYWORD:before,after+KW2:b2,a2"` substring match. Example: `"Non-Farm:30,60+FOMC:40,45+CPI:50,55"`.
- **Multi-currency**: `"ALL"` expands to all 9 MT5 calendar currencies; any comma/space combo accepted. Default `"USD,EUR,GBP"` for XAUUSD — no dedicated XAU calendar symbol exists.
- **Sliding proximity rule**: 3 zones — ALLOW / TIGHTEN (RSI slides 70→65 BUY, 33→38 SELL) / BLOCK. Symmetric pre and post event. Tighten journals as `entry_quality_news_rsi_tighten`.
- **Post-news hard floor** (`news_filter_hard_floor_min=5`): absolute block for first 5 min post-event (chaos zone).
- **Input override**: `input bool NewsFilterInputsOverride = false` + `input bool NewsFilterEnabled = true`. Active input wins over config JSON on every reload. Enabled by default.
- **23 tests** in `tests/api/test_forge_news_filter.py` — config structure, env mappings, source checks, logic invariants.

### Fixed (Codex review)

- **CRITICAL**: Proximity used midpoint approximation for event_time — wrong with asymmetric windows (e.g. FOMC 40/45). Fixed: store exact `g_nf_event_time` in refresh.
- **HIGH**: Keyword `before` values excluded from query horizon — 40-min keyword override could be missed. Fixed: horizon uses max of all keyword and impact before values.
- **HIGH**: Effective RSI globals could be stale across tick boundaries. Fixed: `ScalperNewsUpdateEffectiveThresholds()` helper called at gate -1 and before BB setup selection.
- **MEDIUM**: Back-to-back events missed after cached window expired. Fixed: force refresh on expiry.
- **MEDIUM**: Silent failure when calendar data unavailable in tester. Fixed: `PrintFormat` warning.

---

## [System 1.9.2] — 2026-05-08 (FORGE 2.7.5 — H1 DI+/DI- BUY quality gate)

### Added

- **H1 DI directional gate** (`bb_breakout.require_h1_di_buy: 1`) — blocks BUY breakout when H1 DI- > DI+ at weak M5 ADX. Implements Wilder's original directional confirmation: ADX strength (buffer 0) confirms trend intensity, but DI+/DI- (buffers 1 and 2) confirms direction. A BUY entry is counter-directional by definition when H1 DI- dominates, regardless of M5 price action. Targets G8-class losses: Monday Apr 20 BUY at ADX 26.4 into a H1-bearish environment (-$269.36). At strong M5 ADX ≥ 28 (`counter_buy_adx_threshold`), gate is inactive — strong momentum self-confirms direction.
- **Zero new indicator handles**: reads DI+ (buffer 1) and DI- (buffer 2) from the existing `g_h_adx = iADX(_Symbol, PERIOD_H1, 14)` handle. Uses `h1_bias_shift` (0 in tester, 1 in live) consistent with all other H1 reads in `CheckNativeScalperSetups()`.
- **New journal gate reason**: `entry_quality_h1_di_buy`
- **New throttle global**: `g_scalper_last_h1dibuy_log_bar`
- **Config**: `bb_breakout.require_h1_di_buy: 1`, `bb_breakout.counter_buy_adx_threshold: 28`
- **Env**: `FORGE_BREAKOUT_REQUIRE_H1_DI_BUY=1`, `FORGE_BREAKOUT_COUNTER_BUY_ADX_THRESHOLD=28`

### Industry context

MQL5 community consensus: using ADX without DI+/DI- is the most common EA design flaw. ADX above 25 confirms a trend exists — DI+/DI- confirms which direction. The `iADX` indicator in MQL5 exposes all three via separate buffers on the same handle. The gate auto-offs at strong ADX (≥ 28) where momentum is self-evident, matching the calibrated threshold from the h1_counter_buy analysis.

---

## [System 1.9.1] — 2026-05-08 (FORGE 2.7.4 — RSI-declining + ADX-duration gates + bounce_adx_max=40)

### Fixed

- **`bounce_adx_max`: 50 → 40** — blocks BB_BOUNCE SELL when ADX > 40. Targets G5009-class losses (BB_BOUNCE SELL at ADX 43.1, -$59.28 in Run 17). High-ADX counter-trend bounces fail at elevated momentum — strong directional moves resist mean-reversion. Config-only change, no code. Env key: `FORGE_BOUNCE_ADX_MAX`.

### Added

- **ADX duration gate** (`bb_breakout.adx_min_sell_lookback_bars: 6`) — blocks SELL breakout when ADX was below `adx_min_sell` (25) exactly N M5 bars ago (default N=6 = 30 min lookback). Targets G5024-class losses: ADX spiked 13→37 in 45 min, creating a valid-looking breakout with no momentum history; price reversed +15pts in 8 min. The gate reads `CopyBuffer(g_mtf[0].h_adx, 0, 6, 1, buf)` against the existing M5 ADX handle — zero new handles. Journal gate reason: `entry_quality_adx_spike_sell`. Config: `bb_breakout.adx_min_sell_lookback_bars`, env: `FORGE_BREAKOUT_ADX_MIN_SELL_LOOKBACK_BARS`. Set `0` to disable.
- **RSI-declining gate** (`bb_breakout.require_rsi_declining_sell: 1`) — blocks SELL breakout when RSI is rising bar-over-bar (current bar RSI > prior bar RSI). Auto-disabled when ADX ≥ `adx_sell_floor_threshold` (35) — strong-trend SELL entries don't require RSI momentum confirmation. Targets G5007-class losses (SELL at RSI 39.5 rising from 35.2, -$38.14; RSI bouncing off the floor signals fading SELL momentum at entry). Reads `CopyBuffer(g_mtf[0].h_rsi, 0, 1, 1, buf)` — one buffer call against existing M5 RSI handle. Journal gate reason: `entry_quality_rsi_rising_sell`. Config: `bb_breakout.require_rsi_declining_sell` (bool01), env: `FORGE_BREAKOUT_REQUIRE_RSI_DECLINING_SELL`. Set `0` to disable.
- **Session-start visibility log** — fires once each time the EA transitions from session_off to active. Logs: current ADX, ADX 30 min ago (6 bars via `CopyBuffer(..., 0, 6, 1, buf)`), RSI, and BB expansion state. Enables "armed context" entries — the same market structure pre-read that RSI divergence analysis recommends doing manually before the session opens. Example: `FORGE SESSION START: hour=7UTC adx=28.4 adx_30min_ago=19.1 rsi=44.2 bb=EXPANDING (width 12.40→14.83)`. Global `g_scalper_prev_session_blocked` tracks the previous tick's session state.
- **New globals**: `g_scalper_last_adxdur_log_bar`, `g_scalper_last_rsidecl_log_bar`, `g_scalper_prev_session_blocked` — M5-bar throttles for new gate journals and session-state tracking.
- **`rsi_decl_sell_adx_threshold: 28`** — separate ADX threshold for `rsi_rising_sell` auto-off, independent of `adx_sell_floor_threshold` (35, used for RSI two-tier floor). At 28, the gate blocks G7-class (ADX 26.8 < 28) while passing G17/G18/G19-class wins (ADX 28-35). Previous implementation incorrectly shared the 35 threshold, which blocked all three of those winning entries. Field: `breakout_rsi_decl_sell_adx_threshold`, env: `FORGE_BREAKOUT_RSI_DECL_SELL_ADX_THRESHOLD`. Default: `28.0`.

### Gate execution order (SELL breakout path)
1. ADX min SELL (≥ 25) ← 2.7.3
2. Two-tier RSI floor (absolute + weak-ADX stricter floor) ← 2.6.8
3. **ADX duration gate** (30min lookback, spike-from-flat) ← **2.7.4**
4. **RSI-declining gate** (rising RSI, auto-off ADX ≥ 35) ← **2.7.4**
5. Direction = SELL

### How to use

- ADX duration gate: `FORGE_BREAKOUT_ADX_MIN_SELL_LOOKBACK_BARS=6` (active). Set `0` to disable. Increase to 12 (60min) if spike-from-flat patterns persist across longer timeframes.
- RSI-declining gate: `FORGE_BREAKOUT_REQUIRE_RSI_DECLINING_SELL=1` (active). Auto-switches off when ADX ≥ 35 — no separate config toggle needed for strong-trend SELLs.
- bounce_adx_max: `FORGE_BOUNCE_ADX_MAX=40`. Previous default was 50 (effectively permissive). 40 blocks ADX 40-50 bounces while allowing ADX 20-40 mean-reversion which has better historical success.

---

## [System 1.9.0] — 2026-05-08 (FORGE 2.7.3 — Split BUY/SELL ADX floors + tester parity + diagnostic log)

### Fixed

- **Tester ADX floor removed**: `breakout_adx_min_eff = MathMin(g_sc.breakout_adx_min, 15.0)` → `= g_sc.breakout_adx_min`. Tester now enforces same ADX threshold as live for both BUY and SELL — eliminates G5018-class artifacts where entries at ADX 15-20 fired in tester but were blocked in live.

### Added

- **`bb_breakout.adx_min_sell: 25`** — separate, stricter ADX floor for SELL-only breakouts. BUY remains at `adx_min=20`. Run 16 data showed BUY entries in the ADX 20-25 zone were highly profitable (+$267: G5005 +$164, G5022 +$103) while SELL entries in the same zone were marginal (+$26 across 3 trades). SELL breakouts in weak ADX are more error-prone (RSI floor bounces, fading moves). New fields: `ScalperConfig.breakout_adx_min_sell`, config key `bb_breakout.adx_min_sell`, env key `FORGE_BREAKOUT_ADX_MIN_SELL`.
- **ADX gate diagnostic log** — once per M5 bar: `FORGE ADX gate: adx=X buy_min=Y sell_min=Z buy=PASS|BLOCKED sell=PASS|BLOCKED | rsi=... price=... atr=...`. Throttled by `g_scalper_last_adxgate_log_bar`. Zero DB overhead.
- **New global**: `g_scalper_last_adxgate_log_bar` — M5-bar throttle for ADX gate diagnostic.

### How to use

- BUY breakouts: blocked when ADX < `adx_min` (default 20). Set `FORGE_BREAKOUT_ADX_MIN` to adjust.
- SELL breakouts: blocked when ADX < `adx_min_sell` (default 25). Set `FORGE_BREAKOUT_ADX_MIN_SELL` to adjust.
- Experts log shows both thresholds every M5 bar — check `sell=BLOCKED` to confirm SELL gate active.
- G5018-class tester artifacts (ADX 15-20 SELL entries) are now impossible in both environments.

---

## [System 1.8.9] — 2026-05-08 (FORGE 2.7.1 — Fix 7C: ATR price extension re-entry gate)

### Added

- **Fix 7C — ATR price extension gate** (`ea/FORGE.mq5`): Blocks same-direction BUY/SELL re-entry when price has moved more than `max_reentry_atr_ext × ATR` from the first group's entry price in the current session. Targets Category F losses (late-stage extended-move re-entry). Gate reason: `entry_quality_atr_ext`. Default `0.0` (disabled); set to `1.5` for Run 15 test.
- **New globals**: `g_first_buy_entry_price`, `g_first_sell_entry_price` — session-scoped anchors, reset on UTC day change and session change.
- **New config key**: `bb_breakout.max_reentry_atr_ext` (float, 0.0–10.0). Wired to `.env` via `FORGE_BREAKOUT_MAX_REENTRY_ATR_EXT`.
- **Tests**: `tests/api/test_forge_7c_atr_ext.py` — 12 tests covering gate disabled, anchor set/no-update, within/at/over limit (BUY + SELL), session reset, zero-ATR guard, wiring checks. All passing.

---

## [System 1.8.8] — 2026-05-08 (FORGE 2.6.10 — correct default inputs: InputMode + ScalperMode)

### Fixed

- **`InputMode` default retained as `"WATCH"`**: Master trading gate. When `g_mode == "WATCH"`, line 739 `WriteTickData(); return;` exits the entire OnTick/OnTimer handler before any scalper code is reached. Prevents accidental live trading on attach — must be set to "SCALPER" explicitly.
- **`ScalperMode` default `"NONE" → "DUAL"`**: Safe to default DUAL because `InputMode=WATCH` is the master gate with two independent checks: (1) `if(g_mode == "WATCH") return;` at line 739 exits before scalper; (2) `if(g_scalper_mode != "NONE" && g_mode != "WATCH" && ...)` at line 744 has explicit WATCH exclusion. EA itself logs: *"native entries need ScalperMode≠NONE and InputMode≠WATCH"*. Setting DUAL by default eliminates one manual step after every recompile with no safety risk.
- **`lot_inputs_override_eff = false` retained by design**: With `NativeScalperInputsOverrideLotSizing=false` and `lot_sizing_source="AUTO"`, config.json remains the authority for all lot engine settings (leg count, staged intervals, etc.). `ScalperLot` input only overrides `fixed_lot` via `ApplyScalperLotInputOverrides()` — this is the intended architecture (retain config.json).

---

## [System 1.8.7] — 2026-05-08 (FORGE 2.6.9 — lot input override + VP POC warmup gate)

### Fixed

- **`ScalperLot` input ignored after JSON load**: `ApplyScalperLotInputOverrides()` never wrote `ScalperLot` back to `g_sc.lot_fixed`, so the config JSON value (0.02) always won even when the input was set to 0.08. Fix: added `if(ScalperLot > 0.0) g_sc.lot_fixed = ScalperLot;` in `ApplyScalperLotInputOverrides()` — same override-or-pass-through pattern used by `SellInsideBandLotFactor`. Changed `ScalperLot` default from `0.01` → `0.0` (sentinel: 0 = use JSON `fixed_lot`; >0 = override JSON). Updated `InitScalperConfig` to seed `lot_fixed` from `ScalperLot` when set, otherwise from the JSON fallback (0.02).
- **VP POC uninit warmup gap**: No check existed that `g_poc_price > 0` before allowing first entry. If `ComputeVolumeProfile()` silently failed at `OnInit` (e.g. `CopyHigh` returned fewer than `vp_lookback` bars), the EA could compute TP targets against a zero POC. Added explicit check `if(g_poc_price <= 0.0) { reason_out = "vp_poc_uninit"; return false; }` in `ForgeNativeScalperWarmupOk()` after the PSAR probe, before the M5 rollover count.

### How to use
- Set `ScalperLot = 0.08` in MT5 Inputs → applies as base lot per leg, overrides `fixed_lot` in JSON
- Leave `ScalperLot = 0.0` → EA uses `scalper_config.json` `lot_sizing.fixed_lot` (unchanged behavior for existing configs)
- `SellInsideBandLotFactor = 0.25` in MT5 Inputs → already worked; now consistent with `ScalperLot` semantics

---

## [System 1.8.6] — 2026-05-08 (FORGE 2.6.8 — hotfix: session_off per-tick journal flood)

### Fixed

- **`session_off` per-tick DB flood (ea/FORGE.mq5 line 3943)**: `JournalRecordSignal("SKIP","session_off",...)` was called on every `OnTick()` during off-hours (Asian session + post-NY), bypassing the existing M5-bar throttle on the adjacent `PrintFormat`. Moved the journal write inside the `if(m5bar != g_scalper_last_sesswarn_log_bar)` guard so it fires at most once per M5 bar. Impact: in Run 12 initial 1.5-day window, 272,238 useless zero-indicator records were written and DB hit 60MB — projects to ~1.5GB for a full 24-day run, causing tester slowdown. Fix reduces off-hours journal output to ≤96 records/day (one per M5 bar during off-hours).

---

## [System 1.8.5] — 2026-05-08 (FORGE 2.6.8 — loss reduction: ADX floor, RSI sell floor, STRICT bounce, inside-band half-lot)

### Phase A — Config changes only

- **`bb_breakout.adx_min`: `14 → 20`** — blocks false breakouts in ranging tape; ADX<20 = no directional trend by Wilder's definition; caused 3 Category-A losses in Run 11 (~$100).
- **`bb_breakout.rsi_sell_floor`: `30 → 33`** — closes 5× float-boundary violation at RSI=30.0 and blocks oversold-exhaustion SELL entries (RSI 30–33 = move near-spent, bounce risk elevated). Journals `entry_quality_rsi_sell_floor`.
- **`bb_bounce.bounce_htf_bias`: `BALANCED → STRICT`** — blocks BB_BOUNCE SELL when H1 OR M15 is bullish; blocks BB_BOUNCE BUY when H1 OR M15 is bearish. Safe during sell-offs: H1 bearish → NOT bullish → SELL bounce still fires. Saves ~$45 from Run 11 Category-C losses.

### Phase B — EA changes (ea/FORGE.mq5)

- **ADX-conditioned RSI sell floor (Fix 5)**: two-tier floor — absolute `rsi_sell_floor=33` always applies; when `ADX < adx_sell_floor_threshold (35)` the stricter `rsi_sell_floor_weak_adx=36` applies. Weak-trend SELL entries with low RSI are the highest-risk exhaustion trades. New gate reason: **`entry_quality_rsi_sell_adx_floor`**. Config: `bb_breakout.adx_sell_floor_threshold`, `bb_breakout.rsi_sell_floor_weak_adx`.
- **Half-lot inside-band SELL (Fix 7)**: after a BB_BREAKOUT SELL fires, if current mid > BB_LOWER (price has bounced back inside the band), lot size is multiplied by `bb_breakout.sell_inside_band_lot_factor (0.5)`. Confirmed breakout (mid ≤ BB_LOWER) uses full lot. Reduces exposure on fading breakouts. Logs "FORGE SCALPER: SELL inside band — lot factor=…".
- **Struct `ScalperConfig`** — 3 new fields: `breakout_adx_sell_floor_threshold`, `breakout_rsi_sell_floor_weak_adx`, `breakout_sell_inside_band_lot_factor`.
- **`InitScalperConfig`** — updated defaults: `rsi_sell_floor=33`, plus new Phase B field defaults.
- **`ReadScalperConfig`** — parses all 3 new fields from `bb_breakout` JSON.
- **Version 2.6.8** (`FORGE_VERSION`, `#property version`).

### Changed (config + tooling)

- **`config/scalper_config.defaults.json`**, **`config/scalper_config.json`** — all Phase A+B keys.
- **`scripts/sync_scalper_config_from_env.py`** — `FORGE_BREAKOUT_ADX_SELL_FLOOR_THRESHOLD`, `FORGE_BREAKOUT_RSI_SELL_FLOOR_WEAK_ADX`, `FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR`.

### Tests

- **`tests/api/test_forge_268_gates.py`** — 52 unit tests covering: config value assertions, Phase B key presence/ranges, gate boundary logic (adx_min, rsi floor, ADX-conditioned floor, inside-band lot factor, STRICT bounce modes), sell-off scenario pass/block, sync script env coverage.

---

## [System 1.8.4] — 2026-05-08 (FORGE 2.6.7 — RSI exhaustion gates + bounce ADX tester fix)

### Added (ea/FORGE.mq5)

- **`bb_breakout.rsi_buy_ceil`** (default **`70`**) — before SL/TP calculation and retest state machine, skip BB_BREAKOUT **BUY** when M5 RSI ≥ ceiling; journal **`SKIP`** **`entry_quality_rsi_buy_ceil`**. Blocked the May 1 cluster (RSI 74.9–83.6) and Apr 17 BUY exhaustion losses from Run 10.
- **`bb_breakout.rsi_sell_floor`** (default **`30`**) — skip BB_BREAKOUT **SELL** when M5 RSI ≤ floor; journal **`SKIP`** **`entry_quality_rsi_sell_floor`**. Blocked 6 confirmed SL hits (Apr 27–May 1, RSI 16–29) from Run 10.
- Both gates apply to the immediate-entry path **and** the retest state machine path (`breakout_use_retest`).
- **Version** **2.6.7** (`FORGE_VERSION`, `#property version`).

### Changed (ea/FORGE.mq5)

- Struct **`ScalperConfig`** — two new fields: **`breakout_rsi_buy_ceil`**, **`breakout_rsi_sell_floor`**.
- **`InitScalperConfig`** — defaults 70.0 / 30.0.
- **`ReadScalperConfig`** bb_breakout section — parses **`rsi_buy_ceil`** / **`rsi_sell_floor`** from `bb_breakout` JSON object.

### Changed (config + tooling)

- **`config/scalper_config.defaults.json`**, **`config/scalper_config.json`**:
  - **`bb_breakout.rsi_buy_ceil: 70`**, **`bb_breakout.rsi_sell_floor: 30`** (new keys).
  - **`bb_bounce.adx_max`**: `38` → `50` — aligns tester and live cap at a single value.
  - **`bb_bounce.bounce_respect_adx_max_in_tester`**: `0` → `1` — tester no longer relaxes the ADX cap to 99; bounce entries above ADX 50 are now blocked in backtests. Closed the Run 10 May 1 09:35 ADX=62 anti-trend entry.
- **`scripts/sync_scalper_config_from_env.py`** — **`FORGE_BREAKOUT_RSI_BUY_CEIL`** (50–100), **`FORGE_BREAKOUT_RSI_SELL_FLOOR`** (0–50).

### Documentation

- **`docs/FORGE_TRADING_RULES.md`** — new §§ "BB_BREAKOUT RSI exhaustion gates" and "BB_BOUNCE ADX cap — tester enforcement".
- **`docs/FORGE_JOURNAL_SQL.md`**, **`docs/DATA_CONTRACT.md`** — added **`entry_quality_rsi_buy_ceil`** and **`entry_quality_rsi_sell_floor`** to the `gate_reason` enum.

---

## [System 1.8.3] — 2026-05-08 (FORGE 2.6.6 — same-direction group cap)

### Added (ea/FORGE.mq5)

- **`safety.max_open_same_direction`** (default **1**, **`0`** = no cap) — before other entry-quality checks, skip when **`g_groups`** already has at least that many open groups in the proposed direction; journal **`SKIP`** **`entry_quality_direction_cap`**. **`ScalperOpenGroupCountByDirection`** uses the in-memory group ledger (no extra MT5 API scan).
- **Version** **2.6.6** (`FORGE_VERSION`, `#property version`).

### Changed (config + tooling)

- **`config/scalper_config.defaults.json`**, generated **`config/scalper_config.json`** — **`safety.max_open_same_direction`**.
- **`scripts/sync_scalper_config_from_env.py`** — **`FORGE_MAX_OPEN_SAME_DIRECTION`**.

### Documentation

- **`docs/FORGE_TRADING_RULES.md`**, **`docs/FORGE_JOURNAL_SQL.md`**, **`docs/DATA_CONTRACT.md`**, **`SKILL.md`**, **`SOUL.md`**, **`.env.example`** — cap and **`entry_quality_direction_cap`**.

---

## [System 1.8.2] — 2026-05-07 (FORGE 2.6.5 — native entry quality gate)

### Added (ea/FORGE.mq5)

- **M5 Entry Quality Gate** (`CheckEntryQuality`) — runs after a native scalp direction is chosen and before R:R / execution:
  - **`safety.min_entry_atr`** — skip when M5 ATR is below floor (default **3.5**); journal **`entry_quality_atr`**.
  - **`safety.entry_quality_bars`** (default **3**) — average candle **body/range** ratio vs **`min_body_ratio`** (default **0.40**); journal **`entry_quality_body`**.
  - **`safety.min_directional_bars`** (default **2**) — minimum completed M5 bars agreeing with trade direction; journal **`entry_quality_direction`**.
  - **`safety.require_bb_expansion`** (default **on**) — reject when BB width contracts vs prior bar (~**5%** threshold); journal **`entry_quality_bb_contraction`**.
- **Version** **2.6.5** (`FORGE_VERSION`, `#property version`).

### Changed (config + tooling)

- **`config/scalper_config.defaults.json`** — new **`safety.*`** keys above; regenerate with **`make scalper-env-sync`**.
- **`scripts/sync_scalper_config_from_env.py`** — **`.env`** overrides: **`FORGE_MIN_ENTRY_ATR`**, **`FORGE_ENTRY_QUALITY_BARS`**, **`FORGE_MIN_BODY_RATIO`**, **`FORGE_MIN_DIRECTIONAL_BARS`**, **`FORGE_REQUIRE_BB_EXPANSION`**.
- **`.env.example`** — documents entry-quality overrides.

### Documentation

- **`docs/FORGE_TRADING_RULES.md`**, **`docs/FORGE_JOURNAL_SQL.md`**, **`docs/DATA_CONTRACT.md`** (`forge_signals.gate_reason`), **`SKILL.md`** §8, **`SOUL.md`** — operator and AURUM context for the gate and journal reasons.

---

## [System 1.8.1] — 2026-05-07 (AURUM journal contract + BRIDGE tester gate)

### Changed (BRIDGE — `python/bridge.py`)

- **Tester journal sync to SCRIBE is off by default.** Strategy-tester SQLite files (`FORGE_journal_*_tester.db`) are **ML training data** and should be queried **in place** (agent `MQL5/Files`) so backtest history does not inflate or distort **`forge_signals`** / **`forge_journal_trades`** in **`aurum_intelligence.db`**. BRIDGE still discovers tester paths but **skips** `sync_forge_journal` / `sync_forge_journal_trades` unless **`BRIDGE_SYNC_TESTER_JOURNAL=1`** (`true`/`yes`/`on`). **Live** journals are unchanged.

### Changed (SCRIBE — `python/scribe.py`)

- **`forge_journal_trades`** — added **`run_id`** (default `0`). **Unique key** is now **`(deal_ticket, journal_source, run_id)`** so the same deal ticket can appear once per FORGE tester run without collision. Startup migration recreates the table atomically when the old **`UNIQUE(deal_ticket, journal_source)`** schema is detected.
- **`sync_forge_journal` / `sync_forge_journal_trades`** — propagate **`run_id`** from journal **`SIGNALS`** / **`TRADES`** when present (v2 journals); **`forge_signals`** gains **`run_id`** via additive **`ALTER TABLE`** when missing.

### Fixed (ea/FORGE.mq5)

- **Journal `TRADES` uniqueness** — old schema used **`deal_ticket INTEGER UNIQUE`**, which drops duplicate deals across tester runs. **`CREATE TABLE`** now uses **`UNIQUE(deal_ticket, run_id)`** with **`synced`** / **`run_id`** columns on create. **`JournalInit`** detects legacy **`deal_ticket INTEGER UNIQUE`** via **`sqlite_master`** and migrates with **`ALTER RENAME` → copy → drop** inside a transaction.

### Changed (ops / docs)

- **`scripts/diagnose_forge_journal.py`** — **`per_run`** breakdown in each journal summary (signal counts, top skips, optional TRADES stats per **`run_id`**).
- **`docs/FORGE_BRIDGE.md`** — §11 documents live vs tester journal sync and **`BRIDGE_SYNC_TESTER_JOURNAL`**.
- **`docs/DATA_CONTRACT.md`** — FORGE mirror tables: **`run_id`**, unique keys, tester sync default.
- **`docs/SCRIBE_QUERY_EXAMPLES.md`**, **`docs/FORGE_TESTER_JOURNAL_QUERIES.md`** — queries grouped by **`run_id`** for tester P&amp;L.
- **`.env.example`** — documents **`BRIDGE_SYNC_TESTER_JOURNAL`**.
- **`README.md`** — journal prompt paths under **`docs/prompts/`**; note on tester DB vs AURUM and optional re-enable flag.

### Added (tests)

- **`tests/api/test_bridge_tester_journal_sync.py`** — default skips tester DB sync; **`BRIDGE_SYNC_TESTER_JOURNAL=1`** restores behaviour.

---

## [System 1.8.0] — 2026-05-07 (FORGE 2.5.1)

### Fixed (ea/FORGE.mq5) — backtest stabilisation + logical error sprint

- **`WriteBrokerInfo()` hardcoded version** — `forge_version` was hardcoded as `"1.6.19"` instead of using the `FORGE_VERSION` constant. `broker_info.json` now always reports the actual running build version.
- **`ManageStagedNativeLegs()` guard asymmetry** — early-return guard only checked `staged_entry_enabled` but the opening path (`CheckNativeScalperSetups`) used `staged_entry_enabled || native_force_staged_scale_in`. Guard updated to match: staged legs now add correctly even when only `native_force_staged_scale_in=1` is set.
- **`WriteModeStatus()` missing fields** — `mode_status.json` now emits `scalper_mode`, `warmup_ok`, and `warmup_reason` so the operator can remotely confirm both mode inputs and warmup state without MT5 Experts tab access.
- **`InitScalperConfig()` defaults too strict** — `high_vol_apply_in_tester` and `high_vol_disable_bounce` were hardcoded `true` (matching the deployed JSON). Changed to `false` so the fail-safe (config unreadable) does not silently block tester trades.
- **iMACD buffer-2 probe permanently failing** (`ForgeNativeScalperWarmupOk`) — The warmup function probed `CopyBuffer(h_macd, 2, ...)` (MACD histogram). MT5's built-in `iMACD` only exposes buffer `0` (MACD main) and buffer `1` (signal); buffer `2` does not exist and `CopyBuffer` always returns `-1`. This caused warmup to permanently fail with reason `m5_macd_buf` on every tick, producing zero TAKEN for the entire backtest. The probe was removed for both MTF (M5/M15/M30) and H1 MACD handles. MACD is only used for `market_data.json` display (`WriteMTFBlock`) which already handles `CopyBuffer` failure gracefully as `0`.
- **Warmup bar-count check blocks fast-start** (`ForgeNativeScalperWarmupOk`) — When `ScalperTesterWarmupM5Bars=0` the operator intends "fire as soon as indicators are readable", but the old code still enforced `Bars() ≥ 70` and `SERIES_SYNCHRONIZED` checks on all timeframes before reaching the `CopyBuffer` probes. Added `do_bar_checks = !in_tester || (ScalperTesterWarmupM5Bars > 0)` gate: bar-count and sync proxy checks are now skipped in tester when `WarmupM5Bars=0`, leaving only the `CopyBuffer` readiness probes as the warmup gate.

### Added (ea/FORGE.mq5)

- **Warmup state observability** — globals `g_warmup_last_reason` (string) and `g_warmup_last_ok` (bool) track the latest warmup outcome. `WriteModeStatus()` exposes them in `mode_status.json`; the warmup failure branch in `CheckNativeScalperSetups()` now journals one `SKIP|warmup_<reason>` row per M5 bar so warmup blockers are visible in SQLite without MT5 Experts access.
- **`TESTER_RUNS` warmup inputs** (`JournalInit`) — `warmup_m5_bars` and `warmup_seconds` columns added to `TESTER_RUNS` so each tester run is traceable (which warmup setting produced which results).

### Changed (config/scalper_config.defaults.json + generated JSON)

- **Tester gate relaxations** — Three `scalper_config` flags that were blocking bounces in the tester were changed to `0` (relaxed) in `scalper_config.defaults.json` and propagated via `make scalper-env-sync`:
  - `bb_bounce.bounce_respect_adx_max_in_tester: 1 → 0` (EA uses ADX cap 99 for bounces in tester)
  - `bb_bounce.bounce_respect_h1_filter_in_tester: 1 → 0` (H1 direction filter skipped in tester)
  - `safety.high_vol_apply_in_tester: 1 → 0` (high-vol guard disabled in tester)

### Added (docs)

- **`docs/FORGE_BACKTEST_DIAGNOSTIC_COMMANDS.md`** — 11 numbered Python commands for remotely verifying warmup, mode, scalper_config gates, journal signal flow, TESTER_RUNS history, rr_too_low geometry, AURUM DB, and make targets. Includes warmup blocker reference table and Inputs checklist.

---

## [System 1.7.7] — 2026-05-06 (FORGE 2.4.6)

### Changed
- **Documentation:** **`docs/SCALPER_CONFIG_PIPELINE.md`** describes **`scalper_config.defaults.json`** → **`sync_scalper_config_from_env.py`** → **`scalper_config.json`**. Updated **`README.md`**, **`docs/WARP_FORGE_VERIFY_PROMPT.md`**, **`docs/FORGE_BRIDGE.md`**, **`docs/FORGE_TRADING_RULES.md`**, **`Makefile`** help text, **`.env.example`**, and **`sync_scalper_config_from_env.py`** module docstring so operators edit **defaults** (or mapped **`.env`** keys), not the generated JSON.
- **`VERSION` / `#property version` / `FORGE_VERSION` / `scalper_config.json`**: **2.4.5 → 2.4.6** (MQL5 **`2.46`**) so MT5 recognises the new build and logs / `market_data.json` show the updated `forge_version`.

---

## [System 1.7.6] — 2026-05-06 (scalper config 2.4.6)

### Changed
- **`config/scalper_config.json` — higher native scalper trade frequency** (hot-reload / `make forge-refresh` as usual): **`high_vol_adx_min`** 28→**40**, **`high_vol_trend_strength_min`** 0.6→**0.82**, **`high_vol_disable_bounce`** 1→**0** (stops hard-blocking BB bounces whenever `high_vol_trend` is true). **`bb_bounce`**: **`adx_max`** 35→**38**, **`rsi_buy_max`**/**`rsi_sell_min`** widened toward 50, **`bb_proximity_pct`** 25→**28**, **`bounce_require_bar0_confirm`** 0. **`bb_breakout.adx_min`** 20→**18**. **`safety`**: **`loss_cooldown_sec`** 120→**90**, **`direction_cooldown_bars`** 3→**2**. Spread / open-groups / rejection-candle / min SL unchanged. See **`docs/FORGE_TRADING_RULES.md` §7** for rollback guidance.

---

## [System 1.7.5] — 2026-05-06 (FORGE 2.4.5)

### Added
- **Per-session skip flags** (`ea/FORGE.mq5`, `config/scalper_config.json`): `skip_london`, `skip_ny`, `skip_asian` — each independently gates that session's trades. Hot-reloaded via `scalper_config.json`; all default to `0` (off, 24h trading unchanged). To skip London: set `"skip_london": 1` in `scalper_config.json` and run `make forge-compile`.
- **`ScalperSessionOK()`** updated to classify the current hour as London/NY/Asian and check the corresponding skip flag before allowing entry. Existing session-hour bounds (`london_start_utc`, `london_end_utc`, etc.) still define the classification window.

---

## [System 1.7.4] — 2026-05-06 (FORGE 2.4.4)

### Changed
- **Session filter disabled** (`config/scalper_config.json`): `london_start_utc=0`, `london_end_utc=24`, `ny_start_utc=0`, `ny_end_utc=24`, `skip_asian=false` — FORGE now evaluates setups 24 h/day. Previously London (07–12) + NY (12–24) only; Asian session was blocked entirely. Hot-reloaded via `scalper_config.json`; no live-session impact from `tester_session_filter` (remains 0).
- **FORGE VERSION bumped `2.4.3 → 2.4.4`** to force MT5 to recognise and reload the new binary.

---

## [System 1.7.3] — 2026-05-06

### Fixed (FORGE ADX — trade blocking)
- **ADX hysteresis disabled** (`ea/FORGE.mq5` line 1707): `adx_hysteresis_enabled` default changed `true → false`. ADX 25–33 is routine XAUUSD — the gate locked `g_adx_trend_regime=true` continuously, suppressing all BB bounce entries on both live and tester. Live journal confirmed 500 consecutive `no_setup` rows (ADX range 25.91–33.28, avg 29.5); tester journal showed 2.2M rows with zero `TAKEN`. Thresholds `adx_trend_enter=35.0` / `adx_trend_exit=28.0` retained in code for future re-enablement via `.env` / hot-reload if needed.

### Fixed
- **`forge_signals` idempotency** (`python/scribe.py`): added existing-row guard keyed on `(forge_id, time, symbol, journal_source)` before each INSERT — prevents duplicate signals if source `synced` flag is reset while BRIDGE is running.
- **Concurrency race — tester sync duplicates**: concurrent BRIDGE + manual terminal sync caused 500 duplicate rows (`forge_id` 65001–65500 each inserted twice). Deduplicated via `DELETE … WHERE rowid NOT IN (SELECT MIN(rowid) …)`; confirmed 0 dups post-fix. Root cause: application-level guard alone is insufficient under concurrent writers — see TODO below.

### Changed
- **`sync_forge_journal` / `sync_forge_journal_trades`** (`python/scribe.py`): batch limit is now a configurable `batch_size: int = 500` parameter (was hardcoded `LIMIT 500`). Default unchanged; `bridge.py` callers unaffected.
- **Tester journal backlog — skipped intentionally**: `FORGE_journal_XAUUSD_tester.db` (503 MB, ~2.2M rows) backlog marked `synced=1` without syncing to SCRIBE. All rows were `SKIP|no_setup` or `SKIP|rr_too_low` with zero `TAKEN` outcomes — pre-spam-fix noise with no ML value. SCRIBE tester total held at ~102,000 rows. Fresh tester runs sync cleanly going forward.
- **DB permissions**: `python/data/aurum_intelligence.db` temporarily `chmod 666` during sandbox sync; restored to `644`.

### Added
- **Focused offline tests** (`tests/services/test_scribe_forge_journal.py`): `test_scribe_db_path_resolution_rules`, `test_forge_journal_sync_tags_source_and_is_idempotent`, `test_forge_journal_sync_keeps_live_and_tester_sources_separate` — all pass, no network/MT5 required.
- **`make test-journal`** (Makefile): runs focused journal test suite via `$(PYTHON)`.

### TODO
- Add `UNIQUE INDEX ON forge_signals(forge_id, time, symbol, journal_source)` to enforce idempotency at the DB layer and eliminate the concurrency race between BRIDGE and any manual sync.

---

## [System 1.7.2] — 2026-05-06
### Added
- **SCRIBE `forge_journal_trades`** — deal-level rows mirrored from FORGE journal **`TRADES`** (History deals with FORGE magic range). Incremental sync via **`synced`** on `TRADES` (`python/scribe.py`). Tagged with **`journal_source`** (`live` \| `tester`).
- **`scripts/diagnose_forge_journal.py`** + **`make journal-diagnose`** — JSON health report: per-path `SIGNALS` / `TRADES` / `TESTER_RUNS` counts, top skip reasons, SCRIBE `forge_*` totals.

### Changed
- **SCRIBE DB path**: `SCRIBE_DB` defaults to **`python/data/aurum_intelligence.db`** relative to the **repo root** (was effectively under `python/` only; `.env` value `data/aurum_intelligence.db` still maps to the same file). Removed unused **`data/aurum_intelligence.db`** at repo root; watch/verify scripts and dashboard dep map now reference the canonical path only.
- **BRIDGE journal discovery** (`python/bridge.py`): search root now includes **`Program Files/MetaTrader 5`** (recursive `FORGE_journal_*.db`) so **Strategy Tester Agent** paths (e.g. `Tester/Agent-*/MQL5/Files/`) are found — tester journals sync to SCRIBE while BRIDGE runs.
- **BRIDGE** calls **`sync_forge_journal_trades`** alongside **`sync_forge_journal`** every 60s per discovered DB.
- **Journal diagnose UX**: when no FORGE journal DBs are discovered, `scripts/diagnose_forge_journal.py` now emits a human-readable stderr note while keeping JSON on stdout and exit status 0.
- **Journal sync return semantics**: `Scribe.sync_forge_journal()` now returns processed source rows, including duplicate rows marked synced after the SCRIBE idempotency guard; use SCRIBE table counts for inserted-row/idempotency assertions.

### Operations
- **Tester journal backlog gate**: before any bulk tester sync, run `make journal-diagnose`, count unsynced tester `SIGNALS` directly, snapshot SCRIBE `forge_signals` by `journal_source`, and confirm duplicate audits for `(forge_id,time,symbol,journal_source)` and `(deal_ticket,journal_source)` are zero. On 2026-05-06 the sync remains gated pending operator decision; no bulk sync was triggered by this review pass.

### Documentation
- **`README.md`**, **`docs/SCRIBE_QUERY_EXAMPLES.md`**, **`schemas/scribe_query_examples.json`**, **`docs/DATA_CONTRACT.md`**, **`docs/FORGE_JOURNAL_ML_PROMPT.md`** — consolidated ML data guidance (SCRIBE as primary; raw journal optional).
- **`docs/FORGE_JOURNAL_SQL.md`** — SQL cookbook for **skipped** / **TAKEN** journal rows (`forge_signals` + raw `SIGNALS`); linked from README and SCRIBE query examples.

## [2.4.3] — 2026-05-06
### Fixed
- **Journal spam**: `no_setup` and **`rr_too_low`** `SIGNALS` rows were written **every tick** when the condition persisted (millions of redundant rows, unusable for ML). Now **at most one row per M5 bar** for each (aligned with throttled `no_setup` logging).
- **`JournalImportTrades()`** (`ea/FORGE.mq5`): replaced prepared-statement `INSERT` with **`DatabaseExecute`** + SQL text (same class of Strategy Tester reliability issue as `SIGNALS`). **`TRADES.synced`** column + index for SCRIBE incremental import (idempotent `ALTER TABLE` on init).
- **Execution failures**: if all legs fail to open (`opened <= 0`), journal records **`SKIP` / `execution_failed`** (was silent).

## [System 1.7.0] — 2026-05-06
### Changed
- **Versioning overhaul**: introduced `SYSTEM_VERSION` file for Python services (separate from FORGE `VERSION`). `bridge.py` and `athena_api.py` now read version from file at startup — no more hardcoded version strings.
- Updated `SOUL.md` — FORGE v2.4.1 features: SL quality rules, native indicators (VWAP, Fibonacci, RSI divergence, PSAR), signal journal, dynamic leg count 1–30.
- Updated `SKILL.md` §8 — full native scalper documentation: SL layers, `.env` hot-reload keys, indicator catalog, trade frequency tuning.
- Updated `README.md` — version header, SCRIBE table count (14), FORGE v2.4.1 feature summary, two-file versioning docs.

## [System 1.7.1] — 2026-05-06
### Added
- **`docs/FORGE_JOURNAL_ML_PROMPT.md`** — implementation blueprint for journal-based **missed-setup analysis** (MFE/MAE, gate accuracy), optional **scikit-learn setup scorer** training (walk-forward validation), and future **AUTO_SCALPER** / **AEGIS** integration. References MQL5 articles 19065/18985/14910 and practical XAUUSD ML patterns.
- **SCRIBE `forge_signals.journal_source`** — column (default `live`) with auto-migration; tags rows synced from live (`FORGE_journal_<sym>.db`) vs Strategy Tester (`FORGE_journal_<sym>_tester.db`) journals (`python/scribe.py`).

### Changed
- **BRIDGE journal sync** (`python/bridge.py`): resolves **both** live Common-Files and local tester journal paths (same discovery rules as MT5/Wine layout), calls `sync_forge_journal(..., source="live"|"tester")` per file.
- **Drawdown guard vs Strategy Tester** (`python/bridge.py`): `_check_drawdown()` returns early when `market_data` reports `strategy_tester` — avoids false WATCH transitions when tester virtual balance differs from live peak equity. One-shot log + HERALD notice when tester mode is detected.
- **Operational visibility** (`python/bridge.py`, `python/athena_api.py`): `strategy_tester` written to `status.json` and exposed on **`GET /api/live`** so ATHENA shows tester runs distinctly from live.

### Documentation
- Updated **`README.md`**, **`SOUL.md`**, **`SKILL.md`** — FORGE **v2.4.2**, journal tester/live split, `journal_source`, tester drawdown bypass, link to journal ML prompt.

## [2.4.2] — 2026-05-06
### Fixed
- **Signal journal in Strategy Tester** (`ea/FORGE.mq5`):
  - When `MQL_TESTER` is active, journal DB is **`FORGE_journal_<SYMBOL>_tester.db`** under the terminal’s **local** `MQL5/Files` tree (writable in the tester sandbox), not Common Files — recovered skipped/taken rows that previously never persisted in backtests.
  - **`SIGNALS` inserts** use **`DatabaseExecute`** with formatted SQL (MT5 tester proved unreliable for prepared-statement + `DatabaseRead` on `INSERT` in some builds).
  - **Skip coverage:** `no_setup` and **`rr_too_low`** paths now call `JournalRecordSignal()` so high-volume skip reasons appear in the DB and sync to SCRIBE.

### Added
- **`TESTER_RUNS`** table in the tester journal DB — one metadata row per backtest run (start time, symbol, balance, `FORGE_VERSION`, scalper mode string).

## [2.4.1] — 2026-05-06
### Fixed
- **SL placement quality overhaul** (`ea/FORGE.mq5`):
  - `FindStructuralSL()` was selecting the **tightest** OB zone (nearest to entry), overriding ATR-based SL with dangerously close stops (e.g., 4.2 pts when ATR = 10.6). Fixed: structural SL can now only **widen** the stop (further from entry), never tighten it.
  - `bounce_sl_atr_mult` / `breakout_sl_atr_mult` were never parsed from `scalper_config.json` — stuck at hardcoded defaults (1.2/1.5). Added JSON parsing from `bb_bounce` and `bb_breakout` sections.
  - Added `min_sl_atr_mult` floor (default 0.8): SL can never be closer than 0.8×ATR from entry, regardless of structural SL. Applies to both bounce and breakout entries.
  - Added per-trade SL diagnostic logging (`FORGE SL CALC`) showing entry, SL, distance, ATR, multiplier, and OB zone count.

### Changed
- **Trade frequency tuning** (`config/scalper_config.json`):
  - `max_trades_per_session`: 3 → 100 (effectively uncapped — scalper trades every valid setup)
  - `max_open_groups`: 2 → 4 (more concurrent groups)
  - `loss_cooldown_sec`: 300 → 120 (2 min recovery for scalper pace)
  - `direction_cooldown_bars`: 6 → 3 (15 min instead of 30 min before opposite direction)
  - `bb_proximity_pct`: 20 → 25 (wider entry zone near BB bands)
  - `adx_max`: 30 → 35 (bounces in slightly trendier markets)
  - `rsi_buy_max`: 45 → 48, `rsi_sell_min`: 55 → 52 (wider RSI window)
  - `bounce_min_candle_score`: 1 → 0 (other filters provide sufficient confirmation)
- **Lot sizing cap** raised from 20 to 30 legs across all EA code paths.
- Removed dead `mode` and `risk_pct` fields from `lot_sizing` config.
- New `.env` overrides: `FORGE_MIN_SL_ATR_MULT`, `FORGE_BOUNCE_SL_ATR_MULT`, `FORGE_BREAKOUT_SL_ATR_MULT`.

## [2.4.0] — 2026-05-06
### Added
- **Native SQLite signal journal** (`ea/FORGE.mq5`, `config/scalper_config.json`, `.env.example`, `scripts/sync_scalper_config_from_env.py`, `python/scribe.py`, `python/bridge.py`):
  - Ref: [MQL5 Article 22009 — "Algorithmic Trading Without the Routine: Quick Trade Analysis in MetaTrader 5 with SQLite"](https://www.mql5.com/en/articles/22009)
  - FORGE now writes a local SQLite database (`FORGE_journal_XAUUSD.db`) in MT5 Common Files, recording **every setup evaluation** — both taken trades and skipped signals — with full indicator context at the moment of decision.
  - **SIGNALS table**: Records time, symbol, setup_type, direction, outcome (TAKEN/SKIP), gate_reason, and a snapshot of price, spread, ATR, RSI, ADX, Bollinger Bands, POC, VWAP, Fibonacci, RSI divergence, PSAR state, candle score, H1 trend, regime, session, and magic number. Includes `synced` column for Python pipeline integration.
  - **TRADES table**: Periodically imports MT5 deal history (configurable depth) using `HistorySelect()`/`HistoryDealGetTicket()`, keyed by `deal_ticket` (INSERT OR IGNORE for idempotence).
  - **STATS_CACHE table**: Self-computes hourly win rate, PnL, trade count, and gate-reason frequency at configurable intervals. Enables on-chart analytics without external tools.
  - **Gate instrumentation**: `JournalRecordSignal()` calls at every exit point in `CheckNativeScalperSetups()` — session_off, spread, open_groups, session_trade_cap, cooldown, direction_cooldown, m1, regime_countertrend — plus TAKEN on successful execution.
  - **SCRIBE sync**: New `forge_signals` table in `aurum_intelligence.db`. `Scribe.sync_forge_journal()` reads unsynced rows from FORGE's journal, inserts them, and marks them `synced=1`. BRIDGE calls sync every 60s via `_resolve_forge_journal_path()`.
  - New `.env` overrides: `FORGE_JOURNAL_ENABLED`, `FORGE_JOURNAL_RECORD_SKIPS`, `FORGE_JOURNAL_IMPORT_TRADES`, `FORGE_JOURNAL_IMPORT_DEPTH_DAYS`, `FORGE_JOURNAL_STATS_INTERVAL_SEC`. All hot-reloadable.

## [2.3.1] — 2026-05-06
### Added
- **Trade quality & survival improvements** (`ea/FORGE.mq5`, `config/scalper_config.json`, `.env.example`, `scripts/sync_scalper_config_from_env.py`):
  Ref: Backtesting diagnosis — fast SL hits (4-minute whipsaws) from tight SL, aggressive ratchet, and missing tester-mode guards.
  1. **Configurable tester session filter**: `ScalperTesterSessionOK()` lets users optionally apply session filtering in Strategy Tester via comma-separated session list (`tester_session_filter`, `tester_allowed_sessions`). Default off (trades all sessions).
  2. **Tester cooldown enabled**: Loss cooldown now applies in tester too (`tester_cooldown_enabled`), preventing rapid opposite-direction whipsaw after a loss. Default on.
  3. **Wider bounce SL**: `sl_atr_mult` default changed from 1.2 to 1.5 — ~25% more breathing room for M5 XAU.
  4. **Longer fast-lock hold**: `fast_lock_min_hold_sec_bounce` default changed from 45s to 90s — lets bounce setups develop 1–2 M5 candles before ratcheting.
  5. **Directional anti-whipsaw cooldown**: `ScalperDirectionCooldownOK()` prevents BUY→SELL flip within configurable N M5 bars (`direction_cooldown_enabled`, `direction_cooldown_bars`). Default 6 bars (30 min). Logged as `skip gate=direction_cooldown`.
- New `.env` overrides: `FORGE_TESTER_SESSION_FILTER`, `FORGE_TESTER_ALLOWED_SESSIONS`, `FORGE_TESTER_COOLDOWN_ENABLED`, `FORGE_DIRECTION_COOLDOWN_ENABLED`, `FORGE_DIRECTION_COOLDOWN_BARS`. All hot-reloadable.
- Sync script `_parse_value()` now supports `"string"` type for `tester_allowed_sessions`.

## [2.3.0] — 2026-05-06
### Added
- **Parabolic SAR state tracking** (`ea/FORGE.mq5`, `config/scalper_config.json`, `scripts/sync_scalper_config_from_env.py`, `python/bridge.py`, `python/lens.py`, `python/scribe.py`):
  - Ref: [MQL5 Article 17234 — "Parabolic Stop and Reverse Tool" by Christian Benjamin](https://www.mql5.com/en/articles/17234)
  - Native `DetectPSARState()` creates an `iSAR` handle on M5 and detects five states: `FLIP_BULL`, `FLIP_BEAR`, `BELOW`, `ABOVE`, `NONE`. Throttled to once per M5 bar.
  - **Informational only** — PSAR state is logged and streamed through the full data pipeline but does **not** gate or block any entries. Purely data collection to evaluate whether PSAR flips correlate with higher win rates before promoting to a gate.
  - **Journal log**: `PSAR=` field in every trade entry Print. Flip events logged with `FORGE PSAR:` prefix.
  - **Data pipeline**: `psar_state` field in `market_data.json`, `scalper_entry.json`, BRIDGE activity log, BRIDGE open_context, SCRIBE `market_snapshots` (TEXT column with auto-migration), and LENS pass-through.
  - **Telegram alerts**: `PSAR: FLIP_BULL` (or `FLIP_BEAR`) appended to FORGE scalp entry notifications only when a flip is active at entry time.
  - New `.env` overrides: `FORGE_PSAR_ENABLED`, `FORGE_PSAR_STEP`, `FORGE_PSAR_MAXIMUM`. All hot-reloadable.

## [2.2.0] — 2026-05-06
### Added
- **RSI divergence detection** (`ea/FORGE.mq5`, `config/scalper_config.json`, `scripts/sync_scalper_config_from_env.py`, `python/bridge.py`, `python/lens.py`, `python/scribe.py`):
  - Ref: [MQL5 Article 17198 — "RSI Sentinel Tool" by Christian Benjamin](https://www.mql5.com/en/articles/17198)
  - Native `DetectRSIDivergence()` scans M5 RSI and price for four divergence types: Regular Bullish, Regular Bearish, Hidden Bullish, Hidden Bearish. Throttled to once per M5 bar.
  - **Bounce entry gate**: counter-trend regular divergence blocks bounce entries (`REG_BEAR` blocks buy, `REG_BULL` blocks sell). Hidden divergences and NONE pass through. Breakout entries are never gated.
  - **Chart visualization**: `DrawDivergenceArrow()` draws green (bullish) or red (bearish) arrows on the chart only when divergence contributes to an actual trade entry.
  - **Journal log**: `RSI_DIV=` field in every trade entry Print.
  - **Data pipeline**: `rsi_divergence` field in `market_data.json`, `scalper_entry.json`, BRIDGE activity log, BRIDGE open_context, SCRIBE `market_snapshots` (TEXT column with auto-migration), and LENS pass-through.
  - **Telegram alerts**: `DIV: REG_BULL` (or similar) appended to FORGE scalp entry notifications when divergence is present.
  - New `.env` overrides: `FORGE_RSI_DIV_ENABLED`, `FORGE_RSI_DIV_LOOKBACK`, `FORGE_RSI_DIV_SWING_BARS`, `FORGE_RSI_DIV_MIN_RSI_DIFF`, `FORGE_RSI_DIV_DRAW_ARROWS`. All hot-reloadable.

## [2.1.0] — 2026-05-06
### Added
- **Fibonacci swing retracement** (`ea/FORGE.mq5`, `config/scalper_config.json`, `scripts/sync_scalper_config_from_env.py`, `python/bridge.py`, `python/lens.py`, `python/scribe.py`):
  - Ref: [MQL5 Article 17121 — "External Flow (III) TrendMap"](https://www.mql5.com/en/articles/17121)
  - Native `ComputeFibonacciSwing()` computes swing high/low and Fib 38.2%, 50%, 61.8% levels from M5 lookback (60s throttle, reuses `vp_lookback` by default).
  - **Directional bias gate**: VWAP-vs-Fib50 optional confirmation for bounce entries (`fib_bias_enabled`). When VWAP < Fib50, sell bias; VWAP > Fib50, buy bias. Breakouts unaffected.
  - **Fib TP targeting**: Fib 38.2% and 61.8% as intermediate TP candidates for bounce entries (`fib_tp_enabled`).
  - All Fib levels flow through `market_data.json` (`volume_profile` section), `scalper_entry.json`, BRIDGE, LENS, and SCRIBE `market_snapshots` (`fib_50`, `fib_382`, `fib_618` columns with auto-migration).
  - New `.env` overrides: `FORGE_FIB_BIAS_ENABLED`, `FORGE_FIB_TP_ENABLED`, `FORGE_FIB_LOOKBACK`. All hot-reloadable.
- **Single-source versioning** (`VERSION`, `scripts/compile_forge_ea_macos.sh`, `scripts/sync_scalper_config_from_env.py`):
  - New `VERSION` file at repo root — the single source of truth for all version stamps.
  - Compile script reads `VERSION` and stamps both `FORGE_VERSION` constant and `#property version` in `ea/FORGE.mq5` before compilation.
  - Sync script reads `VERSION` and stamps `scalper_config.json` version field automatically.
  - To bump: `echo "X.Y.Z" > VERSION && make forge-compile` — no manual edits needed anywhere else.

## [2.0.0] — 2026-05-06
### Added
- **FORGE Scalper V2** — 7 new features (`ea/FORGE.mq5`, `config/scalper_config.json`, `python/lens.py`, `python/bridge.py`, `python/scribe.py`):
  1. **Stricter H1 filter** (`bounce_require_h1_direction`): H1 flat no longer allows bounce entries when enabled.
  2. **Multi-candle bar-0 confirmation** (`bounce_require_bar0_confirm`): requires current price moving away from the band.
  3. **Candlestick pattern scoring** (`ScalperCandlePatternScore()`): Hammer/Shooting Star (2), Engulfing (3), Basic (1) replace simple bullish/bearish check. Gated by `bounce_min_candle_score`.
  4. **Volume Profile + POC** (`ComputeVolumeProfile()`): native M5 tick-volume POC computed every 60s.
  5. **VWAP** (added to `ComputeVolumeProfile()`): typical-price * volume VWAP alongside POC for dual volume-based reference levels.
  6. **Structural SL/TP using POC + VWAP + OB zones**: `FindStructuralSL()` places SL beyond nearest OB zone; `NearLiquidityZone()` checks proximity to POC, VWAP, or OB zones; POC/VWAP used as intermediate TP targets.
  7. **Breakout retest state machine** (`BreakoutRetest` struct): arms retest instead of immediate entry when `breakout_use_retest` enabled; `BB_BREAKOUT_RETEST` setup type with configurable `breakout_retest_max_bars`.
  - LENS writes OB zones to `ob_zones.json` for FORGE consumption.
  - All V2 params hot-reloadable via `scalper_config.json` without recompilation.
  - New `.env` overrides for all V2 params with `sync_scalper_config_from_env.py` mappings.
- **SCRIBE `market_snapshots` VP columns**: `poc_price`, `vwap_price` with auto-migration. BRIDGE flattens `volume_profile` from `market_data.json` and passes through LENS to SCRIBE.
- **`market_data.json` `volume_profile` section**: `poc_price`, `poc_strength`, `vwap_price` (and Fib levels in 2.1.0).
- **`scalper_entry.json` V2 fields**: `poc_price`, `vwap_price`, `pattern_score` carried through BRIDGE to SCRIBE `open_context`.

### Changed
- **FORGE version**: bumped to `v2.0.0` (`FORGE_VERSION` constant + `#property version`).
- **`scalper_config.json` version**: bumped to `"2.0"`.
- **Fixed duplicate `forge_version`** in `WriteMarketData()`: removed hardcoded `"1.6.19"` that was silently overriding the `FORGE_VERSION` constant.
- **`sync_scalper_config_from_env.py`**: now always copies updated config to `MT5/scalper_config.json` after writing, ensuring MT5 picks up changes without recompilation.
- **`BB_BREAKOUT_RETEST` parity**: auto-lot and `move_be_on_tp1` logic now correctly treats retest entries as breakout setups. `ManageOpenGroups` fast-lock matches both `BB_BREAKOUT` and `BB_BREAKOUT_RETEST` comments.

## [Unreleased]

### Added
- **SCRIBE `trade_groups.open_context`** (`python/scribe.py`, `python/bridge.py`): JSON attribution snapshot at group open (regime + compact MT5 + optional AEGIS fields + `extra` per source). Toggle **`BRIDGE_OPEN_CONTEXT_ENABLE`**; size cap **`SCRIBE_OPEN_CONTEXT_MAX_BYTES`**. Migration is additive. Tests: `tests/services/test_scribe_open_context.py`. Example query: `docs/SCRIBE_QUERY_EXAMPLES.md`.

### Changed
- **Scalper regime roadmap — Phases D–F** (`python/bridge.py`, `python/aegis.py`, `python/aurum.py`, tests, `docs/AEGIS.md`, `docs/SCRIBE_QUERY_EXAMPLES.md`, `.env.example`):
  - **Phase D:** `FORGE_NATIVE_SCALP` groups logged to SCRIBE now carry **`regime_*`** fields from the BRIDGE regime snapshot; `FORGE_SCALP_*` system events include a compact regime audit fragment.
  - **Phase E (optional):** **`AEGIS_REGIME_LOT_SCALE_ENABLED`** applies an extra lot-scale multiplier after streak-based scaling when regime label/confidence align (or dampen in RANGE/VOLATILE). Capped by **`AEGIS_SCALE_COMBINED_MAX`**. Default **off**.
  - **Phase F:** AURUM **`_build_context`** and BRIDGE **`AUTO_SCALPER`** AURUM prompts include the **`status.json`** regime block and counter-trend caution when policy is active.

- **FORGE high-volatility trend guard** (`ea/FORGE.mq5`): added live-focused guardrails for trend bursts to reduce loss clusters during volatile runs. New `scalper_config.json` safety keys:
  - `high_vol_trend_guard_enabled`,
  - `high_vol_adx_min`,
  - `high_vol_trend_strength_min`,
  - `high_vol_disable_bounce`,
  - `high_vol_require_h1_h4_breakout_align`,
  - `high_vol_breakout_sl_boost`.
- Behavior in live mode now:
  - suppresses `BB_BOUNCE` entries during confirmed high-vol trend regimes (when enabled),
  - requires stricter H1+H4 alignment for breakouts during those regimes (when enabled),
  - widens breakout SL by configurable multiplier during those regimes to reduce premature stop-outs.
- Added high-vol breakout ratchet dampening keys to reduce fast stop-outs:
  - `high_vol_fast_lock_extra_hold_sec`,
  - `high_vol_fast_lock_trigger_mult`,
  - `high_vol_fast_lock_trail_mult`.
  In high-vol trend regimes, breakout legs now wait longer before fast-lock engages, require deeper favorable progress before ratcheting, and trail with more breathing room.
- Added fast-lock net-profit guards to avoid "locked then loss" exits in volatile spread conditions:
  - `fast_lock_min_profit_points`,
  - `fast_lock_spread_guard_mult`.
  Fast-lock SL now enforces a minimum profit floor relative to entry (BUY above entry / SELL below entry) that scales with live spread, reducing negative SL_HIT outcomes after ratchet.
- **Tester ratchet stabilization + high-vol guard parity**:
  - `python/bridge.py`: disables BRIDGE `PROFIT_RATCHET` when `strategy_tester=true` to avoid frequent `Invalid stops` modify artifacts in tester runs.
  - `ea/FORGE.mq5` + `config/scalper_config.json`: added `high_vol_apply_in_tester` and enabled it by default so high-vol trend bounce suppression applies consistently in Strategy Tester diagnostics.
- **SCRIBE live watcher utility** (`scripts/watch_scribe_live.py`, `Makefile`, `docs/FORGE_TRADING_RULES.md`):
  - Added `make scribe-watch` for real-time `trade_groups`/`trade_closures`/`system_events` monitoring.
  - Added `make scribe-watch-log` to append watcher output into `logs/scribe_watch.log` for post-run review.
  - Added utility usage and review commands to the trading rules documentation.
- **FORGE ADX hysteresis anti-fade gate + SELL grace hold** (`ea/FORGE.mq5`, `config/scalper_config.json`):
  - Added deterministic M5 ADX regime state with hysteresis (`adx_trend_enter`, `adx_trend_exit`, tester toggle) so `BB_BOUNCE` is blocked while ADX is in a trend regime and only re-enabled after cooldown.
  - Added balanced SELL adverse grace window (`sell_loss_grace_sec`, `sell_loss_grace_adverse_points`) that defers ratchet/BE management during early adverse motion without widening SL.
  - Added explicit regime transition and bounce-skip diagnostics for backtest/live verification.

---

## [1.6.19] — 2026-05-02
### Changed
- **FORGE deterministic anti-fade control** (`ea/FORGE.mq5`, `config/scalper_config.json`, `.env.example`, `scripts/sync_scalper_config_from_env.py`):
  - Added M5 ADX hysteresis regime (`adx_trend_enter`/`adx_trend_exit`) to hard-block `BB_BOUNCE` while in trend regime and re-enable only after ADX cooldown.
  - Added balanced SELL adverse grace hold (`sell_loss_grace_sec`, `sell_loss_grace_adverse_points`) that defers ratchet/BE actions in early adverse motion without widening SL.
  - Added `.env` sync support for new hysteresis/grace safety knobs.
- **Version alignment to current release**: FORGE runtime-reported `forge_version` is now **`1.6.19`** in `market_data.json` and `broker_info.json`.

---

## [1.6.17] — 2026-05-02
### Changed
- **FORGE native bounce confirmation + risk controls** (`ea/FORGE.mq5` **v1.6.17**):
  - BB_BOUNCE confirmation is now configurable from `scalper_config.json`:
    - `bounce_reclaim_pct` (0..100, default 20),
    - `bounce_require_rejection_candle` (0/1, default 1).
  - Bounce entries still avoid first-touch catches, but operators can now tune confirmation strictness without recompiling.
- **Ratchet telemetry / hold controls** (`ea/FORGE.mq5`): `ReadScalperConfig()` now prints active bounce confirmation and fast-lock profile (`fast_lock_min_hold_sec_bounce`, `fast_lock_min_hold_sec_breakout`) for runtime auditability.
- **Trend auto-lot guardrails + observability** (`ea/FORGE.mq5`):
  - multiplier remains hard-bounded to `1.0..5.0`,
  - trend reference clamped to `>=0.10`,
  - entry logs now include trend context,
  - `scalper_entry.json` now includes `lot_multiplier`, `auto_lot_*` inputs and derived trend ratio values.

### Documentation
- Updated `docs/FORGE_TRADING_RULES.md` and `docs/DATA_CONTRACT.md` with safe live defaults and expanded scalper-entry decision fields.

---

## [1.6.11] — 2026-05-02
### Fixed
- **FORGE Strategy Tester reliability** (`ea/FORGE.mq5` **v1.6.11**): Native scalper backtests no longer stall behind live-only gates. In **`MQL_TESTER`**, FORGE keeps EA Inputs authoritative (ignores live `config.json` mode/scalper/regime overrides), skips live-only session/spread/sentinel blocks, and avoids stale-feed false positives via **`strategy_tester`** + Python mtime freshness enrichment.
- **Backtest trade generation** (`ea/FORGE.mq5`): Added Tester-only relaxed entry profile so test runs produce fills for diagnostics: looser ADX/trend/buffer/proximity thresholds, optional breakout M15 requirement off, R:R floor eased to 1.0, M1 gate bypassed, and session trade-cap/cooldown bypassed. **Live behavior remains strict**.
- **Tester diagnostics / operator clarity** (`ea/FORGE.mq5`): Journal now prints explicit Strategy Tester startup context and clearer "no setup" hints. Repeated per-tick spam is throttled to once per M5 bar, and unchanged `scalper_config.json` no longer re-logs every reload cycle.
- **Session default alignment** (`ea/FORGE.mq5`): native default NY session end aligned to **24 UTC** (matching `config/scalper_config.json`) to avoid silent 20:00-23:59 UTC shutoff when config is unavailable.

### Changed
- **Version alignment to current release**: FORGE runtime-reported `forge_version` is now **`1.6.11`** in `market_data.json` and `broker_info.json`.

---

## [1.6.5] — 2026-05-02
### Fixed
- **Strategy Tester vs BRIDGE staleness:** In the Tester, FORGE wrote **`timestamp_unix`** from **simulated** **`TimeGMT()`**, so Python treated **`market_data.json`** as years stale → **circuit breaker** + ATHENA **“MT5 data stale”** while you backtested. **FORGE v1.6.5** adds **`"strategy_tester":true`** to **`market_data.json`** when **`MQL_TESTER`** is active. **`python/market_data.py`** **`enrich_mt5_for_stale_check()`** uses **file mtime** for age when that flag is set; **`bridge.py`** and **`athena_api.py`** apply it before staleness / **`/api/live`**. Tests: **`tests/services/test_market_data_strategy_tester.py`**.

---

## [1.6.4] — 2026-05-02
### Fixed
- **FORGE** (`ea/FORGE.mq5` **v1.6.4**): In **Strategy Tester** (`MQL_TESTER`), **`ReadConfig()`** no longer applies **`effective_mode`**, **`scalper_mode`**, or **`regime_*`** from **`config.json`**. Stale live **`config.json`** (e.g. **`effective_mode`** **`WATCH`** when BRIDGE circuit breaker / sentinel, **`scalper_mode`** **`NONE`**) was overriding EA **Inputs** every tick and blocking native scalper backtests. Threshold fields (**`pending_entry_threshold_points`**, etc.) still load from **`config.json`** when present. **`forge_version`** **1.6.4**.

---

## [1.6.2] — 2026-05-02
### Fixed
- **FORGE** (`ea/FORGE.mq5` **v1.6.2**): **`ReadAndExecuteCommand`** — parse and trim **`action`** before timestamp dedup; **do not advance `g_last_cmd_ts`** when **`action`** is empty (avoids torn reads during atomic **`command.json`** writes skipping the real command). **`MODE_CHANGE`**, **`HEALTH_CHECK`**, **`SHELL_EXEC`**, **`AEB`**, **`AURUM_EXEC`**, **`OPEN_TRADE`** are **ignored** (they belong in **`aurum_cmd.json`**, not FORGE) instead of **`Unknown action`**. Actions matched case-insensitively after **`StringToUpper`**.

---

## [1.6.1] — 2026-05-02
### Changed
- **FORGE** (`ea/FORGE.mq5` **v1.6.1**): optional **M1** gate for native scalper — input **`NativeScalperM1Mode`**: **`NONE`** (default), **`CONFIRM`** (M1 EMA/ATR alignment vs **`trend_strength_atr_threshold`**), **`TRIGGER`** (**CONFIRM** plus direction of **prior closed M1 bar**). H1/H4/regime remain **bias-only**; **M5** remains the setup timeframe. **`market_data.json`**: **`indicators_m1`**; **`scalper_entry.json`**: **`native_scalper_m1_mode`**, **`m1_trend_strength`**, **`m1_prior_close`**, **`m1_prior_open`**. Operator: **`make forge-compile`**; **`forge_version`** **1.6.1**.
- Repo **release label** **1.6.1**: **`python/bridge.py`** `VERSION`, **`README.md`**, **`.env.example`**, **`python/athena_api.py`** default.

---

## [1.6.0] — 2026-05-04
### Changed
- **Phase C (FORGE native scalper + BRIDGE config bus)** (`ea/FORGE.mq5` **v1.6.0**): Native BB bounce/breakout setups optionally require **H4** EMA20/50 vs ATR trend alignment (same ATR-normalized threshold as H1) via input **`NativeScalperH4Align`** (default **true**). When **`regime_*`** in **`MT5/config.json`** indicates active entry policy and confidence ≥ min, input **`NativeScalperRegimeGate`** (default **true**) blocks **SELL** vs **`TREND_BULL`** and **BUY** vs **`TREND_BEAR`**, aligned with Python **AEGIS** Phase B. **`market_data.json`** adds **`indicators_h4`**; **`broker_info.json`** / **`market_data.json`** report **`forge_version` `1.6.0`**; **`scalper_entry.json`** adds **`h4_trend_strength`**.
- **`python/bridge.py`**: **`_write_config()`** now includes **`regime_label`**, **`regime_confidence`**, **`regime_apply_entry_policy`** (0/1), **`regime_countertrend_min_confidence`** (from **`AEGIS_REGIME_COUNTERTREND_MIN_CONFIDENCE`**). **`_write_status()`** calls **`_write_config()`** each loop so FORGE sees a fresh regime snapshot without restarting BRIDGE. Test: **`tests/api/test_bridge_config_regime.py`**. Operator: **`make reload-bridge`** after deploy; **`make forge-compile`** after pulling EA changes.

### Documentation
- **`docs/FORGE_TRADING_RULES.md`**, **`docs/FORGE_BRIDGE.md`**, **`docs/DATA_CONTRACT.md`**, **`docs/SCALPER_REGIME_PHASED_PLAN.md`** — Phase C behaviour and **`config.json`** keys.

---

## [1.5.7] — 2026-05-03
### Changed
- **Phase B (regime counter-trend gate)** (`python/aegis.py`): optional **`REGIME_COUNTERTREND:*`** rejection when **`regime_context.apply_entry_policy`** is true (`REGIME_ENTRY_MODE=active`) and the trade **fades** a high-confidence **`TREND_BULL`** / **`TREND_BEAR`** label (SELL in bull, BUY in bear). Default gated sources: **`SCALPER_SUBPATH_DIRECT`** only — configurable via **`AEGIS_REGIME_COUNTERTREND_SOURCES`**, **`AEGIS_REGIME_COUNTERTREND_BLOCK`**, **`AEGIS_REGIME_COUNTERTREND_MIN_CONFIDENCE`**. Shadow/off regime modes leave **`apply_entry_policy`** false so this guard stays inactive. Tests: **`tests/services/test_aegis_regime_countertrend.py`**. Operator: **`make reload-bridge`**.
- **Phase A (scalper + AEGIS)** (`python/bridge.py`): BRIDGE LENS-driven scalper (`_scalper_logic`, `SCALPER_SUBPATH_DIRECT`) now calls **`Aegis.validate()`** with `mt5_data`, **`regime_context`**, and **`current_price`** before `OPEN_GROUP`. Rejections emit **`SCALPER_REJECTED`** activity (`gate: AEGIS`). Approved rows persist **`regime_*`** on `trade_groups`, **`update_group_open_meta`** entry-zone pips, **`herald.trade_group_opened`**, and FORGE commands use **`approval.entry_ladder`** / **`approval.lot_per_trade`** / **`approval.num_trades`**. (`python/aegis.py`): fixed-lot mode respects **`SCALPER_SUBPATH_DIRECT`** alongside other fixed sources. Tests: **`tests/api/test_scalper_aegis_gate.py`**. Operator: **`make reload-bridge`** after deploy.

### Documentation
- Added **[docs/SCALPER_REGIME_PHASED_PLAN.md](docs/SCALPER_REGIME_PHASED_PLAN.md)** — phased roadmap for aligning self-scalping (BRIDGE LENS, FORGE native, AUTO_SCALPER) with regime/trend gates, Makefile verify/restart steps, MT5 Strategy Tester backtesting orientation, testing checklist per phase, copy-paste execution prompts, and documentation touch-points (`README`, `ARCHITECTURE`, `AEGIS`, `DATA_CONTRACT`, `SOUL`, `SKILL`, changelog, architecture diagram when flows change). Includes risk framing for lot scaling vs martingale-style recovery.

---
## [1.5.6] — 2026-05-02
### Phase 3 cleanup sprint
- **M1** (`python/listener.py`): added post-parse `ENTRY` range validation after text/vision merge and before dispatch. LISTENER now drops malformed signals with a WARNING when entry bounds are missing/non-positive, `entry_low > entry_high`, `sl <= 0`, `tp1 <= 0` when present, or XAU/GOLD `entry_low` falls outside `1000..99999`. Tests: `tests/services/test_signal_range_validation.py`.
- **M2** (`python/reconciler.py`, `python/bridge.py`, `.env.example`): centralised FORGE magic range configuration with `FORGE_MAGIC_NUMBER` + `FORGE_MAGIC_MAX`, added reconciler startup assertion, and replaced the hardcoded reconciler range check with the shared env-driven bounds. Tests: `tests/services/test_reconciler_magic_range.py`.
- **M4** (`python/sentinel.py`): added ForexFactory parse-zero fail-safe alerting. During weekday 06:00–20:00 UTC, a zero-event parse now logs WARNING and sends the Herald/Telegram alert `⚠️ SENTINEL: ForexFactory returned 0 events during trading hours — possible markup change or parse failure`; weekends and off-hours stay quiet. Tests: `tests/services/test_sentinel_parse_zero.py`.
- **M5** (`python/sentinel.py`, `requirements.txt`): replaced fixed Eastern→UTC offset arithmetic with DST-aware `America/New_York` conversion using `pytz` when installed, with a standard-library fallback for pre-upgrade environments. July `8:30am` maps to `12:30 UTC`; January `8:30am` maps to `13:30 UTC`. Tests: `tests/services/test_sentinel_parse_zero.py`.
- **M6** (`python/contracts/aurum_forge.py`): added OPEN_GROUP cross-field contract checks for BUY/SELL TP/SL geometry and TP2/TP3 ordering. Tests: `tests/api/test_aurum_forge_contract.py`.
---
## [1.5.5] — 2026-05-02
### L1–L6 low-severity cleanup sprint
- **L1** (`regime.py`): detects HMM feature vector shape changes between calls, logs a WARNING with the old→new shape, and sets `feature_shape_mismatch=True` in the regime snapshot so BRIDGE can surface it. Test: `test_regime_engine_flags_hmm_feature_shape_mismatch`.
- **L2** (`aurum.py`): `SOUL.md` and `SKILL.md` are now cached at module level instead of re-read on every `ask()` call. A `SIGHUP` handler reloads the cache in-place so a running process can refresh without restart. Tests: `test_ask_uses_cached_soul_skill_without_rereading`, `test_sighup_reloads_soul_skill_cache`.
- **L3** (`regime.py`): HMM `n_components` is now read from `REGIME_HMM_COMPONENTS` (default 3, validated 2–10). `.env.example` documents the new knob. Test: `test_regime_hmm_components_env_validation`.
- **L4** (`ea/FORGE.mq5:~550`): added an explicit `(int)` cast on `tp1_close_pct`, with a comment noting fractional values are truncated by design. No logic change.
- **L5** (`.gitignore`): added `.claude/worktrees/` and `.claude/scheduled_tasks.lock` under the Agent / AI context section to prevent Claude Code runtime artifacts from being committed.
- **L6** (`python/freshness.py`): created `DATA_FRESHNESS_WINDOWS` to centralise default staleness thresholds for MT5, SENTINEL, REGIME, and LENS. `bridge.py`, `sentinel.py`, `regime.py`, `lens.py`, and `market_data.py` now import it as the env-var fallback. Test: `test_data_freshness_windows_are_defined`.
### Phase 2 reliability sprint
- **H1** (`python/config_io.py`, `bridge.py`, `listener.py`, `athena_api.py`, `reconciler.py`): added `atomic_write_json()` and routed config/file-bus JSON writes through temp-file + `os.replace` atomic writes. Tests: `test_atomic_write_json_creates_file`, `test_atomic_write_json_is_atomic`, `test_atomic_write_json_cleans_up_on_error`.
- **H3** (`python/listener.py`, `python/aurum.py`): Telegram async handlers now offload blocking file/media/vision/chat work with `asyncio.to_thread()` where the handler directly invoked synchronous work. Test: `test_no_time_sleep_in_async_handlers`.
- **H4** (`python/mcp_client.py`, `python/lens.py`, `python/aeb_executor.py`): MCP stdout reads now use `select.select(..., timeout=15)` and raise `MCPTimeoutError` after killing the process; LENS subprocess calls use 15s timeouts and return stale data with `stale=True` on timeout; AEB shell/health default timeouts are 10s and log `AEB exec slow` above 5s. Tests: `test_mcp_client_raises_on_timeout`, `test_lens_returns_stale_on_subprocess_timeout`.
- **M3** (`bridge.py`, `athena_api.py`, `listener.py`, `reconciler.py`, `aurum.py`, `sentinel.py`): removed bare `except:` blocks from the fixed source files and replaced silent file/JSON read fallbacks with typed exceptions and warning logs. Test: `test_no_bare_except_in_source_files`.
- **M7** (`requirements.txt`): pinned upper bounds for `anthropic`, `telethon`, and `flask`; bumped Telethon to `>=1.40.0`; added missing imported packages `hmmlearn`, `numpy`, and `httpx`. Test: `test_requirements_have_upper_bounds`.
### Security fixes — local MT5 link and scoped channel MODIFY commands
- **P2 Security**: untracked the machine-specific `MT5` symlink and added `make setup-mt5-link`. The committed symlink embedded an absolute path to one developer's MT5 Common Files directory, breaking other checkouts. `MT5_PATH` in `.env` now drives local symlink creation, with `.env.example` documenting the setup flow and `.gitignore` covering the bare symlink name.
- **C2 Security**: channel-origin `MODIFY_SL` and `MODIFY_TP` commands now require a resolved scope (`group_id`/magic or `ticket`) before BRIDGE writes a FORGE modify command. Previously, a channel message without a resolved `group_id` or `ticket` could write an unscoped `MODIFY_*` command that FORGE applied to every managed position. Unresolved channel MODIFY commands are now dropped with a warning log instead of falling through to global scope.
### Security / reliability follow-up fixes
- **C1 Security** (`python/athena_api.py`): ATHENA now binds to `ATHENA_HOST` with a localhost default (`127.0.0.1`) instead of `0.0.0.0`. When `ATHENA_SECRET` is set and non-empty, all state-mutating HTTP methods (`POST`/`PUT`/`PATCH`/`DELETE`) require `X-Athena-Token`; unset/empty keeps existing no-token local behavior and logs a startup warning. `.env.example` documents `ATHENA_SECRET`.
- **C3 Security** (`python/scribe.py`): dynamic SCRIBE table export now rejects table names outside `ALLOWED_SCRIBE_TABLES` and parameterizes the optional `mode` filter instead of interpolating it into SQL.
- **H2 Reliability** (`python/aurum.py`, `python/listener.py`): Claude `messages.create(...)` calls now pass `timeout=httpx.Timeout(30.0)`. LISTENER also wraps the blocking call in `asyncio.wait_for(..., timeout=30)` and timeout exceptions are logged as warnings before returning the existing fallback path.
- **H5 Reliability** (`python/sentinel.py`): ForexFactory fetch failures now retry up to two times with 3-second pauses and then fail closed by returning a high-impact fail-safe event that activates the news guard, instead of silently treating fetch failure as no guard needed.
- Tests: extended `tests/api/test_athena_management_api.py`, `tests/api/test_athena_scribe_query_limits.py`, `tests/api/test_athena_live_unit.py`, and added `tests/services/test_sentinel_failsafe.py`.
---
## [1.5.4] — 2026-05-02
### ATHENA `/api/management` schema validation (backward-compatible)
Closed the gap where `api_management()` wrote raw user-supplied JSON straight to `python/config/management_cmd.json` without any schema check. BRIDGE reads that file every tick; a malformed payload would land in the type-coercion branch (`int(group_id)`, `float(sl)`, `float(tp)`), bubble up through `_tick`'s exception handler, and spam Telegram alerts on every loop until somebody manually deleted the file.
- New schema `schemas/files/management_cmd.schema.json` (Draft-07) with intent-conditional `if/then` branches: `CLOSE_PCT` / `CLOSE_GROUP_PCT` enforce `pct ∈ (0, 100]`; `CLOSE_GROUP` / `CLOSE_GROUP_PCT` require `group_id > 0`; `MODIFY_SL` requires `sl > 0`; `MODIFY_TP` requires `tp > 0`. `additionalProperties: true` on every branch so LISTENER's `signal_id`/`channel`/`edited` fields don't get rejected.
- New `_MGMT_VALIDATOR` + `_validate_mgmt_body(body)` in `python/athena_api.py`. `api_management()` validates the assembled body **before** writing; on failure it returns `400 {error:"validation_failed", intent, details: […]}` and never touches the file.
- **Backward-compatible by design**: validator load is wrapped in `try/except` and `iter_errors` calls are wrapped too. If the schema file is missing, jsonschema imports break, or any runtime error occurs in the validator, `_validate_mgmt_body` returns `[]` and `api_management()` falls through to the original unvalidated write path. Operators can never be "locked out" by a validation infrastructure problem.
- **LISTENER and BRIDGE are intentionally unchanged** — they keep the existing tolerate-bad-payloads behaviour. The fix is at the only entry point where untrusted user JSON enters the file bus.
- Tests: new `tests/api/test_management_schema.py` (15 cases) covering valid intents, missing-required-field rejection, range/null rejection, LISTENER-style extra fields tolerated, validator-unavailable fallback, and validator-internal-error fallback. **346/346 in `tests/api/` pass**.
- Migration / rollout: drop-in. Restart ATHENA to pick up the validator (`make services-restart` or just bounce `com.signalsystem.athena`). No FORGE / SCRIBE / BRIDGE changes.
---
## [1.5.3] — 2026-05-01
### ATHENA `/api/management` schema validation (backward-compatible)
Closed the gap where `api_management()` wrote raw user-supplied JSON straight to `python/config/management_cmd.json` without any schema check. BRIDGE reads that file every tick; a malformed payload would land in the type-coercion branch (`int(group_id)`, `float(sl)`, `float(tp)`), bubble up through `_tick`'s exception handler, and spam Telegram alerts on every loop until somebody manually deleted the file.
- New schema `schemas/files/management_cmd.schema.json` (Draft-07) with intent-conditional `if/then` branches: `CLOSE_PCT` / `CLOSE_GROUP_PCT` enforce `pct ∈ (0, 100]`; `CLOSE_GROUP` / `CLOSE_GROUP_PCT` require `group_id > 0`; `MODIFY_SL` requires `sl > 0`; `MODIFY_TP` requires `tp > 0`. `additionalProperties: true` on every branch so LISTENER's `signal_id`/`channel`/`edited` fields don't get rejected.
- New `_MGMT_VALIDATOR` + `_validate_mgmt_body(body)` in `python/athena_api.py`. `api_management()` validates the assembled body **before** writing; on failure it returns `400 {error:"validation_failed", intent, details: […]}` and never touches the file.
- **Backward-compatible by design**: validator load is wrapped in `try/except` and `iter_errors` calls are wrapped too. If the schema file is missing, jsonschema imports break, or any runtime error occurs in the validator, `_validate_mgmt_body` returns `[]` and `api_management()` falls through to the original unvalidated write path. Operators can never be "locked out" by a validation infrastructure problem.
- **LISTENER and BRIDGE are intentionally unchanged** — they keep the existing tolerate-bad-payloads behaviour. The fix is at the only entry point where untrusted user JSON enters the file bus.
- Tests: new `tests/api/test_management_schema.py` (15 cases) covering valid intents, missing-required-field rejection, range/null rejection, LISTENER-style extra fields tolerated, validator-unavailable fallback, and validator-internal-error fallback. **346/346 in `tests/api/` pass**.
- Migration / rollout: drop-in. Restart ATHENA to pick up the validator (`make services-restart` or just bounce `com.signalsystem.athena`). No FORGE / SCRIBE / BRIDGE changes.
---
## [1.5.3] — 2026-05-01
### Hybrid profit ratchet — SL pin + tightened TP per-ticket
When a leg crosses `PROFIT_RATCHET_TRIGGER_PIPS`, BRIDGE now also pulls that **leg's** TP toward `current_price ± PROFIT_RATCHET_TP_BUFFER_PIPS` so any further forward movement closes the leg with a `TP_HIT` (positive close) rather than letting the SL ratchet catch the retrace. The original SL pin is preserved as the floor on retracements — every closure on the triggered leg now lands positive, regardless of which side fires.
- **Per-ticket scope is preserved**: only the leg that crossed the trigger is tightened. Sibling legs in the same group keep their original TP1/TP2/TP3 targets and continue running. This is the explicit operator preference — lock the runner, let the rest reach the staged targets.
- New env: `PROFIT_RATCHET_TP_BUFFER_PIPS` (default 5; trader-style pips). Set to 0 to disable the TP-tightening side and revert to pure SL ratchet behaviour.
- TP tightening is skipped when (a) the buffer is 0, (b) the position has no resting TP (no regression introduced), or (c) the proposed target would not actually tighten (BUY: `target_tp ≥ live_tp`; SELL: `target_tp ≤ live_tp`).
- Both the SL pin and the TP tighten go through the new FORGE command queue with separate dedup keys (`ratchet:<ticket>` and `ratchet_tp:<ticket>`) and per-ticket verifiers (`_build_ticket_sl_verifier`, `_build_ticket_tp_verifier`), so the two writes serialise correctly across the BRIDGE → FORGE file bus.
- Tests: `tests/api/test_modify_scope.py` adds 4 new cases (skip when no resting TP, skip when buffer would widen, disabled when buffer=0, per-leg isolation across BUY+SELL). Existing BUY/SELL ratchet tests now assert the SL+TP enqueue pair. **331/331 in `tests/api/` pass**.
- Migration / rollout: pure BRIDGE refactor; no FORGE EA / SCRIBE / contract changes. Defaults to enabled with a 5-pip buffer; set `PROFIT_RATCHET_TP_BUFFER_PIPS=0` to opt out.
---
## [1.5.2] — 2026-05-01
### FORGE command queue — fixes per-ticket MODIFY_SL race
Live G64 profit-ratchet test exposed a real overwrite race: BRIDGE wrote 4 ticket-scoped `MODIFY_SL` commands to the shared `MT5/command.json` within ~1.8 s; FORGE polls that file on its `OnTimer` and dedups by `timestamp`, so the first write got clobbered before FORGE could consume it. Leg 0 (#1247680712) never moved its SL, took the original SL hit for **−$4.39**, and turned what should have been a clean +$3.00 set of ratchet locks into a **net −$1.39**. The next BRIDGE tick then "learned" the stale live SL back into its in-memory cache via the drift detector, so the ratchet never retried.
- New module-level `_ForgeCommandQueue` (`python/bridge.py`) serialises FORGE writes: at most one command is in-flight per BRIDGE tick. Each pump verifies the in-flight command via a caller-supplied `verifier(mt5)` (or auto-acks after a one-tick spacing for fire-and-forget shapes), retries on timeout up to `FORGE_QUEUE_MAX_RETRIES`, and drops with an `on_drop` callback so callers can release dedup tokens. New env knobs: `FORGE_QUEUE_ACK_TIMEOUT_SEC` (default 8.0), `FORGE_QUEUE_MAX_RETRIES` (default 2). Pumped once per BRIDGE tick right after `_sync_positions`, even when MT5 is stale, so the ack-timeout path keeps ticking.
- `Bridge._enqueue_forge_command(cmd, *, verifier, description, on_drop, dedup_key)` is the new entry point. Used by `_apply_profit_ratchet` (with strict `_build_ticket_sl_verifier` per ticket and `dedup_key=ratchet:<ticket>` so a re-eligible tick doesn't pile up), `_check_aurum_command` `MODIFY_TP`/`MODIFY_SL`, and `_process_mgmt_command` `MODIFY_TP`/`MODIFY_SL`. Ticket-scoped modifies always come with a verifier; group/stage-wide modifies use the queue's fire-and-forget ack so they still get ≥1-tick spacing without needing a snapshot match.
- `_apply_profit_ratchet` no longer pre-updates `self._known_positions[ticket]['sl']` to the target. The drift detector now skips its "learn-back" branch for any ticket that has a `MODIFY_SL`/`MODIFY_TP` queued or in-flight (`_ForgeCommandQueue.has_inflight_modify_for_ticket`), so MT5's pre-modify live SL never overwrites the queued target. If the queue ultimately drops the ratchet command, `_profit_ratcheted.discard(ticket)` runs from `on_drop` so the next eligible tick re-attempts.
- Tests: `tests/api/test_modify_scope.py` adds 7 new cases — queue writes one cmd per pump (the actual race), inflight held until verifier passes, retry-and-drop budget, dedup_key suppression, `has_inflight_modify_for_ticket` matching only `MODIFY_*`, drift detector skip while modify in-flight, and ratchet `on_drop` clears the dedup token. Existing ratchet + AURUM/MGMT modify tests updated to assert against `_enqueue_forge_command`. **327/327 in `tests/api/` pass**.
- Migration / rollout: pure BRIDGE refactor; no FORGE EA, SCRIBE, or contract changes. `make reload-bridge` to ship.
---
## [1.5.1] — 2026-04-30
### Profit ratchet — auto-lock SL once a leg goes N pips green
New opt-in BRIDGE feature that addresses *"would have been nice if we close the order once we're in winning position"* without waiting for TP1. Once any tracked managed position is `≥ PROFIT_RATCHET_TRIGGER_PIPS` (default 3 XAUUSD pips) in unrealised profit and its current SL is still worse than `entry ± PROFIT_RATCHET_LOCK_PIPS` (default 1 pip past entry), BRIDGE emits a **per-ticket** `MODIFY_SL` to FORGE — reusing the v1.5.0 stage-aware MODIFY pipeline so other legs/stages stay untouched. Idempotent via an in-memory ratcheted set; cleared automatically when the position closes.
- `python/bridge.py` `_apply_profit_ratchet`: pip math via existing `_pip_size_for_symbol` / `_calc_pips`, ticket-scoped FORGE write, `_sync_modify_targets` with `ticket=` for SCRIBE row update only, `[TRACKER|PROFIT_RATCHET]` audit log + Telegram notification.
- Skips re-evaluation when SL is already past the lock target (e.g. FORGE's `move_be_on_tp1` already fired) so it composes cleanly with the existing TP1→BE behaviour.
- New env vars: `PROFIT_RATCHET_ENABLED` (default false, opt-in), `PROFIT_RATCHET_TRIGGER_PIPS` (default 15 → $1.50 on XAU), `PROFIT_RATCHET_LOCK_PIPS` (default 10 → $1.00 past entry; auto-clamped to `< trigger`). **Trader-style pip** convention (XAU/XAG = $0.10, JPY = 0.01, majors = 0.0001) so the env-var values match `trade_closures.pips` and Athena reports. Helper: `_ratchet_pip_size`.
- Tests: `tests/api/test_modify_scope.py` adds 6 ratchet cases (BUY emit, SELL emit with inverted lock, idempotency, below-trigger skip, already-locked skip, disabled short-circuit). 76/76 in the targeted suites pass.
- Docs: `.env.example`, `SKILL.md`, `SOUL.md`, `docs/CLI_API_CHEATSHEET.md`.
---
## [1.5.0] — 2026-04-30
### Per-stage / per-ticket `MODIFY_TP` & `MODIFY_SL`
MODIFY commands across the AURUM → BRIDGE → FORGE pipeline now accept two new optional scope fields so TP2/TP3 legs no longer collapse onto TP1 when only TP1 needs to move.
- **FORGE** (`ea/FORGE.mq5` v1.5.0): `ExecuteModifySL` / `ExecuteModifyTP` read optional `ticket` (single position or pending) and `tp_stage` (1/2/3, filtered against `Comment()` matching `|TP<n>`); legacy whole-magic behaviour preserved when both are absent. `WriteMarketData` adds `comment` to each `open_positions[]` row so BRIDGE can recover the leg-stage metadata `FORGE|G<id>|<leg_index>|TP<stage>`.
- **BRIDGE** (`python/bridge.py`): `_check_aurum_command` and `_process_mgmt_command` MODIFY branches forward `ticket` / `tp_stage` to FORGE after light validation. New `_sync_modify_targets` helper routes SCRIBE persistence: ticket scope updates one row, stage scope only nudges `trade_groups.tp<n>` for the matching stage, and the unscoped path keeps the existing group-wide / all-open fan-out. `_TP_STAGE_RE`/`_parse_tp_stage_from_comment` helpers parse the FORGE comment grammar; TRACKER FILL records `tp_stage` on insert and the seed pass calls `backfill_tp_stage_from_comment` for legacy rows.
- **SCRIBE** (`python/scribe.py`): `log_trade_position` now persists `data['tp_stage']`. New helpers `update_positions_sl_tp_by_stage(group_id, tp_stage, sl, tp)`, `backfill_tp_stage_from_comment(ticket, comment)`, and `get_open_positions_with_stage(group_id)` expose the stage-aware surface. The schema is unchanged — `trade_positions.tp_stage` already existed.
- **AURUM prompt** (`python/aurum.py`): new `PER-STAGE / PER-TICKET MODIFY` section documents the new fields and **requires** a `SCRIBE_QUERY` on `trade_positions` before any multi-leg MODIFY. Two-block example shows independent TP1 vs TP2 moves.
- **Contracts** (`python/contracts/aurum_forge.py`): `validate_aurum_cmd` and `validate_forge_command` accept optional `ticket` (positive int) and `tp_stage` (1/2/3) on `MODIFY_TP` / `MODIFY_SL`; unknown-action error message updated.
- **Tests**: `tests/api/test_modify_scope.py` covers SCRIBE backfill / stage updates, BRIDGE `_coerce_modify_scope` + `_sync_modify_targets` routing, BRIDGE AURUM-cmd MODIFY pass-through, and AURUM-side contract validation. `tests/api/test_aurum_forge_contract.py` extended with stage/ticket validation.
- **Docs**: `docs/DATA_CONTRACT.md`, `docs/CLI_API_CHEATSHEET.md`, `schemas/files/market_data.schema.json`, `SKILL.md`, `SOUL.md` updated with the new shapes, the comment-grammar contract, and the SCRIBE_QUERY-first workflow.
- **Migration / rollout**: SCRIBE migration is purely additive (column already present). FORGE EA must be recompiled / reattached to MT5 for `comment` in `open_positions[]` and the new MODIFY filters; BRIDGE/AURUM/SCRIBE hot-reload via `make restart`.
---
## [1.4.5] — 2026-04-30

### Deferred Analysis Runs (`ANALYSIS_RUN`)
Reusable async-analysis subsystem layered on top of the AEB. AURUM (or any caller) emits a fire-and-forget AEB action and gets an immediate `query_id`; the result is persisted under `logs/analysis/<query_id>.{json,md}` and posted back to the existing Telegram channel via the existing Herald singleton (no new bot, token, or chat_id).
- New module `python/analysis_runner.py`:
  - `register_analysis(kind)` decorator + `_HANDLERS` registry.
  - `submit(payload)` returns immediately with `{ok, query_id, status:"PENDING", log_path}`.
  - `list_pending()` / `list_recent(limit=20)` / `get_status(query_id)` introspection.
  - Daemon `ThreadPoolExecutor` worker (cap `ANALYSIS_MAX_CONCURRENCY`, default 4) writes `.json` (status) + `.md` (body) and audits `ANALYSIS_QUEUED|DONE|FAILED` to `logs/audit/system_events.jsonl`.
  - Idempotency on client-supplied `query_id` (duplicate while PENDING returns `ANALYSIS_RUN duplicate query_id`); soft queue cap returns `ANALYSIS_RUN queue full`.
  - Built-in handler `trade_group_review` (params `{group_id:int}`) reads SCRIBE read-only + scrapes `logs/bridge.log` and renders a markdown review (signal text, AEGIS decision, fills, fill ratio, realised PnL); tolerates SCRIBE schema drift via `schema_missing:` notes.
- AEB / Bridge wiring:
  - `python/aeb_executor.py`: `ANALYSIS_RUN` added to `_AEB_ACTIONS`, validator branch, dispatcher branch (lazy import), Telegram ACK formatter renders `query_id`, `status`, `log_path`.
  - `python/bridge.py`: routes `ANALYSIS_RUN` through the existing local AEB dispatch alongside `SCRIBE_QUERY` / `SHELL_EXEC`.
- AURUM wiring:
  - `python/aurum.py`: `ANALYSIS_RUN` added to supported-actions list, new `DEFERRED ANALYSIS RUNS` section in `_build_system_prompt`, and a pending/recent block appended to `_build_context` (capped at 20 lines).
- Telegram (Herald) reuse — no new bot:
  - `python/herald.py`: new `Herald.post_text()` and `Herald.post_analysis_from_log()` methods plus module-level shims; `_async_send` accepts an optional `chat_id` override; default chat target remains `Herald.chat_id`.
- Schemas + contracts:
  - `schemas/files/aurum_cmd.schema.json`: new `ANALYSIS_RUN` `oneOf` branch.
  - `python/contracts/aurum_forge.py`: `validate_aurum_cmd` accepts `ANALYSIS_RUN` (kind required; params/notify/query_id types validated).
- Docs:
  - `docs/ARCHITECTURE.md`: “Deferred Analysis Runs” section + envelope + data-flow diagram.
  - `docs/DATA_CONTRACT.md`: `ANALYSIS_RUN` listed alongside other AEB actions.
  - `docs/CLI_API_CHEATSHEET.md`: copy-paste examples for queueing a run and tailing the log file.
  - `SKILL.md` §5 + `SOUL.md`: capability + context-awareness bullets.
  - `.env.example`: `ANALYSIS_LOG_DIR` + `ANALYSIS_MAX_CONCURRENCY`.
- Verification: `make test-contracts` 93 passed; `tests/api/test_aeb_executor.py` 9 passed; end-to-end smoke (G56 review) `fills=1/1 pnl=$+4.02` matched bridge.log.

---
## [1.4.4] — 2026-04-14

### AURUM Execution Bridge (AEB) end-to-end
- Added shared executor module `python/aeb_executor.py` for:
  - `SCRIBE_QUERY` (read-only SQLite URI mode + authorizer + single-statement guard + timeout/progress + row truncation)
  - `SHELL_EXEC` (allowlisted program/path validation, legacy `cmd` parsing via `shlex`, `subprocess.run(..., shell=False, timeout=...)`, output caps)
  - common result formatting for Telegram + structured result payloads
- Extended BRIDGE `aurum_cmd.json` router to handle `SCRIBE_QUERY`, `SHELL_EXEC`, and `AURUM_EXEC` while preserving existing command behavior and file-consume semantics.
- Added BRIDGE `AURUM_EXEC` HTTP dispatch path to ATHENA (`AURUM_EXEC_BASE_URL`, timeout, optional shared secret header).
- Added ATHENA `POST /api/aurum/exec` endpoint with optional token auth (`ATHENA_AURUM_EXEC_SECRET`) and shared executor dispatch.
- Hardened ATHENA `POST /api/scribe/query` internals to use the secure read-only executor path (with compatibility fallback for isolated test stubs).
- Extended AURUM JSON extraction allowlist and system prompt examples for `SCRIBE_QUERY`, `SHELL_EXEC`, and `AURUM_EXEC`.

### Contracts, schemas, docs, and tests
- Updated runtime validator `python/contracts/aurum_forge.py` for new AEB actions.
- Updated file-bus schema `schemas/files/aurum_cmd.schema.json` with new `oneOf` branches.
- Updated OpenAPI `schemas/openapi.yaml` with `/api/aurum/exec` and AEB request/result components.
- Updated `.env.example`, `docs/DATA_CONTRACT.md`, and `docs/SCRIBE_QUERY_EXAMPLES.md` for AEB config and usage.
- Added/extended tests:
  - new: `tests/api/test_aeb_executor.py`
  - new: `tests/api/test_athena_aurum_exec_api.py`
  - updated: `tests/api/test_bridge_aurum_cmd.py`
  - updated: `tests/api/test_aurum_forge_contract.py`
  - updated: `tests/api/test_json_schemas.py`
  - updated: `tests/api/test_swagger_ui.py`

---
## [1.4.3] — 2026-04-14

### Regime engine rollout surfaced end-to-end
- Added `python/regime.py` (HMM-primary inference with Gaussian fallback safety path).
- BRIDGE now computes regime snapshots each tick and persists emitted snapshots to SCRIBE `market_regimes`.
- SIGNAL/AURUM entry validation now carries regime context through AEGIS and records regime metadata on `signals_received` and `trade_groups`.
- ATHENA now serves regime surfaces via `GET /api/regime/current`, `GET /api/regime/history`, `GET /api/regime/performance`, and includes a `regime` block in `GET /api/live`.
- Added regime coverage tests:
  - `tests/services/test_regime_engine.py`
  - `tests/api/test_scribe_regime.py`
  - `tests/api/test_athena_regime_api.py`

### Execution-management and tracker hardening
- `MODIFY_SL` / `MODIFY_TP` support global and per-group execution:
  - no `magic` => global apply,
  - resolved `magic` from `group_id` => scoped apply.
- BRIDGE now syncs modified group targets into SCRIBE group + open-position rows (`update_group_sl_tp`) so ATHENA reflects live SL/TP edits immediately.
- FORGE exports `recent_closed_deals[]` in `market_data.json`; BRIDGE tracker now uses broker close metadata first (price, PnL, reason, close time) with inference fallback only when broker hints are missing.
- BRIDGE MT5 stale-data protection now tolerates transient `market_data.json` read/parse races by reusing the last known-good snapshot for a short, parameterized grace window before tripping circuit breaker:
  - `BRIDGE_MT5_STALE` (primary stale threshold),
  - `BRIDGE_MT5_STALE_RELAXED` (read-error fallback threshold),
  - `BRIDGE_MT5_READ_FAIL_STREAK` (consecutive read failures required before fallback can hard-fail).
- Added regression coverage:
  - `tests/api/test_mgmt_channel_scoping.py`
  - `tests/api/test_bridge_manual_position_tracking.py`
  - `tests/api/test_threshold_persistence.py`

### Documentation updates
- Updated `docs/ARCHITECTURE.md` with regime engine flow and `market_regimes` table coverage.
- Updated `docs/FORGE_TRADING_RULES.md` with regime rollout, scoped modify semantics, and broker-first closure attribution.
- Updated `docs/CLI_API_CHEATSHEET.md` and `docs/SCRIBE_QUERY_EXAMPLES.md` for TP-stage close reason examples and regime diagnostics queries.
- Updated `docs/SIGNAL_REPLAY_RUNBOOK.md` with direct SQLite quick diagnostics (Ben's VIP pickup checks, ENTRY-only checks, real Telegram ID filtering, and recent action snapshots using `datetime(timestamp)`).
- Updated `SOUL.md` and `SKILL.md` to reflect merged room allowlist aliases (`SIGNAL_TRADE_ROOMS` + `ACTIVE_SIGNAL_TRADE_ROOMS`), configurable SIGNAL orientation gate (`AEGIS_SIGNAL_LIMIT_ORIENTATION`), and replay-first troubleshooting (`scripts/replay_signal_pickup.py`).

---
## [1.4.2] — 2026-04-13

### LISTENER Signal Room Ingestion — Hardening & Observability

Root cause: signals from configured Telegram rooms were silently dropped as `WATCH_ONLY`
due to brittle room matching, a free-text reason code that was hard to grep, and zero
observability of where in the pipeline signals stopped flowing.

#### Room Allowlist Logic (`python/listener.py`)

- **Robust `_is_trade_room_allowed`** — now returns `(bool, reason_code)` tuple:
  - `ALLOWED_ALL` — `SIGNAL_TRADE_ROOMS` not set (legacy; all rooms trade)
  - `ALLOWED_TITLE_MATCH` — title matched after NFKC normalization + whitespace collapse + lowercase
  - `ALLOWED_ID_MATCH` — chat_id matched; tries all Telethon supergroup ID variants automatically (`-1001234567890`, `1001234567890`, `1234567890`)
  - `WATCH_ONLY_ROOM_FILTER` — not in allowlist (replaces old free-text `ROOM_NOT_PRIORITY:<room>`)
- **Unicode normalization** (`_normalize_room_name`): NFKC + whitespace-collapse + lowercase — handles curly apostrophes, non-breaking spaces, and other Unicode mismatches between operator config and Telethon-resolved titles.
- **chat_id variant matching** (`_chat_id_variants`): auto-tries bare ID, signed ID with `-100` prefix, and positive form — eliminates "configured `1234567890` but Telethon returns `-1001234567890`" silent misses.
- `WATCH_ONLY` blocks now log at **WARNING** (was INFO), making them visible in `make logs-errors`.

#### New Structured Reason Codes

| Reason Code | Where it appears | Meaning |
|---|---|---|
| `WATCH_ONLY_ROOM_FILTER` | `signals_received.skip_reason` | Room not in `SIGNAL_TRADE_ROOMS` allowlist |
| `SIGNAL_DISPATCHED` | `system_events.event_type` | Entry signal written to `parsed_signal.json` |
| `SIGNAL_PARSE_FAILED` | `system_events.event_type` | Non-empty text received but Claude returned IGNORE |
| `AEGIS_REJECTED:<reason>` | `signals_received.skip_reason` | AEGIS blocked the signal (prefixed, not bare reason) |

The old free-text `ROOM_NOT_PRIORITY:<room>` reason code is **removed**.

#### Staleness Detection

- `_last_ingest_at` tracked per LISTENER instance — updated on every received message.
- `_idle_heartbeat_loop` now checks age against `LISTENER_STALE_THRESHOLD_SEC` (default 600s):
  - `> threshold` → reports `status=WARN` with reason `LISTENER_STALE_OR_DISCONNECTED`
  - Normal → reports `status=OK` with "last_ingest Xs ago"

#### New File: `python/config/listener_meta.json`

Written by LISTENER on connect and updated each heartbeat/dispatch. Fields:
- `status` — `OK` | `WARN`
- `last_ingest_at` — ISO-8601 UTC of last processed message
- `signal_trade_rooms_active` / `signal_trade_rooms_count`
- `resolved_rooms[]` — per-channel `{chat_id, title, is_trade_room, match_reason}`

#### Startup Logging

LISTENER logs each resolved channel at startup with trade_room status:
```
LISTENER: channel -100xxx = 'Ben's VIP Club'  trade_room=True (ALLOWED_TITLE_MATCH)
LISTENER: channel -100yyy = 'Other Room'       trade_room=False (WATCH_ONLY_ROOM_FILTER)
```

#### ATHENA API Changes (`python/athena_api.py`)

- **`GET /api/channels`**: new fields per channel — `watch_only` (SCRIBE count), `is_trade_room`, `match_reason`; top-level — `signal_trade_rooms_active`, `listener_last_ingest_at`, `listener_status`.
- **`GET /api/channels/messages`**: new fields — `cache_age_sec` (mtime-based), `listener_stale` (true if cache > 3× refresh interval), `listener_last_ingest_at`, `listener_status`.

#### BRIDGE (`python/bridge.py`)

- AEGIS rejection `skip_reason` now prefixed with `AEGIS_REJECTED:` for unambiguous SCRIBE query filtering (was bare reject_reason string, indistinguishable from LENS/expiry skips).

#### Tests (`tests/api/test_listener_room_filter.py`) — new file, 21 tests

| Test class | Coverage |
|---|---|
| `TestIsTradeRoomAllowed` | empty allowlist; title case/whitespace/Unicode; chat_id variants (bare, -100 prefix, positive form); mismatch → WATCH_ONLY_ROOM_FILTER |
| `TestHandleMessageRoomFilter` | unallowed room → WATCH_ONLY + correct reason; old ROOM_NOT_PRIORITY absent; chat_id match dispatches despite title change; allowed room → SIGNAL_DISPATCHED event; empty allowlist → all dispatch |
| `TestParseFailed` | non-signal text → SIGNAL_PARSE_FAILED event; empty text → no PARSE_FAILED |
| `TestListenerStaleness` | `_last_ingest_at` updated on message; updated on dispatch; threshold config |
| `TestWatchOnlyEventDetails` | event notes contain channel+chat_id; reason field is structured code |

Updated `tests/api/test_vision_listener_aurum.py`: `test_non_priority_room_is_watch_only_in_signal_mode` assertion changed from `ROOM_NOT_PRIORITY` to `WATCH_ONLY_ROOM_FILTER`.

All 195 tests pass (`tests/api/` + `tests/services/`).

#### Documentation Updated

- `docs/SIGNAL_ROOM_POLICY.md` — new matching semantics, startup log to expect, `api/channels` quick check, updated verification queries for new reason codes, added `SIGNAL_DISPATCHED` / `SIGNAL_PARSE_FAILED` queries.
- `docs/DATA_CONTRACT.md` — `listener_meta.json`, `channel_names.json`, `channel_messages.json` added to file bus table; `listener_meta.json` shape documented.
- `docs/CLI_API_CHEATSHEET.md` — replaced `## Signal Channels` with `## Signal Channels & LISTENER Diagnostics`; added 60-second "no trades from room" runbook; AEGIS reject reasons updated to `AEGIS_REJECTED:` prefix; bridge.log grep patterns updated.

#### Runtime Verification

```bash
# Confirm room allowlist status after restart
curl -s http://localhost:7842/api/channels | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f'listener={d[\"listener_status\"]} last_ingest={d[\"listener_last_ingest_at\"]}')
[print(f'  {ch[\"name\"]}: trade_room={ch[\"is_trade_room\"]} match={ch[\"match_reason\"]} watch_only={ch[\"watch_only\"]}') for ch in d['channels']]
"

# Confirm no signals stuck in WATCH_ONLY unexpectedly
curl -s -X POST http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT channel_name, action_taken, skip_reason, COUNT(*) as n FROM signals_received GROUP BY channel_name, action_taken ORDER BY channel_name, n DESC"}' \
  | python3 -c "import sys,json; [print(r) for r in json.load(sys.stdin)['rows']]"
```

---

## [1.4.1] — 2026-04-10

### FORGE Threshold Hardening
- Added configurable runtime threshold parameters:
  - `pending_entry_threshold_points`
  - `trend_strength_atr_threshold`
  - `breakout_buffer_points`
- Native scalper logic hardened:
  - breakout trigger now uses previous M5 close + configurable breakout buffer
  - EMA trend filters normalized by ATR
  - TP split bug fixed (`BB_BREAKOUT` now uses breakout TP split config)
  - stop-level validation + lot normalization enforced before placement
  - spread-aware breakeven logic
  - cooldown timestamp updates on realized losses
  - startup rebuild of in-memory FORGE groups from open positions
- Added threshold + decision-metric telemetry into `market_data.json`, `mode_status.json`, and `scalper_entry.json`.

### BRIDGE + SCRIBE Persistence
- BRIDGE now writes threshold overrides into `MT5/config.json`.
- BRIDGE forwards native scalper threshold fields into SCRIBE `trade_groups`.
- LENS snapshot logging path now includes threshold fields from MT5 payload.
- SCRIBE schema/migrations extended with threshold fields in:
  - `market_snapshots`
  - `trade_groups`

### Tests and Verification
- Added `tests/api/test_threshold_persistence.py`:
  - migration checks on legacy DB shape
  - persistence checks for snapshot/group threshold fields
  - bridge forwarding checks for native scalper entries
- Verified with targeted and full API suite passes.

### Operations Improvements
- Added full lifecycle commands:
  - `make system-up` (TradingView → MetaTrader 5 → Python services)
  - `make system-down` (Python services → TradingView → MetaTrader 5)
- Added MT5 controls:
  - `make mt5-start`
  - `make mt5-stop`
- Hardened TradingView shutdown:
  - `make stop-tradingview` now force-kills and verifies termination.
- Added SCRIBE GUI helper:
  - `make scribe-gui` opens DB Browser for SQLite on `python/data/aurum_intelligence.db`.

### Documentation Updates
- Updated `docs/FORGE_BRIDGE.md` for threshold-hardening behavior and OFF_HOURS no-fill guidance.
- Updated `docs/DATA_CONTRACT.md` for `forge_config` threshold contract and `scalper_entry.json` metrics.
- Updated `docs/SETUP.md` + `docs/OPERATIONS.md` for SQLite GUI workflow and system lifecycle commands.
- Updated `SKILL.md` + `SOUL.md` for threshold-awareness and weekend/off-hours execution behavior.

---

## [1.4.0] — 2026-04-06

### FORGE Native Scalper Engine
- New `ScalperMode` input: `NONE` | `BB_BOUNCE` | `BB_BREAKOUT` | `DUAL`
- **BB Bounce** (ADX<20): buy at BB lower + RSI<35, sell at BB upper + RSI>65, H1 trend filter
- **BB Breakout** (ADX>25): breakout above/below BB + RSI + M5/M15 EMA alignment
- ATR-based SL/TP (1.2x for bounce, 1.5x for breakout), multi-TP with partial closes
- Safety guards: session filter (London+NY), spread<25pt, max 2 groups, loss cooldown
- DD event TP tightening: reads sentinel_status.json, tight TP at 0.8x ATR near news
- R:R minimum 1.2 enforced before every native entry
- Writes `scalper_entry.json` for BRIDGE to log to SCRIBE
- Fully backtestable in MT5 Strategy Tester
- `FORGE_SCALPER_MODE` controllable via `.env` → config.json (no reattach needed)

### Shared Scalper Config
- New `config/scalper_config.json` — BB bounce + breakout rules, session filter, safety guards
- Read by FORGE (MQL5) and AURUM (Python) for strategy consistency
- `make scalper-config-sync` copies config to MT5 Common Files

### AUTO_SCALPER Intelligence
- `format_for_aurum()` now includes BB position %, EMA distance, RSI momentum hints
- AUTO_SCALPER prompt includes decision framework (BUY/SELL/PASS criteria)
- BB squeeze detection (M5 BB range < 1.5x ATR = breakout imminent)
- AURUM context includes scalper_config.json parameters for consistency with FORGE

### Live Floating P&L on Dashboard
- Group tiles show real-time floating P&L from MT5 `open_positions[]` (3s refresh)
- Individual position boxes show entry price + per-position P&L
- Gold `LIVE` badge on groups with active MT5 positions
- Source badges: cyan `FORGE` / gold `AURUM` / orange `SIGNAL`

### BRIDGE Integration
- `_check_forge_scalper_entry()` reads scalper_entry.json from FORGE
- Native scalper trades logged to SCRIBE with `source=FORGE_NATIVE_SCALP`
- Herald Telegram alerts for native scalper entries with setup type + indicators

### Bug Fixes
- AURUM welcome message no longer stuck on "waiting for live data" after page load
- `_normalize_aurum_open_trade` method signature restored after edit corruption
- `AUTO_SCALPER` added to `contracts/aurum_forge.py` VALID_MODES + JSON Schema

---

## [1.3.1] — 2026-04-06

### SL/TP Hit Logging (trade_closures)
- New `trade_closures` SCRIBE table logs every position closure with full context
- `close_reason` inferred by BRIDGE: `SL_HIT`, `TP1_HIT`, `TP2_HIT`, `TP3_HIT`, `MANUAL_CLOSE`, `RECONCILER`, `UNKNOWN`
- BRIDGE `_infer_close_reason()` compares close price to SL/TP levels ($0.50 tolerance for XAUUSD)
- BRIDGE `_match_tp_stage()` resolves TP1/TP2/TP3 from trade_group record
- HERALD `tp_hit()` and `position_closed()` now called per position on SL/TP detection
- RECONCILER ghost positions logged to `trade_closures` with reason `RECONCILER`
- New API: `GET /api/closures?days=7&limit=50` — recent closures with reason
- New API: `GET /api/closure_stats?days=7` — aggregated SL vs TP hit rates
- `/api/live` extended with `recent_closures` (last 5, 24h) and `closure_stats` (7d)
- New ATHENA dashboard **Closures** tab with color-coded SL/TP tags and summary stat tiles
- `POSITION_MODIFIED` events categorized as TRADE in Activity panel (was hidden in SYSTEM)
- AURUM context includes last 5 closures and 7d SL/TP hit rate stats
- SCRIBE methods: `log_trade_closure()`, `get_recent_closures()`, `get_closure_stats()`, `get_open_positions_by_group()`
- Tab bar compacted for 5-tab fit; group position grid boxes reduced
- AURUM chat textarea auto-expands with word wrap (Shift+Enter for newlines)
- Agent.md added (gitignored) for AI tool project context
- Fixed pre-existing em-dash syntax error in scribe.py docstring
- Fixed DDL string split that left component_heartbeats outside the DDL block

### Documentation Updated
- `SKILL.md` — closure queries, closure context in injected state
- `SOUL.md` — trade closure detection knowledge, closure context awareness
- `docs/CLI_API_CHEATSHEET.md` — /api/closures, /api/closure_stats curl examples, SCRIBE closure queries
- `docs/SCRIBE_QUERY_EXAMPLES.md` — trade_closures table + 4 new example queries (#15–#18)
- `docs/DATA_CONTRACT.md` — trade_closures in persistence layer
- `CHANGELOG.md` — this entry

---

## [1.3.0] — 2026-04-06

### AUTO_SCALPER Mode
- New `AUTO_SCALPER` mode — AURUM (Claude) as autonomous decision engine
- BRIDGE polls AURUM every `AUTO_SCALPER_POLL_INTERVAL` (default 120s) with structured multi-TF prompt
- Pre-filters: H1 direction gate, RSI neutral screen, sentinel/max groups, loss cooldown
- AURUM responds with `OPEN_GROUP` JSON or `PASS: <reason>`
- Configurable: `AUTO_SCALPER_LOT_SIZE`, `AUTO_SCALPER_NUM_TRADES`, `AUTO_SCALPER_POLL_INTERVAL`, `AUTO_SCALPER_MAX_GROUPS`
- Dashboard mode button (green, "AURUM auto")

### Multi-Timeframe Indicators (FORGE)
- FORGE now exports `indicators_m5`, `indicators_m15`, `indicators_m30` alongside `indicators_h1`
- Each timeframe: RSI(14), EMA20, EMA50, ATR(14), BB upper/mid/lower, MACD histogram, ADX
- H1 expanded: added BB bands, MACD histogram, ADX (previously only RSI/EMA/ATR)
- New `market_view.py` module — unified MarketView combining FORGE + LENS data
- AURUM context now includes full multi-TF data with bias labels (BULL/BEAR/FLAT)

### Position Tracker (BRIDGE)
- BRIDGE now tracks individual position fills and closes from `market_data.json`
- New positions → `scribe.log_trade_position()` with ticket, magic, direction, lots, entry, SL/TP
- Disappeared positions → `scribe.close_trade_position()` with last-known P&L and estimated pips
- Group auto-rollup: when all positions/pendings gone → `update_trade_group()` with totals
- Seed from SCRIBE on startup to prevent duplicate logging after restarts
- Dedup guard: checks SCRIBE for existing ticket before inserting

### Drawdown Protection
- **Equity DD breaker** (BRIDGE): tracks session peak equity, CLOSE ALL + force WATCH if equity drops `DD_EQUITY_CLOSE_ALL_PCT` (default 3%) from peak. Telegram alert.
- **Floating P&L guard** (AEGIS): blocks new groups if floating loss ≥ `DD_FLOATING_BLOCK_PCT` (default 2%) of balance
- **Loss cooldown** (AUTO_SCALPER): pauses `DD_LOSS_COOLDOWN_SEC` (default 300s) after any position closes at a loss

### AEGIS Enhancements
- **H1 trend hard filter**: rejects BUY when H1 EMA20 < EMA50 (bearish), SELL when bullish. `AEGIS_H1_TREND_FILTER=true`
- **Per-signal `num_trades` override**: signals can include `num_trades` or `trades` (1–20) to override default 8
- **Lot override for AURUM/AUTO_SCALPER**: uses signal's `lot_per_trade` directly instead of risk-based sizing
- All previously hardcoded values now configurable: `AEGIS_MIN_LOT`, `AEGIS_PIP_VALUE_PER_LOT`, `AEGIS_MIN_SL_PIPS`
- `mt5_data` parameter added to `validate()` for H1 trend + floating DD checks

### Explicit Magic Number (SCRIBE)
- `magic_number` column added to `trade_groups` table
- BRIDGE stores `FORGE_MAGIC_BASE + group_id` explicitly (single source of truth)
- Reconciler and ATHENA read stored magic instead of computing `base + id`
- Auto-migration for existing databases
- `update_trade_group_magic()` method added to SCRIBE

### FORGE Bug Fixes
- `ExecuteCloseAll()` now cancels pending orders (limits/stops) in addition to closing filled positions
- Previously only iterated `PositionsTotal()`, missed `OrdersTotal()`

### BRIDGE Bug Fixes
- AURUM CLOSE_ALL now updates SCRIBE groups + clears cache (was missing, only wrote FORGE command)
- `num_trades`/`trades` from AURUM commands now passed through to AEGIS (was silently ignored)
- AURUM dispatch now accepts AUTO_SCALPER as valid effective_mode

### Reconciler Improvements
- FORGE version guard: skips stale-group close if `forge_version` < 1.2.4 (pending_orders not exported before that)
- Uses stored `magic_number` from SCRIBE instead of computing `base + id`

### AURUM Enhancements
- Context now includes full multi-TF indicators (M5/M15/M30/H1) with BB bands, MACD, ADX, EMA levels
- Context includes MT5 H1 ATR with sizing guidance ("use 1.5×ATR for SL")
- SKILL.md: scalping TP distance rules ($2–$5 for TP1, $5–$10 for TP2, never $10+ for scalps)
- SKILL.md: H1 alignment rule (never scalp against H1 EMA direction)
- SKILL.md: AUTO_SCALPER tick response format
- SOUL.md: AUTO_SCALPER role section (decision engine vs rules engine)
- Hot-reload: AURUM re-reads SKILL.md + SOUL.md from disk on every query (no restart needed)

### New Files
- `python/market_view.py` — unified FORGE + LENS market data object
- `docs/CLI_API_CHEATSHEET.md` — curl + python one-liners for all API endpoints

### Mode Persistence Across Restarts
- BRIDGE now restores previous mode from `status.json` on restart (default: enabled)
- `RESTORE_MODE_ON_RESTART=true` (default) — reads saved mode from status.json
- `RESTORE_MODE_ON_RESTART=false` — uses FORGE `requested_mode` or `DEFAULT_MODE` from .env
- Mode changes via API (`POST /api/mode`) write directly to status.json for immediate persistence
- CLI `--mode` from launchd plist only used as fallback when no saved state exists

### TP Split at Order Placement
- FORGE now splits TP targets at open: 75% of positions get TP1, 25% get TP2
- Split ratio controlled by `TP1_CLOSE_PCT` (default 70%)
- When TP1 hits (broker-side): 75% close automatically, remaining positions get SL→BE + TP→TP2
- Comment field shows TP target: `FORGE|G14|0|TP1` or `FORGE|G14|3|TP2`
- No more "all positions close at TP1" problem

### Signal Parser API
- New `POST /api/signals/parse` — test Claude Haiku parser via API without Telegram
- Input: `{"text": "SELL Gold @4691-4701 SL:4706 TP1:4687"}` → returns structured JSON
- Supports ENTRY, MANAGEMENT (CLOSE_ALL, CLOSE_PCT, MODIFY_SL, MODIFY_TP, TP_HIT), and IGNORE

### OpenAPI Spec v1.3.0
- 7 new endpoints added to `schemas/openapi.yaml`
- Management examples expanded with all 9 intents
- Swagger UI at `/api/docs/` fully updated

### Signal Lifecycle (Scalping)
- Signal expiry: `SIGNAL_EXPIRY_SEC=60` — stale signals rejected as EXPIRED
- Pending order timeout: `PENDING_ORDER_TIMEOUT_SEC=120` — unfilled limit orders auto-cancelled after 2min
- Telegram alert `⏰ PENDING EXPIRED` sent when orders timeout
- Full lifecycle: signal → AEGIS → FORGE → fill/timeout → SL/TP → SCRIBE → Telegram close alert

### Scalping-Aware Trend Cascade
- AEGIS trend filter now source-aware with multi-TF cascade
- **SIGNAL source** (channel scalps): M5 → M15 → H1. M5 is primary — if M5 agrees (or is FLAT), trade passes even if H1 disagrees
- **AURUM/AUTO_SCALPER**: H1 → M15 cascade (conservative)
- **SCALPER** (BRIDGE): H1 only (strictest)
- FLAT (EMA20 ≈ EMA50 within $1) counts as agreement — allows entry in either direction
- Replaces the old single-H1 filter that was too strict for scalping signals

### FORGE Reload Make Target
- New `make forge-reload` — compile + restart MT5 + auto-detect if EA loaded
- If FORGE auto-loads: prints ✅ and version. If not: prints reattach instructions
- Note: MT5 on Wine/macOS does NOT reliably auto-restore EAs after restart
- Manual reattach still required in most cases (Wine limitation)

### FORGE Architecture Comments
- Comprehensive architecture overview added to FORGE.mq5 header (50+ lines)
- Documents: data flow, command actions, market data output, TP split, magic numbers
- Section comments on: input parameters, globals, indicator handles, group tracking, symbol matching

### Sentinel Pre-Alert
- New Telegram warning when HIGH-impact event is ≤35min away but guard not yet active
- Message: `⚠️ Guard activating soon! {event} in {min}min`
- Fires with the 10-min adaptive digest cycle

### Sentinel Event Digest (Adaptive)
- SENTINEL sends upcoming HIGH-impact events to Telegram with adaptive timing
- **> 30 min away**: digest every 30 min. **≤ 30 min**: every 10 min. **Guard active**: immediate alerts
- Shows event name, currency, minutes away, and guard status
- Only sends when HIGH-impact events are within 4 hours
- Override interval via `POST /api/sentinel/digest {"interval": 30}` (reverts on restart)

### Telegram Close Alerts
- HERALD now sends `GROUP CLOSED` notifications with P&L summary when groups close
- Fires from both paths: position tracker (SL/TP) and management commands (manual close)
- `trade_group_closed()` and `position_closed()` templates added to HERALD

### Sentinel Override
- New `POST /api/sentinel/override` endpoint — temporarily bypass sentinel news guard
- Configurable duration (60s–3600s), defaults to `SENTINEL_OVERRIDE_DURATION_SEC=600`
- Auto-reverts after timeout — logged as `SENTINEL_OVERRIDE_EXPIRED` in SCRIBE
- BRIDGE handles `SENTINEL_OVERRIDE` action via aurum_cmd.json
- Telegram alert on override and expiry

### Smart Position Closing
- New FORGE commands: `CLOSE_GROUP`, `CLOSE_GROUP_PCT`, `CLOSE_PROFITABLE`, `CLOSE_LOSING`
- Group-targeted: close/partial-close only one group's positions by magic number
- Profit/loss filtering: close only winners or only losers across all groups
- BRIDGE resolves group_id → magic_number via SCRIBE for all group commands
- `POST /api/management` now accepts `group_id` parameter for group-targeted commands
- Dashboard group tile buttons now group-specific (Close Group / Close 70% target the specific group, not all)

### Signal Channels (LISTENER)
- Fixed: channel IDs parsed as integers (was strings → Telethon `ValueError`)
- Signals now logged to SCRIBE in ALL modes (not just SIGNAL/HYBRID) — only dispatch is gated
- New `GET /api/channels` endpoint — configured channels with Telethon-resolved names + signal stats
- New `GET /api/channels/messages` endpoint — recent messages from all channels (cached by LISTENER)
- LISTENER resolves channel names on connect → writes `config/channel_names.json`
- LISTENER caches last 10 messages per channel → `config/channel_messages.json` (refreshes every 5min)
- Dashboard signals tab redesigned: channel name badge on each row, channel filter strip, two-line card layout

### Documentation Updated
- `SOUL.md` — AUTO_SCALPER role, multi-TF context, drawdown protection
- `SKILL.md` — complete context spec, scalping rules, AUTO_SCALPER tick format
- `docs/AEGIS.md` — new guards table, per-signal overrides, DD env vars
- `docs/FORGE_BRIDGE.md` — multi-TF indicators, position tracker, CLI cheat sheet link
- `docs/CLI_API_CHEATSHEET.md` — channel polling commands, all curl examples
- `CHANGELOG.md` — this entry

---

## [1.2.0] — 2026-04-05

### Architecture: API-First Dashboard
All data displayed in ATHENA now flows through the Flask API.
No hardcoded mock data remains in the dashboard.

**Rule enforced:**
Component → SCRIBE/JSON file → Flask endpoint → Dashboard

### Added
- `SCRIBE.component_heartbeats` table — one row per component,
  upserted on every cycle, tracks status/note/last_action/error
- `Scribe.heartbeat()` method — upsert current component state
- `Scribe.get_component_heartbeats()` method — read all heartbeats
- `GET /api/components` — dedicated component health endpoint,
  returns all 11 components including FORGE (synthesised from
  MT5 JSON) and ATHENA (self-reported)
- `GET /api/reconciler` — exposes last reconciler run result
- `GET /api/signals` — signal history endpoint (fixed missing route)
- Heartbeat calls in: bridge, sentinel, lens, aegis, listener,
  herald, aurum, reconciler
- `reconciler.py` writes `config/reconciler_last.json` after
  each run for the API to serve
- DEMO/LIVE account type badge in ATHENA header
- Circuit breaker warning banner in ATHENA left column
- Null-safe rendering for all numeric values (shows '—' not crash)
- `aegis` block in `/api/live` — scale_factor, streak, session_pnl
- `components` dict in `/api/live` — latest heartbeat per component
- `reconciler` block in `/api/live` — last reconciler result
- `account_type`, `broker`, `server` in `/api/live` from broker_info.json
- `circuit_breaker` boolean in `/api/live`

### Changed
- `/api/live` — expanded to include all system state in one payload
- `dashboard/app.js` — now fetches `/api/components` and `/api/events`
- `dashboard/app.js` — COMP_STATUS and MOCK_EVENTS removed
- `dashboard/app.js` — ActivityLog accepts `events` and `components`
  as props instead of internal mock state
- `dashboard/app.js` — System Health panel driven by live API data
- `dashboard/app.js` — fallback D object uses null values not zeros
- `athena_api.py` — all file paths now absolute (resolve correctly
  regardless of working directory)

### Fixed
- LENS_MCP_CMD path in .env verified correct
- MT5 symlink at project root verified working
- Path mismatch: config/ files correctly resolved to python/config/
  (WorkingDirectory=python/), MT5/ files resolved to project root
- Missing `@app.route` decorator on `api_signals` function

### Added: Test Framework
- `tests/api/test_live.py` — 12 tests for /api/live
- `tests/api/test_endpoints.py` — health, sessions, performance, mode, events
- `tests/api/test_components.py` — /api/components all 11 present
- `tests/api/test_aurum.py` — AURUM chat endpoint (marked slow)
- `tests/conftest.py` — shared fixtures, base URL config
- `tests/requirements-test.txt` — pytest, requests, python-dotenv
- `tests/playwright.config.js` — Chrome, localhost:7842, HTML report
- `tests/package.json` — Playwright dev dependency
- `tests/ui/test_dashboard.spec.js` — dashboard load, panels
- `tests/ui/test_panels.spec.js` — activity log, trade groups,
  AURUM chat, mode control, LENS panel

### Added: Scripts and Shortcuts

**scripts/ directory (all Python, platform-agnostic):**

| Script | Purpose | Key flags |
|--------|---------|-----------|
| `health.py` | System health check | `--watch` `--json` |
| `test_api.py` | Run pytest API tests | `--file` `--all` `--html` |
| `test_ui.py` | Run Playwright tests | `--headed` `--debug` `--record` `--report` |
| `test_all.py` | Run all tests | `--api` `--ui` `--ci` |
| `logs.py` | View service logs | `--follow` `--errors` `--lines N` |
| `setup_tests.py` | Install test deps | `--check` |

**Makefile targets:**
`make help`, `make health`, `make test`, `make test-api`,
`make test-ui`, `make logs`, `make logs-bridge`, `make start`,
`make stop`, `make restart`, `make setup-tests`

**Shell aliases (added to ~/.zshrc):**
`ss-health`, `ss-watch`, `ss-status`, `ss-test`, `ss-test-api`,
`ss-test-ui`, `ss-test-silent`, `ss-report`, `ss-record`,
`ss-logs`, `ss-logs-bridge`, `ss-logs-listener`, `ss-logs-aurum`,
`ss-logs-errors`, `ss-start`, `ss-stop`, `ss-restart`, `ss`

---

## [1.1.0] — Earlier

### Added
- `RECONCILER` component — hourly position audit
- `trading_sessions` table in SCRIBE
- Session column on all SCRIBE tables
- `FORGE.WriteBrokerInfo()` — writes broker_info.json on startup
- `InputMode` parameter in FORGE EA dialog
- `BRIDGE._on_session_change()` — session transition detection
- `/api/sessions` and `/api/sessions/current` endpoints
- `/api/channel_performance` endpoint
- `/api/aegis_state` endpoint
- Circuit breaker in BRIDGE for MT5 staleness
- Dynamic lot scaling in AEGIS (scale down after losses)
- Session-aligned daily loss reset in AEGIS
- AURUM conversation memory from SCRIBE
- macOS launchd services for all 4 processes
- Linux systemd service files

## [1.0.0] — Initial Release

### Components
- BRIDGE, FORGE, LISTENER, LENS, SENTINEL, AEGIS,
  SCRIBE, HERALD, AURUM, ATHENA

### Core Features
- Signal room following via Telegram (Telethon)
- Claude API parsing of any signal format
- Layered entry: N trades across price zone
- TP1 partial close + SL to breakeven
- TradingView MCP integration (LewisWJackson)
- 5 operating modes: OFF/WATCH/SIGNAL/SCALPER/HYBRID
- SQLite database with 8 tables
- Flask API + React dashboard
