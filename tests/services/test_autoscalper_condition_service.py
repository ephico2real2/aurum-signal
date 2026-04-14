from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from autoscalper_condition_service import build_autoscalper_condition_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_db(path: Path, *, open_groups: int = 0, loss_close_time: str | None = None, response: str = "PASS: no setup") -> None:
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE trade_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT)"
        )
        cur.execute(
            "CREATE TABLE trade_positions (id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT, pnl REAL, close_time TEXT)"
        )
        cur.execute(
            "CREATE TABLE aurum_conversations (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, source TEXT, response TEXT)"
        )
        for _ in range(open_groups):
            cur.execute("INSERT INTO trade_groups(status) VALUES ('OPEN')")
        if loss_close_time is not None:
            cur.execute(
                "INSERT INTO trade_positions(status, pnl, close_time) VALUES ('CLOSED', -1.23, ?)",
                (loss_close_time,),
            )
        cur.execute(
            "INSERT INTO aurum_conversations(timestamp, source, response) VALUES (datetime('now'), 'AUTO_SCALPER', ?)",
            (response,),
        )
        conn.commit()
    finally:
        conn.close()


def test_condition_report_aligns_with_g47_style_sell_pattern(tmp_path: Path):
    status_path = tmp_path / "status.json"
    sentinel_path = tmp_path / "sentinel.json"
    market_path = tmp_path / "market_data.json"
    db_path = tmp_path / "aurum_intelligence.db"

    _write_json(status_path, {"sentinel_active": False})
    _write_json(sentinel_path, {"block_trading": False})
    _write_json(
        market_path,
        {
            "timestamp_unix": time.time(),
            "price": {"bid": 195.0, "ask": 195.2},
            "indicators_h1": {"ema_20": 100.0, "ema_50": 105.5, "rsi_14": 48.0},
            "indicators_m15": {"rsi_14": 66.0, "bb_lower": 100.0, "bb_upper": 200.0},
            "indicators_m5": {"rsi_14": 72.0, "ema_20": 101.0, "ema_50": 99.5},
        },
    )
    _seed_db(
        db_path,
        open_groups=0,
        loss_close_time="2026-01-01T00:00:00+00:00",
        response='{"action":"OPEN_GROUP","direction":"SELL"}',
    )

    report = build_autoscalper_condition_report(
        status_path=str(status_path),
        sentinel_path=str(sentinel_path),
        market_path=str(market_path),
        db_path=str(db_path),
        max_groups=2,
    )

    assert report["bridge_prefilters"]["prefilter_pass"] is True
    assert report["bridge_prefilters"]["h1_bias"] == "BEAR"
    assert report["setup_snapshot"]["near_upper_bb"] is True
    assert report["overall"]["g47_g48_sell_pattern_match"] is True
    assert report["latest_autoscalper_responses"][0]["decision"] == "OPEN_GROUP"


def test_condition_report_flags_missing_indicator_payload(tmp_path: Path):
    status_path = tmp_path / "status.json"
    sentinel_path = tmp_path / "sentinel.json"
    market_path = tmp_path / "market_data.json"
    db_path = tmp_path / "aurum_intelligence.db"

    _write_json(status_path, {"sentinel_active": False})
    _write_json(sentinel_path, {"block_trading": False})
    _write_json(
        market_path,
        {
            "timestamp_unix": time.time(),
            "price": {"bid": 4771.69, "ask": 4771.95},
            "indicators_h1": {"rsi_14": 0.0, "ema_20": 0.0, "ema_50": 0.0},
            "indicators_m15": {"rsi_14": 0.0, "bb_lower": 0.0, "bb_upper": 0.0},
            "indicators_m5": {"rsi_14": 0.0, "ema_20": 0.0, "ema_50": 0.0},
        },
    )
    _seed_db(db_path, open_groups=0, response="PASS: no setup")

    report = build_autoscalper_condition_report(
        status_path=str(status_path),
        sentinel_path=str(sentinel_path),
        market_path=str(market_path),
        db_path=str(db_path),
        max_groups=2,
    )

    assert report["bridge_prefilters"]["h1_bias"] == "UNKNOWN"
    assert report["bridge_prefilters"]["prefilter_pass"] is False
    assert report["setup_snapshot"]["indicator_data_quality"] == "missing_or_zero"
    assert "h1_bias_not_tradeable" in report["overall"]["failed_checks"]
