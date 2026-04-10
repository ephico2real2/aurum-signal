"""
BRIDGE: aurum_cmd.json is a queue file — removed after a command is accepted.

Uses Bridge._check_aurum_command on a stub instance + monkeypatched AURUM_CMD_FILE
(no full Bridge() construction).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock
import inspect

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


@pytest.mark.unit
def test_aurum_cmd_file_deleted_after_mode_change(monkeypatch, tmp_path):
    import bridge as bm

    cmd_path = tmp_path / "aurum_cmd.json"
    payload = {
        "action": "MODE_CHANGE",
        "new_mode": "SCALPER",
        "timestamp": "2099-06-15T12:00:00+00:00",
    }
    cmd_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(bm, "AURUM_CMD_FILE", str(cmd_path))

    stub = MagicMock()
    stub._last_aurum_ts = None
    stub._change_mode = MagicMock()

    bm.Bridge._check_aurum_command(stub, {})

    assert not cmd_path.exists(), "BRIDGE must remove aurum_cmd.json after handling"
    stub._change_mode.assert_called_once_with("SCALPER", "AURUM")


@pytest.mark.unit
def test_aurum_cmd_duplicate_timestamp_skips_and_does_not_delete(monkeypatch, tmp_path):
    """Same timestamp as last processed: early return; file left (current bridge behavior)."""
    import bridge as bm

    cmd_path = tmp_path / "aurum_cmd.json"
    ts = "2099-06-15T12:00:01+00:00"
    cmd_path.write_text(
        json.dumps({"action": "MODE_CHANGE", "new_mode": "WATCH", "timestamp": ts}),
        encoding="utf-8",
    )
    monkeypatch.setattr(bm, "AURUM_CMD_FILE", str(cmd_path))

    stub = MagicMock()
    stub._last_aurum_ts = ts

    bm.Bridge._check_aurum_command(stub, {})

    assert cmd_path.is_file()
    stub._change_mode.assert_not_called()


@pytest.mark.unit
def test_aurum_cmd_missing_file_no_crash(monkeypatch, tmp_path):
    import bridge as bm

    cmd_path = tmp_path / "aurum_cmd.json"
    monkeypatch.setattr(bm, "AURUM_CMD_FILE", str(cmd_path))
    assert not cmd_path.exists()

    stub = MagicMock()
    stub._last_aurum_ts = None

    bm.Bridge._check_aurum_command(stub, {})

    stub._change_mode.assert_not_called()


@pytest.mark.unit
def test_resolve_forge_scalper_mode_by_mode():
    import bridge as bm

    assert bm._resolve_forge_scalper_mode("SCALPER") == bm.FORGE_SCALPER_MODE
    assert bm._resolve_forge_scalper_mode("HYBRID") == bm.FORGE_SCALPER_MODE
    assert bm._resolve_forge_scalper_mode("SIGNAL") == "NONE"
    assert bm._resolve_forge_scalper_mode("WATCH") == "NONE"
    assert bm._resolve_forge_scalper_mode("OFF") == "NONE"
    assert bm._resolve_forge_scalper_mode("AUTO_SCALPER") == "NONE"


@pytest.mark.unit
def test_build_entry_ladder_even_spacing():
    import bridge as bm

    ladder = bm._build_entry_ladder(100.0, 101.5, 4)
    assert ladder == [100.0, 100.5, 101.0, 101.5]


@pytest.mark.unit
def test_scalper_logic_no_aegis_validate_call():
    import bridge as bm

    src = inspect.getsource(bm.Bridge._scalper_logic)
    assert "aegis.validate" not in src


@pytest.mark.unit
def test_aegis_signal_buy_uses_cheapest_endpoint_for_ladder():
    import aegis

    ladder = aegis.Aegis._build_entry_ladder(
        direction="BUY",
        entry_low=4750.2,
        entry_high=4760.2,
        num_trades=4,
        source="SIGNAL",
    )
    assert ladder == [4750.2, 4750.2, 4750.2, 4750.2]


@pytest.mark.unit
def test_aegis_signal_sell_uses_highest_endpoint_for_ladder():
    import aegis

    ladder = aegis.Aegis._build_entry_ladder(
        direction="SELL",
        entry_low=4750.2,
        entry_high=4760.2,
        num_trades=4,
        source="SIGNAL",
    )
    assert ladder == [4760.2, 4760.2, 4760.2, 4760.2]


@pytest.mark.unit
def test_aegis_non_signal_keeps_even_spread_ladder():
    import aegis

    ladder = aegis.Aegis._build_entry_ladder(
        direction="BUY",
        entry_low=4750.2,
        entry_high=4760.2,
        num_trades=4,
        source="AURUM",
    )
    assert ladder == [4750.2, 4753.53, 4756.87, 4760.2]


@pytest.mark.unit
def test_aegis_signal_buy_above_market_is_rejected_for_limit_policy():
    import aegis

    reason = aegis.Aegis._signal_limit_orientation_reject_reason(
        direction="BUY",
        entry_low=4773.5,
        entry_high=4774.5,
        current_price=4772.3,
        source="SIGNAL",
    )
    assert reason and reason.startswith("SIGNAL_BUY_LIMIT_REQUIRED")


@pytest.mark.unit
def test_aegis_signal_sell_below_market_is_rejected_for_limit_policy():
    import aegis

    reason = aegis.Aegis._signal_limit_orientation_reject_reason(
        direction="SELL",
        entry_low=4769.0,
        entry_high=4770.0,
        current_price=4772.3,
        source="SIGNAL",
    )
    assert reason and reason.startswith("SIGNAL_SELL_LIMIT_REQUIRED")


@pytest.mark.unit
def test_aegis_signal_limit_orientation_accepts_buy_below_market():
    import aegis

    reason = aegis.Aegis._signal_limit_orientation_reject_reason(
        direction="BUY",
        entry_low=4770.0,
        entry_high=4771.0,
        current_price=4772.3,
        source="SIGNAL",
    )
    assert reason is None
