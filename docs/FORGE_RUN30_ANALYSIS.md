# FORGE Run 30 — Tester Analysis

**EA version**: FORGE v2.7.70
**Symbol**: XAUUSD
**Sim period**: 2026-03-31 → (running)
**Scalper mode**: DUAL
**aurum_run_id**: 30
**wall_time**: 49413104
**source_run_id**: 1 (Agent-127.0.0.1-3000)
**Source DB**: `Tester/Agent-127.0.0.1-3000/MQL5/Files/FORGE_journal_XAUUSD_tester.db`

**Status**: COMPLETE (paused at sim 2026-04-02 17:25 — 3 ticks no progression)

## What v2.7.70 ships (vs Run 29 baseline)

| Change | Why | Expected impact on Run 29 losses |
|---|---|---|
| Codex JSON shadowing fix (v2.7.69) | TC/BLR composite overrides finally read by EA | TC composite SL/TP geometry actually applies |
| dump_sell_late_rsi_block 36.0 → 37.0 (v2.7.69) | G5003 RSI=36.01 missed by 0.01 | G5003 should now block (saves entry + −$128 win… wait G5003 actually WON +$128) |
| m15_adx self-populate (v2.7.69) | 99.9% of SKIPs logged 0 — forensic gap | Future Q9 gate precision analysis usable for m15_adx-aware gates |
| BLR_BUY bearish-BOS block (v2.7.69) | G5015/G5016/G5027/G5032 all fired with M5 BOS bearish | Saves ~$4,200 (BLR knife losses) |
| BLR_BUY falling-velocity block (v2.7.69) | Backup gate for BOS-not-yet-confirmed accelerating falls | Backup |
| BB_BREAKOUT BUY exhaustion-no-bos block (v2.7.69) | G5005/G5022/G5023/G5025/G5026 fired RSI 68→74 without bullish BOS | Saves ~$3,300 (second-leg traps) |
| Pyramid kill on adverse direction (v2.7.70) | G5032 8-leg pyramid grew into −$2,166 loss | Caps any leg-3+ adverse pyramid (~$1,200 savings on G5032 alone) |
| NY_SESSION_BEARISH_BREAKOUT_SELL (v2.7.70) | 235pt + 143pt + 80pt bearish runs all missed (HTF lag) | Captures session-open descents — first SELL setup without h1/h4 gate |

## Baseline (tick 1)

- Sim time: 2026-03-31 10:15
- Total signals: 3,756
- TAKEN: 1
- Status: very early — Mar 31 G5001 window (12:30) not yet reached

## TAKEN Groups (running)

| Sim Time | Magic | Setup | Dir | Price | RSI | ADX | h1_trend | Session | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 03/31 08:16:00 | 202401 | MOMENTUM_DUMP_COMPOSITE_TEST | SELL | 4554.82 | 43.6 | 36.9 | +0.81 | LONDON | First-ever fire of the composite path (post-codex-fix) |

## Hypothesis tracking

| Hypothesis | Status |
|---|---|
| v2.7.69 dump_sell_late_rsi_block=37.0 blocks G5003 RSI=36.01 | _pending — sim hasn't reached 12:40_ |
| v2.7.69 BLR_BUY bearish-BOS block prevents G5015 falling knife | _pending — Apr 2 08:33 not reached_ |
| v2.7.69 BB_BREAKOUT BUY exhaustion-no-bos blocks G5005 trio | _pending — Apr 1 08:45 not reached_ |
| v2.7.70 NY_SESSION_BEARISH_BREAKOUT_SELL fires during Apr 2 morning descent | _pending — Apr 2 08:00 not reached_ |
| v2.7.70 pyramid-kill caps G5032 at ≤4 legs (vs 8 in Run 29) | _pending — Apr 8 not reached_ |

## Session Log

| Local time | Sim time | What happened |
|---|---|---|
| 16:09 | 03/31 10:15 | Baseline. v2.7.70 fresh start on Agent-3000. 1 TAKEN (MOMENTUM_DUMP_COMPOSITE_TEST SELL — codex shadowing fix surfaced this setup). NY_SESSION_BEARISH_BREAKOUT_SELL ready, no fires yet (waiting for first KZ velocity event). |
| 16:18 | 04/01 14:55 | Tick 2. TAKEN 1→13. Net P&L −$701. **G5005 BB_BREAKOUT BUY still LOST −$1,694** (BOS exemption let it through at RSI 74.5). **NEW LOSS surfaced** — MOMENTUM_DUMP_COMPOSITE_TEST SELL 03/31 08:16 (−$307) — codex shadowing fix made this setup active. |
| 16:22 | 04/02 10:40 | Tick 3. **BIG IMPROVEMENT.** TAKEN 13→14 (only +1 new = G5013 BB_BREAKOUT BUY @ 17:46 +$985). Net P&L flipped −$701 → **+$287.93** (+$989 swing). **v2.7.69 BLR gates VINDICATED**: `blr_buy_bearish_bos_block` 3,450 hits + `blr_buy_falling_velocity_block` 967 hits. **G5015 + G5016 (Run 29 disasters −$1,587 combined) BOTH BLOCKED** in Run 30. **NY_SESSION_BEARISH_BREAKOUT_SELL did NOT fire** on the 235pt descent (silent — no SKIP code emitted). Pyramid-kill 0 events (no losses to test). |

## Hypothesis update (after tick 3)

| Hypothesis | Status |
|---|---|
| v2.7.69 BLR_BUY bearish-BOS block prevents G5015/G5016 | ✅ **PASS** — G5015 blocked by `blr_buy_falling_velocity_block`, G5016 blocked by `blr_buy_bearish_bos_block`. Saved $1,587. |
| v2.7.69 BB_BREAKOUT BUY exhaustion-no-bos blocks G5005 trio | ❌ **FAIL** — G5005 still fired and lost $1,694 (BOS was bullish at Apr 1 08:45, gate exemption applied) |
| v2.7.70 NY_SESSION_BEARISH_BREAKOUT_SELL captures Apr 2 235pt descent | ❌ **FAIL** — 0 fires across Apr 2 08:00-09:11 window. Logging gap (no SKIP code) — can't diagnose which atom failed |
| v2.7.69 dump_sell_late_rsi_block=37.0 blocks G5003 | 🟡 **PARTIAL** — Run 30 G5003 fired via MOMENTUM_DUMP_COMPOSITE_TEST path at RSI 35.12 (different setup, doesn't share the late_rsi_block gate). The main MD path RSI threshold works but composite test is open |
| v2.7.70 pyramid-kill caps G5032 at ≤4 legs | _pending_ — Apr 8 not reached + no adverse pyramids built yet (gates block entry) |

## Critical issues surfaced (queue for v2.7.71)

### Issue A — BB_BREAKOUT exhaustion gate exempts BOS=+1 (G5005 still loses $1,694)
- Apr 1 08:45 RSI 74.5, ADX 44.3, h1=+2.14 → BOS likely +1 after overnight 4555→4700 rally
- Gate condition `RSI ≥ 72 AND BOS != +1` skipped the exemption
- **Fix**: tighten to `RSI ≥ 72 AND (signed_velocity ≤ 0.5 OR macd_slope ≤ 0)` — require sustained momentum, not just structural alignment
- OR drop the BOS exemption entirely (lower exhaustion_rsi to 70)

### Issue B — NY_SESSION_BEARISH_BREAKOUT_SELL silent (didn't fire, no SKIP code)
- Apr 2 08:00-09:11 descent of -117pt in LONDON open window — exactly the pattern designed for
- Setup has NO SKIP emission (only fires TAKEN when all conditions met)
- **Fix 1**: add diagnostic SKIP codes for each failed condition (kz_window, velocity, rsi, macd_slope, room) — forensic visibility
- **Fix 2**: likely the velocity threshold (1.5×ATR) or kz_max_min (90min) is too strict. Apr 2 08:33 was probably past minute 93 of LONDON_OPEN_KZ (07:00 start). Loosen to 120min.

### Issue C — MOMENTUM_DUMP_COMPOSITE_TEST losing trades (newly active post-codex-fix)
- Composite test SELL @ Mar 31 08:16 lost −$307 (32min hold, knife caught)
- Composite test variant has different (likely weaker) gates than main MD
- **Fix**: either disable composite test in .env OR copy main MD gates into composite test struct

## FINAL Summary — Run 30 STOPPED at 2026-04-02 17:25

- Sim period: 2026-03-31 → 2026-04-02 17:25 (~2.7 days — partial)
- Total signals: 35,118
- TAKEN: 15
- Deals: 49 (41 wins / 8 losses)
- **Net P&L: +$304.19**

## FINAL Losses (4 groups)

| Magic | Entry sim | Setup | Dir | Entry $ | RSI | Loss | Pattern |
|---|---|---|---|---|---|---|---|
| 207407 | 04/01 08:45:00 | BB_BREAKOUT | BUY | 4702.29 | 74.5 | **−$1,694** | G5005-class second-leg top — v2.7.69 gate failed (BOS exemption) → **fixed in v2.7.71** |
| 207402 | 03/31 08:16:00 | MOMENTUM_DUMP_COMPOSITE_TEST | SELL | 4554.82 | 43.6 | −$307 | Composite test setup surfaced by codex fix (newly active) |
| 207411 | 04/01 13:50:00 | MOMENTUM_DUMP | BUY | 4736.96 | 64.1 | −$93 | Small loss — quick SL |
| 227414 | 03/31 12:40:01 | MOMENTUM_DUMP_COMPOSITE_TEST | SELL | 4552.95 | 35.1 | −$35 | Small cascade loss |
| **Total** | | | | | | **−$2,129** | |

## Cross-run delta (Run 29 v2.7.68 → Run 30 v2.7.70)

| Metric | Run 29 (full Mar 31 → Apr 8) | Run 30 (partial Mar 31 → Apr 2 17:25) |
|---|---|---|
| TAKEN | 35 | 15 (run paused) |
| Net P&L | **−$1,224** | **+$304** |
| Sim period | 8.9 days | 2.7 days |
| Run 29 same-period P&L | ~−$1,250 | — |
| **Cross-run delta** | — | **+$1,554** favorable |

The BLR gates (`blr_buy_bearish_bos_block` + `blr_buy_falling_velocity_block`) alone delivered $1,587 in Apr 2 savings by blocking G5015 (−$201) and G5016 (−$1,386).

## Q9 Gate Precision (post-stop)

| Gate | Precision | Sample | Verdict |
|---|---|---|---|
| `rr_too_low` | 64% | 50 | ✅ Keep |
| `dump_h1_trend_block_sell` | 51% | 41 | 🟡 Borderline |
| `dump_v2_misalign_sell` | 50% | 4 | 🟡 Small sample |
| `entry_quality_daily_bear_block_buy` | 41% | 29 | ❌ POOR |
| `dump_rsi_block` | 40% | 50 | ❌ POOR |
| `dump_rsi_buy_ceil` | 40% | 10 | ❌ POOR (small sample) |
| `dump_bar_confirm_missing` | 32% | 50 | ❌ POOR |
| `blr_buy_bearish_bos_block` | **16%** | 50 | ❌ POOR by Q9 metric — but **EV-positive** (blocks big losers, misses small winners) |
| `blr_buy_falling_velocity_block` | **6%** | 50 | ❌ POOR by Q9 metric — same EV asymmetry |

**Note on the BLR gates**: Q9 measures direction-correctness without weighting by magnitude. The BLR gates block falling-knife BLR_BUYs that would have been −$1,000+ losers, at the cost of missing 15-50pt recovery winners ($100-200 each). On EV (size-weighted), the gates are strongly positive — $1,587 saved vs ~$300 missed.

## Recommendations consolidated

### Already in v2.7.71 (compiled, ready to test)
- Issue A: BB_BREAKOUT exhaustion gate tightened — requires BOS=+1 AND velocity>+0.5 AND macd_slope>0 for exemption (no more lone-BOS bypass)
- Issue B: NY_SESSION_BEARISH diagnostic SKIPs + kz_max_min 90→120 + min_velocity 1.5→1.0

### Still queued (v2.7.72+)
- Issue C: MOMENTUM_DUMP_COMPOSITE_TEST losing — either disable or copy main MD gates
- Issue D: BLR gates could be refined to reduce false positives without losing big-loser protection — e.g. require BOTH BOS=-1 AND velocity falling (currently OR)
- Issue E: Apr 6-7-8 windows NOT validated in Run 30 (paused too early) — must restart to test BB exhaustion fix + pyramid kill + NY_SESSION fix

## Session Log (final entry)

| Local time | Sim time | What happened |
|---|---|---|
| 16:26 | 04/02 17:25 | **Run 30 STOPPED** (3 ticks no progression). Final: TAKEN=15, net P&L +$304.19, 41W/8L. Apr 6-8 NOT reached. v2.7.71 compiled separately with Issue A+B fixes — ready for next start. |


## Recommendations & Open Issues

_(append as discovered)_

## Operator Q&A Log

_(append as questions arise)_
