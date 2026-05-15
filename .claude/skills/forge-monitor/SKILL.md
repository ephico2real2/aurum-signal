---
name: forge-monitor
description: Monitor an MT5/MQL5 FORGE EA backtest by polling the source tester journal DB every 45s. ALL monitoring queries run against the source DB (SIGNALS/TRADES/TESTER_RUNS) written directly by FORGE EA — NEVER aurum_tester.db which lags by 60s+. Reports new signals, skips, taken trades, gate deltas, and SELL STOP continuation / BUY LIMIT recovery arming. Writes a per-run analysis doc and keeps the query cheat sheet current. Invoke when the user asks to "monitor the forge tester", "watch the backtest", "tail the journal", "monitor", "now monitor", or "/forge-monitor".
---

# /forge-monitor — FORGE tester journal monitor

You are debugging an MT5/MQL5 backtesting session. Be skeptical — flag suspicious
patterns rather than reporting them as normal: atr=0, identical prices, P&L moving
without trade count changing, unknown gate_reason values, all-skip runs, cascade
magics firing unexpectedly.

## Service operations during monitoring — ALWAYS use Makefile targets

The project root has a comprehensive `Makefile` (`/Users/olasumbo/signal_system/Makefile`).
If during monitoring you need to restart, reload, recompile, or sync anything,
**check `make help` first** — there's almost certainly a target. Never use raw
`kill <pid>` / `launchctl unload-load` / `pkill` — they break because
`KeepAlive.Crashed=true` doesn't respawn on clean SIGTERM. The Makefile targets
encode the correct unload/load sequence + post-restart health probe.

Common targets you'll need during a monitoring session:

| Action | Target |
|---|---|
| Reload ATHENA after API change | `make reload-athena` |
| Reload BRIDGE | `make reload-bridge` |
| Reload all Python services | `make reload` |
| Full restart (re-render plists) | `make restart` |
| Compile FORGE.mq5 → .ex5 | `make forge-compile` (operator may need F7 in MetaEditor on macOS Wine) |
| forge-compile + open MT5 | `make forge-refresh` |
| forge-compile + restart MT5 + verify | `make forge-reload` |
| Verify FORGE is live (poll market_data.json) | `make forge-verify-live` |
| Regenerate scalper_config.json from defaults + .env | `make scalper-env-sync` |
| Live tail ATHENA log | `make logs-athena` |
| FORGE SKIP rollup last 24h | `make monitor-forge-skips` |
| List all run_ids | `make journal-list` |
| Purge a specific run | `make journal-reset-run RUN=N` |

Full reference is in project root `CLAUDE.md` under "Service operations — ALWAYS
use Makefile targets" + `make help` for the complete 698-line listing.

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

## PEMCG ARCHITECTURE REFERENCE (mandatory — single source of truth)

**`docs/FORGE_PEMCG_ARCHITECTURE.md`** is the canonical reference for the PEMCG composite + its three layer consumers (UMCG / CVCSM / Layer-3 BB_EXHAUSTION_REVERSAL) + the two side gates (v2.7.93/94). Read it FIRST when:
- Investigating any `pemcg_*_reversal_block`, `cvcsm_cooldown_block_*`, `bb_breakout_*_band`, or `bb_exhaustion_reversal_*` gate
- Designing a new atom, a new layer consumer, or modifying any of the 7 PEMCG atoms
- Answering operator questions about how the gates relate to each other (see §6 of that doc for the verbatim canonical Q&A from 2026-05-14)
- Writing run analysis docs — cite `FORGE_PEMCG_ARCHITECTURE.md` §3/§5 for the gate stack

**MUST update FORGE_PEMCG_ARCHITECTURE.md when**:
1. A PEMCG atom changes (logic, threshold, added, removed) → update §2.1 + §11 changelog
2. A new layer/consumer of `g_pemcg_*_warning_count` ships → update §3 + ASCII diagram §5
3. CVCSM state machine logic changes → update §3.2 + §5b state diagram
4. Layer 3 (BB_EXHAUSTION_REVERSAL) conditions change → update §3.3 + §5 single-tick flow
5. A side gate gains/loses PEMCG dependency → move between §3 and §4
6. Any vN ship touches PEMCG/UMCG/CVCSM/Layer-3 → §11 changelog one-liner
7. Live evidence (§7) — refresh whenever forge-monitor tick shows counts moving >500

**MUST also report in EVERY forge-monitor tick** the running counts of:
- `pemcg_buy_reversal_block`, `pemcg_sell_reversal_block` (Layer 1 activity)
- `cvcsm_cooldown_block_buy`, `cvcsm_cooldown_block_sell` (Layer 2 activity — flag transitions when ≥1 fires)
- `bb_breakout_buy_below_band`, `bb_breakout_sell_above_band` (v2.7.93 side gate)
- TAKEN count of `BB_EXHAUSTION_REVERSAL_SELL`, `BB_EXHAUSTION_REVERSAL_BUY` (Layer 3 actual fires)

If any of these counts jumped meaningfully since the prior tick, surface it in the tick summary.

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

### MANDATORY: Inflection-Point Audit for every TAKEN BUY at RSI ≥ 70 (and SELL at RSI ≤ 30)

**Operator mandate** (2026-05-13, post-G5006 -$1,760 loss): every new trade must validate market condition BEFORE the setup fires. No setup is allowed to bypass this universal pre-check. The G5006 case showed three existing atoms (`m5_strong_bar`, `m5_body_pct`, `m5_range_expanding`) **perfectly differentiated winner from loser** — but no gate enforced them.

**When this audit fires**: any TAKEN signal where `direction='BUY' AND rsi ≥ 70` (BUY at exhaustion territory) OR `direction='SELL' AND rsi ≤ 30` (SELL into oversold). These are the inflection-point traps.

**Audit query** (run mid-tick on every TAKEN that matches the trigger):

```python
import sqlite3
DB = "<active source DB>"
conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
# Find every BUY at RSI >= 70 (or SELL at RSI <= 30) in this run
cur = conn.execute("""
    SELECT id, datetime(time,'unixepoch') as t, setup_type, direction, ROUND(price,2),
           ROUND(rsi,1), ROUND(adx,1), ROUND(macd_histogram,3),
           ROUND(bb_upper,2), ROUND(vwap_price,2),
           m5_strong_bar, m5_range_expanding, ROUND(m5_body_pct,3),
           long_upper_wick, long_lower_wick, m5_doji
    FROM SIGNALS WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
    AND outcome='TAKEN'
    AND ((direction='BUY' AND rsi >= 70) OR (direction='SELL' AND rsi <= 30))
    ORDER BY time DESC LIMIT 20
""")
for r in cur.fetchall():
    sid, t, setup, dirn, px, rsi, adx, macd, bbu, vwap, strong, range_exp, body, uwick, lwick, doji = r
    # 7-atom reversal-warning composite (matches v2.7.84 PEMCG design)
    if dirn == 'BUY':
        bbu_dist_atr = (px - bbu) / r[6] if r[6] else 0  # would need atr — fetch above
        warnings = sum([
            rsi >= 70,
            (body or 0) < 0.5,
            (strong or 0) == 0,
            (range_exp or 0) == 0,
            bbu_dist_atr < 0.3,
            macd < 0,  # already negative at the top
            (uwick or 0) == 1,  # long upper wick = rejection
        ])
        verdict = "⚠ REVERSAL TRAP" if warnings >= 3 else "✓ continuation"
        print(f"  {t}  {setup} {dirn} @{px}  RSI={rsi} ADX={adx} MACD={macd}  warnings={warnings}/7  {verdict}")
```

**What to report**: for every TAKEN BUY at RSI≥70 (or SELL at RSI≤30), report the 7-atom warning count. If ≥3 → flag as **REVERSAL TRAP** and recommend the PEMCG composite (v2.7.84) to operator.

**Why this matters**: this is the highest-loss pattern in FORGE history (G5005 -$1,694 Run 30, G5005 -$2,934 Run 32, G5006 -$1,760 Run 35). All three were BB_BREAKOUT BUYs at RSI ≥73 with weak m5 candles. The atoms existed to catch them; no gate enforced them.

**Anti-pattern**: writing "G5006 had RSI 73 so it was overbought" — RSI alone is not the differentiator (G5005 also had RSI 73 and WON). Always use the boolean composite (multi-atom) to differentiate winner from loser. RSI is necessary but not sufficient.

**The 3 bar-quality atoms catch reversal traps EVEN WHEN RSI is not overbought**:
- G5015 (22:37 Apr 1, MOMENTUM_DUMP BUY @4773): RSI 59 (not overbought), but `m5_strong_bar=0`, `m5_body_pct=0.26`, `m5_range_expanding=0` → 5/6 PEMCG warnings → was a trap that lost -$564. RSI-only audit would have MISSED this. Bar-quality audit catches it.

So the audit query trigger expands beyond `rsi >= 70`:

**Audit triggers** (any of these makes a TAKEN BUY suspect — run the 7-atom composite on each):
1. RSI ≥ 70 (classic overbought)
2. `m5_strong_bar == 0` AND `m5_body_pct < 0.5` (weak-bar entry — most reliable single condition)
3. Direction = BUY AND `bb_upper - close < 0.3×ATR` (entering at/below BB upper with no breakout)
4. Direction = BUY AND `vwap_dist_atr > 2.0` (overextended from mean)

For SELL: mirror conditions (RSI ≤ 30, weak bar with body < 0.5, bb_lower distance, vwap_dist negative).

**Cross-reference**: `docs/FORGE_CASE_STUDY_G5006_INFLECTION_POINT.md` is the canonical analysis. Cite it from every run analysis that surfaces a similar trap.

---

### MANDATORY: Missed-Opportunity Post-Mortem (per-run end-of-monitoring)

**Operator mandate** (2026-05-14): every monitoring session that runs to stop condition must audit for **missed opportunities** — sessions / days where FORGE took ≤ 1 trade despite a 40+ pip range or directional move. The audit is the symmetric complement to the loss-based post-mortem: losses are about what we SHOULDN'T have entered, misses are about what we SHOULD HAVE.

**When this audit fires**: at stop condition, for every calendar day (UTC) in the simulated period. Run it ALONGSIDE the loss post-mortem — both write to the per-run analysis doc.

**Threshold for declaring a "miss"** (anti-pattern guards):
- Day range ≥ 40 pts (~$4 XAUUSD swing) AND FORGE took ≤ 1 trade that day, OR
- Any single session window (Asian / London / NY-AM / LC+NY-PM) had ≥ 40 pt move AND FORGE took 0 trades during it.
- **Sub-40-pt moves are NOT misses** — they don't justify a new composite (`docs/missed_opportunities/INDEX.md` anti-pattern flag #1).
- Days with zero SIGNALS rows = tester didn't run (broker holiday, weekend). NOT a miss — document the gap and skip.

**Run agnosticism rule**: A "miss" is defined against the LATEST EA version's gates (the run being monitored). Earlier-version captures on the same day are NOT misses *unless* they would have been confirmed winners (positive net P&L after SL/TP) — coincidental survival doesn't justify a regression flag.

**Audit query** (template — adapt run_id to the active run):

```sql
-- Q-MO1: Day-level summary
WITH day_data AS (
  SELECT date(time,'unixepoch') AS day, run_id,
         MIN(m5_low_0) AS lo, MAX(m5_high_0) AS hi,
         SUM(CASE WHEN outcome='TAKEN' THEN 1 ELSE 0 END) AS taken
  FROM SIGNALS WHERE run_id = <ACTIVE> AND m5_high_0 > 0
  GROUP BY day
)
SELECT day, printf('%.1f',(hi-lo)) AS range_pts, taken,
       CASE WHEN (hi-lo) >= 40 AND taken <= 1 THEN 'MISS_CANDIDATE' ELSE 'ok' END AS verdict
FROM day_data ORDER BY day;

-- Q-MO2: Per-session breakdown
WITH base AS (
  SELECT date(time,'unixepoch') AS day,
    CASE
      WHEN CAST(strftime('%H',time,'unixepoch') AS INT) BETWEEN 0 AND 6 THEN 'asian'
      WHEN CAST(strftime('%H',time,'unixepoch') AS INT) BETWEEN 7 AND 12 THEN 'london'
      WHEN CAST(strftime('%H',time,'unixepoch') AS INT) BETWEEN 13 AND 15 THEN 'ny_am'
      WHEN CAST(strftime('%H',time,'unixepoch') AS INT) BETWEEN 16 AND 20 THEN 'lc_ny_pm'
      ELSE 'after_hours' END AS sess,
    m5_high_0, m5_low_0, outcome
  FROM SIGNALS WHERE run_id = <ACTIVE> AND m5_high_0 > 0
)
SELECT day, sess,
       printf('%.1f',(MAX(m5_high_0)-MIN(m5_low_0))) AS pips,
       SUM(CASE WHEN outcome='TAKEN' THEN 1 ELSE 0 END) AS taken
FROM base GROUP BY day, sess ORDER BY day, sess;
```

**Output location**: `docs/<month>/<period>.md` per the schema in `docs/april/2026-03-31_to_2026-04-02.md` (the canonical template). For each period:
- File path follows `docs/<month-name-lowercase>/YYYY-MM-DD_to_YYYY-MM-DD.md`.
- Period boundaries chosen for logical date clusters (Mon-Wed, weekend-bracketed, etc.), NOT arbitrary fixed-length windows.

**Index update** (mandatory): every new period doc adds a row to `docs/missed_opportunities/INDEX.md` with:
- Period doc link
- Date range
- Miss count
- Composites proposed (names + brief)
- Status (REVIEW / PHASE_1 / PHASE_2 / PHASE_3 / ARCHIVED)
- Last-updated date

**Per-period doc structure** (8 mandatory sections):
1. **§1 Day-by-day market action summary** — OHLC table + per-session range matrix + verdict per day
2. **§2 Per-missed-opportunity reconstruction** — one subsection per miss with indicator snapshot at would-be entry, gate(s) that blocked, inverse-composite candidate
3. **§3 Day-type classification** — chop / trend / chop-in-bull / reversal / news-impulse matrix
4. **§4 Industry research findings** — Pattern A/B/C... with verbatim quotes + URLs (per the WebSearch MANDATORY directive)
5. **§5 Proposed composites** — 1-3 composites per period, PEMCG-style with 6-8 atoms, threshold, truth table replay against misses AND known losers (G5006, G5048, Apr-8-04:10-knife-catch must SKIP)
6. **§6 Validation plan** — Phase 1 shadow-log → Phase 2 live-capped → Phase 3 full deploy, with refute conditions
7. **§7 Verification queries** — every numeric claim has a Q# SQL (atlas §13 mirrored)
8. **§8 References** + **§9 Changelog (append-only)**

**Composite proposal rule** (enforced):
- Follow `docs/FORGE_PEMCG_ARCHITECTURE.md` 7-atom warning composite pattern (6-8 atoms typical)
- Threshold ≥ supermajority (≥ 0.7 × atom count) per memory `feedback_supermajority_composite_threshold.md`
- Truth table MUST include known losers (G5006-class BB_BREAKOUT retest, G5048-class against-market) and verify they SKIP
- Ship behind default-OFF flag: `FORGE_SETUP_<NAME>_ENABLED=0`
- Gate code naming per `FORGE_NAMING_CONVENTIONS.md §4.7`: `<composite_name>_<gate_concept>_<direction?>`
- Operator-rule compliance check: for SELL composites in chop, verify `feedback_xauusd_chop_retraces_up.md` (gold chops bounce UP — extra-narrow SELL filters required)

**Cross-reference (mandatory)**: every per-run analysis doc must end with a `## Missed-Opportunity Hook` subsection citing:
1. The period doc(s) covering the run's date range
2. Which proposed composites would have captured trades in this run (if any)
3. Any new misses identified that should append a new period doc OR extend an existing one

**Anti-patterns**:
- Classifying a 30-pip move as a "miss" — threshold is 40+ pts.
- Proposing a composite without a truth-table replay against G5006/G5048 known losers — they MUST SKIP.
- Skipping WebSearch industry validation — every composite needs ≥ 2 canonical-pattern citations (per the WebSearch MANDATORY directive below).
- Treating EA-version regressions as misses when they're correct anti-loss tightening (Run 9 v2.7.94 anti-retest BB_BREAKOUT gate correctly blocks G5006-class — that's PROGRESS, not a miss).

**Cross-references**:
- `docs/missed_opportunities/INDEX.md` — the index
- `docs/april/2026-03-31_to_2026-04-02.md` — canonical example (Period 1, 5 misses → 3 composites)
- `docs/april/2026-04-06_to_2026-04-08.md` — Period 2 (4 misses → 2 NEW + 2 reused composites)
- `docs/FORGE_CASE_STUDY_2026_03_31_to_04_08.md` — precursor case study with V2/V3 atom extensions

---

### MANDATORY: FORGE Core Logic Design Tracker — continuous-update mandate

**Operator mandate** (2026-05-14): "create a document tracking this forge ea discussion that must be kept up to date ... update skill for continuous update". The earlier multi-leg cool-period review (`docs/response-core-logic-design.md`) addressed the wrong architectural paradigm; the corrected design is tracked in `docs/FORGE_CORE_LOGIC_DESIGN.md` as a series of "Sets" (Set 1 through Set N), each documenting one gap between operator-described intent and FORGE code.

**When this mandate fires**: any monitoring session, refactor, or analysis that touches ANY of:
- Multi-leg entry / cascade / pyramid logic (`ArmPostTP1Ladder` and callers)
- TP1/TP2/TP3 tier semantics (`ManageOpenGroups` TP-tier paths, `tp1_close_pct`, `tp2_close_pct`)
- Cool-period / pending-order lifecycle (`sell_stop_cont_*`, `buy_stop_cont_*`, `*_recovery_*`, `CancelPendingOnDailyFlip`)
- Direction-lock state machine (any new state struct or flag)
- SL trail across positions (`move_be_on_tp1`, cushion, ratchet)

**Required reads at session start**:
1. Read `docs/FORGE_CORE_LOGIC_DESIGN.md` §1 (operator verbatim intent) and §3 (mismatch summary) — internalize current alignment status.
2. Skim §4 Sets relevant to the session's focus.
3. Check §9 changelog tail — has the doc been updated more recently than the relevant `ea/FORGE.mq5` cite? If not, your code understanding may be stale.

**Required writes at session end**:
1. **If a Set's behavior was touched in code** — update that Set's Status line in `docs/FORGE_CORE_LOGIC_DESIGN.md` §4 + append a §9 entry (dated, with EA version + file:line cite).
2. **If operator clarified intent during the session** — update the relevant Set's "Operator intent" subsection + append §9.
3. **If a new gap was identified** — add as a new Set §4 subsection (do not renumber existing Sets) + append §9.
4. **If a Set is superseded** by a new approach — mark `Status: superseded by Set N` + cross-link in §9; do not delete the superseded Set.

**Cross-linking rule**: every per-run analysis doc (`docs/FORGE_RUN<N>_ANALYSIS.md`) that surfaces a multi-leg / cool-period / TP-tier / SL-trail anomaly MUST cross-link to the matching Set in this tracker. Format: `(see FORGE_CORE_LOGIC_DESIGN.md Set N)`.

**Anti-patterns to avoid**:
- Editing `ea/FORGE.mq5` cascade / cool-period code without consulting this tracker first.
- Writing prose updates in §4 bodies without logging in §9. Always log.
- Renumbering Sets when one is superseded. Mark `superseded` instead.
- Treating the v2.7.95 BUY-side cascade ship as the "fix" for the operator's described multi-leg system — it closed one asymmetry but is on the existing pending paradigm; Sets 1-10 are the real multi-leg redesign.

**Document path**: `/Users/olasumbo/signal_system/docs/FORGE_CORE_LOGIC_DESIGN.md`

---

### MANDATORY: Acronym discipline — every old + new acronym fully defined

**Operator mandate** (2026-05-14): "all old and newly created acronyms need to be well defined and sources cited and relationship defined etc"

Every acronym used in FORGE code, docs, gate-reasons, or operator-facing output MUST satisfy three rules:

1. **Defined** in `docs/FORGE_PEMCG_ARCHITECTURE.md §1A.1` (the acronym dictionary). Each entry must include:
   - Full expansion of every letter (e.g., **D**irection **L**ock **V**erdict — not just "DLV").
   - Type (computed integer / enum / boolean / state machine / etc).
   - Role in one sentence.
   - Origin attribution: operator-coined (with date + originating discussion) vs introduced-by-redesign (with version + session date + AI-assisted note where applicable).

2. **Sourced** when influenced by industry literature. The `§9 References` block of `FORGE_PEMCG_ARCHITECTURE.md` must include the cited article(s) with verbatim quote + URL. If you introduce an acronym based on a WebSearch finding, the source goes into §9 in the same edit that adds the acronym to §1A — never in a later commit.

3. **Related**: an acronym is never standalone — `§1A.3` (layer-fire sequence) and `§1A.4` (indicator → threshold → atom → count → verdict grouping) must show how this acronym slots into the existing system. Show:
   - What inputs it consumes (other acronyms / raw indicators).
   - What it outputs (boolean? verdict enum? state transition?).
   - Which other layer/acronym consumes its output.

**When this mandate fires**:
- ANY new gate code added to `config/gate_legend.json`.
- ANY new enum / state-machine / verdict type added to `ea/FORGE.mq5`.
- ANY new acronym surfaced in operator conversation (e.g., the operator coins a new term in a design discussion).
- ANY refactor that renames or supersedes an existing acronym.

**Anti-patterns**:
- Adding a new enum (e.g., `DLV_VALID`) to the EA without adding the acronym to `§1A.1` in the SAME commit.
- Citing "industry pattern" in a code comment without the corresponding URL in `§9 References`.
- Defining a new acronym without specifying what existing acronym(s) it relates to — orphan acronyms are forbidden.

**Origin attribution convention** (FORGE acronyms to date):

| Acronym | Origin | When |
|---|---|---|
| PEMCG, UMCG, CVCSM | operator-coined | v2.7.84, 2026-05-13 |
| DLV, DLS | introduced this session, AI-assisted, operator-approved | v2.7.97, 2026-05-14 |

Any FUTURE acronyms must follow this attribution pattern.

**Document path for the dictionary**: `/Users/olasumbo/signal_system/docs/FORGE_PEMCG_ARCHITECTURE.md §1A`

---

### MANDATORY: Trade-flow analysis standard + living doc

**Operator mandate** (2026-05-14): "when I asked questions about how a trade flow, I expect analysis similar to docs/FORGE_TRADE_FLOW_BUY_SELL.md — well breakdown and also this must be updated as I improved the system with comments below on why it was updated etc"

When the operator asks ANY question about how trades flow / fire / progress / exit, the response must match the depth and structure of `docs/FORGE_TRADE_FLOW_BUY_SELL.md`:

**Required structure for trade-flow answers**:

1. **Direct answer to the framing question** (1-2 sentences). Don't bury the verdict.
2. **Execution-model table** — Order class × When placed × Order type × Fills when. Clarifies whether the operator's question involves market orders, pendings, or both.
3. **ASCII lifecycle diagram** for the asked direction (BUY or SELL). Must include:
   - Timeline markers (T=0, T+N, T+M, T+P, T+Q).
   - All gate chain stops (UMCG / CVCSM / DirLock) with file:line cites.
   - Per-leg execution (PlaceMarketBatch when batch_size > 1).
   - Parallel M5-close re-evaluator thread.
   - TP1 close + cascade arm + arm-time gates.
   - TP2 banking close + SL ratchet.
   - TP3 dynamic extension (when tp3_mode=1).
   - DISCARDED → IDLE flow with bilateral cooldown.
4. **Mirror analysis** for the OPPOSITE direction — never answer for only one direction. Either inline a second ASCII block OR include the side-by-side BUY/SELL mirror table from `FORGE_TRADE_FLOW_BUY_SELL.md §3`.
5. **Activation state callout** — list the relevant `.env` knobs and their current values (read from `config/scalper_config.json`). Make clear what's ON vs OFF.
6. **Code line cites** — every claim about EA behavior must include `ea/FORGE.mq5:<line>` cite.

**Anti-patterns**:
- Answering only one direction (e.g., explaining BUY without the SELL mirror).
- Vague prose without ASCII lifecycle.
- "It depends" answers without the file:line cite that explains the dependency.
- Skipping the activation-state callout when knobs may be OFF.

### Living doc requirement

`docs/FORGE_TRADE_FLOW_BUY_SELL.md` is a **living document**. It MUST be updated when:

- Any new gate is added that fires during entry decision (changes the ASCII chain).
- Any new state machine transition is introduced (e.g., new DLS state).
- Any new cascade slot or recovery slot is added.
- Any TP-tier semantic changes (close %, pip floor, dynamic mode).
- A new setup type ships (must be reachable through the same chain — confirm it is).
- A new acronym appears in the chain (see Acronym Discipline mandate above).
- Default-OFF behavior of any §5 activation knob changes.

Each update MUST include in `§8 Changelog`:
- Date
- What changed in the flow
- **Why it was updated** (the operator change / new ship / data observation that motivated it)
- Forward link to the corresponding `FORGE_CORE_LOGIC_DESIGN.md §9` entry if part of a numbered Set.
- Forward link to the version commit (vX.Y.Z) that delivered the change.

**Anti-pattern**: editing the §1 BUY flow or §2 SELL flow without adding the matching §3 mirror-table update + §8 changelog entry. Asymmetric updates leave the doc internally inconsistent.

**Cross-reference rule**: every per-Set update in `FORGE_CORE_LOGIC_DESIGN.md` that touches entry chain / cascade / TP-tier / SL-trail MUST also trigger an update to `FORGE_TRADE_FLOW_BUY_SELL.md`. Reciprocal: every change to the flow doc must reference the originating tracker Set.

**Document path**: `/Users/olasumbo/signal_system/docs/FORGE_TRADE_FLOW_BUY_SELL.md`

---

### MANDATORY: WebSearch industry validation BEFORE proposing any composite, atom, or gate

**Operator mandate** (2026-05-13): "I also need you to a google search on any plan you wanna do to make sure that it conforms with Gold and taking advantage."

Before proposing ANY new composite / atom / gate / setup / parameter change, you MUST run WebSearch to validate against canonical XAUUSD scalping / MT5 EA / technical-analysis literature. This is on top of the existing Industry-research requirement in the RECOMMENDATIONS PATTERN section — it now applies to ALL composite work, not just recommendations.

**Search queries to run** (pick the most relevant per proposal):

| Proposal type | Suggested queries |
|---|---|
| Reversal/exhaustion gate | "Bollinger Band upper exhaustion reversal MACD divergence weak candle composite filter MQL5 <current year>" |
| Cooldown logic | "scalping post-trade cooldown re-entry same direction filter prevent overtrading MQL5 EA best practice" |
| Pre-fill validation | "MT5 pending order pre-fill market condition validation cancel before fill MQL5" |
| Trend continuation | "MT5 EA trend continuation entry filter ADX RSI BB <current year>" |
| Killzone/session | "ICT killzone Asian London NY session XAUUSD intraday rules <current year>" |
| Setup naming | "XAUUSD gold scalping setup catalog breakout pullback reversal momentum" |

**What to capture from each search**:
1. Quote one canonical pattern (verbatim) with source URL
2. Note if proposal conforms or deviates — if deviation, justify why
3. Adapt to FORGE's specifics — do NOT copy-paste code that won't compile
4. If multiple sources disagree, document the disagreement + pick the more conservative path

**Anti-pattern**: writing "I think we should X" without ANY web search citation. The MT5/MQL5 community has worked on most scalping problems for 15+ years. If you can't find prior art, search harder — don't invent novel approaches when established ones exist.

**Where to log the citations**:
- Recommendations section of run analysis docs (per RECOMMENDATIONS PATTERN)
- Case study docs (§4 industry pattern subsection)
- Atlas §13 Command Log (if the search informed an atlas update)

The search is part of the proposal's evidence, not a separate workstream. A proposal without an industry-research citation is incomplete.

---

### MANDATORY: validate market condition at pending-order FILL time, not just placement

**Operator mandate** (2026-05-13, post-G5006 loss): "Our EA logic must check market price before allow on unfilled order in. Also we were selling and you just went to buy without data."

FORGE places three classes of orders:
1. **Market-immediate** (e.g. BB_BREAKOUT BUY @ market) — fills instantly; PEMCG check at placement suffices
2. **Pending SELL_STOP / BUY_LIMIT cascade** (placed N pts below/above market, fills when price hits trigger) — **TIME LAG between placement and fill**
3. **Pending limit-recovery / continuation orders** (e.g. SELL_STOP_CONTINUATION) — same as #2, larger window

For classes #2 and #3, the EA places the pending and walks away. By the time the broker fills it, the M5 atoms may have COMPLETELY FLIPPED. There is no re-validation at fill time. This is the architectural gap the operator wants closed.

**Industry pattern** (per WebSearch — to be verified):
> "Smart pending order management": EA monitors active pendings and CANCELS them when entry conditions break (regime flip, opposite-direction signal, time expiry, indicator inversion).

**How to audit** (run mid-monitoring, surface in every analysis doc):

```python
# Find all CASCADE FILLS (magic in {group_magic + 5001..5009}) that resulted in losses
# Compare their atom state at FILL time vs at the original PLACEMENT signal time.
# Atoms that flipped between placement and fill are the smoking gun for "no pre-fill check".

cur.execute("""
    SELECT t.time as fill_time, t.magic, t.profit, t.comment,
           (SELECT MIN(s.time) FROM SIGNALS s WHERE s.magic = t.magic AND s.outcome='TAKEN') as placement_time
    FROM TRADES t WHERE t.run_id=(SELECT MAX(id) FROM TESTER_RUNS)
    AND t.profit < 0
    AND t.magic > (SELECT magic_base FROM TESTER_RUNS ORDER BY id DESC LIMIT 1) + 5000
""")
# For each loss, query SIGNALS at fill_time to see if atoms had flipped
```

**Recommendation pattern** when this is found (per RECOMMENDATIONS PATTERN section):
- Title: "Pending order filled into reversed market — no pre-fill validation"
- Evidence: cite specific magic, placement time, fill time, atom flip
- Proposed gate: new `cancel_pending_on_atom_flip` background check that runs every M5 close and cancels any FORGE-owned pending where the PEMCG warning count crosses a threshold

This is queued as a **post-v2.7.84 enhancement** (call it v2.7.85+) — out of scope for the immediate PEMCG/post-TP-cooldown ship.

---

### MANDATORY: Canonical entry-gating design (UMCG + SL-only CVCSM with bidirectional retry)

**Operator mandate** (2026-05-13, final): "I like the state machine — because it would have been useful. It just have to have a logic that evaluate both sell and buy and retry."

The canonical FORGE entry-gating system has **three layers**, in this exact order, evaluated at every setup trigger:

#### Layer 1 — UMCG (Universal Market Condition Gate)

- 7-atom PEMCG_BUY composite + 7-atom PEMCG_SELL composite (mirror)
- Evaluated stateless at every BUY/SELL setup trigger
- BUY: SKIP if `pemcg_buy_warnings >= 3` (`gate_reason: pemcg_buy_reversal_block`)
- SELL: SKIP if `pemcg_sell_warnings >= 3` (`gate_reason: pemcg_sell_reversal_block`)
- **Bidirectional and independent** — BUY blocked doesn't block SELL
- Stateless, recomputed at every M5 close

#### Layer 2 — CVCSM (Smart SL-Triggered Cooldown with Bidirectional Retry)

- State per direction: `OPEN | COOLDOWN | RETRYING`
- Independent BUY/SELL state machines
- **Trigger entering COOLDOWN**: SL fired in that direction. **TP firing does NOT trigger cooldown.**
- **Retry logic**: every M5 close, re-evaluates PEMCG for both directions independently
- Release: PEMCG warnings < threshold for N consecutive M5 bars (default 2 = 10 min)
- Safety: hard timeout at max_cooldown_sec (default 1800s / 30 min)
- Opposite direction is NEVER blocked by same-direction cooldown

#### Layer 3 — Opposite-direction reversal capture

When PEMCG_BUY warnings ≥ 4 (high reversal-warning), a `BB_EXHAUSTION_REVERSAL_SELL` setup can fire. Mirror for SELL-side. This converts the very warnings that blocked BUYs into SELL triggers — captures the reversal move rather than just preventing the wrong-side entry.

**Why this specific design**:

| Concern | How the design addresses it |
|---|---|
| TP cooldown blocks legitimate continuation entries | TPs don't trigger cooldown — only SLs |
| Same-direction cooldown blocks legitimate opposite-direction reversal trades | Independent BUY/SELL state machines |
| Time-based cooldown blind to market state | Retry every M5 close — release when atoms confirm |
| Cooldown after loss permanently locks entries | Retry mechanism + N-clean-bars release |
| State machine adds complexity without value | Only triggers on SL, not TP — minimal state changes per session |
| Wrong-side entries leak through | UMCG gate at trigger time catches them even without cooldown |

**Anti-patterns** (rejected at review):
- ❌ TP-firing triggers cooldown
- ❌ Same-direction cooldown blocking opposite-direction entries
- ❌ Time-only release (must be atom-condition based, with timer as safety only)
- ❌ Per-setup cooldown timers (Layer 2 is UNIVERSAL across all 14 setups per direction)
- ❌ Cooldown without a retry mechanism

**Required pattern** when proposing new entry logic:
1. Specify which **layer** the proposal belongs to (UMCG composite, CVCSM trigger, or new reversal capture)
2. State all atoms feeding the composite (cite existing globals; mark new ones as **add**)
3. Provide threshold + N-bar release counts with justification
4. Replay on at least 2 known winners + 2 known losers — truth-table format
5. Document the mirror direction (every BUY composite ships with its SELL mirror, and vice versa)
6. Cite industry pattern + WebSearch source per the WebSearch mandate
7. State the gate_reason code that will be emitted (per FORGE_NAMING_CONVENTIONS.md §4.7)

**Reference design**: see `docs/FORGE_CASE_STUDY_G5006_INFLECTION_POINT.md` + v2.7.84 ship notes. The 7-atom PEMCG composite is the canonical market-condition signal.

---

### MANDATORY: Close-deal magic attribution audit (v2.7.104 bug class)

**Operator mandate** (2026-05-14, Run-on-v2.7.102): "i see Significant changes since prior tick — 9 new losses appeared" → after deeper investigation: 8 of those 9 were tagged at **base magic 202401 with empty comment**, which I initially mis-explained as "v2.7.84 PEMCG protective closes". That was wrong. Deeper trace revealed the actual mechanism: **EA-internal `g_trade.PositionClose()` calls that do not pre-set `CTrade::m_magic` to the position's group magic**. MT5's CTrade copies `m_magic` into the close request, so the resulting close deal inherits whatever magic was last set on the CTrade instance — which is `MagicNumber` (base) after the reset calls at lines 2515 / 2610 / etc. that fire after every entry. v2.7.104 fixes all 10 affected PositionClose call sites by setting the magic before each call and resetting after the loop.

**These ARE real losses** — they're not a defensive mechanism. The originating close path is one of:
- v2.7.54 time-stop for MOMENTUM_DUMP / BB_LOWER_REVERSION_BUY (`g_trade.PositionClose(_ts_tk)` at the dump_max_hold_seconds expiry)
- TP1 partial-close ratchet (closes `tp1_close_pct`% of group positions at TP1 touch)
- TP2 banking close (closes `tp2_close_pct`% of remaining at TP2 touch, v2.7.96)
- Conviction-decay partial close (v2.7.77 — `PositionClosePartial` at decay levels L1/L2/L3)
- BRIDGE `CLOSE_GROUP` / `CLOSE_GROUP_PCT` / `CLOSE_ALL` / `CLOSE_PCT` / `CLOSE_PROFITABLE` / `CLOSE_LOSING` commands

**The bug is in the EA, not in any "defensive mechanism"** — pre-v2.7.104, every internal close path mis-attributes the deal to base magic, breaking per-group P&L roll-ups and creating phantom "losses at magic 202401 with empty comment" that aren't tied to any group in the dashboard.

**Why this matters**: in a single tick a cluster of `profit < 0` deals at base magic with empty comments and round M5 timestamps will appear in W/L counts and dashboards as **losses**, but they are *defensive mechanism outputs*, not structural failures. Confusing the two distorts the operator's mental model of system health and pushes toward wrong fixes (e.g., "widen SL" when the actual issue is "protective threshold too aggressive at the wrong session").

**When this audit fires** (run on every tick that has new `profit < 0` deals):

For every loss deal in the current tick window:

```python
import sqlite3
conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
for r in conn.execute('''
    SELECT deal_ticket, magic, ROUND(profit,2), comment, datetime(time,'unixepoch'), volume, price
    FROM TRADES WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS) AND profit < 0
      AND deal_ticket > <last_seen_deal_ticket>
    ORDER BY time
'''):
    deal, magic, profit, comment, t, vol, price = r
    base_magic = MAGIC_BASE  # 202401 in current run
    # Classification
    if magic == base_magic and not comment:
        cls = "PROTECTIVE_CLOSE"          # v2.7.84 PEMCG / CVCSM partial exit
    elif comment.startswith('sl '):
        cls = "TRUE_SL"                   # broker SL hit
    elif comment.startswith('SCALP'):
        cls = "STAGED_PARTIAL"            # TP1/TP2 partial at loss (rare)
    elif magic >= base_magic + 20000:
        cls = "CASCADE_SLOT_SL"           # SELL_LIMIT_RECOV / BUY_STOP_CONT slot SL
    else:
        cls = "UNKNOWN_INVESTIGATE"       # flag for inspection
    print(f"  {cls:20s} deal={deal} magic={magic} profit={profit} vol={vol} t={t}")
```

**Reporting rule** in every tick + analysis doc:

| Category | What it is | Should be reported as |
|----------|------------|----------------------|
| `TRUE_SL` (comment `sl <price>`) | broker stop fired at SL price | **Loss** (real structural failure) |
| `CASCADE_SLOT_SL` (magic ≥ base+20000, comment `sl <price>`) | cascade/recovery slot SL | **Loss** (intentional small SL on recovery leg) |
| `EA_INTERNAL_CLOSE_MAGIC_BUG` (magic = base, empty comment) | v2.7.54 time-stop / TP1 ratchet / TP2 banking / conviction-decay / BRIDGE CLOSE_* — close-deal magic mis-tagged to base, real loss (fixed in v2.7.104+) | **Loss** — but **mis-attributed** to base magic; trace to originating group by timestamp + volume |
| `STAGED_PARTIAL` (comment starts `SCALP`) | TP-tier partial close at loss (rare) | Investigate — should always be 0 or positive |
| `UNKNOWN_INVESTIGATE` | doesn't match above patterns | Flag and grep the EA + bridge log |

**Tick report format** (correct framing, pre-v2.7.104):

> "+5 new TAKENs, **N losses total: 2 cascade-recovery SLs (-$X) + 8 EA-internal closes mis-tagged at base magic (-$Y, originate from G5011 time-stop expiry per timestamp+volume match)**. Pre-v2.7.104 the dashboard's W/L count and per-group P&L attribution are unreliable for any close that fires from one of the affected paths (time-stop, TP1/TP2 ratchet, conviction-decay, BRIDGE CLOSE_*)."

**Post-v2.7.104** (once the operator restarts the backtest with the new build):
> "+5 new TAKENs, N losses total broken down per-group correctly: G5011 time-stop -$X, G5012 time-stop -$Y, G5014 SELL_LIMIT_RECOV SL -$32. Per-magic P&L now reconciles cleanly."

**Cross-cluster trace** (pre-v2.7.104 mandatory; post-v2.7.104 only if per-group P&L still looks off):

Pre-v2.7.104 the base-magic close deals are real losses but TRACE TO THEIR ORIGINATING GROUP via:
1. **Timestamp match** — close deals at HH:MM:00 (M5-bar-close fire) trace to time-stop expiry. Compute `(close_time - earliest_open_time_in_window) / 60` and compare against `dump_max_hold_seconds / 60` (typically 20 min).
2. **Volume match** — sum of base-magic close volumes for the window vs sum of group-magic open volumes for the same window. Pre-v2.7.104, base-magic closes will exceed group-magic-attributed closes by the leakage volume.
3. **Direction match** — base-magic close `type=1` (SELL action) closes BUY positions, `type=0` (BUY action) closes SELL positions. Match against the originating group's direction.
4. **Closed-at-bottom check** — the close price vs the eventual recovery extreme. If close was within 2 ATR of the local bottom (BUY position bear-retrace) or local top (SELL position bull-retrace), flag as **"time-stop fired at the worst point — wider hold or session-aware threshold candidate"**.

Post-v2.7.104, the deal records carry the correct group magic so the trace is automatic via `WHERE magic = <group_magic>`.

**Session-aware threshold investigation** (operator-mandated 2026-05-14):

When you see a time-stop close cluster, ALWAYS check the SESSION column of the originating TAKEN signal AND the session at the close timestamps. If both are ASIAN, flag for review:

> "ASIAN-session time-stop closes on MOMENTUM_DUMP BUYs. Run 36 case: G5011/G5012 BUYs opened 22:39-22:40 ASIAN @ 4775; time-stops at 23:00/23:05/23:45 force-closed 0.56 lots cumulative at avg price 4763 (worst slice 0.13 × 2 = $430 at 23:45 price 4759, which was within 2pts of the local bottom 4757); price recovered to 4780 by 01:35 producing TP wins on the surviving partial positions. Net cluster: −$319. ASIAN-session `dump_max_hold_seconds` may need to be longer (e.g. 60min vs current 20min) because Asian chop drift naturally retraces deeper before recovering — current 20-min cap force-closes at the worst point of an otherwise-recovering position."

Hypothesis to test in a follow-up backtest (queue as Recommendation): **session-aware `dump_max_hold_seconds`** — current default ~20min for MOMENTUM_DUMP. ASIAN session (low-volume, deeper retraces) may warrant 60min; LONDON+NY (fast reversals) keep 20min. Knob: `FORGE_TIMING_DUMP_MAX_HOLD_SECONDS_ASIAN` (new) overrides default during `session == "ASIAN"`.

Industry citation framework (WebSearch mandate applies):
- Search: "MQL5 session-aware filter ASIAN London NY threshold scalping protective close"
- Search: "ICT killzone PEMCG threshold session differentiation XAUUSD <year>"
- Reference: ICT killzone literature already establishes ASIAN as the "accumulation/distribution" window with more chop and fewer true reversals — supports a more conservative protective-close threshold there.

**Anti-pattern**: reporting protective closes as SL hits without checking the comment + magic + timestamp signature. Always classify first, then report.

**Cross-reference**: this mandate originated from the Run 36 v2.7.102 monitoring session 2026-05-14 G5011-G5015 cluster analysis. The operator question that triggered it: "what is the current mode for forge - analyze the lost in Trades: 36 → 55 (+19); W/L: 35/1 → 45/10". The initial answer treated the 9 deals as SLs; intermediate analysis mis-explained them as "v2.7.84 PEMCG protective closes" (no such mechanism exists); the deep trace surfaced the actual root cause: `CTrade::PositionClose` mis-tagging close deals at base magic across 10 EA call sites. **v2.7.104 fixes all 10 call sites.**

---

### MANDATORY: PEMCG asymmetry audit on every monitoring tick + bear/bull-day intraday detection

**Operator mandate** (2026-05-14, Run 36 v2.7.102 monitoring): "PEMCG_SELL fired 63,716 times during a 140-pt bear move. ZERO SELL setups TAKEN... pemcg_BUY_block = 5,494 vs pemcg_SELL_block = 63,716 (12x ratio)."

**Insight that surfaced from this audit** (the headline lesson):
> **`h1_trend_strength` is a TRAILING indicator and CANNOT be used to detect fresh intraday reversals.** During the Apr-01→Apr-02 140-pt bear move, `h1_trend_strength` averaged +0.42 (still POSITIVE) across the 11,669 blocked-SELL sample. By the time the H1 EMA crosses negative, the move is hours old. **VWAP-distance + M15 ADX + H1 DI dominance are the correct intraday-bias triad** — they catch a regime shift within 1-2 M15 bars, not 1-2 H1 bars.

**When this audit fires** (mandatory every tick that includes a non-trivial PEMCG block window):

```python
import sqlite3
DB = "<active source DB>"
conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
# Pull the BUY vs SELL block ratio over the current monitoring window
row = conn.execute("""
  SELECT
    SUM(CASE WHEN gate_reason='pemcg_buy_reversal_block'  THEN 1 ELSE 0 END) AS buy_blocks,
    SUM(CASE WHEN gate_reason='pemcg_sell_reversal_block' THEN 1 ELSE 0 END) AS sell_blocks
  FROM SIGNALS
  WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
    AND outcome='SKIP'
    AND time >= strftime('%s', '<window start>')
    AND time <= strftime('%s', '<window end>')
""").fetchone()
buy, sell = row
ratio = max(buy, sell) / max(1, min(buy, sell))
direction = "SELL_HEAVY" if sell > buy else "BUY_HEAVY"
print(f"PEMCG block asymmetry: BUY={buy} SELL={sell} ratio={ratio:.1f}× ({direction})")
```

**Rule**: if **ratio ≥ 5× in either direction**, flag as **"PEMCG over-filtering candidate — check day-type"**. Then run the DAY-TYPE VERIFICATION query (below) to confirm whether the bias was structural or noise.

**DAY-TYPE VERIFICATION** (canonical query — pulls the intraday triad that v2.7.105 DTC uses):

```python
conn.execute("""
  SELECT
    ROUND(AVG((vwap_price - price) / atr), 2)   AS avg_below_vwap_atr,
    ROUND(AVG(m15_adx), 1)                       AS avg_m15_adx,
    ROUND(AVG(h1_trend), 2)                      AS avg_h1_trend,
    ROUND(AVG(rsi), 1)                           AS avg_rsi,
    ROUND(MIN(price), 2)                         AS min_px,
    ROUND(MAX(price), 2)                         AS max_px,
    COUNT(*)                                     AS sample_n
  FROM SIGNALS
  WHERE run_id=(SELECT MAX(id) FROM TESTER_RUNS)
    AND outcome='SKIP'
    AND gate_reason = '<the over-blocked gate>'  -- pemcg_sell_reversal_block in Run 36
    AND time BETWEEN strftime('%s','<start>') AND strftime('%s','<end>')
    AND atr > 0
""").fetchall()
```

**Interpretation table**:

| Indicator | "Yes, this is a confirmed bear day" thresholds | "Yes, this is a confirmed bull day" thresholds |
|---|---|---|
| avg_below_vwap_atr | ≥ +1.5 (price way below VWAP) | ≤ −1.5 (price way above VWAP) |
| avg_m15_adx | ≥ 25 | ≥ 25 |
| avg_h1_trend | usually still positive in fresh bear; **don't trust this signal** | usually still negative in fresh bull |
| avg_rsi | mid-range (40-55) suggests bear continuation not oversold reversal | mid-range (45-60) suggests bull continuation |
| sample_n | ≥ 1,000 in window | ≥ 1,000 in window |

**If 2 of 3 confirmation indicators (VWAP-dist, M15 ADX, h1_trend if relevant) point the same direction AND the over-blocked gate matches that direction** (e.g. bear day + pemcg_sell over-blocked), the v2.7.105 DTC modifier + day-bias-block stack is the structural fix.

**Reporting format** in tick + analysis doc:

> "PEMCG asymmetry: BUY=5,494 SELL=63,716 ratio=11.6× SELL_HEAVY in window 22:00 Apr-01 → 23:59 Apr-02. Day-type verification: avg VWAP-dist −4.18 ATR (bear-confirmed), M15 ADX 28.7 (trend-confirmed), h1_trend +0.42 (lagging — discard), RSI 47.1 (not oversold). **Confirmed bear day with PEMCG_SELL over-firing on direction-correct continuation entries**. v2.7.105 DTC (FORGE_COMPOSITE_DTC_*) is the structural fix; flip both `dtc_pemcg_modifier_enabled` and `dtc_day_bias_block_enabled` on next backtest restart."

**Anti-pattern**: reporting "63k SELL blocks during a bear move" as evidence of "PEMCG working as designed". The system is supposed to block reversal-trap SELLs at the bottom of bounces, not direction-correct continuation SELLs during a sustained bear. **Direction asymmetry + day-type confirmation = over-filter, not feature.**

**Cross-references**:
- v2.7.105 ship notes (this version): `docs/FORGE_PEMCG_ARCHITECTURE.md` §3.4 "Layer 4 — DTC"
- Gate codes: `bear_day_buy_block`, `bull_day_sell_block` in `config/gate_legend.json`
- Knob discovery: `.env.example` block under "v2.7.105 — Day-Type Classifier"
- Industry research (per WebSearch mandate, 2026-05-14):
  - [volity.io — RSI Indicator](https://www.volity.io/forex/rsi-indicator/) ("A high ADX reading confirms a strong trend, making RSI's overbought/oversold signals less reliable for reversals and more indicative of continuation.")
  - [mql5.com/blogs/post/767595 — VWAP for Trading Gold](https://www.mql5.com/en/blogs/post/767595) ("When the price is below VWAP, the market sentiment is bearish.")
  - [alchemymarkets — Hidden Bearish Divergence](https://alchemymarkets.com/education/strategies/hidden-bearish-divergence/) (continuation, not reversal)
  - [tradersunion — RSI Divergence](https://tradersunion.com/interesting-articles/rsi-indicator-strategies/rsi-divergence/) (regular vs hidden divergence semantics)

---

### MANDATORY: H4 trend agreement check on every counter-direction setup loss

**Operator mandate** (2026-05-14, Run 36 G5021 −$498.60 + G5026 −$399.00 audit): "you did not consider H4 in your analysis — why?" → root cause: v2.7.105 DTC used intraday triad only. **H4 trend is the ICT-canonical bias-setting timeframe** and must be checked separately from the intraday triad.

**Key insight surfaced**:
> **The intraday triad (VWAP + M15 ADX + H1 DI) alone cannot distinguish trend-continuation from corrective-retracement.** Both look "bear" or "bull" on intraday data. Only H4 agreement (or disagreement) lets the system classify a move as:
> - TREND_ALIGNED — H4 + intraday agree → full DTC behaviour (block opposite-direction, amplify same-direction)
> - COUNTER_TREND — H4 + intraday disagree → block KNIFE-CATCH entries in the intraday direction (G5021 case); allow OTE setups (deep retracement BUYs in bull H4 = G5016-class OTE pattern)
> - NEUTRAL — no triad agreement → pre-DTC behaviour

**When this mandate fires** (every loss review):

For EVERY loss group where the entry was direction-aligned-with-intraday-but-counter-H4:
1. Pull `h4_trend_strength` at entry time (from `g_eval_h4_trend` cached global)
2. Compare against intraday triad direction
3. If H4 disagrees → flag as **"counter-H4 knife-catch — v2.7.107 5-state DTC would block"**

**Canonical 5-state mapping**:

| Intraday triad | H4 trend | State name | What this catches |
|---|---|---|---|
| bull | ≥ +0.5 | `BULL_TREND_ALIGNED` | Normal bull day. Block SELLs (v2.7.105 `bull_day_sell_block`). |
| bear | ≤ −0.5 | `BEAR_TREND_ALIGNED` | Normal bear day. Block BUYs (v2.7.105 `bear_day_buy_block`). |
| bull | ≤ −0.5 | `COUNTER_TREND_BULL` | **Corrective bounce inside bear H4 — G5021 case.** Block BUYs via `counter_bull_day_buy_block` if `dtc_block_counter_trend_buys=1`. |
| bear | ≥ +0.5 | `COUNTER_TREND_BEAR` | Corrective dip inside bull H4 = **canonical OTE setup** at H4 demand. BUYs at deep oversold REMAIN ALLOWED. Block SELLs via `counter_bear_day_sell_block` if `dtc_block_counter_trend_sells=1`. |
| not confirmed | any | `NEUTRAL` | Pre-DTC behaviour (no day-type block). |

**Why counter-trend states DON'T trigger PEMCG modifier** (asymmetric design — operator-validated):
- TREND_ALIGNED: macro + intraday agree → trend-continuation entries are high-probability → de-weight PEMCG warnings (they'd be false alarms)
- COUNTER_TREND: macro disagrees with intraday → retracement is likely a temporary correction → PEMCG warnings should stay strict to filter the higher-failure-rate setups

**Reporting format** in tick + analysis doc:

> "Loss G5021 −$498.60: MOMENTUM_DUMP BUY @ 4697 with intraday VWAP_dist +1.60 (mildly bull) + M15 ADX 22.2 (below 25 threshold) + h4_trend likely ≤ −0.5 (clear bear macro after 4-day decline 4780→4630). State classification: **COUNTER_TREND_BULL**. v2.7.105 binary intraday DOES NOT catch (M15 ADX < 25). v2.7.107 5-state with `dtc_block_counter_trend_buys=1` blocks as `counter_bull_day_buy_block`. **Recommended fix: enable v2.7.107 5-state on next backtest restart.**"

**Anti-pattern**: classifying a loss as "trend-failure" without checking H4 alignment. The same setup can be:
- Trend-aligned and high-probability (BB_LOWER_REVERSION_BUY at H4 demand inside bull macro)
- Counter-trend and low-probability (same setup at the same RSI inside bear macro)

The intraday atoms look identical. H4 is the differentiator.

**ICT framework citation** (per [tradeciety multi-TF guide](https://tradeciety.com/multiple-time-frame-analysis)):
> "Trade only in direction of HTF bias unless confirmed MSS. Counter-bias trades at most fractional sizing. OTE re-entries at HTF premium/discount levels are the canonical setup."

The 5-state design is the direct implementation of this rule.

**Cross-references**:
- v2.7.107 ship notes: `docs/FORGE_PEMCG_ARCHITECTURE.md` §3.5
- Gate codes: `counter_bull_day_buy_block`, `counter_bear_day_sell_block`
- Knob discovery: `.env.example` block under "v2.7.107 — DTC 5-state"
- Industry citations:
  - [tradeciety — Multi-Timeframe Trading](https://tradeciety.com/multiple-time-frame-analysis)
  - [babypips — Multiple Time Frame Analysis](https://www.babypips.com/learn/forex/learn-multiple-time-frame-analysis)
  - [tradethepool — ICT MSS](https://tradethepool.com/technical-skill/ict-market-structure-shift/)

---

### MANDATORY: SL/ATR ratio audit on every loss + R:R matching on trend days

**Operator mandate** (2026-05-14, Run 36 Apr-06/07/08 loss audit): "SL too small on April 6, 7 and 8 — the TP was very small too. It was a bull run. We need to match both risk and reward that day. We need enough S/L to NOT get killed AS WELL AS good TP to win in the pull."

**Key insight from the data**: cascade entries placed using `entry_atr` (snapshot at original group entry) can be **mismatched to current volatility** when the cascade fires 20+ hours later. Worse: 1.5×ATR is correct for chop but **TOO TIGHT for trending days** where normal pullbacks routinely exceed 1.5×ATR.

**When this audit fires** (every loss group with SL hit):

```python
import sqlite3
DB = "<active source DB>"
conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
# For each loss, compute SL_distance / ATR_at_entry
losses = conn.execute("""
  SELECT t.deal_ticket, t.magic, t.price as close_px, t.comment,
         t.profit, datetime(t.time,'unixepoch') as t_close,
         s.price as entry_px, s.atr as entry_atr, s.setup_type, s.direction
  FROM TRADES t
  LEFT JOIN SIGNALS s ON s.magic = t.magic AND s.outcome='TAKEN'
  WHERE t.run_id=(SELECT MAX(id) FROM TESTER_RUNS)
    AND t.profit < 0
    AND t.comment LIKE 'sl %'
  ORDER BY t.time
""").fetchall()
for row in losses:
    deal, magic, close, comment, pnl, t_close, entry, atr, setup, dirn = row
    if entry and atr and atr > 0:
        # Parse SL price from comment "sl 4737.10"
        sl_price = float(comment.replace('sl ', '').strip())
        sl_dist = abs(sl_price - entry)
        sl_atr_ratio = sl_dist / atr
        verdict = "TOO TIGHT" if sl_atr_ratio < 1.5 else ("OK" if sl_atr_ratio < 2.5 else "CHOP-SIZED")
        print(f"  {magic} {setup} {dirn} entry={entry} sl={sl_price} dist={sl_dist:.1f}pt atr={atr:.2f} ratio={sl_atr_ratio:.2f}× {verdict}")
```

**Thresholds** (per [mql5.com/blogs/769205 SL strategies 2026](https://www.mql5.com/en/blogs/post/769205)):

| SL/ATR ratio | Day type fit | Action |
|---|---|---|
| < 1.0×ATR | None — guaranteed wick-out | **Always flag — structural flaw** |
| 1.0–1.5×ATR | Chop only | OK in NEUTRAL state; **TOO TIGHT** in TREND_ALIGNED state |
| 1.5–2.5×ATR | Mixed — depends on context | OK in NEUTRAL/COUNTER_TREND; **borderline** in TREND_ALIGNED |
| 2.5–3.0×ATR | **Trending day standard** (industry) | OK in TREND_ALIGNED |
| > 3.0×ATR | Excessive room — bad R:R | Flag if TP isn't also widened |

**R:R matching rule** (operator-mandated):
> "Enough S/L to NOT get killed AS WELL AS good TP to win in the pull."

If you widen the SL on trend days, you MUST also widen the TP proportionally — otherwise you accumulate small wins and full SL losses (negative-expectancy R:R drift). Always check BOTH:
- `tp_atr_mult ≥ sl_atr_mult × 0.6` (R:R = 1.67:1 minimum)
- `tp_atr_mult ≤ sl_atr_mult × 2.0` (R:R = 2:1 maximum — beyond that TP rarely hits)

**Reporting format**:

> "Loss G5024 cascade 5 legs −$2,456: entry 4756.18, SL 4737.10, distance 19.08pt, entry_atr 13.64, **ratio 1.40×ATR**. Below 1.5× threshold (chop SL on a trend day). DTC state at fire time: BULL_TREND_ALIGNED (intraday + H4 both bull). v2.7.108 fix with `dtc_geometry_widen_enabled=1` + `dtc_trend_aligned_sl_widen_factor=1.67` would have widened SL to 4736.18 (2.34×ATR → cascade survives the pullback) and `dtc_trend_aligned_tp_widen_factor=2.0` widens TP to capture the run to 4810+."

**Anti-pattern**: classifying a loss as "trend-failure" without checking SL/ATR ratio. If the SL fired at < 1.5×ATR during a trending day, it's an SL-geometry problem, not a setup problem.

**Cross-references**:
- v2.7.108 ship: `docs/FORGE_PEMCG_ARCHITECTURE.md` (geometry widener section)
- Knob discovery: `.env.example` block under "v2.7.108 — DTC-aware SL/TP geometry widener"
- Backup: `backups/v2.7.108/FORGE.mq5.pre-dtc-geometry`
- Industry citations:
  - [mql5.com/blogs/769205 — SL Strategies 2026](https://www.mql5.com/en/blogs/post/769205) (chop 1.5×ATR, swing 2.5×ATR)
  - [mql5.com/blogs/769205 — Adaptive SL based on regime](https://www.mql5.com/en/blogs/post/769205)
  - [earnforex — ATR Trailing Stop](https://www.earnforex.com/metatrader-expert-advisors/atr-trailing-stop/)
  - [tradingview — Multiple Time Frame R:R](https://www.tradingview.com/support/solutions/43000591728/)

---

### MANDATORY: ISS (ICT Structure Score) audit on every loss/win — check if score correlated with outcome

v2.7.112 ships ISS (ICT Structure Score) — scaffolding only (atoms stubbed at 0):
0-10 score per setup-trigger from 3 ICT structure atoms (MSS +5, FVG +3, ChoCH support +2).
ChoCH-against is a separate hard gate (not summed). Logged to `SIGNALS.iss_score`
+ 4 atom cols (`iss_mss`, `iss_fvg`, `iss_choch_support`, `iss_choch_against`).

**v2.7.112 caveat**: all atoms stub at 0 because real MSS/ChoCH/FVG detection
requires a swing-pivot tracker (v2.7.113) + FVG state tracker (v2.7.115) that
haven't shipped yet. Until then, `iss_score = 0` on every row is EXPECTED — the
schema + score-compute plumbing are in place, just no signal yet. Don't flag
zero-everywhere as a bug pre-v2.7.115.

**Why this audit is mandatory** (post-v2.7.115): the ICT methodology encodes
thresholds directly (≥8 high-conviction, ≥5 standard, <5 skip). Validation
against actual outcomes confirms the encoded thresholds match reality before
flipping `iss_block_below_threshold=1` to activate the gate.

**Canonical join query** — every TAKEN entry's ISS + atom split, joined with P&L:

```bash
sqlite3 -readonly "$DB" "
SELECT s.magic, s.setup_type, s.direction,
       s.iss_score, s.iss_mss, s.iss_fvg, s.iss_choch_support, s.iss_choch_against,
       ROUND(SUM(t.profit), 2) AS net_pnl,
       COUNT(t.deal_ticket)    AS deals
FROM SIGNALS s
LEFT JOIN TRADES t ON t.magic = s.magic AND t.run_id = s.run_id
WHERE s.outcome = 'TAKEN'
  AND s.run_id = (SELECT MAX(id) FROM TESTER_RUNS)
GROUP BY s.magic
ORDER BY net_pnl ASC;
"
```

**Aggregate query** — win rate + net P&L by ISS bucket (run at end-of-monitoring):

```bash
sqlite3 -readonly "$DB" "
SELECT s.iss_score,
       COUNT(*)                                        AS taken,
       SUM(CASE WHEN t.profit > 0 THEN 1 ELSE 0 END)   AS wins,
       ROUND(SUM(t.profit), 2)                         AS net_pnl,
       ROUND(AVG(t.profit), 2)                         AS avg_pnl
FROM SIGNALS s
JOIN TRADES t ON t.magic = s.magic AND t.run_id = s.run_id
WHERE s.outcome='TAKEN'
  AND s.run_id = (SELECT MAX(id) FROM TESTER_RUNS)
GROUP BY s.iss_score
ORDER BY s.iss_score;
"
```

**Reporting rule** (post-v2.7.115): every per-trade post-mortem section (loss decision
table, win celebration, missed-opportunity) MUST include an ISS line:
`ISS score: 8/10 (MSS +5, FVG +3, ChoCH+ +0, ChoCH− 0)`.

**Activation check** (run once at the start of each monitoring session):

```bash
grep -E "^FORGE_COMPOSITE_ISS_ENABLED|^FORGE_GATE_ISS_BLOCK_BELOW_THRESHOLD" \
     /Users/olasumbo/signal_system/.env
```

Expected for v2.7.112: `FORGE_COMPOSITE_ISS_ENABLED=0` (scaffolding ship; atoms stubbed).
Expected for v2.7.115+: `FORGE_COMPOSITE_ISS_ENABLED=1` (atoms wired, logging-only)
AND `FORGE_GATE_ISS_BLOCK_BELOW_THRESHOLD=0` (gate OFF until validation).
Expected for v2.7.116+: both `=1` once empirical evidence supports the threshold.

See `docs/ICT-Structure-Score.md` for atom definitions + decision tiers +
4-version migration plan (v2.7.113-116).

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

### Live AURUM DB (live FORGE trading on real broker — SCRIBE-written)
```
/Users/olasumbo/signal_system/python/data/aurum_intelligence.db
```
This is the live trading SCRIBE DB. Use this for **LIVE MODE** monitoring (see next section). Do NOT query it for tester/backtest data — those go in `aurum_tester.db` + the source journal DBs above.

---

## LIVE MODE — monitor the live broker EA instead of the tester (operator-mandated 2026-05-14)

### Trigger phrases (route to LIVE MODE)

Default `/forge-monitor` invocation = TESTER MODE (the Sections below). LIVE MODE is invoked by ANY message that contains the word `live` near a monitor-related token. Recognised forms include:

- `/forge-monitor live`
- `live /forge-monitor`
- `live forge-monitor`
- `live mon`
- `live monitor` / `live monitors`
- `live-mon`
- `monitor live`
- `forge live monitor`
- "monitor the live trading"
- "watch the live broker"
- "tail live FORGE"

**Rule**: if the operator's message contains the word `live` (case-insensitive) AND any of {`monitor`, `mon`, `forge-monitor`, `forge monitor`, `tail`, `watch`, `tick`}, route to LIVE MODE — do not over-narrow on the exact phrase. The intent signal is `live` + monitor-noun adjacency.

When you detect any of these, **do NOT use the tester source journal DB**. Switch to the scribe DB + `market_data.json` per the section below. Report at the top of tick 0 that you're in LIVE MODE so the operator can confirm.

### Data sources

| What | Where | Read via |
|---|---|---|
| Live signals + skips (24h+) | `python/data/aurum_intelligence.db` `forge_signals` table | `sqlite3 "file:${DB}?mode=ro&immutable=1"` |
| Live trades | same DB, `forge_journal_trades` table | same |
| Live trade groups (group-level aggregate) | same DB, `trade_groups` table | same |
| Live positions (per-leg state) | same DB, `trade_positions` table | same |
| Live trade closures | same DB, `trade_closures` table | same |
| Current market state | `~/Library/Application Support/.../Common/Files/market_data.json` | `python3 -m json.tool` |
| Service health | `make status` (bridge/listener/aurum/athena PIDs) | shell |
| Athena UI | `http://localhost:7842/` | `mcp__playwright__playwright_navigate` |

The `immutable=1` URI mode bypasses WAL lock contention from live `bridge.py` + `scribe.py` writers. Always use it for read-only live queries — without it, you'll hit transient `unable to open database file` errors during sync cycles.

### Key differences from TESTER mode

| Aspect | TESTER MODE | LIVE MODE |
|---|---|---|
| Source DB | `FORGE_journal_XAUUSD_tester.db` per agent | `aurum_intelligence.db` (single scribe DB) |
| Time scope | filter by `run_id=(SELECT MAX(id) FROM TESTER_RUNS)` | filter by `time >= strftime('%s','now','-24 hours')` (or whatever window) |
| `run_id` concept | exists, primary partition key | does NOT exist in live tables — use time-windowing |
| Sim clock | `MAX(time)` advances as backtest progresses | `MAX(time)` = real wall-clock now |
| TAKEN cadence | dense (hours of sim time per minute of wall time) | sparse (real trades on real broker; may be 0 in a slow day) |
| Analysis doc | `docs/FORGE_RUN<aurum_run_id>_ANALYSIS.md` | `docs/FORGE_LIVE_<YYYY-MM-DD>_ANALYSIS.md` (per calendar day, append-only) |
| MT5 log path | `Tester/Agent-127.0.0.1-3000/logs` | `MQL5/Logs/<broker>.log` (terminal main, not tester) |
| Stop condition | 3 ticks with no new signals (backtest finished) | operator says stop — live runs continuously |

### LIVE MODE setup (replaces tester Setup steps)

```bash
SCRIBE_DB=/Users/olasumbo/signal_system/python/data/aurum_intelligence.db
MD_FILE="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/market_data.json"

# 1. Confirm scribe DB exists + services are up
ls -la "$SCRIBE_DB"
make status | tail -8

# 2. Baseline: 24h signal counts + last TAKEN timestamp + current price
sqlite3 "file:${SCRIBE_DB}?mode=ro&immutable=1" "
SELECT COUNT(*) AS total_24h,
       SUM(CASE WHEN outcome='TAKEN' THEN 1 ELSE 0 END) AS taken_24h,
       datetime((SELECT MAX(time) FROM forge_signals WHERE outcome='TAKEN'),'unixepoch','localtime') AS last_taken_local
FROM forge_signals WHERE time >= strftime('%s','now','-24 hours');"

# 3. Current market state from broker
python3 -c "
import json
md = json.load(open('$MD_FILE'))
p = md.get('price', {})
acc = md.get('account', {})
print(f\"price: bid={p.get('bid')} ask={p.get('ask')} spread={p.get('spread')}\")
print(f\"account: balance={acc.get('balance')} equity={acc.get('equity')} margin={acc.get('margin')}\")
print(f\"open_positions: {len(md.get('open_positions', []))}\")
print(f\"pending_orders: {len(md.get('pending_orders', []))}\")
"

# 4. Analysis doc name — use calendar date
echo "docs/FORGE_LIVE_$(date +%Y-%m-%d)_ANALYSIS.md"
```

### LIVE MODE loop queries (replace Q1-Q9 from tester mode)

#### Live-Q1 — sim progress equivalent (just current count, last signal time)

```bash
sqlite3 "file:${SCRIBE_DB}?mode=ro&immutable=1" "
SELECT datetime(MAX(time),'unixepoch','localtime') AS latest_signal_local,
       COUNT(*) AS total_24h,
       SUM(CASE WHEN outcome='TAKEN' THEN 1 ELSE 0 END) AS taken_24h
FROM forge_signals WHERE time >= strftime('%s','now','-24 hours');"
```

#### Live-Q2 — TAKEN signals (last 24h, no run_id filter)

```bash
sqlite3 "file:${SCRIBE_DB}?mode=ro&immutable=1" "
SELECT datetime(time,'unixepoch','localtime') AS local_t, setup_type, direction,
       ROUND(price,2), ROUND(rsi,1), ROUND(adx,1), session, magic,
       iss_score, iss_mss, iss_fvg, iss_choch_support, iss_choch_against
FROM forge_signals
WHERE outcome='TAKEN' AND time >= strftime('%s','now','-24 hours')
ORDER BY time DESC;"
```

If 0 rows, broaden the window (e.g. `-72 hours` or `-7 days`) but flag in the report: "Last TAKEN was N days ago — possible structural over-block, run gate breakdown."

#### Live-Q3 — gate breakdown (last 24h)

```bash
sqlite3 "file:${SCRIBE_DB}?mode=ro&immutable=1" "
SELECT gate_reason, COUNT(*) AS cnt
FROM forge_signals
WHERE outcome='SKIP' AND gate_reason IS NOT NULL AND gate_reason!=''
  AND time >= strftime('%s','now','-24 hours')
GROUP BY gate_reason ORDER BY cnt DESC LIMIT 15;"
```

Same interpretation rules as tester (PEMCG asymmetry audit, etc.) — only the time-window changes.

#### Live-Q4 — recent trades + closures from broker (canonical, NOT from scribe DB)

For LIVE, the broker is the source of truth for fills. `market_data.json` carries the live `recent_closed_deals` array — read it directly rather than waiting for SCRIBE to sync:

```bash
python3 -c "
import json
md = json.load(open('$MD_FILE'))
print('open_positions:', len(md.get('open_positions', [])))
for p in md.get('open_positions', [])[:10]: print(' ', p)
print()
print('pending_orders:', len(md.get('pending_orders', [])))
for p in md.get('pending_orders', [])[:10]: print(' ', p)
print()
print('recent_closed_deals (last 10):')
for d in md.get('recent_closed_deals', [])[:10]: print(' ', d)
"
```

Cross-reference SCRIBE `forge_journal_trades` for the durable record:

```bash
sqlite3 "file:${SCRIBE_DB}?mode=ro&immutable=1" "
SELECT deal_ticket, magic, ROUND(profit,2), comment, datetime(time,'unixepoch','localtime')
FROM forge_journal_trades
WHERE time >= strftime('%s','now','-24 hours')
ORDER BY time DESC LIMIT 20;"
```

#### Live-Q5 — live cascade arming (MT5 terminal log, not tester log)

```bash
# Live MT5 terminal logs — different path from tester
LOGDIR="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Logs"
grep -E "ArmPostTP1Ladder|SELL STOP CONT|BUY LIMIT|BUY_LIMIT_RECOV|SELL_LIMIT_RECOVERY|slot\[2\]|slot\[3\]|slot\[4\]|exhausted" \
  "$LOGDIR"/*.log 2>/dev/null | sort -u | tail -20
```

If `$LOGDIR` is empty, MT5 may be logging to a different broker-specific path — operator may need to point you at it.

#### Live-Q6 — losses (last 24h)

```bash
sqlite3 "file:${SCRIBE_DB}?mode=ro&immutable=1" "
SELECT deal_ticket, magic, ROUND(profit,2), comment, datetime(time,'unixepoch','localtime')
FROM forge_journal_trades
WHERE profit < 0 AND time >= strftime('%s','now','-24 hours')
ORDER BY profit ASC;"
```

For deeper post-mortem on live losses, additionally join `trade_groups` + `trade_positions` (live-only tables that SCRIBE populates with per-group/per-leg state):

```bash
sqlite3 "file:${SCRIBE_DB}?mode=ro&immutable=1" "
SELECT * FROM trade_groups ORDER BY rowid DESC LIMIT 5;"
sqlite3 "file:${SCRIBE_DB}?mode=ro&immutable=1" "
SELECT * FROM trade_positions ORDER BY rowid DESC LIMIT 10;"
```

Schemas may drift — always `.schema trade_groups` / `.schema trade_positions` before relying on column names (per the atlas §11 verification rule).

#### Live-Q7 — component heartbeats (service health from scribe)

```bash
sqlite3 "file:${SCRIBE_DB}?mode=ro&immutable=1" "
SELECT component, status, datetime(last_seen,'unixepoch','localtime')
FROM component_heartbeats ORDER BY last_seen DESC LIMIT 8;"
```

If any component's `last_seen` is older than 5 minutes during active hours, surface in the tick report. Cross-check with `make status` — heartbeats can lag for genuine reasons but stale-heartbeat + running-PID = silent failure.

### LIVE MODE mandatory checks

The HOUSEKEEPING CHECKS A/B/C from tester mode still apply (run once at session start). Additionally:

- **No open positions check**: if `open_positions: 0` AND last TAKEN > 24h ago, flag as `LIVE DRY SPELL — possible structural over-block` and run the gate breakdown to identify the dominant blocker. Compare against the predicted top-3 from `aurum_run_id=N` tester runs (most recent).
- **PEMCG asymmetry on live data**: same audit as tester (`pemcg_buy_reversal_block` vs `pemcg_sell_reversal_block` over the 24h window) — if ratio ≥ 5× either direction, flag and run day-type verification.
- **Athena UI sync check**: confirm `forge_signals` is populating in scribe (not just `forge_journal_trades`) — same bug class as Check C, just on the live scribe DB. If trades work but signals don't, the Athena "TAKEN ENTRIES" panel will go dark even though live trades execute.

### LIVE MODE reporting differences

- Don't use the per-run analysis doc template — that's tester-specific. Create / append to `docs/FORGE_LIVE_<YYYY-MM-DD>_ANALYSIS.md` per calendar day. Multi-day live monitoring spans multiple files (one per day, append-only daily section log).
- Don't report "sim time" — report **wall-clock local time** + current price. Operator is watching their live broker, not a simulated clock.
- Flag any pending order with `tp == 0` immediately — that's the v2.7.117-fixed bug class. If a pending fills without TP, operator must manually close. Confirm v2.7.117 is loaded with `make forge-verify-live` before assuming the fix is active.
- When live cascade-recovery fills, surface the magic + tp value to confirm the v2.7.117 safety TP is being applied:

```bash
python3 -c "
import json
md = json.load(open('$MD_FILE'))
for p in md.get('pending_orders', []):
    if p.get('tp', 0) == 0:
        print('🔴 PENDING WITH NO TP:', p)
    else:
        print('✓ pending with TP:', p.get('ticket'), 'tp=', p.get('tp'))
"
```

### LIVE MODE stop condition

LIVE MODE has no auto-stop — live trading runs continuously. Stop only when:
- Operator says stop / `/clear` / etc.
- A live SL/loss event occurs that the operator wants a deep post-mortem on (switch to focused investigation, then resume)

Default cadence: 60s loop (vs 45s for tester) — broker tick rate is slower than backtest tick rate, so polling too fast wastes attention.

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

### Check C — Bridge → scribe forge_signals sync health
```bash
# Fast smoke test: any "X values for Y columns" errors in the last hour means
# the scribe.py INSERT placeholder count is out of sync with the column list.
# When this fires, bridge silently loops on sync-recovery and `forge_signals`
# stops accumulating — Athena UI "TAKEN ENTRIES" panel disappears even though
# trades keep syncing (separate INSERT path).
grep -E "SCRIBE sync_forge_journal error:|sync-recovery.*reset [0-9]+ missing" \
     python/logs/bridge.log 2>/dev/null \
   | awk -v cutoff="$(date -u -v-1H +%Y-%m-%dT%H:%M)" '$1 > cutoff' \
   | tail -10
```

If you see repeated lines like `SCRIBE sync_forge_journal error: 106 values for 110 columns`, that's the symptom. **Root cause**: a column was added to `JournalRecordSignal` in `ea/FORGE.mq5` and mirrored into `forge_signals` schema, but the placeholder count in `python/scribe.py::sync_forge_journal` (look for `",".join(["?"] * (N + 24 + 45))`) was NOT bumped to match. Three files must update together:

1. `ea/FORGE.mq5` — `SIGNALS` schema + `JournalRecordSignal` INSERT
2. `schemas/aurum_tester.sql` (or scribe `CREATE TABLE` in `python/scribe.py`) — mirror schema
3. `python/scribe.py::sync_forge_journal` — INSERT column list AND placeholder count

Historical case (2026-05-13): v2.7.45 + v2.7.47 added 5 columns (`killzone`, `minutes_into_kz`, `htf_h1_strong`, `intraday_label`, `intraday_counter_htf`). Schema + tuple were updated, placeholder count was not — every INSERT silently failed, dashboard's TAKEN ENTRIES panel went dark, took 12 hours to diagnose.

The `/forge-ea-review` skill's **Mandatory Check D** validates this parity statically. The monitor's job is to catch it at runtime if it slips through.

If either check fails:
- **Dead env**: fix by adding the mapping to `sync_scalper_config_from_env.py` OR adding the var to `tests/api/test_forge_27x_gates.py::FORGE_ENV_VARS_NOT_IN_SYNC` with rationale
- **Missing gate**: add an entry to `config/gate_legend.json` with label/explanation/category
- **Sync errors**: fix `python/scribe.py::sync_forge_journal` placeholder count to match column list, then `make reload-bridge`
- Report any of the above in the monitoring log so the next analysis doc captures it

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
       ROUND(rsi,1) as rsi, ROUND(adx,1) as adx, session,
       iss_score, iss_mss, iss_fvg, iss_choch_support, iss_choch_against
FROM SIGNALS WHERE outcome='TAKEN'
  AND run_id=(SELECT MAX(id) FROM TESTER_RUNS)
ORDER BY time;"
```

**ISS columns** (v2.7.112 scaffolding only — atoms stubbed at 0 until v2.7.113-115 lands real detection):
- `iss_score` (0–10) — sum of 3 weighted boolean atoms; default threshold `iss_min_threshold=5` (= MSS-mandatory bar)
- `iss_mss` (0 or 5) — MSS confirmed in trade direction (structural; primary, mandatory)
- `iss_fvg` (0 or 3) — price in active FVG retracement zone aligned with direction
- `iss_choch_support` (0 or 2) — recent counter-trend ChoCH supporting reversal turn
- `iss_choch_against` (0 or 1) — opposing ChoCH against trade direction — **HARD GATE** when set (not summed into score)

**Reporting requirement**: every TAKEN row in tick reports + every analysis-doc TAKEN row MUST show `iss_score` and the atom breakdown. Until v2.7.113+ activates real atom detection, all values are 0 — that's expected. Once detection lands, watch for the threshold-tier pattern (≥8 = high-conviction, ≥5 = standard, <5 = should-have-skipped). See `docs/ICT-Structure-Score.md` §3-4 for atom definitions + decision tiers.

**Note**: CES (v2.7.110) was retired in v2.7.112. The old `ces_*` columns may still exist in pre-v2.7.112 source DBs (intentionally not dropped) but are no longer populated. For runs ≥ v2.7.112, query `iss_*` columns only.

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

### MANDATORY: `.env` comment placement — never inline after a value

The env-sync parser (`scripts/sync_scalper_config_from_env.py` → `_parse_value()`) calls
`float(raw)` / `int(raw)` on the **entire post-`=` string**. It does NOT strip a trailing
`#` comment. An inline comment will break the sync at compile time.

**BAD — breaks `make forge-compile`:**
```bash
FORGE_DUMP_MAX_RSI=41             # block dump-SELL at mid-RSI in TREND_BULL
FORGE_CES_BUY_MIN_SCORE=4.5       # weighted-boolean score
```
The sync script crashes with `ValueError: could not convert string to float: '41             # block dump-SELL at mid-RSI in TREND_BULL'` because the raw value becomes the entire trailing string including spaces and `#`.

**GOOD — comment on the line ABOVE the assignment:**
```bash
# v2.7.107 — block dump-SELL at mid-RSI in TREND_BULL (gold chop bounces UP)
FORGE_DUMP_MAX_RSI=41
# v2.7.110 — CES weighted-boolean min score for BUY entries
FORGE_CES_BUY_MIN_SCORE=4.5
```

**Standalone comment lines (starting with `#`) are also safe** — the parser skips them.
Only `KEY=value # comment` on the same physical line is broken.

**Verification command** — must return empty before any commit that edits `.env`:
```bash
grep -nE "^FORGE_[A-Z_]+=[^[:space:]]+[[:space:]]+#" .env
```
If non-empty, fix each offender by moving the comment to the line above before running
`make forge-compile` / `make scalper-env-sync`.

**Same rule applies to `.env.example`** — though `.env.example` is never parsed by the
sync script (it's documentation only), inline comments here teach operators the wrong
pattern. Keep `.env.example` comments on the line ABOVE the key for consistency.

Historical context: v2.7.105 / v2.7.107 / v2.7.108 / v2.7.109 / v2.7.110 / v2.7.111 ships
all hit this. After v2.7.111 build, 14+ lines were corrected in one sweep. The pattern is
load-bearing — re-introducing inline comments breaks the entire compile pipeline.



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

## MANDATORY: GitHub-flavored markdown for all docs and guides

**Operator mandate** (2026-05-14): "all documents or guide being created all be git markup". Every new doc, case study, analysis, run report, recommendation file, or onboarding guide MUST be written in GitHub-flavored markdown (GFM) so it renders correctly on GitHub, in IDE previewers, and in dashboard markdown viewers.

### What "GitHub-flavored markdown" means in practice

| Use | Don't use |
|---|---|
| Pipe tables: `\| col \| col \|` with `\|---\|---\|` separator | Unicode box-drawing tables (`┌`, `─`, `┐`, `│`, `└`, `┘`) — they render as monospace blob in GitHub |
| Fenced code blocks with language: ` ```mql5 ` / ` ```python ` / ` ```bash ` | Indented 4-space code blocks (ambiguous with list items) |
| `**bold**`, `*italic*`, `` `inline code` `` | HTML tags like `<b>`, `<i>`, `<code>` |
| Standard ATX headings: `## §11 Section` | Setext underlined headings (`==` / `--`) — fragile with renumbering |
| Sentence-case headings | ALL CAPS HEADINGS (unless the section IS literally an acronym) |
| Pipe-separated row alignment: `\|---:\|` (right), `\|:---:\|` (center), `\|:---\|` (left) | Hand-spacing columns with extra whitespace |
| Numbered references (`§1.2`, `§11.3`) with anchor link if needed: `[§11.3](#§113-...)` | Page-number references — markdown is not paginated |
| GFM task lists when applicable: `- [ ]` / `- [x]` | Custom checkbox glyphs |
| Em-dash `—` and en-dash `–` (UTF-8) — these render fine in GFM | Triple-hyphen `---` for em-dash (collides with horizontal-rule syntax) |
| Horizontal rule: blank line, then `---`, then blank line | `***` or `___` (technically valid but visually noisy) |

### Tables — the most common failure mode

When generating analysis output you may be tempted to use the unicode box-drawing tables that terminals render nicely. Those DO NOT render in GitHub or in most markdown previewers — they collapse to a monospace blob without column structure. Always use pipe syntax:

```markdown
| Gate | Count | Layer |
|---|---:|---|
| `pemcg_buy_reversal_block` | 72,800 | UMCG (L1) |
| `dirlock_block_buy` | 14,826 | DirLock (L7/8) |
```

Renders as a proper table in GitHub, VS Code preview, dashboard markdown viewers, and `gh pr view`.

### Code blocks

Always specify the language tag — it drives syntax highlighting AND makes the block grep-able by language:

```markdown
```mql5
double tp = entry + (m5_atr * cascade_recovery_tp_atr_mult);
```
```

```markdown
```python
conn.execute("SELECT COUNT(*) FROM forge_signals WHERE aurum_run_id=43")
```
```

```markdown
```bash
make scalper-env-sync && make forge-compile
```
```

### File paths, line numbers, env knobs

- File:line cites: `ea/FORGE.mq5:14991` (no link — keeps it grep-able and copy-paste-friendly)
- Env knobs: `` `FORGE_GEOMETRY_CASCADE_RECOVERY_TP_ATR_MULT` `` (always backtick-quoted)
- Config JSON keys: `` `cascade_recovery_tp_atr_mult` `` (backtick-quoted)
- Function names: `` `EvaluateDirectionLock()` `` (backtick + parens to disambiguate from variables)

### Sections, anchors, cross-references

When you add a new section to an existing doc, **don't renumber other sections** unless the document explicitly says it's renumberable (most case studies have stable §-references; renumbering breaks `See §8 implementation requirements` cross-links inside the same doc).

If the new section forces renumbering of a tail section (e.g., Changelog moves from §11 to §12), add a changelog entry that **explicitly logs the renumbering** so future readers can follow the migration.

### Output for analysis tables in this skill

When `/forge-monitor` produces a gate-breakdown table, a TAKEN-signals table, a P&L-per-magic table, or any tabular tick output, use pipe syntax even in chat — the operator may paste it into a doc later. Don't make the operator translate from box-drawing back to pipes.

### Anti-patterns

- Unicode box-drawing tables in any doc, case study, or chat output that might end up in a doc
- Triple-hyphens or em-dashes used inconsistently in the same doc
- Missing language tag on code blocks (loses syntax highlighting + makes grep harder)
- HTML tags for emphasis (`<b>`, `<i>`) — markdown handles these natively
- Inline `# comments` after env values in `.env` snippets — the sync parser breaks on them (see `## MANDATORY: .env comment placement` in this skill)
- Renumbering stable §-references mid-doc without logging the shift in the changelog

### Onboarding guides and root-level docs

For onboarding guides (root `ONBOARDING.md`, anything in `docs/` that's user-facing rather than analysis-internal), additionally:
- Lead with a one-paragraph "What this is" summary
- TOC or section-index near the top when doc exceeds ~200 lines
- Every code block must be runnable (no pseudo-code mixed with real commands without labeling)
- Cross-link related docs explicitly: `See also: [FORGE_NAMING_CONVENTIONS.md](FORGE_NAMING_CONVENTIONS.md)`

### Enforcement during /forge-monitor sessions

When you (the monitoring agent) create or extend a doc during a session:
1. If you generate a table for a tick report, write it in pipe syntax — never box-drawing
2. If the operator pastes a box-drawing table back at you and asks you to put it in a doc, convert to pipe syntax BEFORE writing — do not store the box-drawing form
3. **Retroactive normalization rule (operator-mandated 2026-05-14)**: any time you touch an existing doc — appending a section, editing a row, fixing a typo, adding a changelog entry — you MUST also normalize the rest of that doc to GFM as part of the same edit. This is not "flag and ask" — it is "fix on touch". Specifically:
   - Convert any unicode box-drawing tables (`┌`, `─`, `┐`, `│`, `└`, `┘`, etc.) in that doc to pipe-syntax tables
   - Add language tags to any unlabeled fenced code blocks (`mql5` / `python` / `bash` / `sql` / `json`)
   - Convert any 4-space indented code blocks to fenced blocks with language tags
   - Replace HTML emphasis tags (`<b>`, `<i>`, `<code>`) with markdown equivalents (`**`, `*`, `` ` ``)
   - Fix Setext underlined headings (`==` / `--`) to ATX headings (`#`, `##`, etc.)
   - Preserve all content, section numbering, and cross-references — normalization is presentation-only, not semantic
   - Add a changelog entry: `**YYYY-MM-DD** — GFM normalization pass (box-drawing→pipe tables, code-block language tags). No semantic change.`
4. Do NOT spawn a separate "convert all docs" pass — only fix the doc you're already editing. The mandate is "the next time it touches any of the existing doc", not "audit the whole tree".
5. Do NOT touch docs you weren't already going to edit. Drive-by normalization across unrelated files creates noisy diffs and slows operator review.

### Cross-skill propagation

This GFM mandate applies to all skills that create or edit docs in this repo — not just `/forge-monitor`. When you (any skill) touch a doc:
- New doc → write in GFM from the start (see "MANDATORY: GitHub-flavored markdown" section above for the rules)
- Existing doc → normalize as part of the edit per the retroactive rule above

Skills currently in scope: `/forge-monitor`, `/forge-ea-review`, `/research`. If a skill not listed here is invoked and creates/touches a doc, the same rule applies — the GFM standard lives in this SKILL.md as the canonical reference, and other skills should cross-reference it rather than re-state it.

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
| Sim Time (UTC) | Group | Setup | Direction | Session | RSI | ADX | ATR | Price | ISS | MSS | FVG | ChoCH+ | ChoCH− | TP reached | P&L |
|----------------|-------|-------|-----------|---------|-----|-----|-----|-------|-----|-----|-----|--------|--------|-----------|-----|

*ISS columns are weighted-boolean components: MSS(0/5), FVG(0/3), ChoCH_support(0/2). ChoCH_against is a HARD GATE (not summed). Sum = `iss_score` (0–10). Decision tiers: ≥8 high-conviction · ≥5 standard · <5 SKIP. v2.7.112 ships scaffolding only — real atom detection in v2.7.113-115. See `docs/ICT-Structure-Score.md`.*

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
