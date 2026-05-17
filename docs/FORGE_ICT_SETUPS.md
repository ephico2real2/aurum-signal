# FORGE ICT Setup Catalog — canonical post-M7 setup_type taxonomy

**Status**: canonical reference for the 4 ICT-canonical setup categories. Each row defines the new `setup_type` string used in SIGNALS / broker comments / code; the atom set (§B.8.2 weights); the key structural / time-series indicators that feed those atoms; and the legacy pre-ICT setups that fold into each via the `setup_subtype` column.

**Anchor specs**:
- `docs/FORGE_SETUP_ICT_MAP.md §B.2` — the 4 entry categories (formal definition)
- `docs/FORGE_SETUP_ICT_MAP.md §B.8.2` — per-category atom catalog with weights
- `docs/FORGE_SETUP_ICT_MAP.md §B.4` — M7-M9 fold spec (revised 2026-05-17 post consensus-gate audit)
- `docs/FORGE_GLOSSARY.md §2 + §3 + §4` — term definitions + atom catalog + composite scoring

**Mandate**: per `feedback_full_ict_alignment_mandate` + skill §I.14, every setup the EA fires must align with one of the 4 ICT-canonical categories. No bespoke names. The `setup_subtype` column preserves the originating legacy trigger for ablation studies per `§B.4`.

---

## §1 The 4 ICT-canonical setup categories — master mapping table

| # | New `setup_type` | Atom set (§B.8.2 weights, total=10) | Key indicators / structural inputs | Folded legacy `setup_subtype` values | Plain-English definition |
|---|---|---|---|---|---|
| **1** | `MSS_CONTINUATION_BUY` / `_SELL` | `atom_mss_confirmed`(3) + `atom_displacement_present`(2) + `atom_fvg_aligned`(2) + `atom_fvg_unfilled`(1) + `atom_killzone_favorable`(1) + `atom_htf_aligned`(1) | Swing pivot ring (`g_swing_highs/lows` in `IctStructure.mqh`); M5 ATR (for displacement gate, default ≥ 1.5×ATR); FVG ring (`g_fvg_ring`); killzone state (`g_regime.killzone` ∈ {LDN_OPEN, NY_OPEN}); H1/H4 trend (`g_eval_h1_trend`, `htf_label`) | `bb_breakout`, `gap_and_go`, `momentum_dump_composite`, `bb_squeeze`, `grinding_sell`, `ny_session_bearish_breakout_sell`, `inside_bar` (provisional) | Market Structure Shift confirmed by a displacement leg (≥1.5×ATR body); entry on retrace into the FVG/OB the impulse created. The 6-7 folded legacy setups all share the structural mechanic of "displacement creates entry zone." Legacy `momentum_dump` (v1) RETIRED alongside `ma_crossover` per operator decision 2026-05-17 — `momentum_dump_composite` is the atom-composed ICT-aligned successor; parallel validation done in v2.7.121-137. |
| **2** | `OTE_RETRACEMENT_BUY` / `_SELL` | `atom_pullback_in_ote`(3) + `atom_premium_discount_aligned`(2) + `atom_fvg_confluence`(2) + `atom_ob_confluence`(1) + `atom_killzone_favorable`(1) + `atom_htf_aligned`(1) | Swing pivot ring (for fib leg lookback 62-79%); dealing-range midpoint (premium/discount split); FVG ring; OB ring (`g_ob_ring` in `IctOrderBlock.mqh` — wired v2.7.136); any-killzone (`g_regime.killzone != ""`); htf trend | `bb_breakout_retest`, `flag_pennant` | Pullback to 62-79% fib retracement in discount (BUY) or premium (SELL) zone, with FVG/OB confluence. The OTE band IS where flag/pennant consolidation forms; retest of broken band IS the OTE entry. |
| **3** | `LIQUIDITY_SWEEP_REVERSAL_BUY` / `_SELL` | `atom_sweep_detected`(3) + `atom_sweep_wick_quality`(2) + `atom_choch_confirmed`(2) + `atom_fvg_on_reversal_leg`(2) + `atom_killzone_favorable`(1) | Equal H/L cluster detector (`g_ict_last_equal_highs_count/lows_count`); buy/sell-side sweep detector (`g_ict_last_liquidity_sweep_recent`); wick-quality scorer (`g_ict_last_sweep_rejection_score` — magnitude-tiered 0/1/2 per spec; **see R23 — currently binary**); ChoCH event counter (`g_ict_last_choch_buy_count/sell_count`); FVG ring; killzone (LDN_OPEN / NY_PM preferred) | `orb` | Sweep of equal highs/lows or session H/L (liquidity grab) followed by Change of Character; entry on first FVG retrace on the reversal leg. Session-open range breaks (ORB) ARE liquidity sweeps at IPDA open. |
| **4** | `BREAKER_RETEST_BUY` / `_SELL` | `atom_ob_broken`(3) + `atom_breaker_retest`(3) + `atom_fvg_confluence`(2) + `atom_killzone_favorable`(1) + `atom_htf_aligned`(1) | OB ring (`g_ob_ring` — Phase 3 v2.7.133); broken-state tracker (body close past extreme); retest tolerance × ATR; FVG ring; killzone; htf trend | (none — Phase 3 net-new setup category) | OB that was traded through (broken — body close past extreme) now retests as opposite-direction S/R; entry on retest tap with FVG confluence (the "Unicorn" pattern per ICT canon). Trigger for trend-reversal trades after liquidity sweeps. |
| **🗑** | `(RETIRED — do not migrate)` | n/a | n/a | `ma_crossover`, `momentum_dump` (v1 legacy) | (1) `ma_crossover`: lagging-indicator-based (EMA20×EMA50). ICT explicitly rejects moving averages and lagging oscillators as primary triggers. No ICT primitive expressed → does not fold. (2) `momentum_dump` (v1 legacy): superseded by atom-composed `momentum_dump_composite` (v2.7.121 promotion from `_TEST`). Parallel validation done; operator decision 2026-05-17 — commit to composite. Both removed in v2.7.137a tech-debt ship OR bundled with M7 code v2.7.138. |

---

## §2 Per-category detail

### §2.1 Category 1 — MSS_CONTINUATION

**ICT-canon definition** (per [innercircletrader.net](https://innercircletrader.net/) tutorials): a Market Structure Shift is a break of a confirmed swing high (bullish) or swing low (bearish) on close, accompanied by a displacement leg (large-bodied bar that leaves a Fair Value Gap within the next few candles). The entry is on the FIRST retrace back into the FVG/OB that the displacement leg created.

**Atom set (10 weight)**:
| Atom | Weight | Source |
|---|---|---|
| `atom_mss_confirmed` | 3 | `IctStructure.mqh::DetectBullishMSS / DetectBearishMSS` |
| `atom_displacement_present` | 2 | `g_eval_m5_velocity_5bar_signed ≥ 1.5×ATR` |
| `atom_fvg_aligned` | 2 | `Forge_GetActiveFVGAlignedWith()` |
| `atom_fvg_unfilled` | 1 | `g_fvg_ring[i].mitigated == false` |
| `atom_killzone_favorable` | 1 | `g_regime.killzone ∈ {LDN_OPEN, NY_OPEN}` (⚠ spec says NY_AM — see R22 drift) |
| `atom_htf_aligned` | 1 | `g_regime.htf_label` matches MSS direction |

**Folded legacy setups (consensus-gate passed)**: 7 subtypes + 1 provisional
- `bb_breakout` — Bollinger band envelope breakout (the breakout produces the displacement leg)
- `gap_and_go` — Open-gap directional continuation (gap = displacement)
- `momentum_dump` — Fast directional impulse (canonical M5 displacement)
- `momentum_dump_composite` — Atom-composed variant of momentum_dump
- `bb_squeeze` — Low-vol consolidation → expansion (accumulation→expansion phase = displacement)
- `grinding_sell` — Multi-bar slow descending impulse (slow-MSS variant)
- `ny_session_bearish_breakout_sell` — NY-session bearish breakout (session-open displacement)
- `inside_bar` (**provisional** — operator call: keep or retire) — Inside bar breakout

**ICT canon citations**:
- [innercircletrader.net OTE pattern](https://innercircletrader.net/tutorials/ict-optimal-trade-entry-ote-pattern/) — for the post-MSS retracement entry
- [innercircletrader.net bull-flag](https://innercircletrader.net/tutorials/bull-flag-pattern-trading-strategy/) — confirms displacement = BOS pole, retracement = entry zone

### §2.2 Category 2 — OTE_RETRACEMENT

**ICT-canon definition** (per [innercircletrader.net OTE](https://innercircletrader.net/tutorials/ict-optimal-trade-entry-ote-pattern/)): Optimal Trade Entry is the fibonacci retracement zone 62-79% (precise level 70.5%) of an established leg, used for joining a continuation at the retracement OR fading a reversal at the tap of a higher-timeframe PD Array.

**Atom set (10 weight)**:
| Atom | Weight | Source |
|---|---|---|
| `atom_pullback_in_ote` | 3 | fib retracement 62-79% of prior leg |
| `atom_premium_discount_aligned` | 2 | dealing range midpoint check |
| `atom_fvg_confluence` | 2 | FVG in OTE zone |
| `atom_ob_confluence` | 1 | `Forge_HasOBConfluence()` (Phase 3 v2.7.136 wire) |
| `atom_killzone_favorable` | 1 | `g_regime.killzone != ""` (any KZ) |
| `atom_htf_aligned` | 1 | trend agreement |

**Folded legacy setups**: 2 subtypes (M8 reclassification per consensus gate)
- `bb_breakout_retest` — Re-entry on retest of broken Bollinger band (retest IS retracement-into-zone)
- `flag_pennant` — Bull/bear flag chart pattern (flag IS the OTE retracement; pole = displacement)

### §2.3 Category 3 — LIQUIDITY_SWEEP_REVERSAL

**ICT-canon definition** (per ICT/SMC literature): a Liquidity Sweep is a wick beyond a recent equal-high/low cluster or session high/low followed by a body close back inside the range — "stop hunt then reversal." Confirmation requires a Change of Character (ChoCH) — a counter-direction structural break — on the bars following the sweep.

**Atom set (10 weight)**:
| Atom | Weight | Source |
|---|---|---|
| `atom_sweep_detected` | 3 | `IctLiquidity.mqh::DetectBuy/SellSideLiquiditySweep` |
| `atom_sweep_wick_quality` | 2 | `g_ict_last_sweep_wick_atr_mult` magnitude tier 0/1/2 (⚠ currently binary — see R23) |
| `atom_choch_confirmed` | 2 | `IctLiquidity.mqh::DetectBullish/BearishChOCh` |
| `atom_fvg_on_reversal_leg` | 2 | FVG opposite to sweep direction |
| `atom_killzone_favorable` | 1 | `g_regime.killzone ∈ {LDN_OPEN, NY_PM}` (⚠ code uses LDN_CLOSE — see R22) |

**Folded legacy setups**: 1 subtype (M9 reclassification per consensus gate)
- `orb` — Opening Range Breakout (session opening range = IPDA liquidity zone; break = sweep)

### §2.4 Category 4 — BREAKER_RETEST

**ICT-canon definition** (per [innercircletrader.net breaker-block](https://innercircletrader.net/tutorials/ict-breaker-block-trading/)): a Breaker Block is a failed Order Block — price body-closed past the OB extreme, the OB now flips to act as opposite-direction support/resistance on retest. The Breaker is the trigger for trend-reversal trades after liquidity sweeps.

**Atom set (10 weight)**:
| Atom | Weight | Source |
|---|---|---|
| `atom_ob_broken` | 3 | `Forge_UpdateOBBrokenState()` — body close past OB extreme |
| `atom_breaker_retest` | 3 | `Forge_UpdateBreakerRetestState()` — price within 0.5×ATR of broken level |
| `atom_fvg_confluence` | 2 | `Forge_UpdateBreakerFVGConfluence()` — aligned FVG near retest |
| `atom_killzone_favorable` | 1 | any active KZ |
| `atom_htf_aligned` | 1 | trend agreement |

**Folded legacy setups**: none (Phase 3 net-new category, no pre-ICT setup mapped to this primitive).

---

## §3 Subtype identifier catalog (`setup_subtype` column values)

The `setup_subtype` TEXT column preserves original-trigger identity for ablation studies. Format: lower_snake_case matching the pre-fold codename minus `_ENABLED` suffix.

| Subtype | Maps to setup_type | Direction | Source line (pre-M7) |
|---|---|---|---|
| `bb_breakout` | MSS_CONTINUATION_{BUY,SELL} | BOTH | FORGE.mq5:12826 (BUY), 13181 (SELL) |
| `bb_breakout_retest` | OTE_RETRACEMENT_{BUY,SELL} | BOTH | FORGE.mq5:12818, 13173 (variant) |
| `bb_pullback_scalp` | OTE_RETRACEMENT_{BUY,SELL} (M8 fold; **R33 retire candidate post-validation**) | BOTH | FORGE.mq5:12279 (BUY), 12373 (SELL) |
| `gap_and_go` | MSS_CONTINUATION_{BUY,SELL} | BOTH | FORGE.mq5:14169 |
| `momentum_dump` | **RETIRED** (no fold — superseded) | — | (delete 3 sites at FORGE.mq5:13259, 13439, 13572) |
| `momentum_dump_composite` | MSS_CONTINUATION_{BUY,SELL} | BOTH | FORGE.mq5:13600 |
| `bb_squeeze` | MSS_CONTINUATION_{BUY,SELL} | BOTH | FORGE.mq5:14100 |
| `flag_pennant` | OTE_RETRACEMENT_{BUY,SELL} | BOTH | FORGE.mq5:14481 |
| `inside_bar` | MSS_CONTINUATION_{BUY,SELL} (provisional) | BOTH | FORGE.mq5:14064 |
| `grinding_sell` | MSS_CONTINUATION_SELL | SELL-only | FORGE.mq5:12511 |
| `ny_session_bearish_breakout_sell` | MSS_CONTINUATION_SELL | SELL-only | FORGE.mq5:13729 |
| `orb` | LIQUIDITY_SWEEP_REVERSAL_{BUY,SELL} | BOTH | FORGE.mq5:14136 |
| `ma_crossover` | **RETIRED** (no fold) | — | (deleted in v2.7.137a) |

---

## §4 Term definitions (linked to glossary)

All ICT terms in this catalog have canonical definitions in `docs/FORGE_GLOSSARY.md`. Quick reference (read the glossary for full detail):

| Term | Glossary section | One-liner |
|---|---|---|
| **MSS** (Market Structure Shift) | [§2 + §3](FORGE_GLOSSARY.md#§2) | Break of a confirmed swing high/low on close, with displacement |
| **Displacement** | §3 | Large-bodied candle (body ≥ 1.5×ATR) that creates an FVG |
| **FVG** (Fair Value Gap) | §3 | 3-bar imbalance where bar i-1 doesn't overlap bar i+1 |
| **OB** (Order Block) | §3 (v2.7.133) | Last opposite-direction candle before a displacement leg |
| **Breaker Block** | §3 (v2.7.133) | Failed OB — body close past extreme; flips to opposite S/R |
| **OTE** (Optimal Trade Entry) | §2 | 62-79% fib retracement zone (precise = 70.5%) |
| **ChoCH** (Change of Character) | §3 | Counter-direction structural break confirming a sweep reversal |
| **Liquidity Sweep** | §3 | Wick beyond equal-H/L cluster or session extreme + body close back |
| **Killzone** (KZ) | §2 + [§B.2](FORGE_SETUP_ICT_MAP.md#§B2) | 5 NY-anchored time windows where institutional flow concentrates |
| **Silver Bullet / Silver Knife** (SB / SK) | §2 + §B.2 | 60-min hyper-concentrated FVG-entry windows inside killzones |
| **IPDA opening range** | (research-citations) | Initial Production Distribution Algorithm session-open zone |
| **PD-array** | (Phase 3c — deferred) | Premium/Discount array of OB ∩ FVG ∩ Breaker ∩ RDRB ∩ liquidity |

---

## §5 Cross-references

- `docs/FORGE_SETUP_ICT_MAP.md` — master ICT-alignment doc (this catalog distills §B.2 + §B.8.2 into a single setup-mapping table)
- `docs/FORGE_GLOSSARY.md` — canonical term + atom + composite definitions
- `docs/FORGE_ICT_COMMENT_CODES.md` — broker-comment scheme (this catalog's `setup_type` values feed the `<CAT>_<DIR>` segment)
- `refinement-ideas/M7-design/2026-05-17_m7-mss-continuation-fold.md` — M7 fold design + consensus-gate audit that drove this catalog
- `refinement-ideas/improvement-recommendations/INDEX.md` — open improvements (R22 KZ-spec drift, R23 wick-quality tier, R24 OB ring direction, R27 PlaceMarketBatch comment bug)
- `.claude/skills/forge-monitor/SKILL.md §I.14` — full ICT alignment mandate
- `.claude/skills/forge-monitor/SKILL.md §I.15` — consensus gate for agent findings

---

## §6 Changelog

- **2026-05-17** — Initial catalog. Distills `FORGE_SETUP_ICT_MAP.md §B.2 + §B.4 + §B.8.2` into single setup-mapping table covering the 4 ICT-canonical categories, their atom sets, the indicators their atoms read, and the legacy pre-ICT setups that fold into each via `setup_subtype`. Revised post consensus-gate audit (skill §I.15): MA_CROSSOVER retires (not in ICT toolkit per [chartinglens.com](https://chartinglens.com/blog/ict-trading-strategy-guide) + [eplanetbrokers.com](https://eplanetbrokers.com/training/ict-trading-strategy-explained)); BB_BREAKOUT_RETEST + FLAG_PENNANT move to Cat 2 (OTE — flag IS retracement per [innercircletrader.net bull-flag](https://innercircletrader.net/tutorials/bull-flag-pattern-trading-strategy/)); ORB moves to Cat 3 (IPDA opening-range break = liquidity sweep).
- **2026-05-17** — **Cat 1 fold shrinks from 7 → 6 setups** per operator decision: `momentum_dump` (v1 legacy) joins the RETIRE bucket alongside `ma_crossover`. Reason: `momentum_dump_composite` is the atom-composed ICT-aligned successor (promoted from `_TEST` in v2.7.121 per FORGE.mq5:1215 comment). Parallel validation between v1 and composite is done — commit to the composite, retire the legacy. Aligns with skill §I.8 plug-and-play principle #1 (atom-decomposed = pure-function evaluators). EA-side delete: 3 fire sites at FORGE.mq5:13259, 13439, 13572 + the `FORGE_DUMP_*` env knobs the composite doesn't reuse. No migration to `setup_subtype` (composite preserves displacement semantics independently). Lands as v2.7.137a tech-debt sub-ship or bundled with M7 code v2.7.138.
- **2026-05-17** — **Cat 2 retire-candidate annotation: `bb_pullback_scalp` (R33)** — operator decision (Option B response to canonical-validity question): the BB-band detector is non-canonical (Bollinger Bands not in ICT toolkit, same class as MA crossovers). Canonical replacement: `atom_pullback_in_ote` (fib 62-79% MSS swing leg) — already wired in `IctScoring.mqh` since v2.7.123 Mode A. Two-phase plan: (1) M8 ship folds `bb_pullback_scalp` to `OTE_RETRACEMENT_BUY/SELL` setup_type with `setup_subtype = "bb_pullback_scalp"` preserved (Option A — no logic change); (2) post-M8 validation compares atom-composed vs bespoke fire rates; when canonical detector confirms equivalent-or-better, retire `bb_pullback_scalp` entirely (delete sites at FORGE.mq5:12279 BUY + 12373 SELL + `g_sc.pullback_scalp_*` knobs). Same "parallel validation → operator decision" pattern as MOMENTUM_DUMP v1 → composite retirement. Retire ships in v2.7.140+ (post-M8 OTE atom validation).
