# FORGE Run 12 — Tester Analysis

**EA version**: FORGE v2.7.13
**Symbol**: XAUUSD
**Sim period**: 2026-04-29 → 2026-05-05 (run paused; period reaches May 5 23:55 UTC)
**Scalper mode**: DUAL
**Balance**: $10,000
**aurum_run_id**: 12
**wall_time**: 520476456
**source_run_id**: 1 (TESTER_RUNS.id)
**Magic base**: 202401

---

## Summary — IN PROGRESS (paused at May 5 23:55 UTC)

| Metric | Value |
|--------|-------|
| Sim period reached | 2026-04-29 01:00 → 2026-05-05 23:55 (~7 sim days) |
| Total signals | 14,477 |
| TAKEN groups | **5** (BB_BREAKOUT only — 2 SELL + 3 BUY) |
| Skipped | 14,472 |
| **Trades** | **62 deals (31 partial closes + 31 final closes)** |
| **Wins / Losses** | **31 / 0** ✓ |
| **Total P&L** | **+$506.63** |
| Best single win | +$89.84 |
| Avg win | +$16.34 |
| Athena cross-check | ✓ `/api/backtest/run/12` returns `pnl=506.63 wins=31 losses=0` |
| AURUM sync | 100.0% (14,477 / 14,477) |
| May 4 17:10 G5008 catastrophe | **BLOCKED** by `entry_quality_adx_spike_sell` ✓ |

---

## Key Configuration vs Run 11

| Change | v2.7.12 (Run 11) | **v2.7.13 (Run 12)** | Effect |
|--------|---|---|---|
| `block_hid_bull_sell` | 0 | **1** | Blocks SELL when RSI_DIV=HID_BULL (reversal warning) |
| `h1h4_crash_sell_min_m15_adx` | 0 (off) | **25** | Crash bypass requires real M15 trend |
| `require_macd_buy` | 0 | **1** | Requires MACD histogram positive for BUY |
| `adx_lot_factor_high` (M15≥45) | 1.0 | **0.5** | Halves lot at high ADX |
| `native_legs_max_when_unclear` | 2 | **5** | More legs when H1 unclear |
| `sell_stop_cont_legs` | 3 | **5** | Larger cascade |
| `sell_stop_cont_require_h1_di` | 0 | **1** | Cascade waits for H1 DI- > DI+ |

---

## TAKEN Groups

| # | Sim Time (UTC) | Group | Setup | Dir | Price | RSI | ADX | M15 ADX | H1 trend | RSI_DIV | lot_f | P&L | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-04-30 07:05 | G5001 | BB_BREAKOUT | SELL | 4554.51 | 32.1 | 41.3 | 35.6 | -1.524 | NONE | 0.25 | **+$23.03** | 5 legs armed, 2 filled (slot 0+1) → both TP |
| 2 | 2026-04-30 16:07 | G5002 | BB_BREAKOUT | BUY | 4636.76 | 54.6 | 23.0 | 50.1 | -0.034 | NONE | 1.00 | **+$112.80** | — |
| 3 | 2026-05-01 17:00 | G5003 | BB_BREAKOUT | BUY | 4626.12 | 74.9 | 26.1 | 42.0 | -0.037 | NONE | 1.00 | **+$148.00** | — |
| 4 | 2026-05-01 17:05 | G5004 | BB_BREAKOUT | BUY | 4634.69 | 78.0 | 31.3 | 43.3 | -0.009 | NONE | 1.00 | **+$68.16** | — |
| 5 | 2026-05-04 13:05 | G5005 | BB_BREAKOUT | SELL | 4558.94 | 23.8 | 29.2 | 41.7 | -0.318 | HID_BEAR | 0.25 | **+$23.96** | ArmPostTP1Ladder skipped (RSI=22.5 < 25 exhausted) |

**Notes**:
- `magic=202401` deals (final closes under base magic) sum to +$192.26 — these are runner-leg final closes attributed to base magic in MT5 (this is the partial-close attribution quirk known from prior analysis)
- Group rank mapping: G5001=207402, G5002=207403, G5003=207404, G5004=207405, G5005=207406
- `lot_f=0.25` on SELLs = `sell_inside_band_lot_factor` (entries placed inside band, not full breakout)
- `lot_f=1.0` on BUYs = full base lot

---

## Gate Breakdown (full run)

| Gate Reason | SELL | BUY | No-dir | Total | Notes |
|---|---|---|---|---|---|
| `entry_quality_direction` | 5,437 | 0 | 0 | **5,437** | Per-tick flood — only 2 distinct M5 bars (Apr 29 07:15 + 07:42). Fixed in v2.7.14. |
| `entry_quality_body` | 4,257 | 0 | 0 | 4,257 | Indecision candles — same flood issue, fixed in v2.7.14 |
| `entry_quality_rsi_buy_ceil` | 0 | 3,386 | 0 | 3,386 | Blocks BUY when RSI > 78. **0% precision** (see Q9) |
| `no_setup` | 0 | 0 | 768 | 768 | No BB breakout/bounce pattern |
| `session_off` | 0 | 0 | 594 | 594 | Asian hours, skip_asian=1 |
| `rr_too_low` | 11 | 0 | 0 | 11 | RR < 1.5× — 55% precision (best gate) |
| `entry_quality_rsi_sell_floor` | 4 | 0 | 0 | 4 | RSI ≤ floor=30 |
| `entry_quality_adx_min_sell` | 4 | 0 | 0 | 4 | ADX < 25 for SELL |
| `entry_quality_session_sell_cutoff` | 3 | 0 | 0 | 3 | UTC hour ≥ 18 — all 3 are May 4 18:16-18:25 same setup |
| `warmup_tester_m5_rollovers` | 0 | 0 | 2 | 2 | Indicator warmup |
| `entry_quality_rsi_sell_adx_floor` | 2 | 0 | 0 | 2 | Weak-ADX RSI floor — **blocked Apr 29 great SELL** |
| `entry_quality_rsi_rising_sell` | 2 | 0 | 0 | 2 | RSI tick-up — **blocked Apr 29 great SELL** |
| `entry_quality_atr_ext` | 0 | 1 | 0 | 1 | ATR too small post-setup |
| `entry_quality_adx_spike_sell` | 1 | 0 | 0 | **1** | **Saved the -$940 May 4 17:10 catastrophe** ✓ |

---

## Q9 — Gate Precision (where price went in 15 min after block)

| Gate | Correct / Total | Precision | Verdict |
|---|---|---|---|
| `entry_quality_rsi_buy_ceil` | 6 / 3,386 | **0%** | Worst gate — 3,380 missed wins. Likely correct to RAISE ceiling further (already at 78) or use ADX-conditioned variant |
| `entry_quality_adx_min_sell` | 1 / 4 | 25% | Over-filters; ADX 20-25 SELLs mostly move right |
| `entry_quality_rsi_sell_floor` | 1 / 4 | 25% | Same pattern — low RSI in strong trends is fine |
| `entry_quality_session_sell_cutoff` | 1 / 3 | 33% | The May 4 18:16 block missed a 32-pt drop. May be redundant given new gates |
| `entry_quality_rsi_sell_adx_floor` | 1 / 2 | 50% | Blocked Apr 29 30-pt winner (H1=-1.91). Fixed by v2.7.14 H1 bypass |
| `entry_quality_rsi_rising_sell` | 1 / 2 | 50% | Same Apr 29 block. Fixed by v2.7.14 H1 bypass |
| `rr_too_low` | 6 / 11 | **55%** | Best gate — keep |
| `entry_quality_adx_spike_sell` | 1 / 1 | **100%** | The G5008 catastrophe-saver. Keep |

---

## Cross-Run Comparison

| Metric | Run 10 (v2.7.11) | Run 11 (v2.7.12) | **Run 12 (v2.7.13)** |
|---|---|---|---|
| TAKEN groups | 7 | 7 | **5** |
| Wins / Losses | 32W / 10L | 6W / 1L | **31W / 0L** |
| Win rate | 76% | 86% | **100%** |
| Total P&L | -$542.75 | -$630.61 | **+$506.63** |
| G5008 / May 4 17:10 | -$960 ❌ | -$940 ❌ | **BLOCKED ✓** |
| Apr 29 15:55-16:00 SELL | TAKEN (+$241) | Filtered | **Filtered** (v2.7.14 will unblock) |

**Net delta**: +$1,137 vs Run 11 — entire turnaround driven by blocking the single G5008-pattern entry that recurred each run.

---

## Run 10 vs Run 12: Why Apr 29 15:55 + 16:00 SELLs Were TAKEN Then SKIPPED

These two entries together earned **~$241 in Run 10** (G5001 @ 4545.45 RSI=26.4 ADX=25.9 → ~$120; G5002 @ 4545.52 RSI=26.3 ADX=29.9 → ~$121). Price then crashed to 4514 by 16:45 (30 pts). Run 12 left this on the table.

**The gate code is identical between v2.7.11 and v2.7.13** — defaults haven't changed:
```
breakout_adx_sell_floor_threshold = 35.0   (both versions)
breakout_rsi_sell_floor_weak_adx  = 36.0   (both versions)
breakout_require_rsi_declining_sell = false (default, both versions)
```

The behavior change comes from TWO upstream/config differences:

### Change 1 — `crash_sell_bypass` got an M15 ADX guard (v2.7.13)

The two-tier RSI floor is wrapped in `if(!crash_sell_bypass)` — i.e., when H1+H4 are both bearish, the RSI floor is SKIPPED on the theory that a confirmed multi-TF bear is allowed deep entries.

**v2.7.11 (Run 10):**
```cpp
crash_sell_bypass = h1_bear && h4_bear && rsi > 20 && adx in range;
```
At Apr 29 15:55: H1=-1.91 ✓, H4 bear ✓, RSI=26.4 > 20 ✓, ADX in range ✓ → **bypass=TRUE → RSI floor SKIPPED → SELL TAKEN.**

**v2.7.13 (Run 12) — added M15 guard:**
```cpp
crash_m15_ok       = (m15_adx_now >= 25);   // FORGE_BREAKOUT_H1H4_CRASH_SELL_MIN_M15_ADX
crash_sell_bypass  = ... && crash_m15_ok;
```
At Apr 29 15:55, M15 ADX was still building (early breakout — M5 ADX was only 25.9, M15 lower). **crash_m15_ok=FALSE → bypass disabled → RSI floor applies → RSI=26.4 ≤ 36 → BLOCKED.**

This guard was added to stop the May 4 17:10 G5008 catastrophe (M5 ADX spike from flat base while M15 ADX=16.7). It worked for that — but as collateral it disabled a legitimate Apr 29 entry where the bypass would have been correct.

### Change 2 — `require_rsi_declining_sell` was switched ON in Run 12's `.env`

Same gate code in both versions. Configuration differs:

**Run 10 `.env`** (commit `2b28b85`): No `FORGE_BREAKOUT_REQUIRE_RSI_DECLINING_SELL` line → falls back to EA default (`false`) → gate disabled.

**Run 12 `.env`**: `FORGE_BREAKOUT_REQUIRE_RSI_DECLINING_SELL=1` → gate enabled. At Apr 29 16:00, RSI went 26.4→26.3 (declining), but the gate measures bar-over-bar against the *closed* prior bar — the just-closed 15:55 bar settled lower than 26.4, so 16:00's 26.3 reads as "rising" → BLOCKED.

### How v2.7.14 unblocks both — without re-introducing the G5008 risk

v2.7.14 adds an H1 strong-bear bypass (`h1_trend < -1.0`) inside both gates:
- `rsi_sell_adx_floor`: skip the weak-ADX floor inflation when H1 is genuinely dominant
- `rsi_rising_sell`: skip the RSI direction check when H1 is genuinely dominant

| Trade | H1 trend | v2.7.14 bypass active? | Outcome |
|---|---|---|---|
| Apr 29 15:55 SELL | -1.912 | **YES** (-1.912 < -1.0) | UNBLOCKED — RSI floor skipped |
| Apr 29 16:00 SELL | -1.997 | **YES** (-1.997 < -1.0) | UNBLOCKED — RSI direction skipped |
| May 4 17:10 (G5008) | -0.556 | **NO** (-0.556 ≥ -1.0) | Still blocked by `adx_spike_sell` AND `block_hid_bull_sell` |

The threshold -1.0 was chosen because the Apr 29 entries (~-1.95) are firmly in "strong bear" territory while May 4 17:10 (-0.55) is borderline-bearish — a clean separation.

---

## SELL STOP CONT / BUY LIMIT Cascade Events

| Group | Event | Detail |
|---|---|---|
| G5001 | ArmPostTP1Ladder armed | 5 SELL STOP legs placed, ADX=41.3 RSI=29.6 ✓ |
| G5001 slot[0] | Filled | ticket=10 at 07:07:21, TP at 4552.88 → **+$2.73** (magic 227402) |
| G5001 slot[1] | Filled | ticket=11 at 07:10:59, TP at 4552.88 → **+$3.58** (magic 227403) |
| G5001 slot[2-6] | Cancelled | 07:16 — no longer pending (price moved past trigger before fill) |
| G5001 BUY LIMIT | Skipped | RSI=29.6 < min=35.0, "Bull Support not confirmed" ✓ |
| G5005 ArmPostTP1Ladder | **Skipped** | RSI=22.5 ≤ 25.0 (exhausted) — gate correctly declined ✓ |
| G5005 BUY LIMIT | Skipped | RSI=22.5 < min=35.0 ✓ |

**Cascade verdict**: arm-time gates working correctly. G5005 deep-oversold correctly refused (would have entered into capitulation reversal).

---

## Losses — Price Movement Analysis

**N/A — no losses recorded.** First clean run since v2.7.7+ era.

---

## Recommended Parameter Changes — More Trades

**Context**: 14,477 signals evaluated, 5 TAKEN (0.03% take rate). Quality is excellent (100% WR) but volume is low — most missed opportunities are BUY blocks at RSI > 78 ceiling (3,386 hits, 0% precision).

### Priority changes for Run 13

| # | Gate / Config | Current | Proposed | Source |
|---|---|---|---|---|
| 1 | **H1 strong-bear bypass** | n/a | **active** | Already shipped in v2.7.14 — unlocks Apr 29 15:55/16:00 SELLs (H1=-1.91 / -1.99) |
| 2 | **direction/body flood throttle** | per-tick | **per-bar** | Shipped in v2.7.14 — removes ~9,000 redundant SKIP rows |
| 3 | `session_ny_sell_cutoff_utc` | 18 | **0 (disable)** OR **20** | 33% precision — missed May 4 18:16 32-pt move. New gates (HID_BULL, ADX spike) now catch what cutoff was guarding against |
| 4 | `rsi_buy_ceil` ADX-conditioned | 78 flat | 78 normal / **84 if M15 ADX ≥ 45** | 0% precision = ceiling blocks momentum BUYs. May 1 BUYs at RSI=74.9 / 78.0 fired right at the edge — many similar entries blocked |
| 5 | `entry_quality_atr_ext` | enabled | leave (1 hit only) | Negligible filter |
| 6 | `adx_min_sell` lookback | 25 | leave (25% precision but only 4 hits) | Low volume — not worth tuning further |

### Apply order
1. **Run 13 = v2.7.14 first** to validate the H1 bypass + flood throttle fixes
2. After Run 13 data: if Apr 29 SELLs now TAKEN cleanly, apply change #3 (cutoff disable) in Run 14
3. Change #4 (RSI ceiling ADX-conditioned) requires EA code — defer to v2.7.15 if Run 13 leaves BUY volume too low

> Changes go via `.env` + `make scalper-env-sync && make forge-compile`.

---

## Observations & Anomalies

1. **`m15_adx=0.0` for all SKIP signals** (TAKEN signals show real values — Apr 30 SELL M15=35.6, May 4 SELL M15=41.7). The SKIP-row logging path doesn't write `m15_adx`. Not affecting trade decisions but limits SKIP forensics.

2. **`entry_quality_direction` per-tick flood**: 5,437 hits from only 2 distinct M5 bars (Apr 29 07:15 = 1,700 ticks, 07:42 = 883 ticks). The gate has no M5-bar throttle in v2.7.13. **Fixed in v2.7.14**.

3. **Group magic mapping for partial closes** is consistent with prior runs — final closes appear under base magic 202401, partial close events under group magic. The +$192.26 on magic=202401 is the sum of final-close runners across G5001-G5005.

4. **Apr 29 great SELL missed** — H1=-1.912 / -1.997 (strongest bearish H1 of the period), price dropped 30 pts from 4545 → 4514 in 50 min, blocked by `rsi_sell_adx_floor` + `rsi_rising_sell`. v2.7.14 H1 bypass fix specifically addresses this.

5. **May 4 17:10 catastrophe = BLOCKED**. The two safety nets fired in order: `entry_quality_adx_spike_sell` first (ADX spiked from <25 to 37.4 in 30 min, a flat-base spike pattern). Even without that, `block_hid_bull_sell` would have caught it (RSI_DIV=HID_BULL). Defense-in-depth working.

6. **G5005 cascade refusal** (May 4 13:05 SELL): RSI dropped to 22.5 by ladder-arm time, deep oversold. EA correctly skipped ArmPostTP1Ladder ("exhausted"). Price recovered shortly after — refusal saved a likely SL hit.

7. **Tester paused since 19:48 local time** — sim time stopped at May 5 23:55 UTC; remaining May 6 + May 7 not yet evaluated. Run still has runway if resumed in MT5.

---

## Session Log

| Local UTC | Sim time | Event |
|---|---|---|
| 2026-05-10 19:11 | — | Run 12 started, FORGE v2.7.13, $10K balance |
| 19:14 | Apr 29 11:00 | Tick 1: 1,779 signals, 0 TAKEN |
| 19:18 | Apr 29 16:35 | Tick 2: 2,774 signals, 0 TAKEN |
| 19:22 | Apr 30 11:30 | Tick 3: 2,990 signals, **G5001 SELL fired** (+$23.03) |
| 19:25 | May 1 07:45 | Tick 4: 5,552 signals, G5002 BUY fired (+$112.80) |
| 19:35 | May 4 14:00 | Tick 5: 11,900 signals, G5003 + G5004 (May 1) + G5005 (May 4) fired |
| 19:40 | May 4 17:10 | **G5008-pattern entry BLOCKED** by `adx_spike_sell` |
| 19:45 | May 5 16:00 | Tick 6: 14,000+ signals, +$506.63 confirmed |
| 19:50+ | May 5 23:55 | Tester paused. DB lock workaround via /tmp snapshot |

---

## Action Items

- [ ] **Decide**: resume Run 12 to May 7 OR mark complete and start Run 13 with v2.7.14
- [ ] **Run 13** (v2.7.14): validate H1 bypass unlocks Apr 29 15:55/16:00 SELLs + flood throttle works
- [ ] **Run 14** (post-13): disable `session_ny_sell_cutoff_utc=0` if Run 13 stays clean
- [ ] **Code change for v2.7.15**: ADX-conditioned `rsi_buy_ceil` (currently 0% precision)
- [ ] **Code change for v2.7.15**: populate `m15_adx` in SKIP-row logging (forensics improvement)
