"""
aurum.py — AURUM AI Agent
=========================
Build order: #8 — depends on SCRIBE, HERALD, LENS.
Claude-powered conversational agent.
Accessible via Telegram bot AND ATHENA dashboard API.
SOUL.md + SKILL.md define identity and capabilities.
Writes aurum_cmd.json for BRIDGE to execute commands.
"""

import os, json, logging, asyncio, time
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic
from telethon import TelegramClient, events

from scribe import get_scribe
from herald import get_herald
from lens import Lens

log = logging.getLogger("aurum")

# ── Config ──────────────────────────────────────────────────────────
ANTHROPIC_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
BOT_TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN", "")
AURUM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")  # your personal chat
API_ID          = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH        = os.environ.get("TELEGRAM_API_HASH", "")
PHONE           = os.environ.get("TELEGRAM_PHONE", "")

CMD_FILE        = os.environ.get("AURUM_CMD_FILE",    "config/aurum_cmd.json")
STATUS_FILE     = os.environ.get("BRIDGE_STATUS_FILE","config/status.json")
MARKET_FILE     = os.environ.get("MT5_MARKET_FILE",   "MT5/market_data.json")
LENS_FILE       = os.environ.get("LENS_SNAPSHOT_FILE","config/lens_snapshot.json")
SENTINEL_FILE   = os.environ.get("SENTINEL_STATUS_FILE","config/sentinel_status.json")
SOUL_FILE       = os.environ.get("SOUL_FILE",         "SOUL.md")
SKILL_FILE      = os.environ.get("SKILL_FILE",        "SKILL.md")
SESSION_FILE    = os.environ.get("TELEGRAM_SESSION_FILE", "config/aurum_session")

MAX_TOKENS      = int(os.environ.get("AURUM_MAX_TOKENS", "1000"))
MODEL           = os.environ.get("AURUM_MODEL", "claude-sonnet-4-6")

Path("config").mkdir(parents=True, exist_ok=True)


def _read_file(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except:
        return ""

def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}


class Aurum:
    def __init__(self):
        self.scribe  = get_scribe()
        self.herald  = get_herald()
        self.claude  = Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None
        self._soul   = _read_file(SOUL_FILE)
        self._skill  = _read_file(SKILL_FILE)
        self._mode   = "SIGNAL"
        if not self.claude:
            log.warning("AURUM: ANTHROPIC_API_KEY not set")
        log.info("AURUM initialised")

    def set_mode(self, mode: str):
        self._mode = mode

    # ── Core query handler ─────────────────────────────────────────
    def ask(self, query: str, source: str = "TELEGRAM") -> str:
        """
        Answer a query. Returns response string.
        Injects last 5 conversations from SCRIBE for continuity.
        """
        if not self.claude:
            return "AURUM: Claude API not configured. Set ANTHROPIC_API_KEY in .env"

        context  = self._build_context()
        memory   = self._build_memory()
        system   = self._build_system_prompt(context, memory)

        try:
            resp = self.claude.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": query}],
            )
            answer = resp.content[0].text.strip()
            tokens = resp.usage.input_tokens + resp.usage.output_tokens

            # Log to SCRIBE
            self.scribe.log_aurum_conversation(
                query=query, response=answer,
                mode=self._mode, source=source, tokens=tokens
            )

            try:
                self.scribe.heartbeat(
                    component   = "AURUM",
                    status      = "OK",
                    mode        = self._mode,
                    note        = f"tokens={tokens}",
                    last_action = f"answered: {query[:80]}",
                )
            except Exception as _he:
                log.debug(f"AURUM heartbeat error: {_he}")

            # Check if response contains a command
            self._check_for_command(answer)

            return answer

        except Exception as e:
            log.error(f"AURUM query error: {e}")
            return f"AURUM: Error — {str(e)[:100]}"

    def _build_system_prompt(self, context: str, memory: str = "") -> str:
        parts = [self._soul, self._skill, "---", "## CURRENT SYSTEM STATE (live data)", context]
        if memory:
            parts += ["---", "## RECENT CONVERSATION HISTORY (from SCRIBE)", memory]
        parts += ["---", "Always refer to this context when answering. "
                  "If data seems stale or missing, say so rather than guessing."]
        return "\n\n".join(parts)

    def _build_memory(self) -> str:
        """
        Pull last 5 conversations from SCRIBE aurum_conversations table.
        Gives AURUM continuity across sessions — it remembers what you discussed.
        """
        try:
            rows = self.scribe.query(
                """SELECT timestamp, source, query, response
                   FROM aurum_conversations
                   ORDER BY timestamp DESC
                   LIMIT 5"""
            )
        except Exception as e:
            log.warning(f"AURUM memory query failed: {e}")
            return ""

        if not rows:
            return ""

        # Reverse to chronological order for natural reading
        rows = list(reversed(rows))
        lines = []
        for r in rows:
            ts  = r.get("timestamp","")[:16]
            src = r.get("source","?")
            q   = r.get("query","")[:120]
            a   = r.get("response","")[:200]
            lines.append(f"[{ts} via {src}]\nYou: {q}\nAURUM: {a}")

        return "\n\n".join(lines)

    def _build_context(self) -> str:
        lines = []

        # Mode + time
        status   = _read_json(STATUS_FILE)
        mode     = status.get("mode", self._mode)
        session  = status.get("session", "UNKNOWN")
        lines.append(f"MODE: {mode}  SESSION: {session}")
        lines.append(f"TIME: {datetime.now(timezone.utc).strftime('%H:%M UTC')}")

        # Account from MT5
        mt5 = _read_json(MARKET_FILE)
        if mt5:
            acc = mt5.get("account", {})
            lines.append(f"\nACCOUNT (MT5 live):")
            lines.append(f"  Balance:  ${acc.get('balance',0):,.2f}")
            lines.append(f"  Equity:   ${acc.get('equity',0):,.2f}")
            lines.append(f"  Floating: ${acc.get('total_floating_pnl',0):+.2f}")
            lines.append(f"  Session P&L: ${acc.get('session_pnl',0):+.2f}")
            lines.append(f"  Open positions: {acc.get('open_positions_count',0)}")

        # Open groups from SCRIBE
        groups = self.scribe.get_open_groups()
        if groups:
            lines.append(f"\nOPEN TRADE GROUPS ({len(groups)}):")
            for g in groups[:5]:
                lines.append(
                    f"  [{g['id']}] {g['direction']} ×{g['num_trades']} "
                    f"@ {g['entry_low']:.0f}–{g['entry_high']:.0f} "
                    f"SL:{g['sl']:.0f} TP1:{g['tp1']:.0f} "
                    f"Status:{g['status']} P&L:${g.get('total_pnl',0) or 0:.2f}"
                )

        # LENS
        lens = _read_json(LENS_FILE)
        if lens:
            lines.append(f"\nLENS (TradingView {lens.get('timeframe','?')}):")
            lines.append(f"  Price: ${lens.get('price',0):.2f}")
            lines.append(f"  RSI: {lens.get('rsi',0):.1f}  "
                         f"MACD hist: {lens.get('macd_hist',0):+.5f}  "
                         f"BB rating: {lens.get('bb_rating',0):+d}  "
                         f"ADX: {lens.get('adx',0):.1f}")
            lines.append(f"  Age: {lens.get('age_seconds',0):.0f}s")

        # Sentinel
        sent = _read_json(SENTINEL_FILE)
        if sent:
            active = sent.get("active", False)
            lines.append(f"\nSENTINEL: {'⚠ ACTIVE — TRADING PAUSED' if active else 'Clear'}")
            if sent.get("next_event"):
                lines.append(
                    f"  Next: {sent['next_event']} in {sent.get('next_in_min','?')}min "
                    f"({sent.get('next_time','?')})"
                )

        # Performance
        perf = self.scribe.get_performance(days=1)
        lines.append(f"\nTODAY:")
        lines.append(f"  P&L: ${perf.get('total_pnl',0):+.2f}  "
                     f"Trades: {perf.get('total',0)}  "
                     f"Win rate: {perf.get('win_rate',0):.0f}%  "
                     f"Avg pips: {perf.get('avg_pips',0):+.1f}")

        return "\n".join(lines)

    def _check_for_command(self, response: str):
        """Check if AURUM's response contains a system command to execute."""
        resp_lower = response.lower()
        cmd = None

        if "switching to watch" in resp_lower or "mode → watch" in resp_lower:
            cmd = {"action": "MODE_CHANGE", "new_mode": "WATCH", "reason": "AURUM"}
        elif "switching to hybrid" in resp_lower or "mode → hybrid" in resp_lower:
            cmd = {"action": "MODE_CHANGE", "new_mode": "HYBRID", "reason": "AURUM"}
        elif "switching to signal" in resp_lower or "mode → signal" in resp_lower:
            cmd = {"action": "MODE_CHANGE", "new_mode": "SIGNAL", "reason": "AURUM"}
        elif "switching to scalper" in resp_lower or "mode → scalper" in resp_lower:
            cmd = {"action": "MODE_CHANGE", "new_mode": "SCALPER", "reason": "AURUM"}

        if cmd:
            cmd["timestamp"] = datetime.now(timezone.utc).isoformat()
            self.write_command(cmd)
            log.info(f"AURUM wrote command: {cmd}")

    def write_command(self, cmd: dict):
        """Write a command for BRIDGE to execute."""
        cmd["timestamp"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(CMD_FILE, "w") as f:
                json.dump(cmd, f, indent=2)
        except Exception as e:
            log.error(f"AURUM write command error: {e}")

    # ── Telegram bot handler ───────────────────────────────────────
    async def start_telegram(self):
        """Start Telegram bot that listens for messages in your personal chat."""
        if not all([API_ID, API_HASH]):
            log.warning("AURUM: Telegram not configured")
            return

        client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        await client.start(phone=PHONE)

        @client.on(events.NewMessage(from_users=int(AURUM_CHAT_ID) if AURUM_CHAT_ID else None))
        async def on_message(event):
            text = event.message.message or ""
            if not text.strip() or text.startswith("/system"):
                return
            log.info(f"AURUM query from Telegram: {text[:60]}")
            reply = self.ask(text, source="TELEGRAM")
            await event.respond(reply)

        log.info("AURUM Telegram bot listening")
        await client.run_until_disconnected()

    # ── Flask API endpoint (called by ATHENA) ─────────────────────
    def flask_ask(self, query: str) -> dict:
        """Used by athena_api.py for the dashboard chat panel."""
        response = self.ask(query, source="ATHENA")
        return {"response": response, "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Singleton ─────────────────────────────────────────────────────
_instance: Aurum = None

def get_aurum() -> Aurum:
    global _instance
    if _instance is None:
        _instance = Aurum()
    return _instance


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    a = Aurum()
    if "--telegram" in sys.argv:
        asyncio.run(a.start_telegram())
    else:
        # Interactive test
        print("AURUM interactive test (type 'quit' to exit)")
        while True:
            q = input("\nYou: ").strip()
            if q.lower() in ("quit","exit","q"):
                break
            print(f"\nAURUM: {a.ask(q, source='TEST')}")
