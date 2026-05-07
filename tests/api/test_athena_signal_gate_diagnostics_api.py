"""ATHENA SIGNAL-path gate diagnostics endpoint."""
from __future__ import annotations

import json
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


def test_signal_gate_diagnostics_404_when_missing(client, monkeypatch, tmp_path):
    import athena_api

    monkeypatch.setattr(athena_api, "GATE_DIAGNOSTICS_LAST_FILE", str(tmp_path / "missing.json"))
    r = client.get("/api/signal_gate/diagnostics")
    assert r.status_code == 404
    body = r.get_json()
    assert body.get("status") == "UNAVAILABLE"


def test_signal_gate_diagnostics_200_when_present(client, monkeypatch, tmp_path):
    import athena_api

    gpath = tmp_path / "g.json"
    payload = {"schema": "signal_gate_diagnostics/v1", "bridge": {"mode": "SIGNAL"}}
    gpath.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(athena_api, "GATE_DIAGNOSTICS_LAST_FILE", str(gpath))
    r = client.get("/api/signal_gate/diagnostics")
    assert r.status_code == 200
    assert r.get_json() == payload
