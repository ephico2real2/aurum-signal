# FORGE ICT/ISS × PEMCG combination matrix

**Status**: canonical operational reference for every possible state of the ICT/ISS layer (v2.7.118+) combined with the existing PEMCG layer (v2.7.84+). Covers all combinations including the dangerous ones — no "audit-only" shortcuts. Read before flipping any of the 14 env knobs.

**Cross-references**:
- [`FORGE_PEMCG_ICT_INTEGRATION.md`](FORGE_PEMCG_ICT_INTEGRATION.md) — the 3-mode architectural spec (Mode A/B/C)
- [`FORGE_PEMCG_ARCHITECTURE.md`](FORGE_PEMCG_ARCHITECTURE.md) — canonical PEMCG reference (7 atoms, 3 layer consumers)
- [`MQL5_MODULAR_EA_DESIGN.md`](MQL5_MODULAR_EA_DESIGN.md) — modular FORGE convention
- [`FORGE_LIVE_2026-05-14_ANALYSIS.md`](FORGE_LIVE_2026-05-14_ANALYSIS.md) §5 — the ISS-C composite design that motivates Mode C
- [`prompts/ICT_Tradingidea.md`](prompts/ICT_Tradingidea.md) — operator ICT spec
- `ea/include/Forge/IctStructure.mqh` — Phase 1 module (v2.7.118)
- `ea/FORGE.mq5:13620-13705` — the ISS gate emission code path

## §1 The 14 knobs, categorized

### §1.1 ICT atom-compute layer (3 boolean + 4 numeric)

| Knob | Layer | Type | Default | Role |
|---|---|---|---:|---|
| `FORGE_COMPOSITE_ISS_ENABLED` | **master** | bool | 0 | Whole ISS compute block at `FORGE.mq5:13632`. When 0, ALL atoms log 0 regardless of sub-knobs. |
| `FORGE_ICT_MSS_ENABLED` | atom | bool | 0 | MSS atom compute (`g_iss_mss`) |
| `FORGE_ICT_FVG_ENABLED` | atom | bool | 0 | FVG atom compute (`g_iss_fvg`) + ring maintenance every M5 close |
| `FORGE_ICT_SWING_LOOKBACK` | tuning | int | 3 | Fractal 2N+1 window for swing-pivot detection |
| `FORGE_ICT_MSS_DISPLACEMENT_ATR_MULT` | tuning | float | 0.5 | MSS body/ATR filter (matches DirLock convention) |
| `FORGE_ICT_FVG_MIN_SIZE_ATR_MULT` | tuning | float | 0.15 | FVG min gap / ATR floor |
| `FORGE_TIMING_ISS_FVG_MAX_AGE_BARS` | tuning | int | 12 | FVG age cap (60 min in M5) |

### §1.2 ICT gate-emission layer (2 boolean + 4 weight/threshold)

| Knob | Layer | Type | Default | Role |
|---|---|---|---:|---|
| `FORGE_GATE_ISS_BLOCK_BELOW_THRESHOLD` | **Mode B** gate | bool | 0 | When 1: SKIP signals where `iss_score < min_threshold` (gate `iss_below_threshold`) |
| `FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED` | **Mode C** gate | bool | 0 | When 1: ISS-C HIGH_CONVICTION overrides `pemcg_*_reversal_block` (Phase 4 wires underlying composite) |
| `FORGE_GATE_ISS_MIN_THRESHOLD` | threshold | int | 5 | Score gate fires below this when Mode B is on |
| `FORGE_GATE_ISS_WEIGHT_MSS` | weight | int | 5 | MSS contribution to `iss_score` |
| `FORGE_GATE_ISS_WEIGHT_FVG` | weight | int | 3 | FVG contribution |
| `FORGE_GATE_ISS_WEIGHT_CHOCH_SUPPORT` | weight | int | 2 | ChoCH contribution (Phase 2 wires the atom) |
| `FORGE_GATE_ISS_FVG_MAX_FILL_PCT` | tuning | float | 0.5 | FVG mitigation threshold (50% retraced) |

### §1.3 PEMCG layer (unchanged through Phase 1-5)

| Knob | Layer | Type | Default | Role |
|---|---|---|---:|---|
| `FORGE_GATE_UMCG_ENABLED` | **Layer 1** | bool | 1 | Universal Market Condition Gate — `pemcg_*_reversal_block` SKIPs |
| `FORGE_GATE_UMCG_BUY_BLOCK_THRESHOLD` | tuning | int | 5 | Supermajority threshold (per v2.7.86 fix) |
| `FORGE_GATE_UMCG_SELL_BLOCK_THRESHOLD` | tuning | int | 5 | Mirror SELL |
| `FORGE_GATE_CVCSM_ENABLED` | **Layer 2** | bool | 1 | SL-triggered cooldown state machine |
| `FORGE_SETUP_BB_EXHAUSTION_REVERSAL_ENABLED` | **Layer 3** | bool | 1 | Opposite-direction reversal capture |

## §2 The combination matrix — 16 cells

Combinations of the 4 ICT macro-states × 3 PEMCG macro-states + 4 edge cases.

### §2.1 ICT macro-states (the row dimension)

| Code | `ISS_ENABLED` | `MSS_ENABLED` | `FVG_ENABLED` | `BLOCK_BELOW` | `ISS_C_OVERRIDE` | Means |
|---|:-:|:-:|:-:|:-:|:-:|---|
| **I0** | 0 | * | * | * | * | Master OFF — atoms stub 0, no gate, byte-identical to v2.7.117 |
| **I1** | 1 | 0 | 0 | 0 | 0 | Master ON but compute OFF — block executes, atoms stay 0, no signal change |
| **I2** | 1 | 1 | 1 | 0 | 0 | **Mode A** — atoms compute + log, no gate fires (instrumentation-only) |
| **I3** | 1 | 1 | 1 | 1 | 0 | **Mode B** — additive: PEMCG fires today PLUS SKIP if `iss_score < threshold` |
| **I4** | 1 | 1 | 1 | 0 | 1 | **Mode C** (Phase 4) — ISS-C HIGH_CONVICTION overrides PEMCG |
| **I5** | 1 | 1 | 1 | 1 | 1 | **Mode B+C** — both gates active (conflict resolution per §4.3) |

### §2.2 PEMCG macro-states (the column dimension)

| Code | UMCG | CVCSM | Layer 3 | Means |
|---|:-:|:-:|:-:|---|
| **P0** | 0 | 0 | 0 | **PEMCG OFF** — no reversal-trap filter at all |
| **P1** | 1 | 0 | 0 | **L1 only** — UMCG gate fires, no cooldown / no reversal capture |
| **P2** | 1 | 1 | 1 | **Full PEMCG** (current default) — all 3 layers active |

### §2.3 16-cell matrix

| | **P0** PEMCG OFF | **P1** UMCG only | **P2** Full PEMCG (default) |
|---|---|---|---|
| **I0** Master OFF | **A0** All gates off. Wide-open. Setups fire whenever raw triggers fire. ⚠️ no safety net. | **A1** UMCG gate fires only. CVCSM cooldown bypassed → re-entry on SL still possible. Layer 3 reversal disabled. | **A2 (← current default v2.7.117 + v2.7.118 baseline)** PEMCG full stack. ICT silent. Byte-identical to pre-ICT FORGE. ✓ |
| **I1** ISS master ON + compute OFF | **B0** PEMCG fully off; ISS block runs but atoms log 0; score always 0. If Mode B were on (it isn't here) every signal would SKIP. Equivalent to A0 functionally — wasted CPU. | **B1** UMCG only + ISS noise compute. Equivalent to A1 functionally. | **B2** Full PEMCG + ISS noise compute. Equivalent to A2 functionally. ISS columns log 0 in SIGNALS. Wasted CPU. |
| **I2** Mode A (compute on) | **C0** No PEMCG, ICT atoms compute + log. Operator sees ISS distribution in raw signal flow (no PEMCG filter). Useful for measuring ISS-vs-PEMCG selectivity. ⚠️ no SKIP gate — fires everything. | **C1** UMCG + ICT atoms log. Lighter-than-default filter. Useful when you want to measure ISS additive value without CVCSM cooldown noise. | **C2 (← recommended for Step-2 testing)** Full PEMCG + ICT atoms log. ISS distribution measured in production-realistic conditions. No behaviour change vs current default. ✓ |
| **I3** Mode B (block gate on) | **D0** No PEMCG. ICT score gate is the ONLY filter. Pure ICT selectivity test. ⚠️ no reversal-trap safety net. | **D1** UMCG + ICT score gate. Two filters stacked but no CVCSM cooldown. | **D2** Full PEMCG + ICT score gate (additive). Mode B canonical state. Most restrictive — both PEMCG and ICT must pass. ⚠️ likely too restrictive in Phase 1 (no ChoCH atom yet — score ceiling 8). |
| **I4** Mode C (override on, Phase 4+) | **E0** No PEMCG to override — knob is a no-op. ICT atoms compute + log; nothing else changes. Equivalent to C0. | **E1** UMCG + override on. When ISS-C ≥ 8: override fires the entry regardless of UMCG. PEMCG L1 effectively becomes "warn unless ICT high-conviction." | **E2** Full PEMCG + override. The **2026-05-14 live problem-solver** — 730× PEMCG_SELL over-block on confirmed-bear day gets released when ISS-C ≥ 8. Requires Phase 4 underlying composite. |
| **I5** Mode B+C | **F0** No PEMCG. ICT score gate + ICT override. Override doesn't matter here (nothing to override). Score gate alone determines fire. Equivalent to D0. | **F1** UMCG + both ICT gates. Conflict-resolution: ISS-C ≥ 8 overrides UMCG; below 8, ISS score gate filters at threshold 5. Complex but legitimate stacking. | **F2** Full PEMCG + both ICT gates. Highest-resolution filter — PEMCG warns, ICT score filters low-conviction, ISS-C overrides high-conviction. Operator-recommended endgame after all 5 phases ship + validation. |

### §2.4 Visual mode key

```
✓  = recommended / production-safe combination
⚠️ = dangerous OR untested combination — read § §3 / §4 before flipping
←  = current state marker
```

## §3 Dangerous combinations (the no-go zone)

These are operationally valid (the EA won't crash) but produce surprising or unsafe behaviour. Avoid unless you specifically know what you're doing.

### §3.1 D0 — Mode B with PEMCG OFF (no safety net)

- ICT score gate filters by `iss_score ≥ 5`, but the score ceiling in Phase 1 is 8 (5 MSS + 3 FVG)
- Without PEMCG, NOTHING filters reversal-trap entries (G5006-class)
- Phase 1 has no ChoCH-against hard gate yet
- **Risk**: a clean MSS + FVG into a reversal trap (e.g., MSS break of a wick swing high then immediate reversal) fires unfiltered

### §3.2 I1 — ISS master ON, both compute switches OFF (vacuous CPU spend)

- The compute block at `:13632` runs every setup-trigger but every atom branch is OFF
- `g_iss_score` always 0
- Every Mode-B SKIP fires (if Mode B were on)
- Mode A produces no useful data (everything logs 0)
- **Risk**: silent waste of compute; logs look like ICT isn't working

### §3.3 D2 — Mode B with Phase 1 score ceiling

- `iss_score` max = 5 (MSS) + 3 (FVG) = 8
- Threshold default 5 means **only MSS-confirmed entries pass**
- FVG alone (score 3) blocks all signals
- Phase 1 has no ChoCH atoms (would contribute 2 more = ceiling 10)
- **Effect**: requires MSS structural break on every entry. Stricter than Mode B will be after Phase 2.
- **Mitigation**: lower `FORGE_GATE_ISS_MIN_THRESHOLD` to 3 until Phase 2 ships, OR wait for Phase 2 to flip Mode B

### §3.4 P1 — UMCG without CVCSM (no SL cooldown)

- Layer 1 still blocks reversal-trap entries
- BUT: after a SL fires, the EA re-enters immediately on the next valid setup (no cooldown)
- High slippage / over-trading risk after a loss cluster
- **Use case**: tester replays where you want to measure UMCG-only selectivity. Never in live.

### §3.5 P0 — PEMCG OFF entirely

- No reversal-trap filter
- No SL cooldown
- No opposite-direction reversal capture
- **The only case to use this**: pure ICT-isolation experiments where you want zero PEMCG interference. Tester only, never live.

### §3.6 I5/F1 — Mode B+C with sub-threshold ISS-C

- Override fires when ISS-C ≥ 8
- Score gate fires when `iss_score < min_threshold`
- For a signal with ISS-C=7 (just below override) and `iss_score`=4 (below threshold): **gate wins**, SKIP
- For a signal with ISS-C=9 and `iss_score`=3: override wins, fires
- **Conflict resolution**: ISS-C override is evaluated BEFORE the score gate. Operator must understand this precedence (codified in Phase 4 implementation).

## §4 Recommended flip sequence (Phase 1 → eventually Mode C)

### §4.1 Current state — Cell A2 (Mode A baseline)

Locked 2026-05-14. All 14 ICT/ISS knobs at canonical defaults / disabling values. PEMCG full stack on. Byte-identical to v2.7.117 runtime. Tester is safe.

### §4.2 Next step — Cell C2 (Mode A with atom compute)

```bash
# .env edits:
FORGE_COMPOSITE_ISS_ENABLED=1     # 0 → 1   master ISS block runs
FORGE_ICT_MSS_ENABLED=1           # 0 → 1   real MSS atom
FORGE_ICT_FVG_ENABLED=1           # 0 → 1   real FVG atom + ring maintenance
# All other knobs unchanged
```

Run `make scalper-env-sync && make forge-reload` → re-attach EA in MT5 → tester replay. ISS columns in SIGNALS now log meaningful values. No SKIP gate fires. PEMCG operates as today.

**Validation query** (Q-MO-ISS):
```sql
SELECT s.iss_score,
       COUNT(*) AS taken,
       SUM(CASE WHEN t.profit > 0 THEN 1 ELSE 0 END) AS wins,
       ROUND(SUM(t.profit), 2) AS net_pnl
FROM SIGNALS s JOIN TRADES t ON t.magic = s.magic AND t.run_id = s.run_id
WHERE s.outcome='TAKEN' AND s.run_id = (SELECT MAX(id) FROM TESTER_RUNS)
GROUP BY s.iss_score ORDER BY s.iss_score;
```

Confirm: distribution non-degenerate, wins skew to higher scores, losses to lower.

### §4.3 Eventual step — Cell D2 (Mode B production)

Only after §4.2 distribution validates against:
- G5006 known loser: score < 5 → would SKIP ✓
- G5048 known loser: score < 5 → would SKIP ✓
- 2026-05-14 live PEMCG-blocked SELLs: score ≥ 5 → would TAKE ✓

```bash
# Single .env edit on top of §4.2:
FORGE_GATE_ISS_BLOCK_BELOW_THRESHOLD=1     # 0 → 1   Mode B active
```

If Phase 1 score ceiling 8 is too restrictive (Mode B blocks legitimate non-MSS setups), lower:
```bash
FORGE_GATE_ISS_MIN_THRESHOLD=3             # 5 → 3   accept FVG-only (score 3)
```

### §4.4 Endgame — Cell F2 (Mode B+C, Phase 4+)

After Phase 4 ships the ISS-C composite, flip:
```bash
FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED=1     # 0 → 1   Mode C active
```

Both gates now active. ISS-C high-conviction overrides PEMCG reversal-trap warnings; ISS score gate filters low-conviction setups.

## §5 Decoder — "given a .env, what mode am I in?"

```python
def decode_mode(env):
    iss = env.get("FORGE_COMPOSITE_ISS_ENABLED", "0") == "1"
    mss = env.get("FORGE_ICT_MSS_ENABLED", "0") == "1"
    fvg = env.get("FORGE_ICT_FVG_ENABLED", "0") == "1"
    block = env.get("FORGE_GATE_ISS_BLOCK_BELOW_THRESHOLD", "0") == "1"
    override = env.get("FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED", "0") == "1"
    umcg = env.get("FORGE_GATE_UMCG_ENABLED", "1") == "1"
    cvcsm = env.get("FORGE_GATE_CVCSM_ENABLED", "1") == "1"
    rev = env.get("FORGE_SETUP_BB_EXHAUSTION_REVERSAL_ENABLED", "1") == "1"

    ict = "I0" if not iss else \
          "I1" if not (mss and fvg) else \
          "I5" if (block and override) else \
          "I4" if override else \
          "I3" if block else "I2"

    pemcg = "P2" if (umcg and cvcsm and rev) else \
            "P0" if not (umcg or cvcsm or rev) else "P1"

    return f"{ict}/{pemcg}"
```

Quick reads:
- `I0/P2` = current default (PEMCG full, ICT silent)
- `I2/P2` = recommended testing state (PEMCG full, ICT logging)
- `I3/P2` = Mode B production
- `I4/P2` = Mode C production (Phase 4+)
- `I5/P2` = Mode B+C endgame
- Anything with `P0` or `P1` = special use only, never live

## §6 What this doc deliberately does NOT cover

- **Numeric tuning** (`SWING_LOOKBACK`, `MSS_DISPLACEMENT_ATR_MULT`, etc.) — these are sub-state of each cell, not separate modes. Out-of-band tuning per Phase-1 atom validation.
- **Phase 2-5 atom additions** (ChoCH support/against, Liquidity Sweep, OB, Breaker, Unicorn, CRT) — score ceiling will rise from 8 → 10+ as atoms ship; thresholds may need re-tuning. Each phase doc covers its own ceiling impact.
- **CVCSM/Layer 3 interactions** with future ChoCH-against — open question, see [`FORGE_PEMCG_ICT_INTEGRATION.md`](FORGE_PEMCG_ICT_INTEGRATION.md) §7.
- **Mode D** (replace PEMCG entirely with ICT score) — not on the table today.

## §7 Changelog

- **2026-05-14** — Initial doc. Captures all 16 ICT × PEMCG combination cells, dangerous-zone list, recommended flip sequence (A2 → C2 → D2 → F2), .env-to-mode decoder. Current branch state: `v2.7.118-ict-trading-models`, Mode A baseline locked (cell A2).
