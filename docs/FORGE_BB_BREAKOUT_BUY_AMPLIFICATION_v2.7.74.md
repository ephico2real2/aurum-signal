# BB_BREAKOUT BUY — Amplification Chain (v2.7.74)

**Shipped**: 2026-05-13 (v2.7.74)
**Status**: Compiled, ready for tester validation
**Context**: Run 30 (v2.7.70) revealed that BB_BREAKOUT BUYs banked TP1 too quickly and missed
60+pt NY rallies. TP3 staging infrastructure exists since v2.7.27 but was never firing because
TP2 distance (1.5×ATR) was rarely reached on M5 scalps. v2.7.74 fixes the geometry AND adds
conviction-aware leg amplification so high-quality setups deploy more firepower.

## The complete chain

```
BB_BREAKOUT BUY trigger fires
       │
       ▼
v2.7.74 conviction check (6 atoms):
  ✓ (price − bb_upper) / ATR ≥ 0.5    (strong impulse — not a fake-touch breakout)
  ✓ (price − VWAP) / ATR ≤ 1.5         (within institutional value zone, not overextended)
  ✓ RSI ∈ [55, 70]                     (sweet spot — momentum confirmed, room to grow)
  ✓ M15 ADX ≥ 20                       (M15 trend confirms momentum)
  ✓ signed velocity > 0                (M5 5-bar displacement still climbing)
  ✓ BOS direction = +1                 (bullish break of structure on M5)
       │
   4+ atoms aligned?
       │
   ┌───┴────────────────────────┐
  YES                          NO
   │                            │
   ▼                            ▼
HIGH CONVICTION:           STANDARD:
- Fire 5 legs immediate    - Fire 3 legs (existing)
- TP1 closes 50% only      - TP1 closes 70%
- 50% rides into runner    - 30% rides into runner
   │                            │
   └────────┬───────────────────┘
            ▼
TP1 hits at +0.5×ATR (~2.5pts) — partial close
       │
       ▼
Remaining position rides
       │
       ▼
TP2 at +1.0×ATR (~5pts, NOW REACHABLE) hits:
  → tp2_sl_ratchet_enabled: SL → TP1 level (locked profit)
  → TP3 staging: promote remaining runners to TP3 target
       │
       ▼
TP3 at +5.0×ATR (~25pts) — full runner target
  OR ATR trail catches reversal
```

## The 6 conviction atoms — derivation from Run 30 data

The atoms were derived by comparing the 3 BB_BREAKOUT BUY winners and 1 loser in Run 30:

| Atom | G5004 +$354 (win) | G5005 −$1,694 (loss) | G5013 +$985 (win) | Discriminator |
|---|---|---|---|---|
| (price − bb_upper) / ATR | **+2.64** strong | +0.30 weak | −0.02 | ✅ Winners had strong impulse OR high ATR forgiveness |
| (price − VWAP) / ATR | 2.41 | **2.76** ← overextended | 1.81 | ✅ G5005 above 2.5 threshold (already gated v2.7.73) |
| RSI | 73.32 | 74.54 ← exhaustion | 59.01 sweet | ✅ G5013 in best range; G5005 over threshold |
| M15 ADX | 24.95 | 26.39 | 21.19 | ✅ All confirmed M15 momentum |
| signed velocity_5bar | (positive at climb) | (decelerating) | (positive trend) | ✅ Direction continuation atom |
| BOS direction | +1 (overnight rally) | +1 (same) | +1 | ✅ Bullish structure confirmed |

**Why 4 of 6 threshold**: empirically picks up G5004 (~5/6 align) and G5013 (~4-5/6 align with high ATR forgiveness) while excluding G5005 (already blocked by v2.7.73 VWAP gate at atom-2 alone).

## TP geometry rationale (v2.7.74)

### Previous (v2.7.73 and earlier)
- TP1: 0.5×ATR (BUY) / 0.4×ATR (SELL) — ~2.5pts on 5pt ATR
- TP2: **1.5×ATR** — ~7.5pts (too distant, rarely hit)
- TP3: 2.5×ATR — ~12.5pts (never reached because TP2 never staged)
- TP1 close pct: 70% (banks most of position too aggressively)

**Result in Run 30**: TP3 staging code (FORGE.mq5:2658-2709) existed but never fired. Best
winner G5013 banked $985 on a 60pt available move — only ~26% capture. Most MD_BUY winners
captured 5-10% of the move available.

### New (v2.7.74)
- TP1: 0.5×ATR (BUY) / 0.4×ATR (SELL) — **unchanged**
- TP2: **1.0×ATR** — ~5pts (reachable on most BB_BREAKOUT scalps)
- TP3: **5.0×ATR** — ~25pts (captures Apr 1 NY rally class moves)
- TP1 close pct (standard): 70% (unchanged for non-conviction fires)
- TP1 close pct (conviction): **50%** — leaves more for runner

**Mechanism**: TP2 now reachable → tp2_sl_ratchet_enabled fires → SL ratchets to TP1 level
(locks profit at +2.5pts) AND remaining runners get promoted to TP3=5×ATR target.

## The SL ratchet chain (already existed, just activated by reachable TP2)

| Stage | SL position | Profit locked |
|---|---|---|
| Entry | entry − 3×ATR | none (full risk) |
| After TP1 hit (be_cushion) | entry + 1.5×ATR cushion or BE | BE+1.5×ATR if breakout |
| After TP2 hit (tp2_sl_ratchet) | TP1 level (entry + 0.5×ATR) | +2.5pts locked |
| Runner ride to TP3 | ATR trail (existing atr_trail_enabled) | catches reversal |
| TP3 hit | full close | +25pts |

## Config knobs (v2.7.74)

### Conviction amplifier
| FORGE_* env var | Default | Effect |
|---|---|---|
| `FORGE_SETUP_BREAKOUT_BUY_CONVICTION_ENABLED` | `1` | Master toggle |
| `FORGE_GATE_BREAKOUT_BUY_CONVICTION_MIN_ATOMS` | `4` | Atoms required (of 6) |
| `FORGE_GEOMETRY_BREAKOUT_BUY_CONVICTION_INITIAL_LEGS` | `5` | Legs fired on conviction (was 3) |
| `FORGE_GEOMETRY_BREAKOUT_BUY_CONVICTION_TP1_CLOSE_PCT` | `50` | TP1 close pct on conviction (was 70) |

### TP geometry (universal, all BB_BREAKOUT)
| FORGE_* env var | Default | Effect |
|---|---|---|
| `FORGE_BREAKOUT_TP1_ATR_MULT` | `0.4` | TP1 fallback |
| `FORGE_BREAKOUT_TP1_BUY_ATR_MULT` | `0.5` | TP1 for BUY |
| `FORGE_BREAKOUT_TP1_SELL_ATR_MULT` | `0.4` | TP1 for SELL |
| `FORGE_BREAKOUT_TP2_ATR_MULT` | **`1.0`** | TP2 distance (v2.7.74: was 1.5) |
| `FORGE_BREAKOUT_TP3_ATR_MULT` | **`5.0`** | TP3 runner target (v2.7.74: was 2.5) |
| `FORGE_BREAKOUT_TP1_CLOSE_PCT` | `70` | Standard TP1 close pct |
| `FORGE_BREAKOUT_TP2_SL_RATCHET_ENABLED` | `1` | SL→TP1 on TP2 hit |
| `FORGE_BREAKOUT_ATR_TRAIL_ENABLED` | `1` | Trail runner with ATR |

### Stack with prior gates (defense in depth)
Conviction amplifier ONLY fires after these earlier gates pass:
- v2.7.69 BB_BREAKOUT BUY exhaustion-no-bos (RSI ≥ 72 without sustained momentum → block)
- v2.7.71 tightened exhaustion gate (BOS=+1 exemption requires velocity > 0.5 AND macd_slope > 0)
- v2.7.73 VWAP-distance gate ((price − VWAP)/ATR > 2.5 → block — catches G5005 trap)

## Backtest projection (Run 30 winners with v2.7.74 active)

| Trade | Old result | Atoms aligned | Legs fired | Projected new |
|---|---|---|---|---|
| G5004 (bb_ext +2.64, VWAP 2.41, RSI 73) | +$354 | 4-5 of 6 | **5** (conviction) | +$650-1,000 (5-leg + runner) |
| G5013 (ATR 11.77, RSI 59, BOS +1) | +$985 | 4-5 of 6 | **5** (conviction) | +$2,000-3,000 (5-leg + TP3 catches 60pt rally) |
| G5010 (bb_ext +0.73 weak) | small W/L | 2-3 of 6 | 3 (standard) | unchanged (correct — was weak) |
| G5005 (bb_ext +0.30, VWAP 2.76) | −$1,694 | n/a — blocked by v2.7.73 | n/a | $0 (saved $1,694) |

## EA implementation reference

| Component | File:line |
|---|---|
| Conviction struct fields | `ea/FORGE.mq5:1004-1009` |
| Conviction defaults | `ea/FORGE.mq5:3957-3961` |
| Conviction ReadConfig parsing | `ea/FORGE.mq5:4713-4716` |
| Conviction atom evaluation + leg override | `ea/FORGE.mq5:12022-12047` |
| TP3 staging (existing — now activated) | `ea/FORGE.mq5:2658-2709` |
| TP3 assignment on group fire | `ea/FORGE.mq5:12119-12123` |
| ATR trail (existing) | search `atr_trail_enabled` |
| TP2 SL ratchet (existing) | `ea/FORGE.mq5:2681+` (`tp2_sl_ratchet_enabled`) |

## Validation plan for next tester run

After stop + restart MT5 (loads new .ex5):

1. Look for `FORGE 2.7.74 CONVICTION-AMP` log entries — confirms conviction-aware fires
2. Check SIGNALS table for BB_BREAKOUT BUY entries — count legs in TRADES per group_magic
3. Check MT5 log for `TP2 reached — promoted N runner(s) to TP3` — confirms TP3 staging firing
4. Compare per-magic P&L vs Run 30 winners — conviction fires should bank 2-3× more

## References

- Run 30 analysis: `docs/FORGE_RUN30_ANALYSIS.md`
- v2.7.73 VWAP-distance gate (companion fix): same EA, same release window
- TP3 staging design (original): FORGE_RATCHET_LOGIC_IDEAS.md §5/6 (per code comment FORGE.mq5:521)
- Multi-atom composite pattern: `FORGE_SETUP_PLAYBOOK.md` §10

## Changelog

- 2026-05-13 — v2.7.74 ships conviction amplifier + TP2/TP3 recalibration. Derived from Run 30
  BB_BREAKOUT BUY winners/losers analysis. Activates dormant TP3 staging infrastructure
  (existed since v2.7.27 but never fired due to unreachable TP2 distance).
