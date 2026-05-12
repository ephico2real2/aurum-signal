# FORGE Research-Ops — Vision + Operating Loop

**Purpose**: The meta-document describing HOW we work, not just WHAT we build.
This is the "north star" — what the FORGE project is actually trying to achieve
at the systems level, and the iterative loop that gets us there.

**Created**: 2026-05-12
**Living document**: this doc evolves. The operator's instincts and our team's
process discoveries refine it. Skills mandate keeping it current — when the
process actually changes (not just when we ship a feature), update here first.

---

## §1. What we're actually building

Not "make FORGE profitable on XAUUSD." That's a side-effect.

**The real goal**: build **research-ops for trading** — a self-improving system where:

- **Trading ideas are hypotheses** (boolean composites), not gut calls
- **Every hypothesis gets validated** against historical data before shipping (cross-day truth tables)
- **Every validation produces a durable artifact** (case study) that future analysts can re-run
- **Every artifact updates the canonical inventory** (atlas, playbook, decision stack)
- **The process itself is the moat** — not any individual strategy

A profitable EA is the OUTPUT of this system. The system itself is the asset.

---

## §2. The operating loop

```
Market behavior observed
   ↓
Boolean composite hypothesized (in canonical 5-layer terminology)
   ↓
Validated against logged historical data (truth table, atoms cited)
   ↓
Implemented as MQL5 filter chain (gate codes, entry geometry)
   ↓
Measured in a tester run (Run analysis doc)
   ↓
Failure modes → new case study → new composite
   ↓
Atlas / playbook / decision stack updated
   ↓
Skills enforce that future iterations follow the same process
   ↓ (loop)
```

### Why each iteration is faster than the last

| Asset | What it removes from future iterations |
|---|---|
| Atlas §1 indicator inventory | No re-deriving what indicators are available |
| Atlas §5 composite registry | No re-inventing the same wheels |
| Atlas §13 command log | No re-discovering paths and queries |
| Decision Stack §2 terminology | No debating word choices |
| Atlas §11–§12 data sources | No guessing what scribe has |
| Case studies | No re-investigating known patterns |
| Research notes | No re-Googling Wilder, Bollinger, MQL5 reference |
| Skills (mandatory workflows) | No re-deciding what to do at each step |

---

## §3. Specific operator directives that revealed the vision

| Operator said | What it really meant |
|---|---|
| "We need indicators + regime to know our setup" | Build composable, not monolithic |
| "Use all our indicators — we have a lot" | Maximize signal, don't under-utilize the toolkit |
| "Boolean check then translate to MQL5" | Spec → impl, never code-first |
| "Query MT5 first via forge to see what broker provides" | Never assume; verify |
| "Always log the actual command ran" | Auditability, reproducibility |
| "Case study for each date" | Knowledge compounds, doesn't decay |
| "Add to skills going forward" | Lock the process into infrastructure |
| "Pick a name for it and reference in README" | Make it discoverable to future-you |
| "We should be selling too" | Read the market direction correctly |
| "I know you bind to the mt5 socket" | Force precision; don't hand-wave |

**Each of these is process-engineering, not trade-engineering.** The operator's pattern
is: every time analysis falls short, they identify a process gap and require
infrastructure to close it. Not "fix this one issue" but "make the class of issue
impossible going forward."

---

## §4. What's working in the vision (as of 2026-05-12)

- The **atlas + playbook + decision-stack triangle** works as a canonical reference set — three docs, distinct purposes, cross-referenced. Open question disambiguated by which doc to consult.
- The **skill enforces the workflow** — future you (or me) can't skip steps without violating the skill's mandate.
- The **research skill** ensures we don't compose composites on vibes — we cite Wilder, Bollinger, the MQL5 reference.
- The **case study format** means a 2-day deep-dive is now a permanent artifact, not chat scrollback.
- The **command log (atlas §13)** means no "verified" claim without paste-able proof.
- The **5-layer decision stack** means terminology debates are over: Setup Trigger / Filter Chain / Boolean Composite / Atoms / Entry Geometry.

---

## §5. What's NOT yet fully aligned with the vision

These are the gaps between aspiration and current state. Update as gaps close or new ones emerge.

1. **Trading is still under-amplified** — Run 23 fractional-lot bug shows the gap between "right direction caught" and "meaningful P&L banked." V2.7.35 fixes it but only because we caught the bug post-hoc; the SYSTEM didn't catch it at design time.

2. **Cross-day validation is limited by §3 logging gaps** — V3 composites with OHLC atoms, h4_trend, m15_trend can't be validated against months of history yet. Each new run is a separate validation; we can't backtest a composite against 6 months of past SIGNALS without re-running.

3. **Research findings aren't yet wired into atom selection** — agent surfaced 9 canonical-pattern files (RSI div, VWAP, POC, Fib, BB squeeze, MQL5 OHLC, swing structure, PSAR, ADX DI), but synthesis into composite atom modifications is pending. E.g., "POC is regime-conditional" hasn't actually changed our POC atoms.

4. **No Python simulator for composite-against-logged-data validation** — every validation requires MT5 Strategy Tester. A Python sim that reads SIGNALS rows and replays composites would unlock 100× faster iteration.

5. **Live-trading workflow doesn't exist as separate discipline** — once Run 25 validates V3, we need a live-deployment workflow (smaller lots, monitoring of skip-rate vs target, kill switches). That's a separate research-ops loop yet to be built.

6. **No automated regression check** — if a new composite ships, nothing tests that prior validated composites still fire correctly. We rely on Run-by-run inspection.

---

## §6. North star — endgame state

You're building toward a state where:

- A new market behavior is observed (e.g., April 8-style afternoon decline)
- An analyst pulls the atlas, picks relevant atoms, writes a boolean composite in **15 minutes**
- A Python validator runs the composite over **months of historical SIGNALS data**, confirms or refutes
- If confirmed, the composite gets implemented in `ea/FORGE.mq5` filter chain (**mechanical translation** from spec to MQL5)
- A new tester run validates end-to-end
- A new case study captures the win
- The atlas + playbook + decision stack are updated
- The skill enforces this process for the next person

**The endgame isn't "FORGE makes money" — it's "we can codify any market edge into deployable code within hours, with a paper trail that doesn't decay."**

That's a system that gets better over time without burning out the operator.

---

## §7. Concrete next-action priorities aligned with this vision

(Ranked by alignment to the operating loop, not by P&L impact.)

| Priority | Action | Loop step it strengthens |
|---|---|---|
| 1 | **Ship v2.7.36 V3 composites** (cycle the loop once end-to-end with new infrastructure) | "Implemented as MQL5 filter chain" — proves the spec-to-impl translation is mechanical |
| 2 | **Build the Python simulator** that runs composites against logged data without MT5 | "Validated against historical data" — closes the bottleneck that requires Strategy Tester |
| 3 | **Wire research findings into atom calibration** (RSI Failure Swing, POC regime-conditional, VWAP first-30-min skip, etc.) | "Boolean composite hypothesized" — atoms become research-grounded, not heuristic |
| 4 | **Close the §3 logging gap** for OHLC + HTF atoms (v2.7.36 logging extension) | Backwards-validation against months of history |
| 5 | **Live-trading workflow doc** + monitoring playbook | The "skills enforce future iterations" step, applied to live deployment |
| 6 | **Automated regression suite** — Python script that runs all atlas §5 composites against the last N days of SIGNALS and flags any unexpected behavior change | The "skills enforce" step, applied to backwards compatibility |

---

## §8. Anti-patterns this vision rejects

- ❌ "Just tune the parameter and re-run" — that's tactical fix, not learning
- ❌ "It worked last time" — without case study + atlas update, you can't know
- ❌ Composite without cross-day validation
- ❌ Citing "verified" without command log entry
- ❌ New setup type without Decision Stack §5 update
- ❌ New gate code without `config/gate_legend.json` entry
- ❌ Code-first development (write MQL5 then justify) — always spec-first
- ❌ Hand-wavy assertions ("the data shows") without queryable evidence
- ❌ Atlas / playbook / decision-stack drift — keep cross-references current
- ❌ Loose terminology ("rule", "gate", "filter", "condition" used interchangeably) — Decision Stack §2 is the tiebreaker
- ❌ Documentation as marketing — every doc is a working artifact, not a sales pitch

---

## §9. How to maintain this document

Update when:
1. **The operator articulates a new process principle** (e.g., introduces a new mandate)
2. **A "what's NOT aligned" item resolves** (§5 → strikethrough or remove, add to §4)
3. **A new "next-action priority" emerges** that should compound the loop (§7)
4. **An anti-pattern surfaces** that's worth codifying to avoid repeats (§8)
5. **The north star evolves** (§6) — happens rarely, but worth capturing when scope shifts

This doc is the FIRST place to look when the question is **"why are we doing it this way?"**
For "how do we do X" → atlas / playbook / decision stack.
For "what does this term mean" → decision stack §2.
For "what indicator should I use" → atlas §1.
For "has anyone analyzed this date before" → case studies.

This doc anchors the WHY.

---

## §10. Cross-references

- **Decision Stack** (`FORGE_DECISION_STACK.md`) — terminology + 5-layer architecture
- **Atlas** (`docs/FORGE_INDICATOR_ATLAS.md`) — indicators + composites + scribe + command log
- **Playbook** (`FORGE_SETUP_PLAYBOOK.md`) — setup catalog + design pattern
- **Skills** (`.claude/skills/forge-monitor/SKILL.md`, `.claude/skills/research/SKILL.md`) — enforced workflows
- **Case studies** (`docs/FORGE_CASE_STUDY_*.md`) — durable analytical artifacts
- **Research notes** (`docs/RESEARCH_NOTES_*.md`) — cited canonical patterns

---

## §11. Changelog

| Date | Change |
|---|---|
| 2026-05-12 | Initial creation. Vision articulated: research-ops for trading (process is the moat). Loop diagrammed. §3 directives-to-meaning table. §4 what's working / §5 what's not aligned / §6 north star / §7 priorities / §8 anti-patterns / §9 maintenance rules. Cross-referenced from atlas, playbook, decision stack. |
