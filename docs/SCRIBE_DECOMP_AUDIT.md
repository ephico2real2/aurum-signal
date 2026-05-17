# Scribe.py Structural Audit for Mixin Decomposition

**Date:** 2026-05-16  
**File:** `/Users/olasumbo/signal_system/python/scribe.py` (3,036 lines)  
**Purpose:** Identify tables, cross-domain dependencies, atomicity risks, and safe extraction boundaries for mixin-based refactor.

---

## 1. Domain Mapping (Confirmed + Refined)

| Domain | Tables Touched | Method Count | Notes |
|--------|---|---|---|
| **SIGNALS** | `signals_received`, `market_regimes` | 4 | log_signal, update_signal_action, update_signal_regime, log_vision_extraction |
| **TRADES** | `trade_groups`, `trade_positions`, `trade_closures`, `forge_journal_trades` | 16 | log_trade_group, log_trade_position, close_trade_position, update_trade_group, _rollup_group_pnl, backfill_trade_group_pnl, update_positions_sl_tp_by_stage, get_open_positions_* |
| **FORGE SYNC** | `forge_signals`, `forge_journal_trades`, `aurum_tester_runs` | 2 | sync_forge_journal (1,296 lines!), sync_forge_journal_trades |
| **REGIME** | `market_regimes`, `market_snapshots` | 4 | log_market_snapshot, log_market_regime, get_latest_regime, get_regime_history, get_regime_transitions, get_regime_performance |
| **SESSION** | `trading_sessions`, `signals_received`, `trade_groups`, `news_events` | 4 | open_trading_session, close_trading_session, get_session_history, get_current_session_* |
| **AURUM** | `aurum_conversations` | 1 | log_aurum_conversation |
| **EVENTS** | `system_events` | 1 | log_system_event (+ audit mirror to JSONL) |
| **NEWS** | `news_events` | 2 | log_news_event, close_news_event |
| **SYSTEM** | `component_heartbeats` | 2 | heartbeat, get_component_heartbeats |
| **ADMIN** | All tables via DDL/migrations | 1 | _migrate, _init_db (541 lines of schema migrations) |

**Initial guess validation:** Your domains are mostly correct. **Refinement: TRADES is substantially larger and more coupled than expected—the _rollup_group_pnl helper is called by update_trade_group, backfill_trade_group_pnl, and closing workflows, making it a critical pivot point that cannot move independently.**

---

## 2. Cross-Domain Helper Dependency Map

| Helper | Called By | Domain | Critical? |
|--------|-----------|--------|-----------|
| `_now()` | 23 methods across all domains | CORE | YES—every write method uses it |
| `_conn()` | Every method with SQL | CORE | YES—connection lifecycle mgmt |
| `_serialize_open_context()` | log_trade_group (L2117) | TRADES | NO—static, reusable |
| `_rollup_group_pnl()` | update_trade_group (L2195), backfill_trade_group_pnl (L2300) | TRADES | **YES—atomicity gate** |
| `_mirror_system_event_audit()` | log_system_event (L2277) | EVENTS | NO—side-effect only, can stay |
| `_decode_regime_row()` | get_latest_regime (L2607), get_regime_history (L2619) | REGIME | NO—static decoder |
| `_audit_mirror_enabled()` | _mirror_system_event_audit (L2251) | CORE | NO—env check only |

**Critical finding:** `_now()` and `_conn()` are **load-bearing core primitives**. They must live in a base class or shared module, not duplicated across mixins. `_rollup_group_pnl()` is a **stateful helper that chains multiple tables in one transaction**—it cannot be split.

---

## 3. Risk Register (Ranked by Impact)

### Risk 1: Multi-Table Transactions (HIGHEST)
**Symptom:** Methods touching 3+ tables in one `.with self._conn()` block.

| Method | Tables | Lines | Issue |
|--------|--------|-------|-------|
| `update_trade_group()` | trade_groups, trade_closures, forge_journal_trades (via _rollup) | 2172–2207 | Terminal status triggers auto-rollup from TWO sources. Splitting this across mixins breaks atomicity—rollup fails silently if only one source gets written before split execution. |
| `close_trading_session()` | trading_sessions, signals_received, trade_groups, news_events | 2758–2803 | 4 separate queries within one transaction to compute aggregates. If TRADES mixin commits first and SESSION mixin stalls, dashboard reads stale aggregates. |
| `log_trade_group()` + `update_trade_group_magic()` chain | trade_groups (insert), then magic_number update | 2083–2127 | Two separate writes in sequence. Caller must chain them: `gid = log_trade_group(...); update_trade_group_magic(gid, ...)`. If split across mixins, caller must manage the order. |
| `sync_forge_journal()` | forge_signals, aurum_tester_runs, source SIGNALS (ATTACH) | 1296–1814 | ATTACH DATABASE to cross-validate two DBs. Inserting without wall_time validation breaks dedup. Wall_time map is cached per instance—if two mixins both try to manage it, cache invalidation fails. |

**Mitigation:** `update_trade_group()` and `_rollup_group_pnl()` must stay together. `log_trade_group()` + `update_trade_group_magic()` should be a single logical operation or handled with clear sequencing docs.

---

### Risk 2: Implicit Ordering Dependency (MEDIUM)
**Symptom:** Method A writes state that Method B reads/updates in sequence.

| Sequence | Lines | Impact |
|----------|-------|--------|
| `log_signal()` → `update_signal_regime()` | 1987–2047 | log_signal inserts; update_signal_regime patches regime columns. If split, caller must explicitly manage order. Currently implicit. |
| `log_trade_group()` → `log_trade_position()` × N | 2083–2342 | Group ID is returned; positions inserted with group_id FK. Caller manages loop. OK if documented. |
| `close_trade_position()` → `log_trade_closure()` | 2491–2524 | Position marked CLOSED in trade_positions; separate log row in trade_closures. BRIDGE tracker does both atomically. If split, BRIDGE must sequence explicitly. |

**Mitigation:** Document the contract: "TRADES mixin exposes both methods; callers coordinate the sequence."

---

### Risk 3: Singleton + Cache State (MEDIUM)
**Instance caches (L1291–1294):**
```python
_fj_src_cols_cache: dict = {}      # path → frozenset of source column names
_fj_wall_time_cache: dict = {}     # path → {run_id: wall_time}
_fj_aurum_run_cache: dict = {}     # path → {wall_time: aurum_run_id}
_fj_dedup_index: dict = {}         # (db_path, source) → set of (forge_id, wall_time)
```

**Issue:** These live on the Scribe instance. `sync_forge_journal()` and `sync_forge_journal_trades()` share `_fj_wall_time_cache` and `_fj_aurum_run_cache`. If TRADES mixin extracts trades sync and SIGNALS mixin extracts signals sync, they must either:
- Share the same instance (defeating decomposition), or
- Each maintain their own cache (losing the cross-method optimization from L1519–1520: `wall_time_map_t = self._fj_wall_time_cache.get(cache_key, {0: 0})`).

**Mitigation:** Move these four dicts to a **shared FORGE_SYNC mixin** or keep them on the base Scribe class.

---

### Risk 4: Connection Lifetime & Busy Timeout (LOW-MEDIUM)
**Pattern:** `with self._conn()` opens a fresh connection per method. `_conn()` sets `PRAGMA busy_timeout=5000` on entry (L518).

**Issue:** If two mixins' methods are called in rapid succession (e.g., log_signal then log_trade_group), each opens/closes a connection. This is safe but means busy_timeout is reset per method. **Not a blocker**, but means you cannot optimize with persistent connections across mixin boundaries without threading locks.

**Mitigation:** Document that timeout is per-method, not per-mixin. If latency becomes an issue, add a class-level connection pool later.

---

### Risk 5: Migration Coupling (LOW)
**Pattern:** `_migrate()` (L541–1203) iterates over all 12 tables, checking columns, issuing ALTERs.

**Issue:** If TRADES mixin needs a new column on trade_groups, _migrate must be aware. _migrate is called from `_init_db()` (L528–539) which is called from `__init__()`.

**Mitigation:** Keep _migrate and _init_db on base Scribe class. Mixins can override if needed, but recommend keeping it centralized.

---

## 4. Recommended Mixin Decomposition

### File Layout

```
python/
├── scribe.py (KEEP)
│   ├── class Scribe(ScribeCore, SignalsMixin, TradesMixin, ...) — base
│   └── get_scribe(), get_tester_scribe() singletons
├── scribe_core.py (NEW)
│   ├── ScribeCore
│   ├── _now(), _conn(), _init_db(), _migrate()
│   ├── query(), query_limited(), export_csv()
│   └── DDL constants
├── scribe_signals.py (NEW)
│   ├── SignalsMixin
│   └── log_signal, update_signal_action, update_signal_regime,
│       log_vision_extraction, update_vision_extraction_result
├── scribe_trades.py (NEW)
│   ├── TradesMixin
│   └── log_trade_group, log_trade_position, close_trade_position,
│       update_trade_group, _rollup_group_pnl, backfill_trade_group_pnl,
│       update_positions_sl_tp_by_stage, get_open_positions_*,
│       update_position_sl_tp, update_group_sl_tp, update_trade_group_magic,
│       increment_group_fills, get_in_use_magics, backfill_tp_stage_from_comment
├── scribe_forge_sync.py (NEW)
│   ├── ForgeSyncMixin
│   ├── sync_forge_journal (lines 1296–1814)
│   ├── sync_forge_journal_trades (lines 1816–1914)
│   └── Instance caches: _fj_src_cols_cache, _fj_wall_time_cache, _fj_aurum_run_cache, _fj_dedup_index
├── scribe_regime.py (NEW)
│   ├── RegimeMixin
│   └── log_market_snapshot, log_market_regime, get_latest_regime,
│       get_regime_history, get_regime_transitions, get_regime_performance, _decode_regime_row
├── scribe_session.py (NEW)
│   ├── SessionMixin
│   └── open_trading_session, close_trading_session, get_session_history,
│       get_current_session_id, get_current_session_start
├── scribe_events.py (NEW)
│   ├── EventsMixin
│   └── log_system_event, _mirror_system_event_audit, _audit_mirror_enabled
├── scribe_news.py (NEW)
│   ├── NewsMixin
│   └── log_news_event, close_news_event
├── aurum_messaging.py (NEW)
│   ├── AurumMessagingMixin
│   └── log_aurum_conversation
│   (named for the DOMAIN — AURUM's messaging/conversation persistence
│    layer — not for the Scribe→AURUM relationship. AURUM also talks to
│    BRIDGE via aurum_cmd.json, Telegram via Herald, MCP via tv-mcp, etc.,
│    so "scribe_aurum.py" would have implied a misleading exclusivity.)
└── scribe_system.py (NEW)
    ├── SystemMixin
    └── heartbeat, get_component_heartbeats
```

### Method-to-File Mapping

| Method | Current Line | Target File | Notes |
|--------|---|---|---|
| log_signal | 1987–2015 | scribe_signals.py | Pure write, no cross-domain deps |
| update_signal_action | 2017–2022 | scribe_signals.py | Depends on signal_id from log_signal; OK |
| update_signal_regime | 2024–2047 | scribe_signals.py | Patches regime fields on signals_received |
| log_vision_extraction | 2049–2069 | scribe_signals.py | Separate table, can move |
| update_vision_extraction_result | 2071–2081 | scribe_signals.py | Depends on extraction_id from log_vision; OK |
| log_trade_group | 2083–2120 | scribe_trades.py | **Must stay with update_trade_group_magic** |
| update_trade_group_magic | 2122–2126 | scribe_trades.py | **Chained to log_trade_group** |
| update_group_open_meta | 2128–2150 | scribe_trades.py | Updates trade_groups columns |
| increment_group_fills | 2152–2161 | scribe_trades.py | Updates trades_filled counter |
| get_in_use_magics | 2163–2170 | scribe_trades.py | Pure read |
| update_trade_group | 2172–2207 | scribe_trades.py | **CORE: triggers _rollup_group_pnl** |
| _rollup_group_pnl | 2209–2267 | scribe_trades.py | **CRITICAL: cannot move independently** |
| backfill_trade_group_pnl | 2269–2314 | scribe_trades.py | Uses _rollup_group_pnl; must stay together |
| log_trade_position | 2316–2342 | scribe_trades.py | Inserts into trade_positions |
| backfill_tp_stage_from_comment | 2344–2374 | scribe_trades.py | Updates tp_stage on trade_positions |
| update_positions_sl_tp_by_stage | 2376–2435 | scribe_trades.py | Updates both trade_positions and trade_groups |
| get_open_positions_with_stage | 2437–2449 | scribe_trades.py | Pure read |
| update_position_sl_tp | 2451–2462 | scribe_trades.py | Updates trade_positions |
| update_group_sl_tp | 2463–2489 | scribe_trades.py | Updates both trade_groups and trade_positions |
| close_trade_position | 2491–2499 | scribe_trades.py | Updates trade_positions.status |
| log_trade_closure | 2501–2524 | scribe_trades.py | Inserts into trade_closures |
| get_recent_closures | 2526–2535 | scribe_trades.py | Pure read |
| get_closure_stats | 2537–2572 | scribe_trades.py | Aggregates trade_closures |
| sync_forge_journal | 1296–1814 | scribe_forge_sync.py | **CRITICAL: 519-line method with instance caches** |
| sync_forge_journal_trades | 1816–1914 | scribe_forge_sync.py | **Depends on caches from sync_forge_journal** |
| log_market_snapshot | 1916–1951 | scribe_regime.py | Pure write |
| log_market_regime | 1953–1985 | scribe_regime.py | Pure write |
| get_latest_regime | 2602–2607 | scribe_regime.py | Pure read |
| get_regime_history | 2609–2619 | scribe_regime.py | Pure read |
| get_regime_transitions | 2621–2648 | scribe_regime.py | Traverses market_regimes; uses _decode_regime_row |
| get_regime_performance | 2650–2702 | scribe_regime.py | Joins trade_groups + market_regimes; **cross-domain** |
| _decode_regime_row | 2574–2600 | scribe_regime.py | Static helper |
| open_trading_session | 2740–2756 | scribe_session.py | Pure write |
| close_trading_session | 2758–2803 | scribe_session.py | **RISKY: queries across 4 tables** |
| get_session_history | 2807–2814 | scribe_session.py | Pure read |
| get_current_session_id | 2816–2824 | scribe_session.py | Pure read |
| get_current_session_start | 2826–2834 | scribe_session.py | Pure read |
| log_system_event | 1263–1288 | scribe_events.py | Calls _mirror_system_event_audit |
| _mirror_system_event_audit | 1249–1260 | scribe_events.py | Side-effect; opens file |
| _audit_mirror_enabled | 1245–1247 | scribe_events.py | Env check |
| log_news_event | 2713–2720 | scribe_news.py | Pure write |
| close_news_event | 2722–2728 | scribe_news.py | Pure update |
| log_aurum_conversation | 2730–2737 | aurum_messaging.py | Pure write |
| heartbeat | 2983–2997 | scribe_system.py | Delete + insert (upsert) |
| get_component_heartbeats | 2999–3004 | scribe_system.py | Pure read |
| get_today_pnl | 2837–2846 | scribe_trades.py | Reads trade_closures; pure read |
| get_open_groups | 2848–2852 | scribe_trades.py | Reads trade_groups; pure read |
| get_recent_signals | 2854–2880 | scribe_signals.py | Pure read |
| get_signals_stats | 2882–2902 | scribe_signals.py | Aggregates signals_received |
| get_performance | 2904–2936 | scribe_trades.py | **RISKY: joins across domains** |

---

## 5. The "Safest First" Mixin Candidate

### **PICK: scribe_events.py (EventsMixin)**

**Rationale:**
1. **Smallest surface:** 3 methods, 25 lines of SQL total (log_system_event, _mirror_system_event_audit, _audit_mirror_enabled).
2. **No cross-domain dependencies:** All writes to a single table (system_events). No FKs, no reads from other domains.
3. **No atomicity risks:** log_system_event is a pure INSERT. The audit mirror is a side-effect (file write) that is deliberately async/tolerant.
4. **No instance cache:**  No state beyond inherited `_now()`, `_conn()`, env checks.
5. **Straightforward test:** Add a row to system_events, verify it appears in DB. Call _mirror_system_event_audit, verify JSONL line. Done.
6. **Zero change in behavior:** Moving this doesn't change how BRIDGE, AURUM, or ATHENA call it.

**Test Plan:**
```python
# Before refactor
from scribe import Scribe
s = Scribe()
s.log_system_event("TEST", new_mode="WATCH")
rows = s.query("SELECT * FROM system_events WHERE event_type='TEST'")
assert len(rows) == 1

# After refactor (same test, same result)
```

---

## 6. High-Risk Methods to Extract Last

| Method | Why | Defer Until |
|--------|-----|--------------|
| sync_forge_journal | 519 lines; complex column detection; instance caches shared with trades sync; ATTACH DATABASE pattern | Phase 2—after ForgeSyncMixin is proven stable |
| close_trading_session | 46 lines; 4 separate queries in one transaction; aggregates from signals + trades + news | Phase 2—after SessionMixin + SignalsMixin + TradesMixin are stable |
| get_regime_performance | Joins trade_groups (domain: TRADES) + market_regimes (domain: REGIME) | Phase 2—after both domains extracted and cross-mixin patterns proven |
| update_trade_group | Calls _rollup_group_pnl; touches trade_closures + forge_journal_trades in fallback | Phase 1 with TradesMixin (but document the contract tightly) |

---

## 7. Boundary Insights & Surprises

### Surprise 1: Regime Performance Spans Multiple Domains
**Discovery:** `get_regime_performance()` (L2650–2702) joins `trade_groups` with `market_regimes`. This is a **cross-domain read query**—it cannot live in RegimeMixin alone.

**Solution:** Keep it on ScribeCore or create a separate AnalyticsMixin that depends on both REGIME and TRADES mixins.

---

### Surprise 2: Session Close Couples 4 Domains
**Discovery:** `close_trading_session()` (L2758–2803) aggregates signals, trade_groups, and news_events in a single transaction. This is **tighter coupling than expected**.

**Solution:** Refactor the aggregation logic into a helper that can be overridden per mixin:
```python
# scribe_trades.py
def _get_session_trade_stats(self, session_id):
    return (groups, pnl, pips, wins, losses)

# scribe_signals.py
def _get_session_signal_stats(self, session_id):
    return (received, executed, skipped)

# scribe_session.py
def close_trading_session(self, session_id, ...):
    signal_stats = self._get_session_signal_stats(session_id)
    trade_stats = self._get_session_trade_stats(session_id)
    # ... combine
```

---

### Surprise 3: Trade Group P&L Rollup Is a Critical Gate
**Discovery:** `_rollup_group_pnl()` (L2209–2267) is called by:
- `update_trade_group()` (L2195) — on terminal status
- `backfill_trade_group_pnl()` (L2300) — backfill loop

**Impact:** If this helper fails, both upstream methods silently degrade (rollup returns 0.0, 0.0, 0). **This must be tested exhaustively before extraction.**

**Solution:** Add integration test for each close_reason path:
- SL_HIT → trade_closures lookup
- TP_HIT → trade_closures lookup
- MANUAL_CLOSE → trade_closures lookup
- (fallback) → forge_journal_trades lookup with temporal scoping

---

### Surprise 4: log_trade_group + update_trade_group_magic Is a Two-Step
**Discovery:** `log_trade_group()` returns group_id, but `magic_number` is an optional param. **Caller must chain two methods** to set magic after insert (L2118–2127).

**Current callers:** Likely BRIDGE or AURUM does:
```python
gid = scribe.log_trade_group(...)
if magic:
    scribe.update_trade_group_magic(gid, magic)
```

**Solution:** Document this as a **required sequence** in TradesMixin docstring. Alternatively, make `log_trade_group` accept `magic_number` param and pass it directly to INSERT (avoids the chaining).

---

## 8. Summary Table: Extraction Phases

| Phase | Mixin | Complexity | Dependencies | Estimated Lines |
|-------|-------|------------|--------------|-----------------|
| **1 (SAFEST)** | EventsMixin | Very Low | None | ~25 |
| **1 (SAFE)** | NewsMixin | Low | system_events | ~20 |
| **1 (SAFE)** | AurumMessagingMixin | Low | None | ~10 |
| **1 (SAFE)** | SystemMixin | Low | None | ~30 |
| **2 (MEDIUM)** | SignalsMixin | Medium | vision_extractions, regimes (read) | ~150 |
| **2 (MEDIUM)** | RegimeMixin | Medium | market_snapshots, market_regimes | ~180 |
| **3 (RISKY)** | TradesMixin | High | Atomicity, _rollup_group_pnl, magic sequencing | ~450 |
| **3 (RISKY)** | ForgeSyncMixin | Very High | Caching, ATTACH, wall_time maps, dedup | ~620 |
| **3 (RISKY)** | SessionMixin | High | Cross-domain aggregation | ~100 |

---

## Final Recommendation

**Extraction Order:**
1. **Phase 1:** Extract EventsMixin, NewsMixin, AurumMessagingMixin, SystemMixin together. These are **safe, isolated, and prove the mixin pattern works**.
2. **Phase 1b:** Extract SignalsMixin and RegimeMixin. Add integration tests for signal → regime flow.
3. **Phase 2:** Extract TradesMixin. **Document the _rollup_group_pnl contract exhaustively.** Add property-based tests for the temporal scoping in forge_journal_trades fallback.
4. **Phase 2b:** Extract ForgeSyncMixin last. This is the **most complex**—test the cache invalidation and wall_time entropy handling thoroughly.
5. **Never extract:** ScribeCore (base class with _now, _conn, _init_db, _migrate, query, export_csv).

**Expected outcome:** Clean, testable, 8 focused mixins + 1 base class. Behavior identical to monolithic version. Database schema and queries unchanged.

