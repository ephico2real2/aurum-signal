# LISTENER channel filter state

> **Last updated:** 2026-05-16 (post-restart at `14:51:14` UTC).
> **Owner:** operator-managed via `.env`. This file tracks the current
> configured state — update the snapshot section when channels are
> added/removed/repinned.

## 1. The three filter layers (top to bottom: drops earliest = saves the most)

| Layer | Env var(s) | Effect when filtered | Cost saved |
|---|---|---|---|
| **Subscribe** | `TELEGRAM_CHANNELS` | Listener never receives the message at all | Everything downstream |
| **Ingest** | `LISTENER_INGEST_ALLOWED_CHATS` | Dropped at top of `_handle_message` — no scribe row, no media download, no parse, no Herald | Full per-message cost (incl. Claude) |
| **Credit** | `LISTENER_CLAUDE_TRADE_ROOMS_ONLY` (default `1`) | Falls through to free regex parser — scribe row still written | Claude Haiku call only |

A separate **trade-room execution gate** (`SIGNAL_TRADE_ROOMS` / `ACTIVE_SIGNAL_TRADE_ROOMS`) decides whether a *parsed* signal is permitted to dispatch into BRIDGE. That gate runs AFTER the three filters above and is described in `listener.py` `_is_trade_room_allowed`.

## 2. Snapshot — live state of all four channels (2026-05-16, 15:05 UTC)

| Channel | chat_id | Subscribed? | Ingest gate | Trade-room |
|---|---|---|---|---|
| **Ben's VIP Club** | `-1002034822451` | ✅ | ✅ pass | ✅ executable |
| FXM FREE TRADING ROOM | `-1001959885205` | ✅ | ❌ dropped at ingest | ❌ not in allowlist |
| GARRY'S SIGNALS | `-1003582676523` | ✅ | ❌ dropped at ingest | ❌ not in allowlist |
| FLAIR FX | `-1002293626964` | ✅ | ❌ dropped at ingest | ❌ not in allowlist |

Active `.env` lines that produce this snapshot — both gates pinned to Ben's
(they must agree to avoid the "trade-room says yes but ingest drops it" trap):

```bash
TELEGRAM_CHANNELS=-1002034822451,-1003582676523,-1002293626964,-1001959885205
ACTIVE_SIGNAL_TRADE_ROOMS=-1002034822451
LISTENER_INGEST_ALLOWED_CHATS=-1002034822451
```

Boot-log fingerprint to confirm the snapshot took effect (grep `logs/listener.error.log`):

```
LISTENER: trade-room allowlist active — 1 entries from ACTIVE_SIGNAL_TRADE_ROOMS: ['-1002034822451']
LISTENER: ingest gate = ALLOW-LIST (1 entries from LISTENER_INGEST_ALLOWED_CHATS): ['-1002034822451'] — all other subscribed channels will be DROPPED at the top of _handle_message
LISTENER initialised — watching 4 channels
```

## 3. Coupling rule (both gates must agree)

`ACTIVE_SIGNAL_TRADE_ROOMS` and `LISTENER_INGEST_ALLOWED_CHATS` must list the
same chat_ids. If a chat is in trade-rooms but not in the ingest allow-list,
its messages get dropped before they can be parsed — the trade-room entry
becomes silent dead config. Always update both lines together when adding or
removing a channel.

## 4. How to widen / revert

### Add FXM back as an executable trade room

```bash
# in .env
LISTENER_INGEST_ALLOWED_CHATS=-1002034822451,-1001959885205
```

then:

```bash
make reload
```

### Go back to processing all four channels (no ingest filter)

Comment out or delete the line:

```bash
# in .env
# LISTENER_INGEST_ALLOWED_CHATS=...    ← remove or comment
```

then:

```bash
make reload
```

Boot log should switch back to:

```
LISTENER: ingest gate inactive — all subscribed channels will be processed
          (set LISTENER_INGEST_ALLOWED_CHATS to filter)
```

### Mute one channel without removing it from `TELEGRAM_CHANNELS`

Narrow the allow-list to exclude it. Example — keep Ben's + FXM, mute GARRY'S and FLAIR:

```bash
# in .env
LISTENER_INGEST_ALLOWED_CHATS=-1002034822451,-1001959885205
```

There is no separate block-list. The allow-list already implies "everything
else is blocked," so a second flag would only add config surface (precedence
rules between allow and block) without adding capability. Design choice
landed 2026-05-16.

## 5. `make reload` vs `make restart` — when each is needed

**Footgun verified 2026-05-16:** `make reload` does NOT pick up `.env` value
changes. The rendered plist (`services/macos/rendered/com.signalsystem.listener.plist`)
bakes in env key/value pairs at *install* time — launchd reads them from the
plist, not from `.env`. So any change to a value in `.env` requires re-rendering.

| Change to … | Run |
|---|---|
| Python source code (`listener.py`, `aurum.py`, etc.) | `make reload` |
| **Any value** in `.env` (new key OR new value for existing key) | `make restart` (re-renders all plists from `.env`, then reloads) |
| `services/macos/*.plist` template, or `install_services.py` | `make restart` |

When in doubt: `make restart` is safe; `make reload` is faster but only useful
for code changes, not config.

## 6. Semantics reference (when in doubt, this is authoritative)

From `python/listener.py` `_handle_message` ingest-gate block:

- If `LISTENER_INGEST_ALLOWED_CHATS` is **non-empty** → only listed chats are processed; everything else is dropped at the top of `_handle_message`.
- Else → all subscribed channels process normally (default).

Tokens are comma-separated with no surrounding whitespace. Each token can be a
chat_id (e.g. `-1001234567890`) OR a channel title (case + unicode + whitespace
normalized). Chat_ids survive channel renames; titles are easier to read. Both
forms work in the same env var.

## 7. Testing — `make test-ingest-gate`

Spoof-test the ingest allow-list against all known channels without touching
the live launchd-managed service. The script (`scripts/test_listener_ingest_gate.py`)
loads `.env`, imports the production `listener` module, and runs the SAME gate
logic that lives in `_handle_message` against synthetic message-shaped objects
for each channel — so it reports exactly what the running service would do.

```bash
# Test the current .env config (what the live listener is actually using)
make test-ingest-gate

# What-if: override the allow-list without editing .env
make test-ingest-gate ALLOW=-1002034822451,-1001959885205

# Test gate-off scenario (run the script directly to pass empty string)
.venv/bin/python scripts/test_listener_ingest_gate.py --allow=
```

Output prints PASS / DROPPED for each known channel + a final ✅/❌ summary
line. Exit code is 0 on success, 1 if any case diverges from expected.

If channels are added to or removed from `TELEGRAM_CHANNELS`, update the
`CHANNELS` list at the top of the script so the test stays in sync with prod.

## 8. Related files

| File | Why |
|---|---|
| `python/listener.py` | `_handle_message` (ingest gate) + `_parse` (credit gate) + `_is_trade_room_allowed` (execution gate) |
| `.env` | Live config — change here, `make reload` |
| `.env.example` | Documented examples + defaults |
| `services/install_services.py` | Renders `.env` keys into launchd plists (run by `make restart`) |
| `services/macos/rendered/com.signalsystem.listener.plist` | The plist launchd actually loads |
| `scripts/test_listener_ingest_gate.py` | Spoof-test the gate; run via `make test-ingest-gate` |
