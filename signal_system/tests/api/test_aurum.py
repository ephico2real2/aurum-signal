"""
test_aurum.py — Tests for AURUM chat endpoint (marked slow — calls real Claude API)
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import TIMEOUT


@pytest.mark.slow
class TestAurumEndpoint:

    def test_aurum_empty_query_400(self, api, base_url):
        r = api.post(f"{base_url}/api/aurum/ask",
                     json={"query": ""},
                     timeout=TIMEOUT)
        assert r.status_code == 400

    def test_aurum_missing_query_400(self, api, base_url):
        r = api.post(f"{base_url}/api/aurum/ask",
                     json={},
                     timeout=TIMEOUT)
        assert r.status_code == 400

    @pytest.mark.slow
    def test_aurum_responds(self, api, base_url):
        """Calls real Claude API — slow, requires ANTHROPIC_API_KEY."""
        r = api.post(f"{base_url}/api/aurum/ask",
                     json={"query": "What is the current mode?"},
                     timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "response" in data
        assert len(data["response"]) > 0
