from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

import aegis  # noqa: E402


@pytest.fixture(autouse=True)
def clear_trades_env(monkeypatch):
    for k in (
        "AEGIS_MIN_NUM_TRADES",
        "AEGIS_MAX_NUM_TRADES",
        "aegisMinNumTrades",
        "aegisMaxNumTrades",
    ):
        monkeypatch.delenv(k, raising=False)


def test_trades_envelope_legacy_collapses_to_base(monkeypatch):
    monkeypatch.delenv("AEGIS_MIN_NUM_TRADES", raising=False)
    monkeypatch.delenv("AEGIS_MAX_NUM_TRADES", raising=False)
    lo, hi, active = aegis.trades_envelope_bounds(8)
    assert active is False
    assert lo == hi == 8


def test_trades_envelope_partial_defaults(monkeypatch):
    monkeypatch.setenv("AEGIS_MIN_NUM_TRADES", "4")
    monkeypatch.delenv("AEGIS_MAX_NUM_TRADES", raising=False)
    lo, hi, active = aegis.trades_envelope_bounds(8)
    assert active is True
    assert lo == 4
    assert hi == 20


def test_trades_envelope_camel_case_env_aliases(monkeypatch):
    monkeypatch.delenv("AEGIS_MIN_NUM_TRADES", raising=False)
    monkeypatch.delenv("AEGIS_MAX_NUM_TRADES", raising=False)
    monkeypatch.setenv("aegisMinNumTrades", "3")
    monkeypatch.setenv("aegisMaxNumTrades", "7")
    lo, hi, active = aegis.trades_envelope_bounds(8)
    assert active is True
    assert lo == 3
    assert hi == 7


def test_resolve_single_point_returns_envelope_pin(monkeypatch):
    monkeypatch.setenv("AEGIS_MIN_NUM_TRADES", "5")
    monkeypatch.setenv("AEGIS_MAX_NUM_TRADES", "5")
    lo, hi, active = aegis.trades_envelope_bounds(8)
    n, reason = aegis.resolve_num_trades(
        8,
        lo,
        hi,
        active,
        {},
        {"balance": 10000, "equity": 10000},
        None,
        None,
        1.0,
        0.0,
    )
    assert n == 5
    assert "env_pin" in reason


def test_resolve_wide_envelope_scale_down_reduces(monkeypatch):
    monkeypatch.setenv("AEGIS_MIN_NUM_TRADES", "3")
    monkeypatch.setenv("AEGIS_MAX_NUM_TRADES", "12")
    lo, hi, active = aegis.trades_envelope_bounds(8)
    n, reason = aegis.resolve_num_trades(
        8,
        lo,
        hi,
        active,
        {},
        {"balance": 10000, "equity": 10000},
        None,
        None,
        0.5,
        0.0,
    )
    assert n < 8
    assert "scale_down" in reason
    assert lo <= n <= hi


def test_validate_respects_envelope_and_policy(monkeypatch):
    monkeypatch.setenv("AEGIS_MIN_NUM_TRADES", "2")
    monkeypatch.setenv("AEGIS_MAX_NUM_TRADES", "4")
    ag = aegis.Aegis()
    sig = {
        "direction": "BUY",
        "entry_low": 3180.0,
        "entry_high": 3182.0,
        "sl": 3170.0,
        "tp1": 3200.0,
        "source": "SIGNAL",
        "num_trades": 10,
    }
    acc = {"balance": 10000.0, "equity": 10000.0, "open_groups_count": 0}
    r = ag.validate(sig, acc, 3181.0, mt5_data=None, regime_context=None)
    assert r.approved
    assert 2 <= r.num_trades <= 4
    assert r.trades_policy_reason
    assert r.trades_envelope_min == 2
    assert r.trades_envelope_max == 4
