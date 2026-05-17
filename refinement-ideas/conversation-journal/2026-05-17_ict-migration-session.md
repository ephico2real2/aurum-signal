# 2026-05-17 — ICT Migration Sprint Session

**Status**: LIVE
**Branch**: `v2.7.129-mode-d-cleanup`
**Versions shipped**: 2.7.129 → 2.7.130 → 2.7.131 → 2.7.132 → 2.7.133 → 2.7.134 → 2.7.135 → 2.7.136

---

## Ships in this session (chronological)

### v2.7.129 — Mode D PEMCG/CVCSM/BB_EXHAUSTION retirement (commit `4db2d19`)
- 3 master flags flipped to false (FORGE.mq5:5401/5459/5465)
- Validation: post-Mode-D signal count dropped 67% (40,787 → 13,307) — PEMCG churn was inflating counts
- Lessons doc preserved at `docs/FORGE_PEMCG_CVCSM_LESSONS_LEARNED.md`

### v2.7.130 — F-β.1 composite Mode-A logging (commit `05f012c`)
- 3 ICT atoms (PULLBACK_IN_OTE / PREMIUM_DISCOUNT_ALIGNED / FVG_ON_REVERSAL_LEG) + 3 composite scores enabled
- SIGNALS columns `mss_cont_score_*`, `ote_retrace_score_*`, `liq_sweep_rev_score_*` now populate with real 0-10 values
- BREAKER_RETEST deferred (Phase 3 dependency)

### Skill §I.5a + v2.7.131 magic-collision seed fix (commits `8679ac3`, `613a09c`)
- Skill rule: Google MQL5/MT5 docs before asserting platform facts
- `SeedScalperGroupCounter()` recovers counter from broker on OnInit — closes EA-reload collision risk

### v2.7.132 — Zone-leading ICT broker-comment scheme (commit `39237a8`)
- All 11 comment builders migrated to `<ZONE>_<ORDER_TYPE>|<CAT>_<DIR>|G<ID>|<TP_OR_LEG>|<KZ_DETAIL>|<CONV>[|<SK_DETAIL>]`
- 3 zones (KZ/SK/OFF) × 8 order types = 24 prefixes
- Helper module `ea/include/Forge/IctComment.mqh` + canonical doc `docs/FORGE_ICT_COMMENT_CODES.md`
- OnInit self-test prints 8 canonical sample shapes for verification
- Doc wiring (commit `b3c3064`) — explicit source-producer ↔ helper-consumer chains

### F-β.2 histogram analyzer (commit `118989f`)
- `scripts/fbeta2_histogram.py` — composite-score vs P&L by bucket / per-category / per-threshold
- First-pass on run_id=3 (18 TAKEN signals): score ≥ 3 flips total P&L from −$627 to +$655. H-bucket = 100% WR small sample. Threshold = 5 (proposed in §B.8.2) is too aggressive — data argues for ≥ 3.

### v2.7.133 — Phase 3 OB module body (commit `092031b`)
- `IctOrderBlock.mqh` scaffold (41 lines) → full body (272 lines)
- OB ring + displacement+previous-opposite+FVG-confirmation detection
- Broken-state tracking + retest detection + FVG-confluence atom
- `ComputeCategoryScore(4)` wired (was stub returning 0)
- 4th ICT category alive

### v2.7.134 — Phase 3b BREAKER_RETEST schema parity (commit `2e08733`)
- 7 new SIGNALS columns (5 atom + 2 score) per F-β.1 schema-parity pattern
- 5-layer wire: EA CREATE + ALTER + INSERT + scribe.py CREATE + ALTER + SELECT + INSERT + placeholder count 159 → 166

### v2.7.135 — Phase 3 OB env knobs (commit `fc54141`)
- 4 hardcoded params promoted to FORGE_ICT_OB_* env vars (displacement / lookback / retest / FVG confluence)
- Full 5-layer wire

### Audit + v2.7.136 — ICT canonical naming alignment (commit `ac58237`)
- Operator-requested audit: verify implementation matches `§B.8.2` spec
- Drift found: `atom_breaker_present` should be `atom_ob_broken` per §B.8.2 verbatim
- Rename shipped + `atom_ob_confluence_buy/_sell` added for Cat 2 OTE_RETRACE (was post-Phase 3 stub)
- OB ring rebuild reordered to fire BEFORE composite scores so Cat 2 reads fresh atoms
- All 4 ICT categories now equivalent in implementation depth
- Glossary §3 atom catalog updated with 6 missing entries

### Foundational mandate established (current — this commit)
- 4 new memory rules: full ICT alignment, quant-expert identity, audit loss patterns, refinement workflow
- Skill §I.14 added — consolidates the 4 memories into a single canonical surface
- `refinement-ideas/` folder structure created — research surface for background dissection

---

## Key decisions + rationale

| Decision | Rationale | Pivoted? |
|---|---|---|
| Apply zone-leading comment to ALL trades (not just future ICT) | Operator decision "apply to new trades, forget old trades" — single ship, no incremental rollout, cleaner downstream parsers | No |
| Defer scribe parser update for new comment scheme | Wait until first ICT-canonical setup actually fires (M7) — no consumer yet | No |
| Use `SK` (Silver Knife) not `SB` (Silver Bullet) in comment | Operator-preferred internal vocabulary; ICT canon name stays in SIGNALS columns | No |
| Path A (fix drift first, then M7) over Path B (start M7, fix drift in M9 closing) | Smaller cost NOW; M7 will reference these columns and downstream tools will get used to current names | No |
| Phase 3 minimal-viable Cat 4 OB body (deferred PD-array, hidden OB, mitigation block) | Unblock the 4th category composite scoring first; advanced features land in Phase 3c+ | No |
| Composite enable flags default OFF | Schema-parity byte-stable for users who don't opt in | No |

---

## Pending / deferred

- **F-β.2 Mode B promotion** — data-collection gated; histogram needs more sample
- **M7-M9 folds** — legacy → ICT-canonical setup_type renames; next major phase
- **Phase 2b PEMCG code rip-out** — tech debt cleanup; behaviorally retired since v2.7.129
- **Phase 5 IctIntradayModel** — scaffold-only; not blocking
- **Scribe parser update for new comment scheme** — wait until first ICT setup fires
- **QuestDB metrics design** — discussed in foundational mandate; refinement-ideas surface to be populated
- **DST validation** — needs longer tester run that crosses Mar 8 US DST + Mar 29 EU DST

---

## Operator's foundational mandate (2026-05-17, current commit)

See:
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_full_ict_alignment_mandate.md`
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_quant_expert_identity.md`
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_audit_loss_patterns.md`
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_refinement_workflow.md`
- `.claude/skills/forge-monitor/SKILL.md §I.14`

Highlights:
- Multi-disciplinary expert identity (MQL5/MT5, FOREX, ICT/SMC, QuestDB, ETL, ML, etc.)
- Research over emotions — Google + cite + document
- No bad code even during throttling
- Audit loss patterns across 6 axes (day-of-week, time-of-day, killzone, market regime, news, technical)
- `refinement-ideas/` repo folder for background research
- codex:rescue collaboration encouraged
- QuestDB-queryable metrics path on every new atom/composite
- Strategies must win in killzones + Silver Bullet windows

---

## Next session anchor points

- M7 fold spec at `docs/FORGE_SETUP_ICT_MAP.md §B.4`:
  - 11 legacy setups (BB_BREAKOUT, MA_CROSSOVER, ORB, GAP_AND_GO, MOMENTUM_DUMP, MOMENTUM_DUMP_COMPOSITE, BB_SQUEEZE, FLAG_PENNANT, INSIDE_BAR, GRINDING_SELL, NY_SESSION_BEARISH_BREAKOUT_SELL) → MSS_CONTINUATION_BUY/SELL
  - Subtype column needed to preserve original-trigger identity for ablation studies
- All 4 ICT category composites now alive (atoms+scoring+schema+env knobs)
- Foundational mandate operational
- `refinement-ideas/` surface ready for population
