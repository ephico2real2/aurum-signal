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

    # ── Public API ─────────────────────────────────────────────────
    def validate(self, signal: dict, account: dict,
                 current_price: float = None,
                 mt5_data: dict = None) -> TradeApproval:
        """
        Validate signal and return approval with lot sizes.
        signal keys: direction, entry_low, entry_high, sl, tp1
        account keys: balance, equity, open_groups_count
        mt5_data: raw market_data.json for H1 trend filter
        """
        direction   = signal.get("direction", "")
        entry_low   = float(signal.get("entry_low", 0))
        entry_high  = float(signal.get("entry_high", entry_low))
        sl          = float(signal.get("sl", 0))
        tp1         = float(signal.get("tp1", 0))
        balance     = float(account.get("balance", 0))
        open_groups = int(account.get("open_groups_count", 0))

        # ── Guard 1: Completeness ──────────────────────────────────
        if not all([direction, entry_low, sl, tp1, balance]):
            return TradeApproval(False, "INCOMPLETE_SIGNAL")
        if direction not in ("BUY", "SELL"):
            return TradeApproval(False, f"INVALID_DIRECTION:{direction}")

        # ── Guard 1b: Multi-TF trend filter (cascade by source) ────
        if H1_TREND_FILTER and mt5_data:
            source = signal.get("source", "")
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
            if slippage > MAX_SLIPPAGE:
                return TradeApproval(False,
                    f"SLIPPAGE:{slippage:.1f}>{MAX_SLIPPAGE}pips")

        # ── Guard 5: SL distance ───────────────────────────────────
        mid_entry = (entry_low + entry_high) / 2
        sl_pips   = (mid_entry - sl if direction == "BUY" else sl - mid_entry)
        if sl_pips <= 0:
            return TradeApproval(False, "INVALID_SL:SL_BEYOND_ENTRY")
        if sl_pips < MIN_SL_PIPS:
            return TradeApproval(False, f"SL_TOO_TIGHT:{sl_pips:.1f}<{MIN_SL_PIPS}pips")

        # ── Guard 6: R:R ───────────────────────────────────────────
        tp_pips = (tp1 - mid_entry if direction == "BUY" else mid_entry - tp1)
        if tp_pips <= 0:
            return TradeApproval(False, "INVALID_TP1:TP_BEYOND_ENTRY")
        rr = tp_pips / sl_pips
        if rr < MIN_RR:
            return TradeApproval(False, f"LOW_RR:{rr:.2f}<{MIN_RR}")

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
        if entry_high > entry_low and num_trades > 1:
            step   = (entry_high - entry_low) / (num_trades - 1)
            ladder = [round(entry_low + i * step, 2) for i in range(num_trades)]
        else:
            ladder = [entry_low] * num_trades

        total_risk = lot_per_trade * num_trades * sl_pips * PIP_VALUE_PER_LOT

        log.info(
            f"AEGIS APPROVED: {direction} {num_trades}×{lot_per_trade}lot "
            f"SL={sl_pips:.1f}p R:R={rr:.2f} risk=${total_risk:.2f} "
            f"scale={scale_factor:.0%} ({scale_reason})"
        )

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

