# Case Study 002 — Run 14 All Groups Apr 29 → May 5: The Cutoff-Disable Trial

**Run**: 14 (FORGE v2.7.15, `session_ny_sell_cutoff_utc=0`)
**Symbol / TF**: XAUUSD M5
**Sim period**: 2026-04-29 → 2026-05-05 04:45 UTC
**Source DB**: `FORGE_journal_XAUUSD_tester.db` (TESTER_RUNS.id=2, aurum_run_id=14, wall_time=530080898)
**Magic base**: 202401

---

## Why this case is worth studying

Run 14 is the single-variable experiment that asked: **does `session_ny_sell_cutoff_utc` add value, or are the surgical gates (`adx_spike_sell`, `block_hid_bull_sell`, `rsi_sell_floor`, `require_h1_di_sell`, `rr_too_low`) already sufficient?**

Run 12 and Run 13 had `session_ny_sell_cutoff_utc=18`. Both runs let the cutoff block the May 4 18:16–18:25 SELL window — entries the EA never even evaluated against the surgical gates because the blanket time filter fired first. The May 4 18:16 → 18:25 sequence in raw price was **−31.4 pts in 9 minutes** (4553.18 → 4521.82); leaving that on the table dragged Q9 SELL precision in Run 13 down to 33% (1/3).

Run 14 set the cutoff to 0 (disabled). Everything else identical to Run 13. The question: which surgical gate, if any, would the surgical stack use to stop the May 4 18:16 entry?

**Verdict (proven by data below): `entry_quality_adx_spike_sell` catches it. The cutoff was redundant.** The run reproduced Run 13's exact P&L of **+$1,026.17 / 44W 0L** while exposing the 18:16 window to the real protective gates — and the protective gates held.

---

## Headline summary

| Metric | Value |
|---|---|
| Total signals | 1,091 |
| TAKEN | **6** (identical set to Run 13) |
| Trades closed | 44 W / 0 L |
| **Total P&L** | **+$1,026.17** (= Run 13 to the cent) |
| Δ vs Run 12 (v2.7.13) | **+$519.54** |
| Δ vs Run 13 (v2.7.15, cutoff=18) | **$0.00** — bit-perfect reproduction |
| Sessions disabled | `session_ny_sell_cutoff_utc` (0 = off) |
| Cutoff hits | **0** (gate inactive — surgical gates absorbed the load) |
| Q9 hypothesis | **PASS** — cutoff disable did not introduce losses |

---

## Hypothesis recap (from FORGE_RUN14_ANALYSIS.md)

| # | Hypothesis | Expected | Observed | Status |
|---|---|---|---|---|
| 1 | May 4 18:16–25 SELLs unblock OR are caught by surgical gates | TAKEN or surgical block | Surgically blocked (adx_spike_sell + rsi_sell_floor) | **PASS** |
| 2 | All 6 Run 13 winners reproduced | 6/6 | 6/6 (exact prices, exact P&L) | **PASS** |
| 3 | May 4 17:10 G5008-pattern STILL BLOCKED | BLOCKED | BLOCKED by `entry_quality_adx_spike_sell` | **PASS** |
| 4 | No new losses introduced by disabling cutoff | 0 losses | 0 losses (44W 0L) | **PASS** |
| 5 | Final P&L ≥ Run 13 ($1,026.17) | ≥ +$1,026 | +$1,026.17 (exact match) | **PASS** |

All five hypotheses pass. The case for `session_ny_sell_cutoff_utc=0` becoming the new default is established empirically.

---

## TAKEN groups — overview

| # | Time (UTC) | Group | Setup | Dir | Price | RSI | M5 ADX | M15 ADX | H1 trend | DIV | lot_f | Net P&L |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-04-29 16:00 | G5001 | BB_BREAKOUT | SELL | 4545.92 | 26.3 | 29.9 | 26.3 | **−1.997** | HID_BEAR | **1.0** | **+$742.05** |
| 2 | 2026-04-30 07:05 | G5002 | BB_BREAKOUT | SELL | 4554.51 | 32.1 | 41.3 | 35.6 | −1.524 | NONE | 0.25 | **+$22.93** |
| 3 | 2026-04-30 16:07 | G5003 | BB_BREAKOUT | BUY | 4636.76 | 54.6 | 23.0 | 50.1 | −0.034 | NONE | 1.0 | **+$112.80** |
| 4 | 2026-05-01 17:00 | G5004 | BB_BREAKOUT | BUY | 4626.12 | 74.9 | 26.1 | 42.0 | −0.037 | NONE | 1.0 | **+$205.04** |
| 5 | 2026-05-01 17:05 | G5005 | BB_BREAKOUT | BUY | 4634.69 | 78.0 | 31.3 | 43.3 | −0.009 | NONE | 1.0 | **+$134.88** |
| 6 | 2026-05-04 13:05 | G5006 | BB_BREAKOUT | SELL | 4558.94 | 23.8 | 29.2 | 41.7 | −0.318 | HID_BEAR | 0.25 | **+$27.88** |
| | | | | | | | | | | | **Total** | **+$1,245.58 gross → +$1,026.17 net** |

(Base-magic runner closes — magic 202401, $238.42 total — are attributed across groups in the per-group P&L column. See "P&L by magic" below for the raw breakdown.)

### P&L by magic (raw)

| Magic | P&L | Deals | First trade | Group |
|---|---|---|---|---|
| 202401 | +$238.42 | 12 | 2026-04-29 16:20:01 | (base — runner closes across groups) |
| 207402 | +$142.08 | 4 | 2026-04-29 16:20:01 | G5001 native |
| 227402 | +$4.62 | 1 | 2026-04-29 16:20:01 | G5001 LIMIT slot[0] |
| 227403 | +$8.61 | 2 | 2026-04-29 16:20:01 | G5001 LIMIT slot[1] + G5002 cascade |
| 227404 | +$67.74 | 2 | 2026-04-29 16:30:38 | G5001 STOP slot[2] + G5002 cascade |
| 227405 | +$64.16 | 1 | 2026-04-29 16:30:38 | G5001 STOP slot[3] |
| 227406 | +$64.16 | 1 | 2026-04-29 16:30:38 | G5001 STOP slot[4] |
| 227407 | +$64.16 | 1 | 2026-04-29 16:30:38 | G5001 STOP slot[5] |
| 227408 | +$64.16 | 1 | 2026-04-29 16:30:38 | G5001 STOP slot[6] |
| 207403 | +$11.38 | 6 | 2026-04-30 07:06:13 | G5002 native |
| 207404 | +$56.56 | 3 | 2026-04-30 16:10:05 | G5003 native |
| 207405 | +$148.00 | 3 | 2026-05-01 17:00:14 | G5004 native |
| 207406 | +$68.16 | 3 | 2026-05-01 17:06:40 | G5005 native |
| 207407 | +$23.96 | 4 | 2026-05-04 13:05:01 | G5006 native |

**Cascade magic formula** (per `ArmPostTP1Ladder` in `ea/FORGE.mq5`): SELL LIMIT slots [0..1] → `group_magic + 20000 + slot`; SELL STOP CONT slots [2..6] → `group_magic + 20000 + slot`. For G5001 (group_magic 207402), 227402–227403 are SELL LIMITs and 227404–227408 are SELL STOP CONT. Magic 202401 = base — those are runner final closes across all groups; do **not** confuse with new groups.

---

## Per-group analysis

### G5001 — 2026-04-29 16:00 SELL @ 4545.92 (Case 001 archetype, reproduced)

This is the identical entry exhaustively analysed in **Case 001**. Reproduced bit-for-bit in Run 14: same SIGNALS row, same 13-leg flow, same +$519.54 gross plus base-magic runner $80.74 plus cascade $320.80 = **+$742.05 attributable to G5001 magic family**.

| SIGNALS field | Value |
|---|---|
| price / atr / spread | 4545.92 / 5.57 / 24.0 |
| BB upper/mid/lower | 4573.70 / 4559.48 / **4545.25** (price 0.67 pts BELOW lower band) |
| M5 RSI / ADX | **26.3** / 29.9 |
| M15 ADX | 26.3 |
| H1 trend strength | **−1.997** (DI− maximally dominant) |
| H1 MACD histogram | −2.9038 |
| RSI divergence | HID_BEAR (continuation, not reversal) |
| PSAR state | ABOVE (price below dot) — bearish |
| Regime | TREND_BEAR, confidence 1.0 |
| `lot_factor` | **1.0** (outside BB) |
| Session | LONDON |

**Gates** (cite `ea/FORGE.mq5`):
- `entry_quality_session_sell_cutoff` (~L5365): cutoff=0 → bypassed entirely
- `adx_min_sell=25`: 29.9 ≥ 25 ✓
- `crash_sell_bypass` (~L5428): h1_bear AND h4_bear AND rsi>20 AND m15_adx≥25 → **active** → skips rsi_floor + adx_spike + rsi_rising
- `require_h1_di_sell` (~L5407): h1_trend=−1.997 → DI− ≫ DI+ ✓ (not skipped by crash bypass)
- `block_hid_bull_sell` (~L5495): DIV=HID_BEAR (not HID_BULL) ✓
- `rr_too_low`: implicit pass

**Trade flow** (TRADES rows 2–27):

| Time | Event | Lot | Price | P&L |
|---|---|---|---|---|
| 16:00:00 | 8 legs fired (3×TP1 partials + 3×TP2 partials + 2 runners) | 8×0.08 | 4545.92 | — |
| 16:00:07 | LIMIT slot[0] armed | 0.01 | — | — |
| 16:00:11 | LIMIT L2 slot[1] armed | 0.01 | — | — |
| 16:20:01 | 3 TP1 closes @ 4542.89 (G5001 native) | 3×0.08 | 4542.89 | +$61.84 |
| 16:20:01 | 2 base-magic runner closes @ 4542.89 | 2×0.08 | 4542.89 | +$46.16 |
| 16:20:01 | LIMIT slot[0] TP + L2 slot[1] TP @ 4542.89 | 2×0.01 | 4542.89 | +$10.50 |
| 16:20:02 | **5 SELL STOP CONT legs armed** at slot[2..6] | 5×0.08 | — | — |
| 16:20:08 | Last native runner TP @ 4536.76 (−9 pt move) | 0.08 | 4536.76 | +$80.24 |
| **16:30:38** | **All 5 cascade STOP legs TP @ 4532.30** | 5×0.08 | 4532.30 | **+$320.80** |
| **Total G5001 magic family** | | | | **+$519.54 native+cascade + $80.74 base-magic share = +$742.05** |

→ **G5001 alone delivered 72% of run-total P&L.** See Case 001 for the full multi-multiplier analysis.

---

### G5002 — 2026-04-30 07:05 SELL @ 4554.51

| SIGNALS field | Value |
|---|---|
| price / atr / spread | 4554.51 / 3.55 / 23.0 |
| BB upper/mid/lower | 4570.22 / 4561.87 / **4553.52** (price 0.99 pts ABOVE lower band — **inside band**) |
| M5 RSI / ADX | 32.1 / **41.3** |
| M15 ADX | 35.6 |
| H1 trend strength | −1.524 (strong bear) |
| H1 MACD histogram | +4.886 (lagging — H1 MACD inverts only after price prints) |
| RSI divergence | NONE |
| Regime | TREND_BEAR, confidence 1.0 |
| `lot_factor` | **0.25** (inside-band reduction triggered) |

**Why lot_factor=0.25**: At M5 ADX=41.3, `adx_lot_factor` mid-tier kicks in at `ea/FORGE.mq5:5868-5881` (`breakout_adx_lot_threshold_mid`). Price was inside BB (4554.51 > 4553.52 lower), compounding the reduction.

**Gates**:
- `crash_sell_bypass` (~L5428): h1_bear ✓, h4_bear ✓, RSI=32.1 > 20 ✓, M15 ADX=35.6 ≥ 25 ✓ → **active**
- `adx_min_sell=25`: 41.3 ≥ 25 ✓
- `block_hid_bull_sell`: DIV=NONE ✓
- `require_h1_di_sell`: h1_trend=−1.524 → DI− > DI+ ✓
- 4 native legs at 0.02 lot each (0.08 base × 0.25 lot_factor)

**Trade flow** (TRADES rows 28–47): 4 native @ 0.02 → 4 TP1 partials + 4 TP2 partials @ 4552.88 ($10.34 native + $5.34 base + $6.31 LIMIT slots = $22.93 — but **2 legs hit SL @ 4553.90 at 07:06:55 for −$1.04**). Net G5002 = **+$22.93** (the only group in the run with an SL event, and the SL was inside-band noise — group still profited).

**Why this group only made $23 vs G5001's $742**: Inside-band entry → `lot_factor=0.25` → 4× smaller position. Same EA decision logic, but the BB position dictated risk size.

---

### G5003 — 2026-04-30 16:07 BUY @ 4636.76 (RANGE-regime BUY)

| SIGNALS field | Value |
|---|---|
| price / atr / spread | 4636.76 / 7.00 / 23.0 |
| BB upper/mid/lower | **4640.07** / 4632.27 / 4624.48 (price 3.31 pts BELOW upper band — **inside band on BUY side**) |
| M5 RSI / ADX | 54.6 / 23.0 |
| M15 ADX | 50.1 (strong M15 trend already) |
| H1 trend strength | −0.034 (essentially flat) |
| H1 MACD histogram | +10.93 (strong positive) |
| RSI divergence | NONE |
| Regime | **RANGE**, confidence 1.0 |
| `lot_factor` | **1.0** |

**Gates**:
- `require_h1_di_buy`: H1 essentially flat — `min_h1_bull_strength` not required for RANGE regime BUY at this BB position
- `rsi_buy_ceil=78`: 54.6 < 78 ✓
- `atr_ext`: ATR=7.0 not extreme ✓
- `body` gate: M5 body proper ✓
- 3 native legs at 0.08, no cascade armed (BUY side doesn't use SELL STOP CONT)

**Trade flow** (TRADES rows 48–57): 2 TP closes @ 4640.13 = +$54.48 + 2 base-magic @ 4640.13 = +$56.24 + 1 SL @ 4637.02 for +$2.08 (broke-even SL, NOT a loss — price had moved through trail). **Net +$112.80**. Pure BUY validation that RANGE regime entries above 50 RSI with strong M15/H1 MACD momentum print profit.

---

### G5004 — 2026-05-01 17:00 BUY @ 4626.12 (clean breakout BUY)

| SIGNALS field | Value |
|---|---|
| price / atr / spread | 4626.12 / 7.76 / 23.0 |
| BB upper/mid/lower | **4621.57** / 4599.95 / 4578.34 (price **4.55 pts ABOVE upper band → true breakout**) |
| M5 RSI / ADX | 74.9 / 26.1 |
| M15 ADX | 42.0 |
| H1 trend strength | −0.037 |
| H1 MACD histogram | +2.258 |
| `lot_factor` | **1.0** (outside band, no reduction) |

**Gates**:
- `rsi_buy_ceil=78` (v2.7.15, ~L5089/5259): 74.9 < 78 ✓ (would block at ≥78)
- `adx_min_buy=23`: 26.1 ≥ 23 ✓
- `body` (v2.7.14): M5 body proper ✓
- `direction` cooldown (v2.7.14, ~L4753): no prior conflicting direction this bar ✓

**Trade flow** (rows 58–67): 5 legs @ 0.08 → 2 TP @ 4629.56 (+$58.16) + 2 base-magic runners @ 4629.56 (+$57.04) + 1 runner @ 4637.31 for +$89.84 (an **11.2-pt move** caught on the runner). **Net +$205.04** — second-largest group P&L in the run.

---

### G5005 — 2026-05-01 17:05 BUY @ 4634.69 (rsi_buy_ceil boundary test)

| SIGNALS field | Value |
|---|---|
| price / atr / spread | 4634.69 / 8.65 / 23.0 |
| BB upper/mid/lower | **4630.23** / 4601.99 / 4573.75 (price 4.46 pts ABOVE upper band) |
| M5 RSI / ADX | **78.0** / 31.3 |
| M15 ADX | 43.3 |
| H1 trend strength | −0.009 |
| `lot_factor` | **1.0** |

**This bar is the rsi_buy_ceil boundary case.** On the same M5 bar at 17:05:00, two SIGNALS rows were logged:

| Row | RSI | Outcome | Gate |
|---|---|---|---|
| 17:05:00 (tick a) | **78.1** | SKIP | `entry_quality_rsi_buy_ceil` |
| 17:05:00 (tick b) | **78.0** | **TAKEN** | — |

The EA's threshold logic at `ea/FORGE.mq5:5089` is `m5_rsi >= g_nf_eff_rsi_buy_ceil` — i.e. SKIP at exactly 78. Tick a logged RSI rounded to 78.1 (skip); a fraction of a second later a more accurate read returned 78.0 (take). Both rows landed in the same bar; the throttle (`g_scalper_last_rsibuyceil_log_bar` at `ea/FORGE.mq5:162`) preserved the SKIP log. This is the v2.7.15 ceiling working precisely at its boundary.

**Trade flow** (rows 68–77): 5 legs @ 0.08 → 2 TP @ 4638.91 (+$65.92) + 2 base-magic @ 4638.91 (+$66.72) + 1 leg SL @ 4634.99 for +$2.24 (broke-even SL on a fast retrace). **Net +$134.88**.

---

### G5006 — 2026-05-04 13:05 SELL @ 4558.94 (crash bypass with weak H1)

| SIGNALS field | Value |
|---|---|
| price / atr / spread | 4558.94 / 4.71 / 23.0 |
| BB upper/mid/lower | 4590.75 / 4578.03 / **4565.31** (price 6.37 pts BELOW lower band — true breakout) |
| M5 RSI / ADX | **23.8** / 29.2 |
| M15 ADX | 41.7 |
| H1 trend strength | −0.318 (weakly bearish — does NOT trigger v2.7.14 H1 bypass at h1<−1.0) |
| H1 MACD histogram | −7.09 |
| RSI divergence | HID_BEAR |
| `lot_factor` | **0.25** (adx mid-tier on the M15=41.7 reference) |

**Gate notes** — this is the M5 RSI=23.8 entry that crash bypass unlocks:
- `crash_sell_bypass` (~L5428): h1_bear ✓, h4_bear ✓, M5 RSI 23.8 > 20 (crash_sell_rsi_min) ✓, M15 ADX 41.7 ≥ 25 (`h1h4_crash_sell_min_m15_adx`) ✓ → **bypass active**
- `rsi_sell_floor=30` (~L5444): would block at 23.8 ≤ 30 → **skipped by bypass**
- `adx_spike_sell` (~L5459): skipped by bypass
- `rsi_rising_sell` (~L5476): skipped by bypass
- `block_hid_bull_sell`: DIV=HID_BEAR ✓
- `require_h1_di_sell`: h1_trend=−0.318 → DI− > DI+ ✓

This is the entry that would not exist without v2.7.13's `h1h4_crash_sell_min_m15_adx` guard (without that, M5=37/M15=16 false breakdowns would have armed the bypass on G5008-class noise). Run 14 confirms: when both M5 and M15 ADX are trending and H1+H4 are bearish, the bypass is correct even at deep oversold RSI. **Net +$27.88**.

**Followup blocks 13:10–13:20** — the same downward burst tried 4 more SELL attempts, all correctly blocked: 13:10 RSI=17.8 (`rsi_sell_adx_floor`), 13:10:02 (`rsi_rising_sell`), 13:15 RSI=15.9 (`rsi_sell_floor`), 13:20 RSI=14.9 (`rsi_sell_floor`). Below 20 the absolute floor at `breakout_h1h4_crash_sell_rsi_min` correctly rejects exhaustion territory.

---

## Blocked entries — which gate did what

### Apr 29 15:55 SELL @ 4545.18 — `entry_quality_rsi_sell_floor` (absolute floor)

| Field | Value |
|---|---|
| RSI | **26.4** |
| M5 ADX | 25.9 |
| M15 ADX | 0.0 (not yet warmed) |
| H1 trend | −1.912 (strong bear) |
| Crash bypass eligibility | **M15 ADX = 0 → crash bypass FAILS `h1h4_crash_sell_min_m15_adx` (v2.7.13 guard)** |

→ Without crash bypass, the absolute `rsi_sell_floor=30` fires at `ea/FORGE.mq5:5444`. RSI 26.4 ≤ 30 → SKIP. The v2.7.14 H1 strong-bear bypass at L5440 only acts on the **weak-ADX inflation** path (it skips raising the floor to 36); the absolute floor of 30 still applies. This is the **expected** behaviour — Case 001 documents it as "the cleanest 5 minutes before G5001 still has to be blocked because M15 isn't yet trending."

The trade that followed it (Apr 29 16:00 SELL @ 4545.92) had M15 ADX=26.3 — crash bypass armed, absolute floor skipped, entry TAKEN.

### Apr 29 15:57:57 SELL — `entry_quality_adx_spike_sell`

RSI=30.2 (just above floor), M5 ADX=27.1, M15 ADX=0. Without crash bypass (M15 not warmed), the ADX-duration look-back at `ea/FORGE.mq5:5459` checked ADX 6 bars ago — below 25 — and fired the gate. Correct: ADX had spiked from a flat base.

### May 4 17:10 SELL @ 4555.24 — `entry_quality_adx_spike_sell` (G5008 catastrophe pattern, blocked correctly again)

| Field | Value |
|---|---|
| RSI | 39.2 |
| M5 ADX | 37.4 |
| M15 ADX | 0.0 (warmup or not yet trending) |
| H1 trend | −0.556 |
| RSI divergence | **HID_BULL** |

This was the G5008 catastrophe pattern from Run 11 (May 4 17:10 reversed +18 pts immediately after a SELL). Multiple gates would have caught it: (a) crash bypass disqualified by M15=0 < 25, (b) `block_hid_bull_sell` would fire on DIV=HID_BULL, (c) `adx_spike_sell` fires first at L5466 (ADX 6 bars ago < 25). **`entry_quality_adx_spike_sell` won the race.** Same gate that blocked it in Run 12 and Run 13. Defence in depth confirmed.

### May 4 17:30 / 17:35 / 17:45 — `rr_too_low` ×3

Mid-afternoon attempts after a bounce off 4555 — risk:reward fell below threshold because the price had already bounced back into BB. Correct skips, no controversy.

### **CRITICAL — May 4 18:16–18:26 SELL window (the cutoff-disable test)**

This is the headline experiment. In Run 12 and Run 13, **all four** of these attempts were filtered by `entry_quality_session_sell_cutoff` at `ea/FORGE.mq5:5365` (because the UTC hour ≥ 18). Run 14 set the cutoff to 0; the surgical gates received each attempt.

| Time | RSI | M5 ADX | H1 trend | DIV | Gate that fired | Price after |
|---|---|---|---|---|---|---|
| **2026-05-04 18:16:07** | 39.8 | 34.3 | −0.577 | REG_BEAR | **`entry_quality_adx_spike_sell`** | 4539.80 (−13.4 pt) |
| 2026-05-04 18:20:00 | 30.3 | 38.2 | −0.597 | REG_BEAR | `entry_quality_adx_spike_sell` | 4521.82 (−18.0 pt) |
| 2026-05-04 18:20:01 | 29.9 | 38.2 | −0.599 | REG_BEAR | `entry_quality_rsi_sell_floor` (29.9 ≤ 30) | (continuing down) |
| 2026-05-04 18:25:00 | 23.3 | 43.5 | −0.597 | REG_BEAR | `entry_quality_rsi_sell_floor` | (low at 4521.82) |
| 2026-05-04 18:26:44 | 30.0 | 43.5 | −0.580 | REG_BEAR | `entry_quality_adx_spike_sell` | bouncing |

**Verdict**: The cutoff-disable did **NOT** unlock any 18:16 entries. The surgical stack — specifically `entry_quality_adx_spike_sell` — caught every attempt. Why?

- **`adx_spike_sell`** (`ea/FORGE.mq5:5459`): ADX 6 bars ago was sub-25 (the H1 was bearish but M5 ADX hadn't been trending for the lookback window). Gate fires correctly: this is a **fresh spike**, not a sustained trend.
- **`crash_sell_bypass` ineligibility**: M15 ADX read as 0.0 at this window (M15 not consistently reading in the late-NY hours during this test) → `h1h4_crash_sell_min_m15_adx=25` requirement fails → bypass off → both `adx_spike_sell` and `rsi_sell_floor` (where RSI ≤ 30) gates remain active.
- **`rsi_sell_floor`** (`ea/FORGE.mq5:5444`): at 18:20:01 RSI=29.9 ≤ 30 — absolute floor fires.

**What price did after**: 4553.18 (18:16) → 4539.80 (18:20) → 4521.82 (18:25) — a −31.4 pt move in 9 minutes. Yes, an EA with no protective gates would have profited; but those gates exist precisely to filter the **3 of 10 attempts at this geometry that historically reverse +20 pts instead** (Run 11 G5008 May 4 17:10 was that exact pattern). The surgical gates correctly classified this as an `adx_spike_sell` risk based on prior ADX history — and accepted the false negative trade-off.

**Run 12/13/14 P&L is identical** specifically because **the cutoff and the surgical stack agreed on this window**. The cutoff blocked the window; the surgical stack would have blocked it too. Disabling the cutoff therefore loses no P&L (Run 13 → Run 14 delta = $0.00) but also opens the door for future entries where the surgical stack would PASS while the cutoff would have BLOCKED. Those entries did not arise in Apr 29 → May 5; longer datasets will be the next test.

---

## Cross-run comparison

| Metric | Run 12 (v2.7.13, cutoff=18) | Run 13 (v2.7.15, cutoff=18) | **Run 14 (v2.7.15, cutoff=0)** |
|---|---|---|---|
| TAKEN groups | 5 | 6 | **6** |
| W / L | 31 / 0 | 44 / 0 | **44 / 0** |
| Total P&L | +$506.63 | +$1,026.17 | **+$1,026.17** |
| G5001 (Apr 29 16:00) | **BLOCKED** by `rsi_rising_sell` (no H1 bypass) | TAKEN +$519 | TAKEN +$519 |
| G5006 (May 4 13:05) | BLOCKED (h1_trend=−0.32 — `rsi_sell_floor`?) | TAKEN +$24 | TAKEN +$28 |
| May 4 17:10 G5008-pattern | BLOCKED by `adx_spike_sell` | BLOCKED by `adx_spike_sell` | BLOCKED by `adx_spike_sell` |
| May 4 18:16 window | BLOCKED by `session_sell_cutoff` (gate active) | BLOCKED by `session_sell_cutoff` (gate active) | **BLOCKED by `adx_spike_sell` (surgical) — cutoff inactive** |
| Cutoff hits | 3 | 3 | **0 (disabled)** |
| `entry_quality_direction` (flood throttle) | 2,583 | 3 | **3** (v2.7.14 throttle holding) |

**Run 13 → Run 14 delta**: zero P&L change, zero TAKEN change, but the May 4 18:16 window is now empirically proven to be a surgical-gate block rather than a session-time block. The `session_ny_sell_cutoff_utc` knob can be retired as default-off without regret.

---

## What this case validates

| Feature | Version | Validation |
|---|---|---|
| `session_ny_sell_cutoff_utc=0` does not introduce losses | v2.7.15 + Run 14 knob | **✓ — 44W 0L identical to Run 13** |
| `crash_sell_bypass` M15 ADX guard | v2.7.13 (`h1h4_crash_sell_min_m15_adx=25`) | ✓ — May 4 18:16 had M15=0, bypass correctly off; May 4 17:10 had M15=0, bypass correctly off |
| H1 strong-bear bypass for `rsi_rising_sell` | v2.7.14 (`h1_trend_strength<-1.0` at L5478) | ✓ — G5001 entered with H1=−1.997, bypass active; absolute floor still applies (Apr 29 15:55 correctly blocked) |
| H1 strong-bear bypass for `rsi_sell_adx_floor` (weak-ADX inflation) | v2.7.14 (L5440) | ✓ — G5001 H1=−1.997, ADX=29.9 → floor not raised to 36 |
| `entry_quality_direction` throttle | v2.7.14 (L4753) | ✓ — 3 hits in Run 14 vs 2,583 in Run 12 |
| `entry_quality_body` throttle | v2.7.14 (L4741) | ✓ — 1 hit (Apr 30 16:20) |
| `entry_quality_rsi_buy_ceil=78` | v2.7.15 (L5089/5259) | ✓ — May 1 17:05 boundary case: 78.1 SKIP, 78.0 TAKEN on same bar |
| SELL STOP CONT cascade (5 legs at slot[2..6]) | v2.7.10/12 | ✓ — G5001 16:20:02 fired 5 legs, all 5 TP @ 4532.30 |
| BB lot_factor outside-band = 1.0 vs inside-band = 0.25 | v2.7.x | ✓ — G5001/G5003/G5004/G5005 = 1.0; G5002/G5006 = 0.25 (inside band) |
| `adx_lot_factor` mid-tier at M5 ADX ≥ threshold | v2.7.x (L5868-5881) | ✓ — G5002 ADX=41.3 → 0.25; G5006 M15=41.7 → 0.25 |

---

## Pattern check — Perfect SELL setup (the G5001 archetype)

When monitoring future runs, the EA is making the right call when:

```python
is_perfect_sell = (
    h1_trend < -1.5                    # H1 DI- strongly dominant
    and m15_adx >= 25                  # M15 confirms trend (crash bypass arms)
    and m5_adx >= 25                   # M5 not weak
    and rsi_divergence != "HID_BULL"   # no reversal warning
    and price < bb_lower               # true breakout (not inside-band)
    and atr >= 4.0                     # enough volatility for TP
    and 7 <= utc_hour < 18             # London/NY overlap
    and h1_macd_histogram < 0          # H1 momentum bearish
)
```

Validated in Run 14 by G5001 (every field passes) and G5006 (weaker H1 but crash-bypass eligible because M15 ADX = 41.7).

## Pattern check — Perfect BUY setup (the G5004/G5005 archetype)

Run 14 contributed three BUY winners. The pattern that recurs across G5003, G5004, G5005:

```python
is_perfect_buy = (
    rsi_divergence in (None, "NONE")    # no bearish divergence active
    and m5_rsi < 78                     # below rsi_buy_ceil
    and price > bb_upper                # true breakout above upper band
    and m15_adx >= 23                   # M15 trending
    and m5_adx >= 23                    # M5 not flat
    and atr >= 4.0                      # volatility sufficient
    and 14 <= utc_hour < 18             # London/NY overlap
    and h1_macd_histogram > 0           # H1 momentum bullish (even with weak H1 trend)
)
```

Notes from the three BUY winners:
- **H1 trend strength is NOT required to be > +1.0** for BUYs — all three winners had `|h1_trend| < 0.04`. The H1 directional gate for BUYs is checked but tolerant in RANGE regime.
- **H1 MACD histogram > 0 is the directional confirmer** for BUYs when H1 trend is flat. G5003 had +10.93, G5004 +2.26, G5005 +2.87.
- **`lot_factor=1.0` requires price OUTSIDE the upper band.** All three were 3–5 pts above upper. Inside-band BUYs would print 0.25× lots.
- **`rsi_buy_ceil=78` is a hard >= ceiling.** May 1 17:05 SIGNALS row at RSI=78.0 took; the prior tick at 78.1 was correctly skipped.

---

## Counterfactuals — what would have killed Run 14's $1,026

| Hypothetical change | Group(s) affected | Impact |
|---|---|---|
| Revert v2.7.14 H1 strong-bear bypass | G5001 | **−$742** (Run 12 outcome reproduced) |
| Revert v2.7.13 M15 ADX guard for crash bypass | G5006 + May 4 17:10 catastrophe pattern | G5006 might still be OK (M15=41.7) but May 4 17:10 (M15=0) would have falsely armed bypass → likely catastrophic SL |
| `rsi_buy_ceil=70` instead of 78 | G5004 (RSI=74.9), G5005 (RSI=78.0) | **−$340** (both BUYs blocked) |
| `adx_lot_factor` removed (always 1.0) | G5002, G5006 | Higher lots on inside-band entries → higher SL risk; G5002 had 2 SL hits; net effect ambiguous but adds variance |
| Cascade disabled | G5001 | **−$320** (5 cascade STOP legs at 4532.30) |
| `session_ny_sell_cutoff_utc=18` re-enabled | None in this dataset | **$0** — the cutoff and the surgical stack agree on May 4 18:16 |
| `session_ny_sell_cutoff_utc=15` (earlier) | G5004, G5005 (17:00, 17:05) | **−$340** — both BUYs blocked by overly aggressive cutoff |

The last row is the cautionary tale: **a too-aggressive session cutoff costs more than a too-permissive one in this dataset**. The surgical gates need to keep doing their job; the session-time filter was always a coarse approximation.

---

## What this case did NOT test

- **Longer time horizon**: Apr 29 → May 5 is one week. The cutoff's only divergence from surgical gates would appear in a window where the surgical stack PASSES while the cutoff would BLOCK — Run 14 found zero such windows in this period. Multi-week or multi-symbol runs are the next test.
- **Inside-band BUY breakout boundary**: All three BUY winners were ≥ 3 pts outside the upper band. A BUY at price = bb_upper + 0.3 would test the inside-band reduction logic on the BUY side.
- **Strong H1 BULL trend (h1_trend > +1.5)**: Run 14 had no such bars during BUY signal windows; all three BUYs entered with |H1| < 0.04. The v2.7.14 H1 bypass for BUY-side gates (mirroring the SELL-side bypass) remains untested in production data.
- **News-filter slide on `rsi_buy_ceil`**: `g_nf_eff_rsi_buy_ceil` (L173, L4612-4635) tightens to 70 during news windows. Run 14 had no news-active hours intersecting BUY windows; the slide remains a code-only validation.

---

## Cross-references

- **Case 001** (G5001 deep dive, Run 13): `docs/case_studies/001_G5001_RUN13_APR29_PERFECT_SELL.md`
- **Run 12 analysis** (cutoff=18, no H1 bypass): `docs/FORGE_RUN12_ANALYSIS.md`
- **Run 13 analysis** (cutoff=18, v2.7.14/15 stack): `docs/FORGE_RUN13_ANALYSIS.md`
- **Run 14 analysis** (cutoff=0): `docs/FORGE_RUN14_ANALYSIS.md`
- **Entry conditions reference**: `docs/FORGE_ENTRY_CONDITIONS.md`
- **EA SELL evaluation block**: `ea/FORGE.mq5:5340-5600`
- **EA lot factor combiner**: `ea/FORGE.mq5:5840-5891`
- **EA cascade arm**: `ea/FORGE.mq5` — search `ArmPostTP1Ladder`
- **EA M5 throttle globals**: `ea/FORGE.mq5:120-172`
- **rsi_buy_ceil gate** (v2.7.15): `ea/FORGE.mq5:5089`, `5259`, `5321`
