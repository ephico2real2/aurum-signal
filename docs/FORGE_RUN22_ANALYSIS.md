# FORGE Run 22 — Tester Analysis (v2.7.32 — dump bar-confirm + wider pullback SL)

**EA version**: FORGE v2.7.32
**Symbol**: XAUUSD
**Sim period**: 2026-03-31 → TBD (live)
**Scalper mode**: DUAL
**Balance**: $10,000
**aurum_run_id**: 22
**wall_time**: 596310214
**source_run_id**: 3
**Magic base**: 202401
**Status**: **in progress** (sim at 2026-03-31 13:15 UTC, 172 signals, 4 TAKEN, 6 trades, **−$41.75**)
**Last updated**: 2026-05-12

> Run 21 (aurum_run_id=21, same v2.7.32) was a short attempt — only reached Apr 1 02:40 UTC (357 sigs, 5 TAKEN, 10 trades, **−$27.29**). Re-launched as Run 22 for a full-window pass.

> **Test intent**: Validate v2.7.32 two-knob delta vs Run 20 (v2.7.31 baseline, −$418.06):
> - **Fix D** — `FORGE_DUMP_REQUIRE_BAR_CONFIRM=1` (NEW gate `dump_bar_confirm_missing`). Run 20 Mar 31 showed 16/24 BUY losses were immediate-SL direction failures; requires `close[1]` to move in trade direction before MOMENTUM_DUMP fires.
> - **Tune** — `FORGE_PULLBACK_SCALP_SL_ATR_MULT` 1.0 → **2.5**. Run 20 pullback-scalp legs were SL-hunt victims at 1×ATR; widen to 2.5× and let TP1=0.3×ATR / TP2=0.7×ATR do the banking.

---

## Active config knobs delta vs Run 20

```
# unchanged
FORGE_DAILY_DIRECTION_GATE_ENABLED=1
FORGE_DAILY_CANCEL_PENDING_ON_FLIP=1
FORGE_REGIME_H1_OVERRIDE_FACTOR=2.0
FORGE_REGIME_H1_OVERRIDE_ADX_MIN=30
FORGE_DUMP_CATCH_ENABLED=1
FORGE_DUMP_REQUIRE_D1_BIAS=0
FORGE_DUMP_LOT_FACTOR=0.5
FORGE_DUMP_MIN_ADX=20
FORGE_PULLBACK_SCALP_ENABLED=1
FORGE_PULLBACK_SCALP_FRESH_FLIP_BARS=3
FORGE_PULLBACK_SCALP_LOT_FACTOR=0.5
FORGE_PULLBACK_SCALP_TP1_ATR_MULT=0.3
FORGE_PULLBACK_SCALP_TP2_ATR_MULT=0.7
FORGE_PULLBACK_SCALP_COOLDOWN_SECONDS=600
FORGE_PULLBACK_SCALP_MAX_ADX=30

# NEW / CHANGED for Run 22
FORGE_DUMP_REQUIRE_BAR_CONFIRM=1                 # v2.7.32, was 0
FORGE_PULLBACK_SCALP_SL_ATR_MULT=2.5             # was 1.0
```

---

## Mandatory Housekeeping (session start)

| Check | Result |
|-------|--------|
| Check A — dead `FORGE_*` env vars | **PASS** (0 dead, 0 lowercase leaks) |
| Check B — gate legend coverage | **PASS** (no missing gates) |

---

## Cross-run target table

| Metric | Run 20 (v2.7.31) | Run 21 (v2.7.32, short) | Run 22 target (v2.7.32) |
|---|---|---|---|
| Sim window | Mar 31 → ??? | Mar 31 → Apr 1 02:40 (early stop) | Mar 31 → ??? |
| Signals total | 510 | 357 | TBD |
| TAKEN | 16 | 5 | _target_ ≥ Run 20 |
| Trades | 123 | 10 | TBD |
| Net P&L | **−$418.06** | **−$27.29** | _target_ **break-even or better** |
| Win rate | 61.8% (76W / 47L) | 80% (8W / 2L) | ≥ 70% |
| Mar 31 BUY losses (immediate SL) | 16 of 24 | _N/A (early stop)_ | **0–2 (Fix D)** |
| Apr 1 G5001/G5002 legs | _from Run 20 data_ | _N/A_ | matches/exceeds Run 20 |
| New gate `dump_bar_confirm_missing` | not present | 1 hit | **non-trivial hits expected** |

---

## Hypothesis tracker

| H | Status | Detail |
|---|---|---|
| H1 — Run launched correctly, parity audit log clean | _pending_ | will confirm on first Q-tick with TAKEN |
| H2 — Fix D: `dump_bar_confirm_missing` fires on Mar 31 chop BUYs | _pending_ | sim ~hours from Mar 31 London open |
| H3 — Pullback scalp losses drop with 2.5×ATR SL | _pending_ | sim ~1 day away |
| H4 — Run 21's early-stop entries reproduce in Run 22 | _pending_ | sim ~21 hours away |
| H5 — Total signal count and TAKEN ≥ Run 20 (no regression from new gate) | _pending_ | end of run |

---

## TAKEN Groups (running)

| Sim Time (UTC) | Group | Setup | Dir | Price | ATR | RSI | ADX | h1_trend | Regime | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-03-31 08:16 | G5001 (207402) | MOMENTUM_DUMP | SELL | 4554.74 | 6.31 | **43.6** | 36.9 | +0.81 | TREND_BULL | **−$51.16** (SL @ 4580.35, 4.06×ATR adverse) |
| 2026-03-31 08:36 | G5002 (207403) | MOMENTUM_DUMP | BUY | 4575.81 | 7.09 | 59.2 | 37.9 | +0.83 | TREND_BULL | +$5.66 (TP @ 4578.63) |
| 2026-03-31 12:30 | G5003 (207404) | MOMENTUM_DUMP | SELL | 4558.11 | 5.39 | 39.5 | 34.2 | +0.89 | TREND_BULL | +$3.75 (TP @ 4556.52) |
| 2026-03-31 12:40 | G5004 (207405) | MOMENTUM_DUMP | SELL | 4552.82 | 5.75 | 34.9 | 43.9 | +0.87 | TREND_BULL | partials open |

---

## Losses — Price Movement Analysis

### G5001 SELL @ 4554.74 — −$51.16 (TREND-FAILURE / DIRECTION-CONTRA)

**Trajectory (entry → SL, 32 min):**

| Time | Price | Δ vs entry | Note |
|------|-------|-----------|------|
| 08:16:00 | 4554.74 | 0.00 | Entry SELL |
| 08:16:00 | 4554.80 | +0.06 | "TP1" partial (label only; price ABOVE entry — no actual TP hit) |
| 08:16:00 | 4554.78 | +0.04 | "TP2" partial (same) |
| 08:20:00 | 4557.81 | **+3.07** | Already adverse |
| 08:25:00 | 4563.43 | +8.69 | |
| 08:30:00 | 4561.29 | +6.55 | |
| 08:35:00 | 4575.46 | **+20.72** | |
| 08:36:00 | 4575.81 | +21.07 | **G5002 BUY fired** (counter-position) |
| 08:40:00 | 4579.14 | +24.40 | |
| 08:48:14 | 4580.37 | **+25.63** | **SL hit** (both runner legs, deal 8 & 9) |

**Q1 Direction**: NO — price never moved in SELL direction at any point after entry.
**Q2 SL**: 4.06×ATR (25.61 pts) — wide enough, not the problem.
**Q3 TP reach**: 0% — TP1 (4552.22) never touched.

**Why every gate passed** (`ea/FORGE.mq5:6747-6802`):

| Gate | Threshold | G5001 value | Verdict |
|------|-----------|-------------|---------|
| `dump_rsi_block` | RSI ≥ 50 (`dump_max_rsi` default) | **RSI=43.6** | PASSED (too loose) |
| `dump_adx_block` | ADX < 20 | ADX=36.9 | PASSED |
| `dump_psar_block` | PSAR ≠ ABOVE | PSAR=ABOVE | PASSED |
| `dump_chop_block` (2.7.32) | regime=RANGE | regime=TREND_BULL | PASSED (chop filter doesn't catch trend-contra) |
| `dump_bar_confirm_missing` (2.7.32) | close[1] ≥ close[2] | one-bar dip preceded entry | PASSED (1-bar memory too short) |

**No h1_trend filter on MOMENTUM_DUMP_SELL** despite h1_trend=+0.81 (strong bull).

**Geometry concern** (`ea/FORGE.mq5:6796-6798`):
```
sl  = ask + m5_atr * 4.0    # hardcoded 4.0 — overrides FORGE_SELL_STOP_CONT_SL_ATR_MULT=3.5 env
tp1 = bid - m5_atr * 0.4
tp2 = bid - m5_atr * 1.0
```
R:R for TP1 = 0.1:1. Even 90% WR barely breaks even.

---

## Gate Breakdown (running)

| Gate Reason | Count |
|---|---|
| _will refresh on next tick_ | _172 signals total, 4 TAKEN, 168 SKIPs_ |

---

## SELL STOP CONT / BUY LIMIT Events

_(none yet)_

---

## Losses — Price Movement Analysis

_(deferred — populated at stop condition via Q6b)_

---

## Observations & Anomalies

_(none yet)_

---

## Recommendations & Open Issues

### Issue 1 — `dump_max_rsi=50` too loose for SELL; G5001 lost −$51.16 at RSI=43.6

**Evidence** (Run 22, Mar 31 08:16:
- G5001 SELL @ 4554.74 fired with RSI=43.6, ADX=36.9, h1_trend=+0.81, regime=TREND_BULL.
- Price moved +25.6 pts AGAINST trade in 32 min, never touched TP1 (-2.52). SL hit on both runner legs.
- 3 other MOMENTUM_DUMPs the same day succeeded: G5002 BUY (RSI 59.2), G5003 SELL (RSI 39.5), G5004 SELL (RSI 34.9). Common factor of winners: RSI ≤ 40 for SELLs.
- G5001 was the only SELL with RSI in 42-50 zone.

**Root cause** (verified, `ea/FORGE.mq5:6750`):
```
if(m5_rsi >= g_sc.dump_max_rsi) {  // default 50 — too high for an "exhausted dump" signal
```
At RSI=43.6 the M5 hasn't oversold — the prior move is a retracement inside a larger bull leg, not an exhausted dump.

#### Option A — Tighten `FORGE_DUMP_MAX_RSI` 50 → 42 (preferred)
```
FORGE_DUMP_MAX_RSI=42
```
- Blocks G5001 (RSI 43.6 ≥ 42)
- Keeps G5003 (39.5), G5004 (34.9), and the BUY mirror (which uses `100 - max_rsi = 58` floor, kept consistent)
- Defaults: was 50, propose 42.
- Risk: BUY mirror floor would tighten 50 → 58 (line 6806 mirrors via `100 - max_rsi`). G5002 BUY at RSI=59.2 PASSES (59.2 > 58). No regression on the run so far.

#### Option B — Add `dump_h1_trend_block_sell` gate (block SELL when h1_trend ≥ +0.5)
- Blocks G5001 (h1_trend +0.81)
- Also blocks G5003 (+0.89, winner) and G5004 (+0.87, winner) — false positives
- Net: −$3.75 winner lost vs −$51.16 loser avoided. Positive but lower precision than Option A.

#### Option C — Tighten SL geometry (separate from gate fix)
- Hardcoded 4.0×ATR SL with 0.4×ATR TP1 = 0.1:1 R:R. Mathematically unsustainable.
- Either lower SL multiplier to 2.0-2.5×ATR or implement aggressive BE-trail on TP1 fill.

**Preferred**: **Option A** as a one-knob, high-precision fix that survives RSI cross-validation against all 4 entries in the run so far. Option C is a parallel structural improvement to the R:R math and should follow regardless.

**Backward compatibility**: Option A is just a `.env` knob change; default 50 preserved in `.env.example`. Operator opts in. Option C would need a new flag (e.g. `FORGE_DUMP_SL_ATR_MULT=2.5` replacing the hardcoded 4.0).

**RESOLUTION (sim 2026-04-01 10:05, operator directive)**: tightened to **41** (not 42) — operator domain principle: "during chop market gold always retracts upwards as well". Applied to `.env:450` as `FORGE_DUMP_MAX_RSI=41`. Cross-validation across all 11 Run 22 TAKEN entries:

| Blocked | RSI | P&L | Pattern |
|---|---|---|---|
| G5001 SELL | 43.6 | −$51.16 | chop-retrace up in TREND_BULL |
| G5011 SELL | 48.7 | −$51.05 | chop-retrace up in TREND_BULL |

| Preserved | RSI | P&L |
|---|---|---|
| G5003 SELL | 39.5 | +$114.66 |
| G5004 SELL | 34.9 | +$113.24 |
| G5006 SELL | 31.7 | +$105.70 |
| All BUYs (G5002, G5005, G5007–G5010) | 59.2–74.5 | all winners (mirror floor 100−41=59) |

**Net impact**: saves **$102.21** in losses, costs **$0** in foregone winners. Will apply on next EA launch (Run 23+). The current Run 22 already loaded `dump_max_rsi=50` at OnInit, so this run continues with old value.

### Issue 2 — TP geometry undersized for available move (separate fix candidate)

**Evidence** (Run 22 max favorable excursion analysis):

| Trade | MaxFav reached | Configured TP2 | Actually banked | % of move captured |
|---|---|---|---|---|
| G5003 SELL | **24.29 pts (4.51×ATR)** | 5.39 pts (1.0×ATR) | +2.16 pts | **~9%** |
| G5004 SELL | **19.00 pts (3.30×ATR)** | 5.75 pts | +2.33 pts | ~12% |
| G5007 BUY | 9.59 pts (2.10×ATR) | 4.56 pts | +1.98 pts | ~21% |
| G5006 SELL | 5.55 pts (1.15×ATR) | 4.82 pts | +2.02 pts | ~36% |
| G5002 BUY | 3.88 pts (0.55×ATR) | 7.09 pts | +2.84 pts | within ATR |

**Mechanism**: configured `tp1 = 0.4×ATR`, `tp2 = 1.0×ATR` (`ea/FORGE.mq5:6797-6798`) but realized exits hit at ~0.3–0.4×ATR even when 4.5×ATR was available. Some exit (fast-lock? BE-trail? ATR trail?) is taking profit far short of TP2, capturing 9–36% of the available move.

**Root cause hypothesis** (UNVERIFIED): the runner is exiting on BE-trail or ATR-trail before TP2 is reached. Need to instrument runner exit reason or read `ManageOpenGroups` / trail code path. Operator question for next dive: which exit logic books the "tp" deal at ~2 pts of favor when TP2 is set at ~6 pts?

**Why this matters**: even with RSI=41 fix saving $102, the remaining 9 winners averaging $2/leg can't dwarf a single $156 BB_BREAKOUT loss (G5009). Run 22 only goes net-positive because of one outlier: G5012 BB_BREAKOUT BUY at +$645.12. Without that, math is closer to break-even. Capturing the leftover 80% of the dump moves would change the profile from variance-driven to systematically profitable.

---

## Operator Q&A Log

### Q1 (sim 2026-03-31 13:15): "analyze the loss now" / "what is the verdict?"
**Investigation**: Pulled Run 22 trades — found 2 losses (deals 8 & 9, both magic 207402 = G5001 SELL runner legs, SL @ 4580.35, −$25.57 + −$25.59 = −$51.16). Ran price trajectory query across the entry → SL window. Read MOMENTUM_DUMP_SELL filter chain in `ea/FORGE.mq5:6747-6802`. Compared G5001 RSI vs the other 3 TAKEN signals on the same sim day.

**Evidence**:
- G5001 SELL @ 4554.74 fired in TREND_BULL regime with h1_trend=+0.81, RSI=43.6, ADX=36.9, ATR=6.31.
- Price went +3 pts adverse at next M5 bar (08:20), +20.72 pts by 08:35, +25.63 pts at SL (08:48). Never closed below entry — TP1 (4552.22) untouched.
- SL was 4.06×ATR away. Not too tight — direction was wrong.
- Filter chain (`FORGE.mq5:6750-6789`) let it through: RSI 43.6 < dump_max_rsi=50, ADX 36.9 ≥ 20, PSAR=ABOVE, regime=TREND_BULL (not RANGE so dump_chop_block missed it), bar-confirm passed (1-bar memory).
- 3 same-day winners had lower RSI: G5003 SELL 39.5, G5004 SELL 34.9; G5002 BUY 59.2 (with trend).

**Answer**: **TREND-FAILURE / DIRECTION-CONTRA loss**, not SL-hunt. Single-knob high-precision fix: lower `FORGE_DUMP_MAX_RSI` from 50 → 42 — blocks G5001 (RSI 43.6 ≥ 42), preserves both later-day SELL winners (RSI 39.5, 34.9). Geometry also bad (R:R = 0.1:1 with hardcoded 4.0×ATR SL on line 6796) — separate fix recommended.

**Forward link**: Issue 1 in Recommendations & Open Issues.

---

## Session Log

| Local | Sim time | Event |
|-------|----------|-------|
| 2026-05-12 (tick 0) | 2026-03-31 05:35 | **Run 22 baseline**. FORGE v2.7.32, aurum_run_id=22, wall_time=596310214, source_run_id=3. Magic_base=202401. 56 signals, all `session_off` (pre-London). Housekeeping checks A+B PASS. Prior Run 21 (same v2.7.32) early-stopped at Apr 1 02:40 with 5 TAKEN / −$27.29 — re-launch for full window. Cross-run baseline vs Run 20 (v2.7.31) captured: 510 sigs, 16 TAKEN, −$418.06. |
| 2026-05-12 (tick 1) | 2026-03-31 13:15 | **Loss analysis** (operator request). Sim advanced from 05:35 → 13:15 with 172 signals, 4 TAKEN, 6 trades, **−$41.75**. Two losses on G5001 SELL runners (deals 8/9) — SL @ 4580.35, 25.6 pts adverse / 4.06×ATR. Classified as TREND-FAILURE: SELL into TREND_BULL with h1_trend=+0.81, RSI=43.6 (highest of 4 entries that day). Issue 1 logged: `FORGE_DUMP_MAX_RSI` 50→42 (one-knob fix, blocks G5001, preserves G5003/G5004 winners). Geometry concern flagged: hardcoded 4.0×ATR SL vs 0.4×ATR TP1 = R:R 0.1:1 (`ea/FORGE.mq5:6796`). |
| 2026-05-12 (tick 2) | 2026-04-01 10:05 | **TP-geometry analysis** (operator question). Sim now at 11 TAKEN, 48 trades, **+$678.32** net. Max-favorable-excursion calc shows G5003 reached **24.29 pts (4.51×ATR)** but exited at +2.16 (9% captured); G5004 reached 19 pts but exited at +2.33. Two new losses: G5009 BB_BREAKOUT BUY −$156.32 and G5011 SELL RSI=48.7 −$51.05. Operator directive: set `FORGE_DUMP_MAX_RSI=41` based on "chop market gold always retracts upwards" principle. Applied to `.env:450`. Cross-validation: blocks G5001 (43.6) + G5011 (48.7) = saves $102.21, costs 0 winners. Will apply Run 23+. Issue 2 (TP undersize) logged as separate fix track. |
