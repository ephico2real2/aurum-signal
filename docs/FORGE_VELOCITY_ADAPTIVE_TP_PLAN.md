# FORGE — Velocity Tracking & Adaptive TP/SL Plan
**Date:** 2026-05-08 | **Status:** PLANNED — document only, no code yet

---

## Problem Being Solved

Price frequently approaches TP on a SELL, then violently reverses and hits SL instead — particularly common on SELL positions. The observation: price moves "almost to TP" then reverses sharply, bypassing the TP and going all the way to SL.

This is a known market maker pattern ("stop hunt" or "liquidity sweep") where price sweeps stop clusters before reversing. It's more common on SELLs because:
1. SELL TPs are below entry → require sustained downward momentum
2. Bullish reversals (the common regime) tend to be fast and violent
3. Buy-stop orders cluster just above recent highs, creating sweep targets

---

## Three Mechanisms Evaluated

### Mechanism 1 — Move SL to Break-Even at X% of TP (PARTIAL — already in FORGE)

**Status: Partially implemented via `move_be_on_tp1`**

`move_be_on_tp1=true` moves SL to entry when TP1 partial close fires. BUT:
- Only triggers when TP1 actually **closes legs** (price must reach TP1 and a deal executes)
- If price *approaches* TP1 but doesn't reach it, no SL move occurs
- The violent reversal pattern hits SL before TP1 fires → mechanism doesn't help in this scenario

**Gap:** Need a price-proximity trigger, not a deal-execution trigger.

**Enhancement:** Add `sl_be_proximity_pct` — move SL to breakeven when price reaches X% of the way from entry to TP1:
```json
"safety": { "sl_be_proximity_pct": 80 }
```
When `(entry_price - current_price) / (entry_price - tp1) >= 0.80` (for SELL), move SL to entry immediately — before TP1 actually closes.

---

### Mechanism 2 — Fast-Lock Tightening on Adverse Velocity (PARTIAL — already in FORGE)

**Status: Partially implemented via `fast_lock_min_profit_points` and spread guards**

FORGE has a "fast-lock" system (`fast_lock_min_profit_points`, `fast_lock_spread_guard_mult`, `fast_lock_breath_mult`) that tightens SL when price has moved favorably and then starts reversing. BUT:
- It locks in profit, not prevents losses on the initial adverse move
- It doesn't track "velocity" (rate of change), only current profit level

**Gap:** No velocity-based SL tightening when a "fast reversal" is detected mid-trade.

**Enhancement:** `adverse_velocity_guard` — if price reverses > N points in < M seconds after moving favorably, tighten SL to lock in partial gain:
- Tracks `g_position_max_favorable_price` (high-water mark for SELL = lowest price reached)
- If `current_price - g_position_max_favorable_price > velocity_adverse_pts` within `velocity_window_sec` seconds → tighten SL immediately

---

### Mechanism 3 — Counter-Recovery Trade on Reversal (NOT RECOMMENDED)

**Status: Deliberately excluded**

Some EAs open a counter BUY when a SELL position is rapidly reversing. The theory: catch the reversal wave with a new position.

**Why not to implement:**
1. **Double exposure** — opens net long while short is still open
2. **Amplification risk** — if the reversal itself reverses, now losing on both sides
3. **Complexity** — requires knowing when to close the counter trade, creating a cascade of decision points
4. **Margin risk** — in a real account, double exposure can trigger margin calls

FORGE's philosophy is single-position clarity. Counter-trades undermine the group-based management model.

---

## Recommended Implementation: Adaptive TP via ATR Expansion

**Core idea:** When ATR spikes significantly bar-over-bar (fast move detected), widen TP to capture the extended move *before* the inevitable reversal hits.

**Internal tracking (fully automated, no external tools):**
```mq5
// Prior bar ATR — same handle used for entry gates
double atr_prev_buf[1];
if(CopyBuffer(g_mtf[0].h_atr, 0, 1, 1, atr_prev_buf) == 1) {
    double atr_prev = atr_prev_buf[0];
    double atr_expansion = m5_atr / MathMax(atr_prev, 0.01);
    
    if(atr_expansion > g_sc.adaptive_tp_atr_expansion_trigger) {
        // ATR expanded rapidly — widen TP for all open legs in direction
        double new_tp = NormalizeDouble(entry_price - (m5_atr * g_sc.adaptive_tp_extended_mult), _Digits);
        // Apply MODIFY_TP to all legs in the group
    }
}
```

**Why this works for the "almost hit TP then reverse" pattern:**
- If ATR suddenly expands (fast move), it often means momentum is extended and reversal is near
- Widening TP while momentum is strong captures the extended range before the snap-back
- If the move continues, the wider TP captures more profit
- If price reverses before the wider TP, the existing SL/fast-lock handles the exit

**Risk:** If ATR expands on a fundamentals-driven trend (NFP, FOMC), widening TP may be insufficient — price could blow through the extended TP too. Mitigate with `max_tp_atr_mult` cap.

---

## Implementation Plan

### Phase 1 — SL Proximity Trigger (no velocity, just proximity)

**Config:**
```json
"safety": {
  "sl_be_proximity_pct": 80,
  "sl_be_proximity_apply_sell": true,
  "sl_be_proximity_apply_buy": false
}
```

**MQL5 — in `ManageOpenGroups()`, per-position check:**
```mq5
if(g_sc.sl_be_proximity_pct > 0 && g_sc.sl_be_proximity_apply_sell) {
    for each open SELL position in group {
        double dist_to_tp1 = entry_price - tp1_price;
        double dist_moved  = entry_price - current_price;
        if(dist_to_tp1 > 0 && (dist_moved / dist_to_tp1) >= g_sc.sl_be_proximity_pct / 100.0) {
            if(current_sl < entry_price) {
                // Move SL to entry (breakeven)
                ModifySL(ticket, entry_price);
            }
        }
    }
}
```

**Internal tracking:** Uses existing `g_pos.OpenPrice()`, `g_pos.StopLoss()`, `g_pos.TakeProfit()` — no new state.

---

### Phase 2 — Adverse Velocity Guard (velocity-based SL tightening)

**Config:**
```json
"safety": {
  "adverse_velocity_pts": 15,
  "adverse_velocity_window_sec": 120
}
```

**MQL5 — new globals for velocity tracking:**
```mq5
// Per-group high-water mark (SELL = lowest price reached, BUY = highest)
double g_group_hwm[MAX_GROUPS];     // high-water mark price
datetime g_group_hwm_time[MAX_GROUPS]; // when HWM was set
```

**In `ManageOpenGroups()`:**
```mq5
// Update high-water mark
double current_bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
for each open SELL group {
    if(current_bid < g_group_hwm[gi] || g_group_hwm[gi] == 0)
        g_group_hwm[gi] = current_bid;  // new low = better for SELL
    
    // Check adverse velocity
    double adverse_move = current_bid - g_group_hwm[gi];  // positive = reversal
    double seconds_elapsed = TimeCurrent() - g_group_hwm_time[gi];
    
    if(adverse_move > g_sc.adverse_velocity_pts && seconds_elapsed < g_sc.adverse_velocity_window_sec) {
        // Fast reversal detected — tighten SL to lock in partial gain
        double tight_sl = g_group_hwm[gi] + (adverse_move * 0.5);  // lock half the favorable move
        ModifySL(ticket, tight_sl);
    }
}
```

---

### Phase 3 — Adaptive TP on ATR Expansion

**Config:**
```json
"safety": {
  "adaptive_tp_atr_expansion_trigger": 1.5,
  "adaptive_tp_extended_mult": 2.0,
  "adaptive_tp_apply_sell": true,
  "adaptive_tp_apply_buy": false
}
```

**MQL5:**
```mq5
// In OnTick() / ManageOpenGroups():
double atr_prev_buf[1];
if(CopyBuffer(g_mtf[0].h_atr, 0, 1, 1, atr_prev_buf) == 1) {
    double atr_now = m5_atr;
    double atr_was = atr_prev_buf[0];
    if(atr_was > 0 && (atr_now / atr_was) >= g_sc.adaptive_tp_atr_expansion_trigger) {
        for each open SELL leg in group {
            double extended_tp = entry_price - (atr_now * g_sc.adaptive_tp_extended_mult);
            if(extended_tp < current_tp)  // only widen, never narrow
                ModifyTP(ticket, extended_tp);
        }
    }
}
```

**Risk guard:** Only modify if new TP is *further from entry* than current (prevent accidental narrowing). Never modify past `max_tp_atr_mult` from entry.

---

## Implementation Order

| Phase | Feature | Risk | Effort | Impact |
|-------|---------|------|--------|--------|
| 1 | SL proximity trigger (80% to TP) | Low | Small | Prevents "almost TP" losses |
| 2 | Adverse velocity guard | Medium | Medium | Locks partial gain on fast reversal |
| 3 | Adaptive TP on ATR expansion | Medium | Medium | Captures extended moves before reversal |

**Suggested version:** FORGE 2.8.1 (trade management sprint, parallel to DB fix in 2.8.0)

All three use only `CopyBuffer`, `TimeCurrent()`, `SymbolInfoDouble()`, `g_pos.*`, `g_trade.PositionModify()` — zero external dependencies.

---

---

## Online Research Findings — Mathematical Approaches (MQL5 Community)

*Source: MQL5 Articles, MQL5 Market, EarnForex open-source EA library*

### Published Mathematical Formulas

**1. Price Velocity (Rate of Change)**
```
Velocity = (Close[0] - Close[N]) / N
Velocity_normalized = Velocity / ATR(14)
```
Values > 2.0 on normalized scale = runaway candle likely to snap back.
MQL5 reference: ["Price velocity measurement methods"](https://www.mql5.com/en/articles/6947)

**2. Proximity-Triggered Breakeven (community standard)**
```
if ((EntryPrice - CurrentPrice) / (EntryPrice - TP) >= 0.80)
    NewSL = EntryPrice - Spread   // spread offset prevents immediate stop-out
```
Widely cited threshold: 70-80% of distance to TP. MQL5 forum consensus uses BE (not trail) at this stage.

**3. ATR Expansion TP Widening**
```
ATR_baseline = average of ATR[1..N]   // 3-5 bar average, not current bar
expansion_ratio = ATR_current / ATR_baseline
if (expansion_ratio >= 1.5)
    NewTP = TP - (ATR_current - ATR_baseline) * multiplier
```
Only widen if `|NewTP - TP| > Step_ATR * ATR` to avoid noise chasing.

**4. Proportional Trailing (final leg)**
```
TrailingDistance = |CurrentPrice - OpenPrice| * Ratio - Spread
```
Ratio tightens as proximity to TP increases. Reserve for entry-to-70% phase only.

### MQL5 Functions for Implementation

| Function | Purpose |
|---|---|
| `iATR(_Symbol, PERIOD_M5, 14)` | Baseline volatility handle — already in FORGE as `g_mtf[0].h_atr` |
| `iMomentum(_Symbol, PERIOD_M5, N, PRICE_CLOSE)` | Direct price velocity (new handle needed) |
| `CopyBuffer(g_mtf[0].h_atr, 0, 1, 1, buf)` | Prior bar ATR — internal, no new handle |
| `PositionGetDouble(POSITION_PRICE_OPEN)` | Entry price from existing `g_pos` object |
| `PositionGetDouble(POSITION_TP)` | Current TP from existing `g_pos` object |
| `g_trade.PositionModify(ticket, sl, tp)` | Apply new SL/TP — existing `g_trade` object |
| `SymbolInfoDouble(_Symbol, SYMBOL_SPREAD)` | Spread for BE offset |
| `TimeCurrent()` | For velocity window timing |

**Key FORGE advantage:** `g_mtf[0].h_atr` already holds the M5 ATR handle — prior bar ATR via `CopyBuffer(..., 1, 1, buf)` is the only new call needed. No new indicator initialization required for Phase 1 or Phase 3.

### Risk Considerations from Research

1. **Spread offset required:** BE SL must be `EntryPrice - Spread` (for SELL), not exactly at entry. Without offset, broker will stop out immediately on spread fluctuation.
2. **Use 3-5 bar ATR average, not single bar:** Single bar ATR spikes (one big candle) can trigger false expansion signals. Average `ATR[1..3]` as baseline.
3. **Never trail in the 80-100% proximity zone:** MQL5 community recommends BE-only (not trail) at 80%. Reserve trailing for the entry-to-70% phase. Over-tightening near TP stops legitimate continuations.
4. **Bar-change throttle for `PositionModify`:** Broker rejects rapid `OrderModify` calls in `OnTick()`. Use `if(_adx_bar != g_last_modify_bar)` pattern (same as ADX gate log throttle) — modify once per M5 bar maximum.
5. **Counter-trades excluded:** MQL5 community notes double-exposure EAs amplify losses when the counter-trade direction also fails. Avoided entirely in this plan.

### Published Reference Implementations

- [Trailing Stop on Profit EA (EarnForex)](https://github.com/EarnForex/Trailing-Stop-on-Profit) — activates trailing only after profit threshold; directly applicable to 80%-to-TP trigger
- [Adaptive ATR Trailing Stop](https://www.mql5.com/en/market/product/152421) — runtime ATR recalculation with step filter
- [Trade Manager Auto SLTP Trailing](https://www.mql5.com/en/market/product/152607) — complete SL/TP management suite

---

---

## Updated Research Findings — 2026-05-08 (Post Run 17 G21 Analysis)

*Source: MQL5 Articles 19911, 17957, 134; MQL5 Book (Trailing Stop, Spreads); MQL5 Forum threads 435220, 392046, 509407*

### G21 Stop-Hunt Anatomy

| Event | Price | Notes |
|-------|-------|-------|
| SELL entry | 4609.15 | ADX 28.8, RSI 36.1 |
| Favorable move toward TP | ~4580-4590 | Price moved ~19-30 pts in favor |
| Violent reversal | 4609 → 4618.94 | +9.79 pts adverse in 49 min |
| Stop-out | 4618.94 | -$40.38 (2 legs) |
| After stop-hunt | 4618 → 4565 | Original SELL direction resumed (-$53 pts) |

If `sl_be_proximity_pct` had fired at 75-80% of TP1 distance, SL would move to breakeven (~4609.40) before the reversal. Exit would be ~$0 instead of -$40.

---

### Critical Correction to Phase 1 Plan

**The original plan used `entry_price` as the BE SL level — this is WRONG.**

For a SELL position:
- Position opens at **Bid**; closes via SL at **Ask**
- Setting SL exactly at entry means: as soon as Ask > Bid crosses entry → immediate stop-out on the spread
- Correct formula: `bePrice = entryPrice + spread + stopLevel` (for SELL)

```mql5
double spread    = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) * _Point;
double stopLvl   = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
double beSL_sell = entryPrice + spread + stopLvl;  // slightly above entry
```

For XAUUSD with typical spread 20-30 pts: `beSL_sell ≈ entryPrice + 0.25 to 0.35`.

---

### Critical Correction: State Flag Required

The original plan had no `beTriggered` flag — the proximity check would fire every tick once triggered, spamming `PositionModify` calls. Brokers return **Error 4756** (too frequent) or **Error 10016** (invalid stops) on rapid modification.

**Correct pattern (one-shot per position):**
```mql5
// Per-position state (in g_groups[] struct or parallel array)
bool be_proximity_triggered;  // false on group open, true after BE fires once

// In ManageOpenGroups() — per-position tick check:
if(!be_proximity_triggered && traveled >= proximity_pct * tp_dist) {
    double beSL = entryPrice + spread + stopLevel;  // SELL: above entry by spread+freeze
    g_trade.PositionModify(ticket, beSL, tp);
    be_proximity_triggered = true;  // never fires again for this position
}
```

---

### BID vs ASK — Correct Price for Each Check

| Check | Price | Reason |
|-------|-------|--------|
| Proximity trigger condition | **BID** | SELL P&L tracks BID (position value) |
| BE SL level | `entry + spread + stopLevel` | SL fires when ASK crosses; must be above entry by spread |
| HWM tracking | **BID** | Lowest BID = best SELL progress |
| HWM trail SL | `hwm + trail_pts + spread` | SL fires at ASK; add spread so it doesn't immediately fire |

```mql5
double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
double traveled = entryPrice - bid;          // SELL: positive when favorable
double tp_dist  = entryPrice - tp1_price;   // SELL: entry - tp1 (positive)
```

---

### PositionModify Throttling — Hybrid Approach (Research Consensus)

| Mechanism | Frequency | Rationale |
|-----------|-----------|-----------|
| Proximity BE trigger | **Every tick** | One-shot; state flag prevents spam |
| HWM high-water-mark update | **Every tick** | Must track intra-bar lows for SELL |
| HWM trail SL modification | **Once per M5 bar** | Broker-safe; `iTime(M5,0) != lastBarTime` guard |

---

### Corrected Phase 1 Implementation (Production-Grade)

```mql5
// --- In g_groups[] struct: add ---
// bool be_proximity_triggered;  // reset false on group open

// --- In ManageOpenGroups(), inside per-position loop ---
if(g_sc.sl_be_proximity_pct > 0) {
    bool apply = (g_pos.PositionType()==POSITION_TYPE_SELL && g_sc.sl_be_proximity_apply_sell)
              || (g_pos.PositionType()==POSITION_TYPE_BUY  && g_sc.sl_be_proximity_apply_buy);
    if(apply && !g_groups[gi].be_proximity_triggered) {
        double entry  = g_pos.PriceOpen();
        double tp1    = g_groups[gi].tp1;
        double cur_sl = g_pos.StopLoss();
        double point  = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
        double spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) * point;
        double stopLv = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * point;
        double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);

        if(g_pos.PositionType() == POSITION_TYPE_SELL) {
            double tp_dist  = entry - tp1;        // positive: how far to TP
            double traveled = entry - bid;         // positive: how far price moved favorably
            if(tp_dist > 0 && traveled / tp_dist >= g_sc.sl_be_proximity_pct / 100.0) {
                double be_sl = entry + spread + stopLv;  // above entry by spread buffer
                if(cur_sl == 0 || be_sl < cur_sl) {     // only move SL more favorable
                    if(g_trade.PositionModify(g_pos.Ticket(), NormalizeDouble(be_sl,_Digits), g_pos.TakeProfit())) {
                        g_groups[gi].be_proximity_triggered = true;
                        PrintFormat("FORGE BE-PROXIMITY: group %d SELL SL→%.5f (%.0f%% to TP1)",
                                    g_groups[gi].id, be_sl, g_sc.sl_be_proximity_pct);
                    }
                }
            }
        }
        // BUY mirror: if(apply_buy) { ... entry < bid; tp_dist = tp1-entry; ... be_sl = entry - spread - stopLv; }
    }
}
```

---

### Phase 1 Config Items (Final)

```json
"safety": {
  "sl_be_proximity_pct": 80,
  "sl_be_proximity_apply_sell": 1,
  "sl_be_proximity_apply_buy": 0
}
```

- `sl_be_proximity_pct`: 70–80 is community standard. 80 is conservative (only triggers very close to TP). 70 gives more buffer for the reversal.
- Spread offset and stop level are computed from broker at runtime — no config needed.
- `be_proximity_triggered` flag per group/position — must be stored in `g_groups[]` struct.

---

### Impact on G21

| | Without Phase 1 | With Phase 1 (80%) |
|--|----------------|---------------------|
| Entry | 4609.15 SELL | 4609.15 SELL |
| Price moves to ~4585 (24 pts, ~80% of TP) | — | BE fires: SL → 4609.40 |
| Price reverses to 4618.94 | SL hit: -$40.38 | SL hit: ~$0 (breakeven) |
| Saved | — | **+$40.38** |

*Last updated: 2026-05-08*
