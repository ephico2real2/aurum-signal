# MT5 ↔ Bridge Integration — Architecture, Latency, and Direct-Broker Path

> Covers: how Bridge communicates with MT5, where regime inference fits, real-time vs delayed data,
> latency reality for retail scalping, and a recommended path to direct broker integration.

---

## 1. Current Integration Model — JSON File Bus

Bridge and the FORGE EA communicate entirely through **shared JSON files on disk**.
There is no HTTP server, no sockets, no named pipes, and no shared memory.

```
signal_system/MT5/  ──symlink──►  ~/Library/.../MetaQuotes/Terminal/Common/Files/
```

The `MT5/` directory in the repo is a symlink into MT5's `Common/Files` folder —
the one filesystem path that MT5 exposes across all terminals on the host.
A macOS Python process (Bridge) and a Wine/MT5 Windows process (FORGE EA)
read and write the same physical files through this symlink.

### File bus contract

```
FORGE EA (MQL5, MT5 terminal)             Python (bridge.py, 1s loop)
──────────────────────────────            ──────────────────────────────────────
MT5/market_data.json  ─────────────────►  bridge._tick() reads every 1s
MT5/tick_data.json    ─────────────────►  (raw price ticks, spread)
MT5/broker_info.json  ─────────────────►  (symbol specs, min lot, account type)

MT5/config.json       ◄─────────────────  bridge writes: regime label/confidence,
                                           mode, gates, lot sizing, regime policy
MT5/command.json      ◄─────────────────  bridge writes: trade open/modify/close
MT5/scalper_entry.json ◄────────────────  bridge writes: entry price ladder
MT5/scalper_config.json ◄───────────────  bridge writes: scalper parameters
```

**FORGE EA writes `market_data.json` every EA tick.** Contents include:
live bid/ask, account equity/balance, open positions, pending orders,
recent closed deals, M5/M15/H1 indicators (ADX, EMA20/50, BB, RSI),
session label, ATR, and an `ea_cycle` counter.

**Bridge reads `market_data.json` in its 1-second Python loop** (`_tick()`),
parses it as a dict, and passes it directly to the regime engine, AEGIS,
and signal processing — no DB roundtrip on the hot path.

**Bridge writes `config.json` back** — FORGE reads this every EA tick to pick up
regime label, mode, gate thresholds, and lot sizing without waiting for Bridge.

---

## 2. Where Regime Inference Sits in the Tick Loop

```
MT5 terminal (EA tick)
    │
    │  writes market_data.json every tick
    ▼
bridge._tick()  [every 1 second, BRIDGE_LOOP_SEC=1]
    │
    ├─► _refresh_regime_snapshot(mt5)
    │       │
    │       ├─ reads lens_snapshot.json  (LENS/TradingView, up to 5s old)
    │       │
    │       └─► regime_engine.infer(mt5, session, mode, lens)
    │                │
    │                ├─ HMM predict_proba()  [<1ms, inference only]
    │                │  (or Gaussian fallback if HMM not ready)
    │                │
    │                └─ returns: label, confidence, posterior
    │
    ├─► _write_config()  →  MT5/config.json  (FORGE reads next tick)
    ├─► scribe.log_market_regime()  →  market_regimes table (on transition / 30s)
    └─► _regime_snapshot  →  status.json, /api/regime/current
```

**Key property:** the `mt5` dict passed to `regime_engine.infer()` is the live snapshot
from that same bridge tick — it has **never touched Scribe or any DB**.
Scribe only sees the regime *output* (label, confidence) after inference.

---

## 3. Regime Engine — Purpose and Role

The regime engine answers one question every second:
**"What kind of market are we in right now?"**

Without it, FORGE and AEGIS treat all signals the same regardless of context.
A BB breakout in a clean trend and a BB breakout in choppy noise look identical
to RSI/ADX indicators — the regime engine is what distinguishes them.

### Output labels

| Label | Meaning |
|---|---|
| `TREND_BULL` | ADX ≥ 25, EMA20 > EMA50, positive return bias |
| `TREND_BEAR` | ADX ≥ 25, EMA20 < EMA50, negative return bias |
| `VOLATILE` | High volatility relative to recent baseline, direction unclear |
| `RANGE` | Low ADX, flat EMAs, contained price movement |
| `UNKNOWN` | Insufficient data (cold start) |

### How consumers use it

| Consumer | Gate |
|---|---|
| `AEGIS._regime_countertrend_reject()` | Hard-blocks SELL in TREND_BULL, BUY in TREND_BEAR (conf ≥ 0.55) |
| `AEGIS._resolve_signal_regime_policy()` | Shifts entry ladder weighting (aggressive vs conservative) |
| `FORGE NativeScalperRegimeBlocksDirection()` | Same countertrend gate in MQL5 (native scalper path) |
| `FORGE ForgeResolveNumTrades()` | VOLATILE → one fewer leg; RANGE → one extra leg |
| `Scribe log_market_regime()` | Persists to `market_regimes` table |
| `Athena /api/regime/current` | Live UI display |

### Feature vector — dual data source

The engine blends MT5 (always available) with LENS/TradingView (when fresh ≤ 90s):

```
Feature            Fresh LENS         Stale LENS (> 90s)
──────────────     ────────────       ──────────────────
ema_spread         LENS               MT5 fallback
adx                LENS               MT5 fallback
bb_width           LENS               MT5 fallback
rsi_centered       LENS               0.0  ← degrades
macd_hist          LENS               0.0  ← degrades
tv_recommend       LENS               0.0  ← degrades
lens_price_delta   LENS               0.0  ← degrades
```

Features 7–10 collapsing to zero when LENS is stale materially degrades
directional discrimination. MT5 alone keeps the engine running; LENS makes it smarter.

### Model

- **Primary:** `hmmlearn.GaussianHMM` (3 states, `full` covariance)
- **Training:** unsupervised, from last 5000 feature vectors, retrained every hour
- **Inference:** `predict_proba()` only, < 1ms — does **not** block the bridge tick
- **Retraining:** runs in a background daemon thread — the bridge tick is never blocked
- **Persistence:** model pickled to `python/data/regime_hmm.pkl` after each retrain;
  restored on bridge restart to eliminate the ~2-minute cold-start
- **Fallback:** deterministic Gaussian rule-set used until 120 samples are collected

---

## 4. Latency Reality — Signal Path vs Native Scalper Path

### Signal path (Telegram → trade)

```
TradingView publishes signal
    │
    ▼  Telegram delivery          200ms – 2s
listener.py receives
    │
    ▼  file write                 ~1ms
parsed_signal.json
    │
    ▼  bridge poll (worst case)   0 – 1000ms
AEGIS gates                       ~1ms
    │
    ▼  file write                 ~1ms
MT5/command.json
    │
    ▼  FORGE EA reads next tick   50 – 200ms
broker execution                  20 – 200ms
────────────────────────────────────────────
Total end-to-end                  ~0.5s – 5s
```

### Native scalper path (FORGE autonomous)

```
MT5 price tick
    │
    ▼  FORGE EA detects BB breakout in MQL5
       (reads regime/mode from config.json — already written by bridge)
    │
    ▼  FORGE places order directly via MT5 API
broker execution                  20 – 200ms
────────────────────────────────────────────
Total                             ~20 – 200ms
```

**The 1-second bridge loop is not in the native scalper execution path.**
Bridge governs the EA via `config.json` (updated every tick), but FORGE
fires orders itself using live MT5 price data — no bridge approval needed per order.

### Binding constraint

For retail XAUUSD via MT5 the true floor is **broker execution latency + spread**
(typically 50–500ms). The JSON file bus adds at most 1s on the signal path
and zero on the native scalper path.

Sub-microsecond execution (institutional HFT) requires:
- Co-location at the exchange/matching engine
- FPGA order routing
- Direct market access (DMA) via FIX or exchange binary protocol
- No interpreted language in the hot path

---

## 5. Recommended Path — Direct Broker FIX API Integration

The current architecture is correct for retail MT5 scalping. For the next
infrastructure tier — lower latency, no Wine dependency, broker-agnostic —
the recommended path is a **direct FIX API connection** from Bridge to the broker.

### Architecture overview

```
                   ┌─────────────────────────────────────────────────┐
                   │             SIGNAL SYSTEM (macOS / VPS)         │
                   │                                                  │
  TradingView ──►  │  LENS  ──► regime_engine.infer()               │
  Telegram    ──►  │  LISTENER  ──► AEGIS gates                      │
                   │                    │                            │
                   │              bridge_fix.py                       │
                   │         (replaces JSON file bus)                 │
                   │              │           │                       │
                   │         FIX Session   REST/WS feed              │
                   └──────────────┼───────────┼───────────────────── ┘
                                  │           │
                   ┌──────────────▼───────────▼───────────────────── ┐
                   │              BROKER                              │
                   │                                                  │
                   │  Order routing    Market data feed               │
                   │  (FIX 4.4 / 5.0)  (price, indicators)           │
                   └──────────────────────────────────────────────── ┘
```

### What changes

| Layer | Current (MT5 file bus) | Direct FIX |
|---|---|---|
| **Market data** | `market_data.json` written by FORGE EA, read by bridge | FIX `MarketDataRequest (V)` or broker WS feed → bridge directly |
| **Order routing** | `command.json` → FORGE EA → MT5 API → broker | FIX `NewOrderSingle (D)` → broker matching engine directly |
| **Position tracking** | FORGE EA writes open positions into `market_data.json` | FIX `ExecutionReport (8)` stream → bridge |
| **Execution latency** | 50–500ms (MT5 → broker) | 5–50ms (direct FIX, broker co-located) |
| **MT5 dependency** | Required (Wine on macOS) | Eliminated |
| **Regime engine** | Unchanged — consumes market data however it arrives | Unchanged |
| **AEGIS** | Unchanged | Unchanged |
| **SCRIBE / ATHENA** | Unchanged | Unchanged |

### Implementation steps

1. **Choose a broker with FIX API access** — Interactive Brokers (IBKR TWS/FIX),
   LMAX Exchange, Spotware cTrader FIX, or a prime-of-prime providing FIX.
   Most retail-facing MT5 brokers do not offer FIX; you may need to move broker.

2. **Add `quickfix` or `simplefix` to the Python stack** — `quickfix` is the
   reference Python FIX engine. For lighter weight: `simplefix` (pure Python,
   no C extension).

3. **Write `bridge_fix.py`** — replaces the `_read_json(MARKET_FILE)` call in
   `bridge._tick()` with a FIX session callback that populates the same `mt5` dict.
   The rest of bridge (regime, AEGIS, SCRIBE, ATHENA) is unchanged.

4. **Replace `_write_command()`** — instead of writing `command.json`, send
   `NewOrderSingle (D)` / `OrderCancelReplaceRequest (G)` / `OrderCancelRequest (F)`
   directly over the FIX session.

5. **Keep MT5 optionally** — MT5 can remain as a backup execution path and
   charting tool while FIX handles live order flow.

6. **VPS deployment** — co-locate the Python process on a VPS in the same
   data centre as the broker's matching engine (e.g. LD4 London for most FX brokers).
   Reduces round-trip from ~100ms (macOS home) to ~1–5ms.

### Latency projection

```
Current (MT5 file bus, macOS home):
  signal path         ~0.5 – 5s
  native scalper      ~50 – 500ms  (broker execution floor)

Direct FIX, macOS home (no VPS):
  order submission    ~20 – 100ms  (FIX over internet)
  fills               ~20 – 100ms
  Total               ~40 – 200ms

Direct FIX, VPS co-located (LD4 / NY4):
  order submission    ~0.5 – 5ms   (FIX, same DC)
  fills               ~1 – 10ms
  Total               ~2 – 15ms
```

### What stays the same

- **Regime engine** (`regime.py`) — unchanged. Market data arrives via a different
  transport but the feature extraction, HMM inference, and output contract are identical.
- **AEGIS** — unchanged. All gates operate on the same signal/regime dict.
- **SCRIBE / ATHENA / AURUM** — unchanged. They consume bridge output, not raw FIX.
- **FORGE EA** — can be retired from the execution path but kept for backtesting.

---

## 6. Key Environment Variables (Bridge ↔ MT5 File Bus)

| Variable | Default | Purpose |
|---|---|---|
| `BRIDGE_LOOP_SEC` | `1` | Bridge tick interval (seconds) |
| `BRIDGE_LENS_SEC` | `5` | LENS snapshot refresh cadence |
| `MT5_CONFIG_FILE` | `MT5/config.json` | Path bridge writes regime/mode to |
| `MT5_MARKET_FILE` | `MT5/market_data.json` | Path bridge reads MT5 state from |
| `MT5_CMD_FILE` | `MT5/command.json` | Path bridge writes trade commands to |
| `MT5_CMD_FILE_MIRROR` | _(unset)_ | Optional second command.json path |
| `BRIDGE_MT5_STALE` | `30` | Seconds before market_data.json is treated as stale |
| `REGIME_LENS_STALE_SEC` | `90` | Seconds before LENS data degrades regime features |

---

## References

- `python/bridge.py` — main bridge loop, `_refresh_regime_snapshot()`, `_write_config()`
- `python/regime.py` — HMM + Gaussian fallback, `_extract_features()`, `infer()`
- `python/aegis.py` — `_regime_countertrend_reject()`, `_resolve_signal_regime_policy()`
- `ea/FORGE.mq5` — `NativeScalperRegimeBlocksDirection()`, `ForgeResolveNumTrades()`
- `MT5/` — symlink to `MetaQuotes/Terminal/Common/Files/`
- `docs/FORGE_BRIDGE.md` — MT5 symlink setup and troubleshooting
- `docs/REGIME_ENGINE_REVIEW.md` — HMM gotchas and enhancement backlog
- `docs/ARCHITECTURE.md` — full system component diagram
