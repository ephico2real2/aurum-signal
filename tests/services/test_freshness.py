from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


@pytest.mark.unit
def test_data_freshness_windows_are_defined():
    from freshness import DATA_FRESHNESS_WINDOWS

    assert set(DATA_FRESHNESS_WINDOWS) == {"MT5", "SENTINEL", "REGIME", "LENS"}
    for value in DATA_FRESHNESS_WINDOWS.values():
        assert isinstance(value, int)
        assert value > 0
