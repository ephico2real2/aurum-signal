"""Kill-zone session labels from UTC clock (trading_session.py)."""
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "python"))

from trading_session import get_trading_session_utc  # noqa: E402


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 4, 5, hour, minute, tzinfo=timezone.utc)


def test_london_window():
    assert get_trading_session_utc(_at(8)) == "LONDON"
    assert get_trading_session_utc(_at(12, 59)) == "LONDON"


def test_new_york_then_asian_wrap():
    assert get_trading_session_utc(_at(17)) == "NEW_YORK"
    assert get_trading_session_utc(_at(21, 59)) == "NEW_YORK"
    # Previously misclassified OFF_HOURS (gap 22–01 UTC)
    assert get_trading_session_utc(_at(22)) == "ASIAN"
    assert get_trading_session_utc(_at(23, 40)) == "ASIAN"
    assert get_trading_session_utc(_at(0, 30)) == "ASIAN"
    assert get_trading_session_utc(_at(7, 59)) == "ASIAN"


def test_london_opens_after_asian():
    assert get_trading_session_utc(_at(8, 0)) == "LONDON"


def test_london_ny_mid_window():
    assert get_trading_session_utc(_at(14)) == "LONDON_NY"


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
