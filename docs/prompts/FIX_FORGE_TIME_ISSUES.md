# Prompt: fix FORGE time & session issues

Use this as the **agent / developer brief** to harden **`ea/FORGE.mq5`** and config around **clocks, sessions, and tester parity**. Full rationale and patterns live in **`docs/FORGE_SESSION_TIME_PRODUCTION.md`**. Monday / DI work stays in **`docs/prompts/FORGE_MONDAY_DI_SESSION_PROMPT.md`**.

---

## Goals

1. **One canonical policy clock** for session and calendar rules (prefer **`TimeGMT()`** where FORGE already uses it; do not use **`TimeLocal()`** for gating).
2. **Tester allowlist** matches EA session tokens.
3. **Journal / replay** semantics are documented and consistent where cheap to fix.
4. Optional: **minute-precision** windows; **broker session** gate; **explicit daily** counters — only if scoped in the same PR or follow-ups.

---

## Issue 1 — `tester_allowed_sessions` token mismatch (**bug**)

**Symptom:** `ScalperTesterSessionOK()` compares CSV tokens to **`"LONDON"`**, **`"NY"`**, **`"ASIAN"`** (see `ea/FORGE.mq5`). **`config/scalper_config.defaults.json`** uses **`"LONDON,NEW_YORK"`** — **`NEW_YORK` ≠ `NY`**, so **NY** hours never match the allowlist as written.

**Fix (pick one):**

- **A)** Change defaults + generated JSON to **`LONDON,NY`**; update **`.env.example`** if documented.
- **B)** In MQL5, after `StringToUpper`, map **`NEW_YORK` → `NY`** (and any other aliases).

**Verify:** Strategy Tester with `tester_session_filter=1` and allowed `LONDON,NY` trades during intended UTC hours.

---

## Issue 2 — Overlapping London / NY UTC windows

**Symptom:** If **`london_start_utc`…`london_end_utc`** equals **`ny_start_utc`…`ny_end_utc`**, the **`LONDON`** branch runs **first**; **`current_session` is never `NY`** for those hours.

**Fix:** Document in **`docs/FORGE_TRADING_RULES.md`** and/or adjust defaults so **NY** is a **distinct** window if you need separate NY behavior; or accept “combined” and rename labels for clarity.

---

## Issue 3 — Hour-only session detection

**Symptom:** All native scalper session checks use **`dt.hour` only** — sub-hour blackouts and killzones are impossible without extension.

**Fix (phased):**

- **Phase 1:** Document current behavior (UTC hour, half-open `[start, end)`).
- **Phase 2:** Add optional **`session_filter`** keys for **minute** bounds (or reuse `IsTimeBetween`-style logic from **`FORGE_SESSION_TIME_PRODUCTION.md`**) and use the **same** `TimeGMT` source.

---

## Issue 4 — Journal `time` vs `session` clock

**Symptom:** **`SIGNALS.session`** derives from **`TimeGMT(dt).hour`**; **`SIGNALS.time`** SQL insert uses **`TimeCurrent()`** (see `JournalRecordSignal` path in `FORGE.mq5`).

**Fix (pick one):**

- **A)** Document in **`docs/FORGE_JOURNAL_SQL.md`** / **`FORGE_TESTER_JOURNAL_QUERIES.md`** that **day-boundary analytics** should use a **chosen** column or join to bar time.
- **B)** Add **`time_gmt`** column or store policy timestamp explicitly (schema migration — larger change).

---

## Issue 5 — Daily reset vs “session string” reset

**Symptom:** `ResetScalperSessionStateIfNeeded()` resets on **UTC day** and **session label** changes; there is no single **`trades_today`** / **`daily_pnl`** struct unless added.

**Fix:** If product needs **hard daily max trades or daily loss cap in EA**, add **`CheckDailyReset()`** pattern using **`TimeGMT`** date parts only, and persist state if required (see production doc §2).

---

## Issue 6 — Backtest-safe time audit

**Task:** Grep **`FORGE.mq5`** for **`TimeLocal(`** and any **`TimeToStruct(TimeLocal`**. Replace or restrict to **logging only**; **gating** must use **`TimeCurrent()`** / **`TimeGMT()`** per tester semantics.

---

## Issue 7 — Broker schedule (optional)

**Task:** Optional gate **`SymbolInfoSessionTrade`** (or current MQL5 equivalent) before **new entries** — verify **official** return types for **`from`/`to`** (seconds vs `datetime`).

---

## Issue 8 — `OnTimer` vs `OnTick`

**Task:** Document in code comment or **`FORGE_TRADING_RULES.md`** where **`CheckNativeScalperSetups`**, **`WriteModeStatus`**, and session resets run; ensure **session housekeeping** still runs when ticks are sparse (**`OnTimer`**).

---

## Deliverables checklist

- [ ] **`ea/FORGE.mq5`** — token alias or consistent `NY` labeling.
- [ ] **`config/scalper_config.defaults.json`** + **`make scalper-env-sync`** (if defaults change).
- [ ] **`docs/FORGE_TRADING_RULES.md`** — UTC hour model, optional overlap note.
- [ ] **`docs/FORGE_JOURNAL_SQL.md`** — `time` vs `session` caveat if not changing schema.
- [ ] **`CHANGELOG.md`** + bump **`VERSION` / `FORGE_VERSION`** if behavior changes.
- [ ] Tester run proving **session filter** allows trades when `LONDON,NY` is intended.

---

*Prompt version: 2026-05-09 — actionable fixes derived from FORGE session/time audit.*
