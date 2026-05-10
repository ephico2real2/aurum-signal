# Regime Engine — Design Review & Gotchas

> Reviewed: 2026-05-10 against python/regime.py (565 lines), python/bridge.py, python/aegis.py

---

## 1. Files

| File | Role |
|------|------|
| `python/regime.py` | Core engine — HMM inference, Gaussian fallback, feature extraction |
| `python/bridge.py` | Calls `regime_engine.infer()` every tick, writes to config.json + status.json |
| `python/aegis.py` | Consumes regime context for countertrend gate + entry ladder |
| `python/athena_api.py` | Exposes `/api/regime/current`, `/api/regime/history`, `/api/regime/performance` |
| `python/scribe.py` | Persists to `market_regimes` table; attaches regime to `signals_received` + `trade_groups` |
| `python/freshness.py` | `DATA_FRESHNESS_WINDOWS["REGIME"] = 180` (default, overridden by `.env`) |
| `ea/FORGE.mq5` | Reads `regime_label`, `regime_confidence`, `regime_apply_entry_policy` from config.json |

---

## 2. When It Runs

```
bridge._tick() → _refresh_regime_snapshot(mt5) → regime_engine.infer() → _write_config()
```

**Frequency:** every bridge tick = **every 1 second** (`BRIDGE_LOOP_SEC=1`).

HMM inference is fast (`predict_proba` only). The expensive `model.fit()` runs at most once per `REGIME_RETRAIN_INTERVAL_SEC` (default 3600s).

**DB write throttle:** `log_market_regime()` fires only on label transitions OR when 30s has elapsed since last emit.

**LENS data:** read from `config/lens_snapshot.json` on every tick. LENS refreshes every 5s (`BRIDGE_LENS_SEC=5`) in active modes.

---

## 3. Feature Vector (11 dimensions)

| Index | Feature | Source | Notes |
|-------|---------|--------|-------|
| 0 | `ret_1` | LENS price → MT5 mid | Single-tick return |
| 1 | `vol` | Derived | `pstdev` of last 500 returns |
| 2 | `ema_spread` | LENS ema_20/ema_50 | EMA20 − EMA50 |
| 3 | `adx` | LENS ADX → MT5 M5/H1 | Trend strength |
| 4 | `bb_width` | LENS bb_width → MT5 | Band expansion |
| 5 | `spread` | MT5 ask−bid | Execution cost |
| 6 | `sess_code` | MT5 session | OFF=0 SYDNEY=1 ASIAN=2 LON=3 LON_NY=4 NY=5 |
| 7 | `rsi_centered` | LENS RSI → 0 if MT5-only | (RSI−50)/50 |
| 8 | `macd_hist` | LENS MACD | Momentum direction |
| 9 | `tv_recommend` | LENS tv_recommend | TradingView score −1..+1 |
| 10 | `lens_price_delta` | LENS price − MT5 mid | Cross-source divergence |

Features 7–10 collapse to zero when LENS data is stale. This materially degrades directional discrimination.

---

## 4. HMM Model

- **Class:** `hmmlearn.hmm.GaussianHMM`
- **States:** `REGIME_HMM_COMPONENTS` (default 3, range 2–10)
- **Covariance:** `full` — most expressive, slowest to train
- **Training:** up to last 5000 feature vectors, min 120 samples required
- **Retrain:** every `REGIME_RETRAIN_INTERVAL_SEC` (default 3600s)
- **No persistence:** model is in-memory only — lost on bridge restart

**Output states:** `TREND_BULL`, `TREND_BEAR`, `VOLATILE`, `RANGE`, `UNKNOWN`

**State labeling** (post-training): each HMM state is classified by inspecting mean ADX, mean EMA spread, and mean return of samples assigned to it. States with ADX ≥ 25 and clear directional bias → TREND_BULL/BEAR. High volatility → VOLATILE. Otherwise → RANGE.

**Gaussian fallback** (`_gaussian_fallback`): deterministic rule-based classifier used when HMM is not ready. Uses ADX ≥ 24 or |tv_recommend| ≥ 0.60 as "trend gate", then classifies by EMA spread direction + RSI/MACD bias.

---

## 5. How Results Are Used

```
regime.infer()
  ├─ bridge writes config.json   → FORGE EA reads regime_label/confidence/apply_policy
  ├─ bridge writes status.json   → AURUM context, Athena /api/live
  ├─ scribe.log_market_regime()  → market_regimes table (on emit)
  ├─ AEGIS._regime_countertrend_reject()  → blocks SELL in TREND_BULL, BUY in TREND_BEAR
  ├─ AEGIS._resolve_signal_regime_policy() → entry price ladder distribution
  └─ FORGE.mq5 NativeScalperRegimeBlocksDirection() → same gate, MQL5 side
```

**Active gates using regime:**
1. `AEGIS._regime_countertrend_reject()` — hard block for SCALPER_SUBPATH_DIRECT source (conf ≥ 0.55)
2. `NativeScalperRegimeBlocksDirection()` in FORGE EA — same logic in MQL5
3. `AEGIS._resolve_signal_regime_policy()` — entry ladder weight distribution (always active for SIGNAL)
4. `ForgeResolveNumTrades()` in FORGE EA — VOLATILE reduces leg count by 1, RANGE increases by 1

**Tester synthetic regime** (when bridge not running): FORGE derives its own regime from H1/H4 indicators and sets `g_regime_confidence = 1.0` unconditionally — see Gotcha 5e.

---

## 6. Gotchas

### 6a. Cold-Start Fallback — Silent Degradation
For the first ~2 minutes after bridge restart (120 samples), the HMM is None and all inferences use the weaker Gaussian fallback. No Herald alert is sent. `fallback_reason="hmm_not_ready"` is set but only visible in the API. If bridge restarts during active trading, regime gates operate on degraded classification without operator notification.

### 6b. Synchronous Training Blocks the Bridge Loop
`model.fit()` is called synchronously inside `bridge._tick()`. With 5000 samples and 120 EM iterations, training can take **1–5 seconds** — blocking MT5 data reads, signal processing, and FORGE writes. No timeout protection exists.

### 6c. Feature Shape Reset Clears All Training History
If the feature vector length changes (e.g., LENS fields change mid-session), `_feature_history.clear()` and `_hmm_model = None` are called — wiping all accumulated training data and forcing another cold-start.

### 6d. LENS Staleness Check Uses 300s Floor
```python
lens_stale = bool(lens and (lens_age_sec > max(self.stale_sec, 300)))
```
With `REGIME_STALE_SEC=45`, LENS data up to 5 minutes old is accepted as fresh. MT5 data is considered stale at 45s — an asymmetry: you get stale RSI/MACD input while the engine appears to be using "live" data.

### 6e. Tester Synthetic Regime Always Confidence 1.0
In backtests, `g_regime_confidence = 1.0` is hardcoded. The countertrend gate (threshold 0.55) always passes. This overestimates the regime filter's live effectiveness where confidence typically ranges 0.60–0.72.

### 6f. Duplicate State Labels Inflate Posterior
When two HMM states both get labeled `"RANGE"`, their probabilities are summed in the displayed posterior (`merged["RANGE"] = 0.42 + 0.39 = 0.81`). This can look like high confidence when it's actually two ambiguous states. The raw pre-merge confidence drives the actual gate — so this is display-only, but the Athena UI shows the merged value.

### 6g. No Model Persistence
The HMM lives only in `RegimeEngine._hmm_model` (in-memory). Every bridge restart loses the model and forces a cold-start. Frequent deployments mean the engine spends meaningful time in fallback mode.

### 6h. Entry Ladder Policy Active in Shadow Mode
`_resolve_signal_regime_policy()` applies entry price weighting even when `apply_policy=False` (shadow/off mode). The `apply_policy` flag is returned in the dict but doesn't gate the ladder logic.

---

## 7. Recommended Enhancements

### High priority
1. **Async HMM retraining** — run `model.fit()` in a background thread; swap `_hmm_model` atomically after training. Eliminates bridge loop stall.
2. **Persist model to disk** — `joblib.dump()` after each retrain → `python/data/regime_hmm.pkl`. Load on startup. Eliminates 2-minute cold-start after routine restarts.
3. **Herald alert on cold-start in active mode** — warn when fallback is active and `REGIME_ENTRY_MODE=active`.

### Medium priority
4. **Fix LENS staleness asymmetry** — replace `max(self.stale_sec, 300)` with a separate `REGIME_LENS_STALE_SEC` env var (suggest 60–90s to match LENS refresh cadence).
5. **Tester regime confidence distribution** — instead of hardcoding 1.0, draw from uniform 0.55–0.85 or disable the gate entirely in tester with `regime_apply_entry_policy=0`.
6. **Posterior entropy as secondary signal** — compute Shannon entropy of raw posterior; high entropy = uncertain model = skip regime-based lot scaling even if argmax confidence looks acceptable.

### Low priority
7. **3-tick majority vote** for label stability — reduce spurious transitions in `market_regimes` table.
8. **Document/fix entry ladder shadow mode** — either explicitly gate ladder by `apply_policy` or document that it's intentionally always active.
9. **Warm-start training** — lower `n_iter` to 60 with `tol=0.01` stopping criterion; recency-weight training window to 1000–2000 samples.

---

## 8. Key Env Vars

| Var | Default | Live value |
|-----|---------|-----------|
| `REGIME_ENGINE_ENABLED` | `true` | `true` |
| `REGIME_ENTRY_MODE` | `shadow` | `active` |
| `REGIME_MIN_CONFIDENCE` | `0.60` | `0.60` |
| `REGIME_STALE_SEC` | `180` | `45` |
| `REGIME_HMM_COMPONENTS` | `3` | `3` |
| `REGIME_RETRAIN_INTERVAL_SEC` | `3600` | `3600` |
| `REGIME_MIN_TRAIN_SAMPLES` | `120` | `120` |
| `AEGIS_REGIME_LOT_SCALE_ENABLED` | `false` | `false` |
