import importlib
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def _reload_scribe(monkeypatch, raw_db: str | None):
    if raw_db is None:
        monkeypatch.delenv("SCRIBE_DB", raising=False)
    else:
        monkeypatch.setenv("SCRIBE_DB", raw_db)
    sys.modules.pop("scribe", None)
    return importlib.import_module("scribe")


def _create_journal(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE SIGNALS (
                id INTEGER PRIMARY KEY,
                time INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                setup_type TEXT,
                direction TEXT,
                outcome TEXT NOT NULL,
                gate_reason TEXT,
                price REAL,
                spread REAL,
                atr REAL,
                rsi REAL,
                adx REAL,
                bb_upper REAL,
                bb_lower REAL,
                bb_mid REAL,
                poc_price REAL,
                vwap_price REAL,
                fib_50 REAL,
                rsi_divergence TEXT,
                psar_state TEXT,
                pattern_score INTEGER,
                h1_trend REAL,
                regime_label TEXT,
                regime_confidence REAL,
                adx_trend_regime INTEGER,
                high_vol_trend INTEGER,
                session TEXT,
                magic INTEGER,
                synced INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE TRADES (
                id INTEGER PRIMARY KEY,
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
                synced INTEGER DEFAULT 0,
                run_id INTEGER DEFAULT 0,
                UNIQUE(deal_ticket, run_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO SIGNALS VALUES (
                10, 1710000000, 'XAUUSD', 'BB_BOUNCE', 'BUY', 'SKIP', 'no_setup',
                2200.0, 20.0, 1.2, 55.0, 18.0, 2210.0, 2190.0, 2200.0,
                2201.0, 2202.0, 2200.5, 'NONE', 'BULL', 3, 0.4, 'RANGE',
                0.7, 0, 0, 'LONDON', 202401, 0
            )
            """
        )
        conn.execute(
            """
            INSERT INTO TRADES
                (id, deal_ticket, order_ticket, symbol, type, direction, volume,
                 price, profit, swap, commission, magic, comment, time, time_msc,
                 synced, run_id)
            VALUES (20, 777001, 888001, 'XAUUSD', 0, 0, 0.01, 2200.0, 1.5,
                    0.0, 0.0, 202401, 'SCALP|G1', 1710000100, 1710000100000, 0, 0)
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_scribe_db_path_resolution_rules(monkeypatch):
    checks = [
        (None, ROOT / "python/data/aurum_intelligence.db"),
        ("python/data/aurum_intelligence.db", ROOT / "python/data/aurum_intelligence.db"),
        ("data/aurum_intelligence.db", ROOT / "python/data/aurum_intelligence.db"),
        ("/tmp/scribe-test-absolute.db", Path("/tmp/scribe-test-absolute.db")),
    ]
    for raw, expected in checks:
        scribe = _reload_scribe(monkeypatch, raw)
        assert Path(scribe.DB_PATH) == expected


def test_forge_journal_sync_tags_source_and_is_idempotent(tmp_path, monkeypatch):
    scribe_mod = _reload_scribe(monkeypatch, str(tmp_path / "scribe.db"))
    journal = tmp_path / "FORGE_journal_XAUUSD_tester.db"
    _create_journal(journal)

    scribe = scribe_mod.Scribe(str(tmp_path / "scribe.db"))
    assert scribe.sync_forge_journal(str(journal), source="tester") == 1
    assert scribe.sync_forge_journal_trades(str(journal), source="tester") == 1

    conn = sqlite3.connect(str(journal))
    try:
        conn.execute("UPDATE SIGNALS SET synced=0 WHERE id=10")
        conn.execute("UPDATE TRADES SET synced=0 WHERE id=20")
        conn.commit()
    finally:
        conn.close()

    scribe.sync_forge_journal(str(journal), source="tester")
    scribe.sync_forge_journal_trades(str(journal), source="tester")

    with sqlite3.connect(str(tmp_path / "scribe.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM forge_signals").fetchone()[0] == 1
        assert conn.execute("SELECT journal_source FROM forge_signals").fetchone()[0] == "tester"
        assert conn.execute("SELECT COUNT(*) FROM forge_journal_trades").fetchone()[0] == 1
        assert conn.execute("SELECT journal_source FROM forge_journal_trades").fetchone()[0] == "tester"

    with sqlite3.connect(str(journal)) as conn:
        assert conn.execute("SELECT synced FROM SIGNALS WHERE id=10").fetchone()[0] == 1
        assert conn.execute("SELECT synced FROM TRADES WHERE id=20").fetchone()[0] == 1


def test_forge_journal_trades_multi_run_dedup(tmp_path, monkeypatch):
    """Same deal_ticket with different run_id values must both be stored."""
    scribe_mod = _reload_scribe(monkeypatch, str(tmp_path / "scribe.db"))
    journal = tmp_path / "FORGE_journal_XAUUSD_tester.db"
    _create_journal(journal)

    # Add a second row: same deal_ticket (777001) but run_id=2
    with sqlite3.connect(str(journal)) as conn:
        conn.execute(
            """
            INSERT INTO TRADES
                (id, deal_ticket, order_ticket, symbol, type, direction, volume,
                 price, profit, swap, commission, magic, comment, time, time_msc,
                 synced, run_id)
            VALUES (21, 777001, 888001, 'XAUUSD', 0, 0, 0.01, 2201.0, 2.5,
                    0.0, 0.0, 202401, 'SCALP|G1', 1710001000, 1710001000000, 0, 2)
            """
        )
        conn.commit()

    scribe = scribe_mod.Scribe(str(tmp_path / "scribe.db"))
    synced = scribe.sync_forge_journal_trades(str(journal), source="tester")
    assert synced == 2  # both rows accepted

    with sqlite3.connect(str(tmp_path / "scribe.db")) as conn:
        rows = conn.execute(
            "SELECT deal_ticket, run_id FROM forge_journal_trades ORDER BY run_id"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0] == (777001, 0)
        assert rows[1] == (777001, 2)


def test_forge_journal_sync_keeps_live_and_tester_sources_separate(tmp_path, monkeypatch):
    scribe_mod = _reload_scribe(monkeypatch, str(tmp_path / "scribe.db"))
    journal = tmp_path / "FORGE_journal_XAUUSD.db"
    _create_journal(journal)

    scribe = scribe_mod.Scribe(str(tmp_path / "scribe.db"))
    assert scribe.sync_forge_journal(str(journal), source="live") == 1
    assert scribe.sync_forge_journal_trades(str(journal), source="live") == 1

    with sqlite3.connect(str(journal)) as conn:
        conn.execute("UPDATE SIGNALS SET synced=0 WHERE id=10")
        conn.execute("UPDATE TRADES SET synced=0 WHERE id=20")
        conn.commit()

    assert scribe.sync_forge_journal(str(journal), source="tester") == 1
    assert scribe.sync_forge_journal_trades(str(journal), source="tester") == 1

    with sqlite3.connect(str(tmp_path / "scribe.db")) as conn:
        assert conn.execute(
            "SELECT journal_source, COUNT(*) FROM forge_signals GROUP BY 1 ORDER BY 1"
        ).fetchall() == [("live", 1), ("tester", 1)]
        assert conn.execute(
            "SELECT journal_source, COUNT(*) FROM forge_journal_trades GROUP BY 1 ORDER BY 1"
        ).fetchall() == [("live", 1), ("tester", 1)]
