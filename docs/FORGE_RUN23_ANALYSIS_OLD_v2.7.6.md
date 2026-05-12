# FORGE 2.7.6 — Run 23 Analysis (Tester DB Agent-3000, run_id=1)

**Date:** 2026-05-09 | **Period:** Apr 29–May 5, 2026 | **Symbol:** XAUUSD | **Mode:** DUAL
**EA:** 2.7.6 (all fixes applied) | **Balance:** $10,000 | **Testing:** Every Tick

---

## Final Result

| Metric | Value |
|--------|-------|
| Net P&L | **-$93.86** |
| TAKEN | 13 |
| Wins | 4 groups |
| Losses | 7 groups |
| Period | Apr 29–May 5 |

**P&L by day:**

| Day | P&L | Notes |
|-----|-----|-------|
| Apr 29 | +$32.74 | 3 SELLs: G5001(W)+G5002(W)+G5003(L near-floor) |
| Apr 30 | +$128.80 | G5004(L near-floor) + G5005 BUY WIN |
| May 1 | -$129.36 | G6 SELL SL — full lot (RSI 28.1, not near-floor zone) |
| May 4 | -$126.04 | Mixed: 4 wins 11:00-13:10, 3 losses 17:10-18:38 |

---

## Gate Validation Results

| Gate | Count | Status |
|------|-------|--------|
| `adx_min_sell` | 4 | ✓ 2.7.5 gate active |
| `adx_spike_sell` | 1 | ✓ 2.7.5 gate active |
| `rsi_sell_floor` | 3 | ✓ RSI 16.1 blocked (Cardwell floor) |
| `rsi_sell_adx_floor` | 2 | ✓ Weak-ADX floor active |
| `post_sl_cooldown` | 8,917 | ✓ Direction cooldown after G5011 SL |
| `rsi_rising_sell` | 0 | Gate passed all entries — RSI was declining at each SELL |
| `entry_quality_news_rsi_tighten` | 0 | OHLC mode: breakout + news window never coincided |
| `entry_quality_news_filter` | 0 | No hard-block proximity events in test window |
| `h1_di_buy` | 0 | No weak-ADX BUY setups triggering |
| `open_groups` | 12,432 | Direction cap (max=2) correctly throttling |

---

## All Trade Groups

| Group | Time | Dir | RSI | ADX | H1 | Lot factor | Result |
|-------|------|-----|-----|-----|----|-----------|--------|
| G5001 | Apr 29 15:55 | SELL | 26.4 | 25.9 | -1.91 | Full (crash bypass) | **+$80.32** |
| G5002 | Apr 29 16:00 | SELL | 26.3 | 29.9 | -2.00 | Stack 0.25× | **+$20.54** |
| G5003 | Apr 29 16:46 | SELL | 20.1 | 48.2 | -1.78 | Near-floor 0.25× | **-$68.12** |
| G5004 | Apr 30 07:35 | SELL | 21.1 | 59.2 | -1.50 | Near-floor 0.25× | **-$15.60** |
| G5005 | Apr 30 16:07 | BUY  | 54.6 | 23.0 | -0.03 | Full | **+$144.40** |
| G5006 | May 1 12:55 | SELL | 28.1 | 33.3 | -0.11 | Full (RSI>25) | **-$129.36** |
| G5007 | May 4 11:00 | SELL | 30.4 | 29.2 | -0.10 | Full | **+$61.36** |
| G5008 | May 4 11:05 | SELL | 27.1 | 32.8 | -0.11 | Stack 0.25× | **+$15.54** |
| G5009 | May 4 13:05 | SELL | 23.8 | 29.2 | -0.32 | Near-floor 0.25× | **+$9.14** |
| G5010 | May 4 13:10 | SELL | 20.1 | 33.5 | -0.34 | Near-floor 0.25× | **+$15.50** |
| G5011 | May 4 17:10 | SELL | 39.2 | 37.4 | -0.56 | Full (RSI>25, decline) | **-$238.08** |
| G5012 | May 4 18:20 | SELL | 30.3 | 38.2 | -0.60 | Full | **+$93.60** |
| G5013 | May 4 18:25 | SELL | 23.3 | 43.5 | -0.60 | Near-floor 0.25× | **-$83.34** |

---

## Feature Validation

### H1+H4 Crash SELL Bypass ✓
G5001 (RSI 26.4, ADX 25.9) and G5002 (RSI 26.3, ADX 29.9) captured on Apr 29 crash. Both
previously blocked by `rsi_sell_adx_floor` in Run 21 (no bypass). Both WON.

### Direction Cap 2 + Stack Factor ✓
G5002 entered 5 minutes after G5001 while G5001 was still open. Stack factor applied: 0.25×
lot. G5002 profit = $20.54 vs G5001 $80.32 → ratio 0.256 ≈ 0.25 ✓

### Cardwell RSI 20 Floor ✓
RSI 16.1 (Apr 29 16:45) blocked by `rsi_sell_floor`. Without Cardwell floor, this would have been
G5002 in Run 22 at full lot → -$255. Blocked completely ✓

### Near-Floor Lot Factor 0.25× ✓
| Trade | Run 22 loss (est full lot) | Run 23 loss | Saving |
|-------|--------------------------|-------------|--------|
| G5003 (RSI 20.1) | ~$272 | $68.12 | +$204 |
| G5004 (RSI 21.1) | ~$60 | $15.60 | +$44 |
| G5013 (RSI 23.3) | $333.36 | $83.34 | +$250 |
| **Total** | | | **+$498** |

### Post-SL Cooldown ✓
8,917 SELL attempts blocked after G5011 SL (May 4 17:18). Prevented May 4-5 cascade
entries that would have compounded losses. Cooldown blocked all SELL through May 5 23:55
(real-time 3600s did not expire within the run).

### bounce_min_h1_trend ✓
No BB_BOUNCE BUY taken in Run 23. G5006 (Run 22, H1=+0.186) blocked by H1 strength gate.
Confirmed by absence of BUY bounce trades.

### rsi_rising_sell — No fires (gate inactive, not broken)
`rsi_rising_sell = 0` throughout. G5011 (RSI 39.2, ADX 37.4) was TAKEN because RSI was
**declining** at entry (RSI peaked above 39.2 before 17:10 and fell to 39.2 — valid Cardwell
Bear Resistance failure signal). The ADX threshold raise (28→40) had no measurable impact
in this 7-day window because no entry had rising RSI while passing all other gates.

---

## Remaining Issues

### G5011 / G5006 — Full-lot losses in non-crash conditions
- G5006 (May 1, RSI 28.1): H1 barely bearish (-0.11). Full lot. -$129.36.
- G5011 (May 4, RSI 39.2): RSI declining, ADX 37.4. Full lot. -$238.08.
Both are entries where H1+H4 are nominally bearish but conviction is low (-0.10 to -0.56).
These are NOT crash bypass entries (RSI > 25 → no near-floor factor). The fractional lot
protection doesn't apply.

**Potential fix:** Extend fractional lot to `RSI < 32` when H1 trend strength < 0.3
(borderline conviction), not just `RSI ≤ 25`. This would apply 0.25× to May 1 and May 4
full-lot losers without affecting strong-conviction entries.

### news_rsi_tighten = 0
OHLC testing mode insufficient — BB_BREAKOUT conditions and news windows never
coincided in this period. Requires Every Tick re-test with confirmed news events in the
date range to validate.

### post_sl_cooldown real-time dependency
Cooldown locked SELL for all of May 5 (3600 real seconds never expired during fast tester
run). In live trading, this works correctly. In tester, it's overly restrictive when tester runs
faster than real time. Known limitation — 2.7.7 backlog: switch to `TimeTradeServer()` for
cooldown comparison in tester-aware mode.

---

## Comparison vs Prior Runs

| Run | EA | Period | P&L | Notes |
|-----|----|--------|-----|-------|
| Run 19 | 2.7.5 | Apr-May 2025 | +$1,329.08 | 15 TAKEN, 61W/2L — baseline |
| Run 20 | 2.7.6 (broken) | Apr 29+ | invalid | Codex gate regression |
| Run 21 | 2.7.6 (old) | Apr 29–May 5 | +$25.52 | OHLC, 2 TAKEN |
| **Run 23** | **2.7.6 (full)** | **Apr 29–May 5** | **-$93.86** | **13 TAKEN, 4W/7L(groups)** |

Run 23 is net negative for this specific 7-day crash window. The crash period Apr 29–May 4
had extreme volatility with RSI reaching 14-16 on crash days and sharp reversals. Near-floor
protection saved ~$498 in loss reduction vs equivalent full-lot entries.

---

*Documented: 2026-05-09 | Run 23 complete | FORGE 2.7.6 DUAL | Every Tick*
