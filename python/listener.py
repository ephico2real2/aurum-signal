"""
listener.py — LISTENER Telegram Signal Reader & AI Parser
==========================================================
Build order: #7 — depends on SCRIBE, HERALD.
Monitors Telegram signal channels via Telethon (user account).
Parses every message with Claude API — no brittle regex.
Writes parsed_signal.json and management_cmd.json for BRIDGE.
"""

import os, json, logging, asyncio, tempfile, shutil, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path

import httpx
from anthropic import Anthropic
from telethon import TelegramClient, events

from scribe import get_scribe
from herald import get_herald
from status_report import report_component_status
from vision import Vision
from config_io import atomic_write_json

log = logging.getLogger("listener")


def _positive_number(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out <= 0:
        return None
    return out


def _validate_signal_ranges(parsed: dict) -> list[str]:
    """Validate post-parse signal geometry before LISTENER dispatches it."""
    if not isinstance(parsed, dict) or parsed.get("type") != "ENTRY":
        return []

    errors: list[str] = []
    entry_low = _positive_number(parsed.get("entry_low"))
    entry_high = _positive_number(parsed.get("entry_high"))
    sl = _positive_number(parsed.get("sl"))
    tp1_raw = parsed.get("tp1")
    tp1 = _positive_number(tp1_raw) if tp1_raw not in (None, "") else None

    if entry_low is None:
        errors.append("entry_low must be present, numeric, and > 0")
    if entry_high is None:
        errors.append("entry_high must be present, numeric, and > 0")
    if entry_low is not None and entry_high is not None and entry_low > entry_high:
        errors.append(f"entry_low ({entry_low:g}) must be <= entry_high ({entry_high:g})")
    if sl is None:
        errors.append("sl must be present, numeric, and > 0")
    if tp1_raw not in (None, "") and tp1 is None:
        errors.append("tp1 must be numeric and > 0 when present")

    symbol = str(parsed.get("symbol") or parsed.get("instrument") or "").upper()
    if entry_low is not None and ("XAU" in symbol or "GOLD" in symbol):
        if not (1000 < entry_low < 99999):
            errors.append(f"XAU/GOLD entry_low ({entry_low:g}) must be between 1000 and 99999")

    return errors

# ── Config ─────────────────────────────────────────────────────────
API_ID       = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH     = os.environ.get("TELEGRAM_API_HASH", "")
PHONE        = os.environ.get("TELEGRAM_PHONE", "")
# Channel IDs must be integers for Telethon
_raw_channels = [c.strip() for c in os.environ.get("TELEGRAM_CHANNELS", "").split(",") if c.strip()]
CHANNELS = []
for _ch in _raw_channels:
    try:
        CHANNELS.append(int(_ch))
    except ValueError:
        CHANNELS.append(_ch)  # keep as string for username-style channels
ANTHROPIC_KEY= os.environ.get("ANTHROPIC_API_KEY", "")
VISION_ENABLED = os.environ.get("VISION_ENABLED", "true").lower() in ("1", "true", "yes")
VISION_LOW_CONFIDENCE_HOLD = os.environ.get("VISION_LOW_CONFIDENCE_HOLD", "true").lower() in ("1", "true", "yes")
LISTENER_SIGNAL_MEDIA_SUMMARY_TO_BOT = os.environ.get(
    "LISTENER_SIGNAL_MEDIA_SUMMARY_TO_BOT", "true"
).lower() in ("1", "true", "yes")
LISTENER_SIGNAL_MEDIA_ARCHIVE_ENABLED = os.environ.get(
    "LISTENER_SIGNAL_MEDIA_ARCHIVE_ENABLED", "true"
).lower() in ("1", "true", "yes")
_LISTENER_SIGNAL_MEDIA_ARCHIVE_DIR_RAW = os.environ.get(
    "LISTENER_SIGNAL_MEDIA_ARCHIVE_DIR", "data/signal_media_archive"
)
LISTENER_SIGNAL_MEDIA_ARCHIVE_DIR = (
    _LISTENER_SIGNAL_MEDIA_ARCHIVE_DIR_RAW
    if os.path.isabs(_LISTENER_SIGNAL_MEDIA_ARCHIVE_DIR_RAW)
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), _LISTENER_SIGNAL_MEDIA_ARCHIVE_DIR_RAW)
)


def _normalize_allowlist_token(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def _parse_signal_trade_rooms() -> tuple[set[str], str]:
    """
    Parse trade-room allowlist from env vars.
    Backward compatibility:
      - SIGNAL_TRADE_ROOMS (legacy/current)
      - ACTIVE_SIGNAL_TRADE_ROOMS (alias)
    If both are set, union both lists.
    """
    env_sources = (
        ("SIGNAL_TRADE_ROOMS", os.environ.get("SIGNAL_TRADE_ROOMS", "")),
        ("ACTIVE_SIGNAL_TRADE_ROOMS", os.environ.get("ACTIVE_SIGNAL_TRADE_ROOMS", "")),
    )
    rooms: set[str] = set()
    used_sources: list[str] = []
    for source_name, raw_value in env_sources:
        if not raw_value or not raw_value.strip():
            continue
        tokens = [
            _normalize_allowlist_token(token)
            for token in str(raw_value).split(",")
            if token and token.strip()
        ]
        if tokens:
            rooms.update(tokens)
            used_sources.append(source_name)
    if len(used_sources) == 2:
        source_label = "SIGNAL_TRADE_ROOMS+ACTIVE_SIGNAL_TRADE_ROOMS"
    elif len(used_sources) == 1:
        source_label = used_sources[0]
    else:
        source_label = "NONE"
    return rooms, source_label


SIGNAL_TRADE_ROOMS, SIGNAL_TRADE_ROOMS_SOURCE = _parse_signal_trade_rooms()
SIGNAL_TRADE_ROOMS_ENV_NAMES = "SIGNAL_TRADE_ROOMS/ACTIVE_SIGNAL_TRADE_ROOMS"

# How long (seconds) without any ingest before LISTENER is considered stale.
LISTENER_STALE_THRESHOLD_SEC = int(os.environ.get("LISTENER_STALE_THRESHOLD_SEC", "600"))

SIGNAL_FILE  = os.environ.get("LISTENER_SIGNAL_FILE", "config/parsed_signal.json")
MGMT_FILE    = os.environ.get("LISTENER_MGMT_FILE",   "config/management_cmd.json")
LISTENER_META_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config", "listener_meta.json"
)
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

For MANAGEMENT messages (close, breakeven, TP hit updates, SL/TP changes), return:
{
  "type": "MANAGEMENT",
  "intent": "CLOSE_ALL" | "MOVE_BE" | "CLOSE_PCT" | "TP_HIT" | "HOLD" | "UPDATE" | "MODIFY_SL" | "MODIFY_TP",
  "pct": number or null (e.g. 70 for "close 70%"),
  "tp_stage": 1 or 2 or 3 or null,
  "sl": number or null (new SL price for MODIFY_SL),
  "tp": number or null (new TP price for MODIFY_TP)
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
- "Move SL to 4660" / "SL now 4660" → MODIFY_SL with sl=4660
- "Move TP to 4680" / "TP now 4680" / "new TP 4680" → MODIFY_TP with tp=4680
- Currency must be gold/XAUUSD — ignore other instruments"""


class Listener:
    def __init__(self):
        self.scribe  = get_scribe()
        self.herald  = get_herald()
        self.claude  = Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None
        self.vision  = Vision(self.claude)
        self._mode   = "SIGNAL"   # set by BRIDGE via set_mode()
        self._last_signal_id: set = set()   # dedup
        self._last_ingest_at: datetime | None = None  # last message received timestamp
        if not self.claude:
            log.warning("LISTENER: ANTHROPIC_API_KEY not set — parsing disabled")
        if SIGNAL_TRADE_ROOMS:
            log.info(
                "LISTENER: trade-room allowlist active — %d entries from %s: %s",
                len(SIGNAL_TRADE_ROOMS),
                SIGNAL_TRADE_ROOMS_SOURCE,
                sorted(SIGNAL_TRADE_ROOMS),
            )
        else:
            log.info(
                "LISTENER: %s empty — all rooms are tradable",
                SIGNAL_TRADE_ROOMS_ENV_NAMES,
            )
        log.info(f"LISTENER initialised — watching {len(CHANNELS)} channels")

    def set_mode(self, mode: str):
        self._mode = mode

    # ── Telegram client ────────────────────────────────────────────
    async def _refresh_message_cache(self, client):
        """Periodically refresh cached messages for ATHENA API."""
        interval = int(os.environ.get("LISTENER_CACHE_REFRESH_SEC", "300"))
        while True:
            await asyncio.sleep(interval)
            try:
                recent = {}
                for ch_id in CHANNELS:
                    msgs = await client.get_messages(ch_id, limit=10)
                    recent[str(ch_id)] = [
                        {"date": str(m.date)[:19], "text": (m.message or "(media)")[:200], "id": m.id}
                        for m in msgs
                    ]
                await asyncio.to_thread(atomic_write_json, "config/channel_messages.json", recent)
            except (OSError, TypeError, ValueError) as e:
                log.warning("LISTENER message cache refresh failed: %s", e)

    async def _idle_heartbeat_loop(self):
        interval = int(os.environ.get("LISTENER_HEARTBEAT_SEC", "120"))
        while True:
            await asyncio.sleep(interval)
            try:
                now = datetime.now(timezone.utc)
                if self._last_ingest_at is not None:
                    age = (now - self._last_ingest_at).total_seconds()
                    last_ingest_str = self._last_ingest_at.isoformat()
                    if age > LISTENER_STALE_THRESHOLD_SEC:
                        status = "WARN"
                        note = (
                            f"LISTENER_STALE_OR_DISCONNECTED: no message in {age:.0f}s "
                            f"(threshold {LISTENER_STALE_THRESHOLD_SEC}s)"
                        )
                        log.warning("LISTENER: %s", note)
                    else:
                        status = "OK"
                        note = f"monitoring {len(CHANNELS)} channels, last_ingest {age:.0f}s ago"
                else:
                    status = "OK"
                    last_ingest_str = None
                    note = f"monitoring {len(CHANNELS)} channels, no message yet"

                report_component_status(
                    "LISTENER",
                    status,
                    mode=self._mode,
                    note=note,
                    last_action=f"idle heartbeat ({interval}s)",
                )
                self._write_listener_meta(status=status, last_ingest_at=last_ingest_str)
            except Exception:
                pass

    def _write_listener_meta(self, *, status: str = "OK",
                             last_ingest_at: str | None = None,
                             resolved_rooms: list | None = None):
        """Write listener_meta.json for ATHENA API consumption."""
        try:
            existing: dict = {}
            try:
                with open(LISTENER_META_FILE) as f:
                    existing = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
                log.warning("Failed to read %s: %s", LISTENER_META_FILE, e)
            meta = {
                **existing,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "status": status,
                "channels_count": len(CHANNELS),
                "signal_trade_rooms_active": bool(SIGNAL_TRADE_ROOMS),
                "signal_trade_rooms_count": len(SIGNAL_TRADE_ROOMS),
                "signal_trade_rooms_source": SIGNAL_TRADE_ROOMS_SOURCE,
            }
            if last_ingest_at is not None:
                meta["last_ingest_at"] = last_ingest_at
            if resolved_rooms is not None:
                meta["resolved_rooms"] = resolved_rooms
            atomic_write_json(LISTENER_META_FILE, meta)
        except Exception as e:
            log.debug("LISTENER meta write failed: %s", e)

    async def start(self):
        if not all([API_ID, API_HASH, PHONE]):
            log.error("LISTENER: Telegram credentials not configured")
            report_component_status(
                "LISTENER",
                "ERROR",
                note="Telegram credentials missing",
                last_action="set TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE",
            )
            return
        if not CHANNELS:
            log.error("LISTENER: TELEGRAM_CHANNELS is empty — no channels to monitor")
            report_component_status(
                "LISTENER",
                "ERROR",
                note="TELEGRAM_CHANNELS empty",
                last_action="set TELEGRAM_CHANNELS in .env",
            )
            return

        client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        await client.start(phone=PHONE)
        log.info("LISTENER: Telegram connected")

        # Resolve channel names and write to file for ATHENA API
        resolved_rooms: list[dict] = []
        try:
            names = {}
            for ch_id in CHANNELS:
                entity = await client.get_entity(ch_id)
                name = getattr(entity, 'title', str(ch_id))
                names[str(ch_id)] = name
                allowed, match_reason = self._is_trade_room_allowed(name, ch_id)
                resolved_rooms.append({
                    "chat_id": str(ch_id),
                    "title": name,
                    "is_trade_room": allowed,
                    "match_reason": match_reason,
                })
                log.info(
                    "LISTENER: channel %s = %r  trade_room=%s (%s)",
                    ch_id, name, allowed, match_reason,
                )
            await asyncio.to_thread(atomic_write_json, "config/channel_names.json", names)
        except Exception as e:
            log.warning(f"LISTENER: channel name resolution failed: {e}")

        # Cache recent messages for ATHENA API
        try:
            recent = {}
            for ch_id in CHANNELS:
                msgs = await client.get_messages(ch_id, limit=10)
                recent[str(ch_id)] = [
                    {"date": str(m.date)[:19], "text": (m.message or "(media)")[:200], "id": m.id}
                    for m in msgs
                ]
            await asyncio.to_thread(atomic_write_json, "config/channel_messages.json", recent)
            log.info("LISTENER: cached recent messages for %d channels", len(recent))
        except Exception as e:
            log.warning(f"LISTENER: message cache failed: {e}")

        report_component_status(
            "LISTENER",
            "OK",
            mode=self._mode,
            note=f"monitoring {len(CHANNELS)} channels",
            last_action="Telegram connected",
        )
        self._write_listener_meta(status="OK", resolved_rooms=resolved_rooms)
        asyncio.create_task(self._idle_heartbeat_loop())
        asyncio.create_task(self._refresh_message_cache(client))

        @client.on(events.NewMessage(chats=CHANNELS))
        async def on_message(event):
            await self._handle_message(event.message)

        @client.on(events.MessageEdited(chats=CHANNELS))
        async def on_edit(event):
            await self._handle_message(event.message, edited=True)

        await client.run_until_disconnected()

    @staticmethod
    def _msg_has_media(msg) -> bool:
        return bool(getattr(msg, "photo", None) or getattr(msg, "document", None))

    @staticmethod
    def _normalize_room_name(s: str) -> str:
        """Lowercase + collapse whitespace + normalize Unicode (handles curly quotes etc.)."""
        return _normalize_allowlist_token(s)

    @staticmethod
    def _chat_id_variants(chat_id) -> list[str]:
        """
        Return candidate string forms of a Telethon chat_id to match against SIGNAL_TRADE_ROOMS.
        Telethon supergroup IDs are large negatives like -1001234567890.
        Operators may configure just the base id (1234567890) or the full form.
        """
        if chat_id is None:
            return []
        raw = str(chat_id).strip()
        variants = {raw}
        # Negative → also try without sign and without the -100 prefix
        if raw.startswith("-100"):
            variants.add(raw[4:])       # 1234567890
            variants.add(raw[1:])       # 1001234567890
        elif raw.startswith("-"):
            variants.add(raw[1:])       # positive form
        else:
            variants.add(f"-100{raw}")  # add -100 prefix form
        return [v.lower() for v in variants]

    @staticmethod
    def _is_trade_room_allowed(channel_name: str, chat_id) -> tuple[bool, str]:
        """
        Room-priority policy:
        - SIGNAL_TRADE_ROOMS empty → all rooms tradable (returns True, "ALLOWED_ALL")
        - otherwise match by normalized title OR any chat_id variant

        Returns:
            (allowed: bool, reason_code: str)
            reason_code is one of:
              "ALLOWED_ALL"          – SIGNAL_TRADE_ROOMS not configured
              "ALLOWED_TITLE_MATCH"  – title matched
              "ALLOWED_ID_MATCH"     – chat_id matched
              "WATCH_ONLY_ROOM_FILTER" – not in allowlist
        """
        if not SIGNAL_TRADE_ROOMS:
            return True, "ALLOWED_ALL"

        # Title match (normalized for Unicode, whitespace, case)
        channel_key = Listener._normalize_room_name(channel_name)
        if channel_key in SIGNAL_TRADE_ROOMS:
            return True, "ALLOWED_TITLE_MATCH"

        # chat_id match (try multiple forms to handle supergroup prefix differences)
        for id_variant in Listener._chat_id_variants(chat_id):
            if id_variant in SIGNAL_TRADE_ROOMS:
                log.info(
                    "LISTENER: room %r (chat_id=%s) matched by id_variant=%s",
                    channel_name, chat_id, id_variant,
                )
                return True, "ALLOWED_ID_MATCH"

        log.warning(
            "LISTENER: room %r (chat_id=%s) not in trade-room allowlist (%s) — "
            "reason=WATCH_ONLY_ROOM_FILTER  configured_entries=%s",
            channel_name, chat_id, SIGNAL_TRADE_ROOMS_ENV_NAMES, sorted(SIGNAL_TRADE_ROOMS),
        )
        return False, "WATCH_ONLY_ROOM_FILTER"

    @staticmethod
    def _normalize_parsed(parsed: dict) -> dict:
        out = dict(parsed or {})
        if out.get("type") == "MANAGEMENT":
            if "mgmt_intent" not in out and out.get("intent"):
                out["mgmt_intent"] = out.get("intent")
            if "mgmt_pct" not in out and out.get("pct") is not None:
                out["mgmt_pct"] = out.get("pct")
        return out

    @staticmethod
    def _entry_complete(parsed: dict) -> bool:
        if not isinstance(parsed, dict):
            return False
        if parsed.get("type") != "ENTRY":
            return False
        req = ("direction", "entry_low", "entry_high", "sl", "tp1")
        for k in req:
            if parsed.get(k) in (None, ""):
                return False
        return True

    @staticmethod
    def _parsed_from_vision_struct(structured: dict) -> dict:
        p = dict(structured or {})
        if not p:
            return {"type": "IGNORE"}
        if p.get("type") == "MANAGEMENT":
            p["mgmt_intent"] = p.get("intent")
            p["mgmt_pct"] = p.get("pct")
        return p

    @staticmethod
    def _build_signal_media_summary(channel: str, msg_id: int, vr, parsed: dict | None) -> str:
        pd = parsed if isinstance(parsed, dict) else {}
        out = [
            "🖼️ <b>SIGNAL ROOM CHART ANALYSIS</b>",
            f"Channel: <b>{channel}</b>",
            f"Message ID: <code>{msg_id}</code>",
            f"Confidence: <b>{getattr(vr, 'confidence', 'UNKNOWN')}</b>",
            f"Parsed Type: <b>{pd.get('type', 'IGNORE')}</b>",
        ]
        if pd.get("type") == "ENTRY":
            out.append(
                f"Entry: <code>{pd.get('direction','?')} {pd.get('entry_low','?')}–{pd.get('entry_high','?')}</code> "
                f"SL <code>{pd.get('sl','?')}</code> TP1 <code>{pd.get('tp1','?')}</code>"
            )
        elif pd.get("type") == "MANAGEMENT":
            out.append(
                f"Management: <code>{pd.get('mgmt_intent') or pd.get('intent') or 'UNKNOWN'}</code>"
            )
        extracted = (getattr(vr, "extracted_text", "") or "").strip().replace("\n", " ")
        if extracted:
            out.append(f"Extract: {extracted[:220]}")
        return "\n".join(out)

    def _archive_signal_media(self, *, src_path: str, channel: str, msg_id: int, caption: str) -> str | None:
        if not LISTENER_SIGNAL_MEDIA_ARCHIVE_ENABLED:
            return None
        try:
            safe_channel = re.sub(r"[^a-zA-Z0-9._-]+", "_", (channel or "unknown")).strip("_") or "unknown"
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            base_dir = os.path.join(LISTENER_SIGNAL_MEDIA_ARCHIVE_DIR, safe_channel)
            os.makedirs(base_dir, exist_ok=True)
            dst_img = os.path.join(base_dir, f"{ts}_msg{msg_id}.img")
            shutil.copy2(src_path, dst_img)
            meta = {
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "channel": channel,
                "message_id": msg_id,
                "caption": caption or "",
                "file_path": dst_img,
                "source": "LISTENER_SIGNAL_MEDIA",
            }
            atomic_write_json(dst_img + ".json", meta)
            try:
                self.scribe.log_system_event(
                    event_type="SIGNAL_CHART_ARCHIVED",
                    triggered_by="LISTENER",
                    reason="TELEGRAM_SIGNAL_MEDIA_ARCHIVE",
                    notes=f"channel={channel} msg_id={msg_id} file={dst_img}",
                )
            except Exception:
                pass
            return dst_img
        except Exception as e:
            log.warning("LISTENER media archive failed: %s", e)
            return None

    async def _download_message_media(self, msg) -> str | None:
        try:
            with tempfile.NamedTemporaryFile(prefix="listener_", suffix=".img", delete=False) as tmp:
                path = tmp.name
            out = await msg.download_media(file=path)
            return out or path
        except Exception as e:
            log.warning("LISTENER media download failed: %s", e)
            return None

    def _log_vision(self, *, caller: str, channel: str, hint: str, vr) -> int:
        sd = vr.structured_data if isinstance(vr.structured_data, dict) else {}
        return self.scribe.log_vision_extraction({
            "caller": caller,
            "source_channel": channel,
            "context_hint": hint,
            "image_type": vr.image_type,
            "confidence": vr.confidence,
            "extracted_text": vr.extracted_text,
            "structured_data": sd,
            "direction": sd.get("direction"),
            "entry_price": sd.get("entry_low") or sd.get("entry_high"),
            "sl_price": sd.get("sl"),
            "tp1_price": sd.get("tp1"),
            "tp2_price": sd.get("tp2"),
            "caller_action": vr.caller_action,
            "downstream_result": "CAPTURED",
            "image_hash": vr.image_hash,
            "file_size_kb": vr.file_size_kb,
            "processing_ms": vr.processing_ms,
            "error": vr.error,
        })

    async def _handle_message(self, msg, edited: bool = False):
        text = msg.message or ""
        has_media = self._msg_has_media(msg)
        if not text.strip() and not has_media:
            return

        # Track last ingest timestamp for staleness detection
        self._last_ingest_at = datetime.now(timezone.utc)

        # Dedup by Telegram message identity (ignore edited flag).
        # Same message often arrives as NewMessage then MessageEdited a few seconds later.
        # We should process it once for execution safety.
        msg_key = (msg.id, msg.chat_id)
        if msg_key in self._last_signal_id:
            return
        self._last_signal_id.add(msg_key)
        if len(self._last_signal_id) > 1000:
            self._last_signal_id = set(list(self._last_signal_id)[-500:])

        channel = getattr(msg.chat, "title", str(msg.chat_id)) if msg.chat else "unknown"
        log.info(f"LISTENER [{channel}]: {text[:80]}")
        if has_media:
            try:
                self.scribe.log_system_event(
                    event_type="SIGNAL_CHART_RECEIVED",
                    triggered_by="LISTENER",
                    reason="TELEGRAM_SIGNAL_MEDIA",
                    notes=(
                        f"channel={channel} msg_id={msg.id} "
                        f"photo={bool(getattr(msg, 'photo', None))} "
                        f"document={bool(getattr(msg, 'document', None))} "
                        f"text_len={len(text or '')}"
                    ),
                )
            except Exception:
                pass

        source_type = "MIXED" if (text.strip() and has_media) else ("IMAGE" if has_media else "TEXT")
        parsed = await self._parse(text) if text.strip() else {"type": "IGNORE"}
        parsed = self._normalize_parsed(parsed)
        vision_id = None
        vision_result = None
        if has_media and VISION_ENABLED:
            img_path = await self._download_message_media(msg)
            if not img_path:
                try:
                    self.scribe.log_system_event(
                        event_type="SIGNAL_CHART_DOWNLOAD_FAILED",
                        triggered_by="LISTENER",
                        reason="TELEGRAM_SIGNAL_MEDIA",
                        notes=f"channel={channel} msg_id={msg.id}",
                    )
                except Exception:
                    pass
            if img_path:
                archived_path = await asyncio.to_thread(
                    self._archive_signal_media,
                    src_path=img_path,
                    channel=channel,
                    msg_id=msg.id,
                    caption=text,
                )
                if archived_path:
                    log.info("LISTENER: archived signal media -> %s", archived_path)
                try:
                    vision_result = await asyncio.to_thread(
                        self.vision.extract,
                        image_path=img_path,
                        caption=text,
                        context_hint="SIGNAL",
                        caller="LISTENER",
                    )
                finally:
                    try:
                        os.remove(img_path)
                    except Exception:
                        pass
                if vision_result:
                    vision_id = self._log_vision(
                        caller="LISTENER",
                        channel=channel,
                        hint="SIGNAL",
                        vr=vision_result,
                    )
                    vis_parsed = self._normalize_parsed(
                        self._parsed_from_vision_struct(vision_result.structured_data)
                    )
                    if parsed.get("type") == "IGNORE":
                        parsed = vis_parsed
                    elif parsed.get("type") == "ENTRY" and not self._entry_complete(parsed):
                        for k in ("direction", "entry_low", "entry_high", "sl", "tp1", "tp2", "tp3", "tp3_open"):
                            if parsed.get(k) in (None, "") and vis_parsed.get(k) not in (None, ""):
                                parsed[k] = vis_parsed.get(k)
                    elif parsed.get("type") == "MANAGEMENT":
                        if not parsed.get("mgmt_intent") and vis_parsed.get("mgmt_intent"):
                            parsed["mgmt_intent"] = vis_parsed.get("mgmt_intent")
                        if parsed.get("mgmt_pct") is None and vis_parsed.get("mgmt_pct") is not None:
                            parsed["mgmt_pct"] = vis_parsed.get("mgmt_pct")
                    if LISTENER_SIGNAL_MEDIA_SUMMARY_TO_BOT:
                        try:
                            sent_ok = self.herald.send(
                                self._build_signal_media_summary(channel, msg.id, vision_result, parsed)
                            )
                            event_type = "SIGNAL_CHART_SUMMARY_SENT" if sent_ok else "SIGNAL_CHART_SUMMARY_FAILED"
                            try:
                                self.scribe.log_system_event(
                                    event_type=event_type,
                                    triggered_by="LISTENER",
                                    reason="TELEGRAM_SIGNAL_MEDIA_SUMMARY",
                                    notes=(
                                        f"channel={channel} msg_id={msg.id} "
                                        f"confidence={getattr(vision_result, 'confidence', 'UNKNOWN')} "
                                        f"parsed_type={parsed.get('type','IGNORE')}"
                                    ),
                                )
                            except Exception:
                                pass
                            log.info(
                                "LISTENER signal media summary %s channel=%s msg_id=%s",
                                "sent" if sent_ok else "failed",
                                channel,
                                msg.id,
                            )
                        except Exception as e:
                            log.warning("LISTENER media summary send failed: %s", e)

        if not parsed or parsed.get("type") == "IGNORE":
            if text.strip():
                # Non-empty text was received but not parsed as a signal — log for diagnostics
                log.info(
                    "LISTENER: PARSE_FAILED/IGNORE — channel=%s chat_id=%s msg_id=%s text=%r",
                    channel, msg.chat_id, msg.id, text[:120],
                )
                try:
                    self.scribe.log_system_event(
                        event_type="SIGNAL_PARSE_FAILED",
                        triggered_by="LISTENER",
                        reason="PARSE_FAILED",
                        notes=(
                            f"channel={channel} chat_id={msg.chat_id} msg_id={msg.id} "
                            f"text_len={len(text)} has_media={has_media}"
                        ),
                    )
                except Exception:
                    pass
            if vision_id:
                self.scribe.update_vision_extraction_result(vision_id, "IGNORED")
            return

        range_errors = _validate_signal_ranges(parsed)
        if range_errors:
            log.warning(
                "LISTENER: signal range validation rejected channel=%s chat_id=%s msg_id=%s errors=%s",
                channel,
                msg.chat_id,
                msg.id,
                "; ".join(range_errors),
            )
            if vision_id:
                self.scribe.update_vision_extraction_result(vision_id, "REJECTED_RANGE")
            return

        # Log to SCRIBE regardless of mode
        signal_id = self.scribe.log_signal(
            raw=text, parsed=parsed, mode=self._mode,
            channel=channel, msg_id=msg.id,
            signal_source_type=source_type,
            vision_extraction_id=vision_id,
            vision_confidence=(vision_result.confidence if vision_result else None),
        )
        if vision_id:
            self.scribe.update_vision_extraction_result(vision_id, "PARSED", linked_signal_id=signal_id)

        if (
            source_type in ("IMAGE", "MIXED")
            and vision_result
            and VISION_LOW_CONFIDENCE_HOLD
            and vision_result.confidence == "LOW"
        ):
            self.scribe.update_signal_action(signal_id, "HELD", "VISION_LOW_CONFIDENCE")
            if vision_id:
                self.scribe.update_vision_extraction_result(vision_id, "HELD", linked_signal_id=signal_id)
            self.herald.send(
                f"🟡 LISTENER held image signal from {channel} (LOW confidence). "
                f"Signal #{signal_id} awaiting manual confirmation."
            )
            return

        # In non-trading modes — log only, don't dispatch to BRIDGE
        if self._mode not in ("SIGNAL", "HYBRID"):
            self.scribe.update_signal_action(signal_id, "LOGGED_ONLY")
            if vision_id:
                self.scribe.update_vision_extraction_result(vision_id, "LOGGED_ONLY", linked_signal_id=signal_id)
            log.info(f"LISTENER [{self._mode}]: logged signal, not dispatching")
            try:
                report_component_status(
                    "LISTENER",
                    "OK",
                    mode=self._mode,
                    note=f"monitoring {len(CHANNELS)} channels",
                    last_action=f"[{self._mode}] received msg from {channel}",
                )
            except Exception as _he:
                log.debug(f"LISTENER heartbeat error: {_he}")
            return

        # Dispatch
        if parsed["type"] == "ENTRY":
            allowed, allow_reason = self._is_trade_room_allowed(channel, msg.chat_id)
            if not allowed:
                self.scribe.update_signal_action(signal_id, "WATCH_ONLY", "WATCH_ONLY_ROOM_FILTER")
                if vision_id:
                    self.scribe.update_vision_extraction_result(
                        vision_id, "WATCH_ONLY", linked_signal_id=signal_id
                    )
                try:
                    self.scribe.log_system_event(
                        event_type="SIGNAL_ROOM_WATCH_ONLY",
                        triggered_by="LISTENER",
                        reason="WATCH_ONLY_ROOM_FILTER",
                        notes=(
                            f"channel={channel} chat_id={msg.chat_id} "
                            f"signal_id={signal_id} mode={self._mode} "
                            f"configured_rooms={sorted(SIGNAL_TRADE_ROOMS)}"
                        ),
                    )
                except Exception:
                    pass
                log.warning(
                    "LISTENER: WATCH_ONLY_ROOM_FILTER — channel=%r chat_id=%s "
                    "not in trade-room allowlist (%s) (signal_id=%s)",
                    channel, msg.chat_id, SIGNAL_TRADE_ROOMS_ENV_NAMES, signal_id,
                )
                return
            parsed["signal_id"]  = signal_id
            parsed["channel"]    = channel
            parsed["timestamp"]  = datetime.now(timezone.utc).isoformat()
            parsed["edited"]     = edited
            await asyncio.to_thread(self._write_signal, parsed)
            now_iso = datetime.now(timezone.utc).isoformat()
            self._last_ingest_at = datetime.now(timezone.utc)
            log.info(
                "LISTENER: SIGNAL_DISPATCHED — %s @ %s–%s channel=%r chat_id=%s "
                "match=%s signal_id=%s",
                parsed.get("direction"), parsed.get("entry_low"), parsed.get("entry_high"),
                channel, msg.chat_id, allow_reason, signal_id,
            )
            try:
                self.scribe.log_system_event(
                    event_type="SIGNAL_DISPATCHED",
                    triggered_by="LISTENER",
                    reason="SIGNAL_DISPATCHED",
                    notes=(
                        f"channel={channel} chat_id={msg.chat_id} signal_id={signal_id} "
                        f"direction={parsed.get('direction')} match={allow_reason}"
                    ),
                )
            except Exception:
                pass
            if vision_id:
                self.scribe.update_vision_extraction_result(vision_id, "DISPATCHED_ENTRY", linked_signal_id=signal_id)
            try:
                report_component_status(
                    "LISTENER",
                    "OK",
                    mode=self._mode,
                    note=f"monitoring {len(CHANNELS)} channels",
                    last_action=f"parsed {parsed.get('type','?')} {parsed.get('direction','')} from {channel}",
                )
                self._write_listener_meta(status="OK", last_ingest_at=now_iso)
            except Exception as _he:
                log.debug(f"LISTENER heartbeat error: {_he}")

        elif parsed["type"] == "MANAGEMENT":
            parsed["signal_id"]  = signal_id
            parsed["channel"]    = channel
            parsed["source"]     = "LISTENER"
            parsed["timestamp"]  = datetime.now(timezone.utc).isoformat()

            # Find the most recent OPEN group from this channel
            try:
                rows = self.scribe.query(
                    """SELECT tg.id FROM trade_groups tg
                       JOIN signals_received sr ON sr.trade_group_id = tg.id
                       WHERE sr.channel_name = ? AND tg.status IN ('OPEN','PARTIAL')
                       ORDER BY tg.id DESC LIMIT 1""",
                    (channel,)
                )
                if rows:
                    parsed["group_id"] = rows[0]["id"]
                    log.info(f"LISTENER: MGMT from {channel} targets G{parsed['group_id']}")
            except Exception as e:
                log.warning(f"LISTENER: channel group lookup failed: {e}")

            await asyncio.to_thread(self._write_mgmt, parsed)
            log.info(f"LISTENER → management_cmd.json: {parsed.get('intent')} (group={parsed.get('group_id','ALL')})")
            if vision_id:
                self.scribe.update_vision_extraction_result(vision_id, "DISPATCHED_MANAGEMENT", linked_signal_id=signal_id)

    async def _parse(self, text: str) -> dict | None:
        if not self.claude:
            return self._fallback_parse(text)
        try:
            resp = await asyncio.wait_for(
                asyncio.to_thread(
                    self.claude.messages.create,
                    model="claude-haiku-4-5-20251001",   # fast + cheap for parsing
                    max_tokens=256,
                    messages=[
                        {"role": "user",
                         "content": f"{PARSE_PROMPT}\n\nMessage:\n{text}"}
                    ],
                    timeout=httpx.Timeout(30.0),
                ),
                timeout=30,
            )
            raw = resp.content[0].text.strip()
            raw = raw.replace("```json","").replace("```","").strip()
            return json.loads(raw)
        except json.JSONDecodeError as e:
            log.warning(f"LISTENER parse JSON error: {e}")
            return {"type": "IGNORE"}
        except (httpx.TimeoutException, asyncio.TimeoutError) as e:
            log.warning("LISTENER Claude API timeout: %s", e)
            return self._fallback_parse(text)
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
            atomic_write_json(SIGNAL_FILE, data)
        except Exception as e:
            log.error(f"LISTENER write signal error: {e}")

    def _write_mgmt(self, data: dict):
        try:
            atomic_write_json(MGMT_FILE, data)
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
