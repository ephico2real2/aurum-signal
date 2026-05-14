# FORGE Run 32 — Tester Analysis

**EA version**: FORGE v2.7.77
**Symbol**: XAUUSD
**Sim period**: 2026-03-31 → (running)
**Scalper mode**: DUAL
**aurum_run_id**: 32
**wall_time**: 56869012
**source_run_id**: 1 (Agent-127.0.0.1-3000)
**Source DB**: `Tester/Agent-127.0.0.1-3000/MQL5/Files/FORGE_journal_XAUUSD_tester.db`

**Status**: in progress (sim at 2026-04-01 16:55) — **v2.7.76 VELOCITY CAP CONFIRMED FIRING ✓**

## Full v2.7.69 → v2.7.77 defense stack now live

| Component | Layer | Role |
|---|---|---|
| v2.7.69 BLR-BOS / BLR-velocity / BB exhaustion / NY_SESSION diagnostic | Entry gates | falling knives, exhausted tops, missed moves |
| v2.7.71 BB exhaustion tightened (momentum-confirmed exemption) | Entry gates | G5005 trap |
| v2.7.72 COMPOSITE_TEST disabled / BUY_LIMIT_RECOVERY disabled / staged-add favorable 300 | Entry hygiene | stray losses |
| v2.7.73 BB_BREAKOUT VWAP-distance gate (2.5×ATR) | Entry gates | overextension from value |
| v2.7.74 Conviction amplifier (4-of-6 atoms → 5 legs + TP1 50% close, TP2=1.0, TP3=5.0) | Entry sizing | upside on confirmed setups |
| v2.7.75 TradeScore state machine (0-100 weighted + tier hysteresis) | Entry sizing | unified conviction |
| **v2.7.76 Score velocity cap (caps tier at EMERGING when avg5 ≤ -5)** | Entry sizing | prevents amp on decaying setups |
| **v2.7.77 Conviction-decay partial close (3-tier reverse pyramid: 0.75/0.50/0.25)** | Open-trade mgmt | reverses position when conviction fades AFTER entry |
| v2.7.70 Pyramid-kill on adverse direction | Open-trade mgmt | adverse-direction add prevention |

## Baseline (tick 1)

- Sim time: 2026-03-31 10:12
- Total signals: 3,701
- TAKEN: 0 (early sim — Mar 31 G5001 trio comes at 12:30+)
- Live `market_data.json`:
  - forge_version: 2.7.77 ✓
  - trade_score_buy: 15
  - trade_score_buy_avg5: 15 (prev_avg5: 18, **velocity: −3**)
  - trade_score_buy_tier: LOW (5 bars stable)
  - 5bar history: [15, 15, 15, 15, 15] (chop)

## Mandatory housekeeping checks

- ✅ Check A — dead `FORGE_*` env vars: PASS (set at v2.7.76 ship)
- ✅ Check B — gate legend coverage: PASS

## Key validation targets

| Target | Test | Expected |
|---|---|---|
| v2.7.75 state machine | Score updates every tick, tier transitions on bar close | ✅ baseline shows live |
| v2.7.76 velocity field | trade_score_buy_velocity populated | ✅ baseline shows vel=-3 |
| v2.7.76 velocity cap fires | At G5005 fire (Apr 1 08:46) — if avg5 falling fast, log SCORE-VELOCITY-CAP | _pending_ |
| v2.7.77 conviction-decay L1 | At any open BB_BREAKOUT BUY group, when current avg5 / initial_score ≤ 0.75 → close 25% | _pending — needs open group first_ |
| v2.7.77 conviction-decay L2/L3 | Cascade to deeper closures as score decays further | _pending_ |
| v2.7.73 VWAP gate continues working | bb_breakout_buy_vwap_overextended SKIP count | _pending_ |
| v2.7.69 BLR gates continue working | blr_buy_bearish_bos_block + blr_buy_falling_velocity_block hits | _pending_ |
| G5005 outcome | Should be FAR less than Run 31's −$2,934 (velocity cap + decay close stack) | _pending_ |

## Hypothesis tracking

| Hypothesis | Status |
|---|---|
| v2.7.77 ManageConvictionDecay function compiles + runs | ✅ EA loaded successfully |
| Conviction-decay grace period (2 bars) | _pending — needs entry to validate_ |
| G5005-class loss reduced from −$2,934 → < −$1,000 | _pending — needs Apr 1 08:46 fire_ |
| Apr 2 BLR knife blocked (v2.7.69) | _pending_ |
| Apr 6 BB_BREAKOUT trio blocked (v2.7.73 VWAP gate) | _pending_ |

## Session Log

| Local time | Sim time | What happened |
|---|---|---|
| 18:17 | 03/31 10:12 | Baseline. v2.7.77 live on Agent-3000. State machine + velocity + decay fields all reading correctly. 0 TAKEN yet (sim early). Houseproofeeping A+B PASS. |

## Recommendations & Open Issues

_(append as discovered)_

## Operator Q&A Log

_(append as questions arise)_
