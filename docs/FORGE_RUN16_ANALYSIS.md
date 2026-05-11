# FORGE Run 16 — Tester Analysis

**EA version**: FORGE v2.7.21
**Symbol**: XAUUSD
**Sim period**: 2026-04-01 → (in progress)
**Scalper mode**: DUAL
**Balance**: $10,000
**aurum_run_id**: 16
**wall_time**: 549083107
**source_run_id**: 2 (TESTER_RUNS.id)
**Magic base**: 202401
**Status**: in progress (sim at Apr 1 07:05 UTC — warmup phase, 0 TAKEN yet)

---

## What's NEW in Run 16 vs Run 15 (v2.7.16 → v2.7.21)

The operator reloaded MT5 with the fixed `.ex5` after observing Run 15 lose **−$5,632** (with 84% from cascade SL hits). This run tests every v2.7.17 → v2.7.21 gate together.

### Active gates (vs Run 15 baseline)

| Layer | Run 15 (v2.7.16) | **Run 16 (v2.7.21)** | Catches |
|-------|------------------|----------------------|---------|
| `same_dir_cooldown_seconds` | 0 (off) | **900** (15 min) | G5002, G5013-class double-tap |
| `require_h1_macd_buy` | 0 (off) | **0** (still off) | n/a |
| `breakout_buy_sl_atr_mult` | 0 (off) | **3.0** (BUY SL widen on gate-pass) | G5015-class SL-hunt wicks |
| `failed_gate_enabled` (Fix B) | 0 (off) | **1** (on) | G5013/G5015 fake-breakout pullback |
| `failed_lookback_bars` | n/a | **4** | 20-min memory window |
| `failed_min_peak_rsi` | n/a | **68** (lowered 75→68 in 2.7.20) | catches moderate-RSI rollover (G5018, G5032) |
| `failed_min_rsi_drop` | n/a | **3** | |
| `failed_same_bar_hard_block` (2.7.20) | n/a | **1** (on) | G5018 (-$960), G5022 (-$1035) wick rejection |
| `require_psar_align` (2.7.20) | n/a | **1** (on) | G5035 (-$1139) FLIP_BEAR, G5036 (-$8) FLIP_BULL |
| `rsi_sell_floor` | 30 | **33** (2.7.21) | G5040 SELL @ RSI 32.4 |
| `sell_stop_cont_require_trend_regime` (2.7.21) | n/a | **1** (on) | Cascade arm in RANGE blocked |

### Hypothesis validation (pending evidence as sim crosses each timestamp)

| # | Hypothesis | Run 15 evidence | Status |
|---|------------|-----------------|--------|
| 1 | Same-bar atr_ext hard block prevents G5018 / G5022 pattern (intra-bar wick entries) | G5018 −$960 + G5022 −$1,035 = −$1,995 avoided | _pending Apr 10/Apr 14_ |
| 2 | Failed-breakout-pullback gate (RSI peak ≥68 + RSI drop ≥3) prevents G5013/G5015 | G5013 −$1,086 + G5015 −$875 = −$1,961 avoided | _pending Apr 8/Apr 9_ |
| 3 | PSAR alignment blocks G5035-class catastrophic reversals | G5035 −$1,139 avoided | _pending Apr 16_ |
| 4 | RSI floor 33 blocks G5040-class fake-breakdown SELL | G5040 cascade −$1,107 avoided | _pending Apr 21_ |
| 5 | Cascade regime guard prevents RANGE-regime cascade catastrophes | partial — most cascades were TREND_BEAR (so regime guard alone insufficient) | _pending Apr 23-28_ |
| 6 | Cooldown 900s blocks same-direction double-taps | G5002, G5021/G5022 cascades | _pending Apr 1_ |
| 7 | BUY SL widen 3.0×ATR survives G5015-style wick (entries that pass all gates) | Run 16 should show wider SL distances on BB_BREAKOUT BUY trades | _pending first BUY entry_ |

**Pre-run expectation**: If all 7 hypotheses hold, total Run 16 P&L should be **+$1,300 to +$2,500** (vs Run 15's −$5,632 partial), based on cumulative avoided losses minus surrendered winners.

---

## Summary (running)

| Metric | Value |
|--------|-------|
| Total signals | 73 |
| TAKEN | 0 (warmup) |
| P&L | $0 |
| Latest sim | Apr 1 07:05 UTC |

---

## TAKEN Groups
_None yet — sim in pre-session warmup. London opens at 07:00 UTC._

---

## P&L by magic (running)
_Empty._

---

## Gate Breakdown (running)

| Gate | Count |
|------|-------|
| session_off | 71 |
| warmup_tester_m5_rollovers | 2 |

---

## Mandatory Housekeeping (session start)

| Check | Result |
|-------|--------|
| A. Dead `FORGE_*` env vars | **PASS** |
| A. Lowercase config leaks | **PASS** |
| B. Gate legend coverage | **PASS** |

---

## Session Log

| Local | Sim time | Event |
|-------|----------|-------|
| 2026-05-11 03:43 | Apr 1 07:05 | **Run 16 baseline detected**: wall_time=549083107, FORGE **v2.7.21**, sim_start 2026-04-01. Source run_id=2. aurum_run_id=16. 73 signals (71 session_off + 2 warmup), 0 TAKEN. Approaching London session open (07:00 UTC). All v2.7.17→v2.7.21 fixes active in config: cooldown 900s, failed-breakout-pullback gate (peak_rsi 68 / drop 3 / lookback 4), same-bar hard block, PSAR alignment, BUY SL widen 3.0×ATR, SELL RSI floor 33, cascade trend-regime guard. |
| 2026-05-11 03:55 | Apr 2 03:55 | **Tick: rr_too_low blocking ALL BB_BREAKOUT BUY**. 319 sigs, 0 TAKEN. Apr 1 G5001/G5002/G5003 all blocked: 08:40 rr_too_low, 08:45 rr_too_low, 09:25 entry_quality_psar_misalign_buy (Fix C working!), 09:28 rr_too_low, 09:50 rr_too_low. **Bug found**: v2.7.18 buy_sl_atr_mult=3.0 widens SL placement but R:R denominator also uses widened sl → max R:R = 4.0×ATR (TP4) / 3.0×ATR (SL) = 1.33 < min_rr_floor=1.5 → 100% BUY breakouts blocked rr_too_low. |
| 2026-05-11 04:09 | Apr 2 17:30 | **First TAKEN**: BB_BOUNCE BUY G5001 @ 4623.24 (Apr 2 12:15). 15 deals, all wins, **+$205.32**. BB_BOUNCE unaffected by R:R bug (uses bounce_sl_atr_mult=1.5, not buy_sl widen). Confirms bug is BB_BREAKOUT-only. BB_BOUNCE still firing fine. |
| 2026-05-11 04:18 | Apr 2 17:30 | **v2.7.22 R:R decouple fix shipped** (operator not reloaded yet). Code change at ea/FORGE.mq5:5953 — R:R now uses BASE breakout_sl_atr_mult (2.0) instead of widened buy_sl_atr_mult (3.0). SL placement still 3.0×ATR for SL-hunt protection. .ex5 v2.7.22 built (MQL5 build 2.92). Operator needs to reload to activate. |
| 2026-05-11 04:25 | Apr 2 18:40 | **Tick (no reload yet)**: 500 sigs (+14), 1 TAKEN, +$205.32. Sim crawling at quiet evening hours (RSI 54-74, all no_setup). v2.7.21 still loaded → BB_BREAKOUT BUY still blocked. Operator should reload to get v2.7.22 and unblock BB_BREAKOUT BUY for the rest of the run. |
