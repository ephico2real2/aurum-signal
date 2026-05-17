---
name: handoff
description: Session-handoff workflow. Two modes — (1) Save mode triggered by "handoff" / "/handoff": create a dated session-state summary in refinement-ideas/, save a memory pointer, commit. (2) Resume mode triggered by "I am home" / "am home" / "home" / "/resume": read the latest handoff doc, surface its state + next-action cookbook, prepare to resume from where the previous session paused.
---

# /handoff — session-handoff workflow

This skill bridges sessions when the operator is going offline and needs the next Claude session to land cleanly. Two modes.

---

## Mode 1 — SAVE handoff (triggered by "handoff" / "/handoff")

Operator is leaving. Capture everything needed for a fresh session to pick up.

### Triggers

- `/handoff`
- `handoff` (anywhere in the message)
- `create handoff`
- `i'm leaving — handoff` / `going offline — handoff` etc.

### What to write

**Filename**: `refinement-ideas/YYYY-MM-DD_session_handoff_<topic>.md`
- `YYYY-MM-DD` = today's date (UTC; use `date -u +%Y-%m-%d` if uncertain)
- `<topic>` = short slug describing where we paused (e.g. `post_v2_7_139`, `mid_m8_fold`, `during_r14_validation`)
- If a handoff file already exists for today on the same topic, append a `-2` / `-3` suffix rather than overwriting

**Required sections** (every handoff doc has these — use the most recent handoff in `refinement-ideas/` as the template; `refinement-ideas/2026-05-17_session_handoff_post_v2_7_139.md` is the canonical example):

```markdown
# Session handoff — YYYY-MM-DD (<one-line topic>)

**Purpose**: drop-in context for the next Claude session.
**Where we stopped**: <2-3 sentence summary of last action + reason for pause>

## §1 Repo state at handoff
- Branch, last commit SHA + message, version, EA size, working tree status,
  test suite state. Use `git log --oneline -5` + `wc -l ea/FORGE.mq5` +
  `make forge-compile` output to fill in.

## §2 Operator directives from this session
- Any new mandates / rules / corrections operator gave. Quote verbatim where possible.

## §3 What's DONE (committed, validated, on disk)
- Per-commit summary of code shipped this session.

## §4 What's PENDING (deliberately deferred)
- Next ship + scope. R-numbers from INDEX.md. Sequence + dependencies.

## §5 Critical context the next session MUST know
- Architectural patterns introduced. Anti-patterns to avoid. Gotchas hit this
  session.

## §6 Memory pointers
- Which memory files (under ~/.claude/projects/-Users-olasumbo-signal-system/memory/)
  the next session should read.

## §7 Validation commands to run FIRST in next session
- 3-5 bash commands that confirm clean state before any new work.

## §8 Implementation cookbook for the next ship
- Concrete step-by-step recipe for what's next. File paths + line numbers
  + Python script templates if applicable.

## §9 Outstanding R-list with priority
- Status table from refinement-ideas/improvement-recommendations/INDEX.md
  with priority + sequencing for each open R.

## §10 Where to find things
- File-index table pointing to canonical docs, design docs, tests, EA modules.

## §11 Sanity check before starting any work
- 5 must-pass commands. Hard stop if any fails.
```

### Steps to execute (Save mode)

1. **Confirm clean state**:
   ```bash
   git status -s
   git log --oneline -5
   ```
   If uncommitted code changes exist, ASK the operator before proceeding (they may want to commit first or include changes in the handoff context).

2. **Pull session state**:
   ```bash
   wc -l ea/FORGE.mq5
   cat VERSION
   .venv/bin/python -m pytest tests/api/test_m7_fold.py tests/api/test_forge_27x_gates.py -q 2>&1 | tail -3
   make forge-compile 2>&1 | grep -iE "error|warning|Stamped" | head -3
   ```

3. **Write the handoff doc** at `refinement-ideas/YYYY-MM-DD_session_handoff_<topic>.md` using the template above. Be SPECIFIC — include file paths, line numbers, commit SHAs, Python script templates if relevant.

4. **Update memory** at `~/.claude/projects/-Users-olasumbo-signal-system/memory/project_m7_pre_stabilization_batch.md` (or create `project_<active_work>.md` if the active work has moved on):
   - Top of file: add a "👉 NEXT SESSION: read `refinement-ideas/<filename>` FIRST" pointer
   - Update facts to reflect what was committed this session
   - Add an entry to MEMORY.md if a new memory file was created

5. **Commit the handoff doc**:
   ```bash
   git add refinement-ideas/<filename>.md
   # If memory was updated AND it's the operator's local memory (under ~/.claude/),
   # those changes are NOT committed (they live outside the repo). Only the
   # repo-tracked refinement-ideas/ doc + any updated project files get committed.
   git commit -m "$(cat <<'EOF'
   docs(handoff): session handoff doc — <one-line topic>

   <one-paragraph summary>
   EOF
   )"
   ```
   **NO `Co-Authored-By: Claude` trailer.**

6. **Report back to operator**:
   - Confirm filename created
   - Confirm commit SHA
   - Summarize what was captured in 3-5 bullets
   - Wish them well

### Anti-patterns (Save mode)

- ❌ Vague topic slug (`handoff.md` without date or context — gets lost in the directory)
- ❌ Missing file paths / line numbers in §8 cookbook — next session has to re-research
- ❌ Skipping §11 sanity checks — next session may build on broken baseline
- ❌ Committing operator's untracked backups (`.env.backup-*`, `athena_phase2/`, `backups/`, `python/bridge.py.backup-*`) — these are operator-managed and should stay untracked per the absolute fail-safe in CLAUDE.md
- ❌ Co-authoring credit to Claude in the commit message — per global CLAUDE.md, operator is sole author
- ❌ Aspirational claims (`R32 is fixed`) when reality is (`R32 is logged for ISS-gate ship`). Document what's TRUE, not what's planned

---

## Mode 2 — RESUME from handoff (triggered by "I am home" / "am home" / "home" / "/resume")

Operator is back. Pick up the most recent handoff and orient.

### Triggers

- `i am home` / `am home` / `home` (any case)
- `back` / `i'm back`
- `/resume`
- `resume from handoff` / `pick up from handoff`

### Steps to execute (Resume mode)

1. **Find the latest handoff doc**:
   ```bash
   ls -t refinement-ideas/*session_handoff*.md 2>/dev/null | head -3
   ```
   Pick the most recent. If multiple from the same day, pick by mtime.

2. **Read it end-to-end**:
   Use Read tool on the handoff doc. Internalize all 11 sections.

3. **Read the memory pointer it references**:
   Typically `~/.claude/projects/-Users-olasumbo-signal-system/memory/project_m7_pre_stabilization_batch.md` (or whatever the handoff doc says in §6).

4. **Run the sanity-check commands** from §11 of the handoff doc:
   ```bash
   pwd && git branch --show-current
   git log --oneline -1
   cat VERSION
   grep "FORGE_VERSION = " ea/FORGE.mq5 | head -1
   make forge-compile 2>&1 | grep -iE "error|warning" | head -5
   .venv/bin/python -m pytest tests/api/test_m7_fold.py tests/api/test_forge_27x_gates.py -q 2>&1 | tail -3
   ```
   STOP if any sanity check fails. Diagnose before proceeding.

5. **Surface to operator**:
   - One-line "welcome back" preamble
   - State summary from handoff §1 (branch, last commit, version, test count)
   - The pending-work summary from handoff §4
   - The NEXT ACTION from handoff §8 cookbook step 1
   - Ask: "Ready to proceed with <next step>, or do you want to do something else first?"

6. **Wait for operator confirmation** before starting any code changes. Resume mode is ORIENTATION first, action second.

### Anti-patterns (Resume mode)

- ❌ Skipping the sanity checks — silently building on broken state
- ❌ Re-deriving state from `git log` / `wc -l` without reading the handoff doc (the handoff has CONTEXT that raw commands don't surface — operator directives, architectural patterns, decisions made)
- ❌ Starting code changes without the operator's go-ahead
- ❌ Ignoring older handoff docs entirely — sometimes the operator wants to resume from a SPECIFIC handoff, not just the latest. Ask if ambiguous

---

## Cross-references

- **Memory index**: `~/.claude/projects/-Users-olasumbo-signal-system/memory/MEMORY.md`
- **Project memory pattern**: `~/.claude/projects/-Users-olasumbo-signal-system/memory/project_m7_pre_stabilization_batch.md`
- **Canonical handoff example**: `refinement-ideas/2026-05-17_session_handoff_post_v2_7_139.md` (the doc that motivated this skill)
- **Skill mandates that handoff doc must honor**: `feedback_never_delete_repo.md` (don't commit operator backups), CLAUDE.md commit attribution rule (no Claude co-author trailer)
- **Refinement-ideas workflow**: `feedback_refinement_workflow.md` (every session's research / decisions / open questions land in `refinement-ideas/`)

---

## Skill ownership

This skill lives at `/Users/olasumbo/signal_system/.claude/skills/handoff/SKILL.md`. It's project-local — applies only inside this repo's working directory. Created 2026-05-17 by operator request after the 4-commit session that shipped v2.7.137-139.

The handoff workflow itself is canonical going forward — every long-or-paused session should end with a handoff doc, and every fresh session that picks up paused work should start with a Resume.
