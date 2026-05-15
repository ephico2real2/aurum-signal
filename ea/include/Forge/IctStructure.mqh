//+------------------------------------------------------------------+
//| Forge\IctStructure.mqh                                            |
//| FORGE v2.7.119 — ICT structure detection module                   |
//| First modular FORGE component. See docs/MQL5_MODULAR_EA_DESIGN.md |
//+------------------------------------------------------------------+
#ifndef __FORGE_ICT_STRUCTURE_MQH__
#define __FORGE_ICT_STRUCTURE_MQH__

// ─────────────────────────────────────────────────────────────────────────────
// PURPOSE
//   ICT swing-pivot tracker + Market Structure Shift (MSS) detection +
//   Fair Value Gap (FVG) detection with mitigation/age tracking.
//
//   This is the first FORGE component to live in `.mqh` form. The build
//   pipeline (scripts/compile_forge_ea_macos.sh) mirrors `ea/include/` into
//   Wine `MQL5/Include/` so `#include <Forge\IctStructure.mqh>` resolves.
//
// DEPENDENCIES
//   Standard MQL5 only (no external includes). Caller (FORGE.mq5) passes
//   M5 OHLC + ATR as parameters — module functions perform no implicit
//   global reads (per docs/MQL5_MODULAR_EA_DESIGN.md §4.4).
//
// EXPORTS
//   Structs:
//     IctSwingPoint, FVGZone
//   Globals (module-owned, read by FORGE.mq5):
//     g_swing_highs[16], g_swing_lows[16], g_swing_high_count, g_swing_low_count
//     g_fvg_ring[16], g_fvg_ring_count
//   Functions:
//     Forge_PushSwingHigh / Forge_PushSwingLow / Forge_PushFVG
//     DetectSwingHigh / DetectSwingLow
//     DetectDisplacementCandle / DetectStructureBreak
//     DetectBullishMSS / DetectBearishMSS
//     DetectBullishFVG / DetectBearishFVG
//     IsValidFVG / IsFVGMitigated / IsFVGPartiallyMitigated / GetFVGMidpoint
//     ScoreFVG (placeholder for v2.7.121 IctScoring consumption)
//     UpdateFVGMitigations
//     Forge_GetActiveFVGAlignedWith
//
// NAMING NOTE
//   FORGE.mq5 already defines `struct SwingPoint` (at :382, fields
//   {time, price, direction}) for the Tier 3 Double-Top/H&S infrastructure.
//   To avoid a duplicate-symbol error we expose a separate `IctSwingPoint`
//   struct (fields {time, price, bar_index, confirmed}) per the v2.7.118 spec.
//   Both coexist — the Tier 3 buffer at :8008 is untouched and remains
//   functional for the existing pattern setups.
//
// CHANGELOG
//   2026-05-14  v2.7.118 initial ship — first modular FORGE component.
//   2026-05-14  v2.7.119 — add 8 atom-context globals (g_ict_last_*) populated by
//                          FORGE.mq5 at the chokepoint, read by JournalRecordSignal
//                          for 14-column SIGNALS expansion (5 retroactive iss_*
//                          + 9 new ict_*). Forge_GetActiveFVGAlignedWith now
//                          zero-inits `out` unconditionally so callers can read
//                          struct fields safely on no-match.
//+------------------------------------------------------------------+

// ─── Structs ────────────────────────────────────────────────────────────────

struct IctSwingPoint {
   datetime time;        // M5 bar time of the swing point
   double   price;       // swing high (for highs) or swing low (for lows)
   int      bar_index;   // M5 bar index (shift relative to current bar at creation)
   bool     confirmed;   // true after lookback bars without breakout invalidation
};

struct FVGZone {
   datetime time;                 // M5 bar time of the middle bar (i-1)
   double   upper;                // upper edge of the gap
   double   lower;                // lower edge of the gap
   double   midpoint;             // (upper + lower) / 2 — consequent encroachment line
   bool     bullish;              // true = bullish FVG (gap above), false = bearish
   bool     mitigated;            // fully mitigated (price closed back through opposite edge)
   bool     partiallyMitigated;   // partially mitigated (price reached >= max_fill_pct fill)
   int      sourceBar;            // shift of the bar where the gap was created
   double   displacementScore;    // body / ATR ratio of the middle (displacement) candle
   datetime expiry;               // age-cap timestamp (creation_time + max_age × M5_seconds)
};

// ─── Module globals (read by FORGE.mq5 after include) ───────────────────────

IctSwingPoint g_swing_highs[16];
IctSwingPoint g_swing_lows[16];
int           g_swing_high_count = 0;
int           g_swing_low_count  = 0;

FVGZone       g_fvg_ring[16];
int           g_fvg_ring_count = 0;

// v2.7.119 — ICT atom-context capture for SIGNALS logging.
//   Populated by FORGE.mq5 at the setup-trigger chokepoint AFTER computing g_iss_*.
//   Read inline by JournalRecordSignal so every SIGNALS row carries the ICT context
//   that informed the (would-be) entry, even on SKIPs. All zero by default — when an
//   atom is OFF (iss_enabled=0 / ict_*_enabled=0) the corresponding context stays 0,
//   keeping the schema-parity invariant byte-stable vs v2.7.118 with defaults.
double g_ict_last_mss_swing_price       = 0.0;   // swing price broken (0 if no MSS)
double g_ict_last_mss_displacement_atr  = 0.0;   // body/ATR ratio at MSS fire
double g_ict_last_fvg_upper             = 0.0;   // matched FVG upper bound
double g_ict_last_fvg_lower             = 0.0;   // matched FVG lower bound
double g_ict_last_fvg_midpoint_dist_atr = 0.0;   // (price − midpoint)/ATR
int    g_ict_last_fvg_age_bars          = 0;     // age of matched FVG in M5 bars
double g_ict_last_recent_swing_high     = 0.0;   // most-recent confirmed swing high
double g_ict_last_recent_swing_low      = 0.0;   // most-recent confirmed swing low

// ─────────────────────────────────────────────────────────────────────────────
// Forge_PushSwingHigh — append a new swing high to the ring buffer.
//
// PURPOSE: Maintain a rolling window of the most-recent 16 confirmed swing
//   highs for MSS / structure-break consumption by FORGE.mq5.
//
// PARAMETERS:
//   t          — M5 bar time of the swing high
//   price      — high price at the swing
//   bar_index  — shift relative to current bar at creation (informational only)
//
// RETURNS / SIDE EFFECTS:
//   Appends to g_swing_highs[]; when full (16), evicts the oldest entry by
//   shifting all elements down one slot. New entry is `confirmed = true`
//   (the caller is responsible for fractal-confirmation).
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
void Forge_PushSwingHigh(datetime t, double price, int bar_index)
{
   if(g_swing_high_count >= 16) {
      // FIFO eviction — shift down
      for(int i = 0; i < 15; i++) g_swing_highs[i] = g_swing_highs[i + 1];
      g_swing_high_count = 15;
   }
   g_swing_highs[g_swing_high_count].time      = t;
   g_swing_highs[g_swing_high_count].price     = price;
   g_swing_highs[g_swing_high_count].bar_index = bar_index;
   g_swing_highs[g_swing_high_count].confirmed = true;
   g_swing_high_count++;
}

// ─────────────────────────────────────────────────────────────────────────────
// Forge_PushSwingLow — mirror of Forge_PushSwingHigh for swing lows.
//
// PURPOSE: Maintain a rolling window of the most-recent 16 confirmed swing
//   lows for MSS / structure-break consumption.
//
// PARAMETERS:
//   t          — M5 bar time of the swing low
//   price      — low price at the swing
//   bar_index  — shift relative to current bar at creation
//
// RETURNS / SIDE EFFECTS:
//   Appends to g_swing_lows[]; FIFO eviction at capacity.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
void Forge_PushSwingLow(datetime t, double price, int bar_index)
{
   if(g_swing_low_count >= 16) {
      for(int i = 0; i < 15; i++) g_swing_lows[i] = g_swing_lows[i + 1];
      g_swing_low_count = 15;
   }
   g_swing_lows[g_swing_low_count].time      = t;
   g_swing_lows[g_swing_low_count].price     = price;
   g_swing_lows[g_swing_low_count].bar_index = bar_index;
   g_swing_lows[g_swing_low_count].confirmed = true;
   g_swing_low_count++;
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectSwingHigh — fractal-style swing high detector.
//
// PURPOSE: Return true iff highs[lookback] is the strict maximum in the
//   2*lookback+1-bar window centred on it (canonical fractal pattern).
//
// PARAMETERS:
//   highs[]   — array of M5 highs ordered newest-to-oldest (ArraySetAsSeries)
//               must have at least (2*lookback + 1) elements
//   lookback  — bars on each side of centre (typical 2-5, default 3)
//
// RETURNS: true if highs[lookback] > all neighbours within ±lookback bars.
//          false if array too short or centre is not strict max.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectSwingHigh(double &highs[], int lookback)
{
   int needed = 2 * lookback + 1;
   if(lookback < 1) return false;
   if(ArraySize(highs) < needed) return false;
   double centre = highs[lookback];
   for(int i = 0; i < needed; i++) {
      if(i == lookback) continue;
      if(highs[i] >= centre) return false;
   }
   return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectSwingLow — fractal-style swing low detector (mirror of DetectSwingHigh).
//
// PURPOSE: Return true iff lows[lookback] is the strict minimum in the
//   2*lookback+1-bar window centred on it.
//
// PARAMETERS:
//   lows[]    — array of M5 lows newest-to-oldest, length ≥ 2*lookback+1
//   lookback  — bars on each side of centre
//
// RETURNS: true if lows[lookback] < all neighbours within ±lookback bars.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectSwingLow(double &lows[], int lookback)
{
   int needed = 2 * lookback + 1;
   if(lookback < 1) return false;
   if(ArraySize(lows) < needed) return false;
   double centre = lows[lookback];
   for(int i = 0; i < needed; i++) {
      if(i == lookback) continue;
      if(lows[i] <= centre) return false;
   }
   return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectDisplacementCandle — body / ATR ≥ multiplier.
//
// PURPOSE: Validate that a candle has body magnitude commensurate with
//   "displacement" — the ICT-canonical term for a strong directional move
//   that creates / confirms structure. Used by MSS + FVG detectors.
//
// PARAMETERS:
//   m5_open   — candle open price
//   m5_close  — candle close price
//   m5_atr    — M5 ATR(14) at the candle's time
//   atr_mult  — minimum body / ATR ratio (FORGE default 0.5, matches DirLock)
//
// RETURNS: true iff |close - open| ≥ atr_mult × atr AND atr > 0.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectDisplacementCandle(double m5_open, double m5_close, double m5_atr, double atr_mult)
{
   if(m5_atr <= 0.0) return false;
   double body = MathAbs(m5_close - m5_open);
   return (body >= atr_mult * m5_atr);
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectStructureBreak — close-beyond-level test (not just wick).
//
// PURPOSE: ICT structure breaks count only on BODY close beyond the level.
//   Wick-only excursions are noise / liquidity sweeps and must be rejected.
//
// PARAMETERS:
//   m5_close  — candle close price
//   level     — the structure level (prior swing high or low)
//   above     — true → testing close > level; false → testing close < level
//
// RETURNS: true iff the close passes the directional break test.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectStructureBreak(double m5_close, double level, bool above)
{
   if(level <= 0.0) return false;
   if(above) return (m5_close > level);
   return (m5_close < level);
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectBullishMSS — Market Structure Shift, bullish direction.
//
// PURPOSE: Detect a body-close break of the most recent M5 swing high WITH
//   sufficient displacement. Primary "structural confirmation" signal for
//   the ICT Phase 1 ISS atom (g_iss_mss).
//
// EVALUATION ORDER:
//   1. Guard — return false if recent_swing_high ≤ 0 or atr ≤ 0.
//   2. Close > swing_high — body-close break (not wick) per DetectStructureBreak.
//   3. Displacement — |close - open| ≥ mult × atr per DetectDisplacementCandle.
//
// PARAMETERS:
//   m5_close              — current M5 bar close
//   m5_open               — current M5 bar open
//   m5_atr                — M5 ATR(14) at current bar
//   recent_swing_high     — most recent confirmed swing high
//   displacement_atr_mult — minimum body / ATR ratio (FORGE default 0.5)
//
// RETURNS: true iff all three conditions hold.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship — first modular ICT atom.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectBullishMSS(double m5_close, double m5_open, double m5_atr,
                     double recent_swing_high, double displacement_atr_mult)
{
   if(recent_swing_high <= 0.0 || m5_atr <= 0.0) return false;
   if(!DetectStructureBreak(m5_close, recent_swing_high, true)) return false;
   return DetectDisplacementCandle(m5_open, m5_close, m5_atr, displacement_atr_mult);
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectBearishMSS — mirror of DetectBullishMSS.
//
// PURPOSE: Detect a body-close break BELOW the most recent M5 swing low with
//   sufficient displacement.
//
// PARAMETERS:
//   m5_close              — current M5 bar close
//   m5_open               — current M5 bar open
//   m5_atr                — M5 ATR(14)
//   recent_swing_low      — most recent confirmed swing low
//   displacement_atr_mult — minimum body / ATR ratio
//
// RETURNS: true iff close < swing_low AND body ≥ mult × atr.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectBearishMSS(double m5_close, double m5_open, double m5_atr,
                     double recent_swing_low, double displacement_atr_mult)
{
   if(recent_swing_low <= 0.0 || m5_atr <= 0.0) return false;
   if(!DetectStructureBreak(m5_close, recent_swing_low, false)) return false;
   return DetectDisplacementCandle(m5_open, m5_close, m5_atr, displacement_atr_mult);
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectBullishFVG — 3-candle bullish Fair Value Gap detector.
//
// PURPOSE: Detect the classic ICT bullish FVG pattern where the high of bar
//   (i-2) is strictly below the low of bar (i), creating an unmitigated gap.
//   Populate the output FVGZone on success.
//
// PATTERN:
//   bar i-2 (oldest)  ┐
//   bar i-1 (middle, displacement candle, body usually large)
//   bar i   (newest)  ┘  with  high[i-2] < low[i]
//
// PARAMETERS:
//   h_i_minus_2          — high of the oldest bar (i-2)
//   l_i                  — low of the newest bar (i)
//   atr                  — M5 ATR(14) for size validation
//   min_size_atr_mult    — minimum (l_i - h_i_minus_2) / atr to qualify
//   out                  — [out] FVGZone populated on success
//
// RETURNS: true iff gap exists and size ≥ min_size_atr_mult × atr.
//
// SIDE EFFECTS: writes to `out` only on success. `out.time/expiry/sourceBar`
//   are left to the caller to populate (we don't know the bar shift here).
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectBullishFVG(double h_i_minus_2, double l_i, double atr,
                     double min_size_atr_mult, FVGZone &out)
{
   if(atr <= 0.0) return false;
   if(h_i_minus_2 <= 0.0 || l_i <= 0.0) return false;
   if(h_i_minus_2 >= l_i) return false;            // no gap
   double size = l_i - h_i_minus_2;
   if(size < min_size_atr_mult * atr) return false; // gap too small
   out.upper              = l_i;
   out.lower              = h_i_minus_2;
   out.midpoint           = (l_i + h_i_minus_2) * 0.5;
   out.bullish            = true;
   out.mitigated          = false;
   out.partiallyMitigated = false;
   out.displacementScore  = size / atr;
   // caller fills time/expiry/sourceBar before push
   out.time               = 0;
   out.expiry             = 0;
   out.sourceBar          = 0;
   return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// DetectBearishFVG — mirror of DetectBullishFVG.
//
// PURPOSE: Detect 3-candle bearish FVG where low[i-2] > high[i].
//
// PARAMETERS:
//   l_i_minus_2          — low of the oldest bar (i-2)
//   h_i                  — high of the newest bar (i)
//   atr                  — M5 ATR(14)
//   min_size_atr_mult    — minimum gap size in ATR units
//   out                  — [out] FVGZone populated on success
//
// RETURNS: true iff bearish gap exists and size ≥ threshold.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool DetectBearishFVG(double l_i_minus_2, double h_i, double atr,
                     double min_size_atr_mult, FVGZone &out)
{
   if(atr <= 0.0) return false;
   if(l_i_minus_2 <= 0.0 || h_i <= 0.0) return false;
   if(l_i_minus_2 <= h_i) return false;            // no gap
   double size = l_i_minus_2 - h_i;
   if(size < min_size_atr_mult * atr) return false;
   out.upper              = l_i_minus_2;
   out.lower              = h_i;
   out.midpoint           = (l_i_minus_2 + h_i) * 0.5;
   out.bullish            = false;
   out.mitigated          = false;
   out.partiallyMitigated = false;
   out.displacementScore  = size / atr;
   out.time               = 0;
   out.expiry             = 0;
   out.sourceBar          = 0;
   return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// IsValidFVG — index-bound + un-mitigated + un-expired check.
//
// PURPOSE: Quick boolean qualifier — used before consuming an FVG as an
//   entry zone. Active = idx valid AND not mitigated AND (no expiry set OR
//   expiry not yet reached).
//
// PARAMETERS:
//   idx  — slot index into g_fvg_ring[]
//
// RETURNS: true iff the FVG at idx is currently active / tradeable.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool IsValidFVG(int idx)
{
   if(idx < 0 || idx >= g_fvg_ring_count) return false;
   if(g_fvg_ring[idx].mitigated) return false;
   if(g_fvg_ring[idx].expiry > 0 && TimeCurrent() >= g_fvg_ring[idx].expiry) return false;
   return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// IsFVGMitigated — true if FVG has been fully closed back through.
//
// PURPOSE: Mitigation = price closed through the FAR edge of the gap (the
//   edge opposite the displacement direction). Once mitigated, the FVG is
//   considered consumed and ineligible for entries.
//
// PARAMETERS:
//   idx           — slot index
//   current_price — most recent close (typically m5_close_now)
//
// RETURNS: true iff stored mitigated flag is set OR current_price has
//   moved past the opposite edge (bullish FVG: price ≤ lower edge;
//   bearish FVG: price ≥ upper edge).
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool IsFVGMitigated(int idx, double current_price)
{
   if(idx < 0 || idx >= g_fvg_ring_count) return false;
   if(g_fvg_ring[idx].mitigated) return true;
   if(g_fvg_ring[idx].bullish) {
      return (current_price <= g_fvg_ring[idx].lower);
   } else {
      return (current_price >= g_fvg_ring[idx].upper);
   }
}

// ─────────────────────────────────────────────────────────────────────────────
// IsFVGPartiallyMitigated — true if price has retraced ≥ max_fill_pct into the gap.
//
// PURPOSE: Partial mitigation = price has filled at least max_fill_pct (default
//   0.50 = consequent encroachment / midpoint) of the gap. Used for entry-
//   quality scoring — a fully-filled gap is weaker than a fresh one.
//
// PARAMETERS:
//   idx            — slot index
//   current_price  — current close
//   max_fill_pct   — fill ratio threshold (0.0..1.0)
//
// RETURNS: true iff stored partiallyMitigated flag is set OR price retracement
//   into the gap ≥ max_fill_pct * gap_size.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
bool IsFVGPartiallyMitigated(int idx, double current_price, double max_fill_pct)
{
   if(idx < 0 || idx >= g_fvg_ring_count) return false;
   if(g_fvg_ring[idx].partiallyMitigated) return true;
   double size = g_fvg_ring[idx].upper - g_fvg_ring[idx].lower;
   if(size <= 0.0) return false;
   if(g_fvg_ring[idx].bullish) {
      // bullish: price retraces DOWNWARD from upper edge. Fill = (upper - price) / size.
      if(current_price >= g_fvg_ring[idx].upper) return false;
      double fill = (g_fvg_ring[idx].upper - current_price) / size;
      return (fill >= max_fill_pct);
   } else {
      // bearish: price retraces UPWARD from lower edge. Fill = (price - lower) / size.
      if(current_price <= g_fvg_ring[idx].lower) return false;
      double fill = (current_price - g_fvg_ring[idx].lower) / size;
      return (fill >= max_fill_pct);
   }
}

// ─────────────────────────────────────────────────────────────────────────────
// GetFVGMidpoint — return midpoint (consequent encroachment) of an FVG.
//
// PURPOSE: ICT's "consequent encroachment" = 50% of the gap. Used as a
//   precision entry target — price often reverses at midpoint rather than
//   wicking the full gap.
//
// PARAMETERS:
//   idx  — slot index
//
// RETURNS: midpoint price, or 0.0 if idx out of range.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
double GetFVGMidpoint(int idx)
{
   if(idx < 0 || idx >= g_fvg_ring_count) return 0.0;
   return g_fvg_ring[idx].midpoint;
}

// ─────────────────────────────────────────────────────────────────────────────
// ScoreFVG — placeholder strength score for IctScoring consumption.
//
// PURPOSE: v2.7.121 IctScoring module will consume per-FVG strength scores
//   for the Unicorn / multi-confluence rankers. For v2.7.118 we return the
//   stored displacementScore (body / ATR at creation time) as a stand-in.
//
// PARAMETERS:
//   idx  — slot index
//
// RETURNS: displacement score, or 0.0 if idx out of range.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship — placeholder, refined in v2.7.121.
// ─────────────────────────────────────────────────────────────────────────────
double ScoreFVG(int idx)
{
   if(idx < 0 || idx >= g_fvg_ring_count) return 0.0;
   return g_fvg_ring[idx].displacementScore;
}

// ─────────────────────────────────────────────────────────────────────────────
// UpdateFVGMitigations — sweep ring buffer for mitigation + age-out events.
//
// PURPOSE: Called once per M5 close by FORGE.mq5. Marks FVGs that have been
//   mitigated (full or partial) and evicts entries that exceed max_age_bars.
//
// EVALUATION ORDER:
//   1. For each entry: if not yet fully mitigated, check IsFVGMitigated +
//      IsFVGPartiallyMitigated against current_price; update flags.
//   2. After flag update, build a compacted list keeping only non-expired,
//      non-fully-mitigated entries (FVG is dropped when EITHER fully
//      mitigated OR expiry time reached).
//   3. Re-pack ring + reset g_fvg_ring_count.
//
// PARAMETERS:
//   current_price       — m5_close at the close-tick
//   current_time        — TimeCurrent() at the close-tick
//   max_fill_pct        — 0..1 partial-mitigation threshold (g_sc.iss_fvg_max_fill_pct)
//   max_age_bars        — age cap in M5 bars (g_sc.iss_fvg_max_age_bars)
//   m5_period_seconds   — 300 for M5
//
// RETURNS / SIDE EFFECTS:
//   Mutates g_fvg_ring[] flags. Compacts ring; may decrease g_fvg_ring_count.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
void UpdateFVGMitigations(double current_price, datetime current_time,
                         double max_fill_pct, int max_age_bars, int m5_period_seconds)
{
   if(g_fvg_ring_count <= 0) return;

   // Phase 1: update flags in-place.
   for(int i = 0; i < g_fvg_ring_count; i++) {
      if(!g_fvg_ring[i].mitigated && IsFVGMitigated(i, current_price)) {
         g_fvg_ring[i].mitigated = true;
      }
      if(!g_fvg_ring[i].partiallyMitigated && !g_fvg_ring[i].mitigated
         && IsFVGPartiallyMitigated(i, current_price, max_fill_pct)) {
         g_fvg_ring[i].partiallyMitigated = true;
      }
   }

   // Phase 2: compact — drop fully-mitigated AND age-expired entries.
   long age_cap_seconds = (long)max_age_bars * (long)m5_period_seconds;
   FVGZone tmp[16];
   int kept = 0;
   for(int i = 0; i < g_fvg_ring_count && kept < 16; i++) {
      bool aged_out = (g_fvg_ring[i].time > 0
                      && current_time > g_fvg_ring[i].time
                      && (long)(current_time - g_fvg_ring[i].time) >= age_cap_seconds);
      if(g_fvg_ring[i].mitigated) continue;
      if(aged_out) continue;
      tmp[kept] = g_fvg_ring[i];
      kept++;
   }
   for(int i = 0; i < kept; i++) g_fvg_ring[i] = tmp[i];
   g_fvg_ring_count = kept;
}

// ─────────────────────────────────────────────────────────────────────────────
// Forge_PushFVG — append a FVGZone to the ring with FIFO eviction.
//
// PURPOSE: Append-only insertion. When the ring is full, evict the oldest
//   entry (slot 0) by shifting all entries down one slot.
//
// PARAMETERS:
//   z  — FVGZone to insert. Caller must have populated time/expiry/sourceBar
//        before calling (DetectBullish/BearishFVG leave those zeroed).
//
// RETURNS: slot index of the newly-appended entry (0..15).
//
// SIDE EFFECTS: mutates g_fvg_ring[] and g_fvg_ring_count.
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
// ─────────────────────────────────────────────────────────────────────────────
int Forge_PushFVG(FVGZone &z)
{
   if(g_fvg_ring_count >= 16) {
      for(int i = 0; i < 15; i++) g_fvg_ring[i] = g_fvg_ring[i + 1];
      g_fvg_ring_count = 15;
   }
   g_fvg_ring[g_fvg_ring_count] = z;
   int slot = g_fvg_ring_count;
   g_fvg_ring_count++;
   return slot;
}

// ─────────────────────────────────────────────────────────────────────────────
// Forge_GetActiveFVGAlignedWith — find the most-recent active FVG aligned
//   with a trade direction whose zone contains current_price.
//
// PURPOSE: Consumed by FORGE.mq5 at the setup-trigger chokepoint to compute
//   g_iss_fvg (the ICT Phase 1 FVG atom). "Aligned" = bullish FVG for BUY,
//   bearish FVG for SELL. "Contains" = lower ≤ price ≤ upper.
//
// PARAMETERS:
//   direction      — "BUY" or "SELL"
//   current_price  — m5_close_now at the setup-trigger fire
//   out            — [out] copy of the matching FVGZone on success
//
// RETURNS: true iff an active aligned FVG containing current_price exists.
//   Scans newest-to-oldest; returns the FIRST match (most-recent FVG wins).
//
// CHANGELOG:
//   2026-05-14  v2.7.118 initial ship.
//   2026-05-14  v2.7.119 — always zero-initialize `out` before scanning so callers
//               can safely read the struct fields even when no match is found.
//               (Required for the SIGNALS logging chokepoint that captures FVG
//               context unconditionally.)
// ─────────────────────────────────────────────────────────────────────────────
bool Forge_GetActiveFVGAlignedWith(string direction, double current_price, FVGZone &out)
{
   // v2.7.119 — zero-init `out` first so the caller never reads uninitialized fields.
   out.time               = 0;
   out.upper              = 0.0;
   out.lower              = 0.0;
   out.midpoint           = 0.0;
   out.bullish            = false;
   out.mitigated          = false;
   out.partiallyMitigated = false;
   out.sourceBar          = 0;
   out.displacementScore  = 0.0;
   out.expiry             = 0;
   if(g_fvg_ring_count <= 0) return false;
   bool want_bullish = (direction == "BUY");
   bool want_bearish = (direction == "SELL");
   if(!want_bullish && !want_bearish) return false;
   for(int i = g_fvg_ring_count - 1; i >= 0; i--) {
      if(!IsValidFVG(i)) continue;
      if(want_bullish && !g_fvg_ring[i].bullish) continue;
      if(want_bearish &&  g_fvg_ring[i].bullish) continue;
      if(current_price < g_fvg_ring[i].lower || current_price > g_fvg_ring[i].upper) continue;
      out = g_fvg_ring[i];
      return true;
   }
   return false;
}

#endif // __FORGE_ICT_STRUCTURE_MQH__
