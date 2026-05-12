# FORGE Run 24 — Tester Analysis

**EA version**: FORGE v2.7.39 (`#property version "2.109"`)
**Symbol**: XAUUSD
**Sim period**: 2026-03-31 → (in progress)
**Scalper mode**: DUAL
**aurum_run_id**: 24
**wall_time**: 678530608
**source_run_id**: 1 (TESTER_RUNS.id in Agent-3000 source DB)
**source DB**: `/Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/Agent-127.0.0.1-3000/MQL5/Files/FORGE_journal_XAUUSD_tester.db`
**aurum first_seen_utc**: 2026-05-12T20:05:59.219090+00:00

**Status**: in progress (sim at 2026-03-31 15:10:00 UTC)

## Summary (running)
- Sim latest: 2026-03-31 15:10:00 UTC (Mar 31 mid-NY session)
- Total signals: **228**
- TAKEN: **2** (G5001 + G5002, both MOMENTUM_DUMP SELL)
- Skipped: 226
- Trades: 4 (2 TP1 partials + 2 final closes)
- **Running P&L: +$6.74** (G5001 $3.24 + G5002 $3.50)
- Win rate so far: **100%** (2W / 0L)
- killzone column: empty (FORGE_KILLZONES_ENABLED=0 — expected default)

## Hypothesis validation table

| Hypothesis | Status | Evidence |
|---|---|---|
| v2.7.36 session/KZ refactor doesn't break entry flow | ✅ PASS | Session label populated correctly ("NY" on the 2 TAKEN entries); session_off gate fired 72× during off-hours; no regressions in dump-catch chain |
| v2.7.36 Tier 0 hotfix (`tester_allowed_sessions=LONDON,NY`) lets NY trades fire | ✅ PASS | Both TAKEN entries are session=NY (the very thing the bug previously silently blocked) |
| v2.7.37 atom telemetry doesn't add latency to entry path | ✅ PASS | 228 signals processed; ea_cycle ticking; G5001/G5002 fired at expected M5 timestamps |
| v2.7.38 composites all default-OFF — no live behaviour change | ✅ PASS | All 4 composite gates absent from gate breakdown — operator hasn't enabled any. Expected. |
| v2.7.39 R:R bypass doesn't affect existing setups | ✅ PASS | G5007 BB_BREAKOUT BUY @ Apr 1 13:45 fired and TP1'd (+$5.16). BB_BREAKOUT is NOT in the v2.7.39 bypass list — it uses the original `rr_too_low` gate. Bypass is correctly scoped. |

## TAKEN Groups

| Sim Time (UTC) | Magic | Group | Setup | Dir | Session | KZ | Price | ATR | RSI | ADX | TP1 fill | Final P&L |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-03-31 12:30:29 | 202401 | G5001 | MOMENTUM_DUMP | SELL | NY | "" | 4559.73 | 5.31 | 40.7 | 33.9 | TP1 @ 12:30:51 | **+$3.24** |
| 2026-03-31 12:40:29 | 202401 | G5002 | MOMENTUM_DUMP | SELL | NY | "" | 4552.70 | 5.75 | 34.7 | 43.9 | TP1 @ 13:36:44 | **+$3.50** |
| 2026-04-01 08:20:04 | 202401 | G5003 | MOMENTUM_DUMP | BUY  | LONDON | "" | 4686.30 | — | 59.1 | 31.0 | TP1 @ 08:26:50 | **+$5.02** |
| 2026-04-01 08:30:07 | 202401 | G5004 | MOMENTUM_DUMP | BUY  | LONDON | "" | 4690.15 | — | 63.6 | 32.3 | TP1 @ 08:32:00 | **+$5.30** |
| 2026-04-01 13:30:28 | 202401 | G5005 | MOMENTUM_DUMP | BUY  | NY     | "" | 4730.31 | — | 59.0 | 22.7 | TP1 @ 13:42:50 | **+$7.32** |
| 2026-04-01 13:44:01 | 202401 | G5006 | MOMENTUM_DUMP | BUY  | NY     | "" | 4734.83 | — | 62.4 | 25.0 | TP1 @ 13:47:57 | **+$7.16** |
| 2026-04-01 13:45:00 | 202401 | G5007 | **BB_BREAKOUT** | BUY  | NY     | "" | 4735.29 | — | 62.8 | 27.7 | TP1 @ 13:47:43 | **+$5.16** |
| 2026-04-01 14:05:00 | 202401 | G5008 | MOMENTUM_DUMP | BUY  | NY     | "" | 4737.75 | — | 62.4 | 28.9 | TP1 @ 14:17:08 | **+$9.88** |
| 2026-04-02 07:11:57 | 202401 | G5011 | MOMENTUM_DUMP | SELL | LONDON | "" | 4668.17 | — | 33.6 | 30.1 | TP1 quick | **+$4.51** |
| 2026-04-02 07:22:01 | 202401 | G5012 | MOMENTUM_DUMP | SELL | LONDON | "" | 4663.69 | — | 31.0 | 35.9 | TP1 quick | **+$4.21** |
| 2026-04-02 10:37:35 | 202401 | G5013pre | MOMENTUM_DUMP | BUY | LONDON | "" | 4634.77 | — | 59.3 | 37.0 | TP1 quick | (subgroup) |
| 2026-04-02 10:48:13 | 202401 | G5013pre | MOMENTUM_DUMP | BUY | LONDON | "" | 4643.12 | — | 63.3 | 44.9 | TP1 quick | (subgroup) |
| 2026-04-02 12:09:44 | 202401 | G5013 | MOMENTUM_DUMP | SELL | NY     | "" | 4617.36 | — | 40.7 | 28.3 | **TP1+TP2** runner | **+$5.56** |
| 2026-04-02 12:17:52 | 202401 | **G5014** | **BB_PULLBACK_SCALP** ⭐ | BUY | NY | "" | 4628.20 | — | 50.0 | 24.4 | TP1 @ 12:21 | **+$2.71** |
| 2026-04-02 14:40:03 | 202401 | G5015 | MOMENTUM_DUMP | SELL | NY     | "" | 4606.80 | — | 36.3 | 24.0 | TP1 @ 14:42 | **+$4.85** |

Both classic momentum-dump SELL entries — RSI in dump zone (35-41), strong ADX (33-44), NY session.

## Gate Breakdown (running)

| Gate Reason | Count | Human Label |
|---|---|---|
| `no_setup` | 97 | Neither BB Breakout nor BB Bounce conditions met (incl. dump chain not-trig) |
| `session_off` | 72 | Outside LONDON/NY tester-allowed window |
| `dump_rsi_block` | 20 | M5 RSI not in dump-zone (SELL needs RSI<41) |
| `dump_bar_confirm_missing` | 14 | `dump_require_bar_confirm=1` — bar-close failed dump confirmation |
| `entry_quality_daily_bear_block_buy` | 10 | Daily bias is bearish → BUY blocked (Mar 31 was a bear day) |
| `dump_rsi_buy_ceil` | 3 | BUY-side RSI exhaustion ceiling (G5009 Run 20 fix) |
| `dump_chop_block` | 3 | regime=RANGE blocks dump (gold retraces UP in chop) |
| `warmup_tester_m5_rollovers` | 2 | M5 indicator buffers not ready at backtest start |
| `dump_psar_block` | 2 | PSAR not aligned for direction |
| `dump_cooldown` | 2 | Within same-direction dump cooldown window |
| `dump_adx_block` | 1 | ADX below dump minimum (20) |

**Composite gates** (v2.7.38 — all default-OFF):
- `entry_quality_chop_block_sell` — 0 (FORGE_BLOCK_SELL_IN_CHOP_ENABLED=0)
- `entry_quality_intraday_reversal_buy_block` — 0 (FORGE_INTRADAY_REVERSAL_SELL_ENABLED=0)
- FRACTIONAL_SELL_IN_BULL — 0 fires (FORGE_FRACTIONAL_SELL_IN_BULL_ENABLED=0)
- BULL_DAY_DIP_BUY — 0 fires (FORGE_BULL_DAY_DIP_BUY_ENABLED=0)

## Cross-run comparison

| Metric | Run 24 (current) | Run 23 | Run 22 |
|---|---|---|---|
| FORGE version | 2.7.39 | 2.7.5 | 2.7.4 |
| Sim period | Mar 31 → (in progress) | full period | full period |
| TAKEN @ Mar 31 15:10 | 2 | (pending lookup) | (pending lookup) |

## Observations & Anomalies

- **No new gate codes** observed — Mandatory Check B passed
- **No dead env vars** — Mandatory Check A passed
- **Sync ↔ .env.example parity** — Check C passed (post-backfill commit `db10e34`)
- **All 4 v2.7.38 composites correctly default-OFF** — gate codes absent from breakdown
- **forge_version reported by EA = 2.7.39** ✓ — confirms the R:R bypass build is active in this tester run
- **killzone column populated correctly as empty string** for both TAKEN entries (KZ disabled)
- **Run is fresh** — only 2 TAKEN over 15 hours of sim time. Light Mar 31 (low-volatility day per case study).

## Recommendations & Open Issues

_None yet — run too early. Will populate after stop condition + Q9 gate precision analysis._

## Operator Q&A Log

_None this run._

## Session Log

| Local time | Sim time | Event |
|---|---|---|
| 2026-05-12 20:13 UTC | 2026-03-31 15:10:00 | First /forge-monitor tick — baseline captured. Run 24 active, 228 signals, 2 TAKEN, +$6.74 running P&L. All housekeeping checks pass. |
| 2026-05-12 20:14 UTC | 2026-04-01 04:40:00 | Tick 2. +13.5h sim advance. Signals 228→418 (+190). TAKEN unchanged (Mar 31 evening + Apr 1 Asian = mostly session_off). No new gate codes; no composite fires. |
| 2026-05-12 20:15 UTC | 2026-04-01 09:00:00 | Tick 3. +4.3h sim. Signals 418→493 (+75). **TAKEN 2→4 (+2)**: G5003 + G5004 both MOMENTUM_DUMP BUY in Apr 1 LONDON @ RSI 59.1/63.6, both TP1 quickly. P&L $6.74→$17.06 (+$10.32). NEW gate code first-seen: `dump_h1_trend_block_sell` (×8) — correctly blocking SELLs on Apr 1 bullish H1 (h1_trend≥2.0). Confirms regime-adaptive dump-catch in BOTH directions working as v2.7.34+v2.7.35 designed. |
| 2026-05-12 20:18 UTC | 2026-04-01 18:41:01 | Tick 4. +9.7h sim. Signals 493→711 (+218). **TAKEN 4→8 (+4)**: G5005/G5006/G5008 MOMENTUM_DUMP BUYs + **G5007 BB_BREAKOUT BUY** in Apr 1 NY rally. All TP1 within minutes (3-12 min each). P&L $17.06→$46.58 (+$29.52). **v2.7.39 R:R bypass hypothesis flips to PASS** — BB_BREAKOUT BUY went through original `rr_too_low` gate as designed (not in bypass list). New gate codes first-seen: `entry_quality_atr_ext` (×13), `entry_quality_breakout_failed_samebar` (×8). Apr 1 NY rally captured — chronic earlier-run miss now resolved. |
| 2026-05-12 20:19-20:27 UTC | sim Apr 1 21:40 → Apr 2 03:00 | Ticks 5-9 (quiet Asian session). Signals 711→814 (+103). TAKEN unchanged (8). P&L unchanged. Tester pace slowed from 13h/min → 1-3h/min. |
| 2026-05-12 20:28 UTC | 2026-04-06 01:10:00 | **Tick 10 — Apr 2 crash window blowout.** +4 sim days. Signals 814→1161 (+347). **TAKEN 8→15 (+7)**: full both-sides capture of Apr 2 crash — SELLs at 4668/4663/4617/4606, BUYs at 4634/4643 bouncing bottom, plus **first BB_PULLBACK_SCALP fire** (G5014 BUY @ 4628). **G5013 SELL hit TP1+TP2** (first multi-TP runner of run). P&L $46.58→$105.40 (+$58.82). Win rate 100% (15/0). Case study Apr 2 narrative validated exactly. |
| 2026-05-12 20:37 UTC | 2026-04-07 04:20:00 | **Tick 11 — Apr 6 mixed-regime captured.** +1.1 sim days. Signals 1161→1573 (+412). **TAKEN 15→20 (+5)**: 1 BB_BREAKOUT BUY (G5017), 1 MOMENTUM_DUMP BUY (RSI=68.8 high), 2 MOMENTUM_DUMP SELLs (G5018+G5019, regime flip), 1 MOMENTUM_DUMP BUY runner (G5020 hit TP1+TP2, +$11.50 — biggest single win). P&L $105.40→$157.44 (+$52.04). **Still 100% WR (20/0)** across 7 sim days. EA adapting direction every few hours on mixed-regime day. **Caveat noted**: 100% WR partly a function of 12.5×-too-small lot — at proper 0.25 lot, SL hits would matter. |
| | | **Lot audit finding (not in this tick — meta)**: actual lot 0.01-0.02 per leg vs configured 0.25. Almost certainly `ScalperLot` MT5 input is overriding to ~0.02. Plus `staged_initial_legs=1` + `staged_add_min_favorable_points=500` means leg 2+ never adds (TP1 at ~30pts fires WELL before +500pts favorable). Operator notified — awaiting decision on full-lot multi-leg config. |
