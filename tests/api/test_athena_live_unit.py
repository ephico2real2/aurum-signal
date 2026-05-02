"""
Unit-style /api/live checks via Flask test_client (no running ATHENA process).
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

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
    reg = d.get("regime") or {}
    assert isinstance(reg, dict)
    assert "config" in reg and isinstance(reg["config"], dict)
    assert "current" in reg and isinstance(reg["current"], dict)
    assert "transitions_24h" in reg and isinstance(reg["transitions_24h"], list)
    assert "performance_30d" in reg and isinstance(reg["performance_30d"], dict)


def test_claude_api_call_has_timeout_set(monkeypatch):
    import aurum  # noqa: WPS433
    import listener  # noqa: WPS433
    import httpx

    calls = []

    class _Messages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(text='{"type":"IGNORE"}')],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    class _Scribe:
        def log_aurum_conversation(self, **kwargs):
            return None

    monkeypatch.setattr(aurum, "report_component_status", lambda *args, **kwargs: None)

    a = object.__new__(aurum.Aurum)
    a.claude = SimpleNamespace(messages=_Messages())
    a.scribe = _Scribe()
    a._mode = "SIGNAL"
    a._build_context = lambda: ""
    a._maybe_web_search = lambda query: ""
    a._build_memory = lambda: ""
    a._build_system_prompt = lambda context, memory="": "system"
    a._get_conversation_messages = lambda query, source: [{"role": "user", "content": query}]
    a._check_for_command = lambda answer: None
    a._extract_json_commands_from_response = lambda answer, source="": None
    a._execute_chart_commands = lambda answer: None
    a._append_to_conversation = lambda source, role, content: None
    assert a.ask("status", source="TEST")

    l = object.__new__(listener.Listener)
    l.claude = SimpleNamespace(messages=_Messages())
    parsed = asyncio.run(l._parse("ignore this"))
    assert parsed == {"type": "IGNORE"}

    assert calls
    assert all(isinstance(call.get("timeout"), httpx.Timeout) for call in calls)
