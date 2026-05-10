"""
backtest_compare.py — Compare two FORGE tester runs by their aurum_run_ids.

Reads directly from aurum_tester.db (forge_signals, forge_journal_trades,
aurum_tester_runs). Returns only numbers derived from real DB rows — no
synthetic or estimated values.
"""
from __future__ import annotations

import math
from typing import Any


# ── helpers ──────────────────────────────────────────────────────────

def _pct(num: float, den: float) -> float | None:
    return round(num / den * 100, 1) if den > 0 else None


def _delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, 4)


def _fmt_delta(v: float | None, unit: str = "") -> str:
    if v is None:
        return "n/a"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}{unit}"


# ── per-run stats ─────────────────────────────────────────────────────

def _run_stats(ts, aurum_run_id: int) -> dict[str, Any]:
    """Pull all measurable stats for one run from aurum_tester.db."""
    run_rows = ts.query(
        "SELECT * FROM aurum_tester_runs WHERE aurum_run_id=? LIMIT 1",
        (aurum_run_id,),
    )
    if not run_rows:
        return {}
    run = run_rows[0]

    sig_rows = ts.query(
        """SELECT outcome, gate_reason, COUNT(*) as cnt
           FROM forge_signals WHERE aurum_run_id=?
           GROUP BY outcome, gate_reason""",
        (aurum_run_id,),
    )
    taken = sum(r["cnt"] for r in sig_rows if r["outcome"] == "TAKEN")
    skipped = sum(r["cnt"] for r in sig_rows if r["outcome"] == "SKIP")
    total_signals = taken + skipped

    gate_breakdown: dict[str, int] = {}
    for r in sig_rows:
        if r["outcome"] == "SKIP" and r["gate_reason"]:
            gate_breakdown[r["gate_reason"]] = gate_breakdown.get(r["gate_reason"], 0) + r["cnt"]

    trade_rows = ts.query(
        """SELECT profit FROM forge_journal_trades
           WHERE aurum_run_id=? AND profit IS NOT NULL AND profit != 0""",
        (aurum_run_id,),
    )
    profits = [r["profit"] for r in trade_rows]
    wins    = sum(1 for p in profits if p > 0)
    losses  = sum(1 for p in profits if p < 0)
    total_pnl = round(sum(profits), 2)
    max_win  = round(max(profits), 2) if profits else None
    max_loss = round(min(profits), 2) if profits else None
    avg_win  = round(sum(p for p in profits if p > 0) / wins, 2) if wins else None
    avg_loss = round(sum(p for p in profits if p < 0) / losses, 2) if losses else None
    win_rate = _pct(wins, wins + losses)
    take_rate = _pct(taken, total_signals)

    return {
        "aurum_run_id":  aurum_run_id,
        "forge_version": run.get("forge_version"),
        "scalper_mode":  run.get("scalper_mode"),
        "sim_start":     run.get("sim_start_time"),
        "first_seen":    run.get("first_seen_utc"),
        "total_signals": total_signals,
        "taken":         taken,
        "skipped":       skipped,
        "take_rate_pct": take_rate,
        "wins":          wins,
        "losses":        losses,
        "win_rate_pct":  win_rate,
        "total_pnl":     total_pnl,
        "max_win":       max_win,
        "max_loss":      max_loss,
        "avg_win":       avg_win,
        "avg_loss":      avg_loss,
        "gate_breakdown": dict(sorted(gate_breakdown.items(), key=lambda x: -x[1])),
    }


# ── scoring ───────────────────────────────────────────────────────────

def _score(stats: dict) -> float | None:
    """
    Composite score 0–100 from real metrics only.
    Weights:
      40% win rate (0–100%)
      30% total P&L relative to balance (0–∞, capped at 10% gain = max contribution)
      20% take rate (more entries tested = better coverage)
      10% loss avoidance (0 losses = full 10 pts; each loss costs proportionally)

    Returns None if insufficient data (< 2 closed trades).
    """
    win_rate  = stats.get("win_rate_pct")
    total_pnl = stats.get("total_pnl")
    balance   = stats.get("sim_start")  # not balance — skip relative PnL if missing
    take_rate = stats.get("take_rate_pct")
    wins      = stats.get("wins") or 0
    losses    = stats.get("losses") or 0

    if win_rate is None or (wins + losses) < 2:
        return None

    # win rate component (0–40)
    wr_score = (win_rate / 100.0) * 40.0

    # take rate component (0–20): full 20 at ≥ 0.5% take rate
    tr_score = 0.0
    if take_rate is not None:
        tr_score = min(take_rate / 0.5, 1.0) * 20.0

    # loss avoidance component (0–10)
    total_trades = wins + losses
    loss_ratio = losses / total_trades if total_trades > 0 else 0.0
    loss_score = (1.0 - loss_ratio) * 10.0

    # P&L component (0–30): requires balance — approximated from trade count as proxy
    # Use avg_win vs avg_loss ratio as a risk/reward proxy (capped at 3:1 = full 30)
    pnl_score = 0.0
    avg_win  = stats.get("avg_win")
    avg_loss = stats.get("avg_loss")
    if avg_win and avg_loss and avg_loss < 0:
        rr = abs(avg_win / avg_loss)
        pnl_score = min(rr / 3.0, 1.0) * 30.0
    elif wins > 0 and losses == 0 and total_pnl and total_pnl > 0:
        # All wins, no losses — cap at 25 (can't compute RR)
        pnl_score = 25.0

    return round(wr_score + tr_score + loss_score + pnl_score, 1)


# ── main compare function ─────────────────────────────────────────────

def compare_runs(ts, run_a_id: int, run_b_id: int) -> dict[str, Any]:
    """
    Compare two backtest runs. run_a is "newer", run_b is "baseline".
    Returns delta metrics and scores derived entirely from DB data.
    """
    a = _run_stats(ts, run_a_id)
    b = _run_stats(ts, run_b_id)

    if not a or not b:
        return {
            "error": f"Run {run_a_id if not a else run_b_id} not found in aurum_tester.db",
            "run_a_id": run_a_id,
            "run_b_id": run_b_id,
        }

    score_a = _score(a)
    score_b = _score(b)

    # gate diff: gates that appeared/disappeared or changed count significantly
    gates_a = a.get("gate_breakdown", {})
    gates_b = b.get("gate_breakdown", {})
    all_gates = set(gates_a) | set(gates_b)
    gate_diff = {
        g: {"a": gates_a.get(g, 0), "b": gates_b.get(g, 0),
            "delta": gates_a.get(g, 0) - gates_b.get(g, 0)}
        for g in all_gates
    }
    # sort by abs(delta) descending
    gate_diff = dict(sorted(gate_diff.items(), key=lambda x: -abs(x[1]["delta"])))

    winner = None
    if score_a is not None and score_b is not None:
        if score_a > score_b:
            winner = run_a_id
        elif score_b > score_a:
            winner = run_b_id
        else:
            winner = "tie"

    return {
        "run_a": {**a, "score": score_a},
        "run_b": {**b, "score": score_b},
        "deltas": {
            "total_pnl":     _delta(a.get("total_pnl"),     b.get("total_pnl")),
            "win_rate_pct":  _delta(a.get("win_rate_pct"),  b.get("win_rate_pct")),
            "take_rate_pct": _delta(a.get("take_rate_pct"), b.get("take_rate_pct")),
            "taken":         _delta(a.get("taken"),         b.get("taken")),
            "total_signals": _delta(a.get("total_signals"), b.get("total_signals")),
            "wins":          _delta(a.get("wins"),          b.get("wins")),
            "losses":        _delta(a.get("losses"),        b.get("losses")),
            "score":         _delta(score_a, score_b),
        },
        "gate_diff": gate_diff,
        "winner": winner,
        "note": (
            "Score is 0-100: 40% win rate + 30% risk/reward + 20% take rate + 10% loss avoidance. "
            "None = insufficient closed trades (<2)."
        ),
    }
