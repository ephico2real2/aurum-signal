# FORGE 2.7.7 — Run 25 Analysis (Tester DB Agent-3000, run_id=1)

**Date:** 2026-05-09 | **Period:** Apr 29–May 4, 2026 | **Symbol:** XAUUSD | **Mode:** DUAL
**EA:** 2.7.6 (2.7.7 gates: session cutoff, MACD histogram, ADX tiers + block)
**Balance:** $10,000 | **Testing:** Every Tick

---

## Final Result

| Metric | Value |
|--------|-------|
| Net P&L | **+$257.58** |
| TAKEN | 5 |
| Losses | **0** |
| P&L by day | Apr 29 +$100.86 / Apr 30 +$144.40 / May 4 +$12.32 |

---

## Run comparison

| Run | EA | P&L | Losses | Key difference |
|-----|----|-----|--------|----------------|
| Run 23 | 2.7.6 (no 2.7.7 gates) | -$93.86 | 9 trade rows | G5011+G5013 at -$321 |
| Run 24 | 2.7.6 + H1/ADX gates | +$125.42 | 2 | G5011 still -$238 |
| **Run 25** | **2.7.7 full** | **+$257.58** | **0** | Session cutoff blocked G5011+G5013 |

---

## All TAKEN entries

| Group | Time | Setup | Dir | RSI | ADX | H1 | Result |
|-------|------|-------|-----|-----|-----|----|--------|
| G5001 | Apr 29 15:55 | BB_BREAKOUT | SELL | 26.4 | 25.9 | -1.91 | WIN |
| G5002 | Apr 29 16:00 | BB_BREAKOUT | SELL | 26.3 | 29.9 | -2.00 | WIN (stack 0.25×) |
| G5005 | Apr 30 16:07 | BB_BREAKOUT | BUY  | 54.6 | 23.0 | -0.03 | WIN +$144.40 |
| G5009 | May 4 13:05  | BB_BREAKOUT | SELL | 23.8 | 29.2 | -0.32 | WIN (near-floor 0.25×) |
| G5010 | May 4 13:10  | BB_BREAKOUT | SELL | 20.1 | 33.5 | -0.34 | WIN (near-floor 0.25×) |

---

## 2.7.7 Gate Validation

### Session SELL cutoff (session_ny_sell_cutoff_utc=17) ✓

**4 fires** — first appeared at sim 17:36 UTC (hour=17 ≥ 17), accumulated through 18:50.

| Previously taken | Time UTC | Run 23/24 loss | Run 25 |
|-----------------|----------|----------------|--------|
| G5011 SELL RSI 39.2 | 17:10 | -$238.08 | **BLOCKED** |
| G5013 SELL RSI 23.3 | 18:25 | -$83.34 | **BLOCKED** |

Session cutoff alone saved **+$321.42** vs Run 23. Gate working correctly.

### MACD(3,10,16) histogram gate — 0 fires

Expected. Gate order: session cutoff fires before MACD check. All late-session SELL
attempts (17:10+) were blocked by session cutoff before reaching MACD evaluation.
For valid 13:00–13:10 entries, MACD histogram was negative and contracting → entries
correctly passed. MACD gate needs a longer period or specific news event to observe
`macd_direction`/`macd_histogram` fires.

### ADX extreme block (adx_sell_block_threshold=55) — 0 fires

G5004 (ADX 59.2, Apr 30 07:35): blocked by `rsi_sell_floor` (RSI 21.1 ≤ 30 with crash
bypass OFF at ADX>40). The extreme block gate kicks in only when M15 ADX ≥ 55 AND
all other gates pass — in this period, the rsi_sell_floor acted first.

### ADX min sell — 4 fires ✓ (2.7.5 gate confirmed active)

---

## May 1 Analysis — Missed Parabolic Move

The user identified a **4-hour parabolic move on May 1 (08:30–12:30 UTC)**: a sharp
sell-off followed by a fast bull recovery. Neither leg was captured.

**Why the SELL leg was missed:**
- G5006 (RSI 28.1, H1=-0.11) blocked by `breakout_min_h1_bear_strength=0.2`
- H1 was barely negative — not genuine crash conviction
- The parabolic sell-off started with H1 still transitioning from the Apr 29 crash
- **This block is intentional** — H1=-0.11 has no edge

**Why the BUY recovery was missed:**
- After the sell-off, RSI bounced from ~20s back above 40 (Bull Support zone)
- But H1 was still bearish from the crash → `h1_ok_buy` gate blocks BUY when H1 bearish
- By the time H1 flipped bullish, the 4-hour parabolic rally was already over
- **Requires pending order infrastructure** (Feature 4/5 of 2.7.7 plan): SELL LIMIT
  placed above the crash entry catches the Cardwell bounce; BUY LIMIT placed at crash
  bottom captures the recovery when RSI crosses back above 40

**Parabolic move characteristics:**
- Duration: ~4 hours (short window)
- Direction change: crash → recovery within same trading day
- H1 lagged: didn't confirm direction until after the move completed
- **Conclusion:** Only pending order stacking (2.7.7b) can capture these. Market orders
  with H1 confirmation will always miss parabolic reversals because H1 is too slow.

---

## Gate Breakdown (excl. session_off)

| Gate | Count | Notes |
|------|-------|-------|
| `entry_quality_direction` | 21,391 | Directional bar quality |
| `open_groups` | 12,419 | Direction cap throttling |
| `entry_quality_body` | 11,727 | Doji/wick-dominant bars |
| `entry_quality_rsi_buy_ceil` | 9,868 | BUY overbought ceiling (70) |
| `entry_quality_atr` | 4,438 | Compressed market |
| `entry_quality_bb_contraction` | 3,146 | BB contracting |
| `entry_quality_session_sell_cutoff` | **4** | ✓ NEW 2.7.7 — blocks G5011+G5013 |
| `entry_quality_adx_min_sell` | 4 | ✓ 2.7.5 gate active |
| `entry_quality_rsi_sell_floor` | 4 | ✓ RSI floor active |

---

## DB Note

Run 25 started before the journal schema migration (macd_histogram, m15_adx,
lot_factor columns). These columns are NULL for this run. **Run 26** will be the first
run with all three new diagnostic columns populated.

---

## Pending — 2.7.7b Sprint

| Feature | Status | Impact |
|---------|--------|--------|
| SELL LIMIT cascade (Cardwell bounce re-short) | Not implemented | Captures Cardwell Bear Resistance re-entries |
| Recovery BUY capture | Not implemented | Captures post-crash parabolic rallies |
| M30 bearish confirmation gate | Not implemented | Additional high-ADX filter |

---

*Documented: 2026-05-09 | Run 25 complete | FORGE 2.7.7 | Every Tick | +$257.58, 5 TAKEN, 0 losses*
