"""market_data: Strategy Tester flag uses file mtime for staleness (not simulated TimeGMT)."""

import json
import os
import time

import pytest

from market_data import MT5_STALE_SEC, build_execution_quote, enrich_mt5_for_stale_check


def test_enrich_adds_age_from_mtime(tmp_path):
    p = tmp_path / "market_data.json"
    p.write_text(
        json.dumps(
            {
                "symbol": "XAUUSD",
                "strategy_tester": True,
                "timestamp_unix": 1000,
                "price": {"bid": 2000.0, "ask": 2000.5},
            }
        ),
        encoding="utf-8",
    )
    os.utime(p, (time.time(), time.time()))
    mt5 = json.loads(p.read_text(encoding="utf-8"))
    enriched = enrich_mt5_for_stale_check(mt5, str(p))
    assert enriched.get("_age_from_mtime") is not None
    assert 0 <= float(enriched["_age_from_mtime"]) < 5.0


def test_build_execution_quote_fresh_when_strategy_tester_mtime_recent(tmp_path):
    p = tmp_path / "market_data.json"
    p.write_text(
        json.dumps(
            {
                "symbol": "XAUUSD",
                "strategy_tester": True,
                "timestamp_unix": 1,
                "price": {"bid": 2000.0, "ask": 2000.5},
            }
        ),
        encoding="utf-8",
    )
    os.utime(p, (time.time(), time.time()))
    mt5 = json.loads(p.read_text(encoding="utf-8"))
    mt5 = enrich_mt5_for_stale_check(mt5, str(p))
    q = build_execution_quote(mt5)
    assert q["stale"] is False
    assert q["usable"] is True
    assert q["age_sec"] is not None
    assert q["age_sec"] < MT5_STALE_SEC
