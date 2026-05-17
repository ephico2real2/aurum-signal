# Research Citations — INDEX

Well-cited external sources I've consumed during FORGE design work. Per `feedback_quant_expert_identity` + `feedback_google_mql5_before_assumptions` — research is the path to durable solutions, citation provenance the audit trail.

## Citations by topic

### ICT / SMC canon

| Source | Topic | Used for | Date consumed |
|---|---|---|---|
| https://innercircletrader.net/tutorials/ict-order-block/ | Order Block detection rules | v2.7.133 IctOrderBlock.mqh — last-opposite-candle-before-displacement rule | 2026-05-17 |
| https://innercircletrader.net/tutorials/ict-breaker-block-trading/ | Breaker Block (failed OB) trading | v2.7.133 — body-close-past-extreme + opposite-direction-retest definition | 2026-05-17 |
| https://innercircletrader.net/tutorials/ict-mitigation-block-explained/ | Mitigation Block vs Breaker distinction | Deferred Phase 3c — held-OB continuation case | 2026-05-17 |
| https://www.luxalgo.com/blog/ict-trader-concepts-order-blocks-unpacked/ | OB pattern variations + visualization | v2.7.133 OB scaffold | 2026-05-17 |
| https://atas.net/blog/what-are-ict-order-blocks-and-breaker-blocks-in-trading/ | OB + Breaker mechanics | v2.7.133 module docstring | 2026-05-17 |
| https://innercircletrader.net/tutorials/ict-optimal-trade-entry-ote-pattern/ | OTE 62-79% retracement | v2.7.123 `atom_pullback_in_ote` (existing prior) | 2026-05-15 |
| https://arongroups.co/technical-analyze/ict-equilibrium-zones/ | Premium/Discount 50% midpoint | v2.7.123 `atom_premium_discount_aligned` (existing prior) | 2026-05-15 |
| https://threads.com/@ict_smc_chartist/post/DH-UJkhsf3p | Sweep+ChoCH+FVG pattern | LIQ_SWEEP_REV composite scoring (existing prior) | 2026-05-15 |
| https://tradeciety.com/multiple-time-frame-analysis | HTF alignment methodology | `atom_htf_aligned` (existing prior) | (pre-session) |

### MQL5 / MT5 platform

| Source | Topic | Used for | Date consumed |
|---|---|---|---|
| https://www.mql5.com/en/docs/constants/structures/mqltraderequest | MqlTradeRequest schema | v2.7.132 — comment-length verification (no documented limit) | 2026-05-17 |
| https://www.mql5.com/en/forum/464340 | Order comment length empirical | v2.7.132 — old MT4 31-char claim does NOT apply to MT5 | 2026-05-17 |
| https://www.mql5.com/en/forum/104920 | Magic number + comment length | v2.7.132 — Jimmy moderator answer cited | 2026-05-17 |
| https://www.mql5.com/articles/22009 | SQLite I/O performance (transaction-wrap + WAL) | v2.7.111 JOURNAL_BATCH_TXN + WAL_MODE knobs (existing prior) | (pre-session) |

### Research / Strategy methodology

| Source | Topic | Used for | Date consumed |
|---|---|---|---|
| `docs/research/ICT_KILLZONES.md` | Canonical ICT killzone definitions + NY anchoring | F-α (v2.7.122) — 5 KZ + 3 SB window definitions | 2026-05-15 |
| SSRN 6143486 | SUM3API hybrid architecture (MQL5 ⇄ ZeroMQ ⇄ Rust + QuestDB) | Long-term observability vision (skill §I.8) | (pre-session) |

## Update protocol

- One row per source consumed.
- Topic + how-used keeps the citation actionable rather than archival.
- "Date consumed" lets future-me check if the source has updated since the citation
- Long-form analyses get their own file (e.g. `ict_killzones_deep_dive.md`); INDEX rows link to those.

## Cross-references

- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_google_mql5_before_assumptions.md`
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/feedback_research_mql5_keywords.md`
- `.claude/skills/forge-monitor/SKILL.md §I.5 + §I.5a + §I.14` — research mandates
