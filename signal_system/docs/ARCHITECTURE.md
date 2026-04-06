# SIGNAL SYSTEM — Architecture & Data Flow

> v1.3.1 · 11 components · 6 operating modes · XAUUSD scalping

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SIGNAL INTAKE + PROTECTION                          │
│                                                                             │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐                           │
│  │ LISTENER │     │   LENS   │     │ SENTINEL │                           │
│  │ (Telegram│     │(Trading  │     │ (News    │                           │
│  │  + Claude│     │  View    │     │  Guard)  │                           │
│  │  Parser) │     │  MCP)    │     │          │                           │
│  └────┬─────┘     └────┬─────┘     └────┬─────┘                           │
│       │                │                │                                   │
│       │ parsed_        │ lens_          │ sentinel_                         │
│       │ signal.json    │ snapshot.json  │ status.json                      │
└───────┼────────────────┼────────────────┼───────────────────────────────────┘
        │                │                │
        ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATION                                     │
│                                                                             │
│                      ┌──────────────────┐                                  │
│                      │     BRIDGE       │                                  │
│                      │                  │                                  │
│                      │  • Mode state    │◄──── aurum_cmd.json ◄── AURUM   │
│                      │    machine       │◄──── aurum_cmd.json ◄── ATHENA  │
│                      │  • Signal        │                                  │
│                      │    dispatch      │     ┌──────────────┐            │
│                      │  • Position      │     │   AEGIS      │            │
│                      │    tracker       │◄───►│ (Risk gate)  │            │
│                      │  • Closure       │     └──────────────┘            │
│                      │    detection     │                                  │
│                      │  • Session       │     ┌──────────────┐            │
│                      │    management    │◄───►│ RECONCILER   │            │
│                      │                  │     │ (hourly)     │            │
│                      └───────┬──────────┘     └──────────────┘            │
│                              │                                             │
│                    command.json + config.json                               │
└──────────────────────────────┼─────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            EXECUTION                                        │
│                                                                             │
│                      ┌──────────────────┐                                  │
│                      │  FORGE (MT5 EA)  │                                  │
│                      │                  │                                  │
│                      │  • Opens trades  │                                  │
│                      │  • TP split      │                                  │
│                      │    (70/30)       │                                  │
│                      │  • SL/TP/BE      │                                  │
│                      │    management    │                                  │
│                      │  • Exports       │                                  │
│                      │    market data   │                                  │
│                      └───────┬──────────┘                                  │
│                              │                                             │
│                     market_data.json (every 3s)                            │
│                     • price, account, indicators                           │
│                     • open_positions[], pending_orders[]                   │
└──────────────────────────────┼─────────────────────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐
│     BRIDGE       │  │   ATHENA     │  │     AURUM        │
│  (reads back)    │  │  (API + UI)  │  │  (AI Agent)      │
└──────────────────┘  └──────────────┘  └──────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                      DATA + NOTIFICATIONS + AI                              │
│                                                                             │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐         │
│  │  SCRIBE  │     │  HERALD  │     │  AURUM   │     │  ATHENA  │         │
│  │ (SQLite) │     │(Telegram │     │ (Claude  │     │ (Flask + │         │
│  │          │     │  Alerts) │     │  Agent)  │     │  React)  │         │
│  │ 9 tables │     │          │     │          │     │          │         │
│  └──────────┘     └──────────┘     └──────────┘     └──────────┘         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Trade Lifecycle (Signal → Execution → Closure)

```
                    SIGNAL ENTRY
                    ============

  Telegram Channel ──► LISTENER ──► Claude Haiku parse
        │                                  │
        │                          parsed_signal.json
        │                                  │
        ▼                                  ▼
  AURUM (manual) ──► aurum_cmd.json ──► BRIDGE
                                          │
                                    ┌─────┴──────┐
                                    │   AEGIS     │
                                    │             │
                                    │ • H1 trend  │
                                    │ • R:R ≥ 1.2 │
                                    │ • DD check  │
                                    │ • Lot size  │
                                    └─────┬──────┘
                                          │
                                  APPROVED │ REJECTED
                                     │         │
                                     ▼         ▼
                              command.json   SCRIBE log
                                     │       + HERALD
                                     ▼
                                   FORGE
                                     │
                              Places N trades
                              (70% TP1, 30% TP2)
                                     │
                                     ▼

                    POSITION TRACKING
                    =================

  FORGE ──(3s)──► market_data.json ──► BRIDGE tracker
                                          │
                  ┌───────────────────────┤
                  │                       │
           New position?           SL/TP modified?
                  │                       │
                  ▼                       ▼
           SCRIBE log              SCRIBE log
           trade_positions         POSITION_MODIFIED
           (ticket, entry,         (old→new SL/TP)
            SL, TP, lots)


                    CLOSURE DETECTION
                    =================

  BRIDGE tracker: compare known_positions vs market_data each tick

  Position DISAPPEARED from market_data.json?
        │
        ▼
  ┌─────────────────────────────────────────┐
  │  _infer_close_reason()                  │
  │                                         │
  │  close_price ≈ SL ($0.50 tol)  → SL_HIT│
  │  close_price ≈ TP  ──┐                 │
  │                       ├→ match TP1/2/3  │
  │                       │  from group     │
  │                       │  record         │
  │  otherwise           → MANUAL_CLOSE    │
  └──────────┬──────────────────────────────┘
             │
     ┌───────┼───────┬──────────────┐
     ▼       ▼       ▼              ▼
  SCRIBE   SCRIBE   HERALD      Dashboard
  trade_   trade_   • tp_hit()  Closures
  positions closures • position_ tab
  (CLOSED)  (full    closed()
            context)

  When ALL positions in a group close:
        │
        ▼
  SCRIBE: trade_groups → status=CLOSED, total_pnl, pips
  HERALD: "✅ GROUP CLOSED — G19 BUY +$12.50"
```

---

## File Bus (JSON IPC)

```
                        BRIDGE (Python)
                     WorkingDir: python/
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
    ┌─────┴─────┐    ┌─────┴─────┐    ┌─────┴─────┐
    │  READS    │    │  WRITES   │    │  READS +  │
    │           │    │           │    │  DELETES  │
    └───────────┘    └───────────┘    └───────────┘

    MT5/                python/config/         python/config/
    market_data.json    status.json            aurum_cmd.json
    broker_info.json    MT5/command.json       parsed_signal.json
                        MT5/config.json        management_cmd.json

    python/config/
    lens_snapshot.json
    sentinel_status.json
```

```
    FORGE (MQL5)                     ATHENA (Flask)
    inside MetaTrader 5              port 7842
         │                                │
   ┌─────┴─────┐                    ┌─────┴─────┐
   │  WRITES   │                    │  READS    │
   │           │                    │  (all)    │
   └───────────┘                    │           │
                                    │  WRITES   │
   MT5/market_data.json             │  aurum_   │
   MT5/broker_info.json             │  cmd.json │
   MT5/mode_status.json             │  mgmt_    │
                                    │  cmd.json │
   ┌─────┐                         └───────────┘
   │READS│
   └─────┘
   MT5/command.json
   MT5/config.json
```

---

## SCRIBE Database Schema (9 tables)

```
┌─────────────────────────────────────────────────────────────┐
│                    aurum_intelligence.db                     │
├─────────────────────┬───────────────────────────────────────┤
│ system_events       │ Mode changes, startup, shutdown,      │
│                     │ circuit breakers, session transitions  │
├─────────────────────┼───────────────────────────────────────┤
│ trading_sessions    │ Session windows (ASIAN/LONDON/NY)     │
│                     │ with rolled-up P&L on close           │
├─────────────────────┼───────────────────────────────────────┤
│ signals_received    │ Every Telegram signal + parse result  │
│                     │ + disposition (EXECUTED/SKIPPED)       │
├─────────────────────┼───────────────────────────────────────┤
│ trade_groups        │ N-trade groups: entry zone, SL, TP,   │
│                     │ status, total P&L, magic_number       │
├─────────────────────┼───────────────────────────────────────┤
│ trade_positions     │ Individual MT5 tickets: entry, close, │
│                     │ pnl, pips, close_reason, tp_stage     │
├─────────────────────┼───────────────────────────────────────┤
│ trade_closures      │ SL/TP hit log: close_reason inferred  │
│ (NEW v1.3.1)       │ (SL_HIT/TP1_HIT/TP2_HIT/MANUAL),    │
│                     │ full context: pnl, pips, session      │
├─────────────────────┼───────────────────────────────────────┤
│ news_events         │ SENTINEL guard activations +          │
│                     │ actual market moves                    │
├─────────────────────┼───────────────────────────────────────┤
│ aurum_conversations │ All AURUM queries + responses         │
│                     │ + token usage                          │
├─────────────────────┼───────────────────────────────────────┤
│ component_heartbeats│ Per-component liveness (upserted)     │
└─────────────────────┴───────────────────────────────────────┘

Every record carries: timestamp (UTC ISO) + mode
```

---

## Operating Modes

```
┌────────┬───────────────────────────────────────────────────────┐
│  OFF   │ Dormant. No data, no trades.                         │
├────────┼───────────────────────────────────────────────────────┤
│ WATCH  │ All components active. Records everything.           │
│        │ FORGE does NOT execute. ML data collection.          │
├────────┼───────────────────────────────────────────────────────┤
│ SIGNAL │ Executes Telegram channel signals only.              │
│        │ LISTENER → Claude parse → AEGIS → FORGE.            │
├────────┼───────────────────────────────────────────────────────┤
│SCALPER │ BRIDGE's own LENS-driven entries (ADX>20 gate).      │
│        │ No Telegram dependency.                               │
├────────┼───────────────────────────────────────────────────────┤
│ HYBRID │ SIGNAL + SCALPER both active. Max opportunity.       │
├────────┼───────────────────────────────────────────────────────┤
│ AUTO_  │ AURUM (Claude) as autonomous decision engine.        │
│SCALPER │ BRIDGE polls every 120s with multi-TF prompt.        │
└────────┴───────────────────────────────────────────────────────┘

Mode overrides:
  SENTINEL active  → effective_mode = WATCH (auto-resume)
  MT5 data stale   → CIRCUIT BREAKER → WATCH (auto-resume)
  Equity DD > 3%   → CLOSE ALL + WATCH (manual resume)
```

---

## Safety Layers

```
                    Trade Request
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
     ┌─────────┐   ┌─────────┐   ┌─────────┐
     │SENTINEL │   │ CIRCUIT │   │ EQUITY  │
     │ News    │   │ BREAKER │   │ DD      │
     │ Guard   │   │ MT5     │   │ Breaker │
     │ (30min) │   │ stale   │   │ (3%)    │
     └────┬────┘   └────┬────┘   └────┬────┘
          │              │              │
          └──────────────┼──────────────┘
                    ALL CLEAR?
                         │
                         ▼
                  ┌──────────────┐
                  │    AEGIS     │
                  │              │
                  │ • H1 trend   │ ← cascade: M5→M15→H1
                  │ • R:R ≥ 1.2  │   (SIGNAL source)
                  │ • Lot size   │
                  │ • Max groups │
                  │ • Floating   │
                  │   DD < 2%    │
                  │ • Loss       │
                  │   cooldown   │
                  └──────┬───────┘
                         │
                    APPROVED?
                    │       │
                    ▼       ▼
                  FORGE   REJECT
                  (MT5)   → SCRIBE
                          → HERALD
```

---

## API Surface (ATHENA port 7842)

```
READ
  GET  /api/live              Full system state (3s poll)
  GET  /api/health            Liveness check
  GET  /api/components        11-component health panel
  GET  /api/closures          Trade closures with SL/TP reason
  GET  /api/closure_stats     SL vs TP hit rates (aggregated)
  GET  /api/performance       Closed-trade stats
  GET  /api/pnl_curve         Cumulative P&L chart data
  GET  /api/signals           Signal history
  GET  /api/sessions          Trading session history
  GET  /api/events            System event log
  GET  /api/channels          Configured Telegram channels
  GET  /api/mode              Current mode

WRITE
  POST /api/mode              Queue mode change → BRIDGE
  POST /api/management        CLOSE_ALL, MOVE_BE, etc → FORGE
  POST /api/aurum/ask         Chat with AURUM (Claude)
  POST /api/scribe/query      Read-only SQL against SCRIBE
  POST /api/sentinel/override Bypass news guard temporarily

DOCS
  GET  /api/docs/             Swagger UI
  GET  /api/openapi.yaml      OpenAPI spec
```
