import json
import os
import tempfile


def atomic_write_json(path: str, data) -> None:
    """Write data as JSON atomically using a temp file + os.replace."""
    dir_ = os.path.dirname(os.path.abspath(path)) or "."
    with tempfile.NamedTemporaryFile(mode="w", dir=dir_, delete=False, suffix=".tmp") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
        tmp = f.name
    os.replace(tmp, path)
