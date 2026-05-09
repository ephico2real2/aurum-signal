# FORGE 2.7.0 — Run 14 Backtest Analysis
**Date:** 2026-05-08 | **Period:** Apr 14–May 7 | **Symbol:** XAUUSD | **Mode:** DUAL
**Status:** IN PROGRESS — monitoring live | **DB:** tester run_id=3

---

## Version History Leading to Run 14

| Version | Key Changes |
|---------|-------------|
| 2.6.7 (Run 11) | RSI BUY ceil=70, SELL floor=30, bounce ADX cap — baseline |
| 2.6.8 (Run 12) | adx_min=20, rsi_sell_floor=33, sell_cutoff=17, bounce STRICT, ADX-cond RSI floor |
| 2.6.9 (Run 13) | ScalperLot input fix, VP POC warmup gate, session_off throttle |
| 2.6.10 | ScalperMode default=DUAL, WATCH safety default retained |
| **2.7.0 (Run 14)** | **Current — all above fixes active** |

---

## Run 11 Benchmark (2.6.7 — baseline for all comparisons)

| Metric | Run 11 |
|--------|--------|
| Deals | 200 |
| W/L | 161/39 |
| Win rate | 80.5% |
| Net P&L | +$426.12 (0.02 lot) |
| Avg win | +$8.40 |
| Avg loss | -$23.75 |
| TAKEN groups | 70 |

---

## Active Fixes vs Run 11

| Fix | Parameter | Run 11 | Run 14 | Est. saving |
|-----|-----------|--------|--------|-------------|
| 1 | `bb_breakout.adx_min` | 14 | **20** | ~$100 |
| 2 | `bb_breakout.rsi_sell_floor` | 30 | **33** | ~$120 |
| 3 | `sell_cutoff_utc` | none | **17** | ~$125 |
| 4 | `bb_bounce.bounce_htf_bias` | BALANCED | **STRICT** | ~$45 |
| 5 | ADX-cond RSI floor | none | **35/36** | ~$30 |
| — | session_off throttle | n/a | 1/bar | DB hygiene |
| — | VP POC warmup gate | none | `vp_poc_uninit` | Safety |
| — | `ScalperLot` input | 0.01 default | **0.0 (use JSON)** | Correctness |
| — | `ScalperMode` default | NONE | **DUAL** | Usability |

---

## Warmup Analysis — Apr 14 07:00 UTC

| Bar | Time UTC | Gate | RSI | ADX | Status |
|-----|----------|------|-----|-----|--------|
| Asian | 01:00–06:55 | session_off | 0.0 | 0.0 | ✅ 72 records (1/bar) |
| W1 | 07:00 | warmup_tester_m5_rollovers | 0.0 | 0.0 | ✅ expected |
| W2 | 07:05 | warmup_tester_m5_rollovers | 0.0 | 0.0 | ✅ expected |
| 1 | 07:10 | no_setup | 47.60 | 14.88 | ✅ indicators valid |

**vp_poc_uninit fires: 0** — VP computed at OnInit ✅
**session_off: 72 records** — throttle fix working ✅

---

## Gate Verification Tracker

| Fix | Gate | First Test Date | Status |
|-----|------|-----------------|--------|
| Fix 1 `adx_min=20` | ADX<20 SELL blocked | Apr 20 08:45 (ADX=14.6) | ⏳ |
| Fix 2 `rsi_sell_floor=33` | RSI<33 SELL blocked | Apr 21 16:10 (RSI=32.55) | ⏳ |
| Fix 3 `sell_cutoff_utc=17` | SELL after 17:00 blocked | Apr 28 17:41 | ⏳ |
| Fix 4 `bounce_htf_bias=STRICT` | BB_BOUNCE SELL vs H1 bull | Apr 15 14:35 + 16:45 | ⏳ |
| Fix 5 ADX-cond RSI floor | ADX<35 → floor=36 | Apr 30 19:20 | ⏳ |
| Float fix (floor→33) | 0 RSI=30.0 violations | Throughout | ⏳ |
| `ScalperLot=0.08` | Trade volume=0.08 | First TAKEN | ⏳ |
| `SellInsideBandLotFactor` | Inside-band SELL at 0.02 | First SELL inside band | ⏳ |

---

## Live Progress

### Apr 14 — IN PROGRESS (08:25 UTC)

Skip breakdown so far:

| Gate | Count | Notes |
|------|-------|-------|
| `session_off` | 72 | ✅ 1/bar throttle working |
| `entry_quality_atr` | 37 | Per-tick during ATR burst at 08:15 — see G1 |
| `no_setup` | 16 | Normal London open |
| `warmup_tester_m5_rollovers` | 2 | ✅ |

First TAKEN expected ~09:55. Watching for lot size confirmation.

---

## Daily Performance — Running Tally

| Date | Taken | Deals | W | L | P&L | Run 11 (0.02) | Notes |
|------|-------|-------|---|---|-----|---------------|-------|
| Apr 14 | ⏳ | — | — | — | — | +$160.44 | Lot verification |
| Apr 15 | ⏳ | — | — | — | — | +$43.66 | Fix 4: bounce SELL blocked |
| Apr 17 | ⏳ | — | — | — | — | -$38.14 | Single SELL, ADX=26.8 |
| Apr 20 | ⏳ | — | — | — | — | -$75.56 | Fix 1: ADX=14.6 |
| Apr 21 | ⏳ | — | — | — | — | +$32.98 | Fix 2: RSI=32.55 |
| Apr 22 | ⏳ | — | — | — | — | +$71.84 | |
| Apr 23 | ⏳ | — | — | — | — | +$35.08 | |
| Apr 24 | ⏳ | — | — | — | — | -$16.36 | Fix 2: RSI=30.12 |
| Apr 27 | ⏳ | — | — | — | — | +$32.58 | Float fix |
| Apr 28 | ⏳ | — | — | — | — | -$12.92 | Fix 1+3 |
| Apr 29 | ⏳ | — | — | — | — | +$90.12 | |
| Apr 30 | ⏳ | — | — | — | — | -$2.84 | Fix 5 |
| May 1 | ⏳ | — | — | — | — | -$32.90 | Float fix |
| May 4 | ⏳ | — | — | — | — | +$52.86 | |
| May 5 | ⏳ | — | — | — | — | $0 | Quality gates hold |
| May 6 | ⏳ | — | — | — | — | +$71.68 | Category F |
| May 7 | ⏳ | — | — | — | — | +$13.60 | Category G cascade |
| **TOTAL** | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | **+$426.12** | Target >$850 (0.02 basis) |

**Note:** Run 14 uses `ScalperLot=0.08` (4× Run 11). Raw P&L ~4× larger. Gate verification and win rate are the primary comparison metrics. To normalise: divide Run 14 P&L by 4.

---

## Gotchas & Potential Improvements (Running Log)

### G1 — `entry_quality_atr` per-tick logging at 08:15 (⚠ new observation)
- **What:** At 08:15:19–08:15:50, 12 `entry_quality_atr` SKIP records fired within 31 seconds — clearly per-tick, not per-bar. RSI=ADX=0.0 on all of them (same symptom as the old session_off flood)
- **Pattern:** The gate fires on a tick burst before the bar closes, logging RSI=0.0/ADX=0.0 because the gate is hit before indicator values are read
- **Impact:** Low count (37 total) so not a DB flood risk, but produces noisy zero-indicator records
- **Root cause:** Same class of bug as the session_off per-tick issue — `JournalRecordSignal` called per-tick for this gate rather than being throttled to once per bar
- **Fix for 2.7.1:** Apply same M5-bar throttle pattern to `entry_quality_atr` gate as was applied to `session_off` in 2.6.9

### G2 — `bounce_htf_bias=STRICT` logs as `no_setup` (carried from Run 12/13)
- Apr 15 BB_BOUNCE SELL blocks showed as `no_setup` — STRICT rejection not labelled distinctly
- **Fix for 2.7.1:** Log `gate_reason='bounce_htf_bias_strict'` when STRICT mode rejects

---

## Expected P&L Delta (normalised to 0.02 lot)

| Category | Run 11 Loss | Fix | Expected Saving |
|----------|-------------|-----|-----------------|
| A — ADX<20 breakouts | ~$100 | Fix 1 | ~$100 |
| B — RSI 30–33 SELL | ~$120 | Fix 2 + Fix 5 | ~$120 |
| C — Bounce vs H1 trend | ~$45 | Fix 4 | ~$45 |
| D — Late-session SELL | ~$125 | Fix 3 | ~$125 |
| Float boundary | ~$40 | Fix 2 (floor=33) | ~$40 |
| **Total** | **~$430** | | **~$430** |

**Target: Run 14 normalised P&L > +$850 (0.02 basis) / >+$3,400 (0.08 actual)**

---

*Last updated: 2026-05-08 — monitoring in progress*
