# FORGE Trading Rules (Scalper) — Tuning & Revert Guide
This document explains the active FORGE scalper rule set in `config/scalper_config.json`, what each rule means, and how to revert to stricter defaults.

## Why this exists
- Intraday conditions can make strict scalper filters too selective.
- This guide keeps one place for:
  - active thresholds,
  - baseline thresholds,
  - trade-off of each change,
  - exact rollback commands.

## Active profile (FAST) applied
The following values are currently active:
- `safety.max_spread_points`: `30`
- `bb_bounce.adx_max`: `30`
- `bb_bounce.rsi_buy_max`: `45`
- `bb_bounce.rsi_sell_min`: `55`
- `bb_breakout.adx_min`: `20`
- `bb_breakout.rsi_buy_min`: `50`
- `bb_breakout.rsi_sell_max`: `50`
## One-liner profile switches
### Apply FAST profile
```bash
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/Users/olasumbo/signal_system/config/scalper_config.json')
d=json.loads(p.read_text())
d['safety']['max_spread_points']=30
d['bb_bounce']['adx_max']=30
d['bb_bounce']['rsi_buy_max']=45
d['bb_bounce']['rsi_sell_min']=55
d['bb_breakout']['adx_min']=20
d['bb_breakout']['rsi_buy_min']=50
d['bb_breakout']['rsi_sell_max']=50
p.write_text(json.dumps(d, indent=2))
print('applied FAST profile')
PY
make restart
```
### Apply STRICT baseline profile
```bash
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/Users/olasumbo/signal_system/config/scalper_config.json')
d=json.loads(p.read_text())
d['safety']['max_spread_points']=25
d['bb_bounce']['adx_max']=20
d['bb_bounce']['rsi_buy_max']=35
d['bb_bounce']['rsi_sell_min']=65
d['bb_breakout']['adx_min']=25
d['bb_breakout']['rsi_buy_min']=55
d['bb_breakout']['rsi_sell_max']=45
p.write_text(json.dumps(d, indent=2))
print('applied STRICT profile')
PY
make restart
```

## Baseline profile (STRICT) before this change
These were the prior defaults:
- `safety.max_spread_points`: `25`
- `bb_bounce.adx_max`: `20`
- `bb_bounce.rsi_buy_max`: `35`
- `bb_bounce.rsi_sell_min`: `65`
- `bb_breakout.adx_min`: `25`
- `bb_breakout.rsi_buy_min`: `55`
- `bb_breakout.rsi_sell_max`: `45`

## What each rule means
### Spread gate
- `max_spread_points`
  - Blocks entries when broker spread is above threshold.
  - Higher value = more trades accepted during wider spreads, but potentially worse fills.

### Bounce (mean-reversion) rules
- `bb_bounce.adx_max`
  - Maximum trend strength allowed for bounce setups.
  - Higher value = allows bounce entries in stronger trends (more frequent, higher reversal risk).
- `bb_bounce.rsi_buy_max`
  - RSI must be below this for bounce BUY.
  - Higher value = buys are allowed with less oversold confirmation.
- `bb_bounce.rsi_sell_min`
  - RSI must be above this for bounce SELL.
  - Lower value = sells are allowed with less overbought confirmation.

### Breakout rules
- `bb_breakout.adx_min`
  - Minimum trend strength for breakout setups.
  - Lower value = breakout entries allowed in weaker trend regimes.
- `bb_breakout.rsi_buy_min`
  - RSI must be above this for breakout BUY.
  - Lower value = buys trigger earlier.
- `bb_breakout.rsi_sell_max`
  - RSI must be below this for breakout SELL.
  - Higher value = sells trigger earlier.

## Practical tuning approach
- If there are still too few trades:
  - raise `max_spread_points` in small steps (`+1` or `+2`),
  - then relax RSI by `2–3` points.
- If trade quality drops:
  - tighten spread first,
  - then restore ADX/RSI thresholds toward baseline.
- Change one cluster at a time (spread, bounce, or breakout), then observe at least 1 session.

## Roll back to STRICT baseline
Option A: edit `config/scalper_config.json` manually with the baseline values above.

Option B: run this command:
```bash
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/Users/olasumbo/signal_system/config/scalper_config.json')
d=json.loads(p.read_text())
d['safety']['max_spread_points']=25
d['bb_bounce']['adx_max']=20
d['bb_bounce']['rsi_buy_max']=35
d['bb_bounce']['rsi_sell_min']=65
d['bb_breakout']['adx_min']=25
d['bb_breakout']['rsi_buy_min']=55
d['bb_breakout']['rsi_sell_max']=45
p.write_text(json.dumps(d, indent=2))
print('restored STRICT baseline')
PY
```

Then reload services:
```bash
make restart
```

## Verify active rules after any edit
```bash
python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path('/Users/olasumbo/signal_system/config/scalper_config.json').read_text())
print({
  'max_spread_points': d['safety']['max_spread_points'],
  'bounce': {
    'adx_max': d['bb_bounce']['adx_max'],
    'rsi_buy_max': d['bb_bounce']['rsi_buy_max'],
    'rsi_sell_min': d['bb_bounce']['rsi_sell_min'],
  },
  'breakout': {
    'adx_min': d['bb_breakout']['adx_min'],
    'rsi_buy_min': d['bb_breakout']['rsi_buy_min'],
    'rsi_sell_max': d['bb_breakout']['rsi_sell_max'],
  }
})
PY
```

## Related docs
- `docs/MODES_ARCHITECTURE.md`
- `docs/ARCHITECTURE.md`
- `docs/CLI_API_CHEATSHEET.md`
