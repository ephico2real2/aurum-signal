"""
test_schema_bundle_integrity.py — No extra deps: manifest + valid JSON files.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"


@pytest.mark.unit
def test_manifest_version_and_paths():
    man_path = SCHEMAS / "manifest.json"
    assert man_path.is_file()
    man = json.loads(man_path.read_text(encoding="utf-8"))
    assert man.get("version")
    assert isinstance(man.get("files"), list)
    for rel in man["files"]:
        p = SCHEMAS / rel
        assert p.is_file(), f"manifest lists missing file: {rel}"
        raw = p.read_text(encoding="utf-8")
        if rel.endswith(".json"):
            json.loads(raw)
        elif rel.endswith((".yaml", ".yml")):
            assert raw.lstrip().startswith("openapi:"), f"{rel} should be an OpenAPI YAML"


@pytest.mark.unit
def test_openapi_spec_covers_http_api():
    spec = SCHEMAS / "openapi.yaml"
    text = spec.read_text(encoding="utf-8")
    assert "openapi: 3.0.3" in text
    assert "/api/live:" in text
    assert "/api/openapi.yaml:" in text


@pytest.mark.unit
def test_data_contract_doc_exists():
    doc = ROOT / "docs" / "DATA_CONTRACT.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "File bus" in text or "file bus" in text
    assert "/api/live" in text
    assert "/api/docs" in text
    assert "SCRIBE_QUERY_EXAMPLES" in text


@pytest.mark.unit
def test_sync_openapi_scribe_script_idempotent():
    script = ROOT / "scripts" / "sync_openapi_scribe_examples.py"
    openapi = ROOT / "schemas" / "openapi.yaml"
    before = openapi.read_text(encoding="utf-8")
    r = subprocess.run([sys.executable, str(script)], cwd=str(ROOT), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert openapi.read_text(encoding="utf-8") == before
