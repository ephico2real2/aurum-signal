# PEMCG + ICT integration — how they choreograph

**Status**: canonical reference for how the existing PEMCG composite (v2.7.84, operator-coined) interacts with the new ICT structure layer (v2.7.118+, MSS/FVG/ChoCH/Liquidity/OB/Breaker/Unicorn). Read this before any phase that adds an ICT layer.

## §1 The two systems are not equivalent

| Question they answer | PEMCG | ICT (ISS atoms) |
|---|---|---|
| "Should we NOT enter?" (anti-trap) | ✓ primary role | ✗ |
| "Should we enter with conviction?" (pro-structure) | ✗ | ✓ primary role |
| Asymmetric on direction? | Yes (BUY warnings ≠ SELL warnings) | Yes (BUY/SELL mirror) |
| Stateless per M5 close? | Yes | Yes (atoms); FVG ring is stateful |
| Operator-coined? | Yes (v2.7.84, 2026-05-13) | No (industry-canonical ICT) |
| Currently over-blocking? | Yes — 730× SELL blocks in confirmed bear on 2026-05-14 (see `FORGE_LIVE_2026-05-14_ANALYSIS.md`) | n/a (atoms still stub-0 in v2.7.112; real in v2.7.118 default-OFF) |

**Key insight**: PEMCG is a "reversal-trap warning" composite. ICT MSS/FVG are "structural confirmation" composites. They check **different things**, and their outputs should compose, not compete.

## §2 What each layer does

### §2.1 PEMCG — the existing 7-atom reversal-warning composite

`docs/FORGE_PEMCG_ARCHITECTURE.md` is the canonical reference. Summary:

7 atoms (A1-A7) score whether the *next* candle is likely to reverse against the proposed entry direction. Atoms include RSI extreme, weak bar body, BB distance, MACD divergence, range-expanding flag, long wick rejection.

**Threshold**: 5/7 (supermajority since v2.7.86 fix).

**Three layer consumers**:
- **Layer 1 — UMCG** (Universal Market Condition Gate): SKIP if `pemcg_buy_warnings ≥ 5` (gate code `pemcg_buy_reversal_block`) or mirror SELL. Fires at every setup-trigger.
- **Layer 2 — CVCSM**: SL-triggered cooldown state machine. Re-evaluates PEMCG every M5 close to decide release.
- **Layer 3 — BB_EXHAUSTION_REVERSAL**: opposite-direction reversal setup that *consumes* PEMCG warnings (high warnings on BUY side → fire SELL reversal trade).

PEMCG **stays in place**. The Phase 1-5 ICT work does not modify PEMCG atoms, thresholds, or any of its three layer consumers.

### §2.2 ICT ISS — the new structure-confirmation composite

`ea/include/Forge/IctStructure.mqh` (Phase 1, v2.7.118) introduces:
- `g_iss_mss` — structural break confirmed (close beyond swing + displacement)
- `g_iss_fvg` — price inside an active FVG retracement zone
- `g_iss_choch_support` — Phase 2 work (v2.7.119)
- `g_iss_choch_against` — Phase 2 work (HARD GATE when set)
- `g_iss_score` — weighted sum, 0-10

**Threshold** (per v2.7.112 design): `iss_min_threshold = 5` for STANDARD, `≥ 8` for HIGH_CONVICTION.

The atoms compute regardless of PEMCG state. They are ADDITIVE information — they tell the system *something different* than PEMCG does.

## §3 Integration strategy — three modes, picked by env knob

Operator-validated through experimentation. All three are wired in code; the active behaviour is selected by env knob.

### §3.1 Mode A — Coexist (default; current behaviour through v2.7.118)

```
ISS atoms compute → log to SIGNALS columns (iss_score, iss_mss, iss_fvg, ...)
                  → NO gate fires
PEMCG operates exactly as today (UMCG L1, CVCSM L2, Layer 3 reversal)
```

Knobs:
- `FORGE_ICT_MSS_ENABLED=0` (Phase 1 default; flip to 1 for atom compute)
- `FORGE_GATE_ISS_BLOCK_BELOW_THRESHOLD=0` (default; never gates)

This mode is for the validation phase. We collect ISS distributions in tester replays and live shadow logs. PEMCG is untouched. No behaviour change beyond logging.

### §3.2 Mode B — ICT-additive (post-validation)

```
PEMCG fires as today → still blocks reversal-trap entries
ADDITIONALLY: if ISS_score < iss_min_threshold → SKIP iss_below_threshold
              if iss_choch_against = 1          → SKIP iss_choch_against_block (HARD)
```

Knobs:
- `FORGE_GATE_ISS_BLOCK_BELOW_THRESHOLD=1`
- All ICT atom-compute knobs at 1

Effect: takes signals only when BOTH PEMCG passes AND ICT structure supports. More restrictive than today. Tester evidence required before enabling.

### §3.3 Mode C — ISS-C HIGH_CONVICTION override (the live problem-solver)

This is the **specifically-designed solution** to the 730 PEMCG_SELL over-block pattern documented in `FORGE_LIVE_2026-05-14_ANALYSIS.md`.

```
Compute ISS-C score (trend-continuation, 7 atoms + 1 hard gate per the
live analysis doc §5):
   - regime alignment, h1_trend, m5_adx, m15_adx, vwap_dist, psar, bar quality
   - hard gate: prev-bar range ≤ 2.0×ATR (knife-catch reject)

If ISS-C ≥ 8 (HIGH_CONVICTION):
   → OVERRIDE PEMCG_*_reversal_block on the matching direction
   → fire the entry + apply lot amplifier
Else if ISS-C ∈ [6, 7]:
   → PEMCG applies normally (no override)
Else if ISS-C < 6:
   → PEMCG applies + no ICT structural confirmation
```

Knob: `FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED=0` (default; flip after validation)

This is the **right** integration for trending markets. PEMCG correctly fires on divergence; ISS-C correctly overrides when the entire MTF stack confirms continuation. The two roles remain distinct.

## §4 Phase-by-phase impact on PEMCG

| Phase | Version | Effect on PEMCG |
|---|---|---|
| 1 | v2.7.118 | **No change.** ISS atoms (MSS, FVG) compute + log but never gate. PEMCG fires as today. |
| 2 | v2.7.119 | **No change.** ChoCH atoms (support, against) added. `iss_choch_against` is a HARD GATE in the score struct but `iss_block_below_threshold` stays 0. PEMCG fires as today. |
| 3 | v2.7.120 | **No change.** Order Block + Breaker + Premium/Discount logged. No gating. PEMCG fires as today. |
| 4 | v2.7.121 | **ICT scoring engine** assembles MSS/FVG/ChoCH/OB/Breaker/Unicorn into the master `ICTSignalScore` struct (per the operator spec § K). Still logged-only by default. PEMCG fires as today. |
| 5 | v2.7.122 | **CRT + Venom + Bread-and-Butter + Seek-and-Destroy** added. Master score complete. PEMCG fires as today. |
| Validation (post-5) | — | Operator selects Mode B or Mode C in env knobs based on tester replay results against G5006/G5048 known losers + 2026-05-14 live PEMCG-blocked SELLs. |

## §5 Decision matrix — when each mode is right

| Market condition | PEMCG behavior | Mode A (current) | Mode B (additive) | Mode C (override) |
|---|---|---|---|---|
| Confirmed trend continuation (regime + H1 + M15 + VWAP + PSAR all aligned) | Over-blocks (730× on 2026-05-14 SELL) | ❌ leaves money on table | ❌ still blocks (additive doesn't help) | ✅ overrides on HIGH_CONVICTION → fires |
| Reversal trap at top/bottom (G5006, G5048 class) | Correctly blocks | ✅ blocks | ✅ blocks | ✅ blocks (ISS-C should score low — anti-trap atoms catch it via low bar quality / divergent MACD) |
| Counter-trend deep retracement (OTE at H4 demand) | May block | ❌ blocks legit OTE | ❌ still blocks | △ depends on ISS-C threshold tuning; safer to keep PEMCG in place |
| Chop / range-bound | Blocks both sides aggressively (correct) | ✅ blocks | ✅ blocks | ✅ blocks (ISS-C atoms fail — no regime alignment) |
| Knife-catch / WRB capitulation | Often misses | ❌ misses | △ ISS hard gate `iss_choch_against` should catch when ChoCH ships in Phase 2 | ✅ ISS-C hard-gate A8 (prev_bar_range ≤ 2.0×ATR) explicitly rejects |

## §6 Backwards-compatibility guarantees

- **Phase 1-5 default-OFF**: every new ICT module ships with all its env knobs at 0. With defaults, PEMCG behaviour is byte-identical to v2.7.117.
- **PEMCG knobs untouched**: `FORGE_GATE_UMCG_*`, `FORGE_GATE_CVCSM_*`, `FORGE_SETUP_BB_EXHAUSTION_REVERSAL_*` are NOT modified by any ICT phase.
- **Mode switching is one knob flip**: enabling Mode B = `FORGE_GATE_ISS_BLOCK_BELOW_THRESHOLD=1`. Enabling Mode C = `FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED=1`. Both default 0, both reversible.
- **Operator approval required before flipping**: each mode flip must follow a tester replay validation pass — minimum requirement is "G5006/G5048 known losers still SKIP, 2026-05-14 live PEMCG-blocked SELLs now TAKE."

## §7 What's NOT decided yet (Phase 4-5 work)

- **Whether ICT score replaces PEMCG entirely** — the operator spec § K describes an `ICTSignalScore` master struct. Whether this struct REPLACES PEMCG (Mode D — drop PEMCG, ICT becomes the only gate) is a decision to make AFTER Phase 5 ships, with full tester data. Mode D is not on the table today.
- **Whether PEMCG becomes one input to the ICT score** — e.g., `ictScore.reversalRisk = -pemcg_warning_count * 5`. Possible composition but adds complexity. Not designed yet.
- **CVCSM interaction with ChoCH-against** — Phase 2 ChoCH may want to bypass CVCSM cooldown ("structure flipped — re-enter the new direction immediately, ignore cooldown"). Open question.

## §8 Cross-references

- `docs/FORGE_PEMCG_ARCHITECTURE.md` — canonical PEMCG reference (§3 layer consumers, §5 ASCII diagram, §11 changelog)
- `docs/prompts/ICT_Tradingidea.md` — operator-supplied ICT spec
- `docs/MQL5_MODULAR_EA_DESIGN.md` — modular FORGE convention (Phase 1 first consumer)
- `docs/FORGE_LIVE_2026-05-14_ANALYSIS.md` §5 — the ISS-C composite design that motivates Mode C
- `ea/include/Forge/IctStructure.mqh` — Phase 1 module (MSS + FVG; ChoCH stubbed)
- `ea/FORGE.mq5:13586` — the setup-trigger chokepoint where ISS atoms get computed alongside the existing PEMCG check

## §9 Changelog

- **2026-05-14** — Initial integration spec. Phase 1 (v2.7.118) ships in Mode A (coexist; ISS atoms compute + log, no gating). Modes B and C designed but knob-disabled until tester-replay validation against G5006/G5048 known losers + 2026-05-14 live PEMCG-blocked SELLs. PEMCG behaviour byte-identical to v2.7.117 through Phase 5.
- **2026-05-16 — Mode D SHIPPED (v2.7.129, behavioral)**. Operator-confirmed direction 2026-05-16: *"remove pemcg as well"* + *"let us focus on using ict tier and strategies"*. PEMCG + CVCSM + BB_EXHAUSTION master enables flipped to default OFF. ICT 3-tier (atoms → category composites → Mode A/B/C gates) is the SOLE entry-gating substrate. CVCSM ICT-substrate redesign (Paths A/B/C from clash analysis) explored but **operator chose to retire CVCSM entirely** — the clash analysis showed CVCSM-on-ICT-substrate adds value only via asymmetric thresholds (per §7), and operator chose simplicity: trust the ICT entry-gate alone. Code preserved for forensics; v2.7.130 code-deletion follow-up scheduled. Design rationale captured in [`docs/FORGE_PEMCG_CVCSM_LESSONS_LEARNED.md`](FORGE_PEMCG_CVCSM_LESSONS_LEARNED.md). Mode D matches `§7` original "PEMCG OFF entirely" definition. Mode T (PEMCG-as-telemetry) was an intermediate operator framing that got escalated to full Mode D.
