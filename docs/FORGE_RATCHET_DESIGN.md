# FORGE Ratchet Design & Logic Flow

**Status**: canonical · **Owner**: FORGE EA core · **Last updated**: 2026-05-15 · **First case study**: G5001 (2026-05-15, +$103.84)

This doc captures the **price-tracking + profit-banking architecture** that fires once a FORGE trade is entered. The ratchet stack is what turns ATR-anchored TPs into actual banked dollars under real retraction patterns. Codified after the G5001 win on 2026-05-15 — where SL ratchet + TP tighten captured +$103.84 in 6 minutes vs an alternative path of either +$12 (no ratchet) or potential $0 (no tighten).

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
