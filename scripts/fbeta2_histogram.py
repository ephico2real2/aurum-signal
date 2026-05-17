#!/usr/bin/env python3
"""
fbeta2_histogram.py — composite-score vs win/loss distribution analyzer.

The F-β.2 gate-promotion question: at what composite-score threshold does
Mode B "warning de-rate at score < N" cleanly separate winners from losers?

Inputs
------
Reads TAKEN signals + their post-fill group P&L from the FORGE tester
journal DB.

  SIGNALS join: SIGNALS.magic stores only the base MagicNumber (known
  schema limitation per project_magic_number_fix.md). The actual
  group_magic is reconstructed from chronological order within a run:
  the Nth TAKEN signal got group_id = 5000 + N (g_scalper_group_counter
  starts at 5000 per FORGE.mq5:173), so group_magic = magic_base + 5000 + N.
  TRADES rows carry the real group_magic, so we join via reconstructed
  magic.

Takes the category-matched composite score for the signal's direction
(highest of MSS_CONT / OTE_RETR / LIQ_SWEEP for that direction), buckets
per the v2.7.132 conviction-tag definition (H ≥ 7, M 4-6, L 1-3, ? < 1),
sums group P&L from TRADES.

Outputs
-------
- Per-bucket count / win-count / loss-count / win-rate / mean-P&L / total-P&L
- Per-category × bucket breakdown
- Per-score-value cumulative threshold analysis (the Mode B decision input)

Usage
-----
  .venv/bin/python scripts/fbeta2_histogram.py
  .venv/bin/python scripts/fbeta2_histogram.py --run-id 3
  .venv/bin/python scripts/fbeta2_histogram.py --db /custom/path/tester.db
  .venv/bin/python scripts/fbeta2_histogram.py --min-version 2.7.130
"""

from __future__ import annotations

import argparse
import datetime
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_DB = (
    Path.home()
    / "Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Tester/Agent-127.0.0.1-3000/MQL5/Files/FORGE_journal_XAUUSD_tester.db"
)
EA_COUNTER_INIT = 5000  # g_scalper_group_counter init at FORGE.mq5:173


def conviction(score: int) -> str:
    """Match IctComment.mqh::Forge_ConvictionLetter — H/M/L/? buckets."""
    if score >= 7:
        return "H"
    if score >= 4:
        return "M"
    if score >= 1:
        return "L"
    return "?"


def category_score_for_signal(row, direction: str) -> tuple[str, int]:
    """Return (best_category, score) — highest composite in trade direction."""
    suffix = "buy" if direction == "BUY" else "sell"
    candidates = [
        ("MSS_CONT",  row[f"mss_cont_score_{suffix}"]      or 0),
        ("OTE_RETR",  row[f"ote_retrace_score_{suffix}"]   or 0),
        ("LIQ_SWEEP", row[f"liq_sweep_rev_score_{suffix}"] or 0),
    ]
    return max(candidates, key=lambda c: c[1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--run-id", type=int, default=None)
    ap.add_argument("--min-version", type=str, default="2.7.130",
                    help="Lowest forge_version run to include (F-β.1 shipped v2.7.130)")
    args = ap.parse_args()

    if not args.db.exists():
        print(f"ERROR: DB not found at {args.db}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    if args.run_id is not None:
        run_rows = conn.execute(
            "SELECT id, forge_version, magic_base FROM TESTER_RUNS WHERE id=?",
            (args.run_id,),
        ).fetchall()
    else:
        run_rows = conn.execute(
            "SELECT id, forge_version, magic_base FROM TESTER_RUNS "
            "WHERE forge_version >= ? ORDER BY id",
            (args.min_version,),
        ).fetchall()

    if not run_rows:
        print(f"No runs found with forge_version ≥ {args.min_version}", file=sys.stderr)
        return 1

    print(f"# F-β.2 histogram")
    print(f"# DB: {args.db}")
    print(f"# Runs: " + ", ".join(f"run_id={r['id']} v{r['forge_version']}" for r in run_rows))
    print()

    # Per-bucket / per-category aggregators
    bucket_pnl = defaultdict(list)        # conv → list[(pnl, has_fill)]
    cat_bucket_pnl = defaultdict(lambda: defaultdict(list))  # cat → conv → [pnl]
    score_to_pnl = []                     # list[(score, pnl, has_fill, cat)]

    detail_rows = []

    for run in run_rows:
        run_id = run["id"]
        magic_base = run["magic_base"]
        # Pull TAKEN signals in chronological order (ROW_NUMBER assigns sequence)
        signals = conn.execute(
            """
            WITH ranked AS (
              SELECT *,
                     ROW_NUMBER() OVER (ORDER BY time) AS seq
              FROM SIGNALS
              WHERE outcome='TAKEN' AND run_id=?
            )
            SELECT
              r.run_id, r.time, r.setup_type, r.direction, r.seq,
              r.mss_cont_score_buy, r.mss_cont_score_sell,
              r.ote_retrace_score_buy, r.ote_retrace_score_sell,
              r.liq_sweep_rev_score_buy, r.liq_sweep_rev_score_sell,
              COALESCE(g.group_pnl, 0.0) AS group_pnl,
              COALESCE(g.deal_count, 0)  AS deal_count
            FROM ranked r
            LEFT JOIN (
              SELECT magic, run_id, SUM(profit) AS group_pnl, COUNT(*) AS deal_count
              FROM TRADES
              WHERE profit IS NOT NULL AND run_id=?
              GROUP BY magic
            ) g ON g.magic = (? + ? + r.seq) AND g.run_id = r.run_id
            ORDER BY r.time
            """,
            (run_id, run_id, magic_base, EA_COUNTER_INIT),
        ).fetchall()

        for r in signals:
            cat, score = category_score_for_signal(r, r["direction"])
            conv = conviction(score)
            pnl = r["group_pnl"]
            deals = r["deal_count"]
            has_fill = deals > 0
            bucket_pnl[conv].append((pnl, has_fill))
            cat_bucket_pnl[cat][conv].append((pnl, has_fill))
            score_to_pnl.append((score, pnl, has_fill, cat))
            sim = datetime.datetime.fromtimestamp(r["time"]).strftime("%m-%d %H:%M")
            detail_rows.append(
                (run_id, sim, r["setup_type"], r["direction"], cat, score, conv,
                 deals, pnl, has_fill))

    if not detail_rows:
        print("No TAKEN signals found in scope.", file=sys.stderr)
        return 1

    print(f"## TAKEN signals analyzed: {len(detail_rows)}")
    print()

    # ─── Per-signal detail ──────────────────────────────────────────
    print("### Per-signal detail")
    print()
    print("| run | sim | setup | dir | best cat | score | conv | deals | pnl |")
    print("|---:|---|---|---|---|---:|:---:|---:|---:|")
    for run_id, sim, setup, dir_, cat, score, conv, deals, pnl, has_fill in detail_rows:
        pnl_disp = f"{pnl:+.2f}" if has_fill else "no fill"
        print(f"| {run_id} | {sim} | {setup} | {dir_} | {cat} | {score} | "
              f"**{conv}** | {deals} | {pnl_disp} |")

    # ─── Bucket histogram ──────────────────────────────────────────
    print()
    print("### Bucket histogram (conviction = max score across MSS_CONT / OTE_RETR / LIQ_SWEEP)")
    print()
    print("| Bucket | Count | With Fill | Wins | Losses | Win Rate | Mean P&L | Total P&L |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for bucket in ["H", "M", "L", "?"]:
        rows = bucket_pnl.get(bucket, [])
        count = len(rows)
        filled = [pnl for pnl, has in rows if has]
        wins = sum(1 for p in filled if p > 0)
        losses = sum(1 for p in filled if p < 0)
        wr = (wins / len(filled) * 100) if filled else 0.0
        mean = (sum(filled) / len(filled)) if filled else 0.0
        total = sum(filled)
        wr_disp = f"{wr:.1f}%" if filled else "—"
        mean_disp = f"{mean:+.2f}" if filled else "—"
        total_disp = f"{total:+.2f}" if filled else "—"
        print(f"| {bucket} | {count} | {len(filled)} | {wins} | {losses} | "
              f"{wr_disp} | {mean_disp} | {total_disp} |")

    # ─── Per-category × bucket detail ──────────────────────────────
    print()
    print("### Per-category × bucket detail")
    print()
    print("| Category | Bucket | Count | With Fill | Wins | Losses | Win Rate | Mean P&L |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    for cat in ["MSS_CONT", "OTE_RETR", "LIQ_SWEEP"]:
        for bucket in ["H", "M", "L", "?"]:
            rows = cat_bucket_pnl[cat].get(bucket, [])
            if not rows:
                continue
            filled = [p for p, has in rows if has]
            wins = sum(1 for p in filled if p > 0)
            losses = sum(1 for p in filled if p < 0)
            wr = (wins / len(filled) * 100) if filled else 0.0
            mean = (sum(filled) / len(filled)) if filled else 0.0
            wr_disp = f"{wr:.1f}%" if filled else "—"
            mean_disp = f"{mean:+.2f}" if filled else "—"
            print(f"| {cat} | {bucket} | {len(rows)} | {len(filled)} | {wins} | "
                  f"{losses} | {wr_disp} | {mean_disp} |")

    # ─── Threshold analysis ────────────────────────────────────────
    print()
    print("### Mode B threshold analysis — cumulative win-rate by score floor")
    print()
    print("| Score ≥ | Trades | With Fill | Wins | Losses | Win Rate | Mean P&L | Total P&L |")
    print("|---:|---:|---:|---:|---:|---:|---:|---:|")
    all_with_score = [(s, p, has) for s, p, has, c in score_to_pnl]
    for threshold in range(0, 11):
        in_scope = [(p, has) for s, p, has in all_with_score if s >= threshold]
        if not in_scope:
            continue
        filled = [p for p, has in in_scope if has]
        wins = sum(1 for p in filled if p > 0)
        losses = sum(1 for p in filled if p < 0)
        wr = (wins / len(filled) * 100) if filled else 0.0
        mean = (sum(filled) / len(filled)) if filled else 0.0
        total = sum(filled)
        wr_disp = f"{wr:.1f}%" if filled else "—"
        mean_disp = f"{mean:+.2f}" if filled else "—"
        total_disp = f"{total:+.2f}" if filled else "—"
        print(f"| {threshold} | {len(in_scope)} | {len(filled)} | {wins} | "
              f"{losses} | {wr_disp} | {mean_disp} | {total_disp} |")

    print()
    print("### Notes")
    print()
    print("- Mode B activates when score < N triggers warning de-rate (lot factor × 0.5 typically).")
    print("- Pick the threshold where the **win rate jumps meaningfully** vs the unfiltered set, AND")
    print("  filtering OUT a meaningful FRACTION of trades (not just 1-2 outliers).")
    print("- Per-category × bucket counts highlight whether the score is selective WITHIN a category")
    print("  (the 'right' question) vs just rejecting whole categories (which symmetric Mode B should not do).")
    print("- Current dataset size makes statistical confidence LOW until longer F-β.1 tester")
    print("  runs accumulate. Re-run this script after each multi-day tester pass.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
