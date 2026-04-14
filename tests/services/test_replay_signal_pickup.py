from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "replay_signal_pickup.py"


spec = importlib.util.spec_from_file_location("replay_signal_pickup", SCRIPT_PATH)
replay_mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = replay_mod
spec.loader.exec_module(replay_mod)


class _ScribeStub:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *_args, **_kwargs):
        return self._rows


@pytest.mark.unit
def test_find_chat_id_for_channel_normalizes_unicode_and_spaces():
    mapping = {
        -1002034822451: "Ben's VIP Club",
        -1001959885205: "FXM FREE TRADING ROOM",
    }
    chat_id = replay_mod._find_chat_id_for_channel("  Ben’s   VIP Club ", mapping)
    assert chat_id == -1002034822451


@pytest.mark.unit
def test_load_replay_payload_from_signal_id_infers_chat_id():
    args = argparse.Namespace(
        from_signal_id=220,
        text=None,
        chat_id=None,
        channel_name="",
    )
    scribe = _ScribeStub(
        [{"id": 220, "raw_text": "Sell Gold @4774.6-4784.6 Sl:4788.6 Tp1:4770.6", "channel_name": "Ben's VIP Club"}]
    )
    payload = replay_mod._load_replay_payload(
        args=args,
        scribe=scribe,
        channel_names={-1002034822451: "Ben's VIP Club"},
    )
    assert payload.channel_name == "Ben's VIP Club"
    assert payload.chat_id == -1002034822451
    assert payload.source == "signals_received.id=220"


@pytest.mark.unit
def test_load_replay_payload_text_requires_chat_id():
    args = argparse.Namespace(
        from_signal_id=None,
        text="Sell Gold @ 4780-4776 SL 4786 TP1 4772",
        chat_id=None,
        channel_name="Ben's VIP Club",
    )
    with pytest.raises(ValueError):
        replay_mod._load_replay_payload(
            args=args,
            scribe=_ScribeStub([]),
            channel_names={},
        )
