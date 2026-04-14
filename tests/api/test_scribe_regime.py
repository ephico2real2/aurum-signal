from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from scribe import Scribe  # noqa: E402


@pytest.mark.unit
def test_scribe_regime_schema_and_roundtrip(tmp_path):
    db = tmp_path / "regime.db"
    s = Scribe(str(db))

    tables = s.query("SELECT name FROM sqlite_master WHERE type='table' AND name='market_regimes'")
    assert tables and tables[0]["name"] == "market_regimes"

    sig_cols = {r["name"] for r in s.query("PRAGMA table_info(signals_received)")}
    tg_cols = {r["name"] for r in s.query("PRAGMA table_info(trade_groups)")}
    assert {"regime_label", "regime_confidence", "regime_model", "regime_entry_mode", "regime_policy"} <= sig_cols
    assert {"regime_label", "regime_confidence", "regime_model", "regime_entry_mode", "regime_policy"} <= tg_cols

    sid = s.log_signal(
        raw="BUY Gold @3200",
        parsed={"type": "ENTRY", "direction": "BUY", "entry_low": 3200, "entry_high": 3201, "sl": 3195, "tp1": 3208},
        mode="SIGNAL",
        channel="unit-test",
        msg_id=1,
    )
    s.update_signal_regime(
        sid,
        {
            "label": "RANGE",
            "confidence": 0.61,
            "model_name": "GAUSSIAN_FALLBACK",
            "entry_mode": "shadow",
            "policy_name": "MEAN_REVERSION_PULLBACK",
            "entry_gate_reason": "entry_mode_shadow",
        },
    )
    row = s.query(
        "SELECT regime_label,regime_confidence,regime_model,regime_entry_mode,regime_policy "
        "FROM signals_received WHERE id=?",
        (sid,),
    )[0]
    assert row["regime_label"] == "RANGE"
    assert row["regime_model"] == "GAUSSIAN_FALLBACK"

    gid = s.log_trade_group(
        {
            "source": "SIGNAL",
            "direction": "BUY",
            "entry_low": 3200.0,
            "entry_high": 3201.0,
            "sl": 3195.0,
            "tp1": 3208.0,
            "num_trades": 2,
            "lot_per_trade": 0.01,
            "regime_label": "RANGE",
            "regime_confidence": 0.61,
            "regime_model": "GAUSSIAN_FALLBACK",
            "regime_entry_mode": "shadow",
            "regime_policy": "MEAN_REVERSION_PULLBACK",
            "regime_fallback_reason": "entry_mode_shadow",
        },
        mode="SIGNAL",
    )
    s.update_trade_group(gid, "CLOSED", total_pnl=12.5, pips=24.0, trades_closed=2, close_reason="TP1_HIT")

    t0 = datetime.now(timezone.utc)
    t1 = t0 + timedelta(minutes=5)

    s.log_market_regime(
        {
            "timestamp": t0.isoformat(),
            "label": "RANGE",
            "confidence": 0.6,
            "posterior": {"RANGE": 0.6, "VOLATILE": 0.4},
            "model_name": "GAUSSIAN_FALLBACK",
            "model_version": "regime-v1",
            "stale": False,
            "age_sec": 1.0,
            "entry_mode": "shadow",
            "apply_entry_policy": False,
            "entry_gate_reason": "entry_mode_shadow",
            "feature_hash": "abc123",
            "features": {"ret_1": 0.1},
        },
        mode="SIGNAL",
        session="LONDON",
    )
    s.log_market_regime(
        {
            "timestamp": t1.isoformat(),
            "label": "TREND_BULL",
            "confidence": 0.72,
            "posterior": {"TREND_BULL": 0.72},
            "model_name": "HMM_GAUSSIAN",
            "model_version": "regime-v1",
            "stale": False,
            "age_sec": 1.0,
            "entry_mode": "active",
            "apply_entry_policy": True,
            "entry_gate_reason": None,
            "feature_hash": "def456",
            "features": {"ret_1": 0.3},
        },
        mode="SIGNAL",
        session="LONDON",
    )

    cur = s.get_latest_regime()
    hist = s.get_regime_history(limit=10, hours=24)
    trans = s.get_regime_transitions(hours=24, limit=10)
    perf = s.get_regime_performance(days=30)
    assert cur.get("label") in ("RANGE", "TREND_BULL")
    assert len(hist) >= 2
    assert trans and trans[0]["to"] == "TREND_BULL"
    assert "by_regime" in perf and isinstance(perf["by_regime"], list)
