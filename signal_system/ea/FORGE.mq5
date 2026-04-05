//+------------------------------------------------------------------+
//|  FORGE.mq5  — FORGE Multi-Mode Expert Advisor                   |
//|  Signal System v1.0  — XAUUSD Scalper                           |
//|  Build order: #2 — independent of Python, compiled in MT5       |
//+------------------------------------------------------------------+
//  Modes:  OFF | WATCH | SIGNAL | SCALPER | HYBRID
//  Input:  MT5/config.json   (BRIDGE writes)
//  Input:  MT5/command.json  (BRIDGE writes)
//  Output: MT5/market_data.json  (BRIDGE + ATHENA read)
//  Output: MT5/tick_data.json    (WATCH mode — ML dataset)
//  Output: MT5/mode_status.json  (ATHENA read)
//+------------------------------------------------------------------+

#property strict
#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Files\FileTxt.mqh>

// ── Input parameters ──────────────────────────────────────────────
input string  FilesPath      = "";           // Override MT5 Files path (leave blank for auto)
input int     MagicNumber    = 202401;       // EA magic number
input int     TimerSeconds   = 3;            // OnTimer interval (seconds)
input bool    EnableBacktest = false;        // Enable Strategy Tester mode
input bool    LogTicks       = true;         // Log ticks in WATCH mode
input string  InputMode      = "WATCH";      // Startup mode: OFF|WATCH|SIGNAL|SCALPER|HYBRID

// ── Globals ───────────────────────────────────────────────────────
CTrade     g_trade;
CPositionInfo g_pos;

string g_mode         = "SIGNAL";
string g_files_path   = "";
string g_last_cmd_ts  = "";
int    g_cycle        = 0;
double g_session_start_balance = 0;

// Indicator handles (H1)
int g_h_rsi  = INVALID_HANDLE;
int g_h_ma20 = INVALID_HANDLE;
int g_h_ma50 = INVALID_HANDLE;
int g_h_atr  = INVALID_HANDLE;

// Group tracking
struct TradeGroup {
   int    id;
   string direction;
   double tp1, tp2, tp3;
   double tp1_close_pct;
   bool   tp1_hit;
   bool   be_moved;
   int    magic_offset;  // magic + id to differentiate groups
};
TradeGroup g_groups[];

//+------------------------------------------------------------------+
//| Expert initialisation                                             |
//+------------------------------------------------------------------+
int OnInit() {
   g_files_path = (FilesPath == "") ? "" : FilesPath;
   g_session_start_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   g_trade.SetExpertMagicNumber(MagicNumber);
   g_trade.SetDeviationInPoints(30);
   g_trade.SetTypeFilling(ORDER_FILLING_IOC);
   EventSetTimer(TimerSeconds);
   g_h_rsi  = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE);
   g_h_ma20 = iMA(_Symbol, PERIOD_H1, 20, 0, MODE_EMA, PRICE_CLOSE);
   g_h_ma50 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_h_atr  = iATR(_Symbol, PERIOD_H1, 14);
   if(g_h_rsi==INVALID_HANDLE || g_h_ma20==INVALID_HANDLE || g_h_ma50==INVALID_HANDLE || g_h_atr==INVALID_HANDLE)
      Print("FORGE: indicator handles unavailable (market closed?) — will retry on timer");
   // Print all path info for diagnostics
   Print("FORGE initialised — magic=",MagicNumber,
         " datapath=",  TerminalInfoString(TERMINAL_DATA_PATH),
         " commonpath=",TerminalInfoString(TERMINAL_COMMONDATA_PATH),
         " balance=",   AccountInfoDouble(ACCOUNT_BALANCE));
   WriteBrokerInfo();
   WriteMarketData();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) {
   EventKillTimer();
   IndicatorRelease(g_h_rsi);
   IndicatorRelease(g_h_ma20);
   IndicatorRelease(g_h_ma50);
   IndicatorRelease(g_h_atr);
   Print("FORGE deinitialised — reason=", reason);
}

//+------------------------------------------------------------------+
//| OnTimer — main cycle                                              |
//+------------------------------------------------------------------+
void OnTimer() {
   g_cycle++;
   ReadConfig();
   if(g_mode == "OFF") { WriteMarketData(); return; }
   ReadAndExecuteCommand();
   WriteMarketData();
   if(g_mode == "WATCH") WriteTickData();  // extra tick record
   WriteModeStatus();
}

//+------------------------------------------------------------------+
//| OnTick — real-time management                                     |
//+------------------------------------------------------------------+
void OnTick() {
   if(g_mode == "OFF") return;
   if(g_mode == "WATCH") { WriteTickData(); return; }
   ManageOpenGroups();
}

//+------------------------------------------------------------------+
//| Config reader                                                      |
//+------------------------------------------------------------------+
void ReadConfig() {
   string path = g_files_path + "config.json";
   int fh = FileOpen(path, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh == INVALID_HANDLE) return;
   string content = "";
   while(!FileIsEnding(fh)) content += FileReadString(fh);
   FileClose(fh);
   // Parse mode
   string mode = JsonGetString(content, "effective_mode");
   if(mode != "" && mode != g_mode) {
      Print("FORGE mode: ", g_mode, " → ", mode);
      g_mode = mode;
   }
}

//+------------------------------------------------------------------+
//| Command reader + executor                                          |
//+------------------------------------------------------------------+
void ReadAndExecuteCommand() {
   string path = g_files_path + "command.json";
   int fh = FileOpen(path, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh == INVALID_HANDLE) return;
   string content = "";
   while(!FileIsEnding(fh)) content += FileReadString(fh);
   FileClose(fh);
   if(content == "") return;

   string ts = JsonGetString(content, "timestamp");
   if(ts == g_last_cmd_ts) return;
   g_last_cmd_ts = ts;

   string action = JsonGetString(content, "action");
   Print("FORGE command: ", action);

   if(action == "OPEN_GROUP")       ExecuteOpenGroup(content);
   else if(action == "CLOSE_ALL")   ExecuteCloseAll();
   else if(action == "CLOSE_PCT")   ExecuteClosePct(content);
   else if(action == "MOVE_BE_ALL") ExecuteMoveBeAll();
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
   bool   move_be       = (JsonGetString(json, "move_be_on_tp1") == "true");

   // Parse entry ladder
   double entries[];
   ParseDoubleArray(json, "entry_ladder", entries);
   int n = ArraySize(entries);
   if(n == 0) {
      double single_entry = JsonGetDouble(json, "entry_low");
      if(single_entry == 0) return;
      ArrayResize(entries, 1);
      entries[0] = single_entry;
      n = 1;
   }

   int opened = 0;
   int group_magic = MagicNumber + group_id;
   g_trade.SetExpertMagicNumber(group_magic);

   for(int i = 0; i < n; i++) {
      double entry = entries[i];
      string comment = "FORGE|G" + IntegerToString(group_id) + "|" + IntegerToString(i);
      bool ok = false;
      if(direction == "BUY") {
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         // Use limit order if entry below current ask, else market
         if(entry < ask - 5)
            ok = g_trade.BuyLimit(lot_per_trade, NormalizeDouble(entry, _Digits), _Symbol, NormalizeDouble(sl, _Digits), NormalizeDouble(tp1, _Digits), ORDER_TIME_GTC, 0, comment);
         else
            ok = g_trade.Buy(lot_per_trade, _Symbol, ask, NormalizeDouble(sl, _Digits), NormalizeDouble(tp1, _Digits), comment);
      } else {
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         if(entry > bid + 5)
            ok = g_trade.SellLimit(lot_per_trade, NormalizeDouble(entry, _Digits), _Symbol, NormalizeDouble(sl, _Digits), NormalizeDouble(tp1, _Digits), ORDER_TIME_GTC, 0, comment);
         else
            ok = g_trade.Sell(lot_per_trade, _Symbol, bid, NormalizeDouble(sl, _Digits), NormalizeDouble(tp1, _Digits), comment);
      }
      if(ok) { opened++; Print("FORGE: Opened trade ", i+1, "/", n, " ticket=", g_trade.ResultOrder()); }
      else Print("FORGE: Failed trade ", i+1, " error=", g_trade.ResultRetcode());
      Sleep(100);  // small delay between entries
   }

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

      // Move remaining SL to breakeven
      GetGroupPositions(gm, positions);  // refresh after closes
      for(int j = 0; j < ArraySize(positions); j++) {
         if(g_pos.SelectByTicket(positions[j])) {
            double be = g_pos.PriceOpen();
            g_trade.PositionModify(positions[j], NormalizeDouble(be, _Digits), g_pos.TakeProfit());
         }
      }
      g_groups[gi].be_moved = true;
   }
}

//+------------------------------------------------------------------+
//| Close all EA positions                                             |
//+------------------------------------------------------------------+
void ExecuteCloseAll() {
   int closed = 0;
   for(int i = PositionsTotal()-1; i >= 0; i--) {
      if(g_pos.SelectByIndex(i) && g_pos.Symbol() == _Symbol) {
         // Check it's one of our magic numbers
         int pm = (int)g_pos.Magic();
         if(pm >= MagicNumber && pm < MagicNumber + 10000) {
            if(g_trade.PositionClose(g_pos.Ticket())) closed++;
         }
      }
   }
   ArrayResize(g_groups, 0);
   Print("FORGE: CLOSE_ALL — closed ", closed, " positions");
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
            double be = g_pos.PriceOpen();
            g_trade.PositionModify(g_pos.Ticket(), NormalizeDouble(be, _Digits), g_pos.TakeProfit());
         }
      }
   }
   Print("FORGE: MOVE_BE_ALL executed");
}

//+------------------------------------------------------------------+
//| Write market_data.json                                             |
//+------------------------------------------------------------------+
void WriteMarketData() {
   string path = g_files_path + "market_data.json";
   string j = "{";
   j += "\"symbol\":\"" + _Symbol + "\",";
   j += "\"hermes_version\":\"FORGE_1.0\",";
   j += "\"timestamp_utc\":\"" + TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\",";
   j += "\"timestamp_unix\":" + IntegerToString(TimeCurrent()) + ",";
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
   for(int i=0;i<PositionsTotal();i++){if(g_pos.SelectByIndex(i)&&g_pos.Symbol()==_Symbol)fp+=g_pos.Profit();}
   j += "\"total_floating_pnl\":" + DoubleToString(fp,2) + ",";
   j += "\"session_start_balance\":" + DoubleToString(g_session_start_balance,2) + ",";
   j += "\"session_pnl\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE)-g_session_start_balance,2);
   j += "},";
   // Indicators H1
   j += "\"indicators_h1\":{";
   double rsi_buf[1], ma20_buf[1], ma50_buf[1], atr_buf[1];
   double rsi_val  = (CopyBuffer(g_h_rsi, 0,0,1,rsi_buf)==1)  ? rsi_buf[0]  : 0;
   double ma20_val = (CopyBuffer(g_h_ma20,0,0,1,ma20_buf)==1) ? ma20_buf[0] : 0;
   double ma50_val = (CopyBuffer(g_h_ma50,0,0,1,ma50_buf)==1) ? ma50_buf[0] : 0;
   double atr_val  = (CopyBuffer(g_h_atr, 0,0,1,atr_buf)==1)  ? atr_buf[0]  : 0;
   j += "\"rsi_14\":" + DoubleToString(rsi_val,1)  + ",";
   j += "\"ma_20\":"  + DoubleToString(ma20_val,2) + ",";
   j += "\"ma_50\":"  + DoubleToString(ma50_val,2) + ",";
   j += "\"atr_14\":" + DoubleToString(atr_val,2);
   j += "},";
   // Open positions
   j += "\"open_positions\":[";
   bool first = true;
   for(int i=0;i<PositionsTotal();i++) {
      if(!g_pos.SelectByIndex(i) || g_pos.Symbol()!=_Symbol) continue;
      if(!first) j += ","; first=false;
      j += "{";
      j += "\"ticket\":"       + IntegerToString(g_pos.Ticket()) + ",";
      j += "\"type\":\""       + (g_pos.PositionType()==POSITION_TYPE_BUY?"BUY":"SELL") + "\",";
      j += "\"lots\":"         + DoubleToString(g_pos.Volume(),2) + ",";
      j += "\"open_price\":"   + DoubleToString(g_pos.PriceOpen(),2) + ",";
      j += "\"current_price\":" + DoubleToString(g_pos.PriceCurrent(),2) + ",";
      j += "\"sl\":"           + DoubleToString(g_pos.StopLoss(),2) + ",";
      j += "\"tp\":"           + DoubleToString(g_pos.TakeProfit(),2) + ",";
      j += "\"profit\":"       + DoubleToString(g_pos.Profit(),2) + ",";
      j += "\"magic\":"        + IntegerToString(g_pos.Magic());
      j += "}";
   }
   j += "]}";

   // Try FILE_COMMON first, fall back to local MQL5/Files
   int fh = FileOpen("market_data.json", FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fh != INVALID_HANDLE) { FileWriteString(fh, j); FileClose(fh); }
   else {
      int err1 = GetLastError();
      fh = FileOpen("market_data.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
      if(fh != INVALID_HANDLE) { FileWriteString(fh, j); FileClose(fh); Print("FORGE: wrote via local path (err_common=",err1,")"); }
      else Print("FORGE: WRITE FAILED both paths err_common=",err1," err_local=",GetLastError());
   }
}

//+------------------------------------------------------------------+
//| Write tick_data.json (WATCH mode ML collection)                   |
//+------------------------------------------------------------------+
void WriteTickData() {
   if(!LogTicks) return;
   string path = g_files_path + "tick_data.json";
   string j = "{";
   j += "\"timestamp_unix\":" + IntegerToString(TimeCurrent()) + ",";
   j += "\"mode\":\"" + g_mode + "\",";
   j += "\"bid\":"  + DoubleToString(SymbolInfoDouble(_Symbol,SYMBOL_BID),2) + ",";
   j += "\"ask\":"  + DoubleToString(SymbolInfoDouble(_Symbol,SYMBOL_ASK),2) + ",";
   j += "\"spread\":" + DoubleToString((SymbolInfoDouble(_Symbol,SYMBOL_ASK)-SymbolInfoDouble(_Symbol,SYMBOL_BID))/_Point,1);
   j += "}";
   int fh = FileOpen(path, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh != INVALID_HANDLE) { FileWriteString(fh, j); FileClose(fh); }
}

//+------------------------------------------------------------------+
//| Write mode_status.json (ATHENA)                                   |
//+------------------------------------------------------------------+
void WriteModeStatus() {
   string path = g_files_path + "mode_status.json";
   string j = "{\"mode\":\"" + g_mode + "\",";
   j += "\"cycle\":" + IntegerToString(g_cycle) + ",";
   j += "\"open_groups\":" + IntegerToString(ArraySize(g_groups)) + ",";
   j += "\"timestamp\":\"" + TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS) + "\"}";
   int fh = FileOpen(path, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh != INVALID_HANDLE) { FileWriteString(fh, j); FileClose(fh); }
}

//+------------------------------------------------------------------+
//| Write broker_info.json — account type, broker, server time       |
//+------------------------------------------------------------------+
void WriteBrokerInfo() {
   string path = g_files_path + "broker_info.json";
   string acct_type = AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO
                      ? "DEMO" : "LIVE";
   string j = "{";
   j += "\"account_type\":\"" + acct_type + "\",";
   j += "\"broker\":\"" + AccountInfoString(ACCOUNT_COMPANY) + "\",";
   j += "\"server\":\"" + AccountInfoString(ACCOUNT_SERVER) + "\",";
   j += "\"account_login\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + ",";
   j += "\"currency\":\"" + AccountInfoString(ACCOUNT_CURRENCY) + "\",";
   j += "\"leverage\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LEVERAGE)) + ",";
   j += "\"server_time\":\"" + TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS) + "\",";
   j += "\"requested_mode\":\"" + InputMode + "\",";
   j += "\"forge_version\":\"1.1.0\"";
   j += "}";
   int fh = FileOpen("broker_info.json", FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fh != INVALID_HANDLE) { FileWriteString(fh, j); FileClose(fh); Print("FORGE: broker_info.json written — ", acct_type, " @ ", AccountInfoString(ACCOUNT_SERVER)); }
   else {
      int err1 = GetLastError();
      fh = FileOpen("broker_info.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
      if(fh != INVALID_HANDLE) { FileWriteString(fh, j); FileClose(fh); Print("FORGE: broker_info.json via local path (err_common=",err1,")"); }
      else Print("FORGE: broker_info.json WRITE FAILED err_common=",err1," err_local=",GetLastError());
   }
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

string JsonGetString(const string &json, const string &key) {
   string search = "\"" + key + "\":\"";
   int start = StringFind(json, search);
   if(start < 0) return "";
   start += StringLen(search);
   int end = StringFind(json, "\"", start);
   if(end < 0) return "";
   return StringSubstr(json, start, end - start);
}

double JsonGetDouble(const string &json, const string &key) {
   string search = "\"" + key + "\":";
   int start = StringFind(json, search);
   if(start < 0) return 0;
   start += StringLen(search);
   int end = start;
   while(end < StringLen(json) && (StringSubstr(json,end,1)!=","&&StringSubstr(json,end,1)!="}")) end++;
   return StringToDouble(StringSubstr(json, start, end - start));
}

void ParseDoubleArray(const string &json, const string &key, double &arr[]) {
   string search = "\"" + key + "\":[";
   int start = StringFind(json, search);
   if(start < 0) { ArrayResize(arr,0); return; }
   start += StringLen(search);
   int end = StringFind(json, "]", start);
   if(end < 0) { ArrayResize(arr,0); return; }
   string content = StringSubstr(json, start, end - start);
   string parts[];
   int n = StringSplit(content, ',', parts);
   ArrayResize(arr, n);
   for(int i=0;i<n;i++) arr[i] = StringToDouble(parts[i]);
}
//+------------------------------------------------------------------+
