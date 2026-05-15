//+------------------------------------------------------------------+
//| Forge\IctOrderBlock.mqh                                          |
//| FORGE v2.7.120 (planned) — ICT order-block + breaker module      |
//+------------------------------------------------------------------+
#ifndef __FORGE_ICT_ORDER_BLOCK_MQH__
#define __FORGE_ICT_ORDER_BLOCK_MQH__

// PURPOSE (Phase 3 — v2.7.120, not yet shipped)
//   Order Block (OB) detection — last opposite candle before displacement.
//   Hidden OB logic. OB strength scoring + mitigation tracking + invalidation.
//   Breaker Block — failed OB that becomes support/resistance on retest.
//   Premium / Discount + PD-array confluence (FVG ∩ OB ∩ Breaker ∩ RDRB ∩
//   liquidity pool).
//
// DEPENDENCIES
//   - <Forge\IctStructure.mqh>: swing-pivot ring (for displacement detection)
//   - <Forge\IctLiquidity.mqh>: ChoCH/sweep context (for breaker validity)
//
// PLANNED EXPORTS
//   - struct OrderBlockZone { ... high, low, midpoint, bullish, mitigated,
//     invalidated, sourceBar, strengthScore ... }
//   - DetectBullishOrderBlock / DetectBearishOrderBlock
//   - DetectHiddenOrderBlock
//   - IsOrderBlockMitigated / IsOrderBlockInvalidated / ScoreOrderBlock
//   - DetectBullishBreakerBlock / DetectBearishBreakerBlock
//   - IsValidBreakerBlock / ScoreBreakerBlock
//   - GetDealingRange / IsInPremium / IsInDiscount / GetEquilibrium
//   - ScorePDArrayConfluence
//
// STATUS
//   Scaffold only (v2.7.118 ship). Empty include guard so the Wine sync
//   pipeline picks up the file path. FORGE.mq5 does NOT #include this file
//   yet — that line lands in v2.7.120 alongside the function bodies.
//
// CHANGELOG
//   2026-05-14  v2.7.118 scaffold (file path reserved; module body deferred).
//+------------------------------------------------------------------+

// (intentionally empty — implementation lands in v2.7.120 Phase 3)

#endif // __FORGE_ICT_ORDER_BLOCK_MQH__
