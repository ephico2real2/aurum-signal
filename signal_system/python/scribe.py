"""
scribe.py — SCRIBE Intelligence Data Logger
============================================
Build order: #1 — no dependencies, pure Python stdlib.
Every component imports and calls Scribe.  All records carry mode + timestamp.
"""

import sqlite3, os, json, logging
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager

log = logging.getLogger("scribe")

DB_PATH = os.environ.get("SCRIBE_DB", "data/aurum_intelligence.db")
_PY_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PY_DIR.parent
_DEFAULT_AUDIT_JSONL = _REPO_ROOT / "logs" / "audit" / "system_events.jsonl"

DDL = """
CREATE TABLE IF NOT EXISTS system_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    prev_mode     TEXT,
    new_mode      TEXT,
    triggered_by  TEXT,
    reason        TEXT,
    news_event    TEXT,
    session       TEXT,
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS trading_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_name    TEXT NOT NULL,
    -- ASIAN | LONDON | LONDON_NY | NEW_YORK | OFF_HOURS
    session_date    TEXT NOT NULL,   -- YYYY-MM-DD (user's local trading date)
    open_time       TEXT NOT NULL,   -- UTC ISO timestamp when session started
    close_time      TEXT,            -- UTC ISO timestamp when session ended
    mode_at_open    TEXT,
    -- Performance (filled when session closes)
    signals_received  INTEGER DEFAULT 0,
    signals_executed  INTEGER DEFAULT 0,
    signals_skipped   INTEGER DEFAULT 0,
    groups_opened     INTEGER DEFAULT 0,
    total_pnl         REAL DEFAULT 0,
    total_pips        REAL DEFAULT 0,
    wins              INTEGER DEFAULT 0,
    losses            INTEGER DEFAULT 0,
    win_rate          REAL DEFAULT 0,
    news_guards       INTEGER DEFAULT 0,
    circuit_breakers  INTEGER DEFAULT 0,
    -- Broker context (from FORGE broker_info.json)
    account_type    TEXT,    -- 'DEMO' or 'LIVE'
    broker          TEXT,
    balance_at_open REAL,
    balance_at_close REAL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    mode            TEXT NOT NULL,
    source          TEXT NOT NULL,
    symbol          TEXT DEFAULT 'XAUUSD',
    bid             REAL, ask REAL, spread REAL,
    open_m1 REAL, high_m1 REAL, low_m1 REAL, close_m1 REAL, volume_m1 REAL,
    rsi_14  REAL, macd_hist REAL, ema_20 REAL, ema_50 REAL,
    bb_upper REAL, bb_mid REAL, bb_lower REAL, bb_width REAL,
    adx REAL, tv_rating INTEGER, timeframe TEXT,
    session TEXT, news_guard_active INTEGER DEFAULT 0,
    outcome_label TEXT, label_filled INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS signals_received (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    mode           TEXT NOT NULL,
    session        TEXT,
    raw_text       TEXT NOT NULL,
    channel_name   TEXT,
    message_id     INTEGER,
    signal_type    TEXT,
    direction      TEXT,
    entry_low      REAL, entry_high REAL,
    sl REAL, tp1 REAL, tp2 REAL, tp3 REAL,
    tp3_open       INTEGER DEFAULT 0,
    mgmt_intent    TEXT,
    mgmt_pct       REAL,
    action_taken   TEXT,
    skip_reason    TEXT,
    trade_group_id INTEGER
);

CREATE TABLE IF NOT EXISTS trade_groups (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    mode           TEXT NOT NULL,
    session        TEXT,
    source         TEXT NOT NULL,
    signal_id      INTEGER,
    direction      TEXT NOT NULL,
    entry_low REAL, entry_high REAL,
    sl REAL, tp1 REAL, tp2 REAL, tp3 REAL,
    num_trades     INTEGER,
    lot_per_trade  REAL,
    risk_pct       REAL,
    scale_factor   REAL DEFAULT 1.0,
    account_balance REAL,
    account_type   TEXT,
    lens_rating    INTEGER,
    lens_rsi       REAL,
    lens_confirmed INTEGER,
    magic_number   INTEGER,
    status         TEXT DEFAULT 'OPEN',
    closed_at      TEXT,
    close_reason   TEXT,
    total_pnl      REAL,
    pips_captured  REAL,
    trades_opened  INTEGER,
    trades_closed  INTEGER
);

CREATE TABLE IF NOT EXISTS trade_positions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_group_id INTEGER NOT NULL,
    timestamp      TEXT NOT NULL,
    mode           TEXT NOT NULL,
    session        TEXT,
    ticket         INTEGER,
    magic_number   INTEGER,
    direction      TEXT,
    lot_size       REAL,
    entry_price    REAL,
    sl REAL, tp REAL,
    status         TEXT DEFAULT 'OPEN',
    close_price    REAL,
    close_time     TEXT,
    close_reason   TEXT,
    pnl            REAL,
    pips           REAL,
    tp_stage       INTEGER
);

CREATE TABLE IF NOT EXISTS news_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    session        TEXT,
    event_name     TEXT,
    impact         TEXT,
    currency       TEXT,
    guard_start    TEXT,
    guard_end      TEXT,
    mode_before    TEXT,
    mode_restored  TEXT,
    market_move_pips REAL
);

CREATE TABLE IF NOT EXISTS aurum_conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    mode        TEXT NOT NULL,
    session     TEXT,
    source      TEXT NOT NULL,
    query       TEXT NOT NULL,
    response    TEXT NOT NULL,
    tokens_used INTEGER
);

CREATE TABLE IF NOT EXISTS component_heartbeats (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    component     TEXT NOT NULL,
    status        TEXT NOT NULL,
    mode          TEXT,
    session       TEXT,
    note          TEXT,
    last_action   TEXT,
    error_msg     TEXT,
    cycle         INTEGER DEFAULT 0
);
"""


class Scribe:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        log.info(f"SCRIBE initialised → {db_path}")

    # ── Internal ───────────────────────────────────────────────────
    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            log.error(f"SCRIBE DB error: {e}")
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as c:
            c.executescript(DDL)
            self._migrate(c)

    def _migrate(self, conn):
        """Additive migrations — safe to re-run."""
        # v1.2.4+: magic_number column on trade_groups
        cols = [r[1] for r in conn.execute("PRAGMA table_info(trade_groups)").fetchall()]
        if "magic_number" not in cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN magic_number INTEGER")
            log.info("SCRIBE migration: added magic_number column to trade_groups")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _audit_mirror_enabled(self) -> bool:
        v = os.environ.get("SCRIBE_AUDIT_ENABLE", "1").strip().lower()
        return v not in ("0", "false", "no", "off")

    def _mirror_system_event_audit(self, row: dict) -> None:
        """Append one NDJSON line for external audit / SIEM (never raises)."""
        if not self._audit_mirror_enabled():
            return
        path = Path(os.environ.get("SCRIBE_AUDIT_JSONL", str(_DEFAULT_AUDIT_JSONL)))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            log.warning("SCRIBE audit mirror write failed: %s", e)

    # ── Public write API ───────────────────────────────────────────
    def log_system_event(self, event_type: str, prev_mode: str = None,
                         new_mode: str = None, triggered_by: str = None,
                         reason: str = None, news_event: str = None,
                         session: str = None, notes: str = None):
        ts = self._now()
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO system_events
                (timestamp,event_type,prev_mode,new_mode,triggered_by,reason,news_event,session,notes)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (ts, event_type, prev_mode, new_mode, triggered_by,
                 reason, news_event, session, notes),
            )
            eid = cur.lastrowid
        self._mirror_system_event_audit({
            "id": eid,
            "timestamp": ts,
            "event_type": event_type,
            "prev_mode": prev_mode,
            "new_mode": new_mode,
            "triggered_by": triggered_by,
            "reason": reason,
            "news_event": news_event,
            "session": session,
            "notes": notes,
        })

    def log_market_snapshot(self, data: dict, mode: str, source: str):
        with self._conn() as c:
            c.execute("""INSERT INTO market_snapshots
                (timestamp,mode,source,symbol,bid,ask,spread,
                 open_m1,high_m1,low_m1,close_m1,volume_m1,
                 rsi_14,macd_hist,ema_20,ema_50,bb_upper,bb_mid,bb_lower,bb_width,
                 adx,tv_rating,timeframe,session,news_guard_active)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self._now(), mode, source,
                 data.get("symbol","XAUUSD"),
                 data.get("bid"), data.get("ask"), data.get("spread"),
                 data.get("open_m1"), data.get("high_m1"),
                 data.get("low_m1"), data.get("close_m1"), data.get("volume_m1"),
                 data.get("rsi_14"), data.get("macd_hist"),
                 data.get("ema_20"), data.get("ema_50"),
                 data.get("bb_upper"), data.get("bb_mid"),
                 data.get("bb_lower"), data.get("bb_width"),
                 data.get("adx"), data.get("tv_rating"),
                 data.get("timeframe","M1"),
                 data.get("session"), int(data.get("news_guard",False))))

    def log_signal(self, raw: str, parsed: dict, mode: str,
                   channel: str = None, msg_id: int = None) -> int:
        with self._conn() as c:
            cur = c.execute("""INSERT INTO signals_received
                (timestamp,mode,raw_text,channel_name,message_id,signal_type,
                 direction,entry_low,entry_high,sl,tp1,tp2,tp3,tp3_open,
                 mgmt_intent,mgmt_pct,action_taken,skip_reason)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self._now(), mode, raw, channel, msg_id,
                 parsed.get("type","ENTRY"),
                 parsed.get("direction"), parsed.get("entry_low"),
                 parsed.get("entry_high"), parsed.get("sl"),
                 parsed.get("tp1"), parsed.get("tp2"), parsed.get("tp3"),
                 int(parsed.get("tp3_open",False)),
                 parsed.get("mgmt_intent"), parsed.get("mgmt_pct"),
                 parsed.get("action","PENDING"), parsed.get("skip_reason")))
            return cur.lastrowid

    def update_signal_action(self, signal_id: int, action: str,
                              skip_reason: str = None, group_id: int = None):
        with self._conn() as c:
            c.execute("""UPDATE signals_received
                SET action_taken=?, skip_reason=?, trade_group_id=?
                WHERE id=?""", (action, skip_reason, group_id, signal_id))

    def log_trade_group(self, data: dict, mode: str,
                        magic_number: int | None = None) -> int:
        with self._conn() as c:
            cur = c.execute("""INSERT INTO trade_groups
                (timestamp,mode,source,signal_id,direction,
                 entry_low,entry_high,sl,tp1,tp2,tp3,
                 num_trades,lot_per_trade,risk_pct,account_balance,
                 lens_rating,lens_rsi,lens_confirmed,
                 magic_number,trades_opened,trades_closed)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self._now(), mode, data.get("source","SIGNAL"),
                 data.get("signal_id"), data.get("direction"),
                 data.get("entry_low"), data.get("entry_high"),
                 data.get("sl"), data.get("tp1"), data.get("tp2"), data.get("tp3"),
                 data.get("num_trades",8), data.get("lot_per_trade"),
                 data.get("risk_pct"), data.get("account_balance"),
                 data.get("lens_rating"), data.get("lens_rsi"),
                 data.get("lens_confirmed"),
                 magic_number,
                 data.get("num_trades",8), 0))
            return cur.lastrowid

    def update_trade_group_magic(self, group_id: int, magic_number: int):
        """Set the magic_number for a trade group (called after SCRIBE assigns the id)."""
        with self._conn() as c:
            c.execute("UPDATE trade_groups SET magic_number=? WHERE id=?",
                      (magic_number, group_id))

    def get_in_use_magics(self) -> set[int]:
        """Return magic numbers of all OPEN/PARTIAL groups."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT magic_number FROM trade_groups "
                "WHERE status IN ('OPEN','PARTIAL') AND magic_number IS NOT NULL"
            ).fetchall()
            return {int(r[0]) for r in rows}

    def update_trade_group(self, group_id: int, status: str,
                           total_pnl: float = None, pips: float = None,
                           trades_closed: int = None, close_reason: str = None):
        with self._conn() as c:
            c.execute("""UPDATE trade_groups SET status=?,total_pnl=?,
                pips_captured=?,trades_closed=?,close_reason=?,
                closed_at=? WHERE id=?""",
                (status, total_pnl, pips, trades_closed, close_reason,
                 self._now() if status not in ("OPEN","PARTIAL") else None,
                 group_id))

    def log_trade_position(self, group_id: int, data: dict, mode: str) -> int:
        with self._conn() as c:
            cur = c.execute("""INSERT INTO trade_positions
                (trade_group_id,timestamp,mode,ticket,magic_number,
                 direction,lot_size,entry_price,sl,tp)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (group_id, self._now(), mode,
                 data.get("ticket"), data.get("magic"),
                 data.get("direction"), data.get("lot_size"),
                 data.get("entry_price"), data.get("sl"), data.get("tp")))
            return cur.lastrowid

    def close_trade_position(self, ticket: int, close_price: float,
                              close_reason: str, pnl: float, pips: float,
                              tp_stage: int = None):
        with self._conn() as c:
            c.execute("""UPDATE trade_positions
                SET status='CLOSED', close_price=?, close_time=?,
                    close_reason=?, pnl=?, pips=?, tp_stage=?
                WHERE ticket=?""",
                (close_price, self._now(), close_reason, pnl, pips, tp_stage, ticket))

    def log_news_event(self, event_name: str, impact: str, currency: str,
                       mode_before: str):
        with self._conn() as c:
            cur = c.execute("""INSERT INTO news_events
                (timestamp,event_name,impact,currency,guard_start,mode_before)
                VALUES (?,?,?,?,?,?)""",
                (self._now(), event_name, impact, currency, self._now(), mode_before))
            return cur.lastrowid

    def close_news_event(self, event_id: int, mode_restored: str,
                          market_move_pips: float = None):
        with self._conn() as c:
            c.execute("""UPDATE news_events
                SET guard_end=?, mode_restored=?, market_move_pips=?
                WHERE id=?""",
                (self._now(), mode_restored, market_move_pips, event_id))

    def log_aurum_conversation(self, query: str, response: str,
                                mode: str, source: str = "TELEGRAM",
                                tokens: int = 0, session: str = None):
        with self._conn() as c:
            c.execute("""INSERT INTO aurum_conversations
                (timestamp,mode,session,source,query,response,tokens_used)
                VALUES (?,?,?,?,?,?,?)""",
                (self._now(), mode, session, source, query, response, tokens))

    # ── Trading session API ────────────────────────────────────────
    def open_trading_session(self, session_name: str, mode: str,
                              account_type: str = None,
                              broker: str = None,
                              balance: float = None) -> int:
        """Open a new trading session record. Returns session id."""
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._conn() as c:
            cur = c.execute("""INSERT INTO trading_sessions
                (session_name, session_date, open_time, mode_at_open,
                 account_type, broker, balance_at_open)
                VALUES (?,?,?,?,?,?,?)""",
                (session_name, today, self._now(), mode,
                 account_type, broker, balance))
            sid = cur.lastrowid
        log.info(f"SCRIBE: trading_session #{sid} opened — {session_name}")
        return sid

    def close_trading_session(self, session_id: int, balance: float = None):
        """Close a session and fill in performance summary."""
        # Query stats for this session
        with self._conn() as c:
            stats = c.execute("""
                SELECT
                    COUNT(*) total_signals,
                    SUM(CASE WHEN action_taken='EXECUTED' THEN 1 ELSE 0 END) executed,
                    SUM(CASE WHEN action_taken='SKIPPED'  THEN 1 ELSE 0 END) skipped
                FROM signals_received
                WHERE timestamp >= (SELECT open_time FROM trading_sessions WHERE id=?)
            """, (session_id,)).fetchone()

            grp = c.execute("""
                SELECT
                    COUNT(*) groups,
                    COALESCE(SUM(total_pnl),0) pnl,
                    COALESCE(SUM(pips_captured),0) pips,
                    SUM(CASE WHEN total_pnl>0 THEN 1 ELSE 0 END) wins,
                    SUM(CASE WHEN total_pnl<0 THEN 1 ELSE 0 END) losses
                FROM trade_groups
                WHERE timestamp >= (SELECT open_time FROM trading_sessions WHERE id=?)
                AND status NOT IN ('OPEN','PARTIAL')
            """, (session_id,)).fetchone()

            guards = c.execute("""
                SELECT COUNT(*) FROM news_events
                WHERE guard_start >= (SELECT open_time FROM trading_sessions WHERE id=?)
            """, (session_id,)).fetchone()

            wins   = grp[3] or 0
            losses = grp[4] or 0
            total  = wins + losses
            wr     = round(wins / total * 100, 1) if total > 0 else 0

            c.execute("""UPDATE trading_sessions SET
                close_time=?, balance_at_close=?,
                signals_received=?, signals_executed=?, signals_skipped=?,
                groups_opened=?, total_pnl=?, total_pips=?,
                wins=?, losses=?, win_rate=?, news_guards=?
                WHERE id=?""",
                (self._now(), balance,
                 stats[0] or 0, stats[1] or 0, stats[2] or 0,
                 grp[0] or 0, grp[1] or 0, grp[2] or 0,
                 wins, losses, wr, guards[0] or 0,
                 session_id))

        log.info(f"SCRIBE: trading_session #{session_id} closed — P&L ${grp[1]:.2f}")

    def get_session_history(self, limit: int = 20) -> list:
        """Return recent trading session records for ATHENA."""
        with self._conn() as c:
            rows = c.execute("""
                SELECT * FROM trading_sessions
                ORDER BY open_time DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_current_session_id(self) -> int | None:
        """Return the ID of the currently open session (no close_time)."""
        with self._conn() as c:
            row = c.execute("""
                SELECT id FROM trading_sessions
                WHERE close_time IS NULL
                ORDER BY open_time DESC LIMIT 1
            """).fetchone()
            return row[0] if row else None

    # ── Read API ───────────────────────────────────────────────────
    def get_today_pnl(self) -> float:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._conn() as c:
            row = c.execute("""SELECT COALESCE(SUM(pnl),0) FROM trade_positions
                WHERE close_time LIKE ? AND status='CLOSED'""",
                (f"{today}%",)).fetchone()
            return float(row[0])

    def get_open_groups(self) -> list:
        with self._conn() as c:
            rows = c.execute("""SELECT * FROM trade_groups
                WHERE status IN ('OPEN','PARTIAL') ORDER BY timestamp DESC""").fetchall()
            return [dict(r) for r in rows]

    def get_recent_signals(self, limit: int = 20, within_days: int = None) -> list:
        with self._conn() as c:
            if within_days is not None:
                d = max(1, min(int(within_days), 366))
                rows = c.execute(
                    """SELECT * FROM signals_received
                       WHERE timestamp >= datetime('now', ?)
                       ORDER BY timestamp DESC LIMIT ?""",
                    (f"-{d} days", limit),
                ).fetchall()
            else:
                rows = c.execute(
                    """SELECT * FROM signals_received
                       ORDER BY timestamp DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def get_signals_stats(self, days: int = 7) -> dict:
        d = max(1, min(int(days), 366))
        with self._conn() as c:
            row = c.execute(
                """SELECT COUNT(*) AS received,
                          COALESCE(SUM(CASE WHEN UPPER(TRIM(COALESCE(action_taken,'')))='EXECUTED'
                              THEN 1 ELSE 0 END),0) AS executed,
                          COALESCE(SUM(CASE WHEN UPPER(TRIM(COALESCE(action_taken,'')))='SKIPPED'
                              THEN 1 ELSE 0 END),0) AS skipped,
                          COALESCE(SUM(CASE WHEN UPPER(TRIM(COALESCE(action_taken,'')))='EXPIRED'
                              THEN 1 ELSE 0 END),0) AS expired
                   FROM signals_received
                   WHERE timestamp >= datetime('now', ?)""",
                (f"-{d} days",),
            ).fetchone()
        return {
            "received": int(row[0] or 0),
            "executed": int(row[1] or 0),
            "skipped": int(row[2] or 0),
            "expired": int(row[3] or 0),
        }

    def get_performance(self, mode: str = None, days: int = 7) -> dict:
        d = max(1, min(int(days), 366))
        with self._conn() as c:
            base = (
                "WHERE close_time >= datetime('now', '-' || ? || ' days') "
                "AND status='CLOSED'"
            )
            params: list = [str(d)]
            if mode:
                base += " AND mode=?"
                params.append(mode)
            rows = c.execute(
                f"""SELECT COUNT(*) total,
                    SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) wins,
                    COALESCE(SUM(pnl),0) total_pnl,
                    COALESCE(AVG(pips),0) avg_pips
                    FROM trade_positions {base}""",
                tuple(params),
            ).fetchone()
            total_n = int(rows[0] or 0)
            wins = int(rows[1] or 0)
            return {
                "total": total_n,
                "wins": wins,
                "win_rate": round(wins / total_n * 100, 1) if total_n else None,
                "total_pnl": round(rows[2] or 0, 2),
                "avg_pips": round(rows[3] or 0, 1),
            }

    def query(self, sql: str, params: tuple = ()) -> list:
        with self._conn() as c:
            rows = c.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def query_limited(
        self,
        sql: str,
        params: tuple = (),
        max_rows: int = 500,
        busy_timeout_ms: int = 5000,
    ) -> tuple[list, bool]:
        """
        Run a SELECT; return at most max_rows rows. truncated=True if more rows existed.
        Sets SQLite busy_timeout on this connection only.
        """
        max_rows = max(1, min(int(max_rows), 50_000))
        busy_timeout_ms = max(0, min(int(busy_timeout_ms), 120_000))
        with self._conn() as c:
            if busy_timeout_ms:
                c.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
            cur = c.execute(sql, params)
            batch = cur.fetchmany(max_rows + 1)
            truncated = len(batch) > max_rows
            batch = batch[:max_rows]
            return [dict(r) for r in batch], truncated

    def export_csv(self, table: str, mode: str = None, path: str = None) -> str:
        import csv
        where = f"WHERE mode='{mode}'" if mode else ""
        out = path or f"data/{table}_{mode or 'all'}.csv"
        with self._conn() as c:
            rows = c.execute(f"SELECT * FROM {table} {where}").fetchall()
        if not rows:
            return out
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(rows[0].keys())
            w.writerows(rows)
        log.info(f"SCRIBE exported {len(rows)} rows → {out}")
        return out

    def heartbeat(self, component: str, status: str = "OK",
                  mode: str = None, note: str = None,
                  last_action: str = None, error_msg: str = None,
                  cycle: int = 0, session: str = None):
        """Upsert current status for a component. One row per component."""
        with self._conn() as c:
            c.execute(
                "DELETE FROM component_heartbeats WHERE component=?",
                (component,))
            c.execute("""INSERT INTO component_heartbeats
                (timestamp,component,status,mode,session,
                 note,last_action,error_msg,cycle)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (self._now(), component, status, mode, session,
                 note, last_action, error_msg, cycle))

    def get_component_heartbeats(self) -> list:
        """Return latest heartbeat for every known component."""
        with self._conn() as c:
            rows = c.execute("""SELECT * FROM component_heartbeats
                ORDER BY component ASC""").fetchall()
            return [dict(r) for r in rows]


# ── Singleton ─────────────────────────────────────────────────────
_instance: Scribe = None

def get_scribe() -> Scribe:
    global _instance
    if _instance is None:
        _instance = Scribe()
    return _instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    s = Scribe("data/test.db")
    s.log_system_event("STARTUP", new_mode="WATCH", triggered_by="USER")
    print("SCRIBE OK — tables created:", s.query("SELECT name FROM sqlite_master WHERE type='table'"))
