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

import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_log = logging.getLogger("trading_session")
_SYDNEY_TZ = ZoneInfo(os.environ.get("SESSION_SYDNEY_TZ", "Australia/Sydney"))
_LONDON_TZ = ZoneInfo(os.environ.get("SESSION_LONDON_TZ", "Europe/London"))
_NY_TZ = ZoneInfo(os.environ.get("SESSION_NY_TZ", "America/New_York"))


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
    return (
        f"Kill zones: ASIAN(UTC) {a0}–{a1} ({wrap}), "
        f"LONDON(local) {lo0}–{lo1} {_LONDON_TZ.key}, "
        f"LONDON_NY(local NY) {mx0}–{mx1} {_NY_TZ.key}, "
        f"NEW_YORK(local) {ny0}–{ny1} {_NY_TZ.key}, "
        f"SYDNEY(local) {sy0}–{sy1} {_SYDNEY_TZ.key}; "
        f"daily P&L roll {trading_day_reset_hour_utc():02d}:00 UTC"
    )
