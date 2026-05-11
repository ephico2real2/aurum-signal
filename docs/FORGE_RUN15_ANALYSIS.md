# FORGE Run 15 — Tester Analysis

**EA version**: FORGE v2.7.16
**Symbol**: XAUUSD
**Sim period**: 2026-04-01 → (in progress)
**Scalper mode**: DUAL
**Balance**: $10,000
**aurum_run_id**: 15
**wall_time**: 539419001
**source_run_id**: 1
**Magic base**: 202401
**Status**: in progress (sim at **Apr 28 17:15 UTC** — user letting v2.7.16 run to completion before reloading v2.7.21)

---

## What's new in Run 15

| Change | From | To |
|--------|------|-----|
| EA version | v2.7.15 | **v2.7.16** |
| **Sim period start** | Apr 29 (Runs 12-14) | **Apr 1** (28 extra sim days) |
| `sell_stop_cont_sl_atr_mult` (v2.7.16) | (didn't exist) | **3.5** — decoupled cascade SL |
| `staged_initial_legs` | 8 | **10** |
| `gold_native_max_sell_legs` | 8 | **10** |
| `max_num_trades` | 8 | **30** |
| `staged_add_min_favorable_points` | 3 | **5** |
| `session_ny_sell_cutoff_utc` | 18 | 0 (kept from Run 14) |
| `fixed_lot` | 0.08 | **0.25** (active config — but Run 15 in flight using 0.08; restart MT5 to apply) |

**Important**: Run 15 sees `forge_version=2.7.16` in TESTER_RUNS but trades show **lot=0.08**, not 0.25. The EA loaded before the lot push. The new lot will take effect on the NEXT tester start after MT5 reload.

---

## Summary (running)

| Metric | Value |
|--------|-------|
| Total signals | **5,330** |
| TAKEN | **52** (≈45 BB_BREAKOUT, ≈5 BB_BOUNCE, mostly BUY then heavy SELL cluster Apr 23–28) |
| Trades | 597 deals / 447W / **150L** |
| **P&L (running)** | **−$5,632.70** |
| Breakdown | Initial-group magics: −$2,090 · Base magic 202401 (TP1 partial closes): +$1,193 · **Cascade SELL STOP CONT magics (≥220000): −$4,736** |
| **Dominant issue** | **84% of total loss is cascade SL hits** — SELL TP1 fills then cascade arms then market reverses through cascade SL (3.5×ATR). |

---

## TAKEN Groups

| # | Sim Time (UTC) | Group | Setup | Dir | Price | RSI | ADX | M15 | H1 | DIV | lot_f | P&L |
|---|----------------|-------|-------|-----|-------|-----|-----|-----|-----|-----|-------|-----|
| 1 | 2026-04-01 08:40 | G5001 | BB_BREAKOUT | BUY | 4700.47 | 73.3 | 40.1 | 24.9 | +2.152 | NONE | 1.0 | **+$80** |
| 2 | 2026-04-01 08:45 | G5002 | BB_BREAKOUT | BUY | 4702.33 | 74.5 | 44.3 | 26.4 | +2.139 | NONE | 1.0 | **−$400** ❌ |
| 3 | 2026-04-01 09:25 | G5003 | BB_BREAKOUT | BUY | 4705.53 | 63.2 | 33.0 | 26.9 | +2.123 | NONE | 1.0 | **+$58** |
| 4 | 2026-04-02 12:15 | G5004 | BB_BOUNCE | BUY | 4623.24 | 46.5 | 25.8 | 25.3 | +0.342 | NONE | 0.25 | **+$122** |
| 5 | 2026-04-06 10:50 | G5006 | BB_BREAKOUT | BUY | 4672.54 | 63.5 | 31.4 | (n/a) | -0.073 | NONE | 1.0 | **+$125** |
| 6 | 2026-04-06 10:55 | G5007 | BB_BREAKOUT | BUY | 4681.18 | 68.6 | 36.7 | (n/a) | -0.055 | NONE | 1.0 | **+$54** |
| 7 | 2026-04-06 11:00 | G5008 | BB_BREAKOUT | BUY | 4685.11 | 70.8 | 40.9 | (n/a) | +0.010 | NONE | 0.25 (inside-band) | **+$14** |
| 8 | 2026-04-06 11:05 | G5009 | BB_BREAKOUT | BUY | 4687.12 | 68.6 | 45.1 | (n/a) | +0.015 | NONE | 0.25 (inside-band) | **+$15** |
| 9 | 2026-04-07 11:25 | G5010 | BB_BREAKOUT | BUY | 4683.39 | 75.2 | 31.3 | (n/a) | -0.073 | NONE | 1.0 | _open_ |
| 10 | 2026-04-07 11:35 | G5011 | BB_BREAKOUT | BUY | 4683.91 | 70.8 | 36.6 | (n/a) | -0.071 | NONE | 0.25 (inside-band) | _open_ |

---

## P&L by magic (running)

| Magic | P&L | Deals | First trade |
|---|---|---|---|
| 202401 (base) | +$179.34 | 8 | 04-01 08:41 |
| 207402 (G5001) | +$40.40 | 3 | 04-01 08:41 |
| **207403 (G5002)** | **−$400.00** | **5** | **04-01 08:55 — all 5 legs SL** |
| 207404 (G5003) | +$58.32 | 3 | 04-01 09:26 |
| 207405 (G5004) | +$122.46 | 11 | 04-02 13:05 |

---

## Loss Analysis — G5002 (Trend-failure pattern)

**Setup nearly identical to G5001/G5003 winners**:
- Same direction (BUY), same setup (BB_BREAKOUT), same indicator stack
- RSI=74.5 (G5001=73.3, G5003=63.2 — all overbought-ish)
- ADX=44.3 (G5001=40.1, G5003=33.0 — strong trend)
- H1=+2.139 (max bullish)
- Fired 5 minutes after G5001 at slightly higher price

**What killed it**:
- Price **never reached TP1** (= entry + 0.5×ATR = ~4704.43)
- 5 partial-close marker orders at TP1/TP2 levels never filled
- 10 minutes after entry, price reversed and hit SL at 4692.39 (entry − 9.94 pts = −2×ATR)
- 5 runner legs stopped out at full SL distance

**Why G5001 escaped but G5002 didn't**:
- G5001 reached TP1 → BE-move-on-TP1 fired → runner closed at BE+$2 instead of SL−$80
- G5002 never reached TP1 → BE-move never fired → original 2×ATR SL was still active

This is the **"Trend-failure"** pattern from the loss taxonomy:
> *"Peaked at <25% of TP1, reversed immediately. Fix: wrong setup for regime — gate (e.g. adx_max, bounce_lot_factor)"*

Gates that fired correctly on both G5001 AND G5002 — but the difference between them was post-entry market behavior, not pre-entry filter quality. No gate change would have prevented G5002 without also blocking G5001 and G5003.

---

## Critical implication for the lot=0.25 change

Run 15 is using **lot=0.08** (old config — EA loaded before the lot push).

If lot=0.25 had been active for Run 15:

| Loss component | This run (0.08) | At lot=0.25 |
|---|---|---|
| Per-leg loss | −$80 | **−$250** |
| 5-leg G5002 loss | **−$400** | **−$1,250** |
| % of $10K account | 4% | **12.5%** |

**One G5002-class loss at lot=0.25 would erase 3-5 typical Run 13/14 winners.** And Run 15 is finding G5002-class losses on Day 1.

---

## Mandatory Housekeeping Checks (session start)

| Check | Result |
|---|---|
| A. Dead `FORGE_*` env vars | **PASS** |
| A. Lowercase config leaks | **PASS** |
| B. Gate legend coverage | **PASS** |

---

## Recommendation before scaling lot

Hold off on the lot=0.25 deployment until you've seen the full Run 15 result. Apr 1-2 has shown:
- 4 TAKEN, **1 was a clean trend-failure loss**
- Loss/win ratio currently 1:3 by count (1L out of 4 entries)
- At 25% loss rate, average $80 loss × 5 legs cancels ~5 wins

If the Apr 1 → May 7 full period shows ≥10% loss rate from trend-failure patterns, then scaling lot 3.125× compounds the problem. Wait for full data before reloading MT5 with the new lot.

---

## Session Log

| Local | Sim time | Event |
|-------|----------|-------|
| 2026-05-11 00:38 | (Run 15 detected) | wall_time=539419001, FORGE v2.7.16, sim_start 2026-04-01 |
| 2026-05-11 (now) | Apr 2 15:30 | Tick 1: 458 sigs, **4 TAKEN, 1 LOSS (G5002 −$400)**, +$0.52 net. **First losses since Run 11**. Trend-failure pattern. Lot still 0.08 (EA needs MT5 reload for lot=0.25). |
| 2026-05-11 00:46 | Apr 6 07:10 | Tick 2: 632 sigs, **still 4 TAKEN**, +$0.52. Apr 2 afternoon → Apr 6 morning quiet — only session_off + no_setup + 3× rr_too_low SELL. No new trend-failure attempts. Gates correctly filtering. |
| 2026-05-11 00:55 | Apr 7 11:35 | Tick 3: 964 sigs, **10 TAKEN**, **+$343.64** / 44W 5L. 4 consecutive Apr 6 BUYs all winners (G5006-G5009, +$208.44 combined). 2 Apr 7 BUYs just fired (open). Double-tap pattern NOT the G5002 root cause — G5002 was regime-specific. |
| 2026-05-11 03:05 | Apr 28 17:15 | **Tick 4 (gap)**: 5,330 sigs, **52 TAKEN** (42 new since tick 3), **P&L collapsed to −$5,632.70** / 447W 150L. Run 15 progressed Apr 7→Apr 28 in the gap. **Catastrophic cascade losses dominate**: cascade SELL STOP CONT magics (≥220000) account for **−$4,736 / 84% of total loss**. Initial group magics: −$2,090. Base magic 202401 (TP1 partials): +$1,193. 11 new SELL BB_BREAKOUT entries Apr 23–28 (all TREND_BEAR regime), most hit TP1 on initial leg, then cascade fired and got crushed on reversal at 3.5×ATR. Examples: Apr 23 13:10–13:20 4 rapid SELLs cascaded for ≈−$1,000; Apr 24 07:25 + 07:34 cluster cascaded for ≈−$1,700; Apr 27 17:55–18:10 cluster (4 SELLs in 15 min) cascaded for ≈−$2,300. Note: v2.7.21 was compiled and config-applied at 02:45 — but operator chose to let v2.7.16 finish first (this run, no reload). RSI values 27.2, 30.1, 32.4 in this cluster — well below v2.7.21's new floor of 33. New cooldown 900s would have blocked half the SELL cluster. **Critical insight**: cascade-regime guard (v2.7.21) only blocks RANGE — but these failures fired in TREND_BEAR, so even v2.7.21 would not block them. The cascade itself needs a stricter arm gate (proposal: raise `sell_stop_cont_min_rsi` from 25 → 33 to prevent arming when RSI already extreme oversold). |
| 2026-05-11 03:33 | Apr 29 13:15 | **Tick 5 (quiet)**: 5,559 sigs (+229), **52 TAKEN (unchanged)**, P&L unchanged −$5,632.70. Sim advanced 20 sim hours. New SKIPs all benign: 118 session_off + 104 no_setup + 3 adx_min_sell + 2 direction + 2 atr_ext. Last trade activity Apr 28 08:06 (G5052 cascade WON +$175 — 5 legs × +$35). Apr 28 afternoon → Apr 29 morning had no entry triggers. Approaching Apr 29 active session — historically Run 10/12 G5001/G5002 SELL cluster fires here. Watching. |
