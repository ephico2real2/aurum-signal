⏺ Got it. Current EA is stamped v2.7.35 in source; Run 23 is running with v2.7.34 binary, and v2.7.35 sits compiled awaiting Run 24 launch. Here's the unified 4-version staged plan with the schema/scribe pieces woven in.

  ---
  FORGE Version Roadmap — v2.7.34 → v2.7.37
  
  Two parts: (A) trade-side gate/lot/geometry fixes that have to ship hot to stop bleeds, and (B) infrastructure work (SIGNALS schema + scribe sync + composite framework + regime struct) that needs Run 23 data first.
  
  ---
  v2.7.34 — RUN 23 hot fixes (shipped, currently running)
  
  Purpose: Stop the Run 22 losses (G5001 SELL −$51, G5009 BUY −$305) immediately. No schema changes — pure gate/geometry tweaks.
  
  ┌──────────────────────────────────────────────────────────────────┬────────────────────────┬─────────────┐
  │                              Change                              │          Knob          │    Value    │
  ├──────────────────────────────────────────────────────────────────┼────────────────────────┼─────────────┤
  │ Block SELL when RSI exhausted (gold retraces up in chop)         │ FORGE_DUMP_MAX_RSI     │ 41 (was 50) │
  ├──────────────────────────────────────────────────────────────────┼────────────────────────┼─────────────┤
  │ Block BUY in BUY-exhaustion zone (RSI ceiling)                   │ FORGE_DUMP_MAX_RSI_BUY │ 70          │
  ├──────────────────────────────────────────────────────────────────┼────────────────────────┼─────────────┤
  │ Block SELL when H1 too bullish                                   │ FORGE_DUMP_SELL_H1_MAX │ 2.0         │
  ├──────────────────────────────────────────────────────────────────┼────────────────────────┼─────────────┤
  │ Extend Daily-Direction Gate to MOMENTUM_DUMP setup               │ (code — Option C)      │ shipped     │
  ├──────────────────────────────────────────────────────────────────┼────────────────────────┼─────────────┤
  │ TP1 0.4×ATR → 0.6×ATR (chop scalp banks reliably before retrace) │ tp1_atr_mult           │ 0.6         │
  └──────────────────────────────────────────────────────────────────┴────────────────────────┴─────────────┘
  
  Schema impact: none. Scribe impact: none.
  
  ---
  v2.7.35 — Run 24 launch (compiled, awaiting operator launch)
  
  Purpose: Fix the broken MOMENTUM_DUMP BUY-lot logic (all Run 23 BUYs in TREND_BULL collapsed to 0.01 broker minimum) + restructure staged-leg behavior to let Apr 8-type rallies keep adding.
  
  ┌──────────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────┬────────────────────────────────────────────┐
  │                              Change                              │                          Knob                          │                   Value                    │
  ├──────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ Split DUMP lot factors so BUY gets full size                     │ FORGE_DUMP_BUY_LOT_FACTOR / FORGE_DUMP_SELL_LOT_FACTOR │ 1.0 / 0.5                                  │
  ├──────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ Drop forced 10-leg staging (was masking wave-confirmation logic) │ FORGE_STAGED_INITIAL_LEGS                              │ commented out (default 1)                  │
  ├──────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ Require 500-pt favorable move before adding a staged leg         │ FORGE_STAGED_ADD_MIN_FAVORABLE_POINTS                  │ 500                                        │
  ├──────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ Amplify lot ×2 once setup is wave-confirmed                      │ FORGE_WAVE_CONFIRMATION_LOT_MULT                       │ 2.0                                        │
  ├──────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ Pending — add to v2.7.35 before launch (task #14):               │                                                        │                                            │
  ├──────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ BB_PULLBACK_SCALP BUY/SELL lot split                             │ FORGE_BB_PULLBACK_BUY/SELL_LOT_FACTOR                  │ TBD                                        │
  ├──────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ Chop-grid ladder (task #6)                                       │ (code)                                                 │ grid orders, basket-DD kill, no per-leg SL │
  ├──────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ Dump ATR-trail 0.6× (task #7)                                    │ (code)                                                 │ post-TP2 trail                             │
  └──────────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────┴────────────────────────────────────────────┘
  
  Schema impact: none. Scribe impact: none. Still pure trade-logic.
  
  ---
  v2.7.36 — SCHEMA milestone (post-Run 23/24) — the missing-indicator fix
  
  Purpose: Close the atlas §3 logging gaps + add 13 OHLC-derived atoms to SIGNALS so V3 composites become historically validatable, and propagate everything to scribe.
  
  The "missing indicators" problem this fixes:
  
  ┌────────────────────────────────────┬─────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────┐
  │             Indicator              │                            Today                            │                     After v2.7.36                      │
  ├────────────────────────────────────┼─────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ m15_adx                            │ logged as 0 (call-site bug — value computed but not passed) │ actual value                                           │
  ├────────────────────────────────────┼─────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ macd_histogram (M5)                │ logged as 0 (same bug)                                      │ actual value                                           │
  ├────────────────────────────────────┼─────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ pattern_score                      │ logged as 0 (same bug)                                      │ actual value                                           │
  ├────────────────────────────────────┼─────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ H4 trend strength                  │ not logged                                                  │ new column h4_trend                                    │
  ├────────────────────────────────────┼─────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ M15 trend strength                 │ not logged                                                  │ new column m15_trend                                   │
  ├────────────────────────────────────┼─────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ H1 DI balance (di_plus − di_minus) │ not logged                                                  │ new column h1_di_balance                               │
  ├────────────────────────────────────┼─────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ Day OHLC                           │ not logged                                                  │ new columns day_high, day_low, day_open                │
  ├────────────────────────────────────┼─────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ M5 prior-bar OHLC                  │ not logged                                                  │ new columns m5_open_1, m5_high_1, m5_low_1, m5_close_1 │
  ├────────────────────────────────────┼─────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ M5 lower-high cascade (3-bar)      │ not logged                                                  │ new column m5_lh_cascade (0/1)                         │
  ├────────────────────────────────────┼─────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ M5 higher-low cascade (3-bar)      │ not logged                                                  │ new column m5_hl_cascade (0/1)                         │
  ├────────────────────────────────────┼─────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ M5 body% of range                  │ not logged                                                  │ new column m5_body_pct                                 │
  └────────────────────────────────────┴─────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────┘
  
  All 13 atoms are broker-provided and EA-computable — verified against market_data.json and FORGE.mq5 production usage. No new broker subscriptions needed.
  
  Schema migration (idempotent ALTER TABLE in OnInit):
  ALTER TABLE SIGNALS ADD COLUMN h4_trend REAL DEFAULT 0;
  ALTER TABLE SIGNALS ADD COLUMN m15_trend REAL DEFAULT 0;
  ALTER TABLE SIGNALS ADD COLUMN h1_di_balance REAL DEFAULT 0;
  ALTER TABLE SIGNALS ADD COLUMN day_high/day_low/day_open REAL DEFAULT 0;
  ALTER TABLE SIGNALS ADD COLUMN m5_open_1/m5_high_1/m5_low_1/m5_close_1 REAL DEFAULT 0;
  ALTER TABLE SIGNALS ADD COLUMN m5_lh_cascade/m5_hl_cascade INTEGER DEFAULT 0;
  ALTER TABLE SIGNALS ADD COLUMN m5_body_pct REAL DEFAULT 0; 
  
  Scribe propagation — the part you flagged:
  1. Source SIGNALS table gets ALTER TABLE on FORGE OnInit (next run picks it up).
  2. Bridge (python/bridge*.py) needs matching ALTER TABLE forge_signals ADD COLUMN ... so sync doesn't error on "no such column" inserts.
  3. Old rows pre-v2.7.36 keep the 0/NULL defaults — clearly identifiable as "pre-logging-extension."
  4. Open question #1 in the design doc: confirm bridge file is python/bridge.py or python/sync_journal_to_scribe.py and whether it auto-detects new columns via PRAGMA table_info or hand-maps them.
  
  Composite layer shipping in v2.7.36 (Tier 1, from roadmap §4):
  
  ┌─────┬─────────────────────────────┬──────────────────┬────────────────────┬───────────────────────────────────────────────────────────┐
  │  #  │ Composite (canonical name)  │       Type       │ Validatable today? │             Validatable after v2.7.36 schema?             │
  ├─────┼─────────────────────────────┼──────────────────┼────────────────────┼───────────────────────────────────────────────────────────┤
  │ 1   │ BULL_DAY_DIP_BUY (V1)       │ BUY filter       │ ✓                  │ ✓ (no new atoms needed)                                   │
  ├─────┼─────────────────────────────┼──────────────────┼────────────────────┼───────────────────────────────────────────────────────────┤
  │ 2   │ INTRADAY_REVERSAL_SELL (V1) │ gate→SELL        │ ✓                  │ ✓ (V2/V3 newly validatable with m5_lh_cascade + day_high) │
  ├─────┼─────────────────────────────┼──────────────────┼────────────────────┼───────────────────────────────────────────────────────────┤
  │ 3   │ BLOCK_SELL_IN_CHOP          │ gate→block       │ ✓                  │ ✓                                                         │
  ├─────┼─────────────────────────────┼──────────────────┼────────────────────┼───────────────────────────────────────────────────────────┤
  │ 4   │ FRACTIONAL_SELL_IN_BULL     │ SELL (small lot) │ ✓                  │ ✓                                                         │
  └─────┴─────────────────────────────┴──────────────────┴────────────────────┴───────────────────────────────────────────────────────────┘
  
  Regime work in v2.7.36 = Phase 1 = NO refactor. Composites use existing globals (g_regime_label, h1_bull, g_daily_bear_bias). Goal: prove the composite framework works against real Run 24 data first.
  
  ---
  v2.7.37 — Phase 2 regime + Tier 2 composites + env-knob renames
  
  Purpose: After v2.7.36 ships and produces validated Tier 1 results, introduce the unified RegimeState struct alongside existing globals (strangler-fig — no removal yet), rename 20 regime env knobs with backward-compat
  aliases, ship Tier 2 composites.
  
  Workstream: Phase 2 regime struct
  Detail: Introduce g_regime (14 fields, 5 layers — taxonomy §3) alongside existing 56 vars. New code paths read g_regime.*; old paths untouched. Additive, low-risk.                   
  ────────────────────────────────────────
  Workstream: 20-knob env-knob rename 
  Detail: Per regime-taxonomy §10.5 mapping table. macro_* → htf_* etc. Add LEGACY_ALIASES so old names still work during the transition. Python contract preserved — scalper_config.json keys +
    sync_scalper_config_from_env.py screening logic untouched (operator-confirmed constraint).
  ────────────────────────────────────────
  Workstream: HTF/MTF/LTF vocabulary
  Detail: Code-side rename of internal variables matches the doc-side vocabulary already adopted in atlas/taxonomy.
  ────────────────────────────────────────
  Workstream: Tier 2 composites
  Detail: TREND_CONTINUATION_BUY, CHOP_LADDER_BUY_GRID, NO_TREND_DAY regime label.
  ────────────────────────────────────────
  Workstream: Researched candidate composites (3 highest-confidence from background research, roadmap §6)
  Detail: FAILED_BREAKOUT_FADE (Bulkowski + Bollinger canonical, 28-44% failure rate), PRIOR_DAY_HIGH_LOW_TEST (Capital.com broker-tier doc), ASIA_RANGE_BREAKOUT_LONDON_OPEN (mql5 community canonical + 65-70% directional
  
    bias).
  
  Schema impact: none new (the v2.7.36 schema covers V2/V3 atoms). Scribe impact: none new.
  
  ---
  Cross-cutting: what each version touches
  
  ┌─────────────────────────────────┬─────────────────────────┬─────────────────────────┬────────────────────────────────────────────────────┬──────────────────────────────────────────────────┐
  │              Layer              │         v2.7.34         │         v2.7.35         │                      v2.7.36                       │                     v2.7.37                      │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ EA code (ea/FORGE.mq5)          │ gate tweaks             │ lot/staging tweaks      │ schema + 13 atom helpers + JournalRecordSignal sig │ RegimeState struct + composite implementations   │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ .env knobs                      │ 5 new/changed           │ 4 new/changed           │ 0                                                  │ ~20 renamed + new COMPOSITE_*_ENABLE flags       │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ SIGNALS DB schema               │ unchanged               │ unchanged               │ 13 new columns + 3 zero-bug fixes                  │ unchanged                                        │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ Scribe (forge_signals)          │ unchanged               │ unchanged               │ ALTER TABLE + bridge sync update                   │ unchanged                                        │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ sync_scalper_config_from_env.py │ unchanged               │ unchanged               │ unchanged                                          │ LEGACY_ALIASES added (Python contract preserved) │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ config/scalper_config.json      │ mirrors .env via sync   │ same                    │ same                                               │ same (keys unchanged — operator constraint)      │
  ├─────────────────────────────────┼─────────────────────────┼─────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ gate_legend.json                │ possible new gate codes │ possible new gate codes │ possible new gate codes                            │ possible new composite-related codes             │
  └─────────────────────────────────┴─────────────────────────┴─────────────────────────┴────────────────────────────────────────────────────┴──────────────────────────────────────────────────┘
  
