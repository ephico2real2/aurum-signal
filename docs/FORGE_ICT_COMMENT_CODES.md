# FORGE ICT Comment Codes — canonical reference

**Status**: canonical reference for the FORGE broker-comment scheme. Single source of truth for every prefix, segment code, parser rule, and rollout decision.

**Audience**: anyone reading a TRADES.comment value, building a scribe parser, designing a new order-placement code path, or grepping the broker journal.

---

## §1 Purpose

Every order FORGE places sets the `MqlTradeRequest.comment` field to a structured, pipe-delimited string. The comment is the **carrier of context** that survives across:

- MT5 broker journal (operator's eyeball scan)
- TRADES table (scribe parses the comment to derive setup_type, direction, group_id without joining SIGNALS)
- Live dashboard / ATHENA queries (`WHERE comment LIKE '...'` filters)
- Post-mortem analysis (the comment is frozen at order-placement time; the SIGNAL row may be evicted before the position closes)

This doc codifies the schema so all five consumers parse the same shape.

---

## §2 The full comment shape

### §2.1 Primary entry / cascade leg / recovery (canonical shape)

```
<ZONE>_<ORDER_TYPE>|<CAT>_<DIR>|G<GROUP_ID>|<TP_OR_LEG>|<KZ_DETAIL>|<CONV>[|<SK_DETAIL>]
```

Six required segments + optional seventh segment (`<SK_DETAIL>` only emitted when a Silver Knife window is active).

### §2.2 Why zone-leading

The PREFIX (`<ZONE>_<ORDER_TYPE>`) is the FIRST thing visible in the broker journal. Putting zone identification there makes the trade's ICT character readable at a glance:

- `SK_MKT|MSS_CONT_B|G5001|...` — operator instantly sees **Silver Knife market entry**, top-conviction window
- `OFF_MKT|LIQ_SWEEP_B|G5003|...` — operator instantly sees **off-session entry**, de-risked region

The `<KZ_DETAIL>` and `<SK_DETAIL>` segments later in the comment provide the SPECIFIC window (LDN_OPEN_KZ vs NY_PM_KZ vs ASIA_KZ).

---

## §3 Segment tables

### §3.1 `<ZONE>` — zone category (3 codes, computed at order-placement time)

| Code | Meaning | Trigger |
|---|---|---|
| **`KZ`** | Inside any identified Killzone | `g_regime.killzone != ""` and `g_regime.silver_bullet == ""` |
| **`SK`** | Inside Silver Knife window | `g_regime.silver_bullet != ""` (which IMPLIES `g_regime.killzone != ""`) |
| **`OFF`** | Off-session | `g_regime.killzone == ""` |

**Silver Knife implies Killzone.** Per ICT canon (and FORGE.mq5 implementation), every Silver Knife sub-window sits inside a Killzone. The `SK` code is a stricter classification — when both are true, the SK prefix wins.

**Source-producer ↔ helper-consumer wiring:**

| Chokepoint state values | Helper returns (IctComment.mqh:39-43) |
|---|---|
| `g_regime.silver_bullet != ""` | `"SK"` (SK check happens FIRST — implies KZ) |
| `g_regime.killzone != ""` AND `g_regime.silver_bullet == ""` | `"KZ"` |
| `g_regime.killzone == ""` | `"OFF"` |

The chokepoint sets both globals per tick at FORGE.mq5:11547 (silver_bullet) + 11546 area (killzone). `Forge_ZonePrefix()` is the single resolver — order-placement code never re-computes zone classification from MqlDateTime.

> **Terminology note**: `SILVER_KNIFE` is the operator's preferred internal name. ICT canonical literature uses `SILVER_BULLET`. The two refer to the same concept (60-min hyper-concentrated FVG-entry windows: 03:00-04:00 / 10:00-11:00 / 14:00-15:00 NY). FORGE source code (SIGNALS column `silver_bullet`, `ComputeCurrentSilverBulletLabel()`, etc.) uses the canonical term internally; the comment scheme uses `SK` for compactness AND operator preference.

### §3.2 `<ORDER_TYPE>` — order kind (8 codes, replaces legacy `SCALP_*` family)

| Code | Legacy prefix | Source line | Semantics |
|---|---|---:|---|
| `MKT` | `SCALP` | 3145, 15604 | Market entry — staged-add leg or primary batch fill |
| `LIMIT` | `SCALP_LIMIT` | 15792 | Limit L1 — placed below market for BUY / above for SELL |
| `LIMIT_L2` | `SCALP_LIMIT_L2` | 15825 | Limit L2 — cascade limit (deeper retrace) |
| `BUY_STOP_CONT` | `SCALP_BUY_STOP_CONT` | 16394 | Buy-stop cascade continuation leg |
| `SELL_STOP_CONT` | `SCALP_SELL_STOP_CONT` | 16189 | Sell-stop cascade continuation leg |
| `BUY_LIMIT_RECOV` | `SCALP_BUY_LIMIT_RECOV` | 16270 | Buy-limit recovery (post-loss re-entry below market) |
| `SELL_LIMIT_RECOV` | `SCALP_SELL_LIMIT_RECOV` | 16473 | Sell-limit recovery (post-loss re-entry above market) |
| `PRE_TP1_RECOV` | `SCALP_PRE_TP1_RECOV_BUY` / `_SELL` | 16626 | Pre-TP1 emergency recovery (direction moves into `<DIR>` segment) |

### §3.3 Composed `<ZONE>_<ORDER_TYPE>` matrix (24 combinations)

| | KZ (killzone) | SK (Silver Knife) | OFF (off-session) |
|---|---|---|---|
| Market entry | `KZ_MKT` | `SK_MKT` | `OFF_MKT` |
| Limit L1 | `KZ_LIMIT` | `SK_LIMIT` | `OFF_LIMIT` |
| Limit L2 cascade | `KZ_LIMIT_L2` | `SK_LIMIT_L2` | `OFF_LIMIT_L2` |
| Buy-stop cascade | `KZ_BUY_STOP_CONT` | `SK_BUY_STOP_CONT` | `OFF_BUY_STOP_CONT` |
| Sell-stop cascade | `KZ_SELL_STOP_CONT` | `SK_SELL_STOP_CONT` | `OFF_SELL_STOP_CONT` |
| Buy-limit recovery | `KZ_BUY_LIMIT_RECOV` | `SK_BUY_LIMIT_RECOV` | `OFF_BUY_LIMIT_RECOV` |
| Sell-limit recovery | `KZ_SELL_LIMIT_RECOV` | `SK_SELL_LIMIT_RECOV` | `OFF_SELL_LIMIT_RECOV` |
| Pre-TP1 emergency recovery | `KZ_PRE_TP1_RECOV` | `SK_PRE_TP1_RECOV` | `OFF_PRE_TP1_RECOV` |

### §3.4 `<CAT>` — ICT entry category (4 codes — the "character of trade strategy")

| Code | Full canonical name | Description |
|---|---|---|
| `MSS_CONT` | MSS_CONTINUATION | Market Structure Shift + displacement; entry on retrace into FVG/OB |
| `OTE_RETR` | OTE_RETRACEMENT | Pullback to 62-79% fib in discount (BUY) / premium (SELL) zone |
| `LIQ_SWEEP` | LIQUIDITY_SWEEP_REVERSAL | Sweep of equal H/L followed by ChoCH; entry on first FVG retrace |
| `BRK_RETEST` | BREAKER_RETEST | OB traded through, retests as new S/R, with FVG confluence (Phase 3 — pending IctOrderBlock.mqh body) |

**Legacy setup transition**: until the M7-M9 folds ship, the EA's actual `setup_type` strings are still legacy (`BB_BREAKOUT`, `MOMENTUM_DUMP`, `ORB`, etc.). The ICT comment scheme is wired through future ICT-canonical entries first; legacy setups continue using the `SCALP_*` family per [§7 Rollout](#7-migration--rollout-strategy).

### §3.5 `<DIR>` — direction (2 codes)

| Code | Meaning |
|---|---|
| `B` | BUY |
| `S` | SELL |

### §3.6 `G<GROUP_ID>` — the elegant decoupled group ID

Per the §3a v2.7.131 review of `g_scalper_group_counter`. The group ID is independent from the EA's MagicNumber config and stable across MagicNumber reconfiguration.

| Range | Owner |
|---|---|
| `G1` – `G4999` | BRIDGE-issued (variable digit count) |
| `G5001` – `G9999` | EA-native scalper (4-digit, counter starts at 5000 per FORGE.mq5:173) |

The corresponding MT5 magic field is computed as `MagicNumber + group_id` (primary band), with cascade legs at `+20000` offset and pre-TP1 recovery at `+30009` offset. See FORGE.mq5:51-52 + 10766-10767 for the full magic-band scheme. Per v2.7.131 `SeedScalperGroupCounter()`, the counter recovers from broker state on EA reload to prevent collision.

### §3.7 `<TP_OR_LEG>` — TP stage or cascade/recovery leg counter

For PRIMARY entries: `TP1` | `TP2` | `TP3` | `TP4` (legacy code only emits TP1/TP2 today; TP3/TP4 emission is Phase B fix).

For CASCADE legs (BUY_STOP_CONT / SELL_STOP_CONT): `L1` | `L2` | `L3` | `L4`.

For RECOVERY legs (BUY_LIMIT_RECOV / SELL_LIMIT_RECOV / PRE_TP1_RECOV): `R1` | `R2` | `R3`.

### §3.8 `<KZ_DETAIL>` — killzone full detail (always emitted)

| Code | Full canonical | NY-local time | Description |
|---|---|---|---|
| `ASIA_KZ` | `ASIAN_KZ` | 20:00 – 00:00 | Asian session — accumulation phase, ranges form |
| `LDN_OPEN_KZ` | `LONDON_OPEN_KZ` | 02:00 – 05:00 | London Open — first liquidity grab |
| `NY_OPEN_KZ` | `NY_OPEN_KZ` | 07:00 – 10:00 | NY AM — primary directional move |
| `LDN_CL_KZ` | `LONDON_CLOSE_KZ` | 10:00 – 12:00 | London Close — bias hand-off |
| `NY_PM_KZ` | `NY_PM_KZ` | 13:30 – 16:00 | NY PM — reversals, profit-taking |
| `OFF` | (off-session) | everything else | Outside any killzone |

`<KZ_DETAIL>` is ALWAYS emitted — predictable 5-segment minimum. When `<ZONE>` = `OFF`, `<KZ_DETAIL>` = `OFF` (redundant by design, for parser predictability).

**Source-producer ↔ helper-consumer wiring:**

| Canonical label emitted by `ComputeCurrentKillzoneLabel()` (FORGE.mq5:7459-7466) | Stored in chokepoint state | Helper translates to comment code |
|---|---|---|
| `return "NY_OPEN_KZ"` (FORGE.mq5:7459) | `g_regime.killzone` | `IctComment.mqh:61` → `NY_OPEN_KZ` |
| `return "LONDON_OPEN_KZ"` (FORGE.mq5:7460) | `g_regime.killzone` | `IctComment.mqh:60` → `LDN_OPEN_KZ` |
| `return "LONDON_CLOSE_KZ"` (FORGE.mq5:7461) | `g_regime.killzone` | `IctComment.mqh:62` → `LDN_CL_KZ` |
| `return "NY_PM_KZ"` (FORGE.mq5:7464) | `g_regime.killzone` | `IctComment.mqh:63` → `NY_PM_KZ` |
| `return "ASIAN_KZ"` (FORGE.mq5:7465) | `g_regime.killzone` | `IctComment.mqh:59` → `ASIA_KZ` |
| `return ""` (off-session fall-through, FORGE.mq5:7466) | `g_regime.killzone` (empty) | `IctComment.mqh:64` fall-through → `OFF` |

The chokepoint produces the canonical label once per tick into `g_regime.killzone`. Comment builders pass `g_regime.killzone` directly into `Forge_BuildScalpComment()`, which calls `Forge_KillzoneDetailCode()` to produce the comment-segment code. No re-derivation, single source of truth.

### §3.9 `<CONV>` — conviction tag (1 char, the "character of trade quality")

Derived from the category-matched composite score (`mss_cont_score_<dir>` / `ote_retrace_score_<dir>` / `liq_sweep_rev_score_<dir>` populated by F-β.1 v2.7.130):

| Code | Composite score range | Meaning |
|---|---|---|
| `H` | 7 – 10 | High conviction |
| `M` | 4 – 6 | Medium conviction |
| `L` | 1 – 3 | Low conviction |
| `?` | no score available (legacy setup pre-M9 fold) | Unknown |

The composite score itself stays in the `SIGNALS` row; the comment carries only the bucketed conviction for at-a-glance reading.

### §3.10 `<SK_DETAIL>` — Silver Knife sub-window (optional 7th segment — only emitted when active)

| Code | Full canonical | NY-local time | Inside KZ |
|---|---|---|---|
| `LDN_SK` | `LONDON_SB` | 03:00 – 04:00 | LDN_OPEN_KZ |
| `AM_SK` | `AM_SB` | 10:00 – 11:00 | LDN_CL_KZ / NY_OPEN_KZ overlap |
| `PM_SK` | `PM_SB` | 14:00 – 15:00 | NY_PM_KZ |

Same dual-namespace pattern as `<ZONE>` SK vs canonical SB: comment uses `_SK` for compactness + operator vocabulary; SIGNALS column `silver_bullet` and atom names stay canonical `_SB`.

**Source-producer ↔ helper-consumer wiring:**

| Canonical label emitted by `ComputeCurrentSilverBulletLabel()` (FORGE.mq5:7474-7484) | Stored in chokepoint state | Helper translates to comment code |
|---|---|---|
| `return "LONDON_SB"` (FORGE.mq5:7481) | `g_regime.silver_bullet` | `IctComment.mqh:78` → `LDN_SK` |
| `return "AM_SB"` (FORGE.mq5:7482) | `g_regime.silver_bullet` | `IctComment.mqh:79` → `AM_SK` |
| `return "PM_SB"` (FORGE.mq5:7483) | `g_regime.silver_bullet` | `IctComment.mqh:80` → `PM_SK` |
| `return ""` (outside any SB window) | `g_regime.silver_bullet` (empty) | `IctComment.mqh:81` fall-through → `""` (segment omitted) |

Per-tick wire-up at FORGE.mq5:11547 (`g_regime.silver_bullet = ComputeCurrentSilverBulletLabel()`). Same single-source-of-truth pattern as killzone — chokepoint computes once, comment builders read `g_regime.silver_bullet` directly, no re-derivation in module code.

---

## §4 Worked examples (full ICT context)

| Comment | Reading |
|---|---|
| `KZ_MKT\|MSS_CONT_B\|G5001\|TP1\|LDN_OPEN_KZ\|H` | Killzone market entry, MSS Continuation BUY, group 5001, TP1, London Open KZ, **high conviction** |
| `SK_MKT\|OTE_RETR_S\|G5002\|TP2\|NY_PM_KZ\|H\|PM_SK` | **Silver Knife** market entry, OTE Retracement SELL, NY PM KZ + **PM Silver Knife**, high conviction |
| `OFF_MKT\|LIQ_SWEEP_B\|G5003\|TP1\|OFF\|L` | **Off-session** market entry, Liquidity Sweep BUY, off-session, low conviction — Mode B candidate to block |
| `KZ_BUY_STOP_CONT\|LIQ_SWEEP_B\|G5003\|L2\|LDN_CL_KZ\|H` | Cascade leg 2 of LIQ_SWEEP_B group 5003, London Close KZ, high conviction |
| `SK_BUY_LIMIT_RECOV\|MSS_CONT_B\|G5001\|R1\|LDN_OPEN_KZ\|H\|LDN_SK` | Recovery limit 1 fired during **London Silver Knife** — top-tier conviction window |
| `KZ_PRE_TP1_RECOV\|BRK_RETEST_S\|G5004\|R1\|NY_OPEN_KZ\|M` | Pre-TP1 emergency recovery of BRK_RETEST SELL, NY Open KZ, medium conviction |
| `OFF_LIMIT\|MSS_CONT_B\|G5005\|TP1\|OFF\|?` | Limit placed off-session for legacy setup with no ICT composite score |

---

## §5 Parser implementation notes

### §5.1 Splitting and field-position semantics

The comment is pure pipe-delimited — split on `|` and read fields by index:

| Index | Field | Required? |
|---|---|---|
| 0 | `<ZONE>_<ORDER_TYPE>` | always |
| 1 | `<CAT>_<DIR>` | always |
| 2 | `G<GROUP_ID>` | always (strip leading `G` before integer parse) |
| 3 | `<TP_OR_LEG>` | always |
| 4 | `<KZ_DETAIL>` | always (even when off-session, value is `OFF`) |
| 5 | `<CONV>` | always (`H` / `M` / `L` / `?`) |
| 6 | `<SK_DETAIL>` | optional — only present when Silver Knife active |

### §5.2 Parsing the zone-leading prefix

Field 0 is structured `<ZONE>_<ORDER_TYPE>`. The order types contain underscores (e.g. `BUY_STOP_CONT`), so naive `split('_', 1)` is wrong.

**Correct parse**: match against a fixed enum of 24 known prefixes. Pseudo-code:

```python
ZONE_PREFIXES = {"KZ", "SK", "OFF"}
for prefix in ZONE_PREFIXES:
    if field0.startswith(prefix + "_"):
        zone = prefix
        order_type = field0[len(prefix) + 1:]
        break
```

### §5.3 Parsing field 1 (CAT_DIR)

The 4 ICT category codes contain underscores too (`MSS_CONT`, `OTE_RETR`, `LIQ_SWEEP`, `BRK_RETEST`). Same enum-match approach:

```python
CATEGORIES = {"MSS_CONT", "OTE_RETR", "LIQ_SWEEP", "BRK_RETEST"}
for cat in CATEGORIES:
    if field1.startswith(cat + "_"):
        category = cat
        direction = field1[len(cat) + 1:]  # "B" or "S"
        break
```

### §5.4 Backward compatibility — legacy `SCALP_*` family

Scribe parser should accept BOTH the legacy and new shapes during rollout:

```python
if field0.startswith("SCALP"):
    # Legacy parse — apply pre-v2.7.131 rules
    ...
elif field0.startswith(("KZ_", "SK_", "OFF_")):
    # New zone-leading parse
    ...
else:
    log.warning(f"Unknown comment shape: {comment!r}")
```

---

## §6 Length budget

### §6.1 MT5 broker comment limit

Per WebSearch of [mql5.com docs](https://www.mql5.com/en/docs/constants/structures/mqltraderequest) (2026-05-16): **no explicit limit documented** on `MqlTradeRequest.comment`. Older MT4 forum-mod claims of 31 characters DO NOT apply to MT5. Empirical limit is broker-dependent (commonly 63+ characters per operator testing).

### §6.2 Comment-length verification table

Worst-case scenarios with current 4-digit EA-native group IDs (`Gxxxx`):

| Composition | Example | Length |
|---|---|---:|
| Shortest (off-session, low conviction, no SK) | `OFF_MKT\|MSS_CONT_B\|G5001\|TP1\|OFF\|L` | 31 |
| Median (KZ market, high conv, no SK) | `KZ_MKT\|OTE_RETR_S\|G5002\|TP2\|LDN_OPEN_KZ\|H` | 41 |
| KZ cascade with full TP4 stage | `KZ_BUY_STOP_CONT\|LIQ_SWEEP_B\|G5003\|L2\|LDN_CL_KZ\|H` | 51 |
| SK market with SK detail | `SK_MKT\|BRK_RETEST_S\|G5004\|TP4\|NY_PM_KZ\|H\|PM_SK` | 47 |
| **Worst case** (SK recovery limit + SK detail) | `SK_BUY_LIMIT_RECOV\|BRK_RETEST_B\|G5004\|R1\|LDN_OPEN_KZ\|H\|LDN_SK` | **63** |

Worst case 63 chars — at the upper edge of the empirical broker limit. If a broker truncates at 63, the trailing `LDN_SK` segment would be the casualty (acceptable — SK info is still recoverable from the `KZ_DETAIL` segment + the timestamp).

### §6.3 Mitigation if specific brokers truncate

If a deployment encounters comment truncation:
- Drop `<SK_DETAIL>` segment (info redundant with `<KZ_DETAIL>` + sim time)
- Drop `<CONV>` segment (recoverable from SIGNALS join)
- Compress ICT category codes further (`MSSC` / `OTER` / `LSWR` / `BRRT` — 4-char fixed)

These optimizations are deferred — implement only if a broker truncates in production.

---

## §7 Migration / Rollout strategy

### §7.1 Apply to all new trades — forget old trades (operator decision 2026-05-16)

- **All 11 comment-building sites in `ea/FORGE.mq5`** migrate to the new zone-leading scheme in a single ship. From the deployment forward, every new TRADE row carries a comment in the `<ZONE>_<ORDER_TYPE>|...` shape.
- **Legacy setup_type strings** (BB_BREAKOUT, MOMENTUM_DUMP, ORB, ASIA_CAPITULATION_BUY, etc. — all currently-active setups) still appear in the `<CAT>_<DIR>` segment AS-IS until the M7-M9 folds rename them to ICT-canonical names. The PREFIX migration does NOT wait for the fold — only the category-segment content evolves.
- **Old TRADES rows** keep their pre-migration `SCALP_*` comment strings — no backfill, no migration of historical data. Parsing tools should drop legacy-format support after rollout (one less code path).

### §7.2 Why this rollout (operator-selected)

- Single, clean ship → entire codebase consistent from day one
- No "two-format coexistence" cognitive overhead during M7-M9 fold work
- Scribe / dashboards / ATHENA queries update once, not piecemeal across multiple folds
- The legacy `SCALP_*` family becomes dead code immediately — single direction for the future

### §7.3 Legacy `<CAT>_<DIR>` segment content during transition

Legacy setup_types (pre-M7 fold) carry their current name in field 1 — direction is BAKED into some of them (e.g. `ASIA_CAPITULATION_BUY`) and SEPARATE in others (e.g. `BB_BREAKOUT` + direction passed as a parameter).

**Decision**: pass the canonical setup_type AS-IS into field 1, with direction appended only if the setup_type doesn't already encode it. The builder helper handles this via simple heuristic — if the setup_type already ends in `_BUY` / `_SELL`, don't double-suffix.

Examples during pre-M7 phase:
- BB_BREAKOUT setup, BUY direction → field 1 = `BB_BREAKOUT_B`
- ASIA_CAPITULATION_BUY setup (direction baked) → field 1 = `ASIA_CAPITULATION_BUY` (no suffix)
- Future MSS_CONTINUATION setup, BUY direction → field 1 = `MSS_CONT_B`

After M7-M9 folds complete, all field-1 values use the ICT 4-letter short form + 1-char direction (`MSS_CONT_B`, `LIQ_SWEEP_S`, etc.) and the heuristic-suffix branch is removed.

---

## §8 Implementation status

### §8.1 Shipped (v2.7.131 → v2.7.132)

- ✅ `ea/include/Forge/IctComment.mqh` — module scaffold (v2.7.131)
- ✅ Module includes wired via `#include <Forge\IctComment.mqh>` in FORGE.mq5
- ✅ **Full helper expansion (v2.7.132)** — `Forge_ZonePrefix`, `Forge_KillzoneDetailCode`, `Forge_SilverKnifeDetailCode`, `Forge_ConvictionLetter`, `Forge_AppendDirectionSuffix`, and the canonical `Forge_BuildScalpComment(order_type, setup_or_cat, direction, group_id, tp_or_leg, kz_label, sb_label, composite_score)` producer
- ✅ **Self-test on OnInit (v2.7.132)** — `Forge_IctComment_SelfTest()` emits 8 sample comments at EA boot
- ✅ **Glossary §11** — cross-referenced into this doc
- ✅ **`FORGE_SETUP_ICT_MAP.md §9` changelog** — ship entries logged
- ✅ **`Forge_OverrideTpOrLeg` (v2.7.137 R27)** — in-place `<tp_or_leg>` swap for `PlaceMarketBatch` per-leg labels; preserves the 6/7-segment shape

### §8.2 Pending

| Item | Scope |
|---|---|
| **Scribe parser** | Defer until M7 ships (first ICT setup actually fires) |
| **Phase B legacy fixup** | Backfill the 6 non-conforming legacy comment builders (cascade/recovery with missing SETUP_TYPE) — separate ship, NOT in this scope |

---

## §9 Changelog

- **2026-05-16** — Initial doc. Captures the v2.7.131 ICT comment design: zone-leading prefix (KZ / SK / OFF × 8 order types = 24 prefixes), 4 ICT category codes (MSS_CONT / OTE_RETR / LIQ_SWEEP / BRK_RETEST), 1-letter direction (B/S), elegant group ID scheme (Gxxxx), full TP1-TP4 / L1-L4 / R1-R3 stage labels, killzone detail (5 codes + OFF), 1-letter conviction tag (H/M/L/?) derived from composite score, optional Silver Knife detail (LDN_SK / AM_SK / PM_SK). Forward-only rollout — legacy SCALP_* family stays canonical until M7-M9 folds ship rename. Implementation status: helper module scaffolded in v2.7.131; full helper expansion + self-test pending. Length budget verified to 63 chars worst case (MT5 has no documented limit; broker-dependent, commonly 63+).

---

## §10 Cross-references

- **`docs/FORGE_SETUP_ICT_MAP.md §B.2`** — the 4 ICT entry categories (this doc's `<CAT>` codes mirror that taxonomy)
- **`docs/FORGE_SETUP_ICT_MAP.md §B.7.4`** — F-α killzone alignment ship (defined the 5 KZ + 3 SB windows this doc's `<KZ>` and `<SK>` codes encode)
- **`docs/FORGE_GLOSSARY.md §2`** — canonical ICT category short names
- **`ea/FORGE.mq5:51-52`** — magic number scheme that pairs with `G<GROUP_ID>` segment
- **`ea/FORGE.mq5:173`** — `g_scalper_group_counter` init (range-segments BRIDGE 1-4999 vs EA-native 5001-9999)
- **`ea/FORGE.mq5:16054`** (v2.7.131) — `SeedScalperGroupCounter()` — broker-state-recovery for the group_id counter
- **`ea/include/Forge/IctComment.mqh`** — implementation module (scaffold shipped v2.7.131, helper expansion pending)
- **`.claude/skills/forge-monitor/SKILL.md §I.5a`** — Google MQL5 docs before asserting platform facts (the rule that drove the empirical-verification of MT5 comment length)
