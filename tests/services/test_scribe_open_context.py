"""SCRIBE trade_groups.open_context migration + JSON persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scribe import Scribe


@pytest.mark.unit
def test_log_trade_group_persists_open_context(tmp_path):
    db = tmp_path / "t.db"
    s = Scribe(str(db))
    payload = {
        "source": "SIGNAL",
        "direction": "BUY",
        "entry_low": 1.0,
        "entry_high": 1.1,
        "sl": 0.9,
        "tp1": 1.2,
        "num_trades": 2,
        "lot_per_trade": 0.01,
        "open_context": {
            "open_context_version": 1,
            "source": "SIGNAL",
            "regime": {"label": "TREND_BULL", "confidence": 0.8},
        },
    }
    gid = s.log_trade_group(payload, "SCALPER")
    rows = s.query("SELECT open_context FROM trade_groups WHERE id=?", (gid,))
    assert rows
    parsed = json.loads(rows[0]["open_context"])
    assert parsed["source"] == "SIGNAL"
    assert parsed["regime"]["label"] == "TREND_BULL"


@pytest.mark.unit
def test_open_context_oversized_stores_stub(monkeypatch, tmp_path):
    monkeypatch.setenv("SCRIBE_OPEN_CONTEXT_MAX_BYTES", "80")
    db = tmp_path / "t2.db"
    s = Scribe(str(db))
    huge = {"x": "y" * 500}
    gid = s.log_trade_group(
        {
            "source": "AURUM",
            "direction": "SELL",
            "entry_low": 2.0,
            "entry_high": 2.0,
            "sl": 2.1,
            "tp1": 1.9,
            "open_context": huge,
        },
        "HYBRID",
    )
    rows = s.query("SELECT open_context FROM trade_groups WHERE id=?", (gid,))
    parsed = json.loads(rows[0]["open_context"])
    assert parsed.get("truncated") is True
