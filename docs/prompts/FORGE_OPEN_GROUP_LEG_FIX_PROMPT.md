Fix three FORGE EA issues in /Users/olasumbo/signal_system.                                                                                                                                                               
                                                                                                                                                                                                                            
  Files to edit:                                                                                                                                                                                                            
  - /Users/olasumbo/signal_system/ea/FORGE.mq5                                                                                                                                                                              
  - /Users/olasumbo/signal_system/config/scalper_config.defaults.json                                                                                                                                                       
  - /Users/olasumbo/signal_system/config/scalper_config.json
                                                                                                                                                                                                                            
  Do not edit config/scalper_config.json except for the requested RR field sync, even though it is normally generated.                                                                                                      
                                                                                                                                                                                                                            
  Issue 1: OPEN_GROUP cascade legs reuse group-level absolute SL/TP instead of rebasing to each leg entry, and skipped legs are not journaled.                                                                              
  Issue 2: RR floor is 0.8; replace with configurable default 1.5.                                                                                                                                                        
  Issue 3: Fibonacci bias gate is off in config; enable it.                                                                                                                                                                 
                                                                                                                                                                                                                            
  Apply only these scoped changes.                                                                                                                                                                                          
                                                                                                                                                                                                                            
  1. In ea/FORGE.mq5, in struct ScalperConfig around lines 209-214, after:                                                                                                                                                  
     double min_rr;
  add:                                                                                                                                                                                                                      
     double min_rr_floor;                                                                                                                                                                                                 
                                                                                                                                                                                                                            
  2. In InitScalperConfig() around lines 1977-1979, change:                                                                                                                                                                 
     g_sc.min_rr = 0.8;
  to:                                                                                                                                                                                                                       
     g_sc.min_rr = 1.5;                                                                                                                                                                                                   
     g_sc.min_rr_floor = 1.5;
                                                                                                                                                                                                                            
  3. In ReadScalperConfig() around lines 2420-2423, after the existing min_rr parser:                                                                                                                                       
     if(JsonHasKey(content, "min_rr")) {                                                                                                                                                                                    
        v = JsonGetDouble(content, "min_rr");                                                                                                                                                                               
        if(v > 0 && v <= 5.0) g_sc.min_rr = v;                                                                                                                                                                            
     }                                                                                                                                                                                                                      
  insert:                                                                                                                                                                                                                 
     if(JsonHasKey(content, "min_rr_floor")) {                                                                                                                                                                              
        v = JsonGetDouble(content, "min_rr_floor");                                                                                                                                                                         
        if(v > 0 && v <= 5.0) g_sc.min_rr_floor = v;
     }                                                                                                                                                                                                                      
                                                                                                                                                                                                                            
  4. In CheckNativeScalperSetups() around lines 3835 and 3844:                                                                                                                                                              
  change:                                                                                                                                                                                                                   
     double rr_min_eff = g_sc.min_rr;                                                                                                                                                                                       
  to:                                                                                                                                                                                                                       
     double rr_min_eff = MathMax(g_sc.min_rr, g_sc.min_rr_floor);
                                                                                                                                                                                                                            
  change tester relaxation:                                                                                                                                                                                               
     rr_min_eff = MathMin(g_sc.min_rr, 1.0);                                                                                                                                                                                
  to:                                                                                                                                                                                                                       
     rr_min_eff = MathMax(1.0, MathMin(MathMax(g_sc.min_rr, g_sc.min_rr_floor), 1.5));
                                                                                                                                                                                                                            
  Expected outcome: native scalper setup RR is never below configured floor in live mode, default 1.5. Tester may relax only down to 1.0 but not below 1.0.                                                                 
                                                                                                                                                                                                                            
  5. Replace the body of PlaceOpenGroupLeg() in ea/FORGE.mq5, lines 4696-4840, with the following body. Keep the function signature unchanged.                                                                              
                                                                                                                                                                                                                          
  ) {                                                                                                                                                                                                                       
     // RR floor context: at RR=1.5 the break-even win rate is 40%                                                                                                                                                        
     // (1 / (1 + 1.5) = 0.4). At RR=2.0 it drops to 33.3%.                                                                                                                                                                 
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
        JournalRecordSignal("SKIP","open_group_" + fail_reason,"OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0);                                                                                                           
        return false;                                                                                                                                                                                                       
     }                                                                                                                                                                                                                      
     if(direction == "SELL" && StringFind(req_type, "BUY_") == 0) {                                                                                                                                                         
        order_kind = req_type;                                                                                                                                                                                              
        fail_reason = "direction/order_type mismatch";
        JournalRecordSignal("SKIP","open_group_" + fail_reason,"OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0);                                                                                                           
        return false;                                                                                                                                                                                                       
     }
     if(req_type != "BUY_MARKET" && req_type != "SELL_MARKET" && !SymbolSupportsOrderType(req_type)) {                                                                                                                      
        order_kind = req_type;                                                                                                                                                                                              
        fail_reason = "symbol does not support order type";
        JournalRecordSignal("SKIP","open_group_unsupported_order_type","OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0);                                                                                                   
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
        JournalRecordSignal("SKIP","open_group_rr_below_floor","OPEN_GROUP",direction,entry_for_stops,0,0,0,0,0,0,0,0,0,0);                                                                                                 
        return false;                                                                                                                                                                                                       
     }                                                                                                                                                                                                                      
                                                                                                                                                                                                                            
     if(req_type == "BUY_MARKET") {                                                                                                                                                                                       
        if(!ValidateStops(ask,sl_for_this,tp_for_this,ORDER_TYPE_BUY)) { fail_reason="invalid BUY market stops"; JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,ask,0,0,0,0,0,0,0,0,0,0);     
  return false; }                                                                                                                                                                                                           
        ok = g_trade.Buy(lot_norm,_Symbol,ask,NormalizeDouble(sl_for_this,_Digits),NormalizeDouble(tp_for_this,_Digits),comment); return true;
     }                                                                                                                                                                                                                      
     if(req_type == "SELL_MARKET") {                                                                                                                                                                                      
        if(!ValidateStops(bid,sl_for_this,tp_for_this,ORDER_TYPE_SELL)) { fail_reason="invalid SELL market stops"; JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,bid,0,0,0,0,0,0,0,0,0,0);   
  return false; }                                                                                                                                                                                                           
        ok = g_trade.Sell(lot_norm,_Symbol,bid,NormalizeDouble(sl_for_this,_Digits),NormalizeDouble(tp_for_this,_Digits),comment); return true;                                                                             
     }                                                                                                                                                                                                                      
     if(req_type == "BUY_LIMIT") {                                                                                                                                                                                        
        if(!ValidateStops(entry,sl_for_this,tp_for_this,ORDER_TYPE_BUY_LIMIT)) { fail_reason="invalid BUY_LIMIT stops";                                                                                                     
  JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0); return false; }                                                                                                  
        ok = g_trade.BuyLimit(lot_norm,NormalizeDouble(entry,_Digits),_Symbol,NormalizeDouble(sl_for_this,_Digits),NormalizeDouble(tp_for_this,_Digits),ORDER_TIME_GTC,0,comment); return true;                             
     }                                                                                                                                                                                                                      
     if(req_type == "SELL_LIMIT") {                                                                                                                                                                                       
        if(!ValidateStops(entry,sl_for_this,tp_for_this,ORDER_TYPE_SELL_LIMIT)) { fail_reason="invalid SELL_LIMIT stops";                                                                                                   
  JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0); return false; }                                                                                                  
        ok = g_trade.SellLimit(lot_norm,NormalizeDouble(entry,_Digits),_Symbol,NormalizeDouble(sl_for_this,_Digits),NormalizeDouble(tp_for_this,_Digits),ORDER_TIME_GTC,0,comment); return true;                            
     }                                                                                                                                                                                                                      
     if(req_type == "BUY_STOP") {                                                                                                                                                                                         
        if(!ValidateStops(entry,sl_for_this,tp_for_this,ORDER_TYPE_BUY_STOP)) { fail_reason="invalid BUY_STOP stops";                                                                                                       
  JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0); return false; }                                                                                                  
        ok = g_trade.BuyStop(lot_norm,NormalizeDouble(entry,_Digits),_Symbol,NormalizeDouble(sl_for_this,_Digits),NormalizeDouble(tp_for_this,_Digits),ORDER_TIME_GTC,0,comment); return true;
     }                                                                                                                                                                                                                      
     if(req_type == "SELL_STOP") {                                                                                                                                                                                        
        if(!ValidateStops(entry,sl_for_this,tp_for_this,ORDER_TYPE_SELL_STOP)) { fail_reason="invalid SELL_STOP stops";                                                                                                     
  JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0); return false; }                                                                                                  
        ok = g_trade.SellStop(lot_norm,NormalizeDouble(entry,_Digits),_Symbol,NormalizeDouble(sl_for_this,_Digits),NormalizeDouble(tp_for_this,_Digits),ORDER_TIME_GTC,0,comment); return true;                             
     }                                                                                                                                                                                                                      
     if(req_type == "BUY_STOP_LIMIT" || req_type == "SELL_STOP_LIMIT") {                                                                                                                                                  
        double slp = leg.stoplimit_price;                                                                                                                                                                                   
        if(slp <= 0) { fail_reason="missing stoplimit_price"; JournalRecordSignal("SKIP","open_group_missing_stoplimit","OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0); return false; }                                  
        if(req_type == "BUY_STOP_LIMIT") {                                                                                                                                                                                  
           if(entry <= ask + entry_tolerance) { fail_reason="BUY_STOP_LIMIT trigger must be above current ask";                                                                                                             
  JournalRecordSignal("SKIP","open_group_bad_stoplimit_trigger","OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0); return false; }                                                                                          
           if(slp > entry) { fail_reason="BUY_STOP_LIMIT stoplimit_price must be <= trigger"; JournalRecordSignal("SKIP","open_group_bad_stoplimit_price","OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0); return false; }
        } else {                                                                                                                                                                                                            
           if(entry >= bid - entry_tolerance) { fail_reason="SELL_STOP_LIMIT trigger must be below current bid";                                                                                                          
  JournalRecordSignal("SKIP","open_group_bad_stoplimit_trigger","OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0); return false; }                                                                                          
           if(slp < entry) { fail_reason="SELL_STOP_LIMIT stoplimit_price must be >= trigger"; JournalRecordSignal("SKIP","open_group_bad_stoplimit_price","OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0); return false;
  }                                                                                                                                                                                                                         
        }                                                                                                                                                                                                                 
        MqlTradeRequest req; MqlTradeResult res; ZeroMemory(req); ZeroMemory(res);                                                                                                                                          
        req.action=TRADE_ACTION_PENDING; req.symbol=_Symbol; req.magic=(ulong)group_magic; req.volume=lot_norm;                                                                                                             
        req.type=(req_type=="BUY_STOP_LIMIT")?ORDER_TYPE_BUY_STOP_LIMIT:ORDER_TYPE_SELL_STOP_LIMIT;                                                                                                                         
        req.price=NormalizeDouble(entry,_Digits); req.stoplimit=NormalizeDouble(slp,_Digits);                                                                                                                               
        if(!ValidateStops(entry,sl_for_this,tp_for_this,req.type)) { fail_reason="invalid stop-limit stops"; JournalRecordSignal("SKIP","open_group_invalid_stops","OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0); return
   false; }                                                                                                                                                                                                                 
        req.sl=NormalizeDouble(sl_for_this,_Digits); req.tp=NormalizeDouble(tp_for_this,_Digits);                                                                                                                         
        req.type_time=ORDER_TIME_GTC; req.deviation=30; req.comment=comment;                                                                                                                                                
        ok=OrderSend(req,res);                                                                                                                                                                                              
        if(!ok) Print("FORGE: stop-limit send failed retcode=",(int)res.retcode," type=",req_type);
        return true;                                                                                                                                                                                                        
     }                                                                                                                                                                                                                    
     fail_reason = "unsupported order_type";                                                                                                                                                                                
     JournalRecordSignal("SKIP","open_group_unsupported_order_type","OPEN_GROUP",direction,entry,0,0,0,0,0,0,0,0,0,0);                                                                                                      
  }                                                                                                                                                                                                                         
                                                                                                                                                                                                                            
  Expected outcomes:                                                                                                                                                                                                        
  - SELL_STOP/BUY_STOP/LIMIT legs each get SL/TP rebased from the group reference entry to their own actual entry.                                                                                                        
  - Any leg with RR below g_sc.min_rr_floor is skipped, logged via PrintFormat, and recorded via JournalRecordSignal("SKIP","open_group_rr_below_floor",...).
  - Skipping one leg still does not abort the group, but skips are no longer journal-silent.                                                                                                                                
                                                                                                                                                                                                                            
  6. In config/scalper_config.defaults.json:                                                                                                                                                                                
  - Change "min_rr": 0.8 to:                                                                                                                                                                                                
      "min_rr": 1.5,                                                                                                                                                                                                      
      "min_rr_floor": 1.5,                                                                                                                                                                                                  
  - Change "fib_bias_enabled": 0 to:                                                                                                                                                                                      
      "fib_bias_enabled": 1,                                                                                                                                                                                                
                            
  7. In config/scalper_config.json:                                                                                                                                                                                         
  - Change "min_rr": 0.8 to:                                                                                                                                                                                                
      "min_rr": 1.5,        
      "min_rr_floor": 1.5,                                                                                                                                                                                                  
  - Change "fib_bias_enabled": 0 to:                                                                                                                                                                                      
      "fib_bias_enabled": 1,        
                                                                                                                                                                                                                            
  8. Verification after edits — run:
    rg -n '"min_rr"|"min_rr_floor"|"fib_bias_enabled"|min_rr_floor|RR floor context|open_group_rr_below_floor|sl_for_this|tp_for_this' ea/FORGE.mq5 config/scalper_config.json config/scalper_config.defaults.json          
  Confirm:                                                                                                                                                                                                                
  - ea/FORGE.mq5 has g_sc.min_rr = 1.5 and g_sc.min_rr_floor = 1.5                                                                                                                                                          
  - Both JSON files have "min_rr": 1.5 and "min_rr_floor": 1.5    
  - Both JSON files have "fib_bias_enabled": 1                                                                                                                                                                              
  - PlaceOpenGroupLeg() contains the RR break-even comment                                                                                                                                                                
  - PlaceOpenGroupLeg() rebases SL/TP per leg using sl_for_this / tp_for_this                                                                                                                                               
  - PlaceOpenGroupLeg() records JournalRecordSignal("SKIP","open_group_rr_below_floor",...)                                                                                                                               
  - No unrelated functions were refactored


---

## Phase 2 — Stop Loss Width Fix (2026-05-07)

### Problem

The original SL configuration was too tight to survive normal XAUUSD M5 noise:

| Parameter | Old Value | Problem |
|---|---|---|
| `bb_bounce.sl_atr_mult` | `1.5` | Initial bounce SL anchor — too close |
| `bb_breakout.sl_atr_mult` | `1.5` | Breakout SL anchor — too close |
| `min_sl_atr_mult` | `0.8` | Floor was narrower than the primary multiplier — meaningless |
| `native_sl_extra_buffer_points` | `0` | No cushion above the ATR distance |
| Breakout SL | ATR-only | `FindStructuralSL()` was never called for breakout entries |

With M5 ATR ≈ $2.00 on live XAUUSD, the `0.8 ATR` floor produced a $1.60 SL — well inside a single candle wick. Breakout entries had no structural awareness at all.

### Changes Applied

**ea/FORGE.mq5 — InitScalperConfig() defaults:**
- `g_sc.bounce_sl_atr_mult`: `1.2` → `2.0` (line ~1926)
- `g_sc.breakout_sl_atr_mult`: `1.5` → `2.0` (line ~1933)
- `g_sc.min_sl_atr_mult`: `0.8` → `1.5` (line ~1978) — floor now equals primary multiplier
- `g_sc.native_sl_extra_buffer_points`: `0.0` → `5.0` (line ~1981)

**ea/FORGE.mq5 — Breakout SL now calls FindStructuralSL():**

BUY breakout (was pure ATR, now structural):
```cpp
// Before
double bo_sl  = NormalizeDouble(bid - m5_atr * breakout_sl_mult_eff, _Digits);

// After
double bo_sl_atr = NormalizeDouble(bid - m5_atr * breakout_sl_mult_eff, _Digits);
double bo_sl = FindStructuralSL(true, bid, bo_sl_atr, point);
```

SELL breakout (same pattern):
```cpp
// Before
double bo_sl  = NormalizeDouble(ask + m5_atr * breakout_sl_mult_eff, _Digits);

// After
double bo_sl_atr = NormalizeDouble(ask + m5_atr * breakout_sl_mult_eff, _Digits);
double bo_sl = FindStructuralSL(false, ask, bo_sl_atr, point);
```

**config/scalper_config.json + config/scalper_config.defaults.json:**
- `bb_bounce.sl_atr_mult`: `1.5` → `2.0`
- `bb_breakout.sl_atr_mult`: `1.5` → `2.0`
- `min_sl_atr_mult`: `0.8` → `1.5`
- `native_sl_extra_buffer_points`: `0` → `5`

### Effect on SL Width (M5 ATR = $2.00, live XAUUSD)

| Scenario | Old SL distance | New SL distance |
|---|---|---|
| Bounce (normal) | $3.00 (1.5 ATR) | $4.00 (2.0 ATR) + $0.05 buffer |
| Bounce (floor triggered) | $1.60 (0.8 ATR) | $3.00 (1.5 ATR) + $0.05 buffer |
| Breakout (normal) | $3.00 (1.5 ATR), no structure | $4.00 + OB zone widening |
| Breakout (high-vol boost) | $3.75 (1.875 ATR) | $5.00 (2.5 ATR) + OB zone |

### Verification

```bash
grep -n "bounce_sl_atr_mult\|breakout_sl_atr_mult\|min_sl_atr_mult\|native_sl_extra_buffer\|FindStructuralSL" \
  ea/FORGE.mq5 config/scalper_config.json config/scalper_config.defaults.json
```

Confirm:
- EA init: `bounce_sl_atr_mult = 2.0`, `breakout_sl_atr_mult = 2.0`, `min_sl_atr_mult = 1.5`, `native_sl_extra_buffer_points = 5.0`
- Both JSONs: `sl_atr_mult: 2.0` (bounce and breakout sections), `min_sl_atr_mult: 1.5`, `native_sl_extra_buffer_points: 5`
- Breakout BUY: `FindStructuralSL(true, bid, bo_sl_atr, point)` present
- Breakout SELL: `FindStructuralSL(false, ask, bo_sl_atr, point)` present


---

## Phase 3 — Backtest Analysis Fixes (2026-05-07)

### Context

FORGE 2.6.0 backtest run against 2026-04-14 to 2026-04-17 XAUUSD. 20,379 signals evaluated. Key findings came from live journal DB monitoring.

### Problems Found

**Problem 1 — open_groups cap jam**

The `open_groups` gate produced 17,612 skips, or 86% of all skips:

- April 15 London afternoon burst opened 4 simultaneous SELL groups
- `max_open_groups` was `4` — all 4 slots filled at once
- Gate froze for 3 days and blocked all new entries
- April 17 bull surge (+80 pts) stopped out all 4 held SELL groups simultaneously, causing a -$23 drawdown in one event

**Problem 2 — bb_bounce sl_atr_mult 2.0 too wide**

The `bb_bounce` SL was too wide for mean-reversion entries and rejected every BUY bounce setup:

- `bounce_sl_atr_mult` at `2.0 ATR` produces SL distances of 8–14 points
- BB band spread (`BB_lower` to `BB_upper`) rarely covers 1.5× that distance for TP2
- `rr_too_low` gate rejected all 92 BUY bounce setups across 4 days
- BUY bounce at ATR=5.55: SL distance = 11.1 pts, `BB_upper` only 16 pts away → RR=1.44, just below the 1.5 floor
- `BB_BOUNCE` is mean-reversion — SL should be tighter than breakout, not equal
- `BB_BREAKOUT` correctly keeps `2.0 ATR` because trend-following needs room

**Problem 3 — direction_cooldown behaviour**

The `direction_cooldown` gate was noisy in tester logs but was not the primary cause of missing BUY entries:

- `direction_cooldown_bars = 2` (10 min post-entry cooldown) — already low
- EA checks every tick in tester, producing 1,517 logged BUY skips across 13 SELL entry windows
- After cooldown clears, BUY setups immediately hit `rr_too_low` anyway
- Root cause of zero BUYs is Problem 2 (RR), not cooldown duration
- `direction_cooldown` is working as designed — it is not the primary fix target

### Fixes Applied

2026-05-07 hot-loadable config changes — no compile needed.

**config/scalper_config.json + config/scalper_config.defaults.json — open group cap:**
- `safety.max_open_groups`: `4` → `2`
- Limits simultaneous exposure to 2 groups maximum
- Prevents a single-session burst from locking out all entries for days
- Halves maximum drawdown on correlated stop-out events
- EA hot-loads this change immediately on next tick

**config/scalper_config.json + config/scalper_config.defaults.json — bounce SL width:**
- `bb_bounce.sl_atr_mult`: `2.0` → `1.5`
- Restores bounce SL to the mean-reversion appropriate width
- At ATR=5.55: SL distance drops from 11.1 to 8.3 pts, `BB_upper` 16 pts away → RR=1.93, passing the 1.5 floor
- `bb_breakout.sl_atr_mult` remains at `2.0` (trend-following, kept wide)
- Unblocks BUY bounce entries immediately

**direction_cooldown — documented, not changed:**
- `direction_cooldown_bars`: `2` is already low — no change needed
- `FORGE.mq5` line 2750: `if(bars_since < g_sc.direction_cooldown_bars)`
- If BUY entries remain absent after Fix 2, option: set `direction_cooldown_enabled: 0`
- Not applied yet — verify BUY entries appear after Fix 2 first

### Expected Improvement for Next Run

- `open_groups` cap of `2` → max 2 concurrent groups, gate clears after each close
- Bounce SL at `1.5 ATR` → BUY bounces qualify at RR 1.5–2.0 in normal ATR range
- Estimated entry rate: 2–3× current (14 entries/4 days → 28–40 entries)
- P&L stability: max correlated stop-out halved

### Verification

```bash
grep -n "max_open_groups\|sl_atr_mult" config/scalper_config.json
```

Confirm:
- `max_open_groups = 2`
- `bb_bounce.sl_atr_mult = 1.5`
- `bb_breakout.sl_atr_mult = 2.0`


---

## Phase 4 — open_groups Lifecycle Bug Fix + Bidirectional Trading (2026-05-07)

### Problem 1 — open_groups Counter Never Clears

The 17,612 `open_groups` skips over 3 days were not a config issue — they were a critical lifecycle bug.

Root cause: `ScalperOpenGroupCount()` counts unique FORGE magics from live MT5 positions and pending orders:

- Positions path: line 2747
- Pending orders path: line 2766

When a group's positions all close, any remaining staged or pending legs for that group still hold their magic. `ScalperOpenGroupCount()` counted those orphan pending orders as open groups. `ManageOpenGroups()` had no path to cancel orphan pendings or remove the group from `g_groups[]` after positions went flat.

The result: every group that closed left a ghost footprint in the open count. 4 groups opened on April 15 → all 4 remained "open" in `ScalperOpenGroupCount()` for 72 hours → the gate permanently blocked at `max_open_groups = 4` for the entire rest of the backtest.

Reducing `max_open_groups` to `2` does not fix this bug — it just jams at 2 instead of 4.

### Fix Applied — ea/FORGE.mq5

Requires compile.

Four targeted changes:

**TradeGroup lifecycle state:**
- Added `had_positions` bool field to `TradeGroup` struct (line 387)
- Tracks whether the group ever had live MT5 positions

**Group registration and rebuild initialisation:**
- `had_positions` initialised to `false` on group registration (lines 972, 4475)
- `had_positions` set to `true` when positions are first detected (lines 984, 4487, 4657)

**New lifecycle helpers:**
- `CountGroupPendingOrders(int magic)` at line 1141 — counts pending orders for a magic
- `CancelGroupPendingOrders(int magic)` at line 1152 — cancels and counts orphan pending orders
- `RemoveGroupAt(int index)` at line 1164 — removes group from `g_groups[]` by shifting the array

**ManageOpenGroups() cleanup paths:**
- `ManageOpenGroups()` starts at line 1175
- If `had_positions = true` and the group now has zero positions: cancel all orphan pending orders for that magic, call `RemoveGroupAt()`, and log how many were cancelled
- If `had_positions = false`, zero positions, zero pending orders, and staging is not active: remove the group from `g_groups[]`
- Both paths decrement `gi` and continue so the loop index stays valid after removal

### Verification

```bash
grep -n "had_positions\|CancelGroupPendingOrders\|RemoveGroupAt\|CountGroupPendingOrders" ea/FORGE.mq5
```

Confirm:
- `had_positions` exists in `TradeGroup`
- `CountGroupPendingOrders()`, `CancelGroupPendingOrders()`, and `RemoveGroupAt()` are present
- `ManageOpenGroups()` contains both cleanup paths

### Problem 2 — direction_cooldown Blocking Bidirectional Trading

Philosophy: if the market is bearish the EA must sell aggressively, if bullish it must buy aggressively. No mercy — the EA must follow the market in both directions without artificial cooldown gates preventing direction flips.

The `direction_cooldown` gate was blocking all 1,517 BUY attempts across 4 days because every SELL entry reset the cooldown timer, and BUY setups that survived the cooldown then failed the RR gate due to Problem 2 from Phase 3 (`bb_bounce` SL too wide).

The cooldown is an anti-whipsaw device designed for a different market context. For XAUUSD scalping with `BB_BOUNCE`, the RR gate already prevents chasing — `direction_cooldown` is redundant and harmful.

### Fix Applied — config

Hot-loadable config change — no compile needed.

**config/scalper_config.json + config/scalper_config.defaults.json:**
- `direction_cooldown_enabled`: `1` → `0`
- EA hot-loads this change immediately
- `direction_cooldown_bars: 2` is preserved but inactive
- Can be re-enabled by flipping the flag if needed

The RR gate (`min_rr = 1.5`, `max(tp1,tp2)` reward) provides sufficient whipsaw protection on its own. If a SELL bounce fires and price immediately reverses to BB lower, a BUY bounce there still needs RR ≥ 1.5 at the new entry. The RR gate blocks the bad flip; the cooldown is not needed.

### All Phase 4 Config Changes

Hot-loaded:

- `direction_cooldown_enabled`: `1` → `0`
- `max_open_groups`: `4` → `2` (from Phase 3, already applied)
- `bb_bounce.sl_atr_mult`: `2.0` → `1.5` (from Phase 3, already applied)

### Expected Outcome for Next Backtest Run

- `open_groups` counter clears correctly after each group closes → gate no longer jams
- BUY and SELL entries both active in all sessions
- `direction_cooldown` no longer blocks 75%+ of BUY signals
- Entry rate expected: 3–5× the 14-entry run (Phase 3 baseline)
