"""Phase E: optional AEGIS regime-conditioned lot scale multiplier (env-gated)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

import aegis  # noqa: E402


@pytest.fixture(autouse=True)
def clear_regime_lot_scale_env(monkeypatch):
    monkeypatch.delenv("AEGIS_REGIME_LOT_SCALE_ENABLED", raising=False)
    monkeypatch.delenv("AEGIS_SCALE_COMBINED_MAX", raising=False)


def test_regime_lot_scale_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AEGIS_REGIME_LOT_SCALE_ENABLED", raising=False)
    m, note = aegis.Aegis._regime_lot_scale_mult(
        "BUY",
        {"label": "TREND_BULL", "confidence": 0.95, "stale": False},
        {},
    )
    assert m == 1.0
    assert "off" in note


def test_regime_lot_scale_aligned_trend_bull_buy(monkeypatch):
    monkeypatch.setenv("AEGIS_REGIME_LOT_SCALE_ENABLED", "true")
    monkeypatch.setenv("AEGIS_REGIME_LOT_SCALE_MAX", "1.3")
    m, note = aegis.Aegis._regime_lot_scale_mult(
        "BUY",
        {"label": "TREND_BULL", "confidence": 0.92, "stale": False},
        {},
    )
    assert m > 1.01
    assert "aligned" in note


def test_regime_lot_scale_range_reduces(monkeypatch):
    monkeypatch.setenv("AEGIS_REGIME_LOT_SCALE_ENABLED", "true")
    monkeypatch.setenv("AEGIS_REGIME_LOT_SCALE_RANGE_MULT", "0.9")
    m, note = aegis.Aegis._regime_lot_scale_mult(
        "BUY",
        {"label": "RANGE", "confidence": 0.8, "stale": False},
        {},
    )
    assert m < 1.0
    assert "range" in note


def test_regime_lot_scale_stale_is_neutral(monkeypatch):
    monkeypatch.setenv("AEGIS_REGIME_LOT_SCALE_ENABLED", "true")
    m, _ = aegis.Aegis._regime_lot_scale_mult(
        "BUY",
        {"label": "TREND_BULL", "confidence": 0.99, "stale": True},
        {},
    )
    assert m == 1.0


def test_validate_applies_combined_cap(monkeypatch):
    monkeypatch.setenv("AEGIS_REGIME_LOT_SCALE_ENABLED", "true")
    monkeypatch.setenv("AEGIS_REGIME_LOT_SCALE_MAX", "2.0")
    monkeypatch.setenv("AEGIS_SCALE_COMBINED_MAX", "1.25")
    ag = aegis.Aegis()
    sig = {
        "direction": "BUY",
        "entry_low": 3180.0,
        "entry_high": 3182.0,
        "sl": 3170.0,
        "tp1": 3200.0,
        "source": "SIGNAL",
        "lot_per_trade": 0.02,
        "num_trades": 4,
    }
    acc = {"balance": 100000.0, "equity": 100000.0, "open_groups_count": 0}
    ctx = {"label": "TREND_BULL", "confidence": 0.99, "stale": False}
    r = ag.validate(sig, acc, 3181.0, mt5_data=None, regime_context=ctx)
    assert r.approved
    assert r.scale_factor <= 1.25 + 1e-6
