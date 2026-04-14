from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def _make_stub():
    import bridge as bm

    stub = SimpleNamespace()
    stub._tracker_seeded = True
    stub._known_positions = {}
    stub._known_unmanaged_positions = {}
    stub._known_pendings = {}
    stub._open_groups = {}
    stub._last_loss_close_ts = 0
    stub.scribe = MagicMock()
    stub.herald = MagicMock()
    stub._effective_mode = lambda: "HYBRID"
    stub._resolve_group_for_magic = lambda _magic: None
    stub._lookup_group_magic = lambda _gid: None
    stub._bridge_activity = MagicMock()
    stub._infer_close_reason = bm.Bridge._infer_close_reason.__get__(stub, type(stub))
    stub._match_tp_stage = bm.Bridge._match_tp_stage.__get__(stub, type(stub))
    return stub, bm


@pytest.mark.unit
def test_sync_positions_logs_unmanaged_open_to_scribe():
    stub, bm = _make_stub()
    stub.scribe.log_trade_group.return_value = 321
    stub.scribe.query.return_value = []
    mt5 = {
        "account": {"balance": 100000.0},
        "open_positions": [
            {
                "ticket": 1146212583,
                "symbol": "XAUUSD",
                "type": "BUY",
                "lots": 0.01,
                "open_price": 4765.61,
                "current_price": 4766.13,
                "sl": 0.0,
                "tp": 0.0,
                "profit": 0.52,
                "magic": 0,
                "forge_managed": False,
            }
        ],
        "pending_orders": [],
    }

    bm.Bridge._sync_positions(stub, mt5)

    stub.scribe.log_trade_group.assert_called_once()
    group_data = stub.scribe.log_trade_group.call_args[0][0]
    assert group_data["source"] == "MANUAL_MT5"
    assert group_data["num_trades"] == 1
    stub.scribe.log_trade_position.assert_called_once()
    pos_data = stub.scribe.log_trade_position.call_args[0][1]
    assert pos_data["ticket"] == 1146212583
    assert pos_data["magic"] == 0
    assert 1146212583 in stub._known_unmanaged_positions
    assert stub._known_unmanaged_positions[1146212583]["group_id"] == 321
    stub._bridge_activity.assert_called()


@pytest.mark.unit
def test_sync_positions_closes_unmanaged_position_in_scribe():
    stub, bm = _make_stub()
    stub.scribe.query.return_value = []
    stub._known_unmanaged_positions[1146212583] = {
        "group_id": 321,
        "magic": 0,
        "symbol": "XAUUSD",
        "direction": "BUY",
        "open_price": 4765.61,
        "last_profit": 0.52,
        "current_price": 4766.13,
        "lot_size": 0.01,
        "sl": 0.0,
        "tp": 0.0,
    }
    mt5 = {"account": {"balance": 100000.0}, "open_positions": [], "pending_orders": []}

    bm.Bridge._sync_positions(stub, mt5)

    stub.scribe.close_trade_position.assert_called_once()
    close_kwargs = stub.scribe.close_trade_position.call_args.kwargs
    assert close_kwargs["ticket"] == 1146212583
    assert close_kwargs["close_reason"] in {"MANUAL_CLOSE", "UNKNOWN"}
    stub.scribe.log_trade_closure.assert_called_once()
    stub.scribe.update_trade_group.assert_called_once()
    assert 1146212583 not in stub._known_unmanaged_positions

@pytest.mark.unit
def test_sync_positions_uses_broker_recent_closed_deal_for_managed_close():
    stub, bm = _make_stub()
    stub.scribe.query.return_value = []
    stub._known_positions[1148548493] = {
        "group_id": 24,
        "magic": 202425,
        "direction": "BUY",
        "open_price": 4750.15,
        "last_profit": 0.0,
        "current_price": 4750.25,
        "lot_size": 0.01,
        "symbol": "XAUUSD",
        "sl": 4744.3,
        "tp": 4755.3,
    }
    mt5 = {
        "account": {"balance": 100000.0},
        "open_positions": [],
        "pending_orders": [],
        "recent_closed_deals": [
            {
                "position_ticket": 1148548493,
                "close_price": 4755.3,
                "profit": 5.42,
                "close_reason": "TP_HIT",
                "time_unix": 1893456000,
            }
        ],
    }

    bm.Bridge._sync_positions(stub, mt5)

    stub.scribe.close_trade_position.assert_called_once()
    close_kwargs = stub.scribe.close_trade_position.call_args.kwargs
    assert close_kwargs["ticket"] == 1148548493
    assert close_kwargs["close_price"] == 4755.3
    assert close_kwargs["pnl"] == 5.42
    assert close_kwargs["close_reason"] == "TP1_HIT"
    assert close_kwargs["close_time"].startswith("2030-01-01T00:00:00")


@pytest.mark.unit
def test_pending_timeout_cancels_pending_only_when_positions_exist(monkeypatch):
    stub, bm = _make_stub()
    stub._lookup_group_magic = lambda gid: 202425 if gid == 24 else None
    stub._known_pendings = {
        900001: {
            "group_id": 24,
            "magic": 202425,
            "order_type": "SELL_LIMIT",
            "price": 4760.3,
            "tracked_since": 1.0,
        }
    }
    # Simulate one already-filled/open position in same group magic.
    stub._known_positions = {
        1148548493: {
            "group_id": 24,
            "magic": 202425,
            "direction": "SELL",
            "open_price": 4750.15,
            "last_profit": 0.0,
            "current_price": 4750.25,
            "sl": 4764.3,
            "tp": 4746.3,
        }
    }
    stub.scribe.query.return_value = []
    captured_cmds = []
    monkeypatch.setattr(bm, "_write_forge_command", lambda cmd: captured_cmds.append(dict(cmd)))
    monkeypatch.setattr(bm, "PENDING_ORDER_TIMEOUT_SEC", 1)
    monkeypatch.setattr(bm.time, "time", lambda: 1000.0)
    mt5 = {
        "account": {"balance": 100000.0},
        "open_positions": [
            {
                "ticket": 1148548493,
                "symbol": "XAUUSD",
                "type": "SELL",
                "lots": 0.01,
                "open_price": 4750.15,
                "current_price": 4750.25,
                "sl": 4764.3,
                "tp": 4746.3,
                "profit": 0.0,
                "magic": 202425,
                "forge_managed": True,
            }
        ],
        "pending_orders": [
            {
                "ticket": 900001,
                "symbol": "XAUUSD",
                "order_type": "SELL_LIMIT",
                "price": 4760.3,
                "sl": 4764.3,
                "tp": 4746.3,
                "magic": 202425,
                "forge_managed": True,
            }
        ],
    }

    bm.Bridge._sync_positions(stub, mt5)

    assert captured_cmds, "Expected timeout to enqueue a pending-cancel command"
    assert captured_cmds[0]["action"] == "CANCEL_GROUP_PENDING"
    assert captured_cmds[0]["magic"] == 202425
    # Group must stay open when it still has filled/open positions.
    stub.scribe.update_trade_group.assert_not_called()


@pytest.mark.unit
def test_pending_timeout_skips_signal_groups(monkeypatch):
    stub, bm = _make_stub()
    stub._lookup_group_magic = lambda gid: 202426 if gid == 26 else None
    stub._known_pendings = {
        900002: {
            "group_id": 26,
            "magic": 202426,
            "order_type": "BUY_LIMIT",
            "price": 3300.0,
            "tracked_since": 1.0,
        }
    }
    stub._known_positions = {}
    stub._open_groups = {26: {"source": "SIGNAL"}}
    stub.scribe.query.return_value = []
    captured_cmds = []
    monkeypatch.setattr(bm, "_write_forge_command", lambda cmd: captured_cmds.append(dict(cmd)))
    monkeypatch.setattr(bm, "PENDING_ORDER_TIMEOUT_SEC", 1)
    monkeypatch.setattr(bm.time, "time", lambda: 1000.0)
    mt5 = {
        "account": {"balance": 100000.0},
        "open_positions": [],
        "pending_orders": [
            {
                "ticket": 900002,
                "symbol": "XAUUSD",
                "order_type": "BUY_LIMIT",
                "price": 3300.0,
                "sl": 3295.0,
                "tp": 3310.0,
                "magic": 202426,
                "forge_managed": True,
            }
        ],
    }

    bm.Bridge._sync_positions(stub, mt5)

    assert not captured_cmds, "SIGNAL groups should not be auto-cancelled by timeout"
    stub.scribe.update_trade_group.assert_not_called()
    stub.herald.send.assert_not_called()


@pytest.mark.unit
def test_calc_pips_xau_uses_cent_pip():
    import bridge as bm
    # 1.5 USD move on XAU -> 150.0 pips when 1 pip = 0.01
    assert bm._calc_pips("XAUUSD", "BUY", 3300.0, 3301.5) == 150.0
    # SELL should invert move sign
    assert bm._calc_pips("XAUUSD", "SELL", 3301.5, 3300.0) == 150.0


@pytest.mark.unit
def test_calc_pips_forex_conventions():
    import bridge as bm

    # EURUSD: pip = 0.0001
    assert bm._calc_pips("EURUSD", "BUY", 1.1000, 1.1015) == 15.0
    # USDJPY: pip = 0.01
    assert bm._calc_pips("USDJPY", "BUY", 150.00, 150.35) == 35.0
