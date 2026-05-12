---
name: forge-monitor
description: Monitor an MT5/MQL5 FORGE EA backtest by polling the source tester journal DB every 45s. ALL monitoring queries run against the source DB (SIGNALS/TRADES/TESTER_RUNS) written directly by FORGE EA — NEVER aurum_tester.db which lags by 60s+. Reports new signals, skips, taken trades, gate deltas, and SELL STOP continuation / BUY LIMIT recovery arming. Writes a per-run analysis doc and keeps the query cheat sheet current. Invoke when the user asks to "monitor the forge tester", "watch the backtest", "tail the journal", "monitor", "now monitor", or "/forge-monitor".
---

# /forge-monitor — FORGE tester journal monitor

You are debugging an MT5/MQL5 backtesting session. Be skeptical — flag suspicious
patterns rather than reporting them as normal: atr=0, identical prices, P&L moving
without trade count changing, unknown gate_reason values, all-skip runs, cascade
magics firing unexpectedly.

---

## STRICT ANALYSIS PROTOCOL — Think Like an Expert Quant/Scalper

**Never attribute a loss to a single indicator in isolation.** ADX, RSI, and ATR are context
signals — they do not individually explain wins or losses. Always answer the 3-question
framework before drawing any conclusion.

### The 3-Question Loss Framework (run for every loss)

**Q1 — Direction**: Was price moving in the right direction at entry, even briefly?
- YES + stopped by wick → SL structure problem (too tight, not a bad setup)
- YES + held too long → TP structure problem (capture the move, re-enter)
- NO → Direction failure (setup fired into wrong momentum — gate or regime issue)

**Q2 — SL proportionality**: Was the SL proportional to ATR?
- Minimum viable SL for cascade/continuation orders: **1.5×ATR**
- SL < 1×ATR = will be wicked out on normal noise. Not a losing setup — a structural flaw.

**Q3 — TP reachability**: Did price actually reach TP territory before reversing?
- Price past TP1 but no TP triggered → TP set too far — short scalp TP needed
- Price never reached TP territory → Direction was wrong — fix the entry gate, not the TP

### Loss pattern decision tree

```
Was price in favorable territory at any point?
├── YES: How far?
│   ├── Past TP1 (>100%): TP too far → add/shorten sell_stop_cont_tp_atr_mult
│   ├── 50–99% of TP1:    TP nearly reached → SL may be too tight OR TP slightly too far
│   └── <25% of TP1:      Trend failure → fix entry gate (adx_max, setup type, direction filter)
└── NO (only intrabar):   Intrabar scalp missed → lower tp1_atr_mult to 0.4× to catch first push
```

### ADX interpretation rules (data-validated, Run 7–9)

**ADX tells you momentum strength, NOT direction.** From actual run data:
- G5003 WON at ADX=41.3 (highest ADX = biggest winner)
- G5007 LOST at ADX=37.4 (similar range, price went wrong direction)
- G5008 WON at ADX=34.3 (similar to G5007, price went right direction)
- **Conclusion: ADX range 23–42 does not predict win/loss. Direction does.**

Only use ADX to:
- Block BB_BOUNCE when ADX > threshold (trending market, wrong setup type)
- Tier lot sizes (high ADX = smaller lot per config)
- Do NOT use ADX to block BB_BREAKOUT — a SELL at ADX=41 can be the best trade of the run

### Scalping principles for XAUUSD (validated against runs)

1. **Short TP, re-enter** — Take 0.4×ATR at TP1, exit, re-evaluate. Do not hold for 4×ATR.
   The market will often give you 3-4 scalp entries in the same direction vs one big TP.

2. **Cascade orders need their own TP** — `sell_stop_cont_tp_atr_mult` ~0.8×ATR.
   G5003 and G5008 cascades had +8 and +21 pts of favorable movement with NO TP.
   At 0.08 lots that was $64 and $170 of missed profit per cascade.

3. **SL width for cascade legs** — minimum 1.5×ATR from entry. G5001/G5002 were stopped
   on a 4.34 pt wick (0.8×ATR) then the market moved 23 pts in the right direction.

4. **Scalp timeframe = seconds to minutes, not hours** — cascade/continuation orders must
   expire within 2 bars (10 min). `sell_stop_cont_expiry_bars=2` (was 8 = 40 min, absurd
   for scalping). If momentum hasn't continued within 10 min of TP1, the setup is dead.
   G5008 held 14 hours overnight — a filled cascade position needs a EA-side max_hold_bars
   enforcement (pending EA code addition: `sell_stop_cont_max_hold_bars`).

   **Flag during monitoring**: any cascade position open >3 bars after fill = anomaly, report it.

5. **Direction is the primary filter** — not ADX. A SELL that fires when the next 5 bars
   go UP is a direction problem. ADX just tells you how strongly the current move is trending.

### SKIP signal analysis — gate precision assessment

**Run at stop condition** alongside Q6b loss analysis. For every major gate, check whether
blocked signals had price move against the blocked direction (gate correct) or in the blocked
direction (missed win). Use Q9 below.

**Known EA processing order** (affects which signals have indicator values):
```
1. session_off          → logged with RSI=0, ADX=0  (no indicators computed yet)
2. warmup check         → logged with RSI=0, ADX=0
3. entry_quality_direction → logged with RSI=0, ADX=0  ← all direction gate signals
4. entry_quality_body   → logged with RSI=0, ADX=0  ← all body gate signals
5. [RSI, ADX, ATR computed here]
6. rsi/adx/rr/setup gates → indicators populated
```
**Consequence**: gate precision can only be measured for gates that fire AFTER step 5.
Do NOT attempt RSI/ADX analysis on direction/body gate blocks — those values are always 0.

**Validated gate precision from Run 9:**

| Gate | Precision | Action |
|---|---|---|
| `entry_quality_rsi_buy_ceil` | 0% on strong trends | Raise ceiling for momentum moves; wrong gate for trends |
| `entry_quality_adx_min_sell` | 25% | Over-filtering; ADX 20–25 SELLs mostly move right |
| `rr_too_low` | 60% | Best gate — keep, prevents genuinely bad R:R setups |
| `entry_quality_direction` | Cannot assess (RSI=0) | Measure only via post-block price movement |
| `entry_quality_body` | Cannot assess (RSI=0) | Same |

### Q9 — SKIP gate precision query (run at stop condition)

```python
python3 << 'EOF'
import sqlite3
DB = "<active DB path>"
conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)

# Only analyse gates where indicators ARE computed (RSI>0, ADX>0)
gates = ["entry_quality_rsi_buy_ceil","entry_quality_adx_min_sell","rr_too_low","no_setup"]
for gate in gates:
    rows = conn.execute(f'''
        SELECT time, direction, ROUND(price,2), ROUND(rsi,1), ROUND(adx,1), ROUND(atr,2)
        FROM SIGNALS WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
          AND outcome="SKIP" AND gate_reason="{gate}"
          AND rsi>0 AND adx>0
        ORDER BY time LIMIT 10
    ''').fetchall()
    correct=0; wrong=0
    for sig_time, direction, price, rsi, adx, atr in rows:
        nxt = conn.execute(f'''
            SELECT ROUND(price,2) FROM SIGNALS
            WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
              AND rsi>0 AND time > {sig_time} AND time <= {sig_time}+900
            ORDER BY time LIMIT 1
        ''').fetchone()
        if nxt:
            delta = nxt[0]-price
            ok = (delta>0.5 if direction=="SELL" else delta<-0.5) if direction else None
            if ok is True: correct+=1
            elif ok is False: wrong+=1
    total=correct+wrong
    if total: print(f"{gate}: {correct}/{total} correct ({round(correct/total*100)}%) | {wrong} missed wins")
conn.close()
EOF
```

### When recommending parameter changes

Always cross-check EVERY proposed change against wins AND losses:
- Does tightening gate X block the losses WITHOUT blocking the wins?
- Run the gate against the full TAKEN list — if a proposed filter would have blocked a winner,
  it costs more than it saves.
- Prefer structural fixes (TP/SL geometry) over gate changes — they work across regimes.
- Use gate precision (Q9) to validate: a gate with <50% precision is blocking more good trades
  than bad ones and should be loosened or removed.

> **ALWAYS query the source tester DB for all monitoring.** aurum_tester.db is
> synced by bridge every 60s and lags by 1–3 minutes during active runs — it is
> stale and must NOT be used for live monitoring. Use aurum_tester.db only in
> Step 4 to look up the stable `aurum_run_id` for naming the analysis doc.

The source DB is read-only. aurum_tester.db is also read-only (bridge manages it).
The cheat sheet and analysis docs are writable.

---

## BOOLEAN COMPOSITE ANALYSIS (mandatory for every setup/signal decision)

**Going-forward rule:** every analytical claim about whether a setup should fire — or
why it failed — must follow the boolean-composite pattern. Single indicators in isolation
are not sufficient. Use existing FORGE globals first; only define a new global if no
existing combination expresses the principle.

### BEFORE doing any composite analysis — pull research-ops + decision stack + atlas + playbook

**FOUR documents** are mandatory reads / writes for entry-logic work:

**−1. `FORGE_RESEARCH_OPS.md` (root folder)** — the vision + operating loop. Read when
you need the WHY behind the workflow. Anti-patterns are codified there. If you find
yourself about to take a tactical shortcut, check §8 anti-patterns first.

Update `FORGE_RESEARCH_OPS.md` when:
- Operator articulates a new process principle (new mandate / new constraint)
- A "what's NOT aligned" item from §5 resolves (or new gap emerges)
- A new next-action priority enters the loop (§7)
- A new anti-pattern surfaces worth codifying (§8)
- Append §11 changelog with the change

**0. `FORGE_DECISION_STACK.md` (root folder)** — canonical naming + the 5-layer
entry-decision architecture (Setup Trigger / Filter Chain / Boolean Composite / Atoms /
Entry Geometry). **Read SECOND (after research-ops)** — every analytical claim must
use these terms exactly (no synonyms, no "rule" vs "composite" confusion).

**0.5. `FORGE_COMPOSITE_ROADMAP.md` (root folder)** — living planning view of what
composites exist, day-type coverage, what ships in each FORGE EA version, candidate
composites under research. Complement to atlas §5 (the static spec).

**0.6. `FORGE_NAMING_CONVENTIONS.md` (root folder)** — config surface naming policy.
When adding ANY new FORGE_* env knob (or struct field, or sync mapping), follow §4
prefix hierarchy: `FORGE_SETUP_/COMPOSITE_/GATE_/ATOM_/GEOMETRY_/TIMING_/GLOBAL_`.
Direction suffix (`_BUY`/`_SELL`) always LAST. `_MULT` for ATR-derived multipliers,
`_FACTOR` for lot multipliers. Existing 146 knobs grandfathered — don't rename.

**Two more policies in this doc**:
- **§4.6 Timeframe vocabulary** — use HTF/MTF/LTF/DAILY (not "macro") in new knob names
- **§4.7 Gate Code naming** — when adding a NEW `gate_reason` to `config/gate_legend.json`:
  use `<setup_or_composite>_<gate_concept>_<direction?>` (e.g.,
  `bull_day_dip_buy_fib_below`, `intraday_reversal_sell_rsi_above`).
  Use `_block` not `_blocked`. Direction LAST. Existing 65 codes grandfathered.
- **§5.0.1 Python-contract preservation** — ANY rename must preserve JSON keys + screening
  logic + Python-app consumers. Three-grep audit checklist.
- **§5.0.2 LEGACY_ALIASES backward-compat pattern** — canonical rename mechanism.

Update `FORGE_NAMING_CONVENTIONS.md` when:
- A new naming pattern category emerges (e.g., new prefix needed)
- An open question from §7 is resolved (e.g., REQUIRE→BLOCK polarity decision)
- A consensus policy refinement after using the policy in practice
- New gate code added to `config/gate_legend.json` (verify it follows §4.7)
- Append §9 changelog.

**0.7. `FORGE_REGIME_TAXONOMY.md` (root folder)** — regime state model + migration plan.
When reading or writing regime/trend variables (currently 56 across globals / handles /
struct fields / per-tick locals), consult this doc to find the canonical answer. Phase 1
(v2.7.36) uses existing variables; Phase 2+ migrates to `g_regime` struct.

**Vocabulary reminder** (defined in `FORGE_REGIME_TAXONOMY.md §2.6` — read once, internalize):
- **HTF** = Higher Time Frame (H1 + H4) — what we previously called "macro"
- **MTF** = Middle Time Frame (M15 + M30)
- **LTF** = Lower Time Frame (M1 + M5, execution)
- Industry-standard from Murphy / Tradeciety / Markets4you / most modern intraday literature.
- Field names in `RegimeState` use HTF prefix (`htf_label`, `htf_confidence`, `htf_h1_strong`)
  and `intraday_counter_htf` for the Apr 8 PM-class divergence detector.
- Avoid "macro" / "divergence" in code — terminology collisions (macro = economics; divergence = RSI/MACD).

Update `FORGE_REGIME_TAXONOMY.md` when:
- A new regime concept added or removed
- A migration phase completes (Phase 1 → 2 → 3 → 4)
- Industry-terminology research lands rename decisions (renames the `g_regime.*` fields)
- A conceptual gap closes (intraday-vs-macro, news regime, session regime, killzone)
- A new code path is migrated from old globals to `g_regime.*`
- A killzone-aware composite gating change (per §11.4 table) — update the table + add an entry in §12 changelog
- Append §12 changelog.

**0.7.1. `docs/research/ICT_KILLZONES.md`** — research source-of-truth for the ICT killzone
framework (4 windows: Asian, London Open, NY Open, London Close). The MQL5 reference
implementation (Approach A `TimeGMT()` + Approach B manual broker-offset) lives here.

The **authoritative integration point** for FORGE is `FORGE_REGIME_TAXONOMY.md §11` —
Layer 5 atoms `g_regime.killzone` + `g_regime.minutes_into_kz`. Read both when:
- Designing a killzone-aware composite filter chain (cite §11.4 table)
- Computing the `killzone` SIGNALS column (v2.7.36 schema item per §11.6)
- Adding a per-killzone gate code to `config/gate_legend.json` (§11.5)
- Debugging DST or NY-time offset issues (use Approach B; tester is unreliable for `TimeGMT()`)
- Validating against the Mar 31 → Apr 8 case study (must run §11.8 checklist before merge)

When researching new killzone behavior, append findings to `docs/research/ICT_KILLZONES.md`
§11 changelog with the citation + the FORGE integration impact.

Update `FORGE_COMPOSITE_ROADMAP.md` when:
- New composite designed → add to §1 inventory + §8 status dashboard
- Composite ships in an EA version → move from "design" to "validated" status
- Composite superseded by another → mark in §1 (and atlas §5)
- New day-type analyzed in a case study → add row to §2 coverage matrix
- A research candidate from §6 shows statistical edge → promote to Tier 2 in §5
- Append §10 changelog with the change.

After ANY of the following, update `FORGE_DECISION_STACK.md`:
- New setup type added to `ea/FORGE.mq5` → cite in §5 (Setup Type row)
- New gate code in a filter chain → reference in §4 if it introduces a new naming pattern
- New boolean composite created → register in atlas §5, cross-reference in §6 usage examples
- New atom (indicator predicate) — add to atlas §1 inventory; if it changes the 5-layer model, update here
- Entry geometry changes (SL/TP/lot multipliers) — Playbook §5 is canonical; ensure §5 here still aligned

Append a one-line entry to `FORGE_DECISION_STACK.md` §9 changelog with the change.

**1. `docs/FORGE_INDICATOR_ATLAS.md`** (renumbered: was #1, now #2 — but #0 above is now FORGE_DECISION_STACK.md) — canonical, continuously-updated source of truth for:
- Every FORGE indicator (with `ea/FORGE.mq5:NNNN` cite + SIGNALS-table population status)
- Every validated boolean composite (with calibration history + cross-day truth tables)
- Logging gaps (computed live but not logged → not yet validatable)
- Day-type pattern coverage matrix
- **Scribe DB schema** (§11) — `python/data/aurum_intelligence.db` table inventory
- **Cross-DB join patterns** (§12) — for post-mortem on live trades

**2. `FORGE_SETUP_PLAYBOOK.md`** — canonical setup catalog and **boolean composite design pattern** (§10).
Every new setup type MUST follow the 8-step pattern in §10 (inventory check → boolean spec
→ cross-day validation → atom map → MQL5 translation → env wiring → atlas register → post-mortem hook).

**Read both FIRST** before constructing a new composite or critiquing an existing one.
- Reuse atoms from already-validated composites where applicable
- Check if the indicator is populated in SIGNALS or only computed live (affects validation strategy)
- Avoid re-deriving inventory you'll find in atlas §1

**After completing any composite work**, append/update BOTH docs:
- Atlas §5 — composite registry entry with calibration history
- Atlas §6 — day-type pattern coverage row
- Atlas §10 — changelog one-liner
- Playbook §1 / §5 / §7 — update setup matrix and SKIP-gate tables if new setup or gate
- Playbook §12 — changelog one-liner

Atlas §5/§6/§10 and playbook §12 are append-only (historical). Atlas §1/§3 and playbook §1
are live-updated (current state).

### MANDATORY: log every verification command to atlas §13 (append-only)

Every time you run a shell/SQL command to verify a fact that will be cited in the atlas,
a case study, or a run analysis doc — **append the literal command to atlas §13 Command Log**.
No "verified", "confirmed", or "the data shows" claim without a corresponding command-log entry.

**Format** (atlas §13 template):

```markdown
### YYYY-MM-DD HH:MM — <one-line purpose>
**Doc/section referencing this**: <atlas §X, case study §Y, run analysis §Z>
**Command**:
\`\`\`bash
<paste the literal command, no truncation>
\`\`\`
**Output sample** (first 5-10 lines if non-trivial):
\`\`\`
<output>
\`\`\`
**Conclusion drawn**: <one sentence>
```

**Why mandatory**: a future analyst (or future-you) MUST be able to re-run the exact
command and reproduce the result. Paraphrased "I checked the data" is not auditable.
Pasted command + output + date = auditable.

**Anti-pattern**: writing "confirmed via .schema" without listing the .schema command run,
the timestamp, and the output observed. Always paste.

### MANDATORY: verification-first principle (don't assume data is available)

**Before adding a new indicator atom to a composite or implementation plan, VERIFY from production sources that the data actually flows.** Don't assume.

The 3-source verification check:

1. **FORGE.mq5 production usage** — grep `ea/FORGE.mq5` for the function/timeframe.
   If FORGE already calls e.g. `iHigh(_Symbol, PERIOD_D1, 0)` somewhere in working code,
   that confirms the data is broker-provided and accessible.

```bash
grep -nE "iHigh\(_Symbol,|iLow\(_Symbol,|iOpen\(_Symbol,|iClose\(_Symbol," ea/FORGE.mq5
# All timeframes that appear in working code are verified-available.
```

2. **market_data.json** — the live broker data FORGE writes every tick at
   `/Users/olasumbo/Library/Application Support/.../Terminal/Common/Files/market_data.json`.
   Inspect to see what indicators/timeframes the broker is actually serving:

```bash
cat "/Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/market_data.json" | python3 -m json.tool
# Look for indicators_m1 / m5 / m15 / m30 / h1 / h4 sections.
# Confirms what's exposed live by THIS broker on THIS account.
```

3. **broker_info.json** — confirms broker capabilities and account type:

```bash
cat "/Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/broker_info.json" | python3 -m json.tool
# Note: trading hours, leverage, account currency may affect indicator behavior.
```

**Anti-pattern**: writing "we will use macd_hist on H4" without first verifying that the
broker provides H4 MACD data — different brokers/accounts have different feed coverage.

**Verified-available baseline as of 2026-05-12** (Vantage International Demo, XAUUSD):

| Data class | Confirmed available | Source |
|---|---|---|
| Tick: bid, ask, spread, digits | ✓ | market_data.json `price` |
| Volume profile: poc_price, vwap_price, fib_50/382/618, fib_high/low | ✓ | market_data.json `volume_profile` |
| Per-TF indicators (M1/M5/M15/M30/H1/H4): rsi_14, ema_20, ema_50, atr_14, bb_upper/mid/lower, adx | ✓ | market_data.json `indicators_*` |
| MACD histogram | ✓ on M5/M15/M30/H1 (✗ not on M1, not on H4) | market_data.json |
| RSI divergence, PSAR state | ✓ | market_data.json |
| OHLC via iHigh/iLow/iOpen/iClose on M1/M5/M15/M30/H1/H4/D1 | ✓ | verified by production code in FORGE.mq5 |
| Account: balance, equity, margin | ✓ | market_data.json `account` |
| Open positions, pending orders, recent_closed_deals | ✓ | market_data.json |
| H1 DI+/DI− (iADX buffer 1/2) | ✓ | FORGE.mq5 `:5700-5704` confirms working |

**Always re-verify before relying on this list** — broker changes, account changes,
or new symbols may shift coverage. Treat this table as "as of date verified", not eternal.

---

### MANDATORY: case study file for date-range / multi-day pattern analyses

Whenever the analysis spans **2 or more trading days** (e.g. day-typing, cross-day composite
calibration, "what worked vs what failed last week"), **create a dedicated case study file**
in `docs/`. Pattern: `docs/FORGE_CASE_STUDY_YYYY_MM_DD_to_MM_DD.md` (or single-date variant
for one-day deep-dives). This is the SOURCE-OF-TRUTH record for the analytical work, NOT
the run-N analysis doc.

**Case study file MUST include** (template — see `docs/FORGE_CASE_STUDY_2026_03_31_to_04_08.md`):

1. **Header**: type, source data (run_id, scribe table refs), method, trigger event, creation date
2. **§1 Day-by-day summary**: open/close/range/h1_trend stats/regime mix per day
3. **§2 Per-day boolean composite derivation**: hourly indicator table + composite that matches the day
4. **§3 Synthesis**: consolidated composite set + day-type coverage matrix
5. **§4 Critical-day deep-dive** if applicable: exact-pivot identification with hour-by-hour walk
6. **§4b Enhanced composites V2**: use the FULL indicator toolkit (atlas §1), not just the 5-6 obvious ones — POC, Fib 50, VWAP gaps, BB width, divergence are often the decisive atoms
7. **§5 Open questions / next-run implementation needs**: what's required to ship the composite
8. **§6 References**: atlas sections, playbook sections, related run analyses
9. **§7 Changelog**: append-only

**After creating the case study**:
- Reference it from atlas §5 (per-composite "Enhanced V2 in [case study]" link)
- Reference from atlas §6 (pattern coverage matrix row pointing to case study)
- Reference from atlas §10 changelog
- Reference from any affected run analysis doc

**Anti-pattern to avoid**: stuffing multi-day analysis into a run analysis doc. The case
study is the analytical record; the run analysis is the per-tester-run timeline. Keep
these separated.

### BEFORE doing any post-mortem on live trades — query scribe

Scribe DB at `python/data/aurum_intelligence.db` holds LIVE trade data — separate from the
tester DB (`aurum_tester.db`). For any "why did this live trade fail" or "what was the
indicator state when this fired" question:

1. **First** run `sqlite3 -readonly <scribe_db> ".tables"` to list current tables
2. **Then** run `sqlite3 -readonly <scribe_db> ".schema <table_name>"` for each relevant table
3. Cross-check against atlas §11 — if columns differ, the schema has evolved; **update atlas §11**
4. Use the four join patterns in atlas §12 (indicator state, trade outcome, regime audit, external correlation)

**Anti-hallucination rule** — the atlas §11 schema is verified-at-write-time. Schema evolves via
ALTER TABLE migrations as new FORGE versions ship. Always re-verify before relying on column
names; if you find a discrepancy with atlas §11, update the atlas immediately so the next
analyst sees current truth.

**If post-mortem reveals a logging gap** (a column needed for analysis is empty / missing):
- Append to atlas §3 with the proposed extension
- Surface as a Recommendation (per the RECOMMENDATIONS PATTERN below) in the relevant run analysis doc
- Cite the post-mortem evidence — never propose a logging extension speculatively

### The standard workflow (operator-mandated)

```
1. ANALYZE the day's data
     → query SIGNALS / forge_signals: prices, indicators, regime, h1_trend per hour
     → narrate what the market did (range, net direction, intraday chop/trend phases)

2. COME UP WITH A BOOLEAN that matches the entry pattern for that day
     → which combination of indicators would have signaled "TAKE" at the right hours
     → which would have correctly said "SKIP" at the wrong hours

3. CHECK FOR PATTERN ACROSS DAYS
     → apply the same composite to other similar days (e.g. Mar 31, Apr 1, Apr 8)
     → does it work on all of them? Or does the threshold need to flex (e.g. h1_trend 1.0 → 0.5)?
     → if a single composite doesn't cover the spectrum, identify the differentiator
       and either narrow scope (multiple composites for different day-types)
       or relax the strictest atom

4. MAP TO EXISTING FORGE INDICATORS
     → every atom in the composite → existing FORGE struct/global (file:line cite)
     → if anything new is needed, add it as `add` and minimize new globals

5. TRANSLATE TO MQL5
     → write the composite as MQL5 syntax exactly as it will appear in the filter chain
     → identify which file/line gets the new filter (`ea/FORGE.mq5:NNNN`)
     → choose: NEW setup (new entry trigger function) OR filter on existing setup
       (insert composite check into existing chain)

6. RECOMMEND
     → concrete change (config knob, new struct field, filter chain insert, new setup)
     → with risk/benefit one-liner
```

This is the meta-loop: **data → boolean → cross-day pattern → existing indicators → MQL5 → ship**.
Skipping any step produces fragile analysis. Especially step 3 (cross-day pattern check) —
a composite that works on one day but fails on similar days is not yet a strategy.

### Required output format (5 parts)

**1. Indicator table** — hourly snapshot at the candidate timestamps:

```
| Time  | Price   | RSI  | ADX  | M15 ADX | PSAR  | h1_trend | Regime     | BB upper gap | BB lower gap | macd | psar_state |
|-------|---------|------|------|---------|-------|----------|------------|--------------|--------------|------|------------|
| 16:00 | 4721.73 | 39.9 | 30.3 | 0       | BELOW | +2.32    | TREND_BULL | 43.97        | 1.43         | ...  | BELOW      |
```

Pull exact values from `forge_signals` (aurum_tester.db post-run) or `SIGNALS` (source DB live).

**2. Boolean composite** — the rule, in MQL5-syntax pseudocode using existing globals:

```mql5
bool MY_SETUP_NAME =
     (h1_trend_strength       >= 1.0)                    // existing global
  && (psar_state              == "BELOW")                 // existing global
  && (g_regime_label IN ["TREND_BULL", "VOLATILE"])       // existing global
  && (!g_daily_bear_bias)                                 // existing global
  && (m5_rsi >= 40 && m5_rsi <= 70)                       // existing per-tick
  && (m5_adx                  >= 20)                      // existing per-tick
  && (m5_close > iClose(_Symbol, PERIOD_M5, 1));          // MQL5 builtin
```

**3. Truth table** — evaluate composite at each candidate hour:

```
| Hour  | h1≥1 | PSAR=BELOW | Regime OK | NOT bear daily | RSI 40-70 | ADX≥20 | Close>prev | RESULT |
|-------|------|------------|-----------|----------------|-----------|--------|------------|--------|
| 14:00 | ✓    | ✓          | ✓         | ✓              | ✓ 56.8    | ✓      | ✓          | TAKE   |
| 16:00 | ✓    | ✓          | ✓         | ✓              | ✗ 39.9    | ✓      | ✓          | edge   |
| 17:00 | ✓    | ✓          | ✓         | ✓              | ✓ 46.4    | ✗ 17   | ✓          | SKIP   |
```

**4. Mapping** — each atom → existing FORGE source. Mark new globals with **add**:

```
| Boolean atom                  | FORGE source                | Status   |
|-------------------------------|-----------------------------|----------|
| g_regime_label                | EA global                   | ✓ exists |
| h1_trend_strength             | computed each tick (l. 5770) | ✓ exists |
| g_last_chop_buy_exit_time     | NEW state variable          | **add**  |
```

**5. Recommendation** — concrete next step (new setup, knob change, code edit), with
file:line cite and one-line risk/benefit.

### Why this discipline matters

Single-indicator claims hide multivariate truth. The same RSI=72 can be:
- A losing G5009-class BUY in TREND_BULL with bearish daily (block it)
- A winning trend-continuation BUY in TREND_BULL with bullish daily (deploy)

Only the composite distinguishes them. The boolean format is also directly
copyable into `ea/FORGE.mq5` — analysis → implementation is mechanical.

### Globals available out of the box (no need to compute)

`g_regime_label`, `g_regime_confidence`, `g_daily_bear_bias`, `g_daily_bull_bias`,
`g_adx_trend_regime`, `g_psar_state`, `g_rsi_div_type`, `h1_trend_strength`,
`h4_trend_strength`, `m1_trend_strength`, `m15_trend_strength`, `m5_rsi`, `m5_adx`,
`m5_atr`, `m5_bb_u`, `m5_bb_l`, `m5_bb_m`, `m5_close`, `prev_close`, `mid`, `bid`, `ask`,
`spread`, `h1_di_plus`, `h1_di_minus`, `m15_adx`, `macd_histogram`, `high_vol_trend`.

If your composite needs something not in this list, you may **add a new global** to
`g_sc` struct + ReadConfig. Prefer reusing existing data over recomputing.

### Trading principles encoded as composites (canonical reference)

| Principle | Composite name | Direction | Lot scale |
|---|---|---|---|
| Choppy + bullish-macro day (Mar 31, Apr 1) — dip-buy with re-entry | `CHOP_IN_BULL_TREND_BUY` | BUY | regime-aligned amplifier ×3-5, TP1-only (30-40 pips), 5-min cooldown |
| Choppy + bearish-macro day (mirror) | `CHOP_IN_BEAR_TREND_SELL` | SELL | mirror of above |
| Strong trend continuation in confirmed bull (Apr 8 NY rally) | `TREND_CONTINUATION_BUY` | BUY | full × wave-confirmation amplifier, TP1+TP2 staged |
| Strong trend continuation in confirmed bear | `TREND_CONTINUATION_SELL` | SELL | full × wave-confirmation amplifier |
| Pure range day (no macro direction) | `CHOP_LADDER` (4-leg BUY LIMIT) | BUY-biased | small lot, basket kills |
| Counter-regime SELL probe (overbought in bull) | `FRACTIONAL_SELL_IN_BULL` | SELL | fractional (0.25× base), single leg, tight TP |
| Block SELL in chop (universal) | `BLOCK_SELL_IN_CHOP` | — | gate (no trade) |
| Fast impulse capture | `MOMENTUM_DUMP` (existing) | both | dump_lot_factor with chop_block + RSI gates |

**Canonical `CHOP_IN_BULL_TREND_BUY` composite (covers Mar 31, Apr 1 — apply daily):**

```mql5
bool CHOP_IN_BULL_TREND_BUY =
     (h1_trend_strength       >= 0.5)              // bullish macro (~3× tester trend_thr_eff)
  && (!g_daily_bear_bias)                           // daily not bearish
  && (m5_rsi                  <= 50)                // dip zone (oversold-of-the-chop)
  && (price <= m5_bb_m + 0.5*m5_atr)                // price below or near BB middle
  && (m5_adx                  >= 12)                // some life (not dead flat)
  && ((TimeCurrent() - g_last_chop_buy_exit_time) >= 300)  // 5-min re-entry cooldown
  ;
```

Validation: Mar 31 (h1 avg +0.57, 63% RANGE) → 3-4 dip-buy entries. Apr 1 (h1 avg +2.26, 38% RANGE) → 2-3 entries. Same composite, different days, both work.

PSAR deliberately excluded from this composite — too noisy on M5 in choppy markets (flips with every dip). h1_trend + daily + BB structure + RSI is sufficient direction confirmation for chop-in-bull days.

### Chop vs trend geometry — operator-mandated

- **Chop scalping**: TP1 ONLY (30-40 pips / ~0.5-0.7×ATR), no TP2/TP3 chasing.
  Re-entry on next dip after TP1 banking. Gold retraces UP — re-entry capability
  is structural, not opportunistic.
- **Trend wave-riding**: TP1 (0.6×ATR) + TP2 (1.0×ATR) per leg, staged-add with
  `staged_add_min_favorable_points` proof, `wave_confirmation_lot_mult` amplifier on
  legs 2+.

Mixing these (e.g. TP3 chasing on a chop BUY) is wrong. The composite tells you which
regime you're in; the geometry follows.

---

## DB ARCHITECTURE (updated 2026-05-10)

### Source journal DB (written by FORGE EA during backtest)
MT5 Strategy Tester writes to agent-specific paths. Check ALL agents:

```
Agent-127.0.0.1-3000:
  /Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/Agent-127.0.0.1-3000/MQL5/Files/FORGE_journal_XAUUSD_tester.db

Agent-127.0.0.1-3001:
  /Users/olasumbo/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/Agent-127.0.0.1-3001/MQL5/Files/FORGE_journal_XAUUSD_tester.db
```

Auto-discover all agents:
```bash
find "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5" \
  -name "FORGE_journal_XAUUSD_tester.db" 2>/dev/null
```

Use the most recently modified DB (check mtime).

**Source DB tables** (TESTER_RUNS, SIGNALS, TRADES, STATS_CACHE):
- `TESTER_RUNS(id, wall_time, sim_start_time, symbol, balance, forge_version, scalper_mode, warmup_m5_bars, warmup_seconds, magic_base)`
- `SIGNALS(id, time, symbol, setup_type, direction, outcome, gate_reason, price, spread, atr, rsi, adx, bb_upper, bb_lower, bb_mid, poc_price, vwap_price, fib_50, rsi_divergence, psar_state, pattern_score, h1_trend, regime_label, regime_confidence, adx_trend_regime, high_vol_trend, session, magic, synced, macd_histogram, m15_adx, lot_factor, run_id)`
- `TRADES(id, deal_ticket, order_ticket, symbol, type, direction, volume, price, profit, swap, commission, magic, comment, time, time_msc, synced, run_id)` — UNIQUE(deal_ticket, run_id)

**Key columns:**
- `SIGNALS.outcome`: `'TAKEN'` or `'SKIP'`
- `SIGNALS.gate_reason`: populated when outcome='SKIP' (see config/gate_legend.json for all 34 codes)
- `TRADES.comment`: `'SCALP|BB_BREAKOUT|G5001|TP1'` (partial closes, profit=0) or `'tp 4539.89'` (final close)
- `TRADES.magic`: group magic (e.g., 207402 for G5001 = magic_base+5001) or base magic for final closes
- `SIGNALS.run_id`: matches `TESTER_RUNS.id` — always filter by `run_id=(SELECT MAX(id) FROM TESTER_RUNS)`

### AURUM tester DB (written by BRIDGE sync — 60s cadence)
```
/Users/olasumbo/signal_system/python/data/aurum_tester.db
```

**Key tables:**
- `aurum_tester_runs(aurum_run_id, wall_time, source_run_id, journal_source, symbol, forge_version, scalper_mode, balance, sim_start_time, magic_base, first_seen_utc)`
  - `wall_time`: GetTickCount64() at run start — unique entropy key per real run, survives source DB wipes
  - `aurum_run_id`: stable AURUM sequential ID (AUTOINCREMENT, never resets)
  - `source_run_id`: run_id from TESTER_RUNS (resets to 1 on each source DB wipe)
- `forge_signals(id, forge_id, time, timestamp_utc, symbol, setup_type, direction, outcome, gate_reason, price, spread, atr, rsi, adx, bb_upper, bb_lower, bb_mid, poc_price, vwap_price, fib_50, rsi_divergence, psar_state, pattern_score, h1_trend, regime_label, regime_confidence, adx_trend_regime, high_vol_trend, session, magic, journal_source, run_id, wall_time, aurum_run_id, macd_histogram, m15_adx, lot_factor)`
- `forge_journal_trades(id, forge_rowid, deal_ticket, order_ticket, symbol, type, direction, volume, price, profit, swap, commission, magic, comment, time, time_msc, journal_source, run_id, wall_time, aurum_run_id)`

**UNIQUE constraints:**
- `forge_signals`: `UNIQUE(forge_id, journal_source, wall_time)` — prevents duplicate syncs across runs
- `forge_journal_trades`: `UNIQUE(deal_ticket, journal_source, wall_time)` — same protection

**Sync lag** — BRIDGE syncs source → aurum_tester.db every 60s in batches of 5000. Lag is typically 1–3 minutes during an active run. Query the source DB for all live monitoring (see top of this skill). Use aurum_tester.db only for `aurum_run_id` lookup (Step 4) and post-run cross-run analysis.

**Sync recovery:** If aurum_tester.db lags significantly, BRIDGE auto-detects the gap using ATTACH and resets `synced=0` on missing rows within one 60s cycle (logged as `BRIDGE: sync-recovery` in bridge.log). MT5 never clears SIGNALS between runs — BRIDGE uses wall_time to distinguish runs.

**Multi-agent design:** When MT5 assigns a new tester run to Agent-3001 while Agent-3000 has an older run, both DBs are monitored simultaneously. Each gets its own `aurum_run_id`.

### Live AURUM DB (NOT for backtest monitoring)
```
/Users/olasumbo/signal_system/python/data/aurum_intelligence.db
```
This is the live trading SCRIBE DB. Do NOT query it for backtest data.

---

## SETUP (run once per monitoring session)

**Step 1** — Find the active tester DB:
```bash
find "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5" \
  -name "FORGE_journal_XAUUSD_tester.db" 2>/dev/null \
  | xargs ls -lt 2>/dev/null | head -5
```
Set `DB` to the most recently modified path.

**Step 2** — Read the cheat sheet:
`/Users/olasumbo/signal_system/docs/FORGE_TESTER_JOURNAL_QUERIES.md`

**Step 3** — Capture baseline (tick 0):
```bash
DB="<path from step 1>"
sqlite3 -readonly "$DB" "
SELECT r.id as run_id, r.wall_time, r.forge_version, r.scalper_mode,
       datetime(r.sim_start_time,'unixepoch') as sim_start,
       r.magic_base,
       COUNT(s.id) as total_signals,
       SUM(CASE WHEN s.outcome='TAKEN' THEN 1 ELSE 0 END) as taken,
       SUM(CASE WHEN s.synced=1 THEN 1 ELSE 0 END) as synced_to_aurum
FROM TESTER_RUNS r LEFT JOIN SIGNALS s ON s.run_id=r.id
GROUP BY r.id ORDER BY r.id DESC LIMIT 1;"
```

**Step 4** — Find or create the analysis doc. First get the aurum_run_id:
```bash
python3 -c "
import sqlite3
src_db = '$DB'
aurum_db = '/Users/olasumbo/signal_system/python/data/aurum_tester.db'
wt = sqlite3.connect(src_db).execute('SELECT wall_time FROM TESTER_RUNS ORDER BY id DESC LIMIT 1').fetchone()
if wt:
    row = sqlite3.connect(aurum_db).execute('SELECT aurum_run_id FROM aurum_tester_runs WHERE wall_time=?', wt).fetchone()
    print('aurum_run_id:', row[0] if row else 'NOT YET SYNCED — wait 60s and retry')
else:
    print('No TESTER_RUNS found — tester not started yet')
"
```

Ensure analysis doc: `/Users/olasumbo/signal_system/docs/FORGE_RUN<aurum_run_id>_ANALYSIS.md`

**Step 5** — Report baseline: run_id, wall_time, FORGE version, scalper_mode, sim_start, signal count, taken count.

---

## MANDATORY HOUSEKEEPING CHECKS (run once per session, flag findings inline)

Two checks have repeatedly caught silent config-drift bugs. Run them once at session start and report any failures alongside the trade monitoring — they take seconds and the cost of missing them is high.

### Check A — Dead `FORGE_*` env vars
```bash
python3 << 'EOF'
import re
from pathlib import Path
ROOT = Path("/Users/olasumbo/signal_system")
env_text = (ROOT / ".env").read_text() if (ROOT / ".env").exists() else ""
sync_text = (ROOT / "scripts/sync_scalper_config_from_env.py").read_text()
WHITELIST = {"FORGE_SCALPER_MODE"}  # consumed by bridge.py / MT5 input
forge_keys = set(re.findall(r"^(FORGE_[A-Z0-9_]+)=", env_text, re.MULTILINE))
dead = [k for k in forge_keys if f'"{k}"' not in sync_text and k not in WHITELIST]
print(f"DEAD ENV VARS: {sorted(dead) if dead else 'none — PASS'}")
# Also catch lowercase config-looking keys that bypass FORGE_ prefix
leaks = []
for m in re.finditer(r"^([a-z][a-z0-9_]*)=", env_text, re.MULTILINE):
    k = m.group(1)
    if any(tok in k for tok in ("adx", "rsi", "atr", "bounce", "breakout", "forge", "tp", "sl")):
        leaks.append(k)
print(f"LOWERCASE LEAKS: {leaks if leaks else 'none — PASS'}")
EOF
```

### Check B — Gate legend coverage
```bash
python3 << 'EOF'
import json, re
from pathlib import Path
ROOT = Path("/Users/olasumbo/signal_system")
ea = (ROOT / "ea/FORGE.mq5").read_text()
legend = json.loads((ROOT / "config/gate_legend.json").read_text())
emitted = set(re.findall(r'JournalRecordSignal\(\s*"SKIP"\s*,\s*"([a-z_]+)"', ea))
keys = {k for k in legend if not k.startswith("_")}
patterns = [p.rstrip("*") for p in legend.get("_patterns", {}) if p.endswith("*")]
missing = [g for g in emitted if g not in keys and not any(g.startswith(p) for p in patterns)]
print(f"MISSING GATES: {sorted(missing) if missing else 'none — PASS'}")
EOF
```

If either check fails:
- **Dead env**: fix by adding the mapping to `sync_scalper_config_from_env.py` OR adding the var to `tests/api/test_forge_27x_gates.py::FORGE_ENV_VARS_NOT_IN_SYNC` with rationale
- **Missing gate**: add an entry to `config/gate_legend.json` with label/explanation/category
- Either way, report in the monitoring log so the next analysis doc captures it

---

## LOOP (every 45s)

### Q1 — Sim progress
```bash
sqlite3 -readonly "$DB" "
SELECT datetime(MAX(time),'unixepoch') as latest_sim_time,
       COUNT(*) as total_signals,
       SUM(CASE WHEN outcome='TAKEN' THEN 1 ELSE 0 END) as taken
FROM SIGNALS WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS);"
```

### Q2 — TAKEN signals
```bash
sqlite3 -readonly "$DB" "
SELECT datetime(time,'unixepoch') as sim_time, magic, setup_type, direction,
       ROUND(price,2) as price, ROUND(atr,2) as atr,
       ROUND(rsi,1) as rsi, ROUND(adx,1) as adx, session
FROM SIGNALS WHERE outcome='TAKEN'
  AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
ORDER BY time;"
```

### Q3 — Gate breakdown
```bash
sqlite3 -readonly "$DB" "
SELECT gate_reason, COUNT(*) as cnt
FROM SIGNALS
WHERE outcome='SKIP' AND gate_reason IS NOT NULL AND gate_reason!=''
  AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
GROUP BY gate_reason ORDER BY cnt DESC LIMIT 15;"
```

### Q4 — Trades and P&L
```bash
# Recent trades
sqlite3 -readonly "$DB" "
SELECT deal_ticket, magic, ROUND(profit,2) as profit, comment,
       datetime(time,'unixepoch') as sim_time
FROM TRADES WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
ORDER BY time DESC LIMIT 15;"

# Summary
sqlite3 -readonly "$DB" "
SELECT COUNT(*) as total_trades,
       SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) as wins,
       SUM(CASE WHEN profit<0 THEN 1 ELSE 0 END) as losses,
       ROUND(SUM(profit),2) as total_pnl
FROM TRADES WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
  AND profit IS NOT NULL AND profit!=0;"
```

### Q5 — SELL STOP CONT + BUY LIMIT cascade arming (FORGE 2.7.10+)
Check MT5 tester log for cascade arming events:
```bash
LOGDIR="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/Agent-127.0.0.1-3000/logs"
grep -E "ArmPostTP1Ladder|SELL STOP CONT|BUY LIMIT|slot\[2\]|slot\[3\]|slot\[4\]|exhausted|RSI.*<.*min_rsi" \
  "$LOGDIR"/*.log 2>/dev/null | sort -u | tail -20
```

**Cascade magic formula** (FORGE 2.7.10+):
- Group rank 1 (G5001): `magic_base + 5001` = 207402 for magic_base=202401
- SELL STOP slot[2]: `group_magic + 20002` = 227404
- SELL STOP slot[3]: `group_magic + 20003` = 227405 (true scaling, second group)
- BUY LIMIT slot[4]: `group_magic + 20004` = 227406

RSI gate: SELL STOP only arms when `RSI > sell_stop_cont_min_rsi` (default 25.0)
BUY LIMIT only arms when `RSI > buy_limit_recovery_min_rsi` (default 35.0)

**Known bug fixed in 2.7.11**: When native TP fires before ManageOpenGroups tick (0.01 min-lot groups), ArmPostTP1Ladder was skipped. Fixed: `total==0` path now calls ArmPostTP1Ladder.

### Q6 — Losses
```bash
sqlite3 -readonly "$DB" "
SELECT deal_ticket, magic, ROUND(profit,2) as profit, comment,
       datetime(time,'unixepoch') as sim_time
FROM TRADES WHERE profit<0
  AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
ORDER BY profit ASC;"
```

### Q6b — Price movement around each loss (run at stop condition)

For every loss, pull the SIGNALS price trajectory in the 30-min window after entry to answer:
- Did price move toward TP before reversing?
- How close (%) did it get to TP1?
- Was it stopped by a wick then the move resumed?

```python
python3 << 'EOF'
import sqlite3
DB = "<active DB path>"
conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)

# Adjust losses list from Q6 output: (label, entry_price, direction, tp1_price, entry_time)
losses = [
    # ("G5001 SELL STOP", 4537.72, "SELL", 4535.55, "2026-04-29 16:20:07"),
]

for label, entry_px, direction, tp1, entry_time in losses:
    print(f"\n=== {label} | entry={entry_px} | TP1={tp1} | dir={direction} ===")
    for r in conn.execute(f'''
        SELECT datetime(time,"unixepoch"), ROUND(price,2),
               ROUND({"price - "+str(tp1) if direction=="SELL" else str(tp1)+" - price"},2) as dist_to_tp
        FROM SIGNALS
        WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
          AND time >= strftime("%s","{entry_time}") - 60
          AND time <= strftime("%s","{entry_time}") + 1800
        ORDER BY time LIMIT 20
    '''):
        t, px, dist = r
        favor = round(entry_px - px if direction=="SELL" else px - entry_px, 2)
        tp_pct = round((1 - dist / abs(tp1 - entry_px)) * 100) if abs(tp1-entry_px) > 0 else 0
        print(f"  {t}  price={px}  favor={favor:+.2f}  tp%={tp_pct}%")
conn.close()
EOF
```

**What to report per loss:**
- Max favorable pts reached and % of TP1 achieved
- Whether price reversed before or after TP1
- Pattern classification (see below)

**Loss pattern taxonomy** (from Run 9 analysis):

| Pattern | Signature | Fix |
|---|---|---|
| **SL-hunt** | Stopped on brief spike, move resumed in favor | SL too tight — widen or disable cascade |
| **Held-too-long** | Was past TP1 (>100%) but no TP triggered, slow reversal | TP too far — tighten TP on continuation legs |
| **Intrabar-only** | Favorable intrabar but bar-close never crossed TP1 | `tp1_atr_mult` too large — lower to 0.4× |
| **Trend-failure** | Peaked at <25% of TP1, reversed immediately | Wrong setup for regime — gate (e.g. adx_max, bounce_lot_factor) |
| **Overnight-hold** | Massively in profit, held past expiry, reversed next day | Expiry_bars not enforced — investigate expiry logic |

### Q7 — STATS_CACHE (hourly P&L breakdown)
```bash
sqlite3 -readonly "$DB" "
SELECT metric, ROUND(value,2) as value
FROM STATS_CACHE
WHERE metric LIKE 'hour_%'
ORDER BY metric;"
```

### Q8 — Sync lag check (optional diagnostic only — do NOT use aurum_tester.db for monitoring data)
```bash
python3 -c "
import sqlite3
src_db = '$DB'
aurum_db = '/Users/olasumbo/signal_system/python/data/aurum_tester.db'
src_cnt = sqlite3.connect(src_db).execute('SELECT COUNT(*) FROM SIGNALS WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)').fetchone()[0]
wt = sqlite3.connect(src_db).execute('SELECT wall_time FROM TESTER_RUNS ORDER BY id DESC LIMIT 1').fetchone()
if wt:
    row = sqlite3.connect(aurum_db).execute('SELECT aurum_run_id, COUNT(*) FROM forge_signals WHERE wall_time=? GROUP BY aurum_run_id', wt).fetchone()
    dst_cnt = row[1] if row else 0
    aid = row[0] if row else '?'
    print(f'Source SIGNALS: {src_cnt} | aurum_tester.db run {aid}: {dst_cnt} | lag: {src_cnt-dst_cnt}')
    if src_cnt - dst_cnt > 5000:
        print('WARNING: large lag — bridge sync-recovery may be running')
"
```

---

## WHAT TO REPORT (changes only vs prev tick)

1. **Sim time progress** and total signal count delta
2. **New TAKEN groups**: direction, session, RSI, ADX, entry price, ATR
3. **Gate changes**: new gate_reason seen for first time, or count jumping >500
4. **New trades**: TP1/TP2/TP3/TP4 partial closes (profit=0, has comment), final closes (profit>0)
5. **ArmPostTP1Ladder events** from MT5 log: slot, RSI at time, expiry, armed vs skipped (exhausted)
6. **Losses**: any profit < 0 — magic, amount, comment
7. **Sync lag** if aurum_tester.db is >5000 behind source

**Silence is valid**: "No new signals since last tick (N total)."

---

## LIVE-UPDATE THE ANALYSIS DOC EVERY TICK (mandatory)

The analysis doc at `docs/FORGE_RUN<aurum_run_id>_ANALYSIS.md` is a **living document**, not a final report. After every monitoring tick, update the doc so an operator who opens the file mid-run sees the current state — not the state from 30 minutes ago.

**What to refresh on each tick (every section above the Session Log):**

| Section | Updated each tick |
|---------|-------------------|
| Summary headline (total signals, TAKEN, P&L, W/L, Δ vs prior runs) | ✓ |
| Hypothesis validation table | ✓ — flip status to PASS as each becomes confirmed |
| TAKEN Groups table | ✓ — append new rows; do NOT mutate historical rows |
| P&L by magic | ✓ — rerun the per-magic aggregation |
| Gate breakdown | ✓ — full breakdown counts only (Q9 deferred to stop condition) |
| Critical-block sections (G5008, Apr 29 etc.) | ✓ — once sim crosses that timestamp |
| Mandatory housekeeping checks A+B | once at session start (don't re-run every tick) |
| Q9 gate precision | **deferred** — only run at stop condition (sample sizes meaningless mid-run) |
| Recommended Parameter Changes | **deferred** — only at stop condition |
| Cross-run comparison | ✓ — update Run-N column with current numbers |
| Observations & Anomalies | append when something is observed (do not rewrite) |
| Session Log | **append-only** — one row per tick (local time, sim time, what happened) |
| **Recommendations & Open Issues** | append when an issue is identified — see "RECOMMENDATIONS PATTERN" section below |
| **Operator Q&A Log** | append every time the operator asks a question and you investigate — see "OPERATOR Q&A LOG" section below |

**Convention**: The doc header should say `**Status**: in progress (sim at <latest_sim_time>)` while running, switching to `**Status**: COMPLETE` at stop condition. Total P&L should be marked `(running total)` until stop.

**Anti-patterns to avoid**:
- Do NOT rewrite the Session Log every tick — it is append-only history. Each tick adds ONE new row at the bottom.
- Do NOT mutate prior TAKEN rows. If a row's P&L was reported at tick 2, that value stays. Net P&L is computed by summing magic-aggregated rows from the TRADES table (which is the source of truth and gets new rows as TP/SL fills happen).
- Do NOT mark hypotheses PASS until the supporting evidence is in the DB. Pre-run expectations stay as `_pending_` until the relevant sim timestamp has been crossed.

**Tick cadence**: write doc updates after Q4 (P&L summary). If the tick had no new TAKEN AND no new trades AND no new gates seen for the first time, you may skip the doc update for that single tick (but still add a one-line entry to the Session Log).

---

## OPERATOR Q&A LOG (mandatory)

Every time the operator asks a question during monitoring — about a specific trade, a regime decision, why something fired or didn't, what a gate is doing, whether a fix is possible, etc. — append a chronological entry to the **Operator Q&A Log** section of the run's analysis doc.

Each entry MUST include:
1. **The question** (verbatim or paraphrased, with sim time context)
2. **The investigation path** — what queries you ran, what files you read, what greps you did
3. **The data evidence** — actual numbers from the DB, not paraphrased
4. **The answer** — your conclusion, with the limits of certainty stated
5. **Forward link** — if the question surfaces an issue that needs fixing, link to the relevant entry in the Recommendations & Open Issues section

**Why this matters**: The conversation between operator and the monitoring agent surfaces the highest-value insights of any run. If those insights are lost in the chat scrollback, the next analysis run starts cold. The Q&A Log preserves the *reasoning* behind every proposal — without it, future operators (or your future self) won't know why a specific knob was chosen.

**Template** (copy into the analysis doc):

```markdown
## Operator Q&A Log

### Q1 (sim YYYY-MM-DD HH:MM): "<operator question verbatim or summary>"
**Investigation**: <queries run, files read, hypotheses tested>
**Evidence**: <key numbers from DB, file:line cites if code-related>
**Answer**: <your conclusion, with uncertainty bounds>
**Forward link**: <if applicable, "See Issue N in Recommendations">

### Q2 (sim ...): "<next question>"
...
```

**Never paraphrase the operator's question into something vague.** "Operator asked about Apr 1 entries" is useless; "Operator asked: 'check the apr 2 entries — were they TAKEN, or blocked by entry_quality_daily_bear_block_buy?'" is what future analysis needs.

---

## RECOMMENDATIONS PATTERN (mandatory)

When investigation surfaces a fix candidate — a config tweak, a code change, a knob to tune — append a structured entry to the **Recommendations & Open Issues** section of the run's analysis doc. Do NOT scatter recommendations across the Session Log or Observations — they belong in their own section so the post-run decision-maker can find them.

Each Recommendation MUST include:
1. **Issue title** (one-line description of the problem)
2. **Evidence** — concrete numbers/timestamps/prices from the current run, NOT generic claims. "G5001 fired 5 legs at Apr 1 08:40 with regime=RANGE despite h1_trend=+2.15" — not "regime classifier seems conservative."
3. **Root cause** — verified via reading the EA code with file:line cites. If you haven't read the code, say "UNVERIFIED — speculation."
4. **Options A / B / C** — at least two alternatives, each with:
   - Brief description (1-2 sentences)
   - Concrete pseudocode showing the diff
   - Default values for any new knobs
   - Risk / blast radius (what downstream consumers are affected)
5. **Industry research** — REQUIRED: Google for canonical patterns ("MQL5 multi-timeframe regime classifier", "MQL5 PSAR scalping confirmation", etc.). Quote one canonical pattern. Adapt to FORGE — do NOT copy-paste code that won't compile. Include source URLs in markdown link format.
6. **Preferred option** — your pick, with the trade-off rationale (why this option over the others, what data would change your mind)
7. **Backward compatibility** — REQUIRED: every fix must ship behind a default-OFF env flag so the running code is not broken. Specify the flag name and default value.

**Anti-hallucination rule**: every claim about EA behavior must cite `ea/FORGE.mq5:<line>` or a SIGNALS-table query that proves it. Speculation without code or DB evidence belongs in Observations, not Recommendations.

**Industry-research requirement**: BEFORE proposing a fix, do a WebSearch for the canonical pattern. The MT5/MQL5 community has worked on most of these problems for 15+ years. Adapt the canonical pattern to FORGE's specifics — do not invent novel approaches when established ones exist. Always cite sources.

**Template** (copy into the analysis doc):

```markdown
## Recommendations & Open Issues

### Issue N — <title>

**Evidence**:
- <bullet — concrete numbers from this run>
- <bullet>

**Root cause** (verified):
- `ea/FORGE.mq5:<line>`: <relevant code>
- Mechanism: <one paragraph explanation>

**Industry pattern** (per <source>):
> "<quote>"
Source: [<title>](<url>)

#### Option A — <name> (effort/risk)
```pseudocode
<diff or function sketch>
```
Defaults: <new env knobs>
Risk: <blast radius>

#### Option B — <name>
<same structure>

#### Option C — <name>
<same structure>

**Preferred**: Option <X>. Reason: <why this beats the others, what data would change the call>.

**Backward compatibility**: ships behind `FORGE_<FLAG>=0` (default-OFF). Existing behavior preserved.
```

**Real example**: see Issue 1 in `docs/FORGE_RUN18_ANALYSIS.md` (inline regime classifier H4 lag) — that entry is the canonical example of this section's format.

---

## STOP CONDITIONS

Stop after **3 consecutive ticks with no new signals** — run is complete. Before stopping:
1. Write final summary to `FORGE_RUN<aurum_run_id>_ANALYSIS.md`
2. Report: total TAKEN, total P&L, win rate, all cascade arm events observed
3. Cross-check with Athena backtest tab: `http://localhost:7842/api/backtest/run/<aurum_run_id>`
4. Append new gate_reason codes to `docs/FORGE_TESTER_JOURNAL_QUERIES.md`
5. **Run Q6b price movement analysis on every loss** — classify each by loss pattern
6. **Write Recommended Parameter Changes section** (see below) to the analysis doc

---

## RECOMMENDED PARAMETER CHANGES (write at end of every run)

After stop condition is met, query the final gate breakdown and produce a parameter-loosening
table in the analysis doc. This section is always written — even if TAKEN count was high,
the gate breakdown reveals what was left on the table.

### Query to run

```python
python3 << 'EOF'
import sqlite3
DB = "<active DB path>"
conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
print("Gate | Count")
for r in conn.execute('''
    SELECT gate_reason, COUNT(*) as cnt
    FROM SIGNALS
    WHERE outcome="SKIP" AND gate_reason IS NOT NULL AND gate_reason!=""
      AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
    GROUP BY gate_reason ORDER BY cnt DESC LIMIT 15
'''):
    print(r)
conn.close()
EOF
```

### Gate → config key mapping (FORGE 2.7.x)

| Gate reason | Config key | Section |
|-------------|-----------|---------|
| `entry_quality_direction` | `min_directional_bars` | `safety` |
| `entry_quality_body` | `min_body_ratio` | `safety` |
| `entry_quality_rsi_buy_ceil` | `rsi_buy_ceil` | `bb_breakout` |
| `entry_quality_rsi_sell_floor` | `rsi_sell_floor` | `bb_breakout` |
| `entry_quality_rsi_sell_adx_floor` | `rsi_sell_floor` (ADX-gated variant) | `bb_breakout` |
| `entry_quality_bb_contraction` | `require_bb_expansion` | `safety` |
| `entry_quality_adx_min_sell` | `adx_min` | `bb_breakout` |
| `entry_quality_session_sell_cutoff` | `session_ny_sell_cutoff_utc` | `safety` |
| `rr_too_low` | `min_rr` / `min_rr_floor` | `safety` |
| `no_setup` | downstream of all quality gates; also gated by `require_macd_buy/sell` | `bb_breakout` |

### Standard output format for analysis doc

```markdown
## Recommended Parameter Changes — More Trades

**Context**: N signals evaluated, N TAKEN (X% take rate). Top N gates account for N SKIPs (~X% of all filtered signals).

### Current blocking gates → parameters

| Gate | Hits | Config key | Current | Proposed |
|------|------|------------|---------|---------|
| `entry_quality_direction` | N | `safety.min_directional_bars` | `2` | `1` |
| `entry_quality_body` | N | `safety.min_body_ratio` | `0.40` | `0.25` |
| `entry_quality_rsi_buy_ceil` | N | `bb_breakout.rsi_buy_ceil` | `70` | `77` |
| `entry_quality_bb_contraction` | N | `safety.require_bb_expansion` | `1` | `0` |

### Change 1 — <key>: <current> → <proposed>
**Impact**: ...  
**Risk**: ...

[repeat for each change]

### Hidden filters to check
`bb_breakout.require_macd_buy` — if set to `1` (non-default), MACD failures hide in `no_setup`
rather than their own gate_reason. Check if BUY count is still low after loosening other gates.

### Apply order
1. Lowest-risk RSI ceiling/floor adjustments first
2. `min_directional_bars` + `min_body_ratio` together (affects both directions equally)
3. `require_bb_expansion` last
4. `require_macd_buy/sell` only if frequency still insufficient after above

> **Note**: `scalper_config.json` is generated — changes go via `.env` or config template,
> then `make scalper-env-sync && make forge-compile`.
```

### Guidance for safe proposals

| Gate | Conservative change | Aggressive change | Do not exceed |
|------|-------------------|-------------------|--------------|
| `rsi_buy_ceil` | 70 → 74 | 70 → 77 | 80 (RSI≥80 = genuine reversal risk) |
| `rsi_sell_floor` | 30 → 26 | 30 → 22 | 18 (RSI≤18 = deep oversold, SL risk) |
| `min_body_ratio` | 0.40 → 0.30 | 0.40 → 0.25 | 0.15 (too noisy below this) |
| `min_directional_bars` | 2 → 1 | 2 → 1 | 0 (removing entirely defeats the filter) |
| `require_bb_expansion` | leave 1 | set to 0 | — |

---

---

## FORGE EA CODE STANDARDS (apply when modifying ea/FORGE.mq5)

Every function block, gate, and structural change must follow this standard.

### BUILD-BEFORE-COMMIT RULE (mandatory)

**After every change to `ea/FORGE.mq5`, you MUST run `make forge-compile` before staging or committing.**

The compile step:
1. Stamps the current `VERSION` file into `FORGE.mq5` (so the `forge_version` column in TESTER_RUNS matches the source)
2. Runs the MQL5 compiler — catches syntax errors and MQL-specific rules (e.g. static-inside-if-block) that aren't visible from reading the source
3. Syncs the compiled `.ex5` into the MT5 Experts directory and `scalper_config.json` into Common Files
4. Confirms the build is newer than the source

If you commit without compiling and the build is broken, the EA in MT5 will silently keep running the previous `.ex5` (with the old `forge_version`). Subsequent backtests will look "wrong" and waste a debugging cycle.

**Sequence for every change**:
```bash
# 1. Edit ea/FORGE.mq5
# 2. (optionally) bump VERSION
echo "X.Y.Z" > VERSION
# 3. Compile + sync (REQUIRED before commit)
make forge-compile
# 4. Stage and commit
git add ea/FORGE.mq5 VERSION config/scalper_config.json
git commit -m "..."
```

If `make forge-compile` reports errors, FIX THEM before committing. Do not commit a broken FORGE.mq5.



### Function header comment block

```mql5
// ─────────────────────────────────────────────────────────────────────────────
// FunctionName — short one-line description
//
// PURPOSE: What problem does this function solve?
//
// EVALUATION ORDER (if the function has sequential gates):
//   1. First check  — why it comes first
//   2. Second check — dependency or cost reason
//   ...
//
// PARAMETERS:
//   param1  — what it is, units, valid range
//   param2  — ...
//
// RETURNS / SIDE EFFECTS: what the caller should expect
//
// CHANGELOG:
//   YYYY-MM-DD  Author description of change (Run N context if applicable)
// ─────────────────────────────────────────────────────────────────────────────
```

### Inline comment rules

- **Every gate block gets a one-liner** explaining WHAT it checks and WHY it fires early
- **Explain the config key** that controls it so it's findable from the code
- **Explain the logging consequence** if the gate logs RSI=0 or other placeholder values
- **No orphan numbers** — `0.95`, `4.34`, `25.0` must have comments explaining what they mean

```mql5
// 2+3. Body ratio & directional alignment
//   Body: avg(bar_body/bar_range) over N bars — filters doji/wick candles (min_body_ratio)
//   Direction: count bars where close agrees with trade dir — filters indecision (min_directional_bars)
//   OHLC-only: safe to run before indicator computation
```

### Changelog entry format

Every code change must add an entry to the relevant function's CHANGELOG block:
```
//   YYYY-MM-DD  Description of change.
//               Why it was needed (data observation, run number, bug).
//               What it affects (gate precision, P&L, signal logging).
```

Example:
```
//   2026-05-10  Pass rsi, adx into CheckEntryQuality signature.
//               Previously logged RSI=0/ADX=0 for all direction/body SKIPs —
//               53% of signals were unanalysable in gate precision audit (Run 9).
```

### When to add a CHANGELOG entry

- Any change to gate logic, config key mapping, threshold, or function signature
- Any bug fix where data was incorrect or incomplete
- Any structural reorder of evaluation logic

---

## CHEAT SHEET EXPANSION

If you discover a table/column not in `FORGE_TESTER_JOURNAL_QUERIES.md`:
- Test your query, then append under `## Discovered Queries (auto-added by /forge-monitor)`
- If an existing query fails, append a working replacement under `## Query revisions (auto-added by /forge-monitor)`
- Never edit existing entries — append only

---

## ANALYSIS DOC TEMPLATE

```markdown
# FORGE Run <aurum_run_id> — Tester Analysis

**EA version**: FORGE vX.Y.Z  
**Symbol**: XAUUSD  
**Sim period**: YYYY-MM-DD → YYYY-MM-DD  
**Scalper mode**: DUAL  
**Balance**: $10,000  
**aurum_run_id**: N  
**wall_time**: NNNNNNNNNN  
**source_run_id**: N (TESTER_RUNS.id)

## Summary — FINAL
- Sim period: YYYY-MM-DD → YYYY-MM-DD
- Total signals: N
- TAKEN: N signals (N actual groups incl. limit fills)  |  Skipped: N
- Total P&L: $N.NN
- Win rate: N% (W wins / L losses)
- Best win: $N.NN
- Avg profit event: $N.NN
- Athena cross-check: ✓/✗ gate counts match, performance.total_pnl=$N.NN confirmed

## TAKEN Groups
| Sim Time (UTC) | Group | Direction | Session | RSI | ADX | ATR | Price | TP reached | P&L |
|----------------|-------|-----------|---------|-----|-----|-----|-------|-----------|-----|

## Gate Breakdown (final, all SKIP reasons)
| Gate Reason | Count | Human Label |
|-------------|-------|-------------|

## Recommended Parameter Changes — More Trades
**Context**: N signals evaluated, N TAKEN (X% take rate).

### Current blocking gates → parameters
| Gate | Hits | Config key | Current | Proposed |
|------|------|------------|---------|---------|

### Change 1 — `<key>`: current → proposed
**Impact**: ...
**Risk**: ...

### Apply order
1. ...

> Changes go via `.env` or config template → `make scalper-env-sync && make forge-compile`

## SELL STOP CONT / BUY LIMIT Events
| Event | Group | Slot | RSI | Price | Result |
|-------|-------|------|-----|-------|--------|

## Losses — Price Movement Analysis
| Deal | Magic | Profit | Entry | TP1 | SL | Max favor pts | % TP1 | Pattern |
|------|-------|--------|-------|-----|-----|---------------|-------|---------|

### Per-loss narrative
For each loss, document:
- Price trajectory (key bar-close prices between entry and SL hit)
- Max favorable pts reached and % of TP1 achieved
- Pattern: SL-hunt / Held-too-long / Intrabar-only / Trend-failure / Overnight-hold

**Loss pattern taxonomy:**
| Pattern | Signature | Fix |
|---|---|---|
| SL-hunt | Stopped on brief spike, move resumed in favor | SL too tight — widen or disable cascade |
| Held-too-long | Was past TP1 (>100%) but no TP triggered, slow reversal | TP too far — tighten continuation TP |
| Intrabar-only | Favorable intrabar but bar-close never crossed TP1 | `tp1_atr_mult` too large — lower to 0.4× |
| Trend-failure | Peaked at <25% of TP1, reversed immediately | Wrong regime — gate (adx_max, bounce_lot_factor) |
| Overnight-hold | Massively in profit, held past expiry, reversed next day | Expiry_bars not enforced — investigate |

## Observations & Anomalies

## Recommendations & Open Issues
<!-- Append every Recommendation here per the RECOMMENDATIONS PATTERN section in SKILL.md.
     Each entry needs: Issue title → Evidence → Root cause (file:line) → Industry pattern
     (with WebSearch citation) → Options A/B/C with pseudocode → Preferred → Backward-compat flag. -->

## Operator Q&A Log
<!-- Append every operator question encountered during monitoring per the OPERATOR Q&A LOG
     section in SKILL.md. Each entry: Q# (sim time): question → Investigation → Evidence →
     Answer → Forward link to Recommendations. -->

## Session Log
```

---

## GATE LEGEND QUICK REFERENCE

Full 34-gate legend: `config/gate_legend.json` | API: `GET http://localhost:7842/api/gate_legend`

Common tester gates:

| gate_reason | Meaning |
|-------------|---------|
| `entry_quality_direction` | Not enough M5 bars moving in trade direction (need 2+) |
| `entry_quality_body` | Candle body too small — indecision candle |
| `entry_quality_rsi_sell_floor` | RSI below sell floor (oversold, default 33) |
| `entry_quality_rsi_sell_adx_floor` | Stricter RSI floor when ADX is weak |
| `entry_quality_adx_min_sell` | ADX too low for breakout sell (default 20) |
| `entry_quality_bb_contraction` | BB squeezing — no momentum |
| `entry_quality_atr` | ATR too low — market too quiet |
| `entry_quality_atr_ext` | Post-setup ATR too small for viable trade |
| `open_groups` | Max concurrent groups reached (default 2) |
| `rr_too_low` | Risk:Reward below minimum (default 1.5×) |
| `no_setup` | Neither BB Breakout nor BB Bounce conditions met |
| `session_off` | Outside London/NY session |
| `warmup_tester_m5_rollovers` | M5 indicator buffers not ready at backtest start |
