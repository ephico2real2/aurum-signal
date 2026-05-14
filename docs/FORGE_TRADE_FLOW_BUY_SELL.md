# FORGE Trade Flow — BUY + SELL lifecycle (v2.7.102 All-Phases-On)

**Created**: 2026-05-14
**EA version**: FORGE v2.7.102
**Status**: ALL-PHASES-ON active in `.env` (12 knobs flipped per docs/FORGE_v2.7.95-2.7.102_ROLLOUT_PLAN.md)
**Audience**: operator + future analyst reading the multi-leg / cool-period / direction-lock system
**References**: docs/FORGE_CORE_LOGIC_DESIGN.md, docs/FORGE_v2.7.95-2.7.102_ROLLOUT_PLAN.md

---

## §0 Execution model — at a glance

The single most important clarification:

> **Leg 1 is ALWAYS a market order.** It is never a pending. You do not need a BUY_LIMIT (or any limit/stop) to trigger a trade. The pending orders in this system are *continuation* legs that get placed AFTER Leg 1's TP1 hits — they capture follow-through, not initial entry.

| Order class | When placed | Order type | Fills when |
|---|---|---|---|
| **Leg 1 entry** (BUY or SELL trigger) | Setup composite fires + gates pass | **Market order** via `g_trade.Buy/Sell` or `PlaceMarketBatch` ×4 (v2.7.99) | Immediately at current bid/ask |
| **Cascade slots 2-8** (continuation) | TP1 of Leg 1 hits | `BUY_STOP` (BUY setup) or `SELL_STOP` (SELL setup) — pending | Price touches trigger AND structure still valid |
| **Recovery slot 9** (counter-trend) | TP1 of Leg 1 hits | `SELL_LIMIT` (BUY TP1) or `BUY_LIMIT` (SELL TP1) — pending | Price touches trigger AND structure still valid |

---

## §1 BUY trade flow (v2.7.102 All-Phases-On)

```
═══════════════════════════════════════════════════════════════════════════════
T=0   SIGNAL TICK — BUY setup composite fires
      (e.g., BB_BREAKOUT BUY, MOMENTUM_DUMP BUY, etc.)
═══════════════════════════════════════════════════════════════════════════════
                                  │
                                  ▼
                  ┌────────────────────────────────┐
                  │  Pre-fire entry gate chain     │ ea/FORGE.mq5:~12734
                  │  (UMCG → CVCSM → DIR LOCK)     │
                  └────────────────────────────────┘
                                  │
              ┌───────────────────┴───────────────────┐
              ▼                                       ▼
   pemcg_buy_warning_count                IsDirLockBlocked("BUY")
   < umcg_buy_block_threshold (5)?        False?  (state IDLE or ARMED,
              │                            no bilateral cooldown active)
              └───────────────────┬───────────────────┘
                                  ▼
                              PROCEED
                                  │
                                  ▼
              ┌────────────────────────────────────────────┐
              │  EnterScalperGroup() — register the group  │ ea/FORGE.mq5:~13662
              │  • Compute entry_swing_high/low (5 M5 bars)│
              │  • direction_lock_broken=false              │
              │  • TRANSITION: dirlock_state_buy IDLE→ARMED│
              │  • TP1 = entry + max(40 pips, 0.4×ATR)     │  v2.7.102 floor
              │  • TP2 = entry + max(60 pips, 1.0×ATR)     │
              │  • TP3 = entry + 2.5×ATR (extends later)   │  v2.7.100 dynamic
              └────────────────────────────────────────────┘
                                  │
                                  ▼
              ┌────────────────────────────────────────────┐
              │  PlaceOpenGroupLeg(BUY_MARKET, leg_index=0)│ ea/FORGE.mq5:~14930
              │                                            │
              │  batch_size = 4 ► PlaceMarketBatch()       │ ea/FORGE.mq5:~14613
              │                                            │
              │   ┌──── per_leg_lot = target_lot / 4 ──┐   │
              │   │  OrderSend BUY @ market (Leg L1)   │   │ ← magic = group_magic
              │   │  OrderSend BUY @ market (Leg L2)   │   │ ← same magic
              │   │  OrderSend BUY @ market (Leg L3)   │   │ ← same magic
              │   │  OrderSend BUY @ market (Leg L4)   │   │ ← same magic
              │   └────────────────────────────────────┘   │
              │                                            │
              │  4 separate position TICKETS (hedge mode)  │
              │  All share same group_magic — GetGroup-    │
              │  Positions() returns all 4 for management  │
              └────────────────────────────────────────────┘
                                  │
                                  ▼ no pendings yet — only 4 market positions

═══════════════════════════════════════════════════════════════════════════════
T+N   PRICE MOVES UP (favorable for BUY)
═══════════════════════════════════════════════════════════════════════════════

Every M5 close (300s cadence):
  ┌────────────────────────────────────────────────────────────────┐
  │  UpdateDirLockState("BUY")                                     │ ea/FORGE.mq5:~14310
  │  ┌── EvaluateDirectionLock("BUY", gi) ──┐                      │
  │  │  Trigger 1: m5_close < entry_swing_   │                      │
  │  │             low − 0.5×ATR? → INVALID   │ (ICT MSS body-close)│
  │  │  Trigger 2a: pemcg_sell ≥ 5? → INVALID│ (opposite flip)     │
  │  │  Trigger 2b: pemcg both ≥ 3? → NEUTRAL│ (bilateral chop)    │
  │  │  Trigger 2c: h1_trend < −0.5?→ INVALID│ (HTF disagreement)  │
  │  │  Trigger 3: tp3_hit/all_closed?       │ → PROFIT_TARGET     │
  │  │             → DLV_PROFIT_TARGET        │                     │
  │  └────────────────┬──────────────────────┘                     │
  │                   │                                            │
  │   verdict=VALID ──┴── verdict ∈ {INVALID, NEUTRAL} ► DISCARDED │
  └──────────────────┬──────────────────────────────┬──────────────┘
                     │                              │
              keep ARMED                  ┌─── all happen ────┐
                                          ▼                   ▼
                                   cancel pendings   bilateral cooldown
                                                     starts (g_dirlock_last_break_time)

T+M   Price touches TP1 (= entry + max(40 pips, 0.4×ATR))
                                  │
                                  ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  ManageOpenGroups() TP1 branch         ea/FORGE.mq5:~2872      │
  │  • Close 50% of 4 positions = 2 of 4 (FIFO order)              │
  │  • Remaining 2 legs: SL → entry + 0.3×ATR cushion (per leg)    │
  │  • Mark tp1_hit = true                                         │
  │  • ArmPostTP1Ladder() ────────────────────────────────────┐    │
  └──────────────────────────────────────────────────────────│────┘
                                                              │
                                  ┌───────────────────────────┘
                                  ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  ArmPostTP1Ladder() — direction == "BUY"  (v2.7.95 NEW branch) │ ea/FORGE.mq5:~14017
  │                                                                │
  │  Arm-time gates (all must pass to place pendings):             │
  │   • cur_rsi < buy_stop_cont_max_rsi (75)? — not exhausted top  │
  │   • cur_adx ≥ buy_stop_cont_min_adx (25)? — trend confirmed    │
  │   • H1 DI+ > DI−?  (require_h1_di_buy)   — HTF bullish        │
  │   • regime != "RANGE"?                    — TREND_BULL/VOLATILE│
  │                                                                │
  │  If all gates pass:                                            │
  │   for slot in 2..6:                                            │
  │      place BUY_STOP @ tp1 + 0.40×ATR  ┐                        │
  │      magic = group_magic + 30000 + slot│ (parallel stack)      │
  │      SL = bs_price − 1.5×ATR           │                        │
  │      TP = bs_price + 1.5×ATR           │ goes to g_buy_stop_stack[slot]
  │      expiration = TimeCurrent + 2×5min │                        │
  │      ─────────────────────────────────┘                        │
  │   place SELL_LIMIT recovery @ tp1 (slot 9, counter-trend pullback)│
  │                                                                │
  │  These are PENDING orders sitting in the broker book           │
  └────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
PARALLEL THREAD — every M5 close, while pendings are sitting
═══════════════════════════════════════════════════════════════════════════════
  ┌────────────────────────────────────────────────────────────────┐
  │  CancelPendingOnStructureFlip()  v2.7.101 Set 4 Option 4B      │ ea/FORGE.mq5:~14282
  │                                                                │
  │  for each group with active cascade pendings:                  │
  │      verdict = EvaluateDirectionLock(direction, gi)            │
  │      if verdict ∈ {INVALID, NEUTRAL}:                          │
  │          for slot in 2..9:                                     │
  │              if g_buy_stop_stack[slot].group_id == gi.id:      │
  │                  OrderDelete(slot.ticket) ───► PENDING KILLED  │ ◄── THE FIX
  │              if g_sell_limit_stack[slot].group_id == gi.id:    │
  │                  OrderDelete(slot.ticket) ───► PENDING KILLED  │
  │          g_groups[gi].direction_lock_broken = true             │
  └────────────────────────────────────────────────────────────────┘
    ↑ This replaces the old "blind timer expiry" — pendings now die
      when structure flips, not just when the clock runs out.

═══════════════════════════════════════════════════════════════════════════════
T+P   PRICE CONTINUES UP → TP2 touched (entry + max(60 pips, 1.0×ATR))
═══════════════════════════════════════════════════════════════════════════════
  ┌────────────────────────────────────────────────────────────────┐
  │  ManageOpenGroups() TP2 branch         ea/FORGE.mq5:~3008      │
  │                                                                │
  │  v2.7.96 Set 2 — TP2 banking close (NEW):                      │
  │   • Close ceil(2 × 25%) = 1 of 2 remaining positions           │
  │   • 1 leg still open                                           │
  │                                                                │
  │  Existing M2 ratchet:                                          │
  │   • SL of remaining 1 leg → TP1 price (locks TP1 profit)       │
  │   • TP promoted to TP3                                         │
  │  Mark tp2_hit = true                                           │
  └────────────────────────────────────────────────────────────────┘

T+Q   PRICE CONTINUES UP — ATR trail engaged (every tick, continuous)
  ┌────────────────────────────────────────────────────────────────┐
  │  ATR trail block            ea/FORGE.mq5:~3253                 │
  │                                                                │
  │  trail_sl = peak_price − 1.5×ATR  (BUY raises SL only)         │
  │                                                                │
  │  v2.7.100 Set 3 Option 3C (tp3_mode=1):                        │
  │   ALSO: new_tp3 = trail_sl + 2.0×ATR                           │
  │        TP3 extends UP only (BUY direction-preserving invariant)│
  │   PositionModify(remaining_leg, sl=trail_sl, tp=new_tp3)       │
  └────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
TIMELINE — what happens to cascade pendings AFTER TP1 placement
═══════════════════════════════════════════════════════════════════════════════

Pendings placed at TP1 fire-moment (arm-time gates passed):
    ┌─── BUY_STOP slot 2 @ tp1 + 0.40×ATR ───┐
    │   BUY_STOP slot 3 @ tp1 + 0.40×ATR     │
    │   BUY_STOP slot 4 @ tp1 + 0.40×ATR     │ ...sitting in broker book
    │   BUY_STOP slot 5 @ tp1 + 0.40×ATR     │ ...with broker-side timer expiry
    │   BUY_STOP slot 6 @ tp1 + 0.40×ATR     │ ...AND EA-side structural cancel
    │   SELL_LIMIT slot 9 @ tp1 (recovery)   │
    └────────────────────────────────────────┘
                       │
                       ▼ Every M5 close (every 5 min):
            ┌─────────────────────────────┐
            │ EvaluateDirectionLock("BUY")│
            └──────────┬──────────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
   verdict=VALID                verdict=INVALID/NEUTRAL
   pendings stay alive          OrderDelete() each pending ──► ALL CANCELLED
                                g_groups[gi].direction_lock_broken=true
                                bilateral cooldown blocks new triggers
                                                ↓
                                  ┌─────────────────────────────┐
                                  │  After 2 M5 bars (10 min):  │
                                  │  state DISCARDED → IDLE     │
                                  │  Fresh BUY signal needed.   │
                                  │  No auto-flip to SELL —     │
                                  │  SELL also needs fresh      │
                                  │  signal + clean PEMCG.      │
                                  └─────────────────────────────┘
```

---

## §2 SELL trade flow (mirror of BUY)

```
═══════════════════════════════════════════════════════════════════════════════
T=0   SIGNAL TICK — SELL setup composite fires
      (e.g., BB_BREAKOUT SELL, MOMENTUM_DUMP SELL, FRACTIONAL_SELL_IN_BULL, etc.)
═══════════════════════════════════════════════════════════════════════════════
                                  │
                                  ▼
                  ┌────────────────────────────────┐
                  │  Pre-fire entry gate chain     │ ea/FORGE.mq5:~12734
                  │  (UMCG → CVCSM → DIR LOCK)     │
                  └────────────────────────────────┘
                                  │
              ┌───────────────────┴───────────────────┐
              ▼                                       ▼
   pemcg_sell_warning_count               IsDirLockBlocked("SELL")
   < umcg_sell_block_threshold (5)?       False?  (state IDLE or ARMED,
              │                            no bilateral cooldown active)
              └───────────────────┬───────────────────┘
                                  ▼
                              PROCEED
                                  │
                                  ▼
              ┌────────────────────────────────────────────┐
              │  EnterScalperGroup() — register the group  │ ea/FORGE.mq5:~13662
              │  • Compute entry_swing_high/low (5 M5 bars)│
              │  • direction_lock_broken=false              │
              │  • TRANSITION: dirlock_state_sell IDLE→ARMED│
              │  • TP1 = entry − max(40 pips, 0.4×ATR)     │  v2.7.102 floor
              │  • TP2 = entry − max(60 pips, 1.0×ATR)     │
              │  • TP3 = entry − 2.5×ATR (extends later)   │  v2.7.100 dynamic
              └────────────────────────────────────────────┘
                                  │
                                  ▼
              ┌────────────────────────────────────────────┐
              │  PlaceOpenGroupLeg(SELL_MARKET, leg_index=0)│ ea/FORGE.mq5:~14971
              │                                            │
              │  batch_size = 4 ► PlaceMarketBatch()       │
              │                                            │
              │   ┌──── per_leg_lot = target_lot / 4 ──┐   │
              │   │  OrderSend SELL @ market (Leg L1)  │   │
              │   │  OrderSend SELL @ market (Leg L2)  │   │
              │   │  OrderSend SELL @ market (Leg L3)  │   │
              │   │  OrderSend SELL @ market (Leg L4)  │   │
              │   └────────────────────────────────────┘   │
              │                                            │
              │  4 separate position TICKETS (hedge mode)  │
              │  All share same group_magic                │
              └────────────────────────────────────────────┘
                                  │
                                  ▼ no pendings yet — only 4 market positions

═══════════════════════════════════════════════════════════════════════════════
T+N   PRICE MOVES DOWN (favorable for SELL)
═══════════════════════════════════════════════════════════════════════════════

Every M5 close (300s cadence):
  ┌────────────────────────────────────────────────────────────────┐
  │  UpdateDirLockState("SELL")                                    │
  │  ┌── EvaluateDirectionLock("SELL", gi) ──┐                     │
  │  │  Trigger 1: m5_close > entry_swing_    │                     │
  │  │             high + 0.5×ATR? → INVALID  │ ICT MSS body-close  │
  │  │  Trigger 2a: pemcg_buy ≥ 5? → INVALID  │ opposite flip       │
  │  │  Trigger 2b: pemcg both ≥ 3? → NEUTRAL │ bilateral chop      │
  │  │  Trigger 2c: h1_trend > +0.5? → INVALID│ HTF disagreement    │
  │  │  Trigger 3: tp3_hit/all_closed?        │ → PROFIT_TARGET     │
  │  │             → DLV_PROFIT_TARGET         │                     │
  │  └────────────────┬──────────────────────┘                     │
  │                   │                                            │
  │   verdict=VALID ──┴── verdict ∈ {INVALID, NEUTRAL} ► DISCARDED │
  └──────────────────┬──────────────────────────────┬──────────────┘
                     │                              │
              keep ARMED                  ┌─── all happen ────┐
                                          ▼                   ▼
                                   cancel pendings   bilateral cooldown
                                                     starts

T+M   Price touches TP1 (= entry − max(40 pips, 0.4×ATR))
                                  │
                                  ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  ManageOpenGroups() TP1 branch         ea/FORGE.mq5:~2872      │
  │  • Close 50% of 4 positions = 2 of 4 (FIFO order)              │
  │  • Remaining 2 legs: SL → entry − 0.3×ATR cushion              │
  │    (SELL ratchets SL DOWN; cushion is ABOVE entry)             │
  │  • Mark tp1_hit = true                                         │
  │  • ArmPostTP1Ladder() ────────────────────────────────────┐    │
  └──────────────────────────────────────────────────────────│────┘
                                                              │
                                  ┌───────────────────────────┘
                                  ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  ArmPostTP1Ladder() — direction == "SELL"  (legacy branch)     │ ea/FORGE.mq5:~13837
  │                                                                │
  │  Arm-time gates (all must pass to place pendings):             │
  │   • cur_rsi > sell_stop_cont_min_rsi (25)? — not exhausted oversold│
  │   • cur_adx ≥ sell_stop_cont_min_adx (25)? — trend confirmed   │
  │   • H1 DI− > DI+? (require_h1_di_sell)   — HTF bearish        │
  │   • regime != "RANGE"?                    — TREND_BEAR/VOLATILE│
  │                                                                │
  │  If all gates pass:                                            │
  │   for slot in 2..6:                                            │
  │      place SELL_STOP @ tp1 − 0.40×ATR ┐                        │
  │      magic = group_magic + 20000 + slot│ (existing scheme)     │
  │      SL = ss_price + 1.5×ATR           │                        │
  │      TP = ss_price − 1.5×ATR           │ goes to g_sell_limit_stack[slot]
  │      expiration = TimeCurrent + 2×5min │                        │
  │      ─────────────────────────────────┘                        │
  │   place BUY_LIMIT recovery @ tp1 (slot 9, counter-trend bounce)│
  │                                                                │
  │  These are PENDING orders sitting in the broker book           │
  └────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
PARALLEL THREAD — every M5 close (same as BUY, iterates BOTH stacks)
═══════════════════════════════════════════════════════════════════════════════
  ┌────────────────────────────────────────────────────────────────┐
  │  CancelPendingOnStructureFlip()  v2.7.101 Set 4 Option 4B      │
  │                                                                │
  │  for each group with active cascade pendings:                  │
  │      verdict = EvaluateDirectionLock(direction, gi)            │
  │      if verdict ∈ {INVALID, NEUTRAL}:                          │
  │          for slot in 2..9:                                     │
  │              if g_sell_limit_stack[slot].group_id == gi.id:    │
  │                  OrderDelete(slot.ticket) ───► PENDING KILLED  │
  │              if g_buy_stop_stack[slot].group_id == gi.id:      │
  │                  OrderDelete(slot.ticket) ───► PENDING KILLED  │
  │          g_groups[gi].direction_lock_broken = true             │
  └────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
T+P   PRICE CONTINUES DOWN → TP2 touched (entry − max(60 pips, 1.0×ATR))
═══════════════════════════════════════════════════════════════════════════════
  ┌────────────────────────────────────────────────────────────────┐
  │  ManageOpenGroups() TP2 branch         ea/FORGE.mq5:~3008      │
  │                                                                │
  │  v2.7.96 Set 2 — TP2 banking close (NEW):                      │
  │   • Close ceil(2 × 25%) = 1 of 2 remaining positions           │
  │   • 1 leg still open                                           │
  │                                                                │
  │  Existing M2 ratchet (mirror):                                 │
  │   • SL of remaining 1 leg → TP1 price (locks TP1 profit)       │
  │     SELL: SL moves DOWN (lower price = more locked profit)     │
  │   • TP promoted to TP3                                         │
  │  Mark tp2_hit = true                                           │
  └────────────────────────────────────────────────────────────────┘

T+Q   PRICE CONTINUES DOWN — ATR trail engaged
  ┌────────────────────────────────────────────────────────────────┐
  │  ATR trail block            ea/FORGE.mq5:~3253                 │
  │                                                                │
  │  trail_sl = trough_price + 1.5×ATR  (SELL lowers SL only)      │
  │                                                                │
  │  v2.7.100 Set 3 Option 3C (tp3_mode=1):                        │
  │   ALSO: new_tp3 = trail_sl − 2.0×ATR                           │
  │        TP3 extends DOWN only (SELL invariant: never retract up)│
  │   PositionModify(remaining_leg, sl=trail_sl, tp=new_tp3)       │
  └────────────────────────────────────────────────────────────────┘
```

---

## §3 Side-by-side comparison (BUY vs SELL)

| Phase | BUY direction | SELL direction (mirror) |
|---|---|---|
| **Signal** | BB_BREAKOUT BUY, MOMENTUM_DUMP BUY, etc. fire | BB_BREAKOUT SELL, MOMENTUM_DUMP SELL, FRACTIONAL_SELL_IN_BULL, etc. fire |
| **UMCG gate** | `pemcg_buy_warning_count < 5` (Layer 1) | `pemcg_sell_warning_count < 5` (mirror) |
| **CVCSM gate** | `cvcsm_state_buy == 0` (OPEN) | `cvcsm_state_sell == 0` (mirror) |
| **DirLock gate** | `IsDirLockBlocked("BUY")` returns false | `IsDirLockBlocked("SELL")` returns false |
| **TP1 target** | entry + max(40 pips, 0.4×ATR) | entry − max(40 pips, 0.4×ATR) |
| **TP2 target** | entry + max(60 pips, 1.0×ATR) | entry − max(60 pips, 1.0×ATR) |
| **TP3 target (initial)** | entry + 2.5×ATR | entry − 2.5×ATR |
| **Leg 1 execution** | `PlaceMarketBatch("BUY", ...)` → 4× `OrderSend(BUY @ market)` | `PlaceMarketBatch("SELL", ...)` → 4× `OrderSend(SELL @ market)` |
| **Slot stack** | `g_buy_stop_stack[10]` (v2.7.95 NEW) | `g_sell_limit_stack[10]` (existed) |
| **Cascade legs (slots 2-8)** | `BUY_STOP` @ tp1 + 0.4×ATR | `SELL_STOP` @ tp1 − 0.4×ATR |
| **Counter-trend recovery (slot 9)** | `SELL_LIMIT` @ tp1 (v2.7.95 NEW) | `BUY_LIMIT` @ tp1 (existed) |
| **Cascade arm-time gates** | RSI < 75; ADX ≥ 25; H1 DI+ > DI−; regime != RANGE | RSI > 25; ADX ≥ 25; H1 DI− > DI+; regime != RANGE |
| **Structural break (Trigger 1)** | m5_close < entry_swing_low − 0.5×ATR | m5_close > entry_swing_high + 0.5×ATR |
| **Opposite PEMCG flip (Trigger 2a)** | `pemcg_sell ≥ 5` → break | `pemcg_buy ≥ 5` → break |
| **HTF disagreement (Trigger 2c)** | `h1_trend < −0.5` → break | `h1_trend > +0.5` → break |
| **SL ratchet on TP1** | SL raises to entry + 0.3×ATR cushion | SL lowers to entry − 0.3×ATR cushion |
| **SL ratchet on TP2** | SL raises to TP1 price | SL lowers to TP1 price |
| **Continuous ATR trail** | SL = peak − 1.5×ATR (raises only) | SL = trough + 1.5×ATR (lowers only) |
| **Dynamic TP3 (Option 3C)** | TP3 = SL + 2.0×ATR (extends up only) | TP3 = SL − 2.0×ATR (extends down only) |

Every gate has its mirror; every threshold has its inversion; every direction-preserving invariant is enforced (BUY raises SL/TP, SELL lowers SL/TP — neither retracts toward current price).

---

## §4 Pending-order lifecycle summary

**Pendings exist in two stacks** (one per direction-family):

| Stack | Used by | Slots |
|---|---|---|
| `g_sell_limit_stack[10]` | SELL-side cascade + BUY counter-trend recovery | [0]/[1] = L1/L2 SELL_LIMIT (legacy); [2..8] = SELL_STOP_CONT cascade; [9] = BUY_LIMIT recovery |
| `g_buy_stop_stack[10]` (v2.7.95 NEW) | BUY-side cascade + SELL counter-trend recovery | [2..8] = BUY_STOP_CONT cascade; [9] = SELL_LIMIT recovery |

**Lifecycle**:

```
PLACED  ────►  WAITING (in broker book)
                  │
                  │   Every M5 close:
                  │   ↓
                  │   EvaluateDirectionLock(direction, gi)
                  │
        ┌─────────┴───────────────────┐
        │                             │
   verdict=VALID                 verdict=INVALID/NEUTRAL
        │                             │
        ▼                             ▼
   keep WAITING                  EA: OrderDelete(ticket)
        │                        Broker book: pending removed
        ▼                        State: CANCELLED (structural)
   Price touches trigger              │
        │                             │
        ▼                             ▼
   Broker fills                   group.direction_lock_broken=true
   pending → market               Bilateral cooldown engaged
   position
        │                             │
        ▼                             ▼
   becomes part of                 No new pendings can be re-armed;
   the group; managed by           ArmPostTP1Ladder returns early;
   TP1/TP2/TP3 staging             new BUY+SELL setups blocked
   like Leg 1 was                  until cooldown elapses + fresh signal

  Fallback safety: broker-side timer expiration also triggers cancel
  if EA goes offline. EA never relies on the timer alone anymore.
```

**Race window**: a pending placed at time T can theoretically fill within [T, next M5 close + ~30s] before the structural cancel sweep runs. Worst case: ~5min 30s. Previously the timer-only behavior left pendings exposed for the full `expiry_bars × 5min` (typically 10 min). Set 4 Option 4B reduces but doesn't eliminate the race — v2.7.103+ (decision-at-fire) would close it 100%.

---

## §5 Activation state (as of 2026-05-14, post-All-Phases-On)

| Knob | Value | What it does |
|---|---|---|
| `FORGE_SETUP_DIRECTION_LOCK_ENABLED` | 1 | Activates Sets 6+7+8 state machine + evaluator + bilateral cooldown |
| `FORGE_TIMING_DIRLOCK_BREAK_BILATERAL_COOLDOWN_BARS` | 2 | 10-min suppression of both directions after any lock break |
| `FORGE_TIMING_COOL_PERIOD_STRUCTURE_CANCEL_ENABLED` | 1 | Activates Set 4 — cancels pendings on structure flip every M5 close |
| `FORGE_GEOMETRY_TP2_CLOSE_ENABLED` | 1 | Activates Set 2 — banks 25% of remaining positions at TP2 |
| `FORGE_GEOMETRY_TP1_PIP_FLOOR` | 40 | TP1 ≥ 40 pips ($4 on XAUUSD, broker convention) |
| `FORGE_GEOMETRY_TP2_PIP_FLOOR` | 60 | TP2 ≥ 60 pips ($6 on XAUUSD) |
| `FORGE_GEOMETRY_BATCH_SIZE` | 4 | Activates Set 1 — Leg 1 splits into 4 market orders |
| `FORGE_GEOMETRY_TP3_MODE` | 1 | Activates Set 3 Option 3C — TP3 extends with SL trail |
| `FORGE_GEOMETRY_TP3_DIST_FROM_SL_ATR_MULT` | 2.0 | TP3 stays 2×ATR ahead of current SL |
| `FORGE_BREAKOUT_ATR_TRAIL_ENABLED` | 1 | Required for TP3 dynamic mode to do anything |
| `FORGE_BUY_STOP_CONT_ENABLED` | 1 | v2.7.95 — BUY cascade asymmetry fix active |
| `FORGE_SELL_LIMIT_RECOVERY_ENABLED` | 1 | v2.7.95 — SELL_LIMIT recovery for BUY setups active |

---

## §6 Validation queries (post-run)

```sql
-- Count direction-lock blocks by direction
SELECT gate_reason, COUNT(*) FROM SIGNALS
WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
  AND gate_reason LIKE 'dirlock_block_%'
GROUP BY gate_reason;

-- Find structural cancellation events (journal log)
grep "structure_flip_cancel" "$HOME/.../MetaTrader 5/Tester/Agent-127.0.0.1-3000/logs"/*.log

-- TP2 banking events
grep "TP2 banked" "$HOME/.../MetaTrader 5/Tester/Agent-127.0.0.1-3000/logs"/*.log

-- Confirm batched legs (4 deals per group)
SELECT magic, COUNT(*) FROM TRADES
WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
  AND type=0
GROUP BY magic HAVING COUNT(*) >= 4;
```

---

## §7 References

- Architectural tracker: `docs/FORGE_CORE_LOGIC_DESIGN.md`
- Rollout phases: `docs/FORGE_v2.7.95-2.7.102_ROLLOUT_PLAN.md`
- PEMCG architecture (Sets 6+7 dependency): `docs/FORGE_PEMCG_ARCHITECTURE.md`
- G5006 case study (canonical loss pattern this redesign defends against): `docs/FORGE_CASE_STUDY_G5006_INFLECTION_POINT.md`
- Operator's original review (the document this flow doc fulfills): `docs/response-core-logic-design.md`

---

## §8 Changelog

### 2026-05-14 — Initial creation
- Captured the All-Phases-On lifecycle for BUY + SELL with full mirror analysis.
- Created in response to operator request after enabling all 12 knobs in `.env`.

### 2026-05-14 — v2.7.103 — Close cool-period cancel sweep gaps
**Why this version exists**: the v2.7.101 `CancelPendingOnStructureFlip` swept slots
`2..9` of `g_sell_limit_stack` / `g_buy_stop_stack` only, and only iterated those two
stacks. Two coverage gaps surfaced during All-Phases-On walkthroughs:

**Gap 1 — Slot range excluded BB_BREAKOUT L1/L2.**
Slot 0 holds the BB_BREAKOUT L1 SELL_LIMIT (`magic = group_magic + 20000`) and slot 1
the L2 SELL_LIMIT (`magic = group_magic + 20001`). The original `_s = 2` loop start
silently skipped both. When a SELL group's direction lock flipped to INVALID between
trigger and L1 fill, the L1/L2 limits could still execute into the new regime.

Fix: gated the slot-loop start index on
`g_sc.structure_cancel_includes_breakout_l1l2`. When ON, the loop iterates `0..9`;
when OFF, the v2.7.101 `2..9` behaviour is preserved.

Default-OFF because BB_BREAKOUT retraces back to the limit price are sometimes
intentional continuation behaviour (price wicks the L1 level on a healthy pullback
before resuming). Flip when you want structural break to invalidate the L1/L2 thesis.

Env knob: `FORGE_TIMING_STRUCTURE_CANCEL_INCLUDES_BREAKOUT_L1L2=1`.

**Gap 2 — Per-trigger setup pendings were invisible to the stack sweep.**
`PlaceOpenGroupLeg` can place a leg as a pending (BUY_LIMIT/SELL_LIMIT/BUY_STOP/
SELL_STOP) instead of a market order. These pendings carry `magic == group_magic`
(no `+20000` cascade offset) so they are NOT registered in either the SELL_LIMIT or
BUY_STOP cascade stacks. The stack-based sweep had no way to see them.

Fix: new `CancelStrayPendingsOnStructureFlip()` walker at `ea/FORGE.mq5` mirrors
the canonical `CancelPendingOnDailyFlip` pattern (`ea/FORGE.mq5:3449`):

```
for(int i = OrdersTotal() - 1; i >= 0; i--)
   - OrderSelect(ot)
   - ChartSymbolMatches filter
   - Magic in core range [MagicNumber..MagicNumber+10000)  (cascade range is owned by stack sweep)
   - Pending type filter (6 types incl. STOP_LIMIT)
   - Group lookup by g_groups[g].magic_offset == om
   - pend_dir from ORDER_TYPE (BUY_*  → BUY; SELL_* → SELL)
   - EvaluateDirectionLock(pend_dir, gi)
   - INVALID or NEUTRAL → g_trade.OrderDelete(ot)
```

Why a per-order-type direction (not the group direction): a SELL_LIMIT placed under a
BUY group (mixed-direction recovery legs) gets evaluated against BUY's lock state,
not SELL's. Correct behaviour for the hedge-mode mixed-direction setups.

Env knob: `FORGE_TIMING_PENDING_PRE_TRIGGER_STRUCT_CANCEL_ENABLED=1`.
New gate code: `pending_pre_trigger_struct_cancel` (PrintFormat-only, not written to
SIGNALS.gate_reason; legend entry exists for forge-monitor SKIP-rollup parity).

**ICT/SMC industry citation**:
- *Market Structure Shift (MSS)* — a body-close beyond the swing level that justified
  the limit-order thesis invalidates the entry. The MSS pattern is documented at
  [tradethepool.com — ICT Market Structure Shift](https://tradethepool.com/technical-skill/ict-market-structure-shift/)
  and [luxalgo.com — Market Structure Shifts (MSS) in ICT Trading](https://www.luxalgo.com/blog/market-structure-shifts-mss-in-ict-trading/).
  Both sources frame MSS as the canonical invalidation event for limit-order entries
  resting at the prior swing level. FORGE's `EvaluateDirectionLock` Trigger 1
  (`m5_close < entry_swing_low - atr × dirlock_struct_break_atr_mult` for BUY; mirror
  for SELL) is the body-close validation of MSS that this walker reacts to.

**Source-code anchors**:
- Struct fields: `ea/FORGE.mq5` `structure_cancel_includes_breakout_l1l2`,
  `pending_pre_trigger_struct_cancel_enabled` (added next to existing
  `structure_flip_cancel_enabled`).
- Init defaults: `ea/FORGE.mq5` `InitScalperConfig` block under the v2.7.101 default
  line — both new knobs default `false`.
- Walker function: `CancelStrayPendingsOnStructureFlip()` directly below the v2.7.101
  `CancelPendingOnStructureFlip`.
- Call site: M5-close branch alongside the existing `CancelPendingOnStructureFlip()`
  call (gated by `g_sc.direction_lock_enabled` per-bar guard).
- JSON-load: `breakout_json` block keys `structure_cancel_includes_breakout_l1l2` and
  `pending_pre_trigger_struct_cancel_enabled`.

**Cross-references**:
- `docs/FORGE_CORE_LOGIC_DESIGN.md` §9 v2.7.103 entry (this fix in design-tracker form)
- `config/gate_legend.json` `pending_pre_trigger_struct_cancel`,
  `structure_flip_cancel_l1l2`
- `scripts/sync_scalper_config_from_env.py` `FORGE_TIMING_STRUCTURE_CANCEL_INCLUDES_BREAKOUT_L1L2`,
  `FORGE_TIMING_PENDING_PRE_TRIGGER_STRUCT_CANCEL_ENABLED`
- `.env.example` v2.7.103 Gap 1 / Gap 2 blocks

**Trade-flow impact (when both knobs ON)**:
- Step 7 (cool period) now closes the last two gaps where stale-condition pendings
  could survive a structural break and fill against the new market regime.
- Combined with v2.7.101's cascade sweep + v2.7.27's daily-flip sweep, FORGE now has
  three layered structural cancellation watchdogs (M5 structure flip × cascade slots,
  M5 structure flip × core-range pendings, D1 regime flip × all pendings).
