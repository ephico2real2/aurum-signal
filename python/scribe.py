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

_PY_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PY_DIR.parent
_DEFAULT_AUDIT_JSONL = _REPO_ROOT / "logs" / "audit" / "system_events.jsonl"
def _resolve_db_path() -> str:
    raw = os.environ.get("SCRIBE_DB", "data/aurum_intelligence.db")
    p = Path(raw)
    if p.is_absolute():
        return str(p)
    return str((_PY_DIR / p).resolve())
DB_PATH = _resolve_db_path()

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
    pending_entry_threshold_points REAL,
    trend_strength_atr_threshold REAL,
    breakout_buffer_points REAL,
    regime_label TEXT,
    regime_confidence REAL,
    regime_model TEXT,
    outcome_label TEXT, label_filled INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS market_regimes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    mode            TEXT,
    session         TEXT,
    symbol          TEXT DEFAULT 'XAUUSD',
    regime_label    TEXT NOT NULL,
    confidence      REAL,
    posterior_json  TEXT,
    model_name      TEXT,
    model_version   TEXT,
    stale           INTEGER DEFAULT 0,
    age_sec         REAL,
    fallback_reason TEXT,
    entry_mode      TEXT,
    apply_entry_policy INTEGER DEFAULT 0,
    entry_gate_reason TEXT,
    feature_hash    TEXT,
    feature_json    TEXT
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
    signal_source_type TEXT DEFAULT 'TEXT',
    vision_extraction_id INTEGER,
    vision_confidence TEXT,
    regime_label    TEXT,
    regime_confidence REAL,
    regime_model    TEXT,
    regime_entry_mode TEXT,
    regime_policy   TEXT,
    regime_fallback_reason TEXT,
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
    pending_entry_threshold_points REAL,
    trend_strength_atr_threshold REAL,
    breakout_buffer_points REAL,
    regime_label    TEXT,
    regime_confidence REAL,
    regime_model    TEXT,
    regime_entry_mode TEXT,
    regime_policy   TEXT,
    regime_fallback_reason TEXT,
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

CREATE TABLE IF NOT EXISTS trade_closures (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    ticket          INTEGER,
    trade_group_id  INTEGER,
    direction       TEXT,
    lot_size        REAL,
    entry_price     REAL,
    close_price     REAL,
    sl              REAL,
    tp              REAL,
    close_reason    TEXT NOT NULL,
    pnl             REAL,
    pips            REAL,
    duration_seconds INTEGER,
    session         TEXT,
    mode            TEXT
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

CREATE TABLE IF NOT EXISTS vision_extractions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT NOT NULL,
    caller            TEXT NOT NULL,
    source_channel    TEXT,
    context_hint      TEXT,
    image_type        TEXT,
    confidence        TEXT,
    extracted_text    TEXT,
    structured_data   TEXT,
    direction         TEXT,
    entry_price       REAL,
    sl_price          REAL,
    tp1_price         REAL,
    tp2_price         REAL,
    caller_action     TEXT,
    downstream_result TEXT,
    linked_signal_id  INTEGER,
    linked_group_id   INTEGER,
    image_hash        TEXT,
    file_size_kb      INTEGER,
    processing_ms     INTEGER,
    error             TEXT
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
        """Additive migrations -- safe to re-run."""
        conn.execute(
            """CREATE TABLE IF NOT EXISTS market_regimes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                mode            TEXT,
                session         TEXT,
                symbol          TEXT DEFAULT 'XAUUSD',
                regime_label    TEXT NOT NULL,
                confidence      REAL,
                posterior_json  TEXT,
                model_name      TEXT,
                model_version   TEXT,
                stale           INTEGER DEFAULT 0,
                age_sec         REAL,
                fallback_reason TEXT,
                entry_mode      TEXT,
                apply_entry_policy INTEGER DEFAULT 0,
                entry_gate_reason TEXT,
                feature_hash    TEXT,
                feature_json    TEXT
            )"""
        )
        # v1.2.4+: magic_number column on trade_groups
        cols = [r[1] for r in conn.execute("PRAGMA table_info(trade_groups)").fetchall()]
        if "magic_number" not in cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN magic_number INTEGER")
            log.info("SCRIBE migration: added magic_number column to trade_groups")
        sig_cols = [r[1] for r in conn.execute("PRAGMA table_info(signals_received)").fetchall()]
        if "signal_source_type" not in sig_cols:
            conn.execute("ALTER TABLE signals_received ADD COLUMN signal_source_type TEXT DEFAULT 'TEXT'")
            log.info("SCRIBE migration: added signal_source_type to signals_received")
        if "vision_extraction_id" not in sig_cols:
            conn.execute("ALTER TABLE signals_received ADD COLUMN vision_extraction_id INTEGER")
            log.info("SCRIBE migration: added vision_extraction_id to signals_received")
        if "vision_confidence" not in sig_cols:
            conn.execute("ALTER TABLE signals_received ADD COLUMN vision_confidence TEXT")
            log.info("SCRIBE migration: added vision_confidence to signals_received")
        if "regime_label" not in sig_cols:
            conn.execute("ALTER TABLE signals_received ADD COLUMN regime_label TEXT")
            log.info("SCRIBE migration: added regime_label to signals_received")
        if "regime_confidence" not in sig_cols:
            conn.execute("ALTER TABLE signals_received ADD COLUMN regime_confidence REAL")
            log.info("SCRIBE migration: added regime_confidence to signals_received")
        if "regime_model" not in sig_cols:
            conn.execute("ALTER TABLE signals_received ADD COLUMN regime_model TEXT")
            log.info("SCRIBE migration: added regime_model to signals_received")
        if "regime_entry_mode" not in sig_cols:
            conn.execute("ALTER TABLE signals_received ADD COLUMN regime_entry_mode TEXT")
            log.info("SCRIBE migration: added regime_entry_mode to signals_received")
        if "regime_policy" not in sig_cols:
            conn.execute("ALTER TABLE signals_received ADD COLUMN regime_policy TEXT")
            log.info("SCRIBE migration: added regime_policy to signals_received")
        if "regime_fallback_reason" not in sig_cols:
            conn.execute("ALTER TABLE signals_received ADD COLUMN regime_fallback_reason TEXT")
            log.info("SCRIBE migration: added regime_fallback_reason to signals_received")
        ms_cols = [r[1] for r in conn.execute("PRAGMA table_info(market_snapshots)").fetchall()]
        if "pending_entry_threshold_points" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN pending_entry_threshold_points REAL")
            log.info("SCRIBE migration: added pending_entry_threshold_points to market_snapshots")
        if "trend_strength_atr_threshold" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN trend_strength_atr_threshold REAL")
            log.info("SCRIBE migration: added trend_strength_atr_threshold to market_snapshots")
        if "breakout_buffer_points" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN breakout_buffer_points REAL")
            log.info("SCRIBE migration: added breakout_buffer_points to market_snapshots")
        if "regime_label" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN regime_label TEXT")
            log.info("SCRIBE migration: added regime_label to market_snapshots")
        if "regime_confidence" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN regime_confidence REAL")
            log.info("SCRIBE migration: added regime_confidence to market_snapshots")
        if "regime_model" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN regime_model TEXT")
            log.info("SCRIBE migration: added regime_model to market_snapshots")
        tg_cols = [r[1] for r in conn.execute("PRAGMA table_info(trade_groups)").fetchall()]
        if "pending_entry_threshold_points" not in tg_cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN pending_entry_threshold_points REAL")
            log.info("SCRIBE migration: added pending_entry_threshold_points to trade_groups")
        if "trend_strength_atr_threshold" not in tg_cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN trend_strength_atr_threshold REAL")
            log.info("SCRIBE migration: added trend_strength_atr_threshold to trade_groups")
        if "breakout_buffer_points" not in tg_cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN breakout_buffer_points REAL")
            log.info("SCRIBE migration: added breakout_buffer_points to trade_groups")
        if "regime_label" not in tg_cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN regime_label TEXT")
            log.info("SCRIBE migration: added regime_label to trade_groups")
        if "regime_confidence" not in tg_cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN regime_confidence REAL")
            log.info("SCRIBE migration: added regime_confidence to trade_groups")
        if "regime_model" not in tg_cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN regime_model TEXT")
            log.info("SCRIBE migration: added regime_model to trade_groups")
        if "regime_entry_mode" not in tg_cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN regime_entry_mode TEXT")
            log.info("SCRIBE migration: added regime_entry_mode to trade_groups")
        if "regime_policy" not in tg_cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN regime_policy TEXT")
            log.info("SCRIBE migration: added regime_policy to trade_groups")
        if "regime_fallback_reason" not in tg_cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN regime_fallback_reason TEXT")
            log.info("SCRIBE migration: added regime_fallback_reason to trade_groups")
        # ── Entry-zone / fill-rate columns ─────────────────────────
        if "entry_zone_pips" not in tg_cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN entry_zone_pips REAL")
            log.info("SCRIBE migration: added entry_zone_pips to trade_groups")
        if "trades_filled" not in tg_cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN trades_filled INTEGER DEFAULT 0")
            log.info("SCRIBE migration: added trades_filled to trade_groups")
        if "entry_type" not in tg_cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN entry_type TEXT")
            log.info("SCRIBE migration: added entry_type to trade_groups")
        if "entry_cluster" not in tg_cols:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN entry_cluster INTEGER")
            log.info("SCRIBE migration: added entry_cluster to trade_groups")

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
                 adx,tv_rating,timeframe,session,news_guard_active,
                 pending_entry_threshold_points,trend_strength_atr_threshold,breakout_buffer_points,
                 regime_label,regime_confidence,regime_model)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                 data.get("session"), int(data.get("news_guard",False)),
                 data.get("pending_entry_threshold_points"),
                 data.get("trend_strength_atr_threshold"),
                 data.get("breakout_buffer_points"),
                 data.get("regime_label"),
                 data.get("regime_confidence"),
                 data.get("regime_model")))

    def log_market_regime(self, snapshot: dict, mode: str = None, session: str = None) -> int:
        if not snapshot:
            return 0
        posterior_json = json.dumps(snapshot.get("posterior") or {}, default=str)
        feature_json = json.dumps(snapshot.get("features") or {}, default=str)
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO market_regimes
                (timestamp,mode,session,symbol,regime_label,confidence,posterior_json,
                 model_name,model_version,stale,age_sec,fallback_reason,
                 entry_mode,apply_entry_policy,entry_gate_reason,feature_hash,feature_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot.get("timestamp") or self._now(),
                    mode,
                    session,
                    snapshot.get("symbol", "XAUUSD"),
                    snapshot.get("label", "UNKNOWN"),
                    snapshot.get("confidence"),
                    posterior_json,
                    snapshot.get("model_name"),
                    snapshot.get("model_version"),
                    int(bool(snapshot.get("stale"))),
                    snapshot.get("age_sec"),
                    snapshot.get("fallback_reason"),
                    snapshot.get("entry_mode"),
                    int(bool(snapshot.get("apply_entry_policy"))),
                    snapshot.get("entry_gate_reason"),
                    snapshot.get("feature_hash"),
                    feature_json,
                ),
            )
            return cur.lastrowid

    def log_signal(self, raw: str, parsed: dict, mode: str,
                   channel: str = None, msg_id: int = None,
                   signal_source_type: str = "TEXT",
                   vision_extraction_id: int = None,
                   vision_confidence: str = None) -> int:
        tp3_open_raw = parsed.get("tp3_open", False)
        if tp3_open_raw is None:
            tp3_open = 0
        elif isinstance(tp3_open_raw, str):
            tp3_open = 1 if tp3_open_raw.strip().lower() in ("1", "true", "yes", "on") else 0
        else:
            tp3_open = 1 if bool(tp3_open_raw) else 0
        with self._conn() as c:
            cur = c.execute("""INSERT INTO signals_received
                (timestamp,mode,raw_text,channel_name,message_id,signal_type,
                 direction,entry_low,entry_high,sl,tp1,tp2,tp3,tp3_open,
                 mgmt_intent,mgmt_pct,signal_source_type,vision_extraction_id,
                 vision_confidence,action_taken,skip_reason)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self._now(), mode, raw, channel, msg_id,
                 parsed.get("type","ENTRY"),
                 parsed.get("direction"), parsed.get("entry_low"),
                 parsed.get("entry_high"), parsed.get("sl"),
                 parsed.get("tp1"), parsed.get("tp2"), parsed.get("tp3"),
                 tp3_open,
                 parsed.get("mgmt_intent"), parsed.get("mgmt_pct"),
                 signal_source_type, vision_extraction_id, vision_confidence,
                 parsed.get("action","PENDING"), parsed.get("skip_reason")))
            return cur.lastrowid

    def update_signal_action(self, signal_id: int, action: str,
                              skip_reason: str = None, group_id: int = None):
        with self._conn() as c:
            c.execute("""UPDATE signals_received
                SET action_taken=?, skip_reason=?, trade_group_id=?
                WHERE id=?""", (action, skip_reason, group_id, signal_id))

    def update_signal_regime(self, signal_id: int, metadata: dict):
        if not signal_id:
            return
        md = metadata or {}
        with self._conn() as c:
            c.execute(
                """UPDATE signals_received
                   SET regime_label=?,
                       regime_confidence=?,
                       regime_model=?,
                       regime_entry_mode=?,
                       regime_policy=?,
                       regime_fallback_reason=?
                   WHERE id=?""",
                (
                    md.get("label"),
                    md.get("confidence"),
                    md.get("model_name"),
                    md.get("entry_mode"),
                    md.get("regime_policy") or md.get("policy_name"),
                    md.get("fallback_reason") or md.get("entry_gate_reason"),
                    signal_id,
                ),
            )

    def log_vision_extraction(self, data: dict) -> int:
        structured = data.get("structured_data")
        structured_json = json.dumps(structured, default=str) if isinstance(structured, dict) else None
        with self._conn() as c:
            cur = c.execute("""INSERT INTO vision_extractions
                (timestamp,caller,source_channel,context_hint,image_type,confidence,
                 extracted_text,structured_data,direction,entry_price,sl_price,tp1_price,tp2_price,
                 caller_action,downstream_result,linked_signal_id,linked_group_id,
                 image_hash,file_size_kb,processing_ms,error)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self._now(),
                 data.get("caller"), data.get("source_channel"), data.get("context_hint"),
                 data.get("image_type"), data.get("confidence"), data.get("extracted_text"),
                 structured_json,
                 data.get("direction"), data.get("entry_price"), data.get("sl_price"),
                 data.get("tp1_price"), data.get("tp2_price"),
                 data.get("caller_action"), data.get("downstream_result"),
                 data.get("linked_signal_id"), data.get("linked_group_id"),
                 data.get("image_hash"), data.get("file_size_kb"), data.get("processing_ms"),
                 data.get("error")))
            return cur.lastrowid

    def update_vision_extraction_result(self, extraction_id: int,
                                        downstream_result: str,
                                        linked_signal_id: int = None,
                                        linked_group_id: int = None):
        with self._conn() as c:
            c.execute("""UPDATE vision_extractions
                SET downstream_result=?,
                    linked_signal_id=COALESCE(?, linked_signal_id),
                    linked_group_id=COALESCE(?, linked_group_id)
                WHERE id=?""",
                (downstream_result, linked_signal_id, linked_group_id, extraction_id))

    def log_trade_group(self, data: dict, mode: str,
                        magic_number: int | None = None) -> int:
        with self._conn() as c:
            cur = c.execute("""INSERT INTO trade_groups
                (timestamp,mode,source,signal_id,direction,
                 entry_low,entry_high,sl,tp1,tp2,tp3,
                 num_trades,lot_per_trade,risk_pct,account_balance,
                 lens_rating,lens_rsi,lens_confirmed,
                 pending_entry_threshold_points,trend_strength_atr_threshold,breakout_buffer_points,
                 regime_label,regime_confidence,regime_model,regime_entry_mode,regime_policy,regime_fallback_reason,
                 magic_number,trades_opened,trades_closed)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self._now(), mode, data.get("source","SIGNAL"),
                 data.get("signal_id"), data.get("direction"),
                 data.get("entry_low"), data.get("entry_high"),
                 data.get("sl"), data.get("tp1"), data.get("tp2"), data.get("tp3"),
                 data.get("num_trades",8), data.get("lot_per_trade"),
                 data.get("risk_pct"), data.get("account_balance"),
                 data.get("lens_rating"), data.get("lens_rsi"),
                 data.get("lens_confirmed"),
                 data.get("pending_entry_threshold_points"),
                 data.get("trend_strength_atr_threshold"),
                 data.get("breakout_buffer_points"),
                 data.get("regime_label"),
                 data.get("regime_confidence"),
                 data.get("regime_model"),
                 data.get("regime_entry_mode"),
                 data.get("regime_policy"),
                 data.get("regime_fallback_reason"),
                 magic_number,
                 data.get("num_trades",8), 0))
            return cur.lastrowid

    def update_trade_group_magic(self, group_id: int, magic_number: int):
        """Set the magic_number for a trade group (called after SCRIBE assigns the id)."""
        with self._conn() as c:
            c.execute("UPDATE trade_groups SET magic_number=? WHERE id=?",
                      (magic_number, group_id))

    def update_group_open_meta(self, group_id: int, *,
                                entry_zone_pips: float | None = None,
                                entry_type: str | None = None,
                                entry_cluster: int | None = None):
        """Populate entry-zone / placement metadata captured at OPEN time.
        Each arg is optional; only non-None fields are written.
        Tolerates missing columns on legacy DBs (OperationalError swallowed)."""
        sets, params = [], []
        if entry_zone_pips is not None:
            sets.append("entry_zone_pips=?"); params.append(float(entry_zone_pips))
        if entry_type is not None:
            sets.append("entry_type=?"); params.append(str(entry_type))
        if entry_cluster is not None:
            sets.append("entry_cluster=?"); params.append(int(bool(entry_cluster)))
        if not sets:
            return
        params.append(int(group_id))
        sql = f"UPDATE trade_groups SET {', '.join(sets)} WHERE id=?"
        try:
            with self._conn() as c:
                c.execute(sql, tuple(params))
        except sqlite3.OperationalError as e:
            log.debug("SCRIBE update_group_open_meta tolerated: %s", e)

    def increment_group_fills(self, group_id: int, delta: int = 1):
        """Increment trades_filled counter for a group; tolerated on legacy DBs."""
        try:
            with self._conn() as c:
                c.execute(
                    "UPDATE trade_groups SET trades_filled = COALESCE(trades_filled, 0) + ? WHERE id=?",
                    (int(delta), int(group_id)),
                )
        except sqlite3.OperationalError as e:
            log.debug("SCRIBE increment_group_fills tolerated: %s", e)

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

    def update_position_sl_tp(self, ticket: int, sl: float = None, tp: float = None):
        """Update SL/TP on an open position (manual MT5 modification detected by tracker)."""
        with self._conn() as c:
            if sl is not None and tp is not None:
                c.execute("UPDATE trade_positions SET sl=?, tp=? WHERE ticket=? AND status='OPEN'",
                          (sl, tp, ticket))
            elif sl is not None:
                c.execute("UPDATE trade_positions SET sl=? WHERE ticket=? AND status='OPEN'",
                          (sl, ticket))
            elif tp is not None:
                c.execute("UPDATE trade_positions SET tp=? WHERE ticket=? AND status='OPEN'",
                          (tp, ticket))
    def update_group_sl_tp(self, group_id: int, sl: float = None, tp: float = None):
        """Sync group-level and open position SL/TP for a specific trade group."""
        if sl is None and tp is None:
            return
        with self._conn() as c:
            if sl is not None:
                c.execute(
                    "UPDATE trade_groups SET sl=? WHERE id=?",
                    (sl, group_id),
                )
                c.execute(
                    "UPDATE trade_positions SET sl=? WHERE trade_group_id=? AND status='OPEN'",
                    (sl, group_id),
                )
            if tp is not None:
                c.execute(
                    """UPDATE trade_groups
                       SET tp1=?,
                           tp2=CASE WHEN tp2 IS NULL OR tp2=0 THEN tp2 ELSE ? END,
                           tp3=CASE WHEN tp3 IS NULL OR tp3=0 THEN tp3 ELSE ? END
                       WHERE id=?""",
                    (tp, tp, tp, group_id),
                )
                c.execute(
                    "UPDATE trade_positions SET tp=? WHERE trade_group_id=? AND status='OPEN'",
                    (tp, group_id),
                )

    def close_trade_position(self, ticket: int, close_price: float,
                              close_reason: str, pnl: float, pips: float,
                              tp_stage: int = None, close_time: str = None):
        with self._conn() as c:
            c.execute("""UPDATE trade_positions
                SET status='CLOSED', close_price=?, close_time=?,
                    close_reason=?, pnl=?, pips=?, tp_stage=?
                WHERE ticket=?""",
                (close_price, close_time or self._now(), close_reason, pnl, pips, tp_stage, ticket))

    def log_trade_closure(self, ticket: int, trade_group_id: int,
                          direction: str, lot_size: float,
                          entry_price: float, close_price: float,
                          sl: float, tp: float,
                          close_reason: str, pnl: float, pips: float,
                          duration_seconds: int = None,
                          session: str = None, mode: str = None) -> int:
        """Log a position closure to trade_closures table."""
        with self._conn() as c:
            cur = c.execute("""INSERT INTO trade_closures
                (timestamp, ticket, trade_group_id, direction, lot_size,
                 entry_price, close_price, sl, tp, close_reason,
                 pnl, pips, duration_seconds, session, mode)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self._now(), ticket, trade_group_id, direction, lot_size,
                 entry_price, close_price, sl, tp, close_reason,
                 pnl, pips, duration_seconds, session, mode))
            return cur.lastrowid

    def get_recent_closures(self, limit: int = 20, days: int = 7) -> list:
        """Return recent trade closures for ATHENA/AURUM."""
        d = max(1, min(int(days), 366))
        with self._conn() as c:
            rows = c.execute("""
                SELECT * FROM trade_closures
                WHERE timestamp >= datetime('now', ?)
                ORDER BY timestamp DESC LIMIT ?""",
                (f"-{d} days", limit)).fetchall()
            return [dict(r) for r in rows]

    def get_closure_stats(self, days: int = 7) -> dict:
        """Aggregated SL vs TP hit rates for ATHENA/AURUM."""
        d = max(1, min(int(days), 366))
        with self._conn() as c:
            row = c.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN close_reason='SL_HIT' THEN 1 ELSE 0 END) AS sl_hits,
                    SUM(CASE WHEN close_reason='TP1_HIT' THEN 1 ELSE 0 END) AS tp1_hits,
                    SUM(CASE WHEN close_reason='TP2_HIT' THEN 1 ELSE 0 END) AS tp2_hits,
                    SUM(CASE WHEN close_reason='TP3_HIT' THEN 1 ELSE 0 END) AS tp3_hits,
                    SUM(CASE WHEN close_reason='MANUAL_CLOSE' THEN 1 ELSE 0 END) AS manual,
                    COALESCE(SUM(pnl), 0) AS total_pnl,
                    COALESCE(AVG(pnl), 0) AS avg_pnl,
                    COALESCE(AVG(pips), 0) AS avg_pips,
                    COALESCE(AVG(duration_seconds), 0) AS avg_duration_sec
                FROM trade_closures
                WHERE timestamp >= datetime('now', ?)""",
                (f"-{d} days",)).fetchone()
            total = row[0] or 1
            return {
                "total": row[0] or 0,
                "sl_hits": row[1] or 0,
                "tp1_hits": row[2] or 0,
                "tp2_hits": row[3] or 0,
                "tp3_hits": row[4] or 0,
                "manual": row[5] or 0,
                "sl_rate": round((row[1] or 0) / total * 100, 1),
                "tp_rate": round(((row[2] or 0) + (row[3] or 0) + (row[4] or 0)) / total * 100, 1),
                "total_pnl": round(row[6] or 0, 2),
                "avg_pnl": round(row[7] or 0, 2),
                "avg_pips": round(row[8] or 0, 1),
                "avg_duration_sec": round(row[9] or 0, 0),
            }

    @staticmethod
    def _decode_regime_row(row: dict) -> dict:
        out = dict(row or {})
        if "label" not in out and "regime_label" in out:
            out["label"] = out.get("regime_label")
        if "confidence" not in out and "regime_confidence" in out:
            out["confidence"] = out.get("regime_confidence")
        try:
            out["posterior"] = json.loads(out.get("posterior_json") or "{}")
        except Exception:
            out["posterior"] = {}
        try:
            out["features"] = json.loads(out.get("feature_json") or "{}")
        except Exception:
            out["features"] = {}
        ts = out.get("timestamp")
        age = None
        if ts:
            try:
                dt = datetime.fromisoformat(str(ts))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - dt).total_seconds()
            except Exception:
                age = None
        out["age_sec"] = round(age, 1) if age is not None else out.get("age_sec")
        return out

    def get_latest_regime(self) -> dict:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM market_regimes ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return self._decode_regime_row(dict(row)) if row else {}

    def get_regime_history(self, limit: int = 50, hours: int = 24) -> list:
        lim = max(1, min(int(limit), 2000))
        hrs = max(1, min(int(hours), 24 * 30))
        with self._conn() as c:
            rows = c.execute(
                """SELECT * FROM market_regimes
                   WHERE timestamp >= datetime('now', ?)
                   ORDER BY id DESC LIMIT ?""",
                (f"-{hrs} hours", lim),
            ).fetchall()
            return [self._decode_regime_row(dict(r)) for r in rows]

    def get_regime_transitions(self, hours: int = 24, limit: int = 20) -> list:
        hrs = max(1, min(int(hours), 24 * 30))
        lim = max(1, min(int(limit), 500))
        with self._conn() as c:
            rows = c.execute(
                """SELECT timestamp, regime_label, confidence, model_name, stale
                   FROM market_regimes
                   WHERE timestamp >= datetime('now', ?)
                   ORDER BY timestamp ASC""",
                (f"-{hrs} hours",),
            ).fetchall()
        transitions: list[dict] = []
        prev_label = None
        for r in rows:
            cur = r["regime_label"]
            if prev_label is not None and cur != prev_label:
                transitions.append(
                    {
                        "timestamp": r["timestamp"],
                        "from": prev_label,
                        "to": cur,
                        "confidence": r["confidence"],
                        "model_name": r["model_name"],
                        "stale": bool(r["stale"]),
                    }
                )
            prev_label = cur
        return list(reversed(transitions[-lim:]))

    def get_regime_performance(self, days: int = 30) -> dict:
        d = max(1, min(int(days), 366))
        with self._conn() as c:
            rows = c.execute(
                """SELECT COALESCE(regime_label,'UNKNOWN') AS regime_label,
                          COUNT(*) AS total,
                          SUM(CASE WHEN total_pnl > 0 THEN 1 ELSE 0 END) AS wins,
                          SUM(CASE WHEN total_pnl < 0 THEN 1 ELSE 0 END) AS losses,
                          COALESCE(SUM(total_pnl), 0) AS total_pnl,
                          COALESCE(AVG(total_pnl), 0) AS avg_pnl,
                          COALESCE(AVG(pips_captured), 0) AS avg_pips
                   FROM trade_groups
                   WHERE status NOT IN ('OPEN','PARTIAL')
                     AND closed_at IS NOT NULL
                     AND closed_at >= datetime('now', ?)
                   GROUP BY COALESCE(regime_label,'UNKNOWN')
                   ORDER BY total DESC""",
                (f"-{d} days",),
            ).fetchall()
            fb = c.execute(
                """SELECT COUNT(*) AS total,
                          SUM(CASE WHEN fallback_reason IS NOT NULL
                                   AND TRIM(fallback_reason) <> ''
                                   THEN 1 ELSE 0 END) AS fallback_count
                   FROM market_regimes
                   WHERE timestamp >= datetime('now', ?)""",
                (f"-{d} days",),
            ).fetchone()
        by_regime = []
        for r in rows:
            total = int(r["total"] or 0)
            wins = int(r["wins"] or 0)
            by_regime.append(
                {
                    "regime_label": r["regime_label"],
                    "total": total,
                    "wins": wins,
                    "losses": int(r["losses"] or 0),
                    "win_rate": round((wins / total) * 100, 1) if total else None,
                    "total_pnl": round(r["total_pnl"] or 0, 2),
                    "avg_pnl": round(r["avg_pnl"] or 0, 2),
                    "avg_pips": round(r["avg_pips"] or 0, 1),
                }
            )
        total_snaps = int((fb["total"] if fb else 0) or 0)
        fallback_count = int((fb["fallback_count"] if fb else 0) or 0)
        return {
            "days": d,
            "by_regime": by_regime,
            "snapshot_count": total_snaps,
            "fallback_count": fallback_count,
            "fallback_rate": round((fallback_count / total_snaps) * 100, 1) if total_snaps else 0.0,
        }

    def get_open_positions_by_group(self, group_id: int) -> list:
        """Return all OPEN positions for a given trade group."""
        with self._conn() as c:
            rows = c.execute("""
                SELECT * FROM trade_positions
                WHERE trade_group_id=? AND status='OPEN'""",
                (group_id,)).fetchall()
            return [dict(r) for r in rows]

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

    def get_current_session_start(self) -> str | None:
        """Return the open_time of the current (unclosed) session, or None."""
        with self._conn() as c:
            row = c.execute("""
                SELECT open_time FROM trading_sessions
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

    def get_recent_signals(self, limit: int = 20, within_days: int = None,
                            since: str = None) -> list:
        """Return recent signals. If `since` is provided (ISO timestamp),
        only return signals on or after that time."""
        with self._conn() as c:
            if since:
                rows = c.execute(
                    """SELECT * FROM signals_received
                       WHERE timestamp >= ?
                       ORDER BY timestamp DESC LIMIT ?""",
                    (since, limit),
                ).fetchall()
            elif within_days is not None:
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
                    SUM(CASE WHEN pnl<0 THEN 1 ELSE 0 END) losses,
                    COALESCE(SUM(pnl),0) total_pnl,
                    COALESCE(AVG(pips),0) avg_pips
                    FROM trade_positions {base}""",
                tuple(params),
            ).fetchone()
            total_n = int(rows[0] or 0)
            wins = int(rows[1] or 0)
            losses = int(rows[2] or 0)
            return {
                "total": total_n,
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / total_n * 100, 1) if total_n else None,
                "total_pnl": round(rows[3] or 0, 2),
                "avg_pips": round(rows[4] or 0, 1),
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
