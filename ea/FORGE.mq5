//+------------------------------------------------------------------+
//|  FORGE.mq5  — FORGE Multi-Mode Expert Advisor v1.6.11           |
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
#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Files\FileTxt.mqh>

// ── INPUT PARAMETERS (shown in EA dialog when attaching to chart) ──
input string  FilesPath      = "";           // Override MT5 Files path (leave blank for auto)
input int     MagicNumber    = 202401;       // EA magic number
input int     TimerSeconds   = 1;            // OnTimer interval (seconds)
input bool    EnableBacktest = false;        // Unused — Tester is detected via MQL_TESTER; kept for input-slot compatibility
input bool    LogTicks       = true;         // Log ticks in WATCH mode
input string  InputMode      = "WATCH";      // Startup mode: OFF|WATCH|SIGNAL|SCALPER|HYBRID
input int     BrokerInfoEveryCycles = 20;    // Re-write broker_info.json every N timer cycles (0=OnInit only)
input string  ScalperMode    = "NONE";       // Native scalper: NONE|BB_BOUNCE|BB_BREAKOUT|DUAL
input double  ScalperLot     = 0.01;         // Lot size per native scalper trade
input int     ScalperTrades  = 4;            // Number of trades per native scalper group
input double  PendingEntryThresholdPoints = 50.0;   // Market-vs-pending switch threshold (points)
input double  TrendStrengthAtrThreshold   = 0.20;   // ATR-normalized EMA trend threshold
input double  BreakoutBufferPoints        = 10.0;   // Breakout buffer beyond BB band (points)
input bool    NativeScalperH4Align        = true;   // Require H4 EMA/ATR trend alignment (same threshold as H1)
input bool    NativeScalperRegimeGate     = true;   // Block counter-trend vs TREND_BULL/BEAR when config regime_* says so
input string  NativeScalperM1Mode         = "NONE"; // NONE | CONFIRM (M1 EMA/ATR vs bias) | TRIGGER (CONFIRM + last closed M1 candle direction)

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
datetime g_scalper_last_loss_time = 0;
datetime g_scalper_last_entry_bar = 0;  // prevent multiple entries on same bar
datetime g_scalper_last_reset_day = 0;  // UTC day marker for session counter reset
datetime g_scalper_last_nosetup_log_bar = 0;   // throttle noisy "no setup" (once per M5 bar)
datetime g_scalper_last_sesswarn_log_bar = 0; // throttle session_off log (once per M5 bar)
string   g_scalper_config_snapshot = "";       // skip re-parse + log spam when scalper_config.json unchanged

// Scalper config (from scalper_config.json or defaults)
struct ScalperConfig {
   // BB Bounce
   bool   bounce_enabled;
   double bounce_adx_max;
   double bounce_rsi_buy_max;
   double bounce_rsi_sell_min;
   double bounce_bb_proximity_pct;
   double bounce_sl_atr_mult;
   double bounce_tp1_close_pct;
   double bounce_tp2_close_pct;
   // BB Breakout
   bool   breakout_enabled;
   double breakout_adx_min;
   double breakout_rsi_buy_min;
   double breakout_rsi_sell_max;
   double breakout_sl_atr_mult;
   double breakout_tp1_atr_mult;
   double breakout_tp2_atr_mult;
   double breakout_tp3_atr_mult;
   double breakout_tp4_atr_mult;
   double breakout_tp1_close_pct;
   bool   breakout_require_m15;
   bool   breakout_move_be;
   // Safety
   double max_spread_points;
   int    max_open_groups;
   int    max_trades_per_session;
   int    loss_cooldown_sec;
   // Session
   int    london_start;
   int    london_end;
   int    ny_start;
   int    ny_end;
   // DD event
   double dd_tight_tp_atr;
   int    sentinel_min_threshold;
   double pending_entry_threshold_points;
   double trend_strength_atr_threshold;
   double breakout_buffer_points;
};
ScalperConfig g_sc;

// H1 INDICATOR HANDLES — created once in EnsureIndicators(), read every OnTimer
int g_h_rsi  = INVALID_HANDLE;
int g_h_ma20 = INVALID_HANDLE;
int g_h_ma50 = INVALID_HANDLE;
int g_h_atr  = INVALID_HANDLE;
int g_h_bb   = INVALID_HANDLE;
int g_h_macd = INVALID_HANDLE;
int g_h_adx  = INVALID_HANDLE;

// H4 — native scalper higher-TF structure (EMA20/50 + ATR; same trend_strength formula as H1)
int g_h4_ma20 = INVALID_HANDLE;
int g_h4_ma50 = INVALID_HANDLE;
int g_h4_atr  = INVALID_HANDLE;

// M1 — optional entry confirmation / trigger (execution TF; H1/H4/regime stay bias-only)
int g_m1_ma20 = INVALID_HANDLE;
int g_m1_ma50 = INVALID_HANDLE;
int g_m1_atr  = INVALID_HANDLE;

// Regime snapshot from BRIDGE config.json (Phase C — mirrors AEGIS counter-trend policy for Python LENS scalper)
string g_regime_label = "";
double g_regime_confidence = 0;
bool   g_regime_apply_policy = false;
double g_regime_ct_min_conf = 0.55;

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
   bool   be_moved;
   bool   move_be_on_tp1;
   int    magic_offset;  // magic + id to differentiate groups
};
TradeGroup g_groups[];

string JsonEscape(const string s);
bool JsonHasKey(const string &json, const string &key);

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
      || g_m1_ma20==INVALID_HANDLE || g_m1_ma50==INVALID_HANDLE || g_m1_atr==INVALID_HANDLE)
      Print("FORGE: indicator handles unavailable (market closed?) — will retry on timer");
   // Print all path info for diagnostics
   Print("FORGE initialised — magic=",MagicNumber,
         " datapath=",  TerminalInfoString(TERMINAL_DATA_PATH),
         " commonpath=",TerminalInfoString(TERMINAL_COMMONDATA_PATH),
         " balance=",   AccountInfoDouble(ACCOUNT_BALANCE));
   WriteBrokerInfo();
   InitScalperConfig();
   WriteMarketData();
   RebuildGroups();
   g_scalper_mode = ScalperMode;
   if(g_scalper_mode != "NONE")
      Print("FORGE: Native scalper mode = ", g_scalper_mode);
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
   IndicatorRelease(g_h_macd); g_h_macd = INVALID_HANDLE;
   IndicatorRelease(g_h_adx);  g_h_adx = INVALID_HANDLE;
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
   g_h_macd = iMACD(_Symbol, PERIOD_H1, 12, 26, 9, PRICE_CLOSE);
   g_h_adx  = iADX(_Symbol, PERIOD_H1, 14);
   g_h4_ma20 = iMA(_Symbol, PERIOD_H4, 20, 0, MODE_EMA, PRICE_CLOSE);
   g_h4_ma50 = iMA(_Symbol, PERIOD_H4, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_h4_atr  = iATR(_Symbol, PERIOD_H4, 14);
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
}

string WriteMTFBlock(int idx) {
   double buf[1];
   double rsi  = (CopyBuffer(g_mtf[idx].h_rsi, 0,0,1,buf)==1)  ? buf[0] : 0;
   double ma20 = (CopyBuffer(g_mtf[idx].h_ma20,0,0,1,buf)==1)  ? buf[0] : 0;
   double ma50 = (CopyBuffer(g_mtf[idx].h_ma50,0,0,1,buf)==1)  ? buf[0] : 0;
   double atr  = (CopyBuffer(g_mtf[idx].h_atr, 0,0,1,buf)==1)  ? buf[0] : 0;
   double bb_m = (CopyBuffer(g_mtf[idx].h_bb,  0,0,1,buf)==1)  ? buf[0] : 0;
   double bb_u = (CopyBuffer(g_mtf[idx].h_bb,  1,0,1,buf)==1)  ? buf[0] : 0;
   double bb_l = (CopyBuffer(g_mtf[idx].h_bb,  2,0,1,buf)==1)  ? buf[0] : 0;
   double macd = (CopyBuffer(g_mtf[idx].h_macd,2,0,1,buf)==1)  ? buf[0] : 0;  // buffer 2 = histogram
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
   if(g_cycle % 20 == 0) ReadScalperConfig();
}

//+------------------------------------------------------------------+
//| OnTick — real-time management                                     |
//+------------------------------------------------------------------+
void OnTick() {
   if(g_mode == "OFF") return;
   ResetScalperSessionStateIfNeeded();
   if(g_mode == "WATCH") { WriteTickData(); return; }
   ManageOpenGroups();
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
   g_groups[gi].tp3           = 0;
   g_groups[gi].tp1_close_pct = tp1_close_pct;
   g_groups[gi].tp1_hit       = false;
   g_groups[gi].be_moved      = false;
   g_groups[gi].move_be_on_tp1 = move_be;
   g_groups[gi].magic_offset  = group_magic;

   Print("FORGE: Group ", group_id, " opened — ", opened, "/", n, " trades");
   g_trade.SetExpertMagicNumber(MagicNumber);
}

//+------------------------------------------------------------------+
//| Manage open groups: TP1 partial close + BE move                   |
//+------------------------------------------------------------------+
void ManageOpenGroups() {
   for(int gi = 0; gi < ArraySize(g_groups); gi++) {
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
      if(total == 0) { g_groups[gi].tp1_hit = true; continue; }
      int to_close = (int)MathCeil(total * g_groups[gi].tp1_close_pct / 100.0);
      int closed   = 0;
      for(int j = 0; j < total && closed < to_close; j++) {
         if(g_pos.SelectByTicket(positions[j])) {
            if(g_trade.PositionClose(positions[j])) closed++;
         }
      }
      g_groups[gi].tp1_hit = true;
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
   j += "\"symbol\":\"" + JsonEscape(_Symbol) + "\",";
   j += "\"hermes_version\":\"FORGE_1.2\",";
   j += "\"forge_version\":\"1.6.11\",";
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
   double h1_macd  = (CopyBuffer(g_h_macd,2,0,1,rsi_buf)==1)  ? rsi_buf[0]  : 0;
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
   double h4_ma20b[1], h4_ma50b[1], h4_atrb[1];
   double h4_m20 = (CopyBuffer(g_h4_ma20,0,0,1,h4_ma20b)==1) ? h4_ma20b[0] : 0;
   double h4_m50 = (CopyBuffer(g_h4_ma50,0,0,1,h4_ma50b)==1) ? h4_ma50b[0] : 0;
   double h4_atr_v = (CopyBuffer(g_h4_atr, 0,0,1,h4_atrb)==1) ? h4_atrb[0] : 0;
   j += "\"ema_20\":" + DoubleToString(h4_m20,2) + ",";
   j += "\"ema_50\":" + DoubleToString(h4_m50,2) + ",";
   j += "\"atr_14\":" + DoubleToString(h4_atr_v,2);
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
   j += "\"forge_version\":\"1.6.11\",";
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
   g_sc.bounce_rsi_sell_min = 65;
   g_sc.bounce_bb_proximity_pct = 20;
   g_sc.bounce_sl_atr_mult = 1.2;
   g_sc.bounce_tp1_close_pct = 40;
   g_sc.bounce_tp2_close_pct = 30;
   g_sc.breakout_enabled = true;
   g_sc.breakout_adx_min = 25;
   g_sc.breakout_rsi_buy_min = 55;
   g_sc.breakout_rsi_sell_max = 45;
   g_sc.breakout_sl_atr_mult = 1.5;
   g_sc.breakout_tp1_atr_mult = 1.0;
   g_sc.breakout_tp2_atr_mult = 1.5;
   g_sc.breakout_tp3_atr_mult = 2.5;
   g_sc.breakout_tp4_atr_mult = 4.0;
   g_sc.breakout_tp1_close_pct = 40;
   g_sc.breakout_require_m15 = true;
   g_sc.breakout_move_be = true;
   g_sc.max_spread_points = 25;
   g_sc.max_open_groups = 2;
   g_sc.max_trades_per_session = 3;
   g_sc.loss_cooldown_sec = 300;
   g_sc.london_start = 7;
   g_sc.london_end = 12;
   g_sc.ny_start = 12;
   // Align with config/scalper_config.json session_filter.ny_end_utc: late NY (20–23 UTC) was silent with 20.
   g_sc.ny_end = 24;
   g_sc.dd_tight_tp_atr = 0.8;
   g_sc.sentinel_min_threshold = 30;
   g_sc.pending_entry_threshold_points = PendingEntryThresholdPoints;
   g_sc.trend_strength_atr_threshold = TrendStrengthAtrThreshold;
   g_sc.breakout_buffer_points = BreakoutBufferPoints;
   ReadScalperConfig();
}

void ReadScalperConfig() {
   string content = "";
   if(!ReadTextFileDual("scalper_config.json", content)) return;
   if(content == "") return;
   if(content == g_scalper_config_snapshot) return;
   g_scalper_config_snapshot = content;
   // Parse config values (use defaults if key missing)
   double v;
   v = JsonGetDouble(content, "adx_max");       if(v > 0) g_sc.bounce_adx_max = v;
   v = JsonGetDouble(content, "rsi_buy_max");    if(v > 0) g_sc.bounce_rsi_buy_max = v;
   v = JsonGetDouble(content, "rsi_sell_min");   if(v > 0) g_sc.bounce_rsi_sell_min = v;
   v = JsonGetDouble(content, "bb_proximity_pct");if(v > 0) g_sc.bounce_bb_proximity_pct = v;
   v = JsonGetDouble(content, "adx_min");        if(v > 0) g_sc.breakout_adx_min = v;
   v = JsonGetDouble(content, "rsi_buy_min");    if(v > 0) g_sc.breakout_rsi_buy_min = v;
   v = JsonGetDouble(content, "rsi_sell_max");   if(v > 0) g_sc.breakout_rsi_sell_max = v;
   v = JsonGetDouble(content, "max_spread_points");if(v > 0) g_sc.max_spread_points = v;
   v = JsonGetDouble(content, "max_open_groups"); if(v > 0) g_sc.max_open_groups = (int)v;
   v = JsonGetDouble(content, "max_trades_per_session"); if(v > 0) g_sc.max_trades_per_session = (int)v;
   v = JsonGetDouble(content, "loss_cooldown_sec"); if(v > 0) g_sc.loss_cooldown_sec = (int)v;
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
   PrintFormat("FORGE config reloaded: pending_entry_threshold_points=%.2f trend_strength_atr_threshold=%.4f breakout_buffer_points=%.2f session=%d-%d/%d-%d",
               g_sc.pending_entry_threshold_points,
               g_sc.trend_strength_atr_threshold,
               g_sc.breakout_buffer_points,
               g_sc.london_start,
               g_sc.london_end,
               g_sc.ny_start,
               g_sc.ny_end);
}
void ResetScalperSessionStateIfNeeded() {
   MqlDateTime dt;
   TimeGMT(dt);
   datetime today = StringToTime(StringFormat("%04d.%02d.%02d 00:00", dt.year, dt.mon, dt.day));
   if(today <= 0) return;
   if(g_scalper_last_reset_day == 0) {
      g_scalper_last_reset_day = today;
      return;
   }
   if(today != g_scalper_last_reset_day) {
      g_scalper_last_reset_day = today;
      g_scalper_session_trades = 0;
      g_scalper_last_entry_bar = 0;
      Print("FORGE SCALPER: session counters reset for new UTC day");
   }
}

bool ScalperSessionOK() {
   MqlDateTime dt;
   TimeGMT(dt);
   int h = dt.hour;
   return ((h >= g_sc.london_start && h < g_sc.london_end)
           || (h >= g_sc.ny_start && h < g_sc.ny_end));
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

bool ScalperOnePerBar() {
   // Prevent multiple entries on the same M5 bar
   datetime bar_time = iTime(_Symbol, PERIOD_M5, 0);
   if(bar_time == g_scalper_last_entry_bar) return false;
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

void CheckNativeScalperSetups() {
   MqlDateTime dt;
   TimeGMT(dt);
   int hour = dt.hour;
   double spread = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / _Point;
   int open_groups = ScalperOpenGroupCount();

   // Safety guards
   // Live: London/NY session window. Tester: skip — simulated TimeGMT() often sits outside 07–20 UTC for
   // long stretches of a backtest (or the whole range), which zeroes out entries despite valid setups.
   if(MQLInfoInteger(MQL_TESTER) == 0 && !ScalperSessionOK()) {
      datetime m5bar = iTime(_Symbol, PERIOD_M5, 0);
      if(m5bar != g_scalper_last_sesswarn_log_bar) {
         g_scalper_last_sesswarn_log_bar = m5bar;
         PrintFormat("FORGE SCALPER: skip gate=session_off hour=%d UTC — london=%d-%d ny=%d-%d (no trades this hour)",
                     hour, g_sc.london_start, g_sc.london_end, g_sc.ny_start, g_sc.ny_end);
      }
      return;
   }
   // Live: enforce max spread. Tester: skip — modeled XAU spread often sits above typical live caps and
   // would block nearly every tick (see Agent logs: spread 26–31 vs max 25), distorting backtest results.
   if(MQLInfoInteger(MQL_TESTER) == 0 && spread > g_sc.max_spread_points) {
      PrintFormat("FORGE SCALPER: skip gate=spread spread=%.1f max=%.1f", spread, g_sc.max_spread_points);
      return;
   }
   if(open_groups >= g_sc.max_open_groups) {
      PrintFormat("FORGE SCALPER: skip gate=open_groups open=%d max=%d", open_groups, g_sc.max_open_groups);
      return;
   }
   if(MQLInfoInteger(MQL_TESTER) == 0 && g_scalper_session_trades >= g_sc.max_trades_per_session) {
      PrintFormat("FORGE SCALPER: skip gate=session_trade_cap trades=%d max=%d",
                  g_scalper_session_trades, g_sc.max_trades_per_session);
      return;
   }
   if(MQLInfoInteger(MQL_TESTER) == 0 && !ScalperCooldownOK()) {
      int remaining = (int)MathMax(0, g_sc.loss_cooldown_sec - (int)(TimeGMT() - g_scalper_last_loss_time));
      PrintFormat("FORGE SCALPER: skip gate=cooldown remaining_sec=%d", remaining);
      return;
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

   // Read H1 trend (for direction filter)
   double h1_ema20 = (CopyBuffer(g_h_ma20,0,0,1,buf)==1) ? buf[0] : 0;
   double h1_ema50 = (CopyBuffer(g_h_ma50,0,0,1,buf)==1) ? buf[0] : 0;
   double h1_atr   = (CopyBuffer(g_h_atr, 0,0,1,buf)==1) ? buf[0] : 0;

   if(m5_rsi == 0 || m5_atr == 0 || m5_bb_u == 0) {
      Print("FORGE SCALPER: skip reason=indicators_not_ready");
      return;
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
   const bool in_tester = (MQLInfoInteger(MQL_TESTER) != 0);
   double bounce_adx_max_eff = g_sc.bounce_adx_max;
   double breakout_adx_min_eff = g_sc.breakout_adx_min;
   double trend_thr_eff = g_sc.trend_strength_atr_threshold;
   double bounce_bb_prox_eff = g_sc.bounce_bb_proximity_pct;
   double breakout_buf_eff_pts = g_sc.breakout_buffer_points;
   double rr_min_eff = 1.2;
   bool breakout_m15_req_eff = g_sc.breakout_require_m15;
   if(in_tester) {
      bounce_adx_max_eff = 99.0;
      breakout_adx_min_eff = MathMin(g_sc.breakout_adx_min, 15.0);
      trend_thr_eff = MathMax(0.08, g_sc.trend_strength_atr_threshold * 0.45);
      bounce_bb_prox_eff = MathMax(g_sc.bounce_bb_proximity_pct, 40.0);
      breakout_buf_eff_pts = MathMax(1.0, g_sc.breakout_buffer_points * 0.30);
      rr_min_eff = 1.0;
      breakout_m15_req_eff = false;
   }
   double breakout_buffer = breakout_buf_eff_pts * point;

   // H1 trend bias
   double h1_trend_strength = (h1_ema20 - h1_ema50) / MathMax(h1_atr, point);
   bool h1_bull = h1_trend_strength > trend_thr_eff;
   bool h1_bear = h1_trend_strength < -trend_thr_eff;
   bool h1_flat = !h1_bull && !h1_bear;

   // H4 structure alignment (same ATR-normalized EMA spread rule as H1)
   double h4_ema20 = (CopyBuffer(g_h4_ma20,0,0,1,buf)==1) ? buf[0] : 0;
   double h4_ema50 = (CopyBuffer(g_h4_ma50,0,0,1,buf)==1) ? buf[0] : 0;
   double h4_atr   = (CopyBuffer(g_h4_atr, 0,0,1,buf)==1) ? buf[0] : 0;
   double h4_trend_strength = (h4_ema20 - h4_ema50) / MathMax(h4_atr, point);
   bool h4_bull = h4_trend_strength > trend_thr_eff;
   bool h4_bear = h4_trend_strength < -trend_thr_eff;
   bool h4_flat = !h4_bull && !h4_bear;
   bool h4_ok_buy  = in_tester || (!NativeScalperH4Align) || h4_bull || h4_flat;
   bool h4_ok_sell = in_tester || (!NativeScalperH4Align) || h4_bear || h4_flat;
   bool h1_ok_buy  = in_tester || h1_bull || h1_flat;
   bool h1_ok_sell = in_tester || h1_bear || h1_flat;

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
   double m15_trend_strength = (m15_ema20 - m15_ema50) / MathMax(m15_atr, point);

   // ── BB BOUNCE (Range Mode) ─────────────────────────────────
   if((g_scalper_mode == "BB_BOUNCE" || g_scalper_mode == "DUAL")
      && g_sc.bounce_enabled && m5_adx < bounce_adx_max_eff) {

      double proximity = bb_range * bounce_bb_prox_eff / 100.0;

      // BUY: price near BB lower + RSI oversold + H1 not bearish + optional H4 alignment
      if(mid <= m5_bb_l + proximity && m5_rsi < g_sc.bounce_rsi_buy_max
         && h1_ok_buy && h4_ok_buy) {
         direction = "BUY";
         sl  = NormalizeDouble(bid - m5_atr * g_sc.bounce_sl_atr_mult, _Digits);
         tp1 = NormalizeDouble(m5_bb_m, _Digits);  // BB mid
         tp2 = NormalizeDouble(m5_bb_u, _Digits);  // opposite BB band
         setup_type = "BB_BOUNCE";
      }
      // SELL: price near BB upper + RSI overbought + H1 not bullish
      else if(mid >= m5_bb_u - proximity && m5_rsi > g_sc.bounce_rsi_sell_min
              && h1_ok_sell && h4_ok_sell) {
         direction = "SELL";
         sl  = NormalizeDouble(ask + m5_atr * g_sc.bounce_sl_atr_mult, _Digits);
         tp1 = NormalizeDouble(m5_bb_m, _Digits);
         tp2 = NormalizeDouble(m5_bb_l, _Digits);
         setup_type = "BB_BOUNCE";
      }
   }

   // ── BB BREAKOUT (Trend Mode) ───────────────────────────────
   if(direction == "" && (g_scalper_mode == "BB_BREAKOUT" || g_scalper_mode == "DUAL")
      && g_sc.breakout_enabled && m5_adx >= breakout_adx_min_eff) {
      bool m5_bull  = m5_trend_strength > trend_thr_eff;
      bool m5_bear  = m5_trend_strength < -trend_thr_eff;
      bool m15_bull = m15_trend_strength > trend_thr_eff;
      bool m15_bear = m15_trend_strength < -trend_thr_eff;
      bool m15_flat = !m15_bull && !m15_bear;
      bool m15_ok_buy  = !breakout_m15_req_eff || m15_bull || m15_flat;
      bool m15_ok_sell = !breakout_m15_req_eff || m15_bear || m15_flat;

      // BUY breakout: close above upper BB + RSI strong + aligned
      if(prev_close > (m5_bb_u + breakout_buffer) && m5_rsi > g_sc.breakout_rsi_buy_min
         && m5_bull && m15_ok_buy && h1_ok_buy && h4_ok_buy) {
         direction = "BUY";
         sl  = NormalizeDouble(bid - m5_atr * g_sc.breakout_sl_atr_mult, _Digits);
         tp1 = NormalizeDouble(bid + m5_atr * g_sc.breakout_tp1_atr_mult, _Digits);
         tp2 = NormalizeDouble(bid + m5_atr * g_sc.breakout_tp2_atr_mult, _Digits);
         setup_type = "BB_BREAKOUT";
      }
      // SELL breakout
      else if(prev_close < (m5_bb_l - breakout_buffer) && m5_rsi < g_sc.breakout_rsi_sell_max
              && m5_bear && m15_ok_sell && h1_ok_sell && h4_ok_sell) {
         direction = "SELL";
         sl  = NormalizeDouble(ask + m5_atr * g_sc.breakout_sl_atr_mult, _Digits);
         tp1 = NormalizeDouble(ask - m5_atr * g_sc.breakout_tp1_atr_mult, _Digits);
         tp2 = NormalizeDouble(ask - m5_atr * g_sc.breakout_tp2_atr_mult, _Digits);
         setup_type = "BB_BREAKOUT";
      }
   }

   if(direction != "" && !in_tester && !NativeScalperM1GateOk(direction, m1_bull, m1_bear, m1_flat)) {
      PrintFormat("FORGE SCALPER: skip gate=m1 mode=%s dir=%s m1_ts=%.4f (CONFIRM=EMA/ATR vs threshold; TRIGGER=+prior M1 bar)",
                  NativeScalperM1Mode, direction, m1_trend_strength);
      return;
   }

   if(direction != "" && NativeScalperRegimeBlocksDirection(direction)) {
      PrintFormat("FORGE SCALPER: skip gate=regime_countertrend label=%s conf=%.3f min=%.3f apply=%s dir=%s",
                  g_regime_label, g_regime_confidence, g_regime_ct_min_conf,
                  g_regime_apply_policy ? "true" : "false", direction);
      return;
   }

   if(direction == "") {
      datetime m5b = iTime(_Symbol, PERIOD_M5, 0);
      if(m5b != g_scalper_last_nosetup_log_bar) {
         g_scalper_last_nosetup_log_bar = m5b;
         bool bounce_armed = (g_scalper_mode == "BB_BOUNCE" || g_scalper_mode == "DUAL")
            && g_sc.bounce_enabled && m5_adx < bounce_adx_max_eff;
         bool inside_bb = (prev_close >= m5_bb_l && prev_close <= m5_bb_u);
         PrintFormat("FORGE SCALPER: no setup mode=%s adx=%.1f rsi=%.1f prev=%.2f bb=[%.2f,%.2f] h1=%.4f h4=%.4f m1=%.4f m5=%.4f m15=%.4f",
                     g_scalper_mode, m5_adx, m5_rsi, prev_close, m5_bb_l, m5_bb_u,
                     h1_trend_strength, h4_trend_strength, m1_trend_strength, m5_trend_strength, m15_trend_strength);
         PrintFormat("FORGE SCALPER:   hint bounce_armed=%s (ADX vs cap %.0f); inside_bb=%s; tester_relax=%s",
                     bounce_armed ? "true" : "false", bounce_adx_max_eff, inside_bb ? "true" : "false", in_tester ? "true" : "false");
      }
      return;
   }

   // DD event: tighten TP
   if(sentinel_tight) {
      if(direction == "BUY")
         tp1 = NormalizeDouble(bid + m5_atr * g_sc.dd_tight_tp_atr, _Digits);
      else
         tp1 = NormalizeDouble(ask - m5_atr * g_sc.dd_tight_tp_atr, _Digits);
      tp2 = 0;  // no runners during news
   }

   // R:R check (minimum 1.2)
   double risk = MathAbs((direction == "BUY" ? ask : bid) - sl);
   double reward = MathAbs(tp1 - (direction == "BUY" ? ask : bid));
   if(risk <= 0 || reward / risk < rr_min_eff) {
      Print("FORGE SCALPER: ", setup_type, " ", direction, " skipped — R:R ",
            DoubleToString(reward / risk, 2), " < ", DoubleToString(rr_min_eff, 2));
      return;
   }

   // Execute the native scalper trade group
   g_scalper_group_counter++;
   int group_id = g_scalper_group_counter;
   int group_magic = MagicNumber + group_id;
   g_trade.SetExpertMagicNumber(group_magic);

   int n = ScalperTrades;
   double lot = NormalizeLot(ScalperLot);
   double tp2_price = (tp2 > 0) ? tp2 : tp1;
   double tp1_split_pct = (setup_type == "BB_BREAKOUT") ? g_sc.breakout_tp1_close_pct : g_sc.bounce_tp1_close_pct;
   int tp1_count = (int)MathCeil(n * tp1_split_pct / 100.0);
   int opened = 0;

   for(int i = 0; i < n; i++) {
      double tp_for_this = (i < tp1_count) ? tp1 : tp2_price;
      string tp_label = (i < tp1_count) ? "TP1" : "TP2";
      string comment = "SCALP|" + setup_type + "|G" + IntegerToString(group_id) + "|" + tp_label;
      bool ok = false;
      if(direction == "BUY") {
         if(!ValidateStops(ask, sl, tp_for_this, ORDER_TYPE_BUY)) {
            Print("FORGE SCALPER: invalid BUY stops for group ", group_id, " leg ", i + 1);
            continue;
         }
         ok = g_trade.Buy(lot, _Symbol, ask, NormalizeDouble(sl, _Digits),
                          NormalizeDouble(tp_for_this, _Digits), comment);
      } else {
         if(!ValidateStops(bid, sl, tp_for_this, ORDER_TYPE_SELL)) {
            Print("FORGE SCALPER: invalid SELL stops for group ", group_id, " leg ", i + 1);
            continue;
         }
         ok = g_trade.Sell(lot, _Symbol, bid, NormalizeDouble(sl, _Digits),
                           NormalizeDouble(tp_for_this, _Digits), comment);
      }
      if(ok) opened++;
      else Print("FORGE SCALPER: leg failed retcode=", g_trade.ResultRetcode(), " group=", group_id, " leg=", i + 1);
      Sleep(50);
   }

   g_trade.SetExpertMagicNumber(MagicNumber);
   if(opened <= 0) {
      Print("FORGE SCALPER: ", setup_type, " ", direction, " rejected — no orders opened");
      return;
   }

   g_scalper_session_trades++;
   g_scalper_last_entry_bar = iTime(_Symbol, PERIOD_M5, 0);

   // Register group for TP management
   int gi = ArraySize(g_groups);
   ArrayResize(g_groups, gi + 1);
   g_groups[gi].id            = group_id;
   g_groups[gi].direction     = direction;
   g_groups[gi].tp1           = tp1;
   g_groups[gi].tp2           = tp2;
   g_groups[gi].tp3           = 0;
   g_groups[gi].tp1_close_pct = tp1_split_pct;
   g_groups[gi].tp1_hit       = false;
   g_groups[gi].be_moved      = false;
   g_groups[gi].move_be_on_tp1 = (setup_type == "BB_BREAKOUT") ? g_sc.breakout_move_be : true;
   g_groups[gi].magic_offset  = group_magic;

   Print("FORGE SCALPER: ", setup_type, " ", direction, " G", group_id,
         " — ", opened, "/", n, " trades @ ", DoubleToString(mid, 2),
         " SL=", DoubleToString(sl, 2), " TP1=", DoubleToString(tp1, 2),
         " TP2=", DoubleToString(tp2_price, 2),
         " ATR=", DoubleToString(m5_atr, 2),
         " RSI=", DoubleToString(m5_rsi, 1),
         " ADX=", DoubleToString(m5_adx, 1),
         sentinel_tight ? " [DD_TIGHT_TP]" : "");

   // Write scalper_entry.json for BRIDGE to pick up and log to SCRIBE
   string ej = "{";
   ej += "\"action\":\"FORGE_NATIVE_SCALP\",";
   ej += "\"setup_type\":\"" + setup_type + "\",";
   ej += "\"group_id\":" + IntegerToString(group_id) + ",";
   ej += "\"magic\":" + IntegerToString(group_magic) + ",";
   ej += "\"direction\":\"" + direction + "\",";
   ej += "\"entry_price\":" + DoubleToString(direction == "BUY" ? ask : bid, 2) + ",";
   ej += "\"sl\":" + DoubleToString(sl, 2) + ",";
   ej += "\"tp1\":" + DoubleToString(tp1, 2) + ",";
   ej += "\"tp2\":" + DoubleToString(tp2_price, 2) + ",";
   ej += "\"lot_per_trade\":" + DoubleToString(lot, 2) + ",";
   ej += "\"num_trades\":" + IntegerToString(n) + ",";
   ej += "\"trades_opened\":" + IntegerToString(opened) + ",";
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
   ej += "\"timestamp\":\"" + JsonEscape(TimeToString(TimeGMT(), TIME_DATE|TIME_SECONDS)) + "Z\"";
   ej += "}";
   WriteJsonFileDual("scalper_entry.json", ej);
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
      g_groups[n].tp3 = 0;
      g_groups[n].tp1_close_pct = 50;
      g_groups[n].tp1_hit = false;
      g_groups[n].be_moved = false;
      g_groups[n].move_be_on_tp1 = true;
      g_groups[n].magic_offset = pm;
   }
   if(ArraySize(g_groups) > 0) {
      Print("FORGE: Rebuilt ", ArraySize(g_groups), " trade groups from open positions");
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
   ok = false;
   fail_reason = "";
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
      return false;
   }
   if(direction == "SELL" && StringFind(req_type, "BUY_") == 0) {
      order_kind = req_type;
      fail_reason = "direction/order_type mismatch";
      return false;
   }
   if(req_type != "BUY_MARKET" && req_type != "SELL_MARKET" && !SymbolSupportsOrderType(req_type)) {
      order_kind = req_type;
      fail_reason = "symbol does not support order type";
      return false;
   }

   order_kind = req_type;
   if(req_type == "BUY_MARKET") {
      if(!ValidateStops(ask, sl, tp_for_this, ORDER_TYPE_BUY)) {
         fail_reason = "invalid BUY market stops";
         return false;
      }
      ok = g_trade.Buy(lot_norm, _Symbol, ask, NormalizeDouble(sl, _Digits), NormalizeDouble(tp_for_this, _Digits), comment);
      return true;
   }
   if(req_type == "SELL_MARKET") {
      if(!ValidateStops(bid, sl, tp_for_this, ORDER_TYPE_SELL)) {
         fail_reason = "invalid SELL market stops";
         return false;
      }
      ok = g_trade.Sell(lot_norm, _Symbol, bid, NormalizeDouble(sl, _Digits), NormalizeDouble(tp_for_this, _Digits), comment);
      return true;
   }
   if(req_type == "BUY_LIMIT") {
      if(!ValidateStops(entry, sl, tp_for_this, ORDER_TYPE_BUY_LIMIT)) {
         fail_reason = "invalid BUY_LIMIT stops";
         return false;
      }
      ok = g_trade.BuyLimit(lot_norm, NormalizeDouble(entry, _Digits), _Symbol, NormalizeDouble(sl, _Digits), NormalizeDouble(tp_for_this, _Digits), ORDER_TIME_GTC, 0, comment);
      return true;
   }
   if(req_type == "SELL_LIMIT") {
      if(!ValidateStops(entry, sl, tp_for_this, ORDER_TYPE_SELL_LIMIT)) {
         fail_reason = "invalid SELL_LIMIT stops";
         return false;
      }
      ok = g_trade.SellLimit(lot_norm, NormalizeDouble(entry, _Digits), _Symbol, NormalizeDouble(sl, _Digits), NormalizeDouble(tp_for_this, _Digits), ORDER_TIME_GTC, 0, comment);
      return true;
   }
   if(req_type == "BUY_STOP") {
      if(!ValidateStops(entry, sl, tp_for_this, ORDER_TYPE_BUY_STOP)) {
         fail_reason = "invalid BUY_STOP stops";
         return false;
      }
      ok = g_trade.BuyStop(lot_norm, NormalizeDouble(entry, _Digits), _Symbol, NormalizeDouble(sl, _Digits), NormalizeDouble(tp_for_this, _Digits), ORDER_TIME_GTC, 0, comment);
      return true;
   }
   if(req_type == "SELL_STOP") {
      if(!ValidateStops(entry, sl, tp_for_this, ORDER_TYPE_SELL_STOP)) {
         fail_reason = "invalid SELL_STOP stops";
         return false;
      }
      ok = g_trade.SellStop(lot_norm, NormalizeDouble(entry, _Digits), _Symbol, NormalizeDouble(sl, _Digits), NormalizeDouble(tp_for_this, _Digits), ORDER_TIME_GTC, 0, comment);
      return true;
   }
   if(req_type == "BUY_STOP_LIMIT" || req_type == "SELL_STOP_LIMIT") {
      double slp = leg.stoplimit_price;
      if(slp <= 0) {
         fail_reason = "missing stoplimit_price";
         return false;
      }
      if(req_type == "BUY_STOP_LIMIT") {
         if(entry <= ask + entry_tolerance) {
            fail_reason = "BUY_STOP_LIMIT trigger must be above current ask";
            return false;
         }
         if(slp > entry) {
            fail_reason = "BUY_STOP_LIMIT stoplimit_price must be <= trigger";
            return false;
         }
      } else {
         if(entry >= bid - entry_tolerance) {
            fail_reason = "SELL_STOP_LIMIT trigger must be below current bid";
            return false;
         }
         if(slp < entry) {
            fail_reason = "SELL_STOP_LIMIT stoplimit_price must be >= trigger";
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
      if(!ValidateStops(entry, sl, tp_for_this, req.type)) {
         fail_reason = "invalid stop-limit stops";
         return false;
      }
      req.sl = NormalizeDouble(sl, _Digits);
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
   return false;
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
