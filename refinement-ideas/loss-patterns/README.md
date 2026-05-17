# Loss Patterns — catalog

Per `feedback_audit_loss_patterns` mandate (2026-05-17). After every audit / backtest / live post-mortem, slice losses across 6 axes; document each pattern here with query + output + hypothesis + recommended fix + test plan.

## The 6 axes

| Axis | What to extract | Example pattern from session prior to mandate |
|---|---|---|
| **Day of week** | Sun/Mon/Tue/Wed/Thu/Fri | (none yet — populated as identified) |
| **Time of day** (NY local) | Hour bucket | Run 3 v2.7.130: 21:00-NY MOMENTUM_DUMP SELL = −$1,014 (1 loss; small sample) |
| **Killzone session** | ASIA_KZ / LDN_OPEN / NY_OPEN / LDN_CL / NY_PM / OFF / Silver Knife window | LO_KZ MOMENTUM_DUMP BUY against H1-bear = 2 losses (G5002-3 in v2.7.130 run 3) |
| **Market regime** | TREND_BULL / TREND_BEAR / RANGE / VOLATILE | Bear-day BUY entries with low conviction (L bucket) — −$1,481 across 2 trades |
| **News context** | high-impact-window adjacency (±15min FOMC/NFP/CPI) | (none — backfill from news calendar overlay needed) |
| **Technical alignment** | HTF aligned vs counter, composite score bucket (H/M/L), wick quality, FVG distance | Counter-trend BUY in TREND_BEAR with L-conviction = systematic loser (per F-β.2 first read) |

## Catalog (populate as patterns identified)

| ID | Pattern | Doc | Status | Recommended fix | Shipped |
|---|---|---|---|---|---|
| LP1 | Bear-day MOMENTUM_DUMP BUY at score=2 (LOW conviction) | (TBD) | OPEN | F-β.2 Mode B at threshold ≥ 3 — blocks pre-emptively | — |
| LP2 | LO_KZ MOMENTUM_DUMP SELL at score=6 — caught despite high score | (TBD) | OPEN — INVESTIGATE | Composite score may not capture chop-flush regime; investigate `g_eval_m5_atr_ratio_5bar` correlation | — |
| LP3 | ASIA_KZ first SELL at 21:00-23:00 NY (G5048-style) | (TBD) | OPEN — needs more data | Defer SELL entries during Asian-overnight first-hour; add `bear_overnight_overshoot_block` | — |

## Doc template (for each new pattern entry)

```markdown
# LP<N> — <pattern title>

**Identified**: <date>
**Source**: <run_id / live post-mortem date / external observation>
**Status**: OPEN | INVESTIGATING | FIX-PROPOSED | SHIPPED | REJECTED

## Pattern description
<plain-language pattern: what's happening, when, with what setup>

## Evidence (queries + output)
<the exact SQL / Python that produced the slice; the output table>

## Hypothesis (why this happens)
<causal explanation — what indicator state / market microstructure / session timing produces this>

## Recommended fix
<specific gate / atom / threshold change — concrete + falsifiable>

## Test plan (how to validate fix doesn't block winners)
<gate-precision Q9 query; histogram against known winners; tester replay window>

## Cross-references
- Improvement-recommendation row: R<N>
- Commit (if shipped): <hash>
- Related patterns: LP<M>, LP<K>
```

## Cross-references

- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_audit_loss_patterns.md`
- `scripts/fbeta2_histogram.py` — composite score bimodality analyzer (shipped)
- (FUTURE) `scripts/loss_pattern_slicer.py` — 6-axis slice generator
