#!/usr/bin/env python3
"""
test_aurum_ben_spoof.py — spoof a message from Ben's VIP Club into AURUM.

AURUM is currently gated to a single chat (TELEGRAM_CHAT_ID) — Ben's channel
messages can never reach it through the normal bot path. This script bypasses
that gate by calling aurum.Aurum.ask() directly with synthetic text labeled as
coming from Ben's. We monkey-patch all side-effect surfaces (scribe write,
command extraction, chart MCP execution, Herald Telegram post) so the test is
non-destructive — it captures AURUM's natural-language response only and
makes no real trades, no Telegram noise, no scribe rows.

Usage
-----
  # Default spoof text (informational; safe — no tradable instruction)
  .venv/bin/python scripts/test_aurum_ben_spoof.py

  # Custom text
  .venv/bin/python scripts/test_aurum_ben_spoof.py --text "BUY XAU 3210 SL 3200 TP 3225"

  # Via Makefile (loads .env automatically)
  make test-aurum-ben-spoof
  make test-aurum-ben-spoof TEXT="your custom text"
"""
from __future__ import annotations

import argparse
import os
import sys

DEFAULT_SPOOF_TEXT = (
    "[Spoof test relayed from Ben's VIP Club]\n"
    "Watching XAUUSD around 3210-3215 zone for a bounce. London close looking "
    "weak. Will share entry if structure holds — no action yet."
)

BENS_CHAT_ID = -1002034822451  # informational label; not actually used by ask()
SPOOF_SOURCE = "TELEGRAM_BEN_SPOOF_TEST"


def _load_dotenv(env_path: str) -> None:
    """Inline .env loader — same shape as scripts/test_listener_ingest_gate.py.
    Skips keys already in os.environ so CLI/shell overrides win."""
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key in os.environ:
                continue
            os.environ[key] = val.strip().strip('"').strip("'")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--text",
        default=DEFAULT_SPOOF_TEXT,
        help="Spoofed message text. Default is an informational watch — change "
             "to a real signal format to see AURUM's response shape.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _load_dotenv(os.path.join(repo_root, ".env"))
    sys.path.insert(0, os.path.join(repo_root, "python"))

    from aurum import Aurum

    aurum = Aurum()

    # Disable side-effect surfaces so the spoof is non-destructive.
    # AURUM's ask() will still build the full system prompt + conversation
    # context + call Claude, but none of the post-call writes will fire.
    captured: dict = {"commands_extracted": False, "chart_executed": False,
                      "scribe_logged": False, "herald_sent": False}
    aurum._check_for_command = lambda *a, **kw: None
    def _no_extract(*a, **kw):
        captured["commands_extracted"] = True
    aurum._extract_json_commands_from_response = _no_extract
    def _no_chart(*a, **kw):
        captured["chart_executed"] = True
        return ""
    aurum._execute_chart_commands = _no_chart
    def _no_scribe(**kw):
        captured["scribe_logged"] = True
    aurum.scribe.log_aurum_conversation = _no_scribe
    def _no_herald(*a, **kw):
        captured["herald_sent"] = True
    if hasattr(aurum, "herald") and aurum.herald is not None:
        aurum.herald.send = _no_herald

    print(f"Spoofing chat_id={BENS_CHAT_ID} (Ben's VIP Club) → AURUM.ask(source={SPOOF_SOURCE!r})")
    print(f"Side-effect surfaces (scribe / herald / command-extract / chart-MCP): DISABLED")
    print()
    print("─" * 72)
    print("Spoofed message text:")
    print("─" * 72)
    print(args.text)
    print()
    print("─" * 72)
    print("AURUM response:")
    print("─" * 72)

    response = aurum.ask(args.text, source=SPOOF_SOURCE)
    print(response)
    print()
    print("─" * 72)
    print("Side-effect-attempt audit (would have fired if not patched):")
    print(f"  scribe.log_aurum_conversation : {'TRIED' if captured['scribe_logged'] else 'skipped'}")
    print(f"  herald.send                   : {'TRIED' if captured['herald_sent'] else 'skipped'}")
    print(f"  _extract_json_commands        : {'TRIED' if captured['commands_extracted'] else 'skipped'}")
    print(f"  _execute_chart_commands       : {'TRIED' if captured['chart_executed'] else 'skipped'}")
    print(
        "  ↑ TRIED means AURUM's response would have triggered that path in prod. "
        "Useful to know if a custom spoof emits JSON commands etc."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
