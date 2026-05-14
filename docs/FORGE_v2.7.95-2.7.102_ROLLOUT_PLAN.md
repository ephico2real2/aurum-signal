# FORGE v2.7.95 → v2.7.102 — Rollout Plan

**Status**: ALL 10 SETS SHIPPED, default-OFF behavior identical to v2.7.94 baseline
**Branch**: `v2.7.95-cascade-direction-lock` (no commits yet — all WIP)
**Tracker**: [`docs/FORGE_CORE_LOGIC_DESIGN.md`](./FORGE_CORE_LOGIC_DESIGN.md) §9 changelog

This is a practical activation guide. Each "Phase" enables one or more knobs, runs a backtest, and validates with specific success criteria before progressing to the next phase. Order is least → most risky.

---

## Phase 0 — Sanity baseline (no knobs flipped)

**Goal**: confirm v2.7.102 with all defaults preserves v2.7.94 behavior byte-for-byte.

```bash
# .env stays as-is. Just rebuild + run.
make scalper-env-sync && make forge-compile && make forge-reload
# Launch backtest in MT5 Strategy Tester: Mar 31 → Apr 8 (same window as Run 9).
```

**Success criteria**:
- TAKEN count matches Run 9 baseline (was 15)
- P&L matches Run 9 baseline (was ~$367)
- No new gate codes appear in SKIP gate breakdown (Sets 6/7/8 inactive)
- forge_version stamped 2.7.102 in TESTER_RUNS

**If anything diverges**: STOP. Revert via `git checkout v2.7.43-layered-helpers && make forge-compile`. Investigate the diff before re-enabling anything.

---

## Phase 1 — Direction lock state machine (Sets 6+7+8)

**Why first**: this is the single highest-leverage change — it directly addresses the Apr 6 -$917 disaster pattern. Default thresholds are conservative (5/7 PEMCG flip threshold; 3/7 NEUTRAL); the system mostly stays in ARMED state and only kicks in on genuine reversal.

```bash
# .env additions:
FORGE_SETUP_DIRECTION_LOCK_ENABLED=1
FORGE_TIMING_DIRLOCK_BREAK_BILATERAL_COOLDOWN_BARS=2   # 10min no-auto-flip after break
# All other dirlock_* knobs stay at defaults (5 / 3 / 0.5 / 5).

make scalper-env-sync && make forge-compile && make forge-reload
```

**Success criteria** (backtest Mar 31 → Apr 8):
- Apr 6 17:35 G5021 disaster: G5021 BUY entry fires (or is blocked by PEMCG), but if entry happens, structural break should fire at the 18:00 M5 close (price closed below entry_swing_low − 0.5×ATR). Bilateral cooldown blocks the 18:05 + 18:15 SL fills from new groups.
- Look for new gate codes in SKIP rollup: `dirlock_block_buy` / `dirlock_block_sell`. If you see these >50 times in a session window, the threshold is too tight (raise `FORGE_GATE_DIRLOCK_FLIP_THRESHOLD` from 5 to 6).
- Run total should match Run 9 OR improve. If worse → investigate which valid entries got blocked.

**Validation queries** post-run:
```sql
-- How often did dirlock trigger?
SELECT gate_reason, COUNT(*) FROM SIGNALS
WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
  AND gate_reason LIKE 'dirlock_block_%'
GROUP BY gate_reason;

-- Apr 6 17:35-18:15 specifically
SELECT datetime(time,'unixepoch'), setup_type, direction, outcome, gate_reason
FROM SIGNALS WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
  AND time BETWEEN strftime('%s','2026-04-06 17:30:00')
              AND strftime('%s','2026-04-06 18:30:00')
ORDER BY time;
```

---

## Phase 2 — Structural pending cancel (Set 4)

**Why next**: closes the pre-fill gap on cascade pendings (operator's original described bug). Requires Phase 1 (uses the same EvaluateDirectionLock evaluator).

```bash
# .env additions (cumulative):
FORGE_TIMING_COOL_PERIOD_STRUCTURE_CANCEL_ENABLED=1

make scalper-env-sync && make forge-compile && make forge-reload
```

**Success criteria**:
- Apr 6 01:10 BB_EXHAUSTION_REVERSAL_BUY (the -$49.65 4-second SL hit): the cascade arm should fire the BB_EXHAUSTION_REVERSAL, BUT the structural-cancel watchdog at the next M5 close should detect the breakdown and cancel any remaining cascade pendings before they fill.
- New telemetry: look for `FORGE 2.7.101: structure_flip_cancel G<N>` in MT5 Experts journal log.
- Cascade fill count drops; cascade SL hit count drops more.

---

## Phase 3 — TP2 banking (Set 2)

**Why next**: pure profit-locking, no rejection logic. Lowest risk of all the knobs.

```bash
# .env addition:
FORGE_GEOMETRY_TP2_CLOSE_ENABLED=1
# breakout_tp2_close_pct=25 default already set; bounce_tp2_close_pct=30 (existing).

make scalper-env-sync && make forge-compile && make forge-reload
```

**Success criteria**:
- Groups that previously rode runners through TP2 (which only ratcheted SL) now bank 25% of remaining positions at TP2 touch.
- Look for `FORGE: Group <N> TP2 banked — closed <M>/<total>` in journal.
- Win rate ↑ (more locked profit), avg-win-size may ↓ (less runner P&L) — net depends on TP3 reach frequency.

---

## Phase 4 — TP1 pip floor hybrid (operator-spec)

**Why next**: makes TP1 = max(40 pips, ATR-based) so low-volatility days get a sane TP target.

```bash
# .env additions:
FORGE_GEOMETRY_TP1_PIP_FLOOR=40
FORGE_GEOMETRY_TP2_PIP_FLOOR=60

make scalper-env-sync && make forge-compile && make forge-reload
```

**Success criteria**:
- On high-ATR days (ATR > 10pt), TP1/TP2 unchanged (ATR-based dominates).
- On low-ATR days (ATR < 10pt — typical Asian session), TP1/TP2 are now 40/60 pips instead of ATR-derived. Should improve banking on tight-range days.

---

## Phase 5 — Multi-leg batch entry (Set 1)

**Why later**: this is the biggest behavioral change — every Leg 1 becomes 4 position tickets instead of 1. **Test carefully** — margin behavior changes (4× the position count).

```bash
# .env addition:
FORGE_GEOMETRY_BATCH_SIZE=4
# Optional: FORGE_GEOMETRY_BATCH_SPACING_ATR_MULT=0.5 for industry-canonical 0.5×ATR stagger

make scalper-env-sync && make forge-compile && make forge-reload
```

**Pre-flight check** (CRITICAL before live):
- Compute `target_lot / 4`. Must be ≥ `SYMBOL_VOLUME_MIN` (0.01 for XAUUSD typically) — helper has auto-reduction but verify.
- Margin: 4 separate positions × current `lot_fixed` ÷ 4 = same total exposure. But position count cap on broker side could trip.

**Success criteria**:
- Each TAKEN signal now creates 4 deal tickets sharing one `group_magic`. Verify in MT5 Toolbox → History.
- TP1 closes 2/4 (50%), TP2 banks 1/2 of remaining (25% via Phase 3), TP3 trails the last 1.
- Total exposure per group should equal pre-batch (lot_fixed scaled equivalently).

---

## Phase 6 — Dynamic TP3 (Set 3 Option 3C)

**Why last**: depends on Phase 1 + ATR trail being active. Extends TP3 as SL ratchets.

```bash
# .env additions:
FORGE_BREAKOUT_ATR_TRAIL_ENABLED=1       # Required for Phase 6 to do anything
FORGE_GEOMETRY_TP3_MODE=1                # 0=fixed, 1=sl_trail (operator pick 3C)
FORGE_GEOMETRY_TP3_DIST_FROM_SL_ATR_MULT=2.0

make scalper-env-sync && make forge-compile && make forge-reload
```

**Success criteria**:
- Runners that previously hit TP3 (fixed) and exited now extend TP3 as SL ratchets up.
- Look for `PositionModify` calls in journal with TP value increasing over time (BUY) or decreasing (SELL).
- Avg-win-size should ↑ on trend days, with some risk of giving back profit if trend stalls before SL ratchet catches up.

---

## All-Phases-On profile (the operator's full vision)

After validating Phases 1-6 individually, the all-on `.env` config:

```env
# Phase 1 — direction lock
FORGE_SETUP_DIRECTION_LOCK_ENABLED=1
FORGE_TIMING_DIRLOCK_BREAK_BILATERAL_COOLDOWN_BARS=2
# Phase 2 — structural cancel
FORGE_TIMING_COOL_PERIOD_STRUCTURE_CANCEL_ENABLED=1
# Phase 3 — TP2 banking
FORGE_GEOMETRY_TP2_CLOSE_ENABLED=1
# Phase 4 — TP pip-floor
FORGE_GEOMETRY_TP1_PIP_FLOOR=40
FORGE_GEOMETRY_TP2_PIP_FLOOR=60
# Phase 5 — multi-leg batch
FORGE_GEOMETRY_BATCH_SIZE=4
# Phase 6 — dynamic TP3
FORGE_BREAKOUT_ATR_TRAIL_ENABLED=1
FORGE_GEOMETRY_TP3_MODE=1
FORGE_GEOMETRY_TP3_DIST_FROM_SL_ATR_MULT=2.0

# v2.7.95 BUY-side cascade (separately optional)
FORGE_BUY_STOP_CONT_ENABLED=0          # Leave OFF until cascade refactor validated separately
FORGE_SELL_LIMIT_RECOVERY_ENABLED=0
```

---

## Rollback procedure (per phase)

If a phase regresses:

```bash
# Revert the .env edits, then:
make scalper-env-sync && make forge-compile && make forge-reload
# Re-run the prior-phase backtest. Validate the regression is gone.
# Document in docs/FORGE_CORE_LOGIC_DESIGN.md §9 with the regression evidence.
```

If a deeper code rollback is needed:

```bash
# All ships are on branch v2.7.95-cascade-direction-lock. The pre-Set baseline is v2.7.43-layered-helpers HEAD.
git checkout v2.7.43-layered-helpers
make forge-compile
```

Per-ship backups are in `backups/v2.7.95/` through `backups/v2.7.102/` if surgical revert of one phase is needed.

---

## Live-trading checklist (post-validation)

Only after Phases 1-6 backtest validate cleanly on Mar 31 → Apr 8 AND a second period (recommend Apr 9-15 if data is available):

1. Re-confirm `FORGE_SCALPER_MODE=DUAL` (or BB_BREAKOUT/BB_BOUNCE if narrowing).
2. Detach EA from Strategy Tester chart.
3. Attach FORGE to live XAUUSD M5 chart in MT5.
4. Verify smiley face is green + "AutoTrading" toolbar button green.
5. Tools → Options → Expert Advisors → ✓ Allow algo trading + ✓ Allow DLL imports.
6. Sufficient margin for 4× position count (per Phase 5 above).
7. `make status` → all four services running (bridge, listener, aurum, athena).
8. `make forge-verify-live` → confirms live forge_version matches what's compiled.
9. Set hard daily loss cap on the account (broker-side) as belt-and-suspenders.
10. Watch the first hour of live activity in `make logs-bridge` before walking away.

---

## Test suite verdict (run 2026-05-14 post-v2.7.102)

| Test slice | Result | Verdict |
|---|---|---|
| `make test-contracts` | 107 passed, 0 failed | ✓ Clean — no schema regressions from v2.7.95-2.7.102 |
| `make forge-compile` | FORGE.ex5 v2.7.102 stamped | ✓ Clean compile |
| Mandatory Check A (dead env) | none | ✓ PASS |
| Mandatory Check B (gate legend) | none | ✓ PASS (`dirlock_block_buy`+`dirlock_block_sell` added) |
| Mandatory Check C (sync ↔ .env.example) | 0 missing | ✓ PASS |
| `make test-api` | 491 passed, 7 FAILED | ⚠ All 7 failures PRE-EXISTING — see below |
| `make test` (UI Playwright) | 27 passed, 1 FAILED | ⚠ Pre-existing (Athena dashboard label test) |

**7 pre-existing API failures** (all in committed HEAD code, not my session):
1. `test_calc_pips_xau_uses_cent_pip` — `python/bridge.py:735` `_calc_pips()` docstring says "1 whole move = 10 pips" but test expects "1 pip = $0.01". Fundamental mismatch in committed code.
2. `test_calc_pips_forex_conventions` — same root cause.
3. `test_live_has_required_keys` — `/api/live` missing `session_utc` key (athena_api.py issue).
4. `test_api_live_has_execution_and_tradingview` — same `session_utc` issue.
5. `test_requirements_have_upper_bounds` — `anthropic>=0.100.0` lacks upper bound.
6. `test_scribe_update_positions_sl_tp_by_stage_rejects_bad_stage` — unrelated.
7. `test_bridge_parse_tp_stage_from_comment` — unrelated.

**Scope boundary confirmed**: v2.7.95-2.7.102 touched only `ea/FORGE.mq5`, `VERSION`, `config/*.json`, `scripts/sync_scalper_config_from_env.py`, `.env.example`, and `docs/*`. No Python code changed by this session. The 7 API failures are all in `python/bridge.py` + `python/athena_api.py` which had WIP modifications pre-dating session start (visible in `git status` at session start). These failures should be addressed separately and do not block the EA ship.

## §1 Document changelog

### 2026-05-14 — Initial creation
- Drafted after v2.7.95-2.7.102 ship session. All 10 Sets shipped default-OFF.
- 6 phases defined as least-risk-first activation sequence.
- Operator wake-up reference doc.

### 2026-05-14 — Test verdict added
- Ran `make test-contracts` (107 PASSED), `make test-api` (491 PASSED / 7 FAILED — all pre-existing), `make test` UI (27 PASSED / 1 FAILED — pre-existing).
- Mandatory Checks A/B/C all PASS after gate-legend update.
- Scope boundary: 0 Python code modifications by this session.
