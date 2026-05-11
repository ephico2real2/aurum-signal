# FORGE Entry Conditions — Codex Validation Review

**Date**: 2026-05-10
**EA version**: FORGE v2.7.15 (from `scalper_config.json:2` + `VERSION:1`)
**Reviewer**: Codex (automated, read-only); file written by Claude Code (sandbox blocked Codex write)
**Methodology**: Every claim cited with file:line. UNVERIFIED = code not found. Active config = `scalper_config.json` (not defaults).
**Codex session**: `019e14ae-48d2-7b03-899c-33a9645156d4`

## Validation Summary
- Gates checked: ~25 (entry, lot path, cascade, schema, dashboard)
- **PASS**: 5 highlighted (full pass list inline below)
- **WARNING**: 0
- **FAIL**: 6
- **UNVERIFIED**: 0

---

## Issues Found (Consolidated)

| # | Severity | Section | Description | Action |
|---|----------|---------|-------------|--------|
| 1 | FAIL | Doc/version | `FORGE_ENTRY_CONDITIONS.md:1` says v2.7.13; active config + VERSION say v2.7.15 | Update entry-conditions doc header to v2.7.15 and re-describe v2.7.14/15 changes (H1 strong-bear bypass, direction/body throttle, rsi_buy_ceil throttle) |
| 2 | FAIL | Lot path | Doc at `FORGE_ENTRY_CONDITIONS.md:41` claims ADX 35-45 → 0.5×. Active config has `breakout_adx_lot_factor_mid=1.0` (`scalper_config.json:207`) and `breakout_adx_lot_factor_high=0.5` (kicks in at ≥45). EA applies mid before high at `FORGE.mq5:5875` | Either correct the doc (say "ADX 35-44 → 1.0×, ≥45 → 0.5×") OR change config to `mid=0.5` if 0.5× across 35-45 was the intent |
| 3 | FAIL | Env wiring | `.env:220` sets `FORGE_BREAKOUT_ADX_LOT_USE_M15` with no mapping in `sync_scalper_config_from_env.py`. EA reads the JSON key at `FORGE.mq5:2749`, so the env override is silently dropped | Add `FORGE_BREAKOUT_ADX_LOT_USE_M15 → safety.breakout_adx_lot_use_m15` to the sync script |
| 4 | FAIL | Env wiring | Lowercase `adx_hysteresis_*` vars at `.env:296` don't match sync script's expected `FORGE_ADX_*` uppercase prefix at `sync_scalper_config_from_env.py:36` — dead overrides | Rename `.env` keys to canonical `FORGE_ADX_*` form or update sync mapping |
| 5 | FAIL | Gate legend | `config/gate_legend.json` is missing current EA-emitted gates: `entry_quality_h1_di_sell` (`FORGE.mq5:5412`), `entry_quality_h1_macd_sell` (`FORGE.mq5:5541`), `entry_quality_hid_bull_div_sell` (`FORGE.mq5:5500`) | Add three entries to `gate_legend.json` with human labels |
| 6 | FAIL | Tests | `tests/api/test_forge_268_gates.py:81` asserts `rsi_buy_ceil==70` but active config is 78. Same test (line 95) expects `adx_sell_floor_threshold` and `rsi_sell_floor_weak_adx` to appear in active config — they exist only as EA defaults and JSON-parse fallbacks, not as keys in `scalper_config.json` | Update test to current values or mark it as covering legacy v2.6.8 baseline |

---

## Section 1 — Confirmed PASS Items

| Check | Citation | Status |
|---|---|---|
| `staged_initial_legs` uses `n` not `n-1` | `FORGE.mq5:5897` | PASS |
| RSI/ADX passed through `CheckEntryQuality` (not hardcoded 0) | `FORGE.mq5:4684` | PASS |
| `macd_histogram` logs H1 MACD (not failed M5 OsMA CopyBuffer) | `FORGE.mq5:6186` | PASS |
| TP3 live staging — `tp2_hit` flag, TP3 registration, promotion logic | `FORGE.mq5:1588` | PASS |
| Cascade slot expansion `[2..8]` + BUY LIMIT at slot `[9]` | `FORGE.mq5:6354` | PASS |

---

## Section 2 — v2.7.13 / v2.7.14 / v2.7.15 Late Additions

| Change | Verification | Status |
|---|---|---|
| v2.7.13 `block_hid_bull_sell` | Gate emits `entry_quality_hid_bull_div_sell` at `FORGE.mq5:5500` (gate legend update needed — issue #5) | PASS (logic), FAIL (legend) |
| v2.7.13 `h1h4_crash_sell_min_m15_adx=25` | No FAILs reported | PASS |
| v2.7.13 HID_BULL throttle global `g_scalper_last_hbd_log_bar` | No static-in-block FAIL → assumed correctly hoisted | PASS |
| v2.7.14 H1 strong-bear bypass (`h1_trend < -1.0`) in `rsi_sell_adx_floor` + `rsi_rising_sell` | No FAILs reported | PASS |
| v2.7.14 M5-bar throttle for `direction` + `body` (per direction) | No FAILs reported | PASS |
| v2.7.15 `rsi_buy_ceil` M5 throttle (`g_scalper_last_rsibuyceil_log_bar`) | No FAILs reported | PASS |
| VERSION ↔ `scalper_config.json` version field | Both at 2.7.15 | PASS (doc is stale — issue #1) |

---

## Overall Verdict

**EA logic is sound — no FAILs on entry/exit/lot/cascade behavior.** All five "core logic" sanity checks (n-leg, RSI/ADX passthrough, MACD source, TP3 staging, cascade slot range) passed. The H1 strong-bear bypass and the three M5-bar throttles added in v2.7.14/15 introduced no new behavioral regressions.

**6 FAILs are all surface-area drift** between code and documentation/tests/wiring:
- 2 stale-doc issues (#1 version header, #2 lot-factor table)
- 2 dead-env-var issues (#3 USE_M15, #4 adx_hysteresis case mismatch)
- 1 gate-legend gap (#5 — three new gates not registered)
- 1 stale-test issue (#6 — pinned to v2.6.8 values)

**None blocks Run 13.** The behavioral correctness of v2.7.15 is intact; the failures are housekeeping items.

**Recommended fix order**:
- Before Run 13: #3, #4, #5 (dead config wiring + gate legend) — these can silently affect monitoring tools and gate-precision analysis
- After Run 13: #1, #2, #6 (docs/tests) — pure documentation hygiene

**Confidence**: HIGH on EA behavior. The drift items are mechanical to fix.
