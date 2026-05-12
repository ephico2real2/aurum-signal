# FORGE Decision Stack — Entry Logic Architecture

**Purpose**: Canonical naming + 5-layer architecture for FORGE's MQL5 entry/gate logic.
This is the source-of-truth for terminology. All other FORGE docs (atlas, playbook,
case studies, run analyses, skills) reference these terms exactly.

**Created**: 2026-05-12
**Maintainer**: kept current alongside `ea/FORGE.mq5` evolution. Every new setup type,
filter chain, composite, or atom MUST update this document. Skills mandate the update.

---

## §1. The 5-layer entry-decision stack

```
┌─ Setup Trigger ──────────────────────────────────────────────────────┐
│  Pattern detector booleans (e.g. dump_sell_trig, bb_breakout_buy_trig)│
│  Fires when raw price/indicator structure matches a setup type       │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
┌─ Filter Chain ───────▼──────────────────────────────────────────────┐
│  if/else-if cascade — each rung blocks entry with a named SKIP code  │
│  e.g. dump_rsi_block, dump_adx_block, dump_chop_block                │
│  This is the "negative space" — what STOPS an entry                  │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
┌─ Boolean Composite ──▼──────────────────────────────────────────────┐
│  Higher-level rule that combines atoms into a single TRUE/FALSE     │
│  e.g. BULL_DAY_DIP_BUY, INTRADAY_REVERSAL_TO_SELL                    │
│  Maps onto the filter chain — composite=TRUE iff every filter passes │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
┌─ Atoms ──────────────▼──────────────────────────────────────────────┐
│  Individual indicator predicates that make up a composite            │
│  e.g. h1_trend>=0.5, m5_rsi<=40, price<vwap_price, m5_lh_cascade     │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
┌─ Entry Geometry ─────▼──────────────────────────────────────────────┐
│  When all filters pass: direction, setup_type, sl, tp1, tp2,         │
│  lot_factor, leg count, cooldown. The "what fires" once "if" is TRUE │
└─────────────────────────────────────────────────────────────────────┘
```

---

## §2. Terminology mapping

| Concept | What we call it | Industry-standard term | FORGE codebase term |
|---|---|---|---|
| The pattern-detection boolean that fires first | **Setup Trigger** | trigger / signal generator | `*_trig` variables (e.g. `dump_sell_trig`) |
| The if/else-if SKIP cascade | **Filter Chain** | filter chain / decision tree / rule cascade | "filter chain" in comments; `gate_reason` in DB |
| The named blocked-entry code | **Gate Code** | reason code / rejection code | `gate_reason` column; entries in `config/gate_legend.json` |
| The TRUE/FALSE high-level rule | **Boolean Composite** | predicate composition / compound condition | "composite" in atlas §5 |
| The individual conditions inside a composite | **Atom** | predicate / atomic condition | "atom" in atlas |
| The named entry pattern | **Setup Type** | setup / pattern / strategy variant | `setup_type` column |
| What fires when the rule is TRUE | **Entry Geometry** | entry parameters / order spec | sl / tp1 / tp2 / lot / legs variables |

### Umbrella term

**"Entry Decision Logic"** or **"Decision Stack"** (this document) — the unified name for
all 5 layers and the way they compose into a single trading decision.

---

## §3. Why each layer is distinct

| Distinction | Why it matters |
|---|---|
| **Setup Trigger vs Filter Chain** | Trigger says "this pattern is happening"; Filter Chain says "this pattern is happening AND it's a quality entry." Two separate questions. |
| **Composite vs Filter Chain** | Composite is the SPEC (logical formula); Filter Chain is the IMPLEMENTATION (MQL5 if/else-if). Same logic, two representations. |
| **Atom vs Indicator** | An indicator is the raw value (`m5_rsi = 42.1`); an atom is a predicate (`m5_rsi <= 50`). Indicators are inputs; atoms are propositions. |
| **Gate Code vs Filter Rung** | A gate code is the named-string identity (`dump_rsi_block`); a filter rung is the if-branch that emits it. Code is what gets logged; rung is what runs. |
| **Boolean Composite vs Setup Type** | Composite is the entry-rule (when to fire); Setup Type is the result-label (what fired). One composite → one setup type, but they're conceptually separate. |
| **Entry Geometry vs everything above** | The above is "should we enter"; geometry is "if yes, what do we enter at what size with what SL/TP." Decision vs deployment. |

---

## §4. Canonical example — MOMENTUM_DUMP_SELL filter chain

```mql5
// ─── SETUP TRIGGER ───
// dump_sell_trig set elsewhere when M5 move > atr_mult × ATR in N bars
if (dump_sell_trig) {

   // ─── FILTER CHAIN (if/else-if cascade) ───
   if (m5_rsi >= g_sc.dump_max_rsi) {
      // GATE CODE: dump_rsi_block — RSI not exhausted
      JournalRecordSignal("SKIP", "dump_rsi_block", "MOMENTUM_DUMP", "SELL", ...);
   }
   else if (m5_adx < g_sc.dump_min_adx) {
      // GATE CODE: dump_adx_block — trend strength insufficient
      JournalRecordSignal("SKIP", "dump_adx_block", "MOMENTUM_DUMP", "SELL", ...);
   }
   else if (g_psar_state != "ABOVE") {
      // GATE CODE: dump_psar_block — PSAR not aligned for SELL
      JournalRecordSignal("SKIP", "dump_psar_block", "MOMENTUM_DUMP", "SELL", ...);
   }
   else if (g_regime_label == "RANGE") {
      // GATE CODE: dump_chop_block — RANGE regime = whipsaw zone
      JournalRecordSignal("SKIP", "dump_chop_block", "MOMENTUM_DUMP", "SELL", ...);
   }
   else if (g_sc.dump_sell_h1_max > 0 && h1_trend_strength >= g_sc.dump_sell_h1_max) {
      // GATE CODE: dump_h1_trend_block_sell — too bullish on H1 for SELL
      JournalRecordSignal("SKIP", "dump_h1_trend_block_sell", "MOMENTUM_DUMP", "SELL", ...);
   }
   else {
      // ─── ENTRY GEOMETRY ───
      // All filters passed → SETUP TYPE = MOMENTUM_DUMP, direction = SELL
      direction  = "SELL";
      setup_type = "MOMENTUM_DUMP";
      sl  = ask + m5_atr * 4.0;
      tp1 = bid - m5_atr * 0.6;
      tp2 = bid - m5_atr * 1.0;
      // ... lot_factor, leg count from setup-specific knobs
   }
}
```

**The equivalent Boolean Composite** (atlas §5 spec form):

```mql5
bool MOMENTUM_DUMP_SELL_COMPOSITE =
     dump_sell_trig                                  // Setup Trigger atom
  && (m5_rsi < g_sc.dump_max_rsi)                    // ← dump_rsi_block reversed
  && (m5_adx >= g_sc.dump_min_adx)                   // ← dump_adx_block reversed
  && (g_psar_state == "ABOVE")                       // ← dump_psar_block reversed
  && (g_regime_label != "RANGE")                     // ← dump_chop_block reversed
  && (g_sc.dump_sell_h1_max <= 0
      || h1_trend_strength < g_sc.dump_sell_h1_max); // ← dump_h1_trend_block_sell reversed
```

**Composite = TRUE iff every rung of the Filter Chain passes** (atoms must all hold).
**Setup Type assigned + Entry Geometry computed when composite is TRUE.**

---

## §5. Where each layer lives in code/docs

| Layer | EA code (`ea/FORGE.mq5`) | Documentation |
|---|---|---|
| Setup Trigger | `~5660-6800` (scalper trigger evaluation) | Playbook §1-§3 |
| Filter Chain | embedded in trigger blocks | gate_legend.json + Playbook §7 |
| Gate Code | string literals in `JournalRecordSignal` calls | `config/gate_legend.json` (authoritative dictionary) |
| Boolean Composite | (filter chains ARE the implementation) | `docs/FORGE_INDICATOR_ATLAS.md` §5 (registry) |
| Atom | individual conditions in `if` statements | `docs/FORGE_INDICATOR_ATLAS.md` §1 (indicator inventory) |
| Setup Type | `setup_type = "..."` assignments | Playbook §1 (Setup Classification Matrix) |
| Entry Geometry | `sl`, `tp1`, `tp2`, `direction`, `lot_factor` assignments | Playbook §5 (Geometry Quick Reference) |

---

## §6. Concrete usage examples

| Statement | Maps to |
|---|---|
| "What does FORGE's **entry decision logic** look like for MOMENTUM_DUMP?" | Walk through the 5 layers for that setup |
| "Add a new **boolean composite** to the BULL_DAY_DIP_BUY filter chain" | Atlas §5 registry update + corresponding ea/FORGE.mq5 filter chain change |
| "The `dump_rsi_block` **gate code** fires when..." | gate_legend.json lookup |
| "This **atom** uses h1_trend_strength..." | Atlas §1 inventory + composite spec in atlas §5 |
| "**Setup Type** = BB_BREAKOUT_RETEST" | Playbook §1 setup matrix |
| "**Entry Geometry** for MOMENTUM_DUMP SELL is sl=4.0×ATR, tp1=0.6×ATR" | Playbook §5 geometry table |
| "Add a new **setup trigger** for impulse detection" | ~`*_trig` boolean in ea/FORGE.mq5, new entry in Playbook §1, new gate codes for its filter chain |

---

## §7. Maintenance rules

This document is the canonical reference for naming. To stay current:

1. **New setup type** added to `ea/FORGE.mq5` → add row to Playbook §1 + reference here in §5
2. **New gate code** in a filter chain → add entry to `config/gate_legend.json` + reference here in §4 if it's a new pattern
3. **New boolean composite** in a case study → register in atlas §5, then cite in §6 above if it introduces a new naming pattern
4. **New atom** in a composite → add to atlas §1 inventory if it's a new indicator, then it's just used in composite specs
5. **Entry geometry changes** (SL/TP/lot multipliers) → update Playbook §5 geometry table

Skills (`forge-monitor`, `forge-ea-review`, `research`) reference this document for terminology. When ambiguity arises ("filter rung" vs "gate code" vs "composite"), this document is the tiebreaker.

---

## §8. Cross-references

- **Atlas** (`docs/FORGE_INDICATOR_ATLAS.md`) — §1 indicator inventory (atoms), §5 composite registry, §13 command log
- **Decision-stack inventory** (`docs/FORGE_DECISION_STACK_INVENTORY.md`) — canonical per-version EA extraction (v2.7.36+). Every setup trigger, filter chain, composite, atom, and entry geometry block in `ea/FORGE.mq5` mapped to file:line. The source-of-truth for "what does FORGE actually implement today."
- **Playbook** (`FORGE_SETUP_PLAYBOOK.md`) — §1 setup matrix, §5 geometry, §7 gate codes per setup, §10 boolean composite design pattern
- **Gate dictionary** (`config/gate_legend.json`) — authoritative source for gate codes
- **EA source** (`ea/FORGE.mq5`) — implementation of all 5 layers
- **Case studies** (`docs/FORGE_CASE_STUDY_*.md`) — boolean composites in action with cross-day truth tables
- **Logging extension** (`docs/FORGE_LOGGING_EXTENSION_DESIGN.md`) — closes the telemetry deficit where Layer-4 atoms reference indicators not yet journaled. v2.7.37+ work item.
- **Skill** (`.claude/skills/forge-monitor/SKILL.md`) — workflow for adding new composites, includes verification-first principle and command logging

---

## §10. Cross-version inventory (NEW v2.7.36)

Per-version 5-layer extractions live in `docs/FORGE_DECISION_STACK_INVENTORY.md`. Each release that changes the EA's entry decision logic appends a section to that file. The inventory is the canonical answer to:

- "Which setup triggers exist in v2.7.X?"
- "What's the filter chain for setup Y in this build?"
- "Which atoms feed composite Z?"
- "When I see `SKIP gate=X` in the journal, which atom failed and where in the EA?" (§7 trace map)

Skills (`forge-monitor`, `forge-ea-review`) reference the inventory for current-state verification before proposing changes. The inventory MUST be regenerated after any v2.7.X EA refactor that touches:
1. A new setup trigger (Layer 1)
2. A new or renamed gate code in a filter chain (Layer 2)
3. A new composite or atom (Layer 3/4)
4. Geometry changes to SL/TP/lot multipliers (Layer 5)

---

## §11. Changelog

| Date | Change |
|---|---|
| 2026-05-12 | Initial document created. 5-layer entry-decision stack defined: Setup Trigger → Filter Chain → Boolean Composite → Atoms → Entry Geometry. Terminology mapping table. Canonical MOMENTUM_DUMP_SELL example. Cross-references to atlas / playbook / gate_legend. |
| 2026-05-12 | Note: `g_regime` struct (defined in [`FORGE_REGIME_TAXONOMY.md §3`](FORGE_REGIME_TAXONOMY.md)) becomes the canonical **Atom source** from Phase 2 (v2.7.37+) onward. Atoms today reference globals like `g_regime_label`, `g_daily_bear_bias`, `h1_bull`; post-migration, atoms reference `g_regime.htf_label`, `g_regime.daily_bear_bias`, `g_regime.intraday_counter_htf`, etc. (See `FORGE_REGIME_TAXONOMY.md §2.6` for HTF/MTF/LTF glossary.) Composite specs in atlas §5 V2/V3 use the future syntax; the EA implementation references the current globals until Phase 3 migration. |
| 2026-05-12 | Added §10 (Cross-version inventory) pointing to `docs/FORGE_DECISION_STACK_INVENTORY.md`. Initial v2.7.36 extraction populated (5 setup types, 58 gate codes, 8 composites, ~45 atoms, 8 geometry rules). Inventory becomes per-release mandatory artefact. |
