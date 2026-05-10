# FORGE Entry Conditions — Run 10

**EA version**: FORGE v2.7.11 | **Symbol**: XAUUSD M5  
**Source**: ea/FORGE.mq5 + config/scalper_config.json  
*All values read directly from code and config — not estimated.*

---

## Indicators Used

| Indicator | Timeframe | Period | Role |
|---|---|---|---|
| Bollinger Bands (BB) | M5 | 20, 2σ | Entry trigger (price vs upper/lower band) |
| RSI | M5 | 14 | Momentum filter — direction and extremes |
| ADX | M5 | 14 | Trend strength — gates entry, drives leg count |
| ATR | M5 | 14 | SL/TP sizing, lot normalization |
| EMA 20/50 | M5 | 20, 50 | M5 trend direction (m5_bull/bear) |
| EMA 20/50 | M15 | 20, 50 | M15 confirmation (m15_bull/bear/flat) |
| EMA 20/50 | M30 | 20, 50 | M30 bearish confirmation gate for SELL |
| EMA 20/50 | H1 | 20, 50 | H1 trend direction + Cardwell strength |
| EMA 20/50 | H4 | 20, 50 | H4 trend alignment (optional H4 gates) |
| ADX (DI+/DI−) | H1 | 14 | H1 Wilder directional confirmation for BUY |
| OsMA (3,10,16) | M5 | — | MACD histogram 4-quadrant gate (both dirs) |

---

## Full Lot Conditions

Full lot = **0.08 per leg** when `combined_lot_factor = 1.0`.

Every factor below must be 1.0:

| Factor | Condition for 1.0 (full lot) | When reduced |
|---|---|---|
| `inside_band_factor` | BUY always. SELL: price is below BB lower (not inside band) | SELL inside BB band → `breakout_sell_inside_band_lot_factor=0.25` |
| `near_floor_factor` | No crash-bypass active, or RSI > 25 | SELL crash-bypass + RSI 20–25 → `breakout_near_floor_lot_factor=0.25` |
| `stack_factor` | First group open in that direction | 2nd concurrent same-direction group → `same_direction_stack_lot_factor=0.25` |
| `adx_lot_factor` | **BUY: always 1.0** (SELL-only check). SELL: factors now = 1.0 | (Fixed this session — was 0.25 at ADX>35) |
| `bounce_factor` | BB_BREAKOUT setup | BB_BOUNCE → `bounce_lot_factor=0.25` |
| `lot_mult` | `NativeScalperAutoLotByTrend=false` (default) | Only > 1.0 if AutoLot input is enabled |

**In normal operation (first group, BB_BREAKOUT, AutoLot off)**: full lot on every entry.

---

## BB_BREAKOUT BUY Entry

### Pre-quality gates (OHLC only — no indicator check)
| Gate | Condition | Config value |
|---|---|---|
| Session | London or NY session | `tester_allowed_sessions=LONDON,NEW_YORK` |
| ATR floor | `ATR ≥ min_entry_atr` | `min_entry_atr = 1.0 pts` |
| Candle body | avg body/range over 3 bars ≥ threshold | `min_body_ratio = 0.25` |
| Directional bars | ≥ N of last 3 bars close in BUY direction | `min_directional_bars = 1` |

### BB_BREAKOUT BUY entry gates (all must pass)
| # | Indicator | Condition | Config value |
|---|---|---|---|
| 1 | BB (M5) | Previous M5 close **above** upper BB band | — |
| 2 | RSI (M5) | `RSI > 40` (Cardwell Bull Support floor) | `rsi_buy_min = 40` |
| 3 | RSI (M5) | `RSI < 77` (overbought ceiling) | `rsi_buy_ceil = 77` |
| 4 | EMA M5 | M5 trend strength > threshold (bull bias) | `trend_thr_eff` |
| 5 | EMA M15 | M15 flat or bullish | `require_m15_agree=true` |
| 6 | EMA H1 | H1 trend not strongly bearish | `h1_ok_buy` check |
| 7 | H1 DI+/DI− | If ADX < 28: H1 DI+ must be ≥ DI− | `require_h1_di_buy=1`, `counter_buy_adx_threshold=28` |
| 8 | OsMA M5 | Histogram positive AND rising (Q0 only) | `require_macd_buy=1` |
| 9 | Re-entry | Price not > 2×ATR from first entry price | `max_reentry_atr_ext = 2.0` |

### BUY trade parameters
```
SL  = bid − 2.0×ATR       (breakout_sl_atr_mult=2.0)
TP1 = bid + 0.5×ATR       (tp1_buy_atr_mult=0.5)
TP2 = bid + 1.5×ATR       (tp2_atr_mult=1.5)
TP3 = entry − 2.5×ATR     (tp3_atr_mult=2.5, set at group registration)
Close 60% at TP1           (tp1_close_pct=60)
SL → breakeven after TP1  (move_be_on_tp1=true)
Runners → TP2, then TP3 when TP2 reached (live TP staging pass)
```

### BUY leg count (ADX-tiered)
| ADX (M5) | base_n | After bonuses | Final legs |
|---|---|---|---|
| < 25 | 4−1 = 3 | +1 breakout = 4, unclear cap = 2 | **2** |
| 25–35 | 4 | +1 breakout ±1 H1/H4 = 4–6 | **4–6** |
| 35–55 | 4+2 = 6 | +1 breakout +1 H1/H4 = 8 | **8** |

All legs fire simultaneously (`staged_initial_legs=8`).

---

## BB_BREAKOUT SELL Entry

### Pre-quality gates (same as BUY)
| Gate | Condition | Config value |
|---|---|---|
| Session | SELL blocked after 18:00 UTC | `session_ny_sell_cutoff_utc = 18` |
| ATR floor | ATR ≥ 1.0 pts | `min_entry_atr = 1.0` |
| Candle body | avg body/range ≥ 0.25 | `min_body_ratio = 0.25` |
| Directional bars | ≥ 1 of last 3 bars close in SELL direction | `min_directional_bars = 1` |

### BB_BREAKOUT SELL entry gates (all must pass)
| # | Indicator | Condition | Config value |
|---|---|---|---|
| 1 | BB (M5) | Previous M5 close **below** lower BB band | — |
| 2 | RSI (M5) | `RSI < 60` (Cardwell Bear Resistance ceiling) | `rsi_sell_max = 60` |
| 3 | RSI (M5) | `RSI > 30` (oversold floor) | `rsi_sell_floor = 30` |
| 4 | ADX (M5) | `ADX ≥ 25` (stricter SELL floor) | `adx_min_sell = 25` |
| 5 | ADX (M5) | ADX was elevated 6 bars ago (spike-from-flat check) | `adx_min_sell_lookback_bars = 6` |
| 6 | ADX (M15) | `ADX < 55` (extreme ADX block — extended move) | `breakout_adx_sell_block_threshold = 55` |
| 7 | EMA M5 | M5 trend bearish | `m5_bear` check |
| 8 | EMA M15 | M15 flat or bearish | `require_m15_agree=true` |
| 9 | EMA H1 | H1 trend not strongly bullish; `h1_trend_strength ≤ −0.2` | `min_h1_bear_strength = 0.2` |
| 10 | OsMA M5 | Histogram negative AND falling (Q2 only) | `require_macd_sell = 1` |
| 11 | EMA M30 | M30 EMA20 < EMA50 when ADX ≥ 25 | `require_m30_bear_sell=1`, `m30_bear_adx_min=25` |
| 12 | RSI (M5) | Not rising bar-over-bar when ADX < 40 | `require_rsi_declining_sell=1` |
| 13 | Session | Hour < 18 UTC | `session_ny_sell_cutoff_utc = 18` |
| 14 | Re-entry | Price not > 2×ATR from first entry price | `max_reentry_atr_ext = 2.0` |

*Gates 3/5 are bypassed when H1+H4 both bearish + RSI > 20 + ADX ≤ 40 (crash-sell bypass path).*

### SELL trade parameters
```
SL  = ask + 2.0×ATR       (breakout_sl_atr_mult=2.0)
TP1 = ask − 0.4×ATR       (tp1_sell_atr_mult=0.4)
TP2 = ask − 1.5×ATR       (tp2_atr_mult=1.5)
TP3 = entry − 2.5×ATR     (tp3_atr_mult=2.5, set at group registration)
Close 60% at TP1           (tp1_close_pct=60)
SL → breakeven after TP1  (move_be_on_tp1=true)
Runners → TP2, then TP3 when TP2 reached
```

### SELL leg count (same ADX tiers as BUY)
| ADX (M5) | Final legs | Note |
|---|---|---|
| < 25 | **2** | Weak/unconfirmed direction |
| 25–35 | **4–6** | Standard breakout |
| 35–55 | **8** | Strong confirmed trend (gold cap = 8) |

---

## BB_BOUNCE Entries (mean-reversion, lower confidence)

### BUY bounce — price at BB lower
| Condition | Value |
|---|---|
| Price | `mid ≤ BB_lower + proximity (28%)` |
| RSI (M5) | `RSI < 50` | `bounce_rsi_buy_max=50` |
| H1 trend | `h1_trend_strength ≥ 0.3` (Cardwell Bull Support) | `bounce_min_h1_trend=0.3` |
| ADX (M5) | `ADX ≤ 50` (not trending) | `bounce_adx_max=30` (current config) |

### SELL bounce — price at BB upper
| Condition | Value |
|---|---|
| Price | `mid ≥ BB_upper − proximity (28%)` |
| RSI (M5) | `RSI > 50` | `bounce_rsi_sell_min=50` |
| ADX (M5) | `ADX ≤ 30` | `bounce_adx_max=30` |

### Bounce parameters
```
TP1 = BB midband (adjusted by POC/VWAP/Fib if available)
TP2 = BB opposite band
SL  = 1.5×ATR from entry    (bounce_sl_atr_mult=1.5)
Lot = fixed_lot × 0.25      (bounce_lot_factor=0.25 → 0.02 at base 0.08)
```

---

## Re-entry / Cascade (currently disabled — re-enable after TP3 staging validated)

### SELL STOP Continuation (arms after primary SELL hits TP1)
```
Condition: RSI > 25 at time of TP1 hit   (sell_stop_cont_min_rsi=25)
Entry:  pending SELL STOP at TP1 − ATR×0.4   (sell_stop_cont_atr_mult=0.4)
SL:     TP1 + ATR×0.4
TP:     entry − ATR×0.8                       (sell_stop_cont_tp_atr_mult=0.8)
Expiry: 2 M5 bars (10 min)                   (sell_stop_cont_expiry_bars=2)
Lot:    fixed_lot × 0.25 = 0.02              (sell_stop_cont_lot_factor=0.25)
Magic:  group_magic + 20002 (slot 2), +20003 (slot 3)
Status: sell_stop_cont_enabled=0 (disabled for Run 10)
```

### BUY LIMIT Recovery (arms after primary SELL hits TP1)
```
Condition: RSI > 35 at TP1 hit             (buy_limit_recovery_min_rsi=35)
Entry:  pending BUY LIMIT at TP1 price
SL:     entry − ATR×1.0
Expiry: 4 M5 bars
Lot:    fixed_lot × 0.25 = 0.02
Magic:  group_magic + 20004
Status: buy_limit_recovery_enabled=1
```

---

## Fast-Lock Trailing Stop (protects open profit)

Activates when position is profitable and held long enough:

```
Min hold before fast-lock eligible: 25 seconds  (fast_lock_min_hold_sec_breakout=25)
Min profit to trigger: 5.0 pts                  (fast_lock_min_profit_points=5.0)
Trail multiplier: 1.35×ATR behind current price  (fast_lock_breath_mult=1.35)
```

Once fast-lock engages, SL ratchets forward as price moves — it never widens.

---

## Full Lot — Quick Reference

**All of the following must be true to get 0.08 lots per leg:**

1. Setup type is BB_BREAKOUT (not BB_BOUNCE)
2. Price outside the BB band in the trade direction (not inside-band SELL)
3. No other group already open in the same direction
4. RSI not in crash-floor zone (RSI 20–25) with crash bypass active
5. `NativeScalperAutoLotByTrend` input = false (default)

When any of these fails, lot reduces to 0.25× or 0.125× per leg.  
**ADX no longer reduces lot** (fixed this session — adx_lot_factor_mid/high = 1.0).
