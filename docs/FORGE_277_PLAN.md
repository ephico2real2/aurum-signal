# FORGE 2.7.7 — Implementation Plan

**Date:** 2026-05-09 | **Basis:** Run 23/24 loss analysis + scalping research + multi-source validation

---

## Research Validation Summary

Eight web searches across academic papers, practitioner blogs, and MQL5 community, 23 sources reviewed.

### What the research confirms ✓

| Feature | Research finding | Source |
|---------|----------------|--------|
| MACD(3,10,16) histogram gate | Detects signals 5-10 candles earlier than 12/26/9; BB+MACD backtest = 78% WR | OpoFinance, QuantifiedStrategies |
| RSI+MACD dual gate | arXiv paper: 84-86% win rate; SSRN paper: "dual confirmation reduced false signals significantly" | arXiv:2206.12282, SSRN:3697734 |
| Session sell cutoff (17:00 UTC) | ~70% of XAUUSD daily range occurs in London + NY overlap. Post-17:00 = lower liquidity, wider spreads, choppier | TMGM, ACY, NordFX |
| SELL LIMIT cascade over market orders | Kinlay (2018): limit orders have positive expected slippage; stacked limits absorb partial fills | jonathankinlay.com |
| ADX + MACD as combined filter | MACD histogram direction to pre-filter ADX entries = dominant practitioner convention | ForexTester, RoboForex |
| MACD histogram negative = SELL zone | "MACD histogram below zero + RSI in 20-60 range = confirmed SELL" matches Cardwell practice | Investing.com, WunderTrading |

### Adjustments to original plan ⚠

| Issue | Evidence | Plan change |
|-------|----------|-------------|
| ADX lag on M1/M5 | OpoFinance, Trade2Win: "ADX reveals high lag on lower timeframes" | Tiered lot sizing should read ADX from M15/M30, not M5 bar |
| RSI 65/35 for XAUUSD | TradingView XAUUSD 10-min community script uses 65/35, not 70/30 | Flag for 2.7.8 validation — test whether 65/35 improves WR on gold |
| Wilder never prescribed MACD+ADX | FasterCapital: practitioner addition, not Wilder-native | No change — practitioner consensus is sufficient justification |

### What was missing from original plan ✗

| Gap | Evidence | Added to plan |
|-----|----------|---------------|
| Spread filter | Multiple sources: XAUUSD spreads 10-15 pips at rollover; scalping edge degrades at high spread | Added as Feature 0 (pre-entry gate) |

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

### Feature 0 — Spread filter pre-entry gate (TRIVIAL, RESEARCH-SUPPORTED)

**Research basis:** XAUUSD spreads documented at 1.5-2.5 pips during London session vs 10-15 pips
at daily rollover (ACY). Scalping edge degrades when spread exceeds ~30% of expected TP distance.
FORGE already has `max_spread_points` in ScalperConfig — but it is NOT currently applied in
`CheckEntryQuality` as an active gate. It needs to be wired.

**Existing config:** `safety.max_spread_points` (default 30). Already parsed in `ReadScalperConfig`.

**Fix:** Confirm the gate is applied. `CheckNativeScalperSetups` should read spread = `(ask-bid)/point`
and block entries when `spread > g_sc.max_spread_points`. Check if this is already wired.

---

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

### Feature 1.5 — MACD(3,10,16) histogram gate (LOW complexity, RESEARCH-VALIDATED)

**Research basis:**
- BB + MACD backtest: **78% win rate**, avg 1.4% per trade (QuantifiedStrategies)
- RSI + MACD dual gate: **84-86% win rate** in arXiv:2206.12282 — "dual confirmation reduced false signals significantly"
- MACD(3,10,16) independently confirmed: detects signals 5-10 candles earlier than standard 12/26/9
- Rule: MACD histogram negative + RSI in Cardwell 20-60 zone = confirmed SELL (Investing.com)

**Design:**
New indicator handle: `iMACD(_Symbol, PERIOD_M5, 3, 10, 16, PRICE_CLOSE)`
- Buffer 0: MACD line
- Buffer 1: Signal line
- Buffer 2: Histogram

**Gate — two checks:**

**Check A: Histogram direction for SELL** — block SELL when histogram is contracting
(histogram[0] > histogram[1] = less negative = momentum shifting bullish):
```mql5
if(g_sc.breakout_require_macd_sell && direction_is_sell) {
   double hist[2];
   CopyBuffer(g_h_macd, 2, 0, 2, hist);
   if(hist[0] > hist[1])  // contracting = momentum weakening SELL
      → SKIP: entry_quality_macd_histogram
}
```

**Check B: Histogram below zero for SELL** — block SELL when histogram is positive
(market has bullish MACD momentum, not confirmed for SELL):
```mql5
if(hist[0] >= 0) → SKIP: entry_quality_macd_direction
```

G5011 impact: at 17:10, market was recovering → histogram likely contracting or positive → BLOCKED.

**Config keys:**
```
FORGE_BREAKOUT_REQUIRE_MACD_SELL=1
FORGE_BREAKOUT_REQUIRE_MACD_BUY=0        # optional BUY filter
FORGE_BREAKOUT_MACD_FAST=3
FORGE_BREAKOUT_MACD_SLOW=10
FORGE_BREAKOUT_MACD_SIGNAL=16
```

**Journal reasons:** `entry_quality_macd_histogram`, `entry_quality_macd_direction`

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

**ADX source — research finding:** OpoFinance and Trade2Win document ADX lag on M1/M5 as a
known problem. The M5 ADX reading at signal time may lag actual trend strength by 3-5 bars.
**Recommendation:** Read ADX at M15 for the lot sizing tier decision rather than M5.
M15 ADX reflects a 75-min trend window — less susceptible to tick noise. Use existing
`g_mtf[1].h_adx` (M15 ADX handle already initialized) for the threshold comparison.

**Config keys:**
```
FORGE_BREAKOUT_ADX_LOT_MID_THRESHOLD=35
FORGE_BREAKOUT_ADX_LOT_HIGH_THRESHOLD=45
FORGE_BREAKOUT_ADX_LOT_EXT_THRESHOLD=55
FORGE_BREAKOUT_ADX_LOT_FACTOR_MID=0.25
FORGE_BREAKOUT_ADX_LOT_FACTOR_HIGH=0.125
FORGE_BREAKOUT_ADX_LOT_FACTOR_EXT=0.0625
FORGE_BREAKOUT_ADX_LOT_USE_M15=1        # 1=use M15 ADX for tier; 0=M5
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

| # | Feature | Complexity | Research support | Impact | Sprint |
|---|---------|-----------|-----------------|--------|--------|
| 0 | Spread filter (verify wired) | Trivial | ACY, TMGM (spread data) | Prevents high-spread entries | **Now** |
| 1 | Session sell cutoff | Low | NordFX, ACY, TMGM | +$321 (G5011+G5013) | **Now** |
| 1.5 | MACD(3,10,16) histogram gate | Low | arXiv:2206.12282, QuantifiedStrategies | Blocks G5011-class exhaustion | **Now** |
| 2 | Tiered ADX lot factors (M15 ADX) | Low | OpoFinance, Trade2Win (ADX lag) | +$50–80 damage control | **Now** |
| 3 | M30 bearish confirmation | Medium | ForexTester, RoboForex | Prevents stale-H1 entries | 2.7.7a |
| 4 | SELL LIMIT cascade | High | Kinlay (math), MQL5 code 27379 | Cardwell re-short, recovery BUY | 2.7.7b |
| 5 | Recovery BUY capture | Medium | Cardwell Bull Support research | Depends on #4 pending infra | 2.7.7b |
| 6 | RSI 65/35 threshold test | Config | TradingView XAUUSD script | XAUUSD-tuned overbought levels | 2.7.8 |

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
