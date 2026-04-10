from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from scribe import Scribe  # noqa: E402


@pytest.mark.unit
def test_scribe_migration_adds_threshold_columns_on_existing_db(tmp_path):
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS trade_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            mode TEXT NOT NULL,
            source TEXT NOT NULL,
            signal_id INTEGER,
            direction TEXT NOT NULL,
            entry_low REAL, entry_high REAL,
            sl REAL, tp1 REAL, tp2 REAL, tp3 REAL,
            num_trades INTEGER,
            lot_per_trade REAL,
            risk_pct REAL,
            account_balance REAL,
            lens_rating INTEGER,
            lens_rsi REAL,
            lens_confirmed INTEGER
        );
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            mode TEXT NOT NULL,
            source TEXT NOT NULL,
            symbol TEXT,
            bid REAL, ask REAL, spread REAL,
            open_m1 REAL, high_m1 REAL, low_m1 REAL, close_m1 REAL, volume_m1 REAL,
            rsi_14 REAL, macd_hist REAL, ema_20 REAL, ema_50 REAL,
            bb_upper REAL, bb_mid REAL, bb_lower REAL, bb_width REAL,
            adx REAL, tv_rating INTEGER, timeframe TEXT,
            session TEXT, news_guard_active INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS signals_received (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            mode TEXT NOT NULL,
            raw_text TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    scribe = Scribe(str(db))
    cols_m = {r["name"] for r in scribe.query("PRAGMA table_info(market_snapshots)")}
    cols_t = {r["name"] for r in scribe.query("PRAGMA table_info(trade_groups)")}

    assert "pending_entry_threshold_points" in cols_m
    assert "trend_strength_atr_threshold" in cols_m
    assert "breakout_buffer_points" in cols_m
    assert "pending_entry_threshold_points" in cols_t
    assert "trend_strength_atr_threshold" in cols_t
    assert "breakout_buffer_points" in cols_t


@pytest.mark.unit
def test_scribe_persists_threshold_fields_for_snapshots_and_trade_groups(tmp_path):
    db = tmp_path / "thr.db"
    scribe = Scribe(str(db))

    scribe.log_market_snapshot(
        {
            "symbol": "XAUUSD",
            "bid": 3300.1,
            "ask": 3300.3,
            "pending_entry_threshold_points": 50.0,
            "trend_strength_atr_threshold": 0.2,
            "breakout_buffer_points": 10.0,
        },
        mode="SCALPER",
        source="LENS_MCP",
    )
    gid = scribe.log_trade_group(
        {
            "source": "FORGE_NATIVE_SCALP",
            "direction": "BUY",
            "entry_low": 3300.2,
            "entry_high": 3300.2,
            "sl": 3299.0,
            "tp1": 3301.0,
            "num_trades": 4,
            "lot_per_trade": 0.01,
            "pending_entry_threshold_points": 50.0,
            "trend_strength_atr_threshold": 0.2,
            "breakout_buffer_points": 10.0,
        },
        mode="SCALPER",
        magic_number=202999,
    )

    m = scribe.query(
        "SELECT pending_entry_threshold_points, trend_strength_atr_threshold, breakout_buffer_points "
        "FROM market_snapshots ORDER BY id DESC LIMIT 1"
    )[0]
    t = scribe.query(
        "SELECT pending_entry_threshold_points, trend_strength_atr_threshold, breakout_buffer_points "
        "FROM trade_groups WHERE id=?",
        (gid,),
    )[0]

    assert m["pending_entry_threshold_points"] == 50.0
    assert m["trend_strength_atr_threshold"] == 0.2
    assert m["breakout_buffer_points"] == 10.0
    assert t["pending_entry_threshold_points"] == 50.0
    assert t["trend_strength_atr_threshold"] == 0.2
    assert t["breakout_buffer_points"] == 10.0


@pytest.mark.unit
def test_bridge_forwards_scalper_threshold_fields(monkeypatch, tmp_path):
    import bridge as bm

    entry_path = tmp_path / "scalper_entry.json"
    entry_path.write_text(
        json.dumps(
            {
                "timestamp": "2099-01-01T00:00:00Z",
                "group_id": 77,
                "magic": 202478,
                "direction": "BUY",
                "setup_type": "BB_BREAKOUT",
                "entry_price": 3300.2,
                "sl": 3299.0,
                "tp1": 3301.0,
                "tp2": 3302.0,
                "num_trades": 4,
                "lot_per_trade": 0.01,
                "pending_entry_threshold_points": 50.0,
                "trend_strength_atr_threshold": 0.2,
                "breakout_buffer_points": 10.0,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bm, "SCALPER_ENTRY_FILE", str(entry_path))
    monkeypatch.setattr(bm, "_tlog", lambda *a, **k: None)

    stub = MagicMock()
    stub._last_scalper_entry_ts = None
    stub.scribe = MagicMock()
    stub.scribe.log_trade_group.return_value = 42
    stub._effective_mode = lambda: "SCALPER"
    stub._open_groups = {}
    stub._bridge_activity = MagicMock()
    stub.herald = MagicMock()

    bm.Bridge._check_forge_scalper_entry(stub)

    args, kwargs = stub.scribe.log_trade_group.call_args
    group_data = args[0]
    assert group_data["pending_entry_threshold_points"] == 50.0
    assert group_data["trend_strength_atr_threshold"] == 0.2
    assert group_data["breakout_buffer_points"] == 10.0
