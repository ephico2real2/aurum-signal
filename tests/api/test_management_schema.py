"""
test_management_schema.py — coverage for /api/management JSON schema validation.

Goals:
  • Valid intents (CLOSE_PCT, CLOSE_ALL, MOVE_BE, MODIFY_SL, MODIFY_TP,
    CLOSE_GROUP, CLOSE_GROUP_PCT, CLOSE_PROFITABLE, CLOSE_LOSING) still
    write management_cmd.json (200 + intent echoed back).
  • Malformed payloads (missing required field for intent, bad value range)
    are rejected with 400 BEFORE the file is written.
  • Backward compatibility: when the validator is disabled (e.g. schema file
    missing or jsonschema import broken), api_management falls back to the
    pre-existing unvalidated write path so existing callers cannot be broken.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


@pytest.fixture()
def athena_client(monkeypatch, tmp_path):
    """Return (flask test client, mgmt_path) with MGMT_FILE pointed at tmp_path."""
    import athena_api as bm

    mgmt_path = tmp_path / "management_cmd.json"
    monkeypatch.setattr(bm, "MGMT_FILE", str(mgmt_path), raising=True)
    return bm.app.test_client(), mgmt_path, bm


# ── Valid payloads ──────────────────────────────────────────────────


@pytest.mark.unit
def test_valid_close_pct_writes_file(athena_client):
    client, mgmt_path, _ = athena_client
    r = client.post("/api/management", json={"intent": "CLOSE_PCT", "pct": 70})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["ok"] is True
    assert body["intent"] == "CLOSE_PCT"
    assert mgmt_path.exists()
    written = json.loads(mgmt_path.read_text())
    assert written["intent"] == "CLOSE_PCT"
    assert written["pct"] == 70.0
    assert written["source"] == "ATHENA"
    assert written["type"] == "MANAGEMENT"


@pytest.mark.unit
def test_valid_close_all_writes_file(athena_client):
    client, mgmt_path, _ = athena_client
    r = client.post("/api/management", json={"intent": "CLOSE_ALL"})
    assert r.status_code == 200
    written = json.loads(mgmt_path.read_text())
    assert written["intent"] == "CLOSE_ALL"


@pytest.mark.unit
def test_valid_modify_sl_with_group(athena_client):
    client, mgmt_path, _ = athena_client
    r = client.post("/api/management", json={
        "intent": "MODIFY_SL", "sl": 4644.0, "group_id": 12,
    })
    assert r.status_code == 200
    written = json.loads(mgmt_path.read_text())
    assert written["intent"] == "MODIFY_SL"
    assert written["sl"] == 4644.0
    assert written["group_id"] == 12


@pytest.mark.unit
def test_valid_close_group_pct(athena_client):
    client, mgmt_path, _ = athena_client
    r = client.post("/api/management", json={
        "intent": "CLOSE_GROUP_PCT", "pct": 50, "group_id": 7,
    })
    assert r.status_code == 200
    written = json.loads(mgmt_path.read_text())
    assert written["intent"] == "CLOSE_GROUP_PCT"
    assert written["pct"] == 50.0
    assert written["group_id"] == 7


@pytest.mark.unit
def test_valid_close_group(athena_client):
    client, mgmt_path, _ = athena_client
    r = client.post("/api/management", json={"intent": "CLOSE_GROUP", "group_id": 5})
    assert r.status_code == 200
    written = json.loads(mgmt_path.read_text())
    assert written["intent"] == "CLOSE_GROUP"
    assert written["group_id"] == 5


# ── Invalid payloads ────────────────────────────────────────────────


@pytest.mark.unit
def test_invalid_intent_returns_400(athena_client):
    client, mgmt_path, _ = athena_client
    r = client.post("/api/management", json={"intent": "BOGUS_INTENT"})
    # Pre-existing manual gate intercepts this with its own message.
    assert r.status_code == 400
    body = r.get_json()
    assert "intent" in (body.get("error") or "")
    assert not mgmt_path.exists()


@pytest.mark.unit
def test_modify_sl_without_sl_value_rejected_by_schema(athena_client):
    """MODIFY_SL with no sl value would write {sl: null}; schema rejects it."""
    client, mgmt_path, _ = athena_client
    r = client.post("/api/management", json={"intent": "MODIFY_SL"})
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"] == "validation_failed"
    assert body["intent"] == "MODIFY_SL"
    assert isinstance(body["details"], list) and body["details"]
    # File must NOT have been written.
    assert not mgmt_path.exists()


@pytest.mark.unit
def test_modify_tp_without_tp_value_rejected_by_schema(athena_client):
    client, mgmt_path, _ = athena_client
    r = client.post("/api/management", json={"intent": "MODIFY_TP"})
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"] == "validation_failed"
    assert not mgmt_path.exists()


@pytest.mark.unit
def test_close_group_pct_without_group_id_rejected_by_schema(athena_client):
    client, mgmt_path, _ = athena_client
    # API permits the call (pct is valid) but schema requires group_id for CLOSE_GROUP_PCT.
    r = client.post("/api/management", json={"intent": "CLOSE_GROUP_PCT", "pct": 70})
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"] == "validation_failed"
    # The schema rejects because group_id is required and the assembled body
    # carries `group_id: null`. We don't pin the exact jsonschema wording —
    # just confirm the validator fired and the file was NOT written.
    assert isinstance(body["details"], list) and body["details"]
    assert not mgmt_path.exists()


@pytest.mark.unit
def test_close_group_without_group_id_rejected_by_schema(athena_client):
    client, mgmt_path, _ = athena_client
    r = client.post("/api/management", json={"intent": "CLOSE_GROUP"})
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"] == "validation_failed"
    assert not mgmt_path.exists()


@pytest.mark.unit
def test_close_pct_out_of_range_rejected_by_manual_gate(athena_client):
    """Out-of-range pct is caught by the existing manual gate (also 400) before
    schema validation; we just verify the file is not written."""
    client, mgmt_path, _ = athena_client
    r = client.post("/api/management", json={"intent": "CLOSE_PCT", "pct": 200})
    assert r.status_code == 400
    assert not mgmt_path.exists()


# ── Backward compatibility: validator unavailable ──────────────────


@pytest.mark.unit
def test_falls_back_to_unvalidated_write_when_validator_missing(monkeypatch, tmp_path):
    """If the schema file is gone (or jsonschema import broke), api_management
    must fall through to the original behaviour and write the file. Critical
    for not breaking existing callers when validation infrastructure is
    misconfigured."""
    import athena_api as bm

    mgmt_path = tmp_path / "management_cmd.json"
    monkeypatch.setattr(bm, "MGMT_FILE", str(mgmt_path), raising=True)
    # Simulate the validator being unavailable for any reason.
    monkeypatch.setattr(bm, "_MGMT_VALIDATOR", None, raising=True)
    client = bm.app.test_client()

    # Even a payload that would normally fail schema validation must be
    # written when the validator is disabled, because we deliberately
    # tolerate this configuration to avoid breaking the trade pipeline.
    r = client.post("/api/management", json={"intent": "MODIFY_SL"})  # sl=null
    assert r.status_code == 200, r.get_json()
    assert mgmt_path.exists()
    written = json.loads(mgmt_path.read_text())
    assert written["intent"] == "MODIFY_SL"
    assert written["sl"] is None  # the stale-tolerated shape


@pytest.mark.unit
def test_validator_internal_error_does_not_block_writes(monkeypatch, tmp_path):
    """If iter_errors raises (e.g. a corrupt validator state at runtime),
    api_management must STILL write the file, not 500 the operator."""
    import athena_api as bm

    mgmt_path = tmp_path / "management_cmd.json"
    monkeypatch.setattr(bm, "MGMT_FILE", str(mgmt_path), raising=True)

    class _BoomValidator:
        def iter_errors(self, _payload):
            raise RuntimeError("synthetic validator failure")

    monkeypatch.setattr(bm, "_MGMT_VALIDATOR", _BoomValidator(), raising=True)
    client = bm.app.test_client()

    r = client.post("/api/management", json={"intent": "CLOSE_ALL"})
    assert r.status_code == 200
    assert mgmt_path.exists()


# ── Schema sanity ───────────────────────────────────────────────────


@pytest.mark.unit
def test_schema_file_loads_and_validator_constructs():
    """Smoke check: the shipped schema parses and accepts a known-good body."""
    import athena_api as bm

    assert bm._MGMT_VALIDATOR is not None, (
        "schema file must load in the test environment so the rest of these "
        "tests exercise real validation rather than the fallback path"
    )
    sample = {
        "type": "MANAGEMENT",
        "intent": "CLOSE_ALL",
        "source": "ATHENA",
        "timestamp": "2026-05-02T11:00:00+00:00",
        "pct": None, "group_id": None, "sl": None, "tp": None, "tp_stage": None,
    }
    assert bm._validate_mgmt_body(sample) == []


@pytest.mark.unit
def test_listener_style_extra_fields_are_tolerated():
    """LISTENER writes signal_id / channel / edited alongside the standard
    body. The schema must tolerate these so the same file format works for
    both writers without a coordinated migration."""
    import athena_api as bm

    payload = {
        "type": "MANAGEMENT",
        "intent": "MOVE_BE",
        "source": "LISTENER",
        "timestamp": "2026-05-02T11:00:00+00:00",
        "pct": None,
        "group_id": 7,
        "sl": None,
        "tp": None,
        "tp_stage": None,
        "signal_id": 12345,
        "channel": "Ben's VIP Club",
        "edited": False,
    }
    assert bm._validate_mgmt_body(payload) == []
