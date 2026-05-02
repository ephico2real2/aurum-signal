from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


log = logging.getLogger("aeb_executor")

_AEB_ACTIONS = {"SCRIBE_QUERY", "SHELL_EXEC", "AURUM_EXEC", "HEALTH_CHECK", "ANALYSIS_RUN"}
_SQL_READ_PREFIX_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        v = default
    return max(lo, min(v, hi))


def _env_csv(name: str, default_csv: str) -> list[str]:
    raw = (os.environ.get(name) or default_csv).strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x and x.strip()]


def _truncate_text(value: str | None, max_chars: int) -> str:
    text = (value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 24] + "\n...(truncated)"


def _safe_subprocess_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
    }


def _warn_if_slow(started: float) -> None:
    elapsed = time.monotonic() - started
    if elapsed > 5:
        log.warning("AEB exec slow: %.1fs", elapsed)


def _normalize_legacy_aeb_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return payload
    action = str(payload.get("action") or "").upper().strip()
    if action:
        return payload
    script = str(payload.get("script") or "").strip().lower()
    if script == "health_check":
        normalized = dict(payload)
        normalized["action"] = "HEALTH_CHECK"
        return normalized
    return payload


def _result(
    *,
    ok: bool,
    action: str,
    summary: str,
    error: str | None = None,
    security_blocked: bool = False,
    rows: list[dict] | None = None,
    count: int | None = None,
    truncated: bool | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
    exit_code: int | None = None,
    duration_ms: int = 0,
) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "action": action,
        "summary": summary,
        "error": error,
        "security_blocked": bool(security_blocked),
        "rows": rows if rows is not None else [],
        "count": int(count) if count is not None else 0,
        "truncated": bool(truncated) if truncated is not None else False,
        "stdout": stdout or "",
        "stderr": stderr or "",
        "exit_code": exit_code,
        "duration_ms": int(duration_ms),
    }


def validate_aeb_payload(payload: dict) -> tuple[bool, str | None]:
    payload = _normalize_legacy_aeb_payload(payload)
    if not isinstance(payload, dict):
        return False, "payload must be a JSON object"
    action = str(payload.get("action") or "").upper().strip()
    if action not in _AEB_ACTIONS:
        return False, f"unsupported action: {action or '(missing)'}"

    if action == "SCRIBE_QUERY":
        sql = payload.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            return False, "SCRIBE_QUERY requires non-empty string field: sql"
        return True, None

    if action == "SHELL_EXEC":
        program = payload.get("program")
        args = payload.get("args")
        cmd = payload.get("cmd")
        if program is None and cmd is None:
            return False, "SHELL_EXEC requires either program+args or cmd"
        if program is not None and not isinstance(program, str):
            return False, "SHELL_EXEC.program must be a string"
        if args is not None and not isinstance(args, list):
            return False, "SHELL_EXEC.args must be a list"
        if cmd is not None and not isinstance(cmd, str):
            return False, "SHELL_EXEC.cmd must be a string"
        return True, None

    if action == "HEALTH_CHECK":
        args = payload.get("args")
        if args is not None and not isinstance(args, dict):
            return False, "HEALTH_CHECK.args must be an object when provided"
        return True, None

    if action == "ANALYSIS_RUN":
        kind = payload.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            return False, "ANALYSIS_RUN requires non-empty string field: kind"
        params = payload.get("params")
        if params is not None and not isinstance(params, dict):
            return False, "ANALYSIS_RUN.params must be an object when provided"
        notify = payload.get("notify")
        if notify is not None and not isinstance(notify, dict):
            return False, "ANALYSIS_RUN.notify must be an object when provided"
        qid = payload.get("query_id")
        if qid is not None and not isinstance(qid, str):
            return False, "ANALYSIS_RUN.query_id must be a string when provided"
        return True, None

    endpoint = payload.get("endpoint")
    nested = payload.get("payload")
    if endpoint is not None and not isinstance(endpoint, str):
        return False, "AURUM_EXEC.endpoint must be a string when provided"
    if nested is not None and not isinstance(nested, dict):
        return False, "AURUM_EXEC.payload must be an object when provided"
    return True, None


def _has_forbidden_sql_semicolon(sql: str) -> bool:
    stripped = sql.strip()
    if stripped.endswith(";"):
        stripped = stripped[:-1].rstrip()
    return ";" in stripped


def _sqlite_ro_uri(db_path: str) -> str:
    return f"{Path(db_path).expanduser().resolve().as_uri()}?mode=ro"


def _sqlite_authorizer():
    allowed_names = ("SQLITE_SELECT", "SQLITE_READ", "SQLITE_FUNCTION", "SQLITE_RECURSIVE")
    allowed = {getattr(sqlite3, name) for name in allowed_names if hasattr(sqlite3, name)}
    sqlite_ok = getattr(sqlite3, "SQLITE_OK")
    sqlite_deny = getattr(sqlite3, "SQLITE_DENY")

    def _auth(action: int, _arg1: str | None, _arg2: str | None, _db: str | None, _src: str | None):
        if action in allowed:
            return sqlite_ok
        return sqlite_deny

    return _auth


def execute_scribe_query(payload: dict, *, db_path: str) -> dict:
    started = time.monotonic()
    action = "SCRIBE_QUERY"
    ok, err = validate_aeb_payload(payload)
    if not ok:
        return _result(
            ok=False,
            action=action,
            summary="SCRIBE_QUERY validation failed",
            error=err,
            security_blocked=True,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    sql = str(payload.get("sql") or "").strip()
    if not _SQL_READ_PREFIX_RE.match(sql):
        return _result(
            ok=False,
            action=action,
            summary="SCRIBE_QUERY blocked",
            error="only SELECT/with-CTE read queries are allowed",
            security_blocked=True,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    if _has_forbidden_sql_semicolon(sql):
        return _result(
            ok=False,
            action=action,
            summary="SCRIBE_QUERY blocked",
            error="multiple statements are not allowed",
            security_blocked=True,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    max_rows = payload.get("max_rows", _env_int("AEB_SCRIBE_MAX_ROWS", 500, 1, 50_000))
    busy_timeout_ms = payload.get("busy_timeout_ms", _env_int("AEB_SCRIBE_BUSY_MS", 5000, 0, 120_000))
    timeout_sec = payload.get("timeout_sec", _env_int("AEB_SCRIBE_TIMEOUT_SEC", 10, 1, 120))
    try:
        max_rows_i = max(1, min(int(max_rows), 50_000))
    except (TypeError, ValueError):
        max_rows_i = 500
    try:
        busy_timeout_i = max(0, min(int(busy_timeout_ms), 120_000))
    except (TypeError, ValueError):
        busy_timeout_i = 5000
    try:
        timeout_i = max(1, min(int(timeout_sec), 120))
    except (TypeError, ValueError):
        timeout_i = 10

    conn = None
    try:
        conn = sqlite3.connect(_sqlite_ro_uri(db_path), uri=True)
        conn.row_factory = sqlite3.Row
        if busy_timeout_i:
            conn.execute(f"PRAGMA busy_timeout = {busy_timeout_i}")
        conn.set_authorizer(_sqlite_authorizer())
        deadline = time.monotonic() + timeout_i

        def _progress() -> int:
            return 1 if time.monotonic() > deadline else 0

        conn.set_progress_handler(_progress, 1000)
        cur = conn.execute(sql)
        rows = cur.fetchmany(max_rows_i + 1)
        truncated = len(rows) > max_rows_i
        rows = rows[:max_rows_i]
        data = [dict(r) for r in rows]
        duration_ms = int((time.monotonic() - started) * 1000)
        return _result(
            ok=True,
            action=action,
            summary=f"Scribe query returned {len(data)} row(s)",
            rows=data,
            count=len(data),
            truncated=truncated,
            duration_ms=duration_ms,
        )
    except sqlite3.DatabaseError as e:
        msg = str(e)
        blocked = ("not authorized" in msg.lower()) or ("only one statement" in msg.lower())
        return _result(
            ok=False,
            action=action,
            summary="SCRIBE_QUERY blocked" if blocked else "SCRIBE_QUERY failed",
            error=msg,
            security_blocked=blocked,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass


def _resolve_program(program: str) -> str | None:
    if "/" in program:
        p = Path(program).expanduser()
        if p.exists():
            return str(p.resolve())
        return None
    found = shutil.which(program)
    return str(Path(found).resolve()) if found else None


def _as_project_path(raw_path: str, project_root: str) -> Path:
    p = Path(raw_path).expanduser()
    if p.is_absolute():
        return p.resolve()
    return (Path(project_root).resolve() / p).resolve()


def _path_allowed(path: Path, *, project_root: Path, allowed_prefixes: list[str]) -> bool:
    try:
        rel = path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return False
    for prefix in allowed_prefixes:
        norm = prefix.strip().lstrip("./")
        if not norm:
            continue
        if rel == norm.rstrip("/") or rel.startswith(norm.rstrip("/") + "/"):
            return True
    return False


def _build_shell_argv(payload: dict) -> tuple[list[str] | None, str | None]:
    program = payload.get("program")
    if isinstance(program, str) and program.strip():
        args = payload.get("args") or []
        if not isinstance(args, list):
            return None, "SHELL_EXEC.args must be a list"
        argv = [program.strip()] + [str(x) for x in args]
        return argv, None

    cmd = payload.get("cmd")
    if isinstance(cmd, str) and cmd.strip():
        try:
            argv = shlex.split(cmd.strip(), posix=True)
            if not argv:
                return None, "SHELL_EXEC.cmd produced empty argv"
            return argv, None
        except ValueError as e:
            return None, f"SHELL_EXEC.cmd parse failed: {e}"

    return None, "SHELL_EXEC requires either program+args or cmd"


def _validate_shell_allowlist(argv: list[str], *, project_root: str) -> tuple[bool, str | None]:
    allowed_programs = {p.lower() for p in _env_csv("AEB_SHELL_EXEC_ALLOWED_PROGRAMS", "python3,sqlite3")}
    allowed_prefixes = _env_csv("AEB_SHELL_EXEC_ALLOWED_PATH_PREFIXES", "scripts/,data/,logs/")
    root = Path(project_root).resolve()

    program = argv[0]
    resolved = _resolve_program(program)
    if not resolved:
        return False, f"program not found: {program}"
    prog_name = Path(resolved).name.lower()
    if prog_name not in allowed_programs and program.lower() not in allowed_programs:
        return False, f"program not allowlisted: {program}"

    if prog_name in {"python", "python3"}:
        script_arg = None
        for arg in argv[1:]:
            if arg.startswith("-"):
                if arg in ("-m", "-c"):
                    return False, f"python option {arg} is not allowed"
                continue
            script_arg = arg
            break
        if script_arg is None:
            return False, "python execution requires a script path argument"
        script_path = _as_project_path(script_arg, str(root))
        if not script_path.exists():
            return False, f"script not found: {script_arg}"
        if not _path_allowed(script_path, project_root=root, allowed_prefixes=allowed_prefixes):
            return False, f"script path not allowlisted: {script_arg}"

    if prog_name == "sqlite3":
        db_arg = None
        for arg in argv[1:]:
            if arg.startswith("-"):
                continue
            db_arg = arg
            break
        if db_arg:
            db_path = _as_project_path(db_arg, str(root))
            if not db_path.exists():
                return False, f"sqlite database path not found: {db_arg}"
            if not _path_allowed(db_path, project_root=root, allowed_prefixes=allowed_prefixes):
                return False, f"sqlite database path not allowlisted: {db_arg}"

    return True, None


def execute_shell_exec(payload: dict, *, project_root: str) -> dict:
    started = time.monotonic()
    action = "SHELL_EXEC"
    ok, err = validate_aeb_payload(payload)
    if not ok:
        return _result(
            ok=False,
            action=action,
            summary="SHELL_EXEC validation failed",
            error=err,
            security_blocked=True,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    argv, parse_err = _build_shell_argv(payload)
    if parse_err:
        return _result(
            ok=False,
            action=action,
            summary="SHELL_EXEC blocked",
            error=parse_err,
            security_blocked=True,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    allow_ok, allow_err = _validate_shell_allowlist(argv or [], project_root=project_root)
    if not allow_ok:
        return _result(
            ok=False,
            action=action,
            summary="SHELL_EXEC blocked",
            error=allow_err,
            security_blocked=True,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    timeout_sec = payload.get("timeout_sec", _env_int("AEB_SHELL_EXEC_TIMEOUT_SEC", 10, 1, 300))
    max_output_chars = _env_int("AEB_SHELL_EXEC_MAX_OUTPUT_CHARS", 4000, 256, 50_000)
    try:
        timeout_i = max(1, min(int(timeout_sec), 300))
    except (TypeError, ValueError):
        timeout_i = 10

    try:
        proc = subprocess.run(
            argv,
            shell=False,
            timeout=timeout_i,
            capture_output=True,
            text=True,
            cwd=str(Path(project_root).resolve()),
            env=_safe_subprocess_env(),
            check=False,
        )
        out = _truncate_text(proc.stdout, max_output_chars)
        err_txt = _truncate_text(proc.stderr, max_output_chars)
        duration_ms = int((time.monotonic() - started) * 1000)
        _warn_if_slow(started)
        ok_rc = proc.returncode == 0
        return _result(
            ok=ok_rc,
            action=action,
            summary=f"SHELL_EXEC exited with code {proc.returncode}",
            stdout=out,
            stderr=err_txt,
            exit_code=proc.returncode,
            duration_ms=duration_ms,
        )
    except subprocess.TimeoutExpired as e:
        out = _truncate_text((e.stdout or ""), max_output_chars)
        err_txt = _truncate_text((e.stderr or ""), max_output_chars)
        _warn_if_slow(started)
        return _result(
            ok=False,
            action=action,
            summary="SHELL_EXEC timed out",
            error=f"command timed out after {timeout_i}s",
            stdout=out,
            stderr=err_txt,
            exit_code=None,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as e:
        return _result(
            ok=False,
            action=action,
            summary="SHELL_EXEC failed",
            error=str(e),
            duration_ms=int((time.monotonic() - started) * 1000),
        )

def execute_health_check(payload: dict, *, project_root: str) -> dict:
    started = time.monotonic()
    action = "HEALTH_CHECK"
    payload = _normalize_legacy_aeb_payload(payload)
    ok, err = validate_aeb_payload(payload)
    if not ok:
        return _result(
            ok=False,
            action=action,
            summary="HEALTH_CHECK validation failed",
            error=err,
            security_blocked=True,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    timeout_sec = payload.get("timeout_sec", _env_int("AEB_HEALTH_CHECK_TIMEOUT_SEC", 10, 1, 300))
    max_output_chars = _env_int("AEB_HEALTH_CHECK_MAX_OUTPUT_CHARS", 8000, 256, 50_000)
    try:
        timeout_i = max(1, min(int(timeout_sec), 300))
    except (TypeError, ValueError):
        timeout_i = 10

    root = Path(project_root).resolve()
    script_path = root / "scripts" / "health.py"
    if not script_path.exists():
        return _result(
            ok=False,
            action=action,
            summary="HEALTH_CHECK failed",
            error=f"health script not found: {script_path}",
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    python_exec = shutil.which("python3") or shutil.which("python") or sys.executable
    argv = [python_exec, str(script_path), "--json"]
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            timeout=timeout_i,
            capture_output=True,
            text=True,
            cwd=str(root),
            env=_safe_subprocess_env(),
            check=False,
        )
        out = _truncate_text(proc.stdout, max_output_chars)
        err_txt = _truncate_text(proc.stderr, max_output_chars)
        summary = f"HEALTH_CHECK exited with code {proc.returncode}"
        overall = ""
        try:
            parsed = json.loads(proc.stdout) if proc.stdout and proc.stdout.strip() else {}
            if isinstance(parsed, dict):
                overall = str(parsed.get("overall") or "").strip().upper()
        except Exception:
            overall = ""
        if overall:
            summary = f"Health check overall={overall}"
        ok_rc = proc.returncode != 2
        _warn_if_slow(started)
        return _result(
            ok=ok_rc,
            action=action,
            summary=summary,
            stdout=out,
            stderr=err_txt,
            exit_code=proc.returncode,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except subprocess.TimeoutExpired as e:
        out = _truncate_text((e.stdout or ""), max_output_chars)
        err_txt = _truncate_text((e.stderr or ""), max_output_chars)
        _warn_if_slow(started)
        return _result(
            ok=False,
            action=action,
            summary="HEALTH_CHECK timed out",
            error=f"health check timed out after {timeout_i}s",
            stdout=out,
            stderr=err_txt,
            exit_code=None,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as e:
        return _result(
            ok=False,
            action=action,
            summary="HEALTH_CHECK failed",
            error=str(e),
            duration_ms=int((time.monotonic() - started) * 1000),
        )


def execute_action(payload: dict, *, db_path: str, project_root: str, _depth: int = 0) -> dict:
    payload = _normalize_legacy_aeb_payload(payload)
    ok, err = validate_aeb_payload(payload)
    action = str(payload.get("action") or "").upper().strip()
    if not ok:
        return _result(
            ok=False,
            action=action or "UNKNOWN",
            summary="AEB payload validation failed",
            error=err,
            security_blocked=True,
        )

    if action == "SCRIBE_QUERY":
        return execute_scribe_query(payload, db_path=db_path)
    if action == "SHELL_EXEC":
        return execute_shell_exec(payload, project_root=project_root)
    if action == "HEALTH_CHECK":
        return execute_health_check(payload, project_root=project_root)
    if action == "ANALYSIS_RUN":
        # Lazy import: keep aeb_executor importable without bringing
        # up the analysis runner / its thread pool unless used.
        try:
            import analysis_runner
        except Exception as e:
            return _result(
                ok=False,
                action="ANALYSIS_RUN",
                summary="ANALYSIS_RUN unavailable",
                error=f"analysis_runner import failed: {e}",
            )
        return analysis_runner.submit(payload)

    if _depth >= 2:
        return _result(
            ok=False,
            action=action,
            summary="AURUM_EXEC recursion blocked",
            error="nested AURUM_EXEC depth exceeded",
            security_blocked=True,
        )

    nested = payload.get("payload")
    if isinstance(nested, dict):
        result = execute_action(nested, db_path=db_path, project_root=project_root, _depth=_depth + 1)
        result["summary"] = f"AURUM_EXEC envelope -> {result.get('summary', '')}".strip()
        return result

    return _result(
        ok=False,
        action=action,
        summary="AURUM_EXEC missing payload",
        error="AURUM_EXEC requires nested payload object",
        security_blocked=True,
    )


def format_result_for_telegram(result: dict, max_chars: int = 3000) -> str:
    action = str(result.get("action") or "AEB")
    ok = bool(result.get("ok"))
    blocked = bool(result.get("security_blocked"))
    summary = str(result.get("summary") or "").strip()
    error = str(result.get("error") or "").strip()
    duration = result.get("duration_ms")

    lines: list[str] = []
    if ok:
        lines.append(f"✅ {action}")
    elif blocked:
        lines.append(f"🚫 {action}")
    else:
        lines.append(f"❌ {action}")
    if summary:
        lines.append(summary)
    if duration is not None:
        lines.append(f"duration_ms={duration}")

    if action == "SCRIBE_QUERY":
        count = int(result.get("count") or 0)
        lines.append(f"rows={count} truncated={bool(result.get('truncated'))}")
        rows = result.get("rows") or []
        if rows:
            preview = json.dumps(rows, ensure_ascii=False, default=str)
            lines.append(_truncate_text(preview, 1200))
    elif action in {"SHELL_EXEC", "HEALTH_CHECK"}:
        lines.append(f"exit_code={result.get('exit_code')}")
        stdout = (result.get("stdout") or "").strip()
        stderr = (result.get("stderr") or "").strip()
        if stdout:
            lines.append("stdout:")
            lines.append(_truncate_text(stdout, 1200))
        if stderr:
            lines.append("stderr:")
            lines.append(_truncate_text(stderr, 1200))
    elif action == "ANALYSIS_RUN":
        qid = result.get("query_id")
        status = result.get("status")
        log_path = result.get("log_path")
        if qid:
            lines.append(f"query_id={qid}")
        if status:
            lines.append(f"status={status}")
        if log_path:
            lines.append(f"log={log_path}")

    if error:
        lines.append(f"error: {error}")

    out = "\n".join(x for x in lines if x)
    return _truncate_text(out, max(256, int(max_chars)))
