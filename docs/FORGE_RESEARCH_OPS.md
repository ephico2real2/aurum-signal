# FORGE Research Operations — Canonical Standard for Pattern Discovery + ICT Edge Squeezing

**Status**: living — append per skill mandate
**Owner**: operator (`ephico2real2`)
**Created**: 2026-05-16 (formalising the 6-month manual workflow)
**Companion docs**: `FORGE_SETUP_ICT_MAP.md` (taxonomy), `QUESTDB_EVALUATION.md` (future ETL/ML), `FORGE_GLOSSARY.md` (terms)

---

## §1 Vision — what we're actually doing

FORGE is **not a strategy** — it is a **system for discovering, codifying, and exploiting market anomalies**. The 28+ active setups in `FORGE_SETUP_ICT_MAP.md §4` exist because each one captures a specific anomaly observed in live + tester data and then formally instrumented. The ICT framework (`§B.2` — 4 entry categories + killzone dimension) gives this work a **canonical ontology** so that anomalies map to a known set of structural primitives rather than to bespoke names.

Operator framing (verbatim, 2026-05-16):

> *"It is because of cases like this that I had so many strategies setup. This is the work of quant. They continuously analyze anomalies to squeeze out the edge — and why my setup grew."*

This doc captures the **operating loop** that produces each setup. It is the methodology — the WHY behind every per-setup case study, gate addition, atom definition, and geometry override. New contributors (or new Claude sessions) read this BEFORE touching `ea/FORGE.mq5` or proposing a new composite.

### §1.1 What edge looks like in this system

Edge in FORGE is a **regime-specific deviation from random**: a price-action pattern (e.g. Asian-session V-flush + lower-wick rejection + bullish ChoCH) whose forward-30-min P&L distribution is statistically biased relative to random entry in the same conditions. The edge is small per-trade (5-15 pts typical), session-specific, and structural — meaning it's tied to identifiable market microstructure events (liquidity sweeps, killzone transitions, HTF alignment shifts), not to indicator-overlay coincidences.

Edge is fragile. A change in market regime, broker behaviour, or session microstructure invalidates the edge — which is why every shipped setup carries a **kill-switch env flag** (default-able to 0) and every per-tick gate firing logs to SIGNALS for post-mortem reconstruction.

### §1.2 What this loop is NOT

- **Not feature accretion.** Setups don't get added because they look interesting. They get added because the anomaly is observed in live data, replayable in tester, atom-validated against canonical ICT primitives, and confirms positive expected value across the relevant regime.
- **Not premature ML.** ML pipelines (per `QUESTDB_EVALUATION.md`) are the future engine that automates what humans + Claude sessions do today via case studies. ML doesn't replace the canonical 8-step loop in §2 — it scales it.
- **Not over-optimization.** Every setup ships **Mode A first** (log-only, no entry impact) before promotion to Mode B (warning de-rate) → Mode C (hard gate). Calibration evidence is required at each promotion per `feedback_supermajority_composite_threshold`.

---

## §2 The 8-step canonical operating loop

Every shipped setup (whether legacy chart-pattern or ICT-canonical) follows this exact sequence. Skipping a step is the **#1 anti-pattern** documented in §8.

```
1. OBSERVE       Live trade or tester run produces an anomaly worth investigating
                 (canonical example: G5001 win + G5003 loss, 49 min apart, same price)
2. QUERY         Pull SIGNALS + TRADES + market_data.json for the affected window
                 (per skill MANDATORY: verification-first principle)
3. ICT-FRAME     Slot the anomaly into one of 4 ICT entry categories (§B.2):
                 MSS_CONTINUATION / OTE_RETRACEMENT /
                 LIQUIDITY_SWEEP_REVERSAL / BREAKER_RETEST
                 If it doesn't slot — STOP. Either misclassification or out-of-scope.
4. ATOM-REPLAY   Replay the §B.8.2 atom catalog against the affected ticks:
                 - which atoms fired, which were null
                 - compute weighted composite score
                 - confirm winners + losers differentiate at score-bucket
5. GEOMETRY-FIX  If atom layer is correct but P&L is wrong, the geometry is the bug.
                 Per `feedback_chop_scalp_one_tp_fast_sl` — chop-scalp profile:
                 TP1=0.4×ATR, BE-snap on TP1, NO staged-add, NO wave-amp.
6. MODE A SHIP   Wire atoms + composite (log only) behind `FORGE_*_ENABLED=0` flag.
                 5-layer schema-parity per skill mandate. Backtest range with logging.
7. CASE STUDY    Formalise as `docs/FORGE_CASE_STUDY_YYYY_MM_DD_<NAME>.md` per skill.
                 Cross-link from FORGE_SETUP_ICT_MAP.md §3.x + §9 changelog.
                 Reference from forge-monitor SKILL.md so future sessions audit.
8. PROMOTE       Mode A → B → C per `FORGE_PEMCG_ICT_INTEGRATION.md`:
                 - A: log-only (default OFF flag, default ON)
                 - B: warning de-rate (lot×0.7 on low score)
                 - C: hard block (gate_reason=<cat>_score_below_threshold)
                 Calibrate against known winners + losers before each promotion.
```

### §2.1 Sequence is load-bearing

Steps cannot be re-ordered:
- **Step 1 before Step 2** — observe in live data first; queries against synthetic data don't validate edge
- **Step 3 before Step 4** — atom-replay against the WRONG category produces garbage scores
- **Step 4 before Step 5** — fixing geometry before validating atoms means you don't know what you fixed
- **Step 6 before Step 8** — Mode A audit must precede Mode B/C calibration

### §2.2 Time investment per setup

| Step | Typical effort | Output |
|---|---|---|
| 1 — Observe | 5-15 min | Anomaly identified, scope defined |
| 2 — Query | 15-30 min | SIGNALS + TRADES extracted, narrative reconstructed |
| 3 — ICT-frame | 15-30 min | Category locked, atoms identified |
| 4 — Atom-replay | 30-60 min | Truth table for affected ticks |
| 5 — Geometry-fix | 30-60 min | Geometry profile drafted, expected swing computed |
| 6 — Mode A ship | 1-3 hours | 5-layer schema, hot-reload flag, backtest re-run |
| 7 — Case study | 1-2 hours | Markdown doc, cross-references, skill mandate |
| 8 — Promote | 1-2 weeks of evidence | Mode B/C calibration with hit-rate data |

**Total cycle**: ~4-8 hours of focused work per setup, plus 1-2 weeks of live evidence for full Mode C promotion.

---

## §3 Data sources catalog

### §3.1 Current (SQLite-based, manual)

| Source | Location | What it holds | Refresh cadence |
|---|---|---|---|
| **Tester journal DB** | `~/Library/Application Support/.../Tester/Agent-127.0.0.1-300[0-2]/MQL5/Files/FORGE_journal_XAUUSD_tester.db` | Per-tick SIGNALS + TRADES + TESTER_RUNS for the active backtest | Real-time during sim |
| **AURUM tester DB** | `python/data/aurum_tester.db` | Cross-run synced version of journal data (stable `aurum_run_id`) | 60s sync via BRIDGE |
| **AURUM live (scribe) DB** | `python/data/aurum_intelligence.db` | LIVE FORGE signals + trade events on real broker | Per-tick scribe writes |
| **Live market data** | `~/Library/Application Support/.../Common/Files/market_data.json` | Current bid/ask/spread, indicators_m1..h4, POC, VWAP, fib, open positions, pending orders, account state | Per-EA-tick |
| **MT5 tester logs** | `~/Library/Application Support/.../Tester/Agent-127.0.0.1-3000/logs/*.log` | EA Print() output, cascade arm events, errors | Real-time |
| **Bridge log** | `python/logs/bridge.log` | BRIDGE sync events, sync-recovery, errors | Real-time |

### §3.2 Future (per `QUESTDB_EVALUATION.md §12` — adopted)

| Source | Hot store | Cold store | Ingest path |
|---|---|---|---|
| OHLC bars (M1-MN) | QuestDB | Parquet zstd (daily partition) | Python `mt5.copy_rates_range()` poll loop |
| Tick data | QuestDB | Parquet zstd (daily) | Python `mt5.copy_ticks_range()` |
| Open positions / pending orders | QuestDB snapshot table | — | Python 5s poll via `mt5.positions_get()` / `mt5.orders_get()` |
| Closed deals | QuestDB `forge_trades` | Parquet | Python 30s idempotent poll |
| FORGE gate state (SIGNALS rows) | QuestDB `forge_signals` | Parquet | EA → SQLite → Python tail → QuestDB ILP |
| Trade groups (relational) | SQLite (stays — relational integrity matters) | — | Python aggregator |

The Python ingress (`mt5` library + ILP push) is the universal adapter that makes ML viable — see §10 for the bridge to FORGE_RESEARCH_OPS in the ML era.

---

## §4 Pattern identification methodology

### §4.1 Three signals that indicate "anomaly worth investigating"

1. **Two-trade discrepancy** — same setup type fires twice within a short window at similar prices, but one wins and one loses dramatically. Example: G5001 (+$1,212) and G5003 (−$3,655) on 2026-03-30. The atom-layer is structurally identical; the discriminator is geometry or post-entry price-action quality.
2. **Direction asymmetry on PEMCG composite** — when `pemcg_buy_reversal_block` and `pemcg_sell_reversal_block` counts have ≥ 5× ratio either direction. Indicates a structural day-type bias the DTC may or may not be catching correctly. Per skill MANDATORY PEMCG asymmetry audit.
3. **Missed opportunity** — a sustained directional move (≥ 40 pts XAUUSD) during which FORGE took ≤ 1 trade. Per skill MANDATORY Missed-Opportunity Post-Mortem. Indicates a gate over-filtering OR an entire pattern not yet instrumented.

### §4.2 Canonical queries for anomaly investigation

These are the queries every operator/Claude session runs at the start of an anomaly investigation. They are stable across schema versions because they read core columns (`time`, `magic`, `setup_type`, `direction`, `outcome`, `price`, `rsi`, `adx`, `atr`) that have been present since v2.6.

```bash
DB="$(find "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5" \
       -name FORGE_journal_XAUUSD_tester.db -print0 | xargs -0 ls -t | head -1)"

# Q1 — TAKEN entries with all the atom context
sqlite3 "file:${DB}?mode=ro&immutable=1" "
SELECT datetime(time,'unixepoch') t, magic, setup_type, direction, ROUND(price,2) px,
       ROUND(rsi,1) rsi, ROUND(adx,1) adx, ROUND(atr,2) atr, regime_label, session,
       iss_score, liq_sweep_rev_score_buy, liq_sweep_rev_score_sell,
       mss_cont_score_buy, mss_cont_score_sell, ote_retrace_score_buy, ote_retrace_score_sell
FROM SIGNALS WHERE outcome='TAKEN' AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
ORDER BY time;"

# Q2 — Per-magic P&L breakdown (which groups won, which lost)
sqlite3 "file:${DB}?mode=ro&immutable=1" "
SELECT magic, COUNT(*) deals,
       SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) wins,
       SUM(CASE WHEN profit<0 THEN 1 ELSE 0 END) losses,
       ROUND(SUM(profit),2) net,
       MIN(datetime(time,'unixepoch')) first_t
FROM TRADES WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS) GROUP BY magic ORDER BY first_t;"

# Q3 — Price trajectory in a specific window (post-entry, pre-SL)
sqlite3 "file:${DB}?mode=ro&immutable=1" "
SELECT datetime(time,'unixepoch') t, ROUND(price,2) px,
       ROUND(price - <ENTRY_PRICE>, 2) favor_pts
FROM SIGNALS WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
  AND time BETWEEN strftime('%s','<ENTRY_T>') AND strftime('%s','<ENTRY_T_PLUS_30M>')
ORDER BY time;"

# Q4 — Gate breakdown (which gates fire most)
sqlite3 "file:${DB}?mode=ro&immutable=1" "
SELECT gate_reason, COUNT(*) cnt FROM SIGNALS
WHERE outcome='SKIP' AND gate_reason!='' AND gate_reason IS NOT NULL
  AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
GROUP BY gate_reason ORDER BY cnt DESC LIMIT 15;"

# Q5 — PEMCG asymmetry (per skill mandate)
sqlite3 "file:${DB}?mode=ro&immutable=1" "
SELECT SUM(CASE WHEN gate_reason='pemcg_buy_reversal_block' THEN 1 ELSE 0 END) buy_block,
       SUM(CASE WHEN gate_reason='pemcg_sell_reversal_block' THEN 1 ELSE 0 END) sell_block
FROM SIGNALS WHERE outcome='SKIP' AND run_id=(SELECT MAX(id) FROM TESTER_RUNS);"
```

Every query result that informs a case study gets logged to `docs/FORGE_INDICATOR_ATLAS.md §13 Command Log` per the skill MANDATORY rule.

### §4.3 ICT atom-replay protocol

Once an anomaly is queried, replay the §B.8.2 atom catalog against the affected ticks:

1. For each TAKEN signal in the affected window, pull the per-atom columns:
   - `iss_mss`, `iss_fvg`, `iss_choch_support`, `iss_choch_against`
   - `liq_sweep_rev_score_buy/sell`
   - `mss_cont_score_buy/sell`
   - `ote_retrace_score_buy/sell`
2. For each magic with a loss, find the entry signal and check whether the composite hit threshold (≥7) and whether the per-atom breakdown matches the canonical pattern.
3. Build a truth table: per-atom column × win/loss. The columns that fire on winners but not losers (or vice versa) are the **differentiators**.
4. If the truth table doesn't differentiate (winners and losers score the same), the atom layer is NOT the bug — geometry is. Proceed to §5.

### §4.4 Geometry-fix protocol

When the atom layer is correct but P&L is wrong:

1. **Compute the favorable peak** of the losing trade (max price post-entry, pre-SL).
2. **Compute what would have triggered TP at canonical chop-scalp profile** (TP1=0.4×ATR, TP2=1.0×ATR).
3. **If TP1 would have hit**: the loss is preventable. The fix is per-setup geometry override (NOT global geometry change — global changes affect every setup).
4. **If TP1 would NOT have hit**: the trade entered too early in the move. Look for an additional entry-quality atom that filters by post-entry price-action signal.
5. **If both TP1 and TP2 hit but the trade still lost**: this is the wave-amp / staged-add overcommitment failure. Disable amplifiers for this setup category.

### §4.5 Industry research mandate

Per `feedback_research_mql5_keywords` + skill MANDATORY WebSearch industry validation: **every proposed atom or geometry override MUST be backed by at least 2 canonical-pattern citations** (ICT canon, MT5/MQL5 community articles, peer-reviewed quant research). The mantra: *"the MT5/MQL5 community has worked on most scalping problems for 15+ years. If you can't find prior art, search harder."*

Cite sources in:
- Case study §4 (industry pattern findings subsection)
- Atlas §13 Command Log
- Composite proposal recommendation (per `RECOMMENDATIONS PATTERN`)

---

## §5 What's NOT aligned (current gaps)

This section is **append-only as gaps are discovered**; items resolved move to §11 changelog with status.

| # | Gap | Severity | Plan |
|---|---|---|---|
| 1 | LIQ_SWEEP_REV_SCORE composite wired but not used as gate; `FORGE_COMPOSITE_LIQ_SWEEP_REV_SCORE_ENABLED` defaults OFF in `.env` | HIGH — blocks Mode A → B promotion | Flip flag, re-run, validate truth table against G5001/G5003 case study |
| 2 | No `LIQUIDITY_SWEEP_REVERSAL_BUY` setup function exists; only `ASIA_CAPITULATION_BUY` covers the pattern (Mode A baseline) | HIGH | Ship v2.7.125 with new entry function + chop-scalp geometry profile |
| 3 | `IctOrderBlock.mqh` scaffolded but 0 functions (Phase 3 deferred); BREAKER_RETEST composite returns 0 | MEDIUM | Schedule Phase 3 (v2.7.121) per skill §I.2 |
| 4 | `IctIntradayModel.mqh` scaffolded but 0 functions (Phase 5 deferred); CRT / Venom / B&B / RDRB models not implemented | LOW | Defer to post-Phase-3 |
| 5 | QuestDB ingest pipeline not yet running; all data still SQLite | MEDIUM (ML scope) | Per `QUESTDB_EVALUATION.md §12` — Python MT5 module + QuestDB ILP + Parquet archive |
| 6 | No automated anomaly detection — every case study is manual | MEDIUM (ML scope) | Future: ML feature store + walk-forward + random-entry baseline (post-QuestDB) |
| 7 | `iss_score` atoms stub at 0 (v2.7.112 scaffolding); real detection scheduled for v2.7.115+ | MEDIUM | Phase 2.5 ship per `docs/ICT-Structure-Score.md` |
| 8 | `FORGE_GLOSSARY.md` not always kept current with new atoms / composites | LOW | Per skill §I.12 — update glossary in SAME commit as the term-introducing code change |

---

## §6 Tools, skills, and roles

### §6.1 Skills (`.claude/skills/`)

| Skill | When to invoke | Primary output |
|---|---|---|
| `forge-monitor` | During an active backtest OR live trading session | Per-tick anomaly surfacing + case study creation + skill mandate addition |
| `forge-ea-review` | After modifying `ea/FORGE.mq5` / config / scribe / dashboard | Cross-system consistency validation (5-layer schema parity, dead env vars, gate legend coverage) |
| `research` | When designing any new atom / composite / geometry | WebSearch industry validation + `docs/RESEARCH_NOTES_<topic>.md` |
| `aurum-bridge-monitor` | When validating AURUM↔BRIDGE flow (S1/S1b/S2/CONFIRM gates) | Live event relay during Telegram test |
| `mcp-trace-aurum` | When modifying the LENS MCP fork (`/Users/olasumbo/tradingview-mcp-aurum/`) | NDJSON tracer-based validation loop |

### §6.2 Memory files (operator-mandated rules)

Per `~/.claude/projects/-Users-olasumbo-signal-system/memory/MEMORY.md`:

- `feedback_chop_scalp_one_tp_fast_sl.md` — chop scalp geometry
- `feedback_no_dead_env_vars.md` — every FORGE_* env var must be fully wired
- `feedback_supermajority_composite_threshold.md` — ≥0.7×N for composite gates
- `feedback_research_mql5_keywords.md` — WebSearch industry validation
- `feedback_trade_setup_analysis_framework.md` — 6-section template for PRE-trade questions
- `feedback_trade_decision_table_format.md` — PER-trade post-mortem format
- `feedback_no_design_ceiling.md` — explore the full design space, don't pre-narrow
- `feedback_glossary_update_mandate.md` — update glossary in same commit
- `feedback_decision_log_mandate.md` — every ship logs to skill §I.11

### §6.3 Roles (you + me)

- **Operator** (`ephico2real2`) — domain expert, decides what to ship, has veto on every commit
- **Claude / Claude Code** — engineering partner, executes the loop, drafts case studies, never ships without operator confirmation per skill default
- **Codex / codex:rescue** — independent reviewer, used via `/forge-ea-review` when cross-validation is needed

---

## §7 Next-action priorities (refresh weekly)

Ordered by edge-impact × effort. Updated 2026-05-16.

1. **Flip `FORGE_COMPOSITE_LIQ_SWEEP_REV_SCORE_ENABLED=1`** (Mode A live test) → 1 env line + `make scalper-env-sync`. Validates the 2026-03-30 G5001/G5003 case study truth table empirically.
2. **Ship v2.7.125 `LIQUIDITY_SWEEP_REVERSAL_BUY` setup with chop-scalp geometry** (M9 milestone) — per case study §6 ship sequence.
3. **Run a multi-day backtest with Mode B promotion** to validate chop-scalp swing actually realizes vs theoretical.
4. **Audit other §3.3 Category-3 setups (BB_EXHAUSTION_REVERSAL, DOUBLE_TOP/BOTTOM, H&S)** against the same LIQ_SWEEP_REV composite. They likely fold into one canonical setup per M9 plan.
5. **Phase 3 ICT module: OrderBlock + Breaker** — fills the BREAKER_RETEST composite score that currently returns 0.
6. **Stand up QuestDB Python ingest pipeline** (per `QUESTDB_EVALUATION.md §12.1`) — start with `mt5.copy_rates_range()` daily OHLC into a parquet archive; QuestDB hot-path follows.
7. **First ML experiment: walk-forward + random-entry baseline** on FORGE atom history once QuestDB has 4+ weeks of data.

---

## §8 Anti-patterns — codified

These are the tactical shortcuts that DESTROY the loop. When tempted, re-read this section.

### §8.1 Skipping the loop steps

- ❌ **"It's a small fix, no case study needed"** — every shipped behaviour change deserves a record. Without the case study, the next anomaly investigation has no prior art to compare against. The case study IS the institutional memory.
- ❌ **"I'll add the schema migration later"** — every new SIGNALS column ships ALL 5 layers in the SAME commit (EA CREATE + ALTER + JournalRecordSignal + scribe.py + sql/). Per skill MANDATORY schema-parity. Deferred migrations are dead-on-arrival per the v2.7.119 retroactive migration incident.
- ❌ **"I'll WebSearch later"** — every new atom/composite/gate cites ≥2 canonical-pattern sources at proposal time. Per skill MANDATORY WebSearch industry validation.

### §8.2 Premature optimization / over-narrowing

- ❌ **"This setup will only fire 3 times a year, but it's a winner"** — low-frequency setups are over-fit to a single historical event. Wait for ≥10 occurrences before promoting from Mode A.
- ❌ **"Threshold 7 vs 6 — doesn't matter much"** — supermajority thresholds (≥0.7×N) have empirical basis per `feedback_supermajority_composite_threshold`. Don't tune by gut.
- ❌ **"Tighten the gate to block the loss"** — every tightening must be cross-checked against winners. A gate with <50% precision blocks more good trades than bad ones (per skill Q9 gate precision check).

### §8.3 Geometry-as-entry-fix

- ❌ **"The entry was bad — block it"** — when atom-layer is correct but P&L is wrong, the GEOMETRY is wrong, not the entry. Don't blame the atoms for a TP-too-far problem. See G5003 case study §4.
- ❌ **"Use global staged-add + wave-amp on a chop-scalp setup"** — the amplifier weaponizes itself when the bounce reverses. Per-setup geometry overrides exist for a reason.

### §8.4 Inline `.env` comments (load-bearing infrastructure)

- ❌ **`FORGE_X=42  # comment here`** — the env-sync parser `_parse_value()` calls `float(raw)` on the entire post-`=` string. Trailing `# comment` breaks `make forge-compile`. Always put comment on the LINE ABOVE. Per skill MANDATORY `.env` comment placement.

### §8.5 Drive-by changes

- ❌ **"While I'm here, let me also tweak X"** — every commit ships ONE coherent change. Drive-by tweaks make rollback granularity worse and obscure regression bisects. Open a follow-up PR if X needs attention.
- ❌ **"Drive-by normalize all docs to GFM"** — per skill retroactive normalization rule: only normalize docs you're already touching. Don't audit the whole tree.

### §8.6 Trusting the dashboard without validating

- ❌ **"Athena shows N TAKEN; that's the truth"** — the dashboard is downstream of `forge_signals` in scribe DB which is downstream of SCRIBE sync which is downstream of source journal SQLite. Any 5-layer migration miss can leave Athena reporting wrong counts (the v2.7.45/47 incident — 12-hour dark dashboard). Verify against source DB on every analytical claim.

### §8.7 Ignoring the operator mandate

- ❌ **"This is small, I'll just ship it without asking"** — per skill default + global CLAUDE.md mantra: ASK before commit. Authorization is per-change, not per-session.
- ❌ **Adding `Co-Authored-By: Claude` trailers** — per global `~/.claude/CLAUDE.md` Commit Attribution mandate. Operator is sole author, always.

---

## §9 References

### §9.1 Canonical FORGE docs
- [`FORGE_SETUP_ICT_MAP.md`](FORGE_SETUP_ICT_MAP.md) — 4 ICT entry categories, 28-setup inventory, atom catalog §B.8.2, killzone dimension §B.7, migration milestones M0-M13 §A.3
- [`FORGE_PEMCG_ARCHITECTURE.md`](FORGE_PEMCG_ARCHITECTURE.md) — PEMCG composite + 3 layer consumers + canonical acronym dictionary §1A
- [`FORGE_PEMCG_ICT_INTEGRATION.md`](FORGE_PEMCG_ICT_INTEGRATION.md) — Mode A/B/C promotion plan
- [`FORGE_GLOSSARY.md`](FORGE_GLOSSARY.md) — all terms, atoms, env vars indexed
- [`FORGE_DECISION_STACK.md`](FORGE_DECISION_STACK.md) — 5-layer entry decision architecture
- [`FORGE_INDICATOR_ATLAS.md`](FORGE_INDICATOR_ATLAS.md) — indicator catalog + command log §13
- [`FORGE_FAST_MARKET_SWEEP_RESCUE.md`](FORGE_FAST_MARKET_SWEEP_RESCUE.md) — FMSR design + §15 living backlog
- [`FORGE_NAMING_CONVENTIONS.md`](FORGE_NAMING_CONVENTIONS.md) — FORGE_* env knob naming policy
- [`FORGE_REGIME_TAXONOMY.md`](FORGE_REGIME_TAXONOMY.md) — regime state model + `g_regime` migration plan (stale reference per §I.9 — content absorbed into `FORGE_SETUP_ICT_MAP.md`)

### §9.2 Per-setup case studies (canonical examples)
- [`FORGE_CASE_STUDY_2026_03_30_LIQ_SWEEP_REV_PATTERN.md`](FORGE_CASE_STUDY_2026_03_30_LIQ_SWEEP_REV_PATTERN.md) — Category 3 LIQUIDITY_SWEEP_REVERSAL canonical reference (G5001/G5003)
- [`FORGE_CASE_STUDY_G5006_INFLECTION_POINT.md`](FORGE_CASE_STUDY_G5006_INFLECTION_POINT.md) — Inflection-point trap (PEMCG 7-atom composite genesis)
- [`FORGE_CASE_STUDY_2026_03_31_to_04_08.md`](FORGE_CASE_STUDY_2026_03_31_to_04_08.md) — Multi-day cross-pattern study
- `docs/april/2026-03-31_to_2026-04-02.md` — missed-opportunity period analysis (Period 1)
- `docs/april/2026-04-06_to_2026-04-08.md` — Period 2

### §9.3 Future / ETL
- [`QUESTDB_EVALUATION.md`](QUESTDB_EVALUATION.md) — adopted (§12 winning architecture: MT5 Python + QuestDB ILP + Parquet)
- [`FORGE_CORE_LOGIC_DESIGN.md`](FORGE_CORE_LOGIC_DESIGN.md) — recovery + multi-leg + cool-period redesign

### §9.4 ICT research
- [`docs/research/ICT_KILLZONES.md`](research/ICT_KILLZONES.md) — ICT canon citations + Approach A/B MQL5 reference

### §9.5 Memory files (operator-mandated rules)
- `~/.claude/projects/-Users-olasumbo-signal-system/memory/MEMORY.md` — full index
- Critical ones referenced throughout: `feedback_chop_scalp_one_tp_fast_sl`, `feedback_supermajority_composite_threshold`, `feedback_research_mql5_keywords`, `feedback_no_dead_env_vars`, `feedback_glossary_update_mandate`, `feedback_decision_log_mandate`, `feedback_trade_setup_analysis_framework`

### §9.6 External
- [SSRN 6143486](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6143486) — SUM3API: Rust + ZeroMQ + MQL5 reference architecture
- [huggingface.co/ContinualQuasars/SUM3API](https://huggingface.co/ContinualQuasars/SUM3API) — reference implementation
- ICT canon: `innercircletrader.net` tutorials, JadeCap entry-models, FXNX gold guides, FXM Brand 2026 ICT guide

---

## §10 Future direction — ML/ETL bridge to QuestDB

The 8-step loop in §2 is **manual today**. The same loop becomes **partially automatable** once `QUESTDB_EVALUATION.md §12` ships. Here's how each step maps:

| §2 Step | Manual today | QuestDB-ML-enabled future |
|---|---|---|
| 1 Observe | Human notices anomaly during forge-monitor | Anomaly detector flags candidates via deviation from baseline P&L distribution per regime/session bucket |
| 2 Query | Human writes SQL against SQLite | Pre-computed feature store in QuestDB; queries return in <1s |
| 3 ICT-frame | Human reads §B.2 + slots manually | LLM-assisted classification using §B.8.2 atom values as features |
| 4 Atom-replay | Human reads truth table | Auto-generated per-atom contribution analysis (SHAP-like) |
| 5 Geometry-fix | Human computes peak + TP simulation | Walk-forward optimization over chop-scalp vs trend-ride profile grid |
| 6 Mode A ship | Human writes EA code | Same — code is operator's domain. ML can SUGGEST atoms but won't write MQL5. |
| 7 Case study | Human writes Markdown | Auto-draft skeleton + human polish |
| 8 Promote | Human reads dashboards | A/B harness with statistical significance gating |

**What ML adds**:
- Anomaly detection at scale (find anomalies in months of data, not just visible incidents)
- Feature interaction discovery (which atom combinations predict edge?)
- Walk-forward + random-entry baselines per setup (validate edge without data leakage)
- CI-blocking lookahead tests (no peeking the future during atom evaluation)

**What ML does NOT add**:
- The decision to add a setup. Operator + Claude session retain veto.
- The atom or composite design. ICT canon dictates structure; ML calibrates weights.
- Production trading decisions. Per §I.8 SUM3API operator mandate: **MQL5 EA stays the brain**. QuestDB + ML is the **analysis / observability layer**, not the executor.

**Ship sequence to ML-enabled state**:

1. (now) Stand up Python ingest pipeline per `QUESTDB_EVALUATION.md §12.1` — start with daily OHLC into Parquet, no QuestDB yet
2. (week +1) Add QuestDB ILP push; mirror SQLite scribe events
3. (week +2-3) Backfill historical SIGNALS + TRADES from existing scribe DBs into QuestDB
4. (week +4+) First ML experiments: feature importance on existing atom catalog using win/loss labels
5. (week +6+) Walk-forward harness with random-entry baseline per ICT category
6. (month +2) Auto-anomaly detection feeding the case-study queue

Each ship lands a `docs/QUESTDB_PROGRESS_<MILESTONE>.md` log per the case-study mandate.

---

## §11 Changelog

| Date | Change |
|---|---|
| 2026-05-16 | Initial creation. Formalises the 6-month manual workflow used to ship the 28 active FORGE setups. Captures: the 8-step canonical operating loop §2, current + future data sources §3, pattern identification methodology §4, current gaps §5, tools/skills/roles §6, next-action priorities §7, anti-patterns §8 (including the recently-codified `.env` inline-comment + GFM mandate + Co-Authored-By trailer rules), references §9, ML/ETL bridge §10 hooking into `QUESTDB_EVALUATION.md §12`. Origin: operator request 2026-05-16 — *"we need to create a standard as well to train the system with historical data and identify patterns"* + *"this is the work of quant. they continuously analyze anomalies to squeeze out the edge"*. Cross-linked from forge-monitor SKILL.md as the §-1 mandatory pre-read. |
