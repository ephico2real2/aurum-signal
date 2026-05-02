from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def _sample_mt5(ts_unix: float, bid: float = 3200.0, ask: float = 3200.5) -> dict:
    return {
        "timestamp_unix": ts_unix,
        "session": "LONDON",
        "price": {"bid": bid, "ask": ask},
        "indicators_h1": {"ema_20": bid + 2.5, "ema_50": bid - 1.0, "adx": 28, "bb_width": 9.0},
        "indicators_m5": {"ema_20": bid + 1.2, "ema_50": bid - 0.8, "adx": 26, "bb_width": 6.5},
    }


def _sample_lens(price: float = 3201.0) -> dict:
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())),
        "age_seconds": 2.0,
        "price": price,
        "rsi": 64.0,
        "macd_hist": 0.85,
        "bb_width": 0.022,
        "adx": 31.0,
        "ema_20": price + 1.4,
        "ema_50": price - 1.1,
        "tv_recommend": 0.72,
    }


class _FakeHMM:
    def __init__(self, n_components, covariance_type=None, n_iter=None, random_state=None):
        self.n_components = n_components

    def fit(self, arr):
        self.arr_shape = tuple(arr.shape)

    def predict(self, arr):
        return [i % self.n_components for i in range(len(arr))]

    def predict_proba(self, arr):
        width = self.n_components
        return [[1.0 / width for _ in range(width)]]


class _FakeArray:
    def __init__(self, rows):
        self.rows = [list(row) for row in rows]
        width = len(self.rows[0]) if self.rows else 0
        self.shape = (len(self.rows), width)

    def __len__(self):
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def __getitem__(self, key):
        if isinstance(key, tuple):
            row_key, col_key = key
            if isinstance(row_key, slice):
                return [row[col_key] for row in self.rows[row_key]]
            return self.rows[row_key][col_key]
        return self.rows[key]


class _FakeNp:
    @staticmethod
    def array(rows, dtype=float):
        return _FakeArray(rows)

    @staticmethod
    def nan_to_num(arr):
        return arr

    @staticmethod
    def abs(values):
        return [abs(v) for v in values]

    @staticmethod
    def median(values):
        vals = sorted(values)
        if not vals:
            return 0.0
        mid = len(vals) // 2
        if len(vals) % 2:
            return vals[mid]
        return (vals[mid - 1] + vals[mid]) / 2.0

    @staticmethod
    def argmax(values):
        return max(range(len(values)), key=lambda i: values[i])

    @staticmethod
    def max(values):
        return max(values)


@pytest.mark.unit
def test_regime_engine_snapshot_has_expected_keys(monkeypatch):
    monkeypatch.setenv("REGIME_ENGINE_ENABLED", "true")
    monkeypatch.setenv("REGIME_ENTRY_MODE", "active")
    monkeypatch.setenv("REGIME_MIN_CONFIDENCE", "0.0")
    from regime import RegimeEngine

    eng = RegimeEngine()
    now = time.time()
    eng.infer(_sample_mt5(now - 1, bid=3200.0, ask=3200.6), session="LONDON", mode="SIGNAL")
    snap = eng.infer(_sample_mt5(now, bid=3201.5, ask=3202.1), session="LONDON", mode="SIGNAL")

    assert snap["label"] in ("TREND_BULL", "TREND_BEAR", "RANGE", "VOLATILE")
    assert "confidence" in snap
    assert "model_name" in snap
    assert "apply_entry_policy" in snap
    assert isinstance(snap.get("features"), dict)


@pytest.mark.unit
def test_regime_engine_includes_lens_chart_features(monkeypatch):
    monkeypatch.setenv("REGIME_ENGINE_ENABLED", "true")
    monkeypatch.setenv("REGIME_ENTRY_MODE", "active")
    monkeypatch.setenv("REGIME_MIN_CONFIDENCE", "0.0")
    from regime import RegimeEngine

    eng = RegimeEngine()
    now = time.time()
    lens = _sample_lens(price=3201.0)
    eng.infer(_sample_mt5(now - 1, bid=3200.0, ask=3200.6), session="LONDON", mode="SIGNAL", lens=lens)
    snap = eng.infer(_sample_mt5(now, bid=3201.2, ask=3201.8), session="LONDON", mode="SIGNAL", lens=lens)
    feat = snap.get("features") or {}

    assert feat.get("source") == "LENS"
    assert feat.get("lens_used") is True
    assert feat.get("rsi") == pytest.approx(64.0)
    assert feat.get("tv_recommend") == pytest.approx(0.72)
    assert feat.get("macd_hist") == pytest.approx(0.85)
    assert feat.get("bb_width") == pytest.approx(0.022)


@pytest.mark.unit
def test_regime_engine_staleness_blocks_active_policy(monkeypatch):
    monkeypatch.setenv("REGIME_ENGINE_ENABLED", "true")
    monkeypatch.setenv("REGIME_ENTRY_MODE", "active")
    monkeypatch.setenv("REGIME_MIN_CONFIDENCE", "0.0")
    monkeypatch.setenv("REGIME_STALE_SEC", "2")
    from regime import RegimeEngine

    eng = RegimeEngine()
    snap = eng.infer(_sample_mt5(time.time() - 20), session="LONDON", mode="SIGNAL")
    assert snap["stale"] is True
    assert snap["apply_entry_policy"] is False
    assert "stale" in (snap.get("entry_gate_reason") or "")


@pytest.mark.unit
def test_regime_engine_shadow_mode_never_applies(monkeypatch):
    monkeypatch.setenv("REGIME_ENGINE_ENABLED", "true")
    monkeypatch.setenv("REGIME_ENTRY_MODE", "shadow")
    monkeypatch.setenv("REGIME_MIN_CONFIDENCE", "0.0")
    from regime import RegimeEngine

    eng = RegimeEngine()
    now = time.time()
    eng.infer(_sample_mt5(now - 1), session="LONDON", mode="SIGNAL")
    snap = eng.infer(_sample_mt5(now), session="LONDON", mode="SIGNAL")
    assert snap["entry_mode"] == "shadow"
    assert snap["apply_entry_policy"] is False
    assert snap.get("entry_gate_reason") == "entry_mode_shadow"


@pytest.mark.unit
def test_regime_engine_flags_hmm_feature_shape_mismatch(monkeypatch, caplog):
    import regime as regime_mod
    from regime import RegimeEngine

    monkeypatch.setattr(regime_mod, "HMM_AVAILABLE", True)
    monkeypatch.setattr(regime_mod, "GaussianHMM", _FakeHMM)
    monkeypatch.setattr(regime_mod, "np", _FakeNp)
    monkeypatch.setenv("REGIME_MIN_TRAIN_SAMPLES", "10")
    monkeypatch.setenv("REGIME_RETRAIN_INTERVAL_SEC", "30")

    eng = RegimeEngine()
    eng.min_train_samples = 2
    now = time.time()
    eng.infer(_sample_mt5(now - 2), session="LONDON", mode="SIGNAL")
    trained = eng.infer(_sample_mt5(now - 1), session="LONDON", mode="SIGNAL")
    assert trained["hmm_ready"] is True

    def _wide_features(mt5, lens, session):
        feat, vector, age_sec, stale = RegimeEngine._extract_features(eng, mt5, lens, session)
        return feat, vector + [1.0], age_sec, stale

    monkeypatch.setattr(eng, "_extract_features", _wide_features)
    with caplog.at_level("WARNING", logger="regime"):
        snap = eng.infer(_sample_mt5(now), session="LONDON", mode="SIGNAL")

    assert snap["feature_shape_mismatch"] is True
    assert "feature shape mismatch" in caplog.text


@pytest.mark.unit
def test_regime_hmm_components_env_validation(monkeypatch):
    from regime import RegimeEngine

    monkeypatch.setenv("REGIME_HMM_COMPONENTS", "1")
    with pytest.raises(ValueError, match="REGIME_HMM_COMPONENTS must be between 2 and 10"):
        RegimeEngine()

    monkeypatch.setenv("REGIME_HMM_COMPONENTS", "5")
    eng = RegimeEngine()
    assert eng.hmm_components == 5
