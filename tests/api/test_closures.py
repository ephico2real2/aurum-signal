"""
test_closures.py — Tests for /api/closures and /api/closure_stats endpoints
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import assert_keys, TIMEOUT


class TestClosuresEndpoint:

    def test_closures_returns_200(self, api, base_url):
        r = api.get(f"{base_url}/api/closures", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_closures_is_list(self, api, base_url):
        data = api.get(f"{base_url}/api/closures", timeout=TIMEOUT).json()
        assert isinstance(data, list)

    def test_closures_with_days_param(self, api, base_url):
        r = api.get(f"{base_url}/api/closures?days=1&limit=5", timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) <= 5

    def test_closures_row_shape(self, api, base_url):
        """If closures exist, each row should have the expected fields."""
        data = api.get(f"{base_url}/api/closures?days=30", timeout=TIMEOUT).json()
        if not data:
            pytest.skip("No closures in SCRIBE — run trades first")
        row = data[0]
        expected = ["id", "timestamp", "ticket", "trade_group_id",
                    "direction", "close_reason", "pnl", "pips"]
        for key in expected:
            assert key in row, f"Missing key '{key}' in closure row"

    def test_closures_close_reason_valid(self, api, base_url):
        """Close reason should be one of the known values."""
        data = api.get(f"{base_url}/api/closures?days=30", timeout=TIMEOUT).json()
        if not data:
            pytest.skip("No closures in SCRIBE")
        valid_reasons = {"SL_HIT", "TP1_HIT", "TP2_HIT", "TP3_HIT",
                         "MANUAL_CLOSE", "CLOSE_ALL", "PARTIAL_CLOSE",
                         "RECONCILER", "UNKNOWN"}
        for row in data:
            reason = row.get("close_reason")
            assert reason in valid_reasons, \
                f"Unexpected close_reason: {reason}"


class TestClosureStatsEndpoint:

    def test_closure_stats_returns_200(self, api, base_url):
        r = api.get(f"{base_url}/api/closure_stats", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_closure_stats_structure(self, api, base_url):
        data = api.get(f"{base_url}/api/closure_stats", timeout=TIMEOUT).json()
        assert isinstance(data, dict)
        required = ["total", "sl_hits", "tp1_hits", "tp2_hits", "tp3_hits",
                    "manual", "sl_rate", "tp_rate", "total_pnl", "avg_pnl",
                    "avg_pips", "avg_duration_sec"]
        assert_keys(data, required, "/api/closure_stats")

    def test_closure_stats_rates_are_numbers(self, api, base_url):
        data = api.get(f"{base_url}/api/closure_stats", timeout=TIMEOUT).json()
        assert isinstance(data["sl_rate"], (int, float))
        assert isinstance(data["tp_rate"], (int, float))
        assert 0 <= data["sl_rate"] <= 100
        assert 0 <= data["tp_rate"] <= 100

    def test_closure_stats_with_days_param(self, api, base_url):
        r = api.get(f"{base_url}/api/closure_stats?days=1", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_closure_stats_total_consistent(self, api, base_url):
        """sl_hits + tp_hits + manual should not exceed total."""
        data = api.get(f"{base_url}/api/closure_stats?days=30", timeout=TIMEOUT).json()
        parts = (data.get("sl_hits", 0) + data.get("tp1_hits", 0) +
                 data.get("tp2_hits", 0) + data.get("tp3_hits", 0) +
                 data.get("manual", 0))
        assert parts <= data.get("total", 0) + 1  # +1 for RECONCILER/UNKNOWN


class TestLiveClosureFields:

    def test_live_has_recent_closures(self, live_data):
        assert "recent_closures" in live_data, \
            "Missing 'recent_closures' in /api/live — restart ATHENA"
        assert isinstance(live_data["recent_closures"], list)

    def test_live_has_closure_stats(self, live_data):
        assert "closure_stats" in live_data, \
            "Missing 'closure_stats' in /api/live — restart ATHENA"
        stats = live_data["closure_stats"]
        assert isinstance(stats, dict)
        assert "sl_hits" in stats
        assert "tp_rate" in stats
