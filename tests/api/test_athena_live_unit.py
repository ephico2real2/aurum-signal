"""
Unit-style /api/live checks via Flask test_client (no running ATHENA process).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "python"))


def test_api_live_has_execution_and_tradingview():
    import athena_api  # noqa: WPS433

    client = athena_api.app.test_client()
    r = client.get("/api/live")
    assert r.status_code == 200
    d = r.get_json()
    assert "execution" in d and isinstance(d["execution"], dict)
    assert "tradingview" in d and isinstance(d["tradingview"], dict)
    assert "mt5_quote_stale" in d
    assert "stale" in d["execution"] and "usable" in d["execution"]
    assert d.get("session_utc") in (
        "SYDNEY", "ASIAN", "LONDON", "LONDON_NY", "NEW_YORK", "OFF_HOURS",
    )
    ag = d.get("aegis") or {}
    assert ag.get("pnl_day_reset_hour_utc") in range(24)
    pw = d.get("performance_window") or {}
    assert pw.get("days") == 7
    assert "label" in pw
