//+------------------------------------------------------------------+
//| Forge\IctIntradayModel.mqh                                       |
//| FORGE v2.7.122 (planned) — ICT intraday + CRT + Venom + B&B + SDF|
//+------------------------------------------------------------------+
#ifndef __FORGE_ICT_INTRADAY_MODEL_MQH__
#define __FORGE_ICT_INTRADAY_MODEL_MQH__

// PURPOSE (Phase 5 — v2.7.122, not yet shipped)
//   Candle Range Theory (CRT): range high/low, manipulation outside range,
//     reclaim of range, expansion away from range. Session candle range
//     bias (Asian range / daily / weekly).
//   Venom Model — 2025 ICT intraday model.
//   Bread and Butter setup (buy + sell variants).
//   Redelivered / Rebalanced Price Range (RDRB).
//   Institutional Order Flow entry drill.
//   Seek and Destroy Friday logic — Friday-specific session manipulation.
//
// DEPENDENCIES
//   - <Forge\IctStructure.mqh>: swing + MSS + FVG
//   - <Forge\IctLiquidity.mqh>: ChoCH + sweep + session
//   - <Forge\IctOrderBlock.mqh>: OB + breaker + PD-array
//   - <Forge\IctScoring.mqh>: master ICTSignalScore struct
//
// PLANNED EXPORTS
//   - DetectCRTRange / DetectCRTManipulation / DetectCRTReclaim /
//     ScoreCRTSetup
//   - DetectVenomBullSetup / DetectVenomBearSetup
//   - DetectBreadButterBuySetup / DetectBreadButterSellSetup
//   - DetectRDRBZone / IsInRDRBContext
//   - DetectSeekAndDestroyFridayPattern
//   - DetectInstitutionalOrderFlowEntry
//
// STATUS
//   Scaffold only (v2.7.118 ship). Empty include guard so the Wine sync
//   pipeline picks up the file path. FORGE.mq5 does NOT #include this file
//   yet — that line lands in v2.7.122 alongside the function bodies.
//
// CHANGELOG
//   2026-05-14  v2.7.118 scaffold (file path reserved; module body deferred).
//+------------------------------------------------------------------+

// (intentionally empty — implementation lands in v2.7.122 Phase 5)

#endif // __FORGE_ICT_INTRADAY_MODEL_MQH__
