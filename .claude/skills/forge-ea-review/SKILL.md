---
name: forge-ea-review
description: Validate FORGE EA logic, workflow and intent against documentation and config using codex:rescue. Cross-checks ea/FORGE.mq5 against FORGE_ENTRY_CONDITIONS.md, scalper_config.json, scalper_config.defaults.json, sync_scalper_config_from_env.py, .env, .env.example, scribe.py and regime.py. Also audits schemas/, dashboard/, scripts/, tests/, and config/ for consistency. Documents findings in docs/FORGE_ENTRY_CONDITIONS_CODEX_REVIEW.md. Invoke when the user types /forge-ea-review or asks to "review the forge EA", "validate forge logic", "codex review forge". You can append or override findings. When you are done with any fix — document and update changelog.md for any solution.
---

# /forge-ea-review — FORGE EA Validation Review

You are performing a rigorous technical validation of the FORGE EA entry logic and configuration pipeline.

> **DO NOT HALLUCINATE.** Every claim must cite exact file:line. If code for a claim cannot be found, mark it UNVERIFIED — do not guess or infer.

---

## SOURCE FILES (read ALL before writing anything)

| File / Folder | Role |
|------|------|
| `/Users/olasumbo/signal_system/ea/FORGE.mq5` | EA implementation — source of truth |
| `/Users/olasumbo/signal_system/docs/FORGE_ENTRY_CONDITIONS.md` | Intent document — what the EA is supposed to do |
| `/Users/olasumbo/signal_system/config/scalper_config.json` | **Active** runtime config (env overrides applied) |
| `/Users/olasumbo/signal_system/config/scalper_config.defaults.json` | Default values before overrides |
| `/Users/olasumbo/signal_system/config/` | All config files — gate_legend.json, lens_brief.json, etc. |
| `/Users/olasumbo/signal_system/scripts/sync_scalper_config_from_env.py` | Maps FORGE_ env vars → JSON config keys |
| `/Users/olasumbo/signal_system/scripts/` | All helper scripts — build, sync, analysis |
| `/Users/olasumbo/signal_system/.env` | Active env overrides |
| `/Users/olasumbo/signal_system/.env.example` | **Cheat sheet** — all documented FORGE_ variables with descriptions |
| `/Users/olasumbo/signal_system/python/scribe.py` | Live trading SCRIBE — reads signals/trades from live EA |
| `/Users/olasumbo/signal_system/python/regime.py` | Regime detection — market context used by EA for lot sizing |
| `/Users/olasumbo/signal_system/python/trading_session.py` | v2.7.49+: `get_ea_killzone()` / `get_ea_session()` readers for market_data.json; `_kz_window()` reads scalper_config.json |
| `/Users/olasumbo/signal_system/python/bridge.py` | v2.7.49+: `_killzone()` / `_session()` EA-anchored with UTC fallback + throttled WARN |
| `/Users/olasumbo/signal_system/python/athena_api.py` | v2.7.47+: `/api/backtest/run/:id` TAKEN entries return killzone+minutes_into_kz; v2.7.49+: `/api/live` returns `*_local_check` divergence fields |
| `/Users/olasumbo/signal_system/python/aurum.py` | v2.7.50+: LENS prompt context reads `get_ea_session(MARKET_FILE)` |
| `/Users/olasumbo/signal_system/python/backtest_compare.py` | v2.7.48: KZ + RegimeState breakdowns in run-vs-run comparator |
| `/Users/olasumbo/signal_system/python/*.py` | All other Python services — herald, sentinel, lens, etc. |
| `/Users/olasumbo/signal_system/schemas/` | DB schema definitions — cross-check against scribe.py CREATE TABLE and ALTER TABLE migrations |
| `/Users/olasumbo/signal_system/dashboard/` | Athena UI — app.js, index.html — cross-check API field names used in UI against athena_api.py response shapes |
| `/Users/olasumbo/signal_system/tests/` | Test specs — flag any tests that reference removed gates, stale config keys, or outdated field names |

---

## VALIDATION PROTOCOL

### MANDATORY CHECKS (must appear in every review output as explicit PASS/FAIL)

Every `/forge-ea-review` run MUST emit explicit results for these two checks. They have proven repeatedly to be the highest-value, lowest-effort regression catchers:

#### Mandatory Check A — Dead `FORGE_*` env vars (must PASS or list all failures)
- Enumerate every `FORGE_*` key in `.env`
- For each: confirm a mapping exists in `scripts/sync_scalper_config_from_env.py` (`f'"{key}"' in source`) — OR confirm it's intentionally consumed outside sync (e.g. by `python/bridge.py` or as an MT5 `input` parameter); in that case the var must be listed in `tests/api/test_forge_27x_gates.py::FORGE_ENV_VARS_NOT_IN_SYNC` with rationale
- Any unmapped, unwhitelisted `FORGE_*` env var is a **FAIL** — these are silently dropped and leave runtime config diverging from `.env`
- Also catch the case-mismatch class: lowercase keys in `.env` (e.g. `adx_hysteresis_enabled=1`) that *look* like FORGE config but bypass the `FORGE_*` uppercase prefix the sync script requires — also a **FAIL**

#### Mandatory Check B — Gate legend completeness (must PASS or list all failures)
- Extract every gate code emitted by `ea/FORGE.mq5`. Two emission patterns must BOTH be considered:
  1. **Literal codes** — `JournalRecordSignal("SKIP","<code>", ...)` direct string literal in the EA
  2. **Runtime-constructed codes** (v2.7.43+ layered helpers) — `Filter_AdxFloor`, `Filter_Cooldown`, `Filter_M15TrendAligned` build the SKIP code at emission time as `<setup_lower> + "_adx_below_min"` / `"_cooldown"` / `"_m15_misalign"`. The literal string never appears in `ea/FORGE.mq5` — only the call-site arguments do. Naively grepping for literals MISSES these (codex caught this as a false-positive WARNING on 2026-05-13).

  Use this exact one-liner to enumerate BOTH classes:
  ```python
  import re, pathlib
  ea = pathlib.Path('ea/FORGE.mq5').read_text()
  # 1. Literal codes
  literal_codes = set(re.findall(r'JournalRecordSignal\(\s*"SKIP"\s*,\s*"([a-z_][a-z0-9_]+)"', ea))
  # 2. v2.7.43+ Filter_*-constructed codes (setup_lower + suffix)
  filter_adx  = re.findall(r'Filter_AdxFloor\(\s*"[A-Z_]+"\s*,\s*"([a-z_][a-z0-9_]+)"', ea)
  filter_cool = re.findall(r'Filter_Cooldown\(\s*"[A-Z_]+"\s*,\s*"([a-z_][a-z0-9_]+)"', ea)
  filter_m15  = re.findall(r'Filter_M15TrendAligned\(\s*"[A-Z_]+"\s*,\s*"([a-z_][a-z0-9_]+)"', ea)
  constructed = (
      {f"{s}_adx_below_min" for s in filter_adx}
      | {f"{s}_cooldown" for s in filter_cool}
      | {f"{s}_m15_misalign" for s in filter_m15}
  )
  all_emitted = literal_codes | constructed
  ```
- For each emitted code (literal OR constructed): confirm a matching key exists in `config/gate_legend.json`, OR the code matches a `_patterns` wildcard (e.g. `warmup_*`)
- Any EA-emitted gate without a legend entry or wildcard match is a **FAIL** — monitoring tools and analysis reports show raw codes with no human label
- The reverse direction (legend entries with no emission source) is **acceptable** when the entry maps to a Filter_*-constructed code from one of the v2.7.42 setups; do NOT flag those as stale. Real stale entries are ones with no literal emission AND no Filter_* call site that would construct them.
- Report exact missing codes and the EA file:line where each is emitted

#### Mandatory Check C — Sync mapping ↔ .env.example parity (must PASS or list all failures)
- Extract every `FORGE_*` key declared in `scripts/sync_scalper_config_from_env.py` MAPPING
- For each: confirm a matching `# FORGE_*=` or `FORGE_*=` line appears in `.env.example`
- Any sync-mapped key missing from `.env.example` is a **FAIL** — operators discover knobs from `.env.example`; a sync mapping without a hint is silently undiscoverable
- Also report the reverse: any `FORGE_*=` in `.env.example` that has no sync mapping (likely a stale doc entry that the sync script will silently drop). Treat as **WARNING** if the key has a comment indicating it's consumed outside sync (e.g. MT5 input, BRIDGE-direct), otherwise **FAIL**
- Use this exact one-liner for the audit:
  ```python
  import re, pathlib
  sync = pathlib.Path('scripts/sync_scalper_config_from_env.py').read_text()
  example = pathlib.Path('.env.example').read_text()
  mapping = set(re.findall(r'"(FORGE_[A-Z0-9_]+)":\s*\(', sync))
  example_keys = set(re.findall(r'^[# ]*(FORGE_[A-Z0-9_]+)=', example, re.MULTILINE))
  missing_doc = sorted(mapping - example_keys)
  missing_map = sorted(example_keys - mapping)
  ```
- Historical context: 2026-05-12 audit found 16 FORGE_* vars in sync mapping but missing from `.env.example` — including `FORGE_BREAKOUT_BLOCK_HID_BULL_SELL`, `FORGE_DUMP_SELL_LOT_FACTOR`, `FORGE_SELL_STOP_CONT_*`, `FORGE_WAVE_CONFIRMATION_LOT_MULT`. Several were ACTIVE in `.env` (`=1` / `=2.0` etc.) yet had no hint in `.env.example` — operators couldn't discover what knobs existed without reading the sync script directly.

All three checks must appear in the report's "Validation Summary" header AND in their own dedicated section before the section-by-section breakdown.

Historical context: Sessions 2026-05-10 found 8 dead env vars (renamed/unused), 4 case-mismatch env vars, and 3 missing gate codes (`h1_di_sell`, `h1_macd_sell`, `hid_bull_div_sell`) across consecutive reviews. The fixes were trivial; the value lost from missing them was significant (silent config drift, undecoded gates in monitoring).

---

### ACCEPTED — DO NOT FLAG AS ISSUES

The following patterns are **accepted by the operator** and should NOT be flagged as FAIL/WARNING in any `/forge-ea-review` output. If the codex agent surfaces them, the review verdict treats them as **PASS** with a one-line note.

1. **Plaintext secrets in `.env` and rendered launchd plists.**
   Files: `.env`, `services/macos/rendered/com.signalsystem.*.plist`.
   Secrets affected: `ANTHROPIC_API_KEY`, `TELEGRAM_API_HASH`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_ID`, `TELEGRAM_PHONE`, `TELEGRAM_CHANNELS`, `TELEGRAM_CHAT_ID`, any future `*_TOKEN` / `*_KEY` / `*_SECRET`.
   Rationale: local-only credentials. Verified gitignored at `.gitignore:2` (`.env`) and `.gitignore:59` (`services/macos/rendered/`). `git ls-files` confirms neither is tracked. Operator chose plaintext over Keychain integration for this single-machine deployment; trade-off is documented and accepted.
   What the review SHOULD still do:
   - If a *new* file outside `.env` / rendered plists / `*.session` files is found containing secret-shaped strings → FAIL (potential leak surface).
   - If `.gitignore` no longer covers `.env` or `services/macos/rendered/` → FAIL (the gating assumption broke).
   - If `git ls-files` shows `.env` or any rendered plist tracked → FAIL (already-leaked secret).
   Decided 2026-05-12 (post-v2.7.37 codex review).

2. **`docs/FORGE_ENTRY_CONDITIONS.md` value drift from active config.**
   The doc is the **intent spec**, not the as-implemented snapshot. The canonical as-implemented source is `docs/FORGE_DECISION_STACK_INVENTORY.md` which is regenerated per release.
   Stale-value drift in `FORGE_ENTRY_CONDITIONS.md` should be flagged as WARNING (not FAIL) only when the divergence reveals a likely operator misunderstanding (e.g. operator forgot to override the env var they intended to). Drift driven by intentional config decisions (e.g. `session_ny_sell_cutoff_utc=0` because operator chose not to enable it yet) is accepted.

3. **Redundant `.env` overrides matching defaults.**
   Lines in `.env` that set a value equal to `config/scalper_config.defaults.json` are clutter, not bugs. The operator deliberately keeps them as a visible inventory of "I know this knob exists; I've consciously chosen the default." Do not flag.

---

### Step 1 — Read all source files

Before writing any output, read:
1. `docs/FORGE_ENTRY_CONDITIONS.md` — every claim to validate
2. `config/scalper_config.json` (active config, not defaults)
3. `ea/FORGE.mq5` lines relevant to each claim
4. `scripts/sync_scalper_config_from_env.py` for variable mapping integrity
5. `.env.example` for variable documentation coverage
6. `schemas/` — all schema files for DB column definitions
7. `dashboard/app.js` — UI field names and API response usage
8. `scripts/` — all helper scripts for build/sync consistency
9. `tests/` — test specs for stale gate names, config keys, field references
10. `config/` — gate_legend.json and other config files for key coverage

### Step 2 — Validate each section of FORGE_ENTRY_CONDITIONS.md

For every gate, parameter, and behavioral claim:
- Find the exact EA code line(s) implementing it
- Confirm the config value in `scalper_config.json` matches what the doc says
- Check that the FORGE_ env var is mapped in `sync_scalper_config_from_env.py`
- Check that the FORGE_ env var is documented in `.env.example`
- Status: **PASS** / **FAIL** / **WARNING** / **UNVERIFIED**

### Step 3 — Variable integrity sweep

For every FORGE_ variable that differs between `scalper_config.json` and `scalper_config.defaults.json`:
- Confirm it has a mapping in `sync_scalper_config_from_env.py`
- Confirm it is documented in `.env.example` with description
- Flag any variable set in `.env` that has no sync mapping (dead var)

### Step 4 — scribe.py and regime.py cross-check

Review `scribe.py` and `regime.py` for:
- Any field names or column names read from the FORGE journal DB that may not exist (schema mismatch)
- Cross-check `schemas/` SQL files against scribe.py CREATE TABLE and ALTER TABLE migrations — flag any column in schemas/ missing from scribe.py or vice versa
- Regime labels used in `ForgeResolveNumTrades` that must match what `regime.py` produces
- Any config keys read by scribe/regime that are not in `scalper_config.json`

### Step 5 — Dashboard / API consistency check

Review `dashboard/app.js` and `python/athena_api.py` for:
- Any field name used in the UI (e.g. `e.trade_outcome`, `e.pnl`, `btDetail.taken`) that is not returned by the API
- Any API response field that the UI silently ignores but should display
- Any gate_reason code referenced in `dashboard/app.js` or `config/gate_legend.json` that no longer exists in the EA

**TAKEN ENTRIES math accuracy (always validate these):**
- `legs` field: verify count comes from `|TP1` SCALP markers per group_magic (not hardcoded or zero)
- `lot_per_leg` field: verify `volume` is selected in the `all_trades` SQL query (was missing — caused lot=null)
- `pnl` accuracy: verify cascade magic deals (+20000..+20009) are summed into each group's P&L (previously only group_magic was summed — missing SELL LIMIT L1/L2 and SELL STOP CONT losses)
- `cascade_pnl` field: verify it is non-zero for groups with cascade fills, and equals sum of +20000..+20009 magic deals with profit≠0
- Run isolation: verify the `WHERE aurum_run_id=?` filter is applied to all queries (SIGNALS, TRADES) — no cross-run data leakage
- Run ID display: verify `btDetail.meta.aurum_run_id` is shown in the UI header and matches the selected run button (`btSelRun === btDetail.meta.aurum_run_id` guard)
- Loading state: verify a "Loading run #N…" indicator appears when `btSelRun !== btDetail.meta.aurum_run_id` (stale detail guard)

### Step 6 — Scripts and tests consistency check

Review `scripts/` for:
- Any script that references a config key, env var, or gate name that has been renamed or removed

Review `tests/` for:
- Any test referencing a removed gate code, stale config key, or field name that no longer matches the current DB schema or API response shape

### Step 7 — Write output report

Write findings to `/Users/olasumbo/signal_system/docs/FORGE_ENTRY_CONDITIONS_CODEX_REVIEW.md`

---

## OUTPUT FORMAT

The report must follow this exact structure:

```markdown
# FORGE Entry Conditions — Codex Validation Review

**Date**: YYYY-MM-DD  
**EA version**: FORGE vX.Y.Z (from scalper_config.json)  
**Reviewer**: Codex (automated, read-only)  
**Methodology**: Every claim cited with file:line. UNVERIFIED = code not found. Active config = scalper_config.json (not defaults).

## Validation Summary
- Gates checked: N
- PASS: N  |  WARNING: N  |  FAIL: N  |  UNVERIFIED: N

## Section 1 — BB_BREAKOUT BUY Gates
| # | Gate | EA file:line | Config key=value (scalper_config.json) | Status | Notes |
|---|------|-------------|---------------------------------------|--------|-------|

## Section 2 — BB_BREAKOUT SELL Gates
[same table format]

## Section 3 — Full Lot Path
For each factor in combined_lot_factor:
| Factor | BUY ADX=38 | SELL ADX=38 | EA line | Status |
|--------|-----------|-----------|---------|--------|

## Section 4 — ADX-Conditional Leg Count
[verify EA code matches doc claim, cite lines]

## Section 5 — TP3 Live Staging
[verify tp2_hit flag, tp3 registration, promotion logic]

## Section 6 — Direction-Split TP1
[verify BUY/SELL path uses correct mult, fallback]

## Section 7 — Crash-Sell Bypass
[verify exact conditions match doc]

## Section 8 — Variable Integrity
| FORGE_ Variable | In sync script | In .env.example | Config value (active) | Default value | Status |
|----------------|---------------|----------------|----------------------|--------------|--------|

## Section 9 — scribe.py / regime.py / schemas/ Cross-Check
| Check | File:line | Status | Notes |
|-------|-----------|--------|-------|

## Section 10 — Dashboard / API Consistency
| Check | dashboard:line | api:line | Status | Notes |
|-------|---------------|----------|--------|-------|

## Section 11 — Scripts / Tests Consistency
| Check | File:line | Status | Notes |
|-------|-----------|--------|-------|

## Mandatory Check A — Dead FORGE_* env vars
**Status**: PASS / FAIL
| .env key | sync mapping found? | Whitelisted (FORGE_ENV_VARS_NOT_IN_SYNC)? | Status |
|----------|---------------------|-------------------------------------------|--------|
| ... | yes/no @ line N | yes/no | PASS/FAIL |

Lowercase config-looking keys (must be empty for PASS):
| .env line | key | Reason flagged |
|-----------|-----|----------------|

## Mandatory Check B — Gate legend completeness
**Status**: PASS / FAIL
| EA gate code | EA file:line | In gate_legend.json? | Matches _patterns wildcard? | Status |
|--------------|--------------|----------------------|------------------------------|--------|
| ... | FORGE.mq5:N | yes/no | yes/no | PASS/FAIL |

## Issues Found (Consolidated)
| # | Severity | Section | Description | Action |
|---|----------|---------|-------------|--------|

## Recommendations & Proposed Fixes
<!-- For each FAIL or WARNING that requires a code/config change, append a structured fix
     proposal here. Follow the same pattern as forge-monitor's RECOMMENDATIONS PATTERN:

     ### Issue N — <title>
     **Evidence**: <concrete file:line cites or config diff>
     **Root cause**: <explanation rooted in code>
     **Industry pattern** (per WebSearch): "<quote>" — Source: [link](url)

     #### Option A — <name>
     ```pseudocode
     <diff>
     ```
     Defaults: <new knobs>
     Risk: <blast radius>

     #### Option B / C — <alternatives>

     **Preferred**: Option <X>. Reason: <trade-off rationale>
     **Backward compatibility**: ships behind FORGE_<FLAG>=0 (default-OFF). -->

## Overall Verdict
[Summary paragraph: what is working, what needs fixing, confidence level in the EA logic]
```

**Hard rules for the Recommendations section**:
1. **No hallucination** — every code reference must include `file:line` cites. Every claim about behavior must be backed by a query result or compiled code.
2. **WebSearch BEFORE proposing** — for every fix candidate, search "MQL5 <topic>" first. Quote the canonical pattern with source URL. Adapt to FORGE's specifics. Never invent novel approaches when established MT5/MQL5 patterns exist.
3. **Multiple options required** — at least 2 alternatives per issue, each with pseudocode + risk assessment. Operator picks; reviewer doesn't impose.
4. **Backward compatibility mandatory** — every proposal ships behind a default-OFF env flag. Specify the flag name and default value.
5. **Rooted in this run's data** — recommendations must cite evidence from the CURRENT review's findings, not generic best practices.

---

## EXECUTION

Use `codex:rescue` (via the Agent tool with `subagent_type: "codex:codex-rescue"`) to perform the validation.

Pass this prompt to the agent verbatim, prefixed with `--fresh`:

```
--fresh

Read-only validation. Write output to /Users/olasumbo/signal_system/docs/FORGE_ENTRY_CONDITIONS_CODEX_REVIEW.md

[Full source file list and validation protocol as defined in this SKILL.md]

[Full output format as defined in this SKILL.md]

CRITICAL RULES:
1. DO NOT HALLUCINATE. Cite file:line for every claim.
2. Compare against scalper_config.json (active config), not defaults.
3. If code is not found, mark UNVERIFIED — do not guess.
4. Validate .env variable names against .env.example and sync_scalper_config_from_env.py.
5. Cross-check schemas/ SQL against scribe.py CREATE TABLE + ALTER TABLE migrations.

ACCEPTED — DO NOT FLAG AS ISSUES (per SKILL.md "ACCEPTED — DO NOT FLAG" section):
- Plaintext secrets in `.env` and `services/macos/rendered/com.signalsystem.*.plist`
  (ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_API_HASH, etc.). Both paths are
  gitignored (`.gitignore:2` and `.gitignore:59`); `git ls-files` confirms neither
  is tracked. Operator-accepted trade-off for single-machine deployment.
  HOWEVER do FLAG: (a) secret-shaped strings in any *other* file; (b) `.env` or
  `services/macos/rendered/` no longer gitignored; (c) `git ls-files` showing them
  tracked.
- `docs/FORGE_ENTRY_CONDITIONS.md` value drift from active config. Canonical
  as-implemented source is `docs/FORGE_DECISION_STACK_INVENTORY.md`. Drift is a
  WARNING at most, never a FAIL.
- Redundant `.env` overrides that set a value identical to defaults.json — operator
  intentionally keeps these as a visible inventory of "I know this knob exists."

MANDATORY CHECKS (REPORT EXPLICIT PASS/FAIL FOR ALL THREE — DO NOT SKIP):
A. Dead FORGE_* env vars: enumerate every FORGE_* key in .env, confirm each maps in
   sync_scalper_config_from_env.py OR appears in the FORGE_ENV_VARS_NOT_IN_SYNC
   whitelist in tests/api/test_forge_27x_gates.py. Also flag any lowercase config-
   looking keys in .env (e.g. adx_hysteresis_enabled=1) that bypass the FORGE_*
   prefix. Each unmapped/unwhitelisted var = FAIL.
B. Gate legend completeness: enumerate BOTH literal AND runtime-constructed gate
   codes from ea/FORGE.mq5:
     (i)  literal: JournalRecordSignal("SKIP","<code>",...) string args
     (ii) constructed (v2.7.43+ layered helpers): for each call site
          Filter_AdxFloor("<NAME>","<lower>",...) emit "<lower>_adx_below_min";
          Filter_Cooldown("<NAME>","<lower>",...) emit "<lower>_cooldown";
          Filter_M15TrendAligned("<NAME>","<lower>",...) emit "<lower>_m15_misalign".
   Confirm each (literal OR constructed) has a key in config/gate_legend.json OR
   matches a _patterns wildcard. Each missing code = FAIL.
   CAUTION: a naive grep-for-literal-string approach MISSES the 26+ codes that
   v2.7.42 setups construct at runtime — on 2026-05-13 codex flagged 20 valid
   legend entries as "stale" because it didn't enumerate Filter_* call sites.
   Always do BOTH passes.
   The reverse direction (legend entry with no emission source) is ACCEPTABLE
   when the entry would be constructed by a Filter_* call site; do NOT flag.
C. Sync mapping ↔ .env.example parity: enumerate every "FORGE_*" key in
   sync_scalper_config_from_env.py MAPPING, confirm each has a matching
   `# FORGE_*=` or `FORGE_*=` line in .env.example. Each sync-mapped key missing
   from .env.example = FAIL (operators discover knobs only from .env.example;
   silent undiscoverable knobs created real configuration-blindness — 16 such
   gaps found in 2026-05-12 audit). Also flag the reverse (in .env.example but
   no sync mapping) as WARNING (likely stale doc).

These three checks have caught real silent-config-drift, undecoded-gate, and
discovery-blindness bugs in every recent review. They MUST appear in the
report's Validation Summary AND in their own dedicated sections.
6. Check dashboard/app.js field names against athena_api.py response shapes.
7. Flag tests/ referencing stale gate codes or removed config keys.
8. After writing the file, output a brief summary of PASS/WARNING/FAIL counts.
```

---

## WHAT TO REPORT

When the review completes, report:
1. Total PASS / WARNING / FAIL / UNVERIFIED counts
2. All FAIL items — exact description and affected gate/feature
3. All WARNING items — potential issues and recommended investigation
4. Whether the output file was written successfully
5. Any dead variables (in `.env` but not in sync script)
6. Any schema mismatches found in scribe.py, regime.py, or schemas/
7. Any dashboard field mismatches (UI reads field not returned by API)
8. Any stale references in scripts/ or tests/

---

## KNOWN ISSUES TO ALWAYS RE-CHECK (from session history)

These patterns have caused real bugs — always validate:

- **Dead .env vars**: `.env` vars with no mapping in `sync_scalper_config_from_env.py` are silently dropped. Previous run found 8 dead vars (SELL_LIMIT_*, ADX_SELL_BLOCK_THRESHOLD, etc.). Always sweep `.env` against sync script.
- **OsMA logging bug**: `macd_histogram` was logging 0.0 for all TAKEN signals because CopyBuffer failed at the TAKEN record site. Fixed in 2.7.12 to log H1 MACD histogram. Check TAKEN record logs H1 MACD, not M5 OsMA.
- **staged_initial_legs n-1 bug**: Was using `MathMin(init_cap, n-1)` — always held one leg back. Fixed to `n`. Re-check this line after any staged_add changes.
- **RSI=0/ADX=0 logging**: CheckEntryQuality was logging hardcoded 0,0. Fixed by passing rsi/adx through. If any new SKIP logging calls are added, verify they pass real indicator values.
- **adx_lot_factor_high silently reducing SELL lots**: Was 0.125 (0.01 lot at ADX>35). Fixed to 1.0. Verify adx_lot_factor_mid and adx_lot_factor_high are both 1.0 in active config.
- **sell_stop_cont slot expansion**: Slot array expanded from 5 to 10. BUY LIMIT moved to slot[9] (magic +20009). Verify no code still references slot[4] for BUY LIMIT.
- **scribe.py schema gap**: CREATE TABLE for forge_signals doesn't include macd_histogram/m15_adx/lot_factor — relies on ALTER TABLE migrations. Verify all 3 have explicit migrations.
- **Version stamp**: VERSION file must be bumped with each 2.7.x release cycle. scalper_config.json version field is auto-stamped from VERSION on make forge-compile.
- **H1 DI sell gate**: require_h1_di_sell=1 blocks SELL when H1 DI+>=DI-. No ADX bypass (unlike BUY gate which bypasses at counter_buy_adx_threshold=28). Verify this asymmetry is intentional and documented.
- **Cascade slots [2..8] vs [4]**: BUY LIMIT previously at slot[4] now at slot[9]. Any slot loop must scan 0..9 (not 0..4). Verify all three slot loops use `< 10`.

### v2.7.43+ Compose architecture (NEW — added 2026-05-13 after sweeping regime-taxonomy alignment)

- **14 of 21 setup_types use the layered compose** (Filter_AdxFloor → Filter_M15TrendAligned (opt) → Filter_Cooldown → Score_SetupConfidence, each `Filter_*` emitting a SKIP code constructed from `setup_lower` at runtime). These 14 are the v2.7.42 additions: MA_CROSSOVER, VWAP_REVERSION, FIB_CONFLUENCE, INSIDE_BAR, BB_SQUEEZE, ORB, GAP_AND_GO, DOUBLE_TOP, DOUBLE_BOTTOM, HEAD_AND_SHOULDERS, INVERSE_HEAD_AND_SHOULDERS, FLAG_PENNANT, TRENDLINE_BOUNCE, SR_FLIP.
- **7 setups stay monolithic** (BB_BREAKOUT, BB_BREAKOUT_RETEST, BB_BOUNCE, BB_PULLBACK_SCALP, MOMENTUM_DUMP, FRACTIONAL_SELL_IN_BULL, BULL_DAY_DIP_BUY) — their dispatch has gates (H4 RSI/ADX, MACD, hidden-div, BB-contraction, cascade arming, trailing-add) the layered helpers don't yet cover. Migration is §5 Phase 3 work, gated by validation rule.
- **Gate codes for the 14 layered setups are runtime-constructed** — they do NOT appear as literal strings in `ea/FORGE.mq5`. Mandatory Check B MUST enumerate Filter_* call sites (see updated Check B above). Codex's literal-grep approach missed 20 valid gate_legend entries on 2026-05-13 → false-positive WARNING.

### v2.7.44+ RegimeState struct + Phase 2 additive intro

- **`struct RegimeState` exists in EA** (`ea/FORGE.mq5:1020`) with 16 fields across 5 layers. **Populated each tick via `RegimeUpdate(...)` (~ea/FORGE.mq5:7761)** called from `CheckNativeScalperSetups`.
- **Legacy globals STILL EXIST** alongside the struct (Phase 2 is additive — no behavior change). `g_regime_label`, `g_regime_confidence`, `g_daily_*`, `g_adx_trend_regime` are all preserved. Filter chains in the 7 monolithic setups still read them directly. §5 Phase 3 will migrate callers; §5 Phase 4 will delete the legacy globals. Do NOT flag legacy-global usage as "should use g_regime.*" yet — that's planned future work.
- **3 NEW SIGNALS columns** added v2.7.47: `htf_h1_strong INTEGER`, `intraday_label TEXT`, `intraday_counter_htf INTEGER`. Mirror to forge_signals via scribe.py ALTER migrations. Column-index shift in scribe's INSERT loop: trio at r[34..36], v37 atoms at r[37..60], v37g3 at r[61..105].
- **`minutes_into_kz` column** added v2.7.45 to SIGNALS + forge_signals. EA computes fresh at JournalRecordSignal site (not via g_regime.minutes_into_kz) so early-gate SKIP paths fire pre-RegimeUpdate still log accurate values.

### v2.7.46+ New gate codes (all default-OFF, operator opts in)

- **`killzone_trade_cap`** (v2.7.46) — emitted by `ScalperKillzoneCapOK()` when `killzones_max_trades_per_kz` cap is hit. Knob: `FORGE_GATE_KILLZONE_MAX_TRADES` (0=disabled). Counter `g_scalper_killzone_trades` increments on TAKEN, resets on KZ transition + daily reset.
- **`dump_judas_window`** (v2.7.51 §11.4) — emitted in MOMENTUM_DUMP SELL dispatch when killzone=LONDON_OPEN_KZ AND minutes_into_kz<60 AND `dump_judas_window_block` knob is on. Knob: `FORGE_GATE_DUMP_JUDAS_WINDOW_BLOCK` (0=disabled).
- **`kz_warmup`** (v2.7.52) — emitted at top-level dispatch when active KZ AND minutes_into_kz<`kz_warmup_min`. Knob: `FORGE_GATE_KZ_WARMUP_MIN` (0=disabled, 15 typical per arongroups stop-hunt research).
- All 3 throttle via the shared `g_scalper_last_sesswarn_log_bar` marker — co-existence with `session_off`.

### v2.7.49+ EA-anchored time-label authority (FORGE_REGIME_TAXONOMY.md §11.7b)

- **MT5 is the authoritative clock for both killzone AND session labels.** Operator decision 2026-05-13: orders fire from MT5, so EA's broker-clock view is the only one with causal authority.
- **Bridge `_killzone()`** (`bridge.py:631`) reads `forge_session_state.killzone` from `market_data.json` via `get_ea_killzone(MARKET_FILE, max_age_sec=MT5_STALE_SEC)`. Falls back to `get_current_killzone_utc()` only when stale/missing; emits throttled WARN log on fallback (every 5 min max).
- **Bridge `_session()`** (`bridge.py:594`) — same pattern with `get_ea_session()` reading `forge_session_state.label`.
- **athena_api `/api/live`** returns `killzone`+`killzone_local_check` and `session`+`session_local_check` — the `_local_check` fields are bridge's UTC-clock compute used for DIVERGENCE detection only, not as a source of truth.
- **athena_api `/api/health`** intentionally retains `killzone_utc`+`session_utc` — heartbeat fields, not authoritative.
- **aurum.py LENS prompt context** reads `get_ea_session(MARKET_FILE)` at `aurum.py:437` so the agent sees the EA's session label.
- **Dashboard** flips precedence to `D.killzone || D.killzone_local_check` (and same for session); renders divergence in red. Default-state field names: `session_local_check` (not `session_utc`) and `killzone_local_check` (not `killzone_utc`).
- **Window definitions (`kz_*_start_min`)** read from `config/scalper_config.json:session_filter.kz_*_*_min` first (EA-authoritative), env vars second, hard-coded NY-minute defaults third — verified by `trading_session._kz_window()`.

### v2.7.51 §11.4 KZ-aware composite refinements

- **`bull_day_dip_buy_prime_amplifier`** (default 1.0) — multiplies BULL_DAY_DIP_BUY lot factor by N when killzone ∈ {NY_OPEN_KZ, LONDON_CLOSE_KZ}. Wired at `ea/FORGE.mq5:10168-10170`. Silent operation (no SKIP).
- **`intraday_reversal_require_prime_kz`** (default false) — when on, `IsIntradayReversalSellActive()` returns false outside prime KZ (final check at `ea/FORGE.mq5:5196`). Silent operation.
- **`dump_judas_window_block`** (default false) — see new gate codes above.
- `BLOCK_SELL_IN_CHOP` is already always-on (no refinement needed); `CHOP_LADDER_BUY_GRID` composite doesn't exist in EA yet — both intentionally skipped from §11.4.

---

## NOTES

- The review doc path is always `docs/FORGE_ENTRY_CONDITIONS_CODEX_REVIEW.md` (overwrite on each run)
- The Codex sandbox may block file writes — if that happens, the agent reports findings in output and Claude Code writes the file manually from those findings
- Run this skill after any significant change to `ea/FORGE.mq5`, `scalper_config.json`, `FORGE_ENTRY_CONDITIONS.md`, `scribe.py`, or `dashboard/app.js`
- Current EA version: FORGE v2.7.52 (2026-05-13). Last review found 0 FAILs, 1 real WARNING (5 bridge-direct env vars need whitelist entry), 0 real findings beyond hygiene. The codex agent's 20-entry "stale gate_legend" WARNING was a false positive — it missed runtime-constructed codes from Filter_* helpers; the skill's Mandatory Check B now explicitly handles both literal AND constructed codes.
- Run 11 is the next backtest — validate before starting Run 11 that H1 DI sell gate and cascade multi-leg are correctly wired.
- **TAKEN ENTRIES P&L missing cascade deals**: `all_trades` SQL was missing `volume`; cascade magics (+20000..+20009) excluded from P&L. Fixed in 2.7.12 session. Always re-verify `volume` is in SELECT and cascade offsets are summed.
- **lot_per_leg was null**: `volume` not fetched in all_trades query. Fixed. Verify `lot_per_leg` is non-null for all TAKEN entries.
- **Run ID guard**: `btSelRun===btDetail.meta.aurum_run_id` enforced before rendering detail. "Loading run #N…" shown when transitioning. Verify this guard is not removed.
