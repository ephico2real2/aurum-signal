#!/usr/bin/env python3
"""
Regenerate the /api/scribe/query requestBody examples in schemas/openapi.yaml
from schemas/scribe_query_examples.json (single source of truth).

Usage:
  python3 scripts/sync_openapi_scribe_examples.py
  make sync-openapi-scribe
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "schemas" / "scribe_query_examples.json"
YAML_PATH = ROOT / "schemas" / "openapi.yaml"

BEGIN = "            # --BEGIN_SCRIBE_OPENAPI_EXAMPLES--"
END = "            # --END_SCRIBE_OPENAPI_EXAMPLES--"


def build_block(examples: list[dict]) -> str:
    lines = [BEGIN, "            examples:"]
    for i, ex in enumerate(examples):
        sid = ex["id"]
        summ = f"{i + 1} · {ex['summary']}"
        sql = ex["sql"]
        lines.append(f"              {sid}:")
        lines.append(f"                summary: {json.dumps(summ, ensure_ascii=False)}")
        lines.append("                value:")
        lines.append(f"                  sql: {json.dumps(sql, ensure_ascii=False)}")
    lines.append(END)
    return "\n".join(lines) + "\n"


def main() -> int:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    examples = data["examples"]
    generated = build_block(examples)
    text = YAML_PATH.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        print("error: openapi.yaml missing SCRIBE example markers", file=sys.stderr)
        print("  expected lines containing BEGIN/END SCRIBE_OPENAPI_EXAMPLES", file=sys.stderr)
        return 1
    i0 = text.index(BEGIN)
    i1 = text.index(END)
    line_after = text.find("\n", i1)
    if line_after < 0:
        line_after = len(text)
    else:
        line_after += 1
    new_text = text[:i0] + generated + text[line_after:]
    YAML_PATH.write_text(new_text, encoding="utf-8")
    print(f"updated {YAML_PATH} with {len(examples)} scribe examples from {JSON_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
