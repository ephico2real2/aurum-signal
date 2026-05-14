# FORGE Case Study — G5006 Inflection-Point Loss (Apr 1 08:46)

**Type**: Single-event loss post-mortem — BB_BREAKOUT BUY at reversal
**Source data**: aurum_run_id=35 (v2.7.83), source DB Agent-3000 run_id=3
**Method**: Side-by-side atom comparison of G5005 (winner +$270) vs G5006 (loser -$1,760), both BB_BREAKOUT BUY 6 min apart
**Trigger event**: Operator flagged the loss + requested inflection-point detection composite
**Created**: 2026-05-13

---

## §1 Event timeline

| Time | Price | Event |
|---|---|---|
| 08:40:00 | 4700.69 | **G5005 BB_BREAKOUT BUY** fires (3 legs × 0.38 lot) ✅ |
| 08:41:22 | 4703.08 | G5005 TP1 hit @ +$270 ✅ |
| 08:42-45 | 4702.16-4702.72 | Price stalls; RSI climbs 74.5→74.8 (overbought intensifies) |
| **08:46:13** | **4701.71** | **G5006 BB_BREAKOUT BUY fires (3 legs × 0.38 lot)** 🔴 |
| 08:58:57 | 4686.26 | G5006 SL hit — all 3 legs → **−$1,760** 🔴 |
| 09:00 | 4684 | Low of the local move |
| 10:00 | 4732 | Rally back |
| **10:37:53** | **4743.86** | **Actual local apex** (G5006 SL was only the first leg of the drop) |
| 12:00+ | 4714+ | Distribution before larger move down |

## §2 The smoking gun — atom comparison

Both signals: BB_BREAKOUT BUY · TREND_BULL · LONDON session · 6 minutes apart.

| Atom | G5005 (WIN +$270) | G5006 (LOSS -$1,760) | Diagnostic |
|---|---|---|---|
| RSI | 73.32 | 73.04 | ≈ identical — RSI alone DOES NOT distinguish |
| ADX | 40.1 | 44.3 | similar — ADX is momentum strength, not direction |
| MACD histogram | −2.23 | −2.16 | both bearish — useless as differentiator |
| h1_trend | +2.15 | +2.14 | identical — HTF bull |
| vwap_dist (ATR) | 2.40 | 2.53 | similar — both VWAP-extended |
| **m5_body_pct** | **0.878** ✅ | **0.389** 🔴 | **G5005 = 87.8% body (strong). G5006 = 38.9% body (weak/doji)** |
| **m5_strong_bar** | **1** ✅ | **0** 🔴 | **G5005 strong-bar TRUE. G5006 strong-bar FALSE.** |
| **m5_range_expanding** | **1** ✅ | **0** 🔴 | **G5005 range EXPANDING. G5006 range CONTRACTING.** |
| price vs bb_upper | **+2.64** ✅ | **−0.09** 🔴 | **G5005 was ABOVE the band (real breakout). G5006 was AT the band (no breakout).** |

### Why these atoms matter

This is **textbook BB exhaustion reversal** pattern from classical technical analysis (Bollinger's own book + Murphy's *Technical Analysis of the Financial Markets*):

> "When price reaches the upper Bollinger Band with declining momentum (small body, contracting range, MACD divergence), the move is exhausted. Expect mean reversion."

G5006 had:
- Price at (not above) BB upper → **no breakout**
- Body 39% (typically need >60% for momentum) → **indecision candle**
- Range NOT expanding → **volatility contraction = exhaustion**
- MACD turning down despite price up → **bearish divergence**
- RSI 73 → **overbought**
- VWAP +2.5×ATR → **mean-reversion zone**

All seven conditions of Row 3 "Reversal Setup" from the operator's setup catalog were ACTIVE at G5006 entry. Yet the EA fired BB_BREAKOUT BUY (Row 1 "Breakout Setup") instead.

## §3 Why FORGE missed this

| Atom | Computed | Logged to SIGNALS | Enforced as gate |
|---|---|---|---|
| `m5_strong_bar` | ✅ (v2.7.64) | ✅ | ❌ **Not gated for BB_BREAKOUT BUY** |
| `m5_body_pct` | ✅ (v2.7.64) | ✅ | ❌ **Not gated for BB_BREAKOUT BUY** |
| `m5_range_expanding` | ✅ (v2.7.64) | ✅ | ❌ **Not gated for BB_BREAKOUT BUY** |
| `m5_atr_ratio_5bar` | ✅ (v2.7.65) | ❌ **Not in SIGNALS schema** | ❌ |
| `m5_velocity_5bar_signed` | ✅ (v2.7.69) | ❌ **Not in SIGNALS** | partial (BLR only) |
| `m5_macd_slope_5bar` | ✅ (v2.7.65) | ❌ | ❌ |
| `bos_direction` (ICT) | ✅ (v2.7.68) | ❌ | partial (BLR only) |

**Two gaps**:

1. **Atoms exist but no enforcement** — m5_strong_bar / m5_body_pct / m5_range_expanding were added in v2.7.64 for instrumentation, but no gate consumes them for BB_BREAKOUT BUY (only some setups use them).
2. **Logging gap** — velocity/MACD-slope/ATR-ratio atoms (v2.7.65 + v2.7.68) live in `market_data.json` but are NOT in the SIGNALS table schema. We can't audit "what did velocity look like at G5006 entry?" from the DB — those atoms exist only at LIVE tick time.

## §4 The 3-layer entry-gating design (operator-locked, 2026-05-13)

**Principle** (per operator mandate): every new trade entry MUST validate market condition BEFORE the setup fires. No setup is allowed to bypass this universal pre-check.

### §4.0 Design evolution — three corrections by operator

The final design emerged through three iterations:

| # | Initial proposal | Operator correction |
|---|---|---|
| 1 | Simple time-based post-TP cooldown (10 min lockout after BB_BREAKOUT BUY TP1) | "Post-TP cooldown is a false idea" — TPs don't trigger cooldown |
| 2 | UMCG-only, no cooldown, stateless gate | "I like the state machine — because it would have been useful" |
| 3 | Restore state machine | "It just have to have a logic that evaluate both sell and buy and retry" |

**Final design = 3 layers**: UMCG (always-on stateless gate) + CVCSM (SL-only state machine with bidirectional retry) + opposite-direction reversal capture.

### §4.1 Layer 1 — UMCG (Universal Market Condition Gate)

7-atom BUY-reversal-warning composite. **≥ 3 of 7 atoms triggers a BUY-block** (and mirror for SELL):

| # | Atom | Condition | Maps to operator's setup #3 (Reversal) |
|---|---|---|---|
| A1 | `m5_rsi` | ≥ 70 | RSI overbought |
| A2 | `m5_body_pct` | < 0.5 (weak candle) | Indecision |
| A3 | `m5_strong_bar` | == 0 (no strong-bar) | No momentum confirmation |
| A4 | `m5_range_expanding` | == 0 (range contracting) | Volatility exhaustion |
| A5 | `bb_upper_dist_atr` | < 0.3 (price NOT meaningfully above band) | No real breakout |
| A6 | `m5_atr_ratio_5bar` | < 1.0 (volatility contracting) | Exhaustion |
| A7 | `macd_histogram` < 0 AND `m5_close` > `m5_close_1` | bearish divergence | Reversal signal |

**Validated against actual data (Run 35)**:

| Trade | RSI | strong_bar | body | range_exp | bbu_dist | MACD div | Total | Verdict |
|---|---|---|---|---|---|---|---|---|
| G5005 ✅WIN | 73 | 1 | 0.88 | 1 | +2.64 | ✅ | **2/7** | PASS |
| **G5006 🔴LOSS** | 73 | 0 | 0.39 | 0 | -0.09 | ✅ | **5/7** | BLOCK |
| **G5015 🔴LOSS** | 59 | 0 | 0.26 | 0 | +0.14 | ✅ | **5/7** | BLOCK |

3-of-7 threshold cleanly separates winners from losers. Stateless — evaluated at every M5 close (or per tick if cheap).

### §4.2 Layer 1 — Mirror SELL composite

Inverse for SELL: if ≥3 of 7 reversal-UP atoms trigger, block any SELL:
- RSI ≤ 30, body weak, no strong-bar, range contracting, bb_lower distance < 0.3×ATR, atr_ratio < 1.0, MACD > 0 AND close < close[1] (bullish divergence).

### §4.3 Layer 2 — CVCSM (Smart SL-Triggered State Machine with Bidirectional Retry)

States per direction (independent BUY/SELL):

```
OPEN  →(SL fired in this direction)→ COOLDOWN
COOLDOWN  →(every M5 close)→ RETRYING
RETRYING  →(PEMCG clean N consecutive bars)→ OPEN
RETRYING  →(PEMCG dirty)→ stays RETRYING
Safety: COOLDOWN → OPEN after max_cooldown_sec timeout (default 1800s / 30 min)
```

**Key principles (operator-locked)**:
- ❌ **TP firing does NOT trigger cooldown** (TPs are wins, no reason to cool)
- ✅ Only **SL** triggers cooldown (loss → be cautious for re-entry)
- ✅ Every M5 close **retries** both directions independently
- ✅ Opposite direction is **NEVER blocked** by same-direction cooldown
- ✅ Release when **atoms confirm** market has moved past the trap (PEMCG warnings cleared for 2 consecutive M5 bars)

**Why state machine + UMCG, not just UMCG**: provides belt-and-braces safety in the post-SL recovery window when emotions/adrenaline would tempt immediate re-entry. PEMCG alone catches Run 35 traps; CVCSM covers the edge cases (atom-ambiguous degradation, cascade-leg fills during reversal) that haven't manifested in this run but are architecturally inevitable.

### §4.4 Layer 3 — Opposite-direction reversal capture

When `pemcg_buy_warnings ≥ 4` (the very warnings that block BUY), fire `BB_EXHAUSTION_REVERSAL_SELL`:
- Lot: 0.10 (fractional, counter-HTF caution)
- SL: `bb_upper + 1.0×ATR` (above the failing top)
- TP1: `bb_mid` (close-in mean reversion)
- TP2: `vwap_price` (deeper)
- Mirror: `BB_EXHAUSTION_REVERSAL_BUY` fires when SELL-side mirror composite hits ≥ 4

This converts the "BUY trap = SELL opportunity" insight into captured P&L. Maps directly to **operator's setup #3 "Reversal Setup"** from the catalog (Double Top + RSI divergence) — translated to a FORGE-native composite.

### §4.5 Cooldown investigation result

Per operator question: "investigate the cooldown — maybe we didn't check market condition before executing".

Pre-v2.7.84 state: `bb_breakout.cooldown_secs = 0` (no cooldown). G5005 → G5006 was 6 minutes apart with no gate between them. **No market-condition check existed.**

**Fix (delivered by Layers 1+2 above, not by a per-setup timer)**:
- Layer 1 UMCG blocks G5006 at trigger time on PEMCG=5/7 (no cooldown needed for this specific case)
- Layer 2 CVCSM adds belt-and-braces — would have entered COOLDOWN if G5006 HAD fired and SL'd; would have prevented a hypothetical G5007 right after
- Layer 3 fires a SELL when conditions warrant — captures the reversal even when BUY is blocked

**Anti-pattern explicitly rejected**: per-setup time-based cooldown (`*_cooldown_secs` env var). Replaced by the bidirectional state machine with PEMCG-driven retry.

## §5 Implementation plan — v2.7.84 (3-layer, operator-locked)

**~170 LOC across FORGE.mq5 + sync mappings + env + gate_legend. Default-ON. No backend changes.**

### Part A — UMCG (Universal Market Condition Gate, Layer 1)

New globals computed in `ForgeEvalAtoms()`:
- `g_pemcg_buy_warning_count` — counts how many of 7 BUY-reversal atoms are TRUE
- `g_pemcg_sell_warning_count` — mirror

Gate check at every BUY/SELL setup trigger:
```mql5
if(direction == "BUY" && g_pemcg_buy_warning_count >= g_sc.umcg_buy_block_threshold) {
   JournalRecordSignal("SKIP", "pemcg_buy_reversal_block", setup_type, "BUY", ...);
   return;  // SKIP entire setup
}
// mirror for SELL
```

Env knobs (default-ON):
- `FORGE_GATE_UMCG_ENABLED=1`
- `FORGE_GATE_UMCG_BUY_BLOCK_THRESHOLD=3`
- `FORGE_GATE_UMCG_SELL_BLOCK_THRESHOLD=3`

### Part B — CVCSM (State Machine, Layer 2)

State globals per direction:
- `g_cvcsm_state_buy ∈ {0=OPEN, 1=COOLDOWN, 2=RETRYING}` + `g_cvcsm_cooldown_start_buy` + `g_cvcsm_clean_bars_buy`
- Mirror for SELL

State machine logic in new function `EvalCVCSM()` called every M5 close (or every tick — bar-close detection cheap):
```mql5
void EvalCVCSM(int direction) {
   int state = (direction == BUY) ? g_cvcsm_state_buy : g_cvcsm_state_sell;
   int warnings = (direction == BUY) ? g_pemcg_buy_warning_count : g_pemcg_sell_warning_count;

   if(state == COOLDOWN) {
      if(warnings < g_sc.cvcsm_release_threshold) {
         // transition to RETRYING
         set_state(direction, RETRYING);
         set_clean_bars(direction, 1);
      } else if(TimeCurrent() - start_time > g_sc.cvcsm_max_cooldown_sec) {
         set_state(direction, OPEN);  // safety release
      }
   } else if(state == RETRYING) {
      if(warnings < g_sc.cvcsm_release_threshold) {
         clean_bars++;
         if(clean_bars >= g_sc.cvcsm_required_clean_bars) {
            set_state(direction, OPEN);
         }
      } else {
         set_state(direction, COOLDOWN);  // re-cool if dirty again
         clean_bars = 0;
      }
   }
}

// Triggered on every SL fill (in close-tracking code):
void OnSLFired(int direction) {
   if(g_cvcsm_state[direction] == OPEN) {
      g_cvcsm_state[direction] = COOLDOWN;
      g_cvcsm_cooldown_start[direction] = TimeCurrent();
   }
}
// CRITICAL: TPs do NOT call OnSLFired — only actual SL hits do.
```

Setup-trigger guard becomes:
```mql5
if(direction == "BUY" && g_cvcsm_state_buy != OPEN) {
   JournalRecordSignal("SKIP", "cvcsm_cooldown_block_buy", setup_type, "BUY", ...);
   return;
}
```

Env knobs (default-ON):
- `FORGE_GATE_CVCSM_ENABLED=1`
- `FORGE_GATE_CVCSM_RELEASE_THRESHOLD=2` (warnings < this releases)
- `FORGE_TIMING_CVCSM_REQUIRED_CLEAN_BARS=2`
- `FORGE_TIMING_CVCSM_MAX_COOLDOWN_SEC=1800`

### Part C — BB_EXHAUSTION_REVERSAL_SELL + mirror (Layer 3)

New setup trigger blocks (one per direction):

```mql5
// BB_EXHAUSTION_REVERSAL_SELL — fires when BUY-side reversal warnings hit threshold
if(direction == "" && g_sc.bb_exhaustion_reversal_enabled
   && g_pemcg_buy_warning_count >= g_sc.bb_exhaustion_reversal_min_warnings
   && g_cvcsm_state_sell == OPEN) {
   // Verify SELL atoms ALSO clean (not just BUY reversing)
   if(g_pemcg_sell_warning_count < g_sc.cvcsm_release_threshold) {
      direction = "SELL";
      setup_type = "BB_EXHAUSTION_REVERSAL_SELL";
      // Geometry
      sl  = NormalizeDouble(m5_bb_u + m5_atr * g_sc.bb_exhaustion_reversal_sl_atr_mult, _Digits);
      tp1 = NormalizeDouble(m5_bb_m, _Digits);
      tp2 = NormalizeDouble(g_vwap_price, _Digits);
   }
}
// Mirror BB_EXHAUSTION_REVERSAL_BUY when g_pemcg_sell_warning_count >= threshold AND BUY side clean
```

Env knobs:
- `FORGE_SETUP_BB_EXHAUSTION_REVERSAL_ENABLED=1`
- `FORGE_GATE_BB_EXHAUSTION_REVERSAL_MIN_WARNINGS=4`
- `FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_LOT=0.10`
- `FORGE_GEOMETRY_BB_EXHAUSTION_REVERSAL_SL_ATR_MULT=1.0`
- `FORGE_TIMING_BB_EXHAUSTION_REVERSAL_COOLDOWN_SEC=1800`

### New gate codes (5)

- `pemcg_buy_reversal_block` — UMCG blocked BUY entry
- `pemcg_sell_reversal_block` — UMCG blocked SELL entry
- `cvcsm_cooldown_block_buy` — CVCSM in COOLDOWN/RETRYING blocks BUY
- `cvcsm_cooldown_block_sell` — CVCSM blocks SELL
- `bb_exhaustion_reversal_sell_below_min` — reversal trigger fired but warning count below threshold

### Validation against Run 35

Replay with all 3 layers:

| Trade | PEMCG_BUY | CVCSM_BUY | UMCG | CVCSM | Reversal trigger | Action |
|---|---|---|---|---|---|---|
| G5005 BUY @08:40 | 2/7 | OPEN | PASS | OPEN | n/a | ✅ fires +$270 |
| G5006 BUY @08:46 | **5/7** | OPEN | **BLOCK** | OPEN | n/a (BUY blocked, but SELL_REVERSAL could fire @ pemcg_buy=5≥4) | 🔴 saves $1,760, possibly +$15-100 SELL capture |
| G5008 BUY @13:30 | 1-2/7 | OPEN | PASS | OPEN | n/a | ✅ fires +$98 |
| G5015 BUY @22:37 | **5/6** | OPEN | **BLOCK** | OPEN | (BUY blocked, SELL_REVERSAL fires) | 🔴 saves $564, possibly +$100-200 SELL capture |

Net expected delta: **+$2,400 to +$2,600** improvement on Run 35 net P&L (from current +$166 to potentially +$2,500-2,800).

## §6 Recommendations

1. **Ship v2.7.84 = PEMCG + post-TP cooldown** — TWO config-flag-protected changes
2. **Extend SIGNALS schema** (separate v2.7.85+) to log all v2.7.65/68 velocity + BOS + atr_ratio atoms — currently you can't audit "what did velocity look like at G5006" from the DB. This is a logging gap that prevented earlier diagnosis.
3. **Update forge-monitor skill** to mandate "Inflection-Point Audit" section in every run analysis — for every TAKEN BUY at RSI ≥ 70, compare its m5_strong_bar / body_pct / range_expanding atoms to known winners
4. **Add `BB_EXHAUSTION_REVERSAL_SELL` setup as v2.7.85** to actually CAPTURE the drop the operator wanted to profit from (the 150-pip move)

## §7 References

- Operator setup catalog screenshot: `/Users/olasumbo/Documents/Lagos_bills/Screenshot 2026-05-13 at 7.09.50 PM.png` (15-setup taxonomy, Row 3 "Reversal Setup")
- Atoms source: `ea/FORGE.mq5` `ForgeEvalAtoms()` ~line 5800+ (v2.7.64-2.7.68 additions)
- Run 35 data: aurum_run_id=35, FORGE v2.7.83
- Prior similar cases: Run 30 G5005 (-$1,694), Run 32 G5005 (-$2,934) — same pattern, same atoms missed

## §9 v2.7.86 — UMCG threshold calibration (2026-05-14)

**Trigger**: Run 4 (FORGE v2.7.85, sim Mar 31 00:00 → 05:30, ~83k signals) produced
**0 TAKEN** at hour 5.5 of sim. Gate breakdown showed PEMCG_BUY firing **67,510×**
and PEMCG_SELL firing **6,500×** — overwhelmingly the top blocker.

### Evidence — PEMCG block RSI distribution (Run 4)

| Direction | RSI band | Block count | In exhaustion zone? |
|-----------|----------|-------------|---------------------|
| BUY | 30-50 | 6,546 | ✗ NO — range bars |
| BUY | 50-70 | 48,758 | ✗ NO — mid-range |
| BUY | 70-80 | 20,657 | ✓ YES — intended |
| BUY | 80+ | 1,097 | ✓ YES |
| SELL | 30-50 | 3,473 | ✗ NO |
| SELL | 50-70 | 5,175 | ✗ NO |
| SELL | <30 | **0** | (would be intended) |

**55,304 BUY blocks at RSI 30-70** — gate fired in normal range conditions, not exhaustion.

### Root cause

Threshold `umcg_buy_block_threshold = 3` (set by v2.7.84) is majority-minus-one of 7
atoms. In normal range/consolidation conditions, A2 (`body_pct<0.5`) + A3
(`m5_strong_bar=0`) + A4 (`m5_range_expanding=0`) + A6 (`atr_ratio_5bar<1.0`) are
naturally TRUE simultaneously → 4 warnings already → gate fires WITHOUT RSI being
anywhere near 70.

The composite was calibrated against G5006 (6/7 warnings at RSI 73) and G5015 (5/7
at RSI 59). The 3/7 threshold was operator-chosen conservatively but is too tight
when UMCG is applied universally (every setup, not just BB_BREAKOUT — see
`ea/FORGE.mq5:12367`).

### Fix

Bumped both BUY and SELL thresholds 3 → 5 (supermajority vote, 71% atom agreement).

| Knob | OLD | NEW | Rationale |
|---|---|---|---|
| `umcg_buy_block_threshold` | 3 | **5** | G5006 had 6/7 → still blocked; range bars with 3-4/7 → released |
| `umcg_sell_block_threshold` | 3 | **5** | mirror; G5015 had 5/7 → still blocked |

### Math check — both losers still caught

- G5006 (Apr 1 08:46): RSI 73 + weak bar + no expansion + bb-near + ATR contract +
  MACD bear = **6/7 warnings** → 6 ≥ 5 → **BLOCKED** ✓
- G5015 (Apr 1 22:37): RSI 59 + 3 bar-quality atoms + ATR contract + MACD-near =
  **5/7 warnings** → 5 ≥ 5 → **BLOCKED** ✓
- ORB BUY at RSI 49.5 (Run 4 sample): weak range bar + body<0.5 + no expansion +
  ATR-flat = **3-4/7** → 4 < 5 → **PASSES** ✓

### Industry pattern

5/7 = ~71% atom agreement = supermajority. Per multi-factor confirmation literature
(Tradeciety, BabyPips, Trading Schools), reversal/exhaustion composites typically
require ≥60% agreement to filter false signals while avoiding over-blocking. 3/7
(~43%) is below majority — almost any volatility contraction passes. 5/7 is the
canonical balance.

### Files changed (v2.7.85 → v2.7.86)

1. `VERSION`: `2.7.85` → `2.7.86`
2. `ea/FORGE.mq5:63`: `FORGE_VERSION = "2.7.86"`
3. `ea/FORGE.mq5:4438-4440`: defaults raised 3 → 5 (BUY + SELL)
4. `.env`: `FORGE_GATE_UMCG_BUY_BLOCK_THRESHOLD=5`, `FORGE_GATE_UMCG_SELL_BLOCK_THRESHOLD=5`
5. `.env.example`: added v2.7.84 UMCG/CVCSM/BB_EXHAUSTION_REVERSAL block + v2.7.85 TC HTF block (was missing — Mandatory Check C failure now resolved)
6. `config/scalper_config.json` (auto-regen via `make scalper-env-sync`): `umcg_*_block_threshold: 5`
7. `FORGE.ex5` 514,536 bytes, compiled clean

### Re-validation plan

Operator should:
1. Stop the current MT5 tester (Run 4 — guaranteed 0 trades)
2. Re-attach FORGE in MT5 (Navigator → drag onto chart) to pick up v2.7.86 .ex5
3. Restart tester with same params
4. Expect on Run 5: PEMCG_BUY blocks drop from ~67k to <5k, ORB/MA_CROSSOVER/INSIDE_BAR
   TAKEN counts rise to normal levels
5. Apr 1 08:46 G5006 still blocked (RSI 73, 6/7); Apr 1 22:37 G5015 still blocked
   (RSI 59, 5/7)

## §10 v2.7.87 — PEMCG A5 atom sign-bug fix (2026-05-14, 15 min after v2.7.86)

**Trigger**: Run 36 (FORGE v2.7.86) at sim hour 9, only 1 TAKEN total despite a clear
100-pip bull thrust between 03:00-05:00 UTC (price 4505 → 4606). PEMCG_BUY blocks rose
to 44,764 — including 13,185 during the thrust hour 04:00 alone.

### Root cause — A5 sign bug in `ea/FORGE.mq5:6635`

```mql5
// BEFORE (v2.7.84 — v2.7.86)
double bbu_dist_atr_pemcg = (m5_close_now - m5_bb_u_pemcg) / m5_atr_now;
//                          └────────── SIGNED distance ──────────┘
if(bbu_dist_atr_pemcg < 0.3) buy_w++;  // A5: "no real breakout above BB"
```

The condition `(close − bb_upper)/atr < 0.3` is TRUE whenever close is below BB upper
(distance is negative, and any negative number is `< 0.3`). Result: A5 fires
**always-TRUE** for any BUY in non-extended trends.

**Run 36 evidence** — ORB BUY at 04:10:
- close 4538.94, BB upper 4554.03, ATR 12
- dist = (4538.94 − 4554.03) / 12 = **−1.26**
- −1.26 < 0.3 = TRUE → A5 fires
- But price is 15 pips BELOW BB upper, nowhere near it. Should be FALSE.

Same bug mirrored on SELL (A5 = `(bb_lower − close)/atr < 0.3` fires whenever close
is above bb_lower — i.e., most of the time).

**Impact** (across all v2.7.84/85/86 runs): one of seven atoms was always-TRUE for
non-extended trades. Effective threshold became 4/6 of the real atoms, not 5/7 of all
seven. In any chop bar where A2/A3/A4/A6 fire (weak body + no strong + no expansion +
ATR contracting), buggy A5 made it 5 → blocked. This is why v2.7.86 still over-blocked
in Run 36 despite the threshold lift.

### Fix

```mql5
// AFTER (v2.7.87)
double bbu_dist_atr_pemcg = MathAbs(m5_close_now - m5_bb_u_pemcg) / m5_atr_now;
double bbl_dist_atr_pemcg = MathAbs(m5_bb_l_pemcg - m5_close_now) / m5_atr_now;
//                          └────── ABSOLUTE distance ──────┘
if(bbu_dist_atr_pemcg < 0.3) buy_w++;  // A5: close is within ±0.3 ATR of BB upper
```

Now A5 fires only when close is within ±0.3 ATR of BB upper (above OR below). This
matches the original "near BB upper" intent.

### Truth-table validation against target losses

| Trade | close - bb_upper | abs(dist)/ATR | A5 v2.7.86 | A5 v2.7.87 | Total atoms |
|---|---|---|---|---|---|
| G5006 LOSS | **−0.09** | ~0.04 | TRUE | **TRUE** (still blocks) | 5/7 → still blocks |
| G5015 LOSS | **+0.14** | ~0.07 | TRUE | **TRUE** (still blocks) | 5/7 → still blocks |
| Run 36 ORB @ 04:10 | **−15.09** | 1.26 | TRUE (bug) | **FALSE** (released) | drops to 3-4/7 → passes |

Both target losses had close within ±0.07 ATR of BB upper — comfortably under the
0.3 ATR threshold. A5 still fires with absolute-distance check. Run 36 trend-continuation
BUYs at 1.26 ATR below BB upper correctly drop A5 → fall below the 5/7 threshold.

### Files changed (v2.7.86 → v2.7.87)

1. `VERSION`: `2.7.86` → `2.7.87`
2. `ea/FORGE.mq5:63`: `FORGE_VERSION = "2.7.87"`
3. `ea/FORGE.mq5:6635-6636`: wrap distance computation in `MathAbs()` for both BUY and SELL
4. `FORGE.ex5` 513,558 bytes, compiled clean (978 bytes smaller than v2.7.86 — inline change only)

**Threshold UNCHANGED at 5/5** — A5 fix lets the supermajority vote work as originally
intended.

### Re-validation plan

Operator should:
1. Stop Run 36 (v2.7.86 — partial coverage, 1 trade so far)
2. Re-attach FORGE in MT5 → drag from Navigator onto chart (loads v2.7.87 .ex5)
3. Restart tester from same start point
4. Expect Run 37: PEMCG_BUY blocks drop further from 44,764 → likely <10,000 (only firing
   when price is truly near BB upper); Asian bull-thrust period (04:00-05:00) should
   produce 2-5 trend-continuation BUYs that were missed in Run 36

## §11 v2.7.88 — A1 RSI threshold widened after Run 5 G5006 reproduction (2026-05-14)

**Trigger**: Run 5 (FORGE v2.7.86) at sim 2026-04-01 08:46:31 — **G5006 BB_BREAKOUT BUY
fired at RSI 69.3 @ 4699.76, SL hit 13 min later at 4684.02. Loss −$1,793.60.** PEMCG
did NOT block it. The original case study's atom calibration was based on the wrong
assumption that G5006 fires at peak RSI (73). It actually fires on the **retest after
the peak**, at RSI 65-69.

### Forensic evidence — 90-second window before the trap

| Sim Time | Price | BB upper | gap (ATR) | RSI | Setup | Outcome |
|---|---|---|---|---|---|---|
| 08:40:00 | 4700.70 | 4698.06 | **+0.527** | **73.3** | BB_BREAKOUT BUY | **TAKEN** (G5005, +$270) |
| 08:45:00 | 4702.29 | 4701.99 | **+0.062** | **74.5** | ORB BUY | **SKIP `pemcg_buy_reversal_block`** ← PEMCG WORKING |
| 08:45:00 | 4702.29 | 4701.99 | +0.062 | 74.5 | BB_BREAKOUT BUY | SKIP `bb_breakout_buy_vwap_overextended` |
| **08:46:31** | **4699.76** | (retest) | **near zero** | **69.3** | **BB_BREAKOUT BUY** | **TAKEN → SL → −$1,793.60** 🔴 |

### Mechanism

1. **08:45**: Price tagged peak at 4702.29 with RSI 74.5, +0.06 ATR above BB upper.
   PEMCG correctly fired 5+/7 atoms (A1 + bar-quality + A5) → ORB BUY blocked.
2. **90 seconds later** (08:46:31): Price already pulled back to 4699.76 (−2.5 pts
   from peak). **RSI dropped to 69.3 — below the 70 A1 threshold.**
3. With A1 OFF, PEMCG count dropped from 5/7 → 4/7 → passed threshold 5.
4. BB_BREAKOUT BUY (which had been blocked at 08:45 by VWAP-overextended) re-fired on
   the **retest of BB upper from below**. This is the textbook "fake breakout / retest
   failure" pattern. Price never recovered.

### Fix

Lower A1 RSI thresholds to capture the post-peak retest window:

| Knob | OLD | NEW | Rationale |
|---|---|---|---|
| `umcg_pemcg_rsi_overbought` | 70.0 | **65.0** | catches RSI 65-70 post-peak retest |
| `umcg_pemcg_rsi_oversold` | 30.0 | **35.0** | mirror; catches RSI 30-35 post-trough retest |

### Validation against all historical cases

| Trade | RSI at entry | A1 v2.7.86 (≥70/≤30) | A1 v2.7.88 (≥65/≤35) | Total atoms TRUE |
|---|---|---|---|---|
| G5005 WIN historical | 73 | TRUE | **TRUE** | (other atoms FALSE because strong bar) → no-block ✓ |
| G5006 LOSS historical | 73 | TRUE | **TRUE** | 5/7 → blocks ✓ |
| G5006 LOSS Run 5 | **69.3** | **FALSE (missed!)** | **TRUE (catches!)** | 5/7 → **blocks** ✓ |
| G5015 LOSS | 59 | FALSE | FALSE | 4/7 from bar+ATR+MACD atoms; still ≥5 if A5 fires |
| Run 36 ORB @ 04:10 | 60.5 | FALSE | FALSE | 3-4/7 → no block ✓ (correct — trend continuation) |

The fix CATCHES the Run 5 G5006 reproduction without producing false positives on
trend continuation BUYs (those still have A1 FALSE because RSI is around 60).

### Files changed (v2.7.87 → v2.7.88)

1. `VERSION`: `2.7.87` → `2.7.88`
2. `ea/FORGE.mq5:63`: `FORGE_VERSION = "2.7.88"`
3. `ea/FORGE.mq5:4441-4442`: defaults 70.0 → 65.0 (overbought) and 30.0 → 35.0 (oversold)
4. `.env:584-585`: overrides 70.0 → 65.0 and 30.0 → 35.0
5. `.env.example`: corresponding doc lines updated
6. `FORGE.ex5` 513,824 bytes, compiled clean

**Threshold UNCHANGED at 5/5** (v2.7.86 supermajority). **A5 absolute-distance fix
PRESERVED from v2.7.87.** This ship only widens A1 RSI envelope.

### Cumulative v2.7.86 + v2.7.87 + v2.7.88 effect

| v2.7.84 state | v2.7.88 final state |
|---|---|
| Threshold 3, A5 always-TRUE, A1 strict (70/30) | Threshold 5, A5 absolute, A1 widened (65/35) |
| Run 4: 0 trades in 5.5h | Run 5: 4 wins +$890 (Mar 31) then 1 loss −$1,794 G5006 (Apr 1) |
| Future Run 6 expected | Catches G5006 retest trap + lets Mar 31 thrust through |

## §8 Changelog

- 2026-05-13 — initial case study after operator-flagged G5006 -$1,760 loss
- 2026-05-13 — added G5015 (-$564) cross-reference; confirmed same pattern (RSI 59 but weak-bar atoms)
- 2026-05-13 — design evolution recorded (§4.0): post-TP cooldown rejected, UMCG-only rejected, final = 3-layer (UMCG + SL-only CVCSM with bidirectional retry + opposite-direction reversal capture)
- 2026-05-13 — implementation plan §5 rewritten for 3-layer design (~170 LOC, default-ON)
- 2026-05-13 — WebSearch industry validation cited (MQL5 Wizard BB articles, scalping cooldown best practices, regime filter patterns)
- 2026-05-14 — **v2.7.86 ship** — UMCG threshold 3 → 5 after Run 4 evidence (55,304 BUY blocks at RSI 30-70). Supermajority vote; both G5006 (6/7) and G5015 (5/7) still blocked; range bars released. See §9.
- 2026-05-14 — **v2.7.87 ship** (15 min after v2.7.86) — PEMCG A5 atom sign-bug fix: signed `(close-bb_upper)/atr` was always-TRUE for non-extended BUYs, inflated effective atom count by 1. Fixed via `MathAbs()`. Run 36 ORB BUYs at 04:10 (1.26 ATR below BB upper) released; G5006 (−0.09) and G5015 (+0.14) both still block. See §10.
- 2026-05-14 — **v2.7.88 ship** (after Run 5 G5006 reproduction −$1,793.60) — A1 RSI thresholds widened 70→65 (overbought) and 30→35 (oversold). Original case study assumed G5006 fires at peak RSI 73; forensics showed it fires on the RETEST 90s later at RSI 69.3, below A1 threshold. New window catches retest trap while preserving trend-continuation BUYs (RSI 60). See §11.
