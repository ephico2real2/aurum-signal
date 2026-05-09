# FORGE News Filter Review

## 1. Summary

The native news filter implementation mostly matches the documented Gate -1 and breakout RSI-tighten flow, but it is not fully safe as a live Run 21 guard because confirmed `BB_BREAKOUT_RETEST` entries bypass the news RSI-tighten checks entirely. The hard-block path still runs through `CheckEntryQuality()`, so the highest-risk block state is covered, but tighten-state protection is incomplete for the live retest path where `breakout_use_retest` is enabled.

## 2. Spec compliance

| Req# | Requirement (short) | Status | Notes |
|---|---|---:|---|
| 1 | `g_nf_*` globals and `ScalperConfig news_filter_*` fields exist | PASS | No deviations found in `ea/FORGE.mq5` around lines 149-158 and 223-238. |
| 2 | Defaults expose all native news filter keys | PASS | No deviations found in `config/scalper_config.defaults.json` around lines 130-145. |
| 3 | `.env` sync maps all native news filter keys | PASS | No deviations found in `scripts/sync_scalper_config_from_env.py` around lines 38-54. |
| 4 | `ReadScalperConfig()` parses all `news_filter_*` keys | PARTIAL | Keys are parsed around lines 2749-2811, but range validation is weaker than the env sync and lacks cross-field validation for tighten/block ordering. |
| 5 | `ApplyNewsFilterInputOverrides()` applies EA input overrides last | PARTIAL | It only overrides `news_filter_enabled` around lines 2241-2245; no other news filter input fields exist to override. |
| 6 | Calendar refresh stores closest future/active event window | PASS | No deviations found in `ScalperNewsFilterRefresh()` around lines 4055-4181. |
| 7 | Proximity is asymmetric pre/post event | PASS | No deviations found in `ScalperNewsProximity()` around lines 4183-4203. |
| 8 | News check returns ALLOW/TIGHTEN/BLOCK and updates effective RSI thresholds | PASS | No deviations found for normal active-window paths in `ScalperNewsCheck()` around lines 4206-4234. |
| 9 | Gate -1 hard-blocks before other quality gates | PASS | No deviations found in `CheckEntryQuality()` around lines 4255-4269. |
| 10 | BUY/SELL breakout news RSI tighten is last defense before entry | FAIL | Direct `BB_BREAKOUT` entries are checked around lines 4780-4787 and 4866-4875, but confirmed `BB_BREAKOUT_RETEST` entries set `direction` before the breakout block and skip both tighten checks. |

## 3. Critical issues

1. `CheckNativeScalperSetups()` around lines 4603-4630 and 4747-4903: confirmed `BB_BREAKOUT_RETEST` entries bypass the news RSI-tighten checks. When `g_retest.active` is confirmed, the function sets `direction`, `sl`, `tp1`, `tp2`, and `setup_type = "BB_BREAKOUT_RETEST"` before the `BB_BREAKOUT` detection block. Because the breakout block is guarded by `if(direction == "" ...)`, neither the BUY tighten block around lines 4780-4787 nor the SELL tighten block around lines 4866-4875 can execute. Exact wrong behavior: during news TIGHTEN state, a retest-confirmed BUY with `m5_rsi >= g_nf_eff_rsi_buy_ceil` or SELL with `m5_rsi <= g_nf_eff_rsi_sell_min` can proceed to `CheckEntryQuality()` and entry placement instead of logging `entry_quality_news_rsi_tighten` and skipping.

## 4. Warnings

1. `ReadScalperConfig()` around lines 2789-2795 and `scripts/sync_scalper_config_from_env.py` around lines 49-50: `news_filter_tighten_pct` and `news_filter_block_pct` are validated independently as `0.0..1.0`, but there is no enforcement that `tighten_pct < block_pct`. Exact risky behavior: if config sets `block_pct <= tighten_pct`, `ScalperNewsCheck()` around lines 4220-4229 can collapse the tighten zone into an abrupt hard block or make tightening unreachable.

2. `ReadScalperConfig()` around lines 2749-2811 and `ScalperNewsUpdateEffectiveThresholds()` around lines 4243-4245: hot-reloading news filter fields does not reset `g_nf_next_refresh` or force `ScalperNewsFilterRefresh()`. Exact risky behavior: changes to currencies, event windows, special keywords, or refresh interval can leave the old cached event window active until the existing refresh deadline.

3. `ScalperNewsFilterRefresh()` around lines 4116-4120: `CalendarValueHistory()` failure is fail-open. Exact risky behavior: if the calendar query returns false for all configured currencies, the function leaves `g_nf_have_window = false`, causing `ScalperNewsProximity()` around lines 4189-4190 to return `-1.0` and `ScalperNewsCheck()` around lines 4208-4211 to allow entries.

4. `ReadScalperConfig()` around lines 2797-2803: JSON parsing accepts `news_filter_tighten_rsi_buy` and `news_filter_tighten_rsi_sell` across `0.0..100.0`, while the env sync constrains them to `50.0..70.0` and `30.0..50.0` around script lines 51-52. Exact risky behavior: hand-edited defaults/config can set nonsensical tighten RSI values that make TIGHTEN ineffective or overly aggressive.

## 5. Design observations

1. `ApplyNewsFilterInputOverrides()` around lines 2241-2245 only provides an EA-panel override for enable/disable. That matches the two declared inputs around lines 90-91, but the function name is broader than the actual override surface.

2. `CheckNativeScalperSetups()` around line 4601 calls `ScalperNewsUpdateEffectiveThresholds()` before setup selection, while `CheckEntryQuality()` around line 4258 calls it again after a direction exists. This duplicates calendar-state evaluation within one bar; it is not a correctness bug, but it makes the effective RSI thresholds depend on shared globals updated in two places.

3. `ScalperNewsCheck()` around lines 4215-4218 returns BLOCK during the post-event hard floor before the generic `block_pct` check. This means `g_nf_eff_rsi_*` remains at the defaults set by `ScalperNewsUpdateEffectiveThresholds()` around lines 4238-4239 during hard-block states. That is acceptable because Gate -1 stops entries, but BLOCK state does not preserve a tightened diagnostic threshold.

## 6. Verdict

Not safe to run live Run 21 with the news filter as the intended final guard until the retest bypass is fixed.

Priority order:

1. Add news RSI-tighten enforcement for confirmed `BB_BREAKOUT_RETEST` entries before order placement, using the same BUY/SELL conditions and `entry_quality_news_rsi_tighten` reason as direct breakout entries.
2. Add cross-field validation or normalization so `news_filter_tighten_pct < news_filter_block_pct` in both JSON parsing and env sync.
3. Reset `g_nf_next_refresh` or force `ScalperNewsFilterRefresh()` when hot-reloaded news filter fields change.

---

## 7. Expert triage & corrections

### Correction to the Codex verdict — Run 21 in Strategy Tester IS safe

The critical retest bypass (Issue 1 above) is a **live-only bug**. The retest path at lines 4794 and 4882 is guarded by `!in_tester`:

```mql5
if(g_sc.breakout_use_retest && !in_tester && !g_retest.active)
```

In Strategy Tester, `in_tester = true`, so `g_retest.active` is never set. The bypass code at lines 4604–4631 is therefore unreachable during any tester run. **Run 21 is safe to proceed.**

The bug must be fixed before deploying live. It is not a Run 21 blocker.

---

### Finding triage

| # | Finding | Verdict | Action |
|---|---------|---------|--------|
| Critical 1 | Retest bypass of news RSI tighten | Real bug — live only | Fix before live deploy |
| Warning 1 | `tighten_pct < block_pct` not cross-validated | Valid — simple guard | Fix now (1 line) |
| Warning 2 | Hot-reload doesn't reset refresh timer | Acceptable by design | No action — resetting on every config reload would spam the calendar API |
| Warning 3 | `CalendarValueHistory` fail-open | Correct design choice | No action — blocking all trades on API failure is worse |
| Warning 4 | JSON range validation wider than env sync | Minor | Add clamping in `ReadScalperConfig` to match env sync ranges |
| Obs 1 | `ApplyNewsFilterInputOverrides` name broader than surface | Cosmetic | No action |
| Obs 2 | Double call to `ScalperNewsUpdateEffectiveThresholds` | Intentional, not a bug | The pre-call at 4601 primes the BB tighten checks; Gate -1 call is the safety net. No action |
| Obs 3 | `g_nf_eff_rsi_*` not diagnostic-preserved on BLOCK | Acceptable | BLOCK kills the entry — the diagnostic threshold is moot |

---

### Fixes required before live trading (2 items)

**Fix A — Retest bypass (Critical 1)**

In the retest confirmation block (lines 4616–4622), add news tighten check before committing `direction`. The values in `g_nf_eff_rsi_*` are already set by the `ScalperNewsUpdateEffectiveThresholds()` call at line 4601, so no re-call is needed:

```mql5
if(price_retested) {
   // News RSI tighten — same guard as direct BB_BREAKOUT entries
   string rt_dir = g_retest.direction;
   bool nf_retest_ok = true;
   if(rt_dir == "BUY"
      && g_nf_eff_rsi_buy_ceil < g_sc.breakout_rsi_buy_ceil
      && SymbolInfoDouble(_Symbol, SYMBOL_ASK) >= g_nf_eff_rsi_buy_ceil) {  // note: use m5_rsi not price
      JournalRecordSignal("SKIP","entry_quality_news_rsi_tighten","BB_BREAKOUT_RETEST","BUY",...);
      nf_retest_ok = false;
   }
   if(rt_dir == "SELL"
      && g_nf_eff_rsi_sell_min > g_sc.breakout_rsi_sell_floor
      && m5_rsi <= g_nf_eff_rsi_sell_min) {
      JournalRecordSignal("SKIP","entry_quality_news_rsi_tighten","BB_BREAKOUT_RETEST","SELL",...);
      nf_retest_ok = false;
   }
   if(nf_retest_ok) {
      direction  = g_retest.direction;
      ...
   }
   g_retest.active = false;
}
```

Note: the check must use `m5_rsi` (already computed), not `SymbolInfoDouble` price. The `JournalRecordSignal` call needs actual local variable values available in scope.

**Fix B — Cross-field validation (Warning 1)**

In `ReadScalperConfig()`, after parsing both pct fields, add:
```mql5
if(g_sc.news_filter_tighten_pct >= g_sc.news_filter_block_pct)
   g_sc.news_filter_tighten_pct = g_sc.news_filter_block_pct * 0.5;
```

Simple, silent correction — collapses to a safe default rather than erroring. No config json change needed.
