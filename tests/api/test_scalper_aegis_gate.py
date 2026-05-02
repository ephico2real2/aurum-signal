"""
BRIDGE _scalper_logic must route LENS-driven scalps through Aegis.validate()
before OPEN_GROUP (Phase A — docs/SCALPER_REGIME_PHASED_PLAN.md).
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


@pytest.mark.unit
def test_scalper_rejected_skips_forge_and_scribe_log(monkeypatch):
    import bridge as bm
    from aegis import TradeApproval

    stub = SimpleNamespace()
    stub._open_groups = {}
    stub.aegis = MagicMock()
    stub.aegis.validate.return_value = TradeApproval(
        approved=False,
        reject_reason="H1_TREND_CONFLICT:H1=BEAR_vs_BUY",
    )
    stub.scribe = MagicMock()
    stub.scribe.log_trade_group = MagicMock(return_value=99)
    stub._effective_mode = MagicMock(return_value="SCALPER")
    stub._regime_context_for_trade = MagicMock(
        return_value={"label": "TREND_BULL", "confidence": 0.6, "apply_entry_policy": False}
    )
    stub._bridge_activity = MagicMock()
    stub.herald = MagicMock()

    lens = SimpleNamespace(
        rsi=35,
        macd_hist=0.5,
        adx=25,
        bb_rating=1,
        price=2650.0,
    )
    mt5 = {
        "account": {"balance": 10000.0, "equity": 10000.0, "total_floating_pnl": 0.0},
        "price": {"bid": 2650.0},
        "indicators_h1": {"ema_20": 2655.0, "ema_50": 2640.0},
    }

    with patch.object(bm, "_write_forge_command") as wfc:
        bm.Bridge._scalper_logic(stub, mt5, lens)

    stub.aegis.validate.assert_called_once()
    _, kwargs = stub.aegis.validate.call_args
    assert kwargs["mt5_data"] is mt5
    assert kwargs["regime_context"]["label"] == "TREND_BULL"
    stub.scribe.log_trade_group.assert_not_called()
    wfc.assert_not_called()
    stub._bridge_activity.assert_called_once()
    assert stub._bridge_activity.call_args[0][0] == "SCALPER_REJECTED"


@pytest.mark.unit
def test_scalper_approved_writes_group_forge_and_regime_columns(monkeypatch):
    import bridge as bm
    from aegis import TradeApproval

    ladder = [2649.8, 2649.9, 2650.0, 2650.1]
    stub = SimpleNamespace()
    stub._open_groups = {}
    stub.aegis = MagicMock()
    stub.aegis.validate.return_value = TradeApproval(
        approved=True,
        lot_per_trade=0.02,
        entry_ladder=ladder,
        num_trades=4,
        risk_pct=2.0,
        rr_ratio=1.5,
        entry_zone_pips=1.0,
        regime_metadata={"policy_name": "LEGACY_SIGNAL_FAVORABLE_ENDPOINT", "applied": False},
    )
    stub.scribe = MagicMock()
    stub.scribe.log_trade_group = MagicMock(return_value=42)
    stub._effective_mode = MagicMock(return_value="HYBRID")
    stub._regime_context_for_trade = MagicMock(
        return_value={
            "label": "RANGE",
            "confidence": 0.55,
            "apply_entry_policy": False,
            "model_name": "GAUSSIAN_FALLBACK",
            "entry_mode": "shadow",
        }
    )
    stub._bridge_activity = MagicMock()
    stub.herald = MagicMock()

    lens = SimpleNamespace(
        rsi=35,
        macd_hist=0.5,
        adx=25,
        bb_rating=1,
        price=2650.0,
    )
    mt5 = {
        "account": {"balance": 10000.0, "equity": 10000.0, "total_floating_pnl": 0.0},
        "price": {"bid": 2650.0},
        "indicators_h1": {"ema_20": 2655.0, "ema_50": 2640.0},
    }

    with patch.object(bm, "_write_forge_command") as wfc:
        wfc.return_value = ["/tmp/command.json"]
        bm.Bridge._scalper_logic(stub, mt5, lens)

    stub.scribe.log_trade_group.assert_called_once()
    gd = stub.scribe.log_trade_group.call_args[0][0]
    assert gd["source"] == "SCALPER_SUBPATH_DIRECT"
    assert gd["regime_label"] == "RANGE"
    assert gd["regime_model"] == "GAUSSIAN_FALLBACK"
    assert gd["lot_per_trade"] == 0.02
    assert gd["num_trades"] == 4

    wfc.assert_called_once()
    cmd = wfc.call_args[0][0]
    assert cmd["action"] == "OPEN_GROUP"
    assert cmd["entry_ladder"] == ladder
    assert cmd["lot_per_trade"] == 0.02
    stub.herald.trade_group_opened.assert_called_once()
    assert stub._open_groups[42]["magic_number"] == bm.FORGE_MAGIC_BASE + 42
