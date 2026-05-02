"""
test_mgmt_channel_scoping.py — Channel management commands must NOT affect non-SIGNAL groups.

Root cause (fixed in v1.4.0): Telegram channel messages like "close all" and "move to BE"
from LISTENER were applying CLOSE_ALL/MOVE_BE_ALL globally — closing AURUM trades,
FORGE native scalper trades, and any other non-channel positions.

Fix: Channel commands are scoped to SIGNAL-source groups only.
ATHENA/AURUM commands still affect all positions (intentional).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def _make_bridge_stub(monkeypatch, tmp_path, open_groups=None):
    """Create a Bridge stub with monkeypatched file paths and mock methods."""
    import bridge as bm

    mgmt_path = tmp_path / "management_cmd.json"
    monkeypatch.setattr(bm, "MGMT_FILE", str(mgmt_path))

    stub = MagicMock()
    stub._last_mgmt_ts = None
    stub._open_groups = open_groups or {}
    stub.scribe = MagicMock()
    stub.scribe.get_open_groups.return_value = [
        {"id": gid, **g} for gid, g in (open_groups or {}).items()
    ]
    stub.scribe.get_open_positions_by_group.return_value = []
    signal_gids = sorted(
        [int(gid) for gid, g in (open_groups or {}).items() if g.get("source") == "SIGNAL"],
        reverse=True,
    )

    def _query(sql, params=()):
        sql = sql or ""
        if "SELECT trade_group_id FROM signals_received WHERE id=?" in sql:
            return []
        if "SELECT DISTINCT tg.id FROM trade_groups tg" in sql:
            return [{"id": gid} for gid in signal_gids]
        if "SELECT tg.id FROM trade_groups tg" in sql:
            return [{"id": signal_gids[0]}] if signal_gids else []
        return []

    stub.scribe.query.side_effect = _query
    stub.herald = MagicMock()
    stub._lookup_group_magic = lambda gid: 202401 + gid
    stub._bridge_activity = MagicMock()
    stub._resolve_channel_group = bm.Bridge._resolve_channel_group.__get__(stub)
    stub._resolve_channel_open_groups = bm.Bridge._resolve_channel_open_groups.__get__(stub)
    stub._effective_mode = lambda: "SIGNAL"

    return stub, mgmt_path, bm


def _write_mgmt(path, intent, source="LISTENER", channel="Ben's VIP Club",
                group_id=None, signal_id=None, **extra):
    """Write a management_cmd.json like LISTENER or ATHENA would."""
    data = {
        "type": "MANAGEMENT",
        "intent": intent,
        "source": source,
        "channel": channel,
        "group_id": group_id,
        "signal_id": signal_id,
        "timestamp": "2099-01-01T00:00:00+00:00",
        **extra,
    }
    path.write_text(json.dumps(data), encoding="utf-8")


# ── Channel CLOSE_ALL should NOT close AURUM/FORGE groups ─────────

@pytest.mark.unit
def test_channel_close_all_only_closes_signal_groups(monkeypatch, tmp_path):
    """Channel 'close all' must only close source=SIGNAL groups, not AURUM."""
    groups = {
        10: {"source": "SIGNAL", "direction": "BUY"},
        11: {"source": "AURUM", "direction": "SELL"},
        12: {"source": "FORGE_NATIVE_SCALP", "direction": "BUY"},
    }
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)
    _write_mgmt(mgmt_path, "CLOSE_ALL", source="LISTENER")

    with patch.object(bm, "_write_forge_command") as mock_forge:
        bm.Bridge._process_mgmt_command(stub, {})

    # Only G10 (SIGNAL) should be closed — G11 (AURUM) and G12 (FORGE) untouched
    stub.scribe.update_trade_group.assert_called_once()
    call_args = stub.scribe.update_trade_group.call_args
    assert call_args[0][0] == 10  # group_id
    assert "CLOSED" in call_args[0][1]  # status


@pytest.mark.unit
def test_channel_close_all_does_not_send_global_close_all(monkeypatch, tmp_path):
    """Channel 'close all' must NOT send FORGE CLOSE_ALL (which kills everything)."""
    groups = {
        10: {"source": "SIGNAL", "direction": "BUY"},
        11: {"source": "AURUM", "direction": "SELL"},
    }
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)
    _write_mgmt(mgmt_path, "CLOSE_ALL", source="LISTENER")

    with patch.object(bm, "_write_forge_command") as mock_forge:
        bm.Bridge._process_mgmt_command(stub, {})

    # Should use CLOSE_GROUP (targeted), never CLOSE_ALL (global)
    for c in mock_forge.call_args_list:
        cmd = c[0][0]
        assert cmd.get("action") != "CLOSE_ALL", \
            f"Channel CLOSE_ALL must not send global CLOSE_ALL to FORGE: {cmd}"


@pytest.mark.unit
def test_athena_close_all_still_closes_everything(monkeypatch, tmp_path):
    """Dashboard CLOSE_ALL should still close all groups (intentional)."""
    groups = {
        10: {"source": "SIGNAL", "direction": "BUY"},
        11: {"source": "AURUM", "direction": "SELL"},
    }
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)
    _write_mgmt(mgmt_path, "CLOSE_ALL", source="ATHENA", channel="")

    with patch.object(bm, "_write_forge_command") as mock_forge:
        bm.Bridge._process_mgmt_command(stub, {})

    # ATHENA CLOSE_ALL sends global CLOSE_ALL
    forge_cmds = [c[0][0] for c in mock_forge.call_args_list]
    actions = [c.get("action") for c in forge_cmds]
    assert "CLOSE_ALL" in actions, "ATHENA CLOSE_ALL should send global CLOSE_ALL"


# ── Channel MOVE_BE should NOT move BE on AURUM/FORGE groups ──────

@pytest.mark.unit
def test_channel_move_be_does_not_send_global_move_be_all(monkeypatch, tmp_path):
    """Channel 'move to BE' must NOT send MOVE_BE_ALL (which affects everything)."""
    groups = {
        10: {"source": "SIGNAL", "direction": "BUY"},
        11: {"source": "AURUM", "direction": "SELL"},
    }
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)
    _write_mgmt(mgmt_path, "MOVE_BE", source="LISTENER")

    with patch.object(bm, "_write_forge_command") as mock_forge:
        bm.Bridge._process_mgmt_command(stub, {})

    for c in mock_forge.call_args_list:
        cmd = c[0][0]
        assert cmd.get("action") != "MOVE_BE_ALL", \
            f"Channel MOVE_BE must not send global MOVE_BE_ALL: {cmd}"


@pytest.mark.unit
def test_athena_move_be_still_moves_all(monkeypatch, tmp_path):
    """Dashboard MOVE_BE should still move BE on all positions."""
    groups = {10: {"source": "SIGNAL", "direction": "BUY"}}
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)
    _write_mgmt(mgmt_path, "MOVE_BE", source="ATHENA", channel="")

    with patch.object(bm, "_write_forge_command") as mock_forge:
        bm.Bridge._process_mgmt_command(stub, {})

    forge_cmds = [c[0][0] for c in mock_forge.call_args_list]
    actions = [c.get("action") for c in forge_cmds]
    assert "MOVE_BE_ALL" in actions, "ATHENA MOVE_BE should send global MOVE_BE_ALL"


# ── Channel with group_id should scope to that specific group ─────

@pytest.mark.unit
def test_channel_close_all_with_group_id_scopes_to_group(monkeypatch, tmp_path):
    """If LISTENER provides group_id, CLOSE_ALL → CLOSE_GROUP for that group only."""
    groups = {
        10: {"source": "SIGNAL", "direction": "BUY"},
        11: {"source": "SIGNAL", "direction": "SELL"},
    }
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)
    _write_mgmt(mgmt_path, "CLOSE_ALL", source="LISTENER", group_id=10)

    with patch.object(bm, "_write_forge_command") as mock_forge:
        bm.Bridge._process_mgmt_command(stub, {})

    # Only G10 should be closed
    stub.scribe.update_trade_group.assert_called_once()
    assert stub.scribe.update_trade_group.call_args[0][0] == 10

@pytest.mark.unit
def test_channel_modify_sl_without_scope_is_dropped(monkeypatch, tmp_path):
    """LISTENER MODIFY_SL with no group/ticket/stage must not reach FORGE."""
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, {})
    stub._sync_modify_targets = MagicMock()
    _write_mgmt(mgmt_path, "MODIFY_SL", source="LISTENER", sl=4660.0)

    with (
        patch.object(bm, "_write_forge_command") as mock_forge,
        patch.object(bm, "_tlog") as mock_tlog,
    ):
        bm.Bridge._process_mgmt_command(stub, {})

    stub._enqueue_forge_command.assert_not_called()
    mock_forge.assert_not_called()
    stub._sync_modify_targets.assert_not_called()
    mock_tlog.assert_any_call(
        "MGMT",
        "MODIFY_SL_IGNORED",
        "channel Ben's VIP Club — no resolved scope found",
        level="warning",
    )


@pytest.mark.unit
def test_channel_modify_sl_with_group_id_is_written(monkeypatch, tmp_path):
    """LISTENER MODIFY_SL with resolved group_id should emit magic-scoped command."""
    groups = {10: {"source": "SIGNAL", "direction": "BUY"}}
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)
    stub._sync_modify_targets = MagicMock()
    stub._build_ticket_sl_verifier = bm.Bridge._build_ticket_sl_verifier
    _write_mgmt(mgmt_path, "MODIFY_SL", source="LISTENER", group_id=10, sl=4660.0)

    bm.Bridge._process_mgmt_command(stub, {})

    stub._enqueue_forge_command.assert_called_once()
    cmd = stub._enqueue_forge_command.call_args[0][0]
    assert cmd == {"action": "MODIFY_SL", "sl": 4660.0, "magic": 202411}
    assert stub._enqueue_forge_command.call_args.kwargs.get("verifier") is None
    stub._sync_modify_targets.assert_called_once_with(
        10, sl=4660.0, tp=None, ticket=None, tp_stage=None,
    )


@pytest.mark.unit
def test_channel_modify_tp_without_scope_is_dropped(monkeypatch, tmp_path):
    """LISTENER MODIFY_TP with no group/ticket/stage must not reach FORGE."""
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, {})
    stub._sync_modify_targets = MagicMock()
    _write_mgmt(mgmt_path, "MODIFY_TP", source="LISTENER", tp=4660.0)

    with (
        patch.object(bm, "_write_forge_command") as mock_forge,
        patch.object(bm, "_tlog") as mock_tlog,
    ):
        bm.Bridge._process_mgmt_command(stub, {})

    stub._enqueue_forge_command.assert_not_called()
    mock_forge.assert_not_called()
    stub._sync_modify_targets.assert_not_called()
    mock_tlog.assert_any_call(
        "MGMT",
        "MODIFY_TP_IGNORED",
        "channel Ben's VIP Club — no resolved scope found",
        level="warning",
    )


@pytest.mark.unit
def test_aurum_modify_sl_without_scope_is_not_dropped_by_channel_guard(monkeypatch, tmp_path):
    """AURUM-origin MODIFY_SL is not a channel command, so this guard must not drop it."""
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, {})
    stub._sync_modify_targets = MagicMock()
    stub._build_ticket_sl_verifier = bm.Bridge._build_ticket_sl_verifier
    _write_mgmt(mgmt_path, "MODIFY_SL", source="AURUM", channel="", sl=4660.0)

    bm.Bridge._process_mgmt_command(stub, {})

    stub._enqueue_forge_command.assert_called_once()
    cmd = stub._enqueue_forge_command.call_args[0][0]
    assert cmd == {"action": "MODIFY_SL", "sl": 4660.0}
    stub._sync_modify_targets.assert_called_once_with(
        None, sl=4660.0, tp=None, ticket=None, tp_stage=None,
    )


@pytest.mark.unit
def test_channel_modify_tp_with_group_id_scopes_to_group_magic(monkeypatch, tmp_path):
    """LISTENER MODIFY_TP with group_id should emit magic-scoped FORGE command."""
    groups = {
        10: {"source": "SIGNAL", "direction": "BUY"},
        11: {"source": "AURUM", "direction": "SELL"},
    }
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)
    stub._sync_modify_targets = MagicMock()
    stub._build_ticket_tp_verifier = bm.Bridge._build_ticket_tp_verifier
    _write_mgmt(mgmt_path, "MODIFY_TP", source="LISTENER", group_id=10, tp=4755.3)

    bm.Bridge._process_mgmt_command(stub, {})

    stub._enqueue_forge_command.assert_called_once()
    cmd = stub._enqueue_forge_command.call_args[0][0]
    assert cmd["action"] == "MODIFY_TP"
    assert cmd["tp"] == 4755.3
    assert cmd["magic"] == 202411
    # Legacy unscoped path: no per-leg keys leak into the FORGE command.
    assert "ticket" not in cmd
    assert "tp_stage" not in cmd
    # Group-wide modify (no ticket): no verifier needed; queue uses 1-tick spacing.
    assert stub._enqueue_forge_command.call_args.kwargs.get("verifier") is None


@pytest.mark.unit
def test_channel_modify_tp_forwards_stage_and_ticket(monkeypatch, tmp_path):
    """LISTENER MODIFY_TP with ticket+tp_stage scope is preserved end-to-end."""
    groups = {10: {"source": "SIGNAL", "direction": "BUY"}}
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)
    stub._sync_modify_targets = MagicMock()
    stub._build_ticket_tp_verifier = bm.Bridge._build_ticket_tp_verifier
    _write_mgmt(
        mgmt_path,
        "MODIFY_TP",
        source="LISTENER",
        group_id=10,
        tp=4648.0,
        ticket=1122706681,
        tp_stage=1,
    )

    bm.Bridge._process_mgmt_command(stub, {})

    stub._enqueue_forge_command.assert_called_once()
    cmd = stub._enqueue_forge_command.call_args[0][0]
    assert cmd["action"] == "MODIFY_TP"
    assert cmd["tp"] == 4648.0
    assert cmd["magic"] == 202411
    assert cmd["ticket"] == 1122706681
    assert cmd["tp_stage"] == 1
    # Ticket-scoped modify must come with a verifier so the queue confirms
    # FORGE applied the change before advancing.
    assert callable(stub._enqueue_forge_command.call_args.kwargs.get("verifier"))
    stub._sync_modify_targets.assert_called_once_with(
        10, sl=None, tp=4648.0, ticket=1122706681, tp_stage=1,
    )


# ── _resolve_channel_group finds the right group ─────────────────

@pytest.mark.unit
def test_resolve_channel_group_by_signal_id(monkeypatch, tmp_path):
    """If LISTENER provides signal_id, resolve to its trade_group_id."""
    groups = {10: {"source": "SIGNAL"}, 11: {"source": "AURUM"}}
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)
    stub.scribe.query.return_value = [{"trade_group_id": 10}]

    result = stub._resolve_channel_group({"signal_id": 42, "channel": "Test"})
    assert result == 10


@pytest.mark.unit
def test_resolve_channel_group_scopes_to_channel_signal_group(monkeypatch, tmp_path):
    """Without signal_id, resolve to most recent channel-scoped SIGNAL group."""
    groups = {
        8: {"source": "SIGNAL"},
        9: {"source": "AURUM"},
        10: {"source": "SIGNAL"},
    }
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)
    stub.scribe.query.return_value = []  # no signal_id match

    result = stub._resolve_channel_group({"channel": "Test"})
    assert result == 10


@pytest.mark.unit
def test_resolve_channel_group_returns_none_if_no_signal_groups(monkeypatch, tmp_path):
    """If no SIGNAL groups are open, returns None."""
    groups = {9: {"source": "AURUM"}, 10: {"source": "FORGE_NATIVE_SCALP"}}
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)
    stub.scribe.query.return_value = []

    result = stub._resolve_channel_group({"channel": "Test"})
    assert result is None


@pytest.mark.unit
def test_channel_close_all_ignored_when_no_scoped_groups(monkeypatch, tmp_path):
    """If channel has no scoped SIGNAL groups, channel CLOSE_ALL should be ignored."""
    groups = {11: {"source": "AURUM", "direction": "SELL"}}
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)
    _write_mgmt(mgmt_path, "CLOSE_ALL", source="LISTENER", channel="Unknown Channel")

    with patch.object(bm, "_write_forge_command") as mock_forge:
        bm.Bridge._process_mgmt_command(stub, {})

    mock_forge.assert_not_called()
    stub.scribe.update_trade_group.assert_not_called()


# ── Source field detection ────────────────────────────────────────

@pytest.mark.unit
def test_listener_source_detected_as_channel(monkeypatch, tmp_path):
    """LISTENER commands (source != ATHENA/AURUM) are treated as channel commands."""
    groups = {10: {"source": "SIGNAL"}, 11: {"source": "AURUM"}}
    stub, mgmt_path, bm = _make_bridge_stub(monkeypatch, tmp_path, groups)

    # Test various LISTENER source values
    for source in ["LISTENER", "", None, "CHANNEL", "Ben's VIP Club"]:
        _write_mgmt(mgmt_path, "CLOSE_ALL", source=source or "", channel="Test")
        stub._last_mgmt_ts = None  # reset dedup

        with patch.object(bm, "_write_forge_command"):
            bm.Bridge._process_mgmt_command(stub, {})

        # Should NOT have sent global CLOSE_ALL (only ATHENA/AURUM can do that)
        # The scoped behavior is what we're testing
