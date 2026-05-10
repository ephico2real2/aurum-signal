"""
vision.py — reusable image extraction module for LISTENER and AURUM.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anthropic import Anthropic
try:
    from PIL import Image
    _PIL_IMPORT_ERROR: Exception | None = None
except Exception as e:
    Image = None  # type: ignore[assignment]
    _PIL_IMPORT_ERROR = e

log = logging.getLogger("vision")
if _PIL_IMPORT_ERROR is not None:
    log.warning("VISION: Pillow import failed; image extraction will be disabled (%s)", _PIL_IMPORT_ERROR)

VISION_ENABLED = os.environ.get("VISION_ENABLED", "true").lower() in ("1", "true", "yes")
VISION_MAX_IMAGE_MB = float(os.environ.get("VISION_MAX_IMAGE_MB", "8"))
VISION_MODEL = os.environ.get("VISION_MODEL", "claude-sonnet-4-6")
VISION_MAX_EDGE_PX = int(os.environ.get("VISION_MAX_EDGE_PX", "1568"))
VISION_SECOND_PASS = os.environ.get("VISION_SECOND_PASS", "true").lower() in ("1", "true", "yes")
VISION_OCR_FALLBACK = os.environ.get("VISION_OCR_FALLBACK", "true").lower() in ("1", "true", "yes")

ALLOWED_MIME = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
}

SYSTEM_PROMPT = """You extract structured trading information from screenshots and chart images.
Return strict JSON only (no markdown, no commentary).
Return:
{
  "image_type": "SIGNAL|CHART|MT5|UNKNOWN",
  "confidence": "HIGH|MEDIUM|LOW",
  "extracted_text": "short plain-language extraction",
  "structured_data": {
    "type": "ENTRY|MANAGEMENT|IGNORE",
    "direction": "BUY|SELL|null",
    "entry_low": number|null,
    "entry_high": number|null,
    "sl": number|null,
    "tp1": number|null,
    "tp2": number|null,
    "tp3": number|null,
    "tp3_open": boolean|null,
    "intent": "CLOSE_ALL|MOVE_BE|CLOSE_PCT|TP_HIT|HOLD|UPDATE|MODIFY_SL|MODIFY_TP|null",
    "pct": number|null,
    "tp_stage": 1|2|3|null,
    "timeframe": "string|null",
    "instrument": "string|null",
    "pinned_levels": ["string numeric price labels from chart, e.g. 4754.54"]
  },
  "caller_action": "DISPATCH|HOLD|CONFIRM"
}
Rules:
- Prioritize reading visible numeric price labels and pinned horizontal-line labels from chart screenshots.
- If data is ambiguous, lower confidence and choose HOLD/CONFIRM.
- For channel signal extraction, prefer ENTRY when clear direction/levels are visible.
- If nothing actionable is visible, use type=IGNORE and LOW confidence.
"""
OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "image_type": {"type": "string", "enum": ["SIGNAL", "CHART", "MT5", "UNKNOWN"]},
        "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "extracted_text": {"type": "string"},
        "structured_data": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "type": {"type": "string", "enum": ["ENTRY", "MANAGEMENT", "IGNORE"]},
                "direction": {"type": ["string", "null"]},
                "entry_low": {"type": ["number", "null"]},
                "entry_high": {"type": ["number", "null"]},
                "sl": {"type": ["number", "null"]},
                "tp1": {"type": ["number", "null"]},
                "tp2": {"type": ["number", "null"]},
                "tp3": {"type": ["number", "null"]},
                "tp3_open": {"type": ["boolean", "null"]},
                "intent": {"type": ["string", "null"]},
                "pct": {"type": ["number", "null"]},
                "tp_stage": {"type": ["integer", "null"]},
                "timeframe": {"type": ["string", "null"]},
                "instrument": {"type": ["string", "null"]},
                "pinned_levels": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                },
            },
            "required": [
                "type",
                "direction",
                "entry_low",
                "entry_high",
                "sl",
                "tp1",
                "tp2",
                "tp3",
                "tp3_open",
                "intent",
                "pct",
                "tp_stage",
                "timeframe",
                "instrument",
                "pinned_levels",
            ],
        },
        "caller_action": {"type": "string", "enum": ["DISPATCH", "HOLD", "CONFIRM"]},
    },
    "required": ["image_type", "confidence", "extracted_text", "structured_data", "caller_action"],
}


@dataclass
class VisionResult:
    extracted_text: str
    structured_data: dict[str, Any]
    confidence: str
    image_type: str
    caller_action: str
    processing_ms: int
    file_size_kb: int
    image_hash: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "extracted_text": self.extracted_text,
            "structured_data": self.structured_data,
            "confidence": self.confidence,
            "image_type": self.image_type,
            "caller_action": self.caller_action,
            "processing_ms": self.processing_ms,
            "file_size_kb": self.file_size_kb,
            "image_hash": self.image_hash,
            "error": self.error,
        }


def _safe_result(
    image_hash: str,
    file_size_kb: int,
    started: float,
    error: str,
) -> VisionResult:
    return VisionResult(
        extracted_text="Unable to extract reliable data from image.",
        structured_data={"type": "IGNORE"},
        confidence="LOW",
        image_type="UNKNOWN",
        caller_action="HOLD",
        processing_ms=int((time.time() - started) * 1000),
        file_size_kb=file_size_kb,
        image_hash=image_hash,
        error=error,
    )


class Vision:
    def __init__(self, claude: Anthropic | None = None):
        self.claude = claude

    @staticmethod
    def file_hash(image_path: str | Path) -> str:
        p = Path(image_path)
        data = p.read_bytes()
        return hashlib.md5(data).hexdigest()

    @staticmethod
    def _mime_for(path: Path) -> str:
        mt, _ = mimetypes.guess_type(str(path))
        if mt == "image/jpg":
            return "image/jpeg"
        if mt in ALLOWED_MIME:
            return mt
        if Image is None:
            return mt or "application/octet-stream"
        # Fallback: inspect actual image content when temp files have no extension (e.g. *.img)
        try:
            with Image.open(path) as im:
                fmt = (im.format or "").upper()
            if fmt == "JPEG":
                return "image/jpeg"
            if fmt == "PNG":
                return "image/png"
            if fmt == "GIF":
                return "image/gif"
            if fmt == "WEBP":
                return "image/webp"
        except Exception:
            pass
        return mt or "application/octet-stream"

    @staticmethod
    def _validate_image(path: Path) -> tuple[int, str]:
        if Image is None:
            detail = str(_PIL_IMPORT_ERROR) if _PIL_IMPORT_ERROR else "Pillow is not installed"
            raise RuntimeError(f"Pillow unavailable: {detail}")
        size_bytes = path.stat().st_size
        if size_bytes > int(VISION_MAX_IMAGE_MB * 1024 * 1024):
            raise ValueError(f"image too large: {size_bytes} bytes")
        mime = Vision._mime_for(path)
        with Image.open(path) as img:
            img.verify()
        return size_bytes, mime

    @staticmethod
    def _confidence_rank(conf: str) -> int:
        return {"LOW": 0, "MEDIUM": 1, "HIGH": 2}.get(str(conf).upper(), 0)

    @staticmethod
    def _numeric_candidates(text: str) -> list[str]:
        if not text:
            return []
        vals = re.findall(r"\b\d{3,5}\.\d{1,3}\b", text)
        out: list[str] = []
        for v in vals:
            if v not in out:
                out.append(v)
        return out

    @staticmethod
    def _infer_symbol_timeframe(text: str) -> tuple[str | None, str | None]:
        if not text:
            return None, None
        sym_match = re.search(r"\b(XAUUSD|GOLD|XAU)\b", text.upper())
        tf_match = re.search(r"\b(M1|M5|M15|M30|H1|H4|D1|W1)\b", text.upper())
        symbol = sym_match.group(1) if sym_match else None
        if symbol in ("GOLD", "XAU"):
            symbol = "XAUUSD"
        timeframe = tf_match.group(1) if tf_match else None
        return symbol, timeframe

    @staticmethod
    def _encode_for_model(path: Path, mime: str) -> tuple[str, str]:
        try:
            with Image.open(path) as img:
                w, h = img.size
                needs_png = mime not in ALLOWED_MIME
                if max(w, h) > VISION_MAX_EDGE_PX or needs_png:
                    ratio = VISION_MAX_EDGE_PX / float(max(w, h))
                    if max(w, h) > VISION_MAX_EDGE_PX:
                        new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
                        img = img.convert("RGB").resize(new_size, Image.Resampling.LANCZOS)
                    else:
                        img = img.convert("RGB")
                    with tempfile.NamedTemporaryFile(prefix="vision_resized_", suffix=".png", delete=False) as tmp:
                        tmp_path = Path(tmp.name)
                    try:
                        img.save(tmp_path, format="PNG", optimize=True)
                        b64 = base64.b64encode(tmp_path.read_bytes()).decode("utf-8")
                        return b64, "image/png"
                    finally:
                        try:
                            tmp_path.unlink(missing_ok=True)
                        except Exception:
                            pass
        except Exception:
            pass
        b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        return b64, mime

    @staticmethod
    def _focus_crop_path(path: Path) -> Path | None:
        try:
            with Image.open(path) as img:
                w, h = img.size
                left = int(w * 0.68)
                top = int(h * 0.08)
                right = w
                bottom = int(h * 0.98)
                if right - left < 60 or bottom - top < 60:
                    return None
                crop = img.crop((left, top, right, bottom))
                with tempfile.NamedTemporaryFile(prefix="vision_focus_", suffix=".png", delete=False) as tmp:
                    out = Path(tmp.name)
                crop.save(out, format="PNG", optimize=True)
                return out
        except Exception:
            return None

    @staticmethod
    def _ocr_numeric_hints(path: Path) -> list[str]:
        if not VISION_OCR_FALLBACK:
            return []
        try:
            import cv2  # type: ignore
            import pytesseract  # type: ignore
        except Exception:
            return []
        try:
            img = cv2.imread(str(path))
            if img is None:
                return []
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            blur = cv2.GaussianBlur(gray, (3, 3), 0)
            thr = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            txt = pytesseract.image_to_string(
                thr,
                config="--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789.",
            )
            vals = Vision._numeric_candidates(txt)
            # keep likely chart price labels only
            out = [v for v in vals if 1000 <= float(v) <= 6000]
            dedup: list[str] = []
            for v in out:
                if v not in dedup:
                    dedup.append(v)
            return dedup[:12]
        except Exception:
            return []

    def _call_claude(self, *, image_path: Path, mime: str, caption: str, context_hint: str, caller: str, focus: str) -> dict[str, Any]:
        b64, encoded_mime = self._encode_for_model(image_path, mime)
        user_text = (
            f"context_hint={context_hint}\ncaller={caller}\nfocus={focus}\ncaption={caption or ''}\n"
            "Extract actionable trading data and visible chart price labels."
        )
        resp = self.claude.messages.create(
            model=VISION_MODEL,
            max_tokens=900,
            temperature=0,
            system=SYSTEM_PROMPT,
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": OUTPUT_SCHEMA,
                }
            },
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": encoded_mime, "data": b64}},
                        {"type": "text", "text": user_text},
                    ],
                }
            ],
        )
        raw_text = resp.content[0].text.strip()
        return json.loads(raw_text)

    def _apply_postprocess(self, raw: dict[str, Any], *, caption: str, context_hint: str, numeric_hints: list[str]) -> dict[str, Any]:
        out = dict(raw or {})
        sd = out.get("structured_data")
        if not isinstance(sd, dict):
            sd = {"type": "IGNORE"}
        levels = sd.get("pinned_levels")
        if not isinstance(levels, list):
            levels = []
        merged_levels: list[str] = []
        for v in levels:
            if isinstance(v, str) and v not in merged_levels:
                merged_levels.append(v)
        for src in (
            out.get("extracted_text", ""),
            json.dumps(sd, default=str),
            caption or "",
            " ".join(numeric_hints),
        ):
            for cand in self._numeric_candidates(str(src)):
                if cand not in merged_levels and 1000 <= float(cand) <= 6000:
                    merged_levels.append(cand)
        if merged_levels:
            sd["pinned_levels"] = merged_levels[:12]
        else:
            sd["pinned_levels"] = []
        symbol, tf = self._infer_symbol_timeframe(
            f"{out.get('extracted_text','')} {caption or ''} {json.dumps(sd, default=str)} {context_hint or ''}"
        )
        if not sd.get("instrument") and symbol:
            sd["instrument"] = symbol
        if not sd.get("timeframe") and tf:
            sd["timeframe"] = tf
        out["structured_data"] = sd
        return out

    @staticmethod
    def _normalized_result(raw: dict[str, Any], base: dict[str, Any]) -> VisionResult:
        conf = str(raw.get("confidence", "LOW")).upper()
        if conf not in ("HIGH", "MEDIUM", "LOW"):
            conf = "LOW"
        image_type = str(raw.get("image_type", "UNKNOWN")).upper()
        if image_type not in ("SIGNAL", "CHART", "MT5", "UNKNOWN"):
            image_type = "UNKNOWN"
        caller_action = str(raw.get("caller_action", "HOLD")).upper()
        if caller_action not in ("DISPATCH", "HOLD", "CONFIRM"):
            caller_action = "HOLD"
        structured = raw.get("structured_data")
        if not isinstance(structured, dict):
            structured = {"type": "IGNORE"}
        extracted = str(raw.get("extracted_text", "")).strip() or "No clear extraction."
        return VisionResult(
            extracted_text=extracted,
            structured_data=structured,
            confidence=conf,
            image_type=image_type,
            caller_action=caller_action,
            processing_ms=base["processing_ms"],
            file_size_kb=base["file_size_kb"],
            image_hash=base["image_hash"],
            error=None,
        )

    def extract(
        self,
        image_path: str | Path,
        caption: str = "",
        context_hint: str = "GENERAL",
        caller: str = "HERALD",
    ) -> VisionResult:
        started = time.time()
        p = Path(image_path)
        if not VISION_ENABLED:
            return _safe_result("disabled", 0, started, "VISION_DISABLED")
        if not p.exists() or not p.is_file():
            return _safe_result("missing", 0, started, "IMAGE_NOT_FOUND")
        try:
            image_hash = self.file_hash(p)
        except Exception:
            image_hash = "hash_error"
        file_size_kb = 0
        try:
            size_bytes, mime = self._validate_image(p)
            file_size_kb = int(size_bytes / 1024)
        except Exception as e:
            return _safe_result(image_hash, file_size_kb, started, f"VALIDATION_ERROR:{e}")

        if not self.claude:
            return _safe_result(image_hash, file_size_kb, started, "CLAUDE_NOT_CONFIGURED")

        try:
            raw = self._call_claude(
                image_path=p,
                mime=mime,
                caption=caption,
                context_hint=context_hint,
                caller=caller,
                focus="FULL_IMAGE",
            )
            focus_path = None
            if VISION_SECOND_PASS:
                sd0 = raw.get("structured_data") if isinstance(raw, dict) else {}
                levels0 = (sd0 or {}).get("pinned_levels") if isinstance(sd0, dict) else []
                need_second = (
                    str(raw.get("confidence", "LOW")).upper() == "LOW"
                    or (isinstance(levels0, list) and len(levels0) == 0)
                )
                if need_second:
                    focus_path = self._focus_crop_path(p)
                    if focus_path:
                        raw2 = self._call_claude(
                            image_path=focus_path,
                            mime="image/png",
                            caption=caption,
                            context_hint=context_hint,
                            caller=caller,
                            focus="RIGHT_PRICE_AXIS",
                        )
                        r1 = self._confidence_rank(str(raw.get("confidence", "LOW")))
                        r2 = self._confidence_rank(str(raw2.get("confidence", "LOW")))
                        l1 = len((raw.get("structured_data") or {}).get("pinned_levels") or []) if isinstance(raw.get("structured_data"), dict) else 0
                        l2 = len((raw2.get("structured_data") or {}).get("pinned_levels") or []) if isinstance(raw2.get("structured_data"), dict) else 0
                        if (r2 > r1) or (l2 > l1):
                            raw = raw2
            ocr_hints = self._ocr_numeric_hints(focus_path or p)
            raw = self._apply_postprocess(
                raw,
                caption=caption,
                context_hint=context_hint,
                numeric_hints=ocr_hints,
            )
            base = {
                "processing_ms": int((time.time() - started) * 1000),
                "file_size_kb": file_size_kb,
                "image_hash": image_hash,
            }
            if focus_path:
                try:
                    focus_path.unlink(missing_ok=True)
                except Exception:
                    pass
            return self._normalized_result(raw, base)
        except Exception as e:
            log.error("VISION extraction error: %s", e)
            return _safe_result(image_hash, file_size_kb, started, f"EXTRACT_ERROR:{e}")
