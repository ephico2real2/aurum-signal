import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def _load_reconciler(monkeypatch, base: int = 202401, max_offset: int = 9999):
    monkeypatch.setenv("FORGE_MAGIC_NUMBER", str(base))
    monkeypatch.setenv("FORGE_MAGIC_MAX", str(max_offset))
    import reconciler

    return importlib.reload(reconciler)


@pytest.mark.unit
def test_forge_magic_boundaries(monkeypatch):
    reconciler = _load_reconciler(monkeypatch, 202401, 9999)

    assert reconciler._is_forge_magic(202401)
    assert reconciler._is_forge_magic(202401 + 9999)
    assert not reconciler._is_forge_magic(202400)
    assert not reconciler._is_forge_magic(202401 + 9999 + 1)


@pytest.mark.unit
def test_custom_forge_magic_number_shifts_range(monkeypatch):
    reconciler = _load_reconciler(monkeypatch, 303000, 10)

    assert reconciler._is_forge_magic(303000)
    assert reconciler._is_forge_magic(303010)
    assert not reconciler._is_forge_magic(302999)
    assert not reconciler._is_forge_magic(303011)
