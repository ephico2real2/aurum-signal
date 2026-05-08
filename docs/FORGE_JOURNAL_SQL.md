# FORGE journal — SQL reference (skipped setups & evaluations)

FORGE writes evaluated setups to a **local SQLite** file. BRIDGE syncs the same logical rows into SCRIBE **`forge_signals`** for analytics and ML.

All components that open the operational SCRIBE DB resolve to `python/data/aurum_intelligence.db` relative to repo root. Override with `SCRIBE_DB` (repo-root-relative or absolute). Use `python3 scripts/diagnose_forge_journal.py` — not `python` — to inspect.

| Store | Path / table | Notes |
|--------|----------------|--------|
| **SCRIBE (preferred)** | `python/data/aurum_intelligence.db` → **`forge_signals`** | Columns include `timestamp_utc`, **`journal_source`** (`live` \| `tester`). |
| **Live journal** | MT5 Common Files → `FORGE_journal_<SYMBOL>.db` → **`SIGNALS`** | `synced` 0/1 until exported to SCRIBE. |
| **Tester journal** | Tester agent `MQL5/Files` → `FORGE_journal_<SYMBOL>_tester.db` → **`SIGNALS`** | Same schema; `TESTER_RUNS` metadata. |

Skipped evaluations use **`outcome = 'SKIP'`** and a non-empty **`gate_reason`** (e.g. `no_setup`, `rr_too_low`, `direction_cooldown`, `execution_failed`, and **FORGE v2.6.5+** native **`entry_quality_atr`**, **`entry_quality_body`**, **`entry_quality_direction`**, **`entry_quality_bb_contraction`**, plus **v2.6.6+** **`entry_quality_direction_cap`**). **`TAKEN`** rows have **`outcome = 'TAKEN'`** and usually an empty **`gate_reason`**.

---

## 1. Quick counts — skipped setups

### SCRIBE (`forge_signals`)

```sql
-- All-time SKIP count and breakdown
SELECT journal_source,
       COALESCE(gate_reason, '') AS gate,
       COUNT(*) AS n
FROM forge_signals
WHERE outcome = 'SKIP'
GROUP BY journal_source, gate
ORDER BY journal_source, n DESC;
```

```sql
-- Skips in the last 24 hours (requires valid ISO timestamps in timestamp_utc)
SELECT COUNT(*) AS skips_24h
FROM forge_signals
WHERE outcome = 'SKIP'
  AND datetime(replace(substr(timestamp_utc, 1, 19), 'T', ' ')) >= datetime('now', '-1 day');
```

```sql
-- Latest skipped rows (newest first)
SELECT id, timestamp_utc, journal_source, gate_reason, setup_type, direction,
       price, atr, rsi, adx, session, magic
FROM forge_signals
WHERE outcome = 'SKIP'
ORDER BY id DESC
LIMIT 50;
```

### Raw FORGE journal (`SIGNALS`)

Use the same shapes; replace table name and use Unix **`time`** instead of **`timestamp_utc`**:

```sql
SELECT gate_reason, COUNT(*) AS n
FROM SIGNALS
WHERE outcome = 'SKIP'
GROUP BY gate_reason
ORDER BY n DESC;
```

```sql
SELECT datetime(time, 'unixepoch') AS ts_utc, gate_reason, setup_type, direction, price, rsi, adx
FROM SIGNALS
WHERE outcome = 'SKIP'
ORDER BY id DESC
LIMIT 50;
```

```sql
-- Unsynced rows still waiting for BRIDGE
SELECT COUNT(*) FROM SIGNALS WHERE outcome = 'SKIP' AND IFNULL(synced, 0) = 0;
```

---

## 2. Common `gate_reason` values (SKIP)

| `gate_reason` | Typical meaning |
|---------------|-----------------|
| `no_setup` | No BB bounce/breakout path matched (or throttled to once per M5 bar in EA **v2.4.3+**). |
| `rr_too_low` | Direction found but reward/risk below minimum (throttled per M5 bar in **v2.4.3+**). |
| `session_off` | Session filter blocked. |
| `spread` | Spread too wide. |
| `open_groups` | `max_open_groups` cap. |
| `session_trade_cap` | Session trade cap. |
| `cooldown` | Loss cooldown. |
| `direction_cooldown` | Anti-whipsaw bars. |
| `m1` | M1 gate failed. |
| `regime_countertrend` | Regime policy blocked direction. |
| `execution_failed` | Setup passed but **no orders** opened (**v2.4.3+**). |

---

## 3. ATHENA `/api/scribe/query`

Same SQL as section 1 against `forge_signals`. Example:

```bash
curl -sS -X POST "http://localhost:7842/api/scribe/query" \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT journal_source, gate_reason, COUNT(*) n FROM forge_signals WHERE outcome = '\''SKIP'\'' GROUP BY 1,2 ORDER BY n DESC LIMIT 20"}'
```

If `ATHENA_SCRIBE_QUERY_SECRET` is set, add the header documented in `docs/SCRIBE_QUERY_EXAMPLES.md`.

---

## 4. CLI from repo root

```bash
export DB="${SCRIBE_DB:-python/data/aurum_intelligence.db}"
sqlite3 "$DB" "SELECT outcome, gate_reason, COUNT(*) n FROM forge_signals GROUP BY 1,2 ORDER BY n DESC;"
make journal-diagnose
```

---

## 6. Tester backlog handling

When a tester journal accumulates a large backlog of skip-only rows (e.g. before a journal spam fix), **do not sync them into SCRIBE**. Skip-only rows (`SKIP|no_setup`, `SKIP|rr_too_low`) with zero `TAKEN` outcomes have no ML value and will bias analytics.

Mark them consumed directly in the source journal:

```bash
sqlite3 "<path-to-FORGE_journal_*_tester.db>" \
  "UPDATE SIGNALS SET synced=1 WHERE synced=0;
   SELECT changes() AS rows_marked_synced;
   SELECT COUNT(*) AS unsynced_remaining FROM SIGNALS WHERE synced=0;"
```

Verify gate_reason distribution before deciding — if `TAKEN` rows exist, sync those first:

```bash
sqlite3 "<tester-journal>" \
  "SELECT gate_reason, COUNT(*) FROM SIGNALS WHERE synced=0 GROUP BY 1 ORDER BY 2 DESC LIMIT 10;"
```

---

## 5. Related

- More examples: `docs/SCRIBE_QUERY_EXAMPLES.md` (§21–22).
- Machine-readable examples: `schemas/scribe_query_examples.json`.
- ML / consolidation: `docs/FORGE_JOURNAL_ML_PROMPT.md`.
