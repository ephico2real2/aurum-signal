# FORGE Flood Resilience Review

> Reviewed: 2026-05-10 — triggered by raising max_open_groups / max_open_same_direction / max_trades_per_session to 5000 for gate-isolation backtesting.

---

## 1. Command Queue Architecture

**Severity: High**

FORGE has no EA-side durable queue. `OnTimer()` fires once per second (`FORGE.mq5:68`, `650`, `868-882`), reads one `command.json` payload, deduplicates on `g_last_cmd_ts`, and dispatches exactly one action (`FORGE.mq5:991-1035`). If bridge writes multiple commands between timer cycles, FORGE sees only the last file state — prior commands are **silently lost**.

Bridge has a partial in-memory FIFO (`bridge.py:340-364`, `432-482`) pumped once per tick (`bridge.py:2801-2809`). However, many high-traffic paths **bypass** it and call `_write_forge_command()` directly:
- Signal `OPEN_GROUP` (`bridge.py:3279-3304`)
- Scalper `OPEN_GROUP` (`bridge.py:3752-3768`)
- AURUM `OPEN_GROUP` (`bridge.py:4860-4883`)
- Several close paths (`bridge.py:3407-3418`, `3433-3439`, `3579-3607`)

These overwrite `command.json` unconditionally with no consumption check.

---

## 2. Internal EA Caps (confirmed silent blockers)

**Severity: High**

### 2a. `max_open_same_direction` parser ceiling — FIXED 2026-05-10

Parser at `FORGE.mq5:2935` previously accepted only `v >= 0 && v <= 10`. Setting 5000 in config was silently ignored; the internal default of 1 remained active (`FORGE.mq5:2334`), blocking all same-direction entries beyond the first. **Fixed: ceiling removed (`v >= 0` only).**

### 2b. Magic range ceiling

Managed magic range is hardcoded as `[MagicNumber, MagicNumber + 10000)` (`FORGE.mq5:50-53`), enforced throughout (`FORGE.mq5:1283-1285`, `1574-1591`, `3303-3324`, `6180`). Native group IDs start at 5000 (`FORGE.mq5:113`) and increment. Near 4,999 native groups, new magics escape the managed range and become untracked.

### 2c. Native leg count cap

Hardcoded at 30 in config parsing and resolver logic (`FORGE.mq5:2751-2758`, `5535-5559`, `6497-6504`, `6542-6543`).

### 2d. One-attempt-per-second native setup guard

`FORGE.mq5:5663-5664`, `5706-5710` — serializes native leg retries even if timer fires more frequently.

---

## 3. MQL5 Overflow Risks

**Severity: Medium**

`g_groups` is a dynamic array (`TradeGroup g_groups[]`, `FORGE.mq5:540-560`), grown via `ArrayResize()` — no hardcoded maximum found. The risk is not a hard overflow but **O(n) hot-path cost**: group management loops scale with `ArraySize(g_groups)` and total open orders/positions (`FORGE.mq5:1185-1208`, `1367-1378`, `3299-3336`, `4346-4353`). Thousands of concurrent groups will progressively delay `OnTick()` and staged-add cycles.

The supplemental ladder stack is a fixed 5-slot array (`FORGE.mq5:2271-2278`, `902-910`). This does not grow with group count.

---

## 4. Bridge Backpressure

**Severity: Medium**

`_ForgeCommandQueue` tracks pending and in-flight commands with retry (`bridge.py:432-474`), dropping after retry exhaustion (`bridge.py:455-466`). Partial protection only:

- **Ack on write, not on consumption** (`bridge.py:437-441`) — write success does not confirm EA execution.
- **Direct writers bypass queue** (`bridge.py:1521-1529`, `1874-1878`, `3279-3304`, `3605-3607`, `4086-4088`, `4220-4262`) — no consumed-check.
- No mechanism for bridge to detect that a prior `OPEN_GROUP` was never consumed before writing the next.
- Startup clearing prevents stale replay at init (`bridge.py:2626-2644`) but is not runtime backpressure.

---

## 5. Recommendations

| Priority | Finding | Fix |
|---|---|---|
| **Critical** | Single-payload `command.json` silently loses commands under flood | Replace with `commands[]` array or per-command inbox files; EA acks command IDs. Affects `FORGE.mq5:991-1035`, `bridge.py:308-315` |
| **Critical** | `max_open_same_direction` parser ceiling at 10 | **Fixed** — ceiling removed at `FORGE.mq5:2935` (2026-05-10) |
| **High** | Direct bridge writers bypass queue | Route all through one serialized path. Affects `bridge.py:3279-3304`, `3752-3768`, `4860-4883`, `3605-3607` |
| **High** | Magic range ceiling at `MagicNumber+10000` | Widen range or reset native ID counter before large tests (`FORGE.mq5:50-53`, `113`) |
| **Medium** | `OnTick()` scales O(n) with group count | Instrument tick duration at 100 / 500 / 1000 groups before trusting 5000 (`FORGE.mq5:1185-1208`) |
| **Medium** | No execution ack for `OPEN_GROUP` | Add command ID, requested/opened/failed legs, retcodes in response |
| **Medium** | Staged adds are tick-opportunistic | Log `staged_next_add` vs actual tick time to catch delayed adds (`FORGE.mq5:1185-1258`) |

---

## 6. Pre-Flood-Test Checklist

Before running a genuine 5000-cap flood test in the tester:

- [x] `max_open_same_direction` parser ceiling removed (this commit)
- [ ] Verify magic range does not overflow at > ~4999 native groups (`FORGE.mq5:50-53`)
- [ ] Instrument `OnTick()` duration logging at 100 / 500 / 1000 concurrent groups
- [ ] Route all direct `_write_forge_command()` callers through queue before live flood test
- [ ] Add command-ID ack protocol to detect silent drops

---

## References

- `ea/FORGE.mq5:2933-2936` — `max_open_same_direction` parser (fixed)
- `ea/FORGE.mq5:50-53`, `113` — magic range ceiling
- `ea/FORGE.mq5:540-560` — `g_groups` dynamic array
- `python/bridge.py:340-482` — `_ForgeCommandQueue` implementation
- `python/bridge.py:3279-3304` — direct OPEN_GROUP writer bypassing queue
