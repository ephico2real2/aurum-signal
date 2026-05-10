# FORGE EA Audit — Codex Second-Pass Review

## Finding 1: Magic Number Mismatch

File: `/Users/olasumbo/signal_system/ea/FORGE.mq5`, lines 3924-3928. Verdict: confirmed, with line drift from the first-pass report. `SIGNALS.magic` is populated from base `MagicNumber`, not `group_magic`.

```mql5
      + IntegerToString(high_vol_flag) + ", "
      + "'" + session + "', "
      + IntegerToString((long)MagicNumber) + ", 0, "
      + IntegerToString(g_tester_run_id) + ", "
      + DoubleToString(macd_hist, 6) + ", "
```

## Finding 2: H4 Incomplete Indicators

File: `/Users/olasumbo/signal_system/ea/FORGE.mq5`, lines 414-417 and 1940-1944. Verdict: confirmed. Only H4 EMA20, EMA50, and ATR handles exist, and only those three fields are written to `indicators_h4`; no H4 RSI/BB/ADX handles or output fields were found.

```mql5
// H4 — native scalper higher-TF structure (EMA20/50 + ATR; same trend_strength formula as H1)
int g_h4_ma20 = INVALID_HANDLE;
int g_h4_ma50 = INVALID_HANDLE;
int g_h4_atr  = INVALID_HANDLE;
```

```mql5
   double h4_atr_v = (CopyBuffer(g_h4_atr, 0,0,1,h4_atrb)==1) ? h4_atrb[0] : 0;
   j += "\"ema_20\":" + DoubleToString(h4_m20,2) + ",";
   j += "\"ema_50\":" + DoubleToString(h4_m50,2) + ",";
   j += "\"atr_14\":" + DoubleToString(h4_atr_v,2);
   j += "},";
```

## Finding 3: Tester Journal Sync Flag

File: `/Users/olasumbo/signal_system/python/bridge.py`, lines 159-164 and 2822-2828. Verdict: confirmed for current code. `BRIDGE_SYNC_TESTER_JOURNAL` defaults false and gates tester journal sync before `sync_forge_journal*` is called.

```python
# Journal sync: tester journals are ML training data — read directly from the
# tester DB; do NOT pollute AURUM with backtest signals/trades.
# Set BRIDGE_SYNC_TESTER_JOURNAL=1 to re-enable (e.g. for debugging).
BRIDGE_SYNC_TESTER_JOURNAL = os.environ.get("BRIDGE_SYNC_TESTER_JOURNAL", "0").strip().lower() in (
    "1", "true", "yes", "on"
)
```

```python
            for journal_path in self._resolve_forge_journal_paths():
                is_tester = "_tester" in Path(journal_path).name
                if is_tester and not BRIDGE_SYNC_TESTER_JOURNAL:
                    continue
                tag = "tester" if is_tester else "live"
                synced_sig = self._active_scribe(is_tester).sync_forge_journal(journal_path, source=tag)
```

Historical verification: before commit `b53ddd3` (`feat(bridge): gate tester journal sync + SCRIBE run_id migration`), `/Users/olasumbo/signal_system/python/bridge.py` at `b53ddd3^`, lines 2741-2748, synced every resolved journal path through `self.scribe`, including tester paths; before Phase 1 commit `14666a1`, even gated tester sync still used `self.scribe` rather than `_active_scribe(is_tester)`, so any enabled tester sync targeted the live AURUM DB.

```python
        # ── 5d. Sync FORGE signal journal → SCRIBE (every 60s)
        _now = time.time()
        if _now - getattr(self, "_last_journal_sync", 0) >= 60:
            self._last_journal_sync = _now
            for journal_path in self._resolve_forge_journal_paths():
                tag = "tester" if "_tester" in journal_path else "live"
                synced_sig = self.scribe.sync_forge_journal(journal_path, source=tag)
                synced_td = self.scribe.sync_forge_journal_trades(journal_path, source=tag)
```

## Finding 4: SELL LIMIT Cascade Slot[1]

File: `/Users/olasumbo/signal_system/ea/FORGE.mq5`, lines 5617-5624. Verdict: different than reported. Grep found no literal `g_sell_limit_stack[1] = ...` write, but slot `[1]` is populated indirectly because the placement loop iterates `_si = 0; _si < 2`; if slot `[0]` is active, the same write block fills slot `[1]`.

```mql5
      if(OrderSend(_lreq, _lres) && _lres.order > 0) {
         for(int _si = 0; _si < 2; _si++) {
            if(!g_sell_limit_stack[_si].active) {
               g_sell_limit_stack[_si].ticket    = _lres.order;
               g_sell_limit_stack[_si].group_id  = group_id;
               g_sell_limit_stack[_si].mkt_magic = (ulong)group_magic;
               g_sell_limit_stack[_si].expiry    = limit_exp;
               g_sell_limit_stack[_si].active    = true;
```

## Finding 5: Column Mapping r[29]/r[30]/r[31]

File: `/Users/olasumbo/signal_system/ea/FORGE.mq5`, lines 3892-3898 and 3925-3928; `/Users/olasumbo/signal_system/python/scribe.py`, lines 794-819. Verdict: confirmed. The FORGE insert order has `run_id`, `macd_histogram`, `m15_adx`, `lot_factor` after `synced`; SCRIBE selects `id` plus 27 fields through `magic`, then maps `r[28]` to `run_id`, `r[29]` to `macd_histogram`, `r[30]` to `m15_adx`, and `r[31]` to `lot_factor`.

```mql5
   string sql = "INSERT INTO SIGNALS "
      "(time, symbol, setup_type, direction, outcome, gate_reason, "
      "price, spread, atr, rsi, adx, bb_upper, bb_lower, bb_mid, "
      "poc_price, vwap_price, fib_50, rsi_divergence, psar_state, "
      "pattern_score, h1_trend, regime_label, regime_confidence, "
      "adx_trend_regime, high_vol_trend, session, magic, synced, run_id, "
      "macd_histogram, m15_adx, lot_factor) VALUES ("
```

```python
                for r in rows:
                    run_id     = r[28]
                    macd_hist  = r[29]
                    m15_adx_v  = r[30]
                    lot_factor = r[31]
```

## Finding 6: OnTradeTransaction TP1 Detection

File: `/Users/olasumbo/signal_system/ea/FORGE.mq5`, lines 5831-5848. Verdict: confirmed missing in `OnTradeTransaction`. The block handles closed deal events, filters to FORGE group magic, computes profit, and triggers loss cooldown / cascade pending cancellation on negative profit; it does not inspect comments, TP labels, TP price, or set `tp1_hit` for 2.7.10 ladder arming.

```mql5
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result) {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   ulong deal = trans.deal;
   if(deal == 0 || !HistoryDealSelect(deal)) return;
   long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);
```

```mql5
   if(profit < 0) {
      g_scalper_last_loss_time = TimeGMT();
      Print("FORGE: cooldown triggered after loss deal ", (long)deal, " profit=", DoubleToString(profit, 2));
      // Cancel all cascade pending orders when market position hits SL (all 4 slots)
      long _deal_magic = HistoryDealGetInteger(deal, DEAL_MAGIC);
```

## Finding 7: _calc_pips Formula

File: `/Users/olasumbo/signal_system/python/bridge.py`, lines 664-682. Verdict: confirmed fixed and committed. `git log --oneline -5` shows `914e110 fix(pips): correct XAUUSD pip formula — floor+×10, not SYMBOL_POINT`; the live `_calc_pips` implementation uses `int(cp) - int(ep)` multiplied by 10 for XAU symbols.

```python
def _calc_pips(symbol: str | None, direction: str, open_price: float, close_price: float) -> float:
    """
    Compute signed pips for a closed trade.

    XAUUSD (Gold): broker standard — discard decimal, each whole-number move = 10 pips.
```

```python
        sym = (symbol or "").upper()
        if "XAU" in sym:
            raw = (int(cp) - int(ep)) * 10
            return float(raw if direction == "BUY" else -raw)
```

## Additional Issues Not in First-Pass Audit

None found in this second-pass scope.
