//+------------------------------------------------------------------+
//| Forge\IctOrderBlock.mqh                                          |
//| FORGE v2.7.133 — ICT order-block + breaker module (Phase 3 body) |
//| See docs/FORGE_SETUP_ICT_MAP.md §B.2 (BREAKER_RETEST category).   |
//+------------------------------------------------------------------+
#ifndef __FORGE_ICT_ORDER_BLOCK_MQH__
#define __FORGE_ICT_ORDER_BLOCK_MQH__

// ─────────────────────────────────────────────────────────────────────────────
// PURPOSE (Phase 3 — v2.7.133)
//   Implements minimal viable Order Block + Breaker Block detection to unblock
//   the 4th ICT category composite (BREAKER_RETEST). The category was returning
//   0 from ComputeCategoryScore() — this module provides the missing atom
//   inputs so Mode A logging populates `composite_breaker_retest_score_*`.
//
// ICT CANON (per WebSearch 2026-05-17)
//   - Order Block: last opposite-direction candle BEFORE a displacement leg.
//     Bullish OB = last bearish candle before a strong bullish push that
//     leaves a Fair Value Gap within the next few bars. Bearish OB mirrors.
//     Sources:
//       https://innercircletrader.net/tutorials/ict-order-block/
//       https://www.luxalgo.com/blog/ict-trader-concepts-order-blocks-unpacked/
//       https://atas.net/blog/what-are-ict-order-blocks-and-breaker-blocks-in-trading/
//
//   - Breaker Block: a FAILED OB. Price body-closed past the OB extreme;
//     the OB now acts as opposite-direction S/R on retest. Distinct from
//     a Mitigation Block (OB held → trend continuation), the Breaker is
//     the trigger for trend-REVERSAL trades. Source:
//       https://innercircletrader.net/tutorials/ict-breaker-block-trading/
//
// MINIMAL VIABLE SCOPE (v2.7.133)
//   1. Detect OBs from displacement-leg + previous-opposite-candle pattern
//   2. Maintain ring buffer of 16 active OBs (same shape as g_fvg_ring)
//   3. Track per-OB broken state (body close past extreme)
//   4. Track per-OB breaker-retest state (price within tolerance of broken
//      OB level)
//   5. Export g_ict_last_breaker_* globals for atom evaluators in
//      IctScoring.mqh
//
// DEFERRED to Phase 3b
//   - Hidden order blocks (no immediate FVG required)
//   - Mitigation block tracking (held OB on retest — continuation trade)
//   - PD-array confluence scoring (OB ∩ FVG ∩ Breaker ∩ RDRB ∩ liquidity)
//   - Premium/Discount + Equilibrium helpers (Get Dealing Range, etc.)
//
// DEPENDENCIES
//   - <Forge\IctStructure.mqh> — uses FVG ring (g_fvg_ring) to verify the
//     post-OB displacement leaves an FVG, per ICT-canon validation rule.
//
// CHANGELOG
//   v2.7.133  full body — 5 helpers + ring buffer + global exports
//   v2.7.118  scaffold (file path reserved)
// ─────────────────────────────────────────────────────────────────────────────

// ─── OB ring struct + globals ──────────────────────────────────────────────

struct OrderBlockZone {
   datetime time;                 // M5 bar time of the OB candle
   double   high;                 // OB high (resistance for bullish OB once broken)
   double   low;                  // OB low (support for bearish OB once broken)
   double   midpoint;             // (high + low) / 2 — OB equilibrium
   bool     bullish;              // true = bullish OB (last bearish before bull push)
   bool     broken;               // body close past extreme → became a Breaker Block
   bool     breaker_active;       // broken AND price currently retesting from opposite side
   bool     mitigated;            // fully retraced through the OB (>= midpoint)
   int      sourceBar;            // shift of the OB candle when detected
   double   displacementAtr;      // body / ATR ratio of the displacement candle
   datetime expiry;               // age-cap timestamp
};

OrderBlockZone g_ob_ring[16];
int            g_ob_ring_count = 0;

// ─── Module-exported globals for atom evaluators ───────────────────────────

int    g_ict_last_atom_ob_broken        = 0;   // 1 if any OB in ring is broken (canonical name per §B.8.2 Cat 4)
int    g_ict_last_atom_ob_confluence_buy  = 0; // v2.7.136 — Cat 2 OTE_RETRACE atom: active OB aligned with BUY direction near price
int    g_ict_last_atom_ob_confluence_sell = 0; // v2.7.136 — Cat 2 OTE_RETRACE atom: active OB aligned with SELL direction near price
int    g_ict_last_breaker_retest_buy    = 0;   // 1 if broken bearish OB retesting (BUY trigger)
int    g_ict_last_breaker_retest_sell   = 0;   // 1 if broken bullish OB retesting (SELL trigger)
double g_ict_last_breaker_level         = 0.0; // price level being retested
int    g_ict_last_breaker_fvg_buy       = 0;   // 1 if bullish FVG aligns with bearish-OB breaker retest
int    g_ict_last_breaker_fvg_sell      = 0;   // 1 if bearish FVG aligns with bullish-OB breaker retest

// ─── Detection ──────────────────────────────────────────────────────────────

//+------------------------------------------------------------------+
//| Forge_DetectOrderBlocks                                          |
//| PURPOSE   : Scan M5 history for OB candidates, populate ring.    |
//|             Per ICT canon: OB = last opposite-color candle       |
//|             before a displacement leg that leaves an FVG.        |
//| PARAMETERS:                                                      |
//|   atr                  — current M5 ATR (for displacement gate)  |
//|   displacement_min_atr — min body/ATR ratio to qualify (1.5)     |
//|   lookback_bars        — how far back to scan (50)               |
//| RETURNS  : count of OBs in ring after rebuild                    |
//+------------------------------------------------------------------+
int Forge_DetectOrderBlocks(double atr, double displacement_min_atr, int lookback_bars) {
   if(atr <= 0.0) return g_ob_ring_count;
   if(lookback_bars < 5)   lookback_bars = 5;
   if(lookback_bars > 100) lookback_bars = 100;

   g_ob_ring_count = 0;
   datetime now_t = TimeCurrent();
   int      max_age_sec = 60 * 60 * 6;   // 6h M5 OB lifespan

   // v2.7.137 R24 fix — scan NEWEST→OLDEST so the 16-slot ring keeps the most-recent
   // OBs when more than 16 candidates exist in the lookback window. The previous
   // OLDEST→NEWEST direction silently retained the most stale OBs in fast markets,
   // which is exactly where breaker/retest atoms need fresh structure.
   for(int i = 3; i <= lookback_bars; i++) {
      if(g_ob_ring_count >= 16) break;

      double o_disp = iOpen (_Symbol, PERIOD_M5, i);
      double c_disp = iClose(_Symbol, PERIOD_M5, i);
      double body   = MathAbs(c_disp - o_disp);
      if(body < displacement_min_atr * atr) continue;

      bool   disp_bullish = (c_disp > o_disp);
      int    ob_shift = i + 1;
      double o_ob = iOpen (_Symbol, PERIOD_M5, ob_shift);
      double c_ob = iClose(_Symbol, PERIOD_M5, ob_shift);
      bool   ob_bullish_color = (c_ob > o_ob);

      bool ob_is_bullish;
      if(disp_bullish && !ob_bullish_color)      ob_is_bullish = true;
      else if(!disp_bullish && ob_bullish_color) ob_is_bullish = false;
      else continue;

      // FVG confirmation: canonical 3-bar gap between i-1 and i+1
      double h_after  = iHigh(_Symbol, PERIOD_M5, i - 1);
      double l_after  = iLow (_Symbol, PERIOD_M5, i - 1);
      double h_before = iHigh(_Symbol, PERIOD_M5, i + 1);
      double l_before = iLow (_Symbol, PERIOD_M5, i + 1);
      bool fvg_ok;
      if(ob_is_bullish) fvg_ok = (l_after > h_before);
      else              fvg_ok = (h_after < l_before);
      if(!fvg_ok) continue;

      int n = g_ob_ring_count;
      g_ob_ring[n].time            = (datetime)iTime(_Symbol, PERIOD_M5, ob_shift);
      g_ob_ring[n].high            = iHigh(_Symbol, PERIOD_M5, ob_shift);
      g_ob_ring[n].low             = iLow (_Symbol, PERIOD_M5, ob_shift);
      g_ob_ring[n].midpoint        = (g_ob_ring[n].high + g_ob_ring[n].low) / 2.0;
      g_ob_ring[n].bullish         = ob_is_bullish;
      g_ob_ring[n].broken          = false;
      g_ob_ring[n].breaker_active  = false;
      g_ob_ring[n].mitigated       = false;
      g_ob_ring[n].sourceBar       = ob_shift;
      g_ob_ring[n].displacementAtr = (atr > 0.0) ? (body / atr) : 0.0;
      g_ob_ring[n].expiry          = now_t + max_age_sec;
      g_ob_ring_count++;
   }
   return g_ob_ring_count;
}

//+------------------------------------------------------------------+
//| Forge_UpdateOBBrokenState                                         |
//| Mark broken=true on any OB whose extreme has been body-closed     |
//| past by a subsequent bar.                                         |
//+------------------------------------------------------------------+
void Forge_UpdateOBBrokenState() {
   for(int idx = 0; idx < g_ob_ring_count; idx++) {
      if(g_ob_ring[idx].broken) continue;
      int from_shift = g_ob_ring[idx].sourceBar - 1;
      if(from_shift < 0) continue;
      for(int bs = from_shift; bs >= 0; bs--) {
         double c = iClose(_Symbol, PERIOD_M5, bs);
         if(g_ob_ring[idx].bullish && c < g_ob_ring[idx].low) {
            g_ob_ring[idx].broken = true;
            break;
         }
         if(!g_ob_ring[idx].bullish && c > g_ob_ring[idx].high) {
            g_ob_ring[idx].broken = true;
            break;
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Forge_UpdateBreakerRetestState                                    |
//| For broken OBs, set breaker_active=true if current price is       |
//| within tolerance × ATR of the now-flipped S/R level.              |
//+------------------------------------------------------------------+
void Forge_UpdateBreakerRetestState(double atr, double retest_tolerance_atr) {
   g_ict_last_breaker_retest_buy  = 0;
   g_ict_last_breaker_retest_sell = 0;
   g_ict_last_breaker_level       = 0.0;
   if(atr <= 0.0) return;
   double tol = retest_tolerance_atr * atr;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double mid = (bid + ask) / 2.0;

   for(int idx = 0; idx < g_ob_ring_count; idx++) {
      g_ob_ring[idx].breaker_active = false;
      if(!g_ob_ring[idx].broken) continue;
      if(g_ob_ring[idx].bullish) {
         // failed bullish OB → now resistance at OB.low
         double level = g_ob_ring[idx].low;
         if(MathAbs(mid - level) <= tol) {
            g_ob_ring[idx].breaker_active = true;
            g_ict_last_breaker_retest_sell = 1;
            g_ict_last_breaker_level = level;
         }
      } else {
         // failed bearish OB → now support at OB.high
         double level = g_ob_ring[idx].high;
         if(MathAbs(mid - level) <= tol) {
            g_ob_ring[idx].breaker_active = true;
            g_ict_last_breaker_retest_buy = 1;
            g_ict_last_breaker_level = level;
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Forge_UpdateBreakerFVGConfluence                                  |
//| Set the breaker-FVG-confluence atoms (BUY/SELL) when an active    |
//| breaker has a direction-aligned FVG within tolerance × ATR.       |
//+------------------------------------------------------------------+
void Forge_UpdateBreakerFVGConfluence(double atr, double confluence_tolerance_atr) {
   g_ict_last_breaker_fvg_buy  = 0;
   g_ict_last_breaker_fvg_sell = 0;
   if(atr <= 0.0) return;
   double tol = confluence_tolerance_atr * atr;

   for(int idx = 0; idx < g_ob_ring_count; idx++) {
      if(!g_ob_ring[idx].breaker_active) continue;
      double ob_level = g_ob_ring[idx].bullish ? g_ob_ring[idx].low : g_ob_ring[idx].high;
      bool need_bullish_fvg = !g_ob_ring[idx].bullish;
      for(int j = 0; j < g_fvg_ring_count; j++) {
         if(g_fvg_ring[j].mitigated) continue;
         if(g_fvg_ring[j].bullish != need_bullish_fvg) continue;
         if(MathAbs(g_fvg_ring[j].midpoint - ob_level) > tol) continue;
         if(need_bullish_fvg) g_ict_last_breaker_fvg_buy  = 1;
         else                 g_ict_last_breaker_fvg_sell = 1;
         break;
      }
   }
}

//+------------------------------------------------------------------+
//| Forge_RebuildOBRing                                               |
//| One-call orchestrator: detect → broken → retest → FVG confluence. |
//| Called from chokepoint each tick alongside the FVG ring rebuild.  |
//+------------------------------------------------------------------+
void Forge_RebuildOBRing(double atr,
                         double displacement_min_atr,
                         int    lookback_bars,
                         double retest_tolerance_atr,
                         double fvg_confluence_tolerance_atr) {
   Forge_DetectOrderBlocks(atr, displacement_min_atr, lookback_bars);
   Forge_UpdateOBBrokenState();
   Forge_UpdateBreakerRetestState(atr, retest_tolerance_atr);
   Forge_UpdateBreakerFVGConfluence(atr, fvg_confluence_tolerance_atr);

   int broken_count = 0;
   for(int idx = 0; idx < g_ob_ring_count; idx++) {
      if(g_ob_ring[idx].broken) broken_count++;
   }
   g_ict_last_atom_ob_broken = (broken_count > 0) ? 1 : 0;
}

//+------------------------------------------------------------------+
//| Forge_HasOBConfluence  (v2.7.136 — Cat 2 OTE_RETRACE atom)        |
//| PURPOSE: Return true if an active (non-broken, non-mitigated) OB  |
//|          exists in the trade direction near the current price.   |
//|          Per §B.8.2 Category 2 weight=1 atom marked "post-Phase 3"|
//|          — previously stubbed at score+=0 in IctScoring.mqh.     |
//| PARAMETERS:                                                      |
//|   direction      — +1 for BUY (looking for bullish OB),          |
//|                    -1 for SELL (looking for bearish OB)           |
//|   atr            — current M5 ATR                                |
//|   tolerance_atr  — proximity tolerance × ATR                      |
//+------------------------------------------------------------------+
bool Forge_HasOBConfluence(int direction, double atr, double tolerance_atr) {
   if(atr <= 0.0) return false;
   double tol = tolerance_atr * atr;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double mid = (bid + ask) / 2.0;
   for(int idx = 0; idx < g_ob_ring_count; idx++) {
      if(g_ob_ring[idx].broken)    continue;  // breaker — that's a Cat 4 atom, not Cat 2
      if(g_ob_ring[idx].mitigated) continue;
      bool dir_match = (direction == 1 && g_ob_ring[idx].bullish)
                    || (direction == -1 && !g_ob_ring[idx].bullish);
      if(!dir_match) continue;
      // "Near" = price within tolerance band around the OB zone
      if(mid >= (g_ob_ring[idx].low - tol) && mid <= (g_ob_ring[idx].high + tol)) {
         return true;
      }
   }
   return false;
}

#endif // __FORGE_ICT_ORDER_BLOCK_MQH__
