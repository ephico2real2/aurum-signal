import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


def _time_sleep_calls_inside_async(path: Path) -> int:
    tree = ast.parse(path.read_text())
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "sleep"
                and isinstance(child.func.value, ast.Name)
                and child.func.value.id == "time"
            ):
                count += 1
    return count


def test_no_time_sleep_in_async_handlers():
    files = [ROOT / "python" / "listener.py", ROOT / "python" / "aurum.py"]
    assert sum(_time_sleep_calls_inside_async(path) for path in files) == 0
