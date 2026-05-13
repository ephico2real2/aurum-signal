"""
trading_session.py — XAUUSD kill-zone session from UTC clock
=============================================================
Used by BRIDGE (status.json) and AURUM (prompt context) so session labels
stay consistent and overnight gaps (e.g. 22:00–01:00 UTC) are not mislabeled
OFF_HOURS.

Default ASIAN window wraps midnight: 22:00 UTC → 08:00 UTC (Tokyo/Sydney overlap
into London open). Override with env SESSION_* (hours 0–23).

Order: LONDON, LONDON_NY, NEW_YORK (simple ranges), then ASIAN (may wrap).
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

_log = logging.getLogger("trading_session")
_SYDNEY_TZ = ZoneInfo(os.environ.get("SESSION_SYDNEY_TZ", "Australia/Sydney"))
_LONDON_TZ = ZoneInfo(os.environ.get("SESSION_LONDON_TZ", "Europe/London"))
_NY_TZ = ZoneInfo(os.environ.get("SESSION_NY_TZ", "America/New_York"))

# ICT killzones — minute-of-day in NY local time. Cross-confirmed standard windows.
# See docs/research/ICT_KILLZONES.md for source citations.
#
# v2.7.49 — EA is the authoritative source for killzone (MT5 is where orders fire,
# so the EA's broker-anchored clock is what causally drives trade decisions). Python
# reads these defaults only as a stale-fallback when market_data.json is missing/old.
# The window MINUTES themselves are read from config/scalper_config.json (the EA's
# canonical config) when available — see _kz_window() below — so window changes flow
# from EA config to bridge in one direction.
_KZ_DEFAULTS = {
    "ASIAN":        (19 * 60,  3 * 60),   # 19:00 – 03:00 NY (wraps)
    "LONDON_OPEN":  ( 2 * 60,  5 * 60),   # 02:00 – 05:00 NY
    "NY_OPEN":      ( 7 * 60, 10 * 60),   # 07:00 – 10:00 NY (forex)
    "LONDON_CLOSE": (10 * 60, 12 * 60),   # 10:00 – 12:00 NY
}

# Map ICT killzone names to scalper_config.session_filter.kz_<name>_start_min/end_min keys.
_SCALPER_CONFIG_KZ_KEYS = {
    "ASIAN":        ("kz_asia_start_min",         "kz_asia_end_min"),
    "LONDON_OPEN":  ("kz_london_open_start_min",  "kz_london_open_end_min"),
    "NY_OPEN":      ("kz_ny_open_start_min",      "kz_ny_open_end_min"),
    "LONDON_CLOSE": ("kz_london_close_start_min", "kz_london_close_end_min"),
}

# Cache for scalper_config.json reads (avoid touching disk on every _kz_window call)
_SCALPER_CONFIG_CACHE: dict = {"mtime": 0.0, "data": None, "path": None}


def _scalper_config() -> dict:
    """Load scalper_config.json window definitions; cache by mtime so we pick up
    operator edits without restarting bridge. Returns {} if file missing/unreadable."""
    path = os.environ.get(
        "FORGE_SCALPER_CONFIG_PATH",
        str(Path(__file__).resolve().parent.parent / "config" / "scalper_config.json"),
    )
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    if _SCALPER_CONFIG_CACHE["path"] == path and _SCALPER_CONFIG_CACHE["mtime"] == mtime:
        return _SCALPER_CONFIG_CACHE["data"] or {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        _log.debug("scalper_config.json unreadable (%s) — falling back to env defaults", e)
        return {}
    _SCALPER_CONFIG_CACHE.update({"path": path, "mtime": mtime, "data": data})
    return data


def _hour_in_range(h: int, start: int, end: int) -> bool:
    """True if integer UTC hour h lies in [start, end) modulo 24."""
    if start < end:
        return start <= h < end
    if start > end:
        return h >= start or h < end
    return False


def get_trading_session_utc(now: datetime | None = None) -> str:
    """
    Return SYDNEY | ASIAN | LONDON | LONDON_NY | NEW_YORK | OFF_HOURS from UTC time.
    """
    now = now or datetime.now(timezone.utc)
    h = now.hour

    london_s = int(os.environ.get("SESSION_LONDON_LOCAL_START", os.environ.get("SESSION_LONDON_START", "8")))
    london_e = int(os.environ.get("SESSION_LONDON_LOCAL_END", os.environ.get("SESSION_LONDON_END", "13")))
    ln_s = int(os.environ.get("SESSION_LONDON_NY_LOCAL_START", os.environ.get("SESSION_LONDON_NY_START", "8")))
    ln_e = int(os.environ.get("SESSION_LONDON_NY_LOCAL_END", os.environ.get("SESSION_LONDON_NY_END", "12")))
    ny_s = int(os.environ.get("SESSION_NY_LOCAL_START", os.environ.get("SESSION_NY_START", "12")))
    ny_e = int(os.environ.get("SESSION_NY_LOCAL_END", os.environ.get("SESSION_NY_END", "17")))
    asian_s = int(os.environ.get("SESSION_ASIAN_START", "22"))
    asian_e = int(os.environ.get("SESSION_ASIAN_END", "8"))
    sydney_local_s = int(os.environ.get("SESSION_SYDNEY_LOCAL_START", "9"))
    sydney_local_e = int(os.environ.get("SESSION_SYDNEY_LOCAL_END", "17"))
    sydney_now = now.astimezone(_SYDNEY_TZ)
    london_now = now.astimezone(_LONDON_TZ)
    ny_now = now.astimezone(_NY_TZ)

    if _hour_in_range(london_now.hour, london_s, london_e):
        return "LONDON"
    if _hour_in_range(ny_now.hour, ln_s, ln_e):
        return "LONDON_NY"
    if _hour_in_range(ny_now.hour, ny_s, ny_e):
        return "NEW_YORK"
    if _hour_in_range(sydney_now.hour, sydney_local_s, sydney_local_e):
        return "SYDNEY"
    if _hour_in_range(h, asian_s, asian_e):
        return "ASIAN"
    return "OFF_HOURS"


def _minute_in_window(now_min: int, start_min: int, end_min: int) -> bool:
    if start_min < 0 or end_min < 0:
        return False
    if start_min < end_min:
        return start_min <= now_min < end_min
    return now_min >= start_min or now_min < end_min  # wraps midnight


def _kz_window(name: str) -> tuple[int, int]:
    """Resolve killzone window minutes for `name`.

    Priority (v2.7.49 — single source of truth for the windows):
      1. config/scalper_config.json → session_filter.kz_<name>_start_min/end_min
         (the EA's canonical config; bridge mirrors it so window changes are one-way)
      2. env SESSION_KZ_<NAME>_START_MIN / _END_MIN (kept as a test/operator override)
      3. _KZ_DEFAULTS hard-coded fallback (only if both above are absent)
    """
    s_def, e_def = _KZ_DEFAULTS[name]

    # Step 1: scalper_config.json (EA's authoritative window definitions)
    cfg = _scalper_config()
    sf = cfg.get("session_filter", {}) if isinstance(cfg, dict) else {}
    cfg_s_key, cfg_e_key = _SCALPER_CONFIG_KZ_KEYS[name]
    if cfg_s_key in sf and cfg_e_key in sf:
        try:
            return int(sf[cfg_s_key]), int(sf[cfg_e_key])
        except (TypeError, ValueError):
            pass  # malformed — fall through

    # Step 2: env override (legacy + tests)
    s = int(os.environ.get(f"SESSION_KZ_{name}_START_MIN", str(s_def)))
    e = int(os.environ.get(f"SESSION_KZ_{name}_END_MIN",   str(e_def)))
    return s, e


def get_ea_killzone(market_data_path: str | os.PathLike,
                    max_age_sec: int = 60) -> Tuple[Optional[str], Optional[float]]:
    """Read the EA's authoritative killzone label from market_data.json.

    The EA writes this file every tick (see FORGE.mq5 WriteMarketData). It contains
    the `killzone` field computed by ComputeCurrentKillzoneLabel() — broker-clock-anchored
    so it matches exactly what gets stored in forge_signals.killzone for every TAKEN/SKIP.

    Returns:
        (label, age_seconds) — `label` may be "" (no killzone active) or an ICT KZ
                                string. `age_seconds` is the file's mtime delta vs now.
        (None,  None)        — file missing, unreadable, stale beyond `max_age_sec`,
                                or doesn't contain a session.killzone field. Caller
                                should fall back to get_current_killzone_utc().
    """
    try:
        mtime = os.path.getmtime(market_data_path)
    except OSError:
        return None, None
    age = max(0.0, time.time() - mtime)
    if age > max_age_sec:
        return None, age
    try:
        with open(market_data_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None, age
    # The EA writes killzone under `forge_session_state` (named that way per
    # FORGE.mq5:2916 to avoid collision with the top-level "session" key used by
    # other producers). See ea/FORGE.mq5 WriteMarketData() for the canonical schema.
    fss = data.get("forge_session_state") if isinstance(data, dict) else None
    if not isinstance(fss, dict):
        return None, age
    label = fss.get("killzone")
    if label is None:
        return None, age
    return str(label), age


def get_current_killzone_utc(now: datetime | None = None) -> str:
    """
    Return ICT killzone label or '' (none).
    Labels: '' | 'ASIAN_KZ' | 'LONDON_OPEN_KZ' | 'NY_OPEN_KZ' | 'LONDON_CLOSE_KZ'
    Always evaluated in NY local time via zoneinfo (OS-DST-aware).
    Returns '' on weekends or when disabled via KILLZONES_ENABLED=0.
    """
    if os.environ.get("KILLZONES_ENABLED", "1") not in ("1", "true", "True"):
        return ""
    now = now or datetime.now(timezone.utc)
    ny_now = now.astimezone(_NY_TZ)
    if ny_now.weekday() == 5:                       # Saturday
        return ""
    if ny_now.weekday() == 6 and ny_now.hour < 17:  # Sunday pre-open
        return ""
    now_min = ny_now.hour * 60 + ny_now.minute
    s, e = _kz_window("NY_OPEN")
    if _minute_in_window(now_min, s, e):
        return "NY_OPEN_KZ"
    s, e = _kz_window("LONDON_OPEN")
    if _minute_in_window(now_min, s, e):
        return "LONDON_OPEN_KZ"
    s, e = _kz_window("LONDON_CLOSE")
    if _minute_in_window(now_min, s, e):
        return "LONDON_CLOSE_KZ"
    s, e = _kz_window("ASIAN")
    if _minute_in_window(now_min, s, e):
        return "ASIAN_KZ"
    return ""


def trading_day_reset_hour_utc() -> int:
    """
    UTC hour when the AEGIS / daily P&L window rolls (same boundary for loss limits).

    If AEGIS_SESSION_RESET_HOUR is set, it wins. Otherwise use SESSION_LONDON_START
    so the trading day aligns with kill-zone config without duplicating numbers.
    """
    raw = os.environ.get("AEGIS_SESSION_RESET_HOUR", "").strip()
    if raw != "":
        try:
            return max(0, min(23, int(raw)))
        except ValueError:
            _log.warning("Invalid AEGIS_SESSION_RESET_HOUR=%r — using SESSION_LONDON_START", raw)
    return int(os.environ.get("SESSION_LONDON_START", "8"))


def sydney_open_alert_info(now: datetime | None = None) -> dict:
    """
    DST-aware helper for once-per-day Sydney-open alerting.
    should_fire is true only within the configured minute window after Sydney local open.
    """
    now = now or datetime.now(timezone.utc)
    local_open_hour = int(os.environ.get("SESSION_SYDNEY_LOCAL_START", "9"))
    grace_min = int(os.environ.get("SYDNEY_OPEN_ALERT_GRACE_MIN", "5"))
    sydney_now = now.astimezone(_SYDNEY_TZ)
    local_open = sydney_now.replace(hour=local_open_hour, minute=0, second=0, microsecond=0)
    should_fire = sydney_now.hour == local_open_hour and 0 <= sydney_now.minute < max(1, grace_min)
    return {
        "should_fire": should_fire,
        "alert_key": sydney_now.date().isoformat(),
        "open_utc": local_open.astimezone(timezone.utc).isoformat(),
        "sydney_now": sydney_now.isoformat(),
    }


def session_clock_summary() -> str:
    """One-line description of SESSION_* env for prompts (AURUM / logs)."""
    a0 = os.environ.get("SESSION_ASIAN_START", "22")
    a1 = os.environ.get("SESSION_ASIAN_END", "8")
    lo0 = os.environ.get("SESSION_LONDON_LOCAL_START", os.environ.get("SESSION_LONDON_START", "8"))
    lo1 = os.environ.get("SESSION_LONDON_LOCAL_END", os.environ.get("SESSION_LONDON_END", "13"))
    mx0 = os.environ.get("SESSION_LONDON_NY_LOCAL_START", os.environ.get("SESSION_LONDON_NY_START", "8"))
    mx1 = os.environ.get("SESSION_LONDON_NY_LOCAL_END", os.environ.get("SESSION_LONDON_NY_END", "12"))
    ny0 = os.environ.get("SESSION_NY_LOCAL_START", os.environ.get("SESSION_NY_START", "12"))
    ny1 = os.environ.get("SESSION_NY_LOCAL_END", os.environ.get("SESSION_NY_END", "17"))
    sy0 = os.environ.get("SESSION_SYDNEY_LOCAL_START", "9")
    sy1 = os.environ.get("SESSION_SYDNEY_LOCAL_END", "17")
    wrap = "wraps midnight" if int(a0) > int(a1) else "flat UTC range"
    kz_enabled = os.environ.get("KILLZONES_ENABLED", "1") in ("1", "true", "True")
    if kz_enabled:
        kz_asia_s, kz_asia_e = _kz_window("ASIAN")
        kz_lo_s,   kz_lo_e   = _kz_window("LONDON_OPEN")
        kz_ny_s,   kz_ny_e   = _kz_window("NY_OPEN")
        kz_lc_s,   kz_lc_e   = _kz_window("LONDON_CLOSE")
        kz_summary = (
            f"; ICT killzones (NY local): ASIAN {kz_asia_s//60:02d}:{kz_asia_s%60:02d}–{kz_asia_e//60:02d}:{kz_asia_e%60:02d}, "
            f"LONDON_OPEN {kz_lo_s//60:02d}:{kz_lo_s%60:02d}–{kz_lo_e//60:02d}:{kz_lo_e%60:02d}, "
            f"NY_OPEN {kz_ny_s//60:02d}:{kz_ny_s%60:02d}–{kz_ny_e//60:02d}:{kz_ny_e%60:02d}, "
            f"LONDON_CLOSE {kz_lc_s//60:02d}:{kz_lc_s%60:02d}–{kz_lc_e//60:02d}:{kz_lc_e%60:02d}"
        )
    else:
        kz_summary = "; ICT killzones disabled (KILLZONES_ENABLED=0)"
    return (
        f"Kill zones: ASIAN(UTC) {a0}–{a1} ({wrap}), "
        f"LONDON(local) {lo0}–{lo1} {_LONDON_TZ.key}, "
        f"LONDON_NY(local NY) {mx0}–{mx1} {_NY_TZ.key}, "
        f"NEW_YORK(local) {ny0}–{ny1} {_NY_TZ.key}, "
        f"SYDNEY(local) {sy0}–{sy1} {_SYDNEY_TZ.key}; "
        f"daily P&L roll {trading_day_reset_hour_utc():02d}:00 UTC"
        f"{kz_summary}"
    )
