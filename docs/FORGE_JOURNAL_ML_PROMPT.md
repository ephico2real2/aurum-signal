# FORGE Journal ML Analysis — Setup Quality Scoring & AUTO_SCALPER Intelligence

> **Ref articles:**
> - [MQL5 #19065 — Python Access to MT5 Market Streams](https://www.mql5.com/en/articles/19065)
> - [MQL5 #18985 — Training and Deploying Predictive Models](https://www.mql5.com/en/articles/18985)
> - [MQL5 #14910 — Model Selection, Creation and Training](https://www.mql5.com/en/articles/14910)
> - [MQL5 Blog — Solving Gold Market Overfitting (Feb 2026)](https://www.mql5.com/en/blogs/post/767489)
> - [MFE/MAE Adaptive AI Agent (Apr 2026)](https://medium.com/@lewalskidave/your-strategy-isnt-broken-the-market-just-changed-and-your-parameters-didn-t-4f88469be3a0)
> - [Walk-Forward Validation for RL Trading (Apr 2026)](https://medium.com/@conniezhou678/machine-learning-for-algorithmic-trading-part-21-from-research-to-reality-walk-forward-31756db6c044)
> - [Market Regime Classifier with Python (2026)](https://www.technical-analysis-pro.com/strategies-market-regime-classifier-python-machine-learning/)
> - [github.com/andywarui/xaubot — LightGBM XAUUSD (66% WR, 1.96 PF)](https://github.com/andywarui/xaubot)
> - [github.com/kennycornellius-collab/DRL-XAUUSD-Bot — Deep RL XAUUSD](https://github.com/kennycornellius-collab/DRL-XAUUSD-Bot)

---

## 1. Problem Statement

FORGE's native scalper evaluates thousands of setups per session. The signal journal
(`FORGE_journal_XAUUSD.db` / `FORGE_journal_XAUUSD_tester.db`) records every evaluation
with full indicator context. Current backtest shows:

- **~88k** `no_setup` skips (no BB conditions met)
- **~5k** `rr_too_low` skips (setup found but R:R insufficient)
- **0** `TAKEN` trades in some windows

**Questions this system answers:**

1. Which skipped setups would have been profitable? (missed opportunity detection)
2. Can we train an ML model to score setup quality using the journal's feature set?
3. Can that model feed AUTO_SCALPER (via AURUM) and AEGIS to improve decisions?

### Data stack for ML (consolidated vs raw)

- **Preferred:** query **`aurum_intelligence.db`** only. After BRIDGE runs, **`forge_signals`** holds one row per journaled evaluation (**TAKEN** + **SKIP** with `gate_reason`). **`forge_journal_trades`** holds **deal-level** P&L rows imported from MT5 history into the FORGE journal, tagged with **`journal_source`** (`live` \| `tester`). Join on **time / magic / comment** (e.g. `SCALP|…|G5001`) as needed. **`trade_groups`** / **`trade_closures`** add lifecycle context for actual executions.
- **Optional:** read the raw **`FORGE_journal_*.db`** files for debugging, backfill, or when BRIDGE was offline — same schema, no `journal_source` in the file (path/filename implies tester vs live).
- **Health check:** `make journal-diagnose` or `python3 scripts/diagnose_forge_journal.py`.

---

## 2. Architecture Overview

```
                    ┌──────────────────────────────────┐
                    │   FORGE Journal DB (SQLite)       │
                    │   live: FORGE_journal_XAUUSD.db   │
                    │   test: ..._tester.db             │
                    └──────────┬───────────────────────┘
                               │
                    ┌──────────▼───────────────────────┐
                    │  Phase 1: analyze_journal.py      │
                    │  - Load journal signals (pandas)  │
                    │  - Fetch M5 bars (MT5 Python lib) │
                    │  - Compute MFE/MAE per skip       │
                    │  - Label: MISSED_TP / CORRECT_SKIP│
                    │  - Gate accuracy report            │
                    │  - CSV export                      │
                    └──────────┬───────────────────────┘
                               │
                    ┌──────────▼───────────────────────┐
                    │  Phase 2: train_setup_scorer.py   │
                    │  - Feature matrix from journal    │
                    │  - Label: PROFITABLE / UNPROFITABLE│
                    │  - GradientBoosting / XGBoost     │
                    │  - Walk-forward TimeSeriesSplit    │
                    │  - Export model.pkl + metrics      │
                    └──────────┬───────────────────────┘
                               │
                    ┌──────────▼───────────────────────┐
                    │  Phase 3: Integration             │
                    │  ┌─────────────────────────────┐  │
                    │  │  BRIDGE / AUTO_SCALPER      │  │
                    │  │  ml_score injected into     │  │
                    │  │  AURUM prompt context       │  │
                    │  └─────────────────────────────┘  │
                    │  ┌─────────────────────────────┐  │
                    │  │  AEGIS                      │  │
                    │  │  ml_confidence gate:        │  │
                    │  │  reject if score < threshold│  │
                    │  └─────────────────────────────┘  │
                    │  ┌─────────────────────────────┐  │
                    │  │  FORGE native (future)      │  │
                    │  │  Read model predictions via │  │
                    │  │  JSON file or REST endpoint │  │
                    │  └─────────────────────────────┘  │
                    └──────────────────────────────────┘
```

---

## 3. Phase 1 — Journal Analysis CLI (`scripts/analyze_journal.py`)

### 3a. Purpose

Standalone CLI that reads the FORGE journal DB, fetches actual price data for each
skipped setup, and reports which skips were genuinely missed profitable trades.

### 3b. CLI Interface

```bash
# Analyze tester journal — 30 min lookahead
python3 scripts/analyze_journal.py --source tester --lookahead 30

# Analyze live journal, filter to R:R rejects only
python3 scripts/analyze_journal.py --source live --gate rr_too_low

# Export full results to CSV
python3 scripts/analyze_journal.py --source tester --export results/journal_missed.csv

# Show top 20 biggest missed opportunities
python3 scripts/analyze_journal.py --source tester --top 20
```

### 3c. Implementation Steps

**Step 1 — DB Loader**

```python
def load_journal(source: str) -> pd.DataFrame:
    """Auto-detect tester or live journal DB path, load SIGNALS table."""
    # Use same path resolution as bridge.py _resolve_forge_journal_paths()
    # Return DataFrame with columns: time, setup_type, direction, outcome,
    #   gate_reason, price, atr, rsi, adx, bb_upper, bb_lower, bb_mid,
    #   vwap_price, fib_50, rsi_divergence, psar_state, h1_trend, session
```

**Step 2 — Price Fetcher (M5 bars)**

Primary: MetaTrader5 Python library (`mt5.copy_rates_range`).
Fallback: SCRIBE `market_snapshots` table for approximate data.

```python
def fetch_bars(symbol: str, start: datetime, end: datetime,
               timeframe=mt5.TIMEFRAME_M5) -> pd.DataFrame:
    """Fetch M5 bars for the journal time range."""
```

**Step 3 — Opportunity Scorer**

For each SKIP signal with `price`, `atr`, `direction` (inferred from setup context):

```python
def score_opportunity(signal: dict, bars_after: pd.DataFrame,
                      sl_mult: float, tp_mult: float) -> dict:
    """
    Compute:
    - mfe: max favorable excursion (best price in trade direction)
    - mae: max adverse excursion (worst price against)
    - tp_would_hit: bool — price reached hypothetical TP
    - sl_would_hit_first: bool — SL triggered before TP
    - label: MISSED_TP | CORRECT_SKIP | BORDERLINE
    """
```

**Step 4 — Report Generator**

Output:
```
FORGE Journal Analysis — tester (93,196 signals)
================================================
Outcome breakdown:
  SKIP/no_setup:             88,359 (94.8%)
  SKIP/rr_too_low:            4,838 (5.2%)
  TAKEN:                          0

Missed Opportunity Analysis (lookahead=30min):
  rr_too_low where TP would hit:     312 / 4,838 (6.4%)
  rr_too_low with MFE > 2×ATR:        89 / 4,838 (1.8%)

Gate Accuracy Scores:
  rr_too_low:          93.6% correct skips
  direction_cooldown:  87.2% correct skips
  no_setup:            99.1% correct skips (rarely moves)

Top 10 Missed Trades:
  2026-04-01 14:32  BB_BOUNCE BUY  rr_too_low  MFE=+$8.40  TP=$7.20
  ...
```

### 3d. File

- **New**: `scripts/analyze_journal.py` (~300 lines)

---

## 4. Phase 2 — ML Setup Quality Scorer (`scripts/train_setup_scorer.py`)

### 4a. Purpose

Train a machine learning model on the journal data to predict whether a setup would
be profitable. The model learns from FORGE's own indicator snapshot at the moment of
each decision.

### 4b. Feature Matrix

The journal already records the ideal feature set (no additional data needed):

| Feature | Source (journal column) | Why |
|---------|------------------------|-----|
| `atr` | `atr` | Volatility context |
| `rsi` | `rsi` | Momentum / overbought-oversold |
| `adx` | `adx` | Trend strength |
| `bb_width` | `bb_upper - bb_lower` | Squeeze / expansion state |
| `bb_position` | `(price - bb_lower) / (bb_upper - bb_lower)` | Where price sits in BB range |
| `h1_trend` | `h1_trend` | Higher-TF directional bias |
| `vwap_dist` | `price - vwap_price` | Distance from VWAP |
| `fib_50_dist` | `price - fib_50` | Distance from Fibonacci midpoint |
| `rsi_div` | `rsi_divergence` (one-hot) | Divergence type |
| `psar_state` | `psar_state` (one-hot) | Parabolic SAR direction |
| `regime_confidence` | `regime_confidence` | Regime model confidence |
| `session` | `session` (one-hot) | Trading session context |
| `spread` | `spread` | Execution cost proxy |
| `pattern_score` | `pattern_score` | Candle pattern quality |

**14 features** — all available in the journal. No external data fetch needed for training.

### 4c. Label Generation

Using Phase 1's opportunity scorer output:

```python
# Label = 1 (PROFITABLE) if:
#   - MFE > 1.5 × ATR within lookahead AND
#   - SL would NOT have been hit first (using min_sl_atr_mult floor)
#
# Label = 0 (UNPROFITABLE) otherwise
```

### 4d. Model Pipeline

```python
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit, RandomizedSearchCV

pipe = Pipeline([
    ('scaler', StandardScaler()),
    ('gb', GradientBoostingClassifier(random_state=42))
])

param_dist = {
    'gb__learning_rate': [0.01, 0.05, 0.1],
    'gb__n_estimators': [300, 500, 700],
    'gb__max_depth': [2, 3, 4],
    'gb__subsample': [0.8, 0.9, 1.0],
}

# Walk-forward split to avoid look-ahead bias (critical for financial data)
cv = TimeSeriesSplit(n_splits=5)
search = RandomizedSearchCV(pipe, param_dist, n_iter=15,
                            cv=cv, scoring='roc_auc', n_jobs=-1)
search.fit(X, y)

# Save model + metadata
joblib.dump(search.best_estimator_, 'models/setup_scorer.pkl')
```

**Anti-overfitting measures** (per MQL5 blog research on gold market overfitting):
- TimeSeriesSplit (never train on future data)
- Walk-forward validation with rolling windows
- Feature importance analysis to prune noise features
- Out-of-sample accuracy must exceed 55% to be deployed (above random)
- Model staleness check: retrain weekly from latest journal data

### 4e. CLI

```bash
# Train on tester journal
python3 scripts/train_setup_scorer.py --source tester --lookahead 30

# Train on live journal
python3 scripts/train_setup_scorer.py --source live --lookahead 15

# Output:
#   models/setup_scorer.pkl       — serialized model
#   models/setup_scorer_meta.json — accuracy, features, train date, sample count
#   models/feature_importance.csv — ranked feature weights
```

### 4f. File

- **New**: `scripts/train_setup_scorer.py` (~250 lines)
- **New**: `models/` directory for model artifacts

---

## 5. Phase 3 — Integration with AUTO_SCALPER & AEGIS

### 5a. Scoring Service (`python/ml_scorer.py`)

Lightweight module that loads the trained model and scores setups on demand.

```python
class SetupScorer:
    def __init__(self, model_path="models/setup_scorer.pkl"):
        self.model = joblib.load(model_path)
        self.meta = json.load(open(model_path.replace('.pkl', '_meta.json')))

    def score(self, features: dict) -> dict:
        """
        Args: dict with keys matching journal columns
              (atr, rsi, adx, bb_upper, bb_lower, price, h1_trend, ...)
        Returns: {"ml_score": 0.73, "ml_label": "PROFITABLE", "model_age_hours": 12}
        """
```

### 5b. AUTO_SCALPER Integration (BRIDGE → AURUM prompt)

In `bridge.py` `_auto_scalper_logic()`, inject ML score into the AURUM prompt:

```python
# After building MTF view, before AURUM prompt
scorer = self._get_setup_scorer()
if scorer:
    features = {
        "atr": m5.get("atr_14"),
        "rsi": m5.get("rsi_14"),
        "adx": m5.get("adx_14"),
        "bb_upper": m5.get("bb_upper"),
        "bb_lower": m5.get("bb_lower"),
        "price": price_mid,
        "h1_trend": h1_trend_strength,
        "vwap_price": ...,  # from market_data.json
        "session": current_session,
    }
    ml_result = scorer.score(features)
    prompt += f"\nML Setup Score: {ml_result['ml_score']:.0%} "
    prompt += f"(model trained {ml_result['model_age_hours']:.0f}h ago)\n"
    prompt += "If ML score < 40%, strongly prefer PASS.\n"
```

This gives AURUM data-backed confidence to decide. AURUM already weighs multiple
factors — the ML score becomes one more input.

### 5c. AEGIS Integration (optional gate)

Add an optional ML confidence gate in `aegis.py` `validate()`:

```python
# New .env: AEGIS_ML_SCORE_MIN=0.0  (disabled by default)
# When > 0, AEGIS rejects setups below the threshold

ml_min = float(os.environ.get("AEGIS_ML_SCORE_MIN", "0.0"))
if ml_min > 0 and signal.get("ml_score", 1.0) < ml_min:
    return AegisResult(approved=False, skip_reason=f"ML_SCORE_LOW:{ml_score:.2f}<{ml_min}")
```

### 5d. FORGE Native Integration (future phase)

BRIDGE writes `ml_score` to `MT5/ml_signal.json`. FORGE reads it and uses as an
additional entry filter. This eliminates the Python round-trip for native scalper
entries. **Not in this implementation — future phase.**

### 5e. Retraining Schedule

```bash
# Add to Makefile
ml-retrain:
    python3 scripts/train_setup_scorer.py --source live --lookahead 15
    @echo "Model retrained from live journal"

# Cron or manual: run weekly after sufficient new journal data
```

### 5f. Files

- **New**: `python/ml_scorer.py` (~80 lines)
- **Modified**: `python/bridge.py` — inject ML score in AUTO_SCALPER prompt
- **Modified**: `python/aegis.py` — optional ML gate (disabled by default)
- **New**: `models/` directory
- **Modified**: `Makefile` — `ml-retrain` target
- **Modified**: `.env.example` — `AEGIS_ML_SCORE_MIN` documentation

---

## 6. MFE/MAE Trade Geometry — Deep Dive

MFE (Maximum Favorable Excursion) and MAE (Maximum Adverse Excursion) are the core
metrics that turn the journal from a log into intelligence. Per recent research
(Lewalski Apr 2026), MFE/MAE distributions reveal:

- **SL calibration quality**: If MAE distributions are tight but SL is wide, the SL
  is wasting capital protection. If MAE frequently exceeds SL, the SL is too tight.
- **TP realism**: If average MFE is $5.00 but TP target is $12.00, the system is
  holding for targets that rarely materialize.
- **Regime sensitivity**: MFE/MAE distributions shift with volatility and trend
  character — a model trained on ranging MFE will fail in trending conditions.

### Vectorized Computation (pandas)

```python
def compute_mfe_mae(signals: pd.DataFrame, bars: pd.DataFrame,
                    lookahead_min: int = 30) -> pd.DataFrame:
    """
    For each signal, slice bars in [signal_time, signal_time + lookahead]
    and compute MFE/MAE relative to signal price and direction.

    Returns signals with added columns:
      mfe, mae, mfe_time, mae_time, tp_would_hit, sl_would_hit_first
    """
    results = []
    for _, sig in signals.iterrows():
        t0 = sig['time']
        t1 = t0 + pd.Timedelta(minutes=lookahead_min)
        window = bars[(bars['time'] >= t0) & (bars['time'] <= t1)]

        if window.empty:
            results.append({**sig, 'mfe': 0, 'mae': 0,
                           'tp_would_hit': False, 'sl_would_hit_first': False})
            continue

        direction = sig.get('direction', 'BUY')
        entry = sig['price']
        atr = sig['atr']

        if direction == 'BUY':
            mfe = (window['high'].max() - entry)
            mae = (entry - window['low'].min())
            tp_price = entry + atr * sig.get('tp_mult', 2.0)
            sl_price = entry - atr * sig.get('sl_mult', 1.2)
            tp_bar = window[window['high'] >= tp_price].head(1)
            sl_bar = window[window['low'] <= sl_price].head(1)
        else:
            mfe = (entry - window['low'].min())
            mae = (window['high'].max() - entry)
            tp_price = entry - atr * sig.get('tp_mult', 2.0)
            sl_price = entry + atr * sig.get('sl_mult', 1.2)
            tp_bar = window[window['low'] <= tp_price].head(1)
            sl_bar = window[window['high'] >= sl_price].head(1)

        tp_hit = not tp_bar.empty
        sl_hit = not sl_bar.empty
        sl_first = sl_hit and (sl_bar.index[0] < tp_bar.index[0] if tp_hit else True)

        results.append({
            **sig,
            'mfe': round(mfe, 2),
            'mae': round(mae, 2),
            'tp_would_hit': tp_hit and not sl_first,
            'sl_would_hit_first': sl_first,
        })
    return pd.DataFrame(results)
```

### Distribution Analysis

The report includes MFE/MAE percentiles per gate reason:

```
MFE Distribution (rr_too_low skips, 30min lookahead):
  P25:   $0.82     P50:   $2.10     P75:   $4.30     P95:   $8.90
MAE Distribution (rr_too_low skips, 30min lookahead):
  P25:   $0.45     P50:   $1.20     P75:   $2.80     P95:   $6.10
```

These distributions directly inform SL/TP tuning in `scalper_config.json`.

---

## 7. Walk-Forward Retraining Protocol

Per walk-forward validation research (Zhou Apr 2026, InsightBig):

### Why Standard Cross-Validation Fails for Trading

Standard k-fold CV randomly shuffles data, allowing the model to "see the future."
Financial time-series have autocorrelation and regime shifts that make this
invalidating. Walk-forward is the only honest validation approach.

### Rolling Window Implementation

```python
from sklearn.model_selection import TimeSeriesSplit

def walk_forward_train(X: pd.DataFrame, y: pd.Series,
                       pipe: Pipeline, n_splits: int = 5) -> dict:
    """
    Walk-forward validation:
      Split 1: train [0..20%],  test [20..25%]
      Split 2: train [0..40%],  test [40..45%]
      ...
      Split N: train [0..80%],  test [80..85%]
    """
    tscv = TimeSeriesSplit(n_splits=n_splits)
    scores = []
    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
        pipe.fit(X_train, y_train)
        score = pipe.score(X_test, y_test)
        scores.append(score)

    return {
        "mean_accuracy": np.mean(scores),
        "std_accuracy": np.std(scores),
        "fold_scores": scores,
        "degradation": scores[-1] - scores[0],  # negative = model degrades on recent data
    }
```

### Retraining Triggers

The model should be retrained when any of:
1. **7+ days since last train** — staleness decay kicks in
2. **500+ new journal entries** — enough new data for meaningful update
3. **Accuracy drift** — live prediction accuracy drops >5% from training accuracy
4. **Regime change** — BRIDGE regime engine detects a new label

### Model Staleness Discount

When serving predictions, the scorer applies a staleness discount:

```python
age_hours = (now - model_meta['train_time']).total_seconds() / 3600
staleness_factor = max(0.5, 1.0 - (age_hours / (7 * 24)) * 0.5)
adjusted_score = raw_score * staleness_factor
```

After 7 days without retrain, the model's effective score is halved — forcing
conservative behavior until fresh data arrives.

---

## 8. Dependencies

Phase 1 & 2 require:
```
pandas          (already installed)
numpy           (already installed)
scikit-learn    (pip install scikit-learn)
joblib          (included with scikit-learn)
MetaTrader5     (already installed for BRIDGE)
```

No new heavy dependencies. scikit-learn is the only addition.

---

## 9. Implementation Order

| Phase | What | Effort | Depends on |
|-------|------|--------|------------|
| **1** | `analyze_journal.py` — missed opportunity CLI | ~300 lines | Journal DB (done) |
| **2** | `train_setup_scorer.py` — ML model training | ~250 lines | Phase 1 labels |
| **3a** | `ml_scorer.py` — scoring service | ~80 lines | Phase 2 model |
| **3b** | BRIDGE integration — AUTO_SCALPER prompt | ~20 lines | Phase 3a |
| **3c** | AEGIS integration — optional ML gate | ~15 lines | Phase 3a |
| **3d** | Docs, .env, Makefile, CHANGELOG | ~50 lines | All above |

**Phase 1 is standalone and immediately useful** — it answers "what did we miss?"
without any ML. Phases 2-3 build on top to make the system self-improving.

---

## 10. Anti-Overfitting Protocol

Per research on gold market ML overfitting (MQL5 blog Feb 2026):

1. **Never train on test data** — strict TimeSeriesSplit with walk-forward windows
2. **Minimum 55% out-of-sample accuracy** to deploy — below this, model is noise
3. **Feature importance audit** — if >60% weight on one feature, model is fragile
4. **Staleness decay** — model score is discounted linearly after 7 days without retrain
5. **AEGIS gate starts at 0.0** (disabled) — operator must explicitly enable after validating model quality
6. **Log everything** — every ML-influenced decision is logged to SCRIBE with `ml_score` for post-hoc audit

---

## 11. Version & Changelog

- **Shipped:** `SYSTEM_VERSION` **1.7.3**, FORGE **`VERSION` 2.4.3** — `forge_signals` idempotency guard, configurable `batch_size` on sync methods, focused offline journal tests, `make test-journal`. Prior: 1.7.2 — journal skip throttling, `forge_journal_trades`, BRIDGE tester discovery, `make journal-diagnose`. See root `CHANGELOG.md`.
- **Data quality note (2026-05-06):** `forge_signals WHERE journal_source='tester'` currently contains ~102,000 rows synced before the spam fix. The remaining 2.1M-row pre-fix backlog was **intentionally skipped** (100% `SKIP|no_setup` / `SKIP|rr_too_low`, zero `TAKEN`). Always filter `WHERE gate_reason NOT LIKE 'SKIP%'` or `WHERE outcome IS NOT NULL` before using tester rows for ML training.
- **After Phase 1 (analyze_journal CLI):** bump `SYSTEM_VERSION` if the script ships standalone.
- **After Phase 3 (ML in production):** consider `SYSTEM_VERSION` **1.9.0** (or next minor) and full CHANGELOG entry.
