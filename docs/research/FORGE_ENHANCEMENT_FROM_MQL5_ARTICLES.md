# FORGE Enhancement Research — MQL5 Article Findings

**Date**: 2026-05-10
**Reviewer**: Background agent (expert forex / XAUUSD M5 scalping perspective)
**FORGE baseline**: v2.7.15
**Sources**: 3 MQL5 articles + their .mq5 source code

Source-of-truth files reviewed:
- `/Users/olasumbo/Downloads/SupportResistanceMonitor.mq5` (668 lines, UTF-8 BOM)
- `/Users/olasumbo/Downloads/GA_Breakout_Master.mq5` (1122 lines, UTF-16 LE — reviewed via UTF-8 conversion at `/tmp/GA_Breakout_Master_utf8.mq5`)
- `/Users/olasumbo/Downloads/Timeframe_Visual_Analyzer.mq5` (710 lines, ASCII)
- `/Users/olasumbo/signal_system/ea/FORGE.mq5` (6907 lines)
- `/Users/olasumbo/signal_system/docs/FORGE_ENTRY_CONDITIONS.md` (intent doc)

Web articles were successfully fetched (all 3 URLs returned content via WebFetch); they confirmed source-code claims but added no algorithm beyond what is in the .mq5.

---

## Executive Summary

The three articles span very different layers: (1) manually-drawn S/R level **monitoring** with state machine, (2) a **structural breakout pattern** built on fractal swings + range qualification + a geometric "votes" filter, and (3) a **visual MTF analyzer** with a trivial 3-TF candle direction agreement check.

Of the three, **Source 2 (GA Breakout Master)** is the highest-value donor. Two of its components are directly applicable to FORGE's two open problems: (a) the **flat-base ADX-spike** false-breakout pattern that the existing `entry_quality_adx_spike_sell` gate already targets at FORGE.mq5:5459-5471 — GA's `RangeQualifies()` and `usedSoft` ATR-cap test (GA:696-761) measures the same "narrow consolidation precondition" *quantitatively* (range height ≤ ATR × 2.0 over ≥8 bars), and could either reinforce that gate or detect cases the lookback ADX threshold misses; and (b) **fractal swing-point detection** (GA:527-545, Bill Williams 5-bar fractal) which FORGE currently lacks — it could provide more honest **structural SL** anchors than the current `FindStructuralSL()` at FORGE.mq5:3801-3819 (which only consults LENS OB zones, possibly empty in tester).

Source 1 (S/R Monitor) and Source 3 (MTF Visual) are mostly drawing/indicator tooling. Source 1's **candlestick reversal pattern detector** (`CheckReversalPatterns()` at SR:580-666) is useful — it would slot into FORGE's existing `ScalperCandlePatternScore()` at FORGE.mq5:3515-3547 (which is only consulted for BB_BOUNCE entries, not BB_BREAKOUT). Adding bearish-reversal-near-BB-upper as an additional **breakout-rejection signal** could MAY catch the same fast-reversal class as G5008 (May 4 17:10) before the HID_BULL divergence finishes forming. Source 3 offers very little — its `CandleDirection()` (TVA:477-501) is too crude (just bullish/bearish candle color); FORGE's `m5_bull/m15_bull/h1_ok_buy` cascade is already strictly superior.

**Caveats**: Every claim below is grounded in code, not the article marketing. The articles' performance claims (e.g., GA's "84-86% WR" framing) are not substantiated by the .mq5 — none of them ships with a backtest report. Treat all "MAY improve" language as exploratory, not guaranteed.

---

## Source 1 — Automating Support and Resistance Monitoring

**File**: `/Users/olasumbo/Downloads/SupportResistanceMonitor.mq5`
**Article**: https://www.mql5.com/en/articles/21961

### What it does

This is an **EA scaffold for chart-drawn horizontal lines** (manually-placed `OBJ_HLINE` support/resistance). It synchronises user-drawn lines into a tracked array (SR:192-215 `SyncAllLines`), then on every tick (SR:382-516 `OnTick`) evaluates each level for six interaction states:

1. **Approach** — `distance ≤ approachTol` → first-time-only alert (SR:407-411).
2. **Touch** — once-per-bar test that level price is between bar high/low ± `TouchTolerancePips` (SR:414-430).
3. **Breakout** — sign of `bid − levelPrice` flips from last tick's sign (SR:432-449).
4. **Reversal** — after a touch, price returns to `sideBeforeTouch` without breakout (SR:451-463).
5. **Retest** — after a breakout, price returns within touch tolerance (SR:466-478).
6. **Candlestick reversal pattern** near the level — `CheckReversalPatterns()` at SR:580-666.

The state machine is the meaningful part. The candlestick pattern detector (Hammer / Shooting Star / Engulfing / Morning + Evening Star / Piercing / Dark Cloud) scans `shift = 1..3` and uses straightforward geometric rules (e.g., Hammer = bull body + lowerShadow ≥ 2×body + upperShadow ≤ 0.3×body, SR:597).

### Key algorithms / logic worth borrowing

- **State machine per level** with `lastSide / sideBeforeTouch / prevValidSide` (SR:64-67, evaluated SR:400-405, 433-449) — clean way to distinguish "true breakout" from "touch-and-reject". This is the conceptual gap in FORGE's BB-band gating: FORGE only checks "prev close beyond band" (FORGE.mq5:5251, 5358) — it does not check whether the band itself was tested and rejected vs. broken with conviction. Note: FORGE has `breakout_use_retest` (referenced at FORGE.mq5:5334-5343) that delays BUY entries to a retest; the SR monitor's "Retest after Breakout" code (SR:466-478) generalizes that.
- **Candlestick reversal patterns** (SR:580-666). These overlap partially with FORGE's existing `ScalperCandlePatternScore()` at FORGE.mq5:3515-3547, but FORGE's version is only consulted for BB_BOUNCE rejection candles (FORGE.mq5:5141-5146) — never for BB_BREAKOUT entries. The SR list of patterns is fuller (Engulfing, Morning/Evening Star, Piercing/Dark Cloud).
- **Approach zone reset on price moving away** (SR:505-511) — auto-clears stale flags. Useful pattern for any "near band" alert that FORGE may add later.

### Where this could enhance FORGE

| Enhancement | FORGE integration point | Type | Benefit (specific, non-hyped) |
|---|---|---|---|
| **Bearish-reversal pattern as additional SELL block at BB upper-band breakout** (Shooting Star, Dark Cloud, Bearish Engulfing within 1-2 bars of prev_close > m5_bb_u) | Add as an additional gate inside the SELL BB_BREAKOUT block, **after** FORGE.mq5:5505 (after the existing HID_BULL gate) but before MACD gate | **inline logic** (port pattern detection from SR:580-666 into a new helper, reuse `iOpen/iHigh/iLow/iClose` like FORGE already does at 4727-4730) | Targets fast-reversal entries where price spikes the upper band on one strong bar then prints a rejection candle. The May 4 17:10 G5008 catastrophe printed a hammer-like rejection structure on M5 right after the break. MAY add another defense layer parallel to HID_BULL, capturing cases where divergence hasn't yet formed. |
| **Bullish-reversal pattern as additional BUY block at BB lower-band breakout** (Hammer, Piercing, Bullish Engulfing on the breakdown bar) | Insert in the SELL BB_BREAKOUT block (the breakdown side) — after FORGE.mq5:5527 (after MACD), parallel to HID_BULL | **inline logic** | MAY reduce false breakdown SELL entries when M5 prints a reversal candle on the breach bar. |
| **Pattern detection unified into `ScalperCandlePatternScore`** (currently only Hammer/Shooting Star/Engulfing per FORGE.mq5:3515-3547 — confirm) | Extend `ScalperCandlePatternScore()` at FORGE.mq5:3515 to add Morning/Evening Star + Piercing/Dark Cloud | **inline logic** (extend existing helper) | Wider pattern coverage for the bounce-rejection check already wired in at FORGE.mq5:5141-5146. Low complexity — same OHLC inputs. |
| Touch-and-reject vs clean-break distinction at BB bands | Add `bb_upper_side_history` state machine (last 3 bars' side relative to band) in `CheckNativeScalperSetups()` near FORGE.mq5:5236 | **inline logic** | MAY help distinguish "second clean break" (high conviction) from "first touch-and-reverse" (low conviction). Today FORGE relies entirely on `prev_close` position. Note: complexity is real — needs cross-bar state, must be M5-bar-throttled to avoid flooding journal logs. |

### Risks / costs

- The SR monitor's state machine assumes a single manually-drawn line price; **FORGE's BB bands move every bar**, so the "side flip" logic must be re-keyed each bar (mid-bar persistence won't work). A simple bar-by-bar memory (last N closes' position vs band) is the right adaptation.
- The candlestick detector iterates `shift=1..3` calling `iOpen/iHigh/iLow/iClose` repeatedly — minor performance cost, comparable to FORGE's existing entry-quality body loop (FORGE.mq5:4726-4736). No tester-incompatible APIs used.
- The SR `OnTick` runs *every tick* (SR:382). Any port into FORGE must integrate with FORGE's existing per-M5-bar throttle pattern (see `g_scalper_last_*_log_bar` globals at FORGE.mq5:125-162) or it will flood journal SKIPs the same way the v2.7.14 / v2.7.15 fixes addressed.
- The pattern functions return on the first match, so multiple simultaneous patterns aren't differentiated — fine for FORGE's needs.
- **Honest scope**: SR's article-level concept of "manually-drawn levels" is **not** what FORGE needs. FORGE has algorithmic levels (BB, POC, VWAP, fib, OB zones). Only the **candle-pattern detector + state machine concept** are portable.

---

## Source 2 — Geometric Asymmetry / Fractal Consolidation Breakouts

**File**: `/Users/olasumbo/Downloads/GA_Breakout_Master.mq5` (UTF-16; analyzed via UTF-8 copy `/tmp/GA_Breakout_Master_utf8.mq5`)
**Article**: https://www.mql5.com/en/articles/21197

### What it does

A pure **indicator-style breakout detector** built around three stages:

1. **Fractal swing detection** (`IsFractalHigh`/`IsFractalLow` at GA:527-545, then `GetLast3AlternatingFractals` at GA:569-657): classic Bill Williams 5-bar fractal (`h > h[i±1] && h > h[i±2]`). The function walks back scanning for the **most recent 3 alternating** swing points (HLH or LHL), preferring same-direction extension over re-alternation. A secondary "soft" fractal test (GA:586-606) accepts `>=` instead of strict `>` to broaden detection.

2. **Range qualification** (`RangeQualifies` at GA:696-761): given the two older fractals p1 and p2, compute `barsSpan = |p2−p1|`, require:
   - Hard: span ≥ `InpRangeMinBarsHard=8` AND height ≤ `InpRangeATRMax=2.0 × ATR` (GA:715-733).
   - Soft fallback: span ≥ 4 AND height ≤ 1.6 × ATR if `InpEnableSoftRangeBars=true` (GA:718-727).
   - **Side-zone test**: within the last 50 bars, price must have come within `InpRangeSideZonePct=0.35 × height` of EITHER the range high OR low (GA:735-759). This verifies the range was actually tested as S/R, not just an arbitrary HH/LL window.

3. **Geometric Asymmetry** (`GeometryAsymmetryInsideRangeOK` at GA:763-861): compare the **last leg** (p0→p1) against the **previous leg** (p1→p2) and award votes:
   - `lenRatio = lenLast/lenPrev ≥ 1.35` (last leg longer than prev) → +1
   - `slopeRatio = (lenLast/dtLast)/(lenPrev/dtPrev) ≥ 1.15` (last leg steeper per unit time) → +1
   - `timeRatio = dtLast/dtPrev ≤ 0.95` (last leg completes faster) → +1
   - Need `votes ≥ InpMinGeometryVotes=2`. There's also a strong-single-factor override: `lenRatio ≥ 1.62 OR slopeRatio ≥ 1.38` forces pass (GA:854-855).
   - Direction `dir = (pr0 > pr1 ? +1 : -1)`, and the last fractal `pr0` must be within `InpLegEndNearBoundaryPct=0.50 × rangePts` of the corresponding boundary (high for bull, low for bear, GA:808-824). This ensures the breakout is being launched **from** the range edge, not from mid-range.

4. **Locked pattern + breakout scan**: validated patterns are stored in `LockedPattern[]` (GA:85-95, GA:213-242) for up to `InpMaxLockBars=30` bars. `CheckAllBreakouts` (GA:864-922) scans for close beyond `rangeHigh + InpBreakBufferPts × _Point` (default 5 pts) — single-bar confirm on close. A 5-bar cooldown (`InpMinBarsBetweenSignals=5`) prevents spam.

The article frames this as "structural" vs reactive breakout detection — meaning the directional bias is established **before** price exits the range.

### Key algorithms / logic worth borrowing

- **Bill Williams 5-bar fractal** (GA:527-545) — clean implementation, zero indicator handles (pure `iHigh`/`iLow`). Reusable as a swing-point primitive.
- **`GetLast3AlternatingFractals`** (GA:569-657) — efficient back-scan that consolidates same-direction extensions (e.g., a higher-high after a high becomes the new HH). Up to `InpMaxScanBars=900` lookback.
- **`CalcRangeHigh/Low` using `iHighest/iLowest` (HH/LL within fractal window)** (GA:674-693) — robust way to compute consolidation extremes that doesn't depend on fractal points being exact extremes.
- **Range qualification with ATR-relative height cap + side-zone retest** (GA:696-761). The side-zone test is the most novel piece: just having a HH/LL window isn't enough; price must have **revisited the edge within 50 bars**. This is a quantitative "this is a real range" signal.
- **Geometry votes (`lenRatio`/`slopeRatio`/`timeRatio`)** (GA:841-858). The math is symmetry-breaking: an accelerating, lengthening, time-compressed last leg = the move is gathering steam **before** the boundary breach.
- **Leg-end-near-boundary check** (`InpLegEndNearBoundaryPct=0.50 × range`, GA:808-824). This filters out asymmetric legs in mid-range.

### Where this could enhance FORGE

| Enhancement | FORGE integration point | Type | Benefit (specific, non-hyped) |
|---|---|---|---|
| **`RangeQualifies()`-style "flat base" detector** to *strengthen* the existing `entry_quality_adx_spike_sell` gate | Augment / replace the lookback-ADX check at FORGE.mq5:5459-5471. Currently FORGE checks one historical ADX value (`adx_min_sell_lookback_bars=6` bars back); GA's range height/ATR ratio is a structural signal. Insert *parallel* to the existing check, OR-merge into a new `entry_quality_breakout_from_flat_base` skip reason. | **inline logic** (use `iATR` handle already at `g_mtf[0].h_atr`; raw `iHighest/iLowest` for height) | The ADX-spike-from-flat pattern is FORGE's known weakness (G5008 May 4 had M5 ADX 37.4 from a 16.7 M15 base). Measuring **height/ATR over the last 8 bars** is a direct, quantitative way to detect the same compression pattern. MAY catch flat-base spikes that the existing 6-bar ADX threshold misses (e.g., where ADX 6 bars ago happens to be > 25 but the price range is still tiny). |
| **Bill Williams fractal swings for structural SL placement** | Add a new helper `FindFractalStructuralSL(is_buy, entry, atr_sl, point)` parallel to `FindStructuralSL()` at FORGE.mq5:3801-3819. Call site for breakouts: FORGE.mq5:5328-5330 (BUY) and the corresponding SELL block ~5630s. Today breakout SL is pure `bid − atr × mult`, no structural anchor at all — see the comment at FORGE.mq5:5327 "Breakout SL is pure ATR — no structural widening". | **inline logic** (no new indicator handle needed; reuse `iHigh`/`iLow`) | Today's `FindStructuralSL()` only checks OB zones (LENS data, may be empty/stale in tester). Adding fractal-anchored SL gives a **broker-independent structural reference** even when OB zones are unavailable. Note: FORGE.mq5:5327 explicitly chose pure-ATR to avoid "blow out RR at TP4" — any addition must respect `min_sl_atr_mult` floor (FORGE.mq5:5329-5330) so we don't widen SL beyond the configured cap. |
| **"Geometric asymmetry" check on the 3 most recent M5 swings as a *breakout confirmation*** (rather than replacement) | Add as an optional gate `require_breakout_asymmetry_buy/sell` — placed after the H4 gates at FORGE.mq5:5320-5326 (BUY) and FORGE.mq5:5589 (SELL). Default off. Reuses fractal helper. | **inline logic** (config flag + fractal helper) | The lenRatio/slopeRatio/timeRatio votes measure "is this breakout being launched by an accelerating impulse, or by a single spike?". MAY catch fake breakouts where the last leg is short/flat/long-duration (none of the 3 votes pass) — opposite quality to G5008's clean impulsive breakout. Honest caveat: this gate would likely have a **low fire rate** at M5 (fractals need 5 bars min to confirm); it should be optional and tested before becoming default. |
| **Side-zone retest detection** to confirm BB bands are acting as S/R | Could feed into `breakout_use_retest` decision at FORGE.mq5:5334. If the band itself has been retested within last 50 M5 bars (GA's logic) → high-quality breakout; if not, defer to retest. | **inline logic** | MAY tighten the existing retest logic. Lower priority than the items above. |

### Risks / costs

- **Fractal lag**: 5-bar fractal requires 2 bars to confirm (need bars `i-2..i+2`). For M5, that's 10 minutes after the swing prints. This means any fractal-based gate adds **latency** relative to FORGE's current 1-bar-ago `prev_close` checks. Acceptable for SL anchoring (SL is set once); marginal for entry gating.
- **Computational cost**: `GetLast3AlternatingFractals` scans up to 900 bars per call (GA:577). At M5 that's ~3 days. FORGE runs `CheckNativeScalperSetups` per tick (FORGE.mq5:915-944 `OnTick` → entry path). Must be **cached per M5 bar** (use `iTime(_Symbol,PERIOD_M5,0)` as a key, same pattern as `g_scalper_last_*_log_bar` globals).
- The article's "5 points breakout buffer" (`InpBreakBufferPts=5.0` × `_Point`) is XAUUSD-friendly (≈ 0.05 USD on a 5-digit gold quote = 50 pts in MT5 point terms — depends on broker tick size). Sanity-check on your broker's XAUUSD point size before porting any pip-thresholded code.
- **`InpRangeMinBarsHard=8` at M5 = 40 minutes** of consolidation. This is a real flat-base check; on a fast XAUUSD trending day (Apr 30 crash), genuine breakouts will *not* have an 8-bar flat base. So this should be used as a *quality* signal (boost confidence / reduce lots) **not** a hard block, or it will kill the trade types FORGE currently profits from (Run 11 Apr 30 +$426 was a fast multi-leg crash, not a slow consolidation breakout).
- The GA EA itself is **stateful with manual buttons + chart objects** — those parts are not portable into FORGE (which is server-side, no chart interaction needed). Strip out the drawing/alert/object code entirely.
- No backtest report ships with the .mq5; treat all "votes ≥ 2 = high probability" claims as the author's design intent, not measured edge.

---

## Source 3 — Multi-Timeframe Visual Analyzer

**File**: `/Users/olasumbo/Downloads/Timeframe_Visual_Analyzer.mq5`
**Article**: https://www.mql5.com/en/articles/20387

### What it does

A **chart overlay indicator** that draws HTF1 (default H1) + HTF2 (default M30) candles as filled rectangles + wicks on the current TF chart (TVA:344-399 `DrawHTF`, `CreateOrUpdateCandle` at TVA:169-273). The "alignment" logic is trivial:

- `CandleDirection(tf, idx)` at TVA:477-501 — return `+1` if `c > o`, `-1` if `c < o`, 0 if equal or below `MinPipsForSignal`.
- `CheckAndAlert()` at TVA:570-612 — if `dirHTF1 == dirHTF2 == dirNow` (all 3 last-closed bars agree), fire a confirmation alert. Optional opposite-direction alerts when all three flip together.

That's the entire "MTF synthesis". There is **no scoring**, **no weighting**, **no ADX/RSI/EMA component**, **no strength quantification** beyond a single `MinPipsForSignal` cutoff.

### Key algorithms / logic worth borrowing

Honestly, very little.

- The **`MinPipsForSignal` filter** on candle direction (TVA:492-493) is a noise-floor concept. FORGE has `min_body_ratio` (FORGE.mq5:4739-4750) and `min_directional_bars` (FORGE.mq5:4751-4762) which are strictly stronger (ratio-based, multi-bar).
- The **3-TF "all agree" trigger** (TVA:586-594) is what FORGE's H1/H4/M15 cascade already does at FORGE.mq5:5252 (BUY) and FORGE.mq5:5359 (SELL), with strictly stronger inputs (`m5_bull && m15_ok_buy && h1_ok_buy && h4_ok_buy`), each derived from EMA trend strength rather than single-candle color.

### Where this could enhance FORGE

| Enhancement | FORGE integration point | Type | Benefit (specific, non-hyped) |
|---|---|---|---|
| (None of substance) | n/a | n/a | FORGE's MTF logic (EMA trend strength + ADX + DI+/DI− + MACD across M5/M15/M30/H1/H4 — see `WriteMTFBlock` at FORGE.mq5:817) is strictly more sophisticated than this article's "are 3 candles the same color". The visual overlay is operator-side tooling, not signal logic. |

### Risks / costs

- Re-implementing the chart overlay would add **per-tick `ObjectCreate`/`ObjectMove` calls** (TVA:259-263) — meaningful cost in tester. Not worth doing.
- The `OnTimer` pattern (TVA:654-670) firing `ClearMTFObjects` + `DrawHTF` × 2 every `RefreshSeconds=1` is brute-force redraw. Bad pattern to copy.

**Net verdict on Source 3**: Not useful for FORGE's algorithm. The article is essentially a **screen visualization tool**, not a quantitative MTF synthesis. If the user wants the operator-side visualization (overlaying H1/M30 candles on the M5 chart for human review), they could run this indicator as-is in MT5 — it does not need to be integrated into FORGE.

---

## Cross-Cutting Themes

1. **All three articles agree multi-bar consolidation precedes high-quality breakouts**, but only Source 2 implements it quantitatively (`RangeQualifies` height/ATR + bar count). Source 1's "approach → touch → breakout" state machine implies it; Source 3 ignores it.
   - **FORGE alignment**: FORGE's `entry_quality_adx_spike_sell` gate (FORGE.mq5:5459-5471) captures the inverse — *blocking* breakouts that lack a prior flat base. Source 2's `RangeQualifies` measures the **same precondition** more directly (height ≤ ATR × 2.0 over 8 bars vs. "ADX was ≥ X six bars ago"). This is the strongest cross-source signal: **measure consolidation height/ATR, not just ADX history**.

2. **Candlestick reversal patterns appear in both Source 1 (full detector) and implicitly in Source 2 (geometry votes capture the same "directional impulse" concept).** FORGE has a partial detector (`ScalperCandlePatternScore` FORGE.mq5:3515-3547) used only for bounces. Extending it to act as a **breakout-rejection veto** is consistent with both articles.

3. **Source 2's "leg-end near boundary" check (GA:808-824) and Source 1's "touch on level" (SR:414-430) both encode the same idea**: a breakout starting from mid-range is suspect; a breakout starting at the boundary is structural. FORGE's `prev_close > bb_upper + buffer` is a 1-bar test — it doesn't verify the last swing finished at the upper band. **MAY be worth adding an "M5 high within N bars was near BB upper" check** as a structural breakout-quality boost.

4. **None of the articles handle fast reversals well**. Source 1's "reversal" event fires *after* the touch-reversal completes (one bar lag). Source 2 has no reversal detection — once locked, only a TIMEOUT or breakout exits. Source 3 doesn't process reversals at all. So if **fast-reversal detection is the goal, the articles do not directly help**; FORGE's existing HID_BULL divergence + M15 ADX crash bypass + ADX spike gate remain the best defenses. The candlestick-rejection-pattern addition (Source 1 port) is the only incremental gain on this front.

5. **All 3 articles are "indicator/visual" style, not full EAs with risk management.** None of them ships entry sizing, SL/TP logic, or leg ladders. FORGE's strength is at exactly that layer (`ManageStagedNativeLegs` FORGE.mq5:1206, `ExecuteOpenGroup` FORGE.mq5:1060, fast-lock trailing). The articles donate *gate/signal* logic, not *execution* logic.

---

## Recommended Adoption Plan

Prioritized list. Each entry: target version, effort (S/M/L = small/medium/large), prerequisite, verification.

1. **[v2.7.16] Extend `ScalperCandlePatternScore` with Morning/Evening Star + Piercing/Dark Cloud** (Source 1 port).
   - Effort: **S** (~30 lines of code, all OHLC-only, no new handles).
   - Prerequisite: confirm current pattern list in `ScalperCandlePatternScore` at FORGE.mq5:3515-3547.
   - Verification: re-run Run 11/12 corpus; count `bounce_rejection_candle_*` SKIPs broken down by new pattern.
   - Confidence: **High** — pure extension of existing logic, no behavior change unless new patterns are explicitly enabled.

2. **[v2.7.17] Add bearish-reversal candlestick veto for SELL BB_BREAKOUT** (Source 1 logic, FORGE integration).
   - Gate name: `entry_quality_bear_rejection_pattern` — when prev_close < m5_bb_l (breakdown bar), look at bar[1] high+close+open: if it's a Hammer / Bullish Engulfing / Morning Star → block SELL.
   - Symmetric for BUY: a Shooting Star / Dark Cloud / Evening Star at the upper-band breakout → block BUY.
   - Insertion point: after FORGE.mq5:5505 (after HID_BULL gate) for SELL; after FORGE.mq5:5298 for BUY (before H4 RSI gate).
   - Effort: **M** — must follow the per-M5-bar throttle pattern (new `g_scalper_last_rejpat_*_log_bar` globals at FORGE.mq5:125-162 level), default-off config flag.
   - Verification: replay Run 11 G5008 (May 4 17:10), G5007 — confirm new gate fires when expected; confirm no regressions on profitable Apr 30 entries.
   - Confidence: **Medium** — depends on whether the actual G5008 bar geometrically matches a reversal pattern (would need to look at the raw OHLC; current data only shows RSI/ADX/BB values).

3. **[v2.7.18] Add `RangeQualifies`-style flat-base detector as a complement (not replacement) to `entry_quality_adx_spike_sell`** (Source 2 port).
   - New helper: `IsBreakoutFromFlatBase(direction, lookback_bars, atr_height_cap)` — return true if `max(highs[1..N]) - min(lows[1..N]) <= atr_now × cap` AND `N >= min_bars`.
   - Insertion: parallel to FORGE.mq5:5459-5471. New SKIP reason `entry_quality_flat_base_spike_sell`. Mirror gate for BUY.
   - Defaults: `lookback_bars=8`, `atr_height_cap=2.0` (matches GA), but **default-off** until backtested — this is a real range-check that may block legitimate Apr-30-style crash breakouts.
   - Effort: **M** — straightforward, uses `iHighest`/`iLowest`.
   - Verification: replay full Run 11/12 corpus. Per-event check: does the gate fire on G5008 (expected yes) but allow Apr 30 entries (expected yes — those had M15 ADX 35.6, M5 ADX 41.3, range not flat)?
   - Confidence: **Medium-High** — quantitatively aligned with FORGE's existing flat-base hypothesis.

4. **[v2.7.19] Fractal-anchored structural SL for breakouts** (Source 2 port, FORGE integration).
   - New helper: `FindFractalStructuralSL(is_buy, entry, atr_sl, point, max_lookback=50)` mirroring `FindStructuralSL` at FORGE.mq5:3801-3819 but consulting Bill Williams fractals (port from GA:527-545) instead of OB zones.
   - Insertion: optional widening at FORGE.mq5:5328 (BUY) and the SELL counterpart ~5630. Must respect `min_sl_atr_mult` floor (the SL widening rule already at FORGE.mq5:5329-5330).
   - Effort: **M** — new helper + integration at 2 sites; must enforce SL-floor invariant.
   - Verification: compute SL distance change on Run 11/12 trade entries; confirm no trade's SL becomes wider than `min_sl_atr_mult × ATR` floor.
   - Confidence: **Medium** — fractal SL helps when OB zones are absent (common in tester); risk is that fractals near entry are sparse on M5, falling back to ATR SL anyway. Net effect may be small.

5. **[v2.7.20+] Geometric asymmetry "votes" as an optional breakout-confirmation gate** (Source 2 port).
   - New gate: `require_breakout_asymmetry_buy/sell` (default off).
   - Effort: **L** — full fractal scan + leg-geometry math + cache per M5 bar + new SKIP reason.
   - Confidence: **Low-Medium** — high latency (5-bar fractal confirm), unclear edge on M5 XAUUSD without backtest. Treat as experimental.

6. **[Out of scope] Source 3 (Timeframe Visual Analyzer)** — already provides less than FORGE's existing MTF cascade. **No adoption recommended.** If the user wants the visualization, run the indicator as a separate chart overlay in MT5 — do not port into FORGE.

---

## Out of Scope

- **Source 1's manually-drawn HLINE state machine** as a whole — FORGE has no human-drawn levels; it computes bands/POC/VWAP algorithmically. Only the candle-pattern detector is portable.
- **Source 1's button-and-alert system** (`SyncSupportBtn` / `ClearAllBtn` at SR:91-96, push notifications at SR:570-572). FORGE is server-side; no chart UI required.
- **Source 2's chart drawing** (rectangles, swing dots, arrows — GA:305-525). FORGE does not need any of this; it logs via `JournalRecordSignal`.
- **Source 2's per-symbol pattern locking** (`LockedPattern[]` with rectangles, GA:85-95) — too heavy as a runtime structure; if we adopt the breakout-asymmetry gate, the much simpler approach is to evaluate the geometry on each candidate entry bar without persistent locks.
- **Source 3 entirely** — the visualizations are useful for a human, not for FORGE.
- **All three articles' "alert.wav" + push notification systems** (SR:562-574, GA:168-194, TVA:540-565). FORGE's notification path is via `Print` + journal; no alert sounds needed.
- **Backtest claims** from the articles. None of the three .mq5 files ships with a backtest report, equity curve, or sample symbol/period statistics. Any FORGE adoption decision must be validated on Run 11/12 corpus (Apr 14–May 7), not on article marketing copy.

---

## Appendix — File:line index for fast verification

**FORGE.mq5 anchors referenced above:**
- `OnTick` → `CheckNativeScalperSetups` (entry path): FORGE.mq5:915-944, FORGE.mq5:4781
- `CheckEntryQuality` (ATR/body/direction/news/BB-expansion gates): FORGE.mq5:4684-4779
- `ScalperCandlePatternScore`: FORGE.mq5:3515-3547
- `DetectRSIDivergence` (HID_BULL / HID_BEAR source): FORGE.mq5:3633-3699
- `FindStructuralSL` (current OB-zone-only structural SL): FORGE.mq5:3801-3819
- `NearLiquidityZone`: FORGE.mq5:3834-3844
- BUY BB_BREAKOUT block: FORGE.mq5:5249-5353
- SELL BB_BREAKOUT block: FORGE.mq5:5358-5630
- `entry_quality_adx_spike_sell` gate: FORGE.mq5:5459-5471
- `entry_quality_hid_bull_div_sell` gate: FORGE.mq5:5494-5504
- Two-tier RSI floor (`entry_quality_rsi_sell_floor` / `_adx_floor`): FORGE.mq5:5437-5455
- Crash-sell bypass (with M15 ADX gate): FORGE.mq5:5418-5431
- BB_BOUNCE block: FORGE.mq5:5167-5221 (uses `FindStructuralSL` for bounce SL)
- Per-M5-bar throttle globals (template for any new gate): FORGE.mq5:125-162

**Source 1 (SupportResistanceMonitor.mq5) anchors:**
- Line state struct: SR:57-80
- Tick loop with 6 events: SR:382-516
- `CheckReversalPatterns` (Hammer/Engulfing/Star/Piercing): SR:580-666

**Source 2 (GA_Breakout_Master.mq5) anchors (UTF-16; use /tmp/GA_Breakout_Master_utf8.mq5 for grep):**
- Fractal primitives `IsFractalHigh`/`IsFractalLow`: GA:527-545
- `GetLast3AlternatingFractals`: GA:569-657
- `RangeQualifies` (ATR-height cap + side-zone test): GA:696-761
- `GeometryAsymmetryInsideRangeOK` (votes): GA:763-861
- `CheckAllBreakouts` (close-beyond-buffer trigger): GA:864-922
- Locked pattern struct: GA:85-95

**Source 3 (Timeframe_Visual_Analyzer.mq5) anchors:**
- `CandleDirection` (single-bar bull/bear): TVA:477-501
- `CheckAndAlert` (3-TF agreement): TVA:570-612
- (No algorithmic content beyond these two functions.)
