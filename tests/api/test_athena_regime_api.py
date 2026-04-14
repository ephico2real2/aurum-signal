"""ATHENA regime endpoints: /api/regime/current|history|performance."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from athena_api import app


class _StubScribe:
    def get_latest_regime(self):
        return {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "label": "RANGE",
            "confidence": 0.64,
            "model_name": "GAUSSIAN_FALLBACK",
            "entry_mode": "shadow",
            "stale": False,
        }

    def get_regime_transitions(self, hours: int = 24, limit: int = 6):
        return [
            {
                "timestamp": "2026-01-01T00:05:00+00:00",
                "from": "RANGE",
                "to": "TREND_BULL",
                "confidence": 0.72,
                "model_name": "HMM_GAUSSIAN",
                "stale": False,
            }
        ][:limit]

    def get_regime_performance(self, days: int = 30):
        return {
            "days": days,
            "by_regime": [{"regime_label": "RANGE", "total": 3, "total_pnl": 21.5}],
            "snapshot_count": 10,
            "fallback_count": 4,
            "fallback_rate": 40.0,
        }

    def get_regime_history(self, limit: int = 50, hours: int = 24):
        return [
            {"timestamp": "2026-01-01T00:00:00+00:00", "label": "RANGE", "confidence": 0.6},
            {"timestamp": "2026-01-01T00:05:00+00:00", "label": "TREND_BULL", "confidence": 0.7},
        ][:limit]


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.mark.unit
def test_regime_current_shape(client, monkeypatch):
    import athena_api

    monkeypatch.setattr(athena_api, "get_scribe", lambda: _StubScribe())
    r = client.get("/api/regime/current")
    assert r.status_code == 200
    d = r.get_json()
    assert "config" in d and "current" in d
    assert isinstance(d["transitions_24h"], list)
    assert isinstance(d["performance_30d"], dict)


@pytest.mark.unit
def test_regime_history_shape(client, monkeypatch):
    import athena_api

    monkeypatch.setattr(athena_api, "get_scribe", lambda: _StubScribe())
    r = client.get("/api/regime/history?limit=2&hours=12")
    assert r.status_code == 200
    d = r.get_json()
    assert d["limit"] == 2
    assert d["hours"] == 12
    assert isinstance(d["history"], list)


@pytest.mark.unit
def test_regime_performance_shape(client, monkeypatch):
    import athena_api

    monkeypatch.setattr(athena_api, "get_scribe", lambda: _StubScribe())
    r = client.get("/api/regime/performance?days=14")
    assert r.status_code == 200
    d = r.get_json()
    assert d["days"] == 14
    assert isinstance(d["by_regime"], list)
    assert "fallback_rate" in d
