from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
HEALTH_PATH = ROOT / "scripts" / "health.py"


def _load_health_module():
    spec = importlib.util.spec_from_file_location("health_script_for_tests", str(HEALTH_PATH))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class _Resp:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self):
        return self._payload


def _live_payload(*, tv_age: float, lens_age: float, tv_brief_timestamp: str = "2026-04-13T00:00:00+00:00"):
    return {
        "mode": "WATCH",
        "session": "SYDNEY",
        "session_utc": "SYDNEY",
        "components": {"AURUM": {"ok": True}},
        "aegis": {"pnl_day_reset_hour_utc": 8},
        "circuit_breaker": False,
        "account_type": "DEMO",
        "broker": "Vantage",
        "mt5_connected": True,
        "open_groups": [],
        "performance": {},
        "tradingview": {
            "age_seconds": tv_age,
            "timestamp": "2026-04-15T05:00:00+00:00",
            "tv_brief_timestamp": tv_brief_timestamp,
        },
        "lens": {
            "age_seconds": lens_age,
            "timestamp": "2026-04-15T05:00:00+00:00",
            "tv_brief_timestamp": tv_brief_timestamp,
        },
    }


@pytest.mark.unit
def test_check_live_ok_when_indicators_fresh_even_if_tv_brief_old(monkeypatch):
    health = _load_health_module()
    payload = _live_payload(tv_age=4.0, lens_age=4.0)
    fake_requests = SimpleNamespace(get=lambda *_args, **_kwargs: _Resp(payload))
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    status, detail = health.check_live()
    assert status == "OK"
    assert detail.get("tradingview_age_sec") == 4.0
    assert detail.get("lens_age_sec") == 4.0
    assert "tv_brief_note" in detail


@pytest.mark.unit
def test_check_live_warns_when_tradingview_snapshot_is_stale(monkeypatch):
    health = _load_health_module()
    payload = _live_payload(tv_age=900.0, lens_age=900.0)
    fake_requests = SimpleNamespace(get=lambda *_args, **_kwargs: _Resp(payload))
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    status, detail = health.check_live()
    assert status == "WARN"
    assert "TradingView/LENS snapshot stale" in str(detail)
