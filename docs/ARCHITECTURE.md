# SIGNAL SYSTEM — Architecture & Data Flow

> Current runtime architecture · 11 components + shared VISION module · 6 operating modes · XAUUSD scalping

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
│       │                │                │                                   │
│       │ media + text   │                │                                   │
│       └──────► VISION module (shared by LISTENER + AURUM)                  │
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
│                     • open_positions[] (all account positions + forge_managed) │
│                     • pending_orders[] (symbol pendings + forge_managed)       │
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

## Trade Lifecycle (Signal → VISION/Parse → Execution → Closure)

```
                    SIGNAL ENTRY
                    ============

  Telegram Channel ──► LISTENER ──► Claude Haiku parse
        │                   │              │
        │             (if media)           │
        │                   ▼              │
        │                VISION ───────────┘
        │                   │
        │      room-priority gate (SIGNAL_TRADE_ROOMS)
        │      non-priority -> WATCH_ONLY (logged), no dispatch
        │
        │      media archive (LISTENER_SIGNAL_MEDIA_ARCHIVE_*)
        │      -> python/data/signal_media_archive/<channel>/*.img + *.img.json
        │
        │      Telegram summary to operator bot chat
        │      -> SIGNAL_CHART_SUMMARY_SENT / FAILED
        │
        │      SCRIBE.vision_extractions + signals_received linkage
        │                                  │
        │                          parsed_signal.json
        │                                  │
        ▼                                  ▼
  AURUM (manual/chat) ──► aurum_cmd.json ──► BRIDGE
        │
        └─ direct image upload ─► VISION ─► SCRIBE.vision_extractions
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
                  │
                  ▼
      unmanaged/manual position?
                  │
                  ▼
      SCRIBE synthetic lifecycle
      source=MANUAL_MT5
      + UNMANAGED_POSITION_OPEN/CLOSED


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

## SCRIBE Database Schema (11 tables)

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
│ signals_received    │ Every Telegram signal + parse result   │
│                     │ + source_type + vision_extraction_id   │
│                     │ + disposition (EXECUTED/SKIPPED)       │
├─────────────────────┼───────────────────────────────────────┤
│ market_snapshots    │ LENS + MT5 indicator snapshots        │
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
├─────────────────────┼───────────────────────────────────────┤
│ vision_extractions  │ Every VISION trigger result            │
│                     │ (caller, confidence, structured_data,  │
│                     │ downstream_result, linked_signal_id)   │
└─────────────────────┴───────────────────────────────────────┘

Every record carries: timestamp (UTC ISO) + mode where applicable.

---

## VISION Invocation Paths & Runtime Behavior

```
1) LISTENER channel message
   NewMessage/Edit -> has_media?
      -> Vision.extract(image, caption, context_hint="SIGNAL", caller="LISTENER")
      -> SCRIBE.log_vision_extraction(caller=LISTENER, source_channel=<channel>)
      -> merge structured_data into parsed signal (when text is incomplete/ignore)
      -> signals_received.vision_extraction_id links signal row to vision_extractions.id

2) AURUM direct bot image
   Telegram bot image -> Aurum._reply_with_optional_image(...)
      -> Vision.extract(image, context_hint=<chat intent>, caller="HERALD")
      -> SCRIBE.log_vision_extraction(caller=HERALD, source_channel="direct")
      -> high confidence: context injected into AURUM answer
      -> low confidence: user gets clarification / resend request
```

Failure handling and resilience:
- VISION is a shared module, not a separate service process.
- Validation failures, unreadable images, or model errors return a safe LOW-confidence result instead of crashing caller flows.
- LISTENER can hold LOW-confidence image signals when `VISION_LOW_CONFIDENCE_HOLD=true`.
- Runtime service reliability depends on launchd using the project `.venv` interpreter so PIL/OpenCV/tesseract bindings are available.
```

---

## Operating Modes
Dedicated mode architecture (ownership, gating, and per-mode workflows):
- **[docs/MODES_ARCHITECTURE.md](MODES_ARCHITECTURE.md)**
Scalper threshold meaning, fast/strict profile values, and rollback commands:
- **[docs/FORGE_TRADING_RULES.md](FORGE_TRADING_RULES.md)**

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
│SCALPER │ BRIDGE scalper + FORGE native scalper are active.     │
│        │ BRIDGE scalper path is direct; FORGE native is EA-side│
├────────┼───────────────────────────────────────────────────────┤
│ HYBRID │ SIGNAL + SCALPER active (includes FORGE native mode).│
├────────┼───────────────────────────────────────────────────────┤
│ AUTO_  │ AURUM (Claude) as autonomous decision engine.        │
│SCALPER │ BRIDGE polls every 120s with multi-TF prompt.        │
└────────┴───────────────────────────────────────────────────────┘

Mode overrides:
  SENTINEL active  → effective_mode = WATCH (auto-resume)
  MT5 data stale   → CIRCUIT BREAKER → WATCH (auto-resume)
  Equity DD > 3%   → CLOSE ALL + WATCH (manual resume)
  BRIDGE_PIN_MODE  → blocks mode changes away from pinned mode (logs MODE_CHANGE_BLOCKED)
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
  POST /api/mode              Queue mode change request → BRIDGE (BRIDGE is source-of-truth; pin may block)
  POST /api/management        CLOSE_ALL, MOVE_BE, etc → FORGE
  POST /api/aurum/ask         Chat with AURUM (Claude)
  POST /api/scribe/query      Read-only SQL against SCRIBE
  POST /api/sentinel/override Bypass news guard temporarily

DOCS
  GET  /api/docs/             Swagger UI
  GET  /api/openapi.yaml      OpenAPI spec
```

Performance tab metric contract:
- Window: **Rolling 7 days (UTC)**
- Source: SCRIBE `trade_positions` with `status='CLOSED'`
- Metrics: Win Rate, Avg Pips, Total P&L, Trades, Wins, Losses

`GET /api/mode` includes:
- `mode`: current requested mode from BRIDGE status
- `effective_mode`: runtime mode after sentinel/circuit-breaker overrides
- `requested_mode`: last queued dashboard mode request (if any)
- `mode_pin`: configured `BRIDGE_PIN_MODE` (if set)
