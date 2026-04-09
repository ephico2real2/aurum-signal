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

_log = logging.getLogger("trading_session")


def _hour_in_range(h: int, start: int, end: int) -> bool:
    """True if integer UTC hour h lies in [start, end) modulo 24."""
    if start < end:
        return start <= h < end
    if start > end:
        return h >= start or h < end
    return False


def get_trading_session_utc(now: datetime | None = None) -> str:
    """
    Return ASIAN | LONDON | LONDON_NY | NEW_YORK | OFF_HOURS from UTC time.
    """
    now = now or datetime.now(timezone.utc)
    h = now.hour

    london_s = int(os.environ.get("SESSION_LONDON_START", "8"))
    london_e = int(os.environ.get("SESSION_LONDON_END", "13"))
    ln_s = int(os.environ.get("SESSION_LONDON_NY_START", "13"))
    ln_e = int(os.environ.get("SESSION_LONDON_NY_END", "17"))
    ny_s = int(os.environ.get("SESSION_NY_START", "17"))
    ny_e = int(os.environ.get("SESSION_NY_END", "22"))
    asian_s = int(os.environ.get("SESSION_ASIAN_START", "22"))
    asian_e = int(os.environ.get("SESSION_ASIAN_END", "8"))

    if london_s <= h < london_e:
        return "LONDON"
    if ln_s <= h < ln_e:
        return "LONDON_NY"
    if ny_s <= h < ny_e:
        return "NEW_YORK"
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


def session_clock_summary() -> str:
    """One-line description of SESSION_* env for prompts (AURUM / logs)."""
    a0 = os.environ.get("SESSION_ASIAN_START", "22")
    a1 = os.environ.get("SESSION_ASIAN_END", "8")
    lo0, lo1 = os.environ.get("SESSION_LONDON_START", "8"), os.environ.get("SESSION_LONDON_END", "13")
    mx0, mx1 = os.environ.get("SESSION_LONDON_NY_START", "13"), os.environ.get("SESSION_LONDON_NY_END", "17")
    ny0, ny1 = os.environ.get("SESSION_NY_START", "17"), os.environ.get("SESSION_NY_END", "22")
    wrap = "wraps midnight" if int(a0) > int(a1) else "flat UTC range"
    return (
        f"Kill zones (UTC): ASIAN {a0}–{a1} ({wrap}), LONDON {lo0}–{lo1}, "
        f"LONDON_NY {mx0}–{mx1}, NEW_YORK {ny0}–{ny1}; "
        f"daily P&L roll {trading_day_reset_hour_utc():02d}:00 UTC"
    )
