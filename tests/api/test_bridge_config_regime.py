"""BRIDGE config.json includes regime_* for FORGE Phase C (native scalper gate)."""

import pytest


@pytest.fixture
def bridge_mod():
    import bridge

    return bridge


def test_write_config_includes_regime_fields_for_forge(monkeypatch, tmp_path, bridge_mod):
    b = bridge_mod
    captured = []

    def fake_write_json(path, body):
        captured.append((path, body))

    monkeypatch.setattr(b, "_write_json", fake_write_json)
    monkeypatch.setattr(b, "_forge_config_targets", lambda: [str(tmp_path / "config.json")])
    monkeypatch.setenv("AEGIS_REGIME_COUNTERTREND_MIN_CONFIDENCE", "0.61")

    obj = object.__new__(b.Bridge)
    obj._mode = "SCALPER"
    obj._sentinel_override = False
    obj._pending_entry_threshold_points = 50.0
    obj._trend_strength_atr_threshold = 0.2
    obj._breakout_buffer_points = 10.0
    obj._regime_snapshot = {
        "label": "TREND_BULL",
        "confidence": 0.72,
        "apply_entry_policy": True,
    }

    def eff(self):
        return self._mode

    monkeypatch.setattr(b.Bridge, "_effective_mode", eff)

    b.Bridge._write_config(obj)  # type: ignore[arg-type]

    assert len(captured) == 1
    _, body = captured[0]
    assert body["regime_label"] == "TREND_BULL"
    assert body["regime_confidence"] == 0.72
    assert body["regime_apply_entry_policy"] == 1
    assert body["regime_countertrend_min_confidence"] == pytest.approx(0.61)

    monkeypatch.delenv("AEGIS_REGIME_COUNTERTREND_MIN_CONFIDENCE", raising=False)
