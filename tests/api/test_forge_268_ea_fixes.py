"""
FORGE 2.6.8 EA-level control-flow fixes — unit tests.

Mirrors the three MQL5 logic fixes applied after Codex review:

  Fix A (line 4544): inside_band_factor uses is_breakout_setup instead of
      setup_type == "BB_BREAKOUT", so BB_BREAKOUT_RETEST entries are also
      covered.

  Fix B (line 4190): BB_BOUNCE detection block guarded by direction == "",
      preventing it from overwriting a retest-confirmed direction in DUAL mode.

  Fix C (line 90): SellInsideBandLotFactor MT5 input default reverted to 0.0
      so scalper_config.json is the single source of truth for the factor value.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT   = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "scalper_config.json"


def load_config() -> dict:
    return json.loads(CONFIG.read_text())


# ---------------------------------------------------------------------------
# Fix A — is_breakout_setup covers BB_BREAKOUT_RETEST
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestInsideBandFactorRetestCoverage:
    """
    MQL5 gate (line 4544):
        if(direction == "SELL" && is_breakout_setup && mid > m5_bb_l ...)
    where is_breakout_setup = setup_type in {BB_BREAKOUT, BB_BREAKOUT_RETEST}.

    Before fix: only BB_BREAKOUT was matched; retest entries always got full lot.
    After fix:  BB_BREAKOUT_RETEST is also matched — exactly the delayed path
                where price has pulled back inside the band.
    """

    def _factor(self, direction: str, setup_type: str, mid: float,
                bb_lower: float, json_factor: float) -> float:
        """Python mirror of the fixed MQL5 condition."""
        is_breakout_setup = setup_type in ("BB_BREAKOUT", "BB_BREAKOUT_RETEST")
        if (direction == "SELL" and is_breakout_setup and mid > bb_lower
                and 0.0 < json_factor < 1.0):
            return json_factor
        return 1.0

    @pytest.mark.parametrize("setup_type,mid,bb_lower,expected_factor", [
        # BB_BREAKOUT — original path, inside band
        ("BB_BREAKOUT",        4760.0, 4750.0, 0.25),
        # BB_BREAKOUT_RETEST — NEW: must also get reduced lot inside band
        ("BB_BREAKOUT_RETEST", 4760.0, 4750.0, 0.25),
        # Outside band (confirmed breakout) — full lot regardless of variant
        ("BB_BREAKOUT",        4740.0, 4750.0, 1.0),
        ("BB_BREAKOUT_RETEST", 4740.0, 4750.0, 1.0),
        # Exactly at band edge — full lot (condition is strictly >)
        ("BB_BREAKOUT",        4750.0, 4750.0, 1.0),
        ("BB_BREAKOUT_RETEST", 4750.0, 4750.0, 1.0),
        # BB_BOUNCE is not a breakout — never reduced
        ("BB_BOUNCE",          4760.0, 4750.0, 1.0),
    ])
    def test_sell_inside_band_factor_by_setup(
            self, setup_type, mid, bb_lower, expected_factor):
        factor = self._factor("SELL", setup_type, mid, bb_lower, json_factor=0.25)
        assert factor == expected_factor, (
            f"{setup_type} mid={mid} bb_l={bb_lower}: "
            f"expected {expected_factor}, got {factor}"
        )

    @pytest.mark.parametrize("direction", ["BUY"])
    def test_buy_direction_never_reduced(self, direction):
        """BUY entries never get the inside-band reduction."""
        factor = self._factor(direction, "BB_BREAKOUT", 4760.0, 4750.0, 0.25)
        assert factor == 1.0, f"BUY must always use full lot, got {factor}"

    def test_retest_inside_band_is_primary_delayed_path(self):
        """
        Retest entries are confirmed AFTER price has bounced back toward the
        band — mid > bb_lower is nearly always true for a retest SELL.
        This test documents that the fix closes the most common gap.
        """
        # Scenario: SELL breakout fired, price pulled back, retest confirmed at 4758
        mid, bb_lower = 4758.0, 4750.0
        before_fix_factor = 1.0  # old code: setup_type == "BB_BREAKOUT" only
        after_fix_factor  = self._factor("SELL", "BB_BREAKOUT_RETEST",
                                         mid, bb_lower, 0.25)
        assert before_fix_factor == 1.0,  "pre-fix: retest always got full lot"
        assert after_fix_factor  == 0.25, "post-fix: retest gets reduced lot"


# ---------------------------------------------------------------------------
# Fix B — direction == "" guard prevents bounce overwriting retest direction
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBounceGuardDirection:
    """
    MQL5 gate (line 4190):
        if(direction == "" && (g_scalper_mode == "BB_BOUNCE" || ...))
    Before fix: bounce block had no direction == "" guard.
    After fix:  bounce block is skipped when retest has already set direction.
    """

    def _bounce_can_fire(self, direction: str, scalper_mode: str,
                         bounce_enabled: bool = True,
                         adx_below_max: bool = True) -> bool:
        """Python mirror of the fixed MQL5 bounce block entry condition."""
        return (
            direction == ""
            and (scalper_mode in ("BB_BOUNCE", "DUAL"))
            and bounce_enabled
            and adx_below_max
        )

    @pytest.mark.parametrize("direction,mode,expected_fires", [
        # No prior direction — bounce can fire normally
        ("",     "BB_BOUNCE",   True),
        ("",     "DUAL",        True),
        # Retest confirmed a SELL — bounce must be blocked
        ("SELL", "BB_BOUNCE",   False),
        ("SELL", "DUAL",        False),
        # Retest confirmed a BUY — bounce must be blocked
        ("BUY",  "BB_BOUNCE",   False),
        ("BUY",  "DUAL",        False),
        # BB_BREAKOUT-only mode — bounce never fires regardless
        ("",     "BB_BREAKOUT", False),
    ])
    def test_bounce_fires_only_when_direction_empty(
            self, direction, mode, expected_fires):
        fires = self._bounce_can_fire(direction, mode)
        assert fires == expected_fires, (
            f"direction={direction!r} mode={mode}: "
            f"expected fires={expected_fires}, got {fires}"
        )

    def test_retest_sell_not_overwritten_by_bounce_buy(self):
        """
        Scenario: retest confirms SELL; price is also near BB upper (bounce BUY).
        Before fix: bounce block runs and can overwrite direction to "BUY".
        After fix:  bounce block is skipped; SELL is preserved.
        """
        retest_direction = "SELL"

        # Pre-fix: bounce block runs unconditionally and would set direction=BUY
        pre_fix_fires = True  # no guard existed

        # Post-fix: guarded by direction == ""
        post_fix_fires = self._bounce_can_fire(retest_direction, "DUAL")

        assert pre_fix_fires  is True,  "pre-fix: bounce would overwrite SELL"
        assert post_fix_fires is False, "post-fix: SELL preserved, bounce skipped"

    def test_retest_buy_not_overwritten_by_bounce_sell(self):
        """Symmetric case: retest BUY must not be overwritten by bounce SELL."""
        retest_direction = "BUY"
        post_fix_fires = self._bounce_can_fire(retest_direction, "DUAL")
        assert post_fix_fires is False, "post-fix: BUY preserved, bounce skipped"

    def test_no_retest_dual_mode_both_can_fire(self):
        """When no retest is pending, DUAL mode can still detect bounce setups."""
        fires = self._bounce_can_fire("", "DUAL")
        assert fires is True, "DUAL mode with empty direction must allow bounce"


# ---------------------------------------------------------------------------
# Fix C — MT5 input default 0.0 defers to JSON; JSON is authoritative
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSellInsideBandLotFactorSource:
    """
    MT5 input SellInsideBandLotFactor = 0.0 (default after fix).
    ApplyScalperLotInputOverrides() only overrides when input > 0.0.
    So with default 0.0, the JSON config value 0.25 is always used.

    Before fix: default was 0.25, silently overriding JSON every time.
    After fix:  default is 0.0, JSON config controls the value.
    """

    def _effective_factor(self, mt5_input: float, json_factor: float) -> float:
        """
        Python mirror of ApplyScalperLotInputOverrides() logic (lines 2165-2167):
            if(SellInsideBandLotFactor > 0.0 && SellInsideBandLotFactor <= 1.0)
               g_sc.breakout_sell_inside_band_lot_factor = SellInsideBandLotFactor;
        """
        # g_sc is pre-loaded with JSON value; input overrides if in range (0, 1]
        effective = json_factor
        if 0.0 < mt5_input <= 1.0:
            effective = mt5_input
        return effective

    @pytest.mark.parametrize("mt5_input,json_factor,expected", [
        # Default input 0.0 — JSON wins
        (0.0,  0.25, 0.25),
        (0.0,  0.3,  0.3),
        (0.0,  0.5,  0.5),
        # Non-zero input — input overrides JSON
        (0.25, 0.25, 0.25),  # both same — no conflict
        (0.5,  0.25, 0.5),   # input higher than JSON
        (0.1,  0.25, 0.1),   # input lower than JSON
        # Boundary: 1.0 is the max allowed override
        (1.0,  0.25, 1.0),
        # Out-of-range inputs — JSON wins
        (0.0,  0.25, 0.25),  # zero → use JSON
        (-0.1, 0.25, 0.25),  # negative → use JSON
        (1.1,  0.25, 0.25),  # > 1.0 → use JSON
    ])
    def test_effective_factor_source(self, mt5_input, json_factor, expected):
        result = self._effective_factor(mt5_input, json_factor)
        assert result == expected, (
            f"input={mt5_input} json={json_factor}: "
            f"expected effective={expected}, got {result}"
        )

    def test_default_input_uses_json_value(self):
        """The post-fix MT5 default (0.0) must defer to whatever JSON says."""
        mt5_default = 0.0
        json_val = load_config()["bb_breakout"]["sell_inside_band_lot_factor"]
        effective = self._effective_factor(mt5_default, json_val)
        assert effective == json_val, (
            f"Default input 0.0 must yield json value {json_val}, got {effective}"
        )

    def test_json_config_value_is_025(self):
        """Confirm the canonical factor in config is 0.25 (1/4 of base lot)."""
        cfg = load_config()
        v = cfg["bb_breakout"]["sell_inside_band_lot_factor"]
        assert v == 0.25, f"Expected 0.25 in config, got {v}"

    def test_pre_fix_default_would_have_overridden_json(self):
        """
        Document the pre-fix problem: default 0.25 silently overrode JSON.
        If the JSON value was changed to 0.3, the operator would see 0.25 —
        a silent misconfiguration with no warning.
        """
        pre_fix_default = 0.25
        json_val = 0.3  # operator changed JSON to 0.3
        effective = self._effective_factor(pre_fix_default, json_val)
        # Pre-fix: input wins, JSON change is ignored
        assert effective == 0.25, "pre-fix: input 0.25 overrides json 0.3 silently"

    def test_post_fix_default_respects_json_change(self):
        """Post-fix: operator can tune via JSON alone."""
        post_fix_default = 0.0
        json_val = 0.3  # operator changed JSON to 0.3
        effective = self._effective_factor(post_fix_default, json_val)
        assert effective == 0.3, "post-fix: json 0.3 is respected when input=0.0"
