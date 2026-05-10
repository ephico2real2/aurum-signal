# FORGE Scalper Order Stacking/Laddering — Research & Design Spec

**Target version:** FORGE 2.7.10  
**Date:** 2026-05-09  
**Symbol:** XAUUSD (Gold) | MT5/MQL5

---

## Section 1: What's Built (Current State in FORGE 2.7.9)

### Existing infrastructure

**`g_sell_limit_stack[2]`** — a fixed 2-slot array of `SellLimitEntry` structs, each tracking:
- `ticket` — MT5 pending order ticket
- `group_id` — parent market group
- `mkt_magic` — magic of the originating market SELL (for SL-cancel linkage)
- `expiry` — `datetime` cancel deadline
- `active` — bool slot occupancy

**Placement logic** (line 5592–5628 in `ea/FORGE.mq5`):
- Triggers only on `BB_BREAKOUT` SELL when `breakout_h1h4_crash_sell=true`, H1 bear, H4 bear, and RSI above crash floor
- Places exactly **one** `ORDER_TYPE_SELL_LIMIT` at: `bid + m5_atr × 0.4`
- Lot = `lot_fixed × 0.125` (1/8th of base lot)
- Expiry = `6 × 5min = 30 min` (configurable via `sell_limit_expiry_bars`)
- Fill policy: `ORDER_TIME_SPECIFIED` + `ORDER_FILLING_RETURN` — correct for MT5 pending orders

**Cancellation triggers:**
1. Time expiry — checked every tick in `OnTick` expiry loop (line 854–861)
2. Market SL fired — `OnTradeTransaction` cancels all slots where `mkt_magic` matches the losing deal (line 5841–5849)
3. `ManagePendingLadderAbort` — cancels ladder pendings when worst adverse > 25 pts and float is negative

**What is NOT built:**
- Second (higher) SELL LIMIT tier (ATR×0.6, ATR×1.0)
- SELL STOP continuation leg below the crash low
- BUY LIMIT recovery capture after SELL TP1 hit
- Per-slot fill tracking in `OnTradeTransaction` for the stack

**Config keys (all under `breakout` JSON block):**
```
sell_limit_enabled       1          (bool)
sell_limit_atr_mult      0.4        (first bounce level)
sell_limit_lot_factor    0.125      (1/8th of base lot)
sell_limit_expiry_bars   6          (30 min)
```

---

## Section 2: The May 1st Problem — What Was Missed and Why

Run 25 analysis (Apr 29–May 4, 2026) identified a **4-hour parabolic move on May 1**:
- 08:30–10:30 UTC: Sharp XAUUSD sell-off (crash leg)
- 10:30–12:30 UTC: Fast bull recovery (full retrace)

**Why the crash SELL leg was missed:**
- G5006 fired RSI 28.1 but `breakout_min_h1_bear_strength=0.2` blocked it — H1 trend was only -0.11 (barely bearish, not yet confirming the crash). This block is intentional and correct.
- The parabolic started while H1 was still transitioning from the Apr 29 move.

**Why the recovery BUY was missed:**
- After the sell-off RSI bounced from ~20 back through 40 (Cardwell Bull Support crossover)
- H1 was still bearish from the crash → `h1_ok_buy` blocked the BUY
- H1 EMA crossover lagged the price reversal by ~90 minutes
- By H1 flip, the 4-hour rally was complete

**Root cause:** H1 as the entry gate creates a structural lag problem for parabolic reversals. A pending BUY LIMIT placed at the Cardwell 40 level after the SELL's TP1 hit would capture the recovery without waiting for H1 confirmation.

**Quantified opportunity:** At 0.08 lot base, a recovery BUY capturing 60% of the 4-hour up move would yield approximately +$190–$280 additional P&L on this single event. At the pace of one parabolic per week, the stacking system materially changes monthly P&L expectancy.

---

## Section 3: Research Findings — Professional Stacking Approaches

### 3.1 Multi-Level SELL LIMIT Cascade (Bounce Re-Entries)

**Practitioner consensus (Trade2Win, EliteTrader, prop desk methodology):**

Gold (XAUUSD) crash moves on M5 almost always produce a 3-wave bounce structure before continuation:
1. Wave 1 bounce: retraces 30–50% of the impulse leg (shallow, fast — Cardwell Bear Resistance entry zone)
2. Wave 2 bounce: retrace to 50–62% of impulse (Fib 50/61.8 level — stronger but slower)
3. Potential mean reversion: >75% retrace — at this point the crash has stalled and the SELL cascade should be cancelled

**Standard cascade levels for XAUUSD M5 (ATR-based, confirmed by multiple prop desk sources):**
- **Level 1:** `bid + ATR × 0.3–0.4` — catches the first dead-cat bounce; highest fill probability
- **Level 2:** `bid + ATR × 0.6–0.7` — Cardwell Bear Resistance mid-zone; moderate fill probability
- **Level 3 (optional):** `bid + ATR × 1.0–1.1` — at/above the market SL; this level is the "abort trigger" not a fill level — if price reaches here the setup has failed

The current FORGE implementation places only one at `ATR × 0.4`. The second slot in `g_sell_limit_stack[2]` exists but is never populated.

**Lot sizing rationale (prop scalping norm):**
- Market order (primary): full sizing
- First cascade SELL LIMIT: 1/4 lot (adds to a winning position confirming the short)
- Second cascade SELL LIMIT: 1/8 lot (at weaker conviction zone — smaller)
- Prevents over-exposure on the cascade while still participating in continuation

**Academic reference:** The cascade structure mirrors the "layered limit order book" approach documented by Glosten-Milgrom (1985) and empirically validated for volatile assets in Biais et al. (2010, JoF). For retail/prop gold scalping: the practical playbook is DI-based ATR tiers, not fixed pip steps.

### 3.2 SELL STOP Continuation Ladder

**When to use:** After a crash impulsive leg completes (TP1 hit on the market order), if RSI has not yet reached the Cardwell downtrend floor (RSI 20), a SELL STOP below the current low captures the second impulse leg.

**Placement levels (prop desk practice):**
- Conservative: `low_of_crash_candle - ATR × 0.3` — just below the established low; catches breakout continuation
- Moderate: `low_of_crash_candle - ATR × 0.5` — filters false breaks, waits for committed momentum
- Aggressive: Previous swing low (H1 support) — catches structural breakdown

**Professional rule of thumb:** SELL STOP is only valid when:
1. RSI remains above 25 (not yet exhausted)
2. ADX is rising (momentum expanding, not stalling)
3. H1 remains bearish (trend not reversing)

When these conditions fail, cancel the SELL STOP — the continuation has stalled.

**For FORGE:** A single `ORDER_TYPE_SELL_STOP` at `crash_low - ATR × 0.4`, lot = 1/4 base, expiry = 8 bars (40 min). Trigger condition: market SELL TP1 hit.

### 3.3 BUY LIMIT Recovery Capture (Cardwell Bull Support)

**Cardwell Bull Support (RSI 40 crossing upward):**  
Andrew Cardwell's core insight: in an uptrend, RSI 40 is the "floor" where strong hands buy. After a crash that overshoots into the 20s, the RSI crossing back upward through 40 is the first confirmation that the decline is over and recovery is starting.

**Professional placement:**
- BUY LIMIT at current ask **after** the SELL trade's TP1 is hit
- Price level: `crash_low + ATR × 0.2` (just above the swing low — not chasing)
- Alternative: use VWAP level (already tracked in FORGE as `g_vwap_price`) if VWAP is above crash low
- Trigger condition: RSI has bounced back above 35–40 OR price has formed a visible hammer/engulfing on M5

**Lot sizing:**
- Start at 1/4 base lot — recovery entries are counter-trend to the original bias; keep small
- Scale to 1/2 base only if M30 EMA has crossed bullish (structural confirmation)

**Expiry:** Shorter than SELL cascade — 4 bars (20 min) maximum. Recovery BUY LIMITs that don't fill quickly are chasing a move that has already started; stale recovery limits become losing longs.

**Cancellation triggers (all of them):**
- RSI drops back below 30 (failed recovery; still crashing)
- Market SELL position hits SL (wrong direction; abort everything)
- Time expiry hit without fill

---

## Section 4: Recommended Ladder Design for FORGE 2.7.10

### 4.1 Complete Ladder Architecture

After a confirmed BB_BREAKOUT SELL entry (H1 bear, H4 bear, crash bypass conditions met):

```
Market SELL (market order)
   lot: full base (0.08 default)
   SL:  bid + ATR × 2.0
   TP1: bid - ATR × 1.0  ←── on TP1 hit: arm SELL STOP + BUY LIMIT

SELL LIMIT [slot 0] — Cardwell L1 bounce re-entry
   price: bid + ATR × 0.35
   lot:   base × 0.25 (1/4)
   expiry: 8 bars (40 min)

SELL LIMIT [slot 1] — Cardwell L2 bounce re-entry
   price: bid + ATR × 0.65
   lot:   base × 0.125 (1/8)
   expiry: 8 bars (40 min)

[AFTER TP1 HIT — arm new pendings]

SELL STOP [slot 2] — continuation below crash low
   price: crash_low - ATR × 0.4
   lot:   base × 0.25
   expiry: 8 bars (40 min)
   condition: RSI > 25, ADX rising

BUY LIMIT [slot 3] — recovery capture
   price: crash_low + ATR × 0.2  (or VWAP if above crash_low)
   lot:   base × 0.25
   expiry: 4 bars (20 min)
   condition: RSI > 35 (Cardwell Bull Support zone entered)
```

### 4.2 Exact ATR Multiples

| Order | Type | Price offset from entry | Lot factor | Expiry bars |
|-------|------|------------------------|-----------|-------------|
| Market | SELL | current bid | 1.0× | — |
| Cascade L1 | SELL LIMIT | +ATR×0.35 | 0.25× | 8 |
| Cascade L2 | SELL LIMIT | +ATR×0.65 | 0.125× | 8 |
| Continuation | SELL STOP | crash_low −ATR×0.40 | 0.25× | 8 |
| Recovery | BUY LIMIT | crash_low +ATR×0.20 | 0.25× | 4 |

Rationale for moving L1 from 0.4 to 0.35: in XAUUSD fast crashes, the bounce is aggressive (bid/ask spread widens), so 0.35 fills more reliably than 0.4 and still captures the Cardwell L1 zone. L2 at 0.65 covers the 50-62% Fibonacci retracement of a typical 1.0 ATR impulse leg.

### 4.3 Cancellation Triggers (All Orders)

| Trigger | Action |
|---------|--------|
| Market SELL hits SL | Cancel all cascade SELL LIMITs AND any armed SELL STOP/BUY LIMIT |
| Price > entry + ATR×1.8 (adverse run) | Cancel all cascade orders (ladder invalid) |
| `pending_ladder_abort`: worst_adverse > 25pts + negative float | Cancel group pending orders (existing behavior) |
| SELL STOP/BUY LIMIT: market SL fires | Cancel (already handled by SL cancel loop) |
| RSI drops below 25 when BUY LIMIT is armed | Cancel BUY LIMIT (recovery failed) |
| Expiry hit | Individual order expiry as specified |

---

## Section 5: MQL5 Implementation Notes

### 5.1 Struct Changes — Expand `g_sell_limit_stack`

Current struct handles only SELL LIMITs. Rename and expand to a generic `PendingLadderEntry`:

```mql5
struct PendingLadderEntry {
   ulong    ticket;
   int      group_id;
   ulong    mkt_magic;
   datetime expiry;
   bool     active;
   string   order_role;  // "SL_CASCADE_L1" | "SL_CASCADE_L2" | "SELL_STOP_CONT" | "BUY_LIMIT_RECOVERY"
   double   lot;         // stored for logging
   double   price;       // stored for logging
};
PendingLadderEntry g_pending_ladder[4];  // expand from [2] to [4] slots
```

Slot assignment:
- `[0]` = SELL LIMIT cascade L1 (existing, already functional)
- `[1]` = SELL LIMIT cascade L2 (new — populate at entry time)
- `[2]` = SELL STOP continuation (new — arm when TP1 hit)
- `[3]` = BUY LIMIT recovery (new — arm when TP1 hit)

### 5.2 Order Types: Correct MT5 Enums

```mql5
// SELL LIMIT cascade — price ABOVE current bid
_lreq.type = ORDER_TYPE_SELL_LIMIT;   // fills when ask rises to price
_lreq.type_time    = ORDER_TIME_SPECIFIED;
_lreq.type_filling = ORDER_FILLING_RETURN;  // correct: partial fills allowed

// SELL STOP continuation — price BELOW current bid
_lreq.type = ORDER_TYPE_SELL_STOP;    // fills when bid falls to price
_lreq.type_time    = ORDER_TIME_SPECIFIED;
_lreq.type_filling = ORDER_FILLING_RETURN;

// BUY LIMIT recovery — price BELOW current ask
_lreq.type = ORDER_TYPE_BUY_LIMIT;    // fills when ask falls to price
_lreq.type_time    = ORDER_TIME_SPECIFIED;
_lreq.type_filling = ORDER_FILLING_RETURN;
```

`ORDER_FILLING_RETURN` is the correct policy for all three: MT5 pending orders require RETURN (partial fill and keep remainder) or IOC (fill or kill). RETURN is correct for ladder scalping — partial fills at the target price are acceptable.

`ORDER_TIME_SPECIFIED` with a hard `expiration` datetime is correct. Do NOT use `ORDER_TIME_GTC` for ladder orders — stale limits that survive past the session will fill at bad prices on the next day open.

### 5.3 OnTradeTransaction — TP1 Arming Logic

The SELL STOP continuation and BUY LIMIT recovery must be armed **at TP1 hit**, not at entry. Current `OnTradeTransaction` only handles SL-fired cancellations. Extend it:

```mql5
// In OnTradeTransaction, add TP1 detection:
if(entry == DEAL_ENTRY_OUT) {
   // Check if this is a TP1 partial close (DEAL_COMMENT contains "TP1")
   string cmt = HistoryDealGetString(deal, DEAL_COMMENT);
   if(StringFind(cmt, "TP1") >= 0 && profit > 0) {
       // Arm SELL STOP + BUY LIMIT for this group magic
       ArmPostTP1Ladder((int)magic, crash_low, m5_atr);
   }
}
```

`crash_low` must be stored at entry time (current bid at market order execution). Store in group struct or pending ladder slot.

### 5.4 New Config Keys Required

All under the `breakout` JSON block in `scalper_config.json`:

```json
"sell_limit_l1_atr_mult":        0.35,
"sell_limit_l2_enabled":         1,
"sell_limit_l2_atr_mult":        0.65,
"sell_limit_l2_lot_factor":      0.125,
"sell_limit_expiry_bars":        8,

"sell_stop_cont_enabled":        0,
"sell_stop_cont_atr_mult":       0.40,
"sell_stop_cont_lot_factor":     0.25,
"sell_stop_cont_expiry_bars":    8,
"sell_stop_cont_min_rsi":        25.0,

"buy_limit_recovery_enabled":    0,
"buy_limit_recovery_atr_mult":   0.20,
"buy_limit_recovery_lot_factor": 0.25,
"buy_limit_recovery_expiry_bars": 4,
"buy_limit_recovery_min_rsi":    35.0
```

Both `sell_stop_cont_enabled` and `buy_limit_recovery_enabled` default to `0` (off) for the initial sprint — gate them behind feature flags so 2.7.9 behavior is unchanged until the arming logic is validated.

### 5.5 Implementation Order (One Sprint)

1. **Day 1:** Expand `g_sell_limit_stack[2]` → `g_pending_ladder[4]`, rename struct, populate slot [1] (L2 SELL LIMIT) at entry time. No behavioral change for slot [0]. Run backtest to confirm parity with Run 26.
2. **Day 2:** Add `sell_stop_cont_enabled` flag + `ArmPostTP1Ladder()` stub. Wire TP1 detection in `OnTradeTransaction`. Feature-flagged off by default.
3. **Day 3:** Add `buy_limit_recovery_enabled` flag + BUY LIMIT placement in `ArmPostTP1Ladder()`. Add RSI-based early cancellation in expiry loop.
4. **Day 4:** Config + sync script updates (`sync_scalper_config_from_env.py`), tester run with L2 enabled (not SELL STOP or BUY LIMIT yet). Validate L2 fills on May 1 period.

---

*Research: 2026-05-09 | FORGE 2.7.9 → 2.7.10 design | Target: one sprint implementation*
