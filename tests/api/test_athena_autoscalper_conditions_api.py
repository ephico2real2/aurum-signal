"""ATHENA AUTO_SCALPER condition diagnostics endpoint."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from athena_api import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_autoscalper_conditions_endpoint_shape_and_args(client, monkeypatch):
    import athena_api

    captured = {}

    def _fake_build(**kwargs):
        captured.update(kwargs)
        return {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "bridge_prefilters": {"prefilter_pass": True},
            "setup_snapshot": {"near_upper_bb": True},
            "latest_autoscalper_responses": [],
            "overall": {
                "g47_g48_sell_pattern_match": True,
                "summary": "ok",
                "failed_checks": [],
            },
        }

    class _StubScribe:
        db_path = "/tmp/fake.db"

    monkeypatch.setattr(athena_api, "build_autoscalper_condition_report", _fake_build)
    monkeypatch.setattr(athena_api, "get_scribe", lambda: _StubScribe())

    r = client.get("/api/autoscalper/conditions?responses=5&h1_flat_threshold=0.8&upper_bb_threshold_pct=88")
    assert r.status_code == 200
    d = r.get_json()
    assert isinstance(d, dict)
    assert "bridge_prefilters" in d
    assert "setup_snapshot" in d
    assert "overall" in d
    assert d["overall"]["g47_g48_sell_pattern_match"] is True

    assert captured["responses_limit"] == 5
    assert captured["h1_flat_threshold"] == 0.8
    assert captured["upper_bb_threshold_pct"] == 88.0
