"""FORGE Fix 7C: first-entry ATR-extension re-entry gate."""
from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EA = ROOT / "ea" / "FORGE.mq5"
DEFAULTS = ROOT / "config" / "scalper_config.defaults.json"
SYNC = ROOT / "scripts" / "sync_scalper_config_from_env.py"


@dataclass
class AtrExtGate:
    max_reentry_atr_ext: float = 0.0
    first_buy_entry_price: float = 0.0
    first_sell_entry_price: float = 0.0

    def gate_reason(self, direction: str, mid: float, m5_atr: float) -> str | None:
        if self.max_reentry_atr_ext > 0.0 and m5_atr > 0.0:
            if direction == "BUY" and self.first_buy_entry_price > 0.0:
                ext = (mid - self.first_buy_entry_price) / m5_atr
                if ext > self.max_reentry_atr_ext:
                    return "entry_quality_atr_ext"
            if direction == "SELL" and self.first_sell_entry_price > 0.0:
                ext = (self.first_sell_entry_price - mid) / m5_atr
                if ext > self.max_reentry_atr_ext:
                    return "entry_quality_atr_ext"
        return None

    def record_taken(self, direction: str, entry_price: float) -> None:
        if direction == "BUY" and self.first_buy_entry_price <= 0.0:
            self.first_buy_entry_price = entry_price
        if direction == "SELL" and self.first_sell_entry_price <= 0.0:
            self.first_sell_entry_price = entry_price

    def reset_session(self) -> None:
        self.first_buy_entry_price = 0.0
        self.first_sell_entry_price = 0.0


@pytest.mark.unit
class TestForge7CAtrExtensionGate:
    def test_gate_disabled_does_not_block_any_extension(self):
        gate = AtrExtGate(max_reentry_atr_ext=0.0, first_buy_entry_price=100.0)
        assert gate.gate_reason("BUY", mid=500.0, m5_atr=10.0) is None

    def test_first_buy_sets_anchor(self):
        gate = AtrExtGate(max_reentry_atr_ext=1.5)
        assert gate.first_buy_entry_price == 0.0
        gate.record_taken("BUY", entry_price=100.0)
        assert gate.first_buy_entry_price == 100.0

    def test_buy_reentry_within_limit_is_allowed(self):
        gate = AtrExtGate(max_reentry_atr_ext=1.5, first_buy_entry_price=100.0)
        assert gate.gate_reason("BUY", mid=112.0, m5_atr=10.0) is None

    def test_buy_reentry_at_exact_limit_is_allowed(self):
        gate = AtrExtGate(max_reentry_atr_ext=1.5, first_buy_entry_price=100.0)
        assert gate.gate_reason("BUY", mid=115.0, m5_atr=10.0) is None

    def test_buy_reentry_over_limit_is_blocked(self):
        gate = AtrExtGate(max_reentry_atr_ext=1.5, first_buy_entry_price=100.0)
        assert gate.gate_reason("BUY", mid=117.9, m5_atr=10.0) == "entry_quality_atr_ext"

    def test_sell_reentry_mirrors_downward_extension(self):
        gate = AtrExtGate(max_reentry_atr_ext=1.5, first_sell_entry_price=100.0)
        assert gate.gate_reason("SELL", mid=88.0, m5_atr=10.0) is None
        assert gate.gate_reason("SELL", mid=82.1, m5_atr=10.0) == "entry_quality_atr_ext"

    def test_anchor_does_not_update_on_subsequent_groups(self):
        gate = AtrExtGate(max_reentry_atr_ext=1.5)
        gate.record_taken("BUY", entry_price=100.0)
        gate.record_taken("BUY", entry_price=110.0)
        assert gate.first_buy_entry_price == 100.0

    def test_session_reset_clears_anchor_then_next_entry_sets_new_anchor(self):
        gate = AtrExtGate(max_reentry_atr_ext=1.5, first_buy_entry_price=100.0)
        gate.reset_session()
        assert gate.first_buy_entry_price == 0.0
        gate.record_taken("BUY", entry_price=120.0)
        assert gate.first_buy_entry_price == 120.0

    def test_gate_only_applies_when_atr_is_positive(self):
        gate = AtrExtGate(max_reentry_atr_ext=1.5, first_buy_entry_price=100.0)
        assert gate.gate_reason("BUY", mid=200.0, m5_atr=0.0) is None


@pytest.mark.unit
class TestForge7CWiring:
    def test_defaults_include_disabled_breakout_key(self):
        cfg = json.loads(DEFAULTS.read_text())
        assert cfg["bb_breakout"]["max_reentry_atr_ext"] == 0.0

    def test_env_mapping_targets_breakout_key(self):
        spec = importlib.util.spec_from_file_location("sync", str(SYNC))
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        assert mod.MAPPING["FORGE_BREAKOUT_MAX_REENTRY_ATR_EXT"] == (
            "bb_breakout",
            "max_reentry_atr_ext",
            "float",
            0.0,
            10.0,
        )

    def test_ea_contains_fix_7c_state_and_gate_reason(self):
        src = EA.read_text()
        assert "double g_first_buy_entry_price = 0.0;" in src
        assert "double g_first_sell_entry_price = 0.0;" in src
        assert "double breakout_max_reentry_atr_ext;" in src
        assert "g_sc.breakout_max_reentry_atr_ext = 0.0;" in src
        assert '"max_reentry_atr_ext"' in src
        assert '"entry_quality_atr_ext"' in src
        assert "(mid - g_first_buy_entry_price) / m5_atr" in src
        assert "(g_first_sell_entry_price - mid) / m5_atr" in src
        assert "g_first_buy_entry_price = 0.0;" in src
        assert "g_first_sell_entry_price = 0.0;" in src
