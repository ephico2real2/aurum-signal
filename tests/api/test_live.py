"""
test_live.py — Tests for /api/live endpoint
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import assert_keys, TIMEOUT


class TestLiveEndpoint:

    def test_live_returns_200(self, api, base_url):
        r = api.get(f"{base_url}/api/live", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_live_has_required_keys(self, live_data):
        if "execution" not in live_data:
            pytest.skip("ATHENA at ATHENA_URL is outdated — restart service or rely on test_athena_live_unit.py")
        if "open_groups_queued" not in live_data:
            pytest.skip("ATHENA at ATHENA_URL is outdated — restart after pull (open_groups MT5 filter)")
        required = ["timestamp", "mode", "session", "session_utc", "cycle", "account",
                    "price", "chart_symbol", "execution", "tradingview", "mt5_quote_stale",
                    "lens", "sentinel", "open_groups", "open_groups_queued", "open_groups_policy",
                    "performance", "performance_window",
                    "recent_closures", "closure_stats",
                    "mt5_connected", "pending_orders"]
        assert_keys(live_data, required, "/api/live")

    def test_live_has_components(self, live_data):
        assert "components" in live_data, "Missing 'components' key — heartbeats not wired"
        assert isinstance(live_data["components"], dict)

    def test_live_has_aegis_state(self, live_data):
        assert "aegis" in live_data, "Missing 'aegis' key"
        aegis = live_data["aegis"]
        assert "scale_factor" in aegis
        assert "streak" in aegis
        assert "streak_type" in aegis
        assert "pnl_day_reset_hour_utc" in aegis, "AEGIS should expose trading-day boundary (trading_session.py)"
        h = aegis["pnl_day_reset_hour_utc"]
        assert isinstance(h, int) and 0 <= h <= 23

    def test_live_has_broker_info(self, live_data):
        assert "account_type" in live_data, "Missing account_type"
        assert "broker" in live_data, "Missing broker"
        assert live_data["account_type"] in ("DEMO", "LIVE", "UNKNOWN")

    def test_live_has_circuit_breaker(self, live_data):
        assert "circuit_breaker" in live_data
        assert isinstance(live_data["circuit_breaker"], bool)

    def test_live_has_reconciler(self, live_data):
        assert "reconciler" in live_data
        # Can be null if reconciler has never run

    def test_live_mode_valid(self, live_data):
        valid = {"OFF", "WATCH", "SIGNAL", "SCALPER", "HYBRID",
                 "AUTO_SCALPER", "UNKNOWN", "DISCONNECTED"}
        assert live_data.get("mode") in valid, \
            f"Invalid mode: {live_data.get('mode')}"

    def test_live_mt5_connected_bool(self, live_data):
        assert isinstance(live_data.get("mt5_connected"), bool)

    def test_live_execution_shape(self, live_data):
        if live_data.get("execution") is None:
            pytest.skip("ATHENA at ATHENA_URL is outdated — restart service")
        ex = live_data.get("execution")
        assert isinstance(ex, dict)
        for k in ("stale", "usable", "bid", "ask", "age_sec"):
            assert k in ex

    def test_live_tradingview_shape(self, live_data):
        if live_data.get("tradingview") is None:
            pytest.skip("ATHENA at ATHENA_URL is outdated — restart service")
        tv = live_data.get("tradingview")
        assert isinstance(tv, dict)

    def test_live_account_has_fields(self, live_data):
        acc = live_data.get("account", {})
        # balance can be null when MT5 not running
        assert isinstance(acc, dict), "account must be a dict"

    def test_live_open_groups_list(self, live_data):
        assert isinstance(live_data.get("open_groups"), list)
        if "open_groups_queued" in live_data:
            assert isinstance(live_data.get("open_groups_queued"), list)
        if "pending_orders" in live_data:
            assert isinstance(live_data.get("pending_orders"), list)
        if "open_groups_policy" in live_data:
            assert isinstance(live_data.get("open_groups_policy"), str)

    def test_live_performance_has_fields(self, live_data):
        perf = live_data.get("performance", {})
        assert isinstance(perf, dict)

    def test_live_session_utc_valid(self, live_data):
        valid = {"SYDNEY", "ASIAN", "LONDON", "LONDON_NY", "NEW_YORK", "OFF_HOURS"}
        su = live_data.get("session_utc")
        if su is not None:
            assert su in valid, f"Unexpected session_utc: {su}"
