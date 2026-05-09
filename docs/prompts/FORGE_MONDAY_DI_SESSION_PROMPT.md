# FORGE — Monday buffer + H1 DI directional gate (implementation prompt)

**Motivation:** Run 17 **G8** (Mon Apr 20 ~10:20 UTC, BB_BREAKOUT **BUY**, loss cluster): M5 shows breakout + ADX in a “trend” band, but **ADX magnitude does not encode direction**. FORGE’s **`h1_trend_strength`** uses **EMA20 vs EMA50** normalized by ATR — useful, but not Wilder’s **+DI / −DI** directional split. Hypothesis: **counter-directional BUYs** can still fire when **H1 −DI dominates +DI** (bearish directional flow per classic ADX indicator).

**This doc is an implementation spec.** Validate with a single-bar replay (tester journal time + H1 buffers) before treating DI as proven root cause for G8.

---

## Part A — Time & session (audit baseline — do not contradict)

These facts are from **`ea/FORGE.mq5`** as of the audit that produced this prompt.

### A.1 Session clock is **UTC via `TimeGMT()`**

- Native scalper uses **`MqlDateTime dt; TimeGMT(dt);`** then **`dt.hour`** for **London / NY / “Asian”** labeling and **`ScalperSessionOK()`** / **`ScalperTesterSessionOK()`**.
- **Implement any Monday / calendar gate with the same `TimeGMT(dt)` decomposition** so logs, journal **`session`**, and policy agree.

### A.2 Session buckets (residual “Asian”)

- **LONDON** if `london_start ≤ hour < london_end`
- **Else NY** if `ny_start ≤ hour < ny_end`
- **Else** labeled **ASIAN** (hours **not** in London or NY windows)

**Note:** If **London and NY windows are identical**, the **`LONDON` branch wins first**; **`NY` is never chosen** for those hours. Separate windows if you need distinct **NY** behavior.

### A.3 Live vs Strategy Tester

- **Live:** **`ScalperSessionOK()`** can block entries outside allowed session buckets.
- **Tester:** **`ScalperTesterSessionOK()`** plus **`tester_allowed_sessions`** — session blocking **differs** from live by design (comment in `CheckNativeScalperSetups`: simulated **`TimeGMT()`** can sit outside narrow windows).

**Requirement:** Document whether **Monday buffer** and **DI gate** apply in **tester + live** identically, or are gated by **`MQL_TESTER`** / new config **`monday_buffer_apply_in_tester`**.

### A.4 Journal **`time`** vs **`session`**

- **`JournalRecordSignal`** builds **`session`** from **`TimeGMT(dt).hour`**.
- The **`SIGNALS.time`** column uses **`TimeCurrent()`** in the SQL insert.

**Requirement:** Any operator doc or replay script must state which timestamp drives **day-of-week** vs which is stored as **`time`** (avoid off-by-one-day confusion).

### A.5 Config hygiene (**tester allowlist token**)

- EA classifies sessions as **`"LONDON"`**, **`"NY"`**, **`"ASIAN"`** (uppercased tokens).
- **`tester_allowed_sessions`** in **`config/scalper_config.defaults.json`** must use **`NY`**, not **`NEW_YORK`**, unless the EA is extended to accept aliases.

**Acceptance:** `"LONDON,NY"` (or alias support in MQL) so tester session filter behaves as intended.

---

## Part B — Feature 1: H1 +DI / −DI directional confirmation

### B.1 Goal

Before allowing **BB_BREAKOUT BUY** (and optionally other BUY paths), require **H1 directional agreement** using:

- **`DI+`** and **`DI−`** from the standard **ADX** indicator (Wilder; MT5 **`iADX`**, sub-indices per MQL5 docs — implementer verifies buffer indices for **+DI** and **−DI**).

### B.2 Suggested gate (configurable)

| Parameter | Role | Starter default |
|-----------|------|-----------------|
| `breakout_require_h1_di_buy` | **bool** — if true, BUY needs **`DI+ > DI−`** (optional margin) | `true` or `false` (ship **off** until backtested) |
| `breakout_h1_di_margin` | Minimum **`DI+ − DI−`** for BUY (points) | `0` or small epsilon |

**SELL symmetry (optional):** `breakout_require_h1_di_sell` requiring **`DI− > DI+`**; respect existing **`adx_min_sell`** and RSI gates — do not duplicate logic incoherently.

### B.3 Integration points

- Create or reuse **H1 ADX handle** (FORGE may already have MTF ADX on M5; **H1 is additional**).
- Evaluate on the **same bar semantics** as **`h1_trend_strength`** (typically **closed H1 bar 1** — match existing HTF convention in the EA).
- **Journal:** new **`gate_reason`** examples: `entry_quality_h1_di_buy`, `entry_quality_h1_di_sell` (names subject to **`docs/FORGE_JOURNAL_SQL.md`** / **`DATA_CONTRACT.md`** update).

### B.4 Telemetry

- Extend **`WriteModeStatus()`** or **`scalper_entry.json`** with **`h1_di_plus`**, **`h1_di_minus`**, **`h1_di_diff`** when the gate is enabled (optional but recommended for Run 18/19 forensics).

---

## Part C — Feature 2: Monday UTC buffer (calendar gate)

### C.1 Goal

Reduce **Monday false breakouts** (e.g. G8-class) by **blocking or tightening** entries during a **configurable UTC window** on **Monday only**.

### C.2 Config (clear semantics — pick one naming scheme)

| Key | Meaning |
|-----|---------|
| `monday_buffer_enabled` | **0/1** |
| `monday_buffer_start_utc_hour` | First **inclusive** UTC hour (0–23) of buffer (**e.g. 7** = week open pressure) |
| `monday_buffer_end_utc_hour` | **Exclusive** end hour (0–24) OR use duration minutes — **document choice** |
| `monday_buffer_setup_types` | Comma list or bitmask: e.g. **`BB_BREAKOUT`** only vs all native entries |
| `monday_buffer_apply_in_tester` | **0/1** — default **1** if you want Run replay to match live policy |

**Example:** Block **BB_BREAKOUT** only from **07:00–11:00 UTC** Mondays: `start=7`, `end=11` (exclusive), `setup_types=BB_BREAKOUT`.

**Requirement:** Use **`TimeGMT(dt)`** and **`dt.day_of_week`** per MQL5 (**verify**: which weekday index is Monday in `MqlDateTime`).

### C.3 Journal

- **`gate_reason`:** e.g. `monday_buffer` with **`setup_type`** preserved.

---

## Part D — Feature 3 (optional): Pre-London / “Asian bleed” context

FORGE **does not** currently compute **Tokyo-range high/low** or **Asian volatility** as a first-class signal—**“Asian”** is only **residual UTC hours** per **`session_filter`**.

If you want **Asian bleed into London**:

1. Define **explicit windows**, e.g. **`asian_range_utc_start` / `asian_range_utc_end`** (can overlap London open).
2. Each day (UTC), compute **Asian session high/low** (or ATR) and pass into **Breakout BUY** logic (e.g. don’t chase into **upper band** if price is only **re-testing Asia high** without DI alignment).

**Defer** to phase 2 unless Monday + DI already fix G8-class losses.

---

## Part E — Repo hygiene (required on merge)

1. **`config/scalper_config.defaults.json`** + **`make scalper-env-sync`**
2. **`scripts/sync_scalper_config_from_env.py`** — **`FORGE_*`** mappings with clamps
3. **`VERSION` / `FORGE_VERSION`**, **`CHANGELOG.md`**
4. **`docs/FORGE_TRADING_RULES.md`** — session clock (**UTC**), Monday buffer, DI gate
5. **`docs/FORGE_JOURNAL_SQL.md`**, **`docs/DATA_CONTRACT.md`** — new **`gate_reason`** values if added
6. **`.env.example`** — comment new overrides

---

## Part F — Acceptance criteria

1. **Regression:** With **`monday_buffer_enabled=0`** and **`breakout_require_h1_di_buy=0`**, tester results unchanged (within noise).
2. **G8 replay:** On the **exact simulated timestamp** of G8, log shows **DI+, DI−, diff** and whether BUY would be **blocked** (one row or `PrintFormat` block).
3. **Session:** **`tester_allowed_sessions`** uses **`NY`** or EA accepts **`NEW_YORK`** alias.
4. **Docs:** Operator knows **UTC** vs journal **`time`** column semantics.

---

*Prompt version: 2026-05-08 — combines Run 17 G8 motivation with audited FORGE `TimeGMT` session behavior and journal timestamp caveat.*
