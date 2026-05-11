# FORGE Run 10 — Tester Analysis

**EA version**: FORGE v2.7.11  
**Symbol**: XAUUSD  
**Sim period**: 2026-04-29 → (in progress)  
**Scalper mode**: DUAL  
**Balance**: 10,000 (magic_base=202401)  
**aurum_run_id**: 10  
**wall_time**: 509255158  
**source_run_id**: 1 (TESTER_RUNS.id)

**First run with full Run 10 config (31 env overrides):**
- `tp1_buy_atr_mult=0.5` / `tp1_sell_atr_mult=0.4` (direction-split TP1)
- `tp1_close_pct=60` (close 60% at TP1)
- `tp3_atr_mult=2.5` (live TP3 staging after TP2 hit)
- `adx_lot_factor_mid/high=1.0` (SELL lot bug fixed — full lot at ADX>35)
- `staged_initial_legs=8` (all legs fire simultaneously)
- `min_num_trades=2`, `max_num_trades=8` (ADX-tiered base: 2/5/8 legs)
- `gold_native_max_sell_legs=8` (SELL cap raised from 2)
- `sell_stop_cont_enabled=0` (cascade disabled pending TP3 staging validation)
- `session_ny_sell_cutoff_utc=18` (2 PM EDT — G5007 fix)
- `rsi_buy_ceil=77` (raised from 70 — captures May 1 rally RSI 74.9–77.0)

---

## Summary (in progress — tick 4, sim May 4 09:15)
- Total signals: 9,832
- TAKEN: 5 signal rows / 6 actual groups (G5004 has no SIGNALS row — known gap)
- Total P&L: **$390.17**
- Win rate: 27W / 0L (100%)

---

## TAKEN Groups
| Sim Time (UTC) | Group | Direction | Session | RSI | ADX | ATR | Price | Legs | TP reached | P&L |
|----------------|-------|-----------|---------|-----|-----|-----|-------|------|-----------|-----|
| 2026-04-29 15:55 | G5001 | SELL | LONDON | 26.4 | 25.9 | 5.41 | 4545.45 | 5 | TP1+TP2 | ~$120 |
| 2026-04-29 16:00 | G5002 | SELL | LONDON | 26.3 | 29.9 | 5.57 | 4545.52 | 5 | TP1+TP2+fast-lock | ~$121 |
| 2026-04-30 07:05 | G5003 | SELL | LONDON | 32.1 | 41.3 | 3.55 | 4554.18 | 6+1 staged | TP1+cascade fills | ~$42 |
| ~2026-04-30 | G5004 | BUY | — | — | 23.0 | — | — | 2 | TP1+TP2 | ~$42 |
| 2026-05-01 17:00 | G5005 | BUY | LONDON | 74.9 | 26.1 | 7.76 | 4625.94 | 5 | TP1 | $29.20 |
| 2026-05-01 17:05 | G5006 | BUY | LONDON | 77.0 | 31.3 | 8.71 | 4633.94 | 5 | TP1+TP2 | $58.32 |

---

## Gate Breakdown (tick 4 — sim May 4 09:15)
| Gate Reason | Count | Human Label |
|-------------|-------|-------------|
| entry_quality_rsi_buy_ceil | 3,612 | RSI > 77 blocks (May 1 rally RSI 77–84.6) |
| entry_quality_direction | 2,957 | Price not at BB extreme |
| entry_quality_body | 2,332 | Candle body too small |
| no_setup | 493 | Neither BB_BREAKOUT nor BB_BOUNCE |
| session_off | 428 | Outside NY+London session hours |
| entry_quality_adx_min_sell | 4 | SELL blocked ADX < 25 |
| rr_too_low | 3 | Risk:reward ratio too low |
| warmup_tester_m5_rollovers | 2 | Warmup period |
| entry_quality_rsi_sell_floor | 2 | SELL RSI < floor |
| entry_quality_atr_ext | 1 | ATR extension exceeded |

---

## Losses — Price Movement Analysis
| Deal | Magic | Profit | Entry | TP1 | SL | Max favor pts | % TP1 | Pattern |
|------|-------|--------|-------|-----|-----|---------------|-------|---------|

---

## Observations & Anomalies

---

## Session Log

### 2026-05-10 (monitoring session start)
- DB: Agent-3000, 800KB + 4MB WAL (active)
- Baseline (tick 0): source_run_id=1, wall_time=509255158, FORGE 2.7.11 DUAL, sim_start=2026-04-29, 2,737 signals, 0 TAKEN
- aurum_run_id=10 confirmed
- Config: 30 env overrides — first full Run 10 config run
- Key gates at baseline: entry_quality_direction=2,583 (Asian/early London pre-breakout), entry_quality_body=0 (min_body_ratio=0.25 working — not over-filtering)
- Tick 1 (sim: Apr 29 23:55): 2,862 signals (+125), 2 TAKEN (G5001+G5002 SELL Apr29). ADX=25.8→base_n=4, ADX=29.9→base_n=4 (confirmed from log). 5 legs each. P&L=$240.80 (14W/0L). vs Run 9 same signals: $100.86. 2.4× improvement from multi-leg. Fast-lock captured G5002 runner at +$70.88 (8.76 pts). SELL LIMIT L1/L2 fills captured. Cascade correctly disabled.
- Tick 2 (sim: May 1 11:30): 5,598 signals (+2,736), 4 TAKEN (+G5003 SELL ADX=41.3→6+1 staged legs, +G5004 BUY ADX=23.0→2 legs). ADX tier validated. P&L=$302.65 (24W/0L). staged_initial_legs fix not yet active (compiled before fix — next run will fire all 7 simultaneously). May 1 17:00 rally window imminent.
- Tick 3 (sim: May 1 23:55): 9,359 signals (+3,761), 5 TAKEN (+G5005 BUY RSI=74.9 ADX=26.1, +G5006 BUY RSI=77.0 ADX=31.3 — May 1 17:00 rally CAPTURED). P&L=$390.17 (27W/0L). rsi_buy_ceil=77 works: G5005 passes (74.9<77), G5006 exactly at ceil (77.0). 3,612 signals still blocked RSI 77–84.6.
- Tick 4 (sim: May 4 09:15): 9,832 signals (+473), 5 TAKEN (unchanged). Weekend gap passed. May 4 London open: all `entry_quality_direction` SKIPs — ADX 23–25, price not at BB extreme. P&L=$390.17 (27W/0L). No losses. Sim advancing into May 4 NY session.
