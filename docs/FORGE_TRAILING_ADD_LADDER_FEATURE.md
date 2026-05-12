# FORGE Trailing-Add Ladder — Feature Design Doc

> **Status**: Design — not yet implemented. Target version: TBD (post v2.7.41 cascade symmetry).
> **Author**: Operator + Claude, 2026-05-12.
> **Naming**: `*_FEATURE.md` suffix marks future feature designs (vs. live reference docs like `FORGE_LOT_SIZING_REFERENCE.md`).
> **Cross-references**: `README.md` § Documentation, `FORGE_DECISION_STACK.md` §5 setup catalog, `docs/FORGE_LOT_SIZING_REFERENCE.md` §0 lot pipeline, `FORGE_REGIME_TAXONOMY.md` §11 ICT killzones, `CHANGELOG.md`.

---

## §1. The concept in one paragraph

A **trailing-add ladder** is a post-TP1 mechanism that **keeps opening new legs as price keeps moving favorably**, stopping only when momentum dies. Unlike the current `SELL_STOP_CONT` / `BUY_STOP_CONT` cascades — which place a fixed N legs at fixed intervals immediately after TP1 — the trailing-add ladder is **open-ended**: leg 2 is placed only after leg 1 fills AND price moves another N points favorably; leg 3 only after leg 2 fills AND another N points; and so on, indefinitely, until a momentum-loss exit signal fires. The cap on total legs is structural (basket DD limit, time expiry) rather than a fixed slot count.

Think: with-trend "scale-in as the move proves itself", Brooks-style.

---

## §2. What it is NOT — distinction from existing mechanisms

| Mechanism | Trigger | Leg placement | Stop condition | Use case |
|-----------|---------|--------------|---------------|----------|
| **SELL_STOP_CONT / BUY_STOP_CONT** (v2.7.10 / v2.7.41) | One-shot, fired ONCE when first TP1 hits | N legs placed immediately as PENDING stops at fixed offsets from TP1 | Time expiry (2 M5 bars) or filled | Capture the second impulse of a confirmed breakout |
| **Staged entry** (`staged_initial_legs` + `staged_add_min_favorable_points`) | Within the SAME group, staged after the initial entry | Stages legs over time after favorable excursion threshold | All legs queued or group hits TP/SL | Spread risk across the initial entry's first few minutes |
| **`SELL_LIMIT_RECOVERY` / `BUY_LIMIT_RECOVERY`** | One-shot, fired when opposite-direction group hits TP1 | One pending LIMIT at the mean-reversion level | Time expiry (4 M5 bars) or filled | Catch a sharp post-TP1 reversal/bounce |
| **🆕 Trailing-add ladder** | Open-ended, continuously after TP1 confirms direction | Each new leg opens only after PRIOR leg is filled AND price moves another N pts favorably from that leg | Momentum-loss signal (RSI, ADX, MACD, EMA cross) OR max-legs ceiling OR basket DD cap OR time expiry | Ride extended one-way moves (Brooks "with-trend") far longer than a 5-leg cascade can |

---

## §3. The Brooks framing — why this matters

Al Brooks (Trading Price Action Trends, Reversals, Trends, Trading Ranges) describes a class of moves he calls **"strong trend with no pullback"**:

- Bars stack one after another in the same direction
- Pullbacks (if any) don't break the prior bar's low/high
- The H1 EMA stays sloped, price stays above (BUY) or below (SELL) the EMA throughout
- These moves typically run 20-50+ M5 bars (= 100-250 mins) without a meaningful retrace

Cascades (5 legs) leave most of the move on the table. The 5 pending stops fill in the first 1-2 bars after TP1; after that, the EA stops adding even though the move keeps going.

A trailing-add ladder lets us **size into the trend as it proves itself** — leg 2 only after leg 1 wins +N pts, leg 3 only after leg 2 also wins, etc. **Bad signals stop the ladder early**; strong trends compound exposure.

### Case study: Apr 1 2024 NY rally (Run 22 G5001)

Real example from FORGE logs:
- BB_BREAKOUT BUY fires at 13:32 NY, TP1 hits at 13:35
- Cascade arms (today: 5 legs SELL_STOP — but BUY cascade doesn't exist!)
- Price runs +85 pts over the next 70 mins with TWO pullbacks of <8 pts each
- Today: no continuation legs fire on the BUY side
- With trailing-add ladder + threshold 10 pts: 8+ legs would fire over the rally
- Brooks framing: "always-in long" — the EA should be loaded up

---

## §4. Trigger + leg-placement geometry

### When the ladder is armed

Same gates as `SELL_STOP_CONT` / `BUY_STOP_CONT`:

1. Group hits TP1
2. Setup_type is eligible (default: `BB_BREAKOUT`, `BB_BREAKOUT_RETEST`)
3. RSI not exhausted (`trail_add_min_rsi` for BUY: ≥ 35; `trail_add_max_rsi` for SELL: ≤ 65)
4. ADX confirmed (`trail_add_min_adx`, default 25)
5. H1 DI alignment (BUY: DI+ > DI−; SELL: DI− > DI+)
6. Regime is trending (not `RANGE`)

### Leg-placement geometry

```
leg_1_entry = TP1_price + atr × trail_add_first_atr_mult         (BUY: above TP1; SELL: below)
leg_1_lot   = lot_fixed × trail_add_lot_factor × ScalperLotFactor
leg_1_SL    = leg_1_entry ∓ atr × trail_add_sl_atr_mult          (below for BUY, above for SELL)
leg_1_TP    = leg_1_entry ± atr × trail_add_tp_atr_mult          (above for BUY, below for SELL)
leg_1_type  = BUY_STOP / SELL_STOP                                (pending order)
leg_1_expiry = TimeCurrent() + trail_add_pending_expiry_bars × M5

After leg_1 FILLS (becomes a live position):
  monitor for price ≥ leg_1_entry + atr × trail_add_step_atr_mult (BUY)
  OR  price ≤ leg_1_entry - atr × trail_add_step_atr_mult (SELL)

When step threshold hits:
  arm leg_2 at leg_1_fill_price + atr × trail_add_first_atr_mult (etc.)

Repeat until:
  - max_legs ceiling reached (default 10)
  - basket DD cap reached
  - momentum-loss signal fires (see §5)
  - time-window expires (default: open trade duration > 4 hours)
```

### Lot-sizing options

| Mode | Effect | Knob |
|------|--------|------|
| **Equal** (default) | Every leg same size: `lot_fixed × trail_add_lot_factor` | `trail_add_lot_mode=EQUAL` |
| **Pyramid down** | Leg N lot = leg 1 lot × pyramid_decay^(N-1). E.g. decay=0.8 → 1.0, 0.8, 0.64, 0.51, 0.41... | `trail_add_lot_mode=PYRAMID_DOWN`, `trail_add_pyramid_decay=0.8` |
| **Pyramid up** | Leg N lot increases. Risk-on; only with very tight momentum-loss exit | `trail_add_lot_mode=PYRAMID_UP`, `trail_add_pyramid_growth=1.25` |

---

## §5. Momentum-loss exit signals

The ladder stops adding when ANY of these fire. Operator can enable/disable each independently.

| Signal | Default behavior | Knob |
|--------|------------------|------|
| **RSI rollover** | BUY ladder: stop adding when M5 RSI < `trail_add_exit_rsi_buy` (default 50). SELL: M5 RSI > `trail_add_exit_rsi_sell` (default 50) | `trail_add_exit_on_rsi_rollover` (bool, default 1) |
| **ADX drop** | Stop adding when M5 ADX drops below `trail_add_exit_adx_drop_pct` of peak ADX seen in the move (default 70% — meaning ADX 35 → 24.5 stops) | `trail_add_exit_on_adx_drop` (bool, default 1) |
| **MACD cross** | Stop adding when H1 MACD histogram crosses zero opposite to direction | `trail_add_exit_on_macd_cross` (bool, default 0 — disabled by default, MACD lags) |
| **EMA break** | Stop adding when price closes against M15 EMA20 (BUY: M15 close < EMA20; SELL: M15 close > EMA20) | `trail_add_exit_on_ema_break` (bool, default 1) |
| **Wick rejection bar** | Stop on a single M5 bar with >50% upper wick (BUY) or lower wick (SELL) AND body counter-direction — Brooks "trapped longs/shorts" | `trail_add_exit_on_wick_rejection` (bool, default 1) |
| **Time expiry** | Stop adding after `trail_add_max_duration_min` minutes since first leg fill (default 240 = 4 hours) | always-on |

Existing legs are NOT closed when the ladder exits — they keep their individual TP/SL. The exit only stops NEW legs from being added.

---

## §6. Risk bounds — keeping the ladder bounded

| Bound | Default | Knob |
|-------|---------|------|
| **Max total legs in ladder** | 10 | `trail_add_max_legs` (1–20) |
| **Max basket drawdown $** | 2.5% of account equity | `trail_add_max_basket_dd_pct` |
| **Min favorable points between legs** | 10 (≈ 1.5× M5 ATR for XAUUSD) | `trail_add_step_atr_mult` (× M5 ATR) |
| **Pending order expiry** | 2 M5 bars (kill if not filled — same as cascade) | `trail_add_pending_expiry_bars` |
| **Time window** | 240 min (4 hours) from first leg fill | `trail_add_max_duration_min` |
| **Min spread tolerance** | Skip leg placement if spread > 0.5 × ATR | `trail_add_max_spread_atr_mult` |
| **News blackout** | If news filter is BLOCK, don't add new legs (existing legs unchanged) | inherits `news_filter_apply_in_tester` etc. |

---

## §7. Proposed configuration surface

All knobs ship behind `FORGE_TRAIL_ADD_ENABLED=0` (default-off). Naming follows the **new §4.9 scope-precision** policy from `FORGE_NAMING_CONVENTIONS.md`, since this is a fresh design and not constrained by legacy aliases.

### Enable flag

| Env | Scope | Default |
|-----|-------|---------|
| `FORGE_SETUP_TRAIL_ADD_BUY_ENABLED` | SETUP | 0 |
| `FORGE_SETUP_TRAIL_ADD_SELL_ENABLED` | SETUP | 0 |
| `FORGE_SETUP_TRAIL_ADD_ELIGIBLE_SETUPS` | SETUP | `"BB_BREAKOUT,BB_BREAKOUT_RETEST"` |

### Geometry

| Env | Scope | Default |
|-----|-------|---------|
| `FORGE_GEOMETRY_TRAIL_ADD_FIRST_ATR_MULT` | GEOMETRY | 0.4 |
| `FORGE_GEOMETRY_TRAIL_ADD_STEP_ATR_MULT` | GEOMETRY | 1.5 |
| `FORGE_GEOMETRY_TRAIL_ADD_SL_ATR_MULT` | GEOMETRY | 1.5 |
| `FORGE_GEOMETRY_TRAIL_ADD_TP_ATR_MULT` | GEOMETRY | 1.5 |
| `FORGE_GEOMETRY_TRAIL_ADD_LOT_FACTOR` | GEOMETRY | 1.0 |
| `FORGE_GEOMETRY_TRAIL_ADD_LOT_MODE` | GEOMETRY | `"EQUAL"` |
| `FORGE_GEOMETRY_TRAIL_ADD_PYRAMID_DECAY` | GEOMETRY | 0.8 |

### Gates (entry conditions)

| Env | Scope | Default |
|-----|-------|---------|
| `FORGE_GATE_TRAIL_ADD_MIN_RSI_BUY` | GATE | 35 |
| `FORGE_GATE_TRAIL_ADD_MAX_RSI_SELL` | GATE | 65 |
| `FORGE_GATE_TRAIL_ADD_MIN_ADX` | GATE | 25 |
| `FORGE_GATE_TRAIL_ADD_REQUIRE_H1_DI` | GATE | 1 |
| `FORGE_GATE_TRAIL_ADD_REQUIRE_TREND_REGIME` | GATE | 1 |

### Exit triggers (momentum-loss signals)

| Env | Scope | Default |
|-----|-------|---------|
| `FORGE_GATE_TRAIL_ADD_EXIT_ON_RSI_ROLLOVER` | GATE | 1 |
| `FORGE_GATE_TRAIL_ADD_EXIT_RSI_BUY` | GATE | 50 |
| `FORGE_GATE_TRAIL_ADD_EXIT_RSI_SELL` | GATE | 50 |
| `FORGE_GATE_TRAIL_ADD_EXIT_ON_ADX_DROP` | GATE | 1 |
| `FORGE_GATE_TRAIL_ADD_EXIT_ADX_DROP_PCT` | GATE | 70 |
| `FORGE_GATE_TRAIL_ADD_EXIT_ON_MACD_CROSS` | GATE | 0 |
| `FORGE_GATE_TRAIL_ADD_EXIT_ON_EMA_BREAK` | GATE | 1 |
| `FORGE_GATE_TRAIL_ADD_EXIT_ON_WICK_REJECTION` | GATE | 1 |

### Risk bounds

| Env | Scope | Default |
|-----|-------|---------|
| `FORGE_GEOMETRY_TRAIL_ADD_MAX_LEGS` | GEOMETRY | 10 |
| `FORGE_GEOMETRY_TRAIL_ADD_MAX_BASKET_DD_PCT` | GEOMETRY | 2.5 |
| `FORGE_TIMING_TRAIL_ADD_MAX_DURATION_MIN` | TIMING | 240 |
| `FORGE_TIMING_TRAIL_ADD_PENDING_EXPIRY_BARS` | TIMING | 2 |
| `FORGE_GATE_TRAIL_ADD_MAX_SPREAD_ATR_MULT` | GATE | 0.5 |

**Total: ~26 new env knobs, all new — no LEGACY_ALIASES needed.**

---

## §8. Implementation phases

### Phase 0 — prerequisite (BLOCKING)

Direction-cap with risk-1 bypass (v2.7.41) MUST be in place. The trailing-add ladder is **the** mechanism that would routinely produce 8-10 same-direction open legs, and `max_open_same_direction=1` would block every leg past the first. Bypass list must include `TRAIL_ADD_BUY` / `TRAIL_ADD_SELL` setup types OR the cap must be raised.

### Phase 1 — minimum viable (single direction)

- BUY only, `EQUAL` lot mode only
- Exit signals: RSI rollover + ADX drop + time expiry (no MACD/EMA/wick)
- Eligible setups: `BB_BREAKOUT_RETEST` only (highest-confidence BUY per the risk table)
- 1 case study validation: replay Apr 1 2024 NY rally, count legs that fire vs cascade today
- Ship behind `FORGE_SETUP_TRAIL_ADD_BUY_ENABLED=0`

### Phase 2 — SELL symmetry

- Mirror Phase 1 for SELL direction
- Validate with Apr 2 2024 crash + Apr 8 PM intraday reversal

### Phase 3 — full exit signal suite

- Add MACD-cross, EMA-break, wick-rejection exits
- Add `PYRAMID_DOWN` and `PYRAMID_UP` lot modes
- Add broader eligible-setup list (`BB_BREAKOUT`, `MOMENTUM_DUMP` etc. if validated)

### Phase 4 — observability + post-mortem

- New SCRIBE columns: `trail_add_leg_count`, `trail_add_exit_reason`, `trail_add_peak_adx`, `trail_add_basket_dd_pct`
- Dashboard: trailing-add ladder visualization (legs colored by fill order, exit signal annotated)

---

## §9. Open questions

1. **Magic-offset band** — current SELL cascade is `+20002..+20008`, BUY cascade (v2.7.41) is `+21002..+21008`. Trailing-add could use `+22000..+22019` (20 slots for up to 10 legs per direction). Or extend existing arrays with per-leg-slot bookkeeping.

2. **Interaction with cascade** — if `BUY_STOP_CONT` is ALSO enabled, do both fire (cascade gives 5 legs immediately + trailing-add adds more as price moves)? Or cascade-OR-trailing exclusivity? **Proposal**: mutual exclusion via a global priority knob: `FORGE_POST_TP1_PRIORITY=CASCADE|TRAIL_ADD|BOTH` (default `CASCADE` for backward compat).

3. **Interaction with `SELL_LIMIT_RECOVERY`** — recovery probes for mean-reversion bounce; trailing-add is with-trend. They're orthogonal and could fire simultaneously. No conflict expected.

4. **Live vs tester** — live trading needs broker-side pending-order count safeguards (some brokers cap concurrent pending orders at 50-200). The 10-leg ceiling × concurrent BUY+SELL ladders × cascade legs × manual recovery limits = could exceed cap in extreme cases. Live deployment needs broker-cap sanity check.

5. **Setup-type emitted in journal** — when leg N of a trailing-add ladder fires, what's the `setup_type`? Proposals: (a) Keep original (`BB_BREAKOUT_RETEST`); (b) Mark as `BB_BREAKOUT_RETEST_TRAIL_ADD`; (c) Use `TRAIL_ADD_BUY` / `TRAIL_ADD_SELL` distinct types. **Proposal**: (c) — cleanest for analysis filtering, requires bypass-list update.

6. **Adverse-leg handling** — if leg 5 of the ladder fills then immediately moves -1×ATR adverse before the next step threshold, do we close it early or let SL handle? **Proposal**: respect leg SL (no early close); add an optional `FORGE_GATE_TRAIL_ADD_EARLY_CLOSE_ON_ADVERSE=1` toggle for operators who want tighter risk control.

---

## §10. Validation plan (when implemented)

Before shipping any Phase, run these against the FORGE Strategy Tester database:

| Validation | Pass criteria |
|-----------|---------------|
| Apr 1 2024 NY rally — count legs trailing-add WOULD have placed | ≥ 6 legs |
| Apr 2 2024 crash — count SELL trailing-add legs | ≥ 6 legs |
| Apr 8 2024 PM reversal — trailing-add doesn't pile into the reversal direction | exit signals fire before the pivot |
| Worst-case basket DD across a 30-day window | ≤ `trail_add_max_basket_dd_pct` default |
| Cumulative pending-order count across all symbols | < 50 (broker safety margin) |
| Compared to v2.7.41 cascade-only — total profit on trending days | trailing-add ≥ cascade |
| Compared to v2.7.41 cascade-only — total loss on choppy days | trailing-add ≤ cascade × 1.2 (some slippage acceptable) |

---

## §11. Cross-references

- **README.md** — Documentation index → this doc listed under "Future Features"
- **`FORGE_DECISION_STACK.md`** §5 — new SETUP entry rows for `TRAIL_ADD_BUY` / `TRAIL_ADD_SELL` when implemented
- **`docs/FORGE_LOT_SIZING_REFERENCE.md`** §0 — lot pipeline includes `trail_add_lot_factor` if ladder enabled
- **`FORGE_REGIME_TAXONOMY.md`** §11 — killzone awareness: trailing-add probably should be PAUSED in London-Close killzone (low momentum)
- **`docs/FORGE_INDICATOR_ATLAS.md`** §1 — exit-signal atoms (RSI rollover, ADX drop %, MACD cross, EMA break, wick rejection) should be inventoried
- **`FORGE_NAMING_CONVENTIONS.md`** §4.9 — all new knobs follow GLOBAL/SETUP/GATE/GEOMETRY/TIMING scope policy
- **`FORGE_RESEARCH_OPS.md`** §7 — add trailing-add to next-actions priorities once direction-cap (v2.7.41) is validated
- **`CHANGELOG.md`** — entry per Phase

---

## §12. Changelog (this doc)

| Date | Change |
|------|--------|
| 2026-05-12 | Initial design doc. Concept, distinction from cascade/staged/recovery, Brooks framing, Apr 1 2024 case study, full configuration surface (~26 env knobs all under new §4.9 scope policy), 4-phase implementation plan, 6 open questions, validation plan. Filed under `docs/FORGE_TRAILING_ADD_LADDER_FEATURE.md` per operator's "*_FEATURE.md" naming convention for future features (vs. `_REFERENCE.md` for live state). |
