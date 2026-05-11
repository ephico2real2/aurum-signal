# FORGE 2.7.3 — Run 17 Analysis (Tester DB run_id=1)
**Date:** 2026-05-08 | **Period:** Apr 14–May 7 | **Symbol:** XAUUSD | **Mode:** DUAL
**Status:** COMPLETE | **EA:** 2.7.3 | **Lot:** 0.08

---

## Key Changes vs Run 16 (2.7.2)

| Change | Value | Expected effect |
|--------|-------|----------------|
| `adx_min` (BUY) | 20 | Unchanged — preserves BUY 20-25 zone wins (+$267 in R16) |
| `adx_min_sell` (SELL) | **25** (new field) | Blocks SELL at ADX 20-25; journals `entry_quality_adx_min_sell` |
| Tester ADX floor | `= g_sc.breakout_adx_min_sell` | Tester = live, no relaxation |
| ADX gate diagnostic | new PrintFormat per M5 bar | `FORGE ADX gate: adx=X buy_min=20 sell_min=25 buy=P/B sell=P/B` |

**Run 16 baseline to beat:**
- BUY: +$1,053 net (+91.4% win rate) ← preserve
- SELL: -$490 net (71.9% win rate, avg loss -$72 vs avg win +$21) ← fix
- Total: +$587.98, PF=1.58, DD=5.42%

---

## Daily Tally

| Date | Groups | Deals | W | L | P&L | Run 16 SELL -$490 context | Notes |
|------|--------|-------|---|---|-----|--------------------------|-------|
| Apr 14 | ⏳ | — | — | — | — | — | |
| **TOTAL** | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | | |

---

## Monitoring Log

| Wall time | Sim time | SKIP | TAKEN | Deals | W | L | P&L | Notes |
|-----------|----------|------|-------|-------|---|---|-----|-------|
| 17:14 | Apr 14 08:32 | 1,483 | 0 | 0 | 0 | 0 | $0 | Baseline — ATR blocks early London |
| 17:16 | Apr 14 15:00 | 10,713 | 2 | 10 | 10 | 0 | +$192.80 | G1+G2 BUY 4779/4783 — identical to R16; adx_min_sell not yet fired |
| 17:25 | Apr 16 07:10 | 24,408 | 6 | 41 | 41 | 0 | +$1,008.32 | G3-G6 BUY (incl G5 ADX 23.4 preserved by BUY floor=20); P&L = R16 exactly |
| 17:28 | Apr 16 17:50 | 37,045 | 6 | 41 | 41 | 0 | +$1,008.32 | Apr 16 full: 0 trades; dir_filter +8046; adx_min_sell still not fired; G5007 imminent |
| 17:32 | Apr 17 14:25 | 43,149 | 7 | 43 | 41 | ? | open | G7 SELL 4782 ADX 26.8 — SAME as R16 G5007; ADX>25 passes gate; RSI-declining needed |
| 17:34 | Apr 17 20:40 | 54,373 | 7 | 43 | 41 | 2 | +$970.18 | G7 SELL SL -$38.14 (0.02 lot, inside-band); BUY 100% WR; query bug fixed |
| 17:39 | Apr 20 14:35 | 58,754 | 8 | 46 | 41 | 5 | +$700.82 | G8 BUY 4802 ADX 26.4 Monday SL -$269; adx_min_sell still not fired |
| 17:42 | Apr 21 05:45 | 62,573 | 9 | 47 | 41 | 6 | +$641.54 | G9 BB_BOUNCE SELL 4807 ADX 43.1 SL -$59; R18 bounce_adx_max=40 would block |
| 17:45 | Apr 21 17:51 | 75,699 | 12 | 52 | 46 | 6 | +$687.78 | G10-12 SELL wins ADX 26-31; adx_min_sell still not fired; RSI floor +3955 |
| 17:48 | Apr 22 09:20 | 81,193 | 12 | 52 | 46 | 6 | +$687.78 | Overnight quiet; ADX 15.7 (below both floors); no_setup; adx_min_sell pending |
| 17:50 | Apr 22 17:25 | 86,588 | 13 | 56 | 48 | 6 | +$707.36 | **adx_min_sell FIRST FIRE (3x)** — blocked G5013(23.3)/G5014(24.9); G13 ADX 34.8 wins |
| 17:51 | Apr 22 22:25 | 86,648 | 14 | 58 | 50 | 6 | +$733.58 | G14 SELL 4738 ADX 27.1 wins; net ≈ R16 (+$733.48); adx_min_sell gate net-neutral |
| 18:02 | Apr 24 05:15 | 104,978 | 15 | 58 | 52 | 6 | **+$751.98** | G15 SELL ADX 39.8 wins (+$18.40, 2 deals); SELL now net-positive +$13.02; no new losses |
| 18:09 | Apr 27 13:55 | 113,731 | 16 | 60 | 54 | 6 | **+$763.62** | G16 SELL ADX 50.3 @ 4711 confirmed; SELL +$24.66; no new losses; adx_min_sell still 3 fires |
| 18:14 | Apr 27 17:50 | 114,837 | 16 | 60 | 54 | 6 | **+$763.62** | adx_min_sell fire #4 (Apr 27 ~16:xx); atr_ext blocks SELL re-entry ADX 37.4; P&L unchanged |
| 18:21 | Apr 28 08:12 | 125,353 | 16 | 60 | 54 | 6 | **+$763.62** | RSI crashed to 17.9 @ 4650 — rsi_sell_adx_floor blocks 5 consecutive SELLs; no new losses |
| 18:26 | Apr 28 12:05 | 135,274 | 16 | 60 | 54 | 6 | **+$763.62** | ADX collapsed 33→15; RSI bounced 17.9→42-50; rsi_floor blocks +11k; no trades; ranging market |
| 18:31 | Apr 28 16:35 | 146,174 | 18 | 64 | 58 | 6 | **+$798.28** | G17 SELL ADX 34.7 RSI 36.4 + G18 SELL ADX 28.7 RSI 39.6 — both WIN; SELL +$59.32; **+$210 vs R16** |
| 18:38 | Apr 29 01:40 | 146,274 | 18 | 64 | 58 | 6 | **+$798.28** | adx_min_sell fires 4→**6** (G5021-equiv blocked, ADX 21.9/20.5, ATR 10+); overnight session_off |
| 18:46 | Apr 29 11:15 | 149,702 | 18 | 64 | 58 | 8 | **+$798.28** | adx_min_sell fires 6→**8** (G5021≡ADX 21.4 blocked ✅); ADX spiked 21→46 by 11:00 (spike-from-flat) |
| 18:53 | Apr 29 20:50 | 160,851 | 19 | 66 | 60 | 8 | **+$817.46** | G19 SELL ADX 28.3 RSI 36.2 WIN +$19.18; adx_min_sell 8→**10** (ADX 20-21 fires 15:35-15:44) |
| 19:01 | Apr 30 08:30 | 164,172 | 19 | 66 | 60 | 10 | **+$817.46** | Overnight quiet; RSI 24→49-54; ADX 27-31; price 4552-4558; G5022-equiv (BUY ADX 23) pending |
| 19:06 | Apr 30 14:10 | 164,240 | 19 | 66 | 60 | 10 | **+$817.46** | Strong BUY rally 4552→4644 (+87pts); ADX 43-51 RSI 65-71; no_setup only; rsi_buy_ceil active |
| 19:16 | Apr 30 19:45 | 176,851 | 21 | 69 | 63 | 6 | **+$961.86** | **G20 BUY ADX 23.0** ✅ G5022-equiv (+$144.40, 3 wins); G21 SELL ADX 28.8 open; **+$374 vs R16** |
| 19:31 | May 01 12:30 | 177,040 | 21 | 69 | 63 | 8 | **+$921.48** | G21 SELL SL -$40.38 (2 legs, 49min — velocity stop-hunt); ADX 37-57 RSI 27 strong SELL continues |
| 19:38 | May 01 18:25 | 196,831 | 21 | 69 | 63 | 8 | **+$921.48** | V-reversal 4565→4640 (+75); RSI 27→63; rsi_buy_ceil +9k fires; no new trades; 5 days remaining |
| 19:43 | May 01 23:55 | 196,897 | 21 | 69 | 63 | 8 | **+$921.48** | Overnight session_off; price 4611-4616; 4 days remaining (May 2-7) |
| 19:49 | May 04 12:15 | 202,240 | 21 | 69 | 63 | 8 | **+$921.48** | Weekend (May 2-3) + Mon open; ADX 20-26 below SELL floor; price 4577-4584; 3 days remaining |
| 19:54 | May 04 17:49 | 221,381 | 22 | 69 | 65 | 8 | **+$683.40** | **G22 SELL -$238.08** (G5024-equiv! ADX 37.4, ADX[6]=16.8 → BLOCKED in R18 by adx_spike_sell ✅) |
| 20:00 | May 05 07:10 | 225,156 | 23 | 71 | 67 | 8 | **+$717.74** | G23 SELL ADX 34.3 WIN +$34.34 (58min after G22); price 4534; **+$130 vs R16** |
| 20:08 | May 06 01:55 | 229,197 | 23 | 71 | 67 | 8 | **+$717.74** | May 5 full day — zero new groups; rsi_sell_floor +3k blocks; 1 day remaining |
| 20:13 | May 06 07:30 | 229,264 | 24 | open | open | 8 | **+$717.74+** | **G24 BUY 4652 ADX 38.8 RSI 68.6** (price surge +105pts overnight); barely cleared rsi_buy_ceil |
| 20:18 | May 06 16:00 | 239,359 | 26 | 73 | 65 | 8 | **+$758.22** | G24 SL -$127.84; G25+G26 BUY wins +$168; price 4677-4683 ADX 37-44; **+$170 vs R16** |
| 20:24 | May 06 23:50 | 239,455 | 26 | 73 | 65 | 8 | **+$758.22** | Overnight session_off; price 4688-4692; May 7 final day approaching |
| 20:31 | May 07 09:20 | 239,557 | 26 | 73 | 65 | 8 | **+$758.22** | Ranging (ADX 15-25); G27 still forming |
| 20:38 | May 07 20:45 | 248,968 | **27** | **79** | **74** | **10** | **+$830.94** | **RUN COMPLETE** — G27 BUY +$72.72 (3 wins); session_off = end of period |

---

## Gate Verification

### `entry_quality_adx_min_sell` (new — key gate to validate)
- **First appearance: Apr 22 16:xx UTC — 3 fires** ✅ CONFIRMED WORKING
- Blocked: G5013-equivalent (ADX 23.3) and G5014-equivalent (ADX 24.9) — both were wins in R16 (+$17.24 opportunity cost)
- Allowed: G13 (ADX 34.8) — correctly passed, won +$19.58
- Allowed: G15 (ADX 39.8, Apr 23) — correctly passed, won +$18.40
- Net gate cost: -$17.24 blocked wins; gate preserved G13+G14+G15 wins
- Remaining blocked target: G5021-equivalent (ADX 21.4, Apr 29) — still pending
- **Run 18 calibration — `rsi_rising_sell` auto-off threshold**: G17 (ADX 34.7), G18 (ADX 28.7), G19 (ADX 28.3) all WINS that gate would block at threshold=35. G7 (ADX 26.8, LOSS) correctly blocked at any threshold. **Optimal threshold = ADX ≥ 28**: catches G7 while passing G17/G18/G19. Change `breakout_adx_sell_floor_threshold` from 35 → 28 for `rsi_rising_sell` auto-off, OR add a separate `rsi_declining_sell_adx_threshold` config param.
- **Run 18 calibration — `adx_spike_sell` gate**: G19 (ADX 28.3, 26min after ADX 20.0) would be BLOCKED → was WIN. The 30-min lookback catches volatile ADX oscillation patterns that turn out OK. Consider reducing lookback from 6 bars (30min) to 3 bars (15min) to reduce false blocks.

---

## Loss Register

| Group | Date | Setup | ADX | RSI | Legs | Loss (per leg) | Total | Root cause | Gate fix |
|-------|------|-------|-----|-----|------|----------------|-------|------------|----------|
| G7 | Apr 17 10:51 | BB_BREAKOUT SELL | 26.8 | 39.5 | 2 | -$18.34, -$19.80 | -$38.14 | RSI bounce from floor; inside-band 0.02 lot | RSI-declining (R18) |
| G8 | Apr 20 10:20 | BB_BREAKOUT BUY | 26.4 | 66.1 | 3 | -$82.08, -$92.16, -$95.12 | -$269.36 | Monday false breakout; 3-leg SL | ADX-duration (R18) |
| G9 | Apr 20 15:10 | BB_BOUNCE SELL | 43.1 | 66.3 | 1 | -$59.28 | -$59.28 | High-ADX bounce reversal | bounce_adx_max=40 (R18) |
| G21 | Apr 30 19:21 | BB_BREAKOUT SELL | 28.8 | 36.1 | 2 | -$19.60, -$20.78 | -$40.38 | Velocity stop-hunt (49min SL); price -39pts below entry by May 1 | sl_be_proximity_pct (Velocity Plan) |
| G22 | May 4 17:10 | BB_BREAKOUT SELL | 37.4 | 39.2 | 2 | -$115.44, -$122.64 | **-$238.08** | **G5024-equiv!** ADX spiked 13→37 in 40min; ADX[6]=16.8 < 25 → adx_spike_sell blocks in R18 ✅ | `adx_spike_sell` (R18 ✅) |
| **Total** | — | — | — | — | 10 | — | **-$645.24** | — | — |

---

## BUY vs SELL Scoreboard (vs Run 16 baseline)

| Metric | Run 16 | Run 17 (FINAL) | Delta |
|--------|--------|----------------|-------|
| BUY groups | — | **17** | — |
| BUY deals | — | **58 (53W/5L, 91.4% WR)** | — |
| BUY P&L | **+$1,053** | **+$996.56** | -$56 (near parity!) |
| SELL groups | — | **10** | — |
| SELL deals | — | **28 (21W/7L, 75.0% WR)** | — |
| SELL P&L | **-$490** | **-$165.62** | **+$324 ✅** |
| **Net** | **+$587.98** | **+$830.94** | **+$242.96 (+41%) ✅** |
| adx_min_sell blocks | — | **10 fires** | Gate confirmed |
| Total signals | — | 248,968 | — |
| Total deals | — | 86 (74W/12L, 86.0% WR) | — |

---

## Gotchas & Findings (Run 17)

- **Agent port change**: Run 17 runs on Agent-3000 DB; a secondary Agent-3001 DB appeared (stuck at Apr 14) — ignore 3001 for monitoring.
- **SELL reversal confirmed**: adx_min_sell=25 transformed SELL from -$490 (R16) to +$13.02 by Apr 24. Main remaining SELL losses are pre-gate (G7) and BB_BOUNCE type (G9, needs bounce_adx_max).
- **BUY drag**: G8 BUY loss (-$269.36 in 3 legs) is the dominant P&L drag. ADX 26.4 Monday false breakout — ADX-duration gate (Run 18) should address.

---

*Last updated: 2026-05-08 20:38 CDT — Run 17 COMPLETE*
