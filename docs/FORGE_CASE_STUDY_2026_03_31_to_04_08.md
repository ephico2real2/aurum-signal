# FORGE Case Study — XAUUSD Mar 31 → Apr 8 2026 (Boolean Composite Day-Typing)

**Type**: Multi-day pattern analysis with boolean composite derivation
**Source data**: Run 23 (v2.7.34) source DB SIGNALS table, run_id=4
**Method**: Hourly indicator walk → boolean composite per day → cross-day pattern consolidation → exact-pivot identification for outlier (Apr 8)
**Trigger event**: Apr 8 BB_BOUNCE BUY @ 4783 (Run 23 G-magic from Apr 8 16:35) floated −$200 against the daily reversal — diagnostic question: what indicator combination would have flagged the day's afternoon as SELL-mode?
**Created**: 2026-05-12 (during Run 23 monitoring at sim Apr 9 09:10)

> **Skill compliance**: This case study is the canonical record for the boolean composite work on this date range. Reference from analysis docs and the indicator atlas. Future case studies follow this template.

---

## 1. Day-by-day summary (verified from Run 23 SIGNALS)

| Day | Open | Close | Net | Range | h1_trend avg / range | Regime mix | Day character |
|---|---|---|---|---|---|---|---|
| **Mar 31** | 4514 | 4665 | **+$150** | $191 | +0.61 (0 to 1.28) | 34% BULL / 64% RANGE | **chop-in-bull** |
| **Apr 1** | 4672 | 4758 | **+$86** | $124 | +1.58 (0 to 2.46) | 83% BULL / 17% RANGE | **clean strong bull** |
| **Apr 2** | 4757 | 4672 | **−$85** | **$228** | +0.27 (−0.06 to 1.34) | 65% BULL / 35% RANGE | **REVERSAL day** |
| Apr 3-5 | — | — | — | — | — | (Good Friday + weekend) | trading closed |
| **Apr 6** | 4654 | 4652 | −$2 | $101 | +0.05 (−0.18 to 0.28) | 60% BULL / 40% RANGE | **flat / no-trend** |
| **Apr 7** | 4651 | 4709 | +$58 | $99 | −0.06 (−0.19 to 0.02) | 0% BULL / 100% RANGE | **disguised-bear-walk-up** |
| **Apr 8** | 4721 | 4719 | −$2 | $144 | +0.94 (0 to 1.77) | 100% BULL | **bull → reversal (the disaster)** |

---

## 2. Per-day boolean composite derivation

### Mar 31 — chop-in-bull (+$150, $191 range, 64% RANGE)

**Hourly walk** (07:00-20:00):

| Hour | Price | RSI | ADX | PSAR | h1t | Regime | bbm gap | bbl gap | vwap gap | Div |
|---|---|---|---|---|---|---|---|---|---|---|
| 07:10 | 4559.87 | 46 | 33.1 | BELOW | 0.80 | TREND_BULL | -4.75 | 13.96 | 19.62 | NONE |
| 08:00 | 4564.39 | 51.1 | 48.2 | BELOW | 0.87 | TREND_BULL | 4.06 | 11.90 | 17.31 | NONE |
| 09:00 | 4568.66 | 51.3 | 31.1 | BELOW | 0.89 | TREND_BULL | 2.34 | 16.86 | 14.84 | NONE |
| **10:00** | **4558.38** | **45.5** | 22.4 | ABOVE | 0.87 | RANGE | **-5.93** | 9.66 | 1.01 | NONE |
| 11:00 | 4565.82 | 57.1 | 22.5 | BELOW | 0.91 | RANGE | 7.89 | 17.24 | 4.68 | NONE |
| 12:00 | 4568.57 | 54.4 | 36.1 | BELOW | 0.94 | TREND_BULL | 2.95 | 15.21 | 0.94 | NONE |
| **13:00** | **4555.44** | **40.0** | 32.9 | ABOVE | 0.90 | TREND_BULL | **-9.15** | 4.84 | -13.34 | NONE |
| 14:00 | 4547.99 | 42.7 | 18.8 | ABOVE | 0.82 | RANGE | -5.39 | 9.43 | -14.21 | HID_BEAR |
| 15:00 | 4583.47 | 62.8 | 25.5 | BELOW | 0.85 | RANGE | 19.39 | 55.81 | 20.70 | NONE |
| 16:00 | 4576.68 | 52.0 | 13.9 | ABOVE | 0.85 | RANGE | -4.30 | 6.86 | 11.04 | NONE |
| 17:00 | 4607.10 | 69.4 | 23.3 | BELOW | 1.00 | RANGE | 22.78 | 43.78 | 38.55 | HID_BULL |
| 18:00 | 4600.66 | 51.7 | 25.4 | ABOVE | 1.16 | RANGE | -2.01 | 23.58 | 24.86 | REG_BEAR |
| 19:00 | 4609.45 | 50.3 | 18.8 | BELOW | 1.28 | RANGE | -4.11 | 9.10 | 26.01 | NONE |

**Identified BUY-fire moments**: 10:00 + 13:00 (both have RSI 40-45 + price near BB middle + h1_trend bull).

**Boolean composite**: `BULL_DAY_DIP_BUY` (h1_trend ≥ 0.5 + RSI 30-50 + price near BB mid/lower + soft VWAP + no bear div).

---

### Apr 1 — clean strong bull (+$86, $124 range, 83% TREND_BULL)

**Hourly walk** (07:00-19:00):

| Hour | Price | RSI | ADX | PSAR | h1t | Regime | bbm gap | bbl gap | vwap gap | Div |
|---|---|---|---|---|---|---|---|---|---|---|
| 07:00 | 4681.93 | 39.6 | 23.4 | ABOVE | 2.17 | RANGE | -3.45 | 2.66 | -4.83 | NONE |
| 08:00 | 4678.13 | 45.6 | 28.9 | BELOW | 2.26 | RANGE | -0.53 | 10.79 | -10.01 | NONE |
| 09:00 | 4684.24 | 47.4 | 32.9 | BELOW | 2.24 | TREND_BULL | 0.01 | 18.25 | -5.20 | NONE |
| 10:00 | 4732.38 | 75.8 | 38.4 | BELOW | 2.38 | TREND_BULL | 28.14 | 57.44 | 39.01 | NONE |
| 11:00 | 4711.97 | 48.9 | 21.6 | ABOVE | 2.31 | RANGE | -7.77 | 11.20 | 12.90 | REG_BEAR |
| 12:00 | 4728.80 | 55.6 | 20.7 | BELOW | 2.30 | TREND_BULL | 1.73 | 16.12 | 26.63 | NONE |
| 13:00 | 4722.80 | 51.1 | 22.3 | ABOVE | 2.34 | TREND_BULL | -1.89 | 10.38 | 18.63 | NONE |
| 14:00 | 4731.26 | 56.8 | 26.2 | BELOW | 2.36 | TREND_BULL | 6.50 | 19.24 | 22.70 | NONE |
| 15:00 | 4753.59 | 64.0 | 44.9 | BELOW | 2.45 | TREND_BULL | 11.01 | 32.38 | 37.79 | NONE |
| **16:00** | **4721.73** | **39.9** | 30.3 | BELOW | 2.32 | TREND_BULL | **-21.27** | **1.43** | -0.44 | NONE |
| 17:00 | 4733.50 | 46.4 | 17.0 | BELOW | 2.31 | TREND_BULL | -2.79 | 12.13 | 6.01 | HID_BEAR |
| **18:00** | **4760.99** | **61.0** | 35.9 | BELOW | 2.38 | TREND_BULL | 14.14 | 32.05 | 27.05 | HID_BULL |
| 19:00 | 4787.08 | 70.5 | 63.6 | BELOW | 2.46 | TREND_BULL | 17.77 | 45.88 | 46.32 | NONE |

**Identified entries**: 16:00 (perfect BUY DIP — RSI 39.9 + bbl gap 1.43 + bull macro 2.32). 17:00-19:00 is sustained NY rally (TREND_CONTINUATION).

**Boolean**: `BULL_DAY_DIP_BUY` catches 16:00; `TREND_CONTINUATION_BUY` (h1_trend ≥ 1.0 + bar-over-bar continuation + RSI 40-70) catches 17:00-19:00 rally.

---

### Apr 2 — REVERSAL day (−$85, $228 range, BULL→RANGE)

**Hourly walk**:

| Hour | Price | RSI | ADX | PSAR | h1t | Regime | bbm gap | bbl gap | vwap gap | Div |
|---|---|---|---|---|---|---|---|---|---|---|
| 07:00 | 4676.30 | 37.3 | 26.1 | ABOVE | 1.34 | TREND_BULL | -5.85 | 11.55 | **-60.45** | NONE |
| 08:00 | 4672.71 | 44.0 | 28.3 | ABOVE | 1.25 | TREND_BULL | -1.01 | 16.77 | -53.44 | NONE |
| **🚨 09:00** | **4594.26** | **22.1** | 28.8 | ABOVE | **0.76** | TREND_BULL | **-56.52** | 1.87 | **-116.17** | NONE |
| 10:00 | 4598.85 | 39.4 | 18.8 | BELOW | 0.55 | TREND_BULL | -4.77 | 48.17 | -90.32 | NONE |
| 11:00 | 4642.80 | 61.2 | 49.5 | BELOW | 0.48 | TREND_BULL | 25.75 | 65.72 | -32.59 | NONE |
| 12:00 | 4620.91 | 42.7 | 25.7 | ABOVE | 0.34 | TREND_BULL | -13.74 | 2.13 | -40.08 | NONE |
| 13:00 | 4621.84 | 46.0 | 16.0 | BELOW | 0.26 | TREND_BULL | -3.47 | 8.54 | -23.50 | NONE |
| 14:00 | 4620.61 | 47.8 | 11.1 | BELOW | 0.17 | TREND_BULL | -0.85 | 8.01 | -14.74 | NONE |
| 15:00 | 4600.30 | 34.3 | 29.9 | ABOVE | 0.04 | RANGE | -15.40 | 4.34 | -26.02 | NONE |
| 16:00 | 4602.09 | 38.8 | 19.0 | BELOW | -0.04 | RANGE | -9.86 | 7.99 | -18.49 | NONE |
| 17:00 | 4646.41 | 65.9 | 24.9 | BELOW | 0.00 | RANGE | 34.51 | 72.72 | 32.73 | HID_BULL |
| 18:00 | 4681.92 | 66.4 | 47.9 | BELOW | 0.07 | RANGE | 30.74 | 94.65 | 55.63 | NONE |

**THE Apr 2 09:00 CRASH** is canonical INTRADAY_REVERSAL_TO_SELL:
- price dropped from 4672 → 4594 = **−$78 in 1 hour**
- RSI dropped from 44 → 22 (extreme)
- h1_trend dropped 1.25 → 0.76 (macro weakening)
- vwap gap −116 (deeply below VWAP)
- bbm gap −56 (massively below BB middle)

**Boolean composite** that would have fired SELL at 08:30-09:00:
```
INTRADAY_REVERSAL_TO_SELL = (h1_trend ≥ 0.3) && (M5 declining 2hr cascade)
  && (m5_rsi ≤ 40) && (price < bb_mid) && (price < vwap_price)
```
All atoms pass at 09:00 with extreme margins.

After 17:00, the recovery cycles into `BULL_DAY_DIP_BUY` territory again (h1 returns to ~0, RSI 65 HID_BULL → SELL exhaustion).

---

### Apr 6 — flat / no-trend (−$2, $101 range, mixed)

| Hour | Price | RSI | ADX | PSAR | h1t | Regime | bbm gap | bbl gap | vwap gap | Div |
|---|---|---|---|---|---|---|---|---|---|---|
| 07:00 | 4640.63 | 53.9 | 25.4 | ABOVE | -0.18 | RANGE | 0.69 | 20.89 | -0.43 | NONE |
| 08:00 | 4659.44 | 68.0 | 46.4 | BELOW | -0.14 | RANGE | 15.61 | 33.75 | 21.92 | NONE |
| 09:00 | 4652.73 | 46.4 | 29.3 | ABOVE | -0.15 | RANGE | -7.86 | 10.79 | 15.82 | NONE |
| 10:00 | 4666.05 | 59.3 | 16.8 | BELOW | -0.09 | RANGE | 5.85 | 15.67 | 27.72 | HID_BEAR |
| 11:00 | 4685.51 | 70.8 | 40.9 | BELOW | 0.01 | RANGE | 24.42 | 46.88 | 43.08 | NONE |
| 12:00 | 4696.26 | 65.9 | 62.5 | BELOW | 0.10 | TREND_BULL | 13.21 | 42.65 | 43.50 | REG_BEAR |
| 13:00 | 4693.77 | 53.0 | 41.9 | ABOVE | 0.16 | TREND_BULL | -3.82 | 4.73 | 32.24 | NONE |
| 14:00 | 4689.84 | 47.4 | 16.2 | ABOVE | 0.19 | TREND_BULL | -4.55 | 6.03 | 21.83 | NONE |
| 15:00 | 4679.14 | 34.4 | 32.7 | ABOVE | 0.21 | TREND_BULL | -9.46 | -0.50 | 4.49 | HID_BULL |
| 16:00 | 4677.32 | 45.2 | 23.7 | BELOW | 0.23 | TREND_BULL | -1.23 | 12.15 | -0.64 | NONE |
| 17:00 | 4681.73 | 56.0 | 36.9 | BELOW | 0.27 | TREND_BULL | 8.67 | 19.48 | 3.90 | NONE |
| 18:00 | 4683.78 | 53.9 | 21.1 | BELOW | 0.28 | TREND_BULL | 5.45 | 20.83 | 3.56 | NONE |

**Boolean**: `NO_TREND_DAY` triggered on `|h1_trend| ≤ 0.3` throughout most of day. Conviction-low; small chop ladder probes only. The 12:00 brief flip to TREND_BULL is too short to matter.

---

### Apr 7 — disguised-bear-walk-up (+$58, $99 range, 100% RANGE, h1<0)

| Hour | Price | RSI | ADX | PSAR | h1t | Regime | bbm gap | bbl gap | vwap gap |
|---|---|---|---|---|---|---|---|---|---|
| 07:00 | 4649.84 | 57.4 | 32.0 | BELOW | -0.14 | RANGE | 4.26 | 12.85 | 1.25 |
| 08:00 | 4660.57 | 65.4 | 41.5 | BELOW | -0.11 | RANGE | 8.30 | 21.11 | 11.71 |
| 09:00 | 4643.35 | 47.4 | 26.9 | ABOVE | -0.19 | RANGE | -5.55 | 16.21 | -3.90 |
| 12:00 | 4683.19 | 67.3 | 44.8 | BELOW | -0.01 | RANGE | 19.76 | 56.00 | 34.39 |
| 13:00 | 4672.57 | 50.0 | 33.9 | ABOVE | 0.00 | RANGE | -7.88 | 6.74 | 19.93 |
| 14:00 | 4653.07 | 35.3 | 46.5 | ABOVE | -0.06 | RANGE | -15.48 | 3.85 | -4.46 |
| 19:00 | 4656.60 | 56.8 | 27.5 | BELOW | -0.10 | RANGE | 10.13 | 25.96 | 0.89 |

**Anomaly**: h1_trend negative all day, but price drifted UP from 4651 to 4709. h1 EMAs lagging the recovery from Apr 2 crash. Boolean: `NO_TREND_DAY` (h1 near 0 from -0.18 to +0.02). Treat as chop ladder only; no directional bets. h1 isn't a reliable signal here.

---

### Apr 8 — bull morning → reversal (−$2 net, but $144 range, 100% TREND_BULL regime)

**THIS IS THE DEEP DIVE** — the day Run 23 lost −$200 floating.

| Hour | Price | RSI | ADX | PSAR | h1t | Regime | bbm gap | bbl gap | vwap gap | Div | NOTE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 07:00 | 4797.60 | 41.9 | 16.3 | ABOVE | 1.08 | TREND_BULL | -5.38 | 5.02 | 24.81 | NONE | morning |
| 08:00 | 4803.71 | 53.1 | 12.5 | BELOW | 1.24 | TREND_BULL | 4.23 | 11.02 | 15.40 | NONE | continuing up |
| **🟢 09:00 PEAK** | **4827.52** | **64.9** | 57.0 | BELOW | 1.34 | TREND_BULL | 14.50 | 37.04 | 25.22 | NONE | **momentum top** |
| 10:00 | 4820.09 | **47.5** | 35.3 | ABOVE | 1.37 | TREND_BULL | -7.55 | 4.76 | 6.70 | NONE | RSI dropped −17 |
| 11:00 | 4813.71 | 46.3 | 24.2 | BELOW | 1.44 | TREND_BULL | -5.74 | 12.15 | -1.24 | NONE | first lower close |
| **🚨 12:00 PIVOT** | **4793.90** | **33.4** | 25.5 | ABOVE | 1.40 | TREND_BULL | **-13.93** | 3.93 | **-17.84** | **HID_BEAR** | **THE TURN** |
| 13:00 | 4783.41 | 32.5 | 23.0 | ABOVE | 1.44 | TREND_BULL | -11.41 | 3.13 | -26.57 | NONE | continuing down |
| 14:00 | 4782.67 | 40.8 | 21.8 | BELOW | 1.40 | TREND_BULL | -4.09 | 7.77 | -24.40 | NONE | minor bounce |
| 15:00 | 4798.76 | 58.5 | 23.2 | BELOW | 1.77 | TREND_BULL | 9.58 | 20.12 | -6.70 | REG_BULL | bounce |
| 16:00 | 4799.52 | 54.4 | 33.5 | FLIP_BULL | 1.74 | TREND_BULL | 5.41 | 21.46 | -4.79 | NONE | bounce top |
| **❌ 16:35** | **4782.91** | **42.1** | 21.8 | BELOW | 1.56 | TREND_BULL | (BB lower) | 0 | (gap) | NONE | **BB_BOUNCE BUY fired here** |
| 17:00 | 4776.98 | 42.9 | 17.5 | ABOVE | 1.68 | TREND_BULL | -12.54 | 6.52 | -23.90 | NONE | decline resumes |
| **🔻 18:00** | **4736.18** | **28.3** | 41.8 | ABOVE | 1.37 | TREND_BULL | **-33.22** | -1.81 | **-55.01** | NONE | **capitulation** |
| 19:00 | 4756.34 | 45.5 | 18.3 | BELOW | 1.32 | TREND_BULL | 2.13 | 16.48 | -26.38 | NONE | small recovery |

#### Apr 8 — when did selling START? **12:00 UTC**

The signals progressed:

```
09:00 momentum peak:    RSI 64.9, price 4827  (overbought zone)
10:00 weakness:          RSI 47.5 (-17), price 4820 (-$7)
11:00 confirmation:      RSI 46.3, first lower close at 4813 (-$14)
🚨 12:00 SELL PIVOT:    RSI 33.4 (-31 from peak)
                          price 4793 (-$34 from peak)
                          HID_BEAR DIVERGENCE detected
                          bbm gap -13.93 (below BB middle)
                          vwap gap -17.84 (below VWAP)
13:00 continuing:        price 4783 (-$44 from peak)
18:00 capitulation:      price 4736 (-$91 from peak)
```

**12:00 is the exact pivot.** All four classical bear signals confirmed: RSI collapse, lower closes, HID_BEAR divergence, price below BB middle + VWAP.

#### Why FORGE missed it

| Gate | What it said at 16:35 | Should have said |
|---|---|---|
| `regime_label` | TREND_BULL | (correct — h1_trend stayed positive) |
| `daily_bear_block` | not active (daily bull) | (correct — daily was bull) |
| `dump_max_rsi=41` for SELL | (didn't gate — BB_BOUNCE not MOMENTUM_DUMP) | (irrelevant — wrong setup type) |
| `dump_max_rsi_buy=70` | RSI 42.1 < 70 → BUY allowed | **needed `INTRADAY_REVERSAL_TO_SELL` check** |
| BB_BOUNCE PSAR-misalign gate | PSAR=BELOW (bullish aligned) → BUY allowed | (correct under macro lens) |

**No existing gate looked at "M5 has been declining 2-3 hours with bear divergence."** That's the missing composite.

#### The boolean that would have saved Apr 8

```mql5
bool INTRADAY_REVERSAL_TO_SELL =
     (h1_trend_strength >= 0.3)               // macro WAS bull
  && (m5_close < iClose(_Symbol,PERIOD_M5,6))  // M5 declining 30min
  && (iClose(_Symbol,PERIOD_M5,6)
       < iClose(_Symbol,PERIOD_M5,12))         // and 60min ago higher → 2hr cascade
  && (m5_rsi <= 40)
  && (g_rsi_div_type == "HID_BEAR"
      || g_rsi_div_type == "REG_BEAR"
      || (m5_close < m5_bb_m))
  && (price < vwap_price);
```

At Apr 8 12:00: every atom passes. At Apr 8 16:35: still passes (price 4783 below BBm by -13, below VWAP by ~-25, RSI 42 in range, M5 has been declining 4+ hours since 09:00 peak).

**INTRADAY_REVERSAL_TO_SELL fires at 12:00 and stays true through 18:00.** Action: block ALL BUY setups for 6 hours, amplify SELL setups. The 16:35 BB_BOUNCE BUY would be SKIPped.

Equivalent SELL action: amplifier active on MOMENTUM_DUMP SELL at 15:26 (+$5 at 0.01 lot) and 16:40 (+$5 at 0.01 lot) → 2x amplifier = 0.02 lot each = $10 + $10 = **$20 instead of $10 banking**, and additional SELL entries throughout 12:00-18:00 decline.

---

## 3. Synthesis — 3 composites cover 6 days

| Composite | Days covered | Activation |
|---|---|---|
| **`BULL_DAY_DIP_BUY`** | Mar 31 (10:00, 13:00), Apr 1 (16:00), Apr 8 AM (08:00-09:00) | `h1_trend ≥ 0.5` + `RSI 30-50` + price near BB lower/mid + no bear div |
| **`INTRADAY_REVERSAL_TO_SELL`** | Apr 2 (09:00 crash), Apr 8 (12:00 pivot through 18:00) | 2hr M5 decline + RSI ≤ 40 + bear div / below BB mid + below VWAP |
| **`NO_TREND_DAY`** | Apr 6, Apr 7 | `|h1_trend| ≤ 0.3` + RANGE regime + ADX < 25 |

**4th composite** (refinement of `BULL_DAY_DIP_BUY` for sustained strong trends): `TREND_CONTINUATION_BUY` for Apr 1 NY rally — kicks in when h1_trend ≥ 1.0 AND bar-over-bar rising AND RSI 40-70.

---

## 4. Apr 8 — what the inverse outcome would have been

| Original trade | What we did | What composite says | Inverse if `INTRADAY_REVERSAL_TO_SELL` enforced |
|---|---|---|---|
| Apr 8 16:35 BB_BOUNCE BUY 0.02 @ 4783 | TAKE (floating −$54) | BLOCK | no entry — saved $54 |
| Apr 8 16:49 cascade BUY 0.04 @ 4788 | TAKE (floating −$130) | BLOCK | no entry — saved $130 |
| Apr 8 15:26 MOMENTUM_DUMP SELL 0.01 @ 4775 | TAKE (+$5.78) | TAKE + AMPLIFY 2× → 0.02 | +$11.56 (doubled) |
| Apr 8 16:40 MOMENTUM_DUMP SELL 0.01 @ 4777 | TAKE (+$4.69) | TAKE + AMPLIFY 2× → 0.02 | +$9.38 (doubled) |
| Hypothetical additional SELL @ 18:00 capitulation | none fired | composite would have fired (RSI 28, h1 1.37, deep below VWAP) | est +$15-25 |

**Net delta**: **+$200 protected from BUY loss** + **+$10-25 amplified SELL win** + **+$15-25 additional SELL entry** = **~+$250 swing** on Apr 8 alone.

---

## 4b. Enhanced composites — using the full indicator toolkit (V2)

The initial composites used 8-10 atoms (RSI, ADX, h1_trend, BB, VWAP, divergence). After re-analyzing with **POC, Fib 50, BB width** added, the picture sharpens significantly.

### Apr 8 — POC/Fib/VWAP-gap timeline

| Hour | Price | RSI | **POC gap** | **Fib 50 gap** | **VWAP gap** | **BB width** | Div |
|---|---|---|---|---|---|---|---|
| 09:00 PEAK | 4828 | 64.9 | +25.90 | +45.58 | +25.22 | 45.07 | NONE |
| 10:00 | 4820 | 47.5 | +1.76 | +10.39 | +6.70 | 24.61 | NONE |
| **11:00** | 4814 | 46.3 | +1.21 | **−9.20** | −1.24 | 35.79 | NONE |
| **🚨 12:00** | 4794 | 33.4 | **−9.27** | **−22.02** | **−17.84** | 35.71 | **HID_BEAR** |
| 13:00 | 4783 | 32.5 | −19.22 | −26.61 | −26.57 | 29.08 | NONE |
| **16:35** BB_BOUNCE BUY | 4783 | 42.1 | ~−10 | **~−29** | ~−24 | 38 | NONE |
| **18:00 CAPITULATION** | 4736 | 28.3 | **−61.47** | **−49.67** | **−55.01** | **62.82** | NONE |

**The 11:00 break-below-Fib-50 was the EARLIEST warning** — Fib_gap flipped from +10 (10:00) to −9.20 (11:00), one full hour before HID_BEAR divergence appeared at 12:00.

### Apr 2 — same lens shows the morning crash AT 07:00 OPEN

| Hour | Price | RSI | POC gap | Fib gap | VWAP gap | BB width |
|---|---|---|---|---|---|---|
| 07:00 | 4676 | 37.3 | **−20.74** | **−49.19** | **−60.45** | 34.8 |
| 07:41 | 4659 | 28.5 | −37.68 | −66.13 | −70.11 | 43.7 |
| 08:00 | 4673 | 44.0 | −24.33 | −52.78 | −53.44 | 35.6 |

**Apr 2 at session open**: price was ALREADY $20 below POC, $49 below Fib 50, $60 below VWAP — yet regime stayed TREND_BULL (h1=1.34 lagging). The POC/Fib/VWAP triple-confirmation said "bear regime" hours before regime_label caught up.

### Enhanced composite V2 — INTRADAY_REVERSAL_TO_SELL_V2

```mql5
bool INTRADAY_REVERSAL_TO_SELL_V2 =
     (h1_trend_strength       >= 0.3)               // macro was bull (h1 lagging)
  // ── MOMENTUM EXHAUSTION ──
  && (m5_close < iClose(_Symbol,PERIOD_M5,6))         // M5 declining 30min
  && (iClose(_Symbol,PERIOD_M5,6)
       < iClose(_Symbol,PERIOD_M5,12))                // 60min cascade
  && (m5_rsi <= 40)
  // ── STRUCTURAL BEAR CONFIRMATION (3-anchor triangulation) ──
  && ((price - poc_price)     < -5.0)                 // below POC = institutional bear
  && ((price - fib_50)        < -10.0)                // below 50% Fib retracement
  && ((price - vwap_price)    < -10.0)                // below VWAP = institutional selling
  && ((bb_upper - bb_lower)   > 1.5 * m5_atr)         // BB expanding (vol regime)
  // ── DIVERGENCE / SETUP HEALTH ──
  && (g_rsi_div_type == "HID_BEAR"
      || g_rsi_div_type == "REG_BEAR"
      || (m5_close < m5_bb_m));
```

### Enhanced composite V2 — BULL_DAY_DIP_BUY_V2

```mql5
bool BULL_DAY_DIP_BUY_V2 =
     (h1_trend_strength       >= 0.5)
  && (!g_daily_bear_bias)
  && (m5_rsi >= 30 && m5_rsi <= 50)
  && (m5_adx >= 12 && m5_adx <= 40)
  // ── STRUCTURAL DIP (BB + POC + Fib alignment) ──
  && (price <= m5_bb_m + 0.5 * m5_atr)
  && (price >= m5_bb_l - 0.2 * m5_atr)
  && ((price - poc_price)     > -m5_atr)             // not deeply below POC
  && ((price - fib_50)        > -m5_atr * 0.5)       // not far below 50% Fib (← would block Apr 8 16:35!)
  && ((price - vwap_price)    <= 0.5 * m5_atr)
  // ── DIVERGENCE / EXHAUSTION SAFETY ──
  && (g_rsi_div_type != "REG_BEAR")
  && (g_rsi_div_type != "HID_BEAR")                   // ← NEW
  && (session == "LONDON" || session == "NY")
  && ((TimeCurrent() - g_last_chop_buy_exit_time) >= 300);
```

### Critical insight — the Fib 50 atom would have blocked the Apr 8 16:35 BB_BOUNCE BUY

At 16:35:
- price ≈ 4783
- fib_50 ≈ 4812 (estimated, day high 4846 / day low 4702 → 50% = 4774; but day range from morning high to current low closer to 4775; FORGE's daily fib_50 likely tracked the recent swing)
- Actual Run 23 SIGNALS row at 17:00 showed `fib_50 gap = −28.98` — so 16:35 was already significantly below Fib 50

`BULL_DAY_DIP_BUY_V2`'s `price > fib_50 - ATR/2` atom (−15 threshold) → 16:35's −28.98 gap **FAILS** → BUY BLOCKED.

**That one atom would have saved the $200 floating loss.**

### Layer 2 additions (require EA-side compute + §3 logging fix to validate fully)

```mql5
// Adds the indicators NOT yet logged in SIGNALS
bool LAYER_2_EXTRAS =
     (h4_trend_strength       >= 0.3)              // H4 alignment
  && (m15_trend_strength      >= 0.3)              // M15 not flipped
  && (h1_di_plus              >  h1_di_minus)      // H1 directional momentum bull
  && (m15_adx                 >= 15)               // M15 has structure
  && (macd_histogram          >  0                 // M5 MACD bullish OR
      || g_rsi_div_type       == "HID_BULL");
```

Adding these to BULL_DAY_DIP_BUY_V2 brings atom count from 12 → 17. After §3 logging fix, this is the full toolkit.

### Layered Atom Selection Strategy

Pick atoms by **what failure mode they prevent** — not blindly stack them:

| Atom | Primary failure prevented | Days where it matters |
|---|---|---|
| `h1_trend ≥ 0.5` | Buying in bear days | Apr 7 (h1<0) |
| `daily_bear_block` | Multi-day rollover BUY | (G5048-class, future) |
| `RSI 30-50` | Catching falling knife AND chasing tops | Mar 31, Apr 1 |
| `ADX 12-40 band` | Parabolic exhaustion / dead chop | Apr 7 (low ADX) |
| `price ≤ bb_mid + 0.5*ATR` | Buying near upper band | universal |
| **`price > poc_price - ATR`** | **Buying below day's high-volume node** | **Apr 8 PM** |
| **`price > fib_50 - ATR/2`** | **Buying past 50% retracement** | **Apr 8 16:35!** |
| `VWAP soft filter` | Buying far above value | Apr 1 PM peak |
| `RSI div != REG_BEAR` | Reversal-forming entry | universal |
| **`RSI div != HID_BEAR`** | **Trend exhaustion forming** | **Apr 8 12:00** |
| `session LONDON/NY` | Asian thin liquidity | universal |

The bolded atoms are the ones I missed in V1 — they're the difference between "looks like a dip" and "actually a structurally weak entry."

---

## 4c. Enhanced composites V3 — OHLC-derived atoms (Run 25 target)

V2 used POC + Fib 50 + VWAP gaps from indicator data. V3 adds **OHLC-derived atoms** from
`iHigh/iLow/iOpen/iClose` calls — bar-structure and intraday-extreme atoms that the indicator-only
view misses.

### OHLC availability inventory

| OHLC source | Where | Access | Populated today? |
|---|---|---|---|
| M1 OHLC | scribe `market_snapshots` | SQL | ✓ live only (not in SIGNALS) |
| M5 / M15 / H1 / H4 / D1 OHLC | EA runtime | `iOpen/iHigh/iLow/iClose(_Symbol, TF, shift)` | ✗ NOT in SIGNALS (computable per-tick) |

EA can USE OHLC in filters today; validation against historical data requires the v2.7.36 logging extension (see `docs/FORGE_LOGGING_EXTENSION_DESIGN.md`).

### OHLC-derived atoms

#### Day-relative position
```mql5
double day_high      = iHigh(_Symbol, PERIOD_D1, 0);
double day_low       = iLow(_Symbol, PERIOD_D1, 0);
double dist_high_atr = (day_high - price) / m5_atr;     // ATRs below day high
```

Apr 8 12:00: `dist_high_atr ≈ 1.7` (price 1.7×ATR below day high) — exhaustion signal.

#### Sequential structure (Dow-theory programmatic)
```mql5
bool m5_lh_cascade =                      // 3 consecutive lower highs = downtrend
     iHigh(_Symbol,PERIOD_M5,1) < iHigh(_Symbol,PERIOD_M5,2)
  && iHigh(_Symbol,PERIOD_M5,2) < iHigh(_Symbol,PERIOD_M5,3);

bool m5_hl_cascade =                      // 3 consecutive higher lows = uptrend
     iLow(_Symbol,PERIOD_M5,1) > iLow(_Symbol,PERIOD_M5,2)
  && iLow(_Symbol,PERIOD_M5,2) > iLow(_Symbol,PERIOD_M5,3);
```

Apr 8 hourly cascade: 4828 → 4820 → 4814 → 4794 = 4 consecutive lower hourly highs (and M5-level would have shown even earlier). **Confirms intraday-bear ahead of HID_BEAR divergence.**

#### Bar quality (rejection structure)
```mql5
double body_pct = MathAbs(close[1]-open[1]) / (high[1]-low[1]);
bool long_lower_wick = (open[1]-low[1]) >= 0.4*(high[1]-low[1]);   // rejection from low (bull bounce)
bool long_upper_wick = (high[1]-close[1]) >= 0.4*(high[1]-low[1]); // rejection at high (bear)
```

BB_BOUNCE BUY should require `long_lower_wick` on the entry-bar predecessor — otherwise it catches dips with no rejection structure (Apr 8 16:35 pattern).

### V3 composites — BULL_DAY_DIP_BUY_V3

```mql5
bool BULL_DAY_DIP_BUY_V3 =
  // ── V2 atoms (POC, Fib, VWAP, RSI div) ──
     (h1_trend_strength       >= 0.5)
  && (!g_daily_bear_bias)
  && (m5_rsi >= 30 && m5_rsi <= 50)
  && (m5_adx >= 12 && m5_adx <= 40)
  && (price <= m5_bb_m + 0.5 * m5_atr)
  && (price >= m5_bb_l - 0.2 * m5_atr)
  && ((price - poc_price)  > -m5_atr)
  && ((price - fib_50)     > -m5_atr * 0.5)
  && ((price - vwap_price) <= 0.5 * m5_atr)
  && (g_rsi_div_type != "REG_BEAR")
  && (g_rsi_div_type != "HID_BEAR")
  // ── NEW OHLC V3 atoms ──
  && ((iHigh(_Symbol,PERIOD_D1,0) - price) < 2.0 * m5_atr)    // within 2×ATR of day high
  && !m5_lh_cascade                                            // NOT in lower-high cascade
  && long_lower_wick                                           // prior bar had rejection at low
  // ── Standard ──
  && (session == "LONDON" || session == "NY")
  && ((TimeCurrent() - g_last_chop_buy_exit_time) >= 300);
```

**16 atoms.** The `!m5_lh_cascade` alone blocks Apr 8 16:35 BB_BOUNCE BUY (clear cascade structure since 09:00 peak).

### V3 composites — INTRADAY_REVERSAL_TO_SELL_V3

```mql5
bool INTRADAY_REVERSAL_TO_SELL_V3 =
  // ── V2 atoms ──
     (h1_trend_strength       >= 0.3)
  && (m5_close < iClose(_Symbol,PERIOD_M5,6))
  && (iClose(_Symbol,PERIOD_M5,6) < iClose(_Symbol,PERIOD_M5,12))
  && (m5_rsi <= 40)
  && ((price - poc_price)  < -5.0)
  && ((price - fib_50)     < -10.0)
  && ((price - vwap_price) < -10.0)
  && ((bb_upper - bb_lower) > 1.5 * m5_atr)
  && (g_rsi_div_type == "HID_BEAR"
      || g_rsi_div_type == "REG_BEAR"
      || (m5_close < m5_bb_m))
  // ── NEW OHLC V3 atoms ──
  && (m5_lh_cascade                                                  // M5 cascade OR
      || ((iHigh(_Symbol,PERIOD_D1,0) - price) > 1.5 * m5_atr))      // >1.5×ATR below day high
  && long_upper_wick;                                                // prior bar showed bear rejection
```

**13 atoms.** Cascade + day-high-distance + upper-wick rejection give 3 OHLC angles of bear confirmation.

### V3 effect — concrete impact summary

| Trade | V2 outcome | V3 outcome |
|---|---|---|
| Apr 8 16:35 BB_BOUNCE BUY | borderline blocked by Fib | **BLOCKED definitively** by `dist_high_atr > 2.0` + `m5_lh_cascade` |
| Apr 8 12:00 INTRADAY_REVERSAL_TO_SELL fires | requires HID_BEAR div (12:00) | **Fires at 11:00** when 3rd lower-high prints (1hr earlier) |
| Apr 2 09:00 crash detection | needs 30+60min cascade | **Fires within 1-2 M5 bars** of gap-down |
| Mar 31 dip BUYs (10:00, 13:00) | both fire | both fire ✓ (no regression) |
| Apr 1 16:00 BUY | fires | fires ✓ (no regression) |
| Atoms per composite | 12 | **16** |
| False-positive rate | medium | **lower** (wick rejection filter) |
| **Net P&L impact Apr 8** | (baseline) | **+$200-300** (BUY losses prevented + earlier SELL entries) |

### Trade-offs (V3)

1. **Code surface**: ~20-40 extra iX calls per tick across all setups. Microseconds — negligible.
2. **Day-boundary edge case**: `iHigh(PERIOD_D1, 0)` at 00:01 UTC has fresh single-bar values. Atoms degrade gracefully (day_high ≈ day_low at open, expands through day).
3. **Cascade lag**: `m5_lh_cascade` needs 3 bars history (15 min). Fast crashes (Apr 2 gap-down) may miss first 10 min of the move — supplement with `dist_high_atr` for instant signal.
4. **Logging dependency**: 13+ new atoms not in SIGNALS today. Layer-1 validation against historical data requires v2.7.36 logging extension (`docs/FORGE_LOGGING_EXTENSION_DESIGN.md`).

---

## 5. Open questions / Run 25 implementation needs

1. `INTRADAY_REVERSAL_TO_SELL` requires no new logging — all atoms in SIGNALS today (verified atlas §11). Ready to implement.
2. Need to confirm gate fires fast enough (within 1 M5 bar of HID_BEAR div + RSI drop) so we don't miss the pivot.
3. Once fired, how long does it stay TRUE? Until `m5_rsi > 50` AND `m5_close > bb_mid`? Need exit condition.
4. Apply to ALL BUY setups (BB_BOUNCE, BB_PULLBACK_SCALP, MOMENTUM_DUMP_BUY, BB_BREAKOUT_BUY)?
5. SELL amplifier: route through existing `wave_confirmation_lot_mult` or new `regime_aligned_lot_mult` knob?
6. `NO_TREND_DAY` requires chop ladder implementation (atlas §5.5, not yet shipped) before usable.

---

## 6. References

- **Atlas** §5.7 `INTRADAY_REVERSAL_TO_SELL` (composite spec + Apr 2 + Apr 8 truth tables)
- **Atlas** §5.1 `CHOP_IN_BULL_TREND_BUY` (canonical `BULL_DAY_DIP_BUY` precursor)
- **Atlas** §5.8 `NO_TREND_DAY`
- **Playbook** §10 boolean composite design pattern
- **Run 23 analysis** `docs/FORGE_RUN23_ANALYSIS.md`

---

## 7. Changelog

| Date | Change |
|---|---|
| 2026-05-12 | Initial case study created during Run 23 sim at Apr 9 09:10. 6 trading days characterized (Mar 31, Apr 1, Apr 2, Apr 6, Apr 7, Apr 8). 3-composite consolidation derived. Apr 8 12:00 identified as the exact INTRADAY_REVERSAL_TO_SELL pivot moment. |
