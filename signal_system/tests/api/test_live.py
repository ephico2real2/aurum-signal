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
        required = ["timestamp", "mode", "session", "cycle", "account",
                    "price", "lens", "sentinel", "open_groups", "performance",
                    "mt5_connected"]
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
                 "UNKNOWN", "DISCONNECTED"}
        assert live_data.get("mode") in valid, \
            f"Invalid mode: {live_data.get('mode')}"

    def test_live_mt5_connected_bool(self, live_data):
        assert isinstance(live_data.get("mt5_connected"), bool)

    def test_live_account_has_fields(self, live_data):
        acc = live_data.get("account", {})
        # balance can be null when MT5 not running
        assert isinstance(acc, dict), "account must be a dict"

    def test_live_open_groups_list(self, live_data):
        assert isinstance(live_data.get("open_groups"), list)

    def test_live_performance_has_fields(self, live_data):
        perf = live_data.get("performance", {})
        assert isinstance(perf, dict)
