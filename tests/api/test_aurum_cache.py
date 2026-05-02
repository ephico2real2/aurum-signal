from __future__ import annotations

import builtins
import os
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


class _Readable:
    def __init__(self, text: str):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.text


def _reload_aurum_with_fake_open(monkeypatch, reads: dict[str, list[str]]):
    soul = str(ROOT / "SOUL.md")
    skill = str(ROOT / "SKILL.md")
    monkeypatch.setenv("SOUL_FILE", soul)
    monkeypatch.setenv("SKILL_FILE", skill)
    counts = {soul: 0, skill: 0}
    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        p = str(path)
        if p in counts:
            idx = min(counts[p], len(reads[p]) - 1)
            counts[p] += 1
            return _Readable(reads[p][idx])
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.delitem(sys.modules, "aurum", raising=False)
    import aurum as aurum_mod

    return aurum_mod, counts


def _askable_aurum(aurum_mod):
    a = aurum_mod.Aurum.__new__(aurum_mod.Aurum)
    a.claude = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(
                content=[SimpleNamespace(text="cached answer")],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )
        )
    )
    a._mode = "SIGNAL"
    a._build_context = lambda: "context"
    a._build_memory = lambda: ""
    a._get_conversation_messages = lambda query, source: [{"role": "user", "content": query}]
    a._maybe_web_search = lambda query: None
    a._check_for_command = lambda answer: None
    a._extract_json_commands_from_response = lambda answer, source="": None
    a._execute_chart_commands = lambda answer: None
    a._append_to_conversation = lambda source, role, content: None
    a.scribe = SimpleNamespace(log_aurum_conversation=lambda **kwargs: None)
    return a


@pytest.mark.unit
def test_ask_uses_cached_soul_skill_without_rereading(monkeypatch):
    aurum_mod, counts = _reload_aurum_with_fake_open(
        monkeypatch,
        {
            str(ROOT / "SOUL.md"): ["SOUL cached"],
            str(ROOT / "SKILL.md"): ["SKILL cached"],
        },
    )
    a = _askable_aurum(aurum_mod)

    assert a.ask("one", source="TEST") == "cached answer"
    assert a.ask("two", source="TEST") == "cached answer"

    assert counts[str(ROOT / "SOUL.md")] == 1
    assert counts[str(ROOT / "SKILL.md")] == 1


@pytest.mark.unit
def test_sighup_reloads_soul_skill_cache(monkeypatch):
    aurum_mod, counts = _reload_aurum_with_fake_open(
        monkeypatch,
        {
            str(ROOT / "SOUL.md"): ["SOUL v1", "SOUL v2"],
            str(ROOT / "SKILL.md"): ["SKILL v1", "SKILL v2"],
        },
    )

    assert aurum_mod._SOUL_CACHE == "SOUL v1"
    assert aurum_mod._SKILL_CACHE == "SKILL v1"

    os.kill(os.getpid(), signal.SIGHUP)

    assert aurum_mod._SOUL_CACHE == "SOUL v2"
    assert aurum_mod._SKILL_CACHE == "SKILL v2"
    assert counts[str(ROOT / "SOUL.md")] == 2
    assert counts[str(ROOT / "SKILL.md")] == 2
