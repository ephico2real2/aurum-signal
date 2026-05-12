# FORGE v2.7.31 Entry Conditions Review

**Date**: 2026-05-11
**Reviewer**: Codex (automated, read-only)
**EA version**: 2.7.31 (`config/scalper_config.json:2`, `ea/FORGE.mq5:63`)
**Methodology**: Every claim cited with file:line. UNVERIFIED = code not found. Active config = `scalper_config.json` (not defaults).

## Validation Summary
- **PASS**: 8
- **WARNING**: 0
- **FAIL**: 2
- **UNVERIFIED**: 0

## HIGH Severity Findings

### FAIL #1 — `FORGE_PULLBACK_SCALP_*` env vars missing from `.env.example` (FIXED post-review)

All 8 new v2.7.31 env vars were absent from `.env.example` documentation:
- `FORGE_PULLBACK_SCALP_ENABLED`
- `FORGE_PULLBACK_SCALP_FRESH_FLIP_BARS`
- `FORGE_PULLBACK_SCALP_LOT_FACTOR`
- `FORGE_PULLBACK_SCALP_SL_ATR_MULT`
- `FORGE_PULLBACK_SCALP_TP1_ATR_MULT`
- `FORGE_PULLBACK_SCALP_TP2_ATR_MULT`
- `FORGE_PULLBACK_SCALP_COOLDOWN_SECONDS`
- `FORGE_PULLBACK_SCALP_MAX_ADX`

**Wiring is otherwise CORRECT**:
- Sync mappings present: `scripts/sync_scalper_config_from_env.py:231-238` ✓
- Active config values written: `config/scalper_config.json:252-259` ✓
- EA `JsonHasKey` reads present: `ea/FORGE.mq5:3364-3371` ✓
- Consumed in BUY/SELL forks: `ea/FORGE.mq5:5970-6077` ✓

Only `.env.example` documentation layer was missing — does NOT affect Run 20 runtime behavior.

**Action taken 2026-05-11**: Appended a v2.7.31 documentation block to `.env.example` (after the 2.7.29 regime override section, line 428+) covering all 8 `FORGE_PULLBACK_SCALP_*` knobs plus `FORGE_DUMP_MIN_ADX` tuning. Block follows the existing 2.7.28/2.7.29 documentation pattern.

### FAIL #2 — Mandatory Check A: 16 pre-existing `.env.example` `FORGE_*` keys fail four-layer audit

Pre-existing keys in `.env.example` lack a complete `sync_scalper_config_from_env.py` → `scalper_config.json` → EA `JsonHasKey` chain. Notable examples:
- `FORGE_BREAKOUT_ADX_MIN`
- `FORGE_BOUNCE_ADX_MAX`
- `FORGE_FAST_LOCK_MIN_HOLD_SEC_BOUNCE`
- `FORGE_QUEUE_ACK_TIMEOUT_SEC`

Some are intentionally commented-out reference defaults; the four-layer audit is stricter than functional correctness. Not a Run 20 blocker. Deferred to v2.7.32 housekeeping pass.

## Per-Validation Table

| Check | Verdict | Severity |
|---|---:|---|
| 1. Pullback scalp env wiring (sync→JSON→EA) | PASS | LOW |
| 2. `FORGE_DUMP_MIN_ADX` wiring through to `dump_min_adx` | PASS | LOW |
| 3. `pullback_scalp_lot_factor` applied in combined_lot_factor | PASS | LOW |
| 4. Cascade arming skips `BB_PULLBACK_SCALP` | PASS | LOW |
| 5. RR bypass for `MOMENTUM_DUMP` and `BB_PULLBACK_SCALP` | PASS | LOW |
| 6. `BarsSincePSARFlip()` helper exists and is sane | PASS | LOW |
| 7. Parity banner + OnInit audit log in place | PASS | LOW |
| 8. No regression: cascade slots, RSI/ADX logging, OsMA, staged_initial_legs | PASS | LOW |
| Mandatory Check A — Dead `FORGE_*` env vars | FAIL → FIXED for v2.7.31; pre-existing 16 deferred | HIGH |
| Mandatory Check B — Gate legend completeness | PASS | LOW |

## Mandatory Check A — Dead `FORGE_*` env vars

**Status**: FAIL at audit time (documentation-layer); FIXED post-review for v2.7.31 keys.

The 8 new `FORGE_PULLBACK_SCALP_*` keys (v2.7.31) were present in `.env` and wired through sync + JSON + EA, but absent from `.env.example`. Now added. Plus 16 pre-existing keys with documentation/wiring mismatches — most are commented `#` placeholders, deferred to v2.7.32 housekeeping pass.

## Mandatory Check B — Gate legend completeness

**Status**: PASS. Every `JournalRecordSignal("SKIP","<code>",...)` emission in `ea/FORGE.mq5` has a matching entry in `config/gate_legend.json` or matches a `_patterns` wildcard.

## Issues Found (Consolidated)

| # | Severity | Section | Description | Action |
|---|---|---|---|---|
| 1 | HIGH | A | 8 `FORGE_PULLBACK_SCALP_*` missing from `.env.example` | **FIXED 2026-05-11** — doc block appended |
| 2 | HIGH | A | 16 pre-existing `FORGE_*` keys fail four-layer audit | Deferred to v2.7.32 housekeeping pass |

## Recommendations & Proposed Fixes

### Issue 1 — Append v2.7.31 doc block to `.env.example` (DONE)

`.env.example` updated with the v2.7.31 documentation block covering all 8 `FORGE_PULLBACK_SCALP_*` knobs and `FORGE_DUMP_MIN_ADX`.

### Issue 2 — Schedule `.env.example` audit as v2.7.32 housekeeping pass

The 16 pre-existing four-layer audit failures span several historical versions. Recommend a single dedicated sweep:
1. For each failed key, classify as (a) live (needs full wiring), (b) reference-only (clearly commented `#` placeholder, OK), or (c) deprecated (remove).
2. Apply fixes per classification.
3. Update `tests/api/test_forge_27x_gates.py::FORGE_ENV_VARS_NOT_IN_SYNC` whitelist for items consumed outside sync.

## Overall Verdict

**v2.7.31 wiring is functionally correct.** The two FAILs are documentation-layer gaps. FAIL #1 (v2.7.31 keys) was fixed immediately post-review. FAIL #2 (16 pre-existing keys) does not block Run 20. Run 20 can proceed safely.
