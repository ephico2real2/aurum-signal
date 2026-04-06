"""
market_view.py — Unified Market Data View
==========================================
Combines FORGE (market_data.json, 3s, multi-TF) with LENS (TradingView MCP snapshot).
Single source of truth for AURUM, AEGIS, AUTO_SCALPER, and dashboard.
"""

import os, json, logging
from pathlib import Path

log = logging.getLogger("market_view")

_PY = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_PY, ".."))

MARKET_FILE = os.path.join(
    _ROOT, os.environ.get("MT5_MARKET_FILE", "MT5/market_data.json")
)
LENS_FILE = os.path.join(
    _PY, os.environ.get("LENS_SNAPSHOT_FILE", "config/lens_snapshot.json")
)

_TF_KEYS = ("h1", "m5", "m15", "m30")
_INDICATOR_FIELDS = (
    "rsi_14", "ema_20", "ema_50", "atr_14",
    "bb_upper", "bb_mid", "bb_lower",
    "macd_hist", "adx",
)


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _parse_tf(mt5: dict, key: str) -> dict:
    """Extract indicator dict for a timeframe from market_data.json."""
    raw = mt5.get(f"indicators_{key}", {})
    if not raw:
        return {}
    out = {}
    for field in _INDICATOR_FIELDS:
        v = raw.get(field)
        # H1 used to call EMAs "ma_20"/"ma_50" — normalise
        if v is None and field == "ema_20":
            v = raw.get("ma_20")
        if v is None and field == "ema_50":
            v = raw.get("ma_50")
        out[field] = float(v) if v is not None else None
    return out


def _ema_bias(tf_data: dict, flat_threshold: float = 1.0) -> str:
    """BULL / BEAR / FLAT from EMA20 vs EMA50."""
    ema20 = tf_data.get("ema_20")
    ema50 = tf_data.get("ema_50")
    if ema20 is None or ema50 is None:
        return "UNKNOWN"
    diff = ema20 - ema50
    if diff > flat_threshold:
        return "BULL"
    if diff < -flat_threshold:
        return "BEAR"
    return "FLAT"


def build_market_view(mt5: dict = None, lens: dict = None) -> dict:
    """
    Build a unified market view from FORGE + LENS data.

    Parameters
    ----------
    mt5 : dict, optional
        Parsed market_data.json. If None, reads from disk.
    lens : dict, optional
        Parsed lens_snapshot.json. If None, reads from disk.

    Returns
    -------
    dict with keys: price, h1, m5, m15, m30, h1_bias, tv_recommend, fresh
    """
    if mt5 is None:
        mt5 = _read_json(MARKET_FILE)
    if lens is None:
        lens = _read_json(LENS_FILE)

    price_raw = mt5.get("price", {})
    bid = price_raw.get("bid")
    ask = price_raw.get("ask")
    mid = round((bid + ask) / 2, 2) if bid and ask else None

    view = {
        "price": {
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread": price_raw.get("spread_points"),
        },
        "symbol": mt5.get("symbol", "XAUUSD"),
        "fresh": bool(mt5),
    }

    # Multi-TF indicators from FORGE
    for tf in _TF_KEYS:
        tf_data = _parse_tf(mt5, tf)
        tf_data["bias"] = _ema_bias(tf_data)
        view[tf] = tf_data

    # Convenience: H1 bias at top level
    view["h1_bias"] = view.get("h1", {}).get("bias", "UNKNOWN")

    # LENS supplement (TradingView-specific data)
    view["tv_recommend"] = lens.get("tv_recommend") if lens else None
    view["lens_age"] = lens.get("age_seconds") if lens else None

    return view


def market_view_summary(view: dict) -> str:
    """One-line summary for logging."""
    h1 = view.get("h1", {})
    m5 = view.get("m5", {})
    p = view.get("price", {})
    return (
        f"mid=${p.get('mid','?')} H1={view.get('h1_bias','?')} "
        f"RSI(H1)={h1.get('rsi_14','?')} RSI(M5)={m5.get('rsi_14','?')} "
        f"ADX(H1)={h1.get('adx','?')}"
    )


def format_for_aurum(view: dict) -> str:
    """Format MarketView as text for AURUM's system prompt context.

    Includes price-relative analysis so AURUM can make better
    scalping decisions without computing structure from raw numbers.
    """
    lines = []
    p = view.get("price", {})
    mid = p.get("mid")
    if mid:
        lines.append(
            f"MT5 PRICE: bid ${p['bid']:.2f}  ask ${p['ask']:.2f}  "
            f"mid ${mid:.2f}  spread {p.get('spread', '?')}pt"
        )

    for tf_key, label in [("h1", "H1"), ("m30", "M30"), ("m15", "M15"), ("m5", "M5")]:
        tf = view.get(tf_key, {})
        if not tf or tf.get("rsi_14") is None:
            continue
        rsi = tf.get("rsi_14", 0)
        macd = tf.get("macd_hist")
        adx = tf.get("adx")
        ema20 = tf.get("ema_20")
        ema50 = tf.get("ema_50")
        atr = tf.get("atr_14")
        bb_u = tf.get("bb_upper")
        bb_m = tf.get("bb_mid")
        bb_l = tf.get("bb_lower")
        bias = tf.get("bias", "?")

        parts = [f"{label} ({bias}): RSI {rsi:.1f}"]
        if macd is not None:
            parts.append(f"MACD {macd:+.5f}")
        if adx is not None:
            parts.append(f"ADX {adx:.1f}")
        if atr is not None:
            parts.append(f"ATR ${atr:.2f}")
        if ema20 and ema50:
            parts.append(f"EMA20 ${ema20:.2f} EMA50 ${ema50:.2f}")
        if bb_u and bb_m and bb_l:
            parts.append(f"BB [{bb_l:.2f}/{bb_m:.2f}/{bb_u:.2f}]")
        lines.append("  " + " | ".join(parts))

        # Price-relative context (only for M5/M15 — scalping timeframes)
        if mid and tf_key in ("m5", "m15") and bb_u and bb_m and bb_l and atr:
            hints = []
            bb_range = bb_u - bb_l
            if bb_range > 0:
                bb_pct = (mid - bb_l) / bb_range * 100
                hints.append(f"price at {bb_pct:.0f}% of BB range")
                if bb_pct < 20:
                    hints.append("NEAR BB LOWER (bounce zone)")
                elif bb_pct > 80:
                    hints.append("NEAR BB UPPER (rejection zone)")
            if ema20:
                dist_ema20 = mid - ema20
                if abs(dist_ema20) < atr * 0.3:
                    hints.append(f"AT EMA20 (${dist_ema20:+.2f})")
                elif dist_ema20 > 0:
                    hints.append(f"${dist_ema20:.2f} ABOVE EMA20")
                else:
                    hints.append(f"${abs(dist_ema20):.2f} BELOW EMA20")
            # RSI momentum hint
            if rsi < 30:
                hints.append("RSI OVERSOLD")
            elif rsi > 70:
                hints.append("RSI OVERBOUGHT")
            elif rsi < 40:
                hints.append("RSI weak")
            elif rsi > 60:
                hints.append("RSI strong")
            if hints:
                lines.append(f"    → {' | '.join(hints)}")

    tv = view.get("tv_recommend")
    if tv is not None:
        lines.append(f"  TV Recommend: {tv}")

    return "\n".join(lines)
