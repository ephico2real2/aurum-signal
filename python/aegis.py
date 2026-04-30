"""
aegis.py — AEGIS Risk & Position Sizing Guard
=============================================
Build order: #6 — depends on SCRIBE.
Validates every trade before execution.

Human-facing decision logic, formulas, env vars: docs/AEGIS.md
Calculates lot sizes for N-trade groups based on % account risk.
Enforces daily loss limits (session-aligned, not UTC midnight).
Gradual lot scaling: reduce after 3 consecutive losses, restore after 3 wins.
"""

import os, logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from scribe import get_scribe
from status_report import report_component_status
from trading_session import trading_day_reset_hour_utc

log = logging.getLogger("aegis")

# ── Configuration ─────────────────────────────────────────────────
RISK_PCT        = float(os.environ.get("AEGIS_RISK_PCT",        "2.0"))
MAX_RISK_PCT    = float(os.environ.get("AEGIS_MAX_RISK_PCT",    "5.0"))
NUM_TRADES      = int(os.environ.get("AEGIS_NUM_TRADES",        "8"))
MAX_SLIPPAGE    = float(os.environ.get("AEGIS_MAX_SLIPPAGE",    "20.0"))
MIN_RR          = float(os.environ.get("AEGIS_MIN_RR",          "1.2"))
MAX_DAILY_LOSS  = float(os.environ.get("AEGIS_MAX_DAILY_LOSS",  "5.0"))   # % balance
MAX_OPEN_GROUPS = int(os.environ.get("AEGIS_MAX_OPEN_GROUPS",   "3"))
MIN_LOT           = float(os.environ.get("AEGIS_MIN_LOT",           "0.01"))
MAX_LOT_TOTAL     = float(os.environ.get("AEGIS_MAX_LOT_TOTAL",     "5.0"))
PIP_VALUE_PER_LOT = float(os.environ.get("AEGIS_PIP_VALUE_PER_LOT", "100.0"))  # XAUUSD default
MIN_SL_PIPS       = float(os.environ.get("AEGIS_MIN_SL_PIPS",       "3.0"))
AEGIS_SIGNAL_MAX_SLIPPAGE = float(os.environ.get("AEGIS_SIGNAL_MAX_SLIPPAGE", str(MAX_SLIPPAGE)))
AEGIS_SIGNAL_MIN_RR = float(os.environ.get("AEGIS_SIGNAL_MIN_RR", str(MIN_RR)))
AEGIS_SIGNAL_MIN_SL_PIPS = float(os.environ.get("AEGIS_SIGNAL_MIN_SL_PIPS", str(MIN_SL_PIPS)))
# SIGNAL limit-orientation gate:
#   both (default): enforce BUY below market and SELL above market
#   buy: enforce BUY only
#   sell: enforce SELL only
#   off: disable orientation gate for SIGNAL source
AEGIS_SIGNAL_LIMIT_ORIENTATION = os.environ.get(
    "AEGIS_SIGNAL_LIMIT_ORIENTATION", "both"
).strip().lower()
# Entry zone width guard (advisory by default; reject only when explicitly set).
MAX_ENTRY_ZONE_PIPS = float(os.environ.get("AEGIS_MAX_ENTRY_ZONE_PIPS", "8"))
ZONE_WIDTH_ACTION = os.environ.get("AEGIS_ZONE_WIDTH_ACTION", "warn").strip().lower()
if ZONE_WIDTH_ACTION not in ("warn", "reject"):
    ZONE_WIDTH_ACTION = "warn"
H1_TREND_FILTER   = os.environ.get("AEGIS_H1_TREND_FILTER", "true").lower() == "true"
H1_FLAT_THRESHOLD = float(os.environ.get("AEGIS_H1_FLAT_THRESHOLD", "1.0"))  # $ diff for FLAT
# Lot sizing mode: "fixed" = use source lot_per_trade as-is, "risk_based" = compute from balance/risk%
# Default "fixed" — set to "risk_based" to enable dynamic sizing
AEGIS_LOT_MODE    = os.environ.get("AEGIS_LOT_MODE", "fixed").lower().strip()

# Lot scaling thresholds
SCALE_DOWN_AFTER_LOSSES = int(os.environ.get("AEGIS_SCALE_DOWN_LOSSES", "3"))
SCALE_UP_AFTER_WINS     = int(os.environ.get("AEGIS_SCALE_UP_WINS",     "3"))
SCALE_DOWN_FACTOR       = float(os.environ.get("AEGIS_SCALE_DOWN_FACTOR","0.5"))

# Daily P&L / loss-limit window: AEGIS_SESSION_RESET_HOUR or SESSION_LONDON_START
SESSION_RESET_HOUR_UTC = trading_day_reset_hour_utc()


@dataclass
class TradeApproval:
    approved:       bool
    reject_reason:  str   = ""
    lot_per_trade:  float = 0.0
    entry_ladder:   list  = field(default_factory=list)
    num_trades:     int   = 0
    total_risk:     float = 0.0
    risk_pct:       float = 0.0
    rr_ratio:       float = 0.0
    scale_factor:   float = 1.0   # current lot scaling multiplier
    scale_reason:   str   = ""
    regime_metadata: dict = field(default_factory=dict)
    warnings:       list  = field(default_factory=list)   # advisory flags (e.g. WIDE_ZONE)
    entry_zone_pips: float = 0.0
    scale_zone_risk: bool  = False  # True when scale>1.0 AND entry_zone_pips>5


class Aegis:
    def __init__(self):
        self.scribe = get_scribe()
        log.info(f"AEGIS initialised — risk={RISK_PCT}% trades={NUM_TRADES} "
                 f"session_reset={SESSION_RESET_HOUR_UTC:02d}:00 UTC")
        try:
            report_component_status(
                "AEGIS",
                "OK",
                note=f"risk={RISK_PCT}% trades={NUM_TRADES}",
                last_action="initialised",
            )
        except Exception as e:
            log.debug(f"AEGIS heartbeat init error: {e}")

    @staticmethod
    def _score_entry_ratio(direction: str, ratio: float, fill_weight: float, edge_weight: float, target_ratio: float) -> float:
        d = (direction or "").upper()
        fill_score = ratio if d == "BUY" else (1.0 - ratio)
        edge_score = (1.0 - ratio) if d == "BUY" else ratio
        target_bonus = max(0.0, 1.0 - abs(ratio - target_ratio))
        return (fill_weight * fill_score) + (edge_weight * edge_score) + (0.15 * target_bonus)

    @staticmethod
    def _resolve_signal_regime_policy(direction: str, regime_context: dict | None) -> dict:
        ctx = dict(regime_context or {})
        label = (ctx.get("label") or "UNKNOWN").upper()
        confidence = max(0.0, min(1.0, float(ctx.get("confidence") or 0.0)))
        entry_mode = (ctx.get("entry_mode") or "off").lower()
        apply_policy = bool(ctx.get("apply_entry_policy"))
        d = (direction or "").upper()

        if label == "RANGE":
            target = 0.20 if d == "BUY" else 0.80
            dispersion = 0.16
            fill_w, edge_w = 0.35, 0.65
            policy_name = "MEAN_REVERSION_PULLBACK"
        elif label == "VOLATILE":
            target = 0.50
            dispersion = 0.45
            fill_w, edge_w = 0.62, 0.38
            policy_name = "VOLATILITY_BALANCED"
        elif label == "TREND_BULL":
            if d == "BUY":
                target = 0.78
                dispersion = 0.28
                fill_w, edge_w = 0.72, 0.28
            else:
                target = 0.84
                dispersion = 0.12
                fill_w, edge_w = 0.30, 0.70
            policy_name = "TREND_FOLLOW_BULL"
        elif label == "TREND_BEAR":
            if d == "SELL":
                target = 0.22
                dispersion = 0.28
                fill_w, edge_w = 0.72, 0.28
            else:
                target = 0.16
                dispersion = 0.12
                fill_w, edge_w = 0.30, 0.70
            policy_name = "TREND_FOLLOW_BEAR"
        else:
            target = 0.35 if d == "BUY" else 0.65
            dispersion = 0.20
            fill_w, edge_w = 0.50, 0.50
            policy_name = "LEGACY_SIGNAL_FAVORABLE_ENDPOINT"

        # Blend toward neutral as confidence drops.
        blend = confidence
        neutral = 0.50
        target = (blend * target) + ((1.0 - blend) * neutral)
        fill_w = (blend * fill_w) + ((1.0 - blend) * 0.50)
        edge_w = (blend * edge_w) + ((1.0 - blend) * 0.50)
        norm = max(0.0001, fill_w + edge_w)
        fill_w, edge_w = fill_w / norm, edge_w / norm

        return {
            "label": label,
            "confidence": confidence,
            "entry_mode": entry_mode,
            "apply_policy": apply_policy,
            "policy_name": policy_name,
            "fill_weight": fill_w,
            "edge_weight": edge_w,
            "target_ratio": target,
            "dispersion_ratio": max(0.0, min(0.50, dispersion)),
            "model_name": ctx.get("model_name"),
            "fallback_reason": ctx.get("fallback_reason"),
            "entry_gate_reason": ctx.get("entry_gate_reason"),
        }

    @staticmethod
    def _build_entry_ladder(
        direction: str,
        entry_low: float,
        entry_high: float,
        num_trades: int,
        source: str = "",
        regime_context: dict | None = None,
        include_meta: bool = False,
    ) -> list[float] | tuple[list[float], dict]:
        """
        Build entry prices for group legs.
        For SIGNAL source, prioritize favorable endpoint:
          - BUY -> cheapest entry (entry_low)
          - SELL -> highest entry (entry_high)
        """
        trades = max(1, int(num_trades))
        lo = float(entry_low)
        hi = float(entry_high)
        dir_u = (direction or "").upper()
        src_u = (source or "").upper()

        meta = {
            "label": None,
            "confidence": None,
            "model_name": None,
            "entry_mode": "off",
            "policy_name": "LEGACY_SIGNAL_FAVORABLE_ENDPOINT",
            "fallback_reason": None,
            "entry_gate_reason": None,
            "applied": False,
        }

        if src_u == "SIGNAL" and hi > lo and trades > 1:
            policy = Aegis._resolve_signal_regime_policy(dir_u, regime_context)
            meta.update(
                {
                    "label": policy.get("label"),
                    "confidence": policy.get("confidence"),
                    "model_name": policy.get("model_name"),
                    "entry_mode": policy.get("entry_mode"),
                    "policy_name": policy.get("policy_name"),
                    "fallback_reason": policy.get("fallback_reason"),
                    "entry_gate_reason": policy.get("entry_gate_reason"),
                }
            )

            if policy.get("apply_policy"):
                ratios = [i / 10.0 for i in range(1, 10)]
                target_ratio = float(policy.get("target_ratio") or 0.5)
                fill_w = float(policy.get("fill_weight") or 0.5)
                edge_w = float(policy.get("edge_weight") or 0.5)
                best_ratio = max(
                    ratios,
                    key=lambda r: Aegis._score_entry_ratio(
                        dir_u,
                        r,
                        fill_w,
                        edge_w,
                        target_ratio,
                    ),
                )
                span = hi - lo
                anchor = lo + (span * best_ratio)
                dispersion = span * float(policy.get("dispersion_ratio") or 0.0)
                lo_b = max(lo, anchor - (dispersion / 2.0))
                hi_b = min(hi, anchor + (dispersion / 2.0))
                if trades == 1 or hi_b <= lo_b:
                    ladder = [round(anchor, 2)] * trades
                else:
                    step = (hi_b - lo_b) / (trades - 1)
                    ladder = [round(lo_b + i * step, 2) for i in range(trades)]
                meta["applied"] = True
                meta["target_ratio"] = round(best_ratio, 4)
                if include_meta:
                    return ladder, meta
                return ladder

            # shadow/off/blocked gate -> keep legacy endpoint behavior
            favored = lo if dir_u == "BUY" else hi
            ladder = [round(favored, 2)] * trades
            if include_meta:
                return ladder, meta
            return ladder

        if hi > lo and trades > 1:
            step = (hi - lo) / (trades - 1)
            ladder = [round(lo + i * step, 2) for i in range(trades)]
            if include_meta:
                return ladder, meta
            return ladder
        ladder = [round(lo, 2)] * trades
        if include_meta:
            return ladder, meta
        return ladder

    @staticmethod
    def _signal_limit_orientation_reject_reason(
        direction: str,
        entry_low: float,
        entry_high: float,
        current_price: float | None,
        source: str = "",
    ) -> str | None:
        """
        SIGNAL policy: pending entries should be LIMIT-oriented, not STOP-oriented.
          - BUY entry should be below current market
          - SELL entry should be above current market
        """
        if (source or "").upper() != "SIGNAL" or current_price is None:
            return None
        try:
            cp = float(current_price)
            lo = float(entry_low)
            hi = float(entry_high)
        except (TypeError, ValueError):
            return None
        mode = AEGIS_SIGNAL_LIMIT_ORIENTATION
        if mode in ("off", "none", "false", "0", "disabled"):
            return None
        if mode not in ("both", "buy", "sell"):
            mode = "both"
        d = (direction or "").upper()
        enforce_buy = mode in ("both", "buy")
        enforce_sell = mode in ("both", "sell")
        if d == "BUY" and enforce_buy and lo >= cp:
            return f"SIGNAL_BUY_LIMIT_REQUIRED:entry_low={lo:.2f}>=market={cp:.2f}"
        if d == "SELL" and enforce_sell and hi <= cp:
            return f"SIGNAL_SELL_LIMIT_REQUIRED:entry_high={hi:.2f}<=market={cp:.2f}"
        return None

    # ── Public API ─────────────────────────────────────────────────
    def validate(self, signal: dict, account: dict,
                 current_price: float = None,
                 mt5_data: dict = None,
                 regime_context: dict | None = None) -> TradeApproval:
        """
        Validate signal and return approval with lot sizes.
        signal keys: direction, entry_low, entry_high, sl, tp1
        account keys: balance, equity, open_groups_count
        mt5_data: raw market_data.json for H1 trend filter
        """
        direction   = signal.get("direction", "")
        source      = signal.get("source", "")
        source_u    = (source or "").upper()
        entry_low   = float(signal.get("entry_low", 0))
        entry_high  = float(signal.get("entry_high", entry_low))
        sl          = float(signal.get("sl", 0))
        tp1         = float(signal.get("tp1", 0))
        balance     = float(account.get("balance", 0))
        open_groups = int(account.get("open_groups_count", 0))
        min_rr_req = AEGIS_SIGNAL_MIN_RR if source_u == "SIGNAL" else MIN_RR
        min_sl_req = AEGIS_SIGNAL_MIN_SL_PIPS if source_u == "SIGNAL" else MIN_SL_PIPS
        max_slippage_req = AEGIS_SIGNAL_MAX_SLIPPAGE if source_u == "SIGNAL" else MAX_SLIPPAGE

        # ── Guard 1: Completeness ──────────────────────────────────
        if not all([direction, entry_low, sl, tp1, balance]):
            return TradeApproval(False, "INCOMPLETE_SIGNAL")
        if direction not in ("BUY", "SELL"):
            return TradeApproval(False, f"INVALID_DIRECTION:{direction}")
        orientation_reject = self._signal_limit_orientation_reject_reason(
            direction, entry_low, entry_high, current_price, source=source
        )
        if orientation_reject:
            return TradeApproval(False, orientation_reject)

        # ── Guard 1b: Multi-TF trend filter (cascade by source) ────
        if H1_TREND_FILTER and mt5_data:
            rejection = self._check_trend_cascade(direction, source, mt5_data)
            if rejection:
                return TradeApproval(False, rejection)

        # ── Guard 1c: Floating P&L check ─────────────────────────
        if mt5_data:
            floating = (mt5_data.get("account") or {}).get("total_floating_pnl", 0)
            if floating < 0 and balance > 0:
                float_pct = abs(floating) / balance * 100
                float_limit = float(os.environ.get("DD_FLOATING_BLOCK_PCT", "2.0"))
                if float_pct >= float_limit:
                    return TradeApproval(False,
                        f"FLOATING_DD:{float_pct:.1f}%>={float_limit}% (floating ${floating:.2f})")

        # ── Guard 2: Max open groups ─────────────────────────────
        if open_groups >= MAX_OPEN_GROUPS:
            return TradeApproval(False,
                f"MAX_GROUPS:{open_groups}/{MAX_OPEN_GROUPS}")

        # ── Guard 3: Daily loss (session-aligned) ──────────────────
        session_pnl = self._get_session_pnl()
        max_loss    = balance * (MAX_DAILY_LOSS / 100)
        if session_pnl < 0 and abs(session_pnl) >= max_loss:
            return TradeApproval(False,
                f"DAILY_LOSS_LIMIT:${abs(session_pnl):.2f}/${max_loss:.2f}")

        # ── Guard 4: Slippage ──────────────────────────────────────
        if current_price:
            slippage = (current_price - entry_high if direction == "BUY"
                        else entry_low - current_price)
            if slippage > max_slippage_req:
                return TradeApproval(False,
                    f"SLIPPAGE:{slippage:.1f}>{max_slippage_req}pips")

        # ── Guard 5: SL distance ───────────────────────────────────
        mid_entry = (entry_low + entry_high) / 2
        sl_pips   = (mid_entry - sl if direction == "BUY" else sl - mid_entry)
        if sl_pips <= 0:
            return TradeApproval(False, "INVALID_SL:SL_BEYOND_ENTRY")
        if sl_pips < min_sl_req:
            return TradeApproval(False, f"SL_TOO_TIGHT:{sl_pips:.1f}<{min_sl_req}pips")

        # ── Guard 6: R:R ─────────────────────────────────────────────
        tp_pips = (tp1 - mid_entry if direction == "BUY" else mid_entry - tp1)
        if tp_pips <= 0:
            return TradeApproval(False, "INVALID_TP1:TP_BEYOND_ENTRY")
        rr = tp_pips / sl_pips
        if rr < min_rr_req:
            return TradeApproval(False, f"LOW_RR:{rr:.2f}<{min_rr_req}")

        # ── Guard 7: Entry zone width (SIGNAL/AURUM only) ────────────
        # Wide zones carry inherent fill-rate risk for layered limit ladders.
        # Default action is `warn` (advisory). Set AEGIS_ZONE_WIDTH_ACTION=reject
        # to hard-block wide-zone entries.
        warnings: list[str] = []
        entry_zone_pips = abs(entry_high - entry_low)
        if source_u in ("SIGNAL", "AURUM", "AUTO_SCALPER") and entry_zone_pips > MAX_ENTRY_ZONE_PIPS:
            if ZONE_WIDTH_ACTION == "reject":
                return TradeApproval(
                    False,
                    f"WIDE_ZONE:{entry_zone_pips:.1f}>={MAX_ENTRY_ZONE_PIPS:.1f}",
                )
            log.warning(
                "AEGIS: WIDE_ZONE entry_zone_pips=%.1f threshold=%.1f source=%s",
                entry_zone_pips, MAX_ENTRY_ZONE_PIPS, source_u,
            )
            warnings.append("WIDE_ZONE")

        # ── Per-signal num_trades override ───────────────────────
        num_trades = NUM_TRADES
        sig_nt = signal.get("num_trades")
        if sig_nt is not None:
            try:
                sig_nt = int(sig_nt)
                if 1 <= sig_nt <= 20:
                    num_trades = sig_nt
            except (TypeError, ValueError):
                pass

        # ── Lot scaling ────────────────────────────────────────────
        scale_factor, scale_reason = self._get_scale_factor()

        # ── Lot sizing ─────────────────────────────────────────────
        # Risk-based sizing always computed (for logging/reference)
        effective_risk_pct = RISK_PCT * scale_factor
        risk_amount  = balance * (effective_risk_pct / 100)
        risk_lot = risk_amount / (num_trades * sl_pips * PIP_VALUE_PER_LOT)
        risk_lot = max(MIN_LOT, round(risk_lot, 2))

        sig_lot = signal.get("lot_per_trade")
        use_fixed = (
            AEGIS_LOT_MODE == "fixed"
            and sig_lot is not None
            and signal.get("source") in ("AUTO_SCALPER", "AURUM", "SIGNAL", "SCALPER")
        )
        if use_fixed:
            try:
                lot_per_trade = max(MIN_LOT, min(float(sig_lot), MAX_LOT_TOTAL / num_trades))
            except (TypeError, ValueError):
                lot_per_trade = risk_lot
        else:
            lot_per_trade = risk_lot

        # Cap total exposure
        if lot_per_trade * num_trades > MAX_LOT_TOTAL:
            lot_per_trade = round(MAX_LOT_TOTAL / num_trades, 2)

        # ── Entry ladder ───────────────────────────────────────────
        ladder, ladder_meta = self._build_entry_ladder(
            direction,
            entry_low,
            entry_high,
            num_trades,
            source=source,
            regime_context=regime_context,
            include_meta=True,
        )

        total_risk = lot_per_trade * num_trades * sl_pips * PIP_VALUE_PER_LOT
        scale_zone_risk = bool(scale_factor > 1.0 and entry_zone_pips > 5.0)

        approved_line = (
            f"AEGIS APPROVED: {direction} {num_trades}×{lot_per_trade}lot "
            f"SL={sl_pips:.1f}p R:R={rr:.2f} risk=${total_risk:.2f} "
            f"scale={scale_factor:.0%} ({scale_reason}) "
            f"entry_zone_pips={entry_zone_pips:.1f}"
        )
        if scale_zone_risk:
            approved_line += " scale_zone_risk=true"
        if warnings:
            approved_line += f" warnings={','.join(warnings)}"
        log.info(approved_line)

        try:
            report_component_status(
                "AEGIS",
                "OK",
                note=f"scale={scale_factor:.0%} ({scale_reason})",
                last_action=f"approved {direction} {NUM_TRADES}x{lot_per_trade}lot rr={rr:.1f}",
            )
        except Exception as e:
            log.debug(f"AEGIS heartbeat error: {e}")

        return TradeApproval(
            approved=True,
            lot_per_trade=lot_per_trade,
            entry_ladder=ladder,
            num_trades=num_trades,
            total_risk=round(total_risk, 2),
            risk_pct=round(effective_risk_pct, 2),
            rr_ratio=round(rr, 2),
            scale_factor=scale_factor,
            scale_reason=scale_reason,
            regime_metadata=ladder_meta,
            warnings=warnings,
            entry_zone_pips=round(entry_zone_pips, 2),
            scale_zone_risk=scale_zone_risk,
        )

    # ── Multi-TF trend cascade ───────────────────────────────
    @staticmethod
    def _tf_bias(indicators: dict, flat_threshold: float = 1.0) -> str:
        """Return BULL/BEAR/FLAT for a timeframe's EMA20 vs EMA50."""
        ema20 = indicators.get("ema_20") or indicators.get("ma_20")
        ema50 = indicators.get("ema_50") or indicators.get("ma_50")
        if ema20 is None or ema50 is None:
            return "FLAT"
        diff = float(ema20) - float(ema50)
        if diff > flat_threshold:
            return "BULL"
        if diff < -flat_threshold:
            return "BEAR"
        return "FLAT"

    def _check_trend_cascade(self, direction: str, source: str, mt5_data: dict) -> str | None:
        """
        Multi-TF trend filter with cascade priority based on signal source.
        Returns rejection reason string, or None if trade is allowed.

        SIGNAL source (scalping): M5 → M15 → H1
          - If M5 agrees with direction → PASS (scalpers trust M5)
          - If M5 flat but M15 agrees → PASS
          - If both M5 and M15 conflict → REJECT

        AURUM / AUTO_SCALPER: H1 → M15
          - H1 conflicts → check M15 fallback
          - Both conflict → REJECT

        SCALPER (BRIDGE internal): H1 only (strict)
        """
        h1  = self._tf_bias((mt5_data or {}).get("indicators_h1", {}), H1_FLAT_THRESHOLD)
        m15 = self._tf_bias((mt5_data or {}).get("indicators_m15", {}), H1_FLAT_THRESHOLD)
        m5  = self._tf_bias((mt5_data or {}).get("indicators_m5", {}), H1_FLAT_THRESHOLD)

        def agrees(bias: str) -> bool:
            if direction == "BUY":
                return bias in ("BULL", "FLAT")
            else:
                return bias in ("BEAR", "FLAT")

        if source == "SIGNAL":
            # Scalping cascade: M5 → M15 → H1
            if agrees(m5):
                if not agrees(h1):
                    log.info("AEGIS: SIGNAL allowed via M5 %s (H1=%s M15=%s M5=%s)", direction, h1, m15, m5)
                return None  # M5 agrees → pass
            if agrees(m15):
                log.info("AEGIS: SIGNAL allowed via M15 %s (H1=%s M15=%s M5=%s)", direction, h1, m15, m5)
                return None  # M5 doesn't agree but M15 does → pass
            # Both M5 and M15 conflict → reject
            return f"TREND_CONFLICT:M5={m5}_M15={m15}_vs_{direction}(scalp_cascade)"

        elif source in ("AURUM", "AUTO_SCALPER"):
            # Conservative cascade: H1 → M15
            if agrees(h1):
                return None
            if agrees(m15):
                log.info("AEGIS: %s allowed via M15 fallback (H1=%s M15=%s)", source, h1, m15)
                return None
            return f"H1_TREND_CONFLICT:H1={h1}_M15={m15}_vs_{direction}"

        else:
            # SCALPER / other: strict H1 only
            if not agrees(h1):
                return f"H1_TREND_CONFLICT:H1={h1}_vs_{direction}"
            return None

    # ── Session-aligned daily P&L ──────────────────────────────
    def _get_session_pnl(self) -> float:
        """
        Returns P&L since the last trading-day boundary (SESSION_RESET_HOUR_UTC,
        from AEGIS_SESSION_RESET_HOUR or SESSION_LONDON_START — see trading_session.py).
        This avoids counting trades after that hour against the previous day's loss cap.
        """
        now = datetime.now(timezone.utc)
        session_start = now.replace(
            hour=SESSION_RESET_HOUR_UTC, minute=0, second=0, microsecond=0
        )
        # If current time is before session start, use yesterday's session start
        if now < session_start:
            session_start -= timedelta(days=1)

        try:
            rows = self.scribe.query(
                """SELECT COALESCE(SUM(pnl), 0) as total
                   FROM trade_positions
                   WHERE status = 'CLOSED'
                   AND close_time >= ?""",
                (session_start.isoformat(),)
            )
            return float(rows[0]["total"]) if rows else 0.0
        except Exception as e:
            log.error(f"AEGIS session P&L query error: {e}")
            return 0.0

    # ── Gradual lot scaling ────────────────────────────────────────
    def _get_scale_factor(self) -> tuple[float, str]:
        """
        Returns (scale_factor, reason_string).
        Checks last N closed trades from this session:
        - 3+ consecutive losses → scale down to SCALE_DOWN_FACTOR
        - 3+ consecutive wins   → allow up to MAX_RISK_PCT
        - Mixed                 → normal RISK_PCT (factor = 1.0)
        """
        try:
            rows = self.scribe.query(
                """SELECT pnl FROM trade_positions
                   WHERE status = 'CLOSED'
                   ORDER BY close_time DESC
                   LIMIT ?""",
                (max(SCALE_DOWN_AFTER_LOSSES, SCALE_UP_AFTER_WINS),)
            )
        except Exception as e:
            log.error(f"AEGIS scale query error: {e}")
            return 1.0, "NORMAL (query error)"

        if not rows:
            return 1.0, "NORMAL (no history)"

        pnls = [r["pnl"] for r in rows]

        # Check consecutive losses (most recent first)
        consecutive_losses = 0
        for p in pnls:
            if p < 0:
                consecutive_losses += 1
            else:
                break

        # Check consecutive wins
        consecutive_wins = 0
        for p in pnls:
            if p > 0:
                consecutive_wins += 1
            else:
                break

        if consecutive_losses >= SCALE_DOWN_AFTER_LOSSES:
            factor = SCALE_DOWN_FACTOR
            reason = f"REDUCED ({consecutive_losses} consecutive losses)"
            log.warning(f"AEGIS: lot scaling DOWN to {factor:.0%} — {reason}")
            return factor, reason

        if consecutive_wins >= SCALE_UP_AFTER_WINS:
            # Scale up proportionally — e.g. MAX/NORMAL gives the headroom
            factor = min(MAX_RISK_PCT / RISK_PCT, 1.5)  # cap at 1.5×
            reason = f"INCREASED ({consecutive_wins} consecutive wins)"
            log.info(f"AEGIS: lot scaling UP to {factor:.0%} — {reason}")
            return factor, reason

        return 1.0, "NORMAL"


# ── Singleton ─────────────────────────────────────────────────────
_instance: Aegis = None

def get_aegis() -> Aegis:
    global _instance
    if _instance is None:
        _instance = Aegis()
    return _instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    a = Aegis()

    # Test 1: Good signal
    sig  = {"direction":"BUY","entry_low":3180.0,"entry_high":3185.0,
             "sl":3170.0,"tp1":3200.0,"tp2":3220.0}
    acc  = {"balance":10000.0,"equity":10000.0,"open_groups_count":0}
    r    = a.validate(sig, acc, 3183.0)
    print(f"BUY test:      approved={r.approved} lot={r.lot_per_trade} "
          f"scale={r.scale_factor:.0%} ({r.scale_reason})")

    # Test 2: Slippage
    r2 = a.validate(sig, acc, 3210.0)
    print(f"Slippage test: approved={r2.approved} reason={r2.reject_reason}")

    # Test 3: Low R:R
    sig3 = {"direction":"SELL","entry_low":3200.0,"entry_high":3202.0,
             "sl":3220.0,"tp1":3198.0}
    r3 = a.validate(sig3, acc, 3201.0)
    print(f"Low R:R test:  approved={r3.approved} reason={r3.reject_reason}")

    print(f"\nSession P&L: ${a._get_session_pnl():.2f}")
    print(f"Scale factor: {a._get_scale_factor()}")

