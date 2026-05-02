import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def test_sentinel_returns_true_on_fetch_failure(monkeypatch):
    import requests
    import sentinel

    def _raise(*args, **kwargs):
        raise requests.RequestException("network down")

    monkeypatch.setattr(sentinel.requests, "get", _raise)
    monkeypatch.setattr(sentinel.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(sentinel.Sentinel, "_write_status", lambda self, status: None)
    monkeypatch.setattr(sentinel, "gather_news_feeds", lambda: {})
    monkeypatch.setattr(sentinel, "report_component_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sentinel.Sentinel,
        "_activate_guard",
        lambda self, event, current_mode: setattr(self, "guard_active", True)
        or setattr(self, "_guarding_event", event),
    )

    s = object.__new__(sentinel.Sentinel)
    s.guard_active = False
    s._guarding_event = None
    s._event_id = None
    s._last_digest_ts = 10**20
    s._digest_interval = 600

    status = s.check("HYBRID")
    assert status["block_trading"] is True


def test_sentinel_retries_before_failsafe(monkeypatch):
    import requests
    import sentinel

    calls = {"n": 0}

    def _get(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.RequestException("temporary failure")
        return type("_Resp", (), {"text": "<html></html>"})()

    s = object.__new__(sentinel.Sentinel)

    monkeypatch.setattr(sentinel.requests, "get", _get)
    monkeypatch.setattr(sentinel.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        sentinel.Sentinel,
        "_parse_ff",
        lambda self, html, currencies: [
            {
                "name": "Real event",
                "impact": "LOW",
                "currency": "USD",
                "minutes_away": 999,
                "time_str": "00:00 UTC",
                "event_dt": "2026-05-02T00:00:00+00:00",
            }
        ],
    )

    events = s._fetch_events({"USD"})
    assert calls["n"] == 3
    assert events[0]["name"] == "Real event"
    assert not events[0].get("fail_safe")
