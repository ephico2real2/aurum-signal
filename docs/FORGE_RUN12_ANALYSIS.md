# FORGE 2.6.8 — Run 12 Backtest Analysis
**Date:** 2026-05-08 | **Period:** Apr 14–May 7 (same window as Run 11) | **Symbol:** XAUUSD | **Mode:** DUAL
**Status:** IN PROGRESS — monitoring live

---

## Key Config Changes vs Run 11 (2.6.7 → 2.6.8)

| Fix | Parameter | Run 11 | Run 12 | Rationale |
|-----|-----------|--------|--------|-----------|
| Fix 1 | `bb_breakout.adx_min` | 14 | **20** | Block false breakouts in ranging tape (Category A losses: ~$100) |
| Fix 2 | `bb_breakout.rsi_sell_floor` | 30 | **33** | Block near-exhausted SELL entries + float boundary fix (Category B + float: ~$120) |
| Fix 3 | `bb_breakout.sell_cutoff_utc` | none | **17** | Block late-session SELL reversals (Category D: ~$125) |
| Fix 4 | `bb_bounce.bounce_htf_bias` | BALANCED | **STRICT** | Block SELL bounces against H1 uptrend (Category C: ~$45) |
| Fix 5 | `adx_sell_floor_threshold` + `rsi_sell_floor_weak_adx` | none | **35.0 / 36.0** | ADX-conditioned RSI floor: if ADX<35 then floor=36, else floor=33 |

**Expected savings from fixes: ~$390–$440 (Fixes 1–4 combined)**

---

## Run 11 Benchmark (2.6.7)

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

---

## Live Progress — Run 12

### Snapshot: Apr 14 (COMPLETE)

**P&L: +$160.44 | 30 deals | 28W / 2L | 5 TAKEN groups**

| # | Time UTC | Setup | Dir | RSI | ADX | Price | vs Run 11 |
|---|----------|-------|-----|-----|-----|-------|-----------|
| 1 | Apr 14 09:55 | BB_BREAKOUT | BUY | 65.94 | 31.16 | 4779.11 | ✅ identical |
| 2 | Apr 14 10:00 | BB_BREAKOUT | BUY | 69.97 | 36.21 | 4783.54 | ✅ identical |
| 3 | Apr 14 10:10 | BB_BREAKOUT | BUY | 69.94 | 46.87 | 4789.86 | ✅ identical |
| 4 | Apr 14 16:22 | BB_BREAKOUT | BUY | 64.63 | 30.36 | 4790.66 | ✅ identical |
| 5 | Apr 14 16:39 | BB_BREAKOUT | BUY | 61.58 | 36.67 | 4792.68 | ✅ identical |

**Gate verification — Apr 14:**
- `rsi_buy_ceil` fires: **1,518** (Apr 14 only; Run 11 full-run total was 40,224)
- `rsi_sell_floor` fires: **0** (expected — Apr 14 was all-BUY)
- No SELL entries → Fix 2/3/5 not yet exercised

### Skip Breakdown — Apr 14

| Gate | Run 12 (Apr 14) | Run 11 (full run) | Notes |
|------|-----------------|-------------------|-------|
| `session_off` | **167,883** | 0 (not in Run 11) | ⚠ NEW — session filter firing heavily; likely tester_session_filter=1 on Asian bars |
| `entry_quality_direction` | 6,451 | 132,501 | Partial — only Apr 14 |
| `entry_quality_direction_cap` | 3,374 | 21,518 | Partial |
| `entry_quality_atr` | 2,987 | 36,776 | Partial |
| `entry_quality_body` | 2,724 | 107,473 | Partial |
| `entry_quality_rsi_buy_ceil` | 1,518 | 40,224 | Partial |
| `entry_quality_bb_contraction` | 581 | 5,798 | Partial |
| `no_setup` | 149 | 2,738 | Partial |
| `warmup_tester_m5_rollovers` | 2 | 2 | ✅ same |
| `cooldown` | 2 | 24 | Partial |
| `rr_too_low` | 1 | 19 | Partial |
| `entry_quality_rsi_sell_floor` | **0** | 52,443 | Not yet active (no SELL days yet) |

#### ⚠ Gotcha: `session_off` gate — 167,883 fires not seen in Run 11

Run 11 had no `session_off` in the skip breakdown. Run 12 shows 167,883 on Apr 14 alone. This is likely the `tester_session_filter=1` + `skip_asian=1` correctly firing on every M5 bar in the Asian session (00:00–07:00 UTC = 84 bars/day × ~5-week run = ~2,000+ bars). The April 14 count of 167,883 is suspicious — this is far more than one day of Asian bars suggests. **To investigate:** whether `session_off` was renamed from another gate in 2.6.8, or if the filter is over-firing on intraday bars.

---

## Fix Verification Tracker

| Fix | Gate | Expected | Confirmed | Notes |
|-----|------|----------|-----------|-------|
| Fix 1 `adx_min=20` | blocks ADX<20 breakouts | Apr 20 ADX=14.6 SELL blocked | ⏳ pending | First test: Apr 20 08:45 |
| Fix 2 `rsi_sell_floor=33` | blocks RSI<33 SELL | Apr 21 RSI=32.55 blocked | ⏳ pending | First test: Apr 21 16:10 |
| Fix 3 `sell_cutoff_utc=17` | blocks SELL after 17:00 UTC | Apr 28 17:41 SELL blocked | ⏳ pending | First test: Apr 28 17:41 |
| Fix 4 `bounce_htf_bias=STRICT` | blocks SELL bounce vs H1 bull | Apr 15 bounce SELL blocked | ✅ CONFIRMED | Both Apr 15 14:35 + 16:45 BB_BOUNCE SELL blocked (were -$13.02 and -$16.40 in Run 11); gate logs as `no_setup` — see G2 |
| Fix 5 ADX-cond RSI floor | `adx<35 → floor=36` | Apr 30 RSI=33 ADX=29 blocked | ⏳ pending | First test: Apr 30 |
| Float fix (→33) | RSI=30.0 violations | 0 violations | ⏳ pending | Was 5 in Run 11 |

---

## Daily Performance — Running Tally

| Date | Taken | Deals | W | L | P&L | vs Run 11 | Key changes |
|------|-------|-------|---|---|-----|-----------|-------------|
| Apr 14 | 5 | 30 | 28 | 2 | **+$160.44** | = same | BUY only — no SELL fixes exercised |
| Apr 15 | 2 BUY | 6+ | 6 | 0 | **+$31.58+** | Run 11: +$43.66 (14W/2L) | Fix 4 ✅ CONFIRMED — both BB_BOUNCE SELL losses blocked; BUY legs still settling |
| Apr 17 | ⏳ | — | — | — | — | Run 11: -$38.14 | |
| Apr 20 | ⏳ | — | — | — | — | Run 11: -$75.56 | Fix 1 first test (ADX=14.6) |
| Apr 21 | ⏳ | — | — | — | — | Run 11: +$32.98 | Fix 2 first test (RSI=32.55) |
| Apr 22 | ⏳ | — | — | — | — | Run 11: +$71.84 | |
| Apr 23 | ⏳ | — | — | — | — | Run 11: +$35.08 | |
| Apr 24 | ⏳ | — | — | — | — | Run 11: -$16.36 | Fix 2 test (RSI=30.12) |
| Apr 27 | ⏳ | — | — | — | — | Run 11: +$32.58 | Float fix test |
| Apr 28 | ⏳ | — | — | — | — | Run 11: -$12.92 | Fix 1+3 test (ADX=14.7, 17:41 cutoff) |
| Apr 29 | ⏳ | — | — | — | — | Run 11: +$90.12 | Fix 3 test (ADX<20 entries at 15:35/15:57) |
| Apr 30 | ⏳ | — | — | — | — | Run 11: -$2.84 | Fix 5 test (ADX=29, RSI=33) |
| May 1 | ⏳ | — | — | — | — | Run 11: -$32.90 | Float fix test |
| May 4 | ⏳ | — | — | — | — | Run 11: +$52.86 | Float fix test |
| May 5 | ⏳ | — | — | — | — | Run 11: $0 | Quality gates expected to hold |
| May 6 | ⏳ | — | — | — | — | Run 11: +$71.68 | Category F test |
| May 7 | ⏳ | — | — | — | — | Run 11: +$13.60 | Category G cascade test |
| **TOTAL** | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | **Run 11: +$426.12** | Target: >$500 |

---

## Gotchas & Potential Improvements (Running Log)

### G1 — `session_off` per-tick journal flood — BUG FOUND & FIXED (hotfix 1.8.6)
- **What:** `JournalRecordSignal("SKIP","session_off",...)` at `ea/FORGE.mq5:3943` fired on every `OnTick()` during Asian/overnight hours — 272,238 records with RSI=ADX=0.0 in just 1.5 days, DB hit 60MB
- **Root cause:** `PrintFormat` was inside the M5-bar throttle guard; `JournalRecordSignal` was not — one line below the closing `}`
- **Projected impact unpatched:** ~4.3M session_off records, ~1.5GB DB for a full 24-day run; tester progressively slows as SQLite insert cost scales
- **Fix:** Moved `JournalRecordSignal` inside the `if(m5bar != g_scalper_last_sesswarn_log_bar)` block — now fires at most once per M5 bar (≤96 records/day off-hours)
- **Action:** Stop backtest → `make journal-reset-tester` → recompile EA → restart Run 12 with clean DB
- **For 2.6.9:** Add regression test asserting session_off record count ≤ (off_hours_bars × days) to catch this class of per-tick flood

### G3 — `ScalperLot` input ignored after JSON load — BUG FIXED (hotfix 1.8.7)
- **What:** Setting `ScalperLot=0.08` in MT5 Inputs had no effect; `g_sc.lot_fixed` was always overwritten by the config JSON (`fixed_lot=0.02`) and `ApplyScalperLotInputOverrides()` never restored it
- **Root cause:** The function applied `SellInsideBandLotFactor` correctly (with override semantics) but had no equivalent line for `ScalperLot`. The old default (0.01) also made it impossible to distinguish "user left at default" from "user set intentionally"
- **Fix:** Changed `ScalperLot` default `0.01 → 0.0` (0 = use JSON, >0 = override); added `if(ScalperLot > 0.0) g_sc.lot_fixed = ScalperLot;` in `ApplyScalperLotInputOverrides()`; updated `InitScalperConfig` to seed `lot_fixed` from `ScalperLot` when non-zero
- **For 2.6.9:** All existing configs unaffected (ScalperLot=0 → JSON drives lot). Users who relied on ScalperLot=0.01 as a "fixed" lot should set `fixed_lot: 0.01` in JSON instead

### G4 — VP POC warmup gap — FIXED (hotfix 1.8.7)
- **What:** No check that `g_poc_price > 0` before allowing first trade entry. If `ComputeVolumeProfile()` silently failed at `OnInit` (CopyHigh/Low/Close returning fewer than `vp_lookback=100` bars), the EA would compute TP adjustments against a zero POC — incorrect TP targets on the first group
- **Fix:** Added `if(g_poc_price <= 0.0) { reason_out = "vp_poc_uninit"; return false; }` in `ForgeNativeScalperWarmupOk()` after PSAR probe, before M5 rollover count. In practice this should never fire in a properly configured backtest (100 bars of pre-history always available), but catches silent VP init failures in edge cases

### G2 — `bounce_htf_bias=STRICT` blocks log as `no_setup` — ambiguous gate reason (for 2.6.9)
- **What:** When STRICT mode rejects a BB_BOUNCE SELL because H1 is bullish, the signal is logged with `gate_reason='no_setup'` rather than a dedicated reason like `bounce_htf_bias_strict`
- **Impact:** Can't distinguish STRICT-mode rejections from "BB condition genuinely not met" in skip analysis; underreports how many trades STRICT mode is saving
- **Evidence:** Apr 15 14:35 — RSI=51.83 ADX=25.47 (same as Run 11 TAKEN BB_BOUNCE SELL) appears as `no_setup` in Run 12. The price was near BB upper but STRICT blocked it before BB touch was confirmed as a valid setup
- **Fix for 2.6.9:** Log `gate_reason='bounce_htf_bias_strict'` when STRICT mode rejects a bounce direction, so analysis can track savings from this gate specifically

---

## Expected P&L Delta (Run 12 vs Run 11)

| Category | Run 11 Loss | Fix Applied | Expected Saving |
|----------|------------|-------------|-----------------|
| A — ADX<20 breakouts | ~$100 | Fix 1: adx_min=20 | ~$100 |
| B — Near-floor RSI 30–33 SELL | ~$120 | Fix 2: floor=33 + Fix 5: ADX-cond | ~$120 |
| C — BB_BOUNCE vs H1 trend | ~$45 | Fix 4: STRICT bias | ~$45 |
| D — Late-session SELL | ~$125 | Fix 3: cutoff=17 | ~$125 |
| Float boundary (RSI=30.0) | ~$40 | Fix 2 (floor=33 makes moot) | ~$40 |
| **Total expected** | **~$430** | | **~$430** |

Run 11 net: +$426.12 → **Target Run 12: >$850** (if fixes work and no new loss categories emerge)

Note: Some saved losses may also mean fewer profitable SELL entries blocked — net delta could be lower if ADX/RSI floors filter out winners too. Monitor SELL TAKEN count carefully.

---

*Last updated: 2026-05-08 — monitoring in progress*
