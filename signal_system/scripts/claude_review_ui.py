#!/usr/bin/env python3
"""
claude_review_ui.py — Build a markdown prompt from Playwright ATHENA audit JSON.

Usage:
  python3 scripts/claude_review_ui.py
  python3 scripts/claude_review_ui.py --quiet   # only write file, minimal stdout

Requires: tests/results/athena-ui-audit.json from `make test-ui-audit`
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "tests" / "results" / "athena-ui-audit.json"
OUT = ROOT / "tests" / "results" / "claude-review-ui-prompt.md"


def build_prompt(data: dict) -> str:
    lines = [
        "# ATHENA dashboard — UI audit handoff for Claude Code",
        "",
        "Review and update the Signal System dashboard using the facts below.",
        "",
        "## How this was produced",
        "",
        "- Playwright spec `tests/ui/test_athena_audit.spec.js`",
        "- Screenshots: `tests/results/athena-ui/screens/{groups,activity,signals,perf}.png`",
        "",
        "## API snapshot at audit time (`/api/live` subset)",
        "",
        "```json",
        json.dumps(data.get("api_live_summary") or {}, indent=2),
        "```",
        "",
        "## Console errors (filtered)",
        "",
        "```",
        *(data.get("console_errors_filtered") or ["(none)"]),
        "```",
        "",
        "## Per-tab text snippets (truncated in JSON; open screenshots for pixels)",
        "",
    ]
    for t in data.get("tabs") or []:
        tid = t.get("id", "?")
        lines.append(f"### Tab `{tid}`")
        lines.append("")
        if t.get("findings"):
            lines.append("**Findings:**")
            for f in t["findings"]:
                lines.append(f"- {f}")
            lines.append("")
        snip = (t.get("text_snippet") or "")[:3500]
        lines.append("```")
        lines.append(snip + ("\n…" if len(t.get("text_snippet") or "") > 3500 else ""))
        lines.append("```")
        lines.append("")

    lines.extend([
        "## Mock / static UI flagged by audit",
        "",
    ])
    for m in data.get("mock_or_static_ui") or []:
        lines.append(f"- **{m.get('tab')}**: {m.get('issue')} — `{m.get('code')}`")
    if not data.get("mock_or_static_ui"):
        lines.append("- (none auto-detected)")
    lines.append("")
    lines.append("## Suggested tasks")
    lines.append("")
    for s in data.get("suggested_next_steps_for_claude") or []:
        lines.append(f"- {s}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "**Instruction for Claude:** Prioritize replacing demo Signals rows and mock sparkline "
        "with real SCRIBE/API data; keep layout and theme; add empty states when no data."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--quiet", action="store_true", help="Write file only")
    args = p.parse_args()

    if not AUDIT.exists():
        print(
            f"Missing {AUDIT}\nRun first: make test-ui-audit",
            file=sys.stderr,
        )
        return 1

    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    md = build_prompt(data)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(md, encoding="utf-8")
    if args.quiet:
        print(str(OUT))
    else:
        print(f"Wrote {OUT}")
        print()
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
