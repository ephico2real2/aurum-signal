# /mcp-trace-aurum — Validate every change to tradingview-mcp-aurum with tracer evidence

You are working on the **tradingview-mcp-aurum** fork at `/Users/olasumbo/tradingview-mcp-aurum`. This is the LENS MCP server that AURUM spawns to read/write TradingView via Chrome DevTools Protocol.

**Operator rule (2026-05-16, foundational)**: *"I don't wanna ship bad code."* Every code change to this MCP must be validated against the live tracer (`src/tracer.js` → `/tmp/mcp-trace-aurum.log`) BEFORE commit. The operator will fire Telegram messages that exercise the changed code path; you read the NDJSON trace, prove the change behaves as designed, then summarize.

**You ASK before committing or shipping.** Default is *ask*. Only skip the ask when the operator explicitly says "skip validation", "just commit", or similar. Authorization is per-change, not per-session.

**No shortcuts, never a bad job (2026-05-16, foundational)**: *"we don't take shortcuts and never do a bad job. You are a great and experienced developer."* The operator collaborates with you as a senior — that means you complete the work properly, not the easy 80%. When a gap is identified (e.g. *"the lazy-recovery path isn't observable"*), you implement the fix in full — instrumentation, tests, validation, glossary updates, doc additions — not a TODO comment, not a "follow-up later" framing. Quick-and-dirty is allowed **only during debugging** (a one-shot `console.log`, a fast bisect script, a one-line monkeypatch to confirm a hypothesis). Quick-and-dirty is NOT allowed in shipped code, even when it would technically work. If you're tempted to "leave it as a follow-up" and the change is in-scope, the right move is to do it now — full quality, with the same validation loop as the primary change.

---

## When this skill applies

Trigger phrases: `/mcp-trace-aurum`, `mcp-trace-aurum`, "test the mcp", "validate the tracer", "fire a message and check the trace", or any session where the operator is iterating on `/Users/olasumbo/tradingview-mcp-aurum/` files.

This skill is the **validation gate** for fork edits. Do not commit fork changes outside this loop.

---

## The validation loop (one cycle per change)

```
1. STATE         Confirm tracer is hot + capture file mark
2. ASK           Tell operator what kind of message to fire (and why it exercises the change)
3. WAIT          Operator fires Telegram message to AURUM
4. INSPECT       Read the NEW trace events (since the mark) — never the whole file
5. VALIDATE      Cross-check events against the change's intent
6. SUMMARIZE     One short verdict per change: PASS / FAIL / INCONCLUSIVE
7. ASK           "Ship? / Adjust? / Test another path?" — wait for operator
```

Do not collapse steps. Do not commit between 6 and 7.

---

## Step 1 — STATE (confirm tracer is hot)

Before asking the operator to fire anything, verify:

```bash
# Env var set in signal_system .env (AURUM reads this when it spawns the MCP)
grep -n MCP_TRACE_FILE /Users/olasumbo/signal_system/.env

# Trace file exists and is writable
ls -la /tmp/mcp-trace-aurum.log

# Capture the byte offset NOW — this is the "mark"
wc -c < /tmp/mcp-trace-aurum.log
```

Save the byte offset (call it `$MARK`). Every later `tail -c +$((MARK+1))` reads ONLY events emitted after this point — clean isolation from prior session noise.

If `MCP_TRACE_FILE` is unset in `.env`, the next spawned MCP subprocess will boot tracer-disabled. Fix the env, then `make reload-bridge` (which also reloads aurum.py) so AURUM picks up the new env. Re-mark after the reload.

If the AURUM service was restarted between the operator's last fork edit and now, the change is live. If not — and the edit touched `src/server.js`, `src/connection.js`, or anything imported at startup — the next MCP spawn already picks up the change (MCP is spawn-per-call from `python/mcp_client.py`); no service reload required for fork code.

But: if the operator changed `.env` (added/changed `MCP_TRACE_*`), reload IS required because the env is injected at AURUM service start, not at MCP-subprocess spawn. (Verify with `ps -e | grep aurum` start time.)

## Step 2 — ASK (specify the test stimulus)

Tell the operator EXACTLY what to send and why. Examples:

| Change touches | Ask the operator to send |
|---|---|
| `evaluateWrite` callers (chart, drawing, alerts, indicators, pine) | "Send a write — e.g. *'set timeframe to 15m'* or *'change symbol to XAUUSD'*. This exercises `evaluateWrite` → mutex." |
| `withWriteLock` callers (multi-step writes like `chart_manage_indicator`) | "Send *'add RSI indicator'* — this is multi-step so we'll see `writeLock.queued` → `.acquired` → multiple inner `evaluate.*` → `.released`." |
| Read-only code (`evaluate` callers — quote, market data, lens) | "Send *'how's gold looking?'* or *'show me the chart'* — read-only path, we'll see `evaluate.start`/`.end` only." |
| Tracer itself (`src/tracer.js`) | Ask for ANY message — verify field shape, `pid`/`seq`/`tool` attribution, file rotation if applicable. |
| Reconnect / CDP plumbing (`connection.js`) | "Close + reopen the TradingView tab, then send a query — we want a fresh CDP reconnect in the trace." |

State the prediction explicitly:
> "I expect to see: `evaluateWrite.queued` (excerpt='Symbol.search...') → `evaluateWrite.acquired` (wait_ms ~0) → ... → `evaluateWrite.released` (work_ms < 2000)."

If the prediction is vague, the validation is vague. Predict concretely.

## Step 3 — WAIT

The operator fires the message. They will tell you when ("fired", "sent", "done", or implicit by you noticing new events). DO NOT spin a polling Monitor — let them signal.

Optional: arm a one-shot tail with `Monitor` only if the operator asks for live-stream relay. Otherwise just inspect after they confirm send.

## Step 4 — INSPECT (read only NEW events)

```bash
# Read events emitted after $MARK
NEW_BYTES=$(( $(wc -c < /tmp/mcp-trace-aurum.log) - MARK ))
tail -c "$NEW_BYTES" /tmp/mcp-trace-aurum.log > /tmp/mcp-trace-window.ndjson
wc -l /tmp/mcp-trace-window.ndjson
```

Common inspections:

```bash
# Event count by kind in this window
jq -r '.kind' /tmp/mcp-trace-window.ndjson | sort | uniq -c | sort -rn

# All write events grouped by PID (one MCP spawn per PID typically)
jq -r 'select(.kind|startswith("evaluateWrite") or startswith("writeLock"))
       | [.ts[11:23], .pid, .kind, .tool, .wait_ms//"", .work_ms//"", .excerpt//""]
       | @tsv' /tmp/mcp-trace-window.ndjson | column -t -s $'\t'

# Tool call counts
jq -r 'select(.kind=="evaluate.start" or .kind=="evaluateWrite.queued") | .tool // "(unattributed)"' \
   /tmp/mcp-trace-window.ndjson | sort | uniq -c | sort -rn

# Lifecycle traces — one tool from queued to released
jq -r 'select(.tool=="chart_set_timeframe") | [.ts[11:23], .kind, .wait_ms//"", .work_ms//""] | @tsv' \
   /tmp/mcp-trace-window.ndjson
```

If the new window is empty: the operator's message didn't reach AURUM, or AURUM didn't dispatch to MCP (e.g. info query answered from cache), or MCP spawn failed. Investigate AURUM logs (`make logs-aurum`) before claiming a tracer failure.

## Step 5 — VALIDATE (prediction vs reality)

For every change being tested, present a 3-column table to the operator:

| Prediction | Observed in trace | Status |
|---|---|---|
| `evaluateWrite.queued` for chart_set_timeframe | `seq=4 pid=98221 kind=evaluateWrite.queued tool=chart_set_timeframe excerpt='var w = window.TradingViewApi...'` | ✅ |
| `wait_ms == 0` (no contention, single MCP spawn) | `wait_ms=0` | ✅ |
| `work_ms < 2000` | `work_ms=1437` | ✅ |
| No `evaluateWrite.error` | (none) | ✅ |

If any row is ❌ or missing — STOP. Do not summarize as success. Show the operator the discrepancy and ask whether to adjust the code or the prediction (sometimes the prediction was wrong).

## Step 6 — SUMMARIZE (one short verdict per change)

```markdown
**Change**: <one-line description, e.g. "F2 mutex serializes concurrent writes via evaluateWrite()">
**Test stimulus**: <what operator fired, e.g. "Telegram: 'change timeframe to 15m'">
**Trace evidence**: <bullet of N events emitted, with PID + timing>
**Verdict**: PASS / FAIL / INCONCLUSIVE
**Why**: <one sentence — if FAIL, name the gap; if INCONCLUSIVE, name what's missing>
```

Keep this ≤8 lines. The operator wants verdict-first, not narrative.

## Step 7 — ASK (ship / adjust / next)

After the summary, ask exactly one question:

> "Verdict above. Ship this change (commit + push)? Adjust the code first? Or test another path before deciding?"

Wait. Do not commit. Do not push. Do not edit anything in the fork. Even if the verdict is PASS, the operator may want to test additional paths before shipping.

The ONLY exception: the operator's current message contains explicit ship authorization for this change ("yes ship it", "commit and push", "skip validation, ship it"). Authorization is for THIS change only — the next change re-enters the loop at Step 1.

---

## Anti-patterns (rejected by operator history)

| ❌ Don't | ✅ Do |
|---|---|
| Commit code, then run the bench, then claim "validated" | Run bench/test → show trace evidence → summarize → ASK → commit on go-ahead |
| Say "the tracer works" without showing the actual NDJSON line for the change under test | Paste the literal `jq` output of the events from THIS test window |
| Read the whole 50MB trace file to find an event | Mark before, slice after — work in a small window |
| Assume MCP_TRACE_FILE is set because it was set yesterday | Re-`grep` the env, re-`ls` the file, on every session start |
| Predict vaguely ("I expect some write events") | Predict concretely with tool name + expected `wait_ms` / `work_ms` range |
| Continue to the next code edit while the previous one is still INCONCLUSIVE | Resolve the validation outcome for the current change before touching another file |
| Spawn a long-running Monitor that floods the chat | Inspect on-demand after operator says "fired" |

## Why this exists (incident reference)

2026-05-15 session: I committed `8e2a209` adding `writeLock.*` event kinds to the tracer, then ran `bench-mutex.mjs` to "validate" — but had not actually inspected the trace file to confirm `writeLock.queued` / `writeLock.acquired` / `writeLock.released` emitted live. The operator caught it: *"you are working too fast - we need to validate that this tracer is working"* → *"dude chill -"*. This skill is the corrective process: predict → fire → inspect → ASK → ship.

## Reference files

| File | Role |
|---|---|
| `/Users/olasumbo/tradingview-mcp-aurum/src/tracer.js` | Tracer implementation — read this when changing tracer behavior |
| `/Users/olasumbo/tradingview-mcp-aurum/src/connection.js` | `evaluate` / `evaluateWrite` / `withWriteLock` instrumentation points |
| `/Users/olasumbo/tradingview-mcp-aurum/src/server.js` | `withToolName` AsyncLocalStorage wrapper (attributes events to MCP tool) |
| `/Users/olasumbo/tradingview-mcp-aurum/docs/TRACING.md` | Operator-facing guide for the tracer (env vars, schema, jq recipes) |
| `/Users/olasumbo/tradingview-mcp-aurum/scripts/bench-mutex.mjs` | B1/B2/B3 concurrency bench — useful when validating mutex changes specifically |
| `/Users/olasumbo/signal_system/.env` | `MCP_TRACE_FILE=/tmp/mcp-trace-aurum.log` line lives here |
| `/Users/olasumbo/signal_system/python/aurum.py` | LLM agent; spawns MCP via `mcp_client.MCPSession` |
| `/Users/olasumbo/signal_system/python/mcp_client.py` | MCP subprocess spawn — env propagation happens here |

## `gh` auth recovery (when shipping)

When opening the upstream PR via `gh pr create` you may hit `HTTP 401: Requires authentication`. The token rotates / expires; the fix is a fresh device-code login. Operator's preferred command (2026-05-16) uses HTTPS protocol + web flow:

```bash
gh auth login -h github.com -p https -w
```

After the device-code flow completes, retry the `gh pr create` command — the new token takes effect immediately, no restart needed. Tell the operator to type the command into the prompt with the `!` prefix (e.g. `! gh auth login -h github.com -p https -w`) so the interactive device-code prompt lands in this session.

## Service ops (always Makefile, never raw)

If the `.env` changes during this session and you need AURUM to pick up the new env:

```bash
make reload-bridge   # reloads bridge + aurum + listener + sentinel (4 python services)
```

If you only changed fork code (anything under `/Users/olasumbo/tradingview-mcp-aurum/src/`), no reload — next MCP spawn picks it up.

If you're unsure: `make health` to check service ages + `ps -ef | grep aurum` to confirm AURUM is running.

## Markdown / docs

Any doc this skill touches (TRACING.md, README.md additions, etc.) follows the GFM rule from `.claude/skills/forge-monitor/SKILL.md`: pipe tables only, fenced code blocks with language tags, ATX headings, retroactive normalization on touch.
