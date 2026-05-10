# FORGE Run 7 — Tester Analysis

**EA version**: FORGE v2.7.11  
**Symbol**: XAUUSD  
**Sim period**: 2026-04-29 → 2026-05-04 (6 trading days)  
**Scalper mode**: DUAL  
**Balance**: 10,000 (magic_base=202401)  
**aurum_run_id**: 7  
**wall_time**: 496414983  
**source_run_id**: 2 (TESTER_RUNS.id)

---

## Summary — FINAL
- Sim period: 2026-04-29 01:00 → 2026-05-04 23:55 UTC
- Total signals: 51,171
- TAKEN: 4 signals (5 actual groups incl. G5004 limit fill)  |  Skipped: 51,167
- Total P&L: **$257.58**
- Win rate: **100%** (10 wins / 0 losses)
- Best win: $57.68 (G5003 BUY Apr 30)
- Avg profit event: $25.76
- Athena cross-check: ✓ gate counts match, performance.total_pnl=$257.58 confirmed

---

## TAKEN Groups
| Sim Time (UTC) | Group | Direction | Session | RSI | ADX | ATR | Price | TP reached | P&L |
|----------------|-------|-----------|---------|-----|-----|-----|-------|-----------|-----|
| 2026-04-29 15:55 | G5001 (207402) | SELL | LONDON | 26.4 | 25.9 | 5.41 | 4545.06 | TP1+TP2+Final | +$80.32 |
| 2026-04-29 16:00 | G5002 (207403) | SELL | LONDON | 26.3 | 29.9 | 5.57 | 4545.17 | TP1+TP2+Final | +$20.54 |
| 2026-04-30 16:07 | G5003 (207404) | BUY  | LONDON | 54.6 | 23.0 | 7.00 | 4636.83 | TP1+TP2+Final | +$144.40 |
| 2026-05-04 13:05 | G5004 (207405) | SELL | LONDON | —    | —    | —    | —       | TP1+Final     | +$4.57 ⚑ |
| 2026-05-04 13:10 | G5005 (207406) | SELL | LONDON | 20.1 | 33.5 | 5.71 | 4548.77 | TP1+TP2+Final | +$7.75 |

*Note: G5001 P&L = deals 10+13 (43.60+36.72). G5002 P&L = deals 14+17 (10.86+9.68). G5003 P&L = deals 25+26+27 (57.68+45.44+41.28). G5004 P&L = deals 28+29 (0+4.57). G5005 P&L = deals 30+31+32+33 (0+0+5.49+2.26). Deals 13,17,27 use base magic 202401 for final close (known pattern).*  
*⚑ G5004 has no SIGNALS TAKEN row — opened via sell_limit companion fill path (see Observations).*

---

## Gate Breakdown (SKIP reasons, as of tick 5 / sim 2026-05-04)
| Gate Reason | Count | Human Label |
|-------------|-------|-------------|
| entry_quality_direction | 23,091 | <2 M5 bars moving in trade direction |
| entry_quality_body | 14,194 | Candle body too small — indecision |
| entry_quality_rsi_buy_ceil | 9,868 | RSI above BUY ceiling (all from May 1 rally) |
| entry_quality_bb_contraction | 2,909 | BB squeezing — no momentum |
| no_setup | 612 | Neither BB Breakout nor BB Bounce met |
| session_off | 477 | Outside London/NY |
| entry_quality_session_sell_cutoff | 4 | SELL after NY session sell cutoff (17:00 UTC) |
| entry_quality_adx_min_sell | 4 | ADX too low for breakout sell |
| entry_quality_rsi_sell_floor | 4 | RSI below sell floor |
| warmup_tester_m5_rollovers | 2 | M5 buffers not ready at backtest start |
| entry_quality_rsi_sell_adx_floor | 1 | RSI below stricter ADX-aware sell floor |
| rr_too_low | 1 | Risk:Reward below minimum |

---

## Recommended Parameter Changes — More Trades

**Context**: 51,171 signals evaluated, 4 TAKEN (0.008% take rate). Top 4 gates account for 50,062 SKIPs (~98% of all filtered signals).

### Current blocking gates → parameters

| Gate | Hits | Config key | Current | Proposed |
|------|------|------------|---------|---------|
| `entry_quality_direction` | 14,924 | `safety.min_directional_bars` | `2` | **`1`** |
| `entry_quality_body` | 14,194 | `safety.min_body_ratio` | `0.40` | **`0.25`** |
| `entry_quality_rsi_buy_ceil` | 9,868 | `bb_breakout.rsi_buy_ceil` | `70` | **`77`** |
| `entry_quality_bb_contraction` | 2,909 | `safety.require_bb_expansion` | `1` | **`0`** |

*Gate hit counts are from tick 1 (sim Apr 30) for direction/body/bb_contraction; rsi_buy_ceil counts are cumulative through tick 5.*

### Change 1 — `bb_breakout.rsi_buy_ceil`: 70 → 77
**Impact**: Would have caught the May 1 LONDON rally opening candle (RSI 74.9–79.2, +$34 move). At 77 the extreme candles (RSI 79–84.6) are still blocked, keeping protection against genuine overbought reversals.  
**Risk**: Low — only relaxes the upper RSI band for BB_BREAKOUT BUYs. The Apr 30 BUY at RSI=54.6 already passes comfortably; this change only affects high-momentum breakout days.  
**Do not raise above 80** — RSI=84 entries on XAUUSD carry real mean-reversion risk.

### Change 2 — `safety.min_directional_bars`: 2 → 1
**Impact**: Largest single gate by count (14,924 hits). Dropping from 2 confirming bars to 1 captures the breakout candle itself rather than always entering one bar late.  
**Risk**: Medium — more entries into early setups before direction is fully confirmed. Watch for whipsaw losses on choppy sessions. Recommend testing this in isolation before combining with Change 3.

### Change 3 — `safety.min_body_ratio`: 0.40 → 0.25
**Impact**: Second-largest gate (14,194 hits). A 40% body minimum blocks many valid XAUUSD breakout bars that have upper/lower wicks. 25% still rejects pure dojis and spinning tops.  
**Risk**: Medium — more entries on thin-body bars. Pairs well with Change 2; both address the same root issue (overly strict candle quality filter for a volatile instrument like Gold).

### Change 4 — `safety.require_bb_expansion`: 1 → 0
**Impact**: Third-largest gate (2,909 hits). Disabling allows entries in early-stage breakouts before the bands fully open. Useful for catching the first bar of a squeeze resolution.  
**Risk**: Lower — do this after validating Changes 1–3. Early-squeeze entries add noise but the `bb_breakout.adx_min=20` gate still filters out directionless conditions.

### Hidden filter to be aware of
`bb_breakout.require_macd_buy = 1` (overridden from default `0`). This requires MACD confirmation on every BUY entry; failures surface as `no_setup` (612 hits, not its own gate_reason). If BUY count is still low after applying Changes 1–3, consider reverting this to `0` — but do it as a separate run to isolate the effect.

### Apply order
1. Change 1 (`rsi_buy_ceil` 70→77) — standalone, lowest risk, addresses the single largest missed opportunity
2. Changes 2+3 together (`min_directional_bars` + `min_body_ratio`) — test as a pair, monitor for loss rate increase
3. Change 4 (`require_bb_expansion`) — add after 2+3 are validated
4. `require_macd_buy` 1→0 — only if BUY frequency still insufficient after above

> **Note**: `scalper_config.json` is generated — do not hand-edit. Changes go via `.env` or the config template, then `make scalper-env-sync && make forge-compile`.

---

## SELL STOP CONT / BUY LIMIT Events
| Event | Group | Slot | RSI | Price | Result |
|-------|-------|------|-----|-------|--------|
| SELL STOP CONT placed | G5001 | slot[2] | 28.4 | 4537.72 | filled/cancelled (ticket no longer pending) |
| BUY LIMIT skipped | G5001 | — | 28.4 | — | RSI=28.4 < min=35.0, Bull Support not confirmed |
| SELL STOP CONT placed | G5002 | slot[3] | 28.3 | 4537.32 | filled/cancelled (ticket no longer pending) |
| BUY LIMIT skipped | G5002 | — | 28.3 | — | RSI=28.3 < min=35.0, Bull Support not confirmed |
| ArmPostTP1Ladder — SELL STOP skipped | G5005 | — | 16.2 | — | RSI=16.2 ≤ 25.0, exhausted (sim: 2026-05-04 13:11) ✓ confirmed |
| BUY LIMIT skipped | G5005 | — | 16.2 | — | RSI=16.2 < min=35.0, Bull Support not confirmed ✓ confirmed |

---

## Losses
None as of current sim time.

---

## Observations & Anomalies

### [TICK 3] May 1 missed BUY — `entry_quality_rsi_buy_ceil` blocked a 34-pt LONDON rally
**Window**: 2026-05-01 17:00–17:20 UTC | **Gate**: `entry_quality_rsi_buy_ceil` | **Skips**: 9,868

| Candle | Skips | RSI range | Price range |
|--------|-------|-----------|-------------|
| 17:00–17:05 | 2,845 | 74.9–79.2 | 4625.80–4638.45 |
| 17:05–17:10 | 3,438 | 75.8–79.9 | 4632.78–4640.56 |
| 17:15–17:20 | 3,585 | 76.9–84.6 | 4649.38–4660.26 |

Total move: +34.46 pts in 20 min. RSI ceiling ~70; Apr 30 BUY at RSI=54.6 passed fine. This breakout was immediately above the ceiling and stayed there. Candidate fix for next config: raise `rsi_buy_ceil` to 75–77 for BB_BREAKOUT setups, or make the ceiling setup-type-aware (stricter for BB_BOUNCE, looser for BB_BREAKOUT).

### RSI sell floor below default
SELL signals at RSI 26.4 and 26.3 were TAKEN. The `entry_quality_rsi_sell_floor` gate blocked RSI=16.1 and RSI=21.1, meaning the configured floor is approximately 22–25 (lower than the default 33). This is intentional EA parameter configuration — not a bug. The memory warning from Run 10/11 (FORGE 2.6.7) about SL hits at RSI<30 may or may not apply at these levels under 2.7.11 logic.

### G5003 dual TP1 closes (deals 22, 23)
Both deal 22 and deal 23 show comment `SCALP|BB_BREAKOUT|G5003|TP1`. Similarly, deals 25 and 26 both close with magic=207404 and comment `tp 4643.63` at the same timestamp. Consistent with DUAL-mode managing two simultaneous positions within the same group — not suspicious.

### G5001/G5002 SELL STOP CONT "no longer pending"
Slots armed and then immediately "filled or external cancel" at the same sim tick. Need more trades data to confirm whether these continuation orders were actually filled (appear in TRADES) or just expired/cancelled.

### [TICK 5] G5004 — trades present, no SIGNALS TAKEN row (sell_limit fill path)
G5004 (magic 207405) shows a complete trade lifecycle in TRADES (TP1 at 13:05:00, final close at 13:05:13, profit $4.57) but has no corresponding row in SIGNALS with outcome='TAKEN'. The SIGNALS table only has one TAKEN entry for the May 4 13:00-13:15 window: G5005 at 13:10:02. G5004 is most likely the `sell_limit_enabled` companion order — when a SELL BB_BREAKOUT fires, FORGE places a SELL LIMIT at entry - ATR×0.4 with `sell_limit_lot_factor=0.125`. That limit fill opens a trade under the next group magic but bypasses signal logging. Not a bug per se, but a gap in SIGNALS coverage for limit-fill opens. Impact: SIGNALS TAKEN count (4) understates actual groups opened (5) by 1.

### [TICK 5] New gate: `entry_quality_session_sell_cutoff` (4 hits)
First seen in May 4 session. Blocks SELL entries after `session_ny_sell_cutoff_utc=17` UTC. Expected as the NY session ages past the cutoff hour.

### [TICK 5] RSI sell floor refined: ~18–20 (not 22–25)
At 13:10:00: `entry_quality_rsi_sell_adx_floor` blocked RSI=17.8 (ADX-aware stricter floor). At 13:10:02: RSI=20.1 TAKEN. At 13:15:00: `entry_quality_rsi_sell_floor` blocked RSI=15.9. Floor is in the 18–20 range, not 22–25 as initially estimated.

### Base magic final closes (deals 13, 17, 27)
Final closes record magic=202401 (base) instead of group magic. Known pattern — see memory `project_magic_number_fix.md`.

---

## Session Log

### 2026-05-10 (monitoring session start)
- DB: Agent-3000, 11MB, WAL active
- Baseline (tick 0): run_id=2, wall_time=496414983, FORGE 2.7.11 DUAL, sim_start=2026-04-29, 20,763 signals, 2 TAKEN
- aurum_run_id=7 confirmed in aurum_tester.db
- Tick 1 (sim: 2026-04-30 19:05): 23,154 signals (+2,391), 3 TAKEN (+1 G5003 BUY), P&L=$245.26, 0 losses
- Sync lag: 3,828 (within normal range, bridge keeping up)
- Tick 2 (sim: 2026-05-01 14:25): 24,404 signals (+1,250), no new TAKEN, P&L flat
- Tick 3 (sim: 2026-05-01 21:50): 42,324 signals (+17,920), no new TAKEN — NEW GATE `entry_quality_rsi_buy_ceil` appeared with 9,868 hits all from May 1 17:00–17:20 LONDON rally (+34.46 pts, RSI 74.9–84.6). BUY ceiling ~70 blocked entire move.
- Tick 4 (sim: 2026-05-04 12:15): 42,858 signals (+534), TAKEN still 3. Sim skipped May 2–3 weekend. New gates: none yet. Watching for G5005 at 13:11.
- Tick 5 (sim: 2026-05-04 18:55): 51,111 signals (+8,253), TAKEN=4 (+G5005 SELL 13:10 RSI=20.1 +$7.75). G5004 SELL LIMIT fill adds +$4.57 (no SIGNALS row). ArmPostTP1Ladder G5005 confirmed — SELL STOP exhausted RSI=16.2, BUY LIMIT skipped RSI=16.2. New gates: `entry_quality_session_sell_cutoff` (4), `entry_quality_rsi_sell_adx_floor` (1). P&L=$257.58.
- Tick 6 (sim: 2026-05-04 23:55): +60 signals, Asian session lull. No new trades. P&L flat.
- Tick 7 (sim: 2026-05-04 23:55): 0 new signals. DB frozen. WAL 0 bytes. 2nd consecutive zero tick.
- Tick 8 (sim: 2026-05-04 23:55): 0 new signals. **STOP CONDITION MET** (3 consecutive zero ticks). Run complete. Athena cross-check passed. Gate codes confirmed in cheat sheet.
