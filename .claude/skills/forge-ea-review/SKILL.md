---
name: forge-ea-review
description: Validate FORGE EA logic, workflow and intent against documentation and config using codex:rescue. Cross-checks ea/FORGE.mq5 against FORGE_ENTRY_CONDITIONS.md, scalper_config.json, scalper_config.defaults.json, sync_scalper_config_from_env.py, .env, .env.example, scribe.py and regime.py. Documents findings in docs/FORGE_ENTRY_CONDITIONS_CODEX_REVIEW.md. Invoke when the user types /forge-ea-review or asks to "review the forge EA", "validate forge logic", "codex review forge".
---

# /forge-ea-review — FORGE EA Validation Review

You are performing a rigorous technical validation of the FORGE EA entry logic and configuration pipeline.

> **DO NOT HALLUCINATE.** Every claim must cite exact file:line. If code for a claim cannot be found, mark it UNVERIFIED — do not guess or infer.

---

## SOURCE FILES (read ALL before writing anything)

| File | Role |
|------|------|
| `/Users/olasumbo/signal_system/ea/FORGE.mq5` | EA implementation — source of truth |
| `/Users/olasumbo/signal_system/docs/FORGE_ENTRY_CONDITIONS.md` | Intent document — what the EA is supposed to do |
| `/Users/olasumbo/signal_system/config/scalper_config.json` | **Active** runtime config (env overrides applied) |
| `/Users/olasumbo/signal_system/config/scalper_config.defaults.json` | Default values before overrides |
| `/Users/olasumbo/signal_system/scripts/sync_scalper_config_from_env.py` | Maps FORGE_ env vars → JSON config keys |
| `/Users/olasumbo/signal_system/.env` | Active env overrides |
| `/Users/olasumbo/signal_system/.env.example` | **Cheat sheet** — all documented FORGE_ variables with descriptions |
| `/Users/olasumbo/signal_system/python/scribe.py` | Live trading SCRIBE — reads signals/trades from live EA |
| `/Users/olasumbo/signal_system/python/regime.py` | Regime detection — market context used by EA for lot sizing |

---

## VALIDATION PROTOCOL

### Step 1 — Read all source files

Before writing any output, read:
1. `docs/FORGE_ENTRY_CONDITIONS.md` — every claim to validate
2. `scalper_config.json` (active config, not defaults)
3. `ea/FORGE.mq5` lines relevant to each claim
4. `sync_scalper_config_from_env.py` for variable mapping integrity
5. `.env.example` for variable documentation coverage

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
- Regime labels used in `ForgeResolveNumTrades` that must match what `regime.py` produces
- Any config keys read by scribe/regime that are not in `scalper_config.json`

### Step 5 — Write output report

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

## Section 9 — scribe.py / regime.py Cross-Check
| Check | File:line | Status | Notes |
|-------|-----------|--------|-------|

## Issues Found (Consolidated)
| # | Severity | Section | Description | Action |
|---|----------|---------|-------------|--------|

## Overall Verdict
[Summary paragraph: what is working, what needs fixing, confidence level in the EA logic]
```

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
5. After writing the file, output a brief summary of PASS/WARNING/FAIL counts.
```

---

## WHAT TO REPORT

When the review completes, report:
1. Total PASS / WARNING / FAIL / UNVERIFIED counts
2. All FAIL items — exact description and affected gate/feature
3. All WARNING items — potential issues and recommended investigation
4. Whether the output file was written successfully
5. Any dead variables (in `.env` but not in sync script)
6. Any schema mismatches found in scribe.py or regime.py

---

## NOTES

- The review doc path is always `docs/FORGE_ENTRY_CONDITIONS_CODEX_REVIEW.md` (overwrite on each run)
- The Codex sandbox may block file writes — if that happens, the agent reports findings in output and you must write the file manually from those findings
- Run this skill after any significant change to `ea/FORGE.mq5`, `scalper_config.json`, or `FORGE_ENTRY_CONDITIONS.md`
- The previous review (Run 10 session) found 4 FAILs — all fixed. This skill re-runs the same validation after each EA change cycle.
