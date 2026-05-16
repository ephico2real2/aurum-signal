# FORGE System Architecture — corrected, comprehensive

```
                              ┌──────────────────────┐
                              │   MT5 Broker         │
                              │   (Vantage live)     │ ◀── real money execution
                              └──────────┬───────────┘
                                         │ direct broker API
                                         │ (g_trade.OrderSend,
                                         │  PositionModify, PositionClose)
                                         ▼
                            ┌─────────────────────────────┐
                            │       FORGE EA (MQL5)        │ ◀──── ONLY component with
                            │                              │       MT5 direct access
                            │  Master trade-taker +        │
                            │  master ratchet authority    │
                            │  for ALL trades regardless   │
                            │  of who created them.        │
                            │                              │
                            │  Autonomous logic (OnTick):  │
                            │   ▸ CheckNativeScalperSetups │
                            │     (~30 setups, 50+ gates)  │
                            │   ▸ ManageOpenGroups → L0-L9 │
                            │     ┌─────────────────────┐  │
                            │     │ L0 Conviction-decay │  │
                            │     │ L1 Time-stop close  │  │
                            │     │ L2 Fast-lock SL trail│ │
                            │     │ L3 Pre-TP1 recovery │  │
                            │     │ L4 TP1 partial close│  │
                            │     │ L5 SL→BE + TP→TP2   │  │
                            │     │ L6 TP2 staging      │  │
                            │     │ L7 TP3 staging      │  │
                            │     │ L8 TP4 staging      │  │
                            │     │ L9 Post-TP1 ladder  │  │
                            │     └─────────────────────┘  │
                            │                              │
                            │  Command handlers (BRIDGE→EA):│
                            │   ExecuteOpenGroup           │
                            │   ExecuteCloseAll/Pct/Group  │
                            │   ExecuteModifySL/TP         │
                            │   ExecuteMoveBeAll           │
                            │   ExecuteCancelGroupPending  │
                            └──────────────┬───────────────┘
                                           │
                        ┌──────────────────┼──────────────────┐
                        │ writes every     │ polls every tick │
                        │ tick             │ (ReadAndExec     │
                        ▼                  │  Command :2534)  │
                ┌──────────────┐    ┌──────┴────────────────┐
                │ market_data  │    │  forge_command.json    │
                │ .json        │    │  (one cmd at a time,   │
                │ (full state) │    │   then deleted by EA)  │
                └──────┬───────┘    └──────────▲─────────────┘
                       │ reads                 │ writes
                       │                       │ (_write_forge_command
                       │                       │  via BridgeQueue
                       │                       │  with verifiers + retries)
                       │                       │
                       ▼                       │
      ┌────────────────────────────────────────────────────────────┐
      │                  BRIDGE (Python)                            │
      │                                                            │
      │  NO direct MT5 access. All commands go through FORGE EA.    │
      │                                                            │
      │  ┌──────────────────────────────────────────────────────┐  │
      │  │  Supplementary ratchet engine (modify-only,          │  │
      │  │  Aegis-bypassed by design):                          │  │
      │  │                                                      │  │
      │  │   B1 — PROFIT_RATCHET SL  (pip-based, MFE ≥ 30)      │  │
      │  │   B2 — Hybrid TP TIGHTEN  (per-ticket, cur±5pips)    │  │
      │  │   (and: _enqueue_move_be_for_group manual BE)        │  │
      │  │                                                      │  │
      │  │   ↓ emits MODIFY_SL / MODIFY_TP to forge_command.json│  │
      │  └──────────────────────────────────────────────────────┘  │
      │                                                            │
      │  ┌──────────────────────────────────────────────────────┐  │
      │  │  System-level circuit breaker (BRIDGE-unique):       │  │
      │  │                                                      │  │
      │  │   _check_drawdown → equity DD ≥ threshold → CLOSE_ALL│  │
      │  │   + forces mode to WATCH + Telegram alert            │  │
      │  └──────────────────────────────────────────────────────┘  │
      │                                                            │
      │  ┌──────────────────────────────────────────────────────┐  │
      │  │  Entry-creation orchestration (4 sources funnel here):│ │
      │  │                                                      │  │
      │  │   _check_aurum_command   (file poll: aurum_cmd.json) │  │
      │  │     → _dispatch_aurum_open_group                     │  │
      │  │   _process_mgmt_command  (Athena MGMT panel)         │  │
      │  │   _scalper_logic        (LENS-driven, asks AURUM)    │  │
      │  │   _auto_scalper_tick    (60s loop, asks AURUM)       │  │
      │  │                                                      │  │
      │  │   ↓ ALL paths converge here:                         │  │
      │  └──────────────────────┬───────────────────────────────┘  │
      │                         │                                  │
      │                         ▼                                  │
      │              ┌────────────────────────┐                    │
      │              │  AEGIS.validate()       │ ◀── decision     │
      │              │  (Anthropic SDK + R:R)  │     engine —      │
      │              │  ONLY on first-trade    │     ONLY for      │
      │              │  placement              │     OPEN_GROUP    │
      │              │                         │                   │
      │              │  ⚠ CLOSE_ALL / CLOSE_GROUP / MODIFY_SL /    │
      │              │    MODIFY_TP / CANCEL_PENDING bypass Aegis  │
      │              │    entirely — no validation layer between   │
      │              │    AURUM-parsed intent and EA execution.    │
      │              │    (Canonical incident: G5008, −$955.44.)   │
      │              └──────────┬─────────────┘                   │
      │                         │ approved                         │
      │                         ▼                                  │
      │              ┌────────────────────────┐                    │
      │              │  scribe.log_trade_group│ (persists state)   │
      │              │  _write_forge_command  │ (emits OPEN_GROUP) │
      │              └──────────┬─────────────┘                   │
      └─────────────────────────┼──────────────────────────────────┘
                                │
                                ▼ (writes to forge_command.json,
                                   which FORGE EA polls)
                                │
                                └─── back to FORGE EA at top of diagram

╔════════════════════════════════════════════════════════════════════╗
║ External command sources (all converge into BRIDGE's entry funnel) ║
╠════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║   ┌──────────────────────┐                                         ║
║   │  Operator Telegram   │ ──► AURUM (LLM agent, ──► aurum_cmd.json║
║   │  / Athena / Herald   │     playbook = SKILL.md)    (file)      ║
║   │  message             │                                         ║
║   └──────────────────────┘                                         ║
║                                                                    ║
║   AURUM is not a parser — it is an LLM agent operating under the   ║
║   SKILL.md playbook (/Users/olasumbo/signal_system/SKILL.md). The  ║
║   playbook lists 10 supported commands (OPEN_GROUP, CLOSE_ALL,     ║
║   CLOSE_GROUP, CLOSE_GROUP_PCT, MODIFY_SL, MODIFY_TP, …) and       ║
║   instructs the model to "act, you must not refuse" when the       ║
║   operator explicitly asks for trade or risk actions (§5).         ║
║                                                                    ║
║   ⚠ FAILURE SURFACE (S1):                                          ║
║     The "must not refuse" disposition means a conversational       ║
║     phrase ("close all", "move SL to 4660") inside a *question     ║
║     about* a trade is treated as an executable command. SKILL.md   ║
║     §5 line 289 mentions confirmation as OPTIONAL prose — there is ║
║     no enforced gate. Aegis cannot catch this because Aegis only   ║
║     validates OPEN_GROUP — CLOSE/MODIFY commands flow straight     ║
║     through to the EA.                                             ║
║                                                                    ║
║     G5008 (2026-05-15, −$955.44) was caused exactly this way:      ║
║     operator asked AURUM about the trade, message contained        ║
║     conversational "close all", AURUM emitted CLOSE_ALL, EA        ║
║     closed at a loss.                                              ║
║                                                                    ║
║     Mitigation S1 (SHIPPED 2026-05-15) — TWO-SIDED, defense-in-    ║
║     depth:                                                         ║
║      (a) SKILL.md §5: confirmation MANDATORY for destructive       ║
║          commands. AURUM must propose, never auto-CONFIRM itself.  ║
║      (b) bridge.py: destructive cmds HELD in                       ║
║          _pending_aurum_confirmations keyed by proposal_id (8-char ║
║          hex), TTL = AURUM_CONFIRMATION_TTL_SEC (30s default).     ║
║          Herald posts the prompt; operator's literal "CONFIRM      ║
║          <id>" reply, intercepted before the LLM in aurum.py       ║
║          _handle_telegram_natural_language_command, releases the   ║
║          held cmd for dispatch.                                    ║
║      Scope: CLOSE_ALL/_GROUP/_PCT/_PROFITABLE/_LOSING, MOVE_BE,    ║
║      and GLOBAL-scope MODIFY_SL/MODIFY_TP. Per-ticket/per-group/   ║
║      per-stage modifies stay gate-free (mirror EA L0-L9 path).     ║
║                                                                    ║
║   ┌──────────────────────┐                                         ║
║   │  Athena MGMT panel   │ ──► /api/mgmt ──► _process_mgmt_command  ║
║   │  (operator UI click) │                                         ║
║   └──────────────────────┘                                         ║
║                                                                    ║
║   ┌──────────────────────┐                                         ║
║   │  LENS (TV indicator) │ ──► _process_signal / _scalper_logic    ║
║   │  signal stream       │     (LENS-driven, asks AURUM)           ║
║   └──────────────────────┘                                         ║
║                                                                    ║
║   ┌──────────────────────┐                                         ║
║   │  Auto-scalper 60s    │ ──► _auto_scalper_tick (asks AURUM)     ║
║   │  internal loop       │                                         ║
║   └──────────────────────┘                                         ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
```

## Known failure surfaces (as of 2026-05-15)

| # | Surface | Evidence | Mitigation |
|---|---|---|---|
| **F1 — AURUM LLM acts on conversational phrasing** | AURUM is an LLM agent following the SKILL.md playbook, which instructs "act, you must not refuse" on operator-directed action language (SKILL.md §5). Confirmation was described as OPTIONAL prose (line 289), not enforced. Aegis only validates `OPEN_GROUP`; `CLOSE_ALL` / `CLOSE_GROUP` / `MODIFY_*` / `CANCEL_PENDING` flowed through unchecked. | **G5008** (2026-05-15): operator asked AURUM about the trade, the message contained "close all" conversationally, AURUM emitted `CLOSE_ALL`, EA closed at −$955.44. Scribe `close_reason` = `AURUM_CLOSE_ALL`. | **S1 SHIPPED 2026-05-15** — (a) SKILL.md §5 confirmation rules for destructive commands. (b) `bridge.py` `_check_aurum_command` holds destructive cmds in `_pending_aurum_confirmations` (proposal_id, 30s TTL); Herald posts the prompt; `aurum.py` `_handle_telegram_natural_language_command` intercepts the operator's literal `CONFIRM <id>` reply before the LLM. |
| **F2 — BRIDGE B2 (`PROFIT_RATCHET_TP`) silent broker reject** | Bridge emits a TP-tighten that lands inside the broker's min-stops distance from market. MT5 returns `[invalid stops]`, BridgeQueue retries identical params, broker rejects again. Tracker logs the close with the original (untightened) TP value, hiding the failure. | **G5001** (2026-05-15): leg2 ticket 1309868809 — three MODIFY_TP attempts at 15:01:06 / 15:01:15 / 15:03:03 all rejected with `[invalid stops]` (proposed TP 4543.73 was ~0.27 pts from market vs broker min). EA's `tp1_close_pct=100` is what actually banked the +$65.12, not B2. | **E4** — adaptive buffer on `[invalid stops]` rejection in `_compute_ratchet_tp`. <1h. |
| **F3 — Bridge B1/B2 dual ratchet authority** | Architecture states "FORGE EA is master ratchet authority for ALL trades", but BRIDGE's B1 (`PROFIT_RATCHET` SL) and B2 (`PROFIT_RATCHET_TP`) run an autonomous Aegis-bypassed modify loop on every tick. Two authorities can race on the same ticket and the silent-rejection mode (F2) hides which one actually took effect. | Same G5001 trace + general design review. | **Design decision pending** — strip B1/B2 (recommended) OR formally co-own with the EA. If stripping, port any unique behavior into EA L0–L9 first. |
| **F4 — Aegis-only-on-OPEN_GROUP asymmetry** | The validation engine guards new entries but every other state-changing command (close, modify, cancel) bypasses it. Same gap F1 exploits. | G5008 + 40-day event log (76 `AURUM_COMMAND_RX OPEN_GROUP`, 0 `AURUM_COMMAND_RX CLOSE_*` validated). | Subsumed by S1; longer-term, extend Aegis to gate destructive commands too. |
