# FORGE 2.7.7 — Implementation Plan

**Date:** 2026-05-09 | **Basis:** Run 23/24 loss analysis + scalping research

---

## Context — What Run 24 showed us

| Problem | Evidence | Current state |
|---------|----------|---------------|
| G5011 (-$238): High ADX + late session reversal | May 4 17:10, ADX 37, 17:10 UTC | No time gate, full lot |
| G5004 (-$16): ADX 59 crash entry still taken | Apr 30 07:35 | ADX cap blocks; tiny loss at 0.25× |
| May 1 sell-off + BUY recovery missed | 08:30–12:30 then bounce | H1 barely bearish → G5006 blocked |
| No pending order stacking | Single market entry per signal | Misses Cardwell bounce re-short fills |

---

## Research synthesis

### From FXOpen scalping indicators article
- **RSI(7–9)** for scalping (not 14) — faster exhaustion signal
- **BB(7–10, StdDev 1.5–2)** — tighter bands for scalp volatility
- **EMA(5/15) crossover + RSI** or **BB + Stochastic(5,3,3)** are the two main scalp combos
- Directly maps to existing FORGE BB+RSI architecture — validate with shorter RSI period in 2.7.8

### From MQL5 candlestick scalper (article 16643 + USDJPY file)
- **Triple gate**: engulfing candle + price above/below MA channel + 365-day midpoint bias
- **ATR(14) × 2 for SL** — already used in FORGE (validated)
- **Daily trailing SL** — tighten only in profitable direction, padded by mean ATR
- **Candle-close-only** signal processing — already done

### From MQL5 Market MA Cross EA
- **Risk-% lot sizing with hard cap** — correct for gold volatility
- **Session hour filter** — configurable start/end UTC hour
- **One trade at a time guard** — already done via max_open_groups

---

## Feature List — Priority Order

### Feature 1 — Session sell cutoff gate (LOW complexity, HIGH impact)

**Problem:** G5011 at 17:10 and G5013 at 18:25 UTC are late NY session. XAUUSD
consistently reverses at session close (profit-taking + Asia transition). Entering
SELL in the final 2–3 hours of NY creates reversal exposure with wide SL.

**Design:** Per-session configurable SELL cutoff hour. After the cutoff, no new SELL
entries are opened — existing positions run to TP/SL. BUY entries continue (gold
overnight drift tends to be long-biased).

**Config keys** (using existing session naming pattern):
```
SESSION_NY_SELL_CUTOFF_UTC=17        # no new SELL after 17:00 UTC
SESSION_LONDON_SELL_CUTOFF_UTC=0     # 0 = disabled (London is fine)
SESSION_ASIAN_SELL_CUTOFF_UTC=0      # 0 = disabled
```

**Gate logic** (in `CheckNativeScalperSetups`, before SELL block):
```mql5
// Session SELL cutoff: block new SELL near session close (gold reversal zone)
MqlDateTime now_dt; TimeToStruct(TimeTradeServer(), now_dt);
bool sell_cutoff_ok = true;
int sell_cutoff = (int)g_sc.session_ny_sell_cutoff_utc;
if(sell_cutoff > 0 && now_dt.hour >= sell_cutoff && NativeScalperInNYSession())
   sell_cutoff_ok = false;
// (repeat for London if enabled)
```

**Journal reason:** `entry_quality_session_sell_cutoff`

**Impact on Run 23/24:**
- G5011 (17:10 UTC) → BLOCKED (NY cutoff = 17:00)
- G5013 (18:25 UTC) → BLOCKED
- Saves: $238 + $83 = **+$321** net improvement

---

### Feature 2 — Tiered lot factors for high-ADX entries (LOW complexity, MEDIUM impact)

**Problem:** When crash bypass allows entries at ADX 35–50, these are valid Cardwell
setups but elevated reversal risk. Currently all crash bypass entries not in RSI 20–25
use full lot. Need tiered protection: the more extended the move (higher ADX), the
smaller the position.

**Design:** Two additional lot factor tiers applied in the lot computation block,
stacking with the existing near-floor factor:

```
ADX 35–44 → breakout_high_adx_lot_factor_mid  = 0.25   (same as near-floor)
ADX 45–54 → breakout_high_adx_lot_factor_high = 0.125  (1/8th)
ADX ≥ 55  → breakout_high_adx_lot_factor_ext  = 0.0625 (1/16th)
```

Thresholds are configurable. `h1h4_crash_sell_adx_max=40` blocks the bypass above
ADX 40 — these tiers apply to entries where bypass IS active (ADX ≤ 40) but still
elevated.

Actually, the tiers apply to ALL BB_BREAKOUT SELL entries (not just crash bypass),
as a protection against extended moves regardless of bypass state:

```mql5
// ADX-based lot tiers: the more extended the trend, the smaller the bet
double adx_lot_factor = 1.0;
if(direction == "SELL" && is_breakout_setup) {
   if(m5_adx >= g_sc.breakout_adx_lot_ext_threshold)        // ≥55
      adx_lot_factor = g_sc.breakout_adx_lot_factor_ext;    // 1/16
   else if(m5_adx >= g_sc.breakout_adx_lot_high_threshold)  // ≥45
      adx_lot_factor = g_sc.breakout_adx_lot_factor_high;   // 1/8
   else if(m5_adx >= g_sc.breakout_adx_lot_mid_threshold)   // ≥35
      adx_lot_factor = g_sc.breakout_adx_lot_factor_mid;    // 0.25
}
```

**Compound floor:** existing `MathMax(0.25, ...)` floor prevents going below 25% —
but at 1/16 = 0.0625, we want to allow it. Raise the compound floor to account for
all three factors: `combined = MathMax(0.0625, all_factors_product)`.

**Config keys:**
```
FORGE_BREAKOUT_ADX_LOT_MID_THRESHOLD=35
FORGE_BREAKOUT_ADX_LOT_HIGH_THRESHOLD=45
FORGE_BREAKOUT_ADX_LOT_EXT_THRESHOLD=55
FORGE_BREAKOUT_ADX_LOT_FACTOR_MID=0.25
FORGE_BREAKOUT_ADX_LOT_FACTOR_HIGH=0.125
FORGE_BREAKOUT_ADX_LOT_FACTOR_EXT=0.0625
```

---

### Feature 3 — M30 bearish confirmation for high-ADX SELL entries (MEDIUM complexity)

**Problem:** G5011 (ADX 37, late session) was technically Cardwell-valid (RSI declining)
but H1 had been bearish for hours — the H1 bias was stale. M30 or M15 EMA alignment
would have shown the market was already recovering by 17:10.

**Design:** When ADX > 30 and crash bypass is active, require M30 EMA20 < EMA50
(M30 bearish) as additional confirmation. This checks whether the intermediate
timeframe confirms the trend before entering.

New MTF handle: `g_m30_ma20`, `g_m30_ma50` — same pattern as existing M15/H1 handles.

**Gate logic:**
```mql5
bool m30_ok_sell = true;
if(g_sc.breakout_require_m30_bear_sell && m5_adx >= g_sc.breakout_m30_bear_adx_min) {
   double m30_ema20 = CopyBuffer(g_m30_ma20, 0, 0, 1, buf) == 1 ? buf[0] : 0;
   double m30_ema50 = CopyBuffer(g_m30_ma50, 0, 0, 1, buf) == 1 ? buf[0] : 0;
   if(m30_ema20 > 0 && m30_ema50 > 0 && m30_ema20 >= m30_ema50)
      m30_ok_sell = false;  // M30 not bearish — skip
}
```

**Config keys:**
```
FORGE_BREAKOUT_REQUIRE_M30_BEAR_SELL=1
FORGE_BREAKOUT_M30_BEAR_ADX_MIN=30
```

**Impact on G5011:** At 17:10, M30 EMA20 was likely crossing above EMA50 (market
recovering). This gate would have blocked it.

---

### Feature 4 — SELL LIMIT cascade / scalper stacking (HIGH complexity, HIGH reward)

**Problem:** We enter one market SELL and miss the Cardwell bounce-and-fail re-short.
When crash fires at RSI 26 and the market bounces back to RSI 45-55 (Bear Resistance),
we have no pending order to catch that re-short. This is the most profitable pattern
in Cardwell's framework.

**Design:** Strategy 1 (SELL LIMIT stack — Cardwell-aligned):

When crash SELL signal fires AND `breakout_use_sell_limit_stack=1`:
1. Place market SELL at bid (immediate)
2. Place SELL LIMIT at `bid + ATR × limit_atr_mult_1` (default 0.4) — catch first bounce
3. Place SELL LIMIT at `bid + ATR × limit_atr_mult_2` (default 0.8) — catch deeper bounce

Each limit uses the same SL as the market order but `1/8th lot` (dangerous zone sizing).
Expiry: 6 M5 bars (30 min) via `ORDER_TIME_SPECIFIED`.

**Cancellation (OnTradeTransaction):**
```mql5
// When market SELL SL hits → cancel all pending SELL LIMITs from same group
if(profit < 0 && StringFind(comment, "sl") >= 0) {
   for each pending_ticket in g_pending_stack:
      trade.OrderDelete(pending_ticket);
   g_pending_stack.Clear();
}
```

**Pending order state:**
```mql5
struct PendingStack {
   ulong  tickets[2];    // up to 2 pending order tickets
   int    count;
   ulong  parent_magic;  // market order magic — for SL matching
   datetime expiry;
};
PendingStack g_sell_limit_stack;
```

**Architecture requirements:**
- `ORDER_FILLING_RETURN` fill policy (not FOK)
- `ORDER_TIME_SPECIFIED` + expiry timestamp
- `OnTimer` check: if bar count > 6 since stack placed → cancel all
- Manual delete in `OnTradeTransaction` when parent SL fires

**Config keys:**
```
FORGE_BREAKOUT_USE_SELL_LIMIT_STACK=0     # off by default until tested
FORGE_BREAKOUT_SELL_LIMIT_ATR_MULT_1=0.4
FORGE_BREAKOUT_SELL_LIMIT_ATR_MULT_2=0.8
FORGE_BREAKOUT_SELL_LIMIT_LOT_FACTOR=0.125  # 1/8 each
FORGE_BREAKOUT_SELL_LIMIT_EXPIRY_BARS=6
```

**Recovery BUY after crash (same feature, BUY side):**
When crash SELL run completes (RSI bouncing, H1 recovering), place BUY LIMIT
at `ask - ATR × 0.3` to catch the Cardwell Bull Support re-entry at RSI 40-50 bounce.
Same expiry/cancellation pattern as SELL stack.

---

### Feature 5 — May 1 recovery BUY capture

**Problem:** After the crash sell-off (08:30–12:30), gold bounced strongly. H1 was
still bearish from the crash, blocking BB_BREAKOUT BUY (`h1_ok_buy` requires H1 not bearish).
M5/M15 had already reversed bullish but H1 lags.

**Design options:**
- **Option A (simple):** When RSI crosses above 40 from below AND M15 is bullish AND
  price closes above BB upper → BUY with small lot (0.25×) even with H1 bearish.
  New gate: `breakout_buy_recovery_enabled` — allows BUY when M5+M15 both bull
  even if H1 is still bearish, but requires ADX < 30 (momentum not extended).

- **Option B (pending, preferred):** Part of the SELL LIMIT stack feature — after the
  crash SELL hits TP, automatically place BUY LIMIT at TP price + ATR×0.2
  (Cardwell: RSI bounce back toward 40 = Bull Support re-entry). This captures
  the recovery BUY without needing H1 to confirm.

Option B is the clean implementation — it ties naturally into the scalper stacking
feature and uses Cardwell's framework consistently.

---

## Implementation Order

| # | Feature | Complexity | Impact | Sprint |
|---|---------|-----------|--------|--------|
| 1 | Session sell cutoff | Low | +$321 (G5011+G5013) | **Now** |
| 2 | Tiered ADX lot factors | Low | +$50–80 damage control | **Now** |
| 3 | M30 bearish confirmation | Medium | Prevents stale-H1 entries | 2.7.7a |
| 4 | SELL LIMIT cascade | High | Cardwell re-short, recovery BUY | 2.7.7b |
| 5 | Recovery BUY capture | Medium | Depends on #4 pending infra | 2.7.7b |

Features 1 and 2 can be implemented and compiled today (code only, no new handles).
Feature 3 requires a new M30 handle (OnInit change).
Features 4 and 5 require OnTradeTransaction extension and PendingStack struct.

---

## Config naming convention (existing pattern)

```
# Session timing (UTC hours)
SESSION_NY_SELL_CUTOFF_UTC=17
SESSION_LONDON_SELL_CUTOFF_UTC=0

# ADX lot tiers
FORGE_BREAKOUT_ADX_LOT_MID_THRESHOLD=35
FORGE_BREAKOUT_ADX_LOT_HIGH_THRESHOLD=45
FORGE_BREAKOUT_ADX_LOT_EXT_THRESHOLD=55
FORGE_BREAKOUT_ADX_LOT_FACTOR_MID=0.25
FORGE_BREAKOUT_ADX_LOT_FACTOR_HIGH=0.125
FORGE_BREAKOUT_ADX_LOT_FACTOR_EXT=0.0625

# M30 confirmation
FORGE_BREAKOUT_REQUIRE_M30_BEAR_SELL=1
FORGE_BREAKOUT_M30_BEAR_ADX_MIN=30

# Scalper stacking (pending orders)
FORGE_BREAKOUT_USE_SELL_LIMIT_STACK=0
FORGE_BREAKOUT_SELL_LIMIT_ATR_MULT_1=0.4
FORGE_BREAKOUT_SELL_LIMIT_ATR_MULT_2=0.8
FORGE_BREAKOUT_SELL_LIMIT_LOT_FACTOR=0.125
FORGE_BREAKOUT_SELL_LIMIT_EXPIRY_BARS=6
```

---

## Research sources

- [FXOpen — Scalping Indicators](https://fxopen.com/blog/en/what-indicators-do-traders-use-for-scalping/)
  Key: RSI(7-9), BB(7-10), Stochastic(5,3,3) for scalp entries
- [MQL5 Article 16643 — Candlestick Scalper](https://www.mql5.com/en/articles/16643)
  Key: Triple gate confluence, ATR×2 SL, candle-close-only, daily trailing
- [MQL5 Market — MA Cross EA](https://www.mql5.com/en/market/product/166906)
  Key: Risk-% lot sizing with hard cap, session hour filter pattern
- USDJPY_Price_Action_Strategy_2.mq5 (local)
  Key: EMA(90) channel + 365-day midpoint + ATR trailing SL implementation

---

*Plan status: Features 1–2 ready to implement. Features 3–5 design approved, pending implementation sprint.*
