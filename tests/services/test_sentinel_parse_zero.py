import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


@pytest.mark.unit
def test_zero_events_during_weekday_trading_hours_triggers_warning_and_alert(monkeypatch, caplog):
    import herald
    import sentinel

    sent = []
    monkeypatch.setattr(herald, "get_herald", lambda: SimpleNamespace(send=lambda msg: sent.append(msg)))
    s = object.__new__(sentinel.Sentinel)

    now = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    with caplog.at_level(logging.WARNING, logger="sentinel"):
        assert s._alert_parse_zero_if_needed([], now) is True

    assert sent == [sentinel._PARSE_ZERO_ALERT]
    assert sentinel._PARSE_ZERO_ALERT in caplog.text


@pytest.mark.unit
def test_zero_events_on_saturday_does_not_trigger_alert(monkeypatch):
    import herald
    import sentinel

    sent = []
    monkeypatch.setattr(herald, "get_herald", lambda: SimpleNamespace(send=lambda msg: sent.append(msg)))
    s = object.__new__(sentinel.Sentinel)

    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    assert s._alert_parse_zero_if_needed([], now) is False
    assert sent == []


@pytest.mark.unit
def test_zero_events_outside_trading_hours_does_not_trigger_alert(monkeypatch):
    import herald
    import sentinel

    sent = []
    monkeypatch.setattr(herald, "get_herald", lambda: SimpleNamespace(send=lambda msg: sent.append(msg)))
    s = object.__new__(sentinel.Sentinel)

    now = datetime(2026, 5, 1, 3, 0, tzinfo=timezone.utc)
    assert s._alert_parse_zero_if_needed([], now) is False
    assert sent == []


@pytest.mark.unit
def test_non_zero_events_never_trigger_alert(monkeypatch):
    import herald
    import sentinel

    sent = []
    monkeypatch.setattr(herald, "get_herald", lambda: SimpleNamespace(send=lambda msg: sent.append(msg)))
    s = object.__new__(sentinel.Sentinel)

    now = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    assert s._alert_parse_zero_if_needed([{"name": "CPI"}], now) is False
    assert sent == []


@pytest.mark.unit
def test_forexfactory_eastern_time_uses_dst_in_summer():
    import sentinel

    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    out = sentinel.Sentinel._parse_time(object.__new__(sentinel.Sentinel), "8:30am", base)
    assert out.hour == 12
    assert out.minute == 30


@pytest.mark.unit
def test_forexfactory_eastern_time_uses_est_in_winter():
    import sentinel

    base = datetime(2026, 1, 15, tzinfo=timezone.utc)
    out = sentinel.Sentinel._parse_time(object.__new__(sentinel.Sentinel), "8:30am", base)
    assert out.hour == 13
    assert out.minute == 30
