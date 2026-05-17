  

⏺ Compact, single-table layout — tight cells, abbreviation legend below:

  #: 1
  Setup: BB_BREAKOUT  
  Detects: M5 close beyond BB edge + buffer
  Filters: spread, ATR, body, trend, H4_RSI, H4_ADX, H1_MACD, hid_div, D1_gate, BB_contract, news, dir_cool, regime
  Dir: BOTH
  Default: ON
  Compose: old
  ────────────────────────────────────────
  #: 2
  Setup: BB_BREAKOUT_RETEST
  Detects: Retrace to BB edge after breakout
  Filters: breakout filters + retest_window + post_breakout_bar
  Dir: BOTH
  Default: ON
  Compose: old
  ────────────────────────────────────────
  #: 3
  Setup: BB_BOUNCE
  Detects: BB outer touch → reverse to mid
  Filters: H1_strict, max_adx, rsi_div, fib_bias, regime≠VOL, cool, news                                            
  Dir: BOTH
  Default: ON
  Compose: old
  ────────────────────────────────────────
  #: 4
  Setup: BB_PULLBACK_SCALP
  Detects: Pullback to BB mid post-breakout
  Filters: spread, ATR, max_adx, flip_bars, scalp_cool, news                                                        
  Dir: BOTH
  Default: ON
  Compose: old
  ────────────────────────────────────────
  #: 5
  Setup: MOMENTUM_DUMP
  Detects: Rapid ≥1.5×ATR move
  Filters: max_rsi, min_adx, D1_bias?, chop_block, judas?, dump_cool, IR_amp?                                       
  Dir: BOTH
  Default: ON
  Compose: old
  ────────────────────────────────────────
  #: 6
  Setup: FRACTIONAL_SELL_IN_BULL
  Detects: Overbought SELL probe in TREND_BULL
  Filters: IsFractionalActive() (16 atoms) + news + dir_cool                                                        
  Dir: SELL
  Default: ON
  Compose: old
  ────────────────────────────────────────
  #: 7
  Setup: BULL_DAY_DIP_BUY
  Detects: Dip-buy on choppy bull day
  Filters: IsBullDipActive() (16 atoms) + IR_block + reentry_cool 300s + prime_amp?                                 
  Dir: BUY
  Default: ON
  Compose: old
  ────────────────────────────────────────
  #: 8
  Setup: MA_CROSSOVER
  Detects: EMA20 crosses EMA50
  Filters: Atr + AdxFloor + M15Align + Cool + Score
  Dir: BOTH
  Default: OFF
  Compose: new
  ────────────────────────────────────────
  #: 9
  Setup: VWAP_REVERSION
  Detects: Reverse after ≥N×ATR from VWAP
  Filters: Atr + Cool + Score (H1-align in detector)
  Dir: BOTH
  Default: OFF
  Compose: new
  ────────────────────────────────────────
  #: 10
  Setup: FIB_CONFLUENCE
  Detects: Retrace to fib + ≥N ref-line overlap
  Filters: Atr + Cool + Score (H1-align in detector)
  Dir: BOTH
  Default: OFF
  Compose: new
  ────────────────────────────────────────
  #: 11
  Setup: INSIDE_BAR
  Detects: bar[1] inside bar[2] → breakout
  Filters: Atr + AdxFloor + Cool + Score
  Dir: BOTH
  Default: OFF
  Compose: new
  ────────────────────────────────────────
  #: 12
  Setup: BB_SQUEEZE
  Detects: Low-pctile bandwidth → breakout
  Filters: Atr + AdxFloor + Cool + Score
  Dir: BOTH
  Default: OFF
  Compose: new
  ────────────────────────────────────────
  #: 13
  Setup: ORB
  Detects: Break of locked NY-window range
  Filters: Atr + AdxFloor + Cool + Score (detector unconditional)                                                   
  Dir: BOTH
  Default: OFF
  Compose: new
  ────────────────────────────────────────
  #: 14
  Setup: GAP_AND_GO
  Detects: Bar-time-skip + price jump
  Filters: Atr + Cool + Score
  Dir: BOTH
  Default: OFF
  Compose: new
  ────────────────────────────────────────
  #: 15
  Setup: DOUBLE_TOP
  Detects: 2 swing highs + neckline break
  Filters: swing-ring + Atr + AdxFloor + Cool + Score(−1)
  Dir: SELL
  Default: OFF
  Compose: new
  ────────────────────────────────────────
  #: 16
  Setup: DOUBLE_BOTTOM
  Detects: 2 swing lows + neckline break
  Filters: swing-ring + Atr + AdxFloor + Cool + Score(+1)
  Dir: BUY
  Default: OFF
  Compose: new
  ────────────────────────────────────────
  #: 17
  Setup: HEAD_AND_SHOULDERS
  Detects: L-H-LH swing pattern + neckline break
  Filters: swing-ring + Atr + AdxFloor + Cool + Score(−1)
  Dir: SELL
  Default: OFF
  Compose: new
  ────────────────────────────────────────
  #: 18
  Setup: INVERSE_HEAD_AND_SHOULDERS
  Detects: Valley-trough-valley + neckline break
  Filters: swing-ring + Atr + AdxFloor + Cool + Score(+1)
  Dir: BUY
  Default: OFF
  Compose: new
  ────────────────────────────────────────
  #: 19
  Setup: FLAG_PENNANT
  Detects: Impulse + consolidation + breakout
  Filters: Atr + AdxFloor + Cool + Score
  Dir: BOTH
  Default: OFF
  Compose: new
  ────────────────────────────────────────
  #: 20
  Setup: TRENDLINE_BOUNCE
  Detects: Bounce off algorithmic trendline
  Filters: swing-ring + Atr + AdxFloor + Cool + Score
  Dir: BOTH
  Default: OFF
  Compose: new
  ────────────────────────────────────────
  #: 21
  Setup: SR_FLIP
  Detects: S/R level breaks + retests as opposite
  Filters: swing-ring + Atr + AdxFloor + Cool + Score
  Dir: BOTH
  Default: OFF
  Compose: new

  Column legend

  ┌─────────┬─────────────────────────────────────────────────────────────────────┐
  │ Column  │                               Meaning                               │
  ├─────────┼─────────────────────────────────────────────────────────────────────┤
  │ #       │ Row index                                                           │
  ├─────────┼─────────────────────────────────────────────────────────────────────┤
  │ Setup   │ setup_type literal as written in EA                                 │
  ├─────────┼─────────────────────────────────────────────────────────────────────┤
  │ Detects │ What the detector function recognizes (event trigger)               │
  ├─────────┼─────────────────────────────────────────────────────────────────────┤
  │ Filters │ Gates the entry must pass after the detector fires                  │
  ├─────────┼─────────────────────────────────────────────────────────────────────┤
  │ Dir     │ BOTH = bidirectional, BUY/SELL = single-direction                   │
  ├─────────┼─────────────────────────────────────────────────────────────────────┤
  │ Default │ ON = enabled in production, OFF = operator opt-in                   │
  ├─────────┼─────────────────────────────────────────────────────────────────────┤
  │ Compose │ new = v2.7.43 layered helpers; old = monolithic v2.7.0-era dispatch │
  └─────────┴─────────────────────────────────────────────────────────────────────┘

  Filter-token cheat sheet

  ┌─────────────┬────────────────────────────────────────────┬──────────────────────────────────────────────────────┐
  │    Token    │                 Full name                  │                         Role                         │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ Atr         │ Atom_M5AtrPositive                         │ early guard: m5_atr > 0                              │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ AdxFloor    │ Filter_AdxFloor                            │ m5_adx ≥ threshold; emits SKIP <setup>_adx_below_min │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ M15Align    │ Filter_M15TrendAligned                     │ M15 EMA20/50 agrees with direction                   │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ Cool        │ Filter_Cooldown                            │ (now − last) ≥ cooldown OR bypass                    │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ Score       │ Score_SetupConfidence                      │ 0–100 informational; logged only                     │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ swing-ring  │ g_swings[64] + UpdateSwingsOnNewBar()      │ shared swing-buffer infra (Tier 3)                   │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ chop_block  │ regime_label == "RANGE" block              │ MOMENTUM_DUMP-specific                               │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ judas?      │ dump_judas_window_block (v2.7.51)          │ optional MOMENTUM_DUMP gate                          │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ IR_amp      │ IntradayReversalSellApplies()              │ INTRADAY_REVERSAL_TO_SELL amplifier                  │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ IR_block    │ entry_quality_intraday_reversal_buy_block  │ blocks BUY when IR composite fires                   │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ prime_amp?  │ bull_day_dip_buy_prime_amplifier (v2.7.51) │ optional ×N in NY_OPEN_KZ ∪ LONDON_CLOSE_KZ          │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ D1_gate     │ daily_direction_gate_enabled               │ block opposite of daily slope                        │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ hid_div     │ hidden-divergence block                    │ breakout SELL blocked when HID_BULL_DIV              │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ BB_contract │ min BB bandwidth                           │ avoid trading deepest chop                           │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ H4_*        │ H4 RSI/ADX/MACD gate                       │ HTF agreement                                        │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ regime      │ g_regime_label alignment                   │ TREND_BULL→BUY, TREND_BEAR→SELL                      │
  ├─────────────┼────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ ? suffix    │ gate is optional/operator-tunable          │ default OFF                                          │
  └─────────────┴────────────────────────────────────────────┴──────────────────────────────────────────────────────┘
  
  Universal gates (run BEFORE all 21 rows)

  session_off → killzone_trade_cap(opt) → kz_warmup(opt) → spread → entry_quality_* → direction_cooldown → post_sl_cooldown

  Summary counts
  
  ┌───────────────────────────────────┬────────────┐
  │                                   │   Count    │
  ├───────────────────────────────────┼────────────┤
  │ Total setups                      │ 21         │
  ├───────────────────────────────────┼────────────┤
  │ new compose (layered)             │ 14 (#8–21) │
  ├───────────────────────────────────┼────────────┤
  │ old compose (monolithic)          │ 7 (#1–7)   │
  ├───────────────────────────────────┼────────────┤
  │ Bidirectional → 2 direction pairs │ 15         │
  ├───────────────────────────────────┼────────────┤
  │ Single-direction → 1 pair         │ 6          │
  ├───────────────────────────────────┼────────────┤
  │ Total setup-direction pairs       │ 36         │
  ├───────────────────────────────────┼────────────┤
  │ Default ON                        │ 7          │
  ├───────────────────────────────────┼────────────┤
  │ Default OFF                       │ 14         │
  └───────────────────────────────────┴────────────┘




  base_lot = lot_sizing.fixed_lot                              (absolute base)
      × scalper_lot_factor                                     (MT5 input — global)
      × per-setup lot_factor                                   (one per setup)
      × per-direction factor                                   (where applicable)
      × ADX-tier factor                                        (SELL only on BB_BREAKOUT)
      × position-stack factor                                  (same-direction stacking penalty)
      × composite amplifier                                    (intraday_reversal, bull_day_dip prime, etc.)
      × wave_confirmation_lot_mult                             (when wave atom confirms)
  = combined lot ↓ NormalizeLot(MathMax(0.125, MathMax(SYMBOL_VOLUME_MIN, combined)))



    ┌───────────────────────────────────────┬─────────────────┬──────────────┬──────────────────────────────────────────────────────────────────┐
  │                 Knob                  │      Today      │   Proposed   │                              Reason                              │
  ├───────────────────────────────────────┼─────────────────┼──────────────┼──────────────────────────────────────────────────────────────────┤
  │ FORGE_DIRECTION_COOLDOWN_ENABLED      │ 0               │ 1            │ Cap same-direction stacking across 21 setups                     │
  ├───────────────────────────────────────┼─────────────────┼──────────────┼──────────────────────────────────────────────────────────────────┤
  │ FORGE_DIRECTION_COOLDOWN_BARS         │ 2 (M5 = 10 min) │ 2            │ Reasonable default                                               │
  ├───────────────────────────────────────┼─────────────────┼──────────────┼──────────────────────────────────────────────────────────────────┤
  │ FORGE_GATE_KZ_WARMUP_MIN              │ 0               │ 15           │ Skip first 15 min of every KZ open (arongroups stop-hunt advice) │
  ├───────────────────────────────────────┼─────────────────┼──────────────┼──────────────────────────────────────────────────────────────────┤
  │ FORGE_GATE_KILLZONE_MAX_TRADES        │ 0               │ 5            │ Cap entries per ICT window                                       │
  ├───────────────────────────────────────┼─────────────────┼──────────────┼──────────────────────────────────────────────────────────────────┤
  │ FORGE_POST_SL_COOLDOWN_SEC            │ 0               │ 600 (10 min) │ Don't re-enter into same losing regime                           │
  ├───────────────────────────────────────┼─────────────────┼──────────────┼──────────────────────────────────────────────────────────────────┤
  │ FORGE_STAGED_INITIAL_LEGS             │ 1               │ 1 (keep)     │ Single-leg is the safer first backtest                           │
  ├───────────────────────────────────────┼─────────────────┼──────────────┼──────────────────────────────────────────────────────────────────┤
  │ FORGE_STAGED_ADD_MIN_FAVORABLE_POINTS │ 500             │ 500 (keep)   │ Multi-leg unblock = separate decision after first backtest       │
  └───────────────────────────────────────┴─────────────────┴──────────────┴──────────────────────────────────────────────────────────────────┘



    Where the new composite pattern HAS touched MOMENTUM_DUMP — partial integration only:

  - INTRADAY_REVERSAL_TO_SELL_V3 is wired as a quality filter on top of MOMENTUM_DUMP BUY (ea/FORGE.mq5:9207, gate code entry_quality_intraday_reversal_buy_block). So one
  composite-style atom hangs off the chain, but the chain itself is the old structure.
  - Roadmap §75-76 (FORGE_COMPOSITE_ROADMAP.md) lists BULL_DAY_DIP_BUY_V3 + INTRADAY_REVERSAL_TO_SELL_V3 as Tier-1 candidates that would wrap MOMENTUM_DUMP BUY/SELL — but they
  haven't shipped as full composites yet.

INTRADAY_REVERSAL_TO_SELL_V3 as INTRADAY_REVERSAL_SELL

BULL_DAY_DIP_BUY_V3 as BULL_DAY_DIP_BUY




│ Distance-from-recent-high     │ not pre-computed  │ Anti-peak gate (G5017 was AT 4h high)                      │
  └───────────────────────────────┴───────────────────┴────────────────────────────────────────────────────────────┘


   1. Yes — ship Tier A + B (5 new atoms, all default-ON) (Recommended)
     ADX rising, MACD slope strong, velocity present, H1 DI cross direction, day-extreme block. Mirror BUY↔SELL. ~80 lines MQL5. Will block the current live-state bad entry + Run
      27's G5010/G5017 losses.
  2. Tier A only (3 velocity atoms)
     Just the velocity gates: ADX rising + MACD slope + velocity. Cleanest first ship. DI cross + day-extreme deferred.
  3. All 8 atoms (Tier A+B+C) — most comprehensive
     Add KZ time-of-day, ATR expansion, 2+ green bar confirmation on top. Most restrictive — fewer fires, higher quality.
  4. Type something.