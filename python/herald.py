"""
herald.py — HERALD Telegram Notification Service
=================================================
Build order: #3 — depends only on .env (bot token).
Send-only bot. Other components call herald.send() for alerts.
"""

import os, logging, asyncio, tempfile, html, json
from datetime import datetime, timezone

from status_report import report_component_status
from trading_session import get_trading_session_utc

log = logging.getLogger("herald")


def telegram_group_label(group_id: int | str | None) -> str:
    """Human-readable trade group reference for Telegram only (not ATHENA / DB)."""
    if group_id is None:
        return "Group ?"
    try:
        return f"Group {int(group_id)}"
    except (TypeError, ValueError):
        return "Group ?"


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

    @staticmethod
    def _fmt_value(v) -> str:
        if v is None:
            return "n/a"
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)

    def _render_alert_template(self, alert_type: str, payload: dict | None = None) -> str:
        p = payload or {}
        t = (alert_type or "GENERIC_ALERT").upper()
        if t == "MCP_RESULT_CAPTURED":
            return (
                "📡 <b>MCP RESULT CAPTURED</b>\n"
                f"Tool: <code>{html.escape(self._fmt_value(p.get('tool')))}</code>\n"
                f"Freshness: <b>{html.escape(self._fmt_value(p.get('freshness')))}</b>\n"
                f"Timestamp: <code>{html.escape(self._fmt_value(p.get('timestamp')))}</code>\n"
                f"Summary: {html.escape(self._fmt_value(p.get('summary')))}"
            )
        if t == "MCP_RESULT_MISSING":
            return (
                "⚠️ <b>MCP RESULT MISSING</b>\n"
                f"Tool: <code>{html.escape(self._fmt_value(p.get('tool')))}</code>\n"
                f"Reason: {html.escape(self._fmt_value(p.get('reason')))}"
            )
        if t == "MCP_CALL_FAILED":
            return (
                "❌ <b>MCP CALL FAILED</b>\n"
                f"Tool: <code>{html.escape(self._fmt_value(p.get('tool')))}</code>\n"
                f"Error: {html.escape(self._fmt_value(p.get('error')))}"
            )
        if t == "WEBHOOK_ALERT_READY":
            return (
                "🔔 <b>WEBHOOK ALERT READY</b>\n"
                f"Type: <code>{html.escape(self._fmt_value(p.get('alert_kind')))}</code>\n"
                f"Instrument: <code>{html.escape(self._fmt_value(p.get('instrument')))}</code>\n"
                f"Timeframe: <code>{html.escape(self._fmt_value(p.get('timeframe')))}</code>\n"
                f"Condition: {html.escape(self._fmt_value(p.get('condition')))}"
            )
        if t == "WEBHOOK_ALERT_SENT":
            return (
                "✅ <b>WEBHOOK ALERT SENT</b>\n"
                f"Type: <code>{html.escape(self._fmt_value(p.get('alert_kind')))}</code>\n"
                f"Delivery: <code>{html.escape(self._fmt_value(p.get('delivery')))}</code>\n"
                f"Notes: {html.escape(self._fmt_value(p.get('notes')))}"
            )
        if t == "WEBHOOK_ALERT_FAILED":
            return (
                "🚨 <b>WEBHOOK ALERT FAILED</b>\n"
                f"Type: <code>{html.escape(self._fmt_value(p.get('alert_kind')))}</code>\n"
                f"Failure: {html.escape(self._fmt_value(p.get('failure')))}\n"
                f"Retryable: <b>{html.escape(self._fmt_value(p.get('retryable')))}</b>"
            )
        return (
            "ℹ️ <b>SYSTEM ALERT</b>\n"
            f"Type: <code>{html.escape(t)}</code>\n"
            f"Payload: {html.escape(json.dumps(p, default=str)[:1000])}"
        )

    def send_alert(self, alert_type: str, payload: dict | None = None) -> bool:
        msg = self._render_alert_template(alert_type, payload)
        return self.send(msg)

    def send(self, text: str, parse_mode: str = "HTML") -> bool:
        """Sync wrapper — safe to call from anywhere."""
        if not self.token or not self.chat_id:
            log.warning(f"HERALD (no token): {text[:60]}")
            return False
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop in this thread — safe to run synchronously.
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

            # Running inside an event loop (e.g., AURUM Bot API handlers).
            # Schedule send asynchronously and return immediately.
            loop.create_task(self._async_send(text, parse_mode))
            try:
                report_component_status(
                    "HERALD",
                    "OK",
                    note="bot active" if self.token else "no token configured",
                    last_action=f"queued-send: {text[:80]}",
                )
            except Exception as _he:
                log.debug(f"HERALD heartbeat error: {_he}")
            return True
        except Exception as e:
            self._bot = None
            log.error(f"HERALD send error: {e}")
            return False

    async def _async_send(self, text: str, parse_mode: str, chat_id: str | int | None = None) -> bool:
        bot = self._get_bot()
        if not bot:
            return False
        await bot.send_message(
            chat_id=chat_id if chat_id not in (None, "") else self.chat_id,
            text=text,
            parse_mode=parse_mode,
        )
        return True

    # ── Reusable post helpers (Deferred Analysis Run subsystem) ───
    def post_text(self, text: str, *, chat_id: str | int | None = None,
                  parse_mode: str = "HTML") -> bool:
        """Reusable thin wrapper over send/_async_send with optional chat_id
        override. Default chat target is ``self.chat_id`` (existing channel).
        Never hard-codes a chat id.
        """
        if not self.token:
            log.warning(f"HERALD (no token): {text[:60]}")
            return False
        target_chat = chat_id if chat_id not in (None, "") else self.chat_id
        if not target_chat:
            log.warning("HERALD post_text: no chat_id available")
            return False
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                result = asyncio.run(self._async_send(text, parse_mode, target_chat))
                self._bot = None
                return result
            loop.create_task(self._async_send(text, parse_mode, target_chat))
            return True
        except Exception as e:
            self._bot = None
            log.error(f"HERALD post_text error: {e}")
            return False

    def post_analysis_from_log(self, query_id: str, *, header: str | None = None,
                               footer: str | None = None,
                               chat_id: str | int | None = None,
                               max_chars: int = 3500) -> bool:
        """Read ``logs/analysis/<query_id>.md`` and post it to the existing
        Telegram channel (Herald singleton, BOT_TOKEN/CHAT_ID). Reusable by
        any module that wants to surface an analysis result by query id.
        """
        log_dir_raw = (os.environ.get("ANALYSIS_LOG_DIR") or "").strip()
        if log_dir_raw:
            log_dir = log_dir_raw
        else:
            here = os.path.dirname(os.path.abspath(__file__))
            log_dir = os.path.normpath(os.path.join(here, "..", "logs", "analysis"))
        body_path = os.path.join(log_dir, f"{query_id}.md")
        if not os.path.exists(body_path):
            log.warning("HERALD post_analysis_from_log: missing %s", body_path)
            return False
        try:
            with open(body_path, "r", encoding="utf-8") as f:
                body = f.read()
        except Exception as e:
            log.warning("HERALD post_analysis_from_log: read failed for %s: %s", body_path, e)
            return False

        body = body.strip()
        truncated = False
        if len(body) > max_chars:
            body = body[: max_chars - 64].rstrip()
            truncated = True
            body += f"\n…(truncated, see logs/analysis/{query_id}.md)"

        parts = []
        if header:
            parts.append(str(header))
        parts.append(f"<b>Analysis</b> <code>{html.escape(str(query_id))}</code>")
        parts.append("<pre>" + html.escape(body) + "</pre>")
        if footer:
            parts.append(str(footer))
        if truncated:
            parts.append(f"<i>truncated · full file: logs/analysis/{html.escape(str(query_id))}.md</i>")
        message = "\n".join(parts)
        return self.post_text(message, chat_id=chat_id, parse_mode="HTML")

    async def download_inbound_media(self, message, prefix: str = "herald_img_") -> str | None:
        """Download Telegram photo/document to a temp file and return the local path."""
        try:
            if not message:
                return None
            media_obj = None
            photo = getattr(message, "photo", None)
            document = getattr(message, "document", None)
            effective = getattr(message, "effective_attachment", None)
            if photo:
                media_obj = photo[-1]
            elif document:
                media_obj = document
            elif isinstance(effective, (list, tuple)) and effective:
                media_obj = effective[-1]
            elif effective:
                media_obj = effective
            if media_obj is None:
                return None
            tg_file = None
            if hasattr(media_obj, "get_file"):
                tg_file = await media_obj.get_file()
            else:
                file_id = getattr(media_obj, "file_id", None)
                bot = None
                try:
                    bot = message.get_bot()
                except Exception:
                    bot = None
                if file_id and bot:
                    tg_file = await bot.get_file(file_id)
            if tg_file is None:
                return None
            with tempfile.NamedTemporaryFile(prefix=prefix, suffix=".img", delete=False) as tmp:
                image_path = tmp.name
            if hasattr(tg_file, "download_to_drive"):
                await tg_file.download_to_drive(custom_path=image_path)
            else:
                await tg_file.download(custom_path=image_path)
            return image_path
        except Exception as e:
            log.warning("HERALD media download failed: %s", e)
            return None

    # ── Pre-built message templates ──────────────────────────────
    @staticmethod
    def _trade_group_open_head_label(group: dict) -> str:
        """Short label after FORGE (matches native: FORGE SCALP BB_BOUNCE -- …)."""
        src = str(group.get("source") or "").strip().upper()
        if src == "SIGNAL":
            return "SIGNAL"
        if src == "SCALPER_SUBPATH_DIRECT":
            return "SCALPER"
        if src == "AURUM":
            return "AURUM"
        if src == "FORGE_NATIVE_SCALP":
            return "SCALP"
        return html.escape(str(group.get("source") or "OPEN"))

    def trade_group_opened(self, group: dict):
        d = group.get("direction", "?")
        d_h = html.escape(str(d))
        try:
            gid_int = int(group.get("id"))
        except (TypeError, ValueError):
            gid_int = 0
        label = self._trade_group_open_head_label(group)
        n = int(group.get("num_trades") or 0)
        el = float(group.get("entry_low") or 0)
        eh = float(group.get("entry_high") or 0)
        sl = float(group.get("sl") or 0)
        tp1 = float(group.get("tp1") or 0)
        tp2_raw = group.get("tp2")
        tp3_raw = group.get("tp3")
        try:
            tp2_f = float(tp2_raw) if tp2_raw not in (None, "", "?") else 0.0
        except (TypeError, ValueError):
            tp2_f = 0.0
        try:
            tp3_f = float(tp3_raw) if tp3_raw not in (None, "", "?", "OPEN") else 0.0
        except (TypeError, ValueError):
            tp3_f = 0.0
        lot = float(group.get("lot_per_trade") or 0)
        emoji = "\U0001f7e2" if d == "BUY" else "\U0001f534"
        tp2_seg = f" TP2: <code>{tp2_raw}</code>" if tp2_f > 0 else ""
        tp3_seg = f" TP3: <code>{tp3_raw}</code>" if tp3_f > 0 else ""
        entry_seg = ""
        if el > 0 and eh > 0:
            entry_seg = f"Entry: <code>{el:.2f}\u2013{eh:.2f}</code>\n"
        self.send(
            f"{emoji} <b>FORGE {label}</b> -- {telegram_group_label(gid_int)} {d_h}\n"
            f"SL: <code>{sl:.2f}</code> TP1: <code>{tp1:.2f}</code>{tp2_seg}{tp3_seg}\n"
            f"{entry_seg}"
            f"{n} x {lot} lot"
        )

    def trade_group_closed(self, group_id: int, direction: str, trades: int,
                           total_pnl: float, pips: float, reason: str):
        emoji = "✅" if total_pnl >= 0 else "❌"
        reason_h = html.escape(str(reason))
        dir_h = html.escape(str(direction))
        self.send(
            f"{emoji} <b>GROUP CLOSED</b> — {telegram_group_label(group_id)} {dir_h}\n"
            f"💰 P&L: <code>${total_pnl:+.2f}</code>  Pips: {pips:+.1f}\n"
            f"📦 {trades} trades closed\n"
            f"📌 Outcome: <code>{reason_h}</code>"
        )

    def position_closed(self, ticket: int, direction: str, pnl: float, pips: float,
                        *, group_id: int | None = None,
                        outcome: str = "SL HIT"):
        """Per-leg close (typically stop loss). ``outcome`` is shown as the title e.g. SL HIT."""
        emoji = "💔" if pnl < 0 else "💚"
        g_part = f" {telegram_group_label(group_id)}" if group_id is not None else ""
        title = html.escape(str(outcome or "CLOSED"))
        dir_h = html.escape(str(direction))
        self.send(
            f"{emoji} <b>{title}</b> —{g_part} #{ticket} {dir_h}\n"
            f"P&L: <code>${pnl:+.2f}</code>  Pips: {pips:+.1f}"
        )

    def tp_hit(self, group_id: str, tp_stage: int, closed_n: int,
               remaining_n: int, pips: float, pnl: float, be_moved: bool,
               *, direction: str | None = None):
        dir_part = f" {html.escape(direction)}" if direction else ""
        self.send(
            f"✅ <b>TP{tp_stage} HIT</b> — {telegram_group_label(group_id)}{dir_part}\n"
            f"Closed {closed_n} leg(s)  P&L: <code>${pnl:+.2f}</code>  +{pips:.1f} pips\n"
            f"Remaining: {remaining_n} leg(s)"
            + ("  · SL → BE" if be_moved else "")
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

    def signal_skipped(
        self,
        direction: str,
        reason: str,
        entry: str,
        *,
        gate_summary: str | None = None,
    ):
        msg = (
            f"⏭ Signal skipped — {direction} @ {entry}\n"
            f"Reason: {reason}"
        )
        if gate_summary:
            msg += f"\n<code>{html.escape(gate_summary)}</code>"
        self.send(msg)

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


# ── Module-level reusable shims (use the singleton) ───────────────
def post_text(text: str, *, chat_id: str | int | None = None,
              parse_mode: str = "HTML") -> bool:
    """Module-level shim — reuses the existing Herald singleton."""
    return get_herald().post_text(text, chat_id=chat_id, parse_mode=parse_mode)


def post_analysis_from_log(query_id: str, *, header: str | None = None,
                           footer: str | None = None,
                           chat_id: str | int | None = None,
                           max_chars: int = 3500) -> bool:
    """Module-level shim — reuses the existing Herald singleton.
    Default chat target is the singleton's ``chat_id`` (existing channel).
    """
    return get_herald().post_analysis_from_log(
        query_id,
        header=header,
        footer=footer,
        chat_id=chat_id,
        max_chars=max_chars,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    h = Herald()
    print("HERALD initialised. Token set:", bool(h.token))
    if h.token:
        h.send("🧪 HERALD test message from Signal System")
        print("Test message sent")
