from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


@pytest.mark.unit
def test_sydney_open_alert_fires_once_per_day(monkeypatch):
    import bridge as bm

    stub = SimpleNamespace()
    stub._current_session = "ASIAN"
    stub._last_sydney_open_alert_key = None
    stub.scribe = MagicMock()
    stub.herald = MagicMock()

    monkeypatch.setattr(bm, "SYDNEY_OPEN_ALERT_ENABLED", True)
    monkeypatch.setattr(
        bm,
        "sydney_open_alert_info",
        lambda: {
            "should_fire": True,
            "alert_key": "2026-06-15",
            "open_utc": "2026-06-15T23:00:00+00:00",
            "sydney_now": "2026-06-16T09:01:00+10:00",
        },
    )

    bm.Bridge._check_sydney_open_alert(stub)
    bm.Bridge._check_sydney_open_alert(stub)

    stub.scribe.log_system_event.assert_called_once()
    stub.herald.send.assert_called_once()

