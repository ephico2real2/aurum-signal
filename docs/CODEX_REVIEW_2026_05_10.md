# FORGE Signal System — Code Review 2026-05-10

> Reviewed files: `python/regime.py`, `python/bridge.py`, `python/aegis.py`, `python/athena_api.py`, `python/scribe.py`, `ea/FORGE.mq5`
> Reviewer: Codex (GPT-5.4) + Claude — read-only analysis, no source files modified.

---

## 1. Bugs

### B-1 — Stale regime snapshot leaks into live decisions after inference failure
**File:** `python/bridge.py` ~lines 2324–2358, 4976–5009
**Severity:** High

If `RegimeEngine.predict()` raises (bad feature vector, model not ready, etc.), the bridge catches the exception and continues the tick loop without updating `_last_regime_snapshot`. The stale snapshot is then written into `regime_state.json` and consumed by AEGIS and FORGE. The EA may trade under an incorrect regime for an extended window — potentially through a full adverse session — with no warning in the UI.

**Fix:** On inference failure, write a `"regime": "UNKNOWN"` sentinel (or the existing `error` key) into the snapshot *and* pass it through to AEGIS so countertrend gates default to the most conservative posture until the engine recovers.

---

### B-2 — FORGE keeps previous regime gate state if `config.json` becomes unreadable
**File:** `ea/FORGE.mq5` ~lines 927–929, 962–985, 3378–3384
**Severity:** High

`ReadRegimeConfig()` returns early (false) if the file is missing or malformed, but the gate variables (`g_regime_allow_buy`, `g_regime_allow_sell`, etc.) are not reset to safe defaults. If the file disappears mid-session the EA continues trading under whatever gate posture it last read. This is particularly dangerous during a flip from TRENDING to RANGING — the old trending gates stay active.

**Fix:** At the top of `ReadRegimeConfig()`, reset all gate booleans to their safest default (e.g., both sides blocked or both sides permitted depending on your risk posture) before any conditional read logic.

---

### B-3 — Lot sizing falls through to zero on unknown symbol precision
**File:** `python/aegis.py` ~lines 280–310
**Severity:** Medium

`_normalize_lot()` uses a lookup table of known symbol precisions. For an unlisted symbol the function returns `None`, which propagates to the order dict and causes MT5 to reject the order with retcode 10014. The failure is logged but the calling function does not abort the signal cleanly — it continues to write the order JSON with `lot: None`.

**Fix:** Add a final fallback: `return max(SYMBOL_VOLUME_MIN, round(lot, 2))` and ensure callers check for `None` before writing the order file.

---

### B-4 — `/api/management` raises unhandled on bad input before write error handler
**File:** `python/athena_api.py` ~lines 1017–1024
**Severity:** High

The route performs `float(request.form['sl'])` without a try/except. A malformed POST (empty field, non-numeric string) raises `ValueError` which Flask surfaces as a 500 with a stack trace. Since Athena is occasionally accessed via CLI curl scripts, this is reachable in practice.

**Fix:** Wrap the form field coercions in a try/except and return a 400 JSON error before any database write is attempted.

---

### B-5 — `_fj_src_cols_cache` and related caches never invalidated across DB reconnects
**File:** `python/scribe.py` ~lines 780–812
**Severity:** Medium

The column-list caches (`_fj_src_cols_cache`, `_fj_wall_time_cache`, `_fj_aurum_run_cache`, `_fj_dedup_index_cache`) are class-level dicts. If the underlying SQLite file is rotated (e.g., backtest vs. live DB swap) without restarting the process, the caches hold column lists from the old schema. Subsequent inserts silently drop columns that exist in the new schema but not in the cache.

**Fix:** Tie cache invalidation to the DB path: key the cache on `(db_path, table_name)` and clear on each `connect()` call.

---

## 2. Race Conditions (Async HMM Training)

### RC-1 — `_training_in_progress` read/set/cleared outside `_train_lock`
**File:** `python/regime.py` ~lines 354–364, 401
**Severity:** High

The guard that prevents double-starting a background fit reads `_training_in_progress` *before* acquiring `_train_lock`, sets it *before* the lock, and clears it *inside* the lock at the end of the worker thread. Two concurrent callers (e.g., the bridge tick + an API call to `/api/regime/train`) can both observe `_training_in_progress == False`, both enter the training branch, and start two concurrent `GaussianHMM.fit()` runs on the same deque snapshot. The second fit overwrites the first model atomically but wastes CPU and can produce a model trained on an inconsistent window.

**Fix:**
```python
with self._train_lock:
    if self._training_in_progress:
        return
    self._training_in_progress = True
# ... spawn thread
```
Move the guard and the flag set inside a single `_train_lock` acquisition. Use a `threading.Event` for the running state to make it easier to await completion from tests.

---

### RC-2 — HMM model state cleared outside `_train_lock`
**File:** `python/regime.py` ~lines 271–276
**Severity:** Medium

`reset()` (or equivalent invalidation) sets `self.model = None` and `self._fitted = False` without holding `_train_lock`. A concurrent `predict()` call that holds `_train_lock` long enough to copy `self.model` and then calls `model.predict()` after `reset()` has run will operate on a model that has been conceptually invalidated. The predict still succeeds because the object is still alive, but the result is reported as valid against a regime that has been reset.

**Fix:** Acquire `_train_lock` inside `reset()` before nulling model state, or add a separate `_infer_lock` that both `predict()` and `reset()` respect.

---

### RC-3 — Deque snapshot taken without lock during async training
**File:** `python/regime.py` ~lines 242–282, 362
**Severity:** Medium

The training worker thread receives a `list(self._history)` snapshot. The snapshot is taken in the calling thread before `_train_lock` is acquired, meaning the main bridge loop can `appendleft()` to the deque between the snapshot and the start of `fit()`. The resulting model is fit on data that may not match what `predict()` later uses. This is unlikely to cause catastrophic errors but introduces a subtle window inconsistency that degrades regime stability after a retrain.

**Fix:** Take the deque snapshot *inside* `_train_lock`:
```python
with self._train_lock:
    snapshot = list(self._history)
    self._training_in_progress = True
# spawn thread with snapshot
```

---

### RC-4 — `_prev_mid` not protected under any lock
**File:** `python/regime.py` ~lines 271–276 (approximate — wherever `_prev_mid` is updated)
**Severity:** Low

`_prev_mid` (used to compute price velocity as an HMM feature) is updated in the inference path without holding `_train_lock`. If inference is ever made concurrent (e.g., separate threads per symbol), two writers can produce a corrupt velocity feature. Currently the bridge is single-threaded for inference, so this is latent rather than active.

**Fix:** Document the single-caller assumption with an assertion or use an `RLock` when updating `_prev_mid`.

---

## 3. MLops Opportunities

### ML-1 — Supervised regime labeling from closed trade outcomes
**Files:** `python/scribe.py` (tables `market_regimes`, `trade_groups`), `python/regime.py`
**Severity:** Opportunity

`market_regimes.feature_json` stores the raw HMM feature vector at the time of each regime classification. `trade_groups` stores `open_context` (regime at open), final P&L, and closure reason. This is the core dataset for a supervised regime quality classifier:

- **Target:** `profitable` (bool) or `outcome_bucket` (win/scratch/loss)
- **Features:** `feature_json` columns at signal time + session, symbol, direction
- **Model:** Gradient-boosted classifier (XGBoost or LightGBM) predicting trade outcome from regime features
- **Use:** Replace or augment HMM state label with a learned "regime quality" score that can gate entries probabilistically rather than as hard on/off

A first version can be trained offline from the existing DB and pickled alongside the HMM model. The bridge can load and call it on every regime transition.

---

### ML-2 — Gate calibration using FORGE journal feature columns
**Files:** `python/scribe.py` ~lines 813–1035, `ea/FORGE.mq5` ~lines 3988–4036
**Severity:** Opportunity

The FORGE journal (tester DB) captures `rsi_at_entry`, `adx_at_entry`, `bb_width_at_entry`, `m5_quality_at_entry`, `entry_reason`, and gate outcomes. These are exactly the inputs to the existing hard-coded gate thresholds. A logistic regression or decision tree trained on these features against binary outcome (SL hit vs. TP/time-exit) can produce calibrated gate thresholds with confidence intervals, replacing the current hand-tuned values.

Suggested pipeline:
1. Export `forge_journal` rows with all gate features + `outcome` label.
2. Train a calibrated binary classifier per symbol/session segment.
3. Compute optimal thresholds via Youden's J or F1 grid search.
4. Emit updated thresholds to `scalper_config.json` via the existing env sync pipeline.

---

### ML-3 — Regime transition prediction (look-ahead smoothing)
**File:** `python/regime.py`
**Severity:** Opportunity

The HMM emits a point-in-time state but does not model transition probability over the next N bars. `market_regimes` has enough rows to train a simple sequence model (even a 2nd-order Markov chain) on the observed state sequence. This gives a transition probability that can be used to suppress entries when the model assigns >30% probability of switching away from the current regime within the trade's expected duration.

---

### ML-4 — Feature importance audit before next HMM refit
**File:** `python/regime.py` ~lines 371–383
**Severity:** Opportunity / Accuracy

The current HMM features mix raw price velocity (in pips), ATR (in price units), RSI (0–100), and Bollinger Band width (dimensionless ratio). Without standardization, the Gaussian emission distributions are dominated by the highest-variance features (typically ATR on volatile days). A `StandardScaler` fit on the training window and persisted alongside the HMM pickle would make emission parameters more interpretable and the model less sensitive to volatility spikes.

Suggested change in `regime.py`:
```python
from sklearn.preprocessing import StandardScaler
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)
self.model.fit(X_scaled)
# persist scaler with pickle alongside model
```

---

### ML-5 — Online regime evaluation against trade outcomes
**Files:** `python/scribe.py`, `python/bridge.py`
**Severity:** Opportunity

Add a nightly job (cron or bridge idle hook) that:
1. Joins `market_regimes` with `trade_groups` on `open_time` window overlap.
2. Computes per-regime WR, avg P&L, and SL rate for the trailing 30/90 days.
3. Writes a `regime_performance` summary table to the Scribe DB.
4. Exposes it via a new `/api/regime/performance` endpoint in Athena.

This closes the feedback loop: the HMM is unsupervised, but the labeled performance data gives you an empirical prior to weight regime decisions. If RANGING has had 40% WR for 30 days, you can apply a conservative lot multiplier even when the HMM confidently labels RANGING.

---

## 4. Performance Bottlenecks

### P-1 — Bridge tick loop runs all I/O synchronously at 1 s cadence
**File:** `python/bridge.py` `_tick()` function ~lines 2789–2990
**Severity:** High

Every tick performs (in the hot path, serially):
1. `json.load()` of `regime_state.json`, `command_queue.json`, and up to N symbol tick files
2. HMM `predict()` (involves numpy matrix multiply on history window)
3. `scribe.upsert_regime()` SQLite write
4. Signal validation (possibly additional SQLite reads in AEGIS)
5. `json.dump()` of `status.json`, `regime_state.json`, output signal files

On a busy session with 4+ symbols this is 10–15 file system operations per second plus 2–4 SQLite transactions. If the OS disk cache is warm this is typically sub-50 ms, but on wine-mounted MT5 paths (which are virtual filesystem) I/O can spike to 200–400 ms, causing the bridge to fall behind and pile up command queue entries.

**Recommendations:**
- Batch symbol tick reads with a single `os.scandir()` pass rather than per-symbol `open()` calls.
- Move `upsert_regime()` to an async write queue (same pattern as current training thread) — regime rows do not need to be committed before the next tick.
- Cache the `status.json` dict and only write it when any field changes.

---

### P-2 — Session P&L queried twice per signal validation in AEGIS
**File:** `python/aegis.py` ~lines 556–558, 625–628
**Severity:** Medium

`validate_signal()` calls `scribe.get_session_pnl()` once to check the session loss limit and again inside `_check_daily_drawdown()`. Both calls hit the same `trade_groups` aggregation query with a `WHERE close_time > session_start` filter. On an active session with many closed trades this query can scan thousands of rows twice per validation.

**Fix:** Compute session P&L once at the top of `validate_signal()`, pass it as a parameter to all sub-checks, or cache it with a 1-second TTL.

---

### P-3 — `/api/live` endpoint combines file reads + DB analytics in one blocking call
**File:** `python/athena_api.py` ~lines 452–620
**Severity:** Medium

The `/api/live` route reads multiple JSON status files, queries the regime table, queries open trades, and serializes everything into one response. Since Flask runs in single-threaded dev mode, this blocks all other API requests (including `/api/status` polled by the CLI) for the duration of the query. On a slow NFS/wine path this can be 500 ms+.

**Fix:** Run Flask with `threaded=True` (already supported) and add a 2-second in-memory cache on the `/api/live` response using `functools.lru_cache` with a time-based invalidation wrapper or `cachetools.TTLCache`.

---

### P-4 — HMM `predict()` called even when feature vector is unchanged
**File:** `python/regime.py` ~lines 371–383 (predict path), `python/bridge.py` tick loop
**Severity:** Low

If no new tick data arrived for a symbol (flat market, weekend), the feature vector is identical to the previous call. The bridge still calls `predict()` which performs the full Viterbi/forward algorithm. For XAUUSD on a fast 1 s loop this is unnecessary work.

**Fix:** Hash the feature tuple and skip `predict()` if the hash matches the previous call's hash. Return the cached `(state, posterior)` instead.

---

## 5. Missing Error Handling / Silent Failures

### E-1 — `json.load()` on signal files not wrapped; file truncation causes unhandled `JSONDecodeError`
**File:** `python/bridge.py` ~lines 220–510 (file-read helpers)
**Severity:** High

MT5 writes signal files non-atomically (open → write → close without rename). If the bridge reads a file mid-write it gets a partial JSON and `json.load()` raises `JSONDecodeError`. Some read helpers wrap this, others do not. The unhandled exception propagates to the tick loop and, depending on the outer try/except scope, can silently drop the entire tick.

**Fix:** Standardize all JSON file reads behind a single `_safe_json_load(path, default=None)` helper that catches `JSONDecodeError` and `OSError`, logs at WARNING, and returns the default. Use atomic rename (write to `.tmp`, then `os.replace()`) on all bridge-side JSON writes.

---

### E-2 — Pickle load does not validate model schema version
**File:** `python/regime.py` ~lines 608–613 (approximate load path)
**Severity:** Medium

`pickle.load()` on the persisted HMM model has no version guard. If the `RegimeEngine` class gains new attributes between restarts (e.g., adding a scaler), loading an old pickle silently gives an object missing those attributes. The first access to the missing attribute raises `AttributeError` inside `predict()`, which the bridge catches generically and logs — meaning the regime engine silently falls back to the default state without alerting the operator.

**Fix:** Store a `MODEL_VERSION = "2.6.x"` constant in the pickle payload dict. On load, compare and refuse to load (or retrain from scratch) if the version does not match.

---

### E-3 — Scribe `upsert_regime()` swallows `sqlite3.OperationalError` on locked DB
**File:** `python/scribe.py` ~lines 260–300 (approximate upsert path)
**Severity:** Medium

The upsert uses `execute()` inside a broad `except Exception: logger.warning(...)` block. A `database is locked` error (common when the tester and bridge share an SQLite file) is silently swallowed. The regime row is lost with no retry. Over a session this can produce gaps in `market_regimes` that break the MLops joins described in Section 3.

**Fix:** Distinguish `sqlite3.OperationalError` from other exceptions, implement a simple retry-with-backoff (3 attempts, 50 ms spacing), and escalate to `logger.error` after all retries fail.

---

### E-4 — FORGE does not emit a machine-readable error if regime file age exceeds staleness threshold
**File:** `ea/FORGE.mq5` ~lines 430–760
**Severity:** Low

FORGE checks `FileGetInteger(FORGE_REGIME_FILE, FILE_MODIFY_DATE)` and suppresses entries if the file is stale, but it only prints to the MT5 Experts log. The bridge has no visibility into this gate firing. In production the operator may not notice that entries have been silently blocked for 30+ minutes due to a bridge crash.

**Fix:** Write a machine-readable `{"staleness_gate": true, "stale_seconds": N}` field into the command-response JSON so the bridge can surface it in Athena's `/api/live` response.

---

### E-5 — `_check_daily_drawdown` can raise `TypeError` if `scribe` returns `None` for P&L
**File:** `python/aegis.py` ~lines 625–628
**Severity:** Medium

If `scribe.get_session_pnl()` returns `None` (DB error, empty table, first run of the day), the comparison `session_pnl < -self.config.max_daily_loss` raises `TypeError: '<' not supported between instances of 'NoneType' and 'float'`. The exception propagates up and blocks all signal validation for that tick cycle.

**Fix:** Coerce: `session_pnl = scribe.get_session_pnl() or 0.0`.

---

## 6. Regime Accuracy Optimizations

### A-1 — Add feature standardization (StandardScaler) to HMM training
See ML-4 above. This is the single highest-leverage change for classification accuracy. The current mixed-unit feature space causes the Gaussian emissions to be poorly conditioned on low-volatility days.

---

### A-2 — Add posterior hysteresis / dwell-time smoothing before regime changes propagate
**File:** `python/regime.py` ~lines 608–613 (publish path)
**Severity:** Recommendation

The HMM can flip state on a single-bar anomaly (news spike, spread widen). Adding a dwell-time requirement (e.g., "must observe new state for ≥3 consecutive bars before publishing a regime change") would reduce false regime flips that prematurely toggle AEGIS gates. Implement as:
```python
if new_state != self._current_state:
    self._dwell_counter += 1
    if self._dwell_counter >= DWELL_MIN_BARS:
        self._current_state = new_state
        self._dwell_counter = 0
else:
    self._dwell_counter = 0
```

---

### A-3 — Use posterior probability as a confidence filter, not just argmax state
**File:** `python/bridge.py` (regime state export), `python/aegis.py` (gate logic)
**Severity:** Recommendation

HMM `predict_proba()` gives posterior probabilities per state. When max posterior < 0.65 (uncertain), the regime label is unreliable. Export `regime_confidence` alongside `regime` in `regime_state.json` and add a gate in AEGIS: if confidence < threshold, treat as UNKNOWN and apply conservative defaults. This is already partially implemented (LENS staleness fix) but the low-confidence case is not covered.

---

### A-4 — Retrain on symbol-specific history windows, not a shared deque
**File:** `python/regime.py` ~lines 242–282
**Severity:** Recommendation

The current deque appears to aggregate bars across symbols (or uses a single symbol's history). XAUUSD and EURUSD have structurally different volatility distributions. A per-symbol `RegimeEngine` instance with its own deque, scaler, and HMM model would produce more accurate state labels than a shared model. The bridge already dispatches per-symbol tick files — instantiating one engine per symbol is straightforward.

---

### A-5 — Periodically retrain on the last 90 days of live data, not just the current session
**File:** `python/regime.py` (training trigger logic)
**Severity:** Recommendation

Training is triggered by the bridge hitting a bar-count threshold within a single session. The model never sees multi-week regime cycles (e.g., a sustained trending quarter followed by a ranging quarter). Adding a weekly retrain from the `market_regimes.feature_json` historical rows would give the HMM a broader distribution to fit, improving state separation.

---

## 7. Prioritized Recommendations

| Priority | ID | File(s) | Action |
|---|---|---|---|
| 1 | RC-1 | `regime.py` | Fix `_training_in_progress` guard inside `_train_lock` — prevents double-training |
| 2 | B-1 | `bridge.py` | Write `"regime": "UNKNOWN"` sentinel on inference failure — prevents stale gate leak |
| 3 | B-2 | `FORGE.mq5` | Reset gate booleans to safe defaults at top of `ReadRegimeConfig()` |
| 4 | E-1 | `bridge.py` | Standardize all JSON reads behind `_safe_json_load()`; use atomic rename on writes |
| 5 | B-4 | `athena_api.py` | Wrap form field coercions in try/except, return 400 before any DB write |
| 6 | E-5 | `aegis.py` | Coerce `None` P&L to `0.0` before comparison |
| 7 | RC-2 | `regime.py` | Acquire `_train_lock` inside `reset()` before nulling model state |
| 8 | P-2 | `aegis.py` | Compute session P&L once per validation, pass as parameter |
| 9 | A-1 / ML-4 | `regime.py` | Add `StandardScaler` to feature pipeline, persist alongside HMM pickle |
| 10 | A-2 | `regime.py` | Add 3-bar dwell-time smoothing before publishing regime changes |
| 11 | ML-1 | `scribe.py`, `regime.py` | Build supervised outcome classifier from `market_regimes` + `trade_groups` join |
| 12 | ML-2 | `scribe.py`, `FORGE.mq5` | Calibrate gate thresholds from FORGE journal feature columns |
| 13 | P-1 | `bridge.py` | Batch symbol tick reads; move `upsert_regime()` to async write queue |
| 14 | A-3 | `bridge.py`, `aegis.py` | Export `regime_confidence` and gate on low-confidence regimes |
| 15 | ML-5 | `scribe.py`, `athena_api.py` | Add `regime_performance` summary table + `/api/regime/performance` endpoint |

---

*Generated by Codex (GPT-5.4) read-only analysis pass on 2026-05-10. No source files were modified.*
