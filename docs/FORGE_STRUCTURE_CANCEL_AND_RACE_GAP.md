# FORGE Structural Cancel Refinement + 30s Race Gap

**Created**: 2026-05-14
**Scope**: Deep-dive on (a) the `structure_cancel_includes_breakout_l1l2` knob shipped in v2.7.103 Gap 1, and (b) the residual intra-bar race window that remains open until v2.8.x decision-at-fire ships.

---

## 1. `structure_cancel_includes_breakout_l1l2` — the slot 0/1 extension

### What it does

`CancelPendingOnStructureFlip()` at `ea/FORGE.mq5:15277` is the M5-close sweep that cancels cascade pendings when `EvaluateDirectionLock` returns INVALID/NEUTRAL. The slot loop is gated by a single `_slot_lo` constant at line 15285:

```mql5
const int _slot_lo = g_sc.structure_cancel_includes_breakout_l1l2 ? 0 : 2;
```

- `_slot_lo = 2` (default): sweep covers **cascade rungs only** — slots 2-9 = SELL_STOP continuation + BUY_STOP recovery legs placed *after* Leg 1
- `_slot_lo = 0` (knob ON): sweep also covers **slot 0 = L1 SELL_LIMIT** (`magic = group_magic + 20000`) and **slot 1 = L2 SELL_LIMIT** (`magic = group_magic + 20001`) — the initial BB_BREAKOUT limit-entry retest pendings

### Why default-OFF

Per the in-EA comment at `ea/FORGE.mq5:651-652` and `.env.example:625-626`:

> "Default-OFF because BB_BREAKOUT retraces back to the limit price are sometimes intentional (continuation after pullback). Flip when you want structural break to invalidate the L1/L2 retest thesis too."

The classic BB_BREAKOUT thesis is "breakout fires, price retraces to mid-band, L2 fills on retest, trend resumes." A mid-bar h1_trend wobble shouldn't kill that retest if the bar still closes inside structure. Default-OFF preserves that play.

### Why our active config has it ON (`.env:1079 = 1`)

Operator override 2026-05-13 — "Our EA logic must check market price before allow on unfilled order in." Bundled with Gap 2 (`PENDING_PRE_TRIGGER_STRUCT_CANCEL_ENABLED=1` at `.env:1081`). The operator chose the stricter posture: structural break invalidates ALL pendings including L1/L2 retests.

- **Cost**: some lost legitimate retest fills
- **Benefit**: no L1/L2 filling into a flipped market

### Cosmetic

When the broader sweep cancels a slot 0/1 pending, the log tag is `structure_flip_cancel_l1l2` instead of `structure_flip_cancel` (line `15322`) so `/forge-monitor`'s SKIP rollup can distinguish them.

---

## 2. The 30-second race — why M5-close sweep can't close it

### The race in mechanical detail

MT5's broker matches pending orders **server-side** on every tick. The EA gets `OnTick` after the fill has already happened — there's no pre-fill veto hook. The closest thing is `OnTradeTransaction` (per `docs/FORGE_CORE_LOGIC_DESIGN.md:300`), which fires *after* the fill.

The current sweep cadence is M5-close (300s). Worst case:

1. **t=0**: M5 bar closes. Sweep evaluates direction lock = VALID. Pending stays.
2. **t=10s**: M5 bar #2 begins. Structure flips intra-bar (e.g. PEMCG opposite warnings spike, h1_trend rolls over).
3. **t=15s**: Price tags the pending's trigger price. Broker fills. EA had no chance to react.
4. **t=300s**: Next M5 close. Sweep runs, but the order is already a filled position.

The position is now under direction-lock-broken management (`g_groups[gi].direction_lock_broken = true`) — SL trail still applies — but the entry happened against a flipped market.

### Why the v2.7.101 design accepted this

From `docs/FORGE_CORE_LOGIC_DESIGN.md:806-807`:

> "No `decision-at-fire` (Option 4C) refactor needed — Option 4B closes ~95% of the gap with minimal blast radius. v2.8.x roadmap: Option 4C as a follow-up if backtest data shows the race window is still costing entries."

The 5% is the intra-bar tick window. Operator accepted it as a pragmatic tradeoff for shipping speed.

### What "decision-at-fire" (Option 4C) actually means

`docs/FORGE_CORE_LOGIC_DESIGN.md:290`:

> "Don't place pendings at all. Mark group `cascade_eligible = true` at TP1. Per-tick check: 'if eligible AND original setup composite passes AND direction lock valid → fire fresh market order, decrement eligibility counter.' Pure decision-at-fire."

The cascade stops being a queue of broker-side limit orders. It becomes a **per-tick eligibility flag**. Each tick the EA re-evaluates: setup composite + direction lock + ATR/RSI/regime.

- If all green at this exact tick → market order
- If any red → wait, never fire
- Zero broker pendings = zero race window

**Cost**: implementation complexity. The cascade re-arm logic, lot sizing, leg counting, expiry — all currently encoded in the `g_*_stack` slots — has to migrate to per-group counter state. Also lose the broker-side safety net of "set it and forget it" if EA crashes mid-cascade.

### Decision still in operator's court

Per `docs/FORGE_CORE_LOGIC_DESIGN.md:567`:

> "The pending model is incompatible with operator's 're-analyze and decide' cool period. Even with structure-flip cancel (Set 4 Option 4A), there is a race window. Market-order paradigm eliminates it."

Whether the 5% gap is worth a v2.8.x bump depends on Run 36+ forward data:

- Do backtests show pendings filling into flipped markets and losing? If yes → ship 4C.
- If no → the 95% coverage of 4B + the v2.7.103 Gap 1 + Gap 2 extensions probably remains the right tradeoff.

---

## Cross-references

- `ea/FORGE.mq5:15277` — `CancelPendingOnStructureFlip` (stack-based sweep)
- `ea/FORGE.mq5:15361` — `CancelStrayPendingsOnStructureFlip` (Gap 2, per-trigger walker)
- `ea/FORGE.mq5:15433` — `EvaluateDirectionLock` (4-verdict evaluator)
- `ea/FORGE.mq5:15487` — `UpdateDirLockState` (state machine)
- `ea/FORGE.mq5:15537` — `IsDirLockBlocked` (bilateral cooldown gate)
- `ea/FORGE.mq5:7593-7604` — M5-close chokepoint wiring
- `.env:991-996` — Phase 1 + Phase 2 activation knobs
- `.env:1079-1081` — v2.7.103 Gap 1 + Gap 2 overrides (operator-mandated stricter posture)
- `docs/FORGE_CORE_LOGIC_DESIGN.md` §4, §9 — Set 4 Options 4A/4B/4C design notes
