# FORGE Entry Conditions — v2.7.15

**EA version**: FORGE v2.7.15 | **Symbol**: XAUUSD M5
**Source**: ea/FORGE.mq5 + config/scalper_config.json
*All values read directly from code and config — not estimated.*
*Last updated: 2026-05-10 (post-Run 12 + Codex review)*

## Changelog since v2.7.13

| Version | Change | Rationale |
|---|---|---|
| **v2.7.15** | M5-bar throttle for `entry_quality_rsi_buy_ceil` (global `g_scalper_last_rsibuyceil_log_bar`) | Run 12 logged 3,386 SKIPs from only 2 distinct M5 bars (per-tick flood) — corrupted Q9 gate-precision math to a false 0%. Throttle restores meaningful precision measurement. |
| **v2.7.14** | H1 strong-bear bypass (`h1_trend < -1.0`) added to `entry_quality_rsi_sell_adx_floor` and `entry_quality_rsi_rising_sell` | Run 12 missed Apr 29 15:55/16:00 SELLs that had H1=-1.91/-1.99 (strongest bearish H1 of the period). The two-tier RSI floor and RSI-rising checks fire as if the trend is unconfirmed even when H1 dominates. Bypass keeps May 4 17:10 G5008 blocked (H1=-0.55, bypass inactive). |
| **v2.7.14** | M5-bar throttle for `entry_quality_direction` + `entry_quality_body` (per direction — separate globals for SELL and BUY) | Two M5 bars on Apr 29 generated 2,583 direction SKIP rows from per-tick logging. Same flood-pattern fix as v1.8.6 session_off. |
| **v2.7.13** | `block_hid_bull_sell=1` — `entry_quality_hid_bull_div_sell` gate | Blocks SELL when RSI_DIV=HID_BULL is active. Catches the G5008 May 4 17:10 -$940 catastrophe pattern. |
| **v2.7.13** | `h1h4_crash_sell_min_m15_adx=25` added to `crash_sell_bypass` | Crash bypass now requires M15 ADX ≥25 (genuine multi-TF trend). Prevents M5 ADX spike-from-flat patterns from skipping the RSI floor gate. |
| **v2.7.13** | `require_macd_buy=1` | Requires H1 MACD histogram positive before BUY breakout fires. |
| **v2.7.13 bugfix** | HID_BULL throttle: `static datetime` inside if-block → global `g_scalper_last_hbd_log_bar` | MQL5 disallows static-in-nested-block; symptom was unclickable inputs dialog in MT5. |

---

## Indicators Used

| Indicator | Timeframe | Period | Role |
|---|---|---|---|
| Bollinger Bands (BB) | M5 | 20, 2σ | Entry trigger (price vs upper/lower band) |
| RSI | M5 | 14 | Momentum filter — direction and extremes |
| ADX (main) | M5 | 14 | Trend strength — gates entry, drives leg count |
| ADX (DI+/DI−) | M5 | 14 | ADX spike-from-flat detection (lookback gate) |
| ADX (main) | M15 | 14 | Crash bypass confirmation, bounce gate override |
| ATR | M5 | 14 | SL/TP sizing, lot normalisation |
| EMA 20/50 | M5 | 20, 50 | M5 trend direction (m5_bull/bear) |
| EMA 20/50 | M15 | 20, 50 | M15 confirmation (m15_bull/bear/flat) |
| EMA 20/50 | M30 | 20, 50 | M30 bearish confirmation gate for SELL |
| EMA 20/50 | H1 | 20, 50 | H1 trend direction + Cardwell strength |
| ADX (DI+/DI−) | H1 | 14 | H1 Wilder directional gate (BUY and SELL) |
| OsMA (3,10,16) | M5 | — | MACD histogram 4-quadrant gate (both dirs) |
| MACD (12,26,9) | H1 | — | H1 momentum confirmation (optional gate) |
| RSI divergence | M5 | 20-bar swing | Hidden/regular divergence detection |
| EMA 20/50 | H4 | 20, 50 | H4 trend alignment (optional H4 gates) |

---

## Full Lot Conditions

Full lot = **0.08 per leg** when `combined_lot_factor = 1.0`.

| Factor | Condition for 1.0 | When reduced |
|---|---|---|
| `inside_band_factor` | BUY always. SELL: price below BB lower | SELL inside BB band → `breakout_sell_inside_band_lot_factor=0.25` |
| `near_floor_factor` | No crash-bypass, or RSI > 25 | SELL crash-bypass + RSI 20–25 → `breakout_near_floor_lot_factor=0.25` |
| `stack_factor` | First group open in that direction | 2nd concurrent same-direction group → `same_direction_stack_lot_factor=0.25` |
| `adx_lot_factor` | BUY always 1.0. SELL: ADX < `adx_lot_mid_threshold` (35) | SELL ADX 35–44 → `adx_lot_factor_mid=1.0` (no reduction). SELL ADX ≥45 → **0.5×** (`adx_lot_factor_high=0.5`). EA checks **high first then mid** as `if(high) else if(mid)` at `FORGE.mq5:5875-5877` — non-overlapping thresholds make the order behaviorally identical. M5 vs M15 ADX selectable via `breakout_adx_lot_use_m15=1` (default — uses M15) |
| `bounce_factor` | BB_BREAKOUT setup | BB_BOUNCE → `bounce_lot_factor=0.25` |

**Lot factor note**: `adx_lot_factor_high=0.5` at M15 ADX ≥45 for SELL — limits damage on high-ADX reversal entries. In Run 11 G5007 (M5 ADX=37.4 at entry; M15 ADX retroactively unverifiable because SIGNALS logged m15_adx=0 for SKIP rows in v2.7.12), the tier was likely `factor_mid=1.0` (M5 ADX 35-44) — meaning the high-tier halving did NOT apply. Mid-tier currently does not reduce. If 0.5× was intended across 35-45 (covering G5007-class entries), set `FORGE_BREAKOUT_ADX_LOT_FACTOR_MID=0.5` in `.env`.

**EA comment at `FORGE.mq5:5867` is stale** (`// ADX 35-44 → 0.25× | ADX 45-54 → 1/8th | ADX ≥55 → 1/16th`) — those were v2.7.7 values. Current actual behavior: mid=1.0, high=0.5, no ≥55 tier. Behavior is correct; only the comment lies.

---

## BB_BREAKOUT BUY Entry

### Pre-quality gates (OHLC only — no indicator needed)
| Gate | Condition | Config value |
|---|---|---|
| Session | London or NY session | `tester_allowed_sessions=LONDON,NEW_YORK` |
| ATR floor | ATR ≥ min_entry_atr | `min_entry_atr = 1.0 pts` |
| Candle body | avg body/range over 3 bars ≥ threshold | `min_body_ratio = 0.25` |
| Directional bars | ≥ N of last 3 bars close in BUY direction | `min_directional_bars = 1` |

### BB_BREAKOUT BUY entry gates (all must pass)
| # | Indicator | Condition | Config value |
|---|---|---|---|
| 1 | BB (M5) | Previous M5 close **above** upper BB band | — |
| 2 | RSI (M5) | `RSI > 40` (Cardwell Bull Support floor) | `rsi_buy_min = 40` |
| 3 | RSI (M5) | `RSI < 78` (overbought ceiling) | `rsi_buy_ceil = 78` |
| 4 | EMA M5 | M5 trend bullish | `m5_bull` check |
| 5 | EMA M15 | M15 flat or bullish | `require_m15_agree=true` |
| 6 | EMA H1 | H1 not strongly bearish | `h1_ok_buy` |
| 7 | H1 DI+/DI− | If ADX < 28: H1 DI+ ≥ DI− (H1 bullish) | `require_h1_di_buy=1`, `counter_buy_adx_threshold=28` |
| 8 | OsMA M5 | Histogram positive AND rising (Q0 only) | `require_macd_buy=1` |
| 9 | Re-entry | Price not > 2×ATR from first entry price | `max_reentry_atr_ext = 2.0` |

### BUY trade parameters
```
SL  = bid − 2.0×ATR       (breakout_sl_atr_mult=2.0)
TP1 = bid + 0.5×ATR       (tp1_buy_atr_mult=0.5)
TP2 = bid + 1.5×ATR       (tp2_atr_mult=1.5)
TP3 = entry + 2.5×ATR     (tp3_atr_mult=2.5, set at group registration, activated after TP2)
Close 60% at TP1           (tp1_close_pct=60)
SL → breakeven after TP1  (move_be_on_tp1=true)
Runners → TP2, then TP3 when TP2 reached (live TP staging pass)
```

### BUY leg count (ADX-tiered)
| ADX (M5) | base_n | After bonuses | H1 trend clear? | Final legs |
|---|---|---|---|---|
| < 25 | 5−1 = 4 | +1 breakout = 5 | No (unclear cap=5) | **5** |
| < 25 | 5−1 = 4 | +1 breakout = 5 | Yes | **5** |
| 25–35 | 5 | +1 breakout = 6 | No (cap=5) | **5** |
| 25–35 | 5 | +1 breakout = 6 | Yes | **6** |
| 35–55 | 5+2 = 7 | +1 breakout = 8 | Yes (htf_clear) | **8** |

`native_legs_max_when_unclear=5`: when H1 trend strength is near zero (e.g. early sim warmup), caps legs at 5.  
All legs fire simultaneously (`staged_initial_legs=8` — capped at actual n).

---

## BB_BREAKOUT SELL Entry

### Pre-quality gates (same as BUY except session)
| Gate | Condition | Config value |
|---|---|---|
| Session | SELL blocked after 18:00 UTC (2 PM EDT) | `session_ny_sell_cutoff_utc = 18` |
| ATR floor | ATR ≥ 1.0 pts | `min_entry_atr = 1.0` |
| Candle body | avg body/range ≥ 0.25 | `min_body_ratio = 0.25` |
| Directional bars | ≥ 1 of last 3 bars close in SELL direction | `min_directional_bars = 1` |

### BB_BREAKOUT SELL entry gates (all must pass)
| # | Indicator | Condition | Config value |
|---|---|---|---|
| 1 | BB (M5) | Previous M5 close **below** lower BB band | — |
| 2 | RSI (M5) | `RSI < 60` (Cardwell Bear Resistance ceiling) | `rsi_sell_max = 60` |
| 3 | RSI (M5) | `RSI > 30` (oversold floor, stricter at weak ADX) | `rsi_sell_floor=30`, `rsi_sell_floor_weak_adx=36` |
| 4 | ADX (M5) | `ADX ≥ 25` (stricter SELL floor) | `adx_min_sell = 25` |
| 5 | ADX (M5) | ADX was ≥ 25 at least 6 bars ago (spike-from-flat check) | `adx_min_sell_lookback_bars = 6` |
| 6 | ADX (M15) | `ADX < 55` (extreme move block) | `breakout_adx_sell_block_threshold = 55` |
| 7 | H1 DI+/DI− | H1 DI− > DI+ (H1 bearish) — **no ADX bypass** | `require_h1_di_sell=1` |
| 8 | EMA M5 | M5 trend bearish | `m5_bear` check |
| 9 | EMA M15 | M15 flat or bearish | `require_m15_agree=true` |
| 10 | EMA H1 | H1 trend strength ≤ −0.2 | `min_h1_bear_strength = 0.2` |
| 11 | OsMA M5 | Histogram negative AND falling (Q2 only) | `require_macd_sell=1` |
| 12 | EMA M30 | M30 EMA20 < EMA50 when ADX ≥ 25 | `require_m30_bear_sell=1`, `m30_bear_adx_min=25` |
| 13 | RSI (M5) | Not rising bar-over-bar when ADX < 40 | `require_rsi_declining_sell=1` |
| 14 | H1 MACD | H1 MACD histogram < 0 (disabled for now) | `require_h1_macd_sell=0` |
| 15 | RSI divergence | **NOT** HID_BULL (hidden bullish = reversal warning) | `block_hid_bull_sell=1` |
| 16 | Re-entry | Price not > 2×ATR from first entry price | `max_reentry_atr_ext = 2.0` |

### Crash-Sell Bypass (gates 3 and 5 skipped when ALL of these are true)
```
H1 trend bearish (h1_bear)
H4 trend bearish (h4_bear)
RSI > 20                    (h1h4_crash_sell_rsi_min=20)
ADX ≤ 40                    (h1h4_crash_sell_adx_max=40)
M15 ADX ≥ 25               (h1h4_crash_sell_min_m15_adx=25)  ← NEW in 2.7.13
```
**M15 ADX requirement prevents false-breakdown crash bypass.** In a genuine crash, M15 and M5 trend together (Run11 Apr30: M5=41.3, M15=35.6 ✓). In a congestion-zone spike, M15 lags (Run11 May4: M5=37.4, M15=16.7 → bypass blocked ✓ → ADX spike gate runs → SKIP).

### SELL trade parameters
```
SL  = ask + 2.0×ATR       (breakout_sl_atr_mult=2.0)
TP1 = ask − 0.4×ATR       (tp1_sell_atr_mult=0.4)
TP2 = ask − 1.5×ATR       (tp2_atr_mult=1.5)
TP3 = entry − 2.5×ATR     (tp3_atr_mult=2.5, set at registration, activated after TP2)
Close 60% at TP1           (tp1_close_pct=60)
SL → breakeven after TP1  (move_be_on_tp1=true)
```

### SELL leg count (same ADX tiers as BUY, but lot reduced at ADX>35)
| ADX (M5) | Final legs | Lot factor | Notes |
|---|---|---|---|
| < 25 | **3–5** | 1.0 | ADX-weak, unclear cap applies |
| 25–35 | **5–6** | 1.0 | Standard breakout |
| 35–55 | **8** | **0.5×** | Strong trend but elevated reversal risk |

---

## BB_BOUNCE Entries (mean-reversion)

### BUY bounce — price at BB lower
| Condition | Value | Notes |
|---|---|---|
| Price | `mid ≤ BB_lower + proximity (28%)` | — |
| RSI (M5) | `RSI < 50` | `bounce_rsi_buy_max=50` |
| ADX (M5) | `ADX ≤ 30` normally | `bounce_adx_max=30` |
| **ADX override** | If `RSI_DIV=HID_BULL` AND `M15 ADX < 30`: use M15 ADX instead of M5 ADX for gate | NEW 2.7.13 — allows bounce when M5 ADX spiked but M15 is still ranging |

**HID_BULL bounce logic (Run 11 validation):**  
At May4 17:10: M5 ADX=37.4 > 30 (blocks bounce normally). But RSI_DIV=HID_BULL + M15 ADX=16.7 < 30 → bounce allowed. BUY bounce at 4554.82 would have hit TP1=4565.12 (+10.3 pts) at 17:20, TP2=4574.77 (+19.95 pts) at 17:25.

### SELL bounce — price at BB upper
| Condition | Value |
|---|---|
| Price | `mid ≥ BB_upper − proximity (28%)` |
| RSI (M5) | `RSI > 50` |
| ADX (M5) | `ADX ≤ 30` |

### Bounce parameters
```
TP1 = BB midband
TP2 = BB opposite band
SL  = 1.5×ATR from entry    (bounce_sl_atr_mult=1.5)
Lot = fixed_lot × 0.25      (bounce_lot_factor=0.25)
```

---

## SELL STOP Continuation Cascade (arms after primary SELL hits TP1)

**Status: ENABLED** (`sell_stop_cont_enabled=1`)

### Arming conditions (ArmPostTP1Ladder — real-time checks at TP1 hit)
| Gate | Condition | Config |
|---|---|---|
| RSI exhaustion | RSI > 25 at TP1 time | `sell_stop_cont_min_rsi=25` |
| ADX confirmation | M5 ADX ≥ 25 at TP1 time | `sell_stop_cont_min_adx=25` |
| H1 DI direction | H1 DI− > DI+ (H1 bearish) | `sell_stop_cont_require_h1_di=1` |

All three gates must pass for cascade to arm. When blocked, logged as "SELL STOP skipped" with reason.

### Cascade order parameters
```
Entry:  pending SELL STOP at TP1_price − ATR×0.4   (sell_stop_cont_atr_mult=0.4)
SL:     TP1_price + ATR×0.4
TP:     cascade_entry − ATR×1.5                     (sell_stop_cont_tp_atr_mult=1.5)
Expiry: 2 M5 bars (10 min)                          (sell_stop_cont_expiry_bars=2)
Lot:    fixed_lot × 1.0 = 0.08 (FULL LOT)          (sell_stop_cont_lot_factor=1.0)
Legs:   5 simultaneous pending orders               (sell_stop_cont_legs=5)
Slots:  [2..8] (up to 7 legs max)
Magic:  group_magic + 20002 through +20008
```

**Rationale**: TP1 hit proves the trend is real. Cascade fires at full lot — same conviction as the primary entry. 5 legs × 0.08 lot × 1.5×ATR TP = same risk profile as the primary group.

### BUY LIMIT Recovery (arms after primary SELL hits TP1)
```
Condition: RSI > 35 at TP1 hit             (buy_limit_recovery_min_rsi=35)
Entry:  pending BUY LIMIT at TP1 price
SL:     entry − ATR×1.0
Expiry: 4 M5 bars
Lot:    fixed_lot × 0.25
Slot:   [9]  Magic: group_magic + 20009
```

---

## Fast-Lock Trailing Stop

```
Min hold before eligible: 25 seconds  (fast_lock_min_hold_sec_breakout=25)
Min profit to trigger:    5.0 pts     (fast_lock_min_profit_points=5.0)
Trail multiplier:         1.35×ATR    (fast_lock_breath_mult=1.35)
```

---

## Full Lot — Quick Reference

**To get 0.08 lots per leg on a SELL BB_BREAKOUT:**

1. Setup type is BB_BREAKOUT (not BB_BOUNCE)
2. Price outside BB lower band (not inside-band SELL)
3. No other group already open in the same direction
4. RSI not in crash-floor zone (RSI 20–25) with crash bypass active
5. ADX < 35 (ADX 35–45 → 0.5× lot, ADX > 45 → further reduction)
6. `NativeScalperAutoLotByTrend` input = false (default)

---

## Framework Summary: M5 → M15 → H1 → H4

FORGE uses a bottom-up multi-timeframe validation:

| TF | Role | How used |
|---|---|---|
| M5 | Entry signal | BB breakout trigger, RSI, ADX spike gate, OsMA, RSI divergence |
| M15 | Confirmation | Must agree with direction; ADX used for crash bypass validation |
| H1 | Trend filter | DI+/DI- direction gate; trend strength for leg count; crash bypass |
| H4 | Context | Secondary bearish/bullish alignment; optional H4 RSI/ADX gates |

**Key principle**: M5 divergence (RSI_DIV=HID_BULL) is the first-mover signal — it sees reversals before H1/H4. When M5 warns of reversal AND M15 confirms ranging (flat ADX), the SELL is blocked and the BUY bounce evaluates instead.
