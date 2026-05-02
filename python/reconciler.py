"""
reconciler.py — Position Reconciliation Service
================================================
Runs hourly. Compares what SCRIBE thinks is open
against what MT5 actually has open.

Catches silent failures: partial fills, rejected orders,
broker requotes, or positions closed manually in MT5
that BRIDGE doesn't know about.

Alerts via HERALD if mismatch found. Logs to SCRIBE.
Can run standalone or imported by BRIDGE.
"""

import os, json, logging, time
from datetime import datetime, timezone
from pathlib import Path

from scribe import get_scribe
from herald import get_herald
from status_report import report_component_status
from config_io import atomic_write_json

log = logging.getLogger("reconciler")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, ".."))


def _resolved_market_file() -> str:
    rel = os.environ.get("MT5_MARKET_FILE", "MT5/market_data.json")
    if os.path.isabs(rel):
        return rel
    return os.path.join(_ROOT, rel)


RECON_INTERVAL  = int(os.environ.get("RECON_INTERVAL_SEC", "3600"))   # 1 hour
# Tolerance: ignore differences below this $ amount (swap/commission noise)
PNL_TOLERANCE   = float(os.environ.get("RECON_PNL_TOLERANCE", "1.0"))
# Fallback for legacy rows missing magic_number column
FORGE_MAGIC_BASE = int(os.environ.get("FORGE_MAGIC_NUMBER", "202401"))
# Close SCRIBE trade_groups OPEN/PARTIAL when no MT5 position or pending shares that magic
RECON_CLOSE_STALE_GROUPS = os.environ.get("RECON_CLOSE_STALE_GROUPS", "true").lower() == "true"
# Minimum FORGE version that exports pending_orders (skip stale-group check if older)
FORGE_MIN_PENDING_VERSION = "1.2.4"


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        log.warning("Failed to read %s: %s", path, e)
        return {}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Reconciler:
    def __init__(self):
        self.scribe = get_scribe()
        self.herald = get_herald()
        log.info(f"RECONCILER initialised — interval={RECON_INTERVAL}s")

    def run_once(self) -> dict:
        """
        Run a single reconciliation check.
        Returns summary dict with any discrepancies found.
        """
        mt5_data = _read_json(_resolved_market_file())
        if not mt5_data:
            log.warning("RECONCILER: MT5 market_data.json not found — skipping")
            try:
                report_component_status(
                    "RECONCILER",
                    "WARN",
                    note="SKIPPED — no MT5 JSON",
                    last_action="run_once: empty or missing market_data",
                    error_msg="MT5 data unavailable",
                )
            except Exception:
                pass
            return {"status":"SKIPPED","reason":"MT5 data unavailable",
                    "issue_count":0,"mt5_open_count":0,"scribe_open_count":0}

        # ── What MT5 actually has open ────────────────────────────
        mt5_positions = {
            str(p["ticket"]): p
            for p in mt5_data.get("open_positions", [])
        }
        magics_live: set[int] = set()
        for p in mt5_data.get("open_positions", []):
            try:
                magics_live.add(int(p["magic"]))
            except (TypeError, ValueError, KeyError):
                pass
        for o in mt5_data.get("pending_orders", []) or []:
            try:
                magics_live.add(int(o["magic"]))
            except (TypeError, ValueError, KeyError):
                pass

        # ── What SCRIBE thinks is open ────────────────────────────
        scribe_open = self.scribe.query(
            """SELECT ticket, direction, lot_size, entry_price,
                      sl, tp, trade_group_id
               FROM trade_positions
               WHERE status = 'OPEN'
               AND ticket IS NOT NULL"""
        )
        scribe_tickets = {str(r["ticket"]): r for r in scribe_open}

        # ── Find discrepancies ─────────────────────────────────────
        issues = []

        # 1. Tickets SCRIBE thinks are open but MT5 doesn't have
        ghost_tickets = set(scribe_tickets) - set(mt5_positions)
        for ticket in ghost_tickets:
            r = scribe_tickets[ticket]
            issues.append({
                "type":    "GHOST_POSITION",
                "ticket":  ticket,
                "detail":  f"SCRIBE shows OPEN but not in MT5 — "
                           f"{r['direction']} {r['lot_size']}lot @ {r['entry_price']}",
                "severity":"HIGH",
            })
            # Auto-heal: mark as closed in SCRIBE with unknown reason
            log.warning(f"RECONCILER: ghost ticket {ticket} — marking CLOSED in SCRIBE")
            self.scribe.close_trade_position(
                ticket=int(ticket),
                close_price=0.0,
                close_reason="RECONCILER_GHOST",
                pnl=0.0,
                pips=0.0,
            )
            # Also log to trade_closures for audit trail
            self.scribe.log_trade_closure(
                ticket=int(ticket),
                trade_group_id=r.get("trade_group_id") or 0,
                direction=r.get("direction", "?"),
                lot_size=r.get("lot_size", 0),
                entry_price=r.get("entry_price", 0),
                close_price=0.0,
                sl=r.get("sl", 0), tp=r.get("tp", 0),
                close_reason="RECONCILER",
                pnl=0.0, pips=0.0,
                mode="RECONCILER",
            )

        # 2. Tickets MT5 has that SCRIBE doesn't know about
        # (manual trades opened directly in MT5 — not a problem but worth noting)
        unknown_tickets = set(mt5_positions) - set(scribe_tickets)
        for ticket in unknown_tickets:
            p = mt5_positions[ticket]
            # Only flag if it looks like one of our magic numbers
            magic = p.get("magic", 0)
            if 202400 <= magic < 213000:   # our magic number range
                issues.append({
                    "type":    "UNTRACKED_POSITION",
                    "ticket":  ticket,
                    "detail":  f"MT5 has position not in SCRIBE — "
                               f"{p.get('type')} {p.get('lots')}lot @ {p.get('open_price')} "
                               f"magic:{magic}",
                    "severity":"MEDIUM",
                })

        # 3. P&L sanity check — compare MT5 floating vs SCRIBE open group totals
        mt5_floating = mt5_data.get("account", {}).get("total_floating_pnl", 0)
        scribe_groups = self.scribe.get_open_groups()
        scribe_floating = sum(g.get("total_pnl") or 0 for g in scribe_groups)
        pnl_diff = abs(mt5_floating - scribe_floating)

        if pnl_diff > PNL_TOLERANCE and mt5_floating != 0:
            issues.append({
                "type":    "PNL_MISMATCH",
                "ticket":  None,
                "detail":  f"MT5 floating ${mt5_floating:.2f} vs "
                           f"SCRIBE groups ${scribe_floating:.2f} "
                           f"(diff ${pnl_diff:.2f})",
                "severity":"LOW",
            })

        # 4. SCRIBE trade_groups still OPEN but FORGE has no position/pending for that magic
        forge_version = mt5_data.get("forge_version", "")
        pending_reliable = forge_version >= FORGE_MIN_PENDING_VERSION
        if RECON_CLOSE_STALE_GROUPS:
            if not pending_reliable:
                log.info(
                    "RECONCILER: forge_version=%s < %s — skipping stale-group "
                    "check (pending_orders not exported by old FORGE)",
                    forge_version, FORGE_MIN_PENDING_VERSION,
                )
            else:
                for g in scribe_groups:
                    gid = g.get("id")
                    if gid is None:
                        continue
                    # Use stored magic_number; fall back to base+id for legacy rows
                    exp_magic = g.get("magic_number")
                    if exp_magic is None:
                        exp_magic = FORGE_MAGIC_BASE + int(gid)
                    else:
                        exp_magic = int(exp_magic)
                    if exp_magic not in magics_live:
                        issues.append({
                            "type":    "STALE_TRADE_GROUP",
                            "ticket":  None,
                            "detail":  f"SCRIBE group {gid} OPEN but MT5 has no FORGE position/pending "
                                       f"with magic {exp_magic} — marking CLOSED in SCRIBE",
                            "severity":"MEDIUM",
                        })
                        log.warning(
                            "RECONCILER: stale trade_group %s — no MT5 magic %s",
                            gid,
                            exp_magic,
                        )
                        self.scribe.update_trade_group(
                            int(gid),
                            "CLOSED",
                            close_reason="RECONCILER_NO_MT5_EXPOSURE",
                        )

        # ── Build result ───────────────────────────────────────────
        result = {
            "status":          "CLEAN" if not issues else "MISMATCH",
            "timestamp":       _now(),
            "mt5_open_count":  len(mt5_positions),
            "scribe_open_count": len(scribe_tickets),
            "issues":          issues,
            "issue_count":     len(issues),
            "mt5_floating":    mt5_floating,
            "scribe_floating": scribe_floating,
        }

        # ── Log to SCRIBE ──────────────────────────────────────────
        self.scribe.log_system_event(
            event_type="RECONCILIATION",
            notes=f"status={result['status']} issues={len(issues)} "
                  f"mt5={len(mt5_positions)} scribe={len(scribe_tickets)}",
        )

        # ── Alert on issues ────────────────────────────────────────
        if issues:
            high    = [i for i in issues if i["severity"] == "HIGH"]
            medium  = [i for i in issues if i["severity"] == "MEDIUM"]
            low     = [i for i in issues if i["severity"] == "LOW"]

            msg = f"⚠️ <b>RECONCILIATION MISMATCH</b>\n"
            msg += f"MT5: {len(mt5_positions)} open · SCRIBE: {len(scribe_tickets)} open\n\n"

            for issue in issues[:5]:   # cap at 5 in message
                icon = "🔴" if issue["severity"]=="HIGH" else "🟡" if issue["severity"]=="MEDIUM" else "🟢"
                msg += f"{icon} {issue['type']}\n{issue['detail']}\n\n"

            if len(issues) > 5:
                msg += f"...and {len(issues)-5} more issues. Check ATHENA."

            self.herald.send(msg)
            log.warning(f"RECONCILER: {len(issues)} issues — "
                        f"{len(high)} HIGH, {len(medium)} MEDIUM, {len(low)} LOW")
        else:
            log.info(f"RECONCILER: CLEAN — "
                     f"MT5={len(mt5_positions)} SCRIBE={len(scribe_tickets)} "
                     f"floating=${mt5_floating:.2f}")

        try:
            report_component_status(
                "RECONCILER",
                "WARN" if issues else "OK",
                note=f"{result['status']} mt5={result['mt5_open_count']} scribe={result['scribe_open_count']}",
                last_action=f"checked {result['timestamp'][:16] if result.get('timestamp') else 'now'}",
                error_msg=issues[0].get("detail") if issues else None,
            )
        except Exception as e:
            log.debug(f"RECONCILER heartbeat error: {e}")

        try:
            result_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "config", "reconciler_last.json"
            )
            atomic_write_json(result_path, result)
        except Exception as e:
            log.error(f"RECONCILER: failed to write result: {e}")

        return result

    def run_loop(self):
        """Run reconciliation on a loop. Called by BRIDGE every hour."""
        log.info("RECONCILER loop started")
        while True:
            try:
                result = self.run_once()
                log.info(f"RECONCILER: {result['status']} "
                         f"({result['issue_count']} issues)")
            except Exception as e:
                log.error(f"RECONCILER error: {e}", exc_info=True)
            time.sleep(RECON_INTERVAL)


# ── Singleton ─────────────────────────────────────────────────────
_instance: Reconciler = None

def get_reconciler() -> Reconciler:
    global _instance
    if _instance is None:
        _instance = Reconciler()
    return _instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    r = Reconciler()
    result = r.run_once()
    import json as _json
    print(_json.dumps(result, indent=2))
