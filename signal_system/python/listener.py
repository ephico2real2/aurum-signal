"""
listener.py — LISTENER Telegram Signal Reader & AI Parser
==========================================================
Build order: #7 — depends on SCRIBE, HERALD.
Monitors Telegram signal channels via Telethon (user account).
Parses every message with Claude API — no brittle regex.
Writes parsed_signal.json and management_cmd.json for BRIDGE.
"""

import os, json, logging, asyncio
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic
from telethon import TelegramClient, events

from scribe import get_scribe
from herald import get_herald

log = logging.getLogger("listener")

# ── Config ─────────────────────────────────────────────────────────
API_ID       = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH     = os.environ.get("TELEGRAM_API_HASH", "")
PHONE        = os.environ.get("TELEGRAM_PHONE", "")
CHANNELS     = [c.strip() for c in os.environ.get("TELEGRAM_CHANNELS", "").split(",") if c.strip()]
ANTHROPIC_KEY= os.environ.get("ANTHROPIC_API_KEY", "")

SIGNAL_FILE  = os.environ.get("LISTENER_SIGNAL_FILE", "config/parsed_signal.json")
MGMT_FILE    = os.environ.get("LISTENER_MGMT_FILE",   "config/management_cmd.json")
SESSION_FILE = "config/telegram_session"

Path("config").mkdir(parents=True, exist_ok=True)

# ── Claude parser prompt ────────────────────────────────────────────
PARSE_PROMPT = """You are a gold trading signal parser. Extract structured data from Telegram messages.

Return ONLY a JSON object. No explanation, no markdown, no backticks.

For ENTRY signals, return:
{
  "type": "ENTRY",
  "direction": "BUY" or "SELL",
  "entry_low": number (lowest price in entry zone),
  "entry_high": number (highest price, same as entry_low if single price),
  "sl": number (stop loss),
  "tp1": number or null,
  "tp2": number or null,
  "tp3": number or null,
  "tp3_open": true if TP3 is "open" or not specified
}

For MANAGEMENT messages (close, breakeven, TP hit updates), return:
{
  "type": "MANAGEMENT",
  "intent": "CLOSE_ALL" | "MOVE_BE" | "CLOSE_PCT" | "TP_HIT" | "HOLD" | "UPDATE",
  "pct": number or null (e.g. 70 for "close 70%"),
  "tp_stage": 1 or 2 or 3 or null
}

For unrecognised messages, return:
{"type": "IGNORE"}

Rules:
- Entry zone: "@ 3180-3185" → entry_low=3180, entry_high=3185
- Single entry: "@ 3180" → entry_low=3180, entry_high=3180
- "TP3: Open" → tp3_open=true, tp3=null
- "Close all" / "close now" → CLOSE_ALL
- "Move to BE" / "breakeven" → MOVE_BE
- "Secure 70%" / "close 70%" → CLOSE_PCT with pct=70
- "TP1 hit" / "TP1 done" → TP_HIT with tp_stage=1
- Currency must be gold/XAUUSD — ignore other instruments"""


class Listener:
    def __init__(self):
        self.scribe  = get_scribe()
        self.herald  = get_herald()
        self.claude  = Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None
        self._mode   = "SIGNAL"   # set by BRIDGE via set_mode()
        self._last_signal_id: set = set()   # dedup
        if not self.claude:
            log.warning("LISTENER: ANTHROPIC_API_KEY not set — parsing disabled")
        log.info(f"LISTENER initialised — watching {len(CHANNELS)} channels")

    def set_mode(self, mode: str):
        self._mode = mode

    # ── Telegram client ────────────────────────────────────────────
    async def start(self):
        if not all([API_ID, API_HASH, PHONE]):
            log.error("LISTENER: Telegram credentials not configured")
            return

        client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        await client.start(phone=PHONE)
        log.info("LISTENER: Telegram connected")

        @client.on(events.NewMessage(chats=CHANNELS))
        async def on_message(event):
            await self._handle_message(event.message)

        @client.on(events.MessageEdited(chats=CHANNELS))
        async def on_edit(event):
            await self._handle_message(event.message, edited=True)

        await client.run_until_disconnected()

    async def _handle_message(self, msg, edited: bool = False):
        text = msg.message or ""
        if not text.strip():
            return

        # Dedup
        msg_key = (msg.id, msg.chat_id, edited)
        if msg_key in self._last_signal_id:
            return
        self._last_signal_id.add(msg_key)
        if len(self._last_signal_id) > 1000:
            self._last_signal_id = set(list(self._last_signal_id)[-500:])

        channel = getattr(msg.chat, "title", str(msg.chat_id)) if msg.chat else "unknown"
        log.info(f"LISTENER [{channel}]: {text[:80]}")

        # Parse
        parsed = await self._parse(text)
        if not parsed or parsed.get("type") == "IGNORE":
            return

        # Log to SCRIBE regardless of mode
        signal_id = self.scribe.log_signal(
            raw=text, parsed=parsed, mode=self._mode,
            channel=channel, msg_id=msg.id
        )

        # In WATCH/OFF — log only
        if self._mode in ("OFF", "WATCH"):
            self.scribe.update_signal_action(signal_id, "LOGGED_ONLY")
            log.info(f"LISTENER [{self._mode}]: logged signal, not dispatching")
            try:
                from scribe import get_scribe
                get_scribe().heartbeat(
                    component   = "LISTENER",
                    status      = "OK",
                    mode        = self._mode,
                    note        = f"monitoring {len(CHANNELS)} channels",
                    last_action = f"[{self._mode}] received msg from {channel}",
                )
            except Exception as _he:
                log.debug(f"LISTENER heartbeat error: {_he}")
            return

        # Dispatch
        if parsed["type"] == "ENTRY":
            parsed["signal_id"]  = signal_id
            parsed["channel"]    = channel
            parsed["timestamp"]  = datetime.now(timezone.utc).isoformat()
            parsed["edited"]     = edited
            self._write_signal(parsed)
            log.info(f"LISTENER → parsed_signal.json: {parsed.get('direction')} "
                     f"@ {parsed.get('entry_low')}–{parsed.get('entry_high')}")
            try:
                from scribe import get_scribe
                get_scribe().heartbeat(
                    component   = "LISTENER",
                    status      = "OK",
                    mode        = self._mode,
                    note        = f"monitoring {len(CHANNELS)} channels",
                    last_action = f"parsed {parsed.get('type','?')} {parsed.get('direction','')} from {channel}",
                )
            except Exception as _he:
                log.debug(f"LISTENER heartbeat error: {_he}")

        elif parsed["type"] == "MANAGEMENT":
            parsed["signal_id"]  = signal_id
            parsed["timestamp"]  = datetime.now(timezone.utc).isoformat()
            self._write_mgmt(parsed)
            log.info(f"LISTENER → management_cmd.json: {parsed.get('intent')}")

    async def _parse(self, text: str) -> dict | None:
        if not self.claude:
            return self._fallback_parse(text)
        try:
            resp = self.claude.messages.create(
                model="claude-haiku-4-5-20251001",   # fast + cheap for parsing
                max_tokens=256,
                messages=[
                    {"role": "user",
                     "content": f"{PARSE_PROMPT}\n\nMessage:\n{text}"}
                ]
            )
            raw = resp.content[0].text.strip()
            raw = raw.replace("```json","").replace("```","").strip()
            return json.loads(raw)
        except json.JSONDecodeError as e:
            log.warning(f"LISTENER parse JSON error: {e}")
            return {"type": "IGNORE"}
        except Exception as e:
            log.error(f"LISTENER Claude error: {e}")
            return self._fallback_parse(text)

    def _fallback_parse(self, text: str) -> dict:
        """Minimal regex fallback if Claude API unavailable."""
        import re
        text_l = text.lower()
        if any(w in text_l for w in ["close all","close now","exit all"]):
            return {"type":"MANAGEMENT","intent":"CLOSE_ALL","pct":None,"tp_stage":None}
        if any(w in text_l for w in ["breakeven","move sl to be","move to be"]):
            return {"type":"MANAGEMENT","intent":"MOVE_BE","pct":None,"tp_stage":None}
        # Entry signal
        direction = None
        if re.search(r'\bbuy\b', text_l): direction = "BUY"
        elif re.search(r'\bsell\b', text_l): direction = "SELL"
        if not direction:
            return {"type":"IGNORE"}
        # Find prices
        prices = re.findall(r'\b(\d{4,5}(?:\.\d{1,2})?)\b', text)
        prices = [float(p) for p in prices]
        if len(prices) < 2:
            return {"type":"IGNORE"}
        return {
            "type": "ENTRY",
            "direction": direction,
            "entry_low": min(prices[:2]),
            "entry_high": max(prices[:2]),
            "sl": prices[2] if len(prices) > 2 else None,
            "tp1": prices[3] if len(prices) > 3 else None,
            "tp2": prices[4] if len(prices) > 4 else None,
            "tp3": None, "tp3_open": True,
        }

    def _write_signal(self, data: dict):
        try:
            with open(SIGNAL_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.error(f"LISTENER write signal error: {e}")

    def _write_mgmt(self, data: dict):
        try:
            with open(MGMT_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.error(f"LISTENER write mgmt error: {e}")

    # ── Test parse (no Telegram needed) ───────────────────────────
    async def test_parse(self, message: str) -> dict:
        return await self._parse(message)


def run():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    l = Listener()
    asyncio.run(l.start())


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        # Test parser without Telegram
        import asyncio
        test_msgs = [
            "Buy Gold now\n@ 4605.00 - 4601.00\nStoploss: 4596.00\nTake Profit 1: 4607.00\nTake Profit 2: 4609.00\nTake Profit 3: Open",
            "Gold melting RUNNING +90PIPS PROFITS & hit TP2!!\nClose all for scalpers. Others only hold few highest layers with Breakeven!",
            "DONE HIT TP 1 ✅✅\nLet's secure 70% profit. Hold 30%\nStick to breakeven+ okay?",
        ]
        l = Listener()
        for msg in test_msgs:
            result = asyncio.run(l.test_parse(msg))
            print(f"\nInput: {msg[:60]}...")
            print(f"Parsed: {json.dumps(result, indent=2)}")
    else:
        run()
