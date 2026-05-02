# SIGNAL SYSTEM — CHANGELOG
## [1.5.5] — 2026-05-02
### L1–L6 low-severity cleanup sprint
- **L1** (`regime.py`): detects HMM feature vector shape changes between calls, logs a WARNING with the old→new shape, and sets `feature_shape_mismatch=True` in the regime snapshot so BRIDGE can surface it. Test: `test_regime_engine_flags_hmm_feature_shape_mismatch`.
- **L2** (`aurum.py`): `SOUL.md` and `SKILL.md` are now cached at module level instead of re-read on every `ask()` call. A `SIGHUP` handler reloads the cache in-place so a running process can refresh without restart. Tests: `test_ask_uses_cached_soul_skill_without_rereading`, `test_sighup_reloads_soul_skill_cache`.
- **L3** (`regime.py`): HMM `n_components` is now read from `REGIME_HMM_COMPONENTS` (default 3, validated 2–10). `.env.example` documents the new knob. Test: `test_regime_hmm_components_env_validation`.
- **L4** (`ea/FORGE.mq5:~550`): added an explicit `(int)` cast on `tp1_close_pct`, with a comment noting fractional values are truncated by design. No logic change.
- **L5** (`.gitignore`): added `.claude/worktrees/` and `.claude/scheduled_tasks.lock` under the Agent / AI context section to prevent Claude Code runtime artifacts from being committed.
- **L6** (`python/freshness.py`): created `DATA_FRESHNESS_WINDOWS` to centralise default staleness thresholds for MT5, SENTINEL, REGIME, and LENS. `bridge.py`, `sentinel.py`, `regime.py`, `lens.py`, and `market_data.py` now import it as the env-var fallback. Test: `test_data_freshness_windows_are_defined`.
### Security fixes — local MT5 link and scoped channel MODIFY commands
- **P2 Security**: untracked the machine-specific `MT5` symlink and added `make setup-mt5-link`. The committed symlink embedded an absolute path to one developer's MT5 Common Files directory, breaking other checkouts. `MT5_PATH` in `.env` now drives local symlink creation, with `.env.example` documenting the setup flow and `.gitignore` covering the bare symlink name.
- **C2 Security**: channel-origin `MODIFY_SL` and `MODIFY_TP` commands now require a resolved scope (`group_id`/magic or `ticket`) before BRIDGE writes a FORGE modify command. Previously, a channel message without a resolved `group_id` or `ticket` could write an unscoped `MODIFY_*` command that FORGE applied to every managed position. Unresolved channel MODIFY commands are now dropped with a warning log instead of falling through to global scope.
---
## [1.5.4] — 2026-05-02
### ATHENA `/api/management` schema validation (backward-compatible)
Closed the gap where `api_management()` wrote raw user-supplied JSON straight to `python/config/management_cmd.json` without any schema check. BRIDGE reads that file every tick; a malformed payload would land in the type-coercion branch (`int(group_id)`, `float(sl)`, `float(tp)`), bubble up through `_tick`'s exception handler, and spam Telegram alerts on every loop until somebody manually deleted the file.
- New schema `schemas/files/management_cmd.schema.json` (Draft-07) with intent-conditional `if/then` branches: `CLOSE_PCT` / `CLOSE_GROUP_PCT` enforce `pct ∈ (0, 100]`; `CLOSE_GROUP` / `CLOSE_GROUP_PCT` require `group_id > 0`; `MODIFY_SL` requires `sl > 0`; `MODIFY_TP` requires `tp > 0`. `additionalProperties: true` on every branch so LISTENER's `signal_id`/`channel`/`edited` fields don't get rejected.
- New `_MGMT_VALIDATOR` + `_validate_mgmt_body(body)` in `python/athena_api.py`. `api_management()` validates the assembled body **before** writing; on failure it returns `400 {error:"validation_failed", intent, details: […]}` and never touches the file.
- **Backward-compatible by design**: validator load is wrapped in `try/except` and `iter_errors` calls are wrapped too. If the schema file is missing, jsonschema imports break, or any runtime error occurs in the validator, `_validate_mgmt_body` returns `[]` and `api_management()` falls through to the original unvalidated write path. Operators can never be "locked out" by a validation infrastructure problem.
- **LISTENER and BRIDGE are intentionally unchanged** — they keep the existing tolerate-bad-payloads behaviour. The fix is at the only entry point where untrusted user JSON enters the file bus.
- Tests: new `tests/api/test_management_schema.py` (15 cases) covering valid intents, missing-required-field rejection, range/null rejection, LISTENER-style extra fields tolerated, validator-unavailable fallback, and validator-internal-error fallback. **346/346 in `tests/api/` pass**.
- Migration / rollout: drop-in. Restart ATHENA to pick up the validator (`make services-restart` or just bounce `com.signalsystem.athena`). No FORGE / SCRIBE / BRIDGE changes.
---
## [1.5.3] — 2026-05-01
### ATHENA `/api/management` schema validation (backward-compatible)
Closed the gap where `api_management()` wrote raw user-supplied JSON straight to `python/config/management_cmd.json` without any schema check. BRIDGE reads that file every tick; a malformed payload would land in the type-coercion branch (`int(group_id)`, `float(sl)`, `float(tp)`), bubble up through `_tick`'s exception handler, and spam Telegram alerts on every loop until somebody manually deleted the file.
- New schema `schemas/files/management_cmd.schema.json` (Draft-07) with intent-conditional `if/then` branches: `CLOSE_PCT` / `CLOSE_GROUP_PCT` enforce `pct ∈ (0, 100]`; `CLOSE_GROUP` / `CLOSE_GROUP_PCT` require `group_id > 0`; `MODIFY_SL` requires `sl > 0`; `MODIFY_TP` requires `tp > 0`. `additionalProperties: true` on every branch so LISTENER's `signal_id`/`channel`/`edited` fields don't get rejected.
- New `_MGMT_VALIDATOR` + `_validate_mgmt_body(body)` in `python/athena_api.py`. `api_management()` validates the assembled body **before** writing; on failure it returns `400 {error:"validation_failed", intent, details: […]}` and never touches the file.
- **Backward-compatible by design**: validator load is wrapped in `try/except` and `iter_errors` calls are wrapped too. If the schema file is missing, jsonschema imports break, or any runtime error occurs in the validator, `_validate_mgmt_body` returns `[]` and `api_management()` falls through to the original unvalidated write path. Operators can never be "locked out" by a validation infrastructure problem.
- **LISTENER and BRIDGE are intentionally unchanged** — they keep the existing tolerate-bad-payloads behaviour. The fix is at the only entry point where untrusted user JSON enters the file bus.
- Tests: new `tests/api/test_management_schema.py` (15 cases) covering valid intents, missing-required-field rejection, range/null rejection, LISTENER-style extra fields tolerated, validator-unavailable fallback, and validator-internal-error fallback. **346/346 in `tests/api/` pass**.
- Migration / rollout: drop-in. Restart ATHENA to pick up the validator (`make services-restart` or just bounce `com.signalsystem.athena`). No FORGE / SCRIBE / BRIDGE changes.
---
## [1.5.3] — 2026-05-01
### Hybrid profit ratchet — SL pin + tightened TP per-ticket
When a leg crosses `PROFIT_RATCHET_TRIGGER_PIPS`, BRIDGE now also pulls that **leg's** TP toward `current_price ± PROFIT_RATCHET_TP_BUFFER_PIPS` so any further forward movement closes the leg with a `TP_HIT` (positive close) rather than letting the SL ratchet catch the retrace. The original SL pin is preserved as the floor on retracements — every closure on the triggered leg now lands positive, regardless of which side fires.
- **Per-ticket scope is preserved**: only the leg that crossed the trigger is tightened. Sibling legs in the same group keep their original TP1/TP2/TP3 targets and continue running. This is the explicit operator preference — lock the runner, let the rest reach the staged targets.
- New env: `PROFIT_RATCHET_TP_BUFFER_PIPS` (default 5; trader-style pips). Set to 0 to disable the TP-tightening side and revert to pure SL ratchet behaviour.
- TP tightening is skipped when (a) the buffer is 0, (b) the position has no resting TP (no regression introduced), or (c) the proposed target would not actually tighten (BUY: `target_tp ≥ live_tp`; SELL: `target_tp ≤ live_tp`).
- Both the SL pin and the TP tighten go through the new FORGE command queue with separate dedup keys (`ratchet:<ticket>` and `ratchet_tp:<ticket>`) and per-ticket verifiers (`_build_ticket_sl_verifier`, `_build_ticket_tp_verifier`), so the two writes serialise correctly across the BRIDGE → FORGE file bus.
- Tests: `tests/api/test_modify_scope.py` adds 4 new cases (skip when no resting TP, skip when buffer would widen, disabled when buffer=0, per-leg isolation across BUY+SELL). Existing BUY/SELL ratchet tests now assert the SL+TP enqueue pair. **331/331 in `tests/api/` pass**.
- Migration / rollout: pure BRIDGE refactor; no FORGE EA / SCRIBE / contract changes. Defaults to enabled with a 5-pip buffer; set `PROFIT_RATCHET_TP_BUFFER_PIPS=0` to opt out.
---
## [1.5.2] — 2026-05-01
### FORGE command queue — fixes per-ticket MODIFY_SL race
Live G64 profit-ratchet test exposed a real overwrite race: BRIDGE wrote 4 ticket-scoped `MODIFY_SL` commands to the shared `MT5/command.json` within ~1.8 s; FORGE polls that file on its `OnTimer` and dedups by `timestamp`, so the first write got clobbered before FORGE could consume it. Leg 0 (#1247680712) never moved its SL, took the original SL hit for **−$4.39**, and turned what should have been a clean +$3.00 set of ratchet locks into a **net −$1.39**. The next BRIDGE tick then "learned" the stale live SL back into its in-memory cache via the drift detector, so the ratchet never retried.
- New module-level `_ForgeCommandQueue` (`python/bridge.py`) serialises FORGE writes: at most one command is in-flight per BRIDGE tick. Each pump verifies the in-flight command via a caller-supplied `verifier(mt5)` (or auto-acks after a one-tick spacing for fire-and-forget shapes), retries on timeout up to `FORGE_QUEUE_MAX_RETRIES`, and drops with an `on_drop` callback so callers can release dedup tokens. New env knobs: `FORGE_QUEUE_ACK_TIMEOUT_SEC` (default 8.0), `FORGE_QUEUE_MAX_RETRIES` (default 2). Pumped once per BRIDGE tick right after `_sync_positions`, even when MT5 is stale, so the ack-timeout path keeps ticking.
- `Bridge._enqueue_forge_command(cmd, *, verifier, description, on_drop, dedup_key)` is the new entry point. Used by `_apply_profit_ratchet` (with strict `_build_ticket_sl_verifier` per ticket and `dedup_key=ratchet:<ticket>` so a re-eligible tick doesn't pile up), `_check_aurum_command` `MODIFY_TP`/`MODIFY_SL`, and `_process_mgmt_command` `MODIFY_TP`/`MODIFY_SL`. Ticket-scoped modifies always come with a verifier; group/stage-wide modifies use the queue's fire-and-forget ack so they still get ≥1-tick spacing without needing a snapshot match.
- `_apply_profit_ratchet` no longer pre-updates `self._known_positions[ticket]['sl']` to the target. The drift detector now skips its "learn-back" branch for any ticket that has a `MODIFY_SL`/`MODIFY_TP` queued or in-flight (`_ForgeCommandQueue.has_inflight_modify_for_ticket`), so MT5's pre-modify live SL never overwrites the queued target. If the queue ultimately drops the ratchet command, `_profit_ratcheted.discard(ticket)` runs from `on_drop` so the next eligible tick re-attempts.
- Tests: `tests/api/test_modify_scope.py` adds 7 new cases — queue writes one cmd per pump (the actual race), inflight held until verifier passes, retry-and-drop budget, dedup_key suppression, `has_inflight_modify_for_ticket` matching only `MODIFY_*`, drift detector skip while modify in-flight, and ratchet `on_drop` clears the dedup token. Existing ratchet + AURUM/MGMT modify tests updated to assert against `_enqueue_forge_command`. **327/327 in `tests/api/` pass**.
- Migration / rollout: pure BRIDGE refactor; no FORGE EA, SCRIBE, or contract changes. `make reload-bridge` to ship.
---
## [1.5.1] — 2026-04-30
### Profit ratchet — auto-lock SL once a leg goes N pips green
New opt-in BRIDGE feature that addresses *"would have been nice if we close the order once we're in winning position"* without waiting for TP1. Once any tracked managed position is `≥ PROFIT_RATCHET_TRIGGER_PIPS` (default 3 XAUUSD pips) in unrealised profit and its current SL is still worse than `entry ± PROFIT_RATCHET_LOCK_PIPS` (default 1 pip past entry), BRIDGE emits a **per-ticket** `MODIFY_SL` to FORGE — reusing the v1.5.0 stage-aware MODIFY pipeline so other legs/stages stay untouched. Idempotent via an in-memory ratcheted set; cleared automatically when the position closes.
- `python/bridge.py` `_apply_profit_ratchet`: pip math via existing `_pip_size_for_symbol` / `_calc_pips`, ticket-scoped FORGE write, `_sync_modify_targets` with `ticket=` for SCRIBE row update only, `[TRACKER|PROFIT_RATCHET]` audit log + Telegram notification.
- Skips re-evaluation when SL is already past the lock target (e.g. FORGE's `move_be_on_tp1` already fired) so it composes cleanly with the existing TP1→BE behaviour.
- New env vars: `PROFIT_RATCHET_ENABLED` (default false, opt-in), `PROFIT_RATCHET_TRIGGER_PIPS` (default 15 → $1.50 on XAU), `PROFIT_RATCHET_LOCK_PIPS` (default 10 → $1.00 past entry; auto-clamped to `< trigger`). **Trader-style pip** convention (XAU/XAG = $0.10, JPY = 0.01, majors = 0.0001) so the env-var values match `trade_closures.pips` and Athena reports. Helper: `_ratchet_pip_size`.
- Tests: `tests/api/test_modify_scope.py` adds 6 ratchet cases (BUY emit, SELL emit with inverted lock, idempotency, below-trigger skip, already-locked skip, disabled short-circuit). 76/76 in the targeted suites pass.
- Docs: `.env.example`, `SKILL.md`, `SOUL.md`, `docs/CLI_API_CHEATSHEET.md`.
---
## [1.5.0] — 2026-04-30
### Per-stage / per-ticket `MODIFY_TP` & `MODIFY_SL`
MODIFY commands across the AURUM → BRIDGE → FORGE pipeline now accept two new optional scope fields so TP2/TP3 legs no longer collapse onto TP1 when only TP1 needs to move.
- **FORGE** (`ea/FORGE.mq5` v1.5.0): `ExecuteModifySL` / `ExecuteModifyTP` read optional `ticket` (single position or pending) and `tp_stage` (1/2/3, filtered against `Comment()` matching `|TP<n>`); legacy whole-magic behaviour preserved when both are absent. `WriteMarketData` adds `comment` to each `open_positions[]` row so BRIDGE can recover the leg-stage metadata `FORGE|G<id>|<leg_index>|TP<stage>`.
- **BRIDGE** (`python/bridge.py`): `_check_aurum_command` and `_process_mgmt_command` MODIFY branches forward `ticket` / `tp_stage` to FORGE after light validation. New `_sync_modify_targets` helper routes SCRIBE persistence: ticket scope updates one row, stage scope only nudges `trade_groups.tp<n>` for the matching stage, and the unscoped path keeps the existing group-wide / all-open fan-out. `_TP_STAGE_RE`/`_parse_tp_stage_from_comment` helpers parse the FORGE comment grammar; TRACKER FILL records `tp_stage` on insert and the seed pass calls `backfill_tp_stage_from_comment` for legacy rows.
- **SCRIBE** (`python/scribe.py`): `log_trade_position` now persists `data['tp_stage']`. New helpers `update_positions_sl_tp_by_stage(group_id, tp_stage, sl, tp)`, `backfill_tp_stage_from_comment(ticket, comment)`, and `get_open_positions_with_stage(group_id)` expose the stage-aware surface. The schema is unchanged — `trade_positions.tp_stage` already existed.
- **AURUM prompt** (`python/aurum.py`): new `PER-STAGE / PER-TICKET MODIFY` section documents the new fields and **requires** a `SCRIBE_QUERY` on `trade_positions` before any multi-leg MODIFY. Two-block example shows independent TP1 vs TP2 moves.
- **Contracts** (`python/contracts/aurum_forge.py`): `validate_aurum_cmd` and `validate_forge_command` accept optional `ticket` (positive int) and `tp_stage` (1/2/3) on `MODIFY_TP` / `MODIFY_SL`; unknown-action error message updated.
- **Tests**: `tests/api/test_modify_scope.py` covers SCRIBE backfill / stage updates, BRIDGE `_coerce_modify_scope` + `_sync_modify_targets` routing, BRIDGE AURUM-cmd MODIFY pass-through, and AURUM-side contract validation. `tests/api/test_aurum_forge_contract.py` extended with stage/ticket validation.
- **Docs**: `docs/DATA_CONTRACT.md`, `docs/CLI_API_CHEATSHEET.md`, `schemas/files/market_data.schema.json`, `SKILL.md`, `SOUL.md` updated with the new shapes, the comment-grammar contract, and the SCRIBE_QUERY-first workflow.
- **Migration / rollout**: SCRIBE migration is purely additive (column already present). FORGE EA must be recompiled / reattached to MT5 for `comment` in `open_positions[]` and the new MODIFY filters; BRIDGE/AURUM/SCRIBE hot-reload via `make restart`.
---
## [1.4.5] — 2026-04-30

### Deferred Analysis Runs (`ANALYSIS_RUN`)
Reusable async-analysis subsystem layered on top of the AEB. AURUM (or any caller) emits a fire-and-forget AEB action and gets an immediate `query_id`; the result is persisted under `logs/analysis/<query_id>.{json,md}` and posted back to the existing Telegram channel via the existing Herald singleton (no new bot, token, or chat_id).
- New module `python/analysis_runner.py`:
  - `register_analysis(kind)` decorator + `_HANDLERS` registry.
  - `submit(payload)` returns immediately with `{ok, query_id, status:"PENDING", log_path}`.
  - `list_pending()` / `list_recent(limit=20)` / `get_status(query_id)` introspection.
  - Daemon `ThreadPoolExecutor` worker (cap `ANALYSIS_MAX_CONCURRENCY`, default 4) writes `.json` (status) + `.md` (body) and audits `ANALYSIS_QUEUED|DONE|FAILED` to `logs/audit/system_events.jsonl`.
  - Idempotency on client-supplied `query_id` (duplicate while PENDING returns `ANALYSIS_RUN duplicate query_id`); soft queue cap returns `ANALYSIS_RUN queue full`.
  - Built-in handler `trade_group_review` (params `{group_id:int}`) reads SCRIBE read-only + scrapes `logs/bridge.log` and renders a markdown review (signal text, AEGIS decision, fills, fill ratio, realised PnL); tolerates SCRIBE schema drift via `schema_missing:` notes.
- AEB / Bridge wiring:
  - `python/aeb_executor.py`: `ANALYSIS_RUN` added to `_AEB_ACTIONS`, validator branch, dispatcher branch (lazy import), Telegram ACK formatter renders `query_id`, `status`, `log_path`.
  - `python/bridge.py`: routes `ANALYSIS_RUN` through the existing local AEB dispatch alongside `SCRIBE_QUERY` / `SHELL_EXEC`.
- AURUM wiring:
  - `python/aurum.py`: `ANALYSIS_RUN` added to supported-actions list, new `DEFERRED ANALYSIS RUNS` section in `_build_system_prompt`, and a pending/recent block appended to `_build_context` (capped at 20 lines).
- Telegram (Herald) reuse — no new bot:
  - `python/herald.py`: new `Herald.post_text()` and `Herald.post_analysis_from_log()` methods plus module-level shims; `_async_send` accepts an optional `chat_id` override; default chat target remains `Herald.chat_id`.
- Schemas + contracts:
  - `schemas/files/aurum_cmd.schema.json`: new `ANALYSIS_RUN` `oneOf` branch.
  - `python/contracts/aurum_forge.py`: `validate_aurum_cmd` accepts `ANALYSIS_RUN` (kind required; params/notify/query_id types validated).
- Docs:
  - `docs/ARCHITECTURE.md`: “Deferred Analysis Runs” section + envelope + data-flow diagram.
  - `docs/DATA_CONTRACT.md`: `ANALYSIS_RUN` listed alongside other AEB actions.
  - `docs/CLI_API_CHEATSHEET.md`: copy-paste examples for queueing a run and tailing the log file.
  - `SKILL.md` §5 + `SOUL.md`: capability + context-awareness bullets.
  - `.env.example`: `ANALYSIS_LOG_DIR` + `ANALYSIS_MAX_CONCURRENCY`.
- Verification: `make test-contracts` 93 passed; `tests/api/test_aeb_executor.py` 9 passed; end-to-end smoke (G56 review) `fills=1/1 pnl=$+4.02` matched bridge.log.

---
## [1.4.4] — 2026-04-14

### AURUM Execution Bridge (AEB) end-to-end
- Added shared executor module `python/aeb_executor.py` for:
  - `SCRIBE_QUERY` (read-only SQLite URI mode + authorizer + single-statement guard + timeout/progress + row truncation)
  - `SHELL_EXEC` (allowlisted program/path validation, legacy `cmd` parsing via `shlex`, `subprocess.run(..., shell=False, timeout=...)`, output caps)
  - common result formatting for Telegram + structured result payloads
- Extended BRIDGE `aurum_cmd.json` router to handle `SCRIBE_QUERY`, `SHELL_EXEC`, and `AURUM_EXEC` while preserving existing command behavior and file-consume semantics.
- Added BRIDGE `AURUM_EXEC` HTTP dispatch path to ATHENA (`AURUM_EXEC_BASE_URL`, timeout, optional shared secret header).
- Added ATHENA `POST /api/aurum/exec` endpoint with optional token auth (`ATHENA_AURUM_EXEC_SECRET`) and shared executor dispatch.
- Hardened ATHENA `POST /api/scribe/query` internals to use the secure read-only executor path (with compatibility fallback for isolated test stubs).
- Extended AURUM JSON extraction allowlist and system prompt examples for `SCRIBE_QUERY`, `SHELL_EXEC`, and `AURUM_EXEC`.

### Contracts, schemas, docs, and tests
- Updated runtime validator `python/contracts/aurum_forge.py` for new AEB actions.
- Updated file-bus schema `schemas/files/aurum_cmd.schema.json` with new `oneOf` branches.
- Updated OpenAPI `schemas/openapi.yaml` with `/api/aurum/exec` and AEB request/result components.
- Updated `.env.example`, `docs/DATA_CONTRACT.md`, and `docs/SCRIBE_QUERY_EXAMPLES.md` for AEB config and usage.
- Added/extended tests:
  - new: `tests/api/test_aeb_executor.py`
  - new: `tests/api/test_athena_aurum_exec_api.py`
  - updated: `tests/api/test_bridge_aurum_cmd.py`
  - updated: `tests/api/test_aurum_forge_contract.py`
  - updated: `tests/api/test_json_schemas.py`
  - updated: `tests/api/test_swagger_ui.py`

---
## [1.4.3] — 2026-04-14

### Regime engine rollout surfaced end-to-end
- Added `python/regime.py` (HMM-primary inference with Gaussian fallback safety path).
- BRIDGE now computes regime snapshots each tick and persists emitted snapshots to SCRIBE `market_regimes`.
- SIGNAL/AURUM entry validation now carries regime context through AEGIS and records regime metadata on `signals_received` and `trade_groups`.
- ATHENA now serves regime surfaces via `GET /api/regime/current`, `GET /api/regime/history`, `GET /api/regime/performance`, and includes a `regime` block in `GET /api/live`.
- Added regime coverage tests:
  - `tests/services/test_regime_engine.py`
  - `tests/api/test_scribe_regime.py`
  - `tests/api/test_athena_regime_api.py`

### Execution-management and tracker hardening
- `MODIFY_SL` / `MODIFY_TP` support global and per-group execution:
  - no `magic` => global apply,
  - resolved `magic` from `group_id` => scoped apply.
- BRIDGE now syncs modified group targets into SCRIBE group + open-position rows (`update_group_sl_tp`) so ATHENA reflects live SL/TP edits immediately.
- FORGE exports `recent_closed_deals[]` in `market_data.json`; BRIDGE tracker now uses broker close metadata first (price, PnL, reason, close time) with inference fallback only when broker hints are missing.
- BRIDGE MT5 stale-data protection now tolerates transient `market_data.json` read/parse races by reusing the last known-good snapshot for a short, parameterized grace window before tripping circuit breaker:
  - `BRIDGE_MT5_STALE` (primary stale threshold),
  - `BRIDGE_MT5_STALE_RELAXED` (read-error fallback threshold),
  - `BRIDGE_MT5_READ_FAIL_STREAK` (consecutive read failures required before fallback can hard-fail).
- Added regression coverage:
  - `tests/api/test_mgmt_channel_scoping.py`
  - `tests/api/test_bridge_manual_position_tracking.py`
  - `tests/api/test_threshold_persistence.py`

### Documentation updates
- Updated `docs/ARCHITECTURE.md` with regime engine flow and `market_regimes` table coverage.
- Updated `docs/FORGE_TRADING_RULES.md` with regime rollout, scoped modify semantics, and broker-first closure attribution.
- Updated `docs/CLI_API_CHEATSHEET.md` and `docs/SCRIBE_QUERY_EXAMPLES.md` for TP-stage close reason examples and regime diagnostics queries.
- Updated `docs/SIGNAL_REPLAY_RUNBOOK.md` with direct SQLite quick diagnostics (Ben's VIP pickup checks, ENTRY-only checks, real Telegram ID filtering, and recent action snapshots using `datetime(timestamp)`).
- Updated `SOUL.md` and `SKILL.md` to reflect merged room allowlist aliases (`SIGNAL_TRADE_ROOMS` + `ACTIVE_SIGNAL_TRADE_ROOMS`), configurable SIGNAL orientation gate (`AEGIS_SIGNAL_LIMIT_ORIENTATION`), and replay-first troubleshooting (`scripts/replay_signal_pickup.py`).

---
## [1.4.2] — 2026-04-13

### LISTENER Signal Room Ingestion — Hardening & Observability

Root cause: signals from configured Telegram rooms were silently dropped as `WATCH_ONLY`
due to brittle room matching, a free-text reason code that was hard to grep, and zero
observability of where in the pipeline signals stopped flowing.

#### Room Allowlist Logic (`python/listener.py`)

- **Robust `_is_trade_room_allowed`** — now returns `(bool, reason_code)` tuple:
  - `ALLOWED_ALL` — `SIGNAL_TRADE_ROOMS` not set (legacy; all rooms trade)
  - `ALLOWED_TITLE_MATCH` — title matched after NFKC normalization + whitespace collapse + lowercase
  - `ALLOWED_ID_MATCH` — chat_id matched; tries all Telethon supergroup ID variants automatically (`-1001234567890`, `1001234567890`, `1234567890`)
  - `WATCH_ONLY_ROOM_FILTER` — not in allowlist (replaces old free-text `ROOM_NOT_PRIORITY:<room>`)
- **Unicode normalization** (`_normalize_room_name`): NFKC + whitespace-collapse + lowercase — handles curly apostrophes, non-breaking spaces, and other Unicode mismatches between operator config and Telethon-resolved titles.
- **chat_id variant matching** (`_chat_id_variants`): auto-tries bare ID, signed ID with `-100` prefix, and positive form — eliminates "configured `1234567890` but Telethon returns `-1001234567890`" silent misses.
- `WATCH_ONLY` blocks now log at **WARNING** (was INFO), making them visible in `make logs-errors`.

#### New Structured Reason Codes

| Reason Code | Where it appears | Meaning |
|---|---|---|
| `WATCH_ONLY_ROOM_FILTER` | `signals_received.skip_reason` | Room not in `SIGNAL_TRADE_ROOMS` allowlist |
| `SIGNAL_DISPATCHED` | `system_events.event_type` | Entry signal written to `parsed_signal.json` |
| `SIGNAL_PARSE_FAILED` | `system_events.event_type` | Non-empty text received but Claude returned IGNORE |
| `AEGIS_REJECTED:<reason>` | `signals_received.skip_reason` | AEGIS blocked the signal (prefixed, not bare reason) |

The old free-text `ROOM_NOT_PRIORITY:<room>` reason code is **removed**.

#### Staleness Detection

- `_last_ingest_at` tracked per LISTENER instance — updated on every received message.
- `_idle_heartbeat_loop` now checks age against `LISTENER_STALE_THRESHOLD_SEC` (default 600s):
  - `> threshold` → reports `status=WARN` with reason `LISTENER_STALE_OR_DISCONNECTED`
  - Normal → reports `status=OK` with "last_ingest Xs ago"

#### New File: `python/config/listener_meta.json`

Written by LISTENER on connect and updated each heartbeat/dispatch. Fields:
- `status` — `OK` | `WARN`
- `last_ingest_at` — ISO-8601 UTC of last processed message
- `signal_trade_rooms_active` / `signal_trade_rooms_count`
- `resolved_rooms[]` — per-channel `{chat_id, title, is_trade_room, match_reason}`

#### Startup Logging

LISTENER logs each resolved channel at startup with trade_room status:
```
LISTENER: channel -100xxx = 'Ben's VIP Club'  trade_room=True (ALLOWED_TITLE_MATCH)
LISTENER: channel -100yyy = 'Other Room'       trade_room=False (WATCH_ONLY_ROOM_FILTER)
```

#### ATHENA API Changes (`python/athena_api.py`)

- **`GET /api/channels`**: new fields per channel — `watch_only` (SCRIBE count), `is_trade_room`, `match_reason`; top-level — `signal_trade_rooms_active`, `listener_last_ingest_at`, `listener_status`.
- **`GET /api/channels/messages`**: new fields — `cache_age_sec` (mtime-based), `listener_stale` (true if cache > 3× refresh interval), `listener_last_ingest_at`, `listener_status`.

#### BRIDGE (`python/bridge.py`)

- AEGIS rejection `skip_reason` now prefixed with `AEGIS_REJECTED:` for unambiguous SCRIBE query filtering (was bare reject_reason string, indistinguishable from LENS/expiry skips).

#### Tests (`tests/api/test_listener_room_filter.py`) — new file, 21 tests

| Test class | Coverage |
|---|---|
| `TestIsTradeRoomAllowed` | empty allowlist; title case/whitespace/Unicode; chat_id variants (bare, -100 prefix, positive form); mismatch → WATCH_ONLY_ROOM_FILTER |
| `TestHandleMessageRoomFilter` | unallowed room → WATCH_ONLY + correct reason; old ROOM_NOT_PRIORITY absent; chat_id match dispatches despite title change; allowed room → SIGNAL_DISPATCHED event; empty allowlist → all dispatch |
| `TestParseFailed` | non-signal text → SIGNAL_PARSE_FAILED event; empty text → no PARSE_FAILED |
| `TestListenerStaleness` | `_last_ingest_at` updated on message; updated on dispatch; threshold config |
| `TestWatchOnlyEventDetails` | event notes contain channel+chat_id; reason field is structured code |

Updated `tests/api/test_vision_listener_aurum.py`: `test_non_priority_room_is_watch_only_in_signal_mode` assertion changed from `ROOM_NOT_PRIORITY` to `WATCH_ONLY_ROOM_FILTER`.

All 195 tests pass (`tests/api/` + `tests/services/`).

#### Documentation Updated

- `docs/SIGNAL_ROOM_POLICY.md` — new matching semantics, startup log to expect, `api/channels` quick check, updated verification queries for new reason codes, added `SIGNAL_DISPATCHED` / `SIGNAL_PARSE_FAILED` queries.
- `docs/DATA_CONTRACT.md` — `listener_meta.json`, `channel_names.json`, `channel_messages.json` added to file bus table; `listener_meta.json` shape documented.
- `docs/CLI_API_CHEATSHEET.md` — replaced `## Signal Channels` with `## Signal Channels & LISTENER Diagnostics`; added 60-second "no trades from room" runbook; AEGIS reject reasons updated to `AEGIS_REJECTED:` prefix; bridge.log grep patterns updated.

#### Runtime Verification

```bash
# Confirm room allowlist status after restart
curl -s http://localhost:7842/api/channels | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f'listener={d[\"listener_status\"]} last_ingest={d[\"listener_last_ingest_at\"]}')
[print(f'  {ch[\"name\"]}: trade_room={ch[\"is_trade_room\"]} match={ch[\"match_reason\"]} watch_only={ch[\"watch_only\"]}') for ch in d['channels']]
"

# Confirm no signals stuck in WATCH_ONLY unexpectedly
curl -s -X POST http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT channel_name, action_taken, skip_reason, COUNT(*) as n FROM signals_received GROUP BY channel_name, action_taken ORDER BY channel_name, n DESC"}' \
  | python3 -c "import sys,json; [print(r) for r in json.load(sys.stdin)['rows']]"
```

---

## [1.4.1] — 2026-04-10

### FORGE Threshold Hardening
- Added configurable runtime threshold parameters:
  - `pending_entry_threshold_points`
  - `trend_strength_atr_threshold`
  - `breakout_buffer_points`
- Native scalper logic hardened:
  - breakout trigger now uses previous M5 close + configurable breakout buffer
  - EMA trend filters normalized by ATR
  - TP split bug fixed (`BB_BREAKOUT` now uses breakout TP split config)
  - stop-level validation + lot normalization enforced before placement
  - spread-aware breakeven logic
  - cooldown timestamp updates on realized losses
  - startup rebuild of in-memory FORGE groups from open positions
- Added threshold + decision-metric telemetry into `market_data.json`, `mode_status.json`, and `scalper_entry.json`.

### BRIDGE + SCRIBE Persistence
- BRIDGE now writes threshold overrides into `MT5/config.json`.
- BRIDGE forwards native scalper threshold fields into SCRIBE `trade_groups`.
- LENS snapshot logging path now includes threshold fields from MT5 payload.
- SCRIBE schema/migrations extended with threshold fields in:
  - `market_snapshots`
  - `trade_groups`

### Tests and Verification
- Added `tests/api/test_threshold_persistence.py`:
  - migration checks on legacy DB shape
  - persistence checks for snapshot/group threshold fields
  - bridge forwarding checks for native scalper entries
- Verified with targeted and full API suite passes.

### Operations Improvements
- Added full lifecycle commands:
  - `make system-up` (TradingView → MetaTrader 5 → Python services)
  - `make system-down` (Python services → TradingView → MetaTrader 5)
- Added MT5 controls:
  - `make mt5-start`
  - `make mt5-stop`
- Hardened TradingView shutdown:
  - `make stop-tradingview` now force-kills and verifies termination.
- Added SCRIBE GUI helper:
  - `make scribe-gui` opens DB Browser for SQLite on `python/data/aurum_intelligence.db`.

### Documentation Updates
- Updated `docs/FORGE_BRIDGE.md` for threshold-hardening behavior and OFF_HOURS no-fill guidance.
- Updated `docs/DATA_CONTRACT.md` for `forge_config` threshold contract and `scalper_entry.json` metrics.
- Updated `docs/SETUP.md` + `docs/OPERATIONS.md` for SQLite GUI workflow and system lifecycle commands.
- Updated `SKILL.md` + `SOUL.md` for threshold-awareness and weekend/off-hours execution behavior.

---

## [1.4.0] — 2026-04-06

### FORGE Native Scalper Engine
- New `ScalperMode` input: `NONE` | `BB_BOUNCE` | `BB_BREAKOUT` | `DUAL`
- **BB Bounce** (ADX<20): buy at BB lower + RSI<35, sell at BB upper + RSI>65, H1 trend filter
- **BB Breakout** (ADX>25): breakout above/below BB + RSI + M5/M15 EMA alignment
- ATR-based SL/TP (1.2x for bounce, 1.5x for breakout), multi-TP with partial closes
- Safety guards: session filter (London+NY), spread<25pt, max 2 groups, loss cooldown
- DD event TP tightening: reads sentinel_status.json, tight TP at 0.8x ATR near news
- R:R minimum 1.2 enforced before every native entry
- Writes `scalper_entry.json` for BRIDGE to log to SCRIBE
- Fully backtestable in MT5 Strategy Tester
- `FORGE_SCALPER_MODE` controllable via `.env` → config.json (no reattach needed)

### Shared Scalper Config
- New `config/scalper_config.json` — BB bounce + breakout rules, session filter, safety guards
- Read by FORGE (MQL5) and AURUM (Python) for strategy consistency
- `make scalper-config-sync` copies config to MT5 Common Files

### AUTO_SCALPER Intelligence
- `format_for_aurum()` now includes BB position %, EMA distance, RSI momentum hints
- AUTO_SCALPER prompt includes decision framework (BUY/SELL/PASS criteria)
- BB squeeze detection (M5 BB range < 1.5x ATR = breakout imminent)
- AURUM context includes scalper_config.json parameters for consistency with FORGE

### Live Floating P&L on Dashboard
- Group tiles show real-time floating P&L from MT5 `open_positions[]` (3s refresh)
- Individual position boxes show entry price + per-position P&L
- Gold `LIVE` badge on groups with active MT5 positions
- Source badges: cyan `FORGE` / gold `AURUM` / orange `SIGNAL`

### BRIDGE Integration
- `_check_forge_scalper_entry()` reads scalper_entry.json from FORGE
- Native scalper trades logged to SCRIBE with `source=FORGE_NATIVE_SCALP`
- Herald Telegram alerts for native scalper entries with setup type + indicators

### Bug Fixes
- AURUM welcome message no longer stuck on "waiting for live data" after page load
- `_normalize_aurum_open_trade` method signature restored after edit corruption
- `AUTO_SCALPER` added to `contracts/aurum_forge.py` VALID_MODES + JSON Schema

---

## [1.3.1] — 2026-04-06

### SL/TP Hit Logging (trade_closures)
- New `trade_closures` SCRIBE table logs every position closure with full context
- `close_reason` inferred by BRIDGE: `SL_HIT`, `TP1_HIT`, `TP2_HIT`, `TP3_HIT`, `MANUAL_CLOSE`, `RECONCILER`, `UNKNOWN`
- BRIDGE `_infer_close_reason()` compares close price to SL/TP levels ($0.50 tolerance for XAUUSD)
- BRIDGE `_match_tp_stage()` resolves TP1/TP2/TP3 from trade_group record
- HERALD `tp_hit()` and `position_closed()` now called per position on SL/TP detection
- RECONCILER ghost positions logged to `trade_closures` with reason `RECONCILER`
- New API: `GET /api/closures?days=7&limit=50` — recent closures with reason
- New API: `GET /api/closure_stats?days=7` — aggregated SL vs TP hit rates
- `/api/live` extended with `recent_closures` (last 5, 24h) and `closure_stats` (7d)
- New ATHENA dashboard **Closures** tab with color-coded SL/TP tags and summary stat tiles
- `POSITION_MODIFIED` events categorized as TRADE in Activity panel (was hidden in SYSTEM)
- AURUM context includes last 5 closures and 7d SL/TP hit rate stats
- SCRIBE methods: `log_trade_closure()`, `get_recent_closures()`, `get_closure_stats()`, `get_open_positions_by_group()`
- Tab bar compacted for 5-tab fit; group position grid boxes reduced
- AURUM chat textarea auto-expands with word wrap (Shift+Enter for newlines)
- Agent.md added (gitignored) for AI tool project context
- Fixed pre-existing em-dash syntax error in scribe.py docstring
- Fixed DDL string split that left component_heartbeats outside the DDL block

### Documentation Updated
- `SKILL.md` — closure queries, closure context in injected state
- `SOUL.md` — trade closure detection knowledge, closure context awareness
- `docs/CLI_API_CHEATSHEET.md` — /api/closures, /api/closure_stats curl examples, SCRIBE closure queries
- `docs/SCRIBE_QUERY_EXAMPLES.md` — trade_closures table + 4 new example queries (#15–#18)
- `docs/DATA_CONTRACT.md` — trade_closures in persistence layer
- `CHANGELOG.md` — this entry

---

## [1.3.0] — 2026-04-06

### AUTO_SCALPER Mode
- New `AUTO_SCALPER` mode — AURUM (Claude) as autonomous decision engine
- BRIDGE polls AURUM every `AUTO_SCALPER_POLL_INTERVAL` (default 120s) with structured multi-TF prompt
- Pre-filters: H1 direction gate, RSI neutral screen, sentinel/max groups, loss cooldown
- AURUM responds with `OPEN_GROUP` JSON or `PASS: <reason>`
- Configurable: `AUTO_SCALPER_LOT_SIZE`, `AUTO_SCALPER_NUM_TRADES`, `AUTO_SCALPER_POLL_INTERVAL`, `AUTO_SCALPER_MAX_GROUPS`
- Dashboard mode button (green, "AURUM auto")

### Multi-Timeframe Indicators (FORGE)
- FORGE now exports `indicators_m5`, `indicators_m15`, `indicators_m30` alongside `indicators_h1`
- Each timeframe: RSI(14), EMA20, EMA50, ATR(14), BB upper/mid/lower, MACD histogram, ADX
- H1 expanded: added BB bands, MACD histogram, ADX (previously only RSI/EMA/ATR)
- New `market_view.py` module — unified MarketView combining FORGE + LENS data
- AURUM context now includes full multi-TF data with bias labels (BULL/BEAR/FLAT)

### Position Tracker (BRIDGE)
- BRIDGE now tracks individual position fills and closes from `market_data.json`
- New positions → `scribe.log_trade_position()` with ticket, magic, direction, lots, entry, SL/TP
- Disappeared positions → `scribe.close_trade_position()` with last-known P&L and estimated pips
- Group auto-rollup: when all positions/pendings gone → `update_trade_group()` with totals
- Seed from SCRIBE on startup to prevent duplicate logging after restarts
- Dedup guard: checks SCRIBE for existing ticket before inserting

### Drawdown Protection
- **Equity DD breaker** (BRIDGE): tracks session peak equity, CLOSE ALL + force WATCH if equity drops `DD_EQUITY_CLOSE_ALL_PCT` (default 3%) from peak. Telegram alert.
- **Floating P&L guard** (AEGIS): blocks new groups if floating loss ≥ `DD_FLOATING_BLOCK_PCT` (default 2%) of balance
- **Loss cooldown** (AUTO_SCALPER): pauses `DD_LOSS_COOLDOWN_SEC` (default 300s) after any position closes at a loss

### AEGIS Enhancements
- **H1 trend hard filter**: rejects BUY when H1 EMA20 < EMA50 (bearish), SELL when bullish. `AEGIS_H1_TREND_FILTER=true`
- **Per-signal `num_trades` override**: signals can include `num_trades` or `trades` (1–20) to override default 8
- **Lot override for AURUM/AUTO_SCALPER**: uses signal's `lot_per_trade` directly instead of risk-based sizing
- All previously hardcoded values now configurable: `AEGIS_MIN_LOT`, `AEGIS_PIP_VALUE_PER_LOT`, `AEGIS_MIN_SL_PIPS`
- `mt5_data` parameter added to `validate()` for H1 trend + floating DD checks

### Explicit Magic Number (SCRIBE)
- `magic_number` column added to `trade_groups` table
- BRIDGE stores `FORGE_MAGIC_BASE + group_id` explicitly (single source of truth)
- Reconciler and ATHENA read stored magic instead of computing `base + id`
- Auto-migration for existing databases
- `update_trade_group_magic()` method added to SCRIBE

### FORGE Bug Fixes
- `ExecuteCloseAll()` now cancels pending orders (limits/stops) in addition to closing filled positions
- Previously only iterated `PositionsTotal()`, missed `OrdersTotal()`

### BRIDGE Bug Fixes
- AURUM CLOSE_ALL now updates SCRIBE groups + clears cache (was missing, only wrote FORGE command)
- `num_trades`/`trades` from AURUM commands now passed through to AEGIS (was silently ignored)
- AURUM dispatch now accepts AUTO_SCALPER as valid effective_mode

### Reconciler Improvements
- FORGE version guard: skips stale-group close if `forge_version` < 1.2.4 (pending_orders not exported before that)
- Uses stored `magic_number` from SCRIBE instead of computing `base + id`

### AURUM Enhancements
- Context now includes full multi-TF indicators (M5/M15/M30/H1) with BB bands, MACD, ADX, EMA levels
- Context includes MT5 H1 ATR with sizing guidance ("use 1.5×ATR for SL")
- SKILL.md: scalping TP distance rules ($2–$5 for TP1, $5–$10 for TP2, never $10+ for scalps)
- SKILL.md: H1 alignment rule (never scalp against H1 EMA direction)
- SKILL.md: AUTO_SCALPER tick response format
- SOUL.md: AUTO_SCALPER role section (decision engine vs rules engine)
- Hot-reload: AURUM re-reads SKILL.md + SOUL.md from disk on every query (no restart needed)

### New Files
- `python/market_view.py` — unified FORGE + LENS market data object
- `docs/CLI_API_CHEATSHEET.md` — curl + python one-liners for all API endpoints

### Mode Persistence Across Restarts
- BRIDGE now restores previous mode from `status.json` on restart (default: enabled)
- `RESTORE_MODE_ON_RESTART=true` (default) — reads saved mode from status.json
- `RESTORE_MODE_ON_RESTART=false` — uses FORGE `requested_mode` or `DEFAULT_MODE` from .env
- Mode changes via API (`POST /api/mode`) write directly to status.json for immediate persistence
- CLI `--mode` from launchd plist only used as fallback when no saved state exists

### TP Split at Order Placement
- FORGE now splits TP targets at open: 75% of positions get TP1, 25% get TP2
- Split ratio controlled by `TP1_CLOSE_PCT` (default 70%)
- When TP1 hits (broker-side): 75% close automatically, remaining positions get SL→BE + TP→TP2
- Comment field shows TP target: `FORGE|G14|0|TP1` or `FORGE|G14|3|TP2`
- No more "all positions close at TP1" problem

### Signal Parser API
- New `POST /api/signals/parse` — test Claude Haiku parser via API without Telegram
- Input: `{"text": "SELL Gold @4691-4701 SL:4706 TP1:4687"}` → returns structured JSON
- Supports ENTRY, MANAGEMENT (CLOSE_ALL, CLOSE_PCT, MODIFY_SL, MODIFY_TP, TP_HIT), and IGNORE

### OpenAPI Spec v1.3.0
- 7 new endpoints added to `schemas/openapi.yaml`
- Management examples expanded with all 9 intents
- Swagger UI at `/api/docs/` fully updated

### Signal Lifecycle (Scalping)
- Signal expiry: `SIGNAL_EXPIRY_SEC=60` — stale signals rejected as EXPIRED
- Pending order timeout: `PENDING_ORDER_TIMEOUT_SEC=120` — unfilled limit orders auto-cancelled after 2min
- Telegram alert `⏰ PENDING EXPIRED` sent when orders timeout
- Full lifecycle: signal → AEGIS → FORGE → fill/timeout → SL/TP → SCRIBE → Telegram close alert

### Scalping-Aware Trend Cascade
- AEGIS trend filter now source-aware with multi-TF cascade
- **SIGNAL source** (channel scalps): M5 → M15 → H1. M5 is primary — if M5 agrees (or is FLAT), trade passes even if H1 disagrees
- **AURUM/AUTO_SCALPER**: H1 → M15 cascade (conservative)
- **SCALPER** (BRIDGE): H1 only (strictest)
- FLAT (EMA20 ≈ EMA50 within $1) counts as agreement — allows entry in either direction
- Replaces the old single-H1 filter that was too strict for scalping signals

### FORGE Reload Make Target
- New `make forge-reload` — compile + restart MT5 + auto-detect if EA loaded
- If FORGE auto-loads: prints ✅ and version. If not: prints reattach instructions
- Note: MT5 on Wine/macOS does NOT reliably auto-restore EAs after restart
- Manual reattach still required in most cases (Wine limitation)

### FORGE Architecture Comments
- Comprehensive architecture overview added to FORGE.mq5 header (50+ lines)
- Documents: data flow, command actions, market data output, TP split, magic numbers
- Section comments on: input parameters, globals, indicator handles, group tracking, symbol matching

### Sentinel Pre-Alert
- New Telegram warning when HIGH-impact event is ≤35min away but guard not yet active
- Message: `⚠️ Guard activating soon! {event} in {min}min`
- Fires with the 10-min adaptive digest cycle

### Sentinel Event Digest (Adaptive)
- SENTINEL sends upcoming HIGH-impact events to Telegram with adaptive timing
- **> 30 min away**: digest every 30 min. **≤ 30 min**: every 10 min. **Guard active**: immediate alerts
- Shows event name, currency, minutes away, and guard status
- Only sends when HIGH-impact events are within 4 hours
- Override interval via `POST /api/sentinel/digest {"interval": 30}` (reverts on restart)

### Telegram Close Alerts
- HERALD now sends `GROUP CLOSED` notifications with P&L summary when groups close
- Fires from both paths: position tracker (SL/TP) and management commands (manual close)
- `trade_group_closed()` and `position_closed()` templates added to HERALD

### Sentinel Override
- New `POST /api/sentinel/override` endpoint — temporarily bypass sentinel news guard
- Configurable duration (60s–3600s), defaults to `SENTINEL_OVERRIDE_DURATION_SEC=600`
- Auto-reverts after timeout — logged as `SENTINEL_OVERRIDE_EXPIRED` in SCRIBE
- BRIDGE handles `SENTINEL_OVERRIDE` action via aurum_cmd.json
- Telegram alert on override and expiry

### Smart Position Closing
- New FORGE commands: `CLOSE_GROUP`, `CLOSE_GROUP_PCT`, `CLOSE_PROFITABLE`, `CLOSE_LOSING`
- Group-targeted: close/partial-close only one group's positions by magic number
- Profit/loss filtering: close only winners or only losers across all groups
- BRIDGE resolves group_id → magic_number via SCRIBE for all group commands
- `POST /api/management` now accepts `group_id` parameter for group-targeted commands
- Dashboard group tile buttons now group-specific (Close Group / Close 70% target the specific group, not all)

### Signal Channels (LISTENER)
- Fixed: channel IDs parsed as integers (was strings → Telethon `ValueError`)
- Signals now logged to SCRIBE in ALL modes (not just SIGNAL/HYBRID) — only dispatch is gated
- New `GET /api/channels` endpoint — configured channels with Telethon-resolved names + signal stats
- New `GET /api/channels/messages` endpoint — recent messages from all channels (cached by LISTENER)
- LISTENER resolves channel names on connect → writes `config/channel_names.json`
- LISTENER caches last 10 messages per channel → `config/channel_messages.json` (refreshes every 5min)
- Dashboard signals tab redesigned: channel name badge on each row, channel filter strip, two-line card layout

### Documentation Updated
- `SOUL.md` — AUTO_SCALPER role, multi-TF context, drawdown protection
- `SKILL.md` — complete context spec, scalping rules, AUTO_SCALPER tick format
- `docs/AEGIS.md` — new guards table, per-signal overrides, DD env vars
- `docs/FORGE_BRIDGE.md` — multi-TF indicators, position tracker, CLI cheat sheet link
- `docs/CLI_API_CHEATSHEET.md` — channel polling commands, all curl examples
- `CHANGELOG.md` — this entry

---

## [1.2.0] — 2026-04-05

### Architecture: API-First Dashboard
All data displayed in ATHENA now flows through the Flask API.
No hardcoded mock data remains in the dashboard.

**Rule enforced:**
Component → SCRIBE/JSON file → Flask endpoint → Dashboard

### Added
- `SCRIBE.component_heartbeats` table — one row per component,
  upserted on every cycle, tracks status/note/last_action/error
- `Scribe.heartbeat()` method — upsert current component state
- `Scribe.get_component_heartbeats()` method — read all heartbeats
- `GET /api/components` — dedicated component health endpoint,
  returns all 11 components including FORGE (synthesised from
  MT5 JSON) and ATHENA (self-reported)
- `GET /api/reconciler` — exposes last reconciler run result
- `GET /api/signals` — signal history endpoint (fixed missing route)
- Heartbeat calls in: bridge, sentinel, lens, aegis, listener,
  herald, aurum, reconciler
- `reconciler.py` writes `config/reconciler_last.json` after
  each run for the API to serve
- DEMO/LIVE account type badge in ATHENA header
- Circuit breaker warning banner in ATHENA left column
- Null-safe rendering for all numeric values (shows '—' not crash)
- `aegis` block in `/api/live` — scale_factor, streak, session_pnl
- `components` dict in `/api/live` — latest heartbeat per component
- `reconciler` block in `/api/live` — last reconciler result
- `account_type`, `broker`, `server` in `/api/live` from broker_info.json
- `circuit_breaker` boolean in `/api/live`

### Changed
- `/api/live` — expanded to include all system state in one payload
- `dashboard/app.js` — now fetches `/api/components` and `/api/events`
- `dashboard/app.js` — COMP_STATUS and MOCK_EVENTS removed
- `dashboard/app.js` — ActivityLog accepts `events` and `components`
  as props instead of internal mock state
- `dashboard/app.js` — System Health panel driven by live API data
- `dashboard/app.js` — fallback D object uses null values not zeros
- `athena_api.py` — all file paths now absolute (resolve correctly
  regardless of working directory)

### Fixed
- LENS_MCP_CMD path in .env verified correct
- MT5 symlink at project root verified working
- Path mismatch: config/ files correctly resolved to python/config/
  (WorkingDirectory=python/), MT5/ files resolved to project root
- Missing `@app.route` decorator on `api_signals` function

### Added: Test Framework
- `tests/api/test_live.py` — 12 tests for /api/live
- `tests/api/test_endpoints.py` — health, sessions, performance, mode, events
- `tests/api/test_components.py` — /api/components all 11 present
- `tests/api/test_aurum.py` — AURUM chat endpoint (marked slow)
- `tests/conftest.py` — shared fixtures, base URL config
- `tests/requirements-test.txt` — pytest, requests, python-dotenv
- `tests/playwright.config.js` — Chrome, localhost:7842, HTML report
- `tests/package.json` — Playwright dev dependency
- `tests/ui/test_dashboard.spec.js` — dashboard load, panels
- `tests/ui/test_panels.spec.js` — activity log, trade groups,
  AURUM chat, mode control, LENS panel

### Added: Scripts and Shortcuts

**scripts/ directory (all Python, platform-agnostic):**

| Script | Purpose | Key flags |
|--------|---------|-----------|
| `health.py` | System health check | `--watch` `--json` |
| `test_api.py` | Run pytest API tests | `--file` `--all` `--html` |
| `test_ui.py` | Run Playwright tests | `--headed` `--debug` `--record` `--report` |
| `test_all.py` | Run all tests | `--api` `--ui` `--ci` |
| `logs.py` | View service logs | `--follow` `--errors` `--lines N` |
| `setup_tests.py` | Install test deps | `--check` |

**Makefile targets:**
`make help`, `make health`, `make test`, `make test-api`,
`make test-ui`, `make logs`, `make logs-bridge`, `make start`,
`make stop`, `make restart`, `make setup-tests`

**Shell aliases (added to ~/.zshrc):**
`ss-health`, `ss-watch`, `ss-status`, `ss-test`, `ss-test-api`,
`ss-test-ui`, `ss-test-silent`, `ss-report`, `ss-record`,
`ss-logs`, `ss-logs-bridge`, `ss-logs-listener`, `ss-logs-aurum`,
`ss-logs-errors`, `ss-start`, `ss-stop`, `ss-restart`, `ss`

---

## [1.1.0] — Earlier

### Added
- `RECONCILER` component — hourly position audit
- `trading_sessions` table in SCRIBE
- Session column on all SCRIBE tables
- `FORGE.WriteBrokerInfo()` — writes broker_info.json on startup
- `InputMode` parameter in FORGE EA dialog
- `BRIDGE._on_session_change()` — session transition detection
- `/api/sessions` and `/api/sessions/current` endpoints
- `/api/channel_performance` endpoint
- `/api/aegis_state` endpoint
- Circuit breaker in BRIDGE for MT5 staleness
- Dynamic lot scaling in AEGIS (scale down after losses)
- Session-aligned daily loss reset in AEGIS
- AURUM conversation memory from SCRIBE
- macOS launchd services for all 4 processes
- Linux systemd service files

## [1.0.0] — Initial Release

### Components
- BRIDGE, FORGE, LISTENER, LENS, SENTINEL, AEGIS,
  SCRIBE, HERALD, AURUM, ATHENA

### Core Features
- Signal room following via Telegram (Telethon)
- Claude API parsing of any signal format
- Layered entry: N trades across price zone
- TP1 partial close + SL to breakeven
- TradingView MCP integration (LewisWJackson)
- 5 operating modes: OFF/WATCH/SIGNAL/SCALPER/HYBRID
- SQLite database with 8 tables
- Flask API + React dashboard
