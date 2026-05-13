# FORGE Entry Conditions — Codex Validation Review

**Date**: 2026-05-12  
**EA version**: FORGE v2.7.41 (from scalper_config.json)  
**Reviewer**: Codex (automated, read-only)  
**Methodology**: Every claim cited with file:line. UNVERIFIED = code not found. Active config = scalper_config.json (not defaults).

## Validation Summary
- Gates checked: 62 EA-emitted SKIP codes from `JournalRecordSignal("SKIP",...)`.
- PASS: 48  |  WARNING: 9  |  FAIL: 2  |  UNVERIFIED: 3
- Mandatory Check A (dead FORGE_* env vars): PASS
- Mandatory Check B (gate legend completeness): PASS
- Mandatory Check C (sync ↔ .env.example parity): PASS

## Section 1 — BB_BREAKOUT BUY Gates
| # | Gate | EA file:line | Config key=value (scalper_config.json) | Status | Notes |
|---|------|-------------|---------------------------------------|--------|-------|
| 1 | Previous close above upper BB | `ea/FORGE.mq5:7234-7237` | no config key | PASS | Implemented as `prev_close > m5_bb_u + breakout_buffer`. |
| 2 | RSI BUY floor | `ea/FORGE.mq5:7235-7237` | `bb_breakout.rsi_buy_min=40` at `config/scalper_config.json:36`; sync `FORGE_BREAKOUT_ADX_MIN`/RSI mappings include breakout keys at `scripts/sync_scalper_config_from_env.py:95-106`; `.env.example` documents breakout RSI keys at `.env.example:313-321` | PASS | `rsi_buy_min` is loaded from JSON at `ea/FORGE.mq5:3332`. |
| 3 | RSI BUY ceiling | `ea/FORGE.mq5:7257-7264` | `bb_breakout.rsi_buy_ceil=78` at `config/scalper_config.json:63`; mapping `FORGE_BREAKOUT_RSI_BUY_CEIL` at `scripts/sync_scalper_config_from_env.py:103`; `.env.example:313-314` | PASS | SKIP code is `entry_quality_rsi_buy_ceil`. |
| 4 | M5 bullish trend | `ea/FORGE.mq5:7218` and `ea/FORGE.mq5:7236-7237` | threshold from runtime `trend_thr_eff` | PASS | Exact threshold source is outside this section; gate expression is present. |
| 5 | M15 flat/bullish agreement | `ea/FORGE.mq5:7220-7224` and `ea/FORGE.mq5:7236-7237` | `bb_breakout.require_m15_agree=true` at `config/scalper_config.json:38` | PASS | BUY uses `m15_ok_buy`. |
| 6 | H1/H4 BUY alignment | `ea/FORGE.mq5:7225` and `ea/FORGE.mq5:7236-7237` | high-vol alignment keys at `config/scalper_config.json:195-201` | PASS | Doc says H1 not strongly bearish; EA also includes H4/high-vol alignment. |
| 7 | H1 DI BUY at weak ADX | `ea/FORGE.mq5:7267-7277` | `require_h1_di_buy=1`, `counter_buy_adx_threshold=28.0` at `config/scalper_config.json:74-75`; mapping at `scripts/sync_scalper_config_from_env.py:115` and `scripts/sync_scalper_config_from_env.py:133`; docs at `.env.example:335-357` | PASS | Gate applies only when `m5_adx < threshold`. |
| 8 | OsMA BUY Q0 | `ea/FORGE.mq5:7280-7299` | `require_macd_buy=1`, `macd_fast=3`, `macd_slow=10`, `macd_signal=16` at `config/scalper_config.json:91-94`; mapping at `scripts/sync_scalper_config_from_env.py:143-147`; docs at `.env.example:530-538` | PASS | Non-Q0 logs Q1/Q2/Q3 gate reasons. |
| 9 | Re-entry ATR extension | `ea/FORGE.mq5:8109-8117` and BUY log path `ea/FORGE.mq5:8129` | `max_reentry_atr_ext=2` at `config/scalper_config.json:86`; mapping at `scripts/sync_scalper_config_from_env.py:135`; docs at `.env.example:555-561` | PASS | Blocks entries too far from first entry. |

## Section 2 — BB_BREAKOUT SELL Gates
| # | Gate | EA file:line | Config key=value (scalper_config.json) | Status | Notes |
|---|------|-------------|---------------------------------------|--------|-------|
| 1 | Previous close below lower BB | `ea/FORGE.mq5:7463-7468` | no config key | PASS | Implemented as `prev_close < m5_bb_l - breakout_buffer`. |
| 2 | RSI SELL ceiling | `ea/FORGE.mq5:7467` | `bb_breakout.rsi_sell_max=60` at `config/scalper_config.json:37` | PASS | SELL only enters below ceiling. |
| 3 | RSI SELL floor | `ea/FORGE.mq5:7568-7581` | `rsi_sell_floor=33`, `rsi_sell_floor_weak_adx=36`, `adx_sell_floor_threshold=35` at `config/scalper_config.json:64-66`; mappings at `scripts/sync_scalper_config_from_env.py:104-106`; docs at `.env.example:315-323` | WARNING | Intent doc says `rsi_sell_floor=30` at `docs/FORGE_ENTRY_CONDITIONS.md:132`; active config is 33. Per repo instruction, doc drift is warning max. |
| 4 | ADX SELL floor | `ea/FORGE.mq5:7517-7522` | `adx_min_sell=25.0` at `config/scalper_config.json:72`; mapping at `scripts/sync_scalper_config_from_env.py:111`; docs at `.env.example:302-306` | PASS | SKIP code `entry_quality_adx_min_sell`. |
| 5 | ADX duration/spike gate | `ea/FORGE.mq5:7587-7599` | `adx_min_sell_lookback_bars=6` at `config/scalper_config.json:73`; mapping at `scripts/sync_scalper_config_from_env.py:113`; docs at `.env.example:329-334` | PASS | Skipped when crash-sell bypass is active. |
| 6 | ADX extreme SELL block | `ea/FORGE.mq5:7505-7515` | `breakout_adx_sell_block_threshold=55` at `config/scalper_config.json:258`; mapping at `scripts/sync_scalper_config_from_env.py:159`; docs at `.env.example:551-552` | PASS | Uses M15 ADX when available. |
| 7 | H1 DI SELL | `ea/FORGE.mq5:7533-7545` | `require_h1_di_sell=1` at `config/scalper_config.json:76`; mapping at `scripts/sync_scalper_config_from_env.py:117`; docs at `.env.example:341-344` | PASS | No ADX bypass in the EA lines cited. |
| 8 | M5/M15/H1/H4 trend filters | `ea/FORGE.mq5:7218-7226` and `ea/FORGE.mq5:7467-7470` | `require_m15_agree=true`, `min_h1_bear_strength=0.2` at `config/scalper_config.json:38` and `config/scalper_config.json:87` | PASS | SELL also enforces H4/high-vol alignment when configured. |
| 9 | OsMA SELL Q2 | `ea/FORGE.mq5:7635-7655` | `require_macd_sell=1` at `config/scalper_config.json:90`; mapping at `scripts/sync_scalper_config_from_env.py:143`; docs at `.env.example:530-538` | PASS | PASS only when histogram is negative and falling. |
| 10 | M30 bearish EMA confirmation | `ea/FORGE.mq5:7678-7697` | `require_m30_bear_sell=1`, `m30_bear_adx_min=25` at `config/scalper_config.json:88-89`; mappings at `scripts/sync_scalper_config_from_env.py:137` and `scripts/sync_scalper_config_from_env.py:141`; docs at `.env.example:524-528` | PASS | Enforced at ADX >= configured floor. |
| 11 | RSI declining SELL | `ea/FORGE.mq5:7602-7618` | `require_rsi_declining_sell=1`, `rsi_decl_sell_adx_threshold=40` at `config/scalper_config.json:124` and `config/scalper_config.json:69`; mapping at `scripts/sync_scalper_config_from_env.py:138-140`; docs at `.env.example:324-328` | PASS | Bypassed when H1 is strongly bearish. |
| 12 | H1 MACD SELL | `ea/FORGE.mq5:7658-7675` | `require_h1_macd_sell=0` at `config/scalper_config.json:77`; mapping at `scripts/sync_scalper_config_from_env.py:119`; docs at `.env.example:346-350` | PASS | Code exists but active config disables it. |
| 13 | HID_BULL divergence block | `ea/FORGE.mq5:7620-7633` | `bb_breakout.block_hid_bull_sell=1` at `config/scalper_config.json:125`; mapping at `scripts/sync_scalper_config_from_env.py:139` | PASS | Note duplicate inactive safety key `safety.block_hid_bull_sell=0` at `config/scalper_config.json:259`; EA uses `bb_breakout` key. |
| 14 | SELL session cutoff | `ea/FORGE.mq5:7492-7502` | `session_ny_sell_cutoff_utc=0` at `config/scalper_config.json:251`; mapping at `scripts/sync_scalper_config_from_env.py:210`; docs at `.env.example:636-643` | PASS | Active config disables cutoff. |

## Section 3 — Full Lot Path
| Factor | BUY ADX=38 | SELL ADX=38 | EA line | Status |
|--------|-----------|-----------|---------|--------|
| `fixed_lot` | 0.25 base | 0.25 base | `ea/FORGE.mq5:8410-8414` | PASS |
| `inside_band_factor` | 1.0 | 0.25 only if SELL is back inside band | `ea/FORGE.mq5:8318-8325`; active value `config/scalper_config.json:126` | PASS |
| `near_floor_factor` | 1.0 | 0.25 only in crash-bypass RSI 20-25 zone | `ea/FORGE.mq5:8326-8335`; active value `config/scalper_config.json:249` | PASS |
| `stack_factor` | 0.25 on second same-direction group | 0.25 on second same-direction group | `ea/FORGE.mq5:8336-8343`; active value `config/scalper_config.json:250` | PASS |
| `adx_lot_factor` | 1.0 | 1.0 at M15 ADX 35-44, 0.5 at >=45 | `ea/FORGE.mq5:8344-8359`; active values `config/scalper_config.json:253-257` | FAIL |
| `bounce_factor` | 0.25 for non-breakout bounce | 0.25 for non-breakout bounce | `ea/FORGE.mq5:8361-8363`; active value `config/scalper_config.json:8` | PASS |
| Combined factor | multiplicative floor 0.125 | multiplicative floor 0.125 | `ea/FORGE.mq5:8399-8408` | PASS |

FAIL detail: `.env` says "ADX lot reduction DISABLED" at `.env:298-300`, sets mid to 1.0 at `.env:301`, but sets `FORGE_BREAKOUT_ADX_LOT_FACTOR_HIGH=0.5` at `.env:302`. The known re-check requirement says high ADX SELL reduction must be 1.0; active config is 0.5 at `config/scalper_config.json:257`.

## Section 4 — ADX-Conditional Leg Count
PASS. ADX changes `base_n` before `ForgeResolveNumTrades`: ADX < 25 subtracts one; ADX 35 through below sell-block threshold adds two at `ea/FORGE.mq5:8253-8264`. `ForgeResolveNumTrades` then adds a breakout bonus for setup names containing `BREAKOUT` at `ea/FORGE.mq5:9397-9400`, clamps to env min/max at `ea/FORGE.mq5:9409-9413`, and cap logic applies when HTF is unclear at `ea/FORGE.mq5:8301-8307`. Active config has `min_num_trades=2`, `max_num_trades=30`, `staged_initial_legs=1`, `native_legs_max_when_unclear=5`, `gold_native_max_sell_legs=10` at `config/scalper_config.json:312-323`.

WARNING: The intent doc still says all legs fire simultaneously with `staged_initial_legs=8` at `docs/FORGE_ENTRY_CONDITIONS.md:112-113`; active config is `staged_initial_legs=1` at `config/scalper_config.json:315`, and `.env` explicitly comments that forced 10-leg initial staging was removed at `.env:208-220`.

## Section 5 — TP3 Live Staging
PASS. The group structure has `tp3`, `tp2_hit`, and `tp3_hit` fields at `ea/FORGE.mq5:887-895`. TP3 is registered for breakout groups from `breakout_tp3_atr_mult` at `ea/FORGE.mq5:8512-8518`. The live staging pass waits for TP1, then TP2, then modifies remaining positions to TP3 and marks `tp2_hit=true` at `ea/FORGE.mq5:1994-2048`. Active `tp3_atr_mult=2.5` is at `config/scalper_config.json:54`; mapping is `FORGE_BREAKOUT_TP3_ATR_MULT` at `scripts/sync_scalper_config_from_env.py:273`; docs are at `.env.example:517-522`.

## Section 6 — Direction-Split TP1
PASS. BUY TP1 uses `breakout_tp1_buy_atr_mult` fallback to shared `breakout_tp1_atr_mult` at `ea/FORGE.mq5:7440-7442`; SELL TP1 uses `breakout_tp1_sell_atr_mult` fallback at `ea/FORGE.mq5:7767-7769`. Active values are shared `0.4`, BUY `0.5`, SELL `0.4` at `config/scalper_config.json:50-52`. Sync mappings are at `scripts/sync_scalper_config_from_env.py:268-270`; `.env.example` documents fallback and direction-specific keys at `.env.example:502-515`.

## Section 7 — Crash-Sell Bypass
PASS. The bypass requires `h1_bear`, `h4_bear`, RSI above crash minimum, ADX at/below max, and M15 ADX confirmation at `ea/FORGE.mq5:7548-7561`. It skips only the RSI floor and ADX spike sections guarded by `if(!crash_sell_bypass)` at `ea/FORGE.mq5:7568-7585` and `ea/FORGE.mq5:7587-7599`; H1 DI SELL runs before the bypass at `ea/FORGE.mq5:7533-7547`. Active values are `h1h4_crash_sell=1`, `h1h4_crash_sell_rsi_min=20`, `h1h4_crash_sell_adx_max=40`, and `h1h4_crash_sell_min_m15_adx=25.0` at `config/scalper_config.json:67-72`.

## Section 8 — Variable Integrity
| FORGE_ Variable / config key | In sync script | In .env.example | Config value (active) | Default value | Status |
|----------------|---------------|----------------|----------------------|--------------|--------|
| Active config version | stamp code `scripts/sync_scalper_config_from_env.py:502-511` | n/a | `2.7.41` at `config/scalper_config.json:2`; EA constant `ea/FORGE.mq5:63` | `0.0.0` at `config/scalper_config.defaults.json:2` | PASS |
| All 87 active `.env` `FORGE_*` vars | mapping loop `scripts/sync_scalper_config_from_env.py:464-485`; whitelist `tests/api/test_forge_27x_gates.py:302-307` | audited against `.env.example` | no unmapped active vars | n/a | PASS |
| 251 sync mapping keys | mapping declared at `scripts/sync_scalper_config_from_env.py:27-329` | no missing doc keys from audit; `.env.example` FORGE block begins `.env.example:190-196` | n/a | n/a | PASS |
| Reverse `.env.example` keys | bridge consumes magic/mode/queue keys at `python/bridge.py:119-120`, `python/bridge.py:157-160`, `python/bridge.py:328-329` | `FORGE_MAGIC_NUMBER`, `FORGE_MAGIC_MAX`, `FORGE_SCALPER_MODE`, `FORGE_QUEUE_ACK_TIMEOUT_SEC`, `FORGE_QUEUE_MAX_RETRIES` | not sync-mapped | n/a | WARNING |
| `bb_breakout.block_hid_bull_sell` | `scripts/sync_scalper_config_from_env.py:139` | `.env:237-239`; no separate `.env.example` line found by direct key name in loaded snippet, but audit found key documented | active 1 at `config/scalper_config.json:125` | absent in defaults section before later safety duplicate | PASS |
| `safety.block_hid_bull_sell` duplicate | no active EA read found; EA reads `g_sc.breakout_block_hid_bull_sell` | no operator knob needed | active 0 at `config/scalper_config.json:259` | 0 at `config/scalper_config.defaults.json:258` | WARNING |
| `breakout_adx_lot_factor_high` | `scripts/sync_scalper_config_from_env.py:281` | `.env.example:547-550` | 0.5 at `config/scalper_config.json:257` | 0.125 at `config/scalper_config.defaults.json:256` | FAIL |

All active FORGE-backed config diffs found between active/defaults are mapped or intentionally outside sync. Notable active diffs include lot sizing (`config/scalper_config.json:310-330` vs defaults `config/scalper_config.defaults.json:276-278`), breakout gates (`config/scalper_config.json:63-127` vs defaults `config/scalper_config.defaults.json:63-123`), safety thresholds (`config/scalper_config.json:249-291` vs defaults `config/scalper_config.defaults.json:248-277`), and bounce sizing (`config/scalper_config.json:7-30` vs defaults `config/scalper_config.defaults.json:7-30`).

## Section 9 — scribe.py / regime.py / schemas/ Cross-Check
| Check | File:line | Status | Notes |
|-------|-----------|--------|-------|
| `forge_signals` base table | `python/scribe.py:119-225` | PASS | Includes 107-column Layer-4 telemetry shape in current CREATE. |
| `forge_journal_trades` includes `volume` | `python/scribe.py:225-246` and tester table `python/scribe.py:750-792` | PASS | Required by Athena lot-per-leg math. |
| `aurum_run_id` migrations | `python/scribe.py:570-650` and `python/scribe.py:828-830` | PASS | Signals and trades both migrated. |
| SIGNALS sync inserts Layer-4 columns | `python/scribe.py:1043-1048` and `python/scribe.py:1239-1244` | PASS | Atom telemetry is synced when present. |
| Regime labels | `python/regime.py:320`, `python/regime.py:336-345`, `python/regime.py:530-549`; EA resolver uses `VOLATILE`/`RANGE` at `ea/FORGE.mq5:9392-9395` and TP staging uses all three trend labels at `ea/FORGE.mq5:2057-2063` | PASS | Labels align: `TREND_BULL`, `TREND_BEAR`, `VOLATILE`, `RANGE`. |
| schemas/ SQL alignment | `schemas/openapi.yaml:970-977`; repo schema inventory from `schemas/manifest.json` | UNVERIFIED | No DB `.sql` schema files were found under `schemas/`; DB alignment is therefore based on `scribe.py` CREATE/ALTER code, not independent SQL. |

## Section 10 — Dashboard / API Consistency
| Check | dashboard:line | api:line | Status | Notes |
|-------|---------------|----------|--------|-------|
| Run detail guarded by selected run ID | `dashboard/app.js:1483-1489` | `python/athena_api.py:1705-1716` | PASS | UI only renders detail when `btSelRun===btDetail.meta.aurum_run_id`. |
| Loading run indicator | `dashboard/app.js:1483-1486` | n/a | PASS | Shows `Loading run #N…`. |
| Run ID shown in header | `dashboard/app.js:1497-1503` | `python/athena_api.py:1948-1954` | PASS | API returns `meta`; UI displays `Run #`. |
| Run isolation on queries | n/a | `python/athena_api.py:1728-1730`, `python/athena_api.py:1741-1746`, `python/athena_api.py:1751-1759`, `python/athena_api.py:1763-1768`, `python/athena_api.py:1771-1778`, `python/athena_api.py:1782-1786`, `python/athena_api.py:1937-1941` | PASS | `aurum_run_id=?` appears on every run-detail SIGNALS/TRADES query. |
| TAKEN legs from TP1 markers | `dashboard/app.js:1703-1708` | `python/athena_api.py:1903-1907` | PASS | API computes from `|TP1` comments; UI renders legs x lot. |
| `lot_per_leg` uses volume | `dashboard/app.js:1703-1708` | `python/athena_api.py:1780-1786` and `python/athena_api.py:1909-1911` | PASS | `ROUND(volume,3) as volume` is selected. |
| P&L includes cascades +20000..+20009 | `dashboard/app.js:1724-1731` | `python/athena_api.py:1830-1843`, `python/athena_api.py:1870-1892` | PASS | Cascade owner map includes offsets 20000..20009. |
| `cascade_pnl` surfaced | `dashboard/app.js:1724-1731` | `python/athena_api.py:1891-1892`, `python/athena_api.py:1924-1934` | PASS | UI tooltip shows cascade breakdown when non-zero. |
| `trade_outcome` field | `dashboard/app.js:1681-1686` | `python/athena_api.py:1913-1927` | PASS | Field names match. |

## Section 11 — Scripts / Tests Consistency
| Check | File:line | Status | Notes |
|-------|-----------|--------|-------|
| VERSION/config parity test | `tests/api/test_forge_27x_gates.py:75-80`; active version `config/scalper_config.json:2`; EA constant `ea/FORGE.mq5:63` | PASS | Version is 2.7.41 in config and EA. |
| Dead env var test | `tests/api/test_forge_27x_gates.py:310-325` | PASS | Matches Mandatory Check A. |
| Lowercase env leak test | `tests/api/test_forge_27x_gates.py:279-299` | PASS | No lowercase config-looking keys found in `.env`. |
| ADX high lot test | `tests/api/test_forge_27x_gates.py:106-120` | FAIL | Test allows `breakout_adx_lot_factor_high=0.5`; known re-check requires 1.0. |
| Gate legend stale codes | `config/gate_legend.json:19-204`, `config/gate_legend.json:294-346`; EA emitted gates audited from `ea/FORGE.mq5` | PASS | No missing legend entries. |
| Stale slot comments | `ea/FORGE.mq5:1290`, `ea/FORGE.mq5:3048-3056`, `ea/FORGE.mq5:9048-9051` | WARNING | Comments still say "all 5 slots"; loops correctly use `< 10`. |

## Mandatory Check A — Dead FORGE_* env vars
PASS. Audit enumerated 87 active `.env` `FORGE_*` keys; each is sync-mapped by `scripts/sync_scalper_config_from_env.py:27-329` or whitelisted in `tests/api/test_forge_27x_gates.py:302-307`. No lowercase config-looking keys were found; the test pattern is defined at `tests/api/test_forge_27x_gates.py:274-299`. Accepted plaintext-secret assumptions are intact: `.env` is gitignored at `.gitignore:1-7`, rendered plists are gitignored at `.gitignore:62-63`, and `git ls-files .env services/macos/rendered` returned no tracked paths.

## Mandatory Check B — Gate legend completeness
PASS. EA emits 90 SKIP call sites and 62 unique SKIP codes via `JournalRecordSignal("SKIP",...)`; all codes have explicit keys or wildcard coverage in `config/gate_legend.json`. The legend includes core entry gates at `config/gate_legend.json:19-204`, daily/dump gates at `config/gate_legend.json:294-346`, and wildcard/pattern coverage for dynamic codes in the same file. No missing code was found.

## Mandatory Check C — Sync mapping ↔ .env.example parity
PASS. The one-liner audit found `missing_doc=[]`: every one of 251 sync mapping keys from `scripts/sync_scalper_config_from_env.py:27-329` appears in `.env.example`. Reverse keys not in sync are `FORGE_MAGIC_NUMBER`, `FORGE_MAGIC_MAX`, `FORGE_SCALPER_MODE`, `FORGE_QUEUE_ACK_TIMEOUT_SEC`, and `FORGE_QUEUE_MAX_RETRIES`; these are consumed directly by bridge code at `python/bridge.py:119-120`, `python/bridge.py:157-160`, and `python/bridge.py:328-329`, so they are warnings, not failures.

## Issues Found (Consolidated)
1. FAIL: Active high-ADX SELL lot factor is still reducing lots. Active `breakout_adx_lot_factor_high=0.5` at `config/scalper_config.json:257` and `.env:302`, while `.env:298-300` states ADX lot reduction is disabled and the known re-check requires high factor 1.0.
2. FAIL: Tests do not enforce the no-reduction invariant. `tests/api/test_forge_27x_gates.py:106-120` only checks `(0,1]` and high <= mid, so `0.5` passes.
3. WARNING: Entry intent doc is stale on version and some values: it says v2.7.37 at `docs/FORGE_ENTRY_CONDITIONS.md:1-6`, while active config and EA are v2.7.41 at `config/scalper_config.json:2` and `ea/FORGE.mq5:63`.
4. WARNING: Intent doc says `rsi_sell_floor=30` at `docs/FORGE_ENTRY_CONDITIONS.md:132`; active config is 33 at `config/scalper_config.json:64`.
5. WARNING: Intent doc says simultaneous initial legs via `staged_initial_legs=8` at `docs/FORGE_ENTRY_CONDITIONS.md:112-113`; active config is `staged_initial_legs=1` at `config/scalper_config.json:315`.
6. WARNING: `schemas/` has API/file schemas but no DB SQL schema to cross-check independently; DB validation relies on `python/scribe.py` CREATE/ALTER migrations.
7. WARNING: Slot comments still say "all 5 slots" at `ea/FORGE.mq5:1290`, `ea/FORGE.mq5:3055`, and `ea/FORGE.mq5:9049`; executable loops use `< 10` at `ea/FORGE.mq5:1292`, `ea/FORGE.mq5:3056`, and `ea/FORGE.mq5:9051`.

## Recommendations & Proposed Fixes
1. Set `FORGE_BREAKOUT_ADX_LOT_FACTOR_HIGH=1.0` in `.env` and regenerate `config/scalper_config.json` via `make scalper-env-sync`.
2. Update `tests/api/test_forge_27x_gates.py` with an explicit assertion that mid and high ADX lot factors are both 1.0 when the operator policy is "ADX lot reduction disabled."
3. Refresh `docs/FORGE_ENTRY_CONDITIONS.md` or add a top warning that current active details moved to `docs/FORGE_DECISION_STACK_INVENTORY.md`; do not treat value drift in that intent doc as a runtime failure.
4. Either add DB schema SQL under `schemas/` or document that `python/scribe.py` is the authoritative DB migration source.
5. Update stale "all 5 slots" comments to "all 10 slots" to match executable slot loops.

## Overall Verdict
WARNING with 2 actionable FAIL items. Core BUY/SELL gate logic, crash-sell bypass, TP3 staging, direction-split TP1, cascade slot expansion, SCRIBE sync, and Athena TAKEN-entry math are implemented and line-verified. Operator attention is required for the active high-ADX SELL lot reduction and the test gap that lets it pass.
