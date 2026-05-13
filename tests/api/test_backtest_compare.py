"""
backtest_compare.py unit tests — v2.7.48 killzone + RegimeState breakdowns.

Uses an in-memory sqlite TS-shim to exercise _run_stats and compare_runs end-to-end
without touching the real aurum_tester.db. Covers:
  - new fields (taken_by_killzone, htf_h1_strong_rate_pct,
    intraday_counter_htf_rate_pct, judas_window_taken) appear in _run_stats output
  - compare_runs returns the new killzone_diff dict + new delta keys
  - soft-degrade: when forge_signals lacks the v2.7.45/.47 columns, the call
    succeeds with safe defaults (matches backwards-compat promise for old DBs)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
import sys

# Allow running this test file standalone (pytest auto-resolves from conftest in api/)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

from backtest_compare import _run_stats, compare_runs  # noqa: E402


class _TSShim:
    """Minimal stand-in for scribe.TesterScribe — just needs .query(sql, params)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def query(self, sql: str, params: tuple = ()):
        cur = self.conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _make_db(*, include_v47_cols: bool = True) -> sqlite3.Connection:
    """Build an in-memory aurum_tester.db with two minimal runs, optionally without
    the v2.7.45/.47 RegimeState columns (to exercise the soft-degrade path)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE aurum_tester_runs (
            aurum_run_id   INTEGER PRIMARY KEY,
            wall_time      INTEGER,
            source_run_id  INTEGER,
            journal_source TEXT,
            symbol         TEXT,
            forge_version  TEXT,
            scalper_mode   TEXT,
            balance        REAL,
            sim_start_time TEXT,
            magic_base     INTEGER,
            first_seen_utc TEXT
        )
    """)
    # forge_signals — only the columns we exercise. Add v47 cols conditionally.
    extra = (
        ", killzone TEXT DEFAULT '', minutes_into_kz INTEGER DEFAULT 0, "
        "htf_h1_strong INTEGER DEFAULT 0, intraday_counter_htf INTEGER DEFAULT 0"
        if include_v47_cols else ""
    )
    conn.execute(f"""
        CREATE TABLE forge_signals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            aurum_run_id  INTEGER,
            outcome       TEXT,
            gate_reason   TEXT
            {extra}
        )
    """)
    conn.execute("""
        CREATE TABLE forge_journal_trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            aurum_run_id  INTEGER,
            profit        REAL
        )
    """)
    # Two runs — Run 1 is the "killzone-rich" one, Run 2 is more uniform.
    conn.executemany(
        "INSERT INTO aurum_tester_runs (aurum_run_id, balance, forge_version) VALUES (?,?,?)",
        [(1, 10_000.0, "2.7.47"), (2, 10_000.0, "2.7.46")],
    )

    if include_v47_cols:
        # Run 1 — 8 TAKEN: 4 NY_OPEN_KZ, 3 LONDON_OPEN_KZ (2 inside Judas window <60m),
        #                  1 LONDON_CLOSE_KZ. 3 with htf_h1_strong=1, 2 with intraday_counter_htf=1.
        run1_takens = [
            ("TAKEN", None, "NY_OPEN_KZ",      120, 1, 0),
            ("TAKEN", None, "NY_OPEN_KZ",      130, 1, 0),
            ("TAKEN", None, "NY_OPEN_KZ",      140, 1, 0),
            ("TAKEN", None, "NY_OPEN_KZ",      150, 0, 0),
            ("TAKEN", None, "LONDON_OPEN_KZ",   30, 0, 1),  # Judas window
            ("TAKEN", None, "LONDON_OPEN_KZ",   45, 0, 1),  # Judas window
            ("TAKEN", None, "LONDON_OPEN_KZ",   90, 0, 0),
            ("TAKEN", None, "LONDON_CLOSE_KZ",  60, 0, 0),
        ]
        # Run 1 — 5 SKIPs: 2 killzone_trade_cap (the new v2.7.46 gate), 3 session_off
        run1_skips = [
            ("SKIP", "killzone_trade_cap", "NY_OPEN_KZ", 200, 0, 0),
            ("SKIP", "killzone_trade_cap", "NY_OPEN_KZ", 210, 0, 0),
            ("SKIP", "session_off",        "",             0, 0, 0),
            ("SKIP", "session_off",        "",             0, 0, 0),
            ("SKIP", "session_off",        "",             0, 0, 0),
        ]
        conn.executemany(
            "INSERT INTO forge_signals (aurum_run_id, outcome, gate_reason, killzone, "
            "minutes_into_kz, htf_h1_strong, intraday_counter_htf) VALUES (1,?,?,?,?,?,?)",
            run1_takens + run1_skips,
        )

        # Run 2 — 4 TAKEN, all NY_OPEN_KZ. 1 htf_h1_strong, 0 intraday_counter_htf, 0 Judas.
        run2_takens = [
            ("TAKEN", None, "NY_OPEN_KZ", 120, 1, 0),
            ("TAKEN", None, "NY_OPEN_KZ", 130, 0, 0),
            ("TAKEN", None, "NY_OPEN_KZ", 140, 0, 0),
            ("TAKEN", None, "NY_OPEN_KZ", 150, 0, 0),
        ]
        run2_skips = [
            ("SKIP", "session_off", "", 0, 0, 0),
            ("SKIP", "session_off", "", 0, 0, 0),
        ]
        conn.executemany(
            "INSERT INTO forge_signals (aurum_run_id, outcome, gate_reason, killzone, "
            "minutes_into_kz, htf_h1_strong, intraday_counter_htf) VALUES (2,?,?,?,?,?,?)",
            run2_takens + run2_skips,
        )
    else:
        # Pre-v2.7.45 schema — no killzone / regime columns at all.
        conn.executemany(
            "INSERT INTO forge_signals (aurum_run_id, outcome, gate_reason) VALUES (1,?,?)",
            [("TAKEN", None), ("TAKEN", None), ("SKIP", "session_off")],
        )
        conn.executemany(
            "INSERT INTO forge_signals (aurum_run_id, outcome, gate_reason) VALUES (2,?,?)",
            [("TAKEN", None), ("SKIP", "session_off")],
        )

    # A few closed trades per run so _score has something to chew on
    conn.executemany(
        "INSERT INTO forge_journal_trades (aurum_run_id, profit) VALUES (?,?)",
        [(1, 12.5), (1, -4.0), (1, 8.0), (1, -2.5), (1, 15.0),
         (2, 5.0), (2, -3.0), (2, 4.0)],
    )
    conn.commit()
    return conn


def test_run_stats_exposes_killzone_breakdown():
    """v2.7.48: _run_stats returns taken_by_killzone with TAKEN counts per KZ."""
    ts = _TSShim(_make_db())
    stats = _run_stats(ts, 1)
    kz = stats["taken_by_killzone"]
    assert kz["NY_OPEN_KZ"] == 4
    assert kz["LONDON_OPEN_KZ"] == 3
    assert kz["LONDON_CLOSE_KZ"] == 1
    # SKIPs are NOT in the killzone breakdown (TAKEN-only — that's the analytical question)
    assert "(none)" not in kz


def test_run_stats_computes_regime_rates():
    """v2.7.48: htf_h1_strong + intraday_counter_htf utilization rates + Judas window count."""
    ts = _TSShim(_make_db())
    stats = _run_stats(ts, 1)
    # Run 1: 8 TAKEN, 3 with htf_h1_strong=1 → 37.5%
    assert stats["htf_h1_strong_rate_pct"] == 37.5
    # 2 with intraday_counter_htf=1 → 25.0%
    assert stats["intraday_counter_htf_rate_pct"] == 25.0
    # 2 inside LONDON_OPEN_KZ with minutes_into_kz<60 → judas_window_taken=2
    assert stats["judas_window_taken"] == 2


def test_run_stats_killzone_trade_cap_gate_visible():
    """v2.7.48: the v2.7.46 killzone_trade_cap gate flows through existing gate_breakdown."""
    ts = _TSShim(_make_db())
    stats = _run_stats(ts, 1)
    assert stats["gate_breakdown"]["killzone_trade_cap"] == 2
    assert stats["gate_breakdown"]["session_off"] == 3


def test_compare_runs_includes_killzone_diff():
    """v2.7.48: compare_runs surfaces a killzone_diff dict + regime-rate deltas."""
    ts = _TSShim(_make_db())
    cmp = compare_runs(ts, 1, 2)
    # killzone_diff present and reveals A>B in NY_OPEN_KZ and uniquely-A killzones
    assert "killzone_diff" in cmp
    assert cmp["killzone_diff"]["NY_OPEN_KZ"]["delta"] == 0  # 4 vs 4
    assert cmp["killzone_diff"]["LONDON_OPEN_KZ"]["delta"] == 3   # A=3, B=0
    assert cmp["killzone_diff"]["LONDON_CLOSE_KZ"]["delta"] == 1  # A=1, B=0
    # Deltas surface regime-rate diffs
    assert cmp["deltas"]["htf_h1_strong_rate_pct"] is not None
    assert cmp["deltas"]["intraday_counter_htf_rate_pct"] is not None
    assert cmp["deltas"]["judas_window_taken"] == 2  # Run A=2, Run B=0


def test_run_stats_soft_degrades_on_old_schema():
    """v2.7.48: when forge_signals lacks the v2.7.45/.47 columns, _run_stats still returns
    a sane dict with empty/None values rather than crashing.
    Covers the case where an analyst opens an old aurum_tester.db that was created before
    SCRIBE ran the v2.7.45/.47 ALTER TABLE migrations."""
    ts = _TSShim(_make_db(include_v47_cols=False))
    stats = _run_stats(ts, 1)
    # Core fields still work
    assert stats["taken"] == 2
    assert stats["skipped"] == 1
    # New fields degrade to defaults — not crashes, not absent
    assert stats["taken_by_killzone"] == {}
    assert stats["htf_h1_strong_rate_pct"] is None
    assert stats["intraday_counter_htf_rate_pct"] is None
    assert stats["judas_window_taken"] == 0
