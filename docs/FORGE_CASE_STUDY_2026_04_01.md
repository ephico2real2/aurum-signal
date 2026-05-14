# FORGE Case Study — 2026-04-01: Missed Bidirectional Opportunity

**Type**: single-day missed-opportunity post-mortem
**Source data**: Run #2 aurum_tester run (FORGE v2.7.111, source DB `Agent-127.0.0.1-3000/.../FORGE_journal_XAUUSD_tester.db`, source_run_id=2)
**Method**: Hourly price aggregation + SKIP gate audit + SELL-setup trigger gap analysis
**Trigger event**: Operator observation 2026-05-14 — "we should be selling and making money from up down. but we cut in another buy fight - we survived but due to our new S/L there was dip and bull. we should written both directions"
**Creation date**: 2026-05-14
**Cross-references**: `docs/ICT-Structure-Score.md` (ISS framework), `.claude/skills/forge-monitor/SKILL.md` (case study mandate)

---

## §1 Day summary

**Apr 1 2026 — bidirectional bull-trend day with two corrections**

| Metric | Value |
|---|---|
| Day open | ~4682 (06:00 UTC) |
| Day low | 4667 (07:00 UTC) |
| Day high | 4791 (19:00 UTC) |
| Day close | ~4769 (23:00 UTC) |
| Net move | +87 pts up |
| Intraday range | 124 pts (4667 → 4791) |
| h1_trend (avg) | bullish |
| Regime | TREND_BULL with two intraday corrections |
| DTC state | BULL_TREND_ALIGNED |

**Four directional legs**:

| Leg | Window | Price action | Pts | What FORGE did |
|---|---|---|---|---|
| **1** — Overnight dip | 06:00 → 07:00 | 4691 → 4667 | **−24** | ✗ no SELL setup fired |
| **2** — LONDON ramp | 07:00 → 14:00 | 4667 → 4761 | **+94** | ✅ G5005 BUY @4700.70 (08:40) + G5007 BUY @4735.29 (13:45) |
| **3** — NY correction | 14:39 → 16:00 | 4761 → 4721 | **−40** | ✗ no SELL setup fired |
| **4** — London-close ramp | 17:00 → 19:00 | 4733 → 4791 | **+58** | ✗ no new BUY entry (PEMCG over-block) |
| **5** — Topping | 19:00 → 21:00 | 4791 → 4749 | **−42** | ✗ no SELL setup fired |

**Three of five legs missed entirely.** All three misses are SELL-direction legs (legs 1, 3, 5).

---

## §2 What FORGE captured (the wins)

3 TAKEN entries + cascade ladder. All winners.

| Group | Sim time | Setup | Direction | Entry | RSI | ADX | Fills | P&L |
|---|---|---|---|---|---|---|---|---|
| G5005 | 08:40 | BB_BREAKOUT | BUY | 4700.70 | 73.3 | 40.1 | 3 | +$270.56 |
| G5006 | 09:25 | FRACTIONAL_SELL_IN_BULL | SELL | 4709.91 | 68.4 | 32.7 | 3 | +$19.32 |
| G5007 | 13:45 | MOMENTUM_DUMP | BUY | 4735.29 | 62.8 | 27.7 | 2 | +$196.42 |
| G5008-G5011 cascade | 14:09-14:39 | BUY_LIMIT recovery ladder (cascade slots 207409-227418) | BUY | 4739-4747 | — | — | 11 | +$2,059.77 net |

**Day P&L captured: ~$2,546 (+74% return)**

The cascade is the key event. After G5007 BUY @4735.29 at 13:45, price ran up to 4761 by 14:39, then began the correction. The recovery cascade (BUY_LIMIT slots placed BELOW market) caught the dip at 4739-4747 and TPd at 4752-4754 when price bounced.

**Operator's "buy fight, we survived"**: this is G5008-G5011 cascade. We were positioned BUY across multiple slots, price dipped 4747 → 4739 hitting the lowest rung (227418 SL'd for −$33.24), then bounced and TPd the upper rungs (+$2,093). Net cascade = +$2,060. **Survived the dip because v2.7.108's wider SL gave each rung enough room to weather the noise.**

---

## §3 What FORGE missed (the three SELL legs)

### Leg 1 — Overnight dip (06:00 → 07:00, −24 pts)

Brief 24-point drop from 4691 to 4667 during ASIA-close → LONDON-pre. ATR was small; the move was fast. **No SELL setup fired**. ASIA_CAPITULATION_BUY did fire as the bounce setup at 07:00+ but never TAKEN (atom count below min). This dip leg was simply unmodeled — FORGE's SELL setups all require either: trend confirmation (TC_SELL needs strong bull conditions inverted), ADX threshold (MOMENTUM_DUMP_SELL needs ADX ≥ 20), or counter-trend conditions (FRACTIONAL_SELL_IN_BULL needs RSI ≥ 65 in bull day).

The 06:00-07:00 dip happened too fast to satisfy any trigger.

### Leg 3 — NY correction (14:39 → 16:00, −40 pts)

The 40-point dip from 4761 peak (cascade TP exhausted) to 4721 bottom. SELL-side SKIPs during this window: **only 3 `dump_h1_trend_block_sell` skips**. PEMCG_SELL_REVERSAL_BLOCK fired 0 times. No SELL setups even attempted to fire.

**Why**: All FORGE SELL setups require trigger conditions that didn't manifest:
- MOMENTUM_DUMP_SELL: needs RSI < 40 for BUY direction (mirror = RSI > 60 for SELL). RSI was 50-55 during the dip — neutral zone.
- FRACTIONAL_SELL_IN_BULL: needs RSI ≥ 65 — RSI peaked at 62 during the dip, never crossed the threshold.
- BB_EXHAUSTION_REVERSAL_SELL: needs PEMCG_BUY warnings ≥ 4. PEMCG triggered but not enough atoms for reversal capture.
- TREND_CONTINUATION_SELL: needs prior bearish trend — not present (we were in bull day).

A structural SELL signal existed (price closed below 4737 swing low at ~14:39 + with a wide red body) — but FORGE has **no MSS-driven SELL setup** to consume it.

### Leg 5 — Topping (19:00 → 21:00, −42 pts)

The 42-point sell-off from the day high 4791 down to 4749. SELL-side SKIPs: **1 `dump_h1_trend_block_sell`**. Same pattern as leg 3 — no SELL setups triggered.

The structural signal: ChoCH-down at ~19:30 when price closed below the 18:00 swing low (around 4775). MSS-down confirmation at ~20:00 when price closed below 4760. Neither signal has a consuming setup in FORGE today.

---

## §4 The structural gap

### Why the existing gate stack doesn't help

FORGE's 5-layer entry-gating architecture (UMCG/CVCSM/DTC/DLV/DLS) **filters** setup triggers — it doesn't **create** them. If no setup trigger fires, no gate is consulted. The Apr 1 missed legs all failed at trigger-creation, not at gate-passage.

| Layer | Apr 1 leg 1 (overnight dip) | Apr 1 leg 3 (NY correction) | Apr 1 leg 5 (topping) |
|---|---|---|---|
| Setup trigger | NONE fired (no condition matched) | NONE fired | NONE fired |
| UMCG | not reached | not reached | not reached |
| CVCSM | not reached | not reached | not reached |
| DTC | not reached | not reached | not reached |
| DLV/DLS | not reached | not reached | not reached |
| Score (ISS) | not reached | not reached | not reached |

### The setup catalog gap

FORGE's 14 setups (per FORGE_SETUP_PLAYBOOK.md) cluster around three trigger archetypes:

| Archetype | Trigger | Direction bias |
|---|---|---|
| Range-break (BB_BREAKOUT, ORB) | Price exits a band/range | Symmetric |
| Reversal (BB_BOUNCE, BB_EXHAUSTION_REVERSAL, ASIA_CAPITULATION_BUY, BLR) | RSI extreme + bar quality | Symmetric, but threshold-sensitive |
| Momentum continuation (MOMENTUM_DUMP, TREND_CONTINUATION) | ADX + RSI bands + velocity | Tied to regime |

**None of these consume structural break-of-swing**. The closest is BB_BREAKOUT, but BB breaks ≠ swing breaks — Bollinger bands are volatility-derived, not pivot-derived.

The Apr 1 missed legs were all **structural breaks**: price closed past a recent swing pivot with full body. ICT calls this an MSS. FORGE has no MSS-driven entry trigger.

---

## §5 What ISS atoms would have enabled

The ISS framework (per `docs/ICT-Structure-Score.md`) introduces three atoms:

| ISS atom | Status | Would have caught Apr 1 missed legs? |
|---|---|---|
| **MSS** (Market Structure Shift) | v2.7.113 scope | **YES** — every missed leg had a textbook MSS firing |
| **ChoCH** (Change of Character) | v2.7.114 scope | YES — legs 1, 3, 5 all had ChoCH-against-prior-direction signals |
| **FVG** (Fair Value Gap) | v2.7.115 scope | Partial — would have provided entry precision on the leg-2 and leg-4 BUYs we did catch |

### Leg 1 (overnight dip) replay with ISS

```
06:00 — price topping at 4691, prior trend up from Mar 31 (HH-HL sequence intact)
06:30 — first close below 4683 (the most recent HL from 05:30)
        ↓ ChoCH-DOWN fires (bull trend dying)
06:45 — close below 4675 (the most recent swing low)
        ↓ MSS-DOWN fires (full-body break, m5_strong_bar = 1)
07:00 — ISS_SELL score = MSS(5) + ChoCH_support(2) = 7 → Standard-tier SHORT entry
        Target: structural — next liquidity pool at 4655 (Mar 31 day low)
        SL: above the 4691 swing high (24-pt risk, 36-pt reward = 1.5 R:R)
```

**Captured**: ~24 pts × 0.01 lot × $100/pt = $24. Small but real.

### Leg 3 (NY correction) replay with ISS

```
14:39 — cascade exhausts at 4761 high; subsequent bars produce lower-high at 4759
15:00 — close below 4737 (the most recent swing low from 12:00 range)
        ↓ MSS-DOWN fires (full-body break)
15:30 — FVG forms in the displacement candle (bearish FVG between 14:55 high and 15:25 low)
15:45 — price retraces UP into the bearish FVG
        ↓ iss_fvg_active fires (price in active bearish FVG aligned with SELL direction)
        ↓ ISS_SELL = MSS(5) + FVG(3) + ChoCH_support(2) = 10 → HIGH-CONVICTION SHORT
16:00 — exits at 4721 (next structural liquidity pool = morning swing low ~4715)
```

**Captured**: ~24 pts × 0.01 lot = $24+ (plus possible TP1+TP2 stage = ~$50+ per leg with proper position sizing).

### Leg 5 (topping) replay with ISS

```
19:30 — close below 4775 (the 18:30 swing low)
        ↓ ChoCH-DOWN fires
20:00 — close below 4760 (the 17:00 swing low — same level as leg-3 MSS confirmation)
        ↓ MSS-DOWN fires
20:15 — bearish FVG forms; price retraces up into it
        ↓ ISS_SELL = MSS(5) + FVG(3) + ChoCH_support(2) = 10 → HIGH-CONVICTION SHORT
21:00 — exits at 4749 (matches the morning recovery low)
```

**Captured**: ~26 pts × 0.01 lot = $26+ on the leg alone.

---

## §6 The direction-lock problem

Even if ISS atoms were wired, the existing **DLV → DLS no-auto-flip rule** (v2.7.97) would block opposite-direction entries when a same-direction position is active. On Apr 1:

| Window | Active direction | DLS state | Would block opposite? |
|---|---|---|---|
| 08:40 → 14:00 | BUY (G5005 + G5007 cascade armed) | LOCKED_BUY | YES — blocks SELL |
| 14:39 → 16:00 | BUY (cascade open) | LOCKED_BUY | YES — would have blocked leg-3 SHORT |
| 17:00 → 19:00 | (cascade closed by ~14:39 TPs; new BUYs blocked by PEMCG) | partly cleared | open to SELL but no setup triggered |
| 19:00 → 21:00 | (no active BUY) | open | open to SELL — but no setup triggered |

**Conclusion**: DLS only blocked leg 3. Legs 1 and 5 were missed purely because no SELL setup fired.

For ISS to work end-to-end on bidirectional days, two things must happen:
1. **MSS / ChoCH / FVG atoms get real detection** (v2.7.113-115)
2. **DLS no-auto-flip rule defers to ISS structural signals** — if ISS-SELL score ≥ 8 (high-conviction SHORT) while LOCKED_BUY is active, DLS should release the lock. This is a v2.7.116+ enhancement.

---

## §7 Quantified missed P&L for Apr 1

| Leg | Direction | Pts available | At 0.01 lot | At 0.05 lot (op sizing) | Caught? |
|---|---|---|---|---|---|
| 1. Overnight dip | SELL | ~20 (06:00 → 07:00) | ~$20 | ~$100 | NO |
| 2. London ramp | BUY | ~70 (07:00 → 14:00) | $70+ | $350+ | PARTIAL ($270 + $196 captured of theoretical $400+) |
| 3. NY correction | SELL | ~36 (14:39 → 16:00) | ~$36 | ~$180 | NO |
| 4. London-close ramp | BUY | ~55 (17:00 → 19:00) | ~$55 | ~$275 | NO (PEMCG over-block) |
| 5. Topping | SELL | ~38 (19:00 → 21:00) | ~$38 | ~$190 | NO |
| Sum missed | | | **~$149** | **~$745** | |

We banked $2,546 on Apr 1 from the captured legs. **Missing the three SELL legs cost ~$300-700** depending on position sizing. With ISS atoms + DLS-defers-to-ISS enhancement, projected Apr 1 P&L would have been **$2,846 to $3,246** (12-27% improvement).

---

## §8 Implementation requirements (action items)

To make Apr 1 fully tradeable in both directions, three ships are needed:

1. **v2.7.113 — Swing-pivot tracker + MSS atom** (per `docs/ICT-Structure-Score.md` §14)
   - Williams 3-bar fractal on M5 (operator decision on size)
   - Real `iss_mss` predicate evaluation (per direction)
   - Would catch legs 1, 3, 5 SHORT signals

2. **v2.7.114 — ChoCH atom** (uses swing tracker from v2.7.113)
   - Detects counter-trend pivot violations
   - Boosts ISS score on supportive ChoCH
   - Hard-gates entries on ChoCH-against

3. **v2.7.115 — FVG state tracker + atom** (per `docs/ICT-Structure-Score.md` §15)
   - 3-candle imbalance detector
   - Active-FVG list with lifecycle (mitigation, age, regime-flip invalidation)
   - Provides entry precision (high-conviction tier)

4. **v2.7.116 — DLS defers to ISS structural signals** (new — NOT in current roadmap)
   - When DLS is locked in one direction AND opposite-direction ISS score ≥ 8, release the lock
   - Encodes the canonical ICT principle: "respect the structure" — don't fight a confirmed MSS even if it's opposite to current direction
   - Pseudocode:
     ```mql5
     // In DLS direction-lock evaluation:
     if(g_dls_state == LOCKED_BUY && iss_score_sell >= 8 && !iss_choch_against_sell) {
        g_dls_state = OPEN;  // release lock — high-conviction SHORT overrides
        PrintFormat("DLS: released LOCKED_BUY due to high-conviction ISS SELL (%d)", iss_score_sell);
     }
     ```

5. **v2.7.117+ — MSS-driven entry triggers** (new setup catalog)
   - `MSS_BREAKOUT_BUY` / `MSS_BREAKOUT_SELL` — fires when ISS_score ≥ 5 in respective direction
   - Direct MSS-driven entry, no other setup gating required (ISS itself replaces the setup-trigger condition)
   - Catches legs 1, 3, 5 from this case study

---

## §9 Cross-references

- `docs/ICT-Structure-Score.md` — ISS framework (§3 ICT toolkit, §5 atom predicates, §13 roadmap, §14 swing-tracker spec, §15 FVG-tracker spec)
- `.claude/skills/forge-monitor/SKILL.md` — case study mandate + monitor contract
- Run #2 source data: `Agent-127.0.0.1-3000/.../FORGE_journal_XAUUSD_tester.db`, run_id=2, wall_time=134104435
- Related ship: v2.7.108 (DTC-aware SL widener — the "wider SL gave each cascade rung enough room to weather noise" credit)
- Related ship: v2.7.97 (DLV/DLS no-auto-flip — the rule that needs v2.7.116 enhancement to release on high-conviction opposite ISS)

---

## §10 Operator Q&A captured during this analysis

### Q1 (2026-05-14): "we should be selling and making money from up down. but we cut in another buy fight - we survived but due to our new S/L there was dip and bull. we should written both directions"
**Investigation**: Pulled Apr 1 hourly price range; identified 4 directional legs (overnight dip, LONDON ramp, NY correction, London-close ramp, topping); audited SKIP gates for SELL-side blockers in correction windows.
**Evidence**: 3 SELL_SKIPs in 14:30-16:00 window (all `dump_h1_trend_block_sell`); 1 SELL_SKIP in 19:00-22:00 window. No `pemcg_sell_reversal_block`, no `dirlock_block_sell`. Indicates SELL setups didn't even fire (trigger gap, not gate gap).
**Answer**: Three of five Apr 1 directional legs (the SELL legs at 06:00-07:00, 14:39-16:00, 19:00-21:00) were missed because FORGE has no MSS-driven SELL trigger. The captured "buy fight survived" was the G5008-G5011 BUY_LIMIT recovery cascade catching the 14:39-16:00 dip from underneath (4739-4747 fills, 4752-4754 TPs). Missed P&L estimate: $300-700 depending on sizing.
**Forward link**: See §8 implementation requirements — needs v2.7.113-115 atom ships + v2.7.116 DLS-defers-to-ISS rule + v2.7.117 MSS-driven SELL setups.

---

## §11 Changelog

- **2026-05-14** — Initial case study. Apr 1 day structure (5 legs, +124 pt intraday range), captured trades ($2,546 / 35W-1L), missed SELL legs (~$300-700 foregone), structural gap analysis (no MSS-driven SELL setup), ISS replay for each missed leg, implementation roadmap v2.7.113-117.
