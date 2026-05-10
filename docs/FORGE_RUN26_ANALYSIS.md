# FORGE 2.7.9 — Run 1 Analysis (Tester DB Agent-3000, run_id=1)

**Date:** 2026-05-09 | **Period:** Apr 29–May 4, 2026 | **Symbol:** XAUUSD | **Mode:** DUAL  
**EA:** 2.7.9 (M30 EMA bearish confirmation gate added — Feature 3)  
**Balance:** $10,000 | **Testing:** Every Tick

---

## Final Result

| Metric | Value |
|--------|-------|
| Net P&L | **+$257.58** |
| TAKEN | 5 |
| Losses | **0** |
| Win rate | 100% |

---

## Run comparison

| Run | EA | P&L | Losses | Key difference |
|-----|----|-----|--------|----------------|
| Run 23 | 2.7.6 (no 2.7.7 gates) | -$93.86 | 9 | No session/MACD/ADX gates |
| Run 24 | 2.7.6 + H1/ADX gates | +$125.42 | 2 | G5011 still -$238 |
| Run 25 | 2.7.7 full | +$257.58 | 0 | Session cutoff blocked G5011+G5013 |
| **Run 1** | **2.7.9 (M30 added)** | **+$257.58** | **0** | M30 gate added; 0 fires this period |

---

## All TAKEN entries

| Group | Time | Setup | Dir | RSI | ADX | Result |
|-------|------|-------|-----|-----|-----|--------|
| G1 | Apr 29 15:55 | BB_BREAKOUT | SELL | 26.45 | 25.85 | WIN |
| G2 | Apr 29 16:00 | BB_BREAKOUT | SELL | 26.34 | 29.91 | WIN (stack 0.25×) |
| G3 | Apr 30 16:07 | BB_BREAKOUT | BUY  | 54.62 | 23.01 | WIN +$144.40 |
| G4 | May 4 13:05  | BB_BREAKOUT | SELL | 23.78 | 29.22 | WIN (near-floor 0.25×) |
| G5 | May 4 13:10  | BB_BREAKOUT | SELL | 20.12 | 33.48 | WIN (near-floor 0.25×) |

---

## 2.7.9 Gate Validation

### M30 EMA bearish confirmation — 0 fires ✓

The new `entry_quality_m30_not_bearish` gate (Feature 3, 2.7.9) had **zero fires** this period.

This is correct behavior: every entry that passed the OsMA Q2 gate and reached the M30 check already had M30 EMA20 < EMA50 (M30 bearish), confirming trend alignment. The gate is a safety net for recovery entries where M30 has crossed bullish before the crash completes — no such cases occurred in Apr 29–May 4.

**Gate not over-filtering:** P&L identical to Run 25 (+$257.58). Zero entries blocked by M30 that were previously taken.

### Session SELL cutoff (17:00 UTC) — 4 fires ✓

| Time UTC | Action |
|----------|--------|
| 4 fires post-17:00 | **BLOCKED** by session cutoff |

Consistent with Run 25. Gate protecting against late-NY reversal zone.

### ADX min SELL — 4 fires ✓

Same 4 ADX gate blocks as prior runs. Gate active and consistent.

### MACD quadrant gates — 0 fires

No SELL entry reached the OsMA Q2 check and was blocked. All rejections happened at earlier gates (ATR, body quality, direction bars, RSI ceiling).

### OsMA BUY Q0 gate (enabled in 2.7.8)

G3 BUY at RSI 54.62, ADX 23.01 cleared the Q0 check — OsMA was positive and rising at entry time. Gate passed correctly.

---

## Complete Gate Breakdown

| Gate | Count | Notes |
|------|-------|-------|
| `entry_quality_direction` | 21,391 | Directional bar quality (dominant) |
| `open_groups` | 12,418 | Direction cap throttling |
| `entry_quality_body` | 11,727 | Doji/wick-dominant bars |
| `entry_quality_rsi_buy_ceil` | 9,868 | BUY overbought ceiling (70) |
| `entry_quality_atr` | 4,438 | Compressed market |
| `entry_quality_bb_contraction` | 3,146 | BB contracting |
| `entry_quality_session_sell_cutoff` | **4** | ✓ 17:00 UTC cutoff |
| `entry_quality_rsi_sell_floor` | 4 | RSI floor active |
| `entry_quality_adx_min_sell` | 4 | ADX min SELL gate |
| `entry_quality_m30_not_bearish` | **0** | ✓ NEW 2.7.9 — no blocks this period |
| `rr_too_low` | 2 | R:R filter |
| `entry_quality_rsi_sell_adx_floor` | 1 | Two-tier RSI floor |

---

## Next Steps

The M30 gate needs a longer/different test period to validate its blocking behavior. Ideal test periods: May 1 recovery zone (where H1 was stale-bearish while M30 recovered) or any period with rapid trend reversals.

Recommend running a longer backtest (Apr 1–May 31) to:
1. Confirm M30 fires in at least one recovery scenario
2. Verify it blocks losers without filtering winners
3. Compare Run 26 P&L vs prior runs across the full period

---

*Documented: 2026-05-09 | Run 1 complete | FORGE 2.7.9 | Every Tick | +$257.58, 5 TAKEN, 0 losses*
