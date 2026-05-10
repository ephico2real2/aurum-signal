//+------------------------------------------------------------------+
//|  FORGE.mq5  — FORGE Multi-Mode Expert Advisor v2.0.0            |
//|  Signal System  — XAUUSD Scalper + Native Price Action          |
//|  Build order: #2 — independent of Python, compiled in MT5       |
//+------------------------------------------------------------------+
//
//  ARCHITECTURE OVERVIEW:
//  FORGE is the MT5-side execution engine. It runs on the XAUUSD chart
//  and communicates with Python (BRIDGE) via JSON files in Common Files.
//  There is NO HTTP — everything is file-based polling.
//
//  DATA FLOW:
//    BRIDGE writes → command.json  → FORGE reads + executes
//    BRIDGE writes → config.json   → FORGE reads (mode, thresholds, regime_* for native scalper gate).
//    Strategy Tester: mode/scalper/regime from config.json are ignored — BRIDGE is not running; stale
//    effective_mode (e.g. WATCH under circuit breaker) must not override EA Inputs.
//    FORGE writes  → market_data.json → BRIDGE + ATHENA read
//    FORGE writes  → broker_info.json  → ATHENA reads (account type)
//    FORGE writes  → mode_status.json  → ATHENA reads
//
//  COMMAND ACTIONS (from command.json):
//    OPEN_GROUP      — place N trades across entry ladder with TP split
//    CLOSE_ALL       — close all positions + cancel all pending orders
//    CLOSE_PCT       — close N% of all positions
//    CLOSE_GROUP     — close positions + pendings for specific magic number
//    CANCEL_GROUP_PENDING — cancel pending orders only for specific magic number
//    CLOSE_GROUP_PCT — close N% of positions for specific magic number
//    CLOSE_PROFITABLE— close only positions in profit
//    CLOSE_LOSING    — close only positions in loss
//    MOVE_BE_ALL     — move all SL to breakeven
//    MODIFY_SL       — change SL; optional fields:
//                       magic     → scope to a single group (existing)
//                       ticket    → scope to ONE position/pending ticket
//                       tp_stage  → scope to legs whose comment matches |TP<n> (1/2/3)
//    MODIFY_TP       — change TP; same optional scope fields as MODIFY_SL
//                      (omit ticket+tp_stage for legacy whole-magic behaviour)
//
//  MARKET DATA OUTPUT (every 3s via OnTimer):
//    - price: bid/ask/spread
//    - account: balance/equity/margin/floating PnL
//    - indicators_h1: RSI, EMA20/50, ATR, BB, MACD, ADX
//    - indicators_m5/m15/m30: same indicators for scalping timeframes
//    - open_positions[]: ticket, type, lots, price, SL, TP, profit, magic
//    - pending_orders[]: ticket, type, volume, price, SL, TP, magic
//
//  TP SPLIT (v1.3.0):
//    When opening a group, 70% of positions get TP1, 30% get TP2.
//    When TP1 hits, ManageOpenGroups moves remaining SL to BE + TP to TP2.
//
//  MAGIC NUMBERS:
//    Each group gets magic = MagicNumber + group_id (from BRIDGE)
//    Range check: [MagicNumber, MagicNumber + 10000)
//
//  Modes:  OFF | WATCH | SIGNAL | SCALPER | HYBRID | AUTO_SCALPER
//+------------------------------------------------------------------+

#property strict
#property version "2.81"
#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Files\FileTxt.mqh>

const string FORGE_VERSION = "2.7.11";

// ── INPUT PARAMETERS (shown in EA dialog when attaching to chart) ──
input string  FilesPath      = "";           // Override MT5 Files path (leave blank for auto)
input int     MagicNumber    = 202401;       // EA magic number
input int     TimerSeconds   = 1;            // OnTimer interval (seconds)
input bool    EnableBacktest = false;        // Unused — Tester is detected via MQL_TESTER; kept for input-slot compatibility
input bool    LogTicks       = true;         // Log ticks in WATCH mode
input string  InputMode      = "WATCH";      // Startup mode: OFF|WATCH|SIGNAL|SCALPER|HYBRID
input int     BrokerInfoEveryCycles = 20;    // Re-write broker_info.json every N timer cycles (0=OnInit only)
// ── NATIVE SCALPER — Inputs (see also config/scalper_config.json lot_sizing) ──
input string  ScalperMode    = "DUAL";       // Native scalper: NONE|BB_BOUNCE|BB_BREAKOUT|DUAL
input double  ScalperLot     = 0.0;          // Lot per leg (0=use scalper_config.json fixed_lot; >0 overrides JSON — same semantics as SellInsideBandLotFactor)
input int     ScalperTrades  = 4;            // Default leg count when lot source = Inputs only (ignored when using JSON min/max envelope)
input int     ScalperMinTrades = 0;          // Min legs 1..30 for native group; 0 = use scalper_config.json min_num_trades only
input int     ScalperMaxTrades = 0;          // Max legs 1..30 for native group; 0 = use scalper_config.json max_num_trades only
input double  PendingEntryThresholdPoints = 50.0;   // Market-vs-pending switch threshold (points)
input double  TrendStrengthAtrThreshold   = 0.20;   // ATR-normalized EMA trend threshold
input double  BreakoutBufferPoints        = 10.0;   // Breakout buffer beyond BB band (points)
input bool    NativeScalperH4Align        = true;   // Require H4 EMA/ATR trend alignment (same threshold as H1)
input bool    NativeScalperRegimeGate     = true;   // Block counter-trend vs TREND_BULL/BEAR when config regime_* says so
input string  NativeScalperM1Mode         = "NONE"; // NONE | CONFIRM (M1 EMA/ATR vs bias) | TRIGGER (CONFIRM + last closed M1 candle direction)
input bool    NativeScalperAutoLotByTrend = false;  // Optional: scale lot size by trend strength (bounded, breakout-friendly)
input bool    NativeScalperAutoLotBreakoutOnly = true; // When true, trend auto-lot applies to BB_BREAKOUT only
input double  NativeScalperAutoLotMaxMultiplier = 2.0; // Hard cap multiplier (1.0..5.0)
input double  NativeScalperAutoLotTrendRef = 1.0;   // Trend strength that reaches max multiplier
input bool    NativeScalperInputsOverrideLotSizing = false; // true = force ScalperLot + ScalperTrades from Inputs; false = prefer scalper_config.json (fixed_lot, min/max legs, resolver)
input bool    NewsFilterInputsOverride = false; // true = use NewsFilterEnabled input over config
input bool    NewsFilterEnabled        = true;  // Enable native news filter (when NewsFilterInputsOverride=true)
input double  SellInsideBandLotFactor = 0.0;               // Lot fraction for BB_BREAKOUT SELL when price inside BB band (0=use scalper_config.json sell_inside_band_lot_factor; 0.1–1.0 overrides)
input int     ScalperWarmupSeconds = 0;       // Extra delay after other warmup gates (live + Tester), wall/sim seconds. 0 = off. Live: prefer LiveWarmupM15Bars.
input int     ScalperLiveWarmupM15Bars = 1;   // Live only: min M15 bar rollovers after attach (~1 = wait past one M15 open). 0 = off.
input int     ScalperTesterWarmupM5Bars = 2;       // Strategy Tester: M5 bar rollovers after init (each ~5 min simulated time); 0=off.
input int     ScalperTesterWarmupSimCapMinutes = 0; // Strategy Tester: after this many *simulated* minutes, waive M5 rollover wait (0=off). Only if ScalperTesterWarmupM5Bars>0.

// ── GLOBALS ───────────────────────────────────────────────────────
// CTrade: MQL5 trade execution helper (buy, sell, modify, close)
// CPositionInfo: MQL5 position info reader (ticket, price, profit)
CTrade     g_trade;
CPositionInfo g_pos;

string g_mode         = "SIGNAL";
string g_files_path   = "";
string g_last_cmd_ts  = "";
int    g_cycle        = 0;
int    g_cycles_since_broker = 0;
double g_session_start_balance = 0;

// ── NATIVE SCALPER STATE ──────────────────────────────────────────
string g_scalper_mode = "NONE";  // NONE | BB_BOUNCE | BB_BREAKOUT | DUAL
int    g_scalper_group_counter = 5000;  // native groups start at 5000+ to avoid BRIDGE collision
int    g_scalper_session_trades = 0;
datetime g_scalper_last_loss_time   = 0;
datetime g_last_sl_time_buy         = 0;  // last SL hit on a BUY group — for post-SL direction cooldown
datetime g_last_sl_time_sell        = 0;  // last SL hit on a SELL group
datetime g_scalper_last_entry_bar = 0;  // prevent multiple entries on same bar
string   g_scalper_last_direction = "";          // last entry direction for anti-whipsaw
datetime g_scalper_last_direction_time = 0;      // when last direction was entered
datetime g_scalper_last_reset_day = 0;  // UTC day marker for session counter reset
string   g_scalper_last_session_label = "";      // UTC session label used to reset first-entry anchors
datetime g_scalper_last_nosetup_log_bar  = 0;   // throttle noisy "no setup" (once per M5 bar)
datetime g_scalper_last_rrtoolow_log_bar = 0;   // throttle journal rr_too_low (once per M5 bar)
datetime g_scalper_last_sesscut_log_bar  = 0;   // throttle entry_quality_session_sell_cutoff (2.7.7)
datetime g_scalper_last_macd_log_bar     = 0;   // throttle entry_quality_macd_* gates (2.7.7)
datetime g_scalper_last_h1disell_log_bar = 0;  // throttle entry_quality_h1_di_sell (2.7.12)
datetime g_scalper_last_h1macd_log_bar   = 0;  // throttle entry_quality_h1_macd_sell (2.7.12)
datetime g_scalper_last_adxblk_log_bar   = 0;   // throttle entry_quality_adx_extreme_sell (2.7.7)
double   g_last_combined_lot_factor      = 1.0; // last computed combined lot factor — written to SIGNALS.lot_factor
datetime g_scalper_last_sesswarn_log_bar = 0; // throttle session_off log (once per M5 bar)
datetime g_scalper_last_cooldown_log_bar = 0; // throttle cooldown log (once per M5 bar)
datetime g_scalper_last_atr_ext_log_bar = 0;  // throttle entry_quality_atr_ext log (once per M5 bar)
datetime g_scalper_last_attempt_time = 0;     // rate-limit order retries (one attempt per second)
datetime g_forge_init_gmt = 0;                 // TimeGMT() at OnInit — warmup delay anchor (Tester + live)
datetime g_scalper_last_warmup_log_bar = 0;   // throttle warmup skip log (once per M5 bar)
bool     g_scalper_warmup_ready_logged = false; // one-shot "entries enabled" after first successful warmup
datetime g_warmup_m5_time_ref = 0;             // Tester: last seen M5 bar time for warmup rollover counting
int      g_warmup_m5_rollover_count = 0;      // Tester: M5 bar opens counted since init
datetime g_warmup_m15_time_ref = 0;            // Live: last seen M15 bar time for warmup rollover counting
int      g_warmup_m15_rollover_count = 0;   // Live: M15 bar opens counted since init
string   g_scalper_config_snapshot = "";       // skip re-parse + log spam when scalper_config.json unchanged
bool     g_scalper_config_missing_logged = false; // one-shot Journal hint when scalper JSON cannot be opened
bool     g_adx_trend_regime = false;           // persistent ADX hysteresis regime state (M5)
string   g_warmup_last_reason = "";            // last warmup sub-reason for mode_status.json / journal
bool     g_warmup_last_ok = false;              // true once warmup has passed (sticky after first success)
int      g_tester_run_id = 0;                  // TESTER_RUNS.id for the current run (0 = live/unset)
double g_first_buy_entry_price = 0.0;   // price of first BUY group opened this session; 0 = none
double g_first_sell_entry_price = 0.0;  // price of first SELL group opened this session; 0 = none
datetime g_scalper_last_adxgate_log_bar = 0;   // throttle ADX gate diagnostic (once per M5 bar)
datetime g_scalper_last_adxsell_log_bar = 0;   // throttle entry_quality_adx_min_sell journal (once per M5 bar)
datetime g_scalper_last_adxdur_log_bar  = 0;   // throttle entry_quality_adx_spike_sell journal (once per M5 bar)
datetime g_scalper_last_rsidecl_log_bar = 0;   // throttle entry_quality_rsi_rising_sell journal (once per M5 bar)
datetime g_scalper_last_m30bear_log_bar = 0;   // throttle entry_quality_m30_not_bearish journal (2.7.9)
datetime g_scalper_last_h1dibuy_log_bar = 0;   // throttle entry_quality_h1_di_buy journal (once per M5 bar)
datetime g_scalper_last_rsisellfloor_log_bar = 0; // throttle entry_quality_rsi_sell_floor/adx_floor (once per M5 bar)
bool     g_scalper_prev_session_blocked = true; // session-start log: true = previous tick was session_off

// Native news filter state
datetime g_nf_next_refresh             = 0;
datetime g_nf_block_start              = 0;
datetime g_nf_block_end                = 0;
datetime g_nf_event_time               = 0;
string   g_nf_block_reason             = "";
bool     g_nf_have_window              = false;
datetime g_scalper_last_newsfilter_log_bar = 0;
double   g_nf_eff_rsi_buy_ceil         = 70.0;
double   g_nf_eff_rsi_sell_min         = 33.0;

// Scalper config (from scalper_config.json or defaults)
struct ScalperConfig {
   // BB Bounce
   bool   bounce_enabled;
   double bounce_adx_max;
   double bounce_rsi_buy_max;
   double bounce_min_h1_trend;         // Cardwell: min H1 trend strength for BB_BOUNCE BUY (default 0.3)
   double bounce_rsi_sell_min;
   double bounce_bb_proximity_pct;
   double bounce_reclaim_pct;
   bool   bounce_require_rejection_candle;
   double bounce_sl_atr_mult;
   double bounce_tp1_close_pct;
   double bounce_tp2_close_pct;
   double bounce_lot_factor;        // fractional lot for BB_BOUNCE entries (1.0=full, 0.25=quarter; default 1.0)
   // BB Breakout
   bool   breakout_enabled;
   double breakout_adx_min;       // BUY breakout ADX floor (default 20)
   double breakout_adx_min_sell;  // SELL breakout ADX floor — stricter (default 25)
   bool   breakout_require_rsi_declining_sell;       // block SELL if RSI rising bar-over-bar (default false)
   double breakout_rsi_decl_sell_adx_threshold;     // rsi_rising_sell auto-off: gate inactive when ADX ≥ this (default 28; independent of two-tier RSI floor)
   // M30 intermediate-TF bearish confirmation (2.7.9 — Feature 3)
   // Requires M30 EMA20 < EMA50 when ADX ≥ adx_min; blocks recovery entries where H1 is stale
   bool   breakout_require_m30_bear_sell;           // require M30 EMA20 < EMA50 for SELL (default true)
   double breakout_m30_bear_adx_min;                // M30 gate only activates when m5_adx ≥ this (default 25)
   bool   breakout_require_h1_di_buy;               // block BUY when H1 DI- > DI+ at weak ADX (default false; DI+/DI- Wilder directional gate)
   double breakout_counter_buy_adx_threshold;       // h1_di_buy gate active only when m5_adx < this (default 28; auto-off in strong trend)
   bool   breakout_require_h1_di_sell;              // block SELL when H1 DI+ >= DI- (bullish H1 — no ADX bypass; catches false breakdowns)
   bool   breakout_require_h1_macd_sell;            // block SELL when H1 MACD histogram >= 0 (H1 bullish momentum; Run 12+ gate)
   int    breakout_adx_min_sell_lookback_bars;       // ADX spike-from-flat gate: bars back to check (default 6 = 30min; 0=disabled)
   // Cardwell RSI Zone Theory (Andrew Cardwell):
   //   Uptrend range: RSI 40–80.  Bull Support floor = 40 (long re-entry on dip).
   //   Downtrend range: RSI 20–60.  Bear Resistance ceiling = 60 (short re-entry on bounce).
   // Sources: tradingview.com/script/v6JlR98g, alchemymarkets.com/education/indicators/relative-strength-index
   double breakout_rsi_buy_min;   // Cardwell Bull Support floor — BUY only when RSI > this (default 40)
   double breakout_rsi_sell_max;  // Cardwell Bear Resistance ceiling — SELL only when RSI < this (default 60)
   double breakout_rsi_buy_ceil;              // block BUY breakout when RSI >= this (default 70.0)
   double breakout_rsi_sell_floor;            // block SELL breakout when RSI <= this (default 33.0)
   double breakout_adx_sell_floor_threshold;  // ADX below this uses rsi_sell_floor_weak_adx (default 35.0)
   double breakout_rsi_sell_floor_weak_adx;   // stricter floor when ADX < threshold (default 36.0)
   bool   breakout_h1h4_crash_sell;           // bypass RSI floor + ADX spike on confirmed H1+H4 bear crash
   // Cardwell: RSI 20 is the extreme-oversold floor in a confirmed downtrend (RSI 20–60 range).
   // Below RSI 20 the move is exhausted — mean-reversion risk spikes even in genuine crashes.
   double breakout_h1h4_crash_sell_rsi_min;   // Cardwell downtrend floor — RSI must be above this in crash bypass (default 20)
   double h1h4_crash_sell_adx_max;            // crash bypass blocked when ADX > this — high ADX = move already extended (default 40)
   double breakout_min_h1_bear_strength;      // SELL blocked when |H1 trend| < this — filters barely-bearish H1 (default 0.2)
   double breakout_sell_inside_band_lot_factor; // lot multiplier when SELL entry is above BB lower (default 0.5)
   double breakout_max_reentry_atr_ext;  // 0 = disabled; >0 = max ATR multiples price can be from first entry for re-entry
   double breakout_sl_atr_mult;
   double breakout_tp1_atr_mult;      // fallback if direction-specific not set
   double breakout_tp1_buy_atr_mult;  // TP1 for BUY (0 = use breakout_tp1_atr_mult)
   double breakout_tp1_sell_atr_mult; // TP1 for SELL (0 = use breakout_tp1_atr_mult)
   double breakout_tp2_atr_mult;
   double breakout_tp3_atr_mult;
   double breakout_tp4_atr_mult;
   double breakout_tp1_close_pct;
   bool   breakout_require_m15;
   bool   breakout_move_be;
   int    fast_lock_min_hold_sec_bounce;
   int    fast_lock_min_hold_sec_breakout;
   // Session SELL cutoff (2.7.7) — block new SELL entries after configured UTC hour
   // Research: post-17:00 UTC = lower liquidity, wider spreads, adverse for XAUUSD scalps (TMGM, ACY, NordFX)
   int    session_ny_sell_cutoff_utc;      // block SELL when UTC hour >= this in NY session (0=disabled, default 17)
   int    session_london_sell_cutoff_utc;  // block SELL in London session (0=disabled, default 0)
   // OsMA(3,10,16) histogram gate (2.7.7) — MACD Histogram MC 4-quadrant approach; arXiv:2206.12282 84-86% WR
   // Q0(+↑)=strong bull, Q1(+↓)=bull fading, Q2(−↓)=strong bear ✓, Q3(−↑)=bear fading
   bool   breakout_require_macd_sell;      // block SELL outside Q2 (histogram must be negative+falling)
   bool   breakout_require_macd_buy;       // block BUY outside Q0 (histogram must be positive+rising); default off
   int    breakout_macd_fast;              // OsMA fast EMA period (default 3 for scalping)
   int    breakout_macd_slow;              // OsMA slow EMA period (default 10)
   int    breakout_macd_signal;            // OsMA signal SMA period (default 16)
   // ADX-tiered lot factors (2.7.7) — more extended move = smaller bet
   // Research: OpoFinance/Trade2Win: ADX lags on M5 — use M15 ADX for tier decision
   bool   breakout_adx_lot_use_m15;        // use M15 ADX for tier (less lag than M5)
   double breakout_adx_lot_mid_threshold;   // ADX >= this → mid factor (default 35)
   double breakout_adx_lot_high_threshold;  // ADX >= this → 1/8th lot / broker min (default 45)
   double breakout_adx_lot_factor_mid;      // lot factor at mid-threshold (default 0.25)
   double breakout_adx_lot_factor_high;     // lot factor at high-threshold — 1/8th = 0.01 lot at base 0.08 (default 0.125)
   double breakout_adx_sell_block_threshold;// ADX >= this → BLOCK SELL entirely (default 55); at min lot 1/16th = same as 1/8th
   // Cardwell SELL LIMIT cascade (2.7.7b) — pending orders catch RSI bounce toward Bear Resistance
   bool   breakout_sell_limit_enabled;      // place SELL LIMITs above crash entry (default true)
   double breakout_sell_limit_atr_mult;     // L1 SELL LIMIT at bid + ATR × this (default 0.4 = 1st Cardwell bounce)
   double breakout_sell_limit_lot_factor;   // L1 lot factor — 1/8th (default 0.125)
   int    breakout_sell_limit_expiry_bars;  // cancel if not filled within N M5 bars (default 6 = 30min)
   // SELL LIMIT L2 — second cascade level at deeper Cardwell Bear Resistance zone (2.7.10)
   bool   breakout_sell_limit_l2_enabled;   // place L2 SELL LIMIT at deeper bounce (default true)
   double breakout_sell_limit_l2_atr_mult;  // L2 price: bid + ATR × this (default 0.65 = 50-62% retrace)
   double breakout_sell_limit_l2_lot_factor;// L2 lot factor — 1/8th (default 0.125)
   // SELL STOP continuation (2.7.10 Day 2) — places SELL STOP below crash low after TP1 hit
   // Captures second impulse leg when RSI is not yet exhausted (RSI > sell_stop_cont_min_rsi)
   // Enable via .env: FORGE_SELL_STOP_CONT_ENABLED=1; disabled by default to preserve pre-2.7.10 behavior
   bool   sell_stop_cont_enabled;      // arm SELL STOP below TP1 after TP1 hit (default false)
   double sell_stop_cont_atr_mult;     // SELL STOP price: tp1 - ATR × this (default 0.40)
   double sell_stop_cont_lot_factor;   // lot factor per continuation leg — 1.0 = full lot, same as primary (default 1.0)
   double sell_stop_cont_tp_atr_mult;  // TP: cascade_entry - ATR×mult (default 1.5 = ~9pts @ ATR=6)
   int    sell_stop_cont_expiry_bars;  // cancel if not triggered within N M5 bars (default 2 = 10 min)
   double sell_stop_cont_min_rsi;      // only arm when M5 RSI > this — blocks exhausted entries (default 25.0)
   int    sell_stop_cont_legs;         // number of cascade SELL STOP legs to place (default 5, max 7)
   // BUY LIMIT recovery (2.7.10 Day 3) — Cardwell Bull Support entry after crash RSI bounce
   // Arms at SELL TP1 hit when RSI has recovered above min_rsi (> 35 = Cardwell Bull Support zone entered)
   // Price: crash TP1 level — buy at the established swing low, not chasing the recovery
   // Expiry: short (4 bars / 20 min) — stale recovery limits become losing longs
   // Enable: FORGE_BUY_LIMIT_RECOVERY_ENABLED=1 in .env
   bool   buy_limit_recovery_enabled;  // arm BUY LIMIT at TP1 crash low after TP1 hit (default false)
   double buy_limit_recovery_min_rsi;  // only arm when M5 RSI > this — Cardwell Bull Support zone (default 35.0)
   double buy_limit_recovery_lot_factor; // lot factor (default 0.25)
   int    buy_limit_recovery_expiry_bars;// cancel if not filled within N M5 bars (default 4 = 20 min)
   double buy_limit_recovery_sl_atr_mult;// SL = TP1 - ATR × this below the crash low (default 1.0)
   // H4 supplemental gates — disabled by default (2.7.10)
   // Enable via .env: FORGE_H4_RSI_GATE_ENABLED=1, FORGE_H4_ADX_GATE_ENABLED=1
   // Rationale: H4 RSI identifies structural HH/LL exhaustion zones (Cardwell Bear Resistance ≥60 / Bull Support ≤40)
   //            H4 ADX confirms the H4 trend is directional (not ranging) before adding a directional scalp entry
   //            H4 BB upper/lower exported to market_data.json for BRIDGE/LENS structural context (no entry gate)
   bool   h4_rsi_gate_enabled;   // block SELL when H4 RSI >= h4_rsi_sell_max; block BUY when H4 RSI <= h4_rsi_buy_min (default false)
   double h4_rsi_sell_max;       // SELL blocked when H4 RSI >= this — Cardwell Bear Resistance zone (default 60)
   double h4_rsi_buy_min;        // BUY blocked when H4 RSI <= this — Cardwell Bull Support zone (default 40)
   bool   h4_adx_gate_enabled;   // block entries when H4 ADX < h4_adx_min — prevents entries in ranging H4 (default false)
   double h4_adx_min_sell;       // H4 ADX minimum for SELL entries (default 20.0)
   double h4_adx_min_buy;        // H4 ADX minimum for BUY entries (default 20.0)
   // Safety
   double max_spread_points;
   int    max_open_groups;
   int    max_trades_per_session;
   int    loss_cooldown_sec;
   int    post_sl_cooldown_sec;         // extended cooldown per-direction after SL hit (default 3600s = 60min)
   double breakout_near_floor_lot_factor;  // Cardwell RSI 20-25 zone: lot factor when crash bypass + RSI near floor (default 0.25)
   double same_direction_stack_lot_factor; // lot factor for 2nd concurrent group in same direction (default 0.25)
   bool   tester_cooldown_enabled;
   // Directional anti-whipsaw
   bool   direction_cooldown_enabled;
   int    direction_cooldown_bars;
   // Session
   int    london_start;
   int    london_end;
   int    ny_start;
   int    ny_end;
   bool   skip_asian;    // skip Asian session trades (hot-reload via scalper_config.json)
   bool   skip_london;   // skip London session trades (hot-reload via scalper_config.json)
   bool   skip_ny;       // skip NY session trades (hot-reload via scalper_config.json)
   // Tester session control
   bool   tester_session_filter;
   string tester_allowed_sessions;
   // DD event
   double dd_tight_tp_atr;
   int    sentinel_min_threshold;
   bool   news_filter_enabled;
   string news_filter_currencies;
   int    news_filter_low_before;
   int    news_filter_low_after;
   int    news_filter_medium_before;
   int    news_filter_medium_after;
   int    news_filter_high_before;
   int    news_filter_high_after;
   string news_filter_special;
   int    news_filter_hard_floor_min;
   double news_filter_tighten_pct;
   double news_filter_block_pct;
   double news_filter_tighten_rsi_buy;
   double news_filter_tighten_rsi_sell;
   int    news_filter_refresh_sec;
   bool   news_filter_apply_in_tester;
   double pending_entry_threshold_points;
   double trend_strength_atr_threshold;
   double breakout_buffer_points;
   // High-volatility trend guardrails (live-focused).
   bool   high_vol_trend_guard_enabled;
   bool   high_vol_apply_in_tester;
   double high_vol_adx_min;
   double high_vol_trend_strength_min;
   bool   high_vol_disable_bounce;
   bool   high_vol_require_h1_h4_breakout_align;
   double high_vol_breakout_sl_boost;
   int    high_vol_fast_lock_extra_hold_sec;
   double high_vol_fast_lock_trigger_mult;
   double high_vol_fast_lock_trail_mult;
   double fast_lock_min_profit_points;
   double fast_lock_spread_guard_mult;
   // >1 widens fast-lock trigger/trail (more room before SL ratchet tightens). 1.0 = legacy behaviour.
   double fast_lock_breath_mult;
   bool   adx_hysteresis_enabled;
   bool   adx_hysteresis_apply_in_tester;
   double adx_trend_enter;
   double adx_trend_exit;
   int    sell_loss_grace_sec;
   double sell_loss_grace_adverse_points;
   double min_sl_atr_mult;
   double min_rr;
   double min_rr_floor;
   // After ATR + structural + min-distance SL: widen by this many points (BUY → SL lower, SELL → SL higher).
   double native_sl_extra_buffer_points;
   // Entry Quality Gate — M5 bar-based pre-entry validation
   double min_entry_atr;           // reject entries when ATR < this (default 3.5)
   int    max_open_same_direction; // max concurrent open groups per direction (default 1)
   int    entry_quality_bars;      // look-back bars for body/direction checks (default 3)
   double min_body_ratio;          // min avg body/candle ratio — filters doji/wick bars (default 0.40)
   int    min_directional_bars;    // min bars agreeing with trade direction out of entry_quality_bars (default 2)
   bool   require_bb_expansion;    // reject entries when BB width is contracting (default true)
   string lot_sizing_source;
   bool   lot_inputs_override;
   // Lot sizing precedence: config/scalper_config.json lot_sizing by default,
   // optionally overridden by MT5 Inputs when NativeScalperInputsOverrideLotSizing=true.
   double lot_fixed;
   int    lot_num_trades;
   int    lot_min_trades;
   int    lot_max_trades;
   // Staged native entries: open a probe first, add legs after time + favorable excursion.
   bool   staged_entry_enabled;
   int    staged_initial_legs;
   int    staged_add_interval_sec;
   double staged_add_min_favorable_points;
   // true = min_favorable_points measured from first probe only (legacy). false = after each add, anchor resets — each new leg needs fresh move in favor.
   bool   staged_favorable_from_entry_only;
   // OPEN_GROUP entry ladder: if some legs filled as market/limits and pendings remain, cancel pendings
   // when filled legs are in loss and worst leg is adverse by >= N points (stops adding into a bad fade).
   bool   pending_ladder_abort_enabled;
   double pending_ladder_abort_adverse_points;
   bool   pending_ladder_abort_require_negative_float;
   // When equity drawdown exceeds threshold, bias resolver toward more legs (recovery / scale-in).
   bool   recovery_leg_boost_enabled;
   double recovery_leg_boost_dd_pct_min;
   int    recovery_leg_boost_extra;
   // Native scalper on XAU* (symbol contains \"XAU\"): max legs for SELL only (0 = use full resolver n).
   int    gold_native_max_sell_legs;
   // When H1+H4 are not strongly aligned with trade direction, cap ladder size (0 = no cap). Clear trend uses full resolver band.
   int    native_legs_max_when_unclear;
   // \"Clear\" = both H1 and H4 trend_strength exceed trend_strength_atr_threshold × this factor in the trade direction.
   double native_legs_clear_trend_factor;
   // If true, when n>1 always probe+scale (never market all legs at once), even if staged_entry_enabled is false.
   bool   native_force_staged_scale_in;
   // If true, BB_BOUNCE native entries use BUY_LIMIT/SELL_LIMIT at the band price instead of market orders.
   bool   native_scalper_use_limit_entry;
   // V2: stricter H1 filter, multi-candle confirmation, candle pattern scoring
   bool   bounce_require_h1_direction;
   bool   bounce_require_bar0_confirm;
   int    bounce_min_candle_score;
   bool   bounce_require_liquidity_zone;
   // BB bounce: block fade when H1 and M15 both trend against the bounce (bull+↘ sell, bear+↗ buy).
   bool   bounce_block_htf_trend_align;
   // 0=LEGACY (h1_ok_buy/sell + bounce_block_htf). 1=BALANCED: buy ok unless (H1 bear AND M15 bear); sell ok unless (H1 bull AND M15 bull). 2=STRICT: buy ok only if neither bear; sell ok only if neither bull (fewest counter-trend fades).
   int    bounce_htf_bias;
   // Strategy Tester: when true, do not relax bounce ADX cap / H1 filter (backtest closer to live).
   bool   bounce_respect_adx_max_in_tester;
   bool   bounce_respect_h1_filter_in_tester;
   // V2: volume profile
   int    vp_lookback;
   int    vp_bins;
   // V2: breakout retest
   bool   breakout_use_retest;
   int    breakout_retest_max_bars;
   // V2: Fibonacci swing levels
   bool   fib_bias_enabled;
   bool   fib_tp_enabled;
   int    fib_lookback;
   // V2: RSI divergence
   bool   rsi_div_enabled;
   int    rsi_div_lookback;
   int    rsi_div_swing_bars;
   double rsi_div_min_rsi_diff;
   bool   rsi_div_draw_arrows;
   // V2: Parabolic SAR
   bool   psar_enabled;
   double psar_step;
   double psar_maximum;
   // V2: Signal Journal (SQLite)
   bool   journal_enabled;
   bool   journal_record_skips;
   bool   journal_import_trades;
   int    journal_import_depth_days;
   int    journal_stats_interval_sec;
};
ScalperConfig g_sc;

// H1 INDICATOR HANDLES — created once in EnsureIndicators(), read every OnTimer
int g_h_rsi  = INVALID_HANDLE;
int g_h_ma20 = INVALID_HANDLE;
int g_h_ma50 = INVALID_HANDLE;
int g_h_atr  = INVALID_HANDLE;
int g_h_bb   = INVALID_HANDLE;
int g_h_macd      = INVALID_HANDLE;
int g_h_osma_scalp = INVALID_HANDLE;  // M5 OsMA(3,10,16) — iOsMA buffer 0 = MACD−Signal directly (2.7.7)
int g_h_adx        = INVALID_HANDLE;

// H4 — native scalper higher-TF structure (EMA20/50 + ATR; same trend_strength formula as H1)
int g_h4_ma20 = INVALID_HANDLE;
int g_h4_ma50 = INVALID_HANDLE;
int g_h4_atr  = INVALID_HANDLE;
// H4 supplemental handles — RSI/BB/ADX for HH/LL context and structural gate checks
// Disabled by default; enable via FORGE_H4_RSI_GATE_ENABLED=1 / FORGE_H4_ADX_GATE_ENABLED=1 in .env
int g_h4_rsi  = INVALID_HANDLE;  // H4 RSI(14) — structural overbought/oversold; Cardwell Bear Resistance (RSI>60=avoid sell), Bull Support (RSI<40=avoid buy)
int g_h4_bb   = INVALID_HANDLE;  // H4 Bollinger Bands(20,2) — upper/lower for HH/LL zone context
int g_h4_adx  = INVALID_HANDLE;  // H4 ADX(14) — H4 trend strength; min gate prevents entries in structurally ranging H4

// M1 — optional entry confirmation / trigger (execution TF; H1/H4/regime stay bias-only)
int g_m1_ma20 = INVALID_HANDLE;
int g_m1_ma50 = INVALID_HANDLE;
int g_m1_atr  = INVALID_HANDLE;

// Regime snapshot from BRIDGE config.json (Phase C — mirrors AEGIS counter-trend policy for Python LENS scalper)
string g_regime_label = "";
double g_regime_confidence = 0;
bool   g_regime_apply_policy = false;
double g_regime_ct_min_conf = 0.55;

// V2: Volume Profile — POC + VWAP computed from M5 CopyTickVolume
double   g_poc_price = 0.0;
double   g_poc_strength = 0.0;
double   g_vwap_price = 0.0;
datetime g_vp_last_calc = 0;

// V2: Fibonacci swing retracement levels from M5 lookback
double   g_fib_high = 0.0;
double   g_fib_low  = 0.0;
double   g_fib_50   = 0.0;
double   g_fib_382  = 0.0;
double   g_fib_618  = 0.0;
datetime g_fib_last_calc = 0;

// V2: RSI divergence detection
string   g_rsi_div_type = "NONE";   // NONE | REG_BULL | REG_BEAR | HID_BULL | HID_BEAR
datetime g_rsi_div_last_calc = 0;
datetime g_rsi_div_last_arrow_bar = 0;

// V2: Parabolic SAR state tracking
int      g_h_psar = INVALID_HANDLE;
string   g_psar_state = "NONE";     // NONE | FLIP_BULL | FLIP_BEAR | BELOW | ABOVE
datetime g_psar_last_calc = 0;

// V2: Signal Journal (SQLite)
int      g_journal_db = INVALID_HANDLE;
datetime g_journal_last_import = 0;
datetime g_journal_last_stats = 0;
int      g_journal_signals_count = 0;

// V2: Order Block zones from LENS → ob_zones.json
double g_ob_zones_hi[6];
double g_ob_zones_lo[6];
int    g_ob_zone_count = 0;
string g_ob_zones_snapshot = "";

// V2: Breakout retest state machine
struct BreakoutRetest {
   bool     active;
   string   direction;
   double   breakout_level;
   double   sl;
   double   tp1, tp2;
   string   setup_type;
   datetime trigger_time;
   int      max_wait_bars;
   int      bars_waited;
};
BreakoutRetest g_retest;

// Cardwell SELL LIMIT cascade (2.7.7b): pending SELL LIMITs placed above entry to catch RSI bounce
// toward Bear Resistance (50-60) before continuation down. Cardwell: sell the bounce, not the breakout.
struct SellLimitEntry {
   ulong    ticket;       // pending order ticket (0 = none)
   int      group_id;     // market group this limit belongs to
   ulong    mkt_magic;    // magic of the market SELL (for SL-fired cancellation)
   datetime expiry;       // cancel if not filled by this time
   bool     active;
};
SellLimitEntry g_sell_limit_stack[10]; // 10 slots: [0]=L1 SELL LIMIT, [1]=L2 SELL LIMIT, [2-8]=SELL STOP continuation legs (up to 7, set by sell_stop_cont_legs), [9]=BUY LIMIT recovery

// MULTI-TIMEFRAME INDICATORS (M5, M15, M30) — for AURUM scalping context
struct TFIndicators {
   ENUM_TIMEFRAMES tf;
   string          label;
   int h_rsi, h_ma20, h_ma50, h_atr, h_bb, h_macd, h_adx;
};
TFIndicators g_mtf[3];  // M5, M15, M30

// GROUP TRACKING — in-memory state for TP1 partial close + BE move
// Each group has a unique magic = MagicNumber + group_id
struct TradeGroup {
   int    id;
   string direction;
   double tp1, tp2, tp3;
   double tp1_close_pct;
   bool   tp1_hit;
   bool   tp2_hit;   // set when all TP2 runners are modified to target TP3
   bool   be_moved;
   bool   move_be_on_tp1;
   int    magic_offset;  // magic + id to differentiate groups
   // Native scalper staged scale-in (optional); inactive when staging_active=false.
   bool   staging_active;
   bool   had_positions;
   string scalper_setup;
   int    legs_planned;
   int    next_staged_leg_i;
   double staged_sl;
   double staged_lot;
   bool   staged_is_breakout;
   int    staged_tp1_legs;
   double staged_anchor;
   datetime staged_next_add;
   // Post-TP1 ladder context (2.7.10 Day 2) — stored at entry, consumed by ArmPostTP1Ladder()
   double crash_low;   // bid (SELL) or ask (BUY) at market order execution
   double entry_atr;  // M5 ATR at entry — used for SELL STOP + BUY LIMIT placement offsets
};
TradeGroup g_groups[];

string JsonEscape(const string s);
bool JsonHasKey(const string &json, const string &key);
double ApplyNativeSlExtraBuffer(const bool is_buy, double sl, const double point);

struct EntryLeg {
   string order_type;      // AUTO | BUY_LIMIT | SELL_LIMIT | BUY_STOP | SELL_STOP | BUY_STOP_LIMIT | SELL_STOP_LIMIT
   double entry_price;     // trigger/entry price
   double stoplimit_price; // required for *_STOP_LIMIT
   double tp;              // optional per-leg TP override
};

string NormalizeOrderType(string ot);
bool ParseEntryLegs(const string &json, const string &key, EntryLeg &legs[]);
bool SymbolSupportsOrderType(const string order_type);
bool PlaceOpenGroupLeg(
   const string direction,
   const EntryLeg &leg,
   const double lot_per_trade,
   const double sl,
   const double tp_default,
   const int group_magic,
   const int group_id,
   const int leg_index,
   const int leg_count,
   bool &ok,
   string &order_kind,
   string &fail_reason
);
double NormalizeLot(const double lot);
bool ValidateStops(const double entry, const double sl, const double tp, const ENUM_ORDER_TYPE type);
void RebuildGroups();
void ResetScalperSessionStateIfNeeded();
string DealCloseReasonHint(const long reason_code);
string BuildRecentClosedDealsJson(const int max_items = 40);
int ForgeResolveNumTrades(const int base_n, const int env_lo, const int env_hi, const bool env_active,
                          const string setup_type, const double regime_conf, const string regime_label,
                          const double lot_mult_trend, string &out_reason);
void ManageStagedNativeLegs();
void ManagePendingLadderAbort();
void ForgeRefreshScalperAnalytics();
bool SymbolIsGoldFamily();

// SYMBOL MATCHING — handles broker suffixes (XAUUSD vs XAUUSDm vs XAUUSD.r)
// Used to filter positions/orders to only those on the chart symbol
bool ChartSymbolMatches(const string sym) {
   if(sym == _Symbol) return true;
   int i = StringFind(sym, ".");
   string s2 = (i > 0) ? StringSubstr(sym, 0, i) : sym;
   i = StringFind(_Symbol, ".");
   string c2 = (i > 0) ? StringSubstr(_Symbol, 0, i) : _Symbol;
   if(s2 == c2) return true;
   // Broker suffix without dot: XAUUSDm, EURUSD.pro
   const int MIN_PREFIX = 5;
   if(StringLen(c2) >= MIN_PREFIX && StringFind(s2, c2) == 0) return true;
   if(StringLen(s2) >= MIN_PREFIX && StringFind(c2, s2) == 0) return true;
   return false;
}

// Chart symbol is gold spot/metal (XAU*), broker suffixes ok.
bool SymbolIsGoldFamily() {
   string s = _Symbol;
   StringToUpper(s);
   return (StringFind(s, "XAU") >= 0);
}

// Volume profile / Fib / RSI div / PSAR / OB zones + journal import (hot path also every 20 timer cycles).
void ForgeRefreshScalperAnalytics() {
   ComputeVolumeProfile();
   ComputeFibonacciSwing();
   DetectRSIDivergence();
   DetectPSARState();
   ReadOBZones();
   if(g_sc.journal_enabled) {
      JournalImportTrades();
      JournalComputeStats();
   }
}

//+------------------------------------------------------------------+
//| Expert initialisation                                             |
//+------------------------------------------------------------------+
int OnInit() {
   g_files_path = (FilesPath == "") ? "" : FilesPath;
   g_session_start_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   ApplyStartupMode();
   g_trade.SetExpertMagicNumber(MagicNumber);
   g_trade.SetDeviationInPoints(30);
   g_trade.SetTypeFilling(ORDER_FILLING_IOC);
   EventSetTimer(TimerSeconds);
   EnsureIndicators();
   EnsureMTFIndicators();
   if(g_h_rsi==INVALID_HANDLE || g_h_ma20==INVALID_HANDLE || g_h_ma50==INVALID_HANDLE || g_h_atr==INVALID_HANDLE
      || g_h4_ma20==INVALID_HANDLE || g_h4_ma50==INVALID_HANDLE || g_h4_atr==INVALID_HANDLE
      || g_h4_rsi==INVALID_HANDLE  || g_h4_bb==INVALID_HANDLE   || g_h4_adx==INVALID_HANDLE
      || g_m1_ma20==INVALID_HANDLE || g_m1_ma50==INVALID_HANDLE || g_m1_atr==INVALID_HANDLE)
      Print("FORGE: indicator handles unavailable (market closed?) — will retry on timer");
   // Print all path info for diagnostics
   Print("FORGE v", FORGE_VERSION, " initialised — magic=",MagicNumber,
         " datapath=",  TerminalInfoString(TERMINAL_DATA_PATH),
         " commonpath=",TerminalInfoString(TERMINAL_COMMONDATA_PATH),
         " balance=",   AccountInfoDouble(ACCOUNT_BALANCE));
   WriteBrokerInfo();
   InitScalperConfig();
   JournalInit();
   // Same live sync as OnTimer: BRIDGE config.json + analytics once at attach (not after 1s / 20 cycles).
   ReadConfig();
   ForgeRefreshScalperAnalytics();
   WriteMarketData();
   RebuildGroups();
   g_scalper_mode = ScalperMode;
   if(g_scalper_mode != "NONE") {
      Print("FORGE: Native scalper mode = ", g_scalper_mode);
      PrintFormat("FORGE: warmup enabled — Live M15 bars=%d, extra Sec=%d, ScalperTesterWarmupM5Bars=%d, ScalperTesterWarmupSimCapMinutes=%d (MTF buffers always required first)",
                  ScalperLiveWarmupM15Bars, ScalperWarmupSeconds, ScalperTesterWarmupM5Bars, ScalperTesterWarmupSimCapMinutes);
   }
   if(MQLInfoInteger(MQL_TESTER) != 0) {
      Print("FORGE: Strategy Tester — InputMode=", g_mode, " ScalperMode=", g_scalper_mode,
            " — native entries need ScalperMode≠NONE and InputMode≠WATCH (SCALPER/HYBRID/SIGNAL all call the scalper).");
      if(g_scalper_mode == "NONE")
         Print("FORGE TESTER: ScalperMode is NONE — no native scalper. Set DUAL, BB_BOUNCE, or BB_BREAKOUT.");
      if(g_mode == "WATCH")
         Print("FORGE TESTER: InputMode WATCH — OnTick exits before CheckNativeScalperSetups. Use SCALPER or HYBRID.");
      Print("FORGE TESTER: max spread / London–NY session / sentinel_active gates are not applied in Tester.");
      Print("FORGE TESTER: native scalper uses relaxed thresholds + no H1/H4 direction gate + no M1 gate + no session cap/cooldown so backtests show fills (live stays strict).");
   }
   g_forge_init_gmt = TimeGMT();
   g_warmup_m5_time_ref = 0;
   g_warmup_m5_rollover_count = 0;
   g_warmup_m15_time_ref = 0;
   g_warmup_m15_rollover_count = 0;
   g_scalper_warmup_ready_logged = false;
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) {
   EventKillTimer();
   IndicatorRelease(g_h_rsi);
   IndicatorRelease(g_h_ma20);
   IndicatorRelease(g_h_ma50);
   IndicatorRelease(g_h_atr);
   IndicatorRelease(g_h_bb);
   IndicatorRelease(g_h_macd);
   IndicatorRelease(g_h_adx);
   IndicatorRelease(g_h4_ma20);
   IndicatorRelease(g_h4_ma50);
   IndicatorRelease(g_h4_atr);
   IndicatorRelease(g_h4_rsi);
   IndicatorRelease(g_h4_bb);
   IndicatorRelease(g_h4_adx);
   IndicatorRelease(g_m1_ma20);
   IndicatorRelease(g_m1_ma50);
   IndicatorRelease(g_m1_atr);
   for(int i = 0; i < 3; i++) {
      IndicatorRelease(g_mtf[i].h_rsi);
      IndicatorRelease(g_mtf[i].h_ma20);
      IndicatorRelease(g_mtf[i].h_ma50);
      IndicatorRelease(g_mtf[i].h_atr);
      IndicatorRelease(g_mtf[i].h_bb);
      IndicatorRelease(g_mtf[i].h_macd);
      IndicatorRelease(g_mtf[i].h_adx);
   }
   JournalClose();
   Print("FORGE deinitialised — reason=", reason);
}

void ApplyStartupMode() {
   string m = InputMode;
   StringTrimLeft(m);
   StringTrimRight(m);
   if(m == "OFF" || m == "WATCH" || m == "SIGNAL" || m == "SCALPER" || m == "HYBRID")
      g_mode = m;
   else {
      Print("FORGE: unknown InputMode '", InputMode, "' — using SIGNAL");
      g_mode = "SIGNAL";
   }
}

void EnsureIndicators() {
   if(g_h_rsi != INVALID_HANDLE && g_h_ma20 != INVALID_HANDLE && g_h_ma50 != INVALID_HANDLE
      && g_h_atr != INVALID_HANDLE && g_h_bb != INVALID_HANDLE && g_h_macd != INVALID_HANDLE
      && g_h_adx != INVALID_HANDLE
      && g_h4_ma20 != INVALID_HANDLE && g_h4_ma50 != INVALID_HANDLE && g_h4_atr != INVALID_HANDLE
      && g_m1_ma20 != INVALID_HANDLE && g_m1_ma50 != INVALID_HANDLE && g_m1_atr != INVALID_HANDLE)
      return;
   IndicatorRelease(g_h_rsi);  g_h_rsi = INVALID_HANDLE;
   IndicatorRelease(g_h_ma20); g_h_ma20 = INVALID_HANDLE;
   IndicatorRelease(g_h_ma50); g_h_ma50 = INVALID_HANDLE;
   IndicatorRelease(g_h_atr);  g_h_atr = INVALID_HANDLE;
   IndicatorRelease(g_h_bb);   g_h_bb = INVALID_HANDLE;
   IndicatorRelease(g_h_macd);       g_h_macd = INVALID_HANDLE;
   IndicatorRelease(g_h_osma_scalp); g_h_osma_scalp = INVALID_HANDLE;
   IndicatorRelease(g_h_adx);        g_h_adx = INVALID_HANDLE;
   IndicatorRelease(g_h4_ma20); g_h4_ma20 = INVALID_HANDLE;
   IndicatorRelease(g_h4_ma50); g_h4_ma50 = INVALID_HANDLE;
   IndicatorRelease(g_h4_atr);  g_h4_atr = INVALID_HANDLE;
   IndicatorRelease(g_m1_ma20); g_m1_ma20 = INVALID_HANDLE;
   IndicatorRelease(g_m1_ma50); g_m1_ma50 = INVALID_HANDLE;
   IndicatorRelease(g_m1_atr);  g_m1_atr = INVALID_HANDLE;
   g_h_rsi  = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE);
   g_h_ma20 = iMA(_Symbol, PERIOD_H1, 20, 0, MODE_EMA, PRICE_CLOSE);
   g_h_ma50 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_h_atr  = iATR(_Symbol, PERIOD_H1, 14);
   g_h_bb   = iBands(_Symbol, PERIOD_H1, 20, 0, 2.0, PRICE_CLOSE);
   g_h_macd       = iMACD(_Symbol, PERIOD_H1, 12, 26, 9, PRICE_CLOSE);
   g_h_osma_scalp = iOsMA(_Symbol, PERIOD_M5, g_sc.breakout_macd_fast, g_sc.breakout_macd_slow, g_sc.breakout_macd_signal, PRICE_CLOSE);
   g_h_adx        = iADX(_Symbol, PERIOD_H1, 14);
   g_h4_ma20 = iMA(_Symbol, PERIOD_H4, 20, 0, MODE_EMA, PRICE_CLOSE);
   g_h4_ma50 = iMA(_Symbol, PERIOD_H4, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_h4_atr  = iATR(_Symbol, PERIOD_H4, 14);
   g_h4_rsi  = iRSI(_Symbol, PERIOD_H4, 14, PRICE_CLOSE);
   g_h4_bb   = iBands(_Symbol, PERIOD_H4, 20, 0, 2.0, PRICE_CLOSE);
   g_h4_adx  = iADX(_Symbol, PERIOD_H4, 14);
   g_m1_ma20 = iMA(_Symbol, PERIOD_M1, 20, 0, MODE_EMA, PRICE_CLOSE);
   g_m1_ma50 = iMA(_Symbol, PERIOD_M1, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_m1_atr  = iATR(_Symbol, PERIOD_M1, 14);
}

void EnsureMTFIndicators() {
   g_mtf[0].tf = PERIOD_M5;  g_mtf[0].label = "m5";
   g_mtf[1].tf = PERIOD_M15; g_mtf[1].label = "m15";
   g_mtf[2].tf = PERIOD_M30; g_mtf[2].label = "m30";
   for(int i = 0; i < 3; i++) {
      if(g_mtf[i].h_rsi > 0) continue;  // already initialised (0 = uninitialised, INVALID_HANDLE = -1)
      g_mtf[i].h_rsi  = iRSI(_Symbol, g_mtf[i].tf, 14, PRICE_CLOSE);
      g_mtf[i].h_ma20 = iMA(_Symbol, g_mtf[i].tf, 20, 0, MODE_EMA, PRICE_CLOSE);
      g_mtf[i].h_ma50 = iMA(_Symbol, g_mtf[i].tf, 50, 0, MODE_EMA, PRICE_CLOSE);
      g_mtf[i].h_atr  = iATR(_Symbol, g_mtf[i].tf, 14);
      g_mtf[i].h_bb   = iBands(_Symbol, g_mtf[i].tf, 20, 0, 2.0, PRICE_CLOSE);
      g_mtf[i].h_macd = iMACD(_Symbol, g_mtf[i].tf, 12, 26, 9, PRICE_CLOSE);
      g_mtf[i].h_adx  = iADX(_Symbol, g_mtf[i].tf, 14);
   }
   if(g_h_psar == INVALID_HANDLE && g_sc.psar_enabled)
      g_h_psar = iSAR(_Symbol, PERIOD_M5, g_sc.psar_step, g_sc.psar_maximum);
}

string WriteMTFBlock(int idx) {
   double buf[1], buf2[1];
   double rsi  = (CopyBuffer(g_mtf[idx].h_rsi, 0,0,1,buf)==1)  ? buf[0] : 0;
   double ma20 = (CopyBuffer(g_mtf[idx].h_ma20,0,0,1,buf)==1)  ? buf[0] : 0;
   double ma50 = (CopyBuffer(g_mtf[idx].h_ma50,0,0,1,buf)==1)  ? buf[0] : 0;
   double atr  = (CopyBuffer(g_mtf[idx].h_atr, 0,0,1,buf)==1)  ? buf[0] : 0;
   double bb_m = (CopyBuffer(g_mtf[idx].h_bb,  0,0,1,buf)==1)  ? buf[0] : 0;
   double bb_u = (CopyBuffer(g_mtf[idx].h_bb,  1,0,1,buf)==1)  ? buf[0] : 0;
   double bb_l = (CopyBuffer(g_mtf[idx].h_bb,  2,0,1,buf)==1)  ? buf[0] : 0;
   // iMACD: buffer 0=main, 1=signal; no buffer 2. OsMA = main − signal.
   double macd = (CopyBuffer(g_mtf[idx].h_macd,0,0,1,buf)==1 && CopyBuffer(g_mtf[idx].h_macd,1,0,1,buf2)==1) ? (buf[0]-buf2[0]) : 0;
   double adx  = (CopyBuffer(g_mtf[idx].h_adx, 0,0,1,buf)==1)  ? buf[0] : 0;  // buffer 0 = ADX main
   string j = "{";
   j += "\"rsi_14\":" + DoubleToString(rsi, 1) + ",";
   j += "\"ema_20\":" + DoubleToString(ma20, 2) + ",";
   j += "\"ema_50\":" + DoubleToString(ma50, 2) + ",";
   j += "\"atr_14\":" + DoubleToString(atr, 2) + ",";
   j += "\"bb_upper\":" + DoubleToString(bb_u, 2) + ",";
   j += "\"bb_mid\":" + DoubleToString(bb_m, 2) + ",";
   j += "\"bb_lower\":" + DoubleToString(bb_l, 2) + ",";
   j += "\"macd_hist\":" + DoubleToString(macd, 5) + ",";
   j += "\"adx\":" + DoubleToString(adx, 1);
   j += "}";
   return j;
}

// Read JSON sibling to WriteJsonFileDual: Common Files first, then terminal-local Files.
bool ReadTextFileDual(const string rel_path, string &out_body) {
   out_body = "";
   string path = g_files_path + rel_path;
   int fh = FileOpen(path, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh != INVALID_HANDLE) {
      while(!FileIsEnding(fh)) out_body += FileReadString(fh);
      FileClose(fh);
      return true;
   }
   int err_c = GetLastError();
   fh = FileOpen(path, FILE_READ | FILE_TXT | FILE_ANSI);
   if(fh != INVALID_HANDLE) {
      while(!FileIsEnding(fh)) out_body += FileReadString(fh);
      FileClose(fh);
      Print("FORGE: read ", rel_path, " from terminal Files (COMMON open err=", err_c, ")");
      return true;
   }
   return false;
}

bool WriteJsonFileDual(const string filename, const string body) {
   int fh = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh != INVALID_HANDLE) {
      FileWriteString(fh, body);
      FileFlush(fh);
      FileClose(fh);
      return true;
   }
   int err1 = GetLastError();
   fh = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(fh != INVALID_HANDLE) {
      FileWriteString(fh, body);
      FileFlush(fh);
      FileClose(fh);
      Print("FORGE: ", filename, " via local Files (common err=", err1, ")");
      return true;
   }
   Print("FORGE: WRITE FAILED ", filename, " common=", err1, " local=", GetLastError());
   return false;
}

//+------------------------------------------------------------------+
//| OnTimer — main cycle                                              |
//+------------------------------------------------------------------+
void OnTimer() {
   g_cycle++;
   ResetScalperSessionStateIfNeeded();
   EnsureIndicators();
   ReadConfig();
   if(BrokerInfoEveryCycles > 0) {
      g_cycles_since_broker++;
      if(g_cycles_since_broker >= BrokerInfoEveryCycles) {
         g_cycles_since_broker = 0;
         WriteBrokerInfo();
      }
   }
   if(g_mode == "OFF") { WriteMarketData(); return; }
   ReadAndExecuteCommand();
   WriteMarketData();
   if(g_mode == "WATCH") WriteTickData();  // extra tick record
   WriteModeStatus();
   // Reload scalper config every 20 cycles (hot-reload without recompile)
   if(g_cycle % 20 == 0) {
      ReadScalperConfig();
      ForgeRefreshScalperAnalytics();
   }
}

//+------------------------------------------------------------------+
//| OnTick — real-time management                                     |
//+------------------------------------------------------------------+
void OnTick() {
   if(g_mode == "OFF") return;
   ResetScalperSessionStateIfNeeded();
   if(g_mode == "WATCH") { WriteTickData(); return; }
   ManageStagedNativeLegs();
   ManageOpenGroups();
   ManagePendingLadderAbort();
   // Pending ladder expiry + fill-detection (2.7.7b/2.7.10): all 5 slots
   { datetime _now = TimeTradeServer();
     for(int _si = 0; _si < 10; _si++) {
        if(!g_sell_limit_stack[_si].active) continue;
        bool _pending = OrderSelect(g_sell_limit_stack[_si].ticket);
        if(!_pending && _now < g_sell_limit_stack[_si].expiry) {
           // Order no longer pending before expiry — filled or cancelled externally
           g_sell_limit_stack[_si].active = false;
           PrintFormat("FORGE SCALPER: ladder slot[%d] ticket=%d no longer pending (filled or external cancel)",
                       _si, g_sell_limit_stack[_si].ticket);
        } else if(_now >= g_sell_limit_stack[_si].expiry) {
           if(_pending) g_trade.OrderDelete(g_sell_limit_stack[_si].ticket);
           g_sell_limit_stack[_si].active = false;
           PrintFormat("FORGE SCALPER: ladder slot[%d] ticket=%d expired", _si, g_sell_limit_stack[_si].ticket);
        }
     }
   }
   // Native scalper: check for setups on each tick
   if(g_scalper_mode != "NONE" && g_mode != "WATCH" && g_mode != "OFF")
      CheckNativeScalperSetups();
}

//+------------------------------------------------------------------+
//| Config reader                                                      |
//+------------------------------------------------------------------+
void ReadConfig() {
   string content = "";
   if(!ReadTextFileDual("config.json", content)) return;
   const bool in_tester = (MQLInfoInteger(MQL_TESTER) != 0);

   // Live: BRIDGE drives effective_mode / scalper_mode / regime_* from Python.
   // Tester: ignore those — stale config.json often has effective_mode=WATCH (circuit breaker) and
   // scalper_mode=NONE; applying them overrides EA Inputs and blocks native scalper backtests.
   if(!in_tester) {
      string mode = JsonGetString(content, "effective_mode");
      if(mode != "" && mode != g_mode) {
         Print("FORGE mode: ", g_mode, " -> ", mode);
         g_mode = mode;
      }
      string sm = JsonGetString(content, "scalper_mode");
      if(sm != "") {
         if(sm == "NONE" || sm == "BB_BOUNCE" || sm == "BB_BREAKOUT" || sm == "DUAL") {
            if(sm != g_scalper_mode) {
               Print("FORGE scalper: ", g_scalper_mode, " -> ", sm, " (from config.json)");
               g_scalper_mode = sm;
            }
         }
      }
   }

   double v;
   v = JsonGetDouble(content, "pending_entry_threshold_points");
   if(v > 0) g_sc.pending_entry_threshold_points = v;
   v = JsonGetDouble(content, "trend_strength_atr_threshold");
   if(v > 0) g_sc.trend_strength_atr_threshold = v;
   if(JsonHasKey(content, "breakout_buffer_points")) {
      v = JsonGetDouble(content, "breakout_buffer_points");
      if(v >= 0) g_sc.breakout_buffer_points = v;
   }

   if(!in_tester) {
      if(JsonHasKey(content, "regime_label"))
         g_regime_label = JsonGetString(content, "regime_label");
      else
         g_regime_label = "";
      if(JsonHasKey(content, "regime_confidence"))
         g_regime_confidence = JsonGetDouble(content, "regime_confidence");
      else
         g_regime_confidence = 0;
      if(JsonHasKey(content, "regime_apply_entry_policy"))
         g_regime_apply_policy = (JsonGetDouble(content, "regime_apply_entry_policy") >= 0.5);
      else
         g_regime_apply_policy = false;
      if(JsonHasKey(content, "regime_countertrend_min_confidence")) {
         v = JsonGetDouble(content, "regime_countertrend_min_confidence");
         if(v > 0) g_regime_ct_min_conf = v;
      } else
         g_regime_ct_min_conf = 0.55;
   } else {
      g_regime_label = "";
      g_regime_confidence = 0;
      g_regime_apply_policy = false;
      g_regime_ct_min_conf = 0.55;
   }
}

//+------------------------------------------------------------------+
//| Command reader + executor                                          |
//+------------------------------------------------------------------+
void ReadAndExecuteCommand() {
   string content = "";
   if(!ReadTextFileDual("command.json", content)) {
      if(g_cycle % 20 == 0)
         Print("FORGE: cannot read command.json (FILE_COMMON + terminal Files). ",
               "BRIDGE must write to the same folder FORGE uses. FilesPath=\"", g_files_path,
               "\" common=\"", TerminalInfoString(TERMINAL_COMMONDATA_PATH), "\"");
      return;
   }
   if(content == "") return;

   string ts = JsonGetString(content, "timestamp");
   string action = JsonGetString(content, "action");
   StringTrimLeft(action);
   StringTrimRight(action);
   StringToUpper(action);

   // Partial / torn read while BRIDGE atomically replaces command.json — do not ack timestamp
   if(action == "") return;

   if(ts != "" && ts == g_last_cmd_ts) return;

   // These belong in aurum_cmd / other BRIDGE queues, not FORGE execution — ignore quietly
   if(action == "MODE_CHANGE" || action == "HEALTH_CHECK" || action == "SHELL_EXEC" ||
      action == "AEB" || action == "AURUM_EXEC" || action == "OPEN_TRADE") {
      g_last_cmd_ts = ts;
      return;
   }

   g_last_cmd_ts = ts;
   Print("FORGE command: ", action);

   if(action == "OPEN_GROUP")       ExecuteOpenGroup(content);
   else if(action == "CLOSE_ALL")   ExecuteCloseAll();
   else if(action == "CLOSE_PCT")   ExecuteClosePct(content);
   else if(action == "MOVE_BE_ALL") ExecuteMoveBeAll();
   else if(action == "MODIFY_SL")   ExecuteModifySL(content);
   else if(action == "MODIFY_TP")   ExecuteModifyTP(content);
   else if(action == "CLOSE_GROUP")     ExecuteCloseGroup(content);
   else if(action == "CANCEL_GROUP_PENDING") ExecuteCancelGroupPending(content);
   else if(action == "CLOSE_GROUP_PCT") ExecuteCloseGroupPct(content);
   else if(action == "CLOSE_PROFITABLE") ExecuteCloseProfitable();
   else if(action == "CLOSE_LOSING")    ExecuteCloseLosing();
   else Print("FORGE: Unknown action — ", action);
}

//+------------------------------------------------------------------+
//| Open N trades as a group across entry ladder                       |
//+------------------------------------------------------------------+
void ExecuteOpenGroup(const string &json) {
   int    group_id      = (int)JsonGetDouble(json, "group_id");
   string direction     = JsonGetString(json,  "direction");
   double lot_per_trade = JsonGetDouble(json,  "lot_per_trade");
   double sl            = JsonGetDouble(json,  "sl");
   double tp1           = JsonGetDouble(json,  "tp1");
   double tp2           = JsonGetDouble(json,  "tp2");
   double tp1_close_pct = JsonGetDouble(json,  "tp1_close_pct");
   if(tp1_close_pct == 0) tp1_close_pct = 70;
   string mbe = JsonGetString(json, "move_be_on_tp1");
   bool   move_be = true;
   if(mbe == "false" || mbe == "0") move_be = false;
   else if(mbe == "true" || mbe == "1") move_be = true;

   EntryLeg legs[];
   ParseEntryLegs(json, "entry_legs", legs);
   int n = ArraySize(legs);
   if(n == 0) {
      // Backward-compatible path: build AUTO legs from entry_ladder/entry_low.
      double entries[];
      ParseDoubleArray(json, "entry_ladder", entries);
      n = ArraySize(entries);
      if(n == 0) {
         double single_entry = JsonGetDouble(json, "entry_low");
         if(single_entry == 0) {
            Print("FORGE: OPEN_GROUP aborted — entry_ladder/entry_legs empty and no entry_low");
            return;
         }
         ArrayResize(entries, 1);
         entries[0] = single_entry;
         n = 1;
      }
      ArrayResize(legs, n);
      for(int i = 0; i < n; i++) {
         legs[i].order_type = "AUTO";
         legs[i].entry_price = entries[i];
         legs[i].stoplimit_price = 0;
         legs[i].tp = 0;
      }
   }
   if(direction != "BUY" && direction != "SELL") {
      Print("FORGE: OPEN_GROUP aborted — bad direction '", direction, "'");
      return;
   }

   lot_per_trade = NormalizeLot(lot_per_trade);
   int opened = 0;
   int group_magic = MagicNumber + group_id;
   g_trade.SetExpertMagicNumber(group_magic);

   // Split TP targets: first tp1_close_pct% get TP1, remainder get TP2 (or TP1 if no TP2)
   // explicit int cast — fractional pct values are truncated by design.
   int tp1_count = (int)MathCeil(n * (int)tp1_close_pct / 100.0);  // e.g. 3 of 4 at 70%
   double tp2_price = (tp2 > 0) ? tp2 : tp1;  // fallback to TP1 if no TP2

   for(int i = 0; i < n; i++) {
      double tp_for_this = (i < tp1_count) ? tp1 : tp2_price;  // first N get TP1, rest get TP2
      string tp_label = (i < tp1_count) ? "TP1" : "TP2";
      if(legs[i].tp > 0) tp_for_this = legs[i].tp;
      bool ok = false;
      string order_kind = "UNKNOWN";
      string fail_reason = "";
      bool placed = PlaceOpenGroupLeg(
         direction,
         legs[i],
         lot_per_trade,
         sl,
         tp_for_this,
         group_magic,
         group_id,
         i,
         n,
         ok,
         order_kind,
         fail_reason
      );
      if(!placed) {
         Print(
            "FORGE: Skipped leg ", i+1, "/", n,
            " ", order_kind,
            " entry=", DoubleToString(legs[i].entry_price, _Digits),
            " reason=", fail_reason
         );
         continue;
      }
      if(ok) {
         opened++;
         Print(
            "FORGE: Opened trade ", i+1, "/", n,
            " ", order_kind,
            " entry=", DoubleToString(legs[i].entry_price, _Digits),
            " ", tp_label, "=", DoubleToString(tp_for_this,2),
            " ticket=", g_trade.ResultOrder()
         );
      } else {
         Print(
            "FORGE: Failed trade ", i+1,
            " ", order_kind,
            " entry=", DoubleToString(legs[i].entry_price, _Digits),
            " retcode=", g_trade.ResultRetcode()
         );
      }
      Sleep(100);
   }
   Print("FORGE: Group ", group_id, " TP split: ", tp1_count, " at TP1=", DoubleToString(tp1,2),
         ", ", n-tp1_count, " at TP2=", DoubleToString(tp2_price,2));

   // Register group
   int gi = ArraySize(g_groups);
   ArrayResize(g_groups, gi + 1);
   g_groups[gi].id            = group_id;
   g_groups[gi].direction     = direction;
   g_groups[gi].tp1           = tp1;
   g_groups[gi].tp2           = tp2;
   g_groups[gi].tp3           = 0;   // BRIDGE path — tp3 not available from JSON
   g_groups[gi].tp1_close_pct = tp1_close_pct;
   g_groups[gi].tp1_hit       = false;
   g_groups[gi].tp2_hit       = false;
   g_groups[gi].be_moved      = false;
   g_groups[gi].move_be_on_tp1 = move_be;
   g_groups[gi].magic_offset  = group_magic;
   g_groups[gi].staging_active = false;
   g_groups[gi].had_positions = false;
   g_groups[gi].scalper_setup = "";
   g_groups[gi].legs_planned = 0;
   g_groups[gi].next_staged_leg_i = 0;
   g_groups[gi].staged_sl = 0;
   g_groups[gi].staged_lot = 0;
   g_groups[gi].staged_is_breakout = false;
   g_groups[gi].staged_tp1_legs = 0;
   g_groups[gi].staged_anchor = 0;
   g_groups[gi].staged_next_add = 0;
   // crash_low/entry_atr: BRIDGE groups use current bid/ATR; native scalper groups set these at CheckScalperEntry
   g_groups[gi].crash_low = (direction == "SELL") ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   g_groups[gi].entry_atr = 0;  // BRIDGE path: ATR not available here; post-TP1 ladder disabled for BRIDGE groups
   int bridge_group_positions[];
   GetGroupPositions(group_magic, bridge_group_positions);
   g_groups[gi].had_positions = (ArraySize(bridge_group_positions) > 0);

   Print("FORGE: Group ", group_id, " opened — ", opened, "/", n, " trades");
   g_trade.SetExpertMagicNumber(MagicNumber);
}

//+------------------------------------------------------------------+
//| Staged native scale-in: add legs after min hold + favorable move  |
//+------------------------------------------------------------------+
void ManageStagedNativeLegs() {
   if(!g_sc.staged_entry_enabled && !g_sc.native_force_staged_scale_in) return;
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   datetime now = TimeCurrent();
   for(int gi = 0; gi < ArraySize(g_groups); gi++) {
      if(!g_groups[gi].staging_active) continue;
      if(g_groups[gi].legs_planned <= 0 || g_groups[gi].scalper_setup == "") {
         g_groups[gi].staging_active = false;
         continue;
      }
      if(g_groups[gi].next_staged_leg_i >= g_groups[gi].legs_planned) {
         g_groups[gi].staging_active = false;
         continue;
      }
      if(now < g_groups[gi].staged_next_add) continue;
      int gm = g_groups[gi].magic_offset;
      int pos[];
      GetGroupPositions(gm, pos);
      if(ArraySize(pos) == 0) {
         g_groups[gi].staging_active = false;
         continue;
      }
      double fav_req = g_sc.staged_add_min_favorable_points;
      if(fav_req > 0.0 && point > 0.0) {
         bool okf = false;
         if(g_groups[gi].direction == "BUY")
            okf = ((bid - g_groups[gi].staged_anchor) / point >= fav_req);
         else
            okf = ((g_groups[gi].staged_anchor - ask) / point >= fav_req);
         if(!okf) continue;
      }
      int i = g_groups[gi].next_staged_leg_i;
      double tp1g = g_groups[gi].tp1;
      double tp2p = (g_groups[gi].tp2 > 0) ? g_groups[gi].tp2 : tp1g;
      double tp_for_this = (i < g_groups[gi].staged_tp1_legs) ? tp1g : tp2p;
      string tp_label = (i < g_groups[gi].staged_tp1_legs) ? "TP1" : "TP2";
      string comment = "SCALP|" + g_groups[gi].scalper_setup + "|G" + IntegerToString(g_groups[gi].id) + "|" + tp_label;
      double lotv = g_groups[gi].staged_lot;
      double sl = g_groups[gi].staged_sl;
      g_trade.SetExpertMagicNumber(gm);
      bool okx = false;
      if(g_groups[gi].direction == "BUY") {
         if(ValidateStops(ask, sl, tp_for_this, ORDER_TYPE_BUY))
            okx = g_trade.Buy(lotv, _Symbol, ask, NormalizeDouble(sl, _Digits),
                              NormalizeDouble(tp_for_this, _Digits), comment);
      } else {
         if(ValidateStops(bid, sl, tp_for_this, ORDER_TYPE_SELL))
            okx = g_trade.Sell(lotv, _Symbol, bid, NormalizeDouble(sl, _Digits),
                               NormalizeDouble(tp_for_this, _Digits), comment);
      }
      g_trade.SetExpertMagicNumber(MagicNumber);
      if(!okx) {
         PrintFormat("FORGE STAGED: add leg failed group=%d idx=%d ret=%d",
                     g_groups[gi].id, i, (int)g_trade.ResultRetcode());
         g_groups[gi].staged_next_add = now + MathMax(5, g_sc.staged_add_interval_sec);
         continue;
      }
      g_groups[gi].next_staged_leg_i++;
      g_groups[gi].staged_next_add = now + MathMax(3, g_sc.staged_add_interval_sec);
      // Rolling anchor: each further add must re-prove favorable excursion from the last fill level.
      if(!g_sc.staged_favorable_from_entry_only) {
         if(g_groups[gi].direction == "BUY")
            g_groups[gi].staged_anchor = bid;
         else
            g_groups[gi].staged_anchor = ask;
      }
      PrintFormat("FORGE STAGED: group %d opened leg %d/%d",
                  g_groups[gi].id, g_groups[gi].next_staged_leg_i, g_groups[gi].legs_planned);
      if(g_groups[gi].next_staged_leg_i >= g_groups[gi].legs_planned)
         g_groups[gi].staging_active = false;
      Sleep(50);
   }
}

//+------------------------------------------------------------------+
//| Cancel unfilled pendings for a group magic when fills are losing   |
//| and price has moved adversely (OPEN_GROUP ladders, not native MKT).|
//+------------------------------------------------------------------+
void ManagePendingLadderAbort() {
   if(!g_sc.pending_ladder_abort_enabled) return;
   if(g_sc.pending_ladder_abort_adverse_points <= 0.0) return;
   static datetime s_last_abort_sec = 0;
   datetime now = TimeCurrent();
   if(now == s_last_abort_sec) return;
   s_last_abort_sec = now;
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(point <= 0) return;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   // Collect group magics that still have pending orders
   int magics[];
   ArrayResize(magics, 0);
   for(int oi = 0; oi < OrdersTotal(); oi++) {
      ulong ot = OrderGetTicket(oi);
      if(ot == 0 || !OrderSelect(ot)) continue;
      if(!ChartSymbolMatches(OrderGetString(ORDER_SYMBOL))) continue;
      int om = (int)OrderGetInteger(ORDER_MAGIC);
      if(om < MagicNumber || om >= MagicNumber + 10000) continue;
      bool dup = false;
      for(int k = 0; k < ArraySize(magics); k++) {
         if(magics[k] == om) { dup = true; break; }
      }
      if(!dup) {
         int ns = ArraySize(magics);
         ArrayResize(magics, ns + 1);
         magics[ns] = om;
      }
   }
   for(int mi = 0; mi < ArraySize(magics); mi++) {
      int gm = magics[mi];
      int pos_tix[];
      GetGroupPositions(gm, pos_tix);
      if(ArraySize(pos_tix) == 0) continue;
      double sum_profit = 0.0;
      double worst_adverse = 0.0;
      for(int pj = 0; pj < ArraySize(pos_tix); pj++) {
         if(!g_pos.SelectByTicket(pos_tix[pj])) continue;
         sum_profit += g_pos.Profit() + g_pos.Swap() + g_pos.Commission();
         double openp = g_pos.PriceOpen();
         double adv = 0.0;
         if(g_pos.PositionType() == POSITION_TYPE_BUY)
            adv = (openp - bid) / point;
         else
            adv = (ask - openp) / point;
         if(adv > worst_adverse) worst_adverse = adv;
      }
      bool float_gate = true;
      if(g_sc.pending_ladder_abort_require_negative_float)
         float_gate = (sum_profit < -0.01);
      if(!float_gate) continue;
      if(worst_adverse < g_sc.pending_ladder_abort_adverse_points) continue;
      int cancelled = 0;
      for(int oj = OrdersTotal() - 1; oj >= 0; oj--) {
         ulong ot = OrderGetTicket(oj);
         if(ot == 0 || !OrderSelect(ot)) continue;
         if(!ChartSymbolMatches(OrderGetString(ORDER_SYMBOL))) continue;
         if((int)OrderGetInteger(ORDER_MAGIC) != gm) continue;
         if(g_trade.OrderDelete(ot)) cancelled++;
      }
      if(cancelled > 0) {
         PrintFormat("FORGE PENDING ABORT: magic=%d cancelled=%d worst_adv=%.1f pts float=%.2f (thr=%.1f)",
                     gm, cancelled, worst_adverse, sum_profit, g_sc.pending_ladder_abort_adverse_points);
      }
   }
}

int CountGroupPendingOrders(int magic) {
   int count = 0;
   for(int i = 0; i < OrdersTotal(); i++) {
      ulong ot = OrderGetTicket(i);
      if(ot == 0 || !OrderSelect(ot)) continue;
      if(!ChartSymbolMatches(OrderGetString(ORDER_SYMBOL))) continue;
      if((int)OrderGetInteger(ORDER_MAGIC) == magic) count++;
   }
   return count;
}

int CancelGroupPendingOrders(int magic) {
   int cancelled = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      ulong ot = OrderGetTicket(i);
      if(ot == 0 || !OrderSelect(ot)) continue;
      if(!ChartSymbolMatches(OrderGetString(ORDER_SYMBOL))) continue;
      if((int)OrderGetInteger(ORDER_MAGIC) != magic) continue;
      if(g_trade.OrderDelete(ot)) cancelled++;
   }
   return cancelled;
}

void RemoveGroupAt(int index) {
   int n = ArraySize(g_groups);
   if(index < 0 || index >= n) return;
   for(int i = index; i < n - 1; i++)
      g_groups[i] = g_groups[i + 1];
   ArrayResize(g_groups, n - 1);
}

//+------------------------------------------------------------------+
//| Manage open groups: TP1 partial close + BE move                   |
//+------------------------------------------------------------------+
void ManageOpenGroups() {
   for(int gi = 0; gi < ArraySize(g_groups); gi++) {
      // Native scalper fast-lock ratchet:
      // once price moves enough in favor, tighten SL progressively (not too tight) to keep momentum gains
      // while allowing normal pullback "breathing room".
      int gm_lock = g_groups[gi].magic_offset;
      int pos_lock[];
      GetGroupPositions(gm_lock, pos_lock);
      if(ArraySize(pos_lock) > 0) {
         g_groups[gi].had_positions = true;
      } else {
         int pending_count = CountGroupPendingOrders(gm_lock);
         if(g_groups[gi].had_positions) {
            int cancelled = CancelGroupPendingOrders(gm_lock);
            PrintFormat("FORGE: Group %d closed — removed from lifecycle, cancelled %d orphan pending orders",
                        g_groups[gi].id, cancelled);
            RemoveGroupAt(gi);
            gi--;
            continue;
         }
         if(pending_count == 0 && !g_groups[gi].staging_active) {
            PrintFormat("FORGE: Group %d removed from lifecycle — no positions or pending orders",
                        g_groups[gi].id);
            RemoveGroupAt(gi);
            gi--;
            continue;
         }
      }
      int ratchet_updates = 0;
      if(ArraySize(pos_lock) > 0) {
         double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         double spread_pts_live = (point > 0) ? ((ask - bid) / point) : 0.0;
         int stops_level = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
         double min_dist = MathMax(stops_level * point, point);
         double atr_buf[1];
         double m5_atr_pts = 0.0;
         if(point > 0 && CopyBuffer(g_mtf[0].h_atr, 0, 0, 1, atr_buf) == 1)
            m5_atr_pts = MathMax(0.0, atr_buf[0] / point);
         double m5_adx_live = 0.0;
         if(CopyBuffer(g_mtf[0].h_adx, 0, 0, 1, atr_buf) == 1)
            m5_adx_live = atr_buf[0];
         double h1_ema20_live = 0.0, h1_ema50_live = 0.0, h1_atr_live = 0.0;
         double h4_ema20_live = 0.0, h4_ema50_live = 0.0, h4_atr_live = 0.0;
         const int h1_live_shift = (MQLInfoInteger(MQL_TESTER) != 0) ? 0 : 1;
         if(CopyBuffer(g_h_ma20, 0, h1_live_shift, 1, atr_buf) == 1) h1_ema20_live = atr_buf[0];
         if(CopyBuffer(g_h_ma50, 0, h1_live_shift, 1, atr_buf) == 1) h1_ema50_live = atr_buf[0];
         if(CopyBuffer(g_h_atr,  0, h1_live_shift, 1, atr_buf) == 1) h1_atr_live = atr_buf[0];
         if(CopyBuffer(g_h4_ma20,0, 0, 1, atr_buf) == 1) h4_ema20_live = atr_buf[0];
         if(CopyBuffer(g_h4_ma50,0, 0, 1, atr_buf) == 1) h4_ema50_live = atr_buf[0];
         if(CopyBuffer(g_h4_atr, 0, 0, 1, atr_buf) == 1) h4_atr_live = atr_buf[0];
         double h1_ts_live = (h1_ema20_live - h1_ema50_live) / MathMax(h1_atr_live, point);
         double h4_ts_live = (h4_ema20_live - h4_ema50_live) / MathMax(h4_atr_live, point);
         bool h1_bull_live = h1_ts_live > g_sc.trend_strength_atr_threshold;
         bool h1_bear_live = h1_ts_live < -g_sc.trend_strength_atr_threshold;
         bool h1_flat_live = !h1_bull_live && !h1_bear_live;
         bool h4_bull_live = h4_ts_live > g_sc.trend_strength_atr_threshold;
         bool h4_bear_live = h4_ts_live < -g_sc.trend_strength_atr_threshold;
         bool h4_flat_live = !h4_bull_live && !h4_bear_live;
         double trend_mag_live = MathMax(MathAbs(h1_ts_live), MathAbs(h4_ts_live));
         bool trend_dir_agree_live = (h1_bull_live && (h4_bull_live || h4_flat_live))
                                  || (h1_bear_live && (h4_bear_live || h4_flat_live))
                                  || (h4_bull_live && h1_flat_live)
                                  || (h4_bear_live && h1_flat_live);
         bool high_vol_trend_live = g_sc.high_vol_trend_guard_enabled
                                 && ((MQLInfoInteger(MQL_TESTER) == 0) || g_sc.high_vol_apply_in_tester)
                                 && (m5_adx_live >= g_sc.high_vol_adx_min)
                                 && trend_dir_agree_live
                                 && (trend_mag_live >= g_sc.high_vol_trend_strength_min);
         for(int pj = 0; pj < ArraySize(pos_lock); pj++) {
            if(!g_pos.SelectByTicket(pos_lock[pj])) continue;
            string cmt = g_pos.Comment();
            if(StringFind(cmt, "SCALP|") != 0) continue;  // only native scalper legs
            bool is_bounce = (StringFind(cmt, "SCALP|BB_BOUNCE|") == 0);
            bool is_breakout = (StringFind(cmt, "SCALP|BB_BREAKOUT|") == 0) || (StringFind(cmt, "SCALP|BB_BREAKOUT_RETEST|") == 0);
            datetime pos_time = (datetime)PositionGetInteger(POSITION_TIME);
            int held_sec = (int)MathMax(0, TimeCurrent() - pos_time);
            int min_hold = is_bounce ? g_sc.fast_lock_min_hold_sec_bounce : g_sc.fast_lock_min_hold_sec_breakout;
            if(is_breakout && high_vol_trend_live)
               min_hold += g_sc.high_vol_fast_lock_extra_hold_sec;
            if(held_sec < min_hold) continue;  // allow bounce/breakout room before ratcheting
            double open = g_pos.PriceOpen();
            double cur_sl = g_pos.StopLoss();
            double tp = g_pos.TakeProfit();
            double target_sl = cur_sl;
            double trigger_pts = MathMax(20.0, MathMax(g_sc.pending_entry_threshold_points * 0.55, m5_atr_pts * 1.00));
            double lock_pts = MathMax(1.5, trigger_pts * (is_bounce ? 0.06 : 0.10));
            double trail_pts = MathMax(12.0, MathMax(trigger_pts * (is_bounce ? 0.95 : 0.80), m5_atr_pts * (is_bounce ? 1.20 : 0.90)));
            if(is_breakout && high_vol_trend_live) {
               trigger_pts *= g_sc.high_vol_fast_lock_trigger_mult;
               trail_pts *= g_sc.high_vol_fast_lock_trail_mult;
               // Keep lock buffer conservative when volatility is elevated.
               lock_pts = MathMax(1.5, lock_pts * 0.85);
            }
            double breath = g_sc.fast_lock_breath_mult;
            if(breath < 0.75) breath = 0.75;
            if(breath > 2.50) breath = 2.50;
            trigger_pts *= breath;
            trail_pts *= breath;
            lock_pts *= MathPow(breath, 0.5);
            double min_profit_pts = MathMax(
               0.0,
               MathMax(g_sc.fast_lock_min_profit_points, spread_pts_live * g_sc.fast_lock_spread_guard_mult)
            );
            if(g_pos.PositionType() == POSITION_TYPE_BUY) {
               double moved_pts = (bid - open) / point;
               double tp1_dist = (g_groups[gi].tp1 > open) ? ((g_groups[gi].tp1 - open) / point) : 0.0;
               double progress_trigger = (tp1_dist > 0) ? (tp1_dist * (is_bounce ? 0.65 : 0.45)) : 0.0;
               if(moved_pts < MathMax(trigger_pts, progress_trigger)) continue;
               double lock_sl = open + (lock_pts * point);
               double trail_sl = bid - (trail_pts * point);
               target_sl = MathMax(lock_sl, trail_sl);
               target_sl = MathMax(target_sl, open + (min_profit_pts * point));
               double max_valid = bid - min_dist;
               if(target_sl > max_valid) target_sl = max_valid;
               if(target_sl <= open) continue;
               if(cur_sl > 0 && target_sl <= (cur_sl + point * 0.5)) continue;
            } else if(g_pos.PositionType() == POSITION_TYPE_SELL) {
               // Balanced SELL loss grace: defer management in early adverse moves.
               // This never widens SL; it only pauses ratchet/BE actions.
               if(g_sc.sell_loss_grace_sec > 0 && g_sc.sell_loss_grace_adverse_points > 0.0) {
                  double adverse_pts = (ask - open) / point;
                  if(adverse_pts >= g_sc.sell_loss_grace_adverse_points && held_sec < g_sc.sell_loss_grace_sec)
                     continue;
               }
               double moved_pts = (open - ask) / point;
               double tp1_dist = (open > g_groups[gi].tp1 && g_groups[gi].tp1 > 0) ? ((open - g_groups[gi].tp1) / point) : 0.0;
               // Sells were over-tightening in bounce conditions: wait for deeper progress before ratcheting.
               double progress_trigger = (tp1_dist > 0) ? (tp1_dist * (is_bounce ? 0.75 : 0.55)) : 0.0;
               if(moved_pts < MathMax(trigger_pts, progress_trigger)) continue;
               double lock_sl = open - (lock_pts * point);
               double trail_sl = ask + (trail_pts * point);
               target_sl = MathMin(lock_sl, trail_sl);
               target_sl = MathMin(target_sl, open - (min_profit_pts * point));
               double min_valid = ask + min_dist;
               if(target_sl < min_valid) target_sl = min_valid;
               if(target_sl >= open) continue;
               if(cur_sl > 0 && target_sl >= (cur_sl - point * 0.5)) continue;
            } else continue;
            if(g_trade.PositionModify(pos_lock[pj], NormalizeDouble(target_sl, _Digits), tp))
               ratchet_updates++;
         }
      }
      if(ratchet_updates > 0) {
         PrintFormat("FORGE SCALPER: group %d fast-lock SL ratchet updated=%d", g_groups[gi].id, ratchet_updates);
      }

      if(g_groups[gi].tp1_hit) continue;  // already processed TP1
      double tp1 = g_groups[gi].tp1;
      string dir = g_groups[gi].direction;
      int    gm  = g_groups[gi].magic_offset;
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      bool tp1_reached = (dir=="BUY" && bid >= tp1) || (dir=="SELL" && ask <= tp1);
      if(!tp1_reached) continue;

      // TP1 hit — close tp1_close_pct of positions in this group
      int positions[];
      GetGroupPositions(gm, positions);
      int total = ArraySize(positions);
      if(total == 0) {
         // Native TP/SL closed the position before ManageOpenGroups ran this tick.
         // Still arm the post-TP1 ladder — SELL STOP CONT is a new independent order.
         g_groups[gi].tp1_hit = true;
         ArmPostTP1Ladder(gi);
         continue;
      }
      int to_close = (int)MathCeil(total * g_groups[gi].tp1_close_pct / 100.0);
      int closed   = 0;
      for(int j = 0; j < total && closed < to_close; j++) {
         if(g_pos.SelectByTicket(positions[j])) {
            if(g_trade.PositionClose(positions[j])) closed++;
         }
      }
      g_groups[gi].tp1_hit = true;
      ArmPostTP1Ladder(gi);  // 2.7.10 Day 2: arm SELL STOP continuation (off by default: sell_stop_cont_enabled=false)
      Print("FORGE: Group ", g_groups[gi].id, " TP1 — closed ", closed, "/", total);

      if(g_groups[gi].move_be_on_tp1) {
         GetGroupPositions(gm, positions);  // refresh after closes
         double remaining_tp = (g_groups[gi].tp2 > 0) ? g_groups[gi].tp2 : tp1;
         for(int j = 0; j < ArraySize(positions); j++) {
            if(g_pos.SelectByTicket(positions[j])) {
               double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
               double spread = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
               double buffer = spread + (5.0 * point);
               double be = g_pos.PriceOpen();
               if(g_pos.PositionType() == POSITION_TYPE_BUY) be += buffer;
               else be -= buffer;
               // Move SL to breakeven + set TP to TP2 for remaining runners
               g_trade.PositionModify(positions[j], NormalizeDouble(be, _Digits), NormalizeDouble(remaining_tp, _Digits));
            }
         }
         g_groups[gi].be_moved = true;
         Print("FORGE: Group ", g_groups[gi].id, " remaining ", ArraySize(positions),
               " trades: SL→BE, TP→", DoubleToString(remaining_tp, 2));
      }
   }

   // ── TP3 staging pass ─────────────────────────────────────────────────────
   // After TP1 runners reach TP2, promote remaining positions to target TP3.
   // Allows scalper to ride in stages: capture TP2 exit, then let runners run
   // to TP3 rather than going naked. TP4 is intentionally omitted — scalpers
   // take TP3 and re-enter rather than holding for 4×ATR.
   // tp3=0 disables this (BRIDGE groups, bounce groups, breakout_tp3_atr_mult=0).
   for(int gi2 = 0; gi2 < ArraySize(g_groups); gi2++) {
      if(!g_groups[gi2].tp1_hit)  continue;   // TP1 not hit yet
      if(g_groups[gi2].tp2_hit)   continue;   // already staged to TP3
      if(g_groups[gi2].tp3 <= 0)  continue;   // TP3 not set for this group

      double tp2_price = g_groups[gi2].tp2;
      double tp3_price = g_groups[gi2].tp3;
      string dir2 = g_groups[gi2].direction;
      int    gm2  = g_groups[gi2].magic_offset;
      double bid2 = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask2 = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      // Check if TP2 has been reached (market has touched/crossed TP2 price)
      bool tp2_reached = (dir2 == "BUY" && bid2 >= tp2_price) || (dir2 == "SELL" && ask2 <= tp2_price);
      if(!tp2_reached) continue;

      // Promote runners to TP3
      int pos3[];
      GetGroupPositions(gm2, pos3);
      int promoted = 0;
      for(int j = 0; j < ArraySize(pos3); j++) {
         if(g_pos.SelectByTicket(pos3[j])) {
            double cur_sl = g_pos.StopLoss();
            if(g_trade.PositionModify(pos3[j], cur_sl, NormalizeDouble(tp3_price, _Digits)))
               promoted++;
         }
      }
      g_groups[gi2].tp2_hit = true;
      if(promoted > 0)
         PrintFormat("FORGE: Group %d TP2 reached — promoted %d runner(s) to TP3=%.2f",
                     g_groups[gi2].id, promoted, tp3_price);
   }
}

//+------------------------------------------------------------------+
//| Close all EA positions                                             |
//+------------------------------------------------------------------+
void ExecuteCloseAll() {
   // 1. Close filled positions
   int closed = 0;
   for(int i = PositionsTotal()-1; i >= 0; i--) {
      if(g_pos.SelectByIndex(i) && g_pos.Symbol() == _Symbol) {
         int pm = (int)g_pos.Magic();
         if(pm >= MagicNumber && pm < MagicNumber + 10000) {
            if(g_trade.PositionClose(g_pos.Ticket())) closed++;
         }
      }
   }
   // 2. Cancel pending orders (limits/stops)
   int cancelled = 0;
   for(int i = OrdersTotal()-1; i >= 0; i--) {
      ulong ot = OrderGetTicket(i);
      if(ot == 0) continue;
      if(!OrderSelect(ot)) continue;
      if(!ChartSymbolMatches(OrderGetString(ORDER_SYMBOL))) continue;
      long om = OrderGetInteger(ORDER_MAGIC);
      if(om >= MagicNumber && om < MagicNumber + 10000) {
         if(g_trade.OrderDelete(ot)) cancelled++;
      }
   }
   ArrayResize(g_groups, 0);
   Print("FORGE: CLOSE_ALL — closed ", closed, " positions, cancelled ", cancelled, " pending orders");
}

//+------------------------------------------------------------------+
//| Close pct% of all open EA positions                               |
//+------------------------------------------------------------------+
void ExecuteClosePct(const string &json) {
   double pct = JsonGetDouble(json, "pct");
   if(pct <= 0 || pct > 100) pct = 70;
   int all[];
   for(int i = 0; i < PositionsTotal(); i++) {
      if(g_pos.SelectByIndex(i) && g_pos.Symbol() == _Symbol) {
         int pm = (int)g_pos.Magic();
         if(pm >= MagicNumber && pm < MagicNumber + 10000) {
            int sz = ArraySize(all);
            ArrayResize(all, sz+1);
            all[sz] = (int)g_pos.Ticket();
         }
      }
   }
   int n = ArraySize(all);
   int to_close = (int)MathCeil(n * pct / 100.0);
   int closed = 0;
   for(int i = 0; i < n && closed < to_close; i++) {
      if(g_trade.PositionClose(all[i])) closed++;
   }
   Print("FORGE: CLOSE_PCT ", pct, "% — closed ", closed, "/", n);
}

//+------------------------------------------------------------------+
//| Move all EA positions SL to breakeven                             |
//+------------------------------------------------------------------+
void ExecuteMoveBeAll() {
   for(int i = 0; i < PositionsTotal(); i++) {
      if(g_pos.SelectByIndex(i) && g_pos.Symbol() == _Symbol) {
         int pm = (int)g_pos.Magic();
         if(pm >= MagicNumber && pm < MagicNumber + 10000) {
            double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
            double spread = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
            double buffer = spread + (5.0 * point);
            double be = g_pos.PriceOpen();
            if(g_pos.PositionType() == POSITION_TYPE_BUY) be += buffer;
            else be -= buffer;
            g_trade.PositionModify(g_pos.Ticket(), NormalizeDouble(be, _Digits), g_pos.TakeProfit());
         }
      }
   }
   Print("FORGE: MOVE_BE_ALL executed");
}

//+------------------------------------------------------------------+
//| Close all positions + pending orders for a specific group (magic)  |
//+------------------------------------------------------------------+
void ExecuteCloseGroup(const string &json) {
   int target_magic = (int)JsonGetDouble(json, "magic");
   if(target_magic <= 0) { Print("FORGE: CLOSE_GROUP aborted — invalid magic"); return; }
   int closed = 0;
   for(int i = PositionsTotal()-1; i >= 0; i--) {
      if(g_pos.SelectByIndex(i) && g_pos.Symbol() == _Symbol && (int)g_pos.Magic() == target_magic) {
         if(g_trade.PositionClose(g_pos.Ticket())) closed++;
      }
   }
   int cancelled = 0;
   for(int i = OrdersTotal()-1; i >= 0; i--) {
      ulong ot = OrderGetTicket(i);
      if(ot == 0 || !OrderSelect(ot)) continue;
      if(!ChartSymbolMatches(OrderGetString(ORDER_SYMBOL))) continue;
      if((int)OrderGetInteger(ORDER_MAGIC) == target_magic) {
         if(g_trade.OrderDelete(ot)) cancelled++;
      }
   }
   Print("FORGE: CLOSE_GROUP magic=", target_magic, " — closed ", closed, " positions, cancelled ", cancelled, " pending");
}

//+------------------------------------------------------------------+
//| Cancel only pending orders for a specific group (magic)          |
//+------------------------------------------------------------------+
void ExecuteCancelGroupPending(const string &json) {
   int target_magic = (int)JsonGetDouble(json, "magic");
   if(target_magic <= 0) { Print("FORGE: CANCEL_GROUP_PENDING aborted — invalid magic"); return; }
   int cancelled = 0;
   for(int i = OrdersTotal()-1; i >= 0; i--) {
      ulong ot = OrderGetTicket(i);
      if(ot == 0 || !OrderSelect(ot)) continue;
      if(!ChartSymbolMatches(OrderGetString(ORDER_SYMBOL))) continue;
      if((int)OrderGetInteger(ORDER_MAGIC) == target_magic) {
         if(g_trade.OrderDelete(ot)) cancelled++;
      }
   }
   Print("FORGE: CANCEL_GROUP_PENDING magic=", target_magic, " — cancelled ", cancelled, " pending");
}

//+------------------------------------------------------------------+
//| Close N% of positions in a specific group                          |
//+------------------------------------------------------------------+
void ExecuteCloseGroupPct(const string &json) {
   int target_magic = (int)JsonGetDouble(json, "magic");
   double pct = JsonGetDouble(json, "pct");
   if(target_magic <= 0) { Print("FORGE: CLOSE_GROUP_PCT aborted — invalid magic"); return; }
   if(pct <= 0 || pct > 100) pct = 70;
   int tickets[];
   for(int i = 0; i < PositionsTotal(); i++) {
      if(g_pos.SelectByIndex(i) && g_pos.Symbol() == _Symbol && (int)g_pos.Magic() == target_magic) {
         int sz = ArraySize(tickets);
         ArrayResize(tickets, sz+1);
         tickets[sz] = (int)g_pos.Ticket();
      }
   }
   int n = ArraySize(tickets);
   int to_close = (int)MathCeil(n * pct / 100.0);
   int closed = 0;
   for(int i = 0; i < n && closed < to_close; i++) {
      if(g_trade.PositionClose(tickets[i])) closed++;
   }
   Print("FORGE: CLOSE_GROUP_PCT magic=", target_magic, " ", pct, "% — closed ", closed, "/", n);
}

//+------------------------------------------------------------------+
//| Close only positions currently in profit                           |
//+------------------------------------------------------------------+
void ExecuteCloseProfitable() {
   int closed = 0;
   for(int i = PositionsTotal()-1; i >= 0; i--) {
      if(g_pos.SelectByIndex(i) && g_pos.Symbol() == _Symbol) {
         int pm = (int)g_pos.Magic();
         if(pm >= MagicNumber && pm < MagicNumber + 10000) {
            if(g_pos.Profit() + g_pos.Swap() + g_pos.Commission() > 0) {
               if(g_trade.PositionClose(g_pos.Ticket())) closed++;
            }
         }
      }
   }
   Print("FORGE: CLOSE_PROFITABLE — closed ", closed, " winning positions");
}

//+------------------------------------------------------------------+
//| Close only positions currently in loss                             |
//+------------------------------------------------------------------+
void ExecuteCloseLosing() {
   int closed = 0;
   for(int i = PositionsTotal()-1; i >= 0; i--) {
      if(g_pos.SelectByIndex(i) && g_pos.Symbol() == _Symbol) {
         int pm = (int)g_pos.Magic();
         if(pm >= MagicNumber && pm < MagicNumber + 10000) {
            if(g_pos.Profit() + g_pos.Swap() + g_pos.Commission() < 0) {
               if(g_trade.PositionClose(g_pos.Ticket())) closed++;
            }
         }
      }
   }
   if(closed > 0) g_scalper_last_loss_time = TimeGMT();
   Print("FORGE: CLOSE_LOSING — closed ", closed, " losing positions");
}

//+------------------------------------------------------------------+
//| Stage-comment matcher: returns true if comment contains "|TP<n>"   |
//+------------------------------------------------------------------+
bool CommentMatchesStage(const string comment, const int stage) {
   if(stage <= 0) return true;  // stage filter disabled
   string needle = "|TP" + IntegerToString(stage);
   return (StringFind(comment, needle) >= 0);
}

//+------------------------------------------------------------------+
//| Modify SL — optional ticket / tp_stage scope (see header docs)     |
//+------------------------------------------------------------------+
void ExecuteModifySL(const string &json) {
   double new_sl = JsonGetDouble(json, "sl");
   if(new_sl <= 0) { Print("FORGE: MODIFY_SL aborted — invalid sl"); return; }
   int target_magic   = (int)JsonGetDouble(json, "magic");
   ulong target_ticket = (ulong)JsonGetDouble(json, "ticket");
   int target_stage   = (int)JsonGetDouble(json, "tp_stage");
   bool scoped_magic  = (target_magic > 0);
   bool scoped_ticket = (target_ticket > 0);
   bool scoped_stage  = (target_stage >= 1 && target_stage <= 3);
   int modified = 0;
   int pending_modified = 0;
   for(int i = 0; i < PositionsTotal(); i++) {
      if(!g_pos.SelectByIndex(i) || g_pos.Symbol() != _Symbol) continue;
      ulong tk = g_pos.Ticket();
      int pm = (int)g_pos.Magic();
      bool in_scope = scoped_magic
                       ? (pm == target_magic)
                       : (pm >= MagicNumber && pm < MagicNumber + 10000);
      if(scoped_ticket && tk != target_ticket) in_scope = false;
      if(scoped_stage && !CommentMatchesStage(g_pos.Comment(), target_stage)) in_scope = false;
      if(!in_scope) continue;
      if(g_trade.PositionModify(tk, NormalizeDouble(new_sl, _Digits), g_pos.TakeProfit()))
         modified++;
   }
   // Also modify pending orders
   for(int i = OrdersTotal()-1; i >= 0; i--) {
      ulong ot = OrderGetTicket(i);
      if(ot == 0 || !OrderSelect(ot)) continue;
      if(!ChartSymbolMatches(OrderGetString(ORDER_SYMBOL))) continue;
      long om = OrderGetInteger(ORDER_MAGIC);
      bool in_scope = scoped_magic
                       ? ((int)om == target_magic)
                       : (om >= MagicNumber && om < MagicNumber + 10000);
      if(scoped_ticket && ot != target_ticket) in_scope = false;
      if(scoped_stage && !CommentMatchesStage(OrderGetString(ORDER_COMMENT), target_stage)) in_scope = false;
      if(!in_scope) continue;
      if(g_trade.OrderModify(ot, OrderGetDouble(ORDER_PRICE_OPEN),
         NormalizeDouble(new_sl, _Digits), OrderGetDouble(ORDER_TP),
         ORDER_TIME_GTC, 0)) {
         pending_modified++;
      }
   }
   string scope_tag = "";
   if(scoped_ticket) scope_tag += " ticket=" + IntegerToString((long)target_ticket);
   if(scoped_stage)  scope_tag += " stage=TP" + IntegerToString(target_stage);
   if(scoped_magic)  scope_tag += " magic=" + IntegerToString(target_magic);
   Print("FORGE: MODIFY_SL", scope_tag, " to ", DoubleToString(new_sl, _Digits),
         " — ", modified, " positions, ", pending_modified, " pending modified");
}

//+------------------------------------------------------------------+
//| Modify TP — optional ticket / tp_stage scope (see header docs)     |
//+------------------------------------------------------------------+
void ExecuteModifyTP(const string &json) {
   double new_tp = JsonGetDouble(json, "tp");
   if(new_tp <= 0) { Print("FORGE: MODIFY_TP aborted — invalid tp"); return; }
   int target_magic   = (int)JsonGetDouble(json, "magic");
   ulong target_ticket = (ulong)JsonGetDouble(json, "ticket");
   int target_stage   = (int)JsonGetDouble(json, "tp_stage");
   bool scoped_magic  = (target_magic > 0);
   bool scoped_ticket = (target_ticket > 0);
   bool scoped_stage  = (target_stage >= 1 && target_stage <= 3);
   int modified = 0;
   int pending_modified = 0;
   for(int i = 0; i < PositionsTotal(); i++) {
      if(!g_pos.SelectByIndex(i) || g_pos.Symbol() != _Symbol) continue;
      ulong tk = g_pos.Ticket();
      int pm = (int)g_pos.Magic();
      bool in_scope = scoped_magic
                       ? (pm == target_magic)
                       : (pm >= MagicNumber && pm < MagicNumber + 10000);
      if(scoped_ticket && tk != target_ticket) in_scope = false;
      if(scoped_stage && !CommentMatchesStage(g_pos.Comment(), target_stage)) in_scope = false;
      if(!in_scope) continue;
      if(g_trade.PositionModify(tk, g_pos.StopLoss(), NormalizeDouble(new_tp, _Digits)))
         modified++;
   }
   // Also modify pending orders
   for(int i = OrdersTotal()-1; i >= 0; i--) {
      ulong ot = OrderGetTicket(i);
      if(ot == 0 || !OrderSelect(ot)) continue;
      if(!ChartSymbolMatches(OrderGetString(ORDER_SYMBOL))) continue;
      long om = OrderGetInteger(ORDER_MAGIC);
      bool in_scope = scoped_magic
                       ? ((int)om == target_magic)
                       : (om >= MagicNumber && om < MagicNumber + 10000);
      if(scoped_ticket && ot != target_ticket) in_scope = false;
      if(scoped_stage && !CommentMatchesStage(OrderGetString(ORDER_COMMENT), target_stage)) in_scope = false;
      if(!in_scope) continue;
      if(g_trade.OrderModify(ot, OrderGetDouble(ORDER_PRICE_OPEN),
         OrderGetDouble(ORDER_SL), NormalizeDouble(new_tp, _Digits),
         ORDER_TIME_GTC, 0)) {
         pending_modified++;
      }
   }
   string scope_tag = "";
   if(scoped_ticket) scope_tag += " ticket=" + IntegerToString((long)target_ticket);
   if(scoped_stage)  scope_tag += " stage=TP" + IntegerToString(target_stage);
   if(scoped_magic)  scope_tag += " magic=" + IntegerToString(target_magic);
   Print("FORGE: MODIFY_TP", scope_tag, " to ", DoubleToString(new_tp, _Digits),
         " — ", modified, " positions, ", pending_modified, " pending modified");
}

string DealCloseReasonHint(const long reason_code) {
   if(reason_code == DEAL_REASON_TP) return "TP_HIT";
   if(reason_code == DEAL_REASON_SL) return "SL_HIT";
   return "MANUAL_CLOSE";
}

string BuildRecentClosedDealsJson(const int max_items) {
   int lim = (max_items > 0) ? max_items : 40;
   datetime to_time = TimeCurrent();
   datetime from_time = to_time - 172800; // last 48h
   if(!HistorySelect(from_time, to_time)) return "[]";
   int total = (int)HistoryDealsTotal();
   if(total <= 0) return "[]";

   string arr = "[";
   int added = 0;
   int d = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   for(int i = total - 1; i >= 0 && added < lim; i--) {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0) continue;
      string sym = HistoryDealGetString(deal, DEAL_SYMBOL);
      if(!ChartSymbolMatches(sym)) continue;
      long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY) continue;

      long pos_id = HistoryDealGetInteger(deal, DEAL_POSITION_ID);
      if(pos_id <= 0) continue;
      long reason = HistoryDealGetInteger(deal, DEAL_REASON);
      long magic = HistoryDealGetInteger(deal, DEAL_MAGIC);
      double close_price = HistoryDealGetDouble(deal, DEAL_PRICE);
      double profit = HistoryDealGetDouble(deal, DEAL_PROFIT)
                    + HistoryDealGetDouble(deal, DEAL_SWAP)
                    + HistoryDealGetDouble(deal, DEAL_COMMISSION);
      long t_unix = HistoryDealGetInteger(deal, DEAL_TIME);

      if(added > 0) arr += ",";
      arr += "{";
      arr += "\"deal_ticket\":" + IntegerToString((long)deal) + ",";
      arr += "\"position_ticket\":" + IntegerToString((long)pos_id) + ",";
      arr += "\"magic\":" + IntegerToString((int)magic) + ",";
      arr += "\"close_price\":" + DoubleToString(close_price, d) + ",";
      arr += "\"profit\":" + DoubleToString(profit, 2) + ",";
      arr += "\"reason_code\":" + IntegerToString((int)reason) + ",";
      arr += "\"close_reason\":\"" + DealCloseReasonHint(reason) + "\",";
      arr += "\"time_unix\":" + IntegerToString((long)t_unix);
      arr += "}";
      added++;
   }
   arr += "]";
   return arr;
}
//+------------------------------------------------------------------+
//| Write market_data.json
//+------------------------------------------------------------------+
void WriteMarketData() {
   string j = "{";
   j += "\"forge_version\":\"" + FORGE_VERSION + "\",";
   j += "\"symbol\":\"" + JsonEscape(_Symbol) + "\",";
   j += "\"hermes_version\":\"FORGE_1.2\",";
   j += "\"timestamp_utc\":\"" + JsonEscape(TimeToString(TimeGMT(), TIME_DATE|TIME_SECONDS)) + "Z\",";
   j += "\"timestamp_unix\":" + IntegerToString((long)TimeGMT()) + ",";
   if(MQLInfoInteger(MQL_TESTER) != 0)
      j += "\"strategy_tester\":true,";
   j += "\"server_time_unix\":" + IntegerToString((long)TimeCurrent()) + ",";
   j += "\"terminal_connected\":" + IntegerToString((int)TerminalInfoInteger(TERMINAL_CONNECTED)) + ",";
   j += "\"trade_allowed\":" + IntegerToString((int)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)) + ",";
   j += "\"symbol_trade_mode\":" + IntegerToString((int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE)) + ",";
   j += "\"digits\":" + IntegerToString((int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS)) + ",";
   j += "\"ea_cycle\":" + IntegerToString(g_cycle) + ",";
   j += "\"mode\":\"" + g_mode + "\",";
   j += "\"price\":{";
   j += "\"bid\":" + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_BID), 2) + ",";
   j += "\"ask\":" + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_ASK), 2) + ",";
   j += "\"spread_points\":" + DoubleToString((SymbolInfoDouble(_Symbol,SYMBOL_ASK)-SymbolInfoDouble(_Symbol,SYMBOL_BID))/_Point, 1);
   j += "},";
   // Account
   j += "\"account\":{";
   j += "\"balance\":"       + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2) + ",";
   j += "\"equity\":"        + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2) + ",";
   j += "\"margin\":"        + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN),2) + ",";
   j += "\"free_margin\":"   + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2) + ",";
   j += "\"margin_level\":"  + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_LEVEL),1) + ",";
   j += "\"open_positions_count\":" + IntegerToString(PositionsTotal()) + ",";
   double fp = 0;
   for(int i=0;i<PositionsTotal();i++) {
      if(g_pos.SelectByIndex(i))
         fp += g_pos.Profit() + g_pos.Swap() + g_pos.Commission();
   }
   j += "\"total_floating_pnl\":" + DoubleToString(fp,2) + ",";
   j += "\"session_start_balance\":" + DoubleToString(g_session_start_balance,2) + ",";
   j += "\"session_pnl\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE)-g_session_start_balance,2);
   j += "},";
   j += "\"forge_config\":{";
   j += "\"pending_entry_threshold_points\":" + DoubleToString(g_sc.pending_entry_threshold_points,2) + ",";
   j += "\"trend_strength_atr_threshold\":" + DoubleToString(g_sc.trend_strength_atr_threshold,4) + ",";
   j += "\"breakout_buffer_points\":" + DoubleToString(g_sc.breakout_buffer_points,2);
   j += "},";
   j += "\"volume_profile\":{";
   j += "\"poc_price\":" + DoubleToString(g_poc_price, 2) + ",";
   j += "\"poc_strength\":" + DoubleToString(g_poc_strength, 3) + ",";
   j += "\"vwap_price\":" + DoubleToString(g_vwap_price, 2) + ",";
   j += "\"fib_high\":" + DoubleToString(g_fib_high, 2) + ",";
   j += "\"fib_low\":" + DoubleToString(g_fib_low, 2) + ",";
   j += "\"fib_50\":" + DoubleToString(g_fib_50, 2) + ",";
   j += "\"fib_382\":" + DoubleToString(g_fib_382, 2) + ",";
   j += "\"fib_618\":" + DoubleToString(g_fib_618, 2);
   j += "},";
   j += "\"rsi_divergence\":\"" + g_rsi_div_type + "\",";
   j += "\"psar_state\":\"" + g_psar_state + "\",";
   // Indicators H1
   j += "\"indicators_h1\":{";
   double rsi_buf[1], ma20_buf[1], ma50_buf[1], atr_buf[1];
   double rsi_val  = (CopyBuffer(g_h_rsi, 0,0,1,rsi_buf)==1)  ? rsi_buf[0]  : 0;
   double ma20_val = (CopyBuffer(g_h_ma20,0,0,1,ma20_buf)==1) ? ma20_buf[0] : 0;
   double ma50_val = (CopyBuffer(g_h_ma50,0,0,1,ma50_buf)==1) ? ma50_buf[0] : 0;
   double atr_val  = (CopyBuffer(g_h_atr, 0,0,1,atr_buf)==1)  ? atr_buf[0]  : 0;
   double h1_bb_m  = (CopyBuffer(g_h_bb, 0,0,1,rsi_buf)==1)   ? rsi_buf[0]  : 0;
   double h1_bb_u  = (CopyBuffer(g_h_bb, 1,0,1,rsi_buf)==1)   ? rsi_buf[0]  : 0;
   double h1_bb_l  = (CopyBuffer(g_h_bb, 2,0,1,rsi_buf)==1)   ? rsi_buf[0]  : 0;
   double _h1m[1]; double h1_macd = (CopyBuffer(g_h_macd,0,0,1,rsi_buf)==1 && CopyBuffer(g_h_macd,1,0,1,_h1m)==1) ? (rsi_buf[0]-_h1m[0]) : 0;
   double h1_adx   = (CopyBuffer(g_h_adx, 0,0,1,rsi_buf)==1)  ? rsi_buf[0]  : 0;
   j += "\"rsi_14\":" + DoubleToString(rsi_val,1)  + ",";
   j += "\"ema_20\":"  + DoubleToString(ma20_val,2) + ",";
   j += "\"ema_50\":"  + DoubleToString(ma50_val,2) + ",";
   j += "\"atr_14\":" + DoubleToString(atr_val,2) + ",";
   j += "\"bb_upper\":" + DoubleToString(h1_bb_u,2) + ",";
   j += "\"bb_mid\":" + DoubleToString(h1_bb_m,2) + ",";
   j += "\"bb_lower\":" + DoubleToString(h1_bb_l,2) + ",";
   j += "\"macd_hist\":" + DoubleToString(h1_macd,5) + ",";
   j += "\"adx\":" + DoubleToString(h1_adx,1);
   j += "},";
   // H4 — structure / regime context (native scalper alignment)
   j += "\"indicators_h4\":{";
   double h4_ma20b[1], h4_ma50b[1], h4_atrb[1], h4_rsib[1], h4_bbb[1], h4_adxb[1];
   double h4_m20    = (CopyBuffer(g_h4_ma20, 0, 0, 1, h4_ma20b) == 1) ? h4_ma20b[0] : 0;
   double h4_m50    = (CopyBuffer(g_h4_ma50, 0, 0, 1, h4_ma50b) == 1) ? h4_ma50b[0] : 0;
   double h4_atr_v  = (CopyBuffer(g_h4_atr,  0, 0, 1, h4_atrb)  == 1) ? h4_atrb[0]  : 0;
   double h4_rsi_v  = (CopyBuffer(g_h4_rsi,  0, 0, 1, h4_rsib)  == 1) ? h4_rsib[0]  : 0;
   double h4_bb_m   = (CopyBuffer(g_h4_bb,   0, 0, 1, h4_bbb)   == 1) ? h4_bbb[0]   : 0;  // buffer 0 = middle
   double h4_bb_u   = (CopyBuffer(g_h4_bb,   1, 0, 1, h4_bbb)   == 1) ? h4_bbb[0]   : 0;  // buffer 1 = upper
   double h4_bb_l   = (CopyBuffer(g_h4_bb,   2, 0, 1, h4_bbb)   == 1) ? h4_bbb[0]   : 0;  // buffer 2 = lower
   double h4_adx_v  = (CopyBuffer(g_h4_adx,  0, 0, 1, h4_adxb)  == 1) ? h4_adxb[0]  : 0;  // buffer 0 = ADX line
   j += "\"ema_20\":" + DoubleToString(h4_m20,2)   + ",";
   j += "\"ema_50\":" + DoubleToString(h4_m50,2)   + ",";
   j += "\"atr_14\":" + DoubleToString(h4_atr_v,2) + ",";
   j += "\"rsi_14\":" + DoubleToString(h4_rsi_v,1) + ",";
   j += "\"bb_upper\":" + DoubleToString(h4_bb_u,2) + ",";
   j += "\"bb_mid\":" + DoubleToString(h4_bb_m,2)   + ",";
   j += "\"bb_lower\":" + DoubleToString(h4_bb_l,2) + ",";
   j += "\"adx_14\":" + DoubleToString(h4_adx_v,1);
   j += "},";
   // M1 — optional scalper confirmation context
   j += "\"indicators_m1\":{";
   double m1_m20b[1], m1_m50b[1], m1_atrb[1];
   double m1_m20 = (CopyBuffer(g_m1_ma20,0,0,1,m1_m20b)==1) ? m1_m20b[0] : 0;
   double m1_m50 = (CopyBuffer(g_m1_ma50,0,0,1,m1_m50b)==1) ? m1_m50b[0] : 0;
   double m1_atr_v = (CopyBuffer(g_m1_atr, 0,0,1,m1_atrb)==1) ? m1_atrb[0] : 0;
   j += "\"ema_20\":" + DoubleToString(m1_m20,2) + ",";
   j += "\"ema_50\":" + DoubleToString(m1_m50,2) + ",";
   j += "\"atr_14\":" + DoubleToString(m1_atr_v,2);
   j += "},";
   // Multi-timeframe indicators (M5, M15, M30)
   for(int ti = 0; ti < 3; ti++) {
      j += "\"indicators_" + g_mtf[ti].label + "\":" + WriteMTFBlock(ti) + ",";
   }
   // Open positions: ALL account positions (not chart-symbol filtered).
   // Include forge_managed so BRIDGE/ATHENA can distinguish FORGE vs manual.
   j += "\"open_positions\":[";
   bool first = true;
   int posForge = 0;
   for(int i=0;i<PositionsTotal();i++) {
      if(!g_pos.SelectByIndex(i)) continue;
      int pm = (int)g_pos.Magic();
      bool forgeManaged = (pm >= MagicNumber && pm < MagicNumber + 10000);
      if(forgeManaged) posForge++;
      if(!first) j += ","; first=false;
      j += "{";
      j += "\"ticket\":"       + IntegerToString(g_pos.Ticket()) + ",";
      j += "\"symbol\":\""     + JsonEscape(g_pos.Symbol()) + "\",";
      j += "\"type\":\""       + (g_pos.PositionType()==POSITION_TYPE_BUY?"BUY":"SELL") + "\",";
      j += "\"lots\":"         + DoubleToString(g_pos.Volume(),2) + ",";
      j += "\"open_price\":"   + DoubleToString(g_pos.PriceOpen(),2) + ",";
      j += "\"current_price\":" + DoubleToString(g_pos.PriceCurrent(),2) + ",";
      j += "\"sl\":"           + DoubleToString(g_pos.StopLoss(),2) + ",";
      j += "\"tp\":"           + DoubleToString(g_pos.TakeProfit(),2) + ",";
      j += "\"profit\":"       + DoubleToString(g_pos.Profit()+g_pos.Swap()+g_pos.Commission(),2) + ",";
      j += "\"magic\":"        + IntegerToString(pm) + ",";
      j += "\"forge_managed\":";
      j += forgeManaged ? "true" : "false";
      j += ",";
      // comment carries FORGE leg metadata: "FORGE|G<id>|<leg_index>|TP<stage>".
      // BRIDGE parses |TP<n> to backfill trade_positions.tp_stage at FILL.
      j += "\"comment\":\"" + JsonEscape(g_pos.Comment()) + "\"";
      j += "}";
   }
   j += "],\"open_positions_forge_count\":" + IntegerToString(posForge) + ",";
   // Pending orders: ALL limits/stops on this chart symbol (ATHENA). Previously we filtered
   // by FORGE magic only — that hid broker magic=0 or non-standard magics from the dashboard.
   j += "\"pending_orders\":[";
   first = true;
   int noc = (int)OrdersTotal();
   int pendForge = 0;
   for(int i = 0; i < noc; i++) {
      ulong ot = OrderGetTicket(i);
      if(ot == 0) continue;
      if(!OrderSelect(ot)) continue;
      string osym = OrderGetString(ORDER_SYMBOL);
      if(!ChartSymbolMatches(osym)) continue;
      long om = OrderGetInteger(ORDER_MAGIC);
      bool forgeManaged = (om >= MagicNumber && om < MagicNumber + 10000);
      if(forgeManaged) pendForge++;
      if(!first) j += ","; first = false;
      long otyp = OrderGetInteger(ORDER_TYPE);
      string otn = "OTHER";
      if(otyp == ORDER_TYPE_BUY_LIMIT) otn = "BUY_LIMIT";
      else if(otyp == ORDER_TYPE_SELL_LIMIT) otn = "SELL_LIMIT";
      else if(otyp == ORDER_TYPE_BUY_STOP) otn = "BUY_STOP";
      else if(otyp == ORDER_TYPE_SELL_STOP) otn = "SELL_STOP";
      else if(otyp == ORDER_TYPE_BUY_STOP_LIMIT) otn = "BUY_STOPLIMIT";
      else if(otyp == ORDER_TYPE_SELL_STOP_LIMIT) otn = "SELL_STOPLIMIT";
      j += "{";
      j += "\"ticket\":" + IntegerToString((long)ot) + ",";
      j += "\"symbol\":\"" + JsonEscape(osym) + "\",";
      j += "\"order_type\":\"" + otn + "\",";
      j += "\"volume\":" + DoubleToString(OrderGetDouble(ORDER_VOLUME_INITIAL),2) + ",";
      j += "\"price\":" + DoubleToString(OrderGetDouble(ORDER_PRICE_OPEN),_Digits) + ",";
      j += "\"sl\":" + DoubleToString(OrderGetDouble(ORDER_SL),_Digits) + ",";
      j += "\"tp\":" + DoubleToString(OrderGetDouble(ORDER_TP),_Digits) + ",";
      j += "\"magic\":" + IntegerToString((int)om) + ",";
      j += "\"forge_managed\":";
      j += forgeManaged ? "true" : "false";
      j += ",";
      j += "\"comment\":\"" + JsonEscape(OrderGetString(ORDER_COMMENT)) + "\"";
      j += "}";
   }
   j += "],\"pending_orders_forge_count\":" + IntegerToString(pendForge) + ",";
   j += "\"recent_closed_deals\":" + BuildRecentClosedDealsJson(40);
   j += "}";

   WriteJsonFileDual("market_data.json", j);
}

//+------------------------------------------------------------------+
//| Write tick_data.json (WATCH mode ML collection)                   |
//+------------------------------------------------------------------+
void WriteTickData() {
   if(!LogTicks) return;
   string j = "{";
   j += "\"timestamp_unix\":" + IntegerToString((long)TimeGMT()) + ",";
   j += "\"mode\":\"" + g_mode + "\",";
   j += "\"symbol\":\"" + JsonEscape(_Symbol) + "\",";
   j += "\"bid\":"  + DoubleToString(SymbolInfoDouble(_Symbol,SYMBOL_BID),2) + ",";
   j += "\"ask\":"  + DoubleToString(SymbolInfoDouble(_Symbol,SYMBOL_ASK),2) + ",";
   j += "\"spread\":" + DoubleToString((SymbolInfoDouble(_Symbol,SYMBOL_ASK)-SymbolInfoDouble(_Symbol,SYMBOL_BID))/_Point,1);
   j += "}";
   WriteJsonFileDual("tick_data.json", j);
}

//+------------------------------------------------------------------+
//| Write mode_status.json (ATHENA)                                   |
//+------------------------------------------------------------------+
void WriteModeStatus() {
   string j = "{\"mode\":\"" + g_mode + "\",";
   j += "\"scalper_mode\":\"" + g_scalper_mode + "\",";
   j += "\"warmup_ok\":" + (g_warmup_last_ok ? "true" : "false") + ",";
   j += "\"warmup_reason\":\"" + JsonEscape(g_warmup_last_reason) + "\",";
   j += "\"cycle\":" + IntegerToString(g_cycle) + ",";
   j += "\"open_groups\":" + IntegerToString(ArraySize(g_groups)) + ",";
   j += "\"pending_entry_threshold_points\":" + DoubleToString(g_sc.pending_entry_threshold_points,2) + ",";
   j += "\"trend_strength_atr_threshold\":" + DoubleToString(g_sc.trend_strength_atr_threshold,4) + ",";
   j += "\"breakout_buffer_points\":" + DoubleToString(g_sc.breakout_buffer_points,2) + ",";
   j += "\"timestamp\":\"" + JsonEscape(TimeToString(TimeGMT(),TIME_DATE|TIME_SECONDS)) + "Z\"}";
   WriteJsonFileDual("mode_status.json", j);
}

//+------------------------------------------------------------------+
//| Write broker_info.json — account type, broker, server time       |
//+------------------------------------------------------------------+
void WriteBrokerInfo() {
   string acct_type = AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO
                      ? "DEMO" : "LIVE";
   string j = "{";
   j += "\"account_type\":\"" + acct_type + "\",";
   j += "\"broker\":\"" + JsonEscape(AccountInfoString(ACCOUNT_COMPANY)) + "\",";
   j += "\"server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\",";
   j += "\"account_login\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + ",";
   j += "\"currency\":\"" + JsonEscape(AccountInfoString(ACCOUNT_CURRENCY)) + "\",";
   j += "\"leverage\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LEVERAGE)) + ",";
   j += "\"server_time\":\"" + JsonEscape(TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS)) + "\",";
   j += "\"server_time_unix\":" + IntegerToString((long)TimeCurrent()) + ",";
   j += "\"gmt_time\":\"" + JsonEscape(TimeToString(TimeGMT(),TIME_DATE|TIME_SECONDS)) + "Z\",";
   j += "\"chart_symbol\":\"" + JsonEscape(_Symbol) + "\",";
   j += "\"requested_mode\":\"" + JsonEscape(InputMode) + "\",";
   j += "\"effective_mode\":\"" + g_mode + "\",";
   j += "\"forge_version\":\"" + FORGE_VERSION + "\",";
   j += "\"scalper_mode\":\"" + g_scalper_mode + "\"";
   j += "}";
   if(WriteJsonFileDual("broker_info.json", j))
      Print("FORGE: broker_info.json — ", acct_type, " @ ", AccountInfoString(ACCOUNT_SERVER));
}

//+------------------------------------------------------------------+
string JsonEscape(const string s) {
   string out = "";
   int n = StringLen(s);
   for(int i = 0; i < n; i++) {
      ushort ch = StringGetCharacter(s, i);
      if(ch == '\\') out += "\\\\";
      else if(ch == '\"') out += "\\\"";
      else if(ch == '\r' || ch == '\n' || ch == '\t') out += " ";
      else out += StringSubstr(s, i, 1);
   }
   return out;
}

//+------------------------------------------------------------------+
//| NATIVE SCALPER ENGINE                                             |
//+------------------------------------------------------------------+
void InitScalperConfig() {
   // Set defaults (overridden by ReadScalperConfig if file exists)
   g_sc.bounce_enabled = true;
   g_sc.bounce_adx_max = 20;
   g_sc.bounce_rsi_buy_max = 35;
   g_sc.bounce_min_h1_trend = 0.3;
   g_sc.bounce_rsi_sell_min = 65;
   g_sc.bounce_bb_proximity_pct = 20;
   g_sc.bounce_reclaim_pct = 20;
   g_sc.bounce_lot_factor  = 1.0;
   g_sc.bounce_require_rejection_candle = true;
   g_sc.bounce_sl_atr_mult = 2.0;
   g_sc.bounce_tp1_close_pct = 40;
   g_sc.bounce_tp2_close_pct = 30;
   g_sc.breakout_enabled = true;
   g_sc.breakout_adx_min = 20;
   g_sc.breakout_adx_min_sell = 25;
   g_sc.breakout_require_rsi_declining_sell   = false;
   g_sc.breakout_rsi_decl_sell_adx_threshold = 40.0;
   g_sc.breakout_require_m30_bear_sell        = true;
   g_sc.breakout_m30_bear_adx_min             = 25.0;
   g_sc.breakout_require_h1_di_buy            = false;
   g_sc.breakout_counter_buy_adx_threshold    = 28.0;
   g_sc.breakout_require_h1_di_sell           = false;
   g_sc.breakout_require_h1_macd_sell         = false;
   g_sc.breakout_adx_min_sell_lookback_bars   = 6;
   g_sc.breakout_rsi_buy_min = 40;
   g_sc.breakout_rsi_sell_max = 60;
   g_sc.breakout_rsi_buy_ceil                = 70.0;
   g_sc.breakout_rsi_sell_floor              = 33.0;
   g_sc.breakout_adx_sell_floor_threshold    = 35.0;
   g_sc.breakout_rsi_sell_floor_weak_adx     = 36.0;
   g_sc.breakout_h1h4_crash_sell             = true;
   g_sc.breakout_h1h4_crash_sell_rsi_min    = 20.0;
   g_sc.h1h4_crash_sell_adx_max             = 40.0;
   g_sc.breakout_min_h1_bear_strength       = 0.2;
   g_sc.breakout_sell_inside_band_lot_factor = 0.25;
   g_sc.breakout_max_reentry_atr_ext = 0.0;
   g_sc.breakout_sl_atr_mult = 2.0;
   g_sc.breakout_tp1_atr_mult       = 1.0;
   g_sc.breakout_tp1_buy_atr_mult   = 0.0;  // 0 = use breakout_tp1_atr_mult
   g_sc.breakout_tp1_sell_atr_mult  = 0.0;  // 0 = use breakout_tp1_atr_mult
   g_sc.breakout_tp2_atr_mult = 1.5;
   g_sc.breakout_tp3_atr_mult = 2.5;
   g_sc.breakout_tp4_atr_mult = 4.0;
   g_sc.breakout_tp1_close_pct = 40;
   g_sc.breakout_require_m15 = true;
   g_sc.breakout_move_be = true;
   g_sc.fast_lock_min_hold_sec_bounce = 45;
   g_sc.fast_lock_min_hold_sec_breakout = 50;
   g_sc.max_spread_points = 25;
   g_sc.max_open_groups = 2;
   g_sc.max_trades_per_session = 3;
   g_sc.loss_cooldown_sec = 300;
   // 2.7.7 defaults
   g_sc.session_ny_sell_cutoff_utc      = 17;
   g_sc.session_london_sell_cutoff_utc  = 0;
   g_sc.breakout_require_macd_sell      = true;
   g_sc.breakout_require_macd_buy       = false;
   g_sc.breakout_macd_fast              = 3;
   g_sc.breakout_macd_slow              = 10;
   g_sc.breakout_macd_signal            = 16;
   g_sc.breakout_adx_lot_use_m15        = true;
   g_sc.breakout_adx_lot_mid_threshold      = 35.0;
   g_sc.breakout_adx_lot_high_threshold     = 45.0;
   g_sc.breakout_adx_lot_factor_mid         = 0.25;
   g_sc.breakout_adx_lot_factor_high        = 0.125;
   g_sc.breakout_adx_sell_block_threshold   = 55.0;
   g_sc.breakout_sell_limit_enabled         = true;
   g_sc.breakout_sell_limit_atr_mult        = 0.4;
   g_sc.breakout_sell_limit_lot_factor      = 0.125;
   g_sc.breakout_sell_limit_expiry_bars     = 6;
   g_sc.breakout_sell_limit_l2_enabled      = true;
   g_sc.breakout_sell_limit_l2_atr_mult     = 0.65;
   g_sc.breakout_sell_limit_l2_lot_factor   = 0.125;
   // SELL STOP continuation — off by default; enable via FORGE_SELL_STOP_CONT_ENABLED=1
   g_sc.sell_stop_cont_enabled       = false;
   g_sc.sell_stop_cont_atr_mult      = 0.40;
   g_sc.sell_stop_cont_lot_factor    = 1.0;   // full lot — cascade is a confirmed continuation entry
   g_sc.sell_stop_cont_tp_atr_mult   = 1.5;   // ~9pts at ATR=6 — captures the continuation leg
   g_sc.sell_stop_cont_expiry_bars   = 2;     // 10 min — scalpers don't wait; if no fill in 10min, dead
   g_sc.sell_stop_cont_min_rsi       = 25.0;
   g_sc.sell_stop_cont_legs          = 5;     // 5 legs = same as typical ADX-tiered primary entry
   // BUY LIMIT recovery — off by default; enable via FORGE_BUY_LIMIT_RECOVERY_ENABLED=1
   g_sc.buy_limit_recovery_enabled      = false;
   g_sc.buy_limit_recovery_min_rsi      = 35.0;  // Cardwell Bull Support zone threshold
   g_sc.buy_limit_recovery_lot_factor   = 0.25;
   g_sc.buy_limit_recovery_expiry_bars  = 4;     // 20 min — stale recovery limits become losing longs
   g_sc.buy_limit_recovery_sl_atr_mult  = 1.0;   // SL below crash low by 1 ATR
   // H4 supplemental gates — off by default; enable via .env + scalper_config.json
   g_sc.h4_rsi_gate_enabled  = false;
   g_sc.h4_rsi_sell_max      = 60.0;  // Cardwell Bear Resistance ceiling
   g_sc.h4_rsi_buy_min       = 40.0;  // Cardwell Bull Support floor
   g_sc.h4_adx_gate_enabled  = false;
   g_sc.h4_adx_min_sell      = 20.0;
   g_sc.h4_adx_min_buy       = 20.0;
   // Init SELL LIMIT stack (all 5 slots — [2][3]=SELL STOP scale-in, [4]=Day 3 BUY LIMIT)
   for(int _si = 0; _si < 10; _si++) {
      g_sell_limit_stack[_si].ticket   = 0;
      g_sell_limit_stack[_si].group_id = 0;
      g_sell_limit_stack[_si].mkt_magic = 0;
      g_sell_limit_stack[_si].expiry   = 0;
      g_sell_limit_stack[_si].active   = false;
   }
   g_sc.post_sl_cooldown_sec          = 3600;
   g_sc.breakout_near_floor_lot_factor = 0.25;
   g_sc.same_direction_stack_lot_factor = 0.25;
   g_sc.london_start = 0;
   g_sc.london_end = 24;
   g_sc.ny_start = 0;
   g_sc.ny_end = 24;
   g_sc.skip_asian  = false;
   g_sc.skip_london = false;
   g_sc.skip_ny     = false;
   g_sc.dd_tight_tp_atr = 0.8;
   g_sc.sentinel_min_threshold = 30;
   g_sc.news_filter_enabled         = true;
   g_sc.news_filter_currencies      = "USD,EUR,GBP";
   g_sc.news_filter_low_before      = 5;
   g_sc.news_filter_low_after       = 5;
   g_sc.news_filter_medium_before   = 10;
   g_sc.news_filter_medium_after    = 15;
   g_sc.news_filter_high_before     = 20;
   g_sc.news_filter_high_after      = 30;
   g_sc.news_filter_special         = "Non-Farm:30,60+FOMC:40,45+CPI:50,55";
   g_sc.news_filter_hard_floor_min  = 5;
   g_sc.news_filter_tighten_pct     = 0.50;
   g_sc.news_filter_block_pct       = 0.85;
   g_sc.news_filter_tighten_rsi_buy = 65.0;
   g_sc.news_filter_tighten_rsi_sell= 38.0;
   g_sc.news_filter_refresh_sec     = 900;
   g_sc.news_filter_apply_in_tester = true;
   g_sc.pending_entry_threshold_points = PendingEntryThresholdPoints;
   g_sc.trend_strength_atr_threshold = TrendStrengthAtrThreshold;
   g_sc.breakout_buffer_points = BreakoutBufferPoints;
   g_sc.high_vol_trend_guard_enabled = true;
   g_sc.high_vol_apply_in_tester = false;  // relaxed default — JSON overrides for live; prevents silent trade block if config unreadable
   g_sc.high_vol_adx_min = 28.0;
   g_sc.high_vol_trend_strength_min = 0.60;
   g_sc.high_vol_disable_bounce = false;  // relaxed default — JSON overrides for live
   g_sc.high_vol_require_h1_h4_breakout_align = true;
   g_sc.high_vol_breakout_sl_boost = 1.25;
   g_sc.high_vol_fast_lock_extra_hold_sec = 30;
   g_sc.high_vol_fast_lock_trigger_mult = 1.35;
   g_sc.high_vol_fast_lock_trail_mult = 1.35;
   g_sc.fast_lock_min_profit_points = 12.0;
   g_sc.fast_lock_spread_guard_mult = 1.20;
   g_sc.fast_lock_breath_mult = 1.35;
   g_sc.adx_hysteresis_enabled = false;  // disabled — ADX 25-33 is routine XAUUSD, gate was blocking all BB bounces
   g_sc.adx_hysteresis_apply_in_tester = false;
   g_sc.adx_trend_enter = 35.0;
   g_sc.adx_trend_exit = 28.0;
   g_sc.sell_loss_grace_sec = 90;
   g_sc.sell_loss_grace_adverse_points = 20.0;
   g_sc.min_sl_atr_mult = 1.5;
   g_sc.min_rr = 1.5;
   g_sc.min_rr_floor = 1.5;
   g_sc.native_sl_extra_buffer_points = 5.0;
   g_sc.min_entry_atr = 3.5;
   g_sc.max_open_same_direction = 1;
   g_sc.entry_quality_bars = 3;
   g_sc.min_body_ratio = 0.40;
   g_sc.min_directional_bars = 2;
   g_sc.require_bb_expansion = true;
   g_sc.lot_sizing_source = "AUTO";
   g_sc.lot_inputs_override = false;
   g_sc.lot_fixed = (ScalperLot > 0.0) ? ScalperLot : 0.02;
   g_sc.lot_num_trades = MathMax(1, ScalperTrades);
   g_sc.lot_min_trades = 0;
   g_sc.lot_max_trades = 0;
   g_sc.staged_entry_enabled = true;
   g_sc.staged_initial_legs = 1;
   g_sc.staged_add_interval_sec = 25;
   g_sc.staged_add_min_favorable_points = 0;
   g_sc.staged_favorable_from_entry_only = false;
   g_sc.pending_ladder_abort_enabled = true;
   g_sc.pending_ladder_abort_adverse_points = 25.0;
   g_sc.pending_ladder_abort_require_negative_float = true;
   g_sc.recovery_leg_boost_enabled = false;
   g_sc.recovery_leg_boost_dd_pct_min = 1.0;
   g_sc.recovery_leg_boost_extra = 2;
   g_sc.gold_native_max_sell_legs = 2;
   g_sc.native_legs_max_when_unclear = 3;
   g_sc.native_legs_clear_trend_factor = 1.35;
   g_sc.native_force_staged_scale_in = true;
   g_sc.native_scalper_use_limit_entry = false;
   g_sc.bounce_require_h1_direction = true;
   g_sc.bounce_require_bar0_confirm = true;
   g_sc.bounce_min_candle_score = 1;
   g_sc.bounce_require_liquidity_zone = true;
   g_sc.bounce_block_htf_trend_align = false;
   g_sc.bounce_htf_bias = 1;
   g_sc.bounce_respect_adx_max_in_tester = false;
   g_sc.bounce_respect_h1_filter_in_tester = false;
   g_sc.vp_lookback = 100;
   g_sc.vp_bins = 50;
   g_sc.breakout_use_retest = true;
   g_sc.breakout_retest_max_bars = 6;
   g_sc.fib_bias_enabled = true;
   g_sc.fib_tp_enabled = true;
   g_sc.fib_lookback = 0;
   g_sc.rsi_div_enabled = true;
   g_sc.rsi_div_lookback = 20;
   g_sc.rsi_div_swing_bars = 3;
   g_sc.rsi_div_min_rsi_diff = 1.0;
   g_sc.rsi_div_draw_arrows = true;
   g_sc.psar_enabled = true;
   g_sc.psar_step = 0.02;
   g_sc.psar_maximum = 0.2;
   g_sc.tester_session_filter = false;
   g_sc.tester_allowed_sessions = "ALL";
   g_sc.tester_cooldown_enabled = true;
   g_sc.direction_cooldown_enabled = true;
   g_sc.direction_cooldown_bars = 6;
   g_sc.journal_enabled = true;
   g_sc.journal_record_skips = true;
   g_sc.journal_import_trades = true;
   g_sc.journal_import_depth_days = 30;
   g_sc.journal_stats_interval_sec = 300;
   g_retest.active = false;
   ReadScalperConfig();
}

// First `"key": { ... }` object with brace matching; empty if missing (lot_sizing block in scalper_config.json).
string JsonExtractBracedObject(const string &json, const string &key) {
   string search = "\"" + key + "\"";
   int kpos = StringFind(json, search);
   if(kpos < 0) return "";
   int p = kpos + StringLen(search);
   while(p < StringLen(json) && StringGetCharacter(json, p) <= 32) p++;
   if(p >= StringLen(json) || StringGetCharacter(json, p) != ':') return "";
   p++;
   while(p < StringLen(json) && StringGetCharacter(json, p) <= 32) p++;
   if(p >= StringLen(json) || StringGetCharacter(json, p) != '{') return "";
   int start = p;
   int depth = 0;
   for(; p < StringLen(json); p++) {
      ushort c = StringGetCharacter(json, p);
      if(c == '{') depth++;
      else if(c == '}') {
         depth--;
         if(depth == 0)
            return StringSubstr(json, start, p - start + 1);
      }
   }
   return "";
}

// Merge MT5 Inputs envelope (0 = leave bound from JSON); re-run whenever scalper JSON is unchanged so Inputs still apply.
void ApplyScalperLotInputOverrides() {
   bool input_env_touch = false;
   if(ScalperMinTrades >= 1) {
      g_sc.lot_min_trades = MathMax(1, MathMin(30, ScalperMinTrades));
      input_env_touch = true;
   }
   if(ScalperMaxTrades >= 1) {
      g_sc.lot_max_trades = MathMax(1, MathMin(30, ScalperMaxTrades));
      input_env_touch = true;
   }
   if(input_env_touch && (g_sc.lot_min_trades > 0 || g_sc.lot_max_trades > 0)) {
      int tlo2 = g_sc.lot_min_trades > 0 ? g_sc.lot_min_trades : 1;
      int thi2 = g_sc.lot_max_trades > 0 ? g_sc.lot_max_trades : 20;
      tlo2 = MathMax(1, MathMin(30, tlo2));
      thi2 = MathMax(1, MathMin(30, thi2));
      if(tlo2 > thi2) { int sw2 = tlo2; tlo2 = thi2; thi2 = sw2; }
      g_sc.lot_num_trades = MathMax(1, MathMin(30, (tlo2 + thi2) / 2));
   }
   // ScalperLot > 0 overrides scalper_config.json fixed_lot (0 = keep JSON value)
   if(ScalperLot > 0.0) g_sc.lot_fixed = ScalperLot;
   // SellInsideBandLotFactor input overrides scalper_config.json when in range (0, 1]
   if(SellInsideBandLotFactor > 0.0 && SellInsideBandLotFactor <= 1.0)
      g_sc.breakout_sell_inside_band_lot_factor = SellInsideBandLotFactor;
}

void ApplyNewsFilterInputOverrides() {
   if(!NewsFilterInputsOverride) return;
   g_sc.news_filter_enabled = NewsFilterEnabled;
   PrintFormat("FORGE NEWS FILTER: input override active — enabled=%s",
               g_sc.news_filter_enabled ? "true" : "false");
}

void ReadScalperConfig() {
   string content = "";
   if(!ReadTextFileDual("scalper_config.json", content)) {
      if(!g_scalper_config_missing_logged) {
         Print("FORGE: scalper_config.json not readable (copy to MT5 Common ",
               TerminalInfoString(TERMINAL_COMMONDATA_PATH), " or terminal Files; optional FilesPath input). ",
               "Lot/legs fall back to ScalperLot/ScalperTrades until the file is available.");
         g_scalper_config_missing_logged = true;
      }
      ApplyScalperLotInputOverrides();
      ApplyNewsFilterInputOverrides();
      return;
   }
   g_scalper_config_missing_logged = false;
   if(content == "") {
      ApplyScalperLotInputOverrides();
      ApplyNewsFilterInputOverrides();
      return;
   }
   bool json_changed = (content != g_scalper_config_snapshot);
   if(!json_changed) {
      ApplyScalperLotInputOverrides();
      ApplyNewsFilterInputOverrides();
      return;
   }
   g_scalper_config_snapshot = content;
   g_sc.lot_min_trades = 0;
   g_sc.lot_max_trades = 0;

   string lot_json = JsonExtractBracedObject(content, "lot_sizing");
   if(lot_json == "") lot_json = content;
   // Parse config values (use defaults if key missing)
   double v;
   v = JsonGetDouble(content, "adx_max");       if(v > 0) g_sc.bounce_adx_max = v;
   v = JsonGetDouble(content, "rsi_buy_max");    if(v > 0) g_sc.bounce_rsi_buy_max = v;
   v = JsonGetDouble(content, "rsi_sell_min");   if(v > 0) g_sc.bounce_rsi_sell_min = v;
   if(JsonHasKey(content, "bounce_lot_factor")) { v = JsonGetDouble(content, "bounce_lot_factor"); if(v > 0.0 && v <= 1.0) g_sc.bounce_lot_factor = v; }
   if(JsonHasKey(content, "bounce_min_h1_trend")) {
      v = JsonGetDouble(content, "bounce_min_h1_trend");
      if(v >= 0 && v <= 5.0) g_sc.bounce_min_h1_trend = v;
   }
   v = JsonGetDouble(content, "bb_proximity_pct");if(v > 0) g_sc.bounce_bb_proximity_pct = v;
   if(JsonHasKey(content, "bounce_reclaim_pct")) {
      v = JsonGetDouble(content, "bounce_reclaim_pct");
      if(v >= 0 && v <= 100) g_sc.bounce_reclaim_pct = v;
   }
   if(JsonHasKey(content, "bounce_require_rejection_candle")) {
      v = JsonGetDouble(content, "bounce_require_rejection_candle");
      g_sc.bounce_require_rejection_candle = (v >= 0.5);
   }
   v = JsonGetDouble(content, "adx_min");        if(v > 0) g_sc.breakout_adx_min = v;
   v = JsonGetDouble(content, "adx_min_sell");   if(v > 0) g_sc.breakout_adx_min_sell = v;
   v = JsonGetDouble(content, "rsi_buy_min");    if(v > 0) g_sc.breakout_rsi_buy_min = v;
   v = JsonGetDouble(content, "rsi_sell_max");   if(v > 0) g_sc.breakout_rsi_sell_max = v;
   string bounce_json = JsonExtractBracedObject(content, "bb_bounce");
   if(bounce_json != "") {
      if(JsonHasKey(bounce_json, "sl_atr_mult")) {
         v = JsonGetDouble(bounce_json, "sl_atr_mult");
         if(v >= 0.5 && v <= 5.0) g_sc.bounce_sl_atr_mult = v;
      }
      if(JsonHasKey(bounce_json, "bounce_block_htf_trend_align")) {
         v = JsonGetDouble(bounce_json, "bounce_block_htf_trend_align");
         g_sc.bounce_block_htf_trend_align = (v >= 0.5);
      }
      if(JsonHasKey(bounce_json, "bounce_htf_bias")) {
         string bm = JsonGetString(bounce_json, "bounce_htf_bias");
         StringTrimLeft(bm);
         StringTrimRight(bm);
         StringToUpper(bm);
         if(bm == "LEGACY") g_sc.bounce_htf_bias = 0;
         else if(bm == "STRICT") g_sc.bounce_htf_bias = 2;
         else g_sc.bounce_htf_bias = 1;
      }
      if(JsonHasKey(bounce_json, "bounce_respect_adx_max_in_tester")) {
         v = JsonGetDouble(bounce_json, "bounce_respect_adx_max_in_tester");
         g_sc.bounce_respect_adx_max_in_tester = (v >= 0.5);
      }
      if(JsonHasKey(bounce_json, "bounce_respect_h1_filter_in_tester")) {
         v = JsonGetDouble(bounce_json, "bounce_respect_h1_filter_in_tester");
         g_sc.bounce_respect_h1_filter_in_tester = (v >= 0.5);
      }
   }
   string breakout_json = JsonExtractBracedObject(content, "bb_breakout");
   if(breakout_json != "") {
      if(JsonHasKey(breakout_json, "sl_atr_mult")) {
         v = JsonGetDouble(breakout_json, "sl_atr_mult");
         if(v >= 0.5 && v <= 5.0) g_sc.breakout_sl_atr_mult = v;
      }
      // Direction-specific TP1 — BUY gets more room (confirmed uptrend), SELL tighter (catch fast dip)
      // 0 = fall back to breakout_tp1_atr_mult (backward compat). CHANGELOG: 2026-05-10.
      if(JsonHasKey(breakout_json, "tp1_buy_atr_mult")) { v = JsonGetDouble(breakout_json,"tp1_buy_atr_mult");  if(v > 0.0) g_sc.breakout_tp1_buy_atr_mult  = v; }
      if(JsonHasKey(breakout_json, "tp1_sell_atr_mult")){ v = JsonGetDouble(breakout_json,"tp1_sell_atr_mult"); if(v > 0.0) g_sc.breakout_tp1_sell_atr_mult = v; }
      if(JsonHasKey(breakout_json, "rsi_buy_ceil")) {
         v = JsonGetDouble(breakout_json, "rsi_buy_ceil");
         if(v > 0 && v <= 100) g_sc.breakout_rsi_buy_ceil = v;
      }
      if(JsonHasKey(breakout_json, "rsi_sell_floor")) {
         v = JsonGetDouble(breakout_json, "rsi_sell_floor");
         if(v >= 0 && v < 100) g_sc.breakout_rsi_sell_floor = v;
      }
      if(JsonHasKey(breakout_json, "adx_sell_floor_threshold")) {
         v = JsonGetDouble(breakout_json, "adx_sell_floor_threshold");
         if(v > 0 && v <= 80) g_sc.breakout_adx_sell_floor_threshold = v;
      }
      if(JsonHasKey(breakout_json, "rsi_sell_floor_weak_adx")) {
         v = JsonGetDouble(breakout_json, "rsi_sell_floor_weak_adx");
         if(v >= 0 && v < 100) g_sc.breakout_rsi_sell_floor_weak_adx = v;
      }
      if(JsonHasKey(breakout_json, "h1h4_crash_sell")) {
         v = JsonGetDouble(breakout_json, "h1h4_crash_sell");
         g_sc.breakout_h1h4_crash_sell = (v >= 0.5);
      }
      if(JsonHasKey(breakout_json, "h1h4_crash_sell_rsi_min")) {
         v = JsonGetDouble(breakout_json, "h1h4_crash_sell_rsi_min");
         if(v >= 0 && v < 50) g_sc.breakout_h1h4_crash_sell_rsi_min = v;
      }
      if(JsonHasKey(breakout_json, "h1h4_crash_sell_adx_max")) {
         v = JsonGetDouble(breakout_json, "h1h4_crash_sell_adx_max");
         if(v > 0 && v <= 100) g_sc.h1h4_crash_sell_adx_max = v;
      }
      if(JsonHasKey(breakout_json, "min_h1_bear_strength")) {
         v = JsonGetDouble(breakout_json, "min_h1_bear_strength");
         if(v >= 0 && v <= 5.0) g_sc.breakout_min_h1_bear_strength = v;
      }
      if(JsonHasKey(breakout_json, "require_macd_sell")) { v = JsonGetDouble(breakout_json,"require_macd_sell"); g_sc.breakout_require_macd_sell = (v >= 0.5); }
      if(JsonHasKey(breakout_json, "require_macd_buy"))  { v = JsonGetDouble(breakout_json,"require_macd_buy");  g_sc.breakout_require_macd_buy  = (v >= 0.5); }
      if(JsonHasKey(breakout_json, "macd_fast"))         { v = JsonGetDouble(breakout_json,"macd_fast");   if(v >= 1 && v <= 50) g_sc.breakout_macd_fast   = (int)v; }
      if(JsonHasKey(breakout_json, "macd_slow"))         { v = JsonGetDouble(breakout_json,"macd_slow");   if(v >= 1 && v <= 100) g_sc.breakout_macd_slow  = (int)v; }
      if(JsonHasKey(breakout_json, "macd_signal"))       { v = JsonGetDouble(breakout_json,"macd_signal"); if(v >= 1 && v <= 50) g_sc.breakout_macd_signal = (int)v; }
      if(JsonHasKey(breakout_json, "sell_limit_enabled"))      { v = JsonGetDouble(breakout_json,"sell_limit_enabled");      g_sc.breakout_sell_limit_enabled      = (v >= 0.5); }
      if(JsonHasKey(breakout_json, "sell_limit_atr_mult"))     { v = JsonGetDouble(breakout_json,"sell_limit_atr_mult");     if(v > 0 && v <= 5.0) g_sc.breakout_sell_limit_atr_mult     = v; }
      if(JsonHasKey(breakout_json, "sell_limit_lot_factor"))   { v = JsonGetDouble(breakout_json,"sell_limit_lot_factor");   if(v > 0 && v <= 1.0) g_sc.breakout_sell_limit_lot_factor   = v; }
      if(JsonHasKey(breakout_json, "sell_limit_expiry_bars"))  { v = JsonGetDouble(breakout_json,"sell_limit_expiry_bars");  if(v >= 1 && v <= 50) g_sc.breakout_sell_limit_expiry_bars  = (int)v; }
      if(JsonHasKey(breakout_json, "sell_limit_l2_enabled"))   { v = JsonGetDouble(breakout_json,"sell_limit_l2_enabled");   g_sc.breakout_sell_limit_l2_enabled   = (v >= 0.5); }
      if(JsonHasKey(breakout_json, "sell_limit_l2_atr_mult"))  { v = JsonGetDouble(breakout_json,"sell_limit_l2_atr_mult");  if(v > 0 && v <= 5.0) g_sc.breakout_sell_limit_l2_atr_mult  = v; }
      if(JsonHasKey(breakout_json, "sell_limit_l2_lot_factor")){ v = JsonGetDouble(breakout_json,"sell_limit_l2_lot_factor"); if(v > 0 && v <= 1.0) g_sc.breakout_sell_limit_l2_lot_factor = v; }
      // SELL STOP continuation (2.7.10 Day 2) — disabled by default
      if(JsonHasKey(breakout_json, "sell_stop_cont_enabled"))    { v = JsonGetDouble(breakout_json,"sell_stop_cont_enabled");    g_sc.sell_stop_cont_enabled    = (v >= 0.5); }
      if(JsonHasKey(breakout_json, "sell_stop_cont_atr_mult"))   { v = JsonGetDouble(breakout_json,"sell_stop_cont_atr_mult");   if(v > 0 && v <= 5.0)  g_sc.sell_stop_cont_atr_mult   = v; }
      if(JsonHasKey(breakout_json, "sell_stop_cont_lot_factor")) { v = JsonGetDouble(breakout_json,"sell_stop_cont_lot_factor"); if(v > 0 && v <= 2.0)  g_sc.sell_stop_cont_lot_factor = v; }
      if(JsonHasKey(breakout_json, "sell_stop_cont_tp_atr_mult")) { v = JsonGetDouble(breakout_json,"sell_stop_cont_tp_atr_mult"); if(v >= 0.0) g_sc.sell_stop_cont_tp_atr_mult = v; }
      if(JsonHasKey(breakout_json, "sell_stop_cont_expiry_bars")){ v = JsonGetDouble(breakout_json,"sell_stop_cont_expiry_bars"); if(v >= 1 && v <= 50) g_sc.sell_stop_cont_expiry_bars = (int)v; }
      if(JsonHasKey(breakout_json, "sell_stop_cont_min_rsi"))    { v = JsonGetDouble(breakout_json,"sell_stop_cont_min_rsi");    if(v >= 0 && v < 50)  g_sc.sell_stop_cont_min_rsi    = v; }
      if(JsonHasKey(breakout_json, "sell_stop_cont_legs"))       { v = JsonGetDouble(breakout_json,"sell_stop_cont_legs");       if(v >= 1 && v <= 7)  g_sc.sell_stop_cont_legs       = (int)v; }
      // BUY LIMIT recovery (2.7.10 Day 3) — disabled by default
      if(JsonHasKey(breakout_json, "buy_limit_recovery_enabled"))    { v = JsonGetDouble(breakout_json,"buy_limit_recovery_enabled");    g_sc.buy_limit_recovery_enabled    = (v >= 0.5); }
      if(JsonHasKey(breakout_json, "buy_limit_recovery_min_rsi"))    { v = JsonGetDouble(breakout_json,"buy_limit_recovery_min_rsi");    if(v >= 0 && v < 80) g_sc.buy_limit_recovery_min_rsi    = v; }
      if(JsonHasKey(breakout_json, "buy_limit_recovery_lot_factor")) { v = JsonGetDouble(breakout_json,"buy_limit_recovery_lot_factor"); if(v > 0 && v <= 1.0) g_sc.buy_limit_recovery_lot_factor = v; }
      if(JsonHasKey(breakout_json, "buy_limit_recovery_expiry_bars")){ v = JsonGetDouble(breakout_json,"buy_limit_recovery_expiry_bars"); if(v >= 1 && v <= 50) g_sc.buy_limit_recovery_expiry_bars = (int)v; }
      if(JsonHasKey(breakout_json, "buy_limit_recovery_sl_atr_mult")){ v = JsonGetDouble(breakout_json,"buy_limit_recovery_sl_atr_mult"); if(v > 0 && v <= 5.0) g_sc.buy_limit_recovery_sl_atr_mult = v; }
      // H4 supplemental gates (2.7.10) — disabled by default
      if(JsonHasKey(breakout_json, "h4_rsi_gate_enabled"))  { v = JsonGetDouble(breakout_json,"h4_rsi_gate_enabled");  g_sc.h4_rsi_gate_enabled  = (v >= 0.5); }
      if(JsonHasKey(breakout_json, "h4_rsi_sell_max"))      { v = JsonGetDouble(breakout_json,"h4_rsi_sell_max");      if(v > 0 && v <= 100) g_sc.h4_rsi_sell_max      = v; }
      if(JsonHasKey(breakout_json, "h4_rsi_buy_min"))       { v = JsonGetDouble(breakout_json,"h4_rsi_buy_min");       if(v >= 0 && v < 100) g_sc.h4_rsi_buy_min       = v; }
      if(JsonHasKey(breakout_json, "h4_adx_gate_enabled"))  { v = JsonGetDouble(breakout_json,"h4_adx_gate_enabled");  g_sc.h4_adx_gate_enabled  = (v >= 0.5); }
      if(JsonHasKey(breakout_json, "h4_adx_min_sell"))      { v = JsonGetDouble(breakout_json,"h4_adx_min_sell");      if(v >= 0 && v <= 100) g_sc.h4_adx_min_sell      = v; }
      if(JsonHasKey(breakout_json, "h4_adx_min_buy"))       { v = JsonGetDouble(breakout_json,"h4_adx_min_buy");       if(v >= 0 && v <= 100) g_sc.h4_adx_min_buy       = v; }
      if(JsonHasKey(breakout_json, "sell_inside_band_lot_factor")) {
         v = JsonGetDouble(breakout_json, "sell_inside_band_lot_factor");
         if(v > 0 && v <= 1.0) g_sc.breakout_sell_inside_band_lot_factor = v;
      }
      if(JsonHasKey(breakout_json, "max_reentry_atr_ext")) {
         v = JsonGetDouble(breakout_json, "max_reentry_atr_ext");
         if(v >= 0.0) g_sc.breakout_max_reentry_atr_ext = v;
      }
      if(JsonHasKey(breakout_json, "require_rsi_declining_sell")) {
         v = JsonGetDouble(breakout_json, "require_rsi_declining_sell");
         g_sc.breakout_require_rsi_declining_sell = (v >= 0.5);
      }
      if(JsonHasKey(breakout_json, "rsi_decl_sell_adx_threshold")) {
         v = JsonGetDouble(breakout_json, "rsi_decl_sell_adx_threshold");
         if(v > 0 && v <= 80) g_sc.breakout_rsi_decl_sell_adx_threshold = v;
      }
      if(JsonHasKey(breakout_json, "require_m30_bear_sell")) {
         v = JsonGetDouble(breakout_json, "require_m30_bear_sell");
         g_sc.breakout_require_m30_bear_sell = (v >= 0.5);
      }
      if(JsonHasKey(breakout_json, "m30_bear_adx_min")) {
         v = JsonGetDouble(breakout_json, "m30_bear_adx_min");
         if(v >= 0 && v <= 80) g_sc.breakout_m30_bear_adx_min = v;
      }
      if(JsonHasKey(breakout_json, "require_h1_di_buy")) {
         v = JsonGetDouble(breakout_json, "require_h1_di_buy");
         g_sc.breakout_require_h1_di_buy = (v >= 0.5);
      }
      if(JsonHasKey(breakout_json, "require_h1_di_sell")) {
         v = JsonGetDouble(breakout_json, "require_h1_di_sell");
         g_sc.breakout_require_h1_di_sell = (v >= 0.5);
      }
      if(JsonHasKey(breakout_json, "require_h1_macd_sell")) {
         v = JsonGetDouble(breakout_json, "require_h1_macd_sell");
         g_sc.breakout_require_h1_macd_sell = (v >= 0.5);
      }
      if(JsonHasKey(breakout_json, "counter_buy_adx_threshold")) {
         v = JsonGetDouble(breakout_json, "counter_buy_adx_threshold");
         if(v > 0 && v <= 80) g_sc.breakout_counter_buy_adx_threshold = v;
      }
      if(JsonHasKey(breakout_json, "adx_min_sell_lookback_bars")) {
         v = JsonGetDouble(breakout_json, "adx_min_sell_lookback_bars");
         if(v >= 0 && v <= 20) g_sc.breakout_adx_min_sell_lookback_bars = (int)v;
      }
   }
   v = JsonGetDouble(content, "fast_lock_min_hold_sec_bounce"); if(v >= 0) g_sc.fast_lock_min_hold_sec_bounce = (int)v;
   v = JsonGetDouble(content, "fast_lock_min_hold_sec_breakout"); if(v >= 0) g_sc.fast_lock_min_hold_sec_breakout = (int)v;
   v = JsonGetDouble(content, "max_spread_points");if(v > 0) g_sc.max_spread_points = v;
   v = JsonGetDouble(content, "max_open_groups"); if(v > 0) g_sc.max_open_groups = (int)v;
   v = JsonGetDouble(content, "max_trades_per_session"); if(v > 0) g_sc.max_trades_per_session = (int)v;
   v = JsonGetDouble(content, "loss_cooldown_sec"); if(v > 0) g_sc.loss_cooldown_sec = (int)v;
   if(JsonHasKey(content,"session_ny_sell_cutoff_utc")) { v = JsonGetDouble(content,"session_ny_sell_cutoff_utc"); if(v >= 0 && v <= 23) g_sc.session_ny_sell_cutoff_utc = (int)v; }
   if(JsonHasKey(content,"session_london_sell_cutoff_utc")) { v = JsonGetDouble(content,"session_london_sell_cutoff_utc"); if(v >= 0 && v <= 23) g_sc.session_london_sell_cutoff_utc = (int)v; }
   if(JsonHasKey(content,"breakout_near_floor_lot_factor")) { v = JsonGetDouble(content,"breakout_near_floor_lot_factor"); if(v > 0 && v <= 1.0) g_sc.breakout_near_floor_lot_factor = v; }
   if(JsonHasKey(content,"same_direction_stack_lot_factor")) { v = JsonGetDouble(content,"same_direction_stack_lot_factor"); if(v > 0 && v <= 1.0) g_sc.same_direction_stack_lot_factor = v; }
   if(JsonHasKey(content,"breakout_adx_lot_use_m15")) { v = JsonGetDouble(content,"breakout_adx_lot_use_m15"); g_sc.breakout_adx_lot_use_m15 = (v >= 0.5); }
   if(JsonHasKey(content,"breakout_adx_lot_mid_threshold"))    { v = JsonGetDouble(content,"breakout_adx_lot_mid_threshold");    if(v > 0 && v <= 100) g_sc.breakout_adx_lot_mid_threshold    = v; }
   if(JsonHasKey(content,"breakout_adx_lot_high_threshold"))   { v = JsonGetDouble(content,"breakout_adx_lot_high_threshold");   if(v > 0 && v <= 100) g_sc.breakout_adx_lot_high_threshold   = v; }
   if(JsonHasKey(content,"breakout_adx_lot_factor_mid"))       { v = JsonGetDouble(content,"breakout_adx_lot_factor_mid");       if(v > 0 && v <= 1.0) g_sc.breakout_adx_lot_factor_mid       = v; }
   if(JsonHasKey(content,"breakout_adx_lot_factor_high"))      { v = JsonGetDouble(content,"breakout_adx_lot_factor_high");      if(v > 0 && v <= 1.0) g_sc.breakout_adx_lot_factor_high      = v; }
   if(JsonHasKey(content,"breakout_adx_sell_block_threshold")) { v = JsonGetDouble(content,"breakout_adx_sell_block_threshold"); if(v > 0 && v <= 100) g_sc.breakout_adx_sell_block_threshold = v; }
   v = JsonGetDouble(content, "post_sl_cooldown_sec"); if(v >= 0) g_sc.post_sl_cooldown_sec = (int)v;
   if(JsonHasKey(content, "breakout_near_floor_lot_factor")) {
      v = JsonGetDouble(content, "breakout_near_floor_lot_factor");
      if(v > 0 && v <= 1.0) g_sc.breakout_near_floor_lot_factor = v;
   }
   if(JsonHasKey(content, "same_direction_stack_lot_factor")) {
      v = JsonGetDouble(content, "same_direction_stack_lot_factor");
      if(v > 0 && v <= 1.0) g_sc.same_direction_stack_lot_factor = v;
   }
   v = JsonGetDouble(content, "tight_tp_atr_mult"); if(v > 0) g_sc.dd_tight_tp_atr = v;
   v = JsonGetDouble(content, "pending_entry_threshold_points"); if(v > 0) g_sc.pending_entry_threshold_points = v;
   v = JsonGetDouble(content, "trend_strength_atr_threshold"); if(v > 0) g_sc.trend_strength_atr_threshold = v;
   if(JsonHasKey(content, "breakout_buffer_points")) {
      v = JsonGetDouble(content, "breakout_buffer_points");
      if(v >= 0) g_sc.breakout_buffer_points = v;
   }
   if(JsonHasKey(content, "london_start_utc")) {
      v = JsonGetDouble(content, "london_start_utc");
      if(v >= 0 && v <= 23) g_sc.london_start = (int)v;
   }
   if(JsonHasKey(content, "london_end_utc")) {
      v = JsonGetDouble(content, "london_end_utc");
      if(v >= 0 && v <= 24) g_sc.london_end = (int)v;
   }
   if(JsonHasKey(content, "ny_start_utc")) {
      v = JsonGetDouble(content, "ny_start_utc");
      if(v >= 0 && v <= 23) g_sc.ny_start = (int)v;
   }
   if(JsonHasKey(content, "ny_end_utc")) {
      v = JsonGetDouble(content, "ny_end_utc");
      if(v >= 0 && v <= 24) g_sc.ny_end = (int)v;
   }
   if(JsonHasKey(content, "skip_asian"))  { v = JsonGetDouble(content, "skip_asian");  g_sc.skip_asian  = (v >= 0.5); }
   if(JsonHasKey(content, "skip_london")) { v = JsonGetDouble(content, "skip_london"); g_sc.skip_london = (v >= 0.5); }
   if(JsonHasKey(content, "skip_ny"))     { v = JsonGetDouble(content, "skip_ny");     g_sc.skip_ny     = (v >= 0.5); }
   if(JsonHasKey(content, "tester_session_filter")) {
      v = JsonGetDouble(content, "tester_session_filter");
      g_sc.tester_session_filter = (v >= 0.5);
   }
   if(JsonHasKey(content, "tester_allowed_sessions")) {
      string ts_val = JsonGetString(content, "tester_allowed_sessions");
      if(StringLen(ts_val) > 0) g_sc.tester_allowed_sessions = ts_val;
   }
   if(JsonHasKey(content, "tester_cooldown_enabled")) {
      v = JsonGetDouble(content, "tester_cooldown_enabled");
      g_sc.tester_cooldown_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "direction_cooldown_enabled")) {
      v = JsonGetDouble(content, "direction_cooldown_enabled");
      g_sc.direction_cooldown_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "direction_cooldown_bars")) {
      v = JsonGetDouble(content, "direction_cooldown_bars");
      if(v >= 0 && v <= 50) g_sc.direction_cooldown_bars = (int)v;
   }
   if(JsonHasKey(content, "journal_enabled")) {
      v = JsonGetDouble(content, "journal_enabled");
      g_sc.journal_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "journal_record_skips")) {
      v = JsonGetDouble(content, "journal_record_skips");
      g_sc.journal_record_skips = (v >= 0.5);
   }
   if(JsonHasKey(content, "journal_import_trades")) {
      v = JsonGetDouble(content, "journal_import_trades");
      g_sc.journal_import_trades = (v >= 0.5);
   }
   if(JsonHasKey(content, "journal_import_depth_days")) {
      v = JsonGetDouble(content, "journal_import_depth_days");
      if(v >= 1 && v <= 365) g_sc.journal_import_depth_days = (int)v;
   }
   if(JsonHasKey(content, "journal_stats_interval_sec")) {
      v = JsonGetDouble(content, "journal_stats_interval_sec");
      if(v >= 60 && v <= 3600) g_sc.journal_stats_interval_sec = (int)v;
   }
   if(JsonHasKey(lot_json, "fixed_lot")) {
      v = JsonGetDouble(lot_json, "fixed_lot");
      if(v > 0) g_sc.lot_fixed = v;
   }
   if(JsonHasKey(lot_json, "num_trades")) {
      v = JsonGetDouble(lot_json, "num_trades");
      if(v >= 1) g_sc.lot_num_trades = (int)v;
   }
   if(JsonHasKey(lot_json, "min_num_trades")) {
      v = JsonGetDouble(lot_json, "min_num_trades");
      if(v >= 1) g_sc.lot_min_trades = (int)v;
   }
   if(JsonHasKey(lot_json, "max_num_trades")) {
      v = JsonGetDouble(lot_json, "max_num_trades");
      if(v >= 1) g_sc.lot_max_trades = (int)v;
   }
   // When min/max define the envelope, derive base leg count for the resolver (midpoint; equals min when min==max).
   if(g_sc.lot_min_trades > 0 || g_sc.lot_max_trades > 0) {
      int tlo = g_sc.lot_min_trades > 0 ? g_sc.lot_min_trades : 1;
      int thi = g_sc.lot_max_trades > 0 ? g_sc.lot_max_trades : 20;
      tlo = MathMax(1, MathMin(30, tlo));
      thi = MathMax(1, MathMin(30, thi));
      if(tlo > thi) { int sw = tlo; tlo = thi; thi = sw; }
      g_sc.lot_num_trades = MathMax(1, MathMin(30, (tlo + thi) / 2));
   }
   if(JsonHasKey(lot_json, "lot_sizing_source")) {
      string src = JsonGetString(lot_json, "lot_sizing_source");
      StringTrimLeft(src);
      StringTrimRight(src);
      StringToUpper(src);
      if(src == "AUTO" || src == "INPUTS" || src == "CONFIG")
         g_sc.lot_sizing_source = src;
   }
   if(JsonHasKey(lot_json, "inputs_override_lot_sizing")) {
      v = JsonGetDouble(lot_json, "inputs_override_lot_sizing");
      g_sc.lot_inputs_override = (v >= 0.5);
   }
   if(JsonHasKey(lot_json, "staged_entry_enabled")) {
      v = JsonGetDouble(lot_json, "staged_entry_enabled");
      g_sc.staged_entry_enabled = (v >= 0.5);
   }
   if(JsonHasKey(lot_json, "staged_initial_legs")) {
      v = JsonGetDouble(lot_json, "staged_initial_legs");
      if(v >= 1 && v <= 30) g_sc.staged_initial_legs = (int)v;
   }
   if(JsonHasKey(lot_json, "staged_add_interval_sec")) {
      v = JsonGetDouble(lot_json, "staged_add_interval_sec");
      if(v >= 3 && v <= 600) g_sc.staged_add_interval_sec = (int)v;
   }
   if(JsonHasKey(lot_json, "staged_add_min_favorable_points")) {
      v = JsonGetDouble(lot_json, "staged_add_min_favorable_points");
      if(v >= 0 && v <= 5000) g_sc.staged_add_min_favorable_points = v;
   }
   if(JsonHasKey(lot_json, "staged_favorable_from_entry_only")) {
      v = JsonGetDouble(lot_json, "staged_favorable_from_entry_only");
      g_sc.staged_favorable_from_entry_only = (v >= 0.5);
   }
   if(JsonHasKey(lot_json, "pending_ladder_abort_enabled")) {
      v = JsonGetDouble(lot_json, "pending_ladder_abort_enabled");
      g_sc.pending_ladder_abort_enabled = (v >= 0.5);
   }
   if(JsonHasKey(lot_json, "pending_ladder_abort_adverse_points")) {
      v = JsonGetDouble(lot_json, "pending_ladder_abort_adverse_points");
      if(v >= 0 && v <= 5000) g_sc.pending_ladder_abort_adverse_points = v;
   }
   if(JsonHasKey(lot_json, "pending_ladder_abort_require_negative_float")) {
      v = JsonGetDouble(lot_json, "pending_ladder_abort_require_negative_float");
      g_sc.pending_ladder_abort_require_negative_float = (v >= 0.5);
   }
   if(JsonHasKey(lot_json, "recovery_leg_boost_enabled")) {
      v = JsonGetDouble(lot_json, "recovery_leg_boost_enabled");
      g_sc.recovery_leg_boost_enabled = (v >= 0.5);
   }
   if(JsonHasKey(lot_json, "recovery_leg_boost_dd_pct_min")) {
      v = JsonGetDouble(lot_json, "recovery_leg_boost_dd_pct_min");
      if(v >= 0.05 && v <= 50.0) g_sc.recovery_leg_boost_dd_pct_min = v;
   }
   if(JsonHasKey(lot_json, "recovery_leg_boost_extra")) {
      v = JsonGetDouble(lot_json, "recovery_leg_boost_extra");
      if(v >= 0 && v <= 15) g_sc.recovery_leg_boost_extra = (int)v;
   }
   if(JsonHasKey(lot_json, "gold_native_max_sell_legs")) {
      v = JsonGetDouble(lot_json, "gold_native_max_sell_legs");
      if(v >= 0 && v <= 30) g_sc.gold_native_max_sell_legs = (int)v;
   }
   if(JsonHasKey(lot_json, "native_legs_max_when_unclear")) {
      v = JsonGetDouble(lot_json, "native_legs_max_when_unclear");
      if(v >= 0 && v <= 30) g_sc.native_legs_max_when_unclear = (int)v;
   }
   if(JsonHasKey(lot_json, "native_legs_clear_trend_factor")) {
      v = JsonGetDouble(lot_json, "native_legs_clear_trend_factor");
      if(v >= 1.0 && v <= 3.0) g_sc.native_legs_clear_trend_factor = v;
   }
   if(JsonHasKey(lot_json, "native_force_staged_scale_in")) {
      v = JsonGetDouble(lot_json, "native_force_staged_scale_in");
      g_sc.native_force_staged_scale_in = (v >= 0.5);
   }
   if(JsonHasKey(lot_json, "native_scalper_use_limit_entry")) {
      v = JsonGetDouble(lot_json, "native_scalper_use_limit_entry");
      g_sc.native_scalper_use_limit_entry = (v >= 0.5);
   }
   if(JsonHasKey(content, "high_vol_trend_guard_enabled")) {
      v = JsonGetDouble(content, "high_vol_trend_guard_enabled");
      g_sc.high_vol_trend_guard_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "high_vol_apply_in_tester")) {
      v = JsonGetDouble(content, "high_vol_apply_in_tester");
      g_sc.high_vol_apply_in_tester = (v >= 0.5);
   }
   if(JsonHasKey(content, "high_vol_adx_min")) {
      v = JsonGetDouble(content, "high_vol_adx_min");
      if(v > 0) g_sc.high_vol_adx_min = v;
   }
   if(JsonHasKey(content, "high_vol_trend_strength_min")) {
      v = JsonGetDouble(content, "high_vol_trend_strength_min");
      if(v > 0) g_sc.high_vol_trend_strength_min = v;
   }
   if(JsonHasKey(content, "high_vol_disable_bounce")) {
      v = JsonGetDouble(content, "high_vol_disable_bounce");
      g_sc.high_vol_disable_bounce = (v >= 0.5);
   }
   if(JsonHasKey(content, "high_vol_require_h1_h4_breakout_align")) {
      v = JsonGetDouble(content, "high_vol_require_h1_h4_breakout_align");
      g_sc.high_vol_require_h1_h4_breakout_align = (v >= 0.5);
   }
   if(JsonHasKey(content, "high_vol_breakout_sl_boost")) {
      v = JsonGetDouble(content, "high_vol_breakout_sl_boost");
      if(v >= 1.0) g_sc.high_vol_breakout_sl_boost = v;
   }
   if(JsonHasKey(content, "high_vol_fast_lock_extra_hold_sec")) {
      v = JsonGetDouble(content, "high_vol_fast_lock_extra_hold_sec");
      if(v >= 0) g_sc.high_vol_fast_lock_extra_hold_sec = (int)v;
   }
   if(JsonHasKey(content, "high_vol_fast_lock_trigger_mult")) {
      v = JsonGetDouble(content, "high_vol_fast_lock_trigger_mult");
      if(v >= 1.0) g_sc.high_vol_fast_lock_trigger_mult = v;
   }
   if(JsonHasKey(content, "high_vol_fast_lock_trail_mult")) {
      v = JsonGetDouble(content, "high_vol_fast_lock_trail_mult");
      if(v >= 1.0) g_sc.high_vol_fast_lock_trail_mult = v;
   }
   if(JsonHasKey(content, "fast_lock_min_profit_points")) {
      v = JsonGetDouble(content, "fast_lock_min_profit_points");
      if(v >= 0) g_sc.fast_lock_min_profit_points = v;
   }
   if(JsonHasKey(content, "fast_lock_spread_guard_mult")) {
      v = JsonGetDouble(content, "fast_lock_spread_guard_mult");
      if(v >= 0.0) g_sc.fast_lock_spread_guard_mult = v;
   }
   if(JsonHasKey(content, "fast_lock_breath_mult")) {
      v = JsonGetDouble(content, "fast_lock_breath_mult");
      if(v >= 0.75 && v <= 2.5) g_sc.fast_lock_breath_mult = v;
   }
   if(JsonHasKey(content, "adx_hysteresis_enabled")) {
      v = JsonGetDouble(content, "adx_hysteresis_enabled");
      g_sc.adx_hysteresis_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "adx_hysteresis_apply_in_tester")) {
      v = JsonGetDouble(content, "adx_hysteresis_apply_in_tester");
      g_sc.adx_hysteresis_apply_in_tester = (v >= 0.5);
   }
   if(JsonHasKey(content, "adx_trend_enter")) {
      v = JsonGetDouble(content, "adx_trend_enter");
      if(v > 0) g_sc.adx_trend_enter = v;
   }
   if(JsonHasKey(content, "adx_trend_exit")) {
      v = JsonGetDouble(content, "adx_trend_exit");
      if(v > 0) g_sc.adx_trend_exit = v;
   }
   if(g_sc.adx_trend_exit > g_sc.adx_trend_enter)
      g_sc.adx_trend_exit = g_sc.adx_trend_enter;
   if(JsonHasKey(content, "sell_loss_grace_sec")) {
      v = JsonGetDouble(content, "sell_loss_grace_sec");
      if(v >= 0) g_sc.sell_loss_grace_sec = (int)v;
   }
   if(JsonHasKey(content, "sell_loss_grace_adverse_points")) {
      v = JsonGetDouble(content, "sell_loss_grace_adverse_points");
      if(v >= 0) g_sc.sell_loss_grace_adverse_points = v;
   }
   if(JsonHasKey(content, "min_sl_atr_mult")) {
      v = JsonGetDouble(content, "min_sl_atr_mult");
      if(v >= 0.3 && v <= 3.0) g_sc.min_sl_atr_mult = v;
   }
   if(JsonHasKey(content, "min_rr")) {
      v = JsonGetDouble(content, "min_rr");
      if(v > 0 && v <= 5.0) g_sc.min_rr = v;
   }
   if(JsonHasKey(content, "min_rr_floor")) {
      v = JsonGetDouble(content, "min_rr_floor");
      if(v > 0 && v <= 5.0) g_sc.min_rr_floor = v;
   }
   if(JsonHasKey(content, "native_sl_extra_buffer_points")) {
      v = JsonGetDouble(content, "native_sl_extra_buffer_points");
      if(v >= 0.0 && v <= 500.0) g_sc.native_sl_extra_buffer_points = v;
   }
   if(JsonHasKey(content, "min_entry_atr")) {
      v = JsonGetDouble(content, "min_entry_atr");
      if(v >= 0.0 && v <= 50.0) g_sc.min_entry_atr = v;
   }
   if(JsonHasKey(content, "max_open_same_direction")) {
      v = JsonGetDouble(content, "max_open_same_direction");
      if(v >= 0) g_sc.max_open_same_direction = (int)v;
   }
   if(JsonHasKey(content, "entry_quality_bars")) {
      v = JsonGetDouble(content, "entry_quality_bars");
      if(v >= 1 && v <= 20) g_sc.entry_quality_bars = (int)v;
   }
   if(JsonHasKey(content, "min_body_ratio")) {
      v = JsonGetDouble(content, "min_body_ratio");
      if(v >= 0.0 && v <= 1.0) g_sc.min_body_ratio = v;
   }
   if(JsonHasKey(content, "min_directional_bars")) {
      v = JsonGetDouble(content, "min_directional_bars");
      if(v >= 0 && v <= 20) g_sc.min_directional_bars = (int)v;
   }
   if(JsonHasKey(content, "require_bb_expansion")) {
      v = JsonGetDouble(content, "require_bb_expansion");
      g_sc.require_bb_expansion = (v >= 0.5);
   }
   // V2 bounce filters
   if(JsonHasKey(content, "bounce_require_h1_direction")) {
      v = JsonGetDouble(content, "bounce_require_h1_direction");
      g_sc.bounce_require_h1_direction = (v >= 0.5);
   }
   if(JsonHasKey(content, "bounce_require_bar0_confirm")) {
      v = JsonGetDouble(content, "bounce_require_bar0_confirm");
      g_sc.bounce_require_bar0_confirm = (v >= 0.5);
   }
   if(JsonHasKey(content, "bounce_min_candle_score")) {
      v = JsonGetDouble(content, "bounce_min_candle_score");
      if(v >= 0 && v <= 3) g_sc.bounce_min_candle_score = (int)v;
   }
   if(JsonHasKey(content, "bounce_require_liquidity_zone")) {
      v = JsonGetDouble(content, "bounce_require_liquidity_zone");
      g_sc.bounce_require_liquidity_zone = (v >= 0.5);
   }
   // V2 volume profile
   if(JsonHasKey(content, "vp_lookback")) {
      v = JsonGetDouble(content, "vp_lookback");
      if(v >= 20 && v <= 500) g_sc.vp_lookback = (int)v;
   }
   if(JsonHasKey(content, "vp_bins")) {
      v = JsonGetDouble(content, "vp_bins");
      if(v >= 10 && v <= 200) g_sc.vp_bins = (int)v;
   }
   // V2 breakout retest
   if(JsonHasKey(content, "breakout_use_retest")) {
      v = JsonGetDouble(content, "breakout_use_retest");
      g_sc.breakout_use_retest = (v >= 0.5);
   }
   if(JsonHasKey(content, "breakout_retest_max_bars")) {
      v = JsonGetDouble(content, "breakout_retest_max_bars");
      if(v >= 1 && v <= 20) g_sc.breakout_retest_max_bars = (int)v;
   }
   // V2 Fibonacci swing
   if(JsonHasKey(content, "fib_bias_enabled")) {
      v = JsonGetDouble(content, "fib_bias_enabled");
      g_sc.fib_bias_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "fib_tp_enabled")) {
      v = JsonGetDouble(content, "fib_tp_enabled");
      g_sc.fib_tp_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "fib_lookback")) {
      v = JsonGetDouble(content, "fib_lookback");
      if(v >= 0 && v <= 500) g_sc.fib_lookback = (int)v;
   }
   // V2 RSI divergence
   if(JsonHasKey(content, "rsi_div_enabled")) {
      v = JsonGetDouble(content, "rsi_div_enabled");
      g_sc.rsi_div_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "rsi_div_lookback")) {
      v = JsonGetDouble(content, "rsi_div_lookback");
      if(v >= 5 && v <= 200) g_sc.rsi_div_lookback = (int)v;
   }
   if(JsonHasKey(content, "rsi_div_swing_bars")) {
      v = JsonGetDouble(content, "rsi_div_swing_bars");
      if(v >= 1 && v <= 10) g_sc.rsi_div_swing_bars = (int)v;
   }
   if(JsonHasKey(content, "rsi_div_min_rsi_diff")) {
      v = JsonGetDouble(content, "rsi_div_min_rsi_diff");
      if(v >= 0.0 && v <= 20.0) g_sc.rsi_div_min_rsi_diff = v;
   }
   if(JsonHasKey(content, "rsi_div_draw_arrows")) {
      v = JsonGetDouble(content, "rsi_div_draw_arrows");
      g_sc.rsi_div_draw_arrows = (v >= 0.5);
   }
   // V2 Parabolic SAR
   if(JsonHasKey(content, "psar_enabled")) {
      v = JsonGetDouble(content, "psar_enabled");
      g_sc.psar_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "psar_step")) {
      v = JsonGetDouble(content, "psar_step");
      if(v >= 0.001 && v <= 0.5) g_sc.psar_step = v;
   }
   if(JsonHasKey(content, "psar_maximum")) {
      v = JsonGetDouble(content, "psar_maximum");
      if(v >= 0.01 && v <= 5.0) g_sc.psar_maximum = v;
   }
   if(JsonHasKey(content, "news_filter_enabled")) {
      v = JsonGetDouble(content, "news_filter_enabled");
      g_sc.news_filter_enabled = (v >= 0.5);
   }
   if(JsonHasKey(content, "news_filter_currencies")) {
      string nf_cur = JsonGetString(content, "news_filter_currencies");
      if(StringLen(nf_cur) > 0) g_sc.news_filter_currencies = nf_cur;
   }
   if(JsonHasKey(content, "news_filter_low_before")) {
      v = JsonGetDouble(content, "news_filter_low_before");
      if(v >= 0) g_sc.news_filter_low_before = (int)v;
   }
   if(JsonHasKey(content, "news_filter_low_after")) {
      v = JsonGetDouble(content, "news_filter_low_after");
      if(v >= 0) g_sc.news_filter_low_after = (int)v;
   }
   if(JsonHasKey(content, "news_filter_medium_before")) {
      v = JsonGetDouble(content, "news_filter_medium_before");
      if(v >= 0) g_sc.news_filter_medium_before = (int)v;
   }
   if(JsonHasKey(content, "news_filter_medium_after")) {
      v = JsonGetDouble(content, "news_filter_medium_after");
      if(v >= 0) g_sc.news_filter_medium_after = (int)v;
   }
   if(JsonHasKey(content, "news_filter_high_before")) {
      v = JsonGetDouble(content, "news_filter_high_before");
      if(v >= 0) g_sc.news_filter_high_before = (int)v;
   }
   if(JsonHasKey(content, "news_filter_high_after")) {
      v = JsonGetDouble(content, "news_filter_high_after");
      if(v >= 0) g_sc.news_filter_high_after = (int)v;
   }
   if(JsonHasKey(content, "news_filter_special")) {
      string nf_special = JsonGetString(content, "news_filter_special");
      if(StringLen(nf_special) > 0) g_sc.news_filter_special = nf_special;
   }
   if(JsonHasKey(content, "news_filter_hard_floor_min")) {
      v = JsonGetDouble(content, "news_filter_hard_floor_min");
      if(v >= 0) g_sc.news_filter_hard_floor_min = (int)v;
   }
   if(JsonHasKey(content, "news_filter_tighten_pct")) {
      v = JsonGetDouble(content, "news_filter_tighten_pct");
      if(v >= 0.0 && v <= 1.0) g_sc.news_filter_tighten_pct = v;
   }
   if(JsonHasKey(content, "news_filter_block_pct")) {
      v = JsonGetDouble(content, "news_filter_block_pct");
      if(v >= 0.0 && v <= 1.0) g_sc.news_filter_block_pct = v;
   }
   if(g_sc.news_filter_tighten_pct >= g_sc.news_filter_block_pct)
      g_sc.news_filter_tighten_pct = g_sc.news_filter_block_pct * 0.5;
   if(JsonHasKey(content, "news_filter_tighten_rsi_buy")) {
      v = JsonGetDouble(content, "news_filter_tighten_rsi_buy");
      if(v >= 0.0 && v <= 100.0) g_sc.news_filter_tighten_rsi_buy = v;
   }
   if(JsonHasKey(content, "news_filter_tighten_rsi_sell")) {
      v = JsonGetDouble(content, "news_filter_tighten_rsi_sell");
      if(v >= 0.0 && v <= 100.0) g_sc.news_filter_tighten_rsi_sell = v;
   }
   if(JsonHasKey(content, "news_filter_refresh_sec")) {
      v = JsonGetDouble(content, "news_filter_refresh_sec");
      if(v > 0) g_sc.news_filter_refresh_sec = (int)v;
   }
   if(JsonHasKey(content, "news_filter_apply_in_tester")) {
      v = JsonGetDouble(content, "news_filter_apply_in_tester");
      g_sc.news_filter_apply_in_tester = (v >= 0.5);
   }
   ApplyScalperLotInputOverrides();
   ApplyNewsFilterInputOverrides();
   PrintFormat("FORGE config reloaded: pending_entry_threshold_points=%.2f trend_strength_atr_threshold=%.4f breakout_buffer_points=%.2f session=%d-%d/%d-%d",
               g_sc.pending_entry_threshold_points,
               g_sc.trend_strength_atr_threshold,
               g_sc.breakout_buffer_points,
               g_sc.london_start,
               g_sc.london_end,
               g_sc.ny_start,
               g_sc.ny_end);
   PrintFormat("FORGE scalper profile: bounce_reclaim_pct=%.1f require_reject=%s fast_lock_hold_sec bounce=%d breakout=%d auto_lot enabled=%s breakout_only=%s max_mult=%.2f trend_ref=%.2f",
               g_sc.bounce_reclaim_pct,
               g_sc.bounce_require_rejection_candle ? "true" : "false",
               g_sc.fast_lock_min_hold_sec_bounce,
               g_sc.fast_lock_min_hold_sec_breakout,
               NativeScalperAutoLotByTrend ? "true" : "false",
               NativeScalperAutoLotBreakoutOnly ? "true" : "false",
               MathMax(1.0, MathMin(5.0, NativeScalperAutoLotMaxMultiplier)),
               MathMax(0.10, NativeScalperAutoLotTrendRef));
   bool lot_inputs_override_eff = false;
   string lot_source_mode = g_sc.lot_sizing_source;
   if(lot_source_mode == "INPUTS") lot_inputs_override_eff = true;
   else if(lot_source_mode == "CONFIG") lot_inputs_override_eff = false;
   else lot_inputs_override_eff = NativeScalperInputsOverrideLotSizing ? true : g_sc.lot_inputs_override;
   PrintFormat("FORGE lot sizing profile: mode=%s source=%s input_lot=%.2f input_trades=%d config_min_legs=%d config_max_legs=%d config_lot=%.2f config_trades_mid=%d effective_lot=%.2f effective_trades=%d",
               lot_source_mode,
               lot_inputs_override_eff ? "inputs" : "config",
               ScalperLot,
               ScalperTrades,
               g_sc.lot_min_trades,
               g_sc.lot_max_trades,
               g_sc.lot_fixed,
               g_sc.lot_num_trades,
               lot_inputs_override_eff ? ScalperLot : g_sc.lot_fixed,
               lot_inputs_override_eff ? MathMax(1, ScalperTrades) : MathMax(1, g_sc.lot_num_trades));
   PrintFormat("FORGE staged entry: enabled=%s initial_legs=%d add_interval_sec=%d min_favorable_pts=%.1f from_entry_only=%s | recovery boost: enabled=%s dd_min_pct=%.2f extra_legs=%d",
               g_sc.staged_entry_enabled ? "true" : "false",
               g_sc.staged_initial_legs,
               g_sc.staged_add_interval_sec,
               g_sc.staged_add_min_favorable_points,
               g_sc.staged_favorable_from_entry_only ? "true" : "false",
               g_sc.recovery_leg_boost_enabled ? "true" : "false",
               g_sc.recovery_leg_boost_dd_pct_min,
               g_sc.recovery_leg_boost_extra);
   PrintFormat("FORGE high-vol guard: enabled=%s apply_in_tester=%s adx_min=%.1f trend_min=%.2f disable_bounce=%s strict_breakout_align=%s breakout_sl_boost=%.2f ratchet_extra_hold=%ds trigger_x=%.2f trail_x=%.2f",
               g_sc.high_vol_trend_guard_enabled ? "true" : "false",
               g_sc.high_vol_apply_in_tester ? "true" : "false",
               g_sc.high_vol_adx_min,
               g_sc.high_vol_trend_strength_min,
               g_sc.high_vol_disable_bounce ? "true" : "false",
               g_sc.high_vol_require_h1_h4_breakout_align ? "true" : "false",
               g_sc.high_vol_breakout_sl_boost,
               g_sc.high_vol_fast_lock_extra_hold_sec,
               g_sc.high_vol_fast_lock_trigger_mult,
               g_sc.high_vol_fast_lock_trail_mult);
   PrintFormat("FORGE fast-lock guard: min_profit_pts=%.1f spread_guard_mult=%.2f breath_mult=%.2f",
               g_sc.fast_lock_min_profit_points,
               g_sc.fast_lock_spread_guard_mult,
               g_sc.fast_lock_breath_mult);
   PrintFormat("FORGE ADX hysteresis: enabled=%s apply_in_tester=%s enter=%.1f exit=%.1f",
               g_sc.adx_hysteresis_enabled ? "true" : "false",
               g_sc.adx_hysteresis_apply_in_tester ? "true" : "false",
               g_sc.adx_trend_enter,
               g_sc.adx_trend_exit);
   PrintFormat("FORGE SELL grace: hold_sec=%d adverse_pts=%.1f",
               g_sc.sell_loss_grace_sec,
               g_sc.sell_loss_grace_adverse_points);
   PrintFormat("FORGE SL quality: bounce_sl_mult=%.2f breakout_sl_mult=%.2f min_sl_floor=%.2f×ATR native_extra_pts=%.1f",
               g_sc.bounce_sl_atr_mult,
               g_sc.breakout_sl_atr_mult,
               g_sc.min_sl_atr_mult,
               g_sc.native_sl_extra_buffer_points);
   PrintFormat("FORGE V2: h1_strict_bounce=%s bar0_confirm=%s min_candle_score=%d liquidity_zone=%s htf_bias=%d block_htf_legacy=%s respect_adx_cap_tester=%s respect_h1_tester=%s vp_lookback=%d vp_bins=%d breakout_retest=%s retest_max_bars=%d",
               g_sc.bounce_require_h1_direction ? "true" : "false",
               g_sc.bounce_require_bar0_confirm ? "true" : "false",
               g_sc.bounce_min_candle_score,
               g_sc.bounce_require_liquidity_zone ? "true" : "false",
               g_sc.bounce_htf_bias,
               g_sc.bounce_block_htf_trend_align ? "true" : "false",
               g_sc.bounce_respect_adx_max_in_tester ? "true" : "false",
               g_sc.bounce_respect_h1_filter_in_tester ? "true" : "false",
               g_sc.vp_lookback,
               g_sc.vp_bins,
               g_sc.breakout_use_retest ? "true" : "false",
               g_sc.breakout_retest_max_bars);
   PrintFormat("FORGE V2 FIB: fib_bias=%s fib_tp=%s fib_lookback=%d (effective=%d)",
               g_sc.fib_bias_enabled ? "true" : "false",
               g_sc.fib_tp_enabled ? "true" : "false",
               g_sc.fib_lookback,
               g_sc.fib_lookback > 0 ? g_sc.fib_lookback : g_sc.vp_lookback);
   PrintFormat("FORGE V2 RSI_DIV: enabled=%s lookback=%d swing_bars=%d min_diff=%.1f arrows=%s",
               g_sc.rsi_div_enabled ? "true" : "false",
               g_sc.rsi_div_lookback,
               g_sc.rsi_div_swing_bars,
               g_sc.rsi_div_min_rsi_diff,
               g_sc.rsi_div_draw_arrows ? "true" : "false");
   PrintFormat("FORGE V2 PSAR: enabled=%s step=%.3f max=%.2f",
               g_sc.psar_enabled ? "true" : "false",
               g_sc.psar_step,
               g_sc.psar_maximum);
   PrintFormat("FORGE V2 QUALITY: tester_session=%s/%s tester_cooldown=%s dir_cooldown=%s/%d_bars",
               g_sc.tester_session_filter ? "true" : "false",
               g_sc.tester_allowed_sessions,
               g_sc.tester_cooldown_enabled ? "true" : "false",
               g_sc.direction_cooldown_enabled ? "true" : "false",
               g_sc.direction_cooldown_bars);
   PrintFormat("FORGE V2 JOURNAL: enabled=%s skips=%s import=%s depth=%dd stats=%ds",
               g_sc.journal_enabled ? "true" : "false",
               g_sc.journal_record_skips ? "true" : "false",
               g_sc.journal_import_trades ? "true" : "false",
               g_sc.journal_import_depth_days,
               g_sc.journal_stats_interval_sec);
}
void ResetScalperSessionStateIfNeeded() {
   MqlDateTime dt;
   TimeGMT(dt);
   datetime today = StringToTime(StringFormat("%04d.%02d.%02d 00:00", dt.year, dt.mon, dt.day));
   if(today <= 0) return;
   string current_session = "ASIAN";
   if(dt.hour >= g_sc.london_start && dt.hour < g_sc.london_end)
      current_session = "LONDON";
   else if(dt.hour >= g_sc.ny_start && dt.hour < g_sc.ny_end)
      current_session = "NY";
   if(g_scalper_last_reset_day == 0) {
      g_scalper_last_reset_day = today;
      g_scalper_last_session_label = current_session;
      return;
   }
   bool midnight_utc = (dt.hour == 0 && today != g_scalper_last_reset_day);
   if(today != g_scalper_last_reset_day || midnight_utc) {
      g_scalper_last_reset_day = today;
      g_scalper_session_trades = 0;
      g_scalper_last_entry_bar = 0;
      g_scalper_last_direction = "";
      g_scalper_last_direction_time = 0;
      g_first_buy_entry_price = 0.0;
      g_first_sell_entry_price = 0.0;
      g_scalper_last_session_label = current_session;
      Print("FORGE SCALPER: session counters reset for new UTC day");
      return;
   }
   if(g_scalper_last_session_label == "") {
      g_scalper_last_session_label = current_session;
      return;
   }
   if(current_session != g_scalper_last_session_label) {
      g_scalper_last_session_label = current_session;
      g_first_buy_entry_price = 0.0;
      g_first_sell_entry_price = 0.0;
      PrintFormat("FORGE SCALPER: first-entry anchors reset for session=%s hour=%d UTC",
                  current_session, dt.hour);
   }
}

bool ScalperSessionOK() {
   MqlDateTime dt;
   TimeGMT(dt);
   int h = dt.hour;
   bool is_london = (h >= g_sc.london_start && h < g_sc.london_end);
   bool is_ny     = (h >= g_sc.ny_start     && h < g_sc.ny_end);
   bool is_asian  = !is_london && !is_ny;
   if(is_london && g_sc.skip_london) return false;
   if(is_ny     && g_sc.skip_ny)     return false;
   if(is_asian  && g_sc.skip_asian)  return false;
   return true;
}

bool ScalperTesterSessionOK() {
   if(!g_sc.tester_session_filter) return true;
   string allowed = g_sc.tester_allowed_sessions;
   if(allowed == "ALL" || allowed == "") return true;

   MqlDateTime dt;
   TimeGMT(dt);
   int h = dt.hour;

   string current_session = "ASIAN";
   if(h >= g_sc.london_start && h < g_sc.london_end)
      current_session = "LONDON";
   else if(h >= g_sc.ny_start && h < g_sc.ny_end)
      current_session = "NY";

   string parts[];
   int count = StringSplit(allowed, ',', parts);
   for(int i = 0; i < count; i++) {
      StringTrimLeft(parts[i]);
      StringTrimRight(parts[i]);
      StringToUpper(parts[i]);
      if(parts[i] == current_session) return true;
   }
   return false;
}

bool ScalperSpreadOK() {
   double spread = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / _Point;
   return spread <= g_sc.max_spread_points;
}

int ScalperOpenGroupCount() {
   // Count unique FORGE group magics across positions and pending orders.
   int magics[];
   ArrayResize(magics, 0);
   for(int i = 0; i < PositionsTotal(); i++) {
      if(!g_pos.SelectByIndex(i) || !ChartSymbolMatches(g_pos.Symbol())) continue;
      int pm = (int)g_pos.Magic();
      if(pm < MagicNumber || pm >= MagicNumber + 10000) continue;
      bool exists = false;
      for(int j = 0; j < ArraySize(magics); j++) {
         if(magics[j] == pm) { exists = true; break; }
      }
      if(!exists) {
         int n = ArraySize(magics);
         ArrayResize(magics, n + 1);
         magics[n] = pm;
      }
   }

   int noc = (int)OrdersTotal();
   for(int i = 0; i < noc; i++) {
      ulong ot = OrderGetTicket(i);
      if(ot == 0 || !OrderSelect(ot)) continue;
      if(!ChartSymbolMatches(OrderGetString(ORDER_SYMBOL))) continue;
      int om = (int)OrderGetInteger(ORDER_MAGIC);
      if(om < MagicNumber || om >= MagicNumber + 10000) continue;
      bool exists = false;
      for(int j = 0; j < ArraySize(magics); j++) {
         if(magics[j] == om) { exists = true; break; }
      }
      if(!exists) {
         int n = ArraySize(magics);
         ArrayResize(magics, n + 1);
         magics[n] = om;
      }
   }

   return ArraySize(magics);
}

bool ScalperCooldownOK() {
   if(g_scalper_last_loss_time == 0) return true;
   return (TimeGMT() - g_scalper_last_loss_time) >= g_sc.loss_cooldown_sec;
}

// Direction-specific post-SL cooldown: after SL hit on a direction, block re-entry for post_sl_cooldown_sec.
// Prevents rapid same-direction re-entry after a loss (gold reversal protection).
bool ScalperPostSLCooldownOK(const string direction) {
   if(g_sc.post_sl_cooldown_sec <= 0) return true;
   datetime last_sl = (direction == "SELL") ? g_last_sl_time_sell : g_last_sl_time_buy;
   if(last_sl == 0) return true;
   return (TimeGMT() - last_sl) >= g_sc.post_sl_cooldown_sec;
}

bool ScalperOnePerBar() {
   datetime bar_time = iTime(_Symbol, PERIOD_M5, 0);
   if(bar_time == g_scalper_last_entry_bar) return false;
   return true;
}

bool ScalperDirectionCooldownOK(string proposed_direction) {
   if(!g_sc.direction_cooldown_enabled) return true;
   if(g_scalper_last_direction == "" || g_scalper_last_direction == proposed_direction) return true;
   if(g_scalper_last_direction_time == 0) return true;

   int bars_since = Bars(_Symbol, PERIOD_M5, g_scalper_last_direction_time, TimeCurrent()) - 1;
   if(bars_since < 0) bars_since = 0;

   if(bars_since < g_sc.direction_cooldown_bars) {
      datetime m5bar = iTime(_Symbol, PERIOD_M5, 0);
      if(m5bar != g_scalper_last_sesswarn_log_bar) {
         PrintFormat("FORGE SCALPER: skip gate=direction_cooldown last=%s proposed=%s bars_since=%d min=%d",
                     g_scalper_last_direction, proposed_direction, bars_since, g_sc.direction_cooldown_bars);
      }
      return false;
   }
   return true;
}

bool NativeScalperRegimeBlocksDirection(const string direction) {
   if(!NativeScalperRegimeGate) return false;
   if(!g_regime_apply_policy) return false;
   if(g_regime_confidence < g_regime_ct_min_conf) return false;
   if(g_regime_label == "TREND_BULL" && direction == "SELL") return true;
   if(g_regime_label == "TREND_BEAR" && direction == "BUY") return true;
   return false;
}

// M1 optional gate: CONFIRM = M1 EMA/ATR structure agrees with direction; TRIGGER = CONFIRM + prior M1 bar close vs open
bool NativeScalperM1GateOk(
   const string direction,
   const bool m1_bull, const bool m1_bear, const bool m1_flat
) {
   string mm = NativeScalperM1Mode;
   StringTrimLeft(mm);
   StringTrimRight(mm);
   StringToUpper(mm);
   if(mm == "" || mm == "NONE") return true;
   bool align_buy  = m1_bull || m1_flat;
   bool align_sell = m1_bear || m1_flat;
   if(mm == "CONFIRM") {
      if(direction == "BUY")  return align_buy;
      if(direction == "SELL") return align_sell;
      return true;
   }
   if(mm == "TRIGGER") {
      double c1 = iClose(_Symbol, PERIOD_M1, 1);
      double o1 = iOpen(_Symbol, PERIOD_M1, 1);
      if(direction == "BUY")
         return align_buy && (c1 > o1);
      if(direction == "SELL")
         return align_sell && (c1 < o1);
      return true;
   }
   Print("FORGE SCALPER: unknown NativeScalperM1Mode='", NativeScalperM1Mode, "' — using NONE");
   return true;
}

// ── V2: Candlestick pattern scoring (bars 1–3) ──────────────────
// 0 = no pattern, 1 = basic rejection, 2 = hammer/pin bar, 3 = engulfing
int ScalperCandlePatternScore(bool is_buy) {
   double o1 = iOpen(_Symbol, PERIOD_M5, 1);
   double c1 = iClose(_Symbol, PERIOD_M5, 1);
   double h1 = iHigh(_Symbol, PERIOD_M5, 1);
   double l1 = iLow(_Symbol, PERIOD_M5, 1);
   double o2 = iOpen(_Symbol, PERIOD_M5, 2);
   double c2 = iClose(_Symbol, PERIOD_M5, 2);

   double body1 = MathAbs(c1 - o1);
   double range1 = h1 - l1;
   if(range1 <= 0) return 0;

   if(is_buy) {
      double lower_shadow = MathMin(o1, c1) - l1;
      double upper_shadow = h1 - MathMax(o1, c1);
      if(c1 > o1 && lower_shadow >= 2.0 * body1 && upper_shadow <= body1 * 0.3)
         return 2;
      if(c1 > o1 && c2 < o2 && o1 <= c2 && c1 >= o2)
         return 3;
      if(c1 > o1) return 1;
   } else {
      double upper_shadow = h1 - MathMax(o1, c1);
      double lower_shadow = MathMin(o1, c1) - l1;
      if(c1 < o1 && upper_shadow >= 2.0 * body1 && lower_shadow <= body1 * 0.3)
         return 2;
      if(c1 < o1 && c2 > o2 && o1 >= c2 && c1 <= o2)
         return 3;
      if(c1 < o1) return 1;
   }
   return 0;
}

// ── V2: Volume Profile — lightweight POC from M5 tick volume ────
void ComputeVolumeProfile() {
   if(TimeCurrent() - g_vp_last_calc < 60) return;
   g_vp_last_calc = TimeCurrent();

   int lookback = g_sc.vp_lookback;
   int n_bins = g_sc.vp_bins;
   double hi[], lo[], cl[];
   long vol[];
   ArraySetAsSeries(hi, true);
   ArraySetAsSeries(lo, true);
   ArraySetAsSeries(cl, true);
   ArraySetAsSeries(vol, true);
   if(CopyHigh(_Symbol, PERIOD_M5, 0, lookback, hi) < lookback) return;
   if(CopyLow(_Symbol, PERIOD_M5, 0, lookback, lo) < lookback) return;
   if(CopyClose(_Symbol, PERIOD_M5, 0, lookback, cl) < lookback) return;
   if(CopyTickVolume(_Symbol, PERIOD_M5, 0, lookback, vol) < lookback) {
      if(CopyRealVolume(_Symbol, PERIOD_M5, 0, lookback, vol) < lookback) return;
   }

   double price_max = hi[ArrayMaximum(hi, 0, lookback)];
   double price_min = lo[ArrayMinimum(lo, 0, lookback)];
   if(price_max <= price_min) return;

   double step = (price_max - price_min) / n_bins;
   double bins[];
   ArrayResize(bins, n_bins);
   ArrayInitialize(bins, 0.0);

   double total_vol = 0.0;
   double vwap_cum_pv = 0.0;
   for(int i = 0; i < lookback; i++) {
      double typical = (hi[i] + lo[i] + cl[i]) / 3.0;
      double v = (double)vol[i];
      vwap_cum_pv += typical * v;
      total_vol += v;
      int bin_idx = (int)MathFloor((cl[i] - price_min) / step);
      if(bin_idx < 0) bin_idx = 0;
      if(bin_idx >= n_bins) bin_idx = n_bins - 1;
      bins[bin_idx] += v;
   }

   int max_bin = 0;
   for(int i = 1; i < n_bins; i++)
      if(bins[i] > bins[max_bin]) max_bin = i;

   g_poc_price = price_min + (max_bin + 0.5) * step;
   g_poc_strength = (total_vol > 0) ? (bins[max_bin] / total_vol) : 0.0;
   g_vwap_price = (total_vol > 0) ? (vwap_cum_pv / total_vol) : 0.0;

   PrintFormat("FORGE VP: POC=%.2f VWAP=%.2f strength=%.3f range=[%.2f,%.2f] bins=%d lookback=%d",
               g_poc_price, g_vwap_price, g_poc_strength, price_min, price_max, n_bins, lookback);
}

// ── V2: Fibonacci swing levels from M5 high/low ────────────────
// Ref: MQL5 Article 17121 — "External Flow (III) TrendMap"
//      https://www.mql5.com/en/articles/17121
void ComputeFibonacciSwing() {
   if(TimeCurrent() - g_fib_last_calc < 60) return;
   g_fib_last_calc = TimeCurrent();

   int lookback = (g_sc.fib_lookback > 0) ? g_sc.fib_lookback : g_sc.vp_lookback;
   double hi[], lo[];
   ArraySetAsSeries(hi, true);
   ArraySetAsSeries(lo, true);
   if(CopyHigh(_Symbol, PERIOD_M5, 0, lookback, hi) < lookback) return;
   if(CopyLow(_Symbol, PERIOD_M5, 0, lookback, lo) < lookback) return;

   double swing_high = hi[ArrayMaximum(hi, 0, lookback)];
   double swing_low  = lo[ArrayMinimum(lo, 0, lookback)];
   if(swing_high <= swing_low) return;

   double range = swing_high - swing_low;
   g_fib_high = swing_high;
   g_fib_low  = swing_low;
   g_fib_50   = swing_low + range * 0.500;
   g_fib_382  = swing_low + range * 0.382;
   g_fib_618  = swing_low + range * 0.618;

   PrintFormat("FORGE FIB: high=%.2f low=%.2f fib50=%.2f fib382=%.2f fib618=%.2f lookback=%d",
               g_fib_high, g_fib_low, g_fib_50, g_fib_382, g_fib_618, lookback);
}

// ── V2: RSI divergence detection ────────────────────────────────
// Ref: MQL5 Article 17198 — "RSI Sentinel Tool" by Christian Benjamin
//      https://www.mql5.com/en/articles/17198
void DetectRSIDivergence() {
   if(!g_sc.rsi_div_enabled) { g_rsi_div_type = "NONE"; return; }
   datetime bar_time = iTime(_Symbol, PERIOD_M5, 0);
   if(bar_time == g_rsi_div_last_calc) return;
   g_rsi_div_last_calc = bar_time;

   int lb = g_sc.rsi_div_lookback;
   int sw = g_sc.rsi_div_swing_bars;
   double rsi_buf[], hi_buf[], lo_buf[];
   ArraySetAsSeries(rsi_buf, true);
   ArraySetAsSeries(hi_buf, true);
   ArraySetAsSeries(lo_buf, true);
   if(CopyBuffer(g_mtf[0].h_rsi, 0, 0, lb, rsi_buf) < lb) return;
   if(CopyHigh(_Symbol, PERIOD_M5, 0, lb, hi_buf) < lb) return;
   if(CopyLow(_Symbol, PERIOD_M5, 0, lb, lo_buf) < lb) return;

   int sl1 = -1, sl2 = -1;
   for(int i = sw; i < lb - sw; i++) {
      bool is_low = true;
      for(int j = 1; j <= sw && is_low; j++) {
         if(lo_buf[i] > lo_buf[i-j] || lo_buf[i] > lo_buf[i+j]) is_low = false;
      }
      if(is_low) {
         if(sl1 < 0) sl1 = i;
         else if(sl2 < 0) { sl2 = i; break; }
      }
   }
   int sh1 = -1, sh2 = -1;
   for(int i = sw; i < lb - sw; i++) {
      bool is_hi = true;
      for(int j = 1; j <= sw && is_hi; j++) {
         if(hi_buf[i] < hi_buf[i-j] || hi_buf[i] < hi_buf[i+j]) is_hi = false;
      }
      if(is_hi) {
         if(sh1 < 0) sh1 = i;
         else if(sh2 < 0) { sh2 = i; break; }
      }
   }

   double min_diff = g_sc.rsi_div_min_rsi_diff;
   string prev_type = g_rsi_div_type;
   g_rsi_div_type = "NONE";

   // Bullish divergence (swing lows)
   if(sl1 >= 0 && sl2 >= 0) {
      if(lo_buf[sl1] < lo_buf[sl2] && rsi_buf[sl1] > rsi_buf[sl2]
         && (rsi_buf[sl1] - rsi_buf[sl2]) >= min_diff)
         g_rsi_div_type = "REG_BULL";
      else if(lo_buf[sl1] > lo_buf[sl2] && rsi_buf[sl1] < rsi_buf[sl2]
              && (rsi_buf[sl2] - rsi_buf[sl1]) >= min_diff)
         g_rsi_div_type = "HID_BULL";
   }
   // Bearish divergence (swing highs)
   if(g_rsi_div_type == "NONE" && sh1 >= 0 && sh2 >= 0) {
      if(hi_buf[sh1] > hi_buf[sh2] && rsi_buf[sh1] < rsi_buf[sh2]
         && (rsi_buf[sh2] - rsi_buf[sh1]) >= min_diff)
         g_rsi_div_type = "REG_BEAR";
      else if(hi_buf[sh1] < hi_buf[sh2] && rsi_buf[sh1] > rsi_buf[sh2]
              && (rsi_buf[sh1] - rsi_buf[sh2]) >= min_diff)
         g_rsi_div_type = "HID_BEAR";
   }

   if(g_rsi_div_type != prev_type && g_rsi_div_type != "NONE")
      PrintFormat("FORGE RSI_DIV: %s detected (swingLows=%d/%d swingHighs=%d/%d)",
                  g_rsi_div_type, sl1, sl2, sh1, sh2);
}

void DrawDivergenceArrow(string div_type, double price, datetime time_val) {
   if(!g_sc.rsi_div_draw_arrows || div_type == "NONE") return;
   if(time_val == g_rsi_div_last_arrow_bar) return;
   g_rsi_div_last_arrow_bar = time_val;

   string name = "FORGE_DIV_" + IntegerToString((long)time_val);
   double dpoint = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int code = 0;
   color clr = clrWhite;

   if(StringFind(div_type, "BULL") >= 0) {
      code = 233;
      clr = clrLime;
      price -= 5.0 * dpoint;
   } else {
      code = 234;
      clr = clrOrangeRed;
      price += 5.0 * dpoint;
   }

   if(ObjectFind(0, name) < 0) {
      ObjectCreate(0, name, OBJ_ARROW, 0, time_val, price);
      ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
      ObjectSetInteger(0, name, OBJPROP_ARROWCODE, code);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
      ObjectSetString(0, name, OBJPROP_TOOLTIP, div_type);
   }
}

// ── V2: Parabolic SAR state tracking ───────────────────────────
// Ref: MQL5 Article 17234 — "Parabolic Stop and Reverse Tool" by Christian Benjamin
//      https://www.mql5.com/en/articles/17234
void DetectPSARState() {
   if(!g_sc.psar_enabled) { g_psar_state = "NONE"; return; }
   datetime bar_time = iTime(_Symbol, PERIOD_M5, 0);
   if(bar_time == g_psar_last_calc) return;
   g_psar_last_calc = bar_time;

   if(g_h_psar == INVALID_HANDLE) {
      g_h_psar = iSAR(_Symbol, PERIOD_M5, g_sc.psar_step, g_sc.psar_maximum);
      if(g_h_psar == INVALID_HANDLE) return;
   }

   double sar[], cl[];
   ArraySetAsSeries(sar, true);
   ArraySetAsSeries(cl, true);
   if(CopyBuffer(g_h_psar, 0, 0, 3, sar) < 3) return;
   if(CopyClose(_Symbol, PERIOD_M5, 0, 3, cl) < 3) return;

   bool cur_below = (sar[0] < cl[0]);
   bool prev_below = (sar[1] < cl[1]);

   string prev_state = g_psar_state;

   if(cur_below && !prev_below)
      g_psar_state = "FLIP_BULL";
   else if(!cur_below && prev_below)
      g_psar_state = "FLIP_BEAR";
   else if(cur_below)
      g_psar_state = "BELOW";
   else
      g_psar_state = "ABOVE";

   if(g_psar_state != prev_state && StringFind(g_psar_state, "FLIP") >= 0)
      PrintFormat("FORGE PSAR: %s (sar0=%.2f cl0=%.2f sar1=%.2f cl1=%.2f)",
                  g_psar_state, sar[0], cl[0], sar[1], cl[1]);
}

// ── V2: Read OB zones from LENS ob_zones.json ──────────────────
void ReadOBZones() {
   string content = "";
   if(!ReadTextFileDual("ob_zones.json", content)) return;
   if(content == "" || content == g_ob_zones_snapshot) return;
   g_ob_zones_snapshot = content;
   g_ob_zone_count = 0;

   int pos = StringFind(content, "\"zones\"");
   if(pos < 0) return;
   int arr_start = StringFind(content, "[", pos);
   if(arr_start < 0) return;

   int p = arr_start + 1;
   while(g_ob_zone_count < 6 && p < StringLen(content)) {
      int obj_start = StringFind(content, "{", p);
      if(obj_start < 0) break;
      int obj_end = StringFind(content, "}", obj_start);
      if(obj_end < 0) break;
      string obj = StringSubstr(content, obj_start, obj_end - obj_start + 1);
      double hi_val = JsonGetDouble(obj, "high");
      double lo_val = JsonGetDouble(obj, "low");
      if(hi_val > 0 && lo_val > 0) {
         g_ob_zones_hi[g_ob_zone_count] = hi_val;
         g_ob_zones_lo[g_ob_zone_count] = lo_val;
         g_ob_zone_count++;
      }
      p = obj_end + 1;
   }
   PrintFormat("FORGE OB zones loaded: count=%d", g_ob_zone_count);
}

// ── V2: Structural SL — widen SL beyond nearest OB zone (never tighten) ──
double FindStructuralSL(bool is_buy, double entry, double atr_sl, double point) {
   double best_sl = atr_sl;
   for(int i = 0; i < g_ob_zone_count; i++) {
      if(is_buy) {
         if(g_ob_zones_lo[i] < entry && g_ob_zones_lo[i] > 0) {
            double candidate = g_ob_zones_lo[i] - 5.0 * point;
            if(candidate < best_sl && candidate > 0)
               best_sl = candidate;
         }
      } else {
         if(g_ob_zones_hi[i] > entry && g_ob_zones_hi[i] > 0) {
            double candidate = g_ob_zones_hi[i] + 5.0 * point;
            if(candidate > best_sl)
               best_sl = candidate;
         }
      }
   }
   return NormalizeDouble(best_sl, _Digits);
}

// Optional: push native scalper SL farther from entry (same units as SYMBOL_POINT).
double ApplyNativeSlExtraBuffer(const bool is_buy, double sl, const double point) {
   if(g_sc.native_sl_extra_buffer_points <= 0.0 || point <= 0.0 || sl <= 0.0)
      return NormalizeDouble(sl, _Digits);
   double delta = g_sc.native_sl_extra_buffer_points * point;
   if(is_buy)
      sl -= delta;
   else
      sl += delta;
   return NormalizeDouble(sl, _Digits);
}

// ── V2: Liquidity zone check — near POC, VWAP, or inside OB zone ──
bool NearLiquidityZone(double price, double atr) {
   if(g_poc_price > 0 && MathAbs(price - g_poc_price) <= atr * 1.5)
      return true;
   if(g_vwap_price > 0 && MathAbs(price - g_vwap_price) <= atr * 1.0)
      return true;
   for(int i = 0; i < g_ob_zone_count; i++) {
      if(price >= g_ob_zones_lo[i] && price <= g_ob_zones_hi[i])
         return true;
   }
   return false;
}

// ── Signal Journal: SQLite database ─────────────────────────────
// Ref: MQL5 Article 22009 — "Algorithmic Trading Without the Routine"
//      https://www.mql5.com/en/articles/22009

bool JournalInit() {
   if(!g_sc.journal_enabled) return true;
   bool in_tester = (MQLInfoInteger(MQL_TESTER) != 0);
   // Tester: always close previous handle and reopen to guarantee a fresh TESTER_RUNS
   // insert even when the MT5 agent reuses the EA instance across consecutive runs.
   if(in_tester && g_journal_db != INVALID_HANDLE) {
      DatabaseClose(g_journal_db);
      g_journal_db = INVALID_HANDLE;
      PrintFormat("FORGE JOURNAL: closed previous tester handle for re-init");
   }
   if(!in_tester && g_journal_db != INVALID_HANDLE) return true;

   string db_name = in_tester
      ? "FORGE_journal_" + _Symbol + "_tester.db"
      : "FORGE_journal_" + _Symbol + ".db";
   int flags = DATABASE_OPEN_READWRITE | DATABASE_OPEN_CREATE;
   if(!in_tester) flags |= DATABASE_OPEN_COMMON;

   g_journal_db = DatabaseOpen(db_name, flags);
   if(g_journal_db == INVALID_HANDLE) {
      PrintFormat("FORGE JOURNAL: failed to open %s (tester=%s) — error=%d",
                  db_name, in_tester ? "true" : "false", GetLastError());
      return false;
   }
   PrintFormat("FORGE JOURNAL: opened %s (tester=%s)", db_name, in_tester ? "true" : "false");

   string sql_signals =
      "CREATE TABLE IF NOT EXISTS SIGNALS ("
      "id INTEGER PRIMARY KEY AUTOINCREMENT, "
      "time INTEGER NOT NULL, "
      "symbol TEXT NOT NULL, "
      "setup_type TEXT, "
      "direction TEXT, "
      "outcome TEXT NOT NULL, "
      "gate_reason TEXT, "
      "price REAL, "
      "spread REAL, "
      "atr REAL, "
      "rsi REAL, "
      "adx REAL, "
      "bb_upper REAL, "
      "bb_lower REAL, "
      "bb_mid REAL, "
      "poc_price REAL, "
      "vwap_price REAL, "
      "fib_50 REAL, "
      "rsi_divergence TEXT, "
      "psar_state TEXT, "
      "pattern_score INTEGER, "
      "h1_trend REAL, "
      "regime_label TEXT, "
      "regime_confidence REAL, "
      "adx_trend_regime INTEGER, "
      "high_vol_trend INTEGER, "
      "session TEXT, "
      "magic INTEGER, "
      "synced INTEGER DEFAULT 0, "
      "macd_histogram REAL, "
      "m15_adx REAL, "
      "lot_factor REAL"
      ");";

   // TRADES schema v2: UNIQUE(deal_ticket, run_id) allows multiple tester runs
   // to accumulate in the same DB without silently losing deals.
   // For live (run_id=0 always): UNIQUE(deal_ticket,0) = UNIQUE(deal_ticket) — no change.
   string sql_trades =
      "CREATE TABLE IF NOT EXISTS TRADES ("
      "id INTEGER PRIMARY KEY AUTOINCREMENT, "
      "deal_ticket INTEGER NOT NULL, "
      "order_ticket INTEGER, "
      "symbol TEXT NOT NULL, "
      "type INTEGER, "
      "direction INTEGER, "
      "volume REAL, "
      "price REAL, "
      "profit REAL, "
      "swap REAL, "
      "commission REAL, "
      "magic INTEGER, "
      "comment TEXT, "
      "time INTEGER, "
      "time_msc INTEGER, "
      "synced INTEGER DEFAULT 0, "
      "run_id INTEGER DEFAULT 0, "
      "UNIQUE(deal_ticket, run_id)"
      ");";

   string sql_stats =
      "CREATE TABLE IF NOT EXISTS STATS_CACHE ("
      "id INTEGER PRIMARY KEY AUTOINCREMENT, "
      "computed_at INTEGER, "
      "key TEXT UNIQUE, "
      "value REAL"
      ");";

   if(!DatabaseExecute(g_journal_db, sql_signals)) {
      PrintFormat("FORGE JOURNAL: SIGNALS table error=%d", GetLastError());
      return false;
   }
   if(!DatabaseExecute(g_journal_db, sql_trades)) {
      PrintFormat("FORGE JOURNAL: TRADES table error=%d", GetLastError());
      return false;
   }
   if(!DatabaseExecute(g_journal_db, sql_stats)) {
      PrintFormat("FORGE JOURNAL: STATS_CACHE table error=%d", GetLastError());
      return false;
   }

   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_time ON SIGNALS(time);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_outcome ON SIGNALS(outcome);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_gate ON SIGNALS(gate_reason);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_setup ON SIGNALS(setup_type);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_synced ON SIGNALS(synced);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_trades_time ON TRADES(time);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_trades_magic ON TRADES(magic);");
   // Additive column migrations — silently ignored when column already exists
   DatabaseExecute(g_journal_db, "ALTER TABLE TRADES ADD COLUMN synced INTEGER DEFAULT 0;");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_trades_synced ON TRADES(synced);");
   // run_id: per-run isolation
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN run_id INTEGER DEFAULT 0;");
   DatabaseExecute(g_journal_db, "ALTER TABLE TRADES ADD COLUMN run_id INTEGER DEFAULT 0;");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_run ON SIGNALS(run_id);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_trades_run ON TRADES(run_id);");
   // ── TRADES unique-constraint migration ─────────────────────────────────────
   // Old schema used deal_ticket INTEGER UNIQUE (can't be extended via ALTER).
   // Detect it via sqlite_master and recreate the table atomically.
   {
      int chk = DatabasePrepare(g_journal_db,
         "SELECT name FROM sqlite_master WHERE type='table' AND name='TRADES' "
         "AND sql LIKE '%deal_ticket INTEGER UNIQUE%'");
      bool old_schema = false;
      if(chk != INVALID_HANDLE) {
         if(DatabaseRead(chk)) old_schema = true;
         DatabaseFinalize(chk);
      }
      if(old_schema) {
         PrintFormat("FORGE JOURNAL: migrating TRADES to UNIQUE(deal_ticket, run_id)...");
         DatabaseExecute(g_journal_db, "BEGIN TRANSACTION;");
         bool ok = true;
         ok = ok && DatabaseExecute(g_journal_db, "ALTER TABLE TRADES RENAME TO _TRADES_old;");
         ok = ok && DatabaseExecute(g_journal_db,
            "CREATE TABLE TRADES ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "deal_ticket INTEGER NOT NULL, "
            "order_ticket INTEGER, "
            "symbol TEXT NOT NULL, "
            "type INTEGER, "
            "direction INTEGER, "
            "volume REAL, "
            "price REAL, "
            "profit REAL, "
            "swap REAL, "
            "commission REAL, "
            "magic INTEGER, "
            "comment TEXT, "
            "time INTEGER, "
            "time_msc INTEGER, "
            "synced INTEGER DEFAULT 0, "
            "run_id INTEGER DEFAULT 0, "
            "UNIQUE(deal_ticket, run_id));");
         ok = ok && DatabaseExecute(g_journal_db,
            "INSERT INTO TRADES (deal_ticket, order_ticket, symbol, type, direction, "
            "volume, price, profit, swap, commission, magic, comment, time, time_msc, "
            "synced, run_id) "
            "SELECT deal_ticket, order_ticket, symbol, type, direction, "
            "volume, price, profit, swap, commission, magic, comment, time, time_msc, "
            "COALESCE(synced,0), COALESCE(run_id,0) FROM _TRADES_old;");
         ok = ok && DatabaseExecute(g_journal_db, "DROP TABLE _TRADES_old;");
         if(ok) {
            DatabaseExecute(g_journal_db, "COMMIT;");
            PrintFormat("FORGE JOURNAL: TRADES migration complete — now UNIQUE(deal_ticket, run_id)");
         } else {
            DatabaseExecute(g_journal_db, "ROLLBACK;");
            PrintFormat("FORGE JOURNAL: TRADES migration FAILED — rolled back (error=%d)", GetLastError());
         }
         DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_trades_time ON TRADES(time);");
         DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_trades_magic ON TRADES(magic);");
         DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_trades_synced ON TRADES(synced);");
         DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_trades_run ON TRADES(run_id);");
      }
   }

   if(in_tester) {
      // TESTER_RUNS schema v2: wall_time = GetTickCount64() (real clock ms, unique per run);
      // sim_start_time = TimeGMT() (simulated backtest start date); magic_base for attribution.
      DatabaseExecute(g_journal_db,
         "CREATE TABLE IF NOT EXISTS TESTER_RUNS ("
         "id INTEGER PRIMARY KEY AUTOINCREMENT, "
         "wall_time INTEGER NOT NULL, "
         "sim_start_time INTEGER, "
         "symbol TEXT, "
         "balance REAL, "
         "forge_version TEXT, "
         "scalper_mode TEXT, "
         "warmup_m5_bars INTEGER, "
         "warmup_seconds INTEGER, "
         "magic_base INTEGER"
         ");");
      // Migrate legacy TESTER_RUNS (add wall_time / sim_start_time / magic_base if missing)
      DatabaseExecute(g_journal_db, "ALTER TABLE TESTER_RUNS ADD COLUMN wall_time INTEGER NOT NULL DEFAULT 0;");
      DatabaseExecute(g_journal_db, "ALTER TABLE TESTER_RUNS ADD COLUMN sim_start_time INTEGER;");
      DatabaseExecute(g_journal_db, "ALTER TABLE TESTER_RUNS ADD COLUMN magic_base INTEGER;");
      string ins = "INSERT INTO TESTER_RUNS (wall_time, sim_start_time, symbol, balance, forge_version, scalper_mode, warmup_m5_bars, warmup_seconds, magic_base) VALUES ("
         + IntegerToString((long)GetTickCount64()) + ", "
         + IntegerToString((long)TimeGMT()) + ", '"
         + _Symbol + "', "
         + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ", '"
         + FORGE_VERSION + "', '"
         + ScalperMode + "', "
         + IntegerToString(ScalperTesterWarmupM5Bars) + ", "
         + IntegerToString(ScalperWarmupSeconds) + ", "
         + IntegerToString(MagicNumber) + ")";
      DatabaseExecute(g_journal_db, ins);
      // Read the new run's id into g_tester_run_id so all signals/trades reference it
      int rstmt = DatabasePrepare(g_journal_db, "SELECT last_insert_rowid()");
      if(rstmt != INVALID_HANDLE) {
         if(DatabaseRead(rstmt)) DatabaseColumnInteger(rstmt, 0, g_tester_run_id);
         DatabaseFinalize(rstmt);
      }
      PrintFormat("FORGE JOURNAL: tester run=%d wall_time=%I64d balance=%.2f version=%s",
                  g_tester_run_id, (long)GetTickCount64(), AccountInfoDouble(ACCOUNT_BALANCE), FORGE_VERSION);
   }

   return true;
}

void JournalClose() {
   if(g_journal_db != INVALID_HANDLE) {
      DatabaseClose(g_journal_db);
      g_journal_db = INVALID_HANDLE;
      Print("FORGE JOURNAL: database closed");
   }
}

void JournalRecordSignal(string outcome, string gate_reason,
                         string setup_type, string direction,
                         double price, double spread_val, double atr,
                         double rsi, double adx,
                         double bb_u, double bb_l, double bb_m,
                         int pattern_score, double h1_trend,
                         int high_vol_flag,
                         double macd_hist=0.0, double m15_adx_val=0.0, double lot_factor_val=0.0) {
   if(g_journal_db == INVALID_HANDLE) return;
   if(outcome == "SKIP" && !g_sc.journal_record_skips) return;

   MqlDateTime dt;
   TimeGMT(dt);
   int h = dt.hour;
   string session = "ASIAN";
   if(h >= g_sc.london_start && h < g_sc.london_end) session = "LONDON";
   else if(h >= g_sc.ny_start && h < g_sc.ny_end) session = "NY";

   string sql = "INSERT INTO SIGNALS "
      "(time, symbol, setup_type, direction, outcome, gate_reason, "
      "price, spread, atr, rsi, adx, bb_upper, bb_lower, bb_mid, "
      "poc_price, vwap_price, fib_50, rsi_divergence, psar_state, "
      "pattern_score, h1_trend, regime_label, regime_confidence, "
      "adx_trend_regime, high_vol_trend, session, magic, synced, run_id, "
      "macd_histogram, m15_adx, lot_factor) VALUES ("
      + IntegerToString((long)TimeCurrent()) + ", "
      + "'" + _Symbol + "', "
      + "'" + setup_type + "', "
      + "'" + direction + "', "
      + "'" + outcome + "', "
      + "'" + gate_reason + "', "
      + DoubleToString(price, _Digits) + ", "
      + DoubleToString(spread_val, 1) + ", "
      + DoubleToString(atr, _Digits) + ", "
      + DoubleToString(rsi, 2) + ", "
      + DoubleToString(adx, 2) + ", "
      + DoubleToString(bb_u, _Digits) + ", "
      + DoubleToString(bb_l, _Digits) + ", "
      + DoubleToString(bb_m, _Digits) + ", "
      + DoubleToString(g_poc_price, _Digits) + ", "
      + DoubleToString(g_vwap_price, _Digits) + ", "
      + DoubleToString(g_fib_50, _Digits) + ", "
      + "'" + g_rsi_div_type + "', "
      + "'" + g_psar_state + "', "
      + IntegerToString(pattern_score) + ", "
      + DoubleToString(h1_trend, 4) + ", "
      + "'" + g_regime_label + "', "
      + DoubleToString(g_regime_confidence, 4) + ", "
      + IntegerToString(g_adx_trend_regime ? 1 : 0) + ", "
      + IntegerToString(high_vol_flag) + ", "
      + "'" + session + "', "
      + IntegerToString((long)MagicNumber) + ", 0, "
      + IntegerToString(g_tester_run_id) + ", "
      + DoubleToString(macd_hist, 6) + ", "
      + DoubleToString(m15_adx_val, 2) + ", "
      + DoubleToString(lot_factor_val, 4) + ")";

   if(!DatabaseExecute(g_journal_db, sql)) {
      if(g_journal_signals_count == 0)
         PrintFormat("FORGE JOURNAL: INSERT failed error=%d", GetLastError());
      return;
   }
   g_journal_signals_count++;
}

string JournalSqlText(const string t) {
   string r = t;
   StringReplace(r, "'", "''");
   return r;
}

void JournalImportTrades() {
   if(g_journal_db == INVALID_HANDLE || !g_sc.journal_import_trades) return;

   datetime now = TimeCurrent();
   if(g_journal_last_import > 0 && (now - g_journal_last_import) < 300) return;
   g_journal_last_import = now;

   datetime from_date = now - g_sc.journal_import_depth_days * 86400;
   if(!HistorySelect(from_date, now)) return;

   int total = HistoryDealsTotal();
   int imported = 0;

   DatabaseExecute(g_journal_db, "BEGIN TRANSACTION;");

   for(int i = 0; i < total; i++) {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0) continue;

      ENUM_DEAL_TYPE dtype = (ENUM_DEAL_TYPE)HistoryDealGetInteger(ticket, DEAL_TYPE);
      if(dtype == DEAL_TYPE_BALANCE || dtype == DEAL_TYPE_CREDIT) continue;

      long deal_magic = HistoryDealGetInteger(ticket, DEAL_MAGIC);
      // +29999 covers primary group magics (+5001..+5099) AND all cascade/limit magics
      // (+20000 SELL_LIMIT_L1, +20001 SELL_LIMIT_L2, +20002/+20003 SELL_STOP_CONT, +20004 BUY_LIMIT).
      if(deal_magic < MagicNumber || deal_magic > MagicNumber + 29999) continue;

      ENUM_DEAL_ENTRY deal_entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY);
      int dir = 0;
      if(deal_entry == DEAL_ENTRY_OUT) dir = 1;
      else if(deal_entry == DEAL_ENTRY_INOUT) dir = 2;
      else if(deal_entry == DEAL_ENTRY_OUT_BY) dir = 3;

      string ins = "INSERT OR IGNORE INTO TRADES (deal_ticket, order_ticket, symbol, type, direction, volume, price, "
         "profit, swap, commission, magic, comment, time, time_msc, run_id) VALUES ("
         + IntegerToString((long)ticket) + ", "
         + IntegerToString((long)HistoryDealGetInteger(ticket, DEAL_ORDER)) + ", "
         + "'" + JournalSqlText(HistoryDealGetString(ticket, DEAL_SYMBOL)) + "', "
         + IntegerToString((int)dtype) + ", "
         + IntegerToString(dir) + ", "
         + DoubleToString(HistoryDealGetDouble(ticket, DEAL_VOLUME), 8) + ", "
         + DoubleToString(HistoryDealGetDouble(ticket, DEAL_PRICE), (int)_Digits) + ", "
         + DoubleToString(HistoryDealGetDouble(ticket, DEAL_PROFIT), 2) + ", "
         + DoubleToString(HistoryDealGetDouble(ticket, DEAL_SWAP), 2) + ", "
         + DoubleToString(HistoryDealGetDouble(ticket, DEAL_COMMISSION), 2) + ", "
         + IntegerToString((long)deal_magic) + ", "
         + "'" + JournalSqlText(HistoryDealGetString(ticket, DEAL_COMMENT)) + "', "
         + IntegerToString((long)HistoryDealGetInteger(ticket, DEAL_TIME)) + ", "
         + IntegerToString((long)HistoryDealGetInteger(ticket, DEAL_TIME_MSC)) + ", "
         + IntegerToString(g_tester_run_id) + ")";

      if(DatabaseExecute(g_journal_db, ins))
         imported++;
   }

   DatabaseExecute(g_journal_db, "COMMIT;");

   if(imported > 0)
      PrintFormat("FORGE JOURNAL: imported %d deals", imported);
}

void JournalComputeStats() {
   if(g_journal_db == INVALID_HANDLE) return;

   datetime now = TimeCurrent();
   if(g_journal_last_stats > 0 &&
      (now - g_journal_last_stats) < g_sc.journal_stats_interval_sec) return;
   g_journal_last_stats = now;

   // Scope stats to current run when in tester mode — prevents multi-run contamination.
   bool in_tester_stats = (MQLInfoInteger(MQL_TESTER) != 0) && (g_tester_run_id > 0);
   string run_filter = in_tester_stats ? " AND run_id = " + IntegerToString(g_tester_run_id) : "";

   string sql_hr = "SELECT "
      "CAST(strftime('%H', time, 'unixepoch') AS INTEGER) as hour, "
      "COUNT(*) as trades, "
      "SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins, "
      "SUM(profit + swap + commission) as net_pnl "
      "FROM TRADES WHERE direction IN (1,2,3)" + run_filter + " "
      "GROUP BY hour ORDER BY hour";

   int stmt = DatabasePrepare(g_journal_db, sql_hr);
   if(stmt != INVALID_HANDLE) {
      DatabaseExecute(g_journal_db, "DELETE FROM STATS_CACHE WHERE key LIKE 'hour_%'");
      string upsert_sql = "INSERT OR REPLACE INTO STATS_CACHE (computed_at, key, value) VALUES (?, ?, ?)";
      while(DatabaseRead(stmt)) {
         int hour_val; double trades_d, wins_d, pnl;
         DatabaseColumnInteger(stmt, 0, hour_val);
         DatabaseColumnDouble(stmt, 1, trades_d);
         DatabaseColumnDouble(stmt, 2, wins_d);
         DatabaseColumnDouble(stmt, 3, pnl);
         double wr = (trades_d > 0) ? (wins_d / trades_d * 100.0) : 0;

         int us;
         us = DatabasePrepare(g_journal_db, upsert_sql);
         if(us != INVALID_HANDLE) {
            DatabaseBind(us, 0, (long)now);
            DatabaseBind(us, 1, StringFormat("hour_%02d_winrate", hour_val));
            DatabaseBind(us, 2, wr);
            DatabaseRead(us); DatabaseFinalize(us);
         }
         us = DatabasePrepare(g_journal_db, upsert_sql);
         if(us != INVALID_HANDLE) {
            DatabaseBind(us, 0, (long)now);
            DatabaseBind(us, 1, StringFormat("hour_%02d_pnl", hour_val));
            DatabaseBind(us, 2, pnl);
            DatabaseRead(us); DatabaseFinalize(us);
         }
         us = DatabasePrepare(g_journal_db, upsert_sql);
         if(us != INVALID_HANDLE) {
            DatabaseBind(us, 0, (long)now);
            DatabaseBind(us, 1, StringFormat("hour_%02d_trades", hour_val));
            DatabaseBind(us, 2, trades_d);
            DatabaseRead(us); DatabaseFinalize(us);
         }
      }
      DatabaseFinalize(stmt);
   }

   string sql_gates = "SELECT gate_reason, COUNT(*) as cnt "
      "FROM SIGNALS WHERE outcome='SKIP' AND gate_reason != ''" + run_filter + " "
      "GROUP BY gate_reason ORDER BY cnt DESC";

   stmt = DatabasePrepare(g_journal_db, sql_gates);
   if(stmt != INVALID_HANDLE) {
      DatabaseExecute(g_journal_db, "DELETE FROM STATS_CACHE WHERE key LIKE 'gate_%'");
      while(DatabaseRead(stmt)) {
         string gate; double cnt;
         DatabaseColumnText(stmt, 0, gate);
         DatabaseColumnDouble(stmt, 1, cnt);
         int us = DatabasePrepare(g_journal_db,
            "INSERT OR REPLACE INTO STATS_CACHE (computed_at, key, value) VALUES (?, ?, ?)");
         if(us != INVALID_HANDLE) {
            DatabaseBind(us, 0, (long)now);
            DatabaseBind(us, 1, "gate_" + gate);
            DatabaseBind(us, 2, cnt);
            DatabaseRead(us); DatabaseFinalize(us);
         }
      }
      DatabaseFinalize(stmt);
   }

   PrintFormat("FORGE JOURNAL: stats refreshed — %d signals this session", g_journal_signals_count);
}

// After attach: require enough history on M5/M15/M30/H1/H4, synchronized series,
// full indicator buffers on those TFs, optional PSAR; then ScalperTesterWarmup* (Tester), Live M15 rollovers (live), optional extra seconds.
// Tester fast-start: when ScalperTesterWarmupM5Bars==0 the operator is saying "fire as soon as indicators are readable" —
// skip the bar-count and sync proxy checks and rely solely on CopyBuffer readiness probes below.
bool ForgeNativeScalperWarmupOk(string &reason_out) {
   reason_out = "";
   const bool in_tester = (MQLInfoInteger(MQL_TESTER) != 0);
   if(SymbolInfoDouble(_Symbol, SYMBOL_BID) <= 0.0 || SymbolInfoDouble(_Symbol, SYMBOL_ASK) <= 0.0) {
      reason_out = "no_quotes";
      return false;
   }
   // Bar-count + sync proxy: enforced live always; enforced in tester only when WarmupM5Bars>0.
   // When WarmupM5Bars==0, CopyBuffer probes below are the sole readiness gate.
   const bool do_bar_checks = !in_tester || (ScalperTesterWarmupM5Bars > 0);
   if(do_bar_checks) {
      const int need_bars = 70;  // covers EMA50 / BB20 / ATR14 with margin
      if(Bars(_Symbol, PERIOD_M5) < need_bars) { reason_out = "m5_bars"; return false; }
      if(Bars(_Symbol, PERIOD_M15) < need_bars) { reason_out = "m15_bars"; return false; }
      if(Bars(_Symbol, PERIOD_M30) < need_bars) { reason_out = "m30_bars"; return false; }
      if(Bars(_Symbol, PERIOD_H1) < need_bars) { reason_out = "h1_bars"; return false; }
      if(Bars(_Symbol, PERIOD_H4) < need_bars) { reason_out = "h4_bars"; return false; }
   }
   string m1_mode_trim = NativeScalperM1Mode;
   StringTrimLeft(m1_mode_trim);
   StringTrimRight(m1_mode_trim);
   const bool m1_used = (m1_mode_trim != "" && m1_mode_trim != "NONE");
   if(do_bar_checks) {
      if(m1_used && Bars(_Symbol, PERIOD_M1) < 70) { reason_out = "m1_bars"; return false; }
      if(!SeriesInfoInteger(_Symbol, PERIOD_M5, SERIES_SYNCHRONIZED)) { reason_out = "m5_unsynced"; return false; }
      if(!SeriesInfoInteger(_Symbol, PERIOD_M15, SERIES_SYNCHRONIZED)) { reason_out = "m15_unsynced"; return false; }
      if(!SeriesInfoInteger(_Symbol, PERIOD_M30, SERIES_SYNCHRONIZED)) { reason_out = "m30_unsynced"; return false; }
      if(!SeriesInfoInteger(_Symbol, PERIOD_H1, SERIES_SYNCHRONIZED)) { reason_out = "h1_unsynced"; return false; }
      if(!SeriesInfoInteger(_Symbol, PERIOD_H4, SERIES_SYNCHRONIZED)) { reason_out = "h4_unsynced"; return false; }
      if(m1_used && !SeriesInfoInteger(_Symbol, PERIOD_M1, SERIES_SYNCHRONIZED)) { reason_out = "m1_unsynced"; return false; }
   }

   const string mtf_lbl[3] = {"m5", "m15", "m30"};
   for(int mi = 0; mi < 3; mi++) {
      if(g_mtf[mi].h_rsi == INVALID_HANDLE || g_mtf[mi].h_adx == INVALID_HANDLE || g_mtf[mi].h_bb == INVALID_HANDLE
         || g_mtf[mi].h_atr == INVALID_HANDLE || g_mtf[mi].h_ma20 == INVALID_HANDLE || g_mtf[mi].h_ma50 == INVALID_HANDLE
         || g_mtf[mi].h_macd == INVALID_HANDLE) {
         reason_out = mtf_lbl[mi] + "_handles";
         return false;
      }
      double probe[2];
      if(CopyBuffer(g_mtf[mi].h_rsi, 0, 0, 2, probe) != 2) { reason_out = mtf_lbl[mi] + "_rsi_buf"; return false; }
      if(CopyBuffer(g_mtf[mi].h_adx, 0, 0, 2, probe) != 2) { reason_out = mtf_lbl[mi] + "_adx_buf"; return false; }
      if(CopyBuffer(g_mtf[mi].h_bb, 0, 0, 2, probe) != 2) { reason_out = mtf_lbl[mi] + "_bb_mid_buf"; return false; }
      if(CopyBuffer(g_mtf[mi].h_bb, 1, 0, 2, probe) != 2) { reason_out = mtf_lbl[mi] + "_bb_up_buf"; return false; }
      if(CopyBuffer(g_mtf[mi].h_bb, 2, 0, 2, probe) != 2) { reason_out = mtf_lbl[mi] + "_bb_lo_buf"; return false; }
      if(CopyBuffer(g_mtf[mi].h_atr, 0, 0, 2, probe) != 2) { reason_out = mtf_lbl[mi] + "_atr_buf"; return false; }
      if(CopyBuffer(g_mtf[mi].h_ma20, 0, 0, 2, probe) != 2) { reason_out = mtf_lbl[mi] + "_ema20_buf"; return false; }
      if(CopyBuffer(g_mtf[mi].h_ma50, 0, 0, 2, probe) != 2) { reason_out = mtf_lbl[mi] + "_ema50_buf"; return false; }
      // iMACD has only 2 buffers (0=main, 1=signal); buffer 2 (histogram) does not exist — no probe needed.
      // MACD is not used for entry decisions; WriteMTFBlock handles CopyBuffer failure as 0.
   }

   if(g_h_rsi == INVALID_HANDLE || g_h_bb == INVALID_HANDLE || g_h_macd == INVALID_HANDLE || g_h_adx == INVALID_HANDLE
      || g_h_ma20 == INVALID_HANDLE || g_h_ma50 == INVALID_HANDLE || g_h_atr == INVALID_HANDLE) {
      reason_out = "h1_handles";
      return false;
   }
   double pb[2];
   if(CopyBuffer(g_h_rsi, 0, 0, 2, pb) != 2) { reason_out = "h1_rsi_buf"; return false; }
   if(CopyBuffer(g_h_bb, 0, 0, 2, pb) != 2) { reason_out = "h1_bb_mid_buf"; return false; }
   if(CopyBuffer(g_h_bb, 1, 0, 2, pb) != 2) { reason_out = "h1_bb_up_buf"; return false; }
   if(CopyBuffer(g_h_bb, 2, 0, 2, pb) != 2) { reason_out = "h1_bb_lo_buf"; return false; }
   // iMACD buffer 2 does not exist; WriteMarketData handles CopyBuffer failure for MACD as 0.
   if(CopyBuffer(g_h_adx, 0, 0, 2, pb) != 2) { reason_out = "h1_adx_buf"; return false; }
   if(CopyBuffer(g_h_ma20, 0, 0, 2, pb) != 2) { reason_out = "h1_ema20_buf"; return false; }
   if(CopyBuffer(g_h_ma50, 0, 0, 2, pb) != 2) { reason_out = "h1_ema50_buf"; return false; }
   if(CopyBuffer(g_h_atr, 0, 0, 2, pb) != 2) { reason_out = "h1_atr_buf"; return false; }

   if(g_h4_ma20 == INVALID_HANDLE || g_h4_ma50 == INVALID_HANDLE || g_h4_atr == INVALID_HANDLE) {
      reason_out = "h4_handles";
      return false;
   }
   if(CopyBuffer(g_h4_ma20, 0, 0, 2, pb) != 2) { reason_out = "h4_ema20_buf"; return false; }
   if(CopyBuffer(g_h4_ma50, 0, 0, 2, pb) != 2) { reason_out = "h4_ema50_buf"; return false; }
   if(CopyBuffer(g_h4_atr, 0, 0, 2, pb) != 2) { reason_out = "h4_atr_buf"; return false; }

   if(m1_used) {
      if(g_m1_ma20 == INVALID_HANDLE || g_m1_ma50 == INVALID_HANDLE || g_m1_atr == INVALID_HANDLE) {
         reason_out = "m1_handles";
         return false;
      }
      if(CopyBuffer(g_m1_ma20, 0, 0, 2, pb) != 2) { reason_out = "m1_ema20_buf"; return false; }
      if(CopyBuffer(g_m1_ma50, 0, 0, 2, pb) != 2) { reason_out = "m1_ema50_buf"; return false; }
      if(CopyBuffer(g_m1_atr, 0, 0, 2, pb) != 2) { reason_out = "m1_atr_buf"; return false; }
   }

   if(g_sc.psar_enabled) {
      if(g_h_psar == INVALID_HANDLE) { reason_out = "psar_handle"; return false; }
      if(CopyBuffer(g_h_psar, 0, 0, 2, pb) != 2) { reason_out = "psar_buf"; return false; }
   }

   if(g_poc_price <= 0.0) { reason_out = "vp_poc_uninit"; return false; }

   if(in_tester && ScalperTesterWarmupM5Bars > 0) {
      bool require_m5_rollovers = true;
      if(ScalperTesterWarmupSimCapMinutes > 0) {
         const int sim_elapsed_sec = (int)(TimeGMT() - g_forge_init_gmt);
         if(sim_elapsed_sec >= ScalperTesterWarmupSimCapMinutes * 60)
            require_m5_rollovers = false;
      }
      if(require_m5_rollovers) {
         datetime m5t = iTime(_Symbol, PERIOD_M5, 0);
         if(g_warmup_m5_time_ref == 0)
            g_warmup_m5_time_ref = m5t;
         else if(m5t != g_warmup_m5_time_ref) {
            g_warmup_m5_rollover_count++;
            g_warmup_m5_time_ref = m5t;
         }
         if(g_warmup_m5_rollover_count < ScalperTesterWarmupM5Bars) {
            reason_out = "tester_m5_rollovers";
            return false;
         }
      }
   }

   if(!in_tester && ScalperLiveWarmupM15Bars > 0) {
      datetime m15t = iTime(_Symbol, PERIOD_M15, 0);
      if(g_warmup_m15_time_ref == 0)
         g_warmup_m15_time_ref = m15t;
      else if(m15t != g_warmup_m15_time_ref) {
         g_warmup_m15_rollover_count++;
         g_warmup_m15_time_ref = m15t;
      }
      if(g_warmup_m15_rollover_count < ScalperLiveWarmupM15Bars) {
         reason_out = "live_m15_rollovers";
         return false;
      }
   }

   if(ScalperWarmupSeconds > 0) {
      int elapsed = (int)(TimeGMT() - g_forge_init_gmt);
      if(elapsed < ScalperWarmupSeconds) {
         reason_out = "warmup_delay";
         return false;
      }
   }
   return true;
}

// Count currently open (live positions or active staging) groups for a specific direction.
// Uses g_groups[] which the lifecycle fix keeps accurate — no MT5 API query needed.
int ScalperOpenGroupCountByDirection(const string direction) {
   int count = 0;
   for(int i = 0; i < ArraySize(g_groups); i++) {
      if(g_groups[i].direction == direction) count++;
   }
   return count;
}

bool IsTesting() {
   return (MQLInfoInteger(MQL_TESTER) != 0);
}

void ScalperNewsFilterRefresh() {
   datetime now = TimeTradeServer();
   g_nf_next_refresh = now + g_sc.news_filter_refresh_sec;
   g_nf_have_window = false;
   g_nf_block_start = 0;
   g_nf_block_end = 0;
   g_nf_event_time = 0;
   g_nf_block_reason = "";

   int max_before = MathMax(g_sc.news_filter_high_before, MathMax(g_sc.news_filter_medium_before, g_sc.news_filter_low_before));
   int max_after = MathMax(g_sc.news_filter_high_after, MathMax(g_sc.news_filter_medium_after, g_sc.news_filter_low_after));
   string special_parts[];
   int special_count = StringSplit(g_sc.news_filter_special, '+', special_parts);
   for(int s = 0; s < special_count; s++) {
      string part = special_parts[s];
      StringTrimLeft(part);
      StringTrimRight(part);
      int colon = StringFind(part, ":");
      int comma = StringFind(part, ",", colon + 1);
      if(colon > 0 && comma > colon) {
         int sp_before = (int)StringToInteger(StringSubstr(part, colon + 1, comma - colon - 1));
         int sp_after = (int)StringToInteger(StringSubstr(part, comma + 1));
         if(sp_before > max_before) max_before = sp_before;
         if(sp_after > max_after) max_after = sp_after;
      }
   }

   // Expand "ALL" to full 9-currency list; split by comma+space; deduplicate
   string ALL_CURRENCIES[] = {"USD","EUR","GBP","JPY","AUD","CAD","CHF","NZD","CNY"};
   string raw_cur = g_sc.news_filter_currencies;
   StringReplace(raw_cur, " ", ",");
   string tokens[];
   int n_tok = StringSplit(raw_cur, ',', tokens);
   string currencies[];
   int ccount = 0;
   for(int ti = 0; ti < n_tok; ti++) {
      string t = tokens[ti];
      StringTrimLeft(t); StringTrimRight(t); StringToUpper(t);
      if(StringLen(t) == 0) continue;
      if(t == "ALL") {
         for(int ai = 0; ai < ArraySize(ALL_CURRENCIES); ai++) {
            bool dup = false;
            for(int bi = 0; bi < ccount; bi++)
               if(currencies[bi] == ALL_CURRENCIES[ai]) { dup = true; break; }
            if(!dup) { ArrayResize(currencies, ccount+1); currencies[ccount++] = ALL_CURRENCIES[ai]; }
         }
      } else {
         bool dup = false;
         for(int bi = 0; bi < ccount; bi++)
            if(currencies[bi] == t) { dup = true; break; }
         if(!dup) { ArrayResize(currencies, ccount+1); currencies[ccount++] = t; }
      }
   }

   datetime from_time = now - max_after * 60;
   datetime to_time = now + max_before * 60;
   long best_distance = LONG_MAX;

   for(int c = 0; c < ccount; c++) {
      string cur = currencies[c];

      MqlCalendarValue values[];
      if(!CalendarValueHistory(values, from_time, to_time, NULL, cur)) {
         if(IsTesting())
            PrintFormat("FORGE NEWS FILTER: CalendarValueHistory returned false for currency=%s", cur);
         continue;
      }

      for(int i = 0; i < ArraySize(values); i++) {
         if(values[i].time <= 0) continue;   // guard: skip invalid event times
         MqlCalendarEvent ev;
         if(!CalendarEventById(values[i].event_id, ev))
            continue;

         int before_min = g_sc.news_filter_low_before;
         int after_min = g_sc.news_filter_low_after;
         string impact = "LOW";
         if(ev.importance == CALENDAR_IMPORTANCE_HIGH) {
            before_min = g_sc.news_filter_high_before;
            after_min = g_sc.news_filter_high_after;
            impact = "HIGH";
         } else if(ev.importance == CALENDAR_IMPORTANCE_MODERATE) {
            before_min = g_sc.news_filter_medium_before;
            after_min = g_sc.news_filter_medium_after;
            impact = "MEDIUM";
         }

         string ev_name = ev.name;
         string ev_name_uc = ev_name;
         StringToUpper(ev_name_uc);
         for(int sp = 0; sp < special_count; sp++) {
            string spec = special_parts[sp];
            StringTrimLeft(spec);
            StringTrimRight(spec);
            int sp_colon = StringFind(spec, ":");
            int sp_comma = StringFind(spec, ",", sp_colon + 1);
            if(sp_colon <= 0 || sp_comma <= sp_colon) continue;
            string keyword = StringSubstr(spec, 0, sp_colon);
            StringTrimLeft(keyword);
            StringTrimRight(keyword);
            string keyword_uc = keyword;
            StringToUpper(keyword_uc);
            if(StringLen(keyword_uc) > 0 && StringFind(ev_name_uc, keyword_uc) >= 0) {
               before_min = (int)StringToInteger(StringSubstr(spec, sp_colon + 1, sp_comma - sp_colon - 1));
               after_min = (int)StringToInteger(StringSubstr(spec, sp_comma + 1));
               impact = "SPECIAL";
            }
         }

         datetime ev_time = values[i].time;
         datetime start = ev_time - before_min * 60;
         datetime end = ev_time + after_min * 60;
         if(now > end)
            continue;

         long dist = (now < start) ? (long)(start - now) : (long)MathAbs((double)(now - ev_time));
         if(dist < best_distance) {
            best_distance = dist;
            g_nf_block_start = start;
            g_nf_block_end = end;
            g_nf_event_time = ev_time;
            g_nf_block_reason = StringFormat("%s %s %s", cur, impact, ev_name);
            g_nf_have_window = true;
         }
      }
   }
}

double ScalperNewsProximity() {
   datetime now = TimeTradeServer();
   if(g_nf_have_window && now > g_nf_block_end) {
      ScalperNewsFilterRefresh();
      now = TimeTradeServer();
   }
   if(!g_nf_have_window || now < g_nf_block_start || now > g_nf_block_end)
      return -1.0;

   // Asymmetric proximity per design spec:
   // Pre-news:  p = (now - window_start) / (event_time - window_start)  → 0.0 at window open, 1.0 at event
   // Post-news: p = (window_end - now)   / (window_end - event_time)    → 1.0 at event, 0.0 at window close
   if(now <= g_nf_event_time) {
      double denom = (double)(g_nf_event_time - g_nf_block_start);
      if(denom <= 0.0) return 1.0;
      return MathMin(1.0, (double)(now - g_nf_block_start) / denom);
   } else {
      double denom = (double)(g_nf_block_end - g_nf_event_time);
      if(denom <= 0.0) return 1.0;
      return MathMin(1.0, (double)(g_nf_block_end - now) / denom);
   }
}

int ScalperNewsCheck() {
   double proximity = ScalperNewsProximity();
   if(proximity < 0.0) {
      g_nf_eff_rsi_buy_ceil = g_sc.breakout_rsi_buy_ceil;
      g_nf_eff_rsi_sell_min = g_sc.breakout_rsi_sell_floor;
      return 0;
   }

   datetime now = TimeTradeServer();
   if(g_sc.news_filter_hard_floor_min > 0
      && now >= g_nf_event_time
      && now <= g_nf_event_time + g_sc.news_filter_hard_floor_min * 60)
      return 2;

   if(proximity >= g_sc.news_filter_block_pct)
      return 2;

   if(proximity >= g_sc.news_filter_tighten_pct) {
      double slide = (proximity - g_sc.news_filter_tighten_pct)
                     / MathMax(0.001, g_sc.news_filter_block_pct - g_sc.news_filter_tighten_pct);
      slide = MathMin(1.0, slide);
      g_nf_eff_rsi_buy_ceil = g_sc.breakout_rsi_buy_ceil   - (g_sc.breakout_rsi_buy_ceil   - g_sc.news_filter_tighten_rsi_buy)  * slide;
      g_nf_eff_rsi_sell_min = g_sc.breakout_rsi_sell_floor + (g_sc.news_filter_tighten_rsi_sell - g_sc.breakout_rsi_sell_floor) * slide;
      return 1;
   }

   g_nf_eff_rsi_buy_ceil = g_sc.breakout_rsi_buy_ceil;
   g_nf_eff_rsi_sell_min = g_sc.breakout_rsi_sell_floor;
   return 0;
}

int ScalperNewsUpdateEffectiveThresholds(string &ev_label) {
   g_nf_eff_rsi_buy_ceil = g_sc.breakout_rsi_buy_ceil;
   g_nf_eff_rsi_sell_min = g_sc.breakout_rsi_sell_floor;
   ev_label = "";
   if(!g_sc.news_filter_enabled) return 0;
   if(IsTesting() && !g_sc.news_filter_apply_in_tester) return 0;
   datetime now = TimeTradeServer();
   if(g_nf_next_refresh == 0 || now >= g_nf_next_refresh)
      ScalperNewsFilterRefresh();
   int state = ScalperNewsCheck();
   ev_label = g_nf_block_reason;
   return state;
}

// ─────────────────────────────────────────────────────────────────────────────
// CheckEntryQuality — M5 bar structure pre-filter
//
// PURPOSE: Reject low-quality candle setups before committing to indicator
//   computation or order placement. Checks are ordered cheapest-first.
//
// EVALUATION ORDER (each gate returns false + logs SKIP on failure):
//   -1. News filter hard-block    — stop immediately if high-impact event active
//    0. Same-direction open cap   — prevent stacking same-direction exposure
//    1. ATR floor                 — reject compressed/noise markets (min_entry_atr)
//    2. Body ratio                — reject doji / wick-dominant bars (min_body_ratio)
//    3. Directional alignment     — reject bars where candle closes disagree with direction
//    4. BB expansion              — reject when bands are contracting (require_bb_expansion)
//    5. ADX spike-from-flat       — reject SELL when ADX spiked recently without sustained trend
//
// PARAMETERS:
//   direction     — "BUY" or "SELL"
//   atr           — current M5 ATR value (already computed by caller)
//   bb_upper_now  — current M5 BB upper band
//   bb_lower_now  — current M5 BB lower band
//   rsi           — current M5 RSI (passed for logging — not used in gate logic here)
//   adx           — current M5 ADX (passed for logging — not used in gate logic here)
//
// NOTE ON LOGGING: rsi/adx are passed solely so JournalRecordSignal can log
//   meaningful indicator values. Previously these were hardcoded 0 which made
//   gate precision analysis impossible. Fix: 2026-05-10 (Run 10 prep).
//
// CHANGELOG:
//   2026-05-10  Pass rsi/adx through signature; fixes RSI=0/ADX=0 in SKIP logs. See CHANGELOG.md.
// ─────────────────────────────────────────────────────────────────────────────
bool CheckEntryQuality(const string direction, const double atr,
                       const double bb_upper_now, const double bb_lower_now,
                       const double rsi, const double adx) {
   // -1. Native news filter — hard block only
   {
      string nf_ev = "";
      int nf_state = ScalperNewsUpdateEffectiveThresholds(nf_ev);
      if(nf_state == 2) {  // BLOCK
         datetime cur_bar = iTime(_Symbol, PERIOD_M5, 0);
         if(cur_bar != g_scalper_last_newsfilter_log_bar) {
            g_scalper_last_newsfilter_log_bar = cur_bar;
            JournalRecordSignal("SKIP","entry_quality_news_filter","",direction,
               SymbolInfoDouble(_Symbol,SYMBOL_BID),0,atr,rsi,adx,bb_upper_now,bb_lower_now,0,0,0,0);
            Print("FORGE SCALPER: skip gate=entry_quality_news_filter event=[", nf_ev, "]");
         }
         return false;
      }
      // state 1 (TIGHTEN) or 0 (ALLOW): g_nf_eff_rsi_buy_ceil/sell_min updated, passed to BB gates below
   }
   // 0. Per-direction open group cap — prevent stacking same-direction exposure
   if(g_sc.max_open_same_direction > 0) {
      int dir_open = ScalperOpenGroupCountByDirection(direction);
      if(dir_open >= g_sc.max_open_same_direction) {
         JournalRecordSignal("SKIP","entry_quality_direction_cap","",direction,
            SymbolInfoDouble(_Symbol,SYMBOL_BID),0,atr,rsi,adx,bb_upper_now,bb_lower_now,0,0,0,0);
         return false;
      }
   }
   // 1. Minimum ATR floor — no entries in compressed/noise markets
   //    atr < min_entry_atr → entry_quality_atr SKIP
   if(g_sc.min_entry_atr > 0.0 && atr < g_sc.min_entry_atr) {
      JournalRecordSignal("SKIP","entry_quality_atr","",direction,
         SymbolInfoDouble(_Symbol,SYMBOL_BID),0,atr,rsi,adx,bb_upper_now,bb_lower_now,0,0,0,0);
      return false;
   }
   // 2+3. Body ratio & directional alignment — evaluated over last entry_quality_bars M5 bars
   //   Body ratio: avg (bar_body / bar_range) across N bars — filters doji/wick-dominant candles.
   //   Directional: count of bars where close agrees with trade direction (c<o for SELL, c>o for BUY).
   //   Both checks use only OHLC data — no indicator dependency, safe to run before RSI/ADX gating.
   int n = MathMax(1, g_sc.entry_quality_bars);
   double total_body_ratio = 0.0;
   int directional_count = 0;
   for(int i = 1; i <= n; i++) {
      double o = iOpen(_Symbol,  PERIOD_M5, i);
      double c = iClose(_Symbol, PERIOD_M5, i);
      double h = iHigh(_Symbol,  PERIOD_M5, i);
      double l = iLow(_Symbol,   PERIOD_M5, i);
      double candle_range = h - l;
      double body         = MathAbs(c - o);
      total_body_ratio += (candle_range > 0.0) ? (body / candle_range) : 1.0;
      if(direction == "SELL" && c < o) directional_count++;
      if(direction == "BUY"  && c > o) directional_count++;
   }
   double avg_body_ratio = total_body_ratio / n;
   // rsi/adx now logged correctly — previously hardcoded 0 (fix: 2026-05-10)
   if(g_sc.min_body_ratio > 0.0 && avg_body_ratio < g_sc.min_body_ratio) {
      JournalRecordSignal("SKIP","entry_quality_body","",direction,
         SymbolInfoDouble(_Symbol,SYMBOL_BID),0,atr,rsi,adx,bb_upper_now,bb_lower_now,0,0,0,0);
      return false;
   }
   if(g_sc.min_directional_bars > 0 && directional_count < g_sc.min_directional_bars) {
      JournalRecordSignal("SKIP","entry_quality_direction","",direction,
         SymbolInfoDouble(_Symbol,SYMBOL_BID),0,atr,rsi,adx,bb_upper_now,bb_lower_now,0,0,0,0);
      return false;
   }
   // 4. BB band expansion — reject entries when bands are contracting (< 95% of previous width).
   //    Contracting bands = market losing momentum/entering squeeze. Breakout entries in squeezes
   //    tend to reverse quickly. Controlled by require_bb_expansion config flag.
   if(g_sc.require_bb_expansion && g_mtf[0].h_bb != INVALID_HANDLE) {
      double buf1[1];
      double bb_upper_prev = (CopyBuffer(g_mtf[0].h_bb, 1, 1, 1, buf1)==1) ? buf1[0] : 0.0;
      double bb_lower_prev = (CopyBuffer(g_mtf[0].h_bb, 2, 1, 1, buf1)==1) ? buf1[0] : 0.0;
      double width_now  = bb_upper_now  - bb_lower_now;
      double width_prev = bb_upper_prev - bb_lower_prev;
      if(width_prev > 0.0 && width_now < width_prev * 0.95) {
         JournalRecordSignal("SKIP","entry_quality_bb_contraction","",direction,
            SymbolInfoDouble(_Symbol,SYMBOL_BID),0,atr,rsi,adx,bb_upper_now,bb_lower_now,0,0,0,0);
         return false;
      }
   }
   return true;
}

void CheckNativeScalperSetups() {
   EnsureIndicators();
   EnsureMTFIndicators();
   MqlDateTime dt;
   TimeGMT(dt);
   int hour = dt.hour;
   double spread = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / _Point;
   int open_groups = ScalperOpenGroupCount();

   // Safety guards
   // Live: London/NY session window. Tester: skip — simulated TimeGMT() often sits outside 07–20 UTC for
   // long stretches of a backtest (or the whole range), which zeroes out entries despite valid setups.
   bool session_blocked = false;
   if(MQLInfoInteger(MQL_TESTER) == 0 && !ScalperSessionOK())
      session_blocked = true;
   else if(MQLInfoInteger(MQL_TESTER) != 0 && !ScalperTesterSessionOK())
      session_blocked = true;
   if(session_blocked) {
      datetime m5bar = iTime(_Symbol, PERIOD_M5, 0);
      if(m5bar != g_scalper_last_sesswarn_log_bar) {
         g_scalper_last_sesswarn_log_bar = m5bar;
         PrintFormat("FORGE SCALPER: skip gate=session_off hour=%d UTC — london=%d-%d ny=%d-%d (no trades this hour)",
                     hour, g_sc.london_start, g_sc.london_end, g_sc.ny_start, g_sc.ny_end);
         JournalRecordSignal("SKIP","session_off","","",SymbolInfoDouble(_Symbol,SYMBOL_BID),spread,0,0,0,0,0,0,0,0,0);
      }
      g_scalper_prev_session_blocked = true;
      return;
   }
   // Session-start visibility log (2.7.4): fire once on session_off → active transition
   if(g_scalper_prev_session_blocked) {
      double _ss_buf[1];
      double adx_now_ss = (CopyBuffer(g_mtf[0].h_adx, 0, 0, 1, _ss_buf)==1) ? _ss_buf[0] : 0.0;
      double adx_lb_ss  = (CopyBuffer(g_mtf[0].h_adx, 0, 6, 1, _ss_buf)==1) ? _ss_buf[0] : 0.0;
      double rsi_ss     = (CopyBuffer(g_mtf[0].h_rsi, 0, 0, 1, _ss_buf)==1) ? _ss_buf[0] : 0.0;
      double bbu_now    = (CopyBuffer(g_mtf[0].h_bb,  1, 0, 1, _ss_buf)==1) ? _ss_buf[0] : 0.0;
      double bbl_now    = (CopyBuffer(g_mtf[0].h_bb,  2, 0, 1, _ss_buf)==1) ? _ss_buf[0] : 0.0;
      double bbu_prev   = (CopyBuffer(g_mtf[0].h_bb,  1, 1, 1, _ss_buf)==1) ? _ss_buf[0] : 0.0;
      double bbl_prev   = (CopyBuffer(g_mtf[0].h_bb,  2, 1, 1, _ss_buf)==1) ? _ss_buf[0] : 0.0;
      double w_now  = bbu_now  - bbl_now;
      double w_prev = bbu_prev - bbl_prev;
      bool bb_exp = (w_prev > 0.0 && w_now > w_prev);
      PrintFormat("FORGE SESSION START: hour=%dUTC adx=%.1f adx_30min_ago=%.1f rsi=%.1f bb=%s (width %.2f→%.2f)",
                  hour, adx_now_ss, adx_lb_ss, rsi_ss,
                  bb_exp ? "EXPANDING" : "FLAT/CONTRACTING", w_prev, w_now);
   }
   g_scalper_prev_session_blocked = false;
   // Live: enforce max spread. Tester: skip — modeled XAU spread often sits above typical live caps and
   // would block nearly every tick (see Agent logs: spread 26–31 vs max 25), distorting backtest results.
   if(MQLInfoInteger(MQL_TESTER) == 0 && spread > g_sc.max_spread_points) {
      PrintFormat("FORGE SCALPER: skip gate=spread spread=%.1f max=%.1f", spread, g_sc.max_spread_points);
      JournalRecordSignal("SKIP","spread","","",SymbolInfoDouble(_Symbol,SYMBOL_BID),spread,0,0,0,0,0,0,0,0,0);
      return;
   }
   if(open_groups >= g_sc.max_open_groups) {
      PrintFormat("FORGE SCALPER: skip gate=open_groups open=%d max=%d", open_groups, g_sc.max_open_groups);
      JournalRecordSignal("SKIP","open_groups","","",SymbolInfoDouble(_Symbol,SYMBOL_BID),spread,0,0,0,0,0,0,0,0,0);
      return;
   }
   if(MQLInfoInteger(MQL_TESTER) == 0 && g_scalper_session_trades >= g_sc.max_trades_per_session) {
      PrintFormat("FORGE SCALPER: skip gate=session_trade_cap trades=%d max=%d",
                  g_scalper_session_trades, g_sc.max_trades_per_session);
      JournalRecordSignal("SKIP","session_trade_cap","","",SymbolInfoDouble(_Symbol,SYMBOL_BID),spread,0,0,0,0,0,0,0,0,0);
      return;
   }
   if((MQLInfoInteger(MQL_TESTER) == 0 || g_sc.tester_cooldown_enabled) && !ScalperCooldownOK()) {
      int remaining = (int)MathMax(0, g_sc.loss_cooldown_sec - (int)(TimeGMT() - g_scalper_last_loss_time));
      datetime m5b_cd = iTime(_Symbol, PERIOD_M5, 0);
      if(m5b_cd != g_scalper_last_cooldown_log_bar) {
         g_scalper_last_cooldown_log_bar = m5b_cd;
         PrintFormat("FORGE SCALPER: skip gate=cooldown remaining_sec=%d", remaining);
         JournalRecordSignal("SKIP","cooldown","","",SymbolInfoDouble(_Symbol,SYMBOL_BID),spread,0,0,0,0,0,0,0,0,0);
      }
      return;
   }

   string warmup_reason = "";
   if(!ForgeNativeScalperWarmupOk(warmup_reason)) {
      g_warmup_last_ok = false;
      g_warmup_last_reason = warmup_reason;
      datetime m5bar_w = iTime(_Symbol, PERIOD_M5, 0);
      if(m5bar_w != g_scalper_last_warmup_log_bar) {
         g_scalper_last_warmup_log_bar = m5bar_w;
         PrintFormat("FORGE SCALPER: skip gate=warmup reason=%s (Live M15 target=%d; extra s=%d; ScalperTesterWarmupM5Bars=%d)",
                     warmup_reason, ScalperLiveWarmupM15Bars, ScalperWarmupSeconds, ScalperTesterWarmupM5Bars);
         JournalRecordSignal("SKIP", "warmup_" + warmup_reason, "", "",
            SymbolInfoDouble(_Symbol, SYMBOL_BID), spread, 0, 0, 0, 0, 0, 0, 0, 0, 0);
      }
      return;
   }
   g_warmup_last_ok = true;
   g_warmup_last_reason = "";
   if(!g_scalper_warmup_ready_logged) {
      g_scalper_warmup_ready_logged = true;
      PrintFormat("FORGE SCALPER: warmup complete — native entries allowed (Live M15=%d, extra s=%d, ScalperTesterWarmupM5Bars=%d, ScalperTesterWarmupSimCapMinutes=%d)",
                  ScalperLiveWarmupM15Bars, ScalperWarmupSeconds, ScalperTesterWarmupM5Bars, ScalperTesterWarmupSimCapMinutes);
   }

   if(!ScalperOnePerBar()) return;

   // Read M5 indicators
   double buf[1];
   double m5_rsi  = (CopyBuffer(g_mtf[0].h_rsi, 0,0,1,buf)==1)  ? buf[0] : 0;
   double m5_adx  = (CopyBuffer(g_mtf[0].h_adx, 0,0,1,buf)==1)  ? buf[0] : 0;
   double m5_bb_m = (CopyBuffer(g_mtf[0].h_bb,  0,0,1,buf)==1)  ? buf[0] : 0;
   double m5_bb_u = (CopyBuffer(g_mtf[0].h_bb,  1,0,1,buf)==1)  ? buf[0] : 0;
   double m5_bb_l = (CopyBuffer(g_mtf[0].h_bb,  2,0,1,buf)==1)  ? buf[0] : 0;
   double m5_atr  = (CopyBuffer(g_mtf[0].h_atr, 0,0,1,buf)==1)  ? buf[0] : 0;
   double m5_ema20= (CopyBuffer(g_mtf[0].h_ma20,0,0,1,buf)==1)  ? buf[0] : 0;
   double m5_ema50= (CopyBuffer(g_mtf[0].h_ma50,0,0,1,buf)==1)  ? buf[0] : 0;

   // Read M15 indicators (for breakout confirmation)
   double m15_ema20= (CopyBuffer(g_mtf[1].h_ma20,0,0,1,buf)==1) ? buf[0] : 0;
   double m15_ema50= (CopyBuffer(g_mtf[1].h_ma50,0,0,1,buf)==1) ? buf[0] : 0;
   double m15_atr  = (CopyBuffer(g_mtf[1].h_atr, 0,0,1,buf)==1) ? buf[0] : 0;

   const bool in_tester = (MQLInfoInteger(MQL_TESTER) != 0);
   // Live: H1 trend bias from last *completed* H1 bar (non-repainting). Tester: bar 0 for responsiveness.
   const int h1_bias_shift = in_tester ? 0 : 1;

   // Read H1 trend (for direction filter)
   double h1_ema20    = (CopyBuffer(g_h_ma20,0,h1_bias_shift,1,buf)==1) ? buf[0] : 0;
   double h1_ema50    = (CopyBuffer(g_h_ma50,0,h1_bias_shift,1,buf)==1) ? buf[0] : 0;
   double h1_atr      = (CopyBuffer(g_h_atr, 0,h1_bias_shift,1,buf)==1) ? buf[0] : 0;
   // H1 DI+/DI- from existing g_h_adx handle (iADX buffer 1=DI+, buffer 2=DI-)
   // h1_di_read_ok: false during warmup/reconnect → gate defaults to pass (no false-block)
   double h1_di_plus   = 0.0;
   double h1_di_minus  = 0.0;
   bool   h1_di_read_ok = (CopyBuffer(g_h_adx, 1, h1_bias_shift, 1, buf)==1);
   if(h1_di_read_ok) {
      h1_di_plus = buf[0];
      h1_di_read_ok = (CopyBuffer(g_h_adx, 2, h1_bias_shift, 1, buf)==1);
      if(h1_di_read_ok) h1_di_minus = buf[0];
   }

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double mid = (bid + ask) / 2.0;
   double bb_range = m5_bb_u - m5_bb_l;
   if(bb_range <= 0) {
      Print("FORGE SCALPER: skip reason=invalid_bb_range");
      return;
   }
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double prev_close = iClose(_Symbol, PERIOD_M5, 1);

   // Live: use scalper_config.json / defaults. Strategy Tester: relax so backtests produce trades (fills, R:R stats).
   double bounce_adx_max_eff = g_sc.bounce_adx_max;
   double breakout_adx_min_eff = g_sc.breakout_adx_min;           // BUY floor
   double breakout_adx_min_sell_eff = g_sc.breakout_adx_min_sell; // SELL floor (stricter)
   double trend_thr_eff = g_sc.trend_strength_atr_threshold;
   double bounce_bb_prox_eff = g_sc.bounce_bb_proximity_pct;
   double breakout_buf_eff_pts = g_sc.breakout_buffer_points;
   double rr_min_eff = MathMax(g_sc.min_rr, g_sc.min_rr_floor);
   bool breakout_m15_req_eff = g_sc.breakout_require_m15;
   if(in_tester) {
      if(!g_sc.bounce_respect_adx_max_in_tester)
         bounce_adx_max_eff = 99.0;
      breakout_adx_min_eff = g_sc.breakout_adx_min;
      breakout_adx_min_sell_eff = g_sc.breakout_adx_min_sell;
      trend_thr_eff = MathMax(0.08, g_sc.trend_strength_atr_threshold * 0.45);
      bounce_bb_prox_eff = MathMax(g_sc.bounce_bb_proximity_pct, 40.0);
      breakout_buf_eff_pts = MathMax(1.0, g_sc.breakout_buffer_points * 0.30);
      rr_min_eff = MathMax(1.0, MathMin(MathMax(g_sc.min_rr, g_sc.min_rr_floor), 1.5));
      breakout_m15_req_eff = false;
   }
   double breakout_buffer = breakout_buf_eff_pts * point;

   // Deterministic M5 ADX trend regime with hysteresis to avoid bounce whipsaws:
   // enter trend only above `adx_trend_enter`, exit only below `adx_trend_exit`.
   bool adx_hyst_active = g_sc.adx_hysteresis_enabled && (!in_tester || g_sc.adx_hysteresis_apply_in_tester);
   if(adx_hyst_active) {
      bool prev_regime = g_adx_trend_regime;
      if(!g_adx_trend_regime && m5_adx >= g_sc.adx_trend_enter) g_adx_trend_regime = true;
      else if(g_adx_trend_regime && m5_adx <= g_sc.adx_trend_exit) g_adx_trend_regime = false;
      if(prev_regime != g_adx_trend_regime) {
         PrintFormat("FORGE SCALPER: adx_regime transition=%s adx=%.1f enter=%.1f exit=%.1f",
                     g_adx_trend_regime ? "TREND" : "RANGE",
                     m5_adx, g_sc.adx_trend_enter, g_sc.adx_trend_exit);
      }
   } else {
      g_adx_trend_regime = false;
   }

   // H1 trend bias
   double h1_trend_strength = (h1_ema20 - h1_ema50) / MathMax(h1_atr, point);
   bool h1_bull = h1_trend_strength > trend_thr_eff;
   bool h1_bear = h1_trend_strength < -trend_thr_eff;
   bool h1_flat = !h1_bull && !h1_bear;

   // M15 HTF structure (used for bounce counter-trend block + breakouts below)
   double m15_trend_strength_htf = (m15_ema20 - m15_ema50) / MathMax(m15_atr, point);
   bool m15_bull_htf = m15_trend_strength_htf > trend_thr_eff;
   bool m15_bear_htf = m15_trend_strength_htf < -trend_thr_eff;

   // H4 structure alignment (same ATR-normalized EMA spread rule as H1)
   double h4_ema20 = (CopyBuffer(g_h4_ma20,0,0,1,buf)==1) ? buf[0] : 0;
   double h4_ema50 = (CopyBuffer(g_h4_ma50,0,0,1,buf)==1) ? buf[0] : 0;
   double h4_atr   = (CopyBuffer(g_h4_atr, 0,0,1,buf)==1) ? buf[0] : 0;
   double h4_trend_strength = (h4_ema20 - h4_ema50) / MathMax(h4_atr, point);
   bool h4_bull = h4_trend_strength > trend_thr_eff;
   bool h4_bear = h4_trend_strength < -trend_thr_eff;
   bool h4_flat = !h4_bull && !h4_bear;
   // H4 supplemental reads for gate checks (RSI + ADX); BB upper/lower exported to WriteMarketData
   double h4_rsi_v = (g_h4_rsi != INVALID_HANDLE && CopyBuffer(g_h4_rsi, 0, 0, 1, buf) == 1) ? buf[0] : 0;
   double h4_adx_v = (g_h4_adx != INVALID_HANDLE && CopyBuffer(g_h4_adx, 0, 0, 1, buf) == 1) ? buf[0] : 0;
   bool h4_ok_buy  = in_tester || (!NativeScalperH4Align) || h4_bull || h4_flat;
   bool h4_ok_sell = in_tester || (!NativeScalperH4Align) || h4_bear || h4_flat;
   // V2 Fibonacci: VWAP-vs-Fib50 directional bias (optional gate for bounce entries)
   bool fib_bias_active = g_sc.fib_bias_enabled && (g_fib_50 > 0) && (g_vwap_price > 0);
   bool fib_ok_buy  = in_tester || !fib_bias_active || (g_vwap_price >= g_fib_50);
   bool fib_ok_sell = in_tester || !fib_bias_active || (g_vwap_price <= g_fib_50);
   // V2 RSI divergence: block bounce only when counter-trend regular divergence is active
   bool rsi_div_active = g_sc.rsi_div_enabled && (g_rsi_div_type != "NONE");
   bool rsi_div_buy_bounce  = !rsi_div_active || (g_rsi_div_type != "REG_BEAR");
   bool rsi_div_sell_bounce = !rsi_div_active || (g_rsi_div_type != "REG_BULL");

   // V2 Task 1: stricter H1 filter — when enabled, H1 flat no longer allows bounce entries.
   // Strategy Tester: H1 can be ignored unless bounce_respect_h1_filter_in_tester.
   bool tester_bounce_h1_skip = in_tester && !g_sc.bounce_respect_h1_filter_in_tester;
   bool bounce_h1_strict = g_sc.bounce_require_h1_direction && !tester_bounce_h1_skip;
   bool h1_ok_buy  = h1_bull || (!bounce_h1_strict && h1_flat);
   bool h1_ok_sell = h1_bear || (!bounce_h1_strict && h1_flat);
   double trend_mag = MathMax(MathAbs(h1_trend_strength), MathAbs(h4_trend_strength));
   bool trend_dir_agree = (h1_bull && (h4_bull || h4_flat))
                        || (h1_bear && (h4_bear || h4_flat))
                        || (h4_bull && h1_flat)
                        || (h4_bear && h1_flat);
   bool high_vol_trend = g_sc.high_vol_trend_guard_enabled
                      && ((!in_tester) || g_sc.high_vol_apply_in_tester)
                      && (m5_adx >= g_sc.high_vol_adx_min)
                      && trend_dir_agree
                      && (trend_mag >= g_sc.high_vol_trend_strength_min);

   // In tester, BRIDGE does not push regime updates — derive it from native indicators so the journal is populated.
   if(in_tester) {
      if(high_vol_trend)                              g_regime_label = "VOLATILE";
      else if(h1_bull && (h4_bull || h4_flat))        g_regime_label = "TREND_BULL";
      else if(h1_bear && (h4_bear || h4_flat))        g_regime_label = "TREND_BEAR";
      else                                             g_regime_label = "RANGE";
      g_regime_confidence = 1.0;
   }

   // M1 — execution TF confirmation (bias remains H1/H4/regime only)
   double m1_ema20 = (CopyBuffer(g_m1_ma20,0,0,1,buf)==1) ? buf[0] : 0;
   double m1_ema50 = (CopyBuffer(g_m1_ma50,0,0,1,buf)==1) ? buf[0] : 0;
   double m1_atr   = (CopyBuffer(g_m1_atr, 0,0,1,buf)==1) ? buf[0] : 0;
   double m1_trend_strength = (m1_ema20 - m1_ema50) / MathMax(m1_atr, point);
   bool m1_bull = m1_trend_strength > trend_thr_eff;
   bool m1_bear = m1_trend_strength < -trend_thr_eff;
   bool m1_flat = !m1_bull && !m1_bear;

   // Check sentinel (read sentinel_status.json for news guard)
   bool sentinel_tight = false;
   string sent_content = "";
   if(ReadTextFileDual("sentinel_status.json", sent_content) && sent_content != "") {
      string active = JsonGetString(sent_content, "active");
      if(active == "true" || active == "True") {
         // Tester: ignore — a copied live sentinel_status.json would block all backtest entries.
         if(MQLInfoInteger(MQL_TESTER) == 0) {
            Print("FORGE SCALPER: skip gate=sentinel_active");
            return;
         }
      }
      double mins = JsonGetDouble(sent_content, "next_in_min");
      if(mins > 0 && mins <= g_sc.sentinel_min_threshold)
         sentinel_tight = true;  // news approaching — tighten TP
   }

   string direction = "";
   double sl = 0, tp1 = 0, tp2 = 0;
   string setup_type = "";
   double m5_trend_strength = (m5_ema20 - m5_ema50) / MathMax(m5_atr, point);
   double m15_trend_strength = m15_trend_strength_htf;
   string nf_ev_label_pre = "";
   ScalperNewsUpdateEffectiveThresholds(nf_ev_label_pre);

   // ── V2 Task 7: Breakout retest state machine — check pending retest ──
   if(g_retest.active) {
      g_retest.bars_waited++;
      double rt_price = (g_retest.direction == "BUY")
         ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
         : SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double rt_level = g_retest.breakout_level;
      bool price_retested = false;
      if(g_retest.direction == "BUY")
         price_retested = (rt_price <= rt_level + m5_atr * 0.3) && (rt_price >= rt_level - m5_atr * 0.5);
      else
         price_retested = (rt_price >= rt_level - m5_atr * 0.3) && (rt_price <= rt_level + m5_atr * 0.5);

      if(price_retested) {
         // News RSI tighten — same additive guard as direct BB_BREAKOUT entries
         // g_nf_eff_rsi_* already primed by ScalperNewsUpdateEffectiveThresholds() at line 4601
         bool nf_retest_ok = true;
         if(g_retest.direction == "BUY"
            && g_nf_eff_rsi_buy_ceil < g_sc.breakout_rsi_buy_ceil
            && m5_rsi >= g_nf_eff_rsi_buy_ceil) {
            JournalRecordSignal("SKIP","entry_quality_news_rsi_tighten","BB_BREAKOUT_RETEST","BUY",
               mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            nf_retest_ok = false;
         } else if(g_retest.direction == "SELL"
            && g_nf_eff_rsi_sell_min > g_sc.breakout_rsi_sell_floor
            && m5_rsi <= g_nf_eff_rsi_sell_min) {
            JournalRecordSignal("SKIP","entry_quality_news_rsi_tighten","BB_BREAKOUT_RETEST","SELL",
               mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            nf_retest_ok = false;
         }
         if(!nf_retest_ok) {
            g_retest.active = false;
            return;
         }
         direction  = g_retest.direction;
         sl         = g_retest.sl;
         tp1        = g_retest.tp1;
         tp2        = g_retest.tp2;
         setup_type = g_retest.setup_type;
         g_retest.active = false;
         PrintFormat("FORGE SCALPER: retest confirmed %s at %.2f after %d bars", direction, rt_price, g_retest.bars_waited);
      } else if(g_retest.bars_waited > g_retest.max_wait_bars) {
         PrintFormat("FORGE SCALPER: retest expired after %d bars", g_retest.bars_waited);
         g_retest.active = false;
         return;
      } else {
         return;
      }
   }

   // ── BB BOUNCE (Range Mode) ─────────────────────────────────
   if(direction == "" && (g_scalper_mode == "BB_BOUNCE" || g_scalper_mode == "DUAL")
      && g_sc.bounce_enabled && m5_adx < bounce_adx_max_eff) {
      if(adx_hyst_active && g_adx_trend_regime) {
         PrintFormat("FORGE SCALPER: skip gate=adx_trend_regime_bounce adx=%.1f enter=%.1f exit=%.1f",
                     m5_adx, g_sc.adx_trend_enter, g_sc.adx_trend_exit);
      } else if(high_vol_trend && g_sc.high_vol_disable_bounce) {
         PrintFormat("FORGE SCALPER: skip gate=high_vol_trend_bounce adx=%.1f trend_mag=%.3f", m5_adx, trend_mag);
      } else {

      double proximity = bb_range * bounce_bb_prox_eff / 100.0;
      // Bounce confirmation: do not enter on first touch.
      // Require last closed M5 candle to show rejection and reclaim toward band interior.
      double m5_o1 = iOpen(_Symbol, PERIOD_M5, 1);
      double m5_c1 = iClose(_Symbol, PERIOD_M5, 1);
      double m5_l1 = iLow(_Symbol, PERIOD_M5, 1);
      double m5_h1 = iHigh(_Symbol, PERIOD_M5, 1);
      double reclaim_frac = MathMax(0.0, MathMin(1.0, g_sc.bounce_reclaim_pct / 100.0));
      bool buy_reclaim = (m5_l1 <= m5_bb_l) && (m5_c1 >= (m5_bb_l + proximity * reclaim_frac));
      bool sell_reclaim = (m5_h1 >= m5_bb_u) && (m5_c1 <= (m5_bb_u - proximity * reclaim_frac));
      // V2 Task 3: candlestick pattern scoring replaces simple bullish/bearish check
      int buy_pattern = ScalperCandlePatternScore(true);
      int sell_pattern = ScalperCandlePatternScore(false);
      bool buy_candle_ok = (!g_sc.bounce_require_rejection_candle) || (buy_pattern >= g_sc.bounce_min_candle_score);
      bool sell_candle_ok = (!g_sc.bounce_require_rejection_candle) || (sell_pattern >= g_sc.bounce_min_candle_score);
      bool buy_reject = buy_reclaim && buy_candle_ok;
      bool sell_reject = sell_reclaim && sell_candle_ok;
      // V2 Task 2: bar-0 continuation — current price moving away from the band
      bool buy_bar0_ok = (!g_sc.bounce_require_bar0_confirm) || (mid > m5_bb_l + proximity * 0.5);
      bool sell_bar0_ok = (!g_sc.bounce_require_bar0_confirm) || (mid < m5_bb_u - proximity * 0.5);
      // V2 Task 6: liquidity zone awareness (skip in tester — Common Files may lack fresh data)
      bool liquidity_ok = in_tester || (!g_sc.bounce_require_liquidity_zone) || NearLiquidityZone(mid, m5_atr);
      bool bounce_tf_buy_ok  = h1_ok_buy;
      bool bounce_tf_sell_ok = h1_ok_sell;
      bool use_htf_bias = (g_sc.bounce_htf_bias == 1 || g_sc.bounce_htf_bias == 2);
      if(use_htf_bias) {
         if(g_sc.bounce_htf_bias == 1) {
            bounce_tf_buy_ok  = !(h1_bear && m15_bear_htf);
            bounce_tf_sell_ok = !(h1_bull && m15_bull_htf);
         } else {
            bounce_tf_buy_ok  = !h1_bear && !m15_bear_htf;
            bounce_tf_sell_ok = !h1_bull && !m15_bull_htf;
         }
      }
      bool bounce_htf_blocks_sell = (!use_htf_bias) && g_sc.bounce_block_htf_trend_align && h1_bull && m15_bull_htf;
      bool bounce_htf_blocks_buy  = (!use_htf_bias) && g_sc.bounce_block_htf_trend_align && h1_bear && m15_bear_htf;

      // BUY: price near BB lower + RSI oversold + H1 not bearish + optional H4 alignment
      // bounce_min_h1_trend: Cardwell Bull Support requires confirmed uptrend — H1 barely positive is insufficient.
      if(mid <= m5_bb_l + proximity && m5_rsi < g_sc.bounce_rsi_buy_max
         && bounce_tf_buy_ok && h4_ok_buy && fib_ok_buy && rsi_div_buy_bounce && buy_reject && buy_bar0_ok && liquidity_ok
         && !bounce_htf_blocks_buy
         && h1_trend_strength >= g_sc.bounce_min_h1_trend) {
         direction = "BUY";
         double atr_sl_buy = NormalizeDouble(bid - m5_atr * g_sc.bounce_sl_atr_mult, _Digits);
         sl  = FindStructuralSL(true, bid, atr_sl_buy, point);
         double sl_floor_buy = NormalizeDouble(bid - m5_atr * g_sc.min_sl_atr_mult, _Digits);
         if(sl > sl_floor_buy) sl = sl_floor_buy;
         tp1 = NormalizeDouble(m5_bb_m, _Digits);
         tp2 = NormalizeDouble(m5_bb_u, _Digits);
         if(g_poc_price > ask && g_poc_price < tp1)
            tp1 = NormalizeDouble(g_poc_price, _Digits);
         if(g_vwap_price > ask && g_vwap_price < tp1)
            tp1 = NormalizeDouble(g_vwap_price, _Digits);
         if(g_sc.fib_tp_enabled && g_fib_382 > ask && g_fib_382 < tp1)
            tp1 = NormalizeDouble(g_fib_382, _Digits);
         if(g_sc.fib_tp_enabled && g_fib_618 > ask && g_fib_618 < tp2 && g_fib_618 > tp1)
            tp2 = NormalizeDouble(g_fib_618, _Digits);
         double min_tp1 = ask + (m5_atr * 0.40);
         double min_tp2 = ask + (m5_atr * 0.80);
         if(tp1 < min_tp1) tp1 = NormalizeDouble(min_tp1, _Digits);
         if(tp2 < min_tp2) tp2 = NormalizeDouble(min_tp2, _Digits);
         if(tp2 <= tp1) tp2 = NormalizeDouble(tp1 + (m5_atr * 0.25), _Digits);
         setup_type = "BB_BOUNCE";
      }
      // SELL: price near BB upper + RSI overbought + H1 not bullish
      else if(mid >= m5_bb_u - proximity && m5_rsi > g_sc.bounce_rsi_sell_min
              && bounce_tf_sell_ok && h4_ok_sell && fib_ok_sell && rsi_div_sell_bounce && sell_reject && sell_bar0_ok && liquidity_ok
              && !bounce_htf_blocks_sell) {
         direction = "SELL";
         double atr_sl_sell = NormalizeDouble(ask + m5_atr * g_sc.bounce_sl_atr_mult, _Digits);
         sl  = FindStructuralSL(false, ask, atr_sl_sell, point);
         double sl_ceil_sell = NormalizeDouble(ask + m5_atr * g_sc.min_sl_atr_mult, _Digits);
         if(sl < sl_ceil_sell) sl = sl_ceil_sell;
         tp1 = NormalizeDouble(m5_bb_m, _Digits);
         tp2 = NormalizeDouble(m5_bb_l, _Digits);
         if(g_poc_price < bid && g_poc_price > tp1)
            tp1 = NormalizeDouble(g_poc_price, _Digits);
         if(g_vwap_price < bid && g_vwap_price > tp1)
            tp1 = NormalizeDouble(g_vwap_price, _Digits);
         if(g_sc.fib_tp_enabled && g_fib_618 < bid && g_fib_618 > tp1)
            tp1 = NormalizeDouble(g_fib_618, _Digits);
         if(g_sc.fib_tp_enabled && g_fib_382 < bid && g_fib_382 > tp2 && g_fib_382 < tp1)
            tp2 = NormalizeDouble(g_fib_382, _Digits);
         double max_tp1 = bid - (m5_atr * 0.40);
         double max_tp2 = bid - (m5_atr * 0.80);
         if(tp1 > max_tp1) tp1 = NormalizeDouble(max_tp1, _Digits);
         if(tp2 > max_tp2) tp2 = NormalizeDouble(max_tp2, _Digits);
         if(tp2 >= tp1) tp2 = NormalizeDouble(tp1 - (m5_atr * 0.25), _Digits);
         setup_type = "BB_BOUNCE";
      }
      }
   }

   // ── BB BREAKOUT (Trend Mode) ───────────────────────────────
   {
      datetime _adx_bar = iTime(_Symbol, PERIOD_M5, 0);
      if(_adx_bar != g_scalper_last_adxgate_log_bar) {
         g_scalper_last_adxgate_log_bar = _adx_bar;
         PrintFormat("FORGE ADX gate: adx=%.1f buy_min=%.1f sell_min=%.1f buy=%s sell=%s | rsi=%.1f price=%.2f atr=%.2f",
            m5_adx, breakout_adx_min_eff, breakout_adx_min_sell_eff,
            (m5_adx >= breakout_adx_min_eff) ? "PASS" : "BLOCKED",
            (m5_adx >= breakout_adx_min_sell_eff) ? "PASS" : "BLOCKED",
            m5_rsi, mid, m5_atr);
      }
   }
   if(direction == "" && (g_scalper_mode == "BB_BREAKOUT" || g_scalper_mode == "DUAL")
      && g_sc.breakout_enabled && m5_adx >= breakout_adx_min_eff) {
      bool m5_bull  = m5_trend_strength > trend_thr_eff;
      bool m5_bear  = m5_trend_strength < -trend_thr_eff;
      bool m15_bull = m15_trend_strength > trend_thr_eff;
      bool m15_bear = m15_trend_strength < -trend_thr_eff;
      bool m15_flat = !m15_bull && !m15_bear;
      bool m15_ok_buy  = !breakout_m15_req_eff || m15_bull || m15_flat;
      bool m15_ok_sell = !breakout_m15_req_eff || m15_bear || m15_flat;
      bool strict_breakout_buy_ok = !high_vol_trend || !g_sc.high_vol_require_h1_h4_breakout_align || (h1_bull && h4_bull);
      bool strict_breakout_sell_ok = !high_vol_trend || !g_sc.high_vol_require_h1_h4_breakout_align || (h1_bear && h4_bear);
      double breakout_sl_mult_eff = g_sc.breakout_sl_atr_mult * ((high_vol_trend) ? g_sc.high_vol_breakout_sl_boost : 1.0);

      // BUY breakout: close above upper BB + RSI strong + aligned
      // rsi_buy_min=40: Cardwell Bull Support zone (RSI 40–80 in uptrend; 40 = dip re-entry floor)
      if(prev_close > (m5_bb_u + breakout_buffer) && m5_rsi > g_sc.breakout_rsi_buy_min
         && m5_bull && m15_ok_buy && h1_ok_buy && h4_ok_buy && strict_breakout_buy_ok) {
         if(m5_rsi >= g_sc.breakout_rsi_buy_ceil) {
            JournalRecordSignal("SKIP","entry_quality_rsi_buy_ceil","BB_BREAKOUT","BUY",
               mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
         } else {
            // H1 DI directional gate (2.7.5): block weak-ADX BUY when H1 DI- dominates DI+ (Wilder's directional check)
            bool h1_di_ok = true;
            if(g_sc.breakout_require_h1_di_buy && m5_adx < g_sc.breakout_counter_buy_adx_threshold) {
               if(h1_di_read_ok && h1_di_plus <= h1_di_minus) {
                  datetime _h1di_bar = iTime(_Symbol, PERIOD_M5, 0);
                  if(_h1di_bar != g_scalper_last_h1dibuy_log_bar) {
                     g_scalper_last_h1dibuy_log_bar = _h1di_bar;
                     JournalRecordSignal("SKIP","entry_quality_h1_di_buy","BB_BREAKOUT","BUY",
                        mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
                  }
                  h1_di_ok = false;
               }
            }
            // OsMA histogram gate for BUY (2.7.7, MACD Histogram MC Q0 pass only, default off)
            // BUY passes only in Q0: histogram positive AND rising (strong bull momentum confirmed).
            // Q0(+↑): PASS | Q1(+↓): bull fading | Q2(−↓): strong bear | Q3(−↑): bear fading → all block
            bool macd_buy_ok = true;
            if(h1_di_ok && g_sc.breakout_require_macd_buy && g_h_osma_scalp != INVALID_HANDLE) {
               double _hist[2];
               if(CopyBuffer(g_h_osma_scalp, 0, 0, 2, _hist) == 2) {
                  double _h0 = _hist[0], _h1 = _hist[1];
                  datetime _macd_bar = iTime(_Symbol, PERIOD_M5, 0);
                  string _qreason = "";
                  if(_h0 <= 0.0)      _qreason = (_h0 < _h1) ? "entry_quality_macd_q2_bear_str"    : "entry_quality_macd_q3_bear_fading";
                  else if(_h0 < _h1)  _qreason = "entry_quality_macd_q1_bull_fading";
                  if(_qreason != "") {
                     if(_macd_bar != g_scalper_last_macd_log_bar) {
                        g_scalper_last_macd_log_bar = _macd_bar;
                        JournalRecordSignal("SKIP",_qreason,"BB_BREAKOUT","BUY",
                           mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0,_h0);
                     }
                     macd_buy_ok = false;
                  }
               }
            }
            // H4 RSI gate — blocks BUY when H4 RSI <= h4_rsi_buy_min (Cardwell Bull Support exhaustion)
            // Rationale: H4 RSI <=40 = structurally oversold on H4 → breakout BUY may be catching a falling knife
            // Enable: FORGE_H4_RSI_GATE_ENABLED=1 in .env + "h4_rsi_gate_enabled":1 in scalper_config.json
            bool h4_rsi_buy_ok = true;
            if(h1_di_ok && macd_buy_ok && g_sc.h4_rsi_gate_enabled && h4_rsi_v > 0) {
               if(h4_rsi_v <= g_sc.h4_rsi_buy_min) {
                  JournalRecordSignal("SKIP","entry_quality_h4_rsi_buy_blocked","BB_BREAKOUT","BUY",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
                  h4_rsi_buy_ok = false;
               }
            }
            // H4 ADX gate — blocks BUY when H4 ADX < h4_adx_min_buy (H4 not directional)
            bool h4_adx_buy_ok = true;
            if(h1_di_ok && macd_buy_ok && h4_rsi_buy_ok && g_sc.h4_adx_gate_enabled && h4_adx_v > 0) {
               if(h4_adx_v < g_sc.h4_adx_min_buy) {
                  JournalRecordSignal("SKIP","entry_quality_h4_adx_buy_blocked","BB_BREAKOUT","BUY",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
                  h4_adx_buy_ok = false;
               }
            }
            // News RSI tighten — independent additive check (last line of defense before entry)
            bool nf_buy_ok = true;
            if(h1_di_ok && macd_buy_ok && h4_rsi_buy_ok && h4_adx_buy_ok
               && g_nf_eff_rsi_buy_ceil < g_sc.breakout_rsi_buy_ceil && m5_rsi >= g_nf_eff_rsi_buy_ceil) {
               JournalRecordSignal("SKIP","entry_quality_news_rsi_tighten","BB_BREAKOUT","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
               nf_buy_ok = false;
            }
            if(h1_di_ok && macd_buy_ok && h4_rsi_buy_ok && h4_adx_buy_ok && nf_buy_ok)
            { // Breakout SL is pure ATR — no structural widening (OB widening blows out RR at TP4).
            double bo_sl = NormalizeDouble(bid - m5_atr * breakout_sl_mult_eff, _Digits);
            double bo_sl_floor = NormalizeDouble(bid - m5_atr * g_sc.min_sl_atr_mult, _Digits);
            if(bo_sl > bo_sl_floor) bo_sl = bo_sl_floor;
            double _tp1_buy_mult = (g_sc.breakout_tp1_buy_atr_mult > 0.0) ? g_sc.breakout_tp1_buy_atr_mult : g_sc.breakout_tp1_atr_mult;
            double bo_tp1 = NormalizeDouble(bid + m5_atr * _tp1_buy_mult, _Digits);
            double bo_tp2 = NormalizeDouble(bid + m5_atr * g_sc.breakout_tp2_atr_mult, _Digits);
            if(g_sc.breakout_use_retest && !in_tester && !g_retest.active) {
               g_retest.active = true;
               g_retest.direction = "BUY";
               g_retest.breakout_level = m5_bb_u;
               g_retest.sl = bo_sl;
               g_retest.tp1 = bo_tp1;
               g_retest.tp2 = bo_tp2;
               g_retest.setup_type = "BB_BREAKOUT_RETEST";
               g_retest.trigger_time = TimeCurrent();
               g_retest.max_wait_bars = g_sc.breakout_retest_max_bars;
               g_retest.bars_waited = 0;
               PrintFormat("FORGE SCALPER: breakout BUY — waiting for retest at %.2f", m5_bb_u);
            } else {
               direction = "BUY";
               sl = bo_sl; tp1 = bo_tp1; tp2 = bo_tp2;
               setup_type = "BB_BREAKOUT";
            }
            } // end h1_di_ok block
         }
      }
      // SELL breakout — uses stricter ADX floor (breakout_adx_min_sell_eff)
      // rsi_sell_max=60: Cardwell Bear Resistance ceiling (RSI 20–60 in downtrend; 60 = bounce re-short ceiling)
      // Second SELL entry fires when RSI bounces from crash low back toward 50–60 and BB re-breaks lower.
      // min_h1_bear_strength: blocks SELL when H1 barely bearish (e.g. -0.11) — requires genuine H1 conviction.
      else if(prev_close < (m5_bb_l - breakout_buffer) && m5_rsi < g_sc.breakout_rsi_sell_max
              && m5_bear && m15_ok_sell && h1_ok_sell && h4_ok_sell && strict_breakout_sell_ok
              && (g_sc.breakout_min_h1_bear_strength <= 0.0
                  || h1_trend_strength <= -g_sc.breakout_min_h1_bear_strength)) {
         // Session SELL cutoff (2.7.7): post-17:00 UTC = lower liquidity, wider spread, adverse for XAUUSD scalps
         // Research: TMGM, ACY, NordFX — ~70% of daily range occurs in London+NY overlap only (08:00-17:00 UTC)
         MqlDateTime _sdt; TimeToStruct(TimeTradeServer(), _sdt);
         bool _sell_session_ok = !((g_sc.session_ny_sell_cutoff_utc > 0 && _sdt.hour >= g_sc.session_ny_sell_cutoff_utc)
                                || (g_sc.session_london_sell_cutoff_utc > 0 && _sdt.hour >= g_sc.session_london_sell_cutoff_utc && _sdt.hour < 13));
         if(!_sell_session_ok) {
            datetime _sc_bar = iTime(_Symbol, PERIOD_M5, 0);
            if(_sc_bar != g_scalper_last_sesscut_log_bar) {
               g_scalper_last_sesscut_log_bar = _sc_bar;
               JournalRecordSignal("SKIP","entry_quality_session_sell_cutoff","BB_BREAKOUT","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else {
            // Extreme ADX block (2.7.7): at ADX(M15) >= threshold, move is exhausted; block outright.
            // 1/16th lot rounds to same as 1/8th (broker min 0.01) — block is cleaner. G5004(ADX 59) validated.
            double _adx_blk_ref = m5_adx;
            { double _m15a[1]; if(CopyBuffer(g_mtf[1].h_adx, 0, 0, 1, _m15a) == 1) _adx_blk_ref = _m15a[0]; }
            bool _adx_extreme = (g_sc.breakout_adx_sell_block_threshold > 0 && _adx_blk_ref >= g_sc.breakout_adx_sell_block_threshold);
            if(_adx_extreme) {
               datetime _ab_bar = iTime(_Symbol, PERIOD_M5, 0);
               if(_ab_bar != g_scalper_last_adxblk_log_bar) {
                  g_scalper_last_adxblk_log_bar = _ab_bar;
                  JournalRecordSignal("SKIP","entry_quality_adx_extreme_sell","BB_BREAKOUT","SELL",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
               }
            } else if(m5_adx < breakout_adx_min_sell_eff) {
               datetime _adxsell_bar = iTime(_Symbol, PERIOD_M5, 0);
               if(_adxsell_bar != g_scalper_last_adxsell_log_bar) {
                  g_scalper_last_adxsell_log_bar = _adxsell_bar;
                  JournalRecordSignal("SKIP","entry_quality_adx_min_sell","BB_BREAKOUT","SELL",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
               }
            } else {
         // H1+H4 crash bypass: confirmed multi-TF bear trend overrides RSI floor and ADX spike gate.
         // ADX minimum, RSI declining, and news tighten all still apply.
         // Cardwell: RSI 20–60 is the downtrend range; RSI 20 is the extreme floor (crash_sell_rsi_min).
         // Below RSI 20 = exhaustion territory even in genuine crashes — mean-reversion risk too high.
         // Hard lower bound: even in crash mode, RSI must be above crash_sell_rsi_min (default 20)
         // — prevents late exhaustion entries at RSI 14-20 where mean-reversion risk is highest.
         // crash_sell_adx_max: high ADX means the move is already very extended — reversal risk elevated.
         // Mirrors bounce_adx_max logic: counter-trend bounces blocked when ADX > 40 for same reason.
         // H1 DI directional gate (2.7.12): block SELL when H1 DI+ >= DI- (H1 bullish — counter-trend SELL)
         // No ADX bypass: high-ADX false-breakdowns (like G5008 ADX=37.4) are the exact risk this gate targets.
         // crash_sell_bypass does not skip this gate — if H1 is genuinely bearish, DI- > DI+ will confirm it.
         bool h1_di_sell_ok = true;
         if(g_sc.breakout_require_h1_di_sell) {
            if(h1_di_read_ok && h1_di_plus >= h1_di_minus) {
               datetime _h1ds_bar = iTime(_Symbol, PERIOD_M5, 0);
               if(_h1ds_bar != g_scalper_last_h1disell_log_bar) {
                  g_scalper_last_h1disell_log_bar = _h1ds_bar;
                  JournalRecordSignal("SKIP","entry_quality_h1_di_sell","BB_BREAKOUT","SELL",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
               }
               h1_di_sell_ok = false;
            }
         }
         bool crash_sell_bypass = g_sc.breakout_h1h4_crash_sell && h1_bear && h4_bear
                                  && m5_rsi > g_sc.breakout_h1h4_crash_sell_rsi_min
                                  && (g_sc.h1h4_crash_sell_adx_max <= 0 || m5_adx <= g_sc.h1h4_crash_sell_adx_max);
         // Two-tier RSI floor — absolute + ADX-conditioned stricter floor (skipped on crash bypass)
         bool rsi_floor_ok = true;
         if(!crash_sell_bypass) {
            double sell_floor_eff = g_sc.breakout_rsi_sell_floor;
            bool weak_adx_floor = (m5_adx < g_sc.breakout_adx_sell_floor_threshold);
            if(weak_adx_floor)
               sell_floor_eff = MathMax(sell_floor_eff, g_sc.breakout_rsi_sell_floor_weak_adx);
            if(m5_rsi <= sell_floor_eff) {
               datetime _rsif_bar = iTime(_Symbol, PERIOD_M5, 0);
               if(_rsif_bar != g_scalper_last_rsisellfloor_log_bar) {
                  g_scalper_last_rsisellfloor_log_bar = _rsif_bar;
                  string floor_gate = (weak_adx_floor && sell_floor_eff >= g_sc.breakout_rsi_sell_floor_weak_adx)
                                      ? "entry_quality_rsi_sell_adx_floor" : "entry_quality_rsi_sell_floor";
                  JournalRecordSignal("SKIP",floor_gate,"BB_BREAKOUT","SELL",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
               }
               rsi_floor_ok = false;
            }
         }
         if(rsi_floor_ok && h1_di_sell_ok) {
            // ADX duration gate: block SELL if ADX spiked from flat base (skipped on crash bypass)
            bool adx_dur_ok = true;
            if(!crash_sell_bypass && g_sc.breakout_adx_min_sell_lookback_bars > 0) {
               double adx_lb_buf[1];
               if(CopyBuffer(g_mtf[0].h_adx, 0, g_sc.breakout_adx_min_sell_lookback_bars, 1, adx_lb_buf) == 1
                  && adx_lb_buf[0] < breakout_adx_min_sell_eff) {
                  datetime _adxdur_bar = iTime(_Symbol, PERIOD_M5, 0);
                  if(_adxdur_bar != g_scalper_last_adxdur_log_bar) {
                     g_scalper_last_adxdur_log_bar = _adxdur_bar;
                     JournalRecordSignal("SKIP","entry_quality_adx_spike_sell","BB_BREAKOUT","SELL",
                        mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
                  }
                  adx_dur_ok = false;
               }
            }
            // RSI-declining gate (2.7.4): block SELL if RSI rising bar-over-bar (auto-off at ADX≥threshold)
            bool rsi_decl_ok = true;
            if(adx_dur_ok && g_sc.breakout_require_rsi_declining_sell
               && m5_adx < g_sc.breakout_rsi_decl_sell_adx_threshold) {
               double rsi_prev_buf[1];
               if(CopyBuffer(g_mtf[0].h_rsi, 0, 1, 1, rsi_prev_buf) == 1 && m5_rsi > rsi_prev_buf[0]) {
                  datetime _rsidecl_bar = iTime(_Symbol, PERIOD_M5, 0);
                  if(_rsidecl_bar != g_scalper_last_rsidecl_log_bar) {
                     g_scalper_last_rsidecl_log_bar = _rsidecl_bar;
                     JournalRecordSignal("SKIP","entry_quality_rsi_rising_sell","BB_BREAKOUT","SELL",
                        mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
                  }
                  rsi_decl_ok = false;
               }
            }
            // OsMA(3,10,16) histogram gate (2.7.7): MACD Histogram MC 4-quadrant method (AK20/traderak20)
            // arXiv:2206.12282: RSI+MACD dual gate 84-86% WR. iOsMA buffer 0 = MACD−Signal directly.
            // SELL only passes Q2 (histogram negative AND falling = strong bear momentum confirmed).
            // Q0(+↑): strong bull | Q1(+↓): bull fading | Q2(−↓): PASS | Q3(−↑): bear fading → block
            bool macd_sell_ok = true;
            if(adx_dur_ok && rsi_decl_ok && g_sc.breakout_require_macd_sell && g_h_osma_scalp != INVALID_HANDLE) {
               double _hist[2];
               if(CopyBuffer(g_h_osma_scalp, 0, 0, 2, _hist) == 2) {
                  double _h0 = _hist[0], _h1 = _hist[1];
                  datetime _macd_bar = iTime(_Symbol, PERIOD_M5, 0);
                  string _qreason = "";
                  if(_h0 >= 0.0)      _qreason = (_h0 > _h1) ? "entry_quality_macd_q0_bull_rising" : "entry_quality_macd_q1_bull_fading";
                  else if(_h0 > _h1)  _qreason = "entry_quality_macd_q3_bear_fading";
                  if(_qreason != "") {
                     if(_macd_bar != g_scalper_last_macd_log_bar) {
                        g_scalper_last_macd_log_bar = _macd_bar;
                        JournalRecordSignal("SKIP",_qreason,"BB_BREAKOUT","SELL",
                           mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0,_h0);
                     }
                     macd_sell_ok = false;
                  }
               }
            }
            // H1 MACD histogram gate (2.7.12, Run 12+): block SELL when H1 MACD histogram >= 0 (H1 bullish momentum).
            // Uses existing g_h_macd handle (H1 iMACD 12,26,9). Hist = main(buf0) - signal(buf1).
            // Complements H1 DI gate: DI catches trend direction, MACD catches momentum phase.
            bool h1_macd_sell_ok = true;
            if(adx_dur_ok && rsi_decl_ok && macd_sell_ok && g_sc.breakout_require_h1_macd_sell
               && g_h_macd != INVALID_HANDLE) {
               double _h1ma[1], _h1si[1];
               if(CopyBuffer(g_h_macd, 0, 0, 1, _h1ma) == 1 && CopyBuffer(g_h_macd, 1, 0, 1, _h1si) == 1) {
                  double _h1_hist = _h1ma[0] - _h1si[0];
                  if(_h1_hist >= 0.0) {
                     datetime _h1mcd_bar = iTime(_Symbol, PERIOD_M5, 0);
                     if(_h1mcd_bar != g_scalper_last_h1macd_log_bar) {
                        g_scalper_last_h1macd_log_bar = _h1mcd_bar;
                        JournalRecordSignal("SKIP","entry_quality_h1_macd_sell","BB_BREAKOUT","SELL",
                           mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0,_h1_hist);
                     }
                     h1_macd_sell_ok = false;
                  }
               }
            }
            // M30 EMA bearish confirmation (2.7.9 Feature 3): block SELL when M30 is recovering
            // Uses existing g_mtf[2] handles (M30 EMA20/EMA50) — no new indicator handles needed.
            // Gate activates when ADX ≥ m30_bear_adx_min (trend confirmed) to avoid filtering
            // valid ranging entries where M30 EMA gap is meaningless.
            bool m30_bear_ok = true;
            if(adx_dur_ok && rsi_decl_ok && macd_sell_ok && h1_macd_sell_ok
               && g_sc.breakout_require_m30_bear_sell
               && m5_adx >= g_sc.breakout_m30_bear_adx_min) {
               double _m30buf[1];
               double m30_ema20 = (CopyBuffer(g_mtf[2].h_ma20, 0, 0, 1, _m30buf) == 1) ? _m30buf[0] : 0;
               double m30_ema50 = (CopyBuffer(g_mtf[2].h_ma50, 0, 0, 1, _m30buf) == 1) ? _m30buf[0] : 0;
               if(m30_ema20 > 0 && m30_ema50 > 0 && m30_ema20 >= m30_ema50) {
                  datetime _m30_bar = iTime(_Symbol, PERIOD_M5, 0);
                  if(_m30_bar != g_scalper_last_m30bear_log_bar) {
                     g_scalper_last_m30bear_log_bar = _m30_bar;
                     JournalRecordSignal("SKIP","entry_quality_m30_not_bearish","BB_BREAKOUT","SELL",
                        mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
                  }
                  m30_bear_ok = false;
               }
            }
            // H4 RSI gate — blocks SELL when H4 RSI >= h4_rsi_sell_max (Cardwell Bear Resistance exhaustion)
            // Rationale: H4 RSI >=60 = structurally overbought on H4 → crash sell more likely to be a HH spike
            //            that quickly reverses rather than a genuine breakdown. Gate is disabled by default.
            // Enable: FORGE_H4_RSI_GATE_ENABLED=1 in .env + "h4_rsi_gate_enabled":1 in scalper_config.json
            bool h4_rsi_sell_ok = true;
            if(adx_dur_ok && rsi_decl_ok && macd_sell_ok && h1_macd_sell_ok && m30_bear_ok
               && g_sc.h4_rsi_gate_enabled && h4_rsi_v > 0) {
               if(h4_rsi_v >= g_sc.h4_rsi_sell_max) {
                  JournalRecordSignal("SKIP","entry_quality_h4_rsi_sell_blocked","BB_BREAKOUT","SELL",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
                  h4_rsi_sell_ok = false;
               }
            }
            // H4 ADX gate — blocks SELL when H4 ADX < h4_adx_min_sell (H4 trend not directional)
            // Rationale: if H4 is ranging (ADX < 20), scalp SELL breakouts have no structural confirmation
            // Enable: FORGE_H4_ADX_GATE_ENABLED=1 in .env + "h4_adx_gate_enabled":1 in scalper_config.json
            bool h4_adx_sell_ok = true;
            if(adx_dur_ok && rsi_decl_ok && macd_sell_ok && h1_macd_sell_ok && m30_bear_ok && h4_rsi_sell_ok
               && g_sc.h4_adx_gate_enabled && h4_adx_v > 0) {
               if(h4_adx_v < g_sc.h4_adx_min_sell) {
                  JournalRecordSignal("SKIP","entry_quality_h4_adx_sell_blocked","BB_BREAKOUT","SELL",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
                  h4_adx_sell_ok = false;
               }
            }
            // News RSI tighten — independent additive check (last line of defense before entry)
            bool nf_sell_ok = true;
            if(adx_dur_ok && rsi_decl_ok && macd_sell_ok && h1_macd_sell_ok && m30_bear_ok && h4_rsi_sell_ok && h4_adx_sell_ok
               && g_nf_eff_rsi_sell_min > g_sc.breakout_rsi_sell_floor
               && m5_rsi <= g_nf_eff_rsi_sell_min) {
               JournalRecordSignal("SKIP","entry_quality_news_rsi_tighten","BB_BREAKOUT","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
               nf_sell_ok = false;
            }
            if(adx_dur_ok && rsi_decl_ok && macd_sell_ok && h1_macd_sell_ok && m30_bear_ok && h4_rsi_sell_ok && h4_adx_sell_ok && nf_sell_ok) {
            // Breakout SL is pure ATR — no structural widening (OB widening blows out RR at TP4).
            double bo_sl = NormalizeDouble(ask + m5_atr * breakout_sl_mult_eff, _Digits);
            double bo_sl_ceil = NormalizeDouble(ask + m5_atr * g_sc.min_sl_atr_mult, _Digits);
            if(bo_sl < bo_sl_ceil) bo_sl = bo_sl_ceil;
            double _tp1_sell_mult = (g_sc.breakout_tp1_sell_atr_mult > 0.0) ? g_sc.breakout_tp1_sell_atr_mult : g_sc.breakout_tp1_atr_mult;
            double bo_tp1 = NormalizeDouble(ask - m5_atr * _tp1_sell_mult, _Digits);
            double bo_tp2 = NormalizeDouble(ask - m5_atr * g_sc.breakout_tp2_atr_mult, _Digits);
            if(g_sc.breakout_use_retest && !in_tester && !g_retest.active) {
               g_retest.active = true;
               g_retest.direction = "SELL";
               g_retest.breakout_level = m5_bb_l;
               g_retest.sl = bo_sl;
               g_retest.tp1 = bo_tp1;
               g_retest.tp2 = bo_tp2;
               g_retest.setup_type = "BB_BREAKOUT_RETEST";
               g_retest.trigger_time = TimeCurrent();
               g_retest.max_wait_bars = g_sc.breakout_retest_max_bars;
               g_retest.bars_waited = 0;
               PrintFormat("FORGE SCALPER: breakout SELL — waiting for retest at %.2f", m5_bb_l);
            } else {
               direction = "SELL";
               sl = bo_sl; tp1 = bo_tp1; tp2 = bo_tp2;
               setup_type = "BB_BREAKOUT";
            }
            } // end adx_dur_ok && rsi_decl_ok
         }
         } // end ADX-sell-min else block (inner: if/else-if/else within session-OK else)
         } // end session-OK else block
      }
   }

   if(direction != "" && !ScalperDirectionCooldownOK(direction)) {
      JournalRecordSignal("SKIP","direction_cooldown",setup_type,direction,SymbolInfoDouble(_Symbol,SYMBOL_BID),spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
      return;
   }
   if(direction != "" && !ScalperPostSLCooldownOK(direction)) {
      JournalRecordSignal("SKIP","post_sl_cooldown",setup_type,direction,SymbolInfoDouble(_Symbol,SYMBOL_BID),spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
      return;
   }

   if(direction != "" && !in_tester && !NativeScalperM1GateOk(direction, m1_bull, m1_bear, m1_flat)) {
         PrintFormat("FORGE SCALPER: skip gate=m1 mode=%s dir=%s m1_ts=%.4f (CONFIRM=EMA/ATR vs threshold; TRIGGER=+prior M1 bar)",
                  NativeScalperM1Mode, direction, m1_trend_strength);
      JournalRecordSignal("SKIP","m1",setup_type,direction,SymbolInfoDouble(_Symbol,SYMBOL_BID),spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
      return;
   }

   if(direction != "" && NativeScalperRegimeBlocksDirection(direction)) {
      PrintFormat("FORGE SCALPER: skip gate=regime_countertrend label=%s conf=%.3f min=%.3f apply=%s dir=%s",
                  g_regime_label, g_regime_confidence, g_regime_ct_min_conf,
                  g_regime_apply_policy ? "true" : "false", direction);
      JournalRecordSignal("SKIP","regime_countertrend",setup_type,direction,SymbolInfoDouble(_Symbol,SYMBOL_BID),spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
      return;
   }

   if(direction == "") {
      datetime m5b = iTime(_Symbol, PERIOD_M5, 0);
      if(m5b != g_scalper_last_nosetup_log_bar) {
         g_scalper_last_nosetup_log_bar = m5b;
         bool bounce_armed = (g_scalper_mode == "BB_BOUNCE" || g_scalper_mode == "DUAL")
            && g_sc.bounce_enabled && m5_adx < bounce_adx_max_eff;
         double prox = bb_range * bounce_bb_prox_eff / 100.0;
         bool bounce_buy_zone = (mid <= m5_bb_l + prox);
         bool bounce_sell_zone = (mid >= m5_bb_u - prox);
         bool inside_bb = (prev_close >= m5_bb_l && prev_close <= m5_bb_u);
         PrintFormat("FORGE SCALPER: no setup mode=%s adx=%.1f rsi=%.1f prev=%.2f bb=[%.2f,%.2f] h1=%.4f h4=%.4f m1=%.4f m5=%.4f m15=%.4f",
                     g_scalper_mode, m5_adx, m5_rsi, prev_close, m5_bb_l, m5_bb_u,
                     h1_trend_strength, h4_trend_strength, m1_trend_strength, m5_trend_strength, m15_trend_strength);
         PrintFormat("FORGE SCALPER:   hint bounce_armed=%s adx_regime=%s buy_zone=%s sell_zone=%s inside_bb=%s reject_req=%s reclaim=%.0f%% tester_relax=%s",
                     bounce_armed ? "true" : "false",
                     (adx_hyst_active && g_adx_trend_regime) ? "trend" : "range",
                     bounce_buy_zone ? "true" : "false",
                     bounce_sell_zone ? "true" : "false",
                     inside_bb ? "true" : "false",
                     g_sc.bounce_require_rejection_candle ? "true" : "false",
                     g_sc.bounce_reclaim_pct,
                     in_tester ? "true" : "false");
         JournalRecordSignal("SKIP","no_setup","","",mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
      }
      return;
   }

   if(g_sc.breakout_max_reentry_atr_ext > 0.0 && m5_atr > 0.0) {
      bool atr_ext_blocked = false;
      if(direction == "BUY" && g_first_buy_entry_price > 0.0) {
         double ext = (mid - g_first_buy_entry_price) / m5_atr;
         if(ext > g_sc.breakout_max_reentry_atr_ext) atr_ext_blocked = true;
      }
      if(direction == "SELL" && g_first_sell_entry_price > 0.0) {
         double ext = (g_first_sell_entry_price - mid) / m5_atr;
         if(ext > g_sc.breakout_max_reentry_atr_ext) atr_ext_blocked = true;
      }
      if(atr_ext_blocked) {
         datetime m5bar = iTime(_Symbol, PERIOD_M5, 0);
         if(m5bar != g_scalper_last_atr_ext_log_bar) {
            g_scalper_last_atr_ext_log_bar = m5bar;
            JournalRecordSignal("SKIP", "entry_quality_atr_ext", setup_type, direction,
               mid, spread, m5_atr, m5_rsi, m5_adx, m5_bb_u, m5_bb_l, m5_bb_m,
               0, h1_trend_strength, 0);
         }
         return;
      }
   }

   // Entry Quality Gate — M5 bar body/direction/ATR/BB-expansion pre-filter
   // rsi/adx passed for logging only (not used in gate logic — OHLC-only checks)
   if(!CheckEntryQuality(direction, m5_atr, m5_bb_u, m5_bb_l, m5_rsi, m5_adx)) return;

   // DD event: tighten TP
   if(sentinel_tight) {
      if(direction == "BUY")
         tp1 = NormalizeDouble(bid + m5_atr * g_sc.dd_tight_tp_atr, _Digits);
      else
         tp1 = NormalizeDouble(ask - m5_atr * g_sc.dd_tight_tp_atr, _Digits);
      tp2 = 0;  // no runners during news
   }

   // Widen SL beyond ATR + structural + floor (hot-reload via scalper_config safety.native_sl_extra_buffer_points)
   if(direction == "BUY")
      sl = ApplyNativeSlExtraBuffer(true, sl, point);
   else if(direction == "SELL")
      sl = ApplyNativeSlExtraBuffer(false, sl, point);

   // R:R check (minimum 1.2)
   double sl_entry_ref = (direction == "BUY") ? bid : ask;
   double sl_dist = MathAbs(sl_entry_ref - sl);
   PrintFormat("FORGE SL CALC: %s %s entry=%.2f sl=%.2f dist=%.2f atr=%.2f sl_mult=%.2f floor_mult=%.2f extra_pts=%.1f OB_zones=%d",
               setup_type, direction, sl_entry_ref, sl, sl_dist, m5_atr,
               (setup_type == "BB_BOUNCE") ? g_sc.bounce_sl_atr_mult : g_sc.breakout_sl_atr_mult,
               g_sc.min_sl_atr_mult, g_sc.native_sl_extra_buffer_points, g_ob_zone_count);
   double rr_entry_ref = (direction == "BUY") ? ask : bid;
   double risk = MathAbs(rr_entry_ref - sl);
   double reward_tp1 = (direction == "BUY") ? (tp1 - rr_entry_ref) : (rr_entry_ref - tp1);
   double reward_tp2 = (tp2 > 0.0) ? ((direction == "BUY") ? (tp2 - rr_entry_ref) : (rr_entry_ref - tp2)) : 0.0;
   double reward = reward_tp1;
   if(setup_type == "BB_BOUNCE")
      reward = MathMax(reward_tp1, reward_tp2);
   if(setup_type == "BB_BREAKOUT" || setup_type == "BB_BREAKOUT_RETEST") {
      // Breakout scales out across 4 TPs — use the best reachable TP for the RR gate.
      // TP1(1.0x) and TP2(1.5x) always give RR<1.0 at 2.0x SL; TP3(2.5x) gives RR=1.25, TP4(4.0x)=2.0.
      double reward_tp3 = m5_atr * g_sc.breakout_tp3_atr_mult;
      double reward_tp4 = m5_atr * g_sc.breakout_tp4_atr_mult;
      reward = MathMax(reward_tp1, MathMax(reward_tp2, MathMax(reward_tp3, reward_tp4)));
   }
   if(risk <= 0 || reward / risk < rr_min_eff) {
      double rr_calc = (risk > 0.0) ? (reward / risk) : 0.0;
      Print("FORGE SCALPER: ", setup_type, " ", direction, " skipped — R:R ",
            DoubleToString(rr_calc, 2), " < ", DoubleToString(rr_min_eff, 2),
            " tp1_rwd=", DoubleToString(reward_tp1, 2), " tp2_rwd=", DoubleToString(reward_tp2, 2));
      datetime m5rr = iTime(_Symbol, PERIOD_M5, 0);
      if(m5rr != g_scalper_last_rrtoolow_log_bar) {
         g_scalper_last_rrtoolow_log_bar = m5rr;
         JournalRecordSignal("SKIP","rr_too_low",setup_type,direction,mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
      }
      return;
   }

   // Execute the native scalper trade group
   g_scalper_group_counter++;
   int group_id = g_scalper_group_counter;
   int group_magic = MagicNumber + group_id;
   g_trade.SetExpertMagicNumber(group_magic);

   bool lot_inputs_override_eff = false;
   string lot_source_mode = g_sc.lot_sizing_source;
   if(lot_source_mode == "INPUTS") lot_inputs_override_eff = true;
   else if(lot_source_mode == "CONFIG") lot_inputs_override_eff = false;
   else lot_inputs_override_eff = NativeScalperInputsOverrideLotSizing ? true : g_sc.lot_inputs_override;
   int base_n = lot_inputs_override_eff ? MathMax(1, ScalperTrades) : MathMax(1, g_sc.lot_num_trades);
   base_n = MathMax(1, MathMin(30, base_n));

   double lot_mult = 1.0;
   double dir_trend = 0.0;
   double lot_ratio = 0.0;
   double lot_max_mult = MathMax(1.0, MathMin(5.0, NativeScalperAutoLotMaxMultiplier));
   double lot_trend_ref = MathMax(0.10, NativeScalperAutoLotTrendRef);
   bool is_breakout_setup = (setup_type == "BB_BREAKOUT" || setup_type == "BB_BREAKOUT_RETEST");
   if(NativeScalperAutoLotByTrend && (!NativeScalperAutoLotBreakoutOnly || is_breakout_setup)) {
      double dir_h1 = (direction == "BUY") ? MathMax(0.0, h1_trend_strength) : MathMax(0.0, -h1_trend_strength);
      double dir_h4 = (direction == "BUY") ? MathMax(0.0, h4_trend_strength) : MathMax(0.0, -h4_trend_strength);
      dir_trend = (dir_h1 + dir_h4) / 2.0;
      lot_ratio = MathMin(1.0, dir_trend / lot_trend_ref);
      lot_mult = 1.0 + lot_ratio * (lot_max_mult - 1.0);
   }

   bool env_tr = (g_sc.lot_min_trades > 0 || g_sc.lot_max_trades > 0);
   int env_lo = 1, env_hi = 20;
   if(env_tr) {
      env_lo = g_sc.lot_min_trades > 0 ? g_sc.lot_min_trades : 1;
      env_hi = g_sc.lot_max_trades > 0 ? g_sc.lot_max_trades : 20;
      env_lo = MathMax(1, MathMin(30, env_lo));
      env_hi = MathMax(1, MathMin(30, env_hi));
      if(env_lo > env_hi) { int sw = env_lo; env_lo = env_hi; env_hi = sw; }
   }
   // ADX-based leg count — strong confirmed trend = more immediate exposure
   // Complements ForgeResolveNumTrades H1/H4 strength adjustments.
   // ADX < 25: direction weak/unconfirmed → trim base by 1 (htf-unclear cap handles the rest)
   // ADX 35–block: strong confirmed trend, not yet extended → boost base by 2
   // CHANGELOG: 2026-05-10 — conditional sizing (ADX tier → leg count). See CHANGELOG.md.
   if(is_breakout_setup) {
      if(m5_adx < 25.0)
         base_n = MathMax(1, base_n - 1);
      else if(m5_adx >= 35.0 && m5_adx < (double)g_sc.breakout_adx_sell_block_threshold)
         base_n = MathMin(30, base_n + 2);
      PrintFormat("FORGE SCALPER: ADX=%.1f → leg count base_n=%d (range %d–%d)",
                  m5_adx, base_n, env_lo, env_hi);
   }
   string trades_policy_out = "";
   int n = ForgeResolveNumTrades(base_n, env_lo, env_hi, env_tr, setup_type,
                                 g_regime_confidence, g_regime_label, lot_mult, trades_policy_out);
   bool htf_clear_with_trade = false;
   double clr_thr = trend_thr_eff * g_sc.native_legs_clear_trend_factor;
   if(clr_thr > 0 && (direction == "BUY" || direction == "SELL")) {
      if(direction == "BUY")
         htf_clear_with_trade = (h1_trend_strength >= clr_thr && h4_trend_strength >= clr_thr);
      else
         htf_clear_with_trade = (h1_trend_strength <= -clr_thr && h4_trend_strength <= -clr_thr);
   }
   if(g_sc.native_legs_max_when_unclear > 0 && !htf_clear_with_trade) {
      int cap_uc = MathMax(1, MathMin(30, g_sc.native_legs_max_when_unclear));
      if(n > cap_uc) {
         n = cap_uc;
         trades_policy_out += " legs_htf_unclear_cap=" + IntegerToString(cap_uc) + ";";
      }
   }
   if(direction == "SELL" && SymbolIsGoldFamily() && g_sc.gold_native_max_sell_legs > 0) {
      int cap_au = MathMax(1, MathMin(30, g_sc.gold_native_max_sell_legs));
      if(n > cap_au) {
         n = cap_au;
         trades_policy_out += " xau_sell_leg_cap=" + IntegerToString(cap_au) + ";";
      }
   }
   int tr_min_log = 0, tr_max_log = 0;
   if(env_tr) { tr_min_log = env_lo; tr_max_log = env_hi; }

   // Fix 7 (2.6.8): half lot when BB_BREAKOUT SELL price has pulled back inside the BB band
   double inside_band_factor = 1.0;
   if(direction == "SELL" && is_breakout_setup && mid > m5_bb_l
      && g_sc.breakout_sell_inside_band_lot_factor > 0.0 && g_sc.breakout_sell_inside_band_lot_factor < 1.0) {
      inside_band_factor = g_sc.breakout_sell_inside_band_lot_factor;
      PrintFormat("FORGE SCALPER: SELL inside band — lot factor=%.2f (mid=%.2f > bb_l=%.2f)",
                  inside_band_factor, mid, m5_bb_l);
   }
   // Cardwell near-floor lot factor (0.25x): RSI 20-25 in crash bypass = uncertain reversal zone
   // Allows participation in crash continuation without full exposure at extreme RSI.
   double near_floor_factor = 1.0;
   if(direction == "SELL" && is_breakout_setup
      && g_sc.breakout_h1h4_crash_sell && h1_bear && h4_bear
      && m5_rsi > g_sc.breakout_h1h4_crash_sell_rsi_min && m5_rsi <= 25.0
      && g_sc.breakout_near_floor_lot_factor > 0.0 && g_sc.breakout_near_floor_lot_factor < 1.0) {
      near_floor_factor = g_sc.breakout_near_floor_lot_factor;
      PrintFormat("FORGE SCALPER: SELL near Cardwell floor RSI=%.1f — lot factor=%.2f", m5_rsi, near_floor_factor);
   }
   // Stack lot factor (0.25x): 2nd concurrent group in same direction = reduced exposure
   // Scalper stacking: 1st entry full size, additional concurrent entries at fractional lot.
   double stack_factor = 1.0;
   if(g_sc.same_direction_stack_lot_factor > 0.0 && g_sc.same_direction_stack_lot_factor < 1.0
      && ScalperOpenGroupCountByDirection(direction) >= 1) {
      stack_factor = g_sc.same_direction_stack_lot_factor;
      PrintFormat("FORGE SCALPER: %s stack entry — lot factor=%.2f", direction, stack_factor);
   }
   // ADX-tiered lot factor (2.7.7): the more extended the trend, the smaller the bet
   // Research: OpoFinance/Trade2Win — ADX lags on M5; use M15 ADX for tier decision
   // ADX 35-44 → 0.25×  |  ADX 45-54 → 1/8th  |  ADX ≥55 → 1/16th
   double adx_lot_factor = 1.0;
   if(direction == "SELL" && is_breakout_setup) {
      double _adx_ref = m5_adx;
      if(g_sc.breakout_adx_lot_use_m15) {
         double _m15adx[1];
         if(CopyBuffer(g_mtf[1].h_adx, 0, 0, 1, _m15adx) == 1) _adx_ref = _m15adx[0];
      }
      if(_adx_ref >= g_sc.breakout_adx_lot_high_threshold && g_sc.breakout_adx_lot_factor_high > 0)
         adx_lot_factor = g_sc.breakout_adx_lot_factor_high;  // 1/8th = 0.01 lot at base 0.08 (broker min)
      else if(_adx_ref >= g_sc.breakout_adx_lot_mid_threshold && g_sc.breakout_adx_lot_factor_mid > 0)
         adx_lot_factor = g_sc.breakout_adx_lot_factor_mid;   // 0.25× = 0.02 lot
      if(adx_lot_factor < 1.0)
         PrintFormat("FORGE SCALPER: SELL ADX(M15)=%.1f → ADX lot tier=%.4f", _adx_ref, adx_lot_factor);
   }
   // BB_BOUNCE fractional lot — allows smaller position sizing for mean-reversion entries.
   double bounce_factor = (!is_breakout_setup && g_sc.bounce_lot_factor > 0.0 && g_sc.bounce_lot_factor < 1.0)
                          ? g_sc.bounce_lot_factor : 1.0;
   // Compound factor floor: 0.125 = broker minimum lot (0.01) at base lot 0.08.
   // ADX >= 55 entries are now BLOCKED (not taken at 1/16th which rounded to same as 1/8th).
   // Floor ensures no entry falls below 0.01 regardless of how many reducers stack.
   double combined_lot_factor = MathMax(0.125, inside_band_factor * near_floor_factor * stack_factor * adx_lot_factor * bounce_factor);
   g_last_combined_lot_factor = combined_lot_factor;
   double base_lot = lot_inputs_override_eff ? ScalperLot : g_sc.lot_fixed;
   double lot = NormalizeLot(base_lot * lot_mult * combined_lot_factor);
   double tp2_price = (tp2 > 0) ? tp2 : tp1;
   double tp1_split_pct = is_breakout_setup ? g_sc.breakout_tp1_close_pct : g_sc.bounce_tp1_close_pct;
   int tp1_count = (int)MathCeil(n * tp1_split_pct / 100.0);
   int init_cap = MathMax(1, MathMin(30, g_sc.staged_initial_legs));
   // Staged scale-in: open init_cap legs immediately; remainder added via ManageStagedNativeLegs.
   // When staged_initial_legs >= n, ALL legs fire at once (immediate multi-leg — scalp mode).
   // Fix 2026-05-10: was MathMin(init_cap, n-1) which always held one back even when init_cap>=n.
   // CHANGELOG: 2026-05-10 — staged_initial_legs=8 now fires all n legs at once when init_cap>=n.
   int open_first = n;
   bool staging_on = false;
   bool staging_eff = (g_sc.staged_entry_enabled || g_sc.native_force_staged_scale_in) && n > 1;
   if(staging_eff) {
      int wave1 = MathMin(init_cap, n);   // init_cap >= n → fire all; init_cap < n → fire init_cap
      if(wave1 < 1) wave1 = 1;
      open_first = wave1;
      staging_on = (open_first < n);
   }
   open_first = MathMax(1, MathMin(n, open_first));
   int opened = 0;
   PrintFormat("FORGE SCALPER STAGING: staged=%s force_layer=%s htf_clear=%s n=%d init_cap=%d open_first=%d staging_on=%s %s",
               g_sc.staged_entry_enabled ? "true" : "false",
               g_sc.native_force_staged_scale_in ? "true" : "false",
               htf_clear_with_trade ? "true" : "false",
               n, init_cap, open_first,
               staging_on ? "true" : "false", trades_policy_out);

   // One order attempt per second — prevents sub-second tick floods while still allowing retries across ticks.
   if(TimeCurrent() == g_scalper_last_attempt_time) return;

   for(int i = 0; i < open_first; i++) {
      double tp_for_this = (i < tp1_count) ? tp1 : tp2_price;
      string tp_label = (i < tp1_count) ? "TP1" : "TP2";
      string comment = "SCALP|" + setup_type + "|G" + IntegerToString(group_id) + "|" + tp_label;
      bool ok = false;
      if(direction == "BUY") {
         if(g_sc.native_scalper_use_limit_entry && !is_breakout_setup && m5_bb_l > 0) {
            double limit_px = NormalizeDouble(m5_bb_l, _Digits);
            if(!ValidateStops(limit_px, sl, tp_for_this, ORDER_TYPE_BUY_LIMIT)) {
               Print("FORGE SCALPER: invalid BUY_LIMIT stops for group ", group_id, " leg ", i + 1);
               continue;
            }
            ok = g_trade.BuyLimit(lot, limit_px, _Symbol, NormalizeDouble(sl, _Digits),
                                  NormalizeDouble(tp_for_this, _Digits), 0, 0, comment);
         } else {
            if(!ValidateStops(ask, sl, tp_for_this, ORDER_TYPE_BUY)) {
               Print("FORGE SCALPER: invalid BUY stops for group ", group_id, " leg ", i + 1);
               continue;
            }
            ok = g_trade.Buy(lot, _Symbol, ask, NormalizeDouble(sl, _Digits),
                             NormalizeDouble(tp_for_this, _Digits), comment);
         }
      } else {
         if(g_sc.native_scalper_use_limit_entry && !is_breakout_setup && m5_bb_u > 0) {
            double limit_px = NormalizeDouble(m5_bb_u, _Digits);
            if(!ValidateStops(limit_px, sl, tp_for_this, ORDER_TYPE_SELL_LIMIT)) {
               Print("FORGE SCALPER: invalid SELL_LIMIT stops for group ", group_id, " leg ", i + 1);
               continue;
            }
            ok = g_trade.SellLimit(lot, limit_px, _Symbol, NormalizeDouble(sl, _Digits),
                                   NormalizeDouble(tp_for_this, _Digits), 0, 0, comment);
         } else {
            if(!ValidateStops(bid, sl, tp_for_this, ORDER_TYPE_SELL)) {
               Print("FORGE SCALPER: invalid SELL stops for group ", group_id, " leg ", i + 1);
               continue;
            }
            ok = g_trade.Sell(lot, _Symbol, bid, NormalizeDouble(sl, _Digits),
                              NormalizeDouble(tp_for_this, _Digits), comment);
         }
      }
      if(ok) opened++;
      else {
         Print("FORGE SCALPER: leg failed retcode=", g_trade.ResultRetcode(), " group=", group_id, " leg=", i + 1);
         g_scalper_last_attempt_time = TimeCurrent();
      }
      Sleep(50);
   }

   g_trade.SetExpertMagicNumber(MagicNumber);
   if(opened <= 0) {
      Print("FORGE SCALPER: ", setup_type, " ", direction, " rejected — no orders opened");
      JournalRecordSignal("SKIP","execution_failed",setup_type,direction,mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
      return;
   }

   g_scalper_session_trades++;
   g_scalper_last_entry_bar = iTime(_Symbol, PERIOD_M5, 0);
   if(g_scalper_last_direction != direction)
      g_scalper_last_direction_time = TimeCurrent();
   g_scalper_last_direction = direction;

   // Register group for TP management
   int gi = ArraySize(g_groups);
   ArrayResize(g_groups, gi + 1);
   g_groups[gi].id            = group_id;
   g_groups[gi].direction     = direction;
   g_groups[gi].tp1           = tp1;
   g_groups[gi].tp2           = tp2;
   // TP3 live target — runner rides to TP3 after TP2 hit. 0 disables staging.
   // Only set for breakout setups; tp3_atr_mult=0 or bounce disables it.
   g_groups[gi].tp3 = (is_breakout_setup && g_sc.breakout_tp3_atr_mult > 0.0)
                      ? NormalizeDouble((direction == "SELL")
                          ? rr_entry_ref - m5_atr * g_sc.breakout_tp3_atr_mult
                          : rr_entry_ref + m5_atr * g_sc.breakout_tp3_atr_mult, _Digits)
                      : 0.0;
   g_groups[gi].tp1_close_pct = tp1_split_pct;
   g_groups[gi].tp1_hit       = false;
   g_groups[gi].tp2_hit       = false;
   g_groups[gi].be_moved      = false;
   g_groups[gi].move_be_on_tp1 = is_breakout_setup ? g_sc.breakout_move_be : true;
   g_groups[gi].magic_offset  = group_magic;
   g_groups[gi].staging_active = staging_on;
   g_groups[gi].had_positions = false;
   g_groups[gi].scalper_setup = staging_on ? setup_type : "";
   g_groups[gi].legs_planned = staging_on ? n : 0;
   g_groups[gi].next_staged_leg_i = staging_on ? open_first : 0;
   g_groups[gi].staged_sl = staging_on ? sl : 0;
   g_groups[gi].staged_lot = staging_on ? lot : 0;
   g_groups[gi].staged_is_breakout = staging_on ? is_breakout_setup : false;
   g_groups[gi].staged_tp1_legs = staging_on ? tp1_count : 0;
   g_groups[gi].staged_anchor = staging_on ? ((direction == "BUY") ? ask : bid) : 0;
   g_groups[gi].staged_next_add = staging_on ? (TimeCurrent() + MathMax(3, g_sc.staged_add_interval_sec)) : 0;
   // Post-TP1 ladder context: execution price is crash_low for SELL (bid) or entry_high for BUY (ask)
   g_groups[gi].crash_low  = (direction == "SELL") ? bid : ask;
   g_groups[gi].entry_atr  = m5_atr;
   int native_group_positions[];
   GetGroupPositions(group_magic, native_group_positions);
   g_groups[gi].had_positions = (ArraySize(native_group_positions) > 0);

   // ── Cardwell SELL LIMIT cascade (2.7.7b) ────────────────────────────────────────
   // Place SELL LIMIT above entry to catch RSI bounce toward Bear Resistance (50-60).
   // Cardwell: in downtrend, sell the bounce back to resistance — not just the breakout.
   // Only on confirmed crash (H1+H4 bear) to match Cardwell downtrend range (RSI 20-60).
   if(direction == "SELL" && is_breakout_setup && g_sc.breakout_sell_limit_enabled
      && g_sc.breakout_h1h4_crash_sell && h1_bear && h4_bear
      && m5_rsi > g_sc.breakout_h1h4_crash_sell_rsi_min) {
      double limit_price = NormalizeDouble(bid + m5_atr * g_sc.breakout_sell_limit_atr_mult, _Digits);
      double _broker_min = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
      double limit_lot   = NormalizeLot(MathMax(_broker_min, g_sc.lot_fixed * g_sc.breakout_sell_limit_lot_factor));
      datetime limit_exp = TimeTradeServer() + (datetime)(g_sc.breakout_sell_limit_expiry_bars * PeriodSeconds(PERIOD_M5));
      MqlTradeRequest _lreq = {}; MqlTradeResult _lres = {};
      _lreq.action     = TRADE_ACTION_PENDING;
      _lreq.type       = ORDER_TYPE_SELL_LIMIT;
      _lreq.symbol     = _Symbol;
      _lreq.volume     = limit_lot;
      _lreq.price      = limit_price;
      _lreq.sl         = NormalizeDouble(sl, _Digits);
      _lreq.tp         = NormalizeDouble(tp1, _Digits);
      _lreq.type_time  = ORDER_TIME_SPECIFIED;
      _lreq.expiration = limit_exp;
      _lreq.type_filling = ORDER_FILLING_RETURN;
      _lreq.magic      = (ulong)group_magic + 20000;  // distinct from market order magic
      _lreq.comment    = "SCALP_LIMIT|" + setup_type + "|G" + IntegerToString(group_id);
      g_trade.SetExpertMagicNumber((ulong)group_magic + 20000);
      if(OrderSend(_lreq, _lres) && _lres.order > 0) {
         // L1 always uses slot [0]; slot [1] is reserved for L2 (hard-coded below)
         if(!g_sell_limit_stack[0].active) {
            g_sell_limit_stack[0].ticket    = _lres.order;
            g_sell_limit_stack[0].group_id  = group_id;
            g_sell_limit_stack[0].mkt_magic = (ulong)group_magic;
            g_sell_limit_stack[0].expiry    = limit_exp;
            g_sell_limit_stack[0].active    = true;
            PrintFormat("FORGE SCALPER: SELL LIMIT placed ticket=%d price=%.2f (ATR×%.1f) lot=%.2f expiry=%s",
                        _lres.order, limit_price, g_sc.breakout_sell_limit_atr_mult, limit_lot,
                        TimeToString(limit_exp, TIME_DATE|TIME_SECONDS));
         }
      }
      // L2 SELL LIMIT — deeper Cardwell Bear Resistance zone (2.7.10 Day 1)
      // Uses slot [1]. Only placed when L1 placed successfully (same crash conditions apply).
      if(g_sc.breakout_sell_limit_l2_enabled) {
         double l2_price = NormalizeDouble(bid + m5_atr * g_sc.breakout_sell_limit_l2_atr_mult, _Digits);
         double l2_lot   = NormalizeLot(MathMax(_broker_min, g_sc.lot_fixed * g_sc.breakout_sell_limit_l2_lot_factor));
         datetime l2_exp = limit_exp;  // same expiry as L1
         MqlTradeRequest _l2req = {}; MqlTradeResult _l2res = {};
         _l2req.action     = TRADE_ACTION_PENDING;
         _l2req.type       = ORDER_TYPE_SELL_LIMIT;
         _l2req.symbol     = _Symbol;
         _l2req.volume     = l2_lot;
         _l2req.price      = l2_price;
         _l2req.sl         = NormalizeDouble(sl, _Digits);
         _l2req.tp         = NormalizeDouble(tp1, _Digits);
         _l2req.type_time  = ORDER_TIME_SPECIFIED;
         _l2req.expiration = l2_exp;
         _l2req.type_filling = ORDER_FILLING_RETURN;
         _l2req.magic      = (ulong)group_magic + 20001;  // distinct from L1 (+20000)
         _l2req.comment    = "SCALP_LIMIT_L2|" + setup_type + "|G" + IntegerToString(group_id);
         g_trade.SetExpertMagicNumber((ulong)group_magic + 20001);
         if(OrderSend(_l2req, _l2res) && _l2res.order > 0) {
            if(!g_sell_limit_stack[1].active) {
               g_sell_limit_stack[1].ticket    = _l2res.order;
               g_sell_limit_stack[1].group_id  = group_id;
               g_sell_limit_stack[1].mkt_magic = (ulong)group_magic;
               g_sell_limit_stack[1].expiry    = l2_exp;
               g_sell_limit_stack[1].active    = true;
               PrintFormat("FORGE SCALPER: SELL LIMIT L2 placed ticket=%d price=%.2f (ATR×%.2f) lot=%.2f",
                           _l2res.order, l2_price, g_sc.breakout_sell_limit_l2_atr_mult, l2_lot);
            }
         }
      }
      g_trade.SetExpertMagicNumber(MagicNumber);
   }

   int entry_candle_score = ScalperCandlePatternScore(direction == "BUY");
   Print("FORGE SCALPER: ", setup_type, " ", direction, " G", group_id,
         " — ", opened, "/", open_first, " now; ", n, " planned",
         staging_on ? " [STAGED]" : "",
         " @ ", DoubleToString(mid, 2),
         " lot=", DoubleToString(lot, 2), " (x", DoubleToString(lot_mult, 2), ")",
         " trend=", DoubleToString(dir_trend, 4),
         " SL=", DoubleToString(sl, 2), " TP1=", DoubleToString(tp1, 2),
         " TP2=", DoubleToString(tp2_price, 2),
         " ATR=", DoubleToString(m5_atr, 2),
         " RSI=", DoubleToString(m5_rsi, 1),
         " ADX=", DoubleToString(m5_adx, 1),
         " pattern_score=", IntegerToString(entry_candle_score),
         " POC=", DoubleToString(g_poc_price, 2),
         " VWAP=", DoubleToString(g_vwap_price, 2),
         " FIB50=", DoubleToString(g_fib_50, 2),
         " RSI_DIV=", g_rsi_div_type,
         " PSAR=", g_psar_state,
         " OB_zones=", IntegerToString(g_ob_zone_count),
         sentinel_tight ? " [DD_TIGHT_TP]" : "");

   DrawDivergenceArrow(g_rsi_div_type, direction == "BUY" ? ask : bid, iTime(_Symbol, PERIOD_M5, 0));

   // Write scalper_entry.json for BRIDGE to pick up and log to SCRIBE.
   // In Strategy Tester BRIDGE is not running — skip these writes to avoid leaving
   // a stale tester artifact that BRIDGE could misread as a live entry after restart.
   if(!in_tester) {
   string ej = "{";
   ej += "\"forge_version\":\"" + FORGE_VERSION + "\",";
   ej += "\"action\":\"FORGE_NATIVE_SCALP\",";
   ej += "\"setup_type\":\"" + setup_type + "\",";
   ej += "\"group_id\":" + IntegerToString(group_id) + ",";
   ej += "\"magic\":" + IntegerToString(group_magic) + ",";
   ej += "\"direction\":\"" + direction + "\",";
   ej += "\"entry_price\":" + DoubleToString(direction == "BUY" ? ask : bid, 2) + ",";
   ej += "\"sl\":" + DoubleToString(sl, 2) + ",";
   ej += "\"native_sl_extra_buffer_points\":" + DoubleToString(g_sc.native_sl_extra_buffer_points, 1) + ",";
   ej += "\"gold_native_max_sell_legs\":" + IntegerToString(g_sc.gold_native_max_sell_legs) + ",";
   ej += "\"native_legs_max_when_unclear\":" + IntegerToString(g_sc.native_legs_max_when_unclear) + ",";
   ej += "\"native_legs_clear_trend_factor\":" + DoubleToString(g_sc.native_legs_clear_trend_factor, 3) + ",";
   ej += "\"native_force_staged_scale_in\":" + (g_sc.native_force_staged_scale_in ? "true" : "false") + ",";
   ej += "\"htf_clear_with_trade\":" + (htf_clear_with_trade ? "true" : "false") + ",";
   ej += "\"tp1\":" + DoubleToString(tp1, 2) + ",";
   ej += "\"tp2\":" + DoubleToString(tp2_price, 2) + ",";
   ej += "\"lot_per_trade\":" + DoubleToString(lot, 2) + ",";
   ej += "\"lot_base\":" + DoubleToString(base_lot, 2) + ",";
   ej += "\"lot_source\":\"" + (lot_inputs_override_eff ? "inputs" : "config") + "\",";
   ej += "\"lot_multiplier\":" + DoubleToString(lot_mult, 3) + ",";
   ej += "\"auto_lot_enabled\":" + (NativeScalperAutoLotByTrend ? "true" : "false") + ",";
   ej += "\"auto_lot_breakout_only\":" + (NativeScalperAutoLotBreakoutOnly ? "true" : "false") + ",";
   ej += "\"auto_lot_max_multiplier\":" + DoubleToString(lot_max_mult, 2) + ",";
   ej += "\"auto_lot_trend_ref\":" + DoubleToString(lot_trend_ref, 2) + ",";
   ej += "\"auto_lot_dir_trend\":" + DoubleToString(dir_trend, 4) + ",";
   ej += "\"auto_lot_ratio\":" + DoubleToString(lot_ratio, 4) + ",";
   ej += "\"num_trades\":" + IntegerToString(n) + ",";
   ej += "\"trades_range_min\":" + IntegerToString(tr_min_log) + ",";
   ej += "\"trades_range_max\":" + IntegerToString(tr_max_log) + ",";
   ej += "\"trades_policy_reason\":\"" + JsonEscape(trades_policy_out) + "\",";
   ej += "\"trades_opened\":" + IntegerToString(opened) + ",";
   ej += "\"staged_entry\":" + (staging_on ? "true" : "false") + ",";
   ej += "\"staged_legs_pending\":" + IntegerToString(staging_on ? (n - open_first) : 0) + ",";
   ej += "\"m5_rsi\":" + DoubleToString(m5_rsi, 1) + ",";
   ej += "\"m5_adx\":" + DoubleToString(m5_adx, 1) + ",";
   ej += "\"m5_atr\":" + DoubleToString(m5_atr, 2) + ",";
   ej += "\"h1_trend_strength\":" + DoubleToString(h1_trend_strength, 4) + ",";
   ej += "\"h4_trend_strength\":" + DoubleToString(h4_trend_strength, 4) + ",";
   ej += "\"native_scalper_m1_mode\":\"" + JsonEscape(NativeScalperM1Mode) + "\",";
   ej += "\"m1_trend_strength\":" + DoubleToString(m1_trend_strength, 4) + ",";
   ej += "\"m1_prior_close\":" + DoubleToString(iClose(_Symbol, PERIOD_M1, 1), _Digits) + ",";
   ej += "\"m1_prior_open\":" + DoubleToString(iOpen(_Symbol, PERIOD_M1, 1), _Digits) + ",";
   ej += "\"prev_close\":" + DoubleToString(prev_close, _Digits) + ",";
   ej += "\"m5_bb_upper\":" + DoubleToString(m5_bb_u, _Digits) + ",";
   ej += "\"m5_bb_lower\":" + DoubleToString(m5_bb_l, _Digits) + ",";
   ej += "\"pending_entry_threshold_points\":" + DoubleToString(g_sc.pending_entry_threshold_points, 2) + ",";
   ej += "\"trend_strength_atr_threshold\":" + DoubleToString(g_sc.trend_strength_atr_threshold, 4) + ",";
   ej += "\"breakout_buffer_points\":" + DoubleToString(g_sc.breakout_buffer_points, 2) + ",";
   ej += "\"sentinel_tight\":" + (sentinel_tight ? "true" : "false") + ",";
   ej += "\"poc_price\":" + DoubleToString(g_poc_price, 2) + ",";
   ej += "\"vwap_price\":" + DoubleToString(g_vwap_price, 2) + ",";
   ej += "\"fib_50\":" + DoubleToString(g_fib_50, 2) + ",";
   ej += "\"fib_382\":" + DoubleToString(g_fib_382, 2) + ",";
   ej += "\"fib_618\":" + DoubleToString(g_fib_618, 2) + ",";
   ej += "\"rsi_divergence\":\"" + g_rsi_div_type + "\",";
   ej += "\"psar_state\":\"" + g_psar_state + "\",";
   ej += "\"pattern_score\":" + IntegerToString(entry_candle_score) + ",";
   ej += "\"timestamp\":\"" + JsonEscape(TimeToString(TimeGMT(), TIME_DATE|TIME_SECONDS)) + "Z\"";
   ej += "}";
   WriteJsonFileDual("scalper_entry.json", ej);
   // BRIDGE reads scalper_entry + market_data in one cycle; market_data was only refreshed from OnTimer,
   // causing no_mt5_exposure_for_magic when the snapshot predates these new positions. Flush immediately.
   WriteMarketData();
   }  // end if(!in_tester)

   double _taken_macd = 0.0, _taken_m15adx = 0.0;
   { double _h1ma[1], _h1si[1];  // log H1 MACD histogram — direction context for post-trade analysis
     if(g_h_macd != INVALID_HANDLE && CopyBuffer(g_h_macd,0,0,1,_h1ma)==1 && CopyBuffer(g_h_macd,1,0,1,_h1si)==1)
        _taken_macd = _h1ma[0] - _h1si[0]; }
   { double _tb[1]; if(CopyBuffer(g_mtf[1].h_adx, 0, 0, 1, _tb) == 1) _taken_m15adx = _tb[0]; }
   JournalRecordSignal("TAKEN","",setup_type,direction,
      direction=="BUY" ? SymbolInfoDouble(_Symbol,SYMBOL_ASK) : SymbolInfoDouble(_Symbol,SYMBOL_BID),
      spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,entry_candle_score,h1_trend_strength,0,
      _taken_macd, _taken_m15adx, g_last_combined_lot_factor);
   double entry_price = (direction == "BUY") ? SymbolInfoDouble(_Symbol,SYMBOL_ASK) : SymbolInfoDouble(_Symbol,SYMBOL_BID);
   if(direction == "BUY" && g_first_buy_entry_price <= 0.0)
      g_first_buy_entry_price = entry_price;
   if(direction == "SELL" && g_first_sell_entry_price <= 0.0)
      g_first_sell_entry_price = entry_price;
}

//+------------------------------------------------------------------+
void GetGroupPositions(int magic, int &tickets[]) {
   ArrayResize(tickets, 0);
   for(int i=0;i<PositionsTotal();i++) {
      if(g_pos.SelectByIndex(i) && g_pos.Symbol()==_Symbol && (int)g_pos.Magic()==magic) {
         int sz = ArraySize(tickets);
         ArrayResize(tickets, sz+1);
         tickets[sz] = (int)g_pos.Ticket();
      }
   }
}

double NormalizeLot(const double lot) {
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double min_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double v = MathMax(min_lot, MathMin(max_lot, lot));
   int precision = 2;
   if(step > 0) precision = (int)MathRound(-MathLog10(step));
   if(precision < 0) precision = 0;
   if(precision > 8) precision = 8;
   return NormalizeDouble(v, precision);
}

bool ValidateStops(const double entry, const double sl, const double tp, const ENUM_ORDER_TYPE type) {
   if(entry <= 0 || sl <= 0 || tp <= 0) return false;
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int stops_level = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double min_dist = MathMax(stops_level * point, point);
   if(type == ORDER_TYPE_BUY || type == ORDER_TYPE_BUY_LIMIT || type == ORDER_TYPE_BUY_STOP || type == ORDER_TYPE_BUY_STOP_LIMIT) {
      if(sl >= (entry - min_dist)) return false;
      if(tp <= (entry + min_dist)) return false;
      return true;
   }
   if(type == ORDER_TYPE_SELL || type == ORDER_TYPE_SELL_LIMIT || type == ORDER_TYPE_SELL_STOP || type == ORDER_TYPE_SELL_STOP_LIMIT) {
      if(sl <= (entry + min_dist)) return false;
      if(tp >= (entry - min_dist)) return false;
      return true;
   }
   return false;
}

void RebuildGroups() {
   ArrayResize(g_groups, 0);
   for(int i = 0; i < PositionsTotal(); i++) {
      if(!g_pos.SelectByIndex(i) || g_pos.Symbol() != _Symbol) continue;
      int pm = (int)g_pos.Magic();
      if(pm < MagicNumber || pm >= MagicNumber + 10000) continue;
      int gid = pm - MagicNumber;
      bool found = false;
      for(int g = 0; g < ArraySize(g_groups); g++) {
         if(g_groups[g].magic_offset == pm) {
            found = true;
            break;
         }
      }
      if(found) continue;
      int n = ArraySize(g_groups);
      ArrayResize(g_groups, n + 1);
      g_groups[n].id = gid;
      g_groups[n].direction = (g_pos.PositionType() == POSITION_TYPE_BUY) ? "BUY" : "SELL";
      g_groups[n].tp1 = g_pos.TakeProfit();
      g_groups[n].tp2 = g_pos.TakeProfit();
      g_groups[n].tp3 = 0;         // RebuildGroups path — tp3 not recomputed from live position
      g_groups[n].tp1_close_pct = 50;
      g_groups[n].tp1_hit = false;
      g_groups[n].tp2_hit = false;
      g_groups[n].be_moved = false;
      g_groups[n].move_be_on_tp1 = true;
      g_groups[n].magic_offset = pm;
      g_groups[n].staging_active = false;
      g_groups[n].had_positions = true;
      g_groups[n].scalper_setup = "";
      g_groups[n].legs_planned = 0;
      g_groups[n].next_staged_leg_i = 0;
      g_groups[n].staged_sl = 0;
      g_groups[n].staged_lot = 0;
      g_groups[n].staged_is_breakout = false;
      g_groups[n].staged_tp1_legs = 0;
      g_groups[n].staged_anchor = 0;
      g_groups[n].staged_next_add = 0;
   }
   if(ArraySize(g_groups) > 0) {
      Print("FORGE: Rebuilt ", ArraySize(g_groups), " trade groups from open positions");
   }
}

// ArmPostTP1Ladder — called from ManageOpenGroups() when TP1 is hit on a SELL group (2.7.10 Day 2)
// Places SELL STOP continuation below TP1 when RSI not yet exhausted.
// TRUE SCALING: searches slots [2..3] for first free slot — up to 2 concurrent SELL STOPs
// (one per group that fires TP1, e.g. G5001 and G5002 within ~10 pips of each other).
// Slot [4] reserved for Day 3 BUY LIMIT recovery.
// Enable via FORGE_SELL_STOP_CONT_ENABLED=1 in .env.
void ArmPostTP1Ladder(const int gi) {
   if(gi < 0 || gi >= ArraySize(g_groups)) return;
   // Day 2 only arms for SELL groups — BUY recovery is Day 3
   if(g_groups[gi].direction != "SELL") return;
   double crash_low = g_groups[gi].crash_low;
   double entry_atr = g_groups[gi].entry_atr;
   int    grp_id    = g_groups[gi].id;
   int    grp_magic = g_groups[gi].magic_offset;
   // Guard: BRIDGE groups have entry_atr=0 (ATR unavailable at BRIDGE registration time)
   if(crash_low <= 0 || entry_atr <= 0) {
      if(g_sc.sell_stop_cont_enabled)
         PrintFormat("FORGE: ArmPostTP1Ladder G%d — skipped (entry_atr unavailable; BRIDGE group)",
                     grp_id);
      return;
   }

   // SELL STOP continuation — multi-leg: place up to sell_stop_cont_legs orders in slots [2..8].
   // Each leg = full lot (lot_factor=1.0 default) — cascade is a confirmed continuation, not a minor add.
   // Rationale: TP1 hit proves the trend is real. ADX rising + RSI declining = indicators aligned.
   // Use same lot as primary entry — this IS a primary entry at a better (confirmed) price.
   if(g_sc.sell_stop_cont_enabled) {
      double _rbuf[1];
      double cur_rsi = (g_mtf[0].h_rsi != INVALID_HANDLE && CopyBuffer(g_mtf[0].h_rsi, 0, 0, 1, _rbuf) == 1) ? _rbuf[0] : 0;
      if(cur_rsi > 0 && cur_rsi <= g_sc.sell_stop_cont_min_rsi) {
         PrintFormat("FORGE: ArmPostTP1Ladder G%d — SELL STOP skipped (RSI=%.1f <= %.1f, exhausted)",
                     grp_id, cur_rsi, g_sc.sell_stop_cont_min_rsi);
      } else {
         double tp1_ref  = g_groups[gi].tp1;
         double ss_price = NormalizeDouble(tp1_ref - entry_atr * g_sc.sell_stop_cont_atr_mult, _Digits);
         double ss_sl    = NormalizeDouble(tp1_ref + entry_atr * g_sc.sell_stop_cont_atr_mult, _Digits);
         double ss_lot   = NormalizeLot(MathMax(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN),
                                                g_sc.lot_fixed * g_sc.sell_stop_cont_lot_factor));
         datetime ss_exp = TimeCurrent() + (datetime)(g_sc.sell_stop_cont_expiry_bars * PeriodSeconds(PERIOD_M5));
         double ss_tp    = (g_sc.sell_stop_cont_tp_atr_mult > 0.0)
                           ? NormalizeDouble(ss_price - entry_atr * g_sc.sell_stop_cont_tp_atr_mult, _Digits)
                           : 0.0;
         int legs_placed = 0;
         int legs_target = MathMin(g_sc.sell_stop_cont_legs, 7); // max 7 legs — slots [2..8]
         for(int _s = 2; _s <= 8 && legs_placed < legs_target; _s++) {
            if(g_sell_limit_stack[_s].active) continue; // slot occupied — skip to next
            ulong ss_magic = (ulong)grp_magic + 20002 + (ulong)(_s - 2); // slot2→+20002 .. slot8→+20008
            MqlTradeRequest _ssr = {}; MqlTradeResult _ssres = {};
            _ssr.action       = TRADE_ACTION_PENDING;
            _ssr.type         = ORDER_TYPE_SELL_STOP;
            _ssr.symbol       = _Symbol;
            _ssr.volume       = ss_lot;
            _ssr.price        = ss_price;
            _ssr.sl           = ss_sl;
            _ssr.tp           = ss_tp;
            _ssr.type_time    = ORDER_TIME_SPECIFIED;
            _ssr.expiration   = ss_exp;
            _ssr.type_filling = ORDER_FILLING_RETURN;
            _ssr.magic        = ss_magic;
            _ssr.comment      = "SCALP_SELL_STOP_CONT|G" + IntegerToString(grp_id) + "|L" + IntegerToString(legs_placed+1);
            g_trade.SetExpertMagicNumber(ss_magic);
            if(OrderSend(_ssr, _ssres) && _ssres.order > 0) {
               g_sell_limit_stack[_s].ticket    = _ssres.order;
               g_sell_limit_stack[_s].group_id  = grp_id;
               g_sell_limit_stack[_s].mkt_magic = (ulong)grp_magic;
               g_sell_limit_stack[_s].expiry    = ss_exp;
               g_sell_limit_stack[_s].active    = true;
               legs_placed++;
               if(legs_placed == 1)
                  PrintFormat("FORGE: SELL STOP CONT G%d — placing %d legs price=%.2f TP=%.2f SL=%.2f lot=%.2f ATR=%.2f RSI=%.1f",
                              grp_id, legs_target, ss_price, ss_tp, ss_sl, ss_lot, entry_atr, cur_rsi);
            } else {
               PrintFormat("FORGE: SELL STOP CONT placement FAILED G%d slot[%d] retcode=%d", grp_id, _s, _ssres.retcode);
            }
            g_trade.SetExpertMagicNumber(MagicNumber);
         }
         if(legs_placed == 0)
            PrintFormat("FORGE: ArmPostTP1Ladder G%d — no free slots [2..8], all %d cascade legs skipped", grp_id, legs_target);
         else
            PrintFormat("FORGE: ArmPostTP1Ladder G%d — %d/%d SELL STOP legs placed", grp_id, legs_placed, legs_target);
      }
   }
   // BUY LIMIT recovery (slot [4]) — Cardwell Bull Support entry at crash low after SELL TP1
   // Captures the May-1-style parabolic reversal: RSI bounces from 20 back through 35 = recovery starting.
   // Price: TP1 level (crash low) — buy at the established swing low, not chasing.
   // BUY LIMIT at bid-level of TP1 is valid pending: bid ≈ ask - spread, order sits below current ask.
   if(g_sc.buy_limit_recovery_enabled) {
      if(g_sell_limit_stack[9].active) {
         PrintFormat("FORGE: ArmPostTP1Ladder G%d — slot [9] occupied, BUY LIMIT recovery skipped", grp_id);
      } else {
         double _rbuf2[1];
         double cur_rsi_buy = (g_mtf[0].h_rsi != INVALID_HANDLE && CopyBuffer(g_mtf[0].h_rsi, 0, 0, 1, _rbuf2) == 1) ? _rbuf2[0] : 0;
         if(cur_rsi_buy > 0 && cur_rsi_buy < g_sc.buy_limit_recovery_min_rsi) {
            PrintFormat("FORGE: G%d BUY LIMIT skipped (RSI=%.1f < min=%.1f, Bull Support not confirmed)",
                        grp_id, cur_rsi_buy, g_sc.buy_limit_recovery_min_rsi);
         } else {
            double tp1_ref_buy = g_groups[gi].tp1;   // crash low = TP1 hit price (bid at hit)
            double ask_now     = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            double _pt         = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
            int    _stoplv     = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
            double min_dist    = MathMax(_stoplv * _pt, _pt);
            // BUY LIMIT must be below current ask by at least broker min-stop distance.
            // tp1_ref_buy = bid at TP1 time ≈ ask - spread → may be at or slightly above ask.
            // Clamp to ask - min_dist to guarantee a valid pending order price.
            double bl_price = NormalizeDouble(MathMin(tp1_ref_buy, ask_now - min_dist), _Digits);
            double bl_sl    = NormalizeDouble(bl_price - entry_atr * g_sc.buy_limit_recovery_sl_atr_mult, _Digits);
            // Validate price and SL are tradeable before sending
            if(bl_price <= 0 || bl_sl <= 0 || bl_price <= bl_sl + min_dist) {
               PrintFormat("FORGE: BUY LIMIT RECOV skipped G%d — invalid price %.2f or SL %.2f (ask=%.2f min_dist=%.5f)",
                           grp_id, bl_price, bl_sl, ask_now, min_dist);
               g_trade.SetExpertMagicNumber(MagicNumber);
               // fall through to Day 3 done — don't skip Day 3 entirely if price math fails
            } else {
            double bl_lot   = NormalizeLot(MathMax(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN),
                                                   g_sc.lot_fixed * g_sc.buy_limit_recovery_lot_factor));
            datetime bl_exp = TimeCurrent() + (datetime)(g_sc.buy_limit_recovery_expiry_bars * PeriodSeconds(PERIOD_M5));
            MqlTradeRequest _blr = {}; MqlTradeResult _blres = {};
            _blr.action       = TRADE_ACTION_PENDING;
            _blr.type         = ORDER_TYPE_BUY_LIMIT;
            _blr.symbol       = _Symbol;
            _blr.volume       = bl_lot;
            _blr.price        = bl_price;
            _blr.sl           = bl_sl;
            _blr.tp           = 0;    // no TP — trail manually or let RSI cancellation handle exit
            _blr.type_time    = ORDER_TIME_SPECIFIED;
            _blr.expiration   = bl_exp;
            _blr.type_filling = ORDER_FILLING_RETURN;
            _blr.magic        = (ulong)grp_magic + 20009; // slot[9] — clear of cascade slots [2..8]
            _blr.comment      = "SCALP_BUY_LIMIT_RECOV|G" + IntegerToString(grp_id);
            g_trade.SetExpertMagicNumber(_blr.magic);
            if(OrderSend(_blr, _blres) && _blres.order > 0) {
               g_sell_limit_stack[9].ticket    = _blres.order;
               g_sell_limit_stack[9].group_id  = grp_id;
               g_sell_limit_stack[9].mkt_magic = (ulong)grp_magic;
               g_sell_limit_stack[9].expiry    = bl_exp;
               g_sell_limit_stack[9].active    = true;
               PrintFormat("FORGE: BUY LIMIT RECOV placed G%d slot[9] ticket=%d price=%.2f SL=%.2f lot=%.2f RSI=%.1f exp=%s",
                           grp_id, _blres.order, bl_price, bl_sl, bl_lot, cur_rsi_buy,
                           TimeToString(bl_exp, TIME_DATE|TIME_SECONDS));
            } else {
               PrintFormat("FORGE: BUY LIMIT RECOV placement FAILED G%d retcode=%d", grp_id, _blres.retcode);
            }
            g_trade.SetExpertMagicNumber(MagicNumber);
            } // end price-validity else
         }
      }
   }
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result) {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   ulong deal = trans.deal;
   if(deal == 0 || !HistoryDealSelect(deal)) return;
   long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);
   if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY) return;
   long magic = HistoryDealGetInteger(deal, DEAL_MAGIC);
   if(magic < MagicNumber || magic >= MagicNumber + 10000) return;
   double profit = HistoryDealGetDouble(deal, DEAL_PROFIT)
                 + HistoryDealGetDouble(deal, DEAL_SWAP)
                 + HistoryDealGetDouble(deal, DEAL_COMMISSION);
   if(profit < 0) {
      g_scalper_last_loss_time = TimeGMT();
      Print("FORGE: cooldown triggered after loss deal ", (long)deal, " profit=", DoubleToString(profit, 2));
      // Cancel all cascade pending orders when market position hits SL (all 5 slots)
      long _deal_magic = HistoryDealGetInteger(deal, DEAL_MAGIC);
      for(int _si = 0; _si < 10; _si++) {
         if(g_sell_limit_stack[_si].active && (long)g_sell_limit_stack[_si].mkt_magic == _deal_magic) {
            if(OrderSelect(g_sell_limit_stack[_si].ticket))
               g_trade.OrderDelete(g_sell_limit_stack[_si].ticket);
            g_sell_limit_stack[_si].active = false;
            PrintFormat("FORGE SCALPER: cancelled SELL LIMIT %d (market SL fired group magic %d)",
                        g_sell_limit_stack[_si].ticket, _deal_magic);
         }
      }
      // Direction-specific post-SL cooldown: OUT deal type is opposite of the position direction
      string cmt = HistoryDealGetString(deal, DEAL_COMMENT);
      if(StringFind(cmt, "sl") >= 0) {
         long dtype = HistoryDealGetInteger(deal, DEAL_TYPE);
         // DEAL_TYPE_BUY closes a SELL position (SL on SELL group)
         if(dtype == DEAL_TYPE_BUY)  g_last_sl_time_sell = TimeGMT();
         // DEAL_TYPE_SELL closes a BUY position (SL on BUY group)
         else if(dtype == DEAL_TYPE_SELL) g_last_sl_time_buy = TimeGMT();
      }
   }
}

string NormalizeOrderType(string ot) {
   string out = ot;
   StringTrimLeft(out);
   StringTrimRight(out);
   StringToUpper(out);
   if(out == "") return "AUTO";
   if(out == "BUY_STOPLIMIT") return "BUY_STOP_LIMIT";
   if(out == "SELL_STOPLIMIT") return "SELL_STOP_LIMIT";
   return out;
}

bool SymbolSupportsOrderType(const string order_type) {
   long mode = SymbolInfoInteger(_Symbol, SYMBOL_ORDER_MODE);
   string ot = NormalizeOrderType(order_type);
   if(ot == "BUY_LIMIT" || ot == "SELL_LIMIT")
      return (mode & SYMBOL_ORDER_LIMIT) == SYMBOL_ORDER_LIMIT;
   if(ot == "BUY_STOP" || ot == "SELL_STOP")
      return (mode & SYMBOL_ORDER_STOP) == SYMBOL_ORDER_STOP;
   if(ot == "BUY_STOP_LIMIT" || ot == "SELL_STOP_LIMIT")
      return (mode & SYMBOL_ORDER_STOP_LIMIT) == SYMBOL_ORDER_STOP_LIMIT;
   return true;
}

bool ParseEntryLegs(const string &json, const string &key, EntryLeg &legs[]) {
   ArrayResize(legs, 0);
   string search = "\"" + key + "\"";
   int kpos = StringFind(json, search);
   if(kpos < 0) return false;
   int p = kpos + StringLen(search);
   while(p < StringLen(json) && StringGetCharacter(json, p) <= 32) p++;
   if(p >= StringLen(json) || StringGetCharacter(json, p) != ':') return false;
   p++;
   while(p < StringLen(json) && StringGetCharacter(json, p) <= 32) p++;
   if(p >= StringLen(json) || StringGetCharacter(json, p) != '[') return false;
   p++;
   int idx = p;
   int depth = 0;
   int obj_start = -1;
   while(idx < StringLen(json)) {
      ushort c = StringGetCharacter(json, idx);
      if(c == '{') {
         if(depth == 0) obj_start = idx;
         depth++;
      } else if(c == '}') {
         depth--;
         if(depth == 0 && obj_start >= 0) {
            string obj = StringSubstr(json, obj_start, idx - obj_start + 1);
            int n = ArraySize(legs);
            ArrayResize(legs, n + 1);
            legs[n].order_type = NormalizeOrderType(JsonGetString(obj, "order_type"));
            if(legs[n].order_type == "") legs[n].order_type = "AUTO";
            legs[n].entry_price = JsonGetDouble(obj, "entry_price");
            legs[n].stoplimit_price = JsonGetDouble(obj, "stoplimit_price");
            legs[n].tp = JsonGetDouble(obj, "tp");
            if(legs[n].entry_price <= 0) {
               ArrayResize(legs, n);
            }
            obj_start = -1;
         }
      } else if(c == ']' && depth == 0) {
         break;
      }
      idx++;
   }
   return ArraySize(legs) > 0;
}

bool PlaceOpenGroupLeg(
   const string direction,
   const EntryLeg &leg,
   const double lot_per_trade,
   const double sl,
   const double tp_default,
   const int group_magic,
   const int group_id,
   const int leg_index,
   const int leg_count,
   bool &ok,
   string &order_kind,
   string &fail_reason
) {
   // RR floor context: at RR=1.5 the break-even win rate is 40%
   // (1 / (1 + 1.5) = 0.4). At RR=2.0 it drops to 33.3%.
   ok = false;
   fail_reason = "";
   // Read current RSI/ADX for SKIP log completeness — open_group_* gates previously logged 0,0
   // (PlaceOpenGroupLeg has no caller-side indicator params; local read avoids signature churn)
   double _pog_buf[1];
   double _log_rsi = (g_mtf[0].h_rsi != INVALID_HANDLE && CopyBuffer(g_mtf[0].h_rsi,0,0,1,_pog_buf)==1) ? _pog_buf[0] : 0;
   double _log_adx = (g_mtf[0].h_adx != INVALID_HANDLE && CopyBuffer(g_mtf[0].h_adx,0,0,1,_pog_buf)==1) ? _pog_buf[0] : 0;
   string tp_label = (leg_index < (int)MathCeil(leg_count * 0.7)) ? "TP1" : "TP2";
   string comment = "FORGE|G" + IntegerToString(group_id) + "|" + IntegerToString(leg_index) + "|" + tp_label;
   string req_type = NormalizeOrderType(leg.order_type);
   double entry = leg.entry_price;
   double entry_tolerance = MathMax(g_sc.pending_entry_threshold_points * _Point, _Point);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double lot_norm = NormalizeLot(lot_per_trade);
   double tp_for_this = tp_default;
   if(leg.tp > 0) tp_for_this = leg.tp;

   if(req_type == "AUTO") {
      if(direction == "BUY") {
         if(entry <= ask - entry_tolerance) req_type = "BUY_LIMIT";
         else if(entry >= ask + entry_tolerance) req_type = "BUY_STOP";
         else req_type = "BUY_MARKET";
      } else {
         if(entry >= bid + entry_tolerance) req_type = "SELL_LIMIT";
         else if(entry <= bid - entry_tolerance) req_type = "SELL_STOP";
         else req_type = "SELL_MARKET";
      }
   }

   if(direction == "BUY" && StringFind(req_type, "SELL_") == 0) {
      order_kind = req_type;
      fail_reason = "direction/order_type mismatch";
      JournalRecordSignal("SKIP","open_group_" + fail_reason,"OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
      return false;
   }
   if(direction == "SELL" && StringFind(req_type, "BUY_") == 0) {
      order_kind = req_type;
      fail_reason = "direction/order_type mismatch";
      JournalRecordSignal("SKIP","open_group_" + fail_reason,"OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
      return false;
   }
   if(req_type != "BUY_MARKET" && req_type != "SELL_MARKET" && !SymbolSupportsOrderType(req_type)) {
      order_kind = req_type;
      fail_reason = "symbol does not support order type";
      JournalRecordSignal("SKIP","open_group_unsupported_order_type","OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
      return false;
   }

   order_kind = req_type;

   double entry_for_stops = entry;
   if(req_type == "BUY_MARKET")  entry_for_stops = ask;
   else if(req_type == "SELL_MARKET") entry_for_stops = bid;

   double sl_for_this = sl;
   double base_entry = (direction == "BUY") ? ask : bid;
   bool is_market_req = (req_type == "BUY_MARKET" || req_type == "SELL_MARKET");

   // Pending ladder legs need the group SL/TP distances rebased onto each leg's actual entry.
   if(!is_market_req && leg.tp <= 0 && base_entry > 0.0 && entry_for_stops > 0.0) {
      if(direction == "BUY") {
         double sl_dist = base_entry - sl;
         double tp_dist = tp_for_this - base_entry;
         if(sl_dist > 0.0) sl_for_this = NormalizeDouble(entry_for_stops - sl_dist, _Digits);
         if(tp_dist > 0.0) tp_for_this = NormalizeDouble(entry_for_stops + tp_dist, _Digits);
      } else {
         double sl_dist = sl - base_entry;
         double tp_dist = base_entry - tp_for_this;
         if(sl_dist > 0.0) sl_for_this = NormalizeDouble(entry_for_stops + sl_dist, _Digits);
         if(tp_dist > 0.0) tp_for_this = NormalizeDouble(entry_for_stops - tp_dist, _Digits);
      }
   }

   double rr_risk = 0.0, rr_reward = 0.0;
   if(direction == "BUY") { rr_risk = entry_for_stops - sl_for_this; rr_reward = tp_for_this - entry_for_stops; }
   else                   { rr_risk = sl_for_this - entry_for_stops; rr_reward = entry_for_stops - tp_for_this; }
   double rr_floor = (g_sc.min_rr_floor > 0.0) ? g_sc.min_rr_floor : 1.5;
   double rr = (rr_risk > 0.0) ? (rr_reward / rr_risk) : 0.0;
   if(rr_risk <= 0.0 || rr_reward <= 0.0 || rr < rr_floor) {
      fail_reason = "RR below floor";
      PrintFormat("FORGE: skipped %s leg %d/%d entry=%.2f sl=%.2f tp=%.2f RR=%.2f floor=%.2f",
                  req_type, leg_index+1, leg_count, entry_for_stops, sl_for_this, tp_for_this, rr, rr_floor);
      JournalRecordSignal("SKIP","open_group_rr_below_floor","OPEN_GROUP",direction,entry_for_stops,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
      return false;
   }

   if(req_type == "BUY_MARKET") {
      if(!ValidateStops(ask, sl_for_this, tp_for_this, ORDER_TYPE_BUY)) {
         fail_reason = "invalid BUY market stops";
         JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,ask,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
         return false;
      }
      ok = g_trade.Buy(lot_norm, _Symbol, ask, NormalizeDouble(sl_for_this, _Digits), NormalizeDouble(tp_for_this, _Digits), comment);
      return true;
   }
   if(req_type == "SELL_MARKET") {
      if(!ValidateStops(bid, sl_for_this, tp_for_this, ORDER_TYPE_SELL)) {
         fail_reason = "invalid SELL market stops";
         JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,bid,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
         return false;
      }
      ok = g_trade.Sell(lot_norm, _Symbol, bid, NormalizeDouble(sl_for_this, _Digits), NormalizeDouble(tp_for_this, _Digits), comment);
      return true;
   }
   if(req_type == "BUY_LIMIT") {
      if(!ValidateStops(entry, sl_for_this, tp_for_this, ORDER_TYPE_BUY_LIMIT)) {
         fail_reason = "invalid BUY_LIMIT stops";
         JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
         return false;
      }
      ok = g_trade.BuyLimit(lot_norm, NormalizeDouble(entry, _Digits), _Symbol, NormalizeDouble(sl_for_this, _Digits), NormalizeDouble(tp_for_this, _Digits), ORDER_TIME_GTC, 0, comment);
      return true;
   }
   if(req_type == "SELL_LIMIT") {
      if(!ValidateStops(entry, sl_for_this, tp_for_this, ORDER_TYPE_SELL_LIMIT)) {
         fail_reason = "invalid SELL_LIMIT stops";
         JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
         return false;
      }
      ok = g_trade.SellLimit(lot_norm, NormalizeDouble(entry, _Digits), _Symbol, NormalizeDouble(sl_for_this, _Digits), NormalizeDouble(tp_for_this, _Digits), ORDER_TIME_GTC, 0, comment);
      return true;
   }
   if(req_type == "BUY_STOP") {
      if(!ValidateStops(entry, sl_for_this, tp_for_this, ORDER_TYPE_BUY_STOP)) {
         fail_reason = "invalid BUY_STOP stops";
         JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
         return false;
      }
      ok = g_trade.BuyStop(lot_norm, NormalizeDouble(entry, _Digits), _Symbol, NormalizeDouble(sl_for_this, _Digits), NormalizeDouble(tp_for_this, _Digits), ORDER_TIME_GTC, 0, comment);
      return true;
   }
   if(req_type == "SELL_STOP") {
      if(!ValidateStops(entry, sl_for_this, tp_for_this, ORDER_TYPE_SELL_STOP)) {
         fail_reason = "invalid SELL_STOP stops";
         JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
         return false;
      }
      ok = g_trade.SellStop(lot_norm, NormalizeDouble(entry, _Digits), _Symbol, NormalizeDouble(sl_for_this, _Digits), NormalizeDouble(tp_for_this, _Digits), ORDER_TIME_GTC, 0, comment);
      return true;
   }
   if(req_type == "BUY_STOP_LIMIT" || req_type == "SELL_STOP_LIMIT") {
      double slp = leg.stoplimit_price;
      if(slp <= 0) {
         fail_reason = "missing stoplimit_price";
         JournalRecordSignal("SKIP","open_group_missing_stoplimit","OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
         return false;
      }
      if(req_type == "BUY_STOP_LIMIT") {
         if(entry <= ask + entry_tolerance) {
            fail_reason = "BUY_STOP_LIMIT trigger must be above current ask";
            JournalRecordSignal("SKIP","open_group_bad_stoplimit_trigger","OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
            return false;
         }
         if(slp > entry) {
            fail_reason = "BUY_STOP_LIMIT stoplimit_price must be <= trigger";
            JournalRecordSignal("SKIP","open_group_bad_stoplimit_price","OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
            return false;
         }
      } else {
         if(entry >= bid - entry_tolerance) {
            fail_reason = "SELL_STOP_LIMIT trigger must be below current bid";
            JournalRecordSignal("SKIP","open_group_bad_stoplimit_trigger","OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
            return false;
         }
         if(slp < entry) {
            fail_reason = "SELL_STOP_LIMIT stoplimit_price must be >= trigger";
            JournalRecordSignal("SKIP","open_group_bad_stoplimit_price","OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
            return false;
         }
      }
      MqlTradeRequest req;
      MqlTradeResult  res;
      ZeroMemory(req);
      ZeroMemory(res);
      req.action = TRADE_ACTION_PENDING;
      req.symbol = _Symbol;
      req.magic = (ulong)group_magic;
      req.volume = lot_norm;
      req.type = (req_type == "BUY_STOP_LIMIT") ? ORDER_TYPE_BUY_STOP_LIMIT : ORDER_TYPE_SELL_STOP_LIMIT;
      req.price = NormalizeDouble(entry, _Digits);
      req.stoplimit = NormalizeDouble(slp, _Digits);
      if(!ValidateStops(entry, sl_for_this, tp_for_this, req.type)) {
         fail_reason = "invalid stop-limit stops";
         JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
         return false;
      }
      req.sl = NormalizeDouble(sl_for_this, _Digits);
      req.tp = NormalizeDouble(tp_for_this, _Digits);
      req.type_time = ORDER_TIME_GTC;
      req.deviation = 30;
      req.comment = comment;
      ok = OrderSend(req, res);
      if(!ok) {
         Print("FORGE: stop-limit send failed retcode=", (int)res.retcode, " type=", req_type,
               " trigger=", DoubleToString(entry, _Digits), " stoplimit=", DoubleToString(slp, _Digits));
      }
      return true;
   }
   fail_reason = "unsupported order_type";
   JournalRecordSignal("SKIP","open_group_unsupported_order_type","OPEN_GROUP",direction,entry,0,0,_log_rsi,_log_adx,0,0,0,0,0,0);
   return false;
}

// Deterministic leg count for native scalper (mirrors python/aegis.py where possible; no session P&L in MQL5).
int ForgeResolveNumTrades(const int base_n, const int env_lo, const int env_hi, const bool env_active,
                          const string setup_type, const double regime_conf, const string regime_label,
                          const double lot_mult_trend, string &out_reason) {
   out_reason = "";
   int lo = MathMax(1, MathMin(30, env_lo));
   int hi = MathMax(1, MathMin(30, env_hi));
   if(lo > hi) { int sw = lo; lo = hi; hi = sw; }

   if(!env_active) {
      int nb = MathMax(1, MathMin(30, base_n));
      out_reason = "forge_legacy_base n=" + IntegerToString(nb);
      return nb;
   }
   if(lo == hi) {
      out_reason = "forge_env_pin n=" + IntegerToString(lo);
      return lo;
   }

   int n = MathMax(lo, MathMin(hi, base_n));
   string parts = "";

   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double dd_pct_resolve = 0.0;
   if(bal > 0.0) {
      dd_pct_resolve = MathMax(0.0, (bal - eq) / bal * 100.0);
      if(dd_pct_resolve >= 2.0) { n--; parts += "eq_dd_ge2;"; }
      if(dd_pct_resolve >= 4.0) { n--; parts += "eq_dd_ge4;"; }
   }
   if(lot_mult_trend < 0.99) { n--; parts += "lot_mult_down;"; }
   else if(lot_mult_trend > 1.01) { n++; parts += "lot_mult_up;"; }

   string ru = regime_label;
   StringToUpper(ru);
   if(ru == "VOLATILE" && regime_conf >= 0.45) { n--; parts += "reg_volatile;"; }
   if(ru == "RANGE" && regime_conf >= 0.55) { n++; parts += "reg_range;"; }

   string su = setup_type;
   StringToUpper(su);
   if(StringFind(su, "BREAKOUT") >= 0) { n++; parts += "setup_breakout;"; }
   if(StringFind(su, "BOUNCE") >= 0) { n--; parts += "setup_bounce;"; }

   if(g_sc.recovery_leg_boost_enabled && bal > 0.0
      && dd_pct_resolve >= g_sc.recovery_leg_boost_dd_pct_min
      && g_sc.recovery_leg_boost_extra > 0) {
      n += g_sc.recovery_leg_boost_extra;
      parts += "recovery_boost;";
   }

   n = MathMax(lo, MathMin(hi, n));
   n = MathMax(1, MathMin(30, n));
   out_reason = "forge_resolve base=" + IntegerToString(base_n) + " n=" + IntegerToString(n)
      + " env=[" + IntegerToString(lo) + "," + IntegerToString(hi) + "] " + parts;
   return n;
}

bool JsonHasKey(const string &json, const string &key) {
   string search = "\"" + key + "\"";
   return StringFind(json, search) >= 0;
}
// Tolerant of Python json.dump(indent=2): space after colon, newlines inside arrays.
string JsonGetString(const string &json, const string &key) {
   string search = "\"" + key + "\"";
   int kpos = StringFind(json, search);
   if(kpos < 0) return "";
   int p = kpos + StringLen(search);
   while(p < StringLen(json) && StringGetCharacter(json, p) <= 32) p++;
   if(p >= StringLen(json) || StringGetCharacter(json, p) != ':') return "";
   p++;
   while(p < StringLen(json) && StringGetCharacter(json, p) <= 32) p++;
   if(p >= StringLen(json) || StringGetCharacter(json, p) != '"') return "";
   p++;
   int endq = StringFind(json, "\"", p);
   if(endq < 0) return "";
   return StringSubstr(json, p, endq - p);
}

double JsonGetDouble(const string &json, const string &key) {
   string search = "\"" + key + "\"";
   int kpos = StringFind(json, search);
   if(kpos < 0) return 0;
   int p = kpos + StringLen(search);
   while(p < StringLen(json) && StringGetCharacter(json, p) <= 32) p++;
   if(p >= StringLen(json) || StringGetCharacter(json, p) != ':') return 0;
   p++;
   while(p < StringLen(json) && StringGetCharacter(json, p) <= 32) p++;
   int end = p;
   while(end < StringLen(json)) {
      ushort c = StringGetCharacter(json, end);
      if(c == ',' || c == '}' || c == ']' || c == '\r' || c == '\n') break;
      end++;
   }
   return StringToDouble(StringSubstr(json, p, end - p));
}

void ParseDoubleArray(const string &json, const string &key, double &arr[]) {
   ArrayResize(arr, 0);
   string search = "\"" + key + "\"";
   int kpos = StringFind(json, search);
   if(kpos < 0) return;
   int p = kpos + StringLen(search);
   while(p < StringLen(json) && StringGetCharacter(json, p) <= 32) p++;
   if(p >= StringLen(json) || StringGetCharacter(json, p) != ':') return;
   p++;
   while(p < StringLen(json) && StringGetCharacter(json, p) <= 32) p++;
   if(p >= StringLen(json) || StringGetCharacter(json, p) != '[') return;
   p++;
   int close = StringFind(json, "]", p);
   if(close < 0) return;
   string body = StringSubstr(json, p, close - p);
   string parts[];
   int n = StringSplit(body, ',', parts);
   ArrayResize(arr, n);
   for(int i = 0; i < n; i++) {
      string s = parts[i];
      StringTrimLeft(s);
      StringTrimRight(s);
      arr[i] = StringToDouble(s);
   }
}
//+------------------------------------------------------------------+
