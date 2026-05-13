# FORGE Indicators & Calculated Atoms — v2.7.58 to v2.7.68 Additions

**Created**: 2026-05-13 during operator-driven sprint
**Scope**: All new indicators / atoms / gates added in v2.7.58–v2.7.68 (10 shipped versions)
**Companion docs**: `FORGE_INDICATOR_ATLAS.md` (canonical full inventory, 1329 lines)

This is a focused supplement covering what was added recently. For the full inventory of every indicator FORGE uses, see the atlas.

---

## Quick reference — where to find each new atom

| Layer | Where exposed | Source |
|---|---|---|
| **Live state (real-time)** | `market_data.json` → `entry_atoms` block | `WriteMarketData` in `ea/FORGE.mq5:3174+` |
| **Per-trade log** | `SIGNALS` table columns | `JournalRecordSignal` in `ea/FORGE.mq5:7548+` |
| **Computed per tick** | `g_eval_*` globals | `ForgeEvalAtoms` in `ea/FORGE.mq5:5590+` |

---

## §1. Velocity / Momentum Atoms (v2.7.65)

Measure HOW FAST price is moving. Direction-agnostic except where signed.

| Atom | Formula | Threshold meaning | Source |
|---|---|---|---|
| `m5_velocity_1bar` | `\|close[0] − close[1]\| / atr` | >0.8 = fast single bar (NY open spike) | M5 close + ATR |
| `m5_velocity_5bar` | `\|close[0] − close[5]\| / atr` | >2.0 = impulsive 25-min move; <0.3 = chop | M5 close + ATR |
| `m5_adx_delta_5bar` | `adx[0] − adx[5]` | >+5 = momentum strengthening; <−5 = fading | iADX M5 |
| `m5_macd_slope_5bar` | `(macd[0] − macd[5]) / atr` | **SIGNED**: positive = bull momentum, negative = bear | iOsMA M5 |
| `m5_atr_ratio_5bar` | `atr[0] / atr[5]` | >1.3 = volatility expansion (impulse); <0.85 = contraction | iATR M5 |

**Used in**: TC_BUY/SELL gates (v2.7.67), available for MD V2 future expansion.

---

## §2. ICT/SMC Market Formation Atoms (v2.7.68)

Price structure detection per Smart Money Concepts. Closed-bars only (non-repainting). 30-bar M5 lookback. 5-bar fractal (N=2) for swing detection.

### Swing pivots

| Atom | Formula | Use |
|---|---|---|
| `last_swing_high_price` | Bar i.high > bars [i±1, i±2].high (5-bar fractal) | Resistance target / BOS trigger |
| `last_swing_low_price` | Bar i.low < bars [i±1, i±2].low | Support target / BOS trigger |
| `last_swing_high_bars_ago` | M5 bars since most recent swing high (-1 = none in 30-bar window) | Recency |
| `last_swing_low_bars_ago` | Same for low | Recency |

### Break of Structure (BOS)

| Atom | Formula | Use |
|---|---|---|
| `bos_direction` | `+1` if M5 close > last swing high within 10 bars; `-1` if close < swing low; `0` otherwise | Trend continuation confirmation |
| `bos_bars_ago` | M5 bars since BOS confirmation (-1 = none) | Recency |

### Fair Value Gap (FVG) — 3-bar imbalance

| Atom | Formula | Use |
|---|---|---|
| `bullish_fvg_low` / `bullish_fvg_high` | `bar[i+2].low > bar[i].high` (gap up; bar i+1 spans gap) | Bullish target / retest zone |
| `bearish_fvg_low` / `bearish_fvg_high` | `bar[i+2].high < bar[i].low` (gap down) | Bearish target |

### Order Block (OB) — last opposing candle before move

| Atom | Formula | Use |
|---|---|---|
| `last_bullish_ob_low` | Last bearish candle (close<open) followed by 2+ bullish candles closing above high | Bull support / accumulation zone |
| `last_bearish_ob_high` | Last bullish candle followed by 2+ bearish candles closing below low | Bear resistance / distribution |

### Liquidity Sweep

| Atom | Formula | Use |
|---|---|---|
| `liquidity_sweep_recent` | `+1` = wick above swing high but close BELOW (buy-side sweep); `-1` = wick below swing low but close ABOVE (sell-side sweep); `0` = none in last 5 bars | Reversal signal |

**Used in**: Not yet — exposed for future composite gates (queued v2.7.69+).

---

## §3. TC_BUY/SELL Decision-Tree Atoms (v2.7.58 + v2.7.67)

Composite gates added to TREND_CONTINUATION_BUY/SELL triggers. All default-ON.

### v2.7.58 — Initial atom expansion

| Atom | Direction | Type | Default |
|---|---|---|---|
| `trend_continuation_buy_require_macd_positive` | BUY | bool | true |
| `trend_continuation_buy_macd_min` | BUY | double | 0.0 (any positive) |
| `trend_continuation_buy_require_above_vwap` | BUY | bool | true |
| `trend_continuation_buy_max_poc_distance_atr` | BUY | double | 1.5 |
| `trend_continuation_buy_block_bearish_div` | BUY | bool | true |
| `trend_continuation_buy_require_h4_alignment` | BUY | bool | true |
| `trend_continuation_buy_h4_min` | BUY | double | 0.0 |
| (mirrored for SELL with sign flips) | SELL | | |

### v2.7.67 — Velocity / DI / day-extreme expansion

| Atom | Direction | Default |
|---|---|---|
| `trend_continuation_require_velocity_check` | both | true (master toggle) |
| `trend_continuation_min_adx_delta_5bar` | both | 0.0 (ADX must be rising) |
| `trend_continuation_min_velocity_5bar` | both | 0.5 (≥0.5×ATR move in 25min) |
| `trend_continuation_buy_min_macd_slope_5bar` | BUY | +0.2 |
| `trend_continuation_sell_max_macd_slope_5bar` | SELL | −0.2 |
| `trend_continuation_buy_min_di_balance` | BUY | 0.0 (DI+ > DI−) |
| `trend_continuation_sell_max_di_balance` | SELL | 0.0 (DI+ < DI−) |
| `trend_continuation_buy_max_dist_from_day_high_atr` | BUY | 0.5 (not at top) |
| `trend_continuation_sell_max_dist_from_day_low_atr` | SELL | 0.5 (not at bottom) |

---

## §4. MOMENTUM_DUMP V2 Composite Atoms (v2.7.60 + v2.7.61)

### v2.7.60 — MD V2 composite (catch G5001/G5002, block G5003)

| Atom | Direction | Default |
|---|---|---|
| `dump_v2_enabled` | both | true (master) |
| `dump_sell_h4_max` | SELL | 0.0 (H4 bearish/neutral) |
| `dump_buy_h4_min` | BUY | 0.0 (H4 bullish/neutral) |
| `dump_sell_macd_max` | SELL | 0.0 |
| `dump_buy_macd_min` | BUY | 0.0 |
| `dump_sell_vwap_atr_min` | SELL | 0.3 (price ≤ VWAP − 0.3×ATR) |
| `dump_buy_vwap_atr_min` | BUY | 0.3 (price ≥ VWAP + 0.3×ATR) |
| `dump_sell_poc_atr_min` | SELL | 0.3 |
| `dump_buy_poc_atr_min` | BUY | 0.3 |
| `dump_max_adx` | both | 42 (exhaustion ADX ceiling) |
| `dump_sell_late_rsi_block` | SELL | 36 (exhaustion: ADX≥42 AND RSI≤36) |
| `dump_buy_late_rsi_block` | BUY | 64 (exhaustion: ADX≥42 AND RSI≥64) |

### v2.7.61 — Day-extreme block

| Atom | Direction | Default |
|---|---|---|
| `dump_buy_max_dist_from_day_high_atr` | BUY | 0.5 (block if within 0.5×ATR of day high) |
| `dump_sell_max_dist_from_day_low_atr` | SELL | 0.5 (block if within 0.5×ATR of day low) |

### v2.7.62 — Day-extreme distance amplifier (reward room-to-run)

| Atom | Default |
|---|---|
| `dump_dist_amplifier_enabled` | true |
| `dump_dist_amplifier_threshold_atr` | 1.5 (Tier 1) |
| `dump_dist_amplifier_factor` | 1.5× (mid-range zone) |
| `dump_dist_amplifier_strong_threshold_atr` | 3.0 (Tier 2) |
| `dump_dist_amplifier_strong_factor` | 2.0× (deep-room zone) |

---

## §5. Killzone Tier Amplifier (v2.7.63 + v2.7.65 recalibration)

ICT killzone-tier lot amplifier based on `minutes_into_kz`. Atoms read `g_regime.killzone` + `g_regime.minutes_into_kz` (already populated each tick).

| Window | Factor (default) |
|---|---|
| 0-5 min (Tier 1, peak) | 2.0× |
| 5-15 min (Tier 2, peak extended) | 2.0× |
| 15-30 min (Tier 3, strong) | 1.5× |
| 30-60 min (Tier 4, normal) | 1.0× |
| 60+ min (Tier 5, fade) | 0.85× |
| Between KZs (dead zone) | 0.5× (fractional, not block) |

---

## §6. BLR_BUY Falling-Knife Protection (v2.7.59)

Added to BB_LOWER_REVERSION_BUY composite.

| Atom | Default | Purpose |
|---|---|---|
| `bb_lower_reversion_buy_require_reversal_candle` | true | Require last M5 close > open (no entry during freefall) |
| `bb_lower_reversion_buy_consec_loss_max` | 2 | After 2 SLs, throttle |
| `bb_lower_reversion_buy_consec_loss_window_sec` | 1800 | 30-min counter window |
| `bb_lower_reversion_buy_consec_loss_cooldown_sec` | 1800 | 30-min throttle duration |
| `bb_lower_reversion_buy_h4_min` | −1.0 | Block when H4 trend ≤ this (strongly bearish HTF) |

---

## §7. Pyramid (v2.7.56 → v2.7.66 reshape)

| Atom | v2.7.56 (escalating, WRONG) | v2.7.66 (decreasing, CANONICAL) |
|---|---|---|
| `dump_pyramid_base_factor` | 1.0 | **5.0** (start big) |
| `dump_pyramid_step` | +1.0 | **−1.0** (decrease) |
| `dump_pyramid_max_factor` | 5.0 | 5.0 (ceiling unchanged) |
| `dump_pyramid_min_factor` | (none, clamped at base) | **1.0** (floor) |

Sequence: 5×, 4×, 3×, 2×, 1×, 1×, ... (canonical decreasing pyramid)

---

## §8. SL / TP Geometry (v2.7.58 → v2.7.66)

| Setup | SL (v2.7.66) | TP1 | TP2 | TP1 close % |
|---|---|---|---|---|
| MOMENTUM_DUMP BUY | 3.5×ATR | 0.7×ATR | 2.5×ATR | 70% |
| MOMENTUM_DUMP SELL | 3.5×ATR | 0.7×ATR | 2.5×ATR | 70% |
| TREND_CONTINUATION_BUY | 2.5×ATR | 0.7×ATR | 1.4×ATR | 60% (default) |
| TREND_CONTINUATION_SELL | 2.5×ATR | 0.7×ATR | 1.4×ATR | 60% |
| BB_LOWER_REVERSION_BUY | 2.5×ATR | bb_m | bb_u | 60% |

R:R math: weighted_win = 0.7×0.7 + 2.5×0.3 = 1.24; loss = 3.5; **breakeven WR ≈ 74%**.

---

## §9. macd_histogram Bug Fix (v2.7.63)

Critical bug in v2.7.62: macd_histogram defaulted to 0.0 in JournalRecordSignal → 17,940 SIGNALS rows logged 0 → V2 MD SELL gate `_md_macd >= 0` was always TRUE → blocked all SELLs.

**Fix**: self-populate macd inside JournalRecordSignal via CopyBuffer(g_h_osma_scalp). Hardened with iMACD fallback (g_mtf[0].h_macd) + on-tick handle re-init + diagnostic Print.

**Result**: macd_histogram column now always reflects real broker data.

---

## §10. market_data.json Live State Visibility (v2.7.64)

Added `entry_atoms` block exposing 27+ internal atoms to live JSON. Three tiers:

- **Tier 1**: h1/h4/m5/m15/m30 trend strengths, regime, KZ minutes, day extremes, daily bias
- **Tier 2**: DI atoms, htf_h1_strong, adx_trend_regime, intraday label
- **Tier 3**: M5 candle patterns (lh_cascade, body_pct, wicks, doji, range_expanding)

Plus subsequent additions:
- Velocity atoms (v2.7.65): 5 atoms
- ICT atoms (v2.7.68): 13 atoms

**Current entry_atoms total**: ~45 fields.

---

## §11. Time-Gate Removal (operator: "let conditions decide")

All time-based blocking gates removed across v2.7.62-v2.7.67:

| Knob | Before | After |
|---|---|---|
| `dump_cooldown_seconds` | 60 | **0** |
| `bb_lower_reversion_buy_cooldown_seconds` | 180 | **0** |
| `trend_continuation_buy_cooldown_seconds` | 60 | **0** |
| `trend_continuation_sell_cooldown_seconds` | 60 | **0** |
| `bull_day_dip_buy_reentry_cooldown_sec` | 300 | **0** |
| `dump_max_hold_seconds` (time-stop on positions) | 600 | **0 (disabled)** |
| `bb_lower_reversion_buy_max_hold_seconds` | 1800 | **0 (disabled)** |
| `staged_add_interval_sec` | 25 | **5** (sub-second flood prevention only) |
| `staged_add_min_favorable_points` | 500 | **100** (~1pt favorable = leg fires) |

KZ tier amplifier is **NOT a time gate** — it scales lot, never blocks.

---

## §12. Stack at Peak NY KZ Open (worked example)

```
T+0  (NY KZ minutes_into_kz=0, Tier 1 = 2.0×):
  Setup armed → MOMENTUM_DUMP V2 atoms ALL align (h4≤0, macd<0, price<VWAP, price<POC,
                                                    NOT exhausted, not at day-low)
  → Legs 1-3 fire IMMEDIATELY (staged_initial_legs=3)
  → Lot factors: 5× + 4× + 3× = 12× combined pyramid
  → × KZ tier 2.0× × distance amp ≤2× = up to 48× base @ T+0

T+5s : Leg 4 fires (2× pyramid, conditions still met)
T+10s: Leg 5 fires (1× pyramid floor)
T+15-45s: Legs 6-10 fire (all 1× floor)

Final position by T+45s if move sustains:
  10 legs filled
  Total exposure ≈ 20× base × KZ tier × distance amp = up to 80× peak
  SL: 3.5×ATR (judas swing absorber)
  TP1: 0.7×ATR (70% closes — fast bank)
  TP2: 2.5×ATR (30% runner — April-day big-move capture)
```

---

## §13. References

- **Atlas**: `docs/FORGE_INDICATOR_ATLAS.md` (canonical full inventory)
- **Decision stack**: `FORGE_DECISION_STACK.md`
- **Playbook**: `FORGE_SETUP_PLAYBOOK.md`
- **Live JSON**: `~/.../market_data.json` (read every tick)
- **SIGNALS DB**: `~/.../FORGE_journal_XAUUSD_tester.db`

### MQL5 research sources

- [BoS strategy](https://www.mql5.com/en/articles/15017)
- [SMC: OB, BOS, FVG](https://www.mql5.com/en/articles/16340)
- [Liquidity sweep on BOS](https://www.mql5.com/en/articles/20569)
- [ATR pyramid 2×ATR rule (Trade That Swing)](https://tradethatswing.com/trend-trading-strategy-for-high-momentum-stocks-atr-based/)
- [Decreasing pyramid (JustMarkets)](https://justmarkets.com/trading-articles/forex/what-is-pyramiding-in-trading)
- [MACD Slope as lead indicator (TradingView)](https://www.tradingview.com/script/INJYo1xh-MACD-Slope/)

---

## §14. Changelog (append-only)

| Version | Date | Summary |
|---|---|---|
| v2.7.58 | 2026-05-13 | TC_BUY atom expansion (MACD/VWAP/POC/RSI-div/H4) + G5003 SELL-in-bull fix |
| v2.7.59 | 2026-05-13 | BLR_BUY falling-knife protection + MD cascade enable |
| v2.7.60 | 2026-05-13 | MD V2 composite (catch G5001/G5002, block G5003 via ADX-RSI exhaustion) |
| v2.7.61 | 2026-05-13 | Day-extreme distance gate (Apr 13 top-of-range BUYs fix) |
| v2.7.62 | 2026-05-13 | Day-extreme distance amplifier (reward G5092 deep-room entries) |
| v2.7.63 | 2026-05-13 | Fix macd_histogram=0 bug (silent V2-SELL blocker) + KZ tier amplifier |
| v2.7.64 | 2026-05-13 | Live state visibility (entry_atoms block in market_data.json) |
| v2.7.65 | 2026-05-13 | Velocity atoms (ADX delta, MACD slope, ATR ratio, displacement) + KZ recal + wide SL |
| v2.7.66 | 2026-05-13 | DECREASING pyramid (5×→1×) + wide TP matching wide SL |
| v2.7.67 | 2026-05-13 | TC velocity/DI/day-extreme expansion + staged-add throttle removal |
| v2.7.68 | 2026-05-13 | ICT/SMC market-formation atoms (swing/BOS/FVG/OB/liquidity) |
