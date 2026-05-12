# Research Notes — Regime/Trend Terminology (canonical industry usage)

**Topic**: Whether to rename FORGE's proposed `RegimeState` fields (`macro_label`,
`intraday_label`, `daily_slope_atr`, `high_vol`, `intraday_vs_macro_diverged`) to
match well-established industry vocabulary, or keep our descriptive names.

**Retrieval date**: 2026-05-11

---

## §1. Question / Goal

The FORGE Regime Taxonomy (`FORGE_REGIME_TAXONOMY.md` §7.1, §9) proposes a
`RegimeState` struct that collapses ~20 globals into a single source of truth.
Five field names need a sanity-check against canonical literature before we
freeze the public API in v2.7.37 Phase 2:

| Proposed name | Captures |
|---|---|
| `macro_label` | H1+H4 integrated regime (TREND_BULL / TREND_BEAR / RANGE / VOLATILE) |
| `intraday_label` | M5+M15 regime (NEW — closes Apr 8 PM gap) |
| `daily_slope_atr` | D1 SMA slope, ATR-normalized |
| `high_vol` | Volatility-trend hybrid bool |
| `intraday_vs_macro_diverged` | Intraday says one direction, macro says another |

Goal: find ≥3 authoritative sources per concept, decide adopt-rename or keep, and
log the decision in §11 of the taxonomy.

---

## §2. Methodology

### Search queries (verbatim)

1. `"Dow Theory primary secondary minor trend definition Charles Dow"`
2. `multi-timeframe analysis HTF MTF LTF trading higher lower timeframe`
3. `Elliott Wave degrees of trend Grand Supercycle Primary Intermediate Minor`
4. `Wyckoff method four phases accumulation markup distribution markdown`
5. `trending market vs ranging market definition technical analysis John Murphy`
6. `Markov regime switching model bull bear ranging market academic paper`
7. `volatility regime low high volatility clustering GARCH Bollinger squeeze expansion`
8. `"low volatility regime" "high volatility regime" definition trading academic`
9. `200 day moving average trend bias long-term trend follow Stan Weinstein stage analysis`
10. `pullback vs counter-trend correction Elliott Wave ABC corrective wave definition`
11. `"pullback" definition trading temporary retracement within trend Investopedia`
12. `Bollinger Bands squeeze breakout John Bollinger volatility contraction expansion`
13. `"counter-trend" trading vs "pullback" vs "retracement" terminology difference`

### Source-quality filter

- Tier A (peer-reviewed / canonical references): Wikipedia (Dow Theory, Elliott
  Wave, volatility clustering), Mandelbrot quote on volatility clustering, MDPI
  Hidden Markov Models in finance.
- Tier B (established broker/exchange education): StockCharts ChartSchool (John
  Murphy, Bollinger Band squeeze), Stage Analysis dot net, Babypips Forexpedia,
  Wyckoff Analytics.
- Tier C (community/blog): LuxAlgo, Tradeciety, Markets4you — used only for
  cross-validation, not single-source claims.
- Rejected: SEO content farms, affiliate-link aggregator pages, generic "best
  settings" listicles.

### Sources surveyed (retrieved 2026-05-11)

- Wikipedia "Dow theory" — https://en.wikipedia.org/wiki/Dow_theory
- Wikipedia "Volatility clustering" — https://en.wikipedia.org/wiki/Volatility_clustering
- Wyckoff Analytics — https://www.wyckoffanalytics.com/wyckoff-method/
- StockCharts ChartSchool, John Murphy's 10 Laws —
  https://chartschool.stockcharts.com/table-of-contents/overview/john-murphys-10-laws-of-technical-trading
- StockCharts ChartSchool, Bollinger Band Squeeze —
  https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/bollinger-band-squeeze
- Stage Analysis (Stan Weinstein) — https://www.stageanalysis.net/
- LuxAlgo "Market Regimes Explained" —
  https://www.luxalgo.com/blog/market-regimes-explained-build-winning-trading-strategies/
- Tradeciety MTF analysis — https://tradeciety.com/how-to-perform-a-multiple-time-frame-analysis
- Markets4you MTF guide —
  https://www.markets4you.com/en/blog/product-features/mastering-multiple-time-frame-analysis-in-forex-from-trend-to-entry/
- Elliott Wave Insights, degree labels —
  https://elliottwaveinsight.co.uk/elliott-wave-degrees-labeling/
- MDPI "Regime-Switching Factor Investing with HMMs" —
  https://www.mdpi.com/1911-8074/13/12/311 (search-result snippet; full fetch
  403'd, snippet treated as Medium confidence corroboration)
- Babypips Forexpedia "Pullback" — https://www.babypips.com/forexpedia/pullback
- Gate Wiki — pullback vs retracement vs reversal —
  https://www.gate.com/crypto-wiki/article/pullback-vs-retracement-vs-reversal-...

---

## §3. Findings (cited)

### §3.1 Concept 1 — Multi-timeframe trend hierarchy

**Claim**: Trading literature has THREE established taxonomies for multi-scale
trend, each from a different school: Dow Theory (primary/secondary/minor),
modern MTF (HTF/MTF/LTF), and Elliott Wave (degree hierarchy). All three agree
on a three-level structure but use different labels.

**Source A — Dow Theory (Wikipedia)** — https://en.wikipedia.org/wiki/Dow_theory
- Direct quote: *"The 'main movement', primary movement or major trend may last
  from less than a year to several years. It can be bullish or bearish."*
- Direct quote: *"The 'medium swing', secondary reaction or intermediate
  reaction may last from ten days to three months and generally retraces from
  33% to 66% of the primary price change."*
- Direct quote: *"The 'short swing' or minor movement varies with opinion from
  hours to a month or more."*

**Source B — Modern MTF (Tradeciety / Markets4you)** —
https://tradeciety.com/how-to-perform-a-multiple-time-frame-analysis and
https://www.markets4you.com/en/blog/product-features/mastering-multiple-time-frame-analysis-in-forex-from-trend-to-entry/
- Direct quote: *"The higher-time-frame (HTF) defines bias and key levels; the
  mid-time-frame (MTF) shapes the play; the low-time-frame (LTF) times the
  entry — think: map → route → turn signal."*
- Direct quote: *"Swing traders use: Daily (HTF) for trend, H4 (MTF) for
  structure, H1 or M30 (LTF) for entry. Scalpers may use: H1 for trend, M15
  for pullback, M1 or M5 for entry timing."*

**Source C — John Murphy (StockCharts ChartSchool)** —
https://chartschool.stockcharts.com/table-of-contents/overview/john-murphys-10-laws-of-technical-trading
- Direct quote: *"Market trends come in many sizes — long-term, intermediate-term
  and short-term."*
- Direct quote: *"Let the longer range chart determine the trend, and then use
  the shorter term chart for timing."*

**Source D — Elliott Wave degrees (Elliott Wave Insights)** —
https://elliottwaveinsight.co.uk/elliott-wave-degrees-labeling/ (cross-checked
against Wikipedia "Elliott wave principle")
- Hierarchy (largest → smallest): Grand Supercycle → Supercycle → Cycle →
  Primary → Intermediate → Minor → Minute → Minuette → Subminuette. Primary =
  "a few months to two years"; Intermediate = "weeks to months"; Minor = "weeks".

**FORGE application**: For a scalper on H1/M5/M1 charts, the Murphy/MTF
vocabulary maps best because Dow Theory's primary (year+) and Elliott's
Primary (months-years) are too long for our regime windows. The Murphy/MTF
"long-term / intermediate / short-term" or "HTF / MTF / LTF" terms are the
canonical fit. Note that **`macro`** is NOT a standard label in this
literature — it's a borrowed economics term. **`primary`** (Dow) or
**`higher_timeframe` / `htf`** (MTF) is the canonical option.

**Confidence**: High (4 sources, three independent schools agree on three-tier
hierarchy).

---

### §3.2 Concept 2 — Trending vs ranging market regime

**Claim**: The canonical labels are **trending (bull / bear)**, **ranging
(sideways / consolidation)**, and **volatile**. Academic regime-switching
literature uses 2 or 3 states (bull / bear, or bull / bear / neutral). FORGE's
existing `TREND_BULL` / `TREND_BEAR` / `RANGE` / `VOLATILE` already aligns.

**Source A — Wyckoff Analytics** — https://www.wyckoffanalytics.com/wyckoff-method/
- Direct quote: *"Phase E depicts the unfolding of the uptrend; the stock leaves
  the TR and demand is in full control."* (Markup phase)
- Direct quote: *"Phase E depicts the unfolding of the downtrend; the stock
  leaves the TR and supply is in control."* (Markdown phase)
- Wyckoff TR ("trading range") is the canonical Wyckoff term for a ranging
  market (= consolidation between support/resistance during accumulation /
  distribution).

**Source B — LuxAlgo "Market Regimes Explained"** —
https://www.luxalgo.com/blog/market-regimes-explained-build-winning-trading-strategies/
- Direct quote: *"Market regimes are the distinct 'states' or 'moods' of
  financial markets — like bullish trends, bearish declines, or volatile
  swings."*
- Direct quote: *"Trending markets are defined by clear directional
  movement. In a bull market, prices consistently climb... Conversely, bear
  markets see prices steadily drop, forming lower highs and lower lows."*
- Direct quote: *"Sideways markets occur when prices move back and forth
  between established support and resistance levels, without forming a clear
  trend."*

**Source C — Stan Weinstein Stage Analysis** — https://www.stageanalysis.net/
- Four stages: *"Stage 1 Base"* (accumulation / range), *"Stage 2 Advancing"*
  (uptrend / markup), *"Stage 3 Top/Distribution"* (range / topping), *"Stage 4
  Declining"* (downtrend / markdown). Two trending stages (2, 4) and two
  ranging stages (1, 3).

**Source D — MDPI "Regime-Switching Factor Investing with HMMs"** —
https://www.mdpi.com/1911-8074/13/12/311 (search snippet, fetch 403'd)
- Snippet: *"three hidden states: representing periods including bull, bear,
  and neutral market regimes."*

**FORGE application**: FORGE's existing `g_regime_label` values
(`TREND_BULL` / `TREND_BEAR` / `RANGE` / `VOLATILE`) match canonical labels
directly. **Keep `macro_label` enum values**. The field name itself ("label" is
generic; OK) doesn't need renaming.

**Confidence**: High (4 sources, three schools — Wyckoff, Weinstein, modern
regime classification — all agree on trending/ranging dichotomy).

---

### §3.3 Concept 3 — Volatility regime

**Claim**: "Volatility regime" is the established term, with "low" / "high" as
the canonical state labels. Comes from GARCH literature (Bollerslev 1986,
Mandelbrot volatility clustering) and Bollinger Bands (squeeze = low,
expansion = high).

**Source A — Wikipedia "Volatility clustering" (Mandelbrot)** —
https://en.wikipedia.org/wiki/Volatility_clustering
- Direct quote (Mandelbrot): *"large changes tend to be followed by large
  changes, of either sign, and small changes tend to be followed by small
  changes."*

**Source B — John Bollinger via StockCharts ChartSchool** —
https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/bollinger-band-squeeze
- Direct quote: *"A Bollinger Band Squeeze is a condition that occurs when
  the Bollinger Bands narrow due to decreased volatility."*
- Direct quote: *"periods of low volatility are often followed by periods of
  high volatility"* (attributed to Bollinger).

**Source C — LuxAlgo Market Regimes** —
https://www.luxalgo.com/blog/market-regimes-explained-build-winning-trading-strategies/
- Direct quote: *"High-Volatility Markets are characterized by sharp price
  swings, increased uncertainty, and significant movements."*
- Direct quote: *"Low-Volatility Markets feature more subdued price movements,
  narrower trading ranges, and a generally stable environment."*

**FORGE application**: `high_vol` is a recognizable shorthand and is fine as a
bool. The canonical pair would be `volatility_regime ∈ {LOW, NORMAL, HIGH}`,
but FORGE only needs the HIGH-vol guard, so a single bool `high_vol` is
acceptable. **No rename needed.** Optional: rename to `high_volatility_regime`
for symmetry with the rest of the struct, but `high_vol` reads fine.

**Confidence**: High (Mandelbrot + Bollinger + modern regime-trading literature
all use "volatility regime" with low/high states).

---

### §3.4 Concept 4 — Daily-slope / macro bias

**Claim**: The canonical term for "longer-timeframe trend direction used as a
directional filter" is **daily bias** or **daily trend direction**, often
operationalized via the 200-day moving average (Weinstein, Murphy). "Slope" is
descriptive but not a standard label; "macro bias" is informal.

**Source A — Stan Weinstein Stage Analysis** —
https://www.stageanalysis.net/ and TraderLion summary —
https://traderlion.com/trading-strategies/stage-analysis/
- *"Stan Weinstein originally used the 30-week moving average as his primary
  trend filter but has now switched to the 40-week moving average (200-day
  moving average)."*
- The 200-day MA is "the core tool used to divide an asset's price action into
  four distinct life cycle stages."

**Source B — John Murphy (StockCharts ChartSchool, 10 Laws)** —
https://chartschool.stockcharts.com/table-of-contents/overview/john-murphys-10-laws-of-technical-trading
- Direct quote: *"Begin a chart analysis with monthly and weekly charts spanning
  several years."*
- Direct quote: *"Let the longer range chart determine the trend, and then use
  the shorter term chart for timing."*
- Murphy explicitly calls this longer-range determination "the trend" — there
  is no special "bias" or "slope" term in Murphy's 10 Laws; the canonical
  phrase is **"long-term trend"** or **"the prevailing trend"**.

**Source C — Dow Theory (Wikipedia)** —
https://en.wikipedia.org/wiki/Dow_theory
- The longer-timeframe direction is canonically the **"primary trend"** —
  *"The 'main movement', primary movement or major trend may last from less
  than a year to several years."*

**FORGE application**: `daily_slope_atr` is descriptive of *what is computed*
(ATR-normalized slope of the D1 SMA), but the *concept* is **daily bias** or
**daily trend direction**. The numerical metric should keep the descriptive
name (`daily_slope_atr` is more precise than `daily_bias_value`), but the
derived bools `daily_bull_bias` / `daily_bear_bias` already align with the
canonical "bias" vocabulary. **Recommendation: keep `daily_slope_atr` as the
metric, keep `daily_bull_bias` / `daily_bear_bias` as derived bools.** These
together accurately encode the "daily bias" concept.

**Confidence**: High (Weinstein + Murphy + Dow all agree the long-timeframe
directional filter is called the "primary" or "long-term" trend; "bias" is the
modern shorthand and FORGE already uses it).

---

### §3.5 Concept 5 — Divergence / conflict between timeframes

**Claim**: The canonical industry term for "shorter-timeframe direction
conflicts with longer-timeframe direction" is **pullback** (when temporary) or
**counter-trend move** / **correction** (when more pronounced). "Divergence"
is reserved for indicator-vs-price divergence (RSI / MACD), not
trend-timeframe conflict.

**Source A — Babypips Forexpedia "Pullback"** —
https://www.babypips.com/forexpedia/pullback (cross-checked against Gate Wiki
and Markets4you content above)
- Pullback = *"a temporary reversal in the upward price trend of a stock or
  other investment"* / *"a temporary counter-move within a trend"*. Pullbacks
  *"typically last only a few consecutive sessions"*.

**Source B — Gate Wiki "Pullback vs Retracement vs Reversal"** —
https://www.gate.com/crypto-wiki/article/pullback-vs-retracement-vs-reversal-...
- Direct quote: *"pullbacks are temporary declines within uptrends,
  retracements are counter-trend price corrections, while counter-trend
  trading would more broadly refer to trading against the prevailing
  direction."*
- Direct quote: *"The most significant difference between pullbacks and
  reversals is that a pullback is temporary, while a reversal is a more
  permanent change in the direction of an overall trend."*

**Source C — Elliott Wave corrective waves (Babypips / Elliott Wave
Insights)** — https://www.babypips.com/learn/forex/corrective-waves and
https://elliottwave-forecast.com/elliott-wave-theory/
- Direct quote: *"ABC corrections are counter-trend movements with three waves:
  A, B, and C... The corrective phase aligns against the trend of one higher
  degree (a counter trend move)."*

**Source D — John Murphy** (StockCharts, 10 Laws) — *"Buy dips if the trend
is up. Sell rallies if the trend is down."* — implicitly defines a "dip" (=
pullback in uptrend) and "rally" (= bounce in downtrend) as canonical
counter-direction moves within a larger trend.

**FORGE application**: The proposed name `intraday_vs_macro_diverged` uses
"divergence" in its trend-conflict sense, but the canonical industry meaning
of **divergence** is indicator divergence (RSI / MACD vs price). Using
"diverged" here will *confuse* future readers who expect indicator divergence.

The canonical industry terms for "intraday-direction conflicts with
longer-timeframe direction" are:
- **Pullback** — short, temporary, expected to resume the higher-degree trend.
- **Counter-trend move** — broader, doesn't presuppose temporary nature.
- **Correction** — pronounced retracement, sometimes sustained (Elliott ABC).

The Apr 8 PM scenario was a sustained intraday decline against a TREND_BULL
macro — that's closer to a **correction** or **counter-trend move** than to a
pullback (a pullback would have been brief and resumed). The bool that detects
"intraday direction ≠ macro direction" is best named one of:

- `intraday_counter_macro` — direct restatement of canonical "counter-trend"
- `intraday_against_htf` — uses MTF vocabulary (HTF = higher timeframe)
- `htf_conflict` — terse, emphasizes the *conflict* concept

**Strong recommendation: rename `intraday_vs_macro_diverged` → `intraday_counter_macro`
(or `intraday_against_htf` if we adopt HTF naming for `macro_label`)** to
avoid collision with the established meaning of "divergence" in technical
analysis.

**Confidence**: High (4 sources, three schools — Babypips/MTF, Elliott Wave,
Murphy — converge on "counter-trend" / "pullback" / "correction" as the
canonical vocabulary; "divergence" is reserved for indicator divergence).

---

## §4. Synthesis — Recommendation table

| FORGE proposed name | Industry-canonical term(s) | Adopt rename? | Suggested final name | Rationale (1 sentence) |
|---|---|---|---|---|
| `macro_label` | **Primary trend** (Dow), **HTF trend** (MTF), **long-term trend** (Murphy) | **Optional rename** | `htf_label` *(or keep `macro_label`)* | "Macro" is borrowed from economics; "HTF" is the modern trading-canonical short form and reads consistent with `intraday` (MTF). Keeping `macro_label` is acceptable; renaming to `htf_label` aligns with industry MTF vocabulary. |
| `intraday_label` | **MTF trend** (modern), **intermediate-term trend** (Murphy), **secondary trend** (Dow) | **No** | `intraday_label` | "Intraday" is a clear, widely-understood scalper-relevant label; "MTF" is generic, "secondary" is Dow-era (different time horizon). Keep as-is. |
| `daily_slope_atr` | **Daily bias / primary trend direction** (Weinstein, Murphy) | **No** | `daily_slope_atr` | The field is a *metric* (signed, normalized scalar), not a *label*; the canonical concept (bias) is encoded in derived `daily_bull_bias` / `daily_bear_bias`. Descriptive name is more precise than `daily_bias_value`. |
| `high_vol` | **High volatility regime** (Bollinger, GARCH, regime literature) | **No** *(optional polish)* | `high_vol` *(or `high_volatility_regime` for symmetry)* | "High vol" is universally recognized; full form is `high_volatility_regime` but the abbreviation reads cleanly. No semantic issue. |
| `intraday_vs_macro_diverged` | **Counter-trend move**, **HTF conflict**, **correction** (Elliott / Babypips / Murphy) | **YES — rename** | `intraday_counter_macro` *(or `intraday_counter_htf` if `macro_label` → `htf_label`)* | "Divergence" canonically means RSI/MACD-vs-price divergence; using it for timeframe-conflict will confuse readers. "Counter" is the established term for trend-conflict moves. |

### Summary

- **1 strong rename**: `intraday_vs_macro_diverged` → `intraday_counter_macro`
  (avoids collision with canonical "indicator divergence" meaning).
- **1 optional rename**: `macro_label` → `htf_label` (aligns with modern MTF
  vocabulary; not load-bearing). Keep `macro_label` if we prefer current
  descriptive naming.
- **3 fields keep current names**: `intraday_label`, `daily_slope_atr`,
  `high_vol` all align with canonical concepts or are precise descriptive metrics.

### MQL5 reference shape after recommended rename

```mql5
struct RegimeState {
   // Layer 1 — Macro (H1+H4)
   string macro_label;          // KEEP (or rename → htf_label)
   double macro_confidence;
   bool   macro_h1_strong;

   // Layer 2 — Intraday (M5+M15)
   string intraday_label;       // KEEP
   double intraday_confidence;
   bool   intraday_counter_macro;  // RENAMED from intraday_vs_macro_diverged

   // Layer 3 — Daily slope
   double daily_slope_atr;      // KEEP (metric, not label)
   bool   daily_bear_bias;
   bool   daily_bull_bias;
   bool   daily_flip_now;

   // Layer 4 — Volatility
   bool   high_vol;             // KEEP
   double m5_adx;

   // Layer 5 — Session / news
   string session;
   bool   news_active;
};
```

---

## §5. Open questions / Followups

1. **Should we also rename `macro_label` → `htf_label` for full MTF
   consistency?** Operator preference. Renaming gains industry-jargon alignment
   but loses some intuitive "macro = big picture" readability. Recommend
   defer to Phase 2 PR review.

2. **Should `intraday_label` get its own enum value `CORRECTING` or
   `COUNTER_HTF`?** The Apr 8 PM scenario is captured by
   `intraday_counter_macro = true`, but a dedicated `intraday_label =
   CORRECTING` value would make logging more readable. Defer to Phase 2.

3. **Volatility regime as 3-state enum (`LOW`/`NORMAL`/`HIGH`) vs current
   bool?** Bollinger, GARCH and academic literature all use 3+ states; FORGE
   only has the HIGH guard. If we later need a LOW-vol setup branch (e.g.
   "trade only the squeeze breakout"), we'll need to expand to enum.

4. **Should `macro_h1_strong` be renamed to `htf_h1_dominant`?** "Strong" is
   informal; "dominant" reads more like academic regime language. Low priority.

5. **No source explicitly endorses `daily_flip_now`** — this is FORGE-specific
   nomenclature for an edge-detected event. Acceptable as long as it's
   internally documented; no industry term exists for "daily-bias hysteresis
   one-tick edge flag".

---

## §6. References list (deduplicated, retrieved 2026-05-11)

1. [Dow theory — Wikipedia](https://en.wikipedia.org/wiki/Dow_theory)
2. [Volatility clustering — Wikipedia](https://en.wikipedia.org/wiki/Volatility_clustering)
3. [The Wyckoff Method — Wyckoff Analytics](https://www.wyckoffanalytics.com/wyckoff-method/)
4. [John Murphy's 10 Laws of Technical Trading — StockCharts ChartSchool](https://chartschool.stockcharts.com/table-of-contents/overview/john-murphys-10-laws-of-technical-trading)
5. [Bollinger Band Squeeze — StockCharts ChartSchool](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/bollinger-band-squeeze)
6. [Stage Analysis (Stan Weinstein)](https://www.stageanalysis.net/)
7. [Stage Analysis Complete Guide — TraderLion](https://traderlion.com/trading-strategies/stage-analysis/)
8. [Market Regimes Explained — LuxAlgo](https://www.luxalgo.com/blog/market-regimes-explained-build-winning-trading-strategies/)
9. [How To Perform A Multiple Time Frame Analysis — Tradeciety](https://tradeciety.com/how-to-perform-a-multiple-time-frame-analysis)
10. [Mastering Multiple Time-Frame Analysis — Markets4you](https://www.markets4you.com/en/blog/product-features/mastering-multiple-time-frame-analysis-in-forex-from-trend-to-entry/)
11. [Elliott Wave Degrees & Labeling — Elliott Wave Insights](https://elliottwaveinsight.co.uk/elliott-wave-degrees-labeling/)
12. [Regime-Switching Factor Investing with HMMs — MDPI](https://www.mdpi.com/1911-8074/13/12/311) *(snippet only — fetch returned 403)*
13. [Pullback — Babypips Forexpedia](https://www.babypips.com/forexpedia/pullback)
14. [Corrective Wave Pattern — Babypips](https://www.babypips.com/learn/forex/corrective-waves)
15. [Pullback vs Retracement vs Reversal — Gate Wiki](https://www.gate.com/crypto-wiki/article/pullback-vs-retracement-vs-reversal-understanding-the-key-differences-in-crypto-trading-20260116)
16. [Elliott Wave Theory — Elliott Wave Forecast](https://elliottwave-forecast.com/elliott-wave-theory/)
