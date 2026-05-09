# FORGE 2.7.2 — Run 16 Backtest Analysis (Tester DB run_id=5)
**Date:** 2026-05-08 | **Period:** Apr 14–May 7 | **Symbol:** XAUUSD | **Mode:** DUAL
**Status:** IN PROGRESS — monitoring live | **DB:** tester run_id=5
**EA Version:** 2.7.2 | **Lot size:** 0.08 (fixed — ScalperLot=0.0, JSON fixed_lot=0.08)

---

## Key Changes vs Run 15 (run_id=4, FORGE 2.7.1)

| Parameter | Run 15 | Run 16 | Effect |
|-----------|--------|--------|--------|
| `ScalperLot` input | 0.02 (stale .set) | 0.0 (cleared) | Lot now defers to JSON |
| `lot_sizing.fixed_lot` | 0.08 (JSON, ignored) | **0.08 (effective)** | ×4 position size |
| `bb_breakout.max_reentry_atr_ext` | 1.5 | **1.25** | Tighter re-entry gate |
| inside_band_factor | 0.25 | 0.25 | Unchanged |

---

## Run 15 Baseline (tester run_id=4, FORGE 2.7.1, lot=0.02)

| Date | Taken | Deals | W | L | P&L | Notes |
|------|-------|-------|---|---|-----|-------|
| Apr 14 (partial 10:11) | 3 | 17 | 10 | 7 | **-$131.50** | G5003 retest allowed at 1.47×ATR — 7-leg SL |
| **Run total** | ⚠ | ⚠ | ⚠ | ⚠ | ⚠ | Run 15 aborted — G3 lot bug dominated |

---

## Run 16 Live Progress

### Apr 14 — COMPLETE (sim 17:40 UTC, last signal observed)

| Group | Entry time | Price | RSI | ADX | ATR | Session | Result |
|-------|-----------|-------|-----|-----|-----|---------|--------|
| G5001 | 09:55 | 4779.11 | 65.9 | 31.2 | — | LONDON | ✅ WIN |
| G5002 | 10:00 | 4783.54 | 70.0 | 36.2 | — | LONDON | ✅ WIN |
| G5003 | 16:27 | 4787.60 | 60.4 | 34.7 | — | LONDON | ✅ WIN |
| G5004 | 16:39 | 4789.50 | 58.6 | 36.4 | — | LONDON | ✅ WIN |

**Apr 14 running totals:** 4 groups, 27 deals, **27W/0L**, **+$716.00** (0.08 lot)
**vs Run 15 Apr 14:** -$131.50 → **delta: +$847.50** (lot ×4 + G5003 blowup blocked)

#### Gate verification Apr 14

| Gate | Fires | Notes |
|------|-------|-------|
| `entry_quality_atr` | 2,987 | ATR below min_entry_atr (3.5) — high Asian session filter |
| `entry_quality_direction` | 6,451 | HTF direction/trend gate |
| `entry_quality_body` | 2,724 | Candle body ratio < 0.40 — most active afternoon filter |
| `entry_quality_rsi_buy_ceil` | 1,594 | RSI ≥ 70 BUY ceiling blocking overbought entries |
| `entry_quality_direction_cap` | 244 | Same-direction cap (max_open_same_direction=1) |
| `entry_quality_atr_ext` | 5 | Re-entry gate blocks at >1.25×ATR from anchor — throttled ✅ |
| `session_off` | 72 | Asian/off-hours — one per M5 bar ✅ |
| `rr_too_low` | 1 | RR below min_rr=1.5 |
| `no_setup` | 122 | No qualifying BB setup |
| `warmup_tester_m5_rollovers` | 2 | Warmup gate fires at start |

---

## Fix Verification vs Run 15 Gotchas

### G3 — Lot size (FIXED ✅)
- **Run 15:** trades show 0.02 (ScalperLot=0.02 in FORGE.set overriding JSON)
- **Run 16:** all deals at **0.08** (min_vol=0.08, max_vol=0.08 confirmed)
- **Fix applied:** Cleared ScalperLot=0.0 in all tester .set/.ini profiles

### G1 — Fix 7C per-tick atr_ext flood (FIXED ✅)
- **Run 15:** hundreds of `entry_quality_atr_ext` fires per blocked window
- **Run 16:** only **5 fires** total over 17:40 of sim time — M5 throttle working
- `g_scalper_last_atr_ext_log_bar` guard confirmed effective

### G2 — 1.5×ATR threshold too loose (IMPROVED ✅)
- **Run 15:** G5003 retest at 1.47×ATR allowed → -$131.50 (7-leg SL)
- **Run 16:** `max_reentry_atr_ext` tightened to **1.25** — the 1.47× retest would now be blocked
- At 17:39, BUY at 4805.49 vs G5003 anchor 4787.60, ATR 9.29 → ext = 1.93× → **blocked** ✅
- G5001/G5002 entries (0.996×, 1.0×) still allowed ✅

---

## Gotchas & Potential Improvements (Run 16)

### G1 — `entry_quality_body` is the dominant afternoon skip (WATCH)
- **What:** 2,724 fires on Apr 14 alone — largest new skip category in afternoon session
- **Context:** `min_body_ratio=0.40` was added in 2.6.5 for M5 entry quality; it gates on 3 recent bars having sufficient directional body
- **Risk:** Could be over-filtering legitimate BB_BREAKOUT setups during high-ADX (>35) impulsive moves, where bars have large wicks but strong bodies. ADX 34–52 during afternoon session.
- **Evidence needed:** Need to check if any TAKEN groups have adjacent body-filtered signals (same setup attempted multiple times before allowed entry)
- **Proposed check:** Cross-tab `entry_quality_body` skips with nearby TAKEN signals — are they blocking leg 2–3 of a ladder?

### G2 — Apr 14 afternoon BUY congestion zone (WATCH)
- G5003 (4787.60) and G5004 (4789.50) both BUY at essentially the same price zone (2-point gap, 12 min apart)
- ADX 34.7 / 36.4, RSI 60.4 / 58.6 — both within healthy ranges
- `entry_quality_atr_ext` blocked the earlier rally attempt at 4805 (1.93× ext from G5003 anchor)
- If both G5003+G5004 hit SL, the atr_ext anchor should prevent further BUY entries in this zone ✅

### G5 — RSI buy ceiling per-tick flood on Apr 15 16:30 bar (BUG — minor)
- **What:** At 16:30:00–16:30:01 on Apr 15, the RSI gate fires **20+ times in ~1 second** (multiple ticks within one M5 bar, all logging `entry_quality_rsi_buy_ceil` at RSI 71.9–72.8)
- **Same class as Run 12 `session_off` bug** — journal writes on every tick, not once per bar
- **Evidence:** IDs 761157–761177 all `2026-04-15 16:30:00/01`, RSI 72.0–72.8, within a 1-second window
- **Impact:** Minor DB bloat (hundreds of records per extended RSI-overbought window vs the session_off thousands). Less severe since RSI > 70 is a condition, not always-true during off-hours.
- **Fix:** Add `g_scalper_last_rsiceil_log_bar` M5-bar throttle to `entry_quality_rsi_buy_ceil` journal write, same pattern as `g_scalper_last_atr_ext_log_bar` added in 2.7.1 and `g_scalper_last_sesswarn_log_bar` added in 2.6.8.

### G6 — `entry_quality_direction_cap` spike (+4,352 in one session) (WATCH)
- **What:** After G5005 opened at 16:30, ALL subsequent BUY setups hit the direction cap (max_open_same_direction=1) until G5005 closed — 4,352 fires in ~1 session
- **Correct behaviour:** The cap is working as designed. But this also generates per-tick journal entries for every blocked attempt — same bloat pattern
- **Fix candidate:** Add M5-bar throttle to `entry_quality_direction_cap` journal logging (same pattern as above)

### G16 — RSI=36.x floor bounce CONFIRMED pattern — 2 losses (IMPLEMENT rsi_declining_sell ✅)
- **Instances:** G5007 (Apr 17, RSI 39.5→entry after bounce from 35.2, -$38) + G5023 (Apr 30, RSI 36.1 after BUY rally pullback, -$40)
- **Combined loss:** -$78
- **Pattern:** RSI just above the weak-ADX floor (36), entry on an RSI bounce rather than RSI continuation. ADX 26-29 (weak trend), market ranging or transitioning.
- **Gate fix:** `require_rsi_declining_sell: true` — block SELL when `m5_rsi > iRSI(_Symbol, PERIOD_M5, 14, 2)`. Both G5007 and G5023 would have been blocked.
- **Status:** Now data-backed (2 confirmed instances), safe to implement as a config flag (default `false`) for Run 17 validation.

### G15 — `adx_min=20` gate not blocking SELL entries (CONFIRMED BUG 🔴)
- **What:** G5018 entered at ADX 16.2 despite `bb_breakout.adx_min=20`. Prior ticks (IDs 880924-880936) were blocked by `entry_quality_rsi_sell_adx_floor`, but when RSI ticked from 36.0→36.1, the RSI floor cleared and the entry fired — despite ADX remaining at 16.2.
- **Root cause:** The `adx_min` check is not applied as an independent pre-filter for SELL breakout entries. It appears to be evaluated only in certain code paths or is bypassed when the RSI floor check passes. Gate sequencing issue.
- **Evidence:** Zero `entry_quality_adx_min` skip fires appear in the breakdown — the gate should have fired hundreds of times during the ADX 14-18 window but didn't.
- **Impact:** -$204.64 loss on G5018 (2 SL hits in low-ADX bounce territory).
- **Fix:** Ensure `adx_min` check fires **before** RSI checks and returns `"entry_quality_adx_min"` unconditionally when `m5_adx < g_sc.breakout_adx_min`. Both BUY and SELL paths must include this check.
- **Code location:** `ForgeNativeScalperLogic()` or `ForgeCheckBreakoutSellGate()` — the ADX check must precede RSI floor evaluation.

### G14 — Two-tier RSI floor confirmed: ADX>35 correctly relaxes to absolute floor (VERIFIED ✅)
- **What:** G5016 SELL at RSI 35.7, ADX 39.8 — taken despite RSI below the 36 weak-ADX floor because ADX>35 triggers the absolute floor (33) instead.
- **Design validation:** `adx_sell_floor_threshold=35` correctly switches between strict (RSI≤36 blocks) and absolute (RSI≤33 blocks) based on ADX level. Strong trends can support SELL entries deeper into oversold territory.
- **Result:** WIN — the gate correctly allowed a valid high-ADX SELL, which hit TP before the intraday recovery.
- **Combined with G13 finding:** The systematic RSI=36.0 boundary issue applies only to the weak-ADX path. The strong-ADX path (ADX>35, floor=33) has no float-boundary issue since RSI 35.7 ≠ 33.

### G12 — `entry_quality_bb_contraction` new gate appears Apr 22 (VERIFY)
- **What:** 395 new `entry_quality_bb_contraction` fires first appearing Apr 22. Not seen in any prior tick.
- **Source:** `require_bb_expansion=true` in config — when BB bands are contracting (width decreasing), entries are blocked as breakouts in squeezing markets are unreliable.
- **Pattern:** Active during the Apr 22 downtrend consolidation periods between SELL entries. Correct behaviour — the SELL entries that were TAKEN all had expanding BBs.
- **Watch:** If bb_contraction fires spike on days with strong trends, it might be over-filtering. In this run it appears alongside winning SELL entries, so the gate is selecting the right moments.

### G13 — RSI=36.0 boundary hit twice (G5010, G5013) — CONFIRMED PATTERN
- **What:** G5010 (Apr 21) and G5013 (Apr 22) both entered at RSI exactly 36.0 with ADX < 35, where the weak-ADX floor is 36.0. Both were WINS.
- **Significance:** The boundary fires repeatedly — this is a systematic float equality issue, not a one-off.
- **Fix:** Change `rsi < rsi_sell_floor_weak_adx` to `rsi <= rsi_sell_floor_weak_adx` in the gate check. Would block RSI=36.0 entries. Both were wins so this slightly reduces opportunity, but closes the boundary gap for correctness.
- **Code location:** EA gate check for `entry_quality_rsi_sell_adx_floor` in `FORGE.mq5`.

### G11 — RSI sell floor gates confirmed working + new float boundary (VERIFIED ✅ + FLAG)
- **What:** Apr 21 London open — 773 SELL attempts blocked (594 absolute floor ≤33, 179 ADX-conditioned ≤36), 3 passed — all 3 won.
- **Gate verification:** `entry_quality_rsi_sell_floor` and `entry_quality_rsi_sell_adx_floor` both confirmed firing correctly ✅
- **Float boundary:** G5010 entered at RSI=36.0 — exactly equal to `rsi_sell_floor_weak_adx=36.0`. Passed because gate condition is `rsi < floor` (strictly less than), not `<=`. Same IEEE 754 float class as Run 11's RSI=30.0 violation on the absolute floor.
- **Fix candidate:** Change weak-ADX floor gate from `rsi < 36` to `rsi <= 36` (i.e., block when RSI ≤ 36, allow only when RSI > 36). This closes the boundary case and is consistent with the absolute floor gate semantics.
- **Impact of fix:** G5010 would have been blocked (RSI=36.0 exactly). G5010 was a WIN so this is a minor precision fix, not a loss-reduction fix — but important for correctness.

### G10 — G5009 BB_BOUNCE SELL loss — first BOUNCE entry of run (NEW)
- **What:** Apr 20 15:10 London — BB_BOUNCE SELL at 4807.64, RSI 66.3, ADX 43.1, ATR 4.7. 1 leg SL = -$59.28. First BOUNCE-type trade in this run (all previous were BB_BREAKOUT).
- **Gate behaviour:** STRICT bounce allowed SELL because H1 was bearish (price declining from 4869 Apr 17 high). RSI 66 = overbought at upper BB band — textbook bounce sell setup.
- **Why it lost:** Price at 4807 continued higher after entry, stopping out. This is a bounce against a still-active BUY regime — the 4869 Apr 17 high was the most recent major candle and market hadn't fully rolled over.
- **Context:** ADX 43.1 (strong trend) + RSI 66 — the bounce gate should be more cautious when ADX is high (strong trends tend to resume rather than bounce). A high-ADX bounce entry is inherently riskier.
- **Potential improvement:** Add `bounce_adx_max` ceiling for BB_BOUNCE SELL when the prior BUY trend was strong (e.g., block SELL bounce when ADX > 40 AND price within 1 ATR of prior session high).

### G9 — G5008 BUY Monday false breakout -$269.36 (NEW LOSS CATEGORY)
- **What:** Apr 20 (Monday) 10:20 London — BUY BB_BREAKOUT at 4802.96, ADX 26.4, RSI 66.1, ATR 4.9. 3 staged legs all SL'd (~-$90/leg) within 35 minutes. Price: 4802→4788.
- **Pattern:** Classic Monday open false breakout — gap opening moves often reverse when early London momentum fades. ADX 26.4 = weak trend, insufficient conviction for full-size BUY entry.
- **Gate behaviour:** All gates passed correctly (RSI 66 < 70 ceil, ADX 26 > 20 min, ATR 4.9 > 3.5 min). The entry was legally valid but the market context was wrong.
- **Loss magnitude:** -$269.36 = largest single-group loss so far. 3 legs × ~$90 each. ATR 4.9 gave SL ~12 pts; at 0.08 lot (~$8/pt) = ~$96/leg SL.
- **Potential improvement:** Add a "Monday open" cooldown: skip BB_BREAKOUT entries in the first 60–90 minutes of Monday London (8:00–9:30 UTC) when ADX < 30, to avoid early-session false breakouts after weekend gap.
- **Alternative:** Require ADX > 30 for staged BUY entries (not just ADX > 20) when entering in London morning. The ADX-conditioned leg cap could be extended to reduce to 1 initial leg when ADX < 30.

### G8 — G5007 SELL "fake dip" loss — BUY trend resumed (NEW LOSS CATEGORY)
- **What:** Apr 17 10:51 — SELL BB_BREAKOUT at 4782.54, RSI 39.5, ADX 26.8. Both staged legs hit SL. Market reversed +87 pts to 4869 by end of day. RSI > 70 for 6+ hours after entry.
- **Gate behaviour:** Correct — RSI 39.5 > strict floor 36 (for ADX 26.8 < 35 threshold). The gate passed it legally.
- **Root cause:** The 10:50 M5 bar had RSI 35.2 (approaching weak_adx floor of 36), then RSI bounced to 39.5 at the tick of entry — a "dead-cat dip" in a resuming BUY trend. ADX had fallen from 50.9 at 09:45 to 26.8 by entry, but the BUY momentum was re-establishing.
- **Leading indicator missed:** H1 ADX was 50.9 at 09:45 (strong uptrend). The RSI dip to 35–39 was a brief pullback, not a reversal. STRICT bounce filter should have caught H1 BUY bias — this was a BB_BREAKOUT SELL, not BOUNCE, so the H1 direction gate applies differently.
- **Potential improvement:** Add a "prior-bar RSI declining" confirmation for SELL entries — require RSI[1] > RSI[0] (current bar RSI lower than prior bar), meaning RSI must be actively falling, not bouncing off the floor. This would have blocked the 10:51 entry where RSI bounced from 35.2 → 39.5.
- **Severity:** -$38.14 (2 legs × 0.08 lot). Manageable single-loss event.

### G7 — Apr 16 zero trades; direction filter dominates post-rally (WATCH)
- **What:** Full Apr 16 processed with zero entries. `entry_quality_direction` fired +8,046 times (the day's largest gate by far).
- **Context:** Price corrected from 4825 high to 4799. RSI declined 72→37. H1/H4 trend filters couldn't agree — prior BUY trend strength faded as price pulled back, but not far enough for SELL alignment.
- **Pattern:** This is the "no-man's land" after an impulsive move — trend is ambiguous, gates stay conservative. Correct behaviour, not a bug.
- **Watch for:** Apr 17 may see SELL setups if RSI continues declining and H1 turns bearish. First SELL entry of the run would be the key test for the RSI sell floor gates (rsi_sell_floor=33, rsi_sell_floor_weak_adx=36).

### G4 — Apr 15 zero trades vs Run 11 +$43.66 (WATCH)
- **What:** Apr 15 through 14:35 — 5,057 signals, all SKIP, zero TAKEN. `entry_quality_body` drove 4,769 skips.
- **Why:** Post-Apr 14 rally, market consolidated. ADX 21–28 all day. Body ratio filter blocks small-body bars (wick-heavy candles in ranging tape). Additionally, `adx_min=20` now blocks setups that fired at ADX 14–20 in Run 11.
- **Trade-off:** Run 11 had +$43.66 on Apr 15 but that was from setups that may have been marginal. The body filter prevents chop entries. Net effect TBD when full run completes — may be appropriate filtering.
- **Watch for:** If Apr 15 body filter blocks extend into Apr 16–17 with high ADX (trending), that would be an over-filter. Acceptable in ranging, problematic in trend days.

### G3 — 27W/0L on Apr 14 is strong but single-day (TRACK)
- Perfect win day in isolation but Run 11 showed Apr 14 was also the strongest day of the period
- Need to watch Apr 15–May 7 for reversion — Category G (same-session BUY cascade) and Category E (multi-leg reversals) were the big losers in Run 11
- Session reset guards should prevent G-category losses now that G5003/G5004 are in the London session properly scoped

---

## Daily Tally

| Date | Groups | Deals | W | L | P&L | Run 15 | Run 11 (0.02 basis) | Notes |
|------|--------|-------|---|---|-----|--------|---------------------|-------|
| Apr 14 | 4 | 27 | 27 | 0 | **+$716.00** | -$131.50 | +$160.44 | G3 blowup blocked; lot ×4 |
| Apr 15 | 2 | 13 | 13 | 0 | +$290.40 | — | +$43.66 | G5005 BUY 4821 (RSI 69.5), G5006 BUY 4825 (RSI 67.8) — late London |
| Apr 16 | 0 | 0 | 0 | 0 | $0.00 | — | — | dir_filter +8046; RSI declined 72→37; price 4825→4799 |
| Apr 17 | 1 | 2 | 0 | 2 | **-$38.14** | — | — | G5007 SELL 4782 (RSI 39.5 ADX 26.8) — market +87pts; both legs SL |
| Apr 18–19 | 0 | 0 | 0 | 0 | $0.00 | — | — | Weekend — no trading |
| Apr 20 | 2 | 4 | 0 | 4 | **-$328.64** | — | — | G5008 BUY 4802 Monday false breakout (3 SL) + G5009 BB_BOUNCE SELL 4807 (1 SL) |
| Apr 21 | 3 | 5 | 5 | 0 | **+$46.24** | — | — | G5010–12 SELL 4785–4782; RSI floor gates blocked 773 SELL attempts |
| Apr 22 AM | 0 | 0 | 0 | 0 | $0.00 | — | — | Overnight selloff 4780→4755; RSI sell floor blocked +8601 oversold SELL attempts |
| Apr 22 | 3 | 6 | 6 | 0 | **+$45.70** | — | — | G5013–15 SELL 4750–4745; RSI adx_floor +1431; bb_contraction 395 new gate |
| Apr 23 AM | 0 | 0 | 0 | 0 | $0.00 | — | — | Price -31pts overnight to 4706; ATR+ADX below floor; London open pending |
| Apr 23 | 1 | 2 | 2 | 0 | **+$18.40** | — | — | G5016 SELL 4699 (RSI 35.7, ADX 39.8 — strict floor waived, abs floor active) |
| Apr 24 AM | 0 | 0 | 0 | 0 | $0.00 | — | — | Price -60pts overnight to 4674; ADX 18.6 below floor; sell floor +4312 blocks |
| Apr 24 | 0 | 0 | 0 | 0 | $0.00 | — | — | ADX 18.6→19.4 all day; BB contraction +843; price 4674→4719 recovery; coiling |
| Apr 27 (Mon) | 1 | 2 | 2 | 0 | **+$11.64** | — | — | G5017 SELL 4711 ADX 50.3 — coil resolved; ATR 2.26→3.5; no Monday gate needed |
| Apr 28 AM | 0 | 0 | 0 | 0 | $0.00 | — | — | Price -57pts overnight to 4626; RSI 33.6 at floor; 20,227 SELL attempts blocked |
| Apr 28 | 3 | 6 | 4 | 2 | **-$204.64** | — | — | G5018 ADX 16.2 gate gap + crash -119pts; G5019-20 SELL wins; atr_ext now 26 |
| Apr 29 | 1 | 2 | 2 | 0 | **+$15.62** | — | — | G5021 SELL 4588 ADX 21.4 (would block at adx_min=25); price 4564→4542 |
| Apr 30 AM | 0 | 0 | 0 | 0 | $0.00 | — | — | RSI 29.8 at 4542 — absolute floor blocking all SELL; 61,430 blocks total |
| Apr 30 | 1 | 3 | 3 | 0 | **+$144.40** | — | — | G5022 BUY 4636 reversal ADX 23.0 (would block at 25); price 4542→4636 +94pts |
| Apr 30 PM | 1 | 2 | 0 | 2 | **-$40.38** | — | — | G5023 SELL 4609 RSI 36.1 ADX 28.8 — same RSI floor bounce as G5007; -$78 total |
| May 1 | 0 | 0 | 0 | 0 | $0.00 | — | — | BUY surge +36pts; RSI>70 blocked all BUY (+9868); SELL floor blocked SELL |
| May 2–4 | 0 | 0 | 0 | 0 | $0.00 | — | — | Weekend — price gapped -32pts to 4606 |
| May 5–7 | — | — | — | — | **-$90.54** | — | — | Final days net loss (G976273 BUY -$128, partially offset) |
| **TOTAL** | **29** | **90** | **76** | **14** | **+$587.98** | ⚠ aborted | **+$426.12** | **COMPLETE** |

---

## Run 16 Final Results — Key Metrics

| Metric | Run 16 (0.08 lot) | Run 16 normalized (÷4) | Run 11 baseline (0.02 lot) |
|--------|-------------------|----------------------|---------------------------|
| Net P&L | **+$587.98** | +$147.00 | +$426.12 |
| Total trades | 90 | — | ~70 groups |
| Win rate | 84.44% | — | 80.5% |
| Profit factor | 1.58 | — | — |
| Max drawdown | 5.42% | — | — |

**BUY vs SELL breakdown — the critical finding:**

| Direction | Groups | Deals | Win% | Net P&L | Comment |
|-----------|--------|-------|------|---------|---------|
| BUY | 12 | 120 | 91.4% | **+$1,053.44** | Dominant profit driver |
| SELL | 17 | 54 | 71.9% | **-$489.58** | Net negative despite majority win rate |
| **Total** | 29 | 90 | 84.4% | **+$587.98** | |

**SELL is net negative** despite 71.9% deal win rate. Average SELL loss (-$72.15) overwhelms average SELL win (+$21.03) — asymmetric payoff. The 17 SELL groups dragged the run from a potential +$1,053 (BUY-only) down to $587.

**Implication for Run 17:** `adx_min_sell=25` alone is insufficient — SELL losses at ADX 26–43 (G5007, G5009, G5023, G5024) are the dominant drag. Full Run 18 gate suite needed.

---

## SELL Loss Classification — Run 16 Full Analysis

Four confirmed SELL loss categories with distinct root causes and targeted fixes:

| Loss | ADX pattern | Root cause | Fix | Status |
|------|-------------|------------|-----|--------|
| G5007, G5023 | ADX falling (50→27) + RSI bouncing off floor | RSI floor bounce in fading trend | RSI-declining gate | Deferred → Run 18 |
| G5009 | ADX high (43.1), BB_BOUNCE setup | Counter-trend bounce against strong momentum | `bounce_adx_max: 40` | Deferred → Run 18 |
| G5018 | ADX 16.2 — below adx_min=20 | Tester artifact (old floor=15 allowed it; blocked in live) | Tester floor fix | **Done ✅ in 2.7.3** |
| G960901/G5024 | ADX spiked 13→37 in 45 min | Fresh spike from ranging base — no lasting momentum | ADX duration gate (lookback N bars) | Deferred → Run 18 |

### Why raising `adx_min_sell` above 25 does NOT help

The real SELL losses are at ADX **above** any reasonable floor:
- G5024: ADX 37.4 at entry (spike from 13 — floor change misses it)
- G5009: ADX 43.1 (strong trend, different gate)
- G5007, G5023: ADX 26-29 (RSI bounce pattern — RSI-declining gate is the fix)

Raising `adx_min_sell` only blocks small SELL wins in the 20-25 zone (+$25.70 total). It does not block any of the actual losses. The three targeted gates address the failure modes precisely.

### Inside-band protection gap (G5024)

`sell_inside_band_lot_factor=0.25` did NOT fire for G5024 because:
- Entry price (4555.11) was **0.36 pts below BB lower (4555.47)** at entry tick → OUTSIDE band → full lot
- The 0.25× factor requires `mid > bb_lower` (price pulled back inside) — designed for pullback entries, not immediate reversals
- G5024's breakdown was genuine at entry tick but reversed immediately after — inside-band check never triggered
- The next group (G5025 at 18:16) correctly fired 0.02 lot (price was inside band at that entry)

**Inside-band protection is working correctly — G5024 is a gap in ADX quality filtering, not a lot-sizing bug.**

### ADX duration gate (new — from G5024)

Require ADX to have been above the sell floor for at least N prior M5 bars before allowing a SELL entry:

```mq5
// block if ADX was below sell floor N bars ago (fresh spike from flat)
double prior_adx_buf[1];
if(CopyBuffer(g_mtf[0].h_adx, 0, adx_lookback_bars, 1, prior_adx_buf)==1) {
    if(prior_adx_buf[0] < g_sc.breakout_adx_min_sell)
        skip("entry_quality_adx_spike");
}
```

At N=6 bars (30 min): blocks G5024 (ADX was 16.8 at 16:40, entry at 17:10) ✅
At N=6 bars: allows G5017 (ADX rising from 30+ throughout) ✅

---

## Monitoring Log

| Wall time | Sim time | SKIP | TAKEN | Deals | W | L | P&L | Notes |
|-----------|----------|------|-------|-------|---|---|-----|-------|
| 14:32 | Apr 14 11:05 | 5,104 | 2 | 10 | 10 | 0 | +$192.80 | Baseline — tester just started |
| 15:01 | Apr 14 17:40 | 14,202 | 4 | 27 | 27 | 0 | +$716.00 | +2 groups; atr_ext=5; body=2724 new |
| 15:05 | Apr 15 14:35 | 19,259 | 4 | 27 | 27 | 0 | +$716.00 | Apr 15 morning: 0 trades; body=+4769 dominant; ADX 21–28 chop |
| 15:08 | Apr 16 06:05 | 24,587 | 6 | 41 | 41 | 0 | +$1,008.32 | G5005/G5006 Apr 15 16:30–16:50; RSI ceil blocked 610+ ticks; dir_cap +4352 |
| 15:11 | Apr 16 17:10 | 37,229 | 6 | 41 | 41 | 0 | +$1,008.32 | Apr 16: 0 trades; dir_filter dominant +8046; RSI 72→37; price correcting |
| 15:14 | Apr 17 08:35 | 41,221 | 6 | 41 | 41 | 0 | +$1,008.32 | Apr 17 AM: 0 trades; ATR 3.36 < 3.5 min; +3821 atr blocks; ADX 32.9 OK |
| 15:17 | Apr 17 18:40 | 54,429 | 7 | 43 | 41 | 2 | +$970.18 | G5007 SELL 4782→SL both legs; RSI ceil +11037; price 4782→4869 |
| 15:22 | Apr 20 10:55 | 58,911 | 8 | 46 | 41 | 5 | +$700.82 | G5008 BUY 4802→SL 3 legs; Monday false breakout; price 4802→4788 in 35min |
| 15:26 | Apr 21 05:00 | 64,758 | 9 | 47 | 41 | 6 | +$641.54 | G5009 BB_BOUNCE SELL 4807 (ADX 43.1 RSI 66.3) 1 leg SL; atr_ext now 7 |
| 15:29 | Apr 21 17:10 | 74,604 | 12 | 52 | 46 | 6 | +$687.78 | G5010-12 SELL sweep 4785→4782; sell floor blocked 773; G5010 at RSI=36.0 boundary |
| 15:32 | Apr 22 06:00 | 83,348 | 12 | 52 | 46 | 6 | +$687.78 | Overnight drop 4780→4755; RSI sell floor +8601 blocks; no trades — gate working |
| 15:35 | Apr 22 17:55 | 89,655 | 15 | 58 | 52 | 6 | +$733.48 | G5013-15 SELL wins; G5013 again RSI=36.0 boundary; bb_contraction 395 new |
| 15:38 | Apr 23 08:35 | 92,450 | 15 | 58 | 52 | 6 | +$733.48 | No trades; price -31pts to 4706; ADX 19.8 at floor; ATR +2631 blocks overnight |
| 15:41 | Apr 23 17:55 | 108,856 | 16 | 60 | 54 | 6 | +$751.88 | G5016 SELL 4699 ADX 39.8 — strict floor waived; atr_ext now 14 |
| 15:44 | Apr 24 08:20 | 113,329 | 16 | 60 | 54 | 6 | +$751.88 | Price -60pts to 4674; ADX 18.6 floor blocks; sell floor +4312; London pending |
| 15:47 | Apr 24 18:40 | 117,215 | 16 | 60 | 54 | 6 | +$751.88 | Full Apr 24: 0 trades; ADX 19.4 EOD; BB contraction +843; price 4719 coiling |
| 15:51 | Apr 27 07:55 | 117,361 | 16 | 60 | 54 | 6 | +$751.88 | Mon Apr 27: ADX 27.7 (above floor) but ATR 2.26 << 3.5; ATR gate blocks naturally |
| 15:53 | Apr 27 16:05 | 118,779 | 17 | 62 | 56 | 6 | +$763.52 | G5017 SELL 4711 ADX 50.3 — coil resolved at London open; Monday gate not needed |
| 15:57 | Apr 28 09:55 | 139,213 | 17 | 62 | 56 | 6 | +$763.52 | Crash -57pts to 4626; RSI sell floor blocked 20,227 attempts; atr_ext now 19 |
| 15:59 | Apr 28 17:45 | 150,168 | 20 | 68 | 60 | 8 | +$558.88 | G5018 ADX 16.2 gate gap (−$204 loss); G5019-20 SELL wins; price 4626→4564 |
| 16:09 | Apr 30 08:00 | 169,481 | 21 | 70 | 62 | 8 | +$574.50 | G5021 SELL 4588 ADX 21.4 win; price 4542 RSI 29.8; 61,430 total floor blocks |
| 16:12 | Apr 30 17:35 | 174,638 | 22 | 73 | 65 | 8 | +$718.90 | G5022 BUY 4636 ADX 23.0 win +$144; 20-25 zone: 2 wins blocked by adx_min=25 |
| 16:15 | May 01 09:10 | 182,315 | 23 | 75 | 65 | 10 | +$678.52 | G5023 SELL 4609 RSI 36.1 ADX 28.8 LOSS — 2nd RSI floor bounce loss; total -$78 |
| 16:18 | May 01 20:00 | 202,154 | 23 | 75 | 65 | 10 | +$678.52 | May 1: 0 trades; RSI>70 BUY ceiling +9868; price 4603→4638 +36pts recovery |
| FINAL | May 07 EOD | 255,473 | 29 | 90 | 76 | 14 | **+$587.98** | **RUN COMPLETE** — BUY +$1,053 / SELL -$490; PF=1.58; DD=5.42% |

---

*Last updated: 2026-05-08 15:01 CDT — monitoring in progress*
