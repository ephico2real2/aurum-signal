"""
scribe.py — SCRIBE Intelligence Data Logger
============================================
Build order: #1 — no dependencies, pure Python stdlib.
Every component imports and calls Scribe.  All records carry mode + timestamp.
"""

import sqlite3, os, json, logging, re
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager

log = logging.getLogger("scribe")

_PY_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PY_DIR.parent
_DEFAULT_AUDIT_JSONL = _REPO_ROOT / "logs" / "audit" / "system_events.jsonl"
_SCRIBE_DB_DEFAULT = "python/data/aurum_intelligence.db"


def _resolve_db_path() -> str:
    raw = (os.environ.get("SCRIBE_DB") or _SCRIBE_DB_DEFAULT).strip() or _SCRIBE_DB_DEFAULT
    # Legacy: was relative to python/ only — same on-disk file, path from repo root
    if raw == "data/aurum_intelligence.db":
        raw = _SCRIBE_DB_DEFAULT
    p = Path(raw)
    if p.is_absolute():
        return str(p)
    return str((_REPO_ROOT / p).resolve())


DB_PATH = _resolve_db_path()

ALLOWED_SCRIBE_TABLES = frozenset({
    "aurum_conversations",
    "component_heartbeats",
    "market_regimes",
    "market_snapshots",
    "news_events",
    "signals_received",
    "system_events",
    "trade_closures",
    "trade_groups",
    "trade_positions",
    "trading_sessions",
    "vision_extractions",
})

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
    poc_price REAL,
    vwap_price REAL,
    fib_50 REAL,
    fib_382 REAL,
    fib_618 REAL,
    rsi_divergence TEXT,
    psar_state TEXT,
    outcome_label TEXT, label_filled INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS forge_signals (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    forge_id          INTEGER,
    time              INTEGER NOT NULL,
    timestamp_utc     TEXT NOT NULL,
    symbol            TEXT NOT NULL,
    setup_type        TEXT,
    direction         TEXT,
    outcome           TEXT NOT NULL,
    gate_reason       TEXT,
    price             REAL,
    spread            REAL,
    atr               REAL,
    rsi               REAL,
    adx               REAL,
    bb_upper          REAL,
    bb_lower          REAL,
    bb_mid            REAL,
    poc_price         REAL,
    vwap_price        REAL,
    fib_50            REAL,
    rsi_divergence    TEXT,
    psar_state        TEXT,
    pattern_score     INTEGER,
    h1_trend          REAL,
    regime_label      TEXT,
    regime_confidence REAL,
    adx_trend_regime  INTEGER,
    high_vol_trend    INTEGER,
    session           TEXT,
    killzone          TEXT,
    minutes_into_kz   INTEGER DEFAULT 0,
    -- 2.7.47 RegimeState surfacing (FORGE_REGIME_TAXONOMY.md §3)
    htf_h1_strong        INTEGER DEFAULT 0,
    intraday_label       TEXT DEFAULT '',
    intraday_counter_htf INTEGER DEFAULT 0,
    magic             INTEGER,
    journal_source    TEXT DEFAULT 'live',
    -- 2.7.37 Layer-4 atom telemetry (24 cols)
    h4_trend          REAL,
    m15_trend         REAL,
    h1_di_balance     REAL,
    day_open          REAL,
    day_high          REAL,
    day_low           REAL,
    m5_open_1         REAL,
    m5_high_1         REAL,
    m5_low_1          REAL,
    m5_close_1        REAL,
    m5_lh_cascade     INTEGER DEFAULT 0,
    m5_hl_cascade     INTEGER DEFAULT 0,
    m5_body_pct       REAL,
    h1_di_plus        REAL,
    h1_di_minus       REAL,
    h4_rsi            REAL,
    h4_adx            REAL,
    m30_trend         REAL,
    d1_open           REAL,
    d1_close          REAL,
    h1_atr            REAL,
    h4_atr            REAL,
    m15_atr           REAL,
    m1_atr            REAL,
    -- 2.7.37 Group 3 — full per-TF indicator + OHLC + bar-quality inventory (45 cols)
    h1_rsi            REAL,
    h1_adx            REAL,
    h1_bb_u           REAL,
    h1_bb_m           REAL,
    h1_bb_l           REAL,
    h4_bb_u           REAL,
    h4_bb_m           REAL,
    h4_bb_l           REAL,
    m15_rsi           REAL,
    m15_ema20         REAL,
    m15_ema50         REAL,
    m30_rsi           REAL,
    m30_adx           REAL,
    m30_atr           REAL,
    m30_ema20         REAL,
    m30_ema50         REAL,
    m1_ema20          REAL,
    m1_ema50          REAL,
    m5_open_0         REAL,
    m5_high_0         REAL,
    m5_low_0          REAL,
    m5_close_0        REAL,
    m15_open          REAL,
    m15_high          REAL,
    m15_low           REAL,
    m15_close         REAL,
    m30_open          REAL,
    m30_high          REAL,
    m30_low           REAL,
    m30_close         REAL,
    h1_open           REAL,
    h1_high           REAL,
    h1_low            REAL,
    h1_close          REAL,
    h4_open           REAL,
    h4_high           REAL,
    h4_low            REAL,
    h4_close          REAL,
    m5_inside_bar     INTEGER DEFAULT 0,
    m5_outside_bar    INTEGER DEFAULT 0,
    m5_doji           INTEGER DEFAULT 0,
    m5_strong_bar     INTEGER DEFAULT 0,
    long_lower_wick   INTEGER DEFAULT 0,
    long_upper_wick   INTEGER DEFAULT 0,
    m5_range_expanding INTEGER DEFAULT 0,
    -- v2.7.112 ISS (ICT Structure Score) — 5 INTEGER cols (atoms ship in v2.7.118+)
    iss_score             INTEGER DEFAULT 0,
    iss_mss               INTEGER DEFAULT 0,
    iss_fvg               INTEGER DEFAULT 0,
    iss_choch_support     INTEGER DEFAULT 0,
    iss_choch_against     INTEGER DEFAULT 0,
    -- v2.7.119 ICT Phase-1 atom context (9 cols; LOG-ONLY)
    ict_mss_swing_price       REAL    DEFAULT 0,
    ict_mss_displacement_atr  REAL    DEFAULT 0,
    ict_fvg_count_active      INTEGER DEFAULT 0,
    ict_fvg_active_upper      REAL    DEFAULT 0,
    ict_fvg_active_lower      REAL    DEFAULT 0,
    ict_fvg_midpoint_dist_atr REAL    DEFAULT 0,
    ict_fvg_age_bars          INTEGER DEFAULT 0,
    ict_recent_swing_high     REAL    DEFAULT 0,
    ict_recent_swing_low      REAL    DEFAULT 0,
    -- v2.7.120 ICT Phase-2 atom context (8 cols; LOG-ONLY — ChoCH + liquidity sweep + killzone)
    ict_choch_buy_count        INTEGER DEFAULT 0,
    ict_choch_sell_count       INTEGER DEFAULT 0,
    ict_choch_level            REAL    DEFAULT 0,
    ict_liquidity_sweep_recent INTEGER DEFAULT 0,
    ict_sweep_level            REAL    DEFAULT 0,
    ict_equal_highs_count      INTEGER DEFAULT 0,
    ict_equal_lows_count       INTEGER DEFAULT 0,
    ict_killzone_active        INTEGER DEFAULT 0,
    -- v2.7.122 ict_sweep_rejection_score: 0..1 wick-quality score from ScoreLiquiditySweep
    ict_sweep_rejection_score  REAL    DEFAULT 0,
    -- v2.7.122 Pre-TP1 recovery armed flag (1 = this tick armed a pre-TP1 recovery LIMIT)
    pre_tp1_recovery_armed     INTEGER DEFAULT 0,
    -- v2.7.123 Phase A ICT atom outputs (5 INTEGERs; LOG-ONLY, Mode A).
    -- Per docs/FORGE_SETUP_ICT_MAP.md §B.8.2 — atom_* prefix (not ict_atom_*).
    -- Bound by FORGE.mq5 JournalRecordSignal from g_ict_last_atom_* globals.
    atom_killzone_favorable       INTEGER DEFAULT 0,
    atom_htf_aligned              INTEGER DEFAULT 0,
    atom_pullback_in_ote          INTEGER DEFAULT 0,
    atom_premium_discount_aligned INTEGER DEFAULT 0,
    atom_fvg_on_reversal_leg      INTEGER DEFAULT 0,
    -- v2.7.124 Phase A expansion (6 INTEGERs) — per-category KZ + per-direction HTF.
    -- Per docs/FORGE_SETUP_ICT_MAP.md §B.8.2. Reuse existing FORGE_ICT_ATOM_*_ENABLED flags.
    atom_kz_fav_mss_cont          INTEGER DEFAULT 0,
    atom_kz_fav_ote               INTEGER DEFAULT 0,
    atom_kz_fav_liq_sweep         INTEGER DEFAULT 0,
    atom_kz_fav_breaker           INTEGER DEFAULT 0,
    atom_htf_aligned_buy          INTEGER DEFAULT 0,
    atom_htf_aligned_sell         INTEGER DEFAULT 0,
    -- v2.7.124 Phase B (6 INTEGERs) — composite scores 0-10 per category × direction.
    -- BREAKER_RETEST deferred until Phase 3 IctOrderBlock.mqh ships.
    mss_cont_score_buy            INTEGER DEFAULT 0,
    mss_cont_score_sell           INTEGER DEFAULT 0,
    ote_retrace_score_buy         INTEGER DEFAULT 0,
    ote_retrace_score_sell        INTEGER DEFAULT 0,
    liq_sweep_rev_score_buy       INTEGER DEFAULT 0,
    liq_sweep_rev_score_sell      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS forge_journal_trades (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    forge_rowid       INTEGER NOT NULL,
    deal_ticket       INTEGER NOT NULL,
    order_ticket      INTEGER,
    symbol            TEXT NOT NULL,
    type              INTEGER,
    direction         INTEGER,
    volume            REAL,
    price             REAL,
    profit            REAL,
    swap              REAL,
    commission        REAL,
    magic             INTEGER,
    comment           TEXT,
    time              INTEGER NOT NULL,
    time_msc          INTEGER,
    journal_source    TEXT DEFAULT 'live',
    run_id            INTEGER DEFAULT 0,
    UNIQUE(deal_ticket, journal_source, run_id)
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
    total_pip_value_usd REAL,
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
    pip_value_usd  REAL,
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
    pip_value_usd   REAL,
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
        # busy_timeout=5000: read connections wait up to 5s for write locks
        # to clear (BRIDGE batch-sync transactions can hold the lock briefly).
        # WAL mode is applied once at init below — connection-level setting here
        # is the per-call backstop that avoids instant "database is locked" errors.
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            log.error(f"SCRIBE DB error: {e}")
            raise
        finally:
            conn.close()

    def _init_db(self):
        # Apply WAL mode + relaxed sync ONCE at startup. These are persistent
        # SQLite settings — they survive across connections after first set.
        # WAL allows concurrent reads while writes happen (BRIDGE syncs + Athena
        # reads coexist without "database is locked" errors). synchronous=NORMAL
        # relaxes fsync (still ACID with WAL). Per mql5.com/articles/22009 pattern
        # (same fix as v2.7.111 on the source FORGE_journal_*.db).
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
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
        if "poc_price" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN poc_price REAL")
            log.info("SCRIBE migration: added poc_price to market_snapshots")
        if "vwap_price" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN vwap_price REAL")
            log.info("SCRIBE migration: added vwap_price to market_snapshots")
        if "fib_50" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN fib_50 REAL")
            log.info("SCRIBE migration: added fib_50 to market_snapshots")
        if "fib_382" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN fib_382 REAL")
            log.info("SCRIBE migration: added fib_382 to market_snapshots")
        if "fib_618" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN fib_618 REAL")
            log.info("SCRIBE migration: added fib_618 to market_snapshots")
        if "rsi_divergence" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN rsi_divergence TEXT")
            log.info("SCRIBE migration: added rsi_divergence to market_snapshots")
        if "psar_state" not in ms_cols:
            conn.execute("ALTER TABLE market_snapshots ADD COLUMN psar_state TEXT")
            log.info("SCRIBE migration: added psar_state to market_snapshots")
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        # aurum_tester_runs — stable AURUM-level run registry keyed on wall_time (entropy).
        # aurum_run_id auto-increments per unique wall_time and never resets even when the
        # source journal DB is wiped. Use this instead of run_id for all AURUM run filtering.
        # run_id in forge_signals/forge_journal_trades is kept for source-journal cross-reference
        # only — it is unreliable across source DB resets (resets to 1 each wipe).
        if "aurum_tester_runs" not in tables:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS aurum_tester_runs (
                    aurum_run_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    wall_time      INTEGER NOT NULL UNIQUE,
                    source_run_id  INTEGER DEFAULT 0,
                    journal_source TEXT DEFAULT 'tester',
                    symbol         TEXT,
                    forge_version  TEXT,
                    scalper_mode   TEXT,
                    balance        REAL,
                    sim_start_time INTEGER,
                    magic_base     INTEGER,
                    first_seen_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_atr_wall ON aurum_tester_runs(wall_time);
            """)
            log.info("SCRIBE migration: created aurum_tester_runs registry")
        if "forge_signals" not in tables:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS forge_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    forge_id INTEGER, time INTEGER NOT NULL,
                    timestamp_utc TEXT NOT NULL, symbol TEXT NOT NULL,
                    setup_type TEXT, direction TEXT, outcome TEXT NOT NULL,
                    gate_reason TEXT, price REAL, spread REAL, atr REAL,
                    rsi REAL, adx REAL, bb_upper REAL, bb_lower REAL,
                    bb_mid REAL, poc_price REAL, vwap_price REAL, fib_50 REAL,
                    rsi_divergence TEXT, psar_state TEXT, pattern_score INTEGER,
                    h1_trend REAL, regime_label TEXT, regime_confidence REAL,
                    adx_trend_regime INTEGER, high_vol_trend INTEGER,
                    session TEXT, killzone TEXT, minutes_into_kz INTEGER DEFAULT 0,
                    htf_h1_strong INTEGER DEFAULT 0, intraday_label TEXT DEFAULT '', intraday_counter_htf INTEGER DEFAULT 0,
                    magic INTEGER,
                    h4_trend REAL, m15_trend REAL, h1_di_balance REAL,
                    day_open REAL, day_high REAL, day_low REAL,
                    m5_open_1 REAL, m5_high_1 REAL, m5_low_1 REAL, m5_close_1 REAL,
                    m5_lh_cascade INTEGER DEFAULT 0, m5_hl_cascade INTEGER DEFAULT 0, m5_body_pct REAL,
                    h1_di_plus REAL, h1_di_minus REAL, h4_rsi REAL, h4_adx REAL, m30_trend REAL,
                    d1_open REAL, d1_close REAL, h1_atr REAL, h4_atr REAL, m15_atr REAL, m1_atr REAL,
                    -- 2.7.37 Group 3
                    h1_rsi REAL, h1_adx REAL, h1_bb_u REAL, h1_bb_m REAL, h1_bb_l REAL,
                    h4_bb_u REAL, h4_bb_m REAL, h4_bb_l REAL,
                    m15_rsi REAL, m15_ema20 REAL, m15_ema50 REAL,
                    m30_rsi REAL, m30_adx REAL, m30_atr REAL, m30_ema20 REAL, m30_ema50 REAL,
                    m1_ema20 REAL, m1_ema50 REAL,
                    m5_open_0 REAL, m5_high_0 REAL, m5_low_0 REAL, m5_close_0 REAL,
                    m15_open REAL, m15_high REAL, m15_low REAL, m15_close REAL,
                    m30_open REAL, m30_high REAL, m30_low REAL, m30_close REAL,
                    h1_open REAL, h1_high REAL, h1_low REAL, h1_close REAL,
                    h4_open REAL, h4_high REAL, h4_low REAL, h4_close REAL,
                    m5_inside_bar INTEGER DEFAULT 0, m5_outside_bar INTEGER DEFAULT 0,
                    m5_doji INTEGER DEFAULT 0, m5_strong_bar INTEGER DEFAULT 0,
                    long_lower_wick INTEGER DEFAULT 0, long_upper_wick INTEGER DEFAULT 0,
                    m5_range_expanding INTEGER DEFAULT 0,
                    -- v2.7.110 CES (Confluence Entry Score) — Option C instrumentation (retired v2.7.112, retained as nullable for back-compat)
                    ces_score INTEGER DEFAULT 0,
                    ces_dtc INTEGER DEFAULT 0,
                    ces_pemcg INTEGER DEFAULT 0,
                    ces_momentum INTEGER DEFAULT 0,
                    ces_rsi INTEGER DEFAULT 0,
                    ces_vwap INTEGER DEFAULT 0,
                    ces_di INTEGER DEFAULT 0,
                    -- v2.7.112 ISS (ICT Structure Score) — 5 INTEGER cols (atoms live in v2.7.118+)
                    iss_score INTEGER DEFAULT 0,
                    iss_mss INTEGER DEFAULT 0,
                    iss_fvg INTEGER DEFAULT 0,
                    iss_choch_support INTEGER DEFAULT 0,
                    iss_choch_against INTEGER DEFAULT 0,
                    -- v2.7.119 ICT Phase-1 atom context (9 cols; LOG-ONLY, no gate behaviour)
                    ict_mss_swing_price REAL DEFAULT 0,
                    ict_mss_displacement_atr REAL DEFAULT 0,
                    ict_fvg_count_active INTEGER DEFAULT 0,
                    ict_fvg_active_upper REAL DEFAULT 0,
                    ict_fvg_active_lower REAL DEFAULT 0,
                    ict_fvg_midpoint_dist_atr REAL DEFAULT 0,
                    ict_fvg_age_bars INTEGER DEFAULT 0,
                    ict_recent_swing_high REAL DEFAULT 0,
                    ict_recent_swing_low REAL DEFAULT 0,
                    -- v2.7.120 ICT Phase-2 atom context (8 cols; LOG-ONLY — ChoCH + sweep + killzone)
                    ict_choch_buy_count INTEGER DEFAULT 0,
                    ict_choch_sell_count INTEGER DEFAULT 0,
                    ict_choch_level REAL DEFAULT 0,
                    ict_liquidity_sweep_recent INTEGER DEFAULT 0,
                    ict_sweep_level REAL DEFAULT 0,
                    ict_equal_highs_count INTEGER DEFAULT 0,
                    ict_equal_lows_count INTEGER DEFAULT 0,
                    ict_killzone_active INTEGER DEFAULT 0,
                    -- v2.7.122 ict_sweep_rejection_score: 0..1 wick-quality score from ScoreLiquiditySweep
                    ict_sweep_rejection_score REAL DEFAULT 0,
                    -- v2.7.122 Pre-TP1 recovery armed flag (1 = this tick armed pre-TP1 recovery)
                    pre_tp1_recovery_armed INTEGER DEFAULT 0,
                    -- v2.7.123 Phase A ICT atom outputs (5 INTEGERs; LOG-ONLY, Mode A).
                    -- Per docs/FORGE_SETUP_ICT_MAP.md §B.8.2 — atom_* prefix.
                    atom_killzone_favorable INTEGER DEFAULT 0,
                    atom_htf_aligned INTEGER DEFAULT 0,
                    atom_pullback_in_ote INTEGER DEFAULT 0,
                    atom_premium_discount_aligned INTEGER DEFAULT 0,
                    atom_fvg_on_reversal_leg INTEGER DEFAULT 0,
                    -- v2.7.124 Phase A expansion (6 INTEGERs) + Phase B composite scores (6 INTEGERs).
                    -- Per docs/FORGE_SETUP_ICT_MAP.md §B.8.2. atom_kz_fav_* / atom_htf_aligned_*
                    -- expand the BUY-context atoms above with all category × direction permutations.
                    -- *_score_* are the 0-10 weighted composites consumed by Phase B Mode A logging.
                    atom_kz_fav_mss_cont INTEGER DEFAULT 0,
                    atom_kz_fav_ote INTEGER DEFAULT 0,
                    atom_kz_fav_liq_sweep INTEGER DEFAULT 0,
                    atom_kz_fav_breaker INTEGER DEFAULT 0,
                    atom_htf_aligned_buy INTEGER DEFAULT 0,
                    atom_htf_aligned_sell INTEGER DEFAULT 0,
                    mss_cont_score_buy INTEGER DEFAULT 0,
                    mss_cont_score_sell INTEGER DEFAULT 0,
                    ote_retrace_score_buy INTEGER DEFAULT 0,
                    ote_retrace_score_sell INTEGER DEFAULT 0,
                    liq_sweep_rev_score_buy INTEGER DEFAULT 0,
                    liq_sweep_rev_score_sell INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_fs_time ON forge_signals(time);
                CREATE INDEX IF NOT EXISTS idx_fs_outcome ON forge_signals(outcome);
                CREATE INDEX IF NOT EXISTS idx_fs_gate ON forge_signals(gate_reason);
            """)
            log.info("SCRIBE migration: created forge_signals table")
        fs_cols = [r[1] for r in conn.execute("PRAGMA table_info(forge_signals)").fetchall()]
        if "journal_source" not in fs_cols:
            conn.execute("ALTER TABLE forge_signals ADD COLUMN journal_source TEXT DEFAULT 'live'")
            log.info("SCRIBE migration: added journal_source to forge_signals")
        if "run_id" not in fs_cols:
            conn.execute("ALTER TABLE forge_signals ADD COLUMN run_id INTEGER DEFAULT 0")
            log.info("SCRIBE migration: added run_id to forge_signals")
        if "wall_time" not in fs_cols:
            # wall_time = TESTER_RUNS.wall_time (GetTickCount64 at run start) — uniquely identifies
            # a real tester run even when the source journal DB is wiped and run_id resets to 1.
            # This is the "magic number + entropy" fix: prevents de-dup false positives across runs.
            conn.execute("ALTER TABLE forge_signals ADD COLUMN wall_time INTEGER DEFAULT 0")
            log.info("SCRIBE migration: added wall_time to forge_signals")
        if "aurum_run_id" not in fs_cols:
            # aurum_run_id — stable AURUM-level sequential ID from aurum_tester_runs table.
            # Use this for run filtering/grouping instead of run_id (which resets on source DB wipe).
            conn.execute("ALTER TABLE forge_signals ADD COLUMN aurum_run_id INTEGER DEFAULT 0")
            log.info("SCRIBE migration: added aurum_run_id to forge_signals")
        if "macd_histogram" not in fs_cols:
            # macd_histogram — H1 MACD histogram at signal time (added in FORGE 2.7.12).
            conn.execute("ALTER TABLE forge_signals ADD COLUMN macd_histogram REAL")
            log.info("SCRIBE migration: added macd_histogram to forge_signals")
        if "m15_adx" not in fs_cols:
            # m15_adx — M15 ADX at signal time for multi-TF context.
            conn.execute("ALTER TABLE forge_signals ADD COLUMN m15_adx REAL")
            log.info("SCRIBE migration: added m15_adx to forge_signals")
        if "lot_factor" not in fs_cols:
            # lot_factor — combined lot factor applied at entry (product of all lot modifiers).
            conn.execute("ALTER TABLE forge_signals ADD COLUMN lot_factor REAL")
            log.info("SCRIBE migration: added lot_factor to forge_signals")
        if "killzone" not in fs_cols:
            # killzone — ICT killzone label at signal time (added in FORGE 2.7.36).
            conn.execute("ALTER TABLE forge_signals ADD COLUMN killzone TEXT DEFAULT ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fs_killzone ON forge_signals(killzone)")
            log.info("SCRIBE migration: added killzone to forge_signals")
        if "minutes_into_kz" not in fs_cols:
            # minutes_into_kz — minutes since current killzone started, for Judas-window
            # detection + retrospective composite validation (added in FORGE 2.7.45 per
            # FORGE_REGIME_TAXONOMY.md §11.6).
            conn.execute("ALTER TABLE forge_signals ADD COLUMN minutes_into_kz INTEGER DEFAULT 0")
            log.info("SCRIBE migration: added minutes_into_kz to forge_signals")
        # 2.7.47 — RegimeState surfacing (FORGE_REGIME_TAXONOMY.md §3): 3 NEW regime fields
        if "htf_h1_strong" not in fs_cols:
            conn.execute("ALTER TABLE forge_signals ADD COLUMN htf_h1_strong INTEGER DEFAULT 0")
            log.info("SCRIBE migration: added htf_h1_strong to forge_signals")
        if "intraday_label" not in fs_cols:
            conn.execute("ALTER TABLE forge_signals ADD COLUMN intraday_label TEXT DEFAULT ''")
            log.info("SCRIBE migration: added intraday_label to forge_signals")
        if "intraday_counter_htf" not in fs_cols:
            conn.execute("ALTER TABLE forge_signals ADD COLUMN intraday_counter_htf INTEGER DEFAULT 0")
            log.info("SCRIBE migration: added intraday_counter_htf to forge_signals")
        # 2.7.37 — Layer-4 atom telemetry (24 cols; closes Decision Stack §6 gap)
        _v37_cols = [
            ("h4_trend",       "REAL"),
            ("m15_trend",      "REAL"),
            ("h1_di_balance",  "REAL"),
            ("day_open",       "REAL"),
            ("day_high",       "REAL"),
            ("day_low",        "REAL"),
            ("m5_open_1",      "REAL"),
            ("m5_high_1",      "REAL"),
            ("m5_low_1",       "REAL"),
            ("m5_close_1",     "REAL"),
            ("m5_lh_cascade",  "INTEGER DEFAULT 0"),
            ("m5_hl_cascade",  "INTEGER DEFAULT 0"),
            ("m5_body_pct",    "REAL"),
            ("h1_di_plus",     "REAL"),
            ("h1_di_minus",    "REAL"),
            ("h4_rsi",         "REAL"),
            ("h4_adx",         "REAL"),
            ("m30_trend",      "REAL"),
            ("d1_open",        "REAL"),
            ("d1_close",       "REAL"),
            ("h1_atr",         "REAL"),
            ("h4_atr",         "REAL"),
            ("m15_atr",        "REAL"),
            ("m1_atr",         "REAL"),
        ]
        for _col, _decl in _v37_cols:
            if _col not in fs_cols:
                try:
                    conn.execute(f"ALTER TABLE forge_signals ADD COLUMN {_col} {_decl}")
                    log.info("SCRIBE migration: added %s to forge_signals", _col)
                except sqlite3.OperationalError as _e:
                    # Concurrent migration race: another Scribe() init added the col
                    # between our fs_cols snapshot and this ALTER. Idempotent skip.
                    if "duplicate column" not in str(_e).lower():
                        raise
        # 2.7.37 Group 3 — full per-TF indicator + OHLC + bar-quality inventory (45 cols)
        _v37g3_cols = [
            ("h1_rsi", "REAL"), ("h1_adx", "REAL"),
            ("h1_bb_u", "REAL"), ("h1_bb_m", "REAL"), ("h1_bb_l", "REAL"),
            ("h4_bb_u", "REAL"), ("h4_bb_m", "REAL"), ("h4_bb_l", "REAL"),
            ("m15_rsi", "REAL"), ("m15_ema20", "REAL"), ("m15_ema50", "REAL"),
            ("m30_rsi", "REAL"), ("m30_adx", "REAL"), ("m30_atr", "REAL"),
            ("m30_ema20", "REAL"), ("m30_ema50", "REAL"),
            ("m1_ema20", "REAL"), ("m1_ema50", "REAL"),
            ("m5_open_0", "REAL"), ("m5_high_0", "REAL"), ("m5_low_0", "REAL"), ("m5_close_0", "REAL"),
            ("m15_open", "REAL"), ("m15_high", "REAL"), ("m15_low", "REAL"), ("m15_close", "REAL"),
            ("m30_open", "REAL"), ("m30_high", "REAL"), ("m30_low", "REAL"), ("m30_close", "REAL"),
            ("h1_open", "REAL"), ("h1_high", "REAL"), ("h1_low", "REAL"), ("h1_close", "REAL"),
            ("h4_open", "REAL"), ("h4_high", "REAL"), ("h4_low", "REAL"), ("h4_close", "REAL"),
            ("m5_inside_bar", "INTEGER DEFAULT 0"),
            ("m5_outside_bar", "INTEGER DEFAULT 0"),
            ("m5_doji", "INTEGER DEFAULT 0"),
            ("m5_strong_bar", "INTEGER DEFAULT 0"),
            ("long_lower_wick", "INTEGER DEFAULT 0"),
            ("long_upper_wick", "INTEGER DEFAULT 0"),
            ("m5_range_expanding", "INTEGER DEFAULT 0"),
        ]
        for _col, _decl in _v37g3_cols:
            if _col not in fs_cols:
                try:
                    conn.execute(f"ALTER TABLE forge_signals ADD COLUMN {_col} {_decl}")
                    log.info("SCRIBE migration: added %s to forge_signals", _col)
                except sqlite3.OperationalError as _e:
                    # Idempotent under concurrent Scribe() init (see _v37_cols loop)
                    if "duplicate column" not in str(_e).lower():
                        raise
        # 2.7.110 — CES (Confluence Entry Score) — 7 INTEGER cols (default 0)
        _v110_ces_cols = [
            ("ces_score",    "INTEGER DEFAULT 0"),
            ("ces_dtc",      "INTEGER DEFAULT 0"),
            ("ces_pemcg",    "INTEGER DEFAULT 0"),
            ("ces_momentum", "INTEGER DEFAULT 0"),
            ("ces_rsi",      "INTEGER DEFAULT 0"),
            ("ces_vwap",     "INTEGER DEFAULT 0"),
            ("ces_di",       "INTEGER DEFAULT 0"),
        ]
        for _col, _decl in _v110_ces_cols:
            if _col not in fs_cols:
                try:
                    conn.execute(f"ALTER TABLE forge_signals ADD COLUMN {_col} {_decl}")
                    log.info("SCRIBE migration: added %s to forge_signals", _col)
                except sqlite3.OperationalError as _e:
                    if "duplicate column" not in str(_e).lower():
                        raise
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fs_ces_score ON forge_signals(ces_score)")
        # v2.7.112 — ISS (ICT Structure Score) scaffolding columns (5 INTEGERs).
        #   Retroactive migration: ISS columns were declared in FORGE SIGNALS CREATE
        #   TABLE text at v2.7.112 but never had ALTERs on the FORGE side, AND were
        #   never wired into scribe forge_signals at all. v2.7.119 lands both.
        _v112_iss_cols = [
            ("iss_score",         "INTEGER DEFAULT 0"),
            ("iss_mss",           "INTEGER DEFAULT 0"),
            ("iss_fvg",           "INTEGER DEFAULT 0"),
            ("iss_choch_support", "INTEGER DEFAULT 0"),
            ("iss_choch_against", "INTEGER DEFAULT 0"),
        ]
        for _col, _decl in _v112_iss_cols:
            if _col not in fs_cols:
                try:
                    conn.execute(f"ALTER TABLE forge_signals ADD COLUMN {_col} {_decl}")
                    log.info("SCRIBE migration: added %s to forge_signals", _col)
                except sqlite3.OperationalError as _e:
                    if "duplicate column" not in str(_e).lower():
                        raise
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fs_iss_score ON forge_signals(iss_score)")
        # v2.7.119 — ICT Phase-1 atom context (9 cols; LOG-ONLY, no gate behaviour).
        #   Captured at the FORGE setup-trigger chokepoint and bound by JournalRecordSignal
        #   alongside the 5 iss_* atoms. With ict_*_enabled=0 defaults all values are 0.
        _v119_ict_ctx_cols = [
            ("ict_mss_swing_price",       "REAL DEFAULT 0"),
            ("ict_mss_displacement_atr",  "REAL DEFAULT 0"),
            ("ict_fvg_count_active",      "INTEGER DEFAULT 0"),
            ("ict_fvg_active_upper",      "REAL DEFAULT 0"),
            ("ict_fvg_active_lower",      "REAL DEFAULT 0"),
            ("ict_fvg_midpoint_dist_atr", "REAL DEFAULT 0"),
            ("ict_fvg_age_bars",          "INTEGER DEFAULT 0"),
            ("ict_recent_swing_high",     "REAL DEFAULT 0"),
            ("ict_recent_swing_low",      "REAL DEFAULT 0"),
        ]
        for _col, _decl in _v119_ict_ctx_cols:
            if _col not in fs_cols:
                try:
                    conn.execute(f"ALTER TABLE forge_signals ADD COLUMN {_col} {_decl}")
                    log.info("SCRIBE migration: added %s to forge_signals", _col)
                except sqlite3.OperationalError as _e:
                    if "duplicate column" not in str(_e).lower():
                        raise
        # v2.7.120 — ICT Phase-2 atom context (8 cols; LOG-ONLY).
        #   ChoCH event counters, liquidity-sweep state, equal-H/L cluster sizes,
        #   killzone enum. Captured by FORGE.mq5 chokepoint via g_ict_last_*
        #   globals from Forge\IctLiquidity.mqh. With both Phase-2 master flags=0
        #   defaults all values are 0 (schema-parity byte-stable vs v2.7.119).
        _v120_ict_p2_cols = [
            ("ict_choch_buy_count",        "INTEGER DEFAULT 0"),
            ("ict_choch_sell_count",       "INTEGER DEFAULT 0"),
            ("ict_choch_level",            "REAL DEFAULT 0"),
            ("ict_liquidity_sweep_recent", "INTEGER DEFAULT 0"),
            ("ict_sweep_level",            "REAL DEFAULT 0"),
            ("ict_equal_highs_count",      "INTEGER DEFAULT 0"),
            ("ict_equal_lows_count",       "INTEGER DEFAULT 0"),
            ("ict_killzone_active",        "INTEGER DEFAULT 0"),
        ]
        for _col, _decl in _v120_ict_p2_cols:
            if _col not in fs_cols:
                try:
                    conn.execute(f"ALTER TABLE forge_signals ADD COLUMN {_col} {_decl}")
                    log.info("SCRIBE migration: added %s to forge_signals", _col)
                except sqlite3.OperationalError as _e:
                    if "duplicate column" not in str(_e).lower():
                        raise
        # v2.7.122 — ict_sweep_rejection_score (1 REAL col; LOG-ONLY).
        #   0..1 wick-quality score from ScoreLiquiditySweep (Forge\IctLiquidity.mqh).
        #   Computed at chokepoint into g_ict_last_sweep_rejection_score, bound by
        #   JournalRecordSignal. Default 0 keeps pre-v2.7.122 rows valid.
        if "ict_sweep_rejection_score" not in fs_cols:
            try:
                conn.execute("ALTER TABLE forge_signals ADD COLUMN ict_sweep_rejection_score REAL DEFAULT 0")
                log.info("SCRIBE migration: added ict_sweep_rejection_score to forge_signals")
            except sqlite3.OperationalError as _e:
                if "duplicate column" not in str(_e).lower():
                    raise
        # v2.7.122 — Pre-TP1 recovery armed flag (1 INTEGER col; LOG-ONLY).
        #   Set inside ArmPreTP1Recovery (ea/FORGE.mq5) on successful OrderSend, cleared
        #   at top of each tick's ManageOpenGroups. Captured in SIGNALS via
        #   JournalRecordSignal. Default 0 keeps pre-v2.7.122 rows valid.
        if "pre_tp1_recovery_armed" not in fs_cols:
            try:
                conn.execute("ALTER TABLE forge_signals ADD COLUMN pre_tp1_recovery_armed INTEGER DEFAULT 0")
                log.info("SCRIBE migration: added pre_tp1_recovery_armed to forge_signals")
            except sqlite3.OperationalError as _e:
                if "duplicate column" not in str(_e).lower():
                    raise
        # v2.7.123 — Phase A ICT atom outputs (5 INTEGER cols; LOG-ONLY, Mode A).
        #   atom_* prefix per docs/FORGE_SETUP_ICT_MAP.md §B.8.2 (not ict_atom_*).
        #   Captured by FORGE.mq5 ForgeEvalAtoms() with BUY-direction context into
        #   g_ict_last_atom_* globals; bound by JournalRecordSignal. With all 5
        #   enable flags off (defaults), every row logs 0 across these columns.
        _v123_atom_cols = [
            ("atom_killzone_favorable",       "INTEGER DEFAULT 0"),
            ("atom_htf_aligned",              "INTEGER DEFAULT 0"),
            ("atom_pullback_in_ote",          "INTEGER DEFAULT 0"),
            ("atom_premium_discount_aligned", "INTEGER DEFAULT 0"),
            ("atom_fvg_on_reversal_leg",      "INTEGER DEFAULT 0"),
        ]
        for _col, _decl in _v123_atom_cols:
            if _col not in fs_cols:
                try:
                    conn.execute(f"ALTER TABLE forge_signals ADD COLUMN {_col} {_decl}")
                    log.info("SCRIBE migration: added %s to forge_signals", _col)
                except sqlite3.OperationalError as _e:
                    if "duplicate column" not in str(_e).lower():
                        raise
        # v2.7.124 — Phase A expansion (6 INTEGERs) + Phase B composite scores (6 INTEGERs).
        #   Per docs/FORGE_SETUP_ICT_MAP.md §B.8.2. Idempotent ALTERs — no-op on existing rows.
        _v124_atom_score_cols = [
            ("atom_kz_fav_mss_cont",        "INTEGER DEFAULT 0"),
            ("atom_kz_fav_ote",             "INTEGER DEFAULT 0"),
            ("atom_kz_fav_liq_sweep",       "INTEGER DEFAULT 0"),
            ("atom_kz_fav_breaker",         "INTEGER DEFAULT 0"),
            ("atom_htf_aligned_buy",        "INTEGER DEFAULT 0"),
            ("atom_htf_aligned_sell",       "INTEGER DEFAULT 0"),
            ("mss_cont_score_buy",          "INTEGER DEFAULT 0"),
            ("mss_cont_score_sell",         "INTEGER DEFAULT 0"),
            ("ote_retrace_score_buy",       "INTEGER DEFAULT 0"),
            ("ote_retrace_score_sell",      "INTEGER DEFAULT 0"),
            ("liq_sweep_rev_score_buy",     "INTEGER DEFAULT 0"),
            ("liq_sweep_rev_score_sell",    "INTEGER DEFAULT 0"),
        ]
        for _col, _decl in _v124_atom_score_cols:
            if _col not in fs_cols:
                try:
                    conn.execute(f"ALTER TABLE forge_signals ADD COLUMN {_col} {_decl}")
                    log.info("SCRIBE migration: added %s to forge_signals", _col)
                except sqlite3.OperationalError as _e:
                    if "duplicate column" not in str(_e).lower():
                        raise
        # 2.7.37 — v37 telemetry indexes. CREATE INDEX IF NOT EXISTS is idempotent;
        # always run so fresh DBs (which pass the col-missing check) still get indexes.
        # Previously gated by `not in fs_cols` which left fresh tables index-less.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fs_h1_di_balance ON forge_signals(h1_di_balance)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fs_m5_cascade ON forge_signals(m5_lh_cascade, m5_hl_cascade)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fs_m5_inside ON forge_signals(m5_inside_bar)")
        # forge_journal_trades: create fresh with UNIQUE(deal_ticket, journal_source, run_id)
        # or migrate old schema (UNIQUE on deal_ticket+journal_source only) atomically.
        fjt_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='forge_journal_trades'"
        ).fetchone()
        if fjt_sql is None:
            # New table — UNIQUE uses wall_time (entropy) so runs accumulate even after source DB reset
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS forge_journal_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    forge_rowid INTEGER NOT NULL,
                    deal_ticket INTEGER NOT NULL,
                    order_ticket INTEGER,
                    symbol TEXT NOT NULL,
                    type INTEGER,
                    direction INTEGER,
                    volume REAL,
                    price REAL,
                    profit REAL,
                    swap REAL,
                    commission REAL,
                    magic INTEGER,
                    comment TEXT,
                    time INTEGER NOT NULL,
                    time_msc INTEGER,
                    journal_source TEXT DEFAULT 'live',
                    run_id INTEGER DEFAULT 0,
                    wall_time INTEGER DEFAULT 0,
                    UNIQUE(deal_ticket, journal_source, wall_time)
                );
                CREATE INDEX IF NOT EXISTS idx_fjt_time ON forge_journal_trades(time);
                CREATE INDEX IF NOT EXISTS idx_fjt_magic ON forge_journal_trades(magic);
                CREATE INDEX IF NOT EXISTS idx_fjt_run ON forge_journal_trades(run_id);
                CREATE INDEX IF NOT EXISTS idx_fjt_wall ON forge_journal_trades(wall_time);
            """)
            log.info("SCRIBE migration: created forge_journal_trades with UNIQUE(deal_ticket,journal_source,wall_time)")
        elif "wall_time" not in fjt_sql[0]:
            # Upgrade schema: add wall_time + change UNIQUE to use wall_time as entropy
            # wall_time = TESTER_RUNS.wall_time (GetTickCount64) — unique per real run even when
            # the source journal DB is wiped and deal_ticket/run_id reset to 1.
            conn.executescript("""
                ALTER TABLE forge_journal_trades RENAME TO _fjt_old;
                CREATE TABLE forge_journal_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    forge_rowid INTEGER NOT NULL,
                    deal_ticket INTEGER NOT NULL,
                    order_ticket INTEGER,
                    symbol TEXT NOT NULL,
                    type INTEGER,
                    direction INTEGER,
                    volume REAL,
                    price REAL,
                    profit REAL,
                    swap REAL,
                    commission REAL,
                    magic INTEGER,
                    comment TEXT,
                    time INTEGER NOT NULL,
                    time_msc INTEGER,
                    journal_source TEXT DEFAULT 'live',
                    run_id INTEGER DEFAULT 0,
                    wall_time INTEGER DEFAULT 0,
                    UNIQUE(deal_ticket, journal_source, wall_time)
                );
                INSERT INTO forge_journal_trades
                    SELECT id, forge_rowid, deal_ticket, order_ticket, symbol,
                           type, direction, volume, price, profit, swap,
                           commission, magic, comment, time, time_msc,
                           COALESCE(journal_source,'live'), COALESCE(run_id,0), 0
                    FROM _fjt_old;
                DROP TABLE _fjt_old;
                CREATE INDEX IF NOT EXISTS idx_fjt_time ON forge_journal_trades(time);
                CREATE INDEX IF NOT EXISTS idx_fjt_magic ON forge_journal_trades(magic);
                CREATE INDEX IF NOT EXISTS idx_fjt_run ON forge_journal_trades(run_id);
                CREATE INDEX IF NOT EXISTS idx_fjt_wall ON forge_journal_trades(wall_time);
            """)
            log.info("SCRIBE migration: forge_journal_trades upgraded to UNIQUE(deal_ticket,journal_source,wall_time)")
        else:
            # Correct schema already — just ensure indexes
            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_fjt_time ON forge_journal_trades(time);
                CREATE INDEX IF NOT EXISTS idx_fjt_magic ON forge_journal_trades(magic);
                CREATE INDEX IF NOT EXISTS idx_fjt_run ON forge_journal_trades(run_id);
                CREATE INDEX IF NOT EXISTS idx_fjt_wall ON forge_journal_trades(wall_time);
            """)
        fjt_cols = [r[1] for r in conn.execute("PRAGMA table_info(forge_journal_trades)").fetchall()]
        if "aurum_run_id" not in fjt_cols:
            conn.execute("ALTER TABLE forge_journal_trades ADD COLUMN aurum_run_id INTEGER DEFAULT 0")
            log.info("SCRIBE migration: added aurum_run_id to forge_journal_trades")
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
        tg_cols2 = [r[1] for r in conn.execute("PRAGMA table_info(trade_groups)").fetchall()]
        if "trades_range_min" not in tg_cols2:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN trades_range_min INTEGER")
            log.info("SCRIBE migration: added trades_range_min to trade_groups")
        if "trades_range_max" not in tg_cols2:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN trades_range_max INTEGER")
            log.info("SCRIBE migration: added trades_range_max to trade_groups")
        if "trades_policy_reason" not in tg_cols2:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN trades_policy_reason TEXT")
            log.info("SCRIBE migration: added trades_policy_reason to trade_groups")
        tg_cols3 = [r[1] for r in conn.execute("PRAGMA table_info(trade_groups)").fetchall()]
        if "open_context" not in tg_cols3:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN open_context TEXT")
            log.info("SCRIBE migration: added open_context to trade_groups (JSON attribution snapshot)")
        # ── Pip value USD columns ───────────────────────────────────
        # trade_closures: pip_value_usd (signed USD value of pip move)
        tc_cols = [r[1] for r in conn.execute("PRAGMA table_info(trade_closures)").fetchall()]
        if "pip_value_usd" not in tc_cols:
            conn.execute("ALTER TABLE trade_closures ADD COLUMN pip_value_usd REAL")
            log.info("SCRIBE migration: added pip_value_usd to trade_closures")
        # trade_positions: pip_value_usd + comment
        tp_cols = [r[1] for r in conn.execute("PRAGMA table_info(trade_positions)").fetchall()]
        if "pip_value_usd" not in tp_cols:
            conn.execute("ALTER TABLE trade_positions ADD COLUMN pip_value_usd REAL")
            log.info("SCRIBE migration: added pip_value_usd to trade_positions")
        if "comment" not in tp_cols:
            conn.execute("ALTER TABLE trade_positions ADD COLUMN comment TEXT")
            log.info("SCRIBE migration: added comment to trade_positions")
        # trade_groups: total_pip_value_usd (sum across all closed legs)
        tg_cols4 = [r[1] for r in conn.execute("PRAGMA table_info(trade_groups)").fetchall()]
        if "total_pip_value_usd" not in tg_cols4:
            conn.execute("ALTER TABLE trade_groups ADD COLUMN total_pip_value_usd REAL")
            log.info("SCRIBE migration: added total_pip_value_usd to trade_groups")

    @staticmethod
    def _serialize_open_context(value) -> str | None:
        """JSON for SQLite TEXT; caps size (see SCRIBE_OPEN_CONTEXT_MAX_BYTES)."""
        if value is None:
            return None
        raw_lim = os.environ.get("SCRIBE_OPEN_CONTEXT_MAX_BYTES", "65536").strip()
        try:
            lim = int(raw_lim)
        except ValueError:
            lim = 65536
        lim = max(64, lim)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
        else:
            try:
                text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
            except (TypeError, ValueError):
                return None
        raw = text.encode("utf-8")
        if len(raw) <= lim:
            return text
        log.warning(
            "SCRIBE: open_context oversized (%d bytes > %d); storing stub JSON",
            len(raw),
            lim,
        )
        stub = {
            "open_context_version": 1,
            "truncated": True,
            "original_bytes": len(raw),
            "limit_bytes": lim,
        }
        return json.dumps(stub, separators=(",", ":"))

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

    # Per-instance caches to avoid repeated PRAGMA/migration overhead across sync calls
    _fj_src_cols_cache: dict = {}      # path → frozenset of source column names
    _fj_wall_time_cache: dict = {}     # path → {run_id: wall_time}
    _fj_aurum_run_cache: dict = {}     # path → {wall_time: aurum_run_id}
    _fj_dedup_index: dict = {}         # (db_path, source) → set of (forge_id, wall_time)

    def sync_forge_journal(self, journal_db_path: str, source: str = "live", batch_size: int = 2000) -> int:
        """Read unsynced SIGNALS from FORGE journal DB, insert into forge_signals.

        Optimisations vs naïve version:
        - Column detection and migration cached per DB path (one-time PRAGMA)
        - TESTER_RUNS wall_time map cached per DB path; refreshed only when new run_id appears
        - Batch de-dup: existing (forge_id, wall_time) pairs loaded once into a Python set
          instead of one SELECT per row — eliminates N round-trips to SQLite
        - executemany for all INSERTs (one round-trip for the whole batch)
        - Unique index on (forge_id, journal_source, wall_time) ensures INSERT OR IGNORE
          is safe as a fallback even if the set misses a row (e.g. after restart)
        """
        from pathlib import Path as _P
        if not _P(journal_db_path).exists():
            return 0, 0

        import sqlite3 as _sqlite3
        from datetime import datetime, timezone as _tz
        try:
            src = _sqlite3.connect(journal_db_path, timeout=5)
            src.execute("PRAGMA journal_mode=WAL")   # allow concurrent tester writes
        except Exception as e:
            log.warning("SCRIBE sync_forge_journal: cannot open %s — %s", journal_db_path, e)
            return 0, 0

        try:
            # ── 1. One-time PRAGMA + migration (cached per DB path) ──────────
            cache_key = journal_db_path
            if cache_key not in self._fj_src_cols_cache:
                src_cols = frozenset(r[1] for r in src.execute("PRAGMA table_info(SIGNALS)").fetchall())
                self._fj_src_cols_cache[cache_key] = src_cols
                # Ensure UNIQUE index on destination for safe INSERT OR IGNORE
                try:
                    with self._conn() as _c:
                        _c.execute(
                            "CREATE UNIQUE INDEX IF NOT EXISTS idx_fs_dedup "
                            "ON forge_signals(forge_id, journal_source, wall_time)"
                        )
                except Exception:
                    pass
            src_cols = self._fj_src_cols_cache[cache_key]
            has_run_id     = "run_id"         in src_cols
            has_macd_hist  = "macd_histogram" in src_cols
            has_m15_adx    = "m15_adx"        in src_cols
            has_lot_factor = "lot_factor"      in src_cols
            has_killzone   = "killzone"       in src_cols
            has_min_into_kz = "minutes_into_kz" in src_cols
            # 2.7.47 — RegimeState surfacing (FORGE_REGIME_TAXONOMY.md §3) — all-or-nothing trio
            has_regime_v47 = all(c in src_cols for c in ("htf_h1_strong", "intraday_label", "intraday_counter_htf"))
            # 2.7.37 — detect Layer-4 atom telemetry columns on source SIGNALS
            v37_cols = [
                "h4_trend", "m15_trend", "h1_di_balance",
                "day_open", "day_high", "day_low",
                "m5_open_1", "m5_high_1", "m5_low_1", "m5_close_1",
                "m5_lh_cascade", "m5_hl_cascade", "m5_body_pct",
                "h1_di_plus", "h1_di_minus", "h4_rsi", "h4_adx", "m30_trend",
                "d1_open", "d1_close", "h1_atr", "h4_atr", "m15_atr", "m1_atr",
            ]
            has_v37 = all(c in src_cols for c in v37_cols)
            # 2.7.37 Group 3 — full per-TF inventory (45 cols, additive on top of v37)
            v37g3_cols = [
                "h1_rsi", "h1_adx", "h1_bb_u", "h1_bb_m", "h1_bb_l",
                "h4_bb_u", "h4_bb_m", "h4_bb_l",
                "m15_rsi", "m15_ema20", "m15_ema50",
                "m30_rsi", "m30_adx", "m30_atr", "m30_ema20", "m30_ema50",
                "m1_ema20", "m1_ema50",
                "m5_open_0", "m5_high_0", "m5_low_0", "m5_close_0",
                "m15_open", "m15_high", "m15_low", "m15_close",
                "m30_open", "m30_high", "m30_low", "m30_close",
                "h1_open", "h1_high", "h1_low", "h1_close",
                "h4_open", "h4_high", "h4_low", "h4_close",
                "m5_inside_bar", "m5_outside_bar", "m5_doji", "m5_strong_bar",
                "long_lower_wick", "long_upper_wick", "m5_range_expanding",
            ]
            has_v37g3 = all(c in src_cols for c in v37g3_cols)
            # 2.7.110 — CES (Confluence Entry Score) — 7 INTEGER cols, all-or-nothing (same pattern as v37g3)
            v110_ces_cols = [
                "ces_score", "ces_dtc", "ces_pemcg",
                "ces_momentum", "ces_rsi", "ces_vwap", "ces_di",
            ]
            has_v110_ces = all(c in src_cols for c in v110_ces_cols)
            # 2.7.112 — ISS (ICT Structure Score) — 5 INTEGER cols (retroactive ALTER in v2.7.119)
            v112_iss_cols = [
                "iss_score", "iss_mss", "iss_fvg",
                "iss_choch_support", "iss_choch_against",
            ]
            has_v112_iss = all(c in src_cols for c in v112_iss_cols)
            # 2.7.119 — ICT Phase-1 atom context (9 cols; LOG-ONLY)
            v119_ict_ctx_cols = [
                "ict_mss_swing_price", "ict_mss_displacement_atr",
                "ict_fvg_count_active", "ict_fvg_active_upper",
                "ict_fvg_active_lower", "ict_fvg_midpoint_dist_atr",
                "ict_fvg_age_bars", "ict_recent_swing_high",
                "ict_recent_swing_low",
            ]
            has_v119_ict_ctx = all(c in src_cols for c in v119_ict_ctx_cols)
            # 2.7.120 — ICT Phase-2 atom context (8 cols; LOG-ONLY)
            v120_ict_p2_cols = [
                "ict_choch_buy_count", "ict_choch_sell_count",
                "ict_choch_level", "ict_liquidity_sweep_recent",
                "ict_sweep_level", "ict_equal_highs_count",
                "ict_equal_lows_count", "ict_killzone_active",
            ]
            has_v120_ict_p2 = all(c in src_cols for c in v120_ict_p2_cols)
            # v2.7.122 — ict_sweep_rejection_score (1 REAL col; LOG-ONLY).
            #   0..1 wick-quality score from ScoreLiquiditySweep. Wired in v2.7.122
            #   alongside pre_tp1_recovery_armed.
            has_ict_sweep_rej = "ict_sweep_rejection_score" in src_cols
            # v2.7.122 — Pre-TP1 recovery armed flag (1 INTEGER col; LOG-ONLY)
            has_pre_tp1_recov = "pre_tp1_recovery_armed" in src_cols
            # v2.7.123 — Phase A ICT atom outputs (5 INTEGER cols; LOG-ONLY, Mode A).
            #   atom_* prefix (not ict_atom_*) per docs/FORGE_SETUP_ICT_MAP.md §B.8.2.
            v123_atom_cols = [
                "atom_killzone_favorable", "atom_htf_aligned",
                "atom_pullback_in_ote", "atom_premium_discount_aligned",
                "atom_fvg_on_reversal_leg",
            ]
            has_v123_atoms = all(c in src_cols for c in v123_atom_cols)
            # v2.7.124 — Phase A expansion (6) + Phase B composite scores (6) = 12 INTEGER cols.
            #   Per docs/FORGE_SETUP_ICT_MAP.md §B.8.2. All-or-nothing presence check; if any
            #   column is missing on the source we fall back to 0s.
            v124_atom_score_cols = [
                "atom_kz_fav_mss_cont", "atom_kz_fav_ote",
                "atom_kz_fav_liq_sweep", "atom_kz_fav_breaker",
                "atom_htf_aligned_buy", "atom_htf_aligned_sell",
                "mss_cont_score_buy", "mss_cont_score_sell",
                "ote_retrace_score_buy", "ote_retrace_score_sell",
                "liq_sweep_rev_score_buy", "liq_sweep_rev_score_sell",
            ]
            has_v124_atom_scores = all(c in src_cols for c in v124_atom_score_cols)

            # ── 2. wall_time map (cached; refresh when new run_id seen) ──────
            wall_time_map  = self._fj_wall_time_cache.get(cache_key, {0: 0})
            aurum_run_id_map = self._fj_aurum_run_cache.get(cache_key, {0: 0})
            tester_runs_meta: dict = {}
            # Track which run_ids got a NEW wall_time this cycle — these need
            # their source SIGNALS reset to synced=0 so the full run re-syncs
            # under the new aurum_run_id (MT5 never clears SIGNALS between runs).
            new_wall_time_run_ids: list[int] = []
            try:
                tr_cols = frozenset(r[1] for r in src.execute("PRAGMA table_info(TESTER_RUNS)").fetchall())
                tr_select = (
                    "SELECT id, wall_time"
                    + (", sim_start_time" if "sim_start_time" in tr_cols else ", NULL")
                    + (", symbol"         if "symbol"         in tr_cols else ", NULL")
                    + (", balance"        if "balance"        in tr_cols else ", NULL")
                    + (", forge_version"  if "forge_version"  in tr_cols else ", NULL")
                    + (", scalper_mode"   if "scalper_mode"   in tr_cols else ", NULL")
                    + (", magic_base"     if "magic_base"     in tr_cols else ", NULL")
                    + " FROM TESTER_RUNS"
                )
                for tr in src.execute(tr_select).fetchall():
                    rid, wt = int(tr[0]), int(tr[1] or 0)
                    prev_wt = wall_time_map.get(rid)
                    if prev_wt is None:
                        # First time we see this run_id — treat as new run
                        wall_time_map[rid] = wt
                        tester_runs_meta[wt] = {
                            "source_run_id": rid, "sim_start_time": tr[2],
                            "symbol": tr[3], "balance": tr[4],
                            "forge_version": tr[5], "scalper_mode": tr[6], "magic_base": tr[7],
                        }
                        new_wall_time_run_ids.append(rid)
                    elif prev_wt != wt:
                        # wall_time changed → MT5 started a new tester run on this run_id.
                        # Old SIGNALS rows still exist with synced=1 from the previous run.
                        # Reset them so the full new run gets re-synced under the new aurum_run_id.
                        wall_time_map[rid] = wt
                        tester_runs_meta[wt] = {
                            "source_run_id": rid, "sim_start_time": tr[2],
                            "symbol": tr[3], "balance": tr[4],
                            "forge_version": tr[5], "scalper_mode": tr[6], "magic_base": tr[7],
                        }
                        new_wall_time_run_ids.append(rid)
                        # Invalidate the dedup cache for this source so it rebuilds
                        self._fj_dedup_index.pop((cache_key, source), None)

            except Exception:
                pass  # live DB has no TESTER_RUNS

            # Reset synced=0 for all signals belonging to run_ids with a new wall_time
            if new_wall_time_run_ids:
                try:
                    placeholders = ",".join("?" * len(new_wall_time_run_ids))
                    reset_count = src.execute(
                        f"UPDATE SIGNALS SET synced=0 WHERE run_id IN ({placeholders}) AND synced=1",
                        tuple(new_wall_time_run_ids),
                    ).rowcount
                    src.commit()
                    if reset_count:
                        log.info(
                            "SCRIBE: new TESTER_RUNS wall_time detected — reset %d SIGNALS "
                            "to synced=0 for full re-sync under new aurum_run_id (run_ids=%s)",
                            reset_count, new_wall_time_run_ids,
                        )
                except Exception as _e:
                    log.debug("SCRIBE: synced-reset on new wall_time failed: %s", _e)

            # Register any new wall_times into aurum_tester_runs
            if tester_runs_meta:
                with self._conn() as c:
                    for wt, meta in tester_runs_meta.items():
                        if wt == 0 or wt in aurum_run_id_map:
                            continue
                        existing = c.execute(
                            "SELECT aurum_run_id FROM aurum_tester_runs WHERE wall_time=? LIMIT 1", (wt,)
                        ).fetchone()
                        if existing:
                            aurum_run_id_map[wt] = existing[0]
                        else:
                            cur = c.execute(
                                "INSERT INTO aurum_tester_runs "
                                "(wall_time, source_run_id, journal_source, symbol, forge_version, "
                                "scalper_mode, balance, sim_start_time, magic_base, first_seen_utc) "
                                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                                (wt, meta["source_run_id"], source, meta["symbol"],
                                 meta["forge_version"], meta["scalper_mode"], meta["balance"],
                                 meta["sim_start_time"], meta["magic_base"],
                                 datetime.now(_tz.utc).isoformat()),
                            )
                            aurum_run_id_map[wt] = cur.lastrowid
                            log.info("SCRIBE: registered aurum_run_id=%d wall_time=%d source=%s",
                                     cur.lastrowid, wt, source)
            self._fj_wall_time_cache[cache_key]  = wall_time_map
            self._fj_aurum_run_cache[cache_key]  = aurum_run_id_map

            # ── 2b. Fast-forward dedup hits in bulk ──────────────────────────
            # MT5 never clears SIGNALS between runs. After bridge restart or
            # SCRIBE re-init, the destination forge_signals can already contain
            # rows whose source SIGNALS.synced was never advanced past them
            # (e.g. crash mid-cycle). The row-by-row dedup loop below would
            # crawl through these at batch_size/cycle (5000 rows = 60s) —
            # at ~656k stale rows that's ~131 minutes before reaching truly-new
            # signals on a fresh run.
            #
            # Fast-forward: in one UPDATE, mark synced=1 in source for any row
            # whose (id, wall_time-for-that-run_id) already exists in destination
            # forge_signals. This collapses hours of dedup-crawl into one SQL.
            #
            # ATTACH is required because src is the journal DB and we need to
            # join against the destination forge_signals table.
            try:
                # Build a list of (source_run_id, wall_time) we know about.
                run_wt_pairs = [
                    (rid, wt) for rid, wt in wall_time_map.items()
                    if rid > 0 and wt > 0
                ]
                if run_wt_pairs:
                    dst_path = self.db_path
                    src.execute("ATTACH DATABASE ? AS dst", (dst_path,))
                    try:
                        ff_total = 0
                        for rid, wt in run_wt_pairs:
                            # Mark synced=1 in source for any row whose
                            # (id == dst.forge_id) and (wall_time matches) and
                            # not already synced. Limit per run to keep one
                            # transaction small.
                            cur = src.execute(
                                "UPDATE SIGNALS SET synced=1 "
                                "WHERE run_id=? AND synced=0 AND id IN ("
                                "  SELECT forge_id FROM dst.forge_signals "
                                "  WHERE journal_source=? AND wall_time=?"
                                ")",
                                (rid, source, wt),
                            )
                            ff_total += cur.rowcount
                        if ff_total:
                            src.commit()
                            log.info(
                                "SCRIBE fast-forward: marked %d source SIGNALS "
                                "as synced=1 (already present in destination, "
                                "source=%s)", ff_total, source,
                            )
                    finally:
                        try:
                            src.execute("DETACH DATABASE dst")
                        except Exception:
                            pass
            except Exception as _e:
                log.debug("SCRIBE fast-forward skipped: %s", _e)

            # ── 3. Fetch unsynced rows (large batch) ─────────────────────────
            select_sql = (
                "SELECT id, time, symbol, setup_type, direction, outcome, gate_reason, "
                "price, spread, atr, rsi, adx, bb_upper, bb_lower, bb_mid, "
                "poc_price, vwap_price, fib_50, rsi_divergence, psar_state, "
                "pattern_score, h1_trend, regime_label, regime_confidence, "
                "adx_trend_regime, high_vol_trend, session, magic"
                + (", run_id"         if has_run_id     else ", 0")
                + (", macd_histogram" if has_macd_hist  else ", NULL")
                + (", m15_adx"        if has_m15_adx    else ", NULL")
                + (", lot_factor"     if has_lot_factor  else ", NULL")
                + (", killzone"       if has_killzone   else ", ''")
                + (", minutes_into_kz" if has_min_into_kz else ", 0")
                # 2.7.47 — RegimeState trio (all-or-nothing) appended together
                + (", htf_h1_strong, intraday_label, intraday_counter_htf"
                   if has_regime_v47 else ", 0, '', 0")
                # 2.7.37 — all 24 atom telemetry cols appended together (all-or-nothing)
                + (", " + ", ".join(v37_cols) if has_v37 else ", " + ", ".join(["NULL"] * len(v37_cols)))
                # 2.7.37 Group 3 — 45 more cols, same all-or-nothing pattern
                + (", " + ", ".join(v37g3_cols) if has_v37g3 else ", " + ", ".join(["NULL"] * len(v37g3_cols)))
                # 2.7.110 — CES (Confluence Entry Score) — 7 INTEGER cols, same all-or-nothing pattern
                + (", " + ", ".join(v110_ces_cols) if has_v110_ces else ", " + ", ".join(["0"] * len(v110_ces_cols)))
                # 2.7.112 — ISS scaffolding — 5 INTEGER cols, all-or-nothing (retroactive ALTER in v2.7.119)
                + (", " + ", ".join(v112_iss_cols) if has_v112_iss else ", " + ", ".join(["0"] * len(v112_iss_cols)))
                # 2.7.119 — ICT Phase-1 atom context — 9 cols (REAL/INTEGER mixed), all-or-nothing
                + (", " + ", ".join(v119_ict_ctx_cols) if has_v119_ict_ctx else ", " + ", ".join(["0"] * len(v119_ict_ctx_cols)))
                # 2.7.120 — ICT Phase-2 atom context — 8 cols (REAL/INTEGER mixed), all-or-nothing
                + (", " + ", ".join(v120_ict_p2_cols) if has_v120_ict_p2 else ", " + ", ".join(["0"] * len(v120_ict_p2_cols)))
                # v2.7.122 — ict_sweep_rejection_score (1 REAL col; LOG-ONLY)
                + (", ict_sweep_rejection_score" if has_ict_sweep_rej else ", 0")
                # v2.7.122 — Pre-TP1 recovery armed flag (1 INTEGER col; LOG-ONLY)
                + (", pre_tp1_recovery_armed" if has_pre_tp1_recov else ", 0")
                # v2.7.123 — Phase A ICT atom outputs (5 INTEGER cols, all-or-nothing)
                + (", " + ", ".join(v123_atom_cols) if has_v123_atoms else ", " + ", ".join(["0"] * len(v123_atom_cols)))
                # v2.7.124 — Phase A expansion (6 cols) + Phase B composite scores (6 cols), all-or-nothing.
                + (", " + ", ".join(v124_atom_score_cols) if has_v124_atom_scores else ", " + ", ".join(["0"] * len(v124_atom_score_cols)))
                + f" FROM SIGNALS WHERE synced = 0 ORDER BY id LIMIT {max(1, int(batch_size))}"
            )
            rows = src.execute(select_sql).fetchall()
            if not rows:
                return 0, 0

            # ── 4. Batch de-dup: load existing keys into a Python set (1 query) ──
            dedup_key = (journal_db_path, source)
            if dedup_key not in self._fj_dedup_index:
                with self._conn() as _c:
                    existing_keys = {
                        (r[0], r[1])
                        for r in _c.execute(
                            "SELECT forge_id, wall_time FROM forge_signals WHERE journal_source=?",
                            (source,)
                        ).fetchall()
                    }
                self._fj_dedup_index[dedup_key] = existing_keys
            dedup_set = self._fj_dedup_index[dedup_key]

            # ── 5. Build insert params + mark synced ids ──────────────────────
            insert_params: list[tuple] = []
            synced_ids: list[int] = []
            for r in rows:
                run_id     = int(r[28] or 0)
                wall_time  = wall_time_map.get(run_id, 0)
                fid        = r[0]
                dedup_pair = (fid, wall_time)
                if dedup_pair in dedup_set:
                    synced_ids.append(fid)
                    continue
                ts_utc   = datetime.fromtimestamp(r[1], tz=_tz.utc).isoformat()
                aurum_rid = aurum_run_id_map.get(wall_time, 0)
                killzone_val = r[32] if len(r) > 32 else ""
                # 2.7.45 — minutes_into_kz at r[33] (FORGE_REGIME_TAXONOMY.md §11.6)
                min_into_kz_val = r[33] if len(r) > 33 else 0
                # 2.7.47 — RegimeState trio at r[34]..r[36] (FORGE_REGIME_TAXONOMY.md §3)
                htf_h1_strong_val      = r[34] if len(r) > 34 else 0
                intraday_label_val     = r[35] if len(r) > 35 else ""
                intraday_counter_htf_v = r[36] if len(r) > 36 else 0
                # 2.7.37 — 24 atom columns at positions r[37]..r[60] (was r[34]..r[57] before 2.7.47)
                v37_vals = tuple(r[37 + i] if len(r) > 37 + i else None for i in range(24))
                # 2.7.37 Group 3 — 45 more cols at positions r[61]..r[105] (was r[58]..r[102] before 2.7.47)
                v37g3_vals = tuple(r[61 + i] if len(r) > 61 + i else None for i in range(45))
                # 2.7.110 — CES — 7 INTEGER cols at positions r[106]..r[112]
                v110_ces_vals = tuple(r[106 + i] if len(r) > 106 + i else 0 for i in range(7))
                # 2.7.112 — ISS scaffolding — 5 INTEGER cols at positions r[113]..r[117]
                v112_iss_vals = tuple(r[113 + i] if len(r) > 113 + i else 0 for i in range(5))
                # 2.7.119 — ICT Phase-1 atom context — 9 cols at positions r[118]..r[126].
                #   ict_fvg_count_active and ict_fvg_age_bars are INTEGERs in the source schema
                #   (default 0). The remaining 7 cols are REALs (default 0.0). sqlite3 handles
                #   both via the same param binding — just preserve the source row value.
                v119_ict_ctx_vals = tuple(r[118 + i] if len(r) > 118 + i else 0 for i in range(9))
                # 2.7.120 — ICT Phase-2 atom context — 8 cols at positions r[127]..r[134].
                #   Mix of INTEGERs (counts, killzone enum, sweep-recent flag) and REALs
                #   (level prices). sqlite3 handles both via the same param binding.
                v120_ict_p2_vals = tuple(r[127 + i] if len(r) > 127 + i else 0 for i in range(8))
                # v2.7.122 — ict_sweep_rejection_score at r[135] (1 REAL col; 0..1 wick quality)
                ict_sweep_rej_val = r[135] if len(r) > 135 else 0
                # v2.7.122 — Pre-TP1 recovery armed flag at r[136] (1 INTEGER col)
                pre_tp1_recov_val = r[136] if len(r) > 136 else 0
                # v2.7.123 — Phase A ICT atom outputs (5 INTEGERs) at positions r[137]..r[141].
                #   Per docs/FORGE_SETUP_ICT_MAP.md §B.8.2. SELECT order is fixed by
                #   v123_atom_cols list above: killzone_favorable, htf_aligned,
                #   pullback_in_ote, premium_discount_aligned, fvg_on_reversal_leg.
                v123_atom_vals = tuple(r[137 + i] if len(r) > 137 + i else 0 for i in range(5))
                # v2.7.124 — Phase A expansion (6 INTEGERs) + Phase B composite scores (6
                #   INTEGERs) at positions r[142]..r[153]. SELECT order fixed by
                #   v124_atom_score_cols list above: atom_kz_fav_mss_cont,
                #   atom_kz_fav_ote, atom_kz_fav_liq_sweep, atom_kz_fav_breaker,
                #   atom_htf_aligned_buy, atom_htf_aligned_sell, mss_cont_score_buy,
                #   mss_cont_score_sell, ote_retrace_score_buy, ote_retrace_score_sell,
                #   liq_sweep_rev_score_buy, liq_sweep_rev_score_sell.
                v124_atom_score_vals = tuple(r[142 + i] if len(r) > 142 + i else 0 for i in range(12))
                insert_params.append((
                    fid, r[1], ts_utc, *r[2:28], source, run_id,
                    r[29], r[30], r[31], wall_time, aurum_rid, killzone_val, min_into_kz_val,
                    htf_h1_strong_val, intraday_label_val, intraday_counter_htf_v,
                    *v37_vals, *v37g3_vals, *v110_ces_vals,
                    *v112_iss_vals, *v119_ict_ctx_vals, *v120_ict_p2_vals,
                    ict_sweep_rej_val,
                    pre_tp1_recov_val,
                    *v123_atom_vals,
                    *v124_atom_score_vals,
                ))
                synced_ids.append(fid)
                dedup_set.add(dedup_pair)  # update in-place so next batch sees it

            # ── 6. executemany INSERT + one UPDATE (2 round-trips total) ─────
            inserted = 0
            if insert_params:
                with self._conn() as c:
                    c.executemany(
                        "INSERT OR IGNORE INTO forge_signals "
                        "(forge_id, time, timestamp_utc, symbol, setup_type, direction, "
                        "outcome, gate_reason, price, spread, atr, rsi, adx, "
                        "bb_upper, bb_lower, bb_mid, poc_price, vwap_price, fib_50, "
                        "rsi_divergence, psar_state, pattern_score, h1_trend, "
                        "regime_label, regime_confidence, adx_trend_regime, "
                        "high_vol_trend, session, magic, journal_source, run_id, "
                        "macd_histogram, m15_adx, lot_factor, wall_time, aurum_run_id, killzone, minutes_into_kz, "
                        # 2.7.47 RegimeState trio (FORGE_REGIME_TAXONOMY.md §3)
                        "htf_h1_strong, intraday_label, intraday_counter_htf, "
                        # 2.7.37 atoms — 24 cols
                        "h4_trend, m15_trend, h1_di_balance, "
                        "day_open, day_high, day_low, "
                        "m5_open_1, m5_high_1, m5_low_1, m5_close_1, "
                        "m5_lh_cascade, m5_hl_cascade, m5_body_pct, "
                        "h1_di_plus, h1_di_minus, h4_rsi, h4_adx, m30_trend, "
                        "d1_open, d1_close, h1_atr, h4_atr, m15_atr, m1_atr, "
                        # 2.7.37 Group 3 — 45 more cols
                        "h1_rsi, h1_adx, h1_bb_u, h1_bb_m, h1_bb_l, "
                        "h4_bb_u, h4_bb_m, h4_bb_l, "
                        "m15_rsi, m15_ema20, m15_ema50, "
                        "m30_rsi, m30_adx, m30_atr, m30_ema20, m30_ema50, "
                        "m1_ema20, m1_ema50, "
                        "m5_open_0, m5_high_0, m5_low_0, m5_close_0, "
                        "m15_open, m15_high, m15_low, m15_close, "
                        "m30_open, m30_high, m30_low, m30_close, "
                        "h1_open, h1_high, h1_low, h1_close, "
                        "h4_open, h4_high, h4_low, h4_close, "
                        "m5_inside_bar, m5_outside_bar, m5_doji, m5_strong_bar, "
                        "long_lower_wick, long_upper_wick, m5_range_expanding, "
                        # 2.7.110 — CES (Confluence Entry Score) — 7 INTEGER cols
                        "ces_score, ces_dtc, ces_pemcg, ces_momentum, "
                        "ces_rsi, ces_vwap, ces_di, "
                        # 2.7.112 — ISS (ICT Structure Score) — 5 INTEGER cols
                        # (retroactive scribe wiring; SIGNALS schema added them at v2.7.112
                        #  but never landed in scribe forge_signals until v2.7.119).
                        "iss_score, iss_mss, iss_fvg, iss_choch_support, iss_choch_against, "
                        # 2.7.119 — ICT Phase-1 atom context — 9 cols (LOG-ONLY)
                        # Captured at the FORGE setup-trigger chokepoint and bound by
                        # JournalRecordSignal alongside the iss_* atoms.
                        "ict_mss_swing_price, ict_mss_displacement_atr, ict_fvg_count_active, "
                        "ict_fvg_active_upper, ict_fvg_active_lower, ict_fvg_midpoint_dist_atr, "
                        "ict_fvg_age_bars, ict_recent_swing_high, ict_recent_swing_low, "
                        # 2.7.120 — ICT Phase-2 atom context — 8 cols (LOG-ONLY)
                        # ChoCH event counters + liquidity-sweep state + equal-H/L cluster
                        # sizes + killzone enum. Captured at chokepoint via g_ict_last_*
                        # globals from Forge\IctLiquidity.mqh.
                        "ict_choch_buy_count, ict_choch_sell_count, ict_choch_level, "
                        "ict_liquidity_sweep_recent, ict_sweep_level, "
                        "ict_equal_highs_count, ict_equal_lows_count, ict_killzone_active, "
                        # v2.7.122 — ict_sweep_rejection_score (1 REAL col; LOG-ONLY).
                        # 0..1 wick-quality score from ScoreLiquiditySweep, bound from
                        # g_ict_last_sweep_rejection_score (Forge\IctLiquidity.mqh).
                        "ict_sweep_rejection_score, "
                        # v2.7.122 — Pre-TP1 recovery armed flag (1 INTEGER col; LOG-ONLY)
                        # Set inside ArmPreTP1Recovery (FORGE.mq5) on successful OrderSend,
                        # cleared at top of each tick's ManageOpenGroups.
                        "pre_tp1_recovery_armed, "
                        # v2.7.123 — Phase A ICT atom outputs (5 INTEGER cols; LOG-ONLY, Mode A).
                        # Per docs/FORGE_SETUP_ICT_MAP.md §B.8.2 — atom_* prefix (not ict_atom_*).
                        # Captured by FORGE.mq5 ForgeEvalAtoms() with BUY-direction context
                        # into g_ict_last_atom_* globals; bound by JournalRecordSignal.
                        "atom_killzone_favorable, atom_htf_aligned, atom_pullback_in_ote, "
                        "atom_premium_discount_aligned, atom_fvg_on_reversal_leg, "
                        # v2.7.124 — Phase A expansion (6 INTEGERs) — per-category KZ +
                        # per-direction HTF. Reuses Phase A enable flags.
                        "atom_kz_fav_mss_cont, atom_kz_fav_ote, "
                        "atom_kz_fav_liq_sweep, atom_kz_fav_breaker, "
                        "atom_htf_aligned_buy, atom_htf_aligned_sell, "
                        # v2.7.124 — Phase B composite scores (6 INTEGERs; 0-10 weighted sums)
                        # per docs/FORGE_SETUP_ICT_MAP.md §B.8.2. BREAKER_RETEST deferred.
                        "mss_cont_score_buy, mss_cont_score_sell, "
                        "ote_retrace_score_buy, ote_retrace_score_sell, "
                        "liq_sweep_rev_score_buy, liq_sweep_rev_score_sell"
                        ") "
                        # Base group = 41 cols (37 original + 2 v2.7.45 killzone/min_into_kz
                        # + 3 v2.7.47 RegimeState trio). v2.7.110 adds 7 CES cols → 117.
                        # v2.7.119 adds 5 ISS (retroactive) + 9 ICT context cols → total now
                        # 41 + 24 + 45 + 7 + 5 + 9 = 131.
                        # v2.7.120 adds 8 ICT Phase-2 context cols → 41 + 24 + 45 + 7 + 5 + 9 + 8 = 139.
                        # v2.7.122 adds 1 pre_tp1_recovery_armed + 1 ict_sweep_rejection_score
                        #   = 41+24+45+7+5+9+8+2 = 141.
                        # v2.7.123 adds 5 Phase A ICT atom outputs (atom_*_*) cols
                        #   = 41+24+45+7+5+9+8+7 = 146.
                        # v2.7.124 adds 6 Phase A expansion (per-category KZ + per-direction HTF)
                        # + 6 Phase B composite scores
                        #   = 41+24+45+7+5+9+8+19 = 158.
                        # If you add/remove a column in the col list ABOVE, bump both the
                        # count below AND the matching *_vals tuple build above. (See
                        # forge-monitor SKILL.md Check C — v2.7.45/47 historical incident
                        # where this drifted silently.)
                        "VALUES (" + ",".join(["?"] * (41 + 24 + 45 + 7 + 5 + 9 + 8 + 19)) + ")",
                        insert_params,
                    )
                    inserted = len(insert_params)

            if synced_ids:
                placeholders = ",".join("?" * len(synced_ids))
                src.execute(f"UPDATE SIGNALS SET synced = 1 WHERE id IN ({placeholders})",
                            tuple(synced_ids))
                src.commit()

            # Return (total_processed, newly_inserted) so caller can log both
            return len(synced_ids), inserted
        except Exception as e:
            log.warning("SCRIBE sync_forge_journal error: %s", e)
            return 0, 0
        finally:
            src.close()

    def sync_forge_journal_trades(self, journal_db_path: str, source: str = "live", batch_size: int = 500) -> int:
        """Read unsynced TRADES deal rows from FORGE journal DB into forge_journal_trades."""
        from pathlib import Path as _P
        if not _P(journal_db_path).exists():
            return 0, 0

        import sqlite3 as _sqlite3
        try:
            src = _sqlite3.connect(journal_db_path, timeout=5)
        except Exception as e:
            log.warning("SCRIBE sync_forge_journal_trades: cannot open %s — %s", journal_db_path, e)
            return 0, 0

        try:
            # Ensure synced column exists (one-time, cached via src_cols check below)
            cols_t = frozenset(r[1] for r in src.execute("PRAGMA table_info(TRADES)").fetchall())
            if "synced" not in cols_t:
                try:
                    src.execute("ALTER TABLE TRADES ADD COLUMN synced INTEGER DEFAULT 0")
                    src.commit()
                    cols_t = cols_t | {"synced"}
                except Exception:
                    pass
        except Exception as e:
            log.warning("SCRIBE sync_forge_journal_trades: no TRADES table in %s — %s", journal_db_path, e)
            src.close()
            return 0, 0

        try:
            src.execute("PRAGMA journal_mode=WAL")
            # Reuse wall_time and aurum_run_id maps already built by sync_forge_journal
            # (both use the same instance-level cache keyed by journal_db_path)
            cache_key    = journal_db_path
            wall_time_map_t  = self._fj_wall_time_cache.get(cache_key, {0: 0})
            aurum_run_id_map_t = self._fj_aurum_run_cache.get(cache_key, {0: 0})

            # If caches are empty (trades sync called before signals sync), build them now
            if len(wall_time_map_t) <= 1:
                try:
                    for tr in src.execute("SELECT id, wall_time FROM TESTER_RUNS").fetchall():
                        wt = int(tr[1] or 0)
                        wall_time_map_t[int(tr[0])] = wt
                except Exception:
                    pass
                if wall_time_map_t:
                    with self._conn() as _c:
                        for wt in list(wall_time_map_t.values()):
                            if wt and wt not in aurum_run_id_map_t:
                                row = _c.execute(
                                    "SELECT aurum_run_id FROM aurum_tester_runs WHERE wall_time=? LIMIT 1", (wt,)
                                ).fetchone()
                                aurum_run_id_map_t[wt] = row[0] if row else 0

            has_run_id_t = "run_id" in cols_t

            select_sql_t = (
                "SELECT id, deal_ticket, order_ticket, symbol, type, direction, volume, "
                "price, profit, swap, commission, magic, comment, time, time_msc"
                + (", run_id" if has_run_id_t else "")
                + f" FROM TRADES WHERE synced = 0 ORDER BY id LIMIT {max(1, int(batch_size))}"
            )
            rows = src.execute(select_sql_t).fetchall()
            if not rows:
                return 0, 0

            # Build all insert params then executemany (one round-trip)
            insert_params_t: list[tuple] = []
            synced_ids: list[int] = []
            for r in rows:
                run_id_t  = int(r[15] if has_run_id_t else 0)
                wall_time = wall_time_map_t.get(run_id_t, 0)
                aurum_rid = aurum_run_id_map_t.get(wall_time, 0)
                insert_params_t.append((*r[:15], source, run_id_t, wall_time, aurum_rid))
                synced_ids.append(r[0])

            if insert_params_t:
                with self._conn() as c:
                    c.executemany(
                        "INSERT OR IGNORE INTO forge_journal_trades "
                        "(forge_rowid, deal_ticket, order_ticket, symbol, type, direction, "
                        "volume, price, profit, swap, commission, magic, comment, time, time_msc, "
                        "journal_source, run_id, wall_time, aurum_run_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        insert_params_t,
                    )

            inserted_t = len(insert_params_t) if insert_params_t else 0
            if synced_ids:
                placeholders = ",".join("?" * len(synced_ids))
                src.execute(f"UPDATE TRADES SET synced = 1 WHERE id IN ({placeholders})",
                            tuple(synced_ids))
                src.commit()

            # Return (total_processed, newly_inserted)
            return len(synced_ids), inserted_t
        except Exception as e:
            log.warning("SCRIBE sync_forge_journal_trades error: %s", e)
            return 0, 0
        finally:
            src.close()

    def log_market_snapshot(self, data: dict, mode: str, source: str):
        with self._conn() as c:
            c.execute("""INSERT INTO market_snapshots
                (timestamp,mode,source,symbol,bid,ask,spread,
                 open_m1,high_m1,low_m1,close_m1,volume_m1,
                 rsi_14,macd_hist,ema_20,ema_50,bb_upper,bb_mid,bb_lower,bb_width,
                 adx,tv_rating,timeframe,session,news_guard_active,
                 pending_entry_threshold_points,trend_strength_atr_threshold,breakout_buffer_points,
                 regime_label,regime_confidence,regime_model,
                 poc_price,vwap_price,fib_50,fib_382,fib_618,rsi_divergence,psar_state)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                 data.get("regime_model"),
                 data.get("poc_price"),
                 data.get("vwap_price"),
                 data.get("fib_50"),
                 data.get("fib_382"),
                 data.get("fib_618"),
                 data.get("rsi_divergence"),
                 data.get("psar_state")))

    def log_market_regime(self, snapshot: dict, mode: str = None, session: str = None) -> int:
        if not snapshot:
            return 0, 0
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
                 trades_range_min,trades_range_max,trades_policy_reason,
                 open_context,
                 magic_number,trades_opened,trades_closed)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                 data.get("trades_range_min"),
                 data.get("trades_range_max"),
                 data.get("trades_policy_reason"),
                 self._serialize_open_context(data.get("open_context")),
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
        """Update a trade_group's status + optional P&L rollup.

        When the caller passes ``total_pnl=None`` and the new ``status`` is a
        terminal state (CLOSED / CLOSED_ALL / SL_HIT / TP_HIT), the rollup is
        computed automatically from ``trade_closures`` (preferred — populated
        by the BRIDGE tracker at close-detection time), with
        ``forge_journal_trades`` as fallback via the group's ``magic_number``
        (catches the case where BRIDGE was down or initializing when the
        close event fired and the tracker never wrote a closure row).

        OPEN / PARTIAL transitions never trigger a rollup — those statuses
        should preserve whatever P&L the previous update set (if any).
        """
        terminal = status not in ("OPEN", "PARTIAL")
        with self._conn() as c:
            # Auto-rollup when the caller didn't supply explicit numbers AND
            # the group is closing. This is the canonical P&L path for AURUM
            # CLOSE_GROUP / CLOSE_ALL / channel-close / pending-expiry, none of
            # which currently pass total_pnl.
            if terminal and total_pnl is None:
                rolled_pnl, rolled_pips, rolled_count = self._rollup_group_pnl(c, group_id)
                if rolled_count > 0:
                    total_pnl = rolled_pnl
                    if pips is None:
                        pips = rolled_pips
                    if trades_closed is None:
                        trades_closed = rolled_count
            c.execute("""UPDATE trade_groups SET status=?,total_pnl=?,
                pips_captured=?,trades_closed=?,close_reason=?,
                closed_at=? WHERE id=?""",
                (status, total_pnl, pips, trades_closed, close_reason,
                 self._now() if terminal else None,
                 group_id))

    def _rollup_group_pnl(self, conn, group_id: int) -> tuple[float, float, int]:
        """Compute (pnl, pips, deal_count) for ``group_id`` from authoritative sources.

        Order of preference:
        1. ``trade_closures`` rows linked by ``trade_group_id`` (the canonical
           BRIDGE-tracker write path; populated at close-detection).
        2. ``forge_journal_trades`` rows linked by ``magic`` to the group's
           ``magic_number``, summing only the closing-side deals (positive or
           negative ``profit`` — opens are always 0). This is the broker
           journal mirror, populated independently of BRIDGE state.

        Returns (0.0, 0.0, 0) when neither source has data — caller should
        leave the column NULL/0 rather than fabricate a value.
        """
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl),0.0) AS pnl, "
            "       COALESCE(SUM(pips),0.0) AS pips, "
            "       COUNT(*) AS n "
            "FROM trade_closures WHERE trade_group_id=?",
            (group_id,),
        ).fetchone()
        if row and row[2] > 0:
            return (round(float(row[0] or 0), 2),
                    round(float(row[1] or 0), 1),
                    int(row[2]))
        # Journal fallback requires magic + temporal scoping. FORGE recycles
        # magic numbers across cycles (e.g. magic 207402 = G5001 reused for
        # consecutive entries on the same setup); summing journal rows by
        # magic alone collapses multiple groups together. Scope to the
        # group's [open, close] window so we get THIS cycle's deals only.
        grp = conn.execute(
            "SELECT magic_number, timestamp, closed_at "
            "FROM trade_groups WHERE id=?",
            (group_id,),
        ).fetchone()
        if not grp or not grp[0]:
            return (0.0, 0.0, 0)
        magic = int(grp[0])
        opened_iso = grp[1]
        closed_iso = grp[2]
        if not opened_iso:
            return (0.0, 0.0, 0)
        # Closes are the deals with non-zero profit (opens are always 0.00).
        # Bound the window: lower = group open; upper = close or +24h
        # padding if the group is somehow flagged terminal without closed_at.
        # Use strftime to convert ISO → unix epoch inside SQLite for
        # comparison against forge_journal_trades.time.
        jrow = conn.execute(
            "SELECT COALESCE(SUM(profit),0.0) AS pnl, "
            "       SUM(CASE WHEN profit != 0 THEN 1 ELSE 0 END) AS n "
            "FROM forge_journal_trades "
            "WHERE magic = ? "
            "  AND time >= CAST(strftime('%s', ?) AS INTEGER) "
            "  AND time <= CAST(strftime('%s', COALESCE(?, datetime(?, '+24 hours'))) AS INTEGER)",
            (magic, opened_iso, closed_iso, opened_iso),
        ).fetchone()
        if jrow and jrow[1] and jrow[1] > 0:
            return (round(float(jrow[0] or 0), 2), 0.0, int(jrow[1]))
        return (0.0, 0.0, 0)

    def backfill_trade_group_pnl(
        self, since_iso: str | None = None, force: bool = False,
    ) -> dict:
        """One-shot: populate ``total_pnl`` on closed groups from
        ``trade_closures`` / ``forge_journal_trades``.

        - ``force=False`` (default): only touches rows where ``total_pnl`` is
          NULL or 0 — safe to re-run without overwriting good data.
        - ``force=True``: recomputes every terminal-status row in scope.
          Useful when a prior backfill produced wrong totals (e.g. before the
          temporal scoping for recycled magic numbers was in place).

        Returns ``{"scanned": N, "updated": M}``.
        """
        updated = 0
        scanned = 0
        with self._conn() as c:
            where = "status IN ('CLOSED','CLOSED_ALL','SL_HIT','TP_HIT')"
            if not force:
                where += " AND (total_pnl IS NULL OR total_pnl = 0)"
            params: tuple = ()
            if since_iso:
                where += " AND timestamp >= ?"
                params = (since_iso,)
            rows = c.execute(
                f"SELECT id FROM trade_groups WHERE {where}",
                params,
            ).fetchall()
            for row in rows:
                scanned += 1
                gid = int(row[0])
                pnl, pips, n = self._rollup_group_pnl(c, gid)
                if n > 0 and pnl != 0:
                    c.execute(
                        "UPDATE trade_groups SET total_pnl=?, "
                        "pips_captured=COALESCE(NULLIF(pips_captured,0), ?), "
                        "trades_closed=COALESCE(NULLIF(trades_closed,0), ?) "
                        "WHERE id=?",
                        (pnl, pips or None, n, gid),
                    )
                    updated += 1
        log.info(
            "SCRIBE backfill: scanned=%d updated=%d force=%s",
            scanned, updated, force,
        )
        return {"scanned": scanned, "updated": updated}

    def log_trade_position(self, group_id: int, data: dict, mode: str) -> int:
        """Insert a new trade_positions row.

        Optional ``data['tp_stage']`` (1/2/3) records which take-profit stage
        the leg targets at OPEN time so AURUM can introspect multi-leg groups
        before issuing scoped MODIFY commands. Tolerated on legacy rows that
        do not yet know their stage (column already defaults to NULL).
        """
        stage_val = data.get("tp_stage")
        try:
            stage_int = int(stage_val) if stage_val is not None else None
        except (TypeError, ValueError):
            stage_int = None
        if stage_int is not None and stage_int not in (1, 2, 3, 4):
            stage_int = None
        comment_val = data.get("comment") or ""
        with self._conn() as c:
            cur = c.execute("""INSERT INTO trade_positions
                (trade_group_id,timestamp,mode,ticket,magic_number,
                 direction,lot_size,entry_price,sl,tp,tp_stage,comment)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (group_id, self._now(), mode,
                 data.get("ticket"), data.get("magic"),
                 data.get("direction"), data.get("lot_size"),
                 data.get("entry_price"), data.get("sl"), data.get("tp"),
                 stage_int, comment_val or None))
            return cur.lastrowid

    def backfill_tp_stage_from_comment(self, ticket: int, comment: str) -> int | None:
        """Parse ``|TP<n>`` out of a FORGE position/order comment and persist
        it on the matching trade_positions row only when the column is NULL.

        Returns the stage written (1/2/3) or None when nothing was changed.
        Comment grammar: ``FORGE|G<group_id>|<leg_index>|TP<stage>``.
        """
        if not ticket or not comment:
            return None
        m = re.search(r"\|TP(\d+)", str(comment))
        if not m:
            return None
        try:
            stage = int(m.group(1))
        except (TypeError, ValueError):
            return None
        if stage not in (1, 2, 3):
            return None
        try:
            with self._conn() as c:
                cur = c.execute(
                    """UPDATE trade_positions
                       SET tp_stage=?
                       WHERE ticket=? AND tp_stage IS NULL""",
                    (stage, int(ticket)),
                )
                if cur.rowcount > 0:
                    return stage
        except sqlite3.OperationalError as e:
            log.debug("SCRIBE backfill_tp_stage_from_comment tolerated: %s", e)
        return None

    def update_positions_sl_tp_by_stage(self, group_id: int, tp_stage: int,
                                         sl: float | None = None,
                                         tp: float | None = None) -> int:
        """Update SL/TP only on OPEN positions of ``group_id`` whose tp_stage
        matches. Also nudges the corresponding ``trade_groups.tp<n>`` column
        when ``tp`` is provided (so dashboards reflect the per-stage change).

        Returns the number of trade_positions rows updated. Tolerates legacy
        DBs missing optional columns.
        """
        # Signature returns int — return single int from every path for consistency.
        if tp_stage not in (1, 2, 3):
            return 0
        if sl is None and tp is None:
            return 0
        affected = 0
        try:
            with self._conn() as c:
                if sl is not None and tp is not None:
                    cur = c.execute(
                        "UPDATE trade_positions SET sl=?, tp=? "
                        "WHERE trade_group_id=? AND tp_stage=? AND status='OPEN'",
                        (sl, tp, group_id, tp_stage),
                    )
                elif sl is not None:
                    cur = c.execute(
                        "UPDATE trade_positions SET sl=? "
                        "WHERE trade_group_id=? AND tp_stage=? AND status='OPEN'",
                        (sl, group_id, tp_stage),
                    )
                else:
                    cur = c.execute(
                        "UPDATE trade_positions SET tp=? "
                        "WHERE trade_group_id=? AND tp_stage=? AND status='OPEN'",
                        (tp, group_id, tp_stage),
                    )
                affected = cur.rowcount or 0
                # Stage-aware group-level mirror:
                #   * trade_positions SL/TP are both bounded by tp_stage above
                #     (mirrors FORGE which only modifies positions whose comment
                #     matches |TP<stage>).
                #   * trade_groups.tp<n> only moves for the targeted stage so
                #     the dashboard does not collapse other stages onto it.
                #   * trade_groups.sl moves group-wide because the operator's
                #     intent is "protect every leg with this SL" — same as a
                #     standard MOVE_BE.
                if tp is not None:
                    col = f"tp{int(tp_stage)}"
                    c.execute(
                        f"UPDATE trade_groups SET {col}=? WHERE id=?",
                        (tp, group_id),
                    )
                if sl is not None:
                    c.execute(
                        "UPDATE trade_groups SET sl=? WHERE id=?",
                        (sl, group_id),
                    )
        except sqlite3.OperationalError as e:
            log.debug("SCRIBE update_positions_sl_tp_by_stage tolerated: %s", e)
        return affected

    def get_open_positions_with_stage(self, group_id: int) -> list[dict]:
        """Return OPEN positions for a group with stage info — the canonical
        AURUM helper for picking the right MODIFY scope."""
        with self._conn() as c:
            rows = c.execute(
                """SELECT id, ticket, direction, entry_price, sl, tp, tp_stage,
                          lot_size, status
                   FROM trade_positions
                   WHERE trade_group_id=? AND status='OPEN'
                   ORDER BY id ASC""",
                (int(group_id),),
            ).fetchall()
            return [dict(r) for r in rows]

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
                          pip_value_usd: float = 0.0,
                          duration_seconds: int = None,
                          session: str = None, mode: str = None) -> int:
        """Log a position closure to trade_closures table.

        pip_value_usd: signed USD value of the pip move for this trade.
          For XAUUSD: pip_value_usd = lot_size × pips  (since contract_size=100, pip_size=0.01 → factor=1.0).
          Positive = profitable move, negative = loss.
        """
        with self._conn() as c:
            cur = c.execute("""INSERT INTO trade_closures
                (timestamp, ticket, trade_group_id, direction, lot_size,
                 entry_price, close_price, sl, tp, close_reason,
                 pnl, pips, pip_value_usd, duration_seconds, session, mode)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self._now(), ticket, trade_group_id, direction, lot_size,
                 entry_price, close_price, sl, tp, close_reason,
                 pnl, pips, pip_value_usd, duration_seconds, session, mode))
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
                    COALESCE(AVG(duration_seconds), 0) AS avg_duration_sec,
                    COALESCE(AVG(pip_value_usd), 0) AS avg_pip_value_usd
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
                "avg_pip_value_usd": round(row[10] or 0, 2),
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
        # trade_closures.timestamp is canonical — trade_positions.close_time is often
        # NULL for positions closed via the TRACKER path (log_trade_closure called but
        # close_trade_position skipped), causing this function to silently return $0.
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._conn() as c:
            row = c.execute(
                "SELECT COALESCE(SUM(pnl),0) FROM trade_closures WHERE timestamp LIKE ?",
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
            # trade_closures.timestamp is canonical — always populated at close.
            # trade_positions.close_time is only written by close_trade_position() which
            # some close paths skip, causing performance stats to be permanently 0.
            base = "WHERE timestamp >= datetime('now', '-' || ? || ' days')"
            params: list = [str(d)]
            if mode:
                base += " AND mode=?"
                params.append(mode)
            rows = c.execute(
                f"""SELECT COUNT(*) total,
                    SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) wins,
                    SUM(CASE WHEN pnl<0 THEN 1 ELSE 0 END) losses,
                    COALESCE(SUM(pnl),0) total_pnl,
                    COALESCE(AVG(pips),0) avg_pips,
                    COALESCE(AVG(pip_value_usd),0) avg_pip_value_usd
                    FROM trade_closures {base}""",
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
                "avg_pip_value_usd": round(rows[5] or 0, 2),
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
        if table not in ALLOWED_SCRIBE_TABLES:
            raise ValueError(f"table {table!r} not in allowlist")
        where = "WHERE mode=?" if mode else ""
        params = (mode,) if mode else ()
        out = path or f"data/{table}_{mode or 'all'}.csv"
        with self._conn() as c:
            rows = c.execute(f"SELECT * FROM {table} {where}", params).fetchall()
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


# ── Tester DB singleton (Phase 1 — backtest isolation) ────────────
_tester_scribe: "Scribe | None" = None

def get_tester_scribe() -> "Scribe":
    """Return a Scribe instance pointing at aurum_tester.db (Strategy Tester writes only)."""
    global _tester_scribe
    if _tester_scribe is None:
        tester_path = os.environ.get(
            "SCRIBE_TESTER_DB",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "aurum_tester.db"),
        )
        _tester_scribe = Scribe(db_path=tester_path)
    return _tester_scribe


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    s = Scribe("data/test.db")
    s.log_system_event("STARTUP", new_mode="WATCH", triggered_by="USER")
    print("SCRIBE OK — tables created:", s.query("SELECT name FROM sqlite_master WHERE type='table'"))
