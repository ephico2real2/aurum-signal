# FORGE CES (Confluence Entry Score) — Design Reference

**Status**: Living document. Updated whenever atom weights, threshold, or composition change.
**Version added**: 2.7.110 (Option C — instrumentation-only ship 2026-05-14).
**Cross-references**: `docs/FORGE_PEMCG_ARCHITECTURE.md` (§3.4/§3.5 DTC consumed by atom 1), `docs/FORGE_DECISION_STACK.md`, `.claude/skills/forge-monitor/SKILL.md` (CES audit section).

---

## §1 Origin — the operator question that motivated CES

> **Operator** (2026-05-14): "internal logic to calculate win or loss before entry — can we score how confluent the setup actually is before we commit?"

PEMCG/UMCG/CVCSM/DLV/DTC already gate setups, but each layer answers a binary "block this fire?" question. The operator wanted a **composite confidence score** that aggregates the same atoms across layers into a 0-10 integer per setup-trigger, so analysis can answer:

- Do high-CES trades correlate with wins?
- Do low-CES trades correlate with losses?
- Is the threshold at which "block below" delivers net positive EV measurable from the existing journal?

The answer to those questions decides whether **Option A (gate-mode)** is worth shipping. v2.7.110 ships **Option C (logging-only)** so the next backtest run accumulates the data to make that decision.

---

## §2 The 7 atoms

CES sums 6 atoms (one is intentionally absorbed into atom #1's DTC-alignment check, see Implementation note). Max score = 10. Each atom is a deterministic boolean produced by an existing FORGE atom + threshold; the atom's *weight* is the integer added to `g_ces_score` when its boolean fires.

| # | Atom | Condition (BUY / SELL) | Weight | Industry citation |
|---|---|---|---:|---|
| 1 | **DTC trend-aligned** | `g_dtc_state == BULL_TREND_ALIGNED && BUY` / `BEAR_TREND_ALIGNED && SELL` (falls back to `g_dtc_bull_day_intraday`/`g_dtc_bear_day_intraday` when 5-state OFF) | **+3** | ICT framework + tradeciety multi-TF: "trade only in direction of H4 bias" — see `docs/FORGE_PEMCG_ARCHITECTURE.md §3.5` |
| 2 | **PEMCG clean** | `g_pemcg_<dir>_warning_count ≤ 2` (clean reversal-trap reading) | **+2** | v2.7.84 PEMCG composite — same threshold the CVCSM uses to release direction from cooldown (`cvcsm_release_threshold=2`). |
| 3 | **M5 momentum candle** | `g_eval_m5_strong_bar == 1 && g_eval_m5_body_pct ≥ 0.5` | **+2** | Nison candlestick + ICT displacement bar: strong body in trend direction = institutional commitment, not retest noise. |
| 4 | **RSI in trend zone** | BUY: `m5_rsi ∈ [40, 65]`; SELL: `m5_rsi ∈ [35, 60]` (not extreme, not divergence territory) | **+1** | volity.io RSI guide: "In strong trend, RSI stays in trend-zone band; extremes flip from reversal-signal to continuation-signal." We want trades inside the band, away from both extremes. |
| 5 | **VWAP-distance confirms** | BUY: `g_eval_vwap_dist_atr ≥ -0.5`; SELL: `g_eval_vwap_dist_atr ≤ +0.5` | **+1** | mql5.com/blogs/767595 — VWAP as intraday sentiment line: buying not deeply below VWAP / selling not deeply above. |
| 6 | **H1 DI dominance** | BUY: `DI+ > DI- + 5`; SELL: `DI- > DI+ + 5` | **+1** | Wilder DMI canon: \|DI+ − DI−\| ≥ 5 = clear directional bias on H1. Same threshold DTC uses (`dtc_h1_di_dominance_min`). |

**Why these atoms?** They span the three independent axes of "should this trade work":
- **Macro direction** (atom 1 — DTC = intraday + H4 confluence)
- **Setup-quality / no-trap** (atoms 2 + 3 — PEMCG clean + strong candle)
- **Indicator alignment** (atoms 4 + 5 + 6 — RSI / VWAP / H1 DI all confirm)

No atom is a slope-of-slope or higher-order derivative; every atom is a value FORGE already computes per tick. Compute cost ~0.5 µs per setup-trigger (6 comparisons + 1 sum).

**Implementation note** — the prompt enumerated 7 atoms but combines "DTC matches direction" (atom 1, weight 3) as the dominant signal; the H1 DI atom (weight 1) keeps an independent axis check. In code this lands as 6 component globals — see `ea/FORGE.mq5` around the v2.7.110 CES compute block.

---

## §3 Three options considered

### Option A — Gate (block below threshold)
At every setup-trigger, after UMCG/CVCSM/DLV/DTC pass, compute CES. If `g_ces_score < ces_min_threshold` (default 6) → SKIP with `gate_reason="ces_below_threshold"`. **Pros**: directly filters low-confluence entries. **Cons**: requires empirical threshold calibration before shipping — wrong threshold blocks winners or lets losers through. Operator decided against shipping this *first* until backtest data validates the cutoff.

### Option B — Replacement (replace existing gates)
CES becomes the single decision layer; UMCG/CVCSM/DTC are demoted to atom inputs. **Pros**: cleaner architecture. **Cons**: huge regression surface, destroys the layered post-mortem story ("which gate blocked this trade?"). Rejected.

### Option C — Logging-only (instrumentation) ← **operator chose this 2026-05-14**
CES is computed at every setup-trigger that survives UMCG/CVCSM/DLV/DTC and is logged to SIGNALS via 7 new columns (`ces_score`, `ces_dtc`, `ces_pemcg`, `ces_momentum`, `ces_rsi`, `ces_vwap`, `ces_di`). **No blocking.** Backtest analysis joins `SIGNALS.ces_score` with `TRADES.profit` (via magic) to see if score correlates with outcome. If yes → flip Option A on.

---

## §4 Option C — what this version (v2.7.110) does

1. **Compute** `g_ces_score` (int 0-10) at every setup-trigger fire when `ces_enabled=1`.
2. **Compute** 6 component globals (`g_ces_component_dtc/pemcg/momentum/rsi/vwap/di`) so each atom's contribution is visible per row.
3. **Log** all 7 to SIGNALS via new columns; available to both TAKEN and SKIP rows (when SKIP is fired by another layer, CES values reflect what the score would have been).
4. **Index** `idx_sig_ces_score ON SIGNALS(ces_score)` for fast analysis queries.
5. **Mirror** the columns into `forge_signals` (AURUM-side) via additive ALTERs in scribe.py.
6. **Default-OFF**: when `ces_enabled=0`, components stay at 0 (no compute cost, byte-identical to v2.7.109 logging).
7. **No blocking** — `ces_block_below_threshold=0` is the default-off ship config.

---

## §5 Option A — single-flag activation sequence (future)

When backtest validates the threshold:

```bash
# .env
FORGE_COMPOSITE_CES_ENABLED=1                      # already on after v2.7.110 ship
FORGE_GATE_CES_BLOCK_BELOW_THRESHOLD=1             # flip ONE flag to engage Option A
FORGE_GATE_CES_MIN_THRESHOLD=6                     # tune based on §6 analysis
```

Then `make scalper-env-sync && make forge-compile && make forge-reload`. Gate logs as `gate_reason="ces_below_threshold"`.

No code changes required — Option A is fully scaffolded in v2.7.110.

---

## §6 Backtest validation plan — full statistical pipeline

The bucket query below is a useful starting point, but it's too crude as the sole decision rule. This section lays out the rigorous statistical stack — what's sound, what the simple bucket misses, and the decision matrix for activating Option A.

### §6.1 The starter query (calibration sanity check)

After v2.7.110 ships and accumulates ≥ 100 TAKEN entries with `ces_score > 0`:

```sql
-- Win rate by CES score bucket
SELECT
  CASE
    WHEN s.ces_score < 4 THEN 'low_confidence'
    WHEN s.ces_score < 6 THEN 'mid_confidence'
    WHEN s.ces_score < 8 THEN 'high_confidence'
    ELSE 'extreme_confidence'
  END AS ces_bucket,
  COUNT(*) AS n,
  ROUND(AVG(t.profit), 2) AS avg_pnl,
  SUM(CASE WHEN t.profit > 0 THEN 1 ELSE 0 END) AS wins,
  SUM(CASE WHEN t.profit < 0 THEN 1 ELSE 0 END) AS losses
FROM SIGNALS s
JOIN TRADES t ON t.magic = s.magic AND t.run_id = s.run_id
WHERE s.outcome='TAKEN' AND s.ces_score > 0
GROUP BY ces_bucket
ORDER BY 1;
```

**What the bucket query gets RIGHT**: it's a **non-parametric calibration check**. Categorizing by score and computing win rate per bucket tests whether CES is monotonic with expected profit without assuming any functional form. If win rate rises monotonically with score, CES has signal. If it's flat or non-monotonic, the score is noise.

### §6.2 What the bucket query gets WRONG (5 statistical gaps)

**Gap 1 — No sample-size threshold → bucket totals can lie.** A bucket with 5 trades at 80% win rate looks identical to one with 500 trades at 80% — but the first has a 95% confidence interval of (28%, 99%) while the second has (76%, 84%). The "win rate" is dramatically less informative for small N.

Fix: add Wilson score confidence interval to every bucket. Only treat the bucket as informative if `ci_high - ci_low < 0.20` (CI tighter than 20pp).

```python
import statsmodels.stats.proportion as smp
ci_low, ci_high = smp.proportion_confint(wins, n, alpha=0.05, method='wilson')
```

**Gap 2 — Win rate ignores expectancy.** A bucket with 80% win rate but tiny wins and huge losses is unprofitable. The right metric is **expectancy per signal**:
```
expectancy = (win_rate × avg_win) + ((1 − win_rate) × avg_loss)
```
Or even better, **profit factor** = `sum(wins) / |sum(losses)|`. PF > 1.5 = robust edge.

**Gap 3 — Bucket boundaries are arbitrary (4/6/8) → overfitting risk.** Hand-picking thresholds tunes them to the historical data. Better: report **per-score-level statistics** (0, 1, 2, ..., 10) and let the data show natural break points, OR use a **single continuous AUC metric** rather than bucketing.

**Gap 4 — Independence assumption violated.** Cascade legs of the same group share fate — the 5 G5024 legs all SL'd together = 5 "independent" losses that are actually 1 correlated event. The query counts them as 5 separate observations, inflating apparent sample size.

Fix: aggregate to **group-level outcome** before any statistical test:
```sql
WITH group_outcomes AS (
  SELECT s.magic,
         MAX(s.ces_score) AS ces_score,
         SUM(t.profit)    AS group_pnl
  FROM SIGNALS s
  JOIN TRADES t ON t.magic = s.magic
  WHERE s.outcome='TAKEN'
  GROUP BY s.magic
)
SELECT * FROM group_outcomes;
```

**Gap 5 — No ROC/AUC analysis.** CES is implicitly a **binary classifier** — "high score → trade, low score → skip". The standard evaluation is ROC curve sweeping thresholds with **AUC ≥ 0.65 = useful, ≥ 0.75 = strong, < 0.55 = noise**. The bucket query doesn't reveal this.

### §6.3 The full analysis pipeline (6 steps)

```python
import pandas as pd, numpy as np
from statsmodels.stats.proportion import proportion_confint
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score, roc_curve
import statsmodels.api as sm
import sqlite3

# Step 1: Pull group-aggregated data (Gap 4 fix)
conn = sqlite3.connect('file:<active source DB>?mode=ro', uri=True)
query = """
  SELECT s.magic,
         MAX(s.ces_score)     AS ces_score,
         MAX(s.ces_dtc)       AS ces_dtc,
         MAX(s.ces_pemcg)     AS ces_pemcg,
         MAX(s.ces_momentum)  AS ces_momentum,
         MAX(s.ces_rsi)       AS ces_rsi,
         MAX(s.ces_vwap)      AS ces_vwap,
         MAX(s.ces_di)        AS ces_di,
         SUM(t.profit)        AS group_pnl,
         CASE WHEN SUM(t.profit) > 0 THEN 1 ELSE 0 END AS won
  FROM SIGNALS s
  JOIN TRADES t ON t.magic = s.magic
  WHERE s.outcome='TAKEN' AND s.ces_score > 0
  GROUP BY s.magic
"""
df = pd.read_sql(query, conn)

# Step 2: Calibration plot — per-score win rate + Wilson CI + expectancy
calib = df.groupby('ces_score').agg(
    n=('won', 'count'),
    wins=('won', 'sum'),
    avg_pnl=('group_pnl', 'mean'),
    total_pnl=('group_pnl', 'sum')
)
calib['win_rate'] = calib['wins'] / calib['n']
calib['ci_low'], calib['ci_high'] = zip(*[
    proportion_confint(w, n, alpha=0.05, method='wilson')
    for w, n in zip(calib['wins'], calib['n'])
])
# Profit factor per bucket
df['win_pnl']  = df.apply(lambda r: r['group_pnl'] if r['won'] else 0, axis=1)
df['loss_pnl'] = df.apply(lambda r: abs(r['group_pnl']) if not r['won'] else 0, axis=1)
pf = df.groupby('ces_score').apply(
    lambda g: g['win_pnl'].sum() / max(g['loss_pnl'].sum(), 1e-9)
)

# Step 3: Monotonicity test (Spearman rank correlation)
rho, pval = spearmanr(df['ces_score'], df['won'])
# rho > 0.3 AND p < 0.05 → CES is monotonically related to outcome

# Step 4: ROC / AUC — treat CES as binary classifier
auc = roc_auc_score(df['won'], df['ces_score'])
# auc ≥ 0.65 useful ; ≥ 0.75 strong ; < 0.55 noise

# Step 5: Optimal threshold via F1 (balanced precision/recall)
fpr, tpr, thresholds = roc_curve(df['won'], df['ces_score'])
# F1 from FPR+TPR (handles divide-by-zero in tpr=0 regions)
denom = (1 + fpr + tpr - fpr)
f1 = np.divide(2 * tpr, denom, out=np.zeros_like(tpr), where=denom>0)
optimal_threshold = thresholds[np.argmax(f1)]

# Step 6: Logistic regression — fit per-atom weights from data
X = df[['ces_dtc', 'ces_pemcg', 'ces_momentum', 'ces_rsi', 'ces_vwap', 'ces_di']]
y = df['won']
model = sm.Logit(y, sm.add_constant(X)).fit(disp=0)
# Coefficients with p < 0.05 AND positive sign → keep weight or boost
# Non-significant or wrong-sign coefficients → reduce weight to 0 in next version
print(model.summary())
```

### §6.4 Decision matrix

| Statistical signal | Interpretation | Action |
|---|---|---|
| AUC < 0.55 | CES is noise | Re-tune atoms — current formulation doesn't separate winners from losers |
| AUC 0.55–0.65 | Weak signal | Keep instrumentation; do NOT activate Option A gate yet |
| **AUC ≥ 0.65 + monotonic calibration (Spearman ρ > 0.3, p < 0.05)** | **Useful classifier** | **Activate Option A** with `ces_min_threshold = optimal_threshold` from F1 |
| AUC ≥ 0.75 | Strong classifier | Activate Option A + consider higher threshold to capture only premium signals |
| Monotonic but CI overlap is wide | Insufficient data | Wait for more signals (N ≥ 500 for stable stats) |
| Logistic regression shows some atoms non-significant | Some atoms are noise | Drop their weight to 0 in a follow-up version; re-fit; re-test |
| Logistic regression shows wrong-sign coefficient | Atom is anti-predictive | INVERT the atom polarity OR drop it |
| Winners cluster at LOW score | Atom signs are flipped | Inspect per-component columns in losing rows; fix polarity globally |

### §6.5 Sample-size requirements (statistical power)

For a base 50% win rate, detecting whether CES moves it to 60% with 80% power and α=0.05 requires:

| Population | What it unlocks |
|---|---|
| **N ≈ 100** signals per atom | Logistic regression coefficients become meaningful |
| **N ≈ 200** signals total | ROC/AUC stabilizes (curve flattens above 200 in most empirical work) |
| **N ≈ 500** signals total | Bucket query and per-score breakdowns reach narrow CIs |

Current FORGE pace ≈ **45 TAKEN signals per 10 sim-days** (Run 36 benchmark):

| Sim window | Approx signal population | Analysis confidence |
|---|---|---|
| 2 weeks (~63 signals) | Too small — Spearman only | Calibration sanity check only; no AUC decision |
| **6 weeks (~200 signals)** | **ROC/AUC reliable** | Provisional Option A activation decision |
| 12 weeks (~500 signals) | Full statistical confidence | Production Option A activation |

### §6.6 Component-level diagnostic (which atom is doing the work?)

The Step 6 logistic-regression output already answers this rigorously, but a quick SQL look at component means by outcome gives an at-a-glance view:

```sql
SELECT
  AVG(CASE WHEN profit > 0 THEN ces_dtc      END) AS dtc_w_avg,
  AVG(CASE WHEN profit < 0 THEN ces_dtc      END) AS dtc_l_avg,
  AVG(CASE WHEN profit > 0 THEN ces_pemcg    END) AS pemcg_w_avg,
  AVG(CASE WHEN profit < 0 THEN ces_pemcg    END) AS pemcg_l_avg,
  AVG(CASE WHEN profit > 0 THEN ces_momentum END) AS momentum_w_avg,
  AVG(CASE WHEN profit < 0 THEN ces_momentum END) AS momentum_l_avg,
  AVG(CASE WHEN profit > 0 THEN ces_rsi      END) AS rsi_w_avg,
  AVG(CASE WHEN profit < 0 THEN ces_rsi      END) AS rsi_l_avg,
  AVG(CASE WHEN profit > 0 THEN ces_vwap     END) AS vwap_w_avg,
  AVG(CASE WHEN profit < 0 THEN ces_vwap     END) AS vwap_l_avg,
  AVG(CASE WHEN profit > 0 THEN ces_di       END) AS di_w_avg,
  AVG(CASE WHEN profit < 0 THEN ces_di       END) AS di_l_avg
FROM SIGNALS s JOIN TRADES t ON t.magic=s.magic AND t.run_id=s.run_id
WHERE s.outcome='TAKEN' AND s.ces_score > 0;
```

Atoms where `winner avg` ≫ `loser avg` are predictive; atoms where they're equal are noise and can be removed in a future version.

### §6.7 Operational integration — proposed `make ces-analyze`

Wire this as a Makefile target so analysis runs anywhere after a CES-instrumented backtest:

```bash
make ces-analyze    # runs scripts/analyze_ces.py against the latest run
```

Output artifacts:
- **`reports/ces_calibration.png`** — score 0-10 on X-axis, win rate + Wilson CI band on Y; expectancy line overlay
- **`reports/ces_roc.png`** — ROC curve with AUC annotated; F1-optimal threshold marked
- **`reports/ces_logit.txt`** — logistic regression summary (coefficients, p-values, confidence intervals)
- **`reports/ces_decision.md`** — verdict: which row of §6.4 decision matrix applies; recommended action

Status: **not yet wired** — pending operator decision to bundle in a follow-up commit on the v2.7.110 line.

---

## §7 References

### Internal
- `docs/FORGE_PEMCG_ARCHITECTURE.md §3.4/§3.5` — DTC 5-state classifier (atom 1's source)
- `docs/FORGE_DECISION_STACK.md` — 5-layer architecture CES sits on top of
- `docs/FORGE_CASE_STUDY_G5006_INFLECTION_POINT.md` — PEMCG origin (atom 2's source)
- `ea/FORGE.mq5` — `FORGE_VERSION = "2.7.110"`, CES compute block in the UMCG enforcement region, struct + JsonHasKey loaders
- `python/scribe.py::sync_forge_journal` — `(41 + 24 + 45 + 7)` placeholder math (Check C parity)
- `.claude/skills/forge-monitor/SKILL.md` — CES audit section + canonical join query

### Industry
- volity.io/forex/rsi-indicator/ — ADX × RSI continuation framework (atom 4)
- mql5.com/en/blogs/post/767595 — VWAP intraday sentiment (atom 5)
- tradeciety.com/multiple-time-frame-analysis/ — H4 bias mandate (atom 1)
- Wilder DMI canon — DI dominance threshold (atom 6)

### Statistical methodology
- statsmodels — Wilson Score Confidence Interval: https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.proportion_confint.html (proper CIs for proportions)
- scikit-learn — ROC / AUC: https://scikit-learn.org/stable/modules/model_evaluation.html#roc-metrics (canonical binary classifier evaluation)
- statsmodels — Logit / Logistic regression: https://www.statsmodels.org/stable/generated/statsmodels.discrete.discrete_model.Logit.html (MLE coefficient fitting with significance tests)
- scipy.stats — Spearman rank correlation: https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html (non-parametric monotonicity test)

---

## §8 Changelog

- 2026-05-14 — **doc created** + v2.7.110 Option C shipped (instrumentation-only). Operator decision: ship Option C first; flip Option A after backtest correlation analysis.
- 2026-05-14 — **§6 Backtest validation plan rewritten** with full statistical pipeline: 5 named gaps in the naive bucket query (sample size, expectancy, bucket overfitting, independence violation from cascade legs, missing ROC/AUC), 6-step rigorous analysis pipeline (group-aggregated pull → calibration with Wilson CI → Spearman monotonicity → AUC → F1-optimal threshold → logistic regression for per-atom weights), explicit decision matrix mapping statistical-signal-tier to action, sample-size power table (N≈100/200/500), and proposed `make ces-analyze` target with 4 output artifacts. Added Statistical methodology section to §7 References (statsmodels Wilson CI + Logit, scikit-learn ROC, scipy Spearman).
