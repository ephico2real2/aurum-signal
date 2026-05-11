# Case Study 001 — G5001 Apr 29 16:00 SELL: Perfect Multi-TF Bearish Alignment

**Run**: 13 (FORGE v2.7.15)
**Date**: 2026-04-29 16:00 UTC (LONDON session)
**Outcome**: TAKEN → **+$519.54 over 13 winning legs in 30 minutes**
**Group magic**: 207402 (`magic_base + 5001`)
**Cascade magics**: 207402 native + 227402, 227403 (SELL LIMIT slots 0/1) + 227404–227408 (SELL STOP CONT slots 2–6)

---

## Why this case is worth studying

This is the cleanest BB_BREAKOUT SELL of the v2.7.x era. Every layer of the multi-timeframe stack confirmed the same direction simultaneously, every conditional bypass activated correctly, and every cascade infrastructure piece fired as designed. The trade ran from 4545.92 down to 4532.30 (−13.62 pts) and the EA captured the full move with full lot allocation at every leg.

It is also the entry that was **missed in Run 12** (blocked by `entry_quality_rsi_rising_sell`). The v2.7.14 H1 strong-bear bypass was specifically designed to unlock this class of entry — and the +$519 result validates the design.

---

## The Setup — Full SIGNALS Row Snapshot

### Price + Bollinger Bands

| Metric | Value | Meaning |
|---|---|---|
| Price | **4545.92** | Entry |
| BB upper | 4573.70 | — |
| BB mid | 4559.48 | — |
| BB lower | **4545.25** | Price is **0.67 pts BELOW** lower band |
| ATR | 5.57 | High volatility — TP1 @ 0.4×ATR = 2.2 pts achievable |
| Spread | 24.0 | Within 30-pt safety filter |

→ **True breakout outside BB → `lot_factor=1.0`** (no inside-band reduction). This is the key difference vs Run 12's G5001 which was inside-band (`lot_factor=0.25`).

### Momentum / Trend Indicators

| Indicator | Value | Verdict |
|---|---|---|
| M5 RSI | **26.3** | Deep oversold — would normally fail `rsi_sell_floor=30` |
| M5 ADX | 29.9 | Above `adx_min_sell=25` ✓ |
| M15 ADX | **26.3** | Above `h1h4_crash_sell_min_m15_adx=25` ✓ |
| H1 trend strength | **−1.997** | Strongest bearish reading possible (DI− dominates DI+) |
| H1 MACD histogram | **−2.9038** | Strongly negative — H1 momentum bearish |
| PSAR state | ABOVE (price below dot) | Bearish |
| RSI divergence | **HID_BEAR** | Confirms downtrend (NOT HID_BULL which would block) |
| Regime | TREND_BEAR, confidence 1.0 | Maximum bearish regime label |

---

## Why every gate passed

| Gate | Condition | Status |
|---|---|---|
| `adx_min_sell` | M5 ADX ≥ 25? | 29.9 ≥ 25 ✓ |
| `adx_spike_sell` | ADX 6 bars ago ≥ 25? | Yes (already trending) ✓ |
| `require_h1_di_sell` | H1 DI− > DI+? | h1_trend=−1.997 → emphatically yes ✓ |
| `crash_sell_bypass` (v2.7.13) | h1_bear AND h4_bear AND rsi>20 AND m15_adx≥25? | All true → **bypass active** ✓ |
| **`rsi_sell_floor=30`** | RSI > 30? | 26.3 < 30 — would FAIL, but **crash_sell_bypass SKIPS this check** ✓ |
| `rsi_sell_adx_floor` (weak-ADX floor=36) | — | Bypass would skip; also v2.7.14 H1 bypass (h1<−1.0) would skip ✓ |
| **`rsi_rising_sell` (v2.7.14 bypass test)** | RSI declining bar-over-bar? | **v2.7.14 H1 bypass (h1<−1.0) activates → skip** ✓ |
| `block_hid_bull_sell` | RSI_DIV == HID_BULL? | RSI_DIV=HID_BEAR (the opposite — confirms trend) ✓ |
| `require_macd_sell` | H1 MACD histogram < 0? | −2.9038 < 0 ✓ |
| `rr_too_low` | Risk:reward ≥ 1.5? | Implicit pass (entry took place) ✓ |
| `session_ny_sell_cutoff_utc=18` | UTC hour < 18? | 16:00 < 18 ✓ |

---

## The Trade Flow — 13 Winning Legs

| Time | Event | Lot | Price | P&L |
|---|---|---|---|---|
| 16:00:00 | 8 legs fired @ 4545.92 | 8×0.08 | 4545.92 | — |
| 16:00:00 | 3 TP1 partial closes (40% off) | — | — | $0 (partials) |
| 16:00:00 | 3 TP2 partial closes (30% off) | — | — | $0 (partials) |
| 16:00:07 | SELL LIMIT slot[0] cascade armed | 0.01 | — | — |
| 16:00:11 | SELL LIMIT L2 slot[1] cascade armed | 0.01 | — | — |
| 16:20:01 | 3 final closes at TP=4542.89 (−3 pts) | 3×0.08 | 4542.89 | +$61.84 |
| 16:20:01 | 2 base-magic runner closes (TP=4542.89) | 2×0.08 | 4542.89 | +$46.16 |
| 16:20:01 | SELL LIMITs hit TP (slot[0] +$4.62, slot[1] +$5.88) | 2×0.01 | 4542.89 | +$10.50 |
| **16:20:02** | **5 SELL STOP CONT legs armed at slot[2..6]** | **5×0.08** | — | — |
| 16:20:08 | Last native leg TP=4536.76 (−9 pts!) | 0.08 | 4536.76 | +$80.24 |
| **16:30:38** | **All 5 cascade STOP legs TP=4532.30 (−5 pts each)** | 5×0.08 | 4532.30 | **+$320.80** |
| **TOTAL** | **13 winning legs** | | | **+$519.54** |

---

## Why it earned $519 — three multipliers that compounded

1. **`lot_factor=1.0`** (price outside BB) → 8 native legs × full 0.08 lot = 0.64 total lot, vs Run 12 G5001's 0.02 × 8 = 0.16 lot (4× the size)
2. **First group of the run** → no leg-budget contention with prior open groups
3. **Cascade fired correctly** (v2.7.12+ infrastructure): 5 SELL STOP CONT legs @ 0.08 lot armed at slot[2..6] when M5 TP1 hit at 16:20. All 5 filled and closed at TP=4532.30 (5-pt move each) → +$320.80 from cascade alone

Without **any one of these three**, the P&L would have been roughly:
- Without #1 (inside-band 0.25× lot): ~$130
- Without #2 (compressed legs as G5003): ~$130
- Without #3 (no cascade): ~$200

The compound effect of all three: $519.

---

## The defining feature of this setup

**Multi-timeframe bearish alignment at maximum strength.** Every timeframe confirmed the same direction without ambiguity:

| TF | Signal | Reading |
|---|---|---|
| M5 | ADX | trending up (20.5 → 29.9 in 30 min) — early breakout |
| M5 | RSI | 26.3 (deep, but with continuation divergence) |
| M5 | BB | price outside lower band (true breakout) |
| M15 | ADX | 26.3 (passes crash bypass threshold of 25) |
| H1 | Trend strength | **−1.997** (DI− ≫ DI+ — bearish at maximum reading) |
| H1 | MACD histogram | −2.9038 (strong negative momentum) |
| H4 | Regime | TREND_BEAR confidence 1.0 |
| Divergence | HID_BEAR | Confirms continuation, not reversal |

When **all eight** of those line up at the same bar, it is the EA's job to fire. The fact that Run 12 v2.7.13 missed it (and Run 11 v2.7.12 missed it) was the regression v2.7.14's H1 strong-bear bypass was built to fix.

---

## Pattern Check — How to recognize similar setups

When monitoring new runs, the EA is most likely making the right call when these conditions co-occur:

```python
# Strong-bear setup pattern (the G5001 archetype)
is_perfect_sell = (
    h1_trend < -1.5                # H1 DI- strongly dominant
    and m15_adx >= 25              # M15 confirms trend (crash bypass arms)
    and m5_adx >= 25               # M5 not weak
    and rsi_divergence != "HID_BULL"  # no reversal warning
    and price < bb_lower           # true breakout (not inside-band)
    and atr >= 4.0                 # enough volatility for TP
    and 7 <= utc_hour < 18         # London/NY overlap, pre-cutoff
)
```

When all of those are true and the EA still SKIPs, look for:
- An ABSOLUTE floor that fires regardless of bypass (e.g. RSI < `rsi_sell_floor=30` without crash bypass conditions met) — see Apr 29 15:55 case in the Run 13 analysis
- Open-group cap (`max_open_groups`) — prior group still open
- `entry_quality_session_sell_cutoff` (UTC ≥ 18)

If none of those are firing and the entry still doesn't TAKEN, there is a real bug — flag it.

---

## Counterfactuals (what would have killed this trade)

| Hypothetical | What changes | Impact |
|---|---|---|
| Run 12 (v2.7.13) | No H1 bypass for `rsi_rising_sell` | **BLOCKED** — entry never fires, $519 left on table |
| Higher `rsi_buy_ceil` setting | — | No effect (SELL trade) |
| Lower `adx_min_sell=25 → 30` | M5 ADX 29.9 fails new threshold | **BLOCKED** — would lose $519 |
| `block_hid_bull_sell` set to 1 (default) | RSI_DIV=HID_BEAR, not HID_BULL | No effect — wrong divergence type |
| `session_ny_sell_cutoff_utc=15` | 16:00 ≥ 15 | **BLOCKED** — would miss the trade entirely |
| Cascade disabled | No SELL STOP CONT legs | **−$320 cascade profit**; total ≈ $200 |
| Inside-band lot factor would apply | If price had been at 4545.30 instead of 4545.92 | **lot_factor=0.25** → P&L ≈ $130 |

---

## What this case validates

| Feature | Version | Validated |
|---|---|---|
| H1 strong-bear bypass for `rsi_rising_sell` | v2.7.14 | ✓ — entry took which was blocked in Run 12 |
| H1 strong-bear bypass for `rsi_sell_adx_floor` weak-ADX inflation | v2.7.14 | ✓ — gate would not have inflated floor to 36 here |
| Crash sell bypass M15 ADX guard | v2.7.13 | ✓ — m15_adx=26.3 ≥ 25 allowed crash bypass; absolute floor correctly skipped |
| SELL STOP CONT cascade arm-time gates (RSI/ADX/H1 DI) | v2.7.12 | ✓ — all 5 legs armed and filled |
| Cascade slot expansion to [2..8] | v2.7.10 | ✓ — slot[2..6] used cleanly |
| BB_BREAKOUT direction-split TP1 (SELL=0.4×ATR) | v2.7.x | ✓ — TP1 at 0.4×5.57=2.2 pts achievable |

---

## What this case did NOT test

- **`block_hid_bull_sell`** — divergence was HID_BEAR, not HID_BULL. The G5001 (Run 11) catastrophe block test is May 4 17:10 in this same run (still to come at time of writing).
- **`session_ny_sell_cutoff_utc=18` boundary case** — 16:00 was well before cutoff. Boundary test would be the May 4 18:16-25 SELLs that fired in Run 12.
- **Inside-band lot factor** — price was 0.67 pts outside BB. Boundary test is when price is exactly at or just inside BB lower at entry.

---

## Cross-references

- Run 13 analysis: `docs/FORGE_RUN13_ANALYSIS.md`
- Run 12 analysis (where this same entry was BLOCKED): `docs/FORGE_RUN12_ANALYSIS.md`
- Entry conditions doc (gate definitions): `docs/FORGE_ENTRY_CONDITIONS.md`
- EA code (gates): `ea/FORGE.mq5:5340-5600` (SELL evaluation block)
- EA code (lot factors): `ea/FORGE.mq5:5840-5891` (combined_lot_factor)
- EA code (cascade arm): `ea/FORGE.mq5` — search `ArmPostTP1Ladder`
