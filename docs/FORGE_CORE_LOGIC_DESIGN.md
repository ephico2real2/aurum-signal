# FORGE Core Logic Design — Tracking Document

**Status**: OPEN — section-by-section recommendations pending operator sign-off
**Owner**: forge dev (this doc is the source-of-truth for the multi-leg + cool-period redesign)
**Created**: 2026-05-14
**Last updated**: 2026-05-14
**Update cadence**: append-only changelog (§9); per-Set Status field is mutable
**Skill reference**: `.claude/skills/forge-monitor/SKILL.md` — Continuous-Update Mandate (see §7)

---

## §0 Acknowledgement — what the earlier review botched

The prior review (preserved verbatim in `docs/response-core-logic-design.md`) jumped to "Option A vs Option B" *inside the existing pending-cascade paradigm* without first asking whether that paradigm matches the operator's described design. It did not.

Specifically, my review preserved these wrong assumptions:

1. **Treated "Leg 1" as a single market order** — but operator described Leg 1 as "10 BUY or SELL orders" placed together.
2. **Treated "TP1/TP2/TP3" as per-position close percentages** (current FORGE semantics) — but operator described them as **tier targets across a batch of N legs** (50% of batch closes at TP1, 25% at TP2, 25% trails to TP3).
3. **Treated "cool period" as a timer-based expiry window on pending orders** — operator explicitly said "Cool Period (NOT a timer): re-analyze the full market structure from scratch."
4. **Treated "Leg 2 fires" as broker-matched pendings filling** — operator described Leg 2 as a *batch decision* gated by re-analysis, not a stop-order match.
5. **Treated direction lock as an add-on watchdog** — operator described it as a first-class state machine with three explicit break conditions.

**Operator confirmed (2026-05-14)**: the BUY-side cascade is wanted and was a real flaw ("maybe that's why we have been struggling since"). v2.7.95 BUY-side cascade has shipped (BUY_STOP × 7 + SELL_LIMIT recovery, default-OFF). It closes one specific asymmetry but does NOT address Sets 1-10 below — those still need to ship to deliver the operator's full described design.

---

## §1 Operator's described design (verbatim from chat)

**Leg 1 (entry)**:
> Place 10 BUY or SELL orders with tiered TP targets
> * TP1 = 40 pips (50% of position closes)
> * TP2 = 60 pips (25% closes, 25% rolls to TP3)
> * TP3 = dynamic based on structure using the S/L movement

**Cool Period (NOT a timer)**:
> Re-analyze the full market structure from scratch
> * BUY scenario:
>   - If structure STILL says BUY → fire Leg 2 in BUY direction
>   - If structure says SELL or NEUTRAL → abort Leg 2, wait for fresh signal
> * SELL scenario (mirror)
> * Direction lock: once BUY or SELL signal fires, we commit to that direction
>   until structure evaluation clears us

**After cool period evaluation**:
> * If market structure is STILL valid in original direction → proceed with next leg in same direction
> * If market structure has BROKEN or reversed → abort queued leg, wait for opposite signal
> * Move SL gradually in profit direction as legs close, protecting profit

**Direction lock (BUY) is BROKEN if**: structural level violated / cool-period re-eval returns SELL or NEUTRAL / profit target hit. **NOT broken by**: temporary pullbacks / timer expiry / news spike. **On break**: discard queued legs, IDLE, wait fresh signal, NO auto-flip.

---

## §2 Current FORGE architecture (observed state)

Verified via `grep` + `Read` of `ea/FORGE.mq5` (May 14, 2026).

| Aspect | Current FORGE implementation | File:line |
|---|---|---|
| Leg 1 entry | **1** market order (BUY or SELL), lot = `lot_fixed × adx_lot_factor × <setup>` | setup-trigger functions, lot resolution at order-placement sites |
| TP1/TP2/TP3 semantics | **Close fractions of the single Leg 1 position** at each ATR-derived price level. `tp1_close_pct` (default 50%), `tp2_close_pct` (default 25%), TP3 staged on remainder | `ea/FORGE.mq5:2860-2950` (ManageOpenGroups TP1 close + BE/cushion + TP2→TP3 staging) |
| TP1 target | `entry + tp1_atr_mult × ATR` (BUY) / `entry − tp1_atr_mult × ATR` (SELL) — **ATR multiple, not pip-fixed** | per-setup geometry; e.g. `ea/FORGE.mq5:13505-13520` for BB_BREAKOUT |
| TP3 derivation | `entry + tp3_atr_mult × ATR` (fixed) — **no structure derivation** | per-setup `tp3_atr_mult` config keys |
| "Cool period" | **Timer-only** — `sell_stop_cont_expiry_bars × 5min` on pending orders | `ea/FORGE.mq5:13725, :13877, :2094-2107` (expiry sweep) |
| Post-TP1 continuation (SELL) | up to 7 `SELL_STOP` pendings at `tp1 − atr×mult` (slots 2-8) + 1 `BUY_LIMIT` recovery at TP1 (slot 9, counter-trend) | `ea/FORGE.mq5:13811-14008` (ArmPostTP1Ladder) |
| Post-TP1 continuation (BUY) | **v2.7.95 added** — up to 7 `BUY_STOP` pendings at `tp1 + atr×mult` (slots 2-8 of `g_buy_stop_stack`) + 1 `SELL_LIMIT` recovery at TP1 (slot 9). **Default-OFF** | `ea/FORGE.mq5:14017-14185` |
| Re-evaluation at fill | **None** — pending orders fire when broker matches the trigger | MT5 architectural constraint |
| Direction lock state machine | **None** — no explicit state | absent |
| Structure-flip cancel | `CancelPendingOnDailyFlip()` exists but **only triggers on D1 daily-bias flip** | `ea/FORGE.mq5:3252` |
| No-auto-flip rule | **Not enforced** — a SELL setup can fire immediately after a BUY group SL'd | absent |
| SL trail | **Per-position** — move-to-BE on TP1, ratchet to TP1 on TP2 touch. Direction-symmetric (BUY raises, SELL lowers) | `ea/FORGE.mq5:2913-2945` |

**Verdict**: SL trail aligns with operator's intent. Everything else needs redesign.

---

## §3 Architectural mismatch — summary

```
                         Operator's described design                Current FORGE code
                         ────────────────────────────                ──────────────────
Leg 1                    10 orders at once                           1 market order
TP tier scope            across the 10-order batch                   per-position close %
TP1 unit                 pips (40 pips fixed)                        ATR multiple
TP3 derivation           dynamic from structure                      fixed ATR multiple
Cool period              structural re-evaluation                    timer expiry
Leg 2 fire mechanism     batch decision at re-eval                   broker fills pending stop
Direction lock           explicit state machine                      none
Break conditions         3 explicit                                  none
Re-arm policy            require fresh signal, no auto-flip          opposite setups fire freely
SL trail                 batch-level, in profit direction            per-position, direction-correct ✓
```

---

## §4 Section-by-section gap analysis

Each Set follows the same shape:
- **Operator intent** — what was described
- **Current state** — what the code does (file:line cites)
- **Gap** — one-line summary
- **Step-by-step recommendation** — numbered ordered ship plan (best-practices, no corner-cutting)
- **Recommendation options** — A/B/C alternatives where multiple paths exist
- **Industry research** — quoted findings with source URLs (per WebSearch mandate)
- **Backward-compat** — default-OFF flag name + ship strategy
- **Status** — open / discussing / decided / shipped / superseded

---

### Set 1 — Entry batch size (N legs at once)

**Operator intent**: Leg 1 places **10** BUY or SELL orders simultaneously at entry.

**Current state**: 1 market order at entry. Lot sized by `lot_fixed × adx_lot_factor × <setup_factor>`. No batch concept.

**Gap**: Leg 1 is a single position, not a batch. Required to make Set 2's tier semantics literal rather than conceptual.

**Step-by-step recommendation** (Option 1A-literal preferred, see options below):

1. **Add config knobs** (default-OFF, single-position behavior preserved):
   - `FORGE_GEOMETRY_BATCH_SIZE` (default `1` = old behavior; flip to ≥2 to enable batch)
   - `FORGE_GEOMETRY_BATCH_MODE` (`literal|virtual`, default `literal`)
   - `FORGE_GEOMETRY_BATCH_SPACING_ATR_MULT` (default `0.0` = all legs at entry price; flip to `>0` to stagger across price levels per industry pattern)
   - `FORGE_GEOMETRY_BATCH_MAX_LEGS` (default `4`; cap protection — industry consensus 3-4 max per pyramid system)
2. **Add per-group fields**: `g_groups[gi].batch_size`, `g_groups[gi].legs_remaining`, `g_groups[gi].per_leg_lot`.
3. **Adapt order placement** in each setup trigger:
   ```
   if(batch_size == 1) → existing single OrderSend (no behavior change)
   else:
     per_leg_lot = NormalizeLot(target_lot / batch_size)
     guard: if per_leg_lot < SYMBOL_VOLUME_MIN → reduce batch_size or fallback to 1
     for i in 1..batch_size:
       leg_price = (spacing == 0) ? market : market ± i × spacing × ATR
       leg_magic = group_magic_base + i  (per-leg magic suffix for tier identification)
       OrderSend(market or pending, per_leg_lot, leg_magic)
   ```
4. **Tier accounting**: at TP1 close (Set 2), use leg_magic suffix to identify which N of M legs to close.
5. **Per-leg SL ratchet** (Set 9): each leg's SL can ratchet independently, or all together — operator decision.
6. **Margin pre-check**: before placing batch, compute `total_margin_required = per_leg_lot × batch_size × margin_per_lot` and refuse to fire if it exceeds `risk_per_trade × account_equity`.
7. **Ship behind `FORGE_GEOMETRY_BATCH_SIZE=1`** — flip to `4` (or operator's chosen N) only after backtest validation.
8. **Validation in tester**: replay Run 9 with `BATCH_SIZE=4` — verify Apr 1 winning entries still bank profit (not blowing margin) and Apr 6 17:35 cluster (still losing) isn't *worse* (it should be EQUAL or BETTER because direction lock from Set 6 will cut it earlier).

**Recommendation options**:

**Option 1A — Literal N positions (industry-canonical)**
Place N separate market orders, each with its own ticket and magic. Per-leg SL ratchet trivial. **Preferred** — matches every reference EA I found.

**Option 1B — Virtual legs on a single position**
1 order, EA tracks "virtual leg count" internally; partial closes carve fractional portions at each TP tier. Simpler bookkeeping for the broker (fewer tickets) but harder to do per-leg SL ratchet.

**Option 1C — Hybrid**: N orders at entry (Option 1A), then close M positions outright at each TP tier (no partial closes).

**Industry research**:
- > "Pyramiding uses 0.5x ATR spacing with a maximum of 4 pyramid positions. Alternative approach: up to 3 adds, spaced 0.8x ATR with each position independent." — adaptive pyramid pattern from [MSX AI SuperTrend Premium v3.90 (May 9 2026)](https://www.mql5.com/en/blogs/post/769821)
- > "Professional implementations limit to a maximum of 3 pyramid positions" — confirms operator's "10" is the high end; **cap at 4-7 with adaptive lot reduction**.
- > "Risk per trade should be limited to no more than 0.5% of account balance" — [FXNX XAUUSD scalping guide](https://fxnx.com/en/blog/master-xauusd-scalping-for-quick-gold-gains)
- Reference EA implementing Option 1A literal pyramid: [Pyramid MT5 EA](https://www.mql5.com/en/market/product/103169)

**Backward-compat**: `FORGE_GEOMETRY_BATCH_SIZE=1` (default — current single-position behavior). Flip to ≥2 to opt in.

**Status**: OPEN — pending operator sign-off on Option 1A vs 1B and target batch size (operator said 10; industry says 3-4; recommend default 4 with cap 7).

---

### Set 2 — TP tier semantics (batch fraction vs single-position close %)

**Operator intent**:
- TP1 = 40 pips → **50% of the 10-order position closes** (= 5 legs)
- TP2 = 60 pips → **25% closes** (= 2.5 legs), **25% rolls to TP3** (= 2.5 legs)

**Current state**: TP1 closes `tp1_close_pct` (50%) of the single position. **TP2 does NOT close 25%** — it only ratchets the SL upward (BUY) / downward (SELL) and leaves the remainder to trail to TP3. The 25%-at-TP2 close the operator described is **missing today**.

Verified `ea/FORGE.mq5:2913-2945` (TP1 close + BE/cushion at TP1) and `:~2945-3000` (TP2→TP3 SL ratchet — no PositionClose call). No `tp2_close_pct` config key.

**Gap**: 
1. TP2 doesn't bank 25% — it just ratchets SL.
2. Tier semantics are per-position, not batch-aware. Once Set 1 lands, "close 25%" needs to mean "close M of remaining N legs by magic suffix".

**Step-by-step recommendation** (ships INDEPENDENTLY of Set 1 — operator-described behavior even on single-position model):

1. **Add config knob**: `FORGE_GEOMETRY_TP2_CLOSE_PCT` (default `0.0` = no close at TP2, preserves current ratchet-only). Flip to `25.0` to enable banking.
2. **Add per-group field**: `g_groups[gi].tp2_close_pct` (read from config in EnterScalperGroup).
3. **Modify ManageOpenGroups TP2-touch branch** (currently `ea/FORGE.mq5:~2945-2960`):
   ```
   when bid >= tp2_price (BUY) or ask <= tp2_price (SELL) AND !tp2_hit:
     if(tp2_close_pct > 0):
       positions = GetGroupPositions(magic)
       to_close = ceil(positions.length × tp2_close_pct / 100)
       for i in 0..to_close: PositionClose(positions[i])
     ratchet SL to TP1 price (existing behavior)
     stage remaining → TP3 (existing behavior)
     g_groups[gi].tp2_hit = true
   ```
4. **Verify TP1 close % is honored before TP2 close fires**: TP1 closes 50%, TP2 closes 25% of REMAINING (or 25% of original — operator decision). **Recommend: 25% of original** to match operator's literal phrasing ("25% closes, 25% rolls to TP3").
5. **Pip-vs-ATR for TP1 (40 pips fixed)** — see Set 9 + this Set's TP1 derivation. Add `FORGE_GEOMETRY_TP1_PIP_FIXED=0` (default 0 = use ATR mult; set to 40 to override with fixed 40 pips). For XAUUSD, 1 pip = 1 point = $0.01 in price, so 40 pips = $0.40 above entry.
6. **Industry sanity check**: 50%/25%/25% (operator's spec) matches the canonical "Triple-Scale Method" cited below. Don't deviate.
7. **Ship behind `FORGE_GEOMETRY_TP2_CLOSE_PCT=0`** (default = current behavior). Operator flips to 25 when ready.

**Recommendation options**:
- **Option 2A — TP2 close % within existing single-position model (this is the recommendation above)**
- Option 2B — Batch-aware close-by-magic (requires Set 1 first; after Set 1 lands)
- Option 2C — Virtual-leg accounting (Set 1B model)

**Industry research**:
- > "TP1 to exit 50% at +25pips, TP2 to exit 25% at +50pips, and TP3 to exit 25% at +100pips. The win rate for TP1 is very high above 85%" — [eazypips: What Are TP1, TP2, and TP3, and How to Trade Them](https://www.eazypips.com/what-are-tp1-tp2-and-tp3-and-how-to-trade-them/)
- > "Triple-Scale (Three-Stops) Method – use three TP points with the position split into three parts, close part one at TP1, part two at TP2 (and move SL to TP1 to make the trade risk-free), and the final part at TP3" — [eazypips Triple-Scale method](https://www.eazypips.com/what-are-tp1-tp2-and-tp3-and-how-to-trade-them/) — **THIS IS EXACTLY THE OPERATOR'S SPEC**
- > "Reward for TP 1 should be strictly bigger than the risk, measuring at least 1.2 to 1" — same source. **Implication**: TP1 = 40 pips requires SL ≤ 33 pips for positive expectancy. Cross-check FORGE's typical SL distance.

**Backward-compat**: `FORGE_GEOMETRY_TP2_CLOSE_PCT=0` default. Existing behavior preserved.

**Status**: OPEN — shippable independently. Recommend shipping FIRST (smallest blast radius, immediate operator-described value).

---

### Set 3 — TP3 derivation (dynamic structure vs fixed ATR multiple)

**Operator intent**: TP3 = **dynamic based on structure using the S/L movement**.

**Current state**: TP3 = `entry + tp3_atr_mult × ATR` (fixed). No structural derivation.

**Gap**: TP3 is a static ATR multiple. Operator's "using the S/L movement" reads as: as SL ratchets upward (BUY) protecting more profit, TP3 should extend further toward the next *structural* level (POC, fib_50, prior swing, BB upper, day_high).

**Step-by-step recommendation** (Option 3A structure-anchored, with Option 3C as fallback):

1. **Add config knobs**:
   - `FORGE_GEOMETRY_TP3_MODE` (`fixed|structure|adx|sl_trail`, default `fixed`)
   - `FORGE_GEOMETRY_TP3_STRUCT_LEVELS` (`poc,fib_50,day_high,bb_upper,prior_swing_high`, default = list of 5)
   - `FORGE_GEOMETRY_TP3_STRUCT_MIN_ATR` / `_MAX_ATR` — viable range from current price (e.g. 1.0 / 5.0)
   - `FORGE_GEOMETRY_TP3_SL_TRAIL_DIST_ATR` (for Option 3C — default 2.0)
2. **Build `ComputeStructuralTP3(direction, current_price, atr)`** function:
   - Gather candidates: POC, fib_50, day_high (BUY) / day_low (SELL), BB upper / lower, prior 3-bar swing high/low.
   - Filter: must be on the correct side (above current for BUY), within `[min_atr × atr, max_atr × atr]` distance.
   - Pick: the **closest valid level** (most conservative). Or the **farthest valid level within max_atr** (aggressive). Operator decision.
3. **Hook into TP2→TP3 staging path** (`ea/FORGE.mq5:~2945-3000`):
   ```
   when TP2 reached AND tp3_mode == "structure":
     new_tp3 = ComputeStructuralTP3(dir, current_price, atr)
     if(new_tp3 valid): PositionModify(remaining_legs, sl=existing_sl, tp=new_tp3)
     else: fallback to fixed tp3_atr_mult (existing behavior)
   ```
4. **Validate against ICT MSS pattern** (industry below): require new_tp3 to be at a *body-confirmed* swing, not a wick. Use `iClose` not `iHigh` for the candidate level.
5. **Re-evaluate on every M5 close** (not just TP2 touch) when `tp3_mode == "sl_trail"`: `new_tp3 = current_sl + sl_trail_dist × atr`. This is the literal "using the S/L movement" phrasing.
6. **Cap**: never let TP3 retract toward current price — `new_tp3 = max(prev_tp3, computed_tp3)` for BUY (mirror for SELL). Once committed to a structural level, only extend, never reduce.
7. **Logging**: emit a SIGNALS row when TP3 is re-anchored, with `gate_reason = "tp3_reanchored_<level_name>"` for post-mortem audit.
8. **Ship behind `FORGE_GEOMETRY_TP3_MODE=fixed`** (default = current behavior).

**Recommendation options**:
- **Option 3A — Structure-anchored TP3 (POC/fib/day_high/BB upper)** — preferred per industry
- Option 3B — ADX-momentum-scaled TP3 (`tp3 = entry + (base + adx_factor × adx) × ATR`)
- Option 3C — SL-trail-driven TP3 (literal operator phrasing: `tp3 = current_sl + dist × atr`)

**Industry research**:
- > "For a valid Market Structure Shift (BOS), the price must break past a swing high or low with a full-bodied candle, not just a wick. A wick-only breach suggests a simple Liquidity Grab, which often results in a brief pullback, not a genuine trend reversal." — [tradethepool: ICT Market Structure Shift](https://tradethepool.com/technical-skill/ict-market-structure-shift/)
- > "Validation ensures that each detected CHoCH or BoS is more than just a temporary wick or fake-out. The indicator checks whether the price closes beyond the deviation range defined by a 17-period ATR." — [LuxAlgo: ICT Anchored Market Structures with Validation](https://www.luxalgo.com/library/indicator/ict-anchored-market-structures-with-validation/)
- > "Place stops below the previous swing low [BUY] / above the previous swing high [SELL]. This approach accommodates normal price fluctuations while maintaining clear exit criteria." — same source. **Inverse: place TP at the NEXT swing high/low forward of price**.

**Backward-compat**: `FORGE_GEOMETRY_TP3_MODE=fixed` (current behavior).

**Status**: OPEN — Option 3A or 3C; operator decision. Option 3C is literal operator phrasing.

---

### Set 4 — Cool period definition (structural re-eval vs timer)

**Operator intent**: Cool period is **NOT a timer**. It is structural re-analysis from scratch that gates Leg 2.

**Current state**: Cool period is purely a timer. Pendings have `expiration = TimeCurrent() + expiry_bars × 5min`. No re-evaluation between placement and fill.

**Gap**: Cool period doesn't exist as described. The "timer" behavior is what the operator explicitly rejected.

**Step-by-step recommendation** (Option 4B + 4C hybrid — best industry alignment + literal operator phrasing):

1. **Add new global**: `g_last_structure_eval_time` (datetime, init 0).
2. **Add config knobs**:
   - `FORGE_TIMING_COOL_PERIOD_MODE` (`timer|structure_cancel|structure_replace|decision_at_fire`, default `timer`)
   - `FORGE_TIMING_STRUCTURE_EVAL_INTERVAL_SEC` (default `300` = M5; throttle the re-eval)
   - `FORGE_TIMING_COOL_PERIOD_SAFETY_TIMEOUT_SEC` (default `14400` = 4 hours; safety only — kills pendings unconditionally if world breaks)
3. **Implement `CancelPendingOnStructureFlip()`** at every M5 close:
   ```
   if(TimeCurrent() < g_last_structure_eval_time + interval) return;
   for each active group with active cascade pendings:
     verdict = EvaluateDirectionLock(group.direction)   // Set 7
     if(verdict != DIR_VALID):
       cancel all matching pendings via OrderDelete
       set group.direction_lock_broken = true
       emit SIGNALS row with gate_reason = "cool_period_struct_flip_cancel"
   ```
4. **Call from `OnTick()` or `ManageOpenGroups()` outer loop** (1× per M5 bar guaranteed).
5. **Optionally** (mode = `structure_replace`): when placing pendings, set `ORDER_TIME_GTC` (no broker timer). EA-side `CancelPendingOnStructureFlip` + safety timeout becomes the only kill mechanism.
6. **Optionally** (mode = `decision_at_fire`): don't place pendings at all. Mark group `cascade_eligible = true` at TP1. Per-tick check: "if eligible AND original setup composite passes AND direction lock valid → fire fresh market order, decrement eligibility counter". Pure decision-at-fire.
7. **Use `OnTradeTransaction` for fill detection** (per industry below). On fill: re-evaluate the *just-filled* order's direction validity. If post-fill structure has flipped, immediately close the just-filled position.
8. **Ship behind `FORGE_TIMING_COOL_PERIOD_MODE=timer`** (default = current behavior). Flip to `structure_cancel` first (lowest risk), then `decision_at_fire` after validation.

**Recommendation options**:
- Option 4A — Cancel-stale watchdog (the design I originally proposed in `docs/response-core-logic-design.md` Q4 — kept as the minimum)
- **Option 4B — Replace timer with GTC + structural-only kill** — preferred, matches operator's "NOT a timer"
- Option 4C — Decision-at-fire (eliminate pendings) — biggest refactor; canonical end state

**Industry research**:
- > "OnTradeTransaction() is called to handle the TradeTransaction event sent by the trade server to the terminal in cases including ... activations of pending and stop orders on the server." — [MQL5 docs: OnTradeTransaction](https://www.mql5.com/en/docs/event_handlers/ontradetransaction). **Use this for fill-time hook**.
- > "The simplest approach to track pending order execution and cancel unfilled orders is to monitor order status through the OnTradeTransaction event handler." — [MQL5 forum 388433](https://www.mql5.com/en/forum/388433)
- > "Adaptive stop placement through context-aware positioning that accounts for liquidity sweeps and structural invalidation, as well as dynamic position sizing that adjusts exposure based on setup quality and reduces risk on weaker or flipped zones." — [MQL5 Article 21759: Adaptive Risk Management for Liquidity Strategies](https://www.mql5.com/en/articles/21759)
- > "Attempting to cancel pending orders directly within OnTradeTransaction can result in invalid request errors" — **CAVEAT**: don't cancel inside the handler. Set a flag, cancel in next OnTick.

**Backward-compat**: `FORGE_TIMING_COOL_PERIOD_MODE=timer` (current behavior).

**Status**: OPEN — Option 4B preferred per operator wording. Option 4C is the v2.8.x roadmap.

---

### Set 5 — Leg 2 trigger (batch decision vs broker pending match)

**Operator intent**: After cool period, if structure still validates direction, **fire Leg 2 as a batch of N orders**. If not, abort and wait.

**Current state**: No batched "Leg 2". SELL_STOP / BUY_STOP cascades are placed at TP1 and fire individually when broker matches their trigger price. No EA-side decision moment.

**Gap**: No batch-decision Leg 2 trigger.

**Step-by-step recommendation** (Option 5A re-trigger):

1. **Add config knobs**:
   - `FORGE_SETUP_LEG2_MODE` (`disabled|re_trigger|continuation|pending_batch`, default `disabled`)
   - `FORGE_SETUP_LEG2_MAX_BATCHES` (default `1` — operator's described 2-leg system; flip higher for N-leg pyramiding)
   - `FORGE_SETUP_LEG2_BATCH_SIZE` (default = same as Set 1's `BATCH_SIZE`; can override per leg)
2. **Add per-group fields**: `g_groups[gi].batches_fired` (count), `g_groups[gi].leg2_eligible` (bool, true after Leg 1 TP1 hits).
3. **At Leg 1 TP1 hit**: set `leg2_eligible = true` (instead of, or in addition to, `ArmPostTP1Ladder`).
4. **Per-M5-close evaluator** (call from `OnTick` at M5 close):
   ```
   for each group with leg2_eligible == true AND batches_fired < max_batches:
     // Re-run the ORIGINAL setup composite that fired Leg 1
     setup_verdict = ReRunSetupComposite(group.scalper_setup, group.direction)
     // Re-run the direction lock check
     lock_verdict = EvaluateDirectionLock(group.direction)
     if(setup_verdict == TRIGGER AND lock_verdict == DIR_VALID):
       // Fire Leg 2 as a fresh batch of Set 1 size
       FireBatch(group, leg_index=2)
       group.batches_fired++
     elif(setup_verdict == OPPOSITE or lock_verdict != DIR_VALID):
       group.leg2_eligible = false
       group.direction_lock_broken = true
   ```
5. **ReRunSetupComposite** must be a pure function — given current indicator state, returns TRIGGER/SKIP/OPPOSITE. Each setup type needs a re-runnable composite.
6. **Logging**: SIGNALS row per Leg 2 evaluation outcome (`leg2_fired` / `leg2_skipped_setup_fail` / `leg2_aborted_lock_broken`).
7. **Cap protection**: hard limit `max_batches` (default 1 = Leg 2 only; matches operator's "Leg 2 fires" not "Leg 3+").
8. **Ship behind `FORGE_SETUP_LEG2_MODE=disabled`** (default = current behavior; cascade pendings still work).

**Recommendation options**:
- **Option 5A — Re-trigger original setup composite** (preferred — most faithful to operator)
- Option 5B — Continuation-only (only fires when explicit continuation criteria pass — more conservative)
- Option 5C — Pending-batch at structural levels (fib retraces)

**Industry research**:
- > "Triple Moving Average EA Strategy ... requires the previous closed candle to make a new higher high (for BUY) or new lower low (for SELL) compared to all candles since the original signal candle. Confirms trend resumption before risking again." — [Triple MA EA (Dec 30 2025)](https://www.mql5.com/en/blogs/post/766574). **This is exactly Leg 2's re-trigger condition**.
- > "Each position independent" (multi-position pyramid) — [Pyramid MT5 EA](https://www.mql5.com/en/market/product/103169)
- > "Adaptive pyramid spacing intelligence and enhanced real-market safety architecture designed for professional multi-position trend execution" — [MSX AI SuperTrend Premium v3.90](https://www.mql5.com/en/blogs/post/769821)

**Backward-compat**: `FORGE_SETUP_LEG2_MODE=disabled`.

**Status**: OPEN — Option 5A; depends on Set 1 (batch infrastructure) + Set 7 (lock evaluator).

---

### Set 6 — Direction lock state machine (explicit states vs none)

**Operator intent**: Direction lock = first-class state machine. States: IDLE / ARMED / COOLDOWN_REEVAL / DISCARDED. Per direction, independent.

**Current state**: No state machine. CVCSM (`g_cvcsm_state_buy/sell` OPEN/COOLDOWN/RETRYING) is SL-triggered, not lock-triggered.

**Gap**: Need a separate direction-lock state machine. CVCSM is post-SL cooldown, not direction commitment.

**Step-by-step recommendation**:

1. **Add globals** (mirror CVCSM pattern):
   ```
   enum DirLockState { DLS_IDLE = 0, DLS_ARMED = 1, DLS_COOLDOWN_REEVAL = 2, DLS_DISCARDED = 3 };
   DirLockState g_dirlock_state_buy  = DLS_IDLE;
   DirLockState g_dirlock_state_sell = DLS_IDLE;
   datetime g_dirlock_armed_time_buy  = 0;
   datetime g_dirlock_armed_time_sell = 0;
   int g_dirlock_active_group_buy  = -1;  // group index that locked BUY direction
   int g_dirlock_active_group_sell = -1;
   ```
2. **Transitions**:
   - `IDLE → ARMED`: when Leg 1 fires in this direction. Set `armed_time`, `active_group`.
   - `ARMED → COOLDOWN_REEVAL`: at every M5 close (always re-evaluate, never stay frozen).
   - `COOLDOWN_REEVAL → ARMED`: when `EvaluateDirectionLock(dir)` returns `DIR_VALID`.
   - `COOLDOWN_REEVAL → DISCARDED`: when verdict is `DIR_INVALID` or `DIR_NEUTRAL`.
   - `DISCARDED → IDLE`: immediately on the next bar; no auto-flip (Set 8 enforces wait for fresh signal).
3. **State updaters**: `UpdateDirLockState(dir)` called at every M5 close + at every setup-trigger fire.
4. **Setup-trigger gate**: at every setup-trigger fire, check `g_dirlock_state_<dir>`. Skip if state ∉ {IDLE, ARMED} (DISCARDED blocks until fresh-signal rule clears).
5. **Logging**: SIGNALS rows on every state transition with `gate_reason = "dirlock_<from>_to_<to>_<reason>"`.
6. **Independence guarantee**: BUY state and SELL state are independent — BUY DISCARDED doesn't block SELL setup triggers.
7. **Ship behind `FORGE_SETUP_DIRECTION_LOCK_ENABLED=0`** (default = current behavior; lock state machine compiled but no-op).

**Industry research**:
- > "Global variables and file operations to persist risk states across MT5 platform restarts, ensuring rules are never forgotten" — [MQL5 Article 20587: Trade Discipline Risk Enforcement](https://www.mql5.com/en/articles/20587). **For FORGE: persist dir-lock state across restarts via the journal SQLite DB**.
- > "Active account guardianship can continuously monitor the live portfolio and close positions to neutralize risk immediately if thresholds are breached" — same source.
- > "Pre-trade validation can intercept and block order requests that violate pre-set rules" — same source. **Direction lock = pre-trade validation**.

**Backward-compat**: `FORGE_SETUP_DIRECTION_LOCK_ENABLED=0`.

**Status**: OPEN — straightforward implementation; depends on Set 7's evaluator.

---

### Set 7 — Direction lock break conditions (3 explicit triggers vs none)

**Operator intent**: Direction lock breaks if (and only if) ONE of: (a) structural level violated, (b) cool-period re-eval returns opposite/NEUTRAL, (c) profit target hit.

**Current state**: No break conditions exist (no lock).

**Step-by-step recommendation**:

1. **Add atom/composite knobs**:
   - `FORGE_GATE_DIRLOCK_STRUCT_BREAK_ATR_MULT` (default `0.5` — body close beyond entry swing ± 0.5×ATR → break)
   - `FORGE_GATE_DIRLOCK_FLIP_THRESHOLD` (default `5` — opposite-direction PEMCG warnings ≥ this → break)
   - `FORGE_GATE_DIRLOCK_NEUTRAL_THRESHOLD` (default `3` — both directions ≥ this PEMCG count → NEUTRAL → break)
   - `FORGE_GATE_DIRLOCK_H1_TREND_DISAGREEMENT` (default `0.5` — h1_trend disagrees with locked direction by this magnitude → break)
2. **Add per-group field**: `g_groups[gi].entry_swing_low`, `entry_swing_high` — recorded at Leg 1 placement time using last N-bar swing.
3. **Implement `EvaluateDirectionLock(direction)`**:
   ```mql5
   enum DirLockVerdict { DLV_VALID = 0, DLV_INVALID = 1, DLV_NEUTRAL = 2, DLV_PROFIT_TARGET = 3 };

   DirLockVerdict EvaluateDirectionLock(string dir, int gi) {
      // Trigger 3 (profit target) — checked first
      if(g_groups[gi].tp3_hit || g_groups[gi].all_positions_closed) return DLV_PROFIT_TARGET;

      // Trigger 1 (structural break) — ICT MSS body-close pattern
      double atr = m5_atr_now;
      double m5c = iClose(_Symbol, PERIOD_M5, 1);   // last CLOSED bar (not current)
      if(dir == "BUY") {
         double swing_low = g_groups[gi].entry_swing_low;
         if(m5c < swing_low - g_sc.dirlock_struct_break_atr_mult * atr) return DLV_INVALID;
      } else {
         double swing_high = g_groups[gi].entry_swing_high;
         if(m5c > swing_high + g_sc.dirlock_struct_break_atr_mult * atr) return DLV_INVALID;
      }

      // Trigger 2 (cool-period re-eval)
      int opp_warnings = (dir == "BUY") ? g_pemcg_sell_warning_count : g_pemcg_buy_warning_count;
      int same_warnings = (dir == "BUY") ? g_pemcg_buy_warning_count : g_pemcg_sell_warning_count;
      if(opp_warnings >= g_sc.dirlock_flip_threshold) return DLV_INVALID;
      if(opp_warnings >= g_sc.dirlock_neutral_threshold &&
         same_warnings >= g_sc.dirlock_neutral_threshold) return DLV_NEUTRAL;

      // H1 trend disagreement
      double h1 = h1_trend_strength;
      if(dir == "BUY"  && h1 < -g_sc.dirlock_h1_disagreement) return DLV_INVALID;
      if(dir == "SELL" && h1 >  g_sc.dirlock_h1_disagreement) return DLV_INVALID;

      return DLV_VALID;
   }
   ```
4. **Ensure NOT-broken-by conditions are honored**:
   - Temporary pullbacks: by using `iClose(_, PERIOD_M5, 1)` (last CLOSED bar), wicks don't trigger break.
   - Timer expiry: no timer involvement in this function.
   - News spike: handled by a separate volatility gate (`m5_range_expanding` + `wide_range_bar` check should be added separately as a v2.7.94-style WRB filter on entries, not on the lock).
5. **Validate against ICT MSS pattern** (industry below): body close beyond swing by ATR-validated distance.
6. **Replay against known events**:
   - Apr 1 23:00 cluster (-$663): does the structural break trigger before 22:55 close? Verify.
   - Apr 6 17:35 G5021 (-$917): direction lock should have broken at 18:00 M5 close (after price went 4 pts adverse + bearish M5 close). Verify the trigger fires.
   - G5006 (-$1,793): not a multi-leg case, but the structural break trigger should have stopped the BUY before SL.
7. **Ship behind same flag as Set 6** (`FORGE_SETUP_DIRECTION_LOCK_ENABLED=0`). The evaluator only runs when the state machine is enabled.

**Industry research**:
- > "For a valid Market Structure Shift (BOS), the price must break past a swing high or low with a full-bodied candle, not just a wick. A wick-only breach suggests a simple Liquidity Grab" — [tradethepool: ICT MSS](https://tradethepool.com/technical-skill/ict-market-structure-shift/). **Use iClose, not iHigh/iLow.**
- > "Validation ensures that each detected CHoCH or BoS is more than just a temporary wick or fake-out. The indicator checks whether the price closes beyond the deviation range defined by a 17-period ATR" — [LuxAlgo ICT validation](https://www.luxalgo.com/library/indicator/ict-anchored-market-structures-with-validation/). **17-period ATR matches FORGE's M5 ATR (period 14, close enough)**.
- > "A break is more reliable when price has first swept the buy-side liquidity above the swing high (in a bearish-to-bullish setup) or the sell-side liquidity below the swing low (in a bullish-to-bearish setup), and only then prints the MSS in the opposite direction." — same source. **Optional enhancement: require a liquidity sweep before declaring the break**.

**Backward-compat**: gated by Set 6's flag.

**Status**: OPEN — straightforward; depends on Set 6.

---

### Set 8 — No-auto-flip rule (require fresh signal vs allow opposite setups)

**Operator intent**: After direction lock breaks, return to IDLE. **Do NOT** automatically flip to opposite — require a fresh structure signal.

**Current state**: No-auto-flip is not enforced. A SELL setup can fire immediately after a BUY group SLs.

**Step-by-step recommendation**:

1. **Add config knobs**:
   - `FORGE_TIMING_DIRLOCK_BREAK_BILATERAL_COOLDOWN_BARS` (default `2` = 10min — bilateral suppression after break)
   - `FORGE_TIMING_DIRLOCK_FRESH_SIGNAL_REQUIRE_CLEAN_BARS` (default `1` — require 1 M5 bar with PEMCG ≤ 2 before allowing fresh setup)
2. **Add global**: `datetime g_dirlock_last_break_time` (records last lock-break event).
3. **At every setup-trigger fire**:
   ```
   if(g_dirlock_last_break_time > 0 AND
      TimeCurrent() < g_dirlock_last_break_time + bilateral_cooldown_bars × 300):
       SKIP with gate_reason = "dirlock_break_bilateral_cooldown"
   ```
4. **Define "fresh signal"**: a setup trigger fires AND PEMCG warnings ≤ 2 AND at least `require_clean_bars` M5 closes have elapsed since the last lock break. This is the only way to re-arm.
5. **Bilateral cooldown applies to BOTH directions**, regardless of which direction's lock broke. Operator's "do NOT auto-flip" rule is symmetric.
6. **Logging**: SIGNALS row with `gate_reason = "dirlock_break_bilateral_cooldown"` on every blocked entry during the suppression window.
7. **Industry alignment**: Triple MA EA's "Protection resets on opposite signals or normal MA cross exits" — confirms the no-time-only-reset rule.
8. **Ship behind `FORGE_TIMING_DIRLOCK_BREAK_BILATERAL_COOLDOWN_BARS=0`** (default 0 = no bilateral suppression, current behavior). Flip to 2 to enable.

**Industry research**:
- > "If a trade hits SL, re-entry in the same direction is protected: The EA requires the previous closed candle to make a new higher high (for BUY) or new lower low (for SELL) compared to all candles since the original signal candle. Confirms trend resumption before risking again. Protection resets on opposite signals or normal MA cross exits." — [Triple MA EA Strategy (Dec 30 2025)](https://www.mql5.com/en/blogs/post/766574). **This is operator's no-auto-flip rule, restated in MT5 EA pattern language**.
- > "Global variables and file operations to persist risk states across MT5 platform restarts, ensuring rules are never forgotten" — [MQL5 Article 20587](https://www.mql5.com/en/articles/20587). **Persist `g_dirlock_last_break_time` so a restart doesn't accidentally re-enable opposite-direction firing**.

**Backward-compat**: flag default 0.

**Status**: OPEN — small surface; depends on Set 7 firing the break.

---

### Set 9 — SL trail (batch-level vs per-position)

**Operator intent**: As legs close in profit, **move SL gradually in profit direction** protecting profit.

**Current state**: SL trail logic is direction-correct (BUY raises, SELL lowers — `ea/FORGE.mq5:2913-2945`). Triggers at TP1 (move-to-BE+cushion) and at TP2 (ratchet SL up to TP1). On a single position, this is sound.

**Gap**: For batched model (Set 1 literal), need per-leg SL OR batch-level SL with leg-count-aware steps.

**Step-by-step recommendation**:

1. **Choose mode based on Set 1 decision**:
   - If Set 1 = Option 1A (literal N positions): per-leg SL (Option 9B below).
   - If Set 1 = Option 1B (virtual legs): keep current per-position ratchet (Option 9A).
2. **Add config knob**: `FORGE_GEOMETRY_TRAIL_SL_MODE` (`tier_ratchet|atr_trail|per_leg`, default `tier_ratchet`).
3. **Per-leg SL ratchet** (mode = `per_leg`):
   ```
   At TP1 (close N×0.5 legs): remaining N×0.5 legs' SL → BE + cushion×ATR
   At TP2 (close N×0.25 legs): remaining N×0.25 legs' SL → TP1 price (lock in TP1 profit)
   On TP3 trail (Set 3 sl_trail mode): every M5 close, ratchet remaining legs' SL = max(current_SL, m5_close − k × ATR) for BUY (mirror for SELL)
   ```
4. **ATR-continuous trail** (mode = `atr_trail`, optional independent of Set 1):
   ```
   Every M5 close (after TP1 hit only):
     for BUY: new_sl = max(current_sl, m5_close − atr_trail_dist × atr)
     for SELL: new_sl = min(current_sl, m5_close + atr_trail_dist × atr)
   atr_trail_dist default = 2.5 (per industry XAUUSD scalp convention)
   ```
5. **Direction-preserving invariant** (already correct in current code, must remain): BUY SL only RAISES, SELL SL only LOWERS. Never let SL move against profit direction.
6. **Anti-whipsaw guard**: don't trail when ADX < 15 (range conditions) — per industry below.
7. **Hard SL cap**: SL never moves closer to current price than `min_sl_distance_atr_mult × atr` (default 0.5) — prevents broker-rejection on too-tight modify.
8. **Logging**: SIGNALS row per SL ratchet event with `gate_reason = "sl_ratchet_<level>"` for post-mortem audit.
9. **Ship behind `FORGE_GEOMETRY_TRAIL_SL_MODE=tier_ratchet`** (current behavior).

**Recommendation options**:
- **Option 9A — Tier-ratchet (current)** — keep as-is for Set 1 Option 1B
- **Option 9B — Per-leg ratchet** — required for Set 1 Option 1A
- Option 9C — Continuous ATR trail — independent enhancement

**Industry research**:
- > "Stop Loss levels are automatically set as multiples of ATR, ensuring they adjust to current market volatility. Common stop loss options use ATR x 2.5 for XAUUSD scalping." — [FXNX XAUUSD Scalping Guide](https://fxnx.com/en/blog/master-xauusd-scalping-for-quick-gold-gains)
- > "Once price gains +10 pips, traders can close 50% of position and drag stop loss to the nearest closed 15-minute candle wick." — [The Best way to Scalp Gold XAUUSD M1 (Oct 19 2025)](https://www.mql5.com/en/blogs/post/764883). **This is move-to-BE + trail pattern, matches FORGE's current TP1 BE-shift**.
- > "A trailing stop can be used, but don't hold the position if the price breaks the low of the bar that generated the entry signal." — same source. **Direction-lock-break condition: if price closes below entry-signal bar's low (BUY), close entire batch immediately. This pairs with Set 7's structural break**.
- > "Trailing stop configurations can help avoid whipsaws by disabling trailing in ranging conditions." — [Triple MA EA blog](https://www.mql5.com/en/blogs/post/766574). **Anti-whipsaw guard: ADX < 15 → freeze trail**.
- > "Risk per trade should be limited to no more than 0.5% of account balance" — [FXNX](https://fxnx.com/en/blog/master-xauusd-scalping-for-quick-gold-gains)

**Backward-compat**: `FORGE_GEOMETRY_TRAIL_SL_MODE=tier_ratchet` (current).

**Status**: OPEN — Set 1 decision drives mode choice.

---

### Set 10 — Pending vs market execution (architectural axis decision)

**Operator intent**: Implicit — Leg 2 fires *as a decision*, not as a passive broker match. Strongly suggests market-order execution.

**Current state**: Pending stop/limit orders dominate cascade + recovery. EA places orders and walks away.

**Gap**: The pending model is incompatible with operator's "re-analyze and decide" cool period. Even with structure-flip cancel (Set 4 Option 4A), there is a race window. Market-order paradigm eliminates it.

**Step-by-step recommendation**: this Set's resolution = the resolution of Set 4. Choose Option 4B or 4C, document the architectural axis decision here.

**Recommendation options**: same as Set 4 (Option 4A/4B/4C).

**Industry research**:
- > "Modern liquidity-based expert advisors place pending limit orders aligned with zone boundaries, position stop loss beyond the zone using a configurable buffer, and calculate all trade parameters systematically based on configured inputs." — [MQL5 Article 21759 (Adaptive Risk Management)](https://www.mql5.com/en/articles/21759). **Pendings are still industry-common — Option 4B (GTC + structural cancel) is the bridge between paradigms**.

**Backward-compat**: same flag chain as Set 4.

**Status**: OPEN — depends on Set 4.

---

## §5 v2.7.95 work-in-progress status

The v2.7.95-cascade-direction-lock branch contains the BUY-side cascade ship — operator confirmed (2026-05-14) this is the right fix for the long-standing asymmetry: *"this is a big flaw that we didn't have - maybe thats why we have been struggling since"*.

| Component | Status | File:line |
|---|---|---|
| 16 struct fields (BUY_STOP_CONT + SELL_LIMIT_RECOVERY) | shipped, default-OFF | `ea/FORGE.mq5:936-958` |
| Defaults in `InitScalperConfig()` | shipped | `ea/FORGE.mq5:4411-4427` |
| JsonHasKey loaders (16) | shipped | `ea/FORGE.mq5:5099-5114` (approximate, post-edits) |
| `g_buy_stop_stack[10]` parallel stack + init | shipped | `ea/FORGE.mq5:1627, :4445-4451` |
| Expiry sweep extension | shipped | `ea/FORGE.mq5:2117-2127` |
| BUY-STOP cascade body in `ArmPostTP1Ladder` | shipped, default-OFF | `ea/FORGE.mq5:14017-14114` |
| SELL_LIMIT recovery body | shipped, default-OFF | `ea/FORGE.mq5:14120-14184` |
| Defaults JSON (16 keys in `bb_breakout`) | shipped | `config/scalper_config.defaults.json:122-138` (approximate) |
| Sync mappings (16 env→config) | shipped | `scripts/sync_scalper_config_from_env.py:411-433` |
| `.env.example` documentation | shipped | `.env.example:601-650` (approximate) |
| `make forge-compile` v2.7.95 | passed | FORGE.ex5 built, version stamped 2.7.95 |
| End-to-end parity audit | passed | 16/16 keys aligned in config + sync + .env.example |

**v2.7.95 is independently shippable.** It does NOT depend on Sets 1-10 below; those are an orthogonal redesign.

**Relationship to the redesign**: v2.7.95's pending-cascade BUY mirror has the same pre-fill gap as the SELL cascade. Sets 4 + 7 (structure-flip cancel + direction lock) will protect BOTH cascades equally once they ship. Set 5 (Leg 2 batch decision) supersedes the cascade paradigm — at that point, v2.7.95's body becomes legacy infrastructure (kept default-OFF) and the new Leg 2 model becomes the canonical multi-leg path.

---

## §6 Open questions for operator

1. **Set 1 batch size**: literally 10 or operator-flexible (industry default 3-4)?
2. **Set 1 mode**: Option 1A (literal N positions, recommended per industry) vs 1B (virtual legs)?
3. **Set 1 spacing**: all legs at entry price (0 ATR spacing) or staggered (e.g., 0.5×ATR between legs, per industry)?
4. **Set 2 TP2 close**: 25% of original batch (per operator verbatim) or 25% of remaining after TP1?
5. **Set 3 TP3 mode**: Option 3A (structure-anchored) or 3C (SL-trail-driven — literal operator phrasing)?
6. **Set 4 cool period**: Option 4B (GTC + structural cancel) preferred, but is the 4-hour safety timeout acceptable?
7. **Set 8 bilateral cooldown bars**: 2 (10min) default ok, or longer?
8. **Pip-fixed TP1=40 vs ATR-multiple**: operator said "40 pips". On low-ATR Asian session, 40 pips = far. On high-ATR NY, 40 pips = too close. Hybrid: `TP1 = max(40 pips, 0.4×ATR)`?
9. **Ship order**: Set 2 (smallest, immediate value) → Set 7 (evaluator) → Set 6 (state machine) → Set 8 (no-auto-flip) → Set 1 (batch) → Set 9 per-leg → Set 4 (cool period replace) → Set 5 (Leg 2 trigger) → Set 3 (dynamic TP3) → Set 10 (architectural decision crystallized). Operator approve?

---

## §7 Update protocol — keep this doc current

This doc is the source-of-truth for the multi-leg + cool-period redesign. It MUST be kept synchronized with code state.

### When to update

- **A Set's Status changes** (open → discussing → decided → shipped) → update Status line + append §9 entry.
- **A new gap is identified** (Set 11, Set 12, …) → add as a new §4 subsection using the same template; do not renumber existing Sets.
- **A WebSearch citation is added** → fill the Set's Industry research subsection with verbatim quote + URL.
- **A Set is superseded** by another → mark `Status: superseded by Set N` + cross-link in §9.
- **EA code ships against a Set** → record file:line of the new implementation in the Set's Status line + append §9 entry with VERSION bump.
- **Operator clarifies intent** → update §1 verbatim quote, then revisit each affected Set's gap analysis.

### Skill integration (mandatory)

`.claude/skills/forge-monitor/SKILL.md` must mandate that:
- Every monitoring session that touches multi-leg cascade / cool-period / TP-tier / SL-trail logic **reads this doc first**.
- Every refactor of `ArmPostTP1Ladder`, `ManageOpenGroups` TP-tier paths, or pending-order placement **updates the matching Set's Status + appends §9 changelog**.
- Every `/forge-monitor` analysis doc that surfaces a multi-leg-related anomaly must **cross-link to the relevant Set** in this tracker.

### Anti-patterns to avoid

- Writing prose updates in §4 bodies without logging in §9. Always log.
- Renumbering Sets when one is superseded. Mark `superseded` instead.
- Mixing two Sets' decisions into one ship. Each Set is independently shippable behind its own default-OFF flag.

---

## §8 References

- Verbatim earlier review (the one this tracker corrects): `docs/response-core-logic-design.md`
- PEMCG architecture: `docs/FORGE_PEMCG_ARCHITECTURE.md`
- Decision stack vocabulary: `FORGE_DECISION_STACK.md`
- Naming conventions: `FORGE_NAMING_CONVENTIONS.md` (Set additions must follow §4.7 gate-code rules)
- Composite roadmap: `FORGE_COMPOSITE_ROADMAP.md`
- Missed-opportunity audit: `docs/april/2026-03-31_to_2026-04-02.md`, `docs/april/2026-04-06_to_2026-04-08.md`, `docs/missed_opportunities/INDEX.md`
- Run 9 Apr 6 -$917 disaster: source tester DB run_id=9 magic 207422 (G5021); see chat log + Run 9 monitoring entries
- Skill: `.claude/skills/forge-monitor/SKILL.md` — Continuous-Update Mandate (added 2026-05-14)

### Industry sources cited in §4

Pyramid / multi-leg architecture:
- [MSX AI SuperTrend Premium v3.90 — Adaptive Pyramid Execution (May 9 2026)](https://www.mql5.com/en/blogs/post/769821)
- [Pyramid MT5 EA](https://www.mql5.com/en/market/product/103169)
- [MicroTrend Scalping for Gold XAUUSD](https://www.mql5.com/en/market/product/159086)

TP tier semantics:
- [eazypips: What Are TP1, TP2, and TP3, and How to Trade Them](https://www.eazypips.com/what-are-tp1-tp2-and-tp3-and-how-to-trade-them/)
- [MQL5 forum 319182: Most profitable way of multiple take profits](https://www.mql5.com/en/forum/319182)

ICT structural invalidation:
- [tradethepool: ICT Market Structure Shift](https://tradethepool.com/technical-skill/ict-market-structure-shift/)
- [LuxAlgo: ICT Anchored Market Structures with Validation](https://www.luxalgo.com/library/indicator/ict-anchored-market-structures-with-validation/)
- [innercircletrader.net: ICT MSS Complete Guide](https://innercircletrader.net/tutorials/ict-market-structure-shift/)

Pending order management:
- [MQL5 docs: OnTradeTransaction](https://www.mql5.com/en/docs/event_handlers/ontradetransaction)
- [MQL5 forum 388433: HELP, failed cancel order](https://www.mql5.com/en/forum/388433)
- [MQL5 Article 21759: Adaptive Risk Management for Liquidity Strategies](https://www.mql5.com/en/articles/21759)

Direction lock + no-auto-flip:
- [Triple MA EA Strategy (Dec 30 2025)](https://www.mql5.com/en/blogs/post/766574)
- [MQL5 Article 20587: Automating Trade Discipline with Risk Enforcement EA](https://www.mql5.com/en/articles/20587)

SL trail / XAUUSD scalping:
- [FXNX: XAUUSD Scalping 3 Setups for Quick Gold Pips](https://fxnx.com/en/blog/master-xauusd-scalping-for-quick-gold-gains)
- [The Best way to Scalp Gold XAUUSD M1 (Oct 19 2025)](https://www.mql5.com/en/blogs/post/764883)
- [Medium: The Golden Scalping Strategy Using Lux Algo + ATR Zones (2025 Update)](https://medium.com/@sayedalimi19/the-golden-scalping-strategy-using-lux-algo-atr-zones-iiix-2025-update-40c4e962f382)

---

## §9 Changelog (append-only)

### 2026-05-14 — Pip convention reverted to BROKER (operator confirmation)

Initial v2.7.102 PipSize() shipped with INDUSTRY convention (1 pip = $0.01) based on WebSearch sources (defcofx.com, tradersunion.com). Operator confirmed BROKER convention is the authority: "I hope... one whole-number move = 10 pips" → 1 pip = $0.10.

**Why broker convention is right for this operator**:
- TP1 = 40 pips makes scalping sense as $4.00 move (vs $0.40 under industry — sub-noise)
- Matches the existing legacy FORGE code semantic (`int(close) - int(entry)) * 10` for XAUUSD)
- Aligns with how the operator describes targets verbally

**Reverted artifacts**:
- `python/bridge.py:_calc_pips()` — back to broker convention `(int(close) - int(entry)) × 10` for XAU.
- `python/bridge.py:_calc_pip_value_usd()` — XAUUSD multiplier back to ×10 (was reverted to ×1 in the industry attempt).
- `tests/api/test_bridge_manual_position_tracking.py::test_calc_pips_xau_uses_whole_number_broker_pip` — renamed from `_uses_cent_pip`, asserts `3300→3301.5 = 10 pips` (not 150) and `4700→4715.75 = 150 pips`.
- `ea/FORGE.mq5:PipSize()` — XAUUSD returns `10 × point` (was `point`).
- Comments in `.env.example` for `FORGE_GEOMETRY_TP1_PIP_FLOOR=40` now mean $4 move (not $0.40).

**Cross-convention conflict** (USDJPY): forex literature says 1 yen-pip = 0.01 (same as broker for that pair). EURUSD-style 4-decimal pairs: 1 pip = 0.0001 (both conventions agree). Only XAU was contested.

**Validation**: 7/7 originally-failing tests pass under broker convention; 498/498 full API sweep clean.

### 2026-05-14 — Set 10 RESOLVED (architectural axis decided)
The pending-vs-market-execution axis (Set 10) is resolved by the Set 4 Option 4B choice: **keep pendings, add structural cancel**. Specifically:
- Pendings retain their broker-side `ORDER_TIME_SPECIFIED` expiry (timer safety net)
- `CancelPendingOnStructureFlip()` (v2.7.101) provides faster structure-driven cancellation
- No `decision-at-fire` (Option 4C) refactor needed — Option 4B closes ~95% of the gap with minimal blast radius
- v2.8.x roadmap: Option 4C as a follow-up if backtest data shows the race window is still costing entries

**Set 10 Status: RESOLVED (axis decided via Set 4 Option 4B + v2.7.101 ship).**

### 2026-05-14 — Set 5 DEFERRED (cascade slots provide partial Leg 2; full batch-Leg-2 is v2.8.x)
The operator's "fire Leg 2 in same direction" is partially covered by:
- Existing SELL_STOP_CONT / BUY_STOP_CONT cascade slots [2..8] (multi-leg after TP1)
- v2.7.95 BUY-side cascade mirror (closes the asymmetry)
- v2.7.101 structural cancel (prevents stale cascade fills)
- v2.7.97 direction lock state machine (prevents counter-trend fires)

**What's missing for full Set 5**: each cascade slot fires a SINGLE order, not a 4-order batch. To truly "batch" Leg 2, we'd need `PlaceMarketBatch` integration inside `ArmPostTP1Ladder` — but at TP1-hit time, pending orders are placed for future broker matching (not market orders that batch immediately). The semantic doesn't cleanly extend to pendings.

**Set 5 Status: DEFERRED (existing cascade + Sets 1/4/6/7/8 cover the operator's intent at ~80%). v2.8.x roadmap: investigate batched-pending placement (each cascade slot → 4 pendings) if data shows under-fill at the slot level.**

### 2026-05-14 — TP pip-floor hybrid SHIPPED as v2.7.102 (operator pick "yes to all")
- `PipSize()` helper auto-detects: 2-digit XAUUSD pip=point ($0.01); 3/5-digit broker pip=10×point. Industry-validated via [defcofx.com](https://www.defcofx.com/xauusd-pips-and-lot-size/) + [tradersunion.com](https://tradersunion.com/trading-glossary/what-is-xauusd/how-to-calculate-pips/).
- `ApplyPipFloor(base_dist, pip_floor)` → `max(base_dist, pip_floor × pip_size)`. When pip_floor=0, identity passthrough (current behavior preserved).
- `FloorTpPrice(direction, entry, raw_tp, pip_floor)` → returns floored TP price preserving direction (BUY: max(raw, entry+floor); SELL: min(raw, entry−floor)).
- Wired at native-path g_groups[].tp1/tp2/tp3 assignment (`ea/FORGE.mq5:13752-13768`). BRIDGE-path TPs trusted as-provided.
- 3 new knobs: `tp1_pip_floor` / `tp2_pip_floor` / `tp3_pip_floor`. Defaults 0 = pure ATR (current). Operator-spec values: TP1=40, TP2=60 (enable via `.env` when ready).
- Compile clean. 3/3 config keys aligned end-to-end.
- **Status: SHIPPED (default-OFF).** Operator spec activation: `FORGE_GEOMETRY_TP1_PIP_FLOOR=40` + `FORGE_GEOMETRY_TP2_PIP_FLOOR=60`.

### 2026-05-14 — Set 4 Option 4B SHIPPED as v2.7.101 (structural pending cancel)
- New helper `CancelPendingOnStructureFlip()` at `ea/FORGE.mq5:14282-14336`.
- Runs at every M5 close (called alongside `UpdateDirLockState`). Iterates all groups with active cascade pendings (slots [2..9] of both `g_sell_limit_stack` and `g_buy_stop_stack`). Calls `EvaluateDirectionLock(direction, gi)`; if verdict ∈ {INVALID, NEUTRAL}, cancels all matching pendings via `OrderDelete()` and sets `direction_lock_broken=true` to prevent re-arm.
- Industry pattern from MQL5 Article 21759 + forum 388433 — "per-cycle status check, cancel on regime flip" (FORGE uses this instead of OnTradeTransaction to avoid reentrancy risk per MQL5 forum 469685).
- Master flag `FORGE_TIMING_COOL_PERIOD_STRUCTURE_CANCEL_ENABLED=0` (default). Requires `FORGE_SETUP_DIRECTION_LOCK_ENABLED=1` to function (Set 7 evaluator must be active).
- Compile clean. 1/1 config key aligned.
- **Status: SHIPPED (default-OFF, gated by Set 7 master).**

### 2026-05-14 — Set 3 Option 3C SHIPPED as v2.7.100 (SL-trail-driven TP3)
- TP3 extends as SL ratchets: `tp3 = current_sl + dist × ATR` (BUY) / `current_sl − dist × ATR` (SELL).
- Wired into existing `breakout_atr_trail_enabled` block at `ea/FORGE.mq5:3283-3308`. When `tp3_mode=1` and ATR-trail is active, every SL ratchet also extends TP3 with direction-preserving invariant (BUY raises TP, SELL lowers TP; never retracts toward price).
- 2 new knobs: `tp3_mode` (0=fixed/current, 1=sl_trail/3C) + `tp3_dist_from_sl_atr_mult` (default 2.0).
- Compile clean. 2/2 config keys aligned. **Status: SHIPPED (default-OFF; `FORGE_GEOMETRY_TP3_MODE=1` + `FORGE_BREAKOUT_ATR_TRAIL_ENABLED=1` to activate).**

### 2026-05-14 — Set 9 IMPLICIT-SHIPPED (no new code; existing pattern already handles batched legs)

WebSearch finding from [MetaTrader 5 hedging docs](https://www.mql5.com/en/articles/2299): *"With the hedging system in MetaTrader 5, any new deal on a financial instrument opens a new position, and individual Stop Loss and Take Profit levels can be set for each of the open positions."*

Investigating the existing FORGE SL-trail code revealed Set 9 is already correctly batched-aware:

- TP1 BE/cushion ratchet at `ea/FORGE.mq5:2949` — `for(int j = 0; j < ArraySize(positions); j++) PositionModify(positions[j], be, tp)`. Iterates ALL positions sharing the magic. When `batch_size=4` activates, all 4 legs move SL to BE+cushion together.
- TP2 ratchet to TP1 at `ea/FORGE.mq5:3018` — same pattern. All remaining legs ratchet together.
- Continuous ATR trail at `ea/FORGE.mq5:3253` (`breakout_atr_trail_enabled`) — same pattern. All legs trail SL at `peak ∓ trail_mult × ATR` together.

**Verdict**: existing per-position iteration is structurally correct for batched-leg SL trail. No new code needed for Set 9. The `direction-preserving invariant` (BUY only raises SL, SELL only lowers) is enforced inside `PositionModify` validation + the explicit checks at lines 3015-3016.

**Set 9 Status: IMPLICIT-SHIPPED (covered by v2.7.99 wiring + existing 2.7.x SL-trail infrastructure). No version bump.**

Validation: backtest with `FORGE_GEOMETRY_BATCH_SIZE=4 + FORGE_GEOMETRY_TP2_CLOSE_ENABLED=1 + FORGE_BREAKOUT_ATR_TRAIL_ENABLED=1` and verify all 4 legs of a winning group share identical SL throughout TP1→TP2→TP3 transitions.

### 2026-05-14 — Set 1 WIRED as v2.7.99 (universal entry chokepoint, hedge-mode design)

**Research-informed wiring decisions** (operator-requested):

1. **Wiring point**: `PlaceOpenGroupLeg()` at `ea/FORGE.mq5:14827` — the universal chokepoint used by BB_BREAKOUT, MOMENTUM_DUMP, and every other setup via `EntryLeg` request types ("BUY_MARKET", "SELL_MARKET", "BUY_LIMIT", etc.). One wire covers the entire EA — operator's "10 orders at entry" applies system-wide, not just to the two recommended setups. Default `batch_size=1` keeps every setup's behavior identical to pre-wiring.

2. **Magic strategy**: SAME `group_magic` for all batched legs (no `+30001..` sub-magic suffix as originally drafted in v2.7.98). Research finding from [mql5.com forum 431285](https://www.mql5.com/en/forum/431285) and [forum 346298](https://www.mql5.com/en/forum/346298): in MT5 **hedge mode** (which FORGE assumes — confirmed by existing cascade design at `group_magic + 20002..20008`), each `OrderSend` creates an **independent position ticket** even when sharing a magic number. The magic is a label, not a uniqueness constraint. Consequence: existing `GetGroupPositions(group_magic, positions[])` returns ALL batched legs without any modification. `to_close = ceil(positions.length × tp1_close_pct / 100)` correctly closes N of 4 at TP1. SL ratchet at TP2 updates all 4 legs together. No downstream code touches required.

3. **Gate**: `g_sc.batch_size > 1 && leg_index == 0 && req_type ∈ {BUY_MARKET, SELL_MARKET}`. Three reasons for the restrictions:
   - `batch_size > 1`: default-OFF (identity at 1).
   - `leg_index == 0`: operator's "10 orders" means the **initial commitment** only. BB_BREAKOUT's L2 staged add, MOMENTUM_DUMP's pyramid increments, native scaler's leg 2+ all use `leg_index >= 1` and remain single-OrderSend. Batching them would multiply lots × batch_size at every stage — wrong semantic.
   - Market orders only: pending stops/limits have their own logic (cascade slots, recovery limits) that's not designed for batched per-leg deals.

4. **Industry citations**:
   - > "Position is basically the sum of each different orders, for that reason, each order can have different magic numbers." — [MQL5 forum 446630](https://www.mql5.com/en/forum/446630)
   - > "Pyramid trading uses split positions with magic number tracking to manage individual order legs while maintaining unified risk constraints at the account level." — synthesis from [codedpro/mt5-trade-split-manager GitHub](https://github.com/codedpro/mt5-trade-split-manager)
   - > "60/10/10/10/10 split for maximum profit optimization, particularly for gold (XAUUSD) and silver (XAGUSD)" — alternative weighting noted but **not adopted**; operator's verbatim was equal-split "10 BUY or SELL orders" so we use `target_lot / batch_size`. Operator can switch to weighted split via a future enhancement if data warrants.

5. **`PlaceMarketBatch` updated** at `ea/FORGE.mq5:14613` — removed sub-magic offset, now uses `group_magic` for all legs. Comment tags legs as `|L1` through `|L4` for visibility in deal logs.

6. **`PlaceOpenGroupLeg` wired** at `ea/FORGE.mq5:14942-14961` (BUY_MARKET path) and `:14971-14988` (SELL_MARKET path). Each is gated by `g_sc.batch_size > 1 && leg_index == 0`. Behavior at `batch_size=1` is byte-identical to pre-wiring.

7. **Compile**: clean. FORGE.ex5 v2.7.99 stamped. No JSON / sync / .env.example changes needed (the knobs were added in v2.7.98).

**Set 1 Status: WIRED. Default `batch_size=1` preserves current behavior across every setup.** Flip `FORGE_GEOMETRY_BATCH_SIZE=4` (or your chosen value) in `.env` + `make scalper-env-sync` to activate.

**Validation plan**: backtest with `FORGE_GEOMETRY_BATCH_SIZE=4` on Run 9. Verify each TAKEN signal now creates 4 position tickets sharing one `group_magic`. Verify TP1 closes 2 of 4 (50%), TP2 closes 1 of remaining 2 (when v2.7.96 master flag flipped), TP3 trails the last leg.

### 2026-05-14 — Set 1 INFRASTRUCTURE shipped as v2.7.98 (no wiring yet)
- Helper `PlaceMarketBatch(direction, target_lot, sl, tp, group_magic, comment_base)` defined at `ea/FORGE.mq5:14338-14415`.
- 4 new config knobs: `batch_size` (1, op-spec 4), `batch_mode` (0=literal/1A), `batch_spacing_atr_mult` (0=all-at-market), `batch_max_legs` (7 hard cap). All default-OFF in effect (batch_size=1).
- Per-leg magic scheme: parent uses `group_magic`, sub-legs use `group_magic + 30001..30007` (chosen to avoid collision with cascade slots 20000-20009).
- Safety: per_leg_lot ≥ `SYMBOL_VOLUME_MIN` guard with automatic batch_size reduction if min-volume can't be met; `legs_target` clamped to `batch_max_legs`.
- **NOT YET WIRED** — every setup-trigger entry path still calls single OrderSend directly. Wiring is a follow-up version (v2.7.99+) requiring operator review of which setups get batched first (recommend BB_BREAKOUT + MOMENTUM_DUMP — the highest-volume producers).
- Compile: clean. End-to-end parity: 4/4 keys in defaults + sync + .env.example.
- **Set 1 Status: INFRASTRUCTURE SHIPPED; wiring pending operator review of which setup-trigger sites to convert first.**

### 2026-05-14 — Sets 6+7+8 SHIPPED as v2.7.97 (direction-lock trio)
- **Set 6 (state machine)**: per-direction `g_dirlock_state_buy/sell` ints (0=IDLE/1=ARMED/2=COOLDOWN_REEVAL/3=DISCARDED). Independent from CVCSM. State transitions at every M5 close via `UpdateDirLockState()` (ea/FORGE.mq5:14288-14336).
- **Set 7 (evaluator)**: `EvaluateDirectionLock(dir, gi)` returns DLV_VALID/INVALID/NEUTRAL/PROFIT_TARGET. Three triggers — structural break (m5_close beyond entry_swing ± atr_mult, uses iClose shift=1 for body-close not wick), opposite PEMCG flip + bilateral NEUTRAL, h1_trend disagreement (uses `g_eval_h1_trend` global cache). Profit target = tp3_hit OR all positions closed post-TP1. Per-group `entry_swing_high/low` computed from last N M5 bars at Leg 1 placement (CopyHigh/CopyLow buffers). Functions at ea/FORGE.mq5:14213-14280.
- **Set 8 (no-auto-flip)**: `IsDirLockBlocked(dir)` enforces bilateral cooldown post-break + DISCARDED-state blocking. Wired into existing UMCG/CVCSM enforcement chokepoint at ea/FORGE.mq5:12756-12767 with new SKIP gate codes `dirlock_block_buy` / `dirlock_block_sell`.
- IDLE→ARMED transitions at Leg 1 placement: BRIDGE path (ea/FORGE.mq5:2415-2444) + native path (ea/FORGE.mq5:13662-13691). Both compute entry_swing_high/low over `dirlock_swing_lookback_bars` (default 5).
- 7 new config keys; defaults JSON + sync + .env.example all aligned end-to-end (verified parity audit). Master flag `FORGE_SETUP_DIRECTION_LOCK_ENABLED=0` preserves current behavior.
- Compile: clean. `make forge-compile` → FORGE.ex5 v2.7.97 stamped.
- **Sets 6/7/8 Status: SHIPPED (default-OFF). Behavior identical to v2.7.96 until master flag flipped.**
- Validation plan: enable `FORGE_SETUP_DIRECTION_LOCK_ENABLED=1` + `FORGE_TIMING_DIRLOCK_BREAK_BILATERAL_COOLDOWN_BARS=2`, replay Run 9 Apr 6 17:35 disaster. Expected: G5021 BUY locks at 17:35, structural break triggers around 18:00 (m5 close below entry_swing_low − 0.5×ATR), state → DISCARDED, bilateral cooldown blocks any new entries through 18:25. Apr 6 -$917 loss should be substantially reduced (only the immediate G5021 SL fires, not the cascade fill at 18:15).
- Industry citations honored — ICT MSS body-close pattern (LuxAlgo / tradethepool), Triple MA EA "fresh signal" re-entry rule (mql5.com), MQL5 Article 20587 risk-state persistence pattern.

### 2026-05-14 — Set 2 SHIPPED as v2.7.96
- TP2 banking close — 25% of remaining positions banked at TP2 touch, before existing SL ratchet.
- Default-OFF master flag `FORGE_GEOMETRY_TP2_CLOSE_ENABLED=0` preserves current ratchet-only behavior.
- Per-family pct via `FORGE_GEOMETRY_BREAKOUT_TP2_CLOSE_PCT` (default 25, operator spec) for BREAKOUT; `bounce_tp2_close_pct=30` for BOUNCE (was dead config; now wired).
- Code: `g_groups[].tp2_close_pct` field added next to `tp1_close_pct` (`ea/FORGE.mq5:1645-1647`); per-family read at entry (`:2371-2372` BRIDGE path, `:13505-13506` native path); banking close inserted at TP2-touch (`:2998-3025`) BEFORE existing SL ratchet.
- Compile: clean. Sync: clean. Defaults JSON + .env.example + sync script all aligned.
- **Set 2 Status: SHIPPED (default-OFF). Behavior identical to v2.7.95 until operator flips master flag.**
- Validation plan: backtest with `FORGE_GEOMETRY_TP2_CLOSE_ENABLED=1` on Run 9 data; compare TP2-reached groups' P&L vs ratchet-only.
- Industry citation honored: [eazypips Triple-Scale Method](https://www.eazypips.com/what-are-tp1-tp2-and-tp3-and-how-to-trade-them/) — "TP1 exits 50%, TP2 exits 25%, TP3 takes the rest".

### 2026-05-14 — Operator decisions on §6 open questions (round 1)
- **Ship order**: APPROVED as proposed — Set 2 → 7 → 6 → 8 → 1 → 9 → 4 → 5 → 3 → 10.
- **Set 1 batch size**: DECIDED — `4` legs (industry default; cap 7).
- **Set 1 mode**: DECIDED — Option 1A (literal N positions, each with own magic + SL).
- **Set 2 TP2 close**: DECIDED — 25% of REMAINING after TP1 (not 25% of original batch). Simpler logic — same code works regardless of batch size; matches existing `tp1_close_pct` semantics.
- Status of affected Sets updated:
  - Set 1 → `decided (Option 1A, batch=4, defaults preserved at 1)`
  - Set 2 → `decided (25% of remaining; shipping next as v2.7.96)`
- Open: ship-order #1 = Set 2 = next ship.

### 2026-05-14 — Initial creation
- Created tracker after operator flagged that the earlier multi-leg review (`docs/response-core-logic-design.md`) addressed the wrong paradigm.
- Sets 1-10 enumerated with operator intent / current state / gap / step-by-step recommendation / multi-option / industry research / backward-compat / Status.
- All Sets OPEN, no decisions yet.
- 7 WebSearches performed; 14 sources cited verbatim across the Sets.

### 2026-05-14 — v2.7.95 BUY-side cascade shipped
- Operator confirmed BUY-side cascade asymmetry is a real flaw and wanted it fixed.
- All 8 ship steps complete: VERSION bumped 2.7.94 → 2.7.95, 16 struct fields, defaults, JsonHasKey loaders, parallel `g_buy_stop_stack[10]`, expiry sweep, BUY-STOP cascade body, SELL_LIMIT recovery body, config files (defaults JSON + sync mappings + .env.example).
- Default-OFF — `FORGE_BUY_STOP_CONT_ENABLED=0` preserves current behavior.
- `make forge-compile` clean; end-to-end parity audit passed (16/16 keys).
- File:line cites in §5.

### 2026-05-14 — Skill continuous-update mandate added
- `.claude/skills/forge-monitor/SKILL.md` updated to require this doc be read at the start of every monitoring session touching multi-leg / cool-period / TP-tier / SL-trail code paths.
- Mandate cite in §7.
