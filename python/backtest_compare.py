"""
backtest_compare.py — Compare two FORGE tester runs by their aurum_run_ids.

Reads directly from aurum_tester.db (forge_signals, forge_journal_trades,
aurum_tester_runs). Returns only numbers derived from real DB rows — no
synthetic or estimated values.

Scoring (0–100):
  40%  Win rate
  30%  P&L return % vs opening balance (total_pnl / balance * 100, capped at 5% = full)
  15%  Loss avoidance (0 losses = full 15; each loss costs proportionally)
  15%  Take rate (quality entries / total signals, full at ≥ 0.05%)

When avg_win and avg_loss are both available, a ±5pt R/R bonus is added
(capped so total never exceeds 100).
"""
from __future__ import annotations

from typing import Any


# ── helpers ──────────────────────────────────────────────────────────

def _pct(num: float, den: float) -> float | None:
    return round(num / den * 100, 1) if den > 0 else None


def _delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, 4)


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
    balance = float(run.get("balance") or 10_000)

    sig_rows = ts.query(
        """SELECT outcome, gate_reason, COUNT(*) as cnt
           FROM forge_signals WHERE aurum_run_id=?
           GROUP BY outcome, gate_reason""",
        (aurum_run_id,),
    )
    taken   = sum(r["cnt"] for r in sig_rows if r["outcome"] == "TAKEN")
    skipped = sum(r["cnt"] for r in sig_rows if r["outcome"] == "SKIP")
    total_signals = taken + skipped

    gate_breakdown: dict[str, int] = {}
    for r in sig_rows:
        if r["outcome"] == "SKIP" and r["gate_reason"]:
            gate_breakdown[r["gate_reason"]] = gate_breakdown.get(r["gate_reason"], 0) + r["cnt"]

    # v2.7.48 — killzone + RegimeState breakdowns (FORGE_REGIME_TAXONOMY.md §3 + §11.3 + §11.6).
    # Surfaces the columns that v2.7.36/.45/.47 added to forge_signals so run-vs-run can answer
    # "did Run A enter more in the prime window than Run B?" and "did intraday_counter_htf
    # entries underperform?" — the whole reason those columns exist.
    # All wrapped in try/except: pre-v2.7.36 aurum_tester.db files won't have the columns and
    # should soft-degrade (no enrichment) rather than crash the comparator.
    taken_by_killzone: dict[str, int] = {}
    htf_h1_strong_rate_pct: float | None = None
    intraday_counter_htf_rate_pct: float | None = None
    judas_window_taken: int = 0
    try:
        kz_rows = ts.query(
            """SELECT COALESCE(NULLIF(killzone,''),'(none)') AS kz, COUNT(*) AS cnt
               FROM forge_signals
               WHERE aurum_run_id=? AND outcome='TAKEN'
               GROUP BY 1
               ORDER BY cnt DESC""",
            (aurum_run_id,),
        )
        taken_by_killzone = {r["kz"]: r["cnt"] for r in kz_rows}
    except Exception:
        # Column doesn't exist on old aurum_tester.db — leave empty.
        pass

    try:
        regime_rows = ts.query(
            """SELECT
                 SUM(CASE WHEN htf_h1_strong=1        THEN 1 ELSE 0 END) AS htf_strong_cnt,
                 SUM(CASE WHEN intraday_counter_htf=1 THEN 1 ELSE 0 END) AS counter_htf_cnt,
                 SUM(CASE WHEN killzone='LONDON_OPEN_KZ' AND minutes_into_kz < 60 THEN 1 ELSE 0 END) AS judas_cnt
               FROM forge_signals
               WHERE aurum_run_id=? AND outcome='TAKEN'""",
            (aurum_run_id,),
        )
        if regime_rows and taken > 0:
            r0 = regime_rows[0]
            htf_strong_cnt  = int(r0.get("htf_strong_cnt")  or 0)
            counter_htf_cnt = int(r0.get("counter_htf_cnt") or 0)
            judas_window_taken = int(r0.get("judas_cnt") or 0)
            htf_h1_strong_rate_pct        = _pct(htf_strong_cnt,  taken)
            intraday_counter_htf_rate_pct = _pct(counter_htf_cnt, taken)
    except Exception:
        # Columns from v2.7.47 (htf_h1_strong, intraday_counter_htf) or v2.7.45 (minutes_into_kz)
        # don't exist on older DB — leave the rate fields as None.
        pass

    trade_rows = ts.query(
        """SELECT profit FROM forge_journal_trades
           WHERE aurum_run_id=? AND profit IS NOT NULL AND profit != 0""",
        (aurum_run_id,),
    )
    profits   = [r["profit"] for r in trade_rows]
    wins      = sum(1 for p in profits if p > 0)
    losses    = sum(1 for p in profits if p < 0)
    total_pnl = round(sum(profits), 2)
    max_win   = round(max(profits), 2) if profits else None
    max_loss  = round(min(profits), 2) if profits else None
    avg_win   = round(sum(p for p in profits if p > 0) / wins, 2)   if wins   else None
    avg_loss  = round(sum(p for p in profits if p < 0) / losses, 2) if losses else None
    win_rate  = _pct(wins, wins + losses)
    take_rate = _pct(taken, total_signals)
    pnl_return_pct = round(total_pnl / balance * 100, 3) if balance else None

    return {
        "aurum_run_id":    aurum_run_id,
        "forge_version":   run.get("forge_version"),
        "scalper_mode":    run.get("scalper_mode"),
        "sim_start":       run.get("sim_start_time"),
        "first_seen":      run.get("first_seen_utc"),
        "balance":         balance,
        "total_signals":   total_signals,
        "taken":           taken,
        "skipped":         skipped,
        "take_rate_pct":   take_rate,
        "wins":            wins,
        "losses":          losses,
        "win_rate_pct":    win_rate,
        "total_pnl":       total_pnl,
        "pnl_return_pct":  pnl_return_pct,
        "max_win":         max_win,
        "max_loss":        max_loss,
        "avg_win":         avg_win,
        "avg_loss":        avg_loss,
        "gate_breakdown":  dict(sorted(gate_breakdown.items(), key=lambda x: -x[1])),
        # v2.7.48 — killzone + RegimeState breakdowns (sorted desc by cnt already)
        "taken_by_killzone":             taken_by_killzone,
        "htf_h1_strong_rate_pct":        htf_h1_strong_rate_pct,
        "intraday_counter_htf_rate_pct": intraday_counter_htf_rate_pct,
        "judas_window_taken":            judas_window_taken,
    }


# ── scoring ───────────────────────────────────────────────────────────

def _score(stats: dict) -> float | None:
    """
    Composite score 0–100 derived from real DB metrics only.

    40%  Win rate          — (win_rate / 100) * 40
    30%  P&L return        — (pnl_return_pct / 5.0, capped at 1.0) * 30
                             Full marks = 5% return on opening balance.
                             e.g. $500 on $10 000 = full 30 pts.
    15%  Loss avoidance    — (1 - loss_ratio) * 15
    15%  Take rate         — (take_rate / 0.05, capped at 1.0) * 15
                             Full marks = ≥ 0.05% of signals taken.
    Bonus ±5  R/R ratio    — when avg_win and avg_loss both exist:
                             min(rr / 3.0, 1.0) * 5  (capped so total ≤ 100)

    Returns None when fewer than 2 closed trades exist.
    """
    win_rate       = stats.get("win_rate_pct")
    pnl_return_pct = stats.get("pnl_return_pct")
    take_rate      = stats.get("take_rate_pct")
    wins           = stats.get("wins") or 0
    losses         = stats.get("losses") or 0

    if win_rate is None or (wins + losses) < 2:
        return None

    total_trades = wins + losses

    # 40% win rate
    wr_score = (win_rate / 100.0) * 40.0

    # 30% P&L return vs balance (5% return on balance = full marks)
    pnl_score = 0.0
    if pnl_return_pct is not None:
        pnl_score = min(pnl_return_pct / 5.0, 1.0) * 30.0

    # 15% loss avoidance
    loss_ratio  = losses / total_trades if total_trades > 0 else 0.0
    loss_score  = (1.0 - loss_ratio) * 15.0

    # 15% take rate (full at ≥ 0.05%)
    tr_score = 0.0
    if take_rate is not None:
        tr_score = min(take_rate / 0.05, 1.0) * 15.0

    # R/R bonus (±5 pts) — only when we have both avg_win and avg_loss
    rr_bonus = 0.0
    avg_win  = stats.get("avg_win")
    avg_loss = stats.get("avg_loss")
    if avg_win and avg_loss and avg_loss < 0:
        rr = abs(avg_win / avg_loss)
        rr_bonus = min(rr / 3.0, 1.0) * 5.0

    total = wr_score + pnl_score + loss_score + tr_score + rr_bonus
    return round(min(total, 100.0), 1)


# ── main compare function ─────────────────────────────────────────────

def compare_runs(ts, run_a_id: int, run_b_id: int) -> dict[str, Any]:
    """
    Compare two backtest runs. run_a is "newer/selected", run_b is "baseline/pinned".
    All values derived from real DB rows only.
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

    # Gate diff — sorted by abs(delta)
    gates_a = a.get("gate_breakdown", {})
    gates_b = b.get("gate_breakdown", {})
    all_gates = set(gates_a) | set(gates_b)
    gate_diff = {
        g: {
            "a":     gates_a.get(g, 0),
            "b":     gates_b.get(g, 0),
            "delta": gates_a.get(g, 0) - gates_b.get(g, 0),
        }
        for g in all_gates
    }
    gate_diff = dict(sorted(gate_diff.items(), key=lambda x: -abs(x[1]["delta"])))

    # v2.7.48 — Killzone diff: same shape as gate_diff. Reveals e.g. "Run A took 12 more entries
    # in NY_OPEN_KZ but 4 fewer in LONDON_OPEN_KZ" — directly speaks to §11.4 composite refinements.
    kz_a = a.get("taken_by_killzone", {})
    kz_b = b.get("taken_by_killzone", {})
    all_kz = set(kz_a) | set(kz_b)
    killzone_diff = {
        k: {
            "a":     kz_a.get(k, 0),
            "b":     kz_b.get(k, 0),
            "delta": kz_a.get(k, 0) - kz_b.get(k, 0),
        }
        for k in all_kz
    }
    killzone_diff = dict(sorted(killzone_diff.items(), key=lambda x: -abs(x[1]["delta"])))

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
            "total_pnl":      _delta(a.get("total_pnl"),      b.get("total_pnl")),
            "pnl_return_pct": _delta(a.get("pnl_return_pct"), b.get("pnl_return_pct")),
            "win_rate_pct":   _delta(a.get("win_rate_pct"),   b.get("win_rate_pct")),
            "take_rate_pct":  _delta(a.get("take_rate_pct"),  b.get("take_rate_pct")),
            "taken":          _delta(a.get("taken"),          b.get("taken")),
            "total_signals":  _delta(a.get("total_signals"),  b.get("total_signals")),
            "wins":           _delta(a.get("wins"),           b.get("wins")),
            "losses":         _delta(a.get("losses"),         b.get("losses")),
            "score":          _delta(score_a,                 score_b),
            # v2.7.48 — regime/killzone deltas (FORGE_REGIME_TAXONOMY.md §3 + §11.6)
            "htf_h1_strong_rate_pct":        _delta(a.get("htf_h1_strong_rate_pct"),
                                                    b.get("htf_h1_strong_rate_pct")),
            "intraday_counter_htf_rate_pct": _delta(a.get("intraday_counter_htf_rate_pct"),
                                                    b.get("intraday_counter_htf_rate_pct")),
            "judas_window_taken":            _delta(a.get("judas_window_taken"),
                                                    b.get("judas_window_taken")),
        },
        "gate_diff":    gate_diff,
        "killzone_diff": killzone_diff,
        "winner":       winner,
        "note": (
            "Score 0-100: 40% win rate + 30% P&L return (vs balance, 5%=full) + "
            "15% loss avoidance + 15% take rate (0.05%=full) + up to 5pt R/R bonus. "
            "None = fewer than 2 closed trades."
        ),
    }
