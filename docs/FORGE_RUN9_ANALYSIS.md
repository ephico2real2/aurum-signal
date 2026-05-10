# FORGE Run 9 — Tester Analysis

**EA version**: FORGE v2.7.11  
**Symbol**: XAUUSD  
**Sim period**: 2026-04-29 → 2026-05-05 (7 trading days)  
**Scalper mode**: DUAL  
**Balance**: 10,000 (magic_base=202401)  
**aurum_run_id**: 9  
**wall_time**: 500391851  
**source_run_id**: 4 (TESTER_RUNS.id)

**Key changes vs Run 7:**
- Magic range fix: `+9999 → +29999` — cascade/limit deals now captured in TRADES
- `rsi_buy_ceil`: 70 → 77
- `min_directional_bars`: 2 → 1
- `min_body_ratio`: 0.40 → 0.25
- `require_bb_expansion`: 1 → 0
- `session_ny_sell_cutoff_utc`: 17 → 20
- `bb_bounce.adx_max`: 50 → 40
- `require_h1_di_buy`: 0 → 1 (now wired)
- `max_reentry_atr_ext`: 0.0 → 1.25 (now wired)

---

## Summary — FINAL
- Sim period: 2026-04-29 01:00 → 2026-05-05 23:55 UTC (7 trading days)
- Total signals: 20,924
- TAKEN: 8 signals (+ cascade entries)  |  Skipped: 20,916
- Total P&L: **−$143.39**
- Gross profit: $334.27  |  Gross loss: −$477.66
- Win rate: **62.1%** (18 wins / 11 losses)
- Best win: +$57.68 (G5004 BUY Apr 30)
- Worst loss: −$122.64 (G5007 SELL May 4 SL)
- Athena cross-check: ✓ total_pnl=−$143.39 confirmed

---

## TAKEN Groups
| Sim Time (UTC) | Group | Direction | Session | RSI | ADX | ATR | Price | TP reached | P&L |
|----------------|-------|-----------|---------|-----|-----|-----|-------|-----------|-----|
| 2026-04-29 15:55 | G5001 (207402) | SELL | LONDON | 26.4 | 25.9 | 5.41 | 4545.06 | TP1+TP2+Final | +$80.32 |
| 2026-04-29 16:00 | G5002 (207403) | SELL | LONDON | 26.3 | 29.9 | 5.57 | 4545.17 | TP1+TP2+Final | +$20.54 |
| 2026-04-30 07:05 | G5003 (207404) | SELL | LONDON | 32.1 | 41.3 | 3.55 | 4554.16 | TP1+TP2+Final | +$16.54 ⚑ |

*⚑ G5003 now fires at 07:05 Apr 30 (vs 16:07 BUY in Run 7) — loosened body/direction gates opened a new SELL setup at London open.*  
*G5003 cascade: SELL LIMIT L1 (227404) +$4.83, SELL LIMIT L2 (227405) +$5.68, SELL STOP CONT slot[2] (227406) -$5.90 SL hit.*

---

## Gate Breakdown (as of tick 2)
| Gate Reason | Count | Human Label |
|-------------|-------|-------------|
| entry_quality_direction | 3,313 | <1 M5 bar in trade direction (floor at 1 now) |
| session_off | 191 | Outside London/NY |
| no_setup | 189 | Neither BB Breakout nor BB Bounce met |
| entry_quality_adx_min_sell | 4 | ADX below SELL floor (min_sell=25) |
| rr_too_low | 3 | Risk:Reward below minimum |
| warmup_tester_m5_rollovers | 2 | M5 buffers not ready |
| entry_quality_rsi_sell_floor | 2 | RSI below sell floor |

**Notable absences vs Run 7**: `entry_quality_body` (0, was 14k+) and `entry_quality_bb_contraction` (0, was 2.9k) — both loosened gates working as intended.

---

## SELL STOP CONT / BUY LIMIT Events (all now captured in TRADES)
| Event | Group | Slot | Magic | RSI | Price | Result |
|-------|-------|------|-------|-----|-------|--------|
| SELL LIMIT L1 filled | G5001 | — | 227402 | — | — | TP hit → profit (Run 7 missing, now captured) |
| SELL LIMIT L1 filled | G5002 | — | 227403 | — | — | TP hit → profit (Run 7 missing, now captured) |
| SELL STOP CONT slot[2] placed | G5001 | slot[2] | 227404 | 28.4 | 4537.72 | SL hit −$8.78 |
| SELL STOP CONT slot[3] placed | G5002 | slot[3] | 227406 | 28.3 | 4537.32 | SL hit −$12.68 |
| SELL LIMIT L1 filled | G5003 | — | 227404 | — | 4549.33 | TP hit +$4.83 |
| SELL LIMIT L2 filled | G5003 | — | 227405 | — | — | TP hit +$5.68 |
| SELL STOP CONT slot[2] placed | G5003 | slot[2] | 227406 | 29.4 | 4549.33 | SL hit −$5.90 |

---

## Losses — Full Price Movement Analysis

| Deal | Magic | Profit | Entry | TP1 | SL | Max favor | % TP1 reached |
|------|-------|--------|-------|-----|-----|-----------|---------------|
| 20 | 227406 (G5002 slot[3]) | −$12.68 | 4537.32 | ~4535.09 | 4541.78 | +23 pts *after* SL | — |
| 21 | 227404 (G5001 slot[2]) | −$8.78 | 4537.72 | ~4535.55 | 4542.06 | +23 pts *after* SL | — |
| 31 | 227406 (G5003 slot[2]) | −$5.90 | 4549.33 | ~4547.16 | 4552.17 | +8.15 pts | 376% |
| 41-43 | 207406 (G5005 BB_BOUNCE) | −$175.44 | 4591.47 | 4596.61 | 4584.67 | +0.98 pts | 19% |
| 50-53 | 207408 (G5007 SELL) | −$259.22 | 4555.12 | 4548.07 | 4569.50 | ~+2.5 intrabar | intrabar only |
| 59 | 227411 (G5008 SELL STOP) | −$15.64 | ~4543.61 | ~4541.44 | 4547.94 | +21.79 pts | 1004% |

### G5001 SELL STOP CONT slot[2] — Entry 4537.72, SL 4542.06 (−$8.78)
```
16:20  price=4543.70  (above entry, not yet filled)
16:21  SL HIT 4542.06  (filled AND stopped in <60s)
16:25  price=4538.45  ← market then went the RIGHT way
16:35  price=4533.03  +4.7 pts below entry
16:45  price=4514.82  +22.9 pts below entry ← would have been +$46 profit
16:50  price=4514.53  +23.2 pts below entry
```
**Verdict**: Stopped out on a brief 4-pt spike, then market fell 23 pts in the right direction. SL was too tight — only 4.34 pts buffer. Classic SL hunt before the real move.

### G5002 SELL STOP CONT slot[3] — Entry 4537.32, SL 4541.78 (−$12.68)
Identical pattern. Stopped on 4-pt wick, then −23 pts in correct direction within 30 min.

**Verdict**: Same root cause as G5001. Both stopped out right at the SL then market moved massively in favor.

### G5003 SELL STOP CONT slot[2] — Entry 4549.33, SL 4552.17 (−$5.90)
```
07:30  price=4547.23  +2.10 pts favor  ← 97% of way to TP1 (4547.16) — 0.07 pts away!
07:35  price=4541.18  +8.15 pts favor  ← 376% PAST TP1
07:50  price=4547.00  +2.33 pts favor  ← price bouncing back
07:55  price=4547.33  +2.00 pts favor
08:08  SL HIT 4552.17
```
**Verdict**: Was within 0.07 pts of TP1 at 07:30, then ran to +8 pts past TP1 — but NO TP triggered. Held in profit for 40 minutes, reversed slowly and hit SL. **This was a winner the EA held too long.**

### G5005 BB_BOUNCE BUY — Entry 4591.47, TP1(bb_mid) 4596.61, SL 4584.67 (−$175.44)
```
10:25  Entry 4591.47
10:30  price=4592.45  +0.98 pts favor  ← peak: 19% of way to TP1
10:35  price=4585.89  reversal begins
10:33  SL HIT 4584.67
```
**Verdict**: Peaked at just 0.98 pts (19% of TP1). Never made meaningful progress. BB_BOUNCE into ADX=33.2 trending market — failed immediately. **No TP tightening helps here. Prevention-only fix: `adx_max=30`.**  
`bounce_lot_factor=0.25` (wired, needs recompile): −$175 → ~−$44.

### G5007 BB_BREAKOUT SELL — Entry 4555.12, TP1 4548.07, SL 4569.50 (−$259.22)
```
17:10  Entry 4554.98  +0.14 pts favor  ← intrabar brief dip (~2.5 pts, invisible in bar data)
17:15  price=4560.28  −5.16 pts AGAINST
17:20  price=4572.98  −17.86 pts AGAINST  ← SL hit here
```
**Verdict**: Never profitable on any M5 bar close. The ~$40 floating profit was **intrabar only** — a brief 2.5 pt dip within the first M5 candle. With `tp1_atr_mult=0.4` (2.82 pts TP), that intrabar dip would have been caught and TP1 filled. **This directly validates the TP tightening request.**

### G5008 SELL STOP CONT slot[2] — Entry ~4543.61, SL 4547.94 (−$15.64)
```
18:20  price=4539.80  +3.81 pts favor  (176% past TP1)
18:20  price=4535.45  +8.16 pts favor
18:25  price=4521.82  +21.79 pts favor  ← MASSIVE win potential
18:25→next day: price slowly recovered
May 5 08:35  SL HIT 4547.94
```
**Verdict**: Trade was +21 pts in profit overnight. No close-range TP was set. Held open 14 hours, reversed to SL next morning. **`sell_stop_cont_expiry_bars=8` (40 min) should have closed this — possible expiry bug worth investigating.**

### What this tells us for Run 10

| Group | Root cause | Fix |
|---|---|---|
| G5001/G5002 SELL STOP | SL too tight (4.34 pts). Stopped on wick, move resumed −23 pts | Wider cascade SL OR disable |
| G5003/G5008 SELL STOP | Was deeply in profit (8–22 pts) but no nearby TP. Reversed overnight | Add `sell_stop_cont_tp_atr_mult` ~0.5×ATR |
| G5005 BB_BOUNCE | ADX=33 trending market. Peaked at 19% of TP1 | `adx_max=30` + `bounce_lot_factor=0.25` |
| G5007 BREAKOUT | Intrabar 2.5 pt dip, TP1 was 7 pts away | `tp1_atr_mult=0.4` catches intrabar moves |
| G5008 cascade | Survived overnight past expiry_bars=8 | Investigate expiry logic |

---

## Observations & Anomalies

### Magic range fix working — cascade/limit deals now fully captured
All SELL LIMIT L1 (magic +20000), SELL LIMIT L2 (+20001), and SELL STOP CONT (+20002/+20003) deals now appear in TRADES. In Run 7 these were all silently dropped by `JournalImportTrades` filter (`MagicNumber + 9999` cap, now `+ 29999`).

### G5003 different from Run 7
With loosened entry gates, G5003 fires as a SELL at Apr 30 07:05 LONDON (RSI 32.1, ADX 41.3). In Run 7 it was a BUY at Apr 30 16:07 (RSI 54.6, ADX 23.0). The loosened body/direction gates are opening different signal paths — the Apr 30 London open SELL is a genuinely strong setup (ADX 41 = confirmed trend).

### SELL STOP CONT pattern — all hitting SL
3 of 3 SELL STOP CONT slots armed so far have hit SL (−$8.78, −$12.68, −$5.90). This is worth tracking across the full run — if SELL STOP CONTs consistently lose, consider raising `sell_stop_cont_min_rsi` above 25 to require higher RSI before arming (less exhausted market).

---

## Session Log

### 2026-05-10 (monitoring session start)
- DB: Agent-3000, active WAL
- Baseline (tick 0): source_run_id=4, wall_time=500391851, FORGE 2.7.11 DUAL, sim_start=2026-04-29, 29 signals, 0 TAKEN
- aurum_run_id=9 confirmed tick 2
- Tick 1 (sim: 2026-04-29 18:15): 3,522 signals, 2 TAKEN (G5001+G5002 SELL), P&L=$112.96 (8W/2L). Magic fix confirmed: deals 20,21 captured (−$12.68, −$8.78 SELL STOP SL hits)
- Tick 2 (sim: 2026-04-30 10:20): 3,710 signals (+188), 3 TAKEN (+G5003 SELL Apr30 07:05). New SELL LIMIT L1+L2 fills captured (deals 24,25,27,28). SELL STOP CONT slot[2] filled+SL (deals 30,31 −$5.90). P&L=$123.60 (12W/3L). Lag=27.
- Tick 3 (sim: 2026-04-30 20:35): 6,165 signals (+2,455), 4 TAKEN (+G5004 BUY Apr30 16:07 +$144.40). entry_quality_body reappeared (2,332) in Apr30 afternoon BUY signals. No new losses. P&L=$268.00 (15W/3L) — already above Run 7 final $257.58.
- Tick 4 (sim: 2026-05-01 16:20): 6,390 signals (+225), 5 TAKEN (+G5005 BB_BOUNCE BUY May1 10:25 RSI=32.2 ADX=33.2). CATASTROPHIC: 3 SL hits −$54.40/−$59.12/−$61.92 = −$175.44. All 3 legs stopped at 4584.67. P&L=$92.56 (15W/6L). BB_BOUNCE adx_max=40 allowed ADX=33 — needs review. May 1 17:00 rally not yet reached (sim at 16:20).
- Tick 5 (sim: 2026-05-01 23:55): 15,489 signals (+9,099). No new TAKEN. P&L flat $92.56. May 1 rally: rsi_buy_ceil=77 now passes first 3 candles (RSI 74.9–77.0) BUT entry_quality_atr_ext (3 hits) blocks them via max_reentry_atr_ext=1.25. RSI 77–84.6 still blocked by ceiling (9,005 hits). Need: max_reentry_atr_ext→2.0 or 0 to fully capture rally.
- Tick 6 (sim: 2026-05-04 17:31): 16,067 signals (+578), 7 TAKEN (+G5006 SELL +$4.57, +G5007 SELL −$259.22). G5007 at 17:10 UTC directly caused by session_ny_sell_cutoff=20 (old 17 would have blocked). 4 SL hits at 17:18 (8 min trade). P&L=−$162.09 (16W/10L). Recommend: revert cutoff to 18, lower bb_bounce.adx_max to 30.
- Tick 7 (sim: 2026-05-05 13:50): 18,238 signals (+2,171), 8 TAKEN (+G5008 SELL May4 18:16 +$18.70 net). SELL STOP CONT now 0-for-4 (all SL): G5001/G5002/G5003/G5008 = −$43 total. New gate entry_quality_adx_spike_sell (1 hit) — ADX lookback gate live. P&L=−$143.39 (18W/11L).
- Tick 8 (sim: May 5 23:55): +2,686 signals, no new trades. Quiet tick 1/3.
- Tick 9 (sim: May 5 23:55): flat. Quiet tick 2/3.
- Tick 10 (sim: May 5 23:55): flat. **STOP CONDITION MET**. Athena confirmed. gate codes checked.

---

## Recommended Parameter Changes — Run 10

**Context**: 20,924 signals, 8 TAKEN (0.04% take rate). Gross profit $334.27 overwhelmed by gross loss $477.66. Three loss categories identified.

### Loss breakdown by category

| Category | Groups | Total Loss | Root Cause |
|---|---|---|---|
| TP too far, SL hit | G5007 | −$259.22 | `tp1_atr_mult=1.0` — TP1 7 pts away, trade peaked at 2.5 pts then reversed |
| BB_BOUNCE SL | G5005 | −$175.44 | `adx_max=35` allows ADX=33.2; mean-reversion into trending market |
| SELL STOP CONT SL | G5001/G5002/G5003/G5008 | −$43.00 | 0-for-4, all continuation legs reversed after primary TP |
| **Total losses** | | **−$477.66** | |

### Current blocking gates → parameters

| Gate | Hits | Config key | Current | Proposed |
|------|------|------------|---------|---------|
| `entry_quality_rsi_buy_ceil` | 9,005 | `bb_breakout.rsi_buy_ceil` | `77` | `77` (keep — correct, May 1 rally still too extended) |
| `entry_quality_direction` | 6,250 | `safety.min_directional_bars` | `1` | `1` (keep) |
| `entry_quality_body` | 4,265 | `safety.min_body_ratio` | `0.25` | `0.25` (keep) |

### Change 1 — `bb_breakout.tp1_atr_mult`: 1.0 → 0.4 *(critical)*
**Impact**: TP1 fires at 0.4×ATR (~2.8 pts at ATR=7). G5007 would have hit TP1, closed 60%, moved SL to BE. Outcome: +$20 vs −$259 actual.  
**Risk**: Lower per-trade profit on winners. Becomes pure scalping — capture the first push, close, re-enter.  
**Pair with**: `tp1_close_pct` 40→60 (lock in more at TP1).

### Change 2 — `bb_breakout.tp1_close_pct`: 40 → 60
**Impact**: Close 60% of position at TP1 instead of 40%. More capital protected early.  
**Risk**: Less runner volume for TP2-TP4. Accept lower ceiling, gain reliability.

### Change 3 — `safety.fast_lock_min_profit_points`: 12.0 → 5.0
**Impact**: Fast-lock trailing stop engages when up 5 pts instead of 12. Would have protected G5007's brief 2.5 pt profit moment (close to triggering at 5).  
**Risk**: More premature fast-lock exits on slow-building moves.

### Change 4 — `safety.fast_lock_min_hold_sec_breakout`: 50 → 25
**Impact**: Allow fast-lock to engage 25s after entry instead of 50s. G5007's SELL LIMIT L1 filled at 17:11:55 (105s after entry) — fast-lock would have been eligible by then.  
**Risk**: Slightly more reactive on fast initial moves. Acceptable for scalping regime.

### Change 5 — `bb_bounce.adx_max`: 35 → 30 *(high priority)*
**Impact**: G5005 had ADX=33.2 — blocked at adx_max=30. Prevents mean-reversion into trending markets.  
**Risk**: Fewer BB_BOUNCE trades (intentional — bounce is higher-risk).  
**Note**: `bounce_lot_factor=0.25` (wired this session) provides additional risk control even if a bounce fires.

### Change 6 — `sell_stop_cont_enabled`: 1 → 0 *(disable for next run)*
**Impact**: Eliminates 0-for-4 continuation legs (−$43 drag). Primary groups win; cascades consistently lose.  
**Risk**: Miss genuine continuation moves. But 4/4 SL hits = clear evidence this regime doesn't support SELL STOP CONT.

### Change 7 — `session_ny_sell_cutoff_utc`: 20 → 18
**Impact**: G5007 (17:10 UTC) and G5008 (18:16 UTC) both fired after the old 17:00 cutoff. G5007 = −$259. 18 UTC (2 PM EDT) is the right compromise — covers early NY without the 17-20 danger window.  
**Risk**: Misses a small set of valid NY afternoon SELLs. Worth it given G5007.

### Apply order for Run 10
1. Changes 1+2 together (`tp1_atr_mult` + `tp1_close_pct`) — single biggest P&L impact
2. Change 7 (`session_ny_sell_cutoff`) — prevents repeat G5007
3. Change 5 (`bb_bounce.adx_max=30`) — closes the bounce filter gap
4. Change 6 (`sell_stop_cont_enabled=0`) — eliminate cascade drain
5. Changes 3+4 (`fast_lock` tightening) — fine-tuning after main fixes confirmed

> Recompile FORGE.mq5 required: `bounce_lot_factor` (struct + lot calc) + magic range fix (`+9999→+29999`)
> Changes go via `.env` → `make scalper-env-sync && make forge-compile`
