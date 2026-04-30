from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from aeb_executor import execute_action, execute_scribe_query, execute_shell_exec


def _seed_db(path: Path):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (n INTEGER)")
    conn.executemany("INSERT INTO t (n) VALUES (?)", [(1,), (2,), (3,), (4,)])
    conn.commit()
    conn.close()


@pytest.mark.unit
def test_execute_scribe_query_allows_read_select(tmp_path):
    db = tmp_path / "test.db"
    _seed_db(db)
    result = execute_scribe_query({"action": "SCRIBE_QUERY", "sql": "SELECT n FROM t ORDER BY n"}, db_path=str(db))
    assert result["ok"] is True
    assert result["count"] == 4
    assert result["rows"][0]["n"] == 1


@pytest.mark.unit
def test_execute_scribe_query_blocks_non_read_sql(tmp_path):
    db = tmp_path / "test.db"
    _seed_db(db)
    result = execute_scribe_query({"action": "SCRIBE_QUERY", "sql": "DELETE FROM t"}, db_path=str(db))
    assert result["ok"] is False
    assert result["security_blocked"] is True


@pytest.mark.unit
def test_execute_scribe_query_blocks_multi_statement(tmp_path):
    db = tmp_path / "test.db"
    _seed_db(db)
    result = execute_scribe_query(
        {"action": "SCRIBE_QUERY", "sql": "SELECT n FROM t; SELECT COUNT(*) FROM t"},
        db_path=str(db),
    )
    assert result["ok"] is False
    assert result["security_blocked"] is True


@pytest.mark.unit
def test_execute_scribe_query_row_cap_sets_truncated(tmp_path):
    db = tmp_path / "test.db"
    _seed_db(db)
    result = execute_scribe_query(
        {"action": "SCRIBE_QUERY", "sql": "SELECT n FROM t ORDER BY n", "max_rows": 2},
        db_path=str(db),
    )
    assert result["ok"] is True
    assert result["count"] == 2
    assert result["truncated"] is True


@pytest.mark.unit
def test_execute_shell_exec_allowlist_success(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    script = scripts_dir / "echo_ok.py"
    script.write_text("print('ok-from-script')\n", encoding="utf-8")

    monkeypatch.setenv("AEB_SHELL_EXEC_ALLOWED_PROGRAMS", "python3")
    monkeypatch.setenv("AEB_SHELL_EXEC_ALLOWED_PATH_PREFIXES", "scripts/")

    result = execute_shell_exec(
        {"action": "SHELL_EXEC", "program": "python3", "args": ["scripts/echo_ok.py"], "timeout_sec": 10},
        project_root=str(tmp_path),
    )
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert "ok-from-script" in result["stdout"]


@pytest.mark.unit
def test_execute_shell_exec_disallowed_program_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("AEB_SHELL_EXEC_ALLOWED_PROGRAMS", "python3")
    monkeypatch.setenv("AEB_SHELL_EXEC_ALLOWED_PATH_PREFIXES", "scripts/")
    result = execute_shell_exec(
        {"action": "SHELL_EXEC", "program": "bash", "args": ["-lc", "echo nope"]},
        project_root=str(tmp_path),
    )
    assert result["ok"] is False
    assert result["security_blocked"] is True


@pytest.mark.unit
def test_execute_shell_exec_legacy_cmd_uses_shell_false(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    script = scripts_dir / "echo_legacy.py"
    script.write_text("print('legacy')\n", encoding="utf-8")

    monkeypatch.setenv("AEB_SHELL_EXEC_ALLOWED_PROGRAMS", "python3")
    monkeypatch.setenv("AEB_SHELL_EXEC_ALLOWED_PATH_PREFIXES", "scripts/")

    captured: dict = {}

    def _fake_run(*args, **kwargs):
        captured["argv"] = args[0]
        captured["shell"] = kwargs.get("shell")
        return subprocess.CompletedProcess(args[0], 0, stdout="legacy\n", stderr="")

    monkeypatch.setattr("aeb_executor.subprocess.run", _fake_run)
    result = execute_shell_exec(
        {"action": "SHELL_EXEC", "cmd": "python3 scripts/echo_legacy.py"},
        project_root=str(tmp_path),
    )
    assert result["ok"] is True
    assert captured["shell"] is False
    assert captured["argv"][0] == "python3"


@pytest.mark.unit
def test_execute_action_aurum_exec_envelope_dispatches_nested_payload(tmp_path):
    db = tmp_path / "test.db"
    _seed_db(db)
    result = execute_action(
        {"action": "AURUM_EXEC", "payload": {"action": "SCRIBE_QUERY", "sql": "SELECT 1 AS ok"}},
        db_path=str(db),
        project_root=str(tmp_path),
    )
    assert result["ok"] is True
    assert result["action"] == "SCRIBE_QUERY"


@pytest.mark.unit
def test_execute_action_legacy_health_check_script_alias(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "health.py").write_text("print('ok')\n", encoding="utf-8")

    captured: dict = {}

    def _fake_run(*args, **kwargs):
        captured["argv"] = args[0]
        captured["shell"] = kwargs.get("shell")
        return subprocess.CompletedProcess(args[0], 0, stdout='{"overall":"OK","checks":[]}\n', stderr="")

    monkeypatch.setattr("aeb_executor.subprocess.run", _fake_run)
    result = execute_action(
        {"script": "health_check", "args": {}},
        db_path=str(tmp_path / "test.db"),
        project_root=str(tmp_path),
    )
    assert result["ok"] is True
    assert result["action"] == "HEALTH_CHECK"
    assert "overall=OK" in result["summary"]
    assert captured["shell"] is False
    assert str(scripts_dir / "health.py") in captured["argv"][1]
