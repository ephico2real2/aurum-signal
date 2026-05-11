# FORGE Case Studies — Index

Curated walkthroughs of individual TAKEN signals, losses, or blocked entries that illuminate **why the EA made a specific decision** and what generalizable lesson it carries.

Use these as concrete reference points when tuning gates or interpreting Q9 precision data — abstract rules are easier to apply when anchored to a real trade.

---

## Case Studies

| # | Case | Run | Type | Outcome | One-line summary |
|---|------|-----|------|---------|------------------|
| 001 | [G5001 Apr 29 16:00 SELL — Perfect Multi-TF Bearish Alignment](001_G5001_RUN13_APR29_PERFECT_SELL.md) | 13 | TAKEN | **+$519.54** | Textbook entry: M5/M15/H1/H4 all bearish, breakout outside BB, full lot factor + cascade catches 30-pt drop with 13 legs |

---

## How to add a new case study

1. Pick a trade that's instructive (best winner, worst loss, regression block, surprising skip)
2. Pull the full SIGNALS row for the entry (all columns)
3. Pull the full TRADES list for the group (entry → all partials → final closes → cascades)
4. Walk through every gate the entry passed/failed, citing config keys and EA file:line
5. Identify the **one defining feature** that made the outcome — not just a list of indicators
6. Write a copy/paste-able pattern check for spotting similar setups going forward
7. Add the entry to the index table above (next sequential number)
8. Reference the case from `FORGE_RUN<N>_ANALYSIS.md` where it occurred
