import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "python"))


def test_mcp_client_raises_on_timeout():
    import mcp_client  # noqa: WPS433

    proc = SimpleNamespace(
        stdout=object(),
        kill=mock.Mock(),
    )
    session = mcp_client.MCPSession(timeout=15)
    session.proc = proc

    with mock.patch("mcp_client.select.select", return_value=([], [], [])):
        try:
            session._read_response()
        except mcp_client.MCPTimeoutError:
            pass
        else:
            raise AssertionError("MCPTimeoutError was not raised")

    proc.kill.assert_called_once()


def test_lens_returns_stale_on_subprocess_timeout(monkeypatch):
    import lens  # noqa: WPS433

    monkeypatch.setattr(lens.shutil, "which", lambda name: "/usr/bin/tv")
    monkeypatch.setattr(
        lens.subprocess,
        "run",
        mock.Mock(side_effect=subprocess.TimeoutExpired(cmd=["tv"], timeout=15)),
    )

    inst = object.__new__(lens.Lens)
    inst._cache = None
    result = inst._tv_brief_from_cli()

    assert result["stale"] is True
