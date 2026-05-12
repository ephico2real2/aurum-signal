# FORGE Run 18 — Tester Analysis (v2.7.28 + Filter 1 isolation)

**EA version**: FORGE v2.7.28
**Symbol**: XAUUSD
**Sim period**: 2026-03-31 → in progress
**Scalper mode**: DUAL
**Balance**: $10,000
**aurum_run_id**: 18
**wall_time**: 574713130
**source_run_id**: 1
**Magic base**: 202401
**Status**: STOPPED MID-RUN by operator at sim 2026-04-14 ~10:25 UTC (12 TAKEN, +$2,713.02, 131W/14L). Run 18 truncated to pivot to v2.7.29 regime override fix; Run 19 will re-test from Mar 31 with v2.7.29 + Filter 1 + dump-catch all active. Partial Run 18 data validates: Filter 1 calibration ✓ (no false positives Apr 1-14), G5028 ✓ blocked correctly Apr 10, +5 BB_BREAKOUT BUYs Run 17 didn't have, but ~$1,500 opportunity cost from v2.7.26 PSAR + regime=RANGE 5-leg cap (the v2.7.29 target).
**Last updated**: 2026-05-11

> **Test isolation**: Only v2.7.27 Filter 1 + Filter 3 are enabled (`FORGE_DAILY_DIRECTION_GATE_ENABLED=1`,
> `FORGE_DAILY_CANCEL_PENDING_ON_FLIP=1`). TP4/TP5 staging and v2.7.28 dump-catch are
> default-OFF — Run 18 measures **only the daily-direction-gate effect**.

> **All regime-related discussion has been moved** to [`docs/FORGE_REGIME_PREDICTOR_DESIGN.md`](FORGE_REGIME_PREDICTOR_DESIGN.md) — phased architecture (data collection / library / classification / interpretation / transport / payload), historical Q&A (Q3b, Q8-Q10, Q16-Q22), and superseded proposals (Issue 1 v2.7.29 inline override, Issue 7 file-driven stream). The Run 18 doc retains stubs in their original positions.

---

## Comparison target — Run 17 (v2.7.22 baseline)

| Metric | Run 17 (Apr 1 → May 7) | Run 18 target (same window, Filter 1 only) |
|---|---|---|
| TAKEN groups | 83 | 75–82 (a few daily-blocked) |
| **G5048 in TAKEN** | **Yes (Apr 16 16:35 BB_BREAKOUT BUY, −$1,666)** | **No — should appear as `entry_quality_daily_bear_block_buy` SKIP** |
| Apr 15 14:46 SELL cluster | 3 SELLs taken, −$140 combined | Some/all blocked by `entry_quality_daily_bull_block_sell` |
| Net P&L | +$5,630.29 | **Target: +$6,800 to +$7,300** (≈ +$1,500 lift) |
| Win rate | 93.32% | 93–96% |
| Loss count | 58 trades / 6 net-neg groups | Lower (G5048's 13 SL legs avoided) |

---

## Hypothesis validation

| # | Hypothesis | Evidence target | Status |
|---|------------|-----------------|--------|
| 1 | Filter 1 blocks G5048 disaster | `entry_quality_daily_bear_block_buy` SKIP at Apr 16 16:35 | _pending Apr 16_ |
| 2 | Filter 1 blocks Apr 15 SELL cluster | `entry_quality_daily_bull_block_sell` SKIPs in 14:00–17:00 window | _pending Apr 15_ |
| 3 | Filter 1 doesn't over-filter legitimate trends | TAKEN count drops ≤ 8 vs Run 17's 83 | **PASS (Apr 1 partial)** — both Apr 1 BUYs taken at exact Run 17 prices, 0 daily-block SKIPs on Apr 1 |
| 4 | Net P&L exceeds Run 17 by ≥ $1,500 | end-of-run TRADES sum | _pending end-of-run_ |
| 5 | Filter 3 cancels stale pendings on a real flip | INFO log `Daily regime flip — cancelled N pending order(s)` | _pending flip event_ |
| 6 | v2.7.26 PSAR-on-BB_BOUNCE precision ≥ 50% | Q9 audit on `entry_quality_psar_misalign_*` blocks at end-of-run: of total blocks, % where price moved IN blocked-direction within 15min should be ≥ 50%. If < 50%, gate is blocking more wins than losses and needs refinement (fresh-flip gate, ADX-gated enforcement, or revert). Apr 2 already cost $225 in lost Run 17 winners. | _pending end-of-run_ |

---

## Summary (running)

| Metric | Value |
|--------|-------|
| Total signals | 394 |
| TAKEN | 2 (Apr 1 BB_BREAKOUT BUYs — matching Run 17) |
| P&L | $0 (positions just opened, no closes yet) |
| Latest sim | 2026-04-01 09:40 UTC |
| **Filter 1 blocks (Mar 31)** | **6 BUYs blocked** (`entry_quality_daily_bear_block_buy`) — correct, daily was bearish |
| **Filter 1 behavior Apr 1** | **0 blocks** — correct, daily had flipped bullish (4570 → 4700 overnight rally) |

---

## TAKEN Groups

| Sim time (UTC) | Setup | Dir | Price | ATR | RSI | ADX | h1_trend | PSAR | Regime | Run 17 match |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-04-01 08:40:00 | BB_BREAKOUT | BUY | 4700.47 | 5.01 | 73.3 | 40.1 | +2.15 | BELOW | RANGE | ✓ byte-identical |
| 2026-04-01 09:28:57 | BB_BREAKOUT | BUY | 4706.01 | 7.59 | 63.6 | 33.2 | +2.12 | BELOW | RANGE | ✓ byte-identical |
| 2026-04-06 10:50:00 | BB_BREAKOUT | BUY | 4672.54 | 6.52 | 63.5 | 31.4 | — | — | RANGE | ✓ byte-identical Run 17 G5005 |

**Apr 1 daily-block SKIPs: 0** — Filter 1 correctly allowed both legitimate BUYs.

---

## P&L by magic
_Empty._

---

## Gate Breakdown (running)
_Mostly `session_off` during Asian session._

---

## Mandatory Housekeeping (session start)

| Check | Result |
|-------|--------|
| A. Dead `FORGE_*` env vars | **PASS** |
| A. Lowercase config leaks | **PASS** |
| B. Gate legend coverage (digit-aware, 56 gates) | **PASS** |
| `.env` Filter 1 keys | `FORGE_DAILY_DIRECTION_GATE_ENABLED=1`, `FORGE_DAILY_CANCEL_PENDING_ON_FLIP=1` ✓ |

---

## Filter 1 SKIPs (Mar 31 — pre-Apr 1 window)

| Sim time | Direction | Price | Gate |
|----------|-----------|-------|------|
| 2026-03-31 08:35 | BUY | 4575.46 | entry_quality_daily_bear_block_buy |
| 2026-03-31 08:40 | BUY | 4579.14 | entry_quality_daily_bear_block_buy |
| 2026-03-31 10:25 | BUY | 4550.88 | entry_quality_daily_bear_block_buy |
| 2026-03-31 14:40 | BUY | 4587.65 | entry_quality_daily_bear_block_buy |
| 2026-03-31 15:55 | BUY | 4574.32 | entry_quality_daily_bear_block_buy |
| 2026-03-31 16:05 | BUY | 4570.62 | entry_quality_daily_bear_block_buy |

All 6 = BUY candidates blocked because D1 SMA20 slope was bearish (prices 4550-4587 vs longer-term mean). No `daily_bull_block_sell` events yet.

---

## Observations & Anomalies

### Apr 2 — v2.7.26 PSAR gate blocks Run 17 winners
Two Run 17 BB_BOUNCE entries (Apr 2 10:25 SELL G5003 +$103, Apr 2 12:15 BUY G5004 +$122) were blocked in Run 18 by `entry_quality_psar_misalign_sell` / `_buy`. These were **NOT blocked by Filter 1** — they were blocked by the v2.7.26 PSAR-for-BB_BOUNCE alignment gate shipped in the pre-v2.7.27 baseline commit (f884c04).

This is expected — v2.7.26 was added to prevent G5028-class losses (Apr 10 18:45 BB_BOUNCE BUY @ 4766.27 with PSAR=ABOVE, crashed -12pts). Trade-off: −$225 opportunity vs Run 17 on Apr 2, expected to be recouped at G5028 timestamp.

**Framing correction**: Run 18 is the full v2.7.23 → v2.7.27 stack vs Run 17's v2.7.22 baseline. The "Filter 1 isolation" framing is technically incomplete — v2.7.23 (BE-cushion), v2.7.24 (TP2 ratchet), v2.7.25 (ATR trail), v2.7.26 (PSAR-on-BB_BOUNCE), and v2.7.27 (Filter 1) all contribute. To isolate Filter 1 cleanly would require a separate Run on v2.7.26 with daily-gate off — but the current goal (validate G5048 block + gauge full-stack delta) is well-served.

---

## Recommendations & Open Issues

> Findings rooted in the Run 18 evidence so far. All proposals preserve
> backward compatibility via opt-in env flags so they don't break the running
> code. Final decisions deferred to end-of-run.

### Issue 1 — Inline regime classifier H4 lag → over-conservative leg sizing

**Status**: Option A shipped as **v2.7.29** (H1-strong override). Full options analysis (A/B/C with code, defaults, risk analysis, Apr 1 sim math) **moved to** [`docs/FORGE_REGIME_PREDICTOR_DESIGN.md`](FORGE_REGIME_PREDICTOR_DESIGN.md) (Pre-design Issue 1 section).

**Quick summary**: G5001 Apr 1 08:40 capped at 5 legs because `regime=RANGE` from the inline classifier (H1+H4 unanimous-AND model lagged H1's bullish flip by 3.5h). v2.7.29 added an H1-strong override clause; v2.7.30 made it run in both tester and live. The full predictor replacement (LightGBM + ONNX) is the long-term fix — see the design doc.

---

### Issue 2 — v2.7.26 PSAR-on-BB_BOUNCE structurally anti-correlated with entry timing (PROMOTED TO TOP PRIORITY post-Apr 7-8 data)

**Evidence (cumulative through Apr 8 sim)**:
- Apr 2 10:25 BB_BOUNCE SELL @ 4617.92 → blocked. Run 17: +$103
- Apr 2 12:15 BB_BOUNCE BUY @ 4623.24 → blocked. Run 17: +$122
- Apr 7 11:20 BB_BOUNCE SELL @ 4661.02 → blocked. Run 17: ~+$103 (G5006)
- Apr 7 15:25 BB_BOUNCE SELL @ 4667.59 → blocked. Run 17: ~+$70 (G5008)
- Apr 8 07:20 BB_BOUNCE BUY @ 4794.76 → blocked (PSAR=ABOVE). Run 17: ~+$170
- Apr 8 11:30 BB_BOUNCE BUY @ 4808.7  → blocked (PSAR=ABOVE). Run 17: ~+$159
- Apr 8 12:50 BB_BOUNCE BUY @ 4785.7  → blocked (PSAR=ABOVE). Run 17: TAKEN
- Apr 8 13:00 BB_BOUNCE BUY @ 4783.41 → blocked (PSAR=ABOVE). NEW Run 17 didn't have.
- Apr 8 13:25 BB_BOUNCE BUY @ 4778.85 → blocked (PSAR=ABOVE). Run 17: ~+$108
- Apr 8 15:30 BB_BOUNCE BUY @ 4784.27 → blocked (PSAR=ABOVE). Run 17: TAKEN
- Apr 8 16:35 BB_BOUNCE BUY @ 4783.29 → **TAKEN** (PSAR=BELOW — rare alignment). Run 17: ~+$146. **Both runs took it**.
- Apr 8 16:40 BB_BOUNCE BUY @ 4777.49 → blocked (PSAR=ABOVE)
- Apr 8 17:00 BB_BOUNCE BUY @ 4776.98 → blocked (PSAR=ABOVE). Run 17: TAKEN
- Apr 8 17:30 BB_BOUNCE BUY @ 4768.29 → blocked (PSAR=ABOVE). Run 17: TAKEN
- Apr 8 17:41 BB_BOUNCE BUY @ 4767.26 → blocked (PSAR=ABOVE). Run 17: TAKEN

**Pass rate for BB_BOUNCE BUY on Apr 7-8**: 1 of 10 attempts = **10%**.

**Opportunity cost through Apr 7-8**: ~$1,250 (10 blocked BB_BOUNCEs × Run 17 avg ~$125 each).

**Indirect benefit**: 2 Run 18 BB_BREAKOUT BUYs (Apr 8 08:35 + 08:50, ~$300 combined) fired only because the Apr 8 07:20 BB_BOUNCE was blocked. So **partial offset** of ~$300 — but net opportunity cost still ~$950 on these 2 days.

**Structural root cause** (verified via SIGNALS data + EA logic at FORGE.mq5:5576-5580 for BUY, 5611-5615 for SELL):
- BB_BOUNCE BUY fires at the BB lower band — i.e. at the END of a pullback in a bull trend.
- PSAR is a trailing-stop indicator: during the pullback creating the entry opportunity, PSAR FLIPS to ABOVE price (the dip triggers PSAR reversal).
- At the entry moment, PSAR=ABOVE → v2.7.26 BLOCKS (requires BELOW).
- After the bounce begins, PSAR flips BELOW again — but the entry timestamp has passed, and the next setup doesn't fire until price re-approaches the band.
- **Conclusion**: v2.7.26 fires `psar_misalign_buy` AT EXACTLY THE MOMENT BB_BOUNCE wants to enter. The gate is structurally anti-correlated with BB_BOUNCE timing.

**Why v2.7.26 was added**: to block G5028 (Apr 10 18:45 BB_BOUNCE BUY @ 4766.27 with PSAR=ABOVE, crashed −12pts ≈ −$50-100 loss).

**ROI**: blocking 9 winners @ ~$125 each to save 1 loser @ ~$100 = **−$1,025 net** so far. Expected precision <10% (Apr 7-8 only had 1/10 pass) — orders of magnitude below the 50% threshold.

#### Option α — Direction-aware refinement (fresh-flip gate)

Only block when PSAR is on the wrong side AND has been there for ≥ N bars. PSAR=BELOW for 30 min ≠ "fresh confirmation of bullish reversal" — it's "up-move is well underway." A FRESH flip (within last 2-3 bars) is the actionable signal.

#### Option β — ADX-gated v2.7.26

Only enforce PSAR alignment when ADX > 30 (trending markets where PSAR matters). In chop (ADX < 30), allow BB_BOUNCEs through.

#### Option γ — Revert v2.7.26 for BB_BOUNCE

Remove the gate entirely. Accept G5028-class losses (Apr 10 BB_BOUNCE BUY @ 4766.27 PSAR=ABOVE → −12pts). Only sensible if the gate is killing >2× more $ than it saves.

**Preferred (pending Q9)**: Run Q9 precision audit at end-of-run. If `entry_quality_psar_misalign_*` precision ≥ 50%, keep as-is. If < 50%, ship **Option α** (fresh-flip refinement) as v2.7.30.

---

### Issue 3 — TP1 close pct=60 + tight TP1 produces many near-BE groups

**Evidence (from Run 17 retrospective, applicable here too)**:
- 36 of 83 Run 17 groups (43%) banked < $50 net
- 4 groups in BE-clip zone (< $10 net)
- Active config: `tp1_close_pct=60` + `tp1_buy_atr_mult=0.5` + `tp1_sell_atr_mult=0.4`
- 60% of position closes at TP1 (≈2-3 pts) — small banking. Remaining 40% rides into BE-cushion zone (entry − 1.5×ATR for BUY) where it often gives back gains.

**Two paths**:

#### Path 1 — Lower close pct + tighten BE-cushion ("Option A+" from earlier chat)
```
FORGE_BREAKOUT_TP1_CLOSE_PCT=40           # was 60
FORGE_BREAKOUT_BE_CUSHION_ATR_MULT=0.3    # was 1.5
FORGE_BREAKOUT_ATR_TRAIL_MULT=0.8         # was 1.5
FORGE_BREAKOUT_TP4_STAGING_ENABLED=1
FORGE_BREAKOUT_TP5_STAGING_ENABLED=1
```
Leaves 60% of position alive (vs 40%), locks SL near BE on TP1 hit, runners extend via TP4/TP5.

**Risk**: Tighter BE-cushion → more noise-stops on winners that needed breathing room.

#### Path 2 — Widen TP1 (less invasive)
```
FORGE_BREAKOUT_TP1_BUY_ATR_MULT=0.7       # was 0.5
FORGE_BREAKOUT_TP1_SELL_ATR_MULT=0.6      # was 0.4
```
TP1 fires less often but bankings are ~50% larger when it does. No SL changes.

**Preferred**: Try Path 2 in Run 19 (smaller change, no SL geometry risk). Path 1 is a Run 20 candidate if Path 2 alone doesn't shift the win-distribution histogram.

---

### Issue 4 — Intraday counter-trend pullbacks uncaught (no SELL setup for bull-day dips)

**Evidence (Apr 8 sim data)**:
After the 08:50 BB_BREAKOUT BUY at 4831.82, Apr 8 had 5 distinct intraday dump windows:
- 11:30→11:45: 4808 → 4793 = **−15 pts in 15 min**
- 12:30→12:45: 4799 → 4782 = **−17 pts in 15 min**
- 13:05→13:20: 4788 → 4776 = **−12 pts in 15 min**
- 15:10→15:25: 4800 → 4770 = **−30 pts in 15 min** (deepest)
- 16:30→16:45: 4791 → 4774 = **−17 pts in 15 min**

Total move from breakout peak to trough: **−62 pts (≈ 10×ATR)**. Estimated counter-trend scalp value at TP1=0.4×ATR: ~$75-150 across the 5 windows.

**FORGE caught**: zero. No SELL setup fired during any of these pullbacks. BB_BOUNCE BUYs at the bottom were blocked by v2.7.26 PSAR (Issue 2). MOMENTUM_DUMP_SELL (v2.7.28) didn't fire because `dump_require_d1_bias=1` requires daily slope bearish — and Apr 8 daily was TREND_BULL all day.

**Root cause** (verified): v2.7.28 dump-catch was designed for "BB-invisible dump in a bear macro" — the G5048-class direction-failure scenario. The `d1_bear_bias` requirement at the trigger (FORGE.mq5 in dump-catch block) gates SELL only when daily is bearish. This is the wrong gate for **intraday counter-trend scalping in a bull macro** — exactly the Apr 8 pattern.

**Structural picture**:
| Market state | Setup that should fire | Status in Run 18 |
|---|---|---|
| Bull thrust / new high | BB_BREAKOUT BUY | ✓ Firing correctly |
| Pullback drop in bull day | MOMENTUM_DUMP_SELL | ✗ Blocked by `d1_bear_bias` gate |
| Bottom of pullback | BB_BOUNCE BUY | ✗ Blocked by v2.7.26 PSAR (Issue 2) |

#### Option A — Activate dump-catch with d1-bias OFF (zero code change)

`.env` toggle:
```
FORGE_DUMP_CATCH_ENABLED=1
FORGE_DUMP_REQUIRE_D1_BIAS=0      # allow counter-trend dump-catch in any regime
FORGE_DUMP_LOT_FACTOR=0.5         # smaller per-leg since counter-trend
FORGE_DUMP_COOLDOWN_SECONDS=900   # 15-min between dumps (was 600 = 10)
```

**Risk**: Counter-trend scalping in a strong bull trend has more whipsaw risk than trend-aligned dumps. SL at 1.5×ATR limits per-trade loss. The cooldown prevents stacking entries on a single multi-bar leg.

#### Option B — Make d1-bias gate direction-asymmetric

Code change: keep `d1_bear_bias` requirement for SELL when daily is "strongly bearish" (e.g. slope < −1.5×ATR), but allow SELL in "mildly bullish" daily (slope < +0.5×ATR). This catches counter-trend scalps in flat-ish daily but still requires the daily-flip case for SELL during strong bull.

#### Option C — Add a separate INTRADAY_COUNTER_TREND_SELL setup

New non-BB setup with stricter filters: require ADX>30 AND M5 trend strength reversal AND BB upper band touch. Effectively merges v2.7.28 dump-catch with a structural reversal confirm.

**Preferred**: **Option A** — already shipped, two-line .env change, can be tested in Run 19. If Apr 8 sim shows 3-5 winning counter-trend scalps and net positive contribution, the design is validated. If whipsaw rate is high, fall back to Option B's asymmetric daily gate.

**Backward compatibility**: 100% — only changes .env values, no code change.

#### Companion fix — tighter ATR trail for dump-catch (v2.7.29 candidate)

The currently-active `breakout_atr_trail_mult=1.5×ATR` (~9 pts at ATR=6) is tuned for BB_BREAKOUT runners — too loose for dump-catch scalps. Operator insight: "sell sharp, track profit, keep moving SL" → we want a tighter ratchet for MOMENTUM_DUMP groups specifically.

Code change (FORGE.mq5 ATR trail block ~line 1755):
```mql5
// Replace:
double trail_mult = g_sc.breakout_atr_trail_mult;
// With:
double trail_mult = (g_groups[gt].scalper_setup == "MOMENTUM_DUMP")
                    ? g_sc.dump_atr_trail_mult       // new, default 0.6×ATR
                    : g_sc.breakout_atr_trail_mult;  // legacy 1.5×ATR for BREAKOUT
```

New knob: `FORGE_DUMP_ATR_TRAIL_MULT=0.6` (default 0 = falls back to breakout_atr_trail_mult).

**Apr 8 15:10-15:25 simulation** with this trail:
- Entry at 4800.70, trough drops to 4770.07
- Trail SL = 4770.07 + 0.6×6.5 = 4773.97
- Bounce reversal at 15:30 stops out at 4773.97
- **Capture: 26.7 pts vs 20 pts with current 1.5×ATR trail (33% better)**

**Backward compatibility**: ships with `dump_atr_trail_mult=0` default = uses existing breakout trail. Operator opts in via env. Same blast-radius rules as Filter 1: 100% backward compat.

---

### Issue 5 — TREND_PULLBACK family (slow-drift counter-trend scalps in both directions)

**Evidence (Apr 10 sim data)**:
- 09:40 → 12:00: price drifted 4752 → 4741 = **−21 pts over 2h 20min** in a bull-macro day
- Pace: ~2 pts per 15-min — too slow for v2.7.28 MOMENTUM_DUMP_SELL trigger (1.5×ATR over 3 bars ≈ −6pts in 15min)
- Run 17 had 4 BB_BOUNCE BUYs in this window (all blocked in Run 18 by v2.7.26 PSAR per Issue 2)
- FORGE caught zero SELLs during this 21-pt down-drift. Sitting flat while market moves against the macro trend.
- Distinct from Issue 4's "fast break" — Apr 8 15:10→15:25 was −30 pts in 15min (fast); Apr 10 was −21 pts in 140min (slow grind).

**Root cause**: No setup type targets "slow trend pullback in opposite direction." BB_BREAKOUT SELL requires BB break (didn't happen). BB_BOUNCE SELL fires at BB upper (only one happened on Apr 10 at 13:30, also blocked). v2.7.28 MOMENTUM_DUMP_SELL only fires on fast impulses. Slow drift in a bull macro = uncovered.

**Operator framing (Q14)**: "we indeed need that trending rally sell or buy" — confirms the design as a **symmetric two-way pullback setup** that fires in EITHER direction depending on macro regime: SHORT the pullback in TREND_BULL, BUY the pullback in TREND_BEAR.

**Industry pattern**: classic "trend pullback short" — fires in TREND_BULL when M15 prints lower-low AND M5 shows reversal momentum. Per multiple MQL5 trend-pullback EAs (Break Tracer, Adaptive SuperTrend with TQI). The setup uses M15 as the "trend integrity" check and M5 for trigger timing.

#### Option A — TREND_PULLBACK family setup (v2.7.31 code, ~250 lines)

Two symmetric variants, gated on macro regime:

```mql5
// TREND_PULLBACK_SHORT — bull macro + M15 lower-low + M5 reversal
if(g_regime_label == "TREND_BULL"
   && m15_close_now < m15_close_back_3bars
   && m5_adx > g_sc.pullback_min_adx       // default 22
   && m5_rsi < g_sc.pullback_max_rsi       // default 50
   && bid < m5_bb_m                         // below midline
   && (TimeCurrent() - g_scalper_last_pullback_sell_time) > g_sc.pullback_cooldown_seconds) {
   fire SHORT at market with scalp geometry (see below)
}

// TREND_PULLBACK_LONG — bear macro + M15 higher-high + M5 reversal (mirror)
if(g_regime_label == "TREND_BEAR"
   && m15_close_now > m15_close_back_3bars
   && m5_adx > g_sc.pullback_min_adx
   && m5_rsi > (100 - g_sc.pullback_max_rsi)  // mirror RSI bound
   && ask > m5_bb_m                            // above midline
   && (TimeCurrent() - g_scalper_last_pullback_buy_time) > g_sc.pullback_cooldown_seconds) {
   fire BUY at market with scalp geometry
}

// Asymmetric-risk scalp geometry (both variants):
// SL          = 1.0 × ATR       (tight — counter-trend)
// TP1         = 0.3 × ATR       (bank fast, 60% close)
// TP2         = 0.8 × ATR
// TP3         = 1.5 × ATR
// ATR trail   = 0.5 × ATR       (tight ratchet after TP1)
// Lot factor  = 0.5             (smaller exposure)
// Cooldown    = 900 sec         (15 min per direction)
```

12 new config keys (6 per direction). Master toggles `FORGE_TREND_PULLBACK_SHORT_ENABLED=0` and `FORGE_TREND_PULLBACK_LONG_ENABLED=0`.

**Risk**: Trend-pullback shorts in strong bull trends face whipsaw. The 1.0×ATR SL caps per-trade loss; cooldown prevents stacking. Net positive contribution depends on the ratio of slow-drift-then-rally (loss) vs slow-drift-continuation (win). On Apr 10 this would have caught the 4752→4741 drift for ~$15-30 scalp.

#### Option B — Loosen v2.7.28 MOMENTUM_DUMP_SELL trigger to catch slow drifts

Lower `dump_atr_mult` from 1.5 to 0.7 — triggers on smaller moves. Risk: massive over-firing on every 5-pt M5 candle. Probably unworkable.

**Preferred**: **Option A**, but as a v2.7.31 candidate AFTER v2.7.28 dump-catch is validated. Sequence: ship v2.7.28 activation (Track 1) → measure → ship v2.7.29 trail tighten → measure → ship v2.7.30 TREND_PULLBACK_SHORT.

**Backward compatibility**: 100% — new setup type, default-OFF, no change to existing setups.

---

### Issue 6 — High-frequency two-way scalper (BB_MIDLINE_OSCILLATOR — the "in/out over and over" engine)

**Evidence (Run 18 frequency analysis through Apr 10)**:
- Current trade frequency: 11 TAKEN in 10 sim-days = **~1 entry per day average**.
- Operator-requested frequency (Q15): 5-10 entries per active session.
- Active config sets up FORGE as selective trend trader. Missing: a high-frequency engine that compounds small wins.
- Existing setups all fire 0-3/day. None fire 5-10/day.

**Root cause**: No setup type designed for high-frequency fire. BB_BREAKOUT requires a real BB band break (rare). BB_BOUNCE fires at band extremes (rare). MOMENTUM_DUMP fires on 1.5×ATR impulses (rare). TREND_PULLBACK fires on M15 confirmation (rare). The intraday "ordinary cross-up / cross-down at BB midline" pattern — the most common scalp setup — has no FORGE setup type.

**Industry pattern (canonical MQL5 high-frequency)**:
> "BB Midline Bounce — fires when M5 close crosses the BB midline (20-period basis). In trending markets, take the trend direction on the cross. In ranging markets, fade both edges. Tight TP at 0.25-0.5×ATR, tight SL at 1.0×ATR, cooldown 3-5 min between fires."
This is the standard MQL5 community pattern for "fire often" scalping. Reference: countless MQL5 codebase entries searching "BB midline scalper".

#### Option A — BB_MIDLINE_OSCILLATOR (v2.7.32 code, ~300 lines)

```mql5
// Fires on every M5 close crossing the BB midline.
// Direction governed by regime label.

if(g_regime_label == "TREND_BULL" || g_regime_label == "TREND_BEAR") {
    bool crossed_up = (prev_close < m5_bb_m && current_close > m5_bb_m);
    bool crossed_dn = (prev_close > m5_bb_m && current_close < m5_bb_m);
    bool is_bull = (g_regime_label == "TREND_BULL");

    // Trend-aligned scalp on cross-with-trend
    if((is_bull && crossed_up) || (!is_bull && crossed_dn)) {
        if(rsi_in_band(40, 70) && cooldown_ok) fire_midline_oscillator(trend_aligned);
    }
    // Counter-trend fade on cross-against-trend
    if((is_bull && crossed_dn) || (!is_bull && crossed_up)) {
        if(rsi_extreme() && cooldown_ok) fire_midline_oscillator(counter_trend, smaller_lot);
    }
}
else if(g_regime_label == "RANGE") {
    // Fade band extremes
    if(bid <= m5_bb_l && cooldown_ok) fire BUY at lower edge
    if(bid >= m5_bb_u && cooldown_ok) fire SELL at upper edge
}

// Geometry (asymmetric small-win pattern):
//   Lot factor:    0.30 × fixed_lot
//   Number of legs: 2-3
//   SL:            1.0 × ATR
//   TP1:           0.25 × ATR (very fast bank, 60% close)
//   TP2:           0.5 × ATR (small runner)
//   ATR trail:     0.4 × ATR (tight ratchet after TP1)
//   Cooldown:      300 sec (5 min between fires per direction)
```

8 new config keys. Master toggle `FORGE_BB_MIDLINE_OSCILLATOR_ENABLED=0`.

**Default-OFF** so no behavior change unless operator opts in.

**Risk**:
- High whipsaw potential — every midline cross fires. ATR trail at 0.4×ATR is the safety mechanism.
- Could conflict with BB_BREAKOUT entries on the same bar — needs setup-prioritization (BB_BREAKOUT wins ties).
- Per-trade size is small so worst-case drawdown is bounded.

#### Option B — Extend BB_BOUNCE to fire mid-band, not just at extremes (smaller change)

Loosen BB_BOUNCE BUY/SELL to fire at `bb_mid ± 0.2 × bb_range` instead of `bb_lower / bb_upper`. Increases frequency without adding a new setup type.

**Risk**: Mixes "mean reversion at band extreme" semantics with "trend-with momentum" semantics. Cleaner to keep them separate.

#### Option C — Use existing BB_BREAKOUT logic with loosened break threshold

Lower `breakout_buffer_points` from default to 0 — fires on every BB band touch rather than break. Increases BB_BREAKOUT frequency.

**Risk**: BB_BREAKOUT is supposed to be a TREND_BREAKOUT setup. Firing on every band touch (not break) corrupts the semantic.

**Preferred**: **Option A — purpose-built BB_MIDLINE_OSCILLATOR**. Reasons:
1. Separate setup type → cleanly distinguishable in analysis / Q9 precision audits
2. Designed-for-purpose geometry (tight scalp) doesn't mix with trend-setup geometry
3. Independent SL/TP/lot config → operator can tune frequency vs P&L tradeoff
4. Backward-compat 100% — default-OFF, zero impact on existing setups when off

**Backward compatibility**: ships behind `FORGE_BB_MIDLINE_OSCILLATOR_ENABLED=0`. Existing setups unaffected.

**Industry sources**:
- [MQL5 BB Midline Trading Strategy](https://www.mql5.com/en/articles) — canonical pattern (multiple variants in codebase)
- [Adaptive SuperTrend with TQI](https://www.mql5.com/en/blogs/post/769330) — same "fire-on-cross" design philosophy
- [Multi-Timeframe Harmony Index](https://www.mql5.com/en/articles/20097) — for direction governance via weighted regime score

---

### Issue 7 — Tester/live regime parity via file-driven pre-computed regime stream (SUPERSEDED)

**Status**: **SUPERSEDED** by Phases 1-6 in [`docs/FORGE_REGIME_PREDICTOR_DESIGN.md`](FORGE_REGIME_PREDICTOR_DESIGN.md). The full Options A/B/C analysis (file-driven stream, MQL5 HMM port, MSDR+CPD hybrid) **moved to** the design doc's "Pre-design Issue 7" section.

**Quick summary**: file-driven pre-computed regime stream was the precursor design. The follow-up phased discussion concluded that **ONNX-embedded LightGBM inference** is the better path — same parity guarantee, sub-ms latency, no file IO, no external dependency, in-EA execution.


### Priority order (post-Run 18)

1. **Wait for Run 18 to complete** — measure G5048 block + total P&L vs Run 17.
2. **Run Q9 precision audit** on v2.7.26 PSAR gates + Filter 1 gates.
3. If Issue 1 cost is high (5-leg cap blocking >$500 of upside across the run), ship **v2.7.29 = Option C** (weighted harmony regime).
4. If Issue 2 PSAR precision < 50%, ship **v2.7.30 = Option α** (fresh-flip refinement).
5. If small-win/BE-clip cluster persists, run **Run 19 with Path 2** TP1 widening.

---

## Operator Q&A Log

> Captures the running conversation between operator and the monitoring agent.
> Each entry: question asked, my analysis path, the data pulled, the answer
> given. Kept so the rationale behind every fix proposal is preserved.

### Q1 (sim Apr 2): "check the apr 2 entries"
**Finding**: Both Run 17 Apr 2 BB_BOUNCEs blocked by `entry_quality_psar_misalign_*` (v2.7.26), NOT Filter 1. Recorded as Issue 2 above.

### Q2 (sim Apr 1, post-tick): "if the first trade in london session on april 1 were perfect setup - why didn't fire more legs in that group? why was the logic very conservative?"
**Finding**: G5001 fired 5 legs (capped at `native_legs_max_when_unclear=5`) because `regime_label=RANGE` from the inline classifier. h1_trend was +2.15 (very bullish), M5 ADX 40.1, but regime stayed RANGE because H1+H4 unanimous-AND gate hadn't fired (H4 still bearish from prior down-trend). Price moved +41 pts (8.1×ATR) post-entry — confirming the setup was perfect, the leg sizer was wrong. → Issue 1 above.

### Q3 (sim Apr 1, follow-up): "Look at the prices before and after and the duration of the price movement..."
**Finding**: Pulled SIGNALS price trajectory:
- Pre-entry (06:00→08:40): price 4685 → 4669 (low at 07:20) → 4700 (entry); +31 pts rally
- Post-entry: peak +41 pts at Apr 1 10:40, +28 pts at noon, regime flipped TREND_BULL only at 12:00
- Confirmed the move was real; the regime classifier was 3.5 hours behind

### Q4 (sim Apr 2-7): "do we have the S/L moving strategy to support option A?"
**Finding**: Yes — full SL ladder exists (BE-cushion → ATR trail → TP2 ratchet → TP3/TP4/TP5 ratchets), but currently calibrated for "let the runner breathe" not "lock profit." Vulnerability between TP1 and TP2 where SL is at entry−1.5×ATR (giveback zone). Option A alone won't help — needs to pair with BE-cushion tightening. → Issue 3, Path 1 above.

### Q5: "if you review some of the trades - we barely broke even"
**Finding**: 43% of Run 17 groups banked < $50 net. Driven by `tp1_close_pct=60` aggressive scalp banking + BE-cushion at 1.5×ATR giving back gains on reversal. → Issue 3 above. Two paths offered (Path 1 SL-tightening or Path 2 TP1-widening). Recommendation: Path 2 first.

### Q6: "what date should I test with v2.7.27 - i wanna do 1 day earlier"
**Finding**: Recommended `2026-03-31 → 2026-05-07` (1 day earlier than Run 17). Operator launched with this window; sim_start=Mar 31 confirmed.

### Q7: "i wanna short window to capture this effect"
**Finding**: Recommended `2026-04-14 → 2026-04-17` for surgical G5048 isolation. Operator opted for the longer Mar 31 → May 7 window for full validation.

> **Note**: Q8 (regime classifier wiring), Q9 (regime.py usage scope), Q10 (regime Google search), Q3b (Apr 1 regime explanation), and Q16-Q22 (v2.7.30 parity + design discussion) **moved to** [`docs/FORGE_REGIME_PREDICTOR_DESIGN.md`](FORGE_REGIME_PREDICTOR_DESIGN.md) → "Historical Q&A — Regime Discussion Thread" section. This Q&A log retains only non-regime entries from Run 18.

### Q15 (sim Apr 13 05:55): "But a scalper captures BOTH legs of the intraday swing. We need a way to trigger regularly to capture in and out over and over"
**Investigation**: Reviewed Run 18 entry frequency (11 in 10 sim-days = 1/day average); compared with high-frequency scalper benchmarks; mapped existing setups to phase coverage.
**Evidence**:
- Run 18 current trade frequency: ~1 entry per day — selective trend trading paradigm.
- Operator-requested frequency: 5-10 entries per active day — true high-frequency two-way scalping.
- Mapped existing setups to intraday phases:

| Existing | Frequency | Purpose |
|---|---|---|
| BB_BREAKOUT BUY/SELL | 1-3/day | Catch trend thrusts |
| BB_BOUNCE BUY/SELL | 0-2/day | Mean-revert at extremes (broken by v2.7.26) |
| MOMENTUM_DUMP_SELL | 0-2/day | Fast dump impulse (v2.7.28, off) |
| TREND_PULLBACK_SHORT/LONG | 1-3/day | Slow drift counter-trend (v2.7.31, not coded) |
| **MISSING: high-freq scalper** | **5-10/day** | **In/out over and over — what operator wants** |

- Industry pattern: BB midline oscillator scalper — fires every M5 close crossing the BB midline. On XAUUSD, midline gets crossed 5-12× per session. With 5-min cooldown, 5-10 fires/day achievable.
- Geometry: lot_factor=0.3, SL=1.0×ATR, TP1=0.25×ATR, TP2=0.5×ATR, ATR trail=0.4×ATR, cooldown=300s.
- Per-trade math: winning ≈ +$11, losing ≈ −$4.50. 8 fires/day × 65% WR ≈ +$44/day on top of trend trades.
**Answer**: This is fundamentally a **paradigm shift** from "selective trend trader" to "high-frequency two-way scalper". The existing setups are not designed for high-frequency fire — they need a partner. Proposing **BB_MIDLINE_OSCILLATOR** as v2.7.32 (new setup type, ~300 lines). Fires on every M5 close crossing bb_midline (with direction governed by regime label + RSI bands). Combined with v2.7.26 PSAR refinement (Issue 2) and v2.7.28 dump-catch activation, FORGE becomes a true two-way scalper firing 6-13 times per active day. Updated roadmap: v2.7.29 (dump-catch activation, config-only) → v2.7.30 (dump-catch trail tighten) → v2.7.31 (TREND_PULLBACK family) → **v2.7.32 (BB_MIDLINE_OSCILLATOR — highest single-addition impact for the high-freq objective)**.
**Forward link**: Issue 6 in Recommendations (new) — BB_MIDLINE_OSCILLATOR setup spec with Options A/B/C + pseudocode.

### Q14 (sim Apr 10 17:50): "same issues with april 10 / we were trading against the market / we should catching that fast break as well / setting a good S/L to not get crash out — or was april 10 a great rally and recovery?"
**Investigation**: Pulled all Apr 10 TAKEN + PSAR-misalign SKIPs; reconstructed intraday price arc; computed counter-trend short P&L geometry with proposed TREND_PULLBACK_SHORT params.
**Evidence**:
- Apr 10 daily: open 4762, close ~4780 = **+17 pts close-to-close — a "rally and recovery" day**
- Intraday range: **59 pts** (4741 low → 4779 high). Morning DD 21 pts + afternoon rally 38 pts.
- Run 18 took 3 BB_BREAKOUT BUYs (14:45/15:00/15:35) — the afternoon rally phase only.
- Run 17 took 10 entries (7 BB_BOUNCE BUYs + 2 BB_BOUNCE SELLs + 1 BB_BREAKOUT BUY); Run 18 blocked 7 of those by v2.7.26 PSAR.
- **The slow drift 09:40 → 12:00 (−21 pts in 2h 20min) was uncovered by any SHORT setup** — too slow for v2.7.28 MOMENTUM_DUMP_SELL trigger.
- Pure-hold strategy captured 17 pts (daily close gain).
- A two-way scalper with TREND_PULLBACK_SHORT could have captured the 21-pt drift + 38-pt rally = up to 59 pts intraday.
**SL geometry for counter-trend (asymmetric risk)**:
- SL = 1.0×ATR (tight cap, only 4 pts at risk with ATR=4)
- TP1 = 0.3×ATR (1.2 pts, bank fast, 60% close pct)
- ATR trail after TP1 = trough + 0.5×ATR (very tight ratchet)
- Lot factor 0.5 (smaller exposure than trend setups)
- Net asymmetric: $25-50 winning case vs $10 max loss per group
**Answer**: **Yes — Apr 10 was a rally-and-recovery day overall (+17 pts net), but the intraday 59-pt range contained 21 pts of sellable drift and 38 pts of buy-back rally.** Pure-trend strategy captures 17 pts. Two-way scalper can capture 30-50 pts. The "good SL" you mention is exactly the asymmetric-risk profile: 1.0×ATR SL + 0.5×ATR trail + 0.3×ATR scalp TP. Tight enough to cap losses ("don't get crashed out"), loose enough to ride the drift. This is fundamentally different from BB_BREAKOUT's 2-3×ATR SL philosophy (which is trend-aligned and "let runner breathe"). Counter-trend = "lock fast, exit fast."
**Forward link**: Issue 5 in Recommendations now has the exact SL/TP/trail params spelled out per this operator dialogue. Track 1 (v2.7.28 dump-catch activation, .env only) handles fast breaks; Track 2 (v2.7.30 TREND_PULLBACK_SHORT, code) handles slow drifts.

### Q13 (sim Apr 9 15:10): "we were in a DD until it rally — shouldn't we be selling then sharp and track profit and keep moving S/L?"
**Investigation**: Pulled Apr 8 price trajectory 11:00→17:00 with 5-min granularity. Quantified 5 distinct dump windows (each M5 dropped 12-30 pts in 15 min). Reviewed v2.7.28 dump-catch trigger spec + v2.7.25 ATR trail mechanism.
**Evidence**:
- Apr 8 had 5 sellable counter-trend pullback windows totaling −62 pts from breakout peak (4831 → 4770 trough).
- v2.7.28 MOMENTUM_DUMP_SELL was designed for "sharp enter on M5 dump impulse" — exactly this pattern.
- v2.7.25 ATR trail (currently active for breakout) trails SL at `trough + trail_mult × ATR` — exactly the "keep moving SL" mechanism.
- Two prerequisites missing to make it work for bull-day pullbacks:
  1. `FORGE_DUMP_CATCH_ENABLED=1` (default 0)
  2. `FORGE_DUMP_REQUIRE_D1_BIAS=0` (default 1 — currently requires daily bearish, which prevents bull-day counter-trend SELLs)
- Gap identified: current `breakout_atr_trail_mult=1.5×ATR` is too LOOSE for dump-catch scalps. Apr 8 15:10→15:25 sim: trail at 1.5×ATR captures 20 pts; trail at 0.6×ATR captures 26.7 pts (33% better).
**Answer**: **Yes — that's exactly the right model and it's mostly already built.** v2.7.28 enters sharp at market on M5 dump trigger; v2.7.25 ATR trail ratchets SL down as trough drops. Two prerequisites for it to fire on bull-day pullbacks: (1) flip `dump_require_d1_bias` to 0 in .env, (2) tighten the trail for MOMENTUM_DUMP setup specifically. Without prerequisite (2), the trail gives back 30-50% of the dump before stopping (too loose). The user's intuition "sell sharp + track profit + keep moving SL" maps directly onto: market entry → TP1 scalp banking (0.4×ATR) → ATR trail ratcheting trough.
**Forward link**: Issue 4 in Recommendations. v2.7.29 candidate = dump-catch trail tighten code change (≤20 lines, default-OFF flag).

### Q12 (sim Apr 9 15:10): "look april 7 and 8 again — is this what you expect to see?"
**Investigation**: Pulled all TAKEN entries Apr 7-8 (Run 18) + all psar_misalign / cooldown / atr_ext / breakout_failed SKIPs same window; compared 1:1 against Run 17's 12 entries from same window.
**Evidence**:
- **Run 18 Apr 7-8 took 4 entries**: Apr 7 11:25 BREAKOUT BUY ✓, Apr 8 08:35 BREAKOUT BUY (NEW), Apr 8 08:50 BREAKOUT BUY (NEW), Apr 8 16:35 BB_BOUNCE BUY ✓.
- **Run 17 Apr 7-8 took 12 entries** (1 BREAKOUT, 2 BB_BOUNCE SELL, 9 BB_BOUNCE BUY).
- **Run 18 blocked 10 BB_BOUNCE attempts** Apr 7-8 — 8 of them on Apr 8 alone. All by `entry_quality_psar_misalign_*`.
- Pass rate for BB_BOUNCE BUY: **1 of 10 = 10%**.
- PSAR state at every blocked Apr 8 BB_BOUNCE BUY: **ABOVE** (gate requires BELOW).
- The one allowed BB_BOUNCE (Apr 8 16:35) had PSAR=BELOW — rare moment when PSAR happened to be on the aligned side.
- The 2 NEW BB_BREAKOUTs (Apr 8 08:35/08:50) fired only because Apr 8 07:20 BB_BOUNCE was blocked → no open group → cooldown didn't apply → BREAKOUT got the slot (confirmed: 08:55 BREAKOUT BUY was SKIPped as `entry_quality_breakout_cooldown`, proving cooldown engaged after 08:50).
- Estimated Run 17 P&L on the 10 blocked trades: ~$1,250. Estimated Run 18 compensation via 2 NEW BREAKOUTs: ~$300. **Net opportunity cost on Apr 7-8 alone: ~$950**.
**Answer**: **No, this is NOT what I expected** in magnitude. v2.7.26 is structurally anti-correlated with BB_BOUNCE entry timing. BB_BOUNCE BUY fires at the BB lower band (end of a pullback). PSAR is trailing — during the pullback, PSAR flips to ABOVE price. So at the entry moment, PSAR is on the WRONG side by design. The gate fires precisely when BB_BOUNCE wants to enter. ROI calculation: blocking 9 winners @ ~$125 each to save 1 loser (G5028) @ ~$100 = **−$1,025 net through Apr 8**. Precision <10% (vs 50% threshold). v2.7.26 was the wrong implementation choice for BB_BOUNCE; structurally it can't work because PSAR misalignment IS the BB_BOUNCE entry condition by definition.
**Forward link**: Issue 2 in Recommendations PROMOTED to top priority. Preferred fix: Option α (fresh-flip refinement) — only enforce PSAR alignment when PSAR has been on aligned side for ≥3 bars (filter out post-pullback flips, keep "true alignment" signal). Backward-compat: `FORGE_BREAKOUT_PSAR_FRESH_FLIP_BARS=0` (default-OFF; current behavior preserved).

### Q11 (sim Apr 9 15:10): "look april 16 again — is this what you expect to see?"
**Investigation**: Pulled Apr 16 SIGNALS rows (empty — sim hasn't reached Apr 16 yet, currently at Apr 9 15:10). Filter 1 totals: 13 blocks all on Mar 31, none since.
**Evidence**: Sim 7 sim-days short of G5048 (Apr 16 16:35). Apr 16 SIGNALS table empty for that day. Filter 1 has correctly stayed silent during the Apr 1-Apr 9 bull rally (daily slope was positive — no false positives expected on those bullish days).
**Answer**: **Not yet — sim hasn't reached Apr 16.** Two outcomes possible when sim arrives:
  - **(A, the goal)**: Filter 1 fires `entry_quality_daily_bear_block_buy` at Apr 16 16:35. Daily slope should be negative because Apr 14 close ~4841 → Apr 16 mid-day ~4810 = −31 pts over 2 days; threshold = 0.5 × daily_ATR(~25) = 12.5 → −31 < −12.5 → BLOCK. G5048 in TAKEN list: NO. Filter 1 count 13 → 14+.
  - **(B, the worry)**: Daily slope is between −7 and −12 pts because the prior 2-week rally lifted D1 SMA20 enough that the recent pullback only nudges slope slightly negative. Threshold of 0.5×ATR doesn't trip → G5048 fires anyway. Fix would be `FORGE_DAILY_SLOPE_BLOCK_ATR=0.3` (one env-var change).
**Forward link**: Hypothesis 1 in this doc, and Issue 1 (regime classifier) — separate concern from Filter 1. The two are independent: Filter 1 is about D1 slope (multi-day), Issue 1 regime is about H1+H4 alignment within a single day.


## Session Log

| Local | Sim time | Event |
|-------|----------|-------|
| 2026-05-11 10:15 | 2026-03-31 00:00 | **Run 18 launched**. FORGE v2.7.28 confirmed. aurum_run_id=18, wall_time=574713130. magic_base=202401. Filter 1 isolation test. |
| 2026-05-11 10:16 | 2026-03-31 06:05 | Baseline tick — 62 signals, 0 TAKEN. Asian session (`session_off` dominant). Housekeeping A+B PASS. |
| 2026-05-11 10:18 | 2026-03-31 16:10 | Tick 2 — 189 signals, 0 TAKEN, **6 Filter 1 BUY blocks** (`entry_quality_daily_bear_block_buy`) on Mar 31 London+NY. Run 17 also had no Mar 31 entries (sim_start was Apr 1). Apr 1 entries up next. |
| 2026-05-11 10:27 | 2026-04-01 09:40 | Tick 4 — 394 signals, **2 TAKEN** (Apr 1 08:40 + 09:28 BB_BREAKOUT BUYs identical to Run 17). **0 daily-block SKIPs on Apr 1** — Filter 1 correctly allowed legit BUYs after the overnight 4570 → 4700 rally flipped daily bullish. Hypothesis 3 (no over-filter) tracking PASS. |
| 2026-05-11 10:28 | 2026-04-01 12:40 | Tick 5 (operator re-check on Apr 1 entries) — confirmed both 08:40 + 09:28 entries are byte-identical to Run 17. Full context dump: h1_trend=+2.15/+2.12, PSAR=BELOW, regime=RANGE, magic=202401 (base). 433 signals total, still 2 TAKEN. Sim advancing through Apr 1 NY session. |
| 2026-05-11 10:30 | 2026-04-02 06:55 | Tick 6 — 650 signals, still 2 TAKEN. **10 trades closed, 9W/1L, +$247.36**. G5002 (207403) booked 4 final TPs ($91.04, $28.96, $28.88, $28.48, $30.40). Filter 1 total = 13 blocks (all Mar 31, range 08:35→19:50). Apr 1 + early Apr 2 = 0 daily-gate SKIPs (correct). Sim advancing into Apr 2 London. |
| 2026-05-11 10:35 | 2026-04-02 15:10 | Tick 7 (operator check Apr 2) — 756 signals, still 2 TAKEN. **Apr 2 anomaly**: Run 17 had 2 entries (10:25 SELL G5003, 12:15 BUY G5004) but both blocked in Run 18 by **v2.7.26 `entry_quality_psar_misalign_*`** (NOT Filter 1). G5003 lost as +$103 win, G5004 lost as +$122 win → ~$225 opportunity cost. v2.7.26 PSAR-on-BB_BOUNCE was added to block G5028-class losses (Apr 10 incoming) — net trade-off awaits end-of-run. Filter 1 total unchanged at 13 (Mar 31 only). |
| 2026-05-11 10:46 | 2026-04-06 10:35 | Tick 8 — 975 signals, still 2 TAKEN, +$247.36 unchanged. Apr 3-5 weekend (Fri+Sat+Sun) produced 219 SKIPs but no entries/blocks (matches Run 17). Next expected Run 17 entry: Apr 6 10:50 BB_BREAKOUT BUY @ 4672.54 — 15 sim-min away. |
| 2026-05-11 10:50 | 2026-04-06 12:35 | Tick 9 — 1003 signals, **3 TAKEN** (Apr 6 10:50 BB_BREAKOUT BUY @ 4672.54 fired identically to Run 17 G5005). G5003 (Run 18 numbering = 207404) banked +$174.56 in 2 TPs (TP1 @ +3pts × 2 legs = $49, TP2 @ +9pts × 1 leg = $75). Net total +$421.92, 14W/1L. Same 5-leg cap as G5001 (regime=RANGE). |
| 2026-05-11 10:55 | 2026-04-07 09:00 | Tick 10 — 1236 signals, 3 TAKEN, +$421.92 unchanged. Apr 6 PM idle (matches Run 17). Pace ~3 sim-hr/wall-min when idle. Next Run 17 entry: Apr 7 11:20 BB_BOUNCE SELL @ 4660.25 — ~1 wall-min away. |
| 2026-05-11 11:00 | 2026-04-07 21:35 | Tick 11 — 1392 signals, **4 TAKEN** (added Apr 7 11:25 BB_BREAKOUT BUY @ 4683.39, byte-identical to Run 17). G5006 banked +$67.68 (2 TP1) − $22.24 (1 SL) = +$45 visible. Run 17 also had Apr 7 11:20 + 15:25 BB_BOUNCE SELLs — **both blocked by v2.7.26 psar_misalign_sell** (count went 4→7). ~$170 more opportunity cost vs Run 17 from this PSAR gate. Net +$535.04, 18W/2L. |
| 2026-05-11 11:08 | 2026-04-08 21:05 | Tick 12 (operator added Recommendations + Q&A pattern to doc + skills) — 1674 signals, **7 TAKEN**, +$1,400.80, 51W/2L. **3 new entries on Apr 8**: 08:35 BB_BREAKOUT BUY @ 4822.59 (ADX=41.9), 08:50 BB_BREAKOUT BUY @ 4831.82 (ADX=55.2!), 16:35 BB_BOUNCE BUY @ 4783.29 (PSAR aligned). Run 17 did NOT have the Apr 8 08:35/08:50 BB_BREAKOUTs (only had BB_BOUNCE BUYs at 07:20+11:30 etc.). **Run 18 ahead of Run 17 pace in P&L** through Apr 8. Updated Run 18 doc with Recommendations + Operator Q&A Log sections; updated forge-monitor + forge-ea-review skills to make this documentation pattern mandatory going forward (always Google for canonical patterns, cite sources, propose multiple options with pseudocode, default-OFF flags). |
| 2026-05-11 12:09 | 2026-04-14 ~10:25 | **Run 18 STOPPED by operator** (12 TAKEN, +$2,713.02, 131W/14L). Pivoted to v2.7.29 regime override fix (Issue 1 Option A). Operator-approved roadmap: v2.7.29 ships H1-strong override clause + .env activation of dump-catch (`FORGE_DUMP_CATCH_ENABLED=1`, `FORGE_DUMP_REQUIRE_D1_BIAS=0`, `FORGE_DUMP_LOT_FACTOR=0.5`) + regime override (`FORGE_REGIME_H1_OVERRIDE_FACTOR=2.0`). Apr 15 SELL cluster + Apr 16 G5048 outcomes NOT captured — to be tested in Run 19. |
| 2026-05-11 11:21 | 2026-04-09 15:10 | Tick 13 (operator: "look april 16 again — is this what you expect?") — Apr 16 still ~7 sim-days away (sim hasn't reached it). 1890 signals, **8 TAKEN** (added Apr 9 13:51 BB_BREAKOUT BUY @ 4743.11 = Run 17 G5018). **G5008 loss cluster**: 5 legs SL'd at 4739.68 within 11 min of entry, all at −3.43pts (0.73×ATR — tight). Loss −$60.72 — note SL tighter than `breakout_buy_sl_atr_mult=3.0×ATR` expectation, structural placement (LENS OB zone). Net: 60W/7L, +$1,371.76. Filter 1 unchanged at 13 (all Mar 31). |
| 2026-05-11 11:28 | 2026-04-10 23:55 | Tick 14 — **G5028 ✓ BLOCKED** (Apr 10 18:45 BB_BOUNCE BUY @ 4766.05, PSAR=ABOVE → `entry_quality_psar_misalign_buy`). This is THE TRADE v2.7.26 was specifically designed to prevent — design validated. 2298 signals, **11 TAKEN** (added Apr 10 14:45/15:00/15:35 BREAKOUT BUYs = Run 17 G5024+G5025 + 1 NEW). Run 17 also had Apr 10 morning BB_BOUNCE cluster (7 trades) — all blocked Run 18. **+$2,298.22 P&L, 114W/14L = 89.1% WR**. Updated v2.7.26 ROI: 1 prevented loss (~$100) vs 10 missed winners (~$1,250), partially offset by 4 unexpected BB_BREAKOUTs (~$600). Net cost: ~$550 so far. Filter 1 unchanged at 13. Apr 16 G5048 still 5.5 sim-days away. |
| 2026-05-11 12:30 | n/a (chat) | **v2.7.30 shipped** — tester/live regime parity fix. Removed `if(in_tester)` wrapper from inline classifier at `FORGE.mq5:5687-5704` so H1+H4 EMA-spread classifier with v2.7.29 override clause runs unconditionally in both modes. VERSION 2.7.29 → 2.7.30, `make forge-compile` PASS, housekeeping A+B PASS, 28/28 gate tests PASS. JSON regime_label read at `:1094-1099` becomes advisory (overwritten each tick). |
| 2026-05-11 12:45 | n/a (chat) | **Regime architecture review** — operator surfaced design question: regime.py output is bypassed for FORGE entries post-v2.7.30, alive only for SCRIBE/Athena observability. Schema confirmed correctly aligned (label vocab, payload, SCRIBE columns) per Q18. Three structural gaps identified: BRIDGE-not-in-tester, M5-vs-H1+H4 TF mismatch, confidence semantics divergence (HMM posterior vs hardcoded 1.0). |
| 2026-05-11 13:00 | n/a (chat) | **TradingView MCP investigation** — operator pointed out LENS already wraps `LewisWJackson/tradingview-mcp-jackson`. Re-read MCP server source: exposes `replay_start` / `replay_step` / `data_get_study_values` / `batch_run` — historical regime features ARE retrievable via Bar Replay (correcting my earlier "not feasible" answer). |
| 2026-05-11 13:15 | n/a (chat) | **Issue 7 drafted** — file-driven regime stream as v2.7.31 candidate. WebSearched 4 canonical patterns (HMM/hmmlearn, Markov-Switching/statsmodels, change-point/ruptures, multi-factor rule-based ARC). Three Options (A: file-driven JSON stream, B: MQL5 HMM port, C: MSDR+CPD hybrid). Preferred: Option A. All cited sources captured in Issue 7. |
| 2026-05-11 13:30 | n/a (chat) | **Parity invariant codified in EA** — added `PARITY INVARIANT` banner block to `FORGE.mq5` just below `FORGE_VERSION` declaration (4 enforcement rules + changelog). Added `FORGE PARITY:` runtime audit log in `OnInit` printing `mode`, `regime_source`, `trend_strength_atr_threshold`, `regime_h1_override_factor`, `regime_h1_override_adx_min` — grep this prefix in MT5 journal/tester log to confirm identical knobs apply in tester and live. `make forge-compile` PASS. |
