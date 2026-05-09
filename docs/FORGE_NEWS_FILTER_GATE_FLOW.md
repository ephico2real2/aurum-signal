# FORGE 2.7.6 — News Filter Gate Flow

Native MT5 Economic Calendar news filter architecture and full signal gate flow.
Shows how a potential trade evaluates through every gate layer, where the news
filter intercepts, and how the two news-filter skip reasons are produced.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  FORGE 2.7.6 — Signal Gate Flow & News Filter Architecture                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

  OnTimer() → CheckNativeScalperSetups()
  │
  ├─ ScalperMode == BB_BOUNCE or DUAL?
  │    └─ BB_BOUNCE condition check (price near band, RSI, HTF align, ADX ≤ max)
  │         └─ direction = "BUY" or "SELL"
  │
  └─ ScalperMode == BB_BREAKOUT or DUAL?
       └─ ADX ≥ breakout_adx_min_eff? ──── NO ──→ [skip breakout block]
            │
            ├─ BUY path: prev_close > BB_upper + buffer
            │    RSI > buy_min? RSI < buy_ceil (70)?
            │    M5/M15 bull? H1/H4 aligned?
            │
            └─ SELL path: prev_close < BB_lower - buffer
                 RSI < sell_max? M5/M15 bear? H1/H4 aligned?

  ─────────────────────────────────────────────────────────────────────────────
  ANY setup candidate (direction != "") → CheckEntryQuality()
  ─────────────────────────────────────────────────────────────────────────────
  │
  ├─[Gate -1]  NEWS HARD BLOCK
  │             ScalperNewsUpdateEffectiveThresholds()
  │             │  ┌──────────────────────────────────────────────┐
  │             │  │  NEWS FILTER SUBSYSTEM                       │
  │             │  │                                              │
  │             │  │  ScalperNewsFilterRefresh()  (every 900s)   │
  │             │  │  ├─ CalendarValueHistory(from, to, NULL, cur)│
  │             │  │  │   cur = USD,EUR,GBP (or ALL → 9 CCY)     │
  │             │  │  ├─ Per event: importance → before/after min │
  │             │  │  │   LOW:5/5  MED:10/15  HIGH:20/30         │
  │             │  │  ├─ Keyword override: "Non-Farm:30,60" etc. │
  │             │  │  └─ Store closest future/active event:       │
  │             │  │     g_nf_block_start, g_nf_event_time,      │
  │             │  │     g_nf_block_end, g_nf_block_reason       │
  │             │  │                                              │
  │             │  │  ScalperNewsProximity()  (asymmetric)        │
  │             │  │  ├─ outside window      → return -1.0        │
  │             │  │  ├─ pre-news (now ≤ event_time):            │
  │             │  │  │   p = (now - block_start)                │
  │             │  │  │       / (event_time - block_start)       │
  │             │  │  │   → 0.0 at window open, 1.0 at event     │
  │             │  │  └─ post-news (now > event_time):           │
  │             │  │     p = (block_end - now)                   │
  │             │  │         / (block_end - event_time)          │
  │             │  │     → 1.0 at event, 0.0 at window close     │
  │             │  │                                              │
  │             │  │  ScalperNewsCheck()                          │
  │             │  │  ├─ p < 0          → ALLOW (0)              │
  │             │  │  │   eff_rsi_buy_ceil = 70.0                │
  │             │  │  │   eff_rsi_sell_min = 33.0                │
  │             │  │  ├─ hard_floor_min: event_time ≤ now        │
  │             │  │  │   ≤ event_time + 5min → BLOCK (2)        │
  │             │  │  ├─ p ≥ block_pct (0.85) → BLOCK (2)       │
  │             │  │  ├─ p ≥ tighten_pct (0.5):                 │
  │             │  │  │   slide = (p - 0.5) / (0.85 - 0.5)      │
  │             │  │  │   slide clamped to [0.0, 1.0]            │
  │             │  │  │   buy_ceil = 70 - (70-65)*slide          │
  │             │  │  │   sell_min = 33 + (38-33)*slide          │
  │             │  │  │   → TIGHTEN (1)                          │
  │             │  │  └─ p < tighten_pct → ALLOW (0)            │
  │             │  └──────────────────────────────────────────────┘
  │             │
  │             state==2 (BLOCK)?
  │             ├─ YES → log entry_quality_news_filter → return false ✗
  │             └─ NO (state 0 or 1) → eff_rsi values set, continue ↓
  │
  ├─[Gate 0]   direction cap: open groups in same direction < max? else ✗
  ├─[Gate 1]   ATR ≥ min_entry_atr? else ✗
  ├─[Gate 2]   avg body ratio ≥ min_body_ratio? else ✗
  ├─[Gate 3]   directional bars ≥ min_directional_bars? else ✗
  └─[Gate 4]   BB width now ≥ 95% of previous? (expansion) else ✗
               └─ return true ✓ (direction survives quality check)

  ─────────────────────────────────────────────────────────────────────────────
  Back in CheckNativeScalperSetups() — post-quality, mode-specific gates
  ─────────────────────────────────────────────────────────────────────────────

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  BB_BREAKOUT BUY PATH                                                   │
  │                                                                         │
  │  RSI > buy_min                     → pass                               │
  │  RSI < buy_ceil (70)               → pass  else log rsi_buy_ceil ✗     │
  │  H1 DI gate (if ADX < 28):         → pass                               │
  │    H1 DI+ > DI-?                     else log h1_di_buy ✗              │
  │                                                                         │
  │  [NEWS TIGHTEN — additive, independent]                                 │
  │  eff_rsi_buy_ceil < buy_ceil (70)  (news is tightening?)               │
  │  AND RSI ≥ eff_rsi_buy_ceil        (RSI in newly-blocked zone?)        │
  │    → log entry_quality_news_rsi_tighten ✗                               │
  │                                                                         │
  │  ALL pass → ENTRY (BUY)                                                 │
  └─────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  BB_BREAKOUT SELL PATH                                                  │
  │                                                                         │
  │  RSI < sell_max                    → pass                               │
  │  ADX ≥ adx_min_sell_eff (25)      → pass  else log adx_min_sell ✗     │
  │  Two-tier RSI floor:               → pass                               │
  │    RSI > sell_floor (33)                   else log rsi_sell_floor ✗   │
  │    weak ADX? RSI > floor_weak (36)         else log rsi_sell_adx_floor ✗
  │  ADX spike gate (6-bar lookback):  → pass                               │
  │    ADX[6 bars ago] ≥ adx_min_sell?         else log adx_spike_sell ✗  │
  │  RSI declining gate (if ADX < 28): → pass                               │
  │    RSI ≤ RSI[1 bar ago]?                   else log rsi_rising_sell ✗  │
  │                                                                         │
  │  [NEWS TIGHTEN — additive, independent]                                 │
  │  eff_rsi_sell_min > sell_floor (33) (news is tightening?)              │
  │  AND RSI ≤ eff_rsi_sell_min         (RSI in newly-blocked zone?)       │
  │    → log entry_quality_news_rsi_tighten ✗                               │
  │                                                                         │
  │  ALL pass → ENTRY (SELL)                                                │
  └─────────────────────────────────────────────────────────────────────────┘

  ─────────────────────────────────────────────────────────────────────────────
  News filter state → g_nf_eff_rsi values — how they interact
  ─────────────────────────────────────────────────────────────────────────────

  State         eff_buy_ceil   eff_sell_min   Gate -1   BUY tighten   SELL tighten
  ─────────────────────────────────────────────────────────────────────────────────
  ALLOW  (0)    70.0           33.0           pass      inactive*     inactive*
  TIGHTEN(1)    65.0→70.0†    38.0→33.0†     pass      may fire      may fire
  BLOCK  (2)    —              —              KILL       never reached never reached

  * inactive: guard condition false (70 < 70 = false, 33 > 33 = false)
  † linear slide proportional to depth in tighten zone (0.0 at entry, 1.0 at block)

  ─────────────────────────────────────────────────────────────────────────────
  Skip reason codes logged to FORGE_journal DB
  ─────────────────────────────────────────────────────────────────────────────

  entry_quality_news_filter        → hard BLOCK (Gate -1, any direction)
  entry_quality_news_rsi_tighten   → RSI in tightened zone (BUY or SELL)
  entry_quality_adx_min_sell       → ADX below sell floor (25)
  entry_quality_rsi_sell_floor     → RSI at/below normal sell floor (33)
  entry_quality_rsi_sell_adx_floor → RSI at/below weak-ADX sell floor (36)
  entry_quality_adx_spike_sell     → ADX spiked from flat base (6-bar)
  entry_quality_rsi_rising_sell    → RSI rising bar-over-bar (sell blocked)
  entry_quality_h1_di_buy          → H1 DI- > DI+ at weak ADX (buy blocked)
  entry_quality_rsi_buy_ceil       → RSI overbought at upper ceiling (70)
  entry_quality_atr                → market too compressed
  entry_quality_body               → doji / wick-dominant bars
  entry_quality_direction          → bars not closing in trade direction
  entry_quality_bb_contraction     → BB bands contracting
  entry_quality_direction_cap      → too many open groups same direction
```

## Design principles

**Additive / independent architecture** — the news filter does not merge with or
override existing gate RSI thresholds. The flow is strictly:
capture → evaluate → pass along to next check.

- **Gate -1** (`entry_quality_news_filter`) is a hard kill-switch inside
  `CheckEntryQuality()`. It fires before any other quality gate and returns
  `false` immediately on BLOCK. TIGHTEN/ALLOW states set the effective RSI
  globals and pass through.

- **News RSI tighten checks** sit after all mode-specific gates in
  `CheckNativeScalperSetups()` — BUY tighten fires only when `h1_di_ok` is
  true; SELL tighten fires only when `adx_dur_ok && rsi_decl_ok` are both true.
  They are the last line of defense before an entry is placed.

- **ALLOW state is truly inert** — guard conditions `eff_buy_ceil < buy_ceil`
  and `eff_sell_min > sell_floor` both evaluate to false when the effective
  values equal the config defaults (70/33), so no spurious skips occur.

## Config chain

```
.env  FORGE_NEWS_FILTER_*
  → scripts/sync_scalper_config_from_env.py
    → config/scalper_config.json  (news_filter_* under "safety")
      → ea/FORGE.mq5  ReadScalperConfig() hot-reload every 20 OnTimer ticks
        → ApplyNewsFilterInputOverrides()  (EA input panel overrides last)
```

16 keys wired across all four surfaces. Toggle `news_filter_enabled` in
`.env` or the EA input panel without recompile.

## Key MT5 API notes

- `CalendarValueHistory(vals, from, to, NULL, currency)` — `NULL` for country
  prevents false negatives (MQL5 docs: currency param matches any country
  issuing that currency).
- `TimeTradeServer()` used throughout (not `TimeGMT()` which is broken in
  Strategy Tester).
- Calendar cache refreshes every `news_filter_refresh_sec` (default 900s).
  In-tester: controlled by `news_filter_apply_in_tester` flag.
