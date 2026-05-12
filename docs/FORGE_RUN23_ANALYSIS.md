# FORGE Run 23 — Tester Analysis (v2.7.34 — wave-confirmation + dump-sensitivity)

**EA version**: FORGE v2.7.34 (build 2.104)
**Symbol**: XAUUSD
**Sim period**: 2026-03-31 → TBD
**Scalper mode**: DUAL
**Balance**: $10,000
**aurum_run_id**: pending sync (~60s)
**wall_time**: 602287869
**source_run_id**: 4
**Magic base**: 202401
**Status**: **in progress** (sim at 2026-03-31 08:31 UTC, 97 signals, 0 TAKEN — London open)

> Previous Run 23 doc (FORGE 2.7.6 from May 9) archived as `FORGE_RUN23_ANALYSIS_OLD_v2.7.6.md`.

---

## Test intent — Run 23 v2.7.34 bundle (vs Run 22 v2.7.33 baseline)

**ENTRY FILTERS (block wrong-direction)**
- `dump_max_rsi=41` — SELL chop-retrace block (already shipped 2.7.33)
- `dump_max_rsi_buy=70` — **NEW** BUY wave-exhaustion block (G5009 Run 20 fix)
- `entry_quality_daily_bear_block_buy` extended to MOMENTUM_DUMP_BUY filter chain — **NEW** daily reality check

**ENTRY DETECTION (catch slower dumps)**
- `dump_atr_mult=1.0` (was 1.5 default) — **NEW** catches Apr 8-style slow drift dumps
- `dump_min_adx=20` — unchanged
- `dump_require_d1_bias=0` — unchanged (allows counter-trend dumps)

**POSITION SIZING (size to confirmation)**
- `FORGE_STAGED_INITIAL_LEGS=10` env REMOVED — defaults to 1 leg per entry
- `staged_add_min_favorable_points=500` ($5 favorable per added leg)
- `wave_confirmation_lot_mult=2.0` — **NEW** legs 2-10 deploy at 2× lot (amplify confirmed legs only)
- TP1=0.6×ATR / TP2=1.0×ATR (TP1 widened from 0.4 in 2.7.33)

---

## Mandatory Housekeeping (session start)

| Check | Result |
|-------|--------|
| Check A — dead `FORGE_*` env vars | **PASS** |
| Check B — gate legend coverage (`dump_rsi_buy_ceil` newly added) | **PASS** |

---

## Cross-run target table

| Metric | Run 20 (2.7.31) | Run 22 (2.7.33) | Run 23 target (2.7.34) |
|---|---|---|---|
| Sim reach | Apr 1 11:35 | Apr 1 (full Apr1) | full window TBD |
| TAKEN | 16 | 20 (11 incl post-fix) | ≥ 20 + Apr 8 PM coverage |
| Trades | 123 | 48 | TBD |
| Net P&L | −$418 | +$678 | **+$1,000+** target |
| G5001-class SELL (Mar 31 08:16 RSI 43.6) | TAKEN −$51 | TAKEN −$51 | **BLOCKED by RSI=41** (shipped 2.7.33) |
| G5011-class SELL (Apr 1 09:01 RSI 48.7) | n/a | TAKEN −$51 | **BLOCKED by RSI=41** |
| G5009-class BUY (Mar 31 14:44 RSI 72.2) | TAKEN −$305 | n/a | **BLOCKED by RSI=70 ceiling** _pending_ |
| Apr 8 PM dump (60-pt SELL) | n/a | n/a | **TARGET: fire MOMENTUM_DUMP SELL** _pending Apr 8_ |
| Wave-confirmation leg banking | n/a | n/a | _pending — measure per-wave $ vs Run 22_ |

---

## Hypothesis tracker

| H | Test |
|---|------|
| H1 — Parity audit log clean | confirm OnInit knobs match: dump_max_rsi=41, dump_max_rsi_buy=70, dump_atr_mult=1.0, wave_confirmation_lot_mult=2.0, staged_add_min_favorable_points=500 |
| H2 — Apr 8 morning BB_BREAKOUT BUYs still fire (08:35, 08:50) | _pending Apr 8_ |
| H3 — Apr 8 PM dump fires as MOMENTUM_DUMP SELL with new dump_atr_mult=1.0 | _pending Apr 8 13:00-17:00_ |
| H4 — Apr 14 declines covered | _pending Apr 14_ |
| H5 — G5001-class SELL @ RSI 43.6 logged as `dump_rsi_block` SKIP, not TAKEN | **PASS** — Mar 31 08:10 SELL @ RSI=45.1 → `dump_rsi_block` SKIP. Run 22 equivalent 08:16 SELL @ RSI=43.6 had been TAKEN (−$51). |
| H6 — G5009-class BUY @ RSI 72.2 logged as `dump_rsi_buy_ceil` SKIP | _pending Mar 31 14:44_ |
| H7 — daily_bear_block fires on MOMENTUM_DUMP_BUY (not just BB_BREAKOUT) | _pending — Mar 31 daily bearish day_ |
| H8 — Wave-confirmation legs deploy at 2× base lot (0.02) after $5 favor | _pending — any successful trend ride_ |
| H9 — No regression: total TAKEN ≥ Run 22 (20) | _at end of run_ |

---

## TAKEN Groups (running)

_(none yet — sim in Asia pre-session)_

---

## P&L by magic (running)

_(none yet)_

---

## Gate Breakdown (running)

| Gate Reason | Count | Note |
|---|---|---|
| `session_off` | 72 | Pre-London Asia |
| `no_setup` | 17 | |
| `dump_rsi_block` | 3 | **NEW filter active** — 2× SELL @ RSI≥41 (G5001-class), 1× BUY @ RSI≤59 (mirror) |
| `dump_bar_confirm_missing` | 2 | 2.7.32 filter from prior version |
| `warmup_tester_m5_rollovers` | 2 | |
| `dump_psar_block` | 1 | |

---

## Losses — Price Movement Analysis

_(deferred — populated at stop condition via Q6b)_

---

## Observations & Anomalies

_(none yet)_

---

## Recommendations & Open Issues

_(none yet)_

---

## Operator Q&A Log

_(empty)_

---

## Session Log

| Local | Sim time | Event |
|-------|----------|-------|
| tick 0 | 2026-03-31 03:55 | **Run 23 launched**. FORGE v2.7.34 build 2.104, source_run_id=4, wall_time=602287869. Magic_base=202401. 36 signals all `session_off` (Asia pre-London). EA loaded new .ex5 successfully (forge_version=2.7.34 confirmed in TESTER_RUNS). Awaiting first London session entries. |
| tick 1 | 2026-03-31 08:31 | **H5 PASS**. London open. 97 signals, 0 TAKEN yet. **`dump_rsi_block` fired 3×** including Mar 31 08:10 SELL @ RSI=45.1 (G5001-equivalent — would have been TAKEN+lost $51 in Run 22). BUY mirror also blocking RSI 50-53 entries (07:20, 08:25). `dump_bar_confirm_missing` 2×. `dump_psar_block` 1×. New filters active and working both directions. Waiting for first TAKEN to verify wave-confirmation amplifier deployment. aurum_run_id=23. |
