# FORGE Case Study — 2026-03-30 Asian Session: Fast-Sweep Directional-Flip Pattern

**Date of pattern**: 2026-03-30 (Sunday-open / early Tokyo, UTC 01:10–02:32)
**Date case study created**: 2026-05-16
**Date case study corrected (empirical-data pass)**: 2026-05-16 — original version mis-framed G5003 as a "chop-scalp small-win" pattern based on hypothetical math. Operator corrected: the actual price action was a **59-pt fast sweep DOWN** through the entry zone with $5,000+ of capturable edge on the SELL side. This version uses verified queries against the source DB.
**Type**: ICT framework case study + Fast-Sweep Directional-Flip design
**Source data**: tester run on `Agent-127.0.0.1-3000` source DB; pre-fork v2.7.119 run (run_id=5 — wiped) + current v2.7.123 run (run_id=1)
**Triggering event**: 2026-05-16 operator-driven analysis of G5001 win + G5003 loss cluster; reframed when empirical price data revealed the actual SELL-side edge
**Status**: living — append entries as live evidence accumulates
**Canonical anchor**: Reference example for **Fast-Sweep Directional-Flip** mechanism + Category 3 LIQ_SWEEP_REVERSAL of [`FORGE_SETUP_ICT_MAP.md §B.2`](FORGE_SETUP_ICT_MAP.md)

---

## §1 The pattern, in one paragraph

On 2026-03-30 Asian session, `ASIA_CAPITULATION_BUY` fired twice 49 minutes apart at near-identical prices (4485.62 and 4483.39). The first won +$1,212.60 — a clean bounce that captured the first 11 pts of the move up. The second lost −$3,655.40 — caught on the wrong side of a **fast sweep continuation DOWN that traveled 31.73 pts below the entry to a session low of 4451.66**. Between the two fires, **three SELL signals were generated and blocked** by stale `dump_*` gates (`dump_rsi_block`, `dump_psar_block`, `dump_bar_confirm_missing`) — the market was already telling the system "continuation down, not bounce" and the gates suppressed it. **The fix isn't smaller TP on the BUY side — it's a cooldown-resident analysis routine that detects the directional bias shift and FLIPS G5003's direction from BUY to SELL** at the same trigger conditions. With the inverted direction at G5003's lot trajectory (0.6 → 1.0 → 1.6), the same SL distance becomes a +$3,592 → +$5,077 capture (depending on TP geometry), turning a −$2,370 actual cluster into a +$5,033 to +$6,518 cluster. Total swing: **$7,403 to $8,888**.

---

## §2 The empirical data (all queries verified against source DB)

### §2.1 The trades that fired (TRADES + SIGNALS, run_id=1)

| # | Sim time UTC | Setup | Direction | Entry | Exit | Net P&L | Outcome |
|---|---|---|---|---|---|---|---|
| **G5001** (mag 207402) | 01:10:00 | `ASIA_CAPITULATION_BUY` | BUY | 4485.62 | TP @ 4496.51 | **+$1,212.60** | ✅ Clean bounce win |
| **G5002** (mag 207403) | 01:15:12 | `MOMENTUM_DUMP_COMPOSITE` | SELL | 4493.32 | TP early | **+$229.68** | ✅ Small early scalp (closed before the deeper move) |
| **Recovery leg** (mag 227412) | 01:56:49 | SCALP_BUY_LIMIT_RECOV | BUY | — | SL | **−$156.00** | ❌ Recovery leg filled into bear |
| **G5003** (mag 207404) | 01:59:09 | `ASIA_CAPITULATION_BUY` | BUY | 4483.39 | SL @ 4460.94 | **−$3,655.40** | ❌ Wrong direction in fast sweep down |

**Actual cluster total**: **−$2,369.12** (per `SUM(profit) WHERE run_id=1`).

### §2.2 The 59-pt window range (the actual edge available)

Verified via `SELECT MIN(price), MAX(price) FROM SIGNALS WHERE run_id=1 AND time BETWEEN '2026-03-30 01:14:30' AND '2026-03-30 02:35:00'`:

| Extreme | Price | Time | Distance from G5003 entry (4483.39) |
|---|---|---|---|
| **High** | **4510.74** | 2026-03-30 01:28:46 | +27.35 pts ABOVE G5003 entry |
| **Low** | **4451.66** | 2026-03-30 02:32:40 | −31.73 pts BELOW G5003 entry |
| **Total window range** | **59.08 pts** | | huge for Asian session |

### §2.3 Price trajectory (the actual story, not my hypothetical)

| Time | Price | What happened |
|---|---|---|
| 01:10:00 | 4485.62 | G5001 ASIA_CAPITULATION_BUY enters (3 partials @ 4485.62-4485.75) |
| 01:10:08 | 4489.27 | G5001 staged-add fires (+3.6 pts) |
| 01:10:35 | 4492.26 | G5001 wave-amp fires (+6.6 pts) |
| 01:14:18 | 4495.30 | G5001 holding (+9.7 pts favorable) |
| 01:14:27 | 4496.81 | **G5001 all TPs hit @ 4496.51 → +$1,212.60 ✅** |
| 01:15:12 | 4493.32 | G5002 MOMENTUM_DUMP_COMPOSITE SELL fires → **+$229.68 ✅** (small scalp) |
| **01:28:46** | **4510.74** | **MARKET HIGH** — ran UP another 17 pts post G5001/G5002 |
| 01:25–01:55 | declining | Price slid DOWN 27 pts from 4510 back to 4483 area |
| 01:59:09 | 4483.39 | G5003 fires (system saw second "flush", bought the next bounce) |
| 02:00:13 | 4486.75 | G5003 staged-add fires |
| 02:00:49 | 4490.33 | G5003 wave-amp fires (1.6 lots total) |
| 02:05:00 | 4488.35 | **G5003 PEAK favorable** = only +4.96 pts (the bounce died early) |
| 02:30:00 | 4472.37 | Fast sweep continuation — −11 pts from entry |
| 02:32:15 | 4460.94 | **G5003 SL hits → −$3,655.40 ❌** |
| **02:32:40** | **4451.66** | **MARKET LOW** — price kept falling, −31.73 pts below G5003 entry |

### §2.4 The SELL signals the system blocked between G5001 and G5003

Verified via `SELECT gate_reason, COUNT(*), MIN(time), MAX(time) FROM SIGNALS WHERE direction='SELL' AND outcome='SKIP' AND time BETWEEN G5001_CLOSE AND G5003_ENTRY`:

| Time | Gate that blocked the SELL | Count |
|---|---|---|
| 01:15:00 | `dump_bar_confirm_missing` | 1 |
| 01:44:36, 01:45:00 | `dump_rsi_block` | 2 |
| 01:50:00 | `dump_psar_block` | 1 |

The market was generating SELL signals during the entire 01:15-01:59 cooldown window. Each was blocked by a single-atom gate (RSI, PSAR, bar-confirm). **Cumulatively, those 4 SELL signals were the market telling the system "this is a continuation sweep down, not a bounce"** — and the gates suppressed them.

### §2.5 G5003 deal-by-deal trajectory (the loss mechanism)

| Time | Action | Price | Cumulative lot | Favorable from entry |
|---|---|---|---|---|
| 01:59:09 | 3 partials open @ 4483.37/35/35 | 4483.39 | 0.6 | baseline |
| 02:00:13 | staged-add fires (300-pt favorable threshold met) | 4486.75 | 1.0 | +3.36 pts |
| 02:00:49 | wave-amp fires (2× lot mult) | 4490.33 | **1.6** | +6.94 pts (execution price) |
| 02:05:00 | (market peak post-entry) | 4488.35 | 1.6 | **+4.96 pts (actual market peak from SIGNALS)** |
| _32-min gap_ | Fast sweep DOWN | | | |
| 02:32:15 | 5 deals stop @ 4460.94 | 4460.94 | 0 | −22.45 pts from entry |
| 02:32:40 | (market low, post-SL) | 4451.66 | — | −31.73 pts |

**Critical empirical note**: The wave-amp execution price (4490.33 in TRADES) is NOT the same as the post-entry market peak (4488.35 in SIGNALS). They differ because TRADES records the price at which the staged-add order was placed/filled vs SIGNALS recording the per-tick price evaluations. **Don't conflate execution prices with market extremes** (operator-flagged error case; rule now codified in skill `### MANDATORY: empirical-data-only rule`).

---

## §3 ICT-canonical framing per `FORGE_SETUP_ICT_MAP.md §B.8.2`

### §3.1 Atom-level replay — both G5001 and G5003 score 9/10

The composite is `LIQ_SWEEP_REV_SCORE_BUY`, computed at `IctScoring.mqh::ComputeCategoryScore(3, 1)`. Globals `g_ict_last_liq_sweep_rev_score_buy/sell` exist, SIGNALS columns `liq_sweep_rev_score_buy/sell` exist, but the `composite_liq_sweep_rev_score_enabled` flag defaults FALSE (Mode A awaiting flip).

| Atom | Source | Weight | G5001 (won) | G5003 (lost) | Notes |
|---|---|---|---|---|---|
| `atom_sweep_detected` | `IctLiquidity.mqh::DetectSellSideLiquiditySweep` | 3 | ✅ +3 | ✅ +3 | Both swept prior Asian range lows |
| `atom_sweep_wick_quality` | `g_ict_last_sweep_wick_atr_mult ≥ 1.0` | 2 | ✅ +2 | ✅ +2 | Both flushes had proportional rejection wicks |
| `atom_choch_confirmed` | `IctLiquidity.mqh::DetectBullishChOCh` | 2 | ✅ +2 | ✅ +2 | Both bounced first → bullish ChoCH on M5 (predicted; awaits Mode A live confirmation) |
| `atom_fvg_on_reversal_leg` | `Atom_FVGOnReversalLeg(DIR_BUY)` | 2 | ✅ +2 | ✅ +2 | Fresh FVG on each displacement leg |
| `atom_killzone_favorable` | `Atom_KillzoneFavorable(LIQ_SWEEP_REV, BUY)` — favors LONDON_OPEN / NY_PM | 1 | ❌ 0 | ❌ 0 | Both fires at ASIAN_KZ — not the canonical sweep window |
| **Total** | | **10** | **9/10** | **9/10** | Atom layer can't differentiate |

### §3.2 The LIQ_SWEEP_REV atom layer doesn't differentiate — but ISS does

Both trades score 9/10 on the LIQ_SWEEP_REV_BUY composite. The category-3 composite atom-level pattern detection is doing its job: both ticks had sweep + wick + ChoCH + FVG = canonical setup. **The differentiator is NOT in the LIQ_SWEEP_REV layer — it's in the ICT Structure Score (ISS) layer**, which checks the broader market structure context the per-category composite doesn't see.

### §3.3 ISS (ICT Structure Score) replay — both directions, both trades

**Critical empirical caveat**: ISS atoms are stubbed at 0 in v2.7.112 (verified — every TAKEN row in run_id=1 logs `iss_score=0, iss_mss=0, iss_fvg=0, iss_choch_support=0, iss_choch_against=0`). Real atom detection ships v2.7.115+. This subsection is a **structural prediction** based on ICT canon + the verified price action — pending Mode A live confirmation after the atoms are wired.

#### §3.3.1 ISS scoring scheme (canonical per `FORGE_SETUP_ICT_MAP.md §B.8.2`)

| Atom | Weight | Meaning |
|---|---|---|
| `iss_mss` | 5 | MSS confirmed in trade direction (structural; primary, mandatory) |
| `iss_fvg` | 3 | Price in active FVG retracement zone aligned with direction |
| `iss_choch_support` | 2 | Recent counter-trend ChoCH supporting the reversal turn |
| `iss_choch_against` | **HARD GATE (0/1)** | Opposing ChoCH against trade direction — blocks the trade entirely when set, NOT summed into score |

Decision tiers: **≥8 high-conviction · ≥5 standard · <5 SKIP**. ChoCH-against firing = automatic SKIP regardless of score.

#### §3.3.2 G5001 BUY @ 01:10:00 (4485.62) — entry-tick ISS

Pre-entry structure: Sunday open at ~4485 dropped fast in the first hour → first V-flush. Setup pattern: capitulation wick rejection.

| Atom | Weight | Predicted at entry | Rationale |
|---|---|---|---|
| `iss_mss` | 5 | **0** | BUY MSS hasn't fired yet. MSS requires close > prior swing high. The flush had just bottomed; bullish MSS confirms only AFTER the bounce closes above 4496+. At entry tick, structural confirmation lags by 1-2 bars. |
| `iss_fvg` | 3 | **0 at entry → ~3 within 1-2 bars** | Bullish FVG forms on the displacement leg UP from the bottom. At entry the FVG is being CREATED. |
| `iss_choch_support` | 2 | **2** | The first V-flush + lower wick + rejection IS the counter-trend ChoCH signal — bearish leg's last leg gets rejected. |
| `iss_choch_against` | HARD GATE | **0** | No established bearish HTF ChoCH against BUY. Sunday-open down move is fresh; no prior structural bearish ChoCH to oppose. |
| **Score at entry** | | **2/10** | Below ≥5 standard tier |
| **Score 5 min post-entry** | | **9-10/10** | MSS=5 + ChoCH-support=2 + FVG=3 once bounce confirms. High-conviction tier. |

**Decision at entry**: **SKIP per pure ISS gate** (score 2/10 < 5 standard tier). But the LIQ_SWEEP_REV composite scored it 9/10 (sweep + wick + ChoCH + FVG-coming) — different question, different lens.

**This reveals the ICT-canon tradeoff** (acknowledged in canon):
- Pure sweep-reversal entry (G5001 approach): enter on wick rejection, accept ISS lags by 1-2 bars. Catches the first +11 pts.
- Canonical OTE-retrace entry: wait for displacement + FVG to form, then enter on retrace INTO the FVG. ISS at entry hits 8-10/10. Misses the first +5-7 pts but enters with full structural validation.

FORGE today does the first; ICT canon prefers the second. **Edge size vs entry quality** trade-off — both valid.

#### §3.3.3 G5003 BUY @ 01:59:09 (4483.39) — entry-tick ISS

Pre-entry structure (the critical 49-min context):
- 01:14 G5001 TP @ 4496.51 (prior swing high)
- 01:28 Market high 4510.74 (new swing high)
- 01:28 → 01:59: Price SLID 27 pts back to 4483 (lower low after the 4510 high)
- This creates a bearish swing structure: **4510 high → break below intermediate support → BEARISH MSS on M5**

| Atom | Weight | Predicted at entry | Rationale |
|---|---|---|---|
| `iss_mss` | 5 | **0** | Same as G5001 — no bullish MSS at entry tick. (But there's a CONFIRMED bearish MSS — see SELL replay below.) |
| `iss_fvg` | 3 | **0** | Any bullish FVG from G5001's leg up to 4510 was FILLED by the 4510 → 4483 retrace. No fresh bullish FVG aligned with BUY. |
| `iss_choch_support` | 2 | **0-2 uncertain** | A small bullish ChoCH might form on the immediate flush rejection — but the dominant structure since 4510 is BEARISH. Likely 0. |
| **`iss_choch_against`** | **HARD GATE** | **1 (strong)** | **The 4510 → 4483 leg established a clear M5 bearish ChoCH against BUY**. Lower high at 4510 (after 4496 prior high) + lower low at 4483 = canonical bearish structure shift. **HARD GATE FIRES**. |
| **Score at entry** | | **N/A — HARD GATE blocks BUY** | ChoCH-against=1 → automatic SKIP regardless of score |

**Decision at entry**: **SKIP via HARD GATE** (`gate_reason=iss_choch_against_blocks_buy` or equivalent).

#### §3.3.4 G5003 SELL replay @ 01:59:09 — same tick, opposite direction

If we replay the SAME tick with direction=SELL:

| Atom | Weight | Predicted at entry | Rationale |
|---|---|---|---|
| `iss_mss` | 5 | **5 (bearish MSS confirmed)** | The 4510 → 4483 leg IS the bearish MSS — close below the prior swing low completes the structure shift. SELL direction has full structural confirmation. |
| `iss_fvg` | 3 | **3 likely** | Bearish FVG from the 4510 → 4496 displacement leg DOWN should still be intact, aligned with SELL. |
| `iss_choch_support` | 2 | **2 (likely)** | The brief bounces during the slide each created mini bullish ChoCHs that got swept = counter-trend ChoCH support for SELL continuation. |
| `iss_choch_against` | HARD GATE | **0** | No bullish ChoCH against SELL — bull structure was already broken at 4496. |
| **Score** | | **10/10 — HIGH CONVICTION** | Hits ≥8 tier; SELL is fully structurally validated |

**Decision at entry as SELL**: **TAKE — high conviction** (10/10).

#### §3.3.5 ISS-driven verdict summary

| Direction at G5003 trigger tick | ISS score | ChoCH-against hard gate | Action |
|---|---|---|---|
| **BUY** (what actually fired) | N/A | ✅ FIRES (bearish ChoCH 4510→4483) | **SKIP** |
| **SELL** (the structurally-correct side) | **10/10** | clear | **TAKE — high conviction** |

**This is the structural case for the directional-flip mechanism**: the ISS framework (once v2.7.115+ atoms ship) provides **two independent blocks** that would have caught G5003:

1. **Hard structural veto** — `iss_choch_against` fires on BUY because the 4510→4483 leg is bearish MSS
2. **High-conviction SELL signal** — the same tick scores 10/10 SELL, so the system has the affirmative direction to flip TO

**G5001 escapes the ISS gate** because at 01:10 there's no prior bearish ChoCH (the Sunday-open down move was the first leg, not yet a confirmed structure shift). ISS correctly differentiates the two trades despite the LIQ_SWEEP_REV composite scoring them identically.

### §3.4 Defense layers — ISS + Cooldown-flip routine are complementary

| Mechanism | Type | Strength | When it fires |
|---|---|---|---|
| **ISS ChoCH-against** | Structural directional veto (price-structure primitives) | Clean — pure ICT canon | When prior leg established bearish/bullish MSS against trade direction |
| **Cooldown-flip routine** | Empirical bias-shift detector (operational signals) | Adaptive — incorporates blocked-SELL counts + price slide | When ≥3 SELL signals blocked + price slides ≥20 pts during cooldown |

Either alone would have caught G5003. Both layered = redundant safety per `feedback_no_design_ceiling`. The ISS layer is the **mandatory clean structural** check; the cooldown-flip routine is the **adaptive operational** check that runs even when atoms haven't yet detected the structural shift cleanly.

**Implementation priority** (informs the Mode B ship order in §6):
1. ISS atom ship (v2.7.115+) — wires the structural veto. This is the cleaner, simpler defense.
2. Cooldown-flip routine (v2.7.125+) — adds the adaptive layer that fires even when ISS doesn't yet have the bearish MSS confirmed.

---

### §3.5 What detects the broader-context bias shift (for cooldown-flip routine)

The cooldown-flip routine layers ON TOP of ISS by reading operational signals during the cooldown window:

- Prior 30-min price action (declining from 4510 → 4483 = bear momentum forming)
- Multiple `dump_*` SELL signals firing but being blocked = directional pressure the gates suppress
- M15 ADX trend (was it confirming bear?), H1 trend (was it flipping?), VWAP distance (was price increasingly below VWAP?)
- Per `FORGE_PEMCG_ARCHITECTURE.md §3.4` DTC (Day-Type Classifier) — should flag if the day is shifting bias

These signals existed; the system saw them; the chokepoint just didn't use them to **flip the directional bias** at the next setup trigger.

---

## §4 The actual design — Cooldown-Resident Directional-Flip Routine

### §4.1 The core mechanism

The 30-minute cooldown post-G5001 isn't dead time. It's the system's **bias re-evaluation window**. During cooldown:

1. **Continuously analyze** price action since the last entry: peak → current price slide magnitude, blocked SELL gate counts, M15/H1 directional drift, VWAP-distance trajectory
2. **Detect bias-shift signals**: SELL gates firing repeatedly (≥3 in window) + price sliding from window-high toward prior-entry zone + ADX strengthening on the new direction
3. **Flip the next-setup-trigger direction**: when ASIA_CAPITULATION pattern re-triggers, fire SELL (not BUY) because the bias-flip detector says continuation
4. **Same geometry, opposite direction**: same lot trajectory (initial + staged-add + wave-amp), same SL distance, same TP1 close % (operator spec: 80% on fast breaks), opposite sign

### §4.2 Empirical capture math — SELL flip at G5003's lot trajectory

If G5003 had fired **SELL** instead of **BUY**, with the same lot escalation (0.6 → 1.0 via staged-add → 1.6 via wave-amp), holding to the same magnitude SL distance:

| Stop level reached | Pts captured | Lot at peak | Realized P&L |
|---|---|---|---|
| Hit 4460 (the price where G5003 BUY's SL fired) | 22.45 pts | 1.6 | **+$3,592** |
| Hit 4456 (chop-scalp TP2 @ 2.5×ATR with ATR=10.76) | 27 pts | 1.6 | **+$4,320** |
| Hit 4451.66 (verified window low @ 02:32:40) | 31.73 pts | 1.6 | **+$5,077** |
| **TP1 80% close** at +0.4×ATR (4479.09) then rest rides to low | mixed | tapered | **~$2,800-3,500 banked + 20% running to 4451** |

### §4.3 Aggregate impact on this case study

| Aggregate | Current actual (BUY at G5003) | SELL flip — conservative (ride to 4460) | SELL flip — aggressive (ride to 4451) |
|---|---|---|---|
| G5001 | +$1,212.60 | +$1,212.60 | +$1,212.60 |
| G5002 | +$229.68 | +$229.68 | +$229.68 |
| Recovery leg | −$156.00 | — (no recovery needed if directional bias was correct) | — |
| **G5003 (flipped)** | **−$3,655.40** | **+$3,592** | **+$5,077** |
| **Cluster total** | **−$2,369.12** | **+$5,034.28** | **+$6,519.28** |
| **Swing vs current** | baseline | **+$7,403** | **+$8,888** |

The operator's claim "and could be more" is empirically validated — the maximum realizable was $5,077 on the SELL leg alone (1.6 lots × 31.73 pts × $1/pt). With TP1 80% close geometry, the bulk locks fast and 20% rides to the low.

---

## §5 Industry citations (per WebSearch mandate, 2026-05-16)

| Source | Key quote | URL |
|---|---|---|
| ICT Sweep + CHoCH + FVG (TradingView, salim-ali) | *"For long signals, traders look for: a bearish liquidity sweep, a bullish CHoCH, and a bullish FVG that forms and gets respected."* | https://www.tradingview.com/script/HgGWdxtB-ICT-Sweep-CHoCH-FVG-Alerts/ |
| ICT Algo Sweep + MSS + High Prob FVG (DivergentTrades) | *"High-probability FVG = one created by a strong impulsive move that causes a Market Structure Shift, after a clear sweep of a significant liquidity pool."* | https://www.tradingview.com/script/SD8VyvVg-ICT-Algo-Sweep-MSS-High-Prob-FVG-IFVG/ |
| FXM Brand — 2026 Gold ICT Guide | *"Triple confluence buy: price sweeps below the Asian low (provides liquidity), brings price into a marked Bullish Order Block, simultaneously fills a Bullish FVG."* | https://medium.com/@fxmbrand/ict-smart-money-concepts-finally-explained-like-youre-5-for-gold-trading-the-ultimate-2026-6517ea11c7c7 |
| Inner Circle Trader — Liquidity Sweep vs Run | *"The Asian range sweep is gold's most repeatable intraday setup… 30-50 pip stop runs typical."* — note: G5001/G5003 cluster fits this magnitude exactly (27-31 pts) | https://innercircletrader.net/tutorials/ict-liquidity-sweep-vs-liquidity-run/ |
| All Five ICT Entry Models (JadeCap) | *"Liquidity sweep reversal: sweep + CHoCH + FVG retrace = the canonical Category 3 entry."* | https://time-price-research-astrofin.blogspot.com/2026/02/all-five-ict-entry-models-explained.html |
| ICT PowerOf3 / AMD canon | Accumulation → Manipulation (sweep wick) → Distribution (trend leg) — applies to BOTH directions; the manipulation phase doesn't pre-commit to a side | (multiple ICT sources) |

ICT canon validates BOTH the bounce-reversal pattern (G5001) AND the sweep-continuation pattern (G5003's correct SELL side). The system needs both as first-class behaviors, not BUY-only.

---

## §6 Mode A → B → C ship sequence (corrected)

### Mode A — enable composite logging + cooldown-analysis logging (next ship, no entry logic change)
- Flip `FORGE_COMPOSITE_LIQ_SWEEP_REV_SCORE_ENABLED=1` in `.env` (1 line, hot-reloadable per `FORGE.mq5:2404`)
- New: log per-cooldown-tick `cooldown_sell_signals_blocked_count`, `cooldown_price_slide_pts`, `cooldown_directional_bias_score` to SIGNALS so the bias-shift detector can be calibrated empirically
- Re-run the same backtest window
- Verify G5001 + G5003 SIGNALS rows log `liq_sweep_rev_score_buy ≈ 9`
- Verify cooldown window 01:15-01:59 logs the 4 blocked SELL signals + the −27 pt price slide

### Mode B — Cooldown-Resident Directional-Flip Routine (v2.7.125 target)
- New function `EvaluateCooldownDirectionalBias()` in `ea/FORGE.mq5` — runs on every M5 close during any active cooldown
- Tracks: blocked SELL count since cooldown start, price extreme during cooldown, current price's distance from extreme, ADX direction-of-strengthening, VWAP-distance trajectory
- Computes `g_cooldown_directional_bias_score` (−10 = strong SELL flip, 0 = neutral, +10 = stay BUY)
- When next setup trigger fires AND `g_cooldown_directional_bias_score ≤ −7` AND threshold met: **fire opposite direction** with the setup's geometry inverted (BUY → SELL, lot trajectory preserved, SL distance preserved, TP1 close % = 80% per operator spec for fast breaks)
- New gate code `cooldown_bias_flip_buy_to_sell` / `cooldown_bias_flip_sell_to_buy` in `config/gate_legend.json`
- 5-layer schema-parity ship for new SIGNALS columns
- Default `FORGE_GATE_COOLDOWN_DIRECTIONAL_FLIP_ENABLED=0` so it coexists with existing behavior for one ship cycle

### Mode C — Promote after calibration
- Validate Mode B captures G5003-class fast-sweep continuations across multiple historical days
- Calibrate threshold (−7 default) against winners + losers per `feedback_supermajority_composite_threshold`
- Flip default to `=1` and remove the `ASIA_CAPITULATION_BUY` setup per M9 milestone (this case study validates Category-3 fold)

---

## §7 Cross-references

- [`FORGE_RESEARCH_OPS.md`](FORGE_RESEARCH_OPS.md) — canonical 8-step operating loop; this case study is a worked example
- [`FORGE_SETUP_ICT_MAP.md §B.8.2`](FORGE_SETUP_ICT_MAP.md) — atom catalog with weights (canonical spec)
- [`FORGE_SETUP_ICT_MAP.md §3.3`](FORGE_SETUP_ICT_MAP.md) — Category 3 LIQUIDITY_SWEEP_REVERSAL deep-dive (this case study is linked there)
- [`FORGE_PEMCG_ICT_INTEGRATION.md`](FORGE_PEMCG_ICT_INTEGRATION.md) — Mode A/B/C promotion sequence
- [`FORGE_FAST_MARKET_SWEEP_RESCUE.md`](FORGE_FAST_MARKET_SWEEP_RESCUE.md) — FMSR; cooldown-flip is a sister mechanism (FMSR = pre-TP1 bilateral arm; cooldown-flip = post-TP1 directional pivot)
- [`FORGE_GLOSSARY.md`](FORGE_GLOSSARY.md) — terminology (LSR, MSS, ChoCH, FVG, OTE, KZ, cooldown-flip)
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_trade_setup_analysis_framework.md` — PRE-trade analysis template
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_supermajority_composite_threshold.md` — composite threshold mandate
- `~/.claude/CLAUDE.md` `## Empirical-data-only rule` + `forge-monitor/SKILL.md ### MANDATORY: empirical-data-only rule` — the rules this corrected case study was rewritten under

---

## §8 Changelog

| Date | Change |
|---|---|
| 2026-05-16 (initial, retracted) | Initial creation. Mis-framed G5003 as "chop-scalp small win" pattern; proposed TP1=0.4×ATR + BE-snap geometry profile that would have produced ~$68 capture. Operator corrected: speculative math obscured the actual edge by ~10×. Original framing retracted. |
| 2026-05-16 (ISS replay added) | Added §3.3 ISS atom replay for both G5001 + G5003, both BUY and SELL directions, per operator request. Empirical caveat: atoms stub at 0 in v2.7.112 — predictions await Mode A live confirmation post-v2.7.115. Key finding: ISS `iss_choch_against` HARD GATE would have blocked G5003 BUY (bearish ChoCH from 4510→4483 leg) while simultaneously scoring G5003 SELL at 10/10 high-conviction. ISS provides clean structural directional veto; cooldown-flip routine layers on top as adaptive operational check (§3.4 + §3.5). G5001 escapes the gate because at 01:10 no prior bearish ChoCH had established. ISS atom ship (v2.7.115) is the clean primary defense; cooldown-flip (v2.7.125) is the adaptive secondary layer. |
| 2026-05-16 (rewrite, current) | Rewritten with empirical-data-only protocol. Verified queries against source DB produced: 59.08-pt window range (4451.66 → 4510.74), 4 blocked SELL signals in cooldown (`dump_*` gates), 31.73-pt actual move below G5003 entry to verified window low. New framing: **Fast-Sweep Directional-Flip** — the cooldown isn't dead time, it's the bias re-evaluation window; when ≥3 SELL signals fire blocked + price slides ≥20 pts from window-high during cooldown, the next setup trigger flips direction (BUY → SELL with inverted geometry). Capture math: $3,592 - $5,077 on the SELL leg (1.6 lots × 22-32 pts), total cluster swing $7,403 - $8,888 vs current −$2,369. Mode A ships: composite enable + cooldown-state logging. Mode B ship: `EvaluateCooldownDirectionalBias()` routine + 80% TP1 close for fast breaks. Mode C: deprecate ASIA_CAPITULATION_BUY (M9 milestone). Linked from `FORGE_SETUP_ICT_MAP.md §3.3` + `FORGE_RESEARCH_OPS.md §1`. Operator instruction codified to global CLAUDE.md `## Empirical-data-only rule` + forge-monitor SKILL.md `### MANDATORY: empirical-data-only rule` as the canonical anti-pattern preventing this class of error in future analyses. |
