from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

import athena_api


def test_parse_signal_trade_rooms_from_active_alias(monkeypatch):
    monkeypatch.delenv("SIGNAL_TRADE_ROOMS", raising=False)
    monkeypatch.setenv(
        "ACTIVE_SIGNAL_TRADE_ROOMS",
        "-1002034822451,-1001959885205",
    )
    rooms, source = athena_api._parse_signal_trade_rooms_from_env()
    assert rooms == {"-1002034822451", "-1001959885205"}
    assert source == "ACTIVE_SIGNAL_TRADE_ROOMS"


def test_is_trade_room_allowed_matches_supergroup_id_variants():
    rooms = {"1234567890"}
    allowed, reason = athena_api._is_trade_room_allowed("Any Room", -1001234567890, rooms)
    assert allowed is True
    assert reason == "ALLOWED_ID_MATCH"


@pytest.fixture
def client():
    athena_api.app.config["TESTING"] = True
    with athena_api.app.test_client() as c:
        yield c


def test_api_channels_uses_alias_allowlist_for_id_match(client, monkeypatch):
    class _StubScribe:
        def query(self, *_args, **_kwargs):
            return []

    monkeypatch.setenv("TELEGRAM_CHANNELS", "-1002034822451,-1003582676523")
    monkeypatch.delenv("SIGNAL_TRADE_ROOMS", raising=False)
    monkeypatch.setenv("ACTIVE_SIGNAL_TRADE_ROOMS", "-1002034822451")
    monkeypatch.setattr(athena_api, "get_scribe", lambda: _StubScribe())

    def _fake_read_json(path: str):
        if path.endswith("channel_names.json"):
            return {}
        if path.endswith("listener_meta.json"):
            return {}
        return {}

    monkeypatch.setattr(athena_api, "_read_json", _fake_read_json)

    r = client.get("/api/channels")
    assert r.status_code == 200
    d = r.get_json()
    assert d["signal_trade_rooms_active"] is True
    assert d["signal_trade_rooms_source"] == "ACTIVE_SIGNAL_TRADE_ROOMS"
    by_id = {c["id"]: c for c in d["channels"]}
    assert by_id["-1002034822451"]["is_trade_room"] is True
    assert by_id["-1002034822451"]["match_reason"] == "ALLOWED_ID_MATCH"
    assert by_id["-1003582676523"]["is_trade_room"] is False
    assert by_id["-1003582676523"]["match_reason"] == "WATCH_ONLY_ROOM_FILTER"
