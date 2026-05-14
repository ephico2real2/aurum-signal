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

## §6 Backtest validation plan

After v2.7.110 ships and accumulates ≥ 100 TAKEN entries with `ces_score > 0`, run:

```sql
-- Win rate by CES score bucket
SELECT s.ces_score,
       COUNT(*)                                        AS taken,
       SUM(CASE WHEN t.profit > 0 THEN 1 ELSE 0 END)   AS wins,
       ROUND(SUM(t.profit), 2)                         AS net_pnl,
       ROUND(AVG(t.profit), 2)                         AS avg_pnl
FROM SIGNALS s
JOIN TRADES t ON t.magic = s.magic AND t.run_id = s.run_id
WHERE s.outcome='TAKEN' AND s.ces_score > 0
GROUP BY s.ces_score
ORDER BY s.ces_score;
```

**Decision matrix**:

| Pattern in results | Decision |
|---|---|
| Net P&L positive ABOVE some `N` AND negative BELOW `N`, monotone | Ship Option A with `ces_min_threshold = N` |
| Monotone P&L curve but no clear bucket inflection | Re-weight atoms (operator-tunable knobs) before deciding |
| Flat P&L across all buckets | CES atoms are uncorrelated with outcome — re-design atoms (rare given each was hand-picked) |
| Winners cluster at LOW score | Atom signs are flipped — inspect each component column in losing rows |

**Component-level diagnostic** (which atom is doing the work?):

```sql
SELECT
  AVG(CASE WHEN profit > 0 THEN ces_dtc      END) AS dtc_w_avg,
  AVG(CASE WHEN profit < 0 THEN ces_dtc      END) AS dtc_l_avg,
  AVG(CASE WHEN profit > 0 THEN ces_pemcg    END) AS pemcg_w_avg,
  AVG(CASE WHEN profit < 0 THEN ces_pemcg    END) AS pemcg_l_avg,
  -- ... mirror for momentum/rsi/vwap/di
FROM SIGNALS s JOIN TRADES t ON t.magic=s.magic AND t.run_id=s.run_id
WHERE s.outcome='TAKEN' AND s.ces_score > 0;
```

Atoms where `winner avg` ≫ `loser avg` are predictive; atoms where they're equal are noise and can be removed in a future version.

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

---

## §8 Changelog

- 2026-05-14 — **doc created** + v2.7.110 Option C shipped (instrumentation-only). Operator decision: ship Option C first; flip Option A after backtest correlation analysis.
