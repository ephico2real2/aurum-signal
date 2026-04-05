"""
conftest.py — Shared fixtures for Signal System API tests
"""
import os
import pytest
import requests
from pathlib import Path

ROOT = Path(__file__).parent.parent
ATHENA_URL = os.environ.get("ATHENA_URL", "http://localhost:7842")
TIMEOUT = 10


def assert_keys(data: dict, keys: list, context: str = ""):
    for key in keys:
        assert key in data, f"Missing key '{key}' in {context or 'response'}: {list(data.keys())}"


@pytest.fixture(scope="session")
def base_url():
    return ATHENA_URL


@pytest.fixture(scope="session")
def api():
    session = requests.Session()
    return session


@pytest.fixture(scope="session")
def live_data(api, base_url):
    r = api.get(f"{base_url}/api/live", timeout=TIMEOUT)
    assert r.status_code == 200, f"/api/live returned {r.status_code}"
    return r.json()
