from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
import aegis as aegis_mod
import listener as listener_mod

from aurum import Aurum
from herald import Herald
from listener import Listener
from vision import Vision


class _Obj:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _VisionStub:
    def __init__(self, result):
        self._result = result

    def extract(self, **kwargs):
        return self._result


class _ScribeStub:
    def __init__(self):
        self.logged_signals = []
        self.signal_updates = []
        self.logged_vision = []
        self.vision_updates = []
        self.system_events = []

    def log_signal(self, **kwargs):
        self.logged_signals.append(kwargs)
        return 1

    def update_signal_action(self, signal_id, action, skip_reason=None, group_id=None):
        self.signal_updates.append((signal_id, action, skip_reason, group_id))

    def log_vision_extraction(self, data):
        self.logged_vision.append(data)
        return 7

    def update_vision_extraction_result(self, extraction_id, downstream_result, linked_signal_id=None, linked_group_id=None):
        self.vision_updates.append((extraction_id, downstream_result, linked_signal_id, linked_group_id))

    def log_system_event(self, **kwargs):
        self.system_events.append(kwargs)


@pytest.mark.unit
class TestVisionModule:
    def test_extract_missing_file_returns_low_safe_result(self):
        v = Vision(None)
        res = v.extract("/tmp/does-not-exist-vision.png")
        assert res.confidence == "LOW"
        assert res.structured_data.get("type") == "IGNORE"
        assert "IMAGE_NOT_FOUND" in (res.error or "")

    def test_extract_without_claude_returns_safe_result(self, tmp_path):
        p = tmp_path / "ok.png"
        Image.new("RGB", (8, 8), "white").save(p)
        v = Vision(None)
        res = v.extract(p)
        assert res.confidence == "LOW"
        assert "CLAUDE_NOT_CONFIGURED" in (res.error or "")

    def test_postprocess_adds_pinned_levels_and_infers_symbol_timeframe(self):
        v = Vision(None)
        raw = {
            "image_type": "CHART",
            "confidence": "MEDIUM",
            "extracted_text": "XAUUSD, M1 with red line at 4754.54 and current 4746.57",
            "structured_data": {"type": "IGNORE"},
            "caller_action": "CONFIRM",
        }
        out = v._apply_postprocess(
            raw,
            caption="chart screenshot",
            context_hint="GENERAL",
            numeric_hints=[],
        )
        sd = out["structured_data"]
        assert sd["instrument"] == "XAUUSD"
        assert sd["timeframe"] == "M1"
        assert "4754.54" in sd["pinned_levels"]
        assert "4746.57" in sd["pinned_levels"]

    def test_numeric_candidates_parses_price_labels(self):
        vals = Vision._numeric_candidates("sell 3.00 @ 4754.54 current 4746.57")
        assert "4754.54" in vals
        assert "4746.57" in vals


@pytest.mark.unit
class TestListenerImageFlow:
    def _build_msg(self, *, text: str, has_media: bool):
        class DummyMsg:
            def __init__(self, text, has_media):
                self.message = text
                self.id = 99
                self.chat_id = -1001
                self.chat = _Obj(title="test-channel")
                self.photo = object() if has_media else None
                self.document = None

            async def download_media(self, file):
                Image.new("RGB", (12, 12), "white").save(file, format="PNG")
                return file

        return DummyMsg(text, has_media)

    def test_low_confidence_image_signal_is_held(self, monkeypatch):
        l = Listener()
        scribe = _ScribeStub()
        l.scribe = scribe
        l.herald = _Obj(send=lambda *_args, **_kwargs: True)
        l._mode = "SIGNAL"
        l._write_signal = lambda data: (_ for _ in ()).throw(RuntimeError("should not dispatch"))
        l._write_mgmt = lambda data: None

        async def parse_ok(_text):
            return {
                "type": "ENTRY",
                "direction": "BUY",
                "entry_low": 100.0,
                "entry_high": 101.0,
                "sl": 99.0,
                "tp1": 103.0,
            }

        l._parse = parse_ok
        low = _Obj(
            structured_data={"type": "ENTRY", "direction": "BUY", "entry_low": 100.0, "entry_high": 101.0, "sl": 99.0, "tp1": 103.0},
            confidence="LOW",
            image_type="SIGNAL",
            caller_action="HOLD",
            extracted_text="unclear chart",
            image_hash="abc",
            file_size_kb=3,
            processing_ms=1,
            error=None,
        )
        l.vision = _VisionStub(low)
        msg = self._build_msg(text="BUY now", has_media=True)
        asyncio.run(l._handle_message(msg))

        assert scribe.signal_updates
        assert scribe.signal_updates[-1][1] == "HELD"
        assert scribe.logged_signals[0]["signal_source_type"] == "MIXED"

    def test_mixed_message_fills_missing_entry_fields_from_vision(self):
        l = Listener()
        scribe = _ScribeStub()
        l.scribe = scribe
        l.herald = _Obj(send=lambda *_args, **_kwargs: True)
        l._mode = "SIGNAL"
        captured = {}

        def capture_signal(data):
            captured["signal"] = dict(data)

        l._write_signal = capture_signal
        l._write_mgmt = lambda data: None

        async def parse_missing_tp1(_text):
            return {
                "type": "ENTRY",
                "direction": "SELL",
                "entry_low": 200.0,
                "entry_high": 201.0,
                "sl": 205.0,
                "tp1": None,
            }

        l._parse = parse_missing_tp1
        high = _Obj(
            structured_data={"type": "ENTRY", "direction": "SELL", "entry_low": 200.0, "entry_high": 201.0, "sl": 205.0, "tp1": 196.0},
            confidence="HIGH",
            image_type="SIGNAL",
            caller_action="DISPATCH",
            extracted_text="clear levels",
            image_hash="xyz",
            file_size_kb=4,
            processing_ms=2,
            error=None,
        )
        l.vision = _VisionStub(high)
        msg = self._build_msg(text="sell setup", has_media=True)
        asyncio.run(l._handle_message(msg))

        assert "signal" in captured
        assert captured["signal"]["tp1"] == 196.0
        assert scribe.logged_signals[0]["signal_source_type"] == "MIXED"

    def test_signal_room_media_sends_bot_summary_with_channel(self, monkeypatch):
        l = Listener()
        scribe = _ScribeStub()
        l.scribe = scribe
        sent = []
        l.herald = _Obj(send=lambda msg, **_kwargs: sent.append(msg) or True)
        l._mode = "SIGNAL"
        l._write_signal = lambda data: None
        l._write_mgmt = lambda data: None
        monkeypatch.setattr(listener_mod, "LISTENER_SIGNAL_MEDIA_SUMMARY_TO_BOT", True)

        async def parse_ok(_text):
            return {
                "type": "ENTRY",
                "direction": "BUY",
                "entry_low": 4700.0,
                "entry_high": 4701.0,
                "sl": 4695.0,
                "tp1": 4706.0,
            }

        l._parse = parse_ok
        high = _Obj(
            structured_data={"type": "ENTRY", "direction": "BUY", "entry_low": 4700.0, "entry_high": 4701.0, "sl": 4695.0, "tp1": 4706.0},
            confidence="HIGH",
            image_type="SIGNAL",
            caller_action="DISPATCH",
            extracted_text="BUY GOLD 4700-4701 with clear TP and SL",
            image_hash="sum1",
            file_size_kb=5,
            processing_ms=3,
            error=None,
        )
        l.vision = _VisionStub(high)
        msg = self._build_msg(text="BUY GOLD 4700-4701 SL 4695 TP1 4706", has_media=True)
        msg.id = 4122
        msg.chat = _Obj(title="FLAIR FX")
        asyncio.run(l._handle_message(msg))

        assert sent, "Expected LISTENER to send chart analysis summary to Herald"
        assert "SIGNAL ROOM CHART ANALYSIS" in sent[-1]
        assert "FLAIR FX" in sent[-1]
        assert "Message ID" in sent[-1]
        assert any(e.get("event_type") == "SIGNAL_CHART_SUMMARY_SENT" for e in scribe.system_events)

    def test_signal_room_media_is_archived_for_replay(self, monkeypatch, tmp_path):
        l = Listener()
        scribe = _ScribeStub()
        l.scribe = scribe
        l.herald = _Obj(send=lambda *_args, **_kwargs: True)
        l._mode = "SIGNAL"
        l._write_signal = lambda data: None
        l._write_mgmt = lambda data: None
        monkeypatch.setattr(listener_mod, "LISTENER_SIGNAL_MEDIA_ARCHIVE_ENABLED", True)
        monkeypatch.setattr(listener_mod, "LISTENER_SIGNAL_MEDIA_ARCHIVE_DIR", str(tmp_path))
        monkeypatch.setattr(listener_mod, "LISTENER_SIGNAL_MEDIA_SUMMARY_TO_BOT", False)

        async def parse_ok(_text):
            return {
                "type": "ENTRY",
                "direction": "BUY",
                "entry_low": 4700.0,
                "entry_high": 4701.0,
                "sl": 4695.0,
                "tp1": 4706.0,
            }

        l._parse = parse_ok
        high = _Obj(
            structured_data={"type": "ENTRY", "direction": "BUY", "entry_low": 4700.0, "entry_high": 4701.0, "sl": 4695.0, "tp1": 4706.0},
            confidence="HIGH",
            image_type="SIGNAL",
            caller_action="DISPATCH",
            extracted_text="clear setup",
            image_hash="arch1",
            file_size_kb=4,
            processing_ms=2,
            error=None,
        )
        l.vision = _VisionStub(high)
        msg = self._build_msg(text="BUY GOLD 4700-4701 SL 4695 TP1 4706", has_media=True)
        msg.id = 5001
        msg.chat = _Obj(title="FLAIR FX")
        asyncio.run(l._handle_message(msg))

        archived = list(tmp_path.rglob("*.img"))
        meta = list(tmp_path.rglob("*.img.json"))
        assert archived, "Expected archived image file for replay"
        assert meta, "Expected metadata sidecar file for replay"
        assert any(e.get("event_type") == "SIGNAL_CHART_ARCHIVED" for e in scribe.system_events)

    def test_watch_mode_media_still_logs_signal_chart_event(self, monkeypatch):
        l = Listener()
        scribe = _ScribeStub()
        l.scribe = scribe
        l.herald = _Obj(send=lambda *_args, **_kwargs: True)
        l._mode = "WATCH"
        l._write_signal = lambda data: None
        l._write_mgmt = lambda data: None
        monkeypatch.setattr(listener_mod, "VISION_ENABLED", False)

        async def parse_ok(_text):
            return {
                "type": "ENTRY",
                "direction": "BUY",
                "entry_low": 100.0,
                "entry_high": 101.0,
                "sl": 99.0,
                "tp1": 103.0,
            }

        l._parse = parse_ok
        msg = self._build_msg(text="BUY setup", has_media=True)
        asyncio.run(l._handle_message(msg))

        assert any(e.get("event_type") == "SIGNAL_CHART_RECEIVED" for e in scribe.system_events)
        assert scribe.signal_updates
        assert scribe.signal_updates[-1][1] == "LOGGED_ONLY"

    def test_non_priority_room_is_watch_only_in_signal_mode(self, monkeypatch):
        l = Listener()
        scribe = _ScribeStub()
        l.scribe = scribe
        l.herald = _Obj(send=lambda *_args, **_kwargs: True)
        l._mode = "SIGNAL"
        l._write_signal = lambda data: (_ for _ in ()).throw(RuntimeError("should not dispatch"))
        l._write_mgmt = lambda data: None
        monkeypatch.setattr(listener_mod, "VISION_ENABLED", False)
        monkeypatch.setattr(listener_mod, "SIGNAL_TRADE_ROOMS", {"ben's vip club"})

        async def parse_ok(_text):
            return {
                "type": "ENTRY",
                "direction": "BUY",
                "entry_low": 100.0,
                "entry_high": 101.0,
                "sl": 99.0,
                "tp1": 103.0,
            }

        l._parse = parse_ok
        msg = self._build_msg(text="BUY setup", has_media=False)
        msg.chat = _Obj(title="Other Room")
        msg.chat_id = -100999
        asyncio.run(l._handle_message(msg))

        assert scribe.signal_updates
        assert scribe.signal_updates[-1][1] == "WATCH_ONLY"
        assert "ROOM_NOT_PRIORITY" in (scribe.signal_updates[-1][2] or "")
        assert any(e.get("event_type") == "SIGNAL_ROOM_WATCH_ONLY" for e in scribe.system_events)


@pytest.mark.unit
class TestAegisSignalOverrides:
    def _make_aegis(self):
        a = aegis_mod.Aegis.__new__(aegis_mod.Aegis)
        a._get_session_pnl = lambda: 0.0
        a._get_scale_factor = lambda: (1.0, "NORMAL")
        a._check_trend_cascade = lambda direction, source, mt5_data: None
        return a

    def test_signal_rr_override_allows_trade_below_global_min_rr(self, monkeypatch):
        monkeypatch.setattr(aegis_mod, "MIN_RR", 1.2)
        monkeypatch.setattr(aegis_mod, "AEGIS_SIGNAL_MIN_RR", 0.8)
        monkeypatch.setattr(aegis_mod, "MIN_SL_PIPS", 3.0)
        monkeypatch.setattr(aegis_mod, "AEGIS_SIGNAL_MIN_SL_PIPS", 3.0)
        monkeypatch.setattr(aegis_mod, "MAX_SLIPPAGE", 20.0)
        monkeypatch.setattr(aegis_mod, "AEGIS_SIGNAL_MAX_SLIPPAGE", 20.0)
        a = self._make_aegis()
        signal = {
            "source": "SIGNAL",
            "direction": "BUY",
            "entry_low": 100.0,
            "entry_high": 100.0,
            "sl": 96.0,      # SL = 4
            "tp1": 103.6,    # TP = 3.6 => RR = 0.9
            "lot_per_trade": 0.01,
            "num_trades": 2,
        }
        account = {"balance": 10000.0, "open_groups_count": 0}
        approval = a.validate(signal, account, current_price=100.0, mt5_data=None)
        assert approval.approved is True

    def test_non_signal_still_uses_global_rr(self, monkeypatch):
        monkeypatch.setattr(aegis_mod, "MIN_RR", 1.2)
        monkeypatch.setattr(aegis_mod, "AEGIS_SIGNAL_MIN_RR", 0.8)
        monkeypatch.setattr(aegis_mod, "MIN_SL_PIPS", 3.0)
        monkeypatch.setattr(aegis_mod, "AEGIS_SIGNAL_MIN_SL_PIPS", 3.0)
        monkeypatch.setattr(aegis_mod, "MAX_SLIPPAGE", 20.0)
        monkeypatch.setattr(aegis_mod, "AEGIS_SIGNAL_MAX_SLIPPAGE", 20.0)
        a = self._make_aegis()
        signal = {
            "source": "AURUM",
            "direction": "BUY",
            "entry_low": 100.0,
            "entry_high": 100.0,
            "sl": 96.0,
            "tp1": 103.6,    # RR = 0.9 < global 1.2
            "lot_per_trade": 0.01,
            "num_trades": 2,
        }
        account = {"balance": 10000.0, "open_groups_count": 0}
        approval = a.validate(signal, account, current_price=100.0, mt5_data=None)
        assert approval.approved is False
        assert "LOW_RR" in approval.reject_reason


@pytest.mark.unit
class TestAurumImageHelper:
    def test_message_has_media_detects_effective_attachment(self):
        msg = _Obj(photo=None, document=None, effective_attachment=object(), animation=None, video=None)
        assert Aurum._message_has_media(msg) is True

    def test_response_claims_no_image_detection(self):
        assert Aurum._response_claims_no_image("Still no image attached, Captain!") is True
        assert Aurum._response_claims_no_image("I received the image and extracted levels.") is False
    def test_reply_with_optional_image_low_confidence(self):
        a = Aurum()
        a.scribe = _ScribeStub()
        low = _Obj(
            structured_data={"type": "ENTRY"},
            confidence="LOW",
            image_type="SIGNAL",
            caller_action="HOLD",
            extracted_text="unclear",
            image_hash="h",
            file_size_kb=1,
            processing_ms=1,
            error=None,
        )
        a.vision = _VisionStub(low)
        a.ask = lambda query, source="TELEGRAM", extra_context="": "should-not-be-used"
        out = a._reply_with_optional_image(
            query="analyze", caption="", image_path="/tmp/fake.png", source="TELEGRAM"
        )
        assert "confidence is LOW" in out
        assert a.scribe.vision_updates[-1][1] == "LOW_CONFIDENCE"

    def test_reply_with_optional_image_high_confidence_injects_context(self):
        a = Aurum()
        a.scribe = _ScribeStub()
        high = _Obj(
            structured_data={"type": "ENTRY", "direction": "BUY"},
            confidence="HIGH",
            image_type="SIGNAL",
            caller_action="DISPATCH",
            extracted_text="clear setup",
            image_hash="z",
            file_size_kb=1,
            processing_ms=1,
            error=None,
        )
        a.vision = _VisionStub(high)
        calls = {}

        def ask_spy(query, source="TELEGRAM", extra_context=""):
            calls["query"] = query
            calls["extra"] = extra_context
            return "ok"

        a.ask = ask_spy
        out = a._reply_with_optional_image(
            query="analyze", caption="cap", image_path="/tmp/fake.png", source="TELEGRAM"
        )
        assert out == "ok"
        assert "IMAGE EXTRACTION (VISION)" in calls["extra"]

    def test_reply_with_optional_image_fallback_when_model_claims_no_image(self):
        a = Aurum()
        a.scribe = _ScribeStub()
        high = _Obj(
            structured_data={"type": "ENTRY", "direction": "BUY"},
            confidence="HIGH",
            image_type="SIGNAL",
            caller_action="DISPATCH",
            extracted_text="BUY setup around 4754.54 with support 4746.57",
            image_hash="z",
            file_size_kb=1,
            processing_ms=1,
            error=None,
        )
        a.vision = _VisionStub(high)
        a.ask = lambda *_args, **_kwargs: "Still no image attached, Captain! ☠️"
        out = a._reply_with_optional_image(
            query="analyze", caption="cap", image_path="/tmp/fake.png", source="TELEGRAM"
        )
        assert "Image received and parsed (HIGH)." in out
        assert "BUY setup around 4754.54" in out


@pytest.mark.unit
class TestHeraldInboundMedia:
    def test_download_inbound_media_fallbacks_to_bot_get_file(self):
        class _File:
            async def download(self, custom_path):
                Image.new("RGB", (8, 8), "white").save(custom_path, format="PNG")

        class _Bot:
            async def get_file(self, file_id):
                assert file_id == "file-123"
                return _File()

        class _Doc:
            file_id = "file-123"

        class _Msg:
            document = _Doc()
            photo = None
            effective_attachment = None

            def get_bot(self):
                return _Bot()

        h = Herald()
        out = asyncio.run(h.download_inbound_media(_Msg(), prefix="t_img_"))
        assert out is not None
        assert Path(out).exists()
        Path(out).unlink(missing_ok=True)
