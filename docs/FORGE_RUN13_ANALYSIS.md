# FORGE 2.6.9 — Run 13 Backtest Analysis
**Date:** 2026-05-08 | **Period:** Apr 14–May 7 (same window as Run 11) | **Symbol:** XAUUSD | **Mode:** DUAL
**Status:** IN PROGRESS — monitoring live | **DB run_id:** 2

---

## Key Config Changes vs Run 11 (2.6.7 → 2.6.9)

### Inherited from 2.6.8 (Run 12)
| Fix | Parameter | Run 11 | Run 13 | Rationale |
|-----|-----------|--------|--------|-----------|
| Fix 1 | `bb_breakout.adx_min` | 14 | **20** | Block false breakouts in ranging tape (~$100 Category A) |
| Fix 2 | `bb_breakout.rsi_sell_floor` | 30 | **33** | Block near-exhausted SELL + float boundary fix (~$120 Category B) |
| Fix 3 | `bb_breakout.sell_cutoff_utc` | none | **17** | Block late-session SELL reversals (~$125 Category D) |
| Fix 4 | `bb_bounce.bounce_htf_bias` | BALANCED | **STRICT** | Block SELL bounces against H1 uptrend (~$45 Category C) |
| Fix 5 | `adx_sell_floor_threshold` + `rsi_sell_floor_weak_adx` | none | **35.0 / 36.0** | ADX-conditioned RSI floor: if ADX<35 → floor=36 |

### New in 2.6.9
| Fix | Component | Change | Rationale |
|-----|-----------|--------|-----------|
| G1 hotfix | `session_off` journal | Per-tick → per-M5-bar | Prevented DB flood (272k→72 records for Asian session) |
| G3 fix | `ScalperLot` input | Default 0.01→0.0; now writes `g_sc.lot_fixed` | Input 0.08 now correctly overrides JSON `fixed_lot` |
| G4 fix | Warmup gate | Added `vp_poc_uninit` check | Blocks entry if VP failed to init at OnInit |

**Run 13 inputs: `ScalperLot=0.08`, `SellInsideBandLotFactor=0.25`**

---

## Run 11 Benchmark (2.6.7 — baseline)

| Metric | Run 11 |
|--------|--------|
| Period | Apr 14–May 7 |
| Deals | 200 |
| W/L | 161/39 |
| Win rate | 80.5% |
| Net P&L | +$426.12 |
| Avg win | +$8.40 |
| Avg loss | -$23.75 |
| TAKEN groups | 70 |
| Lot size | 0.02 |

**Run 13 lot is 0.08 (4× Run 11)** — all P&L figures will be ~4× larger. For fair comparison, use win rate, avg R:R, and per-lot P&L.

---

## Gate Verification Tracker

| Fix | Gate | Expected | Confirmed | Notes |
|-----|------|----------|-----------|-------|
| G1 session_off throttle | ≤1 record/M5 bar off-hours | 72 records Asian Apr 14 | ✅ CONFIRMED | Was 272k+ per-tick in Run 12; now 1 per bar |
| G4 VP POC warmup | `vp_poc_uninit` if POC=0 | No block = POC valid | ✅ CONFIRMED | No vp_poc_uninit in warmup; VP computed at OnInit |
| G3 lot override | Trade volume=0.08 | First trade > 0.02 | ⚠ NOT APPLIED | Trades show volume=0.02 — `ScalperLot` reset to new default 0.0 when EA recompiled; JSON `fixed_lot=0.02` wins. See G5. |
| Fix 1 `adx_min=20` | Apr 20 ADX=14.6 SELL blocked | ⏳ pending | First test: Apr 20 08:45 |
| Fix 2 `rsi_sell_floor=33` | Apr 21 RSI=32.55 blocked | ⏳ pending | First test: Apr 21 16:10 |
| Fix 3 `sell_cutoff_utc=17` | Apr 28 17:41 SELL blocked | ⏳ pending | First test: Apr 28 17:41 |
| Fix 4 `bounce_htf_bias=STRICT` | Apr 15 bounce SELL blocked | ⏳ pending | First test: Apr 15 14:35 |
| Fix 5 ADX-cond RSI floor | Apr 30 ADX=29 RSI=33 blocked | ⏳ pending | First test: Apr 30 19:20 |
| Float fix (floor→33) | 0 RSI=30.0 violations | ⏳ pending | Was 5 in Run 11 |
| SellInsideBandLotFactor=0.25 | Inside-band SELL at 0.25× lot | ⏳ pending | First inside-band SELL entry |

---

## Warmup Analysis — Apr 14 07:00 UTC

| Bar | Time UTC | Gate | RSI | ADX | Status |
|-----|----------|------|-----|-----|--------|
| W1 | 07:00 | warmup_tester_m5_rollovers | 0.0 | 0.0 | Expected — pre-indicator |
| W2 | 07:05 | warmup_tester_m5_rollovers | 0.0 | 0.0 | Expected |
| 1 | 07:10 | no_setup | 47.60 | 14.88 | ✅ Indicators valid |
| 2 | 07:15 | no_setup | 49.59 | 15.37 | ✅ |

**vp_poc_uninit: 0 fires** — VP computed successfully at OnInit. ✅

**session_off: 72 records** for full Asian session (01:00–06:55 UTC = 72 × 5-min bars). ✅ Fix confirmed.

---

## Live Progress — Run 13

### Snapshot: Apr 14 (IN PROGRESS — at 07:55 UTC)

| # | Time UTC | Setup | Dir | RSI | ADX | Price | Vol | vs Run 11 |
|---|----------|-------|-----|-----|-----|-------|-----|-----------|
| — | First TAKEN expected ~09:55 | — | — | — | — | — | — | — |

### Skip Breakdown — Apr 14 so far

| Gate | Run 13 (Apr 14 so far) | Run 11 (full run) | Notes |
|------|----------------------|-------------------|-------|
| `session_off` | **72** | 0 (not tracked in R11) | ✅ Throttled to 1/bar — was 167k+ in Run 12 |
| `warmup_tester_m5_rollovers` | 2 | 2 | ✅ same |
| `no_setup` | 10 | 2,738 | Partial |

---

## Daily Performance — Running Tally

| Date | Taken | Deals | W | L | P&L | vs Run 11 (0.02 lot) | vs Run 11 (scaled ×4) | Key events |
|------|-------|-------|---|---|-----|----------------------|----------------------|------------|
| Apr 14 | ⏳ | — | — | — | — | Run 11: +$160.44 | ~+$641 | First lot verification |
| Apr 15 | ⏳ | — | — | — | — | Run 11: +$43.66 | ~+$175 | Fix 4: bounce SELL blocked |
| Apr 17 | ⏳ | — | — | — | — | Run 11: -$38.14 | ~-$153 | |
| Apr 20 | ⏳ | — | — | — | — | Run 11: -$75.56 | ~-$302 | Fix 1: ADX=14.6 blocked |
| Apr 21 | ⏳ | — | — | — | — | Run 11: +$32.98 | ~+$132 | Fix 2: RSI=32.55 blocked |
| Apr 22 | ⏳ | — | — | — | — | Run 11: +$71.84 | ~+$287 | |
| Apr 23 | ⏳ | — | — | — | — | Run 11: +$35.08 | ~+$140 | |
| Apr 24 | ⏳ | — | — | — | — | Run 11: -$16.36 | ~-$65 | Fix 2: RSI=30.12 blocked |
| Apr 27 | ⏳ | — | — | — | — | Run 11: +$32.58 | ~+$130 | Float fix |
| Apr 28 | ⏳ | — | — | — | — | Run 11: -$12.92 | ~-$52 | Fix 1+3: ADX=14.7, 17:41 cutoff |
| Apr 29 | ⏳ | — | — | — | — | Run 11: +$90.12 | ~+$360 | |
| Apr 30 | ⏳ | — | — | — | — | Run 11: -$2.84 | ~-$11 | Fix 5: ADX=29 RSI=33 |
| May 1 | ⏳ | — | — | — | — | Run 11: -$32.90 | ~-$132 | Float fix |
| May 4 | ⏳ | — | — | — | — | Run 11: +$52.86 | ~+$211 | |
| May 5 | ⏳ | — | — | — | — | Run 11: $0 | $0 | Quality gates hold |
| May 6 | ⏳ | — | — | — | — | Run 11: +$71.68 | ~+$287 | Category F |
| May 7 | ⏳ | — | — | — | — | Run 11: +$13.60 | ~+$54 | Category G cascade |
| **TOTAL** | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | **Run 11: +$426.12** | **~+$1,704 (scaled)** | |

**Note on P&L comparison:** Run 13 uses 0.08 lots vs Run 11's 0.02 lots (4× scale). Raw P&L will be ~4× larger. Win rate and gate verification are the primary comparisons. `SellInsideBandLotFactor=0.25` further reduces lot on inside-band SELL entries to 0.08×0.25=0.02 (same as Run 11 for those specific entries).

---

## Gotchas & Potential Improvements (Running Log)

### G1 — session_off per-tick journal flood — FIXED (2.6.9 / hotfix 1.8.6)
- **Status:** Confirmed fixed. 72 records for full Apr 14 Asian session (1/bar) vs 272k+ per-tick in Run 12
- **DB size at run start:** 125MB (bloated from Run 12 old data in run_id=1; Run 13 data is run_id=2 and clean)

### G2 — `bounce_htf_bias=STRICT` logs as `no_setup` (pending re-confirmation)
- Apr 15 14:35 BB_BOUNCE SELL blocked in Run 12 but gate_reason=`no_setup` not descriptive
- Monitoring Run 13 Apr 15 to re-confirm and check gate_reason label
- **Fix for 2.6.10:** Log `bounce_htf_bias_strict` when STRICT mode rejects bounce direction

### G3 — `ScalperLot` input ignored after JSON load — FIXED (2.6.9 / hotfix 1.8.7)
- `ScalperLot=0.08` in MT5 Inputs now correctly writes `g_sc.lot_fixed=0.08`
- **Verification:** First TAKEN trade volume must be 0.08 (not 0.02)

### G5 — MT5 input reset on recompile — operational gap (for workflow docs)
- **What:** When EA is recompiled in MT5 Strategy Tester, all inputs reset to their default values. `ScalperLot` default changed from `0.01 → 0.0` in 2.6.9, so after recompile it silently fell back to 0.0 = use JSON `fixed_lot=0.02`. Run 13 is executing at 0.02 lot, not the intended 0.08.
- **Impact:** P&L magnitude is ¼ of target, but gate verification (ADX floor, RSI floor, bounce STRICT, session cutoff) is unaffected — continue monitoring for correctness
- **Fix for next run:** After every recompile, explicitly set `ScalperLot=0.08` in the MT5 Inputs panel before starting the tester. OR set `fixed_lot: 0.08` in `config/scalper_config.json` (permanent, survives recompile).
- **Recommendation for 2.6.10:** Add a `PrintFormat("FORGE lot_fixed=%.2f ScalperLot=%.2f lot_source=%s", g_sc.lot_fixed, ScalperLot, g_sc.lot_sizing_source)` at OnInit so the active lot is always visible in the MT5 journal at startup

### G4 — VP POC warmup gap — FIXED (2.6.9 / hotfix 1.8.7)
- `vp_poc_uninit` check added to `ForgeNativeScalperWarmupOk()`
- **Confirmed:** No `vp_poc_uninit` fires in Run 13 warmup — VP computed at OnInit ✅

---

## Expected P&L Delta (Run 13 vs Run 11, normalized to 0.02 lot basis)

| Category | Run 11 Loss | Fix | Expected Saving |
|----------|------------|-----|-----------------|
| A — ADX<20 breakouts | ~$100 | Fix 1: adx_min=20 | ~$100 |
| B — Near-floor RSI 30–33 SELL | ~$120 | Fix 2: floor=33 + Fix 5 ADX-cond | ~$120 |
| C — BB_BOUNCE vs H1 trend | ~$45 | Fix 4: STRICT bias | ~$45 |
| D — Late-session SELL | ~$125 | Fix 3: cutoff=17 | ~$125 |
| Float boundary (RSI=30.0) | ~$40 | Fix 2 (floor=33 makes moot) | ~$40 |
| **Total expected savings** | **~$430** | | **~$430** |

Run 11 net: +$426.12 → **Target Run 13 (0.02 basis): >$850**
Run 13 actual (0.08 lot, ×4 scale): **Target >$3,400** if all fixes work

---

*Last updated: 2026-05-08 — monitoring in progress*
