"""
FORGE 2.6.8 gate fixes — unit tests.

Tests cover:
  Phase A (config):
    - adx_min raised to 20 (no ranging-tape breakouts)
    - rsi_sell_floor raised to 33 (exhaustion zone + float fix)
    - bounce_htf_bias set to STRICT (no bounce SELL against H1/M15 uptrend)

  Phase B (MQL5 gates — tested via config contract):
    - adx_sell_floor_threshold / rsi_sell_floor_weak_adx present and valid
    - sell_inside_band_lot_factor present and in (0, 1]

  Sync script:
    - All new env vars map to correct config paths
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "scalper_config.json"
DEFAULTS = ROOT / "config" / "scalper_config.defaults.json"
SYNC = ROOT / "scripts" / "sync_scalper_config_from_env.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config(path: Path) -> dict:
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Phase A — config values
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPhaseAConfigValues:

    def test_version_is_268(self):
        cfg = load_config(CONFIG)
        assert cfg["version"] == "2.6.8", f"Expected 2.6.8, got {cfg['version']}"

    def test_adx_min_raised_to_20(self):
        cfg = load_config(CONFIG)
        v = cfg["bb_breakout"]["adx_min"]
        assert v == 20, f"adx_min should be 20 (no ranging-tape breakouts), got {v}"

    def test_adx_min_defaults_raised_to_20(self):
        cfg = load_config(DEFAULTS)
        v = cfg["bb_breakout"]["adx_min"]
        assert v == 20, f"defaults adx_min should be 20, got {v}"

    def test_rsi_sell_floor_raised_to_33(self):
        cfg = load_config(CONFIG)
        v = cfg["bb_breakout"]["rsi_sell_floor"]
        assert v == 33, f"rsi_sell_floor should be 33, got {v}"

    def test_rsi_sell_floor_defaults_raised_to_33(self):
        cfg = load_config(DEFAULTS)
        v = cfg["bb_breakout"]["rsi_sell_floor"]
        assert v == 33, f"defaults rsi_sell_floor should be 33, got {v}"

    def test_bounce_htf_bias_is_strict(self):
        cfg = load_config(CONFIG)
        v = cfg["bb_bounce"]["bounce_htf_bias"]
        assert v == "STRICT", f"bounce_htf_bias should be STRICT, got {v}"

    def test_bounce_htf_bias_defaults_is_strict(self):
        cfg = load_config(DEFAULTS)
        v = cfg["bb_bounce"]["bounce_htf_bias"]
        assert v == "STRICT", f"defaults bounce_htf_bias should be STRICT, got {v}"

    def test_rsi_buy_ceil_unchanged_at_70(self):
        """Ceiling stays at 70 — May 6-7 data confirmed do not raise."""
        cfg = load_config(CONFIG)
        v = cfg["bb_breakout"]["rsi_buy_ceil"]
        assert v == 70, f"rsi_buy_ceil must remain 70, got {v}"


# ---------------------------------------------------------------------------
# Phase B — new config keys present and in valid range
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPhaseBConfigKeys:

    def test_adx_sell_floor_threshold_present(self):
        cfg = load_config(CONFIG)
        assert "adx_sell_floor_threshold" in cfg["bb_breakout"], \
            "bb_breakout.adx_sell_floor_threshold missing from config"

    def test_adx_sell_floor_threshold_value(self):
        cfg = load_config(CONFIG)
        v = cfg["bb_breakout"]["adx_sell_floor_threshold"]
        assert 15.0 <= v <= 80.0, f"adx_sell_floor_threshold={v} out of range [15, 80]"
        assert v == 35.0, f"Expected 35.0, got {v}"

    def test_rsi_sell_floor_weak_adx_present(self):
        cfg = load_config(CONFIG)
        assert "rsi_sell_floor_weak_adx" in cfg["bb_breakout"], \
            "bb_breakout.rsi_sell_floor_weak_adx missing from config"

    def test_rsi_sell_floor_weak_adx_value(self):
        cfg = load_config(CONFIG)
        v = cfg["bb_breakout"]["rsi_sell_floor_weak_adx"]
        assert v > cfg["bb_breakout"]["rsi_sell_floor"], \
            "rsi_sell_floor_weak_adx must be stricter (higher) than rsi_sell_floor"
        assert v == 36.0, f"Expected 36.0, got {v}"

    def test_sell_inside_band_lot_factor_present(self):
        cfg = load_config(CONFIG)
        assert "sell_inside_band_lot_factor" in cfg["bb_breakout"], \
            "bb_breakout.sell_inside_band_lot_factor missing from config"

    def test_sell_inside_band_lot_factor_range(self):
        cfg = load_config(CONFIG)
        v = cfg["bb_breakout"]["sell_inside_band_lot_factor"]
        assert 0.0 < v <= 1.0, f"sell_inside_band_lot_factor={v} must be in (0, 1]"
        assert v == 0.25, f"Expected 0.25, got {v}"

    def test_all_phase_b_keys_in_defaults(self):
        cfg = load_config(DEFAULTS)
        bo = cfg["bb_breakout"]
        for key in ("adx_sell_floor_threshold", "rsi_sell_floor_weak_adx", "sell_inside_band_lot_factor"):
            assert key in bo, f"defaults missing bb_breakout.{key}"


# ---------------------------------------------------------------------------
# Gate logic — boundary assertions (pure Python, mirrors MQL5 gate logic)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGateLogicBoundaries:
    """
    Mirror the MQL5 gate decisions in Python for fast regression testing.
    Each test names the exact gate_reason the EA would journal.
    """

    # --- adx_min gate ---

    @pytest.mark.parametrize("adx,expected_pass", [
        (19.9, False),   # below new floor — false breakout in ranging market
        (20.0, True),    # exactly at floor — allowed
        (25.0, True),    # clear trend
        (14.0, False),   # old floor — now blocked
    ])
    def test_adx_min_gate(self, adx, expected_pass):
        adx_min = 20.0
        passes = adx >= adx_min
        assert passes == expected_pass, \
            f"ADX={adx}: expected pass={expected_pass}, got {passes}"

    # --- rsi_sell_floor absolute gate ---

    @pytest.mark.parametrize("rsi,expected_skip", [
        (30.0, True),    # float boundary — now safely below floor=33
        (32.9, True),    # below 33 — exhaustion zone
        (33.0, True),    # exactly at floor — gate uses <= so blocked
        (33.01, False),  # just above floor — allowed
        (34.0, False),   # above floor
        (40.0, False),   # healthy momentum
    ])
    def test_rsi_sell_floor_absolute(self, rsi, expected_skip):
        floor = 33.0
        skipped = rsi <= floor
        assert skipped == expected_skip, \
            f"RSI={rsi}: expected skip={expected_skip}, got {skipped}"

    # --- ADX-conditioned floor (Fix 5) ---

    @pytest.mark.parametrize("adx,rsi,expected_gate", [
        # strong trend — only absolute floor applies
        (40.0, 34.0, None),                                     # ADX>=35, RSI=34 > floor=33 → pass
        (40.0, 32.0, "entry_quality_rsi_sell_floor"),           # ADX>=35, RSI=32 <= 33 → absolute floor
        # weak trend — stricter floor applies
        (25.0, 36.1, None),                                     # ADX<35, RSI=36.1 > weak_floor=36 → pass
        (25.0, 36.0, "entry_quality_rsi_sell_adx_floor"),       # ADX<35, RSI=36 <= 36 → ADX floor
        (25.0, 32.0, "entry_quality_rsi_sell_adx_floor"),       # ADX<35, RSI=32 — hits both, ADX reason
        (34.9, 35.5, "entry_quality_rsi_sell_adx_floor"),       # just below threshold, RSI 35.5 <= 36
    ])
    def test_adx_conditioned_floor(self, adx, rsi, expected_gate):
        floor = 33.0
        threshold = 35.0
        weak_floor = 36.0

        effective_floor = floor
        weak_adx = adx < threshold
        if weak_adx:
            effective_floor = max(floor, weak_floor)

        if rsi <= effective_floor:
            gate = ("entry_quality_rsi_sell_adx_floor"
                    if weak_adx and effective_floor >= weak_floor
                    else "entry_quality_rsi_sell_floor")
        else:
            gate = None

        assert gate == expected_gate, \
            f"ADX={adx} RSI={rsi}: expected gate={expected_gate!r}, got {gate!r}"

    # --- inside-band lot factor (Fix 7) ---

    @pytest.mark.parametrize("mid,bb_lower,direction,setup,expected_factor", [
        # quarter lot fires when mid > bb_lower (price pulled back INSIDE the band)
        (4760.0, 4750.0, "SELL", "BB_BREAKOUT", 0.25),  # mid=4760 > bb_l=4750 → inside band → quarter lot
        (4750.1, 4750.0, "SELL", "BB_BREAKOUT", 0.25),  # just above bb_lower → quarter lot
        # full lot when mid <= bb_lower (confirmed breakout, price still outside/at band)
        (4740.0, 4750.0, "SELL", "BB_BREAKOUT", 1.0),  # mid=4740 < bb_l=4750 → below band → full lot
        (4750.0, 4750.0, "SELL", "BB_BREAKOUT", 1.0),  # mid exactly at bb_lower → full lot (not strictly >)
        (4760.0, 4750.0, "BUY",  "BB_BREAKOUT", 1.0),  # BUY → factor not applied
        (4760.0, 4750.0, "SELL", "BB_BOUNCE",   1.0),  # BB_BOUNCE → factor not applied
    ])
    def test_inside_band_lot_factor(self, mid, bb_lower, direction, setup, expected_factor):
        inside_band_factor = 0.25
        factor = 1.0
        if direction == "SELL" and setup == "BB_BREAKOUT" and mid > bb_lower:
            factor = inside_band_factor
        assert factor == expected_factor, \
            f"mid={mid} bb_l={bb_lower} {direction}/{setup}: expected factor={expected_factor}, got {factor}"

    # --- bounce_htf_bias STRICT ---

    @pytest.mark.parametrize("h1_bull,h1_bear,m15_bull,m15_bear,direction,expected_ok", [
        # SELL bounce: allowed only when NEITHER H1 NOR M15 is bullish
        (False, True,  False, True,  "SELL", True),   # H1 bear, M15 bear → SELL ok
        (False, False, False, False, "SELL", True),   # both flat → SELL ok
        (True,  False, False, False, "SELL", False),  # H1 bull → SELL blocked
        (False, False, True,  False, "SELL", False),  # M15 bull → SELL blocked
        (True,  False, True,  False, "SELL", False),  # both bull → SELL blocked
        # BUY bounce: allowed only when NEITHER H1 NOR M15 is bearish
        (True,  False, True,  False, "BUY",  True),   # H1 bull, M15 bull → BUY ok
        (False, True,  False, False, "BUY",  False),  # H1 bear → BUY blocked
        (False, False, False, True,  "BUY",  False),  # M15 bear → BUY blocked
        (False, False, False, False, "BUY",  True),   # both flat → BUY ok
    ])
    def test_bounce_strict_htf_logic(self, h1_bull, h1_bear, m15_bull, m15_bear,
                                     direction, expected_ok):
        # STRICT = mode 2: !h1_bear && !m15_bear for BUY; !h1_bull && !m15_bull for SELL
        if direction == "BUY":
            ok = (not h1_bear) and (not m15_bear)
        else:
            ok = (not h1_bull) and (not m15_bull)
        assert ok == expected_ok, \
            f"{direction} h1_bull={h1_bull} h1_bear={h1_bear} m15_bull={m15_bull} m15_bear={m15_bear}: " \
            f"expected ok={expected_ok}, got {ok}"

    # --- sell-off scenario: STRICT does not block SELL bounces during downtrend ---

    def test_strict_allows_sell_bounce_during_selloff(self):
        """During a huge sell-off H1 is bearish → NOT bullish → SELL bounce ok."""
        h1_bull = False   # H1 is bearish during sell-off
        m15_bull = False  # M15 also bearish
        ok = (not h1_bull) and (not m15_bull)
        assert ok is True, "STRICT must allow SELL bounce when H1 and M15 are not bullish"

    def test_strict_blocks_buy_bounce_during_selloff(self):
        """During sell-off H1 is bearish → BUY bounce blocked — prevents dip-buying into waterfall."""
        h1_bear = True
        m15_bear = True
        ok = (not h1_bear) and (not m15_bear)
        assert ok is False, "STRICT must block BUY bounce when H1 or M15 is bearish"


# ---------------------------------------------------------------------------
# Sync script — env var coverage
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSyncScriptEnvMappings:

    def _load_mapping(self) -> dict:
        import importlib.util
        spec = importlib.util.spec_from_file_location("sync", str(SYNC))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.MAPPING

    def test_adx_sell_floor_threshold_mapped(self):
        m = self._load_mapping()
        assert "FORGE_BREAKOUT_ADX_SELL_FLOOR_THRESHOLD" in m
        section, key, typ, lo, hi = m["FORGE_BREAKOUT_ADX_SELL_FLOOR_THRESHOLD"]
        assert section == "bb_breakout"
        assert key == "adx_sell_floor_threshold"
        assert lo <= 35.0 <= hi

    def test_rsi_sell_floor_weak_adx_mapped(self):
        m = self._load_mapping()
        assert "FORGE_BREAKOUT_RSI_SELL_FLOOR_WEAK_ADX" in m
        section, key, typ, lo, hi = m["FORGE_BREAKOUT_RSI_SELL_FLOOR_WEAK_ADX"]
        assert section == "bb_breakout"
        assert key == "rsi_sell_floor_weak_adx"
        assert lo <= 36.0 <= hi

    def test_sell_inside_band_lot_factor_mapped(self):
        m = self._load_mapping()
        assert "FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR" in m
        section, key, typ, lo, hi = m["FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR"]
        assert section == "bb_breakout"
        assert key == "sell_inside_band_lot_factor"
        assert lo > 0.0 and hi <= 1.0

    def test_all_268_env_keys_present(self):
        """Regression: all 2.6.8 env keys must be in MAPPING."""
        m = self._load_mapping()
        required = {
            "FORGE_BREAKOUT_ADX_MIN",              # raised to 20
            "FORGE_BREAKOUT_RSI_SELL_FLOOR",       # raised to 33
            "FORGE_BOUNCE_HTF_BIAS",               # changed to STRICT
            "FORGE_BREAKOUT_RSI_BUY_CEIL",         # kept at 70
            "FORGE_BREAKOUT_ADX_SELL_FLOOR_THRESHOLD",
            "FORGE_BREAKOUT_RSI_SELL_FLOOR_WEAK_ADX",
            "FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR",
        }
        missing = required - set(m.keys())
        assert not missing, f"Missing env mappings: {missing}"
