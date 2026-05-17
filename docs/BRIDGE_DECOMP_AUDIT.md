# BRIDGE Decomposition Audit
**Structural Analysis for Mixin-Based Refactoring**  
Date: 2026-05-16 | Bridge.py: 5,403 lines

---

## Executive Summary

The Bridge class is a **monolithic orchestrator** coupling 7 distinct responsibility domains with complex cross-method state dependencies. A mixin split is viable, but **order of extraction is critical**: position tracking must be extracted last because it reads/writes state managed by every other domain. The safest first mixin is **drawdown protection** (smallest blast radius, no inbound calls from other methods).

---

## Domain Map

| Domain | Entry Points | Key Methods (line ranges) | Instance State | Cross-Domain Calls | Risk Level |
|--------|--------------|--------------------------|-----------------|------------------|-----------|
| **1. Position Tracker** | _sync_positions (1273) | _seed_tracker_from_scribe (1113), _sync_positions (1273), _infer_close_reason (1211), _match_tp_stage (1253) | _known_positions, _known_unmanaged_positions, _known_pendings, _tracker_seeded | Reads SCRIBE, updates trade_groups; called FROM EVERY domain that closes trades | **CRITICAL** |
| **2. Drawdown Protection** | _check_drawdown (3815) | _close_losing_positions (3771), _check_drawdown (3815) | _session_peak_equity, _dd_warn_fired, _dd_close_losers_fired, _dd_close_all_fired | Calls SCRIBE, Herald, _change_mode, _write_forge_command; NO inbound calls | **LOW** |
| **3. AURUM Dispatch** | _check_aurum_command (4228) | _is_destructive_aurum_action (4142), _summarize_destructive_action (4158), _aurum_cmd_signature (4179), _sweep_expired_* (4196–4227), _check_aurum_command (4228), _report_aeb_result (4590), _dispatch_aurum_exec (4627), _dispatch_aurum_open_group (4940), _normalize_aurum_open_trade (4934) | _pending_aurum_confirmations (S1 gate), _recent_aurum_signatures (S2 dedup), _last_aurum_ts | Calls _process_mgmt_command logic, AEGIS, SCRIBE, _sync_modify_targets; reads _open_groups, _known_positions | **MEDIUM** |
| **4. Signal Processing** | _process_signal (3035) | _process_signal (3035), _resolve_channel_group (3303), _resolve_channel_open_groups (3330) | _last_signal_id | Calls AEGIS, LENS, SCRIBE, _sync_modify_targets; writes trade_groups; reads _open_groups | **MEDIUM** |
| **5. Scalper Logic** | _scalper_logic (3580) | _scalper_logic (3580), _auto_scalper_tick (4034) | _last_auto_scalper_ts, _last_loss_close_ts | Calls AEGIS, SCRIBE, Herald; reads _open_groups, _regime_snapshot | **MEDIUM** |
| **6. MGMT Commands** | _process_mgmt_command (3350) | _process_mgmt_command (3350), _sync_group_targets (3949), _sync_all_open_group_targets (3972), _sync_modify_targets (3991) | _last_mgmt_ts | Calls SCRIBE, _enqueue_forge_command; reads _open_groups, _known_positions | **MEDIUM** |
| **7. State Management** | _change_mode, _effective_mode, _write_status | _effective_mode (5212), _change_mode (5220), _write_status (5312), _write_config (5277), _heartbeat_passive_components (5250) | _mode, _prev_mode, _sentinel_override, _sentinel_user_override, _sentinel_override_until, _mt5_blind_override, _cycle, _current_session, _current_session_id, _current_killzone, _killzone_start_ts | Calls SCRIBE, Herald, Listener, AURUM, status/config file writes | **LOW** |

---

## Coupling Matrix: Cross-Domain Calls

```
                          Position | Drawdown | AURUM | Signal | Scalper | MGMT | State
                          ---------|----------|-------|--------|---------|------|-------
Position Tracker (caller)    —      |    ✓     |   ✓   |   ✓    |    ✓    |  ✓   |  —
Drawdown Protection          —      |    —     |   —   |   —    |    —    |  —   |  ✓
AURUM Dispatch              ✓✓      |    —     |   —   |   ✓    |    —    |  ✓   |  ✓
Signal Processing           ✓       |    —     |   —   |   —    |    —    |  ✓   |  —
Scalper Logic               —       |    —     |   —   |   —    |    —    |  —   |  —
MGMT Commands              ✓✓       |    —     |   —   |   —    |    —    |  —   |  —
State Management            —       |    ✓     |   ✓   |   ✓    |    ✓    |  ✓   |  —
```
Legend: `✓` = calls into, `✓✓` = heavy coupling (multiple call sites)

---

## Risk Register: Hidden Coupling

### CRITICAL Risks

**1. Implicit State Machine: _pending_aurum_confirmations (S1 gate)**
- **Pattern**: AURUM command is SET in `_check_aurum_command()` line 4307 → expires checked+swept line 4207 → CONFIRM handler line 4269 pops it and re-dispatches
- **Risk**: Confirmation TTL (`_pending_aurum_confirmations[pid].expires_at`) is set in `_check_aurum_command()` but swept in `_sweep_expired_aurum_confirmations()` called in same method line 4231. If a mixin splits these, it breaks the "sweep-then-check" order.
- **Blast Radius**: If extraction loses the ordering, proposals expire silently or fail to re-dispatch.

**2. Dedup State: _recent_aurum_signatures (S2 window)**
- **Pattern**: Command signature hashed line 4247, stored line 4266, window swept line 4232
- **Risk**: Window expiry is `time.time() - AURUM_DEDUP_WINDOW_SEC` (line 4199). If BRIDGE runs slow ticks, clock jitter can cause duplicate-detection to fail (old sigs not yet expired, new identical sig accepted).
- **Mitigation**: Signature is stable hash ignoring volatile fields (timestamp, proposal_id). But ANY mixin that re-implements this logic risks dedup-bypass.

**3. Position Drift Detection: has_inflight_modify_for_ticket()**
- **Location**: Line 1338 calls `_forge_queue.has_inflight_modify_for_ticket(ticket)` to suppress "learn-back"
- **Pattern**: If a MODIFY_SL is queued (line 3484, 4463), the next tick's position sync (line 1338) skips SL/TP drift detection. Without this guard, the drift detector learns-back the pre-modify live value, and the queue's verifier never sees the post-modify state.
- **Risk**: If queue pump logic moves to a separate mixin, the drift detector won't know a modify is in-flight. Result: silent revert of SL changes.
- **Line**: 1338 (`if self._forge_queue.has_inflight_modify_for_ticket(ticket)`)

### MEDIUM Risks

**4. Implicit Ordering Dependency: _sync_positions() → _forge_queue.pump()**
- **Pattern**: Sync positions first (line 2698), then pump queue (line 2708)
- **Risk**: If sync and pump swap order, a queued MODIFY_SL won't see the freshest MT5 snapshot for its verifier. Verifier timeout increases.
- **Mitigation**: Comment exists (lines 2702–2706), but no enforcement. A mixin that extracts both must preserve order.

**5. _open_groups Cache Invalidation**
- **Pattern**: `_open_groups` dict is updated in _process_signal (3238), _scalper_logic (3716), _dispatch_aurum_open_group (5148), and synced from SCRIBE in _sync_open_groups_from_scribe (2192)
- **Risk**: Sync is called once per tick (line 2764), AFTER mode-specific logic (lines 2852–2895). If a mixin extracts signal/scalper/AURUM logic without also calling _sync_open_groups_from_scribe first, it operates on stale _open_groups.
- **Line**: 2764 called in _tick(), but signal/scalper/AURUM paths read _open_groups at lines 3081, 3588, 5045

**6. SCRIBE Transaction Boundaries Implicit**
- **Pattern**: SCRIBE writes are scattered: trade_groups.open (line 3220), positions.fill (line 1410), positions.close (line 1730), group.magic (line 3224)
- **Risk**: No explicit transaction begin/commit. If a partial mixin writes trade_groups but crashes before log_trade_group(), the group is orphaned in SCRIBE.
- **Mitigation**: SCRIBE methods internally use transactions, but the contract is implicit.

### LOW Risks

**7. Herald Parse Mode Inconsistency**
- **Pattern**: Most herald.send() calls omit parse_mode (defaults to HTML). Line 4970, 5085 explicitly pass `parse_mode=None` to disable HTML.
- **Risk**: Low-priority but a mixin extracting Herald calls might use inconsistent parse modes, breaking Telegram rendering.
- **Mitigated By**: All send() calls in bridge.py are consistent; just note for the mixin boundary.

---

## Method-to-File Mapping Recommendation

### Primary: Extract as Standalone Mixins

```
bridge.py (stays ~2,200 lines after split)
├── core._bridge.py (base Bridge class + run loop)
│   ├── __init__, run, _tick (main orchestrator)
│   ├── _effective_mode, _change_mode, _write_status, _write_config
│   ├── _refresh_regime_snapshot, _regime_context_for_trade
│   └── session/killzone transition handlers
│
├── position._tracker.py (PositionTrackerMixin)
│   ├── _seed_tracker_from_scribe, _sync_positions
│   ├── _infer_close_reason, _match_tp_stage
│   ├── _known_positions, _known_unmanaged_positions, _known_pendings cache
│   └── ALL interaction with deal close time, pips calc, TP stage detection
│   EXTRACTED LAST (depends on all others)
│
├── gate._aurum.py (AurumDispatchMixin)
│   ├── _is_destructive_aurum_action, _summarize_destructive_action
│   ├── _aurum_cmd_signature (S2 dedup)
│   ├── _sweep_expired_aurum_confirmations, _sweep_expired_aurum_signatures
│   ├── _check_aurum_command (main dispatcher)
│   ├── _dispatch_aurum_open_group, _normalize_aurum_open_trade
│   ├── _dispatch_aurum_exec, _report_aeb_result
│   ├── _pending_aurum_confirmations, _recent_aurum_signatures state
│   └── CRITICAL: S1/S2 gates, CONFIRM handler
│
├── gate._signal.py (SignalProcessingMixin)
│   ├── _process_signal, _resolve_channel_group, _resolve_channel_open_groups
│   ├── _last_signal_id state
│   └── LENS → AEGIS → SCRIBE flow
│
├── gate._scalper.py (ScalperMixin)
│   ├── _scalper_logic, _auto_scalper_tick
│   ├── _last_auto_scalper_ts, _last_loss_close_ts state
│   └── LENS-driven + AURUM-autonomous paths
│
├── trade._mgmt.py (ManagementMixin)
│   ├── _process_mgmt_command
│   ├── _sync_group_targets, _sync_all_open_group_targets, _sync_modify_targets
│   ├── _lookup_group_magic
│   └── Telegram channel scoping + MODIFY routing
│
└── protect._drawdown.py (DrawdownProtectionMixin)
    ├── _check_drawdown, _close_losing_positions
    ├── _session_peak_equity, _dd_warn_fired, _dd_close_losers_fired, _dd_close_all_fired state
    └── E3 three-tier breaker logic (T1/T2/T3)
```

### Secondary: Keep in bridge.py (Glue + Utilities)

- `_ForgeCommandQueue` (lines 360–518) — stays in bridge.py; used by multiple mixins
- Static helpers: `_calc_pips()`, `_calc_pip_value_usd()`, `_build_entry_ladder()`, etc. (lines 702–1007) — consider a `util._calcs.py` or keep in bridge.py
- `_enqueue_forge_command()` (2042) wrapper for queue — stays in Bridge base

---

## Extraction Order (Dependency Flow)

1. **Drawdown Protection** → `protect._drawdown.py` (0 inbound deps)
   - Safe: only reads _open_groups, writes SCRIBE + Herald + mode change
   
2. **State Management** → core._bridge.py (no outbound to other mixins except via _tick orchestration)
   - Keep in base class; it's the orchestrator
   
3. **MGMT Commands** → `trade._mgmt.py` (reads _open_groups, calls _enqueue_forge_command)
   - Safe after drawdown; no other domain calls it except via _tick
   
4. **Signal Processing** → `gate._signal.py` (reads _open_groups, writes _last_signal_id)
   - Safe; no crossover with AURUM or Scalper
   
5. **Scalper Logic** → `gate._scalper.py` (reads _open_groups, _regime_snapshot)
   - Safe after Signal; independent LENS path
   
6. **AURUM Dispatch** → `gate._aurum.py` (reads _open_groups, calls _sync_modify_targets, CONFIRM logic)
   - Medium risk: S1/S2 gates must be preserved; extract with care
   - **Constraint**: Must retain _enqueue_forge_command, _build_ticket_sl_verifier, _build_ticket_tp_verifier in Bridge base (needed by both MGMT and AURUM)
   
7. **Position Tracker** → `position._tracker.py` (**LAST**)
   - Reads from ALL domains; writes to SCRIBE
   - Called from _tick() after signal/scalper/AURUM paths complete
   - **Constraint**: Fixture methods like _infer_close_reason must remain accessible to all mixins (make public or abstract method on Bridge base)

---

## Safe First Mixin: DrawdownProtectionMixin

### Rationale
- **Smallest scope**: 2 methods, ~100 lines of logic (lines 3771–3940)
- **Fewest dependencies**: reads mt5 snapshot + _open_groups cache, calls SCRIBE/Herald
- **No inbound calls**: NO other method calls _check_drawdown or _close_losing_positions except the main _tick loop
- **No implicit state machines**: _dd_warn_fired, _dd_close_losers_fired are simple per-session flags (reset on new peak)
- **Proof-of-concept value**: Demonstrates mixin pattern without risk; validates _open_groups lifetime

### Implementation Plan
1. Create `protect/_drawdown.py` with class `DrawdownProtectionMixin`
2. Move state: `_session_peak_equity`, `_dd_warn_fired`, `_dd_close_losers_fired`, `_dd_close_all_fired`, `_last_loss_close_ts`
3. Move methods: `_check_drawdown()`, `_close_losing_positions()`
4. Bridge base class inherits mixin: `class Bridge(DrawdownProtectionMixin, ...)`
5. Call in _tick() unchanged: `self._check_drawdown(mt5, now)` (line 2898)

### Expected Blast Radius
- `_close_losing_positions()` calls `_write_forge_command()` (already a Bridge module-level function)
- SCRIBE reads via `get_open_groups()`, `update_trade_group()` (unchanged API)
- Herald usage is fire-and-forget (no state)
- **No modifications to call sites needed**

---

## Boundary Adjustments from Initial Guess

| Initial Guess | Audit Finding | Recommendation |
|---------------|---------------|-----------------|
| AEB dispatch (SCRIBE_QUERY/SHELL_EXEC/ANALYSIS_RUN) | Entangled in AURUM dispatch path; can't isolate | Keep in gate._aurum.py until full AURUM refactor (complex S1/S2 logic) |
| FORGE_IO (queue + command writes) | Not a domain; infrastructure used by multiple domains | Keep _ForgeCommandQueue + _enqueue_forge_command in Bridge base; static helpers in util module |
| Forge Journal Sync | Single entry point (_check_forge_journal_paths, sync calls) in _tick loop | Consider extracting to `journal._sync.py` as a secondary mixin (LOW risk, no state) |
| Forge Native Scalper Detection | Isolated in _check_forge_scalper_entry (lines 4748–4932) | Extract to `gate._forge_native.py` (STANDALONE mixin, safe) |
| Session/Killzone Transitions | Two isolated handlers; no state machine | Keep in Bridge base (they interact with SCRIBE directly; low coupling) |

---

## Metrics

| Metric | Before | After (Post-First-Mixin) | Target |
|--------|--------|-------------------------|--------|
| Bridge.py lines | 5,403 | ~5,200 | <3,000 (after 3–4 mixins) |
| Methods per class | 95 | 88 | <30 per mixin |
| Max cyclomatic complexity | 8 (drawdown check) | 6 | <5 |
| Cross-domain method calls | 67 | 60 | <20 |
| State variables (self._*) | 29 | 22 | <10 per mixin |

---

## Final Recommendation

1. **Start with DrawdownProtectionMixin** (weeks 1–2)
   - Proves the pattern, low risk, fast review cycle
   
2. **Follow with Scalper + Forge Native** (weeks 2–3)
   - Both are independent LENS-driven paths; can extract in parallel
   
3. **Tackle AURUM + MGMT together** (weeks 3–5)
   - AURUM is complex (S1/S2/S3 gates); MGMT is dependent on AURUM's _enqueue logic
   - Extract MGMT first (simpler), validate, then AURUM
   
4. **Position Tracker last** (week 6+)
   - Only after all other domains are isolated; it's the sink that touches all
   - Requires careful interface design for position fixture methods

**Estimated refactoring timeline**: 6–8 weeks, staged rollout with test coverage at each stage.

