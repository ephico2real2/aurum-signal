# FORGE Run 31 — Tester Analysis

**EA version**: FORGE v2.7.75
**Symbol**: XAUUSD
**Sim period**: 2026-03-31 → (running)
**Scalper mode**: DUAL
**aurum_run_id**: 31
**wall_time**: 55215312
**source_run_id**: 1 (Agent-127.0.0.1-3000)
**Source DB**: `Tester/Agent-127.0.0.1-3000/MQL5/Files/FORGE_journal_XAUUSD_tester.db`

**Status**: in progress (sim at 2026-04-02 23:30) — **CRITICAL: amplifier backfired on G5005**

## What v2.7.75 brings vs Run 30 (v2.7.70)

| Feature shipped | Component |
|---|---|
| v2.7.71 BB_BREAKOUT exhaustion gate tightened (BOS exemption requires momentum) | (queued in stack since 30 paused) |
| v2.7.71 NY_SESSION_BEARISH diagnostic SKIPs + loosened kz_max_min=120 + min_velocity=1.0 | included |
| v2.7.72 COMPOSITE_TEST disabled + staged_add favorable 300 + BUY_LIMIT_RECOVERY disabled | included |
| v2.7.73 BB_BREAKOUT VWAP-distance gate (2.5×ATR) | included |
| v2.7.74 conviction amplifier (4-of-6 atoms → 5 legs + TP1 50% close) + TP2=1.0 + TP3=5.0 | included |
| **v2.7.75 TradeScore state machine** (5-bar weighted score + tier hysteresis) | **NEW** |

## Mandatory housekeeping checks (session start)

- ✅ Check A — dead `FORGE_*` env vars: PASS
- ✅ Check B — gate legend coverage: PASS

## Baseline (tick 1)

- Sim time: 2026-03-31 14:44
- Total signals: 9,832
- TAKEN: **3** (all MOMENTUM_DUMP SELL, Mar 31 12:30/12:35/12:41 G5001-G5003 trio)
- Live `market_data.json` trade score: tier=LOW, score=50, avg5=29, 5bar=[40,20,15,30,40], bars=2

## TAKEN Groups (running)

| Sim Time | Magic | Setup | Dir | Price | RSI | ADX | h1 | Session |
|---|---|---|---|---|---|---|---|---|
| 03/31 12:30:29 | 207402 | MOMENTUM_DUMP | SELL | 4559.45 | 40.7 | 33.9 | +0.90 | NY |
| 03/31 12:35:00 | 207403 | MOMENTUM_DUMP | SELL | 4557.36 | 38.0 | 38.9 | +0.88 | NY |
| **03/31 12:41:17** | 207404 | MOMENTUM_DUMP | SELL | 4554.13 | **37.1** | 43.9 | +0.87 | NY | G5003-class, RSI 37.1 > 37.0 threshold by 0.1 → not blocked |

## Hypothesis tracking

| Hypothesis | Status |
|---|---|
| TradeScore state machine computes every tick | ✅ PASS — live in market_data.json |
| Tier hysteresis works (2-bar persistence) | ✅ PASS — tier_bars=2 stable at LOW |
| 5-bar ring buffer populates | ✅ PASS — [40,20,15,30,40] |
| Apr 1 G5005 BB_BREAKOUT BUY blocked by v2.7.73 VWAP gate | _pending — Apr 1 08:45 not yet reached_ |
| Apr 1 G5004/G5013 BB_BREAKOUT BUY fires with HIGH tier (5-leg amplification) | _pending_ |
| Apr 2 BLR knife blocked by v2.7.69 BLR gates | _pending — Apr 2 not yet reached_ |
| Apr 2 morning descent captured by NY_SESSION_BEARISH (v2.7.71 loosened thresholds) | _pending_ |
| Apr 8 G5032 BLR_BUY 8-leg pyramid blocked | _pending — Apr 8 not yet reached_ |
| **v2.7.69 G5003-RSI fix catches the 12:40 entry** | ❌ FAIL — G5003 fired at RSI 37.1 (threshold 37.0, off by 0.1). Need 38.0 in v2.7.76 |

## Critical issues surfaced

### Issue (NEW) — G5003 RSI threshold still too tight by 0.1
- Run 30 G5003 RSI was 36.01 → bumped to 37.0 in v2.7.69
- Run 31 G5003 RSI is 37.1 → 0.1 above the new threshold, still fires
- The RSI value varies slightly across runs (price ticks slightly different)
- **Fix**: bump `dump_sell_late_rsi_block` from 37.0 → 38.0 OR 39.0 (add safety margin)
- OR tighten ADX threshold from 42 to 40 (G5003 has ADX 43.9 — would still trigger with 40 threshold)
- Recommended: combine both — `dump_max_adx=40 AND dump_sell_late_rsi_block=38.0`

## Session Log

| Local time | Sim time | What happened |
|---|---|---|
| 17:50 | 03/31 14:44 | Baseline. v2.7.75 fresh on Agent-3000. 3 TAKEN MOMENTUM_DUMP SELL trio. Trade score state machine LIVE in market_data.json (tier=LOW, score=50). G5003 fired again at RSI 37.1 — v2.7.69 threshold 37.0 still too tight. Housekeeping checks both PASS. |

## Recommendations & Open Issues

### Issue 1 — dump_sell_late_rsi_block needs another bump
- v2.7.69 raised 36.0 → 37.0; Run 31 G5003 fired at 37.1
- Bump to 38.0 for safety margin OR also lower dump_max_adx 42→40
- Defer to v2.7.76 ship (along with Nyao-inspired improvements)

### Issue 2 (CRITICAL) — Conviction amplifier backfired on G5005, +$1,240 worse than Run 30

**Evidence (from MT5 log + DB)**:
- 04/01 08:40 G5004 BB_BREAKOUT BUY fired tier=ULTRA score=40 avg5=76 → **7 legs** → +$556 win
- 04/01 08:46 G5005 BB_BREAKOUT BUY fired tier=HIGH score=20 avg5=63 → **5 legs** → **−$2,934 loss** (5× $587 each)
- Run 30 same group fired 3 legs → −$1,694
- **Run 31 amplified loss by $1,240 by deploying 5 legs instead of 3**

**Root cause (verified)**:
- `ea/FORGE.mq5:12022+` — conviction amplifier uses `g_regime.trade_score_buy_tier` for sizing
- Tier driven by `trade_score_buy_avg5` (5-bar smoothing)
- At G5005 fire: current score = 20 (LOW), but avg5 = 63 (HIGH) — score had DECAYED from 76 → 20 in 6 min
- Smoothing masked the rapid decline → tier stayed HIGH → amplified leg count

**Mechanism**: smoothing is good against tick flicker but bad against rapid decay. The 5-bar avg lags the truth when score crashes.

#### Option A (recommended) — Add score velocity gate
```mql5
// Before amplifying, check if score is RISING or FALLING:
int prev_avg5 = g_regime.trade_score_buy_5bar[3];  // previous bar's avg5 ≈ index 3
int score_velocity = g_regime.trade_score_buy_avg5 - prev_avg5;
if (score_velocity < 0 && tier == "HIGH" || tier == "ULTRA") {
    tier = "EMERGING";  // cap amplification when score is falling
}
```
Defaults: enabled by default. Risk: minor — only caps UPSIDE on declining setups.

#### Option B — Tighten VWAP gate 2.5 → 2.0
G5005 VWAP_dist was ~2.5×ATR (just under threshold). 2.0 catches it.
Risk: blocks G5013 EMERGING winner (also probably 1.8-2.0). Net neutral or negative.

#### Option C — Disable conviction amplifier
`FORGE_SETUP_BREAKOUT_BUY_CONVICTION_ENABLED=0`. Falls back to 3-leg standard. Loses G5004 upside (+$556 with 7 legs would become +$240 with 3 legs).
Risk: undo all the bull-rally amplification.

**Preferred**: Option A (score velocity gate). Catches the specific decay pattern without losing G5004 ULTRA opportunity. Aligns with Nyao Scalper canonical pattern.

**Backward compatibility**: ship behind `FORGE_GATE_BREAKOUT_BUY_SCORE_VELOCITY_CHECK=1` (default ON). Existing v2.7.75 behavior preserved if knob = 0.

**Industry pattern** (per Nyao Scalper, file at `/Users/olasumbo/Downloads/nyao_scalper.mq5:1499-1517`):
```mql5
double velocity = strength.finalScore - prevScore;   // signed: rising vs falling
double normalizedVelocity = (vel + window) / (2.0 × window);  // maps to 0-1
```
Used in Nyao's tier decision — falling score blocks higher tiers.

### Issue 3 (informational) — TP3 staging not yet observed
- No "TP2 reached — promoted N runner(s) to TP3" log entries yet
- All BB_BREAKOUT BUYs in Run 31 either won at TP1 or hit SL — none reached TP2 at 1.0×ATR
- Expected: with v2.7.74 TP2=1.0×ATR (vs old 1.5×ATR), some legs should reach it. Either ATR is high enough that 1.0×ATR is still distant, or all legs banked at TP1 quickly.
- Will continue watching Apr 6+ for sustained rallies.

## Operator Q&A Log

_(append as questions arise)_
