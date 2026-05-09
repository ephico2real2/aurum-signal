# FORGE DB/EA Enhancement Plan — Journal Integrity & Magic Number Fix
**Date:** 2026-05-08 | **Priority:** Infrastructure — implement after Run 17/18 gate sprint

---

## Problem 1: SIGNALS.magic always stores base magic (no group attribution)

### Current behaviour
`JournalRecordSignal("TAKEN", ...)` is called **before** the group magic offset is assigned. The EA logs `MagicNumber` (e.g. `202401`) into the `magic` column for every TAKEN signal, regardless of which group was opened. This means:
- All TAKEN signals share the same magic value in the DB
- SIGNALS cannot be directly joined to TRADES on `magic`
- BUY vs SELL P&L requires workarounds (closing-deal direction inference, time-window lookups)

### Root cause in EA (FORGE.mq5)
The `JournalRecordSignal("TAKEN", ...)` call fires in `ForgeNativeScalperLogic()` after the setup direction is determined but before `OpenNativeGroup()` assigns the group ID and derives the magic offset. By the time `g_trade.SetExpertMagicNumber(magic_offset)` is called, the TAKEN signal has already been written.

### Fix — Internal group counter + magic stored at TAKEN time

**Step 1: Add a global group counter:**
```mq5
// Global — increments each time a new group is opened this run
int g_group_counter = 0;

// In OnInit / tester reset:
g_group_counter = 0;
```

**Step 2: Derive pending group magic before TAKEN signal is logged:**
```mq5
// In ForgeNativeScalperLogic(), just before JournalRecordSignal("TAKEN"):
int pending_group_id = g_group_counter + 1;  // next group to be opened
int pending_magic = MagicNumber + pending_group_id;
// Pass pending_magic to JournalRecordSignal instead of 0/MagicNumber
```

**Step 3: Increment counter when group actually opens:**
```mq5
// In OpenNativeGroup(), on first successful order:
g_group_counter++;
int magic_for_this_group = MagicNumber + g_group_counter;
g_trade.SetExpertMagicNumber(magic_for_this_group);
```

**Step 4: Update JournalRecordSignal signature** to accept a `magic_override` parameter (or pass it as the existing `magic` field):
```mq5
// Current: JournalRecordSignal("TAKEN","",setup_type,direction,...)
// Fixed:   JournalRecordSignal("TAKEN","",setup_type,direction,..., pending_magic)
```

### Result: direct join works
```sql
-- Clean BUY/SELL P&L — no workarounds
SELECT s.direction,
  COUNT(s.id) as groups,
  SUM(t.deals) as deals,
  SUM(t.wins) as wins,
  ROUND(SUM(t.pnl),2) as pnl
FROM SIGNALS s
JOIN (
  SELECT magic, COUNT(*) as deals,
    SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) as wins,
    SUM(profit) as pnl
  FROM TRADES WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
    AND direction IN (1,2,3)
  GROUP BY magic
) t ON t.magic = s.magic
WHERE s.outcome='TAKEN'
  AND s.run_id=(SELECT MAX(id) FROM TESTER_RUNS)
GROUP BY s.direction;
```

---

## Problem 2: Journal DB does not append — each run overwrites

### Current behaviour
The tester DB appears to reset between runs (or the file is recreated). Run 17 started as `run_id=1` in a fresh DB after Run 16 completed with `run_id=5`. This means:
- Historical run data is lost when the tester resets
- Cross-run comparison requires manual DB backup before each run
- `make journal-reset-tester` is required but also destroys previous data

### Root cause
The tester DB file is likely re-created by the EA on `OnInit()` in tester mode, or the `make journal-reset-tester` target drops and recreates tables. The `TESTER_RUNS` table auto-increments from 1 on each fresh DB.

### Fix — Persistent append-mode journal

**Option A: Never drop — just insert new run rows**
- Remove the `DROP TABLE` / `DELETE FROM` calls from `journal-reset-tester`
- Replace with: `INSERT INTO TESTER_RUNS` always appends
- `run_id` auto-increments naturally across sessions
- Cross-run comparison works across all historical runs in a single DB

**Option B: Separate archive DB + active DB**
- `FORGE_journal_XAUUSD_tester.db` = active (one run at a time, small)
- `FORGE_journal_XAUUSD_archive.db` = all historical runs (append-only)
- After each run: copy run data to archive, then reset active
- Complex but keeps active DB small for tester performance

**Recommendation: Option A** — simplest, no EA changes needed. Just change `make journal-reset-tester` to not wipe data. Add a `make journal-new-run` target that marks the start of a new logical run without dropping history.

### Makefile changes needed
```makefile
# Current (destructive):
journal-reset-tester:
    @sqlite3 "$(TESTER_DB)" "DROP TABLE IF EXISTS SIGNALS; DROP TABLE IF EXISTS ..."

# Fixed — append mode, never drop:
journal-reset-tester:
    @echo "Warning: journal-reset-tester now deprecated. Use journal-new-run."
    @echo "All run data is preserved. Run IDs auto-increment."

journal-new-run:
    @echo "New run will get next auto-incremented run_id from TESTER_RUNS."
    @echo "No reset needed — EA appends a new TESTER_RUNS row on each OnInit()."
```

**EA change needed:** Ensure `OnInit()` in tester mode always `INSERT INTO TESTER_RUNS` and never `DELETE FROM SIGNALS WHERE run_id=...`. Currently the EA may wipe signals from its own run_id on reinit.

---

## Problem 3: Entropy number for magic uniqueness across sessions

### Current issue
`MagicNumber + group_counter` can produce the same magic value across different tester runs if both start at `group_counter=0`. E.g., Run 1 group 1 = magic 202402, Run 2 group 1 = magic 202402. Trades from different runs share magic values.

### Fix — Wall-time entropy in magic offset
```mq5
// On OnInit(), generate a run-unique entropy offset:
int g_run_entropy = 0;

// In OnInit():
g_run_entropy = (int)(TimeGMT() % 10000);  // 0–9999 range
// Or use tester run_id × stride:
// g_run_entropy = g_tester_run_id * 1000;  // needs run_id assigned first

// Group magic:
int magic_for_group = MagicNumber + g_run_entropy * 100 + g_group_counter;
// Example: Run entropy=1234, group=5 → magic = 202401 + 123400 + 5 = 325806
```

This ensures no two runs produce the same magic numbers, even if the DB is append-mode. Cross-run P&L attribution by magic becomes unambiguous.

**Alternative (simpler):** Use `wall_time` from `TESTER_RUNS` as the uniqueness key — store `run_id` in every TAKEN signal and join on `(run_id, magic)` rather than `magic` alone. This avoids entropy in the magic number itself.

---

## Implementation Order

| Step | What | EA change? | DB change? | Effort |
|------|------|-----------|-----------|--------|
| 1 | Group counter + magic stored in SIGNALS.magic at TAKEN time | Yes — small | No | Medium |
| 2 | Append-mode journal — remove DROP from reset target | No | Yes — Makefile only | Small |
| 3 | Entropy magic offset to prevent cross-run collision | Yes — small | No | Small |

**Suggested version:** FORGE 2.8.0 (DB infrastructure sprint, no gate changes)

---

## Impact on Queries After Fix

| Query | Before fix | After fix |
|-------|-----------|-----------|
| BUY/SELL P&L | Uses `TRADES.type=1, direction` workaround | Direct `JOIN ON magic` |
| Group attribution | Time-window magic lookup (fragile) | `WHERE magic = s.magic` |
| Cross-run compare | Requires DB backup between runs | Single DB, all runs in `TESTER_RUNS` |
| Loss investigation | Join by time proximity | Join by exact magic |

---

*Last updated: 2026-05-08*
