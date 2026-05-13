```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                                Market Data                                   │
│                                                                              │
│ Raw broker + platform feeds                                                  │
│                                                                              │
│ e.g. OHLCV, spread, DOM, tick flow, session data, ATR, VWAP,                │
│ news state, symbol properties, higher timeframe candles                      │
│                                                                              │
│ Central normalized data source consumed by all downstream engines            │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                               Regime Engine                                  │
│                                                                              │
│ Determines current market environment/state                                  │
│                                                                              │
│ e.g. TRENDING, RANGING, EXPANSION, COMPRESSION,                              │
│ HIGH_VOLATILITY, NEWS_LOCKOUT, LONDON_OPEN                                   │
│                                                                              │
│ Controls which strategy families are allowed or suppressed                   │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Setup Detectors                                 │
│                                                                              │
│ Raw structural setup recognizers                                              │
│                                                                              │
│ e.g. breakout_buy_trig, dump_sell_trig, liquidity_sweep_buy,                │
│ asia_range_breakout, london_reversal_setup                                   │
│                                                                              │
│ ONLY detects patterns — does NOT decide execution                            │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Atomic Predicates                               │
│                                                                              │
│ Reusable truth-evaluation atoms                                              │
│                                                                              │
│ e.g. h1_trend_bullish, m5_rsi_oversold,                                      │
│ price_above_vwap, atr_expansion_active                                       │
│                                                                              │
│ Stateless reusable logic units used by higher-level composites               │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                                Filter Chain                                  │
│                                                                              │
│ Negative-space rejection pipeline                                            │
│                                                                              │
│ e.g. spread_block, news_block, chop_block,                                   │
│ cooldown_block, low_volume_block                                              │
│                                                                              │
│ Produces explicit SKIP reason codes                                          │
│                                                                              │
│ Defines what PREVENTS trade execution                                        │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                               Scoring Engine                                 │
│                                                                              │
│ Weighted probabilistic confidence model                                      │
│                                                                              │
│ e.g. +20 trend alignment                                                     │
│      +15 VWAP confirmation                                                   │
│      -10 spread expansion                                                    │
│      +25 momentum acceleration                                               │
│                                                                              │
│ Converts boolean logic into confidence/quality score                         │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                            Composite Strategies                              │
│                                                                              │
│ Higher-level semantic trading models                                         │
│                                                                              │
│ e.g. BULL_DAY_DIP_BUY                                                        │
│      NY_REVERSAL_SELL                                                        │
│      LONDON_BREAKOUT_EXPANSION                                               │
│                                                                              │
│ Combines setups + atoms + filters + scoring                                 │
│ into unified strategy identities                                             │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                                 Risk Engine                                  │
│                                                                              │
│ Dynamic exposure and protection system                                       │
│                                                                              │
│ e.g. max_daily_drawdown                                                      │
│      risk_per_trade                                                          │
│      dynamic lot sizing                                                      │
│      volatility scaling                                                      │
│      exposure limits                                                         │
│      correlation guardrails                                                  │
│                                                                              │
│ Decides WHETHER account can safely take trade                                │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Entry Geometry                                  │
│                                                                              │
│ Defines HOW trade is structured                                              │
│                                                                              │
│ e.g. direction, SL, TP1, TP2, trailing,                                      │
│ breakeven logic, scale-ins, pyramiding,                                      │
│ leg count, cooldown                                                          │
│                                                                              │
│ Converts approved signal into executable trade plan                          │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Trade State Machine                                │
│                                                                              │
│ Trade lifecycle controller                                                   │
│                                                                              │
│ e.g. IDLE → ARMED → ENTERED → MANAGING →                                     │
│ SCALE_IN → EXITING → COOLDOWN                                                │
│                                                                              │
│ Prevents duplicate execution and manages lifecycle transitions               │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Order Execution                                 │
│                                                                              │
│ Low-level MT5 trade execution layer                                          │
│                                                                              │
│ e.g. OrderSend(), modification, partial close,                               │
│ retry handling, slippage protection,                                         │
│ broker validation, fill policies                                             │
│                                                                              │
│ Final interaction with MetaTrader 5 trade server                             │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                       Telemetry / SCRIBE / SQLite                            │
│                                                                              │
│ Persistent analytics and observability layer                                 │
│                                                                              │
│ Stores:                                                                      │
│ - setups                                                                     │
│ - scores                                                                     │
│ - skip reasons                                                               │
│ - trade lifecycle                                                            │
│ - pnl                                                                         │
│ - regime snapshots                                                           │
│ - execution latency                                                          │
│ - model diagnostics                                                          │
│                                                                              │
│ Enables backtesting intelligence, ML training, and AI analysis               │
└──────────────────────────────────────────────────────────────────────────────┘
```
