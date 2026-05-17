# Improvement Recommendations — INDEX

Running list of improvements I've identified but not yet shipped. Cross-references to source (audit, loss-pattern, codex:rescue dialogue, web research, code review).

## Open recommendations

| ID | Recommendation | Source | Why | Effort | Status |
|---|---|---|---|---|---|
| R1 | Build `scripts/loss_pattern_slicer.py` — 6-axis slice generator per `feedback_audit_loss_patterns` | Foundational mandate 2026-05-17 | Loss-pattern identification must be tooled, not ad-hoc | M (~200 LOC, mirrors fbeta2_histogram pattern) | OPEN |
| R2 | Design QuestDB metrics schema for atoms/composites/geometry | Foundational mandate 2026-05-17 Q4 | Future-proof observability path; replaces scribe-only SQLite analytics | L (schema design + ingestion + dashboards) | OPEN — DESIGN |
| R3 | Extend `fbeta2_histogram.py` to slice by killzone + Silver Knife | Foundational mandate 2026-05-17 Q5 ("win in KZ/SK") | The killzone slice is the most leveraged composite-score discriminator | S (add filter args) | OPEN |
| R4 | Wire `atom_ob_confluence` into MSS_CONT + LIQ_SWEEP_REV scoring | v2.7.136 ship reflection — only Cat 2 + Cat 4 use the OB ring; Cat 1 & 3 could too | Cat 1 MSS_CONT has implicit OB context via the displacement leg; explicit atom would tighten scoring | S (add 2 conditional adds in IctScoring.mqh) | OPEN — RESEARCH |
| R5 | Add `composite_score` and `conviction_letter` columns DIRECTLY to TRADES (not just SIGNALS) | v2.7.132 ship reflection — comment carries conviction but TRADES.profit join requires SIGNALS round-trip | Eliminates a JOIN in every loss-pattern query | S (scribe schema + TP1 fill handler) | OPEN |
| R6 | Phase 3c — implement Hidden Order Blocks + Mitigation Blocks (deferred from v2.7.133) | Phase 3 minimal-viable scope | OB detection currently misses the no-FVG variants + the held-OB continuation case | M (300 lines IctOrderBlock.mqh extension) | DEFERRED |
| R7 | Phase 3d — PD-array (Premium/Discount) confluence scoring | Phase 3 minimal-viable scope | ICT canon includes PD-arrays; not currently used | M (new helpers in IctOrderBlock.mqh + new atom) | DEFERRED |
| R8 | Phase 5 IctIntradayModel.mqh body — CRT / Venom / Bread & Butter / S&D / RDRB | Scaffold present, body deferred | High-conviction intraday ICT models | L (per model: detection + atom + composite) | DEFERRED |
| R9 | Phase 2b — physically delete the 355 PEMCG/CVCSM/BB_EXHAUSTION code refs (behaviorally retired since v2.7.129) | Tech debt | Dead code attracts maintenance burden + confuses readers | M (mechanical deletion + test re-run) | DEFERRED |
| R10 | Scribe parser update for new zone-leading comment scheme | v2.7.132 deferral | Currently scribe still parses legacy SCALP_*; M7-M9 folds will produce new shape | M (parser + dual-format handling) | OPEN — WAIT-FOR-M7 |

## Update protocol

- Append new recommendations as identified. Don't lose them in chat scrollback.
- Effort: S (< 1h) / M (1-4h) / L (> 4h)
- Status: OPEN / OPEN — RESEARCH / OPEN — DESIGN / OPEN — WAIT-FOR-PREREQ / IN PROGRESS / SHIPPED / DEFERRED / REJECTED
- SHIPPED rows: link the commit. Don't delete.
- REJECTED rows: document WHY in a short paragraph below the table.
