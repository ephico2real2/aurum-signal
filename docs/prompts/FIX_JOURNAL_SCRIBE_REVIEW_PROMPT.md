# FIX: FORGE Journal ↔ SCRIBE — Step-by-Step Fix & Phased Testing Prompt

> **Reference:** This document follows up on `docs/JOURNAL_SCRIBE_REVIEW_PROMPT.md`.
> All findings below were produced by a prior Codex investigation run against
> `/Users/olasumbo/signal_system` on 2026-05-06.
> Implement fixes in phase order. Do not skip ahead. Re-run the phase checklist
> before moving to the next phase.

---

### Revision stamp — Cursor Agent (**Composer**), 2026-05-06

The following adjustments were **recommended after a code review** of this prompt against the live repo. **Codex (or any implementer):** treat these as authoritative clarifications; do not assume the original investigation text is still exact.

| Topic | Adjustment |
|--------|------------|
| **Phase 2 / tests** | `tests/services/test_scribe_forge_journal.py` **already exists**. Coverage is under **different test names** than the four listed originally; see Phase 2 for the mapping. Add **extra** tests only if you need the four isolated scenarios spelled out. |
| **Phase 3 / diagnose** | As of review, `main()` **already exits 0** when no journals are found (JSON with `journals_found: 0`). Phase 3 is **UX**: add an explicit human-readable note on empty discovery — not necessarily “fix non-zero exit.” |
| **`sync_forge_journal_trades` return** | The method returns **`len(synced_ids)`** (rows **processed** from the journal batch), not “rows inserted.” Assertions should use **table counts** in SCRIBE where that distinction matters. |
| **Final gate** | There is **no** `tests/` integration directory in this repo; `--ignore=tests/integration` is a no-op. Split **offline** `pytest tests/` from **`make test-api`** (requires ATHENA on `:7842`). |
| **Python invocation** | Prefer repo **`.venv/bin/python`** when a venv exists; the **Makefile** `PYTHON` variable already prefers `.venv`. `python3` is still the right default for bare shells. |

---

## Context recap (from the review)

| Finding | Severity | Status going in |
|---|---|---|
| `forge_signals` duplicate re-sync possible if `synced` flag reset | High | Patched in prior run — **verify patch still present** |
| No focused offline tests for journal sync / path resolution | Medium | **`test_scribe_forge_journal.py` exists** — **Composer:** verify & optionally expand (Phase 2) |
| `python` not on PATH (only `python3`) | Low | Doc gap only |
| Tester journal backlog: 2,197,149 unsynced `SIGNALS` rows | Medium | Decision needed |
| `pyflakes` / `ruff` not installed in venv | Low | Tooling gap |
| Diagnose script when no journals found | Low | **Composer review:** already **exit 0** + JSON; optional **UX** = clearer stdout message (see Phase 3) |

Use repo root: `/Users/olasumbo/signal_system`.
Use **`python3`** on a bare shell, or **`.venv/bin/python`** / **`make`** targets (which set `PYTHON` to `.venv` when present).

---

## Phase 1 — Verify the existing patch is correct and complete

### Goal
Confirm the `forge_signals` idempotency guard committed in the prior run is sound,
covers all call sites, and has no off-by-one or missing-column bugs.

### Steps

1. **Read the patch** in `python/scribe.py` around line 710.
   - Confirm the guard key is `(forge_id, time, symbol, journal_source)`.
   - Confirm the guard runs **before** `INSERT`, not after.
   - Confirm already-mirrored rows are marked `synced=1` in the source journal.

2. **Read `sync_forge_journal_trades`** (nearby in the same file).
   - Confirm `UNIQUE(deal_ticket, journal_source)` + `INSERT OR IGNORE` is still
     intact and has not been accidentally removed.

3. **Static compile check** (must pass before any further work):
   ```
   python3 -m py_compile python/scribe.py python/bridge.py \
       scripts/diagnose_forge_journal.py
   echo "compile OK"
   ```

4. **Run existing focused tests**:
   ```
   cd /Users/olasumbo/signal_system
   python3 -m pytest tests/services/test_scribe_forge_journal.py -v
   ```
   Expected: all tests pass. If any fail, fix before continuing.

### Phase 1 checklist

| Check | Command | Pass/Fail |
|---|---|---|
| Guard key correct | Read scribe.py ~line 710 | |
| Guard position correct (before INSERT) | Read scribe.py | |
| Trades UNIQUE constraint intact | Read scribe.py | |
| Compile clean | `python3 -m py_compile ...` | |
| Focused tests pass | `pytest tests/services/test_scribe_forge_journal.py -v` | |

---

## Phase 2 — Expand offline regression tests

### Goal
Ensure the test suite will catch any future regression in:
- `SCRIBE_DB` path resolution (unset / default / legacy / absolute)
- `journal_source` tagging (`live` vs `tester`)
- Signal idempotency (duplicate guard)
- Trade idempotency (`INSERT OR IGNORE`)

### Steps

1. Open `tests/services/test_scribe_forge_journal.py`.

2. **Composer review — current file already covers the scenarios below** (names differ from an earlier spec):
   - **`test_scribe_db_path_resolution_rules`** — unset default, `python/data/...`, legacy `data/aurum_intelligence.db`, absolute path.
   - **`test_forge_journal_sync_tags_source_and_is_idempotent`** — fixture journal; sync with **`source="tester"`**; asserts `journal_source` on `forge_signals` / `forge_journal_trades`; resets source `synced=0` and re-runs sync; asserts **`forge_signals` row count stays 1** (signal idempotency); asserts trade mirror count stays 1 with **`INSERT OR IGNORE`** behavior.

3. **Optional expansion (only if you need four isolated tests):** split or add dedicated tests for:
   - explicit **`live`** vs **`tester`** tagging in separate calls,
   - trade duplicate `deal_ticket` / second insert attempt,
   — using `tmp_path` SQLite only (no network, no MT5).

4. Run the full focused suite:
   ```
   python3 -m pytest tests/services/test_scribe_forge_journal.py -v --tb=short
   ```

5. Run the broader SCRIBE suite to check for regressions:
   ```
   python3 -m pytest \
       tests/services/test_scribe_forge_journal.py \
       tests/services/test_scribe_open_context.py \
       tests/api/test_scribe_query_examples.py \
       tests/api/test_scribe_regime.py \
       -v --tb=short
   ```
   Expected: all listed tests pass (exact count may vary; confirm zero failures).

### Phase 2 checklist

| Check | Command | Pass/Fail |
|---|---|---|
| Required scenarios covered (see step 2) | Read `test_scribe_forge_journal.py` | |
| Focused suite passes | `pytest tests/services/test_scribe_forge_journal.py` | |
| Broader suite passes (no regression) | `pytest tests/services/... tests/api/...` | |

---

## Phase 3 — Diagnose script hardening

### Goal
**Composer review:** Today the script typically **exits 0** and prints JSON even when
**no journals** are found (`journals_found: 0`). Goal here is **operator UX**:
make empty discovery **obvious** (stderr or stdout banner) without changing
success semantics unless you find a real crash path (e.g. missing SCRIBE file — handle gracefully in JSON output).

### Steps

1. Read `scripts/diagnose_forge_journal.py`.

2. When **`len(journals) == 0`** (after `_journal_paths()`), ensure users see a clear note, e.g.:
   ```
   No FORGE journal files found in search paths. Is MetaTrader 5 installed
   and has it written a journal at least once?
   ```
   Emit this **before or after** the JSON (document which in `CHANGELOG` if ambiguous for tooling).

3. Confirm the script uses `python3`-safe syntax (no `python2`-only constructs).

4. Run the script on the real machine:
   ```
   python3 scripts/diagnose_forge_journal.py
   ```
   - If journals exist: confirm output shows 2 journals, canonical SCRIBE path,
     and counts consistent with the prior run (live ~38 k signals, tester large backlog).
   - If no journals: confirm clean exit with the friendly message above.

5. Run the script with `SCRIBE_DB` explicitly overridden to a tmp path to confirm
   it reports the override path correctly:
   ```
   SCRIBE_DB=/tmp/test_scribe_check.db python3 scripts/diagnose_forge_journal.py
   ```

### Phase 3 checklist

| Check | Command | Pass/Fail |
|---|---|---|
| Empty-journal friendly message present | Read diagnose script | |
| Script exits 0 with no journals | Run on a machine with no MT5 journals | |
| Real run: journals + SCRIBE summary consistent | `python3 scripts/diagnose_forge_journal.py` | |
| SCRIBE_DB override reported correctly | `SCRIBE_DB=/tmp/... python3 scripts/diagnose_forge_journal.py` | |

---

## Phase 4 — Tester backlog decision + sync validation

### Goal
Address the 2,197,149 unsynced tester `SIGNALS` rows responsibly. Do not run
a bulk sync without first validating it won't corrupt SCRIBE.

### Steps

1. **Dry-run count** — query the tester journal directly:
   ```
   sqlite3 "<path-to-tester-FORGE_journal_*.db>" \
       "SELECT COUNT(*) FROM SIGNALS WHERE synced=0;"
   ```
   Confirm count is still ~2.2 M (or document if it has changed).

2. **Pre-sync SCRIBE snapshot**:
   ```
   sqlite3 python/data/aurum_intelligence.db \
       "SELECT journal_source, COUNT(*) FROM forge_signals GROUP BY 1;"
   ```
   Record these numbers as baseline.

3. **Idempotency pre-check** — run the duplicate audit:
   ```
   sqlite3 python/data/aurum_intelligence.db "
   SELECT COUNT(*) AS dup_signal_keys FROM (
     SELECT forge_id,time,symbol,journal_source
     FROM forge_signals GROUP BY 1,2,3,4 HAVING COUNT(*)>1);
   SELECT COUNT(*) AS dup_trade_keys FROM (
     SELECT deal_ticket, journal_source
     FROM forge_journal_trades GROUP BY 1,2 HAVING COUNT(*)>1);"
   ```
   Both counts must be 0 before proceeding.

4. **Decision gate** (human judgment required):
   - If the tester backlog is analytics noise that should never be synced,
     document that BRIDGE should be configured to skip tester journals or
     truncate old tester rows after N days.
   - If the tester data is valuable, trigger one BRIDGE sync cycle and
     re-run step 2 and 3 to confirm row counts grew correctly and no
     duplicates appeared.

5. Document the decision and outcome in `CHANGELOG.md` under today's date.

### Phase 4 checklist

| Check | Command | Pass/Fail |
|---|---|---|
| Tester unsynced count confirmed | `sqlite3 <tester-journal> "SELECT COUNT(*) ..."` | |
| Pre-sync SCRIBE baseline recorded | `sqlite3 python/data/aurum_intelligence.db ...` | |
| Duplicate audit clean before sync | Both dup counts = 0 | |
| Decision documented in CHANGELOG | Edit CHANGELOG.md | |
| Post-sync duplicate audit clean (if synced) | Re-run step 3 | |

---

## Phase 5 — Tooling and docs cleanup

### Goal
Remove the remaining low-severity gaps so CI and on-call are unambiguous.

### Steps

1. **Install `ruff`** into the project venv (preferred over pyflakes):
   ```
   .venv/bin/pip install ruff
   .venv/bin/ruff check python/scribe.py python/bridge.py \
       scripts/diagnose_forge_journal.py
   ```
   Fix any reported issues that are not style-only (ignore line-length by default).

2. **Add Makefile target** for the focused journal tests (**Composer:** match existing Makefile style — use `$(PYTHON)` so `.venv` is preferred):
   ```makefile
   test-journal:
   	@$(PYTHON) -m pytest $(ROOT_DIR)/tests/services/test_scribe_forge_journal.py -v
   ```
   Run `make test-journal` to confirm it works.

3. **Update README / docs** — add or verify one paragraph in
   `docs/FORGE_JOURNAL_SQL.md` stating:
   > All components that open the operational SCRIBE DB resolve to
   > `python/data/aurum_intelligence.db` relative to repo root.
   > Override with `SCRIBE_DB` (repo-root-relative or absolute).
   > Use `python3 scripts/diagnose_forge_journal.py` — not `python` — to inspect.

4. **`.env.example` `python` note** — add a comment near `SCRIBE_DB`:
   ```
   # Use python3 (not python) to run scripts on this machine.
   ```

### Phase 5 checklist

| Check | Command | Pass/Fail |
|---|---|---|
| `ruff` installed and clean | `.venv/bin/ruff check ...` | |
| `make test-journal` works | `make test-journal` | |
| FORGE_JOURNAL_SQL.md has canonical path paragraph | Read docs | |
| `.env.example` has `python3` note | Read .env.example | |

---

## Final gate — full test suite

After all phases, run the **offline** suite (no ATHENA required):

```
cd /Users/olasumbo/signal_system
.venv/bin/python -m pytest tests/ -q --tb=short
```

**Composer notes:**

- There is **no** `tests/integration/` tree in this repo; do not rely on `--ignore=tests/integration`.
- **`make test-api`** / `scripts/test_api.py` hit **`localhost:7842`** — run separately if you need that surface; failures there are **not** automatic regressions of journal/SCRIBE logic.

Expected: all offline tests pass (fix or skip matrix documented if anything environment-specific remains).

---

## Output format

Respond with:

1. **Phase-by-phase results** — for each phase, list every checklist row with
   actual command output and Pass/Fail.
2. **Files changed** — list every file edited or created with a one-line summary
   of what changed.
3. **Remaining open items** — anything blocked on human decision or environment
   access (e.g. the tester backlog gate in Phase 4).
4. **Updated operator runbook** — incorporate any new steps discovered during
   implementation into the runbook from the original review.

Run every command in the real environment. Do not simulate or hypothesize results.

---

*End of prompt. Revision block at top documents **Composer (Cursor Agent)** adjustments for Codex / implementers.*
