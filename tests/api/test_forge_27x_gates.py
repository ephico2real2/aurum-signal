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


def test_adx_lot_factor_floor_not_silent_reduction(cfg):
    """ADX lot factors must NOT drop below 0.5.

    Codex audit history (2.7.x): adx_lot_factor_high was silently 0.125, firing 0.02 lots
    on perfect SELL setups at ADX > 35. Operator policy 2026-05-12: high-tier may be 0.5
    (deliberate de-risk in trend-exhaustion zone), but anything below 0.5 is the old
    silent-reduction bug returning. Mid-tier (ADX 35-44) stays at 1.0 by policy.
    """
    s = cfg["safety"]
    mid = s["breakout_adx_lot_factor_mid"]
    high = s["breakout_adx_lot_factor_high"]
    assert mid == 1.0, f"breakout_adx_lot_factor_mid={mid} — must be 1.0 (mid tier should not reduce)"
    assert 0.5 <= high <= 1.0, (
        f"breakout_adx_lot_factor_high={high} outside [0.5, 1.0] — "
        f"<0.5 reintroduces the silent-reduction bug fixed in 2.7.x"
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


def test_ma_crossover_setup_wired_end_to_end(ea_src, cfg, defaults):
    """v2.7.42 MA_CROSSOVER Phase 2 — ensure EA + config + gate legend are aligned."""
    # 1. setup_type literal emitted in EA
    assert 'setup_type = "MA_CROSSOVER"' in ea_src, \
        "MA_CROSSOVER setup_type literal missing from ea/FORGE.mq5 dispatch"
    # 2. Detector helper exists
    assert "DetectMaCrossoverEvent" in ea_src, \
        "DetectMaCrossoverEvent helper missing from ea/FORGE.mq5"
    # 3. All 7 config knobs present in active config (matching defaults JSON shape)
    for key in (
        ("setup", "ma_crossover_enabled"),
        ("atom", "ma_crossover_adx_min"),
        ("geometry", "ma_crossover_lot_factor"),
        ("geometry", "ma_crossover_sl_atr_mult"),
        ("geometry", "ma_crossover_tp1_atr_mult"),
        ("geometry", "ma_crossover_tp2_atr_mult"),
        ("timing", "ma_crossover_cooldown_seconds"),
    ):
        section, name = key
        assert section in cfg, f"active config missing '{section}' section"
        assert name in cfg[section], f"active config missing '{section}.{name}'"
    # 4. Default-OFF by default — EA dispatch is gated by enabled flag
    assert defaults["setup"]["ma_crossover_enabled"] == 0, \
        "ma_crossover_enabled should default to 0 (Phase 2 ships OFF)"
    # 5. Lot factor present in combined_lot_factor product (don't quietly drop)
    assert "ma_crossover_factor" in ea_src, \
        "ma_crossover_factor not multiplied into combined_lot_factor"
    # 6. All 3 SKIP gate codes are emitted (via Filter_* helpers in v2.7.43 — constructed
    #    from setup_lower + suffix at runtime, so check gate_legend.json instead of ea_src)
    import json as _json
    from pathlib import Path as _Path
    legend = _json.loads((_Path(__file__).parent.parent.parent / "config" / "gate_legend.json").read_text())
    for gate in ("ma_crossover_adx_below_min", "ma_crossover_m15_misalign", "ma_crossover_cooldown"):
        assert gate in legend, f"gate code {gate} not in gate_legend.json"
    # Verify the dispatch uses the layered helpers (Filter_AdxFloor, Filter_M15TrendAligned, Filter_Cooldown)
    assert 'Filter_AdxFloor("MA_CROSSOVER"' in ea_src, "MA_CROSSOVER not migrated to Filter_AdxFloor helper"
    assert 'Filter_M15TrendAligned("MA_CROSSOVER"' in ea_src, "MA_CROSSOVER not migrated to Filter_M15TrendAligned helper"
    assert 'Filter_Cooldown("MA_CROSSOVER"' in ea_src, "MA_CROSSOVER not migrated to Filter_Cooldown helper"


def test_vwap_reversion_setup_wired_end_to_end(ea_src, cfg, defaults, gate_legend):
    """v2.7.42 VWAP_REVERSION Phase 2 — EA + config + gate legend aligned."""
    # 1. setup_type literal emitted in EA
    assert 'setup_type = "VWAP_REVERSION"' in ea_src, \
        "VWAP_REVERSION setup_type literal missing from ea/FORGE.mq5 dispatch"
    # 2. Detector helper exists
    assert "DetectVwapReversionEvent" in ea_src, \
        "DetectVwapReversionEvent helper missing from ea/FORGE.mq5"
    # 3. All 9 config knobs present in active config
    for key in (
        ("setup", "vwap_reversion_enabled"),
        ("atom", "vwap_reversion_min_deviation_atr"),
        ("atom", "vwap_reversion_max_deviation_atr"),
        ("atom", "vwap_reversion_min_extension_bars"),
        ("geometry", "vwap_reversion_lot_factor"),
        ("geometry", "vwap_reversion_sl_atr_mult"),
        ("geometry", "vwap_reversion_tp1_atr_mult"),
        ("geometry", "vwap_reversion_tp2_atr_mult"),
        ("timing", "vwap_reversion_cooldown_seconds"),
    ):
        section, name = key
        assert section in cfg, f"active config missing '{section}' section"
        assert name in cfg[section], f"active config missing '{section}.{name}'"
    # 4. Default-OFF
    assert defaults["setup"]["vwap_reversion_enabled"] == 0, \
        "vwap_reversion_enabled should default to 0 (Phase 2 ships OFF)"
    # 5. Lot factor present in combined_lot_factor product
    assert "vwap_reversion_factor" in ea_src, \
        "vwap_reversion_factor not multiplied into combined_lot_factor"
    # 6. SKIP gate code registered (Filter_Cooldown constructs code at runtime in v2.7.43)
    assert "vwap_reversion_cooldown" in gate_legend, \
        "gate code vwap_reversion_cooldown not in gate_legend.json"
    assert 'Filter_Cooldown("VWAP_REVERSION"' in ea_src, \
        "VWAP_REVERSION not migrated to Filter_Cooldown helper"


def test_fib_confluence_setup_wired_end_to_end(ea_src, cfg, defaults, gate_legend):
    """v2.7.42 FIB_CONFLUENCE Phase 2 — EA + config + gate legend aligned."""
    # 1. setup_type literal emitted in EA
    assert 'setup_type = "FIB_CONFLUENCE"' in ea_src, \
        "FIB_CONFLUENCE setup_type literal missing from ea/FORGE.mq5 dispatch"
    # 2. Detector helper exists
    assert "DetectFibConfluenceEvent" in ea_src, \
        "DetectFibConfluenceEvent helper missing from ea/FORGE.mq5"
    # 3. Detector uses all 3 fib levels (382, 50, 618)
    for level in ("g_fib_382", "g_fib_50", "g_fib_618"):
        assert level in ea_src, f"detector should reference {level}"
    # 4. All 9 config knobs present in active config
    for key in (
        ("setup", "fib_confluence_enabled"),
        ("atom", "fib_confluence_min_confluences"),
        ("atom", "fib_confluence_tolerance_atr"),
        ("atom", "fib_confluence_min_swing_atr"),
        ("geometry", "fib_confluence_lot_factor"),
        ("geometry", "fib_confluence_sl_atr_mult"),
        ("geometry", "fib_confluence_tp1_atr_mult"),
        ("geometry", "fib_confluence_tp2_atr_mult"),
        ("timing", "fib_confluence_cooldown_seconds"),
    ):
        section, name = key
        assert section in cfg, f"active config missing '{section}' section"
        assert name in cfg[section], f"active config missing '{section}.{name}'"
    # 5. Default-OFF
    assert defaults["setup"]["fib_confluence_enabled"] == 0, \
        "fib_confluence_enabled should default to 0 (Phase 2 ships OFF)"
    # 6. Lot factor present in combined_lot_factor product
    assert "fib_confluence_factor" in ea_src, \
        "fib_confluence_factor not multiplied into combined_lot_factor"
    # 7. SKIP gate code registered (Filter_Cooldown constructs code at runtime in v2.7.43)
    assert "fib_confluence_cooldown" in gate_legend, \
        "gate code fib_confluence_cooldown not in gate_legend.json"
    assert 'Filter_Cooldown("FIB_CONFLUENCE"' in ea_src, \
        "FIB_CONFLUENCE not migrated to Filter_Cooldown helper"


def test_inside_bar_setup_wired_end_to_end(ea_src, cfg, defaults):
    """v2.7.42 INSIDE_BAR — C-extended Tier 1 — trivial 2-bar pattern, no new state."""
    # 1. setup_type literal emitted in EA
    assert 'setup_type = "INSIDE_BAR"' in ea_src, \
        "INSIDE_BAR setup_type literal missing from ea/FORGE.mq5 dispatch"
    # 2. Detector helper exists
    assert "DetectInsideBarBreakoutEvent" in ea_src, \
        "DetectInsideBarBreakoutEvent helper missing from ea/FORGE.mq5"
    # 3. All 8 config knobs present in active config
    for key in (
        ("setup", "inside_bar_enabled"),
        ("atom", "inside_bar_min_outer_atr"),
        ("atom", "inside_bar_adx_min"),
        ("geometry", "inside_bar_lot_factor"),
        ("geometry", "inside_bar_sl_atr_mult"),
        ("geometry", "inside_bar_tp1_atr_mult"),
        ("geometry", "inside_bar_tp2_atr_mult"),
        ("timing", "inside_bar_cooldown_seconds"),
    ):
        section, name = key
        assert section in cfg, f"active config missing '{section}' section"
        assert name in cfg[section], f"active config missing '{section}.{name}'"
    # 4. Default-OFF
    assert defaults["setup"]["inside_bar_enabled"] == 0, \
        "inside_bar_enabled should default to 0 (C-extended Tier 1 ships OFF)"
    # 5. Lot factor present in combined_lot_factor product
    assert "inside_bar_factor" in ea_src, \
        "inside_bar_factor not multiplied into combined_lot_factor"
    # 6. Both SKIP gate codes registered (Filter_* helpers construct codes from
    #    setup_lower + suffix at runtime in v2.7.43)
    import json as _json
    from pathlib import Path as _Path
    legend = _json.loads((_Path(__file__).parent.parent.parent / "config" / "gate_legend.json").read_text())
    for gate in ("inside_bar_adx_below_min", "inside_bar_cooldown"):
        assert gate in legend, f"gate code {gate} not in gate_legend.json"
    # Verify dispatch uses the layered helpers
    assert 'Filter_AdxFloor("INSIDE_BAR"' in ea_src, "INSIDE_BAR not migrated to Filter_AdxFloor helper"
    assert 'Filter_Cooldown("INSIDE_BAR"' in ea_src, "INSIDE_BAR not migrated to Filter_Cooldown helper"


def test_bb_squeeze_setup_wired_end_to_end(ea_src, cfg, defaults, gate_legend):
    """v2.7.42 BB_SQUEEZE — C-extended Tier 1 — stateless percentile-rank detector."""
    # 1. setup_type literal emitted
    assert 'setup_type = "BB_SQUEEZE"' in ea_src, \
        "BB_SQUEEZE setup_type literal missing from ea/FORGE.mq5 dispatch"
    # 2. Detector helper exists
    assert "DetectBbSqueezeBreakoutEvent" in ea_src, \
        "DetectBbSqueezeBreakoutEvent helper missing from ea/FORGE.mq5"
    # 3. Detector reads BB upper (buf 1) and lower (buf 2)
    assert "CopyBuffer(g_mtf[0].h_bb, 1, 1," in ea_src, \
        "detector should CopyBuffer BB upper (buf 1)"
    assert "CopyBuffer(g_mtf[0].h_bb, 2, 1," in ea_src, \
        "detector should CopyBuffer BB lower (buf 2)"
    # 4. All 10 config knobs present
    for key in (
        ("setup", "bb_squeeze_enabled"),
        ("atom", "bb_squeeze_lookback_bars"),
        ("atom", "bb_squeeze_pctile_threshold"),
        ("atom", "bb_squeeze_min_breakout_atr"),
        ("atom", "bb_squeeze_adx_min"),
        ("geometry", "bb_squeeze_lot_factor"),
        ("geometry", "bb_squeeze_sl_atr_mult"),
        ("geometry", "bb_squeeze_tp1_atr_mult"),
        ("geometry", "bb_squeeze_tp2_atr_mult"),
        ("timing", "bb_squeeze_cooldown_seconds"),
    ):
        section, name = key
        assert section in cfg, f"active config missing '{section}' section"
        assert name in cfg[section], f"active config missing '{section}.{name}'"
    # 5. Default-OFF
    assert defaults["setup"]["bb_squeeze_enabled"] == 0, \
        "bb_squeeze_enabled should default to 0 (C-extended Tier 1 ships OFF)"
    # 6. Lot factor in combined_lot_factor product
    assert "bb_squeeze_factor" in ea_src, \
        "bb_squeeze_factor not multiplied into combined_lot_factor"
    # 7. Both SKIP codes registered (Filter_* helpers construct codes at runtime in v2.7.43)
    for gate in ("bb_squeeze_adx_below_min", "bb_squeeze_cooldown"):
        assert gate in gate_legend, f"gate code {gate} not in gate_legend.json"
    assert 'Filter_AdxFloor("BB_SQUEEZE"' in ea_src, "BB_SQUEEZE not migrated to Filter_AdxFloor helper"
    assert 'Filter_Cooldown("BB_SQUEEZE"' in ea_src, "BB_SQUEEZE not migrated to Filter_Cooldown helper"


def test_orb_setup_wired_end_to_end(ea_src, cfg, defaults, gate_legend):
    """v2.7.42 ORB — C-extended Tier 2 — Opening Range Breakout with daily reset."""
    # 1. setup_type literal emitted
    assert 'setup_type = "ORB"' in ea_src, \
        "ORB setup_type literal missing from ea/FORGE.mq5 dispatch"
    # 2. Detector helper + state machine pieces exist
    assert "DetectOrbBreakoutEvent" in ea_src, \
        "DetectOrbBreakoutEvent helper missing"
    for sym in ("g_orb_window_high", "g_orb_window_low", "g_orb_window_locked", "g_orb_window_day_stamp"):
        assert sym in ea_src, f"ORB state global {sym} missing"
    # 3. Uses GetSessionAnchorTime() for NY-local minute-of-day
    assert "GetSessionAnchorTime()" in ea_src, \
        "ORB detector should use GetSessionAnchorTime for NY-local time"
    assert "MinuteInWindow" in ea_src, \
        "ORB detector should use MinuteInWindow helper"
    # 4. All 11 config knobs present
    for key in (
        ("setup", "orb_enabled"),
        ("atom", "orb_window_start_min"),
        ("atom", "orb_window_end_min"),
        ("atom", "orb_min_range_atr"),
        ("atom", "orb_min_breakout_atr"),
        ("atom", "orb_adx_min"),
        ("geometry", "orb_lot_factor"),
        ("geometry", "orb_sl_atr_mult"),
        ("geometry", "orb_tp1_atr_mult"),
        ("geometry", "orb_tp2_atr_mult"),
        ("timing", "orb_cooldown_seconds"),
    ):
        section, name = key
        assert section in cfg, f"active config missing '{section}' section"
        assert name in cfg[section], f"active config missing '{section}.{name}'"
    # 5. Default-OFF + sensible default window (London Open NY-local)
    assert defaults["setup"]["orb_enabled"] == 0, "orb_enabled should default to 0"
    assert cfg["atom"]["orb_window_start_min"] < cfg["atom"]["orb_window_end_min"], \
        "ORB window start must precede end (within-day window)"
    # 6. Lot factor wired
    assert "orb_factor" in ea_src, "orb_factor not in combined_lot_factor"
    # 7. SKIP codes registered (Filter_* helpers construct codes at runtime in v2.7.43)
    for gate in ("orb_adx_below_min", "orb_cooldown"):
        assert gate in gate_legend, f"gate code {gate} not in gate_legend.json"
    assert 'Filter_AdxFloor("ORB"' in ea_src, "ORB not migrated to Filter_AdxFloor helper"
    assert 'Filter_Cooldown("ORB"' in ea_src, "ORB not migrated to Filter_Cooldown helper"


def test_gap_and_go_setup_wired_end_to_end(ea_src, cfg, defaults, gate_legend):
    """v2.7.42 GAP_AND_GO — C-extended Tier 2 — bar-time-skip + price-jump."""
    # 1. setup_type literal emitted
    assert 'setup_type = "GAP_AND_GO"' in ea_src, \
        "GAP_AND_GO setup_type literal missing"
    # 2. Detector helper exists
    assert "DetectGapAndGoEvent" in ea_src, \
        "DetectGapAndGoEvent helper missing"
    # 3. Detector uses iTime for skip + iOpen/iClose for gap
    assert "iTime(_Symbol, PERIOD_M5, 0)" in ea_src, \
        "GAP_AND_GO detector should read M5 bar times"
    # 4. All 9 config knobs present
    for key in (
        ("setup", "gap_and_go_enabled"),
        ("atom", "gap_and_go_min_time_skip_seconds"),
        ("atom", "gap_and_go_min_gap_atr"),
        ("atom", "gap_and_go_max_gap_atr"),
        ("geometry", "gap_and_go_lot_factor"),
        ("geometry", "gap_and_go_sl_atr_mult"),
        ("geometry", "gap_and_go_tp1_atr_mult"),
        ("geometry", "gap_and_go_tp2_atr_mult"),
        ("timing", "gap_and_go_cooldown_seconds"),
    ):
        section, name = key
        assert section in cfg, f"active config missing '{section}' section"
        assert name in cfg[section], f"active config missing '{section}.{name}'"
    # 5. Default-OFF + sensible bounds
    assert defaults["setup"]["gap_and_go_enabled"] == 0, "gap_and_go_enabled should default to 0"
    assert cfg["atom"]["gap_and_go_min_gap_atr"] < cfg["atom"]["gap_and_go_max_gap_atr"], \
        "gap_and_go min < max"
    # 6. Lot factor wired
    assert "gap_and_go_factor" in ea_src, "gap_and_go_factor not in combined_lot_factor"
    # 7. SKIP code registered (Filter_Cooldown constructs code at runtime in v2.7.43)
    assert "gap_and_go_cooldown" in gate_legend, "gate code gap_and_go_cooldown not in gate_legend.json"
    assert 'Filter_Cooldown("GAP_AND_GO"' in ea_src, \
        "GAP_AND_GO not migrated to Filter_Cooldown helper"


def test_swing_infra_and_double_patterns_wired(ea_src, cfg, defaults, gate_legend):
    """v2.7.42 C-extended Tier 3 — swing-point ring buffer + DOUBLE_TOP/BOTTOM."""
    # 1. Swing-point infra: struct + globals + helper functions
    assert "struct SwingPoint" in ea_src, "SwingPoint struct missing"
    for sym in ("g_swings[64]", "g_swings_count", "g_swings_next_idx", "g_swings_last_update_bar"):
        assert sym in ea_src, f"swing global {sym} missing"
    assert "UpdateSwingsOnNewBar" in ea_src, "UpdateSwingsOnNewBar helper missing"
    assert "GetRecentSwings" in ea_src, "GetRecentSwings helper missing"
    # 2. Both detectors + setup_type literals
    assert "DetectDoubleTopEvent" in ea_src, "DetectDoubleTopEvent missing"
    assert "DetectDoubleBottomEvent" in ea_src, "DetectDoubleBottomEvent missing"
    assert 'setup_type = "DOUBLE_TOP"' in ea_src, "DOUBLE_TOP setup_type literal missing"
    assert 'setup_type = "DOUBLE_BOTTOM"' in ea_src, "DOUBLE_BOTTOM setup_type literal missing"
    # 3. Shared swing infra config knobs
    for key in (("atom", "swing_lookback_bars"), ("atom", "swing_min_size_atr")):
        section, name = key
        assert section in cfg, f"active config missing '{section}'"
        assert name in cfg[section], f"active config missing '{section}.{name}'"
    # 4. Double-pattern config knobs (shared + per-direction enables)
    for key in (
        ("setup", "double_top_enabled"),
        ("setup", "double_bottom_enabled"),
        ("atom", "double_pattern_peak_tolerance_atr"),
        ("atom", "double_pattern_min_neckline_drop_atr"),
        ("atom", "double_pattern_adx_min"),
        ("geometry", "double_pattern_lot_factor"),
        ("geometry", "double_pattern_sl_atr_mult"),
        ("geometry", "double_pattern_tp1_atr_mult"),
        ("geometry", "double_pattern_tp2_atr_mult"),
        ("timing", "double_pattern_cooldown_seconds"),
    ):
        section, name = key
        assert section in cfg, f"active config missing '{section}'"
        assert name in cfg[section], f"active config missing '{section}.{name}'"
    # 5. Default-OFF for both directions
    assert defaults["setup"]["double_top_enabled"] == 0
    assert defaults["setup"]["double_bottom_enabled"] == 0
    # 6. Shared lot factor in combined_lot_factor
    assert "double_pattern_factor" in ea_src, "double_pattern_factor not in combined_lot_factor"
    # 7. All 4 SKIP codes registered (Filter_* helpers construct codes at runtime in v2.7.43)
    for gate in ("double_top_adx_below_min", "double_top_cooldown",
                 "double_bottom_adx_below_min", "double_bottom_cooldown"):
        assert gate in gate_legend, f"gate code {gate} not in gate_legend.json"
    assert 'Filter_AdxFloor("DOUBLE_TOP"' in ea_src, "DOUBLE_TOP not migrated to Filter_AdxFloor helper"
    assert 'Filter_Cooldown("DOUBLE_TOP"' in ea_src, "DOUBLE_TOP not migrated to Filter_Cooldown helper"
    assert 'Filter_AdxFloor("DOUBLE_BOTTOM"' in ea_src, "DOUBLE_BOTTOM not migrated to Filter_AdxFloor helper"
    assert 'Filter_Cooldown("DOUBLE_BOTTOM"' in ea_src, "DOUBLE_BOTTOM not migrated to Filter_Cooldown helper"


def test_head_and_shoulders_setups_wired(ea_src, cfg, defaults, gate_legend):
    """v2.7.42 C-extended Tier 3 — HEAD_AND_SHOULDERS + INVERSE_HEAD_AND_SHOULDERS."""
    # Detectors + setup_type literals
    for sym in ("DetectHeadAndShouldersEvent", "DetectInverseHeadAndShouldersEvent"):
        assert sym in ea_src, f"{sym} missing"
    assert 'setup_type = "HEAD_AND_SHOULDERS"' in ea_src
    assert 'setup_type = "INVERSE_HEAD_AND_SHOULDERS"' in ea_src
    # Config knobs (10)
    for key in (
        ("setup", "head_and_shoulders_enabled"),
        ("setup", "inverse_head_and_shoulders_enabled"),
        ("atom", "hs_shoulder_tolerance_atr"),
        ("atom", "hs_head_prominence_atr"),
        ("atom", "hs_adx_min"),
        ("geometry", "hs_lot_factor"),
        ("geometry", "hs_sl_atr_mult"),
        ("geometry", "hs_tp1_atr_mult"),
        ("geometry", "hs_tp2_atr_mult"),
        ("timing", "hs_cooldown_seconds"),
    ):
        section, name = key
        assert section in cfg, f"missing section {section}"
        assert name in cfg[section], f"missing {section}.{name}"
    # Default-OFF
    assert defaults["setup"]["head_and_shoulders_enabled"] == 0
    assert defaults["setup"]["inverse_head_and_shoulders_enabled"] == 0
    # Shared lot factor wired
    assert "hs_factor" in ea_src, "hs_factor not in combined_lot_factor"
    # 4 SKIP codes registered (Filter_* helpers construct codes at runtime in v2.7.43)
    for gate in ("head_and_shoulders_adx_below_min", "head_and_shoulders_cooldown",
                 "inverse_head_and_shoulders_adx_below_min", "inverse_head_and_shoulders_cooldown"):
        assert gate in gate_legend, f"gate code {gate} not in gate_legend.json"
    assert 'Filter_AdxFloor("HEAD_AND_SHOULDERS"' in ea_src, \
        "HEAD_AND_SHOULDERS not migrated to Filter_AdxFloor helper"
    assert 'Filter_Cooldown("HEAD_AND_SHOULDERS"' in ea_src, \
        "HEAD_AND_SHOULDERS not migrated to Filter_Cooldown helper"
    assert 'Filter_AdxFloor("INVERSE_HEAD_AND_SHOULDERS"' in ea_src, \
        "INVERSE_HEAD_AND_SHOULDERS not migrated to Filter_AdxFloor helper"
    assert 'Filter_Cooldown("INVERSE_HEAD_AND_SHOULDERS"' in ea_src, \
        "INVERSE_HEAD_AND_SHOULDERS not migrated to Filter_Cooldown helper"


def test_flag_pennant_setup_wired(ea_src, cfg, defaults, gate_legend):
    """v2.7.42 C-extended Tier 3 — FLAG_PENNANT (impulse + consolidation + breakout)."""
    assert 'setup_type = "FLAG_PENNANT"' in ea_src
    assert "DetectFlagPennantEvent" in ea_src
    for key in (
        ("setup", "flag_pennant_enabled"),
        ("atom", "flag_pennant_impulse_lookback_bars"),
        ("atom", "flag_pennant_impulse_min_atr"),
        ("atom", "flag_pennant_consolidation_bars"),
        ("atom", "flag_pennant_consolidation_max_atr"),
        ("atom", "flag_pennant_adx_min"),
        ("geometry", "flag_pennant_lot_factor"),
        ("geometry", "flag_pennant_sl_atr_mult"),
        ("geometry", "flag_pennant_tp1_atr_mult"),
        ("geometry", "flag_pennant_tp2_atr_mult"),
        ("timing", "flag_pennant_cooldown_seconds"),
    ):
        section, name = key
        assert section in cfg
        assert name in cfg[section]
    assert defaults["setup"]["flag_pennant_enabled"] == 0
    assert "flag_pennant_factor" in ea_src
    # SKIP codes registered (Filter_* helpers construct codes at runtime in v2.7.43)
    for gate in ("flag_pennant_adx_below_min", "flag_pennant_cooldown"):
        assert gate in gate_legend, f"gate code {gate} not in gate_legend.json"
    assert 'Filter_AdxFloor("FLAG_PENNANT"' in ea_src, "FLAG_PENNANT not migrated to Filter_AdxFloor helper"
    assert 'Filter_Cooldown("FLAG_PENNANT"' in ea_src, "FLAG_PENNANT not migrated to Filter_Cooldown helper"


def test_trendline_bounce_and_sr_flip_setups_wired(ea_src, cfg, defaults, gate_legend):
    """v2.7.42 C-extended Tier 3 FINAL — TRENDLINE_BOUNCE + SR_FLIP."""
    for sym in ("DetectTrendlineBounceEvent", "DetectSrFlipEvent"):
        assert sym in ea_src, f"{sym} missing"
    assert 'setup_type = "TRENDLINE_BOUNCE"' in ea_src
    assert 'setup_type = "SR_FLIP"' in ea_src
    for key in (
        ("setup", "trendline_bounce_enabled"),
        ("atom", "trendline_touch_tolerance_atr"),
        ("atom", "trendline_adx_min"),
        ("geometry", "trendline_bounce_lot_factor"),
        ("geometry", "trendline_bounce_sl_atr_mult"),
        ("geometry", "trendline_bounce_tp1_atr_mult"),
        ("geometry", "trendline_bounce_tp2_atr_mult"),
        ("timing", "trendline_bounce_cooldown_seconds"),
        ("setup", "sr_flip_enabled"),
        ("atom", "sr_flip_tolerance_atr"),
        ("atom", "sr_flip_adx_min"),
        ("geometry", "sr_flip_lot_factor"),
        ("geometry", "sr_flip_sl_atr_mult"),
        ("geometry", "sr_flip_tp1_atr_mult"),
        ("geometry", "sr_flip_tp2_atr_mult"),
        ("timing", "sr_flip_cooldown_seconds"),
    ):
        section, name = key
        assert section in cfg
        assert name in cfg[section]
    assert defaults["setup"]["trendline_bounce_enabled"] == 0
    assert defaults["setup"]["sr_flip_enabled"] == 0
    assert "trendline_bounce_factor" in ea_src
    assert "sr_flip_factor" in ea_src
    # SKIP codes registered (Filter_* helpers construct codes at runtime in v2.7.43)
    for gate in ("trendline_bounce_adx_below_min", "trendline_bounce_cooldown",
                 "sr_flip_adx_below_min", "sr_flip_cooldown"):
        assert gate in gate_legend, f"gate code {gate} not in gate_legend.json"
    assert 'Filter_AdxFloor("TRENDLINE_BOUNCE"' in ea_src, "TRENDLINE_BOUNCE not migrated to Filter_AdxFloor helper"
    assert 'Filter_Cooldown("TRENDLINE_BOUNCE"' in ea_src, "TRENDLINE_BOUNCE not migrated to Filter_Cooldown helper"
    assert 'Filter_AdxFloor("SR_FLIP"' in ea_src, "SR_FLIP not migrated to Filter_AdxFloor helper"
    assert 'Filter_Cooldown("SR_FLIP"' in ea_src, "SR_FLIP not migrated to Filter_Cooldown helper"


# ──────────────────────────────────────────────────────────────────────────────
# v2.7.44 — RegimeState struct (FORGE_REGIME_TAXONOMY.md §3 + §5 Phase 2)
# ──────────────────────────────────────────────────────────────────────────────

def test_regime_state_struct_declared(ea_src):
    """v2.7.44 Phase 2: RegimeState struct + g_regime global exist (FORGE_REGIME_TAXONOMY.md §3)."""
    assert "struct RegimeState" in ea_src, \
        "RegimeState struct missing — Phase 2 of FORGE_REGIME_TAXONOMY.md"
    assert "RegimeState g_regime" in ea_src, \
        "g_regime global instance missing"
    # 16 fields per §3 + §11.3 — verify each is declared inside the struct
    for field in (
        "htf_label",  "htf_confidence",  "htf_h1_strong",
        "intraday_label", "intraday_confidence", "intraday_counter_htf",
        "daily_slope_atr", "daily_bear_bias", "daily_bull_bias", "daily_flip_now",
        "high_vol", "m5_adx",
        "session", "killzone", "minutes_into_kz", "news_active",
    ):
        # Field declaration always appears as " <field>;" inside the struct (no g_regime. prefix yet)
        assert f"{field};" in ea_src, f"RegimeState.{field} field declaration missing"


def test_regime_update_function_called(ea_src):
    """v2.7.44 Phase 2: RegimeUpdate() is defined and invoked from CheckNativeScalperSetups."""
    assert "void RegimeUpdate(" in ea_src, \
        "RegimeUpdate() function definition missing"
    # The call site lives inside CheckNativeScalperSetups, after the regime classification block
    assert "RegimeUpdate(m5_adx, m5_rsi," in ea_src, \
        "RegimeUpdate call site missing — Phase 2 needs the populator wired into the per-tick eval loop"
    # Phase 2 is ADDITIVE: legacy globals must STILL be assigned (no Phase 3 removal yet)
    assert 'g_regime_label = "RANGE"' in ea_src, \
        "Phase 2 must keep g_regime_label assignment intact (additive only — Phase 3 migrates callers)"
    assert "g_daily_bear_bias" in ea_src and "g_daily_bull_bias" in ea_src, \
        "Phase 2 must keep g_daily_*_bias globals (additive only — Phase 4 removes them)"


# ──────────────────────────────────────────────────────────────────────────────
# v2.7.45 — minutes_into_kz column (FORGE_REGIME_TAXONOMY.md §11.6)
# ──────────────────────────────────────────────────────────────────────────────

def test_minutes_into_kz_logged(ea_src):
    """v2.7.45 §11.6: minutes_into_kz reaches the SIGNALS journal.

    EA-side requirements:
      - ALTER TABLE adds the column to the journal SIGNALS table
      - JournalRecordSignal INSERT includes the column
      - Value is computed fresh from g_scalper_killzone_start_time (RegimeUpdate
        may not have run for early-gate SKIP paths like spread/session_off)
    """
    assert "ALTER TABLE SIGNALS ADD COLUMN minutes_into_kz INTEGER" in ea_src, \
        "SIGNALS schema missing minutes_into_kz ALTER (§11.6)"
    assert "minutes_into_kz" in ea_src.split('INSERT INTO SIGNALS')[1].split('VALUES')[0], \
        "INSERT INTO SIGNALS column list missing minutes_into_kz"
    assert "minutes_into_kz_now = (g_scalper_killzone_start_time > 0)" in ea_src, \
        "minutes_into_kz must be computed fresh from g_scalper_killzone_start_time, not read from g_regime"


def test_minutes_into_kz_scribe_mirror():
    """v2.7.45 §11.6: scribe.py mirrors minutes_into_kz from EA journal to forge_signals."""
    from pathlib import Path as _Path
    scribe = (_Path(__file__).parent.parent.parent / "python" / "scribe.py").read_text()
    # CREATE TABLE has the column
    assert "minutes_into_kz INTEGER DEFAULT 0" in scribe, \
        "scribe.py CREATE TABLE forge_signals missing minutes_into_kz"
    # ALTER TABLE migration for existing DBs
    assert 'ALTER TABLE forge_signals ADD COLUMN minutes_into_kz INTEGER' in scribe, \
        "scribe.py missing ALTER TABLE migration for minutes_into_kz"
    # SELECT propagation from source SIGNALS
    assert 'has_min_into_kz = "minutes_into_kz" in src_cols' in scribe, \
        "scribe.py missing source-column detection for minutes_into_kz"
    # INSERT INTO forge_signals column list
    assert "killzone, minutes_into_kz" in scribe, \
        "scribe.py forge_signals INSERT missing minutes_into_kz alongside killzone"


# ──────────────────────────────────────────────────────────────────────────────
# v2.7.46 — per-killzone trade cap (FORGE_REGIME_TAXONOMY.md §11.5)
# ──────────────────────────────────────────────────────────────────────────────

def test_killzone_trade_cap_wired_end_to_end(ea_src, cfg, gate_legend, sync_src, defaults):
    """v2.7.46 §11.5: per-killzone trade cap is fully wired (config + EA + gate + sync)."""
    # 1. ScalperConfig field + default + JsonHasKey parse
    assert "killzones_max_trades_per_kz" in ea_src, \
        "ScalperConfig field killzones_max_trades_per_kz missing"
    assert 'JsonHasKey(content, "killzones_max_trades_per_kz")' in ea_src, \
        "EA JSON loader missing killzones_max_trades_per_kz read"
    # 2. ScalperKillzoneCapOK helper + gate wiring
    assert "bool ScalperKillzoneCapOK()" in ea_src, \
        "ScalperKillzoneCapOK helper function missing"
    assert "!ScalperKillzoneCapOK()" in ea_src, \
        "ScalperKillzoneCapOK not called in dispatch path"
    assert 'JournalRecordSignal("SKIP","killzone_trade_cap"' in ea_src, \
        "EA must emit SKIP killzone_trade_cap when cap hit"
    # 3. Counter increment on TAKEN entry (alongside session_trades++)
    assert "g_scalper_killzone_trades++" in ea_src, \
        "g_scalper_killzone_trades must be incremented when a TAKEN entry fires"
    # 4. Gate code in gate_legend.json
    assert "killzone_trade_cap" in gate_legend, \
        "gate_legend.json missing killzone_trade_cap entry"
    assert gate_legend["killzone_trade_cap"].get("category") == "Session / Time", \
        "killzone_trade_cap should be categorized under Session / Time"
    # 5. Config defaults + sync mapping (active config + defaults JSON)
    assert cfg["session_filter"]["killzones_max_trades_per_kz"] == 0, \
        "killzones_max_trades_per_kz should default to 0 (disabled — operator opts in)"
    assert defaults["session_filter"]["killzones_max_trades_per_kz"] == 0, \
        "defaults.json killzones_max_trades_per_kz should be 0"
    assert "FORGE_GATE_KILLZONE_MAX_TRADES" in sync_src, \
        "sync_scalper_config_from_env.py missing FORGE_GATE_KILLZONE_MAX_TRADES mapping"


# ──────────────────────────────────────────────────────────────────────────────
# v2.7.51 — §11.4 killzone-aware composite refinements
# ──────────────────────────────────────────────────────────────────────────────

def test_bull_day_dip_buy_prime_amplifier_wired(ea_src, cfg, defaults, sync_src):
    """v2.7.51 §11.4: BULL_DAY_DIP_BUY prime-window amplifier (NY_OPEN_KZ ∪ LONDON_CLOSE_KZ)."""
    # ScalperConfig field + default + JsonHasKey
    assert "bull_day_dip_buy_prime_amplifier" in ea_src
    assert 'JsonHasKey(content, "bull_day_dip_buy_prime_amplifier")' in ea_src
    # Default no-change (1.0)
    assert cfg["composites"]["bull_day_dip_buy_prime_amplifier"] == 1.0
    assert defaults["composites"]["bull_day_dip_buy_prime_amplifier"] == 1.0
    # Sync mapping
    assert "FORGE_AMPLIFY_BULL_DAY_DIP_BUY_PRIME_FACTOR" in sync_src
    # Wired into lot factor — multiplied into bull_day_dip_factor when KZ matches
    assert 'g_sc.bull_day_dip_buy_prime_amplifier > 1.0' in ea_src
    assert 'g_regime.killzone == "NY_OPEN_KZ"' in ea_src
    assert 'g_regime.killzone == "LONDON_CLOSE_KZ"' in ea_src
    assert "bull_day_dip_factor *= g_sc.bull_day_dip_buy_prime_amplifier" in ea_src


def test_intraday_reversal_require_prime_kz_wired(ea_src, cfg, defaults, sync_src):
    """v2.7.51 §11.4: INTRADAY_REVERSAL_SELL amplifier only fires in prime KZ when knob is on."""
    assert "intraday_reversal_require_prime_kz" in ea_src
    assert 'JsonHasKey(content, "intraday_reversal_require_prime_kz")' in ea_src
    assert cfg["composites"]["intraday_reversal_require_prime_kz"] == 0
    assert defaults["composites"]["intraday_reversal_require_prime_kz"] == 0
    assert "FORGE_GATE_INTRADAY_REVERSAL_REQUIRE_PRIME_KZ" in sync_src
    # Gate sits at the END of IsIntradayReversalSellActive — pre-existing returns must still be reachable
    assert "if(g_sc.intraday_reversal_require_prime_kz) {" in ea_src
    # When the gate fires, the function returns false (amplifier doesn't apply)


def test_dump_judas_window_block_wired(ea_src, cfg, defaults, sync_src, gate_legend):
    """v2.7.51 §11.4: MOMENTUM_DUMP SELL blocked in first 60 min of LONDON_OPEN_KZ when knob is on."""
    assert "dump_judas_window_block" in ea_src
    assert 'JsonHasKey(content, "dump_judas_window_block")' in ea_src
    assert cfg["composites"]["dump_judas_window_block"] == 0
    assert defaults["composites"]["dump_judas_window_block"] == 0
    assert "FORGE_GATE_DUMP_JUDAS_WINDOW_BLOCK" in sync_src
    # Dispatch-site check: knob + KZ + minutes
    assert 'g_sc.dump_judas_window_block' in ea_src
    assert 'g_regime.killzone == "LONDON_OPEN_KZ"' in ea_src
    assert 'g_regime.minutes_into_kz < 60' in ea_src
    # SKIP code emitted + registered in gate_legend
    assert 'JournalRecordSignal("SKIP","dump_judas_window","MOMENTUM_DUMP","SELL"' in ea_src
    assert "dump_judas_window" in gate_legend
    assert gate_legend["dump_judas_window"]["category"] == "Session / Time"


def test_kz_warmup_gate_wired(ea_src, cfg, defaults, sync_src, gate_legend):
    """v2.7.52: KZ warmup gate (FORGE_GATE_KZ_WARMUP_MIN) blocks entries in first N min of any KZ.
    Implements the arongroups stop-hunt advice — first 5-15 min of session opens have wide spreads
    and frequent stop hunts; better to wait for opening volatility to settle."""
    # ScalperConfig field + default + JsonHasKey
    assert "kz_warmup_min" in ea_src
    assert 'JsonHasKey(content, "kz_warmup_min")' in ea_src
    # Default OFF (0 = disabled)
    assert cfg["session_filter"]["kz_warmup_min"] == 0
    assert defaults["session_filter"]["kz_warmup_min"] == 0
    # Sync mapping
    assert "FORGE_GATE_KZ_WARMUP_MIN" in sync_src
    # Wired into the early-gate dispatch path: knob > 0 AND KZ active AND minutes_into_kz < threshold
    assert "g_sc.kz_warmup_min > 0" in ea_src
    assert "g_regime.minutes_into_kz < g_sc.kz_warmup_min" in ea_src
    # SKIP code emitted + registered in gate_legend
    assert 'JournalRecordSignal("SKIP","kz_warmup"' in ea_src
    assert "kz_warmup" in gate_legend
    assert gate_legend["kz_warmup"]["category"] == "Session / Time"


# ──────────────────────────────────────────────────────────────────────────────
# v2.7.47 — RegimeState surfacing to SIGNALS (FORGE_REGIME_TAXONOMY.md §3)
# ──────────────────────────────────────────────────────────────────────────────

def test_regime_state_logged_to_signals(ea_src):
    """v2.7.47: 3 NEW computed RegimeState fields land in SIGNALS for retrospective analysis."""
    # EA-side ALTER TABLE
    assert "ALTER TABLE SIGNALS ADD COLUMN htf_h1_strong INTEGER" in ea_src, \
        "SIGNALS schema missing htf_h1_strong column"
    assert "ALTER TABLE SIGNALS ADD COLUMN intraday_label TEXT" in ea_src, \
        "SIGNALS schema missing intraday_label column"
    assert "ALTER TABLE SIGNALS ADD COLUMN intraday_counter_htf INTEGER" in ea_src, \
        "SIGNALS schema missing intraday_counter_htf column"
    # INSERT column list
    insert_block = ea_src.split('INSERT INTO SIGNALS')[1].split('VALUES')[0]
    for col in ("htf_h1_strong", "intraday_label", "intraday_counter_htf"):
        assert col in insert_block, f"INSERT INTO SIGNALS column list missing {col}"
    # Values are sourced from g_regime struct (Phase 2 wiring proves itself useful)
    assert "g_regime.htf_h1_strong" in ea_src, "INSERT must source htf_h1_strong from g_regime"
    assert "g_regime.intraday_label" in ea_src, "INSERT must source intraday_label from g_regime"
    assert "g_regime.intraday_counter_htf" in ea_src, "INSERT must source intraday_counter_htf from g_regime"


def test_regime_state_scribe_mirror():
    """v2.7.47: scribe.py mirrors the 3 RegimeState SIGNALS columns to forge_signals."""
    from pathlib import Path as _Path
    scribe = (_Path(__file__).parent.parent.parent / "python" / "scribe.py").read_text()
    # CREATE TABLE has the 3 columns
    for col in ("htf_h1_strong", "intraday_label", "intraday_counter_htf"):
        assert col in scribe, f"scribe.py missing {col}"
    # ALTER TABLE migrations
    assert "ADD COLUMN htf_h1_strong INTEGER" in scribe, "scribe.py missing ALTER for htf_h1_strong"
    assert "ADD COLUMN intraday_label TEXT" in scribe, "scribe.py missing ALTER for intraday_label"
    assert "ADD COLUMN intraday_counter_htf INTEGER" in scribe, "scribe.py missing ALTER for intraday_counter_htf"
    # All-or-nothing detection
    assert 'has_regime_v47' in scribe, "scribe.py missing has_regime_v47 source-column detector"
    # INSERT column list
    assert "htf_h1_strong, intraday_label, intraday_counter_htf" in scribe, \
        "scribe.py forge_signals INSERT missing the v2.7.47 trio"


def test_athena_api_returns_killzone_minutes_in_taken_entries():
    """v2.7.47: /api/backtest/run/:id TAKEN SELECT exposes killzone + minutes_into_kz."""
    from pathlib import Path as _Path
    api = (_Path(__file__).parent.parent.parent / "python" / "athena_api.py").read_text()
    # The TAKEN-entries SELECT must include both columns
    taken_block_start = api.find("# TAKEN entries enriched")
    assert taken_block_start >= 0, "athena_api TAKEN entries SELECT block not found"
    taken_block = api[taken_block_start:taken_block_start + 800]
    assert "killzone" in taken_block, "TAKEN entries SELECT missing killzone column"
    assert "minutes_into_kz" in taken_block, "TAKEN entries SELECT missing minutes_into_kz column"


# ──────────────────────────────────────────────────────────────────────────────
# v2.7.43+ Gate-legend reachability — catches stale legend entries in CI
# rather than waiting for /forge-ea-review. See FORGE_LAYERED_GATE_LIFECYCLE.md §6.
# ──────────────────────────────────────────────────────────────────────────────

def test_gate_legend_entries_reachable_in_EA(ea_src, gate_legend):
    """Every gate_legend.json entry must be reachable from EA source. Three
    classes of reachability are accepted:

      1. **Direct literal**     `JournalRecordSignal("SKIP","<code>",...)` —
         the gate code is a string argument to the journal call directly.

      2. **Indirect literal**   `string _reason = "<code>"; ... JournalRecordSignal(...,_reason,...)` —
         the gate code appears as a quoted literal somewhere in EA source but
         not necessarily as a direct JournalRecordSignal arg. Common for dynamic
         classifier gates like MACD quadrants (`entry_quality_macd_q0_bull_rising`
         at ea/FORGE.mq5:8546) and RSI conditional codes
         (`entry_quality_rsi_sell_adx_floor` at ea/FORGE.mq5:8835).

      3. **Runtime-constructed** v2.7.43+ Filter_* helper call sites:
            Filter_AdxFloor("<NAME>","<lower>",...)        → "<lower>_adx_below_min"
            Filter_Cooldown("<NAME>","<lower>",...)        → "<lower>_cooldown"
            Filter_M15TrendAligned("<NAME>","<lower>",...) → "<lower>_m15_misalign"

      4. **Wildcard match** — entries like `warmup_*` cover any prefixed code.

    Catches stale entries early: if all emission paths for a legend key are
    removed but the legend entry isn't cleaned up, this test fails in CI rather
    than surfacing in a quarterly /forge-ea-review.

    Why this matters: codex's 2026-05-13 review flagged 20 legend entries as
    "stale" because its grep-for-literal-Journal-arg approach missed both the
    runtime construction (class 3) and indirect literal (class 2) patterns.
    The /forge-ea-review SKILL.md was updated to enumerate constructed codes;
    this test is the CI-side complement that covers all reachability classes.

    See FORGE_LAYERED_GATE_LIFECYCLE.md §6 for the underlying lifecycle.
    """
    import re

    # 3. Runtime-constructed codes from v2.7.43+ Filter_* helper call sites
    filter_adx  = re.findall(r'Filter_AdxFloor\(\s*"[A-Z_]+"\s*,\s*"([a-z_][a-z0-9_]+)"', ea_src)
    filter_cool = re.findall(r'Filter_Cooldown\(\s*"[A-Z_]+"\s*,\s*"([a-z_][a-z0-9_]+)"', ea_src)
    filter_m15  = re.findall(r'Filter_M15TrendAligned\(\s*"[A-Z_]+"\s*,\s*"([a-z_][a-z0-9_]+)"', ea_src)
    constructed = (
        {f"{s}_adx_below_min" for s in filter_adx}
        | {f"{s}_cooldown"      for s in filter_cool}
        | {f"{s}_m15_misalign"  for s in filter_m15}
    )

    # 4. Wildcard patterns from legend itself
    legend_keys = {k for k in gate_legend if not k.startswith("_")}
    patterns = list(gate_legend.get("_patterns", {}).keys())

    def matches_pattern(code: str, pats: list) -> bool:
        return any(p.endswith("_*") and code.startswith(p[:-1]) for p in pats)

    # For each legend key, classify reachability:
    #   - constructed (class 3) — already in `constructed` set
    #   - wildcard (class 4)    — matches_pattern() returns True
    #   - literal (class 1+2)   — `"<key>"` appears anywhere in EA source
    stale = []
    for key in legend_keys:
        if key in constructed:
            continue
        if matches_pattern(key, patterns):
            continue
        # Check for literal occurrence (handles both direct JournalRecordSignal
        # args AND indirect assignments like `_qreason = "entry_quality_..."`)
        if f'"{key}"' in ea_src:
            continue
        stale.append(key)

    stale = sorted(stale)
    assert not stale, (
        f"gate_legend.json has {len(stale)} unreachable entries (no literal "
        f"in EA source AND no Filter_* call site that constructs them AND no "
        f"wildcard match):\n  "
        + "\n  ".join(stale)
        + "\n\nEither restore the EA emission / Filter_* call site / wildcard "
        "pattern, or remove the legend entry. See FORGE_LAYERED_GATE_LIFECYCLE.md."
    )


def test_filter_helper_call_sites_have_legend_coverage(ea_src, gate_legend):
    """Reverse direction of the reachability check: every Filter_* call site
    must produce a code that has a legend entry (or matches a wildcard).

    Catches the other drift: a new setup is added with Filter_AdxFloor("NEW",...)
    but the operator forgets to add `new_adx_below_min` to gate_legend.json.
    Without this test the gate emits at runtime but monitoring tools show a raw
    undecoded code.
    """
    import re

    filter_adx  = re.findall(r'Filter_AdxFloor\(\s*"[A-Z_]+"\s*,\s*"([a-z_][a-z0-9_]+)"', ea_src)
    filter_cool = re.findall(r'Filter_Cooldown\(\s*"[A-Z_]+"\s*,\s*"([a-z_][a-z0-9_]+)"', ea_src)
    filter_m15  = re.findall(r'Filter_M15TrendAligned\(\s*"[A-Z_]+"\s*,\s*"([a-z_][a-z0-9_]+)"', ea_src)

    constructed = (
        {f"{s}_adx_below_min" for s in filter_adx}
        | {f"{s}_cooldown"      for s in filter_cool}
        | {f"{s}_m15_misalign"  for s in filter_m15}
    )

    legend_keys = {k for k in gate_legend if not k.startswith("_")}
    patterns = list(gate_legend.get("_patterns", {}).keys())

    def matches_pattern(code: str, pats: list) -> bool:
        return any(p.endswith("_*") and code.startswith(p[:-1]) for p in pats)

    uncovered = sorted(
        c for c in constructed
        if c not in legend_keys and not matches_pattern(c, patterns)
    )

    assert not uncovered, (
        f"{len(uncovered)} Filter_* call sites produce codes with no legend entry "
        f"(monitoring tools will show raw undecoded codes):\n  "
        + "\n  ".join(uncovered)
        + "\n\nAdd these to config/gate_legend.json with category + explanation."
    )
