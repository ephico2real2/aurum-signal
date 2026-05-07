# FORGE — how it should work + cumulative changes (operator / assistant prompt)

**Use:** Copy everything **below** the horizontal rule into Warp, Cursor, or another assistant when you need full context on FORGE behavior, BRIDGE coupling, tester vs live, and what was added or fixed in recent work (through **2026-05-06** afternoon **US/Central**).

---

## Role of FORGE

FORGE is the **MetaTrader 5 Expert Advisor** (`ea/FORGE.mq5`). It is the execution engine on the chart. It does **not** use HTTP: it reads/writes **JSON files** in the MT5 file bus (Common Files and, for some tester paths, the agent-local `MQL5/Files` tree).

**Python stack (BRIDGE, ATHENA, SCRIBE)** polls those files, syncs journals to SQLite, and may send Telegram / AURUM context. FORGE must remain correct **even when BRIDGE is off** (e.g. Strategy Tester).

---

## Data flow (contract)

| Direction | File | Purpose |
|-----------|------|---------|
| BRIDGE → FORGE | `command.json` | Bracket commands: OPEN_GROUP, MODIFY_*, CLOSE_*, etc. |
| BRIDGE → FORGE | `config.json` | Thresholds, regime snapshot (`regime_*`), `effective_mode` / `scalper_mode` — **live** |
| FORGE → rest | `market_data.json` | Prices, indicators (H1/H4/M1/M5/M15/M30), **`open_positions[]`**, `pending_orders[]`, `forge_version`, optional **`strategy_tester`: true** |
| FORGE → rest | `scalper_entry.json` | Native scalper decision snapshot when FORGE opens (or attempts) a scalp group |
| FORGE → rest | `broker_info.json`, `mode_status.json` | Broker + mode telemetry |
| Shared | `scalper_config.json` | Hot-reload scalper rules (from repo via **`make scalper-env-sync`** / compile pipeline; see **`docs/SCALPER_CONFIG_PIPELINE.md`**) |
| FORGE only (MT5) | `FORGE_journal_<SYMBOL>.db` / `FORGE_journal_<SYMBOL>_tester.db` | SQLite journal: setup evaluations, skips, TAKEN |

**Critical ordering (live + BRIDGE):** After FORGE writes **`scalper_entry.json`**, **`market_data.json` must be refreshed immediately** (same tick/cycle) so **`open_positions[]`** includes the new **magic** before BRIDGE validates the entry. If `WriteMarketData()` ran only on `OnTimer`, BRIDGE could log **`no_mt5_exposure_for_magic`** / **`FORGE_SCALP_ENTRY_IGNORED`** despite successful orders. **Intended fix:** call **`WriteMarketData()`** right after **`WriteJsonFileDual("scalper_entry.json", …)`** on the native entry path.

---

## Modes and native scalper path

- **Inputs:** `InputMode` (`OFF|WATCH|SIGNAL|SCALPER|HYBRID`), `ScalperMode` (`NONE|BB_BOUNCE|BB_BREAKOUT|DUAL`).
- **`OnTick`:** Native checks run when scalper mode is not `NONE` and `InputMode` is not `WATCH`/`OFF` (exact branching as in current `FORGE.mq5`).
- **Path:** `CheckNativeScalperSetups()` → gates (session, spread, groups, cooldowns, warmup, BB/breakout logic, R:R, optional M1/regime gates) → **leg count resolution** → market open + group registration → optional **staged** adds via `ManageStagedNativeLegs()`.

---

## Strategy Tester vs live (must not be confused)

When **`MQLInfoInteger(MQL_TESTER) != 0`**:

- **`config.json`** must **not** override EA **`InputMode`** / **`ScalperMode`** / **`regime_*`** from stale BRIDGE files (tester uses **Inputs** as source of truth for mode).
- **Live-only gates** are typically skipped or relaxed so backtests are not empty: e.g. London/NY session window, max spread, session trade cap, loss cooldown (per current EA logic).
- **`market_data.json`** should include **`"strategy_tester": true`** so Python stale-age logic uses **file mtime** instead of absurd simulated-clock ages (**circuit breaker / “MT5 stale”** false positives).

**Symptom checklist — zero tester trades:** `InputMode` not `SCALPER`/`HYBRID`/`SIGNAL`, **`ScalperMode = NONE`**, warmup stuck, strict JSON (`bounce_respect_*_in_tester`), R:R, ADX hysteresis stuck in trend regime — see **`docs/FORGE_BACKTEST_NO_TRADES_FIX_PROMPT.md`**.

---

## Warmup (`ForgeNativeScalperWarmupOk`) — deliberate delay before first trade

**Plan / intent (both environments):** FORGE must **not** take native scalper trades until the chart has **sufficient history and stable indicator buffers**. That is an intentional **startup delay**, not a bug: entries are blocked so RSI/EMA/ATR/BB/MACD/etc. and multi-timeframe alignment reflect the real market instead of partially filled series right after attach or backtest start.

**What must pass before any entry (shared):**

- **Minimum bars + synchronization** on M5/M15/M30/H1/H4 (and M1 when M1 mode is used): `SERIES_SYNCHRONIZED`, successful `CopyBuffer` probes on the handles FORGE uses in the check path.

**Environment-specific extra waits (on top of bar/buffer readiness):**

| Environment | Extra delay (inputs) | Role |
|-------------|----------------------|------|
| **Live** | `ScalperLiveWarmupM15Bars` | Require **N completed M15 bars** after init before entries — aligns with “real” session pace so the first signal is not on the first few ticks of attach. |
| **Live** | `ScalperWarmupSeconds` | Optional **wall-clock** (or broker-time) pause **after** bar rules pass — extra safety for feed/indicator settle. |
| **Strategy Tester** | `ScalperTesterWarmupM5Bars` | Optional **M5 bar rollovers** in **simulated** time ( **`0` = off** for that block). |
| **Strategy Tester** | `ScalperTesterWarmupSimCapMinutes` | When M5 bars **> 0**, cap how long the tester waits in **simulated minutes** before waiving the remaining M5 rollover wait — avoids backtests stalling forever while still enforcing some “market rolled forward” discipline. |
| **Strategy Tester** | `ScalperWarmupSeconds` | Treated as **simulated** seconds in tester **after** the above — same knob as live, different clock semantics. |

**Operational:** While warmup fails, every tick logs **`FORGE SCALPER: skip gate=warmup reason=...`** with a concrete sub-reason (e.g. bar count, buffer copy, rollover count). Fix that reason first; no other gate matters until warmup passes.

---

## Leg count, envelope, and staging (post–“simple ScalperTrades” era)

**Older committed baseline** used **`int n = ScalperTrades`** and opened all legs in one loop.

**Current intended design** (in evolved `FORGE.mq5`):

1. **Base count** from `lot_sizing` / config: `num_trades`, `min_num_trades`, `max_num_trades`, merged with inputs **`ScalperMinTrades`** / **`ScalperMaxTrades`** when set.
2. **`ForgeResolveNumTrades(base_n, env_lo, env_hi, env_active, …)`** clamps into **[min,max]** and adjusts for drawdown, trend lot multiplier, regime label, setup type (still **≥ 1** legs after clamp).
3. **Staging:** When `staged_entry_enabled` or `native_force_staged_scale_in` and **`n > 1`**, FORGE may open only **`staged_initial_legs`** first, then add legs on timer + favorable movement (`ManageStagedNativeLegs`). JSON and logs should expose **`staged_entry`**, **`staged_legs_pending`**, **`num_trades`**.

**BRIDGE implication:** staging makes **single-leg-first** opens common — **market_data sync after `scalper_entry.json`** matters more, not less.

---

## Journal and SCRIBE

- FORGE writes **`SIGNALS`** (and **`TRADES`** import, **`TESTER_RUNS`** in tester DB) to SQLite under MT5.
- **Tester path:** typically **`FORGE_journal_<SYMBOL>_tester.db`** under the **agent** `MQL5/Files` tree (writable in sandbox).
- **Live path:** often Common Files **`FORGE_journal_<SYMBOL>.db`**.
- BRIDGE **`sync_forge_journal`** / **`sync_forge_journal_trades`** pushes into SCRIBE with **`journal_source`** = `live` | `tester`.
- **Idempotency:** inserts keyed to avoid duplicates under concurrent sync; DB-level `UNIQUE` index may still be TODO per changelog.
- **Queries:** use **`ORDER BY time DESC`** for “current simulated time”; do not rely on **`id`** alone vs wall/sim time.

---

## Regime, H1/H4/M1 gates

- **Phase C (v1.6.0 era):** optional **H4** alignment input; **`regime_*`** from `config.json` can block counter-trend entries when policy applies (**live**).
- **M1:** input **`NativeScalperM1Mode`** (`NONE|CONFIRM|TRIGGER`) — optional extra confirmation on execution TF.
- **Live H1 bias:** completed H1 bar (**shift 1**) is used where documented for setup/management; `WriteMarketData()` may still expose bar 0 for BRIDGE/UI — confirm in code for your build.

---

## Safety and high-vol behavior (config-driven)

Examples of keys in **`scalper_config.json`** / `.env` sync:

- **ADX hysteresis** (`adx_trend_enter` / `adx_trend_exit`): can block **BB_BOUNCE** while ADX says “trend”; default hysteresis was fixed when it **suppressed all bounces** in routine XAU ADX (see CHANGELOG **1.7.3**).
- **High-vol trend guard:** `high_vol_*` keys — can suppress bounces, tighten breakout alignment, widen breakout SL, adjust fast-lock in volatile regimes; **`high_vol_apply_in_tester`** controls tester parity.
- **Session skip flags:** `skip_london`, `skip_ny`, `skip_asian` (per-session independent gates).
- **Fast-lock / ratchet:** profit guards, spread-aware floors, SELL grace (`sell_loss_grace_*`).

---

## Versioning

- **`VERSION`** file at repo root drives FORGE **`FORGE_VERSION`** / `#property version` (via compile script) and stamps **`scalper_config.json`** **`version`** when synced.
- **`SYSTEM_VERSION`** / Python services may track the wider repo separately.
- **Drift check:** If **`CHANGELOG.md`** lags **`VERSION`**, treat **`VERSION`** + **`forge_version`** in `market_data.json` as ground truth for the running binary.

---

## Makefile / operator commands (typical)

- **`make forge-compile`** / **`make forge-recompile`** — stamp FORGE from **`VERSION`** and compile.
- **`make scalper-env-sync`** — regenerate **`scalper_config.json`** from defaults + `.env`.
- **`make journal-diagnose`** — discover journal DBs, counts, top skip reasons.
- **`make monitor-forge-skips`** — read-only skip analysis.

---

## Deep-dive docs (same repo)

- **`docs/WARP_FORGE_VERIFY_PROMPT.md`** — verification order, paths, staging, BRIDGE exposure.
- **`docs/FORGE_BACKTEST_NO_TRADES_FIX_PROMPT.md`** — zero-trade tester triage.
- **`docs/FORGE_TRADING_RULES.md`**, **`docs/DATA_CONTRACT.md`**, **`docs/FORGE_BRIDGE.md`**
- **`CHANGELOG.md`** — dated release notes (may lag **`VERSION`** on active branches).

---

## What was “added” in this thread’s scope (summary for assistants)

Not every item may be committed yet; verify in `git diff` / **`VERSION`**.

1. **Tester stabilization** — ignore stale `config.json` mode/regime in tester; relax live-only session/spread/caps; **`strategy_tester`** in `market_data.json`; mtime-based staleness in Python.
2. **command.json** — robust `action` parse; ignore non-FORGE actions; do not advance dedup on empty/partial reads.
3. **Warmup / startup delay (live + tester)** — intentional **no-trade window** until series + indicators are ready; **live** adds **`ScalperLiveWarmupM15Bars`** + **`ScalperWarmupSeconds`**; **tester** adds optional **`ScalperTesterWarmupM5Bars`**, **`ScalperTesterWarmupSimCapMinutes`** (when M5 bars > 0), and simulated **`ScalperWarmupSeconds`** so backtests don’t fire on uninitialized buffers or sit idle forever.
4. **Dynamic leg count** — `ForgeResolveNumTrades`, min/max envelope from JSON + inputs; cap 30 legs.
5. **Staged scale-in** — initial legs + timer/favorable adds; `native_force_staged_scale_in` option.
6. **BRIDGE race** — **`WriteMarketData()`** immediately after **`scalper_entry.json`** so **`open_positions`** matches new magics.
7. **Journal** — SQLite SIGNALS/TRADES/TESTER_RUNS; throttled skip spam; `DatabaseExecute` paths for tester; SCRIBE sync + **`journal_source`**; idempotency guards.
8. **Scalper config pipeline** — **`scalper_config.defaults.json`** as edit surface; **`docs/SCALPER_CONFIG_PIPELINE.md`**.
9. **Operational** — `journal-diagnose`, skip monitor scripts, ADX hysteresis default fix, session 24h / skip flags, high-vol and fast-lock tuning per CHANGELOG.
10. **iMACD buffer-2 bug fixed (v2.5.1)** — `ForgeNativeScalperWarmupOk` previously probed `CopyBuffer(h_macd, 2, ...)`. MT5's `iMACD` only has buffers 0 and 1; buffer 2 does not exist. `CopyBuffer` always returned `-1`, permanently blocking warmup with reason `m5_macd_buf` and producing zero TAKEN in every backtest. Probe removed from all MTF (M5/M15/M30) and H1 MACD handles. MACD histogram is display-only in `WriteMTFBlock()` which gracefully returns `0`.
11. **Warmup observability (v2.5.1)** — `mode_status.json` now emits `scalper_mode`, `warmup_ok`, `warmup_reason` every cycle. Warmup failures are also journaled as `SKIP|warmup_<reason>` (once per M5 bar) so blockers are visible in SQLite without MT5 Experts access. `TESTER_RUNS` now records `warmup_m5_bars` and `warmup_seconds`.
12. **Tester fast-start gate (v2.5.1)** — When `ScalperTesterWarmupM5Bars=0`, bar-count + `SERIES_SYNCHRONIZED` checks are now skipped (`do_bar_checks = false`); only `CopyBuffer` readiness probes remain. This lets the operator say "fire as soon as indicators are ready" without the 70-bar proxy gate blocking.
13. **Logic bug fixes (v2.5.1)** — `WriteBrokerInfo()` hardcoded version `"1.6.19"` → now uses `FORGE_VERSION`; `ManageStagedNativeLegs()` guard fixed to check both `staged_entry_enabled` and `native_force_staged_scale_in`; `InitScalperConfig()` fail-safe defaults relaxed (`high_vol_apply_in_tester=false`, `high_vol_disable_bounce=false`).
14. **Scalper config tester relaxations (v2.5.1)** — `scalper_config.defaults.json` changed: `bounce_respect_adx_max_in_tester`, `bounce_respect_h1_filter_in_tester`, `high_vol_apply_in_tester` all set to `0`. Regenerated via `make scalper-env-sync`.
15. **`docs/FORGE_BACKTEST_DIAGNOSTIC_COMMANDS.md`** — 11 numbered Python one-liners for remote warmup/mode/journal/rr_too_low diagnosis. Also added to `FORGE_BACKTEST_NO_TRADES_FIX_PROMPT.md` and `WARP_FORGE_VERIFY_PROMPT.md`.

---

**End of paste block.**
