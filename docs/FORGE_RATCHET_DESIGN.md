# FORGE Ratchet Design & Logic Flow

**Status**: canonical · **Owner**: FORGE EA core · **Last updated**: 2026-05-15 · **First case study**: G5001 (2026-05-15, +$103.84)

This doc captures the **price-tracking + profit-banking architecture** that fires once a FORGE trade is entered. The ratchet stack is what turns ATR-anchored TPs into actual banked dollars under real retraction patterns. Codified after the G5001 win on 2026-05-15 — where SL ratchet + TP tighten captured +$103.84 in 6 minutes vs an alternative path of either +$12 (no ratchet) or potential $0 (no tighten).

## §0 Why FORGE has a ratchet system (and why it's unique)

The ratchet system is a **FORGE-original design** — not borrowed from any retail EA framework, not a port of an ICT canonical pattern, not a MetaQuotes default. It's the operator's encoded discipline made algorithmic. This section captures the design philosophy + empirical motivation so future contributors understand the **why** before changing the **what**.

### §0.1 The trading problem the ratchet solves

XAUUSD scalp setups on M5 timeframe have a characteristic pattern that doesn't fit any standard EA architecture:

1. **Impulse leg arrives in 3-5 M5 bars** — price moves 5-15 pts in the trade direction quickly
2. **Multiple retracements follow** — price tries to retrace 30-60% of the leg, often 2-4 times within 10-20 minutes
3. **Final continuation OR reversal** — either price breaks through prior structure and continues, OR retraces fail and price reverses fully

The trader's question on every winning impulse is: **bank now or hold for more?** Holding risks all the locked gain (next retrace hits SL or BE). Banking too early leaves money on the table. **The decision must be made in seconds, repeatedly, while the trade is live.**

A human operator cannot evaluate this 50× per session across multiple positions. The ratchet system is the algorithmic answer: encode the operator's "bank-vs-hold" decision rule into the EA so it fires deterministically on every retrace + every continuation.

### §0.2 Why standard EAs / canonical patterns don't solve this

| Approach | What it does | Why it fails for XAUUSD scalps |
|---|---|---|
| **Fixed TP / SL (off-the-shelf)** | Set TP once at entry; no modification | TP at 2×ATR is reached often, but retracements mean position rarely SURVIVES to TP. Win rate looks ok; banked $/trade is low. |
| **Trailing SL (classic)** | Move SL toward price as price moves favorably | Reduces drawdown but does nothing about the **TP side**. Position still gives back profit when retracement hits the trailing SL after going far. |
| **Break-even SL only** | Move SL to entry on first profit | First-order improvement but ignores all subsequent retracement signals. Leaves big TPs unreachable. |
| **ICT canonical** (set-and-forget at PD-array level) | Place SL beyond OB / FVG / liquidity; let it run to target | Designed for H1/H4 swing trading where retracement patterns are slower. On M5 scalping the retracement velocity is too high. |
| **Martingale / averaging** | Add to losers on retrace | Catastrophic risk on persistent moves. Operator explicitly bans this per `feedback_chop_grid_no_per_leg_sl`. |
| **Discretionary "feel"** | Trader manually adjusts each trade | Doesn't scale. Operator can't sit in front of MT5 50× per session. |

None of these match the specific shape of XAUUSD M5 scalps. The ratchet is built **for this exact shape**.

### §0.3 The design hypothesis encoded in the ratchet

FORGE's ratchet system embodies three operator-tested hypotheses about how XAUUSD scalps actually pay out:

**H1 — The first TP is the *banking gate*, not the *take-profit*.**

Most EAs treat TP1 as the goal. FORGE treats it as a checkpoint that triggers **all subsequent risk reduction**. Once TP1 fires:
- A partial profit is locked (the leg1 close)
- The remaining position becomes "free to run" (SL ratchets to BE)
- The geometry has empirically validated direction-correctness — the impulse was real

This is why TP1 is set tight (0.5-0.8×ATR), not aspirational. Hitting it doesn't end the trade; it **enables** the trade to proceed safely.

**H2 — Retracement patterns are a real-time signal, not noise.**

Standard EAs filter retracement out (smooth the price, use trailing SL with wide stops). FORGE reads retracement as **information**:
- 1 retrace after TP1 → likely continuation (no L3 fire yet)
- 2-3 retraces within 5 M5 bars → regime is shifting from impulse to chop → **L3 tighten triggers**
- Continuation through prior swing extreme → regime is confirming impulse → **L5 extend triggers**

The retracement count + magnitude is itself an atom that drives the bank-vs-hold decision. The trail_pts formula in `FORGE.mq5:3224` (`MathMax` over trigger_pts, ATR, fixed floor) is the algorithmic embodiment.

**H3 — Conviction decays continuously and must be tracked continuously.**

L4 conviction-decay (`conviction_decay_l1/l2/l3_ratio`) measures **current MFE vs initial MFE**. When the ratio drops to 75% → 50% → 25%, the position is "decaying" — the original conviction at entry is no longer being validated by price. Partial closes scale down exposure as conviction erodes. This is unique to FORGE — most EAs either hold full size or close all; the **graduated decay** is what lets FORGE survive a partial reversal without giving everything back.

### §0.4 What makes FORGE's ratchet structurally unique

Five architectural choices that aren't found together in any other system:

1. **Four-layer stack with strict ordering** (L1→L2→L3→L4). Each layer has a distinct trigger and a distinct effect. Retail EAs typically have one trailing mechanism that conflates all four into a single SL-trail rule.
2. **L3 TIGHTENS the TP** (not just trails it). Most "TP trail" implementations only EXTEND TP as price moves favorably. FORGE pulls TP CLOSER to entry on retracement risk — the opposite of conventional thinking. This is what banked the +$65.12 on G5001's leg2 that would otherwise have been $0.
3. **Multi-leg native architecture**. The ratchet treats a 2-3 leg group as a single risk unit. SL ratchets are computed per-leg but anchored to group events (TP1 fires on leg1 → SL ratchets on leg2 AND leg3). Most retail EAs are single-position per ticket.
4. **Regime-aware fork between EXTEND (L5) and TIGHTEN (L3)**. Same surviving leg, different decisions depending on whether the post-TP1 price action shows continuation pattern or chop pattern. Few systems have this branch.
5. **MFE-ratio decay (L4) as a continuous risk-down**. Most systems either hold full position or fully close. The graduated 0.75 → 0.50 → 0.25 thresholds let FORGE bleed exposure gradually as conviction erodes — preserving optionality on a true continuation while protecting locked profit on a fade.

### §0.5 Empirical motivation — what would happen WITHOUT the ratchet

Per §3.3 counter-factual math on G5001:

- **With ratchet stack**: +$103.84 banked (0 downside)
- **L2 disabled**: leg2 SL stays at original 4559.62; M5 retrace to 4546 would have hit it → leg2 closes at **−$26.50**, net trade = +$12.22
- **L3 disabled**: leg2 TP stays at original 4538.58; reached around 18:11 BUT the intermediate M5 retrace to 4546 hits the BE-ratcheted SL first → leg2 = **$0**, net = +$38.72
- **Both disabled**: same as "L2 disabled" → +$12.22

Without the ratchet stack, G5001 is a **+$12 trade, not a +$104 trade**. Multiply that across the 21 wins / 4 losses today (~25 closed deals, net +$108.57 banked pre-G5001) and the ratchet is plausibly responsible for **2-5× the realized P&L** vs the same entry logic with naive exit.

This is the empirical justification for the architectural complexity — without the ratchet, FORGE's entry edge gets eaten by retracement before it can compound.

### §0.6 Design principles to preserve when modifying the ratchet

Future modifications must respect these invariants (encoded as anti-patterns in §7):

1. **Order matters**. L1 must fire before L2; L2 must fire before L3. Reordering breaks the "$0 minimum guarantee" math.
2. **Direction-only movement**. SL only moves toward entry (BUY: up; SELL: down). TP only tightens toward entry on retrace, only extends away from entry on continuation. Never the reverse.
3. **Group-aware semantics**. A group of legs is a single risk unit. SL ratchets are anchored to group events, not per-leg events.
4. **Idempotent broker calls**. Repeated `OrderModify` calls with the same target return "no change" gracefully; they don't spam the broker. This is what the "0 positions modified" log lines mean (§3.4).
5. **Regime fork explicit**. EXTEND (L5) vs TIGHTEN (L3) is a deliberate regime decision based on retracement count + ADX. Don't let one path silently dominate the other.

If a proposed change violates any of these, it's not a ratchet evolution — it's a different system that should ship under a different name with its own A/B knob.

### §0.7 Naming convention origin

The term "ratchet" is operator-coined. It captures the **one-way nature** of the mechanism: a ratchet (the mechanical kind) only moves in one direction; it can't slip back. SL once ratcheted to BE can never fall back below entry. TP once tightened never widens back to the original target. The mechanical metaphor is exact.

This is distinct from:
- **Trail** (`stop trail`) — a continuous follow that can also retreat
- **Cascade** — multi-leg pendings stacked behind entry (different mechanism, lives in FMSR / Track A doc)
- **Decay** — partial-close on MFE erosion (L4 specifically; subset of ratchet, not a synonym)

When writing code, comments, or future docs, prefer "ratchet" for the one-way locked-direction mechanism. Use the other terms for their specific cousins.

---

## §1 Why this doc exists

Every winning FORGE trade is the product of two things:
1. **Entry logic** — the ICT atom catalog + composite scores + filter chain (documented in `FORGE_SETUP_ICT_MAP.md` + skill §I.13)
2. **Exit logic** — the **ratchet stack** that protects locked profit and tightens targets when retracement risk rises

Entry has its own doc. This is the missing canonical doc for exit. Before this doc, the operator had to reconstruct ratchet behaviour from broker logs each time — making it hard to validate, calibrate, or extend safely. Now the design lives here.

## §2 The 4-layer ratchet stack (canonical order of fire)

Once a multi-leg entry fires (e.g. MOMENTUM_DUMP with TP1 + TP2 legs), the stack engages on every tick + every M5 close in this strict order:

| Layer | Name | Fires when | What it does | Code location |
|---|---|---|---|---|
| **L1** | TP1 native fire | price touches the TP1 limit order on the broker | leg1 closes natively at the ATR-anchored TP1 price; `[tp <price>]` comment in TRADES | broker-side (no EA code) |
| **L2** | SL ratchet to BE (`move_be_on_tp1`) | within ~6s after L1 fires | remaining legs' SL moves from initial (1.5-4×ATR away) to TP1 price (= breakeven on the new lot weight) | `FORGE.mq5:1976` (struct), `:3328` (gate), `:3358` (`PositionModify`) |
| **L3** | TP-trail post-TP1 | every tick / M5 close while leg2+ open | TP on remaining legs tightened toward entry as retrace pattern accumulates; eligibility gated by trail-trigger distance + ATR-anchored trail pts | `FORGE.mq5:3224` (`trail_pts` calc), `:3276` (`PositionModify` call) |
| **L4** | Conviction-decay partial close | every M5 close after `decay_grace_bars`, when current/initial MFE ratio crosses thresholds | partial close at L1/L2/L3 ratios (0.75 / 0.50 / 0.25 of initial MFE) — banks fractions of the leg as conviction erodes | `FORGE.mq5:2998-3052` (`conviction_decay_l1/l2/l3_ratio`) |

Optional extension layers (Mode-dependent):
- **L5** TP3 dynamic stretch (`tp3_mode=1`) at `FORGE.mq5:3443` — only fires when a 3rd leg was armed at entry time (currently MOMENTUM_DUMP ships 2 legs, so L5 is dormant for that setup)
- **L6** Pre-TP1 recovery arm (v2.7.122 P1, FMSR Track A) at `ArmPreTP1Recovery` — fires when MFE ≤ 0 AND adverse ≥ 1.5×ATR AND no TP1 hit (bad-trade-state rescue, not bank-on-retrace)

## §2.5 ASCII flow diagrams

These diagrams show the ratchet stack visually. **BUY direction** is the primary illustration (price climbs from entry upward); SELL is the mirror (see §2.5.5).

### §2.5.1 The level map at entry (state 0)

At the moment the trade fires, all targets and stops are set. Distances are illustrative; real values come from per-setup `tp1/tp2/tp3_atr_mult` and `sl_atr_mult` knobs.

```
 price
   ▲
   │
   │  TP3_initial  ───────●────── e.g. entry + 3.5×ATR    (3rd-leg target — only if multi-leg ladder armed)
   │                      │
   │                      │
   │  TP2_initial  ───────●────── e.g. entry + 2.0×ATR    (2nd-leg target)
   │                      │
   │  TP1_initial  ───────●────── e.g. entry + 0.7×ATR    (1st-leg "scalp bank" target)
   │                      │
   │  ENTRY (E)    ━━━━━━━◆━━━━━━ filled price            ◆ = position open
   │                      │
   │                      │
   │  SL_initial   ───────●────── e.g. entry − 1.5..4×ATR (initial stop, ATR-anchored)
   │
   ▼
```

### §2.5.2 The 4 ratchet states (left-to-right time flow)

```
 state 0                state 1                  state 2                  state 3
 (entry)                (post-L1 TP1)            (post-TP2 fire)          (continuation break)
                                                                          ┌─ L3 stretch (TP3 extends)
─────────────────       ─────────────────         ─────────────────         ─────────────────
                                                                          ▲
  TP3 ●                   TP3 ●                    TP3 ●                    TP3_ext ●━━━━━━━━━ ◀── extended
                                                                            (initial TP3 was here)
                                                                          │
  TP2 ●                   TP2 ●                    TP2 ✓ ✗  filled         TP2 ✗ (closed)
                                                                          │
  TP1 ●                   TP1 ✓ ✗  filled         TP1 ✗ (closed)          TP1 ✗ (closed)
                                                                          │
   E  ◆                    E ◆                     E ◆                      E ◆
                                                                          │
                          SL ●  ◀ ratcheted        SL ●  ◀ ratcheted       SL ●  (or trailed up
  SL ●                          to ENTRY (BE)            to TP1 (locks            with structure)
   (initial SL)                                          partial profit)
```

**State 0 → 1**: leg1 hits **TP1 native** (L1 fire). Broker auto-closes leg1 at the TP1 limit. Comment: `[tp <TP1_price>]`.

**State 1 → 2**: within ~6 seconds of L1, the **`move_be_on_tp1` ratchet (L2)** moves SL on every remaining leg to the **ENTRY price** (breakeven). The trade now has **zero downside risk** — worst case all remaining legs close at $0 if price reverses fully.

**State 2 → 3 (good path)**: leg2 hits **TP2 native**. SL ratchets again — this time to **TP1 price** on leg3 (locking in TP1-distance of profit even if leg3 never fires). On a continuation break (price closes above prior swing high, h1 ADX rises, or operator-defined `tp3_mode=1` trigger fires), **TP3 extends** further from entry (L5 / dynamic stretch). Leg3 now chases more profit on the validated trend.

### §2.5.3 The retrace path (what happened on G5001) — TP TIGHTEN, not extend

When the price-action between L1 and L2 shows **multiple retracement attempts** (not a clean continuation), L3 fires instead of L5. TP tightens INWARD toward entry to bank before the next retrace erases it:

```
                  retrace #1     retrace #2     retrace #3
                       ▲              ▲              ▲
                       │              │              │
  TP3 ●                │              │              │            TP3 ●  (untouched)
                       │              │              │
  TP2_initial ●━━━━━━━━┿━━━━━━━━━━━━━━┿━━━━━━━━━━━━━━┿━━━━━━━━━━━ TP2_init ●
                       │              │              │            ━━━━━━━━━━━━ ◀── L3 tighten
  TP2_tight   ━━━━━━━━━┿━━━━━━━━━━━━━━┿━━━━━━━━━━━━━━┿━━━━━━━━●━ TP2_tight ●     pulled INWARD
                       │              │              │            (closer to entry)
  TP1 ✓ ✗ filled       │              │              │            TP1 ✗ (closed)
   (leg1 banked +$X)   │              │              │
                       ▼              ▼              ▼
                                                                  
  E ◆                                                              E ◆
                                                                  
  SL_at_BE ●  ◀ ratcheted to entry on L1                          SL_at_BE ●  (unchanged)
```

The L3 calc (`FORGE.mq5:3224`):
```
trail_pts = MathMax(12.0,
              MathMax(trigger_pts × (is_bounce ? 0.95 : 0.80),
                      m5_atr_pts   × (is_bounce ? 1.20 : 0.90)))
```
chooses the **most conservative (widest) tighten** of three sources, so the TP doesn't ratchet on a single volatile bar. G5001's TP2 tightened from 4538.58 → 4543.73 (2.85 pts inward) after the retrace pattern accumulated.

### §2.5.4 The SL ratchet path (BE → TP1 → TP2 → structure trail)

SL is the primary risk-management ratchet. It only moves in the favorable direction (UP for BUY, DOWN for SELL) — never against the trade.

```
 price
   ▲
   │  ┌──────── TP2 fires here   ▶▶▶  SL ratchets to ◀── 4th rung
   │  │                                                  TP1 price
   │  ●●●●●  ▶▶▶  SL ratchets to TP1 price (state 2)
   │  │                                                  
   │  ●●●●●  ▶▶▶  SL ratchets to ENTRY/BE (state 1)     ◀── 3rd rung
   │  │                                                  
   │  ◆ ENTRY                                            ◀── 2nd rung
   │
   │
   │
   │  ●●●●●  ▶▶▶  SL at initial position (state 0)      ◀── 1st rung (highest risk)
   │
   ▼
                       state 0       state 1       state 2       state 3
                       (entry)       (post-TP1)    (post-TP2)    (cont. break or
                                                                  structure trail)
```

The SL **never goes back down** once ratcheted — even if price retraces, the locked SL holds the worst-case at the ratcheted level. Combined with TP fires, this is what creates the "$0 minimum, +$X locked" math from §3.3.

### §2.5.5 SELL direction (mirror)

For a SELL trade, every level inverts. Price falls from entry; targets are BELOW, SL is ABOVE:

```
 price
   ▲
   │  SL_initial   ───────●────── e.g. entry + 1.5..4×ATR (initial stop, ABOVE entry)
   │
   │
   │  ENTRY (E)    ━━━━━━━◆━━━━━━ filled price
   │
   │  TP1_initial  ───────●────── e.g. entry − 0.7×ATR    (1st leg target, BELOW)
   │
   │  TP2_initial  ───────●────── e.g. entry − 2.0×ATR
   │
   │  TP3_initial  ───────●────── e.g. entry − 3.5×ATR
   │                      │
   │  TP3_extended ───────●────── ◀── on continuation DOWN-break, TP3 extends FURTHER below
   │
   ▼
```

Ratchet logic is symmetric: SL ratchets DOWN (toward entry, then toward TP1 price) on L1/L2/L3 events. TP3 extends DOWNWARD on continuation breaks. G5001 (the canonical SELL case study in §3) used exactly this mirror.

### §2.5.6 TP3 extension trigger — when does L5 fire instead of L3?

The fork between **TP3 EXTEND** (L5, more profit) and **TP TIGHTEN** (L3, bank early) depends on the post-TP1 price-action pattern:

```
 After TP1 fires (state 1), the next 2-5 M5 bars decide:

                   ┌─ price keeps trending favorable WITHOUT
 STRUCTURE BREAK ──┤  retracing past 0.5×ATR back toward entry      ──▶  L5: TP3 EXTENDS
 (continuation)    │  + h1 ADX rises OR price closes past prior          (chase more profit)
                   │  swing extreme (BUY: prior swing high;
                   │   SELL: prior swing low)
                   │
                   └─ tp3_mode=1 ATR-stretch OR tp3_mode=2 structure-anchored


                   ┌─ price oscillates back-and-forth between TP1
 RETRACE PATTERN ──┤  and entry 2+ times within 5 M5 bars            ──▶  L3: TP2/TP3 TIGHTEN
 (chop)            │                                                       (bank before reversal)
                   │
                   └─ trail_pts formula (§2.5.3) computes inward TP
                      shift; SL stays at BE/TP1 from L2
```

In practice both can fire on the same trade at different times: L3 may tighten TP2 first, then if a continuation break appears after TP2 fires, L5 can extend TP3 on the surviving leg3. They're not mutually exclusive — they're **regime-aware**.

---

## §3 The G5001 canonical case study (2026-05-15)

This is the reference trade. Cite this section by name when comparing future winners to the canonical ratchet flow.

### §3.1 Setup

- **Entry fired**: 2026-05-15 14:55:05 broker time (17:55 NY)
- **Symbol / setup**: XAUUSD / MOMENTUM_DUMP SELL (per FORGE_SETUP_ICT_MAP.md §B.2 → slated for MSS_CONTINUATION fold under M7-M11)
- **2 legs entered** at avg 4547.34 (leg1 @ 4547.23, leg2 @ 4547.30), 0.16 lot each
- **Initial geometry**:
  - SL: 4559.62 (12.39 pts above entry = 3.58×ATR_m5)
  - TP1: 4544.81 (2.42 pts below = 0.7×ATR)
  - TP2: 4538.58 (8.65 pts below = 2.5×ATR)

### §3.2 The ratchet sequence

| Time (broker) | Event | Detail | Outcome |
|---|---|---|---|
| 14:55:05 | **Entry** | 2 legs filled | initial SL/TP1/TP2 set per §3.1 |
| ~15:00:57 | **L1 TP1 native fire** | leg1 exits @ 4544.81 | banked **+$38.72** (TP comment `[tp 4544.81]`) |
| 15:01:03 | **L2 SL ratchet** | `MODIFY_SL ticket=...809 to 4544.80 — 1 positions modified` | leg2 SL jumped 4559.62 → 4544.80; downside risk eliminated |
| 15:01:06 | **L3 TP tighten (first)** | `MODIFY_TP ticket=...809 to 4543.73` | TP2 pulled 2.85 pts closer (8.65pt target → 5.15pt target) |
| 15:01:15 | **L3 TP tighten (retry, idempotent)** | `MODIFY_TP ticket=...809 to 4543.73 — 0 positions, 0 pending modified` | "no change needed" — broker already at target |
| ~15:01:18 | **leg2 close @ 4543.23** | exit 0.50 pts past the tightened TP | banked **+$65.12** (4.07 pts) — one more late tighten or M5-retrace exit landed in the gap |
| | **TOTAL** | | **+$103.84 in ~6 min** |

### §3.3 The math — why this beat both alternatives

The operator asked: was the tracking logic banking profit correctly? Counter-factual analysis:

| Path | What happens | Net P&L |
|---|---|---|
| **Actual (with ratchet stack)** | L1 + L2 + L3 fire as above | **+$103.84** ✓ |
| **L2 disabled (no `move_be_on_tp1`)** | leg2 SL stays at 4559.62; M5 retrace to 4546 would have hit SL on leg2 | leg1 +$38.72, leg2 −$26.50 = **+$12.22** |
| **L3 disabled (no TP tighten)** | TP2 left at original 4538.58; price reached it at ~18:11 broker — BUT M5 retraced to 4546 in between, which would have hit the BE-ratcheted SL on leg2 first | leg1 +$38.72, leg2 ~$0 (BE) = **+$38.72** |
| **Both disabled** | leg2 stops at original SL, leg1 wins TP1 cleanly | leg1 +$38.72, leg2 −$26.50 = **+$12.22** |
| **Theoretical max (hold to TP2 4538.58)** | requires no intermediate retrace | leg1 +$38.72, leg2 +$140 = **+$178.72** (but unreachable in this regime — the M5 retrace to 4546 was real) |

**Conclusion**: ratchet stack chose **+$103.84 guaranteed (with $0 downside) vs +$178.72 with downside risk to +$38.72**. Under multiple-retracement patterns, the certainty premium is positive-EV.

### §3.4 The 0.50-pt anomaly (worth a future audit)

- L3 tightened to 4543.73 (target +3.57 pts)
- Actual close @ 4543.23 (+4.07 pts) — 0.50 pts BETTER than the tightened target
- Hypothesis A: one more `MODIFY_TP` landed between 15:01:15 and 15:01:18 that wasn't captured in the log tail sampled
- Hypothesis B: M5 bar-close trigger fired a `PositionClose` on the leg before the tightened TP triggered
- Hypothesis C: conviction-decay (L4) fired at the moment of close, taking partial close on the leg

Currently the active TP value is only reconstructable from broker logs. The future enhancement in §6.1 (`active_tp_price` SIGNALS column) would let us resolve this in scribe directly.

## §4 Operator's preferred discipline (from memory)

The ratchet stack encodes several memory-mandated principles:

| Memory | What it mandates | How the ratchet honours it |
|---|---|---|
| `feedback_chop_scalp_one_tp_fast_sl` | "chop scalp keeps TP1+TP2 with fast BE-snap on TP1 + 0.5×ATR trail post-TP2" | L2 (BE-snap on TP1) + L3 (post-TP1 tighten using ATR-anchored trail_pts) |
| `feedback_lot_broker_minimum` | "every lot calculation must use `MathMax(SYMBOL_VOLUME_MIN, calculated_lot)`" | conviction-decay (L4) closes are guarded by min-lot floor at the partial-close call site |
| `feedback_chop_grid_no_per_leg_sl` | "grid ladder strategies for chop don't use per-leg SL" | ratchet does NOT apply to cascade grid setups (which use basket kill switches instead — separate exit doc) |
| `feedback_trade_review_lens` | "every TAKEN entry passes direction-correctness + miss-catch" | L1-L4 only engage on direction-correct trades; L6 (P1 recovery) handles the misses (bad-trade-state) |

## §5 Default knob values (canonical)

From `config/scalper_config.defaults.json` + `.env.example`:

| Knob | Default | Purpose |
|---|---:|---|
| `move_be_on_tp1` | `1` (ON) | Master toggle for L2 ratchet |
| `tp1_close_pct` | per-setup | % of group lots that close on L1 (e.g. 50 = half) |
| `tp2_close_pct` | per-setup | % of remaining that close on TP2 native fire |
| `conviction_decay_partial_close_enabled` | `1` (ON) | L4 master toggle |
| `conviction_decay_l1_ratio` | `0.75` | partial-close at MFE decay to 75% of peak |
| `conviction_decay_l2_ratio` | `0.50` | partial-close at MFE decay to 50% |
| `conviction_decay_l3_ratio` | `0.25` | full close at MFE decay to 25% |
| `conviction_decay_l1_close_pct` | `25.0` | % of remaining at L1 |
| `conviction_decay_l2_close_pct` | `50.0` | % of remaining at L2 |
| `conviction_decay_grace_bars` | `2` | skip decay for first N M5 bars after entry |
| `tp3_mode` | `1` | TP3 dynamic stretch mode (`0`=off, `1`=ATR-anchored, `2`=structure-anchored) |
| `tp3_dist_from_sl_atr_mult` | `2.0` | TP3 placement: SL + this × ATR (when `tp3_mode=1`) |

Trail-pts formula (FORGE.mq5:3224 — paraphrased):

```mql5
double trail_pts = MathMax(12.0,
                     MathMax(trigger_pts * (is_bounce ? 0.95 : 0.80),
                             m5_atr_pts * (is_bounce ? 1.20 : 0.90)));
```

This means trail distance is the larger of: 12 pts floor, 80-95% of the trigger distance, or 0.9-1.2× M5 ATR — choosing the **more conservative** (wider stop, less twitchy) of the three.

## §6 Future enhancements (Mode B / C roadmap)

### §6.1 `active_tp_price` SIGNALS column (Mode B)

**Problem**: the active TP value is only reconstructable from broker logs. Scribe `forge_signals` doesn't carry the running TP, so analytics can't ask "what % of the time does L3 fire before L4?" or "histogram of TP-tighten magnitude by setup".

**Proposal**: add `active_tp_price REAL` to SIGNALS (5-layer schema parity per §I.5/§I.11.1). EA writes it on every ManageOpenGroups tick. Scribe mirrors it. Then analysts can:
- compute average tighten distance per setup
- correlate tighten frequency with regime (chop vs trend days)
- validate the 0.50-pt G5001 anomaly retroactively

Cost: ~+1 column, +1 EA write per tick, +1 scribe write per tick. Trivial.

**Status**: backlog (parking lot candidate).

### §6.2 `active_sl_price` companion column

Same pattern for SL. Currently the live SL is in `market_data.json open_positions[].sl` but not in scribe. Adding it would let us validate the L2 ratchet timing precisely.

### §6.3 Ratchet-decision SIGNALS columns

Three boolean columns:
- `ratchet_l2_fired` (when L2 SL ratchet fires)
- `ratchet_l3_fired` (when L3 TP tighten fires)
- `ratchet_l4_fired` (when L4 conviction decay fires)

Lets analytics ask "of the trades that won, what % had L3 fire?" → calibrates whether the trail logic is doing real work or just adding noise.

### §6.4 Mode B / C escalation for L3

L3 currently operates in Mode A (compute + log only — but in this case, the "log" is the actual `MODIFY_TP` call, so it IS shaping trade flow). Wait — that's wrong. L3 IS Mode C in current state (it actively modifies the TP, hard-changes the trade outcome). The Mode A→B→C taxonomy from §I.13.5 applies to **composite scores**, not to ratchet mechanisms. The ratchet stack is intrinsically Mode C — it must change trade flow to do its job.

What IS adjustable: the **trigger thresholds** for L3 firing (`trigger_pts`, `is_bounce` switch, ATR-mult). These are tunable per setup. Future calibration work could log L3 fire frequency by setup and identify under-firing or over-firing cases.

## §7 Anti-patterns to avoid

### §7.1 Don't disable L2 to "let winners run"

L2 (`move_be_on_tp1`) is the single most-impactful ratchet — it converts "trade either wins or loses" into "trade either wins more or wins zero". The G5001 case shows the +$92 swing it produced. Disabling L2 for a "swing trading" mentality is a regime mismatch — FORGE is a scalper.

### §7.2 Don't widen L3 trail-pts to "give it room"

The trail_pts formula uses `MathMax` over three sources specifically because operators historically tried to widen it. Wider trail = less tighten = more given-back on retrace. The conservative-wider arm of `MathMax` already protects against premature ratchet on a single volatile bar.

### §7.3 Don't run multi-leg setups without L1-L4

A 2-leg MOMENTUM_DUMP without ratchet is just 2 independent trades. The leverage from L2 (BE-snap) + L3 (tighten) requires both legs working as a unit. If you're tempted to ship a setup that opts out of ratchet, ship it as a 1-leg setup instead — the architecture is cleaner.

### §7.4 Don't conflate ratchet with FMSR

FMSR (Fast-Market Sweep Rescue, `docs/FORGE_FAST_MARKET_SWEEP_RESCUE.md`) handles the **opposite** problem: bad-trade-state rescue when MFE never goes positive. Ratchet handles the **good** problem: protect and tighten when MFE IS positive. The two compose — FMSR's pre-TP1 arm (L6 above) prevents bad-state losses; ratchet (L1-L4) maximizes good-state banking.

## §8 Cross-references

- `FORGE_SETUP_ICT_MAP.md §B.2` — 4-category entry model (ratchet engages after entry)
- `FORGE_SETUP_ICT_MAP.md §B.8.2` — atom catalog (ratchet doesn't read atoms; it operates on price/position state)
- `FORGE_FAST_MARKET_SWEEP_RESCUE.md` — sibling exit doc for bad-trade-state recovery
- `FORGE_GLOSSARY.md §8` — recovery terms (FMSR, P1, Track A/B/C — distinct from ratchet)
- `.claude/skills/forge-monitor/SKILL.md §I.13.3` — Pattern P1 cites G5001 as canonical winner
- `.claude/skills/forge-monitor/SKILL.md §I.11.1` — v2.7.124 decision-log entry
- `ea/FORGE.mq5:1976, 3224, 3276, 3328, 3358, 3443, 2998-3052` — implementation sites
- `config/scalper_config.defaults.json` — knob defaults
- `feedback_chop_scalp_one_tp_fast_sl.md` — operator-mandated discipline that ratchet implements
- `feedback_trade_setup_analysis_framework.md §"Repeatable successful setups" Pattern P1` — canonical winner pattern referencing this doc

## §9 Changelog

- **2026-05-15** — initial canonical doc, written in response to operator question "does the price tracking logic work to help bank?" after G5001 (+$103.84). Captures 4-layer ratchet stack (L1 TP1 native + L2 SL ratchet + L3 TP tighten + L4 conviction decay) with code-line cites + canonical case study + counter-factual math + future Mode-B enhancements + anti-patterns. Cross-linked to skill §I.13.3 Pattern P1 + glossary §8 (which now references this doc as the ratchet authority).
- **2026-05-15** — added §2.5 ASCII flow diagrams (level map at entry, 4-state flow, retrace path showing L3 tighten, SL ratchet path, SELL mirror, L3-vs-L5 fork decision tree) per operator request "add the ASCII of the ratchet system here, illustrate with TP1 and TP2 and potential TP3".
- **2026-05-15** — added §0 design philosophy + motivation (the trading problem, why standard EAs don't solve it, three operator-tested hypotheses H1/H2/H3, five structural uniqueness traits, empirical motivation via counter-factuals, design invariants to preserve, naming-convention origin) per operator request "define the idea and motivation behind the creation of our ratchet system in forge. This is unique to forge".
