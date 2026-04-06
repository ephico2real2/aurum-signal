"""POST /api/management — writes management_cmd.json for BRIDGE."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "python"))


def test_management_rejects_bad_intent(tmp_path, monkeypatch):
    import athena_api  # noqa: WPS433

    monkeypatch.setattr(athena_api, "MGMT_FILE", str(tmp_path / "mgmt.json"))
    client = athena_api.app.test_client()
    r = client.post("/api/management", json={"intent": "NOPE"})
    assert r.status_code == 400


def test_management_close_all_writes_json(tmp_path, monkeypatch):
    import athena_api  # noqa: WPS433

    path = tmp_path / "mgmt.json"
    monkeypatch.setattr(athena_api, "MGMT_FILE", str(path))
    client = athena_api.app.test_client()
    r = client.post("/api/management", json={"intent": "CLOSE_ALL"})
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("ok") is True
    data = json.loads(path.read_text())
    assert data["type"] == "MANAGEMENT"
    assert data["intent"] == "CLOSE_ALL"
    assert data["timestamp"]


def test_management_close_pct(tmp_path, monkeypatch):
    import athena_api  # noqa: WPS433

    path = tmp_path / "mgmt.json"
    monkeypatch.setattr(athena_api, "MGMT_FILE", str(path))
    client = athena_api.app.test_client()
    r = client.post("/api/management", json={"intent": "CLOSE_PCT", "pct": 70})
    assert r.status_code == 200
    data = json.loads(path.read_text())
    assert data["intent"] == "CLOSE_PCT"
    assert data["pct"] == 70
