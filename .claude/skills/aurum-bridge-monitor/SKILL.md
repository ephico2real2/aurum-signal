---
name: aurum-bridge-monitor
description: Tail aurum.error.log + bridge.log in real time with a focused grep filter and relay AURUM Telegram receipts, JSON command emissions, CONFIRM intercepts, BRIDGE gate decisions (S1 destructive-hold, S1b mode-restrict, S2 dedup, CONFIRM accept/expire/reject), Aegis approvals/rejections, trade dispatch, Herald posts, HTTP 4xx/5xx, and tracebacks. Idle file-poll WARNINGs are filtered out so the operator only sees real events. Invoke when the operator wants to validate a live AURUM↔BRIDGE flow — e.g. "monitor aurum + bridge", "validate the S1 gate is working", "watch what aurum is doing", "/aurum-monitor".
---

# /aurum-monitor — AURUM↔BRIDGE live-flow monitor

You are validating the AURUM→BRIDGE command pipeline end-to-end. The operator is about to send Telegram messages to AURUM (or queue commands via Athena) and wants you to confirm every step of the pipeline behaves correctly: receipt, parse, gate evaluation, dispatch, Herald post. **Silence is a meaningful signal** — if AURUM responds to an info query with prose and no gate path fires, that is *correct* and should be reported as such.

## Service ops — always use Makefile targets

The `Makefile` at the project root encodes the correct launchd lifecycle for all services. If during monitoring you need to restart anything, **check `make help` first**. Never use raw `kill <pid>` / `launchctl unload`/`load` / `pkill` — the `KeepAlive.Crashed=true` policy doesn't respawn on clean SIGTERM, so raw commands break.

| Need | Target |
|---|---|
| Reload BRIDGE | `make reload-bridge` |
| Reload AURUM | implicit via `make reload-bridge` (aurum is one of the four python services) — or `make reload` for all |
| Restart all | `make restart` |
| Health sweep | `make health` (also surfaces `tradingview_age_sec`, `lens_age_sec`) |
| Logs (paged) | `make logs-bridge` / `make logs-aurum` / `make logs-errors` |

## Step 1 — arm the monitor

Use the Monitor tool with a tail-F over both AURUM and BRIDGE logs, **two-stage grep** (first `grep -v` strips idle noise, then `grep -E` extracts the signal). Set `persistent: true` so the watch outlives short queries — and end with `TaskStop` when the operator signals "done".

```text
tool: Monitor
description: AURUM/BRIDGE gate test — filtered (no idle noise)
persistent: true
timeout_ms: 1800000
command: tail -F /Users/olasumbo/signal_system/logs/aurum.error.log /Users/olasumbo/signal_system/logs/bridge.log 2>/dev/null \
  | grep -v -E "Failed to read /Users/olasumbo/signal_system/python/config/(aurum_cmd|management_cmd|parsed_signal)\.json" \
  | grep -E --line-buffered "AURUM query from Telegram|AURUM: queued|AURUM: CONFIRM intercepted|AURUM_COMMAND_RX|AURUM_COMMAND_HELD|HELD pending CONFIRM|AURUM CONFIRM (accepted|: unknown)|AURUM_CONFIRMATION_(ACCEPTED|REJECTED|EXPIRED|QUEUED)|AURUM_COMMAND_DEDUPED|DEDUPED \(sig=|AURUM OPEN_GROUP rejected|AURUM_OPEN_SKIPPED|effective_mode=|TRADE_QUEUED|TRADE_REJECTED|\[AURUM\||\[MGMT\||CLOSE_ALL_QUEUED|MGMT_COMMAND|Pending (CLOSE|MODIFY|MOVE_BE)|🚫|⚠️|Traceback|CRITICAL|MCP error|HTTP/1\.1 4|HTTP/1\.1 5"
```

Critical implementation notes:
- The `grep -v` stage is REQUIRED. Without it the monitor floods you with `Failed to read aurum_cmd.json` every ~1s (BRIDGE polling for command files that don't exist in idle state). That noise drowns real events.
- `tail -F` (capital F) follows file renames — survives a launchd reload of bridge/aurum that rotates their stdout.
- `--line-buffered` is mandatory inside pipes or pipe buffering delays events by minutes.
- `persistent: true` — keep the monitor armed for the lifetime of the test session. Stop it explicitly with `TaskStop` when the operator signals done.

## Step 2 — interpret events

Categorize each notification line into one of:

### 2a. AURUM Telegram receipt (input)

```
2026-05-16 05:00:46,771 aurum INFO AURUM query from Telegram (bot): <text>
```

What it means: the operator messaged AURUM. Relay back **what the operator typed** (verbatim, in quotes) + your interpretation of intent:
- **Info query** (e.g. "what's my P&L", "how's gold looking", "tv news") → expect prose response, NO gate path.
- **Action language** (e.g. "close all", "sell at 4500", "move sl to X") → expect either prose (if AURUM proposes + waits for CONFIRM) OR JSON emission (if AURUM acts). Then watch for the gate response.

### 2b. AURUM JSON emit (command queued)

```
2026-05-16 hh:mm:ss aurum INFO AURUM: queued <ACTION> from response JSON (1/1)
```

What it means: AURUM parsed its own response, found a JSON fence with a valid `action`, wrote it to `aurum_cmd.json`. BRIDGE will pick it up on next tick. **Action types you'll see and what to expect next:**

| Action | Expected BRIDGE event |
|---|---|
| `OPEN_GROUP` | `AURUM_COMMAND_RX` → either `TRADE_QUEUED` (success) or `TRADE_REJECTED` (Aegis/AURUM_OPEN_SKIPPED) |
| `CLOSE_ALL` / `CLOSE_GROUP` / `CLOSE_GROUP_PCT` / `CLOSE_PCT` / `CLOSE_PROFITABLE` / `CLOSE_LOSING` / `MOVE_BE` | **S1 destructive gate** → `AURUM_COMMAND_HELD` + Herald `⚠️ Pending <ACTION>` |
| Global `MODIFY_SL` / `MODIFY_TP` (no `ticket`/`group_id`/`tp_stage`) | Same — **S1 hold** |
| Scoped `MODIFY_SL` / `MODIFY_TP` (with `ticket`/`group_id`/`tp_stage`) | Bypass S1 — direct dispatch, log `MGMT_COMMAND` |
| `SCRIBE_QUERY` / `AURUM_EXEC` / `SHELL_EXEC` / `ANALYSIS_RUN` | Bypass S1 + S2 — direct exec, log `AEB_EXEC_OK` |
| `CONFIRM` with `proposal_id` | Should not come from JSON — see 2c |

### 2c. AURUM CONFIRM intercept

```
2026-05-16 hh:mm:ss aurum INFO AURUM: CONFIRM intercepted from Telegram — proposal=<id>
```

What it means: the operator typed `CONFIRM <8-hex>` as raw text. `_handle_telegram_natural_language_command` short-circuited the LLM and wrote `{"action":"CONFIRM","proposal_id":"<id>"}` directly to `aurum_cmd.json`. Watch for BRIDGE's lookup next:
- `AURUM CONFIRM accepted: proposal=<id> action=<orig>` + the original action dispatch → S1 unsealed the held command.
- `AURUM CONFIRM: unknown or expired proposal_id=<id>` + Herald `⚠️ CONFIRM <id>: unknown or expired` → operator confirmed something that already expired or never existed (typo, TTL passed).

### 2d. BRIDGE gate decisions

| Pattern | Gate | Outcome |
|---|---|---|
| `BRIDGE: AURUM <ACTION> HELD pending CONFIRM (proposal=<id> ttl=30s): <summary>` | **S1 destructive gate** | Cmd held; Herald posted prompt; operator's `CONFIRM <id>` within 30s releases it. |
| `BRIDGE: AURUM <ACTION> DEDUPED (sig=<hex> age=<s>s window=10s)` | **S2 content-signature dedup** | Identical logical cmd (same action + params, ignoring timestamp/origin_source/reason) seen within 10s window. Dropped. |
| `BRIDGE: AURUM OPEN_GROUP rejected — effective_mode=<MODE>` | **S1b mode restriction** | AURUM OPEN_GROUP rejected because mode ∉ {HYBRID, AUTO_SCALPER}. Herald post `🚫 AURUM OPEN_GROUP rejected`. |
| `TRADE_REJECTED reason=MAX_GROUPS:N/M` / `SL_TOO_TIGHT:X<Ypips` / etc. | **Aegis validate()** | OPEN_GROUP rejected on geometry/risk. Not a bug — Aegis doing its job. |
| `TRADE_QUEUED ... source=AURUM ... group_id=N` | **Approved** | Order written to `forge_command.json`; EA picks up next tick. |
| `[AURUM\|CLOSE_ALL]` / `[MGMT\|CLOSE_GROUP]` / etc. | **Dispatch** | Command sent through to EA. Either operator-confirmed (post S1) or a non-destructive cmd that bypassed S1. |
| `AURUM_CONFIRMATION_EXPIRED reason=<ACTION>` | **S1 TTL sweep** | A held cmd timed out (30s) without `CONFIRM`. Logged + dropped. Good — operator didn't follow through, cmd safely discarded. |

### 2e. Error patterns (escalate immediately)

- `Traceback (most recent call last):` — Python crash. Read 5-10 lines following to identify which file/handler.
- `CRITICAL` — bridge/aurum surfaced a critical-level log.
- `HTTP/1.1 4XX` / `HTTP/1.1 5XX` on Anthropic API or Telegram — LLM unavailable or Telegram failing.
- `MCP error` — LENS or AURUM MCP call failed. Could be transient (Chrome closed) or persistent.
- `Aegis ... failed` — gate evaluator threw an exception (not a normal rejection — a code-level error).

## Step 3 — relay-format conventions (per-event)

For every notification I get, my response to the operator should be:

```
**`hh:mm:ss` <ROLE>**: brief one-line summary + tag (info-query / S1-held / dispatched / rejected / error).
```

Examples:

- `**05:00:46 AURUM**: "What is my TV setup from lens" — info query, no command expected.`
- `**05:09:12 AURUM**: queued CLOSE_ALL — S1 gate next.`
- `**05:09:13 BRIDGE**: CLOSE_ALL HELD pending CONFIRM (proposal=a3f9c2e1). 30s TTL.`
- `**05:09:14 Herald**: ⚠️ Pending CLOSE_ALL — Reply CONFIRM a3f9c2e1 within 30s.`
- `**05:09:18 AURUM**: CONFIRM intercepted from Telegram — proposal=a3f9c2e1.`
- `**05:09:19 BRIDGE**: CONFIRM accepted, dispatching CLOSE_ALL.`
- `**05:09:19 BRIDGE**: [AURUM|CLOSE_ALL] all groups closed in SCRIBE.`

**Keep relays tight.** One line per event ideally. Don't editorialize unless something is wrong. Silence between events = silence in the chat — never narrate "still watching" without a real event.

## Step 4 — validation checklist (offer the operator)

When the operator says "I want to validate S1 / S1b / S2 / CONFIRM" — offer these test cases. Wait for them to send the Telegram messages; relay events live.

| # | Test | Operator action | Expected event chain |
|---|---|---|---|
| **V1** | Info query baseline | Send: "How's gold looking" | `AURUM query from Telegram` only. NO gate firings. Confirms idle path is healthy. |
| **V2** | S1 destructive hold (CLOSE_ALL) | Send: "close all positions please" | `AURUM: queued CLOSE_ALL` → `BRIDGE: AURUM CLOSE_ALL HELD pending CONFIRM (proposal=X)` → Herald `⚠️ Pending CLOSE_ALL`. Then do nothing for 35s. Expect `AURUM_CONFIRMATION_EXPIRED reason=CLOSE_ALL`. |
| **V3** | S1 confirm path | Repeat V2, then within 30s send: `CONFIRM <id>` | `AURUM: CONFIRM intercepted` → `BRIDGE: AURUM CONFIRM accepted` → `[AURUM\|CLOSE_ALL]`. |
| **V4** | S1b mode restriction | Confirm bridge mode is SCALPER (`/api/status` or dashboard). Send: "sell gold here" | `AURUM_COMMAND_RX OPEN_GROUP` → `BRIDGE: AURUM OPEN_GROUP rejected — effective_mode=SCALPER` + Herald `🚫`. |
| **V5** | S2 dedup | Send the same trade twice within 10s: "sell gold at 4555 SL 4565 TP 4550" then identical | First → `TRADE_QUEUED` or `TRADE_REJECTED`. Second → `BRIDGE: AURUM OPEN_GROUP DEDUPED (sig=X age=Ns)`. |
| **V6** | Scoped MODIFY bypass | Send: "move SL on ticket 12345 to 4500" | `AURUM: queued MODIFY_SL` → direct dispatch, NO S1 hold (scoped modify is allowed without CONFIRM). |
| **V7** | Aegis catch | In HYBRID mode, send: "sell with SL 1 pip away" | `AURUM_COMMAND_RX OPEN_GROUP` → `TRADE_REJECTED reason=SL_TOO_TIGHT`. |

## Step 5 — cleanup

When the operator signals done ("stop monitoring", "thanks", "done testing", or implicit by switching topics for ≥10 min), kill the monitor with `TaskStop` referencing the task_id returned when you armed it.

## Anti-patterns

- ❌ Don't narrate idle silence ("still watching, nothing yet"). The operator can see the lack of notifications. Only chat when something happens.
- ❌ Don't pre-emptively predict what AURUM "will" do. Report what it did.
- ❌ Don't broaden the grep filter unless a missing event class needs catching. The two-stage grep is dialed in; expand only when a real gap appears.
- ❌ Don't `kill <pid>` services to "fix" a monitor; the monitor is read-only. If bridge/aurum need a restart, use `make reload-bridge` / `make reload`.

## When to recompile or reload first

If the operator's test depends on a code path that was changed locally but not yet rebuilt:
- Changed `python/bridge.py` or `python/aurum.py`? Run `make reload-bridge` BEFORE arming the monitor.
- Changed `ea/FORGE.mq5`? Run `make forge-compile` + remind operator MT5 must reload the `.ex5`.
- Changed `config/scalper_config.json` or `.env`? `make scalper-env-sync` (or `make forge-compile` which does it).

## Notes

- Today (2026-05-15/16) the gates are: S1 destructive-cmd CONFIRM (commit `9d25f2a`), S1b OPEN_GROUP mode restriction (`9d25f2a`), S2 content-signature dedup (`944d00b`), E3 graduated DD breaker (`73dcd0b`), S4 EA-side `ValidateOpenGroupSanity` (`0adbd11`), early-lock-floor port to EA L2 (`aa44d53`). Full architecture: `docs/FORGE_RATCHET_SYSTEM_ARCHITECTURE.md` and `docs/LENS_MCP_INTEGRATION.md`.
- Bridge mode at startup is restored from `python/config/status.json`. After `make reload-bridge` it usually comes up in the same mode it was in before the restart.
