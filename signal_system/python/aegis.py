"""
aegis.py — AEGIS Risk & Position Sizing Guard
=============================================
Build order: #6 — depends on SCRIBE.
Validates every trade before execution.
Calculates lot sizes for N-trade groups based on % account risk.
Enforces daily loss limits (session-aligned, not UTC midnight).
Gradual lot scaling: reduce after 3 consecutive losses, restore after 3 wins.
"""

import os, logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from scribe import get_scribe

log = logging.getLogger("aegis")

# ── Configuration ─────────────────────────────────────────────────
RISK_PCT        = float(os.environ.get("AEGIS_RISK_PCT",        "2.0"))
MAX_RISK_PCT    = float(os.environ.get("AEGIS_MAX_RISK_PCT",    "5.0"))
NUM_TRADES      = int(os.environ.get("AEGIS_NUM_TRADES",        "8"))
MAX_SLIPPAGE    = float(os.environ.get("AEGIS_MAX_SLIPPAGE",    "20.0"))
MIN_RR          = float(os.environ.get("AEGIS_MIN_RR",          "1.2"))
MAX_DAILY_LOSS  = float(os.environ.get("AEGIS_MAX_DAILY_LOSS",  "5.0"))   # % balance
MAX_OPEN_GROUPS = int(os.environ.get("AEGIS_MAX_OPEN_GROUPS",   "3"))
MIN_LOT         = 0.01
MAX_LOT_TOTAL   = float(os.environ.get("AEGIS_MAX_LOT_TOTAL",   "5.0"))
PIP_VALUE_PER_LOT = 100.0   # XAUUSD: 1 pip = $100 per full lot

# Lot scaling thresholds
SCALE_DOWN_AFTER_LOSSES = int(os.environ.get("AEGIS_SCALE_DOWN_LOSSES", "3"))
SCALE_UP_AFTER_WINS     = int(os.environ.get("AEGIS_SCALE_UP_WINS",     "3"))
SCALE_DOWN_FACTOR       = float(os.environ.get("AEGIS_SCALE_DOWN_FACTOR","0.5"))

# Session-aligned daily reset: London open = 07:00 UTC
SESSION_RESET_HOUR_UTC  = int(os.environ.get("AEGIS_SESSION_RESET_HOUR", "7"))


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
            self.scribe.heartbeat(
                component   = "AEGIS",
                status      = "OK",
                note        = f"risk={RISK_PCT}% trades={NUM_TRADES}",
                last_action = "initialised",
            )
        except Exception as e:
            log.debug(f"AEGIS heartbeat init error: {e}")

    # ── Public API ─────────────────────────────────────────────────
    def validate(self, signal: dict, account: dict,
                 current_price: float = None) -> TradeApproval:
        """
        Validate signal and return approval with lot sizes.
        signal keys: direction, entry_low, entry_high, sl, tp1
        account keys: balance, equity, open_groups_count
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

        # ── Guard 2: Max open groups ───────────────────────────────
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
        if sl_pips < 3:
            return TradeApproval(False, f"SL_TOO_TIGHT:{sl_pips:.1f}pips")

        # ── Guard 6: R:R ───────────────────────────────────────────
        tp_pips = (tp1 - mid_entry if direction == "BUY" else mid_entry - tp1)
        if tp_pips <= 0:
            return TradeApproval(False, "INVALID_TP1:TP_BEYOND_ENTRY")
        rr = tp_pips / sl_pips
        if rr < MIN_RR:
            return TradeApproval(False, f"LOW_RR:{rr:.2f}<{MIN_RR}")

        # ── Lot scaling ────────────────────────────────────────────
        scale_factor, scale_reason = self._get_scale_factor()

        # ── Lot sizing ─────────────────────────────────────────────
        effective_risk_pct = RISK_PCT * scale_factor
        risk_amount  = balance * (effective_risk_pct / 100)
        lot_per_trade = risk_amount / (NUM_TRADES * sl_pips * PIP_VALUE_PER_LOT)
        lot_per_trade = max(MIN_LOT, round(lot_per_trade, 2))

        # Cap total exposure
        if lot_per_trade * NUM_TRADES > MAX_LOT_TOTAL:
            lot_per_trade = round(MAX_LOT_TOTAL / NUM_TRADES, 2)

        # ── Entry ladder ───────────────────────────────────────────
        if entry_high > entry_low and NUM_TRADES > 1:
            step   = (entry_high - entry_low) / (NUM_TRADES - 1)
            ladder = [round(entry_low + i * step, 2) for i in range(NUM_TRADES)]
        else:
            ladder = [entry_low] * NUM_TRADES

        total_risk = lot_per_trade * NUM_TRADES * sl_pips * PIP_VALUE_PER_LOT

        log.info(
            f"AEGIS APPROVED: {direction} {NUM_TRADES}×{lot_per_trade}lot "
            f"SL={sl_pips:.1f}p R:R={rr:.2f} risk=${total_risk:.2f} "
            f"scale={scale_factor:.0%} ({scale_reason})"
        )

        try:
            self.scribe.heartbeat(
                component   = "AEGIS",
                status      = "OK",
                note        = f"scale={scale_factor:.0%} ({scale_reason})",
                last_action = f"approved {direction} {NUM_TRADES}x{lot_per_trade}lot rr={rr:.1f}",
            )
        except Exception as e:
            log.debug(f"AEGIS heartbeat error: {e}")

        return TradeApproval(
            approved=True,
            lot_per_trade=lot_per_trade,
            entry_ladder=ladder,
            num_trades=NUM_TRADES,
            total_risk=round(total_risk, 2),
            risk_pct=round(effective_risk_pct, 2),
            rr_ratio=round(rr, 2),
            scale_factor=scale_factor,
            scale_reason=scale_reason,
        )

    # ── Session-aligned daily P&L ──────────────────────────────────
    def _get_session_pnl(self) -> float:
        """
        Returns P&L since today's session start (London open, 07:00 UTC).
        This prevents the edge case where trades straddling UTC midnight
        don't count against the next day's loss limit.
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

