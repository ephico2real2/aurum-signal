# FORGE Trading Rules — Execution, Management, and Tuning Guide
This guide documents the active FORGE-side trading behavior and its BRIDGE/AEGIS controls:
- entry gating and regime rollout,
- management-command scope rules (global vs per-group),
- closure attribution behavior,
- scalper threshold profiles and rollback.

## 1) Entry path and policy gates
Execution path:
1. LISTENER/AURUM emits an entry intent.
2. BRIDGE builds the order payload and calls AEGIS validation.
3. If approved, BRIDGE writes `MT5/command.json` with `action=OPEN_GROUP`.
4. FORGE reads command file and places/maintains exposure.

AEGIS gates before FORGE placement include:
- direction/SL/TP sanity,
- minimum R:R and SL distance,
- slippage guard,
- open-group and drawdown guards,
- trend and regime-conditioned entry policy.

Regime rollout controls (in `.env`):
- `REGIME_ENGINE_ENABLED=true|false`
- `REGIME_ENTRY_MODE=off|shadow|active`
- `REGIME_MIN_CONFIDENCE`
- `REGIME_STALE_SEC`
- `REGIME_RETRAIN_INTERVAL_SEC`
- `REGIME_MIN_TRAIN_SAMPLES`

Meaning:
- `off`: legacy entry policy only.
- `shadow`: regime computed/logged, but not enforced for entry policy.
- `active`: regime policy applied only when confidence and freshness pass.

## 2) Management command scope rules (FORGE v1.4.1+)
`MODIFY_SL` and `MODIFY_TP` now support both global and scoped execution.

Runtime semantics:
- Global modify (no `magic`): applies to all EA-managed exposure.
- Scoped modify (with `magic`): applies only to that group’s positions/pending orders.

BRIDGE behavior:
- If command includes `group_id`, BRIDGE resolves group magic and writes scoped FORGE command.
- If `group_id` is absent, BRIDGE writes global modify command.
- BRIDGE also syncs SCRIBE group-level and open-position SL/TP fields to match the live change.

Examples:

Global TP modify:
```json
{
  "action": "MODIFY_TP",
  "tp": 4665.5,
  "timestamp": "2026-04-14T00:00:00Z"
}
```

Scoped SL modify:
```json
{
  "action": "MODIFY_SL",
  "magic": 202410,
  "sl": 4662.0,
  "timestamp": "2026-04-14T00:00:00Z"
}
```

## 3) Closure attribution and tracker behavior
FORGE now exports `recent_closed_deals[]` in `MT5/market_data.json` with:
- `position_ticket`
- `close_price`
- `profit`
- `close_reason`
- `time_unix`

BRIDGE tracker close logic is broker-first:
1. If ticket exists in `recent_closed_deals`, use broker close price/profit/time/reason.
2. Map broker TP hints to `TP1_HIT`/`TP2_HIT`/`TP3_HIT` using group targets.
3. Fallback to SL/TP proximity inference only when broker hints are unavailable.

Result:
- fewer false manual-close classifications,
- closer alignment between MT5 and SCRIBE closure records.

## 4) Native scalper (FORGE) — M1 / H4 / regime (v1.6.0+)
When **`ScalperMode`** is not **`NONE`** and mode allows scalping, FORGE evaluates BB bounce/breakout on **M5** (entry logic) with **H1** trend filter (ATR-normalized EMA20−EMA50 vs **`trend_strength_atr_threshold`** from `config.json` / `scalper_config.json`). **M15** participates in breakout confirmation via `scalper_config.json` (`breakout_require_m15`).

**Higher timeframes (bias / structure, not the primary trigger):**
- **H4** structure filter (same formula as H1): inputs **`NativeScalperH4Align`** (default **true**) — buys only when H4 is not structurally bearish (bull or flat); sells when H4 is not structurally bullish. Set **false** for H1-only alignment.
- **Regime gate:** **`NativeScalperRegimeGate`** (default **true**) reads **`regime_*`** from **`MT5/config.json`**. When policy applies and label is **`TREND_BULL`** / **`TREND_BEAR`**, FORGE blocks fading that regime (aligned with **`AEGIS_REGIME_COUNTERTREND_*`**).

**Lower TF execution (optional, v1.6.1+):** input **`NativeScalperM1Mode`** (`NONE` | `CONFIRM` | `TRIGGER`, default **`NONE`**):
- **`CONFIRM`:** after an M5 setup, require **M1** EMA/ATR structure to agree (same threshold as H1/H4: bull/flat for BUY, bear/flat for SELL).
- **`TRIGGER`:** same as **CONFIRM**, plus the **last completed M1 bar** must agree with direction (bullish close for BUY, bearish close for SELL).

**`market_data.json`** includes **`indicators_h4`**, **`indicators_m1`**. **`scalper_entry.json`** includes **`h4_trend_strength`**, **`native_scalper_m1_mode`**, **`m1_trend_strength`**, **`m1_prior_close`** / **`m1_prior_open`** (for TRIGGER diagnostics).

## 5) Active scalper profile and baseline
Active FAST profile (`config/scalper_config.json`):
- `safety.max_spread_points=30`
- `bb_bounce.adx_max=30`
- `bb_bounce.rsi_buy_max=45`
- `bb_bounce.rsi_sell_min=55`
- `bb_breakout.adx_min=20`
- `bb_breakout.rsi_buy_min=50`
- `bb_breakout.rsi_sell_max=50`

STRICT baseline:
- `safety.max_spread_points=25`
- `bb_bounce.adx_max=20`
- `bb_bounce.rsi_buy_max=35`
- `bb_bounce.rsi_sell_min=65`
- `bb_breakout.adx_min=25`
- `bb_breakout.rsi_buy_min=55`
- `bb_breakout.rsi_sell_max=45`

Apply FAST:
```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('config/scalper_config.json')
d = json.loads(p.read_text())
d['safety']['max_spread_points'] = 30
d['bb_bounce']['adx_max'] = 30
d['bb_bounce']['rsi_buy_max'] = 45
d['bb_bounce']['rsi_sell_min'] = 55
d['bb_breakout']['adx_min'] = 20
d['bb_breakout']['rsi_buy_min'] = 50
d['bb_breakout']['rsi_sell_max'] = 50
p.write_text(json.dumps(d, indent=2))
print('applied FAST profile')
PY
make restart
```

Apply STRICT:
```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('config/scalper_config.json')
d = json.loads(p.read_text())
d['safety']['max_spread_points'] = 25
d['bb_bounce']['adx_max'] = 20
d['bb_bounce']['rsi_buy_max'] = 35
d['bb_bounce']['rsi_sell_min'] = 65
d['bb_breakout']['adx_min'] = 25
d['bb_breakout']['rsi_buy_min'] = 55
d['bb_breakout']['rsi_sell_max'] = 45
p.write_text(json.dumps(d, indent=2))
print('applied STRICT profile')
PY
make restart
```

## 6) Verification checklist
After changing rules or binaries:
1. **Strategy Tester (backtest):** In **Expert properties → Inputs**, set **`InputMode`** to **`SCALPER`** or **`HYBRID`** if you want **native scalper** entries. Default **`WATCH`** only writes **`tick_data.json`** / ticks — **`CheckNativeScalperSetups` does not run**. Set **`ScalperMode`** to **`DUAL`**, **`BB_BOUNCE`**, or **`BB_BREAKOUT`** (not **`NONE`**). **FORGE v1.6.4+:** **`config.json`** from a **live** BRIDGE run must **not** override **`InputMode`** in the Tester (stale **`effective_mode`** **`WATCH`** / circuit-breaker state used to clobber Inputs every tick). **`tick_data.json via local Files (common err=5004)`** is a normal fallback when Common Files is not used in the Tester sandbox (write still succeeds locally).
2. Confirm runtime version:
   - `make forge-verify-live`
3. Confirm management scope behavior:
   - send scoped `MODIFY_*` with `group_id`,
   - verify BRIDGE wrote `magic` in `MT5/command.json`.
4. Confirm closure feed:
   - inspect `MT5/market_data.json` for `recent_closed_deals`.
5. Confirm SCRIBE reflects live state:
   - `trade_groups` and `trade_positions` SL/TP fields updated after modify.

Useful query:
```sql
SELECT ticket, trade_group_id, close_reason, close_time, pnl
FROM trade_positions
ORDER BY id DESC
LIMIT 30;
```

## 7) Rollback quick path
To return to conservative behavior:
1. Set `REGIME_ENTRY_MODE=off` in `.env`.
2. Apply STRICT scalper profile.
3. Restart services (`make restart`).
4. Verify FORGE and BRIDGE versions/paths are aligned.

## Related docs
- `docs/AEGIS.md`
- `docs/FORGE_BRIDGE.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_CONTRACT.md`
- `docs/CLI_API_CHEATSHEET.md`
