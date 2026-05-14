# FORGE Entry Conditions — Codex Validation Review

**Date**: 2026-05-14  
**EA version**: FORGE v2.7.94 (`config/scalper_config.json:2`)  
**Reviewer**: Codex (automated, read-only except this report)  
**Methodology**: Every behavioral claim is cited with file:line. Active config = `config/scalper_config.json`; defaults baseline = `config/scalper_config.defaults.json`. UNVERIFIED = code not found.

## Validation Summary
- Gates checked: 103 EA-emitted SKIP codes (77 literal + 26 `Filter_*` runtime-constructed)
- PASS: 16  |  WARNING: 5  |  FAIL: 3  |  UNVERIFIED: 0
- Mandatory Check A — Dead `FORGE_*` env vars: **PASS**
- Mandatory Check B — Gate legend completeness: **PASS**
- Mandatory Check C — Sync mapping ↔ `.env.example` parity: **FAIL** → **RESOLVED 2026-05-14** (31 missing keys backfilled at `.env.example:1924-1971`; re-audit: 0 sync→doc gaps; `make scalper-env-sync` clean with 210 overrides)
- Mandatory Check D — `scribe.py` placeholder/column count: **PASS**

### Resolution Log (post-review fixes, 2026-05-14)
- **FAIL 1 — defaults JSON missing v2.7.86-v2.7.94 knobs**: RESOLVED. Added 16 `safety` keys (UMCG/CVCSM/bb_breakout_min_break*) and 14 `composites` keys (bb_exhaustion_reversal*) to `config/scalper_config.defaults.json`. Verified: `safety` 181 keys, `composites` 30 keys; all 30 v2.7.86-v2.7.94 keys present.
- **FAIL 2 — 31 sync-mapped keys missing from `.env.example`**: RESOLVED. Added backfill block at `.env.example:1924-1971` covering BREAKOUT_BUY_SCORE_VELOCITY (2), BB_PULLBACK_BUY velocity (2), CONVICTION_DECAY (7), REVERSE_SELL_IN_BULL (10), GRINDING_SELL (10). Re-audit reports 0 missing.
- **FAIL 3 — PEMCG architecture stale line cites**: RESOLVED (pre-fix). `docs/FORGE_PEMCG_ARCHITECTURE.md` §3 cites refreshed to UMCG `12456-12492`, CVCSM state `6725-6777` + enforcement `12472-12482`, Layer 3 `12494-12624`.

## Mandatory Check A — Dead `FORGE_*` Env Vars
**Status**: PASS

| Check | Evidence | Status | Notes |
|---|---|---:|---|
| `.env` `FORGE_*` keys | 366 active `FORGE_*` keys enumerated from `.env`; all either map in `scripts/sync_scalper_config_from_env.py` or are whitelisted. The whitelist currently contains `FORGE_SCALPER_MODE` at `tests/api/test_forge_27x_gates.py:323-325`. | PASS | No unmapped/unwhitelisted active `FORGE_*` key found. |
| Lowercase config-looking keys | No lowercase config-looking keys found. Non-`FORGE_` uppercase session/diagnostic keys are present, e.g. `SESSION_ASIAN_START` in `.env`, but they are not lowercase bypasses. | PASS | The required lowercase bypass class was empty. |

## Mandatory Check B — Gate Legend Completeness
**Status**: PASS

| EA gate class | Evidence | Status | Notes |
|---|---|---:|---|
| Literal SKIP codes | `JournalRecordSignal("SKIP", "...")` literals in `ea/FORGE.mq5` produced 77 codes. | PASS | All matched `config/gate_legend.json` or a `_patterns` wildcard. |
| Runtime-constructed `Filter_*` codes | `Filter_AdxFloor`, `Filter_Cooldown`, and `Filter_M15TrendAligned` setup-lower arguments produced 26 additional codes per the skill rule. | PASS | All matched `config/gate_legend.json` or a `_patterns` wildcard. |
| New v2.7.93 side gates | `bb_breakout_buy_below_band` is emitted at `ea/FORGE.mq5:10813`; legend entry exists at `config/gate_legend.json:213-217`. `bb_breakout_sell_above_band` is emitted at `ea/FORGE.mq5:11174`; legend entry exists at `config/gate_legend.json:218-222`. | PASS | Required new codes are present. |
| Existing PEMCG/CVCSM gates | `pemcg_buy_reversal_block` / `pemcg_sell_reversal_block` are assigned at `ea/FORGE.mq5:12466-12470`; `cvcsm_cooldown_block_buy` / `_sell` are assigned at `ea/FORGE.mq5:12472-12477`. Legend entries exist at `config/gate_legend.json:543-560`. | PASS | See warning below for stale default text in legend explanations. |

## Mandatory Check C — Sync Mapping ↔ `.env.example` Parity
**Status**: FAIL

| Check | Evidence | Status | Notes |
|---|---|---:|---|
| Sync mappings missing from `.env.example` | The sync script maps 604 `FORGE_*` keys; `.env.example` documents 578. 31 mapped keys have no `# FORGE_...=` or `FORGE_...=` line. Examples: `FORGE_GATE_BB_PULLBACK_BUY_BLOCK_ON_FALLING_VELOCITY`, `FORGE_GATE_BREAKOUT_BUY_SCORE_VELOCITY_THRESHOLD`, `FORGE_SETUP_GRINDING_SELL_ENABLED`, `FORGE_SETUP_REVERSE_SELL_IN_BULL_ENABLED`, and `FORGE_TIMING_REVERSE_SELL_IN_BULL_COOLDOWN_SEC` are mapped in `scripts/sync_scalper_config_from_env.py` but absent from `.env.example`. | FAIL | Operators cannot discover these knobs from `.env.example`. |
| `.env.example` keys without sync mapping | `.env.example` documents `FORGE_MAGIC_NUMBER` / `FORGE_MAGIC_MAX` at `.env.example:70-74`, `FORGE_SCALPER_MODE` at `.env.example:198-203`, and queue knobs at `.env.example:1138-1142`; these are not sync mappings. | WARNING | They are consumed directly by Python/MT5 paths: magic in `python/bridge.py:121-122`, `python/reconciler.py:41-42`, `python/athena_api.py:545`; scalper mode in `python/bridge.py:159`; queue knobs in `python/bridge.py:330-331`. |

## Mandatory Check D — `forge_signals` Placeholder Count
**Status**: PASS

| Check | Evidence | Status | Notes |
|---|---|---:|---|
| INSERT column count vs placeholders | `python/scribe.py` inserts `forge_signals` columns at `python/scribe.py:1269-1299`; placeholder expression is `41 + 24 + 45` at `python/scribe.py:1300-1303`. Count is 110 columns and 110 placeholders. | PASS | No `106 values for 110 columns` regression found. |
| v2.7.45/v2.7.47 columns | `killzone`, `minutes_into_kz`, `htf_h1_strong`, `intraday_label`, and `intraday_counter_htf` are selected at `python/scribe.py:1202-1206`, indexed at `python/scribe.py:1244-1250`, and inserted at `python/scribe.py:1276-1278`. | PASS | Column-index comments match current layout. |

## Section 1 — PEMCG / UMCG / CVCSM / Layer-3 Wiring

| Knob | Struct field | EA default | JSON loader | Sync mapping | `.env` | `.env.example` | Active config | Status |
|---|---|---|---|---|---|---|---|---:|
| `umcg_buy_block_threshold` | `ea/FORGE.mq5:1248` | `5` at `ea/FORGE.mq5:4472` | `ea/FORGE.mq5:5412` | `scripts/sync_scalper_config_from_env.py:209` | `.env:585` | `.env.example:1867` | `config/scalper_config.json:378` | PASS |
| `umcg_sell_block_threshold` | `ea/FORGE.mq5:1249` | `5` at `ea/FORGE.mq5:4473` | `ea/FORGE.mq5:5413` | `scripts/sync_scalper_config_from_env.py:210` | `.env:586` | `.env.example:1868` | `config/scalper_config.json:379` | PASS |
| `umcg_pemcg_rsi_overbought` | `ea/FORGE.mq5:1250` | `65` at `ea/FORGE.mq5:4474` | `ea/FORGE.mq5:5414` | `scripts/sync_scalper_config_from_env.py:211` | `.env:591` | `.env.example:1869` | `config/scalper_config.json:380` | PASS |
| `umcg_pemcg_rsi_oversold` | `ea/FORGE.mq5:1251` | `35` at `ea/FORGE.mq5:4475` | `ea/FORGE.mq5:5415` | `scripts/sync_scalper_config_from_env.py:212` | `.env:592` | `.env.example:1870` | `config/scalper_config.json:381` | PASS |
| `umcg_pemcg_bb_dist_atr_threshold` | `ea/FORGE.mq5:1254` | `0.3` at `ea/FORGE.mq5:4478` | `ea/FORGE.mq5:5418` | `scripts/sync_scalper_config_from_env.py:215` | `.env:595` | `.env.example:1873` | `config/scalper_config.json:384` | PASS |
| `bb_exhaustion_reversal_lot_amplifier` | `ea/FORGE.mq5:1284` | `1.5` at `ea/FORGE.mq5:4499` | `ea/FORGE.mq5:5434` | `scripts/sync_scalper_config_from_env.py:231` | `.env:615` | `.env.example:1896` | `config/scalper_config.json:535` | WARNING |
| `bb_exhaustion_reversal_high_conviction_warnings` | `ea/FORGE.mq5:1285` | `6` at `ea/FORGE.mq5:4500` | `ea/FORGE.mq5:5435` | `scripts/sync_scalper_config_from_env.py:232` | `.env:616` | `.env.example:1897` | `config/scalper_config.json:536` | PASS |
| `bb_exhaustion_reversal_high_conviction_lot_factor` | `ea/FORGE.mq5:1286` | `2.0` at `ea/FORGE.mq5:4501` | `ea/FORGE.mq5:5436` | `scripts/sync_scalper_config_from_env.py:233` | `.env:617` | `.env.example:1898` | `config/scalper_config.json:537` | PASS |
| `bb_exhaustion_reversal_legs_high_conviction` | `ea/FORGE.mq5:1287` | `4` at `ea/FORGE.mq5:4502` | `ea/FORGE.mq5:5437` | `scripts/sync_scalper_config_from_env.py:234` | `.env:618` | `.env.example:1899` | `config/scalper_config.json:538` | WARNING |
| `bb_exhaustion_reversal_cooldown_sec` | `ea/FORGE.mq5:1274` | `0` at `ea/FORGE.mq5:4496` | `ea/FORGE.mq5:5431` | `scripts/sync_scalper_config_from_env.py:228` | `.env:608` | `.env.example:1889` | `config/scalper_config.json:533` | WARNING |
| `bb_exhaustion_reversal_max_adx` | `ea/FORGE.mq5:1292` | `35` at `ea/FORGE.mq5:4503` | `ea/FORGE.mq5:5438` | `scripts/sync_scalper_config_from_env.py:236` | `.env:623` | `.env.example:1904` | `config/scalper_config.json:539` | PASS |
| `bb_exhaustion_reversal_max_prev_bar_range_atr_mult` | `ea/FORGE.mq5:1299` | `2.0` at `ea/FORGE.mq5:4504` | `ea/FORGE.mq5:5439` | `scripts/sync_scalper_config_from_env.py:238` | `.env:630` | `.env.example:1908` | `config/scalper_config.json:540` | PASS |
| `bb_breakout_min_breakout_atr_mult` | `ea/FORGE.mq5:1054` | `0.1` at `ea/FORGE.mq5:4253` | `ea/FORGE.mq5:5108` | `scripts/sync_scalper_config_from_env.py:153` | `.env:636` | `.env.example:1913` | `config/scalper_config.json:362` | PASS |
| `bb_breakout_min_breakdown_atr_mult` | `ea/FORGE.mq5:1055` | `0.1` at `ea/FORGE.mq5:4254` | `ea/FORGE.mq5:5109` | `scripts/sync_scalper_config_from_env.py:154` | `.env:637` | `.env.example:1914` | `config/scalper_config.json:363` | PASS |

Warnings in this table are documentation/default-text drift only: the executable defaults and active config are wired.

## Section 2 — Layer-3 Trigger Path

| Check | Evidence | Status | Notes |
|---|---|---:|---|
| SELL fires from BUY-trap PEMCG | SELL reversal requires `g_pemcg_buy_warning_count >= g_sc.bb_exhaustion_reversal_min_warnings` at `ea/FORGE.mq5:12517-12519`. | PASS | Matches architecture intent. |
| SELL v2.7.90 directional opposite-side gate | SELL path blocks only when RSI is oversold and price is near BB lower: `ea/FORGE.mq5:12519-12520`. | PASS | Uses `umcg_pemcg_rsi_oversold` and `umcg_pemcg_bb_dist_atr_threshold`. |
| SELL v2.7.92 ADX gate | SELL path requires disabled gate or `m5_adx < bb_exhaustion_reversal_max_adx`: `ea/FORGE.mq5:12521-12522`. | PASS | Active config is 35 at `config/scalper_config.json:539`. |
| SELL v2.7.94 WRB gate | `_wrb_block` is computed from prior M5 range at `ea/FORGE.mq5:12513-12516`; SELL requires `!_wrb_block` at `ea/FORGE.mq5:12523`. | PASS | Active config is 2.0 at `config/scalper_config.json:540`. |
| BUY mirror | BUY path requires `g_pemcg_sell_warning_count`, overbought + BB upper opposite-side check, ADX ceiling, `!_wrb_block`, and open BUY CVCSM state at `ea/FORGE.mq5:12575-12582`. | PASS | Mirrors SELL path. |
| Conviction lot and leg use | Lot pin uses amplifier/high factor at `ea/FORGE.mq5:13181-13194`; high-conviction leg override uses `bb_exhaustion_reversal_legs_high_conviction` at `ea/FORGE.mq5:13259-13264`. | PASS | Executable logic uses current knobs. |

## Section 3 — Architecture Doc Cross-Check

| Claim | Doc cite | Current code cite | Status | Notes |
|---|---|---|---:|---|
| §3.1 UMCG line cite | `docs/FORGE_PEMCG_ARCHITECTURE.md:67-70` says `ea/FORGE.mq5:12362-12404`. | Current UMCG enforcement is `ea/FORGE.mq5:12456-12492`. | FAIL | Behavior matches, file:line cite is stale. |
| §3.2 CVCSM line cite | `docs/FORGE_PEMCG_ARCHITECTURE.md:90-92` says state update `6668-6709` and enforcement `12378-12384`. | State update is `ea/FORGE.mq5:6725-6777`; enforcement is `ea/FORGE.mq5:12472-12482`. | FAIL | Behavior matches, file:line cite is stale. |
| §3.3 Layer-3 line cite | `docs/FORGE_PEMCG_ARCHITECTURE.md:130-132` says SELL `12427-12477`, BUY `12480-12557`. | SELL block is `ea/FORGE.mq5:12494-12568`; BUY mirror is `ea/FORGE.mq5:12570-12624`. | FAIL | Behavior matches, file:line cite is stale. |
| §4 side-gate line cite | `docs/FORGE_PEMCG_ARCHITECTURE.md:173-176` cites BUY `10781-10798` and SELL `11156-11173`. | BUY gate is `ea/FORGE.mq5:10801-10817`; SELL gate is `ea/FORGE.mq5:11164-11178`. | WARNING | Outside requested §3, but the new source-of-truth doc has stale cites here too. |

## Section 4 — Configuration Pipeline

| Check | Evidence | Status | Notes |
|---|---|---:|---|
| Active config contains all v2.7.86-2.7.94 focus knobs | Active keys are present at `config/scalper_config.json:362-363`, `config/scalper_config.json:378-384`, and `config/scalper_config.json:533-540`. | PASS | Runtime active config is complete. |
| Sync script maps all focus knobs | Mappings exist at `scripts/sync_scalper_config_from_env.py:153-154`, `scripts/sync_scalper_config_from_env.py:209-215`, and `scripts/sync_scalper_config_from_env.py:228-238`. | PASS | Env-to-active sync path is present. |
| `.env` has active overrides for all focus knobs | Overrides exist at `.env:585-595`, `.env:608-630`, and `.env:636-637`. | PASS | Active config can be regenerated from current `.env`. |
| Defaults JSON contains the focus defaults | `config/scalper_config.defaults.json` safety section spans `config/scalper_config.defaults.json:184-349`, composites section spans `config/scalper_config.defaults.json:390-410`, and timing section spans `config/scalper_config.defaults.json:551-566`; the focus keys are absent from the defaults file. | FAIL | A clean sync without `.env` overrides would not carry these defaults from the defaults JSON. |
| `.env.example` values match current defaults | `.env.example:1889` still documents `FORGE_TIMING_BB_EXHAUSTION_REVERSAL_COOLDOWN_SEC=1800`, while EA default is 0 at `ea/FORGE.mq5:4496`; `.env.example:1896` documents lot amplifier 1.0 while EA default is 1.5 at `ea/FORGE.mq5:4499`; `.env.example:1899` documents high-conviction legs 3 while EA default is 4 at `ea/FORGE.mq5:4502`. | WARNING | Presence parity passes for these keys, but the sample values are stale. |
| Struct/default comments match executable defaults | Struct comments still say UMCG thresholds default 3 and RSI 70/30 at `ea/FORGE.mq5:1248-1251`; executable defaults are 5 and 65/35 at `ea/FORGE.mq5:4472-4475`. Comments still say cooldown 1800, lot amp 1.0, legs 3 at `ea/FORGE.mq5:1274` and `ea/FORGE.mq5:1284-1287`; executable defaults are 0, 1.5, 4 at `ea/FORGE.mq5:4496-4502`. | WARNING | Code is correct; inline documentation is stale. |
| Gate legend default text | Legend explanations for `pemcg_buy_reversal_block` and `pemcg_sell_reversal_block` still say threshold default 3 at `config/gate_legend.json:543-550`; current defaults are 5 at `ea/FORGE.mq5:4472-4473`. | WARNING | Monitoring explanation text can mislead operators. |

## Section 5 — PEMCG Composite

| Atom / layer | Evidence | Status | Notes |
|---|---|---:|---|
| PEMCG computes two 0-7 counts | Computation resets and fills `buy_w` / `sell_w`, then assigns `g_pemcg_buy_warning_count` and `g_pemcg_sell_warning_count` at `ea/FORGE.mq5:6699-6719`. | PASS | Matches `docs/FORGE_PEMCG_ARCHITECTURE.md:27-35`. |
| A5 absolute BB-distance fix | Absolute BB upper/lower distance is computed at `ea/FORGE.mq5:6689-6696`; BUY A5 and SELL A5 consume it at `ea/FORGE.mq5:6705` and `ea/FORGE.mq5:6716`. | PASS | v2.7.87 sign bug is fixed in code. |
| CVCSM bar-close state update | BUY state transitions are at `ea/FORGE.mq5:6733-6753`; SELL mirror is at `ea/FORGE.mq5:6756-6776`. | PASS | Matches architecture behavior, not architecture line cites. |
| Pending-order cancellation on UMCG flip | FORGE-owned pending orders are scanned and cancelled when matching-direction PEMCG warnings exceed threshold at `ea/FORGE.mq5:6779-6809`. | PASS | Additional protection is wired. |

## Section 6 — Dashboard / API Consistency

| Check | dashboard:line | api:line | Status | Notes |
|---|---|---|---:|---|
| `/api/backtest/run/:id` run isolation | UI selects `/api/backtest/run/${btSelRun}` at `dashboard/app.js:644-649`. | API filters meta, signals, trades, gates, taken rows, and P&L curve by `aurum_run_id=?` at `python/athena_api.py:1731-1736`, `python/athena_api.py:1740-1750`, `python/athena_api.py:1761-1766`, `python/athena_api.py:1783-1788`, `python/athena_api.py:1794-1801`, `python/athena_api.py:1805-1809`, and `python/athena_api.py:1960-1964`. | PASS | No cross-run leakage found in these queries. |
| Run ID guard and loading state | `dashboard/app.js:1522-1528` shows Loading when selected run differs from loaded detail and renders detail only when IDs match. | API returns `meta` at `python/athena_api.py:1971-1977`; meta comes from the selected `aurum_run_id` query at `python/athena_api.py:1731-1736`. | PASS | Guard is present. |
| TAKEN entry fields | UI reads `trade_outcome`, `pnl`, `cascade_pnl`, `legs`, and `lot_per_leg` at `dashboard/app.js:1720-1770`. | API emits those fields at `python/athena_api.py:1947-1957`. | PASS | Field names match. |
| `lot_per_leg` source | UI renders legs × lot at `dashboard/app.js:1743-1747`. | API selects `ROUND(volume,3) as volume` at `python/athena_api.py:1805-1807` and derives `lot_per_leg` at `python/athena_api.py:1932-1934`. | PASS | Prior missing-volume bug is not present. |
| Legs count | UI renders `legs` at `dashboard/app.js:1743-1747`. | API counts `|TP1` markers from group trades with SL/nonzero fallback at `python/athena_api.py:1926-1930`. | PASS | Matches required source. |
| Cascade P&L | UI tooltip includes cascade split at `dashboard/app.js:1763-1770`. | API maps cascade offsets `20000..20009` at `python/athena_api.py:1853-1866`, sums cascade P&L at `python/athena_api.py:1911-1915`, and emits `cascade_pnl` at `python/athena_api.py:1951-1952`. | PASS | Cascade contribution is included. |
| Live session/killzone authority | Dashboard prefers EA-backed `D.session || D.session_local_check` and `D.killzone || D.killzone_local_check` at `dashboard/app.js:825-852`. | API returns local-check fields at `python/athena_api.py:557-568`. | PASS | UI/API names align. |

## Section 7 — scribe.py / regime.py / schemas Cross-Check

| Check | Evidence | Status | Notes |
|---|---|---:|---|
| `forge_signals` schema includes recent columns | Base CREATE TABLE includes `killzone`, `minutes_into_kz`, and RegimeState trio at `python/scribe.py:149-154`; migration table create also includes them at `python/scribe.py:599-611`; ALTER migrations exist at `python/scribe.py:670-690`. | PASS | Schema/migration path is complete. |
| MACD/M15/lot migrations | ALTER migrations for `macd_histogram`, `m15_adx`, and `lot_factor` are at `python/scribe.py:658-669`. | PASS | Known historical gap remains covered. |
| Regime label compatibility | `forge_signals` persists `regime_label` and `regime_confidence` in the INSERT column list at `python/scribe.py:1273-1275`; the EA passes those as journal fields through `JournalRecordSignal` calls including `ea/FORGE.mq5:12481-12482` and `ea/FORGE.mq5:12667-12669`. | PASS | No missing field found in the reviewed path. |

## Section 8 — Scripts / Tests Consistency

| Check | Evidence | Status | Notes |
|---|---|---:|---|
| Tests reference new gate/config names | `rg` across `tests/` found no references to `bb_breakout_buy_below_band`, `bb_breakout_sell_above_band`, `pemcg_*`, `cvcsm_*`, `umcg_*`, or `bb_exhaustion_reversal*`. | PASS | No stale test reference was found for the focus stack. |
| Env dead-var guard exists | `tests/api/test_forge_27x_gates.py:328-343` asserts active `.env` `FORGE_*` vars must map or be whitelisted. | PASS | This protects Mandatory Check A. |
| Sync parity test coverage | No test was found that enforces Mandatory Check C’s `.env.example` documentation parity. | WARNING | The current 31 missing-doc failures can recur unless covered. |

## Issues Found (Consolidated)

| # | Severity | Section | Description | Action |
|---|---|---|---|---|
| 1 | FAIL | Config pipeline | `config/scalper_config.defaults.json` does not contain the 14 focus v2.7.86-v2.7.94 knobs, while active config does. | Add defaults under the same sections used by sync mappings: safety/composites/timing. |
| 2 | FAIL | Mandatory C | 31 sync-mapped `FORGE_*` variables are missing from `.env.example`. | Add discoverability lines to `.env.example` for every sync mapping. |
| 3 | FAIL | Architecture doc | `docs/FORGE_PEMCG_ARCHITECTURE.md` §3 file:line cites do not match current `ea/FORGE.mq5`. | Refresh cite ranges for UMCG, CVCSM, and Layer 3. |
| 4 | WARNING | Docs/comments | Struct comments, `.env.example`, and gate legend text contain stale default values for several v2.7.86-v2.7.94 knobs. | Update text to match executable defaults. |
| 5 | WARNING | Tests | No test enforces sync mapping ↔ `.env.example` parity. | Add a test based on the skill’s Mandatory Check C one-liner. |

## Recommendations & Proposed Fixes

This was requested as read-only validation, so no repo files were changed except this report. The fixes are local config/docs/test maintenance, not MQL5 execution-pattern changes.

1. Add the missing focus keys to `config/scalper_config.defaults.json` under the sync-mapped sections shown in `scripts/sync_scalper_config_from_env.py:153-154`, `scripts/sync_scalper_config_from_env.py:209-215`, and `scripts/sync_scalper_config_from_env.py:228-238`.
2. Add `.env.example` entries for the 31 sync-mapped but undocumented keys found by Mandatory Check C.
3. Refresh `docs/FORGE_PEMCG_ARCHITECTURE.md` cite ranges to current code: UMCG `ea/FORGE.mq5:12456-12492`, CVCSM update `ea/FORGE.mq5:6725-6777`, CVCSM enforcement `ea/FORGE.mq5:12472-12482`, Layer-3 SELL `ea/FORGE.mq5:12494-12568`, Layer-3 BUY `ea/FORGE.mq5:12570-12624`.
4. Update stale default text at `ea/FORGE.mq5:1248-1251`, `ea/FORGE.mq5:1274`, `ea/FORGE.mq5:1284-1287`, `.env.example:1889`, `.env.example:1896`, `.env.example:1899`, and `config/gate_legend.json:543-550`.

## Overall Verdict

The executable v2.7.94 entry logic is wired correctly for the reviewed PEMCG/UMCG/CVCSM/Layer-3 stack: the PEMCG composite uses absolute BB distance, UMCG/CVCSM enforcement is present, Layer-3 has the v2.7.90 directional opposite-side checks, v2.7.92 ADX gate, and v2.7.94 WRB gate, and the new BB breakout side-gate codes are emitted and present in the legend.

The main risk is pipeline/documentation drift: the active runtime config is complete, but `scalper_config.defaults.json` lacks the new knobs, `.env.example` is missing 31 sync-mapped knobs and has stale sample values for three Layer-3 settings, and the newly created architecture doc’s §3 line citations are stale against current `ea/FORGE.mq5`.
