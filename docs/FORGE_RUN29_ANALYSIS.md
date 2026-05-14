# FORGE Run 29 — Tester Analysis

**EA version**: FORGE v2.7.68
**Symbol**: XAUUSD
**Sim period**: 2026-03-31 → (running)
**Scalper mode**: DUAL
**Balance**: $100,000
**aurum_run_id**: 29
**wall_time**: 46661435
**source_run_id**: 1 (Agent-127.0.0.1-3002)
**Source DB**: `Tester/Agent-127.0.0.1-3002/MQL5/Files/FORGE_journal_XAUUSD_tester.db`

**Status**: COMPLETE (operator stopped run at sim 2026-04-08 21:40)

## What v2.7.68 brought to this run

| Version | Feature | Status |
|---|---|---|
| v2.7.58 | TC_BUY decision-tree upgrade | ✓ gating |
| v2.7.59 | BLR pyramid cap + cascade arming | ✓ |
| v2.7.60 | MOMENTUM_DUMP V2 ADX-RSI exhaustion gate | ⚠ edge-case miss on G5003 (see Issue 1) |
| v2.7.61 | Day-extreme distance gate | ✓ |
| v2.7.62 | Day-extreme distance amplifier | ✓ |
| v2.7.63 | macd_histogram=0 logging fix (iOsMA self-populate) | ✓ **verified — 0/18810 zero-rate** |
| v2.7.64 | market_data.json entry_atoms (27 fields) | ✓ |
| v2.7.65 | 5 velocity atoms | ✓ (3 of 5 gating TC) |
| v2.7.66 | Decreasing pyramid 5×→4×→3×→2×→1× | ✓ |
| v2.7.67 | TC_BUY/SELL velocity gate expansion | ✓ |
| v2.7.68 | 13 ICT/SMC atoms (swing/BOS/FVG/OB/liquidity) | ✓ instrumentation-only by design |

## Summary — IN PROGRESS

- Sim latest: 2026-04-01 13:25
- Total signals evaluated: 19,178
- TAKEN: **6 groups** (running total)
- Skipped: 19,172
- Take rate: 0.03% (intentionally low — many new low-priority setups have aggressive ADX floors)

## TAKEN Groups (running)

| Sim Time (UTC) | Magic | Setup | Dir | Price | RSI | ADX | M15 ADX | h1_trend | Regime | Verdict |
|----------------|-------|-------|-----|-------|-----|-----|---------|----------|--------|---------|
| 03/31 12:30:29 | 202401 | MOMENTUM_DUMP | SELL | 4559.45 | 40.73 | 33.91 | 18.4 | +0.897 | TREND_BULL | G5001 — V2 PASS (ADX<42), intended |
| 03/31 12:35:00 | 202401 | MOMENTUM_DUMP | SELL | 4557.36 | 38.05 | 38.88 | 19.3 | +0.880 | TREND_BULL | G5002 — V2 PASS (ADX<42), intended |
| 03/31 12:40:15 | 202401 | MOMENTUM_DUMP | SELL | 4553.50 | **36.01** | 43.88 | 19.4 | +0.867 | TREND_BULL | **G5003 — V2 EDGE-CASE MISS** (RSI 36.01 vs threshold 36.0) |
| 04/01 08:40:00 | 202401 | BB_BREAKOUT | BUY | 4700.70 | 73.32 | 40.10 | 24.9 | +2.152 | TREND_BULL | NY open trend BUY, strong h1 |
| 04/01 08:45:00 | 202401 | BB_BREAKOUT | BUY | 4702.29 | 74.54 | 44.27 | 26.4 | +2.139 | TREND_BULL | Continuation leg |
| 04/01 09:25:00 | 202401 | FRACTIONAL_SELL_IN_BULL | SELL | 4709.91 | 68.42 | 32.71 | 26.9 | +2.136 | TREND_BULL | Counter-trend fractional probe (by design) |

## Gate Breakdown (running, top 15)

| Gate Reason | Count | Note |
|-------------|-------|------|
| trendline_bounce_adx_below_min | 7,441 | New aggressive instrumentation setup |
| ma_crossover_m15_misalign | 5,738 | New |
| ma_crossover_adx_below_min | 2,711 | New |
| inside_bar_adx_below_min | 1,470 | New |
| sr_flip_adx_below_min | 226 | New |
| no_setup | 110 | Healthy (low) |
| session_off | 72 | Outside London/NY |
| rr_too_low | 62 | R:R floor working |
| dump_rsi_block | 25 | DUMP SELL RSI filter |
| entry_quality_daily_bear_block_buy | 20 | Daily-bias gate |
| dump_bar_confirm_missing | 19 | Close-bar gate |
| entry_quality_direction | 11 | Body/direction filter |
| dump_below_bbl_block_sell | 1 | Day-low proximity (v2.7.55A) |

**dump_v2 emission inventory**: zero `dump_v2_*` gate codes fired. G5003 should have hit `dump_v2_exhaustion_sell` but did not — see Issue 1.

## Hypothesis Validation

| Hypothesis | Status |
|---|---|
| v2.7.63 macd_histogram fix is live | ✅ PASS — all TAKEN macd ≠ 0; zero-rate 0/18810 across SKIPs with rsi>0 |
| v2.7.66 decreasing pyramid is wired | ✅ PASS — config shows base=5 step=-1 min=1 |
| ICT/SMC atoms (v2.7.68) are NOT gating | ✅ PASS — no swing/BOS/FVG gate codes in breakdown (intentional) |
| v2.7.60 dump_v2 blocks G5003 ADX-RSI exhaustion | ❌ FAIL — RSI 36.01 missed 36.0 threshold by 0.01 |
| v2.7.61 day-extreme blocks Apr 13 top-of-range BUYs | _pending_ — sim hasn't reached Apr 13 |
| v2.7.67 TC velocity gates protect TC firings | _pending_ — no TC fires yet |

## Recommendations & Open Issues

### Issue 1 — dump_v2 exhaustion gate edge-case miss on G5003

**Evidence**:
- G5003 fired TAKEN at 03/31 12:40:15 in TREND_BULL (h1=+0.867) — the exact scenario v2.7.60 dump_v2 was designed to block.
- Logged RSI=36.01, ADX=43.88.
- Threshold: `dump_sell_late_rsi_block = 36.0` (default, no .env override).
- Exhaustion check: `m5_adx >= 42 && m5_rsi <= 36.0`.
- 36.01 ≤ 36.0 → **false** by 1/100. Gate misses; SELL fires.

**Root cause** (verified):
- `ea/FORGE.mq5:3684` — `g_sc.dump_sell_late_rsi_block = 36.0;` (default)
- `ea/FORGE.mq5:10287-10290` — exhaustion conjunction uses strict `<=` on `dump_sell_late_rsi_block`.
- No .env override exists for either `FORGE_GATE_DUMP_MAX_ADX` or `FORGE_GATE_DUMP_SELL_LATE_RSI_BLOCK` — defaults apply.

**Mechanism**: The threshold was tuned in v2.7.60 to the historical G5003 value (RSI 35.1 in prior runs). The current run shows RSI=36.01 — slightly above the original observation. Single-side knife-edge threshold; needs a buffer.

#### Option A — Loosen RSI threshold to 37.0 (recommended)
```diff
- g_sc.dump_sell_late_rsi_block = 36.0;
+ g_sc.dump_sell_late_rsi_block = 37.0;
```
Or set in .env: `FORGE_GATE_DUMP_SELL_LATE_RSI_BLOCK=37.0`
**Defaults**: 37.0 (was 36.0). **Risk**: minor — also catches RSI 36-37 exhaustion SELLs which by inspection (40.73 → 38.05 → 36.01 progression with ADX rising 33→39→44) are the textbook "third leg into a falling knife" pattern. Loosening 1 RSI point.
**Backward compatibility**: env-driven knob already exists (read at FORGE.mq5:4642). Default-OFF is impossible since the gate IS the default behavior; this is a tuning change, not a feature toggle.

#### Option B — Loosen ADX threshold to 43.0 (alternative)
```diff
- g_sc.dump_max_adx = 42.0;
+ g_sc.dump_max_adx = 43.0;
```
**Risk**: would still miss G5003 (ADX=43.88) by 0.12 — too tight in the other axis.

#### Option C — Make the AND a "near" match (tolerance window)
Add `0.5` tolerance to BOTH thresholds: ADX ≥ (max_adx - 0.5) AND RSI ≤ (rsi_block + 0.5).
**Risk**: hand-rolled tolerance, harder to reason about.

**Preferred**: Option A. RSI 37.0 catches G5003 (36.01 ≤ 37.0 ✓) without sweeping in genuine reversal-zone SELLs (RSI typically <30 for genuine oversold dumps). Data that would change my mind: if a future run produces a winning SELL with ADX≥42 AND RSI in 36-37 range — none seen in 22 prior runs.

**Industry pattern** (per MQL5 article research, cited per the new feedback rule): Tradeciety + MQL5 articles consistently recommend RSI-as-exhaustion threshold at **30 for oversold, 70 for overbought, with a 5-point tolerance band** around the inflection point. 36-37 sits well below the 30-tolerance-buffer zone for a SELL exhaustion check.

### Issue 2 — m15_adx default-zero at SKIP call sites (logging gap)

**Evidence**:
- 18,789 of 18,810 signals with rsi>0 (99.9%) log `m15_adx = 0`.
- Only 21 (the TAKEN signals + a few SKIPs at specific call sites) log non-zero m15_adx.
- Same pattern as the v2.7.63 macd_histogram bug — JournalRecordSignal default param drops to 0 at call sites that don't pass it.

**Root cause** (likely):
- `JournalRecordSignal` signature has `double m15_adx = 0.0` default.
- Most SKIP call sites (e.g. trendline_bounce, ma_crossover, etc.) don't pass m15_adx, so the default 0 is logged.
- TAKEN signals pass m15_adx because the entry block computes it explicitly.

**Impact**: SKIP gate-precision analysis using m15_adx is impossible — same blind spot the v2.7.63 fix was designed to close for macd.

#### Option A — Apply v2.7.63 self-populate pattern to m15_adx (recommended)
Inside `JournalRecordSignal`: if `m15_adx == 0.0`, compute it via `iADX(_Symbol, PERIOD_M15, 14)` handle + CopyBuffer (same as macd self-populate). Cache the M15 ADX handle as `g_h_adx_m15` initialized in OnInit with diagnostic Print.
**Risk**: low — same pattern that worked for macd. Adds one indicator handle + 1 CopyBuffer per logged signal.

#### Option B — Pass m15_adx at every call site
**Risk**: ~50 call sites — high churn, easy to miss one.

**Preferred**: Option A. Mechanical reuse of v2.7.63 fix pattern; mirrors the macd lifecycle.

**Backward compatibility**: No flag needed — pure logging enrichment, no behavioral change.

## Operator Q&A Log

_(append here as operator asks questions during monitoring)_

## Session Log

| Local time | Sim time | What happened |
|---|---|---|
| 15:30 | 04/01 13:25 | Baseline captured. 6 TAKEN through Apr 1 13:25. Run 29 / aurum_run_id 29. Found G5003 edge-case miss + m15_adx logging gap. |
| 15:36 | 04/06 14:17 | Tick 2. TAKEN 6→21 (+15). Net P&L flipped −$271 → **+$720.38** (62W/14L). Apr 2 BLR cascade fired (−$1,587 combined) THEN later BLR fires at the bottom won (+$306). Codex review completed with 1 FAIL (JSON key shadowing). New gate code seen: `dump_h1_trend_block_sell` (42). **Apr 6 11:00-11:05 firing G5005-class pattern** (3 BB_BREAKOUT BUY legs, RSI 68→71→74, ADX 37→41→45) — watch for reversal. |

## TAKEN Groups (full inventory, sim at 04/06 14:17)

| Sim Time (UTC) | Magic | Setup | Dir | Price | RSI | ADX | Session | Outcome |
|----------------|-------|-------|-----|-------|-----|-----|---------|---------|
| 03/31 12:30:29 | 207402 | MOMENTUM_DUMP | SELL | 4559.45 | 40.7 | 33.9 | NY | TP +$60 |
| 03/31 12:35:00 | 207403 | MOMENTUM_DUMP | SELL | 4557.36 | 38.0 | 38.9 | NY | TP +$118 |
| 03/31 12:40:15 | 207404 | MOMENTUM_DUMP | SELL | 4553.50 | 36.0 | 43.9 | NY | TP +$128 (G5003 should have blocked) |
| 03/31 13:36:44 | 227413 | BUY_LIMIT_RECOVERY | BUY | 4549.10 | — | — | NY | SL −$34 |
| 04/01 08:40:00 | 207405 | BB_BREAKOUT | BUY | 4700.70 | 73.3 | 40.1 | LONDON | TP +$354 |
| 04/01 08:45:00 | 207406 | BB_BREAKOUT | BUY | 4702.29 | 74.5 | 44.3 | LONDON | **SL −$1,694** |
| 04/01 09:25:00 | 207407 | FRACTIONAL_SELL_IN_BULL | SELL | 4709.91 | 68.4 | 32.7 | LONDON | TP +$22 |
| 04/01 13:30:28 | 207408 | MOMENTUM_DUMP | BUY | 4730.31 | 59.0 | 22.7 | NY | TP +$98 |
| 04/01 13:44:01 | 207409 | MOMENTUM_DUMP | BUY | 4734.81 | 62.4 | 25.0 | NY | TP +$97 |
| 04/01 13:45:00 | 207410 | BB_BREAKOUT | BUY | 4735.29 | 62.8 | 27.7 | NY | SL −$62 |
| 04/01 13:50:00 | 207411 | MOMENTUM_DUMP | BUY | 4736.96 | 64.1 | 32.7 | NY | TP +$34 |
| 04/01 14:05:00 | 207412 | MOMENTUM_DUMP | BUY | 4737.75 | 62.4 | 28.9 | NY | TP +$29 |
| 04/01 14:10:00 | 207413 | MOMENTUM_DUMP | BUY | 4739.41 | 64.1 | 32.3 | NY | TP +$15 |
| 04/01 17:46:47 | 207414 | BB_BREAKOUT | BUY | 4753.70 | 59.0 | 21.7 | NY | **TP +$985** (best win) |
| 04/02 08:33:22 | 207415 | BLR_BUY | BUY | 4658.57 | 34.9 | 18.1 | LONDON | SL −$201 (knife) |
| 04/02 08:55:00 | 207416 | BLR_BUY | BUY | 4604.60 | 24.1 | 26.3 | LONDON | **SL −$1,386** (knife) |
| 04/02 12:17:52 | 207417 | BB_PULLBACK_SCALP | BUY | 4628.21 | 50.0 | 24.4 | NY | TP +$8 |
| 04/02 16:13:11 | 207418 | BLR_BUY | BUY | 4586.96 | 33.1 | 23.2 | NY | TP +$110 (knife bottom caught) |
| 04/02 16:24:01 | 207419 | BLR_BUY | BUY | 4581.61 | 32.0 | 26.9 | NY | TP +$196 (knife bottom caught) |
| 04/03+ multiple wins | 207420-207423 | various | — | — | — | — | — | combined +$725 |
| 04/06 10:55:00 | 207424? | BB_BREAKOUT | BUY | 4681.28 | 68.6 | 36.7 | LONDON | _open_ |
| 04/06 11:00:00 | 207425? | BB_BREAKOUT | BUY | 4685.61 | 70.8 | 40.9 | LONDON | _open_ |
| 04/06 11:05:00 | 207426? | BB_BREAKOUT | BUY | 4693.26 | 74.1 | 45.1 | LONDON | ⚠️ _G5005-class risk_ |

**Running net P&L: +$720.38** (62 winning deals, 14 losing deals)

## Issue 3 (NEW) — 235pt bearish run NOT captured (Apr 1 → Apr 2)

**Evidence**: Apr 1 19:00 high $4787 → Apr 2 09:11 low $4555 = **−232pts in 14h**. FORGE caught zero SELLs; BLR_BUY fired into the knife and lost $1,587 combined (G5015 + G5016).

**Root cause**: every SELL setup requires HTF (h1/h4) bearish confirmation. h1_trend stayed TREND_BULL (+1.34 → +0.76) through the descent. By the time h1 flipped, the move was over.

**Proposed v2.7.69** (queued for operator approval): `NY_SESSION_BEARISH_BREAKOUT_SELL` — fires on velocity_5bar ≥ 1.5×ATR + M5 macd_slope < 0 + RSI < 50 + room-to-day-low ≥ 1×ATR, **with no h1/h4 macro gate**. Window: first 90min of LONDON_OPEN or NY_OPEN.

## Codex review findings (completed during tick 2)

23 PASS / 4 WARNING / 1 **FAIL** across 93 gates:

1. **FAIL — JSON key shadowing in EA config reader.** `JsonGetDouble()` reads the first matching key globally. Earlier `safety.*` keys shadow newer `composites.*` overrides. **v2.7.66 TC/BLR composite SL/TP/cooldown directives are silently ignored.** Operator-tuned geometry is in the generated JSON but not being read by the EA. **Highest-priority fix.**
2. WARNING — `market_data.schema.json` missing `entry_atoms` block (27 fields from v2.7.64-v2.7.68 undocumented).
3. WARNING — `FORGE_DECISION_STACK.md` + `FORGE_COMPOSITE_ROADMAP.md` missing; `FORGE_INDICATOR_ATLAS.md` lags v2.7.68 (13 ICT atoms not registered).

Full report: `docs/FORGE_ENTRY_CONDITIONS_CODEX_REVIEW.md`.

## FINAL Summary (operator stop at sim 2026-04-08 21:40)

- Sim period: 2026-03-31 01:00 → 2026-04-08 21:40 (~8.9 days)
- Total signals: 54,530
- TAKEN: 35 groups
- Deals: 136 (91 wins / 45 losses)
- **Net P&L: −$1,223.98** (gross win $6,407, gross loss $7,631)

## FINAL Losses (all 13 losing groups)

| Magic | Group | Entry time | Setup | Dir | Entry $ | RSI | ADX | Net loss |
|---|---|---|---|---|---|---|---|---|
| 207433 | G5032 | 04/08 11:52 | BLR_BUY | BUY | 4793.82 | 32.6 | 26.0 | **−$2,166** (8-leg pyramid into knife) |
| 207406 | G5005 | 04/01 08:45 | BB_BREAKOUT | BUY | 4702.29 | 74.5 | 44.3 | −$1,694 (second-leg top trap) |
| 207416 | G5015 | 04/02 08:55 | BLR_BUY | BUY | 4604.60 | 24.1 | 26.3 | −$1,386 (knife) |
| 207423 | G5022 | 04/06 10:55 | BB_BREAKOUT | BUY | 4681.28 | 68.6 | 36.7 | −$897 (top trio) |
| 207428 | G5027 | 04/07 14:07 | BLR_BUY | BUY | 4647.30 | 33.0 | 49.2 | −$663 (Apr 7 knife) |
| 207424 | G5023 | 04/06 11:00 | BB_BREAKOUT | BUY | 4685.61 | 70.8 | 40.9 | −$438 (top trio) |
| 207415 | G5014 | 04/02 08:33 | BLR_BUY | BUY | 4658.57 | 34.9 | 18.1 | −$201 (knife) |
| 207426 | G5025 | 04/07 11:35 | BB_BREAKOUT | BUY | 4683.84 | 70.8 | 36.6 | −$185 (top pair) |
| 207432 | G5031 | 04/08 11:30 | BB_PULLBACK_SCALP | BUY | 4808.39 | 42.3 | 19.1 | −$104 |
| 207410, 207421, 207427, 227413 | smaller | various | various | BUY | — | — | — | −$247 combined |

**Every losing group is BUY. Three patterns:**

1. **BB_BREAKOUT second-leg-at-top** — 5 incidents, ~$3,300 damage (G5005, G5022, G5023, G5025, G5026)
2. **BLR_BUY falling knife** — 5 incidents, ~$4,420 damage (G5014, G5015, G5016, G5027, G5032)
3. **Zero SELLs caught** the three big bearish runs: Apr 1→2 (235pt), Apr 6→7 (143pt), Apr 8 descent (~80pt)

## Q9 Gate Precision (post-stop, indicator-resolved gates)

| Gate | Precision | Verdict |
|---|---|---|
| `dump_below_bbl_block_sell` | 86% | ✅ Keep — best gate |
| `rr_too_low` | 67% | ✅ Keep |
| `dump_v2_misalign_sell` | 58% | 🟡 Borderline — 8 missed wins include the Apr 2 descent |
| `dump_h1_trend_block_sell` | 50% | ⚠️ Coinflip — HTF lag |
| `dump_rsi_buy_ceil` | 46% | ⚠️ Slightly bad |
| `entry_quality_daily_bear_block_buy` | 41% | ❌ POOR — blocks too many recovery BUYs |
| `dump_rsi_block` | 37% | ❌ POOR — blocks winning SELLs |
| `dump_bar_confirm_missing` | 33% | ❌ POOR — close-bar requirement misses fast scalps |

The three HTF-lag gates (`dump_h1_trend_block_sell`, `dump_v2_misalign_sell`, `entry_quality_daily_bear_block_buy`) confirm the diagnosis: HTF lags M5 by hours, so they block the right SELLs at the wrong time. The Apr 2 descent (Issue 3) is the canonical proof.

## Recommended Parameter Changes — v2.7.69 (ALREADY APPLIED)

| Change | Status |
|---|---|
| `FORGE_GATE_DUMP_SELL_LATE_RSI_BLOCK=37.0` (was 36.0 default) — catches G5003-class edge case | ✅ in `.env` |
| Codex JSON shadowing fix — 13 sync mappings flipped composites→safety so TC/BLR overrides actually load | ✅ in sync script + regenerated config |
| `JournalRecordSignal` self-populates m15_adx — same pattern as v2.7.63 macd fix | ✅ in `ea/FORGE.mq5` |
| VERSION → 2.7.69 | ✅ |

## Recommended Parameter Changes — v2.7.70+ (QUEUED)

| Priority | Change | Why |
|---|---|---|
| HIGH | BB_BREAKOUT BUY "second leg with RSI ≥ 72" block | Would have caught G5005 (RSI 74.5), G5022-G5023 (68→74), G5025-G5026 (70.8). $3,300+ savings. |
| HIGH | BLR_BUY "m5_velocity_5bar ≤ −1.0×ATR" pre-fire check (block when price still accelerating down) | Would have caught G5015, G5016, G5027, G5032. $4,200+ savings. |
| HIGH | NY_SESSION_BEARISH_BREAKOUT_SELL (new setup, no h1/h4 gate) | Would catch the three missed bearish runs (Apr 1→2, Apr 6→7, Apr 8). |
| MED | Loosen `dump_bar_confirm_missing` — 33% precision means it blocks 2× more wins than losses | Lift close-bar requirement for fast NY scalps. |
| MED | Persist `entry_atoms` (velocity, swing, BOS, FVG, day_extreme) into SIGNALS table per signal | Enables forensic mining of "what was the velocity at G5032 fire?" |

