# Missed-Opportunity Post-Mortems — Index

**Purpose**: One-line entry per period doc with status, miss count, composites proposed, validation phase.
**Owner**: forge-monitor `MANDATORY: Missed-Opportunity Post-Mortem` skill section.
**Update protocol**: append a new row whenever a new period doc lands. Existing rows update their `status` column only.

---

## Entries

| Period doc | Date range | Misses identified | Composites proposed | Status | Last updated |
|---|---|---|---|---|---|
| [april/2026-03-31_to_2026-04-02.md](../april/2026-03-31_to_2026-04-02.md) | 2026-03-31 → 2026-04-02 (3 days) | 5 (Apr 1 Asian breakout, Apr 1 LC continuation, Apr 2 London 08:35 cascade, Apr 2 NY-PM recovery, Mar 31 PM continuation) | **A**: `TREND_CONTINUATION_BUY` v2 (4 misses), **B**: `INTRADAY_REVERSAL_SELL` (1 miss; reusable for Apr 8), **C**: `RANGE_REVERSION_BUY` (1 miss) | REVIEW | 2026-05-14 |
| [april/2026-04-06_to_2026-04-08.md](../april/2026-04-06_to_2026-04-08.md) | 2026-04-06 → 2026-04-08 (3 days; Apr 3-5 weekend) | 4 (Apr 6 Asian cascade, Apr 6 London rally, Apr 7 NY-PM walk-up, Apr 8 NY reversal — case study) | **D**: `CHOP_SESSION_BREAKOUT_SELL` (1 miss; high-risk, operator-rule constrained), **E**: `CHOP_VWAP_RALLY_BUY` (2 misses), plus B+C reused | REVIEW | 2026-05-14 |

---

## Status legend

- **REVIEW** — newly written, awaiting operator sign-off on composite designs.
- **PHASE_1** — composites added to EA with `*_ENABLED=0` (shadow log only); awaiting replay backtest.
- **PHASE_2** — first composite enabled live with lot cap.
- **PHASE_3** — full deployment.
- **ARCHIVED** — composites shipped and confirmed in 2+ subsequent runs.

---

## Cross-period composite summary

Aggregated across all entries above. Composites with overlapping coverage are de-duplicated by NAME.

| Composite | Gate-code namespace | Misses covered | Period docs | Status |
|---|---|---|---|---|
| `TREND_CONTINUATION_BUY` (existing EA setup; needs trigger refinement) | `trend_continuation_buy_*` | Apr 1 03:00 Asian, Apr 1 18:00 LC, Mar 31 19:00, Apr 8 08:12 (already fires in Run 3) | Period 1 | REVIEW |
| `INTRADAY_REVERSAL_SELL` (NEW — per case study §5.7 + Period 1 §B) | `intraday_reversal_sell_*` | Apr 2 08:35 London cascade, Apr 8 12:00 NY reversal | Period 1 + 2 | REVIEW |
| `RANGE_REVERSION_BUY` (NEW) | `range_reversion_buy_*` | Apr 2 16:15 NY-PM recovery | Period 1 | REVIEW |
| `CHOP_SESSION_BREAKOUT_SELL` (NEW — operator-rule constrained) | `chop_session_breakout_sell_*` | Apr 6 01:32 Asian cascade | Period 2 | REVIEW |
| `CHOP_VWAP_RALLY_BUY` (NEW) | `chop_vwap_rally_buy_*` | Apr 6 08:00 London rally, Apr 7 PM walk-up | Period 2 | REVIEW |

**5 composites total** across both period docs, covering **9 distinct missed-opportunity windows** in the 6-trading-day Mar 31 → Apr 8 sample.

---

## Cross-reference protocol

Every per-run analysis doc (`FORGE_RUN<N>_ANALYSIS.md`) shipped after this index exists MUST end with a `## Missed-Opportunity Hook` subsection citing:
1. The period doc(s) covering the run's date range.
2. Which proposed composites would have captured trades in this run (if any).
3. Any new misses identified that should append a new period doc OR extend an existing one.

This is enforced by the `MANDATORY: Missed-Opportunity Post-Mortem` section in `.claude/skills/forge-monitor/SKILL.md`.

---

## Anti-pattern flags

- **Sub-40-pt windows are NOT misses**. The minimum threshold is 40 pts (~$4 XAUUSD) per session window. Apr 6 Miss #3 (24-pt swing) is documented in the period doc as a borderline non-miss for transparency, but no composite is proposed for it.
- **EA-version regressions are not misses**. If Run 3 (v2.7.83) caught a trade that Run 9 (v2.7.94) didn't, that's a "miss from current-baseline perspective" — only flag if v2.7.94's stricter gates were the cause AND the trade would have been a confirmed winner (not coincidentally lucky).
- **Data-zero days are not misses**. Apr 3-5 (Good Friday + weekend) have no SIGNALS rows — that's broker-side, not FORGE-side. Document the gap but don't count toward miss counts.

---

## Changelog

| Date | Change |
|---|---|
| 2026-05-14 | INDEX created. 2 period docs added (Mar 31 - Apr 2, Apr 6 - Apr 8). 5 distinct composites covering 9 misses. All composites REVIEW status awaiting operator sign-off. |
