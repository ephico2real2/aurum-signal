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
