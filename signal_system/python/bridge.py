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

log = logging.getLogger("bridge")

# ── Config ──────────────────────────────────────────────────────────
LOOP_INTERVAL   = int(os.environ.get("BRIDGE_LOOP_SEC",     "5"))
LENS_INTERVAL   = int(os.environ.get("BRIDGE_LENS_SEC",     "300"))  # 5 min
SENTINEL_INTERVAL = int(os.environ.get("BRIDGE_SENTINEL_SEC","60"))
MT5_STALE_SEC   = int(os.environ.get("BRIDGE_MT5_STALE",    "120"))

STATUS_FILE     = os.environ.get("BRIDGE_STATUS_FILE", "config/status.json")
CMD_FILE_MT5    = os.environ.get("MT5_CMD_FILE",        "MT5/command.json")
CFG_FILE_MT5    = os.environ.get("MT5_CONFIG_FILE",     "MT5/config.json")
MARKET_FILE     = os.environ.get("MT5_MARKET_FILE",     "MT5/market_data.json")
SIGNAL_FILE     = os.environ.get("LISTENER_SIGNAL_FILE","config/parsed_signal.json")
MGMT_FILE       = os.environ.get("LISTENER_MGMT_FILE",  "config/management_cmd.json")
SENTINEL_FILE   = os.environ.get("SENTINEL_STATUS_FILE","config/sentinel_status.json")
AURUM_CMD_FILE  = os.environ.get("AURUM_CMD_FILE",      "config/aurum_cmd.json")

# TP close percentages
TP1_CLOSE_PCT   = float(os.environ.get("TP1_CLOSE_PCT", "70"))
TP2_CLOSE_PCT   = float(os.environ.get("TP2_CLOSE_PCT", "20"))
MOVE_BE_ON_TP1  = os.environ.get("MOVE_BE_ON_TP1", "true").lower() == "true"

BROKER_INFO_FILE = os.environ.get("MT5_BROKER_FILE",    "MT5/broker_info.json")

# Session boundaries in UTC hours
# Default: US-based trader, day starts at Asian open (01:00 UTC)
SESSIONS = {
    "ASIAN":      (int(os.environ.get("SESSION_ASIAN_START",    "1")),
                   int(os.environ.get("SESSION_ASIAN_END",       "8"))),
    "LONDON":     (int(os.environ.get("SESSION_LONDON_START",   "8")),
                   int(os.environ.get("SESSION_LONDON_END",     "13"))),
    "LONDON_NY":  (int(os.environ.get("SESSION_LONDON_NY_START","13")),
                   int(os.environ.get("SESSION_LONDON_NY_END",  "17"))),
    "NEW_YORK":   (int(os.environ.get("SESSION_NY_START",       "17")),
                   int(os.environ.get("SESSION_NY_END",         "22"))),
}
VERSION     = "1.1.0"
VALID_MODES = ("OFF", "WATCH", "SIGNAL", "SCALPER", "HYBRID")

for d in ("MT5","config","data","logs"):
    Path(d).mkdir(parents=True, exist_ok=True)


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

def _session() -> str:
    """Return current session name based on UTC hour and configured boundaries."""
    h = datetime.now(timezone.utc).hour
    for name, (start, end) in SESSIONS.items():
        if start <= h < end:
            return name
    return "OFF_HOURS"


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

        self._mode               = os.environ.get("DEFAULT_MODE", "SIGNAL")
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
        # Session tracking
        self._current_session    = "OFF_HOURS"
        self._current_session_id = None    # SCRIBE trading_sessions row id
        self._broker_info        = {}      # from FORGE broker_info.json

    # ── Main loop ─────────────────────────────────────────────────
    def run(self):
        # Check if FORGE has requested a specific startup mode
        broker_info = _read_json(BROKER_INFO_FILE)
        if broker_info:
            self._broker_info = broker_info
            requested = broker_info.get("requested_mode","").upper()
            if requested in VALID_MODES:
                env_mode = os.environ.get("DEFAULT_MODE","WATCH").upper()
                if requested != env_mode:
                    log.info(f"BRIDGE: FORGE requested mode '{requested}' "
                             f"(overrides .env DEFAULT_MODE='{env_mode}')")
                self._mode = requested

        log.info(f"BRIDGE v{VERSION} starting — mode={self._mode} "
                 f"account={self._broker_info.get('account_type','?')} "
                 f"broker={self._broker_info.get('broker','?')}")
        self.scribe.log_system_event("STARTUP", new_mode=self._mode,
                                      triggered_by="USER")
        self.herald.system_start(self._mode, VERSION)
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

        # ── 1. SENTINEL check ─────────────────────────────────────
        if now - self._last_sentinel_ts > SENTINEL_INTERVAL:
            sent_status = self.sentinel.check(self._effective_mode())
            self._last_sentinel_ts = now
            if sent_status["block_trading"] and not self._sentinel_override:
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

        # ── 5. AURUM command check ────────────────────────────────
        self._check_aurum_command()

        # ── 6. Mode-specific logic ────────────────────────────────
        mode = self._effective_mode()

        if mode == "OFF":
            self._write_status(mt5)
            return

        if mode == "WATCH":
            # Just update status, FORGE records ticks itself
            self._write_status(mt5)
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
            self._process_mgmt_command(mt5)

        # ── 6. Scalper mode — LENS-driven own entry ───────────────
        if mode in ("SCALPER", "HYBRID") and lens_snap:
            self._scalper_logic(mt5, lens_snap)

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

        # AEGIS validation
        account = mt5.get("account", {}) if mt5 else {}
        account["open_groups_count"] = len(self._open_groups)
        current_price = mt5.get("price", {}).get("bid") if mt5 else None

        approval = self.aegis.validate(signal, account, current_price)

        if not approval.approved:
            log.warning(f"BRIDGE: Signal REJECTED — {approval.reject_reason}")
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

        group_id = self.scribe.log_trade_group(group_data, self._effective_mode())
        self._open_groups[group_id] = group_data
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
        _write_json(CMD_FILE_MT5, cmd)
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

        cmd = None
        if intent == "CLOSE_ALL":
            cmd = {"action": "CLOSE_ALL", "timestamp": _now()}
            # Close all open groups in SCRIBE
            for gid in list(self._open_groups.keys()):
                self.scribe.update_trade_group(gid, "CLOSED_ALL",
                                               close_reason="SIGNAL_CLOSE_ALL")
            self._open_groups.clear()

        elif intent == "MOVE_BE":
            cmd = {"action": "MOVE_BE_ALL", "timestamp": _now()}

        elif intent == "CLOSE_PCT":
            pct = mgmt.get("pct", TP1_CLOSE_PCT)
            cmd = {"action": "CLOSE_PCT", "pct": pct, "timestamp": _now()}

        if cmd:
            _write_json(CMD_FILE_MT5, cmd)

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
        approval = self.aegis.validate(signal, account, price)
        if approval.approved:
            group_data = {**signal, "lot_per_trade": approval.lot_per_trade,
                          "num_trades": approval.num_trades,
                          "risk_pct": approval.risk_pct,
                          "account_balance": account.get("balance",0),
                          "source": "SCALPER"}
            gid = self.scribe.log_trade_group(group_data, "SCALPER")
            self._open_groups[gid] = group_data
            cmd = {"action":"OPEN_GROUP","group_id":gid,"direction":direction,
                   "entry_ladder":approval.entry_ladder,
                   "lot_per_trade":approval.lot_per_trade,
                   "sl":sl,"tp1":tp1,"tp2":None,"tp3":None,
                   "tp1_close_pct":TP1_CLOSE_PCT,
                   "move_be_on_tp1":MOVE_BE_ON_TP1,
                   "timestamp":_now()}
            _write_json(CMD_FILE_MT5, cmd)

    # ── AURUM command processing ───────────────────────────────────
    def _check_aurum_command(self):
        cmd = _read_json(AURUM_CMD_FILE)
        if not cmd:
            return
        action = cmd.get("action")
        ts     = cmd.get("timestamp")
        if not action or ts == getattr(self, "_last_aurum_ts", None):
            return
        self._last_aurum_ts = ts

        if action == "MODE_CHANGE":
            new_mode = cmd.get("new_mode")
            if new_mode in VALID_MODES:
                self._change_mode(new_mode, "AURUM")

        elif action == "CLOSE_ALL":
            _write_json(CMD_FILE_MT5, {"action":"CLOSE_ALL","timestamp":_now()})
            log.info("BRIDGE: AURUM requested CLOSE_ALL")

        # Clear command after processing
        try:
            import os as _os
            _os.remove(AURUM_CMD_FILE)
        except:
            pass

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
    def _write_config(self):
        """Write config.json for FORGE to read."""
        _write_json(CFG_FILE_MT5, {
            "mode":            self._mode,
            "effective_mode":  self._effective_mode(),
            "sentinel_active": self._sentinel_override,
            "tp1_close_pct":   TP1_CLOSE_PCT,
            "tp2_close_pct":   TP2_CLOSE_PCT,
            "move_be_on_tp1":  MOVE_BE_ON_TP1,
            "timestamp":       _now(),
        })

    def _write_status(self, mt5: dict = None, lens_snap=None):
        """Write status.json for ATHENA + AURUM."""
        acc = (mt5 or {}).get("account", {})
        sent = _read_json(SENTINEL_FILE) if not hasattr(self, '_sent_cache') else {}
        _write_json(STATUS_FILE, {
            "mode":              self._mode,
            "effective_mode":    self._effective_mode(),
            "sentinel_active":   self._sentinel_override,
            "circuit_breaker":   self._mt5_blind_override,
            "mt5_fresh":         mt5_fresh if 'mt5_fresh' in dir() else False,
            "session":           self._current_session,
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
            self.scribe.heartbeat(
                component   = "BRIDGE",
                status      = "WARN" if self._mt5_blind_override else "OK",
                mode        = self._mode,
                session     = self._current_session,
                note        = f"Cycle {self._cycle} effective={self._effective_mode()}",
                last_action = f"session={self._current_session} groups={len(self._open_groups)}",
                error_msg   = "MT5 data stale" if self._mt5_blind_override else None,
                cycle       = self._cycle,
            )
        except Exception as e:
            log.debug(f"BRIDGE heartbeat error: {e}")


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
    if args.mode:
        bridge._mode = args.mode

    bridge.run()
