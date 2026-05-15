# FORGE Parking Lot — deferred ideas

Tracked-but-not-scheduled work. When an item gets scope-opened it moves to a canonical doc (FMSR §15, ICT Map §8, etc.) or to a versioned ship.

## §1 Backlog

### §1.1 Athena dashboard — live/backtest auto-switch flag (parked 2026-05-15)

**Operator observation**: the ACCOUNT panel (left column) reads live from `market_data.json` + scribe `aurum_intelligence.db` and works fine. But the right-column backtest-oriented panels (Backtest Runs list, run detail summary, gate breakdown, P&L curve when bound to `/api/backtest/run/<id>`) read `aurum_tester.db` unconditionally — so when no MT5 tester is running, they show stale data from the last completed backtest.

**Desired behaviour**: a server-detected mode + clickable header pill that switches the dual-source panels between LIVE (last 24h from scribe) and BACKTEST (active or most-recent tester run) automatically when the tester DB is stale, with operator override.

**Proposed approach**:
1. New `/api/data_mode` endpoint returning `{mode, backtest_active, last_activity_age_sec, stale_threshold_sec=300, active_aurum_run_id, override}`. Detection: `backtest_active = MAX(forge_signals.time in aurum_tester.db) within last ATHENA_BACKTEST_STALE_SEC`.
2. Dashboard header pill showing current mode + clickable override (persists in localStorage).
3. Panel-level fork — ambiguous-source widgets read mode and switch fetch URL.
4. Backtest page stays canonical (always backtest data — its purpose is run analysis).

**Open questions when scope opens**:
- Which exact panels need the switch (Backtest Runs list, run detail summary, gate breakdown, P&L curve, signals table)?
- Stale threshold default (300s recommended; tunable via env)
- Override persistence: localStorage vs server-side env var vs both?

**Why parked**: ICT modular build-out (Phase A→E + FMSR Mode A→C) is the active priority. UI mode-switch is operator quality-of-life, not trade-flow blocking.

---

## §2 Promotion rules

When an item leaves the parking lot:
1. Operator opens scope explicitly
2. Item moves to the canonical doc covering its area (e.g. UI infra → `docs/ATHENA_ARCHITECTURE.md` if it exists, or a new dedicated doc)
3. A version ship is identified (e.g. v2.7.130-UI)
4. The parking-lot entry stays here as a historical record with a forward link to the canonical doc

## §3 Changelog

- **2026-05-15** — created. First entry: Athena live/backtest auto-switch flag.
