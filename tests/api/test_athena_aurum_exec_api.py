"""POST /api/aurum/exec — shared AEB execution endpoint behavior."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


@pytest.fixture
def client():
    import athena_api

    athena_api.app.config["TESTING"] = True
    with athena_api.app.test_client() as c:
        yield c


@pytest.mark.unit
def test_aurum_exec_happy_path_scribe_query(client, monkeypatch):
    import athena_api

    monkeypatch.setattr(athena_api, "AURUM_EXEC_SECRET", "")
    monkeypatch.setattr(athena_api, "get_scribe", lambda: type("S", (), {"db_path": "/tmp/test.db"})())
    monkeypatch.setattr(
        athena_api,
        "execute_action",
        lambda payload, db_path, project_root: {
            "ok": True,
            "action": "SCRIBE_QUERY",
            "summary": "Scribe query returned 1 row(s)",
            "rows": [{"ok": 1}],
            "count": 1,
            "truncated": False,
            "duration_ms": 3,
        },
    )

    r = client.post("/api/aurum/exec", json={"action": "SCRIBE_QUERY", "sql": "SELECT 1 AS ok"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["action"] == "SCRIBE_QUERY"


@pytest.mark.unit
def test_aurum_exec_happy_path_shell_exec_wrapped_payload(client, monkeypatch):
    import athena_api

    monkeypatch.setattr(athena_api, "AURUM_EXEC_SECRET", "")
    monkeypatch.setattr(athena_api, "get_scribe", lambda: type("S", (), {"db_path": "/tmp/test.db"})())
    monkeypatch.setattr(
        athena_api,
        "execute_action",
        lambda payload, db_path, project_root: {
            "ok": True,
            "action": "SHELL_EXEC",
            "summary": "SHELL_EXEC exited with code 0",
            "stdout": "ok",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 10,
        },
    )

    r = client.post(
        "/api/aurum/exec",
        json={
            "payload": {
                "action": "SHELL_EXEC",
                "program": "python3",
                "args": ["scripts/analyse_performance.py", "--days", "7"],
            }
        },
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["action"] == "SHELL_EXEC"


@pytest.mark.unit
def test_aurum_exec_auth_required(client, monkeypatch):
    import athena_api

    monkeypatch.setattr(athena_api, "AURUM_EXEC_SECRET", "top-secret")
    monkeypatch.setattr(athena_api, "get_scribe", lambda: type("S", (), {"db_path": "/tmp/test.db"})())
    monkeypatch.setattr(
        athena_api,
        "execute_action",
        lambda payload, db_path, project_root: {"ok": True, "action": "SCRIBE_QUERY", "summary": "ok"},
    )

    unauthorized = client.post("/api/aurum/exec", json={"action": "SCRIBE_QUERY", "sql": "SELECT 1"})
    assert unauthorized.status_code == 401

    authorized = client.post(
        "/api/aurum/exec",
        json={"action": "SCRIBE_QUERY", "sql": "SELECT 1"},
        headers={"Authorization": "Bearer top-secret"},
    )
    assert authorized.status_code == 200


@pytest.mark.unit
def test_aurum_exec_blocked_payload_returns_400_with_consistent_shape(client, monkeypatch):
    import athena_api

    monkeypatch.setattr(athena_api, "AURUM_EXEC_SECRET", "")
    monkeypatch.setattr(athena_api, "get_scribe", lambda: type("S", (), {"db_path": "/tmp/test.db"})())
    monkeypatch.setattr(
        athena_api,
        "execute_action",
        lambda payload, db_path, project_root: {
            "ok": False,
            "action": "SHELL_EXEC",
            "summary": "SHELL_EXEC blocked",
            "error": "program not allowlisted",
            "security_blocked": True,
            "duration_ms": 1,
        },
    )

    r = client.post("/api/aurum/exec", json={"action": "SHELL_EXEC", "program": "bash"})
    assert r.status_code == 400
    body = r.get_json()
    assert body["ok"] is False
    assert body["security_blocked"] is True
    assert "summary" in body and "error" in body


@pytest.mark.unit
def test_aurum_exec_non_blocked_failure_returns_500(client, monkeypatch):
    import athena_api

    monkeypatch.setattr(athena_api, "AURUM_EXEC_SECRET", "")
    monkeypatch.setattr(athena_api, "get_scribe", lambda: type("S", (), {"db_path": "/tmp/test.db"})())
    monkeypatch.setattr(
        athena_api,
        "execute_action",
        lambda payload, db_path, project_root: {
            "ok": False,
            "action": "SCRIBE_QUERY",
            "summary": "SCRIBE_QUERY failed",
            "error": "database unavailable",
            "security_blocked": False,
        },
    )

    r = client.post("/api/aurum/exec", json={"action": "SCRIBE_QUERY", "sql": "SELECT 1"})
    assert r.status_code == 500
