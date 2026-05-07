# Warp.ai prompt — FORGE native scalper: verify why trades aren’t firing

Copy everything **below** the horizontal rule into Warp (or any assistant) as a single message. It is self-contained so the tool does not need your full repo context.

---

**Project:** MetaTrader 5 Expert Advisor **FORGE** (MQL5), repository “signal_system”. Native scalper modes: `NONE | BB_BOUNCE | BB_BREAKOUT | DUAL`. Execution path: `OnTick` → `CheckNativeScalperSetups()` → optional native trade group execution (market legs with comments like `SCALP|BB_BOUNCE|G<id>|TP1`).

**Goal:** We changed behavior so that (1) **bounce fades don’t fire against clear H1+M15 trend**, (2) **Strategy Tester respects bounce ADX cap and H1 filter** when JSON flags say so, (3) **staged entry** opens only `staged_initial_legs` first and adds legs later via `ManageStagedNativeLegs()` (interval + min favorable points + optional rolling anchor). **Problem now:** **Trades are not being taken again** (live or tester—need to distinguish), and/or **BRIDGE / AURUM** shows **`FORGE_SCALP_ENTRY_IGNORED`** / **`RECONCILER_NO_MT5_EXPOSURE`** even when FORGE opened legs (sync / snapshot timing).

**Where data lives (do not confuse these):**

1. **SCRIBE / “Aurum” mirror DB (Python, analytics, `forge_signals`)**  
   - Default path: **`python/data/aurum_intelligence.db`** (override with env **`SCRIBE_DB`**; legacy relative `data/aurum_intelligence.db` maps to the same canonical file).  
   - Tables: **`forge_signals`** (each journal row synced from FORGE: `outcome`, `gate_reason`, `setup_type`, `direction`, `journal_source` = `live` | `tester`), **`forge_journal_trades`**, **`trade_groups`**, **`trade_closures`**, etc.  
   - **Monitor SKIP mix:** `make monitor-forge-skips` or `python3 scripts/monitor_forge_skips.py` (read-only).  
   - **AURUM can lag the tester journal:** BRIDGE syncs journals on an interval (e.g. ~60s) via **`_resolve_forge_journal_paths()`**. If **`forge_signals`** `MAX(id)` / tail timestamps do not move while **`FORGE_journal_*_tester.db`** on disk grows, **BRIDGE may be off** or scanning a **different** agent path—verify the **Agent-* **` file MT5 actually updates (`ls -la`, `sqlite3 … ORDER BY time DESC LIMIT 5`).

2. **FORGE native journal SQLite (MT5 writes this; one file per symbol/mode)**  
   - **macOS + Wine MT5 typical locations:**  
     - **Strategy Tester agents:**  
       `~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/Agent-127.0.0.1-*/MQL5/Files/FORGE_journal_*_tester.db`  
       **Note:** Port **`3000` vs `3001` (or other agents)** can differ per run—confirm which folder MT5 is writing **during this test**. Inside **`SIGNALS`**, use **`ORDER BY time DESC`** for “current simulated moment”; **`ORDER BY id DESC`** can disagree with **`time`** (do not use **`id`** alone as the journal clock).  
     - **Terminal Common (live-style bus):**  
       `~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/FORGE_journal_*.db`  
   - Inside those files the EA’s table is usually **`SIGNALS`** (not `forge_signals`).  
   - **Discover + JSON summary:** `make journal-diagnose` (searches the Wine tree and prints counts + top `gate_reason`s).

3. **Scalper parameters (defaults → generated JSON)**  
   - **Edit** committed defaults in **`config/scalper_config.defaults.json`** and/or **`FORGE_*` in `.env`** (see **`scripts/sync_scalper_config_from_env.py`** `MAPPING`).  
   - **Generate** **`config/scalper_config.json`** with **`make scalper-env-sync`** or **`make forge-compile`** (stamps **`version`** from **`VERSION`**). **Do not** treat `scalper_config.json` as hand-edited source — it is overwritten by sync.  
   - **Runtime:** FORGE reads **`scalper_config.json`** from **MT5 Common Files** (and optional **`FilesPath`**). **`make scalper-config-sync`** only **copies** the existing repo JSON to Common (no regenerate). Details: **`docs/SCALPER_CONFIG_PIPELINE.md`**.

**Ask Warp to verify logic in this order:**

1. **Config actually loaded**  
   - `scalper_config.json` must be readable via FORGE’s dual path (terminal Common Files and optional `FilesPath` input).  
   - Keys under `bb_bounce` that affect **whether any bounce trade can happen:**  
     - `bounce_block_htf_trend_align` (blocks bounce SELL if H1 bull **and** M15 bull; blocks bounce BUY if H1 bear **and** M15 bear). Very effective at **reducing** bounce count.  
     - `bounce_respect_adx_max_in_tester`, `bounce_respect_h1_filter_in_tester` (tester parity).  
     - `adx_max`, RSI bands, `bounce_require_*`, ADX hysteresis regime (`adx_trend_regime` can skip all bounce when M5 ADX says “trend”).  
   - **`lot_sizing`:** `staged_entry_enabled`, `staged_initial_legs`, `staged_add_interval_sec`, `staged_add_min_favorable_points`, `staged_favorable_from_entry_only`, `min_num_trades` / `max_num_trades`, recovery boost keys.  
   - **If `max_num_trades` envelope is wide but staged entry is on**, the first bar only opens the probe; missing follow-up adds can look like “no size” but should still show **at least one** TAKEN row if the setup passes.

1b. **EA Inputs (modes)**  
   - **`InputMode`** must **not** be **`WATCH`** or **`OFF`** if native scalper is expected on tick (see **`OnTick`**: `CheckNativeScalperSetups` only when `g_scalper_mode != "NONE"` **and** `g_mode` not WATCH/OFF).  
   - **`ScalperMode`** must **not** be **`NONE`** (`DUAL` / `BB_BOUNCE` / `BB_BREAKOUT`).  
   - Tester startup prints **`FORGE TESTER:`** hints when these block the scalper.

1c. **Warmup (`ForgeNativeScalperWarmupOk`) — blocks *all* entries until pass**  
   - History: **≥70 bars** on M5/M15/M30/H1/H4 (+ M1 if M1 mode used), **`SERIES_SYNCHRONIZED`**, full **MTF/H1/H4** (and optional PSAR) **`CopyBuffer`** probes—reasons like **`h4_ema20_buf`**, **`h1_bars`**, **`tester_m5_rollovers`**, **`live_m15_rollovers`**, **`warmup_delay`**.  
   - **Tester-only:** **`ScalperTesterWarmupM5Bars`**, **`ScalperTesterWarmupSimCapMinutes`** (cap only applies if M5 bars **> 0**); **`0`** M5 bars disables that whole tester rollover block **and** skips bar-count + sync proxy checks (fast-start).  
   - **Live-only:** **`ScalperLiveWarmupM15Bars`**.  
   - **Both:** **`ScalperWarmupSeconds`** (wall/sim seconds **after** the above).  
   - Log: **`FORGE SCALPER: skip gate=warmup reason=...`**.  
   - **v2.5.1+:** `MT5/mode_status.json` now exposes `warmup_ok` and `warmup_reason` for remote diagnosis without MT5 Experts tab:
     ```bash
     python3 -c "import json; ms=json.loads(open('MT5/mode_status.json').read()); print(ms.get('warmup_ok'), ms.get('warmup_reason'), ms.get('scalper_mode'))"
     ```
   - **⚠️ `m5_macd_buf` / `h1_macd_buf` — PERMANENTLY FAILING (fixed v2.5.1):** MT5's built-in `iMACD` only has buffers `0` (MACD line) and `1` (signal); buffer `2` (histogram) does not exist. `CopyBuffer(h_macd, 2, ...)` always returns `-1`. This probe caused warmup to block on every tick for the entire backtest. The probe was removed in v2.5.1. If you see this reason on an older build, `make forge-compile` to rebuild.

2. **Early gates in `CheckNativeScalperSetups` (before BB logic)**  
   - Session (`ScalperSessionOK` / tester variant), **max spread** (live only), **open_groups** cap, **session trade cap**, **loss cooldown**, **`ScalperOnePerBar`**, indicators ready (M5 RSI/ATR/BB).

3. **Bounce branch (mean-reversion entry logic)**  
   - **Entry conditions:** BB proximity, RSI vs `bounce_rsi_*`, reclaim/rejection (`bounce_reclaim_pct`, rejection candle / pattern score), bar-0 confirm, liquidity zone, fib/VWAP bias, RSI divergence filters, H1/H4 inputs (`NativeScalperH4Align`), **`bounce_block_htf_trend_align`**.  
   - `m5_adx < bounce_adx_max_eff` (in tester, if `bounce_respect_adx_max_in_tester` is true, `bounce_adx_max_eff` must use JSON `adx_max`, not 99).  
   - If ADX hysteresis active and `g_adx_trend_regime == true` → bounce skipped (`adx_trend_regime_bounce`).  
   - If high-vol trend guard and `high_vol_disable_bounce` → skip.  
   - **R:R check** after SL/TP computed: `reward/risk >= rr_min_eff` (tester often uses relaxed `rr_min_eff`).  
   - **SL/TP:** bounce SL ATR × mult + structural floor; TP1/BB mid, TP2/opposite band; partial close rules in `ManageOpenGroups`.

4. **Breakout branch (trend entry logic)**  
   - Only if bounce didn’t set `direction`; needs ADX min, M5/M15 trend, H1/H4, optional retest path (retest can defer immediate entry).

5. **Post-setup / execution**  
   - Direction cooldown, optional **NativeScalperM1Mode** gate (if not `NONE`).  
   - Regime counter-trend block input **NativeScalperRegimeGate**.  
   - **`ForgeResolveNumTrades`** envelope + modifiers; market loop vs **`ManageStagedNativeLegs`** for additional legs.

6. **Evidence to request from user / logs**  
   - MT5 **Experts** log lines: `FORGE SCALPER: skip gate=...` vs `FORGE SCALPER: BB_BOUNCE ...` / `FORGE STAGED`.  
   - On config reload: **`FORGE V2:`** log line should show `block_htf_vs_bounce`, `respect_adx_cap_tester`, `respect_h1_tester`.  
   - **`forge_signals` in SCRIBE DB:** last rows’ `outcome`, `gate_reason`, `setup_type`, `journal_source`. Dominant `SKIP|no_setup` means **no branch ever set `direction`**, not necessarily a bug. Filter **`journal_source`** (`tester` vs `live`) when diagnosing backtests.  
   - **`FORGE_journal_*.db`:** `SIGNALS` table for raw counts before sync; **`ORDER BY time DESC`** for “where is simulated time now?”  
   - **`system_events` in AURUM:** **`FORGE_SCALP_ENTRY`** vs **`FORGE_SCALP_ENTRY_IGNORED`** (**`no_mt5_exposure_for_magic`**, **`duplicate_open_group_magic`**). **`trade_groups.close_reason`** **`RECONCILER_NO_MT5_EXPOSURE`**.  
   - **Python / BRIDGE:** **`bridge.py`** **`_check_forge_scalper_entry`**: compares **`scalper_entry.json`** **`magic`** to **`market_data.json`** **`open_positions` / `pending_orders`** magics in the **same** BRIDGE cycle.  
   - **FORGE ≥ 2.5.1:** After native fill, EA should call **`WriteMarketData()`** immediately after writing **`scalper_entry.json`** so the snapshot includes new positions (avoids **`no_mt5_exposure_for_magic`** from stale **`open_positions`**). Confirm **`forge_version`** in **`market_data.json`**.  
   - **Live H1 bias:** scalper uses **previous completed H1 bar** (`h1_bias_shift = 1` live); **`WriteMarketData()` `indicators_h1`** may still be bar **0** (dashboard freshness)—do not conflate the two when debugging “H1 direction.”  
   - Distinguish **live chart** vs **Strategy Tester** (`MQL_TESTER` changes relaxations when flags are off).

7. **Hypotheses to check**  
   - **`bounce_block_htf_trend_align` + strong aligned H1+M15** → almost no bounce in trends (by design).  
   - **ADX hysteresis** stuck in TREND → bounce blocked.  
   - **`rr_too_low`** after SL/TP math (wide SL vs tight TP to mid-BB).  
   - **`staged_entry_enabled`** with **`staged_add_min_favorable_points`** never satisfied → only probe or zero adds.  
   - **Stale `scalper_config.json`** in Common Files.  
   - **Inputs** `NativeScalperH4Align`, `NativeScalperRegimeGate`, `ScalperMinTrades` / `ScalperMaxTrades` affect sizing, not always the first gate.  
   - **Warmup never completes** (reason stays **`m5_macd_buf`**, **`tester_m5_rollovers`**, **`live_m15_rollovers`**, etc.) → no `TAKEN` until pass.  
   - **`no_mt5_exposure_for_magic`:** BRIDGE read **`scalper_entry`** before **`market_data`** listed **`open_positions`** for that magic—verify **`WriteMarketData`** after **`scalper_entry`** in EA and that **`MAGIC` + `group_id`** in comments match expectations.  
   - **`ScalperTesterWarmupSimCapMinutes` has no effect when `ScalperTesterWarmupM5Bars = 0`.**  
   - **`m5_macd_buf` as warmup reason** — permanently failing (iMACD has no buffer 2); requires `make forge-compile` to fix with v2.5.1+ code.  
   - **`mode_status.json` missing `scalper_mode` or `warmup_ok`** — old build; recompile to v2.5.1+ where those fields are always emitted.

**Evaluate entry logic (required):**  
Walk through **`CheckNativeScalperSetups`** as a **state machine**: for both **BB_BOUNCE** and **BB_BREAKOUT**, list predicates in order, note **live vs tester** differences, and flag any **contradiction** (e.g. “block counter-trend bounce but RSI band still allows neutral RSI”). Assess whether **`no_setup`**-heavy journals are **expected** given current JSON + inputs.  
**Testing (required):** Propose **concrete tests** the team can run:  
- **Strategy Tester:** 2–3 periods (range vs trend); what to loggrep (`skip gate=`, `BB_BOUNCE`, `STAGED`).  
- **SQL:** assertions on `forge_signals` (e.g. after a known trend week, expect **zero** `TAKEN|BB_BOUNCE|SELL` with `h1_trend` strongly positive if block is on).  
- **Optional:** small **fixture** ideas (exported indicator rows + expected allow/deny) if the user has Python/MQL harnesses.  
Name **pass/fail criteria** for “entry logic is healthy” vs “over-filtered.”

**Deliverable from Warp:** (1) **Decision tree:** “If log / `gate_reason` shows X → check Y in code/config.” (2) **Checklist** (3–5 bullets) for MT5 + config sync. (3) **Entry-logic review** paragraph + **test plan** as above. (4) **SQL snippets** for `forge_signals` rollup + tail.

**Example SQL (SCRIBE mirror `python/data/aurum_intelligence.db`, table `forge_signals`):**

```sql
PRAGMA busy_timeout=10000;
-- Skip/taken mix (tester vs live) — last ~1 day by ISO timestamp
SELECT journal_source, outcome, COALESCE(gate_reason, ''), COUNT(*) AS n
FROM forge_signals
WHERE timestamp_utc >= datetime('now', '-1 day')
GROUP BY journal_source, outcome, gate_reason
ORDER BY journal_source, n DESC;
```

```sql
-- Tail by primary key (not always chronological vs journal `time`)
SELECT id, timestamp_utc, journal_source, outcome, gate_reason, setup_type, direction
FROM forge_signals
WHERE journal_source = 'tester'
ORDER BY id DESC
LIMIT 20;
```

```sql
-- BRIDGE audit trail (native scalper intake)
SELECT id, timestamp, event_type, reason
FROM system_events
WHERE event_type LIKE 'FORGE_SCALP%' OR reason LIKE '%mt5_exposure%'
ORDER BY id DESC
LIMIT 25;
```

---

## Copy-paste — Warp / assistant: **fix FORGE EA** (BRIDGE mismatch, warmup, journals)

Use this as a **second message** when the problem is **not only** `no_setup` / gates, but **Python audit**, **stale snapshots**, or **“no trades” vs journal mismatch**.

---

**Project:** `signal_system` — MT5 EA **`ea/FORGE.mq5`**, Python **`python/bridge.py`**, SCRIBE **`python/data/aurum_intelligence.db`** (or **`SCRIBE_DB`**).

**Symptoms (any combination):**

- AURUM **`system_events`**: **`FORGE_SCALP_ENTRY_IGNORED`** with **`no_mt5_exposure_for_magic`** or **`duplicate_open_group_magic`**.
- **`trade_groups`** closed with **`RECONCILER_NO_MT5_EXPOSURE`** for **`FORGE_NATIVE_SCALP`**.
- Experts shows fills / **`scalper_entry`** intent, but BRIDGE “never saw” the magic in **`open_positions`**.
- **`forge_signals` (AURUM)** tail does not move while **`FORGE_journal_*_tester.db`** on disk clearly grows (wrong **Agent-*** path or BRIDGE not running / sync lag).
- **`skip gate=warmup`** with reasons **`tester_m5_rollovers`**, **`live_m15_rollovers`**, **`m5_macd_buf`**, etc.
- Tester **never calls** scalper: **`InputMode=WATCH`** or **`ScalperMode=NONE`**.

**Root-cause classes to verify in code (in order):**

1. **Stale `market_data.json` vs new `scalper_entry.json`**  
   BRIDGE **`_check_forge_scalper_entry`** (`bridge.py`) matches **`entry["magic"]`** to **`mt5["open_positions"]` / `pending_orders`** from the **same** read of **`market_data.json`**. If FORGE wrote **`scalper_entry.json`** on **`OnTick`** but **`WriteMarketData()`** only ran on **`OnTimer`**, **`open_positions`** could lag → **`no_mt5_exposure_for_magic`**.  
   **Fix pattern (implemented FORGE ≥ 2.5.1):** immediately after **`WriteJsonFileDual("scalper_entry.json", …)`** call **`WriteMarketData()`**. **Acceptance:** **`market_data.json`** **`forge_version`** ≥ **2.5.1** and IGNORED rate drops after reattach.

2. **Magic / exposure reality**  
   Native legs use **`MagicNumber + group_id`** for the trade object; comments **`SCALP|…|G<id>|…`**. Confirm **`open_positions[].magic`** in JSON equals **`scalper_entry.magic`** when the race above is fixed.

3. **Warmup never clears**  
   Inspect **`ForgeNativeScalperWarmupOk`**: bars, sync, buffers, then **tester** **`ScalperTesterWarmupM5Bars` / `ScalperTesterWarmupSimCapMinutes`**, **live** **`ScalperLiveWarmupM15Bars`**, then **`ScalperWarmupSeconds`**. Remember: **`ScalperTesterWarmupSimCapMinutes`** does nothing if **`ScalperTesterWarmupM5Bars = 0`**.

4. **Journal vs AURUM**  
   Ground truth for a backtest is **`FORGE_journal_<SYM>_tester.db`** under the active **`Tester/Agent-…/MQL5/Files/`**. Query **`SIGNALS`** with **`ORDER BY time DESC`**. Compare to **`forge_signals`** **`journal_source='tester'`**; if **`MAX(id)`** frozen while journal **`COUNT(*)`** rises, fix BRIDGE discovery or keep BRIDGE running.

**Deliverables from the assistant:**

1. Confirm or add **`WriteMarketData()`** immediately after **`scalper_entry.json`** write in **`FORGE.mq5`**; grep **`_check_forge_scalper_entry`** for assumptions.  
2. Short **decision table**: symptom → file → fix.  
3. **SQL** for **`system_events`** + **`forge_signals`** + optional raw **`SIGNALS`** journal.  
4. **Ops checklist:** `make forge-recompile`, **`VERSION`** bump, reattach EA, ensure BRIDGE process up, **`PRAGMA busy_timeout`** if DB locked.

---

## Addendum — paste into Warp.ai (no_setup + what we changed)

**Interpreting `FORGE SCALPER: no setup` (log hint lines)**  
`direction` stayed empty after both **BB bounce** and **BB breakout** branches. The hint line is **diagnostic only**: `bounce_armed=true` means *M5 ADX < bounce cap* and bounce is enabled; **`sell_zone=true`** only means price is in the **upper-band proximity envelope** — **not** that all bounce SELL predicates passed.

**Very common blockers when `sell_zone=true` but still `no_setup`:**

1. **`bounce_htf_bias` (recommended over legacy H1-only)** — `LEGACY` uses `bounce_require_h1_direction` + optional `bounce_block_htf_trend_align`. **`BALANCED`**: bounce BUY unless **(H1 bear AND M15 bear)**; bounce SELL unless **(H1 bull AND M15 bull)**. **`STRICT`**: bounce BUY only if **neither** TF is bear; bounce SELL only if **neither** TF is bull (fewest fades against HTF). When `bounce_htf_bias` is **not** `LEGACY`, the code uses `bounce_tf_*_ok` instead of plain `h1_ok_*` for bounce legs; set **`bounce_require_h1_direction: 0`** to avoid double-filtering.

2. **`bounce_require_h1_direction` (JSON `1`, LEGACY only)** — Strict H1 requires **`h1_ok_sell` ⇒ H1 bear** for bounce SELL and **`h1_ok_buy` ⇒ H1 bull** for bounce BUY. **`h1_flat` satisfies neither** → both sides off in chop. With `bounce_htf_bias` **STRICT**/`BALANCED` and `bounce_require_h1_direction: 0`, HTF gating is **H1+M15 combined** instead.

3. **`bounce_block_htf_trend_align` (LEGACY only)** — When `bounce_htf_bias` is **LEGACY**, blocks bounce SELL when **H1 bull and M15 bull** (and mirror for BUY). Ignored when using **BALANCED**/**STRICT** (use those modes instead).

4. **Reclaim / pattern / bar-0 / liquidity** — `sell_reclaim`, rejection/pattern score, `bounce_require_bar0_confirm`, `bounce_require_liquidity_zone` (live), fib/VWAP bias, RSI divergence — any **false** kills the bounce leg.

5. **Breakout in `DUAL`** — Needs **ADX ≥ breakout min**, **close beyond band + buffer**, **M5/M15 trend alignment**, H1/H4 gates, etc. **Range ADX ~24** often **below** what a strong breakout needs; **price in sell zone** usually means **not** a lower-band breakdown → **SELL breakout** unlikely.

6. **`NativeScalperRegimeGate` / `NativeScalperH4Align` / M1 mode** — Apply **after** a direction is chosen; they do not produce `no_setup` (they produce other `gate_reason`s). **`no_setup` is strictly “no branch set `direction`”.**

**Repo changes that **reduce** or **reshape** fills (tell Warp to treat these as first suspects when trade count drops to ~0):**

| Change | Effect |
|--------|--------|
| **`bounce_htf_bias` STRICT/BALANCED** | Combines **H1 + M15** for bounce direction: fewer counter-trend fades than permissive legacy; **STRICT** is the tightest. |
| **`bounce_block_htf_trend_align`** | Legacy only: HTF dual-bull/bear block when `bounce_htf_bias` is **LEGACY**. |
| **`bounce_respect_adx_max_in_tester` / `bounce_respect_h1_filter_in_tester`** | Tester no longer uses legacy “infinite ADX bounce” / H1 bypass unless you turn flags off. |
| **Stricter H1 interpretation** (tester parity fix) | Live already enforced strict H1; tester now can match. |
| **`bounce_require_h1_direction: 1`** (LEGACY) | Bounce buy only H1 bull; bounce sell only H1 bear — **no bounce when H1 flat** unless using dual-TF bias with this off. |
| **Staged entry (`lot_sizing`)** | First bar opens probe only; does **not** remove `TAKEN` signals if a setup fires — affects **leg count**, not the presence of `no_setup`. |
| **RSI bands near 50** in `bb_bounce` | Fades are **permissive** on RSI but **reclaim/H1/HTF** still dominate. |

**What Warp should test** — Given a log snapshot with **`sell_zone=true`**, **`adx_regime=range`**, **`rsi~53`**: reconstruct **H1/M15 bull/bear/flat** from logged `h1_trend_strength` / `m15_trend_strength`. Under **`bounce_htf_bias: STRICT`**, bounce SELL needs **neither** TF bullish; if either is bull, SELL bounce is blocked. Confirm **`sell_reclaim`** and other gates.

---

## Repo pointers (for humans)

| Artifact | Location |
|----------|----------|
| EA | `ea/FORGE.mq5` — `ForgeNativeScalperWarmupOk`, `CheckNativeScalperSetups`, `ManageStagedNativeLegs`, `WriteMarketData` after `scalper_entry.json` |
| BRIDGE native scalp intake | `python/bridge.py` — `_check_forge_scalper_entry` |
| Config | **`config/scalper_config.defaults.json`** (edit) → **`make scalper-env-sync`** → **`config/scalper_config.json`** (generated; FORGE/BRIDGE read this path in repo + Common Files). See **`docs/SCALPER_CONFIG_PIPELINE.md`**. **`make scalper-config-sync`** = copy-only to Wine Common. |
| **SCRIBE / Aurum DB** | **`python/data/aurum_intelligence.db`** (env **`SCRIBE_DB`**). Main event table for skips: **`forge_signals`**. |
| **FORGE journal (MT5 native)** | **`FORGE_journal_*.db`** under Wine: Tester `.../Tester/Agent-.../MQL5/Files/` and/or `.../Terminal/Common/Files/`. Table **`SIGNALS`**. |
| Journal + SCRIBE summary | `make journal-diagnose` |
| Live table watch | `make scribe-watch` (groups/closures/events) |
| **SKIP monitor (`forge_signals`)** | `make monitor-forge-skips` / `make monitor-forge-skips-watch` — `scripts/monitor_forge_skips.py` |
| **Backtest: zero trades (prompt)** | **`docs/FORGE_BACKTEST_NO_TRADES_FIX_PROMPT.md`** |
