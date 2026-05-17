# PEMCG + CVCSM Lessons Learned — Pre-Retirement Knowledge Preservation

**Status**: Knowledge-preservation doc written BEFORE Mode D code rip-out. Captures the trading-domain insights, design rationale, and empirical incidents that PEMCG / UMCG / CVCSM / Layer-3 BB_EXHAUSTION_REVERSAL encoded. These layers are being retired (Mode D — ICT 3-tier becomes sole entry-gating substrate), but the lessons they taught migrate forward to inform ICT atom design + composite calibration + future regime-aware features.

**Operator mandate (2026-05-16)**: *"but we might to learn from them"* — write this BEFORE deleting the code. Per `feedback_decision_log_mandate` — rationale captured before it's lost to git archaeology.

**Cross-reference**: `~/.claude/projects/-Users-olasumbo-signal-system/memory/project_pemcg_retirement_target.md` for the Mode D decision context.

---

## §1 Purpose + scope

This doc preserves what was learned from running PEMCG (v2.7.84-v2.7.128) and CVCSM as the production entry-gating layer for ~5 weeks of live + tester operation. It is the canonical "lessons learned" reference for:

- **ICT atom designers** — when proposing a new atom or weighting, check §3 for the multi-atom-composition wisdom PEMCG embedded
- **ICT composite calibrators** — when picking a Mode B/C threshold, check §4 for the supermajority lesson
- **Regime-aware feature designers** — when proposing a day-type/regime modifier, check §5 for the PEMCG asymmetry incident
- **Cooldown / post-loss-discipline designers** (if/when this need re-emerges) — check §6 for CVCSM's design intent + §7 for why coupling cooldown release to the same substrate as entry gates creates a clash
- **Counter-trade / reversal-capture designers** — check §8 for Layer-3 BB_EXHAUSTION_REVERSAL's what-worked / what-missed pattern

---

## §2 PEMCG architecture — what it was

**PEMCG** = Premium-Exhaustion Move Confluence Gate. A 7-atom weighted-boolean composite that scored "is the NEXT bar likely to reverse against the proposed entry direction?" for both BUY and SELL contexts independently. Operator-coined v2.7.84 on 2026-05-13.

Output: two integer warning counts per M5 close, `g_pemcg_buy_warning_count` and `g_pemcg_sell_warning_count`, each 0-7.

Three layer-consumers fed off the warning counts:
- **Layer 1 — UMCG** (Universal Market Condition Gate): SKIP if `g_pemcg_<dir>_warning_count ≥ 5/7` (supermajority block, v2.7.86)
- **Layer 2 — CVCSM**: SL-only cooldown state machine; release condition reads PEMCG counts dropping below threshold for N bars
- **Layer 3 — BB_EXHAUSTION_REVERSAL**: counter-direction setup; fires opposite-side entry when PEMCG warnings ≥ 4/7 (reversal-trap signal becomes the new trade)
- **Layer 4 — DTC** (Day-Type Classifier, v2.7.105): regime-aware modifier that adjusted PEMCG behavior on bear/bull days

Canonical reference: `docs/FORGE_PEMCG_ARCHITECTURE.md` §2 (atom catalog), §3 (layer consumers), §5 (ASCII workflow).

---

## §3 The 7 PEMCG atoms — what each measured + WHY + lesson

| # | Atom | BUY-trap condition (mirror for SELL) | What it measured | Why operator picked it | Lesson for ICT atom design |
|---|---|---|---|---|---|
| **A1** | RSI extreme | `m5_rsi ≥ 65` (was 70 pre-v2.7.88) / `≤ 35` (was 30) | "Price is in the canonical overbought/oversold zone where retail traders enter and institutions reverse" | Foundational RSI exhaustion zone per Cardwell / Wilder | RSI ALONE is not the differentiator (G5005 won at RSI 73, G5006 lost at RSI 73). RSI is necessary-but-not-sufficient. ICT atom: use as ONE atom in a composite, never as sole gate. |
| **A2** | Weak candle body | `m5_body_pct < 0.5` (direction-agnostic) | "Bar shows indecision — no committed directional move" | Weak body = no momentum behind the move | Direction-agnostic atom that fires on BOTH BUY and SELL composites. ICT atom: most useful atoms are direction-agnostic state-of-bar atoms; direction-specific atoms (A1, A5, A7) need careful mirroring. |
| **A3** | No strong bar | `m5_strong_bar == 0` | "Current bar didn't break the body+range threshold for 'strong'" | Lack of strong bar = no commitment | Boolean atom (no parameter to tune). Distinguishes itself from A2 by using FORGE's pre-computed strong-bar classifier (body × range × ATR ratio). ICT atom lesson: leverage existing atom layer — don't re-derive bar-quality classifiers. |
| **A4** | Range contracting | `m5_range_expanding == 0` | "Volatility is shrinking — the breakout/break is losing energy" | Contracting range pre-reversal pattern | Direction-agnostic. ICT atom lesson: range-expansion is a precondition for valid MSS / displacement moves; absence = warning. |
| **A5** | Close near BB band | `abs(close − bb_upper)/atr < 0.3` for BUY / `abs(bb_lower − close)/atr < 0.3` for SELL | "Touched the band but didn't break it" | Direction-specific exhaustion signal at the band proximity | v2.7.87 fixed a sign bug here — the threshold was originally inverted. Lesson: when introducing direction-specific atoms, write explicit mirror tests and verify both halves. ICT atom: distance-to-band atoms exist (FVG distance, OB distance) — reuse the pattern. |
| **A6** | ATR contracting | `m5_atr_ratio_5bar < 1.0` (direction-agnostic) | "Volatility 5-bar ratio shrinking — trend energy fading" | Volatility cycle: contraction precedes reversal more often than continuation | Direction-agnostic. Pairs with A4 (range contraction) but at a different timescale (5-bar vs current-bar). ICT atom lesson: multi-timescale volatility atoms are valuable; consider M5 + M15 + H1 ATR-ratio confluence. |
| **A7** | MACD divergence | `macd < 0 AND close > prev_close` for BUY-trap (mirror for SELL) | "MACD says down momentum, but price is going up — divergence" | Classic momentum divergence detector | The most "structural" of the 7 — measures price-vs-momentum disagreement. ICT atom lesson: MACD divergence concept maps to ICT's hidden-divergence patterns (RSI/MACD vs structure); the v2.7.118 `g_rsi_div_type` atom is the ICT-native version. |

**Combined lesson**: 7 atoms span 4 dimensions (RSI extreme, candle quality A2/A3, volatility A4/A6, structural A5/A7). The diversity is what made PEMCG more robust than any single atom — a TRUE reversal trap usually triggers 5+ atoms simultaneously; a normal range-bound bar triggers 3-4. ICT composite design should similarly span multiple dimensions, not stack same-dimension atoms.

---

## §4 Supermajority threshold calibration lesson (v2.7.85 → v2.7.86)

**Incident** (Run 4, 2026-05-13): PEMCG threshold was originally `≥ 3/7` (majority-minus-one). In a 5.5h sim, PEMCG_BUY fired **67,510 times** — 55,304 of those at RSI 30-70 (NOT the exhaustion zone the gate was designed to catch).

**Root cause**: 4 of 7 atoms (A2/A3/A4/A6) are direction-agnostic state-of-bar atoms that frequently fire together on ordinary range bars (small body, no strong bar, no range expansion, ATR shrinking). So 3-4/7 was the baseline for "ordinary chop", not "reversal trap".

**Fix (v2.7.86)**: bump threshold to **≥ 5/7 (supermajority — 0.7N)**. The 5/7 threshold required ALL the state-of-bar atoms PLUS at least one direction-specific atom (A1 RSI extreme OR A5 BB-proximity OR A7 MACD divergence), which is the actual signature of a reversal trap.

**Validation**: at 5/7 threshold, the canonical losers G5006 (PEMCG=6/7) and G5015 (PEMCG=5/7) still SKIPped correctly. Range bars at RSI 30-70 stopped triggering blocks.

**Lesson codified in memory `feedback_supermajority_composite_threshold.md`**:
> "For broadly-scoped composite gates (apply to many setups), start at 0.7×N and tighten only if evidence shows losers leaking through. For narrowly-scoped gates (single setup), 0.5×N can be safe. Always check the RSI/ADX distribution of blocks to confirm the gate is firing in the intended zone, not on random range bars."

**Applies to ICT composites**: per `FORGE_SETUP_ICT_MAP.md §B.8.2`, ICT category composites use weighted scoring (0-10) instead of warning-counts. But the same calibration discipline applies: when picking the Mode B / Mode C threshold:
- Mode B warning derate at `score < 5` (0.5N — soft gate)
- Mode C hard block at `score < 7` (0.7N — supermajority equivalent)
- Validate against known winners AND known losers + check the score distribution of blocks across regime types

---

## §5 PEMCG asymmetry + DTC fix lesson (v2.7.105 / Run 36)

**Incident** (2026-05-14, Apr-01 22:00 → Apr-02 23:59 backtest window during a 140-point bear move): PEMCG_SELL fired **63,716 times** while PEMCG_BUY fired **5,494 times** — **12× asymmetry**. Zero SELL setups TAKEN despite the move being direction-correct continuation.

**Root cause**: PEMCG_SELL atoms A1 (RSI ≤ 35) and A5 (close near BB_lower) fire BY DEFINITION in any sustained bear leg. Combined with the state-of-bar atoms (A2/A3/A4/A6) firing opportunistically on small consolidation bars, the warning count exceeds 5/7 on direction-correct continuation entries.

**The gate's design intent** was "catch reversal-trap entries at the bottom of a bounce" — instead it caught "direction-correct continuation entries during a sustained move". PEMCG had no awareness of regime — it only saw bar-state.

**Fix (v2.7.105 — DTC = Day-Type Classifier)**: introduced a regime-aware modifier with the canonical indicator triad:

| Indicator | Bear day | Bull day |
|---|---|---|
| VWAP distance (ATR) | ≤ −1.5 | ≥ +1.5 |
| M15 ADX | ≥ 25 | ≥ 25 |
| H1 DI dominance | DI− − DI+ ≥ 5 | DI+ − DI− ≥ 5 |

**Notably absent**: `h1_trend_strength`. The H1 EMA-based trend strength lagged 1+ hour on fresh reversals; Run 36 data showed h1_trend = +0.42 during the active 140-pt bear. VWAP + M15 ADX + H1 DI is the correct intraday-bias detector — the H1 EMA crossover is a trailing confirmation, not a leading signal.

**Two consequences**:
- DTC modifier: when bear-day confirmed, raise `umcg_sell_block_threshold` from 5 to 7 (allow direction-correct continuation entries past the gate)
- DTC day-bias block: hard block COUNTER-direction entries (block BUY on confirmed bear day, block SELL on confirmed bull day)

**Lesson for ICT 3-tier**: composite gates need REGIME AWARENESS, not just bar-state. The ICT KZ + Silver Bullet windows already encode session-time context. The remaining axis is **day-type bias** — the v2.7.107 5-state DTC (BULL_TREND_ALIGNED / BEAR_TREND_ALIGNED / NEUTRAL / COUNTER_TREND_BULL / COUNTER_TREND_BEAR) is the ICT-canonical version of this. When ICT composite scores are calibrated, the same multi-day pattern that triggered PEMCG asymmetry can affect ICT composites; counter-trend entries deserve a stricter threshold than trend-aligned entries.

**Key insight to migrate forward**: VWAP distance, M15 ADX, and H1 DI dominance are the CANONICAL intraday-bias detector triad. They appear in the existing `g_regime.htf_label` computation; ICT composite weighting should consider them when scoring direction-favorability.

---

## §6 CVCSM design intent — what it was and what it solved

**CVCSM** = Conditional Cooldown State Machine. SL-only cooldown with bidirectional retry.

**Design intent** (operator-validated v2.7.84):

1. **TP firing does NOT trigger cooldown** — TPs are validation, not noise. Only SLs trigger.
2. **Per-direction independent state** — a BUY SL puts BUY-side in cooldown; SELL-side remains OPEN. Two independent state machines.
3. **Retry every M5 close** — not pure time-based. Cooldown releases when conditions (PEMCG warnings drop below threshold) confirm for N consecutive bars.
4. **Safety timeout** — max_cooldown_sec (default 1800s / 30 min) hard release if condition-based release never fires.
5. **Opposite direction NEVER blocked** — losing a BUY doesn't gate a SELL entry.

**Anti-patterns explicitly rejected** (operator's stated design vetos):
- ❌ TP-firing triggers cooldown (would block legitimate continuation entries)
- ❌ Same-direction cooldown blocking opposite-direction entries (wrong asymmetry)
- ❌ Time-only release (must be condition-based; timer is only the safety)
- ❌ Per-setup cooldowns (CVCSM is UNIVERSAL across all setups in a direction)

**The intent that survives Mode D**: "after an SL, the regime that caused the loss may still be active — wait for conditions to confirm the reversal before re-entering". This intent is now handled by the ICT entry-gate alone:
- ICT Mode C composite gate SKIPs entries when score < threshold
- After an SL, if the regime is still adverse, the score stays low → entry is SKIPped → effectively the same outcome as "CVCSM in COOLDOWN"
- If the regime flips back to favorable, the score rises → entry allowed → faster re-engagement than CVCSM's N-bar wait

**Lesson for future cooldown / post-loss-discipline features**:
- If the entry-gate ALREADY blocks bad-regime entries, a SEPARATE post-loss cooldown is largely redundant (per the clash analysis in §7)
- The legitimate use case for a separate post-loss layer is **asymmetric discipline** — higher bar after a loss than during normal entries (e.g., post-loss requires HIGH_CONVICTION, normal entries allow STANDARD). This is NOT what CVCSM did (CVCSM used the same threshold for release as for normal blocking).
- If/when post-loss discipline IS needed later, ship as one of: (a) daily/session DD-cap (bound total loss exposure, not per-event timer), (b) loss-streak guard (N consecutive losses in T minutes → halt all entries until session reset)

---

## §7 PEMCG-CVCSM coupling — the clash analysis

**Discovered 2026-05-16 during Mode D scoping discussion**: when CVCSM and an entry-gate read the SAME substrate (PEMCG warnings, or — in the proposed ICT-substrate version — ICT atoms / composite scores) to make decisions, three clash types are possible:

| Clash type | Entry-gate rule | CVCSM release rule | Net effect | Verdict |
|---|---|---|---|---|
| **Symmetric (redundant)** | SKIP if signal < threshold | release if signal ≥ same threshold | CVCSM releases at the same point entry-gate allows. Pure time-delay. | ❌ avoid — architectural noise |
| **Asymmetric (additive)** | SKIP if signal < N | release if signal ≥ M (where M > N) | Normal entries OK at standard threshold; post-loss requires higher conviction. | ✅ adds distinct value |
| **Inverted (dangerous)** | SKIP if signal < M (high) | release if signal ≥ N (low) | CVCSM "releases" but entry-gate still blocks. CVCSM does nothing useful. | ❌ avoid — overhead with no behavior |

**The pre-Mode-D PEMCG / CVCSM coupling was a form of Symmetric clash** — CVCSM released when PEMCG < 2/7, and the next entry-decision could be PEMCG < 5/7 (UMCG threshold). When CVCSM released at PEMCG = 2/7, UMCG was ALREADY allowing entries at any value < 5/7. So CVCSM's "wait for 2 clean bars" was an N-bar delay layered on top of an already-permissive entry-gate.

**This is what drove the operator's decision to retire CVCSM entirely** (not rebuild it on ICT substrate). Per `project_pemcg_retirement_target.md` — exploring Paths A/B/C (asymmetric, time-stability, atom-curated) was the alternative, but operator chose simplicity: trust the ICT entry-gate, don't layer a redundant cooldown.

**Lesson for ICT 3-tier**: when proposing ANY new layer that reads from atoms / composite scores to make a SKIP decision, perform the clash analysis FIRST:
- "Is my proposed layer's signal-reading rule the SAME as the entry-gate's?" → if yes, layer is redundant; design must be asymmetric to add value
- "Does my proposed layer's threshold UNDERSHOOT the entry-gate's?" → if yes, layer is doing nothing
- Only design layers that are PROVABLY asymmetric or atom-different from the entry-gate

---

## §8 Layer 3 BB_EXHAUSTION_REVERSAL — what it caught + what it missed

**Concept**: when PEMCG warnings ≥ 4/7 (reversal-warning threshold), fire an OPPOSITE-direction entry. The reversal-trap signal becomes the new trade.

**What it caught well**:
- Asia capitulation reversal patterns (RSI ≤ 25 + multiple PEMCG_SELL atoms aligned + BB_lower proximity)
- Knife-catch protection (v2.7.94 added WRB gate: `prev_bar_range/atr < 2.0` — don't catch falling knives where prior bar was wide-range)
- High-conviction tier (PEMCG ≥ 6/7) deployed with 4 legs vs BASE tier 1 leg — sized to conviction

**What it missed**:
- The setup's motivation was "PEMCG over-blocks the entry I want; fire the opposite instead". In trending markets (Run 36's 140-pt bear), this LOGIC IS BACKWARDS — direction-correct continuation entries were over-blocked AND BB_EXHAUSTION fired the opposite, which was the wrong direction.
- The v2.7.92 ADX gate (`max_adx=35`) was a workaround for this — block BB_EXHAUSTION fires during strong trends. But it didn't fix the root cause (PEMCG misreading bear continuation as reversal trap).

**Fate in Mode D**: per App B M9 fold milestone, BB_EXHAUSTION_REVERSAL folds into `LIQUIDITY_SWEEP_REVERSAL` (Cat 3) — replaced by the ICT-canonical sweep + ChoCH + FVG-retrace mechanism. The OPPOSITE-direction-fire intent survives in LIQ_SWEEP_REV: a sweep + ChoCH IS a reversal signal that drives counter-direction entry.

**Lesson**: counter-direction-fire setups are valuable but need REGIME-AWARE triggering. ICT's LIQUIDITY_SWEEP_REVERSAL uses structural primitives (sweep, ChoCH) instead of composite-warning counts; this is more robust because the primitives directly observe market microstructure rather than inferring "reversal-prone" from a 7-atom warning sum.

---

## §9 Historical incidents tied to PEMCG / CVCSM

Each incident below is a load-bearing data point. Future composite designers should know these.

| Incident | Loss / impact | What PEMCG/CVCSM did | Lesson |
|---|---|---|---|
| **G5005 win at RSI 73** (Run 30) | +$X | PEMCG=4/7 (below threshold) → ALLOWED | RSI alone isn't the differentiator. Composite required. |
| **G5005 loss at RSI 73** (Run 32) | -$1,694 | PEMCG=6/7 → would have BLOCKED if threshold was 5/7 (it was 3/7 then) | This is the case that motivated v2.7.86 supermajority bump. |
| **G5006 loss at RSI 73** (Run 35) | -$1,760 | PEMCG=6/7 → BLOCKED post-v2.7.86 | Canonical reference for the supermajority threshold success. |
| **G5015 loss at RSI 59 (NOT overbought)** | -$X | PEMCG=5/7 (bar-quality atoms triggered without RSI) | Bar-quality atoms catch traps even when RSI isn't extreme. ICT atom design should include similar bar-quality coverage. |
| **G5048 against-market loss** | -$1,666 | PEMCG insufficient to catch — was direction-against-trend (counter to confirmed bear daily) | Drove v2.7.105 DTC day-bias block. Day-type awareness > atom-count alone. |
| **Run 4 PEMCG over-fire** (2026-05-13) | 67,510 PEMCG_BUY fires in 5.5h sim, 55,304 at RSI 30-70 | Threshold was 3/7 (majority-minus-one) | Drove v2.7.86 → 5/7 supermajority bump. |
| **Run 36 PEMCG asymmetry** (2026-05-14) | 63,716 PEMCG_SELL vs 5,494 PEMCG_BUY in 140-pt bear, 0 SELL TAKEN | Symmetric thresholds + regime-blind atoms = direction-correct continuation blocked | Drove v2.7.105 DTC. ICT 3-tier inherits the lesson: regime-aware thresholds. |
| **2026-05-14 PEMCG-blocked SELLs** (live) | 730× SELL blocks in confirmed bear day | Same as above — PEMCG had no day-type awareness | Same lesson. |
| **G5021 / G5026 counter-trend losses** (Run 36 2026-05-14) | -$X | DTC v2.7.105 binary intraday triad alone didn't catch | Drove v2.7.107 5-state DTC (added H4 alignment check). ICT 3-tier inherits: HTF (H4) bias is mandatory in the regime detector. |
| **CTrade magic mis-attribution** (v2.7.102 / Run 36 G5011-G5015) | 9 deals mis-tagged at base magic, post-mortem confusion | Not PEMCG/CVCSM directly, but tangled with the analysis | Drove v2.7.104 fix. Tangential but the audit pattern (classify close-deals by magic+comment+timestamp) is reusable. |

---

## §10 What PEMCG / CVCSM did NOT catch

Per `docs/missed_opportunities/INDEX.md` — 9 missed-opportunity windows identified Mar 31 → Apr 8. Some of these were PEMCG OVER-BLOCKS (direction-correct entries blocked) AND some were structural-pattern gaps PEMCG simply didn't address.

Direction-correct entries that PEMCG blocked (would be CAUGHT by ICT 3-tier with proper regime awareness):
- Apr 1 03:00 Asian breakout (MSS_CONTINUATION pattern)
- Apr 1 18:00 LC continuation
- Apr 8 12:00 NY reversal (LIQUIDITY_SWEEP_REVERSAL — case study mirror)
- Apr 6 01:32 Asian cascade (MSS_CONTINUATION)

Structural patterns PEMCG had no concept of (REQUIRES ICT atoms):
- OTE retracement entries (62-79% fib zone)
- Sweep + ChoCH reversal patterns
- Killzone + Silver Bullet timing windows
- HTF (H4) alignment check
- Premium/Discount zone alignment

**The fundamental gap**: PEMCG was a REVERSAL-WARNING composite (looking for traps). ICT 3-tier is a STRUCTURE-CONFIRMATION substrate (looking for valid setups). Different epistemology — PEMCG asked "is this trade bad?", ICT asks "is this trade good?". Both are valid but asymmetric — a system that ONLY asked "is it bad?" missed the structural setups that ICT directly identifies.

---

## §11 What ICT 3-tier inherits + what it must avoid repeating

**Inherits (these patterns survive Mode D)**:

1. **Multi-dimensional composite atoms** (§3 lesson) — ICT category composites are weighted sums of multiple atoms across dimensions (structure, retracement, killzone, HTF). Same multi-dim discipline as PEMCG.
2. **Supermajority threshold for broadly-scoped gates** (§4 lesson) — Mode C hard-block at score < 7 (0.7N) mirrors PEMCG's 5/7 supermajority.
3. **Regime awareness as a separate layer** (§5 lesson) — DTC 5-state classifier (BULL_TREND_ALIGNED / BEAR_TREND_ALIGNED / NEUTRAL / COUNTER_TREND_BULL / COUNTER_TREND_BEAR) is ICT-canonical and stays. Composites should weight differently per state.
4. **Calibration against known winners + known losers** (`feedback_supermajority_composite_threshold`) — ICT composite calibration uses the 9 INDEX windows + G5006 / G5048 as the validation corpus.
5. **Direction-aware atoms with explicit mirroring** (§3 A5 sign-bug lesson) — every BUY ICT atom ships with explicit SELL mirror tests.

**Must avoid repeating**:

1. **Layering a SKIP gate on the same substrate as the entry gate without asymmetry** (§7 clash analysis) — any new ICT layer that proposes to SKIP entries must justify asymmetry vs the entry-gate.
2. **Regime-blind composite that fires on direction-correct continuation** (§5 PEMCG asymmetry) — ICT composites must consume regime context (killzone, H4 trend, DI dominance) at the composite level, not as an after-the-fact modifier.
3. **Counter-direction-fire setups gated by composite-warning counts** (§8 BB_EXHAUSTION lesson) — counter-direction logic should use structural primitives (sweep, ChoCH, FVG-retrace) not warning sums.
4. **Time-only cooldowns disconnected from market state** (§6 CVCSM design intent) — operator's "let conditions decide" mandate. No fixed-timer SKIPs.
5. **Symmetric BUY/SELL thresholds in regimes that are asymmetric** (§5 Run 36 lesson) — Mode B/C thresholds may need direction-specific tuning based on day-type classifier output.

---

## §12 Cross-references

- `docs/FORGE_PEMCG_ARCHITECTURE.md` — canonical PEMCG/UMCG/CVCSM architecture spec (preserved as historical reference post-Mode D)
- `docs/FORGE_PEMCG_ICT_INTEGRATION.md` — Mode A/B/C/D ladder; Mode D is now the shipped target
- `docs/FORGE_ICT_PEMCG_COMBINATIONS.md` — 16-cell matrix (will collapse to ICT-only rows post-Mode D)
- `docs/FORGE_SETUP_ICT_MAP.md §B.8` — ICT 3-tier architecture (the substrate that replaces PEMCG-as-gate)
- `docs/FORGE_SETUP_ICT_MAP.md §B.8.6` — "Legacy composites still apply" — this section gets revised post-Mode D
- `docs/missed_opportunities/INDEX.md` — 9 missed-window corpus for ICT composite validation
- `docs/FORGE_CASE_STUDY_G5006_INFLECTION_POINT.md` — G5006 case study (canonical reference for §3 / §9)
- `docs/FORGE_LIVE_2026-05-14_ANALYSIS.md` — Run 36 PEMCG asymmetry incident (canonical §5 reference)
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_supermajority_composite_threshold.md` — calibration mandate codified
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/project_pemcg_retirement_target.md` — Mode D decision context (this doc's parent)
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_decision_log_mandate.md` — why this doc exists (preserve rationale before code goes)

---

## §13 Changelog

- **2026-05-16** — Initial doc. Written BEFORE Mode D code rip-out per operator mandate *"but we might to learn from them"*. Captures 7-atom design + supermajority calibration + PEMCG asymmetry + CVCSM design intent + clash analysis + Layer-3 BB_EXHAUSTION + 9 historical incidents + 5 inherit / 5 must-avoid principles for ICT 3-tier. Cross-linked to retirement memory (`project_pemcg_retirement_target.md`) and the canonical architecture doc (`FORGE_PEMCG_ARCHITECTURE.md`). Next: Mode D code rip-out ship (v2.7.129) — PEMCG + CVCSM + UMCG + (Layer 3 decision) all removed from `ea/FORGE.mq5`; `pemcg_*` SIGNALS columns preserved in schema for backward compat with old DBs.
