# Prompt for AI reviewer / investigator (journal DB + SCRIBE workflow)

Copy the block below into another AI session when you want a structured review of FORGE journal ↔ SCRIBE behavior, paths, and verification—not only code reads.

---

You are reviewing **`signal_system`** work around **FORGE’s SQLite journal** and **SCRIBE (`aurum_intelligence.db`)**: paths, sync behavior, docs, scripts, and tests. Prior edits may have changed code and tests without fully institutionalizing **how to prove** correctness end-to-end. Your job is to **verify or fix** gaps and document a **repeatable workflow**.

Use repo root: `/Users/olasumbo/signal_system` (or the clone path on your machine).

## 1. Canonical facts (confirm in code, then validate at runtime)

- **SCRIBE database file** must be unambiguous:
  - **Canonical path:** repo-relative `python/data/aurum_intelligence.db` (resolved from **repo root**).
  - **Env:** `SCRIBE_DB` is relative to repo root; legacy value `data/aurum_intelligence.db` should still map to the same canonical file (if that remap exists, prove it with a one-line Python check).
  - **There must not be** a second “live” DB at repo root `data/aurum_intelligence.db` as the primary store; `data/` is for things like **`signal_media_archive`**, not SCRIBE.
- **FORGE journal files:** `FORGE_journal_*.db` (live vs tester naming / paths per `bridge.py` discovery).
- **SCRIBE mirror tables:** at least `forge_signals`, `forge_journal_trades`, with **`journal_source`** ∈ {`live`, `tester`} where applicable.

Read: `python/scribe.py` (`DB_PATH`, `sync_forge_journal*`), `python/bridge.py` (journal discovery + sync cadence), `scripts/diagnose_forge_journal.py`, `docs/FORGE_JOURNAL_SQL.md`, `docs/FORGE_JOURNAL_ML_PROMPT.md`, `CHANGELOG.md` for recent journal/SCRIBE bullets.

## 2. Expectations (invariants the system should satisfy)

1. **Single writer semantics for SCRIBE path:** All components that open the operational DB should resolve to the **same** file given standard `.env` / defaults (no silent second file).
2. **Sync idempotency:** Re-running BRIDGE sync must not duplicate journal rows in SCRIBE in a way that breaks analytics (understand `synced` / keys used).
3. **Tester vs live:** Rows copied into SCRIBE must be **tagged** so ML/analytics can filter tester vs live (`journal_source`).
4. **Discovery:** BRIDGE should find journals in documented locations (including Strategy Tester / Agent paths if claimed in `CHANGELOG` / docs).
5. **Observability:** `make journal-diagnose` (or `scripts/diagnose_forge_journal.py`) should report coherent counts for discovered journals vs SCRIBE `forge_*` tables.
6. **Tests:** `pytest tests/` and `make test-api` should pass in `.venv`; if something is environment-dependent (ATHENA on `:7842`), **separate** “needs live API” vs “offline unit” checks in your conclusions.

## 3. Verification strategy you must produce (not optional)

Design and **execute** (or clearly block on what’s missing) a **short playbook**:

### A. Static checks

- Grep for stale references to `data/aurum_intelligence.db` as the **primary** SCRIBE file (repo + listed helper scripts). Flag any mismatch with `python/data/...`.
- Confirm `.env.example` `SCRIBE_DB` comment matches `scribe.py` resolution rules.

### B. Runtime smoke (no MT5 required where possible)

- Import `scribe` with controlled `SCRIBE_DB` values: default, `python/data/...`, legacy `data/aurum_intelligence.db`, and one absolute path — assert resolved paths match intent.
- Run `python scripts/diagnose_forge_journal.py` against the user’s machine **or** document exact prerequisites if journal files aren’t present (do not pretend success).

### C. Integration-ish (optional but preferred if journals exist)

- With a real `FORGE_journal_*.db` available: run BRIDGE or the smallest code path that calls `sync_forge_journal` / `sync_forge_journal_trades`, then query SCRIBE for new rows and `journal_source` distribution.
- Document **exact SQL** (or reference `docs/FORGE_JOURNAL_SQL.md`) used to confirm sync.

### D. Regression tests

- List which tests **should** break if journal sync or `SCRIBE_DB` resolution regress; if coverage is thin, **add** focused tests (tmp_path SQLite, no network).

**Deliverable from you:** a **numbered verification checklist** with **pass/fail** and **commands run**.

## 4. Process / flow the user wants

Explain the intended **operational flow** in plain language:

1. FORGE writes journal SQLite (signals / trades / tester runs as designed).
2. BRIDGE discovers journal path(s), runs periodic sync into SCRIBE.
3. SCRIBE remains the **query/analytics** surface (`SCRIBE_QUERY`, notebooks, ML prompt docs).
4. Ops uses **one** DB path mental model: `python/data/aurum_intelligence.db` + `SCRIBE_DB` override when needed.
5. Investigation order when “journal looks wrong”: diagnose script → inspect FORGE file → inspect SCRIBE `forge_*` → BRIDGE logs / discovery.

## 5. What to fix vs what to only document

- If you find **bugs**, patch minimally and re-run the checklist.
- If behavior is correct but **docs/scripts disagree**, align docs **or** add a single “source of truth” paragraph in `README` / `docs/FORGE_JOURNAL_SQL.md` (only if the user wants repo edits).
- Explicitly call out **anthropic / venv / PEP 668** issues as orthogonal to journal logic unless tests fail because of them.

## 6. Output format

Respond with:

1. **Executive summary** (what is true today vs broken/unclear).
2. **Invariant table** (expected vs actual).
3. **Verification checklist** with commands and results.
4. **Recommended next fixes** (prioritized).
5. **One-page operator runbook** — “When I suspect journal/SCRIBE drift, I run: …”

Run commands **in the real environment**, not hypothetically.
