"""
test_endpoints.py — Tests for misc API endpoints
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import assert_keys, TIMEOUT


class TestHealthEndpoint:

    def test_health_returns_200(self, api, base_url):
        r = api.get(f"{base_url}/api/health", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_health_structure(self, api, base_url):
        data = api.get(f"{base_url}/api/health", timeout=TIMEOUT).json()
        assert "status" in data
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestSessionsEndpoint:

    def test_sessions_returns_200(self, api, base_url):
        r = api.get(f"{base_url}/api/sessions", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_sessions_is_list(self, api, base_url):
        data = api.get(f"{base_url}/api/sessions", timeout=TIMEOUT).json()
        assert isinstance(data, list)


class TestEventsEndpoint:

    def test_events_returns_200(self, api, base_url):
        r = api.get(f"{base_url}/api/events", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_events_is_list(self, api, base_url):
        data = api.get(f"{base_url}/api/events", timeout=TIMEOUT).json()
        assert isinstance(data, list)


class TestPerformanceEndpoint:

    def test_performance_returns_200(self, api, base_url):
        r = api.get(f"{base_url}/api/performance", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_performance_has_fields(self, api, base_url):
        data = api.get(f"{base_url}/api/performance", timeout=TIMEOUT).json()
        assert isinstance(data, dict)


class TestModeEndpoint:

    def test_mode_invalid_returns_400(self, api, base_url):
        r = api.post(f"{base_url}/api/mode",
                     json={"mode": "INVALID"},
                     timeout=TIMEOUT)
        assert r.status_code == 400

    def test_mode_valid_returns_200(self, api, base_url):
        r = api.post(f"{base_url}/api/mode",
                     json={"mode": "WATCH"},
                     timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert data.get("new_mode") == "WATCH"
