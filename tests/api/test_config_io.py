import json
import os
import sys
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "python"))

from config_io import atomic_write_json  # noqa: E402


def test_atomic_write_json_creates_file(tmp_path):
    path = tmp_path / "config.json"
    data = {"mode": "WATCH", "risk": 1}

    atomic_write_json(str(path), data)

    assert path.exists()
    assert json.loads(path.read_text()) == data


def test_atomic_write_json_is_atomic(tmp_path):
    path = tmp_path / "config.json"
    data = {"mode": "SIGNAL"}

    with mock.patch("config_io.os.replace", wraps=os.replace) as replace:
        atomic_write_json(str(path), data)

    replace.assert_called_once()
    assert json.loads(path.read_text()) == data


def test_atomic_write_json_cleans_up_on_error(tmp_path):
    path = tmp_path / "config.json"

    with mock.patch("config_io.json.dump", side_effect=TypeError("not serializable")):
        try:
            atomic_write_json(str(path), object())
        except TypeError:
            pass

    assert not path.exists()
