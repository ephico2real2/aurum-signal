"""
test_json_schemas.py — File-bus JSON validates against schemas/files/*.schema.json.

HTTP API: use **schemas/openapi.yaml** + **GET /api/docs/** (tested in test_swagger_ui.py).

Requires: jsonschema (listed in requirements.txt).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"


def _load_schema(rel: str) -> dict:
    path = SCHEMAS / rel
    assert path.is_file(), f"missing schema {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _v(schema: dict):
    return Draft7Validator(schema)


@pytest.mark.unit
class TestFileBusSchemas:
    def test_forge_close_all(self):
        s = _load_schema("files/forge_command.schema.json")
        _v(s).validate({"action": "CLOSE_ALL", "timestamp": "2026-04-06T00:00:00Z"})

    def test_forge_cancel_group_pending(self):
        s = _load_schema("files/forge_command.schema.json")
        _v(s).validate(
            {
                "action": "CANCEL_GROUP_PENDING",
                "magic": 202425,
                "timestamp": "2026-04-06T00:00:00Z",
            }
        )

    def test_aurum_open_group_with_entry_legs(self):
        s = _load_schema("files/aurum_cmd.schema.json")
        _v(s).validate(
            {
                "action": "OPEN_GROUP",
                "direction": "BUY",
                "entry_legs": [
                    {"order_type": "BUY_STOP_LIMIT", "entry_price": 3310.0, "stoplimit_price": 3308.0}
                ],
                "sl": 3290.0,
                "tp1": 3330.0,
                "timestamp": "2026-04-06T00:00:00Z",
            }
        )

    def test_forge_open_group(self):
        s = _load_schema("files/forge_command.schema.json")
        _v(s).validate(
            {
                "action": "OPEN_GROUP",
                "group_id": 7,
                "direction": "BUY",
                "entry_ladder": [2600.0, 2600.5],
                "lot_per_trade": 0.05,
                "sl": 2590.0,
                "tp1": 2620.0,
                "tp2": None,
                "tp3": None,
                "tp1_close_pct": 70.0,
                "move_be_on_tp1": True,
                "timestamp": "2026-04-06T00:00:00Z",
            }
        )

    def test_aurum_mode_change(self):
        s = _load_schema("files/aurum_cmd.schema.json")
        _v(s).validate(
            {
                "action": "MODE_CHANGE",
                "new_mode": "WATCH",
                "reason": "test",
                "timestamp": "2026-04-06T00:00:00Z",
            }
        )


    def test_forge_open_group_with_entry_legs(self):
        s = _load_schema("files/forge_command.schema.json")
        _v(s).validate(
            {
                "action": "OPEN_GROUP",
                "group_id": 8,
                "direction": "SELL",
                "entry_legs": [
                    {"order_type": "SELL_STOP_LIMIT", "entry_price": 3290.0, "stoplimit_price": 3291.5}
                ],
                "lot_per_trade": 0.05,
                "sl": 3310.0,
                "tp1": 3270.0,
                "tp2": None,
                "tp3": None,
                "tp1_close_pct": 70.0,
                "move_be_on_tp1": True,
                "timestamp": "2026-04-06T00:00:00Z",
            }
        )
    def test_aurum_open_group(self):
        s = _load_schema("files/aurum_cmd.schema.json")
        _v(s).validate(
            {
                "action": "OPEN_GROUP",
                "direction": "SELL",
                "entry_low": 2650.0,
                "entry_high": 2650.5,
                "sl": 2660.0,
                "tp1": 2620.0,
                "timestamp": "2026-04-06T00:00:00Z",
            }
        )

    def test_status_minimal(self):
        s = _load_schema("files/status.schema.json")
        _v(s).validate(
            {
                "mode": "SIGNAL",
                "effective_mode": "SIGNAL",
                "timestamp": "2026-04-06T00:00:00Z",
            }
        )

    def test_market_data_minimal(self):
        s = _load_schema("files/market_data.schema.json")
        _v(s).validate({"timestamp_unix": 1_700_000_000.0})
