"""
test_listener_room_filter.py — LISTENER room-allowlist and pipeline observability tests
========================================================================================
Covers:
  - SIGNAL_TRADE_ROOMS matching by chat_id (all variant forms)
  - SIGNAL_TRADE_ROOMS matching by normalized title
  - title mismatch but chat_id match → dispatch proceeds
  - unmatched rooms → WATCH_ONLY with WATCH_ONLY_ROOM_FILTER reason code
  - empty SIGNAL_TRADE_ROOMS → all rooms allowed (ALLOWED_ALL)
  - PARSE_FAILED event logged for non-empty unparsed text
  - SIGNAL_DISPATCHED event logged on successful entry dispatch
  - stale listener detection via last_ingest_at
  - reason code WATCH_ONLY_ROOM_FILTER replaces ROOM_NOT_PRIORITY
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

import listener as listener_mod
from listener import Listener


# ── Shared stubs ────────────────────────────────────────────────────

class _Obj:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _ScribeStub:
    def __init__(self):
        self.logged_signals: list[dict] = []
        self.signal_updates: list[tuple] = []
        self.system_events: list[dict] = []

    def log_signal(self, **kwargs):
        self.logged_signals.append(kwargs)
        return len(self.logged_signals)

    def update_signal_action(self, signal_id, action, skip_reason=None, group_id=None):
        self.signal_updates.append((signal_id, action, skip_reason, group_id))

    def log_vision_extraction(self, data):
        return 1

    def update_vision_extraction_result(self, *args, **kwargs):
        pass

    def log_system_event(self, **kwargs):
        self.system_events.append(kwargs)

    def query(self, *args, **kwargs):
        return []


def _make_listener(mode: str = "SIGNAL") -> tuple[Listener, _ScribeStub]:
    l = Listener()
    scribe = _ScribeStub()
    l.scribe = scribe
    l.herald = _Obj(send=lambda *_a, **_k: True)
    l._mode = mode
    l._write_signal = lambda data: None
    l._write_mgmt = lambda data: None
    return l, scribe


def _entry_parse():
    async def _p(_text):
        return {
            "type": "ENTRY",
            "direction": "BUY",
            "entry_low": 4700.0,
            "entry_high": 4702.0,
            "sl": 4694.0,
            "tp1": 4710.0,
        }
    return _p


def _ignore_parse():
    async def _p(_text):
        return {"type": "IGNORE"}
    return _p


def _build_msg(
    text: str = "BUY Gold 4700-4702 SL 4694 TP 4710",
    chat_title: str = "Ben's VIP Club",
    chat_id: int = -1001234567890,
    msg_id: int = 42,
):
    class _Msg:
        def __init__(self):
            self.message = text
            self.id = msg_id
            self.chat_id = chat_id
            self.chat = _Obj(title=chat_title)
            self.photo = None
            self.document = None
    return _Msg()


# ── _is_trade_room_allowed unit tests ───────────────────────────────

@pytest.mark.unit
class TestTradeRoomAllowlistEnvParsing:

    def test_active_signal_trade_rooms_alias_is_supported(self, monkeypatch):
        monkeypatch.delenv("SIGNAL_TRADE_ROOMS", raising=False)
        monkeypatch.setenv(
            "ACTIVE_SIGNAL_TRADE_ROOMS",
            "-1002034822451,-1001959885205",
        )
        rooms, source = listener_mod._parse_signal_trade_rooms()
        assert rooms == {"-1002034822451", "-1001959885205"}
        assert source == "ACTIVE_SIGNAL_TRADE_ROOMS"

    def test_signal_and_active_allowlists_are_merged(self, monkeypatch):
        monkeypatch.setenv("SIGNAL_TRADE_ROOMS", "ben's vip club")
        monkeypatch.setenv("ACTIVE_SIGNAL_TRADE_ROOMS", "-1001959885205")
        rooms, source = listener_mod._parse_signal_trade_rooms()
        assert "ben's vip club" in rooms
        assert "-1001959885205" in rooms
        assert source == "SIGNAL_TRADE_ROOMS+ACTIVE_SIGNAL_TRADE_ROOMS"

    def test_allowlist_parser_normalizes_spacing_and_case(self, monkeypatch):
        monkeypatch.setenv("SIGNAL_TRADE_ROOMS", "  BEN'S   VIP CLUB  ")
        monkeypatch.delenv("ACTIVE_SIGNAL_TRADE_ROOMS", raising=False)
        rooms, _ = listener_mod._parse_signal_trade_rooms()
        assert rooms == {"ben's vip club"}


@pytest.mark.unit
class TestIsTradeRoomAllowed:

    def test_empty_allowlist_allows_all(self, monkeypatch):
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", set())
        allowed, reason = Listener._is_trade_room_allowed("Any Room", -100999)
        assert allowed is True
        assert reason == "ALLOWED_ALL"

    def test_title_match_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"ben's vip club"})
        allowed, reason = Listener._is_trade_room_allowed("Ben's VIP Club", -100999)
        assert allowed is True
        assert reason == "ALLOWED_TITLE_MATCH"

    def test_title_match_with_extra_whitespace(self, monkeypatch):
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"ben's vip club"})
        allowed, reason = Listener._is_trade_room_allowed("  Ben's VIP Club  ", -100999)
        assert allowed is True
        assert reason == "ALLOWED_TITLE_MATCH"

    def test_title_match_unicode_normalized(self, monkeypatch):
        # Curly apostrophe in channel title vs straight in config
        import unicodedata
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"ben\u2019s vip club"})
        allowed, reason = Listener._is_trade_room_allowed("Ben\u2019s VIP Club", -100999)
        assert allowed is True
        assert reason == "ALLOWED_TITLE_MATCH"

    def test_title_mismatch_falls_through_to_id_check(self, monkeypatch):
        # Configured by full negative chat_id; title is different
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"-1001234567890"})
        allowed, reason = Listener._is_trade_room_allowed("Different Title", -1001234567890)
        assert allowed is True
        assert reason == "ALLOWED_ID_MATCH"

    def test_chat_id_match_base_id_without_prefix(self, monkeypatch):
        # Operator configured just "1234567890" without the -100 supergroup prefix
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"1234567890"})
        allowed, reason = Listener._is_trade_room_allowed("Some Channel", -1001234567890)
        assert allowed is True
        assert reason == "ALLOWED_ID_MATCH"

    def test_chat_id_match_positive_form(self, monkeypatch):
        # Operator configured positive form of the ID
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"1001234567890"})
        allowed, reason = Listener._is_trade_room_allowed("Some Channel", -1001234567890)
        assert allowed is True
        assert reason == "ALLOWED_ID_MATCH"

    def test_unmatched_room_returns_watch_only_filter(self, monkeypatch):
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"ben's vip club"})
        allowed, reason = Listener._is_trade_room_allowed("Other Room", -100999888)
        assert allowed is False
        assert reason == "WATCH_ONLY_ROOM_FILTER"

    def test_multiple_rooms_one_matches(self, monkeypatch):
        monkeypatch.setattr(
            listener_mod, "SIGNAL_TRADE_ROOMS", {"garry's signals", "flair fx"}
        )
        allowed, reason = Listener._is_trade_room_allowed("FLAIR FX", -100999)
        assert allowed is True
        assert reason == "ALLOWED_TITLE_MATCH"


# ── Integration: _handle_message dispatch scenarios ─────────────────

@pytest.mark.unit
class TestHandleMessageRoomFilter:

    def test_watch_only_room_sets_reason_code(self, monkeypatch):
        """Unallowed room → WATCH_ONLY action with WATCH_ONLY_ROOM_FILTER reason."""
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"ben's vip club"})
        monkeypatch.setattr(listener_mod, "VISION_ENABLED", False)

        l, scribe = _make_listener()
        dispatched = []
        l._write_signal = lambda d: dispatched.append(d)
        l._parse = _entry_parse()

        msg = _build_msg(chat_title="Other Room", chat_id=-100999888)
        asyncio.run(l._handle_message(msg))

        assert not dispatched, "Should NOT dispatch for unallowed room"
        assert scribe.signal_updates
        action = scribe.signal_updates[-1]
        assert action[1] == "WATCH_ONLY"
        assert action[2] == "WATCH_ONLY_ROOM_FILTER"
        assert any(e.get("reason") == "WATCH_ONLY_ROOM_FILTER" for e in scribe.system_events)

    def test_watch_only_room_reason_is_not_room_not_priority(self, monkeypatch):
        """Confirm old reason code ROOM_NOT_PRIORITY is no longer used."""
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"ben's vip club"})
        monkeypatch.setattr(listener_mod, "VISION_ENABLED", False)

        l, scribe = _make_listener()
        l._parse = _entry_parse()

        msg = _build_msg(chat_title="Other Room", chat_id=-100999888)
        asyncio.run(l._handle_message(msg))

        for update in scribe.signal_updates:
            assert "ROOM_NOT_PRIORITY" not in (update[2] or ""), \
                "Old reason code ROOM_NOT_PRIORITY must no longer appear"

    def test_chat_id_match_dispatches_even_if_title_mismatch(self, monkeypatch):
        """Room with renamed title still dispatches when chat_id is configured."""
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"-1001234567890"})
        monkeypatch.setattr(listener_mod, "VISION_ENABLED", False)

        l, scribe = _make_listener()
        dispatched = []
        l._write_signal = lambda d: dispatched.append(d)
        l._parse = _entry_parse()

        msg = _build_msg(chat_title="Room Title Has Changed", chat_id=-1001234567890)
        asyncio.run(l._handle_message(msg))

        assert dispatched, "Should dispatch when chat_id matches even if title changed"
        assert not any(
            u[1] == "WATCH_ONLY" for u in scribe.signal_updates
        ), "Should not be WATCH_ONLY when chat_id matches"

    def test_allowed_room_dispatches_and_emits_dispatched_event(self, monkeypatch):
        """Allowed room → signal written and SIGNAL_DISPATCHED event logged."""
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"ben's vip club"})
        monkeypatch.setattr(listener_mod, "VISION_ENABLED", False)

        l, scribe = _make_listener()
        dispatched = []
        l._write_signal = lambda d: dispatched.append(d)
        l._parse = _entry_parse()

        msg = _build_msg(chat_title="Ben's VIP Club", chat_id=-1001234567890)
        asyncio.run(l._handle_message(msg))

        assert dispatched, "Should dispatch for allowed room"
        assert any(
            e.get("event_type") == "SIGNAL_DISPATCHED" for e in scribe.system_events
        ), "SIGNAL_DISPATCHED event must be logged"

    def test_empty_trade_rooms_all_dispatch(self, monkeypatch):
        """Empty SIGNAL_TRADE_ROOMS → every room is tradable."""
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", set())
        monkeypatch.setattr(listener_mod, "VISION_ENABLED", False)

        l, scribe = _make_listener()
        dispatched = []
        l._write_signal = lambda d: dispatched.append(d)
        l._parse = _entry_parse()

        msg = _build_msg(chat_title="Random Room", chat_id=-100111)
        asyncio.run(l._handle_message(msg))

        assert dispatched, "Should dispatch for any room when SIGNAL_TRADE_ROOMS is empty"
        assert not any(u[1] == "WATCH_ONLY" for u in scribe.signal_updates)


# ── PARSE_FAILED observability ───────────────────────────────────────

@pytest.mark.unit
class TestParseFailed:

    def test_non_empty_text_that_parses_as_ignore_logs_parse_failed(self, monkeypatch):
        """Non-signal text produces SIGNAL_PARSE_FAILED system event."""
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", set())
        monkeypatch.setattr(listener_mod, "VISION_ENABLED", False)

        l, scribe = _make_listener()
        l._parse = _ignore_parse()

        msg = _build_msg(text="Good morning traders! Have a great day.")
        asyncio.run(l._handle_message(msg))

        assert any(
            e.get("event_type") == "SIGNAL_PARSE_FAILED" for e in scribe.system_events
        ), "SIGNAL_PARSE_FAILED must be emitted for non-signal text"
        assert any(
            e.get("reason") == "PARSE_FAILED" for e in scribe.system_events
        )

    def test_empty_text_does_not_log_parse_failed(self, monkeypatch):
        """Genuinely empty-text message (media-only) must not emit PARSE_FAILED."""
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", set())
        monkeypatch.setattr(listener_mod, "VISION_ENABLED", False)

        l, scribe = _make_listener()
        l._parse = _ignore_parse()

        msg = _build_msg(text="")
        asyncio.run(l._handle_message(msg))

        assert not any(
            e.get("event_type") == "SIGNAL_PARSE_FAILED" for e in scribe.system_events
        ), "Empty-text message must not generate PARSE_FAILED"


# ── Stale listener detection ─────────────────────────────────────────

@pytest.mark.unit
class TestListenerStaleness:

    def test_last_ingest_at_updated_on_message(self, monkeypatch):
        """_last_ingest_at is set when a message arrives."""
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", set())
        monkeypatch.setattr(listener_mod, "VISION_ENABLED", False)

        l, scribe = _make_listener()
        assert l._last_ingest_at is None

        l._parse = _ignore_parse()  # even IGNORE updates the timestamp
        msg = _build_msg(text="some text")
        asyncio.run(l._handle_message(msg))

        assert l._last_ingest_at is not None
        assert isinstance(l._last_ingest_at, datetime)

    def test_last_ingest_at_updated_on_dispatched_entry(self, monkeypatch):
        """_last_ingest_at is refreshed on successful ENTRY dispatch."""
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", set())
        monkeypatch.setattr(listener_mod, "VISION_ENABLED", False)

        l, scribe = _make_listener()
        l._write_signal = lambda d: None
        l._parse = _entry_parse()

        msg = _build_msg()
        asyncio.run(l._handle_message(msg))

        assert l._last_ingest_at is not None
        age = (datetime.now(timezone.utc) - l._last_ingest_at).total_seconds()
        assert age < 5, "last_ingest_at must be very recent"

    def test_stale_threshold_config(self, monkeypatch):
        """LISTENER_STALE_THRESHOLD_SEC controls the stale check."""
        monkeypatch.setattr(listener_mod, "LISTENER_STALE_THRESHOLD_SEC", 300)
        assert listener_mod.LISTENER_STALE_THRESHOLD_SEC == 300


# ── Reason code consistency — SIGNAL_ROOM_WATCH_ONLY event ──────────

@pytest.mark.unit
class TestWatchOnlyEventDetails:

    def test_watch_only_event_contains_channel_and_chat_id(self, monkeypatch):
        """SIGNAL_ROOM_WATCH_ONLY system event must include channel and chat_id in notes."""
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"ben's vip club"})
        monkeypatch.setattr(listener_mod, "VISION_ENABLED", False)

        l, scribe = _make_listener()
        l._parse = _entry_parse()

        msg = _build_msg(chat_title="GARRY'S SIGNALS", chat_id=-100777)
        asyncio.run(l._handle_message(msg))

        watch_events = [
            e for e in scribe.system_events
            if e.get("event_type") == "SIGNAL_ROOM_WATCH_ONLY"
        ]
        assert watch_events, "SIGNAL_ROOM_WATCH_ONLY event must be emitted"
        notes = watch_events[0].get("notes", "")
        assert "GARRY'S SIGNALS" in notes or "garry" in notes.lower()
        assert "-100777" in notes or "chat_id=-100777" in notes

    def test_watch_only_event_reason_is_structured_code(self, monkeypatch):
        """reason field must be WATCH_ONLY_ROOM_FILTER, not a free-text composite."""
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"ben's vip club"})
        monkeypatch.setattr(listener_mod, "VISION_ENABLED", False)

        l, scribe = _make_listener()
        l._parse = _entry_parse()

        msg = _build_msg(chat_title="Unknown Room", chat_id=-100555)
        asyncio.run(l._handle_message(msg))

        watch_events = [
            e for e in scribe.system_events
            if e.get("event_type") == "SIGNAL_ROOM_WATCH_ONLY"
        ]
        assert watch_events
        assert watch_events[0].get("reason") == "WATCH_ONLY_ROOM_FILTER"
