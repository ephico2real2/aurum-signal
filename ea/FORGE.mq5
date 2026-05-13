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
#property version "2.111"
#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Files\FileTxt.mqh>

const string FORGE_VERSION = "2.7.41";

// ─────────────────────────────────────────────────────────────────────────────
// PARITY INVARIANT (v2.7.30+) — Backtest-knob-transfer-to-live contract
//
// All logic that affects FORGE entry/sizing/SL/TP decisions MUST execute the
// SAME code path in MT5 Strategy Tester and in live trading. The operator's
// mandate (2026-05-11): "The sim is useless if testing results and config for
// logic evaluation cannot be applied to live trades."
//
// CONTRACT
//   1. Any new gate, classifier, or sizing rule MUST be implemented inline in
//      FORGE.mq5 (not in a Python sidecar that only runs in live), OR consumed
//      from a pre-computed file that is populated identically for tester and
//      live (see Issue 7 in docs/FORGE_RUN18_ANALYSIS.md — file-driven regime).
//   2. NO `if(in_tester) { ... }` guards around decision-making code. Tester-
//      only safeguards are allowed for warmup, indicator-handle fallbacks, and
//      diagnostic prints — never for logic that changes which trades fire.
//   3. Every FORGE_* env var must be wired the same way in both modes via
//      sync_scalper_config_from_env.py → scalper_config.json → JsonHasKey →
//      ScalperConfig struct. No mode-specific shortcuts.
//   4. The inline H1+H4 regime classifier at ~line 5693 is the authoritative
//      source for g_regime_label in both modes (v2.7.30 removed the prior
//      `if(in_tester)` wrapper). regime.py output (when BRIDGE running in
//      live) is overwritten by the inline classifier on every tick — it
//      survives only for SCRIBE/Athena observability.
//
// VALIDATION (visible at runtime)
//   OnInit logs the active mode and the values of every regime knob with
//   the prefix "FORGE PARITY:" — grep MT5 journal/tester log for that line
//   to confirm the same knobs are applied in tester and live runs.
//
// CHANGELOG
//   2026-05-11  v2.7.30  Established parity invariant. Inline classifier
//                        promoted to authoritative in both modes.
// ─────────────────────────────────────────────────────────────────────────────

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
input double  ScalperLotFactor = 1.0;        // Global lot multiplier on JSON lot_sizing.fixed_lot. 1.0=no override (full size). 0.5=half-sizing (risk-off). 2.0=double (size-up day). Renamed from absolute ScalperLot (v2.7.40) — old .set entries silently ignored, default 1.0 = safe no-op.
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
input bool    NativeScalperInputsOverrideLotSizing = false; // true = force ScalperTrades-driven leg count from Inputs; false = prefer scalper_config.json (min/max legs, resolver). 2.7.40: lot value always comes from JSON fixed_lot × ScalperLotFactor — this toggle only affects leg COUNT now.
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
// 2.7.41 — Track last TP1 win per direction. Used by regime-aware cooldown bypass:
//   when a setup is gated by a per-setup cooldown (BB_BREAKOUT same-dir, BB_PULLBACK_SCALP,
//   BULL_DAY_DIP_BUY reentry), bypass the cooldown if the last group in this direction
//   won TP1 recently AND regime + ADX confirm trend. Don't bypass after a loss.
datetime g_scalper_last_tp1_buy_time  = 0;
datetime g_scalper_last_tp1_sell_time = 0;
datetime g_last_sl_time_buy         = 0;  // last SL hit on a BUY group — for post-SL direction cooldown
datetime g_last_sl_time_sell        = 0;  // last SL hit on a SELL group
datetime g_scalper_last_entry_bar = 0;  // prevent multiple entries on same bar
string   g_scalper_last_direction = "";          // last entry direction for anti-whipsaw
datetime g_scalper_last_direction_time = 0;      // when last direction was entered
datetime g_scalper_last_reset_day = 0;  // UTC day marker for session counter reset
string   g_scalper_last_session_label = "";      // UTC session label used to reset first-entry anchors
// 2.7.36 — killzone tracking + log-throttle globals for previously-unthrottled gates
string   g_scalper_last_killzone_label = "";
datetime g_scalper_killzone_start_time = 0;
int      g_scalper_killzone_trades    = 0;
datetime g_scalper_last_dircool_log_bar    = 0;  // throttle direction_cooldown log
datetime g_scalper_last_opengroups_log_bar = 0;  // throttle open_groups log
datetime g_scalper_last_sesscap_log_bar    = 0;  // throttle session_trade_cap log
datetime g_scalper_last_nosetup_log_bar  = 0;   // throttle noisy "no setup" (once per M5 bar)
datetime g_scalper_last_rrtoolow_log_bar = 0;   // throttle journal rr_too_low (once per M5 bar)
datetime g_scalper_last_sesscut_log_bar  = 0;   // throttle entry_quality_session_sell_cutoff (2.7.7)
datetime g_scalper_last_macd_log_bar     = 0;   // throttle entry_quality_macd_* gates (2.7.7)
datetime g_scalper_last_h1disell_log_bar = 0;  // throttle entry_quality_h1_di_sell (2.7.12)
datetime g_scalper_last_h1macd_log_bar   = 0;  // throttle entry_quality_h1_macd_sell (2.7.12)
datetime g_scalper_last_h1macdbuy_log_bar = 0; // throttle entry_quality_h1_macd_buy (2.7.17)
datetime g_scalper_last_bocooldown_log_bar = 0; // throttle entry_quality_breakout_cooldown (2.7.17)
datetime g_scalper_last_bb_breakout_buy  = 0;  // wall time of last BB_BREAKOUT BUY entry (2.7.17 cooldown)
datetime g_scalper_last_bb_breakout_sell = 0;  // wall time of last BB_BREAKOUT SELL entry (2.7.17 cooldown)
// 2.7.19 — failed-breakout-pullback gate trackers (Run 15 G5013/G5015 fix)
// RSI peak is computed fresh from M5 RSI buffer at gate-check time (no rolling global needed)
datetime g_scalper_last_atrext_skip_bar_buy  = 0;   // M5 bar of last atr_ext SKIP for BUY
double   g_scalper_last_atrext_skip_price_buy = 0.0; // mid price at that SKIP
datetime g_scalper_last_brkfailed_log_bar     = 0;   // throttle entry_quality_breakout_failed (2.7.19)
datetime g_scalper_last_psar_log_bar          = 0;   // throttle entry_quality_psar_misalign_* (2.7.20)
datetime g_scalper_last_hbd_log_bar      = 0;  // throttle entry_quality_hid_bull_div_sell (2.7.13)
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
datetime g_scalper_last_dir_sell_log_bar  = 0;   // throttle entry_quality_direction SELL (2.7.14)
datetime g_scalper_last_dir_buy_log_bar   = 0;   // throttle entry_quality_direction BUY (2.7.14)
datetime g_scalper_last_body_sell_log_bar = 0;   // throttle entry_quality_body SELL (2.7.14)
datetime g_scalper_last_body_buy_log_bar  = 0;   // throttle entry_quality_body BUY (2.7.14)
datetime g_scalper_last_rsibuyceil_log_bar = 0;  // throttle entry_quality_rsi_buy_ceil (2.7.15)
bool     g_scalper_prev_session_blocked = true; // session-start log: true = previous tick was session_off

// 2.7.27 — Daily Direction Gate state (Filters 1+2+3) — Run 17 G5048 fix.
// Cached per M5 bar to avoid recomputing D1 indicators every tick.
datetime g_daily_bias_cache_bar     = 0;     // M5 bar time of last ComputeDailyBias() refresh
double   g_daily_slope_pts          = 0.0;   // D1_SMA(0) − D1_SMA(daily_sma_lookback_days)
double   g_daily_atr_pts            = 0.0;   // D1 ATR(14) at last refresh
double   g_daily_move_pts           = 0.0;   // D1 close(0) − D1 open(0) — intraday cumulative move
bool     g_daily_bear_bias          = false; // slope < −slope_block_atr × daily_atr  → block BUY
bool     g_daily_bull_bias          = false; // slope > +slope_block_atr × daily_atr  → block SELL
bool     g_daily_intraday_bear      = false; // intraday cumulative move < −move_block_atr × daily_atr
bool     g_daily_intraday_bull      = false; // intraday cumulative move > +move_block_atr × daily_atr
bool     g_daily_prev_intraday_bear = false; // hysteresis state for Filter 2 flip detection
bool     g_daily_prev_intraday_bull = false; // hysteresis state for Filter 2 flip detection
bool     g_daily_flip_now           = false; // one-tick flag set by ComputeDailyBias() when a flip is detected
// 2.7.27 codex-review fix #3 — single shared throttle was too restrictive (one log per
// M5 bar across all 4 paths). Split per-direction so BUY and SELL blocks both get journaled
// when both directions are blocked on the same bar. Per-setup granularity (breakout/bounce)
// is not separated — bar-level dedup is enough.
datetime g_scalper_last_dailybias_buy_log_bar  = 0; // throttle daily_bear_block_buy
datetime g_scalper_last_dailybias_sell_log_bar = 0; // throttle daily_bull_block_sell

// 2.7.28 — Momentum dump-catch state
datetime g_scalper_last_dump_sell_time = 0;   // wall time of last dump SELL entry — cooldown anchor
datetime g_scalper_last_dump_buy_time  = 0;   // wall time of last dump BUY entry  — cooldown anchor
datetime g_scalper_last_dump_log_bar   = 0;   // throttle dump SKIP logs (once per M5 bar)

// 2.7.37 — Layer-4 atom telemetry globals. Populated once per tick by
// ForgeEvalAtoms() at the top of CheckScalperEntry; consumed by
// JournalRecordSignal for every SKIP/TAKEN INSERT. See decision-stack
// inventory §6 + logging extension design for atom→column mapping.
double   g_eval_h4_trend         = 0.0;
double   g_eval_m15_trend        = 0.0;
double   g_eval_m30_trend        = 0.0;
double   g_eval_h1_di_plus       = 0.0;
double   g_eval_h1_di_minus      = 0.0;
double   g_eval_h1_di_balance    = 0.0;
double   g_eval_h4_rsi           = 0.0;
double   g_eval_h4_adx           = 0.0;
double   g_eval_d1_open          = 0.0;
double   g_eval_d1_close         = 0.0;
double   g_eval_day_open         = 0.0;
double   g_eval_day_high         = 0.0;
double   g_eval_day_low          = 0.0;
double   g_eval_m5_open_1        = 0.0;
double   g_eval_m5_high_1        = 0.0;
double   g_eval_m5_low_1         = 0.0;
double   g_eval_m5_close_1       = 0.0;
int      g_eval_m5_lh_cascade    = 0;
int      g_eval_m5_hl_cascade    = 0;
double   g_eval_m5_body_pct      = 0.0;
double   g_eval_h1_atr           = 0.0;
double   g_eval_h4_atr           = 0.0;
double   g_eval_m15_atr          = 0.0;
double   g_eval_m1_atr           = 0.0;
// 2.7.37 Group 3 — full per-TF indicator + OHLC + bar-quality inventory (45 cols)
double   g_eval_h1_rsi           = 0.0;
double   g_eval_h1_adx           = 0.0;
double   g_eval_h1_bb_u          = 0.0;
double   g_eval_h1_bb_m          = 0.0;
double   g_eval_h1_bb_l          = 0.0;
double   g_eval_h4_bb_u          = 0.0;
double   g_eval_h4_bb_m          = 0.0;
double   g_eval_h4_bb_l          = 0.0;
double   g_eval_m15_rsi          = 0.0;
double   g_eval_m15_ema20        = 0.0;
double   g_eval_m15_ema50        = 0.0;
double   g_eval_m30_rsi          = 0.0;
double   g_eval_m30_adx          = 0.0;
double   g_eval_m30_atr          = 0.0;
double   g_eval_m30_ema20        = 0.0;
double   g_eval_m30_ema50        = 0.0;
double   g_eval_m1_ema20         = 0.0;
double   g_eval_m1_ema50         = 0.0;
double   g_eval_m5_open_0        = 0.0;
double   g_eval_m5_high_0        = 0.0;
double   g_eval_m5_low_0         = 0.0;
double   g_eval_m5_close_0       = 0.0;
double   g_eval_m15_open         = 0.0;
double   g_eval_m15_high         = 0.0;
double   g_eval_m15_low          = 0.0;
double   g_eval_m15_close        = 0.0;
double   g_eval_m30_open         = 0.0;
double   g_eval_m30_high         = 0.0;
double   g_eval_m30_low          = 0.0;
double   g_eval_m30_close        = 0.0;
double   g_eval_h1_open          = 0.0;
double   g_eval_h1_high          = 0.0;
double   g_eval_h1_low           = 0.0;
double   g_eval_h1_close         = 0.0;
double   g_eval_h4_open          = 0.0;
double   g_eval_h4_high          = 0.0;
double   g_eval_h4_low           = 0.0;
double   g_eval_h4_close         = 0.0;
int      g_eval_m5_inside_bar    = 0;
int      g_eval_m5_outside_bar   = 0;
int      g_eval_m5_doji          = 0;
int      g_eval_m5_strong_bar    = 0;
int      g_eval_long_lower_wick  = 0;
int      g_eval_long_upper_wick  = 0;
int      g_eval_m5_range_expanding = 0;
datetime g_eval_last_tick        = 0;   // guard — avoid recomputing within same tick

// 2.7.31 — BB_PULLBACK_SCALP cooldown trackers (Run 19 Issue 4)
datetime g_pullback_scalp_last_sell_time = 0; // wall time of last pullback-scalp SELL entry
datetime g_pullback_scalp_last_buy_time  = 0; // wall time of last pullback-scalp BUY entry
// 2.7.42 — MA_CROSSOVER cooldown trackers (Phase 2 — EMA20×EMA50 event-triggered entry)
datetime g_ma_crossover_last_buy_time  = 0; // wall time of last MA_CROSSOVER BUY entry
datetime g_ma_crossover_last_sell_time = 0; // wall time of last MA_CROSSOVER SELL entry
// 2.7.42 — VWAP_REVERSION cooldown trackers (Phase 2 — pullback-to-VWAP in trend direction)
datetime g_vwap_reversion_last_buy_time  = 0; // wall time of last VWAP_REVERSION BUY entry
datetime g_vwap_reversion_last_sell_time = 0; // wall time of last VWAP_REVERSION SELL entry
// 2.7.42 — FIB_CONFLUENCE cooldown trackers (Phase 2 — fib level + EMA/VWAP overlap pullback)
datetime g_fib_confluence_last_buy_time  = 0; // wall time of last FIB_CONFLUENCE BUY entry
datetime g_fib_confluence_last_sell_time = 0; // wall time of last FIB_CONFLUENCE SELL entry
// 2.7.38 Tier 1 Boolean Composites — runtime state
datetime g_last_chop_buy_exit_time         = 0; // last BULL_DAY_DIP_BUY TP1 exit time (re-entry cooldown anchor)
datetime g_last_fractional_sell_in_bull_time = 0; // last FRACTIONAL_SELL_IN_BULL entry time
datetime g_last_intraday_reversal_log_bar  = 0; // throttle entry_quality_intraday_reversal_buy_block log
datetime g_last_chop_block_sell_log_bar    = 0; // throttle entry_quality_chop_block_sell log

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
   bool   breakout_block_hid_bull_sell;             // block SELL when RSI divergence = HID_BULL (reversal precursor; default false)
   double breakout_rsi_decl_sell_adx_threshold;     // rsi_rising_sell auto-off: gate inactive when ADX ≥ this (default 28; independent of two-tier RSI floor)
   // M30 intermediate-TF bearish confirmation (2.7.9 — Feature 3)
   // Requires M30 EMA20 < EMA50 when ADX ≥ adx_min; blocks recovery entries where H1 is stale
   bool   breakout_require_m30_bear_sell;           // require M30 EMA20 < EMA50 for SELL (default true)
   double breakout_m30_bear_adx_min;                // M30 gate only activates when m5_adx ≥ this (default 25)
   bool   breakout_require_h1_di_buy;               // block BUY when H1 DI- > DI+ at weak ADX (default false; DI+/DI- Wilder directional gate)
   double breakout_counter_buy_adx_threshold;       // h1_di_buy gate active only when m5_adx < this (default 28; auto-off in strong trend)
   bool   breakout_require_h1_di_sell;              // block SELL when H1 DI+ >= DI- (bullish H1 — no ADX bypass; catches false breakdowns)
   bool   breakout_require_h1_macd_sell;            // block SELL when H1 MACD histogram >= 0 (H1 bullish momentum; Run 12+ gate)
   bool   breakout_require_h1_macd_buy;             // block BUY when H1 MACD histogram < 0 (H1 momentum stalling; 2.7.17 Run 15 G5002 fix)
   int    breakout_same_dir_cooldown_seconds;       // block consecutive BB_BREAKOUT entries in same direction within N seconds (2.7.17 Run 15 G5002 fix)
   // 2.7.19 — Failed-breakout-pullback gate (Run 15 G5013 -$1086 / G5015 -$875 fix).
   // Blocks BB_BREAKOUT BUY when (a) an atr_ext SKIP fired within last N bars at a HIGHER price than entry,
   // AND (b) RSI peaked >= min_peak_rsi within last N bars, AND (c) current RSI dropped >= min_rsi_drop from that peak.
   bool   breakout_failed_gate_enabled;             // 0 = off (no behavior change)
   int    breakout_failed_lookback_bars;            // M5 bars back to look for atr_ext SKIP + RSI peak (default 4 = 20min)
   double breakout_failed_min_peak_rsi;             // require RSI peak >= this within lookback (default 75)
   double breakout_failed_min_rsi_drop;             // require current RSI <= (peak - this) (default 3.0)
   bool   breakout_failed_same_bar_hard_block;      // 2.7.20: when atr_ext SKIP fires in CURRENT M5 bar, hard-block BUY regardless of RSI (canonical wick-rejection guard from MQL5 Liquidity Sweep article). Catches G5018/G5022.
   // 2.7.20 — PSAR alignment gate (LiteFinance: "wait for first/second dot after flip").
   // Block BUY when psar_state != BELOW; block SELL when psar_state != ABOVE. Catches G5035 (FLIP_BEAR), G5036 (FLIP_BULL).
   bool   breakout_require_psar_align;
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
   double h1h4_crash_sell_min_m15_adx;       // M15 ADX must be >= this for crash bypass — prevents M5-spike false breakdowns (default 25)
   double breakout_min_h1_bear_strength;      // SELL blocked when |H1 trend| < this — filters barely-bearish H1 (default 0.2)
   double breakout_sell_inside_band_lot_factor; // lot multiplier when SELL entry is above BB lower (default 0.5)
   double breakout_max_reentry_atr_ext;  // 0 = disabled; >0 = max ATR multiples price can be from first entry for re-entry
   double breakout_sl_atr_mult;
   double breakout_buy_sl_atr_mult;   // BUY-only SL override (2.7.18, default 0 = use breakout_sl_atr_mult). Widens BUY SL to survive SL-hunt wicks (Run 15 G5015 lost -$875 with 2.0×ATR SL on a 2.49× ATR adverse wick that reversed cleanly).
   double breakout_tp1_atr_mult;      // fallback if direction-specific not set
   double breakout_tp1_buy_atr_mult;  // TP1 for BUY (0 = use breakout_tp1_atr_mult)
   double breakout_tp1_sell_atr_mult; // TP1 for SELL (0 = use breakout_tp1_atr_mult)
   double breakout_tp2_atr_mult;
   double breakout_tp3_atr_mult;
   double breakout_tp4_atr_mult;
   double breakout_tp1_close_pct;
   bool   breakout_require_m15;
   bool   breakout_move_be;
   double breakout_be_cushion_atr_mult;  // 2.7.23: when >0, BE-trail moves SL to entry∓mult×ATR (cushion below/above entry) instead of tight entry±spread+5pts buffer. Run 17 G5002 ATR=7.59 clipped at BE+0.35 then market ran +18pts — wider cushion captures continuation. 0=legacy tight buffer.
   bool   breakout_tp2_sl_ratchet_enabled;  // 2.7.24: Milestone 2 — when TP2 reached, ratchet SL to TP1 level (locks +TP1-distance profit). SL invariant preserved (only ratchets into profit). Per FORGE_RATCHET_LOGIC_IDEAS.md spec section 5/6.
   bool   breakout_atr_trail_enabled;       // 2.7.25: ATR trail per spec — after TP1, track group peak/trough and trail SL at peak ∓ trail_mult×ATR. Runs every tick alongside discrete milestones; SL invariant preserved.
   double breakout_atr_trail_mult;          // 2.7.25: ATR multiplier for trail SL. Default 1.5 per spec.
   // 2.7.27 — Daily Direction Gate (Filters 1+2+3) — Run 17 G5048 fix.
   // Filter 1: block BUY when D1 SMA slope is negative beyond threshold (multi-day rollover).
   // Filter 2: track intraday cumulative move from D1 open and flag bull↔bear flips with hysteresis.
   // Filter 3: when a flip fires, cancel pending stops/limits for our magic range so they don't fill
   //   into the new regime (canonical OrdersTotal()-1→0 iterate-down per MQL5 forum 377826).
   bool   daily_direction_gate_enabled;     // 2.7.27: master toggle for Filters 1+2+3. Default false until backtested.
   int    daily_sma_period;                 // 2.7.27: D1 SMA period for slope bias (default 20).
   int    daily_sma_lookback_days;          // 2.7.27: bars back for slope: slope = D1_sma(0) - D1_sma(N) (default 3).
   double daily_slope_block_atr;            // 2.7.27: slope threshold as multiple of D1 ATR(14). Block BUY when slope < -threshold; block SELL when slope > +threshold (default 0.5).
   double daily_move_block_atr;             // 2.7.27: intraday cumulative-move threshold as multiple of D1 ATR. Bear flag set when D1_close_now − D1_open < -threshold (default 0.5).
   double daily_move_flip_hysteresis;       // 2.7.27: extra D1-ATR fraction required to cross before declaring flip (default 0.3) — prevents oscillation at the threshold.
   bool   daily_cancel_pending_on_flip;     // 2.7.27: when flip detected, cancel pending orders (default true).
   bool   daily_cancel_includes_cascade;    // 2.7.27: also cancel cascade SELL_STOP_CONT / BUY_LIMIT_RECOV pending orders (default true).
   // 2.7.27 — Extended TP4/TP5 staging for BB_BREAKOUT runners (only in TRENDING regime).
   // After TP3 reached, ratchet SL to TP2 and promote TP target to TP4 (4.0×ATR).
   // After TP4 reached, ratchet SL to TP3 and promote TP target to TP5 (5.5×ATR).
   // Captures the extended dump/rip moves that Run 17 cut off at TP3 — Apr 15 G5040 (+$218) had 53 pts of additional move after TP3 exit.
   bool   breakout_tp4_staging_enabled;     // 2.7.27: enable TP3→TP4 staging (default false).
   double breakout_tp5_atr_mult;            // 2.7.27: TP5 ATR multiplier (default 5.5).
   int    breakout_tp4_min_adx;             // 2.7.27: minimum M5 ADX to stage to TP4 (default 25). Below this, runner exits at TP3.
   bool   breakout_tp5_staging_enabled;     // 2.7.27: enable TP4→TP5 staging (default false).
   int    breakout_tp5_min_adx;             // 2.7.27: minimum M5 ADX to stage to TP5 (default 30, stricter than TP4).
   // 2.7.28 — Momentum dump-catch market entry (non-BB setup).
   // Fires when M5 shows a fast directional impulse that BB_BREAKOUT/BB_BOUNCE conditions miss.
   // Single-shot scalp — no cascade arming, smaller lot than BB setups.
   // Run 17 evidence: Apr 22-29 lost ~208 pts in straight bear, FORGE caught only 6 BB_BREAKOUT SELLs
   // because most dump bars never re-broke the BB lower band after the initial break.
   bool   dump_catch_enabled;               // 2.7.28: master toggle. Default false until backtested.
   int    dump_lookback_bars;               // 2.7.28: M5 bars to measure impulse (default 3 = 15min window).
   double dump_atr_mult;                    // 2.7.28: move threshold = atr_mult × M5_ATR. Default 1.5.
   double dump_max_rsi;                     // 2.7.28: SELL only when M5 RSI < this (BUY: > 100−this). Default 50.
   double dump_max_rsi_buy;                 // 2.7.34: block MOMENTUM_DUMP BUY when M5 RSI ≥ this — overbought exhaustion (default 70).
                                            // Mirror of SELL-side dump_max_rsi but as an absolute ceiling on the BUY side.
                                            // Run 20 G5009 (RSI=72.2 BUY in TREND_BULL) lost −$305 in 16-leg cascade — this gate blocks that pattern.
   double dump_min_adx;                     // 2.7.28: M5 ADX must exceed this for sustained move (default 25).
   bool   dump_require_psar;                // 2.7.28: require PSAR alignment (ABOVE for SELL, BELOW for BUY). Default true.
   bool   dump_require_d1_bias;             // 2.7.28: require v2.7.27 Filter 1 daily bias to agree. Default true.
   int    dump_cooldown_seconds;            // 2.7.28: minimum gap between consecutive dump entries per direction (default 600 = 10min).
   double dump_lot_factor;                  // 2.7.28: lot multiplier vs fixed_lot — smaller than BB (default 0.7).
   // 2.7.35 — Direction-specific dump lot factors. If non-zero, override dump_lot_factor per direction.
   // Rationale: in bullish regimes, BUY MOMENTUM_DUMP should size up (with-trend), SELL should probe small.
   double dump_buy_lot_factor;              // 2.7.35: applied to BUY MOMENTUM_DUMP. 0 = use dump_lot_factor (default 0).
   double dump_sell_lot_factor;             // 2.7.35: applied to SELL MOMENTUM_DUMP. 0 = use dump_lot_factor (default 0).
   // 2.7.35 — h1_trend ceiling for MOMENTUM_DUMP SELL. Block SELL when h1_trend ≥ this (counter-trend in strong bull).
   // Run 23 G5004 (h1=2.06 -$19), G5008 (h1=2.27 -$47) — both lost selling into strong bull rallies.
   double dump_sell_h1_max;                 // 2.7.35: SELL blocked when h1_trend ≥ this (default 0 = disabled).
   // 2.7.32 — Option B (default OFF, documented for validation): direction-confirmation gate.
   //   Run 20 Mar 31 had 16 of 24 BUY losses as IMMEDIATE-SL (avg 30min, 1.52×ATR — exact SL setting,
   //   no TPs offset). These are direction failures, not SL-too-tight. Widening SL (Option A 3.0→4.0×ATR)
   //   gives more time but bigger per-failure loss. Confirmation gate fires only when prior closed bar
   //   ALSO moved in trade direction (close[1] < close[2] for SELL, close[1] > close[2] for BUY).
   //   Filters single-wick triggers in chop without rejecting genuine momentum impulses.
   //   Default OFF — needs separate validation pass before enabling.
   bool   dump_require_bar_confirm;         // 2.7.32 default false.
   // 2.7.29 — Regime classifier H1-strong override (Run 18 Issue 1 fix).
   // The inline regime classifier (FORGE.mq5:5658-5661) requires unanimous H1+H4 agreement for TREND_*.
   // H4 EMA20-EMA50 lags H1 by 3-5 hours after a regime turn, so perfect M5/H1 setups get
   // capped at 5 legs (native_legs_max_when_unclear) because regime stays RANGE.
   // Run 18 G5001 Apr 1 08:40: h1_trend=+2.15, ADX=40, but regime=RANGE → only 5 legs fired
   //   despite the market then moving +41pts (8×ATR) in 2 hours.
   // Override: when M5+H1 signal "unambiguously trending" (h1_trend >> threshold AND m5_adx high),
   //   force TREND_BULL/TREND_BEAR regardless of H4. Default OFF via factor=0.
   double regime_h1_override_factor;        // 2.7.29: multiplier on trend_thr_eff for the override.
                                            // 0 = disabled (legacy). 2.0 = h1_trend must be 2× the threshold to override.
                                            // Apr 1 G5001 sim: thr≈0.5, h1_trend=2.15 → 2.15/0.5=4.3× → triggers at 2.0×.
   double regime_h1_override_adx_min;       // 2.7.29: minimum M5 ADX to confirm strong trend (default 30).
                                            //         Both conditions must be true (factor + adx_min) for override to fire.
   // 2.7.31 — BB_PULLBACK_SCALP additive setup (Run 19 Issue 4, Task #53).
   //   Catches BB_BOUNCE entries that v2.7.26 PSAR-misalign would block, but ONLY when the PSAR
   //   flip is fresh (≤ pullback_scalp_fresh_flip_bars). This isolates "pullback bottom" entries
   //   (PSAR just flipped against trade direction = bounce zone) from "sustained reversal" entries
   //   (PSAR on wrong side for many bars = real downtrend that G5028 represented).
   //   Tight asymmetric geometry: SL=1.0×ATR, TP1=0.3×ATR scalp, TP2=0.7×ATR, 0.5× lot.
   //   Default OFF via pullback_scalp_enabled=false.
   bool   pullback_scalp_enabled;           // 2.7.31: master toggle for BB_PULLBACK_SCALP fork.
   int    pullback_scalp_fresh_flip_bars;   // 2.7.31: max bars since last PSAR flip to qualify as fresh (default 3).
   double pullback_scalp_lot_factor;        // 2.7.31: lot multiplier vs fixed_lot (default 0.5).
   double pullback_scalp_sl_atr_mult;       // 2.7.31: SL distance in ATR units (default 1.0 — tight).
   double pullback_scalp_tp1_atr_mult;      // 2.7.31: TP1 in ATR (default 0.3 — fast scalp).
   double pullback_scalp_tp2_atr_mult;      // 2.7.31: TP2 in ATR (default 0.7).
   int    pullback_scalp_cooldown_seconds;  // 2.7.31: min gap between pullback-scalps per direction (default 600 = 10min).
   double pullback_scalp_max_adx;           // 2.7.31: M5 ADX must be BELOW this (default 30) — pullback is exhausting, not accelerating.
   // 2.7.42 — MA_CROSSOVER setup (Phase 2). EMA20 × EMA50 event-triggered entry on M5 close.
   // Config lives under setup.* / atom.* / geometry.* / timing.* per FORGE_NAMING_CONVENTIONS §4.
   bool   ma_crossover_enabled;             // master toggle (default off — operator opts in via env)
   double ma_crossover_adx_min;             // M5 ADX floor for entry (default 20)
   double ma_crossover_lot_factor;          // lot multiplier vs fixed_lot (default 0.5 — crossovers lag)
   double ma_crossover_sl_atr_mult;         // SL = ATR × this (default 1.5)
   double ma_crossover_tp1_atr_mult;        // TP1 = ATR × this (default 0.5)
   double ma_crossover_tp2_atr_mult;        // TP2 = ATR × this (default 1.5)
   int    ma_crossover_cooldown_seconds;    // min gap per direction (default 600 = 10min)
   // 2.7.42 — VWAP_REVERSION setup (Phase 2). Pullback-to-VWAP in established H1 trend.
   // Detects: prior N M5 bars closed beyond min_deviation × ATR from VWAP, current bar
   //   retraces to within tolerance, H1 trend agrees with extension direction. BUY when
   //   H1 bullish + extension was ABOVE VWAP; SELL when H1 bearish + extension BELOW.
   bool   vwap_reversion_enabled;             // master toggle (default off)
   double vwap_reversion_min_deviation_atr;   // min |close − vwap| / ATR to count bar as extended (default 1.0)
   double vwap_reversion_max_deviation_atr;   // max extension before pattern is invalidated (default 3.0)
   int    vwap_reversion_min_extension_bars;  // min bars in lookback that must be extended (default 5)
   double vwap_reversion_lot_factor;          // lot multiplier (default 0.5)
   double vwap_reversion_sl_atr_mult;         // SL = ATR × this (default 1.2 — tight, rejection resolves fast)
   double vwap_reversion_tp1_atr_mult;        // TP1 = ATR × this (default 0.4)
   double vwap_reversion_tp2_atr_mult;        // TP2 = ATR × this (default 1.0 — target = original extension zone)
   int    vwap_reversion_cooldown_seconds;    // min gap per direction (default 600)
   // 2.7.42 — FIB_CONFLUENCE setup (Phase 2). Trend-direction retrace to fib
   //   38.2/50/61.8 of recent swing, coinciding with ≥1 reference (EMA20, EMA50,
   //   VWAP) within tolerance × ATR. Uses g_fib_382/50/618 already computed.
   bool   fib_confluence_enabled;             // master toggle (default off)
   int    fib_confluence_min_confluences;     // min overlapping refs (default 1; max 3 = EMA20+EMA50+VWAP all align)
   double fib_confluence_tolerance_atr;       // proximity threshold for fib + reference overlap (default 0.3 × ATR)
   double fib_confluence_min_swing_atr;       // min (fib_high − fib_low) / ATR to qualify (default 2.0 — avoid micro-swings)
   double fib_confluence_lot_factor;          // lot multiplier (default 0.5)
   double fib_confluence_sl_atr_mult;         // SL = ATR × this (default 1.5)
   double fib_confluence_tp1_atr_mult;        // TP1 = ATR × this (default 0.5)
   double fib_confluence_tp2_atr_mult;        // TP2 = ATR × this (default 1.3 — back toward swing extreme)
   int    fib_confluence_cooldown_seconds;    // min gap per direction (default 600)
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
   double sell_stop_cont_sl_atr_mult;  // SELL STOP SL: cascade_entry + ATR × this (2.7.16, default 1.5; 0 = fall back to legacy 'tp1+atr_mult' geometry)
   double sell_stop_cont_lot_factor;   // lot factor per continuation leg — 1.0 = full lot, same as primary (default 1.0)
   double sell_stop_cont_tp_atr_mult;  // TP: cascade_entry - ATR×mult (default 1.5 = ~9pts @ ATR=6)
   int    sell_stop_cont_expiry_bars;  // cancel if not triggered within N M5 bars (default 2 = 10 min)
   double sell_stop_cont_min_rsi;      // only arm when M5 RSI > this — blocks exhausted entries (default 25.0)
   double sell_stop_cont_min_adx;     // only arm when M5 ADX >= this — trend must be confirmed (default 25.0)
   bool   sell_stop_cont_require_h1_di; // only arm when H1 DI- > DI+ — H1 must be bearish (default true)
   bool   sell_stop_cont_require_trend_regime; // 2.7.21: only arm when regime != "RANGE" (cascade SL-hunt protection — Run 15 G5040 lost -$1119 cascade in RANGE regime)
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
   // 2.7.41 — Regime-aware cooldown bypass. When a setup is throttled by a per-setup cooldown
   //   (BB_BREAKOUT same-dir, BB_PULLBACK_SCALP, BULL_DAY_DIP_BUY reentry), allow the entry
   //   anyway if: (1) last TP1 win in this direction was within `cooldown_bypass_window_sec`,
   //   (2) direction matches g_regime_label, (3) M5 ADX >= cooldown_bypass_min_adx,
   //   (4) min refire-floor passed (anti-flicker). This stops cooldowns from killing
   //   second-leg continuations on strong trend days (Apr 1 NY rally, Apr 2 crash).
   bool   cooldown_bypass_on_tp_with_trend;
   int    cooldown_bypass_window_sec;     // how recently the last TP1 must have hit
   double cooldown_bypass_min_adx;        // M5 ADX floor for bypass
   int    cooldown_bypass_min_refire_sec; // anti-flicker — min gap between same-direction fires
   string cooldown_bypass_setups;         // comma-list — these setups bypass UNCONDITIONALLY
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
   // Session — minute precision (2.7.36; additive; integer minute-of-day 0..1440; -1 = use legacy hour field)
   int    london_start_min;
   int    london_end_min;
   int    ny_start_min;
   int    ny_end_min;
   int    asia_start_min;
   int    asia_end_min;
   // Session — NY-time anchoring (DST-aware via manual broker offset, Approach B)
   bool   sessions_ny_anchored;
   // Broker GMT offsets (manual; works identically in live + Strategy Tester)
   int    broker_gmt_offset_winter;
   int    broker_gmt_offset_summer;
   // ICT Killzones (NY-time minute-of-day; killzones are always NY-anchored)
   bool   killzones_enabled;
   bool   killzones_gate_entries;
   int    kz_asia_start_min;
   int    kz_asia_end_min;
   int    kz_london_open_start_min;
   int    kz_london_open_end_min;
   int    kz_ny_open_start_min;
   int    kz_ny_open_end_min;
   int    kz_london_close_start_min;
   int    kz_london_close_end_min;
   // 2.7.38 Tier 1 Boolean Composites (all default-OFF)
   bool   block_sell_in_chop_enabled;
   bool   intraday_reversal_sell_enabled;
   double intraday_reversal_sell_lot_mult;
   bool   fractional_sell_in_bull_enabled;
   double fractional_sell_in_bull_lot_factor;
   double fractional_sell_in_bull_sl_atr_mult;
   double fractional_sell_in_bull_tp1_atr_mult;
   bool   bull_day_dip_buy_enabled;
   double bull_day_dip_buy_lot_mult;
   double bull_day_dip_buy_sl_atr_mult;
   double bull_day_dip_buy_tp1_atr_mult;
   int    bull_day_dip_buy_reentry_cooldown_sec;
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
   // 2.7.41 — Comma-separated setup_type list that BYPASSES max_open_same_direction. Risk-1
   //   setups (BB_BREAKOUT_RETEST, BUY_LIMIT_RECOVERY) can stack beyond the cap so their
   //   high-confidence signals are not throttled by a low default. Setups outside this list
   //   continue to respect max_open_same_direction.
   string max_open_same_direction_bypass_setups;
   int    entry_quality_bars;      // look-back bars for body/direction checks (default 3)
   double min_body_ratio;          // min avg body/candle ratio — filters doji/wick bars (default 0.40)
   int    min_directional_bars;    // min bars agreeing with trade direction out of entry_quality_bars (default 2)
   bool   require_bb_expansion;    // reject entries when BB width is contracting (default true)
   string lot_sizing_source;
   bool   lot_inputs_override;
   // Lot sizing precedence: config/scalper_config.json lot_sizing by default,
   // optionally overridden by MT5 Inputs when NativeScalperInputsOverrideLotSizing=true.
   double lot_fixed;
   // 2.7.40 — Env-side mirror of MT5 input ScalperLotFactor (FORGE_GLOBAL_SCALPER_LOT_FACTOR).
   // Sits at top of combined_lot_factor chain as a global scaler. 1.0 = no-op.
   // MT5 input wins when non-default; env value wins when MT5 input stays at 1.0.
   double scalper_lot_factor;
   int    lot_num_trades;
   int    lot_min_trades;
   int    lot_max_trades;
   // Staged native entries: open a probe first, add legs after time + favorable excursion.
   bool   staged_entry_enabled;
   int    staged_initial_legs;
   int    staged_add_interval_sec;
   double staged_add_min_favorable_points;
   // 2.7.34 — Wave-confirmation lot amplifier. Multiplies lot size on staged-add legs (legs 2+) after
   // the staged_add_min_favorable_points threshold has confirmed direction.
   // Leg 1 = base lot (test the waters); Legs 2+ = base × wave_confirmation_lot_mult (direction proven).
   // Default 1.0 = no amplification. Set 2.0 to double exposure on confirmed wave-ride legs.
   double wave_confirmation_lot_mult;
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
   double tp4;       // 2.7.27: TP4 price for runner staging (only set when breakout_tp4_staging_enabled)
   double tp5;       // 2.7.27: TP5 price for runner staging (only set when breakout_tp5_staging_enabled)
   double tp1_close_pct;
   bool   tp1_hit;
   bool   tp2_hit;   // set when all TP2 runners are modified to target TP3
   bool   tp3_hit;   // 2.7.27: set when all TP3 runners are modified to target TP4 (SL ratcheted to TP2)
   bool   tp4_hit;   // 2.7.27: set when all TP4 runners are modified to target TP5 (SL ratcheted to TP3)
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
   // 2.7.25 — ATR trail peak/trough tracking (FORGE_RATCHET_LOGIC_IDEAS.md section 5/6)
   double peak_price;     // highest bid seen since entry (BUY) — drives ATR trail SL
   double trough_price;   // lowest ask seen since entry (SELL) — drives ATR trail SL
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
   // 2.7.36 — InitScalperConfig must run BEFORE WriteBrokerInfo, because the new
   // broker_gmt_offset_{winter,summer} + is_eu_dst/is_us_dst fields in
   // WriteBrokerInfo read g_sc.broker_gmt_offset_*. Original pre-2.7.36 order
   // had WriteBrokerInfo first, but it only used Account*/Terminal* APIs then.
   InitScalperConfig();
   WriteBrokerInfo();
   // 2.7.36 — Time diagnostic (verify Approach B broker offsets work in live + tester)
   PrintFormat("FORGE TIME CHECK: TimeCurrent=%s TimeGMT=%s TimeTradeServer=%s",
               TimeToString(TimeCurrent(),    TIME_DATE|TIME_SECONDS),
               TimeToString(TimeGMT(),        TIME_DATE|TIME_SECONDS),
               TimeToString(TimeTradeServer(),TIME_DATE|TIME_SECONDS));
   PrintFormat("FORGE TIME CHECK: BrokerToNY=%s (EU_DST=%d offset=%dh)",
               TimeToString(BrokerToNY(TimeCurrent()), TIME_DATE|TIME_SECONDS),
               IsEU_DST(TimeCurrent()) ? 1 : 0,
               IsEU_DST(TimeCurrent()) ? g_sc.broker_gmt_offset_summer : g_sc.broker_gmt_offset_winter);
   JournalInit();
   // Same live sync as OnTimer: BRIDGE config.json + analytics once at attach (not after 1s / 20 cycles).
   ReadConfig();

   // PARITY-INVARIANT AUDIT — prints the regime classifier configuration so
   // an operator (or grep) can verify tester and live runs use identical knobs.
   // Runs AFTER ReadConfig() so g_sc fields reflect env-overridden values.
   // See top-of-file PARITY INVARIANT contract.
   {
      const bool in_tester = (MQLInfoInteger(MQL_TESTER) != 0);
      PrintFormat("FORGE PARITY: mode=%s | regime_source=inline_classifier (FORGE.mq5:~5693) | "
                  "trend_strength_atr_threshold=%.4f | regime_h1_override_factor=%.4f | regime_h1_override_adx_min=%.1f",
                  in_tester ? "TESTER" : "LIVE",
                  g_sc.trend_strength_atr_threshold,
                  g_sc.regime_h1_override_factor,
                  g_sc.regime_h1_override_adx_min);
      PrintFormat("FORGE PARITY: regime knobs apply identically in tester and live — backtest tuning of "
                  "FORGE_REGIME_H1_OVERRIDE_FACTOR / FORGE_REGIME_H1_OVERRIDE_ADX_MIN transfers as-is. "
                  "JSON regime_label from BRIDGE (live only) is advisory — overwritten each tick.");
   }
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
   g_groups[gi].tp4           = 0;   // 2.7.27: BRIDGE path does not stage TP4
   g_groups[gi].tp5           = 0;   // 2.7.27: BRIDGE path does not stage TP5
   g_groups[gi].tp1_close_pct = tp1_close_pct;
   g_groups[gi].tp1_hit       = false;
   g_groups[gi].tp2_hit       = false;
   g_groups[gi].tp3_hit       = false;  // 2.7.27
   g_groups[gi].tp4_hit       = false;  // 2.7.27
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
   // 2.7.25 — ATR trail peak/trough init (per FORGE_RATCHET_LOGIC_IDEAS.md)
   g_groups[gi].peak_price   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   g_groups[gi].trough_price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
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
      // 2.7.34 — Wave-confirmation amplifier. After staged_add_min_favorable_points has been satisfied
      // (direction proven via favorable price move), amplify this leg's lot by wave_confirmation_lot_mult.
      // Default 1.0 = no amplification. 2.0 = double exposure on confirmed wave-ride legs.
      // Run 20 Apr 8-style $144 day-range supports wave-riding; this amplifies banking on confirmed waves.
      if(g_sc.wave_confirmation_lot_mult > 1.0) {
         lotv = NormalizeLot(MathMax(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN),
                                     lotv * g_sc.wave_confirmation_lot_mult));
      }
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
      // 2.7.41 — track last TP1 win per direction for regime-aware cooldown bypass
      if(dir == "BUY")  g_scalper_last_tp1_buy_time  = TimeCurrent();
      if(dir == "SELL") g_scalper_last_tp1_sell_time = TimeCurrent();
      ArmPostTP1Ladder(gi);  // 2.7.10 Day 2: arm SELL STOP continuation (off by default: sell_stop_cont_enabled=false)
      Print("FORGE: Group ", g_groups[gi].id, " TP1 — closed ", closed, "/", total);

      if(g_groups[gi].move_be_on_tp1) {
         GetGroupPositions(gm, positions);  // refresh after closes
         double remaining_tp = (g_groups[gi].tp2 > 0) ? g_groups[gi].tp2 : tp1;
         // 2.7.23 — ATR-aware BE-trail cushion (Run 17 G5002 fix).
         // Legacy (cushion=0): SL → entry + spread+5pts (BUY) / entry - spread-5pts (SELL).
         //   Result: tight lock that clips runners in volatile markets (G5002 ATR=7.59, clipped at +0.4pt
         //   wick while market then ran +18pts to TP3).
         // Cushion>0: SL → entry - cushion×ATR (BUY) / entry + cushion×ATR (SELL).
         //   Gives breathing room proportional to volatility. Loses guaranteed "lock 0 pts" but captures
         //   runners. Cushion 0.3-0.5 typical for breakout.
         double cushion_mult = g_sc.breakout_be_cushion_atr_mult;
         double grp_atr      = g_groups[gi].entry_atr;
         bool   use_cushion  = (cushion_mult > 0.0 && grp_atr > 0.0);
         for(int j = 0; j < ArraySize(positions); j++) {
            if(g_pos.SelectByTicket(positions[j])) {
               double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
               double spread = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
               double legacy_buffer = spread + (5.0 * point);
               double entry_px = g_pos.PriceOpen();
               double be;
               if(use_cushion) {
                  // ATR cushion: SL below entry for BUY, above for SELL (gives breathing room)
                  if(g_pos.PositionType() == POSITION_TYPE_BUY) be = entry_px - cushion_mult * grp_atr;
                  else                                          be = entry_px + cushion_mult * grp_atr;
               } else {
                  // Legacy tight BE+ buffer
                  if(g_pos.PositionType() == POSITION_TYPE_BUY) be = entry_px + legacy_buffer;
                  else                                          be = entry_px - legacy_buffer;
               }
               // Move SL to breakeven (or cushion) + set TP to TP2 for remaining runners
               g_trade.PositionModify(positions[j], NormalizeDouble(be, _Digits), NormalizeDouble(remaining_tp, _Digits));
            }
         }
         g_groups[gi].be_moved = true;
         Print("FORGE: Group ", g_groups[gi].id, " remaining ", ArraySize(positions),
               " trades: SL→", (use_cushion ? "cushion" : "BE+"), " (mult=",
               DoubleToString(cushion_mult, 2), " atr=", DoubleToString(grp_atr, 2), ") TP→",
               DoubleToString(remaining_tp, 2));
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

      // 2.7.24 — Milestone 2 SL ratchet (FORGE_RATCHET_LOGIC_IDEAS.md): when TP2 reached, ratchet SL up
      // to TP1 level (locks +TP1-distance of profit on remaining runners). SL invariant: BUY only raises
      // SL, SELL only lowers. Falls back to legacy behavior (SL unchanged) when ratchet disabled.
      double tp1_price_m2 = g_groups[gi2].tp1;
      bool   use_m2_ratchet = (g_sc.breakout_tp2_sl_ratchet_enabled && tp1_price_m2 > 0.0);
      // Promote runners to TP3 (and optionally ratchet SL to TP1)
      int pos3[];
      GetGroupPositions(gm2, pos3);
      int promoted = 0;
      int sl_ratcheted = 0;
      for(int j = 0; j < ArraySize(pos3); j++) {
         if(g_pos.SelectByTicket(pos3[j])) {
            double cur_sl = g_pos.StopLoss();
            double new_sl = cur_sl;
            if(use_m2_ratchet) {
               // SL invariant: BUY raises only, SELL lowers only
               if(dir2 == "BUY"  && tp1_price_m2 > cur_sl) new_sl = tp1_price_m2;
               else if(dir2 == "SELL" && tp1_price_m2 < cur_sl) new_sl = tp1_price_m2;
            }
            if(g_trade.PositionModify(pos3[j], NormalizeDouble(new_sl, _Digits), NormalizeDouble(tp3_price, _Digits))) {
               promoted++;
               if(new_sl != cur_sl) sl_ratcheted++;
            }
         }
      }
      g_groups[gi2].tp2_hit = true;
      if(promoted > 0) {
         if(use_m2_ratchet)
            PrintFormat("FORGE: Group %d TP2 reached — promoted %d runner(s) to TP3=%.2f, SL ratcheted to TP1=%.2f on %d leg(s)",
                        g_groups[gi2].id, promoted, tp3_price, tp1_price_m2, sl_ratcheted);
         else
            PrintFormat("FORGE: Group %d TP2 reached — promoted %d runner(s) to TP3=%.2f",
                        g_groups[gi2].id, promoted, tp3_price);
      }
   }

   // ── 2.7.27 — TP3 → TP4 staging pass ──────────────────────────────────────────
   // After TP2 runners reach TP3, promote remaining positions to target TP4 and
   // ratchet SL to TP2 level. Run 17 G5040 captured only 12 pts at TP3 then
   // missed 41 pts of further dump — TP4 staging recovers that capture.
   // Gated by: TRENDING regime (TREND_BULL/TREND_BEAR/VOLATILE) + min ADX.
   if(g_sc.breakout_tp4_staging_enabled) {
      bool tp4_regime_ok = (g_regime_label == "TREND_BULL"
                         || g_regime_label == "TREND_BEAR"
                         || g_regime_label == "VOLATILE");
      double m5_adx_now = 0.0;
      { double _adx_b[1]; if(CopyBuffer(g_mtf[0].h_adx, 0, 0, 1, _adx_b) == 1) m5_adx_now = _adx_b[0]; }
      bool tp4_adx_ok = (m5_adx_now >= (double)g_sc.breakout_tp4_min_adx);
      for(int gi3 = 0; gi3 < ArraySize(g_groups); gi3++) {
         if(!g_groups[gi3].tp2_hit)    continue;   // not yet at TP3 staging level
         if(g_groups[gi3].tp3_hit)     continue;   // already staged to TP4
         if(g_groups[gi3].tp4 <= 0)    continue;   // TP4 not set for this group
         if(!tp4_regime_ok || !tp4_adx_ok) continue; // chop / weak trend — leave at TP3
         double tp3_price_m3 = g_groups[gi3].tp3;
         double tp4_price_m3 = g_groups[gi3].tp4;
         double tp2_price_m3 = g_groups[gi3].tp2;  // ratchet SL target
         string dir3 = g_groups[gi3].direction;
         double bid3 = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double ask3 = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         bool tp3_reached = (dir3 == "BUY" && bid3 >= tp3_price_m3) || (dir3 == "SELL" && ask3 <= tp3_price_m3);
         if(!tp3_reached) continue;
         int pos4[];
         GetGroupPositions(g_groups[gi3].magic_offset, pos4);
         int promoted4 = 0;
         int sl_ratcheted4 = 0;
         for(int k = 0; k < ArraySize(pos4); k++) {
            if(g_pos.SelectByTicket(pos4[k])) {
               double cur_sl4 = g_pos.StopLoss();
               double new_sl4 = cur_sl4;
               // SL invariant: BUY raises only, SELL lowers only
               if(dir3 == "BUY"  && tp2_price_m3 > cur_sl4) new_sl4 = tp2_price_m3;
               else if(dir3 == "SELL" && tp2_price_m3 < cur_sl4) new_sl4 = tp2_price_m3;
               if(g_trade.PositionModify(pos4[k], NormalizeDouble(new_sl4, _Digits), NormalizeDouble(tp4_price_m3, _Digits))) {
                  promoted4++;
                  if(new_sl4 != cur_sl4) sl_ratcheted4++;
               }
            }
         }
         g_groups[gi3].tp3_hit = true;
         if(promoted4 > 0) {
            PrintFormat("FORGE 2.7.27: Group %d TP3 reached — promoted %d runner(s) to TP4=%.2f, SL ratcheted to TP2=%.2f on %d leg(s) (regime=%s adx=%.1f)",
                        g_groups[gi3].id, promoted4, tp4_price_m3, tp2_price_m3, sl_ratcheted4, g_regime_label, m5_adx_now);
         }
      }
   }

   // ── 2.7.27 — TP4 → TP5 staging pass ──────────────────────────────────────────
   // After TP3 runners reach TP4, promote to TP5 and ratchet SL to TP3. Captures
   // the deepest end of a dump/rip. Stricter ADX gate (tp5_min_adx, default 30)
   // so only deeply trending moves qualify. RANGE regime never reaches here.
   if(g_sc.breakout_tp5_staging_enabled) {
      bool tp5_regime_ok = (g_regime_label == "TREND_BULL"
                         || g_regime_label == "TREND_BEAR"
                         || g_regime_label == "VOLATILE");
      double m5_adx_now2 = 0.0;
      { double _adx_b2[1]; if(CopyBuffer(g_mtf[0].h_adx, 0, 0, 1, _adx_b2) == 1) m5_adx_now2 = _adx_b2[0]; }
      bool tp5_adx_ok = (m5_adx_now2 >= (double)g_sc.breakout_tp5_min_adx);
      for(int gi4 = 0; gi4 < ArraySize(g_groups); gi4++) {
         if(!g_groups[gi4].tp3_hit)    continue;   // not yet at TP4 staging level
         if(g_groups[gi4].tp4_hit)     continue;   // already staged to TP5
         if(g_groups[gi4].tp5 <= 0)    continue;   // TP5 not set for this group
         if(!tp5_regime_ok || !tp5_adx_ok) continue;
         double tp4_price_m4 = g_groups[gi4].tp4;
         double tp5_price_m4 = g_groups[gi4].tp5;
         double tp3_price_m4 = g_groups[gi4].tp3;
         string dir4 = g_groups[gi4].direction;
         double bid4 = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double ask4 = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         bool tp4_reached = (dir4 == "BUY" && bid4 >= tp4_price_m4) || (dir4 == "SELL" && ask4 <= tp4_price_m4);
         if(!tp4_reached) continue;
         int pos5[];
         GetGroupPositions(g_groups[gi4].magic_offset, pos5);
         int promoted5 = 0;
         int sl_ratcheted5 = 0;
         for(int k5 = 0; k5 < ArraySize(pos5); k5++) {
            if(g_pos.SelectByTicket(pos5[k5])) {
               double cur_sl5 = g_pos.StopLoss();
               double new_sl5 = cur_sl5;
               if(dir4 == "BUY"  && tp3_price_m4 > cur_sl5) new_sl5 = tp3_price_m4;
               else if(dir4 == "SELL" && tp3_price_m4 < cur_sl5) new_sl5 = tp3_price_m4;
               if(g_trade.PositionModify(pos5[k5], NormalizeDouble(new_sl5, _Digits), NormalizeDouble(tp5_price_m4, _Digits))) {
                  promoted5++;
                  if(new_sl5 != cur_sl5) sl_ratcheted5++;
               }
            }
         }
         g_groups[gi4].tp4_hit = true;
         if(promoted5 > 0) {
            PrintFormat("FORGE 2.7.27: Group %d TP4 reached — promoted %d runner(s) to TP5=%.2f, SL ratcheted to TP3=%.2f on %d leg(s) (regime=%s adx=%.1f)",
                        g_groups[gi4].id, promoted5, tp5_price_m4, tp3_price_m4, sl_ratcheted5, g_regime_label, m5_adx_now2);
         }
      }
   }

   // ── 2.7.25 — ATR trail (peak/trough ratchet) ─────────────────────────────────
   // Per FORGE_RATCHET_LOGIC_IDEAS.md section 5/6:
   //   after TP1 has been hit, track group peak (BUY) / trough (SELL) and trail SL
   //   at peak ∓ trail_mult × ATR. Continuous between milestones — coexists with
   //   the M1 cushion and M2 ratchet-to-TP1. SL invariant preserved (only moves into profit).
   if(g_sc.breakout_atr_trail_enabled) {
      double bid_at = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask_at = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double trail_mult = g_sc.breakout_atr_trail_mult;
      for(int gt = 0; gt < ArraySize(g_groups); gt++) {
         // Update peak/trough every tick regardless of TP1 state (cheap, useful for restart audit)
         if(bid_at > g_groups[gt].peak_price)   g_groups[gt].peak_price   = bid_at;
         if(ask_at > 0 && (g_groups[gt].trough_price <= 0 || ask_at < g_groups[gt].trough_price))
            g_groups[gt].trough_price = ask_at;
         // Trail only kicks in after TP1
         if(!g_groups[gt].tp1_hit) continue;
         double grp_atr_t = g_groups[gt].entry_atr;
         if(grp_atr_t <= 0) continue;  // BRIDGE groups without ATR — skip
         string dir_t = g_groups[gt].direction;
         double trail_sl;
         if(dir_t == "BUY")  trail_sl = g_groups[gt].peak_price   - trail_mult * grp_atr_t;
         else                trail_sl = g_groups[gt].trough_price + trail_mult * grp_atr_t;
         // Apply to each open position in the group with SL invariant
         int trail_pos[];
         GetGroupPositions(g_groups[gt].magic_offset, trail_pos);
         for(int tj = 0; tj < ArraySize(trail_pos); tj++) {
            if(!g_pos.SelectByTicket(trail_pos[tj])) continue;
            double cur_sl_t = g_pos.StopLoss();
            double cur_tp_t = g_pos.TakeProfit();
            bool   would_improve = false;
            if(g_pos.PositionType() == POSITION_TYPE_BUY  && trail_sl > cur_sl_t)
               would_improve = true;
            if(g_pos.PositionType() == POSITION_TYPE_SELL && (cur_sl_t == 0 || trail_sl < cur_sl_t))
               would_improve = true;
            if(!would_improve) continue;
            // Skip tiny moves to avoid OrderModify spam (≥ 1 point change required)
            double point_t = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
            if(MathAbs(trail_sl - cur_sl_t) < point_t) continue;
            g_trade.PositionModify(trail_pos[tj], NormalizeDouble(trail_sl, _Digits), NormalizeDouble(cur_tp_t, _Digits));
         }
      }
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

// ─────────────────────────────────────────────────────────────────────────────
// CancelPendingOnDailyFlip — Filter 3 of v2.7.27 Daily Direction Gate
//
// PURPOSE: When ComputeDailyBias() detects an intraday flip (bull→bear or bear→bull),
//   cancel any pending stops/limits still resting in the broker book within our
//   magic range. Without this, a BUY_STOP placed during a bull morning would still
//   fill in the afternoon dump, opening counter-trend exposure right as the regime
//   has changed.
//
// EVALUATION ORDER:
//   1. Caller checks g_daily_flip_now (one-tick edge flag from ComputeDailyBias)
//   2. Iterate orders top-down (OrdersTotal()-1 → 0) per MQL5 forum 377826 pattern
//   3. Filter by magic range [MagicNumber, MagicNumber+10000)
//   4. Filter by order type — only pending types (limit/stop/stop_limit)
//   5. Optionally skip cascade slot magics if daily_cancel_includes_cascade=false
//
// PARAMETERS: none — reads g_sc.daily_cancel_pending_on_flip / _includes_cascade
//
// RETURNS / SIDE EFFECTS:
//   - Cancels matching pending orders via g_trade.OrderDelete
//   - Prints a one-line journal record for telemetry
//
// CHANGELOG:
//   2026-05-11  v2.7.27 — initial implementation. Pattern adapted from existing
//               ExecuteCancelGroupPending (same iterate-down + magic-range + type filter).
// ─────────────────────────────────────────────────────────────────────────────
void CancelPendingOnDailyFlip() {
   if(!g_sc.daily_direction_gate_enabled) return;
   if(!g_sc.daily_cancel_pending_on_flip) return;
   if(!g_daily_flip_now) return;

   int cancelled = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      ulong ot = OrderGetTicket(i);
      if(ot == 0 || !OrderSelect(ot)) continue;
      if(!ChartSymbolMatches(OrderGetString(ORDER_SYMBOL))) continue;
      int om = (int)OrderGetInteger(ORDER_MAGIC);
      // 2.7.27 codex-review fix #2 — magic range was previously [MagicNumber, MagicNumber+10000)
      // which silently EXCLUDED cascade slot magics (group_magic + 20000..20010), making
      // daily_cancel_includes_cascade=true a no-op. Reworked to two named ranges:
      //   - Core group magics: [MagicNumber+0, MagicNumber+10000)
      //   - Cascade slot magics: [MagicNumber+20000, MagicNumber+30010)
      // Anything outside both ranges is skipped (not ours).
      if(om < MagicNumber) continue;
      int offset = om - MagicNumber;
      bool is_core    = (offset >= 0     && offset < 10000);
      bool is_cascade = (offset >= 20000 && offset < 30010);
      if(!is_core && !is_cascade) continue;
      if(is_cascade && !g_sc.daily_cancel_includes_cascade) continue;
      ENUM_ORDER_TYPE ot_type = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      bool is_pending = (ot_type == ORDER_TYPE_BUY_LIMIT
                      || ot_type == ORDER_TYPE_SELL_LIMIT
                      || ot_type == ORDER_TYPE_BUY_STOP
                      || ot_type == ORDER_TYPE_SELL_STOP
                      || ot_type == ORDER_TYPE_BUY_STOP_LIMIT
                      || ot_type == ORDER_TYPE_SELL_STOP_LIMIT);
      if(!is_pending) continue;
      if(g_trade.OrderDelete(ot)) cancelled++;
   }
   if(cancelled > 0) {
      PrintFormat("FORGE 2.7.27: Daily regime flip — cancelled %d pending order(s). slope=%.2f move=%.2f daily_atr=%.2f",
                  cancelled, g_daily_slope_pts, g_daily_move_pts, g_daily_atr_pts);
   }
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
   // 2.7.36 — Session + killzone state (named to avoid collision with top-level session key)
   j += "\"forge_session_state\":{";
   j += "\"label\":\""           + JsonEscape(ComputeCurrentSessionLabel())  + "\",";
   j += "\"killzone\":\""        + JsonEscape(ComputeCurrentKillzoneLabel()) + "\",";
   j += "\"anchor_mode\":\""     + (g_sc.sessions_ny_anchored ? "NY" : "UTC") + "\",";
   j += "\"killzones_enabled\":" + IntegerToString(g_sc.killzones_enabled ? 1 : 0) + ",";
   j += "\"killzones_gate_entries\":" + IntegerToString(g_sc.killzones_gate_entries ? 1 : 0) + ",";
   j += "\"broker_gmt_offset_winter\":" + IntegerToString(g_sc.broker_gmt_offset_winter) + ",";
   j += "\"broker_gmt_offset_summer\":" + IntegerToString(g_sc.broker_gmt_offset_summer) + ",";
   j += "\"trades_this_session\":"  + IntegerToString(g_scalper_session_trades)  + ",";
   j += "\"trades_this_killzone\":" + IntegerToString(g_scalper_killzone_trades);
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
   j += "\"gmt_offset_sec\":" + IntegerToString(ForgeBrokerGMTOffsetSec()) + ",";
   j += "\"is_us_dst\":"      + IntegerToString(IsUS_DST(TimeGMT()) ? 1 : 0) + ",";
   j += "\"is_eu_dst\":"      + IntegerToString(IsEU_DST(TimeCurrent()) ? 1 : 0) + ",";
   j += "\"broker_gmt_offset_winter\":" + IntegerToString(g_sc.broker_gmt_offset_winter) + ",";
   j += "\"broker_gmt_offset_summer\":" + IntegerToString(g_sc.broker_gmt_offset_summer) + ",";
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
   g_sc.breakout_block_hid_bull_sell          = false;
   g_sc.breakout_rsi_decl_sell_adx_threshold = 40.0;
   g_sc.breakout_require_m30_bear_sell        = true;
   g_sc.breakout_m30_bear_adx_min             = 25.0;
   g_sc.breakout_require_h1_di_buy            = false;
   g_sc.breakout_counter_buy_adx_threshold    = 28.0;
   g_sc.breakout_require_h1_di_sell           = false;
   g_sc.breakout_require_h1_macd_sell         = false;
   g_sc.breakout_require_h1_macd_buy          = false; // 2.7.17: disabled by default; .env override enables
   g_sc.breakout_same_dir_cooldown_seconds    = 0;     // 2.7.17: 0=disabled; .env override sets (e.g. 900 = 15 min)
   g_sc.breakout_failed_gate_enabled          = false; // 2.7.19: 0=disabled by default
   g_sc.breakout_failed_lookback_bars         = 4;     // 4 M5 bars = 20 min memory window
   g_sc.breakout_failed_min_peak_rsi          = 75.0;  // RSI must have peaked at least this in window
   g_sc.breakout_failed_min_rsi_drop          = 3.0;   // current RSI must be >= 3pts below peak
   g_sc.breakout_failed_same_bar_hard_block   = false; // 2.7.20: 0=off; 1=hard-block BUY in same M5 bar as atr_ext SKIP
   g_sc.breakout_require_psar_align           = false; // 2.7.20: 0=off; 1=require psar BELOW for BUY, ABOVE for SELL
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
   g_sc.h1h4_crash_sell_min_m15_adx        = 25.0;  // same as adx_min_sell — M15 must confirm the trend
   g_sc.breakout_min_h1_bear_strength       = 0.2;
   g_sc.breakout_sell_inside_band_lot_factor = 0.25;
   g_sc.breakout_max_reentry_atr_ext = 0.0;
   g_sc.breakout_sl_atr_mult = 2.0;
   g_sc.breakout_buy_sl_atr_mult = 0.0;  // 2.7.18: 0 = use breakout_sl_atr_mult (no BUY override)
   g_sc.breakout_tp1_atr_mult       = 1.0;
   g_sc.breakout_tp1_buy_atr_mult   = 0.0;  // 0 = use breakout_tp1_atr_mult
   g_sc.breakout_tp1_sell_atr_mult  = 0.0;  // 0 = use breakout_tp1_atr_mult
   g_sc.breakout_tp2_atr_mult = 1.5;
   g_sc.breakout_tp3_atr_mult = 2.5;
   g_sc.breakout_tp4_atr_mult = 4.0;
   g_sc.breakout_tp1_close_pct = 40;
   g_sc.breakout_require_m15 = true;
   g_sc.breakout_move_be = true;
   // (peak/trough initialized at group creation in two paths below)
   g_sc.breakout_be_cushion_atr_mult = 0.0;  // 2.7.23: 0 = legacy tight BE+spread+5pts buffer. >0 enables ATR cushion.
   g_sc.breakout_tp2_sl_ratchet_enabled = false;  // 2.7.24: 0 = legacy TP2 only promotes TP→TP3. 1 = also ratchets SL to TP1 level.
   g_sc.breakout_atr_trail_enabled = false;       // 2.7.25: 0 = no ATR trail. 1 = continuous trail SL at peak∓trail_mult×ATR after TP1.
   g_sc.breakout_atr_trail_mult = 1.5;            // 2.7.25: ATR multiplier for trail (spec default).
   // 2.7.27 — Daily Direction Gate defaults (Run 17 G5048 fix).
   g_sc.daily_direction_gate_enabled  = false;    // 2.7.27: master toggle for Filters 1+2+3.
   g_sc.daily_sma_period              = 20;       // 2.7.27: D1 SMA period.
   g_sc.daily_sma_lookback_days       = 3;        // 2.7.27: slope lookback (bars back on D1).
   g_sc.daily_slope_block_atr         = 0.5;      // 2.7.27: slope threshold = 0.5 × daily ATR.
   g_sc.daily_move_block_atr          = 0.5;      // 2.7.27: intraday move threshold = 0.5 × daily ATR.
   g_sc.daily_move_flip_hysteresis    = 0.3;      // 2.7.27: hysteresis on flip declaration.
   g_sc.daily_cancel_pending_on_flip  = true;     // 2.7.27: cancel pendings when regime flips.
   g_sc.daily_cancel_includes_cascade = true;     // 2.7.27: also cancel cascade SELL_STOP_CONT / BUY_LIMIT_RECOV pendings.
   // 2.7.27 — Extended TP4/TP5 staging defaults.
   g_sc.breakout_tp4_staging_enabled  = false;    // 2.7.27: off by default; runner stops at TP3 unless explicitly enabled.
   g_sc.breakout_tp5_atr_mult         = 5.5;      // 2.7.27: TP5 = 5.5×ATR per spec.
   g_sc.breakout_tp4_min_adx          = 25;       // 2.7.27: TP4 only stages when M5 ADX ≥ 25 (trending).
   g_sc.breakout_tp5_staging_enabled  = false;    // 2.7.27: off by default; runner stops at TP4 unless explicitly enabled.
   g_sc.breakout_tp5_min_adx          = 30;       // 2.7.27: TP5 stricter — only stages when M5 ADX ≥ 30 (deep trend).
   // 2.7.28 — Momentum dump-catch defaults (off by default).
   g_sc.dump_catch_enabled            = false;
   g_sc.dump_lookback_bars            = 3;        // 3 M5 bars = 15-min impulse window
   g_sc.dump_atr_mult                 = 1.5;      // move > 1.5×ATR over lookback fires the trigger
   g_sc.dump_max_rsi                  = 50.0;     // SELL when RSI<50, BUY when RSI>50 (mirror)
   g_sc.dump_max_rsi_buy              = 70.0;     // 2.7.34: block BUY when RSI ≥ this — overbought ceiling (G5009 prevention)
   g_sc.dump_min_adx                  = 25.0;     // require ADX>25 to confirm sustained move
   g_sc.dump_require_psar             = true;     // PSAR must agree with dump direction
   g_sc.dump_require_d1_bias          = true;     // require v2.7.27 Filter 1 bias agreement
   g_sc.dump_cooldown_seconds         = 600;      // 10-min cooldown per direction
   g_sc.dump_require_bar_confirm      = false;    // 2.7.32 Option B — default OFF, documented for later validation
   g_sc.dump_lot_factor               = 0.7;      // 0.7× fixed_lot per leg
   g_sc.dump_buy_lot_factor           = 0.0;      // 2.7.35: 0 = use dump_lot_factor; set in .env to override
   g_sc.dump_sell_lot_factor          = 0.0;      // 2.7.35: 0 = use dump_lot_factor; set in .env to override
   g_sc.dump_sell_h1_max              = 0.0;      // 2.7.35: 0 = disabled; set in .env (e.g. 2.0) to block strong-bull SELLs
   // 2.7.29 — Regime H1-strong override defaults (Run 18 Issue 1 fix).
   g_sc.regime_h1_override_factor     = 0.0;      // 0 = disabled (legacy unanimous AND-gating). 2.0 typical when enabled.
   g_sc.regime_h1_override_adx_min    = 30.0;     // Minimum M5 ADX for override to fire.
   // 2.7.31 — BB_PULLBACK_SCALP defaults (additive setup for v2.7.26-blocked bounces)
   g_sc.pullback_scalp_enabled        = false;    // default OFF; operator opts in via env
   g_sc.pullback_scalp_fresh_flip_bars = 3;       // PSAR flip must be within last 3 M5 bars
   g_sc.pullback_scalp_lot_factor     = 0.5;      // half of fixed_lot — smaller exposure
   g_sc.pullback_scalp_sl_atr_mult    = 1.0;      // tight SL — can't ride a real reversal
   g_sc.pullback_scalp_tp1_atr_mult   = 0.3;      // fast scalp TP1
   g_sc.pullback_scalp_tp2_atr_mult   = 0.7;      // runner TP2
   g_sc.pullback_scalp_cooldown_seconds = 600;    // 10-min cooldown per direction
   g_sc.pullback_scalp_max_adx        = 30.0;     // require ADX < 30 (pullback should be exhausting)
   // 2.7.42 — MA_CROSSOVER setup (Phase 2; default OFF, operator opts in via env)
   g_sc.ma_crossover_enabled          = false;
   g_sc.ma_crossover_adx_min          = 20.0;
   g_sc.ma_crossover_lot_factor       = 0.5;
   g_sc.ma_crossover_sl_atr_mult      = 1.5;
   g_sc.ma_crossover_tp1_atr_mult     = 0.5;
   g_sc.ma_crossover_tp2_atr_mult     = 1.5;
   g_sc.ma_crossover_cooldown_seconds = 600;
   // 2.7.42 — VWAP_REVERSION setup (Phase 2; default OFF)
   g_sc.vwap_reversion_enabled              = false;
   g_sc.vwap_reversion_min_deviation_atr    = 1.0;
   g_sc.vwap_reversion_max_deviation_atr    = 3.0;
   g_sc.vwap_reversion_min_extension_bars   = 5;
   g_sc.vwap_reversion_lot_factor           = 0.5;
   g_sc.vwap_reversion_sl_atr_mult          = 1.2;
   g_sc.vwap_reversion_tp1_atr_mult         = 0.4;
   g_sc.vwap_reversion_tp2_atr_mult         = 1.0;
   g_sc.vwap_reversion_cooldown_seconds     = 600;
   // 2.7.42 — FIB_CONFLUENCE setup (Phase 2; default OFF)
   g_sc.fib_confluence_enabled              = false;
   g_sc.fib_confluence_min_confluences      = 1;
   g_sc.fib_confluence_tolerance_atr        = 0.3;
   g_sc.fib_confluence_min_swing_atr        = 2.0;
   g_sc.fib_confluence_lot_factor           = 0.5;
   g_sc.fib_confluence_sl_atr_mult          = 1.5;
   g_sc.fib_confluence_tp1_atr_mult         = 0.5;
   g_sc.fib_confluence_tp2_atr_mult         = 1.3;
   g_sc.fib_confluence_cooldown_seconds     = 600;
   g_sc.fast_lock_min_hold_sec_bounce = 45;
   g_sc.fast_lock_min_hold_sec_breakout = 50;
   g_sc.max_spread_points = 25;
   g_sc.max_open_groups = 2;
   g_sc.max_trades_per_session = 3;
   g_sc.loss_cooldown_sec = 300;
   // 2.7.41 — regime-aware cooldown bypass defaults (default-ON; opt out via env)
   g_sc.cooldown_bypass_on_tp_with_trend = true;
   g_sc.cooldown_bypass_window_sec       = 600;   // 10 min — recent TP1 still counts
   g_sc.cooldown_bypass_min_adx          = 25.0;  // same floor as cascade arming
   g_sc.cooldown_bypass_min_refire_sec   = 5;     // anti-flicker floor
   g_sc.cooldown_bypass_setups           = "";    // empty = no unconditional bypass
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
   g_sc.sell_stop_cont_sl_atr_mult   = 1.5;   // 2.7.16: SL anchored to cascade entry, default 1.5×ATR; protects against SL-hunt wicks

   g_sc.sell_stop_cont_lot_factor    = 1.0;   // full lot — cascade is a confirmed continuation entry
   g_sc.sell_stop_cont_tp_atr_mult   = 1.5;   // ~9pts at ATR=6 — captures the continuation leg
   g_sc.sell_stop_cont_expiry_bars   = 2;     // 10 min — scalpers don't wait; if no fill in 10min, dead
   g_sc.sell_stop_cont_min_rsi       = 25.0;
   g_sc.sell_stop_cont_min_adx      = 25.0;  // same floor as primary SELL entry gate
   g_sc.sell_stop_cont_require_h1_di = true; // H1 DI- > DI+ — same check as require_h1_di_sell gate
   g_sc.sell_stop_cont_require_trend_regime = false; // 2.7.21: 0=off; 1=require regime != RANGE before arming cascade
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
   // 2.7.36 — minute-precision overrides (-1 sentinel = use legacy hour fields)
   g_sc.london_start_min = -1;  g_sc.london_end_min = -1;
   g_sc.ny_start_min     = -1;  g_sc.ny_end_min     = -1;
   g_sc.asia_start_min   = -1;  g_sc.asia_end_min   = -1;
   g_sc.sessions_ny_anchored     = false;
   // Approach B broker offsets — defaults for Vantage / Cyprus brokers.
   g_sc.broker_gmt_offset_winter = 2;
   g_sc.broker_gmt_offset_summer = 3;
   // ICT killzones (NY minute-of-day)
   g_sc.killzones_enabled        = false;
   g_sc.killzones_gate_entries   = false;
   g_sc.kz_asia_start_min        = 19*60;   // 19:00 NY (wraps to 03:00)
   g_sc.kz_asia_end_min          =  3*60;
   g_sc.kz_london_open_start_min =  2*60;
   g_sc.kz_london_open_end_min   =  5*60;
   g_sc.kz_ny_open_start_min     =  7*60;
   g_sc.kz_ny_open_end_min       = 10*60;
   g_sc.kz_london_close_start_min= 10*60;
   g_sc.kz_london_close_end_min  = 12*60;
   // 2.7.38 Tier 1 Boolean Composites — all default-OFF
   g_sc.block_sell_in_chop_enabled            = false;
   g_sc.intraday_reversal_sell_enabled        = false;
   g_sc.intraday_reversal_sell_lot_mult       = 2.0;
   g_sc.fractional_sell_in_bull_enabled       = false;
   g_sc.fractional_sell_in_bull_lot_factor    = 0.25;
   g_sc.fractional_sell_in_bull_sl_atr_mult   = 1.5;
   g_sc.fractional_sell_in_bull_tp1_atr_mult  = 0.3;
   g_sc.bull_day_dip_buy_enabled              = false;
   g_sc.bull_day_dip_buy_lot_mult             = 1.0;
   g_sc.bull_day_dip_buy_sl_atr_mult          = 1.0;
   g_sc.bull_day_dip_buy_tp1_atr_mult         = 0.65;
   g_sc.bull_day_dip_buy_reentry_cooldown_sec = 300;
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
   g_sc.max_open_same_direction_bypass_setups = "";  // empty = no bypass; operator opts in via FORGE_*
   g_sc.entry_quality_bars = 3;
   g_sc.min_body_ratio = 0.40;
   g_sc.min_directional_bars = 2;
   g_sc.require_bb_expansion = true;
   g_sc.lot_sizing_source = "AUTO";
   g_sc.lot_inputs_override = false;
   // 2.7.40 — fixed_lot is the single absolute base. Seed at safe broker-min until JSON loads;
   //   real value comes from lot_sizing.fixed_lot in scalper_config.json (typically 0.25).
   //   ScalperLotFactor flows through combined_lot_factor at compute time, NOT here.
   g_sc.lot_fixed = 0.02;
   g_sc.scalper_lot_factor = 1.0;  // no-op default; env override via FORGE_GLOBAL_SCALPER_LOT_FACTOR
   g_sc.lot_num_trades = MathMax(1, ScalperTrades);
   g_sc.lot_min_trades = 0;
   g_sc.lot_max_trades = 0;
   g_sc.staged_entry_enabled = true;
   g_sc.staged_initial_legs = 1;
   g_sc.staged_add_interval_sec = 25;
   g_sc.staged_add_min_favorable_points = 0;
   g_sc.wave_confirmation_lot_mult = 1.0;  // 2.7.34: default 1.0 = no amplification. Operator opts in via env.
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
   // 2.7.40 — ScalperLot (absolute) removed. ScalperLotFactor (multiplier, default 1.0) now folds
   //   into combined_lot_factor at the compute site; it does NOT mutate g_sc.lot_fixed here.
   //   This unifies the lot pipeline: fixed_lot stays the single absolute base; every other
   //   knob is a multiplier — including the MT5-input lever.
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
               "Lot/legs fall back to seed (lot_fixed=0.02, ScalperLotFactor=1.0, ScalperTrades) until the file is available.");
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
      // 2.7.18 — BUY-only SL widen (Run 15 G5015 fix). 0 = use breakout_sl_atr_mult; >0 = override for BUY only.
      // Range 0..6 allows up to 6×ATR for severe SL-hunt protection while bounded against runaway losses.
      if(JsonHasKey(breakout_json, "buy_sl_atr_mult")) {
         v = JsonGetDouble(breakout_json, "buy_sl_atr_mult");
         if(v >= 0.0 && v <= 6.0) g_sc.breakout_buy_sl_atr_mult = v;
      }
      // 2.7.23 — BE-trail cushion (Run 17 G5002 fix). 0 = legacy tight BE+spread+5pts buffer.
      // >0 = SL moves to entry∓mult×ATR cushion below/above entry, giving breathing room in volatile markets.
      // Range 0..3: 0.3-0.5 typical; >2.0 effectively disables BE-trail.
      if(JsonHasKey(breakout_json, "be_cushion_atr_mult")) {
         v = JsonGetDouble(breakout_json, "be_cushion_atr_mult");
         if(v >= 0.0 && v <= 3.0) g_sc.breakout_be_cushion_atr_mult = v;
      }
      // 2.7.24 — TP2 SL ratchet to TP1 (per FORGE_RATCHET_LOGIC_IDEAS.md Milestone 2).
      // When TP2 reached, ratchet SL up to TP1 level (locks TP1-distance of profit).
      // SL invariant preserved by ratchet helper (only moves SL into profit direction).
      if(JsonHasKey(breakout_json, "tp2_sl_ratchet_enabled")) {
         v = JsonGetDouble(breakout_json, "tp2_sl_ratchet_enabled");
         g_sc.breakout_tp2_sl_ratchet_enabled = (v >= 0.5);
      }
      // 2.7.25 — ATR trail (per FORGE_RATCHET_LOGIC_IDEAS.md). After TP1, trail SL at group peak∓mult×ATR.
      if(JsonHasKey(breakout_json, "atr_trail_enabled")) {
         v = JsonGetDouble(breakout_json, "atr_trail_enabled");
         g_sc.breakout_atr_trail_enabled = (v >= 0.5);
      }
      if(JsonHasKey(breakout_json, "atr_trail_mult")) {
         v = JsonGetDouble(breakout_json, "atr_trail_mult");
         if(v >= 0.3 && v <= 5.0) g_sc.breakout_atr_trail_mult = v;
      }
      // 2.7.27 — Extended TP4/TP5 staging (Run 17 G5040 +$218 winner had 53 pts of additional move after TP3).
      // TP3→TP4 ratchets SL to TP2 and promotes TP target to TP4 (4.0×ATR by default).
      // TP4→TP5 ratchets SL to TP3 and promotes TP target to TP5 (5.5×ATR default).
      // Both gated by min ADX + TRENDING regime so chop entries don't over-hold.
      if(JsonHasKey(breakout_json, "tp4_staging_enabled")) {
         v = JsonGetDouble(breakout_json, "tp4_staging_enabled");
         g_sc.breakout_tp4_staging_enabled = (v >= 0.5);
      }
      if(JsonHasKey(breakout_json, "tp5_atr_mult")) {
         v = JsonGetDouble(breakout_json, "tp5_atr_mult");
         if(v >= 3.0 && v <= 10.0) g_sc.breakout_tp5_atr_mult = v;
      }
      if(JsonHasKey(breakout_json, "tp4_min_adx")) {
         v = JsonGetDouble(breakout_json, "tp4_min_adx");
         if(v >= 0 && v <= 100) g_sc.breakout_tp4_min_adx = (int)v;
      }
      if(JsonHasKey(breakout_json, "tp5_staging_enabled")) {
         v = JsonGetDouble(breakout_json, "tp5_staging_enabled");
         g_sc.breakout_tp5_staging_enabled = (v >= 0.5);
      }
      if(JsonHasKey(breakout_json, "tp5_min_adx")) {
         v = JsonGetDouble(breakout_json, "tp5_min_adx");
         if(v >= 0 && v <= 100) g_sc.breakout_tp5_min_adx = (int)v;
      }
      // 2.7.27 codex-review fix: tp2/tp3/tp4 ATR multipliers were orphan keys —
      // present in sync.py mapping + scalper_config.json but never parsed in the EA.
      // Adding parse handlers so FORGE_BREAKOUT_TP{2,3,4}_ATR_MULT overrides actually apply.
      if(JsonHasKey(breakout_json, "tp2_atr_mult")) {
         v = JsonGetDouble(breakout_json, "tp2_atr_mult");
         if(v >= 0.1 && v <= 10.0) g_sc.breakout_tp2_atr_mult = v;
      }
      if(JsonHasKey(breakout_json, "tp3_atr_mult")) {
         v = JsonGetDouble(breakout_json, "tp3_atr_mult");
         if(v >= 0.1 && v <= 20.0) g_sc.breakout_tp3_atr_mult = v;
      }
      if(JsonHasKey(breakout_json, "tp4_atr_mult")) {
         v = JsonGetDouble(breakout_json, "tp4_atr_mult");
         if(v >= 0.1 && v <= 20.0) g_sc.breakout_tp4_atr_mult = v;
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
      if(JsonHasKey(breakout_json, "h1h4_crash_sell_min_m15_adx")) {
         v = JsonGetDouble(breakout_json, "h1h4_crash_sell_min_m15_adx");
         if(v >= 0 && v <= 80) g_sc.h1h4_crash_sell_min_m15_adx = v;
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
      if(JsonHasKey(breakout_json, "sell_stop_cont_sl_atr_mult")){ v = JsonGetDouble(breakout_json,"sell_stop_cont_sl_atr_mult"); if(v >= 0.0 && v <= 10.0) g_sc.sell_stop_cont_sl_atr_mult = v; }
      if(JsonHasKey(breakout_json, "sell_stop_cont_lot_factor")) { v = JsonGetDouble(breakout_json,"sell_stop_cont_lot_factor"); if(v > 0 && v <= 2.0)  g_sc.sell_stop_cont_lot_factor = v; }
      if(JsonHasKey(breakout_json, "sell_stop_cont_tp_atr_mult")) { v = JsonGetDouble(breakout_json,"sell_stop_cont_tp_atr_mult"); if(v >= 0.0) g_sc.sell_stop_cont_tp_atr_mult = v; }
      if(JsonHasKey(breakout_json, "sell_stop_cont_expiry_bars")){ v = JsonGetDouble(breakout_json,"sell_stop_cont_expiry_bars"); if(v >= 1 && v <= 50) g_sc.sell_stop_cont_expiry_bars = (int)v; }
      if(JsonHasKey(breakout_json, "sell_stop_cont_min_rsi"))    { v = JsonGetDouble(breakout_json,"sell_stop_cont_min_rsi");    if(v >= 0 && v < 50)  g_sc.sell_stop_cont_min_rsi    = v; }
      if(JsonHasKey(breakout_json, "sell_stop_cont_min_adx"))   { v = JsonGetDouble(breakout_json,"sell_stop_cont_min_adx");   if(v >= 0 && v <= 80) g_sc.sell_stop_cont_min_adx   = v; }
      if(JsonHasKey(breakout_json, "sell_stop_cont_require_h1_di")) { v = JsonGetDouble(breakout_json,"sell_stop_cont_require_h1_di"); g_sc.sell_stop_cont_require_h1_di = (v >= 0.5); }
      if(JsonHasKey(breakout_json, "sell_stop_cont_require_trend_regime")) { v = JsonGetDouble(breakout_json,"sell_stop_cont_require_trend_regime"); g_sc.sell_stop_cont_require_trend_regime = (v >= 0.5); }
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
      if(JsonHasKey(breakout_json, "block_hid_bull_sell")) {
         v = JsonGetDouble(breakout_json, "block_hid_bull_sell");
         g_sc.breakout_block_hid_bull_sell = (v >= 0.5);
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
      if(JsonHasKey(breakout_json, "require_h1_macd_buy")) {
         v = JsonGetDouble(breakout_json, "require_h1_macd_buy");
         g_sc.breakout_require_h1_macd_buy = (v >= 0.5);
      }
      if(JsonHasKey(breakout_json, "same_dir_cooldown_seconds")) {
         v = JsonGetDouble(breakout_json, "same_dir_cooldown_seconds");
         if(v >= 0 && v <= 3600) g_sc.breakout_same_dir_cooldown_seconds = (int)v;
      }
      // 2.7.19 — failed-breakout-pullback gate config parse (Run 15 G5013/G5015 fix)
      if(JsonHasKey(breakout_json, "failed_gate_enabled")) {
         v = JsonGetDouble(breakout_json, "failed_gate_enabled");
         g_sc.breakout_failed_gate_enabled = (v >= 0.5);
      }
      if(JsonHasKey(breakout_json, "failed_lookback_bars")) {
         v = JsonGetDouble(breakout_json, "failed_lookback_bars");
         if(v >= 1 && v <= 20) g_sc.breakout_failed_lookback_bars = (int)v;
      }
      if(JsonHasKey(breakout_json, "failed_min_peak_rsi")) {
         v = JsonGetDouble(breakout_json, "failed_min_peak_rsi");
         if(v >= 50.0 && v <= 90.0) g_sc.breakout_failed_min_peak_rsi = v;
      }
      if(JsonHasKey(breakout_json, "failed_min_rsi_drop")) {
         v = JsonGetDouble(breakout_json, "failed_min_rsi_drop");
         if(v >= 0.0 && v <= 30.0) g_sc.breakout_failed_min_rsi_drop = v;
      }
      // 2.7.20 — same-bar hard block + PSAR alignment
      if(JsonHasKey(breakout_json, "failed_same_bar_hard_block")) {
         v = JsonGetDouble(breakout_json, "failed_same_bar_hard_block");
         g_sc.breakout_failed_same_bar_hard_block = (v >= 0.5);
      }
      if(JsonHasKey(breakout_json, "require_psar_align")) {
         v = JsonGetDouble(breakout_json, "require_psar_align");
         g_sc.breakout_require_psar_align = (v >= 0.5);
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
   // 2.7.41 — regime-aware cooldown bypass
   if(JsonHasKey(content, "cooldown_bypass_on_tp_with_trend")) {
      v = JsonGetDouble(content, "cooldown_bypass_on_tp_with_trend");
      g_sc.cooldown_bypass_on_tp_with_trend = (v >= 0.5);
   }
   if(JsonHasKey(content, "cooldown_bypass_window_sec")) {
      v = JsonGetDouble(content, "cooldown_bypass_window_sec");
      if(v >= 30 && v <= 7200) g_sc.cooldown_bypass_window_sec = (int)v;
   }
   if(JsonHasKey(content, "cooldown_bypass_min_adx")) {
      v = JsonGetDouble(content, "cooldown_bypass_min_adx");
      if(v >= 0 && v <= 80) g_sc.cooldown_bypass_min_adx = v;
   }
   if(JsonHasKey(content, "cooldown_bypass_min_refire_sec")) {
      v = JsonGetDouble(content, "cooldown_bypass_min_refire_sec");
      if(v >= 0 && v <= 600) g_sc.cooldown_bypass_min_refire_sec = (int)v;
   }
   if(JsonHasKey(content, "cooldown_bypass_setups")) {
      g_sc.cooldown_bypass_setups = JsonGetString(content, "cooldown_bypass_setups");
   }
   if(JsonHasKey(content,"session_ny_sell_cutoff_utc")) { v = JsonGetDouble(content,"session_ny_sell_cutoff_utc"); if(v >= 0 && v <= 23) g_sc.session_ny_sell_cutoff_utc = (int)v; }
   // 2.7.27 — Daily Direction Gate (Filters 1+2+3) — Run 17 G5048 fix.
   // Filter 1 blocks BUY when D1 SMA slope < −threshold (multi-day rollover);
   //   blocks SELL when slope > +threshold. Threshold = slope_block_atr × daily_ATR.
   // Filter 2 tracks intraday cumulative move from D1 open; flips between bull/bear with hysteresis.
   // Filter 3 cancels pending stops/limits within our magic range when a flip fires.
   if(JsonHasKey(content,"daily_direction_gate_enabled"))  { v = JsonGetDouble(content,"daily_direction_gate_enabled");  g_sc.daily_direction_gate_enabled  = (v >= 0.5); }
   if(JsonHasKey(content,"daily_sma_period"))               { v = JsonGetDouble(content,"daily_sma_period");              if(v >= 2 && v <= 200) g_sc.daily_sma_period = (int)v; }
   if(JsonHasKey(content,"daily_sma_lookback_days"))        { v = JsonGetDouble(content,"daily_sma_lookback_days");       if(v >= 1 && v <= 30)  g_sc.daily_sma_lookback_days = (int)v; }
   if(JsonHasKey(content,"daily_slope_block_atr"))          { v = JsonGetDouble(content,"daily_slope_block_atr");         if(v >= 0.0 && v <= 5.0) g_sc.daily_slope_block_atr = v; }
   if(JsonHasKey(content,"daily_move_block_atr"))           { v = JsonGetDouble(content,"daily_move_block_atr");          if(v >= 0.0 && v <= 5.0) g_sc.daily_move_block_atr  = v; }
   if(JsonHasKey(content,"daily_move_flip_hysteresis"))     { v = JsonGetDouble(content,"daily_move_flip_hysteresis");    if(v >= 0.0 && v <= 5.0) g_sc.daily_move_flip_hysteresis = v; }
   if(JsonHasKey(content,"daily_cancel_pending_on_flip"))   { v = JsonGetDouble(content,"daily_cancel_pending_on_flip");  g_sc.daily_cancel_pending_on_flip  = (v >= 0.5); }
   if(JsonHasKey(content,"daily_cancel_includes_cascade"))  { v = JsonGetDouble(content,"daily_cancel_includes_cascade"); g_sc.daily_cancel_includes_cascade = (v >= 0.5); }
   // 2.7.28 — Momentum dump-catch parses
   if(JsonHasKey(content,"dump_catch_enabled"))       { v = JsonGetDouble(content,"dump_catch_enabled");       g_sc.dump_catch_enabled       = (v >= 0.5); }
   if(JsonHasKey(content,"dump_lookback_bars"))       { v = JsonGetDouble(content,"dump_lookback_bars");       if(v >= 1 && v <= 20)    g_sc.dump_lookback_bars    = (int)v; }
   if(JsonHasKey(content,"dump_atr_mult"))            { v = JsonGetDouble(content,"dump_atr_mult");            if(v >= 0.3 && v <= 5.0) g_sc.dump_atr_mult         = v; }
   if(JsonHasKey(content,"dump_max_rsi"))             { v = JsonGetDouble(content,"dump_max_rsi");             if(v >= 0 && v <= 100)   g_sc.dump_max_rsi          = v; }
   if(JsonHasKey(content,"dump_max_rsi_buy"))         { v = JsonGetDouble(content,"dump_max_rsi_buy");         if(v >= 0 && v <= 100)   g_sc.dump_max_rsi_buy      = v; }
   if(JsonHasKey(content,"dump_min_adx"))             { v = JsonGetDouble(content,"dump_min_adx");             if(v >= 0 && v <= 100)   g_sc.dump_min_adx          = v; }
   if(JsonHasKey(content,"dump_require_psar"))        { v = JsonGetDouble(content,"dump_require_psar");        g_sc.dump_require_psar    = (v >= 0.5); }
   if(JsonHasKey(content,"dump_require_d1_bias"))     { v = JsonGetDouble(content,"dump_require_d1_bias");     g_sc.dump_require_d1_bias = (v >= 0.5); }
   if(JsonHasKey(content,"dump_cooldown_seconds"))    { v = JsonGetDouble(content,"dump_cooldown_seconds");    if(v >= 0 && v <= 7200)  g_sc.dump_cooldown_seconds = (int)v; }
   if(JsonHasKey(content,"dump_require_bar_confirm")) { v = JsonGetDouble(content,"dump_require_bar_confirm"); g_sc.dump_require_bar_confirm = (v >= 0.5); }
   if(JsonHasKey(content,"dump_lot_factor"))          { v = JsonGetDouble(content,"dump_lot_factor");          if(v > 0 && v <= 2.0)    g_sc.dump_lot_factor       = v; }
   if(JsonHasKey(content,"dump_buy_lot_factor"))      { v = JsonGetDouble(content,"dump_buy_lot_factor");      if(v >= 0 && v <= 2.0)   g_sc.dump_buy_lot_factor   = v; }
   if(JsonHasKey(content,"dump_sell_lot_factor"))     { v = JsonGetDouble(content,"dump_sell_lot_factor");     if(v >= 0 && v <= 2.0)   g_sc.dump_sell_lot_factor  = v; }
   if(JsonHasKey(content,"dump_sell_h1_max"))         { v = JsonGetDouble(content,"dump_sell_h1_max");         if(v >= 0 && v <= 10.0)  g_sc.dump_sell_h1_max      = v; }
   // 2.7.29 — Regime H1-strong override (Run 18 Issue 1 fix).
   if(JsonHasKey(content,"regime_h1_override_factor"))  { v = JsonGetDouble(content,"regime_h1_override_factor");  if(v >= 0.0 && v <= 10.0) g_sc.regime_h1_override_factor  = v; }
   if(JsonHasKey(content,"regime_h1_override_adx_min")) { v = JsonGetDouble(content,"regime_h1_override_adx_min"); if(v >= 0.0 && v <= 100.0) g_sc.regime_h1_override_adx_min = v; }
   // 2.7.31 — BB_PULLBACK_SCALP JSON overrides
   if(JsonHasKey(content,"pullback_scalp_enabled"))        { v = JsonGetDouble(content,"pullback_scalp_enabled");        g_sc.pullback_scalp_enabled = (v >= 0.5); }
   if(JsonHasKey(content,"pullback_scalp_fresh_flip_bars")) { v = JsonGetDouble(content,"pullback_scalp_fresh_flip_bars"); if(v >= 1 && v <= 20) g_sc.pullback_scalp_fresh_flip_bars = (int)v; }
   if(JsonHasKey(content,"pullback_scalp_lot_factor"))      { v = JsonGetDouble(content,"pullback_scalp_lot_factor");      if(v >= 0.01 && v <= 2.0) g_sc.pullback_scalp_lot_factor = v; }
   if(JsonHasKey(content,"pullback_scalp_sl_atr_mult"))     { v = JsonGetDouble(content,"pullback_scalp_sl_atr_mult");     if(v >= 0.2 && v <= 5.0) g_sc.pullback_scalp_sl_atr_mult = v; }
   if(JsonHasKey(content,"pullback_scalp_tp1_atr_mult"))    { v = JsonGetDouble(content,"pullback_scalp_tp1_atr_mult");    if(v >= 0.1 && v <= 3.0) g_sc.pullback_scalp_tp1_atr_mult = v; }
   if(JsonHasKey(content,"pullback_scalp_tp2_atr_mult"))    { v = JsonGetDouble(content,"pullback_scalp_tp2_atr_mult");    if(v >= 0.2 && v <= 5.0) g_sc.pullback_scalp_tp2_atr_mult = v; }
   if(JsonHasKey(content,"pullback_scalp_cooldown_seconds")) { v = JsonGetDouble(content,"pullback_scalp_cooldown_seconds"); if(v >= 0 && v <= 7200) g_sc.pullback_scalp_cooldown_seconds = (int)v; }
   if(JsonHasKey(content,"pullback_scalp_max_adx"))         { v = JsonGetDouble(content,"pullback_scalp_max_adx");         if(v >= 0 && v <= 100) g_sc.pullback_scalp_max_adx = v; }
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
   // 2.7.36 — Session minute-precision + NY anchor + broker offsets + killzones
   if(JsonHasKey(content, "london_start_min")) { v=JsonGetDouble(content,"london_start_min"); if(v>=-1&&v<=1439) g_sc.london_start_min=(int)v; }
   if(JsonHasKey(content, "london_end_min"))   { v=JsonGetDouble(content,"london_end_min");   if(v>=-1&&v<=1440) g_sc.london_end_min  =(int)v; }
   if(JsonHasKey(content, "ny_start_min"))     { v=JsonGetDouble(content,"ny_start_min");     if(v>=-1&&v<=1439) g_sc.ny_start_min    =(int)v; }
   if(JsonHasKey(content, "ny_end_min"))       { v=JsonGetDouble(content,"ny_end_min");       if(v>=-1&&v<=1440) g_sc.ny_end_min      =(int)v; }
   if(JsonHasKey(content, "asia_start_min"))   { v=JsonGetDouble(content,"asia_start_min");   if(v>=-1&&v<=1439) g_sc.asia_start_min  =(int)v; }
   if(JsonHasKey(content, "asia_end_min"))     { v=JsonGetDouble(content,"asia_end_min");     if(v>=-1&&v<=1440) g_sc.asia_end_min    =(int)v; }
   if(JsonHasKey(content, "sessions_ny_anchored"))     { v=JsonGetDouble(content,"sessions_ny_anchored");     g_sc.sessions_ny_anchored=(v>=0.5); }
   if(JsonHasKey(content, "broker_gmt_offset_winter")) { v=JsonGetDouble(content,"broker_gmt_offset_winter"); if(v>=-12&&v<=14) g_sc.broker_gmt_offset_winter=(int)v; }
   if(JsonHasKey(content, "broker_gmt_offset_summer")) { v=JsonGetDouble(content,"broker_gmt_offset_summer"); if(v>=-12&&v<=14) g_sc.broker_gmt_offset_summer=(int)v; }
   if(JsonHasKey(content, "killzones_enabled"))        { v=JsonGetDouble(content,"killzones_enabled");        g_sc.killzones_enabled=(v>=0.5); }
   if(JsonHasKey(content, "killzones_gate_entries"))   { v=JsonGetDouble(content,"killzones_gate_entries");   g_sc.killzones_gate_entries=(v>=0.5); }
   if(JsonHasKey(content, "kz_asia_start_min"))         { v=JsonGetDouble(content,"kz_asia_start_min");         if(v>=0&&v<=1439) g_sc.kz_asia_start_min        =(int)v; }
   if(JsonHasKey(content, "kz_asia_end_min"))           { v=JsonGetDouble(content,"kz_asia_end_min");           if(v>=0&&v<=1440) g_sc.kz_asia_end_min          =(int)v; }
   if(JsonHasKey(content, "kz_london_open_start_min"))  { v=JsonGetDouble(content,"kz_london_open_start_min");  if(v>=0&&v<=1439) g_sc.kz_london_open_start_min =(int)v; }
   if(JsonHasKey(content, "kz_london_open_end_min"))    { v=JsonGetDouble(content,"kz_london_open_end_min");    if(v>=0&&v<=1440) g_sc.kz_london_open_end_min   =(int)v; }
   if(JsonHasKey(content, "kz_ny_open_start_min"))      { v=JsonGetDouble(content,"kz_ny_open_start_min");      if(v>=0&&v<=1439) g_sc.kz_ny_open_start_min     =(int)v; }
   if(JsonHasKey(content, "kz_ny_open_end_min"))        { v=JsonGetDouble(content,"kz_ny_open_end_min");        if(v>=0&&v<=1440) g_sc.kz_ny_open_end_min       =(int)v; }
   if(JsonHasKey(content, "kz_london_close_start_min")) { v=JsonGetDouble(content,"kz_london_close_start_min"); if(v>=0&&v<=1439) g_sc.kz_london_close_start_min=(int)v; }
   if(JsonHasKey(content, "kz_london_close_end_min"))   { v=JsonGetDouble(content,"kz_london_close_end_min");   if(v>=0&&v<=1440) g_sc.kz_london_close_end_min  =(int)v; }
   // 2.7.38 Tier 1 Boolean Composites
   if(JsonHasKey(content, "block_sell_in_chop_enabled"))            { v=JsonGetDouble(content,"block_sell_in_chop_enabled");            g_sc.block_sell_in_chop_enabled=(v>=0.5); }
   if(JsonHasKey(content, "intraday_reversal_sell_enabled"))        { v=JsonGetDouble(content,"intraday_reversal_sell_enabled");        g_sc.intraday_reversal_sell_enabled=(v>=0.5); }
   if(JsonHasKey(content, "intraday_reversal_sell_lot_mult"))       { v=JsonGetDouble(content,"intraday_reversal_sell_lot_mult");       if(v>=0.5&&v<=5.0) g_sc.intraday_reversal_sell_lot_mult=v; }
   if(JsonHasKey(content, "fractional_sell_in_bull_enabled"))       { v=JsonGetDouble(content,"fractional_sell_in_bull_enabled");       g_sc.fractional_sell_in_bull_enabled=(v>=0.5); }
   if(JsonHasKey(content, "fractional_sell_in_bull_lot_factor"))    { v=JsonGetDouble(content,"fractional_sell_in_bull_lot_factor");    if(v>0.0&&v<=1.0) g_sc.fractional_sell_in_bull_lot_factor=v; }
   if(JsonHasKey(content, "fractional_sell_in_bull_sl_atr_mult"))   { v=JsonGetDouble(content,"fractional_sell_in_bull_sl_atr_mult");   if(v>=0.5&&v<=5.0) g_sc.fractional_sell_in_bull_sl_atr_mult=v; }
   if(JsonHasKey(content, "fractional_sell_in_bull_tp1_atr_mult"))  { v=JsonGetDouble(content,"fractional_sell_in_bull_tp1_atr_mult");  if(v>=0.1&&v<=2.0) g_sc.fractional_sell_in_bull_tp1_atr_mult=v; }
   if(JsonHasKey(content, "bull_day_dip_buy_enabled"))              { v=JsonGetDouble(content,"bull_day_dip_buy_enabled");              g_sc.bull_day_dip_buy_enabled=(v>=0.5); }
   if(JsonHasKey(content, "bull_day_dip_buy_lot_mult"))             { v=JsonGetDouble(content,"bull_day_dip_buy_lot_mult");             if(v>=0.1&&v<=10.0) g_sc.bull_day_dip_buy_lot_mult=v; }
   if(JsonHasKey(content, "bull_day_dip_buy_sl_atr_mult"))          { v=JsonGetDouble(content,"bull_day_dip_buy_sl_atr_mult");          if(v>=0.3&&v<=5.0) g_sc.bull_day_dip_buy_sl_atr_mult=v; }
   if(JsonHasKey(content, "bull_day_dip_buy_tp1_atr_mult"))         { v=JsonGetDouble(content,"bull_day_dip_buy_tp1_atr_mult");         if(v>=0.1&&v<=3.0) g_sc.bull_day_dip_buy_tp1_atr_mult=v; }
   if(JsonHasKey(content, "bull_day_dip_buy_reentry_cooldown_sec")) { v=JsonGetDouble(content,"bull_day_dip_buy_reentry_cooldown_sec"); if(v>=0&&v<=3600) g_sc.bull_day_dip_buy_reentry_cooldown_sec=(int)v; }
   // 2.7.42 — MA_CROSSOVER setup (Phase 2). JSON keys live under setup.* / atom.* / geometry.* /
   //   timing.* in defaults.json; JsonHasKey/JsonGetDouble use flat substring search so we read
   //   them as top-level here per the v2.7.38 composites convention.
   if(JsonHasKey(content, "ma_crossover_enabled"))           { v=JsonGetDouble(content,"ma_crossover_enabled");           g_sc.ma_crossover_enabled=(v>=0.5); }
   if(JsonHasKey(content, "ma_crossover_adx_min"))           { v=JsonGetDouble(content,"ma_crossover_adx_min");           if(v>=5.0&&v<=80.0) g_sc.ma_crossover_adx_min=v; }
   if(JsonHasKey(content, "ma_crossover_lot_factor"))        { v=JsonGetDouble(content,"ma_crossover_lot_factor");        if(v>=0.1&&v<=2.0) g_sc.ma_crossover_lot_factor=v; }
   if(JsonHasKey(content, "ma_crossover_sl_atr_mult"))       { v=JsonGetDouble(content,"ma_crossover_sl_atr_mult");       if(v>=0.5&&v<=5.0) g_sc.ma_crossover_sl_atr_mult=v; }
   if(JsonHasKey(content, "ma_crossover_tp1_atr_mult"))      { v=JsonGetDouble(content,"ma_crossover_tp1_atr_mult");      if(v>=0.1&&v<=5.0) g_sc.ma_crossover_tp1_atr_mult=v; }
   if(JsonHasKey(content, "ma_crossover_tp2_atr_mult"))      { v=JsonGetDouble(content,"ma_crossover_tp2_atr_mult");      if(v>=0.1&&v<=10.0) g_sc.ma_crossover_tp2_atr_mult=v; }
   if(JsonHasKey(content, "ma_crossover_cooldown_seconds"))  { v=JsonGetDouble(content,"ma_crossover_cooldown_seconds");  if(v>=0&&v<=7200) g_sc.ma_crossover_cooldown_seconds=(int)v; }
   // 2.7.42 — VWAP_REVERSION setup (Phase 2). Same flat-search convention as MA_CROSSOVER.
   if(JsonHasKey(content, "vwap_reversion_enabled"))              { v=JsonGetDouble(content,"vwap_reversion_enabled");              g_sc.vwap_reversion_enabled=(v>=0.5); }
   if(JsonHasKey(content, "vwap_reversion_min_deviation_atr"))    { v=JsonGetDouble(content,"vwap_reversion_min_deviation_atr");    if(v>=0.1&&v<=10.0) g_sc.vwap_reversion_min_deviation_atr=v; }
   if(JsonHasKey(content, "vwap_reversion_max_deviation_atr"))    { v=JsonGetDouble(content,"vwap_reversion_max_deviation_atr");    if(v>=0.5&&v<=20.0) g_sc.vwap_reversion_max_deviation_atr=v; }
   if(JsonHasKey(content, "vwap_reversion_min_extension_bars"))   { v=JsonGetDouble(content,"vwap_reversion_min_extension_bars");   if(v>=1&&v<=50) g_sc.vwap_reversion_min_extension_bars=(int)v; }
   if(JsonHasKey(content, "vwap_reversion_lot_factor"))           { v=JsonGetDouble(content,"vwap_reversion_lot_factor");           if(v>=0.1&&v<=2.0) g_sc.vwap_reversion_lot_factor=v; }
   if(JsonHasKey(content, "vwap_reversion_sl_atr_mult"))          { v=JsonGetDouble(content,"vwap_reversion_sl_atr_mult");          if(v>=0.5&&v<=5.0) g_sc.vwap_reversion_sl_atr_mult=v; }
   if(JsonHasKey(content, "vwap_reversion_tp1_atr_mult"))         { v=JsonGetDouble(content,"vwap_reversion_tp1_atr_mult");         if(v>=0.1&&v<=5.0) g_sc.vwap_reversion_tp1_atr_mult=v; }
   if(JsonHasKey(content, "vwap_reversion_tp2_atr_mult"))         { v=JsonGetDouble(content,"vwap_reversion_tp2_atr_mult");         if(v>=0.1&&v<=10.0) g_sc.vwap_reversion_tp2_atr_mult=v; }
   if(JsonHasKey(content, "vwap_reversion_cooldown_seconds"))     { v=JsonGetDouble(content,"vwap_reversion_cooldown_seconds");     if(v>=0&&v<=7200) g_sc.vwap_reversion_cooldown_seconds=(int)v; }
   // 2.7.42 — FIB_CONFLUENCE setup (Phase 2). Flat-search reads from setup/atom/geometry/timing sections.
   if(JsonHasKey(content, "fib_confluence_enabled"))              { v=JsonGetDouble(content,"fib_confluence_enabled");              g_sc.fib_confluence_enabled=(v>=0.5); }
   if(JsonHasKey(content, "fib_confluence_min_confluences"))      { v=JsonGetDouble(content,"fib_confluence_min_confluences");      if(v>=1&&v<=5) g_sc.fib_confluence_min_confluences=(int)v; }
   if(JsonHasKey(content, "fib_confluence_tolerance_atr"))        { v=JsonGetDouble(content,"fib_confluence_tolerance_atr");        if(v>=0.05&&v<=2.0) g_sc.fib_confluence_tolerance_atr=v; }
   if(JsonHasKey(content, "fib_confluence_min_swing_atr"))        { v=JsonGetDouble(content,"fib_confluence_min_swing_atr");        if(v>=0.5&&v<=20.0) g_sc.fib_confluence_min_swing_atr=v; }
   if(JsonHasKey(content, "fib_confluence_lot_factor"))           { v=JsonGetDouble(content,"fib_confluence_lot_factor");           if(v>=0.1&&v<=2.0) g_sc.fib_confluence_lot_factor=v; }
   if(JsonHasKey(content, "fib_confluence_sl_atr_mult"))          { v=JsonGetDouble(content,"fib_confluence_sl_atr_mult");          if(v>=0.5&&v<=5.0) g_sc.fib_confluence_sl_atr_mult=v; }
   if(JsonHasKey(content, "fib_confluence_tp1_atr_mult"))         { v=JsonGetDouble(content,"fib_confluence_tp1_atr_mult");         if(v>=0.1&&v<=5.0) g_sc.fib_confluence_tp1_atr_mult=v; }
   if(JsonHasKey(content, "fib_confluence_tp2_atr_mult"))         { v=JsonGetDouble(content,"fib_confluence_tp2_atr_mult");         if(v>=0.1&&v<=10.0) g_sc.fib_confluence_tp2_atr_mult=v; }
   if(JsonHasKey(content, "fib_confluence_cooldown_seconds"))     { v=JsonGetDouble(content,"fib_confluence_cooldown_seconds");     if(v>=0&&v<=7200) g_sc.fib_confluence_cooldown_seconds=(int)v; }
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
   // 2.7.40 — env-side mirror of MT5 input ScalperLotFactor. Sits at top of combined_lot_factor.
   if(JsonHasKey(lot_json, "scalper_lot_factor")) {
      v = JsonGetDouble(lot_json, "scalper_lot_factor");
      if(v >= 0.05 && v <= 10.0) g_sc.scalper_lot_factor = v;
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
   if(JsonHasKey(lot_json, "wave_confirmation_lot_mult")) {
      v = JsonGetDouble(lot_json, "wave_confirmation_lot_mult");
      if(v >= 1.0 && v <= 10.0) g_sc.wave_confirmation_lot_mult = v;
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
   if(JsonHasKey(content, "max_open_same_direction_bypass_setups")) {
      g_sc.max_open_same_direction_bypass_setups = JsonGetString(content, "max_open_same_direction_bypass_setups");
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
   // 2.7.40 — ScalperLotFactor (multiplier) replaces ScalperLot (absolute). Effective lot now
   //   shows base × factor (pre-combined-factor) so operators see the size-up/down at a glance.
   double _slf_eff_log = (ScalperLotFactor != 1.0) ? ScalperLotFactor : g_sc.scalper_lot_factor;
   PrintFormat("FORGE lot sizing profile: mode=%s source=%s scalper_lot_factor_input=%.2f scalper_lot_factor_env=%.2f effective_factor=%.2f input_trades=%d config_min_legs=%d config_max_legs=%d config_lot=%.2f config_trades_mid=%d effective_lot=%.4f effective_trades=%d",
               lot_source_mode,
               lot_inputs_override_eff ? "inputs" : "config",
               ScalperLotFactor,
               g_sc.scalper_lot_factor,
               _slf_eff_log,
               ScalperTrades,
               g_sc.lot_min_trades,
               g_sc.lot_max_trades,
               g_sc.lot_fixed,
               g_sc.lot_num_trades,
               g_sc.lot_fixed * _slf_eff_log,
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
//+------------------------------------------------------------------+
//| 2.7.36 — Session/killzone helpers (Approach B: manual broker     |
//| offset + EU-DST detection). Works identically in live + tester  |
//| because TimeGMT() is unreliable in MT5 Strategy Tester.          |
//| See docs/research/ICT_KILLZONES.md §5.                           |
//+------------------------------------------------------------------+
int LastSundayOfMonth(int year, int month) {
   MqlDateTime d;
   d.year = year; d.mon = month; d.day = 28;
   d.hour = 0; d.min = 0; d.sec = 0;
   datetime t = StructToTime(d);
   TimeToStruct(t, d);
   int last_day = 28;
   for(int i = 28; i <= 31; i++) {
      d.day = i;
      t = StructToTime(d);
      MqlDateTime check; TimeToStruct(t, check);
      if(check.mon == month) last_day = i;
   }
   d.day = last_day;
   t = StructToTime(d);
   TimeToStruct(t, d);
   return last_day - d.day_of_week;
}

bool IsEU_DST(datetime broker_time) {
   MqlDateTime d; TimeToStruct(broker_time, d);
   if(d.mon < 3 || d.mon > 10) return false;
   if(d.mon > 3 && d.mon < 10) return true;
   if(d.mon == 3) {
      int last_sun = LastSundayOfMonth(d.year, 3);
      if(d.day < last_sun) return false;
      if(d.day > last_sun) return true;
      return d.hour >= 3;
   }
   int last_sun = LastSundayOfMonth(d.year, 10);
   if(d.day < last_sun) return true;
   if(d.day > last_sun) return false;
   return d.hour < 4;
}

int FirstSundayOfMonth(int year, int month) {
   MqlDateTime d;
   d.year = year; d.mon = month; d.day = 1;
   d.hour = 0; d.min = 0; d.sec = 0;
   datetime t = StructToTime(d);
   TimeToStruct(t, d);
   return (d.day_of_week == 0) ? 1 : (1 + (7 - d.day_of_week));
}

bool IsUS_DST(datetime utc) {
   MqlDateTime d; TimeToStruct(utc, d);
   if(d.mon < 3 || d.mon > 11) return false;
   if(d.mon > 3 && d.mon < 11) return true;
   if(d.mon == 3) {
      int second_sun = FirstSundayOfMonth(d.year, 3) + 7;
      if(d.day < second_sun) return false;
      if(d.day > second_sun) return true;
      return d.hour >= 7;
   }
   int first_sun = FirstSundayOfMonth(d.year, 11);
   if(d.day < first_sun) return true;
   if(d.day > first_sun) return false;
   return d.hour < 6;
}

datetime BrokerToNY(datetime broker) {
   int broker_off = IsEU_DST(broker)
                       ? g_sc.broker_gmt_offset_summer
                       : g_sc.broker_gmt_offset_winter;
   datetime utc = broker - broker_off * 3600;
   int ny_off   = IsUS_DST(utc) ? -4 : -5;
   return utc + ny_off * 3600;
}

datetime GetNYTimeNow() {
   return BrokerToNY(TimeCurrent());
}

datetime GetSessionAnchorTime() {
   return g_sc.sessions_ny_anchored ? GetNYTimeNow() : TimeGMT();
}

bool MinuteInWindow(int now_min, int start_min, int end_min) {
   if(start_min < 0 || end_min < 0) return false;
   if(start_min < end_min) return now_min >= start_min && now_min < end_min;
   return now_min >= start_min || now_min < end_min;
}

void GetEffectiveLondonWindow(int &start_min, int &end_min) {
   start_min = (g_sc.london_start_min >= 0) ? g_sc.london_start_min : g_sc.london_start * 60;
   end_min   = (g_sc.london_end_min   >= 0) ? g_sc.london_end_min   : g_sc.london_end   * 60;
}
void GetEffectiveNYWindow(int &start_min, int &end_min) {
   start_min = (g_sc.ny_start_min >= 0) ? g_sc.ny_start_min : g_sc.ny_start * 60;
   end_min   = (g_sc.ny_end_min   >= 0) ? g_sc.ny_end_min   : g_sc.ny_end   * 60;
}
void GetEffectiveAsiaWindow(int &start_min, int &end_min) {
   start_min = g_sc.asia_start_min;
   end_min   = g_sc.asia_end_min;
}

string ComputeCurrentSessionLabel() {
   datetime t = GetSessionAnchorTime();
   MqlDateTime dt; TimeToStruct(t, dt);
   int now_min = dt.hour * 60 + dt.min;
   int ls, le, ns, ne, asn, ae;
   GetEffectiveLondonWindow(ls, le);
   GetEffectiveNYWindow(ns, ne);
   GetEffectiveAsiaWindow(asn, ae);
   // NY checked FIRST so when ranges overlap (legacy default), NY wins for the
   // overlap window instead of LONDON always winning.
   if(MinuteInWindow(now_min, ns, ne)) return "NY";
   if(MinuteInWindow(now_min, ls, le)) return "LONDON";
   if(asn >= 0 && ae >= 0) {
      if(MinuteInWindow(now_min, asn, ae)) return "ASIAN";
      return "OFF";
   }
   return "ASIAN";    // legacy fallback when asia_*_min < 0
}

string ComputeCurrentKillzoneLabel() {
   if(!g_sc.killzones_enabled) return "";
   datetime ny = GetNYTimeNow();
   MqlDateTime dt; TimeToStruct(ny, dt);
   if(dt.day_of_week == 6) return "";
   if(dt.day_of_week == 0 && dt.hour < 17) return "";
   int now_min = dt.hour * 60 + dt.min;
   if(MinuteInWindow(now_min, g_sc.kz_ny_open_start_min,      g_sc.kz_ny_open_end_min))      return "NY_OPEN_KZ";
   if(MinuteInWindow(now_min, g_sc.kz_london_open_start_min,  g_sc.kz_london_open_end_min))  return "LONDON_OPEN_KZ";
   if(MinuteInWindow(now_min, g_sc.kz_london_close_start_min, g_sc.kz_london_close_end_min)) return "LONDON_CLOSE_KZ";
   if(MinuteInWindow(now_min, g_sc.kz_asia_start_min,         g_sc.kz_asia_end_min))         return "ASIAN_KZ";
   return "";
}

int ForgeBrokerGMTOffsetSec() {
   if(MQLInfoInteger(MQL_TESTER) != 0) {
      datetime now = TimeCurrent();
      int hr = IsEU_DST(now) ? g_sc.broker_gmt_offset_summer : g_sc.broker_gmt_offset_winter;
      return hr * 3600;
   }
   return (int)(TimeTradeServer() - TimeGMT());
}

//+------------------------------------------------------------------+
//| 2.7.37 — Populate Layer-4 atom telemetry globals once per tick.  |
//| Called at the top of CheckScalperEntry; cheap (each iX is one    |
//| broker round-trip but cached by MT5 within the bar). Idempotent  |
//| within a single tick via g_eval_last_tick guard.                 |
//+------------------------------------------------------------------+
void ForgeEvalAtoms() {
   datetime now_tc = TimeCurrent();
   if(now_tc == g_eval_last_tick) return;   // already computed this tick
   g_eval_last_tick = now_tc;

   double _buf[1], _buf2[1];

   // ── HTF trend strength components ──
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(point <= 0.0) point = _Point;

   double h1_e20=0, h1_e50=0, h1_atr_v=0;
   if(g_h_ma20 != INVALID_HANDLE && CopyBuffer(g_h_ma20, 0, 0, 1, _buf) == 1) h1_e20 = _buf[0];
   if(g_h_ma50 != INVALID_HANDLE && CopyBuffer(g_h_ma50, 0, 0, 1, _buf) == 1) h1_e50 = _buf[0];
   if(g_h_atr  != INVALID_HANDLE && CopyBuffer(g_h_atr,  0, 0, 1, _buf) == 1) h1_atr_v = _buf[0];
   g_eval_h1_atr = h1_atr_v;

   double h4_e20=0, h4_e50=0, h4_atr_v=0;
   if(g_h4_ma20 != INVALID_HANDLE && CopyBuffer(g_h4_ma20, 0, 0, 1, _buf) == 1) h4_e20 = _buf[0];
   if(g_h4_ma50 != INVALID_HANDLE && CopyBuffer(g_h4_ma50, 0, 0, 1, _buf) == 1) h4_e50 = _buf[0];
   if(g_h4_atr  != INVALID_HANDLE && CopyBuffer(g_h4_atr,  0, 0, 1, _buf) == 1) h4_atr_v = _buf[0];
   g_eval_h4_atr   = h4_atr_v;
   g_eval_h4_trend = (h4_atr_v > 0.0) ? (h4_e20 - h4_e50) / MathMax(h4_atr_v, point) : 0.0;

   // M15 trend (g_mtf[1] = M15 per InitMTFIndicators)
   double m15_e20=0, m15_e50=0, m15_atr_v=0;
   if(g_mtf[1].h_ma20 != INVALID_HANDLE && CopyBuffer(g_mtf[1].h_ma20, 0, 0, 1, _buf) == 1) m15_e20 = _buf[0];
   if(g_mtf[1].h_ma50 != INVALID_HANDLE && CopyBuffer(g_mtf[1].h_ma50, 0, 0, 1, _buf) == 1) m15_e50 = _buf[0];
   if(g_mtf[1].h_atr  != INVALID_HANDLE && CopyBuffer(g_mtf[1].h_atr,  0, 0, 1, _buf) == 1) m15_atr_v = _buf[0];
   g_eval_m15_atr   = m15_atr_v;
   g_eval_m15_trend = (m15_atr_v > 0.0) ? (m15_e20 - m15_e50) / MathMax(m15_atr_v, point) : 0.0;

   // M30 trend (g_mtf[2] = M30)
   double m30_e20=0, m30_e50=0, m30_atr_v=0;
   if(g_mtf[2].h_ma20 != INVALID_HANDLE && CopyBuffer(g_mtf[2].h_ma20, 0, 0, 1, _buf) == 1) m30_e20 = _buf[0];
   if(g_mtf[2].h_ma50 != INVALID_HANDLE && CopyBuffer(g_mtf[2].h_ma50, 0, 0, 1, _buf) == 1) m30_e50 = _buf[0];
   if(g_mtf[2].h_atr  != INVALID_HANDLE && CopyBuffer(g_mtf[2].h_atr,  0, 0, 1, _buf) == 1) m30_atr_v = _buf[0];
   g_eval_m30_trend = (m30_atr_v > 0.0) ? (m30_e20 - m30_e50) / MathMax(m30_atr_v, point) : 0.0;

   // M1 ATR
   if(g_m1_atr != INVALID_HANDLE && CopyBuffer(g_m1_atr, 0, 0, 1, _buf) == 1) g_eval_m1_atr = _buf[0];
   else g_eval_m1_atr = 0.0;

   // ── H1 ADX directional indices ──
   if(g_h_adx != INVALID_HANDLE
      && CopyBuffer(g_h_adx, 1, 0, 1, _buf)  == 1
      && CopyBuffer(g_h_adx, 2, 0, 1, _buf2) == 1) {
      g_eval_h1_di_plus  = _buf[0];
      g_eval_h1_di_minus = _buf2[0];
      g_eval_h1_di_balance = _buf[0] - _buf2[0];
   } else {
      g_eval_h1_di_plus = 0.0; g_eval_h1_di_minus = 0.0; g_eval_h1_di_balance = 0.0;
   }

   // ── H4 RSI + ADX ──
   if(g_h4_rsi != INVALID_HANDLE && CopyBuffer(g_h4_rsi, 0, 0, 1, _buf) == 1) g_eval_h4_rsi = _buf[0];
   else g_eval_h4_rsi = 0.0;
   if(g_h4_adx != INVALID_HANDLE && CopyBuffer(g_h4_adx, 0, 0, 1, _buf) == 1) g_eval_h4_adx = _buf[0];
   else g_eval_h4_adx = 0.0;

   // ── D1 OHLC + current-day high/low/open ──
   g_eval_d1_open  = iOpen (_Symbol, PERIOD_D1, 0);
   g_eval_d1_close = iClose(_Symbol, PERIOD_D1, 0);
   g_eval_day_open = g_eval_d1_open;
   g_eval_day_high = iHigh (_Symbol, PERIOD_D1, 0);
   g_eval_day_low  = iLow  (_Symbol, PERIOD_D1, 0);

   // ── M5 prior-bar OHLC ──
   g_eval_m5_open_1  = iOpen (_Symbol, PERIOD_M5, 1);
   g_eval_m5_high_1  = iHigh (_Symbol, PERIOD_M5, 1);
   g_eval_m5_low_1   = iLow  (_Symbol, PERIOD_M5, 1);
   g_eval_m5_close_1 = iClose(_Symbol, PERIOD_M5, 1);

   // ── M5 OHLC cascades (3 consecutive lower-highs / higher-lows over bars 1..3) ──
   double h1 = iHigh(_Symbol, PERIOD_M5, 1);
   double h2 = iHigh(_Symbol, PERIOD_M5, 2);
   double h3 = iHigh(_Symbol, PERIOD_M5, 3);
   double l1 = iLow (_Symbol, PERIOD_M5, 1);
   double l2 = iLow (_Symbol, PERIOD_M5, 2);
   double l3 = iLow (_Symbol, PERIOD_M5, 3);
   g_eval_m5_lh_cascade = (h1 > 0 && h2 > 0 && h3 > 0 && h1 < h2 && h2 < h3) ? 1 : 0;
   g_eval_m5_hl_cascade = (l1 > 0 && l2 > 0 && l3 > 0 && l1 > l2 && l2 > l3) ? 1 : 0;

   // ── M5 body % (prior bar) ──
   double _body  = MathAbs(g_eval_m5_close_1 - g_eval_m5_open_1);
   double _range = g_eval_m5_high_1 - g_eval_m5_low_1;
   g_eval_m5_body_pct = (_range > 0.0) ? (_body / _range) : 0.0;

   // ── 2.7.37 Group 3 — full per-TF indicator + OHLC + bar-quality inventory ──

   // H1 RSI, ADX, BB
   if(g_h_rsi != INVALID_HANDLE && CopyBuffer(g_h_rsi, 0, 0, 1, _buf) == 1) g_eval_h1_rsi = _buf[0];
   if(g_h_adx != INVALID_HANDLE && CopyBuffer(g_h_adx, 0, 0, 1, _buf) == 1) g_eval_h1_adx = _buf[0];
   if(g_h_bb  != INVALID_HANDLE) {
      if(CopyBuffer(g_h_bb, 1, 0, 1, _buf) == 1) g_eval_h1_bb_u = _buf[0];
      if(CopyBuffer(g_h_bb, 0, 0, 1, _buf) == 1) g_eval_h1_bb_m = _buf[0];
      if(CopyBuffer(g_h_bb, 2, 0, 1, _buf) == 1) g_eval_h1_bb_l = _buf[0];
   }

   // H4 BB
   if(g_h4_bb != INVALID_HANDLE) {
      if(CopyBuffer(g_h4_bb, 1, 0, 1, _buf) == 1) g_eval_h4_bb_u = _buf[0];
      if(CopyBuffer(g_h4_bb, 0, 0, 1, _buf) == 1) g_eval_h4_bb_m = _buf[0];
      if(CopyBuffer(g_h4_bb, 2, 0, 1, _buf) == 1) g_eval_h4_bb_l = _buf[0];
   }

   // M15 RSI + EMAs
   if(g_mtf[1].h_rsi  != INVALID_HANDLE && CopyBuffer(g_mtf[1].h_rsi,  0, 0, 1, _buf) == 1) g_eval_m15_rsi = _buf[0];
   g_eval_m15_ema20 = m15_e20;
   g_eval_m15_ema50 = m15_e50;

   // M30 RSI + ADX + ATR + EMAs
   if(g_mtf[2].h_rsi  != INVALID_HANDLE && CopyBuffer(g_mtf[2].h_rsi,  0, 0, 1, _buf) == 1) g_eval_m30_rsi = _buf[0];
   if(g_mtf[2].h_adx  != INVALID_HANDLE && CopyBuffer(g_mtf[2].h_adx,  0, 0, 1, _buf) == 1) g_eval_m30_adx = _buf[0];
   g_eval_m30_atr   = m30_atr_v;
   g_eval_m30_ema20 = m30_e20;
   g_eval_m30_ema50 = m30_e50;

   // M1 EMAs
   if(g_m1_ma20 != INVALID_HANDLE && CopyBuffer(g_m1_ma20, 0, 0, 1, _buf) == 1) g_eval_m1_ema20 = _buf[0];
   if(g_m1_ma50 != INVALID_HANDLE && CopyBuffer(g_m1_ma50, 0, 0, 1, _buf) == 1) g_eval_m1_ema50 = _buf[0];

   // M5 current-bar OHLC (bar 0 — forming bar)
   g_eval_m5_open_0  = iOpen (_Symbol, PERIOD_M5, 0);
   g_eval_m5_high_0  = iHigh (_Symbol, PERIOD_M5, 0);
   g_eval_m5_low_0   = iLow  (_Symbol, PERIOD_M5, 0);
   g_eval_m5_close_0 = iClose(_Symbol, PERIOD_M5, 0);

   // M15/M30/H1/H4 OHLC (bar 0)
   g_eval_m15_open  = iOpen (_Symbol, PERIOD_M15, 0);
   g_eval_m15_high  = iHigh (_Symbol, PERIOD_M15, 0);
   g_eval_m15_low   = iLow  (_Symbol, PERIOD_M15, 0);
   g_eval_m15_close = iClose(_Symbol, PERIOD_M15, 0);
   g_eval_m30_open  = iOpen (_Symbol, PERIOD_M30, 0);
   g_eval_m30_high  = iHigh (_Symbol, PERIOD_M30, 0);
   g_eval_m30_low   = iLow  (_Symbol, PERIOD_M30, 0);
   g_eval_m30_close = iClose(_Symbol, PERIOD_M30, 0);
   g_eval_h1_open   = iOpen (_Symbol, PERIOD_H1, 0);
   g_eval_h1_high   = iHigh (_Symbol, PERIOD_H1, 0);
   g_eval_h1_low    = iLow  (_Symbol, PERIOD_H1, 0);
   g_eval_h1_close  = iClose(_Symbol, PERIOD_H1, 0);
   g_eval_h4_open   = iOpen (_Symbol, PERIOD_H4, 0);
   g_eval_h4_high   = iHigh (_Symbol, PERIOD_H4, 0);
   g_eval_h4_low    = iLow  (_Symbol, PERIOD_H4, 0);
   g_eval_h4_close  = iClose(_Symbol, PERIOD_H4, 0);

   // M5 bar-quality flags (computed from prior bar OHLC for stable post-bar evaluation)
   double _h0 = iHigh (_Symbol, PERIOD_M5, 1);
   double _l0 = iLow  (_Symbol, PERIOD_M5, 1);
   double _o0 = iOpen (_Symbol, PERIOD_M5, 1);
   double _c0 = iClose(_Symbol, PERIOD_M5, 1);
   double _hp = iHigh (_Symbol, PERIOD_M5, 2);
   double _lp = iLow  (_Symbol, PERIOD_M5, 2);
   double _rg = _h0 - _l0;
   double _rg_prev = _hp - _lp;
   double _bd = MathAbs(_c0 - _o0);
   // Inside bar: prior bar wholly contained within bar-before-prior
   g_eval_m5_inside_bar  = (_h0 < _hp && _l0 > _lp) ? 1 : 0;
   // Outside bar: prior bar engulfs bar-before-prior
   g_eval_m5_outside_bar = (_h0 > _hp && _l0 < _lp) ? 1 : 0;
   // Doji: body < 10% of range
   g_eval_m5_doji        = (_rg > 0.0 && (_bd / _rg) < 0.10) ? 1 : 0;
   // Strong bar: body > 70% of range
   g_eval_m5_strong_bar  = (_rg > 0.0 && (_bd / _rg) > 0.70) ? 1 : 0;
   // Long lower wick: lower wick > 50% of range AND body in upper third (bullish rejection)
   double _lower_wick = MathMin(_o0, _c0) - _l0;
   double _upper_wick = _h0 - MathMax(_o0, _c0);
   g_eval_long_lower_wick = (_rg > 0.0 && (_lower_wick / _rg) > 0.50) ? 1 : 0;
   g_eval_long_upper_wick = (_rg > 0.0 && (_upper_wick / _rg) > 0.50) ? 1 : 0;
   // Range expanding: prior bar range > prior-to-prior range
   g_eval_m5_range_expanding = (_rg_prev > 0.0 && _rg > _rg_prev) ? 1 : 0;
}

//+------------------------------------------------------------------+
//| 2.7.38 — Tier 1 Boolean Composites                              |
//|                                                                  |
//| Each Is*Active() helper evaluates the composite atoms against   |
//| current g_eval_* + globals + regime + h1_trend. ALL guarded by   |
//| FORGE_*_ENABLED config flag — returns false when composite is   |
//| disabled, even if atoms would evaluate TRUE.                    |
//|                                                                  |
//| Specs: docs/FORGE_INDICATOR_ATLAS.md §5                          |
//| Case study: docs/FORGE_CASE_STUDY_2026_03_31_to_04_08.md §4b/c   |
//+------------------------------------------------------------------+

// #1 BLOCK_SELL_IN_CHOP — universal SELL gate for RANGE regime
// Triggers when SELL is being attempted in a RANGE regime while H1 still has
// bull-leaning momentum. Gold retraces UP in chop — chop-SELL has historically
// high loss-rate (Run 22 G5001 −$51).
//
// Note: this helper returns "true if composite is active and would BLOCK".
// Caller emits entry_quality_chop_block_sell when true.
bool IsBlockSellInChopActive(const double h1_trend_strength) {
   if(!g_sc.block_sell_in_chop_enabled) return false;
   if(g_regime_label != "RANGE") return false;
   if(h1_trend_strength <= 0.5) return false;
   // Allow the rare FRACTIONAL_SELL_IN_BULL probe to bypass — that composite
   // is the intentional counter-regime SELL when overbought, not chop-block.
   if(IsFractionalSellInBullActive(h1_trend_strength)) return false;
   return true;
}

// #2 INTRADAY_REVERSAL_TO_SELL_V3 — pivot detection
// Detects the moment within a bullish-macro day when intraday turns to a
// sustained decline. Atoms: V2 (h1≥0.3 + 30/60min cascade + RSI≤40 +
// (HID_BEAR | REG_BEAR | below_bbm) + price<vwap) + V3 OHLC (m5_lh_cascade).
//
// Validated: Apr 2 09:00 crash, Apr 8 12:00 pivot.
// When true: caller blocks BUY setups AND amplifies MOMENTUM_DUMP SELL lot.
bool IsIntradayReversalSellActive(const double h1_trend_strength,
                                   const double m5_rsi,
                                   const double price,
                                   const double m5_bb_m) {
   if(!g_sc.intraday_reversal_sell_enabled) return false;
   if(h1_trend_strength < 0.3) return false;  // macro WAS bull (h1 lags reversal)
   // 30-min M5 decline (close[0] < close[6])
   double c0 = iClose(_Symbol, PERIOD_M5, 0);
   double c6 = iClose(_Symbol, PERIOD_M5, 6);
   double c12 = iClose(_Symbol, PERIOD_M5, 12);
   if(c0 <= 0 || c6 <= 0 || c12 <= 0) return false;
   if(!(c0 < c6)) return false;        // M5 declining 30min
   if(!(c6 < c12)) return false;       // and 60min ago higher → 2hr cascade
   if(m5_rsi > 40.0) return false;
   // RSI divergence OR price below BB middle (structural confirmation)
   bool divergence_or_struct =
      (g_rsi_div_type == "HID_BEAR" || g_rsi_div_type == "REG_BEAR" || c0 < m5_bb_m);
   if(!divergence_or_struct) return false;
   // VWAP confirmation — must be below institutional reference
   if(g_vwap_price > 0 && price >= g_vwap_price) return false;
   // V3 OHLC atom: m5_lh_cascade — 3 consecutive lower-highs
   if(g_eval_m5_lh_cascade != 1) return false;
   return true;
}

// #3 FRACTIONAL_SELL_IN_BULL — fractional counter-regime overbought probe
// NEW setup trigger. Fires when regime is TREND_BULL but M5 is overbought
// with bar-over-bar bearish — pullback expected but bounded by 1.5×ATR SL.
bool IsFractionalSellInBullActive(const double h1_trend_strength) {
   if(!g_sc.fractional_sell_in_bull_enabled) return false;
   if(g_regime_label != "TREND_BULL") return false;
   if(h1_trend_strength < 1.0) return false;
   if(g_psar_state != "ABOVE") return false;
   double buf[1];
   double m5_rsi = (CopyBuffer(g_mtf[0].h_rsi, 0, 0, 1, buf) == 1) ? buf[0] : 0.0;
   if(m5_rsi < 60.0 || m5_rsi > 75.0) return false;
   double m5_adx = (CopyBuffer(g_mtf[0].h_adx, 0, 0, 1, buf) == 1) ? buf[0] : 0.0;
   if(m5_adx < 30.0) return false;
   // Bar-over-bar bearish
   double c0 = iClose(_Symbol, PERIOD_M5, 0);
   double c1 = iClose(_Symbol, PERIOD_M5, 1);
   if(c0 <= 0 || c1 <= 0 || c0 >= c1) return false;
   // Near or above BB upper
   double bb_u = (CopyBuffer(g_mtf[0].h_bb, 1, 0, 1, buf) == 1) ? buf[0] : 0.0;
   double m5_atr = (CopyBuffer(g_mtf[0].h_atr, 0, 0, 1, buf) == 1) ? buf[0] : 0.0;
   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(price < bb_u - 0.2 * m5_atr) return false;
   return true;
}

// 2.7.42 — MA_CROSSOVER event detector (Phase 2). Returns 1 = BUY cross-up
// confirmed on bar[1]'s close, -1 = SELL cross-down confirmed, 0 = no fresh
// event. Uses M5 EMA(20) and EMA(50) buffers via g_mtf[0] handles.
//
// Crossover = sign flip of (ema20 - ema50) between bar[2] and bar[1]:
//   BUY  cross: prev_diff <= 0  AND  now_diff > 0
//   SELL cross: prev_diff >= 0  AND  now_diff < 0
//
// CopyBuffer(handle, 0, start=1, count=2) → buf[0]=bar1 (most recent closed),
// buf[1]=bar2 (one before). Reading shift 1 skips the still-forming bar 0.
int DetectMaCrossoverEvent() {
   if(!g_sc.ma_crossover_enabled) return 0;
   double ema20_buf[2], ema50_buf[2];
   if(CopyBuffer(g_mtf[0].h_ma20, 0, 1, 2, ema20_buf) != 2) return 0;
   if(CopyBuffer(g_mtf[0].h_ma50, 0, 1, 2, ema50_buf) != 2) return 0;
   double diff_now  = ema20_buf[0] - ema50_buf[0];  // bar 1 (most recent closed)
   double diff_prev = ema20_buf[1] - ema50_buf[1];  // bar 2 (one before)
   if(diff_prev <= 0.0 && diff_now > 0.0) return 1;   // BUY cross
   if(diff_prev >= 0.0 && diff_now < 0.0) return -1;  // SELL cross
   return 0;
}

// 2.7.42 — VWAP_REVERSION event detector (Phase 2). Returns 1 = BUY pullback,
// -1 = SELL pullback, 0 = no event. Detects price retracing to VWAP after a
// multi-bar extension in the H1-trend direction.
//
// Logic:
//   1. Current price near VWAP (within min_deviation_atr × 0.5 of VWAP)
//   2. Of the prior `min_extension_bars` M5 closes, at least (N-1) were
//      extended beyond min_deviation_atr × ATR from VWAP (filters chop)
//   3. Extension direction agrees with H1 trend:
//      - extension ABOVE VWAP + H1 bullish → BUY pullback
//      - extension BELOW VWAP + H1 bearish → SELL pullback
//   4. max_deviation_atr guards against runaway extensions (probably trend
//      acceleration, not a pullback opportunity)
int DetectVwapReversionEvent(const double m5_atr, const double h1_trend_strength) {
   if(!g_sc.vwap_reversion_enabled) return 0;
   if(g_vwap_price <= 0.0 || m5_atr <= 0.0) return 0;
   double min_dev = g_sc.vwap_reversion_min_deviation_atr;
   double max_dev = g_sc.vwap_reversion_max_deviation_atr;
   int    N       = g_sc.vwap_reversion_min_extension_bars;
   if(N < 2) N = 2;
   // Step 1: current price near VWAP
   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double dist_now_atr = (price - g_vwap_price) / m5_atr;
   if(MathAbs(dist_now_atr) > min_dev * 0.5) return 0;
   // Step 2: count extended bars in prior N
   int ext_up = 0, ext_dn = 0;
   for(int shift = 1; shift <= N; shift++) {
      double bar_close = iClose(_Symbol, PERIOD_M5, shift);
      if(bar_close <= 0.0) continue;
      double dev_atr = (bar_close - g_vwap_price) / m5_atr;
      if(dev_atr > min_dev && dev_atr < max_dev) ext_up++;
      else if(dev_atr < -min_dev && dev_atr > -max_dev) ext_dn++;
   }
   bool extended_above = (ext_up >= N - 1);
   bool extended_below = (ext_dn >= N - 1);
   // Step 3: direction by H1 trend agreement
   if(extended_above && h1_trend_strength > 0.0) return 1;
   if(extended_below && h1_trend_strength < 0.0) return -1;
   return 0;
}

// 2.7.42 — FIB_CONFLUENCE event detector (Phase 2). Returns 1 = BUY pullback,
// -1 = SELL pullback, 0 = no event. Trend-direction retrace to fib 38.2/50/61.8
// of the recent swing, with at least min_confluences other references (EMA20,
// EMA50, VWAP) within tolerance × ATR of the active fib level.
//
// Uses g_fib_382 / g_fib_50 / g_fib_618 computed at FORGE.mq5 (~5142-5144) and
// g_fib_high/low for the swing-size guard. Throttled at 60s in the fib pass.
int DetectFibConfluenceEvent(const double m5_atr, const double h1_trend_strength) {
   if(!g_sc.fib_confluence_enabled) return 0;
   if(m5_atr <= 0.0) return 0;
   if(g_fib_high <= 0.0 || g_fib_low <= 0.0) return 0;
   if(g_fib_382 <= 0.0 || g_fib_50 <= 0.0 || g_fib_618 <= 0.0) return 0;
   // Step 1: swing-size guard — avoid micro-swings
   double swing_size = g_fib_high - g_fib_low;
   if(swing_size < g_sc.fib_confluence_min_swing_atr * m5_atr) return 0;
   // Step 2: price near any fib level
   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double tol = g_sc.fib_confluence_tolerance_atr * m5_atr;
   double levels[3];
   levels[0] = g_fib_382;
   levels[1] = g_fib_50;
   levels[2] = g_fib_618;
   double active_fib = 0.0;
   for(int i = 0; i < 3; i++) {
      if(MathAbs(price - levels[i]) <= tol) {
         active_fib = levels[i];
         break;
      }
   }
   if(active_fib <= 0.0) return 0;
   // Step 3: count confluences (EMA20, EMA50, VWAP within tol of active_fib)
   int confluences = 0;
   double ema20_buf[1], ema50_buf[1];
   if(CopyBuffer(g_mtf[0].h_ma20, 0, 1, 1, ema20_buf) == 1
      && MathAbs(ema20_buf[0] - active_fib) <= tol) confluences++;
   if(CopyBuffer(g_mtf[0].h_ma50, 0, 1, 1, ema50_buf) == 1
      && MathAbs(ema50_buf[0] - active_fib) <= tol) confluences++;
   if(g_vwap_price > 0.0 && MathAbs(g_vwap_price - active_fib) <= tol) confluences++;
   if(confluences < g_sc.fib_confluence_min_confluences) return 0;
   // Step 4: direction by H1 trend agreement (trend-continuation pullback)
   if(h1_trend_strength > 0.0) return 1;
   if(h1_trend_strength < 0.0) return -1;
   return 0;
}

// #4 BULL_DAY_DIP_BUY_V3 — 16-atom dip-buy on choppy bull days
// NEW setup trigger. V2 atoms (POC + Fib + VWAP + RSI div) plus V3 OHLC atoms
// (dist_high_atr < 2.0 + !m5_lh_cascade + long_lower_wick).
//
// Validated: Mar 31, Apr 1 dip-buy patterns. !m5_lh_cascade alone blocks the
// Apr 8 16:35 BB_BOUNCE BUY −$200 disaster.
bool IsBullDayDipBuyActive(const double h1_trend_strength) {
   if(!g_sc.bull_day_dip_buy_enabled) return false;
   if(h1_trend_strength < 0.5) return false;
   if(g_daily_bear_bias) return false;
   double buf[1];
   double m5_rsi = (CopyBuffer(g_mtf[0].h_rsi, 0, 0, 1, buf) == 1) ? buf[0] : 0.0;
   if(m5_rsi < 30.0 || m5_rsi > 50.0) return false;
   double m5_adx = (CopyBuffer(g_mtf[0].h_adx, 0, 0, 1, buf) == 1) ? buf[0] : 0.0;
   if(m5_adx < 12.0 || m5_adx > 40.0) return false;
   double bb_m = (CopyBuffer(g_mtf[0].h_bb, 0, 0, 1, buf) == 1) ? buf[0] : 0.0;
   double bb_l = (CopyBuffer(g_mtf[0].h_bb, 2, 0, 1, buf) == 1) ? buf[0] : 0.0;
   double m5_atr = (CopyBuffer(g_mtf[0].h_atr, 0, 0, 1, buf) == 1) ? buf[0] : 0.0;
   double price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(price > bb_m + 0.5 * m5_atr) return false;          // structural dip near BB middle
   if(price < bb_l - 0.2 * m5_atr) return false;          // not flushed below band
   if(g_poc_price > 0 && (price - g_poc_price) <= -m5_atr) return false;       // not far below POC
   if(g_fib_50 > 0   && (price - g_fib_50)     <= -m5_atr * 0.5) return false; // not below 50% Fib
   if(g_vwap_price > 0 && (price - g_vwap_price) > 0.5 * m5_atr) return false; // close to VWAP
   if(g_rsi_div_type == "REG_BEAR" || g_rsi_div_type == "HID_BEAR") return false;
   // V3 OHLC atoms
   if((g_eval_day_high - price) >= 2.0 * m5_atr) return false; // within 2×ATR of day high
   if(g_eval_m5_lh_cascade == 1) return false;                  // NOT in lower-high cascade
   if(g_eval_long_lower_wick != 1) return false;                // prior bar rejected from low
   // Session: LONDON or NY (use EA session label, not Python)
   string sess = ComputeCurrentSessionLabel();
   if(sess != "LONDON" && sess != "NY") return false;
   // Re-entry cooldown — 2.7.41 honors regime-aware bypass (m5_adx already computed above)
   if(g_last_chop_buy_exit_time > 0
      && (TimeCurrent() - g_last_chop_buy_exit_time) < g_sc.bull_day_dip_buy_reentry_cooldown_sec
      && !CooldownBypassActive("BUY", "BULL_DAY_DIP_BUY", m5_adx))
      return false;
   return true;
}

void ResetScalperSessionStateIfNeeded() {
   datetime anchor = GetSessionAnchorTime();
   MqlDateTime dt; TimeToStruct(anchor, dt);
   datetime today = StringToTime(StringFormat("%04d.%02d.%02d 00:00", dt.year, dt.mon, dt.day));
   if(today <= 0) return;

   string current_session  = ComputeCurrentSessionLabel();
   string current_killzone = ComputeCurrentKillzoneLabel();

   if(g_scalper_last_reset_day == 0) {
      g_scalper_last_reset_day      = today;
      g_scalper_last_session_label  = current_session;
      g_scalper_last_killzone_label = current_killzone;
      return;
   }

   if(today != g_scalper_last_reset_day) {
      g_scalper_last_reset_day      = today;
      g_scalper_session_trades      = 0;
      g_scalper_killzone_trades     = 0;
      g_scalper_last_entry_bar      = 0;
      g_scalper_last_direction      = "";
      g_scalper_last_direction_time = 0;
      g_first_buy_entry_price       = 0.0;
      g_first_sell_entry_price      = 0.0;
      g_scalper_last_session_label  = current_session;
      g_scalper_last_killzone_label = current_killzone;
      PrintFormat("FORGE SCALPER: daily reset (anchor=%s)",
                  g_sc.sessions_ny_anchored ? "NY" : "UTC");
      return;
   }

   if(g_scalper_last_session_label == "") g_scalper_last_session_label = current_session;
   if(current_session != g_scalper_last_session_label) {
      g_scalper_last_session_label = current_session;
      g_first_buy_entry_price      = 0.0;
      g_first_sell_entry_price     = 0.0;
      PrintFormat("FORGE SCALPER: session change → %s (%s %02d:%02d)",
                  current_session, g_sc.sessions_ny_anchored ? "NY" : "UTC", dt.hour, dt.min);
   }

   if(current_killzone != g_scalper_last_killzone_label) {
      g_scalper_last_killzone_label = current_killzone;
      g_scalper_killzone_start_time = anchor;
      g_scalper_killzone_trades     = 0;
      if(StringLen(current_killzone) > 0) {
         PrintFormat("FORGE SCALPER: killzone → %s (NY %02d:%02d)",
                     current_killzone, dt.hour, dt.min);
      }
   }
}

bool ScalperSessionOK() {
   string s = ComputeCurrentSessionLabel();
   if(s == "OFF") return false;
   if(s == "LONDON" && g_sc.skip_london) return false;
   if(s == "NY"     && g_sc.skip_ny)     return false;
   if(s == "ASIAN"  && g_sc.skip_asian)  return false;
   if(g_sc.killzones_enabled && g_sc.killzones_gate_entries) {
      if(StringLen(ComputeCurrentKillzoneLabel()) == 0) return false;
   }
   return true;
}

bool ScalperTesterSessionOK() {
   if(!g_sc.tester_session_filter) return true;
   string allowed = g_sc.tester_allowed_sessions;
   if(allowed == "ALL" || allowed == "") return true;
   string current_session = ComputeCurrentSessionLabel();
   if(current_session == "OFF") return false;
   string parts[];
   int count = StringSplit(allowed, ',', parts);
   for(int i = 0; i < count; i++) {
      StringTrimLeft(parts[i]); StringTrimRight(parts[i]); StringToUpper(parts[i]);
      if(parts[i] == "NEW_YORK") parts[i] = "NY";
      if(parts[i] == "ASIA")     parts[i] = "ASIAN";
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
      if(m5bar != g_scalper_last_dircool_log_bar) {
         g_scalper_last_dircool_log_bar = m5bar;
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

// ─────────────────────────────────────────────────────────────────────────────
// ComputeDailyBias — Daily Direction Gate state refresh (2.7.27)
//
// PURPOSE: Detect when the D1 (daily) trend is at odds with intended intraday
//   direction. Run 17 G5048 BUY @ 4822.65 lost −$1,666 because no gate saw the
//   multi-day rollover (Apr 14 close 4841 → Apr 16 mid-day 4810). All local M5/M15/H1
//   indicators looked fine. This helper computes the daily SMA slope, daily ATR,
//   and intraday cumulative move; flags bear/bull bias and flip events for the
//   entry chain (Filter 1) and the pending-order cancel logic (Filter 3).
//
// EVALUATION ORDER:
//   1. Per-M5-bar cache check — only recompute when M5 bar rolls over
//   2. D1 SMA(period) at bar 0 and bar lookback_days → slope (pts/lookback period)
//   3. D1 ATR(14) at bar 0
//   4. Slope thresholds → set g_daily_bear_bias / g_daily_bull_bias
//   5. D1 close(0) − open(0) → daily_move; threshold check → intraday flags
//   6. Detect flip: if g_daily_prev_intraday_bull && intraday_bear → flip event
//   7. Persist current intraday state into prev state
//
// PARAMETERS: none — reads g_sc daily_* fields.
//
// RETURNS / SIDE EFFECTS:
//   - Updates globals: g_daily_slope_pts, g_daily_atr_pts, g_daily_move_pts,
//     g_daily_bear_bias, g_daily_bull_bias, g_daily_intraday_bear/bull,
//     g_daily_flip_now, g_daily_prev_intraday_bear/bull.
//   - g_daily_flip_now is a one-tick edge flag — consumers must check it the
//     same tick the function is called.
//
// CHANGELOG:
//   2026-05-11  v2.7.27 — initial implementation (Run 17 G5048 fix).
//               Cached per-M5-bar; reuses iMA/iATR pseudo-handles each call
//               (cost is amortized since the per-bar gate keeps it to ~once/5min).
// ─────────────────────────────────────────────────────────────────────────────
void ComputeDailyBias() {
   // Reset edge flag (consumers see it for one tick only)
   g_daily_flip_now = false;
   if(!g_sc.daily_direction_gate_enabled) {
      g_daily_bear_bias    = false;
      g_daily_bull_bias    = false;
      g_daily_intraday_bear = false;
      g_daily_intraday_bull = false;
      g_daily_prev_intraday_bear = false;
      g_daily_prev_intraday_bull = false;
      return;
   }

   // Cache per M5 bar — the daily numbers don't change on every tick
   datetime m5_now = iTime(_Symbol, PERIOD_M5, 0);
   if(m5_now == g_daily_bias_cache_bar) return;
   g_daily_bias_cache_bar = m5_now;

   int sma_period = g_sc.daily_sma_period;
   int lookback   = g_sc.daily_sma_lookback_days;
   if(sma_period < 2)  sma_period = 2;
   if(lookback   < 1)  lookback   = 1;

   // D1 SMA(period) at bar 0 and bar lookback (using CopyBuffer-equivalent via iMA)
   double sma_buf[];
   ArraySetAsSeries(sma_buf, true);
   int ma_handle = iMA(_Symbol, PERIOD_D1, sma_period, 0, MODE_SMA, PRICE_CLOSE);
   if(ma_handle == INVALID_HANDLE) return;
   int copied = CopyBuffer(ma_handle, 0, 0, lookback + 1, sma_buf);
   IndicatorRelease(ma_handle);
   if(copied < lookback + 1) return;
   double sma_now  = sma_buf[0];
   double sma_back = sma_buf[lookback];
   g_daily_slope_pts = sma_now - sma_back;

   // D1 ATR(14) at bar 0
   double atr_buf[];
   ArraySetAsSeries(atr_buf, true);
   int atr_handle = iATR(_Symbol, PERIOD_D1, 14);
   if(atr_handle == INVALID_HANDLE) return;
   int atr_copied = CopyBuffer(atr_handle, 0, 0, 1, atr_buf);
   IndicatorRelease(atr_handle);
   if(atr_copied < 1) return;
   g_daily_atr_pts = atr_buf[0];

   // Filter 1 — slope bias
   double slope_thresh = g_sc.daily_slope_block_atr * g_daily_atr_pts;
   g_daily_bear_bias = (g_daily_slope_pts < -slope_thresh);
   g_daily_bull_bias = (g_daily_slope_pts >  slope_thresh);

   // Filter 2 — intraday cumulative move from D1 open
   double d1_open  = iOpen (_Symbol, PERIOD_D1, 0);
   double d1_close = iClose(_Symbol, PERIOD_D1, 0);
   g_daily_move_pts = d1_close - d1_open;
   double move_thresh = g_sc.daily_move_block_atr     * g_daily_atr_pts;
   double hyst        = g_sc.daily_move_flip_hysteresis * g_daily_atr_pts;
   // Apply hysteresis only on the bullish→bearish or bearish→bullish flip path —
   // require an extra hyst margin in the new direction before flipping.
   bool was_bull = g_daily_prev_intraday_bull;
   bool was_bear = g_daily_prev_intraday_bear;
   g_daily_intraday_bear = (g_daily_move_pts < -(move_thresh + (was_bull ? hyst : 0.0)));
   g_daily_intraday_bull = (g_daily_move_pts >  (move_thresh + (was_bear ? hyst : 0.0)));
   bool flipped_bull_to_bear = (was_bull && g_daily_intraday_bear);
   bool flipped_bear_to_bull = (was_bear && g_daily_intraday_bull);
   g_daily_flip_now = (flipped_bull_to_bear || flipped_bear_to_bull);
   g_daily_prev_intraday_bear = g_daily_intraday_bear;
   g_daily_prev_intraday_bull = g_daily_intraday_bull;
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

// 2.7.31 — Count M5 bars since last PSAR flip (Run 19 Issue 4 helper).
//   Used by BB_PULLBACK_SCALP gate to distinguish "fresh-flip pullback bottom" entries
//   (PSAR just flipped against trade direction = bounce zone) from "sustained reversal"
//   entries (PSAR on wrong side for many bars = real trend G5028 represented).
//   Returns 0 when PSAR is currently on the opposite side of bar 1 (just flipped).
//   Returns the bar offset where the flip last occurred (1 = previous bar flipped, etc.).
//   Returns lookback (default 10) if no flip found in the window — caller should treat as "stale".
int BarsSincePSARFlip() {
   if(!g_sc.psar_enabled || g_h_psar == INVALID_HANDLE) return 99;
   const int lookback = 10;
   double sar[], cl[];
   ArraySetAsSeries(sar, true);
   ArraySetAsSeries(cl, true);
   if(CopyBuffer(g_h_psar, 0, 0, lookback, sar) < lookback) return 99;
   if(CopyClose(_Symbol, PERIOD_M5, 0, lookback, cl) < lookback) return 99;
   bool cur_below = (sar[0] < cl[0]);
   for(int i = 1; i < lookback; i++) {
      bool i_below = (sar[i] < cl[i]);
      if(i_below != cur_below) return i;
   }
   return lookback;
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
      "killzone TEXT DEFAULT '', "
      "magic INTEGER, "
      "synced INTEGER DEFAULT 0, "
      "macd_histogram REAL, "
      "m15_adx REAL, "
      "lot_factor REAL, "
      // 2.7.37 — Layer-4 atom telemetry (24 cols: closes Decision Stack §6 gap)
      "h4_trend REAL, "
      "m15_trend REAL, "
      "h1_di_balance REAL, "
      "day_open REAL, "
      "day_high REAL, "
      "day_low REAL, "
      "m5_open_1 REAL, "
      "m5_high_1 REAL, "
      "m5_low_1 REAL, "
      "m5_close_1 REAL, "
      "m5_lh_cascade INTEGER DEFAULT 0, "
      "m5_hl_cascade INTEGER DEFAULT 0, "
      "m5_body_pct REAL, "
      "h1_di_plus REAL, "
      "h1_di_minus REAL, "
      "h4_rsi REAL, "
      "h4_adx REAL, "
      "m30_trend REAL, "
      "d1_open REAL, "
      "d1_close REAL, "
      "h1_atr REAL, "
      "h4_atr REAL, "
      "m15_atr REAL, "
      "m1_atr REAL, "
      // 2.7.37 Group 3 — full per-TF indicator + OHLC + bar-quality inventory (45 cols)
      "h1_rsi REAL, h1_adx REAL, h1_bb_u REAL, h1_bb_m REAL, h1_bb_l REAL, "
      "h4_bb_u REAL, h4_bb_m REAL, h4_bb_l REAL, "
      "m15_rsi REAL, m15_ema20 REAL, m15_ema50 REAL, "
      "m30_rsi REAL, m30_adx REAL, m30_atr REAL, m30_ema20 REAL, m30_ema50 REAL, "
      "m1_ema20 REAL, m1_ema50 REAL, "
      "m5_open_0 REAL, m5_high_0 REAL, m5_low_0 REAL, m5_close_0 REAL, "
      "m15_open REAL, m15_high REAL, m15_low REAL, m15_close REAL, "
      "m30_open REAL, m30_high REAL, m30_low REAL, m30_close REAL, "
      "h1_open REAL, h1_high REAL, h1_low REAL, h1_close REAL, "
      "h4_open REAL, h4_high REAL, h4_low REAL, h4_close REAL, "
      "m5_inside_bar INTEGER DEFAULT 0, m5_outside_bar INTEGER DEFAULT 0, "
      "m5_doji INTEGER DEFAULT 0, m5_strong_bar INTEGER DEFAULT 0, "
      "long_lower_wick INTEGER DEFAULT 0, long_upper_wick INTEGER DEFAULT 0, "
      "m5_range_expanding INTEGER DEFAULT 0"
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
   // 2.7.36 — killzone column (additive; silently ignored when already present)
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN killzone TEXT DEFAULT '';");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_killzone ON SIGNALS(killzone);");
   // 2.7.37 — Layer-4 atom telemetry (24 columns; additive ALTERs are no-ops if column exists)
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h4_trend REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m15_trend REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h1_di_balance REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN day_open REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN day_high REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN day_low REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_open_1 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_high_1 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_low_1 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_close_1 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_lh_cascade INTEGER DEFAULT 0;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_hl_cascade INTEGER DEFAULT 0;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_body_pct REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h1_di_plus REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h1_di_minus REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h4_rsi REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h4_adx REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m30_trend REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN d1_open REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN d1_close REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h1_atr REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h4_atr REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m15_atr REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m1_atr REAL;");
   // 2.7.37 Group 3 — full per-TF indicator + OHLC + bar-quality inventory (45 cols)
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h1_rsi REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h1_adx REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h1_bb_u REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h1_bb_m REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h1_bb_l REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h4_bb_u REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h4_bb_m REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h4_bb_l REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m15_rsi REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m15_ema20 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m15_ema50 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m30_rsi REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m30_adx REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m30_atr REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m30_ema20 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m30_ema50 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m1_ema20 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m1_ema50 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_open_0 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_high_0 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_low_0 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_close_0 REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m15_open REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m15_high REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m15_low REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m15_close REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m30_open REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m30_high REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m30_low REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m30_close REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h1_open REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h1_high REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h1_low REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h1_close REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h4_open REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h4_high REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h4_low REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN h4_close REAL;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_inside_bar INTEGER DEFAULT 0;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_outside_bar INTEGER DEFAULT 0;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_doji INTEGER DEFAULT 0;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_strong_bar INTEGER DEFAULT 0;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN long_lower_wick INTEGER DEFAULT 0;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN long_upper_wick INTEGER DEFAULT 0;");
   DatabaseExecute(g_journal_db, "ALTER TABLE SIGNALS ADD COLUMN m5_range_expanding INTEGER DEFAULT 0;");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_h1_di_balance ON SIGNALS(h1_di_balance);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_m5_cascade ON SIGNALS(m5_lh_cascade, m5_hl_cascade);");
   DatabaseExecute(g_journal_db, "CREATE INDEX IF NOT EXISTS idx_sig_m5_inside ON SIGNALS(m5_inside_bar);");
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

   string session  = ComputeCurrentSessionLabel();
   string killzone = ComputeCurrentKillzoneLabel();

   string sql = "INSERT INTO SIGNALS "
      "(time, symbol, setup_type, direction, outcome, gate_reason, "
      "price, spread, atr, rsi, adx, bb_upper, bb_lower, bb_mid, "
      "poc_price, vwap_price, fib_50, rsi_divergence, psar_state, "
      "pattern_score, h1_trend, regime_label, regime_confidence, "
      "adx_trend_regime, high_vol_trend, session, killzone, magic, synced, run_id, "
      "macd_histogram, m15_adx, lot_factor, "
      // 2.7.37 — Layer-4 atom telemetry (24 cols sourced from g_eval_* globals
      // populated by ForgeEvalAtoms() at the top of CheckScalperEntry)
      "h4_trend, m15_trend, h1_di_balance, "
      "day_open, day_high, day_low, "
      "m5_open_1, m5_high_1, m5_low_1, m5_close_1, "
      "m5_lh_cascade, m5_hl_cascade, m5_body_pct, "
      "h1_di_plus, h1_di_minus, h4_rsi, h4_adx, m30_trend, "
      "d1_open, d1_close, h1_atr, h4_atr, m15_atr, m1_atr, "
      // 2.7.37 Group 3 — full inventory (45 cols)
      "h1_rsi, h1_adx, h1_bb_u, h1_bb_m, h1_bb_l, "
      "h4_bb_u, h4_bb_m, h4_bb_l, "
      "m15_rsi, m15_ema20, m15_ema50, "
      "m30_rsi, m30_adx, m30_atr, m30_ema20, m30_ema50, "
      "m1_ema20, m1_ema50, "
      "m5_open_0, m5_high_0, m5_low_0, m5_close_0, "
      "m15_open, m15_high, m15_low, m15_close, "
      "m30_open, m30_high, m30_low, m30_close, "
      "h1_open, h1_high, h1_low, h1_close, "
      "h4_open, h4_high, h4_low, h4_close, "
      "m5_inside_bar, m5_outside_bar, m5_doji, m5_strong_bar, "
      "long_lower_wick, long_upper_wick, m5_range_expanding"
      ") VALUES ("
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
      + "'" + killzone + "', "
      + IntegerToString((long)MagicNumber) + ", 0, "
      + IntegerToString(g_tester_run_id) + ", "
      + DoubleToString(macd_hist, 6) + ", "
      + DoubleToString(m15_adx_val, 2) + ", "
      + DoubleToString(lot_factor_val, 4) + ", "
      // 2.7.37 Layer-4 atoms
      + DoubleToString(g_eval_h4_trend,      4) + ", "
      + DoubleToString(g_eval_m15_trend,     4) + ", "
      + DoubleToString(g_eval_h1_di_balance, 2) + ", "
      + DoubleToString(g_eval_day_open,  _Digits) + ", "
      + DoubleToString(g_eval_day_high,  _Digits) + ", "
      + DoubleToString(g_eval_day_low,   _Digits) + ", "
      + DoubleToString(g_eval_m5_open_1, _Digits) + ", "
      + DoubleToString(g_eval_m5_high_1, _Digits) + ", "
      + DoubleToString(g_eval_m5_low_1,  _Digits) + ", "
      + DoubleToString(g_eval_m5_close_1,_Digits) + ", "
      + IntegerToString(g_eval_m5_lh_cascade) + ", "
      + IntegerToString(g_eval_m5_hl_cascade) + ", "
      + DoubleToString(g_eval_m5_body_pct,    4) + ", "
      + DoubleToString(g_eval_h1_di_plus,     2) + ", "
      + DoubleToString(g_eval_h1_di_minus,    2) + ", "
      + DoubleToString(g_eval_h4_rsi,         2) + ", "
      + DoubleToString(g_eval_h4_adx,         2) + ", "
      + DoubleToString(g_eval_m30_trend,      4) + ", "
      + DoubleToString(g_eval_d1_open,   _Digits) + ", "
      + DoubleToString(g_eval_d1_close,  _Digits) + ", "
      + DoubleToString(g_eval_h1_atr,    _Digits) + ", "
      + DoubleToString(g_eval_h4_atr,    _Digits) + ", "
      + DoubleToString(g_eval_m15_atr,   _Digits) + ", "
      + DoubleToString(g_eval_m1_atr,    _Digits) + ", "
      // 2.7.37 Group 3 values
      + DoubleToString(g_eval_h1_rsi,         2) + ", "
      + DoubleToString(g_eval_h1_adx,         2) + ", "
      + DoubleToString(g_eval_h1_bb_u,   _Digits) + ", "
      + DoubleToString(g_eval_h1_bb_m,   _Digits) + ", "
      + DoubleToString(g_eval_h1_bb_l,   _Digits) + ", "
      + DoubleToString(g_eval_h4_bb_u,   _Digits) + ", "
      + DoubleToString(g_eval_h4_bb_m,   _Digits) + ", "
      + DoubleToString(g_eval_h4_bb_l,   _Digits) + ", "
      + DoubleToString(g_eval_m15_rsi,        2) + ", "
      + DoubleToString(g_eval_m15_ema20, _Digits) + ", "
      + DoubleToString(g_eval_m15_ema50, _Digits) + ", "
      + DoubleToString(g_eval_m30_rsi,        2) + ", "
      + DoubleToString(g_eval_m30_adx,        2) + ", "
      + DoubleToString(g_eval_m30_atr,   _Digits) + ", "
      + DoubleToString(g_eval_m30_ema20, _Digits) + ", "
      + DoubleToString(g_eval_m30_ema50, _Digits) + ", "
      + DoubleToString(g_eval_m1_ema20,  _Digits) + ", "
      + DoubleToString(g_eval_m1_ema50,  _Digits) + ", "
      + DoubleToString(g_eval_m5_open_0, _Digits) + ", "
      + DoubleToString(g_eval_m5_high_0, _Digits) + ", "
      + DoubleToString(g_eval_m5_low_0,  _Digits) + ", "
      + DoubleToString(g_eval_m5_close_0,_Digits) + ", "
      + DoubleToString(g_eval_m15_open,  _Digits) + ", "
      + DoubleToString(g_eval_m15_high,  _Digits) + ", "
      + DoubleToString(g_eval_m15_low,   _Digits) + ", "
      + DoubleToString(g_eval_m15_close, _Digits) + ", "
      + DoubleToString(g_eval_m30_open,  _Digits) + ", "
      + DoubleToString(g_eval_m30_high,  _Digits) + ", "
      + DoubleToString(g_eval_m30_low,   _Digits) + ", "
      + DoubleToString(g_eval_m30_close, _Digits) + ", "
      + DoubleToString(g_eval_h1_open,   _Digits) + ", "
      + DoubleToString(g_eval_h1_high,   _Digits) + ", "
      + DoubleToString(g_eval_h1_low,    _Digits) + ", "
      + DoubleToString(g_eval_h1_close,  _Digits) + ", "
      + DoubleToString(g_eval_h4_open,   _Digits) + ", "
      + DoubleToString(g_eval_h4_high,   _Digits) + ", "
      + DoubleToString(g_eval_h4_low,    _Digits) + ", "
      + DoubleToString(g_eval_h4_close,  _Digits) + ", "
      + IntegerToString(g_eval_m5_inside_bar)  + ", "
      + IntegerToString(g_eval_m5_outside_bar) + ", "
      + IntegerToString(g_eval_m5_doji)        + ", "
      + IntegerToString(g_eval_m5_strong_bar)  + ", "
      + IntegerToString(g_eval_long_lower_wick) + ", "
      + IntegerToString(g_eval_long_upper_wick) + ", "
      + IntegerToString(g_eval_m5_range_expanding)
      + ")";

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

// 2.7.41 — Returns true if `setup_type` appears in the comma-separated
// `max_open_same_direction_bypass_setups` list. Risk-1 setups bypass the
// concurrent-open cap. Match is whole-token (commas as delimiters), case-sensitive.
// Example list value: "BB_BREAKOUT_RETEST,BUY_LIMIT_RECOVERY" — both bypass; raw
// "BB_BREAKOUT" does NOT match "BB_BREAKOUT_RETEST" (different setup_type).
bool SetupBypassesDirectionCap(const string setup_type) {
   if(StringLen(g_sc.max_open_same_direction_bypass_setups) == 0) return false;
   if(StringLen(setup_type) == 0) return false;
   string padded_list = "," + g_sc.max_open_same_direction_bypass_setups + ",";
   string padded_setup = "," + setup_type + ",";
   return (StringFind(padded_list, padded_setup) >= 0);
}

// 2.7.41 — Regime-aware cooldown bypass.
// Returns true when a per-setup cooldown (BB_BREAKOUT same-dir, BB_PULLBACK_SCALP,
// BULL_DAY_DIP_BUY reentry) should be IGNORED for this entry attempt.
//
// Bypass conditions (ALL must hold for the trend-aware path):
//   1. cooldown_bypass_on_tp_with_trend = 1 (master switch, default ON)
//   2. Last TP1 win in this direction was within `cooldown_bypass_window_sec` (10 min default)
//   3. Direction matches g_regime_label (BUY ↔ TREND_BULL, SELL ↔ TREND_BEAR)
//   4. M5 ADX ≥ cooldown_bypass_min_adx (default 25 — trend confirmed)
//   5. ≥ cooldown_bypass_min_refire_sec since last TP1 (anti-flicker, default 5s)
//
// Alternate path: setup_type appears in cooldown_bypass_setups list (unconditional).
// Designed for highest-confidence setups (BB_BREAKOUT_RETEST, BUY_LIMIT_RECOVERY).
//
// Use case (Apr 1 2024 NY rally): BB_BREAKOUT BUY G5001 → TP1 → cooldown active →
//   regime=TREND_BULL, ADX=38, 13s since TP1 → bypass returns TRUE → G5002 fires.
//   Without bypass, the 30-min cooldown would block 4-5 continuation entries.
bool CooldownBypassActive(const string direction, const string setup_type, const double m5_adx) {
   // Unconditional bypass list (checked first — applies regardless of master switch)
   if(StringLen(g_sc.cooldown_bypass_setups) > 0 && StringLen(setup_type) > 0) {
      string padded_list = "," + g_sc.cooldown_bypass_setups + ",";
      string padded_setup = "," + setup_type + ",";
      if(StringFind(padded_list, padded_setup) >= 0) return true;
   }
   if(!g_sc.cooldown_bypass_on_tp_with_trend) return false;
   datetime last_tp = (direction == "BUY") ? g_scalper_last_tp1_buy_time
                    : (direction == "SELL") ? g_scalper_last_tp1_sell_time
                    : (datetime)0;
   if(last_tp == 0) return false;
   long since_tp = (long)(TimeCurrent() - last_tp);
   if(since_tp < (long)g_sc.cooldown_bypass_min_refire_sec) return false;     // anti-flicker
   if(since_tp > (long)g_sc.cooldown_bypass_window_sec)     return false;     // win too stale
   bool with_trend = (direction == "BUY"  && g_regime_label == "TREND_BULL")
                  || (direction == "SELL" && g_regime_label == "TREND_BEAR");
   if(!with_trend) return false;
   if(m5_adx > 0 && m5_adx < g_sc.cooldown_bypass_min_adx) return false;
   return true;
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
                       const double rsi, const double adx,
                       const string setup_type = "") {
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
   //    2.7.41 — Risk-1 setups in `max_open_same_direction_bypass_setups` skip this gate.
   //    Example: BB_BREAKOUT_RETEST + BUY_LIMIT_RECOVERY can fire even when 1 BUY group
   //    is already open, letting high-confidence signals stack past the default cap.
   if(g_sc.max_open_same_direction > 0 && !SetupBypassesDirectionCap(setup_type)) {
      int dir_open = ScalperOpenGroupCountByDirection(direction);
      if(dir_open >= g_sc.max_open_same_direction) {
         JournalRecordSignal("SKIP","entry_quality_direction_cap",setup_type,direction,
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
      datetime _body_bar = iTime(_Symbol, PERIOD_M5, 0);
      bool _body_new = (direction=="SELL") ? (_body_bar != g_scalper_last_body_sell_log_bar)
                                           : (_body_bar != g_scalper_last_body_buy_log_bar);
      if(_body_new) {
         if(direction=="SELL") g_scalper_last_body_sell_log_bar = _body_bar;
         else                  g_scalper_last_body_buy_log_bar  = _body_bar;
         JournalRecordSignal("SKIP","entry_quality_body","",direction,
            SymbolInfoDouble(_Symbol,SYMBOL_BID),0,atr,rsi,adx,bb_upper_now,bb_lower_now,0,0,0,0);
      }
      return false;
   }
   if(g_sc.min_directional_bars > 0 && directional_count < g_sc.min_directional_bars) {
      datetime _dir_bar = iTime(_Symbol, PERIOD_M5, 0);
      bool _dir_new = (direction=="SELL") ? (_dir_bar != g_scalper_last_dir_sell_log_bar)
                                          : (_dir_bar != g_scalper_last_dir_buy_log_bar);
      if(_dir_new) {
         if(direction=="SELL") g_scalper_last_dir_sell_log_bar = _dir_bar;
         else                  g_scalper_last_dir_buy_log_bar  = _dir_bar;
         JournalRecordSignal("SKIP","entry_quality_direction","",direction,
            SymbolInfoDouble(_Symbol,SYMBOL_BID),0,atr,rsi,adx,bb_upper_now,bb_lower_now,0,0,0,0);
      }
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
   // 2.7.37 — Populate Layer-4 atom telemetry globals FIRST, before any
   // JournalRecordSignal call (including the pre-trigger SKIPs that fire
   // before the per-bar/session/spread/cooldown gates). Codex v2.7.37
   // FAIL #1: pre-2.7.37 call site at end of CheckScalperEntry left
   // pre-trigger SKIPs with stale g_eval_* from the previous tick.
   ForgeEvalAtoms();
   // 2.7.27 — Daily Direction Gate refresh + Filter 3 cancel-pending-on-flip.
   //   ComputeDailyBias() is cached per M5 bar; CancelPendingOnDailyFlip reads the
   //   one-tick g_daily_flip_now edge flag and cancels stale pending orders in our
   //   magic range. Both are no-ops when daily_direction_gate_enabled=false.
   if(g_sc.daily_direction_gate_enabled) {
      ComputeDailyBias();
      CancelPendingOnDailyFlip();
   }
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
         MqlDateTime _so; TimeToStruct(GetSessionAnchorTime(), _so);
         PrintFormat("FORGE SCALPER: skip gate=session_off anchor=%s %02d:%02d (no trades)",
                     g_sc.sessions_ny_anchored ? "NY" : "UTC", _so.hour, _so.min);
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
      datetime m5b_og = iTime(_Symbol, PERIOD_M5, 0);
      if(m5b_og != g_scalper_last_opengroups_log_bar) {
         g_scalper_last_opengroups_log_bar = m5b_og;
      PrintFormat("FORGE SCALPER: skip gate=open_groups open=%d max=%d", open_groups, g_sc.max_open_groups);
         JournalRecordSignal("SKIP","open_groups","","",SymbolInfoDouble(_Symbol,SYMBOL_BID),spread,0,0,0,0,0,0,0,0,0);
      }
      return;
   }
   if(MQLInfoInteger(MQL_TESTER) == 0 && g_scalper_session_trades >= g_sc.max_trades_per_session) {
      datetime m5b_sc = iTime(_Symbol, PERIOD_M5, 0);
      if(m5b_sc != g_scalper_last_sesscap_log_bar) {
         g_scalper_last_sesscap_log_bar = m5b_sc;
      PrintFormat("FORGE SCALPER: skip gate=session_trade_cap trades=%d max=%d",
                  g_scalper_session_trades, g_sc.max_trades_per_session);
         JournalRecordSignal("SKIP","session_trade_cap","","",SymbolInfoDouble(_Symbol,SYMBOL_BID),spread,0,0,0,0,0,0,0,0,0);
      }
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

   // 2.7.37 — ForgeEvalAtoms() already called at top of CheckNativeScalperSetups
   // (idempotent via g_eval_last_tick guard). Atoms are now populated for every
   // SKIP/TAKEN INSERT including the pre-trigger gates (news/atr/body/session_off/etc).

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
   // HID_BULL divergence override (2.7.13): when RSI shows hidden bullish divergence, M5 ADX spike is
   // misleading — congestion zone, not a real trend. If M15 ADX confirms ranging (< bounce_adx_max),
   // override the M5 ADX spike so BB_BOUNCE BUY can evaluate at the same support level.
   // Run11 May4 17:10: M5=37.4 would block bounce, M15=16.7 confirms ranging → override → BUY hits TP1+TP2.
   double _m15adx_bounce[1];
   double m15_adx_bounce = (g_mtf[1].h_adx != INVALID_HANDLE
                             && CopyBuffer(g_mtf[1].h_adx, 0, 0, 1, _m15adx_bounce) == 1)
                            ? _m15adx_bounce[0] : m5_adx;
   bool hid_bull_active = (g_sc.rsi_div_enabled && g_rsi_div_type == "HID_BULL");
   double bounce_adx_max_eff = g_sc.bounce_adx_max;
   if(hid_bull_active && m15_adx_bounce < g_sc.bounce_adx_max) {
      // M15 confirms ranging → raise effective cap so M5 spike doesn't block the bounce
      bounce_adx_max_eff = MathMax(g_sc.bounce_adx_max, m5_adx + 1.0);
   }
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
   //
   // 2.7.29 — H1-strong override clause (Run 18 Issue 1 fix).
   //   The legacy 3 clauses require unanimous H1+H4 agreement. H4 EMA20-EMA50 lags H1 by 3-5 hours
   //   after a regime turn, so perfect M5/H1 setups get capped at 5 legs (native_legs_max_when_unclear)
   //   because regime stays RANGE.
   //   Run 18 G5001 Apr 1 08:40: h1_trend=+2.15, m5_adx=40.1, but regime=RANGE → 5 legs fired
   //     when 10 would have been appropriate (market then moved +41 pts in 2 hours = 8×ATR).
   //   Override: when |h1_trend| >= regime_h1_override_factor × trend_thr_eff AND m5_adx >= regime_h1_override_adx_min,
   //     force TREND_BULL or TREND_BEAR regardless of H4.
   //   Default OFF: regime_h1_override_factor=0 → override clause never triggers, behavior matches legacy.
   //   Operator opt-in via FORGE_REGIME_H1_OVERRIDE_FACTOR=2.0 in .env.
   // 2.7.30 — tester/live parity: classifier runs in BOTH modes per operator mandate.
   //   "I want the regime calculation to be fix for both live and testing — this sim is useless
   //    if testing results and config for logic evaluation cannot be applied to live trades."
   //   Backtest tuning of FORGE_REGIME_H1_OVERRIDE_FACTOR / ADX_MIN must transfer to live as-is.
   //   In live, BRIDGE may also write regime_label into the JSON (advisory) — this inline
   //   classifier is now authoritative and overwrites it every tick.
   if(high_vol_trend)                              g_regime_label = "VOLATILE";
   else if(h1_bull && (h4_bull || h4_flat))        g_regime_label = "TREND_BULL";
   else if(h1_bear && (h4_bear || h4_flat))        g_regime_label = "TREND_BEAR";
   // 2.7.29 — H1-strong override: unlock TREND_BULL/TREND_BEAR when M5+H1 unambiguously trending
   //          even if H4 EMA hasn't caught up yet.
   else if(g_sc.regime_h1_override_factor > 0.0
           && m5_adx >= g_sc.regime_h1_override_adx_min
           && MathAbs(h1_trend_strength) >= g_sc.regime_h1_override_factor * trend_thr_eff) {
      g_regime_label = (h1_trend_strength > 0.0) ? "TREND_BULL" : "TREND_BEAR";
   }
   else                                             g_regime_label = "RANGE";
   g_regime_confidence = 1.0;

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
         // 2.7.27 — Daily Direction Gate Filter 1 (Run 17 G5048 fix, applied to BB_BOUNCE for symmetry).
         //   Even though G5048 was a BB_BREAKOUT, the Apr 15 14:46 SELL cluster of BB_BOUNCEs lost
         //   when daily was rolling bullish — so the same daily check applies here.
         if(g_sc.daily_direction_gate_enabled) ComputeDailyBias();
         // 2.7.38 — INTRADAY_REVERSAL_TO_SELL_V3 composite block. When active, ALL
         //   BUY setups are blocked because intraday flipped from bull to sustained decline.
         if(IsIntradayReversalSellActive(h1_trend_strength, m5_rsi, mid, m5_bb_m)) {
            datetime _irb_bar = iTime(_Symbol, PERIOD_M5, 0);
            if(_irb_bar != g_last_intraday_reversal_log_bar) {
               g_last_intraday_reversal_log_bar = _irb_bar;
               JournalRecordSignal("SKIP","entry_quality_intraday_reversal_buy_block","BB_BOUNCE","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else
         if(g_sc.daily_direction_gate_enabled && g_daily_bear_bias) {
            datetime _dbb_bar_bb = iTime(_Symbol, PERIOD_M5, 0);
            if(_dbb_bar_bb != g_scalper_last_dailybias_buy_log_bar) {
               g_scalper_last_dailybias_buy_log_bar = _dbb_bar_bb;
               JournalRecordSignal("SKIP","entry_quality_daily_bear_block_buy","BB_BOUNCE","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else
         // 2.7.26 — PSAR alignment gate for BB_BOUNCE BUY (mirror of v2.7.20 BB_BREAKOUT gate).
         // Run 17 G5028 (Apr 10 18:45 BB_BOUNCE BUY @ 4766.27 PSAR=ABOVE) misread the signal — PSAR was
         // already bearish (dots above price), but BB_BOUNCE BUY fired anyway because PSAR gate was
         // BB_BREAKOUT-only. Price then crashed −12 pts. Block BUY when PSAR is not stable BELOW.
         if(g_sc.breakout_require_psar_align && g_sc.psar_enabled && g_psar_state != "BELOW") {
            // 2.7.31 — BB_PULLBACK_SCALP BUY fork (Run 19 Issue 4, Task #53).
            //   Before logging the PSAR-misalign SKIP, check if this is a "fresh PSAR flip" + h1-trend-aligned
            //   pullback bottom — in which case fire as BB_PULLBACK_SCALP with tight scalp geometry instead.
            //   G5028 fails this fork because: (a) h1_trend was negative on Apr 10 18:45 (downtrend, not pullback)
            //   AND (b) PSAR had been ABOVE for many bars (sustained), not a fresh flip.
            int psar_flip_age = BarsSincePSARFlip();
            datetime _now_psb = TimeCurrent();
            bool pullback_buy_ok = g_sc.pullback_scalp_enabled
               && psar_flip_age <= g_sc.pullback_scalp_fresh_flip_bars
               && h1_trend_strength >= g_sc.bounce_min_h1_trend           // must be pullback in bull trend
               && m5_adx < g_sc.pullback_scalp_max_adx                    // exhausting, not accelerating
               && (g_sc.pullback_scalp_cooldown_seconds <= 0
                   || g_pullback_scalp_last_buy_time == 0
                   || (_now_psb - g_pullback_scalp_last_buy_time) >= g_sc.pullback_scalp_cooldown_seconds
                   || CooldownBypassActive("BUY", "BB_PULLBACK_SCALP", m5_adx));  // 2.7.41 — bypass when last TP1 + TREND_BULL + ADX ok
            if(pullback_buy_ok) {
         direction = "BUY";
               double pb_sl  = NormalizeDouble(bid - m5_atr * g_sc.pullback_scalp_sl_atr_mult, _Digits);
               double pb_tp1 = NormalizeDouble(ask + m5_atr * g_sc.pullback_scalp_tp1_atr_mult, _Digits);
               double pb_tp2 = NormalizeDouble(ask + m5_atr * g_sc.pullback_scalp_tp2_atr_mult, _Digits);
               sl  = pb_sl;
               tp1 = pb_tp1;
               tp2 = pb_tp2;
               setup_type = "BB_PULLBACK_SCALP";
               g_pullback_scalp_last_buy_time = _now_psb;
               PrintFormat("FORGE 2.7.31: BB_PULLBACK_SCALP BUY fired @ %.2f (h1_trend=%.2f, ADX=%.1f, psar_flip_age=%d)",
                           ask, h1_trend_strength, m5_adx, psar_flip_age);
            } else {
               datetime _psb_bar = iTime(_Symbol, PERIOD_M5, 0);
               if(_psb_bar != g_scalper_last_psar_log_bar) {
                  g_scalper_last_psar_log_bar = _psb_bar;
                  JournalRecordSignal("SKIP","entry_quality_psar_misalign_buy","BB_BOUNCE","BUY",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
               }
            }
         } else {
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
         } // end PSAR-ok-buy-bounce else
      }
      // SELL: price near BB upper + RSI overbought + H1 not bullish
      else if(mid >= m5_bb_u - proximity && m5_rsi > g_sc.bounce_rsi_sell_min
              && bounce_tf_sell_ok && h4_ok_sell && fib_ok_sell && rsi_div_sell_bounce && sell_reject && sell_bar0_ok && liquidity_ok
              && !bounce_htf_blocks_sell) {
         // 2.7.27 — Daily Direction Gate Filter 1 SELL side (mirror of BUY block above).
         //   Block BB_BOUNCE SELL when D1 SMA slope is positive beyond threshold (multi-day rip).
         if(g_sc.daily_direction_gate_enabled) ComputeDailyBias();
         // 2.7.38 — BLOCK_SELL_IN_CHOP composite. Block SELL on RANGE-regime days
         //   with H1 still bull-leaning (gold retraces UP in chop). Applied here
         //   before daily-bias gate so chop-block fires first when both apply.
         if(IsBlockSellInChopActive(h1_trend_strength)) {
            datetime _cbs_bar = iTime(_Symbol, PERIOD_M5, 0);
            if(_cbs_bar != g_last_chop_block_sell_log_bar) {
               g_last_chop_block_sell_log_bar = _cbs_bar;
               JournalRecordSignal("SKIP","entry_quality_chop_block_sell","BB_BOUNCE","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else
         if(g_sc.daily_direction_gate_enabled && g_daily_bull_bias) {
            datetime _dbb_bar_bs = iTime(_Symbol, PERIOD_M5, 0);
            if(_dbb_bar_bs != g_scalper_last_dailybias_sell_log_bar) {
               g_scalper_last_dailybias_sell_log_bar = _dbb_bar_bs;
               JournalRecordSignal("SKIP","entry_quality_daily_bull_block_sell","BB_BOUNCE","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else
         // 2.7.26 — PSAR alignment gate for BB_BOUNCE SELL (mirror of BUY). Block SELL when PSAR is not stable ABOVE.
         if(g_sc.breakout_require_psar_align && g_sc.psar_enabled && g_psar_state != "ABOVE") {
            // 2.7.31 — BB_PULLBACK_SCALP SELL fork (mirror of BUY fork above).
            //   Fires when PSAR just flipped BELOW (fresh) + h1_trend negative (bearish pullback in
            //   downtrend) + ADX low (exhausting). Recovers Run 17 SELL winners blocked Apr 2/Apr 7.
            int psar_flip_age_s = BarsSincePSARFlip();
            datetime _now_pss = TimeCurrent();
            bool pullback_sell_ok = g_sc.pullback_scalp_enabled
               && psar_flip_age_s <= g_sc.pullback_scalp_fresh_flip_bars
               && h1_trend_strength <= -g_sc.bounce_min_h1_trend          // pullback in bear trend
               && m5_adx < g_sc.pullback_scalp_max_adx
               && (g_sc.pullback_scalp_cooldown_seconds <= 0
                   || g_pullback_scalp_last_sell_time == 0
                   || (_now_pss - g_pullback_scalp_last_sell_time) >= g_sc.pullback_scalp_cooldown_seconds
                   || CooldownBypassActive("SELL", "BB_PULLBACK_SCALP", m5_adx));  // 2.7.41 — bypass when last TP1 + TREND_BEAR + ADX ok
            if(pullback_sell_ok) {
         direction = "SELL";
               double pb_sl_s  = NormalizeDouble(ask + m5_atr * g_sc.pullback_scalp_sl_atr_mult, _Digits);
               double pb_tp1_s = NormalizeDouble(bid - m5_atr * g_sc.pullback_scalp_tp1_atr_mult, _Digits);
               double pb_tp2_s = NormalizeDouble(bid - m5_atr * g_sc.pullback_scalp_tp2_atr_mult, _Digits);
               sl  = pb_sl_s;
               tp1 = pb_tp1_s;
               tp2 = pb_tp2_s;
               setup_type = "BB_PULLBACK_SCALP";
               g_pullback_scalp_last_sell_time = _now_pss;
               PrintFormat("FORGE 2.7.31: BB_PULLBACK_SCALP SELL fired @ %.2f (h1_trend=%.2f, ADX=%.1f, psar_flip_age=%d)",
                           bid, h1_trend_strength, m5_adx, psar_flip_age_s);
            } else {
               datetime _pss_bar = iTime(_Symbol, PERIOD_M5, 0);
               if(_pss_bar != g_scalper_last_psar_log_bar) {
                  g_scalper_last_psar_log_bar = _pss_bar;
                  JournalRecordSignal("SKIP","entry_quality_psar_misalign_sell","BB_BOUNCE","SELL",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
               }
            }
         } else {
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
         } // end PSAR-ok-sell-bounce else
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

      // 2.7.27 — Daily Direction Gate refresh (cached per M5 bar).
      //   Populates g_daily_bear_bias / g_daily_bull_bias / g_daily_flip_now.
      //   When disabled in config, all flags remain false → no behavior change.
      if(g_sc.daily_direction_gate_enabled) ComputeDailyBias();

      // BUY breakout: close above upper BB + RSI strong + aligned
      // rsi_buy_min=40: Cardwell Bull Support zone (RSI 40–80 in uptrend; 40 = dip re-entry floor)
      if(prev_close > (m5_bb_u + breakout_buffer) && m5_rsi > g_sc.breakout_rsi_buy_min
         && m5_bull && m15_ok_buy && h1_ok_buy && h4_ok_buy && strict_breakout_buy_ok) {
         // 2.7.27 — Daily Direction Gate Filter 1 (Run 17 G5048 fix).
         //   Block BUY when D1 SMA slope is negative beyond threshold (multi-day rollover).
         //   Throttled per M5 bar to avoid journal flooding.
         // 2.7.38 — INTRADAY_REVERSAL_TO_SELL_V3 composite block. When active, ALL BUY blocked.
         if(IsIntradayReversalSellActive(h1_trend_strength, m5_rsi, mid, m5_bb_m)) {
            datetime _irb_bar_bk = iTime(_Symbol, PERIOD_M5, 0);
            if(_irb_bar_bk != g_last_intraday_reversal_log_bar) {
               g_last_intraday_reversal_log_bar = _irb_bar_bk;
               JournalRecordSignal("SKIP","entry_quality_intraday_reversal_buy_block","BB_BREAKOUT","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else
         if(g_sc.daily_direction_gate_enabled && g_daily_bear_bias) {
            datetime _dbb_bar_b = iTime(_Symbol, PERIOD_M5, 0);
            if(_dbb_bar_b != g_scalper_last_dailybias_buy_log_bar) {
               g_scalper_last_dailybias_buy_log_bar = _dbb_bar_b;
               JournalRecordSignal("SKIP","entry_quality_daily_bear_block_buy","BB_BREAKOUT","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else if(m5_rsi >= g_sc.breakout_rsi_buy_ceil) {
            // Per-M5-bar throttle (2.7.15): prior runs flooded thousands of ticks per bar,
            // corrupting Q9 gate-precision math. Same pattern as direction/body throttles.
            datetime _rbc_bar = iTime(_Symbol, PERIOD_M5, 0);
            if(_rbc_bar != g_scalper_last_rsibuyceil_log_bar) {
               g_scalper_last_rsibuyceil_log_bar = _rbc_bar;
               JournalRecordSignal("SKIP","entry_quality_rsi_buy_ceil","BB_BREAKOUT","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
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
            // H1 MACD histogram gate (2.7.17, Run 15 G5002 fix): block BUY when H1 MACD histogram < 0 (H1 momentum stalling).
            // Mirror of require_h1_macd_sell — Run 15 G5002 lost -$400 with h1_trend=+2.139 (max bullish DI) but H1 MACD=-2.11
            // (momentum stalled). DI says "trend up", MACD says "momentum gone" → classic trend-exhaustion BUY-the-top trap.
            bool h1_macd_buy_ok = true;
            if(h1_di_ok && macd_buy_ok && h4_rsi_buy_ok && h4_adx_buy_ok
               && g_sc.breakout_require_h1_macd_buy && g_h_macd != INVALID_HANDLE) {
               double _h1mb[1], _h1sb[1];
               if(CopyBuffer(g_h_macd, 0, 0, 1, _h1mb) == 1 && CopyBuffer(g_h_macd, 1, 0, 1, _h1sb) == 1) {
                  double _h1_hist_b = _h1mb[0] - _h1sb[0];
                  if(_h1_hist_b < 0.0) {
                     datetime _h1mcdb_bar = iTime(_Symbol, PERIOD_M5, 0);
                     if(_h1mcdb_bar != g_scalper_last_h1macdbuy_log_bar) {
                        g_scalper_last_h1macdbuy_log_bar = _h1mcdb_bar;
                        JournalRecordSignal("SKIP","entry_quality_h1_macd_buy","BB_BREAKOUT","BUY",
                           mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0,_h1_hist_b);
                     }
                     h1_macd_buy_ok = false;
                  }
               }
            }
            // BB_BREAKOUT same-direction cooldown (2.7.17, Run 15 G5002 fix): block consecutive BB_BREAKOUT BUY entries
            // within N seconds of the prior same-direction BB_BREAKOUT TAKEN. Targets the "double-tap stack onto fading
            // momentum" failure mode. Set FORGE_BREAKOUT_SAME_DIR_COOLDOWN_SECONDS=900 (15 min) in .env to enable.
            bool bo_cooldown_buy_ok = true;
            if(h1_di_ok && macd_buy_ok && h4_rsi_buy_ok && h4_adx_buy_ok && h1_macd_buy_ok
               && g_sc.breakout_same_dir_cooldown_seconds > 0
               && g_scalper_last_bb_breakout_buy > 0
               && (TimeCurrent() - g_scalper_last_bb_breakout_buy) < g_sc.breakout_same_dir_cooldown_seconds
               && !CooldownBypassActive("BUY", "BB_BREAKOUT", m5_adx)) {  // 2.7.41 — bypass on TP+TREND_BULL+ADX
               datetime _boc_bar = iTime(_Symbol, PERIOD_M5, 0);
               if(_boc_bar != g_scalper_last_bocooldown_log_bar) {
                  g_scalper_last_bocooldown_log_bar = _boc_bar;
                  JournalRecordSignal("SKIP","entry_quality_breakout_cooldown","BB_BREAKOUT","BUY",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
               }
               bo_cooldown_buy_ok = false;
            }
            // 2.7.19 — Failed-breakout-pullback gate (Run 15 G5013 -$1086 / G5015 -$875 fix):
            // Block BUY when (a) an atr_ext SKIP fired within last N bars at a HIGHER price than entry,
            // AND (b) RSI peaked >= min_peak_rsi in the lookback window, AND (c) current RSI is below
            // peak by at least min_rsi_drop. Catches the "fake breakout / buy the pullback / reversal" pattern.
            // 2.7.20 — added same-bar hard-block (canonical wick-rejection guard, MQL5 Liquidity Sweep article):
            // when atr_ext SKIP fired in the CURRENT M5 bar, hard-block BUY regardless of RSI (catches G5018/G5022).
            bool brk_failed_buy_ok = true;
            if(h1_di_ok && macd_buy_ok && h4_rsi_buy_ok && h4_adx_buy_ok && h1_macd_buy_ok && bo_cooldown_buy_ok
               && g_sc.breakout_failed_gate_enabled
               && g_scalper_last_atrext_skip_bar_buy > 0) {
               datetime _bf_now_bar = iTime(_Symbol, PERIOD_M5, 0);
               int _bf_bars_since = (int)((_bf_now_bar - g_scalper_last_atrext_skip_bar_buy) / PeriodSeconds(PERIOD_M5));
               bool _bf_recent      = (_bf_bars_since >= 0 && _bf_bars_since <= g_sc.breakout_failed_lookback_bars);
               bool _bf_lower_entry = (mid < g_scalper_last_atrext_skip_price_buy);
               // 2.7.20 — Same-bar hard block: if atr_ext SKIP fired in the same M5 bar as this entry attempt,
               // block BUY unconditionally. The bar has already shown wick-rejection structure.
               if(_bf_bars_since == 0 && _bf_lower_entry && g_sc.breakout_failed_same_bar_hard_block) {
                  if(_bf_now_bar != g_scalper_last_brkfailed_log_bar) {
                     g_scalper_last_brkfailed_log_bar = _bf_now_bar;
                     JournalRecordSignal("SKIP","entry_quality_breakout_failed_samebar","BB_BREAKOUT","BUY",
                        mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0,g_scalper_last_atrext_skip_price_buy);
                  }
                  brk_failed_buy_ok = false;
               } else if(_bf_recent && _bf_lower_entry && g_mtf[0].h_rsi != INVALID_HANDLE) {
                  // Compute RSI peak over last lookback_bars (current bar + history)
                  double _bf_rsi_peak = m5_rsi;
                  int _bf_lb = g_sc.breakout_failed_lookback_bars;
                  if(_bf_lb > 20) _bf_lb = 20;
                  double _bf_rbuf[20];
                  if(CopyBuffer(g_mtf[0].h_rsi, 0, 0, _bf_lb, _bf_rbuf) == _bf_lb) {
                     for(int _bf_i = 0; _bf_i < _bf_lb; _bf_i++) {
                        if(_bf_rbuf[_bf_i] > _bf_rsi_peak) _bf_rsi_peak = _bf_rbuf[_bf_i];
                     }
                  }
                  bool _bf_rsi_rollover = (_bf_rsi_peak >= g_sc.breakout_failed_min_peak_rsi)
                                          && (m5_rsi <= _bf_rsi_peak - g_sc.breakout_failed_min_rsi_drop);
                  if(_bf_rsi_rollover) {
                     if(_bf_now_bar != g_scalper_last_brkfailed_log_bar) {
                        g_scalper_last_brkfailed_log_bar = _bf_now_bar;
                        JournalRecordSignal("SKIP","entry_quality_breakout_failed","BB_BREAKOUT","BUY",
                           mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0,_bf_rsi_peak);
                     }
                     brk_failed_buy_ok = false;
                  }
               }
            }
            // 2.7.20 — PSAR alignment gate (LiteFinance: "wait for first/second dot after flip").
            // BUY requires psar_state == BELOW (stable bullish regime). Block FLIP_BEAR/FLIP_BULL transitional
            // states (G5036 at FLIP_BULL) and ABOVE (G5035 had FLIP_BEAR — bear flip just printed).
            bool psar_align_buy_ok = true;
            if(h1_di_ok && macd_buy_ok && h4_rsi_buy_ok && h4_adx_buy_ok && h1_macd_buy_ok && bo_cooldown_buy_ok && brk_failed_buy_ok
               && g_sc.breakout_require_psar_align && g_sc.psar_enabled) {
               if(g_psar_state != "BELOW") {
                  datetime _ps_bar = iTime(_Symbol, PERIOD_M5, 0);
                  if(_ps_bar != g_scalper_last_psar_log_bar) {
                     g_scalper_last_psar_log_bar = _ps_bar;
                     JournalRecordSignal("SKIP","entry_quality_psar_misalign_buy","BB_BREAKOUT","BUY",
                        mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
                  }
                  psar_align_buy_ok = false;
               }
            }
            // News RSI tighten — independent additive check (last line of defense before entry)
            bool nf_buy_ok = true;
            if(h1_di_ok && macd_buy_ok && h4_rsi_buy_ok && h4_adx_buy_ok && h1_macd_buy_ok && bo_cooldown_buy_ok && brk_failed_buy_ok && psar_align_buy_ok
               && g_nf_eff_rsi_buy_ceil < g_sc.breakout_rsi_buy_ceil && m5_rsi >= g_nf_eff_rsi_buy_ceil) {
               JournalRecordSignal("SKIP","entry_quality_news_rsi_tighten","BB_BREAKOUT","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
               nf_buy_ok = false;
            }
            if(h1_di_ok && macd_buy_ok && h4_rsi_buy_ok && h4_adx_buy_ok && h1_macd_buy_ok && bo_cooldown_buy_ok && brk_failed_buy_ok && psar_align_buy_ok && nf_buy_ok)
            { // Breakout SL is pure ATR — no structural widening (OB widening blows out RR at TP4).
            // 2.7.18 — BUY-only SL override: when breakout_buy_sl_atr_mult > 0, replace base mult to widen
            // BUY SL against SL-hunt wicks (Run 15 G5015: 2.49×ATR adverse wick wiped 11 legs at 2.0×ATR SL,
            // price reversed cleanly to entry within 70 min). SELL path uses the unmodified breakout_sl_mult_eff.
            double bo_sl_mult_buy = (g_sc.breakout_buy_sl_atr_mult > 0.0)
               ? g_sc.breakout_buy_sl_atr_mult * ((high_vol_trend) ? g_sc.high_vol_breakout_sl_boost : 1.0)
               : breakout_sl_mult_eff;
            double bo_sl = NormalizeDouble(bid - m5_atr * bo_sl_mult_buy, _Digits);
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
         // 2.7.27 — Daily Direction Gate Filter 1 SELL side (mirror of BUY block above).
         //   Block SELL when D1 SMA slope is positive beyond threshold (multi-day rip).
         //   Same throttle window as BUY side — at most one bias-block log per M5 bar.
         // 2.7.38 — BLOCK_SELL_IN_CHOP composite (chop-regime + h1 still bullish).
         //   Fires before daily-bias gate so chop-block wins when both apply.
         if(IsBlockSellInChopActive(h1_trend_strength)) {
            datetime _cbs_bar_bk = iTime(_Symbol, PERIOD_M5, 0);
            if(_cbs_bar_bk != g_last_chop_block_sell_log_bar) {
               g_last_chop_block_sell_log_bar = _cbs_bar_bk;
               JournalRecordSignal("SKIP","entry_quality_chop_block_sell","BB_BREAKOUT","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else
         if(g_sc.daily_direction_gate_enabled && g_daily_bull_bias) {
            datetime _dbb_bar_s = iTime(_Symbol, PERIOD_M5, 0);
            if(_dbb_bar_s != g_scalper_last_dailybias_sell_log_bar) {
               g_scalper_last_dailybias_sell_log_bar = _dbb_bar_s;
               JournalRecordSignal("SKIP","entry_quality_daily_bull_block_sell","BB_BREAKOUT","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else {
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
         // Crash bypass: H1+H4 both bear → skip RSI floor + ADX spike gate.
         // M15 ADX gate (2.7.13): crash bypass requires M15 ADX >= h1h4_crash_sell_min_m15_adx.
         // Prevents false breakdowns where M5 ADX spikes from flat (e.g., May4 17:10 M5=37.4, M15=16.7).
         // In a genuine crash, M15 and M5 trend together (Apr30 07:05: M5=41.3, M15=35.6 ✓).
         double _m15adx_crash[1];
         double m15_adx_now = (g_mtf[1].h_adx != INVALID_HANDLE
                               && CopyBuffer(g_mtf[1].h_adx, 0, 0, 1, _m15adx_crash) == 1)
                              ? _m15adx_crash[0] : 0;
         bool crash_m15_ok = (g_sc.h1h4_crash_sell_min_m15_adx <= 0)
                             || (m15_adx_now >= g_sc.h1h4_crash_sell_min_m15_adx);
         bool crash_sell_bypass = g_sc.breakout_h1h4_crash_sell && h1_bear && h4_bear
                                  && m5_rsi > g_sc.breakout_h1h4_crash_sell_rsi_min
                                  && (g_sc.h1h4_crash_sell_adx_max <= 0 || m5_adx <= g_sc.h1h4_crash_sell_adx_max)
                                  && crash_m15_ok;
         // Two-tier RSI floor — absolute + ADX-conditioned stricter floor (skipped on crash bypass)
         // strong_h1_bear bypass (2.7.14): when H1 DI- strongly dominates (h1_trend<-1.0),
         // the M5 ADX may still be building (early breakout) — the ADX-conditioned floor would
         // incorrectly block genuine trend entries. Apr29 15:55 example: H1=-1.912, ADX=25.9 →
         // weak_adx_floor raised floor to 36, blocked a 30-pt SELL. Bypass restores normal floor.
         bool rsi_floor_ok = true;
         if(!crash_sell_bypass) {
            double sell_floor_eff = g_sc.breakout_rsi_sell_floor;
            bool strong_h1_bear = (h1_trend_strength < -1.0);
            bool weak_adx_floor = (m5_adx < g_sc.breakout_adx_sell_floor_threshold) && !strong_h1_bear;
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
            // strong_h1_bear bypass (2.7.14): when H1 is strongly bearish (h1_trend<-1.0), a one-bar
            // RSI tick-up is noise in a genuine downtrend — Apr29 16:00 H1=-1.997 blocked a 30-pt move.
            bool rsi_decl_ok = true;
            if(adx_dur_ok && g_sc.breakout_require_rsi_declining_sell
               && m5_adx < g_sc.breakout_rsi_decl_sell_adx_threshold
               && h1_trend_strength >= -1.0) {  // bypass when H1 strongly bearish
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
            // RSI hidden-bull divergence gate (2.7.13): block SELL when HID_BULL divergence is active.
            // HID_BULL = price higher low + RSI lower low → downtrend pullback about to reverse UP.
            // G5007 (Run 11, May4 17:10) had HID_BULL at entry and reversed +18pts immediately.
            // Uses g_rsi_div_type computed by DetectRSIDivergence() each bar.
            bool hid_bull_ok = true;
            if(adx_dur_ok && rsi_decl_ok && g_sc.breakout_block_hid_bull_sell
               && g_rsi_div_type == "HID_BULL") {
               datetime _hbd_bar = iTime(_Symbol, PERIOD_M5, 0);
               if(_hbd_bar != g_scalper_last_hbd_log_bar) {
                  g_scalper_last_hbd_log_bar = _hbd_bar;
                  JournalRecordSignal("SKIP","entry_quality_hid_bull_div_sell","BB_BREAKOUT","SELL",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
               }
               hid_bull_ok = false;
            }
            // OsMA(3,10,16) histogram gate (2.7.7): MACD Histogram MC 4-quadrant method (AK20/traderak20)
            // arXiv:2206.12282: RSI+MACD dual gate 84-86% WR. iOsMA buffer 0 = MACD−Signal directly.
            // SELL only passes Q2 (histogram negative AND falling = strong bear momentum confirmed).
            // Q0(+↑): strong bull | Q1(+↓): bull fading | Q2(−↓): PASS | Q3(−↑): bear fading → block
            bool macd_sell_ok = true;
            if(adx_dur_ok && rsi_decl_ok && hid_bull_ok && g_sc.breakout_require_macd_sell && g_h_osma_scalp != INVALID_HANDLE) {
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
            if(adx_dur_ok && rsi_decl_ok && hid_bull_ok && macd_sell_ok && g_sc.breakout_require_h1_macd_sell
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
            if(adx_dur_ok && rsi_decl_ok && hid_bull_ok && macd_sell_ok && h1_macd_sell_ok
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
            if(adx_dur_ok && rsi_decl_ok && hid_bull_ok && macd_sell_ok && h1_macd_sell_ok && m30_bear_ok
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
            if(adx_dur_ok && rsi_decl_ok && hid_bull_ok && macd_sell_ok && h1_macd_sell_ok && m30_bear_ok && h4_rsi_sell_ok
               && g_sc.h4_adx_gate_enabled && h4_adx_v > 0) {
               if(h4_adx_v < g_sc.h4_adx_min_sell) {
                  JournalRecordSignal("SKIP","entry_quality_h4_adx_sell_blocked","BB_BREAKOUT","SELL",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
                  h4_adx_sell_ok = false;
               }
            }
            // BB_BREAKOUT same-direction cooldown (2.7.17) — mirror of BUY-side cooldown
            bool bo_cooldown_sell_ok = true;
            if(adx_dur_ok && rsi_decl_ok && hid_bull_ok && macd_sell_ok && h1_macd_sell_ok && m30_bear_ok && h4_rsi_sell_ok && h4_adx_sell_ok
               && g_sc.breakout_same_dir_cooldown_seconds > 0
               && g_scalper_last_bb_breakout_sell > 0
               && (TimeCurrent() - g_scalper_last_bb_breakout_sell) < g_sc.breakout_same_dir_cooldown_seconds
               && !CooldownBypassActive("SELL", "BB_BREAKOUT", m5_adx)) {  // 2.7.41 — bypass on TP+TREND_BEAR+ADX
               datetime _bocs_bar = iTime(_Symbol, PERIOD_M5, 0);
               if(_bocs_bar != g_scalper_last_bocooldown_log_bar) {
                  g_scalper_last_bocooldown_log_bar = _bocs_bar;
                  JournalRecordSignal("SKIP","entry_quality_breakout_cooldown","BB_BREAKOUT","SELL",
                     mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
               }
               bo_cooldown_sell_ok = false;
            }
            // 2.7.20 — PSAR alignment gate (mirror of BUY path): SELL requires psar_state == ABOVE.
            bool psar_align_sell_ok = true;
            if(adx_dur_ok && rsi_decl_ok && hid_bull_ok && macd_sell_ok && h1_macd_sell_ok && m30_bear_ok && h4_rsi_sell_ok && h4_adx_sell_ok && bo_cooldown_sell_ok
               && g_sc.breakout_require_psar_align && g_sc.psar_enabled) {
               if(g_psar_state != "ABOVE") {
                  datetime _pss_bar = iTime(_Symbol, PERIOD_M5, 0);
                  if(_pss_bar != g_scalper_last_psar_log_bar) {
                     g_scalper_last_psar_log_bar = _pss_bar;
                     JournalRecordSignal("SKIP","entry_quality_psar_misalign_sell","BB_BREAKOUT","SELL",
                        mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
                  }
                  psar_align_sell_ok = false;
               }
            }
            // News RSI tighten — independent additive check (last line of defense before entry)
            bool nf_sell_ok = true;
            if(adx_dur_ok && rsi_decl_ok && hid_bull_ok && macd_sell_ok && h1_macd_sell_ok && m30_bear_ok && h4_rsi_sell_ok && h4_adx_sell_ok && bo_cooldown_sell_ok && psar_align_sell_ok
               && g_nf_eff_rsi_sell_min > g_sc.breakout_rsi_sell_floor
               && m5_rsi <= g_nf_eff_rsi_sell_min) {
               JournalRecordSignal("SKIP","entry_quality_news_rsi_tighten","BB_BREAKOUT","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
               nf_sell_ok = false;
            }
            if(adx_dur_ok && rsi_decl_ok && hid_bull_ok && macd_sell_ok && h1_macd_sell_ok && m30_bear_ok && h4_rsi_sell_ok && h4_adx_sell_ok && bo_cooldown_sell_ok && psar_align_sell_ok && nf_sell_ok) {
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
         } // 2.7.27 — end daily-bull-bias else block (SELL Filter 1 wrapper)
      }
   }

   // ─────────────────────────────────────────────────────────────────────────────
   // 2.7.28 — Momentum dump-catch market entry
   //
   // PURPOSE: Fire market entries on fast M5 impulses that BB_BREAKOUT and BB_BOUNCE
   //   conditions miss. Run 17 lost ~208 pts of Apr 22-29 bear move because most
   //   dump bars never re-broke the BB lower band after the initial break.
   //
   // EVALUATION ORDER (only runs when direction is still empty after BB checks):
   //   1. Master toggle (dump_catch_enabled) — skip block entirely if false
   //   2. Compute move_3bars = M5_close(0) − M5_close(lookback_bars)
   //   3. SELL trigger: move < -atr_mult × m5_atr
   //      BUY trigger:  move > +atr_mult × m5_atr
   //   4. Filter chain (logs SKIP per gate when trigger fires but filter blocks):
   //      a. RSI bound (SELL: rsi < max; BUY: rsi > 100−max)
   //      b. ADX min (sustained move)
   //      c. PSAR alignment (optional)
   //      d. Daily bias agreement (optional, depends on v2.7.27 Filter 1)
   //      e. Cooldown (per-direction wall-time gate)
   //   5. On pass: set direction + setup_type="MOMENTUM_DUMP" + SL/TP for downstream.
   //
   // GEOMETRY (single-shot scalp):
   //   SL = 1.5 × ATR
   //   TP1 = 0.4 × ATR (scalp banker)
   //   TP2 = 1.0 × ATR
   //   TP3 = 2.0 × ATR
   //   Lot = fixed_lot × dump_lot_factor (0.7 default)
   //   No cascade arming — ArmPostTP1Ladder checks setup_type at top.
   //
   // CHANGELOG:
   //   2026-05-11  v2.7.28 — initial implementation (Run 17 trend-capture gap fix).
   // ─────────────────────────────────────────────────────────────────────────────
   if(direction == "" && g_sc.dump_catch_enabled && m5_atr > 0.0) {
      int dump_lb = MathMax(1, g_sc.dump_lookback_bars);
      double m5_close_now  = iClose(_Symbol, PERIOD_M5, 0);
      double m5_close_back = iClose(_Symbol, PERIOD_M5, dump_lb);
      double move_pts      = m5_close_now - m5_close_back;
      double dump_thresh   = g_sc.dump_atr_mult * m5_atr;
      bool   dump_sell_trig = (move_pts < -dump_thresh);
      bool   dump_buy_trig  = (move_pts >  dump_thresh);
      datetime _dump_bar = iTime(_Symbol, PERIOD_M5, 0);
      datetime _now_t    = TimeCurrent();
      // 2.7.32 Option B (default OFF) — direction-confirmation gate.
      //   Require the IMMEDIATELY PRIOR closed bar (bar 1) to also have moved in trade direction
      //   vs bar 2. Filters single-wick triggers that fire on one strong bar then reverse.
      //   Enable via FORGE_DUMP_REQUIRE_BAR_CONFIRM=1. Currently default 0; logged as `dump_bar_confirm_missing` SKIP.
      if(g_sc.dump_require_bar_confirm && (dump_sell_trig || dump_buy_trig)) {
         double cl1 = iClose(_Symbol, PERIOD_M5, 1);
         double cl2 = iClose(_Symbol, PERIOD_M5, 2);
         bool confirmed = (dump_sell_trig && cl1 < cl2) || (dump_buy_trig && cl1 > cl2);
         if(!confirmed) {
            bool _logged_bc = (_dump_bar == g_scalper_last_dump_log_bar);
            if(!_logged_bc) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_bar_confirm_missing","MOMENTUM_DUMP",
                  dump_sell_trig ? "SELL" : "BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
            dump_sell_trig = false;
            dump_buy_trig  = false;
         }
      }

      if(dump_sell_trig) {
         // SELL filter chain — log SKIP on first blocking gate, throttled per M5 bar.
         bool _logged = (_dump_bar == g_scalper_last_dump_log_bar);
         // 2.7.35 — h1_trend ceiling for SELL (Run 23 G5004/G5008/G5020 fix).
         // Run 23 evidence: SELLs with h1_trend ≥ 2.0 in TREND_BULL lost large ($19-47) vs winners
         // at h1_trend < 1.5 banking $3-6. Counter-trend SELLs in very strong bull are statistically
         // losing trades — block at h1_trend ≥ dump_sell_h1_max (default 0 = disabled).
         if(g_sc.dump_sell_h1_max > 0.0 && h1_trend_strength >= g_sc.dump_sell_h1_max) {
            if(!_logged) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_h1_trend_block_sell","MOMENTUM_DUMP","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0,
                  0.0, m15_adx_bounce, 0.0);
            }
         } else if(m5_rsi >= g_sc.dump_max_rsi) {
            if(!_logged) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_rsi_block","MOMENTUM_DUMP","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0,
                  0.0, m15_adx_bounce, 0.0);
            }
         } else if(m5_adx < g_sc.dump_min_adx) {
            if(!_logged) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_adx_block","MOMENTUM_DUMP","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else if(g_sc.dump_require_psar && g_sc.psar_enabled && g_psar_state != "ABOVE") {
            if(!_logged) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_psar_block","MOMENTUM_DUMP","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else if(g_sc.dump_require_d1_bias && g_sc.daily_direction_gate_enabled && !g_daily_bear_bias) {
            if(!_logged) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_d1_bias_block","MOMENTUM_DUMP","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else if(g_sc.dump_cooldown_seconds > 0
                && g_scalper_last_dump_sell_time > 0
                && (_now_t - g_scalper_last_dump_sell_time) < g_sc.dump_cooldown_seconds) {
            if(!_logged) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_cooldown","MOMENTUM_DUMP","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else if(g_regime_label == "RANGE") {
            // 2.7.32 — Chop filter: RANGE regime = no clean trend, dump-catch gets whipsawed.
            // Run 20 Mar 31 showed 4/7 dumps lost in regime=RANGE (4550-4575 range chop).
            if(!_logged) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_chop_block","MOMENTUM_DUMP","SELL",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else {
            // All filters pass — fire market SELL entry
            direction = "SELL";
            setup_type = "MOMENTUM_DUMP";
            // 2.7.32 — SL widened 1.5→3.0×ATR. Operator mandate: "S/L to widen as long as we follow the market".
            //   With 3.0×ATR (~12pts) the SL survives chop wicks. ATR trail ratchets down as profit develops.
            // 2.7.33 — TP1 0.4→0.6×ATR (operator directive 2026-05-12). Run 22 G5003/G5004 reached
            //   3-4×ATR favorable but exited at +2 pts — wider TP1 captures more on the first scalp leg.
            sl  = NormalizeDouble(ask + m5_atr * 4.0, _Digits);
            tp1 = NormalizeDouble(bid - m5_atr * 0.6, _Digits);
            tp2 = NormalizeDouble(bid - m5_atr * 1.0, _Digits);
            g_scalper_last_dump_sell_time = _now_t;
            PrintFormat("FORGE 2.7.33: MOMENTUM_DUMP SELL fired @ %.2f (move=%.2fpts over %d bars, ATR=%.2f, RSI=%.1f, ADX=%.1f, regime=%s)",
                        bid, move_pts, dump_lb, m5_atr, m5_rsi, m5_adx, g_regime_label);
         }
      } else if(dump_buy_trig) {
         // BUY mirror — same filter chain with sign flips.
         bool _logged_b = (_dump_bar == g_scalper_last_dump_log_bar);
         double buy_rsi_min = 100.0 - g_sc.dump_max_rsi;  // mirror: RSI > 100−max
         // 2.7.38 — INTRADAY_REVERSAL_TO_SELL_V3 composite block. When active, ALL BUY blocked.
         //   Inserted as the first rung of the BUY filter cascade so the else-if chain
         //   skips all subsequent gates AND the entry assignment when reversal fires.
         if(IsIntradayReversalSellActive(h1_trend_strength, m5_rsi, mid, m5_bb_m)) {
            if(_dump_bar != g_last_intraday_reversal_log_bar) {
               g_last_intraday_reversal_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","entry_quality_intraday_reversal_buy_block","MOMENTUM_DUMP","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         }
         // 2.7.34 — BUY RSI ceiling (G5009 Run 20 fix). Block BUY when RSI is overbought-exhausted.
         // G5009 BUY @ 4592.63 fired at RSI=72.2 in TREND_BULL → reversed −18 pts → 10-leg cascade SL = −$305.
         // The "wave is exhausted" reality check that M5 momentum indicators alone miss.
         else if(g_sc.dump_max_rsi_buy > 0 && m5_rsi >= g_sc.dump_max_rsi_buy) {
            if(!_logged_b) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_rsi_buy_ceil","MOMENTUM_DUMP","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else if(m5_rsi <= buy_rsi_min) {
            if(!_logged_b) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_rsi_block","MOMENTUM_DUMP","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else if(g_sc.daily_direction_gate_enabled && g_daily_bear_bias) {
            // 2.7.34 — Daily reality check (Fix C). MOMENTUM_DUMP_BUY blocked on bearish daily slope.
            // Operator principle: "use indicators and regime to know our setup" — daily slope is the
            // regime-level direction signal. G5009 Mar 31 fired BUY on a bearish daily (D1 slope < 0):
            // M5 indicators showed up-momentum, but the day "in reality" was selling. This gate prevents
            // MOMENTUM_DUMP_BUY entries from bypassing the daily-direction filter that BB_BREAKOUT/BB_BOUNCE already respect.
            if(!_logged_b) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","entry_quality_daily_bear_block_buy","MOMENTUM_DUMP","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else if(m5_adx < g_sc.dump_min_adx) {
            if(!_logged_b) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_adx_block","MOMENTUM_DUMP","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else if(g_sc.dump_require_psar && g_sc.psar_enabled && g_psar_state != "BELOW") {
            if(!_logged_b) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_psar_block","MOMENTUM_DUMP","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else if(g_sc.dump_require_d1_bias && g_sc.daily_direction_gate_enabled && !g_daily_bull_bias) {
            if(!_logged_b) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_d1_bias_block","MOMENTUM_DUMP","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else if(g_sc.dump_cooldown_seconds > 0
                && g_scalper_last_dump_buy_time > 0
                && (_now_t - g_scalper_last_dump_buy_time) < g_sc.dump_cooldown_seconds) {
            if(!_logged_b) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_cooldown","MOMENTUM_DUMP","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else if(g_regime_label == "RANGE") {
            // 2.7.32 — Chop filter: same as SELL side. Range regime = whipsaw zone.
            if(!_logged_b) {
               g_scalper_last_dump_log_bar = _dump_bar;
               JournalRecordSignal("SKIP","dump_chop_block","MOMENTUM_DUMP","BUY",
                  mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
            }
         } else {
            // All filters pass — fire market BUY entry
            direction = "BUY";
            setup_type = "MOMENTUM_DUMP";
            // 2.7.32 — SL widened 1.5→3.0×ATR (chop survival, mirror of SELL side).
            // 2.7.33 — TP1 0.4→0.6×ATR (operator directive 2026-05-12, mirror of SELL).
            sl  = NormalizeDouble(bid - m5_atr * 4.0, _Digits);
            tp1 = NormalizeDouble(ask + m5_atr * 0.6, _Digits);
            tp2 = NormalizeDouble(ask + m5_atr * 1.0, _Digits);
            g_scalper_last_dump_buy_time = _now_t;
            PrintFormat("FORGE 2.7.33: MOMENTUM_DUMP BUY fired @ %.2f (move=+%.2fpts over %d bars, ATR=%.2f, RSI=%.1f, ADX=%.1f)",
                        ask, move_pts, dump_lb, m5_atr, m5_rsi, m5_adx);
         }
      }
   }

   // 2.7.38 — #3 FRACTIONAL_SELL_IN_BULL trigger (atlas §5.3). Counter-regime
   //   overbought probe — fires when TREND_BULL + h1≥1.0 + PSAR ABOVE + RSI 60-75
   //   + ADX≥30 + bar-over-bar bearish + price near BB upper. Fractional lot
   //   (default 0.25× base) so a wrong-direction probe is bounded.
   if(direction == "" && g_sc.fractional_sell_in_bull_enabled && m5_atr > 0.0
      && IsFractionalSellInBullActive(h1_trend_strength)) {
      direction  = "SELL";
      setup_type = "FRACTIONAL_SELL_IN_BULL";
      double ask_px = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double bid_px = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      sl  = NormalizeDouble(ask_px + m5_atr * g_sc.fractional_sell_in_bull_sl_atr_mult, _Digits);
      tp1 = NormalizeDouble(bid_px - m5_atr * g_sc.fractional_sell_in_bull_tp1_atr_mult, _Digits);
      tp2 = 0;  // single banking — no runner per atlas §5.3
      g_last_fractional_sell_in_bull_time = TimeCurrent();
      PrintFormat("FORGE 2.7.38: FRACTIONAL_SELL_IN_BULL fired @ %.2f (h1_trend=%.2f, RSI=%.1f, ADX=%.1f, regime=%s)",
                  bid_px, h1_trend_strength, m5_rsi, m5_adx, g_regime_label);
   }

   // 2.7.38 — #4 BULL_DAY_DIP_BUY_V3 trigger (atlas §5.1 V3, case study §4c).
   //   16-atom dip-buy on choppy bull days. Single TP1 (default 0.65×ATR ≈ 40
   //   pips at ATR=6), no TP2/TP3, 300sec re-entry cooldown after TP1 exit.
   //   V3 OHLC atoms (!m5_lh_cascade, long_lower_wick, dist_high_atr<2) blocked
   //   the Apr 8 16:35 BB_BOUNCE BUY −$200 disaster.
   if(direction == "" && g_sc.bull_day_dip_buy_enabled && m5_atr > 0.0
      && IsBullDayDipBuyActive(h1_trend_strength)) {
      direction  = "BUY";
      setup_type = "BULL_DAY_DIP_BUY";
      double ask_px2 = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double bid_px2 = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      sl  = NormalizeDouble(bid_px2 - m5_atr * g_sc.bull_day_dip_buy_sl_atr_mult, _Digits);
      tp1 = NormalizeDouble(ask_px2 + m5_atr * g_sc.bull_day_dip_buy_tp1_atr_mult, _Digits);
      tp2 = 0;  // single banking — no runner per atlas §5.1
      // Re-entry cooldown anchor (atlas §5.1 spec says "exit time"; we set at entry as
      // a conservative simplification — TP1 ≈ 40 pips fires within minutes so the
      // 300s cooldown effectively starts post-exit). Refine to true exit time in v2.7.39
      // if needed (would require hook in ManageOpenGroups TP1-close branch).
      g_last_chop_buy_exit_time = TimeCurrent();
      PrintFormat("FORGE 2.7.38: BULL_DAY_DIP_BUY fired @ %.2f (h1_trend=%.2f, RSI=%.1f, ADX=%.1f, dist_high_atr=%.2f, regime=%s)",
                  ask_px2, h1_trend_strength, m5_rsi, m5_adx,
                  m5_atr > 0 ? (g_eval_day_high - ask_px2) / m5_atr : 0.0, g_regime_label);
   }

   // 2.7.42 — MA_CROSSOVER trigger (Phase 2). EMA(20) × EMA(50) event-triggered entry.
   //   Fires on the M5 close where the EMA20 crosses EMA50 (sign-flip detected by
   //   DetectMaCrossoverEvent). BUY on up-cross, SELL on down-cross. Gates: ADX ≥
   //   ma_crossover_adx_min, M15 trend agreement (existing m15_ok_buy/sell), per-
   //   direction cooldown with v2.7.41 bypass-on-TP-win. Lot factor 0.5 (lagging).
   if(direction == "" && g_sc.ma_crossover_enabled && m5_atr > 0.0) {
      int mac_event = DetectMaCrossoverEvent();
      if(mac_event != 0) {
         string mac_dir = (mac_event > 0) ? "BUY" : "SELL";
         bool mac_adx_ok = (m5_adx >= g_sc.ma_crossover_adx_min);
         // Local recompute of M15 trend agreement (m15_ok_buy/sell locals are out
         // of scope at this point in CheckNativeScalperSetups). g_mtf[1] is M15.
         bool mac_m15_ok = true;
         double mac_m15_e20[1], mac_m15_e50[1];
         if(CopyBuffer(g_mtf[1].h_ma20, 0, 1, 1, mac_m15_e20) == 1
            && CopyBuffer(g_mtf[1].h_ma50, 0, 1, 1, mac_m15_e50) == 1) {
            double mac_m15_diff = mac_m15_e20[0] - mac_m15_e50[0];
            mac_m15_ok = (mac_event > 0) ? (mac_m15_diff >= 0.0) : (mac_m15_diff <= 0.0);
         }
         datetime mac_last = (mac_event > 0) ? g_ma_crossover_last_buy_time : g_ma_crossover_last_sell_time;
         datetime mac_now  = TimeCurrent();
         bool mac_cool_ok = (g_sc.ma_crossover_cooldown_seconds <= 0
                             || mac_last == 0
                             || (mac_now - mac_last) >= g_sc.ma_crossover_cooldown_seconds
                             || CooldownBypassActive(mac_dir, "MA_CROSSOVER", m5_adx));
         if(!mac_adx_ok) {
            JournalRecordSignal("SKIP","ma_crossover_adx_below_min","MA_CROSSOVER",mac_dir,
               mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
         } else if(!mac_m15_ok) {
            JournalRecordSignal("SKIP","ma_crossover_m15_misalign","MA_CROSSOVER",mac_dir,
               mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
         } else if(!mac_cool_ok) {
            JournalRecordSignal("SKIP","ma_crossover_cooldown","MA_CROSSOVER",mac_dir,
               mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
         } else {
            direction  = mac_dir;
            setup_type = "MA_CROSSOVER";
            double mac_ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            double mac_bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
            if(mac_event > 0) {
               sl  = NormalizeDouble(mac_bid - m5_atr * g_sc.ma_crossover_sl_atr_mult, _Digits);
               tp1 = NormalizeDouble(mac_ask + m5_atr * g_sc.ma_crossover_tp1_atr_mult, _Digits);
               tp2 = NormalizeDouble(mac_ask + m5_atr * g_sc.ma_crossover_tp2_atr_mult, _Digits);
               g_ma_crossover_last_buy_time = mac_now;
            } else {
               sl  = NormalizeDouble(mac_ask + m5_atr * g_sc.ma_crossover_sl_atr_mult, _Digits);
               tp1 = NormalizeDouble(mac_bid - m5_atr * g_sc.ma_crossover_tp1_atr_mult, _Digits);
               tp2 = NormalizeDouble(mac_bid - m5_atr * g_sc.ma_crossover_tp2_atr_mult, _Digits);
               g_ma_crossover_last_sell_time = mac_now;
            }
            PrintFormat("FORGE 2.7.42: MA_CROSSOVER %s fired @ %.2f (M5 EMA20×EMA50, ADX=%.1f, h1_trend=%.2f)",
                        mac_dir, (mac_event > 0 ? mac_ask : mac_bid), m5_adx, h1_trend_strength);
         }
      }
   }

   // 2.7.42 — VWAP_REVERSION trigger (Phase 2). Pullback-to-VWAP in established
   //   H1 trend direction (gold-friendly). H1 direction is built into the
   //   detector — so only cooldown can block here.
   if(direction == "" && g_sc.vwap_reversion_enabled && m5_atr > 0.0) {
      int vwr_event = DetectVwapReversionEvent(m5_atr, h1_trend_strength);
      if(vwr_event != 0) {
         string vwr_dir = (vwr_event > 0) ? "BUY" : "SELL";
         datetime vwr_last = (vwr_event > 0) ? g_vwap_reversion_last_buy_time : g_vwap_reversion_last_sell_time;
         datetime vwr_now  = TimeCurrent();
         bool vwr_cool_ok = (g_sc.vwap_reversion_cooldown_seconds <= 0
                             || vwr_last == 0
                             || (vwr_now - vwr_last) >= g_sc.vwap_reversion_cooldown_seconds
                             || CooldownBypassActive(vwr_dir, "VWAP_REVERSION", m5_adx));
         if(!vwr_cool_ok) {
            JournalRecordSignal("SKIP","vwap_reversion_cooldown","VWAP_REVERSION",vwr_dir,
               mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
         } else {
            direction  = vwr_dir;
            setup_type = "VWAP_REVERSION";
            double vwr_ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            double vwr_bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
            if(vwr_event > 0) {
               sl  = NormalizeDouble(vwr_bid - m5_atr * g_sc.vwap_reversion_sl_atr_mult, _Digits);
               tp1 = NormalizeDouble(vwr_ask + m5_atr * g_sc.vwap_reversion_tp1_atr_mult, _Digits);
               tp2 = NormalizeDouble(vwr_ask + m5_atr * g_sc.vwap_reversion_tp2_atr_mult, _Digits);
               g_vwap_reversion_last_buy_time = vwr_now;
            } else {
               sl  = NormalizeDouble(vwr_ask + m5_atr * g_sc.vwap_reversion_sl_atr_mult, _Digits);
               tp1 = NormalizeDouble(vwr_bid - m5_atr * g_sc.vwap_reversion_tp1_atr_mult, _Digits);
               tp2 = NormalizeDouble(vwr_bid - m5_atr * g_sc.vwap_reversion_tp2_atr_mult, _Digits);
               g_vwap_reversion_last_sell_time = vwr_now;
            }
            PrintFormat("FORGE 2.7.42: VWAP_REVERSION %s fired @ %.2f (vwap=%.2f, h1_trend=%.2f, ADX=%.1f)",
                        vwr_dir, (vwr_event > 0 ? vwr_ask : vwr_bid), g_vwap_price, h1_trend_strength, m5_adx);
         }
      }
   }

   // 2.7.42 — FIB_CONFLUENCE trigger (Phase 2). Retrace to fib 38.2/50/61.8 +
   //   reference overlap (EMA20/EMA50/VWAP) in established H1 trend direction.
   if(direction == "" && g_sc.fib_confluence_enabled && m5_atr > 0.0) {
      int fc_event = DetectFibConfluenceEvent(m5_atr, h1_trend_strength);
      if(fc_event != 0) {
         string fc_dir = (fc_event > 0) ? "BUY" : "SELL";
         datetime fc_last = (fc_event > 0) ? g_fib_confluence_last_buy_time : g_fib_confluence_last_sell_time;
         datetime fc_now  = TimeCurrent();
         bool fc_cool_ok = (g_sc.fib_confluence_cooldown_seconds <= 0
                            || fc_last == 0
                            || (fc_now - fc_last) >= g_sc.fib_confluence_cooldown_seconds
                            || CooldownBypassActive(fc_dir, "FIB_CONFLUENCE", m5_adx));
         if(!fc_cool_ok) {
            JournalRecordSignal("SKIP","fib_confluence_cooldown","FIB_CONFLUENCE",fc_dir,
               mid,spread,m5_atr,m5_rsi,m5_adx,m5_bb_u,m5_bb_l,m5_bb_m,0,h1_trend_strength,0);
         } else {
            direction  = fc_dir;
            setup_type = "FIB_CONFLUENCE";
            double fc_ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            double fc_bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
            if(fc_event > 0) {
               sl  = NormalizeDouble(fc_bid - m5_atr * g_sc.fib_confluence_sl_atr_mult, _Digits);
               tp1 = NormalizeDouble(fc_ask + m5_atr * g_sc.fib_confluence_tp1_atr_mult, _Digits);
               tp2 = NormalizeDouble(fc_ask + m5_atr * g_sc.fib_confluence_tp2_atr_mult, _Digits);
               g_fib_confluence_last_buy_time = fc_now;
            } else {
               sl  = NormalizeDouble(fc_ask + m5_atr * g_sc.fib_confluence_sl_atr_mult, _Digits);
               tp1 = NormalizeDouble(fc_bid - m5_atr * g_sc.fib_confluence_tp1_atr_mult, _Digits);
               tp2 = NormalizeDouble(fc_bid - m5_atr * g_sc.fib_confluence_tp2_atr_mult, _Digits);
               g_fib_confluence_last_sell_time = fc_now;
            }
            PrintFormat("FORGE 2.7.42: FIB_CONFLUENCE %s fired @ %.2f (fib382=%.2f, fib50=%.2f, fib618=%.2f, h1_trend=%.2f)",
                        fc_dir, (fc_event > 0 ? fc_ask : fc_bid), g_fib_382, g_fib_50, g_fib_618, h1_trend_strength);
         }
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
         // 2.7.19 — failed-breakout-pullback gate tracker: record price + bar of THIS atr_ext SKIP for BUY
         // so a later lower-priced entry within breakout_failed_lookback_bars can be blocked.
         if(direction == "BUY" && setup_type == "BB_BREAKOUT") {
            g_scalper_last_atrext_skip_bar_buy   = m5bar;
            g_scalper_last_atrext_skip_price_buy = mid;
         }
         return;
      }
   }

   // Entry Quality Gate — M5 bar body/direction/ATR/BB-expansion pre-filter
   // rsi/adx passed for logging only (not used in gate logic — OHLC-only checks)
   if(!CheckEntryQuality(direction, m5_atr, m5_bb_u, m5_bb_l, m5_rsi, m5_adx, setup_type)) return;

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
   // 2.7.22 — R:R uses BASE breakout_sl_atr_mult (with high_vol boost) instead of the actually-placed sl.
   // Run 16 (v2.7.21) revealed: breakout_buy_sl_atr_mult=3.0 widens BUY SL placement for SL-hunt protection,
   // but the R:R gate then computed risk=3.0×ATR vs max TP4=4.0×ATR → R:R=1.33 < min_rr_floor=1.5 → 100%
   // BUY breakouts blocked rr_too_low (G5001/G5002/G5003 all blocked Apr 1 Run 16). buy_sl_atr_mult is a
   // tail-risk protection (worst-case wick survival); the R:R gate evaluates expected-MAE risk. Decouple.
   double rr_base_sl_mult = (setup_type == "BB_BOUNCE")
      ? g_sc.bounce_sl_atr_mult
      : g_sc.breakout_sl_atr_mult * ((high_vol_trend) ? g_sc.high_vol_breakout_sl_boost : 1.0);
   double risk = m5_atr * rr_base_sl_mult;
   double reward_tp1 = (direction == "BUY") ? (tp1 - rr_entry_ref) : (rr_entry_ref - tp1);
   double reward_tp2 = (tp2 > 0.0) ? ((direction == "BUY") ? (tp2 - rr_entry_ref) : (rr_entry_ref - tp2)) : 0.0;
   double reward = reward_tp1;
   if(setup_type == "BB_BOUNCE")
      reward = MathMax(reward_tp1, reward_tp2);
   if(setup_type == "BB_BREAKOUT" || setup_type == "BB_BREAKOUT_RETEST") {
      // Breakout scales out across 4 TPs — use the best reachable TP for the RR gate.
      // At base 2.0× SL: TP1(0.5x)=0.25 RR, TP2(1.5x)=0.75, TP3(2.5x)=1.25, TP4(4.0x)=2.0.
      double reward_tp3 = m5_atr * g_sc.breakout_tp3_atr_mult;
      double reward_tp4 = m5_atr * g_sc.breakout_tp4_atr_mult;
      reward = MathMax(reward_tp1, MathMax(reward_tp2, MathMax(reward_tp3, reward_tp4)));
   }
   // 2.7.31 — MOMENTUM_DUMP bypass: dump-catch is a tight-SL scalp with TP1=0.4×ATR / SL=1.5×ATR
   //   (R:R=0.27 < min_rr_floor=1.5 → would always block). The dump trigger gates (RSI extreme,
   //   ADX strength, PSAR alignment, cooldown) ARE the safety net. Operator mandate 2026-05-11
   //   (Run 19 Apr 8): "open more orders on the bearish run — it was a great day to milk money"
   //   — Apr 8 had 30+ MOMENTUM_DUMP SELL triggers all blocked downstream by rr_too_low.
   //   Bypass is structural, not env-tunable, because the dump geometry is intrinsically scalp.
   //
   // 2.7.39 — Extend bypass to FRACTIONAL_SELL_IN_BULL and BULL_DAY_DIP_BUY:
   //   Both are intrinsic single-TP1 / no-TP2 scalps per atlas §5.3 and §5.1 V3.
   //   FRACTIONAL_SELL_IN_BULL: SL 1.5×ATR / TP1 0.3×ATR → R:R=0.2 (structural, no TP2).
   //   BULL_DAY_DIP_BUY: SL 1.0×ATR / TP1 0.65×ATR → R:R=0.65 (still < 1.5 floor).
   //   Codex v2.7.38 review FAIL #1: without this bypass both new setup types are
   //   silently rejected by rr_too_low even when their composite enable flag is set.
   //   Same rationale as MOMENTUM_DUMP: trigger atoms + composite gates ARE the safety net.
   bool _rr_bypass = (setup_type == "MOMENTUM_DUMP"
                   || setup_type == "BB_PULLBACK_SCALP"
                   || setup_type == "FRACTIONAL_SELL_IN_BULL"
                   || setup_type == "BULL_DAY_DIP_BUY");
   if(!_rr_bypass && (risk <= 0 || reward / risk < rr_min_eff)) {
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
   // 2.7.32 — Scalp setups capped at 2 legs (was 5 default). Operator mandate post-Run 20:
   //   "fire 2 per leg, not 1" — keep some scaling flexibility while preventing the
   //   5-leg × -$10 SL = -$50 per direction-failure that broke Run 20 Mar 31.
   if(setup_type == "MOMENTUM_DUMP" || setup_type == "BB_PULLBACK_SCALP") {
      if(n > 2) {
         trades_policy_out += " scalp_leg_cap=2;";
         n = 2;
      }
   }
   bool htf_clear_with_trade = false;
   double clr_thr = trend_thr_eff * g_sc.native_legs_clear_trend_factor;
   if(clr_thr > 0 && (direction == "BUY" || direction == "SELL")) {
      if(direction == "BUY")
         htf_clear_with_trade = (h1_trend_strength >= clr_thr && h4_trend_strength >= clr_thr);
      else
         htf_clear_with_trade = (h1_trend_strength <= -clr_thr && h4_trend_strength <= -clr_thr);
   }
   // 2.7.31 — H1-strong override on leg-cap (Run 19 Issue 2 / Task #51).
   //   v2.7.29 fixed g_regime_label override but the leg-cap path here was independent.
   //   Apr 1 G5001 fired regime=TREND_BULL ✓ but htf_clear=false (h4 lagged) → still 5-leg cap.
   //   Mirror the regime override clause here: if H1 is exceptionally strong and ADX confirms,
   //   trust the leg ladder ("ride this with multiple orders" — operator mandate 2026-05-11).
   if(!htf_clear_with_trade && g_sc.regime_h1_override_factor > 0.0
      && m5_adx >= g_sc.regime_h1_override_adx_min
      && MathAbs(h1_trend_strength) >= g_sc.regime_h1_override_factor * trend_thr_eff) {
      bool h1_aligned = (direction == "BUY"  && h1_trend_strength > 0.0)
                     || (direction == "SELL" && h1_trend_strength < 0.0);
      if(h1_aligned) {
         htf_clear_with_trade = true;
         trades_policy_out += " legs_h1_strong_override;";
      }
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
   // 2.7.28 — MOMENTUM_DUMP fractional lot. Dump-catch is a scalp; smaller per-leg exposure than BB setups.
   // 2.7.35 — direction-specific override: dump_buy_lot_factor / dump_sell_lot_factor when set (> 0).
   //   In bullish regimes BUY MOMENTUM_DUMP should size up (with-trend); SELL stays probe-size.
   double _dump_eff_factor = g_sc.dump_lot_factor;
   if(setup_type == "MOMENTUM_DUMP") {
      if(direction == "BUY"  && g_sc.dump_buy_lot_factor  > 0.0) _dump_eff_factor = g_sc.dump_buy_lot_factor;
      if(direction == "SELL" && g_sc.dump_sell_lot_factor > 0.0) _dump_eff_factor = g_sc.dump_sell_lot_factor;
   }
   double dump_factor = (setup_type == "MOMENTUM_DUMP" && _dump_eff_factor > 0.0 && _dump_eff_factor <= 2.0)
                        ? _dump_eff_factor : 1.0;
   // 2.7.31 — BB_PULLBACK_SCALP fractional lot. Same scalp profile as MOMENTUM_DUMP.
   double pullback_factor = (setup_type == "BB_PULLBACK_SCALP" && g_sc.pullback_scalp_lot_factor > 0.0 && g_sc.pullback_scalp_lot_factor < 1.0)
                            ? g_sc.pullback_scalp_lot_factor : 1.0;
   // 2.7.38 — INTRADAY_REVERSAL_TO_SELL_V3 amplifier. When composite is active AND
   //   this is a MOMENTUM_DUMP SELL, multiply lot by intraday_reversal_sell_lot_mult.
   //   The pivot-detection composite gives high-conviction SELL signals; amplifying
   //   the regime-aligned SELL is the with-trend doubling rationale (atlas §5.7).
   double intraday_reversal_factor = 1.0;
   if(setup_type == "MOMENTUM_DUMP" && direction == "SELL"
      && IsIntradayReversalSellActive(h1_trend_strength, m5_rsi,
                                       SymbolInfoDouble(_Symbol, SYMBOL_BID), m5_bb_m)) {
      intraday_reversal_factor = g_sc.intraday_reversal_sell_lot_mult;
   }
   // 2.7.38 — FRACTIONAL_SELL_IN_BULL fractional probe (atlas §5.3). Scales down
   //   the lot for the counter-regime overbought SELL probe to keep risk bounded.
   double fractional_sell_factor = (setup_type == "FRACTIONAL_SELL_IN_BULL" && direction == "SELL"
                                    && g_sc.fractional_sell_in_bull_lot_factor > 0.0
                                    && g_sc.fractional_sell_in_bull_lot_factor <= 1.0)
                                    ? g_sc.fractional_sell_in_bull_lot_factor : 1.0;
   // 2.7.38 — BULL_DAY_DIP_BUY_V3 amplifier (atlas §5.1). Regime-aligned dip-buy
   //   on choppy bull days. Lot multiplier is operator-tunable (default 1.0 = no
   //   amplification; set higher to size up when composite fires).
   double bull_day_dip_factor = (setup_type == "BULL_DAY_DIP_BUY" && direction == "BUY"
                                 && g_sc.bull_day_dip_buy_lot_mult > 0.0)
                                 ? g_sc.bull_day_dip_buy_lot_mult : 1.0;
   // 2.7.42 — MA_CROSSOVER lot factor (Phase 2). Default 0.5 — crossovers lag,
   //   so per-leg lot is halved by default. Operator can override via
   //   FORGE_GEOMETRY_MA_CROSSOVER_LOT_FACTOR.
   double ma_crossover_factor = (setup_type == "MA_CROSSOVER"
                                 && g_sc.ma_crossover_lot_factor > 0.0
                                 && g_sc.ma_crossover_lot_factor < 1.0)
                                 ? g_sc.ma_crossover_lot_factor : 1.0;
   // 2.7.42 — VWAP_REVERSION lot factor (Phase 2). Default 0.5 — pullback
   //   entries are higher-edge than chasing but still half-size by policy.
   double vwap_reversion_factor = (setup_type == "VWAP_REVERSION"
                                   && g_sc.vwap_reversion_lot_factor > 0.0
                                   && g_sc.vwap_reversion_lot_factor < 1.0)
                                   ? g_sc.vwap_reversion_lot_factor : 1.0;
   // 2.7.42 — FIB_CONFLUENCE lot factor (Phase 2). Default 0.5.
   double fib_confluence_factor = (setup_type == "FIB_CONFLUENCE"
                                   && g_sc.fib_confluence_lot_factor > 0.0
                                   && g_sc.fib_confluence_lot_factor < 1.0)
                                   ? g_sc.fib_confluence_lot_factor : 1.0;
   // 2.7.40 — ScalperLotFactor at top of combined_lot_factor chain. MT5 input (non-default 1.0)
   //   wins; otherwise env-side scalper_lot_factor (from FORGE_GLOBAL_SCALPER_LOT_FACTOR) takes over.
   //   Default for both = 1.0 (no-op). This is the unifying scaler — half/double-sizing without
   //   touching fixed_lot. Lot pipeline is now ONE absolute base × N multipliers.
   double scalper_lot_factor_eff = (ScalperLotFactor != 1.0) ? ScalperLotFactor : g_sc.scalper_lot_factor;
   if(scalper_lot_factor_eff <= 0.0) scalper_lot_factor_eff = 1.0;
   // Compound factor floor: 0.125 = broker minimum lot (0.01) at base lot 0.08.
   // ADX >= 55 entries are now BLOCKED (not taken at 1/16th which rounded to same as 1/8th).
   // Floor ensures no entry falls below 0.01 regardless of how many reducers stack.
   double combined_lot_factor = MathMax(0.125, scalper_lot_factor_eff * inside_band_factor * near_floor_factor * stack_factor * adx_lot_factor * bounce_factor * dump_factor * pullback_factor * intraday_reversal_factor * fractional_sell_factor * bull_day_dip_factor * ma_crossover_factor * vwap_reversion_factor * fib_confluence_factor);
   g_last_combined_lot_factor = combined_lot_factor;
   // 2.7.40 — base_lot is now ALWAYS g_sc.lot_fixed (single absolute source of truth).
   //   The old MT5-input absolute override (ScalperLot) is gone; size-up/down happens via the
   //   ScalperLotFactor multiplier above. INPUTS lot_sizing_source still controls leg count.
   double base_lot = g_sc.lot_fixed;
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
   // 2.7.27 — TP4/TP5 levels for extended runner staging in TRENDING regime.
   // TP4 = 4.0×ATR (already configured via breakout_tp4_atr_mult); TP5 = 5.5×ATR (breakout_tp5_atr_mult).
   // Levels are precomputed at entry; staging activation is gated at runtime by ADX + regime.
   g_groups[gi].tp4 = (is_breakout_setup && g_sc.breakout_tp4_staging_enabled && g_sc.breakout_tp4_atr_mult > 0.0)
                      ? NormalizeDouble((direction == "SELL")
                          ? rr_entry_ref - m5_atr * g_sc.breakout_tp4_atr_mult
                          : rr_entry_ref + m5_atr * g_sc.breakout_tp4_atr_mult, _Digits)
                      : 0.0;
   g_groups[gi].tp5 = (is_breakout_setup && g_sc.breakout_tp5_staging_enabled && g_sc.breakout_tp5_atr_mult > 0.0)
                      ? NormalizeDouble((direction == "SELL")
                          ? rr_entry_ref - m5_atr * g_sc.breakout_tp5_atr_mult
                          : rr_entry_ref + m5_atr * g_sc.breakout_tp5_atr_mult, _Digits)
                      : 0.0;
   g_groups[gi].tp1_close_pct = tp1_split_pct;
   g_groups[gi].tp1_hit       = false;
   g_groups[gi].tp2_hit       = false;
   g_groups[gi].tp3_hit       = false;  // 2.7.27
   g_groups[gi].tp4_hit       = false;  // 2.7.27
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
   // 2.7.25 — ATR trail peak/trough init (per FORGE_RATCHET_LOGIC_IDEAS.md)
   g_groups[gi].peak_price   = bid;
   g_groups[gi].trough_price = ask;
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
   // 2.7.17: track last BB_BREAKOUT entry time per direction for the breakout cooldown gate
   if(setup_type == "BB_BREAKOUT") {
      if(direction == "BUY")  g_scalper_last_bb_breakout_buy  = TimeCurrent();
      if(direction == "SELL") g_scalper_last_bb_breakout_sell = TimeCurrent();
   }
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
      g_groups[n].tp4 = 0;         // 2.7.27: RebuildGroups path does not stage TP4/TP5 (no recompute from live)
      g_groups[n].tp5 = 0;
      g_groups[n].tp1_close_pct = 50;
      g_groups[n].tp1_hit = false;
      g_groups[n].tp2_hit = false;
      g_groups[n].tp3_hit = false;  // 2.7.27
      g_groups[n].tp4_hit = false;  // 2.7.27
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
   // 2.7.28 — MOMENTUM_DUMP is a single-shot scalp; never arm cascade for it.
   if(g_groups[gi].scalper_setup == "MOMENTUM_DUMP") return;
   // 2.7.31 — BB_PULLBACK_SCALP is also a single-shot tight scalp; no cascade.
   if(g_groups[gi].scalper_setup == "BB_PULLBACK_SCALP") return;
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
      bool cascade_ok = true;
      double cur_rsi = (g_mtf[0].h_rsi != INVALID_HANDLE && CopyBuffer(g_mtf[0].h_rsi, 0, 0, 1, _rbuf) == 1) ? _rbuf[0] : 0;
      double cur_adx = (g_mtf[0].h_adx != INVALID_HANDLE && CopyBuffer(g_mtf[0].h_adx, 0, 0, 1, _rbuf) == 1) ? _rbuf[0] : 0;

      // Gate 1 — RSI: do not add to position when market is oversold (exhausted)
      if(cascade_ok && cur_rsi > 0 && cur_rsi <= g_sc.sell_stop_cont_min_rsi) {
         PrintFormat("FORGE: ArmPostTP1Ladder G%d — skipped RSI=%.1f <= %.1f (exhausted)", grp_id, cur_rsi, g_sc.sell_stop_cont_min_rsi);
         cascade_ok = false;
      }
      // Gate 2 — ADX: trend must be confirmed at arm time, not a random spike from flat
      if(cascade_ok && g_sc.sell_stop_cont_min_adx > 0 && cur_adx > 0 && cur_adx < g_sc.sell_stop_cont_min_adx) {
         PrintFormat("FORGE: ArmPostTP1Ladder G%d — skipped ADX=%.1f < %.1f (trend not confirmed)", grp_id, cur_adx, g_sc.sell_stop_cont_min_adx);
         cascade_ok = false;
      }
      // Gate 3 — H1 DI: H1 must be bearish (DI- > DI+). Same logic as require_h1_di_sell gate.
      // Uses g_h_adx (PERIOD_H1 handle): buffer 1=DI+, buffer 2=DI-.
      if(cascade_ok && g_sc.sell_stop_cont_require_h1_di && g_h_adx != INVALID_HANDLE) {
         double _di[1];
         double arm_di_plus  = (CopyBuffer(g_h_adx, 1, 0, 1, _di) == 1) ? _di[0] : 0;
         double arm_di_minus = (CopyBuffer(g_h_adx, 2, 0, 1, _di) == 1) ? _di[0] : 0;
         if(arm_di_plus > 0 && arm_di_minus > 0 && arm_di_plus >= arm_di_minus) {
            PrintFormat("FORGE: ArmPostTP1Ladder G%d — skipped H1 DI+=%.1f >= DI-=%.1f (H1 bullish, counter-trend)", grp_id, arm_di_plus, arm_di_minus);
            cascade_ok = false;
         }
      }
      // Gate 4 — Regime (2.7.21, Run 15 G5040 fix): cascade is a TREND amplifier. In RANGE regime the
      // typical post-TP1 continuation is a mean-reversal stop-hunt that fills cascade at the move's
      // extreme low, then reverses through SL. G5040 cascade lost -$1119 in RANGE regime when SELL @
      // 4768.81 hit TP1 at 4766, armed cascade at 4761.23, then market reversed to 4789 (cascade SL).
      // Canonical gold-trading literature: "Trade after the liquidity grab, not before" — chasing
      // continuation in RANGE is exactly buying the liquidity grab.
      if(cascade_ok && g_sc.sell_stop_cont_require_trend_regime) {
         if(g_regime_label == "RANGE" || g_regime_label == "") {
            PrintFormat("FORGE: ArmPostTP1Ladder G%d — skipped regime='%s' (require_trend_regime=1, only arm in TREND_BULL/TREND_BEAR/VOLATILE)", grp_id, g_regime_label);
            cascade_ok = false;
         }
      }

      if(cascade_ok) {
         double tp1_ref  = g_groups[gi].tp1;
         double ss_price = NormalizeDouble(tp1_ref - entry_atr * g_sc.sell_stop_cont_atr_mult, _Digits);
         // SL geometry (2.7.16): anchored to cascade entry, sized by sell_stop_cont_sl_atr_mult.
         // Decoupled from entry trigger to prevent SL-hunt wicks (Run 13 cascade survived only because
         // h1_trend=-1.997 trend was maximally strong; weaker continuations would wick out at the old 0.8×ATR SL).
         // Fallback to legacy geometry (sl_atr_mult=0 → tp1 + atr_mult×ATR) preserves backward compatibility.
         double _ss_sl_mult = g_sc.sell_stop_cont_sl_atr_mult;
         double ss_sl    = (_ss_sl_mult > 0.0)
                           ? NormalizeDouble(ss_price + entry_atr * _ss_sl_mult, _Digits)
                           : NormalizeDouble(tp1_ref + entry_atr * g_sc.sell_stop_cont_atr_mult, _Digits);
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
            PrintFormat("FORGE: ArmPostTP1Ladder G%d — %d/%d SELL STOP legs placed (ADX=%.1f RSI=%.1f)", grp_id, legs_placed, legs_target, cur_adx, cur_rsi);
      }  // end if(cascade_ok)
   }  // end if(sell_stop_cont_enabled)
   // BUY LIMIT recovery (slot [9]) — Cardwell Bull Support entry at crash low after SELL TP1
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
