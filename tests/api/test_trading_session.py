"""Kill-zone session labels from UTC clock (trading_session.py)."""
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "python"))
from trading_session import get_trading_session_utc, sydney_open_alert_info  # noqa: E402


def _at(hour: int, minute: int = 0) -> datetime:
    # Winter baseline (London UTC+0, NY UTC-5)
    return datetime(2026, 1, 5, hour, minute, tzinfo=timezone.utc)


def test_london_window():
    assert get_trading_session_utc(_at(8)) == "LONDON"
    assert get_trading_session_utc(_at(12, 59)) == "LONDON"


def test_new_york_then_asian_wrap():
    assert get_trading_session_utc(_at(17)) == "NEW_YORK"
    assert get_trading_session_utc(_at(21, 59)) == "NEW_YORK"
    # Previously misclassified OFF_HOURS (gap 22–01 UTC)
    assert get_trading_session_utc(_at(22)) == "SYDNEY"
    assert get_trading_session_utc(_at(23, 40)) == "SYDNEY"
    assert get_trading_session_utc(_at(0, 30)) == "SYDNEY"
    assert get_trading_session_utc(_at(7, 59)) == "ASIAN"


def test_london_opens_after_asian():
    assert get_trading_session_utc(_at(8, 0)) == "LONDON"


def test_london_ny_mid_window():
    assert get_trading_session_utc(_at(14)) == "LONDON_NY"


def test_sydney_session_dst_aware_summer():
    # Jan = AEDT (UTC+11): 22:00 UTC -> 09:00 Sydney local
    now = datetime(2026, 1, 15, 22, 0, tzinfo=timezone.utc)
    assert get_trading_session_utc(now) == "SYDNEY"


def test_sydney_session_dst_aware_winter():
    # Jun = AEST (UTC+10): 23:00 UTC -> 09:00 Sydney local
    now = datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc)
    assert get_trading_session_utc(now) == "SYDNEY"


def test_sydney_open_alert_info_respects_dst():
    summer = sydney_open_alert_info(datetime(2026, 1, 15, 22, 1, tzinfo=timezone.utc))
    winter = sydney_open_alert_info(datetime(2026, 6, 15, 23, 1, tzinfo=timezone.utc))
    assert summer["should_fire"] is True
    assert winter["should_fire"] is True
    assert "T22:00:00+00:00" in summer["open_utc"]
    assert "T23:00:00+00:00" in winter["open_utc"]


def test_london_dst_shift_summer():
    # In summer (BST), London 08:00 local starts at 07:00 UTC.
    assert get_trading_session_utc(datetime(2026, 6, 15, 7, 0, tzinfo=timezone.utc)) == "LONDON"


def test_new_york_dst_shift_summer():
    # In summer (EDT), New York 12:00 local starts at 16:00 UTC.
    assert get_trading_session_utc(datetime(2026, 6, 15, 16, 0, tzinfo=timezone.utc)) == "NEW_YORK"


def test_trading_day_reset_hour_defaults_to_london(monkeypatch):
    from trading_session import trading_day_reset_hour_utc

    monkeypatch.delenv("AEGIS_SESSION_RESET_HOUR", raising=False)
    monkeypatch.setenv("SESSION_LONDON_START", "8")
    assert trading_day_reset_hour_utc() == 8


def test_trading_day_reset_hour_aegis_override(monkeypatch):
    from trading_session import trading_day_reset_hour_utc

    monkeypatch.setenv("AEGIS_SESSION_RESET_HOUR", "1")
    monkeypatch.setenv("SESSION_LONDON_START", "8")
    assert trading_day_reset_hour_utc() == 1
