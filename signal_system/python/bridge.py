"""
bridge.py — BRIDGE System Orchestrator
=======================================
Build order: #9 — depends on all other Python components.
Central nervous system. Mode state machine. Coordinates everything.
Entry point: python bridge.py
"""

import os, json, logging, time, sys
from datetime import datetime, timezone
from pathlib import Path

from scribe      import get_scribe
from herald      import get_herald
from sentinel    import Sentinel
from lens        import get_lens
from aegis       import get_aegis
from listener    import Listener
from aurum       import get_aurum
from reconciler  import get_reconciler
from status_report import report_component_status
from trading_session import get_trading_session_utc

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
LENS_INTERVAL   = int(os.environ.get("BRIDGE_LENS_SEC",     "60"))
# Refresh TradingView MCP while in WATCH (launchd has no login PATH without install_services fix)
LENS_WATCH_REFRESH_SEC = int(os.environ.get("LENS_WATCH_REFRESH_SEC", "60"))
SENTINEL_INTERVAL = int(os.environ.get("BRIDGE_SENTINEL_SEC","60"))
MT5_STALE_SEC   = int(os.environ.get("BRIDGE_MT5_STALE",    "120"))

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

# AUTO_SCALPER config
AUTO_SCALPER_LOT_SIZE      = float(os.environ.get("AUTO_SCALPER_LOT_SIZE",      "0.01"))
AUTO_SCALPER_NUM_TRADES    = int(os.environ.get("AUTO_SCALPER_NUM_TRADES",      "4"))
AUTO_SCALPER_POLL_INTERVAL = int(os.environ.get("AUTO_SCALPER_POLL_INTERVAL",   "120"))
AUTO_SCALPER_MAX_GROUPS    = int(os.environ.get("AUTO_SCALPER_MAX_GROUPS",      "2"))

# SIGNAL mode config
SIGNAL_LOT_SIZE    = float(os.environ.get("SIGNAL_LOT_SIZE",    "0.01"))
SIGNAL_NUM_TRADES  = int(os.environ.get("SIGNAL_NUM_TRADES",    "4"))
SIGNAL_EXPIRY_SEC  = int(os.environ.get("SIGNAL_EXPIRY_SEC",    "60"))   # 60s default — scalping signals must be fresh
PENDING_ORDER_TIMEOUT_SEC = int(os.environ.get("PENDING_ORDER_TIMEOUT_SEC", "120"))  # 2min — auto-cancel unfilled pending orders

# Mode persistence across restarts
RESTORE_MODE_ON_RESTART = os.environ.get("RESTORE_MODE_ON_RESTART", "true").lower() == "true"

# Sentinel override
SENTINEL_OVERRIDE_DURATION = int(os.environ.get("SENTINEL_OVERRIDE_DURATION_SEC", "600"))  # 10min default

# Drawdown protection
DD_EQUITY_CLOSE_ALL_PCT  = float(os.environ.get("DD_EQUITY_CLOSE_ALL_PCT",  "3.0"))
DD_FLOATING_BLOCK_PCT    = float(os.environ.get("DD_FLOATING_BLOCK_PCT",    "2.0"))   # block new groups if floating loss exceeds this % of balance
DD_LOSS_COOLDOWN_SEC     = int(os.environ.get("DD_LOSS_COOLDOWN_SEC",       "300"))   # seconds to wait after a group closes at loss before AUTO_SCALPER resumes

for d in ("config", "data", "logs"):
    Path(_PY, d).mkdir(parents=True, exist_ok=True)
Path(_ROOT, "MT5").mkdir(parents=True, exist_ok=True)


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}

def _write_json(path: str, data: dict):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.error(f"Write {path} error: {e}")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class Bridge:
    def __init__(self):
        self.scribe   = get_scribe()
        self.herald   = get_herald()
        self.sentinel    = Sentinel()
        self.lens        = get_lens()
        self.aegis       = get_aegis()
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
        self._last_recon_ts      = 0
        self._open_groups        = {}
        self._last_auto_scalper_ts  = 0
        self._sentinel_user_override = False   # user manually bypassed sentinel
        self._sentinel_override_until = 0      # auto-revert timestamp
        # Drawdown protection state
        self._session_peak_equity  = 0.0
        self._dd_close_all_fired   = False
        self._last_loss_close_ts   = 0
        # Position tracker
        self._known_positions: dict[int, dict] = {}   # ticket → snapshot
        self._known_pendings:  dict[int, dict] = {}   # ticket → snapshot
        self._tracker_seeded = False
        # Session tracking
        self._current_session    = "OFF_HOURS"
        self._current_session_id = None    # SCRIBE trading_sessions row id
        self._broker_info        = {}      # from FORGE broker_info.json

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
                "SELECT ticket, trade_group_id, magic_number, direction, entry_price "
                "FROM trade_positions WHERE status='OPEN' AND ticket IS NOT NULL"
            )
            for r in open_pos:
                t = int(r["ticket"])
                self._known_positions[t] = {
                    "group_id": r["trade_group_id"],
                    "magic": r["magic_number"],
                    "direction": r["direction"],
                    "open_price": r["entry_price"],
                    "last_profit": 0,
                    "current_price": r["entry_price"],
                }
        except Exception as e:
            log.warning("TRACKER seed from SCRIBE failed: %s", e)

        # Also seed from current market_data to catch positions SCRIBE doesn't know about yet
        for p in mt5.get("open_positions") or []:
            magic = p.get("magic", 0)
            if magic >= FORGE_MAGIC_BASE and magic < FORGE_MAGIC_BASE + FORGE_MAGIC_MAX + 1:
                t = int(p["ticket"])
                if t not in self._known_positions:
                    self._known_positions[t] = {
                        "group_id": self._resolve_group_for_magic(magic),
                        "magic": magic,
                        "direction": p.get("type", "SELL"),
                        "open_price": p.get("open_price"),
                        "last_profit": p.get("profit", 0),
                        "current_price": p.get("current_price"),
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
                }

        log.info("TRACKER seeded: %d positions, %d pendings from SCRIBE + market_data",
                 len(self._known_positions), len(self._known_pendings))
        self._tracker_seeded = True

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
            magic = p.get("magic", 0)
            if magic >= FORGE_MAGIC_BASE and magic < FORGE_MAGIC_BASE + FORGE_MAGIC_MAX + 1:
                live_positions[int(p["ticket"])] = p

        live_pendings: dict[int, dict] = {}
        for o in mt5.get("pending_orders") or []:
            if not o.get("forge_managed"):
                continue
            live_pendings[int(o["ticket"])] = o

        # ── New filled positions ───────────────────────────────────
        for ticket, p in live_positions.items():
            if ticket in self._known_positions:
                # Update last-known profit for close detection
                self._known_positions[ticket]["last_profit"] = p.get("profit", 0)
                self._known_positions[ticket]["current_price"] = p.get("current_price")
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
                }
                continue
            direction = p.get("type", "SELL")  # FORGE writes "BUY"/"SELL"
            self.scribe.log_trade_position(gid, {
                "ticket":      ticket,
                "magic":       magic,
                "direction":   direction,
                "lot_size":    p.get("lots"),
                "entry_price": p.get("open_price"),
                "sl":          p.get("sl"),
                "tp":          p.get("tp"),
            }, mode)
            self._known_positions[ticket] = {
                "group_id": gid, "magic": magic, "direction": direction,
                "open_price": p.get("open_price"), "last_profit": p.get("profit", 0),
                "current_price": p.get("current_price"),
            }
            log.info("TRACKER: new position ticket=%s G%s %s %.2flot @ %s",
                     ticket, gid, direction, p.get("lots", 0), p.get("open_price"))

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
                magic = self._lookup_group_magic(gid)
                if magic:
                    log.warning("TRACKER: pending orders for G%s stale (>%ds) — auto-cancelling",
                                gid, PENDING_ORDER_TIMEOUT_SEC)
                    _write_forge_command({"action": "CLOSE_GROUP", "magic": magic, "timestamp": _now()})
                    self.scribe.update_trade_group(gid, "CLOSED", close_reason="PENDING_EXPIRED")
                    self.herald.send(
                        f"⏰ <b>PENDING EXPIRED</b> — G{gid}\n"
                        f"Unfilled orders cancelled after {PENDING_ORDER_TIMEOUT_SEC}s")
                    self._bridge_activity(
                        "PENDING_EXPIRED", reason=f"G{gid} timeout {PENDING_ORDER_TIMEOUT_SEC}s")

        # ── Disappeared positions → closed (SL/TP/manual) ─────────
        closed_tickets = set(self._known_positions) - set(live_positions)
        groups_touched: dict[int, list] = {}  # gid → [pnl, ...]
        for ticket in closed_tickets:
            snap = self._known_positions.pop(ticket)
            gid = snap["group_id"]
            pnl = snap.get("last_profit", 0)
            close_price = snap.get("current_price") or 0
            open_price = snap.get("open_price") or 0
            # Estimate pips (XAUUSD: 1 pip = $0.01)
            pips = 0.0
            if open_price and close_price:
                raw = close_price - open_price
                if snap.get("direction") == "SELL":
                    raw = -raw
                pips = round(raw / 0.01, 1)  # XAUUSD pip

            self.scribe.close_trade_position(
                ticket=ticket,
                close_price=close_price,
                close_reason="BROKER",  # SL/TP/manual — we don't know which
                pnl=pnl,
                pips=pips,
            )
            groups_touched.setdefault(gid, []).append(pnl)
            log.info("TRACKER: position closed ticket=%s G%s pnl=%.2f pips=%.1f",
                     ticket, gid, pnl, pips)
            if pnl < 0:
                self._last_loss_close_ts = time.time()
            # Don't spam individual position alerts — batch at group level

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
                log.info(
                    "TRACKER: group G%s fully closed — %d trades, pnl=%.2f, pips=%.1f",
                    gid, trades_closed, total_pnl, total_pips,
                )
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

        restored = "(restored)" if RESTORE_MODE_ON_RESTART else "(default)"
        log.info(f"BRIDGE v{VERSION} starting — mode={self._mode} {restored} "
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
        mt5 = _read_json(MARKET_FILE)
        mt5_age = now - mt5.get("timestamp_unix", 0) if mt5 else 9999
        mt5_fresh = mt5 and mt5_age < MT5_STALE_SEC

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
                    reason=f"MT5 market_data.json stale: {mt5_age:.0f}s > {MT5_STALE_SEC}s",
                )
                # Throttle alerts — only fire once per 5 minutes
                if now - self._last_mt5_alert_ts > 300:
                    self.herald.error(
                        "CIRCUIT BREAKER",
                        f"MT5 data stale {mt5_age:.0f}s — trading suspended. "
                        f"Check FORGE EA on XAUUSD chart."
                    )
                    self._last_mt5_alert_ts = now
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

        # ── 1. SENTINEL check ─────────────────────────────────────
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
                log.warning("BRIDGE: Sentinel override ACTIVE")
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

        # ── 4. BROKER INFO from FORGE ──────────────────────────────
        broker_info = _read_json(BROKER_INFO_FILE)
        if broker_info:
            self._broker_info = broker_info

        # ── 4b. Open groups from SCRIBE (source of truth vs in-memory dict) ─
        self._sync_open_groups_from_scribe()

        # ── 5. AURUM command check ────────────────────────────────
        self._check_aurum_command(mt5)

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

        approval = self.aegis.validate(signal, account, current_price, mt5_data=mt5)

        if not approval.approved:
            log.warning(f"BRIDGE: Signal REJECTED — {approval.reject_reason}")
            self._bridge_activity(
                "SIGNAL_REJECTED",
                reason=approval.reject_reason,
                notes=json.dumps(
                    {
                        "source": "SIGNAL",
                        "direction": signal.get("direction"),
                        "signal_id": signal.get("signal_id"),
                        "gate": "AEGIS",
                    },
                    default=str,
                ),
            )
            self.scribe.update_signal_action(
                signal.get("signal_id"), "SKIPPED", approval.reject_reason)
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
        }

        group_id = self.scribe.log_trade_group(
            group_data, self._effective_mode())
        magic = FORGE_MAGIC_BASE + group_id
        # Store the magic FORGE will compute (MagicNumber + group_id)
        self.scribe.update_trade_group_magic(group_id, magic)
        self._open_groups[group_id] = {**group_data, "magic_number": magic}
        self.scribe.update_signal_action(
            signal.get("signal_id"), "EXECUTED", group_id=group_id)

        # Write command for FORGE
        cmd = {
            "action":        "OPEN_GROUP",
            "group_id":      group_id,
            "direction":     signal["direction"],
            "entry_ladder":  approval.entry_ladder,
            "lot_per_trade": approval.lot_per_trade,
            "sl":            signal["sl"],
            "tp1":           signal["tp1"],
            "tp2":           signal.get("tp2"),
            "tp3":           signal.get("tp3"),
            "tp1_close_pct": TP1_CLOSE_PCT,
            "tp2_close_pct": TP2_CLOSE_PCT,
            "move_be_on_tp1":MOVE_BE_ON_TP1,
            "timestamp":     _now(),
        }
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
                    "command_path": cmd_paths[0],
                    "command_paths": cmd_paths,
                },
                default=str,
            ),
        )
        self.herald.trade_group_opened({**group_data, "id": group_id})
        log.info(f"BRIDGE: Group {group_id} dispatched to FORGE "
                 f"— {approval.num_trades}×{approval.lot_per_trade}lot")

    def _process_mgmt_command(self, mt5: dict):
        mgmt = _read_json(MGMT_FILE)
        if not mgmt:
            return

        ts = mgmt.get("timestamp")
        if ts == self._last_mgmt_ts:
            return
        self._last_mgmt_ts = ts

        intent = mgmt.get("intent")
        log.info(f"BRIDGE: Management command — {intent}")

        # If LISTENER provided a group_id, use group-specific commands
        mgmt_gid = mgmt.get("group_id")

        cmd = None
        if intent == "CLOSE_ALL":
            if mgmt_gid:
                # Channel said "close all" but we scope it to their group
                intent = "CLOSE_GROUP"
                magic = self._lookup_group_magic(int(mgmt_gid))
                if magic:
                    cmd = {"action": "CLOSE_GROUP", "magic": magic, "timestamp": _now()}
                    self.scribe.update_trade_group(int(mgmt_gid), "CLOSED", close_reason="CHANNEL_CLOSE")
                    self.herald.trade_group_closed(int(mgmt_gid), "?", 0, 0, 0, f"CHANNEL_CLOSE ({mgmt.get('channel','')})")
            else:
                cmd = {"action": "CLOSE_ALL", "timestamp": _now()}
                for g in self.scribe.get_open_groups():
                    gid = g.get("id")
                    if gid is not None:
                        self.scribe.update_trade_group(
                            int(gid), "CLOSED_ALL", close_reason="MGMT_CLOSE_ALL"
                        )
                self._open_groups.clear()

        elif intent == "MOVE_BE":
            cmd = {"action": "MOVE_BE_ALL", "timestamp": _now()}

        elif intent == "CLOSE_PCT":
            pct = mgmt.get("pct", TP1_CLOSE_PCT)
            if mgmt_gid:
                magic = self._lookup_group_magic(int(mgmt_gid))
                if magic:
                    cmd = {"action": "CLOSE_GROUP_PCT", "magic": magic, "pct": float(pct), "timestamp": _now()}
            else:
                cmd = {"action": "CLOSE_PCT", "pct": pct, "timestamp": _now()}

        elif intent == "MODIFY_SL":
            sl = mgmt.get("sl")
            if sl:
                cmd = {"action": "MODIFY_SL", "sl": float(sl), "timestamp": _now()}

        elif intent == "MODIFY_TP":
            tp = mgmt.get("tp")
            if tp:
                cmd = {"action": "MODIFY_TP", "tp": float(tp), "timestamp": _now()}

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
            "source": "SCALPER",
        }
        log.info(f"BRIDGE SCALPER: {direction} signal @ {entry:.2f}")
        account = mt5.get("account", {}) if mt5 else {}
        account["open_groups_count"] = len(self._open_groups)
        approval = self.aegis.validate(signal, account, price, mt5_data=mt5)
        if approval.approved:
            group_data = {**signal, "lot_per_trade": approval.lot_per_trade,
                          "num_trades": approval.num_trades,
                          "risk_pct": approval.risk_pct,
                          "account_balance": account.get("balance",0),
                          "source": "SCALPER"}
            gid = self.scribe.log_trade_group(group_data, "SCALPER")
            magic = FORGE_MAGIC_BASE + gid
            self.scribe.update_trade_group_magic(gid, magic)
            self._open_groups[gid] = {**group_data, "magic_number": magic}
            cmd = {"action":"OPEN_GROUP","group_id":gid,"direction":direction,
                   "entry_ladder":approval.entry_ladder,
                   "lot_per_trade":approval.lot_per_trade,
                   "sl":sl,"tp1":tp1,"tp2":None,"tp3":None,
                   "tp1_close_pct":TP1_CLOSE_PCT,
                   "move_be_on_tp1":MOVE_BE_ON_TP1,
                   "timestamp":_now()}
            _write_forge_command(cmd)
            self._bridge_activity(
                "TRADE_QUEUED",
                reason="OPEN_GROUP",
                notes=json.dumps(
                    {
                        "source": "SCALPER",
                        "group_id": gid,
                        "direction": direction,
                        "num_trades": approval.num_trades,
                        "lot_per_trade": approval.lot_per_trade,
                    },
                    default=str,
                ),
            )
        else:
            self._bridge_activity(
                "TRADE_REJECTED",
                reason=approval.reject_reason,
                notes=json.dumps(
                    {"source": "SCALPER", "direction": direction, "gate": "AEGIS"},
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
        prompt = (
            f"AUTO_SCALPER tick. H1 bias: {h1_bias}. "
            f"Only {h1_bias.replace('BULL','BUY').replace('BEAR','SELL')} trades allowed.\n"
            f"Constraints: lot_per_trade={AUTO_SCALPER_LOT_SIZE}, num_trades={AUTO_SCALPER_NUM_TRADES}\n"
            f"\n{mtf_text}\n\n"
            f"If you see a scalping opportunity aligned with H1 {h1_bias}, "
            f"respond with ONE OPEN_GROUP json block (scalping SL/TP per SKILL rules). "
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
            log.info("BRIDGE: AURUM requested CLOSE_ALL")

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

        # Clear command after processing
        try:
            import os as _os
            _os.remove(AURUM_CMD_FILE)
        except:
            pass

    def _normalize_aurum_open_trade(self, cmd: dict) -> dict:
        """Map legacy / LLM OPEN_TRADE shape → OPEN_GROUP fields FORGE understands."""
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
        signal = {
            "direction": direction,
            "entry_low": el,
            "entry_high": eh,
            "sl": sl,
            "tp1": tp1,
            "tp2": cmd.get("tp2"),
            "tp3": cmd.get("tp3"),
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

        approval = self.aegis.validate(signal, account, cur, mt5_data=mt5)
        if not approval.approved:
            log.warning("BRIDGE: AURUM OPEN_GROUP rejected — %s", approval.reject_reason)
            self._bridge_activity(
                "TRADE_REJECTED",
                reason=approval.reject_reason,
                notes=json.dumps(
                    {"source": "AURUM", "direction": direction, "gate": "AEGIS"},
                    default=str,
                ),
            )
            try:
                self.herald.send(
                    f"⚠️ <b>AURUM trade blocked</b>\nAEGIS: {approval.reject_reason}"
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
        }
        gid = self.scribe.log_trade_group(group_data, eff)
        magic = FORGE_MAGIC_BASE + gid
        self.scribe.update_trade_group_magic(gid, magic)
        self._open_groups[gid] = {**group_data, "magic_number": magic}

        forge_cmd = {
            "action": "OPEN_GROUP",
            "group_id": gid,
            "direction": direction,
            "entry_ladder": approval.entry_ladder,
            "lot_per_trade": lot_pt,
            "sl": sl,
            "tp1": tp1,
            "tp2": cmd.get("tp2"),
            "tp3": cmd.get("tp3"),
            "tp1_close_pct": TP1_CLOSE_PCT,
            "move_be_on_tp1": MOVE_BE_ON_TP1,
            "timestamp": _now(),
        }
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
                    "command_path": cmd_paths[0],
                    "command_paths": cmd_paths,
                },
                default=str,
            ),
        )
        self.herald.trade_group_opened({**group_data, "id": gid})
        log.info(
            "BRIDGE: AURUM OPEN_GROUP #%s → FORGE (%s ×%s lot)",
            gid, direction, lot_pt,
        )

    # ── Mode management ────────────────────────────────────────────
    def _effective_mode(self) -> str:
        """Returns WATCH if sentinel or circuit breaker override is active."""
        if self._mode == "OFF":
            return "OFF"
        if self._sentinel_override or self._mt5_blind_override:
            return "WATCH"
        return self._mode

    def _change_mode(self, new_mode: str, triggered_by: str = "USER"):
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
        log.info(f"BRIDGE: Mode {prev} → {new_mode} (by {triggered_by})")

    # ── File writers ───────────────────────────────────────────────
    def _heartbeat_passive_components(self):
        """
        LENS snapshot row for ATHENA grid in WATCH/OFF (main loop skips MCP refresh).
        """
        lens_rel = os.environ.get(
            "LENS_SNAPSHOT",
            os.environ.get("LENS_SNAPSHOT_FILE", "config/lens_snapshot.json"),
        )
        lens_path = lens_rel if os.path.isabs(lens_rel) else _under_python(lens_rel)
        ld = _read_json(lens_path)
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
        body = {
            "mode":            self._mode,
            "effective_mode":  self._effective_mode(),
            "sentinel_active": self._sentinel_override,
            "tp1_close_pct":   TP1_CLOSE_PCT,
            "tp2_close_pct":   TP2_CLOSE_PCT,
            "move_be_on_tp1":  MOVE_BE_ON_TP1,
            "timestamp":       _now(),
        }
        for pth in _forge_config_targets():
            _write_json(pth, body)

    def _write_status(self, mt5: dict = None, lens_snap=None):
        """Write status.json for ATHENA + AURUM."""
        acc = (mt5 or {}).get("account", {})
        sent = _read_json(SENTINEL_FILE) if not hasattr(self, '_sent_cache') else {}
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
