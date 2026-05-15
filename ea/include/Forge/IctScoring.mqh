//+------------------------------------------------------------------+
//| Forge\IctScoring.mqh                                             |
//| FORGE v2.7.121 (planned) — ICT unicorn + master scoring engine   |
//+------------------------------------------------------------------+
#ifndef __FORGE_ICT_SCORING_MQH__
#define __FORGE_ICT_SCORING_MQH__

// PURPOSE (Phase 4 — v2.7.121, not yet shipped)
//   Unicorn Model — liquidity sweep + MSS/ChoCH + FVG + breaker overlap +
//   entry from FVG/breaker confluence + kill-zone preference.
//   ICTSignalScore master struct (operator spec § K):
//     liquidityScore + structureScore + fvgScore + sessionScore +
//     pdArrayScore + orderBlockScore → totalScore, tradeAllowed.
//   ISS-C continuation composite (regime + h1 + m5_adx + m15_adx + vwap +
//   psar + bar-quality + prev-bar hard gate) — wires to the existing
//   FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED knob to enable Mode C of the
//   PEMCG↔ICT integration spec.
//
// DEPENDENCIES
//   - <Forge\IctStructure.mqh>: MSS + FVG atoms
//   - <Forge\IctLiquidity.mqh>: ChoCH + sweep + kill-zone
//   - <Forge\IctOrderBlock.mqh>: OB + breaker + PD-array
//
// PLANNED EXPORTS
//   - struct ICTSignalScore { ... }
//   - DetectBullishUnicornSetup / DetectBearishUnicornSetup
//   - ScoreUnicornSetup
//   - ScoreICTBuySetup / ScoreICTSellSetup
//   - IsHighProbabilityICTSetup
//   - ComputeIssCBuy / ComputeIssCSell — Mode C override composite
//
// WIRES INTO
//   - FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED (default 0; reservation
//     knob already in .env + sync mapping per v2.7.118 ship)
//   - The setup-trigger chokepoint at ea/FORGE.mq5:13620-13705 (adds ISS-C
//     evaluation before / overriding the existing PEMCG block)
//
// STATUS
//   Scaffold only (v2.7.118 ship). Empty include guard so the Wine sync
//   pipeline picks up the file path. FORGE.mq5 does NOT #include this file
//   yet — that line lands in v2.7.121 alongside the function bodies.
//
// CHANGELOG
//   2026-05-14  v2.7.118 scaffold (file path reserved; module body deferred).
//+------------------------------------------------------------------+

// (intentionally empty — implementation lands in v2.7.121 Phase 4)

#endif // __FORGE_ICT_SCORING_MQH__
