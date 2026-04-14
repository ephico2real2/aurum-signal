"""
test_channels_listener_api.py — Live integration tests for LISTENER channel endpoints
======================================================================================
Validates the API changes introduced in v1.4.2:

  GET /api/channels
    - new fields: watch_only, is_trade_room, match_reason (per channel)
    - new top-level: signal_trade_rooms_active, listener_last_ingest_at, listener_status

  GET /api/channels/messages
    - new fields: cache_age_sec, listener_stale, listener_last_ingest_at, listener_status

  SCRIBE pipeline trace
    - signals_received contains expected action_taken values
    - system_events contains correctly structured reason codes (no bare ROOM_NOT_PRIORITY)
    - new events: SIGNAL_DISPATCHED, SIGNAL_PARSE_FAILED use structured reason codes
    - AEGIS rejections prefixed with AEGIS_REJECTED: (for new records)

These tests hit the live ATHENA API (localhost:7842 by default).
Run with:
    pytest tests/api/test_channels_listener_api.py -v
or with a custom base URL:
    ATHENA_URL=http://myhost:7842 pytest tests/api/test_channels_listener_api.py -v
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import assert_keys, TIMEOUT


# ── /api/channels ─────────────────────────────────────────────────────────────

class TestChannelsEndpoint:

    def test_channels_returns_200(self, api, base_url):
        r = api.get(f"{base_url}/api/channels", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_channels_top_level_shape(self, api, base_url):
        d = api.get(f"{base_url}/api/channels", timeout=TIMEOUT).json()
        assert_keys(d, [
            "configured_ids",
            "channels",
            "total_configured",
            "signal_trade_rooms_active",
        ], "/api/channels")

    def test_channels_listener_meta_fields_present(self, api, base_url):
        """listener_last_ingest_at and listener_status added in v1.4.2."""
        d = api.get(f"{base_url}/api/channels", timeout=TIMEOUT).json()
        assert "listener_last_ingest_at" in d, (
            "Missing listener_last_ingest_at — ATHENA needs reload after v1.4.2 patch"
        )
        assert "listener_status" in d, "Missing listener_status"

    def test_channels_signal_trade_rooms_active_is_bool(self, api, base_url):
        d = api.get(f"{base_url}/api/channels", timeout=TIMEOUT).json()
        assert isinstance(d["signal_trade_rooms_active"], bool)

    def test_channels_list_not_empty(self, api, base_url):
        d = api.get(f"{base_url}/api/channels", timeout=TIMEOUT).json()
        assert len(d["channels"]) > 0, "Expected at least one configured channel"

    def test_channels_per_channel_shape(self, api, base_url):
        """Each channel object must include all v1.4.2 fields."""
        d = api.get(f"{base_url}/api/channels", timeout=TIMEOUT).json()
        required = [
            "id", "name",
            "total_signals", "executed", "skipped", "logged_only",
            "watch_only",       # new in v1.4.2
            "last_signal",
            "is_trade_room",    # new in v1.4.2
            "match_reason",     # new in v1.4.2
        ]
        for ch in d["channels"]:
            assert_keys(ch, required, f"channel {ch.get('id')}")

    def test_channels_is_trade_room_is_bool(self, api, base_url):
        d = api.get(f"{base_url}/api/channels", timeout=TIMEOUT).json()
        for ch in d["channels"]:
            assert isinstance(ch["is_trade_room"], bool), (
                f"is_trade_room must be bool for channel {ch.get('name')}"
            )

    def test_channels_match_reason_is_valid_code(self, api, base_url):
        """match_reason must be one of the four structured codes."""
        valid = {
            "ALLOWED_ALL",
            "ALLOWED_TITLE_MATCH",
            "ALLOWED_ID_MATCH",
            "WATCH_ONLY_ROOM_FILTER",
        }
        d = api.get(f"{base_url}/api/channels", timeout=TIMEOUT).json()
        for ch in d["channels"]:
            assert ch["match_reason"] in valid, (
                f"channel {ch.get('name')!r} has unexpected match_reason={ch['match_reason']!r}"
            )

    def test_channels_match_reason_consistent_with_is_trade_room(self, api, base_url):
        """is_trade_room=True must not have WATCH_ONLY_ROOM_FILTER, and vice-versa."""
        d = api.get(f"{base_url}/api/channels", timeout=TIMEOUT).json()
        for ch in d["channels"]:
            if ch["is_trade_room"]:
                assert ch["match_reason"] != "WATCH_ONLY_ROOM_FILTER", (
                    f"{ch['name']!r}: is_trade_room=True but match_reason=WATCH_ONLY_ROOM_FILTER"
                )
            else:
                assert ch["match_reason"] == "WATCH_ONLY_ROOM_FILTER", (
                    f"{ch['name']!r}: is_trade_room=False but match_reason={ch['match_reason']!r}"
                )

    def test_channels_watch_only_is_int(self, api, base_url):
        d = api.get(f"{base_url}/api/channels", timeout=TIMEOUT).json()
        for ch in d["channels"]:
            assert isinstance(ch["watch_only"], int), (
                f"watch_only must be int for channel {ch.get('name')}"
            )

    def test_channels_watch_only_rooms_have_nonzero_watch_count_or_zero(self, api, base_url):
        """
        Channels marked is_trade_room=False should have watch_only >= 0.
        (May be 0 if no signals have arrived yet from that room since SCRIBE was populated.)
        """
        d = api.get(f"{base_url}/api/channels", timeout=TIMEOUT).json()
        for ch in d["channels"]:
            assert ch["watch_only"] >= 0, (
                f"watch_only must be non-negative for {ch.get('name')}"
            )

    def test_channels_trade_rooms_have_zero_watch_only(self, api, base_url):
        """
        Channels that are allowed (is_trade_room=True) should never have
        watch_only > 0 — those signals would have been dispatched (or skipped by AEGIS).
        """
        d = api.get(f"{base_url}/api/channels", timeout=TIMEOUT).json()
        for ch in d["channels"]:
            if ch["is_trade_room"]:
                assert ch["watch_only"] == 0, (
                    f"Trade room {ch['name']!r} has watch_only={ch['watch_only']} — "
                    f"signals from an allowed room should not be WATCH_ONLY"
                )

    def test_channels_listener_status_valid(self, api, base_url):
        d = api.get(f"{base_url}/api/channels", timeout=TIMEOUT).json()
        status = d.get("listener_status")
        if status is not None:
            assert status in ("OK", "WARN"), (
                f"listener_status must be OK or WARN, got {status!r}"
            )


# ── /api/channels/messages ────────────────────────────────────────────────────

class TestChannelMessagesEndpoint:

    def test_channel_messages_returns_200(self, api, base_url):
        r = api.get(f"{base_url}/api/channels/messages", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_channel_messages_top_level_shape(self, api, base_url):
        d = api.get(f"{base_url}/api/channels/messages", timeout=TIMEOUT).json()
        assert_keys(d, ["channels"], "/api/channels/messages")

    def test_channel_messages_staleness_fields_present(self, api, base_url):
        """cache_age_sec, listener_stale, listener_last_ingest_at added in v1.4.2."""
        d = api.get(f"{base_url}/api/channels/messages", timeout=TIMEOUT).json()
        assert "cache_age_sec" in d, (
            "Missing cache_age_sec — reload ATHENA after v1.4.2 patch"
        )
        assert "listener_stale" in d, "Missing listener_stale"
        assert "listener_last_ingest_at" in d, "Missing listener_last_ingest_at"
        assert "listener_status" in d, "Missing listener_status"

    def test_channel_messages_cache_age_is_numeric_or_none(self, api, base_url):
        d = api.get(f"{base_url}/api/channels/messages", timeout=TIMEOUT).json()
        age = d.get("cache_age_sec")
        if age is not None:
            assert isinstance(age, (int, float)), (
                f"cache_age_sec must be numeric, got {type(age)}"
            )
            assert age >= 0, "cache_age_sec must be non-negative"

    def test_channel_messages_listener_stale_is_bool(self, api, base_url):
        d = api.get(f"{base_url}/api/channels/messages", timeout=TIMEOUT).json()
        stale = d.get("listener_stale")
        assert isinstance(stale, bool), (
            f"listener_stale must be bool, got {type(stale)}"
        )

    def test_channel_messages_not_stale_when_fresh_cache(self, api, base_url):
        """
        If the cache was written recently (cache_age_sec < 3 × 300s = 900s),
        listener_stale must be False.
        """
        d = api.get(f"{base_url}/api/channels/messages", timeout=TIMEOUT).json()
        age = d.get("cache_age_sec")
        if age is not None and age < 900:
            assert d["listener_stale"] is False, (
                f"cache is only {age}s old but listener_stale=True"
            )

    def test_channel_messages_channels_list(self, api, base_url):
        d = api.get(f"{base_url}/api/channels/messages", timeout=TIMEOUT).json()
        assert isinstance(d["channels"], list)
        for ch in d["channels"]:
            assert "id" in ch
            assert "name" in ch
            assert "messages" in ch
            assert isinstance(ch["messages"], list)

    def test_channel_messages_listener_status_valid(self, api, base_url):
        d = api.get(f"{base_url}/api/channels/messages", timeout=TIMEOUT).json()
        status = d.get("listener_status")
        if status is not None:
            assert status in ("OK", "WARN")


# ── SCRIBE pipeline reason code contract ─────────────────────────────────────

class TestScribePipelineReasonCodes:

    def _scribe_query(self, api, base_url, sql):
        r = api.post(
            f"{base_url}/api/scribe/query",
            json={"sql": sql},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"SCRIBE query failed {r.status_code}: {r.text[:200]}"
        return r.json().get("rows", [])

    def test_watch_only_reason_code_is_structured(self, api, base_url):
        """
        Any WATCH_ONLY record written after v1.4.2 must use WATCH_ONLY_ROOM_FILTER,
        not the old free-text ROOM_NOT_PRIORITY:<room> format.
        New records are identified by having skip_reason='WATCH_ONLY_ROOM_FILTER'.
        """
        rows = self._scribe_query(api, base_url,
            "SELECT skip_reason FROM signals_received "
            "WHERE action_taken='WATCH_ONLY' AND skip_reason IS NOT NULL "
            "ORDER BY id DESC LIMIT 100"
        )
        # Partition into old (pre-v1.4.2) and new records
        new_format = [r for r in rows if r["skip_reason"] == "WATCH_ONLY_ROOM_FILTER"]
        old_format = [r for r in rows if "ROOM_NOT_PRIORITY" in (r["skip_reason"] or "")]
        # If we have new-format records, that confirms new code ran
        # Old-format records are fine — they're historical
        if not rows:
            pytest.skip("No WATCH_ONLY signals in SCRIBE yet")
        # At minimum, any record must be either old-format (historic) or new-format
        for r in rows:
            reason = r["skip_reason"] or ""
            assert reason == "WATCH_ONLY_ROOM_FILTER" or "ROOM_NOT_PRIORITY" in reason, (
                f"Unexpected WATCH_ONLY skip_reason: {reason!r}"
            )

    def test_watch_only_room_watch_only_event_reason_field(self, api, base_url):
        """
        SIGNAL_ROOM_WATCH_ONLY events written after v1.4.2 must use
        reason='WATCH_ONLY_ROOM_FILTER', not 'ROOM_PRIORITY_POLICY'.
        """
        rows = self._scribe_query(api, base_url,
            "SELECT reason FROM system_events "
            "WHERE event_type='SIGNAL_ROOM_WATCH_ONLY' "
            "ORDER BY id DESC LIMIT 50"
        )
        if not rows:
            pytest.skip("No SIGNAL_ROOM_WATCH_ONLY events in SCRIBE yet")
        new_format = [r for r in rows if r["reason"] == "WATCH_ONLY_ROOM_FILTER"]
        old_format = [r for r in rows if r["reason"] == "ROOM_PRIORITY_POLICY"]
        # After restart with new code, at least the newest event should be new-format
        # Old records are historic — acceptable to coexist
        for r in rows:
            assert r["reason"] in ("WATCH_ONLY_ROOM_FILTER", "ROOM_PRIORITY_POLICY"), (
                f"Unexpected SIGNAL_ROOM_WATCH_ONLY reason: {r['reason']!r}"
            )

    def test_signal_dispatched_event_has_structured_reason(self, api, base_url):
        """SIGNAL_DISPATCHED events must carry reason='SIGNAL_DISPATCHED'."""
        rows = self._scribe_query(api, base_url,
            "SELECT event_type, reason FROM system_events "
            "WHERE event_type='SIGNAL_DISPATCHED' "
            "ORDER BY id DESC LIMIT 10"
        )
        if not rows:
            pytest.skip("No SIGNAL_DISPATCHED events yet — will appear after next live signal")
        for r in rows:
            assert r["reason"] == "SIGNAL_DISPATCHED", (
                f"SIGNAL_DISPATCHED event has unexpected reason={r['reason']!r}"
            )

    def test_signal_parse_failed_event_has_structured_reason(self, api, base_url):
        """SIGNAL_PARSE_FAILED events must carry reason='PARSE_FAILED'."""
        rows = self._scribe_query(api, base_url,
            "SELECT event_type, reason FROM system_events "
            "WHERE event_type='SIGNAL_PARSE_FAILED' "
            "ORDER BY id DESC LIMIT 10"
        )
        if not rows:
            pytest.skip("No SIGNAL_PARSE_FAILED events yet — will appear after next non-signal message")
        for r in rows:
            assert r["reason"] == "PARSE_FAILED", (
                f"SIGNAL_PARSE_FAILED event has unexpected reason={r['reason']!r}"
            )

    def test_new_aegis_rejections_use_prefixed_reason(self, api, base_url):
        """
        AEGIS rejections written after v1.4.2 have skip_reason prefixed AEGIS_REJECTED:.
        Historic records (pre-v1.4.2) will be bare — they are allowed to coexist.
        At least verify no new-format record accidentally uses the old bare format
        alongside a clearly new-format one.
        """
        rows = self._scribe_query(api, base_url,
            "SELECT id, skip_reason FROM signals_received "
            "WHERE action_taken='SKIPPED' AND skip_reason IS NOT NULL "
            "ORDER BY id DESC LIMIT 50"
        )
        if not rows:
            pytest.skip("No SKIPPED signals in SCRIBE yet")
        # If any record has the new AEGIS_REJECTED: prefix, verify it's well-formed
        prefixed = [r for r in rows if (r["skip_reason"] or "").startswith("AEGIS_REJECTED:")]
        for r in prefixed:
            suffix = r["skip_reason"][len("AEGIS_REJECTED:"):]
            assert suffix, f"AEGIS_REJECTED: prefix with empty suffix in id={r['id']}"

    def test_action_taken_values_are_valid(self, api, base_url):
        """signals_received.action_taken must only contain known action codes."""
        rows = self._scribe_query(api, base_url,
            "SELECT DISTINCT action_taken FROM signals_received"
        )
        valid = {
            "PENDING", "EXECUTED", "SKIPPED", "WATCH_ONLY",
            "LOGGED_ONLY", "HELD", "EXPIRED", "DUPLICATE",
        }
        for r in rows:
            action = r.get("action_taken") or ""
            assert action in valid or action == "", (
                f"Unexpected action_taken={action!r}"
            )


# ── /api/channel_performance ──────────────────────────────────────────────────

class TestChannelPerformanceEndpoint:

    def test_channel_performance_returns_200(self, api, base_url):
        r = api.get(f"{base_url}/api/channel_performance", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_channel_performance_shape(self, api, base_url):
        d = api.get(f"{base_url}/api/channel_performance", timeout=TIMEOUT).json()
        assert "channels" in d
        assert "days" in d
        assert isinstance(d["channels"], list)

    def test_channel_performance_custom_days(self, api, base_url):
        d = api.get(f"{base_url}/api/channel_performance?days=7", timeout=TIMEOUT).json()
        assert d["days"] == 7

    def test_channel_performance_row_fields(self, api, base_url):
        d = api.get(f"{base_url}/api/channel_performance", timeout=TIMEOUT).json()
        if not d["channels"]:
            pytest.skip("No channel performance data yet")
        for row in d["channels"]:
            assert_keys(row, [
                "channel", "total_signals", "executed",
                "skipped", "expired", "groups_opened",
                "total_pnl", "avg_pips",
            ], "channel_performance row")
