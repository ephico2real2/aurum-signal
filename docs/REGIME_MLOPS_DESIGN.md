# Regime Engine — MLOps Extension Design
## Supervised Regime Classification: From HMM Discovery to Outcome-Validated Inference

> Written: 2026-05-10  
> Author: signal_system regime analysis  
> Status: Design / Pre-implementation  
> See also: [docs/REGIME_ENGINE_REVIEW.md](REGIME_ENGINE_REVIEW.md) — current engine gotchas and enhancement backlog  
> See also: [docs/MT5_BROKER_INTEGRATION.md](MT5_BROKER_INTEGRATION.md) — system architecture, tick loop, latency

---

## 1. Current State — What We Have, What We Are Missing

### 1.1 What the Bridge Already Collects

The bridge is, unknowingly, running a continuous supervised learning data collection pipeline across three tables in `aurum_intelligence.db`:

| Table | Written by | Frequency | Key columns |
|-------|------------|-----------|-------------|
| `market_regimes` | `scribe.log_market_regime()` | On label transition OR every 30s | `regime_label`, `confidence`, `posterior_json`, `feature_json`, `model_name`, `session`, `timestamp` |
| `signals_received` | `scribe.log_signal()` | Every signal parsed | `regime_label`, `regime_confidence`, `regime_model`, `regime_fallback_reason`, `direction`, `action_taken`, `skip_reason`, `trade_group_id` |
| `trade_groups` | `scribe.log_trade_group()` | Every group opened | `regime_label`, `regime_confidence`, `regime_model`, `regime_fallback_reason`, `total_pnl`, `pips_captured`, `status`, `direction` |

This is **complete ground truth for supervised learning**: feature vector + label at signal time + trade outcome. The data pipeline is already running. No new collection infrastructure is required.

### 1.2 What the HMM and Gaussian Actually Know

**HMM (primary model):**
- Trained entirely unsupervised on the 11-dimensional feature history
- Has never seen a trade P&L, a win/loss flag, or even a signal outcome
- Learns to separate market states by their statistical properties alone
- Assigns labels post-hoc by inspecting which HMM state has the highest mean ADX and EMA spread — a heuristic that can mislabel states when the feature distribution shifts
- Confidence = `argmax(predict_proba())` on a single vector — no sequence context, no calibration against outcomes

**Gaussian fallback (deterministic rules):**
- Pure rule engine: ADX ≥ 24 → trend; EMA spread direction → BULL/BEAR; BB width → VOLATILE; else RANGE
- Confidence is synthetic (0.58 + heuristic boost), not derived from data
- Has no learning capacity — the same input always produces the same output regardless of how many times that signal proved wrong

**The ceiling these models hit:**
- A `TREND_BULL` label from the HMM means "the feature vector today statistically resembles past vectors that the HMM grouped into a high-ADX, positive-EMA-spread cluster." It says nothing about whether trades taken in that state actually won.
- Two RANGE states can be statistically identical but produce very different trade outcomes depending on session, spread environment, and institutional order flow. The HMM cannot distinguish them because it has never seen outcomes.
- Confidence values are not calibrated. HMM confidence of 0.72 does not mean 72% of trades win in that state — there is no outcome feedback loop.

### 1.3 The Opportunity

The bridge has been collecting outcome-tagged regime data since the first day `regime_label` and `total_pnl` columns were added to `trade_groups`. After ~500 closed trades, we have enough labeled examples to train a third model tier that knows which regimes actually produce wins — not just which regimes look statistically distinct.

---

## 2. Three-Tier Model Architecture

The architecture preserves the cold-start safety of the existing stack while adding an outcome-validated classifier as a third tier.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     REGIME ENGINE — THREE-TIER STACK                        │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ TIER 1 — Gaussian Fallback (DETERMINISTIC RULES)                     │   │
│  │                                                                      │   │
│  │  Inputs:  11-dim feature vector (ADX, EMA spread, BB width, ...)     │   │
│  │  Logic:   Hard thresholds — ADX≥24 → trend; BB expand → volatile    │   │
│  │  Output:  label + synthetic confidence (0.52–0.95)                   │   │
│  │  When:    Always available; used when HMM has < 120 samples          │   │
│  │  Knows:   Market structure rules. Nothing about trade outcomes.       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                            │  (after 120 samples)                           │
│                            ▼                                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ TIER 2 — GaussianHMM (UNSUPERVISED DISCOVERY)                        │   │
│  │                                                                      │   │
│  │  Inputs:  11-dim feature history (up to last 5000 vectors)           │   │
│  │  Logic:   EM training → hidden state clustering → heuristic labeling │   │
│  │  Output:  label + predict_proba() confidence (raw, uncalibrated)     │   │
│  │  When:    After 120 samples; retrained hourly in background thread   │   │
│  │  Knows:   Statistical structure of market features. Not outcomes.    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                            │  (after ~500 closed trades)                    │
│                            ▼                                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ TIER 3 — Supervised Classifier (OUTCOME-VALIDATED)                   │   │
│  │                                                                      │   │
│  │  Inputs:  11-dim features + HMM posterior (5 dims) + context        │   │
│  │  Logic:   XGBoost / logistic regression trained on (features, win)   │   │
│  │  Output:  label + calibrated win-rate probability per regime class   │   │
│  │  When:    After promotion threshold is met (holdout WR ≥ current)   │   │
│  │  Knows:   Which regime labels actually predict winning trades.        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Active model is always the highest tier that meets its readiness criteria  │
│  Output contract: {label, confidence, posterior, model_name, model_version} │
│  — unchanged regardless of which tier is active                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key design principle:** each tier is a strict superset of the previous. Tier 3 never replaces Tier 1/2 — it augments them. If Tier 3 is demoted (drift detected, holdout WR drops), the engine falls back to Tier 2 automatically with a single flag flip.

---

## 3. Training Data Pipeline

### 3.1 The SQL Join

The training dataset is built by joining the three tables on `trade_group_id` and timestamped regime snapshots:

```sql
-- Training dataset query
-- Produces one row per closed trade group with: features at signal time, regime label, outcome
SELECT
    tg.id                       AS trade_group_id,
    tg.timestamp                AS entry_time,
    tg.direction,
    tg.regime_label             AS label_at_entry,
    tg.regime_confidence        AS conf_at_entry,
    tg.regime_model             AS model_at_entry,
    tg.session,
    tg.total_pnl,
    tg.pips_captured,
    tg.trades_opened,
    tg.trades_closed,

    -- Outcome label: WIN if total_pnl > 0, LOSS if total_pnl <= 0
    CASE WHEN tg.total_pnl > 0 THEN 1 ELSE 0 END AS outcome_win,

    -- Feature vector from closest market_regimes snapshot at signal time
    mr.feature_json             AS features_json,
    mr.posterior_json           AS hmm_posterior_json,
    mr.confidence               AS hmm_confidence,

    -- Signal context
    sr.skip_reason,
    sr.regime_policy,
    sr.regime_fallback_reason

FROM trade_groups tg
LEFT JOIN signals_received sr
    ON tg.signal_id = sr.id
LEFT JOIN market_regimes mr
    ON mr.timestamp = (
        SELECT timestamp FROM market_regimes
        WHERE timestamp <= tg.timestamp
        ORDER BY timestamp DESC
        LIMIT 1
    )
WHERE tg.status = 'CLOSED'
  AND tg.total_pnl IS NOT NULL
  AND tg.regime_label IS NOT NULL
ORDER BY tg.timestamp;
```

### 3.2 Feature Vector for Tier 3

Tier 3 uses a richer feature vector than the raw 11-dim HMM input. It combines:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TIER 3 FEATURE VECTOR (17–21 dimensions)                 │
│                                                                             │
│  From market_regimes.feature_json (11 dims — same as HMM input):           │
│    ret_1, volatility, ema_spread, adx, bb_width, spread, session_code,     │
│    rsi_centered, macd_hist, tv_recommend, lens_price_delta                  │
│                                                                             │
│  From market_regimes.posterior_json (up to 5 dims — HMM posterior):        │
│    P(TREND_BULL), P(TREND_BEAR), P(VOLATILE), P(RANGE), P(UNKNOWN)         │
│    → This lets Tier 3 learn from the HMM's uncertainty, not just its       │
│      argmax label. A posterior of [0.45, 0.40, 0.10, 0.05] at the         │
│      TREND_BULL/TREND_BEAR boundary is a very different signal to          │
│      [0.88, 0.05, 0.04, 0.03].                                             │
│                                                                             │
│  Context features (1–5 dims):                                               │
│    session_encoded (one-hot or ordinal: LONDON=3, LONDON_NY=4, ...)        │
│    direction_encoded (BUY=1, SELL=-1)                                       │
│    lens_used (bool: 1 if LENS data was live at signal time, 0 if stale)    │
│    hmm_confidence (float: raw confidence from HMM posterior argmax)         │
│    fallback_flag (bool: 1 if Gaussian was active, not HMM)                 │
│                                                                             │
│  Target label (1 dim):                                                       │
│    outcome_win = 1 if total_pnl > 0 else 0                                 │
│    (binary classification task per regime class)                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Data Pipeline Architecture

```
aurum_intelligence.db
        │
        │  SQL join (Section 3.1)
        ▼
python/ml/build_training_set.py
        │
        │  outputs: python/data/regime_training_set.parquet
        │           (one row per closed trade group, N features + outcome_win)
        ▼
python/ml/train_regime_classifier.py
        │
        ├── stratified train/validation/holdout split (60/20/20)
        │   stratify by: regime_label × direction × session
        │
        ├── XGBoost or logistic regression (see Section 4)
        │
        ├── calibration (Platt scaling or isotonic regression)
        │   → ensures confidence output is a true probability, not raw score
        │
        ├── per-label win-rate validation (holdout set)
        │   → must beat current HMM win-rate threshold to be promoted
        │
        └── outputs: python/data/regime_supervised.pkl
                     python/data/regime_supervised_meta.json
                     (model + calibration + per-label win rates + feature schema)
```

### 3.4 Minimum Data Requirement

| Regime label | Minimum rows (both directions) | Rationale |
|---|---|---|
| `TREND_BULL` | 60 (30 BUY + 30 SELL) | Enough for stratified CV |
| `TREND_BEAR` | 60 (30 BUY + 30 SELL) | Same |
| `VOLATILE` | 40 | Less frequent — lower bar |
| `RANGE` | 60 (30 BUY + 30 SELL) | Most common — needs balance |
| **Total** | **~220 per regime class, ~500+ overall** | Practical minimum before training is meaningful |

Below 500 closed trades, the training data is too sparse for a reliable holdout validation. Below this threshold, Tier 3 is not trained; the system stays on Tier 2.

---

## 4. Model Selection

### 4.1 Starting Model — XGBoost or Logistic Regression

**Why XGBoost first:**
- Handles small tabular datasets (500–5000 rows) extremely well — this is its sweet spot
- Feature importance is directly interpretable: which features drove the TREND_BULL → win prediction?
- No assumption of linear separability (unlike logistic regression)
- Robust to feature scale differences without normalization
- `xgboost` is already a likely dependency given the Python stack; if not, `scikit-learn GradientBoostingClassifier` is a drop-in alternative

**Why logistic regression as a cross-check:**
- Maximum interpretability — each feature weight is a coefficient
- Acts as a calibration sanity check: if logistic regression and XGBoost agree on feature importance, trust increases
- Very fast to train — can be re-trained every hour alongside HMM if needed

**Training approach:**
```
Phase 1 (< 2000 labeled trades):
  - Logistic regression (L2 regularization, C=0.1) — baseline
  - XGBoost (max_depth=4, n_estimators=100, learning_rate=0.05) — primary
  - Platt calibration wrapper on both
  - Per-label win-rate on holdout: if Tier 3 holdout WR > Tier 2 empirical WR → promote

Phase 2 (2000–10000 labeled trades):
  - Increase XGBoost depth and estimators
  - Add SHAP values for feature attribution (pip install shap)
  - Begin online update experiments (partial_fit on new batches)

Phase 3 (> 10000 labeled trades, ~6–12 months of live trading):
  - Evaluate LSTM on feature sequences (5–20 ticks before signal)
  - Sequence patterns the HMM misses: e.g., rising volatility + falling ADX → VOLATILE trap
```

### 4.2 When to Graduate to LSTM

LSTM adds value when:
1. **Sequence context matters** — not just "ADX is 28" but "ADX rose from 15 to 28 over the last 10 ticks before signal"
2. **You have enough data** — LSTM needs at least 5000–10000 sequences to generalize; at 500 trades it will overfit
3. **XGBoost feature importance shows time-lag features are top predictors** — if `ret_1` dominates over `adx`, sequence models will likely help

LSTM is explicitly deferred to Phase 3. Building it before Phase 1 is validated is a common MLops mistake.

### 4.3 Online Learning Considerations

The regime distribution is non-stationary — XAUUSD volatility regimes change with macro cycles. Three strategies:

| Strategy | Mechanism | When to use |
|---|---|---|
| **Periodic full retrain** | Retrain XGBoost from scratch every N weeks on rolling window | Simplest; recommended for Phase 1 |
| **Sliding window** | Keep only the last K trades in training data; drop oldest | Handles regime drift; loses long-term pattern memory |
| **Incremental update** | `sklearn SGDClassifier.partial_fit()` on new batches | Fast; stateful; harder to calibrate |

**Recommended for Phase 1:** full retrain weekly, 90-day rolling window, triggered manually or by a cron job. Move to automated incremental updates in Phase 2 once the monitoring layer (Section 6) is validated.

---

## 5. Integration with regime.py

### 5.1 How Tier 3 Slots Into `infer()`

The key constraint: the output contract of `infer()` — the `RegimeSnapshot` dict with `label`, `confidence`, `posterior`, `model_name`, `model_version` — must not change. Consumers (AEGIS, FORGE EA, SCRIBE, ATHENA) depend on this contract.

Tier 3 slots in as a new inference path alongside the existing Tier 2/1 paths:

```python
# Current flow in infer() (simplified):
label, conf, posterior, hmm_reason = self._hmm_infer(vector)
if label == "UNKNOWN":
    label, conf, posterior = self._gaussian_fallback(feat)
    model_name = "GAUSSIAN_FALLBACK"

# Proposed flow with Tier 3:
label, conf, posterior, hmm_reason = self._hmm_infer(vector)
if label == "UNKNOWN":
    label, conf, posterior = self._gaussian_fallback(feat)
    model_name = "GAUSSIAN_FALLBACK"
else:
    # Tier 3: attempt supervised override if model is ready and promoted
    sv_result = self._supervised_infer(vector, posterior, feat)
    if sv_result is not None:
        label, conf, posterior = sv_result
        model_name = "SUPERVISED_XGB"
    else:
        model_name = "HMM_GAUSSIAN"
```

`_supervised_infer()` returns `None` when:
- The supervised model is not loaded (not yet promoted, or not yet trained)
- The model's feature schema doesn't match the current vector shape
- Inference raises an exception (graceful fallback to Tier 2)

This means **Tier 3 failure is always silent** — the system falls back to Tier 2 without operator intervention. The `fallback_reason` field in `RegimeSnapshot` is used to surface Tier 3 failures to the API and monitoring layer.

### 5.2 Model Versioning

```
python/data/
├── regime_hmm.pkl                    # Tier 2 — existing pickle (HMM model)
├── regime_supervised.pkl             # Tier 3 — supervised model + calibrator
├── regime_supervised_meta.json       # Tier 3 metadata:
│                                     #   {
│                                     #     "model_type": "xgboost",
│                                     #     "trained_at": "2026-06-01T12:00:00Z",
│                                     #     "training_samples": 623,
│                                     #     "feature_schema": ["ret_1", "volatility", ...],
│                                     #     "holdout_wr_by_label": {
│                                     #       "TREND_BULL": 0.74, "RANGE": 0.61, ...
│                                     #     },
│                                     #     "promoted": true,
│                                     #     "promotion_date": "2026-06-02T08:00:00Z"
│                                     #   }
└── regime_supervised_archive/
    ├── regime_supervised_20260601.pkl  # versioned archive on each retrain
    └── regime_supervised_20260601.json
```

The `RegimeEngine` loads `regime_supervised.pkl` on startup via `_load_supervised_model_from_disk()` (mirrors the existing `_load_model_from_disk()` pattern). On each retrain, the new model is written to a temp file and atomically renamed — same pattern as the HMM pickle.

### 5.3 Promotion Criteria

Tier 3 is not promoted to active inference automatically without explicit validation. The promotion gate:

```python
def _should_promote_supervised(meta: dict, hmm_empirical_wr: dict) -> bool:
    """
    Promote Tier 3 if, on the holdout set:
      - Per-label holdout WR beats the HMM empirical WR for that label
        by at least SUPERVISED_PROMOTE_MARGIN (default 2 percentage points)
      - Holdout sample size is at least SUPERVISED_MIN_HOLDOUT_TRADES (default 80)
      - Overall holdout WR is >= SUPERVISED_PROMOTE_FLOOR (default 0.60)
    """
    holdout_wr = meta.get("holdout_wr_by_label", {})
    if meta.get("holdout_samples", 0) < SUPERVISED_MIN_HOLDOUT_TRADES:
        return False
    if meta.get("overall_holdout_wr", 0) < SUPERVISED_PROMOTE_FLOOR:
        return False
    for label, wr in holdout_wr.items():
        baseline = hmm_empirical_wr.get(label, 0.0)
        if wr < baseline + SUPERVISED_PROMOTE_MARGIN:
            return False
    return True
```

Promotion is stored in `regime_supervised_meta.json` as `"promoted": true` and is a human-reviewed step for Phase 1. In Phase 2, promotion can be automated within the weekly retrain job.

---

## 6. Monitoring Layer

### 6.1 Posterior Entropy Drift Detection

Posterior entropy measures how uncertain the active model is. High entropy = the model sees a feature vector that is unlike anything in its training distribution.

```
Shannon entropy H(p) = -Σ p_i * log(p_i)
  where p_i are the posterior probabilities over regime labels.

H = 0.0   → Maximum certainty (all probability on one label)
H = log(N) → Maximum uncertainty (uniform distribution over N labels)
```

**Implementation (add to `_hmm_infer()` or `_supervised_infer()`):**
```python
import math

def _posterior_entropy(posterior: dict) -> float:
    h = 0.0
    for p in posterior.values():
        if p > 0:
            h -= p * math.log(p)
    return round(h, 4)
```

**Entropy thresholds:**
- `H < 0.5` — confident inference; no action
- `0.5 ≤ H < 1.0` — moderate uncertainty; log to `market_regimes` for review
- `H ≥ 1.0` — high uncertainty; automatically lower the effective confidence by `entropy_penalty = (H - 0.5) * 0.1`; surface in Athena dashboard
- `H ≥ 1.4` — drift alert; suppress Tier 3; fall back to Tier 2 with `fallback_reason="supervised_entropy_drift"`

This implements the "posterior entropy as secondary signal" enhancement from REGIME_ENGINE_REVIEW.md §7 Medium 6, extended to work across all three tiers.

### 6.2 Per-Label Win Rate Tracking

A rolling win-rate table is maintained in Scribe (new table, or as a materialized view query):

```sql
-- Regime performance view (queryable via Athena /api/regime/performance)
SELECT
    tg.regime_label,
    tg.regime_model,
    COUNT(*)                                    AS total_trades,
    SUM(CASE WHEN tg.total_pnl > 0 THEN 1 END) AS wins,
    ROUND(AVG(CASE WHEN tg.total_pnl > 0 THEN 1.0 ELSE 0.0 END), 4)
                                                AS win_rate,
    ROUND(AVG(tg.total_pnl), 2)                AS avg_pnl,
    MIN(tg.timestamp)                           AS first_trade,
    MAX(tg.timestamp)                           AS last_trade
FROM trade_groups tg
WHERE tg.status = 'CLOSED'
  AND tg.total_pnl IS NOT NULL
  AND tg.regime_label IS NOT NULL
GROUP BY tg.regime_label, tg.regime_model
ORDER BY win_rate DESC;
```

This query already works today against the live `aurum_intelligence.db`. No new schema changes are needed.

**Alert thresholds:**
- If any label's rolling 30-trade WR drops below `0.45`, alert via Herald: `"REGIME MONITOR: TREND_BULL win rate 42% (last 30 trades) — review classification"`
- If overall WR drops below `0.50` on any 50-trade window, flag for human review

### 6.3 Auto-Threshold Adjustment for REGIME_MIN_CONFIDENCE

The current `REGIME_MIN_CONFIDENCE=0.60` is a static threshold. It should adapt to empirical calibration:

```python
def _calibrate_confidence_threshold(label: str, target_wr: float = 0.60) -> float:
    """
    Find the minimum confidence threshold that, historically,
    achieves target_wr on closed trades for this label.
    Query: SELECT MIN(conf) WHERE rolling_wr(conf_bucket) >= target_wr
    """
    ...
```

In Phase 1, this runs offline (weekly, in the retrain script) and the result is written to `regime_supervised_meta.json` as `"calibrated_min_confidence": {"TREND_BULL": 0.65, "RANGE": 0.58, ...}`. The `RegimeEngine` reads these per-label thresholds on startup and uses them instead of the global `REGIME_MIN_CONFIDENCE` when Tier 3 is active.

---

## 7. Backtest Validation — FORGE Tester Integration

### 7.1 The FORGE Tester SIGNALS Table

The FORGE tester journal (`FORGE_journal_*_tester.db`) stores a `SIGNALS` table with regime context at signal evaluation time:

```sql
-- FORGE tester SIGNALS table columns (regime-relevant):
--   regime_label, regime_confidence, adx_trend_regime, high_vol_trend
-- FORGE tester TRADES table:
--   profit, pips, close_reason
```

This enables regime accuracy measurement in a controlled backtest environment — every signal evaluation has both the regime state and the eventual trade outcome.

### 7.2 Regime Accuracy Replay Query

```sql
-- For each closed trade in tester, measure regime label accuracy
-- "Accurate" = regime predicted direction matches actual win direction
SELECT
    s.regime_label,
    COUNT(*)                                        AS signals_evaluated,
    SUM(CASE WHEN t.profit > 0 THEN 1 ELSE 0 END)  AS wins,
    ROUND(AVG(CASE WHEN t.profit > 0 THEN 1.0 ELSE 0.0 END), 4)
                                                    AS win_rate,
    -- Direction accuracy: TREND_BULL + BUY should win; TREND_BEAR + SELL should win
    SUM(CASE
        WHEN s.regime_label = 'TREND_BULL' AND s.direction = 'BUY'  AND t.profit > 0 THEN 1
        WHEN s.regime_label = 'TREND_BEAR' AND s.direction = 'SELL' AND t.profit > 0 THEN 1
        ELSE 0 END)                                 AS direction_aligned_wins,
    ROUND(AVG(s.regime_confidence), 4)              AS avg_confidence
FROM SIGNALS s
JOIN TRADES t ON t.deal_ticket = s.deal_ticket
WHERE t.close_reason IN ('TP1', 'TP2', 'TP3', 'SL')
  AND s.regime_label IS NOT NULL
GROUP BY s.regime_label
ORDER BY win_rate DESC;
```

### 7.3 Confidence Calibration Measurement

The tester data can measure whether confidence is actually calibrated:

```sql
-- Confidence calibration: do high-confidence signals win more often?
-- Bin confidence into deciles and measure win rate per bin
SELECT
    ROUND(s.regime_confidence, 1)                   AS conf_bucket,
    COUNT(*)                                         AS n_signals,
    ROUND(AVG(CASE WHEN t.profit > 0 THEN 1.0 ELSE 0.0 END), 4)
                                                    AS actual_win_rate
FROM SIGNALS s
JOIN TRADES t ON t.deal_ticket = s.deal_ticket
WHERE t.close_reason IN ('TP1', 'TP2', 'TP3', 'SL')
  AND s.regime_label IS NOT NULL
GROUP BY conf_bucket
ORDER BY conf_bucket;
```

If `actual_win_rate` doesn't increase with `conf_bucket`, the confidence is not calibrated and the Platt scaling step (Section 4.1) is mandatory.

### 7.4 Addressing Gotcha 6e — Tester Regime Always Confidence 1.0

REGIME_ENGINE_REVIEW.md Gotcha 6e notes that tester backtests hardcode `g_regime_confidence = 1.0`. This means the tester cannot currently measure confidence calibration — the confidence signal is flat.

**Remediation (to implement alongside Tier 3):**
1. Change FORGE EA tester path to draw `regime_confidence` from a distribution matching live observations: uniform(0.58, 0.85) or sample from the `market_regimes` empirical distribution
2. OR: disable the confidence gate in tester entirely (`regime_apply_entry_policy=0`) and measure raw regime label accuracy against outcomes, ignoring confidence

Until this is fixed, the tester validates regime label accuracy but not confidence calibration.

---

## 8. Implementation Roadmap

### Phase 0 — Baseline Measurement (No Code Changes Required)
**Goal:** understand current regime accuracy before building anything.  
**Duration:** 1 week.  
**Data requirement:** existing closed trades in `trade_groups`.

1. Run the per-label win rate query (Section 6.2) against current data
2. Run the FORGE tester confidence calibration query (Section 7.3) against the latest tester DB
3. Record baseline metrics in a doc or spreadsheet: WR per regime label, avg confidence per label, calibration curve shape
4. This baseline becomes the "beat this" target for Tier 3

### Phase 1 — Training Pipeline + XGBoost (Minimum Viable Tier 3)
**Goal:** build and validate Tier 3 in offline mode; do not deploy to active inference yet.  
**Duration:** 2–3 weeks.  
**Minimum data requirement:** 500 closed trade groups with `regime_label` and `total_pnl` not null.

| Step | File to create | Description |
|---|---|---|
| 1 | `python/ml/__init__.py` | New `ml/` subpackage |
| 2 | `python/ml/build_training_set.py` | SQL join (Section 3.1) → parquet export |
| 3 | `python/ml/train_regime_classifier.py` | XGBoost + Platt calibration + holdout WR |
| 4 | `python/ml/evaluate_regime.py` | Per-label WR, calibration curve, SHAP values |
| 5 | `python/regime.py` | Add `_load_supervised_model_from_disk()`, `_supervised_infer()` |
| 6 | `config/.env.example` | Add `REGIME_SUPERVISED_ENABLED=false` (off by default) |

**Promotion gate:** after Phase 1 training, the holdout validation must show:
- Per-label holdout WR ≥ HMM empirical WR + 2pp for at least 3 of 4 labels
- Holdout sample ≥ 80 trades
- No label has holdout WR below 0.45

If the gate passes, set `"promoted": true` in `regime_supervised_meta.json` and enable `REGIME_SUPERVISED_ENABLED=true` in `.env`.

### Phase 2 — Monitoring Layer + Auto-Retrain
**Goal:** Tier 3 is live; add drift detection and automated weekly retraining.  
**Duration:** 2–4 weeks after Phase 1 promotion.  
**Minimum data requirement:** 1000+ closed trades.

| Step | Description |
|---|---|
| Posterior entropy | Add `_posterior_entropy()` to `infer()`, write to `market_regimes` feature_json |
| Per-label WR tracking | Add Herald alert when rolling WR drops below threshold |
| Weekly retrain cron | `scripts/retrain_regime_supervised.sh` → calls `train_regime_classifier.py` → validates → promotes if criteria met |
| Athena API | Add `/api/regime/ml_performance` endpoint with per-label WR, entropy trend, model version |
| REGIME_MIN_CONFIDENCE | Per-label calibrated thresholds from `regime_supervised_meta.json` |

### Phase 3 — LSTM Sequence Model
**Goal:** capture sequential patterns the HMM misses.  
**Duration:** estimated 4–8 weeks, after Phase 2 is stable.  
**Minimum data requirement:** 5000+ closed trades (~6–12 months of live trading).

This phase is deliberately deferred. The sequence modeling architecture decision should be made based on the SHAP feature importance output from Phase 1/2. If time-lagged features don't consistently rank in the top-5 predictors, LSTM may not add material lift over XGBoost.

---

## Summary: Estimated Timeline and Data Milestones

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      IMPLEMENTATION TIMELINE                                │
│                                                                             │
│  COLLECTING  ──────────────────────────────────────────────────────────►   │
│  (already running — market_regimes + trade_groups being populated)          │
│                                                                             │
│  Phase 0    Phase 1          Phase 2              Phase 3                  │
│  [now]      [~500 trades]    [~1000 trades]        [~5000 trades]          │
│    │             │                │                      │                 │
│    ▼             ▼                ▼                      ▼                 │
│  Baseline   XGBoost          Monitoring +          LSTM sequence           │
│  metrics    offline →        auto-retrain          model                   │
│             promoted         + Athena ML           (optional)              │
│                              dashboard                                      │
│                                                                             │
│  1 week     2–3 weeks        2–4 weeks             4–8 weeks               │
│  (no code)  after 500 tg     after Phase 1         after Phase 2           │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Milestone | Closed trades needed | Calendar estimate |
|---|---|---|
| Phase 0 baseline | 0 (existing data) | Week 1 |
| Phase 1 training ready | 500 | ~4–8 weeks at current pace |
| Phase 1 promoted | 500 + holdout validation | ~1 week after data threshold |
| Phase 2 monitoring live | 1000 | ~4–8 weeks after Phase 1 |
| Phase 3 LSTM evaluation | 5000 | ~6–12 months after Phase 2 |

The system can move to Phase 1 as soon as 500 closed `trade_groups` rows exist with non-null `regime_label` and `total_pnl`. Check current count:

```sql
SELECT COUNT(*) FROM trade_groups
WHERE status = 'CLOSED'
  AND total_pnl IS NOT NULL
  AND regime_label IS NOT NULL;
```

---

## Key Files

| File | Role |
|---|---|
| `python/regime.py` | Tier 1/2 (Gaussian + HMM); will add Tier 3 `_supervised_infer()` |
| `python/scribe.py` | Source of truth: `market_regimes`, `signals_received`, `trade_groups` |
| `python/ml/build_training_set.py` | SQL join → training parquet (to create in Phase 1) |
| `python/ml/train_regime_classifier.py` | XGBoost + calibration + holdout WR (to create in Phase 1) |
| `python/data/regime_supervised.pkl` | Tier 3 model file (created by training pipeline) |
| `python/data/regime_supervised_meta.json` | Model metadata + per-label WR + promotion flag |
| `docs/REGIME_ENGINE_REVIEW.md` | Current engine gotchas; sections 7 Medium 5/6 map to this design |

---

*This design document is the Phase 0 foundation. Implementation begins when the 500-trade data milestone is confirmed.*
