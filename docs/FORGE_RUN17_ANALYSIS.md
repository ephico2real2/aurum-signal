# FORGE Run 17 — Tester Analysis (v2.7.22 epoch)

**EA version**: FORGE v2.7.22
**Symbol**: XAUUSD
**Sim period**: 2026-04-01 → 2026-05-07
**Scalper mode**: DUAL
**Balance**: $10,000
**aurum_run_id**: 17
**wall_time**: 550109260
**source_run_id**: 3
**Magic base**: 202401
**Status**: COMPLETE
**Last reviewed**: 2026-05-11

> Prior aurum_run_id=17 from v2.7.3 epoch archived as `FORGE_RUN17_ANALYSIS_OLD_v2.7.3.md`.

---

## Summary — FINAL

| Metric | Value |
|--------|-------|
| Sim period | 2026-04-01 → 2026-05-07 (37 calendar days) |
| Total signals | 7,444 |
| TAKEN | 83 (all 83 distinct groups; LONDON-only) |
| SKIP | 7,361 |
| Profit events (trades w/ non-zero P&L) | 868 |
| Wins | 810 |
| Losses | 58 |
| Win rate | 93.32% |
| **Net P&L** | **+$5,630.29** |
| Best win event | +$89.84 |
| Worst loss event | −$131.44 (G5048 leg) |
| **Single worst group** | **G5048 −$1,666.32** (13 legs SL'd same minute) |
| Sessions used | LONDON 100% (NY zero TAKEN) |

**Cross-check with prior runs**:

| Metric | Run 15 (v2.7.16) | Run 16 (v2.7.21) | Run 17 (v2.7.22) |
|---|---|---|---|
| Forge version | 2.7.16 | 2.7.21 | 2.7.22 |
| TAKEN | 52 | 1 | 83 |
| Net P&L | (prior) | ~$0 (neutered) | +$5,630.29 |
| Notes | baseline | R:R bug blocked all BB_BREAKOUT BUY | R:R decouple unblocks BUY; G5048 disaster surfaces |

---

## What's NEW in Run 17 vs Run 16 (v2.7.21 → v2.7.22)

Run 16 was effectively neutered — `breakout_buy_sl_atr_mult=3.0` made the R:R gate fail on every BB_BREAKOUT BUY because the placed SL (3.0×ATR) was used as the R:R denominator. Result: 0 BB_BREAKOUT BUY entries in 18+ sim hours.

**v2.7.22 surgical fix** (ea/FORGE.mq5:5953):
- R:R risk now computed from BASE `breakout_sl_atr_mult` (2.0×ATR) with high_vol_boost applied
- SL placement still uses widened `breakout_buy_sl_atr_mult` (3.0×ATR) for SL-hunt protection
- BB_BOUNCE / SELL R:R math unchanged

**Outcome confirmed**: BB_BREAKOUT BUY fires correctly — 18 entries booked in the run (vs 0 in Run 16). All v2.7.17–v2.7.21 gates were properly stress-tested for the first time.

---

## Hypothesis validation

| # | Hypothesis | Status | Evidence |
|---|------------|--------|----------|
| 1 | v2.7.22 R:R fix unblocks BB_BREAKOUT BUY | **PASS** | 18 BB_BREAKOUT BUY taken in run |
| 2 | Cooldown 900s blocks G5002 (5min after G5001) | **PASS** | `entry_quality_breakout_cooldown` fired 10× (60% precision) |
| 3 | Fix B failed-breakout blocks G5013 (atr_ext same-bar + RSI rollover) | **PASS** | `entry_quality_breakout_failed_samebar` fired 44× (50% precision) |
| 4 | Same-bar hard block catches G5015 | **PASS** | (subset of above) |
| 5 | Same-bar hard block catches G5018 | **PASS** | (subset of above) |
| 6 | PSAR alignment blocks G5035 (FLIP_BEAR) | **PARTIAL** | `entry_quality_psar_misalign_buy` 5× (40% precision); `_sell` 2× at 0% precision |
| 7 | RSI floor 33 blocks G5040 (RSI 32.4 SELL) | **PASS** | `entry_quality_rsi_sell_floor` fired 27× |
| 8 | **NEW disaster surfaces** that no current gate catches | **FAIL (gate side)** | G5048 −$1,666 BUY into multi-day rollover — no daily-direction gate exists |

---

## TAKEN Groups (all 83)

| # | Sim time (UTC) | Setup | Dir | Price | ATR | RSI | ADX | Session |
|---|----------------|-------|-----|-------|-----|-----|-----|---------|
| 1 | 2026-04-01 08:40 | BB_BREAKOUT | BUY | 4700.47 | 5.01 | 73.3 | 40.1 | LONDON |
| 2 | 2026-04-01 09:28 | BB_BREAKOUT | BUY | 4706.01 | 7.59 | 63.6 | 33.2 | LONDON |
| 3 | 2026-04-02 10:25 | BB_BOUNCE | SELL | 4617.92 | 11.04 | 50.6 | 29.9 | LONDON |
| 4 | 2026-04-02 12:15 | BB_BOUNCE | BUY | 4623.24 | 8.33 | 46.5 | 25.8 | LONDON |
| 5 | 2026-04-06 10:50 | BB_BREAKOUT | BUY | 4672.54 | 6.52 | 63.5 | 31.4 | LONDON |
| 6 | 2026-04-07 11:20 | BB_BOUNCE | SELL | 4660.25 | 7.07 | 63.1 | 25.6 | LONDON |
| 7 | 2026-04-07 11:25 | BB_BREAKOUT | BUY | 4683.39 | 8.9 | 75.2 | 31.3 | LONDON |
| 8 | 2026-04-07 15:25 | BB_BOUNCE | SELL | 4668.33 | 7.78 | 58.3 | 28.1 | LONDON |
| 9 | 2026-04-08 07:20 | BB_BOUNCE | BUY | 4794.94 | 4.93 | 40.1 | 22.5 | LONDON |
| 10 | 2026-04-08 11:30 | BB_BOUNCE | BUY | 4806.09 | 7.04 | 39.8 | 19.1 | LONDON |
| 11 | 2026-04-08 12:50 | BB_BOUNCE | BUY | 4786.16 | 7.57 | 34.1 | 23.0 | LONDON |
| 12 | 2026-04-08 13:25 | BB_BOUNCE | BUY | 4778.99 | 8.09 | 34.0 | 28.8 | LONDON |
| 13 | 2026-04-08 15:30 | BB_BOUNCE | BUY | 4784.69 | 9.61 | 45.7 | 22.3 | LONDON |
| 14 | 2026-04-08 16:35 | BB_BOUNCE | BUY | 4783.29 | 7.5 | 42.1 | 21.8 | LONDON |
| 15 | 2026-04-08 17:00 | BB_BOUNCE | BUY | 4777.67 | 9.65 | 42.9 | 17.5 | LONDON |
| 16 | 2026-04-08 17:30 | BB_BOUNCE | BUY | 4768.11 | 12.01 | 39.1 | 21.7 | LONDON |
| 17 | 2026-04-08 17:41 | BB_BOUNCE | BUY | 4767.51 | 12.6 | 42.4 | 29.9 | LONDON |
| 18 | 2026-04-09 13:51 | BB_BREAKOUT | BUY | 4743.11 | 4.68 | 66.4 | 22.6 | LONDON |
| 19 | 2026-04-10 08:05 | BB_BOUNCE | BUY | 4762.40 | 2.97 | 50.0 | 27.2 | LONDON |
| 20 | 2026-04-10 08:55 | BB_BOUNCE | SELL | 4766.71 | 3.75 | 59.6 | 22.0 | LONDON |
| 21 | 2026-04-10 09:40 | BB_BOUNCE | BUY | 4752.22 | 4.22 | 37.3 | 24.1 | LONDON |
| 22 | 2026-04-10 10:07 | BB_BOUNCE | BUY | 4750.12 | 5.39 | 40.7 | 29.0 | LONDON |
| 23 | 2026-04-10 11:20 | BB_BOUNCE | BUY | 4745.75 | 4.11 | 37.5 | 24.8 | LONDON |
| 24 | 2026-04-10 12:00 | BB_BOUNCE | BUY | 4741.77 | 5.26 | 39.1 | 22.3 | LONDON |
| 25 | 2026-04-10 13:30 | BB_BOUNCE | SELL | 4758.73 | 4.05 | 61.0 | 22.5 | LONDON |
| 26 | 2026-04-10 14:45 | BB_BREAKOUT | BUY | 4767.27 | 3.68 | 66.0 | 31.6 | LONDON |
| 27 | 2026-04-10 15:00 | BB_BREAKOUT | BUY | 4767.04 | 4.04 | 62.7 | 38.9 | LONDON |
| 28 | 2026-04-10 18:45 | BB_BOUNCE | BUY | 4766.27 | 8.53 | 41.1 | 25.1 | LONDON |
| 29 | 2026-04-13 08:05 | BB_BOUNCE | SELL | 4721.65 | 4.24 | 59.3 | 29.0 | LONDON |
| 30 | 2026-04-13 10:55 | BB_BOUNCE | SELL | 4734.41 | 5.38 | 57.4 | 23.4 | LONDON |
| 31 | 2026-04-14 08:30 | BB_BOUNCE | BUY | 4767.27 | 3.07 | 42.7 | 29.9 | LONDON |
| 32 | 2026-04-14 12:41 | BB_BOUNCE | BUY | 4776.60 | 4.65 | 43.6 | 19.8 | LONDON |
| 33 | 2026-04-14 12:50 | BB_BOUNCE | BUY | 4776.20 | 4.45 | 43.0 | 24.5 | LONDON |
| 34 | 2026-04-14 15:20 | BB_BOUNCE | BUY | 4769.17 | 4.71 | 39.3 | 21.6 | LONDON |
| 35 | 2026-04-15 08:43 | BB_BOUNCE | BUY | 4816.33 | 4.67 | 34.7 | 16.7 | LONDON |
| 36 | 2026-04-15 10:16 | BB_BOUNCE | BUY | 4810.83 | 5.45 | 40.1 | 28.6 | LONDON |
| 37 | 2026-04-15 14:15 | BB_BOUNCE | SELL | 4802.77 | 4.44 | 52.6 | 21.1 | LONDON |
| 38 | 2026-04-15 14:33 | BB_BOUNCE | SELL | 4803.39 | 4.39 | 52.5 | 28.7 | LONDON |
| 39 | 2026-04-15 14:35 | BB_BOUNCE | SELL | 4803.04 | 4.09 | 51.8 | 25.5 | LONDON |
| 40 | 2026-04-15 16:30 | BB_BREAKOUT | BUY | 4821.86 | 4.59 | 72.1 | 23.0 | LONDON |
| 41 | 2026-04-15 16:35 | BB_BOUNCE | SELL | 4819.35 | 4.69 | 64.5 | 23.9 | LONDON |
| 42 | 2026-04-15 16:50 | BB_BREAKOUT | BUY | 4825.14 | 5.40 | 67.8 | 32.8 | LONDON |
| 43 | 2026-04-16 08:05 | BB_BREAKOUT | BUY | 4836.58 | 2.40 | 72.7 | 37.7 | LONDON |
| 44 | 2026-04-16 09:05 | BB_BOUNCE | BUY | 4824.42 | 3.98 | 43.9 | 27.0 | LONDON |
| 45 | 2026-04-16 09:25 | BB_BOUNCE | BUY | 4821.32 | 4.39 | 39.4 | 29.7 | LONDON |
| 46 | 2026-04-16 13:35 | BB_BOUNCE | BUY | 4808.33 | 3.56 | 38.8 | 27.4 | LONDON |
| 47 | 2026-04-16 14:10 | BB_BOUNCE | SELL | 4818.21 | 3.32 | 59.9 | 27.8 | LONDON |
| 48 | **2026-04-16 16:35** | **BB_BREAKOUT** | **BUY** | **4822.65** | **5.00** | **58.4** | **26.9** | **LONDON ⚠** |
| 49 | 2026-04-17 11:54 | BB_BOUNCE | SELL | 4793.45 | 4.96 | 56.8 | 29.9 | LONDON |
| 50 | 2026-04-17 16:01 | BB_BREAKOUT | BUY | 4839.21 | 7.31 | 76.0 | 60.5 | LONDON |
| 51 | 2026-04-20 10:10 | BB_BOUNCE | SELL | 4796.04 | 4.49 | 58.5 | 20.0 | LONDON |
| 52 | 2026-04-20 16:30 | BB_BREAKOUT | BUY | 4824.85 | 6.15 | 74.2 | 30.3 | LONDON |
| 53 | 2026-04-21 10:55 | BB_BOUNCE | SELL | 4788.79 | 4.32 | 56.8 | 24.6 | LONDON |
| 54 | 2026-04-21 14:05 | BB_BOUNCE | SELL | 4787.26 | 2.61 | 53.1 | 28.1 | LONDON |
| 55 | 2026-04-22 08:30 | BB_BOUNCE | SELL | 4766.10 | 3.80 | 64.8 | 24.4 | LONDON |
| 56 | 2026-04-22 16:55 | BB_BOUNCE | SELL | 4754.83 | 6.55 | 56.5 | 19.7 | LONDON |
| 57 | 2026-04-23 08:15 | BB_BOUNCE | SELL | 4707.71 | 2.98 | 51.8 | 20.7 | LONDON |
| 58 | 2026-04-23 09:10 | BB_BOUNCE | SELL | 4713.20 | 4.64 | 59.3 | 21.7 | LONDON |
| 59 | 2026-04-23 09:55 | BB_BOUNCE | SELL | 4714.39 | 4.30 | 58.7 | 20.8 | LONDON |
| 60 | 2026-04-23 12:05 | BB_BREAKOUT | SELL | 4699.18 | 5.06 | 35.7 | 39.8 | LONDON |
| 61 | 2026-04-23 18:20 | BB_BOUNCE | SELL | 4738.19 | 5.61 | 61.3 | 22.7 | LONDON |
| 62 | 2026-04-23 18:25 | BB_BOUNCE | SELL | 4736.24 | 5.61 | 58.1 | 21.9 | LONDON |
| 63 | 2026-04-24 07:25 | BB_BREAKOUT | SELL | 4661.58 | 3.72 | 27.2 | 38.9 | LONDON |
| 64 | 2026-04-24 14:20 | BB_BOUNCE | SELL | 4695.26 | 5.63 | 63.8 | 24.0 | LONDON |
| 65 | 2026-04-27 15:25 | BB_BOUNCE | SELL | 4709.04 | 3.69 | 59.0 | 23.4 | LONDON |
| 66 | 2026-04-28 08:05 | BB_BREAKOUT | SELL | 4663.30 | 2.21 | 31.1 | 27.0 | LONDON |
| 67 | 2026-04-29 16:00 | BB_BREAKOUT | SELL | 4546.13 | 5.57 | 26.3 | 29.9 | LONDON |
| 68 | 2026-04-30 07:05 | BB_BREAKOUT | SELL | 4554.62 | 3.58 | 33.3 | 41.3 | LONDON |
| 69 | 2026-04-30 16:07 | BB_BREAKOUT | BUY | 4636.76 | 7.00 | 54.6 | 23.0 | LONDON |
| 70 | 2026-05-01 14:30 | BB_BOUNCE | SELL | 4571.71 | 3.57 | 53.7 | 22.6 | LONDON |
| 71 | 2026-05-01 14:45 | BB_BOUNCE | SELL | 4575.68 | 3.52 | 59.8 | 27.1 | LONDON |
| 72 | 2026-05-01 16:50 | BB_BOUNCE | SELL | 4601.04 | 5.88 | 61.2 | 18.8 | LONDON |
| 73 | 2026-05-01 17:00 | BB_BREAKOUT | BUY | 4626.12 | 7.76 | 74.9 | 26.1 | LONDON |
| 74 | 2026-05-04 13:05 | BB_BREAKOUT | SELL | 4559.36 | 4.71 | 23.8 | 29.2 | LONDON |
| 75 | 2026-05-04 17:30 | BB_BOUNCE | SELL | 4573.27 | 7.94 | 56.5 | 24.6 | LONDON |
| 76 | 2026-05-04 17:35 | BB_BOUNCE | SELL | 4575.36 | 8.06 | 58.4 | 24.7 | LONDON |
| 77 | 2026-05-04 17:45 | BB_BOUNCE | SELL | 4574.59 | 7.57 | 55.8 | 27.6 | LONDON |
| 78 | 2026-05-05 08:45 | BB_BOUNCE | SELL | 4545.37 | 4.13 | 62.5 | 28.5 | LONDON |
| 79 | 2026-05-05 12:05 | BB_BOUNCE | SELL | 4555.15 | 4.16 | 58.2 | 23.0 | LONDON |
| 80 | 2026-05-05 12:15 | BB_BOUNCE | SELL | 4556.95 | 4.17 | 59.0 | 26.7 | LONDON |
| 81 | 2026-05-06 07:30 | BB_BREAKOUT | BUY | 4651.63 | 3.74 | 66.5 | 38.8 | LONDON |
| 82 | 2026-05-06 08:10 | BB_BREAKOUT | BUY | 4655.73 | 3.70 | 67.7 | 35.4 | LONDON |
| 83 | 2026-05-07 09:30 | BB_BREAKOUT | BUY | 4717.48 | 4.04 | 71.7 | 36.0 | LONDON |

**Setup/direction split**: BB_BOUNCE SELL 34, BB_BOUNCE BUY 25, BB_BREAKOUT BUY 18, BB_BREAKOUT SELL 6.

**Session anomaly**: 0 NY-session TAKEN. Either NY conditions never met current gate stack, or the `session_off` block (3,094 SKIPs) is filtering it out by design. Worth investigating — half the trading day is unused.

---

## Hourly P&L (STATS_CACHE)

| Hour (UTC) | Trades | Win rate | P&L |
|---|---|---|---|
| 01 | 10 | 100% | +$200.02 |
| 03 | 3 | 100% | −$4.22 |
| 04 | 22 | 100% | +$41.13 |
| 07 | 39 | 94.87% | +$267.72 |
| 08 | 66 | 100% | +$585.50 |
| 09 | 84 | 97.62% | +$715.09 |
| 10 | 78 | 93.59% | +$413.35 |
| 11 | 23 | 86.96% | +$83.31 |
| 12 | 58 | 98.28% | +$416.10 |
| **13** | **143** | **99.30%** | **+$1,080.86** |
| 14 | 35 | 54.29% | +$166.57 |
| 15 | 79 | 96.20% | +$361.42 |
| **16** | **83** | **78.31%** | **−$274.97** |
| 17 | 65 | 93.85% | +$412.93 |
| 18 | 65 | 96.92% | +$758.58 |
| 19 | 13 | 92.31% | +$141.12 |
| 20 | 2 | 100% | −$4.55 |

Hour 13 is the workhorse (+$1,081, 143 events). **Hour 16 is the only red hour** — G5048 (Apr 16 16:51) and the Apr 15 14:46→16:50 SELL cluster (which exits in 16:50:38) both fall here.

---

## P&L by magic (top winners + all losers)

**Top 10 winners**:

| Magic | Trades | Wins | Losses | P&L | Best |
|---|---|---|---|---|---|
| 202401 (base — final closes) | 217 | 217 | 0 | +$2,164.93 | $41.32 |
| 207468 | 7 | 7 | 0 | +$332.72 | $83.12 |
| 207441 | 13 | 13 | 0 | +$217.52 | $30.48 |
| 207417 | 11 | 11 | 0 | +$170.51 | $18.20 |
| 207462 | 7 | 7 | 0 | +$169.32 | $35.68 |
| 207410 | 11 | 11 | 0 | +$159.54 | $22.16 |
| 207474 | 3 | 3 | 0 | +$148.00 | $89.84 |
| 207418 | 11 | 11 | 0 | +$145.53 | $17.60 |
| 207451 | 3 | 3 | 0 | +$142.40 | $85.76 |
| 207476 | 7 | 7 | 0 | +$132.82 | $35.76 |

**All loss magics**:

| Magic | Legs | P&L | Avg lot | Exit | Category |
|---|---|---|---|---|---|
| 207449 (G5048) | 13 | **−$1,666.32** | 0.08 | 2026-04-16 16:51:48 | **DIRECTION FAILURE — daily rollover** |
| 207442 (G5041) | 5 | −$74.66 | 0.02 | 2026-04-15 16:50:38 | SELL stopped by upward push |
| 207438 (G5037) | 5 | −$72.98 | 0.02 | 2026-04-15 14:46:19 | SELL stopped by upward push |
| 207452 (G5051) | 5 | −$70.96 | 0.02 | 2026-04-20 10:18:35 | SELL stopped by upward push |
| 207443 (G5042) | 1 | −$39.56 | 0.02 | 2026-04-15 18:05:16 | Runner SL after net-positive group |
| 207439 (G5038) | 5 | −$34.61 | 0.01 | 2026-04-15 14:46:19 | SELL stopped by upward push |
| 207440 (G5039) | 5 | −$32.43 | 0.01 | 2026-04-15 14:46:19 | SELL stopped by upward push |
| 227485 / 227487 | 1+1 | −$31.32 | 0.02 | 2026-05-04 17:59:24 | Cascade slot SL (normal) |
| 227418 / 227466 / 227464 / 227471 / 227440 / 227459 / 227439 / 227468 / 227463 / 227430 / 227475 / 227465 / 227435 | various | total ≈ −$129 | 0.01–0.02 | various | Cascade slot SLs (normal, offset by 12 cascade WINS) |
| 207403 / 207416 / 207428 | 1 each | total −$1.15 | 0.01–0.08 | various | Breakeven-clip clips (≈$0) |

**Take-away**: G5048 alone = 29.6% of total run P&L wiped (would be **+$7,296** without it). All other losses combined are ~$465, which is normal scalping noise easily covered by hundreds of small wins.

---

## Gate Breakdown (Q3) — full SKIP counts

| gate_reason | Count | Category |
|---|---|---|
| no_setup | 3,964 | structural (no BB pattern) |
| session_off | 3,094 | session filter (NY hours) |
| entry_quality_atr_ext | 74 | post-setup ATR filter |
| rr_too_low | 51 | R:R guard |
| entry_quality_breakout_failed_samebar | 44 | Fix B same-bar block |
| entry_quality_rsi_sell_floor | 27 | RSI < 33 SELL block |
| entry_quality_direction | 22 | M5 directional bars |
| entry_quality_rsi_buy_ceil | 14 | RSI > 70 BUY block |
| entry_quality_body | 11 | body ratio |
| entry_quality_breakout_cooldown | 10 | same-dir cooldown 900s |
| entry_quality_adx_min_sell | 10 | ADX < min SELL |
| entry_quality_rsi_rising_sell | 9 | RSI rising during SELL setup |
| entry_quality_adx_spike_sell | 8 | ADX spike SELL block |
| entry_quality_psar_misalign_buy | 5 | PSAR above BUY |
| entry_quality_rsi_sell_adx_floor | 3 | stricter RSI floor at weak ADX |
| entry_quality_h1_di_sell | 3 | H1 +DI/−DI SELL block |
| entry_quality_breakout_failed | 3 | failed-breakout pullback |
| entry_quality_adx_extreme_sell | 3 | ADX extreme |
| entry_quality_psar_misalign_sell | 2 | PSAR below SELL |
| warmup_tester_m5_rollovers | 2 | warmup |
| entry_quality_m30_not_bearish | 1 | M30 trend confirm |
| entry_quality_h1_di_buy | 1 | H1 +DI/−DI BUY block |

Mandatory housekeeping (session start): **dead env vars PASS, lowercase leaks PASS, gate legend coverage PASS** (39 emitted gates all map to `gate_legend.json`).

---

## Q9 — Gate precision (run-end)

Indicator-bearing gates only (`rsi>0` and `adx>0` at SKIP time). "Correct" = price moved ≥0.5 pts in the blocked direction within 900s; "missed" = price moved against (i.e. the entry would have been good).

| Gate | Total | Correct | Missed | Precision | Verdict |
|---|---|---|---|---|---|
| entry_quality_breakout_cooldown | 10 | 6 | 4 | **60%** | ✓ keep |
| entry_quality_breakout_failed_samebar | 44 | 22 | 22 | 50% | ✓ keep — prevents same-bar wick-fakes (structural) |
| entry_quality_rsi_sell_floor | 26 | 12 | 14 | 46% | loosen (was useful in Run 9 RSI<30 cases) |
| entry_quality_rsi_buy_ceil | 14 | 6 | 8 | 43% | loosen — too tight on trend moves |
| rr_too_low | 51 | 21 | 30 | 41% | review — was 60% in Run 9 |
| entry_quality_psar_misalign_buy | 5 | 2 | 3 | 40% | borderline — keep for now |
| entry_quality_atr_ext | 74 | 29 | 45 | 39% | **loosen** — 45 missed wins on highest-volume gate |
| entry_quality_adx_spike_sell | 8 | 3 | 5 | 38% | loosen |
| entry_quality_rsi_sell_adx_floor | 3 | 1 | 2 | 33% | small sample |
| entry_quality_breakout_failed | 3 | 1 | 2 | 33% | small sample |
| entry_quality_adx_extreme_sell | 3 | 1 | 2 | 33% | small sample |
| entry_quality_h1_di_sell | 3 | 1 | 2 | 33% | small sample |
| entry_quality_adx_min_sell | 10 | 3 | 7 | **30%** | **loosen** — over-filtering SELLs |
| entry_quality_rsi_rising_sell | 9 | 2 | 7 | **22%** | **loosen / disable** |
| entry_quality_psar_misalign_sell | 2 | 0 | 2 | 0% | small sample but 0% — verify |
| entry_quality_h1_di_buy | 1 | 1 | 0 | 100% | sample of 1 |
| entry_quality_m30_not_bearish | 1 | 1 | 0 | 100% | sample of 1 |

> **Caveat**: precision uses 900s drift, not full TP/SL geometry. "Missed win" means price drifted favorably, not that an actual trade would have profited after spread + SL. Treat as directional signal, not as P&L estimate.

---

## Losses — Price Movement Analysis (Q6b)

| Group | Magic | Profit | Entry | Direction | SL | Pattern |
|---|---|---|---|---|---|---|
| **G5048** | 207449 | **−$1,666.32** | 4822.65 | BUY | 4806.65 (−16/−3.2×ATR) | **Direction failure** — never positive; −0.85 at first tick after entry, −8.6 at 16:50, −18.8 at 16:52 (post-SL), trough −30.2 at 17:05. Multi-day rollover invisible to local gates. |
| G5037–G5039 (Apr 15 14:46) | 207438/9/40 | −$140.02 | 4802.7–4803.4 | SELL | +6.4–6.9 (+1.5×ATR) | **SL-hunt / direction wrong** — three SELLs into a continuing afternoon bounce; all SL'd within seconds of each other at +1.5×ATR (minimum-viable SL). |
| G5041 (Apr 15 16:35) | 207442 | −$74.66 | 4819.35 | SELL | +7.0 (+1.5×ATR) | Same upward push that triggered G5042 BUY 15 min later. |
| G5042 (Apr 15 16:50) | 207443 | −$39.56 net (group +$0.34) | 4825.14 | BUY | (runner) | **Held-too-long** — TP1/TP2 partials banked, runner SL hit at 18:05 after rollover. |
| G5051 (Apr 20 10:10) | 207452 | −$70.96 | 4796.04 | SELL | +7.0 (+1.5×ATR) | SL-hunt / direction wrong — bounce-fade SELL stopped on continuation. |
| Cascade slot SLs (227xxx) | various | total ≈ −$160 | various | mixed | Normal cascade-leg stop-outs at minimum viable 1.5×ATR. Offset by ~$340 in cascade-leg wins (227470, 227472, 227473, 227474, 227476, 227478). |

### G5048 detailed trajectory (the disaster)

Entry 16:35:00 BUY 4822.65 (ATR=5.0, RSI=58.4, ADX=26.9):

| Sim time | Price | Δ from entry | Note |
|---|---|---|---|
| 16:35:00 | 4822.65 | 0.00 | TAKEN, h1_trend=+0.75, PSAR=below, all local gates passed |
| 16:40:02 | 4821.16 | −1.49 | Never positive |
| 16:45:00 | 4816.34 | −6.31 | 1.26×ATR adverse |
| 16:50:00 | 4814.06 | −8.59 | 1.72×ATR adverse |
| **16:51:48** | **4806.55** | **−16.10** | **SL hit (3.2×ATR — widened breakout SL did its job)** |
| 16:55:00 | 4794.47 | −28.18 | Continued falling after SL |
| 17:05:00 | 4792.44 | −30.21 | Trough 6.04×ATR adverse |
| 17:30:00 | 4799.23 | −23.42 | Still red 55 minutes later |

**Why no gate caught it**:
- M5/M15 local indicators looked fine
- H1 trend +0.75 (still mildly bull)
- PSAR below price (still bullish)
- BB_BREAKOUT setup valid
- RSI 58.4 (mid-range, no exhaustion signal)

But Apr 14 daily close was 4841 → Apr 16 mid-day 4810 = **−31 pts over 2 days = daily SMA rolling bearish**. **Zero gates in the v2.7.22 stack see multi-day rollover.**

---

## Recommended Parameter Changes — More Trades

**Context**: 7,444 signals evaluated, 83 TAKEN (1.1% take rate). Top 5 SKIP gates account for 7,247 (97.5%) of all blocks. Most are structural (`no_setup`, `session_off`); indicator-bearing blocks total ~290 and Q9 precision shows several over-filtering.

### Current blocking gates → parameters

| Gate | Hits | Q9 prec | Config key | Current | Conservative | Aggressive |
|------|------|---------|------------|---------|--------------|------------|
| `entry_quality_atr_ext` | 74 | 39% | `breakout.atr_ext_min_mult` / `bounce.atr_ext_min_mult` | (varies) | ↓ 0.05×ATR | ↓ 0.1×ATR |
| `rr_too_low` | 51 | 41% | `safety.min_rr` | 1.5 | 1.4 | 1.3 |
| `entry_quality_rsi_sell_floor` | 27 (Q9: 26) | 46% | `bb_breakout.rsi_sell_floor` + `bb_bounce.rsi_sell_floor` | 33 | 28 | 25 |
| `entry_quality_direction` | 22 | n/a (RSI=0) | `safety.min_directional_bars` | 2 | 1 | 1 |
| `entry_quality_rsi_buy_ceil` | 14 | 43% | `bb_breakout.rsi_buy_ceil` + `bb_bounce.rsi_buy_ceil` | 70 | 74 | 77 |
| `entry_quality_rsi_rising_sell` | 9 | **22%** | (likely `safety.rsi_rising_sell_enabled` or threshold) | on | review/disable for SELLs | disable |
| `entry_quality_adx_min_sell` | 10 | 30% | `bb_breakout.adx_min_sell` | 20 | 18 | 16 |
| `entry_quality_body` | 11 | n/a (RSI=0) | `safety.min_body_ratio` | 0.40 | 0.30 | 0.25 |

### Hidden filters to check
- `bb_breakout.require_macd_buy/sell` — if non-default, MACD failures hide in `no_setup`. Verify before assuming the 3,964 `no_setup` blocks are all genuine.
- NY session: 0 TAKEN despite 3,094 `session_off` SKIPs. Check `session_ny_buy_cutoff_utc` / `session_ny_sell_cutoff_utc` — half the day is unused.

### Apply order
1. RSI ceiling/floor loosening (lowest risk, Q9 shows these over-filter)
2. `rsi_rising_sell` review (22% precision is the worst non-trivial gate)
3. `atr_ext_min_mult` loosen (highest-volume gate)
4. `min_rr` 1.5 → 1.4 (modest, helps RR borderline trades)
5. Check NY-session block last

> Config goes via `.env` → `make scalper-env-sync && make forge-compile`.

> ⚠ **More important than parameter loosening**: the **v2.7.27 release (already operator-approved)** addresses the actual run-defining loss. G5048 passed every gate above with ample headroom — no amount of loosening would have made it better, and no realistic tightening of these gates would have caught it.

---

## v2.7.27 — Approved Structural Fixes (the real lever)

Per prior session (`/tmp/history.txt`, ending with operator "yes"), v2.7.27 was greenlit but blocked at handoff by an API rate limit. Bringing it forward here as the primary follow-up action:

### Filter 1 — D1 SMA-slope bias gate (PRIMARY)
- `iMA(D1, 20)` minus 3-day-ago → daily_slope (pts/3d)
- Threshold = `0.5 × iATR(D1, 14)`
- Block BUY when slope < −thresh; block SELL when slope > +thresh
- New gates: `entry_quality_daily_bear_block_buy`, `entry_quality_daily_bull_block_sell`
- **G5048 simulation**: Apr 14→16 slope ≈ −15 pts/day vs threshold −12.5 → block BUY → **−$1,666 prevented**

### Filter 2 — Intraday cumulative-move flip
- `daily_move = D1 close_now − D1 open`; track was_bull/was_bear across ticks
- Hysteresis 0.3×daily_ATR before flagging flip
- Covers Apr 15 14:46 cluster (afternoon bull→bear flip)

### Filter 3 — Pending-order cancel on flip
- Canonical `OrdersTotal()-1 → 0` iterate-down loop (MQL5 forum 377826)
- Cancel only PENDING types within our magic range (includes cascade SELL_STOP_CONT/BUY_LIMIT_RECOV)

### Extended TP4/TP5 ladder
- TP3 → TP4 (4.0×ATR, gated by `tp4_min_adx=25` + TRENDING regime)
- TP4 → TP5 (5.5×ATR, gated by `tp5_min_adx=30`)
- Each milestone ratchets SL up to prior milestone
- RANGE regime stops at TP3 (chop protection)
- **Apr 15 G5040 simulation**: dump moved 53 pts after TP3; T4 and T5 would have captured an additional +$15–25 per runner leg

### 12 new config keys
```
FORGE_DAILY_DIRECTION_GATE_ENABLED=1
FORGE_DAILY_SMA_PERIOD=20
FORGE_DAILY_SMA_LOOKBACK_DAYS=3
FORGE_DAILY_SLOPE_BLOCK_ATR=0.5
FORGE_DAILY_MOVE_BLOCK_ATR=0.5
FORGE_DAILY_MOVE_FLIP_HYSTERESIS=0.3
FORGE_DAILY_CANCEL_PENDING_ON_FLIP=1
FORGE_DAILY_CANCEL_INCLUDES_CASCADE=1
FORGE_BREAKOUT_TP4_STAGING_ENABLED=1
FORGE_BREAKOUT_TP4_MIN_ADX=25
FORGE_BREAKOUT_TP5_STAGING_ENABLED=1
FORGE_BREAKOUT_TP5_MIN_ADX=30
```
(plus existing `breakout_tp4_atr_mult=4.0`, new `breakout_tp5_atr_mult=5.5`)

### Pending todos at rate-limit cutoff
- v2.7.27a — Daily Direction Gate struct + globals + parse
- v2.7.27b — Daily bias compute + entry-chain integration

### Status of v2.7.26 (PSAR for BB_BOUNCE)
Source `VERSION` file currently reads `2.7.26`, but the run-3 EA was `2.7.22`. v2.7.26 is **compiled-or-not status unclear** — operator should `make forge-compile` and confirm the `.ex5` matches `VERSION` before the next backtest (per the `feedback_compile_before_commit` rule).

---

## Observations & Anomalies

1. **NY session never traded** — 0 TAKEN despite ~3K `session_off` blocks. Either the cutoff is overly restrictive or NY conditions never aligned for the entire 37 days. Worth a targeted query of NY-hour signal counts post-cutoff.
2. **Cascade leg quality is excellent** — 12 winning 227xxx magics vs 14 small-loss 227xxx magics, net positive. The slot[2]/slot[3]/slot[4] ladder is paying for itself. Don't disable it.
3. **Hour 13 is the workhorse** — +$1,081 / 143 events / 99.3% WR. Best London-mid-session bucket. Reflects M5 reactive momentum aligning with H1 trend.
4. **The 217 trades on magic 202401** are base-magic final closes (cleanup events when group flattens). Not separate setups — they ride on the 83 TAKEN groups.
5. **Single-loss dependence** — net P&L is +$5,630 with G5048; without G5048 it would be +$7,296. The system is robust except for the daily-direction blind spot, which is exactly what v2.7.27 Filter 1 targets.

---

## Session Log

| Local | Sim time | Event |
|-------|----------|-------|
| 2026-05-11 04:35 | Apr 1 07:00 | Run 17 baseline detected: wall_time=550109260, FORGE v2.7.22, sim_start 2026-04-01. aurum_run_id=17. 73 signals (pre-session), 0 TAKEN. |
| 2026-05-11 06:47 | May 7 23:55 | Run ended (final source DB write). 7,444 signals / 83 TAKEN / 868 trades / +$5,630.29 / 93.3% WR. |
| 2026-05-11 08:30 | (review) | **Post-run review completed**. Identified G5048 as catastrophic outlier (−$1,666 on direction failure). Q9 precision audit run. v2.7.27 plan re-confirmed (operator approval intact from prior session). Doc finalized to **Status: COMPLETE**. |
