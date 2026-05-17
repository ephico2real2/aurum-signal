# `refinement-ideas/` — research surface for FORGE design work

**Operator mandate 2026-05-17** (foundational, memorialized in `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_refinement_workflow.md`).

This folder is the **PRE-canonical** scratch space. Speculative ideas, partial analyses, research-in-progress, codex:rescue dialogues, operator-question parking, loss-pattern dissection — all land HERE first. When an idea matures, it graduates into the main repo docs (`docs/`, code modules, glossary) and the surface here links back as provenance.

**Why this exists**: speculative content polluting main docs creates drift between operator's mental model and the codebase. The `// TODO: maybe try X` antipattern hurts the docs and never gets done. This folder lets me build research surface deliberately — and force-document the journey.

---

## Sub-folder map

| Folder | Purpose | When to write | When to archive |
|---|---|---|---|
| `conversation-journal/` | Per-session log of operator ↔ Claude design dialogue. Captures decisions even when we pivot. | After every substantial operator session | Never delete — historical context |
| `questions-from-operator/` | Bank of questions the operator has raised. Pending / researching / answered with link to where addressed. | On every new question | Mark resolved; don't delete |
| `improvement-recommendations/` | Running list of improvements I've identified but not yet shipped. Cross-references to source. | On each finding (during audit, code review, research) | Mark shipped → link commit |
| `loss-patterns/` | Per-pattern docs with query + output + hypothesis + recommended fix + test plan | After every audit / backtest / post-mortem that surfaces losses | Mark addressed → link commit |
| `research-citations/` | Summaries of well-cited external sources (MQL5 docs, ICT canon, HFT papers, QuestDB best practices) | Per-source as consumed | Never delete — citation trail |
| `codex-dialogues/` | Summaries of codex:rescue background consultations | Per dialogue | Never delete — design provenance |

---

## Rules of engagement

1. **Speculative ideas go HERE first.** Not in `docs/`. Not in code comments. Not in commit messages.
2. **Document with facts + data.** Every claim has supporting evidence — a query result, a citation, a benchmark, a regression check.
3. **Cross-reference everything.** Every doc here links to the canonical source it serves AND to any docs that supersede it.
4. **Graduate mature ideas.** When research solidifies, distill the SUMMARY into the main docs and leave the surface here as provenance.
5. **Never delete; archive.** Move stale docs into a `_archived/` sub-folder within each category if they've been superseded.

---

## Active surfaces (as of 2026-05-17)

| Surface | INDEX | First entry |
|---|---|---|
| Conversation journal | [conversation-journal/INDEX.md](conversation-journal/INDEX.md) | [2026-05-17 ICT migration session](conversation-journal/2026-05-17_ict-migration-session.md) |
| Operator questions | [questions-from-operator/INDEX.md](questions-from-operator/INDEX.md) | (populated as questions arrive) |
| Improvement recommendations | [improvement-recommendations/INDEX.md](improvement-recommendations/INDEX.md) | (initial seeded from skill audit findings) |
| Loss patterns | [loss-patterns/README.md](loss-patterns/README.md) | (populated per `feedback_audit_loss_patterns`) |
| Research citations | [research-citations/INDEX.md](research-citations/INDEX.md) | (initial seeded from existing v2.7.133 ICT-canon citations) |
| codex:rescue dialogues | [codex-dialogues/INDEX.md](codex-dialogues/INDEX.md) | (populated as dialogues happen) |

---

## Cross-references

- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_refinement_workflow.md` — the foundational mandate
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_full_ict_alignment_mandate.md` — ICT alignment goal
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_quant_expert_identity.md` — quality bar
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_audit_loss_patterns.md` — loss-pattern discipline
- `.claude/skills/forge-monitor/SKILL.md §I.14` — consolidated mandate in the skill surface
