# FORGE Regime Predictor — Design Document

**Status**: DRAFT (design discussion 2026-05-11, no code yet)
**Target release**: FORGE v2.7.31+
**Author**: Operator + monitoring agent (chat-derived)
**Predecessor**: v2.7.30 inline H1+H4 EMA classifier (parity baseline, safety-net fallback)
**Cross-references**:
- [`docs/FORGE_RUN18_ANALYSIS.md`](FORGE_RUN18_ANALYSIS.md) — Issue 7 (file-driven regime stream, superseded by this design)
- [`ea/FORGE.mq5:5687-5704`](../ea/FORGE.mq5) — current inline classifier (v2.7.30 parity invariant)
- [`python/regime.py`](../python/regime.py) — existing HMM engine (to be re-tasked as observability-only)
- [`python/scribe.py`](../python/scribe.py) — `market_regimes`, `market_snapshots.regime_*`, `forge_signals.regime_*` schemas

---

## Core framing — regime is *prediction*, not description

The thing we have today (rule-based H1+H4 EMA spread check) answers
**"what does the market look like right now?"** That's *descriptive*.

What FORGE actually needs is a model that answers **"given current features, which
regime will produce profitable trades over the next N bars?"** That's *predictive*.

The model's target variable is forward P&L, not current price action. Training
labels are derived from forward-return windows, not from chart inspection. The
model is evaluated on forward-return correlation, not on label accuracy against
a hand-labeled "ground truth."

This reframing changes the entire architecture:
- Library choice: classification with forward-return targets, not unsupervised clustering
- Training data: 2 years of M5 OHLCV with forward-return-derived labels
- Validation metric: Spearman correlation between predicted regime and forward trade P&L (≥ 0.4 = production-quality)
- Failure mode that matters: predicted regime says TREND_BULL but forward P&L on BUY trades is negative — that's the bug we need to catch

---

## Phased architecture

| Phase | Topic | Decision |
|-------|-------|----------|
| 1 | Data collection | MT5 primary, TV (paid via LENS MCP) secondary enrichment |
| 2 | Analysis library | LightGBM primary (ONNX-exportable); TCN as v2 upgrade candidate |
| 3 | Classification | 4-class multinomial (TREND_BULL/TREND_BEAR/RANGE/VOLATILE) with forward-return labels |
| 4 | Interpretation | Confidence gate + N-bar hysteresis + regime tenure tracking |
| 5 | Transport | ONNX via `OnnxRun()` — native MQL5, sub-ms latency, identical in tester and live |
| 6 | Payload contract | 40-feature MT5 vector + 10 optional LENS-TV enrichment slots; 4-element probability output |

---

## Phase 1 — Data Collection

### Sources

| Source | Quality | Tester | Live | Cost |
|--------|---------|--------|------|------|
| **MT5 broker history** | Deterministic, broker-aligned | ✓ Replay-perfect | ✓ Real ticks | Free |
| **TradingView paid feed (via LENS MCP)** | Different venue, 100-500ms MCP latency, rich indicators | Pre-fetch via Bar Replay (~1h for 2mo M5) | Real-time via MCP | Paid subscription (operator has) |

### Decision: MT5 as primary input source

**Rationale**:
1. Forward P&L is realized on MT5 broker fills. Features must come from the same feed.
2. MT5 history is bit-identical in tester (history replay) and live (current ticks). Zero drift.
3. Native MQL5 indicators are 30+: `iMA`, `iRSI`, `iMACD`, `iBands`, `iATR`, `iADX`, `iStochastic`, `iSAR`, `iCCI`, `iOBV`, `iAlligator`, `iIchimoku`, `iAC`, `iAO`, `iEnvelopes`, etc. More than enough for a strong predictor.
4. No external dependency at inference time.

### TV (paid feed) retained for two specific roles

1. **Validation / ground-truth cross-check** — does TV's regime read agree with our predictor? Drift = warning sign for re-train.
2. **Auxiliary slow-moving features in live** — `tv_recommend`, Pine OB zones, D1 TV bias. Fed into the model as features `[40..49]` with zero-fill in tester. Model trained robust to these being zero.

### Pre-fetch viability for TV historical (Bar Replay)

The LENS MCP wraps `LewisWJackson/tradingview-mcp-jackson` which exposes:
- `replay_start(symbol, tf, date)` — start bar replay at a date
- `replay_step()` — advance one bar
- `data_get_study_values()` — current indicator values (reflects replay timestamp when active)
- `replay_stop()` — return to realtime

Pre-fetch cost: ~200ms/step × 17,500 bars (2 months M5) ≈ 1 hour wall-clock. Acceptable as a one-time job per tester window. Output: append-only JSONL of TV features keyed by timestamp, consumed at training time only (not at inference time — model already trained).

---

## Phase 2 — Analysis Library

### CPU-only constraint

Operator hardware: no dedicated GPU. All training + inference must run on CPU at acceptable speeds.

### Candidate landscape

| Library | Type | CPU latency (40-feat tabular) | ONNX export | Best for |
|---------|------|-------------------------------|-------------|----------|
| **LightGBM** | **Gradient-boosted trees** | **< 1ms** | **✓ `onnxmltools.convert_lightgbm`** | **Pre-engineered tabular features (our case)** |
| XGBoost | Gradient-boosted trees | ~2ms | ✓ `onnxmltools.convert_xgboost` | Same as LGBM, heavier |
| scikit-learn `MLPClassifier` | Feedforward NN | ~1ms | ✓ `skl2onnx` | Simple baseline NN |
| scikit-learn `RandomForestClassifier` | Bagged trees | ~3ms | ✓ `skl2onnx` | Ensemble baseline |
| PyTorch **TCN** | Temporal CNN (dilated causal conv) | 5-15ms | ✓ `torch.onnx.export` | Raw OHLCV sequence input |
| PyTorch LSTM/GRU | Recurrent NN | 10-30ms | ✓ (stateful export tricky) | Long sequences, GPU preferred |
| PyTorch TabNet | Attention tabular NN | 5-20ms | ✓ | Tabular with attention interpretability |
| TabPFN / TabPFN-TS | Pretrained transformer foundation | 50-200ms | ⚠ heavy | Few-shot tabular |

### Decision: LightGBM primary, TCN as v2 candidate

**Why LightGBM wins as primary** (decisive):
- **Sub-ms CPU inference** — fits per-tick budget with margin
- **40-feature tabular input is LightGBM's home turf** — gradient-boosted trees consistently match or beat NNs on tabular data (well-documented across quant finance literature)
- **Bulletproof ONNX export** — `onnxmltools.convert_lightgbm` produces models MQL5's `OnnxRun()` consumes natively (verified in MQL5 Article 12373)
- **SHAP feature importance** — for every prediction we can ask "why did the model say TREND_BULL?" Critical for debugging in production
- **Robust to noise + missing features** — tester gets zeros for TV slots; model handles it gracefully
- **Proven in finance** — most quant funds use gradient boosting for tabular signals; LSTMs are reserved for raw-sequence problems

**Why not LSTM/GRU as primary**:
- Slower CPU inference (5-30ms vs <1ms) — eats backtest performance budget
- Stateful RNN ONNX export is fiddly (you have to manage hidden state across calls externally)
- LSTMs shine when fed **raw OHLCV sequences** (e.g., last 100 bars). Our 40-feature engineered vector is already a compressed representation of that sequence. Letting trees do the work is more efficient.

**Why TCN is the v2 candidate**:
- If LightGBM's forward-return Spearman plateaus < 0.4, TCN is the right next step
- TCN accepts **raw OHLCV sequences** as input (e.g., last 50 M5 bars × 4 OHLCV channels = 200 inputs)
- Learns temporal micro-structure the engineered features can't capture
- Dilated causal convolutions are parallel-friendly on CPU (faster than LSTM)
- ONNX export from PyTorch is direct (`torch.onnx.export(model, dummy_input, "tcn.onnx")`)
- 5-15ms CPU inference still well within budget

**Roadmap**: ship LightGBM in v2.7.31, evaluate on Run 19/20 forward-return correlation; if < 0.4, upgrade to TCN in v2.7.32.

### The stack

```
TRAINING (Python, offline, one-time per re-train cycle):
  pandas, numpy            — data manipulation
  pandas-ta or talib       — indicator feature engineering
  scikit-learn             — train/test split, walk-forward CV, metrics
  lightgbm                 — multi-class classifier
  shap                     — feature importance per-prediction (model audit)
  optuna                   — hyperparameter tuning
  onnxmltools              — export to .onnx
  matplotlib               — diagnostic plots (label distribution, calibration, etc.)

INFERENCE (MQL5, real-time, identical tester+live):
  OnnxRun()                — load .onnx as EA resource, predict per M5 close
                             ~1ms latency, no Python at runtime
```

---

## Phase 3 — Classification

### Output: 4 labels + post-softmax probability vector

LightGBM multi-class returns probabilities directly:

```
probs = [P(TREND_BULL), P(TREND_BEAR), P(RANGE), P(VOLATILE)]
sum(probs) == 1.0
predicted_label = argmax(probs)
predicted_confidence = max(probs)
```

### Label generation — forward-return based (the predictive part)

For each historical M5 bar at time T:
- Forward return:   `R = close(T + N) - close(T)`
- Forward max:      `H = max(high over [T, T+N])`
- Forward min:      `L = min(low over [T, T+N])`
- ATR at T:         `A = atr_14(T)`

Label rules (configurable thresholds):
- `R > +0.5×A AND (H - close(T)) > 0.7×A` → **TREND_BULL** (sustained up-move with meaningful peak)
- `R < -0.5×A AND (close(T) - L) > 0.7×A` → **TREND_BEAR** (sustained down-move with meaningful trough)
- `(H - L) < 0.6×A AND |R| < 0.3×A` → **RANGE** (compressed forward action)
- Otherwise → **VOLATILE** (wide swing with no net directional payoff)

### Parameter choices

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| Label horizon `N` | **24 bars (2h on M5)** | Matches FORGE scalp horizon; smooths intrabar noise |
| Trend R threshold | 0.5 × ATR | Significant net move |
| Trend extension threshold | 0.7 × ATR | Confirms peak/trough, not just drift |
| Range compression | 0.6 × ATR (max-min) | Tight forward range |
| Range drift cap | 0.3 × ATR | (|R|) — no net directional move |

### Training corpus

- **Symbol**: XAUUSD
- **Timeframe**: M5
- **Length**: 2 years (~150k bars after weekends)
- **Train/validation split**: walk-forward CV; train on rolling [Year-2..Year-0.5], validate on most recent [Year-0.5..Year-0]
- **Class balancing**: `class_weight=balanced` (RANGE typically over-represented)
- **Hyperparameter tuning**: Optuna with TPE sampler, ~100 trials on validation slice
- **Re-train cadence**: monthly baseline + on-demand when rolling-window confidence drops below threshold

### Validation metric

**Spearman correlation between predicted regime and forward trade P&L**, NOT raw accuracy. A model that's 90% accurate but uncorrelated with trade outcomes is useless. The hierarchy:

1. **Primary metric**: per-regime forward-return correlation
   - TREND_BULL predictions → positive forward P&L for hypothetical BUY entries (target: ρ ≥ 0.4)
   - TREND_BEAR predictions → positive forward P&L for hypothetical SELL entries (target: ρ ≥ 0.4)
   - RANGE predictions → tighter forward P&L distributions (less directional payoff, lower variance)
   - VOLATILE predictions → wider P&L distributions (higher variance, low directional bias)
2. **Secondary metrics**: macro-F1, per-class precision/recall, confusion matrix
3. **Operational metric**: prediction stability — how often does `argmax` flip vs. previous bar? (target: < 10% flips at confidence ≥ 0.65)

---

## Phase 4 — Interpretation

Raw `argmax` is noisy at regime boundaries. Three filters before committing to `g_regime_label`:

### 1. Min-confidence gate

```
if max(probs) < FORGE_REGIME_MIN_CONFIDENCE:   # default 0.55
    hold previous label
```

### 2. N-bar hysteresis

```
require N consecutive bars predicting the same new label  # default N=3 (15min on M5)
before flipping g_regime_label
```

### 3. Tenure tracking

```
g_regime_age_bars = bars since last flip
transition_flag = true exactly on the flip bar
```

### FORGE-side enriched regime state

```c++
struct RegimeState {
   string   label;           // "TREND_BULL" | "TREND_BEAR" | "RANGE" | "VOLATILE"
   double   confidence;      // max(probs)
   double   probs[4];        // full distribution for downstream decisions
   int      age_bars;        // tenure in current label
   bool     transition;      // flipped on this bar?
   string   next_likely;     // 2nd-highest label (transition hint)
   datetime stamp;           // time of prediction
};
```

### Examples of FORGE consuming the enriched state

- `label=TREND_BULL && confidence ≥ 0.80 && age_bars ≥ 12` → fire full 10-leg ladder
- `label=TREND_BULL && confidence < 0.60` → conservative 3-leg cap
- `transition=true && new_label != prior_direction` → cancel pending orders on the prior direction
- `next_likely=VOLATILE && confidence drops below 0.60 over 3 bars` → tighten ATR trail in anticipation
- `label=RANGE && age_bars ≥ 20` → enable BB_BOUNCE setup family, disable BB_BREAKOUT

---

## Phase 5 — Transport: HTTP vs ONNX

### Comparison

|                    | HTTP via `WebRequest()` | ONNX via `OnnxRun()` |
|--------------------|-------------------------|----------------------|
| Tester support     | Works but adds 5-50ms/tick → slows backtests 10-100× | **Identical to live** — in-process |
| Live latency       | 5-50ms (localhost)      | **< 1ms** (in-process) |
| Network dependency | Python service must run | None |
| Failure mode       | Service down → trading blocked or fallback | Model file missing → fallback to inline |
| Model size limit   | n/a (model lives in service) | 1GB embeddable as EA resource (MT5 build 5572+, Jan 2026) |
| Parity guarantee   | ❌ — wall-clock-bound tester paths differ | ✓ — bit-identical inference |
| Versioning         | Server-side route       | File-versioned (`regime_model_v1.onnx`, `regime_model_v2.onnx`) |
| CUDA support       | Service-side (irrelevant for CPU) | Optional in MT5 build 5572+ (we don't need it) |

### Decision: ONNX, no contest

MQL5 has native `OnnxRun()` since 2023; mature in 2026. Build 5572 (released Jan 30, 2026) added CUDA support, which we don't need — CPU inference of a LightGBM ONNX model is sub-ms.

**ONNX wins on every axis that matters for this design**:
- Zero network latency in tester
- No service dependency
- Bit-identical inference in tester and live (deterministic given same input)
- File-versioned model, hot-swappable via env flag

### HTTP retained for secondary roles only

1. **Live-mode LENS TV enrichment fetch** — slow cadence (60s), only affects features `[40..49]` which the model is trained robust to (zero in tester)
2. **Hot-reload signal** — Python tells EA "new model file is ready" via WebRequest poll; EA reloads on next tick
3. **Model audit logging** — EA POSTs prediction feature vectors + outputs to Python for offline replay / debugging (live only, fire-and-forget)

None of these secondary roles affect regime decisions. ONNX is authoritative.

---

## Phase 6 — Payload + Data Exchange Contract

### Input feature vector (MQL5 → ONNX)

**Fixed order, 50 slots** (40 MT5 + 10 TV-enrichment). Order MUST match training-time feature order; canonical order lives in `config/regime_model_metadata.json` and is validated at `OnInit`.

```c++
// FORGE.mq5 — feature vector schema
double features[50];

// === MT5 features (40) — primary input, identical tester+live ===

// Trend (10 features)
features[0]  = (M5_EMA20  - M5_EMA50)  / M5_ATR;
features[1]  = (M15_EMA20 - M15_EMA50) / M15_ATR;
features[2]  = (H1_EMA20  - H1_EMA50)  / H1_ATR;
features[3]  = (H4_EMA20  - H4_EMA50)  / H4_ATR;
features[4]  = (M5_EMA50  - M5_EMA200) / M5_ATR;
features[5]  = (H1_EMA50  - H1_EMA200) / H1_ATR;
features[6]  = M5_PSAR_direction;          // +1 above / -1 below
features[7]  = M5_MACD_histogram / M5_ATR;
features[8]  = M5_MACD_signal_cross;        // -1 / 0 / +1
features[9]  = H1_trend_slope;             // existing g_h1_trend

// Momentum (8)
features[10] = (M5_RSI14  - 50.0) / 50.0;
features[11] = (M15_RSI14 - 50.0) / 50.0;
features[12] = (H1_RSI14  - 50.0) / 50.0;
features[13] = M5_Stoch_K  / 100.0;
features[14] = M5_Stoch_D  / 100.0;
features[15] = (M5_Stoch_K - M5_Stoch_D) / 100.0;
features[16] = M5_ADX14;
features[17] = (M5_DIplus - M5_DIminus) / 100.0;

// Volatility (10)
features[18] = M5_ATR14;
features[19] = M15_ATR14;
features[20] = H1_ATR14;
features[21] = M5_BB_width_percentile_50bar;
features[22] = (close - M5_BB_mid) / (M5_BB_upper - M5_BB_mid);   // BB position ∈ [-1, +1]
features[23] = realized_vol_5;
features[24] = realized_vol_20;
features[25] = realized_vol_50;
features[26] = (high - low) / M5_ATR;
features[27] = MathAbs(close - open) / (high - low + 1e-9);       // body/range ratio

// Returns (5)
features[28] = log(close(t) / close(t-1));
features[29] = log(close(t) / close(t-5));
features[30] = log(close(t) / close(t-20));
features[31] = log(close(t) / close(t-60));
features[32] = z_score(return_1, lookback=50);

// Time/session (7)
features[33] = session_code;                          // 0=OFF, 1=Sydney, 2=Asian, 3=London, 4=Lon+NY, 5=NY
features[34] = sin(2*M_PI * hour_of_day_utc / 24.0);
features[35] = cos(2*M_PI * hour_of_day_utc / 24.0);
features[36] = day_of_week;                           // 0=Mon..6=Sun
features[37] = bars_since_session_open;
features[38] = is_news_window;                        // 0/1
features[39] = bars_since_last_volatility_spike;

// === LENS-TV enrichment (10) — live-only, zero-filled in tester ===
features[40] = tv_recommend;                  // -1..+1 from TV technical summary
features[41] = tv_recommend_d1;               // daily TF
features[42] = tv_recommend_h1;
features[43] = tv_recommend_oscillators_m5;
features[44] = tv_recommend_movavg_m5;
features[45] = pine_ob_zone_distance_above;   // points to nearest order block above
features[46] = pine_ob_zone_distance_below;
features[47] = pine_supply_demand_zone_proximity;
features[48] = lens_volume_profile_skew;
features[49] = reserved;                      // free slot for future
```

### Output vector (ONNX → MQL5)

```c++
double probs[4];   // [P_BULL, P_BEAR, P_RANGE, P_VOLATILE]
                   // post-softmax — sums to 1.0 (LightGBM ONNX adds softmax in graph)
OnnxRun(g_regime_model, ONNX_DEFAULT, features, probs);
```

### Files on disk (production paths)

```
config/
├── regime_model.onnx                       # ← current model (symlink to versioned)
├── regime_model_v2026-05-11.onnx           # ← versioned snapshot (immutable, checked in)
├── regime_model_metadata.json              # ← schema contract:
│                                           #     { feature_names: [...50],
│                                           #       label_names:   ["TREND_BULL", "TREND_BEAR", "RANGE", "VOLATILE"],
│                                           #       trained_at:    "2026-05-11T12:00Z",
│                                           #       train_corpus:  "XAUUSD M5 2024-05 to 2026-04",
│                                           #       train_metrics: { macro_f1: 0.78,
│                                           #                        fwd_return_spearman_bull: 0.47,
│                                           #                        fwd_return_spearman_bear: 0.43,
│                                           #                        ... },
│                                           #       label_horizon_bars: 24,
│                                           #       atr_period: 14 }
└── regime_train_log.jsonl                  # ← append-only: every (re)train event with metrics
```

### Env-tunable knobs (default-OFF for safe rollout)

```
# Regime predictor master switch
FORGE_REGIME_USE_ONNX=0                       # default OFF; ON = ONNX authoritative

# Model location
FORGE_REGIME_MODEL_FILE=config/regime_model.onnx

# Inference filters
FORGE_REGIME_MIN_CONFIDENCE=0.55              # min posterior to commit to new label
FORGE_REGIME_HYSTERESIS_BARS=3                # consecutive bars required to flip

# TV enrichment
FORGE_REGIME_TV_ENRICHMENT_ENABLED=0          # tester: 0; live: opt-in via LENS
FORGE_REGIME_TV_ENRICHMENT_POLL_SECONDS=60

# Diagnostics
FORGE_REGIME_ONNX_PROFILING=0                 # MT5 ONNX_ENABLE_PROFILING flag
FORGE_REGIME_AUDIT_HTTP_URL=                  # empty = no audit POST; else POST per prediction
```

### Failure modes + fallbacks

| Failure | Detection | Fallback |
|---------|-----------|----------|
| `.onnx` file missing or corrupt | `OnnxRun` returns error | Disable file-driven path; fall back to v2.7.30 inline classifier; log WARN |
| Feature count mismatch | `OnInit` validates `metadata.json::feature_names.length` matches model input shape | Same as above |
| TV enrichment service down | Last-good-time stale > N seconds | Zero-fill TV slots (model trained robust); log INFO |
| Model accuracy degraded | Rolling-window forward-P&L correlation < threshold | Alert; trigger re-train pipeline; do NOT auto-fallback (operator decides) |

---

## Open decisions before code

| # | Decision | Default | Why default |
|---|----------|---------|-------------|
| 1 | Label horizon `N_bars` | **24 bars (2h)** | Matches FORGE scalp horizon; smooths intrabar noise |
| 2 | Training corpus length | **2 years** | Enough regime variety, recent enough to be relevant |
| 3 | Number of classes | **4 (current)** | FORGE compat; expand to 6 (Strong/Weak Bull/Bear) only if validation shows clear separation |
| 4 | Confidence threshold | **0.55** | Above 1/4=0.25 random; below 0.65 to avoid over-blocking |
| 5 | Hysteresis bars | **3 (15min)** | Filters 1-bar noise without lagging real regime turns |
| 6 | LightGBM `num_leaves` | **31** | Conservative; tune via Optuna |
| 7 | LightGBM `learning_rate` | **0.05** | Slow + many rounds for stability |
| 8 | Re-train cadence | **monthly + on-demand** | Detect non-stationarity quickly without thrashing |

---

## Build order — v2.7.31

| # | Deliverable | File | Effort | Blocks |
|---|-------------|------|--------|--------|
| 1 | Forward-return label generator | `python/label_regime_history.py` (new) | 4-6h | #2 |
| 2 | Training pipeline | `python/train_regime_model.py` (new) | 1-2 days | #4 |
| 3 | EA feature builder (40 MT5 features) | `ea/FORGE.mq5` — `BuildRegimeFeatureVector()` | 4-6h | #4 |
| 4 | EA ONNX integration | `ea/FORGE.mq5` — `OnInit` load + `OnTimer/OnTick` infer + hysteresis | 1 day | #5 |
| 5 | Backward-compat flag + fallback to inline | `ea/FORGE.mq5` | 2h | #6 |
| 6 | Validation harness — fwd-P&L correlation report | `python/validate_regime_model.py` | 1 day | — |
| 7 | TV enrichment HTTP endpoint (live only) | `python/regime_enrichment.py` | 0.5 day | optional |
| 8 | Wire all `FORGE_REGIME_*` env vars through sync → JSON → EA | `scripts/sync_scalper_config_from_env.py`, `.env.example`, `config/scalper_config.defaults.json` | 2h | #4 |

**Total**: ~5-7 days of focused work.

**Default state at v2.7.31 ship**: `FORGE_REGIME_USE_ONNX=0` — inline classifier remains authoritative. Operator validates ONNX model on a tester run, then flips the flag for Run 20+.

---

## Validation plan (Run 20 — first full ONNX evaluation)

1. **Pre-flight**: train model on 2024-05 → 2026-03 (held out 2 months for validation). Validate on 2026-03 → 2026-05. Require:
   - macro-F1 ≥ 0.65
   - Forward-return Spearman ≥ 0.40 (BULL and BEAR classes)
   - Prediction stability ≥ 0.85 (1 - flip rate) at confidence ≥ 0.65

2. **Backtest**: same window as Run 18 (Mar 31 → May 7), `FORGE_REGIME_USE_ONNX=1`. Compare to:
   - Run 17 (v2.7.22 baseline)
   - Run 18 (v2.7.28 + Filter 1 only)
   - Run 20 (v2.7.31 ONNX regime)

3. **Acceptance criteria for promotion to live**:
   - Run 20 P&L ≥ Run 17 P&L (no regression)
   - G5048 (Apr 16 BB_BREAKOUT BUY −$1666) is BLOCKED in Run 20 by regime gate
   - At least one previously-blocked legitimate winner (e.g. Apr 2 G5003/G5004 BB_BOUNCE) is NOW UNBLOCKED by ONNX regime
   - Total trade frequency within ±25% of Run 18 (not over-blocking, not over-firing)

4. **Live shadow mode** (1-2 weeks): `FORGE_REGIME_USE_ONNX=1` in live, but log predictions without acting on them — compare to inline classifier output. Acceptance: ≥ 80% label agreement on calm sessions, divergent only on edge cases that match expected ONNX advantages.

5. **Promotion to live entry gate**: only after items 1-4 pass.

---

## Sources (research dated 2026-05-11)

### MQL5 ONNX runtime + transport
- [MQL5 — ONNX models documentation](https://www.mql5.com/en/docs/onnx)
- [MQL5 — Creating an ONNX model](https://www.mql5.com/en/docs/onnx/onnx_prepare)
- [MQL5 — ONNX support overview](https://www.mql5.com/en/docs/onnx/onnx_intro)
- [MQL5 — How to use ONNX models in MQL5 (Article 12373)](https://www.mql5.com/en/articles/12373)
- [MQL5 — Mastering ONNX: Game-Changer for MQL5 Traders (Article 13394)](https://www.mql5.com/en/articles/13394)
- [MetaTrader 5 Build 5572 — ONNX + CUDA improvements (Jan 30 2026)](https://www.metatrader5.com/en/releasenotes/terminal/2426)
- [MegaJoctan/ONNX-MQL5 — example deployment repo](https://github.com/MegaJoctan/ONNX-MQL5)
- [MQL5 — ONNX Strategy 1 blog post (Apr 2026)](https://www.mql5.com/en/blogs/post/768537)

### MQL5 WebRequest (secondary HTTP channel)
- [MQL5 — WebRequest network function docs](https://www.mql5.com/en/docs/network/webrequest)
- [MQL5 — Mastering API and WebRequest in MQL5 (Article 17774)](https://www.mql5.com/en/articles/17774)
- [MQL5 — Connexus WebRequest framework (Article 15795)](https://www.mql5.com/en/articles/15795)
- [MQL5 — Python access to MetaTrader 5 market streams (Article 19065)](https://www.mql5.com/en/articles/19065)

### Tabular ML libraries (CPU-only)
- [XGBoost & LightGBM for Time Series Forecasting (365 Data Science)](https://365datascience.com/tutorials/python-tutorials/xgboost-lgbm/)
- [Gradient Boosting comparison: sklearn / XGBoost / LightGBM / CatBoost (MachineLearningMastery)](https://machinelearningmastery.com/gradient-boosting-with-scikit-learn-xgboost-lightgbm-and-catboost/)
- [LightGBM Python API documentation](https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMClassifier.html)
- [XGBoost Time Series Forecasting tutorial](https://machinelearningmastery.com/xgboost-for-time-series-forecasting/)
- [Skforecast — gradient boosting for time series](https://skforecast.org/0.14.0/user_guides/forecasting-xgboost-lightgbm.html)
- [scikit-learn MLPClassifier docs](https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPClassifier.html)

### Neural network options for time series (CPU)
- [LSTM for Time Series Prediction in PyTorch (MachineLearningMastery)](https://machinelearningmastery.com/lstm-for-time-series-prediction-in-pytorch/)
- [PyTorch Forecasting library (sktime)](https://github.com/sktime/pytorch-forecasting)
- [Temporal Convolutional Networks and Forecasting (Unit8)](https://unit8.com/resources/temporal-convolutional-networks-and-forecasting/)
- [Darts library — TCN model](https://unit8co.github.io/darts/generated_api/darts.models.forecasting.tcn_model.html)
- [Optimizing TCN inference on edge devices (arXiv:2005.03775)](https://arxiv.org/pdf/2005.03775)
- [Nixtla TCN model docs](https://nixtlaverse.nixtla.io/neuralforecast/models.tcn.html)
- [TabNet for financial prediction (GitHub)](https://github.com/ginoitaliano/TabNet_Pred_Financial)
- [TabPFN — Tabular Foundation Models](https://priorlabs.ai/tabpfn)
- [From Tables to Time: TabPFN-v2 for Time Series Forecasting (arXiv:2501.02945)](https://arxiv.org/abs/2501.02945)

### Regime detection patterns
- [QuantStart — Market Regime Detection using HMM](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/)
- [QuantInsti — Regime-Adaptive Trading with HMM + Random Forest](https://blog.quantinsti.com/regime-adaptive-trading-python/)
- [QuantInsti — Market Regime Detection HMM project](https://blog.quantinsti.com/market-regime-detection-hidden-markov-model-project-fahim/)
- [LSEG — Market Regime Detection statistical and ML approaches](https://developers.lseg.com/en/article-catalog/article/market-regime-detection)
- [statsmodels — Markov switching regression docs](https://www.statsmodels.org/dev/examples/notebooks/generated/markov_regression.html)
- [statsmodels — MSDR tutorial](https://gist.github.com/sachinsdate/1307f7b487aaf947c626b5d0e2c30c4f)
- [Time Series Reasoning — MSDR explanation](https://timeseriesreasoning.com/contents/markov-switching-dynamic-regression-model/)
- [ruptures GitHub — change-point detection](https://github.com/deepcharles/ruptures)
- [arXiv:1801.00826 — ruptures paper](https://arxiv.org/abs/1801.00826)
- [HackerNoon — CPD for market turning points](https://hackernoon.com/detecting-market-turning-points-with-change-point-detection-in-python)

### Multi-factor rule-based regime classifiers
- [Auric Regime Classifier on TradingView](https://www.tradingview.com/script/ZjvidEM8-Auric-Regime-Classifier-JOAT/)
- [ADX + Bollinger Bands forex framework (CMS Prime)](https://medium.com/@cmsprime/adx-bollinger-bands-a-quantitative-framework-for-forex-trend-and-volatility-tactics-29e197ac1283)
- [Regime-Filtered Trend Strategy (PyQuantLab)](https://pyquantlab.medium.com/regime-filtered-trend-strategy-a-market-adaptive-trend-following-system-fa933e001237)
- [MQL5 Article 20097 — Multi-Timeframe Harmony Index](https://www.mql5.com/en/articles/20097) (referenced in Issue 1 of Run 18 analysis)

### TradingView MCP integration
- [LewisWJackson/tradingview-mcp-jackson — fork with morning brief workflow](https://github.com/LewisWJackson/tradingview-mcp-jackson)
- [TradingView — Bar Replay how-to](https://www.tradingview.com/support/solutions/43000712747-bar-replay-how-and-why-to-test-a-strategy-in-the-past/)

---

## Historical Q&A — Regime Discussion Thread

> Moved from `docs/FORGE_RUN18_ANALYSIS.md`. Captures the running conversation
> between operator and the monitoring agent during the v2.7.27 → v2.7.30 ship cycle
> and the v2.7.31+ design discussion. Each entry preserves the rationale behind
> every fix proposal and design decision.

### Q8 (Run 18 monitoring): "let us discuss the regime classifier — is it running now and passing data for forge?"
**Finding**: `regime.py` NOT running (empty ps output). FORGE doesn't read it in tester anyway (`if(!in_tester)` gate at `FORGE.mq5:1080`). Tester uses inline H1+H4 EMA-spread classifier at lines 5658-5661 (later moved to 5687+ via v2.7.29, then unconditional via v2.7.30). → Pre-design Issue 1 below.

### Q9 (Run 18 monitoring): "so python/regime.py is never used by forge ... let us focus on fixing the inline regime classifier"
**Finding**: Confirmed scope. Drafted 3 options (A, B, C) for the inline fix. → See "Pre-design Issue 1" below.

### Q10 (Run 18 monitoring): "can you do a google search on how to do this in MT5?"
**Finding**: Industry pattern is **weighted harmony index** (per MQL5 article 20097): bias per TF (+1/0/-1), weighted average, threshold-based label. Self-Aware Trend System uses Kaufman Efficiency Ratio as adaptive width. Veto patterns (RSI multi-TF) use slow TF only when STRONGLY opposing. **No canonical pattern uses unanimous-AND across timeframes** — FORGE is the outlier. → See Option C "weighted harmony" in Pre-design Issue 1.

Sources captured in the response:
- MQL5 Article 20097 (Multi-Timeframe Harmony Index)
- mql5.com/en/code/72247 (Self-Aware Trend System)
- mql5.com/en/code/21399 (ADX multi-TF smoothed)
- mql5.com/en/blogs/post/767332 (RSI multi-TF for scalping, Feb 2026)
- mql5.com/en/blogs/post/769705 (Break Tracer EMA+ATR)
- mql5.com/en/blogs/post/769330 (Adaptive SuperTrend confluence)

### Q3b (Run 18 sim Apr 8, repeated): "Look at the prices before and after and the duration of the price movement — if the first trade in london session on april 1 were perfect setup, why didn't fire more legs in that group?"
**Investigation**: Re-pulled SIGNALS for 07:00 → 12:00 on Apr 1 (5-min granularity); pulled G5001 (magic 207402) trade timeline.
**Evidence — pre-entry buildup (100 min)**:
- 07:20 low at 4669 (RSI=26.7, ADX=43.8) → 08:40 entry at 4700.47 (+31 pts in 80 min)
- PSAR flipped BELOW at 07:55 — **45 min before entry** (confirmed reversal, not whipsaw)
- ADX trajectory: 23.4 → 47.9 (peak at 07:30) → 40.1 at entry
- RSI: 39.6 → 73.3 (full oversold-to-overbought sweep)
- BB bands EXPANDING (lower: 4679 → 4663)
- H1 trend constant +2.05 to +2.26 throughout
- `regime_label = RANGE` for entire pre-entry window
**Evidence — post-entry move (120 min to peak)**:
- 08:41:22: +2.6 pts → 2 TP1 wins ($37.92)
- 08:47:12: −7 pts → 1 leg SL'd (−$37.20)
- 09:00: −16.2 pts MAX ADVERSE EXCURSION (the pullback)
- 09:50: +24.9 (past Run 17's TP3 at +9pts)
- **10:40: peak +40.8 pts = 8.1×ATR**
- 11:40: +37.6 (second push)
- 12:00: regime_label finally flips to TREND_BULL — **3h 20m after entry**, after the move was over
**G5001 leg detail**: 5 legs × 0.08 = 0.40 lots total. 2 TP1 wins ($38), 2 TP2-target legs (~$59 base magic), 1 SL (−$37). Net ≈ +$60.
**Answer**: Setup was perfect AND market validated it (+41 pts, 8.1×ATR). EA fired only 5 legs because `regime_label = RANGE` from the inline classifier. Classifier requires BOTH `h1_bull` AND `(h4_bull || h4_flat)` for TREND_BULL. H4 EMA20-EMA50 was still NEGATIVE (h4_bear=TRUE), so the AND fails despite h1_trend=+2.15. H4 lags H1 by 3-5 hours after regime turns. Money left on table: estimated **$100-250** of unrealized gains across the 5 missing legs at peak prices.
**Forward link**: Pre-design Issue 1 below — shipped as v2.7.29 (Option A H1-strong override).

### Q16 (chat 2026-05-11 post-stop): "I want the regime calculation to be fixed for both live and testing — this sim is useless if testing results and config for logic evaluation cannot be applied to live trades."
**Investigation**: Audited the EA regime path. Found `if(in_tester) { ... }` wrapper at `FORGE.mq5:5687-5700` around the inline H1+H4 classifier — meaning the classifier ran only in tester mode, while live mode read `regime_label` from `config.json` (written by BRIDGE).
**Evidence**: Tester run with `FORGE_REGIME_H1_OVERRIDE_FACTOR=2.0` would have one behavior; live run would have entirely different behavior (BRIDGE-driven label, potentially HMM-based via regime.py). Any backtest-tuned override knobs were dead in live.
**Answer**: Shipped **v2.7.30** — removed the `if(in_tester)` wrapper so the inline classifier (with the v2.7.29 override clause) runs unconditionally in both modes. JSON-read at `:1094-1099` becomes advisory only. VERSION bumped, `FORGE.mq5:63` → "2.7.30", `make forge-compile` PASS, housekeeping A+B PASS, 28/28 gate tests PASS. **Parity invariant codified at `FORGE.mq5:64`** (banner block) and audit log at `OnInit` printing `FORGE PARITY:` with regime knob values.
**Forward link**: Phase 5 (ONNX transport) supersedes the file-driven stream approach (originally proposed in Pre-design Issue 7) because ONNX gives bit-identical inference in tester and live without external dependencies.

### Q17 (chat 2026-05-11): "Is regime.py currently wired to forge EA? What is the mechanical relationship?"
**Investigation**: Traced regime.py → bridge.py → config.json → FORGE.mq5 path. Mapped all consumers of the regime label inside the EA.
**Evidence**:
- `python/regime.py` is alive — `RegimeEngine` (HMM primary + Gaussian fallback) instantiated in `bridge.py:912`
- `bridge.py:5006-5012` writes `regime_label`, `regime_confidence`, `regime_apply_entry_policy`, `regime_countertrend_min_confidence` into `MT5/config.json` every BRIDGE cycle
- `FORGE.mq5:1094-1108` reads those 4 keys but ONLY inside `!in_tester` branch
- After v2.7.30, the inline classifier at `FORGE.mq5:5693-5704` runs unconditionally and overwrites `g_regime_label` every tick — **regime.py output is plumbed but discarded for FORGE entry decisions**
- regime.py output STILL used by: `bridge.py:2386,2399` (system events), `scribe.py:175-194` (`market_regimes` table), `scribe.py:106,144,214,247` (`market_snapshots`/`forge_signals`/`signals_received`/`trade_groups` regime columns), `athena_api.py:407,760,771` (`/api/regime/*` endpoints for Athena UI)
**Answer**: regime.py is **alive for observability** (Athena dashboards, AURUM intelligence, SCRIBE history) but **bypassed for FORGE entry decisions** after v2.7.30. The inline H1+H4 classifier with `regime_h1_override_factor` is the single source of truth on both tester and live.
**Forward link**: Phases 1-6 of this doc — ONNX-driven predictor that replaces both the inline classifier and the regime.py runtime role for FORGE entries (regime.py retained for observability).

### Q18 (chat 2026-05-11): "Let us review python/regime.py and confirm if it is structurally aligned with what we expect — remember we have extended scribe — and how is regime calculated in regime.py. Does it have the right payload and schema needed by FORGE?"
**Investigation**: Full read of `python/regime.py` (656 lines). Mapped `RegimeSnapshot.to_dict()` keys against `FORGE.mq5` consumers and `scribe.py` table columns.
**Evidence — calculation method**:
- 11-feature vector built at `regime.py:257-269`: `[ret_1, volatility, ema_spread, adx, bb_width, spread, session_code, rsi_centered, macd_hist, tv_recommend, lens_price_delta]`
- Indicators sourced M5 → M15 → H1 (first non-zero wins) at `:186-206`
- LENS (TradingView) data merges in when fresh (<90s) at `:208-238`
- HMM primary: GaussianHMM with `REGIME_HMM_COMPONENTS=3` states, `predict_proba` → max posterior wins (`:473-497`)
- State→label map at `:311-346`: `mean_adx ≥ 25 ∧ ema_spread>0 ∧ ret>0` → TREND_BULL; mirror → TREND_BEAR; `mean_adx ≥ 25` ambiguous → VOLATILE; `vol > vol_med × 1.25` → VOLATILE; else RANGE
- Gaussian fallback at `:500-549` for when HMM untrained (<120 samples)
**Evidence — schema alignment**:

| FORGE consumer | Source | Status |
|---|---|---|
| `regime_label` (`FORGE.mq5:1094`) | `bridge.py:5006` | ✓ aligned |
| `regime_confidence` (`:1099`) | `:5008` | ✓ aligned |
| `regime_apply_entry_policy` (`:1103`) | `:5009-5011` | ✓ aligned |
| `regime_countertrend_min_confidence` (`:1107`) | `:5012` | ✓ aligned |
| Label vocabulary {TREND_BULL/TREND_BEAR/VOLATILE/RANGE} | `regime.py:336-345`, `:530-548` | ✓ aligned |
| SCRIBE `market_regimes` table | `scribe.py:175-194` | ✓ aligned (all 17 RegimeSnapshot fields covered) |
| SCRIBE `signals_received.regime_*` | `scribe.py:214-219` | ✓ aligned |
| SCRIBE `market_snapshots.regime_*` | `scribe.py:106-108` | ✓ aligned |
| Athena `/api/regime/*` | `athena_api.py:407,760,771` | ✓ aligned |

**Answer**: **Schema is correct.** Payload + label vocabulary aligned across all consumers. Functional integration is the gap. Three structural gaps separate from schema:
1. BRIDGE doesn't run during MT5 Strategy Tester → regime.py can't be evaluated in tester.
2. Timeframe mismatch — regime.py is M5-first; FORGE inline is H1+H4 (different views).
3. Confidence semantics diverge — regime.py emits real HMM posterior; FORGE inline hardcodes 1.0 at `:5704`, defeating `regime_countertrend_min_confidence` threshold check at `:4015`.
**Forward link**: Phase 5 (ONNX) — runs in-EA in both modes, solving all three gaps. Phase 6 contract — designed to be SCRIBE-compatible so observability layer keeps working unchanged.

### Q19 (chat 2026-05-11): "We need a switch to toggle which data sources to use. MT5 data for both live and backtest is okay. But we have no way of fetching regime from TradingView — should we look at MCP first?"
**Investigation**: Surveyed historical TradingView data availability. Checked LENS MCP integration at `python/lens.py`.
**Evidence**:
- TradingView's public REST APIs do NOT expose historical bar-by-bar indicator data
- `tradingview-ta` library returns CURRENT snapshot only
- TV's "Recommendation" rating is computed on-demand from OHLCV — not archived, must be recomputed
- All ~26 input indicators (MAs, RSI, MACD, Stoch, ADX, CCI, etc.) are computable from raw OHLCV
- LENS at `python/lens.py:29` wraps `LewisWJackson/tradingview-mcp-jackson` MCP
- LENS-derived features (`tv_recommend`, `lens_rsi`, `lens_macd_hist`, `lens_price_delta`) are non-zero only when LENS fresh (`regime.py:228`); HMM trained on full 11-vector becomes mis-calibrated when these go to zero
**Answer**: My initial read was that no MCP would help. After Q20 below, the answer changed — the MCP DOES support historical via Bar Replay. But the structural conclusions hold:
- Make regime.py MT5-only by default
- Trim LENS-dependent features when LENS off
- Use TradingView MCP for pre-fetch when available (replay mode)
**Forward link**: Phase 1 in this doc — MT5 primary, TV secondary enrichment.

### Q20 (chat 2026-05-11): "LENS already communicates with our TradingView MCP — and it can fetch data."
**Investigation**: Re-read `python/lens.py` and the MCP server source at `~/tradingview-mcp-jackson/src/server.js`. Enumerated all exposed tools.
**Evidence**: TV MCP exposes 20+ tools including:
- `data_get_ohlcv` — OHLCV bars from current chart view (historical)
- `data_get_indicator` / `data_get_study_values` — indicator info + values
- `data_get_pine_lines` / `data_get_pine_boxes` — Pine indicator levels/zones
- `batch_run` — run an action across multiple symbols/timeframes
- **`replay_start`** — bar replay mode at a specific date
- **`replay_step`** — advance one bar in replay
- **`replay_autoplay`** — autoplay with speed control
- **`replay_stop`** — return to realtime
- **`replay_status`** — current replay state
**Answer**: I was wrong. The MCP DOES expose historical access via **Bar Replay**. `replay_start(date=X)` + `replay_step()` + `data_get_study_values()` after each step gives historical indicator values bar-by-bar for any date range. In replay mode the chart freezes at the replay timestamp; all study values reflect that historical bar. So the operator's "fetch trading data for [FromDate-1, EndDate+1]" routine IS implementable.
**Forward link**: Phase 1 — TV enrichment via Bar Replay pre-fetch is now part of the secondary feature path; tester gets zeros for TV slots, live gets the real values via LENS MCP cache.

### Q21 (chat 2026-05-11): "What is regime in forex trading?"
**Investigation**: Educational question — answered from systematic-trading canon.
**Answer**: A regime is the prevailing behavioral state of price action over a lookback window. The same instrument behaves differently in different regimes; strategies that win in one lose in another. Four canonical labels: TREND_BULL (HH/HL, EMA20>EMA50, ADX≥25, RSI>50), TREND_BEAR (mirror), RANGE (ADX<20, EMAs flat, BB compressed), VOLATILE (high vol, wide BB, direction unstable). Regime affects FORGE through three levers: filter (block setups in wrong regime), size (reduce lots in unfavorable regime), TP geometry (TP4/TP5 only arm in TREND/VOLATILE per `FORGE.mq5:1790-1792, :1839-1841`; leg count capped in RANGE per `:7408`).
**Forward link**: Phase 3 (classification) — same vocabulary preserved; LightGBM 4-class output → these 4 labels.

### Q22 (chat 2026-05-11): "Regime calculation is an analysis that happens to predict — let us focus in phases: data collection, analysis library (CPU-only, including neural networks), classification, interpretation, HTTP vs ONNX, payload contract."
**Investigation**: WebSearch across CPU-only ML libraries, neural network options (LSTM/GRU/TCN/TabNet/TabPFN), MQL5 ONNX runtime, MQL5 WebRequest, TradingView MCP Bar Replay tools.
**Evidence (summarized in Phases 1-6 above)**:
- Predictive framing changes model objective: forward-return labels, not chart-inspection labels
- LightGBM wins on CPU tabular inference (<1ms, ONNX-exportable, SHAP-interpretable)
- ONNX wins on MQL5 transport (in-process, sub-ms, identical tester+live, native since 2023, build 5572 Jan 2026 added CUDA)
- HTTP retained only for live-side enrichment + audit logging
- 40-feature MT5 input vector + 10 optional TV-enrichment slots; 4-element softmax output
**Answer**: This entire design doc is the answer. Phase 1-6 lock the architecture. Five open decisions to operator (label horizon, training corpus, num classes, confidence threshold, hysteresis bars). All sources cited in the Sources section.
**Forward link**: This doc supersedes Pre-design Issues 1 and 7 below.

---

## Pre-design Proposals (Superseded — kept for historical context)

> These proposals were drafted during the Run 18 monitoring session and the
> v2.7.27-v2.7.30 ship cycle. Issue 1 was shipped as v2.7.29 (Option A) and is
> still active as the fallback classifier in v2.7.30. Issue 7 was the precursor
> design for the file-driven regime stream — superseded by the ONNX-in-EA
> decision in Phase 5 above (ONNX wins on parity, latency, and dependency).

### Pre-design Issue 1 — Inline regime classifier H4 lag → over-conservative leg sizing

**Status**: **Option A shipped as v2.7.29** (H1-strong override). Now the fallback in v2.7.30. Option C (weighted harmony) was the preferred long-term fix but was superseded by the ONNX predictor in this doc's Phase 2.

**Evidence**:
- Apr 1 08:40 G5001 entry: `h1_trend = +2.15` (very bullish), `m5_adx = 40.1`, `psar = BELOW`, `regime_label = RANGE`. Only **5 legs** fired (capped at `native_legs_max_when_unclear=5`) instead of the 10-leg max (`gold_native_max_sell_legs=10`).
- Price moved **+41 pts (≈8.1×ATR)** within 2 hours after entry.
- `regime_label` only flipped to `TREND_BULL` at Apr 1 12:00 — **3 hours 20 min** after entry, when the move was already topping out.
- Apr 6 G5005 entry: same 5-leg cap, same `regime=RANGE` despite ADX=31.4 + H1 bullish.

**Root cause** (verified in code):
- `regime.py` (AURUM layer) NOT used in tester — `ea/FORGE.mq5:1080` gates the JSON read with `if(!in_tester) {...}` (removed in v2.7.30 — now unconditional).
- FORGE has an **inline classifier at lines 5658-5661** (later 5687+ via v2.7.29, then unconditional via v2.7.30):
  ```mql5
  if(high_vol_trend)                         g_regime_label = "VOLATILE";
  else if(h1_bull && (h4_bull || h4_flat))   g_regime_label = "TREND_BULL";
  else if(h1_bear && (h4_bear || h4_flat))   g_regime_label = "TREND_BEAR";
  else                                        g_regime_label = "RANGE";
  ```
- Requires **unanimous H1 + H4 agreement** for trend label. H4 EMA20 vs EMA50 (≈80h vs 200h smoothing) lags H1 by 3-5 hours after a regime turn.

**Industry pattern (per MQL5 article 20097 — Multi-Timeframe Harmony Index)**:
> "Weighted bias scoring per timeframe (+1/0/-1). HI = (Σ bias_i × weight_i) / (Σ weight_i). No blocking conditions or vetoes exist — all enabled timeframes contribute proportionally."

This is the opposite of FORGE's unanimous-AND model.

#### Option A — H1-strong override (SHIPPED as v2.7.29, ~5 lines)

Add a fourth clause that trusts a very-strong H1 even when H4 disagrees:

```mql5
else if(MathAbs(h1_trend_strength) >= trend_thr_eff * g_sc.regime_h1_override_factor
        && m5_adx >= g_sc.regime_h1_override_adx_min) {
   g_regime_label = (h1_trend_strength > 0) ? "TREND_BULL" : "TREND_BEAR";
}
```

Defaults: `regime_h1_override_factor=2.0`, `regime_h1_override_adx_min=30`. Apr 1 08:40 → h1=2.15 ÷ thr~0.5 = 4.3× → trigger.

#### Option B — Swap H4 for M15 in the secondary timeframe (not shipped)

```mql5
// Replace: h1_bull && (h4_bull || h4_flat)
// With:    h1_bull && !m15_bear_htf
```

M15 reacts in ~30 min vs H4 ~3-5 hr. EA already computes `m15_bull_htf` / `m15_bear_htf`.

#### Option C — Weighted harmony index (canonical MQL5 pattern, superseded by ONNX)

Replace the AND-gating block entirely with weighted scoring:

```mql5
if(high_vol_trend) {
   g_regime_label = "VOLATILE";
} else {
   int m5_bias  = m5_bull       ? +1 : (m5_bear       ? -1 : 0);
   int m15_bias = m15_bull_htf  ? +1 : (m15_bear_htf  ? -1 : 0);
   int h1_bias  = h1_bull       ? +1 : (h1_bear       ? -1 : 0);
   int h4_bias  = h4_bull       ? +1 : (h4_bear       ? -1 : 0);
   double sum = m5_bias *g_sc.regime_weight_m5
              + m15_bias*g_sc.regime_weight_m15
              + h1_bias *g_sc.regime_weight_h1
              + h4_bias *g_sc.regime_weight_h4;
   double tot = g_sc.regime_weight_m5 + g_sc.regime_weight_m15
              + g_sc.regime_weight_h1 + g_sc.regime_weight_h4;
   double hi  = (tot > 0.0) ? sum / tot : 0.0;
   if      (hi >=  g_sc.regime_hi_trend_threshold) g_regime_label = "TREND_BULL";
   else if (hi <= -g_sc.regime_hi_trend_threshold) g_regime_label = "TREND_BEAR";
   else                                             g_regime_label = "RANGE";
}
```

Defaults: `m5=0.15, m15=0.25, h1=0.45, h4=0.15, threshold=0.50`.

**Apr 1 08:40 sim**: m5(+1)·0.15 + m15(+1)·0.25 + h1(+1)·0.45 + h4(−1)·0.15 = **+0.70 ≥ 0.50 → TREND_BULL** ✓
**Mar 31 sim** (bearish daily, mild H1+): m15(−1)·0.25 + h1(+1)·0.45 + h4(−1)·0.15 = **+0.05 → RANGE** ✓ (no false positive)

**Why superseded**: The harmony index is still a hand-tuned boolean ensemble. The ONNX predictor in Phase 2 above learns the equivalent weighting from data (forward-return targets) and adds 30+ more features. Option C remains a sensible fallback if ONNX fails — its 4-feature input is trivially computable.

---

### Pre-design Issue 7 — File-driven pre-computed regime stream (superseded by ONNX)

**Status**: **Superseded by Phase 5 (ONNX)** in this doc. The file-driven approach solved the tester/live parity problem at the file layer; ONNX solves it at a deeper layer (in-process inference, no file IO, no Python dependency at runtime). The file-driven approach remains a valid fallback if MT5's ONNX support breaks or model size exceeds the 1GB resource limit (extremely unlikely).

**Evidence**:
- v2.7.30 enforces inline-classifier-as-truth in both modes. Works, but loses HMM-grade regime intelligence.
- regime.py is fully implemented but **bypassed for FORGE entry decisions** because:
  1. BRIDGE doesn't run during MT5 Strategy Tester (clock-speed mismatch)
  2. Live config.json read at `FORGE.mq5:1094-1099` is overwritten by inline classifier at `:5693-5704` every tick
- SCRIBE schema already supports regime metadata — output side is wired, just needs an authoritative producer.

**Root cause** (verified):
- `FORGE.mq5:5693-5704`: inline classifier sets `g_regime_label` + `g_regime_confidence=1.0` unconditionally on every OnTick.
- `bridge.py:5006-5012`: writes regime payload only when BRIDGE running — tester-blind.
- `python/regime.py:228`: `use_lens = bool(lens and not lens_stale)` — implicit on/off, not explicit toggle.
- TradingView MCP exposes `replay_start`/`replay_step`/`data_get_study_values` — historical regime features ARE retrievable via Bar Replay.

**Industry patterns researched** (full source list in main Sources section):
1. HMM via hmmlearn (canonical Python pattern)
2. Markov-Switching Dynamic Regression via statsmodels (k-regime switching)
3. Change-point detection via `ruptures` (PELT, off-line)
4. Multi-factor rule-based regime classifier (ARC-style on TradingView)

#### Option A — Pre-computed regime stream file (was preferred, now superseded)

`python/regime_history.py` CLI pre-computes regime labels for a date range using the existing `RegimeEngine`. Tester reads from JSON file at OnInit; live mode keeps file updated via BRIDGE.

```python
# Originally proposed CLI usage:
python3 python/regime_history.py \
    --from 2026-03-31 --to 2026-05-07 \
    --tf M5 --symbol XAUUSD \
    --source mt5  # or 'tv-replay' for TradingView MCP replay mode
```

EA-side load + binary-search-by-timestamp lookup. Default-OFF flag, falls back to inline.

**Why superseded by ONNX (Phase 5)**:
- ONNX runs inside the EA per tick — no file IO, no pre-fetch step
- ONNX gives < 1ms inference vs ~10ms for JSON file lookup + parse
- ONNX learning happens at training time on rich features; file-driven just serializes whatever regime.py produces (still the limited 11-feature vector)
- ONNX is hot-swappable (replace .onnx file) without re-running a pre-fetch

#### Option B — MQL5-native HMM port (rejected)

Port HMM inference to MQL5. ~500 LOC, maintenance burden, no Markov-chain forward filtering. **Rejected** in favor of ONNX (gives the same in-EA inference with industry-standard tooling).

#### Option C — MSDR + ruptures hybrid (deferred)

Replace regime.py's HMM internals with two-stage classifier (CPD segmentation + MSDR per-segment). Same output file format. **Deferred** — interesting research direction, but Phase 2's LightGBM-with-forward-return-labels is more aligned with FORGE's actual optimization objective (forward P&L).

---

## Changelog

| Date | Author | Change |
|------|--------|--------|
| 2026-05-11 | Operator + agent (chat) | Initial draft — phased architecture, library choice, ONNX vs HTTP, payload contract |
| 2026-05-11 | Agent | Moved historical Q&A (Q3b, Q8-Q10, Q16-Q22) and pre-design proposals (Issue 1, Issue 7) from `docs/FORGE_RUN18_ANALYSIS.md` for centralized regime reference |
| 2026-05-11 | Agent | Appended Appendix A — verbatim source chat transcript from `/tmp/regime.txt` for unedited historical reference |

---

# Appendix A — Source Chat Transcript

> Verbatim record of the 2026-05-11 chat exchange that produced this design.
> Captured from `/tmp/regime.txt`. Kept for audit / re-reading the unedited
> rationale. The Phase 1-6 design above is the curated, post-edit version;
> this appendix shows the original flow including the first iteration (before
> the "regime is prediction" reframing) and the refined version after.

## A.1 — First pass (before predictive reframing)

**Operator**: so i have paid access to trading view - so it provides us with rich data and so on. let us focus on this in phases 1. data collection (trading view or mt5) 2. analysis (why library to use there are some neural network libraris panda, numpy etc - google - anything that will run without a gpu requiremnent ) 3. classification 4. interpretation 5. should use http to pass data to forge or onynx 5. how forge payload and data exchange contract etc

**Agent — Phased Regime Architecture v2.7.31+ (first response)**:

### Phase 1 — Data Collection (TradingView vs MT5) [first iteration]

| Source | Pros | Cons | Tester parity |
|--------|------|------|---------------|
| MT5 history (broker feed) | Deterministic, identical bytes tester/live, no external dep, available in EA via `CopyBuffer/CopyRates` | Limited to MT5 indicators (still 30+ available) | ✓ Perfect |
| TradingView (paid via LENS MCP) | Rich Pine indicators, multi-TF aggregates, OB zones, custom scripts | Different broker feed (venue drift), MCP latency, requires TV Desktop running, Bar Replay throughput ~200ms/step | ⚠ Pre-fetch needed |

**Recommendation**: MT5 primary, TV enrichment secondary.

- MT5 primary: 100% of model input features come from MT5 → guarantees tester/live parity. The EA computes the feature vector in MQL5 from existing indicator handles, feeds it to the ONNX model in-process. Zero network, zero external dependency.
- TV enrichment optional: A separate JSON file with TV-derived slow-moving context (`tv_recommend`, Pine OB zones, D1 TV bias) updated by LENS on its existing cadence. Model has separate input slots for these; they default to 0 in tester (or pre-fetched if you want full parity).

```mql5
// In FORGE.mq5 — at every M5 close (OnTimer or new bar detection)
void BuildRegimeFeatureVector(double &features[]) {
   ArrayResize(features, 40);  // see Phase 6 schema
   features[0]  = M5_EMA20();
   features[1]  = M5_EMA50();
   features[2]  = M5_RSI14();
   features[3]  = M5_ADX14();
   // ... etc — all from existing g_h_* indicator handles
}
```

No CSV dump needed for the primary path — features are computed in-EA and fed directly to ONNX.

### Phase 2 — Analysis Library (CPU-only) [first iteration]

| Library | Type | CPU? | ONNX export? | Notes |
|---------|------|------|--------------|-------|
| scikit-learn | Classical ML | ✓ | ✓ via `skl2onnx` | RandomForest, SVM, LogReg — solid baseline |
| xgboost | Gradient boosting | ✓ | ✓ via `onnxmltools` | Heavier than LightGBM, scikit-learn API |
| **lightgbm** | **Gradient boosting** | **✓** | **✓ via `onnxmltools`** | **Leaf-wise tree growth, faster + smaller than XGBoost** |
| `statsmodels.tsa.regime_switching` | Markov-Switching | ✓ | ✗ | MSDR — explicit regime modeling, no ONNX path |
| `hmmlearn` | HMM | ✓ | ✗ (not trivially) | Current regime.py uses this; ONNX export awkward |
| `ruptures` | Change-point | ✓ | ✗ | Offline only, segmentation not classification |
| `pandas-ta` | Indicator feature eng. | ✓ | n/a | Used for training-time feature computation |

**Recommendation: LightGBM as primary, with optional HMM smoothing layer**

Rationale:
- LightGBM is the fastest non-GPU multi-class classifier with proven ONNX support
- Handles 40-feature input vectors at sub-ms inference
- `objective='multiclass', num_class=4` outputs probabilities for `[TREND_BULL, TREND_BEAR, RANGE, VOLATILE]` directly
- Exports via `onnxmltools.convert_lightgbm` to a `.onnx` file that `OnnxRun()` in MQL5 loads natively
- No neural network needed — gradient-boosted trees handle this regime classification cleanly on tabular features
- Optional second pass: HMM smoothing in MQL5 (~50 lines) to add temporal persistence on top of LightGBM's per-bar prediction

### Phase 3 — Classification [first iteration]

Same vocabulary as today (TREND_BULL / TREND_BEAR / RANGE / VOLATILE) for FORGE compat. Model outputs full probability vector — FORGE can use top-1 (`argmax`) or threshold-based (e.g. "act on TREND_BULL only if prob > 0.7").

**Labeling strategy (the hard part — picking ground truth)**:

| Strategy | How | Pros | Cons |
|----------|-----|------|------|
| Synthetic from rule-based (ARC-style) | Multi-factor weighted score → label | Cheap, infinite training data | Model just learns the rule-based teacher |
| Hand-labeled | Operator labels 1000 bars by chart inspection | Domain expertise encoded | 10-20 hours work |
| **Forward-return based** | **Label by what regime maximized P&L over forward 1-4h window** | **Objective, ties directly to trading outcome, scalable** | Look-ahead in labels (only used for training) |
| Clustering + human review | KMeans/HMM unsupervised → operator confirms labels | Discovers regimes you didn't expect | Initial clusters often don't match trader intuition |

**Recommendation**: forward-return based. For each historical M5 bar:
- Compute return over next N bars (N=12 = 1 hour, N=48 = 4 hours)
- If forward return > +0.5×ATR over N → TREND_BULL
- If forward return < −0.5×ATR over N → TREND_BEAR
- If max-min range over N < 0.5×ATR → RANGE
- Otherwise → VOLATILE

### Phase 4 — Interpretation [first iteration]

Raw LightGBM `argmax` will whipsaw at regime boundaries. Need:

1. **Min-confidence gate**: only flip the EA's `g_regime_label` when `max(probs) ≥ FORGE_REGIME_MIN_CONFIDENCE` (default 0.55). Below threshold → hold previous label.
2. **Hysteresis**: require N consecutive bars in new label before flipping (default N=3 for M5 = 15 min). Filters out 1-bar noise.
3. **Tenure**: track `regime_age_bars` — bars since last flip. Used by FORGE to require regime maturity before sizing up.
4. **Transition flag**: `transition=true` exactly on the flip bar — FORGE uses this for cancel-pending-on-flip logic.

Output enrichment for FORGE consumption:
```json
{
  "label":       "TREND_BULL",
  "confidence":  0.78,
  "probs":       {"bull": 0.78, "bear": 0.05, "range": 0.12, "volatile": 0.05},
  "age_bars":    17,
  "transition":  false,
  "next_likely": "RANGE",
  "ts":          1712016000
}
```

### Phase 5 — Transport: HTTP vs ONNX [first iteration]

**HTTP via `WebRequest()`**:

| | Detail |
|---|---|
| Pattern | Flask/FastAPI service exposes `/predict` POST endpoint accepting JSON feature vector, returning JSON probabilities |
| Latency | 5-50ms per call (localhost) |
| Tester support | `WebRequest()` works in tester but **adds wall-clock time per tick**, slowing 1000× backtest to 100× or worse |
| Dependency | Python service must be running |
| Failure mode | Service down → EA fallback to inline classifier or trade blocked |

**ONNX via `OnnxRun()`**:

| | Detail |
|---|---|
| Pattern | Train LightGBM in Python → export `.onnx` via `onnxmltools` → load as EA resource → `OnnxRun()` per tick |
| Latency | < 1ms per call (in-process) |
| Tester support | **Identical to live** — model file is part of the EA binary, no network |
| Dependency | None at runtime (only at train time) |
| Model size | Up to 1GB embeddable as resource (Build 5572+, Jan 2026) |
| Profiling | `ONNX_ENABLE_PROFILING` flag → `MQL5/Files/OnnxProfileReports/` |

**Recommendation: ONNX, no contest**

HTTP retains a **secondary role only** for:
- Live-only LENS TV enrichment data (low cadence, 60s)
- Hot-swappable model versioning (request remote model URL)
- Out-of-band debugging (Python service can log every prediction for audit)

### Phase 6 — Payload + Data Exchange Contract [first iteration]

```c++
// FORGE.mq5 — feature vector schema (fixed order, must match training)
double features[40];

// Trend (10)
features[0]  = M5_EMA20_minus_EMA50_normalized_by_ATR;
features[1]  = M15_EMA20_minus_EMA50_normalized_by_ATR;
features[2]  = H1_EMA20_minus_EMA50_normalized_by_ATR;
features[3]  = H4_EMA20_minus_EMA50_normalized_by_ATR;
features[4]  = M5_EMA50_minus_EMA200_normalized_by_ATR;
features[5]  = H1_EMA50_minus_EMA200_normalized_by_ATR;
features[6]  = M5_PSAR_direction;          // +1 / -1
features[7]  = M5_MACD_histogram_normalized;
features[8]  = M5_MACD_signal_cross;        // -1/0/+1
features[9]  = H1_trend_slope;

// Momentum (8)
features[10] = M5_RSI14_centered;          // (RSI-50)/50
features[11] = M15_RSI14_centered;
features[12] = H1_RSI14_centered;
features[13] = M5_Stoch_K;
features[14] = M5_Stoch_D;
features[15] = M5_Stoch_KminusD;
features[16] = M5_ADX14;
features[17] = M5_DIplus_minus_DIminus;

// Volatility (10)
features[18] = M5_ATR14;
features[19] = M15_ATR14;
features[20] = H1_ATR14;
features[21] = M5_BB_width_percentile_50bar;
features[22] = M5_BB_position;             // (close-mid)/(upper-mid) ∈ [-1,1]
features[23] = realized_vol_5;
features[24] = realized_vol_20;
features[25] = realized_vol_50;
features[26] = M5_high_low_range_normalized;
features[27] = M5_body_to_range_ratio;

// Returns (5)
features[28] = log_return_1;
features[29] = log_return_5;
features[30] = log_return_20;
features[31] = log_return_60;
features[32] = log_return_1_zscore_50;     // anomaly detection

// Time/session (7)
features[33] = session_code;               // 0-5
features[34] = sin(2π · hour_of_day / 24);
features[35] = cos(2π · hour_of_day / 24);
features[36] = day_of_week;                // 0-6
features[37] = bars_since_session_open;
features[38] = is_news_window;             // 0/1
features[39] = bars_since_last_high_volatility_spike;
```

```c++
// FORGE.mq5 — per M5 close inference
double features[40];
BuildRegimeFeatureVector(features);

double probs[4];
OnnxRun(g_regime_model, ONNX_DEFAULT, features, probs);

int    label_idx = ArgMax(probs);
double conf      = probs[label_idx];

// Apply confidence gate + hysteresis
if(conf >= g_sc.regime_min_confidence) {
   string new_label = LABEL_NAMES[label_idx];
   g_regime_candidate_buf[g_regime_buf_idx++] = new_label;
   if(AllBarsAgree(g_regime_candidate_buf, g_sc.regime_hysteresis_bars)) {
      bool transition = (g_regime_label != new_label);
      g_regime_label = new_label;
      g_regime_confidence = conf;
      ArrayCopy(g_regime_probs, probs);
      if(transition) g_regime_age_bars = 0;
      else           g_regime_age_bars++;
   }
}
```

Optional HTTP enrichment endpoint (live only):
```python
# python/regime_enrichment_service.py — small Flask app
@app.route("/lens_tv_features", methods=["GET"])
def lens_tv_features():
    return jsonify({
        "tv_recommend":   lens.current_recommendation(),
        "tv_bias_d1":     lens.daily_bias(),
        "pine_ob_zones":  lens.order_block_zones(),
        "stamp":          time.time()
    })
```

EA calls this every 60s (low cadence, doesn't hurt tester since tester ignores it). Features feed into the ONNX model as features[40..50] (if model is trained with them) — but model is also trained with zeros for those features so tester works fine.

**Versioning + reload**:
```
config/regime_model.onnx                  # current production model
config/regime_model_v1.onnx              # versioned snapshots
config/regime_model_metadata.json        # { feature_names, label_names, trained_at, train_corpus, metrics }

FORGE_REGIME_MODEL_FILE=config/regime_model.onnx   # env-tunable
FORGE_REGIME_MIN_CONFIDENCE=0.55
FORGE_REGIME_HYSTERESIS_BARS=3
FORGE_REGIME_USE_ONNX=0   # default-OFF, ships behind flag
```

When OFF → falls back to current v2.7.30 inline classifier (the safety net).
When ON → ONNX inference is authoritative.

---

## A.2 — Predictive reframing turn

**Operator**: "The fact is that regime calculation is a analsysis that happens to predict: so i have paid access to trading view - so it provides us with rich data and so on. let us focus on this in phases [same numbered list as before]"

**Agent**: Reframing this through the predictive lens — that changes the library choice. Let me do focused searches on CPU-only neural network options for time-series prediction before I answer.

Web searches performed:
- "CPU only neural network time series prediction python pytorch lstm gru TCN 2026 lightweight"
- "tabular neural network financial time series CPU TabNet NODE FT-Transformer forex regime"
- "TCN temporal convolutional network forecasting forex CPU inference latency low"
- "scikit-learn MLPClassifier vs LightGBM vs LSTM forex regime classification CPU benchmark"

**Refined response**: "You nailed it — regime calculation is forward-looking prediction, not snapshot description. That framing changes the model objective: we're not asking 'what is the market doing right now?' we're asking 'given current features, which regime will produce profitable trades over the next N bars?' That's a supervised prediction problem with forward-return labels."

### Phase 2 (refined) — Landscape with NN options

| Library | Type | CPU latency (40-feat tabular) | ONNX | Best for |
|---------|------|-------------------------------|------|----------|
| **LightGBM** | **Gradient-boosted trees** | **< 1ms** | **✓ via `onnxmltools`** | **Pre-engineered tabular features (our case)** |
| XGBoost | Gradient-boosted trees | ~2ms | ✓ | Same as LGBM, heavier |
| scikit-learn `MLPClassifier` | Feedforward NN | ~1ms | ✓ via `skl2onnx` | Simple baseline NN |
| PyTorch TCN | Temporal CNN | 5-15ms | ✓ via `torch.onnx.export` | Raw OHLCV sequence input |
| PyTorch LSTM/GRU | Recurrent NN | 10-30ms | ✓ (stateful tricky) | Long sequences, GPU preferred |
| TabNet (PyTorch) | Attention tabular NN | 5-20ms | ✓ | Tabular with interpretability |
| TabPFN | Transformer (pretrained) | 50-200ms | ⚠ heavy | Few-shot tabular |
| TabPFN-TS | Tabular foundation for TS | 100ms+ | ⚠ heavy | Zero-shot forecasting |

**Why LightGBM wins as the primary**:
- Sub-ms inference on CPU — fits the per-tick budget with margin
- 40-feature tabular input is LightGBM's home turf — gradient-boosted trees consistently match or beat NNs on tabular data
- Bulletproof ONNX export — `onnxmltools.convert_lightgbm` produces models MQL5's `OnnxRun()` consumes natively
- SHAP feature importance — for every prediction we can ask "why did the model say TREND_BULL?" — invaluable for debugging
- Robust to noise + missing features — works fine if TV features are zero in tester

**Why not LSTM/GRU first**:
- Slower CPU inference, marginal accuracy gain on this size of feature space
- Stateful RNN export to ONNX is fiddly (you have to manage hidden state externally)
- LSTMs shine when you feed raw OHLCV sequences (last 100 bars) and let the network learn temporal structure. We already engineer those features into a 40-vector — letting trees do the work.

**Why TCN is the v2 candidate**:
If LightGBM plateaus, TCN (Temporal Convolutional Network) is the right second-stage upgrade. It:
- Uses dilated causal convolutions — parallel on CPU (faster than LSTM)
- Accepts raw OHLCV sequences (e.g., last 50 M5 bars as input)
- Learns temporal patterns LightGBM can't capture (recurrent micro-structure)
- Exports to ONNX from PyTorch directly via `torch.onnx.export(model, dummy_input, "tcn.onnx")`
- 5-15ms CPU inference is still well within the budget

**Roadmap**: ship LightGBM in v2.7.31, evaluate on Run 19/20, if validation forward-return correlation < 0.4 → upgrade to TCN in v2.7.32.

### Phase 3 (refined) — Forward-return labels (the predictive part)

For each historical M5 bar at time T:
- Compute forward return: `R(T) = close(T + N_bars) - close(T)`
- Compute forward max/min: `H(T) = max(high over [T, T+N])`, `L(T) = min(low over [T, T+N])`
- ATR at T: `A(T)`

Label assignment:
- `R(T) > +0.5 × A(T)` AND `(H - close(T)) > 0.7 × A(T)` → **TREND_BULL**
- `R(T) < -0.5 × A(T)` AND `(close(T) - L) > 0.7 × A(T)` → **TREND_BEAR**
- `(H - L) < 0.6 × A(T)` AND `|R(T)| < 0.3 × A(T)` → **RANGE**
- Otherwise → **VOLATILE** (wide swings, no directional payoff)

Parameters configurable: `N_bars` (label horizon), `R/H/L thresholds`. **Suggested N_bars = 24 (2 hours on M5)** — matches FORGE's scalp horizon, smooths intrabar noise.

**Validation metric**: not accuracy — **forward P&L correlation** (Spearman ≥ 0.4 = production-quality).

### Phase 6 (refined) — 50-slot vector (40 MT5 + 10 TV)

```c++
// FORGE.mq5 — schema must match training-time feature order EXACTLY
// File: config/regime_model_metadata.json carries the canonical order;
// EA loads it at OnInit and validates feature count matches the .onnx model.

double features[50];   // 40 MT5 + 10 LENS-TV (zero-filled in tester)

// MT5 features (40) — primary input, identical tester+live
//   features[0..9]   = Trend: M5/M15/H1/H4 EMA spreads (normalized by ATR), PSAR, MACD hist, H1 slope
//   features[10..17] = Momentum: RSI/Stoch/ADX/DI variants across TFs
//   features[18..27] = Volatility: ATRs, BB width/position, realized vol windows, body/range ratios
//   features[28..32] = Returns: log returns 1/5/20/60 bars + z-score
//   features[33..39] = Time/session: session code, time-of-day sin/cos, day-of-week, news window flag

// LENS-TV enrichment (10) — live-only, zero-filled in tester
//   features[40..49] = tv_recommend, tv_d1_bias, pine OB zone distances, pine_levels, etc.
```

Versioning + metadata sidecar:
```
config/
├── regime_model.onnx                       # ← current model (symlink to versioned)
├── regime_model_v2026-05-11.onnx           # ← versioned snapshot (immutable, checked in)
├── regime_model_metadata.json              # ← schema contract:
                                            #     { feature_names: [...50],
                                            #       label_names:   ["TREND_BULL", "TREND_BEAR", "RANGE", "VOLATILE"],
                                            #       trained_at:    "2026-05-11T12:00Z",
                                            #       train_corpus:  "XAUUSD M5 2024-05 to 2026-04",
                                            #       train_metrics: { macro_f1: 0.78,
                                            #                        fwd_return_spearman_bull: 0.47,
                                            #                        fwd_return_spearman_bear: 0.43 },
                                            #       label_horizon_bars: 24,
                                            #       atr_period: 14 }
└── regime_train_log.jsonl                  # ← append-only: every (re)train event with metrics
```

Env-tunable knobs (default-OFF for safe rollout):
```
# Regime predictor master switch
FORGE_REGIME_USE_ONNX=0                       # default OFF; ON = ONNX authoritative

# Model location
FORGE_REGIME_MODEL_FILE=config/regime_model.onnx

# Inference filters
FORGE_REGIME_MIN_CONFIDENCE=0.55              # min posterior to commit to new label
FORGE_REGIME_HYSTERESIS_BARS=3                # consecutive bars required to flip

# TV enrichment
FORGE_REGIME_TV_ENRICHMENT_ENABLED=0          # tester: 0; live: opt-in via LENS
FORGE_REGIME_TV_ENRICHMENT_POLL_SECONDS=60

# Diagnostics
FORGE_REGIME_ONNX_PROFILING=0                 # MT5 ONNX_ENABLE_PROFILING flag
FORGE_REGIME_AUDIT_HTTP_URL=                  # empty = no audit POST; else POST per prediction
```

### Phase build order (from refined response)

| # | Deliverable | Effort | Blocking? |
|---|---|---|---|
| 1 | OHLCV/feature collection inside EA — `BuildRegimeFeatureVector()` MQL5 helper | 4-6h | No |
| 2 | Python training pipeline: `python/train_regime_model.py` (pandas-ta features, LightGBM, onnxmltools export) | 1-2 days | Yes |
| 3 | Forward-return label generator: `python/label_regime_history.py` | 4-6h | Yes (blocks #2) |
| 4 | ONNX integration in FORGE: load model, `OnnxRun` per M5 close, hysteresis | 1 day | No |
| 5 | Backward-compat flag + inline fallback | 2h | No |
| 6 | Validation harness: regime label vs forward P&L correlation, label stability metrics | 1 day | After #4 |
| 7 | Optional HTTP enrichment service for LENS TV features | 0.5 day | No (last) |

**Total**: ~5-7 days of focused work to v2.7.31 with a real statistical regime classifier shipping behind a default-OFF flag, with full tester/live parity.

### Open decisions captured at end of refined response

1. **Label horizon `N_bars`**: 12 / 24 / 48? Default: **24 bars (2h)** for XAUUSD M5
2. **Training corpus length**: 1 / 2 / 3 years? Default: **2 years**
3. **Number of classes**: 4 (current) or expand to 6 (Strong/Weak Bull/Bear)? Default: **start with 4**
4. **Confidence threshold**: 0.50 / 0.55 / 0.65? Default: **0.55**
5. **Hysteresis bars**: 2 / 3 / 5? Default: **3 (15min)**

---

## A.3 — Doc-creation turn

**Operator**: "let us opoen a new design doc for this discusscion so far and update the previous run analysis doc with an inline link to it."

**Agent**: Wrote `docs/FORGE_REGIME_PREDICTOR_DESIGN.md` (this file) with consolidated phased design + cross-link from Run 18 doc.

**Operator**: "this is only for the regime dission thus far and move all things regime to this doc"

**Agent**: Moved historical Q&A (Q3b, Q8-Q10, Q16-Q22) and pre-design proposals (Issue 1 v2.7.29 inline override, Issue 7 file-driven stream) from Run 18 doc to this design doc's "Historical Q&A" and "Pre-design Proposals (Superseded)" sections. Replaced moved content in Run 18 doc with stubs pointing here.

**Operator**: "update docs/FORGE_REGIME_PREDICTOR_DESIGN.md to with /tmp/regime.txt"

**Agent**: Appended this Appendix A — verbatim chat transcript source — for unedited historical reference.
