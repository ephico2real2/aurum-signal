//+------------------------------------------------------------------+
//| Forge\IctLiquidity.mqh                                           |
//| FORGE v2.7.119 (planned) — ICT liquidity + ChoCH module          |
//+------------------------------------------------------------------+
#ifndef __FORGE_ICT_LIQUIDITY_MQH__
#define __FORGE_ICT_LIQUIDITY_MQH__

// PURPOSE (Phase 2 — v2.7.119, not yet shipped)
//   ChoCH (Change of Character) detection — early reversal clue, separate
//   from full MSS. Buy-side / sell-side liquidity sweep detection. Equal
//   highs / equal lows tracking. Session-anchored sweep (Asian range,
//   London / NY session high+low). Sweep-followed-by-rejection-candle
//   composite. Kill-zone extensions (Silver Bullet windows).
//
// DEPENDENCIES
//   - <Forge\IctStructure.mqh>: g_swing_highs[], g_swing_lows[], FVGZone
//     (for sweep + ChoCH + FVG confluence scoring)
//
// PLANNED EXPORTS
//   - struct LiquidityPool { datetime time; double level; bool buy_side; ... }
//   - DetectBullishChOCh / DetectBearishChOCh
//   - DetectInternalStructureShift / DetectExternalStructureShift
//   - DetectBuySideLiquiditySweep / DetectSellSideLiquiditySweep
//   - DetectEqualHighs / DetectEqualLows
//   - DetectSweepRejection / ScoreLiquiditySweep
//   - IsInLondonKillZone / IsInNewYorkKillZone / IsInKillZone /
//     GetSessionContext
//
// WIRES INTO
//   - g_iss_choch_support (currently stub 0 in v2.7.118)
//   - g_iss_choch_against (HARD GATE when true — already wired at
//     ea/FORGE.mq5:13671)
//
// STATUS
//   Scaffold only (v2.7.118 ship). Empty include guard so the Wine sync
//   pipeline at scripts/compile_forge_ea_macos.sh picks up the file path
//   alongside IctStructure.mqh. FORGE.mq5 does NOT #include this file yet —
//   that line lands in v2.7.119 alongside the function bodies.
//
// CHANGELOG
//   2026-05-14  v2.7.118 scaffold (file path reserved; module body deferred).
//+------------------------------------------------------------------+

// (intentionally empty — implementation lands in v2.7.119 Phase 2)

#endif // __FORGE_ICT_LIQUIDITY_MQH__
