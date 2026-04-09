"""
Each example in schemas/scribe_query_examples.json must run on an empty SCRIBE schema (no syntax errors).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from scribe import Scribe  # noqa: E402


@pytest.mark.unit
def test_scribe_example_queries_execute_on_empty_db(tmp_path):
    data = json.loads((ROOT / "schemas" / "scribe_query_examples.json").read_text(encoding="utf-8"))
    db = tmp_path / "empty_scribe.db"
    scribe = Scribe(str(db))
    for ex in data["examples"]:
        rows = scribe.query(ex["sql"])
        assert isinstance(rows, list), ex["id"]


@pytest.mark.unit
def test_scribe_query_limited_truncates(tmp_path):
    db = tmp_path / "lim.db"
    scribe = Scribe(str(db))
    for i in range(12):
        scribe.log_system_event("TEST_ROW", reason=str(i))
    rows, truncated = scribe.query_limited(
        "SELECT id FROM system_events ORDER BY id",
        max_rows=5,
    )
    assert len(rows) == 5
    assert truncated is True
    rows2, t2 = scribe.query_limited(
        "SELECT id FROM system_events ORDER BY id LIMIT 3",
        max_rows=50,
    )
    assert len(rows2) == 3
    assert t2 is False
