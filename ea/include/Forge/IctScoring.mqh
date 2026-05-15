//+------------------------------------------------------------------+
//| Forge\IctScoring.mqh                                             |
//| FORGE v2.7.123 — ICT atom + scoring engine                       |
//+------------------------------------------------------------------+
#ifndef __FORGE_ICT_SCORING_MQH__
#define __FORGE_ICT_SCORING_MQH__

// ─────────────────────────────────────────────────────────────────────────────
// PURPOSE
//   Phase A (v2.7.123 — this ship): 3 of the 5 atoms feeding §B.8.2 weighted
//   composite scoring. Compute + log only (Mode A) — zero trade-flow impact.
//   Atoms compute per-direction (caller-supplied direction parameter). The
//   per-tick eval hook in FORGE.mq5 stores the BUY-context value into 5 global
//   integers (g_ict_last_atom_*) for SIGNALS logging. The Phase B composite
//   scorer (not yet shipped) will call the functions per-direction directly
//   without going through the globals.
//
//   Phase 4 (v2.7.121-planned — deferred): Unicorn Model + master ICTSignalScore
//   struct + ScoreUnicornSetup + ScoreICTBuySetup / ScoreICTSellSetup +
//   IsHighProbabilityICTSetup + ISS-C continuation composite + Mode C PEMCG
//   override hook (FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED).
//
// DEPENDENCIES
//   - <Forge\IctStructure.mqh>: g_swing_highs[], g_swing_lows[],
//     Forge_GetActiveFVGAlignedWith(direction, price, out)
//   - <Forge\IctLiquidity.mqh>: GetSessionContext, kill-zone helpers (Phase 2)
//   - FORGE.mq5 globals: g_regime (RegimeState struct) — killzone + htf_label +
//     h1_trend strength fields are read directly.
//
// EXPORTS
//   Globals (module-owned, read by JournalRecordSignal at the SIGNALS chokepoint):
//     g_ict_last_atom_killzone_favorable
//     g_ict_last_atom_htf_aligned
//     g_ict_last_atom_pullback_in_ote
//     g_ict_last_atom_premium_discount_aligned
//     g_ict_last_atom_fvg_on_reversal_leg
//   Functions (Phase A — this ship):
//     Atom_KillzoneFavorable(category, direction)
//     Atom_HTFAligned(direction)
//     Atom_FVGOnReversalLeg(direction)
//   Functions (in IctStructure.mqh — uses swing arrays already there):
//     Atom_PullbackInOTE(direction)
//     Atom_PremiumDiscountAligned(direction)
//
// CATEGORY ENUM (per docs/FORGE_SETUP_ICT_MAP.md §B.2)
//   1 = MSS_CONT          (continuation after MSS)
//   2 = OTE_RETRACE       (optimal trade entry retracement)
//   3 = LIQ_SWEEP_REV     (liquidity sweep reversal)
//   4 = BREAKER_RETEST    (breaker block retest)
//
// DIRECTION CONVENTION
//   1 = BUY, -1 = SELL (matches §B.8.2 composite scorer signature).
//
// PHASE A WIRE-UP STATUS
//   - FORGE.mq5 #includes <Forge\IctScoring.mqh> at the same point as
//     IctStructure.mqh / IctLiquidity.mqh.
//   - Per-tick eval hook in ForgeEvalAtoms() reads the 5 enable flags from
//     ScalperConfig and stores the BUY-direction result into the globals.
//   - JournalRecordSignal binds the 5 globals into the SIGNALS row for every
//     emitted record (TAKEN or SKIP). All zero with default flags OFF.
//
// CHANGELOG
//   2026-05-14  v2.7.118 scaffold (file path reserved; module body deferred).
//   2026-05-15  v2.7.123 Phase A ship — 5 atoms behind individual enable flags.
//               Functions for atoms 1/2/5 live here; atoms 3/4 live in
//               IctStructure.mqh (they use the swing arrays already there).
//+------------------------------------------------------------------+

// ─── Module globals (read by FORGE.mq5 / JournalRecordSignal) ───────────────
//
//   Per-tick computed integer flags (0 or 1) — populated by ForgeEvalAtoms()
//   in FORGE.mq5 by calling the Atom_* functions with direction=BUY (1).
//   When the corresponding enable flag is off, the eval hook zeroes the global
//   so SIGNALS rows log 0 — schema-parity byte-stable.
int g_ict_last_atom_killzone_favorable       = 0;
int g_ict_last_atom_htf_aligned              = 0;
int g_ict_last_atom_pullback_in_ote          = 0;
int g_ict_last_atom_premium_discount_aligned = 0;
int g_ict_last_atom_fvg_on_reversal_leg      = 0;

// ─────────────────────────────────────────────────────────────────────────────
// Atom_KillzoneFavorable — shared across all 4 ICT setup categories.
//
// PURPOSE
//   Phase A atom #1. Returns true iff the current g_regime.killzone string
//   falls inside the category's favored kill-zone set. Killzones are the prime
//   windows for setup confluence (time + price + structure). Per §B.2 each
//   category has its own favored set:
//     1 MSS_CONT       : LONDON_OPEN_KZ + NY_OPEN_KZ
//     2 OTE_RETRACE    : any non-empty KZ (any active session)
//     3 LIQ_SWEEP_REV  : LONDON_OPEN_KZ + LONDON_CLOSE_KZ (NY_PM proxy)
//     4 BREAKER_RETEST : any non-empty KZ
//   The g_regime.killzone field is the single source of truth populated each
//   tick by RegimeUpdate() (see §B.7). Reads via the global directly — no
//   recomputation per-tick.
//
// PARAMETERS
//   category   — 1=MSS_CONT, 2=OTE_RETRACE, 3=LIQ_SWEEP_REV, 4=BREAKER_RETEST
//   direction  — 1=BUY, -1=SELL (currently unused; reserved for future
//                directional kill-zone bias — e.g. London Close BUY-only)
//
// RETURNS
//   true iff g_regime.killzone is in the favored set for the category.
//
// CITATION
//   "ICT killzones are the prime windows for setup confluence: time + price +
//    structure. MSS after liquidity sweep in a killzone is the foundational
//    high-probability signal."
//   — innercircletrader.net/tutorials/master-ict-kill-zones
//
// CHANGELOG
//   2026-05-15  v2.7.123 Phase A ship.
// ─────────────────────────────────────────────────────────────────────────────
bool Atom_KillzoneFavorable(int category, int direction)
{
   // Suppress unused-parameter warning until directional bias ships.
   if(direction == 0) return false;
   string kz = g_regime.killzone;
   if(StringLen(kz) == 0) return false;  // outside any KZ → never favorable
   if(category == 1) {
      // MSS_CONT: London Open + NY AM (the canonical institutional MSS windows)
      return (kz == "LONDON_OPEN_KZ" || kz == "NY_OPEN_KZ");
   }
   if(category == 2) {
      // OTE_RETRACE: any active KZ (retracement-into-zone is valid all-session)
      return true;  // kz already non-empty per guard above
   }
   if(category == 3) {
      // LIQ_SWEEP_REV: London Open + London Close (proxy for NY_PM until §B.7
      // NY_PM_KZ ships). Liquidity sweeps cluster at session boundaries.
      return (kz == "LONDON_OPEN_KZ" || kz == "LONDON_CLOSE_KZ");
   }
   if(category == 4) {
      // BREAKER_RETEST: any active KZ (retests can fire in any session window)
      return true;
   }
   return false;  // unknown category
}

// ─────────────────────────────────────────────────────────────────────────────
// Atom_HTFAligned — shared atom (MSS_CONT, OTE_RETRACE, BREAKER_RETEST).
//
// PURPOSE
//   Phase A atom #2. Returns true iff the trade direction aligns with the
//   higher-time-frame bias. Two paths to "aligned":
//     (a) g_regime.htf_label contains "BULL" (BUY) / "BEAR" (SELL), OR
//     (b) raw h1 trend strength clears the ±0.5 threshold.
//   Either path is sufficient. Per §B.8.5 this atom is NOT used by
//   LIQ_SWEEP_REV (sweep reversals are counter-bias by design).
//
// PARAMETERS
//   direction  — 1=BUY, -1=SELL
//
// RETURNS
//   true iff HTF context supports the trade direction.
//
// CITATION
//   "Trade only in direction of HTF bias unless confirmed MSS. Counter-bias
//    trades at most fractional sizing."
//   — tradeciety.com/multiple-time-frame-analysis
//
// CHANGELOG
//   2026-05-15  v2.7.123 Phase A ship.
// ─────────────────────────────────────────────────────────────────────────────
bool Atom_HTFAligned(int direction)
{
   string htf = g_regime.htf_label;
   // h1 trend strength — the legacy double populated by ForgeEvalAtoms (see
   // g_eval_h1_trend at the top of FORGE.mq5). Mirrored into g_regime via
   // RegimeUpdate(). Threshold ±0.5 matches the rest of the codebase
   // (dirlock_h1_disagreement etc).
   double h1 = g_eval_h1_trend;
   if(direction > 0) {
      // BUY — HTF must say BULL or h1_trend strongly positive
      if(StringFind(htf, "BULL") >= 0) return true;
      if(h1 >  0.5) return true;
      return false;
   }
   if(direction < 0) {
      // SELL — HTF must say BEAR or h1_trend strongly negative
      if(StringFind(htf, "BEAR") >= 0) return true;
      if(h1 < -0.5) return true;
      return false;
   }
   return false;
}

// ─────────────────────────────────────────────────────────────────────────────
// Atom_FVGOnReversalLeg — LIQ_SWEEP_REV atom (direction-aligned FVG presence).
//
// PURPOSE
//   Phase A atom #5. After a liquidity sweep + MSS the canonical ICT entry is a
//   retrace into the FVG on the reversal leg. For Phase A this atom is
//   simplified: it wraps the existing Forge_GetActiveFVGAlignedWith(direction)
//   lookup from IctStructure.mqh. Phase B's LIQ_SWEEP_REV composite will
//   combine this with the existing sweep + ChoCH atoms for full directional
//   context.
//
// PARAMETERS
//   direction  — 1=BUY, -1=SELL
//
// RETURNS
//   true iff an active FVG aligned with the direction exists in the ring
//   buffer AND the current bid/ask price sits inside its zone.
//
// CITATION
//   "After MSS (post-sweep), price retraces into an FVG or Order Block,
//    providing the entry opportunity. The FVG on the reversal leg is where
//    smart money fills."
//   — threads.com/@ict_smc_chartist/post/DH-UJkhsf3p
//
// CHANGELOG
//   2026-05-15  v2.7.123 Phase A ship — Mode A simplification.
//               Phase B will pair this with sweep+ChoCH for full setup logic.
// ─────────────────────────────────────────────────────────────────────────────
bool Atom_FVGOnReversalLeg(int direction)
{
   if(direction == 0) return false;
   string dir_str = (direction > 0) ? "BUY" : "SELL";
   // BUY uses bid (entry on the offered side); SELL uses ask. Matches the
   // chokepoint price reference used by the existing ICT FVG atom.
   double px = (direction > 0)
                  ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                  : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(px <= 0.0) return false;
   FVGZone out;
   return Forge_GetActiveFVGAlignedWith(dir_str, px, out);
}

#endif // __FORGE_ICT_SCORING_MQH__
