# ⚒ SIGNAL SYSTEM v2.4.3
> XAUUSD signal-following scalper with AI intelligence layer.
> macOS + MetaTrader 5 native. 12 components. 6 operating modes.

---
## External Dependencies
- **Python 3.11+** (service runtime)
- **Node.js 18+** (TradingView MCP server runtime)
- **MetaTrader 5 (macOS native app)** (FORGE execution + account feed)
- **TradingView Desktop with CDP enabled (`localhost:9222`)** (LENS live indicator source)
- **TradingView MCP server**: `https://github.com/LewisWJackson/tradingview-mcp-jackson.git`
- **Telegram account + Bot API token** (LISTENER intake + HERALD/AURUM notifications)
- **Anthropic API key** (LISTENER parsing + AURUM intelligence layer)
- **Tesseract OCR (optional, recommended for chart image extraction quality)**

For full installation and configuration flow, see [docs/SETUP.md](docs/SETUP.md).

---

## Architecture
Core architecture and operations docs:
- **Scalper + regime phased roadmap** (execution prompts, testing, MT5 Tester, doc checklist): [docs/SCALPER_REGIME_PHASED_PLAN.md](docs/SCALPER_REGIME_PHASED_PLAN.md)
- **System architecture**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Mode architecture**: [docs/MODES_ARCHITECTURE.md](docs/MODES_ARCHITECTURE.md)
- **Scalper rules/tuning**: [docs/FORGE_TRADING_RULES.md](docs/FORGE_TRADING_RULES.md)
- **Vision validation runbook**: [docs/VISION_CLI_RUNBOOK.md](docs/VISION_CLI_RUNBOOK.md)
- **Signal replay runbook**: [docs/SIGNAL_REPLAY_RUNBOOK.md](docs/SIGNAL_REPLAY_RUNBOOK.md)
- **FORGE journal ML / missed-setup roadmap**: [docs/FORGE_JOURNAL_ML_PROMPT.md](docs/FORGE_JOURNAL_ML_PROMPT.md)
- **FORGE journal SQL (skips, SCRIBE + raw DB)**: [docs/FORGE_JOURNAL_SQL.md](docs/FORGE_JOURNAL_SQL.md)
- **Architecture diagram (PNG)**: [docs/assets/trading-system-architecture.png](docs/assets/trading-system-architecture.png)
- **Architecture diagram (interactive HTML)**: [docs/assets/trading-system-architecture.drawio.html](docs/assets/trading-system-architecture.drawio.html)
- **Architecture diagram source (Draw.io)**: [docs/assets/trading-system-architecture.drawio](docs/assets/trading-system-architecture.drawio)
- **Architecture diagram source (XML)**: [docs/assets/trading-system-architecture.xml](docs/assets/trading-system-architecture.xml)

Recent behavior notes:
- BRIDGE LENS scalper (`SCALPER` / `HYBRID`) routes candidates through **AEGIS** + regime metadata on `trade_groups` before `OPEN_GROUP` (see `CHANGELOG.md`, `docs/ARCHITECTURE.md`).
- Signal-room media uploads are archived and replayable via `scripts/replay_signal_uploads.py`, with channel-aware summary notifications to Telegram.
- FORGE market export includes all account positions using `forge_managed=true/false`.
- BRIDGE logs unmanaged/manual MT5 positions into SCRIBE as `MANUAL_MT5` lifecycle records.
- **FORGE v2.4.3** — throttles **`no_setup`** / **`rr_too_low`** journal rows to **one per M5 bar** (avoids tick spam). Reliable **`JournalImportTrades`** (`DatabaseExecute`), **`TRADES.synced`** for SCRIBE. **`SKIP`/`execution_failed`** when no orders open. SCRIBE **`forge_journal_trades`** mirrors deal history; BRIDGE discovers tester agents under **`MetaTrader 5/**`** recursively. Builds on v2.4.2–v2.4.1: journals, `journal_source`, VWAP/Fib/RSI div/PSAR, SL rules, 1–30 legs.
- FORGE journal + analytics roadmap: **`docs/FORGE_JOURNAL_ML_PROMPT.md`** — missed-setup CLI, optional ML scorer, AUTO_SCALPER/AEGIS hooks (planned implementation).

![Trading System Architecture](docs/assets/trading-system-architecture.png)
## System Design Rationale (SCRIBE-first)
- The system was designed **SCRIBE-first** so every decision path is auditable before automation scale-up.
- Starting with persistent event/trade logs enabled a safe WATCH-first rollout, then evidence-based progression into live execution modes.
- BRIDGE, AEGIS, FORGE, LISTENER, and AURUM are layered as a closed loop: ingest → validate → execute → reconcile → learn.
- New features (including unmanaged/manual MT5 trade tracking and session/open alert telemetry) are added as schema-backed events to preserve traceability over time.
- Operational query workflows are documented in [docs/SCRIBE_QUERY_EXAMPLES.md](docs/SCRIBE_QUERY_EXAMPLES.md).

## Components
| # | Name | File | Role |
|---|---|---|---|
| 1 | SCRIBE | `python/scribe.py` | SQLite intelligence logger (15 tables, ML/ops-ready) |
| 2 | FORGE | `ea/FORGE.mq5` | MT5 EA — 5 modes, trade groups, backtest |
| 3 | HERALD | `python/herald.py` | Telegram notifications |
| 4 | SENTINEL | `python/sentinel.py` | News guard, economic calendar |
| 5 | LENS | `python/lens.py` | TradingView MCP ([LewisWJackson/tradingview-mcp-jackson](https://github.com/LewisWJackson/tradingview-mcp-jackson.git)) |
| 6 | AEGIS | `python/aegis.py` | Risk manager, N-trade lot sizer |
| 7 | LISTENER | `python/listener.py` | Telegram signal reader + Claude parser |
| 8 | AURUM | `python/aurum.py` | Claude AI agent (`SOUL.md` + `SKILL.md`) |
| 9 | BRIDGE | `python/bridge.py` | Orchestrator + mode state machine |
| 10 | ATHENA | `python/athena_api.py` | Flask API + React dashboard |
| 11 | VISION | `python/vision.py` | Shared chart/image extraction module for LISTENER + AURUM |
| 12 | RECONCILER | `python/reconciler.py` | Hourly MT5↔SCRIBE consistency audit |

## Operating Modes
- **OFF** — Completely dormant
- **WATCH** — Records data only, no trades (ML collection)
- **SIGNAL** — Executes Telegram signals only
- **SCALPER** — BRIDGE scalper + FORGE native scalper
- **HYBRID** — SIGNAL + SCALPER combined
- **AUTO_SCALPER** — AURUM-driven autonomous scalping loop

## Quick Start
```bash
pip3 install -r requirements.txt
cp .env.example .env
# Fill in .env with your credentials
# One-time MT5 file-bus link:
make setup-mt5-link
# Run once after cloning. Re-running is safe (uses ln -sfn) but not needed unless your MT5 path changes.
# See docs/SETUP.md for full setup guide
python3 python/bridge.py --mode WATCH
```

## Testing (clean machine)

Avoid PEP 668 “externally managed” Python: use a **repo `.venv`**, not system `pip`.

```bash
make venv
# Optional: Playwright + npm UI harness (make test / test-ui)
make setup-tests

make test-api                           # scripts/test_api.py (needs services per that script)
.venv/bin/python -m pytest tests/ -q    # full unit/API pytest tree (jsonschema, etc.)
```

`make venv` installs `requirements.txt` plus `tests/requirements-test.txt` (pytest stack including `jsonschema`).

## Versioning

Two version files at the repo root — no hardcoded versions in source for these:

| File | Tracks | Read by |
|---|---|---|
| `VERSION` | FORGE EA (MQL5) | `make forge-compile` → stamps `ea/FORGE.mq5` and **`config/scalper_config.json`** `version` (via `make scalper-env-sync`) |
| `SYSTEM_VERSION` | Signal System (Python) | `bridge.py`, `athena_api.py` at startup |

### Native scalper JSON (`defaults` → generated)

- **Edit:** `config/scalper_config.defaults.json` and/or `.env` `FORGE_*` keys (see `scripts/sync_scalper_config_from_env.py`).
- **Regenerate:** `make scalper-env-sync` or `make forge-compile`.
- **Details:** [docs/SCALPER_CONFIG_PIPELINE.md](docs/SCALPER_CONFIG_PIPELINE.md).

```bash
# Bump FORGE EA version
echo "2.5.0" > VERSION
make forge-compile

# Bump Python system version
echo "1.7.2" > SYSTEM_VERSION
make reload           # services pick it up on restart
```

## FORGE Refresh Verify
`make forge-refresh-verify` runs the full MT5 refresh check: `forge-compile` copies `ea/FORGE.mq5` into the Wine MT5 Experts folder and compiles it to `FORGE.ex5`, then opens MetaTrader 5 and polls `MT5/market_data.json` for up to 180 seconds until `forge_version` matches the source.

If the copy step fails with `Operation not permitted`, restore write permission on the Wine MT5 Experts folder once:
```bash
chmod -R u+w "/Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Experts"
```
This one-time fix is needed when the Wine MT5 Experts folder loses write permission, for example after a MetaTrader update or macOS privacy reset.

## AURUM — Talk to your system
From Telegram:
> "What's my P&L today?"
> "Is the entry for G047 still valid?"
> "Switch to WATCH mode"
> "Show me LENS analysis"

## Data Schema (SCRIBE)
SCRIBE uses 14 SQLite tables, and every row is tagged with `mode` when applicable:
- `system_events` — mode switches, startups, shutdowns
- `trading_sessions` — session windows and rolled-up performance
- `market_snapshots` — OHLCV + indicators (LENS + MT5)
- `signals_received` — every Telegram signal + parse result
- `trade_groups` — parent record for N-trade groups
- `trade_positions` — individual MT5 trade tickets
- `news_events` — SENTINEL guard events + market moves
- `aurum_conversations` — all AURUM queries + responses
- `trade_closures` — SL/TP hit log with inferred close reason
- `component_heartbeats` — per-component liveness
- `vision_extractions` — LISTENER/AURUM image extraction lineage + confidence
- `regime_snapshots` — HMM regime state snapshots (label, confidence, policy)
- `forge_signals` — FORGE native signal journal (evaluations — taken + skipped) + `forge_journal_trades` — MT5 deal mirror from FORGE journal `TRADES`, both with **`journal_source`**

## License
For personal use only. Not financial advice. Always test on demo first.
