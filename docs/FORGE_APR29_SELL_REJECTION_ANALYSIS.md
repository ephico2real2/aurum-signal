# FORGE 2.7.6 — Apr 29 SELL Rejection Analysis

**Date:** 2026-05-09 | **Ref:** Run 21 vs Run 20 | **Symbol:** XAUUSD

---

## Background

Run 20 (broken Codex 2.7.6 — missing 2.7.5 SELL gates) took 5 SELL trades on Apr 29 and
won all of them for +$323.92. Run 21 (properly restored 2.7.5+2.7.6) took 0 trades on the
same day. This documents exactly which gates blocked the entries and what options exist to
capture them in a future version.

---

## What actually happened at 15:55 UTC Apr 29

From the Run 21 SIGNALS journal:

| Sim time | Gate | RSI | ADX | Notes |
|----------|------|-----|-----|-------|
| 09:18 UTC | `adx_min_sell` | 37.1 | 21.4 | ADX below 25 — pre-trend phase |
| 09:20 UTC | `adx_min_sell` | 33.6 | 20.0 | ADX still 20 — no trend yet |
| 15:35 UTC | `adx_min_sell` | 33.6 | 20.0 | Same |
| 15:44 UTC | `adx_min_sell` | 42.6 | 20.6 | Same |
| **15:55 UTC** | **`rsi_sell_adx_floor`** | **26.4–27.3** | **25.9** | ADX just crossed 25, but RSI deeply oversold |

The crash accelerated through the London/NY overlap. ADX crossed 25 (minimum for SELL
breakout) at ~15:55, but RSI had already crashed to 26–27. The `rsi_sell_adx_floor` gate
fired because:

```
ADX = 25.9  <  adx_sell_floor_threshold (35)  → weak-ADX regime
sell_floor_eff = max(33, 36) = 36
RSI = 26.4  ≤  36  → BLOCKED
```

Run 20 passed these entries because the Codex rebuild had removed `rsi_sell_adx_floor`
and the surrounding 2.7.5 SELL gate structure. Those were unfiltered entries — not a
feature of Run 20, a defect.

---

## Why the gate exists

The `rsi_sell_adx_floor` (weak-ADX two-tier RSI floor, added in 2.6.8 / 2.7.5) blocks
SELL entries where:
- ADX is in the 25–35 band (trend establishing, not confirmed)
- RSI is at extreme oversold (≤ 36 in weak-ADX regime)

The reasoning: RSI at 26 with ADX 25 is ambiguous — the price has moved hard but the
trend is not yet established. This profile matches both early crash entries (good) and
RSI exhaustion traps that reverse sharply (bad). The 2.7.5 gate set was designed after
analysis of Run 10/11 losses where SELL entries at extreme RSI with weak ADX were the
dominant loss category.

---

## Side finding — throttling bug in `rsi_sell_adx_floor`

The gate fires **on every tick** within the same M5 bar. The 15:55 bar alone produced
30+ identical journal rows. All other gates (`adx_min_sell`, `adx_spike_sell`,
`rsi_rising_sell`) have per-bar deduplication via `g_scalper_last_*_log_bar` guards.
`rsi_sell_adx_floor` does not. This inflates skip counts and wastes DB space.

**Fix (one line):** Add a `g_scalper_last_rsisellfloor_log_bar` guard identical to the
pattern used for `adx_min_sell` at lines 4816–4820.

---

## Options to capture these setups in a future version

### Option A — H1/H4 alignment bypass (recommended)

**Rule:** If H1 bear AND H4 bear, skip `rsi_sell_adx_floor` regardless of ADX level.

**Logic:** If both H1 and H4 are already bearish, the trend is confirmed at higher
timeframes. The weak-ADX concern on M5 is moot — the move is structural, not a
micro-spike. Apr 29 was a full multi-hour crash visible on H1/H4.

**Risk:** Slightly wider entry window on H1/H4 bear days. But this is the same
confirmation required by the existing H4/H1 alignment gate earlier in the chain.

**Implementation:** In the `rsi_sell_adx_floor` block (~lines 4822–4831), add:

```mql5
bool htf_bear_confirmed = h1_bear && h4_bear;
if(weak_adx_floor && !htf_bear_confirmed)
   sell_floor_eff = MathMax(sell_floor_eff, g_sc.breakout_rsi_sell_floor_weak_adx);
```

This only applies the stricter floor when HTF is not bearish — confirmed H1+H4 bear
bypasses it.

---

### Option B — ADX rising rate bypass

**Rule:** If ADX has risen by ≥ N points over the last M bars, treat as trending and
skip the weak-ADX RSI floor.

**Logic:** ADX lags price; in a crash the ADX starts at 20 and rises quickly. If it
has climbed from 20→26 in 3 bars, it is actively establishing — the "weak" label is
stale.

**Risk:** Harder to tune. ADX spike-from-flat (`adx_spike_sell`) already guards
against false ADX jumps from flat bases. Interaction risk between the two gates.

**Complexity:** Medium. Requires reading a lookback buffer already used by
`adx_spike_sell`, so the buffer infrastructure exists.

---

### Option C — Lower `rsi_sell_floor_weak_adx` threshold

**Rule:** Change `breakout_rsi_sell_floor_weak_adx` from 36 → 30.

**Effect:** Allows RSI 30–36 SELL entries even in weak-ADX regime. RSI 26–27 (Apr 29
level) would still be blocked by the base `rsi_sell_floor` (33).

**Problem:** This does NOT capture the Apr 29 entries (RSI 26–27 < 30). It only
loosens the marginal zone. The real Apr 29 entries are blocked by the BASE floor (33),
not the weak-ADX extension (36). To capture RSI 26–27 SELLs you would need to lower
`breakout_rsi_sell_floor` itself — which removes protection for all SELL entries, not
just crash conditions.

**Not recommended** as a standalone fix.

---

### Option D — Accept the filtering (default position)

The Apr 29 entries at RSI 26–27, ADX 25.9 are genuinely ambiguous. They were profitable
in Run 20, but Run 20's gate logic was broken — it is not a valid reference for what
"should" be taken. The existing gate design is correct for the general case.

If and when a future live run misses a high-conviction crash setup, revisit with a
specific loss/miss analysis. Do not change the gate based on a single backtested session.

---

## Recommendation

**Short term (2.7.6 patch):** Fix the throttling bug in `rsi_sell_adx_floor` — add the
per-bar deduplication guard. No gate logic change, purely a DB/logging fix.

**Medium term (2.7.7):** Implement Option A (H1+H4 bear bypass). Simple condition, 
aligns with the existing HTF alignment philosophy already built into the gate chain.
Should be validated against Run 19 date range to confirm it re-captures the Apr 29
entries without introducing new losses.

**Do not do:** Lower `rsi_sell_floor` globally. It protects against RSI exhaustion
traps across all conditions, not just crash days.

---

## Summary table

| Gate | Why it fired | RSI | ADX | Can bypass? |
|------|-------------|-----|-----|------------|
| `adx_min_sell` (09:18–15:44) | ADX below 25 minimum | 33–42 | 20–21 | No — correct filter |
| `rsi_sell_adx_floor` (15:55) | RSI ≤ 36 at ADX 25–35 | 26–27 | 25.9 | Yes — via H1+H4 bear bypass (Option A) |
| `entry_quality_news_rsi_tighten` | News proximity tightened SELL floor → 38 | 26–27 | 25.9 | Would not apply if rsi_sell_adx_floor is bypassed first |

The entries Run 20 "captured" on Apr 29 were taken through broken gates. Run 21 is
correctly filtering them. Option A provides a principled path to re-enable these entries
with proper HTF confirmation in 2.7.7.
