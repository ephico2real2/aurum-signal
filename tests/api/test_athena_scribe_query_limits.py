"""POST /api/scribe/query — optional secret, response shape (mocked SCRIBE)."""
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
def test_scribe_query_401_when_secret_and_no_header(client, monkeypatch):
    import athena_api

    monkeypatch.setattr(athena_api, "SCRIBE_QUERY_SECRET", "test-secret")
    r = client.post("/api/scribe/query", json={"sql": "SELECT 1"})
    assert r.status_code == 401
    assert r.get_json().get("error") == "unauthorized"


@pytest.mark.unit
def test_scribe_query_ok_with_bearer(client, monkeypatch):
    import athena_api

    monkeypatch.setattr(athena_api, "SCRIBE_QUERY_SECRET", "test-secret")

    class _S:
        def query_limited(self, sql, params=(), max_rows=500, busy_timeout_ms=5000):
            assert "SELECT" in sql.upper()
            return ([{"ok": 1}], False)

    monkeypatch.setattr(athena_api, "get_scribe", lambda: _S())
    r = client.post(
        "/api/scribe/query",
        json={"sql": "SELECT 1"},
        headers={"Authorization": "Bearer test-secret"},
    )
    assert r.status_code == 200
    d = r.get_json()
    assert d["count"] == 1
    assert d["truncated"] is False
    assert d["max_rows"] == athena_api.SCRIBE_QUERY_MAX_ROWS


@pytest.mark.unit
def test_scribe_query_ok_with_x_header(client, monkeypatch):
    import athena_api

    monkeypatch.setattr(athena_api, "SCRIBE_QUERY_SECRET", "tok")
    class _S:
        def query_limited(self, *a, **k):
            return [], False

    monkeypatch.setattr(athena_api, "get_scribe", lambda: _S())
    r = client.post(
        "/api/scribe/query",
        json={"sql": "SELECT 1"},
        headers={"X-ATHENA-SCRIBE-TOKEN": "tok"},
    )
    assert r.status_code == 200


@pytest.mark.unit
def test_scribe_query_truncated_flag_in_payload(client, monkeypatch):
    import athena_api

    monkeypatch.setattr(athena_api, "SCRIBE_QUERY_SECRET", "")

    class _S:
        def query_limited(self, sql, params=(), max_rows=500, busy_timeout_ms=5000):
            return ([{"n": i} for i in range(2)], True)

    monkeypatch.setattr(athena_api, "get_scribe", lambda: _S())
    r = client.post("/api/scribe/query", json={"sql": "SELECT 1"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["truncated"] is True
    assert d["count"] == 2


@pytest.mark.unit
def test_scribe_query_rejects_unknown_table(tmp_path):
    import scribe

    s = scribe.Scribe(str(tmp_path / "scribe.db"))
    with pytest.raises(ValueError, match="not in allowlist"):
        s.export_csv("not_a_real_table", path=str(tmp_path / "out.csv"))


@pytest.mark.unit
def test_scribe_query_allows_known_tables(tmp_path):
    import scribe

    s = scribe.Scribe(str(tmp_path / "scribe.db"))
    for table in scribe.ALLOWED_SCRIBE_TABLES:
        s.export_csv(table, path=str(tmp_path / f"{table}.csv"))
