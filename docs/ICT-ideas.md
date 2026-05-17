═══════════════════════════════════════════════════════════════════════════════
                  HYBRID ICT TRADING SYSTEM ARCHITECTURE
                MQL5 (MT5)  ⇄  Python Brain  ⇄  QuestDB
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────── MQL5 / MT5 ZONE (EA, ingress) ──────────────────────────┐
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P0] Tick/Bar Feed Forwarder                                    │      │
│  │  • OnTick + OnBar(close) publishers                              │      │
│  │  • Symbols × TFs: M1/M5/M15/H1/H4/D1                             │      │
│  │  • Account state, spread, server time, broker session            │      │
│  │  • Transport: ZeroMQ PUB  (alt: named pipe, MT5 Python pkg)      │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
└─────────────────────────────────┼──────────────────────────────────────────┘
                                  │  ticks, closed bars, account, heartbeat
═════════════════════════════════ ▼ ═══════════════════════════════════════════
┌─────────────────────── PYTHON BRAIN (asyncio) ─────────────────────────────┐
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P0] Bridge Listener + Bar-Close Authority                      │      │
│  │  • ZMQ SUB → in-memory event bus                                 │      │
│  │  • HARD RULE: engines see ONLY closed bars (anti-lookahead)      │      │
│  │  • UTC internally, NY-time for killzones, broker-time for orders │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P1] Market Data Normalizer                                     │      │
│  │  • HTF aggregation, session tags, killzone windows               │      │
│  │  • PDH/PDL, PWH/PWL, Asia H/L, prior session H/L                 │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P2] Swing Engine   ← BUILD FIRST. Everything downstream depends│      │
│  │  • Fractal swing H/L per TF with confirmation lag                │      │
│  │  • Strict bar-close, no peek; unit-tested against fixtures       │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P2] Dealing Range Engine                                       │      │
│  │  • Active HTF swing pair → premium / discount / EQ / OTE band    │      │
│  │  • Explicit refresh rule (when does the range expire?)           │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P3] Liquidity Map                                              │      │
│  │  • Equal H/L, PDH/PDL, PWH/PWL, Asia H/L, session H/L            │      │
│  │  • Internal vs external; per-level strength score                │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P3] Sweep Detector                                             │      │
│  │  • Wick beyond level + close back inside (parametrized)          │      │
│  │  • Outputs: direction, level_id, strength, rejection quality     │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P4] MSS / CHoCH Engine                                         │      │
│  │  • CHoCH = early shift; MSS = swing break + displacement         │      │
│  │  • Gated on upstream sweep within lookback window                │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P4] Displacement Validator                                     │      │
│  │  • Body/ATR ratio, close-beyond-structure, momentum direction    │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P5] FVG Engine  (with state)                                   │      │
│  │  • 3-candle imbalance; tracks untouched/partial/CE/invalidated   │      │
│  │  • Overlap flag with OB and OTE band                             │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P5] Order Block / PD Array Engine  (with state)                │      │
│  │  • OB, Breaker, Mitigation Block, Liquidity Void                 │      │
│  │  • Mitigation state: virgin / touched / mitigated / broken       │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P6] Context Gates  (hard pre-filters)                          │      │
│  │  • HTF bias alignment (H4/D1)                                    │      │
│  │  • Chop / dead-tape detector (ATR percentile, range expansion)   │      │
│  │  • Killzone window + spread + news lockout                       │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P7] Unified Setup Model  (parameterized — NOT branched)        │      │
│  │  • One model: SWEEP→MSS→DISPLACE→PD-ARRAY→ENTRY                  │      │
│  │  • Variants = parameter sets (session, direction, target liq)    │      │
│  │  • Avoids per-strategy code branches that invite overfit         │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P7] Filter Chain  (negative space, every skip logged)          │      │
│  │  SKIP_NO_SWEEP / SKIP_NO_MSS / SKIP_WEAK_DISPLACEMENT /          │      │
│  │  SKIP_NO_VALID_FVG / SKIP_BUY_PREMIUM / SKIP_SELL_DISCOUNT /     │      │
│  │  SKIP_OUTSIDE_KZ / SKIP_SPREAD / SKIP_NEWS / SKIP_CHOP /         │      │
│  │  SKIP_FVG_FILLED / SKIP_OB_MITIGATED / SKIP_HTF_CONFLICT         │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P7] Scoring Engine  (confluence)                               │      │
│  │  • Per-component scores stored individually in QuestDB           │      │
│  │  • v1 = heuristic weights; v2 = fit OOS via walk-forward         │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P8] Risk Engine                                                │      │
│  │  • SL beyond swept liq / OB / FVG invalidation                   │      │
│  │  • Size = $risk ÷ SL distance × pip value                        │      │
│  │  • Daily DD, session loss, max trades / killzone, cooldown       │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P8] Entry Geometry + Trade State Machine                       │      │
│  │  IDLE → MAPPED → SWEPT → MSS_OK → ARMED → ENTERED →             │      │
│  │  MANAGING → PARTIAL → EXITED → COOLDOWN                         │      │
│  │  Entry: FVG retrace / CE / OB mitigation                        │      │
│  │  Targets: TP1 internal liq, TP2 external liq, TP3 HTF pool      │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                 │                                          │
└─────────────────────────────────┼──────────────────────────────────────────┘
                                  │  order intent (symbol, side, vol, SL, TP)
═════════════════════════════════ ▼ ═══════════════════════════════════════════
┌─────────────────── MQL5 / MT5 ZONE (EA, egress) ───────────────────────────┐
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │  [P8] Order Executor (MQL5)                                      │      │
│  │  • OrderSend / OrderModify / partial close / trail               │      │
│  │  • Slippage guard, requote retry, fill policy, magic number      │      │
│  │  • Position reconciliation → publish back to Python              │      │
│  │  • Heartbeat + watchdog (kill switch if bridge silent N sec)     │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

══════════════════════ CROSS-CUTTING: QuestDB ════════════════════════════════
Every engine writes events. Time-partitioned, symbol-tagged.

  ticks(ts, sym, bid, ask, spread)
  bars(ts, sym, tf, o, h, l, c, v)
  swings(ts, sym, tf, type, price, confirmed_at)
  dealing_range(ts, sym, hi, lo, eq, state)
  liquidity_levels(ts, sym, kind, price, strength, swept_at)
  sweeps(ts, sym, dir, level_id, strength, rejection_q)
  mss_events(ts, sym, dir, broken_swing_id, displacement_score)
  fvgs(ts, sym, hi, lo, mid, state, mitigated_pct, overlaps)
  order_blocks(ts, sym, hi, lo, side, state)
  context(ts, sym, htf_bias, chop_score, killzone, spread, news_lock)
  scores(ts, sym, components_json, total, passed)
  skips(ts, sym, reason, context_json)            ← gold for debugging
  decisions(ts, sym, model_params, entry, sl, tps)
  orders(ts, ticket, action, price, slippage, latency_ms)
  trades(ts, ticket, pnl, r_multiple, exit_reason)

══════════════════════ CROSS-CUTTING: Validation ═════════════════════════════
  • Bar-replay backtester (OHLC interpolation, optional tick replay)
  • Walk-forward harness (rolling train/test, no peeking)
  • Regime-stratified PnL (trending vs ranging vs news)
  • Shadow mode: full pipeline, no OrderSend — diff vs live
  • Random-entry baseline (proves the model adds edge vs the SL/TP geometry)
  • Lookahead-bias assertion suite (CI-blocking)