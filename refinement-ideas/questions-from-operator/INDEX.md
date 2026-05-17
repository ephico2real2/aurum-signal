# Questions from Operator — INDEX

Bank of questions the operator has raised. Helps surface recurring themes + ensure nothing gets dropped.

## Active questions

| ID | Question (verbatim or paraphrased) | Raised | Status | Resolution / Where addressed |
|---|---|---|---|---|
| Q1 | "can you verify that you are still using the technical guides and docs about ICT for this design so far" | 2026-05-17 | RESOLVED | Audit in session — found 1 drift (atom_breaker_present → atom_ob_broken) + 1 missing wire (atom_ob_confluence for Cat 2). Shipped v2.7.136 fix |
| Q2 | "are we replacing all pre-ICT conventions to align with ICT specs going forward" | 2026-05-17 | RESOLVED — POLICY | Yes. Memorialized in `feedback_full_ict_alignment_mandate` + `SKILL.md §I.14`. Pre-ICT names migrate on M7-M9 folds |
| Q3 | "how do we identify loss patterns systematically" | 2026-05-17 | RESOLVED — POLICY | 6-axis slice mandate in `feedback_audit_loss_patterns`. Tools: `scripts/fbeta2_histogram.py` (shipped); `loss_pattern_slicer.py` to build per mandate |
| Q4 | "can we create metrics queryable in QuestDB on atoms/composites/geometry" | 2026-05-17 | OPEN — DESIGN PENDING | High-level mandate in §I.14. Detailed metrics schema design needed in `improvement-recommendations/` + `research-citations/questdb_metrics_design.md` |
| Q5 | "should we win even in killzones and silver bullet" | 2026-05-17 | OPEN — STRATEGIC | Goal stated. Implementation path: KZ_MKT comment prefix + composite-score histogram per-KZ slice (extend fbeta2_histogram). Track in improvement-recommendations |
| Q6 | "do you have made a recommendation about replacing the following with ICT" | 2026-05-17 | RESOLVED — TAUGHT META-LESSON | NO, I did not — accepted Explore findings + §B.4 spec without per-setup canon check. Operator's teach moment → codified `feedback_consensus_gate_for_findings` + skill §I.15. Applied consensus gate retroactively to M7 design (`§8b`): 4/11 setups need reclassify/retire. R17-R20 added to improvement-recommendations |

## Update protocol

- Append new questions as raised. Don't lose them in chat scrollback.
- Status: OPEN / RESEARCHING / RESOLVED / RESOLVED — POLICY / OPEN — DESIGN PENDING / OPEN — STRATEGIC
- "RESOLVED" rows stay (don't delete) — provenance + future-me reference
- Cross-reference resolutions: specific commit / doc section / memory file
