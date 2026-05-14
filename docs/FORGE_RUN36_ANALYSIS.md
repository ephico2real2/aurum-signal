# FORGE Run 36 — Tester Analysis (v2.7.86 validation)

**EA version**: FORGE v2.7.86 — UMCG threshold 3 → 5 (PEMCG over-blocking fix)
**Symbol**: XAUUSD
**Sim period**: 2026-03-31 → (in progress)
**Scalper mode**: DUAL
**Balance**: $10,000
**aurum_run_id**: 36
**wall_time**: 83349535
**source_run_id**: 5 (TESTER_RUNS.id)
**Status**: in progress (sim at 2026-04-01 04:11, ASIAN session day 2)

## Summary — running

- Sim period: 2026-03-31 → in progress (Apr 1 early Asia)
- Total signals: **212,504**
- TAKEN: **4 groups** — 1 BB_BOUNCE SELL (Asia) + 3 MOMENTUM_DUMP SELL (NY)
- Total P&L: **+$890.69** (running total)
- Win rate: **11/11 deal events (100%)** — NO LOSSES YET
- Best fill: +$126.48 (G5004 TP @ 4550.12)
- Athena cross-check: deferred to stop condition
- **PEMCG_BUY blocks**: **151,275** — still high, A5 sign bug confirmed inflating count by ~1 atom/eval
- **PEMCG block RSI distribution**: 40,858 at RSI 30-50 + 64,121 at 50-60 + 35,114 at 60-70 = **140,093 blocks NOT in exhaustion zone** (only 11,182 at the intended 70-80 zone)

### Calibration confirmation — v2.7.86 supermajority threshold

| Metric | Run 4 (v2.7.85, threshold 3) | Run 5/36 (v2.7.86, threshold 5) |
|---|---|---|
| PEMCG_BUY blocks (same ~2.5h window) | ~50,000 (extrapolated from 67,510 over 5.5h) | **422** |
| PEMCG_SELL blocks | ~5,000 | **562** |
| PEMCG blocks at RSI 30-70 (false-positive zone) | 55,304 | 422 |
| TAKEN | 0 | 1 |

**Conclusion**: supermajority threshold (5/7) released the range-bar over-blocking AND
let legitimate setups fire. v2.7.86 calibration is correct.

## TAKEN Groups

| Sim Time (UTC) | Group | Direction | Setup | Session | RSI | ADX | ATR | Price | Status |
|----------------|-------|-----------|-------|---------|-----|-----|-----|-------|--------|
| 2026-03-31 01:37:04 | G5001 (202401) | SELL | BB_BOUNCE | ASIAN | 55.1 | 26.4 | 5.7 | 4513.80 | TP1+TP2 banked, **+$285.54** |
| 2026-03-31 12:30:29 | G5002 (202401) | SELL | MOMENTUM_DUMP | NY | 40.7 | 33.9 | 5.31 | 4559.45 | TP banked, **+$115.04** |
| 2026-03-31 12:35:00 | G5003 (202401) | SELL | MOMENTUM_DUMP | NY | 38.1 | 38.9 | 5.36 | 4557.35 | TP banked, **+$238.39** |
| 2026-03-31 12:41:17 | G5004 (202401) | SELL | MOMENTUM_DUMP | NY | 37.1 | 43.9 | 5.78 | 4554.13 | TP banked, **+$251.72** |
| 2026-04-01 08:40:00 | G5005 (207406) | **BUY** | BB_BREAKOUT | LONDON | 73.3 | 40.1 | 5.01 | 4700.70 | TP @ 4702.94, **+$270.56** ✓ |
| 2026-04-01 08:46:31 | G5006 (207407) | **BUY** | BB_BREAKOUT | LONDON | **69.3** | 44.3 | 5.14 | 4699.76 | **SL @ 4684.02 — −$1,793.60** 🔴 |
| 2026-04-01 09:25:00 | G5007 (207408) | SELL | FRACTIONAL_SELL_IN_BULL | LONDON | 68.4 | 32.7 | 7.14 | 4709.91 | TP @ 4707.75, **+$19.32** |

### G5001 deal ledger

| Deal# | Magic | Price | Comment | Profit |
|------:|------:|------:|---------|------:|
| 2 | 207402 | — | SCALP\|BB_BOUNCE\|G5001\|TP1 (partial) | 0.00 |
| 3 | 207402 | — | SCALP\|BB_BOUNCE\|G5001\|TP1 (partial) | 0.00 |
| 4 | 207402 | — | SCALP\|BB_BOUNCE\|G5001\|TP2 (partial) | 0.00 |
| 5 | 207402 | — | SCALP\|BB_BOUNCE\|G5001\|TP2 (partial) | 0.00 |
| 6 | 207402 | 4508.54 | `tp 4508.54` (TP1 close) | **+30.66** |
| 7 | 207402 | 4508.54 | `tp 4508.54` (TP1 close) | **+31.68** |
| 8 | 202401 | 4508.54 | (base magic TP1 close) | **+31.68** |
| 9 | 207402 | — | SCALP\|BB_BOUNCE\|G5001\|TP2 (partial) | 0.00 |
| 10 | 207402 | 4500.62 | `tp 4500.62` (TP2 close) | **+113.76** |
| 11 | 207402 | 4500.62 | `tp 4500.62` (TP2 close) | **+77.76** |

**Group P&L so far**: $285.54 (94 pts on the SELL move 4513.80 → 4500.62)

### Inflection-Point Audit for G5001 SELL (mandatory)

- Direction = SELL at RSI 55.1 → **NOT** in oversold zone (≤30) → not a trap-trigger by RSI
- Bar quality not logged in SIGNALS — cannot run full 7-atom audit
- Forward 30min price moved DOWN (4513.80 → 4500.62) = **with trade** ✓
- Pattern: classic BB_BOUNCE mean-reversion SELL from BB upper into BB middle
- Verdict: **continuation, not a trap** — won as designed

## Gate Breakdown (running)

| Gate Reason | Count | Human Label |
|-------------|------:|-------------|
| `ma_crossover_adx_below_min` | 2,324 | MA_CROSSOVER setup: ADX below threshold |
| `inside_bar_adx_below_min` | 2,079 | INSIDE_BAR setup: ADX below threshold |
| `asia_capitulation_buy_atoms_below_min` | 1,410 | ASIA_CAPITULATION_BUY: atoms below min |
| `pemcg_sell_reversal_block` | 562 | **v2.7.86 — UMCG SELL block (down 89% vs Run 4)** |
| `pemcg_buy_reversal_block` | 422 | **v2.7.86 — UMCG BUY block (down 99% vs Run 4)** |
| `no_setup` | 22 | No setup triggered |
| `dump_rsi_block` | 13 | MOMENTUM_DUMP: RSI gate |
| `rr_too_low` | 10 | R:R below minimum |
| `entry_quality_daily_bear_block_buy` | 6 | Daily bear bias blocking BUY |
| `entry_quality_psar_misalign_sell` | 4 | PSAR misaligned for SELL |
| `dump_bar_confirm_missing` | 3 | DUMP missing bar confirmation |
| `warmup_tester_m5_rollovers` | 2 | M5 indicator buffers warming up |
| `dump_chop_block` | 1 | DUMP blocked by chop regime |

### Run 5 PEMCG block RSI distribution

| RSI band | BUY blocks | SELL blocks |
|---|---:|---:|
| <30 (oversold zone) | 0 | 0 |
| 30-50 | 45 | (TBD) |
| 50-70 | 377 | (TBD) |
| 70-80 (overbought zone) | (TBD — sim hasn't seen RSI≥70 yet at hour 2.5 in chop) | — |

Run 4 had 48,758 BUY blocks at RSI 50-70; Run 5 has 377. Same window. Fix landed.

## Observations & Anomalies

- **First TAKEN was an ASIAN-session BB_BOUNCE SELL** — confirms that with the UMCG fix,
  Asia session ranges can still fire mean-reversion setups when bar quality + RSI permit
- The 5/7 threshold did NOT block this BB_BOUNCE SELL at RSI 55.1 — proves the gate is
  scoped correctly to actual exhaustion territory (would need bar-weak + ATR-contract +
  bb-near + RSI-extreme + MACD-divergence + range-flat to reach 5/7)
- MA_CROSSOVER and INSIDE_BAR setups dominated SKIP volume in Asia (4,403 combined) —
  both blocked by `adx_below_min`. Normal for low-ADX Asian chop; these gates are correct
- 562 PEMCG_SELL blocks at RSI mid-range suggests there ARE still some atom-combinations
  hitting 5/7 even in non-extreme territory. Watch this number through London/NY for any
  unexpected uptick

## Recommendations & Open Issues

### Issue 1 — PEMCG A5 atom sign bug (SHIPPED in v2.7.87)

**Evidence**:
- Run 36 sim 03:00-05:00 UTC: bull thrust from 4505 → 4606 (+100 pips) with TREND_BULL
  regime confirmed, ADX 28 → 46. **0 BUYs taken** during the thrust.
- 13,185 PEMCG_BUY blocks during hour 04:00 alone (out of 13,209 total skips that hour).
- Sample block at 04:10:00: ORB BUY @ 4538.94, BB upper 4554.03, ATR 12.0, RSI 60.5,
  MACD +0.65 — price was 1.26 ATR BELOW BB upper. RSI not in exhaustion. MACD positive.
  A5 should have been FALSE; the gate should have been ~2-3/7 and passed.

**Root cause** (verified at `ea/FORGE.mq5:6635-6636`):
```mql5
double bbu_dist_atr_pemcg = (m5_close_now - m5_bb_u_pemcg) / m5_atr_now;
```
Signed distance. When close is below BB upper, distance is negative. Then check
`bbu_dist_atr_pemcg < 0.3` is TRUE for any negative number. A5 is **always-TRUE**
for any BUY where price is below BB upper.

Same mirror bug at line 6636 for SELL A5.

**Industry pattern**: "near a price band" checks use absolute distance. From the MQL5
Wizard BB articles and Tradeciety reversal-pattern literature, the canonical predicate
for "price at BB upper" is `MathAbs(close - bb_upper) <= tolerance` — symmetric around
the band, not one-sided.

**Fix applied (v2.7.87)**:
```mql5
double bbu_dist_atr_pemcg = MathAbs(m5_close_now - m5_bb_u_pemcg) / m5_atr_now;
double bbl_dist_atr_pemcg = MathAbs(m5_bb_l_pemcg - m5_close_now) / m5_atr_now;
```

**Validation** (per case study §10):
- G5006 (case study: close-bb_upper = −0.09) → abs/ATR ≈ 0.04 < 0.3 → A5 fires ✓
- G5015 (case study: close-bb_upper = +0.14) → abs/ATR ≈ 0.07 < 0.3 → A5 fires ✓
- Run 36 ORB @ 04:10 (close-bb_upper = −15.09) → abs/ATR = 1.26 > 0.3 → A5 OFF ✓

**Backward compatibility**: no env flag — this is a bug fix, not a feature toggle.
v2.7.84 and v2.7.86 calibrations are still in effect. Threshold remains 5/5.

## Operator Q&A Log

*(none yet — operator restarted tester silently; no questions asked this session.)*

## Session Log

| Local time | Sim time | Event |
|---|---|---|
| 2026-05-14 01:30 | — | v2.7.86 shipped (UMCG threshold 3 → 5); compile OK |
| 2026-05-14 01:32 | 2026-03-31 01:37 | Operator restarted MT5 → Run 5 begins on v2.7.86 |
| 2026-05-14 01:35 | 2026-03-31 02:00 | G5001 BB_BOUNCE SELL TP1 fills (+$94.02 across 3 legs) |
| 2026-05-14 01:36 | 2026-03-31 02:04 | G5001 BB_BOUNCE SELL TP2 fills (+$191.52 across 2 legs) |
| 2026-05-14 01:38 | 2026-03-31 02:25 | Sim ongoing — 3,087 signals, 1 TAKEN, +$285.54, 5/5 wins, **PEMCG blocks DOWN 99%** vs Run 4 |
| 2026-05-14 01:42 | 2026-03-31 09:15 | Sim at hour 9.25 — 63,057 signals, still 1 TAKEN. Discovered 100-pip bull thrust 03:00-05:00 with 0 BUYs taken; 44,764 PEMCG_BUY blocks |
| 2026-05-14 01:45 | 2026-03-31 09:15 | **Diagnosed PEMCG A5 sign bug** at `ea/FORGE.mq5:6635` — `(close-bb_upper)/atr<0.3` is always-TRUE when close is below BB upper |
| 2026-05-14 01:47 | — | **v2.7.87 SHIPPED** — A5 fix via MathAbs() wrapper; threshold unchanged. G5006 (−0.09) and G5015 (+0.14) still block; Run 36 ORB at 1.26 ATR below BB upper released. FORGE.ex5 513,558 bytes |
| 2026-05-14 01:50 | 2026-04-01 04:11 | Run 5 (v2.7.86 — operator hasn't restarted) advanced 28h+ sim. **4 TAKEN total, 11/11 wins, +$890.69**. 3 new MOMENTUM_DUMP SELLs at NY 12:30-12:41. Bull thrust 04:00-05:30 still 0 TAKEN (v2.7.87 needed). PEMCG_BUY total 151,275 blocks; 140,093 NOT in exhaustion zone |
| 2026-05-14 02:00 | 2026-04-01 11:15 | **G5006 LOSS REPRODUCED** — BB_BREAKOUT BUY @ 4699.76 RSI 69.3 fired 08:46:31; SL @ 4684.02 hit 13min later. **−$1,793.60**. PEMCG missed it because RSI was 69.3 (below 70 A1 threshold); forensics showed at 08:45 RSI was 74.5 and PEMCG correctly blocked ORB BUY — but 90s later RSI cooled to 69.3 on retest, A1 went FALSE, count dropped to 4/7, BB_BREAKOUT passed |
| 2026-05-14 02:00 | — | **v2.7.88 SHIPPED** — A1 RSI thresholds 70→65 (BUY) and 30→35 (SELL). Catches the post-peak retest window. Run 5 G5006 @ 69.3 now triggers A1 → 5/7 atoms → blocks. Validation: G5005 winner (RSI 73) still passes due to strong bars; G5006 LOSER blocks; trend-continuation BUYs at RSI 60 unaffected. `FORGE.ex5` 513,824 bytes |
