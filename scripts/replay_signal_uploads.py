#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "python"
sys.path.insert(0, str(PY))


def _iter_metadata_files(base_dir: Path):
    if not base_dir.exists():
        return []
    files = list(base_dir.rglob("*.img.json"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _load_meta(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay VISION analysis for archived signal-room uploads.")
    ap.add_argument("--limit", type=int, default=5, help="How many recent uploads to replay (default: 5).")
    ap.add_argument("--channel", default="", help="Optional channel filter (case-insensitive exact match).")
    ap.add_argument("--notify", action="store_true", help="Send replay summaries to Telegram bot chat.")
    ap.add_argument(
        "--db",
        default=str(PY / "data/aurum_intelligence.db"),
        help="SCRIBE SQLite path for replay logs (default: python/data/aurum_intelligence.db).",
    )
    args, _ = ap.parse_known_args()
    os.environ["SCRIBE_DB"] = args.db
    from herald import get_herald
    from listener import Listener, LISTENER_SIGNAL_MEDIA_ARCHIVE_DIR
    from scribe import get_scribe
    from vision import Vision
    from anthropic import Anthropic
    ap.add_argument(
        "--archive-dir",
        default=LISTENER_SIGNAL_MEDIA_ARCHIVE_DIR,
        help="Archive directory root (defaults to LISTENER_SIGNAL_MEDIA_ARCHIVE_DIR).",
    )
    args = ap.parse_args()

    base_dir = Path(args.archive_dir)
    metas = _iter_metadata_files(base_dir)
    if args.channel:
        metas = [m for m in metas if _load_meta(m).get("channel", "").lower() == args.channel.lower()]
    metas = metas[: max(1, args.limit)]
    if not metas:
        print(f"No archived uploads found in {base_dir}")
        return 0

    claude_key = os.environ.get("ANTHROPIC_API_KEY", "")
    claude = Anthropic(api_key=claude_key) if claude_key else None
    vision = Vision(claude)
    scribe = get_scribe()
    herald = get_herald()

    replayed = 0
    for meta_path in metas:
        meta = _load_meta(meta_path)
        image_path = Path(str(meta.get("file_path", "") or meta_path.with_suffix("")))
        channel = meta.get("channel", "unknown")
        msg_id = meta.get("message_id", "unknown")
        caption = meta.get("caption", "")
        if not image_path.exists():
            print(f"SKIP missing image: {image_path}")
            continue

        vr = vision.extract(
            image_path=image_path,
            caption=caption,
            context_hint="SIGNAL",
            caller="LISTENER_REPLAY",
        )
        structured = vr.structured_data if isinstance(vr.structured_data, dict) else {}
        _ = scribe.log_vision_extraction(
            {
                "caller": "LISTENER_REPLAY",
                "source_channel": channel,
                "context_hint": "SIGNAL_REPLAY",
                "image_type": vr.image_type,
                "confidence": vr.confidence,
                "extracted_text": vr.extracted_text,
                "structured_data": structured,
                "direction": structured.get("direction"),
                "entry_price": structured.get("entry_low") or structured.get("entry_high"),
                "sl_price": structured.get("sl"),
                "tp1_price": structured.get("tp1"),
                "tp2_price": structured.get("tp2"),
                "caller_action": vr.caller_action,
                "downstream_result": "REPLAYED",
                "image_hash": vr.image_hash,
                "file_size_kb": vr.file_size_kb,
                "processing_ms": vr.processing_ms,
                "error": vr.error,
            }
        )
        try:
            scribe.log_system_event(
                event_type="SIGNAL_CHART_REPLAYED",
                triggered_by="REPLAY_TOOL",
                reason="VISION_REPLAY",
                notes=f"channel={channel} msg_id={msg_id} file={image_path} confidence={vr.confidence}",
            )
        except Exception:
            pass

        summary = Listener._build_signal_media_summary(
            str(channel),
            int(msg_id) if str(msg_id).isdigit() else msg_id,
            vr,
            structured,
        )
        print("=" * 80)
        print(summary)
        print(f"source_file={image_path}")
        if args.notify:
            herald.send(summary)
        replayed += 1

    print(f"\nReplayed {replayed} upload(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
