# FORGE Momentum TP/SL Research — OsMA Q0/Q2 Confirmed Breakout Entries

**Context:** FORGE EA on XAUUSD M5, BB breakout mode, OsMA(3,10,16) quadrant gate.
Q0 = histogram positive AND rising (fast bull). Q2 = histogram negative AND falling (fast bear).
Current config: `sl_atr_mult: 2.0`, TP ladder at 1.0 / 1.5 / 2.5 / 4.0× ATR, partial closes 40/30/20/10%, move-BE on TP1.

---

## Section 1: Entry Price — Limit vs Market During Fast Momentum

**Research finding: market orders are the dominant recommendation for confirmed Q0/Q2 momentum.**

When OsMA confirms Q0 or Q2 — meaning the histogram is already directionally extreme and accelerating — price is already in motion. Limit orders below/above the breakout zone risk non-fill entirely as the fast move extends without retrace. Practitioner consensus across MQL5 forums and scalping guides (2023–2025) is that market orders are mandatory when momentum confirmation is in hand: waiting for a pullback entry invalidates the very OsMA acceleration that justified the trade.

The partial exception is the **retest-limit** approach, which FORGE already implements (`breakout_use_retest: 1`, `sell_limit_atr_mult: 0.4`). A shallow limit at 0.3–0.5× ATR off the breakout level is reasonable as a fill-quality improvement only if the Q0/Q2 signal is still valid on bar close — the gate must re-confirm. If the histogram has already rotated toward Q1/Q3 by the time the retest limit fills, the order should be cancelled.

**Summary:** Use market orders for immediate Q0/Q2 entries. Retain the retest-limit feature but enforce re-confirmation of quadrant state at fill time to avoid entering a decaying momentum signal.

Sources: [MACD Indicator for Scalping — OpoFinance](https://blog.opofinance.com/en/macd-indicator-for-scalping/); [Breakout vs Pullback — HeyGoTrade](https://www.heygotrade.com/en/blog/choosing-pullback-vs-breakout-trading/); [Buy Stop Momentum Breakouts — LuxAlgo](https://www.luxalgo.com/blog/buy-stop-orders-momentum-breakouts-made-easy/)

---

## Section 2: SL Sizing for Momentum Scalps

**Research finding: 1.5–2.0× ATR(14) is the practitioner sweet spot for M5 intraday scalping; go no tighter than 1.5× on confirmed momentum.**

Multiple sources converge on ATR-based dynamic stops as superior to fixed-pip stops for XAUUSD, given gold's session-varying volatility (typical M5 ATR(14) ≈ 1.5–4.0 points depending on session and news proximity).

Key data points:
- Day traders on 5-minute charts: **1.5–2.0× ATR** recommended; swing traders use 2.0–3.0×. ([QuantVPS ATR Guide](https://www.quantvps.com/blog/using-average-true-range-for-stop-loss-placement))
- ATR multiplier of **1×** was found to be a significant performance outlier — too tight, prevents capturing momentum extension. Multiples of 1.5 and 2× outperformed across an 87-strategy stop-loss backtest study. ([Paper to Profit Substack](https://papertoprofit.substack.com/p/i-tested-87-different-stop-loss-strategies))
- XMSignal gold M5 practitioners use **2× ATR as the standard stop**, occasionally 2.5× near high-impact events. ([Gold Scalping MT5 — XMSignal](https://xmsignal.com/en/blog/gold-scalping-strategy-mt5/))
- During confirmed high-ADX (>40) momentum moves, FORGE's `high_vol_breakout_sl_boost: 1.25` correctly widens SL — research supports this: wider stops in strong trends reduce premature stop-outs and improve net P&L. ([MQL5 Blogs — Indicator-Driven SL/TP](https://www.mql5.com/en/blogs/post/763186))

**For Q0/Q2 entries specifically:** The momentum confirmation provides directional conviction, but XAUUSD spikes 10–30 points per second during fast moves. SL tighter than 1.5× ATR will be clipped by normal volatility before the trade can develop. The current config (`sl_atr_mult: 2.0`, `min_sl_atr_mult: 1.5`) is well-calibrated. Do not go below 1.5× for any breakout entry; keep 2.0× as the base.

---

## Section 3: TP Structure — Fixed ATR, Partial Close, Trailing, RR Ratios

**Research finding: layered partial-close exits with ATR-scaled targets are the highest-performing structure for momentum scalps; minimum RR of 1:1.5.**

The MQL5 community and practitioner literature consistently favor a **multi-target partial close** structure over a single fixed TP for momentum trades:

1. **TP1 at 1.0–1.5× ATR (40–50% close):** Lock realized P&L quickly. Moving stop to breakeven on TP1 hit (FORGE already does this) is supported by research as the best risk-free mechanic for momentum scalps. ([ATR Breakout Strategy — FMZQuant Medium](https://medium.com/@FMZQuant/advanced-momentum-breakout-trading-strategy-with-atr-based-take-profit-and-stop-loss-mechanism-cc8010c8d4c6))
2. **TP2 at 1.5–2.0× ATR (25–30% close):** Captures the extended momentum leg that Q0/Q2 signals tend to produce.
3. **TP3 trailing (remainder):** ATR trailing stop at 1.5–2× ATR distance allows runners to ride the full momentum extension without capping upside. The BB mid-band reversion (used in bounce mode) is a valid TP3 anchor for breakout trades that stall.

**RR ratios for momentum scalps:** Practitioner consensus for XAUUSD M5 is **minimum 1:1.5** (current `min_rr: 1.5` is aligned). The XMSignal XAUUSD scalping guide recommends 1:1.5 minimum with 1:2–1:3 as the target for sessions with strong momentum. ([Gold Scalping MT5 — XMSignal](https://xmsignal.com/en/blog/gold-scalping-strategy-mt5/); [XAUUSD Strategy Guide — NYC Servers](https://newyorkcityservers.com/blog/gold-xauusd-trading-strategy/))

**For BB breakout mode specifically:** The Bollinger Band structure provides natural TP anchors. A partial close at BB mid (FORGE `tp1_target: bb_mid` in bounce mode) is validated by research: "take partial profits when price reaches the middle band, move stop to entry." ([MQL5 Blogs — Indicator-Driven SL/TP](https://www.mql5.com/en/blogs/post/763186)) For breakout mode, continuing to use ATR multiples (1.0/1.5/2.5/4.0) with the trailing runner is appropriate.

---

## Section 4: Slippage Impact on XAUUSD M5

**Research finding: slippage is the single largest edge-killer for gold scalping EAs; 5–15 pips average slippage can flip a profitable system to a loser.**

Quantified data from FXVPS infrastructure testing (2024–2025):
- **Shared VPS:** 2–5× more slippage per trade vs dedicated-core VPS in a financial datacenter
- **Concrete impact:** A breakout scalping strategy netting +$840/month on clean execution turned to -$60/month with 15 pips average slippage — the identical system, flipped by infrastructure alone. ([Forex VPS Gold Trading — FXVPS](https://fxvps.biz/blog/forex-vps-gold-trading-xauusd/))
- **Per-trade math:** At 50-point SL risk, 10 points of slippage eats 20% of risk budget before the trade can move. Over 100 trades, 5 points average slippage = 500 points / ~$5,000 per standard lot in hidden costs. ([Slippage VPS Solution — NYC Servers](https://newyorkcityservers.com/blog/forex-slippage-vps-solution/))
- **During fast Q0/Q2 moves:** Slippage is highest precisely when OsMA confirms acceleration — price is gapping fast. Market orders during these events on raw-spread ECN accounts typically see 3–10 points slippage on XAUUSD during London/NY overlap, and 10–30+ during news. ([XS Gold Scalping Strategy](https://www.xs.com/en/blog/gold-scalping-trading-strategy/))
- **Spread baseline:** ECN/raw accounts show 1.0–2.5 pip spreads during active sessions; this rises sharply in Asian session and around news events. FORGE's `max_spread_points: 30` guard is correctly calibrated.

**Practical implication for FORGE:** Slippage of 5–10 points on entry and 3–5 on exit is realistic on a quality ECN VPS. This argues for TP1 targets no smaller than 1.0× ATR (roughly 15–25 points on typical XAUUSD M5 sessions) so that slippage does not consume more than 30% of the first target. TP1 at 1.0× ATR with the current SL at 2.0× ATR gives a 1:0.5 realized RR on the first leg — acceptable when 40% is closed and BE is moved, securing the remaining position.

---

## Section 5: MQL5/MT5 Community Consensus

Based on MQL5 articles, forum threads, and marketplace EA patterns reviewed for 2023–2025:

1. **ATR-based dynamic stops are standard practice** for gold EAs. Fixed-pip stops are considered naive in the MQL5 community given XAUUSD's session volatility swings. ([MQL5 ATR SL Forum](https://www.mql5.com/en/forum/327164); [ATR Stop Loss Utility](https://www.mql5.com/en/market/product/105561))

2. **Partial close + breakeven move on TP1** is the near-universal pattern in well-reviewed MQL5 gold scalping EAs. The BB Scalping EA and similar products on the marketplace all implement this structure. ([BB Scalping MT5](https://www.mql5.com/en/market/product/150171))

3. **MACD/OsMA confirmation as a momentum gate** (not standalone signal) is the consensus approach — it filters false breakouts, improving win rate from the typical 20–40% of raw breakout systems to 50–70% when confirmation is layered in. ([MACD-RSI Trade Layering — MQL5 Articles](https://www.mql5.com/en/articles/17741))

4. **Retest/limit entry as an option** is available in several MQL5 BB breakout EAs, but it is always secondary to market entry — treated as a "fill quality improvement" only when momentum has not yet resolved. The consensus is to abort a pending limit if momentum state has changed before fill.

5. **VPS + ECN mandatory for gold scalping EAs.** Sub-5ms VPS latency is the community standard for any EA targeting gold with SL/TP in the 20–50 point range. ([Forex VPS for Gold — FXVPS](https://fxvps.biz/blog/forex-vps-gold-trading-xauusd/))

---

## Section 6: Recommended Config for FORGE Based on Findings

The following reflects research-backed adjustments and validations against the current `scalper_config.json` (v2.7.8):

### Confirmed as well-calibrated (no change needed)
| Parameter | Current Value | Research Verdict |
|---|---|---|
| `bb_breakout.sl_atr_mult` | 2.0 | Optimal for M5 gold; do not go below 1.5 |
| `safety.min_sl_atr_mult` | 1.5 | Correct floor; 1× ATR confirmed as outlier |
| `safety.min_rr` | 1.5 | Aligned with XAUUSD M5 practitioner consensus |
| `bb_breakout.move_be_on_tp1` | true | Standard best practice; confirmed by multiple sources |
| `bb_breakout.tp1_close_pct` | 40% | Optimal first-target lock size for slippage-adjusted edge |
| `safety.max_spread_points` | 30 | Correctly filters wide-spread entries |
| `lot_sizing.native_scalper_use_limit_entry` | 0 | Correct default; market orders dominate for Q0/Q2 |

### Recommended adjustments / experiments

**1. TP1 minimum floor — enforce ≥ 1.0× ATR**
Research confirms that sub-1× ATR TP1 targets are eroded by slippage before the position can realize gain. Add a runtime guard that if TP1 distance < 1.0× ATR, widen TP1 to 1.0× ATR rather than skip the trade.

**2. Retest-limit quadrant re-confirm**
The `breakout_use_retest: 1` feature should re-verify OsMA quadrant state at fill time. If the histogram has rotated from Q0→Q1 or Q2→Q3 between signal bar and limit fill bar, cancel the pending order. This prevents entering a decaying momentum signal at a stale limit price.

**3. Trailing runner on TP3/TP4 legs**
Consider replacing the fixed TP3/TP4 ATR multiples (2.5× / 4.0×) for the runner legs with an ATR trailing stop at 2× ATR distance. Research (Momentum Oscillator Trailing Stop study, FMZQuant) shows trailing stops outperform fixed multiples on the runner leg in strong momentum moves by capturing extended runs without leaving money on the table at arbitrary fixed levels.

**4. Session-aware SL boost for peak slippage windows**
During the first 15 minutes of London open and NY open (highest slippage risk), temporarily boost `sl_atr_mult` by 1.1× to absorb entry slippage within the stop. Implement as a time-of-day multiplier in the safety block.

**5. Position sizing: 0.5% risk cap per trade (validation)**
Research uniformly recommends 0.5% account risk per scalp rather than 1%, given typical session frequency of 3–5 M5 scalp entries. At 1% per trade, a 5-loss streak costs 5% equity; at 0.5% it is 2.5% — recoverable in 2–3 winning sessions. Validate that `lot_sizing` AUTO mode targets 0.5% risk on standard account sizes.

---

*Research compiled: 2026-05-09. Primary sources: MQL5 Articles, MQL5 Forums, FXVPS Infrastructure Blog, FMZQuant Medium (ATR Breakout Strategy), XMSignal Gold Scalping MT5, NYC Servers XAUUSD Guide, LuxAlgo ATR SL Blog, PaperToProfit 87-Strategy Backtest, QuantVPS ATR Guide.*
