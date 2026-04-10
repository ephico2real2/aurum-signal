from __future__ import annotations

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
from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint

from scribe import get_scribe
from status_report import KNOWN_COMPONENTS
from market_data import MT5_STALE_SEC, build_execution_quote, safe_float
from trading_session import get_trading_session_utc, trading_day_reset_hour_utc

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


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(os.environ.get(name, str(default)))
        return max(lo, min(v, hi))
    except (TypeError, ValueError):
        return default


# POST /api/scribe/query — optional shared secret (not OAuth). Empty/unset = no auth (typical local-only).
SCRIBE_QUERY_SECRET = (os.environ.get("ATHENA_SCRIBE_QUERY_SECRET") or "").strip()
SCRIBE_QUERY_MAX_ROWS = _env_int("SCRIBE_QUERY_MAX_ROWS", 500, 1, 50_000)
SCRIBE_QUERY_BUSY_MS = _env_int("SCRIBE_QUERY_BUSY_MS", 5000, 0, 120_000)
# MT5 files live at project root (root-level symlink)
MARKET_FILE    = _root_path(os.environ.get("MT5_MARKET_FILE",  "MT5/market_data.json"))
MODE_FILE      = _root_path(os.environ.get("MT5_MODE_FILE",    "MT5/mode_status.json"))
BROKER_FILE    = _root_path(os.environ.get("MT5_BROKER_FILE",  "MT5/broker_info.json"))
# Config files live in python/config/ (written by bridge.py from python/ CWD)
STATUS_FILE    = _py_path(os.environ.get("BRIDGE_STATUS_FILE",   "config/status.json"))
LENS_FILE      = _py_path(os.environ.get("LENS_SNAPSHOT_FILE",   "config/lens_snapshot.json"))
LENS_BRIEF_FILE = _py_path(os.environ.get("LENS_BRIEF_FILE", "config/lens_brief.json"))
SENTINEL_FILE  = _py_path(os.environ.get("SENTINEL_STATUS_FILE", "config/sentinel_status.json"))
AURUM_CMD_FILE = _py_path(os.environ.get("AURUM_CMD_FILE",       "config/aurum_cmd.json"))
MGMT_FILE      = _py_path(os.environ.get("LISTENER_MGMT_FILE",   "config/management_cmd.json"))
# reconciler writes to signal_system/config/ using __file__-relative path
RECON_FILE     = os.path.join(_ROOT, "config", "reconciler_last.json")
DASHBOARD_DIR  = os.environ.get("DASHBOARD_DIR", os.path.join(_ROOT, "dashboard"))
OPENAPI_YAML   = os.path.join(_ROOT, "schemas", "openapi.yaml")

app   = Flask(__name__, static_folder=DASHBOARD_DIR)
CORS(app)

# Swagger UI — interactive docs for OpenAPI (same-origin spec at /api/openapi.yaml)
app.register_blueprint(
    get_swaggerui_blueprint(
        "/api/docs",
        "/api/openapi.yaml",
        config={"app_name": "ATHENA API"},
    )
)

def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}


FORGE_MAGIC_NUMBER_DEFAULT = 202401  # must match ea/FORGE.mq5 input MagicNumber unless overridden


def partition_open_groups_for_athena(
    scribe_open_groups: list,
    mt5: dict,
    forge_magic_base: int,
) -> tuple[list, list]:
    """
    ATHENA group tiles should reflect broker truth, not an immediate SCRIBE write after
    AURUM/BRIDGE queues OPEN_GROUP. A group appears in the confirmed list only when
    its magic_number appears on an MT5 position or pending order in market_data.json.

    Uses the stored magic_number from SCRIBE; falls back to base + id for legacy rows.
    """
    magics: set[int] = set()
    for p in (mt5 or {}).get("open_positions") or []:
        try:
            magics.add(int(p["magic"]))
        except (TypeError, ValueError, KeyError):
            pass
    for o in (mt5 or {}).get("pending_orders") or []:
        try:
            magics.add(int(o["magic"]))
        except (TypeError, ValueError, KeyError):
            pass
    confirmed: list = []
    queued: list = []
    for g in scribe_open_groups or []:
        gid = g.get("id")
        # Prefer stored magic_number; fall back to base+id for legacy rows
        exp_magic = g.get("magic_number")
        if exp_magic is not None:
            exp_magic = int(exp_magic)
        else:
            try:
                exp_magic = forge_magic_base + int(gid)
            except (TypeError, ValueError):
                queued.append(g)
                continue
        if exp_magic in magics:
            confirmed.append(g)
        else:
            queued.append(g)
    return confirmed, queued


TV_KEYS = (
    "rsi", "macd_hist", "bb_rating", "bb_upper", "bb_mid", "bb_lower",
    "bb_width", "bb_squeeze", "adx", "di_plus", "di_minus",
    "dmi_present", "dmi_study",
    "order_block_present", "order_block_study", "order_block_values",
    "ema_20", "ema_50", "tv_recommend", "tv_recommend_source",
    "tv_brief", "tv_brief_source", "tv_brief_timestamp",
    "timeframe", "timestamp", "age_seconds", "mode",
)


def _build_tradingview_panel(lens_raw: dict) -> dict:
    """Indicators + TV last (FX chart); not the same as broker fill prices."""
    if not isinstance(lens_raw, dict):
        return {"last": None, "timeframe": None, "age_seconds": None}
    out = {k: lens_raw.get(k) for k in TV_KEYS}
    out["last"] = safe_float(lens_raw.get("price"))
    return out


def _build_lens_backward_compat(lens_raw: dict, execution: dict, tv: dict) -> dict:
    """Flat lens dict for AURUM/tests; bid/ask omitted when MT5 file is stale."""
    lens = dict(lens_raw) if isinstance(lens_raw, dict) else {}
    tv_last = tv.get("last")
    if tv_last is not None:
        lens["tradingview_close"] = tv_last
    if execution.get("usable"):
        lens["bid"] = execution.get("bid")
        lens["ask"] = execution.get("ask")
        lens["mt5_bid"] = execution.get("bid")
        lens["mt5_ask"] = execution.get("ask")
        lens["spread_usd"] = execution.get("spread_usd")
        lens["spread_points"] = execution.get("spread_points")
        lens["quote_mid"] = execution.get("mid")
        lens["price"] = execution.get("mid")
        lens["mt5_symbol"] = execution.get("symbol")
        lens["mt5_quote_stale"] = False
        mid = execution.get("mid")
        if mid is not None and tv_last is not None and abs(float(tv_last) - float(mid)) > 2.0:
            lens["tv_price_mismatch"] = True
        else:
            lens["tv_price_mismatch"] = False
    else:
        lens["bid"] = None
        lens["ask"] = None
        lens["mt5_bid"] = execution.get("bid")
        lens["mt5_ask"] = execution.get("ask")
        lens["spread_usd"] = execution.get("spread_usd")
        lens["spread_points"] = execution.get("spread_points")
        lens["quote_mid"] = execution.get("mid")
        lens["price"] = tv_last
        lens["mt5_symbol"] = execution.get("symbol")
        lens["mt5_quote_stale"] = True
        b = execution.get("bid")
        lens["tv_price_mismatch"] = bool(
            b is not None and tv_last is not None and abs(float(tv_last) - float(b)) > 2.0
        )
    return lens


# ── Live data endpoint ─────────────────────────────────────────────
@app.route("/api/live")
def api_live():
    mt5       = _read_json(MARKET_FILE)
    status    = _read_json(STATUS_FILE)
    lens_raw  = _read_json(LENS_FILE)
    execution = build_execution_quote(mt5)
    tradingview = _build_tradingview_panel(lens_raw)
    chart_symbol = execution.get("symbol")
    mid_ex = execution.get("mid")
    tv_last = tradingview.get("last")
    if (
        execution.get("usable")
        and mid_ex is not None
        and tv_last is not None
        and abs(float(tv_last) - float(mid_ex)) > 2.0
    ):
        tradingview["divergence_from_mt5_usd"] = round(float(tv_last) - float(mid_ex), 2)
    lens = _build_lens_backward_compat(lens_raw, execution, tradingview)
    sentinel = _read_json(SENTINEL_FILE)
    broker   = _read_json(BROKER_FILE)
    recon    = _read_json(RECON_FILE)
    scribe   = get_scribe()

    # AEGIS scale state
    aegis_state = {"streak": 0, "streak_type": "NONE",
                   "scale_factor": 1, "scale_reason": "UNKNOWN", "session_pnl": 0,
                   "pnl_day_reset_hour_utc": trading_day_reset_hour_utc()}
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
            "pnl_day_reset_hour_utc": trading_day_reset_hour_utc(),
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

    scribe_open_all = scribe.get_open_groups()
    _forge_magic = int(os.environ.get("FORGE_MAGIC_NUMBER", str(FORGE_MAGIC_NUMBER_DEFAULT)))
    open_groups_confirmed, open_groups_queued = partition_open_groups_for_athena(
        scribe_open_all, mt5, _forge_magic
    )

    return jsonify({
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "mode":            status.get("mode", "UNKNOWN"),
        "effective_mode":  status.get("effective_mode", "UNKNOWN"),
        "session":         status.get("session", "OFF_HOURS"),
        "session_utc":     get_trading_session_utc(),
        "session_id":      status.get("session_id"),
        "cycle":           status.get("cycle", 0),
        "version":         status.get("version", "1.1.0"),

        # Safety state
        "sentinel_active":   status.get("sentinel_active", False),
        "circuit_breaker":   status.get("circuit_breaker", False),
        "mt5_fresh":         status.get("mt5_fresh", False),
        "mt5_quote_stale":   execution.get("stale", True),

        # Broker / account identity
        "account_type": broker.get("account_type", "UNKNOWN"),
        "broker":       broker.get("broker", ""),
        "server":       broker.get("server", ""),
        "currency":     broker.get("currency", "USD"),
        "leverage":     broker.get("leverage"),

        # Live account data from MT5
        "account":  mt5.get("account", {}),
        "price":    mt5.get("price", {}),
        "chart_symbol": chart_symbol,
        "indicators_h1": mt5.get("indicators_h1", {}),
        "open_positions": mt5.get("open_positions", []),
        "pending_orders": mt5.get("pending_orders", []),
        "pending_orders_forge_count": mt5.get("pending_orders_forge_count"),
        "mt5_connected":  bool(mt5),
        "forge_version":  mt5.get("forge_version"),
        "ea_cycle":       mt5.get("ea_cycle"),

        # Structured quote + research (dashboard should prefer these over flat lens)
        "execution":    execution,
        "tradingview":  tradingview,

        # LENS (backward compatible flat view for AURUM / older clients)
        "lens": lens,

        # SENTINEL
        "sentinel": sentinel,

        # Open trade groups — tiles: MT5-confirmed only (avoids false positive right after BRIDGE logs)
        "open_groups": open_groups_confirmed,
        "open_groups_queued": open_groups_queued,
        "open_groups_policy": (
            "open_groups are SCRIBE rows with status OPEN/PARTIAL whose FORGE magic "
            "(FORGE_MAGIC_NUMBER + group id) appears in MT5 open_positions or pending_orders. "
            "open_groups_queued holds SCRIBE-only rows still waiting on the broker file."
        ),

        # Closed-trade stats (SCRIBE) — same rolling window as dashboard perf + P&L curve
        "performance": scribe.get_performance(days=7),
        "performance_window": {
            "days": 7,
            "label": "Rolling 7 days (UTC), status=CLOSED in SCRIBE",
        },

        # Recent closures (SL/TP hits) for real-time dashboard display
        "recent_closures": scribe.get_recent_closures(limit=5, days=1),
        "closure_stats": scribe.get_closure_stats(days=7),

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

# ── TradingView brief endpoint ─────────────────────────────────────
@app.route("/api/brief")
def api_brief():
    brief = _read_json(LENS_BRIEF_FILE)
    if not brief:
        return jsonify({
            "status": "UNAVAILABLE",
            "message": "No TradingView brief has been captured yet.",
        }), 404
    return jsonify(brief)

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


@app.route("/api/components/heartbeat", methods=["GET", "POST"])
def api_components_heartbeat():
    """
    POST: ingest a component heartbeat (same persistence as internal reporters).
    GET: JSON help — browsers open this URL with GET and would otherwise see an empty/error page.
    """
    if request.method == "GET":
        return jsonify({
            "message": "POST JSON here to record a component heartbeat (GET is documentation only).",
            "post_url": "/api/components/heartbeat",
            "content_type": "application/json",
            "swagger_ui": "/api/docs/",
            "example_body": {
                "component": "BRIDGE",
                "status": "OK",
                "note": "optional human note",
            },
            "allowed_components": sorted(KNOWN_COMPONENTS),
            "optional_fields": [
                "mode", "note", "last_action", "error_msg", "session", "cycle",
            ],
        })

    data = request.get_json(silent=True) or {}
    comp = (data.get("component") or "").strip().upper()
    if comp not in KNOWN_COMPONENTS:
        return jsonify({
            "error": "unknown component",
            "allowed": sorted(KNOWN_COMPONENTS),
        }), 400
    status = (data.get("status") or "OK").strip().upper() or "OK"
    if status not in ("OK", "WARN", "ERROR", "UNKNOWN"):
        status = "OK"

    mode = data.get("mode")
    note = data.get("note")
    last_action = data.get("last_action")
    error_msg = data.get("error_msg")
    session = data.get("session")
    cycle = data.get("cycle", 0)
    try:
        cycle = int(cycle)
    except (TypeError, ValueError):
        cycle = 0

    scribe = get_scribe()
    scribe.heartbeat(
        component=comp,
        status=status,
        mode=mode,
        note=note,
        last_action=last_action,
        error_msg=error_msg,
        cycle=cycle,
        session=session,
    )
    return jsonify({"ok": True, "component": comp, "timestamp": datetime.now(timezone.utc).isoformat()})


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


# ── Mode read / switch ─────────────────────────────────────────────
@app.route("/api/management", methods=["POST"])
def api_management():
    """
    Queue CLOSE_ALL / MOVE_BE / CLOSE_PCT for BRIDGE → FORGE (same file as Telegram LISTENER).
    BRIDGE reads config/management_cmd.json every tick (all modes).
    """
    data = request.get_json(silent=True) or {}
    intent = (data.get("intent") or "").upper().replace(" ", "_")
    # Accept "CLOSE 70%" style from UI
    if intent == "CLOSE_70%":
        intent = "CLOSE_PCT"
    valid_intents = ("CLOSE_ALL", "MOVE_BE", "CLOSE_PCT", "MODIFY_SL", "MODIFY_TP",
                     "CLOSE_GROUP", "CLOSE_GROUP_PCT", "CLOSE_PROFITABLE", "CLOSE_LOSING")
    if intent not in valid_intents:
        return jsonify({"error": f"intent must be one of {valid_intents}"}), 400
    pct = data.get("pct")
    if intent == "CLOSE_PCT":
        try:
            pct = float(pct if pct is not None else 70)
        except (TypeError, ValueError):
            pct = 70.0
        if pct <= 0 or pct > 100:
            return jsonify({"error": "pct must be between 0 and 100"}), 400
    group_id = data.get("group_id")
    sl_price = data.get("sl")
    tp_price = data.get("tp")
    body = {
        "type":     "MANAGEMENT",
        "intent":   intent,
        "pct":      pct if intent in ("CLOSE_PCT", "CLOSE_GROUP_PCT") else None,
        "group_id": int(group_id) if group_id else None,
        "sl":       float(sl_price) if sl_price else None,
        "tp":       float(tp_price) if tp_price else None,
        "tp_stage": None,
        "source":   "ATHENA",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(MGMT_FILE, "w") as f:
            json.dump(body, f, indent=2)
    except Exception as e:
        log.error("api_management write failed: %s", e)
        return jsonify({"error": str(e)}), 500
    return jsonify({
        "ok": True,
        "intent": intent,
        "pct": body["pct"],
        "file": MGMT_FILE,
        "hint": "BRIDGE picks this up on the next tick (~5s) and writes MT5/command.json for FORGE.",
    })


@app.route("/api/mode", methods=["GET", "POST"])
def api_mode():
    """
    GET: current mode from bridge status file (same source as /api/live mode fields).
    POST: queue MODE_CHANGE by writing aurum_cmd.json for BRIDGE (does not toggle inside Flask).
    """
    if request.method == "GET":
        status = _read_json(STATUS_FILE)
        pinned_mode = (os.environ.get("BRIDGE_PIN_MODE") or "").upper().strip() or None
        return jsonify({
            "mode":           status.get("mode", "UNKNOWN"),
            "effective_mode": status.get("effective_mode", "UNKNOWN"),
            "requested_mode": status.get("requested_mode"),
            "mode_pin":       pinned_mode,
            "timestamp":      status.get("timestamp"),
            "session":        status.get("session"),
            "session_id":     status.get("session_id"),
            "cycle":          status.get("cycle", 0),
            "hint": (
                "POST JSON {\"mode\":\"WATCH\"} (OFF|WATCH|SIGNAL|SCALPER|HYBRID) to queue "
                "MODE_CHANGE via aurum_cmd.json for BRIDGE."
            ),
        })

    data = request.json or {}
    new_mode = data.get("mode", "").upper()
    if new_mode not in ("OFF","WATCH","SIGNAL","SCALPER","HYBRID","AUTO_SCALPER"):
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
        # Do NOT force mode/effective_mode here — BRIDGE is source-of-truth.
        # Record requested_mode for operator visibility until BRIDGE applies/blocks it.
        try:
            status = _read_json(STATUS_FILE)
            status["requested_mode"] = new_mode
            with open(STATUS_FILE, "w") as f:
                json.dump(status, f, indent=2)
        except Exception:
            pass
        pinned_mode = (os.environ.get("BRIDGE_PIN_MODE") or "").upper().strip() or None
        return jsonify({
            "ok": True,
            "new_mode": new_mode,
            "queued": True,
            "mode_pin": pinned_mode,
            "hint": "BRIDGE applies this on next loop tick; if mode pin is active, non-pinned requests are blocked."
        })
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


# ── Sentinel override ───────────────────────────────────
@app.route("/api/sentinel/override", methods=["POST"])
def api_sentinel_override():
    """Temporarily bypass sentinel news guard. Auto-reverts after SENTINEL_OVERRIDE_DURATION_SEC."""
    import time as _time
    duration = int(os.environ.get("SENTINEL_OVERRIDE_DURATION_SEC", "600"))
    data = request.get_json(silent=True) or {}
    if data.get("duration"):
        duration = max(60, min(int(data["duration"]), 3600))  # 1min to 1hr
    # Write override command for BRIDGE
    cmd = {
        "action": "SENTINEL_OVERRIDE",
        "duration": duration,
        "reason": data.get("reason", "manual override from ATHENA"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        aurum_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            os.environ.get("AURUM_CMD_FILE", "config/aurum_cmd.json")
        )
        with open(aurum_path, "w") as f:
            json.dump(cmd, f, indent=2)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({
        "ok": True,
        "duration": duration,
        "reverts_at": (datetime.now(timezone.utc) + __import__('datetime').timedelta(seconds=duration)).isoformat(),
        "hint": f"Sentinel bypassed for {duration}s. Trading allowed during news. Auto-reverts.",
    })


@app.route("/api/sentinel/digest", methods=["POST"])
def api_sentinel_digest():
    """Override sentinel event digest interval (for testing). Reverts on next restart."""
    data = request.get_json(silent=True) or {}
    interval = data.get("interval", 60)
    interval = max(30, min(int(interval), 3600))
    # Write to a file that BRIDGE/SENTINEL can pick up
    digest_file = os.path.join(_HERE, "config", "sentinel_digest_override.json")
    try:
        with open(digest_file, "w") as f:
            json.dump({"interval": interval, "timestamp": datetime.now(timezone.utc).isoformat()}, f)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "interval": interval,
                    "hint": f"Digest interval set to {interval}s. Reverts on restart."})


# ── Channel messages (cached by LISTENER) ─────────────────
@app.route("/api/channels/messages")
def api_channel_messages():
    """Recent messages from configured Telegram channels (cached by LISTENER every 5min)."""
    msgs_file = os.path.join(_HERE, "config", "channel_messages.json")
    names_file = os.path.join(_HERE, "config", "channel_names.json")
    messages = _read_json(msgs_file)
    names = _read_json(names_file)
    result = []
    for ch_id, msgs in messages.items():
        result.append({
            "id": ch_id,
            "name": names.get(ch_id, f"channel_{ch_id}"),
            "messages": msgs,
        })
    return jsonify({"channels": result})


# ── Configured signal channels ────────────────────────────
@app.route("/api/channels")
def api_channels():
    """Return configured Telegram channels with names and recent signal counts."""
    scribe = get_scribe()
    # Get channel names + counts from SCRIBE signal history
    rows = scribe.query(
        """SELECT channel_name, COUNT(*) as total,
               MAX(timestamp) as last_signal,
               SUM(CASE WHEN action_taken='EXECUTED' THEN 1 ELSE 0 END) as executed,
               SUM(CASE WHEN action_taken='SKIPPED' THEN 1 ELSE 0 END) as skipped,
               SUM(CASE WHEN action_taken='LOGGED_ONLY' THEN 1 ELSE 0 END) as logged_only
           FROM signals_received
           WHERE channel_name IS NOT NULL
           GROUP BY channel_name
           ORDER BY last_signal DESC"""
    )
    # Configured channel IDs from env
    raw_ids = os.environ.get("TELEGRAM_CHANNELS", "").split(",")
    configured = [c.strip() for c in raw_ids if c.strip()]

    # Merge Telethon-resolved names (written by LISTENER on connect)
    names_file = os.path.join(_HERE, "config", "channel_names.json")
    resolved_names = _read_json(names_file)

    # Build full channel list: known names + SCRIBE stats
    scribe_map = {r["channel_name"]: r for r in rows}
    all_channels = []
    for cid in configured:
        name = resolved_names.get(cid, resolved_names.get(str(cid)))
        stats = scribe_map.get(name, {})
        all_channels.append({
            "id": cid,
            "name": name or f"channel_{cid}",
            "total_signals": stats.get("total", 0),
            "executed": stats.get("executed", 0),
            "skipped": stats.get("skipped", 0),
            "logged_only": stats.get("logged_only", 0),
            "last_signal": stats.get("last_signal"),
        })

    return jsonify({
        "configured_ids": configured,
        "channels": all_channels,
        "total_configured": len(configured),
    })


# ── Signal room / channel performance ─────────────────────
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


# ── Signal parser test ─────────────────────────────────────
@app.route("/api/signals/parse", methods=["POST"])
def api_signals_parse():
    """Test the Claude Haiku signal parser without Telegram. POST {"text": "SELL Gold @4691..."}."""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "provide 'text' field with the message to parse"}), 400
    try:
        import asyncio
        from listener import Listener
        l = Listener()
        result = asyncio.run(l.test_parse(text))
        return jsonify({"input": text[:200], "parsed": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Signal history ─────────────────────────────────────────
@app.route("/api/signals")
def api_signals():
    limit = int(request.args.get("limit", 20))
    days_raw = request.args.get("days")
    session_filter = request.args.get("session", "").strip().lower()
    stats_flag = request.args.get("stats", "0") == "1"
    scribe = get_scribe()
    # session=current → only signals from the active trading session
    if session_filter == "current":
        since = scribe.get_current_session_start()
        signals = scribe.get_recent_signals(limit=limit, since=since)
    elif days_raw is not None:
        d = max(1, min(int(days_raw), 366))
        signals = scribe.get_recent_signals(limit=limit, within_days=d)
    else:
        signals = scribe.get_recent_signals(limit=limit, within_days=None)
    if stats_flag:
        d_stats = max(1, min(int(days_raw or 7), 366))
        return jsonify({
            "signals": signals,
            "stats": scribe.get_signals_stats(days=d_stats),
        })
    return jsonify(signals)


# ── Trade closures (SL/TP hits) ───────────────────────────────────
@app.route("/api/closures")
def api_closures():
    """Recent trade closures with SL/TP reason."""
    limit = max(1, min(int(request.args.get("limit", 50)), 500))
    days = max(1, min(int(request.args.get("days", 7)), 366))
    scribe = get_scribe()
    return jsonify(scribe.get_recent_closures(limit=limit, days=days))


@app.route("/api/closure_stats")
def api_closure_stats():
    """Aggregated SL vs TP hit rates."""
    days = max(1, min(int(request.args.get("days", 7)), 366))
    scribe = get_scribe()
    return jsonify(scribe.get_closure_stats(days=days))


# ── Performance data ─────────────────────────────────────────────
@app.route("/api/performance")
def api_performance():
    days = int(request.args.get("days", 7))
    mode = request.args.get("mode", None)
    scribe = get_scribe()
    return jsonify(scribe.get_performance(mode=mode, days=days))


# ── P&L curve for chart ────────────────────────────────────────────
@app.route("/api/pnl_curve")
def api_pnl_curve():
    days = max(1, min(int(request.args.get("days", 1)), 366))
    scribe = get_scribe()
    rows = scribe.query(
        """
        SELECT close_time, SUM(pnl) OVER (ORDER BY close_time) AS cumulative
        FROM trade_positions
        WHERE status='CLOSED'
          AND close_time >= datetime('now', '-' || ? || ' days')
        ORDER BY close_time
        """,
        (str(days),),
    )
    return jsonify(rows)


# ── SCRIBE query (for AURUM / power users) ─────────────────────────
@app.route("/api/scribe/query", methods=["POST"])
def api_scribe_query():
    if SCRIBE_QUERY_SECRET:
        auth = (request.headers.get("Authorization") or "").strip()
        hdr = (request.headers.get("X-ATHENA-SCRIBE-TOKEN") or "").strip()
        token_ok = hdr == SCRIBE_QUERY_SECRET
        bearer_ok = auth.startswith("Bearer ") and auth[7:].strip() == SCRIBE_QUERY_SECRET
        if not (token_ok or bearer_ok):
            return jsonify({"error": "unauthorized"}), 401

    data = request.json or {}
    sql  = data.get("sql", "")
    # Only allow SELECT
    if not sql.strip().upper().startswith("SELECT"):
        return jsonify({"error": "only SELECT allowed"}), 400
    try:
        scribe = get_scribe()
        rows, truncated = scribe.query_limited(
            sql,
            max_rows=SCRIBE_QUERY_MAX_ROWS,
            busy_timeout_ms=SCRIBE_QUERY_BUSY_MS,
        )
        return jsonify({
            "rows": rows,
            "count": len(rows),
            "truncated": truncated,
            "max_rows": SCRIBE_QUERY_MAX_ROWS,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── System events log ──────────────────────────────────────────────
@app.route("/api/events")
def api_events():
    limit = max(1, min(int(request.args.get("limit", 200)), 2000))
    scribe = get_scribe()
    rows = scribe.query(
        "SELECT * FROM system_events ORDER BY timestamp DESC LIMIT ?", (limit,))
    return jsonify(rows)


@app.route("/api/events/export")
def api_events_export():
    """NDJSON download for auditors (newest-first chunk, emitted oldest-first within chunk)."""
    limit = max(1, min(int(request.args.get("limit", 5000)), 50000))
    scribe = get_scribe()
    rows = scribe.query(
        "SELECT * FROM system_events ORDER BY timestamp DESC LIMIT ?", (limit,))

    def lines():
        for row in reversed(rows):
            yield json.dumps(row, ensure_ascii=False, default=str) + "\n"

    return Response(
        lines(),
        mimetype="application/x-ndjson",
        headers={
            "Content-Disposition": 'attachment; filename="system_events.ndjson"',
            "Cache-Control": "no-store",
        },
    )


# ── OpenAPI (Swagger) document ─────────────────────────────────────
@app.route("/api/openapi.yaml")
def api_openapi_yaml():
    """Machine-readable HTTP API contract for editors, codegen, and Swagger UI."""
    try:
        with open(OPENAPI_YAML, encoding="utf-8") as f:
            body = f.read()
    except OSError:
        return jsonify({"error": "OpenAPI spec not found", "path": OPENAPI_YAML}), 404
    return Response(
        body,
        mimetype="application/vnd.oai.openapi; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


# ── Web search (reusable — Google CSE) ─────────────────────────────
@app.route("/api/search")
def api_search():
    """On-demand web search. GET /api/search?q=trump+speaking&n=5"""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "missing ?q= parameter"}), 400
    n = max(1, min(int(request.args.get("n", "5")), 10))
    try:
        from web_search import search
        result = search(q, num_results=n)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


# ── Health check ───────────────────────────────────────────
@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mt5_connected": bool(_read_json(MARKET_FILE)),
        "bridge_running": bool(_read_json(STATUS_FILE)),
        "session_utc": get_trading_session_utc(),
        "pnl_day_reset_hour_utc": trading_day_reset_hour_utc(),
        # Live caps for POST /api/scribe/query — missing on stale ATHENA processes (restart after pull).
        "scribe_query": {
            "max_rows": SCRIBE_QUERY_MAX_ROWS,
            "busy_timeout_ms": SCRIBE_QUERY_BUSY_MS,
            "auth_required": bool(SCRIBE_QUERY_SECRET),
        },
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
