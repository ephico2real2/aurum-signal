#!/usr/bin/env python3
"""
replay_signal_pickup.py — Replay a signal through LISTENER and verify pickup
=============================================================================
Use this to inject a Telegram-style text message into LISTENER's normal
_handle_message pipeline, then confirm SCRIBE recorded it.

Safe default:
  - mode defaults to WATCH (no trade dispatch)

Examples:
  python3 scripts/replay_signal_pickup.py \
    --text "Sell Gold @ 4780-4776 SL 4786 TP1 4772 TP2 4768" \
    --chat-id -1002034822451 \
    --channel-name "Ben's VIP Club"

  python3 scripts/replay_signal_pickup.py \
    --from-signal-id 220 \
    --mode HYBRID \
    --wait-bridge-sec 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "python"
sys.path.insert(0, str(PY))


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    for name in (".env", ".env.local"):
        path = ROOT / name
        if path.is_file():
            load_dotenv(path)


def _normalize_room_name(value: str) -> str:
    value = (
        (value or "")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    value = unicodedata.normalize("NFKC", value or "")
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_channel_names(path: Path) -> dict[int, str]:
    raw = _read_json(path)
    out: dict[int, str] = {}
    for key, value in raw.items():
        try:
            out[int(str(key).strip())] = str(value)
        except Exception:
            continue
    return out


def _find_chat_id_for_channel(channel_name: str, channel_names: dict[int, str]) -> int | None:
    needle = _normalize_room_name(channel_name)
    for chat_id, title in channel_names.items():
        if _normalize_room_name(title) == needle:
            return chat_id
    return None


def _effective_mode(status_file: Path, explicit_mode: str | None) -> str:
    if explicit_mode:
        return explicit_mode.upper()
    data = _read_json(status_file)
    mode = (data.get("effective_mode") or data.get("mode") or "WATCH").upper()
    if mode not in {"OFF", "WATCH", "SIGNAL", "SCALPER", "HYBRID", "AUTO_SCALPER"}:
        return "WATCH"
    return mode


@dataclass
class ReplayPayload:
    text: str
    channel_name: str
    chat_id: int
    source: str


class _ReplayChat:
    def __init__(self, title: str):
        self.title = title


class _ReplayMessage:
    def __init__(self, *, text: str, chat_id: int, channel_name: str, message_id: int):
        self.message = text
        self.id = message_id
        self.chat_id = chat_id
        self.chat = _ReplayChat(channel_name)
        self.photo = None
        self.document = None


def _load_replay_payload(
    *,
    args: argparse.Namespace,
    scribe,
    channel_names: dict[int, str],
) -> ReplayPayload:
    if args.from_signal_id is not None:
        rows = scribe.query(
            "SELECT id, raw_text, channel_name FROM signals_received WHERE id=? LIMIT 1",
            (args.from_signal_id,),
        )
        if not rows:
            raise ValueError(f"signal_id {args.from_signal_id} not found in signals_received")
        row = rows[0]
        text = str(row.get("raw_text") or "").strip()
        if not text:
            raise ValueError(f"signal_id {args.from_signal_id} has empty raw_text")
        channel_name = (
            str(args.channel_name).strip()
            if args.channel_name
            else str(row.get("channel_name") or "").strip()
        )
        if not channel_name:
            raise ValueError(
                "channel_name is missing; pass --channel-name (source row had no channel_name)"
            )
        if args.chat_id is not None:
            chat_id = int(args.chat_id)
        else:
            found = _find_chat_id_for_channel(channel_name, channel_names)
            if found is None:
                raise ValueError(
                    f"unable to infer chat_id for channel {channel_name!r}; pass --chat-id explicitly"
                )
            chat_id = int(found)
        return ReplayPayload(
            text=text,
            channel_name=channel_name,
            chat_id=chat_id,
            source=f"signals_received.id={args.from_signal_id}",
        )

    text = str(args.text or "").strip()
    if not text:
        raise ValueError("text is required when --from-signal-id is not provided")

    if args.chat_id is None:
        raise ValueError("--chat-id is required when replaying raw --text")
    chat_id = int(args.chat_id)

    channel_name = str(args.channel_name or "").strip()
    if not channel_name:
        channel_name = channel_names.get(chat_id, f"channel_{chat_id}")

    return ReplayPayload(
        text=text,
        channel_name=channel_name,
        chat_id=chat_id,
        source="raw_text",
    )


def _wait_for_bridge_action(
    *,
    scribe,
    signal_id: int,
    timeout_sec: float,
    poll_sec: float,
) -> dict:
    start = time.time()
    timeout_sec = max(0.0, float(timeout_sec))
    poll_sec = max(0.1, float(poll_sec))
    last = {}
    while True:
        rows = scribe.query(
            "SELECT action_taken, skip_reason, trade_group_id FROM signals_received WHERE id=? LIMIT 1",
            (signal_id,),
        )
        if rows:
            last = rows[0]
            action = str(last.get("action_taken") or "").upper()
            if action and action != "PENDING":
                break
        if time.time() - start >= timeout_sec:
            break
        time.sleep(poll_sec)
    return {
        "waited_sec": round(time.time() - start, 2),
        "action_taken": last.get("action_taken"),
        "skip_reason": last.get("skip_reason"),
        "trade_group_id": last.get("trade_group_id"),
        "terminal": str(last.get("action_taken") or "").upper() not in ("", "PENDING"),
    }


def main() -> int:
    _load_dotenv()
    ap = argparse.ArgumentParser(
        description="Replay one Telegram-style signal through LISTENER and verify SCRIBE pickup."
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="Raw signal text to replay.")
    src.add_argument("--from-signal-id", type=int, help="Replay from existing signals_received.id.")
    ap.add_argument("--chat-id", type=int, help="Telegram chat id (required for --text).")
    ap.add_argument("--channel-name", default="", help="Channel title override.")
    ap.add_argument(
        "--mode",
        choices=["OFF", "WATCH", "SIGNAL", "SCALPER", "HYBRID", "AUTO_SCALPER"],
        default="WATCH",
        help="Listener mode for replay (default: WATCH for safety).",
    )
    ap.add_argument("--msg-id", type=int, default=None, help="Message id override.")
    ap.add_argument(
        "--wait-bridge-sec",
        type=float,
        default=20.0,
        help="When mode is SIGNAL/HYBRID, wait this long for action to leave PENDING.",
    )
    ap.add_argument("--poll-sec", type=float, default=1.0, help="Polling interval while waiting.")
    ap.add_argument(
        "--expect-action",
        default="",
        help="Optional expected final action_taken (e.g. WATCH_ONLY, LOGGED_ONLY, EXECUTED, SKIPPED).",
    )
    ap.add_argument(
        "--db",
        default=str(PY / "data" / "aurum_intelligence.db"),
        help="SCRIBE DB path.",
    )
    ap.add_argument(
        "--status-file",
        default=str(PY / "config" / "status.json"),
        help="Status file used only when --mode not provided.",
    )
    ap.add_argument(
        "--channel-names-file",
        default=str(PY / "config" / "channel_names.json"),
        help="chat_id -> title mapping used for channel-name inference.",
    )
    args = ap.parse_args()

    os.environ["SCRIBE_DB"] = str(Path(args.db).resolve())
    os.chdir(PY)

    from listener import Listener
    from scribe import get_scribe

    scribe = get_scribe()
    channel_names = _load_channel_names(Path(args.channel_names_file))
    mode = _effective_mode(Path(args.status_file), args.mode)

    try:
        payload = _load_replay_payload(args=args, scribe=scribe, channel_names=channel_names)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    msg_id = args.msg_id if args.msg_id is not None else int(time.time() * 1000) % 2_000_000_000
    replay_message = _ReplayMessage(
        text=payload.text,
        chat_id=payload.chat_id,
        channel_name=payload.channel_name,
        message_id=msg_id,
    )

    listener = Listener()
    listener.set_mode(mode)
    asyncio.run(listener._handle_message(replay_message))

    rows = scribe.query(
        """SELECT id, timestamp, mode, channel_name, message_id, signal_type, direction,
                  entry_low, entry_high, sl, tp1, tp2, tp3, action_taken, skip_reason, trade_group_id
           FROM signals_received
           WHERE message_id=? AND channel_name=?
           ORDER BY id DESC LIMIT 1""",
        (msg_id, payload.channel_name),
    )

    if not rows:
        print(
            json.dumps(
                {
                    "ok": False,
                    "picked_up": False,
                    "error": "No signals_received row found for replayed message.",
                    "replay": {
                        "mode": mode,
                        "chat_id": payload.chat_id,
                        "channel_name": payload.channel_name,
                        "message_id": msg_id,
                    },
                },
                indent=2,
            )
        )
        return 1

    signal_row = rows[0]
    signal_id = int(signal_row["id"])

    events = scribe.query(
        """SELECT id, timestamp, event_type, reason, notes
           FROM system_events
           WHERE notes LIKE ? OR notes LIKE ?
           ORDER BY id DESC LIMIT 10""",
        (f"%signal_id={signal_id}%", f"%msg_id={msg_id}%"),
    )

    bridge_wait = None
    if mode in {"SIGNAL", "HYBRID"} and args.wait_bridge_sec > 0:
        bridge_wait = _wait_for_bridge_action(
            scribe=scribe,
            signal_id=signal_id,
            timeout_sec=args.wait_bridge_sec,
            poll_sec=args.poll_sec,
        )
        signal_row["action_taken"] = bridge_wait["action_taken"]
        signal_row["skip_reason"] = bridge_wait["skip_reason"]
        signal_row["trade_group_id"] = bridge_wait["trade_group_id"]

    action_taken = str(signal_row.get("action_taken") or "")
    expected = str(args.expect_action or "").strip().upper()
    expect_ok = (not expected) or (action_taken.upper() == expected)

    output = {
        "ok": True and expect_ok,
        "picked_up": True,
        "replay": {
            "source": payload.source,
            "mode": mode,
            "chat_id": payload.chat_id,
            "channel_name": payload.channel_name,
            "message_id": msg_id,
        },
        "signal_row": signal_row,
        "bridge_wait": bridge_wait,
        "events": events,
    }
    if expected:
        output["expect_action"] = expected
        output["expect_action_met"] = expect_ok

    print(json.dumps(output, indent=2, default=str))
    return 0 if output["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
