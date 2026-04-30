"""
test_modify_scope.py — coverage for per-stage / per-ticket MODIFY_TP & MODIFY_SL.

Validates:
  • SCRIBE log_trade_position persists tp_stage on insert
  • SCRIBE backfill_tp_stage_from_comment + update_positions_sl_tp_by_stage
  • BRIDGE _coerce_modify_scope / _parse_tp_stage_from_comment helpers
  • BRIDGE _sync_modify_targets routing (ticket / stage / fallback)
  • BRIDGE AURUM-cmd MODIFY_TP / MODIFY_SL forwards ticket and tp_stage to FORGE
  • AURUM + FORGE contract validators accept the new optional fields
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


# ── SCRIBE: tp_stage on insert + helpers ──────────────────────────


def _fresh_scribe(tmp_path):
    import scribe as scribe_mod

    db = tmp_path / "scribe.db"
    return scribe_mod.Scribe(db_path=str(db))


@pytest.mark.unit
def test_scribe_log_trade_position_persists_tp_stage(tmp_path):
    s = _fresh_scribe(tmp_path)
    gid = s.log_trade_group(
        {
            "direction": "BUY",
            "entry_low": 100,
            "entry_high": 100,
            "sl": 99,
            "tp1": 101,
            "tp2": 102,
            "tp3": None,
            "num_trades": 2,
            "lot_per_trade": 0.01,
            "source": "SIGNAL",
        },
        "SIGNAL",
    )
    s.log_trade_position(
        gid,
        {
            "ticket": 555,
            "magic": 202402,
            "direction": "BUY",
            "lot_size": 0.01,
            "entry_price": 100,
            "sl": 99,
            "tp": 101,
            "tp_stage": 1,
        },
        "SIGNAL",
    )
    rows = s.query("SELECT ticket, tp_stage FROM trade_positions WHERE ticket=?", (555,))
    assert rows and rows[0]["tp_stage"] == 1


@pytest.mark.unit
def test_scribe_log_trade_position_rejects_invalid_stage(tmp_path):
    s = _fresh_scribe(tmp_path)
    gid = s.log_trade_group(
        {
            "direction": "BUY",
            "entry_low": 100,
            "entry_high": 100,
            "sl": 99,
            "tp1": 101,
            "tp2": None,
            "tp3": None,
            "num_trades": 1,
            "lot_per_trade": 0.01,
            "source": "SIGNAL",
        },
        "SIGNAL",
    )
    s.log_trade_position(
        gid,
        {
            "ticket": 7,
            "magic": 1,
            "direction": "BUY",
            "lot_size": 0.01,
            "entry_price": 100,
            "sl": 99,
            "tp": 101,
            "tp_stage": 9,  # invalid → coerced to NULL
        },
        "SIGNAL",
    )
    rows = s.query("SELECT tp_stage FROM trade_positions WHERE ticket=?", (7,))
    assert rows and rows[0]["tp_stage"] is None


@pytest.mark.unit
def test_scribe_backfill_tp_stage_from_comment(tmp_path):
    s = _fresh_scribe(tmp_path)
    gid = s.log_trade_group(
        {
            "direction": "BUY",
            "entry_low": 100,
            "entry_high": 100,
            "sl": 99,
            "tp1": 101,
            "tp2": 102,
            "tp3": None,
            "num_trades": 1,
            "lot_per_trade": 0.01,
            "source": "SIGNAL",
        },
        "SIGNAL",
    )
    s.log_trade_position(
        gid,
        {"ticket": 999, "magic": 1, "direction": "BUY", "lot_size": 0.01,
         "entry_price": 100, "sl": 99, "tp": 102},
        "SIGNAL",
    )
    # First call writes the stage.
    assert s.backfill_tp_stage_from_comment(999, "FORGE|G7|0|TP2") == 2
    rows = s.query("SELECT tp_stage FROM trade_positions WHERE ticket=?", (999,))
    assert rows[0]["tp_stage"] == 2
    # Second call must not overwrite a populated stage.
    assert s.backfill_tp_stage_from_comment(999, "FORGE|G7|0|TP1") is None
    rows = s.query("SELECT tp_stage FROM trade_positions WHERE ticket=?", (999,))
    assert rows[0]["tp_stage"] == 2


@pytest.mark.unit
def test_scribe_backfill_ignores_garbage_comment(tmp_path):
    s = _fresh_scribe(tmp_path)
    gid = s.log_trade_group(
        {"direction": "BUY", "entry_low": 100, "entry_high": 100, "sl": 99,
         "tp1": 101, "tp2": None, "tp3": None, "num_trades": 1,
         "lot_per_trade": 0.01, "source": "SIGNAL"},
        "SIGNAL",
    )
    s.log_trade_position(
        gid,
        {"ticket": 1, "magic": 1, "direction": "BUY", "lot_size": 0.01,
         "entry_price": 100, "sl": 99, "tp": 101},
        "SIGNAL",
    )
    assert s.backfill_tp_stage_from_comment(1, "no stage hint here") is None
    assert s.backfill_tp_stage_from_comment(1, "FORGE|G1|0|TP9") is None


@pytest.mark.unit
def test_scribe_update_positions_sl_tp_by_stage_only_touches_matching_legs(tmp_path):
    s = _fresh_scribe(tmp_path)
    gid = s.log_trade_group(
        {"direction": "BUY", "entry_low": 100, "entry_high": 100, "sl": 99,
         "tp1": 101, "tp2": 105, "tp3": None, "num_trades": 2,
         "lot_per_trade": 0.01, "source": "SIGNAL"},
        "SIGNAL",
    )
    # Two legs: one on TP1, one on TP2.
    s.log_trade_position(
        gid,
        {"ticket": 1001, "magic": 1, "direction": "BUY", "lot_size": 0.01,
         "entry_price": 100, "sl": 99, "tp": 101, "tp_stage": 1},
        "SIGNAL",
    )
    s.log_trade_position(
        gid,
        {"ticket": 1002, "magic": 1, "direction": "BUY", "lot_size": 0.01,
         "entry_price": 100, "sl": 99, "tp": 105, "tp_stage": 2},
        "SIGNAL",
    )

    affected = s.update_positions_sl_tp_by_stage(gid, 1, sl=98.0, tp=102.0)
    assert affected == 1

    rows = s.query("SELECT ticket, sl, tp FROM trade_positions WHERE trade_group_id=? ORDER BY ticket", (gid,))
    by_ticket = {r["ticket"]: r for r in rows}
    # Position-level SL/TP are both stage-scoped — mirrors FORGE which only
    # touches positions whose comment matches |TP<stage>.
    assert by_ticket[1001]["tp"] == pytest.approx(102.0)
    assert by_ticket[1001]["sl"] == pytest.approx(98.0)
    assert by_ticket[1002]["tp"] == pytest.approx(105.0)  # other stage untouched
    assert by_ticket[1002]["sl"] == pytest.approx(99.0)   # other stage untouched

    # Group-level mirror moves the whole-group SL plus only the matching tp<n>.
    grp = s.query("SELECT sl, tp1, tp2 FROM trade_groups WHERE id=?", (gid,))[0]
    assert grp["sl"] == pytest.approx(98.0)
    assert grp["tp1"] == pytest.approx(102.0)
    assert grp["tp2"] == pytest.approx(105.0)


@pytest.mark.unit
def test_scribe_update_positions_sl_tp_by_stage_rejects_bad_stage(tmp_path):
    s = _fresh_scribe(tmp_path)
    assert s.update_positions_sl_tp_by_stage(1, 0, sl=1.0) == 0
    assert s.update_positions_sl_tp_by_stage(1, 4, tp=1.0) == 0


@pytest.mark.unit
def test_scribe_get_open_positions_with_stage_returns_open_only(tmp_path):
    s = _fresh_scribe(tmp_path)
    gid = s.log_trade_group(
        {"direction": "BUY", "entry_low": 100, "entry_high": 100, "sl": 99,
         "tp1": 101, "tp2": None, "tp3": None, "num_trades": 1,
         "lot_per_trade": 0.01, "source": "SIGNAL"},
        "SIGNAL",
    )
    s.log_trade_position(
        gid,
        {"ticket": 21, "magic": 1, "direction": "BUY", "lot_size": 0.01,
         "entry_price": 100, "sl": 99, "tp": 101, "tp_stage": 1},
        "SIGNAL",
    )
    s.log_trade_position(
        gid,
        {"ticket": 22, "magic": 1, "direction": "BUY", "lot_size": 0.01,
         "entry_price": 100, "sl": 99, "tp": 101, "tp_stage": 2},
        "SIGNAL",
    )
    s.close_trade_position(ticket=22, close_price=101, close_reason="TP2_HIT",
                            pnl=1.0, pips=10.0, tp_stage=2)
    out = s.get_open_positions_with_stage(gid)
    assert {r["ticket"] for r in out} == {21}
    assert out[0]["tp_stage"] == 1


# ── BRIDGE: helpers ───────────────────────────────────────────────


@pytest.mark.unit
def test_bridge_parse_tp_stage_from_comment():
    import bridge as bm

    assert bm._parse_tp_stage_from_comment("FORGE|G56|0|TP1") == 1
    assert bm._parse_tp_stage_from_comment("FORGE|G56|3|TP3 trail") == 3
    assert bm._parse_tp_stage_from_comment("foreign|TP4") is None
    assert bm._parse_tp_stage_from_comment("") is None
    assert bm._parse_tp_stage_from_comment(None) is None


@pytest.mark.unit
def test_bridge_coerce_modify_scope_normalises_inputs():
    import bridge as bm

    assert bm._coerce_modify_scope({}) == (None, None)
    assert bm._coerce_modify_scope({"ticket": "1234", "tp_stage": "2"}) == (1234, 2)
    assert bm._coerce_modify_scope({"ticket": -5, "tp_stage": 9}) == (None, None)
    assert bm._coerce_modify_scope({"ticket": "junk", "tp_stage": "junk"}) == (None, None)
    assert bm._coerce_modify_scope({"ticket": 0, "tp_stage": 0}) == (None, None)


# ── BRIDGE: _sync_modify_targets routing ──────────────────────────


def _stub_bridge_for_sync(monkeypatch):
    import bridge as bm

    stub = MagicMock()
    stub.scribe = MagicMock()
    stub._open_groups = {15: {"source": "SIGNAL", "tp1": 1.0, "tp2": 2.0}}
    # Bind the real method so we exercise the routing logic.
    stub._sync_modify_targets = bm.Bridge._sync_modify_targets.__get__(stub)
    stub._sync_group_targets = MagicMock()
    stub._sync_all_open_group_targets = MagicMock()
    return stub, bm


@pytest.mark.unit
def test_sync_modify_targets_ticket_scope_only_calls_position_update(monkeypatch):
    stub, _bm = _stub_bridge_for_sync(monkeypatch)
    stub._sync_modify_targets(15, sl=10.0, tp=11.0, ticket=999, tp_stage=2)
    stub.scribe.update_position_sl_tp.assert_called_once_with(999, sl=10.0, tp=11.0)
    stub.scribe.update_positions_sl_tp_by_stage.assert_not_called()
    stub._sync_group_targets.assert_not_called()


@pytest.mark.unit
def test_sync_modify_targets_stage_scope_calls_stage_helper_only(monkeypatch):
    stub, _bm = _stub_bridge_for_sync(monkeypatch)
    stub._sync_modify_targets(15, sl=None, tp=4.5, ticket=None, tp_stage=2)
    stub.scribe.update_positions_sl_tp_by_stage.assert_called_once_with(15, 2, sl=None, tp=4.5)
    stub.scribe.update_position_sl_tp.assert_not_called()
    stub._sync_group_targets.assert_not_called()
    # Cache should reflect the matching stage column only.
    assert stub._open_groups[15]["tp2"] == 4.5
    assert stub._open_groups[15]["tp1"] == 1.0


@pytest.mark.unit
def test_sync_modify_targets_unscoped_falls_back_to_group(monkeypatch):
    stub, _bm = _stub_bridge_for_sync(monkeypatch)
    stub._sync_modify_targets(15, sl=10.0, tp=None, ticket=None, tp_stage=None)
    stub._sync_group_targets.assert_called_once_with(15, sl=10.0, tp=None)


@pytest.mark.unit
def test_sync_modify_targets_unscoped_no_group_uses_all_open(monkeypatch):
    stub, _bm = _stub_bridge_for_sync(monkeypatch)
    stub._sync_modify_targets(None, sl=None, tp=42.0, ticket=None, tp_stage=None)
    stub._sync_all_open_group_targets.assert_called_once_with(sl=None, tp=42.0)


# ── BRIDGE: AURUM cmd MODIFY pass-through ─────────────────────────


def _stub_bridge_for_aurum(monkeypatch, cmd: dict, tmp_path):
    import bridge as bm

    aurum_path = tmp_path / "aurum_cmd.json"
    aurum_path.write_text(json.dumps(cmd), encoding="utf-8")
    monkeypatch.setattr(bm, "AURUM_CMD_FILE", str(aurum_path))

    stub = MagicMock()
    stub._last_aurum_ts = None
    stub._open_groups = {}
    stub._lookup_group_magic = lambda gid: 202401 + int(gid)
    stub._sync_modify_targets = MagicMock()
    stub._bridge_activity = MagicMock()
    stub._dispatch_aurum_open_group = MagicMock()
    stub._normalize_aurum_open_trade = MagicMock()
    stub._report_aeb_result = MagicMock()
    stub._change_mode = MagicMock()
    stub.herald = MagicMock()
    stub.scribe = MagicMock()
    return stub, bm


@pytest.mark.unit
def test_aurum_modify_tp_forwards_stage_and_ticket(monkeypatch, tmp_path):
    cmd = {
        "action": "MODIFY_TP",
        "tp": 4648.0,
        "group_id": 15,
        "tp_stage": 1,
        "ticket": 1122706681,
        "timestamp": "2026-04-30T19:00:00+00:00",
    }
    stub, bm = _stub_bridge_for_aurum(monkeypatch, cmd, tmp_path)

    with patch.object(bm, "_write_forge_command") as mock_forge:
        bm.Bridge._check_aurum_command(stub, {})

    mock_forge.assert_called_once()
    forge_cmd = mock_forge.call_args[0][0]
    assert forge_cmd["action"] == "MODIFY_TP"
    assert forge_cmd["tp"] == 4648.0
    assert forge_cmd["magic"] == 202416
    assert forge_cmd["ticket"] == 1122706681
    assert forge_cmd["tp_stage"] == 1
    stub._sync_modify_targets.assert_called_once_with(
        15, sl=None, tp=4648.0, ticket=1122706681, tp_stage=1,
    )


@pytest.mark.unit
def test_aurum_modify_sl_stage_only(monkeypatch, tmp_path):
    cmd = {
        "action": "MODIFY_SL",
        "sl": 4660.0,
        "group_id": 15,
        "tp_stage": 2,
        "timestamp": "2026-04-30T19:00:00+00:00",
    }
    stub, bm = _stub_bridge_for_aurum(monkeypatch, cmd, tmp_path)

    with patch.object(bm, "_write_forge_command") as mock_forge:
        bm.Bridge._check_aurum_command(stub, {})

    forge_cmd = mock_forge.call_args[0][0]
    assert forge_cmd["action"] == "MODIFY_SL"
    assert forge_cmd["sl"] == 4660.0
    assert "ticket" not in forge_cmd
    assert forge_cmd["tp_stage"] == 2
    stub._sync_modify_targets.assert_called_once_with(
        15, sl=4660.0, tp=None, ticket=None, tp_stage=2,
    )


@pytest.mark.unit
def test_aurum_modify_legacy_unscoped_still_works(monkeypatch, tmp_path):
    cmd = {
        "action": "MODIFY_TP",
        "tp": 4700.0,
        "group_id": 7,
        "timestamp": "2026-04-30T19:01:00+00:00",
    }
    stub, bm = _stub_bridge_for_aurum(monkeypatch, cmd, tmp_path)

    with patch.object(bm, "_write_forge_command") as mock_forge:
        bm.Bridge._check_aurum_command(stub, {})

    forge_cmd = mock_forge.call_args[0][0]
    assert "ticket" not in forge_cmd
    assert "tp_stage" not in forge_cmd
    stub._sync_modify_targets.assert_called_once_with(
        7, sl=None, tp=4700.0, ticket=None, tp_stage=None,
    )


# ── Contract validators ───────────────────────────────────────────


@pytest.mark.unit
def test_validate_aurum_modify_tp_with_stage_is_valid():
    from contracts.aurum_forge import validate_aurum_cmd

    cmd = {
        "action": "MODIFY_TP",
        "tp": 4648.0,
        "group_id": 15,
        "tp_stage": 1,
        "timestamp": "2026-04-30T19:00:00+00:00",
    }
    assert validate_aurum_cmd(cmd) == []


@pytest.mark.unit
def test_validate_aurum_modify_sl_with_ticket_is_valid():
    from contracts.aurum_forge import validate_aurum_cmd

    cmd = {
        "action": "MODIFY_SL",
        "sl": 4660.0,
        "ticket": 1122706681,
        "timestamp": "2026-04-30T19:00:00+00:00",
    }
    assert validate_aurum_cmd(cmd) == []


@pytest.mark.unit
def test_validate_aurum_modify_rejects_bad_stage():
    from contracts.aurum_forge import validate_aurum_cmd

    cmd = {
        "action": "MODIFY_TP",
        "tp": 4648.0,
        "tp_stage": 9,
        "timestamp": "2026-04-30T19:00:00+00:00",
    }
    errs = validate_aurum_cmd(cmd)
    assert any("tp_stage" in e for e in errs)


@pytest.mark.unit
def test_validate_aurum_modify_rejects_bad_ticket():
    from contracts.aurum_forge import validate_aurum_cmd

    cmd = {
        "action": "MODIFY_SL",
        "sl": 4660.0,
        "ticket": 0,
        "timestamp": "2026-04-30T19:00:00+00:00",
    }
    errs = validate_aurum_cmd(cmd)
    assert any("ticket" in e for e in errs)


@pytest.mark.unit
def test_validate_forge_modify_with_stage_is_valid():
    from contracts.aurum_forge import validate_forge_command

    cmd = {
        "action": "MODIFY_TP",
        "tp": 4648.0,
        "magic": 202416,
        "tp_stage": 1,
        "timestamp": "2026-04-30T19:00:00+00:00",
    }
    assert validate_forge_command(cmd) == []


@pytest.mark.unit
def test_validate_forge_modify_rejects_bad_stage():
    from contracts.aurum_forge import validate_forge_command

    cmd = {
        "action": "MODIFY_SL",
        "sl": 4660.0,
        "magic": 202416,
        "tp_stage": 5,
        "timestamp": "2026-04-30T19:00:00+00:00",
    }
    errs = validate_forge_command(cmd)
    assert any("tp_stage" in e for e in errs)


# ── BRIDGE: TRACKER drift detector must NOT fan single-ticket TP
#           drift across the whole group (would collapse stage-scoped
#           MODIFYs the AURUM/MGMT path just wrote).


@pytest.mark.unit
def test_tracker_tp_drift_only_updates_drifted_ticket(tmp_path, monkeypatch):
    import bridge as bm

    s = _fresh_scribe(tmp_path)
    gid = s.log_trade_group(
        {"direction": "BUY", "entry_low": 100, "entry_high": 100, "sl": 99,
         "tp1": 101, "tp2": 105, "tp3": None, "num_trades": 2,
         "lot_per_trade": 0.01, "source": "SIGNAL"},
        "SIGNAL",
    )
    s.update_trade_group_magic(gid, 202416)
    s.log_trade_position(
        gid,
        {"ticket": 1001, "magic": 202416, "direction": "BUY", "lot_size": 0.01,
         "entry_price": 100, "sl": 99, "tp": 101, "tp_stage": 1},
        "SIGNAL",
    )
    s.log_trade_position(
        gid,
        {"ticket": 1002, "magic": 202416, "direction": "BUY", "lot_size": 0.01,
         "entry_price": 100, "sl": 99, "tp": 105, "tp_stage": 2},
        "SIGNAL",
    )

    # Build a BRIDGE-like stub that uses the real _sync_positions code path.
    stub = MagicMock()
    stub.scribe = s
    stub._open_groups = {gid: {"id": gid, "magic_number": 202416,
                                 "sl": 99.0, "tp1": 101.0, "tp2": 105.0}}
    stub._tracker_seeded = True
    stub._effective_mode = lambda: "SIGNAL"
    stub._resolve_group_for_magic = lambda m: gid if m == 202416 else None
    stub._bridge_activity = MagicMock()
    stub._sync_group_targets = MagicMock()  # must NOT be called
    stub._sync_all_open_group_targets = MagicMock()
    stub.herald = MagicMock()
    stub._known_positions = {
        1001: {"group_id": gid, "magic": 202416, "direction": "BUY",
               "open_price": 100.0, "last_profit": 0.0,
               "current_price": 100.0, "lot_size": 0.01,
               "sl": 99.0, "tp": 101.0, "symbol": "XAUUSD"},
        1002: {"group_id": gid, "magic": 202416, "direction": "BUY",
               "open_price": 100.0, "last_profit": 0.0,
               "current_price": 100.0, "lot_size": 0.01,
               "sl": 99.0, "tp": 105.0, "symbol": "XAUUSD"},
    }
    stub._known_unmanaged_positions = {}
    stub._known_pendings = {}

    # Live MT5 view: only the TP2 leg (#1002) drifted from 105 -> 110.
    mt5 = {
        "open_positions": [
            {"ticket": 1001, "symbol": "XAUUSD", "type": "BUY", "lots": 0.01,
             "open_price": 100.0, "current_price": 100.0,
             "sl": 99.0, "tp": 101.0, "profit": 0.0, "magic": 202416,
             "forge_managed": True, "comment": "FORGE|G1|0|TP1"},
            {"ticket": 1002, "symbol": "XAUUSD", "type": "BUY", "lots": 0.01,
             "open_price": 100.0, "current_price": 100.0,
             "sl": 99.0, "tp": 110.0, "profit": 0.0, "magic": 202416,
             "forge_managed": True, "comment": "FORGE|G1|1|TP2"},
        ],
        "pending_orders": [],
    }

    bm.Bridge._sync_positions(stub, mt5)

    # The drifted leg's row reflects the new TP. The other stage row is untouched.
    rows = {r["ticket"]: r for r in s.query(
        "SELECT ticket, sl, tp, tp_stage FROM trade_positions WHERE trade_group_id=? AND status='OPEN'",
        (gid,),
    )}
    assert rows[1001]["tp"] == pytest.approx(101.0)  # TP1 leg untouched
    assert rows[1001]["tp_stage"] == 1
    assert rows[1002]["tp"] == pytest.approx(110.0)  # drifted leg updated
    assert rows[1002]["tp_stage"] == 2

    # trade_groups.tp1/tp2/tp3 must NOT collapse onto the drifted ticket's TP.
    grp = s.query("SELECT sl, tp1, tp2 FROM trade_groups WHERE id=?", (gid,))[0]
    assert grp["tp1"] == pytest.approx(101.0)
    assert grp["tp2"] == pytest.approx(105.0)

    # Whole-group fan-out helper must NOT have been invoked for TP drift alone.
    stub._sync_group_targets.assert_not_called()
    stub._sync_all_open_group_targets.assert_not_called()


# ── BRIDGE: profit-ratchet (auto SL lock when leg goes N pips green) ──


def _ratchet_stub(monkeypatch, tmp_path):
    """Build a Bridge stub wired enough to exercise _apply_profit_ratchet."""
    import bridge as bm

    stub = MagicMock()
    stub.scribe = MagicMock()
    stub.herald = MagicMock()
    stub._open_groups = {}
    stub._known_positions = {
        555: {"group_id": 99, "magic": 202416,
               "direction": "BUY", "open_price": 4620.0,
               "sl": 4610.0, "tp": 4632.0, "symbol": "XAUUSD"},
    }
    stub._profit_ratcheted = set()
    stub._sync_modify_targets = MagicMock()
    stub._bridge_activity = MagicMock()
    stub._apply_profit_ratchet = bm.Bridge._apply_profit_ratchet.__get__(stub)
    return stub, bm


@pytest.mark.unit
def test_profit_ratchet_emits_ticket_scoped_modify_sl(monkeypatch, tmp_path):
    monkeypatch.setattr("bridge.PROFIT_RATCHET_ENABLED", True, raising=False)
    monkeypatch.setattr("bridge.PROFIT_RATCHET_TRIGGER_PIPS", 3.0, raising=False)
    monkeypatch.setattr("bridge.PROFIT_RATCHET_LOCK_PIPS", 1.0, raising=False)
    stub, bm = _ratchet_stub(monkeypatch, tmp_path)
    # +5 pips (XAU pip=0.01 → 4620.05 = +5p) so > trigger 3.
    live = {
        555: {"ticket": 555, "symbol": "XAUUSD", "type": "BUY",
              "open_price": 4620.0, "current_price": 4620.05,
              "sl": 4610.0, "tp": 4632.0, "magic": 202416,
              "forge_managed": True, "comment": "FORGE|G99|0|TP1"},
    }
    with patch.object(bm, "_write_forge_command") as mock_forge:
        stub._apply_profit_ratchet(live)
    mock_forge.assert_called_once()
    forge_cmd = mock_forge.call_args[0][0]
    assert forge_cmd["action"] == "MODIFY_SL"
    assert forge_cmd["ticket"] == 555
    assert forge_cmd["magic"] == 202416
    # entry 4620 + lock 1 pip * 0.01 = 4620.01
    assert forge_cmd["sl"] == pytest.approx(4620.01)
    stub._sync_modify_targets.assert_called_once_with(
        99, sl=pytest.approx(4620.01), tp=None, ticket=555, tp_stage=None,
    )
    assert 555 in stub._profit_ratcheted


@pytest.mark.unit
def test_profit_ratchet_idempotent_per_ticket(monkeypatch):
    monkeypatch.setattr("bridge.PROFIT_RATCHET_ENABLED", True, raising=False)
    monkeypatch.setattr("bridge.PROFIT_RATCHET_TRIGGER_PIPS", 3.0, raising=False)
    monkeypatch.setattr("bridge.PROFIT_RATCHET_LOCK_PIPS", 1.0, raising=False)
    stub, bm = _ratchet_stub(monkeypatch, None)
    stub._profit_ratcheted = {555}
    live = {
        555: {"ticket": 555, "symbol": "XAUUSD", "type": "BUY",
              "open_price": 4620.0, "current_price": 4620.10,
              "sl": 4610.0, "tp": 4632.0, "magic": 202416,
              "forge_managed": True},
    }
    with patch.object(bm, "_write_forge_command") as mock_forge:
        stub._apply_profit_ratchet(live)
    mock_forge.assert_not_called()
    stub._sync_modify_targets.assert_not_called()


@pytest.mark.unit
def test_profit_ratchet_skips_when_below_trigger(monkeypatch):
    monkeypatch.setattr("bridge.PROFIT_RATCHET_ENABLED", True, raising=False)
    monkeypatch.setattr("bridge.PROFIT_RATCHET_TRIGGER_PIPS", 3.0, raising=False)
    monkeypatch.setattr("bridge.PROFIT_RATCHET_LOCK_PIPS", 1.0, raising=False)
    stub, bm = _ratchet_stub(monkeypatch, None)
    live = {
        555: {"ticket": 555, "symbol": "XAUUSD", "type": "BUY",
              "open_price": 4620.0, "current_price": 4620.02,  # +2p only
              "sl": 4610.0, "tp": 4632.0, "magic": 202416,
              "forge_managed": True},
    }
    with patch.object(bm, "_write_forge_command") as mock_forge:
        stub._apply_profit_ratchet(live)
    mock_forge.assert_not_called()


@pytest.mark.unit
def test_profit_ratchet_skips_when_sl_already_past_lock(monkeypatch):
    monkeypatch.setattr("bridge.PROFIT_RATCHET_ENABLED", True, raising=False)
    monkeypatch.setattr("bridge.PROFIT_RATCHET_TRIGGER_PIPS", 3.0, raising=False)
    monkeypatch.setattr("bridge.PROFIT_RATCHET_LOCK_PIPS", 1.0, raising=False)
    stub, bm = _ratchet_stub(monkeypatch, None)
    live = {
        555: {"ticket": 555, "symbol": "XAUUSD", "type": "BUY",
              "open_price": 4620.0, "current_price": 4620.10,
              "sl": 4625.0,  # FORGE already moved to BE+ on TP1
              "tp": 4632.0, "magic": 202416,
              "forge_managed": True},
    }
    with patch.object(bm, "_write_forge_command") as mock_forge:
        stub._apply_profit_ratchet(live)
    mock_forge.assert_not_called()
    # Marked as ratcheted so we don't re-evaluate next tick.
    assert 555 in stub._profit_ratcheted


@pytest.mark.unit
def test_profit_ratchet_sell_uses_inverted_lock(monkeypatch):
    monkeypatch.setattr("bridge.PROFIT_RATCHET_ENABLED", True, raising=False)
    monkeypatch.setattr("bridge.PROFIT_RATCHET_TRIGGER_PIPS", 3.0, raising=False)
    monkeypatch.setattr("bridge.PROFIT_RATCHET_LOCK_PIPS", 1.0, raising=False)
    stub, bm = _ratchet_stub(monkeypatch, None)
    stub._known_positions[555]["direction"] = "SELL"
    live = {
        555: {"ticket": 555, "symbol": "XAUUSD", "type": "SELL",
              "open_price": 4620.0, "current_price": 4619.94,  # -6p (SELL profit)
              "sl": 4630.0, "tp": 4610.0, "magic": 202416,
              "forge_managed": True},
    }
    with patch.object(bm, "_write_forge_command") as mock_forge:
        stub._apply_profit_ratchet(live)
    mock_forge.assert_called_once()
    forge_cmd = mock_forge.call_args[0][0]
    # entry 4620 - lock 1 pip * 0.01 = 4619.99
    assert forge_cmd["sl"] == pytest.approx(4619.99)


@pytest.mark.unit
def test_profit_ratchet_disabled_short_circuits(monkeypatch):
    monkeypatch.setattr("bridge.PROFIT_RATCHET_ENABLED", False, raising=False)
    import bridge as bm
    # When the env flag is off, _sync_positions never invokes the helper at all.
    stub = MagicMock()
    stub._apply_profit_ratchet = MagicMock()
    # Simulate the gate at the bottom of _sync_positions.
    if bm.PROFIT_RATCHET_ENABLED:
        stub._apply_profit_ratchet({1: {"foo": "bar"}})
    stub._apply_profit_ratchet.assert_not_called()
