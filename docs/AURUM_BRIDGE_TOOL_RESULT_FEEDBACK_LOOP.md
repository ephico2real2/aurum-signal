# AURUM ↔ BRIDGE — tool-result feedback loop (open design issue)

> **Status:** OPEN — raised 2026-05-16.
> **Source of analysis:** AURUM itself (the in-app trading assistant) flagged this
> in a Telegram conversation with the operator. AURUM identified the gap, drew
> the round-trip diagram, and proposed the Option 1 fix below. The operator
> forwarded AURUM's writeup to Claude Code for capture as a tracked design
> issue. The boundary-correction notes in §3 are Claude Code's audit of
> AURUM's proposal against the actual `python/bridge.py` shape — AURUM's
> example code referred to functions (`_ask_aurum`, `self.conversation_history`)
> that don't exist on the bridge object.
> **Owner:** TBD.
> **Skill impact when shipped:** `.claude/skills/aurum-bridge-monitor/SKILL.md` must be refreshed (new event types, retired "raw JSON to Telegram" pattern) — see §6.
> **Affected components:** `python/bridge.py`, `python/aurum.py`, `python/aeb_executor.py`.

## 1. The problem in one sentence

When AURUM emits a tool call (`SCRIBE_QUERY`, `SHELL_EXEC`, `ANALYSIS_RUN`,
`AURUM_EXEC`, or — separately — a TradingView MCP `chart_command`), the result
is posted to Telegram as raw JSON-ish text and **never fed back into AURUM's
conversation history**. The operator must manually paste the result back to get
a clean natural-language answer. Every database lookup costs two round-trips
instead of one.

## 2. Today's flow (verified against code)

### 2a. SCRIBE_QUERY / SHELL_EXEC / ANALYSIS_RUN / AURUM_EXEC

```
Telegram user
   │  "what was my P&L yesterday"
   ▼
AURUM (python/aurum.py)
   │  reads Telegram, calls Claude API with conversation history
   │  Claude emits: {"action":"SCRIBE_QUERY","sql":"SELECT ..."}
   │  AURUM writes aurum_cmd.json + a prose reply to Telegram
   ▼
BRIDGE (python/bridge.py:4536)
   │  reads aurum_cmd.json, action ∈ {SCRIBE_QUERY, SHELL_EXEC, ANALYSIS_RUN}
   │  result = execute_action(cmd, db_path, project_root)   # aeb_executor.py
   │  self._report_aeb_result(result, via="BRIDGE_LOCAL")   # bridge.py:4552
   ▼
_report_aeb_result (bridge.py:4590-4625)
   │  log + scribe activity event + herald.send(format_result_for_telegram(...))
   ▼
Telegram                            ◀── END OF FLOW (raw result, no AURUM pass-back)
```

The raw result is what the operator sees. AURUM's conversation history
(persisted in scribe table `aurum_conversations`) **never receives the result
row**, so the next time AURUM is prompted it has no idea the query ran or what
it returned.

### 2b. TradingView MCP `chart_command`

Symmetric problem, different transport. The tracing/cache lives in the
`tv-mcp` daemon + Athena. The result is folded into the next AURUM prompt as a
stale `AURUM CHART_COMMAND MCP CACHE` block, which means AURUM can only react
to MCP outcomes **on the operator's next message**, not on the message that
issued the command. Worst case (e.g. `add RSI` returning `success: false`):
AURUM emits the command, BRIDGE/MCP execute it and fail, AURUM has no
visibility — the operator has to paste the failure back before AURUM can
explain or retry.

### 2c. Full wire-fabric view (Herald + Athena + Scribe-as-elephant)

The two flows above (`2a`, `2b`) live inside the larger wire fabric below.
Captured 2026-05-16 from operator verification of the actual running system —
Herald is in-proc inside every Python service (BRIDGE / AURUM / LISTENER) and
fans into Telegram. Athena participates via HTTP into BRIDGE (`/api/mode` →
writes `aurum_cmd.json`). SCRIBE is the elephant — touched by all four
services at 23/22/83/N read+write sites, with BRIDGE the dominant writer.

```
                            ┌──────────────────────┐
                            │      TELEGRAM        │  (channels + DM bot)
                            └──┬─────────────────▲─┘
                inbound  msgs  │                 │  outbound (HERALD.send)
                               │                 │
          ┌────────────────────▼────────┐        │
          │     LISTENER (launchd)      │        │
          │  Telethon → channels        │        │
          │  Claude Haiku parse         │────────┤
          │  scribe.log_signal/news     │        │
          └──────┬────────┬─────────────┘        │
                 │        │                      │
     parsed_     │        │ management_          │
     signal.json │        │ cmd.json             │
     (write)     │        │ (write)              │
                 │        │                      │
                 ▼        ▼                      │
          ┌─────────────────────────────┐        │
          │      BRIDGE (launchd)       │────────┤
          │  read: parsed_signal /      │        │
          │        management_cmd /     │        │
          │        aurum_cmd /          │        │
          │        market_data /        │        │
          │        status (init)        │        │     ┌──────────────┐
          │  S1/S1b/S2/CONFIRM gates    │◀──HTTP─┼─────│  ATHENA      │
          │  forge_queue → MT5 EA       │  AURUM_│     │  Flask :7842 │
          │  scribe.log_trade/group/    │  EXEC  │     │  /api/mode → │
          │       gate/system_event     │        │     │  writes      │
          │  HERALD.send (sync)         │        │     │  aurum_cmd   │
          └──┬───────────┬────────┬─────┘        │     └──┬───────────┘
             │           │        │              │        │
     forge_  │  status   │  HERALD│  (in-proc)   │  status│
     command*│  .json    │  (in-proc fan-in)     │  .json │
     .json   │  (write)  │        │              │  read  │
     (write) │           │        ▼              │        │
             ▼           │   ┌────────────────┐  │        │
          ┌──────────┐   │   │    HERALD      │  │        │
          │ FORGE EA │   │   │  (in-proc      │──┘        │
          │  (MQL5)  │──▶│   │   singleton    │           │
          │  market_ │   │   │   in BRIDGE +  │           │
          │  data.   │   │   │   AURUM +      │◀──────────┤
          │  json    │   │   │   LISTENER)    │  HERALD   │
          │  (write) │   │   │  → Telegram    │           │
          └──────────┘   │   └────────────────┘           │
                         │                                │
                         ▼                                │
                    ┌─────────────────────────────────┐   │
                    │       AURUM (launchd)           │───┘
                    │  Telegram bot → ask() → Claude  │
                    │  read: status / market_data /   │
                    │        sentinel_status /        │
                    │        scribe (history,         │
                    │        recent signals, regime)  │
                    │  write: aurum_cmd.json (cmds) / │
                    │         aurum_mcp_results.json  │
                    │         (own internal cache)    │
                    │  HERALD.send (sync)             │
                    └────────┬────────────────────────┘
                             │
                             ▼
                     ┌─────────────────────────────────┐
                     │  SCRIBE (in-proc, SQLite)       │
                     │  python/data/aurum_intelligence.db │
                     │  Touched by ALL 4 services:     │
                     │   LISTENER 23 sites             │
                     │   AURUM    22 sites             │
                     │   BRIDGE   83 sites  ← elephant │
                     │   ATHENA   (via /api/* reads)   │
                     └─────────────────────────────────┘
```

Anchors this diagram is consistent with:

- `python/listener.py` — Telethon ingest + Haiku parse, writes `parsed_signal.json` + `management_cmd.json`, calls `scribe.log_signal` / `scribe.log_news_event`.
- `python/bridge.py:4536-4581` — AEB action dispatch (incl. `AURUM_EXEC` via Athena HTTP).
- `python/bridge.py:4590-4625` — `_report_aeb_result` (current Telegram post site that §4 will gate).
- `python/aurum.py` — Telegram bot loop, reads status / market_data / sentinel_status / scribe history; writes `aurum_cmd.json`; HERALD.send to Telegram.
- `python/athena_api.py` `/api/mode` — writes `aurum_cmd.json` as a mode-change command into BRIDGE's input bus.
- `python/herald.py` — sync, in-proc; instantiated inside BRIDGE / AURUM / LISTENER, each fans out to Telegram.
- `python/scribe.py` — SQLite at `python/data/aurum_intelligence.db`; per `docs/SCRIBE_DECOMP_AUDIT.md` BRIDGE owns the bulk of the write sites; see `project_scribe_migration_planned.md` memory for why bridge/scribe decomp is deferred until scribe replacement ships.

The §4 fix (route tool results back through AURUM as a new conversation turn) operates entirely inside this fabric — no new transport, no new process. The "raw JSON to Telegram" arrow today is the HERALD.send leg from BRIDGE; the fix suppresses that one arrow and adds an `aurum_tool_result.json` write from BRIDGE that AURUM reads as a synthetic system turn.

---

## 3. Why the obvious pasted-in fix doesn't drop in as written

The discussion that raised this issue included sample code for
`_handle_scribe_query()` and `_ask_aurum()` living on the BRIDGE class with a
`self.conversation_history[source]` dict. **Those don't exist in our
codebase** — be aware before implementing:

| Symbol in the proposal | Reality |
|---|---|
| `bridge._handle_scribe_query(action, reply_to)` | Doesn't exist. The branch is inline at `bridge.py:4536-4552`; the executor is `aeb_executor.execute_action(cmd, db_path, project_root)`. |
| `bridge._ask_aurum(message, source, inject_as_system)` | Doesn't exist. BRIDGE doesn't call AURUM directly — it writes `aurum_cmd.json` for AURUM to pick up, and AURUM (a separate process / launchd service) is the one talking to the Claude API. |
| `self.conversation_history[source]` | Doesn't exist on `bridge`. AURUM owns conversation history in `scribe.aurum_conversations` (rows written via `aurum.py:217 scribe.log_aurum_conversation`, read back at `aurum.py:375-405`). |
| `await self.herald.send(...)` | Herald is sync, not async — `herald.send(...)` (see e.g. `bridge.py:4614`). Mass-converting to `await` would touch every herald call site. |

The design intent is right; the wiring needs to respect our actual
process/transport boundary.

## 4. Proposed solution — Option 1 (operator-recommended)

After BRIDGE executes a tool call, route the result back through AURUM **as a
new turn in AURUM's conversation history**, let AURUM call Claude to format
it, and send AURUM's formatted reply to Telegram — suppressing the raw post.

### 4a. Boundary-correct sketch

Two reasonable implementation paths:

**Path A — file channel (mirrors `aurum_cmd.json`)**

1. BRIDGE writes `python/config/aurum_tool_result.json` with the same envelope
   that today goes to Telegram, plus the originating `cmd` and `source`.
2. AURUM polls that path (same loop that polls `aurum_cmd.json`), ingests the
   row as a synthetic user-or-system turn, calls Claude with the existing
   conversation history + the new turn, writes the formatted answer to
   Telegram via the existing `herald.send` path AURUM already uses.
3. BRIDGE gates `_report_aeb_result`'s `herald.send(...)` behind a feature
   flag (`AEB_RESULT_AUTOFORMAT=1` default on) so the raw post is only emitted
   when the AURUM round-trip fails or times out (fallback for resilience).

**Path B — HTTP endpoint on AURUM (or on Athena, proxying AURUM)**

1. AURUM (or Athena) exposes `POST /aurum/tool_result`.
2. BRIDGE POSTs the result envelope (auth via the existing
   `ATHENA_AURUM_EXEC_SECRET` shared secret, see `bridge.py:102`).
3. The endpoint appends the turn to conversation history, calls Claude,
   returns the formatted reply. BRIDGE sends that reply to Telegram (or the
   endpoint sends it itself and BRIDGE just suppresses the raw post).

Path A is cheaper (no new HTTP surface, reuses the file-bus pattern AURUM
already trusts). Path B has cleaner error semantics (HTTP status codes vs
"did the file get picked up"). Default recommendation: **Path A**.

### 4b. Suppression of the raw post

The raw Telegram post is at `bridge.py:4614 self.herald.send(format_result_for_telegram(...))`.
Gate it behind:

```python
AEB_RESULT_AUTOFORMAT = os.environ.get("AEB_RESULT_AUTOFORMAT", "1") == "1"
...
# in _report_aeb_result:
if not AEB_RESULT_AUTOFORMAT:
    self.herald.send(format_result_for_telegram(result, max_chars=AEB_TELEGRAM_MAX_CHARS), parse_mode=None)
```

…then have the autoformat path post raw **only on AURUM-format failure / timeout**
so the operator never loses observability when the round-trip breaks.

### 4c. Loop-prevention safety

Because the result re-enters AURUM and AURUM can emit *more* commands, this
loop must be bounded:

- Mark the synthetic turn with `origin: "TOOL_RESULT"` so AURUM's
  command-extractor refuses to interpret it as a new command-emitting user
  message — AURUM should reply in prose only.
- Hard cap: if AURUM does emit a JSON command in response to a `TOOL_RESULT`
  turn, BRIDGE rejects it with `AURUM_OPEN_SKIPPED reason=tool-result-recursion`
  (matches the existing skip-reason vocabulary the bridge-monitor skill greps for).
- Time-bound: if AURUM doesn't respond within `AEB_AUTOFORMAT_TIMEOUT_SEC=15`,
  BRIDGE falls back to the raw post.

### 4d. Phased implementation plan (chosen path: A — file channel)

Roll-out is split into four phases so we can verify each layer before flipping
operator-visible Telegram behavior. Each phase is independently revertible
(just unset the env var or revert the commit).

#### Phase 1 — plumbing (zero operator impact)

**Goal:** prove the IPC works end-to-end without changing what the operator sees.

| Component | Change |
|---|---|
| `python/bridge.py` | Add env `AEB_RESULT_AUTOFORMAT` (default **OFF** in Phase 1). Define constant `AURUM_TOOL_RESULT_FILE = "config/aurum_tool_result.json"`. Add helper `_write_aurum_tool_result_envelope(result, *, cmd, source, via)` that writes `{action, source, via, result, cmd, origin: "TOOL_RESULT", queued_at}` to that path. From `_report_aeb_result`, call the helper **before** the existing `herald.send(...)` — so the file gets written on every AEB result, but the raw Telegram post still fires. |
| `python/aurum.py` | Add a poller mirroring the existing `aurum_cmd.json` poller — same loop pattern. On poll: read file, log INFO `AEB_RESULT_RECEIVED action=… source=… via=… ok=…`, then delete the file (consumption ACK). No Claude call yet, no Telegram post yet. |
| `.env.example` | Document the new envs (default values + what they do). |

**Verification:** trigger any SCRIBE_QUERY from Telegram, confirm `aurum.error.log` shows `AEB_RESULT_RECEIVED` within ~1s of the BRIDGE-side post. Telegram behavior unchanged.

#### Phase 2 — AURUM formats the reply (both posts visible)

**Goal:** see Claude's framing of the result before we suppress the raw post.

| Component | Change |
|---|---|
| `python/aurum.py` | Replace the Phase-1 logging stub with the real ingestion: append a synthetic turn to the conversation buffer for `source` (with `origin: "TOOL_RESULT"`), include a short system note ("a tool you queued returned this; respond in prose, do not emit a new command"), call `self.ask(...)` (or the equivalent Claude-call path) so the response flows through the same pipeline as a normal user turn — including the existing `herald.send` for Telegram. Loop guard: in `_extract_json_commands_from_response`, short-circuit when the just-completed turn is `origin="TOOL_RESULT"`; if Claude emitted JSON anyway, log `AURUM_OPEN_SKIPPED reason=tool-result-recursion` and write nothing to `aurum_cmd.json`. |
| `python/bridge.py` | Unchanged from Phase 1 (still default-OFF; raw post still fires). |

**Verification:** trigger SCRIBE_QUERY → operator sees **both** raw JSON post (BRIDGE) and AURUM's formatted prose reply (AURUM). Compare side-by-side; iterate on Claude framing if needed. If AURUM ever emits a command in response to TOOL_RESULT, the `AURUM_OPEN_SKIPPED reason=tool-result-recursion` log line catches it.

#### Phase 3 — suppression + timeout fallback (cutover)

**Goal:** operator now sees one clean reply per tool call. Raw only on failure.

| Component | Change |
|---|---|
| `python/bridge.py` | Flip `AEB_RESULT_AUTOFORMAT` default to **ON**. Modify `_report_aeb_result`: when autoformat is on, **suppress** the synchronous `herald.send(format_result_for_telegram(...))` post. Instead, after `_write_aurum_tool_result_envelope`, register a delayed-check (`AEB_AUTOFORMAT_TIMEOUT_SEC` default 15s): when the deadline fires, check if `aurum_tool_result.json` still exists (AURUM hasn't consumed it). If yes → AURUM dead/stuck → do the raw post + log `AEB_RESULT_AUTOFORMAT_TIMEOUT`. If gone (AURUM consumed it cleanly) → log `AEB_RESULT_AUTOFORMAT_OK`, no raw post. |
| `python/aurum.py` | Unchanged from Phase 2 (consumption = file delete still serves as ACK). |
| `.env.example` | Update default values to match the flip. |

**Verification:** trigger SCRIBE_QUERY → only one Telegram reply (AURUM's prose). Stop AURUM service, trigger another → after 15s deadline, raw post arrives + `AEB_RESULT_AUTOFORMAT_TIMEOUT` in bridge log. Re-start AURUM → next call back to clean prose-only.

#### Phase 4 — finishing (hygiene, no runtime change)

**Goal:** lock in the rollout: monitoring, tests, doc cleanup.

| Item | Change |
|---|---|
| `.claude/skills/aurum-bridge-monitor/SKILL.md` | Step 1 grep pattern: add `AEB_RESULT_AUTOFORMAT_OK\|FAILED\|TIMEOUT\|AURUM_OPEN_SKIPPED reason=tool-result-recursion\|AEB_RESULT_RECEIVED`. Step 2 interpretation table: new row "AURUM formatting-only reply triggered by TOOL_RESULT" (correct silence — no gate path expected); new row for the recursion-skip event (= bug, flag if seen in normal operation). Strike "raw JSON SCRIBE result posted to Telegram" from the expected-events list. |
| `tests/test_aurum_tool_result_feedback.py` *(new)* | End-to-end: AURUM emits SCRIBE_QUERY → BRIDGE writes envelope + suppresses raw → AURUM consumes within timeout → formatted reply posted. Second case: AURUM unreachable → raw fallback + TIMEOUT log line. |
| This doc | Status banner → `RESOLVED <commit-sha> <date>`; append commit reference to §6 resolution checklist. |
| `docs/changelog.md` (or canonical changelog) | Row under shipping version describing the cutover + the env-var defaults that landed. |

#### Phase 5 — TradingView MCP `chart_command` (follow-on, separate ship)

After Phase 3 has been stable for a session or two, apply the same envelope
pattern to MCP results — see §5 below. Reuses `aurum_tool_result.json` so the
AURUM-side ingestion loop is unchanged; only the BRIDGE-side write site moves
from `_report_aeb_result` to the `mcp_client.call(...)` wrapper.

#### Cross-phase env-var table

| Var | Default in Phase | Effect |
|---|---|---|
| `AEB_RESULT_AUTOFORMAT` | **OFF** in P1-P2, **ON** in P3+ | When ON, BRIDGE suppresses raw post on success; when OFF, raw post always fires |
| `AEB_AUTOFORMAT_TIMEOUT_SEC` | `15` (P3+) | If AURUM doesn't consume the result file in this window, raw fallback fires |
| `AURUM_TOOL_RESULT_FILE` | `config/aurum_tool_result.json` (all phases) | Override the file path (mostly for tests) |

#### Rollback path (any phase)

- **P1 / P2:** revert the commit(s); no runtime effect persists (autoformat is OFF by default).
- **P3:** set `AEB_RESULT_AUTOFORMAT=0` in `.env`, `make restart`. Raw posts resume immediately, no code change needed.
- **P4:** doc/test/skill changes only; revert as standard PR rollback.

## 5. TradingView MCP `chart_command` — same shape, different transport

The `chart_command` path doesn't go through `aeb_executor`; it goes through
the `tv-mcp` daemon (`make tv-mcp-*` targets, `python/bridge.py` MCP client
call sites). Same fix pattern applies: after `mcp_client.call(tool, args)`
returns, route the result through the AURUM-format channel above instead of
letting it land as a `CHART_COMMAND_MCP_CACHE` block visible only on the next
prompt.

Open question: should the MCP path share `aurum_tool_result.json` with
SCRIBE/SHELL/ANALYSIS, or use its own file? **Suggested:** share — one
ingestion loop in AURUM, the envelope already carries `action` to disambiguate.

## 6. Resolution checklist — DO THIS WHEN THE FIX LANDS

When the implementation merges:

- [ ] Update `.claude/skills/aurum-bridge-monitor/SKILL.md` Step 2c (the
      "AURUM emits JSON" interpretation) to add a new event: AURUM emitting a
      *formatting-only* reply triggered by a `TOOL_RESULT` turn (no gate path
      should fire — this is correct silence).
- [ ] Add a new grep pattern to the Monitor command in Step 1 to catch
      `AEB_RESULT_AUTOFORMAT_OK` / `AEB_RESULT_AUTOFORMAT_FAILED` /
      `AEB_RESULT_AUTOFORMAT_TIMEOUT` log lines.
- [ ] Add a new line to Step 2's interpretation table for
      `AURUM_OPEN_SKIPPED reason=tool-result-recursion` (loop guard fired —
      flag as a bug if it ever happens in normal operation).
- [ ] Strike "raw JSON SCRIBE result posted to Telegram" from the skill's
      expected events. The new expected post is AURUM's formatted prose reply.
- [ ] Add an end-to-end test (`tests/test_aurum_tool_result_feedback.py`)
      that asserts: operator-style Telegram message → SCRIBE_QUERY emitted →
      raw post suppressed → AURUM formatted reply posted within timeout.
- [ ] Update this doc's status banner to `RESOLVED` with the commit SHA + date.
- [ ] Append a row to `docs/changelog.md` (or the canonical changelog if
      another path is established) under the version that ships the fix.

## 7. Out of scope (don't expand here)

- Replacing the Telegram transport with anything else.
- Changing AURUM's model, prompt, or SOUL.md.
- Adding new actions to the AEB whitelist.
- Refactoring `_ask_aurum`-style direct-call patterns into bridge.py (would
  cross the process boundary in the wrong direction).

## 8. References (code anchors)

| File | Lines | What's there |
|---|---|---|
| `python/bridge.py` | 4536-4552 | AEB action dispatch (`SCRIBE_QUERY`, `SHELL_EXEC`, `ANALYSIS_RUN`) |
| `python/bridge.py` | 4554-4581 | `AURUM_EXEC` dispatch via Athena HTTP |
| `python/bridge.py` | 4590-4625 | `_report_aeb_result` — the Telegram post site to gate |
| `python/bridge.py` | 4627-4690 | `_dispatch_aurum_exec` — HTTP path for AURUM_EXEC |
| `python/aurum.py` | 217 | `scribe.log_aurum_conversation` — where turn rows are written |
| `python/aurum.py` | 375-405 | Conversation-history readback for Claude prompt assembly |
| `python/aeb_executor.py` | — | `execute_action`, `format_result_for_telegram` (Telegram-side formatter — still useful for raw fallback) |
| `.claude/skills/aurum-bridge-monitor/SKILL.md` | Step 1, Step 2c | Monitor grep pattern + AURUM JSON-emit interpretation block |
