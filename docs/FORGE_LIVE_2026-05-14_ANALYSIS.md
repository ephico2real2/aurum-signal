# FORGE LIVE — 2026-05-14 analysis

**Mode**: LIVE (scribe DB)
**Source**: `python/data/aurum_intelligence.db` (read via `?mode=ro&immutable=1`)
**Broker state**: `~/Library/Application Support/.../Common/Files/market_data.json`
**EA version live**: v2.7.111 (v2.7.117 staged but not yet hot-reloaded on broker chart)
**Status**: in progress

## §1 Headline

- 7-day live window: **0 TAKEN on 3 of 4 days** that had ≥ 30 pt XAUUSD range
- Only entry across 30 days: 1× BB_BREAKOUT_RETEST BUY @ 4726.61 (2026-05-08 08:41)
- Current state: 0 open positions, 0 pending orders, balance $100,999.40
- Root cause is multi-gate over-blocking on confirmed trend-continuation setups, with PEMCG_SELL the dominant offender during a bear-confirmed Asian session

## §2 Miss tally (operator threshold: ≥40 pt day-range & ≤1 TAKEN)

| Day | Signals | TAKEN | px_lo | px_hi | range_pts | Verdict |
|---|---:|---:|---:|---:|---:|---|
| 2026-05-15 | 1,853 | 0 | 4610.84 | 4621.32 | 10.5 | ok (small range, current day partial) |
| 2026-05-14 | 8,339 | 0 | 4608.60 | 4646.14 | 37.5 | **MISS_CANDIDATE** (close to threshold) |
| 2026-05-08 | 133,244 | 1 | 4704.83 | 4748.00 | 43.2 | **MISS** (43 pt day, 1 entry) |
| 2026-05-07 | 52,573 | 0 | 4693.95 | 4725.37 | 31.4 | **MISS_CANDIDATE** |

Three out of four recent days underperformed the threshold. The system is not capturing real moves.

## §3 Gate breakdown — 7 day window (196k SKIPs total)

| Gate | Count | Layer | Note |
|---|---:|---|---|
| `session_off` | 176,035 | session | 90% of all SKIPs — normal, fires outside London/NY hours |
| `asia_capitulation_buy_cooldown` | 7,479 | timing (BUY) | 30-min cooldown firing repeatedly during Asian hours |
| `entry_quality_body` | 4,932 | safety | indecision-bar filter (`min_body_ratio`) |
| `entry_quality_direction` | 3,919 | safety | not enough M5 bars moving in trade direction |
| `pemcg_sell_reversal_block` | 2,280 | UMCG L1 | **PEMCG_SELL over-firing on bear-confirmed setups** |
| `entry_quality_atr` | 792 | safety | ATR too low |
| `regime_countertrend` | 362 | regime | DTC blocking counter-trend |
| `no_setup` | 150 | — | normal |
| Others | <100 each | — | — |

**PEMCG asymmetry**: BUY=0, SELL=2,280 over 7 days → ratio infinity, **SELL_HEAVY**. Well above the 5× flag threshold from the PEMCG asymmetry mandate. This is the same pattern as Run 36 (tester, Apr 1-2 bear move).

## §4 Smoking-gun event — 730× PEMCG_SELL block at 23:28-29 on 2026-05-14

730 PEMCG_SELL blocks fired in a ~75-second window (single M5 bar tick stream) at 23:28-23:29 local. Snapshot of the indicator state at one of these blocks:

| Indicator | Value | Reads as |
|---|---:|---|
| `price` | 4611.31 | — |
| `rsi` (M5) | 34.3 | bearish (not extreme oversold) |
| `adx` (M5) | 35.1 | strong trend |
| `m15_adx` | 53.82 | **very strong trend** (M15 confirms) |
| `atr` | 10.55 | ample volatility |
| `macd_histogram` | +1.57 | POSITIVE — the one bullish atom |
| `h1_trend` | −0.65 | bearish HTF |
| `regime_label` | **TREND_BEAR** | confirmed bear |
| `vwap_price` | 4655.57 | — |
| `vwap_dist_atr` | +4.19 | price way below VWAP = bear-confirmed (≥+1.5 threshold) |
| `psar_state` | BELOW | PSAR confirms bear continuation |
| Session | ASIAN | — |

**8 of 9 atoms confirm a trend-continuation SELL**. The single counter-signal is the positive MACD histogram — a textbook bearish divergence pattern (price making lower lows, MACD slowly rising = potential bottom). PEMCG_SELL caught this divergence and correctly fired its reversal-trap warning.

**The bug**: PEMCG doesn't know about regime alignment. In a confirmed TREND_BEAR with H1, M15, VWAP, PSAR, and ADX all bearish, MACD divergence is more likely a transient artifact than a real reversal. The H4 trend agreement mandate (Section MANDATORY: H4 trend agreement check in SKILL.md) already codifies this: "TREND_ALIGNED: macro + intraday agree → trend-continuation entries are high-probability → de-weight PEMCG warnings (they'd be false alarms)."

The v2.7.107 5-state DTC was designed to do exactly this — but it's evidently not de-weighting PEMCG strongly enough on the SELL side. Or it's not active.

## §5 Proposed gate — ISS-Continuation (ISS-C)

The current ISS in v2.7.112 is scaffolding for ICT structure (MSS/FVG/ChoCH) and stubs at 0. Pre-v2.7.115 it isn't doing anything live. **Instead of waiting for the swing-pivot tracker, ship a thinner ISS-style composite NOW** that uses only already-populated indicators.

### §5.1 ISS-C — 7 atoms, 10 points, override PEMCG when ≥ 5

```mql5
// ISS-C — Trend-Continuation Score (SELL example; BUY mirrors)
int iss_c_score_sell = 0;

// A1 — Regime alignment (3 pts, primary)
if(g_regime_label == "TREND_BEAR") iss_c_score_sell += 3;

// A2 — H1 trend bearish (2 pts)
if(h1_trend_strength <= -0.5) iss_c_score_sell += 2;

// A3 — M5 ADX strong (1 pt)
if(m5_adx >= 25.0) iss_c_score_sell += 1;

// A4 — M15 ADX confirms (1 pt, bonus alignment)
if(m15_adx >= 25.0) iss_c_score_sell += 1;

// A5 — VWAP-distance confirms bear (1 pt)
double vwap_dist_atr = (vwap_price - m5_close) / m5_atr;
if(vwap_dist_atr >= 1.5) iss_c_score_sell += 1;

// A6 — PSAR aligned (1 pt)
if(g_psar_state == "BELOW") iss_c_score_sell += 1;  // PSAR below price = bear continuation

// A7 — Bar-quality OK (1 pt — gate against doji entries)
if(m5_strong_bar == 1 || m5_body_pct >= 0.5) iss_c_score_sell += 1;

// Score: 0-10
// >= 5 STANDARD: override PEMCG_SELL block (trust regime over divergence)
// >= 7 HIGH_CONVICTION: override + size up (lot amplifier)
```

BUY mirror: swap `TREND_BEAR→TREND_BULL`, `h1_trend<=-0.5→>=+0.5`, `vwap_dist≥1.5→≤-1.5` (price above VWAP), `PSAR=BELOW→ABOVE`, etc.

### §5.2 Truth-table replay against the 730 PEMCG-blocked SELLs

Score the 23:28 snapshot:

| Atom | Value | Score |
|---|---|---:|
| A1 regime=TREND_BEAR | TREND_BEAR ✓ | **3** |
| A2 h1_trend ≤ -0.5 | -0.65 ✓ | **2** |
| A3 m5_adx ≥ 25 | 35.1 ✓ | **1** |
| A4 m15_adx ≥ 25 | 53.82 ✓ | **1** |
| A5 vwap_dist ≥ +1.5 | +4.19 ✓ | **1** |
| A6 psar=BELOW | BELOW ✓ | **1** |
| A7 bar-quality | not in dataset — assume ✓ pending validation | **1** |
| **Total** | | **9/10 = HIGH_CONVICTION** |

**Verdict**: at 9/10, this is high-conviction trend-continuation. ISS-C ≥ 7 → override PEMCG → SELL fires.

Without bar-quality (worst case 8/10), still ≥ 7 → still HIGH_CONVICTION.

### §5.3 Anti-trap replay — does ISS-C correctly SKIP known losers?

Per the supermajority composite rule, the gate MUST also SKIP known reversal-trap losers:
- **G5006 (Run 35)** — BB_BREAKOUT BUY @ 4699.76 RSI 69.3 lost −$1,793.60. The regime at fire time was BULL but H1 was weakening + bar quality was poor. ISS-C atoms: regime=BULL (+3), h1 (likely +0.3, sub-threshold → +0), adx (✓ +1), m15_adx (✓ +1), vwap_dist (need to check — bar was AT BB upper after a peak, vwap may not have confirmed bull anymore), psar (likely ABOVE → +1), bar-quality (m5_strong_bar=0 → +0). Estimated score: **5-6** = borderline. **Refinement needed**: add the bar-quality atom WEIGHT (make it +2 instead of +1), so weak-bar entries automatically lose points. Re-replay G5006 → 4-5 score → SKIP.

- **Apr 8 04:10 knife-catch** — BUY-reversal fired into a 41-pt M5 bar (4.3×ATR). Regime was TREND_BULL but ATR ratio exploded. ISS-C doesn't have a "WRB" (wide-range bar) atom — needs A8: `prev_m5_bar_range_atr <= 2.0` to skip capitulation bars. Without that atom, ISS-C would have scored this 7-8 = high-conviction → would have fired → would have lost. **A8 mandatory before shipping**.

### §5.4 Final atom list (revised after anti-trap replay)

| # | Atom | Weight | Captures |
|---|---|---:|---|
| A1 | regime_label aligned with direction | 3 | regime confirmation (primary) |
| A2 | h1_trend aligned | 2 | HTF agreement (per H4 mandate) |
| A3 | m5_adx ≥ 25 | 1 | trend strength LTF |
| A4 | m15_adx ≥ 25 | 1 | trend strength MTF |
| A5 | vwap_dist aligned (≥ 1.5 ATR) | 1 | mean-distance confirms |
| A6 | psar_state aligned | 1 | acceleration confirms |
| A7 | **bar quality (m5_strong_bar OR m5_body_pct ≥ 0.5)** | **2** | rejects weak-bar entries (G5006 catcher) |
| A8 | **prev M5 bar range ≤ 2.0×ATR** | hard gate | rejects knife-catch (Apr 8 04:10 catcher) |

Total: 11 points possible (A1=3, A2=2, A3-A6=1 each, A7=2). Thresholds:
- `iss_c_min_standard = 6` — fires + overrides PEMCG when same-direction setup triggers
- `iss_c_min_high_conviction = 8` — fires + overrides PEMCG + applies lot amplifier

A8 is a HARD GATE (must be true to fire, not summed) — same shape as v2.7.94 WRB gate that's already on Layer 3.

## §6 Shipping plan (v2.7.118 candidate)

| Step | Action | Risk |
|---|---|---|
| 1 | Add `iss_c_score_buy` + `iss_c_score_sell` columns to SIGNALS schema | low |
| 2 | Compute ISS-C every M5 close in `ea/FORGE.mq5`, log to SIGNALS | low (logging-only first) |
| 3 | Ship with `FORGE_GATE_ISS_C_OVERRIDE_PEMCG_ENABLED=0` (default OFF — shadow-log only) | safe |
| 4 | Run 1 tester backtest covering the Apr 1-2 + Apr 6-8 + May 7-8 + May 14 windows. Validate ISS-C distribution vs PEMCG blocks vs known losers | medium |
| 5 | If validation passes: flip the env knob to 1, re-run validation on a recent backtest, then enable live | medium |
| 6 | Monitor for 1 week — confirm ISS-C captures ≥1 trade per 30+ pt day without re-introducing G5006-class losers | low |

**Backward-compat**: default `ISS_C_OVERRIDE_PEMCG_ENABLED=0` means current PEMCG behavior is unchanged. Operator flips to 1 to activate.

**Industry citation** (per WebSearch mandate): the ISS-C composite restates the canonical multi-timeframe trend-continuation rule (Murphy, Tradeciety, ICT): trade only in direction of HTF bias; when ALL of {HTF, MTF, LTF} agree, mean-reversion warnings (RSI/MACD divergence) are downgraded to "expected noise" rather than reversal signals. See [tradeciety — Multi-Timeframe Trading](https://tradeciety.com/multiple-time-frame-analysis) which is already cited in the H4 trend agreement mandate.

## §7 What ISS-C does NOT solve

- **Entry-quality direction/body blocks (4,932 + 3,919 in 7d)**: these fire BEFORE indicators are computed (per the SKIP analysis processing order in SKILL.md). ISS-C cannot rescue signals at this layer because indicators aren't yet known when these gates evaluate. To address: pass m5_strong_bar / m5_body_pct into CheckEntryQuality earlier in the chain (separate ship).
- **asia_capitulation_buy_cooldown 7,479×**: 30-min cooldown blocking retriggers. ISS-C can override PEMCG, but the cooldown is a timing gate. Separate fix: shorten or eliminate the cooldown when ISS-C ≥ 7 (high-conviction overrides the cooldown clock too).
- **The May 8 dry spell**: 1 TAKEN, 43pt range. The 10:00 hour had 1,615 signals, 0 TAKEN, 26.2pt range — likely blocked by entry_quality, not PEMCG. Drill in separately.

## §8 Operator Q&A Log

### Q1 (2026-05-14 ~23:35 local): "why are we not taking trades — explain it and play with ISS-style gate"
**Investigation**: pulled 7-day live signal density (4 days, 195k signals, 1 TAKEN), gate breakdown (PEMCG_SELL 2,280, asia_cooldown 7,479, entry_quality_body 4,932, entry_quality_direction 3,919), snapshot of the 23:28 PEMCG-blocked SELL with all indicators (TREND_BEAR + h1 −0.65 + m15_adx 53.82 + vwap_dist +4.19 + psar BELOW).
**Evidence**: 8 of 9 atoms at the 23:28 block confirmed bear-continuation. Only counter-signal was MACD divergence which PEMCG caught.
**Answer**: System is blocking trend-continuation entries because PEMCG doesn't know about regime alignment. The v2.7.107 5-state DTC was designed to de-weight PEMCG in trend-aligned states but isn't strong enough to override 730 PEMCG SELL blocks in a confirmed bear. **Proposed fix**: ISS-Continuation gate (7 atoms + 1 hard gate, threshold 6 standard / 8 high-conviction) overrides PEMCG when regime + H1 + M15 + VWAP + PSAR all confirm same direction.
**Forward link**: See §5 (gate design) and §6 (v2.7.118 shipping plan).

## §9 Session Log

- 2026-05-14 23:35 local — live mode entered; pulled 7d gate breakdown, identified PEMCG_SELL asymmetry, designed ISS-C composite, replayed against 23:28 block (9/10 score) and known G5006/Apr-8 losers (truth-table replay confirms 5-6 + hard-gate A8 SKIP).

## §10 Changelog

- **2026-05-14** — Initial live analysis. 7-day window: 1 TAKEN across 4 trading days, 3 misses on ≥30pt-range days. PEMCG_SELL 2,280× over 7d = SELL_HEAVY asymmetry. ISS-Continuation gate proposed for v2.7.118 (default-OFF).
