#!/usr/bin/env python3
"""
setup_tradingview_indicators.py
================================
Adds required indicators to the TradingView XAUUSD chart via MCP.
Idempotent — skips indicators already present.

Required by LENS:
  - Bollinger Bands
  - Moving Average Exponential (length 20)
  - Moving Average Exponential (length 50)
  - Relative Strength Index
  - Moving Average Convergence Divergence (MACD)
  - Directional Movement (ADX)
  - Cumulative Volume Delta (CVD/Volume Delta when available)

Structure (OB/FVG):
  - Order Block Detector [LuxAlgo]
  - Fair Value Gap [LuxAlgo]

Usage:
    python3 scripts/setup_tradingview_indicators.py
    python3 scripts/setup_tradingview_indicators.py --check   # verify only, don't add
"""

import sys, os, time, argparse, logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from mcp_client import MCPSession

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger()

# Indicators LENS needs — (display_name_fragment, tv_add_name)
REQUIRED_INDICATORS = [
    ("Bollinger Bands",                        "Bollinger Bands"),
    ("Relative Strength Index",                "Relative Strength Index"),
    ("Moving Average Convergence Divergence",  "Moving Average Convergence Divergence"),
    ("Directional Movement Index",             "Directional Movement"),
    ("ADX and DI",                             "ADX and DI for v4"),
]

CVD_PROXY_ACCEPTED = {"Volume Footprint", "Session Volume Profile HD"}

# EMA needs special handling (add twice, set lengths)
EMA_LENGTHS = [20, 50]

# Structure indicators (optional but recommended)
STRUCTURE_INDICATORS = [
    ("Order Block Detector",  "Order Block Detector [LuxAlgo]"),
    ("Fair Value Gap",        "Fair Value Gap [LuxAlgo]"),
]

# CVD candidates vary by TradingView build/account availability
CVD_INDICATOR_CANDIDATES = [
    ("Cumulative Volume Delta", "Cumulative Volume Delta"),
    ("Volume Delta", "Volume Delta"),
    ("Volume Delta Candles", "Volume Delta Candles"),
    ("Volume Footprint", "Volume Footprint"),
    ("Session Volume Profile HD", "Session Volume Profile HD"),
]


def get_current_studies(mcp: MCPSession) -> list:
    """Return list of study dicts from the chart."""
    resp = mcp.call("chart_get_state")
    return resp.get("studies", [])


def has_study(studies: list, name_fragment: str) -> bool:
    """Check if a study matching name_fragment exists."""
    return any(name_fragment.lower() in s.get("name", "").lower() for s in studies)


def count_studies(studies: list, name_fragment: str) -> int:
    """Count studies matching name_fragment."""
    return sum(1 for s in studies if name_fragment.lower() in s.get("name", "").lower())


def add_indicator(mcp: MCPSession, tv_name: str, label: str) -> bool:
    """Add an indicator by TradingView name. Returns True on success."""
    resp = mcp.call("chart_manage_indicator", {"action": "add", "indicator": tv_name})
    ok = resp.get("success", False)
    if ok:
        log.info(f"  ✅ Added: {label}")
    else:
        log.warning(f"  ❌ Failed to add: {label} (name: {tv_name})")
    return ok


def set_ema_length(mcp: MCPSession, entity_id: str, length: int) -> bool:
    """Set EMA length via indicator_set_inputs."""
    resp = mcp.call("indicator_set_inputs", {
        "entity_id": entity_id,
        "inputs": f'{{"length":{length}}}',
    })
    ok = resp.get("success", False)
    if ok:
        log.info(f"  ✅ Set EMA length={length} (entity: {entity_id})")
    else:
        log.warning(f"  ❌ Failed to set EMA length={length}")
    return ok


def setup_indicators(mcp: MCPSession, check_only: bool = False):
    """Add all required indicators to the chart."""
    studies = get_current_studies(mcp)
    log.info(f"Chart: {len(studies)} studies currently on chart\n")

    all_ok = True

    # ── Core indicators ────────────────────────────────────────
    log.info("Core indicators (LENS):")
    for name_frag, tv_name in REQUIRED_INDICATORS:
        if has_study(studies, name_frag):
            log.info(f"  ✅ Already present: {name_frag}")
        elif check_only:
            log.warning(f"  ❌ Missing: {name_frag}")
            all_ok = False
        else:
            if not add_indicator(mcp, tv_name, name_frag):
                all_ok = False
            time.sleep(1)

    # ── EMAs (need exactly 2, with lengths 20 and 50) ──────────
    log.info("\nEMA indicators:")
    ema_count = count_studies(studies, "Exponential")
    emas_needed = max(0, 2 - ema_count)

    if ema_count >= 2:
        log.info(f"  ✅ {ema_count} EMAs already present")
    elif check_only:
        log.warning(f"  ❌ Only {ema_count}/2 EMAs present")
        all_ok = False
    else:
        for _ in range(emas_needed):
            add_indicator(mcp, "Moving Average Exponential", "EMA")
            time.sleep(1)

    # Set EMA lengths (find entity IDs from refreshed chart state)
    if not check_only:
        time.sleep(1)
        refreshed = get_current_studies(mcp)
        ema_entities = [s["id"] for s in refreshed
                        if "exponential" in s.get("name", "").lower()]
        for i, length in enumerate(EMA_LENGTHS):
            if i < len(ema_entities):
                set_ema_length(mcp, ema_entities[i], length)
            else:
                log.warning(f"  ❌ No EMA entity for length={length}")
                all_ok = False

    # ── Structure indicators ───────────────────────────────────
    log.info("\nStructure indicators (OB/FVG):")
    for name_frag, tv_name in STRUCTURE_INDICATORS:
        if has_study(studies, name_frag):
            log.info(f"  ✅ Already present: {name_frag}")
        elif check_only:
            log.warning(f"  ⚠️  Missing (optional): {name_frag}")
        else:
            if not add_indicator(mcp, tv_name, name_frag):
                log.info(f"     ℹ️  {name_frag} may need manual add (community indicator)")

    # ── CVD indicator (order-flow proxy) ───────────────────────
    log.info("\nCVD indicator (order-flow proxy):")
    refreshed = get_current_studies(mcp)
    has_cvd = (
        has_study(refreshed, "Cumulative Volume Delta")
        or has_study(refreshed, "Volume Delta")
        or has_study(refreshed, "CVD")
    )
    has_proxy = any(has_study(refreshed, name) for name in CVD_PROXY_ACCEPTED)
    if has_cvd:
        log.info("  ✅ Already present: CVD/Volume Delta")
    elif has_proxy:
        log.info("  ✅ CVD proxy present: Volume Footprint/Session Volume Profile HD")
    elif check_only:
        log.warning("  ❌ Missing: CVD/Volume Delta")
        all_ok = False
    else:
        added = False
        added_proxy = False
        for label, tv_name in CVD_INDICATOR_CANDIDATES:
            if add_indicator(mcp, tv_name, label):
                added = True
                if label in CVD_PROXY_ACCEPTED:
                    added_proxy = True
                break
            time.sleep(1)
        if not added:
            all_ok = False
            log.warning("  ❌ Could not auto-add CVD by known names.")
            log.warning("     Add CVD manually in TradingView and re-run --check.")
        elif added_proxy:
            log.info("  ✅ Added CVD proxy indicator (native CVD unavailable in this catalog).")

    # ── Verify final state ─────────────────────────────────────
    if not check_only:
        time.sleep(2)
        log.info("\nVerifying...")
        resp = mcp.call("data_get_study_values")
        final_studies = resp.get("studies", [])
        log.info(f"  {len(final_studies)} studies returning data:")
        for s in final_studies:
            vals = ", ".join(f"{k}={v}" for k, v in s.get("values", {}).items())
            log.info(f"    {s['name']}: {vals}")

    print()
    if all_ok:
        log.info("✅ All indicators configured.")
    else:
        log.warning("⚠️  Some indicators missing — check above.")
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Setup TradingView indicators for LENS")
    parser.add_argument("--check", action="store_true", help="Verify only, don't add")
    args = parser.parse_args()

    try:
        with MCPSession(timeout=20) as mcp:
            ok = setup_indicators(mcp, check_only=args.check)
            sys.exit(0 if ok else 1)
    except ConnectionError:
        log.error("❌ Could not connect to TradingView MCP.")
        log.error("   Is TradingView running with CDP? Run: make start-tradingview")
        sys.exit(1)


if __name__ == "__main__":
    main()
