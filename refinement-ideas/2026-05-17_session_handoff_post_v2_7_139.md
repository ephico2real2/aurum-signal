# Session handoff — 2026-05-17 (post v2.7.139 M7 fold)

**Purpose**: drop-in context for the next Claude session. Read this + `~/.claude/projects/-Users-olasumbo-signal-system/memory/project_m7_pre_stabilization_batch.md` and you're fully oriented.

**Where we stopped**: 4 commits shipped this session. M7 ICT-canonical fold is done. M8 OTE_RETRACEMENT fold is the next ship — deliberately paused before starting to (a) let the operator validate v2.7.137/138/139 in the MT5 tester and (b) avoid stacking deferred-state surgery on top of unvalidated M7.

---

## §1 Repo state at handoff

| Item | Value |
|---|---|
| Branch | `v2.7.129-mode-d-cleanup` |
| Last commit | `5c1ac43 feat(forge+ict): v2.7.139 — M7 ICT-canonical fold ship (MSS_CONTINUATION)` |
| EA version (`VERSION` + `FORGE_VERSION` constant) | `2.7.139` |
| `ea/FORGE.mq5` size | 17,925 lines (started session at 18,387 → −462) |
| `FORGE.ex5` size | ~603 KB (started at ~610 KB → −7 KB) |
| Working tree | Clean (no uncommitted code changes; only operator's untracked backups: `.env.backup-pre-dedup-20260515-220637`, `athena_phase2/`, `backups/`, `python/bridge.py.backup-pre-b1-strip-20260515-222625`) |
| Test suite | 72/72 pass (`tests/api/test_m7_fold.py` 17 + `tests/api/test_forge_27x_gates.py` 55) |

**Commits in this session** (`git log --oneline -5`):

```
5c1ac43 feat(forge+ict): v2.7.139 — M7 ICT-canonical fold ship (MSS_CONTINUATION)
d375ff5 feat(forge): v2.7.138 (v2.7.137a tech-debt) — RETIRE MA_CROSSOVER + MOMENTUM_DUMP v1
823193e docs(forge): canonical ICT-aligned 5-tier decision stack reference
b6629c0 feat(forge+ict): v2.7.137 — pre-M7 stabilization batch (R21 MagicGuard + R22 KZ + R24 OB ring + R27 batch comment + cosmetic R29/R30 + R17 doc)
08a4e9f docs(ict): canonical setup catalog FORGE_ICT_SETUPS.md (post-consensus-gate fold map)
```

---

## §2 Operator directives (foundational — internalize before doing ANYTHING)

These were given explicitly in this session. The next session MUST honor them:

1. **"only implement solutions that are part of our final design"** — no tactical band-aids. R32 (dump-BUY counter-trend gate) was REJECTED for exactly this reason — the canonical answer is the ISS gate (v2.7.116), not per-setup RSI ceilings. If you find a loss pattern, log it as an R-number in `refinement-ideas/improvement-recommendations/INDEX.md` and DEFER to the canonical fix.
2. **"don't wanna retire it?"** — when a retire is in scope per design (MA_CROSSOVER, MOMENTUM_DUMP v1), don't hesitate. Just execute methodically with each layer's cleanup.
3. **"is the forge.ea getting smaller"** — operator tracks progress via file-size deltas. Surface `wc -l ea/FORGE.mq5` after each substantial cut.
4. **"1 then 2 then 3 then 4"** — execute sequentially without re-asking. They want momentum.
5. **"ICT only now and update by using ASCII to FORGE_DECISION_STACK.md"** — `docs/FORGE_DECISION_STACK.md` is now the canonical ICT-only reference. NO pre-ICT references (PEMCG/UMCG/CVCSM/DTC) in the active design. Future docs follow same rule.
6. **"we don't need MOMENTUM_DUMP and MOMENTUM_DUMP_COMPOSITE at the same"** — operator's pattern: when bespoke + atom-composed both exist, retire bespoke once composite validates. R33 (BB_PULLBACK_SCALP → atom_pullback_in_ote) follows same pattern.

Cross-reference: `~/.claude/projects/-Users-olasumbo-signal-system/memory/` — full memory tree, especially the foundational mandate memories from 2026-05-17.

---

## §3 What's DONE (committed, validated, on disk)

### v2.7.137 stabilization batch (commit `b6629c0`)
- R21: MagicNumber-change orphan guard — state file `forge_magic_state.txt` + `MagicBaseGate_Init()` + 4 entry-site gates
- R22: Cat 1 NY_AM_KZ alias + Cat 3 NY_PM_KZ canonical (replaces stale LONDON_CLOSE_KZ proxy)
- R24: OB ring scans NEWEST→OLDEST (was oldest-first, wrong for fast markets)
- R27: `Forge_OverrideTpOrLeg()` helper + `PlaceMarketBatch` uses it (preserves 6/7-segment comment shape)
- R29: comment text `breaker_present(3)` → `atom_ob_broken(3)`
- R30: `FORGE_ICT_COMMENT_CODES.md §8` status table updated
- R17: `FORGE_SETUP_ICT_MAP.md §B.4` revised (consensus-gate audit; M7 scope = 6 keep + 1 provisional + 3 reclassify + 2 retire)
- `tests/api/test_m7_fold.py` created (17 tests)
- Bonus: `config/gate_legend.json` stale `ces_below_threshold` → `iss_below_threshold`

### Decision-stack canonical doc (commit `823193e`)
- `docs/FORGE_DECISION_STACK.md` — ICT-only 5-tier reference with ASCII diagram (Indicators → Atoms → Composites → Setup+Gates → Geometry+Management)
- All pre-ICT architecture (PEMCG/UMCG/CVCSM/DTC) removed from the active design narrative
- Cross-linked to `FORGE_SETUP_ICT_MAP.md`, `FORGE_ICT_SETUPS.md`, skill §J.1 + §I.8

### v2.7.138 retire ship (commit `d375ff5`)
- **MA_CROSSOVER fully retired** — `DetectMaCrossoverEvent` deleted, 45-line trigger block deleted, 7 struct fields + defaults + JSON loaders + 2 cooldown globals + lot-factor block + MarkSetupCooldownAnchorOnTaken branch all gone; 7 env knobs removed from `.env` / `.env.example` / sync script / `defaults.json`
- **MOMENTUM_DUMP v1 fully retired** — 314-line trigger block at FORGE.mq5:13229-13542 deleted; 10 v1-only struct fields + defaults + JSON loaders deleted; 3 cooldown-anchor globals deleted; 11 `setup_type == "MOMENTUM_DUMP"` checks renamed → `"MOMENTUM_DUMP_COMPOSITE"` (composite is the canonical successor and inherits all v1 lot/RR/pyramid features); 10 v1-only env knobs removed
- **Preserved** (composite uses): `dump_lot_factor`, `dump_buy/sell_lot_factor`, `dump_sl/tp_atr_mult_*`, `dump_max_hold_seconds`, all `dump_v2_*`, `dump_buy/sell_h4/macd/vwap/poc/*`, `dump_dist/kz_amplifier_*`, `dump_pyramid_*`, `dump_cascade_enabled`, `dump_legs_per_group`, `dump_max_open_same_direction`, `dump_sell_min_rsi`, `dump_sell_block_below_bb_l`, `dump_below_bbl_block_max_rsi`

### v2.7.139 M7 fold (commit `5c1ac43`)
- **New SIGNALS column `setup_subtype TEXT`** — full 5-layer schema parity (EA CREATE + ALTER + INSERT col list + INSERT VALUES bind + scribe.py CREATE + ALTER + SELECT + INSERT + placeholder count 168→169)
- **Global-set pattern** — `g_setup_subtype_for_next_signal` declared near Layer-4 telemetry globals; set at each fire site BEFORE setup_type; **reset at TOP of `CheckNativeScalperSetups`** every tick (NOT inside JournalRecordSignal, which would break MarkSetupCooldownAnchorOnTaken)
- **8 fire-site rewrites** (BB_BREAKOUT×2, GAP_AND_GO, MOMENTUM_DUMP_COMPOSITE, BB_SQUEEZE, GRINDING_SELL, NY_SESSION_BEARISH_BREAKOUT_SELL, INSIDE_BAR-provisional) — each emits `setup_type = "MSS_CONTINUATION_" + direction` + sets subtype global
- **25 downstream `setup_type == "<LEGACY>"` checks renamed** to `g_setup_subtype_for_next_signal == "<legacy_lower>"` (lot factor stack, RR bypass, MarkSetupCooldownAnchorOnTaken branches, BB_BREAKOUT anchor block)
- **17 M7-fold tests pass** (14 prev-xfail M7-arrival tests + 3 stays-correct invariants for M8/M9 reclassified setups)
- **55 existing regression tests pass** (after M7-aware refactor of 3 wired_end_to_end tests + retire-invariant rewrites for MA_CROSSOVER and dump_judas_window tests)

---

## §4 What's PENDING (deliberately deferred)

### Step 4 — v2.7.140 M8 OTE_RETRACEMENT fold (next ship)

**Scope**: 13 fire sites across 10 setups (vs M7's 8 sites / 7 setups). Follow the same global-set pattern as M7.

**Fire-site map** (verified 2026-05-17 post-v2.7.139):

| Setup | Fire sites | Lines in FORGE.mq5 | Notes |
|---|---|---|---|
| `BB_BOUNCE` | 2 | 12266, 12351 | Direct fire-site assignment |
| `BB_PULLBACK_SCALP` | 2 | 12224, 12318 | **R33 retire-candidate** — Phase 1 lands here as fold + subtype; Phase 3 retire ships post-M8 validation |
| `BB_LOWER_REVERSION_BUY` | 1 | 13317 | BUY-only |
| `FIB_CONFLUENCE` | 1 | 13646 | Direct |
| `VWAP_REVERSION` | 1 | 13614 | Direct |
| `BULL_DAY_DIP_BUY` | 1 | 13582 | BUY-only |
| `TREND_CONTINUATION_BUY` | 1 | 13478 | BUY-only |
| `FRACTIONAL_SELL_IN_BULL` | 1 | 13563 | SELL-only |
| `BB_BREAKOUT_RETEST` | 2 | 12814, 13170 | **DEFERRED-STATE pattern** — `g_retest.setup_type = "BB_BREAKOUT_RETEST"` is set at arm-time, NOT at fire-time. Need to find the actual fire site (where the retest condition triggers and the order is placed) and apply M7-style fold there |
| `FLAG_PENNANT` | 1 | 14102 | Verify whether it uses deferred-state too |
| `INTRADAY_REVERSAL_SELL` | 0 | — | No direct fire site found — likely emitted via composite variant. Investigate before deleting from M8 scope or excluding |

**M7 design pattern to follow** (per `refinement-ideas/M7-design/2026-05-17_m7-mss-continuation-fold.md §4.2`):

```mql5
// At each direct fire site:
g_setup_subtype_for_next_signal = "<legacy_lower>";  // M8
setup_type = "OTE_RETRACEMENT_" + direction;  // M8 (was: "<LEGACY>")
```

**Deferred-state nuance** (BB_BREAKOUT_RETEST, possibly FLAG_PENNANT):
- The `g_retest.setup_type = "BB_BREAKOUT_RETEST"` assignment at lines 12814/13170 is a STATE-MACHINE MARKER for the retest engine. Don't change that line.
- Find where `g_retest.setup_type` is CONSUMED at actual fire time (search `g_retest.setup_type` reads) — that's the M8 fold site.
- At consume time: set subtype global from g_retest field, then emit `setup_type = "OTE_RETRACEMENT_" + direction`.

**Downstream setup_type comparison refactor**:
- After fold, `setup_type == "BB_BOUNCE"` etc. won't match (the new value is `"OTE_RETRACEMENT_BUY"`). Use the same Python rename as v2.7.139:

```python
.venv/bin/python << 'PYEOF'
import re
src = open("ea/FORGE.mq5").read()
mapping = {
    "BB_BOUNCE": "bb_bounce", "BB_PULLBACK_SCALP": "bb_pullback_scalp",
    "BB_LOWER_REVERSION_BUY": "bb_lower_reversion_buy",
    "FIB_CONFLUENCE": "fib_confluence", "VWAP_REVERSION": "vwap_reversion",
    "BULL_DAY_DIP_BUY": "bull_day_dip_buy",
    "TREND_CONTINUATION_BUY": "trend_continuation_buy",
    "FRACTIONAL_SELL_IN_BULL": "fractional_sell_in_bull",
    "BB_BREAKOUT_RETEST": "bb_breakout_retest", "FLAG_PENNANT": "flag_pennant",
}
total = 0
for legacy, sub in mapping.items():
    old = f'setup_type == "{legacy}"'
    new = f'g_setup_subtype_for_next_signal == "{sub}"'
    n = src.count(old)
    src = src.replace(old, new)
    total += n
    print(f"  {legacy}: {n} replacements")
open("ea/FORGE.mq5", "w").write(src)
print(f"Total: {total}")
PYEOF
```

**Test scaffolding** — extend `tests/api/test_m7_fold.py` OR create parallel `tests/api/test_m8_fold.py` with the same pattern but for M8:
- `M8_KEEP_SETUPS = [...]` (the 10 setups above)
- Same Layer 1/2/3/4 schema-parity checks (but `setup_subtype` already exists — those tests should still pass; only `OTE_RETRACEMENT_BUY/SELL` string assertions are new)
- Per-setup fold-correctness tests (mirror `test_m7_keep_setup_emits_mss_continuation`)
- Stays-correct invariants for M9 reclassified setups (`ORB`) NOT folded into M8

**CHANGELOG entry** — follow the v2.7.139 structure (schema-parity layers / global-set pattern / fire-site rewrites table / downstream rename count / test validation / out-of-scope deferred items).

**Version bump** — `VERSION` + `FORGE_VERSION` constant: `2.7.139 → 2.7.140`.

**R33 Phase 1** — `BB_PULLBACK_SCALP` folds to `OTE_RETRACEMENT_BUY/SELL` with subtype = `"bb_pullback_scalp"`. No deletion in M8. R33 Phase 3 (delete the bespoke BB-band detector + replace with canonical `atom_pullback_in_ote` Mode B/C gate) ships AFTER post-M8 validation per the two-phase retire pattern in `docs/FORGE_DECISION_STACK.md §7`.

### R14 — tester validation pass on v2.7.137/138/139 baseline (CRITICAL BEFORE M8)

The "test before production" mandate (per `feedback_quant_expert_identity` memory) was not honored on the 4 commits in this session — they shipped without R14 validation. Operator should run the MT5 tester to verify:

1. **R21 state file**: confirm `~/Library/Application Support/.../Common/Files/forge_magic_state.txt` is written with `last_magic_base=202401` on first attach; no `FORGE INIT R21 🚨 BLOCK` lines in the journal.
2. **R22 Cat 3 NY_PM_KZ**: query `SELECT killzone, SUM(atom_kz_fav_liq_sweep) FROM SIGNALS WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS) GROUP BY killzone` — Cat 3 should now favor `NY_PM_KZ` (not `LONDON_CLOSE_KZ`).
3. **R24 OB ring freshness**: `atom_ob_broken` count should be healthy (~20% breakage rate observed in earlier Run 4).
4. **R27 batch comment shape**: when batch fires, broker comments stay at 6 or 7 `|`-segments with `L1`/`L2` in the correct slot.
5. **v2.7.138 retire validation**: `setup_type = "MOMENTUM_DUMP"` count in SIGNALS should be ZERO (v1 retired); `setup_type = "MA_CROSSOVER"` count ZERO; MOMENTUM_DUMP_COMPOSITE TAKENs should fire normally and exhibit all the v1 lot/pyramid/cascade features now inherited.
6. **v2.7.139 M7 validation**: TAKEN signals should emit `setup_type = "MSS_CONTINUATION_BUY"` / `_SELL` for the 6 fold setups; `setup_subtype` column populated with the legacy name; downstream lot factors / cooldown anchors continue to work (read via subtype global within the same tick).

Trigger phrase: `/forge-monitor` or `test mon` per skill `forge-monitor` LIVE-MODE-vs-TESTER-MODE protocol.

### R31 — `BB_PULLBACK_SCALP` consensus-gate canon check (M8 prereq, low priority)

The original M7 Explore audit missed `BB_PULLBACK_SCALP`. The canonical-classification check confirmed M8 OTE is the right destination (BB middle = dynamic equilibrium ≈ OTE band). Not a blocker; this is just documentation that the canon-check was done out-of-band.

### R32 — MOMENTUM_DUMP BUY counter-trend trap (DEFERRED — structural answer is ISS gate, not band-aid)

Per operator directive: NO per-setup RSI/h1 band-aid gate. The structural fix is the ISS gate at v2.7.116 (when `iss_score < 5` → SKIP). MOMENTUM_DUMP_COMPOSITE BUY at MSS=0 + FVG=0 = ISS=0/10 → would skip. Stays in INDEX.md as OPEN — closes naturally when v2.7.116 ships.

### R33 — `BB_PULLBACK_SCALP` retire (Phase 3, post-M8 validation)

Sequenced AFTER M8 ships. Pattern per the two-phase retire (`FORGE_DECISION_STACK.md §7`):
1. **M8** = Phase 1 — fold to `OTE_RETRACEMENT_BUY/SELL` with `setup_subtype = "bb_pullback_scalp"`. No logic change.
2. **Post-M8 backtest** = Phase 2 — compare `atom_pullback_in_ote` fire rate vs `bb_pullback_scalp` fire rate; verify canonical equivalent-or-better.
3. **v2.7.141+** = Phase 3 — retire bespoke detector entirely (delete sites at FORGE.mq5:12224 / 12318 + `g_sc.pullback_scalp_*` knobs).

### ISS atom wiring (v2.7.113-115) + ISS hard-gate activation (v2.7.116)

The structural answer to direction-failure traps. Currently `iss_score` always 0 (atoms stubbed in v2.7.112). When MSS/FVG/ChoCH detection wires real values (v2.7.113-115) and `FORGE_GATE_ISS_BLOCK_BELOW_THRESHOLD=1` flips ON (v2.7.116), the gate auto-blocks all the counter-trend / no-confirmation traps. Sequence this AFTER M8 ships and is validated.

### R28 — EA ALTER TABLE swallows errors (codex review concern #7)

Pre-existing finding. Low priority unless tester surfaces silent migration failures. Defer to a focused codex review when M9 ships.

### R23 — Cat 3 wick-quality tier (codex review concern #2)

Pre-existing. Wick-quality scoring is binary; spec says 0/1/2 tier. Affects LIQ_SWEEP composite calibration. Ship before promoting Cat 3 Mode A → B.

---

## §5 Critical context the next session MUST know

### 5.1 The 5-tier ICT-canonical decision stack

Lives in `docs/FORGE_DECISION_STACK.md` with full ASCII diagram. The 5 tiers top-down per tick:
1. **T1 Indicators** — raw market state
2. **T2 Atoms** — pure-function ICT boolean primitives
3. **T3 Composites** — weighted scores (4 category composites + ISS general, max 10)
4. **T4 Setup Trigger + Gates** — Mode A/B/C decision; emits `setup_type` = MSS_CONTINUATION / OTE_RETRACEMENT / LIQUIDITY_SWEEP_REVERSAL / BREAKER_RETEST
5. **T5 Geometry + Management** — structural SL/TP/lot + post-placement ratchet

**M7/M8/M9 are LAYER 4 RENAMES** — no behavior change to atoms / composites / gates / geometry / management. Only the `setup_type` label changes (with `setup_subtype` preserving legacy identity).

### 5.2 The global-set pattern for `setup_subtype` (CRITICAL — don't violate)

- `g_setup_subtype_for_next_signal` is set at each fire site BEFORE `setup_type = "MSS_CONTINUATION_" + direction`
- It is RESET at the TOP of `CheckNativeScalperSetups` every tick (line ~11648 area), NOT inside `JournalRecordSignal`
- This allows downstream same-tick consumers (`MarkSetupCooldownAnchorOnTaken` at FORGE.mq5:15704; the BB_BREAKOUT cooldown block at FORGE.mq5:15695) to read the subtype AFTER the TAKEN `JournalRecordSignal` call
- **Anti-pattern**: do NOT reset in `JournalRecordSignal`. That broke the cooldown anchor logic in my first attempt during this session — I had to revert mid-implementation.

### 5.3 The schema-parity 5-layer ship contract (`docs/FORGE_DECISION_STACK.md §6`)

Every new column added to T2 (atom output) or T3 (composite score) must land in **all 5 layers in the SAME commit**:
- Layer 1: EA CREATE TABLE IF NOT EXISTS SIGNALS
- Layer 2: EA ALTER TABLE SIGNALS ADD COLUMN (idempotent migration)
- Layer 3: EA JournalRecordSignal INSERT col list + VALUES bind (read from global, NOT positional-param thread per skill §I.11.1)
- Layer 4: `python/scribe.py` — CREATE TABLE + ALTER + SELECT + INSERT col list + tuple-build + placeholder count math
- Layer 5: `schemas/aurum_tester.sql` (file doesn't exist; scribe is the mirror)

Failure mode of skipping any layer: silent INSERT failures, dashboard goes dark, scribe sync errors. Historical incidents: v2.7.45/47 (12-hour dashboard outage), v2.7.112 (missing migrations). Don't repeat.

### 5.4 The two-phase retire pattern (bespoke → canonical successor)

When a bespoke detector has an atom-composed canonical successor (MOMENTUM_DUMP → MOMENTUM_DUMP_COMPOSITE was the canonical example; BB_PULLBACK_SCALP → atom_pullback_in_ote is the next):

- **Phase 1**: fold the bespoke under the new ICT setup_type, preserve identity in `setup_subtype` (no logic change). Both detectors keep firing.
- **Phase 2**: parallel validation period; compare fire rates / win rates / drawdowns.
- **Phase 3**: operator decision → delete bespoke entirely (fire sites + env knobs + struct fields).

Documented in `docs/FORGE_DECISION_STACK.md §7`. Memorialized 2026-05-17 from MOMENTUM_DUMP retirement.

### 5.5 The consensus gate (skill §I.15)

Before designing on top of agent findings (Explore / codex / WebSearch), verify the finding against (a) canonical spec + (b) ICT-canon WebSearch. If 2/3 disagree, **retire / reclassify / replace** before designing. M7 design originally accepted all 11 Explore-found setups; consensus gate caught MA_CROSSOVER (retire), BB_BREAKOUT_RETEST + FLAG_PENNANT (→M8), ORB (→M9). Saved the design from shipping 4/11 misclassifications.

### 5.6 Operator's foundational mantras (CLAUDE.md global rules)

- **Best code, always** — production quality or don't ship
- **No fake implementations, no placeholder stubs that "look done"**
- **No dead code** — when retiring, delete the infrastructure (struct fields, defaults, JSON loaders, env knobs) too
- **Schema-parity 5-layer ship** — see §5.3 above
- **Build-before-commit** — `make forge-compile` clean before staging
- **Commit attribution**: operator is primary author. NO `Co-Authored-By: Claude` trailers in commit messages. Default footer: nothing.
- **NEVER delete the repo** — absolute fail-safe per project CLAUDE.md. No `rm -rf`, no `git reset --hard`, no force-push to main, no `git clean -fdx`. Backup files (`.env.backup-*`, `athena_phase2/`, `backups/`) stay untracked — never `git add -A` (which I tripped on once this session and had to unstage).

---

## §6 Memory pointers

Read these from `~/.claude/projects/-Users-olasumbo-signal-system/memory/`:

| File | Why |
|---|---|
| `MEMORY.md` | Index — auto-loaded each session |
| `project_m7_pre_stabilization_batch.md` | Final state of this 4-commit session (now also references this handoff doc) |
| `feedback_full_ict_alignment_mandate.md` | Why ICT alignment is the design target |
| `feedback_quant_expert_identity.md` | "Best code, always" + research discipline + Wall Street quality bar |
| `feedback_consensus_gate_for_findings.md` | The consensus gate pattern (§5.5 above) |
| `feedback_no_dead_env_vars.md` | Every FORGE_* env var must be fully wired or removed |
| `feedback_decision_log_mandate.md` | Decision log requirements for each ship (skill §I.11) |
| `feedback_never_delete_repo.md` | The absolute fail-safe (§5.6 above) |
| `project_pemcg_retirement_target.md` | Why PEMCG/CVCSM/BB_EXHAUSTION are behaviorally retired (Mode D) — context for the ICT-only doc rewrite |

---

## §7 Validation commands the next session should run FIRST

```bash
# 1. Confirm clean state
git log --oneline -5
git status -s | head -20

# 2. Verify v2.7.139 compiles
make forge-compile 2>&1 | grep -iE "error|warning|Stamped|FORGE.ex5" | head -5

# 3. Test suite green
.venv/bin/python -m pytest tests/api/test_m7_fold.py tests/api/test_forge_27x_gates.py -q 2>&1 | tail -3
# Expected: 72 passed in <1s

# 4. EA size sanity
wc -l ea/FORGE.mq5
# Expected: ~17,925

# 5. R21 state file (post-tester-attach check)
cat "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/forge_magic_state.txt"
# Expected: last_magic_base=202401 + symbol=XAUUSD + last_seen_utc=...
```

---

## §8 The implementation cookbook for M8 (Step 4)

If the operator wants to proceed with M8 next session, here's the recipe (mirrors the v2.7.139 process):

1. **Bump VERSION** to 2.7.140 + `FORGE_VERSION` constant in `ea/FORGE.mq5:83`
2. **Investigate INTRADAY_REVERSAL_SELL** — 0 fire sites found; figure out if it's emitted via composite, deferred state, or genuinely absent. Decide: include in M8 or remove from §B.4 M8 list
3. **Investigate BB_BREAKOUT_RETEST deferred-state fire** — find where `g_retest.setup_type` is read at actual fire time; that's where the M7-style fold pattern applies (not at the arm-time placeholder set at FORGE.mq5:12814 / 13170)
4. **Investigate FLAG_PENNANT** — verify whether it uses deferred-state or direct fire pattern at FORGE.mq5:14102
5. **Apply the fire-site rewrite Python script** (see §4 above; adapt the M7 Python script with the M8 setup map)
6. **Apply the downstream rename Python script** (see §4 above)
7. **`make forge-compile`** — expect 0 errors / 0 warnings
8. **Create or extend `tests/api/test_m8_fold.py`** mirroring `test_m7_fold.py` structure with M8 setup list
9. **Run full test suite** — expect 72 + new M8 test count, all passing
10. **CHANGELOG entry** — follow the v2.7.139 entry shape (schema-parity layers / global-set pattern / fire-site rewrites table / downstream rename count / test validation / out-of-scope deferred items)
11. **Update `refinement-ideas/improvement-recommendations/INDEX.md`** — mark M8-related R-numbers SHIPPED
12. **Update memory `project_m7_pre_stabilization_batch.md`** — append M8 ship state
13. **Commit** with `feat(forge+ict): v2.7.140 — M8 OTE_RETRACEMENT fold ship` format. **NO `Co-Authored-By: Claude` trailer.**
14. **R33 status update** — INDEX.md R33 entry: Phase 1 SHIPPED (bb_pullback_scalp folded); Phase 2 = post-M8 backtest comparison; Phase 3 = v2.7.141+ retire

After M8 ships, the canonical sequence per `docs/FORGE_DECISION_STACK.md §7` retire pattern is M9 (LIQUIDITY_SWEEP_REVERSAL fold of ORB + chart-pattern remnants + ASIA_CAPITULATION_BUY + BB_EXHAUSTION_REVERSAL_*) → ISS atom wiring (v2.7.113-115) → ISS gate activation (v2.7.116) → R33 Phase 3 + other bespoke-detector retires.

---

## §9 Outstanding R-list (priority for next sessions)

From `refinement-ideas/improvement-recommendations/INDEX.md`:

| R# | Status | Priority | Sequence |
|---|---|---|---|
| R17 | SHIPPED v2.7.137 | — | done |
| R18 | SHIPPED v2.7.139 | — | done |
| R21-R30 | SHIPPED v2.7.137 + v2.7.138 | — | done |
| R31 | OPEN — prerequisite for M7/M8 (now M7 done; M8 is next) | low | absorbed into M8 |
| R32 | OPEN — superseded by ISS gate v2.7.116 (no per-setup band-aid) | low | wait for ISS |
| R33 | OPEN — POST-M8 (Phase 1 lands with M8; Phase 3 ships v2.7.141+) | medium | sequential |
| R14 | OPEN — tester validation pass | **CRITICAL** | NEXT — before M8 |
| R23 | OPEN — Cat 3 wick-quality tier (binary → 0/1/2) | medium | before Mode B promotion |
| R28 | OPEN — EA ALTER TABLE swallows errors | low | defer |
| (others R1-R30 various OPEN states for ISS atoms, lot-pattern slicer, QuestDB schema, etc.) | OPEN | various | per ISS roadmap |

---

## §10 Where to find things

| File | What |
|---|---|
| `docs/FORGE_DECISION_STACK.md` | Canonical ICT 5-tier decision stack reference (the doc to read FIRST) |
| `docs/FORGE_SETUP_ICT_MAP.md §B.4` | The fold map (M7-M9) post-consensus-gate audit |
| `docs/FORGE_SETUP_ICT_MAP.md §B.8.2` | Per-category atom catalog with weights |
| `docs/FORGE_ICT_SETUPS.md` | Canonical setup catalog (setup_type ↔ subtype mapping) |
| `docs/FORGE_ICT_COMMENT_CODES.md` | Broker comment grammar |
| `refinement-ideas/M7-design/2026-05-17_m7-mss-continuation-fold.md` | M7 design doc (now SHIPPED; mostly historical but §4 implementation patterns apply to M8) |
| `refinement-ideas/improvement-recommendations/INDEX.md` | All open improvements (R1-R33+) |
| `tests/api/test_m7_fold.py` | M7 test harness (17 tests; template for M8 tests) |
| `CHANGELOG.md` | Full v2.7.137/138/139 entries — read for context |
| `ea/FORGE.mq5` | The EA (17,925 lines; setup_subtype machinery at lines 290+, JournalRecordSignal at 10460+, CheckNativeScalperSetups at 11644+) |
| `python/scribe.py` | The scribe mirror (forge_signals schema + sync_forge_journal at line 1374+) |

---

## §11 Sanity check before starting any work

Run these in order. If any fails, STOP and diagnose:

```bash
# 1. We're in the right repo + branch
pwd && git branch --show-current
# Expected: /Users/olasumbo/signal_system + v2.7.129-mode-d-cleanup

# 2. v2.7.139 is the last commit
git log --oneline -1
# Expected: 5c1ac43 feat(forge+ict): v2.7.139 — M7 ICT-canonical fold ship (MSS_CONTINUATION)

# 3. VERSION + EA constant agree
cat VERSION
grep "FORGE_VERSION = " ea/FORGE.mq5 | head -1
# Both should say 2.7.139

# 4. EA compiles clean
make forge-compile 2>&1 | grep -iE "error|warning" | head -5
# Expected: no output

# 5. Tests green
.venv/bin/python -m pytest tests/api/test_m7_fold.py tests/api/test_forge_27x_gates.py -q 2>&1 | tail -3
# Expected: 72 passed
```

If all 5 pass, the next session can safely proceed with Step 4 (M8) per the cookbook in §8 — or pause for the operator's R14 tester validation pass first.
