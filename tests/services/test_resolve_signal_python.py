"""install_services.resolve_signal_python — .venv vs SIGNAL_PYTHON vs PATH."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "services"
sys.path.insert(0, str(SERVICES))

import install_services  # noqa: E402


@pytest.mark.unit
def test_resolve_prefers_signal_python_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNAL_PYTHON", str(sys.executable))
    p = install_services.resolve_signal_python(tmp_path)
    assert p == str(Path(sys.executable).expanduser())


@pytest.mark.unit
def test_resolve_prefers_venv_when_no_env(tmp_path, monkeypatch):
    monkeypatch.delenv("SIGNAL_PYTHON", raising=False)
    vpy = tmp_path / ".venv" / "bin" / "python"
    vpy.parent.mkdir(parents=True)
    vpy.write_bytes(b"")
    assert install_services.resolve_signal_python(tmp_path) == str(vpy)


@pytest.mark.unit
def test_inject_signal_python_replaces_placeholder():
    project = ROOT
    py = install_services.resolve_signal_python(project)
    out = install_services.inject_signal_python("__SIGNAL_PYTHON__", project)
    assert out == py
