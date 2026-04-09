# ⚒ SIGNAL SYSTEM v1.0

> XAUUSD signal-following scalper with AI intelligence layer.
> macOS + MetaTrader 5 native. 10 components. 5 operating modes.

---

## Architecture

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for full ASCII diagrams: system overview, trade lifecycle, closure detection flow, file bus, safety layers, and API surface.

```
LISTENER · LENS · SENTINEL          ← Signal Intake + Protection
         BRIDGE                     ← Orchestration + Closure Detection
   AEGIS · FORGE · SCRIBE           ← Risk + Execution + Data
 ATHENA · HERALD · AURUM            ← Interface + Notifications + AI
         RECONCILER                 ← Hourly Position Audit
```

## Components

| # | Name | File | Role |
|---|------|------|------|
| 1 | SCRIBE | python/scribe.py | SQLite data logger (7 tables, ML-ready) |
| 2 | FORGE | ea/FORGE.mq5 | MT5 EA — 5 modes, trade groups, backtest |
| 3 | HERALD | python/herald.py | Telegram notifications |
| 4 | SENTINEL | python/sentinel.py | News guard, economic calendar |
| 5 | LENS | python/lens.py | TradingView MCP (LewisWJackson) |
| 6 | AEGIS | python/aegis.py | Risk manager, N-trade lot sizer |
| 7 | LISTENER | python/listener.py | Telegram signal reader + Claude parser |
| 8 | AURUM | python/aurum.py | Claude AI agent (SOUL.md + SKILL.md) |
| 9 | BRIDGE | python/bridge.py | Orchestrator + mode state machine |
| 10 | ATHENA | python/athena_api.py | Flask API + React dashboard |

## Operating Modes

- **OFF** — Completely dormant
- **WATCH** — Records data only, no trades (ML collection)
- **SIGNAL** — Executes Telegram signals only
- **SCALPER** — EA's own LENS-driven entries
- **HYBRID** — Both SIGNAL + SCALPER active

## Quick Start

```bash
pip3 install -r requirements.txt
cp .env.example .env
# Fill in .env with your credentials
# See docs/SETUP.md for full setup guide
python3 python/bridge.py --mode WATCH
```

## AURUM — Talk to your system

From Telegram:
> "What's my P&L today?"
> "Is the entry for G047 still valid?"
> "Switch to WATCH mode"
> "Show me LENS analysis"

## Data Schema (SCRIBE)

9 SQLite tables, every row tagged with `mode`:
- `system_events` — mode switches, startups, shutdowns
- `market_snapshots` — OHLCV + indicators (LENS + MT5)
- `signals_received` — every Telegram signal + parse result
- `trade_groups` — parent record for N-trade groups
- `trade_positions` — individual MT5 trade tickets
- `news_events` — SENTINEL guard events + market moves
- `aurum_conversations` — all AURUM queries + responses
- `trade_closures` — SL/TP hit log with inferred close reason
- `component_heartbeats` — per-component liveness

## License

For personal use only. Not financial advice. Always test on demo first.
