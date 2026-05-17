# FORGE Run 25 — Tester Analysis

**EA version**: FORGE v2.7.52
**Symbol**: XAUUSD
**Sim period**: 2026-03-31 → (in progress)
**Scalper mode**: DUAL
**Balance**: (to be confirmed from TESTER_RUNS)
**aurum_run_id**: 25
**wall_time**: 602936
**source_run_id**: 1 (TESTER_RUNS.id)
**Journal DB**: Agent-127.0.0.1-3000 (Agent-3001 DB present but unreadable / no current run)
**Status**: **COMPLETE** (tester stopped 2026-05-13 ~07:30 local; sim reached 2026-04-16 23:55 UTC; source journal then wiped when MT5 Tester restarted with v2.7.54 .ex5 for Run 26)

> Note: a prior `FORGE_RUN25_ANALYSIS.md` documenting an unrelated FORGE 2.7.7 backtest
> (Apr 29 – May 4, dated 2026-05-09) has been renamed to `FORGE_RUN25_v2.7.7_PRIOR.md`.
> That doc was misnumbered relative to the current AUTOINCREMENT-assigned aurum_run_id=25.

---

## Summary (running)
- Total signals: 143,471
- TAKEN: 2 (both MOMENTUM_DUMP SELL, NY session)  |  Skipped: 143,469
- Total P&L: **+$20.22** (running) — G5001 +$9.72 @ 12:30:51, G5002 +$10.50 @ 13:36:44
- Win rate: 100% (2W / 0L) so far
- Latest sim time: 2026-03-31 18:47:52 UTC (post-NY close on Mar 31)

## Hypotheses to validate (this run)
| # | Hypothesis | Status |
|---|------------|--------|
| H1 | FORGE v2.7.52 KZ warmup gate (`FORGE_GATE_KZ_WARMUP_MIN`, arongroups stop-hunt research) defers entries in first N min of each killzone | _pending_ — sim has not yet entered London KZ (07:00 UTC) |
| H2 | v2.7.51 §11.4 killzone-aware composite refinements (3 of 5 shipped) fire as expected | _pending_ |
| H3 | EA-anchored session authority (§11.7b extension, v2.7.50) holds session boundaries correctly during DST window (Mar 30+ in 2026) | _pending_ |
| H4 | All 16 default-OFF setups stay OFF unless explicitly enabled (per recent test refactor commit 1d88a20) | _pending_ — verify via gate breakdown showing no unexpected setup_type values |

## Pre-flight housekeeping (run once at start)
- Dead `FORGE_*` env vars: **PASS** (none)
- Lowercase config leaks: **PASS** (none)
- Gate legend coverage: **PASS** (no missing gate_reason codes)

## TAKEN Groups
| Sim Time (UTC) | Group | Magic | Direction | Setup | Session | RSI | ADX | m15_adx | ATR | Price | h1_trend | Regime | PSAR | P&L |
|----------------|-------|-------|-----------|-------|---------|-----|-----|---------|-----|-------|----------|--------|------|-----|
| 2026-03-31 12:30:29 | G5001 | 207402 | SELL | MOMENTUM_DUMP | NY | 40.7 | 33.9 | 18.3 | 5.31 | 4559.73 | +0.90 | TREND_BULL | ABOVE | +$9.72 (TP @ 4556.57, 22 sec) |
| 2026-03-31 12:40:29 | G5002 | 207403 | SELL | MOMENTUM_DUMP | NY | 34.7 | 43.9 | 19.4 | 5.75 | 4552.70 | +0.87 | TREND_BULL | ABOVE | +$10.50 (TP @ 4549.25, **56 min** — see anomaly) |

## Gate Breakdown (running, sim 18:47 UTC)
| gate_reason | count | category |
|-------------|-------|----------|
| `double_bottom_cooldown` | 37,615 | §11.4 Double Bottom — NEW dominant gate this tick |
| `fib_confluence_cooldown` | 23,777 | §11.4 Fib Confluence |
| `trendline_bounce_cooldown` | 17,401 | §11.4 Trendline Bounce |
| `sr_flip_cooldown` | 17,088 | §11.4 SR Flip |
| `inside_bar_cooldown` | 16,518 | §11.4 Inside Bar |
| `trendline_bounce_adx_below_min` | 7,111 | Trendline Bounce ADX gate |
| `double_top_cooldown` | 6,362 | §11.4 Double Top |
| `ma_crossover_m15_misalign` | 5,738 | MA Crossover M15 trend misalignment |
| `ma_crossover_adx_below_min` | 2,661 | MA Crossover ADX gate |
| `ma_crossover_cooldown` | 2,619 | §11.4 MA Crossover |
| `bb_squeeze_cooldown` | 2,469 | §11.4 BB Squeeze — NEW this tick |
| `vwap_reversion_cooldown` | 2,096 | §11.4 VWAP Reversion |
| `inside_bar_adx_below_min` | 1,465 | Inside Bar ADX gate |
| `sr_flip_adx_below_min` | 227 | SR Flip ADX gate |
| `no_setup` | 140 | clean miss |
| `session_off` | 72 | pre-London Asia + post-session |
| `rr_too_low` | 47 | R:R below floor |
| `dump_rsi_block` | 30 | MOMENTUM_DUMP RSI block (FORGE_DUMP_MAX_RSI=41) |
| `entry_quality_daily_bear_block_buy` | 23 | daily bear bias blocks BUY |
| `dump_bar_confirm_missing` | 21 | MOMENTUM_DUMP bar confirmation missing |

## Cross-Run Comparison
| Run | EA | TAKEN | P&L | Notes |
|-----|----|-------|-----|-------|
| 23 | 2.7.34 | — | — | (historical baseline) |
| 24 | 2.7.39 | — | — | last FORGE generation before §11.4 KZ work |
| **25** | **2.7.52** | **0 (in progress)** | **$0** | KZ warmup + §11.4 composites + EA-anchored sessions |

## Observations & Anomalies
- _2026-05-13 02:39 local_: Run started. 25 signals at sim 03:00 UTC, all `session_off` — expected pre-London Asia behavior.
- _2026-05-13 02:44 local_ (sim 13:30 UTC): **G5002 held against entry for ~56 min before TP banked**. Entry 4552.70 at 12:40 — price ran AGAINST to 4558.48 by 12:50 (-5.8 pts), oscillated 4555–4560 (5 to 8 pts against) until 13:35, then dumped sharply to 4533.82 at 13:40 banking TP at 4549.25 (13:36:44). This contradicts the operator's chop-grid principle (TP1 should bank fast, < 5-10 min on M5 chop). Hold-to-eventual-TP works only if no SL is triggered first — verify the SL distance on this entry and whether SL was hit at any point during the 56-min hold.
- _2026-05-13 02:44 local_ (sim 13:30 UTC): **TWO MOMENTUM_DUMP SELLs on Mar 31 in TREND_BULL regime with h1_trend=+0.9** (canonical CHOP_IN_BULL_TREND_BUY day). Both banked TP1, so the dump-SELL was correct for the 12:30–13:40 NY mini-dump segment, but the bigger-picture pattern means the broader CHOP_IN_BULL_TREND_BUY composite (memory-validated 3-4 dip-buys per Mar 31) is NOT firing on this day for this run. Awaiting later hours to see if it appears.
- _2026-05-13 02:44 local_: §11.4 cooldown gates massively dominate the gate breakdown (sr_flip 13k, trendline_bounce 12k, inside_bar 9k, fib 7k, double_top 6k, ma_crossover 3k, vwap_reversion 1k). With only 2 actual TAKEN, these cooldowns represent either (a) signal detection firing constantly while the cooldown is held from a single prior fire, or (b) the cooldown is engaging on every M5 bar of qualifying conditions independent of an actual entry. Need to check ea/FORGE.mq5 cooldown logic — if (b), the cooldown gate is functioning as a noise filter rather than a post-entry throttle, which contradicts its name.

## Recommendations & Open Issues
<!-- Append per RECOMMENDATIONS PATTERN. -->

## Operator Q&A Log

### Q1 (sim 2026-03-31 13:30): "is MOMENTUM_DUMP using the new composite?"
**Investigation**: grep `ea/FORGE.mq5` for `MOMENTUM_DUMP|momentum_dump|dump_*`; grep `FORGE_DECISION_STACK.md` and `FORGE_COMPOSITE_ROADMAP.md` for MOMENTUM_DUMP integration status.
**Evidence**:
- `ea/FORGE.mq5:9069-9281` — MOMENTUM_DUMP runs its own legacy filter-chain (sequential `if/else if` blocks emitting `dump_rsi_block`, `dump_adx_block`, `dump_psar_block`, `dump_chop_block`, `dump_h1_trend_block_sell`, `dump_judas_window`, `dump_cooldown`).
- `FORGE_DECISION_STACK.md §4` — MOMENTUM_DUMP_SELL is literally the doc's canonical example of the Filter Chain pattern.
- `ea/FORGE.mq5:9947-9961` — has its own RR bypass (`_rr_bypass = (setup_type == "MOMENTUM_DUMP" ...)`) because dump-catch geometry is tighter than the standard min_rr floor.
- Gate breakdown distinguishes paths: `dump_cooldown=2` (legacy) vs `sr_flip_cooldown=17k` / `double_bottom_cooldown=37k` / etc. (new §11.4) — completely separate code paths.
- `FORGE_COMPOSITE_ROADMAP.md §75-76` — `BULL_DAY_DIP_BUY_V3` + `INTRADAY_REVERSAL_TO_SELL_V3` are Tier-1 candidates that *would* wrap MOMENTUM_DUMP BUY/SELL as quality filters, but **haven't shipped** yet. One composite-style atom IS plumbed: `entry_quality_intraday_reversal_buy_block` at `ea/FORGE.mq5:9207` gates MOMENTUM_DUMP BUY.
**Answer**: No. MOMENTUM_DUMP still uses the legacy filter-chain pattern (`dump_*_block` gate codes), with one composite-style atom (`entry_quality_intraday_reversal_buy_block`) hanging off the BUY branch. Full V3 composite wrap is roadmap-only; the §11.4 cooldown gates dominating the breakdown belong to other setups (SR Flip / Trendline Bounce / Inside Bar / Fib Confluence / Double Top/Bottom / MA Crossover / VWAP Reversion / BB Squeeze).
**Forward link**: n/a — no remediation needed; this is the current designed state.

### Q2 (sim 2026-04-01 04:55): "are INTRADAY_REVERSAL_SELL / BULL_DAY_DIP_BUY ready to be implemented?" → corrected: they are ALREADY implemented in v2.7.52, just default-OFF
**Investigation**: re-grepped `ea/FORGE.mq5` for `IsBullDayDipBuyActive` and `IsIntradayReversalSellActive` after operator pushback. Initial answer claimed only config knobs were plumbed; that was wrong.
**Evidence (corrected)**:
- `ea/FORGE.mq5:5806-5844` — `IsBullDayDipBuyActive` is a 16-atom composite boolean function (V3 spec from atlas §5.1 fully wired: enabled flag, h1≥0.5, !daily_bear, RSI∈[30,50], ADX∈[12,40], BB structure, POC dist, Fib50 dist, VWAP dist, no bear RSI divergence, V3 OHLC atoms `dist_high_atr<2` + `!m5_lh_cascade` + `long_lower_wick`, LONDON/NY session, re-entry cooldown with v2.7.41 bypass).
- `ea/FORGE.mq5:9304-9326` — standalone setup trigger that fires when `direction==""` (no other setup claimed), sets `setup_type="BULL_DAY_DIP_BUY"`, geometry SL=ATR×1.0, TP1=ATR×0.65, TP2=0 (single-banking per atlas §5.1 chop scalping geometry).
- `ea/FORGE.mq5:9322` — updates `g_last_chop_buy_exit_time` as cooldown anchor → enables the continuous-leg opening cycle described by operator.
- `ea/FORGE.mq5:10158-10171` — base lot multiplier (`bull_day_dip_buy_lot_mult`) + prime-KZ amplifier (`bull_day_dip_buy_prime_amplifier` stacks when killzone ∈ {NY_OPEN_KZ, LONDON_CLOSE_KZ}).
- `ea/FORGE.mq5:5168` — `IsIntradayReversalSellActive` function; called as BUY-block gate at `:8292`, `:8498`, `:9204` (gates BB_BREAKOUT BUY / BB_BOUNCE BUY / MOMENTUM_DUMP BUY) and as SELL lot amplifier at `:10145` (`intraday_reversal_sell_lot_mult` default 2.0).
- `config/scalper_config.defaults.json:323,332` — both default `enabled=0` (OFF).
- Run 25 SIGNALS table: zero `BULL_DAY_DIP_BUY` setup_type rows on Mar 31 → confirms OFF.
**Answer**: Both composites are FULLY implemented in v2.7.52 (not just config-plumbed as I incorrectly stated in Q1). They are default-OFF; flipping `FORGE_SETUP_BULL_DAY_DIP_BUY_ENABLED=1` + `FORGE_SETUP_INTRADAY_REVERSAL_SELL_ENABLED=1` in `.env`, then `make scalper-env-sync && make forge-compile`, will activate them for the next run. Mar 31 zero-entry result is direct evidence that the knob is OFF in this run — the canonical chop-in-bull day per memory should produce 3-4 BULL_DAY_DIP_BUY entries when enabled.
**Forward link**: Recommendation 1 — turn both knobs ON for the NEXT tester run to validate Run 25 outcome per roadmap §158-160 ("will validate Run 25" entry currently NOT being validated since the knobs are OFF).

## Session Log
| Local time | Sim time | Event |
|------------|----------|-------|
| 2026-05-13 02:39 | 2026-03-31 03:00 | Baseline tick: 25 SKIPs, all `session_off`. Awaiting London KZ entry at 07:00 UTC to validate KZ warmup gate. |
| 2026-05-13 02:43 | 2026-03-31 12:03 | Tick 2: 38,025 signals, 0 TAKEN. §11.4 cooldown gates dominate breakdown (sr_flip 10k, trendline_bounce 8k, inside_bar 8k). Flagged as alarm-worthy — Mar 31 should be a chop-in-bull dip-buy day per memory; nothing firing. |
| 2026-05-13 02:44 | 2026-03-31 13:30 | Tick 3: 56,459 signals, **2 TAKEN** (MOMENTUM_DUMP SELL G5001+G5002 at 12:30/12:40). Both banked TP1: +$9.72 + $10.50 = +$20.22. G5002 held 56 min against entry before banking — flagged as chop-grid principle violation. |
| 2026-05-13 02:47 | 2026-03-31 18:47 | Tick 4: 143,471 signals (+87k), still 2 TAKEN, P&L unchanged at +$20.22. NEW gates emerged: `double_bottom_cooldown` (37k — now the biggest gate by far), `bb_squeeze_cooldown` (2.5k), `sr_flip_adx_below_min` (227), `trendline_bounce_adx_below_min` (7.1k). Mar 31 NY block (13:00-17:00 UTC) produced **no further entries** beyond the two MOMENTUM_DUMP SELLs at 12:30/12:40 — CHOP_IN_BULL_TREND_BUY composite (memory: 3-4 dip-buys expected per Mar 31) confirmed not implemented as a setup trigger this version. Sim now post-NY close on Mar 31. |
| 2026-05-13 02:50 | 2026-04-01 04:55 | Tick 5: 152,264 signals (+8.8k, low Asia activity), 2 TAKEN unchanged, +$20.22 unchanged. Sim advanced into Apr 1 Asia session — pre-London. `trendline_bounce_cooldown` 17k → 25k. Operator pivoted to Telegram flooding question; investigation logged in Q&A Log Q2. |
| 2026-05-13 03:23 | 2026-04-01 ~Apr 1+ | Out-of-band patch landed: `bridge.py:3106-3146,3148-3170` strategy_tester guard for `_on_session_change` + `_on_killzone_change` (BRIDGE v2.7.53). Reloaded via `make reload-bridge` (new PID 16913). Verified suppression line fires: `BRIDGE: suppressed SESSION-change handler (OFF_HOURS → ASIAN, balance=$10,481.81) — strategy_tester=true`. Telegram flood resolved. Changelog entry added. |
| 2026-05-13 03:38 | 2026-04-07 ~15:00+ | Tick 6 review revealed massive sim progress: 22 TAKEN across Mar 31–Apr 7, **+$491.59 running P&L, 100% WR (26W/0L)**. Apr 1 captured TREND_CONTINUATION rally (7 entries including 1 FRACTIONAL_SELL_IN_BULL probe). Apr 2 captured both directions of the canonical reversal day (6 entries). G5021 banked first TP2 of the run (+$34.50). 0 BULL_DAY_DIP_BUY entries confirmed (knob OFF). §11.4 cooldowns dominate ~440k of 508k signals; new gate `head_and_shoulders_cooldown` (803). |
| 2026-05-13 03:38 | (out-of-band) | Operator flagged second flicker: `account.balance` flips $10,596 ↔ $100,530.31. Implemented shared `stabilize_mt5_tester_overlay()` helper in `market_data.py`; wired into `bridge.py` + 5 athena_api endpoints. `make reload` (athena PID refreshed). Verified `/api/live` balance now stable at $100,530.31 across 6 polls (was alternating). Health probe: `MT5 data Age: 1s, balance=$100,530.31`. CHANGELOG.md updated. |
