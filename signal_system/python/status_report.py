"""
status_report.py — Component status for ATHENA grid
===================================================
Writes to SCRIBE `component_heartbeats` (source of truth for GET /api/components).

Optional: set COMPONENT_HEARTBEAT_USE_HTTP=1 to mirror each update to
POST /api/components/heartbeat (non-blocking thread) for API-first setups.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

log = logging.getLogger("status_report")

KNOWN_COMPONENTS = frozenset(
    {
        "BRIDGE",
        "FORGE",
        "LISTENER",
        "LENS",
        "SENTINEL",
        "AEGIS",
        "SCRIBE",
        "HERALD",
        "AURUM",
        "RECONCILER",
        "ATHENA",
    }
)

_HB_KEYS = frozenset(
    {"mode", "note", "last_action", "error_msg", "cycle", "session"}
)


def report_component_status(
    component: str,
    status: str = "OK",
    **kwargs: Any,
) -> None:
    """
    Persist component heartbeat to SQLite. Optionally mirror to ATHENA HTTP API.
    """
    if component not in KNOWN_COMPONENTS:
        log.warning("Unknown component %r for heartbeat", component)

    hb_kwargs = {k: v for k, v in kwargs.items() if k in _HB_KEYS and v is not None}
    try:
        from scribe import get_scribe

        get_scribe().heartbeat(component=component, status=status, **hb_kwargs)
    except Exception as e:
        log.warning("Heartbeat failed for %s: %s", component, e)
        return

    if os.environ.get("COMPONENT_HEARTBEAT_USE_HTTP", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        return

    payload = {"component": component, "status": status, **hb_kwargs}

    def _mirror() -> None:
        try:
            import requests

            base = os.environ.get("ATHENA_INTERNAL_BASE", "").strip().rstrip("/")
            if not base:
                port = os.environ.get("ATHENA_PORT", "7842")
                base = f"http://127.0.0.1:{port}"
            requests.post(
                f"{base}/api/components/heartbeat",
                json=payload,
                timeout=1.0,
            )
        except Exception:
            pass

    threading.Thread(target=_mirror, daemon=True).start()
