# FORGE Run 20 — Tester Analysis (v2.7.31 — full additive stack)

**EA version**: FORGE v2.7.31
**Symbol**: XAUUSD
**Sim period**: 2026-03-31 → 2026-05-07
**Scalper mode**: DUAL
**Balance**: $10,000
**aurum_run_id**: 20
**wall_time**: 593410062
**source_run_id**: 1
**Magic base**: 202401
**Status**: **in progress** (sim at 2026-03-31 04:00 UTC, 37 signals, 0 TAKEN — Asian warmup)
**Last updated**: 2026-05-11

> Previous FORGE 2.7.6 Run 20 archived as `docs/FORGE_RUN20_ANALYSIS_OLD_v2.7.6.md`.

> **Test intent**: Validate v2.7.31 three-fix bundle vs Run 19 (v2.7.30) same window.
> - **Fix A** — Dump-catch RR bypass + `FORGE_DUMP_MIN_ADX=20` → Apr 8 PM SELLs fire as TAKEN
> - **Fix B** — Leg-cap H1-strong override → Apr 1 G5001/G5002 unlock 10-leg ladder
> - **Fix C** — `BB_PULLBACK_SCALP` additive setup → catches Run 19's PSAR-blocked bounces with G5028 still excluded

> Regime architecture roadmap at [`docs/FORGE_REGIME_PREDICTOR_DESIGN.md`](FORGE_REGIME_PREDICTOR_DESIGN.md) is v2.7.32+.

---

## Active config knobs (from `.env`)

```
FORGE_DAILY_DIRECTION_GATE_ENABLED=1
FORGE_DAILY_CANCEL_PENDING_ON_FLIP=1
FORGE_REGIME_H1_OVERRIDE_FACTOR=2.0
FORGE_REGIME_H1_OVERRIDE_ADX_MIN=30
FORGE_DUMP_CATCH_ENABLED=1
FORGE_DUMP_REQUIRE_D1_BIAS=0
FORGE_DUMP_LOT_FACTOR=0.5

# Run 20 — v2.7.31 NEW
FORGE_DUMP_MIN_ADX=20                # Fix A — was 25 default
FORGE_PULLBACK_SCALP_ENABLED=1       # Fix C — master switch
FORGE_PULLBACK_SCALP_FRESH_FLIP_BARS=3
FORGE_PULLBACK_SCALP_LOT_FACTOR=0.5
FORGE_PULLBACK_SCALP_SL_ATR_MULT=1.0
FORGE_PULLBACK_SCALP_TP1_ATR_MULT=0.3
FORGE_PULLBACK_SCALP_TP2_ATR_MULT=0.7
FORGE_PULLBACK_SCALP_COOLDOWN_SECONDS=600
FORGE_PULLBACK_SCALP_MAX_ADX=30
```

Verified in `config/scalper_config.json`:
- `pullback_scalp_enabled = 1` ✓
- `pullback_scalp_lot_factor = 0.5` ✓
- `pullback_scalp_fresh_flip_bars = 3` ✓
- `dump_min_adx = 20` ✓

---

## Parity audit log (OnInit, sim Mar 31 00:00 UTC)

```
FORGE PARITY: mode=TESTER | regime_source=inline_classifier (FORGE.mq5:~5693)
            | trend_strength_atr_threshold=0.2000   ✓
            | regime_h1_override_factor=2.0000      ✓
            | regime_h1_override_adx_min=30.0       ✓
```

Run 19's zero-values anomaly is FIXED in v2.7.31 — audit log moved post-`ReadConfig()`.

---

## Mandatory Housekeeping (compile-time)

| Check | Result |
|-------|--------|
| Check A — dead `FORGE_*` env vars | **PASS** |
| Check A — lowercase config leaks | **PASS** |
| Check B — gate legend coverage | **PASS** |
| `tests/api/test_forge_27x_gates.py` | **28/28 PASS** |
| Codex `/forge-ea-review` | **8 PASS / 2 FAIL** — see Recommendations Issue 1 below |

---

## Run 17 / 18 / 19 / 20 cross-run target table

| Metric | Run 17 (v2.7.22) | Run 18 (v2.7.28) | Run 19 (v2.7.30) | Run 20 target (v2.7.31) |
|---|---|---|---|---|
| Sim window | Apr 1 → May 7 | Mar 31 → Apr 14 stop | Mar 31 → Apr 9 stop | Mar 31 → May 7 |
| TAKEN | 83 | 12 (partial) | 6 (partial) | 90-110 |
| Net P&L | +$5,630 | +$2,713 | +$1,401 (Apr 9 stop) | **+$6,500-$8,000 target** |
| Win rate | 93.3% | 91.6% | ~97% (small N) | ≥ 90% |
| G5048 (Apr 16) | TAKEN −$1,666 | not reached | not reached | **MUST BLOCK** |
| Apr 1 G5001 legs | 5 (RANGE) | 5 | 5 (TREND_BULL but htf-clear failed) | **10 (Fix B)** |
| Apr 2 BB_BOUNCE entries | 2 winners ~$225 | 0 (PSAR blocked) | 0 (PSAR blocked) | **2 BB_PULLBACK_SCALP** |
| Apr 7 BB_BOUNCE SELLs | 2 winners ~$173 | 0 (PSAR blocked) | 0 (PSAR blocked) | **2 BB_PULLBACK_SCALP** |
| Apr 8 BB_BOUNCEs | 8 winners ~$1,250 | 1 (rare alignment) | 1 | **7+ BB_PULLBACK_SCALP** |
| Apr 8 PM dumps | 0 | 0 (gate too tight) | 0 (RR-blocked) | **3-5 MOMENTUM_DUMP_SELL** |
| G5028 (Apr 10) | TAKEN −~$100 | BLOCKED ✓ | BLOCKED ✓ | **STILL BLOCKED** |

---

## Hypothesis tracker

| H | Status | Detail |
|---|---|---|
| H1 — Parity audit log correct values | **PASS** | Verified OnInit log |
| H2 — Fix A: MOMENTUM_DUMP_SELL fires on Apr 8 PM | _pending_ | Sim ~8 days away |
| H3 — Fix B: Apr 1 G5001/G5002 → 10 legs | _pending_ | Sim ~1 day away |
| H4 — Fix C: Apr 2/Apr 7/Apr 8 BB_PULLBACK_SCALP entries fire | _pending_ | Sim ~1 day away |
| H5 — G5028 (Apr 10) STILL BLOCKED | _pending_ | Sim ~10 days away |
| H6 — G5048 (Apr 16) BLOCKED by Filter 1 | _pending_ | Sim ~16 days away |
| H7 — No regression vs Run 17 base case | _pending_ | Sim ~1 day away |

---

## TAKEN Groups (running)

_(none yet — sim in Asian warmup)_

---

## Gate Breakdown (running)

_(too early — only 37 signals)_

---

## Operator Q&A Log

_(empty)_

---

## Recommendations & Open Issues

### Issue 1 — `.env.example` documentation missing for 8 new `FORGE_PULLBACK_SCALP_*` knobs + 16 pre-existing keys (Codex /forge-ea-review 2026-05-11)

**Evidence**: Codex review of v2.7.31 reported `8 PASS / 0 WARNING / 2 FAIL`. Both FAILs are documentation-layer gaps:
1. All 8 `FORGE_PULLBACK_SCALP_*` env vars missing from `.env.example` (Run 20 active vars).
2. 16 pre-existing `FORGE_*` keys fail four-layer audit (`.env.example` → sync → JSON → EA `JsonHasKey`) — examples: `FORGE_BREAKOUT_ADX_MIN`, `FORGE_BOUNCE_ADX_MAX`, `FORGE_FAST_LOCK_MIN_HOLD_SEC_BOUNCE`, `FORGE_QUEUE_ACK_TIMEOUT_SEC`.

**Wiring is CORRECT for all v2.7.31 new vars** — Codex verified:
- `scripts/sync_scalper_config_from_env.py:231-238` — 8 mappings present ✓
- `config/scalper_config.json:252-259` — 8 values written ✓
- `ea/FORGE.mq5:3364-3371` — 8 `JsonHasKey` reads ✓
- `ea/FORGE.mq5:5970-6077` — fork logic consumes the fields ✓

Only `.env.example` is missing the documentation block.

**Impact for Run 20**: zero — runtime config is correct. This is a maintainability / "next person reading .env.example" issue, not a runtime regression.

**Fix**: append v2.7.31 documentation block to `.env.example`. ~30 lines. Will ship post-Run-20 (operator can run during the backtest since `.env.example` isn't read at runtime).

---

## Session Log

| Local | Sim time | Event |
|-------|----------|-------|
| 2026-05-11 15:26 | 2026-03-31 00:00 | **Run 20 launched**. FORGE v2.7.31, aurum_run_id=20, wall_time=593410062. Magic_base=202401. Full additive stack (Fix A + B + C) active. **Parity audit log NOW CORRECT** (Run 19 zero-values anomaly FIXED via post-`ReadConfig()` log position). |
| 2026-05-11 15:32 | 2026-03-31 04:00 | Baseline tick — 37 signals, 0 TAKEN (Asian warmup). Codex `/forge-ea-review` completed: 8 PASS / 2 FAIL (both `.env.example` documentation gaps, no runtime impact). v2.7.31 wiring 100% correct through sync → JSON → EA per Codex audit. Stale FORGE 2.7.6 Run 20 doc archived. |
