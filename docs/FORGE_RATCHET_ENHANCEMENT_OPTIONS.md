# FORGE Ratchet — Enhancement & Security Options

4 distinct enhancement directions and 4 distinct security directions. Each is independent of the others — pick + sequence in any order.

---

## Enhancement (parity work)

### E1 — BRIDGE-side equivalents for EA L0/L1/L4/L5/L6/L7/L8 (modify-only ratchet layers)

- **Why:** feature parity so AURUM-via-BRIDGE has same management toolkit as EA's autonomous logic
- **Effort:** Multi-day. Each layer is a Python state tracker + command emitter. Reuses existing `_enqueue_forge_command` plumbing.

---

### E2 — BRIDGE-side equivalents for L3 (pre-TP1 recovery) + L9 (post-TP1 ladder)

- **Why:** parity for new-order ratchet layers; routes through Aegis (first placement of additional positions)
- **Effort:** Larger — touches Aegis, scribe `trade_groups`

---

### E3 — DD breaker graduation (warn → close-losers → close-all)

- **Why:** replace single-threshold hammer with graduated response
- **Effort:** 1-day, contained to `bridge.py` `_check_drawdown`

---

### E4 — Profit-ratchet adaptive buffer on broker rejection

- **Why:** rescue B2 attempts that currently fail silently when buffer < broker min-stops
- **Effort:** <1h, contained to `_compute_ratchet_tp`

---

## Security (gap closures)

### S1 — AURUM destructive-command confirmation gate ✅ SHIPPED 2026-05-15

- **Why:** prevents G5008-class accidents (literal `CONFIRM <id>` reply within 30s required before any destructive AURUM cmd dispatches)
- **Effort:** done — `python/bridge.py` (gate + pending queue + Herald prompt + CONFIRM handler + TTL sweep), `python/aurum.py` (Telegram intercept + CONFIRM in `valid_actions`), `SKILL.md` §5 confirmation rules
- **Scope:** `CLOSE_ALL`, `CLOSE_GROUP`, `CLOSE_GROUP_PCT`, `CLOSE_PCT`, `CLOSE_PROFITABLE`, `CLOSE_LOSING`, `MOVE_BE`, and GLOBAL-scope `MODIFY_SL`/`MODIFY_TP`. Per-ticket / per-group / per-stage modifies stay gate-free.
- **TTL:** 30s default (`AURUM_CONFIRMATION_TTL_SEC` env override). Pending proposals swept every Bridge tick.
- **Activation:** requires `make reload-bridge` to pick up changes.

---

### S2 — Per-action dedup window in `_check_aurum_command`

- **Why:** prevents duplicate Telegram processing
- **Effort:** <1h

---

### S3 — F4-corrected: EA L5 (`move_be_on_tp1`) strictly-better SL check

- **Why:** prevents L5 from overwriting BRIDGE B1's tighter lock
- **Effort:** 30min, contained to `FORGE.mq5` L5 block

---

### S4 — EA-side `ExecuteOpenGroup` sanity checks ✅ SHIPPED 2026-05-15

- **Why:** defense in depth — refuse pathological commands even if upstream Aegis approves. Today's G411 (AURUM 0.5 lot SELL, 6× prior leg size) passed Aegis but only avoided filling by timing — S4 explicitly rejects that class.
- **Done:** new `ValidateOpenGroupSanity()` helper in `ea/FORGE.mq5` + three input parameters (`ExecOpenGroup_MaxLotPerLeg=2.0`, `MaxEntryDeviationAbs=50.0`, `MaxSlDistanceAbs=100.0` — XAUUSD-tuned; 0 disables per-check). Validates: lot ceiling, direction-aware SL/TP wrong-side checks, SL distance cap, entry-vs-market deviation cap. Rejection logs `FORGE: OPEN_GROUP REFUSED G<id> <dir> — S4 sanity: <reason>` with 9 distinct reason codes.
- **Activation:** `make forge-compile` done (FORGE.ex5 v2.7.123, 583582 bytes). MT5 must reload the .ex5 (remove + drag-drop FORGE chart, or restart MT5) before the new gate is active in live trading.

---

Mix and match as you like. Or sit on the diagram and think more.
