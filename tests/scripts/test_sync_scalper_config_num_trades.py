"""Tests for scripts/sync_scalper_config_from_env.py — lot_sizing min/max leg count."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import sync_scalper_config_from_env as sc  # noqa: E402


def _base_config() -> dict:
    return {
        "version": "1.0",
        "lot_sizing": {
            "lot_sizing_source": "AUTO",
            "fixed_lot": 0.02,
            "min_num_trades": 6,
            "max_num_trades": 6,
            "risk_pct": 2.0,
        },
    }


def test_sync_forge_min_max_updates_json():
    cfg = _base_config()
    env = {"FORGE_MIN_NUM_TRADES": "3", "FORGE_MAX_NUM_TRADES": "10"}
    n = sc.apply_scalper_env_overrides(env, cfg, emit=lambda _m: None)
    assert n >= 1
    assert cfg["lot_sizing"]["min_num_trades"] == 3
    assert cfg["lot_sizing"]["max_num_trades"] == 10


def test_sync_camel_case_forge_min_max():
    cfg = _base_config()
    env = {"forgeMinNumTrades": "4", "forgeMaxNumTrades": "8"}
    sc.apply_scalper_env_overrides(env, cfg, emit=lambda _: None)
    assert cfg["lot_sizing"]["min_num_trades"] == 4
    assert cfg["lot_sizing"]["max_num_trades"] == 8


def test_legacy_forge_num_trades_sets_min_max_equal_and_drops_deprecated_num_trades():
    cfg = _base_config()
    cfg["lot_sizing"]["num_trades"] = 8
    del cfg["lot_sizing"]["min_num_trades"]
    del cfg["lot_sizing"]["max_num_trades"]
    env = {"FORGE_NUM_TRADES": "5"}
    sc.apply_scalper_env_overrides(env, cfg, emit=lambda _: None)
    assert cfg["lot_sizing"]["min_num_trades"] == 5
    assert cfg["lot_sizing"]["max_num_trades"] == 5
    assert "num_trades" not in cfg["lot_sizing"]


def test_legacy_num_trades_skipped_when_min_or_max_env_set():
    cfg = _base_config()
    env = {"FORGE_NUM_TRADES": "9", "FORGE_MIN_NUM_TRADES": "3"}
    sc.apply_scalper_env_overrides(env, cfg, emit=lambda _: None)
    assert cfg["lot_sizing"]["min_num_trades"] == 3
    assert cfg["lot_sizing"]["max_num_trades"] == 6


def test_min_max_clamped_to_envelope():
    cfg = _base_config()
    env = {"FORGE_MIN_NUM_TRADES": "0", "FORGE_MAX_NUM_TRADES": "99"}
    sc.apply_scalper_env_overrides(env, cfg, emit=lambda _: None)
    assert cfg["lot_sizing"]["min_num_trades"] == 1
    assert cfg["lot_sizing"]["max_num_trades"] == 30


def test_empty_env_no_updates():
    cfg = _base_config()
    snapshot = {"min": cfg["lot_sizing"]["min_num_trades"], "max": cfg["lot_sizing"]["max_num_trades"]}
    n = sc.apply_scalper_env_overrides({}, cfg, emit=lambda _: None)
    assert n == 0
    assert cfg["lot_sizing"]["min_num_trades"] == snapshot["min"]
    assert cfg["lot_sizing"]["max_num_trades"] == snapshot["max"]
