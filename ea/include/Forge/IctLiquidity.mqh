//+------------------------------------------------------------------+
//| Forge\IctLiquidity.mqh                                            |
//| FORGE v2.7.120 — ICT liquidity + ChoCH + Kill Zone module         |
//| Phase 2 of the ICT integration (second modular FORGE component).  |
//| See docs/MQL5_MODULAR_EA_DESIGN.md for include layout + rules.    |
//+------------------------------------------------------------------+
#ifndef __FORGE_ICT_LIQUIDITY_MQH__
#define __FORGE_ICT_LIQUIDITY_MQH__

// ─────────────────────────────────────────────────────────────────────────────
// PURPOSE  (Phase 2 — v2.7.120)
//   1. ChoCH (Change of Character) — early reversal clue. Internal swing break
//      with displacement. Distinct from MSS (external/major break).
//   2. Liquidity Sweep — buy-side / sell-side stop hunts: wick beyond a recent
//      equal-high/low cluster followed by a body close back inside.
//   3. Equal Highs / Equal Lows — pool detector. Cluster of swing extrema
//      within tolerance × ATR.
//   4. Kill Zones — session-context helpers anchored on UTC bar time. Builds
//      on the existing g_regime.killzone field; exposes per-window booleans
//      and the Silver Bullet 1h refinement.
//
//   Wires real values into the existing ISS atoms (g_iss_choch_support /
//   g_iss_choch_against — both stubbed at 0 in v2.7.118-119). With both
//   master flags OFF (FORGE_ICT_CHOCH_ENABLED=0,
//   FORGE_ICT_LIQUIDITY_SWEEP_ENABLED=0) behaviour is byte-identical to
//   v2.7.119.
//
// DEPENDENCIES
//   - <Forge\IctStructure.mqh>: IctSwingPoint, g_swing_highs[], g_swing_lows[]
//     are populated by the Phase 1 M5-close batch and consumed here.
//   - Standard MQL5 only (MathAbs / TimeCurrent / TimeToStruct etc).
//
// EXPORTS
//   Struct:  LiquidityPool
//   Globals: g_liquidity_pools[16], g_liquidity_pool_count
//            g_choch_buy_events / g_choch_sell_events (recent-event ring)
//            g_ict_last_choch_buy_count / *_sell_count / *_level
//            g_ict_last_liquidity_sweep_recent / *_sweep_level
//            g_ict_last_equal_highs_count / *_equal_lows_count
//            g_ict_last_sweep_rejection_score
//            g_ict_last_killzone_active / *_silver_bullet_active
//   Functions:
//     ChoCH:
//       DetectBullishChOCh / DetectBearishChOCh
//       DetectInternalStructureShift / DetectExternalStructureShift
//     Liquidity:
//       DetectBuySideLiquiditySweep / DetectSellSideLiquiditySweep
//       DetectEqualHighs / DetectEqualLows
//       DetectSweepRejection / ScoreLiquiditySweep
//       Forge_PushLiquidityPool / Forge_GetLatestLiquidityPool
//     Kill zones:
//       IsInLondonKillZone / IsInNewYorkKillZone
//       IsInSilverBulletWindow / IsInKillZone / GetSessionContext
//
// SEMANTIC NOTES (per docs/research/ICT_KILLZONES.md + docs/prompts/ICT_Tradingidea.md)
//   - All kill-zone times in UTC (matches g_regime.killzone source).
//   - London KZ:        07:00–10:00 UTC  (winter — 02:00–05:00 NY)
//   - NY AM KZ:         12:00–15:00 UTC  (winter — 07:00–10:00 NY)
//   - NY PM (London Close): 15:00–17:00 UTC  (winter — 10:00–12:00 NY)
//   - Silver Bullet windows: 10:00–11:00 UTC AND 14:00–15:00 UTC
//     (the 1h refinement inside each macro KZ where the AM SB lands).
//   - ASIAN / DEAD_ZONE returned from GetSessionContext outside the four
//     windows above.
//
// CHANGELOG
//   2026-05-14  v2.7.118 scaffold (file path reserved; body deferred).
//   2026-05-15  v2.7.120 Phase 2 ship — ChoCH + liquidity sweep + kill-zone
//               extensions. Default-OFF instrumentation. Lifts ISS score
//               ceiling 8 → 10 when both MSS + FVG + ChoCH_support fire.
//+------------------------------------------------------------------+

// ─── Structs ────────────────────────────────────────────────────────────────

struct LiquidityPool {
   datetime time;        // bar time when the pool was first detected
   double   level;       // price level (the equal-high / equal-low)
   bool     buy_side;    // true = buy-side liquidity (above price = swing highs)
                         // false = sell-side liquidity (below price = swing lows)
   bool     swept;       // true once a sweep (wick beyond + close back) is confirmed
   datetime swept_time;  // bar time the sweep occurred (0 until swept)
   int      cluster_size; // # of equal extrema that formed the pool (≥ 2)
};

// Light per-event records for ChoCH counters (recent window only).
struct ChoChEvent {
   datetime time;        // M5 bar time of the ChoCH fire
   double   level;       // swing level broken
   bool     bullish;     // true → bullish ChoCH (break of a recent swing high)
};

// ─── Module globals (read by FORGE.mq5 after include) ───────────────────────

LiquidityPool g_liquidity_pools[16];
int           g_liquidity_pool_count = 0;

ChoChEvent    g_choch_buy_events[16];   // bullish ChoCH ring
ChoChEvent    g_choch_sell_events[16];  // bearish ChoCH ring
int           g_choch_buy_count  = 0;
int           g_choch_sell_count = 0;

// v2.7.120 — Phase 2 atom-context capture for SIGNALS logging. Populated by
//   FORGE.mq5 at the M5-close batch (pools / sweeps / ChoCH events) and at the
//   setup-trigger chokepoint (counters / killzone). Read inline by
//   JournalRecordSignal so every emitted row carries the Phase 2 ICT context.
//   All zero by default — when both ict_choch_enabled and
//   ict_liquidity_sweep_enabled are 0, the values stay 0 and the schema-parity
//   invariant is byte-stable vs v2.7.119 defaults.
int    g_ict_last_choch_buy_count        = 0;   // recent bullish ChoCH events in lookback
int    g_ict_last_choch_sell_count       = 0;   // recent bearish ChoCH events in lookback
double g_ict_last_choch_level            = 0.0; // swing level broken by the most-recent ChoCH

int    g_ict_last_liquidity_sweep_recent = 0;   // 0/1 — sweep in last window N bars
double g_ict_last_sweep_level            = 0.0; // level that got swept
int    g_ict_last_equal_highs_count      = 0;   // cluster size of latest equal-highs pool
int    g_ict_last_equal_lows_count       = 0;   // cluster size of latest equal-lows pool
double g_ict_last_sweep_rejection_score  = 0.0; // 0..1 strength of rejection wick

int    g_ict_last_killzone_active        = 0;   // 0=DEAD/ASIAN, 1=LONDON, 2=NY_AM, 3=NY_PM, 4=LONDON_CLOSE
int    g_ict_last_silver_bullet_active   = 0;   // 0/1

// ─── Internal helpers ───────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// _PushLiquidityPool — append-with-FIFO-eviction for the pool ring.
//
// PURPOSE: Maintain a rolling 16-slot buffer of recent liquidity pools.
//   Phase 2 internal helper (module-private; callers use Forge_PushLiquidityPool
//   below which is identical but exposed for symmetry with Phase 1).
//
// PARAMETERS:
//   p  — LiquidityPool to insert
//
// SIDE EFFECTS: mutates g_liquidity_pools[] + g_liquidity_pool_count.
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
void _PushLiquidityPool(LiquidityPool &p)
{
   if(g_liquidity_pool_count >= 16) {
      for(int i = 0; i < 15; i++) g_liquidity_pools[i] = g_liquidity_pools[i + 1];
      g_liquidity_pool_count = 15;
   }
   g_liquidity_pools[g_liquidity_pool_count] = p;
   g_liquidity_pool_count++;
}

// Public wrapper — same body. Phase 1 used Forge_PushFVG / Forge_PushSwingHigh
// as the canonical insertion API; Phase 2 follows the same convention.
void Forge_PushLiquidityPool(LiquidityPool &p) { _PushLiquidityPool(p); }

// ─────────────────────────────────────────────────────────────────────────────
// _PushChoChEvent — append a ChoCH event to one of the two direction rings.
//
// PURPOSE: Track recent ChoCH fires so the chokepoint can read a count in
//   the configured lookback window (g_sc.ict_choch_lookback_bars).
//
// PARAMETERS:
//   bullish  — true → append to g_choch_buy_events; false → sell ring
//   t        — M5 bar time
//   level    — swing level broken
//
// SIDE EFFECTS: mutates the appropriate ring + counter.
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
void _PushChoChEvent(bool bullish, datetime t, double level)
{
   if(bullish) {
      if(g_choch_buy_count >= 16) {
         for(int i = 0; i < 15; i++) g_choch_buy_events[i] = g_choch_buy_events[i + 1];
         g_choch_buy_count = 15;
      }
      g_choch_buy_events[g_choch_buy_count].time    = t;
      g_choch_buy_events[g_choch_buy_count].level   = level;
      g_choch_buy_events[g_choch_buy_count].bullish = true;
      g_choch_buy_count++;
   } else {
      if(g_choch_sell_count >= 16) {
         for(int i = 0; i < 15; i++) g_choch_sell_events[i] = g_choch_sell_events[i + 1];
         g_choch_sell_count = 15;
      }
      g_choch_sell_events[g_choch_sell_count].time    = t;
      g_choch_sell_events[g_choch_sell_count].level   = level;
      g_choch_sell_events[g_choch_sell_count].bullish = false;
      g_choch_sell_count++;
   }
}

// ─── ChoCH detection ────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// DetectInternalStructureShift — break of a MINOR (recent / short-lookback) swing.
//
// PURPOSE: "Internal" structure = the 1-2 most-recent swings in the ring.
//   Used as the building block for ChoCH detection (ChoCH = an internal break
//   in the opposite direction of the prior trend leg).
//
// PARAMETERS:
//   m5_close     — current M5 bar close
//   swings_arr[] — IctSwingPoint array (g_swing_highs or g_swing_lows), oldest-first
//                  (Phase 1 push convention)
//   count        — number of valid entries in swings_arr
//   above        — true → testing close > swing.price (high-break)
//                  false → testing close < swing.price (low-break)
//   minor_lookback — how many of the most-recent N swings count as "internal"
//                    (1-2 per ICT canon; default 2)
//   out_level    — [out] the swing level that got broken (0 if no break)
//
// RETURNS: true iff `m5_close` body-breaks at least ONE of the most-recent
//   `minor_lookback` swings in the array.
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectInternalStructureShift(double m5_close, IctSwingPoint &swings_arr[], int count,
                                  bool above, int minor_lookback, double &out_level)
{
   out_level = 0.0;
   if(count <= 0 || minor_lookback < 1) return false;
   int start = count - 1;                   // newest entry index (oldest-first ring)
   int stop  = MathMax(0, count - minor_lookback);
   for(int i = start; i >= stop; i--) {
      double lvl = swings_arr[i].price;
      if(lvl <= 0.0) continue;
      if(above && m5_close > lvl)   { out_level = lvl; return true; }
      if(!above && m5_close < lvl)  { out_level = lvl; return true; }
   }
   return false;
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectExternalStructureShift — break of a MAJOR (older / long-lookback) swing.
//
// PURPOSE: "External" structure = swings further back in the ring (≥3 entries
//   ago). When an external swing breaks, it's a confirmed BOS / full MSS —
//   distinct from a ChoCH internal-only break.
//
// PARAMETERS:
//   m5_close       — current M5 bar close
//   swings_arr[]   — IctSwingPoint array (oldest-first)
//   count          — number of valid entries
//   above          — true → testing close > swing.price
//   external_start — how-many-back to start scanning (default 3; ICT canon:
//                    "the swing before the most-recent 1-2 minor ones")
//   out_level      — [out] swing level broken
//
// RETURNS: true iff m5_close body-breaks AT LEAST ONE swing whose index
//   is older than (count - external_start).
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectExternalStructureShift(double m5_close, IctSwingPoint &swings_arr[], int count,
                                  bool above, int external_start, double &out_level)
{
   out_level = 0.0;
   if(count <= 0 || external_start < 1) return false;
   int top = count - external_start;        // newest "external" index
   if(top < 0) return false;
   for(int i = top; i >= 0; i--) {
      double lvl = swings_arr[i].price;
      if(lvl <= 0.0) continue;
      if(above && m5_close > lvl)   { out_level = lvl; return true; }
      if(!above && m5_close < lvl)  { out_level = lvl; return true; }
   }
   return false;
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectBullishChOCh — bullish Change of Character.
//
// PURPOSE: Early reversal clue distinct from full BOS/MSS. Conditions
//   (per ICT canon and docs/prompts/ICT_Tradingidea.md §B):
//     1. Recent prior trend was DOWN — the most-recent swing low is still
//        intact (i.e. m5_close > recent_swing_low).
//     2. A recent MINOR swing high gets broken with displacement (body close
//        above the swing + sufficient body/ATR).
//
// PARAMETERS:
//   m5_close              — current M5 close
//   m5_open               — current M5 open (for displacement calc)
//   m5_atr                — M5 ATR(14)
//   swing_highs_arr[]     — IctSwingPoint array of swing highs (oldest-first)
//   highs_count           — # of valid entries
//   swing_lows_arr[]      — IctSwingPoint array of swing lows (oldest-first)
//   lows_count            — # of valid entries
//   minor_lookback        — internal lookback (default 2 per spec)
//   displacement_atr_mult — body/ATR displacement floor (default 0.5)
//   out_level             — [out] swing high broken
//
// RETURNS: true iff (a) prior swing low intact AND (b) minor swing high
//   broken with displacement.
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectBullishChOCh(double m5_close, double m5_open, double m5_atr,
                        IctSwingPoint &swing_highs_arr[], int highs_count,
                        IctSwingPoint &swing_lows_arr[],  int lows_count,
                        int minor_lookback, double displacement_atr_mult,
                        double &out_level)
{
   out_level = 0.0;
   if(m5_atr <= 0.0) return false;
   // (1) prior swing low must be intact (price still above it)
   if(lows_count <= 0) return false;
   double recent_low = swing_lows_arr[lows_count - 1].price;
   if(recent_low <= 0.0 || m5_close <= recent_low) return false;
   // (2) internal minor swing-high break with displacement
   double level = 0.0;
   if(!DetectInternalStructureShift(m5_close, swing_highs_arr, highs_count,
                                    true, minor_lookback, level)) return false;
   double body = MathAbs(m5_close - m5_open);
   if(body < displacement_atr_mult * m5_atr) return false;
   out_level = level;
   return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectBearishChOCh — mirror of DetectBullishChOCh.
//
// PURPOSE: Bearish ChoCH — prior swing high still intact, recent minor
//   swing low body-broken with displacement.
//
// PARAMETERS: see DetectBullishChOCh — arrays + counts identical, direction
//   flipped.
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectBearishChOCh(double m5_close, double m5_open, double m5_atr,
                        IctSwingPoint &swing_highs_arr[], int highs_count,
                        IctSwingPoint &swing_lows_arr[],  int lows_count,
                        int minor_lookback, double displacement_atr_mult,
                        double &out_level)
{
   out_level = 0.0;
   if(m5_atr <= 0.0) return false;
   if(highs_count <= 0) return false;
   double recent_high = swing_highs_arr[highs_count - 1].price;
   if(recent_high <= 0.0 || m5_close >= recent_high) return false;
   double level = 0.0;
   if(!DetectInternalStructureShift(m5_close, swing_lows_arr, lows_count,
                                    false, minor_lookback, level)) return false;
   double body = MathAbs(m5_close - m5_open);
   if(body < displacement_atr_mult * m5_atr) return false;
   out_level = level;
   return true;
}

// ─── Equal Highs / Equal Lows + Liquidity sweep detection ───────────────────

// ─────────────────────────────────────────────────────────────────────────────
// DetectEqualHighs — find a cluster of 2+ swing highs within tolerance × ATR.
//
// PURPOSE: Equal-highs are buy-side liquidity (stops above are clustered).
//   Returns the cluster size and the average level. Used as input to
//   ScoreLiquiditySweep (a sweep at a thick cluster is higher-quality).
//
// PARAMETERS:
//   swing_highs_arr[]  — IctSwingPoint array (oldest-first)
//   count              — # of valid entries
//   m5_atr             — M5 ATR(14)
//   tolerance_atr_mult — fraction of ATR within which highs are "equal"
//                        (FORGE default 0.2 → highs within 0.2×ATR cluster)
//   out_avg_level      — [out] mean of the matched cluster (0 if none)
//
// RETURNS: cluster size (0/1 = no pool, ≥2 = pool found).
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
int DetectEqualHighs(IctSwingPoint &swing_highs_arr[], int count, double m5_atr,
                     double tolerance_atr_mult, double &out_avg_level)
{
   out_avg_level = 0.0;
   if(count < 2 || m5_atr <= 0.0) return 0;
   double tol = tolerance_atr_mult * m5_atr;
   // Anchor on the most-recent swing high; find others within tolerance.
   double anchor = swing_highs_arr[count - 1].price;
   if(anchor <= 0.0) return 0;
   double sum   = anchor;
   int    n     = 1;
   for(int i = count - 2; i >= 0; i--) {
      double p = swing_highs_arr[i].price;
      if(p <= 0.0) continue;
      if(MathAbs(p - anchor) <= tol) { sum += p; n++; }
   }
   if(n >= 2) out_avg_level = sum / (double)n;
   return n;
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectEqualLows — mirror of DetectEqualHighs.
//
// PURPOSE: Equal-lows are sell-side liquidity (stops below are clustered).
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
int DetectEqualLows(IctSwingPoint &swing_lows_arr[], int count, double m5_atr,
                    double tolerance_atr_mult, double &out_avg_level)
{
   out_avg_level = 0.0;
   if(count < 2 || m5_atr <= 0.0) return 0;
   double tol = tolerance_atr_mult * m5_atr;
   double anchor = swing_lows_arr[count - 1].price;
   if(anchor <= 0.0) return 0;
   double sum = anchor;
   int    n   = 1;
   for(int i = count - 2; i >= 0; i--) {
      double p = swing_lows_arr[i].price;
      if(p <= 0.0) continue;
      if(MathAbs(p - anchor) <= tol) { sum += p; n++; }
   }
   if(n >= 2) out_avg_level = sum / (double)n;
   return n;
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectSweepRejection — sweep + rejection-candle composite (single bar).
//
// PURPOSE: A liquidity sweep is more valuable when paired with a rejection
//   candle — wick beyond the level + body close back on the opposite side.
//   Returns true iff:
//     buy_side  → m5_h0 > pool_level AND m5_c0 < pool_level
//                 AND (m5_h0 - max(m5_c0, m5_o0)) ≥ min_wick × atr
//     sell_side → m5_l0 < pool_level AND m5_c0 > pool_level
//                 AND (min(m5_c0, m5_o0) - m5_l0) ≥ min_wick × atr
//
// PARAMETERS:
//   m5_h0 / m5_l0 / m5_c0 — current M5 OHLC (open inferred via wick calc;
//                            we treat the wick as h - max(close,open) for
//                            buy-side sweeps to capture the upper-shadow length)
//   pool_level            — the level that's being swept
//   buy_side              — true → buy-side sweep (wick above), false → sell-side
//   m5_atr                — M5 ATR(14)
//   min_wick_atr_mult     — minimum wick / ATR ratio (FORGE default 0.3)
//
// RETURNS: true iff the wick reached past pool_level and the body closed
//   back through with adequate wick magnitude.
//
// NOTE: The wick check uses close-only since m5_open isn't passed (matches
//   the chokepoint's existing _m5_c0/h0/l0 inputs). For tighter wick semantics
//   the chokepoint should pass open + use the open-or-close max instead.
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectSweepRejection(double m5_h0, double m5_l0, double m5_c0,
                          double pool_level, bool buy_side,
                          double m5_atr, double min_wick_atr_mult)
{
   if(m5_atr <= 0.0 || pool_level <= 0.0) return false;
   double min_wick = min_wick_atr_mult * m5_atr;
   if(buy_side) {
      if(m5_h0 <= pool_level) return false;       // wick didn't reach level
      if(m5_c0 >= pool_level) return false;       // close didn't reject
      double wick = m5_h0 - m5_c0;                // upper-wick proxy (close-anchored)
      return (wick >= min_wick);
   } else {
      if(m5_l0 >= pool_level) return false;
      if(m5_c0 <= pool_level) return false;
      double wick = m5_c0 - m5_l0;                // lower-wick proxy
      return (wick >= min_wick);
   }
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectBuySideLiquiditySweep — wick above + close below an equal-highs pool.
//
// PURPOSE: ICT-canonical "stop hunt" above buy-side liquidity. The wick
//   takes out the equal-highs cluster, the body closes back below — a
//   false breakout signature. Often the trigger candle for a bearish ChoCH
//   / MSS that follows.
//
// PARAMETERS:
//   m5_h0 / m5_l0 / m5_c0 — current M5 OHLC
//   swing_highs_arr[]     — IctSwingPoint array
//   highs_count           — # of valid entries
//   m5_atr                — ATR
//   tolerance_atr_mult    — equal-highs tolerance (g_sc.ict_liquidity_equal_tolerance_atr_mult)
//   min_wick_atr_mult     — sweep-rejection wick floor
//   out_level             — [out] level that got swept (avg of cluster)
//   out_cluster_size      — [out] cluster size at the swept level
//
// RETURNS: true iff a 2+ equal-highs cluster exists AND the current bar's
//   wick swept it AND the close rejected it.
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectBuySideLiquiditySweep(double m5_h0, double m5_l0, double m5_c0,
                                 IctSwingPoint &swing_highs_arr[], int highs_count,
                                 double m5_atr, double tolerance_atr_mult,
                                 double min_wick_atr_mult,
                                 double &out_level, int &out_cluster_size)
{
   out_level        = 0.0;
   out_cluster_size = 0;
   double avg = 0.0;
   int n = DetectEqualHighs(swing_highs_arr, highs_count, m5_atr, tolerance_atr_mult, avg);
   if(n < 2 || avg <= 0.0) return false;
   if(!DetectSweepRejection(m5_h0, m5_l0, m5_c0, avg, true, m5_atr, min_wick_atr_mult))
      return false;
   out_level        = avg;
   out_cluster_size = n;
   return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectSellSideLiquiditySweep — mirror: wick below + close above equal-lows.
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectSellSideLiquiditySweep(double m5_h0, double m5_l0, double m5_c0,
                                  IctSwingPoint &swing_lows_arr[], int lows_count,
                                  double m5_atr, double tolerance_atr_mult,
                                  double min_wick_atr_mult,
                                  double &out_level, int &out_cluster_size)
{
   out_level        = 0.0;
   out_cluster_size = 0;
   double avg = 0.0;
   int n = DetectEqualLows(swing_lows_arr, lows_count, m5_atr, tolerance_atr_mult, avg);
   if(n < 2 || avg <= 0.0) return false;
   if(!DetectSweepRejection(m5_h0, m5_l0, m5_c0, avg, false, m5_atr, min_wick_atr_mult))
      return false;
   out_level        = avg;
   out_cluster_size = n;
   return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// ScoreLiquiditySweep — composite 0..1 strength of a sweep event.
//
// PURPOSE: Quality score for a confirmed sweep, used for downstream ranking
//   (IctScoring v2.7.121+). Combines:
//     - equal-highs/lows cluster size (more stops = more liquidity)
//     - rejection wick magnitude relative to ATR
//     - killzone alignment (London KZ / NY AM KZ = institutional flow window)
//
// PARAMETERS:
//   cluster_size      — equal-highs/lows count (typical 2-5)
//   wick_atr_ratio    — wick / ATR (typical 0.3 - 1.5)
//   killzone_active   — 1..4 if inside a kill zone, 0 otherwise
//
// RETURNS: 0..1 score. ~0.3 for a minimal sweep, ~1.0 for thick cluster +
//   strong wick in a kill zone.
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
double ScoreLiquiditySweep(int cluster_size, double wick_atr_ratio, int killzone_active)
{
   double cluster_pts = MathMin(1.0, (double)(cluster_size - 1) / 4.0);  // 2→0.25, 5→1.0
   double wick_pts    = MathMin(1.0, wick_atr_ratio / 1.5);              // 1.5×ATR → 1.0
   double kz_pts      = (killzone_active >= 1 && killzone_active <= 4) ? 1.0 : 0.0;
   // weighted blend: 0.4 cluster, 0.4 wick, 0.2 killzone
   return 0.4 * cluster_pts + 0.4 * wick_pts + 0.2 * kz_pts;
}

// ─────────────────────────────────────────────────────────────────────────────
// Forge_GetLatestLiquidityPool — fetch the most-recent matching-side pool.
//
// PURPOSE: Convenience API for the chokepoint when scoring a setup against
//   the most-recent buy-side or sell-side pool.
//
// PARAMETERS:
//   buy_side  — true → return latest buy-side pool, false → sell-side
//   out       — [out] LiquidityPool copy on match (zero-init on no-match)
//
// RETURNS: true iff a matching-side pool exists.
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool Forge_GetLatestLiquidityPool(bool buy_side, LiquidityPool &out)
{
   out.time = 0; out.level = 0.0; out.buy_side = buy_side; out.swept = false;
   out.swept_time = 0; out.cluster_size = 0;
   for(int i = g_liquidity_pool_count - 1; i >= 0; i--) {
      if(g_liquidity_pools[i].buy_side == buy_side) {
         out = g_liquidity_pools[i];
         return true;
      }
   }
   return false;
}

// ─── Kill Zones ─────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// IsInLondonKillZone — true iff t is within London KZ (07:00-10:00 UTC).
//
// PURPOSE: ICT London Open killzone. Most-cited setup is the Judas Swing
//   ≈ 02:30 NY (07:30 UTC winter) where price sweeps an Asian extreme then
//   reverses sharply. See docs/research/ICT_KILLZONES.md §2.1.
//
// PARAMETERS:
//   t  — datetime (broker / server time interpreted as UTC by MqlDateTime).
//        For mainstream brokers (FOREX.com, IC Markets etc.) server time IS
//        GMT+2/GMT+3 not UTC — the existing g_regime.killzone uses a
//        broker_gmt_offset; here we follow the same convention by treating
//        t as already-UTC. Callers pass TimeCurrent() (which is the broker's
//        idea of UTC for tester DB rows that match real-time signals).
//
// RETURNS: true iff hour ∈ [7, 10).
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool IsInLondonKillZone(datetime t)
{
   if(t <= 0) return false;
   MqlDateTime mt; TimeToStruct(t, mt);
   return (mt.hour >= 7 && mt.hour < 10);
}

// ─────────────────────────────────────────────────────────────────────────────
// IsInNewYorkKillZone — true iff t is within NY AM KZ (12:00-15:00 UTC).
//
// PURPOSE: ICT New York Open killzone. Largest daily move often forms here
//   during the London/NY overlap (gold prime window).
//   See docs/research/ICT_KILLZONES.md §2.2.
//
// PARAMETERS:
//   t  — datetime (UTC convention as IsInLondonKillZone)
//
// RETURNS: true iff hour ∈ [12, 15).
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool IsInNewYorkKillZone(datetime t)
{
   if(t <= 0) return false;
   MqlDateTime mt; TimeToStruct(t, mt);
   return (mt.hour >= 12 && mt.hour < 15);
}

// ─────────────────────────────────────────────────────────────────────────────
// IsInSilverBulletWindow — true iff t is in either Silver Bullet 1h window.
//
// PURPOSE: ICT Silver Bullet — refined 1h sub-window inside each macro KZ
//   where directional flow is statistically strongest. AM SB: 10:00-11:00
//   UTC (final hour of London KZ + first hour of overlap); PM SB: 14:00-15:00
//   UTC (final hour of NY AM KZ).
//
// PARAMETERS:
//   t  — datetime
//
// RETURNS: true iff hour ∈ {10, 14} (i.e. the [10,11) ∪ [14,15) ranges).
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool IsInSilverBulletWindow(datetime t)
{
   if(t <= 0) return false;
   MqlDateTime mt; TimeToStruct(t, mt);
   return (mt.hour == 10 || mt.hour == 14);
}

// ─────────────────────────────────────────────────────────────────────────────
// IsInKillZone — any of the four KZ windows (London / NY AM / NY PM / LDN Close).
//
// PURPOSE: Quick boolean "is institutional flow active right now". Composite
//   of London Open + NY AM + NY PM (15:00-17:00) + London Close (15:00-17:00
//   — note London Close overlaps NY PM in UTC; we collapse them into one).
//
// PARAMETERS:
//   t  — datetime
//
// RETURNS: true iff GetSessionContext(t) ∈ {1, 2, 3, 4}.
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool IsInKillZone(datetime t)
{
   if(t <= 0) return false;
   MqlDateTime mt; TimeToStruct(t, mt);
   if(mt.hour >= 7  && mt.hour < 10) return true;  // London KZ
   if(mt.hour >= 12 && mt.hour < 15) return true;  // NY AM KZ
   if(mt.hour >= 15 && mt.hour < 17) return true;  // NY PM / London Close
   return false;
}

// ─────────────────────────────────────────────────────────────────────────────
// GetSessionContext — enum mapping the time to a session label.
//
// PURPOSE: Categorical session classifier for downstream filters / scoring.
//   Mapping (UTC):
//     0 — ASIAN / DEAD_ZONE  (none of the below; treated identically here)
//     1 — LONDON_KZ          07:00 - 10:00 UTC
//     2 — NY_AM_KZ           12:00 - 15:00 UTC
//     3 — NY_PM              15:00 - 17:00 UTC  (also London Close overlap)
//     4 — LONDON_CLOSE       Not a separate range — same physical 15:00-17:00.
//                            Kept for symmetry with the operator spec; current
//                            implementation collapses 3+4 into code 3. The
//                            chokepoint uses code 0-3 only.
//
// PARAMETERS:
//   t  — datetime
//
// RETURNS: int 0-3 (4 reserved).
//
// ASSUMPTION (documented per ship constraint): UTC = broker server time.
//   The FORGE chokepoint's existing g_regime.killzone uses the same
//   broker-GMT-offset convention via g_scalper_killzone_*_time globals;
//   we follow the simpler "treat as UTC" approach here because the SIGNALS
//   schema already has a `killzone` text column written from the same
//   ComputeCurrentKillzoneLabel() helper. The g_ict_last_killzone_active int
//   is a numeric mirror for analysis joins, not a primary source of truth.
//
// CHANGELOG:
//   2026-05-15  v2.7.120 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
int GetSessionContext(datetime t)
{
   if(t <= 0) return 0;
   MqlDateTime mt; TimeToStruct(t, mt);
   if(mt.hour >= 7  && mt.hour < 10) return 1;   // LONDON_KZ
   if(mt.hour >= 12 && mt.hour < 15) return 2;   // NY_AM_KZ
   if(mt.hour >= 15 && mt.hour < 17) return 3;   // NY_PM / LONDON_CLOSE overlap
   return 0;                                      // ASIAN / DEAD_ZONE
}

#endif // __FORGE_ICT_LIQUIDITY_MQH__
