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

## 4) Active scalper profile and baseline
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

## 5) Verification checklist
After changing rules or binaries:
1. Confirm runtime version:
   - `make forge-verify-live`
2. Confirm management scope behavior:
   - send scoped `MODIFY_*` with `group_id`,
   - verify BRIDGE wrote `magic` in `MT5/command.json`.
3. Confirm closure feed:
   - inspect `MT5/market_data.json` for `recent_closed_deals`.
4. Confirm SCRIBE reflects live state:
   - `trade_groups` and `trade_positions` SL/TP fields updated after modify.

Useful query:
```sql
SELECT ticket, trade_group_id, close_reason, close_time, pnl
FROM trade_positions
ORDER BY id DESC
LIMIT 30;
```

## 6) Rollback quick path
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
