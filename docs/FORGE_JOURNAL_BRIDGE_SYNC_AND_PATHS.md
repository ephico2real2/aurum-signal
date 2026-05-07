# FORGE journals — `BRIDGE_SYNC_TESTER_JOURNAL`, paths, and common confusion

This note clarifies what **`BRIDGE_SYNC_TESTER_JOURNAL`** does and how it differs from **where** tester vs live journal SQLite files live. Use it when diagnosing “DB not found” vs “nothing in AURUM.”

---

## What `BRIDGE_SYNC_TESTER_JOURNAL` actually does

It only controls **whether BRIDGE copies rows from the tester journal SQLite file into `aurum_intelligence.db`** (`forge_signals` / `forge_journal_trades` with `journal_source='tester'`).

| Value | Behaviour |
|--------|-----------|
| **`0` (default)** | BRIDGE **still discovers** tester journal paths (when journal sync runs), but **skips** `sync_forge_journal` / `sync_forge_journal_trades` for `*_tester.db` files. It does **not** create or delete those files. It does **not** mean “the tester DB doesn’t exist.” |
| **`1`** | BRIDGE syncs tester journals into AURUM as before. |

So **“`BRIDGE_SYNC_TESTER_JOURNAL` is 0” is not a valid reason to conclude “the tester DB was not found.”** Those are independent:

- **Sync flag** = whether to mirror tester rows into the SCRIBE / AURUM DB.
- **DB missing** = path discovery failed, no backtest with journal enabled, wrong agent folder, etc.

---

## Two different DBs, two different places

| Kind | Role | Typical on-disk location (Wine / macOS examples) |
|------|------|--------------------------------------------------|
| **Tester** | Written during **Strategy Tester** when FORGE journal is enabled | Under the **tester agent** tree, e.g. `…/MetaTrader 5/Tester/Agent-127.0.0.1-PORT/MQL5/Files/FORGE_journal_XAUUSD_tester.db` — **port / agent folder varies** per run. |
| **Live** | Written when **FORGE runs on a live or demo chart** with journal enabled | Often **Terminal Common Files**, e.g. `…/MetaQuotes/Terminal/Common/Files/FORGE_journal_XAUUSD.db` (or terminal-local `MQL5/Files` depending on setup). |

**Tester and live journals are different files in different locations.**

If you **have not run live** with the journal on, **no live journal file** (or only an old/empty one) is **expected** — that is not caused by `BRIDGE_SYNC_TESTER_JOURNAL`.

---

## What is wrong with conflating these ideas

A misleading chain of reasoning looks like:

1. “Tester journal DB not present”
2. “Because `BRIDGE_SYNC_TESTER_JOURNAL` is 0 by default”
3. “So live per-run signal and P&L queries are unavailable until…”

Problems:

- **“Tester journal DB not present”** should be justified by: path search did not find `*_tester.db`, or **no backtest** was run with journal enabled, or the **wrong agent directory** was inspected — **not** by the sync flag being `0`.
- **“Live per-run signal and P&L”** in **AURUM** usually means **`forge_*` tables** with **`journal_source='live'`**. That requires **live** FORGE journal activity and BRIDGE syncing the **live** journal file. Tester sync settings do not replace a missing **live** journal.
- Mixing **tester file missing** with **live** analytics blurs two different pipelines: **on-disk tester DB for ML** vs **SCRIBE mirror for live ops**.

---

## Operational summary

- **Tester / ML / per-backtest analysis:** Prefer querying **`FORGE_journal_*_tester.db`** **directly** (filter by `run_id` when present), especially while **`BRIDGE_SYNC_TESTER_JOURNAL=0`**. See **`docs/FORGE_TESTER_JOURNAL_QUERIES.md`** and **`make journal-diagnose`**.
- **Live analytics / `forge_signals` in `aurum_intelligence.db`:** Requires **live** chart + journal enabled + BRIDGE discovering the **live** journal path and syncing it (tester sync env var does not gate live sync).

## Related docs

- **`docs/FORGE_BRIDGE.md`** — §11 live vs tester journal sync.
- **`docs/DATA_CONTRACT.md`** — `forge_signals` / `forge_journal_trades`, `journal_source`, `run_id`.
- **`docs/prompts/FORGE_JOURNAL_ML_PROMPT.md`** — ML stack: tester DB vs AURUM.
