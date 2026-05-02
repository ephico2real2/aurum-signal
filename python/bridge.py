"""
bridge.py — BRIDGE System Orchestrator
=======================================
Build order: #9 — depends on all other Python components.
Central nervous system. Mode state machine. Coordinates everything.
Entry point: python bridge.py
"""

import os, json, logging, re, time, sys, urllib.error, urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from aeb_executor import execute_action, format_result_for_telegram

from scribe      import get_scribe
from herald      import get_herald
from sentinel    import Sentinel
from lens        import get_lens
from aegis       import get_aegis
from regime      import get_regime_engine
from listener    import Listener
from aurum       import get_aurum
from reconciler  import get_reconciler
from status_report import report_component_status
from trading_session import get_trading_session_utc, sydney_open_alert_info
from freshness import DATA_FRESHNESS_WINDOWS
from config_io import atomic_write_json

log = logging.getLogger("bridge")

_PY   = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_PY, ".."))


def _under_python(rel: str) -> str:
    if os.path.isabs(rel):
        return rel
    return os.path.join(_PY, rel)


def _under_root(rel: str) -> str:
    """MT5 JSON files live at repo root (same as ATHENA / FORGE)."""
    if os.path.isabs(rel):
        return rel
    return os.path.join(_ROOT, rel)


# ── Config ──────────────────────────────────────────────────────────
LOOP_INTERVAL   = int(os.environ.get("BRIDGE_LOOP_SEC",     "5"))
# TradingView MCP is slow (~3s+); default 60s balances freshness vs load (was 300s).
LENS_INTERVAL   = int(os.environ.get("BRIDGE_LENS_SEC",     str(DATA_FRESHNESS_WINDOWS["LENS"])))
# Refresh TradingView MCP while in WATCH (launchd has no login PATH without install_services fix)
LENS_WATCH_REFRESH_SEC = int(os.environ.get("LENS_WATCH_REFRESH_SEC", str(DATA_FRESHNESS_WINDOWS["LENS"])))
SENTINEL_INTERVAL = int(os.environ.get("BRIDGE_SENTINEL_SEC","60"))
MT5_STALE_SEC   = int(os.environ.get("BRIDGE_MT5_STALE",    str(DATA_FRESHNESS_WINDOWS["MT5"])))
MT5_STALE_RELAXED_SEC = int(os.environ.get("BRIDGE_MT5_STALE_RELAXED", str(MT5_STALE_SEC)))
if MT5_STALE_RELAXED_SEC < MT5_STALE_SEC:
    MT5_STALE_RELAXED_SEC = MT5_STALE_SEC
MT5_READ_FAIL_STREAK = max(1, int(os.environ.get("BRIDGE_MT5_READ_FAIL_STREAK", "2")))

STATUS_FILE     = _under_python(os.environ.get("BRIDGE_STATUS_FILE", "config/status.json"))
CMD_FILE_MT5    = _under_root(os.environ.get("MT5_CMD_FILE",        "MT5/command.json"))
# Optional second path for the same command.json (same JSON written twice). Use when FORGE
# reads Common Files but BRIDGE defaults to a non-symlinked repo MT5/ — see docs/FORGE_BRIDGE.md.
CMD_FILE_MT5_MIRROR = os.environ.get("MT5_CMD_FILE_MIRROR", "").strip()
CFG_FILE_MT5    = _under_root(os.environ.get("MT5_CONFIG_FILE",     "MT5/config.json"))
MARKET_FILE     = _under_root(os.environ.get("MT5_MARKET_FILE",     "MT5/market_data.json"))
SIGNAL_FILE     = _under_python(os.environ.get("LISTENER_SIGNAL_FILE","config/parsed_signal.json"))
MGMT_FILE       = _under_python(os.environ.get("LISTENER_MGMT_FILE",  "config/management_cmd.json"))
SENTINEL_FILE   = _under_python(os.environ.get("SENTINEL_STATUS_FILE","config/sentinel_status.json"))
AURUM_CMD_FILE  = _under_python(os.environ.get("AURUM_CMD_FILE",      "config/aurum_cmd.json"))
ATHENA_PORT     = int(os.environ.get("ATHENA_PORT", "7842"))
AURUM_EXEC_BASE_URL = os.environ.get("AURUM_EXEC_BASE_URL", f"http://127.0.0.1:{ATHENA_PORT}").strip()
AURUM_EXEC_TIMEOUT_SEC = max(1, int(os.environ.get("AURUM_EXEC_TIMEOUT_SEC", "15")))
AURUM_EXEC_SECRET = (os.environ.get("ATHENA_AURUM_EXEC_SECRET") or "").strip()
AEB_TELEGRAM_MAX_CHARS = max(256, int(os.environ.get("AEB_TELEGRAM_MAX_CHARS", "3000")))
AEB_SHELL_EXEC_BLOCKED_SOURCES = {
    x.strip().upper()
    for x in os.environ.get("AEB_SHELL_EXEC_BLOCKED_SOURCES", "TELEGRAM").split(",")
    if x and x.strip()
}
SCALPER_ENTRY_FILE = _under_root(os.environ.get("SCALPER_ENTRY_FILE",  "MT5/scalper_entry.json"))
SCALPER_CONFIG_FILE = os.path.join(_ROOT, "config", "scalper_config.json")
LENS_SNAPSHOT_FILE = _under_python(
    os.environ.get("LENS_SNAPSHOT_FILE", os.environ.get("LENS_SNAPSHOT", "config/lens_snapshot.json"))
)

# TP close percentages
TP1_CLOSE_PCT   = float(os.environ.get("TP1_CLOSE_PCT", "70"))
TP2_CLOSE_PCT   = float(os.environ.get("TP2_CLOSE_PCT", "20"))
MOVE_BE_ON_TP1  = os.environ.get("MOVE_BE_ON_TP1", "true").lower() == "true"

# Must match ea/FORGE.mq5 input MagicNumber — group magic = base + offset
FORGE_MAGIC_BASE = int(os.environ.get("FORGE_MAGIC_NUMBER", "202401"))
FORGE_MAGIC_MAX  = 9999  # FORGE range: [base+1, base+9999]

BROKER_INFO_FILE = _under_root(os.environ.get("MT5_BROKER_FILE",    "MT5/broker_info.json"))

VERSION     = "1.1.0"
VALID_MODES = ("OFF", "WATCH", "SIGNAL", "SCALPER", "HYBRID", "AUTO_SCALPER")
BRIDGE_PIN_MODE = os.environ.get("BRIDGE_PIN_MODE", "").upper().strip()

# AUTO_SCALPER config
AUTO_SCALPER_LOT_SIZE      = float(os.environ.get("AUTO_SCALPER_LOT_SIZE",      "0.01"))
AUTO_SCALPER_NUM_TRADES    = int(os.environ.get("AUTO_SCALPER_NUM_TRADES",      "4"))
AUTO_SCALPER_POLL_INTERVAL = int(os.environ.get("AUTO_SCALPER_POLL_INTERVAL",   "120"))
AUTO_SCALPER_MAX_GROUPS    = int(os.environ.get("AUTO_SCALPER_MAX_GROUPS",      "2"))

# SIGNAL mode config
SIGNAL_LOT_SIZE    = float(os.environ.get("SIGNAL_LOT_SIZE",    "0.01"))
SIGNAL_NUM_TRADES  = int(os.environ.get("SIGNAL_NUM_TRADES",    "4"))
SIGNAL_EXPIRY_SEC  = int(os.environ.get("SIGNAL_EXPIRY_SEC",    "60"))   # 60s default — scalping signals must be fresh
PENDING_ORDER_TIMEOUT_SEC = int(os.environ.get("PENDING_ORDER_TIMEOUT_SEC", "3600"))  # 1h — auto-cancel fulfilled-pending orders that never trigger
# BRIDGE scalper path config (no AEGIS gating)
SCALPER_LOT_SIZE   = float(os.environ.get("SCALPER_LOT_SIZE", "0.01"))
SCALPER_NUM_TRADES = max(1, int(os.environ.get("SCALPER_NUM_TRADES", "4")))

# Mode persistence across restarts
RESTORE_MODE_ON_RESTART = os.environ.get("RESTORE_MODE_ON_RESTART", "true").lower() == "true"

# Sentinel override
SENTINEL_OVERRIDE_DURATION = int(os.environ.get("SENTINEL_OVERRIDE_DURATION_SEC", "600"))  # 10min default

# Native scalper mode (passed to FORGE via config.json)
FORGE_SCALPER_MODE = os.environ.get("FORGE_SCALPER_MODE", "NONE").upper()
FORGE_PENDING_ENTRY_THRESHOLD_POINTS = float(os.environ.get("FORGE_PENDING_ENTRY_THRESHOLD_POINTS", "50"))
FORGE_TREND_STRENGTH_ATR_THRESHOLD = float(os.environ.get("FORGE_TREND_STRENGTH_ATR_THRESHOLD", "0.20"))
FORGE_BREAKOUT_BUFFER_POINTS = float(os.environ.get("FORGE_BREAKOUT_BUFFER_POINTS", "10"))
SYDNEY_OPEN_ALERT_ENABLED = os.environ.get("SYDNEY_OPEN_ALERT_ENABLED", "true").lower() == "true"

# Drawdown protection
DD_EQUITY_CLOSE_ALL_PCT  = float(os.environ.get("DD_EQUITY_CLOSE_ALL_PCT",  "3.0"))
DD_FLOATING_BLOCK_PCT    = float(os.environ.get("DD_FLOATING_BLOCK_PCT",    "2.0"))   # block new groups if floating loss exceeds this % of balance
DD_LOSS_COOLDOWN_SEC     = int(os.environ.get("DD_LOSS_COOLDOWN_SEC",       "300"))   # seconds to wait after a group closes at loss before AUTO_SCALPER resumes

# Entry-zone / fill-rate controls (see docs/AEGIS.md § Entry Zone Width Guard)
SIGNAL_ENTRY_TYPE          = os.environ.get("SIGNAL_ENTRY_TYPE", "limit").strip().lower()
if SIGNAL_ENTRY_TYPE not in ("limit", "market"):
    SIGNAL_ENTRY_TYPE = "limit"
SIGNAL_ENTRY_ZONE_CLUSTER  = os.environ.get("SIGNAL_ENTRY_ZONE_CLUSTER", "false").strip().lower() in ("1", "true", "yes", "on")
SIGNAL_ENTRY_CLUSTER_PIPS  = float(os.environ.get("SIGNAL_ENTRY_CLUSTER_PIPS", "2.0"))
PENDING_CANCEL_ON_GROUP_CLOSE = os.environ.get("PENDING_CANCEL_ON_GROUP_CLOSE", "true").strip().lower() in ("1", "true", "yes", "on")
# Profit-ratchet: lock SL to entry+lock_pips once a leg is in profit by trigger_pips.
# Opt-in (default false) so existing groups behave exactly as before unless the
# operator explicitly enables it. See docs/CLI_API_CHEATSHEET.md § "Profit ratchet".
PROFIT_RATCHET_ENABLED = os.environ.get("PROFIT_RATCHET_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
# Pip convention used by the ratchet (trader-style, matches the SCRIBE pips
# column and AURUM/Athena reports):
#   XAU/XAG  : 1 pip = $0.10  -> LOCK_PIPS=10 means SL pinned $1.00 past entry
#   JPY pairs: 1 pip = 0.01
#   majors   : 1 pip = 0.0001
# This deliberately diverges from _pip_size_for_symbol (which uses broker
# points = $0.01 for XAU) so the env-var value matches what the operator
# sees in trade_closures.pips and Telegram alerts.
try:
    PROFIT_RATCHET_TRIGGER_PIPS = float(os.environ.get("PROFIT_RATCHET_TRIGGER_PIPS", "15"))
except (TypeError, ValueError):
    PROFIT_RATCHET_TRIGGER_PIPS = 15.0
try:
    PROFIT_RATCHET_LOCK_PIPS = float(os.environ.get("PROFIT_RATCHET_LOCK_PIPS", "10"))
except (TypeError, ValueError):
    PROFIT_RATCHET_LOCK_PIPS = 10.0
if PROFIT_RATCHET_TRIGGER_PIPS <= PROFIT_RATCHET_LOCK_PIPS:
    # The trigger must exceed the lock or the move is meaningless.
    PROFIT_RATCHET_LOCK_PIPS = max(0.0, PROFIT_RATCHET_TRIGGER_PIPS - 1.0)
# Hybrid TP tightening alongside the SL pin: when a leg crosses the trigger,
# also pull its TP down (BUY) / up (SELL) to current_price ± buffer * pip_size
# so further forward movement closes the leg with a TP_HIT (positive close)
# instead of letting the SL ratchet catch it on a retrace. Per-ticket scope:
# the leg that crossed the trigger is the only one tightened — sibling legs
# in the same group keep their original TP1/TP2/TP3 targets and continue
# running. Set to 0 to disable TP tightening (pure SL ratchet behaviour).
try:
    PROFIT_RATCHET_TP_BUFFER_PIPS = float(os.environ.get("PROFIT_RATCHET_TP_BUFFER_PIPS", "5"))
except (TypeError, ValueError):
    PROFIT_RATCHET_TP_BUFFER_PIPS = 5.0
if PROFIT_RATCHET_TP_BUFFER_PIPS < 0:
    PROFIT_RATCHET_TP_BUFFER_PIPS = 0.0
# Optional SIGNAL-source override of TP1_CLOSE_PCT (mirrors AEGIS_SIGNAL_MIN_RR pattern)
_SIG_TP1_RAW = os.environ.get("SIGNAL_TP1_CLOSE_PCT", "").strip()
try:
    SIGNAL_TP1_CLOSE_PCT = float(_SIG_TP1_RAW) if _SIG_TP1_RAW else None
except (TypeError, ValueError):
    SIGNAL_TP1_CLOSE_PCT = None

for d in ("config", "data", "logs"):
    Path(_PY, d).mkdir(parents=True, exist_ok=True)
Path(_ROOT, "MT5").mkdir(parents=True, exist_ok=True)


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        log.warning("Failed to read %s: %s", path, e)
        return {}

def _write_json(path: str, data: dict):
    try:
        atomic_write_json(path, data)
    except Exception as e:
        log.error(f"Write {path} error: {e}")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _coerce_unix_ts(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_legacy_aurum_exec_payload(payload: dict) -> dict:
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


# ── Structured trade log ─────────────────────────────────────────
# Format: [SOURCE|EVENT] G<id> #<ticket> detail
# Source: SIGNAL, AURUM, SCALPER, FORGE_NATIVE, TRACKER, MGMT, SYSTEM
# Grep-friendly: grep 'G20' or grep '\[TRACKER|CLOSE\]' or grep '#1122706681'
def _tlog(source: str, event: str, msg: str,
          group_id=None, ticket=None, level: str = "info"):
    parts = [f"[{source}|{event}]"]
    if group_id is not None:
        parts.append(f"G{group_id}")
    if ticket is not None:
        parts.append(f"#{ticket}")
    parts.append(msg)
    line = " ".join(parts)
    getattr(log, level, log.info)(line)


def _forge_command_targets() -> list[str]:
    """Paths that receive BRIDGE → FORGE command.json (primary + optional mirror)."""
    paths: list[str] = [CMD_FILE_MT5]
    if CMD_FILE_MT5_MIRROR:
        m = (
            CMD_FILE_MT5_MIRROR
            if os.path.isabs(CMD_FILE_MT5_MIRROR)
            else _under_root(CMD_FILE_MT5_MIRROR)
        )
        try:
            if Path(m).resolve() != Path(CMD_FILE_MT5).resolve():
                paths.append(m)
        except OSError:
            paths.append(m)
    return paths


def _write_forge_command(cmd: dict) -> list[str]:
    """Write the same command payload to primary (and optional mirror) paths."""
    written: list[str] = []
    for pth in _forge_command_targets():
        _write_json(pth, cmd)
        written.append(os.path.abspath(pth))
    return written


# ── FORGE command queue ──────────────────────────────────────────
# FORGE polls MT5/command.json on its OnTimer and dedups by `timestamp`. A
# single shared file means rapid-fire BRIDGE writes race: each write
# overwrites the previous payload before FORGE has a chance to consume it,
# so all but the latest command are silently lost. This bit the live
# profit-ratchet test on G64 — leg 0 never moved its SL because the next 3
# ratchet writes clobbered it, then BRIDGE's drift detector "learned" the
# stale live SL back into its in-memory cache and never retried.
#
# The queue serialises FORGE writes: at most one command is in-flight at any
# time. Each BRIDGE tick the queue pumps once — verifying the in-flight
# command via a caller-supplied `verifier(mt5)` (or auto-acking after a
# timeout for fire-and-forget shapes), then popping the next pending entry.
# Lost commands are retried automatically; chronically un-ackable commands
# fire `on_drop` so callers (e.g. ratchet) can release their dedup tokens
# and try again on the next eligibility window.
_FORGE_QUEUE_ACK_TIMEOUT_SEC = float(os.environ.get("FORGE_QUEUE_ACK_TIMEOUT_SEC", "8.0"))
_FORGE_QUEUE_MAX_RETRIES = max(0, int(os.environ.get("FORGE_QUEUE_MAX_RETRIES", "2")))


@dataclass
class _ForgeQueueItem:
    cmd: dict
    description: str = ""
    verifier: Optional[Callable[[dict], bool]] = None
    on_drop: Optional[Callable[[], None]] = None
    dedup_key: Optional[str] = None
    enqueued_at: float = field(default_factory=time.time)
    written_at: Optional[float] = None
    retries: int = 0


class _ForgeCommandQueue:
    """In-memory FIFO that serialises FORGE command.json writes.

    Behaviour:
      • At most one command is in-flight (written but not yet ack'd).
      • `pump(mt5)` is called once per BRIDGE tick. It checks the in-flight
        verifier and either:
          - clears it (acked) and pops the next pending command, or
          - re-writes it on timeout (up to MAX_RETRIES), or
          - drops it after retries are exhausted, calling `on_drop`.
      • If `verifier is None`, the command is treated as fire-and-forget and
        is acked on the very next pump (so subsequent commands still see a
        ≥1-tick spacing, which is plenty for FORGE's OnTimer to consume).
      • `dedup_key` lets callers suppress duplicate enqueues (e.g. don't
        re-enqueue the same MODIFY_SL while one is already pending/in-flight).
    """

    ACK_TIMEOUT_SEC = _FORGE_QUEUE_ACK_TIMEOUT_SEC
    MAX_RETRIES = _FORGE_QUEUE_MAX_RETRIES

    def __init__(self, writer: Callable[[dict], list]):
        self._writer = writer
        self._pending: "deque[_ForgeQueueItem]" = deque()
        self._inflight: Optional[_ForgeQueueItem] = None

    # ── Inspection helpers ──
    def __len__(self) -> int:
        return len(self._pending) + (1 if self._inflight else 0)

    def has_inflight(self) -> bool:
        return self._inflight is not None

    def has_pending_or_inflight(self, predicate: Callable[[dict], bool]) -> bool:
        """Return True if any item (in-flight or pending) matches predicate(cmd)."""
        try:
            if self._inflight is not None and predicate(self._inflight.cmd):
                return True
            return any(predicate(it.cmd) for it in self._pending)
        except Exception:
            return False

    def has_inflight_modify_for_ticket(self, ticket: int) -> bool:
        """True if a MODIFY_SL/MODIFY_TP for this ticket is queued or in-flight.

        Used by the drift detector to skip the "learn-back" branch while a
        scoped modify is still propagating to MT5 — otherwise BRIDGE would
        cache the pre-modify live value and never retry on timeout.
        """
        try:
            t = int(ticket)
        except (TypeError, ValueError):
            return False

        def _match(cmd: dict) -> bool:
            action = str(cmd.get("action") or "").upper()
            if action not in ("MODIFY_SL", "MODIFY_TP"):
                return False
            try:
                return int(cmd.get("ticket", 0) or 0) == t
            except (TypeError, ValueError):
                return False

        return self.has_pending_or_inflight(_match)

    # ── Enqueue / pump ──
    def enqueue(
        self,
        cmd: dict,
        *,
        verifier: Optional[Callable[[dict], bool]] = None,
        description: str = "",
        on_drop: Optional[Callable[[], None]] = None,
        dedup_key: Optional[str] = None,
    ) -> Optional[_ForgeQueueItem]:
        if dedup_key is not None and self._has_dedup_key(dedup_key):
            log.debug("BRIDGE queue: deduped enqueue %s (key=%s)", description, dedup_key)
            return None
        item = _ForgeQueueItem(
            cmd=dict(cmd),
            description=description,
            verifier=verifier,
            on_drop=on_drop,
            dedup_key=dedup_key,
        )
        self._pending.append(item)
        return item

    def _has_dedup_key(self, key: str) -> bool:
        if self._inflight is not None and self._inflight.dedup_key == key:
            return True
        return any(it.dedup_key == key for it in self._pending)

    def pump(self, mt5: dict) -> None:
        # 1. Reconcile the in-flight command.
        if self._inflight is not None:
            verifier = self._inflight.verifier
            acked = False
            if verifier is None:
                # Fire-and-forget: ack on the first pump after the write so
                # we still introduce one-tick spacing between writes.
                if self._inflight.written_at is not None:
                    acked = True
            else:
                try:
                    acked = bool(verifier(mt5 or {}))
                except Exception as e:
                    log.debug("BRIDGE queue: verifier raised for %s: %s",
                              self._inflight.description, e)
                    acked = False
            if acked:
                log.debug("BRIDGE queue: ACK %s", self._inflight.description)
                self._inflight = None
            else:
                age = time.time() - (self._inflight.written_at or time.time())
                if age >= self.ACK_TIMEOUT_SEC:
                    if self._inflight.retries >= self.MAX_RETRIES:
                        log.warning(
                            "BRIDGE queue: dropping unacked '%s' after %d retries",
                            self._inflight.description, self._inflight.retries,
                        )
                        cb = self._inflight.on_drop
                        self._inflight = None
                        if cb is not None:
                            try:
                                cb()
                            except Exception as e:
                                log.debug("BRIDGE queue: on_drop callback raised: %s", e)
                    else:
                        self._inflight.retries += 1
                        log.warning(
                            "BRIDGE queue: retry %d/%d for '%s'",
                            self._inflight.retries, self.MAX_RETRIES,
                            self._inflight.description,
                        )
                        self._write_inflight()
                        return  # one write per pump
                else:
                    return  # still waiting for ack

        # 2. Pop the next pending command (if any).
        if self._inflight is None and self._pending:
            self._inflight = self._pending.popleft()
            self._write_inflight()

    def _write_inflight(self) -> None:
        if self._inflight is None:
            return
        cmd = dict(self._inflight.cmd)
        # Stamp a fresh timestamp on every write so FORGE's timestamp-dedup
        # picks up retries as new commands.
        cmd["timestamp"] = _now()
        try:
            self._writer(cmd)
            self._inflight.written_at = time.time()
            log.debug("BRIDGE queue: wrote %s", self._inflight.description)
        except Exception as e:
            log.warning("BRIDGE queue: write failed for '%s': %s",
                        self._inflight.description, e)


def _forge_config_targets() -> list[str]:
    """config.json paths: primary + sibling of mirrored command.json when mirror is set."""
    paths: list[str] = [CFG_FILE_MT5]
    if not CMD_FILE_MT5_MIRROR:
        return paths
    cmd_mirror = (
        CMD_FILE_MT5_MIRROR
        if os.path.isabs(CMD_FILE_MT5_MIRROR)
        else _under_root(CMD_FILE_MT5_MIRROR)
    )
    alt = str(Path(cmd_mirror).resolve().parent / "config.json")
    try:
        if Path(alt).resolve() != Path(CFG_FILE_MT5).resolve():
            paths.append(alt)
    except OSError:
        paths.append(alt)
    return paths


def _log_mt5_forge_integration_hint():
    """
    Explain why SCRIBE can show groups while MT5 has no orders: different directories.
    Call once at BRIDGE startup after paths are known.
    """
    cmd_parent = Path(CMD_FILE_MT5).resolve().parent
    mkt_parent = Path(MARKET_FILE).resolve().parent
    if cmd_parent != mkt_parent:
        log.error(
            "BRIDGE MISCONFIG: command.json and market_data.json resolve to different "
            "directories — %s vs %s",
            cmd_parent,
            mkt_parent,
        )
    mt5 = _read_json(MARKET_FILE)
    if not mt5:
        log.warning(
            "No readable market_data.json at %s — FORGE is not feeding this path "
            "(EA off, wrong MT5_*_FILE, or different Common Files folder).",
            os.path.abspath(MARKET_FILE),
        )
        return
    now = time.time()
    tsu = mt5.get("timestamp_unix")
    try:
        age = now - float(tsu) if tsu is not None else 9999.0
    except (TypeError, ValueError):
        age = 9999.0
    fv = mt5.get("forge_version") or mt5.get("hermes_version", "?")
    cycle = mt5.get("ea_cycle", "?")
    log.info(
        "MT5 file bus: FORGE → market_data (%s, ea_cycle=%s, age=%.0fs). "
        "command.json must be in the same folder FORGE uses: %s",
        fv,
        cycle,
        age,
        cmd_parent,
    )
    if age > MT5_STALE_SEC:
        log.warning(
            "market_data.json is stale (%.0fs) — EA may be writing elsewhere; "
            "fix MT5/ symlink or set MT5_*_FILE / MT5_CMD_FILE_MIRROR (docs/FORGE_BRIDGE.md).",
            age,
        )
    mt5_dir = Path(_ROOT, "MT5")
    if (
        sys.platform == "darwin"
        and mt5_dir.exists()
        and not mt5_dir.is_symlink()
        and not os.environ.get("MT5_CMD_FILE")
        and not CMD_FILE_MT5_MIRROR
    ):
        log.warning(
            "Repo MT5/ is not a symlink. On macOS, native MT5 reads Common Files; "
            "BRIDGE default writes repo MT5/command.json — FORGE often never sees it. "
            "Symlink MT5/ → …/MetaQuotes/Terminal/Common/Files or set MT5_CMD_FILE / "
            "MT5_CMD_FILE_MIRROR (docs/FORGE_BRIDGE.md)."
        )

def _session() -> str:
    """Return current kill-zone session from UTC clock (see trading_session.py)."""
    return get_trading_session_utc()


def _resolve_forge_scalper_mode(mode: str) -> str:
    """
    FORGE native scalper should only be enabled when the strategy mode includes
    scalping logic (SCALPER or HYBRID). Other modes force NONE.
    """
    return FORGE_SCALPER_MODE if mode in ("SCALPER", "HYBRID") else "NONE"


def _extract_forge_thresholds(mt5_data: dict) -> dict:
    cfg = (mt5_data or {}).get("forge_config") or {}
    return {
        "pending_entry_threshold_points": cfg.get(
            "pending_entry_threshold_points",
            (mt5_data or {}).get("pending_entry_threshold_points"),
        ),
        "trend_strength_atr_threshold": cfg.get(
            "trend_strength_atr_threshold",
            (mt5_data or {}).get("trend_strength_atr_threshold"),
        ),
        "breakout_buffer_points": cfg.get(
            "breakout_buffer_points",
            (mt5_data or {}).get("breakout_buffer_points"),
        ),
    }


def _build_entry_ladder(entry_low: float, entry_high: float, trades: int) -> list[float]:
    trades = max(1, int(trades))
    lo = float(entry_low)
    hi = float(entry_high)
    if trades == 1 or hi <= lo:
        return [round((lo + hi) / 2 if hi > 0 else lo, 2)]
    step = (hi - lo) / (trades - 1)
    return [round(lo + i * step, 2) for i in range(trades)]

def _infer_price_decimals(*values: float) -> int:
    """Infer decimal precision from numeric price values."""
    max_dec = 0
    for v in values:
        try:
            s = f"{float(v):.10f}".rstrip("0").rstrip(".")
            if "." in s:
                max_dec = max(max_dec, len(s.split(".")[1]))
        except (TypeError, ValueError):
            continue
    return max_dec


def _pip_size_for_symbol(symbol: str | None, open_price: float, close_price: float) -> float:
    """
    Infer pip size for reporting:
      - XAU/XAG metals: 0.01
      - JPY FX pairs: 0.01
      - Major/minor FX: 0.0001
      - Fallback by decimals: 10*point for 2/3/5-digit quotes, else point
    """
    sym = (symbol or "").upper()
    if sym.startswith(("XAU", "XAG")):
        return 0.01
    if len(sym) >= 6 and sym[3:6] == "JPY":
        return 0.01
    if len(sym) >= 6 and sym[:6].isalpha():
        return 0.0001

    dec = _infer_price_decimals(open_price, close_price)
    if dec <= 0:
        return 1.0
    point = 10 ** (-dec)
    if dec in (2, 3, 5):
        return point * 10.0
    return point


def _calc_pips(symbol: str | None, direction: str, open_price: float, close_price: float) -> float:
    if not open_price or not close_price:
        return 0.0
    raw = float(close_price) - float(open_price)
    if (direction or "").upper() == "SELL":
        raw = -raw
    pip_size = _pip_size_for_symbol(symbol, open_price, close_price)
    if pip_size <= 0:
        pip_size = 1.0
    return round(raw / pip_size, 1)

def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _recent_closed_deals_by_ticket(mt5_data: dict) -> dict[int, dict]:
    """
    Build latest-close-deal map keyed by position ticket from market_data.recent_closed_deals.
    """
    out: dict[int, dict] = {}
    for row in (mt5_data or {}).get("recent_closed_deals") or []:
        if not isinstance(row, dict):
            continue
        tval = _safe_float(row.get("position_ticket", row.get("ticket")))
        if tval is None:
            continue
        ticket = int(tval)
        if ticket <= 0:
            continue
        row_ts = _safe_float(row.get("time_unix")) or 0.0
        prev = out.get(ticket)
        prev_ts = _safe_float((prev or {}).get("time_unix")) or 0.0
        if prev is not None and prev_ts >= row_ts:
            continue
        out[ticket] = dict(row)
    return out


def _deal_close_time_iso(deal_row: dict) -> str | None:
    ts = _safe_float((deal_row or {}).get("time_unix"))
    if ts is None or ts <= 0:
        return None
    try:
        return datetime.fromtimestamp(ts, timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def _close_reason_from_broker_hint(
    reason_hint: str,
    close_price: float,
    group_id: int | None,
    match_tp_stage_fn,
) -> str | None:
    hint = (reason_hint or "").strip().upper()
    if not hint:
        return None
    if hint in ("SL_HIT", "DEAL_REASON_SL"):
        return "SL_HIT"
    if hint in ("TP1_HIT", "TP2_HIT", "TP3_HIT"):
        return hint
    if hint in ("TP_HIT", "DEAL_REASON_TP"):
        return match_tp_stage_fn(close_price, group_id, 1.2)
    if hint in (
        "MANUAL_CLOSE",
        "DEAL_REASON_CLIENT",
        "DEAL_REASON_EXPERT",
        "DEAL_REASON_MOBILE",
        "DEAL_REASON_WEB",
    ):
        return "MANUAL_CLOSE"
    if hint in ("DEAL_REASON_SO", "STOP_OUT", "DEAL_REASON_VMARGIN"):
        return "UNKNOWN"
    return None


_TP_STAGE_RE = re.compile(r"\|TP(\d+)")


def _parse_tp_stage_from_comment(comment) -> int | None:
    """Extract the FORGE leg stage encoded in a position/order comment.

    Comment grammar emitted by FORGE: ``FORGE|G<group>|<leg_index>|TP<stage>``.
    Returns 1/2/3 when present, otherwise None.
    """
    if not comment:
        return None
    m = _TP_STAGE_RE.search(str(comment))
    if not m:
        return None
    try:
        stage = int(m.group(1))
    except (TypeError, ValueError):
        return None
    return stage if stage in (1, 2, 3) else None


def _ratchet_pip_size(symbol: str | None) -> float:
    """Trader-style pip size for the profit ratchet.

    XAU / XAG : 0.10  (1 pip = $0.10)  — matches SCRIBE trade_closures.pips
    JPY pairs : 0.01
    majors    : 0.0001
    fallback  : 0.10  (assume metals when symbol is unknown)
    """
    sym = (symbol or "").upper()
    if sym.startswith(("XAU", "XAG")):
        return 0.10
    if len(sym) >= 6 and sym[3:6] == "JPY":
        return 0.01
    if len(sym) >= 6 and sym[:6].isalpha():
        return 0.0001
    return 0.10


def _coerce_modify_scope(cmd: dict) -> tuple[int | None, int | None]:
    """Extract the optional MODIFY scope fields from an AURUM/MGMT cmd.

    Returns ``(ticket, tp_stage)`` with each field validated independently.
    A ticket of <= 0 or a stage outside 1..3 is treated as unset.
    """
    ticket_raw = cmd.get("ticket") if isinstance(cmd, dict) else None
    stage_raw = cmd.get("tp_stage") if isinstance(cmd, dict) else None
    ticket = None
    if ticket_raw not in (None, ""):
        try:
            t = int(ticket_raw)
            if t > 0:
                ticket = t
        except (TypeError, ValueError):
            ticket = None
    stage = None
    if stage_raw not in (None, ""):
        try:
            s = int(stage_raw)
            if s in (1, 2, 3):
                stage = s
        except (TypeError, ValueError):
            stage = None
    return ticket, stage


def _entry_legs_from_ladder(entry_ladder: list[float]) -> list[dict]:
    return [
        {"order_type": "AUTO", "entry_price": float(px)}
        for px in (entry_ladder or [])
        if px is not None
    ]


def _apply_signal_placement(direction: str, entry_low: float, entry_high: float,
                             ladder: list[float], num_trades: int,
                             current_price: float | None = None) -> tuple[list[float], str, bool]:
    """Apply SIGNAL_ENTRY_TYPE / SIGNAL_ENTRY_ZONE_CLUSTER overrides to the
    AEGIS-built ladder. Returns (new_ladder, entry_type_label, cluster_flag).

    - SIGNAL_ENTRY_TYPE=market: collapse all legs to current_price (or zone
      midpoint as fallback) so FORGE places market orders.
    - SIGNAL_ENTRY_ZONE_CLUSTER=true: spread legs evenly within the cluster
      band [edge, edge ± SIGNAL_ENTRY_CLUSTER_PIPS] at the directional zone
      edge (entry_low for SELL, entry_high for BUY) instead of across the
      full zone.
    - default (limit, no cluster): leave the AEGIS ladder unchanged.
    """
    n = max(1, int(num_trades or 1))
    d = (direction or "").upper()
    lo = float(entry_low)
    hi = float(entry_high)

    if SIGNAL_ENTRY_TYPE == "market":
        anchor = current_price if (current_price and current_price > 0) else (lo + hi) / 2.0
        try:
            anchor = float(anchor)
        except (TypeError, ValueError):
            anchor = (lo + hi) / 2.0
        return [round(anchor, 2)] * n, "market", False

    if SIGNAL_ENTRY_ZONE_CLUSTER:
        edge = lo if d == "BUY" else hi
        band = max(0.0, float(SIGNAL_ENTRY_CLUSTER_PIPS))
        if d == "BUY":
            lo_b = edge
            hi_b = min(hi, edge + band)
        else:
            hi_b = edge
            lo_b = max(lo, edge - band)
        if n == 1 or hi_b <= lo_b:
            return [round((lo_b + hi_b) / 2.0, 2)] * n, "limit", True
        step = (hi_b - lo_b) / (n - 1)
        return [round(lo_b + i * step, 2) for i in range(n)], "limit", True

    # default: keep AEGIS ladder as-is
    return list(ladder or []), "limit", False


def _normalize_forge_entry_legs(raw_legs) -> list[dict]:
    from contracts.aurum_forge import normalize_entry_legs

    return normalize_entry_legs(raw_legs)


class Bridge:
    def __init__(self):
        self.scribe   = get_scribe()
        self.herald   = get_herald()
        self.sentinel    = Sentinel()
        self.lens        = get_lens()
        self.aegis       = get_aegis()
        self.regime_engine = get_regime_engine()
        self.listener    = Listener()
        self.aurum       = get_aurum()
        self.reconciler  = get_reconciler()

        # Restore previous mode or use default
        default_mode = os.environ.get("DEFAULT_MODE", "SIGNAL")
        if RESTORE_MODE_ON_RESTART:
            try:
                prev_status = _read_json(STATUS_FILE)
                saved_mode = prev_status.get("mode", "").upper()
                if saved_mode in VALID_MODES:
                    default_mode = saved_mode
                    log.info(f"BRIDGE: restoring previous mode '{saved_mode}' from status.json")
            except Exception:
                pass
        self._mode               = default_mode
        self._prev_mode          = None
        self._sentinel_override  = False
        self._mt5_blind_override = False
        self._cycle              = 0
        self._last_signal_id     = None
        self._last_mgmt_ts       = None
        self._last_lens_ts       = 0
        self._last_sentinel_ts   = 0
        self._last_mt5_alert_ts  = 0
        self._mt5_read_fail_streak = 0
        self._last_mt5_good_unix = 0.0
        self._last_mt5_snapshot = {}
        self._last_recon_ts      = 0
        self._open_groups        = {}
        self._last_auto_scalper_ts  = 0
        self._last_sydney_open_alert_key = None
        self._sentinel_user_override = False   # user manually bypassed sentinel
        self._sentinel_override_until = 0      # auto-revert timestamp
        # Drawdown protection state
        self._session_peak_equity  = 0.0
        self._dd_close_all_fired   = False
        self._last_loss_close_ts   = 0
        # Position tracker
        self._known_positions: dict[int, dict] = {}   # ticket → snapshot
        self._known_unmanaged_positions: dict[int, dict] = {}   # ticket → snapshot (manual/non-FORGE)
        self._known_pendings:  dict[int, dict] = {}   # ticket → snapshot
        self._tracker_seeded = False
        # Profit-ratchet bookkeeping: tickets we've already nudged so we don't
        # spam FORGE with the same MODIFY_SL every tick. Cleared on close, on
        # ratchet drop (so the next eligibility window can retry), and on
        # SIGNAL group close (to wipe stale entries pointing at recycled tickets).
        self._profit_ratcheted: set[int] = set()
        # FORGE command queue: serialises command.json writes so rapid-fire
        # MODIFY_SL/MODIFY_TP sequences (per-ticket profit-ratchet, multi-stage
        # MGMT modifies) don't race against each other on the shared file. See
        # _ForgeCommandQueue near _write_forge_command for the protocol.
        self._forge_queue = _ForgeCommandQueue(_write_forge_command)
        # Session tracking
        self._current_session    = "OFF_HOURS"
        self._current_session_id = None    # SCRIBE trading_sessions row id
        self._broker_info        = {}      # from FORGE broker_info.json
        self._pending_entry_threshold_points = FORGE_PENDING_ENTRY_THRESHOLD_POINTS
        self._trend_strength_atr_threshold = FORGE_TREND_STRENGTH_ATR_THRESHOLD
        self._breakout_buffer_points = FORGE_BREAKOUT_BUFFER_POINTS
        self._regime_snapshot: dict = {}
    def _pinned_mode(self) -> str | None:
        if BRIDGE_PIN_MODE in VALID_MODES:
            return BRIDGE_PIN_MODE
        return None

    # ── Position tracker ─────────────────────────────────────────
    def _resolve_group_for_magic(self, magic: int) -> int | None:
        """Return the SCRIBE trade_group id that owns this magic number, or None."""
        for gid, g in self._open_groups.items():
            if g.get("magic_number") == magic:
                return int(gid)
        # Fallback: query SCRIBE for any group (OPEN or CLOSED) with this magic
        rows = self.scribe.query(
            "SELECT id FROM trade_groups WHERE magic_number=? ORDER BY id DESC LIMIT 1",
            (magic,),
        )
        return int(rows[0]["id"]) if rows else None

    def _seed_tracker_from_scribe(self, mt5: dict) -> None:
        """On first tick after startup, seed known positions/pendings from SCRIBE
        to avoid re-logging positions that survived a BRIDGE restart."""
        # Seed from SCRIBE OPEN positions
        try:
            open_pos = self.scribe.query(
                "SELECT ticket, trade_group_id, magic_number, direction, entry_price, sl, tp "
                "FROM trade_positions WHERE status='OPEN' AND ticket IS NOT NULL"
            )
            for r in open_pos:
                t = int(r["ticket"])
                magic = int(r.get("magic_number") or 0)
                target = (
                    self._known_positions
                    if FORGE_MAGIC_BASE <= magic < FORGE_MAGIC_BASE + FORGE_MAGIC_MAX + 1
                    else self._known_unmanaged_positions
                )
                target[t] = {
                    "group_id": r["trade_group_id"],
                    "magic": magic,
                    "direction": r["direction"],
                    "open_price": r["entry_price"],
                    "last_profit": 0,
                    "current_price": r["entry_price"],
                    "lot_size": 0,
                    "symbol": None,
                    "sl": r.get("sl"), "tp": r.get("tp"),
                }
        except Exception as e:
            log.warning("TRACKER seed from SCRIBE failed: %s", e)

        # Also seed from current market_data to catch positions SCRIBE doesn't know about yet
        for p in mt5.get("open_positions") or []:
            magic = int(p.get("magic", 0) or 0)
            forge_managed = p.get("forge_managed")
            if forge_managed is None:
                forge_managed = (
                    magic >= FORGE_MAGIC_BASE and magic < FORGE_MAGIC_BASE + FORGE_MAGIC_MAX + 1
                )
            if forge_managed:
                t = int(p["ticket"])
                # Backfill tp_stage from FORGE comment whenever SCRIBE missed it.
                try:
                    self.scribe.backfill_tp_stage_from_comment(t, p.get("comment"))
                except Exception as _e:
                    log.debug("TRACKER: tp_stage seed backfill tolerated: %s", _e)
                if t not in self._known_positions:
                    self._known_positions[t] = {
                        "group_id": self._resolve_group_for_magic(magic),
                        "magic": magic,
                        "direction": p.get("type", "SELL"),
                        "open_price": p.get("open_price"),
                        "last_profit": p.get("profit", 0),
                        "current_price": p.get("current_price"),
                        "lot_size": p.get("lots", 0),
                        "sl": p.get("sl"), "tp": p.get("tp"),
                    }
            else:
                t = int(p["ticket"])
                if t not in self._known_unmanaged_positions:
                    self._known_unmanaged_positions[t] = {
                        "group_id": None,
                        "magic": magic,
                        "symbol": p.get("symbol"),
                        "direction": p.get("type", "SELL"),
                        "open_price": p.get("open_price"),
                        "last_profit": p.get("profit", 0),
                        "current_price": p.get("current_price"),
                        "lot_size": p.get("lots", 0),
                        "sl": p.get("sl"), "tp": p.get("tp"),
                    }

        for o in mt5.get("pending_orders") or []:
            if not o.get("forge_managed"):
                continue
            t = int(o["ticket"])
            if t not in self._known_pendings:
                magic = o.get("magic", 0)
            self._known_pendings[t] = {
                    "group_id": self._resolve_group_for_magic(magic),
                    "magic": magic,
                    "order_type": o.get("order_type"),
                    "price": o.get("price"),
                    "tracked_since": time.time(),  # start timeout from restart
                }

        log.info(
            "TRACKER seeded: %d managed positions, %d unmanaged positions, %d pendings from SCRIBE + market_data",
            len(self._known_positions),
            len(self._known_unmanaged_positions),
            len(self._known_pendings),
        )
        self._tracker_seeded = True

    def _infer_close_reason(self, close_price: float, sl: float, tp: float,
                            direction: str, group_id: int) -> str:
        """Infer SL_HIT / TP1_HIT / TP2_HIT / TP3_HIT / MANUAL_CLOSE
        by comparing close_price to the position's SL and TP levels.
        Tolerance: $0.50 (XAUUSD spread + slippage).
        Zero SL/TP (no stop set) is treated as unset, not matched.
        """
        TOL = 0.50  # $0.50 tolerance for XAUUSD
        if not close_price or close_price <= 0:
            return "UNKNOWN"

        # Check SL (skip if unset / zero — FORGE reports 0.00 for no SL)
        if sl and sl > 100 and abs(close_price - sl) <= TOL:
            return "SL_HIT"

        # Check TP (skip if unset / zero)
        if tp and tp > 100 and abs(close_price - tp) <= TOL:
            # Determine which TP stage by looking up the group's original targets
            return self._match_tp_stage(close_price, group_id, TOL)

        # Also check group-level TP1/TP2/TP3 in case position TP was modified
        if group_id is not None:
            try:
                rows = self.scribe.query(
                    "SELECT sl, tp1, tp2, tp3 FROM trade_groups WHERE id=?",
                    (group_id,))
                if rows:
                    g = rows[0]
                    g_sl = g.get("sl") or 0
                    if g_sl > 100 and abs(close_price - g_sl) <= TOL:
                        return "SL_HIT"
                    for tp_name, tp_val in [("tp1", g.get("tp1")),
                                            ("tp2", g.get("tp2")),
                                            ("tp3", g.get("tp3"))]:
                        if tp_val and tp_val > 100 and abs(close_price - tp_val) <= TOL:
                            return tp_name.upper() + "_HIT"
            except Exception:
                pass

        # Close price doesn't match SL or TP — manual or partial close
        return "MANUAL_CLOSE"

    def _match_tp_stage(self, close_price: float, group_id: int,
                        tol: float) -> str:
        """Match close_price to TP1/TP2/TP3 from the trade_group record."""
        if group_id is None:
            return "TP1_HIT"
        try:
            rows = self.scribe.query(
                "SELECT tp1, tp2, tp3 FROM trade_groups WHERE id=?",
                (group_id,))
            if not rows:
                return "TP1_HIT"
            g = rows[0]
            if g.get("tp3") and abs(close_price - g["tp3"]) <= tol:
                return "TP3_HIT"
            if g.get("tp2") and abs(close_price - g["tp2"]) <= tol:
                return "TP2_HIT"
            return "TP1_HIT"
        except Exception:
            return "TP1_HIT"

    def _sync_positions(self, mt5: dict) -> None:
        """Compare market_data.json positions/pendings against SCRIBE each tick.

        Detects fills, SL/TP hits, and cancellations.  Logs to SCRIBE so the
        dashboard/performance stats reflect real broker activity.
        """
        if not mt5:
            return

        if not self._tracker_seeded:
            self._seed_tracker_from_scribe(mt5)
            return  # don't diff on the seed tick

        mode = self._effective_mode()

        # ── Current MT5 state (FORGE-managed only) ─────────────────
        live_positions: dict[int, dict] = {}
        for p in mt5.get("open_positions") or []:
            magic = int(p.get("magic", 0) or 0)
            forge_managed = p.get("forge_managed")
            if forge_managed is None:
                forge_managed = (
                    magic >= FORGE_MAGIC_BASE and magic < FORGE_MAGIC_BASE + FORGE_MAGIC_MAX + 1
                )
            if forge_managed:
                live_positions[int(p["ticket"])] = p
        live_unmanaged_positions: dict[int, dict] = {}
        for p in mt5.get("open_positions") or []:
            magic = int(p.get("magic", 0) or 0)
            forge_managed = p.get("forge_managed")
            if forge_managed is None:
                forge_managed = (
                    magic >= FORGE_MAGIC_BASE and magic < FORGE_MAGIC_BASE + FORGE_MAGIC_MAX + 1
                )
            if not forge_managed:
                live_unmanaged_positions[int(p["ticket"])] = p

        live_pendings: dict[int, dict] = {}
        for o in mt5.get("pending_orders") or []:
            if not o.get("forge_managed"):
                continue
            live_pendings[int(o["ticket"])] = o
        recent_closed_deals = _recent_closed_deals_by_ticket(mt5)

        # ── New filled positions ───────────────────────────────────
        for ticket, p in live_positions.items():
            if ticket in self._known_positions:
                # Update last-known profit for close detection
                self._known_positions[ticket]["last_profit"] = p.get("profit", 0)
                self._known_positions[ticket]["current_price"] = p.get("current_price")
                # ── SL/TP drift detection: catch manual MT5 modifications ──
                live_sl = p.get("sl")
                live_tp = p.get("tp")
                known_sl = self._known_positions[ticket].get("sl")
                known_tp = self._known_positions[ticket].get("tp")
                sl_changed = (live_sl is not None and known_sl is not None
                              and abs(float(live_sl) - float(known_sl)) > 0.005)
                tp_changed = (live_tp is not None and known_tp is not None
                              and abs(float(live_tp) - float(known_tp)) > 0.005)
                if sl_changed or tp_changed:
                    # Suppress "learn-back" while a queued MODIFY for this ticket
                    # is still propagating to MT5 — otherwise the drift detector
                    # would cache the pre-modify live values and the queue's
                    # subsequent verifier would never see the post-modify state
                    # (the in-flight ratchet/MGMT modify would silently revert).
                    if self._forge_queue.has_inflight_modify_for_ticket(ticket):
                        log.debug(
                            "TRACKER: drift for #%s ignored (modify in-flight)", ticket,
                        )
                        continue
                    changes = []
                    if sl_changed:
                        changes.append(f"SL {known_sl}→{live_sl}")
                    if tp_changed:
                        changes.append(f"TP {known_tp}→{live_tp}")
                    _tlog("TRACKER", "SL_TP_MODIFIED", ", ".join(changes), group_id=self._known_positions[ticket].get("group_id"), ticket=ticket)
                    self._known_positions[ticket]["sl"] = live_sl
                    self._known_positions[ticket]["tp"] = live_tp
                    # Update SCRIBE so dashboard/AURUM show correct levels.
                    # Only the drifted ticket is updated — fanning out via
                    # _sync_group_targets would collapse stage-scoped writes
                    # (e.g. a TP2-only MODIFY) onto every leg. The optional
                    # group SL mirror still moves group-wide because operator
                    # intent for SL is conventionally protective for the whole
                    # group, but tp1/tp2/tp3 columns are left untouched here.
                    try:
                        self.scribe.update_position_sl_tp(ticket, sl=live_sl, tp=live_tp)
                    except Exception as e:
                        log.debug("TRACKER: SCRIBE SL/TP update failed: %s", e)
                    gid = self._known_positions[ticket].get("group_id")
                    if sl_changed and gid is not None:
                        try:
                            with self.scribe._conn() as _c:
                                _c.execute(
                                    "UPDATE trade_groups SET sl=? WHERE id=?",
                                    (live_sl, int(gid)),
                                )
                        except Exception as _e:
                            log.debug("TRACKER: group SL mirror tolerated: %s", _e)
                        g = self._open_groups.get(int(gid))
                        if isinstance(g, dict):
                            g["sl"] = live_sl
                    # Log as system event for audit
                    self._bridge_activity(
                        "POSITION_MODIFIED",
                        reason="SL/TP changed (manual or FORGE)",
                        notes=json.dumps({
                            "ticket": ticket, "group_id": gid,
                            "old_sl": known_sl, "new_sl": live_sl,
                            "old_tp": known_tp, "new_tp": live_tp,
                        }, default=str),
                    )
                continue
            # New position appeared — log to SCRIBE (guard against duplicates)
            magic = p.get("magic", 0)
            gid = self._resolve_group_for_magic(magic)
            if gid is None:
                log.warning("TRACKER: position ticket=%s magic=%s has no SCRIBE group", ticket, magic)
                continue
            # Dedup: skip if SCRIBE already has this ticket
            existing = self.scribe.query(
                "SELECT id FROM trade_positions WHERE ticket=? LIMIT 1", (ticket,))
            if existing:
                self._known_positions[ticket] = {
                    "group_id": gid, "magic": magic,
                    "direction": p.get("type", "SELL"),
                    "open_price": p.get("open_price"),
                    "last_profit": p.get("profit", 0),
                    "current_price": p.get("current_price"),
                    "symbol": p.get("symbol"),
                    "sl": p.get("sl"), "tp": p.get("tp"),
                }
                continue
            direction = p.get("type", "SELL")  # FORGE writes "BUY"/"SELL"
            stage_from_comment = _parse_tp_stage_from_comment(p.get("comment"))
            self.scribe.log_trade_position(gid, {
                "ticket":      ticket,
                "magic":       magic,
                "direction":   direction,
                "lot_size":    p.get("lots"),
                "entry_price": p.get("open_price"),
                "sl":          p.get("sl"),
                "tp":          p.get("tp"),
                "tp_stage":    stage_from_comment,
            }, mode)
            # Increment fill counter for this group (for fill-rate analytics)
            try:
                self.scribe.increment_group_fills(int(gid), 1)
            except Exception as _e:
                log.debug("TRACKER: increment_group_fills tolerated: %s", _e)
            self._known_positions[ticket] = {
                "group_id": gid, "magic": magic, "direction": direction,
                "open_price": p.get("open_price"), "last_profit": p.get("profit", 0),
                "current_price": p.get("current_price"),
                "symbol": p.get("symbol"),
                "lot_size": p.get("lots", 0),
                "sl": p.get("sl"), "tp": p.get("tp"),
            }
            _tlog("TRACKER", "FILL", f"{direction} {p.get('lots',0):.2f}lot @ {p.get('open_price')} SL={p.get('sl')} TP={p.get('tp')}",
                  group_id=gid, ticket=ticket)

        # ── New unmanaged/manual positions (log into SCRIBE) ──────
        for ticket, p in live_unmanaged_positions.items():
            if ticket in self._known_unmanaged_positions:
                snap = self._known_unmanaged_positions[ticket]
                snap["last_profit"] = p.get("profit", 0)
                snap["current_price"] = p.get("current_price")
                snap["sl"] = p.get("sl")
                snap["tp"] = p.get("tp")
                gid = snap.get("group_id")
                magic = int(p.get("magic", 0) or 0)
                if gid is None:
                    existing = self.scribe.query(
                        "SELECT trade_group_id FROM trade_positions WHERE ticket=? LIMIT 1",
                        (ticket,),
                    )
                    if existing:
                        gid = existing[0].get("trade_group_id")
                    else:
                        direction = p.get("type", "SELL")
                        entry_price = p.get("open_price")
                        lot_size = p.get("lots", 0)
                        group_data = {
                            "source": "MANUAL_MT5",
                            "direction": direction,
                            "entry_low": entry_price,
                            "entry_high": entry_price,
                            "sl": p.get("sl"),
                            "tp1": p.get("tp"),
                            "tp2": None,
                            "tp3": None,
                            "num_trades": 1,
                            "lot_per_trade": lot_size,
                            "risk_pct": 0,
                            "account_balance": (mt5.get("account") or {}).get("balance"),
                            "lens_rating": None,
                            "lens_rsi": None,
                            "lens_confirmed": 0,
                        }
                        gid = self.scribe.log_trade_group(group_data, mode)
                        self.scribe.update_trade_group_magic(gid, magic)
                        self.scribe.log_trade_position(gid, {
                            "ticket": ticket,
                            "magic": magic,
                            "direction": direction,
                            "lot_size": lot_size,
                            "entry_price": entry_price,
                            "sl": p.get("sl"),
                            "tp": p.get("tp"),
                        }, mode)
                        self._bridge_activity(
                            "UNMANAGED_POSITION_OPEN",
                            reason="Tracked manual/non-FORGE MT5 position",
                            notes=json.dumps({
                                "ticket": ticket,
                                "group_id": gid,
                                "symbol": p.get("symbol"),
                                "direction": p.get("type"),
                                "lots": p.get("lots"),
                                "open_price": p.get("open_price"),
                                "sl": p.get("sl"),
                                "tp": p.get("tp"),
                                "magic": magic,
                            }, default=str),
                        )
                    snap["group_id"] = gid
                continue
            magic = int(p.get("magic", 0) or 0)
            existing = self.scribe.query(
                "SELECT trade_group_id FROM trade_positions WHERE ticket=? LIMIT 1",
                (ticket,),
            )
            gid = None
            if existing:
                gid = existing[0].get("trade_group_id")
            else:
                direction = p.get("type", "SELL")
                entry_price = p.get("open_price")
                lot_size = p.get("lots", 0)
                group_data = {
                    "source": "MANUAL_MT5",
                    "direction": direction,
                    "entry_low": entry_price,
                    "entry_high": entry_price,
                    "sl": p.get("sl"),
                    "tp1": p.get("tp"),
                    "tp2": None,
                    "tp3": None,
                    "num_trades": 1,
                    "lot_per_trade": lot_size,
                    "risk_pct": 0,
                    "account_balance": (mt5.get("account") or {}).get("balance"),
                    "lens_rating": None,
                    "lens_rsi": None,
                    "lens_confirmed": 0,
                }
                gid = self.scribe.log_trade_group(group_data, mode)
                self.scribe.update_trade_group_magic(gid, magic)
                self.scribe.log_trade_position(gid, {
                    "ticket": ticket,
                    "magic": magic,
                    "direction": direction,
                    "lot_size": lot_size,
                    "entry_price": entry_price,
                    "sl": p.get("sl"),
                    "tp": p.get("tp"),
                }, mode)
            self._known_unmanaged_positions[ticket] = {
                "group_id": gid,
                "magic": magic,
                "symbol": p.get("symbol"),
                "direction": p.get("type", "SELL"),
                "open_price": p.get("open_price"),
                "last_profit": p.get("profit", 0),
                "current_price": p.get("current_price"),
                "lot_size": p.get("lots", 0),
                "sl": p.get("sl"),
                "tp": p.get("tp"),
            }
            self._bridge_activity(
                "UNMANAGED_POSITION_OPEN",
                reason="Tracked manual/non-FORGE MT5 position",
                notes=json.dumps({
                    "ticket": ticket,
                    "group_id": gid,
                    "symbol": p.get("symbol"),
                    "direction": p.get("type"),
                    "lots": p.get("lots"),
                    "open_price": p.get("open_price"),
                    "sl": p.get("sl"),
                    "tp": p.get("tp"),
                    "magic": magic,
                }, default=str),
            )

        # ── New pending orders ─────────────────────────────────────
        for ticket, o in live_pendings.items():
            if ticket in self._known_pendings:
                continue
            magic = o.get("magic", 0)
            gid = self._resolve_group_for_magic(magic)
            if gid is None:
                continue
            self._known_pendings[ticket] = {
                "group_id": gid, "magic": magic,
                "order_type": o.get("order_type"),
                "price": o.get("price"),
                "tracked_since": time.time(),
            }

        # ── Auto-cancel stale pending orders ─────────────────────
        if PENDING_ORDER_TIMEOUT_SEC > 0:
            now_ts = time.time()
            stale_groups: set[int] = set()
            for ticket, snap in self._known_pendings.items():
                if ticket in live_pendings:
                    age = now_ts - snap.get("tracked_since", now_ts)
                    if age > PENDING_ORDER_TIMEOUT_SEC:
                        stale_groups.add(snap.get("group_id"))
            for gid in stale_groups:
                if gid is None:
                    continue
                group_source = None
                g_cached = self._open_groups.get(int(gid))
                if isinstance(g_cached, dict):
                    group_source = (g_cached.get("source") or "").upper()
                if not group_source:
                    try:
                        g_rows = self.scribe.query(
                            "SELECT source FROM trade_groups WHERE id=? LIMIT 1",
                            (int(gid),),
                        )
                        if g_rows:
                            group_source = str(g_rows[0].get("source") or "").upper()
                    except Exception:
                        group_source = ""
                # Signal-origin groups should remain active until explicit operator close.
                if group_source == "SIGNAL":
                    log.info(
                        "TRACKER: skipping pending timeout for SIGNAL group G%s",
                        gid,
                    )
                    continue
                magic = self._lookup_group_magic(gid)
                if magic:
                    log.warning("TRACKER: pending orders for G%s stale (>%ds) — auto-cancelling",
                                gid, PENDING_ORDER_TIMEOUT_SEC)
                    _write_forge_command({
                        "action": "CANCEL_GROUP_PENDING",
                        "magic": magic,
                        "timestamp": _now(),
                    })
                    has_open_positions = any(
                        int(p.get("magic", 0) or 0) == int(magic)
                        for p in live_positions.values()
                    ) or any(
                        int(s.get("magic", 0) or 0) == int(magic)
                        for s in self._known_positions.values()
                    )
                    if not has_open_positions:
                        self.scribe.update_trade_group(gid, "CLOSED", close_reason="PENDING_EXPIRED")
                    self.herald.send(
                        f"⏰ <b>PENDING EXPIRED</b> — G{gid}\n"
                        f"FULFILLED_PENDING orders cancelled after {PENDING_ORDER_TIMEOUT_SEC}s")
                    self._bridge_activity(
                        "PENDING_EXPIRED",
                        reason=f"G{gid} timeout {PENDING_ORDER_TIMEOUT_SEC}s",
                        notes=json.dumps(
                            {
                                "group_id": gid,
                                "magic": magic,
                                "cancelled_pending_only": True,
                                "has_open_positions": has_open_positions,
                            },
                            default=str,
                        ),
                    )

        # ── Disappeared positions → closed (SL/TP/manual) ─────────
        closed_tickets = set(self._known_positions) - set(live_positions)
        groups_touched: dict[int, list] = {}  # gid → [pnl, ...]
        for ticket in closed_tickets:
            snap = self._known_positions.pop(ticket)
            try:
                self._profit_ratcheted.discard(int(ticket))
            except AttributeError:
                pass  # tolerated for stubs without the bookkeeping set
            gid = snap["group_id"]
            pnl = snap.get("last_profit", 0)
            close_price = snap.get("current_price") or 0
            deal_row = recent_closed_deals.get(int(ticket))
            if deal_row:
                broker_price = _safe_float(deal_row.get("close_price"))
                if broker_price is not None and broker_price > 0:
                    close_price = broker_price
                broker_pnl = _safe_float(deal_row.get("profit"))
                if broker_pnl is not None:
                    pnl = broker_pnl
            open_price = snap.get("open_price") or 0
            direction = snap.get("direction", "?")
            symbol = snap.get("symbol")
            sl = snap.get("sl") or 0
            tp = snap.get("tp") or 0
            lot_size = snap.get("lot_size", 0)
            pips = _calc_pips(symbol, direction, open_price, close_price)

            # ── Infer close reason from SL/TP proximity ────────────
            close_reason = None
            close_time = None
            if deal_row:
                close_time = _deal_close_time_iso(deal_row)
                close_reason = _close_reason_from_broker_hint(
                    str(deal_row.get("close_reason") or deal_row.get("reason") or ""),
                    close_price,
                    gid,
                    self._match_tp_stage,
                )
            if not close_reason:
                close_reason = self._infer_close_reason(
                    close_price, sl, tp, direction, gid)

            # Determine TP stage for SCRIBE trade_positions
            tp_stage = None
            if close_reason == "TP1_HIT":
                tp_stage = 1
            elif close_reason == "TP2_HIT":
                tp_stage = 2
            elif close_reason == "TP3_HIT":
                tp_stage = 3

            self.scribe.close_trade_position(
                ticket=ticket,
                close_price=close_price,
                close_reason=close_reason,
                pnl=pnl,
                pips=pips,
                tp_stage=tp_stage,
                close_time=close_time,
            )

            # Log to trade_closures table
            self.scribe.log_trade_closure(
                ticket=ticket,
                trade_group_id=gid,
                direction=direction,
                lot_size=lot_size,
                entry_price=open_price,
                close_price=close_price,
                sl=sl, tp=tp,
                close_reason=close_reason,
                pnl=pnl, pips=pips,
                session=_session(),
                mode=mode,
            )

            groups_touched.setdefault(gid, []).append(pnl)
            _tlog("TRACKER", "CLOSE", f"reason={close_reason} pnl=${pnl:+.2f} pips={pips:+.1f} close@{close_price} entry@{open_price} SL={sl} TP={tp}",
                  group_id=gid, ticket=ticket)
            if pnl < 0:
                self._last_loss_close_ts = time.time()

            # Herald notification per position
            if close_reason == "SL_HIT":
                self.herald.position_closed(ticket, direction, pnl, pips)
            elif close_reason.startswith("TP"):
                remaining = sum(
                    1 for s in self._known_positions.values()
                    if s.get("group_id") == gid
                )
                self.herald.tp_hit(
                    str(gid), tp_stage or 1,
                    closed_n=1, remaining_n=remaining,
                    pips=pips, pnl=pnl,
                    be_moved=False,
                )

        # ── Disappeared unmanaged/manual positions → closed ───────
        unmanaged_closed_tickets = (
            set(self._known_unmanaged_positions) - set(live_unmanaged_positions)
        )
        for ticket in unmanaged_closed_tickets:
            snap = self._known_unmanaged_positions.pop(ticket)
            gid = snap.get("group_id")
            if gid is None:
                direction_seed = snap.get("direction", "SELL")
                entry_seed = snap.get("open_price")
                lot_seed = snap.get("lot_size", 0)
                group_data = {
                    "source": "MANUAL_MT5",
                    "direction": direction_seed,
                    "entry_low": entry_seed,
                    "entry_high": entry_seed,
                    "sl": snap.get("sl"),
                    "tp1": snap.get("tp"),
                    "tp2": None,
                    "tp3": None,
                    "num_trades": 1,
                    "lot_per_trade": lot_seed,
                    "risk_pct": 0,
                    "account_balance": (mt5.get("account") or {}).get("balance"),
                    "lens_rating": None,
                    "lens_rsi": None,
                    "lens_confirmed": 0,
                }
                gid = self.scribe.log_trade_group(group_data, mode)
                self.scribe.update_trade_group_magic(gid, int(snap.get("magic", 0) or 0))
                self.scribe.log_trade_position(gid, {
                    "ticket": ticket,
                    "magic": int(snap.get("magic", 0) or 0),
                    "direction": direction_seed,
                    "lot_size": lot_seed,
                    "entry_price": entry_seed,
                    "sl": snap.get("sl"),
                    "tp": snap.get("tp"),
                }, mode)
            pnl = snap.get("last_profit", 0)
            close_price = snap.get("current_price") or 0
            deal_row = recent_closed_deals.get(int(ticket))
            if deal_row:
                broker_price = _safe_float(deal_row.get("close_price"))
                if broker_price is not None and broker_price > 0:
                    close_price = broker_price
                broker_pnl = _safe_float(deal_row.get("profit"))
                if broker_pnl is not None:
                    pnl = broker_pnl
            open_price = snap.get("open_price") or 0
            direction = snap.get("direction", "?")
            symbol = snap.get("symbol")
            sl = snap.get("sl") or 0
            tp = snap.get("tp") or 0
            lot_size = snap.get("lot_size", 0)
            pips = _calc_pips(symbol, direction, open_price, close_price)
            close_time = _deal_close_time_iso(deal_row) if deal_row else None
            close_reason = _close_reason_from_broker_hint(
                str((deal_row or {}).get("close_reason") or (deal_row or {}).get("reason") or ""),
                close_price,
                gid,
                self._match_tp_stage,
            )
            if not close_reason:
                close_reason = self._infer_close_reason(
                    close_price, sl, tp, direction, gid
                )
            tp_stage = None
            if close_reason == "TP1_HIT":
                tp_stage = 1
            elif close_reason == "TP2_HIT":
                tp_stage = 2
            elif close_reason == "TP3_HIT":
                tp_stage = 3
            self.scribe.close_trade_position(
                ticket=ticket,
                close_price=close_price,
                close_reason=close_reason,
                pnl=pnl,
                pips=pips,
                tp_stage=tp_stage,
                close_time=close_time,
            )
            self.scribe.log_trade_closure(
                ticket=ticket,
                trade_group_id=gid or 0,
                direction=direction,
                lot_size=lot_size,
                entry_price=open_price,
                close_price=close_price,
                sl=sl,
                tp=tp,
                close_reason=close_reason,
                pnl=pnl,
                pips=pips,
                session=_session(),
                mode=mode,
            )
            if gid is not None:
                self.scribe.update_trade_group(
                    gid,
                    "CLOSED",
                    total_pnl=round(pnl, 2),
                    pips=round(pips, 1),
                    trades_closed=1,
                    close_reason=close_reason,
                )
            self._bridge_activity(
                "UNMANAGED_POSITION_CLOSED",
                reason="Tracked manual/non-FORGE MT5 position closed",
                notes=json.dumps({
                    "ticket": ticket,
                    "group_id": gid,
                    "symbol": snap.get("symbol"),
                    "direction": direction,
                    "lots": lot_size,
                    "open_price": open_price,
                    "close_price": close_price,
                    "pnl": pnl,
                    "pips": pips,
                    "close_reason": close_reason,
                    "magic": snap.get("magic", 0),
                }, default=str),
            )

        # ── Disappeared pendings → filled or cancelled ────────────
        gone_pendings = set(self._known_pendings) - set(live_pendings)
        for ticket in gone_pendings:
            snap = self._known_pendings.pop(ticket)
            # If a new position with the same magic appeared this tick,
            # the pending was likely filled (MT5 assigns a new ticket).
            # Otherwise it was cancelled.
            gid = snap["group_id"]
            magic = snap["magic"]
            filled = any(
                p.get("magic") == magic
                for t, p in live_positions.items()
                if t not in (self._known_positions)  # only truly new
            )
            if not filled:
                log.info("TRACKER: pending cancelled ticket=%s G%s", ticket, gid)

        # ── Update group totals when all exposure is gone ──────────
        for gid, pnls in groups_touched.items():
            # Check if this group still has any MT5 exposure
            group_magic = None
            for g in self._open_groups.values():
                if g.get("id") == gid or g.get("magic_number"):
                    gm = g.get("magic_number")
                    if gm and self._resolve_group_for_magic(gm) == gid:
                        group_magic = gm
                        break
            if group_magic is None:
                continue
            still_has_positions = any(
                s["magic"] == group_magic for s in self._known_positions.values()
            )
            still_has_pendings = any(
                s["magic"] == group_magic for s in self._known_pendings.values()
            )
            # Defensive: when positions drained but pendings linger (TP1_HIT
            # while ladder legs upstream never filled), proactively cancel them
            # so they don't sit idle until PENDING_ORDER_TIMEOUT_SEC. Reuses the
            # FORGE CANCEL_GROUP_PENDING action.
            if PENDING_CANCEL_ON_GROUP_CLOSE and not still_has_positions and still_has_pendings:
                try:
                    _write_forge_command({
                        "action": "CANCEL_GROUP_PENDING",
                        "magic":  int(group_magic),
                        "timestamp": _now(),
                    })
                    log.info(
                        "BRIDGE: pending cancelled G%s reason=GROUP_CLOSED magic=%s",
                        gid, group_magic,
                    )
                except Exception as _e:
                    log.debug("BRIDGE: cancel-on-close write failed: %s", _e)

            if not still_has_positions and not still_has_pendings:
                # All exposure gone — close the group with totals
                all_pos = self.scribe.query(
                    "SELECT pnl, pips FROM trade_positions "
                    "WHERE trade_group_id=? AND status='CLOSED'",
                    (gid,),
                )
                total_pnl = sum(r["pnl"] or 0 for r in all_pos)
                total_pips = sum(r["pips"] or 0 for r in all_pos)
                trades_closed = len(all_pos)
                self.scribe.update_trade_group(
                    gid, "CLOSED",
                    total_pnl=round(total_pnl, 2),
                    pips=round(total_pips, 1),
                    trades_closed=trades_closed,
                    close_reason="ALL_CLOSED",
                )
                _tlog("TRACKER", "GROUP_CLOSED", f"{trades_closed} trades pnl=${total_pnl:+.2f} pips={total_pips:+.1f}",
                      group_id=gid)
                self._bridge_activity(
                    "TRADE_GROUP_CLOSED",
                    reason="ALL_CLOSED",
                    notes=json.dumps({
                        "group_id": gid, "trades_closed": trades_closed,
                        "total_pnl": round(total_pnl, 2),
                        "total_pips": round(total_pips, 1),
                    }, default=str),
                )
                # Telegram alert for group close
                try:
                    g_info = self.scribe.query(
                        "SELECT direction FROM trade_groups WHERE id=?", (gid,))
                    direction = g_info[0]["direction"] if g_info else "?"
                    self.herald.trade_group_closed(
                        gid, direction, trades_closed,
                        round(total_pnl, 2), round(total_pips, 1), "ALL_CLOSED")
                except Exception as _he:
                    log.debug("TRACKER herald error: %s", _he)

        # ── Profit ratchet: lock SL once a leg is N pips green ──
        # Runs after fills/closes are reconciled so we only ratchet on legs
        # that are still live this tick. Opt-in via PROFIT_RATCHET_ENABLED.
        if PROFIT_RATCHET_ENABLED:
            self._apply_profit_ratchet(live_positions)

    def _enqueue_forge_command(
        self,
        cmd: dict,
        *,
        verifier: Optional[Callable[[dict], bool]] = None,
        description: str = "",
        on_drop: Optional[Callable[[], None]] = None,
        dedup_key: Optional[str] = None,
    ) -> Optional[_ForgeQueueItem]:
        """Submit a FORGE command through the serialised queue.

        Use this for any MODIFY_SL/MODIFY_TP/CLOSE_* path that may emit
        multiple commands in rapid succession — the queue ensures FORGE sees
        every one. For one-shot commands (OPEN_GROUP) `_write_forge_command`
        directly is still fine.
        """
        return self._forge_queue.enqueue(
            cmd,
            verifier=verifier,
            description=description,
            on_drop=on_drop,
            dedup_key=dedup_key,
        )

    @staticmethod
    def _build_ticket_sl_verifier(
        ticket: int, target_sl: float, direction: str
    ) -> Callable[[dict], bool]:
        """Verifier used for ticket-scoped MODIFY_SL emissions.

        Returns True once the next MT5 snapshot shows the live SL has moved
        past the target (BUY: ≥, SELL: ≤). If the position no longer appears
        in `open_positions`, the command is considered settled (the position
        already closed, e.g. SL/TP hit between writes).
        """
        t = int(ticket)
        d = (direction or "").upper()

        def _verify(mt5: dict) -> bool:
            for p in (mt5 or {}).get("open_positions") or []:
                try:
                    pt = int(p.get("ticket", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if pt != t:
                    continue
                try:
                    live_sl = float(p.get("sl") or 0)
                except (TypeError, ValueError):
                    return False
                if live_sl <= 0:
                    return False
                if d == "BUY":
                    return live_sl >= target_sl - 1e-6
                return live_sl <= target_sl + 1e-6
            # ticket no longer present in MT5 → consider acked (closed)
            return True

        return _verify

    @staticmethod
    def _build_ticket_tp_verifier(
        ticket: int, target_tp: float
    ) -> Callable[[dict], bool]:
        """Verifier used for ticket-scoped MODIFY_TP emissions."""
        t = int(ticket)

        def _verify(mt5: dict) -> bool:
            for p in (mt5 or {}).get("open_positions") or []:
                try:
                    pt = int(p.get("ticket", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if pt != t:
                    continue
                try:
                    live_tp = float(p.get("tp") or 0)
                except (TypeError, ValueError):
                    return False
                return abs(live_tp - target_tp) <= 1e-6
            return True

        return _verify

    def _apply_profit_ratchet(self, live_positions: dict[int, dict]) -> None:
        """For every FORGE-managed live position whose unrealised pip gain is
        ≥ PROFIT_RATCHET_TRIGGER_PIPS and whose current SL is still worse than
        ``entry ± PROFIT_RATCHET_LOCK_PIPS``, enqueue a per-ticket MODIFY_SL
        for FORGE so any retracement closes at a small profit instead of
        giving the move back.

        Idempotency:
          • ``_profit_ratcheted`` holds tickets we've already enqueued so we
            don't duplicate while a write is in-flight.
          • If the queue ultimately drops the command (FORGE never confirmed
            the move within retry budget), the on_drop callback removes the
            ticket from the set so a future eligible tick can re-attempt.
        """
        trigger = float(PROFIT_RATCHET_TRIGGER_PIPS)
        lock = float(PROFIT_RATCHET_LOCK_PIPS)
        if trigger <= 0:
            return
        for ticket, p in live_positions.items():
            if ticket in self._profit_ratcheted:
                continue
            direction = (p.get("type") or "").upper()
            if direction not in ("BUY", "SELL"):
                continue
            try:
                open_price = float(p.get("open_price") or 0)
                cur_price = float(p.get("current_price") or 0)
                live_sl = float(p.get("sl") or 0)
            except (TypeError, ValueError):
                continue
            if open_price <= 0 or cur_price <= 0:
                continue
            symbol = p.get("symbol")
            pip_size = _ratchet_pip_size(symbol)
            if pip_size <= 0:
                continue
            raw = cur_price - open_price
            if direction == "SELL":
                raw = -raw
            pips = round(raw / pip_size, 1)
            if pips < trigger:
                continue
            if direction == "BUY":
                target_sl = round(open_price + lock * pip_size, 5)
                already_locked = live_sl > 0 and live_sl >= target_sl - 1e-6
            else:
                target_sl = round(open_price - lock * pip_size, 5)
                already_locked = live_sl > 0 and live_sl <= target_sl + 1e-6
            if already_locked:
                # Stop already past the lock target (e.g. FORGE moved BE on TP1)
                # — nothing to do; mark to avoid re-checking each tick.
                self._profit_ratcheted.add(int(ticket))
                continue
            magic = int(p.get("magic") or 0)
            gid = self._known_positions.get(int(ticket), {}).get("group_id")
            forge_cmd = {
                "action": "MODIFY_SL",
                "sl": target_sl,
                "ticket": int(ticket),
            }
            if magic > 0:
                forge_cmd["magic"] = magic
            ticket_int = int(ticket)

            def _on_drop(t=ticket_int) -> None:
                # Release the dedup token so the next eligible tick can
                # retry the ratchet — better than silently giving up.
                self._profit_ratcheted.discard(t)
                log.warning(
                    "BRIDGE: profit-ratchet command for #%s dropped after retries; "
                    "will re-attempt next eligibility window", t,
                )

            verifier = self._build_ticket_sl_verifier(ticket_int, target_sl, direction)
            enqueued = self._enqueue_forge_command(
                forge_cmd,
                verifier=verifier,
                description=f"PROFIT_RATCHET ticket={ticket_int} sl={target_sl}",
                on_drop=_on_drop,
                dedup_key=f"ratchet:{ticket_int}",
            )
            if enqueued is None:
                # Already pending/in-flight from a prior tick — nothing to do.
                continue
            try:
                self._sync_modify_targets(
                    gid, sl=target_sl, tp=None, ticket=ticket_int, tp_stage=None,
                )
            except Exception as e:
                log.debug("BRIDGE: profit-ratchet SCRIBE sync tolerated: %s", e)
            self._profit_ratcheted.add(ticket_int)
            # NOTE: we deliberately do NOT pre-update self._known_positions[t]['sl']
            # to target_sl — the drift detector will pick up the actual live SL
            # once FORGE applies the modify, and will skip its "learn-back" branch
            # while the queue still has this MODIFY in flight (see _sync_positions).

            # Hybrid TP tightening: enqueue a per-ticket MODIFY_TP that pulls
            # this leg's TP toward current_price + buffer. Per-ticket scope
            # means only the triggered leg is tightened — sibling legs keep
            # their original TP1/TP2/TP3 targets and continue running. If the
            # tightened TP would not actually tighten (i.e. it's already past
            # current price + buffer), we skip the TP enqueue.
            target_tp = self._compute_ratchet_tp(direction, cur_price, pip_size, p)
            if target_tp is not None:
                tp_cmd = {
                    "action": "MODIFY_TP",
                    "tp": target_tp,
                    "ticket": ticket_int,
                }
                if magic > 0:
                    tp_cmd["magic"] = magic
                tp_verifier = self._build_ticket_tp_verifier(ticket_int, target_tp)
                self._enqueue_forge_command(
                    tp_cmd,
                    verifier=tp_verifier,
                    description=(
                        f"PROFIT_RATCHET_TP ticket={ticket_int} tp={target_tp}"
                    ),
                    dedup_key=f"ratchet_tp:{ticket_int}",
                )
                try:
                    self._sync_modify_targets(
                        gid, sl=None, tp=target_tp,
                        ticket=ticket_int, tp_stage=None,
                    )
                except Exception as e:
                    log.debug("BRIDGE: profit-ratchet TP SCRIBE sync tolerated: %s", e)

            tp_note = (
                f" + TP tightened to {target_tp}"
                if target_tp is not None else ""
            )
            _tlog(
                "TRACKER", "PROFIT_RATCHET",
                f"{direction} {pips:+.1f}pips → SL locked at {target_sl}"
                f"{tp_note} (entry {open_price})",
                group_id=gid, ticket=ticket,
            )
            self._bridge_activity(
                "PROFIT_RATCHET",
                reason=f"{pips:+.1f}p ≥ {trigger:.1f}p trigger",
                notes=json.dumps({
                    "ticket": ticket_int, "group_id": gid,
                    "open_price": open_price, "new_sl": target_sl,
                    "new_tp": target_tp,
                    "trigger_pips": trigger, "lock_pips": lock,
                    "tp_buffer_pips": float(PROFIT_RATCHET_TP_BUFFER_PIPS),
                }, default=str),
            )
            try:
                tp_msg = (
                    f"\nTP tightened to <code>{target_tp}</code>"
                    if target_tp is not None else ""
                )
                self.herald.send(
                    f"🛡️ <b>PROFIT LOCKED</b> — G{gid} #{ticket}\n"
                    f"{direction} +{pips:.1f}p → SL moved to <code>{target_sl}</code> "
                    f"({lock:+.1f}p from entry)"
                    f"{tp_msg}"
                )
            except Exception as _he:
                log.debug("TRACKER profit-ratchet herald error: %s", _he)

    @staticmethod
    def _compute_ratchet_tp(
        direction: str,
        cur_price: float,
        pip_size: float,
        position_view: dict,
    ) -> Optional[float]:
        """Compute the tightened TP for the hybrid ratchet, or None to skip.

        Skips the tighten when:
          • ``PROFIT_RATCHET_TP_BUFFER_PIPS`` is 0 (feature disabled);
          • The position has no resting TP today (target would be a regression);
          • The proposed TP would NOT actually tighten the existing TP
            (BUY: target_tp ≥ live_tp; SELL: target_tp ≤ live_tp).
        """
        buffer_pips = float(PROFIT_RATCHET_TP_BUFFER_PIPS)
        if buffer_pips <= 0 or pip_size <= 0:
            return None
        try:
            live_tp = float(position_view.get("tp") or 0)
        except (TypeError, ValueError):
            live_tp = 0.0
        if live_tp <= 0:
            # Position has no resting TP — don't introduce one here; the SL
            # ratchet is already protecting the downside.
            return None
        offset = buffer_pips * pip_size
        if direction == "BUY":
            target_tp = round(cur_price + offset, 5)
            # Tighten only if it pulls the TP CLOSER (lower for BUY).
            if target_tp >= live_tp - 1e-6:
                return None
        else:
            target_tp = round(cur_price - offset, 5)
            if target_tp <= live_tp + 1e-6:
                return None
        return target_tp

    def _sync_open_groups_from_scribe(self):
        """Reload BRIDGE's open-group map from SCRIBE so ATHENA/reconciler stay aligned."""
        self._open_groups = {}
        try:
            for g in self.scribe.get_open_groups():
                gid = g.get("id")
                if gid is not None:
                    self._open_groups[int(gid)] = dict(g)
        except Exception as e:
            log.warning("BRIDGE: sync open groups from SCRIBE failed: %s", e)

    def _next_group_magic(self) -> int:
        """Allocate the next available magic number for a new trade group.

        Picks the lowest unused offset in [1, FORGE_MAGIC_MAX] so that
        magic = FORGE_MAGIC_BASE + offset.  Avoids collisions with any
        OPEN/PARTIAL group already recorded in SCRIBE.
        """
        in_use = self.scribe.get_in_use_magics()
        for offset in range(1, FORGE_MAGIC_MAX + 1):
            candidate = FORGE_MAGIC_BASE + offset
            if candidate not in in_use:
                return candidate
        raise RuntimeError("BRIDGE: magic number pool exhausted (9999 open groups)")

    def _refresh_regime_snapshot(self, mt5: dict):
        try:
            lens_snapshot = _read_json(LENS_SNAPSHOT_FILE)
            snap = self.regime_engine.infer(
                mt5 or {},
                session=self._current_session,
                mode=self._effective_mode(),
                lens=lens_snapshot if isinstance(lens_snapshot, dict) else None,
            )
            if not snap:
                return
            self._regime_snapshot = dict(snap)
            if snap.get("emit_snapshot"):
                self.scribe.log_market_regime(
                    self._regime_snapshot,
                    mode=self._effective_mode(),
                    session=self._current_session,
                )
        except Exception as e:
            log.warning("BRIDGE: regime inference failed: %s", e)

    def _regime_context_for_trade(self, direction: str) -> dict:
        snap = dict(self._regime_snapshot or {})
        if not snap:
            snap = {"entry_mode": "off", "apply_entry_policy": False, "label": "UNKNOWN"}
        return {
            "label": snap.get("label"),
            "confidence": snap.get("confidence"),
            "posterior": snap.get("posterior"),
            "model_name": snap.get("model_name"),
            "entry_mode": snap.get("entry_mode", "off"),
            "apply_entry_policy": bool(snap.get("apply_entry_policy")),
            "fallback_reason": snap.get("fallback_reason"),
            "entry_gate_reason": snap.get("entry_gate_reason"),
            "stale": snap.get("stale"),
            "age_sec": snap.get("age_sec"),
            "direction": (direction or "").upper(),
        }

    def _bridge_activity(
        self,
        event_type: str,
        *,
        reason=None,
        notes=None,
        news_event=None,
        new_mode=None,
    ):
        """Record SCRIBE system_events (+ on-disk audit JSONL) for BRIDGE audit trail."""
        try:
            self.scribe.log_system_event(
                event_type,
                new_mode=new_mode,
                triggered_by="BRIDGE",
                reason=reason,
                news_event=news_event,
                session=self._current_session,
                notes=notes,
            )
        except Exception as e:
            log.debug("BRIDGE activity log failed: %s", e)

    # ── Main loop ─────────────────────────────────────────────────
    def run(self):
        # Load broker info
        broker_info = _read_json(BROKER_INFO_FILE)
        if broker_info:
            self._broker_info = broker_info

        # Mode priority: RESTORE_MODE (status.json) > FORGE requested_mode > DEFAULT_MODE
        if not RESTORE_MODE_ON_RESTART:
            requested = broker_info.get("requested_mode","").upper() if broker_info else ""
            if requested in VALID_MODES:
                self._mode = requested
                log.info(f"BRIDGE: using FORGE requested_mode '{requested}'")
        else:
            log.info(f"BRIDGE: restored mode '{self._mode}' from previous session")

        pinned = self._pinned_mode()
        if BRIDGE_PIN_MODE and not pinned:
            log.warning("BRIDGE_PIN_MODE='%s' invalid; expected one of %s", BRIDGE_PIN_MODE, VALID_MODES)
        if pinned and self._mode != pinned:
            log.warning("BRIDGE: mode pin active — forcing mode %s (was %s)", pinned, self._mode)
            self._mode = pinned

        restored = "(restored)" if RESTORE_MODE_ON_RESTART else "(default)"
        pin_note = f" pin={pinned}" if pinned else ""
        log.info(f"BRIDGE v{VERSION} starting — mode={self._mode} {restored}{pin_note} "
                 f"account={self._broker_info.get('account_type','?')} "
                 f"broker={self._broker_info.get('broker','?')}")
        _cmd_a = os.path.abspath(CMD_FILE_MT5)
        _cfg_a = os.path.abspath(CFG_FILE_MT5)
        _mkt_a = os.path.abspath(MARKET_FILE)
        log.info(
            "BRIDGE MT5 file paths (FORGE EA must use the SAME folder — symlink repo MT5/ → "
            "Terminal → Common → Files, or set MT5_*_FILE to absolute Common/Files paths):\n"
            "  command.json  → %s\n"
            "  config.json   → %s\n"
            "  market_data   → %s",
            _cmd_a,
            _cfg_a,
            _mkt_a,
        )
        if CMD_FILE_MT5_MIRROR:
            log.info(
                "  command.json (mirror) → %s",
                os.path.abspath(
                    CMD_FILE_MT5_MIRROR
                    if os.path.isabs(CMD_FILE_MT5_MIRROR)
                    else _under_root(CMD_FILE_MT5_MIRROR)
                ),
            )
        _log_mt5_forge_integration_hint()

        # ── CRITICAL: Clear ALL stale command files on startup ────
        # These files persist on disk. On restart, dedup timestamps
        # (_last_mgmt_ts, _last_signal_id, _last_aurum_ts) reset to
        # None, so BRIDGE re-executes stale commands. A leftover
        # CLOSE_ALL would kill all open trades.
        # Clear everything NOW before the first tick.
        for cmd_path in _forge_command_targets():
            try:
                _write_json(cmd_path, {})
            except Exception:
                pass
        for stale_file in (AURUM_CMD_FILE, MGMT_FILE, SIGNAL_FILE):
            try:
                os.remove(stale_file)
            except OSError:
                pass
        log.info(
            "BRIDGE: cleared stale command files on startup "
            "(command.json, aurum_cmd, management_cmd, parsed_signal)")

        self.scribe.log_system_event("STARTUP", new_mode=self._mode,
                                      triggered_by="USER")
        self.herald.system_start(self._mode, VERSION, restored=RESTORE_MODE_ON_RESTART)
        self._write_config()
        self._write_status()

        while True:
            try:
                self._cycle += 1
                self._tick()
            except KeyboardInterrupt:
                log.info("BRIDGE stopping")
                self.scribe.log_system_event("SHUTDOWN", prev_mode=self._mode,
                                              triggered_by="USER")
                break
            except Exception as e:
                log.error(f"BRIDGE tick error: {e}", exc_info=True)
                self.herald.error("BRIDGE", str(e)[:200])
            time.sleep(LOOP_INTERVAL)

    def _tick(self):
        now = time.time()
        mt5 = {}
        mt5_read_error = None
        try:
            with open(MARKET_FILE, encoding="utf-8") as fh:
                parsed = json.load(fh)
            if isinstance(parsed, dict):
                mt5 = parsed
            else:
                mt5_read_error = "non_object_json"
        except Exception as exc:
            mt5_read_error = type(exc).__name__

        mt5_age = 9999.0
        mt5_fresh = False
        used_snapshot_fallback = False

        if mt5:
            mt5.update(_extract_forge_thresholds(mt5))
            ts_unix = _coerce_unix_ts(mt5.get("timestamp_unix"))
            if ts_unix is None:
                mt5_read_error = "invalid_timestamp_unix"
                self._mt5_read_fail_streak += 1
            else:
                mt5_age = max(0.0, now - ts_unix)
                mt5_fresh = mt5_age < MT5_STALE_SEC
                self._last_mt5_good_unix = ts_unix
                self._last_mt5_snapshot = dict(mt5)
                self._mt5_read_fail_streak = 0
        else:
            self._mt5_read_fail_streak += 1

        # Transient file-write/read races can briefly return invalid JSON.
        # Reuse the last-known-good snapshot for a short grace window.
        if (
            not mt5_fresh
            and mt5_read_error is not None
            and self._last_mt5_snapshot
            and self._last_mt5_good_unix > 0
        ):
            fallback_age = max(0.0, now - self._last_mt5_good_unix)
            if (
                self._mt5_read_fail_streak < MT5_READ_FAIL_STREAK
                and fallback_age < MT5_STALE_RELAXED_SEC
            ):
                mt5 = dict(self._last_mt5_snapshot)
                mt5_age = fallback_age
                mt5_fresh = True
                used_snapshot_fallback = True
            else:
                mt5_age = fallback_age

        # ── CIRCUIT BREAKER: MT5 staleness check ──────────────────
        # If market_data.json hasn't updated in MT5_STALE_SEC, FORGE
        # is disconnected. Force WATCH and alert — never trade blind.
        if not mt5_fresh and self._effective_mode() not in ("OFF", "WATCH"):
            if not self._mt5_blind_override:
                self._mt5_blind_override = True
                log.error(f"CIRCUIT BREAKER: MT5 data stale ({mt5_age:.0f}s) — forcing WATCH")
                self.scribe.log_system_event(
                    "CIRCUIT_BREAKER_ON",
                    prev_mode=self._mode, new_mode="WATCH",
                    triggered_by="BRIDGE",
                    reason=(
                        f"MT5 market_data.json stale: {mt5_age:.0f}s > {MT5_STALE_SEC}s"
                        + (
                            f" (read_error={mt5_read_error}, fail_streak={self._mt5_read_fail_streak}, "
                            f"relaxed={MT5_STALE_RELAXED_SEC}s)"
                            if mt5_read_error is not None
                            else ""
                        )
                    ),
                )
                # Throttle alerts — only fire once per 5 minutes
                if now - self._last_mt5_alert_ts > 300:
                    self.herald.error(
                        "CIRCUIT BREAKER",
                        f"MT5 data stale {mt5_age:.0f}s — trading suspended. "
                        f"Check FORGE EA on XAUUSD chart."
                    )
                    self._last_mt5_alert_ts = now
        elif used_snapshot_fallback and (self._cycle % 30 == 0):
            log.warning(
                "BRIDGE: transient MT5 market_data read error (%s); "
                "using last good snapshot age=%.1fs (fail_streak=%d, relaxed=%ss)",
                mt5_read_error,
                mt5_age,
                self._mt5_read_fail_streak,
                MT5_STALE_RELAXED_SEC,
            )
        elif mt5_fresh and self._mt5_blind_override:
            # MT5 recovered — lift circuit breaker
            self._mt5_blind_override = False
            log.info("CIRCUIT BREAKER: MT5 data fresh — circuit breaker lifted")
            self.scribe.log_system_event(
                "CIRCUIT_BREAKER_OFF",
                prev_mode="WATCH", new_mode=self._mode,
                triggered_by="BRIDGE",
                reason="MT5 market_data.json fresh again",
            )
            self.herald.send(
                f"✅ <b>CIRCUIT BREAKER LIFTED</b>\n"
                f"MT5 data restored — resuming {self._mode}"
            )

        # ── 0. POSITION TRACKER: sync MT5 → SCRIBE ──────────────
        if mt5_fresh:
            try:
                self._sync_positions(mt5)
            except Exception as e:
                log.error("BRIDGE: position tracker error: %s", e, exc_info=True)

        # ── 0b. FORGE command queue ────────────────────────────
        # Drain at most one queued FORGE write per tick. Pumping AFTER
        # _sync_positions ensures we have the freshest mt5 snapshot for the
        # in-flight verifier (e.g. ratchet checks live SL has moved). It
        # runs even when mt5 is stale so the ack timeout path still ticks.
        try:
            self._forge_queue.pump(mt5 if mt5_fresh else {})
        except Exception as e:
            log.error("BRIDGE: forge queue pump error: %s", e, exc_info=True)

        # ── 1. SENTINEL check ───────────────────────────────────
        # Auto-revert sentinel user override after timeout
        if self._sentinel_user_override and now > self._sentinel_override_until:
            log.info("BRIDGE: Sentinel user override EXPIRED — reverting to normal")
            self._sentinel_user_override = False
            self.scribe.log_system_event(
                "SENTINEL_OVERRIDE_EXPIRED", triggered_by="BRIDGE",
                reason=f"auto-reverted after {SENTINEL_OVERRIDE_DURATION}s")

        if now - self._last_sentinel_ts > SENTINEL_INTERVAL:
            sent_status = self.sentinel.check(self._effective_mode())
            self._last_sentinel_ts = now
            if self._sentinel_user_override:
                # User override active — ignore sentinel block
                self._sentinel_override = False
            elif sent_status["block_trading"] and not self._sentinel_override:
                self._sentinel_override = True
                is_ext = sent_status.get("extended_event", False)
                post_min = sent_status.get("post_guard_min", 5)
                tag = f" [EXTENDED — holds {post_min}min]" if is_ext else ""
                log.warning("BRIDGE: Sentinel override ACTIVE%s — %s",
                            tag, sent_status.get("event_name", "?"))
            elif not sent_status["block_trading"] and self._sentinel_override:
                self._sentinel_override = False
                log.info("BRIDGE: Sentinel override LIFTED")

        # ── 2. RECONCILER: hourly position check ─────────────────
        RECON_INTERVAL = int(os.environ.get("RECON_INTERVAL_SEC", "3600"))
        if now - self._last_recon_ts > RECON_INTERVAL:
            try:
                self.reconciler.run_once()
            except Exception as e:
                log.error(f"BRIDGE: reconciler error: {e}")
            self._last_recon_ts = now

        # ── 3. SESSION TRANSITION DETECTION ───────────────────────
        new_session = _session()
        if new_session != self._current_session:
            self._on_session_change(new_session, mt5)
        self._check_sydney_open_alert()

        # ── 4. BROKER INFO from FORGE ──────────────────────────────
        broker_info = _read_json(BROKER_INFO_FILE)
        if broker_info:
            self._broker_info = broker_info

        # ── 4b. Open groups from SCRIBE (source of truth vs in-memory dict) ─
        self._sync_open_groups_from_scribe()

        # ── 4c. Regime snapshot (HMM primary + fallback) ──────────
        self._refresh_regime_snapshot(mt5)

        # ── 5. AURUM command check ──────────────────────────────
        self._check_aurum_command(mt5)

        # ── 5c. FORGE native scalper entry detection ─────────────
        self._check_forge_scalper_entry(mt5 or {})

        # ── 5b. Management (ATHENA / Telegram LISTENER) — all modes incl. SCALPER/WATCH
        self._process_mgmt_command(mt5)

        # ── 6. Mode-specific logic ────────────────────────────────
        mode = self._effective_mode()

        if mode == "OFF":
            self._write_status(mt5)
            self._heartbeat_passive_components()
            return

        if mode == "WATCH":
            # Periodic LENS MCP refresh in WATCH so snapshot/AURUM stay current
            if now - self._last_lens_ts > LENS_WATCH_REFRESH_SEC or self._last_lens_ts == 0:
                try:
                    self.lens.fetch_fresh(mode, mt5)
                    self._last_lens_ts = now
                except Exception as e:
                    log.warning("BRIDGE WATCH: LENS refresh failed: %s", e)
            self._write_status(mt5)
            self._heartbeat_passive_components()
            return

        # ── 4. LENS refresh ───────────────────────────────────────
        lens_snap = None
        if now - self._last_lens_ts > LENS_INTERVAL or self._last_lens_ts == 0:
            lens_snap = self.lens.fetch_fresh(mode, mt5)
            self._last_lens_ts = now
        else:
            lens_snap = self.lens.get(mode, mt5)

        # ── 5. Signal mode — check for new Telegram signal ───────
        if mode in ("SIGNAL", "HYBRID"):
            self._process_signal(mt5, lens_snap)

        # ── 6. Scalper mode — LENS-driven own entry ───────────────
        if mode in ("SCALPER", "HYBRID") and lens_snap:
            self._scalper_logic(mt5, lens_snap)

        # ── 6b. AUTO_SCALPER — AURUM-driven autonomous scalping ───
        if mode == "AUTO_SCALPER":
            if now - self._last_auto_scalper_ts >= AUTO_SCALPER_POLL_INTERVAL:
                try:
                    self._auto_scalper_tick(mt5)
                except Exception as e:
                    log.error("BRIDGE: AUTO_SCALPER error: %s", e, exc_info=True)
                self._last_auto_scalper_ts = now

        # ── 6c. DRAWDOWN PROTECTION ───────────────────────────
        if mt5_fresh and mt5:
            self._check_drawdown(mt5, now)

        # ── 7. Update status ──────────────────────────────────────
        self._write_status(mt5, lens_snap)

    def _check_sydney_open_alert(self):
        if not SYDNEY_OPEN_ALERT_ENABLED:
            return
        info = sydney_open_alert_info()
        if not info.get("should_fire"):
            return
        key = info.get("alert_key")
        if key == self._last_sydney_open_alert_key:
            return
        self._last_sydney_open_alert_key = key
        self.scribe.log_system_event(
            "SYDNEY_OPEN_ALERT",
            triggered_by="BRIDGE",
            reason="daily_sydney_open",
            session=self._current_session,
            notes=json.dumps(
                {
                    "sydney_local_now": info.get("sydney_now"),
                    "sydney_open_utc": info.get("open_utc"),
                },
                default=str,
            ),
        )
        self.herald.send(
            "🦘 <b>SYDNEY OPEN</b>\n"
            "Liquidity transition active — watch for Asian-session sweep behavior on XAUUSD.\n"
            f"Sydney open (UTC): <code>{info.get('open_utc')}</code>"
        )

    def _on_session_change(self, new_session: str, mt5: dict):
        """Called whenever the trading session changes."""
        prev_session = self._current_session
        log.info(f"BRIDGE: Session transition {prev_session} → {new_session}")

        # Close previous session in SCRIBE
        if self._current_session_id is not None:
            balance = mt5.get("account",{}).get("balance") if mt5 else None
            self.scribe.close_trading_session(
                self._current_session_id, balance=balance)
            log.info(f"BRIDGE: Closed session #{self._current_session_id} ({prev_session})")

        # Open new session
        account_type = self._broker_info.get("account_type", "UNKNOWN")
        broker       = self._broker_info.get("broker", "FBS")
        balance      = mt5.get("account",{}).get("balance") if mt5 else None

        self._current_session_id = self.scribe.open_trading_session(
            session_name=new_session,
            mode=self._effective_mode(),
            account_type=account_type,
            broker=broker,
            balance=balance,
        )
        self._current_session = new_session

        # Log to system_events
        self.scribe.log_system_event(
            "SESSION_CHANGE",
            triggered_by="BRIDGE",
            session=new_session,
            notes=f"{prev_session} → {new_session}",
        )

        # Herald notification
        acct_tag = f" [{account_type}]" if account_type not in ("UNKNOWN","") else ""
        self.herald.send(
            f"🕐 <b>SESSION: {new_session}</b>{acct_tag}\n"
            f"Balance: ${balance:,.2f}" if balance else
            f"🕐 <b>SESSION: {new_session}</b>{acct_tag}"
        )

    # ── Signal processing ─────────────────────────────────────────
    def _process_signal(self, mt5: dict, lens_snap):
        signal = _read_json(SIGNAL_FILE)
        if not signal:
            return

        sig_id = (signal.get("signal_id"), signal.get("timestamp"))
        if sig_id == self._last_signal_id:
            return  # already processed
        self._last_signal_id = sig_id

        log.info(f"BRIDGE: New signal — {signal.get('direction')} "
                 f"@ {signal.get('entry_low')}–{signal.get('entry_high')}")

        # Check signal age — reject stale signals
        sig_ts = signal.get("timestamp", "")
        if sig_ts:
            try:
                from datetime import datetime, timezone
                sig_time = datetime.fromisoformat(sig_ts)
                if sig_time.tzinfo is None:
                    sig_time = sig_time.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - sig_time).total_seconds()
                if age > SIGNAL_EXPIRY_SEC:
                    log.warning("BRIDGE: Signal EXPIRED — %.0fs old > %ds limit", age, SIGNAL_EXPIRY_SEC)
                    self.scribe.update_signal_action(
                        signal.get("signal_id"), "EXPIRED",
                        f"stale:{age:.0f}s>{SIGNAL_EXPIRY_SEC}s")
                    return
            except Exception:
                pass

        # Inject SIGNAL mode lot size + num_trades so AEGIS uses them
        signal["lot_per_trade"] = SIGNAL_LOT_SIZE
        signal["num_trades"] = SIGNAL_NUM_TRADES
        signal["source"] = "SIGNAL"

        # AEGIS validation
        account = mt5.get("account", {}) if mt5 else {}
        account["open_groups_count"] = len(self._open_groups)
        current_price = mt5.get("price", {}).get("bid") if mt5 else None
        regime_context = self._regime_context_for_trade(signal.get("direction"))

        approval = self.aegis.validate(
            signal,
            account,
            current_price,
            mt5_data=mt5,
            regime_context=regime_context,
        )
        regime_meta = {**regime_context, **(approval.regime_metadata or {})}
        if signal.get("signal_id"):
            self.scribe.update_signal_regime(signal.get("signal_id"), regime_meta)

        if not approval.approved:
            aegis_reason = f"AEGIS_REJECTED:{approval.reject_reason}"
            log.warning(
                "BRIDGE: AEGIS_REJECTED — signal_id=%s direction=%s reason=%s",
                signal.get("signal_id"), signal.get("direction"), approval.reject_reason,
            )
            self._bridge_activity(
                "SIGNAL_REJECTED",
                reason=aegis_reason,
                notes=json.dumps(
                    {
                        "source": "SIGNAL",
                        "direction": signal.get("direction"),
                        "signal_id": signal.get("signal_id"),
                        "gate": "AEGIS",
                        "reason": approval.reject_reason,
                        "regime": {
                            "label": regime_meta.get("label"),
                            "confidence": regime_meta.get("confidence"),
                            "policy": regime_meta.get("policy_name"),
                            "entry_mode": regime_meta.get("entry_mode"),
                        },
                    },
                    default=str,
                ),
            )
            self.scribe.update_signal_action(
                signal.get("signal_id"), "SKIPPED", aegis_reason)
            self.herald.signal_skipped(
                signal.get("direction","?"),
                approval.reject_reason,
                f"{signal.get('entry_low')}–{signal.get('entry_high')}"
            )
            return

        # Also check LENS entry validation
        if lens_snap and lens_snap.price:
            entry_check = lens_snap.validate_entry(
                signal["direction"], signal["entry_low"], signal["entry_high"])
            if not entry_check["valid"]:
                log.warning(f"BRIDGE: Signal REJECTED by LENS — {entry_check['reason']}")
                self._bridge_activity(
                    "SIGNAL_REJECTED",
                    reason=entry_check["reason"],
                    notes=json.dumps(
                        {
                            "source": "SIGNAL",
                            "direction": signal.get("direction"),
                            "signal_id": signal.get("signal_id"),
                            "gate": "LENS",
                        },
                        default=str,
                    ),
                )
                self.scribe.update_signal_action(
                    signal.get("signal_id"), "SKIPPED", entry_check["reason"])
                return

        # Build trade group
        group_data = {
            **signal,
            "lot_per_trade":  approval.lot_per_trade,
            "num_trades":     approval.num_trades,
            "risk_pct":       approval.risk_pct,
            "account_balance":account.get("balance", 0),
            "lens_rating":    lens_snap.bb_rating if lens_snap else None,
            "lens_rsi":       lens_snap.rsi if lens_snap else None,
            "lens_confirmed": 1 if (lens_snap and not lens_snap.conflict_with_mt5(
                mt5.get("indicators_h1",{}).get("rsi_14",50) if mt5 else 50,
                current_price or 0)["conflict"]) else 0,
            "source": "SIGNAL",
            "regime_label": regime_meta.get("label"),
            "regime_confidence": regime_meta.get("confidence"),
            "regime_model": regime_meta.get("model_name"),
            "regime_entry_mode": regime_meta.get("entry_mode"),
            "regime_policy": regime_meta.get("policy_name"),
            "regime_fallback_reason": regime_meta.get("fallback_reason") or regime_meta.get("entry_gate_reason"),
        }

        group_id = self.scribe.log_trade_group(
            group_data, self._effective_mode())
        magic = FORGE_MAGIC_BASE + group_id
        # Store the magic FORGE will compute (MagicNumber + group_id)
        self.scribe.update_trade_group_magic(group_id, magic)
        # Apply placement overrides AFTER AEGIS approval
        ladder, entry_type_label, cluster_flag = _apply_signal_placement(
            signal["direction"], signal["entry_low"], signal["entry_high"],
            approval.entry_ladder, approval.num_trades,
            current_price=current_price,
        )
        # Persist entry-zone / placement metadata to SCRIBE for analytics.
        self.scribe.update_group_open_meta(
            group_id,
            entry_zone_pips=approval.entry_zone_pips or abs(signal["entry_high"] - signal["entry_low"]),
            entry_type=entry_type_label,
            entry_cluster=int(bool(cluster_flag)),
        )
        self._open_groups[group_id] = {**group_data, "magic_number": magic}
        self.scribe.update_signal_action(
            signal.get("signal_id"), "EXECUTED", group_id=group_id)

        # SIGNAL-source TP1 close-pct override (default 100% via existing contract)
        sig_tp1_pct = SIGNAL_TP1_CLOSE_PCT if SIGNAL_TP1_CLOSE_PCT is not None else 100.0

        # Write command for FORGE
        cmd = {
            "action":        "OPEN_GROUP",
            "group_id":      group_id,
            "direction":     signal["direction"],
            "entry_ladder":  ladder,
            "entry_legs":    _entry_legs_from_ladder(ladder),
            "lot_per_trade": approval.lot_per_trade,
            "sl":            signal["sl"],
            "tp1":           signal["tp1"],
            "tp2":           None,
            "tp3":           None,
            "tp1_close_pct": sig_tp1_pct,
            "tp2_close_pct": TP2_CLOSE_PCT,
            "move_be_on_tp1":MOVE_BE_ON_TP1,
            "entry_type":    entry_type_label,
            "timestamp":     _now(),
        }
        if entry_type_label == "market":
            log.info("BRIDGE: SIGNAL entry_type=market — placed %d market lots (zone collapsed)",
                     approval.num_trades)
        elif cluster_flag:
            log.info("BRIDGE: SIGNAL entry_zone_cluster=true — %d legs within %.1fpips of zone edge",
                     approval.num_trades, SIGNAL_ENTRY_CLUSTER_PIPS)
        cmd_paths = _write_forge_command(cmd)
        log.info("BRIDGE: wrote OPEN_GROUP command.json → %s", cmd_paths[0])
        if len(cmd_paths) > 1:
            log.info("BRIDGE: command.json mirror → %s", cmd_paths[1])
        self._bridge_activity(
            "TRADE_QUEUED",
            reason="OPEN_GROUP",
            notes=json.dumps(
                {
                    "source": "SIGNAL",
                    "group_id": group_id,
                    "direction": signal["direction"],
                    "num_trades": approval.num_trades,
                    "lot_per_trade": approval.lot_per_trade,
                    "signal_id": signal.get("signal_id"),
                    "regime": {
                        "label": regime_meta.get("label"),
                        "confidence": regime_meta.get("confidence"),
                        "model_name": regime_meta.get("model_name"),
                        "entry_mode": regime_meta.get("entry_mode"),
                        "policy": regime_meta.get("policy_name"),
                        "applied": regime_meta.get("applied"),
                    },
                    "command_path": cmd_paths[0],
                    "command_paths": cmd_paths,
                },
                default=str,
            ),
        )
        self.herald.trade_group_opened({**group_data, "id": group_id})
        _tlog("SIGNAL", "OPEN_GROUP", f"{signal['direction']} {approval.num_trades}x{approval.lot_per_trade}lot SL={signal['sl']} TP1={signal['tp1']}",
              group_id=group_id)

    def _resolve_channel_group(self, mgmt: dict) -> int | None:
        """Find the most recent SIGNAL-source open group from a channel.
        Channel management commands should only affect their own group."""
        channel = mgmt.get("channel") or ""
        sig_id = mgmt.get("signal_id")
        # If LISTENER provided a signal_id, find the group it created
        if sig_id:
            rows = self.scribe.query(
                "SELECT trade_group_id FROM signals_received WHERE id=? AND trade_group_id IS NOT NULL",
                (sig_id,))
            if rows and rows[0].get("trade_group_id"):
                return int(rows[0]["trade_group_id"])
        # Fallback: most recent OPEN/PARTIAL SIGNAL group from same channel only
        if channel:
            rows = self.scribe.query(
                """SELECT tg.id FROM trade_groups tg
                   JOIN signals_received sr ON sr.trade_group_id = tg.id
                   WHERE sr.channel_name = ?
                     AND tg.source = 'SIGNAL'
                     AND tg.status IN ('OPEN','PARTIAL')
                   ORDER BY tg.id DESC LIMIT 1""",
                (channel,),
            )
            if rows and rows[0].get("id"):
                return int(rows[0]["id"])
        return None

    def _resolve_channel_open_groups(self, channel: str) -> list[int]:
        """Return OPEN/PARTIAL SIGNAL groups for a specific channel only."""
        if not channel:
            return []
        rows = self.scribe.query(
            """SELECT DISTINCT tg.id FROM trade_groups tg
               JOIN signals_received sr ON sr.trade_group_id = tg.id
               WHERE sr.channel_name = ?
                 AND tg.source = 'SIGNAL'
                 AND tg.status IN ('OPEN','PARTIAL')
               ORDER BY tg.id DESC""",
            (channel,),
        )
        out = []
        for r in rows or []:
            gid = r.get("id")
            if gid is not None:
                out.append(int(gid))
        return out

    def _process_mgmt_command(self, mt5: dict):
        mgmt = _read_json(MGMT_FILE)
        if not mgmt:
            return

        ts = mgmt.get("timestamp")
        if ts == self._last_mgmt_ts:
            return
        self._last_mgmt_ts = ts

        intent = mgmt.get("intent")
        mgmt_source = mgmt.get("source", "?")  # ATHENA, LISTENER, etc.
        is_channel = mgmt_source not in ("ATHENA", "AURUM")  # Channel/LISTENER commands

        # If LISTENER provided a group_id, use it; otherwise resolve from channel
        mgmt_gid = mgmt.get("group_id")
        if not mgmt_gid and is_channel:
            mgmt_gid = self._resolve_channel_group(mgmt)

        _tlog("MGMT", intent, f"source={mgmt_source} channel={mgmt.get('channel','-')} group={mgmt_gid or 'all'}"
              + (" [SCOPED TO SIGNAL GROUP]" if mgmt_gid and is_channel else ""))

        cmd = None
        if intent == "CLOSE_ALL":
            if mgmt_gid:
                # Channel said "close all" but we scope it to their group
                magic = self._lookup_group_magic(int(mgmt_gid))
                if magic:
                    cmd = {"action": "CLOSE_GROUP", "magic": magic, "timestamp": _now()}
                    self.scribe.update_trade_group(int(mgmt_gid), "CLOSED", close_reason=f"CHANNEL_CLOSE ({mgmt.get('channel','')})")
                    _tlog("MGMT", "CLOSE_GROUP", f"scoped to G{mgmt_gid} (channel: {mgmt.get('channel','')})", group_id=mgmt_gid)
            elif mgmt_source == "ATHENA":
                # Dashboard CLOSE_ALL is intentional — close everything
                cmd = {"action": "CLOSE_ALL", "timestamp": _now()}
                for g in self.scribe.get_open_groups():
                    gid = g.get("id")
                    if gid is not None:
                        self.scribe.update_trade_group(
                            int(gid), "CLOSED_ALL", close_reason="MGMT_CLOSE_ALL"
                        )
                self._open_groups.clear()
            else:
                # Channel CLOSE_ALL without explicit group_id — scope by channel open groups only.
                ch = mgmt.get("channel", "")
                gids = self._resolve_channel_open_groups(ch)
                if not gids:
                    _tlog("MGMT", "CLOSE_ALL_IGNORED", f"channel {ch} — no scoped SIGNAL groups found", level="warning")
                    return
                _tlog("MGMT", "CLOSE_ALL_SIGNAL_ONLY", f"channel {ch} — closing scoped SIGNAL groups only", level="warning")
                for gid in gids:
                    magic = self._lookup_group_magic(int(gid))
                    if magic:
                        _write_forge_command({"action": "CLOSE_GROUP", "magic": magic, "timestamp": _now()})
                        self.scribe.update_trade_group(int(gid), "CLOSED", close_reason=f"CHANNEL_CLOSE_ALL ({ch})")
                        _tlog("MGMT", "CLOSE_GROUP", f"channel CLOSE_ALL scoped to SIGNAL group", group_id=gid)
                return  # Don't send global CLOSE_ALL

        elif intent == "MOVE_BE":
            if mgmt_gid:
                # Scope to specific group
                magic = self._lookup_group_magic(int(mgmt_gid))
                if magic:
                    # FORGE MOVE_BE_ALL affects all — but we can MODIFY_SL per group
                    # Get entry prices for this group and set SL to entry
                    positions = self.scribe.get_open_positions_by_group(int(mgmt_gid))
                    for pos in positions:
                        ep = pos.get("entry_price")
                        if ep and ep > 100:
                            cmd = {"action": "MODIFY_SL", "magic": magic, "sl": float(ep), "timestamp": _now()}
                            self._sync_group_targets(int(mgmt_gid), sl=float(ep))
                    _tlog("MGMT", "MOVE_BE", f"scoped to G{mgmt_gid}", group_id=mgmt_gid)
            elif mgmt_source == "ATHENA":
                cmd = {"action": "MOVE_BE_ALL", "timestamp": _now()}
            else:
                # Channel MOVE_BE — only affect this channel's SIGNAL groups.
                ch = mgmt.get("channel", "")
                gids = self._resolve_channel_open_groups(ch)
                if not gids:
                    _tlog("MGMT", "MOVE_BE_IGNORED", f"channel {ch} — no scoped SIGNAL groups found", level="warning")
                    return
                _tlog("MGMT", "MOVE_BE_SIGNAL_ONLY", f"channel {ch} — scoped SIGNAL groups only", level="warning")
                for gid in gids:
                    magic = self._lookup_group_magic(int(gid))
                    if magic:
                        positions = self.scribe.get_open_positions_by_group(int(gid))
                        for pos in positions:
                            ep = pos.get("entry_price")
                            if ep and ep > 100:
                                _write_forge_command(
                                    {
                                        "action": "MODIFY_SL",
                                        "magic": magic,
                                        "sl": float(ep),
                                        "timestamp": _now(),
                                    }
                                )
                                self._sync_group_targets(int(gid), sl=float(ep))
                        _tlog("MGMT", "MOVE_BE", f"channel scoped to SIGNAL group", group_id=gid)
                return  # Don't send global MOVE_BE_ALL

        elif intent == "CLOSE_PCT":
            pct = mgmt.get("pct", TP1_CLOSE_PCT)
            if mgmt_gid:
                magic = self._lookup_group_magic(int(mgmt_gid))
                if magic:
                    cmd = {"action": "CLOSE_GROUP_PCT", "magic": magic, "pct": float(pct), "timestamp": _now()}
            elif mgmt_source == "ATHENA":
                cmd = {"action": "CLOSE_PCT", "pct": pct, "timestamp": _now()}
            else:
                # Channel CLOSE_PCT — scope to this channel's SIGNAL groups only.
                ch = mgmt.get("channel", "")
                gids = self._resolve_channel_open_groups(ch)
                if not gids:
                    _tlog("MGMT", "CLOSE_PCT_IGNORED", f"channel {ch} — no scoped SIGNAL groups found", level="warning")
                    return
                for gid in gids:
                    magic = self._lookup_group_magic(int(gid))
                    if magic:
                        _write_forge_command({"action": "CLOSE_GROUP_PCT", "magic": magic, "pct": float(pct), "timestamp": _now()})
                return

        elif intent == "MODIFY_SL":
            sl = mgmt.get("sl")
            if sl:
                slv = float(sl)
                ticket, stage = _coerce_modify_scope(mgmt)
                if is_channel and not (mgmt_gid or ticket or stage):
                    _tlog(
                        "MGMT",
                        "MODIFY_SL_IGNORED",
                        f"channel {mgmt.get('channel','')} — no resolved scope found",
                        level="warning",
                    )
                    return
                forge_cmd = {"action": "MODIFY_SL", "sl": slv}
                if mgmt_gid:
                    magic = self._lookup_group_magic(int(mgmt_gid))
                    if magic:
                        forge_cmd["magic"] = magic
                if ticket is not None:
                    forge_cmd["ticket"] = ticket
                if stage is not None:
                    forge_cmd["tp_stage"] = stage
                if ticket is not None:
                    direction_hint = (
                        self._known_positions.get(int(ticket), {}).get("direction")
                        or "BUY"
                    )
                    verifier = self._build_ticket_sl_verifier(
                        int(ticket), slv, direction_hint,
                    )
                else:
                    verifier = None
                # Use the queue, not the legacy `cmd` fall-through, so we get
                # serialised writes + retries.
                self._enqueue_forge_command(
                    forge_cmd,
                    verifier=verifier,
                    description=(
                        f"MGMT MODIFY_SL sl={slv} group={mgmt_gid} "
                        f"ticket={ticket} stage={stage}"
                    ),
                )
                self._sync_modify_targets(
                    mgmt_gid, sl=slv, tp=None, ticket=ticket, tp_stage=stage,
                )
                self._bridge_activity(
                    "MGMT_COMMAND", reason="MODIFY_SL",
                    notes=json.dumps({"forge_action": "MODIFY_SL"}, default=str),
                )
                cmd = None

        elif intent == "MODIFY_TP":
            tp = mgmt.get("tp")
            if tp:
                tpv = float(tp)
                ticket, stage = _coerce_modify_scope(mgmt)
                if is_channel and not (mgmt_gid or ticket or stage):
                    _tlog(
                        "MGMT",
                        "MODIFY_TP_IGNORED",
                        f"channel {mgmt.get('channel','')} — no resolved scope found",
                        level="warning",
                    )
                    return
                forge_cmd = {"action": "MODIFY_TP", "tp": tpv}
                if mgmt_gid:
                    magic = self._lookup_group_magic(int(mgmt_gid))
                    if magic:
                        forge_cmd["magic"] = magic
                if ticket is not None:
                    forge_cmd["ticket"] = ticket
                if stage is not None:
                    forge_cmd["tp_stage"] = stage
                verifier = (
                    self._build_ticket_tp_verifier(int(ticket), tpv)
                    if ticket is not None
                    else None
                )
                self._enqueue_forge_command(
                    forge_cmd,
                    verifier=verifier,
                    description=(
                        f"MGMT MODIFY_TP tp={tpv} group={mgmt_gid} "
                        f"ticket={ticket} stage={stage}"
                    ),
                )
                self._sync_modify_targets(
                    mgmt_gid, sl=None, tp=tpv, ticket=ticket, tp_stage=stage,
                )
                self._bridge_activity(
                    "MGMT_COMMAND", reason="MODIFY_TP",
                    notes=json.dumps({"forge_action": "MODIFY_TP"}, default=str),
                )
                cmd = None

        elif intent == "CLOSE_GROUP":
            gid = mgmt.get("group_id")
            if gid:
                magic = self._lookup_group_magic(int(gid))
                if magic:
                    cmd = {"action": "CLOSE_GROUP", "magic": magic, "timestamp": _now()}
                    g_info = self.scribe.query("SELECT direction FROM trade_groups WHERE id=?", (int(gid),))
                    self.scribe.update_trade_group(int(gid), "CLOSED", close_reason="CLOSE_GROUP")
                    self.herald.trade_group_closed(
                        int(gid), g_info[0]["direction"] if g_info else "?",
                        0, 0, 0, "CLOSE_GROUP (manual)")

        elif intent == "CLOSE_GROUP_PCT":
            gid = mgmt.get("group_id")
            pct = mgmt.get("pct", 70)
            if gid:
                magic = self._lookup_group_magic(int(gid))
                if magic:
                    cmd = {"action": "CLOSE_GROUP_PCT", "magic": magic, "pct": float(pct), "timestamp": _now()}

        elif intent == "CLOSE_PROFITABLE":
            cmd = {"action": "CLOSE_PROFITABLE", "timestamp": _now()}

        elif intent == "CLOSE_LOSING":
            cmd = {"action": "CLOSE_LOSING", "timestamp": _now()}

        if cmd:
            _write_forge_command(cmd)
            self._bridge_activity(
                "MGMT_COMMAND",
                reason=intent,
                notes=json.dumps({"forge_action": cmd.get("action")}, default=str),
            )

    # ── Scalper logic ─────────────────────────────────────────────
    def _scalper_logic(self, mt5: dict, lens_snap):
        """
        LENS-driven autonomous scalping.
        Only enters if strong signal + SENTINEL clear + no conflicting open groups.
        Extend this with your own strategy logic.
        """
        if len(self._open_groups) >= 2:
            return  # Don't over-stack in scalper mode

        rsi  = lens_snap.rsi
        macd = lens_snap.macd_hist
        adx  = lens_snap.adx
        bb   = lens_snap.bb_rating
        price = lens_snap.price

        if not (adx > 20 and price > 0):
            return  # No clear trend

        direction = None
        if rsi < 40 and macd > 0 and bb >= 1:
            direction = "BUY"
        elif rsi > 60 and macd < 0 and bb <= -1:
            direction = "SELL"

        if not direction:
            return

        # Build scalper signal
        atr_est = 3.0  # rough ATR in pips for scalping
        if direction == "BUY":
            entry = price
            sl    = round(price - atr_est * 3, 2)
            tp1   = round(price + atr_est * 2, 2)
        else:
            entry = price
            sl    = round(price + atr_est * 3, 2)
            tp1   = round(price - atr_est * 2, 2)

        signal = {
            "direction":  direction,
            "entry_low":  round(entry - 0.5, 2),
            "entry_high": round(entry + 0.5, 2),
            "sl": sl, "tp1": tp1, "tp2": None,
            "signal_id": None,
            "source": "SCALPER_SUBPATH_DIRECT",
        }
        _tlog("SCALPER", "SETUP", f"{direction} @ {entry:.2f} SL={sl} TP1={tp1}")
        account = mt5.get("account", {}) if mt5 else {}
        account["open_groups_count"] = len(self._open_groups)
        entry_ladder = _build_entry_ladder(signal["entry_low"], signal["entry_high"], SCALPER_NUM_TRADES)
        group_data = {**signal, "lot_per_trade": SCALPER_LOT_SIZE,
                      "num_trades": SCALPER_NUM_TRADES,
                      "risk_pct": None,
                      "account_balance": account.get("balance",0),
                      "source": "SCALPER_SUBPATH_DIRECT"}
        gid = self.scribe.log_trade_group(group_data, self._effective_mode())
        magic = FORGE_MAGIC_BASE + gid
        self.scribe.update_trade_group_magic(gid, magic)
        self._open_groups[gid] = {**group_data, "magic_number": magic}
        cmd = {"action":"OPEN_GROUP","group_id":gid,"direction":direction,
               "entry_ladder":entry_ladder,
               "entry_legs":_entry_legs_from_ladder(entry_ladder),
               "lot_per_trade":SCALPER_LOT_SIZE,
               "sl":sl,"tp1":tp1,"tp2":None,"tp3":None,
               "tp1_close_pct":TP1_CLOSE_PCT,
               "move_be_on_tp1":MOVE_BE_ON_TP1,
               "timestamp":_now()}
        _write_forge_command(cmd)
        self._bridge_activity(
            "TRADE_QUEUED",
            reason="OPEN_GROUP_SCALPER_SUBPATH_DIRECT",
            notes=json.dumps(
                {
                    "source": "SCALPER_SUBPATH_DIRECT",
                    "gate": "DIRECT_NO_AEGIS",
                    "group_id": gid,
                    "direction": direction,
                    "num_trades": SCALPER_NUM_TRADES,
                    "lot_per_trade": SCALPER_LOT_SIZE,
                },
                default=str,
            ),
        )

    # ── DRAWDOWN PROTECTION ─────────────────────────────────
    def _check_drawdown(self, mt5: dict, now: float) -> None:
        """Equity drawdown circuit breaker. Runs every tick when mt5 is fresh."""
        acc = mt5.get("account", {})
        equity = acc.get("equity", 0)
        balance = acc.get("balance", 0)
        floating = acc.get("total_floating_pnl", 0)

        if equity <= 0 or balance <= 0:
            return

        # Track session peak equity
        if equity > self._session_peak_equity:
            self._session_peak_equity = equity
            self._dd_close_all_fired = False  # reset if we make new high

        # Equity DD check: if equity drops X% from peak, CLOSE ALL + WATCH
        if self._session_peak_equity > 0 and not self._dd_close_all_fired:
            dd_pct = (self._session_peak_equity - equity) / self._session_peak_equity * 100
            if dd_pct >= DD_EQUITY_CLOSE_ALL_PCT:
                log.error(
                    "DD BREAKER: equity $%.2f dropped %.1f%% from peak $%.2f — CLOSE ALL + WATCH",
                    equity, dd_pct, self._session_peak_equity,
                )
                self._dd_close_all_fired = True
                # Close all positions
                _write_forge_command({"action": "CLOSE_ALL", "timestamp": _now()})
                for g in self.scribe.get_open_groups():
                    gid = g.get("id")
                    if gid is not None:
                        self.scribe.update_trade_group(
                            int(gid), "CLOSED_ALL", close_reason="DD_BREAKER"
                        )
                self._open_groups.clear()
                # Force WATCH
                self._change_mode("WATCH", "DD_BREAKER")
                self.scribe.log_system_event(
                    "DD_BREAKER_CLOSE_ALL",
                    triggered_by="BRIDGE",
                    reason=f"Equity DD {dd_pct:.1f}% (peak ${self._session_peak_equity:.2f} → ${equity:.2f})",
                )
                self.herald.send(
                    f"🚨 <b>DRAWDOWN BREAKER</b>\n"
                    f"Equity dropped {dd_pct:.1f}% from peak ${self._session_peak_equity:,.2f}\n"
                    f"All positions CLOSED. Mode → WATCH.\n"
                    f"Current equity: ${equity:,.2f}"
                )

    def _lookup_group_magic(self, group_id: int) -> int | None:
        """Get magic_number for a group from SCRIBE."""
        rows = self.scribe.query(
            "SELECT magic_number FROM trade_groups WHERE id=?", (group_id,))
        if rows and rows[0].get("magic_number"):
            return int(rows[0]["magic_number"])
        return FORGE_MAGIC_BASE + group_id  # fallback

    def _sync_group_targets(self, group_id: int | None, sl: float = None, tp: float = None):
        """Persist group-level target edits so ATHENA reflects live modified SL/TP."""
        if group_id is None:
            return
        try:
            gid = int(group_id)
        except (TypeError, ValueError):
            return
        try:
            self.scribe.update_group_sl_tp(gid, sl=sl, tp=tp)
        except Exception as e:
            log.debug("BRIDGE: update_group_sl_tp failed for G%s: %s", gid, e)
        g = self._open_groups.get(gid)
        if isinstance(g, dict):
            if sl is not None:
                g["sl"] = sl
            if tp is not None:
                g["tp1"] = tp
                if g.get("tp2") not in (None, 0, 0.0, ""):
                    g["tp2"] = tp
                if g.get("tp3") not in (None, 0, 0.0, ""):
                    g["tp3"] = tp

    def _sync_all_open_group_targets(self, sl: float = None, tp: float = None):
        """Apply target sync across all currently open groups (global MODIFY actions)."""
        gids = set()
        for gid in self._open_groups.keys():
            try:
                gids.add(int(gid))
            except (TypeError, ValueError):
                continue
        if not gids:
            try:
                for g in self.scribe.get_open_groups():
                    gid = g.get("id")
                    if gid is not None:
                        gids.add(int(gid))
            except Exception:
                pass
        for gid in sorted(gids):
            self._sync_group_targets(gid, sl=sl, tp=tp)

    def _sync_modify_targets(self, group_id, *,
                              sl: float | None = None,
                              tp: float | None = None,
                              ticket: int | None = None,
                              tp_stage: int | None = None):
        """Persist a MODIFY scope to SCRIBE.

        Routing rules (in order):
          1. ``ticket`` set → update only that one position row (no group fan-out).
          2. ``tp_stage`` set + ``group_id`` set → stage-scoped update; only the
             matching ``trade_groups.tp<n>`` column moves so other stages keep
             their original target.
          3. otherwise → today's behaviour: group-wide or all-open fan-out.
        """
        if sl is None and tp is None:
            return
        if ticket is not None:
            try:
                self.scribe.update_position_sl_tp(int(ticket), sl=sl, tp=tp)
            except Exception as e:
                log.debug("BRIDGE: ticket-scoped SCRIBE update failed: %s", e)
            return
        if tp_stage is not None and group_id is not None:
            try:
                self.scribe.update_positions_sl_tp_by_stage(
                    int(group_id), int(tp_stage), sl=sl, tp=tp,
                )
            except Exception as e:
                log.debug("BRIDGE: stage-scoped SCRIBE update failed: %s", e)
            # Refresh in-memory cache for the affected stage column only.
            g = self._open_groups.get(int(group_id))
            if isinstance(g, dict):
                if sl is not None:
                    g["sl"] = sl
                if tp is not None:
                    g[f"tp{int(tp_stage)}"] = tp
            return
        if group_id is None:
            self._sync_all_open_group_targets(sl=sl, tp=tp)
        else:
            self._sync_group_targets(int(group_id), sl=sl, tp=tp)

    # ── AUTO_SCALPER: AURUM-driven autonomous scalping ──────────
    def _auto_scalper_tick(self, mt5: dict) -> None:
        """Called every AUTO_SCALPER_POLL_INTERVAL. Pre-filters, then asks AURUM."""
        from market_view import build_market_view, format_for_aurum, market_view_summary

        # Pre-filter: skip if sentinel, max groups, cooldown, or no data
        if self._sentinel_override:
            log.debug("AUTO_SCALPER: skipped — sentinel active")
            return
        if self._last_loss_close_ts > 0 and (time.time() - self._last_loss_close_ts) < DD_LOSS_COOLDOWN_SEC:
            remaining = DD_LOSS_COOLDOWN_SEC - (time.time() - self._last_loss_close_ts)
            log.debug("AUTO_SCALPER: skipped — loss cooldown (%.0fs remaining)", remaining)
            return
        if len(self._open_groups) >= AUTO_SCALPER_MAX_GROUPS:
            log.debug("AUTO_SCALPER: skipped — max groups (%d)", len(self._open_groups))
            return
        if not mt5:
            return

        view = build_market_view(mt5)
        h1_bias = view.get("h1_bias", "UNKNOWN")

        # H1 direction gate — never scalp against H1
        if h1_bias == "UNKNOWN" or h1_bias == "FLAT":
            log.debug("AUTO_SCALPER: skipped — H1 bias %s (no clear direction)", h1_bias)
            return

        # Multi-TF pre-screen: skip if all RSIs neutral (no setup)
        rsi_vals = []
        for tf in ("m5", "m15", "m30"):
            r = (view.get(tf) or {}).get("rsi_14")
            if r:
                rsi_vals.append(r)
        if rsi_vals and all(45 <= r <= 55 for r in rsi_vals):
            log.debug("AUTO_SCALPER: skipped — all RSIs neutral (%s)", rsi_vals)
            return

        # Build structured prompt for AURUM
        mtf_text = format_for_aurum(view)

        # Price action context for better decision-making
        m5 = view.get("m5", {})
        m15 = view.get("m15", {})
        h1 = view.get("h1", {})
        price_mid = (view.get("price") or {}).get("mid", 0)
        m5_atr = m5.get("atr_14", 0)
        pa_hints = []
        if m5.get("bb_lower") and m5.get("bb_upper") and price_mid:
            bb_range = m5["bb_upper"] - m5["bb_lower"]
            if bb_range > 0 and bb_range < m5_atr * 1.5:
                pa_hints.append("M5 BB SQUEEZE — breakout imminent")
        if h1.get("atr_14") and h1["atr_14"] > 0:
            pa_hints.append(f"Use SL={h1['atr_14']*1.5:.2f} (1.5x H1 ATR), TP1 at nearest M5 BB band or EMA")

        prompt = (
            f"AUTO_SCALPER tick. H1 bias: {h1_bias}. "
            f"Only {h1_bias.replace('BULL','BUY').replace('BEAR','SELL')} trades allowed.\n"
            f"Constraints: lot_per_trade={AUTO_SCALPER_LOT_SIZE}, num_trades={AUTO_SCALPER_NUM_TRADES}\n"
            f"\n{mtf_text}\n"
        )
        if pa_hints:
            prompt += "\nPrice action: " + " | ".join(pa_hints) + "\n"
        prompt += (
            f"\nDecision framework:\n"
            f"- BUY if: price near M5 BB lower + RSI<40 + M15 not overbought\n"
            f"- SELL if: price near M5 BB upper + RSI>60 + M15 not oversold\n"
            f"- PASS if: price mid-BB (no edge), all RSIs neutral (45-55), or lower TFs conflict with H1\n"
            f"- SL: 1-1.5x ATR from entry. TP1: nearest BB band/EMA. TP2: next TF structure.\n"
            f"\nIf you see a scalping opportunity aligned with H1 {h1_bias}, "
            f"respond with ONE OPEN_GROUP json block. "
            f"If no clear setup, respond: PASS: <one-line reason>"
        )

        log.info("AUTO_SCALPER: polling AURUM — %s", market_view_summary(view))
        self._bridge_activity(
            "AUTO_SCALPER_POLL",
            reason=f"H1={h1_bias}",
            notes=market_view_summary(view),
        )

        try:
            response = self.aurum.ask(prompt, source="AUTO_SCALPER")
        except Exception as e:
            log.error("AUTO_SCALPER: AURUM call failed: %s", e)
            return

        if not response or "PASS" in response.upper()[:20]:
            log.info("AUTO_SCALPER: AURUM passed — %s", response[:100] if response else "empty")
            return

        # AURUM responded — extract_json_commands will write aurum_cmd.json
        # which _check_aurum_command picks up on the next tick
        self.aurum._extract_json_commands_from_response(response)
        log.info("AUTO_SCALPER: AURUM responded with trade — processing next tick")

    # ── AURUM command processing ───────────────────────────────────
    def _check_aurum_command(self, mt5: dict):
        cmd = _read_json(AURUM_CMD_FILE)
        if not cmd:
            return
        action = (cmd.get("action") or "").upper()
        origin_source = str(cmd.get("origin_source") or cmd.get("source") or "").strip().upper()
        ts     = cmd.get("timestamp")
        if not action or ts == getattr(self, "_last_aurum_ts", None):
            return
        self._last_aurum_ts = ts

        if action == "MODE_CHANGE":
            new_mode = cmd.get("new_mode")
            if new_mode in VALID_MODES:
                self._change_mode(new_mode, "AURUM")

        elif action == "SENTINEL_OVERRIDE":
            duration = int(cmd.get("duration", SENTINEL_OVERRIDE_DURATION))
            self._sentinel_user_override = True
            self._sentinel_override_until = time.time() + duration
            self._sentinel_override = False  # lift immediately
            log.warning("BRIDGE: Sentinel OVERRIDDEN for %ds (reason: %s)",
                        duration, cmd.get("reason", "manual"))
            self.scribe.log_system_event(
                "SENTINEL_OVERRIDE_ON", triggered_by="USER",
                reason=f"{cmd.get('reason','')} — {duration}s")
            self.herald.send(
                f"⚠️ <b>SENTINEL OVERRIDE</b>\n"
                f"News guard bypassed for {duration}s.\n"
                f"Trading allowed. Auto-reverts.")

        elif action == "CLOSE_ALL":
            _write_forge_command({"action": "CLOSE_ALL", "timestamp": _now()})
            # Close all SCRIBE groups + clear cache (same as management CLOSE_ALL)
            for g in self.scribe.get_open_groups():
                gid = g.get("id")
                if gid is not None:
                    self.scribe.update_trade_group(
                        int(gid), "CLOSED_ALL", close_reason="AURUM_CLOSE_ALL"
                    )
            self._open_groups.clear()
            self._bridge_activity(
                "CLOSE_ALL_QUEUED",
                reason="AURUM",
                notes=json.dumps({"via": "aurum_cmd.json"}, default=str),
            )
            _tlog("AURUM", "CLOSE_ALL", "all groups closed in SCRIBE")

        elif action in ("OPEN_GROUP", "OPEN_TRADE"):
            if action == "OPEN_TRADE":
                cmd = self._normalize_aurum_open_trade(cmd)
            self._bridge_activity(
                "AURUM_COMMAND_RX",
                reason=action,
                notes=json.dumps(
                    {
                        "direction": cmd.get("direction"),
                        "entry_low": cmd.get("entry_low"),
                        "entry_high": cmd.get("entry_high"),
                    },
                    default=str,
                )[:800],
            )
            self._dispatch_aurum_open_group(cmd, mt5 or {})

        elif action == "MODIFY_TP":
            tp = cmd.get("tp")
            gid = cmd.get("group_id")
            if tp:
                tpv = float(tp)
                ticket, stage = _coerce_modify_scope(cmd)
                forge_cmd = {"action": "MODIFY_TP", "tp": tpv}
                if gid:
                    magic = self._lookup_group_magic(int(gid))
                    if magic:
                        forge_cmd["magic"] = magic
                if ticket is not None:
                    forge_cmd["ticket"] = ticket
                if stage is not None:
                    forge_cmd["tp_stage"] = stage
                # Ticket-scoped modifies get a strict verifier; broader scopes
                # (stage / group / global) fall back to one-tick spacing.
                verifier = (
                    self._build_ticket_tp_verifier(int(ticket), tpv)
                    if ticket is not None
                    else None
                )
                self._enqueue_forge_command(
                    forge_cmd,
                    verifier=verifier,
                    description=(
                        f"AURUM MODIFY_TP tp={tpv} group={gid} "
                        f"ticket={ticket} stage={stage}"
                    ),
                )
                self._sync_modify_targets(
                    gid, sl=None, tp=tpv, ticket=ticket, tp_stage=stage,
                )
                self._bridge_activity(
                    "MGMT_COMMAND", reason="MODIFY_TP",
                    notes=json.dumps({
                        "tp": tp, "group_id": gid, "ticket": ticket,
                        "tp_stage": stage, "via": "AURUM",
                    }, default=str))
                log.info(
                    "BRIDGE: AURUM MODIFY_TP tp=%s group=%s ticket=%s stage=%s",
                    tp, gid, ticket, stage,
                )

        elif action == "MODIFY_SL":
            sl = cmd.get("sl")
            gid = cmd.get("group_id")
            if sl:
                slv = float(sl)
                ticket, stage = _coerce_modify_scope(cmd)
                forge_cmd = {"action": "MODIFY_SL", "sl": slv}
                if gid:
                    magic = self._lookup_group_magic(int(gid))
                    if magic:
                        forge_cmd["magic"] = magic
                if ticket is not None:
                    forge_cmd["ticket"] = ticket
                if stage is not None:
                    forge_cmd["tp_stage"] = stage
                # Ticket-scoped MODIFY_SL benefits from a strict verifier
                # (matches the profit-ratchet path). For broader scopes the
                # queue uses the fire-and-forget ack so successive commands
                # still get ≥1-tick spacing.
                if ticket is not None:
                    direction_hint = (
                        self._known_positions.get(int(ticket), {}).get("direction")
                        or "BUY"
                    )
                    verifier = self._build_ticket_sl_verifier(
                        int(ticket), slv, direction_hint,
                    )
                else:
                    verifier = None
                self._enqueue_forge_command(
                    forge_cmd,
                    verifier=verifier,
                    description=(
                        f"AURUM MODIFY_SL sl={slv} group={gid} "
                        f"ticket={ticket} stage={stage}"
                    ),
                )
                self._sync_modify_targets(
                    gid, sl=slv, tp=None, ticket=ticket, tp_stage=stage,
                )
                self._bridge_activity(
                    "MGMT_COMMAND", reason="MODIFY_SL",
                    notes=json.dumps({
                        "sl": sl, "group_id": gid, "ticket": ticket,
                        "tp_stage": stage, "via": "AURUM",
                    }, default=str))
                log.info(
                    "BRIDGE: AURUM MODIFY_SL sl=%s group=%s ticket=%s stage=%s",
                    sl, gid, ticket, stage,
                )

        elif action == "CLOSE_GROUP":
            gid = cmd.get("group_id")
            if gid:
                magic = self._lookup_group_magic(int(gid))
                if magic:
                    _write_forge_command({"action": "CLOSE_GROUP", "magic": magic, "timestamp": _now()})
                    self.scribe.update_trade_group(int(gid), "CLOSED", close_reason="AURUM_CLOSE_GROUP")
                    self._bridge_activity(
                        "MGMT_COMMAND", reason="CLOSE_GROUP",
                        notes=json.dumps({"group_id": gid, "via": "AURUM"}, default=str))
                    log.info("BRIDGE: AURUM CLOSE_GROUP G%s", gid)

        elif action == "CLOSE_GROUP_PCT":
            gid = cmd.get("group_id")
            pct = cmd.get("pct", 70)
            if gid:
                magic = self._lookup_group_magic(int(gid))
                if magic:
                    _write_forge_command({"action": "CLOSE_GROUP_PCT", "magic": magic,
                                          "pct": float(pct), "timestamp": _now()})
                    self._bridge_activity(
                        "MGMT_COMMAND", reason="CLOSE_GROUP_PCT",
                        notes=json.dumps({"group_id": gid, "pct": pct, "via": "AURUM"}, default=str))
                    log.info("BRIDGE: AURUM CLOSE_GROUP_PCT G%s %s%%", gid, pct)

        elif action == "MOVE_BE":
            _write_forge_command({"action": "MOVE_BE_ALL", "timestamp": _now()})
            self._bridge_activity("MGMT_COMMAND", reason="MOVE_BE",
                                  notes=json.dumps({"via": "AURUM"}, default=str))
            log.info("BRIDGE: AURUM MOVE_BE_ALL")

        elif action == "CLOSE_PCT":
            pct = cmd.get("pct", 70)
            _write_forge_command({"action": "CLOSE_PCT", "pct": float(pct), "timestamp": _now()})
            self._bridge_activity(
                "MGMT_COMMAND", reason="CLOSE_PCT",
                notes=json.dumps({"pct": pct, "via": "AURUM"}, default=str))
            log.info("BRIDGE: AURUM CLOSE_PCT %s%%", pct)

        elif action == "CLOSE_PROFITABLE":
            _write_forge_command({"action": "CLOSE_PROFITABLE", "timestamp": _now()})
            self._bridge_activity("MGMT_COMMAND", reason="CLOSE_PROFITABLE",
                                  notes=json.dumps({"via": "AURUM"}, default=str))
            log.info("BRIDGE: AURUM CLOSE_PROFITABLE")

        elif action == "CLOSE_LOSING":
            _write_forge_command({"action": "CLOSE_LOSING", "timestamp": _now()})
            self._bridge_activity("MGMT_COMMAND", reason="CLOSE_LOSING",
                                  notes=json.dumps({"via": "AURUM"}, default=str))
            log.info("BRIDGE: AURUM CLOSE_LOSING")

        elif action in ("SCRIBE_QUERY", "SHELL_EXEC", "ANALYSIS_RUN"):
            if action == "SHELL_EXEC" and origin_source and origin_source in AEB_SHELL_EXEC_BLOCKED_SOURCES:
                result = {
                    "ok": False,
                    "action": "SHELL_EXEC",
                    "summary": "SHELL_EXEC blocked",
                    "error": f"SHELL_EXEC not permitted from source: {origin_source}",
                    "security_blocked": True,
                    "duration_ms": 0,
                }
            else:
                result = execute_action(
                    cmd,
                    db_path=self.scribe.db_path,
                    project_root=_ROOT,
                )
            self._report_aeb_result(result, via="BRIDGE_LOCAL")

        elif action == "AURUM_EXEC":
            payload = cmd.get("payload")
            if isinstance(payload, dict):
                payload_norm = _normalize_legacy_aurum_exec_payload(payload)
                if payload_norm is not payload:
                    cmd = dict(cmd)
                    cmd["payload"] = payload_norm
                    payload = payload_norm
            nested_action = ""
            if isinstance(payload, dict):
                nested_action = str(payload.get("action") or "").upper()
            if (
                nested_action == "SHELL_EXEC"
                and origin_source
                and origin_source in AEB_SHELL_EXEC_BLOCKED_SOURCES
            ):
                result = {
                    "ok": False,
                    "action": "SHELL_EXEC",
                    "summary": "SHELL_EXEC blocked",
                    "error": f"SHELL_EXEC not permitted from source: {origin_source}",
                    "security_blocked": True,
                    "duration_ms": 0,
                }
                self._report_aeb_result(result, via="BRIDGE_LOCAL")
            else:
                result = self._dispatch_aurum_exec(cmd)
                self._report_aeb_result(result, via="ATHENA_HTTP")

        # Consume the file so we don't reprocess
        try:
            os.remove(AURUM_CMD_FILE)
        except OSError as e:
            log.debug("BRIDGE: AURUM command consume skipped: %s", e)
            pass

    def _report_aeb_result(self, result: dict, *, via: str):
        if not isinstance(result, dict):
            result = {
                "ok": False,
                "action": "AEB",
                "summary": "AEB result malformed",
                "error": "result is not an object",
                "security_blocked": False,
                "duration_ms": 0,
            }
        action = str(result.get("action") or "AEB")
        ok = bool(result.get("ok"))
        blocked = bool(result.get("security_blocked"))
        level = logging.INFO if ok else logging.WARNING
        log.log(
            level,
            "BRIDGE: %s via %s ok=%s blocked=%s summary=%s",
            action,
            via,
            ok,
            blocked,
            result.get("summary"),
        )
        try:
            self.herald.send(
                format_result_for_telegram(result, max_chars=AEB_TELEGRAM_MAX_CHARS),
                parse_mode=None,
            )
        except Exception as e:
            log.debug("BRIDGE: AEB herald notification failed: %s", e)
        event_type = "AEB_EXEC_OK" if ok else ("AEB_EXEC_BLOCKED" if blocked else "AEB_EXEC_FAILED")
        self._bridge_activity(
            event_type,
            reason=f"{action} via {via}",
            notes=json.dumps(result, default=str)[:3000],
        )

    def _dispatch_aurum_exec(self, cmd: dict) -> dict:
        started = time.monotonic()

        def _fail(summary: str, error: str) -> dict:
            return {
                "ok": False,
                "action": "AURUM_EXEC",
                "summary": summary,
                "error": error,
                "security_blocked": False,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }

        endpoint = str(cmd.get("endpoint") or "/api/aurum/exec").strip()
        payload = cmd.get("payload")
        if not isinstance(payload, dict):
            payload = {
                k: v
                for k, v in cmd.items()
                if k not in {"action", "timestamp", "endpoint", "reply_to"}
            }
        if not isinstance(payload, dict) or not payload:
            return _fail("AURUM_EXEC payload missing", "AURUM_EXEC requires payload object")

        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            url = endpoint
        else:
            ep = endpoint if endpoint.startswith("/") else f"/{endpoint}"
            url = f"{AURUM_EXEC_BASE_URL.rstrip('/')}{ep}"

        timeout_sec = cmd.get("timeout_sec", AURUM_EXEC_TIMEOUT_SEC)
        try:
            timeout_i = max(1, min(int(timeout_sec), 120))
        except (TypeError, ValueError):
            timeout_i = AURUM_EXEC_TIMEOUT_SEC

        body = json.dumps(payload, default=str).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if AURUM_EXEC_SECRET:
            headers["X-ATHENA-AURUM-EXEC-TOKEN"] = AURUM_EXEC_SECRET
            headers["Authorization"] = f"Bearer {AURUM_EXEC_SECRET}"
        req = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout_i) as resp:
                status = int(resp.status or 200)
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                detail = str(e)
            return _fail("AURUM_EXEC HTTP failed", f"status={e.code} detail={detail}")
        except urllib.error.URLError as e:
            return _fail("AURUM_EXEC transport failed", str(e.reason))
        except Exception as e:
            return _fail("AURUM_EXEC failed", str(e))

        if not raw.strip():
            return _fail("AURUM_EXEC invalid response", "empty HTTP body")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            return _fail("AURUM_EXEC invalid response", f"non-JSON body: {e}")

        if not isinstance(parsed, dict):
            return _fail("AURUM_EXEC invalid response", "response body must be JSON object")
        result = parsed.get("result") if isinstance(parsed.get("result"), dict) else parsed
        if not isinstance(result, dict):
            return _fail("AURUM_EXEC invalid response", "result must be JSON object")

        out = dict(result)
        out.setdefault("action", str((payload or {}).get("action") or "AURUM_EXEC"))
        out.setdefault("summary", f"AURUM_EXEC HTTP {status}")
        out.setdefault("ok", status < 400 and not out.get("error"))
        out.setdefault("security_blocked", False)
        out.setdefault("duration_ms", int((time.monotonic() - started) * 1000))
        return out

    def _check_forge_scalper_entry(self, mt5: dict | None = None):
        """Detect native FORGE scalper entries and log them to SCRIBE."""
        entry = _read_json(SCALPER_ENTRY_FILE)
        if not entry:
            return
        ts = entry.get("timestamp")
        if ts == getattr(self, "_last_scalper_entry_ts", None):
            return
        self._last_scalper_entry_ts = ts

        gid = entry.get("group_id")
        try:
            magic = int(entry.get("magic") or 0)
        except (TypeError, ValueError):
            magic = 0
        direction = entry.get("direction", "?")
        setup_type = entry.get("setup_type", "UNKNOWN")
        trades_opened = int(entry.get("trades_opened") or 0)
        requested_trades = int(entry.get("num_trades") or 0)

        live_magics: set[int] = set()
        mt5_data = mt5 or {}
        for p in mt5_data.get("open_positions") or []:
            try:
                live_magics.add(int(p.get("magic") or 0))
            except (TypeError, ValueError):
                continue
        for o in mt5_data.get("pending_orders") or []:
            try:
                live_magics.add(int(o.get("magic") or 0))
            except (TypeError, ValueError):
                continue
        has_live_exposure = bool(magic and magic in live_magics)
        if trades_opened <= 0 or not has_live_exposure:
            reason = "no_trades_opened" if trades_opened <= 0 else "no_mt5_exposure_for_magic"
            self._bridge_activity(
                "FORGE_SCALP_ENTRY_IGNORED",
                reason=reason,
                notes=json.dumps(
                    {
                        "forge_group_id": gid,
                        "magic": magic,
                        "setup_type": setup_type,
                        "direction": direction,
                        "trades_opened": trades_opened,
                        "requested_trades": requested_trades,
                    },
                    default=str,
                ),
            )
            log.warning(
                "BRIDGE: ignore FORGE native scalper entry gid=%s magic=%s reason=%s",
                gid,
                magic,
                reason,
            )
            return

        existing_open = self.scribe.query(
            "SELECT id FROM trade_groups "
            "WHERE source='FORGE_NATIVE_SCALP' AND magic_number=? "
            "AND status IN ('OPEN','PARTIAL') "
            "ORDER BY id DESC LIMIT 1",
            (magic,),
        )
        if existing_open:
            self._bridge_activity(
                "FORGE_SCALP_ENTRY_IGNORED",
                reason="duplicate_open_group_magic",
                notes=json.dumps(
                    {"forge_group_id": gid, "magic": magic, "existing_group_id": existing_open[0].get("id")},
                    default=str,
                ),
            )
            return

        # Log trade group to SCRIBE
        effective_trades = trades_opened if trades_opened > 0 else max(1, requested_trades)
        group_data = {
            "direction": direction,
            "entry_low": entry.get("entry_price", 0),
            "entry_high": entry.get("entry_price", 0),
            "sl": entry.get("sl", 0),
            "tp1": entry.get("tp1", 0),
            "tp2": entry.get("tp2"),
            "num_trades": effective_trades,
            "lot_per_trade": entry.get("lot_per_trade", 0.01),
            "source": "FORGE_NATIVE_SCALP",
            "signal_id": None,
            "pending_entry_threshold_points": entry.get("pending_entry_threshold_points"),
            "trend_strength_atr_threshold": entry.get("trend_strength_atr_threshold"),
            "breakout_buffer_points": entry.get("breakout_buffer_points"),
        }
        scribe_gid = self.scribe.log_trade_group(
            group_data, self._effective_mode(), magic_number=magic)
        self._open_groups[scribe_gid] = {**group_data, "id": scribe_gid, "magic_number": magic}

        self._bridge_activity(
            "FORGE_SCALP_ENTRY",
            reason=setup_type,
            notes=json.dumps({
                "forge_group_id": gid,
                "scribe_group_id": scribe_gid,
                "direction": direction,
                "setup_type": setup_type,
                "sl": entry.get("sl"),
                "tp1": entry.get("tp1"),
                "trades_opened": trades_opened,
                "rsi": entry.get("m5_rsi"),
                "adx": entry.get("m5_adx"),
                "sentinel_tight": entry.get("sentinel_tight"),
                "pending_entry_threshold_points": entry.get("pending_entry_threshold_points"),
                "trend_strength_atr_threshold": entry.get("trend_strength_atr_threshold"),
                "breakout_buffer_points": entry.get("breakout_buffer_points"),
            }, default=str),
        )

        self.herald.send(
            f"{'\U0001f7e2' if direction == 'BUY' else '\U0001f534'} "
            f"<b>FORGE SCALP {setup_type}</b> -- {direction}\n"
            f"SL: <code>{entry.get('sl')}</code> TP1: <code>{entry.get('tp1')}</code>\n"
            f"RSI: {entry.get('m5_rsi')} ADX: {entry.get('m5_adx')} "
            f"ATR: {entry.get('m5_atr')}\n"
            f"{entry.get('num_trades')} x {entry.get('lot_per_trade')} lot"
            + (" [TIGHT TP]" if entry.get("sentinel_tight") else ""))

        _tlog("FORGE_NATIVE", setup_type, f"{direction} magic={magic} scribe_gid={scribe_gid}",
              group_id=gid)

    def _normalize_aurum_open_trade(self, cmd: dict) -> dict:
        """Map legacy / LLM OPEN_TRADE shape -> OPEN_GROUP fields FORGE understands."""
        from contracts.aurum_forge import normalize_aurum_open_trade

        return normalize_aurum_open_trade(cmd, _read_json(MARKET_FILE))

    def _dispatch_aurum_open_group(self, cmd: dict, mt5: dict) -> None:
        """
        AURUM-requested OPEN_GROUP: AEGIS → SCRIBE group → FORGE command.json
        (same end shape as Telegram SIGNAL / internal SCALPER dispatch).
        """
        eff = self._effective_mode()
        if eff not in ("SCALPER", "SIGNAL", "HYBRID", "AUTO_SCALPER"):
            log.warning(
                "BRIDGE: AURUM OPEN_GROUP ignored — effective_mode=%s "
                "(need SCALPER, SIGNAL, or HYBRID; WATCH if sentinel/circuit breaker)",
                eff,
            )
            self._bridge_activity(
                "AURUM_OPEN_SKIPPED",
                reason=f"effective_mode={eff}",
                notes="OPEN_GROUP requires SCALPER, SIGNAL, or HYBRID",
            )
            return

        direction = (cmd.get("direction") or "").upper()
        if direction not in ("BUY", "SELL"):
            log.warning("BRIDGE: AURUM OPEN_GROUP invalid direction %r", cmd.get("direction"))
            self._bridge_activity(
                "AURUM_OPEN_INVALID",
                reason="bad_direction",
                notes=json.dumps({"direction": cmd.get("direction")}, default=str),
            )
            return
        explicit_entry_legs = _normalize_forge_entry_legs(cmd.get("entry_legs"))

        try:
            el = float(cmd.get("entry_low", 0) or 0)
            eh = float(cmd.get("entry_high", 0) or el)
            sl = float(cmd.get("sl", 0) or 0)
            tp1 = float(cmd.get("tp1", 0) or 0)
        except (TypeError, ValueError):
            log.warning("BRIDGE: AURUM OPEN_GROUP non-numeric prices")
            self._bridge_activity(
                "AURUM_OPEN_INVALID",
                reason="non_numeric_prices",
                notes=json.dumps(dict(cmd), default=str)[:500],
            )
            return

        if explicit_entry_legs and el <= 0:
            prices = [float(leg["entry_price"]) for leg in explicit_entry_legs]
            el = min(prices)
            if eh <= 0:
                eh = max(prices)
        if el <= 0 or sl <= 0 or tp1 <= 0:
            log.warning("BRIDGE: AURUM OPEN_GROUP missing entry_low/high, sl, or tp1")
            self._bridge_activity(
                "AURUM_OPEN_INVALID",
                reason="missing_prices",
                notes=json.dumps(
                    {"entry_low": el, "entry_high": eh, "sl": sl, "tp1": tp1},
                    default=str,
                ),
            )
            return

        # Accept num_trades from AURUM command ("num_trades" or "trades")
        req_nt = cmd.get("num_trades") or cmd.get("trades")
        if explicit_entry_legs:
            req_nt = len(explicit_entry_legs)
        signal = {
            "direction": direction,
            "entry_low": el,
            "entry_high": eh,
            "sl": sl,
            "tp1": tp1,
            "tp2": cmd.get("tp2"),
            "tp3": cmd.get("tp3"),
            "entry_legs": explicit_entry_legs,
            "signal_id": None,
            "source": "AURUM",
        }
        if req_nt is not None:
            signal["num_trades"] = req_nt

        account = dict((mt5 or {}).get("account", {}) or {})
        account["open_groups_count"] = len(self._open_groups)
        pm = (mt5 or {}).get("price", {}) or {}
        cur = pm.get("bid") or pm.get("ask")
        try:
            cur = float(cur) if cur is not None else None
        except (TypeError, ValueError):
            cur = None
        regime_context = self._regime_context_for_trade(direction)

        approval = self.aegis.validate(
            signal,
            account,
            cur,
            mt5_data=mt5,
            regime_context=regime_context,
        )
        regime_meta = {**regime_context, **(approval.regime_metadata or {})}
        if not approval.approved:
            log.warning("BRIDGE: AURUM OPEN_GROUP rejected — %s", approval.reject_reason)
            self._bridge_activity(
                "TRADE_REJECTED",
                reason=approval.reject_reason,
                notes=json.dumps(
                    {
                        "source": "AURUM",
                        "direction": direction,
                        "gate": "AEGIS",
                        "regime": {
                            "label": regime_meta.get("label"),
                            "confidence": regime_meta.get("confidence"),
                            "policy": regime_meta.get("policy_name"),
                            "entry_mode": regime_meta.get("entry_mode"),
                        },
                    },
                    default=str,
                ),
            )
            _tlog("AURUM", "REJECTED", f"AEGIS: {approval.reject_reason}", level="warning")
            try:
                # Use plain text — HTML entities in reject_reason can break Telegram
                self.herald.send(
                    f"⚠️ AURUM trade blocked\nAEGIS: {approval.reject_reason}",
                    parse_mode=None,
                )
            except Exception:
                pass
            return

        lot_pt = float(approval.lot_per_trade)
        if cmd.get("lot_per_trade") is not None or cmd.get("lots") is not None:
            raw = cmd.get("lot_per_trade", cmd.get("lots"))
            try:
                req = float(raw)
                if req > 0:
                    lot_pt = max(0.01, min(req, float(approval.lot_per_trade)))
            except (TypeError, ValueError):
                pass

        group_data = {
            **signal,
            "lot_per_trade": lot_pt,
            "num_trades": approval.num_trades,
            "risk_pct": approval.risk_pct,
            "account_balance": account.get("balance", 0),
            "source": "AURUM",
            "regime_label": regime_meta.get("label"),
            "regime_confidence": regime_meta.get("confidence"),
            "regime_model": regime_meta.get("model_name"),
            "regime_entry_mode": regime_meta.get("entry_mode"),
            "regime_policy": regime_meta.get("policy_name"),
            "regime_fallback_reason": regime_meta.get("fallback_reason") or regime_meta.get("entry_gate_reason"),
        }
        gid = self.scribe.log_trade_group(group_data, eff)
        magic = FORGE_MAGIC_BASE + gid
        self.scribe.update_trade_group_magic(gid, magic)

        # Apply placement overrides (same as SIGNAL path).
        # When AURUM provides explicit entry_legs, honour them as-is.
        if explicit_entry_legs:
            ladder = [float(leg["entry_price"]) for leg in explicit_entry_legs]
            entry_type_label = "limit"
            cluster_flag = False
        else:
            ladder, entry_type_label, cluster_flag = _apply_signal_placement(
                direction, el, eh, approval.entry_ladder, approval.num_trades,
                current_price=cur,
            )
        self.scribe.update_group_open_meta(
            gid,
            entry_zone_pips=approval.entry_zone_pips or abs(eh - el),
            entry_type=entry_type_label,
            entry_cluster=int(bool(cluster_flag)),
        )
        self._open_groups[gid] = {**group_data, "magic_number": magic}

        forge_cmd = {
            "action": "OPEN_GROUP",
            "group_id": gid,
            "direction": direction,
            "entry_ladder": ladder,
            "entry_legs": explicit_entry_legs or _entry_legs_from_ladder(ladder),
            "lot_per_trade": lot_pt,
            "sl": sl,
            "tp1": tp1,
            "tp2": cmd.get("tp2"),
            "tp3": cmd.get("tp3"),
            "tp1_close_pct": TP1_CLOSE_PCT,
            "move_be_on_tp1": MOVE_BE_ON_TP1,
            "entry_type":    entry_type_label,
            "timestamp": _now(),
        }
        if entry_type_label == "market":
            log.info("BRIDGE: AURUM entry_type=market — placed %d market lots (zone collapsed)",
                     approval.num_trades)
        elif cluster_flag:
            log.info("BRIDGE: AURUM entry_zone_cluster=true — %d legs within %.1fpips of zone edge",
                     approval.num_trades, SIGNAL_ENTRY_CLUSTER_PIPS)
        cmd_paths = _write_forge_command(forge_cmd)
        log.info("BRIDGE: wrote OPEN_GROUP command.json → %s", cmd_paths[0])
        if len(cmd_paths) > 1:
            log.info("BRIDGE: command.json mirror → %s", cmd_paths[1])
        self._bridge_activity(
            "TRADE_QUEUED",
            reason="OPEN_GROUP",
            notes=json.dumps(
                {
                    "source": "AURUM",
                    "group_id": gid,
                    "direction": direction,
                    "num_trades": approval.num_trades,
                    "lot_per_trade": lot_pt,
                    "regime": {
                        "label": regime_meta.get("label"),
                        "confidence": regime_meta.get("confidence"),
                        "model_name": regime_meta.get("model_name"),
                        "entry_mode": regime_meta.get("entry_mode"),
                        "policy": regime_meta.get("policy_name"),
                        "applied": regime_meta.get("applied"),
                    },
                    "command_path": cmd_paths[0],
                    "command_paths": cmd_paths,
                },
                default=str,
            ),
        )
        self.herald.trade_group_opened({**group_data, "id": gid})
        _tlog("AURUM", "OPEN_GROUP", f"{direction} x{lot_pt}lot SL={signal['sl']} TP1={signal['tp1']}",
              group_id=gid)

    # ── Mode management ────────────────────────────────────────────
    def _effective_mode(self) -> str:
        """Returns WATCH if sentinel or circuit breaker override is active."""
        if self._mode == "OFF":
            return "OFF"
        if self._sentinel_override or self._mt5_blind_override:
            return "WATCH"
        return self._mode

    def _change_mode(self, new_mode: str, triggered_by: str = "USER", allow_pin_override: bool = False):
        pinned = self._pinned_mode()
        if pinned and not allow_pin_override and new_mode != pinned:
            log.warning(
                "BRIDGE: blocked mode change %s -> %s by %s (pin active: %s)",
                self._mode, new_mode, triggered_by, pinned
            )
            self.scribe.log_system_event(
                "MODE_CHANGE_BLOCKED",
                prev_mode=self._mode,
                new_mode=new_mode,
                triggered_by=triggered_by,
                reason=f"BRIDGE_PIN_MODE={pinned}",
                session=_session(),
            )
            return
        if new_mode == self._mode:
            return
        prev = self._mode
        self._mode = new_mode
        self.scribe.log_system_event("MODE_CHANGE", prev_mode=prev,
                                      new_mode=new_mode, triggered_by=triggered_by,
                                      session=_session())
        self.herald.mode_changed(prev, new_mode, triggered_by)
        self._write_config()
        self._write_status()
        self.listener.set_mode(new_mode)
        self.aurum.set_mode(new_mode)
        _tlog("SYSTEM", "MODE_CHANGE", f"{prev} -> {new_mode} (by {triggered_by})")

    # ── File writers ───────────────────────────────────────────────
    def _heartbeat_passive_components(self):
        """
        LENS snapshot row for ATHENA grid in WATCH/OFF (main loop skips MCP refresh).
        """
        ld = _read_json(LENS_SNAPSHOT_FILE)
        mode_eff = self._effective_mode()
        if ld:
            rsi = float(ld.get("rsi", 0) or 0)
            age = float(ld.get("age_seconds", 0) or 0)
            report_component_status(
                "LENS",
                "OK",
                mode=mode_eff,
                session=self._current_session,
                note=f"RSI={rsi:.1f} snapshot_age={age:.0f}s",
                last_action="WATCH/OFF: lens_snapshot.json",
            )
        else:
            report_component_status(
                "LENS",
                "WARN",
                mode=mode_eff,
                session=self._current_session,
                note="no lens_snapshot.json",
                last_action="WATCH/OFF: no MCP snapshot yet",
            )

    def _write_config(self):
        """Write config.json for FORGE to read (and mirror next to MT5_CMD_FILE_MIRROR if set)."""
        scalper_mode = _resolve_forge_scalper_mode(self._mode)
        body = {
            "mode":            self._mode,
            "effective_mode":  self._effective_mode(),
            "sentinel_active": self._sentinel_override,
            "tp1_close_pct":   TP1_CLOSE_PCT,
            "tp2_close_pct":   TP2_CLOSE_PCT,
            "move_be_on_tp1":  MOVE_BE_ON_TP1,
            "scalper_mode":    scalper_mode,
            "pending_entry_threshold_points": self._pending_entry_threshold_points,
            "trend_strength_atr_threshold": self._trend_strength_atr_threshold,
            "breakout_buffer_points": self._breakout_buffer_points,
            "timestamp":       _now(),
        }
        for pth in _forge_config_targets():
            _write_json(pth, body)

    def _write_status(self, mt5: dict = None, lens_snap=None):
        """Write status.json for ATHENA + AURUM."""
        acc = (mt5 or {}).get("account", {})
        _now_ts = time.time()
        _mt5_age = _now_ts - (mt5 or {}).get("timestamp_unix", 0) if mt5 else 9999
        _mt5_fresh = bool(mt5 and _mt5_age < MT5_STALE_SEC)
        _write_json(STATUS_FILE, {
            "mode":              self._mode,
            "effective_mode":    self._effective_mode(),
            "sentinel_active":   self._sentinel_override,
            "circuit_breaker":   self._mt5_blind_override,
            "mt5_fresh":         _mt5_fresh,
            "session":           self._current_session,
            "session_utc":       get_trading_session_utc(),
            "session_id":        self._current_session_id,
            "cycle":             self._cycle,
            "timestamp":         _now(),
            "version":           VERSION,
            "account_type":      self._broker_info.get("account_type","UNKNOWN"),
            "broker":            self._broker_info.get("broker","FBS"),
            "account": {
                "balance":    acc.get("balance"),
                "equity":     acc.get("equity"),
                "session_pnl":acc.get("session_pnl"),
                "open_count": acc.get("open_positions_count"),
            },
            "open_groups": len(self._open_groups),
            "lens": {"price": lens_snap.price if lens_snap else None,
                     "rsi":   lens_snap.rsi if lens_snap else None,
                     "bb":    lens_snap.bb_rating if lens_snap else None},
            "regime": self._regime_snapshot or {},
        })
        try:
            report_component_status(
                "BRIDGE",
                "WARN" if self._mt5_blind_override else "OK",
                mode=self._mode,
                session=self._current_session,
                note=f"Cycle {self._cycle} effective={self._effective_mode()}",
                last_action=f"session={self._current_session} groups={len(self._open_groups)}",
                error_msg="MT5 data stale" if self._mt5_blind_override else None,
                cycle=self._cycle,
            )
        except Exception as e:
            log.debug(f"BRIDGE heartbeat error: {e}")
        try:
            report_component_status(
                "SCRIBE",
                "OK",
                mode=self._effective_mode(),
                session=self._current_session,
                note="SQLite datastore",
                last_action=f"cycle {self._cycle} status + heartbeats",
            )
        except Exception as e:
            log.debug(f"SCRIBE heartbeat error: {e}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/bridge.log"),
        ]
    )
    # Allow mode override via CLI: python bridge.py --mode WATCH
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=VALID_MODES, default=None)
    args = parser.parse_args()

    bridge = Bridge()
    if args.mode and not RESTORE_MODE_ON_RESTART:
        bridge._mode = args.mode
    elif args.mode and RESTORE_MODE_ON_RESTART:
        # CLI --mode is the fallback when no saved state exists
        prev = _read_json(STATUS_FILE)
        if not prev.get("mode"):
            bridge._mode = args.mode

    bridge.run()
