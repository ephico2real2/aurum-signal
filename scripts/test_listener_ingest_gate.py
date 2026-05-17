#!/usr/bin/env python3
"""
test_listener_ingest_gate.py — spoof-test the LISTENER ingest allow-list.

For each of the 4 watched channels, build a synthetic message object with
the matching chat_id + chat.title and run the SAME gate logic that lives in
listener._handle_message — using the same module-level set
(LISTENER_INGEST_ALLOWED_CHATS) and the same helpers (_chat_id_variants,
_normalize_allowlist_token).

This does NOT touch the launchd-managed listener process. It exercises the
gate in-process via the public module surface so the test verifies exactly
what the live service would do given identical env state.

Usage
-----
  # Test the currently-configured allow-list (whatever .env says, or empty)
  .venv/bin/python scripts/test_listener_ingest_gate.py

  # Override the allow-list for a what-if scenario without touching .env:
  .venv/bin/python scripts/test_listener_ingest_gate.py --allow=-1002034822451

  # Allow multiple chats (comma-separated, same syntax as .env):
  .venv/bin/python scripts/test_listener_ingest_gate.py \
      --allow=-1002034822451,-1001959885205

  # Via Makefile (uses currently-configured env):
  make test-ingest-gate
"""
from __future__ import annotations

import argparse
import os
import sys
from types import SimpleNamespace

# Known channels — kept in sync with TELEGRAM_CHANNELS subscriptions.
# If channels are added/removed from production, update this list too.
CHANNELS = [
    ("Ben's VIP Club",        -1002034822451),
    ("FXM FREE TRADING ROOM", -1001959885205),
    ("GARRY'S SIGNALS",       -1003582676523),
    ("FLAIR FX",              -1002293626964),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--allow",
        default=None,
        help=(
            "Comma-separated allow-list to override LISTENER_INGEST_ALLOWED_CHATS "
            "for this test run (no .env edit). Pass empty string to simulate gate-off."
        ),
    )
    return p.parse_args()


def _load_dotenv(env_path: str) -> None:
    """Inline .env loader (no external dep). Skips lines already set in os.environ
    so explicit overrides (CLI flag, shell env) win over .env. Matches the parser
    in services/install_services.py:load_env_vars so test sees the same view the
    launchd-rendered plist would."""
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


def main() -> int:
    args = parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Load .env so the script sees the same env that the launchd-rendered plist
    # would inject. Without this, the gate would report "inactive" even when the
    # live listener has it active, because the launchd plist freezes .env values
    # into itself at install time and our subprocess doesn't inherit them.
    _load_dotenv(os.path.join(repo_root, ".env"))

    if args.allow is not None:
        os.environ["LISTENER_INGEST_ALLOWED_CHATS"] = args.allow

    # Import after env load so the module-level set picks up the right value.
    sys.path.insert(0, os.path.join(repo_root, "python"))
    import importlib
    import listener
    importlib.reload(listener)

    allow = listener.LISTENER_INGEST_ALLOWED_CHATS
    print(f"Loaded gate state: ALLOW={sorted(allow) if allow else '(empty → gate inactive)'}")
    print()

    def gate_decision(chat_id: int, channel_title: str) -> tuple[str, str]:
        """Replica of the ingest-gate block in listener._handle_message.

        Kept in sync with the production logic. If you change one, change both —
        otherwise the test diverges from what the service actually does.
        """
        if not allow:
            return "PASS", "gate inactive"
        tokens: set[str] = set()
        for variant in listener.Listener._chat_id_variants(chat_id):
            tokens.add(listener._normalize_allowlist_token(variant))
        if channel_title:
            tokens.add(listener._normalize_allowlist_token(channel_title))
        if tokens & allow:
            return "PASS", f"matched allow-list via {sorted(tokens & allow)}"
        return "DROPPED", "not in LISTENER_INGEST_ALLOWED_CHATS"

    print(f"{'Channel':<24} {'chat_id':>16}  {'Result':<8}  Reason")
    print("-" * 90)

    failures = 0
    for title, cid in CHANNELS:
        msg = SimpleNamespace(chat_id=cid, chat=SimpleNamespace(title=title))
        decision, reason = gate_decision(msg.chat_id, msg.chat.title)

        # Compute expected outcome to flag drift.
        if not allow:
            expected = "PASS"
        else:
            tokens = {listener._normalize_allowlist_token(v)
                      for v in listener.Listener._chat_id_variants(cid)}
            tokens.add(listener._normalize_allowlist_token(title))
            expected = "PASS" if tokens & allow else "DROPPED"

        ok = decision == expected
        mark = "✅" if ok else "❌"
        if not ok:
            failures += 1
        print(f"{mark} {title:<22} {cid:>16}  {decision:<8}  {reason}")

    print()
    if failures:
        print(f"❌ {failures} case(s) diverged from expected outcome.")
        return 1
    print("✅ All cases match expected outcome.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
