"""
athena_api.py — ATHENA Flask API
=================================
Build order: #10 — depends on SCRIBE.
Serves JSON data to the React dashboard.
Also exposes AURUM chat endpoint.
Run: python athena_api.py
Dashboard: http://localhost:7842
"""

import os, json, logging, time
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from scribe import get_scribe

log = logging.getLogger("athena_api")

# ── Absolute base paths (resolve correctly regardless of CWD) ─────
# Services run with WorkingDirectory=python/, so:
#   config/ files  → python/config/   (where bridge.py writes)
#   MT5/ files     → signal_system/MT5/ (root-level symlink to MetaQuotes)
_HERE = os.path.dirname(os.path.abspath(__file__))   # ~/signal_system/python
_ROOT = os.path.normpath(os.path.join(_HERE, ".."))  # ~/signal_system

def _py_path(rel: str) -> str:
    """Absolute path anchored at python/ directory."""
    if os.path.isabs(rel):
        return rel
    return os.path.join(_HERE, rel)

def _root_path(rel: str) -> str:
    """Absolute path anchored at project root."""
    if os.path.isabs(rel):
        return rel
    return os.path.join(_ROOT, rel)

PORT           = int(os.environ.get("ATHENA_PORT", "7842"))
# MT5 files live at project root (root-level symlink)
MARKET_FILE    = _root_path(os.environ.get("MT5_MARKET_FILE",  "MT5/market_data.json"))
MODE_FILE      = _root_path(os.environ.get("MT5_MODE_FILE",    "MT5/mode_status.json"))
BROKER_FILE    = _root_path(os.environ.get("MT5_BROKER_FILE",  "MT5/broker_info.json"))
# Config files live in python/config/ (written by bridge.py from python/ CWD)
STATUS_FILE    = _py_path(os.environ.get("BRIDGE_STATUS_FILE",   "config/status.json"))
LENS_FILE      = _py_path(os.environ.get("LENS_SNAPSHOT_FILE",   "config/lens_snapshot.json"))
SENTINEL_FILE  = _py_path(os.environ.get("SENTINEL_STATUS_FILE", "config/sentinel_status.json"))
AURUM_CMD_FILE = _py_path(os.environ.get("AURUM_CMD_FILE",       "config/aurum_cmd.json"))
# reconciler writes to signal_system/config/ using __file__-relative path
RECON_FILE     = os.path.join(_ROOT, "config", "reconciler_last.json")
DASHBOARD_DIR  = os.environ.get("DASHBOARD_DIR", os.path.join(_ROOT, "dashboard"))

app   = Flask(__name__, static_folder=DASHBOARD_DIR)
CORS(app)

def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}


# ── Live data endpoint ─────────────────────────────────────────────
@app.route("/api/live")
def api_live():
    mt5      = _read_json(MARKET_FILE)
    status   = _read_json(STATUS_FILE)
    lens     = _read_json(LENS_FILE)
    sentinel = _read_json(SENTINEL_FILE)
    broker   = _read_json(BROKER_FILE)
    recon    = _read_json(RECON_FILE)
    scribe   = get_scribe()

    # AEGIS scale state
    aegis_state = {"streak": 0, "streak_type": "NONE",
                   "scale_factor": 1, "scale_reason": "UNKNOWN", "session_pnl": 0}
    try:
        from aegis import get_aegis
        a = get_aegis()
        scale_factor, scale_reason = a._get_scale_factor()
        session_pnl = a._get_session_pnl()
        trades = scribe.query(
            "SELECT pnl FROM trade_positions WHERE status='CLOSED' "
            "ORDER BY close_time DESC LIMIT 10"
        )
        streak = 0
        streak_type = "NONE"
        if trades:
            first = trades[0]["pnl"]
            streak_type = "WIN" if first > 0 else "LOSS"
            for t in trades:
                if (t["pnl"] > 0) == (first > 0):
                    streak += 1
                else:
                    break
        aegis_state = {
            "scale_factor":  scale_factor,
            "scale_reason":  scale_reason,
            "session_pnl":   session_pnl,
            "streak":        streak,
            "streak_type":   streak_type,
        }
    except Exception as e:
        log.warning(f"AEGIS state error: {e}")

    # Component heartbeats
    heartbeats = {}
    try:
        rows = scribe.get_component_heartbeats()
        for r in rows:
            heartbeats[r["component"]] = {
                "status":      r["status"],
                "timestamp":   r["timestamp"],
                "note":        r["note"],
                "last_action": r["last_action"],
                "error_msg":   r["error_msg"],
            }
    except Exception as e:
        log.warning(f"Heartbeat read error: {e}")

    return jsonify({
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "mode":            status.get("mode", "UNKNOWN"),
        "effective_mode":  status.get("effective_mode", "UNKNOWN"),
        "session":         status.get("session", "OFF_HOURS"),
        "session_id":      status.get("session_id"),
        "cycle":           status.get("cycle", 0),
        "version":         status.get("version", "1.1.0"),

        # Safety state
        "sentinel_active":   status.get("sentinel_active", False),
        "circuit_breaker":   status.get("circuit_breaker", False),
        "mt5_fresh":         status.get("mt5_fresh", False),

        # Broker / account identity
        "account_type": broker.get("account_type", "UNKNOWN"),
        "broker":       broker.get("broker", ""),
        "server":       broker.get("server", ""),
        "currency":     broker.get("currency", "USD"),
        "leverage":     broker.get("leverage"),

        # Live account data from MT5
        "account":  mt5.get("account", {}),
        "price":    mt5.get("price", {}),
        "indicators_h1": mt5.get("indicators_h1", {}),
        "open_positions": mt5.get("open_positions", []),
        "mt5_connected":  bool(mt5),

        # LENS
        "lens": lens,

        # SENTINEL
        "sentinel": sentinel,

        # Open trade groups
        "open_groups": scribe.get_open_groups(),

        # Today's performance
        "performance": scribe.get_performance(days=1),

        # AEGIS risk state
        "aegis": aegis_state,

        # Component health (from heartbeats)
        "components": heartbeats,

        # Reconciler last result
        "reconciler": {
            "status":    recon.get("status", "UNKNOWN"),
            "timestamp": recon.get("timestamp"),
            "issues":    recon.get("issue_count", 0),
            "mt5_open":  recon.get("mt5_open_count", 0),
            "scribe_open": recon.get("scribe_open_count", 0),
        } if recon else None,
    })


# ── Component health endpoint ──────────────────────────────────────
@app.route("/api/components")
def api_components():
    """Component health panel — one entry per component."""
    scribe  = get_scribe()
    mode_st = _read_json(MODE_FILE)
    broker  = _read_json(BROKER_FILE)
    mt5     = _read_json(MARKET_FILE)

    heartbeats = {}
    try:
        for r in scribe.get_component_heartbeats():
            heartbeats[r["component"]] = r
    except Exception as e:
        log.warning(f"Heartbeat error: {e}")

    # FORGE synthesised from MT5 JSON files
    mt5_age = time.time() - mt5.get("timestamp_unix", 0) if mt5 else 9999
    forge_st = "OK" if mt5_age < 120 else ("WARN" if mt5_age < 300 else "ERROR")
    heartbeats["FORGE"] = {
        "component":   "FORGE",
        "status":      forge_st,
        "timestamp":   mt5.get("timestamp_utc") if mt5 else None,
        "note":        f"{broker.get('account_type','?')} @ {broker.get('server','')}",
        "last_action": f"market_data.json age={mt5_age:.0f}s",
        "error_msg":   "Data stale" if forge_st == "ERROR" else None,
        "mode":        mode_st.get("mode"),
    }

    # ATHENA reports itself
    heartbeats["ATHENA"] = {
        "component": "ATHENA", "status": "OK",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "API serving", "last_action": "GET /api/components",
        "error_msg": None,
    }

    expected = ["BRIDGE","FORGE","LISTENER","LENS","SENTINEL",
                "AEGIS","SCRIBE","HERALD","AURUM","RECONCILER","ATHENA"]
    components = []
    for name in expected:
        hb = heartbeats.get(name, {})
        components.append({
            "name":        name,
            "status":      hb.get("status", "UNKNOWN"),
            "ok":          hb.get("status") == "OK",
            "timestamp":   hb.get("timestamp"),
            "note":        hb.get("note", "No heartbeat received yet"),
            "last_action": hb.get("last_action"),
            "error_msg":   hb.get("error_msg"),
            "mode":        hb.get("mode"),
        })

    healthy = sum(1 for c in components if c["ok"])
    return jsonify({
        "components": components,
        "total":      len(components),
        "healthy":    healthy,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    })


# ── Reconciler last result ─────────────────────────────────────────
@app.route("/api/reconciler")
def api_reconciler():
    """Last reconciler run result."""
    result = _read_json(RECON_FILE)
    if not result:
        return jsonify({
            "status": "NEVER_RUN",
            "issue_count": 0,
            "issues": [],
            "mt5_open_count": 0,
            "scribe_open_count": 0,
        })
    return jsonify(result)


# ── AURUM chat endpoint ────────────────────────────────────────────
@app.route("/api/aurum/ask", methods=["POST"])
def api_aurum_ask():
    data  = request.json or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "empty query"}), 400
    try:
        from aurum import get_aurum
        aurum = get_aurum()
        result = aurum.flask_ask(query)
        return jsonify(result)
    except Exception as e:
        log.error(f"AURUM API error: {e}")
        return jsonify({"response": f"AURUM unavailable: {e}", "timestamp": datetime.now(timezone.utc).isoformat()})


# ── Mode switch endpoint ───────────────────────────────────────────
@app.route("/api/mode", methods=["POST"])
def api_mode():
    data = request.json or {}
    new_mode = data.get("mode", "").upper()
    if new_mode not in ("OFF","WATCH","SIGNAL","SCALPER","HYBRID"):
        return jsonify({"error": "invalid mode"}), 400
    cmd = {
        "action":    "MODE_CHANGE",
        "new_mode":  new_mode,
        "reason":    "ATHENA dashboard",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(AURUM_CMD_FILE, "w") as f:
            json.dump(cmd, f, indent=2)
        return jsonify({"ok": True, "new_mode": new_mode})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Trading session history ────────────────────────────────────────
@app.route("/api/sessions")
def api_sessions():
    limit = int(request.args.get("limit", 20))
    scribe = get_scribe()
    return jsonify(scribe.get_session_history(limit))


@app.route("/api/sessions/current")
def api_session_current():
    scribe = get_scribe()
    sid = scribe.get_current_session_id()
    if sid is None:
        return jsonify({"session": None})
    rows = scribe.query(
        "SELECT * FROM trading_sessions WHERE id=?", (sid,))
    return jsonify({"session": rows[0] if rows else None})


# ── Signal room / channel performance ─────────────────────────────
@app.route("/api/channel_performance")
def api_channel_performance():
    days = int(request.args.get("days", 30))
    scribe = get_scribe()
    rows = scribe.query(
        """SELECT
               sr.channel_name                                    AS channel,
               COUNT(*)                                           AS total_signals,
               SUM(CASE WHEN sr.action_taken='EXECUTED' THEN 1 ELSE 0 END) AS executed,
               SUM(CASE WHEN sr.action_taken='SKIPPED'  THEN 1 ELSE 0 END) AS skipped,
               SUM(CASE WHEN sr.action_taken='EXPIRED'  THEN 1 ELSE 0 END) AS expired,
               COUNT(tg.id)                                        AS groups_opened,
               COALESCE(SUM(tg.total_pnl), 0)                    AS total_pnl,
               COALESCE(AVG(tg.pips_captured), 0)                AS avg_pips,
               SUM(CASE WHEN tg.total_pnl > 0 THEN 1 ELSE 0 END) AS wins,
               ROUND(
                   100.0 * SUM(CASE WHEN tg.total_pnl > 0 THEN 1 ELSE 0 END)
                   / NULLIF(COUNT(tg.id), 0), 1
               )                                                  AS win_rate
           FROM signals_received sr
           LEFT JOIN trade_groups tg ON sr.trade_group_id = tg.id
           WHERE sr.timestamp >= datetime('now', ? )
           AND sr.channel_name IS NOT NULL
           GROUP BY sr.channel_name
           ORDER BY total_pnl DESC""",
        (f"-{days} days",)
    )
    return jsonify({"channels": rows, "days": days})


# ── AEGIS scaling state ────────────────────────────────────────────
@app.route("/api/aegis_state")
def api_aegis_state():
    scribe = get_scribe()
    # Last 10 closed trades for streak display
    trades = scribe.query(
        """SELECT pnl, close_time, direction, trade_group_id
           FROM trade_positions
           WHERE status='CLOSED' AND pnl IS NOT NULL
           ORDER BY close_time DESC LIMIT 10"""
    )
    streak = 0
    streak_type = "NONE"
    if trades:
        first_pnl = trades[0]["pnl"]
        streak_type = "WIN" if first_pnl > 0 else "LOSS"
        for t in trades:
            if (t["pnl"] > 0) == (first_pnl > 0):
                streak += 1
            else:
                break
    return jsonify({
        "streak": streak,
        "streak_type": streak_type,
        "recent_trades": trades[:5],
    })


# ── Signal history ─────────────────────────────────────────────────
@app.route("/api/signals")
def api_signals():
    limit = int(request.args.get("limit", 20))
    scribe = get_scribe()
    return jsonify(scribe.get_recent_signals(limit))


# ── Performance data ───────────────────────────────────────────────
@app.route("/api/performance")
def api_performance():
    days = int(request.args.get("days", 7))
    mode = request.args.get("mode", None)
    scribe = get_scribe()
    return jsonify(scribe.get_performance(mode=mode, days=days))


# ── P&L curve for chart ────────────────────────────────────────────
@app.route("/api/pnl_curve")
def api_pnl_curve():
    scribe = get_scribe()
    rows = scribe.query("""
        SELECT close_time, SUM(pnl) OVER (ORDER BY close_time) AS cumulative
        FROM trade_positions
        WHERE status='CLOSED' AND close_time >= date('now','-1 day')
        ORDER BY close_time
    """)
    return jsonify(rows)


# ── SCRIBE query (for AURUM / power users) ─────────────────────────
@app.route("/api/scribe/query", methods=["POST"])
def api_scribe_query():
    data = request.json or {}
    sql  = data.get("sql", "")
    # Only allow SELECT
    if not sql.strip().upper().startswith("SELECT"):
        return jsonify({"error": "only SELECT allowed"}), 400
    try:
        scribe = get_scribe()
        rows = scribe.query(sql)
        return jsonify({"rows": rows, "count": len(rows)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── System events log ──────────────────────────────────────────────
@app.route("/api/events")
def api_events():
    limit = int(request.args.get("limit", 50))
    scribe = get_scribe()
    rows = scribe.query(
        "SELECT * FROM system_events ORDER BY timestamp DESC LIMIT ?", (limit,))
    return jsonify(rows)


# ── Health check ───────────────────────────────────────────────────
@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mt5_connected": bool(_read_json(MARKET_FILE)),
        "bridge_running": bool(_read_json(STATUS_FILE)),
    })


# ── Serve React dashboard ──────────────────────────────────────────
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_dashboard(path):
    if path and (Path(DASHBOARD_DIR) / path).exists():
        return send_from_directory(DASHBOARD_DIR, path)
    return send_from_directory(DASHBOARD_DIR, "index.html")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    log.info(f"ATHENA API starting on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
