# M7 Design — Fold 11 legacy setups → MSS_CONTINUATION_BUY/SELL

**Status**: DESIGN — DRAFT (awaiting Explore agent output on the 11 setups; will refine below before code starts)
**Anchor spec**: `docs/FORGE_SETUP_ICT_MAP.md §B.4`
**Atom spec**: `docs/FORGE_SETUP_ICT_MAP.md §B.8.2 Category 1` (MSS_CONTINUATION = MSS(3) + displacement(2) + FVG_aligned(2) + FVG_unfilled(1) + KZ_favorable(1) + HTF_aligned(1) = 10)
**Pre-conditions**: per self-audit Dimension B (2026-05-17), R14 (validation of v2.7.131-136) and R11 (test harness) are prerequisites. Either ship them first or ship them ATOMICALLY WITH M7.

---

## §1 Purpose

Collapse 11 legacy entry triggers into ONE ICT-canonical `setup_type` (`MSS_CONTINUATION_BUY` / `MSS_CONTINUATION_SELL`) per the §B.4 mandate. The fold:

- **Doesn't change strategy logic** — same triggers fire under new umbrella names
- **Does change observability** — `setup_type` becomes ICT-canonical; new `setup_subtype` column preserves original-trigger identity for ablation studies
- **Does change comment scheme** — `<CAT>_<DIR>` segment of broker comment becomes `MSS_CONT_B` / `MSS_CONT_S` for all 11 (instead of legacy `BB_BREAKOUT_B` / `MOMENTUM_DUMP_BUY` / etc.)

**Honest scope-check** (per self-audit recommendation R13): M7 doesn't improve win-rate. It's a rename + observability ship. KZ/SK behavioral changes (R13) are what would actually move the win-rate needle. Operator confirmed forward motion on M7 anyway.

---

## §2 The 11 setups (verified mapping per Explore agent 2026-05-17)

| # | Legacy setup_type | Subtype id | Direction | Enable flag (config field) | Default ON? | Source lines | Trigger sites |
|---|---|---|---|---|---|---|---|
| 1 | `BB_BREAKOUT` | `bb_breakout` | BIDIRECTIONAL | `g_sc.breakout_enabled` (hardcoded, no env) | **YES** (line 4781) | 12826 (BUY), 13181 (SELL) | 2 |
| 1b | `BB_BREAKOUT_RETEST` (variant) | `bb_breakout_retest` | BIDIRECTIONAL | (retest arm of #1) | — | 12818, 13173 | 2 (variant fires) |
| 2 | `MA_CROSSOVER` | `ma_crossover` | BIDIRECTIONAL | `g_sc.ma_crossover_enabled` (`FORGE_SETUP_MA_CROSSOVER_ENABLED`) | no (line 4955) | 13962 | 1 |
| 3 | `ORB` | `orb` | BIDIRECTIONAL | `g_sc.orb_enabled` (`FORGE_SETUP_ORB_ENABLED`) | no (line 5003) | 14136 | 1 |
| 4 | `GAP_AND_GO` | `gap_and_go` | BIDIRECTIONAL | `g_sc.gap_and_go_enabled` (`FORGE_SETUP_GAP_AND_GO_ENABLED`) | no (line 5015) | 14169 | 1 |
| 5 | `MOMENTUM_DUMP` | `momentum_dump` | BIDIRECTIONAL | `g_sc.dump_catch_enabled` (`FORGE_DUMP_CATCH_ENABLED`) | no (line 4872) | 13389 (SELL), 13522 (BUY) | 2 |
| 6 | `MOMENTUM_DUMP_COMPOSITE` | `momentum_dump_composite` | BIDIRECTIONAL | `g_sc.momentum_dump_composite_enabled` (`FORGE_MOMENTUM_DUMP_COMPOSITE_ENABLED`) | no (line 5100) | 13550 | 1 |
| 7 | `BB_SQUEEZE` | `bb_squeeze` | BIDIRECTIONAL | `g_sc.bb_squeeze_enabled` (`FORGE_SETUP_BB_SQUEEZE_ENABLED`) | no (line 4992) | 14100 | 1 |
| 8 | `FLAG_PENNANT` | `flag_pennant` | BIDIRECTIONAL | `g_sc.flag_pennant_enabled` (`FORGE_SETUP_FLAG_PENNANT_ENABLED`) | no (line 5049) | 14481 | 1 |
| 9 | `INSIDE_BAR` | `inside_bar` | BIDIRECTIONAL | `g_sc.inside_bar_enabled` (`FORGE_SETUP_INSIDE_BAR_ENABLED`) | no (line 4983) | 14064 | 1 |
| 10 | `GRINDING_SELL` | `grinding_sell` | SELL-only | `g_sc.grinding_sell_enabled` (`FORGE_SETUP_GRINDING_SELL_ENABLED`) | **YES** (line 5410) | 12511 | 1 |
| 11 | `NY_SESSION_BEARISH_BREAKOUT_SELL` | `ny_session_bearish_breakout_sell` | SELL-only | **NO ENABLE FLAG** (filter chain at 13726) | always-on when filters pass | 13729 | 1 |

**Total**: 14 trigger sites across 11 legacy setup_types (BB_BREAKOUT + MOMENTUM_DUMP have 2 each; BB_BREAKOUT_RETEST is a variant at the same 2 sites).

### Key findings from Explore audit

1. **Only 2 setups are default-ON**: `BB_BREAKOUT` (hardcoded `true`, no env knob) + `GRINDING_SELL`. The other 9 must be operator-enabled.
2. **`BB_BREAKOUT_RETEST` is NOT independent** — it's a retest-arm of `BB_BREAKOUT` that fires when retest conditions are met (deferred immediate entry). Should fold as a sub-variant subtype.
3. **`MOMENTUM_DUMP_COMPOSITE` is described as a REPLACEMENT for legacy `MOMENTUM_DUMP`** running in parallel for validation. Post-M7 they BOTH map to `MSS_CONTINUATION_*` but `setup_subtype` distinguishes — preserves ablation-study fidelity.
4. **`NY_SESSION_BEARISH_BREAKOUT_SELL` has no enable flag** — fires whenever filter chain passes. Needs an explicit `g_sc.ny_session_bearish_breakout_sell_enabled` field added as part of M7 (per `feedback_no_dead_env_vars` — every setup must have a knob).
5. **`BB_BREAKOUT` is hardcoded ON with no env** — should also gain `FORGE_SETUP_BB_BREAKOUT_ENABLED` for parity. Listed as M7 sub-improvement.

---

## §3 Schema changes

### §3.1 SIGNALS — new `setup_subtype` column (TEXT)

```sql
ALTER TABLE SIGNALS ADD COLUMN setup_subtype TEXT DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_sig_setup_subtype ON SIGNALS(setup_subtype);
```

Stores the legacy trigger identifier (`bb_breakout`, `momentum_dump`, etc.). After M9, this column lets analysts answer "which of the 11 legacy triggers fired this MSS_CONTINUATION_BUY?" without breaking the unified `setup_type='MSS_CONTINUATION_BUY'` group-by.

### §3.2 TRADES — no schema change needed

Group magic preserves attribution via SIGNALS join.

### §3.3 scribe.py forge_signals — mirror the column

Same ALTER block pattern; `has_setup_subtype` SELECT flag; placeholder count 168 → 169.

### §3.4 Schema-parity 5-layer wire (per `feedback_full_ict_alignment_mandate`)

| Layer | Site |
|---|---|
| EA CREATE TABLE SIGNALS | Add `setup_subtype TEXT DEFAULT ''` |
| EA ALTER TABLE migration | Idempotent ADD COLUMN |
| EA JournalRecordSignal INSERT col list | Add `setup_subtype` |
| EA JournalRecordSignal VALUES bind | Add `'" + setup_subtype_local + "'` (string literal) |
| scribe.py forge_signals schema + migration + sync_forge_journal | Mirror |

---

## §4 Code surface change pattern

For each of the 11 legacy setups, at the fire-site:

**Before (legacy)**:
```mql5
string setup_type = "BB_BREAKOUT";
// ... trigger logic ...
JournalRecordSignal("TAKEN", "", setup_type, direction, ...);
```

**After (M7)**:
```mql5
string setup_type    = "MSS_CONTINUATION_" + direction;  // _BUY or _SELL
string setup_subtype = "bb_breakout";
// ... same trigger logic (UNCHANGED) ...
JournalRecordSignal("TAKEN", "", setup_type, direction, setup_subtype, ...);
```

The `JournalRecordSignal` signature gains a `setup_subtype` parameter (defaulted to `""` for legacy / non-MSS_CONT call sites until M8/M9 fold them too).

---

## §5 Comment-scheme integration (v2.7.132 zone-leading + M7 ICT setup_type)

The v2.7.132 `Forge_BuildScalpComment()` helper accepts `setup_or_cat` and applies `Forge_AppendDirectionSuffix`. For M7 setups, the call becomes:

```mql5
Forge_BuildScalpComment("MKT", "MSS_CONT", direction, group_id, tp_label,
                         g_regime.killzone, g_regime.silver_bullet,
                         g_ict_last_mss_cont_score_buy);  // pass composite score for conviction
```

Result: comment shape becomes `KZ_MKT|MSS_CONT_B|G5001|TP1|LDN_OPEN_KZ|H` (the canonical ICT shape from `docs/FORGE_ICT_COMMENT_CODES.md`).

**Conviction tag bug** (caught during M7 design — needs fix): the v2.7.132 `Forge_BuildScalpComment()` calls pass `-1` for composite_score everywhere. After M7, MSS_CONT entries should pass the ACTUAL `g_ict_last_mss_cont_score_<dir>` value so the comment carries `H/M/L` conviction instead of `?`. This becomes a 1-line change per fire-site.

---

## §6 Migration order (recommended)

Conservative — one setup per "sub-ship" to allow rollback of individual setups if issues surface:

| Sub-ship | Folds | Why this order |
|---|---|---|
| M7a | BB_BREAKOUT + BB_BREAKOUT_RETEST | Canonical "structure-break" setup; closest to MSS canon; lowest risk |
| M7b | MA_CROSSOVER | Simplest direction-bake; smallest code surface |
| M7c | ORB + GAP_AND_GO | Session-opener structural breaks; semantically clean |
| M7d | MOMENTUM_DUMP + MOMENTUM_DUMP_COMPOSITE | Displacement-leg setups; primary MSS_CONT volume in current tester data |
| M7e | BB_SQUEEZE + FLAG_PENNANT + INSIDE_BAR | Pattern-based; lower current volume |
| M7f | GRINDING_SELL + NY_SESSION_BEARISH_BREAKOUT_SELL | Direction-baked legacy setups; cleanup last |

Each sub-ship = single commit. Total: 6 commits across one extended session OR one bundled commit if confidence high.

**Bundled vs. incremental**: per `feedback_dont_overask` — operator's call. Recommend BUNDLED (single v2.7.137 commit, all 11 folds) because:
- Schema change is shared (one ALTER block)
- Comment-scheme integration is shared (one fire-site pattern)
- Tester validation can cover all 11 in one run
- Atomic rollback if something breaks

---

## §7 Test plan (closes R11 + R14 from self-audit)

**Pre-flight (R14 — before M7 commits)**:
- One fresh tester run on v2.7.136 — verify all 4 composites populate, all 11 legacy setups still fire, SeedScalperGroupCounter log present
- F-β.2 histogram across all 4 categories — baseline

**M7 validation (closes R11 — tests ship in same PR)**:
- Python harness `tests/test_m7_fold.py` — uses sqlite3 against tester DB:
  - For each of the 11 legacy subtypes, verify SIGNALS rows have `setup_type='MSS_CONTINUATION_<DIR>'` AND `setup_subtype=<legacy_name>`
  - Verify count(setup_type='MSS_CONTINUATION_BUY') matches sum of legacy BUY-direction counts
  - Verify comment shape: TRADES.comment LIKE 'KZ_MKT|MSS_CONT_%' for ≥80% of post-fold trades (some setups may have non-MKT order types)
  - Verify conviction tag is no longer '?' for ≥80% of trades (composite scores ARE populating)
- F-β.2 histogram re-run with fold — should show same TOTAL trades, redistributed under MSS_CONT umbrella

**Rollback**:
- M7 introduces NO new strategy logic — only renames. Rollback = git revert + tester pass to confirm legacy names restored.
- `setup_subtype` column is additive — survives rollback as a dead column (no DROP).

---

## §8 Breaking changes (downstream impact)

| Downstream | Impact | Mitigation |
|---|---|---|
| scribe.py `_parse_tp_stage_from_comment` | Already handles both legacy + new shapes per v2.7.132 dual-parser at FORGE.mq5:3529 | None needed |
| `scripts/fbeta2_histogram.py` | Currently groups by `setup_type` — will show legacy names disappear + MSS_CONT increase | Re-run after fold; visual confirmation |
| `docs/missed_opportunities/INDEX.md` analysis docs | Reference legacy setup names | Stays correct historically; new pattern docs use ICT-canonical |
| `make monitor-forge-skips` rollup | Groups SKIP gate_reasons (not setup_types) | No impact |
| ATHENA dashboards (if grep'ing setup_type literals) | May break | Out of scope; surface as `R<N>` improvement-recommendation if hit |
| `.env` `FORGE_SETUP_*_ENABLED` flags | Stay as-is — each legacy trigger still has its own enable flag | None |

---

## §8b Per-finding consensus check (mandatory per skill §I.15, codified 2026-05-17)

**Audit gap caught by operator**: §B.4 lists 11 setups to fold under MSS_CONTINUATION without per-setup canon check. My initial design accepted Explore's findings + §B.4's spec at face value, skipping ICT-canon verification. Per skill §I.15 the consensus gate is: **agent finding + canonical spec + ICT-canon WebSearch must agree**. Running it retroactively here:

| Setup | Explore (agent) | §B.4 (spec) | ICT canon (WebSearch) | Consensus | Action |
|---|---|---|---|---|---|
| BB_BREAKOUT | exists, 2 trigger sites | fold to M7 | band-break + §B.8.2 displacement atom = MSS criterion ✓ | **PASS** | Keep in M7 |
| BB_BREAKOUT_RETEST | retest variant of #1 | fold to M7 | by definition a retracement entry → OTE pattern | **FAIL — wrong category** | Reclassify to M8 |
| MA_CROSSOVER | exists, EMA20×EMA50 | fold to M7 | [ICT explicitly avoids MAs / lagging indicators](https://eplanetbrokers.com/training/ict-trading-strategy-explained) | **FAIL — not ICT canon** | **RETIRE — do not migrate** |
| ORB | exists, session range break | fold to M7 | session/IPDA opening range IS a liquidity zone — break is sweep, not continuation | **FAIL — wrong category** | Reclassify to M9 (LIQ_SWEEP_REV) |
| GAP_AND_GO | exists, gap-and-go logic | fold to M7 | gap IS a displacement leg | **PASS** | Keep in M7 |
| MOMENTUM_DUMP | exists, 2 sites | fold to M7 | M5 displacement = canonical MSS_CONT primary signal | **PASS** | Keep in M7 |
| MOMENTUM_DUMP_COMPOSITE | exists, supersedes #5 | fold to M7 | same displacement primitive, atom-composed | **PASS** | Keep in M7 |
| BB_SQUEEZE | exists | fold to M7 | accumulation→expansion = IPDA phase = displacement | **PASS** | Keep in M7 |
| FLAG_PENNANT | exists | fold to M7 | [bull flag fits ICT as "BOS pole + valid pullback"](https://innercircletrader.net/tutorials/bull-flag-pattern-trading-strategy/) — flag IS the OTE retracement | **FAIL — wrong category** | Reclassify to M8 (OTE_RETRACEMENT) |
| INSIDE_BAR | exists | fold to M7 | consolidation→expansion = mini-displacement, but also classic chart pattern; ambiguous | **PROVISIONAL** | Operator call: keep in M7 OR retire |
| GRINDING_SELL | exists | fold to M7 | multi-bar slow-displacement = slow MSS variant | **PASS** | Keep in M7 |
| NY_SESSION_BEARISH_BREAKOUT_SELL | exists, no flag | fold to M7 | session-open displacement break + Killzone-tagged MSS | **PASS** | Keep in M7 (+ add missing enable flag) |

**Consensus result**: 7/12 PASS, 4/12 FAIL (3 reclassify + 1 retire), 1/12 PROVISIONAL.

The original §B.4 was **partially wrong** — it pre-classified all 11 as MSS_CONT without per-setup canon check. This audit + skill §I.15 codification means future fold-specs go through this gate FIRST.

---

## §8c Per-setup ICT-canon classification details

### ICT-canonical position on each setup type

**Strong RETIRE candidate**:
- `MA_CROSSOVER` — ICT EXPLICITLY rejects moving-average crossovers. Per [chartinglens.com ICT guide](https://chartinglens.com/blog/ict-trading-strategy-guide): *"Unlike traditional technical analysis that relies on lagging indicators like moving averages and RSI, the ICT method focuses on price action, time, and the structural mechanics of how markets move."* Per [eplanetbrokers.com ICT guide](https://eplanetbrokers.com/training/ict-trading-strategy-explained): *"ICT explicitly avoids moving average crossovers and other lagging indicators as primary trading tools."* — **No ICT primitive expressed. Retire, don't migrate.**

**Reclassify M7 → M8 (OTE_RETRACEMENT)**:
- `FLAG_PENNANT` — Per [innercircletrader.net bull-flag guide](https://innercircletrader.net/tutorials/bull-flag-pattern-trading-strategy/): *"Although the bull flag is a classic technical analysis pattern, it sits perfectly inside the ICT framework as a visualization of a break of structure followed by a valid pullback, with the pole being the displacement leg that produced the BOS."* The POLE is the MSS displacement, the FLAG is the OTE retracement zone — entry happens on the FLAG, not the POLE. **Belongs in M8 OTE_RETRACEMENT.**
- `BB_BREAKOUT_RETEST` — By definition this is a retracement-into-zone entry, not a continuation. The breakout is the displacement; the RETEST is the OTE. **Belongs in M8.**

**Reclassify M7 → M9 (LIQUIDITY_SWEEP_REVERSAL)** (debatable):
- `ORB` — Session-open range break. Per ICT canon the IPDA opening range is a LIQUIDITY ZONE — its break is a liquidity sweep, not a structure-continuation. **Reclassify to M9** unless the operator wants ORB to stay as a session-tagged MSS variant.

**KEEP in M7 (MSS_CONTINUATION)** — these ARE displacement-leg / structure-continuation setups:
- `BB_BREAKOUT` — band-break IS a displacement event when paired with §B.8.2 atom_displacement_present ≥ 1.5×ATR. Per ICT integration, the band break itself isn't the ICT primitive — but the displacement leg the breakout produces IS the MSS confirmation criterion.
- `GAP_AND_GO` — gap IS a displacement leg (weekend/news gap = same structural meaning as M5 displacement candle).
- `MOMENTUM_DUMP` — the canonical M5 displacement detector. Textbook MSS_CONT primary signal.
- `MOMENTUM_DUMP_COMPOSITE` — same primitive, atom-composed. Retire #5 when validation confirms equivalence.
- `BB_SQUEEZE` — consolidation→expansion = ICT IPDA accumulation→expansion phase = displacement. Fit OK.
- `GRINDING_SELL` — multi-bar slow-displacement variant of MSS_CONT.
- `NY_SESSION_BEARISH_BREAKOUT_SELL` — session-open displacement break, MSS_CONT with Killzone tag.

**Provisional in M7 (operator call: keep or retire)**:
- `INSIDE_BAR` — Could fit MSS_CONT (consolidation → expansion = displacement). BUT also a retail chart pattern. Per ICT integration thinking: the inside-bar pattern IS a visualization of consolidation, similar to flag. Could be reclassified to M8 OTE or retired. **Operator decision needed.**

### Revised M7 scope (7 setups, not 11)

| Bucket | Count | Setups |
|---|---|---|
| **M7 (MSS_CONT)** | 7 | BB_BREAKOUT, GAP_AND_GO, MOMENTUM_DUMP, MOMENTUM_DUMP_COMPOSITE, BB_SQUEEZE, GRINDING_SELL, NY_SESSION_BEARISH_BREAKOUT_SELL |
| **M7 (provisional)** | 1 | INSIDE_BAR (operator call) |
| **M8 (OTE_RETRACEMENT)** | 2 | BB_BREAKOUT_RETEST, FLAG_PENNANT |
| **M9 (LIQUIDITY_SWEEP_REVERSAL)** | 1 | ORB |
| **RETIRE (don't migrate)** | 1 | MA_CROSSOVER |

### Recommendation: update `FORGE_SETUP_ICT_MAP.md §B.4` to reflect this audit

The current §B.4 fold-spec was written before the §B.8.2 atom catalog matured. Each setup's category should be determined by which §B.8.2 atom set it actually expresses, NOT by a fixed pre-classified list. This audit + WebSearch citations are the basis for the revision.

### Updated migration order (M7 → 7 setups, not 11)

| Sub-ship | Folds | Total setups |
|---|---|---|
| M7a | BB_BREAKOUT (+ env knob OQ5) | 1 |
| M7b | MOMENTUM_DUMP + MOMENTUM_DUMP_COMPOSITE (parallel — composite supersedes legacy when validated) | 2 |
| M7c | GAP_AND_GO + BB_SQUEEZE | 2 |
| M7d | GRINDING_SELL + NY_SESSION_BEARISH_BREAKOUT_SELL (+ env knob OQ6) | 2 |
| (Provisional) | INSIDE_BAR — fold or retire (operator call) | 0-1 |
| | **M7 total: 7-8 setups (vs the original spec's 11)** | |

`MA_CROSSOVER` retire → separate v2.7.137a tech-debt commit; remove the trigger site + the env knob.

`BB_BREAKOUT_RETEST` + `FLAG_PENNANT` → M8 OTE_RETRACEMENT fold (separate ship).

`ORB` → M9 LIQUIDITY_SWEEP_REVERSAL fold (separate ship).

---

## §9 What M7 does NOT do (deferred)

- **No KZ/SK behavioral changes** (deferred to R13 — operator's #1 stated goal — should be the v2.7.138 ship)
- **No QuestDB metrics** (R15 — bigger design)
- **No legacy code rip-out** (R9 — separate tech-debt ship; legacy triggers stay, just their setup_type STRING gets renamed)
- **No Phase 3 advanced OB features** (R6/R7 — hidden OBs, mitigation blocks, PD-array)

---

## §10 Open questions for operator (parking lot)

| ID | Question | Default if no answer |
|---|---|---|
| OQ1 | Bundled v2.7.137 (one commit) vs incremental M7a-f (6 commits)? | Bundled |
| OQ2 | Should BB_BREAKOUT_RETEST keep its own `setup_subtype` or merge with `bb_breakout`? | Own subtype (`bb_breakout_retest`) — preserves ablation fidelity |
| OQ3 | When MOMENTUM_DUMP fires with composite_enabled=1, do BOTH the legacy and composite branches fold separately? | Yes — two distinct subtypes (`momentum_dump` + `momentum_dump_composite`) preserve original-trigger identity |
| OQ4 | Should the M7 ship also pass real `composite_score` to `Forge_BuildScalpComment` so comment carries H/M/L instead of `?`? (Per §5 above) | YES — this is the "always-test" + "winning conviction tag" rule; fix as part of M7 |
| OQ5 | (Per Explore audit) Add `FORGE_SETUP_BB_BREAKOUT_ENABLED` env knob since `g_sc.breakout_enabled` is currently hardcoded `true`? | YES — `feedback_no_dead_env_vars` requires every gate to have a knob; M7 adds it for parity |
| OQ6 | (Per Explore audit) Add `FORGE_SETUP_NY_SESSION_BEARISH_BREAKOUT_SELL_ENABLED` since this setup has no enable flag? | YES — same rationale; default ON to preserve current behavior |

---

## §11 Skill / memory mandate cross-reference

- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_full_ict_alignment_mandate.md` — M7 is the canonical execution of this rule
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_quant_expert_identity.md` — test plan in §7 satisfies "tests ship in same PR"
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_refinement_workflow.md` — this doc IS the research surface
- `.claude/skills/forge-monitor/SKILL.md §I.14` — consolidated mandate
- `docs/FORGE_SETUP_ICT_MAP.md §B.4` — the §B.4 fold spec

---

## §12 Status + next steps

- [ ] Explore agent populates §2 mapping table (in-flight)
- [ ] Operator confirms migration order (OQ1 — bundled vs incremental)
- [ ] R14 tester validation (5-min) — verify v2.7.136 baseline before M7 multiplies code
- [ ] Code ship: schema change + 11 fire-site patches + `JournalRecordSignal` signature update
- [ ] Test harness: `tests/test_m7_fold.py`
- [ ] Glossary §11 + ICT map §9 changelog entries
- [ ] Commit + push branch
