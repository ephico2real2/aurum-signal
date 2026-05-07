from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from gate_diagnostics import (
    build_signal_gate_diagnostics,
    format_gate_diagnostics_herald_line,
)


def test_build_signal_gate_diagnostics_shape():
    now = time.time()
    d = build_signal_gate_diagnostics(
        status={"sentinel_active": False},
        sentinel={"block_trading": False},
        mt5={
            "timestamp_unix": now,
            "indicators_h1": {"ema_20": 2650.0, "ema_50": 2640.0, "rsi_14": 50.0},
        },
        regime_context={
            "label": "TREND_BULL",
            "confidence": 0.72,
            "entry_mode": "active",
            "apply_entry_policy": True,
            "entry_gate_reason": None,
        },
        bridge_mode="SIGNAL",
        trading_session_label="LONDON_NY",
        mt5_stale_sec=120,
        signal_id="sig-1",
        direction="BUY",
        reject_gate="AEGIS",
        reject_reason="min_rr",
    )
    assert d["schema"] == "signal_gate_diagnostics/v1"
    assert d["environment"]["mt5_fresh"] is True
    assert d["environment"]["environment_ok"] is True
    assert d["indicators_quick"]["h1_bias"] == "BULL"
    assert d["reject"]["gate"] == "AEGIS"
    assert d["reject"]["reason"] == "min_rr"
    assert d["regime"]["label"] == "TREND_BULL"


def test_build_flags_stale_and_sentinel():
    d = build_signal_gate_diagnostics(
        status={"sentinel_active": False},
        sentinel={"block_trading": True},
        mt5={"timestamp_unix": time.time() - 500},
        regime_context={},
        bridge_mode="WATCH",
        trading_session_label="ASIAN",
        mt5_stale_sec=120,
        reject_gate=None,
        reject_reason=None,
    )
    assert d["environment"]["sentinel_block"] is True
    assert d["environment"]["mt5_fresh"] is False
    assert "sentinel_block" in d["environment"]["failed_checks"]
    assert "mt5_stale" in d["environment"]["failed_checks"]


def test_format_herald_line():
    d = build_signal_gate_diagnostics(
        status={"sentinel_active": True},
        sentinel={"block_trading": False},
        mt5=None,
        regime_context={"entry_gate_reason": "stale_regime"},
        bridge_mode="SIGNAL",
        trading_session_label="LONDON",
        reject_gate="AEGIS",
        reject_reason="spread too wide",
    )
    line = format_gate_diagnostics_herald_line(d)
    assert line is not None
    assert "sentinel_block" in line
    assert "reg:stale_regime" in line
    assert "reject:AEGIS" in line
