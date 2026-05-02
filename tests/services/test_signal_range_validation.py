import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from listener import _validate_signal_ranges


@pytest.mark.unit
def test_valid_xau_signal_passes():
    parsed = {
        "type": "ENTRY",
        "symbol": "XAUUSD",
        "entry_low": 4620,
        "entry_high": 4625,
        "sl": 4615,
        "tp1": 4630,
    }
    assert _validate_signal_ranges(parsed) == []


@pytest.mark.unit
def test_entry_low_above_entry_high_is_rejected():
    parsed = {"type": "ENTRY", "entry_low": 4625, "entry_high": 4620, "sl": 4615, "tp1": 4630}
    assert any("entry_low" in e and "<=" in e for e in _validate_signal_ranges(parsed))


@pytest.mark.unit
def test_zero_sl_is_rejected():
    parsed = {"type": "ENTRY", "entry_low": 4620, "entry_high": 4625, "sl": 0, "tp1": 4630}
    assert any("sl" in e and "> 0" in e for e in _validate_signal_ranges(parsed))


@pytest.mark.unit
def test_xau_entry_low_out_of_range_is_rejected():
    parsed = {"type": "ENTRY", "symbol": "GOLD", "entry_low": 500, "entry_high": 505, "sl": 495, "tp1": 510}
    assert any("XAU/GOLD" in e for e in _validate_signal_ranges(parsed))


@pytest.mark.unit
def test_non_xau_signal_positive_price_range_passes():
    parsed = {"type": "ENTRY", "symbol": "EURUSD", "entry_low": 1.08, "entry_high": 1.081, "sl": 1.075, "tp1": 1.09}
    assert _validate_signal_ranges(parsed) == []
