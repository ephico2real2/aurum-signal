"""
regime.py — Regime inference engine (HMM primary + Gaussian fallback)
=====================================================================
Provides a lightweight market regime snapshot for BRIDGE/AEGIS/API/UI:
- HMM-primary inference when hmmlearn + numpy are available.
- Deterministic Gaussian-style fallback when HMM is unavailable or not ready.
- Confidence + staleness gating for rollout modes (off|shadow|active).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import statistics
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

log = logging.getLogger("regime")

try:
    import numpy as np  # type: ignore
    from hmmlearn.hmm import GaussianHMM  # type: ignore
    HMM_AVAILABLE = True
except Exception:
    np = None
    GaussianHMM = None
    HMM_AVAILABLE = False


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_unix() -> float:
    return time.time()


def _norm_mode(raw: str) -> str:
    v = (raw or "off").strip().lower()
    return v if v in ("off", "shadow", "active") else "off"


@dataclass
class RegimeSnapshot:
    timestamp: str
    timestamp_unix: float
    label: str
    confidence: float
    posterior: dict
    model_name: str
    model_version: str
    stale: bool
    age_sec: float | None
    fallback_reason: str | None
    entry_mode: str
    enabled: bool
    apply_entry_policy: bool
    entry_gate_reason: str | None
    feature_hash: str
    features: dict
    transition: bool
    emit_snapshot: bool
    train_samples: int
    hmm_ready: bool

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "timestamp_unix": self.timestamp_unix,
            "label": self.label,
            "confidence": round(float(self.confidence), 4),
            "posterior": self.posterior,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "stale": bool(self.stale),
            "age_sec": None if self.age_sec is None else round(float(self.age_sec), 1),
            "fallback_reason": self.fallback_reason,
            "entry_mode": self.entry_mode,
            "enabled": bool(self.enabled),
            "apply_entry_policy": bool(self.apply_entry_policy),
            "entry_gate_reason": self.entry_gate_reason,
            "feature_hash": self.feature_hash,
            "features": self.features,
            "transition": bool(self.transition),
            "emit_snapshot": bool(self.emit_snapshot),
            "train_samples": int(self.train_samples),
            "hmm_ready": bool(self.hmm_ready),
        }


class RegimeEngine:
    _SESSION_CODE = {
        "OFF_HOURS": 0.0,
        "SYDNEY": 1.0,
        "ASIAN": 2.0,
        "LONDON": 3.0,
        "LONDON_NY": 4.0,
        "NEW_YORK": 5.0,
    }

    def __init__(self):
        self.enabled = _env_bool("REGIME_ENGINE_ENABLED", True)
        self.entry_mode = _norm_mode(os.environ.get("REGIME_ENTRY_MODE", "off"))
        self.min_confidence = max(0.0, min(1.0, _safe_float(os.environ.get("REGIME_MIN_CONFIDENCE"), 0.60)))
        self.stale_sec = max(5, int(_safe_float(os.environ.get("REGIME_STALE_SEC"), 180)))
        self.retrain_interval_sec = max(30, int(_safe_float(os.environ.get("REGIME_RETRAIN_INTERVAL_SEC"), 3600)))
        self.min_train_samples = max(10, int(_safe_float(os.environ.get("REGIME_MIN_TRAIN_SAMPLES"), 120)))
        self.log_interval_sec = max(5, int(_safe_float(os.environ.get("REGIME_LOG_INTERVAL_SEC"), 30)))

        self._feature_history: deque[list[float]] = deque(maxlen=5000)
        self._returns: deque[float] = deque(maxlen=500)
        self._prev_mid: float | None = None
        self._hmm_model = None
        self._hmm_state_labels: dict[int, str] = {}
        self._hmm_last_trained = 0.0
        self._model_version = "regime-v1"
        self._last_snapshot: dict = {}
        self._last_emit_ts = 0.0
        self._last_label = "UNKNOWN"

        log.info(
            "REGIME engine init — enabled=%s mode=%s min_conf=%.2f stale=%ss train_min=%s hmm=%s",
            self.enabled, self.entry_mode, self.min_confidence, self.stale_sec, self.min_train_samples, HMM_AVAILABLE,
        )

    # ── Feature extraction ──────────────────────────────────────
    def _extract_features(self, mt5: dict, lens: dict | None, session: str | None) -> tuple[dict, list[float], float | None, bool]:
        mt5 = mt5 or {}
        lens = lens or {}
        px = mt5.get("price") or {}
        bid = _safe_float(px.get("bid"), default=0.0)
        ask = _safe_float(px.get("ask"), default=0.0)
        mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else None
        spread = (ask - bid) if (bid > 0 and ask > 0) else 0.0

        ind_h1 = mt5.get("indicators_h1") or {}
        ind_m15 = mt5.get("indicators_m15") or {}
        ind_m5 = mt5.get("indicators_m5") or {}

        ema20 = (
            _safe_float(ind_m5.get("ema_20"), default=0.0)
            or _safe_float(ind_m15.get("ema_20"), default=0.0)
            or _safe_float(ind_h1.get("ema_20"), default=0.0)
        )
        ema50 = (
            _safe_float(ind_m5.get("ema_50"), default=0.0)
            or _safe_float(ind_m15.get("ema_50"), default=0.0)
            or _safe_float(ind_h1.get("ema_50"), default=0.0)
        )
        ema_spread_mt5 = ema20 - ema50
        adx_mt5 = (
            _safe_float(ind_m5.get("adx"), default=0.0)
            or _safe_float(ind_m15.get("adx"), default=0.0)
            or _safe_float(ind_h1.get("adx"), default=0.0)
        )
        bb_width_mt5 = (
            _safe_float(ind_m5.get("bb_width"), default=0.0)
            or _safe_float(ind_m15.get("bb_width"), default=0.0)
            or _safe_float(ind_h1.get("bb_width"), default=0.0)
        )

        lens_price = _safe_float(lens.get("price", lens.get("close")), default=0.0)
        lens_ema20 = _safe_float(lens.get("ema_20", lens.get("EMA20")), default=0.0)
        lens_ema50 = _safe_float(lens.get("ema_50", lens.get("EMA50")), default=0.0)
        lens_adx = _safe_float(lens.get("adx", lens.get("ADX")), default=0.0)
        lens_bb_width = _safe_float(lens.get("bb_width"), default=0.0)
        lens_rsi = _safe_float(lens.get("rsi", lens.get("RSI")), default=0.0)
        lens_macd = _safe_float(lens.get("macd_hist", lens.get("MACD.hist")), default=0.0)
        lens_tv_recommend = _safe_float(lens.get("tv_recommend"), default=0.0)
        lens_age_sec = -1.0
        ts_raw = lens.get("timestamp")
        if ts_raw:
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                lens_age_sec = max(0.0, _now_unix() - ts.timestamp())
            except Exception:
                lens_age_sec = -1.0
        if lens_age_sec < 0:
            lens_age_sec = _safe_float(lens.get("age_seconds"), default=-1.0)
        lens_stale = bool(lens and (lens_age_sec < 0 or lens_age_sec > max(self.stale_sec, 300)))
        use_lens = bool(lens and not lens_stale)

        ema_spread_lens = (lens_ema20 - lens_ema50) if (lens_ema20 and lens_ema50) else 0.0
        ema_spread = ema_spread_lens if (use_lens and lens_ema20 and lens_ema50) else ema_spread_mt5
        adx = lens_adx if (use_lens and lens_adx > 0) else adx_mt5
        bb_width = lens_bb_width if (use_lens and lens_bb_width > 0) else bb_width_mt5
        price_basis = lens_price if (use_lens and lens_price > 0) else mid
        rsi = lens_rsi if (use_lens and lens_rsi > 0) else 0.0
        macd_hist = lens_macd if use_lens else 0.0
        tv_recommend = lens_tv_recommend if use_lens else 0.0
        lens_price_delta = (lens_price - mid) if (use_lens and lens_price > 0 and mid is not None) else 0.0
        rsi_centered = ((rsi - 50.0) / 50.0) if rsi > 0 else 0.0

        ret_1 = 0.0
        if price_basis is not None and self._prev_mid is not None:
            ret_1 = float(price_basis - self._prev_mid)
        if price_basis is not None:
            self._prev_mid = float(price_basis)
            self._returns.append(ret_1)

        if len(self._returns) > 1:
            vol = float(statistics.pstdev(self._returns))
        else:
            vol = abs(ret_1)

        sess = (session or mt5.get("session") or "OFF_HOURS").upper()
        sess_code = self._SESSION_CODE.get(sess, 0.0)

        vector = [
            float(ret_1),
            float(vol),
            float(ema_spread),
            float(adx),
            float(bb_width),
            float(spread),
            float(sess_code),
            float(rsi_centered),
            float(macd_hist),
            float(tv_recommend),
            float(lens_price_delta),
        ]
        if price_basis is not None:
            if self._feature_history and len(self._feature_history[-1]) != len(vector):
                old_len = len(self._feature_history[-1])
                self._feature_history.clear()
                self._hmm_model = None
                self._hmm_state_labels = {}
                log.info(
                    "REGIME feature vector shape changed %s→%s — reset HMM history",
                    old_len,
                    len(vector),
                )
            self._feature_history.append(vector)

        tsu_raw = mt5.get("timestamp_unix")
        tsu = _safe_float(tsu_raw, default=0.0)
        age_sec = (_now_unix() - tsu) if tsu > 0 else None
        stale = bool(age_sec is None or age_sec > self.stale_sec)

        feat = {
            "mid": mid,
            "ret_1": ret_1,
            "volatility": vol,
            "ema_spread": ema_spread,
            "adx": adx,
            "bb_width": bb_width,
            "spread": spread,
            "session": sess,
            "session_code": sess_code,
            "source": "LENS" if use_lens else "MT5",
            "lens_used": use_lens,
            "lens_stale": lens_stale if lens else None,
            "lens_age_sec": lens_age_sec if lens_age_sec >= 0 else None,
            "rsi": rsi,
            "macd_hist": macd_hist,
            "tv_recommend": tv_recommend,
            "lens_price_delta": lens_price_delta,
        }
        return feat, vector, age_sec, stale

    # ── HMM helpers ──────────────────────────────────────────────
    def _build_hmm_state_labels(self, arr, states) -> dict[int, str]:
        labels: dict[int, str] = {}
        if arr is None or len(arr) == 0:
            return labels
        vol_med = float(np.median(np.abs(arr[:, 1]))) if np is not None else 0.0
        n_states = int(max(states) + 1) if len(states) else 0
        for s in range(n_states):
            idx = [i for i, st in enumerate(states) if int(st) == s]
            if not idx:
                labels[s] = "RANGE"
                continue
            rets = [float(arr[i, 0]) for i in idx]
            adxs = [float(arr[i, 3]) for i in idx]
            vols = [abs(float(arr[i, 1])) for i in idx]
            mean_ret = statistics.mean(rets) if rets else 0.0
            mean_adx = statistics.mean(adxs) if adxs else 0.0
            mean_vol = statistics.mean(vols) if vols else 0.0
            if mean_adx >= 22.0 and mean_ret > 0:
                labels[s] = "TREND_BULL"
            elif mean_adx >= 22.0 and mean_ret < 0:
                labels[s] = "TREND_BEAR"
            elif mean_vol > max(0.001, vol_med * 1.25):
                labels[s] = "VOLATILE"
            else:
                labels[s] = "RANGE"
        return labels

    def _maybe_train_hmm(self) -> None:
        if not (self.enabled and HMM_AVAILABLE):
            return
        if len(self._feature_history) < self.min_train_samples:
            return
        now = _now_unix()
        if self._hmm_model is not None and (now - self._hmm_last_trained) < self.retrain_interval_sec:
            return
        try:
            arr = np.array(list(self._feature_history), dtype=float)
            arr = np.nan_to_num(arr)
            n_components = 3
            model = GaussianHMM(
                n_components=n_components,
                covariance_type="full",
                n_iter=120,
                random_state=42,
            )
            model.fit(arr)
            states = model.predict(arr)
            labels = self._build_hmm_state_labels(arr, states)
            self._hmm_model = model
            self._hmm_state_labels = labels
            self._hmm_last_trained = now
            log.info(
                "REGIME HMM retrained — samples=%s states=%s labels=%s",
                len(arr), n_components, labels,
            )
        except Exception as e:
            self._hmm_model = None
            self._hmm_state_labels = {}
            log.warning("REGIME HMM train failed: %s", e)

    def _hmm_infer(self, vector: list[float]) -> tuple[str, float, dict, str | None]:
        if not HMM_AVAILABLE:
            return "UNKNOWN", 0.0, {}, "hmm_unavailable"
        if self._hmm_model is None:
            return "UNKNOWN", 0.0, {}, "hmm_not_ready"
        try:
            probs = self._hmm_model.predict_proba(np.array([vector], dtype=float))[0]
            state = int(np.argmax(probs))
            conf = float(np.max(probs))
            label = self._hmm_state_labels.get(state, "RANGE")
            posterior = {
                self._hmm_state_labels.get(int(i), f"STATE_{int(i)}"): round(float(p), 4)
                for i, p in enumerate(probs)
            }
            # Merge duplicate labels by summing probabilities.
            merged: dict[str, float] = {}
            for k, v in posterior.items():
                merged[k] = round(merged.get(k, 0.0) + float(v), 4)
            return label, conf, merged, None
        except Exception as e:
            return "UNKNOWN", 0.0, {}, f"hmm_infer_error:{e}"

    # ── Gaussian fallback ────────────────────────────────────────
    def _gaussian_fallback(self, feat: dict) -> tuple[str, float, dict]:
        ret_1 = float(feat.get("ret_1") or 0.0)
        vol = abs(float(feat.get("volatility") or 0.0))
        ema_spread = float(feat.get("ema_spread") or 0.0)
        adx = float(feat.get("adx") or 0.0)
        bb_width = abs(float(feat.get("bb_width") or 0.0))
        spread = abs(float(feat.get("spread") or 0.0))
        rsi = float(feat.get("rsi") or 0.0)
        macd_hist = float(feat.get("macd_hist") or 0.0)
        tv_recommend = float(feat.get("tv_recommend") or 0.0)

        vol_baseline = statistics.mean([abs(v) for v in self._returns]) if self._returns else max(vol, 0.01)
        trend_strength = abs(ema_spread) / max(spread, 0.1)
        directional_bias = 0.0
        if rsi >= 55.0:
            directional_bias += 0.35
        elif rsi <= 45.0:
            directional_bias -= 0.35
        if macd_hist > 0:
            directional_bias += 0.35
        elif macd_hist < 0:
            directional_bias -= 0.35
        if tv_recommend >= 0.20:
            directional_bias += 0.50
        elif tv_recommend <= -0.20:
            directional_bias -= 0.50
        tv_boost = min(0.12, abs(directional_bias) * 0.06)
        trend_gate = adx >= 24 or abs(tv_recommend) >= 0.60

        if trend_gate and ema_spread > 0 and directional_bias >= -0.15:
            label = "TREND_BULL"
            conf = min(0.95, 0.58 + min(0.33, trend_strength * 0.03 + abs(ret_1) * 0.01) + tv_boost)
            posterior = {"TREND_BULL": round(conf, 4), "RANGE": round(max(0.0, 1.0 - conf), 4)}
            return label, conf, posterior
        if trend_gate and ema_spread < 0 and directional_bias <= 0.15:
            label = "TREND_BEAR"
            conf = min(0.95, 0.58 + min(0.33, trend_strength * 0.03 + abs(ret_1) * 0.01) + tv_boost)
            posterior = {"TREND_BEAR": round(conf, 4), "RANGE": round(max(0.0, 1.0 - conf), 4)}
            return label, conf, posterior
        if vol > max(vol_baseline * 1.4, 0.7) or bb_width > max(abs(ema_spread) * 0.9, 6.0):
            conf = min(0.9, 0.52 + min(0.35, (vol / max(vol_baseline, 0.1)) * 0.08))
            posterior = {
                "VOLATILE": round(conf, 4),
                "RANGE": round(max(0.0, 1.0 - conf), 4),
            }
            return "VOLATILE", conf, posterior

        conf = 0.56
        posterior = {"RANGE": conf, "VOLATILE": 0.22, "TREND_BULL": 0.11, "TREND_BEAR": 0.11}
        return "RANGE", conf, posterior

    def _entry_gate(self, stale: bool, confidence: float, label: str) -> tuple[bool, str | None]:
        if not self.enabled:
            return False, "regime_engine_disabled"
        if self.entry_mode == "off":
            return False, "entry_mode_off"
        if self.entry_mode == "shadow":
            return False, "entry_mode_shadow"
        if stale:
            return False, "snapshot_stale"
        if label == "UNKNOWN":
            return False, "unknown_regime"
        if confidence < self.min_confidence:
            return False, f"confidence_below_min:{confidence:.2f}<{self.min_confidence:.2f}"
        return True, None

    def infer(self, mt5: dict | None, session: str | None = None, mode: str | None = None, lens: dict | None = None) -> dict:
        # Re-read toggles when BRIDGE process is restarted with updated env.
        self.enabled = _env_bool("REGIME_ENGINE_ENABLED", self.enabled)
        self.entry_mode = _norm_mode(os.environ.get("REGIME_ENTRY_MODE", self.entry_mode))
        self.min_confidence = max(0.0, min(1.0, _safe_float(os.environ.get("REGIME_MIN_CONFIDENCE"), self.min_confidence)))
        feat, vector, age_sec, stale = self._extract_features(mt5 or {}, lens or {}, session)
        if mode and (mode or "").upper() == "OFF":
            stale = True

        self._maybe_train_hmm()
        label, conf, posterior, hmm_reason = self._hmm_infer(vector)
        model_name = "HMM_GAUSSIAN"
        fallback_reason = None
        if label == "UNKNOWN":
            label, conf, posterior = self._gaussian_fallback(feat)
            model_name = "GAUSSIAN_FALLBACK"
            fallback_reason = hmm_reason or "hmm_not_ready"

        apply_entry_policy, gate_reason = self._entry_gate(stale, conf, label)

        ts = _now_iso()
        raw_feat = {
            "ret_1": round(float(feat.get("ret_1") or 0.0), 6),
            "volatility": round(float(feat.get("volatility") or 0.0), 6),
            "ema_spread": round(float(feat.get("ema_spread") or 0.0), 6),
            "adx": round(float(feat.get("adx") or 0.0), 4),
            "bb_width": round(float(feat.get("bb_width") or 0.0), 6),
            "spread": round(float(feat.get("spread") or 0.0), 6),
            "session": feat.get("session"),
            "mode": (mode or "").upper() if mode else None,
            "source": feat.get("source"),
            "lens_used": bool(feat.get("lens_used")),
            "lens_stale": feat.get("lens_stale"),
            "lens_age_sec": None if feat.get("lens_age_sec") is None else round(float(feat.get("lens_age_sec")), 1),
            "rsi": round(float(feat.get("rsi") or 0.0), 4),
            "macd_hist": round(float(feat.get("macd_hist") or 0.0), 6),
            "tv_recommend": round(float(feat.get("tv_recommend") or 0.0), 4),
            "lens_price_delta": round(float(feat.get("lens_price_delta") or 0.0), 6),
        }
        feature_hash = hashlib.sha1(
            json.dumps(raw_feat, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]

        transition = bool(self._last_label != label)
        now_u = _now_unix()
        emit_snapshot = bool(transition or (now_u - self._last_emit_ts) >= self.log_interval_sec)
        if emit_snapshot:
            self._last_emit_ts = now_u
        self._last_label = label

        snap = RegimeSnapshot(
            timestamp=ts,
            timestamp_unix=now_u,
            label=label,
            confidence=conf,
            posterior=posterior,
            model_name=model_name,
            model_version=self._model_version,
            stale=stale,
            age_sec=age_sec,
            fallback_reason=fallback_reason,
            entry_mode=self.entry_mode,
            enabled=self.enabled,
            apply_entry_policy=apply_entry_policy,
            entry_gate_reason=gate_reason,
            feature_hash=feature_hash,
            features=raw_feat,
            transition=transition,
            emit_snapshot=emit_snapshot,
            train_samples=len(self._feature_history),
            hmm_ready=bool(self._hmm_model is not None),
        ).to_dict()
        self._last_snapshot = snap
        return snap

    def current_snapshot(self) -> dict:
        return dict(self._last_snapshot or {})


_instance: RegimeEngine | None = None


def get_regime_engine() -> RegimeEngine:
    global _instance
    if _instance is None:
        _instance = RegimeEngine()
    return _instance

