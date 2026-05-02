"""Phase B: AEGIS regime counter-trend guard (docs/SCALPER_REGIME_PHASED_PLAN.md)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


@pytest.mark.unit
def test_countertrend_disabled_via_env(monkeypatch):
    import aegis

    monkeypatch.setenv("AEGIS_REGIME_COUNTERTREND_BLOCK", "false")
    r = aegis.Aegis._regime_countertrend_reject(
        "BUY",
        {"label": "TREND_BEAR", "confidence": 0.99, "apply_entry_policy": True},
        "SCALPER_SUBPATH_DIRECT",
    )
    assert r is None


@pytest.mark.unit
def test_countertrend_wrong_source_not_gated(monkeypatch):
    import aegis

    monkeypatch.setenv("AEGIS_REGIME_COUNTERTREND_BLOCK", "true")
    monkeypatch.setenv("AEGIS_REGIME_COUNTERTREND_SOURCES", "SCALPER_SUBPATH_DIRECT")
    r = aegis.Aegis._regime_countertrend_reject(
        "BUY",
        {"label": "TREND_BEAR", "confidence": 0.99, "apply_entry_policy": True},
        "SIGNAL",
    )
    assert r is None


@pytest.mark.unit
def test_countertrend_inactive_when_apply_policy_false(monkeypatch):
    import aegis

    monkeypatch.delenv("AEGIS_REGIME_COUNTERTREND_BLOCK", raising=False)
    r = aegis.Aegis._regime_countertrend_reject(
        "BUY",
        {"label": "TREND_BEAR", "confidence": 0.99, "apply_entry_policy": False},
        "SCALPER_SUBPATH_DIRECT",
    )
    assert r is None


@pytest.mark.unit
def test_countertrend_range_label_no_block(monkeypatch):
    import aegis

    r = aegis.Aegis._regime_countertrend_reject(
        "BUY",
        {"label": "RANGE", "confidence": 0.8, "apply_entry_policy": True},
        "SCALPER_SUBPATH_DIRECT",
    )
    assert r is None


@pytest.mark.unit
def test_countertrend_conf_below_min(monkeypatch):
    import aegis

    monkeypatch.setenv("AEGIS_REGIME_COUNTERTREND_MIN_CONFIDENCE", "0.80")
    r = aegis.Aegis._regime_countertrend_reject(
        "BUY",
        {"label": "TREND_BEAR", "confidence": 0.50, "apply_entry_policy": True},
        "SCALPER_SUBPATH_DIRECT",
    )
    assert r is None


@pytest.mark.unit
def test_countertrend_bear_blocks_buy(monkeypatch):
    import aegis

    monkeypatch.setenv("AEGIS_REGIME_COUNTERTREND_MIN_CONFIDENCE", "0.55")
    r = aegis.Aegis._regime_countertrend_reject(
        "BUY",
        {"label": "TREND_BEAR", "confidence": 0.72, "apply_entry_policy": True},
        "SCALPER_SUBPATH_DIRECT",
    )
    assert r is not None
    assert "REGIME_COUNTERTREND:TREND_BEAR_vs_BUY" in r


@pytest.mark.unit
def test_countertrend_bull_blocks_sell(monkeypatch):
    import aegis

    monkeypatch.setenv("AEGIS_REGIME_COUNTERTREND_MIN_CONFIDENCE", "0.55")
    r = aegis.Aegis._regime_countertrend_reject(
        "SELL",
        {"label": "TREND_BULL", "confidence": 0.66, "apply_entry_policy": True},
        "SCALPER_SUBPATH_DIRECT",
    )
    assert r is not None
    assert "REGIME_COUNTERTREND:TREND_BULL_vs_SELL" in r


@pytest.mark.unit
def test_countertrend_aligned_direction_passes(monkeypatch):
    import aegis

    r = aegis.Aegis._regime_countertrend_reject(
        "SELL",
        {"label": "TREND_BEAR", "confidence": 0.9, "apply_entry_policy": True},
        "SCALPER_SUBPATH_DIRECT",
    )
    assert r is None


@pytest.mark.unit
def test_extra_source_in_list(monkeypatch):
    import aegis

    monkeypatch.setenv("AEGIS_REGIME_COUNTERTREND_SOURCES", "AUTO_SCALPER,SCALPER_SUBPATH_DIRECT")
    r = aegis.Aegis._regime_countertrend_reject(
        "BUY",
        {"label": "TREND_BEAR", "confidence": 0.9, "apply_entry_policy": True},
        "AUTO_SCALPER",
    )
    assert r is not None
