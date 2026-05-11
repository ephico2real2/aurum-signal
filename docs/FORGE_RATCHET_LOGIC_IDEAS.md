Here's the complete spec for the multi-leg entry system.

## 1. Data structures

```
PositionLeg {
    ulong    ticket
    int      leg_index           // 0, 1, 2
    double   volume              // actual filled lots
    double   entry_price         // actual fill, not signal price
    double   initial_sl
    double   current_sl
    double   tp_target           // tp1, tp2, or tp3
    bool     is_open
    datetime open_time
}

PositionGroup {
    string   group_id            // unique: timestamp + signal hash
    int      magic_number
    string   symbol
    int      direction           // +1 BUY, -1 SELL
    double   entry_price_ref     // reference entry (usually leg 0 fill)
    double   initial_sl
    double   tp1, tp2, tp3
    double   atr_at_entry

    PositionLeg legs[]           // 3 legs by default

    bool     tp1_passed
    bool     tp2_passed
    bool     tp3_passed

    double   peak_price          // highest bid (BUY) / lowest ask (SELL)
    datetime created_at
}

groups[]                         // collection of active groups
```

Persist `groups[]` to a file or MT5 global variables so the EA can rebuild state after a restart.

## 2. Configuration inputs

```
// Multi-leg structure
input int     NumLegs              = 3;
input string  LegVolumeShares      = "0.50,0.30,0.20";   // must sum to 1.0
input string  LegTpAtrMults        = "1.0,1.8,3.0";      // ATR multipliers per leg

// SL management
input double  InitialSlAtrMult     = 1.2;
input double  Tp1LockBufferPips    = 3.0;                // SL = entry ± this after TP1
input bool    EnableAtrTrail       = true;
input double  TrailAtrMult         = 1.5;

// Risk / sizing
input double  RiskPercentPerGroup  = 0.5;                // % of equity per signal
input double  MinLegVolume         = 0.01;
input double  LotStep              = 0.01;

// Operational
input int     MagicNumber          = 270501;
input string  CommentPrefix        = "FORGE";
input int     MaxConcurrentGroups  = 3;
input bool    HedgingAccount       = true;               // false = netting (US brokers)
```

## 3. Entry flow — step by step

When a signal fires (BUY or SELL):

```
1.  Read ATR(period) at signal bar             → atr
2.  Read parsed leg shares                     → shares[] = [0.50, 0.30, 0.20]
3.  Read parsed leg TP multipliers             → tp_mults[] = [1.0, 1.8, 3.0]
4.  Compute target levels:
       BUY:  tp1 = E + tp_mults[0] * atr
             tp2 = E + tp_mults[1] * atr
             tp3 = E + tp_mults[2] * atr
             initial_sl = E - InitialSlAtrMult * atr
       SELL: tp1 = E - tp_mults[0] * atr
             tp2 = E - tp_mults[1] * atr
             tp3 = E - tp_mults[2] * atr
             initial_sl = E + InitialSlAtrMult * atr

5.  Check R:R gate (your existing logic). Abort if fail.

6.  Compute total volume V from risk:
       risk_money = equity * RiskPercentPerGroup / 100
       sl_distance_price = |E - initial_sl|
       sl_distance_money_per_lot = sl_distance_price * contract_size
       V = risk_money / sl_distance_money_per_lot
       V = floor_to_step(V, LotStep)

7.  Split V into legs:
       leg_vols[i] = floor_to_step(V * shares[i], LotStep)
       
       Validate each leg_vols[i] >= MinLegVolume.
       If any leg fails minimum:
         - If 3 legs cant fit, drop to 2 legs (combine smallest into adjacent)
         - If 2 legs cant fit, fire single leg targeting tp2
         - If single leg cant meet minimum, abort signal

8.  Generate group_id (e.g., 8-char hash of timestamp + symbol + direction)

9.  Fire NumLegs OrderSend requests:
       for i in 0..NumLegs-1:
           order = {
               type:     BUY or SELL (market)
               symbol:   current symbol
               volume:   leg_vols[i]
               sl:       initial_sl       // same on all legs
               tp:       tp[i+1]          // tp1, tp2, tp3
               magic:    MagicNumber
               comment:  "FORGE_<group_id>_L<i>"
           }
           Send order, capture ticket.
           
       If any leg fails to fill: log, mark leg as failed in group, continue.

10. Build PositionGroup object with all filled legs, set milestone flags false.
    Append to groups[]. Persist to disk.
```

## 4. Tick loop — monitoring open groups

```
on_tick:
    bid = SymbolInfoDouble(symbol, SYMBOL_BID)
    ask = SymbolInfoDouble(symbol, SYMBOL_ASK)

    for each group in groups[]:
        refresh_group_state(group)              // check which legs still open
        
        if group has no open legs:
            mark group complete, remove from active list
            (optionally trigger cascade re-entry here)
            continue
        
        if group.direction == BUY:
            apply_buy_ratchet(group, bid)
        else:
            apply_sell_ratchet(group, ask)
```

## 5. BUY ratchet logic

```
apply_buy_ratchet(group, bid):
    group.peak = max(group.peak, bid)

    # === MILESTONE 1 ===
    if NOT group.tp1_passed AND bid >= group.tp1:
        new_sl = group.entry_price_ref + Tp1LockBufferPips * point
        ratchet_all_open_legs(group, new_sl, direction=BUY)
        group.tp1_passed = true

    # === MILESTONE 2 ===
    if NOT group.tp2_passed AND bid >= group.tp2:
        new_sl = group.tp1
        ratchet_all_open_legs(group, new_sl, direction=BUY)
        group.tp2_passed = true

    # === MILESTONE 3 ===
    # No SL action needed - last surviving leg's TP = tp3, broker closes it.
    if NOT group.tp3_passed AND bid >= group.tp3:
        group.tp3_passed = true

    # === OPTIONAL: ATR trail between milestones ===
    if EnableAtrTrail AND group.tp1_passed:
        trail_sl = group.peak - TrailAtrMult * group.atr_at_entry
        ratchet_all_open_legs(group, trail_sl, direction=BUY)
```

## 6. SELL ratchet logic (mirror)

```
apply_sell_ratchet(group, ask):
    group.peak = min(group.peak, ask)         # peak is LOWEST seen

    # === MILESTONE 1 ===
    if NOT group.tp1_passed AND ask <= group.tp1:
        new_sl = group.entry_price_ref - Tp1LockBufferPips * point
        ratchet_all_open_legs(group, new_sl, direction=SELL)
        group.tp1_passed = true

    # === MILESTONE 2 ===
    if NOT group.tp2_passed AND ask <= group.tp2:
        new_sl = group.tp1
        ratchet_all_open_legs(group, new_sl, direction=SELL)
        group.tp2_passed = true

    # === MILESTONE 3 ===
    if NOT group.tp3_passed AND ask <= group.tp3:
        group.tp3_passed = true

    # === OPTIONAL: ATR trail between milestones ===
    if EnableAtrTrail AND group.tp1_passed:
        trail_sl = group.peak + TrailAtrMult * group.atr_at_entry
        ratchet_all_open_legs(group, trail_sl, direction=SELL)
```

## 7. The SL ratchet helper — the safety gate

```
ratchet_all_open_legs(group, new_sl, direction):
    for each leg in group.legs:
        if NOT leg.is_open:
            continue
        
        # The invariant - SL only moves in profit direction
        if direction == BUY:
            if new_sl <= leg.current_sl:
                continue                      # would worsen, skip
        else:  # SELL
            if new_sl >= leg.current_sl:
                continue                      # would worsen, skip
        
        # Skip if change is below broker's min stop distance
        if |new_sl - leg.current_sl| < MinSlModifyDistance:
            continue
        
        result = OrderModify(leg.ticket, leg.entry_price, new_sl, leg.tp_target)
        if result == OK:
            leg.current_sl = new_sl
        else:
            log_error("SL ratchet failed", leg.ticket, error_code)
```

## 8. State refresh — handling broker-side closes

```
refresh_group_state(group):
    for each leg in group.legs:
        if leg.is_open AND NOT PositionSelectByTicket(leg.ticket):
            # Broker closed this leg (hit TP or SL)
            leg.is_open = false
            close_price = HistoryDealGetDouble(...)
            log_leg_close(leg, close_price)
```

## 9. Restart recovery

```
on_init (EA startup):
    groups[] = load_from_disk()
    
    # Reconcile with actual open positions
    for each open position with our magic number:
        parse comment → extract group_id and leg_index
        find or create group in groups[]
        attach this position to the right leg slot
    
    # Mark any legs whose tickets no longer exist as closed
    for each group, for each leg:
        if leg.ticket not in open positions:
            leg.is_open = false
```

## 10. Edge cases to handle explicitly

| Situation | Handling |
|-----------|----------|
| Partial fill on entry (only 2 of 3 legs filled) | Proceed with the filled legs; mark missing leg failed. Group still works. |
| Min lot violation when splitting | Drop to 2 legs (combine into adjacent) or fire single leg. Don't silently fail. |
| Broker rejects SL modify | Log and retry next tick; don't crash group state. |
| EA restart mid-group | Rebuild from open positions via magic + comment parsing. |
| Stop level violation (SL too close to price) | Round SL to nearest valid level past stop_level. |
| Account is netting, not hedging | Fall back to single position with partial-close path, or refuse to run. |
| Two groups open same direction same symbol | Each tracked independently by group_id. SL ratchets per group. |
| One leg closes at SL while group is mid-flight | Group continues with remaining legs; milestone tracking unaffected. |

## 11. Worked example — BUY on gold

Conditions: Gold at **2400.00**, ATR = 5.00, equity $10,000, risk 0.5% per group.

**Entry calculation:**
- Risk money = $50
- Initial SL distance = 1.2 × 5.00 = 6.00 → SL = **2394.00**
- $/lot per $1 move on XAUUSD = $100
- SL $/lot = 6.00 × $100 = $600/lot
- Total V = $50 / $600 = 0.083 → rounded to **0.08**

**Leg split:**
- Leg A: 0.08 × 0.50 = 0.04
- Leg B: 0.08 × 0.30 = 0.024 → 0.02
- Leg C: 0.08 × 0.20 = 0.016 → 0.02

**Targets:**
- tp1 = 2400 + 1.0 × 5.00 = **2405.00**
- tp2 = 2400 + 1.8 × 5.00 = **2409.00**
- tp3 = 2400 + 3.0 × 5.00 = **2415.00**

**Orders fired:**

| Leg | Vol  | Entry  | SL     | TP     |
|-----|------|--------|--------|--------|
| A   | 0.04 | 2400.00| 2394.00| 2405.00|
| B   | 0.02 | 2400.00| 2394.00| 2409.00|
| C   | 0.02 | 2400.00| 2394.00| 2415.00|

**Price action — full run-through:**

| Event | Bid hits | Leg A | Leg B | Leg C |
|-------|----------|-------|-------|-------|
| Start | —        | open, SL 2394 | open, SL 2394 | open, SL 2394 |
| TP1 crossed | 2405 | **closed** at 2405 (+$20) | SL → 2400.30 | SL → 2400.30 |
| TP2 crossed | 2409 | (closed) | **closed** at 2409 (+$18) | SL → 2405.00 |
| TP3 crossed | 2415 | (closed) | (closed) | **closed** at 2415 (+$30) |

**Total: +$68 on $50 risked.**

**Reversal scenario after TP1:**

| Event | Bid | Leg A | Leg B | Leg C |
|-------|-----|-------|-------|-------|
| TP1 crossed | 2405 | closed +$20 | SL → 2400.30 | SL → 2400.30 |
| Reversal hits new SL | 2400.30 | (closed) | **closed +$0.60** | **closed +$0.60** |

**Total: +$21.20.** Trade is risk-free the moment TP1 fires.

## 12. SELL mirror — same example flipped

Gold at 2400.00, SELL signal, ATR = 5.00:

| Leg | Vol  | Entry  | SL     | TP     |
|-----|------|--------|--------|--------|
| A   | 0.04 | 2400.00| 2406.00| 2395.00|
| B   | 0.02 | 2400.00| 2406.00| 2391.00|
| C   | 0.02 | 2400.00| 2406.00| 2385.00|

| Event | Ask hits | Leg A | Leg B | Leg C |
|-------|----------|-------|-------|-------|
| TP1 crossed | 2395 | closed at 2395 | SL → 2399.70 | SL → 2399.70 |
| TP2 crossed | 2391 | (closed) | closed at 2391 | SL → 2395.00 |
| TP3 crossed | 2385 | (closed) | (closed) | closed at 2385 |

## 13. Integration with existing systems

**Fast-lock:** Operates per-leg, alongside the milestone ratchet. The combined SL is:

```
BUY:  final_sl = max(milestone_sl, fast_lock_sl, current_sl)
SELL: final_sl = min(milestone_sl, fast_lock_sl, current_sl)
```

Fast-lock can push SL further into profit. It cannot pull SL back below the milestone floor.

**Cascade re-entry (your SELL STOP CONT):** Triggers when an entire group completes — i.e., all legs closed, whether by TP or SL. The cascade looks for re-entry conditions only after `group.all_legs_closed == true`.

**R:R gate:** Runs in step 5 of the entry flow. Uses tp2 (the "expected center of mass" of the trade) for the R:R calculation, since that's roughly where the volume-weighted exit lands.

## 14. The patch you hand Claude Code

> Implement multi-leg entry per the spec. On entry signal: compute tp1/tp2/tp3 from ATR multipliers, compute initial SL, size total volume V from risk, split V into N legs by configured shares (default 3 legs at 50/30/20), validate each leg meets min lot, fire one OrderSend per leg with the same magic and SL but different TPs (tp1/tp2/tp3), tag each order's comment with a shared group_id and leg_index. Maintain a `PositionGroup` per signal, tracking milestone flags (tp1_passed, tp2_passed, tp3_passed) and peak price. On each tick, for each group: refresh leg open/close state from the broker; if bid crosses tp1 (BUY) or ask crosses tp1 (SELL), ratchet SL on all open legs to entry±lock_buffer; if tp2 crossed, ratchet to tp1 level; if tp3 crossed, broker closes last leg. Enforce SL invariant in `ratchet_all_open_legs`: BUY only raises SL, SELL only lowers SL. Optional ATR trail between milestones using peak/trough tracking. Persist groups to disk; on EA init, rebuild groups from open positions tagged with our magic. Coexist with fast-lock by always taking max(milestone_sl, fast_lock_sl) for BUY and min for SELL. Add inputs: NumLegs, LegVolumeShares, LegTpAtrMults, Tp1LockBufferPips, EnableAtrTrail, TrailAtrMult, MaxConcurrentGroups.
