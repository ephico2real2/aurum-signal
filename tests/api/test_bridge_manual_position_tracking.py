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
