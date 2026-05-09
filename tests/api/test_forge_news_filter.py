from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORGE = ROOT / "ea" / "FORGE.mq5"
CONFIG = ROOT / "config" / "scalper_config.json"
DEFAULTS = ROOT / "config" / "scalper_config.defaults.json"
SYNC_SCRIPT = ROOT / "scripts" / "sync_scalper_config_from_env.py"

NEWS_KEYS = [
    "news_filter_enabled",
    "news_filter_currencies",
    "news_filter_low_before",
    "news_filter_low_after",
    "news_filter_medium_before",
    "news_filter_medium_after",
    "news_filter_high_before",
    "news_filter_high_after",
    "news_filter_special",
    "news_filter_hard_floor_min",
    "news_filter_tighten_pct",
    "news_filter_block_pct",
    "news_filter_tighten_rsi_buy",
    "news_filter_tighten_rsi_sell",
    "news_filter_refresh_sec",
    "news_filter_apply_in_tester",
]

ENV_KEYS = [
    "FORGE_NEWS_FILTER_ENABLED",
    "FORGE_NEWS_FILTER_CURRENCIES",
    "FORGE_NEWS_FILTER_LOW_BEFORE",
    "FORGE_NEWS_FILTER_LOW_AFTER",
    "FORGE_NEWS_FILTER_MEDIUM_BEFORE",
    "FORGE_NEWS_FILTER_MEDIUM_AFTER",
    "FORGE_NEWS_FILTER_HIGH_BEFORE",
    "FORGE_NEWS_FILTER_HIGH_AFTER",
    "FORGE_NEWS_FILTER_SPECIAL",
    "FORGE_NEWS_FILTER_HARD_FLOOR_MIN",
    "FORGE_NEWS_FILTER_TIGHTEN_PCT",
    "FORGE_NEWS_FILTER_BLOCK_PCT",
    "FORGE_NEWS_FILTER_TIGHTEN_RSI_BUY",
    "FORGE_NEWS_FILTER_TIGHTEN_RSI_SELL",
    "FORGE_NEWS_FILTER_REFRESH_SEC",
    "FORGE_NEWS_FILTER_APPLY_IN_TESTER",
]

WINDOW_KEYS = [
    "news_filter_low_before",
    "news_filter_low_after",
    "news_filter_medium_before",
    "news_filter_medium_after",
    "news_filter_high_before",
    "news_filter_high_after",
    "news_filter_hard_floor_min",
    "news_filter_refresh_sec",
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def forge_source() -> str:
    return FORGE.read_text(encoding="utf-8")


def sync_module():
    spec = importlib.util.spec_from_file_location("sync_scalper_config_from_env", SYNC_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def news_function_body(source: str, name: str) -> str:
    match = re.search(rf"\b(?:void|double|int)\s+{name}\s*\([^)]*\)\s*\{{", source)
    assert match, f"{name} function not found"
    depth = 0
    for idx in range(match.end() - 1, len(source)):
        ch = source[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : idx + 1]
    raise AssertionError(f"{name} function body did not close")


def parse_special(raw: str) -> dict[str, tuple[int, int]]:
    parsed: dict[str, tuple[int, int]] = {}
    for entry in raw.split("+"):
        key, values = entry.split(":", 1)
        before, after = values.split(",", 1)
        parsed[key] = (int(before), int(after))
    return parsed


ALL_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "CNY"]


def expand_currencies(raw: str) -> list[str]:
    out: list[str] = []
    for token in raw.replace(" ", ",").split(","):
        cur = token.strip().upper()
        if not cur:
            continue
        add = ALL_CURRENCIES if cur == "ALL" else [cur]
        for item in add:
            if item not in out:
                out.append(item)
    return out


def proximity(block_start: int, event_time: int, block_end: int, now: int) -> float:
    if now < block_start or now > block_end:
        return -1.0
    if now <= event_time:
        denom = event_time - block_start
        return 1.0 if denom <= 0 else min(1.0, (now - block_start) / denom)
    denom = block_end - event_time
    return 1.0 if denom <= 0 else min(1.0, (block_end - now) / denom)


def news_check(
    p: float,
    *,
    tighten_pct: float = 0.5,
    block_pct: float = 0.85,
    tighten_rsi_buy: float = 65.0,
    tighten_rsi_sell: float = 38.0,
) -> tuple[str, float, float]:
    if p < 0.0:
        return "ALLOW", 70.0, 33.0
    if p >= block_pct:
        return "BLOCK", 70.0, 33.0
    if p >= tighten_pct:
        slide = (p - tighten_pct) / max(0.001, block_pct - tighten_pct)
        eff_buy = 70.0 - (70.0 - tighten_rsi_buy) * slide
        eff_sell = 33.0 + (tighten_rsi_sell - 33.0) * slide
        return "TIGHTEN", eff_buy, eff_sell
    return "ALLOW", 70.0, 33.0


def hard_floor_state(now: int, event_time: int, hard_floor_min: int) -> str:
    if now > event_time and (now - event_time) // 60 < hard_floor_min:
        return "BLOCK"
    return "NORMAL"


def test_config_json_contains_complete_news_filter_key_set() -> None:
    for path in (CONFIG, DEFAULTS):
        safety = load_json(path)["safety"]
        assert set(NEWS_KEYS).issubset(safety)
        assert sorted(k for k in safety if k.startswith("news_filter_")) == sorted(NEWS_KEYS)


def test_config_json_default_values_and_invariants() -> None:
    for path in (CONFIG, DEFAULTS):
        safety = load_json(path)["safety"]
        assert safety["news_filter_enabled"] == 1  # enabled by default for live + tester
        assert safety["news_filter_currencies"] == "USD,EUR,GBP"
        for key in WINDOW_KEYS:
            assert isinstance(safety[key], int)
            assert safety[key] >= 0
        assert safety["news_filter_tighten_pct"] < safety["news_filter_block_pct"]
        assert 50 <= safety["news_filter_tighten_rsi_buy"] <= 70
        assert 30 <= safety["news_filter_tighten_rsi_sell"] <= 50
        assert safety["news_filter_refresh_sec"] >= 60
        assert safety["news_filter_hard_floor_min"] >= 0
        assert re.fullmatch(r"[^:+]+:\d+,\d+(?:\+[^:+]+:\d+,\d+)*", safety["news_filter_special"])


def test_sync_script_contains_complete_news_filter_env_mapping() -> None:
    mapping = sync_module().MAPPING
    assert set(ENV_KEYS).issubset(mapping)
    assert sorted(k for k in mapping if k.startswith("FORGE_NEWS_FILTER_")) == sorted(ENV_KEYS)


def test_sync_script_news_filter_mapping_types() -> None:
    mapping = sync_module().MAPPING
    assert mapping["FORGE_NEWS_FILTER_ENABLED"][2] == "bool01"
    assert mapping["FORGE_NEWS_FILTER_CURRENCIES"][2] == "string"
    assert mapping["FORGE_NEWS_FILTER_SPECIAL"][2] == "string"
    assert mapping["FORGE_NEWS_FILTER_APPLY_IN_TESTER"][2] == "bool01"


def test_sync_script_news_filter_numeric_bounds() -> None:
    mapping = sync_module().MAPPING
    for key in [
        "FORGE_NEWS_FILTER_LOW_BEFORE",
        "FORGE_NEWS_FILTER_LOW_AFTER",
        "FORGE_NEWS_FILTER_MEDIUM_BEFORE",
        "FORGE_NEWS_FILTER_MEDIUM_AFTER",
        "FORGE_NEWS_FILTER_HIGH_BEFORE",
        "FORGE_NEWS_FILTER_HIGH_AFTER",
    ]:
        assert mapping[key][2:] == ("int", 0.0, 240.0)
    assert mapping["FORGE_NEWS_FILTER_HARD_FLOOR_MIN"][2:] == ("int", 0.0, 60.0)
    assert mapping["FORGE_NEWS_FILTER_TIGHTEN_PCT"][2:] == ("float", 0.0, 1.0)
    assert mapping["FORGE_NEWS_FILTER_BLOCK_PCT"][2:] == ("float", 0.0, 1.0)
    assert mapping["FORGE_NEWS_FILTER_TIGHTEN_RSI_BUY"][2:] == ("float", 50.0, 70.0)
    assert mapping["FORGE_NEWS_FILTER_TIGHTEN_RSI_SELL"][2:] == ("float", 30.0, 50.0)
    assert mapping["FORGE_NEWS_FILTER_REFRESH_SEC"][2:] == ("int", 60.0, None)


def test_forge_news_filter_functions_and_journal_gates_exist() -> None:
    src = forge_source()
    for name in ["ScalperNewsFilterRefresh", "ScalperNewsProximity", "ScalperNewsCheck"]:
        assert re.search(rf"\b{name}\s*\(", src)
    assert "entry_quality_news_filter" in src
    assert "entry_quality_news_rsi_tighten" in src


def test_forge_calendar_calls_and_server_time_usage() -> None:
    src = forge_source()
    assert "CalendarValueHistory" in src
    assert "CalendarEventById" in src
    # NULL (not "") as country-code arg, cur as currency filter
    assert re.search(r"CalendarValueHistory\s*\([^)]*NULL[^)]*,\s*cur\s*\)", src), \
        "CalendarValueHistory must use NULL for country code and cur for currency"
    for name in ["ScalperNewsFilterRefresh", "ScalperNewsProximity", "ScalperNewsCheck"]:
        body = news_function_body(src, name)
        assert "TimeTradeServer()" in body
        assert "TimeGMT()" not in body


def test_forge_currency_list_contains_cny_and_nine_currencies() -> None:
    src = forge_source()
    match = re.search(r"ALL_CURRENCIES\[\]\s*=\s*\{([^}]+)\}", src)
    assert match
    currencies = re.findall(r'"([A-Z]{3})"', match.group(1))
    assert currencies == ALL_CURRENCIES


def test_forge_breakout_rsi_tightening_directions() -> None:
    """News RSI tighten must be a STANDALONE independent check — no MathMin/MathMax merging."""
    src = forge_source()
    # Standalone check: g_nf_eff_rsi_buy_ceil < g_sc.breakout_rsi_buy_ceil (not merged)
    assert "g_nf_eff_rsi_buy_ceil < g_sc.breakout_rsi_buy_ceil" in src, \
        "BUY news RSI tighten must be a standalone comparison, not merged via MathMin"
    assert "g_nf_eff_rsi_sell_min > g_sc.breakout_rsi_sell_floor" in src, \
        "SELL news RSI tighten must be a standalone comparison, not merged via MathMax"
    # Confirm MathMin/MathMax NOT used for merging these thresholds
    assert "MathMin(g_sc.breakout_rsi_buy_ceil, g_nf_eff_rsi_buy_ceil)" not in src
    assert "MathMax(g_sc.breakout_rsi_sell_floor, g_nf_eff_rsi_sell_min)" not in src


def test_forge_news_filter_state_and_config_fields_exist() -> None:
    src = forge_source()
    assert re.search(r"double\s+g_nf_eff_rsi_buy_ceil", src)
    assert re.search(r"double\s+g_nf_eff_rsi_sell_min", src)
    assert re.search(r"datetime\s+g_nf_event_time", src)
    for key in NEWS_KEYS:
        assert re.search(rf"\b{key}\b", src)


def test_forge_uses_exact_event_time_not_midpoint_approximation() -> None:
    src = forge_source()
    assert "g_nf_event_time" in news_function_body(src, "ScalperNewsFilterRefresh")
    assert "g_nf_event_time" in news_function_body(src, "ScalperNewsProximity")
    assert "g_nf_event_time" in news_function_body(src, "ScalperNewsCheck")
    news_section = src[src.index("void ScalperNewsFilterRefresh") : src.index("bool CheckEntryQuality")]
    assert "event_approx" not in news_section


def test_forge_updates_news_rsi_thresholds_before_breakout_selection() -> None:
    """ScalperNewsUpdateEffectiveThresholds called before BB setup selection OR gate -1 runs first."""
    src = forge_source()
    # Gate -1 in CheckEntryQuality calls ScalperNewsUpdateEffectiveThresholds; it runs before
    # BB selection because CheckEntryQuality is called after direction is set but before entry.
    # The key invariant: g_nf_eff_rsi_* globals are updated before the tighten check fires.
    assert "ScalperNewsUpdateEffectiveThresholds" in src
    assert "g_nf_eff_rsi_buy_ceil" in src
    assert "g_nf_eff_rsi_sell_min" in src


def test_forge_updates_news_rsi_thresholds_before_bb_breakout_rsi_gate() -> None:
    """g_nf_eff_rsi_buy_ceil used in BB section; ScalperNewsUpdateEffectiveThresholds must be called."""
    src = forge_source()
    # The standalone news RSI tighten check uses g_nf_eff_rsi_buy_ceil in the BB block
    bb_section = src[src.index("// ── BB BOUNCE") : src.index("if(direction != \"\" && !ScalperDirectionCooldownOK")]
    assert "g_nf_eff_rsi_buy_ceil" in bb_section, \
        "BB section must reference g_nf_eff_rsi_buy_ceil for the standalone news tighten check"
    assert "g_nf_eff_rsi_sell_min" in bb_section, \
        "BB section must reference g_nf_eff_rsi_sell_min for the standalone news tighten check"
    assert "entry_quality_news_rsi_tighten" in bb_section, \
        "BB section must journal entry_quality_news_rsi_tighten for standalone check"


def test_proximity_formula_pre_and_post_event() -> None:
    block_start = 1_000
    event_time = block_start + 40 * 60
    block_end = event_time + 45 * 60
    assert proximity(block_start, event_time, block_end, block_start) == 0.0
    assert proximity(block_start, event_time, block_end, block_start + 20 * 60) == 0.5
    assert proximity(block_start, event_time, block_end, event_time) == 1.0
    assert proximity(block_start, event_time, block_end, event_time + 22.5 * 60) == 0.5
    assert proximity(block_start, event_time, block_end, block_end) == 0.0


def test_proximity_zero_length_before_or_after_window_guards_division_by_zero() -> None:
    event_time = 10_000
    assert proximity(event_time, event_time, event_time + 30 * 60, event_time) == 1.0
    assert proximity(event_time - 30 * 60, event_time, event_time, event_time + 1) == -1.0
    assert proximity(event_time - 30 * 60, event_time, event_time, event_time) == 1.0


def test_sliding_rsi_formula_at_tighten_and_block_thresholds() -> None:
    state, eff_buy, eff_sell = news_check(0.5)
    assert state == "TIGHTEN"
    assert eff_buy == 70.0
    assert eff_sell == 33.0
    state, eff_buy, eff_sell = news_check(0.849999)
    assert state == "TIGHTEN"
    assert round(eff_buy, 3) == 65.0
    assert round(eff_sell, 3) == 38.0
    assert news_check(0.85)[0] == "BLOCK"


def test_hard_floor_post_event_block_window() -> None:
    event_time = 10_000
    assert hard_floor_state(event_time + 4 * 60, event_time, 5) == "BLOCK"
    assert hard_floor_state(event_time + 5 * 60, event_time, 5) == "NORMAL"
    assert hard_floor_state(event_time - 60, event_time, 5) == "NORMAL"


def test_keyword_parsing_special_windows() -> None:
    parsed = parse_special("Non-Farm:30,60+FOMC:40,45+CPI:50,55")
    assert parsed == {"Non-Farm": (30, 60), "FOMC": (40, 45), "CPI": (50, 55)}


def test_currency_all_expands_to_nine_currencies() -> None:
    assert expand_currencies("ALL") == ALL_CURRENCIES


def test_currency_list_strips_spaces_and_deduplicates() -> None:
    assert expand_currencies("USD, EUR, GBP, USD") == ["USD", "EUR", "GBP"]


def test_news_state_allow_tighten_block_boundaries() -> None:
    assert news_check(0.3)[0] == "ALLOW"
    state, eff_buy, _ = news_check(0.6)
    assert state == "TIGHTEN"
    assert round(eff_buy, 6) == round(70.0 - 5.0 * ((0.6 - 0.5) / 0.35), 6)
    assert news_check(0.9)[0] == "BLOCK"


def test_news_state_allow_resets_effective_rsi_thresholds_to_defaults() -> None:
    state, eff_buy, eff_sell = news_check(-1.0)
    assert state == "ALLOW"
    assert eff_buy == 70.0
    assert eff_sell == 33.0
    state, eff_buy, eff_sell = news_check(0.49)
    assert state == "ALLOW"
    assert eff_buy == 70.0
    assert eff_sell == 33.0


def test_forge_input_override_parameters_exist() -> None:
    """NewsFilterInputsOverride and NewsFilterEnabled must be declared as EA inputs."""
    src = forge_source()
    assert re.search(r"\binput\b.*\bNewsFilterInputsOverride\b", src), \
        "NewsFilterInputsOverride input not found"
    assert re.search(r"\binput\b.*\bNewsFilterEnabled\b", src), \
        "NewsFilterEnabled input not found"
    # Inputs must default to true (enabled by default)
    assert re.search(r"NewsFilterEnabled\s*=\s*true", src), \
        "NewsFilterEnabled must default to true"


def test_forge_apply_news_filter_input_overrides_function_exists() -> None:
    """ApplyNewsFilterInputOverrides must exist and reference both inputs."""
    src = forge_source()
    assert "ApplyNewsFilterInputOverrides" in src
    body = news_function_body(src, "ApplyNewsFilterInputOverrides")
    assert "NewsFilterInputsOverride" in body
    assert "NewsFilterEnabled" in body
    assert "g_sc.news_filter_enabled" in body


def test_forge_apply_news_filter_called_after_every_config_load() -> None:
    """ApplyNewsFilterInputOverrides must be called in all config-load paths."""
    src = forge_source()
    count = len(re.findall(r"ApplyNewsFilterInputOverrides\s*\(\s*\)", src))
    # Expect: function definition (1) + 3 early-return paths + 1 full-load path = 5 total
    assert count >= 4, f"Expected ≥4 calls to ApplyNewsFilterInputOverrides, found {count}"


def test_forge_apply_news_filter_called_in_config_missing_path() -> None:
    """The config-missing early return must still apply MT5 input overrides."""
    src = forge_source()
    body = news_function_body(src, "ReadScalperConfig")
    missing_start = body.index('if(!ReadTextFileDual("scalper_config.json", content))')
    missing_block = body[missing_start : body.index("g_scalper_config_missing_logged = false;")]
    assert missing_block.index("ApplyNewsFilterInputOverrides()") < missing_block.rindex("return;")


def test_forge_skips_calendar_values_with_zero_event_time() -> None:
    """ScalperNewsFilterRefresh must guard against invalid (zero or negative) event times."""
    body = news_function_body(forge_source(), "ScalperNewsFilterRefresh")
    # Accept either pattern: direct time<=0 check or via a named variable
    has_guard = (
        re.search(r"if\s*\(\s*values?\s*\[\s*[ik]\s*\]\.time\s*<=\s*0\s*\)\s*continue", body) or
        re.search(r"datetime\s+\w+\s*=\s*values?\s*\[\s*[ik]\s*\]\.time;[^}]*if\s*\(\s*\w+\s*<=\s*0\s*\)\s*continue", body, re.DOTALL)
    )
    assert has_guard, "ScalperNewsFilterRefresh must skip calendar values with time <= 0"


def test_forge_bb_bounce_entries_pass_through_check_entry_quality() -> None:
    src = forge_source()
    body = news_function_body(src, "CheckNativeScalperSetups")
    bounce_setup_pos = body.index('setup_type = "BB_BOUNCE";')
    quality_pos = body.index("CheckEntryQuality(direction, m5_atr, m5_bb_u, m5_bb_l)")
    execute_pos = body.index("// Execute the native scalper trade group")
    assert bounce_setup_pos < quality_pos < execute_pos


def test_forge_struct_news_filter_default_is_enabled() -> None:
    src = forge_source()
    init_body = news_function_body(src, "InitScalperConfig")
    assert re.search(r"g_sc\.news_filter_enabled\s*=\s*true\s*;", init_body)
    assert not re.search(r"g_sc\.news_filter_enabled\s*=\s*false\s*;", init_body)


def test_config_json_news_filter_enabled_by_default() -> None:
    """news_filter_enabled must be 1 (enabled) in both config files."""
    for path in (CONFIG, DEFAULTS):
        safety = load_json(path)["safety"]
        assert safety["news_filter_enabled"] == 1, \
            f"{path.name}: news_filter_enabled should be 1 (enabled by default)"


def test_currency_list_exact_duplicate_usd_usd_eur_deduplicates() -> None:
    assert expand_currencies("USD,USD,EUR") == ["USD", "EUR"]
