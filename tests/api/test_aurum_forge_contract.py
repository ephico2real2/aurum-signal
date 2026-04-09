"""
test_aurum_forge_contract.py — AURUM → BRIDGE → FORGE JSON contracts (no live server).

Validates:
  • config/aurum_cmd.json shapes AURUM/ATHENA may write
  • MT5/command.json OPEN_GROUP / CLOSE_ALL shapes FORGE.mq5 expects
  • normalize_aurum_open_trade (market / numeric entry / tp alias / lots)
  • bridge.Bridge delegates _normalize_aurum_open_trade to contracts
"""
from __future__ import annotations

import json
from pathlib import Path
import inspect

import pytest

from contracts.aurum_forge import (
    VALID_MODES,
    forge_open_group_from_bridge,
    normalize_aurum_open_trade,
    validate_aurum_cmd,
    validate_forge_command,
)


@pytest.mark.unit
class TestAurumCmdContract:
    def test_mode_change_valid(self):
        cmd = {
            "action": "MODE_CHANGE",
            "new_mode": "WATCH",
            "timestamp": "2026-04-06T12:00:00+00:00",
        }
        assert validate_aurum_cmd(cmd) == []

    def test_mode_change_invalid_mode(self):
        cmd = {
            "action": "MODE_CHANGE",
            "new_mode": "INVALID",
            "timestamp": "2026-04-06T12:00:00+00:00",
        }
        errs = validate_aurum_cmd(cmd)
        assert any("new_mode" in e for e in errs)

    def test_close_all_valid(self):
        cmd = {"action": "CLOSE_ALL", "timestamp": "2026-04-06T12:00:00+00:00"}
        assert validate_aurum_cmd(cmd) == []

    def test_open_group_valid(self):
        cmd = {
            "action": "OPEN_GROUP",
            "direction": "BUY",
            "entry_low": 2600.0,
            "entry_high": 2600.5,
            "sl": 2590.0,
            "tp1": 2620.0,
            "timestamp": "2026-04-06T12:00:00+00:00",
        }
        assert validate_aurum_cmd(cmd) == []

    def test_open_group_bad_direction(self):
        cmd = {
            "action": "OPEN_GROUP",
            "direction": "LONG",
            "entry_low": 1,
            "entry_high": 1,
            "sl": 1,
            "tp1": 1,
            "timestamp": "t",
        }
        assert validate_aurum_cmd(cmd)

    def test_valid_modes_matches_bridge(self):
        import bridge

        assert VALID_MODES == set(bridge.VALID_MODES)


@pytest.mark.unit
class TestForgeCommandContract:
    def test_open_group_canonical_passes(self):
        cmd = forge_open_group_from_bridge(
            group_id=42,
            direction="SELL",
            entry_ladder=[2650.0, 2651.0],
            lot_per_trade=0.05,
            sl=2660.0,
            tp1=2620.0,
            tp2=None,
            tp3=None,
            tp1_close_pct=70.0,
            move_be_on_tp1=True,
            timestamp="2026-04-06T12:00:00+00:00Z",
        )
        assert validate_forge_command(cmd) == []

    def test_close_all_passes(self):
        assert validate_forge_command(
            {"action": "CLOSE_ALL", "timestamp": "2026-04-06T12:00:00+00:00"}
        ) == []

    def test_open_group_missing_keys_fails(self):
        bad = {"action": "OPEN_GROUP", "group_id": 1}
        errs = validate_forge_command(bad)
        assert errs

    def test_json_roundtrip_stable(self):
        cmd = forge_open_group_from_bridge(
            group_id=1,
            direction="BUY",
            entry_ladder=[100.0],
            lot_per_trade=0.01,
            sl=99.0,
            tp1=101.0,
            tp2=102.0,
            tp3=None,
            tp1_close_pct=70,
            move_be_on_tp1=False,
            timestamp="t",
        )
        s = json.dumps(cmd)
        back = json.loads(s)
        assert validate_forge_command(back) == []


@pytest.mark.unit
class TestNormalizeAurumOpenTrade:
    def test_market_entry_uses_mid(self):
        cmd = {"action": "OPEN_TRADE", "direction": "BUY", "entry": "market", "sl": 1, "tp1": 2}
        mt5 = {"price": {"bid": 100.0, "ask": 104.0}}
        out = normalize_aurum_open_trade(cmd, mt5)
        assert out["action"] == "OPEN_GROUP"
        assert out["entry_low"] == 102.0
        assert out["entry_high"] == 102.0

    def test_numeric_entry(self):
        cmd = {"action": "OPEN_TRADE", "direction": "SELL", "entry": 2500.0, "sl": 1, "tp1": 2}
        out = normalize_aurum_open_trade(cmd, None)
        assert out["entry_low"] == 2500.0
        assert out["entry_high"] == 2500.0

    def test_tp_alias_and_lots(self):
        cmd = {
            "action": "OPEN_TRADE",
            "direction": "BUY",
            "entry": 1,
            "sl": 0.5,
            "tp": 1.5,
            "lots": 0.02,
        }
        out = normalize_aurum_open_trade(cmd, None)
        assert out["tp1"] == 1.5
        assert out["lot_per_trade"] == 0.02


@pytest.mark.unit
class TestBridgeUsesContractModule:
    def test_normalize_delegates_to_contracts(self):
        import bridge

        src = inspect.getsource(bridge.Bridge._normalize_aurum_open_trade)
        assert "normalize_aurum_open_trade" in src
        assert "contracts" in src


@pytest.mark.unit
def test_schema_bundle_version_matches_manifest():
    from contracts import SCHEMA_BUNDLE_VERSION

    man = json.loads(
        (Path(__file__).resolve().parents[2] / "schemas" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert man["version"] == SCHEMA_BUNDLE_VERSION


@pytest.mark.unit
class TestScribeModeVerifyScript:
    """Documentation / regression: OFF vs trading-mode SQLite behavior."""

    def test_verify_script_exists_and_mentions_off(self):
        script = Path(__file__).resolve().parents[2] / "scripts" / "verify_scribe_mode_writes.py"
        assert script.is_file()
        text = script.read_text(encoding="utf-8")
        assert "OFF" in text and "market_snapshots" in text and "LISTENER" in text
