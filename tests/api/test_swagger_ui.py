"""
test_swagger_ui.py — OpenAPI spec + embedded Swagger UI (no slow external calls).
"""
from __future__ import annotations

import pytest

from athena_api import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.mark.unit
def test_openapi_yaml_served(client):
    r = client.get("/api/openapi.yaml")
    assert r.status_code == 200
    assert b"openapi:" in r.data
    assert b"/api/live:" in r.data
    assert b"getMode" in r.data
    assert b"getComponentHeartbeatHelp" in r.data
    assert b"postScribeQuery" in r.data
    assert b"/api/aurum/exec" in r.data
    assert b"postAurumExec" in r.data
    assert b"/api/regime/current" in r.data
    assert b"getRegimePerformance" in r.data
    assert b"/api/autoscalper/conditions" in r.data
    assert b"getAutoScalperConditions" in r.data


@pytest.mark.unit
def test_health_includes_scribe_query_caps(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    d = r.get_json()
    sq = d.get("scribe_query")
    assert isinstance(sq, dict)
    assert "max_rows" in sq and "busy_timeout_ms" in sq and "auth_required" in sq
    assert sq["auth_required"] in (True, False)


@pytest.mark.unit
def test_get_mode_and_heartbeat_help(client):
    r = client.get("/api/mode")
    assert r.status_code == 200
    d = r.get_json()
    assert "mode" in d and "effective_mode" in d and "hint" in d

    r2 = client.get("/api/components/heartbeat")
    assert r2.status_code == 200
    h = r2.get_json()
    assert h.get("message")
    assert "POST" in h["message"] or "post" in h["message"].lower()
    assert h.get("example_body")
    assert isinstance(h.get("allowed_components"), list)


@pytest.mark.unit
def test_swagger_ui_shell_served(client):
    r = client.get("/api/docs/")
    assert r.status_code == 200
    assert b"swagger" in r.data.lower() or b"SwaggerUIBundle" in r.data


@pytest.mark.unit
def test_swagger_ui_references_openapi_path(client):
    r = client.get("/api/docs/")
    assert r.status_code == 200
    assert b"/api/openapi.yaml" in r.data or b"openapi.yaml" in r.data
