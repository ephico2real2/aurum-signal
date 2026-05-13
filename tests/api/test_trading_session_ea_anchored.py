"""
trading_session.py — v2.7.49 EA-anchored killzone tests.

Covers the new get_ea_killzone() reader + the scalper_config.json window-config
unification. Uses tmp_path fixtures to write controlled market_data.json + a
fake scalper_config.json so we can exercise every branch without touching the
real MT5 files.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

# Allow standalone import of python/trading_session.py
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

import trading_session as ts_mod
from trading_session import get_ea_killzone, get_ea_session, _kz_window


# ── get_ea_killzone() — file freshness + schema branches ─────────────

def test_get_ea_killzone_returns_label_when_fresh(tmp_path):
    """Fresh market_data.json with forge_session_state.killzone → returns the label + age."""
    p = tmp_path / "market_data.json"
    p.write_text(json.dumps({
        "forge_session_state": {"killzone": "NY_OPEN_KZ", "label": "NY"}
    }))
    label, age = get_ea_killzone(p, max_age_sec=60)
    assert label == "NY_OPEN_KZ"
    assert age is not None and age < 5  # written milliseconds ago


def test_get_ea_killzone_empty_string_is_valid(tmp_path):
    """EA writes '' (no killzone active) — that's a legitimate label, not a missing field."""
    p = tmp_path / "market_data.json"
    p.write_text(json.dumps({"forge_session_state": {"killzone": ""}}))
    label, age = get_ea_killzone(p, max_age_sec=60)
    assert label == ""
    assert age is not None


def test_get_ea_killzone_stale_returns_none(tmp_path):
    """File older than max_age_sec → (None, age) so caller falls back to UTC compute."""
    p = tmp_path / "market_data.json"
    p.write_text(json.dumps({"forge_session_state": {"killzone": "NY_OPEN_KZ"}}))
    # Backdate the mtime to 5 minutes ago
    old = time.time() - 300
    os.utime(p, (old, old))
    label, age = get_ea_killzone(p, max_age_sec=60)
    assert label is None
    assert age is not None and age >= 60


def test_get_ea_killzone_missing_file(tmp_path):
    """File doesn't exist → (None, None)."""
    label, age = get_ea_killzone(tmp_path / "missing.json", max_age_sec=60)
    assert label is None
    assert age is None


def test_get_ea_killzone_unreadable_json(tmp_path):
    """Garbage in file → caller treats as fallback rather than crash."""
    p = tmp_path / "market_data.json"
    p.write_text("{not valid json")
    label, age = get_ea_killzone(p, max_age_sec=60)
    assert label is None
    assert age is not None  # file existed and was fresh; just unparseable


def test_get_ea_killzone_missing_forge_session_state(tmp_path):
    """File present but no forge_session_state object → (None, age)."""
    p = tmp_path / "market_data.json"
    p.write_text(json.dumps({"some_other_field": 123}))
    label, age = get_ea_killzone(p, max_age_sec=60)
    assert label is None
    assert age is not None


def test_get_ea_killzone_missing_killzone_field(tmp_path):
    """forge_session_state present but lacking killzone key → (None, age)."""
    p = tmp_path / "market_data.json"
    p.write_text(json.dumps({"forge_session_state": {"label": "NY"}}))
    label, age = get_ea_killzone(p, max_age_sec=60)
    assert label is None
    assert age is not None


# ── _kz_window() — scalper_config.json read overrides env + defaults ─

def test_kz_window_reads_scalper_config(tmp_path, monkeypatch):
    """When scalper_config.json has session_filter.kz_*_*_min, those win over
    env vars and hardcoded defaults. EA-anchored source of truth for window
    definitions."""
    cfg = tmp_path / "scalper_config.json"
    cfg.write_text(json.dumps({
        "session_filter": {
            "kz_ny_open_start_min":   500,  # 8:20 NY — not the default 420
            "kz_ny_open_end_min":     620,
            "kz_london_open_start_min": 150,
            "kz_london_open_end_min":   310,
            "kz_asia_start_min":         1140,
            "kz_asia_end_min":            180,
            "kz_london_close_start_min": 620,
            "kz_london_close_end_min":   740,
        }
    }))
    monkeypatch.setenv("FORGE_SCALPER_CONFIG_PATH", str(cfg))
    # Clear the cache so the test picks up the override
    ts_mod._SCALPER_CONFIG_CACHE.update({"mtime": 0.0, "data": None, "path": None})
    # Also clear conflicting env vars in case they're set in the test env
    for name in ("SESSION_KZ_NY_OPEN_START_MIN", "SESSION_KZ_NY_OPEN_END_MIN"):
        monkeypatch.delenv(name, raising=False)
    s, e = _kz_window("NY_OPEN")
    assert s == 500 and e == 620


def test_kz_window_env_override_when_no_scalper_config(tmp_path, monkeypatch):
    """No scalper_config.json → env vars win over hardcoded defaults."""
    monkeypatch.setenv("FORGE_SCALPER_CONFIG_PATH", str(tmp_path / "nonexistent.json"))
    monkeypatch.setenv("SESSION_KZ_NY_OPEN_START_MIN", "480")
    monkeypatch.setenv("SESSION_KZ_NY_OPEN_END_MIN",   "660")
    ts_mod._SCALPER_CONFIG_CACHE.update({"mtime": 0.0, "data": None, "path": None})
    s, e = _kz_window("NY_OPEN")
    assert s == 480 and e == 660


def test_kz_window_falls_back_to_defaults(tmp_path, monkeypatch):
    """No scalper_config, no env override → use the hard-coded NY-time defaults."""
    monkeypatch.setenv("FORGE_SCALPER_CONFIG_PATH", str(tmp_path / "nonexistent.json"))
    for name in ("SESSION_KZ_NY_OPEN_START_MIN", "SESSION_KZ_NY_OPEN_END_MIN"):
        monkeypatch.delenv(name, raising=False)
    ts_mod._SCALPER_CONFIG_CACHE.update({"mtime": 0.0, "data": None, "path": None})
    s, e = _kz_window("NY_OPEN")
    # _KZ_DEFAULTS["NY_OPEN"] = (7*60, 10*60)
    assert s == 420 and e == 600


# ── get_ea_session() — v2.7.50 session-side mirror of get_ea_killzone ─

def test_get_ea_session_returns_label_when_fresh(tmp_path):
    """Fresh market_data.json with forge_session_state.label → returns label + age."""
    p = tmp_path / "market_data.json"
    p.write_text(json.dumps({
        "forge_session_state": {"label": "NY", "killzone": "NY_OPEN_KZ"}
    }))
    label, age = get_ea_session(p, max_age_sec=60)
    assert label == "NY"
    assert age is not None and age < 5


def test_get_ea_session_empty_string_is_valid(tmp_path):
    """EA writes 'OFF' or '' for off-hours — empty is a legitimate label."""
    p = tmp_path / "market_data.json"
    p.write_text(json.dumps({"forge_session_state": {"label": ""}}))
    label, age = get_ea_session(p, max_age_sec=60)
    assert label == ""
    assert age is not None


def test_get_ea_session_stale_returns_none(tmp_path):
    """File older than max_age_sec → (None, age) so caller falls back to UTC compute."""
    p = tmp_path / "market_data.json"
    p.write_text(json.dumps({"forge_session_state": {"label": "LONDON"}}))
    old = time.time() - 300
    os.utime(p, (old, old))
    label, age = get_ea_session(p, max_age_sec=60)
    assert label is None
    assert age is not None and age >= 60


def test_get_ea_session_missing_file(tmp_path):
    """File doesn't exist → (None, None)."""
    label, age = get_ea_session(tmp_path / "missing.json", max_age_sec=60)
    assert label is None
    assert age is None


def test_get_ea_session_missing_forge_session_state(tmp_path):
    """File present but no forge_session_state object → (None, age)."""
    p = tmp_path / "market_data.json"
    p.write_text(json.dumps({"some_other_field": 123}))
    label, age = get_ea_session(p, max_age_sec=60)
    assert label is None
    assert age is not None


def test_get_ea_session_missing_label_field(tmp_path):
    """forge_session_state present but lacking label key → (None, age)."""
    p = tmp_path / "market_data.json"
    p.write_text(json.dumps({"forge_session_state": {"killzone": "NY_OPEN_KZ"}}))
    label, age = get_ea_session(p, max_age_sec=60)
    assert label is None
    assert age is not None


def test_get_ea_session_independent_from_killzone(tmp_path):
    """Same file, two readers: get_ea_session pulls label, get_ea_killzone pulls killzone.
    Confirms the two readers don't cross-contaminate when one field is missing."""
    p = tmp_path / "market_data.json"
    p.write_text(json.dumps({
        "forge_session_state": {"label": "LONDON_NY", "killzone": "LONDON_CLOSE_KZ"}
    }))
    sess_label, _ = get_ea_session(p, max_age_sec=60)
    kz_label, _   = get_ea_killzone(p, max_age_sec=60)
    assert sess_label == "LONDON_NY"
    assert kz_label   == "LONDON_CLOSE_KZ"


def test_kz_window_malformed_scalper_config_falls_through(tmp_path, monkeypatch):
    """scalper_config.json present but values aren't ints → fall through to env/default."""
    cfg = tmp_path / "scalper_config.json"
    cfg.write_text(json.dumps({
        "session_filter": {
            "kz_ny_open_start_min": "not-a-number",
            "kz_ny_open_end_min":   "neither",
        }
    }))
    monkeypatch.setenv("FORGE_SCALPER_CONFIG_PATH", str(cfg))
    for name in ("SESSION_KZ_NY_OPEN_START_MIN", "SESSION_KZ_NY_OPEN_END_MIN"):
        monkeypatch.delenv(name, raising=False)
    ts_mod._SCALPER_CONFIG_CACHE.update({"mtime": 0.0, "data": None, "path": None})
    s, e = _kz_window("NY_OPEN")
    assert s == 420 and e == 600  # defaults
