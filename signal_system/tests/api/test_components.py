"""
test_components.py — Tests for /api/components and /api/reconciler
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import assert_keys, TIMEOUT

EXPECTED_COMPONENTS = [
    "BRIDGE", "FORGE", "LISTENER", "LENS", "SENTINEL",
    "AEGIS", "SCRIBE", "HERALD", "AURUM", "RECONCILER", "ATHENA"
]


class TestComponentsEndpoint:

    def test_components_returns_200(self, api, base_url):
        r = api.get(f"{base_url}/api/components", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_components_structure(self, api, base_url):
        data = api.get(f"{base_url}/api/components", timeout=TIMEOUT).json()
        assert_keys(data, ["components", "total", "healthy", "timestamp"],
                    "/api/components")
        assert isinstance(data["components"], list)

    def test_components_has_all_expected(self, api, base_url):
        data = api.get(f"{base_url}/api/components", timeout=TIMEOUT).json()
        names = [c["name"] for c in data["components"]]
        for expected in EXPECTED_COMPONENTS:
            assert expected in names, \
                f"Missing component: {expected}. Got: {names}"

    def test_each_component_has_required_fields(self, api, base_url):
        data = api.get(f"{base_url}/api/components", timeout=TIMEOUT).json()
        required = ["name", "status", "ok", "timestamp", "note"]
        for c in data["components"]:
            assert_keys(c, required, f"component {c.get('name', '?')}")

    def test_component_status_valid_values(self, api, base_url):
        valid = {"OK", "WARN", "ERROR", "UNKNOWN", "STARTING"}
        data = api.get(f"{base_url}/api/components", timeout=TIMEOUT).json()
        for c in data["components"]:
            assert c["status"] in valid, \
                f"{c['name']} has invalid status: {c['status']}"

    def test_component_ok_matches_status(self, api, base_url):
        data = api.get(f"{base_url}/api/components", timeout=TIMEOUT).json()
        for c in data["components"]:
            if c["status"] == "OK":
                assert c["ok"] is True, \
                    f"{c['name']} status=OK but ok=False"

    def test_healthy_count_matches(self, api, base_url):
        data = api.get(f"{base_url}/api/components", timeout=TIMEOUT).json()
        actual_healthy = sum(1 for c in data["components"] if c["ok"])
        assert data["healthy"] == actual_healthy, \
            f"healthy count mismatch: reported={data['healthy']} actual={actual_healthy}"

    def test_reconciler_endpoint_200(self, api, base_url):
        r = api.get(f"{base_url}/api/reconciler", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_reconciler_structure(self, api, base_url):
        data = api.get(f"{base_url}/api/reconciler", timeout=TIMEOUT).json()
        assert "status" in data
        assert "issue_count" in data or "issues" in data
