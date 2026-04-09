"""
herald.py — HERALD Telegram Notification Service
=================================================
Build order: #3 — depends only on .env (bot token).
Send-only bot. Other components call herald.send() for alerts.
"""

import os, logging, asyncio
from datetime import datetime, timezone

from status_report import report_component_status
from trading_session import get_trading_session_utc

log = logging.getLogger("herald")

BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID", "")


class Herald:
    def __init__(self, token: str = BOT_TOKEN, chat_id: str = CHAT_ID):
        self.token   = token
        self.chat_id = chat_id
        self._bot    = None
        if not token:
            log.warning("HERALD: TELEGRAM_BOT_TOKEN not set — notifications disabled")

    def _get_bot(self):
        if self._bot is None and self.token:
            from telegram import Bot
            self._bot = Bot(token=self.token)
        return self._bot

    def send(self, text: str, parse_mode: str = "HTML") -> bool:
        """Sync wrapper — safe to call from anywhere."""
        if not self.token or not self.chat_id:
            log.warning(f"HERALD (no token): {text[:60]}")
            return False
        try:
            result = asyncio.run(self._async_send(text, parse_mode))
            self._bot = None
            try:
                report_component_status(
                    "HERALD",
                    "OK" if result else "WARN",
                    note="bot active" if self.token else "no token configured",
                    last_action=f"sent: {text[:80]}",
                )
            except Exception as _he:
                log.debug(f"HERALD heartbeat error: {_he}")
            return result
        except Exception as e:
            self._bot = None
            log.error(f"HERALD send error: {e}")
            return False

    async def _async_send(self, text: str, parse_mode: str) -> bool:
        bot = self._get_bot()
        if not bot:
            return False
        await bot.send_message(
            chat_id=self.chat_id,
            text=text,
            parse_mode=parse_mode,
        )
        return True

    # ── Pre-built message templates ──────────────────────────────
    def trade_group_opened(self, group: dict):
        d   = group.get("direction","?")
        n   = group.get("num_trades",8)
        el  = group.get("entry_low",0)
        eh  = group.get("entry_high",0)
        sl  = group.get("sl",0)
        tp1 = group.get("tp1",0)
        tp2 = group.get("tp2","?")
        tp3 = group.get("tp3","OPEN")
        lot = group.get("lot_per_trade",0)
        emoji = "🟢" if d=="BUY" else "🔴"
        self.send(
            f"{emoji} <b>GROUP OPENED</b> — {d} ×{n}\n"
            f"📍 Entry: <code>{el:.2f}–{eh:.2f}</code>\n"
            f"🛑 SL: <code>{sl:.2f}</code>\n"
            f"🎯 TP1: <code>{tp1:.2f}</code>  TP2: <code>{tp2}</code>  TP3: <code>{tp3}</code>\n"
            f"📦 {n} trades × {lot} lot"
        )

    def trade_group_closed(self, group_id: int, direction: str, trades: int,
                           total_pnl: float, pips: float, reason: str):
        emoji = "✅" if total_pnl >= 0 else "❌"
        self.send(
            f"{emoji} <b>GROUP CLOSED</b> — G{group_id} {direction}\n"
            f"💰 P&L: <code>${total_pnl:+.2f}</code>  Pips: {pips:+.1f}\n"
            f"📦 {trades} trades closed\n"
            f"Reason: {reason}"
        )

    def position_closed(self, ticket: int, direction: str, pnl: float, pips: float):
        emoji = "💚" if pnl >= 0 else "💔"
        self.send(
            f"{emoji} Position #{ticket} {direction} closed\n"
            f"P&L: ${pnl:+.2f}  Pips: {pips:+.1f}"
        )

    def tp_hit(self, group_id: str, tp_stage: int, closed_n: int,
               remaining_n: int, pips: float, pnl: float, be_moved: bool):
        self.send(
            f"✅ <b>TP{tp_stage} HIT</b> — Group {group_id}\n"
            f"Closed {closed_n} trades  +{pips:.1f} pips  +${pnl:.2f}\n"
            f"Holding {remaining_n} trades"
            + ("  ✓ SL → Breakeven" if be_moved else "")
        )

    def news_guard_on(self, event: str, minutes: int, prev_mode: str,
                      extended: bool = False, post_guard_min: int = 5):
        if extended:
            self.send(
                f"🔴 <b>NEWS GUARD ACTIVE [EXTENDED]</b>\n"
                f"📰 {event} in {minutes} min\n"
                f"⏳ Guard holds <b>{post_guard_min}min</b> after start (speech/presser)\n"
                f"Trading paused — Mode: {prev_mode} → WATCH"
            )
        else:
            self.send(
                f"⚠️ <b>NEWS GUARD ACTIVE</b>\n"
                f"📰 {event} in {minutes} min\n"
                f"Trading paused — Mode: {prev_mode} → WATCH"
            )

    def news_guard_off(self, event: str, mode_restored: str,
                       extended: bool = False):
        tag = " [EXTENDED]" if extended else ""
        self.send(
            f"✅ <b>NEWS GUARD LIFTED</b>{tag}\n"
            f"📰 {event} passed\n"
            f"Resuming → {mode_restored}"
        )

    def mode_changed(self, prev: str, new: str, by: str):
        self.send(
            f"⚙️ <b>MODE CHANGED</b>\n"
            f"{prev} → <b>{new}</b>  (by {by})"
        )

    def signal_skipped(self, direction: str, reason: str, entry: str):
        self.send(
            f"⏭ Signal skipped — {direction} @ {entry}\n"
            f"Reason: {reason}"
        )

    def upcoming_events(self, events: list, guard_active: bool):
        if not events:
            self.send("📅 <b>SENTINEL</b> — No high-impact events upcoming")
            return
        lines = ["📅 <b>SENTINEL — Upcoming Events</b>"]
        if guard_active:
            lines.append("⚠️ NEWS GUARD ACTIVE — trading paused")
        for e in events[:5]:
            icon = "🔴" if e.get("impact") == "HIGH" else "🟡"
            lines.append(
                f"{icon} {e.get('name','?')} ({e.get('currency','?')}) "
                f"in {e.get('minutes_away','?')}min — {e.get('time_str','?')}")
        self.send("\n".join(lines))

    def daily_summary(self, stats: dict):
        self.send(
            f"📊 <b>DAILY SUMMARY</b>\n"
            f"P&L: ${stats.get('total_pnl',0):+.2f}\n"
            f"Trades: {stats.get('total',0)}  "
            f"Win rate: {stats.get('win_rate',0):.1f}%\n"
            f"Avg pips: {stats.get('avg_pips',0):+.1f}\n"
            f"Signals recv: {stats.get('signals',0)}  "
            f"Skipped: {stats.get('skipped',0)}"
        )

    def error(self, component: str, msg: str):
        self.send(f"🚨 <b>{component} ERROR</b>\n{msg}")

    def system_start(self, mode: str, version: str = "1.0", restored: bool = False):
        tag = " (restored)" if restored else ""
        self.send(
            f"🚀 <b>SIGNAL SYSTEM STARTED</b>\n"
            f"Version: {version}  Mode: <b>{mode}</b>{tag}\n"
            f"Time: {datetime.now(timezone.utc).strftime('%H:%M UTC')}  "
            f"Kill zone: <b>{get_trading_session_utc()}</b>"
        )


# ── Singleton ─────────────────────────────────────────────────────
_instance: Herald = None

def get_herald() -> Herald:
    global _instance
    if _instance is None:
        _instance = Herald()
    return _instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    h = Herald()
    print("HERALD initialised. Token set:", bool(h.token))
    if h.token:
        h.send("🧪 HERALD test message from Signal System")
        print("Test message sent")
