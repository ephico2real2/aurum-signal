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
                "trades_opened": 1,
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
    stub.scribe.query.return_value = []
    stub.scribe.log_trade_group.return_value = 42
    stub._effective_mode = lambda: "SCALPER"
    stub._open_groups = {}
    stub._bridge_activity = MagicMock()
    stub.herald = MagicMock()
    bm.Bridge._check_forge_scalper_entry(
        stub,
        {
            "open_positions": [{"magic": 202478}],
            "pending_orders": [],
        },
    )
    bm.Bridge._check_forge_scalper_entry(stub)

    args, kwargs = stub.scribe.log_trade_group.call_args
    group_data = args[0]
    assert group_data["pending_entry_threshold_points"] == 50.0
    assert group_data["trend_strength_atr_threshold"] == 0.2
    assert group_data["breakout_buffer_points"] == 10.0


@pytest.mark.unit
def test_bridge_ignores_native_scalper_entry_without_mt5_exposure(monkeypatch, tmp_path):
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
                "trades_opened": 1,
                "lot_per_trade": 0.01,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bm, "SCALPER_ENTRY_FILE", str(entry_path))
    monkeypatch.setattr(bm, "_tlog", lambda *a, **k: None)

    stub = MagicMock()
    stub._last_scalper_entry_ts = None
    stub.scribe = MagicMock()
    stub._effective_mode = lambda: "SCALPER"
    stub._open_groups = {}
    stub._bridge_activity = MagicMock()
    stub.herald = MagicMock()

    bm.Bridge._check_forge_scalper_entry(
        stub,
        {
            "open_positions": [],
            "pending_orders": [],
        },
    )

    stub.scribe.log_trade_group.assert_not_called()
    assert stub._bridge_activity.call_args is not None
    assert stub._bridge_activity.call_args.args[0] == "FORGE_SCALP_ENTRY_IGNORED"


@pytest.mark.unit
def test_scribe_update_group_sl_tp_syncs_group_and_open_positions(tmp_path):
    db = tmp_path / "sync.db"
    scribe = Scribe(str(db))

    gid = scribe.log_trade_group(
        {
            "source": "AURUM",
            "direction": "BUY",
            "entry_low": 4750.2,
            "entry_high": 4750.2,
            "sl": 4740.0,
            "tp1": 4760.0,
            "tp2": 4765.0,
            "tp3": None,
            "num_trades": 1,
            "lot_per_trade": 0.01,
            "risk_pct": 0.1,
            "account_balance": 100000.0,
        },
        mode="HYBRID",
        magic_number=202450,
    )
    scribe.log_trade_position(
        gid,
        {
            "ticket": 123456789,
            "magic": 202450,
            "direction": "BUY",
            "lot_size": 0.01,
            "entry_price": 4750.2,
            "sl": 4740.0,
            "tp": 4760.0,
        },
        mode="HYBRID",
    )

    scribe.update_group_sl_tp(gid, sl=4745.0, tp=4762.5)

    grp = scribe.query("SELECT sl, tp1, tp2, tp3 FROM trade_groups WHERE id=?", (gid,))[0]
    pos = scribe.query(
        "SELECT sl, tp FROM trade_positions WHERE trade_group_id=? AND status='OPEN'",
        (gid,),
    )[0]

    assert grp["sl"] == 4745.0
    assert grp["tp1"] == 4762.5
    assert grp["tp2"] == 4762.5
    assert grp["tp3"] is None
    assert pos["sl"] == 4745.0
    assert pos["tp"] == 4762.5
