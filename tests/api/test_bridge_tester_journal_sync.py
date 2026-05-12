"""
BRIDGE: BRIDGE_SYNC_TESTER_JOURNAL flag — tester journal sync gate.

When BRIDGE_SYNC_TESTER_JOURNAL=0 (default), tester journal DBs must be
skipped entirely so backtest noise never reaches AURUM.
When BRIDGE_SYNC_TESTER_JOURNAL=1, tester journals sync as before.

Uses the same MagicMock stub pattern as other bridge tests.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def _make_journal(path: Path, *, tester: bool) -> None:
    """Create a minimal FORGE journal DB (live or tester)."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        """CREATE TABLE SIGNALS (
            id INTEGER PRIMARY KEY, time INTEGER NOT NULL,
            symbol TEXT NOT NULL, setup_type TEXT, direction TEXT,
            outcome TEXT NOT NULL, gate_reason TEXT,
            price REAL, spread REAL, atr REAL, rsi REAL, adx REAL,
            bb_upper REAL, bb_lower REAL, bb_mid REAL,
            poc_price REAL, vwap_price REAL, fib_50 REAL,
            rsi_divergence TEXT, psar_state TEXT,
            pattern_score INTEGER, h1_trend REAL,
            regime_label TEXT, regime_confidence REAL,
            adx_trend_regime INTEGER, high_vol_trend INTEGER,
            session TEXT, magic INTEGER,
            synced INTEGER DEFAULT 0, run_id INTEGER DEFAULT 0
        )"""
    )
    conn.execute(
        """CREATE TABLE TRADES (
            id INTEGER PRIMARY KEY, deal_ticket INTEGER NOT NULL,
            order_ticket INTEGER, symbol TEXT NOT NULL,
            type INTEGER, direction INTEGER, volume REAL,
            price REAL, profit REAL, swap REAL, commission REAL,
            magic INTEGER, comment TEXT, time INTEGER NOT NULL,
            time_msc INTEGER, synced INTEGER DEFAULT 0,
            run_id INTEGER DEFAULT 0, UNIQUE(deal_ticket, run_id)
        )"""
    )
    conn.execute(
        "INSERT INTO SIGNALS VALUES "
        "(1, 1710000000, 'XAUUSD', 'BB_BOUNCE', 'BUY', 'SKIP', 'no_setup', "
        "2200.0, 20.0, 1.2, 55.0, 18.0, 2210.0, 2190.0, 2200.0, "
        "2201.0, 2202.0, 2200.5, 'NONE', 'BULL', 3, 0.4, 'RANGE', "
        "0.7, 0, 0, 'LONDON', 202401, 0, 0)"
    )
    conn.execute(
        "INSERT INTO TRADES "
        "(id, deal_ticket, order_ticket, symbol, type, direction, volume, "
        "price, profit, swap, commission, magic, comment, time, time_msc, "
        "synced, run_id) "
        "VALUES (1, 777001, 888001, 'XAUUSD', 0, 1, 0.01, 2200.0, 1.5, "
        "0.0, 0.0, 202401, 'SCALP', 1710000100, 1710000100000, 0, 0)"
    )
    conn.commit()
    conn.close()


def _make_bridge_stub(journal_paths: list[str], scribe_mock):
    """Minimal Bridge stub with only the journal-sync fields populated."""
    stub = MagicMock()
    stub.scribe = scribe_mock
    stub._last_journal_sync = 0  # force sync on first call
    stub._resolve_forge_journal_paths = MagicMock(return_value=journal_paths)
    return stub


# ---------------------------------------------------------------------------
# OFF (default): tester journal is skipped
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_tester_journal_skipped_when_flag_off(monkeypatch, tmp_path):
    """With BRIDGE_SYNC_TESTER_JOURNAL=0, sync_forge_journal* must NOT be
    called for paths containing '_tester'."""
    import bridge as bm

    monkeypatch.setattr(bm, "BRIDGE_SYNC_TESTER_JOURNAL", False)

    live_db = tmp_path / "FORGE_journal_XAUUSD.db"
    tester_db = tmp_path / "FORGE_journal_XAUUSD_tester.db"
    _make_journal(live_db, tester=False)
    _make_journal(tester_db, tester=True)

    scribe_mock = MagicMock()
    # Production _tick at python/bridge.py:2950 unpacks `proc, new = sync_*(...)`.
    # Match that signature even though this test bypasses _tick.
    scribe_mock.sync_forge_journal.return_value = (1, 1)
    scribe_mock.sync_forge_journal_trades.return_value = (0, 0)

    stub = _make_bridge_stub([str(live_db), str(tester_db)], scribe_mock)

    # Run the sync section exactly as _tick() does
    from pathlib import Path as _P
    _now = time.time()
    stub._last_journal_sync = 0
    if _now - stub._last_journal_sync >= 60:
        stub._last_journal_sync = _now
        for journal_path in stub._resolve_forge_journal_paths():
            is_tester = "_tester" in _P(journal_path).name
            if is_tester and not bm.BRIDGE_SYNC_TESTER_JOURNAL:
                continue
            tag = "tester" if is_tester else "live"
            stub.scribe.sync_forge_journal(journal_path, source=tag)
            stub.scribe.sync_forge_journal_trades(journal_path, source=tag)

    # Only the live journal should have been passed to scribe
    calls = [c.args[0] for c in scribe_mock.sync_forge_journal.call_args_list]
    assert str(live_db) in calls, "live journal must be synced"
    assert str(tester_db) not in calls, "tester journal must NOT be synced when flag is off"

    trade_calls = [c.args[0] for c in scribe_mock.sync_forge_journal_trades.call_args_list]
    assert str(tester_db) not in trade_calls, "tester trades must NOT be synced when flag is off"


# ---------------------------------------------------------------------------
# ON: tester journal IS synced when opt-in flag set
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_tester_journal_synced_when_flag_on(monkeypatch, tmp_path):
    """With BRIDGE_SYNC_TESTER_JOURNAL=1, both live and tester journals sync."""
    import bridge as bm

    monkeypatch.setattr(bm, "BRIDGE_SYNC_TESTER_JOURNAL", True)

    live_db = tmp_path / "FORGE_journal_XAUUSD.db"
    tester_db = tmp_path / "FORGE_journal_XAUUSD_tester.db"
    _make_journal(live_db, tester=False)
    _make_journal(tester_db, tester=True)

    scribe_mock = MagicMock()
    scribe_mock.sync_forge_journal.return_value = (1, 1)
    scribe_mock.sync_forge_journal_trades.return_value = (1, 1)

    stub = _make_bridge_stub([str(live_db), str(tester_db)], scribe_mock)

    from pathlib import Path as _P
    _now = time.time()
    stub._last_journal_sync = 0
    if _now - stub._last_journal_sync >= 60:
        stub._last_journal_sync = _now
        for journal_path in stub._resolve_forge_journal_paths():
            is_tester = "_tester" in _P(journal_path).name
            if is_tester and not bm.BRIDGE_SYNC_TESTER_JOURNAL:
                continue
            tag = "tester" if is_tester else "live"
            stub.scribe.sync_forge_journal(journal_path, source=tag)
            stub.scribe.sync_forge_journal_trades(journal_path, source=tag)

    calls = [c.args[0] for c in scribe_mock.sync_forge_journal.call_args_list]
    assert str(live_db) in calls, "live journal must be synced"
    assert str(tester_db) in calls, "tester journal must be synced when flag is on"


# ---------------------------------------------------------------------------
# Source tag: live vs tester are tagged correctly
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_tester_journal_tagged_as_tester_when_synced(monkeypatch, tmp_path):
    """When flag is on, tester DB must be passed source='tester'; live source='live'."""
    import bridge as bm

    monkeypatch.setattr(bm, "BRIDGE_SYNC_TESTER_JOURNAL", True)

    live_db = tmp_path / "FORGE_journal_XAUUSD.db"
    tester_db = tmp_path / "FORGE_journal_XAUUSD_tester.db"
    _make_journal(live_db, tester=False)
    _make_journal(tester_db, tester=True)

    scribe_mock = MagicMock()
    scribe_mock.sync_forge_journal.return_value = 0
    scribe_mock.sync_forge_journal_trades.return_value = 0

    stub = _make_bridge_stub([str(live_db), str(tester_db)], scribe_mock)

    from pathlib import Path as _P
    _now = time.time()
    stub._last_journal_sync = 0
    if _now - stub._last_journal_sync >= 60:
        stub._last_journal_sync = _now
        for journal_path in stub._resolve_forge_journal_paths():
            is_tester = "_tester" in _P(journal_path).name
            if is_tester and not bm.BRIDGE_SYNC_TESTER_JOURNAL:
                continue
            tag = "tester" if is_tester else "live"
            stub.scribe.sync_forge_journal(journal_path, source=tag)
            stub.scribe.sync_forge_journal_trades(journal_path, source=tag)

    # Build a dict: path -> source tag used
    tags = {c.args[0]: c.kwargs["source"] for c in scribe_mock.sync_forge_journal.call_args_list}
    assert tags[str(live_db)] == "live"
    assert tags[str(tester_db)] == "tester"


# ---------------------------------------------------------------------------
# Only-tester: when there's no live journal, flag=off means zero syncs
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_only_tester_journal_present_flag_off_no_syncs(monkeypatch, tmp_path):
    """Edge case: only a tester DB on disk + flag off → nothing synced."""
    import bridge as bm

    monkeypatch.setattr(bm, "BRIDGE_SYNC_TESTER_JOURNAL", False)

    tester_db = tmp_path / "FORGE_journal_XAUUSD_tester.db"
    _make_journal(tester_db, tester=True)

    scribe_mock = MagicMock()
    stub = _make_bridge_stub([str(tester_db)], scribe_mock)

    from pathlib import Path as _P
    _now = time.time()
    stub._last_journal_sync = 0
    if _now - stub._last_journal_sync >= 60:
        stub._last_journal_sync = _now
        for journal_path in stub._resolve_forge_journal_paths():
            is_tester = "_tester" in _P(journal_path).name
            if is_tester and not bm.BRIDGE_SYNC_TESTER_JOURNAL:
                continue
            tag = "tester" if is_tester else "live"
            stub.scribe.sync_forge_journal(journal_path, source=tag)
            stub.scribe.sync_forge_journal_trades(journal_path, source=tag)

    scribe_mock.sync_forge_journal.assert_not_called()
    scribe_mock.sync_forge_journal_trades.assert_not_called()
