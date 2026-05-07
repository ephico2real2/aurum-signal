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

### iMACD buffer-2 probe bug (fixed FORGE v2.5.1)
MT5's built-in `iMACD` only exposes **buffer 0** (MACD line) and **buffer 1** (signal line). Buffer 2 (histogram) does not exist. Earlier versions of `ForgeNativeScalperWarmupOk` probed `CopyBuffer(h_macd, 2, ...)` which always returned `-1`, permanently blocking warmup with reason `m5_macd_buf` and producing zero TAKEN in every backtest. The probe was removed in v2.5.1. MACD histogram is used only in `WriteMTFBlock()` for `market_data.json` display and that code already handles the failure gracefully as `0`.

### Scalper JSON — defaults vs generated (read first)

- **Edit:** `config/scalper_config.defaults.json` (committed baseline), and/or **`FORGE_*` keys in `.env`** where **`scripts/sync_scalper_config_from_env.py`** defines a mapping.
- **Generate:** `make scalper-env-sync` or `make forge-compile` runs that script, which writes **`config/scalper_config.json`** (stamps **`version`** from **`VERSION`**) and copies to **`MT5/`** when possible. Avoid hand-editing **`scalper_config.json`** — it is overwritten on the next sync.
- **Copy only:** `make scalper-config-sync` pushes the **existing** `config/scalper_config.json` to Wine Common Files (no regenerate).
- Full detail: **`docs/SCALPER_CONFIG_PIPELINE.md`**.

When **`ScalperMode`** is not **`NONE`** and mode allows scalping, FORGE evaluates BB bounce/breakout on **M5** (entry logic) with **H1** trend filter (ATR-normalized EMA20−EMA50 vs **`trend_strength_atr_threshold`** from `config.json` / `scalper_config.json`). **M15** participates in breakout confirmation via `scalper_config.json` (`breakout_require_m15`).

**Higher timeframes (bias / structure, not the primary trigger):**
- **H4** structure filter (same formula as H1): inputs **`NativeScalperH4Align`** (default **true**) — buys only when H4 is not structurally bearish (bull or flat); sells when H4 is not structurally bullish. Set **false** for H1-only alignment.
- **Regime gate:** **`NativeScalperRegimeGate`** (default **true**) reads **`regime_*`** from **`MT5/config.json`**. When policy applies and label is **`TREND_BULL`** / **`TREND_BEAR`**, FORGE blocks fading that regime (aligned with **`AEGIS_REGIME_COUNTERTREND_*`**).

**Lower TF execution (optional, v1.6.1+):** input **`NativeScalperM1Mode`** (`NONE` | `CONFIRM` | `TRIGGER`, default **`NONE`**):
- **`CONFIRM`:** after an M5 setup, require **M1** EMA/ATR structure to agree (same threshold as H1/H4: bull/flat for BUY, bear/flat for SELL).
- **`TRIGGER`:** same as **CONFIRM**, plus the **last completed M1 bar** must agree with direction (bullish close for BUY, bearish close for SELL).

**`market_data.json`** includes **`indicators_h4`**, **`indicators_m1`**. **`scalper_entry.json`** includes **`h4_trend_strength`**, **`native_scalper_m1_mode`**, **`m1_trend_strength`**, **`m1_prior_close`** / **`m1_prior_open`** (for TRIGGER diagnostics).

## 5) Active scalper profile and baseline
Active FAST profile (apply in **`config/scalper_config.defaults.json`**, then `make scalper-env-sync`; FORGE still reads emitted **`scalper_config.json`**):
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

Apply FAST (edit **defaults**, then regenerate):
```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('config/scalper_config.defaults.json')
d = json.loads(p.read_text())
d['safety']['max_spread_points'] = 30
d['bb_bounce']['adx_max'] = 30
d['bb_bounce']['rsi_buy_max'] = 45
d['bb_bounce']['rsi_sell_min'] = 55
d['bb_breakout']['adx_min'] = 20
d['bb_breakout']['rsi_buy_min'] = 50
d['bb_breakout']['rsi_sell_max'] = 50
p.write_text(json.dumps(d, indent=2) + "\n")
print('updated defaults — run: make scalper-env-sync')
PY
make scalper-env-sync
make restart
```

Apply STRICT (edit **defaults**, then regenerate):
```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('config/scalper_config.defaults.json')
d = json.loads(p.read_text())
d['safety']['max_spread_points'] = 25
d['bb_bounce']['adx_max'] = 20
d['bb_bounce']['rsi_buy_max'] = 35
d['bb_bounce']['rsi_sell_min'] = 65
d['bb_breakout']['adx_min'] = 25
d['bb_breakout']['rsi_buy_min'] = 55
d['bb_breakout']['rsi_sell_max'] = 45
p.write_text(json.dumps(d, indent=2) + "\n")
print('updated defaults — run: make scalper-env-sync')
PY
make scalper-env-sync
make restart
```

## 6) Verification checklist
After changing rules or binaries:
1. **Strategy Tester (backtest):** In **Expert properties → Inputs**, set **`InputMode`** to **`SCALPER`** or **`HYBRID`** if you want **native scalper** entries. Default **`WATCH`** only writes **`tick_data.json`** / ticks — **`CheckNativeScalperSetups` does not run**. Set **`ScalperMode`** to **`DUAL`**, **`BB_BOUNCE`**, or **`BB_BREAKOUT`** (not **`NONE`**). **FORGE v1.6.4+:** **`config.json`** from a **live** BRIDGE run must **not** override **`InputMode`** in the Tester (stale **`effective_mode`** **`WATCH`** / circuit-breaker state used to clobber Inputs every tick). **Save inputs as a `.set` file** to avoid re-entering after reattach.
2. **Confirm warmup cleared (FORGE v2.5.1+):**
   ```bash
   python3 -c "import json; ms=json.loads(open('MT5/mode_status.json').read()); print(ms.get('warmup_ok'), ms.get('warmup_reason'), ms.get('scalper_mode'))"
   ```
   Expected: `True  DUAL`. If `warmup_ok=False`, `warmup_reason` gives the exact sub-reason (`h4_bars`, `psar_buf`, etc.). See **`docs/FORGE_BACKTEST_DIAGNOSTIC_COMMANDS.md`** for full diagnostic command set.
3. Confirm runtime version:
   - `make forge-verify-live`
4. Confirm management scope behavior:
   - send scoped `MODIFY_*` with `group_id`,
   - verify BRIDGE wrote `magic` in `MT5/command.json`.
5. Confirm closure feed:
   - inspect `MT5/market_data.json` for `recent_closed_deals`.
6. Confirm SCRIBE reflects live state:
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
- `docs/SCALPER_CONFIG_PIPELINE.md` — scalper defaults → generated JSON → MT5
- `docs/AEGIS.md`
- `docs/FORGE_BRIDGE.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_CONTRACT.md`
- `docs/CLI_API_CHEATSHEET.md`
