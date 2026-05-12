# FORGE 2.7.5 — Run 19 Analysis (Tester DB Agent-3000, run_id=2)
**Date:** 2026-05-08 | **Period:** Apr 14–May 7 | **Symbol:** XAUUSD | **Mode:** DUAL
**Status:** COMPLETE ✅ | **EA:** 2.7.5 | **Lot:** 0.08

---

## Key Changes vs Run 17 (2.7.3)

| Gate | Config | Targets | Status |
|------|--------|---------|--------|
| `adx_min_sell=25` | Inherited from 2.7.3 | G5013/G5014/G5021-class SELL at weak ADX | ✅ Live |
| `adx_spike_sell` (6-bar lookback) | `adx_min_sell_lookback_bars: 6` | G22/G5024 spike-from-flat (-$238) | ✅ Live |
| `rsi_rising_sell` | `require_rsi_declining_sell: 1`, auto-off ADX≥**28** | G7 RSI bounce (-$38) | ✅ Live (threshold 28, not 35) |
| `bounce_adx_max=40` | `adx_max: 40` in bb_bounce | G9 high-ADX bounce (-$59) | ✅ Live |
| `h1_di_buy` (DI+/DI- gate) | `require_h1_di_buy: 1`, auto-off ADX≥28 | **G8 Monday false breakout (-$269)** | ✅ Live (new in 2.7.5) |
| `rsi_decl_sell_adx_threshold: 28` | Separate from two-tier RSI floor (35) | Preserves G17/G18/G19-class wins | ✅ Fixed |
| `tester_allowed_sessions: "LONDON,NY"` | Fixed from "NEW_YORK" → "NY" | Session filter now correct | ✅ Fixed |
| Session-start log | `FORGE SESSION START: hour=X adx=...` | Overnight context visibility | ✅ Live |

**Run 17 baseline to beat:**
- BUY: +$923.84 net (91.4% WR) — G8 (-$269) was main drag
- SELL: -$165.62 net (75.0% WR)
- Total: +$830.94, 26 groups, 86 deals

**Run 19 expected improvement:**
- G8-class blocked by `h1_di_buy` → BUY should approach R16 baseline (+$1,053)
- G7/G22-class blocked → SELL should further improve beyond Run 17
- G9-class blocked by `bounce_adx_max=40` (same as Run 18 would have had)

---

## Monitoring Log

| Wall time | Sim time | SKIP | TAKEN | Deals | W | L | P&L | Notes |
|-----------|----------|------|-------|-------|---|---|-----|-------|
| 20:46 | Apr 14 12:00 | 6,701 | 2 | 10 | 10 | 0 | +$192.80 | G1+G2 BUY identical to R17; no new gates fired yet |
| 20:52 | Apr 14 20:55 | 14,241 | 4 | 27 | 27 | 0 | **+$716.00** | G3+G4 BUY wins; 100% WR; session_off overnight; no gate fires yet |
| 20:57 | Apr 15 12:05 | 19,229 | 4 | 27 | 27 | 0 | **+$716.00** | Quiet Apr 15 morning; body gate +4.7k; ADX 20-27 ranging; G5/G6 pending ~16:30 |
| 21:02 | Apr 15 21:50 | 24,308 | 6 | 41 | 41 | 0 | **+$1,008.32** | **G5 ADX 23.4 PASSES h1_di_buy ✅** (H1 DI+ dominant); G6 ADX 32.8; = R17 identical |
| 21:07 | Apr 16 12:30 | 27,392 | 6 | 41 | 41 | 0 | **+$1,008.32** | Apr 16 quiet day — zero trades (same as R17); no gate fires; G7-equiv SELL pending Apr 17 |
| 21:11 | Apr 16 22:30 | 37,101 | 6 | 41 | 41 | 0 | **+$1,008.32** | Apr 16 full day complete; dir_filter +6.6k; session_off; G7-equiv SELL ~12 hrs away |
| 21:16 | Apr 17 14:10 | 41,273 | 6 | 41 | 41 | 0 | **+$1,008.32** | **rsi_rising_sell FIRES 1x ✅ G7-equiv BLOCKED** (+$38 saved vs R17); no new trades |
| 21:21 | Apr 17 23:40 | 52,536 | 6 | 41 | 41 | 0 | **+$1,008.32** | BUY rally 4787→4851 (+64pts); rsi_buy_ceil +11k blocks re-entries; weekend approaching |
| 21:26 | Apr 20 14:15 | 56,870 | 6 | 41 | 41 | 0 | **+$1,008.32** | **h1_di_buy FIRES 1x ✅ G8-equiv BLOCKED** (+$269 saved vs R17); 100% WR preserved |
| 21:31 | Apr 20 23:55 | 58,056 | 6 | 41 | 41 | 0 | **+$1,008.32** | **G9-equiv BLOCKED** (no_setup at ADX 43.1, Apr 20 15:10 ✅); +$366 total saved; session_off |
| 21:37 | Apr 21 22:45 | 76,657 | 7 | 43 | 43 | 0 | **+$1,026.44** | G7(R19) SELL WIN +$18; rsi_rising_sell #2 (G10-equiv blocked); **adx_spike_sell FIRST FIRE ✅** |
| 21:41 | Apr 22 17:05 | 80,981 | 7 | 43 | 43 | 0 | **+$1,026.44** | adx_min_sell +3 (Apr 22 ADX 23-24 pattern); adx_spike_sell #2; rsi_rising_sell #3; all gates live |
| 21:46 | Apr 23 09:00 | 83,792 | 7 | 43 | 43 | 0 | **+$1,026.44** | adx_spike_sell #3 (likely G13-equiv ADX 34.8 WIN ~+$20 blocked — opportunity cost); ADX ranging |
| 21:51 | Apr 23 19:00 | 99,302 | 8 | 45 | 45 | 0 | **+$1,044.84** | G8(R19)=G15(R17) SELL ADX 39.8 WIN +$18.40; all gates silent — clean pass; SELL 4W/0L |
| 21:56 | Apr 24 09:15 | 103,774 | 8 | 45 | 45 | 0 | **+$1,044.84** | Quiet Apr 24 London AM; ADX 35-43 recovering; no BB setups yet; G21-equiv (~May 1) ahead |
| 22:01 | Apr 24 23:55 | 106,868 | 8 | 45 | 45 | 0 | **+$1,044.84** | Apr 24 full day — zero trades; session_off overnight; price 4705-4708 stable |
| 22:06 | Apr 27 17:59 | 111,321 | 9 | 47 | 47 | 0 | **+$1,056.48** | G9(R19)=G16(R17) SELL ADX 50.3 WIN +$11.64; adx_min_sell #4; RSI floor blocks at 17:59 |
| 22:10 | Apr 28 08:48 | 127,577 | 9 | 47 | 47 | 0 | **+$1,056.48** | RSI crashed 4677→4628 (-49pts); RSI 20.8 (same Apr 28 crash as R17 17.9); rsi_floor blocks |
| 22:15 | Apr 28 17:25 | 139,319 | 10 | 49 | 49 | 0 | **+$1,071.48** | G10(R19) SELL ADX 28.7 WIN +$15; **adx_spike_sell +4 (3→7)** volatile crash period; -130pts |
| 22:19 | Apr 29 08:30 | 142,801 | 10 | 49 | 49 | 0 | **+$1,071.48** | adx_min_sell #6 (G5021-equiv); price stabilizing 4600; ADX 25-42 recovering; G21-equiv ~Apr 30 |
| 22:24 | Apr 29 18:05 | 151,595 | 10 | 49 | 49 | 0 | **+$1,071.48** | **adx_min_sell 6→10** (all Apr 29 09:18/09:20/15:35/15:44 blocks ✅); price -60 to 4539 |
| T22 | Apr 30 12:10 | 158,544 | 10 | 49 | 49 | 0 | **+$1,071.48** | No new trades; ADX 38-42 high (no_setup dominant); price 4616-4620; G21-equiv SELL ~19:21 ahead |
| T23 | Apr 30 19:00 | 166,202 | 11 | 52 | 52 | 0 | **+$1,215.88** | **G11(R19) BUY BB_BREAKOUT +$144.40** (Apr 30 16:07, ADX 23.0, RSI 54.6, 4636→TP ✅); G21-equiv SELL imminent ~19:21 |
| T24 | May 1 10:20 | 172,368 | 11 | 52 | 52 | 0 | **+$1,215.88** | **G21-equiv CLEARED — 0 losses!** rsi_sell_adx_floor +1,252 during Apr30 19–May1 window (G21-equiv SELL blocked); adx_spike_sell 8→9 |
| T25 | May 1 18:05 | 192,180 | 11 | 52 | 52 | 0 | **+$1,215.88** | BUY rally: rsi_buy_ceil +9,868 (14.9k→24.8k); dir_filter +6.6k; price 4632-4638; no trades; G22-equiv May 4 17:10 |
| T26 | May 1 23:55 | 192,251 | 11 | 52 | 52 | 0 | **+$1,215.88** | Overnight session_off; only +71 new signals; price 4611-4616; May 2 London open next |
| T27 | May 4 11:20 | 197,583 | 11 | 52 | 52 | 0 | **+$1,215.88** | Weekend gap processed; rsi_sell_adx_floor +5,206 (18k→23k); rsi_rising_sell 3→4; **G22-equiv ~17:10 UTC — 6 hrs ahead!** |
| T28 | May 4 18:55 | 220,376 | 11 | 52 | 52 | 0 | **+$1,215.88** | **🎯 G22-equiv BLOCKED ✅** id=209249 May4 17:10 BB_BREAKOUT SELL ADX=37.4 (spike from 16.8) → `adx_spike_sell` 9→12; **ALL 5 R17 losses BLOCKED; 0 losses total** |
| T29 | May 5 09:20 | 224,365 | 11 | 52 | 52 | 0 | **+$1,215.88** | Monday post-crash; ADX 21-26 ranging; price 4539-4543; no new trades; run ends May 7 (~2 sim days) |
| T30 | May 5 18:55 | 224,480 | 11 | 52 | 52 | 0 | **+$1,215.88** | Very slow tick (+115 signals); ADX 16-30 (no setups); price 4571-4578; May 6-7 remaining |
| T31 | May 6 08:50 | 224,638 | 13 | 52+3W | 55 | **2L** | **+$1,152.44** | **NEW LOSSES**: G13(R19)=G5013 BUY SL -$127.84 (deals 114+115); G12 WIN +$64.40; G14 WIN +$103.92 (race condition — see below) |
| T32 | May 7 01:15 | 234,817 | 14 | 58 | 58 | 2L | **+$1,256.36** | G14 fully settled +$103.92; rsi_buy_ceil +9.9k (May 6 rally 4647→4694); overnight session_off; May 7 trading ahead |
| **T33** | **May 7 23:55** | **244,365** | **15** | **61** | **61** | **2L** | **+$1,329.08** | **RUN COMPLETE** — G15(R19) BUY May7 09:30 4716.79 ADX36 RSI69.9 TP 4720.74 +$72.72; rsi_buy_ceil +9.3k (May7 rally to 4713+) |

---

## New Gate Verification

### `entry_quality_h1_di_buy` (key new gate — blocks G8-class)
- Target: Apr 20 ~10:20 UTC — BUY at ADX 26.4, H1 DI- > DI+
- **Status: ✅ CONFIRMED — 1 fire on Apr 20**
- G8-equivalent Monday BUY blocked — saved -$269.36 vs Run 17
- H1 DI- dominated DI+ on Monday morning after weekend bearish gap (price fell from 4851 → 4789)
- **G5 confirmation Apr 15 16:30**: BUY ADX 23.4 (< 28 threshold) PASSED gate — H1 DI+ > DI- during strong BUY trend ✅

### `entry_quality_adx_spike_sell` (6-bar lookback)
- Target: May 4 ~17:10 UTC — ADX[6]=16.8 spiked to 37.4 (G22-equiv)
- **Status: ✅ CONFIRMED — signal id=209249, May 4 17:10 UTC, BB_BREAKOUT SELL ADX=37.4, price=4555.24**
- G22-equivalent SELL blocked — saved -$238.08 vs Run 17 (largest single loss in R17)
- ADX[6 bars ago]=16.8 → ADX=37.4 is the exact spike-from-flat pattern the gate targets
- Gate fired 3 times in the May 4 window (adx_spike_sell 9→12); total 12 fires across the run

### `entry_quality_rsi_rising_sell` (auto-off ADX≥28)
- Target: Apr 17 ~10:51 UTC — SELL RSI 35.2→39.5 rising
- **Status: ✅ CONFIRMED — 1 fire between Apr 17 07:00–14:10 UTC**
- G7-equivalent SELL blocked — saved -$38.14 vs Run 17
- Gate correctly fired when RSI was rising (bar-over-bar) and ADX was below 28 threshold

### `bounce_adx_max=40`
- Target: Apr 20 ~15:10 UTC — BB_BOUNCE SELL ADX 43.1
- **Status: ✅ CONFIRMED — silently blocked as `no_setup` at Apr 20 15:10**
- Confirmed: signal id=57014, ADX=43.1, RSI=66.3, price=4807.76 — exact match to Run 17 G9 (4807.64/43.1/66.3)
- Gate is a condition check (not a journaled gate_reason) — appears as `no_setup` when ADX > bounce_adx_max
- Note: Add `entry_quality_bounce_adx_max` gate reason to FORGE for better observability in future

---

## Run 19 vs Run 17 Loss Register (Expected)

| Group | R17 Loss | Gate in R19 | Expected R19 |
|-------|----------|-------------|--------------|
| G7 (SELL RSI bounce) | -$38.14 | `rsi_rising_sell` ✅ | BLOCKED |
| G8 (BUY Monday DI-) | **-$269.36** | `h1_di_buy` ✅ | BLOCKED |
| G9 (BB_BOUNCE ADX 43) | -$59.28 | `bounce_adx_max=40` ✅ | BLOCKED |
| G21 (SELL velocity SH) | -$40.38 | ❌ Not yet implemented | **BLOCKED by rsi_sell_adx_floor** (surprise ✅) |
| G22 (SELL spike flat) | **-$238.08** | `adx_spike_sell` ✅ | **BLOCKED ✅ CONFIRMED** (id=209249 May4 17:10) |
| G13/R19 (BUY extended RSI) | N/A (new) | ❌ Not in R17 register | **-$127.84 OCCURRED** (May 6 08:31, BUY ADX 35.4 RSI 67.7 → SL 4647.90) |
| **Total R17 losses** | **-$645.24** | | **$0** — all 5 blocked ✅ |
| **New R19 losses** | N/A | | **-$127.84** (G13/R19 only) |

---

## P&L Scoreboard

| Metric | Run 16 | Run 17 | Run 19 target | **Run 19 FINAL** |
|--------|--------|--------|--------------|---------------|
| BUY entries | — | — | — | **11** (10W/1L group; 2L deals) |
| SELL entries | — | — | — | **4** (4W/0L) |
| BUY P&L | +$1,053 | +$923.84 | ~+$1,100+ | **+$1,265.92** |
| SELL P&L | -$490 | -$165.62 | ~+$50+ | **+$63.16** |
| Total entries | — | 26 | — | **15** |
| Total deals | — | 86 | — | **126 (61W/2L)** |
| Net | +$587.98 | +$830.94 | ~+$1,000+ | **+$1,329.08** |
| vs R17 | — | baseline | +$169 target | **+$498.14 (+59.9%)** |

---

*FINAL — 2026-05-08 CDT | Run complete May 7 23:55 sim | 15 entries, 126 deals, 61W/2L | BUY +$1,265.92 / SELL +$63.16 | **Net +$1,329.08** (+$498 vs R17, +59.9%) | All 5 gates verified ✅ | 1 new loss type: G13 BUY stop-hunt -$127.84*
