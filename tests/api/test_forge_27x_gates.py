"""
FORGE 2.7.x config + wiring invariants — unit tests.

Replaces test_forge_268_gates.py and test_forge_268_ea_fixes.py, which were
pinned to v2.6.8 specific numbers (e.g. rsi_buy_ceil=70) and EA line numbers
that have long since drifted in v2.7.x.

This suite asserts INVARIANTS, not pinned values. If a config knob is
deliberately retuned for a new run, this suite stays green as long as the
wiring (env → sync → config → EA) remains intact and values fall in sane
ranges.

Tests cover:
  - .env / sync / config / EA wiring integrity (no dead vars, no orphan keys)
  - Gate legend coverage (every gate emitted by EA has a legend entry or
    matches a wildcard pattern)
  - Sanity ranges for the high-impact knobs (rsi_buy_ceil, rsi_sell_floor,
    adx_min, lot factors)
  - v2.7.13/14/15 specific gate codes are wired
  - Throttle globals exist for every per-bar-throttled gate
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "scalper_config.json"
DEFAULTS = ROOT / "config" / "scalper_config.defaults.json"
GATE_LEGEND = ROOT / "config" / "gate_legend.json"
SYNC = ROOT / "scripts" / "sync_scalper_config_from_env.py"
ENV = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
EA = ROOT / "ea" / "FORGE.mq5"
VERSION_FILE = ROOT / "VERSION"


@pytest.fixture(scope="module")
def cfg() -> dict:
    return json.loads(CONFIG.read_text())


@pytest.fixture(scope="module")
def defaults() -> dict:
    return json.loads(DEFAULTS.read_text())


@pytest.fixture(scope="module")
def gate_legend() -> dict:
    return json.loads(GATE_LEGEND.read_text())


@pytest.fixture(scope="module")
def sync_src() -> str:
    return SYNC.read_text()


@pytest.fixture(scope="module")
def env_text() -> str:
    return ENV.read_text() if ENV.exists() else ""


@pytest.fixture(scope="module")
def ea_src() -> str:
    return EA.read_text()


# ──────────────────────────────────────────────────────────────────────────────
# Version stamping
# ──────────────────────────────────────────────────────────────────────────────

def test_version_file_matches_active_config(cfg):
    """VERSION file is the source of truth — scalper_config.json must reflect it."""
    version = VERSION_FILE.read_text().strip()
    assert cfg["version"] == version, (
        f"VERSION file says {version!r} but scalper_config.json says {cfg['version']!r}. "
        f"Run `make scalper-env-sync` or `make forge-compile`."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Sanity ranges (NOT pinned values — these knobs are deliberately retuned)
# ──────────────────────────────────────────────────────────────────────────────

def test_rsi_buy_ceil_in_safe_range(cfg):
    """rsi_buy_ceil must be in (50, 85). Below 50 = always blocks; ≥85 = useless filter."""
    v = cfg["bb_breakout"]["rsi_buy_ceil"]
    assert 50 < v < 85, f"rsi_buy_ceil={v} outside safe range (50, 85)"


def test_rsi_sell_floor_in_safe_range(cfg):
    """rsi_sell_floor must be in (15, 50). Below 15 = SL hunt territory; ≥50 = useless filter."""
    v = cfg["bb_breakout"]["rsi_sell_floor"]
    assert 15 < v < 50, f"rsi_sell_floor={v} outside safe range (15, 50)"


def test_adx_min_breakout_in_safe_range(cfg):
    """adx_min must be in (10, 40). Below 10 = ranging tape; ≥40 = blocks all trends."""
    v = cfg["bb_breakout"]["adx_min"]
    assert 10 <= v < 40, f"adx_min={v} outside safe range [10, 40)"


def test_adx_lot_factors_in_zero_one(cfg):
    """ADX lot factors must be in (0, 1] — 0 = no entry; >1 = invalid amplification."""
    safety = cfg["safety"]
    for key in ("breakout_adx_lot_factor_mid", "breakout_adx_lot_factor_high"):
        v = safety[key]
        assert 0 < v <= 1, f"{key}={v} outside (0, 1]"


def test_lot_factor_high_no_larger_than_mid(cfg):
    """high-ADX should reduce lot at least as much as mid-ADX. high > mid is structurally wrong."""
    s = cfg["safety"]
    assert s["breakout_adx_lot_factor_high"] <= s["breakout_adx_lot_factor_mid"], (
        f"adx_lot_factor_high ({s['breakout_adx_lot_factor_high']}) > "
        f"adx_lot_factor_mid ({s['breakout_adx_lot_factor_mid']}) — high should reduce more"
    )


def test_adx_lot_thresholds_ordered(cfg):
    """mid threshold < high threshold (tiering must be monotonic)."""
    s = cfg["safety"]
    assert s["breakout_adx_lot_mid_threshold"] < s["breakout_adx_lot_high_threshold"]


# ──────────────────────────────────────────────────────────────────────────────
# v2.7.13/14/15 wiring — config keys must exist (values are runtime-tunable)
# ──────────────────────────────────────────────────────────────────────────────

def test_v2713_block_hid_bull_sell_key_present(cfg):
    assert "block_hid_bull_sell" in cfg["bb_breakout"], (
        "block_hid_bull_sell missing from bb_breakout — v2.7.13 HID_BULL gate not wired"
    )


def test_v2713_crash_m15_adx_guard_key_present(cfg):
    # bb_breakout, not safety — matches sync script mapping + EA JsonHasKey(breakout_json, ...)
    assert "h1h4_crash_sell_min_m15_adx" in cfg["bb_breakout"], (
        "h1h4_crash_sell_min_m15_adx missing — v2.7.13 crash bypass M15 guard not wired"
    )


def test_v2712_require_h1_di_sell_key_present(cfg):
    assert "require_h1_di_sell" in cfg["bb_breakout"]


def test_breakout_adx_lot_use_m15_key_present(cfg):
    """v2.7.x: M15 ADX option for lot tiering. Codex review FAIL #3 added env var mapping."""
    assert "breakout_adx_lot_use_m15" in cfg["safety"]


# ──────────────────────────────────────────────────────────────────────────────
# v2.7.14/15 throttle globals — every per-bar throttled gate has its global
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("global_var", [
    "g_scalper_last_hbd_log_bar",              # v2.7.13 HID_BULL
    "g_scalper_last_dir_sell_log_bar",         # v2.7.14 direction SELL
    "g_scalper_last_dir_buy_log_bar",          # v2.7.14 direction BUY
    "g_scalper_last_body_sell_log_bar",        # v2.7.14 body SELL
    "g_scalper_last_body_buy_log_bar",         # v2.7.14 body BUY
    "g_scalper_last_rsibuyceil_log_bar",       # v2.7.15 rsi_buy_ceil
    "g_scalper_last_rsidecl_log_bar",          # v2.7.4 RSI rising
    "g_scalper_last_rsisellfloor_log_bar",     # rsi_sell_floor / adx_floor
    "g_scalper_last_h1disell_log_bar",         # v2.7.12 H1 DI sell
    "g_scalper_last_h1macd_log_bar",           # v2.7.12 H1 MACD sell
    "g_scalper_last_sesscut_log_bar",          # v2.7.7 session cutoff
    "g_scalper_last_adxblk_log_bar",           # v2.7.7 ADX extreme block
    "g_scalper_last_adxsell_log_bar",          # adx_min_sell
    "g_scalper_last_adxdur_log_bar",           # adx_spike (duration)
])
def test_throttle_global_declared(ea_src, global_var):
    """Every throttled gate must have its M5-bar throttle global declared at file scope."""
    assert re.search(rf"^datetime\s+{re.escape(global_var)}\s*=", ea_src, re.MULTILINE), (
        f"Throttle global '{global_var}' not declared at file scope in FORGE.mq5 "
        f"(likely a static-inside-if regression — see v2.7.13 bug)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Gate legend coverage
# ──────────────────────────────────────────────────────────────────────────────

GATE_CODE_RE = re.compile(
    r'JournalRecordSignal\(\s*"SKIP"\s*,\s*"([a-z_]+)"',
)

# Dynamic gate emissions: JournalRecordSignal("SKIP", "<literal_prefix>_" + <var>, ...)
# Examples emitted by FORGE.mq5:
#   JournalRecordSignal("SKIP","open_group_" + fail_reason, ...)
#   JournalRecordSignal("SKIP", "warmup_" + warmup_reason, ...)
# These MUST be covered by a _patterns wildcard in gate_legend.json (e.g. "warmup_*").
GATE_CODE_DYNAMIC_RE = re.compile(
    r'JournalRecordSignal\(\s*"SKIP"\s*,\s*"([a-z_]+_)"\s*\+\s*[a-zA-Z_]',
)


def _gates_emitted_by_ea(ea_src: str) -> set[str]:
    return set(GATE_CODE_RE.findall(ea_src))


def _dynamic_gate_prefixes_emitted_by_ea(ea_src: str) -> set[str]:
    """Extract literal prefixes from `JournalRecordSignal("SKIP", "prefix_" + var, ...)`.

    Returns the prefix WITHOUT the trailing underscore for matching against
    `_patterns` wildcards (whose keys are like `warmup_*`).
    """
    return set(GATE_CODE_DYNAMIC_RE.findall(ea_src))


def _legend_keys(gate_legend: dict) -> set[str]:
    return {k for k in gate_legend if not k.startswith("_")}


def _legend_patterns(gate_legend: dict) -> list[str]:
    patterns = gate_legend.get("_patterns", {})
    return [p.rstrip("*") for p in patterns if p.endswith("*")]


def test_every_ea_gate_has_legend_entry(ea_src, gate_legend):
    """Every gate code FORGE emits must have a legend entry or match a _patterns wildcard."""
    emitted = _gates_emitted_by_ea(ea_src)
    legend_keys = _legend_keys(gate_legend)
    patterns = _legend_patterns(gate_legend)

    missing = []
    for code in emitted:
        if code in legend_keys:
            continue
        if any(code.startswith(p) for p in patterns):
            continue
        missing.append(code)

    assert not missing, (
        f"Gate codes emitted by FORGE.mq5 but missing from gate_legend.json: {sorted(missing)}.\n"
        f"Add entries to config/gate_legend.json with label, explanation, category."
    )


def test_every_dynamic_gate_prefix_has_legend_pattern(ea_src, gate_legend):
    """Dynamic gate emissions ("<prefix>_" + var) must have a matching _patterns wildcard.

    Closes Codex v2.7.37 WARNING #3: the literal-string GATE_CODE_RE misses
    `open_group_<reason>` and `warmup_<reason>` emissions where the suffix is
    a runtime string. Without this test, removing a `_patterns` wildcard from
    gate_legend.json would silently leave dynamic gates undecoded in monitoring.
    """
    prefixes = _dynamic_gate_prefixes_emitted_by_ea(ea_src)
    patterns = _legend_patterns(gate_legend)

    missing = []
    for prefix in prefixes:
        # patterns are stored without the trailing '*' but WITH the trailing '_'
        # (e.g. legend key "warmup_*" → stored as "warmup_").
        if any(prefix == p or prefix.startswith(p) for p in patterns):
            continue
        missing.append(prefix)

    assert not missing, (
        f"Dynamic gate prefixes emitted by FORGE.mq5 (via string concatenation) "
        f"without a matching `_patterns` wildcard in gate_legend.json: {sorted(missing)}.\n"
        f"Add e.g. {{'{sorted(missing)[0] if missing else 'prefix_'}*': {{...}}}} to "
        f"config/gate_legend.json `_patterns` section so monitoring can decode them."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Env / sync / config wiring integrity
# ──────────────────────────────────────────────────────────────────────────────

ENV_VAR_RE = re.compile(r"^([A-Z][A-Z0-9_]+)=", re.MULTILINE)
ENV_FORGE_VAR_RE = re.compile(r"^(FORGE_[A-Z0-9_]+)=", re.MULTILINE)
LOWER_LEAK_RE = re.compile(r"^([a-z][a-z0-9_]*)=", re.MULTILINE)


def test_no_lowercase_forge_keys_in_env(env_text):
    """All FORGE-related env vars must use uppercase canonical FORGE_ prefix.

    Lowercase keys (e.g. adx_hysteresis_enabled) are silently ignored by the
    sync script. Codex review FAIL #4 caught a previous regression.
    """
    leaked = []
    for m in LOWER_LEAK_RE.finditer(env_text):
        key = m.group(1)
        # Allow these — they are non-FORGE convention keys
        if key in {
            "scalpermode", "magic_base", "fixed_lot",
        }:
            continue
        # Heuristic: keys mentioning forge-ish concepts but lowercase = bug
        if any(tok in key for tok in ("adx", "rsi", "atr", "bounce", "breakout", "tp", "sl", "forge")):
            leaked.append(key)
    assert not leaked, (
        f"Lowercase keys in .env that look like FORGE config: {leaked}. "
        f"Rename to FORGE_<UPPERCASE>_ prefix — lowercase variants are dead vars."
    )


# FORGE_ env vars that are intentionally NOT in the sync script — consumed
# directly by Python services or by the EA's MT5 input parameters, not JSON config.
# Add to this set with a comment whenever you intentionally bypass sync.
FORGE_ENV_VARS_NOT_IN_SYNC = {
    "FORGE_SCALPER_MODE",  # EA: MT5 input (line 74). Python: bridge.py reads os.environ directly.
}


def test_every_forge_env_var_has_sync_mapping(env_text, sync_src):
    """Every FORGE_ var in .env must have a mapping in sync_scalper_config_from_env.py,
    unless it is explicitly whitelisted as consumed-outside-sync.

    Codex review FAIL #3 caught FORGE_BREAKOUT_ADX_LOT_USE_M15 as a dead var.
    """
    env_vars = set(ENV_FORGE_VAR_RE.findall(env_text))
    dead = [
        v for v in env_vars
        if f'"{v}"' not in sync_src and v not in FORGE_ENV_VARS_NOT_IN_SYNC
    ]
    assert not dead, (
        f"FORGE_ env vars set in .env but not mapped in sync script: {sorted(dead)}.\n"
        f"Either add a mapping in scripts/sync_scalper_config_from_env.py, "
        f"or add the var to FORGE_ENV_VARS_NOT_IN_SYNC in this test file "
        f"if it is consumed directly by Python services / MT5 inputs."
    )
