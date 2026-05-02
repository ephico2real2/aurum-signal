import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_FILES = [
    ROOT / "python" / "bridge.py",
    ROOT / "python" / "athena_api.py",
    ROOT / "python" / "listener.py",
    ROOT / "python" / "reconciler.py",
    ROOT / "python" / "aurum.py",
    ROOT / "python" / "sentinel.py",
]


def test_no_bare_except_in_source_files():
    offenders = []
    for path in SOURCE_FILES:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                offenders.append((path.name, node.lineno))

    assert offenders == []
