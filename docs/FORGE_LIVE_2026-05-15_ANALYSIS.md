# FORGE LIVE Monitoring — 2026-05-15

**Mode**: LIVE (scribe DB + market_data.json)
**Symbol**: XAUUSD
**Account**: $100,712.77 (Vantage International Demo)
**Status**: in progress
**EA in MT5**: 🔴 **v2.7.121** (v2.7.122 P1 compiled at 11:37 but NOT YET LOADED — operator action pending)

## Summary (running)

- 24h signals: 58,472 total, **9 TAKEN** (0.015% take rate)
- All 9 TAKENs direction-correct on a clear bear day (4601 → 4528, −73 pts in 8.5h)
- 1 BUY (ASIA_CAPITULATION_BUY at 03:02 ASIAN), 8 SELLs (MOMENTUM_DUMP family, London + NY)
- BUY_LIMIT_RECOV (post-TP1 mechanism) fired on G5005 → **filled +$88.50** ✅
- G5008 cluster -$955.44 SL loss at 12:29:17 (canonical P1 fix target)
- Open positions: 0, Pending orders: 0

## Critical flags

### 🔴 v2.7.122 P1 NOT YET LIVE — MT5 needs FORGE reload

`market_data.json` reports `forge_version: 2.7.121`. The v2.7.122 `FORGE.ex5` is on disk (compiled 11:37, 569 KB) but MT5 is still running the prior build. Operator action required:
- MT5: remove FORGE from chart → drag FORGE from Navigator onto chart (or restart MT5)
- Then `make forge-verify-live` to confirm version flip

Until reloaded:
- `FORGE_RECOVERY_PRE_TP1_ENABLED=1` is dormant
- The G5008-class loss (below) has no recovery arm
- All other v2.7.121 logic continues as-is

### 🔴 G5008 -$955.44 cluster loss at 12:29:17 — canonical P1 target

```
11:49:55  G5008 MOMENTUM_DUMP SELL opens 2×0.18 lot @ 4528.40 (NY KZ)
12:29:17  Both legs SL @ 4554.99/4555.00 = -$477.36 / -$478.08

Price trajectory: 4528 → 4555 = +26.6 pts ADVERSE (no MFE down)
Adverse / ATR ≈ 1.9× (entry_atr ~14)
```

This is the **exact bad-trade-state P1 was designed to catch**. With v2.7.122 live:
- Adverse breached 1.5×ATR threshold (P1 trigger) sometime between 11:55-12:15
- P1 would have armed a SELL_LIMIT @ ~current_ask + 0.3×ATR ≈ 4555 area
- Lot 0.5 × lot_fixed = 0.125 (broker-floored to ~0.13)
- SL: 4569, TP: 4541 (1×ATR each side of LIMIT)
- TP path is ~14 pts back toward entry — a typical retrace after a 26-pt counter-move

Cost of running v2.7.121 instead of v2.7.122 on this single trade: **opportunity to net ~$180 against the -$955 loss**.

### 🟡 PEMCG asymmetry 38× SELL-heavy on confirmed bear day

```
pemcg_sell_reversal_block:  5,868
pemcg_buy_reversal_block:     152
Ratio: 38.6× SELL-HEAVY
```

Day-type verification (visual price action): 4601 → 4528 = confirmed bear day. **PEMCG_SELL is over-blocking direction-correct continuation SELLs** — exactly the v2.7.105 DTC modifier's purpose.

DTC stack confirmed ON in `.env`:
- `FORGE_COMPOSITE_DTC_ENABLED=1`
- `FORGE_COMPOSITE_DTC_PEMCG_MODIFIER_ENABLED=1`
- `FORGE_COMPOSITE_DTC_DAY_BIAS_BLOCK_ENABLED=1`
- `FORGE_COMPOSITE_DTC_5STATE_ENABLED=1`
- `FORGE_COMPOSITE_DTC_GEOMETRY_WIDEN_ENABLED=1`

DTC modifier reduces PEMCG impact but doesn't zero it out — calibration question (not a blocker). Track over coming days whether v2.7.122 P1 lowering the cost of "bad-state SELLs" reduces the effective penalty of these blocks.

## TAKEN Groups (24h, all direction-correct on bear day)

| Local time | Setup | Dir | Price | RSI | ADX | Session | Magic | Outcome |
|---|---|---|---:|---:|---:|---|---|---|
| 03:02:30 | ASIA_CAPITULATION_BUY | BUY | 4601.21 | 40.4 | 27.3 | ASIAN | 202401 | pending |
| 05:55:11 | MOMENTUM_DUMP | SELL | 4570.29 | 40.2 | 28.1 | LONDON | 202401 | pending |
| 06:17:31 | MOMENTUM_DUMP | SELL | 4554.69 | 38.9 | 42.2 | LONDON | 202401 | pending |
| 10:02:40 | MOMENTUM_DUMP | SELL | 4549.50 | 41.0 | 33.3 | NY | 202401 | pending |
| 11:02:33 | MOMENTUM_DUMP | SELL | 4541.62 | 39.5 | 34.0 | NY | 202401 | pending |
| 11:07:22 | MOMENTUM_DUMP | SELL | 4543.57 | 40.9 | 34.2 | NY | 202401 | G5005 partials + BUY_LIMIT_RECOV +$88 |
| 11:10:00 | MOMENTUM_DUMP | SELL | 4538.10 | 36.9 | 36.3 | NY | 202401 | G5006 partials |
| 11:40:54 | MOMENTUM_DUMP | SELL | 4531.01 | 37.1 | 33.5 | NY | 202401 | G5007 +$172 |
| 11:49:55 | MOMENTUM_DUMP | SELL | 4528.40 | 38.1 | 38.7 | NY | 202401 | **G5008 -$955** |

## Gate Breakdown (24h, top 15)

| Gate | Count | Read |
|---|---:|---|
| `regime_countertrend` | 23,077 | BUY blocks in bear regime (correct on this day) |
| `asia_capitulation_buy_cooldown` | 17,806 | BUY cooldown after the 03:02 ASIA_CAP fire |
| `pemcg_sell_reversal_block` | 5,868 | **Over-blocking — see flag above** |
| `ma_crossover_adx_below_min` | 5,400 | ADX gate (chop filter) |
| `sr_flip_adx_below_min` | 2,890 | Same |
| `dirlock_block_sell` | 1,197 | DirLock cooldown on SELLs |
| `inside_bar_adx_below_min` | 895 | ADX gate |
| `trendline_bounce_adx_below_min` | 585 | ADX gate |
| `orb_adx_below_min` | 180 | ADX gate |
| `pemcg_buy_reversal_block` | 152 | Correctly small (BUYs against bear) |
| `no_setup` | 149 | — |
| `rr_too_low` | 81 | — |
| `dump_rsi_block` | 53 | MOMENTUM_DUMP RSI filter |
| `entry_quality_atr_ext` | 24 | — |
| `dump_bar_confirm_missing` | 14 | — |

## Recovery Mechanism Health Check (post-TP1 path — already enabled)

**BUY_LIMIT_RECOVERY** (operator: ON, lot factor 0.5, expiry 8 bars from earlier tweak):
- G5005 fired 11:09:06 → filled 11:18:43 (~10 min in window) → +$88.50 ✅
- Recovery slot magic 227415 (group_magic 207405 + 20009 + 1)
- v2.7.117 safety TP applied (no `tp=0` orphan)

Demonstrates the post-TP1 mechanism is healthy AT THE NEW SETTINGS. The 0.25→0.5 lot factor tweak gave us ~$88 here vs the previous ~$44.

## Session Log

### 14:36 local — Tick 0 (LIVE MODE init)

- LIVE MODE entered per operator `start live mon`
- Baseline captured: 58,472 signals, 9 TAKEN, 0 open / 0 pending
- Latest signal 14:36:49, last TAKEN 11:49:55 (~2.8h ago)
- Services 4/4 up (bridge, listener, aurum, athena)
- Scribe DB 202 MB healthy
- **Flagged**: forge_version=2.7.121 in market_data.json — v2.7.122 NOT LOADED
- **Flagged**: G5008 -$955 loss cluster — canonical P1 target
- **Flagged**: PEMCG asymmetry 38× SELL-heavy on bear day
- Created this doc

## Recommendations & Open Issues

### Issue 1 — v2.7.122 P1 not yet loaded into running EA

**Evidence**: `market_data.json:forge_version = "2.7.121"`. The .ex5 was compiled at 11:37 (FORGE.ex5 569 KB on disk) but MT5 is still running the prior load. The pre-TP1 recovery code is sitting in the binary but inactive.

**Root cause**: MT5 caches the loaded `.ex5` per chart and doesn't auto-reload when the file changes on disk. Operator must manually drag FORGE off → back on the chart.

**Action**: Operator drags FORGE off chart → drag from Navigator back onto chart. Then run `make forge-verify-live` to confirm version flip. No code change needed.

**Backward compat**: N/A — this is the activation step for the already-shipped feature.

### Issue 2 — G5008 -$955 loss validates P1 design fit

**Evidence**: G5008 SELL @ 4528.40 (11:49:55) → SL @ 4555 (12:29:17). Adverse 26.6pt ≈ 1.9×ATR with no MFE down — textbook P1 trigger condition.

**Root cause**: pre-v2.7.122 has no mechanism to arm recovery orders when primary is underwater and never hits TP1.

**Action**: ship is complete and code is shipped (commit `fce2f11`). Activation depends on Issue 1 resolution.

## Operator Q&A Log

_(empty so far this session)_
