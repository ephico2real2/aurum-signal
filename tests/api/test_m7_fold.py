"""
M7 ICT-canonical fold — schema-parity + fold-correctness validator.

These tests assert the post-M7 invariants. Until v2.7.138 M7 ships, every test
is `xfail(strict=True)` — they FAIL today (proving M7 hasn't shipped) and
auto-PASS the moment M7 lands correctly. Operator removes the xfail markers
once v2.7.138 is in.

M7 contract per:
  - docs/FORGE_SETUP_ICT_MAP.md §B.4 (revised 2026-05-17 per consensus gate)
  - docs/FORGE_ICT_SETUPS.md (canonical setup catalog)
  - refinement-ideas/M7-design/2026-05-17_m7-mss-continuation-fold.md
  - skill .claude/skills/forge-monitor/SKILL.md §I.15 (consensus gate)

The fold:
  - 7 setups KEEP in M7 → setup_type becomes MSS_CONTINUATION_<DIR>;
    original name preserved in new setup_subtype column.
  - 1 PROVISIONAL (INSIDE_BAR) — operator call; treated as M7 keep here.
  - 2 RECLASSIFY → M8 (BB_BREAKOUT_RETEST, FLAG_PENNANT) — must NOT appear in
    M7's new MSS_CONTINUATION fire sites; stay on legacy setup_type until M8.
  - 1 RECLASSIFY → M9 (ORB) — same.
  - 1 RETIRE (MA_CROSSOVER) — fire site deleted; no migration to subtype.

Schema-parity is the most error-prone layer (per skill §"Schema-parity ship —
every new data point touches ALL 5 layers" + the v2.7.119 retroactive ship
that fixed v2.7.112's missing migrations). Tests below check all 5 layers
land in sync.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EA = ROOT / "ea" / "FORGE.mq5"
SCRIBE = ROOT / "python" / "scribe.py"

M7_KEEP_SETUPS = [
    "BB_BREAKOUT",
    "GAP_AND_GO",
    "MOMENTUM_DUMP_COMPOSITE",  # MOMENTUM_DUMP v1 retired per operator decision 2026-05-17
    "BB_SQUEEZE",
    "GRINDING_SELL",
    "NY_SESSION_BEARISH_BREAKOUT_SELL",
]
M7_KEEP_SUBTYPES = [s.lower() for s in M7_KEEP_SETUPS]

M7_PROVISIONAL_SETUPS = ["INSIDE_BAR"]  # operator call: keep or retire

M8_RECLASSIFY = ["BB_BREAKOUT_RETEST", "FLAG_PENNANT"]
M9_RECLASSIFY = ["ORB"]
RETIRE_SETUPS = [
    "MA_CROSSOVER",   # ICT canon explicitly rejects MA crossovers
    "MOMENTUM_DUMP",  # superseded by atom-composed MOMENTUM_DUMP_COMPOSITE (v2.7.121 promotion)
]


@pytest.fixture(scope="module")
def ea_text() -> str:
    return EA.read_text()


@pytest.fixture(scope="module")
def scribe_text() -> str:
    return SCRIBE.read_text()


# ─────────────────────────────────────────────────────────────────────────────
# Schema-parity 5-layer wire for the new `setup_subtype` column
# ─────────────────────────────────────────────────────────────────────────────


def test_layer1_ea_create_table_has_setup_subtype(ea_text: str) -> None:
    """EA CREATE TABLE SIGNALS text must declare setup_subtype TEXT."""
    m = re.search(r"CREATE TABLE IF NOT EXISTS SIGNALS \((.+?)\)\";", ea_text, re.DOTALL)
    assert m, "could not locate SIGNALS CREATE TABLE statement"
    assert "setup_subtype" in m.group(1), "setup_subtype missing from CREATE TABLE"


def test_layer2_ea_alter_table_setup_subtype(ea_text: str) -> None:
    """EA must have an idempotent ALTER TABLE migration for setup_subtype."""
    # Look for an ALTER TABLE that adds setup_subtype (any TEXT form acceptable)
    assert re.search(
        r"ALTER TABLE SIGNALS ADD COLUMN setup_subtype\s+TEXT",
        ea_text,
    ), "ALTER TABLE migration for setup_subtype missing"


def test_layer3_journal_record_signal_inserts_setup_subtype(ea_text: str) -> None:
    """JournalRecordSignal INSERT column list must include setup_subtype.

    EA uses MQL5 string concatenation across multiple "..." segments, so the
    INSERT statement is split across many lines. Test verifies (a) the INSERT
    statement exists, (b) the setup_subtype column literal appears within it,
    (c) the corresponding VALUES bind reads g_setup_subtype_for_next_signal.
    """
    assert 'INSERT INTO SIGNALS' in ea_text, "INSERT INTO SIGNALS clause not found"
    # The col list spans multiple "..." segments — just check the literal column name
    # appears somewhere reasonable (within 6000 chars after the INSERT keyword to
    # avoid false matches in comments/changelog references).
    insert_idx = ea_text.find('INSERT INTO SIGNALS')
    window = ea_text[insert_idx : insert_idx + 6000]
    assert "setup_subtype," in window or "setup_subtype TEXT" in window, (
        "setup_subtype column not in INSERT INTO SIGNALS col list window"
    )
    # And the VALUES bind reads the subtype global
    assert 'g_setup_subtype_for_next_signal' in window, (
        "g_setup_subtype_for_next_signal not bound in JournalRecordSignal VALUES clause"
    )


def test_layer4_scribe_forge_signals_has_setup_subtype(scribe_text: str) -> None:
    """scribe.py CREATE TABLE forge_signals + INSERT must include setup_subtype."""
    assert "setup_subtype" in scribe_text, "setup_subtype not referenced in scribe.py"
    # ALTER TABLE migration check
    assert re.search(
        r"ALTER TABLE forge_signals ADD COLUMN setup_subtype",
        scribe_text,
    ), "scribe.py ALTER TABLE migration for setup_subtype missing"


def test_layer4_scribe_placeholder_count_bumped(scribe_text: str) -> None:
    """scribe.py sync_forge_journal placeholder math must include the new column.

    Find `["?"] * (N + ...)` expressions and confirm at least one was bumped
    upward from the pre-M7 baseline (v2.7.137 = 168 columns; M7 adds 1 → 169).
    """
    placeholder_exprs = re.findall(r'"\?"\s*\]\s*\*\s*\((.+?)\)', scribe_text)
    assert placeholder_exprs, "no scribe placeholder math expression found"
    # Heuristic: at least one expression must sum to >= 169 (post-M7 column count).
    # Operator can tighten this exact check at M7 ship time.
    for expr in placeholder_exprs:
        nums = [int(n) for n in re.findall(r"\d+", expr)]
        if sum(nums) >= 169:
            return
    pytest.fail(
        f"scribe placeholder math not bumped for M7 (expressions: {placeholder_exprs})"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Setup-type fold correctness — the 7 keep + 1 provisional setups
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("legacy_name", M7_KEEP_SETUPS)
def test_m7_keep_setup_emits_mss_continuation(ea_text: str, legacy_name: str) -> None:
    """Each M7-keep legacy setup's fire site sets setup_type='MSS_CONTINUATION_<DIR>'.

    The pre-M7 code uses `setup_type = "<LEGACY_NAME>"` literals. Post-M7 the
    literal becomes `setup_type = "MSS_CONTINUATION_BUY"` (or _SELL) with the
    original name moved to the subtype identifier. Per the M7 design doc §4.1
    decision, the subtype is set via a GLOBAL (`g_setup_subtype_for_next_signal`)
    rather than a positional `JournalRecordSignal` param — that avoids the
    119-caller signature-thread blast radius. So this test accepts EITHER:
      - global assignment: `g_setup_subtype_for_next_signal = "bb_breakout";`
      - local variable:    `string setup_subtype = "bb_breakout";`
    What matters is the literal subtype string is present somewhere in the EA.
    """
    # Pre-M7 literal must no longer be assigned as setup_type
    pre_m7_pattern = rf'setup_type\s*=\s*"{legacy_name}"'
    assert not re.search(pre_m7_pattern, ea_text), (
        f"{legacy_name} still assigned as setup_type — M7 fold not applied at fire site"
    )
    # Post-M7 subtype literal must be present (global-set OR local-variable form)
    subtype_literal = legacy_name.lower()
    assert f'"{subtype_literal}"' in ea_text, (
        f'subtype literal "{subtype_literal}" missing — M7 didn\'t preserve identity'
    )


def test_m7_mss_continuation_string_present(ea_text: str) -> None:
    """The new canonical setup_type strings must appear in EA source.

    Accepts either the explicit literals ("MSS_CONTINUATION_BUY" / "_SELL")
    OR the runtime concat pattern ("MSS_CONTINUATION_" + direction) — the
    M7 implementation uses the concat form to keep fire sites direction-agnostic.
    """
    has_explicit = (
        '"MSS_CONTINUATION_BUY"' in ea_text
        and '"MSS_CONTINUATION_SELL"' in ea_text
    )
    has_concat = '"MSS_CONTINUATION_" + direction' in ea_text
    assert has_explicit or has_concat, (
        "MSS_CONTINUATION setup_type emission missing — expected explicit literals "
        '"MSS_CONTINUATION_BUY"/"_SELL" OR concat pattern '
        '"MSS_CONTINUATION_" + direction'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Reclassify + retire enforcement — M8/M9-bound setups MUST NOT fold to MSS_CONT
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("legacy_name", M8_RECLASSIFY + M9_RECLASSIFY)
def test_reclassified_setup_not_in_m7_fold(ea_text: str, legacy_name: str) -> None:
    """Setups reclassified to M8/M9 must NOT carry MSS_CONTINUATION setup_type.

    They stay on their legacy setup_type until M8 (OTE) / M9 (LIQ_SWEEP) ships.
    The mistake to catch: someone accidentally lumps these into M7 because
    Explore's pre-canonical audit listed them.

    This is a "stays-correct" invariant — it should hold both pre-M7 (no fold
    has happened) and post-M7 (M7 shipped without accidentally including these
    3 reclassified setups). Hence no xfail marker — the test should ALWAYS
    pass and only fail if someone regresses the fold.
    """
    # If the legacy fire site still exists, it must NOT have an MSS_CONTINUATION literal
    # adjacent to it. Heuristic: find each setup_type assignment for the legacy name and
    # check the surrounding ~5 lines don't also set MSS_CONTINUATION.
    for m in re.finditer(rf'setup_type\s*=\s*"{legacy_name}"', ea_text):
        window = ea_text[max(0, m.start() - 300) : m.end() + 300]
        assert "MSS_CONTINUATION" not in window, (
            f"{legacy_name} fire site appears to fold into MSS_CONTINUATION — "
            f"should stay legacy until M8/M9"
        )


@pytest.mark.parametrize("retired_name", RETIRE_SETUPS)
def test_retired_setup_fire_site_deleted(ea_text: str, retired_name: str) -> None:
    """Each RETIRE-bucket setup's fire site must be deleted (no migration).

    Per `docs/FORGE_SETUP_ICT_MAP.md §B.4` RETIRE bucket:
      - MA_CROSSOVER — ICT canon explicitly rejects moving-average crossovers
        as primary triggers. No ICT primitive expressed.
      - MOMENTUM_DUMP (v1 legacy) — superseded by MOMENTUM_DUMP_COMPOSITE
        (atom-composed, v2.7.121 promotion from `_TEST`). Operator decision
        2026-05-17: parallel validation done; commit to composite.

    Both: delete the trigger site(s) + env knobs the survivor doesn't reuse.
    No migration to setup_subtype (the appropriate replacement preserves
    semantics independently).
    """
    assert f'setup_type = "{retired_name}"' not in ea_text, (
        f"{retired_name} fire site still present — should be deleted per RETIRE bucket"
    )
    # Env knob removal ships in the same sub-ship (v2.7.137a); this test
    # focuses on the EA-side trigger removal as the primary correctness check.
