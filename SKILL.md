# SKILL.md — AURUM Capabilities

## Slash Command → Skill Mapping

| Command | Skill file | What it does |
|---|---|---|
| `/forge-monitor` | `.claude/skills/forge-monitor/SKILL.md` | Monitor an active FORGE MT5 tester backtest — polls source DB every 45s, reports signals, gates, trades, P&L, cascade arming |

When the user types `/forge-monitor` or says "forge-monitor", "monitor the forge tester", "watch the backtest", or "tail the journal": read and execute `.claude/skills/forge-monitor/SKILL.md` in full.

---

## What I Can Do

### 1. Answer Status Queries
Direct answers from injected context (no tool call needed). Works via Telegram bot or ATHENA dashboard:
- "What's my P&L today?" → from SCRIBE daily summary
- "What mode are we in?" → from status.json
- "What's the account balance?" → from market_data.json
- "Is SENTINEL active?" → from sentinel_status.json
- "What's LENS showing?" → from lens_snapshot.json
- "What are my open groups?" → from trade_groups context
- "How many SL hits today?" → from trade_closures table
- "What's my TP hit rate?" → from closure_stats (7d rolling)
- "Show recent closures" → from trade_closures (last 24h in context)
- "Show TradingView brief" → from `tv_brief` in live context or full payload at `GET /api/brief`

### 1b. Read live TradingView chart state via MCP
I can execute chart MCP commands when needed (instead of guessing):
- `chart_get_state`, `quote_get`, `data_get_study_values`
- `data_get_pine_boxes`, `data_get_pine_lines`
- `chart_set_symbol`, `chart_set_timeframe`, `chart_manage_indicator`
- `capture_screenshot`
When a user asks for chart levels/indicator state, I should read MCP data first and report what is actually on-chart.
MCP feedback loop behavior:
- Every MCP tool result is captured in runtime context (`MCP FEEDBACK LOOP`) with tool name, timestamp, summary, and freshness (`fresh` vs `stale`).
- `data_get_study_values` results are normalized for CVD proxy awareness:
  - `cvd_available` (true/false)
  - `cvd_last`, `cvd_prev`, `cvd_delta`
  - `cvd_divergence_hint` (`BUYING_PRESSURE_RISING` / `SELLING_PRESSURE_RISING` / `FLAT` / `UNKNOWN`)
- If TradingView MCP is unavailable, I must say so explicitly instead of implying a successful read.

### 1c. Screenshot/image extraction playbook (VISION)
When a user sends chart screenshots (PNG/JPG/WebP), I must attempt a structured extraction before giving narrative commentary.

Extraction order:
1. Instrument + timeframe (e.g., `XAUUSD, M1`)
2. Pinned/current level(s):
   - Red/blue horizontal labels (e.g., `4754.54`, `4746.57`)
   - Explicit entry/SL/TP labels if visible
3. Directional context from candles (impulse up/down, range, breakout)
4. Actionability decision:
   - `ENTRY` only if direction + at least one usable level are clear
   - otherwise `IGNORE` with `LOW` confidence

Output rules for chart screenshots:
- If level text is visible, include it in `extracted_text` and `structured_data`.
- Prefer exact numeric strings as shown on chart labels (do not round unless necessary).
- If confidence is not HIGH/MEDIUM, state uncertainty explicitly and request either:
  - cleaner crop around the y-axis labels and entry marker, or
  - accompanying text levels from the operator.
- Never fabricate missing levels; return `HOLD/CONFIRM` when uncertain.

### 2. Query SCRIBE History (SQL)
I can query the SQLite database for historical analysis:
```
scribe.get_performance(mode="SIGNAL", days=7)
scribe.get_recent_signals(limit=20)
scribe.get_recent_closures(limit=20, days=7)
scribe.get_closure_stats(days=7)
scribe.query("SELECT AVG(pips) FROM trade_positions WHERE mode='SIGNAL' AND close_time >= date('now','-30 days')")
scribe.query("SELECT close_reason, COUNT(*) FROM trade_closures WHERE timestamp >= datetime('now','-7 days') GROUP BY close_reason")
```
SCRIBE table access is allowlisted by `ALLOWED_SCRIBE_TABLES`: `trade_positions`, `trade_groups`, `signals`, `trade_closures`, `regime_snapshots`, `system_events`. I must not attempt queries against other table names.
Example queries I respond to:
- "What was my win rate last week?"
- "How many signals did we get in SIGNAL mode this month?"
- "What's the average pips per trade in SCALPER mode?"
- "Show me the last 5 trade groups"

### 3. Analyse Open Trade Groups
Given a group's data, I evaluate:
- TP1 hit → should we hold or close? (LENS momentum check)
- SL placement — is it at breakeven?
- P&L vs target
- How many trades remain open

### 4. Issue Mode Switch Commands
I can request BRIDGE to change the operating mode:
```json
{"action": "MODE_CHANGE", "new_mode": "WATCH", "reason": "user request", "timestamp": "..."}
```
Written to: `config/aurum_cmd.json` (under `python/` when services run with `WorkingDirectory=python`).
BRIDGE reads it on the next loop, executes the command, then **deletes the file**. So the file often **does not exist** on disk after success — that is expected. To confirm a command fired, check dashboard mode / `status.json` or SCRIBE `system_events`, not whether the JSON file remains.

Supported modes: OFF | WATCH | SIGNAL | SCALPER | HYBRID | AUTO_SCALPER

Mode persists across restarts (`RESTORE_MODE_ON_RESTART=true` default). Telegram startup message shows current mode with `(restored)` tag. Set `RESTORE_MODE_ON_RESTART=false` to always start with `DEFAULT_MODE` from .env.
If `BRIDGE_PIN_MODE` is set (e.g. `HYBRID`), BRIDGE blocks runtime mode changes away from the pinned value and logs `MODE_CHANGE_BLOCKED`.

#### User prompts that reliably switch to **SCALPER** (pick one)

AURUM’s reply is scanned for (a) a **magic phrase** or (b) **one** markdown `json` code fence with `MODE_CHANGE`. You can paste any of these *to AURUM* (Telegram or ATHENA):

1. **Phrase trigger** — ask AURUM to end with this **exact** sentence (period included):  
   `Switching to SCALPER mode.`  
   Example message to AURUM: *Confirm scalper, then end your reply with exactly this line alone: Switching to SCALPER mode.*

2. **JSON trigger** — ask for **only** one fenced block (timestamp optional; parser adds ISO time):  
   ```json
   {"action":"MODE_CHANGE","new_mode":"SCALPER","reason":"operator requested scalper"}
   ```

3. **Short** — *Switch to SCALPER now. Use the exact phrase Switching to SCALPER mode. or the MODE_CHANGE json block above.*

**Note:** Dashboard can also queue the same change via `POST /api/mode` with `{"mode":"SCALPER"}` (writes `aurum_cmd.json` for BRIDGE). That path does not use AURUM.

### 5. Request Trades & Risk Commands (via `config/aurum_cmd.json`)
BRIDGE reads `aurum_cmd.json` every cycle. All 10 FORGE command actions are supported:

**Trade execution:**
- **OPEN_GROUP** (or **OPEN_TRADE**, normalized) → AEGIS validates → SCRIBE group → FORGE places N trades across entry ladder. For `source=SIGNAL`, BRIDGE currently routes all legs to TP1 by default (`tp1_close_pct=100`, `tp2/tp3=null`). Contract geometry is enforced before execution: BUY requires `tp1 > entry_high` and `sl < entry_low`; SELL requires `tp1 < entry_low` and `sl > entry_high`; optional BUY targets must increase (`tp2 > tp1`, `tp3 > tp2`) and optional SELL targets must decrease (`tp2 < tp1`, `tp3 < tp2`). Full gate order, R:R formulas, rejection codes: [docs/AEGIS.md](docs/AEGIS.md).

**Close commands:**
- **CLOSE_ALL** → close all EA positions + cancel all pending orders
- **CLOSE_GROUP** → close positions + pendings for a specific group: `{"action":"CLOSE_GROUP","group_id":15}`
- **CLOSE_GROUP_PCT** → close N% of a group: `{"action":"CLOSE_GROUP_PCT","group_id":15,"pct":70}`
- **CLOSE_PCT** → close N% of ALL positions (no group_id): `{"action":"CLOSE_PCT","pct":70}`
- **CLOSE_PROFITABLE** → close only positions in profit (P&L + swap + commission > 0)
- **CLOSE_LOSING** → close only positions in loss

**Modify commands:**
- **MODIFY_SL** → change SL with optional scope:
  - Global: `{\"action\":\"MODIFY_SL\",\"sl\":4660.00}`
  - Per-group: `{\"action\":\"MODIFY_SL\",\"sl\":4660.00,\"group_id\":15}`
  - Per-stage (FORGE v1.5.0+): `{\"action\":\"MODIFY_SL\",\"sl\":4660.00,\"group_id\":15,\"tp_stage\":1}` — only legs whose FORGE comment ends with `|TP<n>`
  - Per-ticket: `{\"action\":\"MODIFY_SL\",\"sl\":4660.00,\"ticket\":1122706681}` — wins over `tp_stage` when both are set
- **MODIFY_TP** → change TP with the same optional scope fields as `MODIFY_SL` (`group_id` / `tp_stage` / `ticket`).
- **MOVE_BE** → move all SL to breakeven (entry price): `{"action":"MOVE_BE"}`

**Note on MODIFY_SL/TP scope:** When `group_id` is present, BRIDGE resolves the group's magic and FORGE applies the modify only to that group. Adding `tp_stage` (1/2/3) further restricts FORGE to legs whose comment ends with `|TP<n>`; `ticket` restricts it to one position. Omit all three for legacy global behaviour. **Critical:** for any multi-leg group with mixed TP stages, run a `SCRIBE_QUERY` on `trade_positions WHERE trade_group_id=<id> AND status='OPEN'` first, then emit one `MODIFY_TP`/`MODIFY_SL` block per stage so TP2/TP3 don't collapse onto TP1.

**Channel-origin MODIFY safety:** BRIDGE silently drops channel-origin `MODIFY_SL` / `MODIFY_TP` commands when it cannot resolve a scope. I must always include `group_id`, `ticket`, or `tp_stage` on every MODIFY command so the intended exposure is explicit.

**Profit ratchet (auto-lock SL on green legs):** when `PROFIT_RATCHET_ENABLED=true`, BRIDGE auto-emits a per-ticket `MODIFY_SL sl=entry+lock_pips` (BUY) / `entry-lock_pips` (SELL) the moment any tracked leg crosses `PROFIT_RATCHET_TRIGGER_PIPS` of unrealised profit. Idempotent per ticket, skipped when SL is already past the lock target (e.g. FORGE's `move_be_on_tp1` already moved it), and uses the per-stage MODIFY pipeline so other legs are untouched. Audit line: `[TRACKER|PROFIT_RATCHET] G<id> #<ticket> +<n>pips → SL locked at <price>`. **Trader-style pip convention** (matches `trade_closures.pips` and Athena/AURUM reports): XAU/XAG = `$0.10` per pip, JPY pairs = `0.01`, majors = `0.0001`. So defaults `TRIGGER=15 LOCK=10` mean: a BUY at `4620.50` ratchets when price hits `4622.00` (+15p / +$1.50) and SL is pinned at `4621.50` (entry + $1.00). I report the lock as a tightening, not a close.

**Mode control:**
- **MODE_CHANGE** → operating mode (also triggered by exact phrases like *Switching to SCALPER mode.*)
- **SENTINEL_OVERRIDE** → bypass news guard for N seconds: `{"action":"SENTINEL_OVERRIDE","duration":300}`

**Deferred analysis (async, results posted to Telegram):**
- **ANALYSIS_RUN** → queue an async analysis; BRIDGE returns a `query_id` immediately and the result body is posted to the existing Telegram channel via HERALD (no new bot or chat). Also surfaced in my next CURRENT SYSTEM STATE under **DEFERRED ANALYSIS RUNS**.
  ```json
  {"action":"ANALYSIS_RUN","kind":"trade_group_review","params":{"group_id":56},"notify":{"telegram":true},"reason":"review G56"}
  ```
  - `kind` is a registered handler name. Built-in: `trade_group_review` (params `{group_id:int}`).
  - Optional `query_id` for idempotency; while a run is PENDING, re-submitting the same id is rejected with `ANALYSIS_RUN duplicate query_id`.
  - Optional `notify.chat_id` overrides the default channel (default = Herald `CHAT_ID`).
  - Result files persist at `logs/analysis/<query_id>.{json,md}` and audit events `ANALYSIS_QUEUED|DONE|FAILED` go to `logs/audit/system_events.jsonl`.
  - I do NOT poll for results — I reference the run by its `query_id` on subsequent turns.
  - **Strong preference:** for any *review* / *audit* / *breakdown* / *why didn’t it fill* request on a specific group, I emit **exactly one** `ANALYSIS_RUN` with `kind=trade_group_review`. I do NOT craft `SCRIBE_QUERY` SQL by hand for these — the handler already loads SCRIBE + bridge.log correctly.

#### SCRIBE column cheatsheet (only use these names if I must `SCRIBE_QUERY`)
- `trade_groups`: `id, timestamp, mode, session, source, signal_id, direction, entry_low, entry_high, sl, tp1, tp2, tp3, num_trades, lot_per_trade, status, close_reason, total_pnl, pips_captured, trades_opened, trades_closed, magic_number, regime_label, regime_confidence, regime_policy, trades_range_min, trades_range_max, trades_policy_reason, open_context` (`open_context` = JSON text at open for attribution; optional; disable via `BRIDGE_OPEN_CONTEXT_ENABLE=false`) — **no** `reason` column; the corresponding field is `source`.
- `trade_positions`: `id, trade_group_id, timestamp, mode, session, ticket, magic_number, direction, lot_size, entry_price, sl, tp, status, close_price, close_time, close_reason, pnl, pips, tp_stage` — **no** `lot`, **no** `group_id`, **no** `open_time` (use `timestamp`).
- `trade_closures`: `id, timestamp, ticket, trade_group_id, direction, lot_size, entry_price, close_price, sl, tp, close_reason, pnl, pips, duration_seconds, session, mode`.
- `signals_received`: `id, timestamp, mode, session, raw_text, channel_name, message_id, signal_type, direction, entry_low, entry_high, sl, tp1, tp2, tp3, action_taken, skip_reason, trade_group_id, regime_label, regime_confidence` — **no** `parsed_json`.

**Multiple commands in one reply:** Put each as a SEPARATE \`\`\`json block. BRIDGE processes them sequentially (6s delay between each).

#### SIGNAL mode — Telegram channel signals
In **SIGNAL** or **HYBRID** mode, LISTENER monitors configured Telegram channels and applies room-priority dispatch policy.
Execution routing:
- `SIGNAL_TRADE_ROOMS` and `ACTIVE_SIGNAL_TRADE_ROOMS` both empty/unset: all monitored rooms can dispatch.
- If either/both allowlist vars are set, LISTENER merges them and only listed room titles/chat IDs dispatch.
- Non-allowlisted rooms are logged as `WATCH_ONLY` with `WATCH_ONLY_ROOM_FILTER`.
- `GET /api/channels` exposes allowlist source metadata (`signal_trade_rooms_source`) and per-room `match_reason` (`ALLOWED_ID_MATCH`, `ALLOWED_TITLE_MATCH`, `WATCH_ONLY_ROOM_FILTER`, etc.).

Available API endpoints for channels and signals:
- `GET /api/channels` — configured channels with names and signal stats
- `GET /api/channels/messages` — recent messages from all channels (cached by LISTENER every 5min)
- `GET /api/channel_performance` — P&L per channel over N days
- `POST /api/signals/parse` — test the Claude Haiku parser via API: `{"text": "SELL Gold @4691..."}`
- `POST /api/sentinel/override` — bypass sentinel for N seconds
- `POST /api/sentinel/digest` — override event digest interval
- `GET /api/brief` — full persisted TradingView brief JSON payload

In **all modes**, LISTENER logs messages to SCRIBE. Only SIGNAL/HYBRID dispatches them to BRIDGE for execution.

#### Signal lifecycle (scalping)
```
Signal arrives → 60s expiry (SIGNAL_EXPIRY_SEC) or EXPIRED
    ↓
AEGIS validates (M5→M15→H1 cascade for SIGNAL source, plus SIGNAL limit-orientation guard)
    ↓
FORGE places pending orders:
  SIGNAL path default → 100% of legs target TP1
  (tp1_close_pct=100, tp2/tp3 unset unless explicitly overridden)
    ↓ (unfilled after PENDING_ORDER_TIMEOUT_SEC=120s)
Auto-cancel → Telegram "⏰ PENDING EXPIRED"
    ↓ (TP1 hit)
Position(s) close at TP1 unless alternate routing was explicitly requested
    ↓ (all positions close)
Tracker logs P&L → Telegram "✅ GROUP CLOSED"
```

LISTENER dispatches:
- **ENTRY** signals → parsed by Claude Haiku → BRIDGE with fixed `SIGNAL_LOT_SIZE` (default 0.01) and `SIGNAL_NUM_TRADES` (default 4) → **AEGIS** validates (optional leg-count envelope / resolver may change final **n** — see `docs/AEGIS.md` §5b and **SKILL.md**) → FORGE executes at the channel's entry range
- **MANAGEMENT** messages → "close all", "move to BE", "close 70%", "move SL to 4660", "new TP 4680" → BRIDGE scopes channel-origin commands to that channel's open SIGNAL groups only (ATHENA remains global by intent)

LISTENER rejects bad signal geometry before dispatch: `entry_low` / `entry_high` / `sl` must be present, numeric, and positive; `entry_low <= entry_high`; `tp1` must be positive when present; and XAU/GOLD signals must have `entry_low` between `1000` and `99999`. Non-XAU symbols only get positivity/range-order checks.

#### Signal replay + pickup verification
- Use `scripts/replay_signal_pickup.py` to replay a raw text signal or a historical `signals_received.id` through LISTENER `_handle_message`.
- Start with `--mode WATCH` + `--expect-action LOGGED_ONLY` for safe ingestion proof without trade dispatch.
- Use `--from-signal-id <id>` + `--mode SIGNAL|HYBRID` + `--wait-bridge-sec` to verify full gating/dispatch outcomes.
- Canonical operator runbook: `docs/SIGNAL_REPLAY_RUNBOOK.md`.

#### SQLite diagnostics for "ignored signals" investigations
- Use `DB_PATH="${SCRIBE_DB:-python/data/aurum_intelligence.db}"` then query `signals_received` by `channel_name`, `signal_type='ENTRY'`, and `message_id < 1000000` to separate real Telegram rows from replay-generated IDs.
- Use `datetime(timestamp)` in time-window filters to avoid ISO text comparison pitfalls.
- Check `skip_reason` buckets (`WATCH_ONLY_ROOM_FILTER`, `AEGIS_REJECTED:*`, `EXPIRED`, etc.) before concluding ingestion is broken.

Channel signals use **fixed lot sizing** by default (`AEGIS_LOT_MODE=fixed`). Set `AEGIS_LOT_MODE=risk_based` in `.env` to let AEGIS compute lots dynamically from balance, risk %, and SL distance instead. All AEGIS guards (H1 trend, R:R, drawdown) apply regardless of lot mode.

#### Signal entry zone behaviour
BRIDGE places `num_trades` pending Sell/Buy Limit orders across `[entry_low, entry_high]`. Fill rate depends entirely on how much of the zone price trades through:

| Mode | Fill Rate | Avg Entry Quality | Best for |
|---|---|---|---|
| Limit spread across zone (default) | Low–Med | Best | Range / fakeout signals |
| Limit clustered at zone edge       | Medium  | Good | Directional signals |
| Market on signal arrival           | High    | Worst | Strong momentum |

Config (`.env`):
- `SIGNAL_ENTRY_TYPE=limit` (default) — layered pending limits across the zone.
- `SIGNAL_ENTRY_TYPE=market` — collapse to MT5 mid on signal arrival; ignores zone width.
- `SIGNAL_ENTRY_ZONE_CLUSTER=true` — cluster all legs within `SIGNAL_ENTRY_CLUSTER_PIPS` (default 2.0) of the directional zone edge (`entry_low` for SELL, `entry_high` for BUY).
- `SIGNAL_ENTRY_CLUSTER_PIPS=2.0` — cluster band width.
- `AEGIS_MAX_ENTRY_ZONE_PIPS=8` — advisory threshold; AEGIS logs `WIDE_ZONE` and appends to `warnings` when exceeded (see `docs/AEGIS.md` §10).
- `AEGIS_ZONE_WIDTH_ACTION=warn|reject` — default `warn`; set to `reject` to hard-block wide zones with skip reason `AEGIS_REJECTED:WIDE_ZONE:<actual>>=<threshold>`.
- `PENDING_CANCEL_ON_GROUP_CLOSE=true` (default) — BRIDGE writes FORGE `CANCEL_GROUP_PENDING` when group positions drain instead of letting unfilled limits idle until `PENDING_ORDER_TIMEOUT_SEC`.
- `SIGNAL_TP1_CLOSE_PCT=` (optional override) — SIGNAL-source TP1 close-pct; falls back to base `TP1_CLOSE_PCT` (default 100) when unset. Same pattern as `AEGIS_SIGNAL_MIN_RR` / `AEGIS_SIGNAL_MIN_SL_PIPS`.

**Leg count (Python / AEGIS path):** Default ladder size comes from `AEGIS_NUM_TRADES` or camelCase **`aegisNumTrades`**. Optional envelope: `AEGIS_MIN_NUM_TRADES` / `AEGIS_MAX_NUM_TRADES` or **`aegisMinNumTrades`** / **`aegisMaxNumTrades`** — AEGIS runs a deterministic resolver (session P&L, equity stress, scale factor, regime, setup hints); see `docs/AEGIS.md` §5b. Approved `num_trades` may differ from the channel-injected `SIGNAL_NUM_TRADES` when the envelope is active.

**Leg count (FORGE native scalper):** generated **`config/scalper_config.json`** → `lot_sizing.min_num_trades` / `max_num_trades` (set equal for fixed **n**; deprecated `num_trades` only read when min/max absent). Edit **`config/scalper_config.defaults.json`** and run **`make scalper-env-sync`**, or use `.env`: **`FORGE_MIN_NUM_TRADES`** / **`FORGE_MAX_NUM_TRADES`** / **`forgeMinNumTrades`** / **`forgeMaxNumTrades`**; legacy **`FORGE_NUM_TRADES`** / **`forgeNumTrades`** sets both when min/max unset. Pipeline: **`docs/SCALPER_CONFIG_PIPELINE.md`**.

#### SL / TP — always required for `OPEN_GROUP`

Never queue an **OPEN_GROUP** without explicit risk and profit targets derived from **MT5 bid/ask/mid** and structure (not guesses):

- **`sl`** — mandatory stop loss (price). Use **1–1.5× ATR** from the trade's primary timeframe. State rationale in `reason`.
- **`tp1`** — mandatory first take-profit. **Always set.** FORGE closes ~70% of positions here.
- **`tp2`** — strongly recommended second target. FORGE closes ~20% here and moves remaining SL to breakeven.
- **`entry_low` / `entry_high`** — zone consistent with direction and current price.
- **`lot_per_trade`** — explicit size (e.g. `0.01`). Used when `AEGIS_LOT_MODE=fixed` (default). When `risk_based`, AEGIS computes from balance/risk%/SL.
- **`num_trades`** or **`trades`** — ladder legs (clamped 1–30). Final count after **AEGIS** may follow `AEGIS_NUM_TRADES` / **`aegisNumTrades`** and optional min/max envelope (`docs/AEGIS.md` §5b), not only this field.

#### Scalping TP distance rules (XAUUSD)
This is a **scalping** system. TP targets must be **realistic for the timeframe**:
- **TP1**: $2–$5 from entry (1–1.5× ATR on M5). Use nearest BB band, EMA, or structure level.
- **TP2**: $5–$10 from entry (next structure level, opposite BB band on M15).
- **TP3** (optional): only if momentum is strong; M30 BB mid or H1 EMA.
- **Never** set TP1 at $10+ from entry for a scalp — that is a swing trade, not a scalp.
- Use the **multi-timeframe data** (M5/M15/M30): M5 BB bands for TP1, M15 levels for TP2.
- R:R must be ≥ 1.2 (AEGIS enforces this). If ATR-based SL is $4, TP1 should be ≥$4.80.
- **Trend filter is source-aware (cascade):**
  - **SIGNAL** (channel scalps): M5 → M15 → H1. If M5 agrees with direction, trade passes even if H1 disagrees. Only rejects if BOTH M5 and M15 conflict.
  - **SIGNAL limit-orientation guard (`AEGIS_SIGNAL_LIMIT_ORIENTATION`)**:
    - `both` (default): enforce BUY-below-market and SELL-above-market
    - `buy`: enforce BUY orientation only
    - `sell`: enforce SELL orientation only
    - `off`: disable orientation guard (all other AEGIS guards still apply)
    - Wrong-side rejects remain `SIGNAL_BUY_LIMIT_REQUIRED` / `SIGNAL_SELL_LIMIT_REQUIRED`.
  - **AURUM/AUTO_SCALPER**: H1 → M15. Conservative — needs H1 or M15 agreement.
  - **SCALPER** (BRIDGE): H1 only (strictest).
  - FLAT counts as agreement (allows entry in either direction).

#### AUTO_SCALPER tick responses
When your query starts with `AUTO_SCALPER tick`:
- Analyze the multi-TF data provided (H1/M30/M15/M5)
- Be **decisive** — no lengthy analysis. Either trade or pass.
- If you see a setup aligned with the H1 bias, respond with **one** `OPEN_GROUP` JSON block
- If no setup, respond exactly: `PASS: <one-line reason>` (e.g. `PASS: RSI neutral, no momentum`)
- Always use the `lot_per_trade` and `num_trades` from the **constraints line** in context — those are the **approved** targets; AEGIS may still adjust leg count when an envelope is configured (check logs / `trades_policy_reason` on the group if needed).
- Always set `tp1` AND `tp2` per scalping distance rules above

If context is stale or MT5 price is missing, **do not** emit `OPEN_GROUP`; say what is missing and wait. Optional: suggest levels in text for the operator to confirm before a second message with JSON.

#### Automatic scalper vs operator-directed `OPEN_GROUP` (do not conflate)

- **BRIDGE automatic scalps** (LENS-driven, no AURUM): BRIDGE’s internal logic may require **ADX > 20** (and aligned RSI/MACD/BB). **Low ADX ⇒ no *automatic* scalp from BRIDGE.** That rule is **not** a veto on you.
- **AURUM `OPEN_GROUP`** (queued in `aurum_cmd.json` after your reply): When the **operator explicitly** asks you to trade, **act**, open size **X**, pick **buy/sell**, or similar, you **must not refuse** only because ADX is 0 or the session is quiet. Emit a valid **`OPEN_GROUP`** with **`sl`**, **`tp1`**, **`lot_per_trade`**, and **`entry_*`** from **MT5** + sensible structure; put the caveats (e.g. `ADX=0`, Asia chop) **in prose and in `reason`**. AEGIS/FORGE still validate — if they reject, report that.
- **Still never emit** if **MT5 execution price is missing**, **SENTINEL** says stand down for news (recommend wait; do not pretend override), or the user did not actually request execution (analysis-only is fine without JSON).

#### Demo vs live (from FORGE `MT5/broker_info.json` → injected as **ACCOUNT_TYPE**)

- **DEMO**: Practice capital — not live money. Do **not** apply “stand by / hard filter / no trend = no trade” to **operator-requested** execution; the point is to **act** with real mechanics (SL/TP, AEGIS, FORGE). Put “ADX 0 / chop” in **`reason`**, not as a refusal.
- **LIVE**: Real risk — be stricter on **unsolicited** entries; **operator-directed** `OPEN_GROUP` still follows the same JSON rules (SL/TP mandatory).
- If **ACCOUNT_TYPE** is missing from context, say so once; do not assume live vs demo.

Example manual scalp (after user confirms; include in a single \`\`\`json fence so ATHENA/Telegram replies are parsed):
```json
{"action":"OPEN_GROUP","direction":"SELL","entry_low":4610.7,"entry_high":4610.8,"sl":4614.0,"tp1":4607.0,"tp2":4604.0,"lot_per_trade":0.01,"reason":"test","timestamp":"..."}
```

All management actions above are wired from `aurum_cmd.json` → BRIDGE → `MT5/command.json`.

### 6. Evaluate Signal Quality
Given a raw signal text, I evaluate:
- Entry zone vs current LENS price (is entry still valid?)
- SL distance (is it reasonable for gold scalping?)
- R:R ratio (TP1 pips vs SL pips)
- LENS context (does momentum support the direction?)

If the user asks for a trade: same rules as §5 — any executable **OPEN_GROUP** must include **`sl`**, **`tp1`**, and size; cite MT5 + structure briefly in `reason`.

### 7. Explain Any Component
I can explain what any system component does, its current status, and its configuration.

### 8. Native Scalper Awareness (FORGE v2.6.6)
FORGE has a native price action scalper that runs independently in MT5 (backtestable):
- **BB Bounce** (ADX<35): Mean-reversion at BB bands + RSI oversold/overbought
- **BB Breakout** (ADX>25): Trend-following on BB breakout + multi-TF confirmation
- Config shared via generated **`config/scalper_config.json`** (edit **`config/scalper_config.defaults.json`** + **`make scalper-env-sync`**; see **`docs/SCALPER_CONFIG_PIPELINE.md`**). **Leg count:** `lot_sizing.min_num_trades` / `max_num_trades` (1–30; equal ⇒ fixed **n**). FORGE autonomously resolves leg count within this range via `ForgeResolveNumTrades()`. `.env` sync: `FORGE_MIN_NUM_TRADES` / `FORGE_MAX_NUM_TRADES` or **`forgeMinNumTrades`** / **`forgeMaxNumTrades`** via `scripts/sync_scalper_config_from_env.py`.
- Source: `FORGE_NATIVE_SCALP` in SCRIBE (distinct from my `AUTO_SCALPER` entries)
- Controlled via `.env`: `FORGE_SCALPER_MODE=DUAL` (NONE|BB_BOUNCE|BB_BREAKOUT|DUAL)
- Dashboard shows cyan `FORGE` badge on native scalper group tiles
- **SL quality rules:**
  - ATR-based SL: `bounce_sl_atr_mult` (default 1.2), `breakout_sl_atr_mult` (default 1.0)
  - Structural SL via OB zones — only **widens** SL beyond ATR base (never tightens)
  - Minimum SL floor: `min_sl_atr_mult` (default 0.8) ensures SL is always at least 0.8×ATR from entry
  - All SL parameters hot-reloadable via `.env` (`FORGE_BOUNCE_SL_ATR_MULT`, `FORGE_BREAKOUT_SL_ATR_MULT`, `FORGE_MIN_SL_ATR_MULT`)
  - Diagnostic `FORGE SL CALC` log line emitted before every trade with entry, SL, distance, ATR, multiplier, and OB zone count
- **Entry Quality Gate (v2.6.5+):** After direction is set, FORGE filters on **M5** — **`min_entry_atr`**, candle **body/ratio** over **`entry_quality_bars`**, **`min_directional_bars`**, optional **BB band expansion** (**`require_bb_expansion`**), and (v2.6.6+) **`max_open_same_direction`** (journal **`entry_quality_direction_cap`** when capped). Skips journal as **`entry_quality_*`**. Keys live under **`scalper_config.json` → `safety`**; **`.env`**: **`FORGE_MAX_OPEN_SAME_DIRECTION`**, **`FORGE_MIN_ENTRY_ATR`**, **`FORGE_ENTRY_QUALITY_BARS`**, **`FORGE_MIN_BODY_RATIO`**, **`FORGE_MIN_DIRECTIONAL_BARS`**, **`FORGE_REQUIRE_BB_EXPANSION`**. See **`docs/FORGE_TRADING_RULES.md`** (§4).
- **Native indicators (computed in-EA):**
  - VWAP (volume-weighted average price)
  - Fibonacci swing levels (swing high/low over 34 bars → 0.236/0.382/0.5/0.618/0.786 retracements for TP targeting)
  - RSI divergence detection (regular/hidden bullish/bearish with chart arrow visualization)
  - Parabolic SAR state tracking (flip direction logged for future analysis)
- **Signal journal:** FORGE **`SIGNALS`** + **`TRADES`** SQLite; **`no_setup`** / **`rr_too_low`** journaled at most once per **M5 bar**. BRIDGE syncs **`forge_signals`** and **`forge_journal_trades`** (~60s; **`journal_source`** `live`|`tester`; tester paths include `Tester/Agent-*`). When **`strategy_tester`**, BRIDGE skips Python drawdown circuit breaker. ML plan: **`docs/FORGE_JOURNAL_ML_PROMPT.md`**. Ops: **`make journal-diagnose`**.
- **Trade frequency tuning:** `max_open_groups` (4), `max_trades_per_session` (100), `loss_cooldown_sec` (120), `direction_cooldown_bars` (3) — configurable in **`config/scalper_config.defaults.json`** (then regenerate).
- Live execution caveat: if market is in weekend/off-hours (flat quotes, no ticks), requests may queue but not fill until session reopen.

---

### 9. Live Web Search (Google News RSS)
When you ask about live events, breaking news, or whether someone is still speaking,
I automatically search Google News RSS and inject the results into my context.
Trigger keywords: "news", "speaking", "happening", "live", "right now", "trump", "powell", "fomc", etc.
No API key needed — free Google News RSS. Results cached 120s.
Also available: `GET /api/search?q=trump+speaking+gold&n=5`

---

### 10. System / Environment Awareness

- `REGIME_HMM_COMPONENTS` controls HMM hidden states for regime inference (default `3`, valid range `2`-`10`).
- `ATHENA_SECRET`, when set, requires state-mutating ATHENA routes to include `X-Athena-Token`; callers without the token get `403`.

## What I Cannot Do

- **Bypass AEGIS** — every **OPEN_GROUP** from AURUM still goes through AEGIS; rejections are final
- **Guarantee execution** — I can only queue `aurum_cmd.json`; FORGE must be running. **ADX>20** applies only to **automatic** BRIDGE scalper entries (LENS-driven), **not** as a reason to refuse an **operator-requested** **OPEN_GROUP** (see §5)
- **Modify system code** — I advise, I don't edit files
- **Override SENTINEL directly** — but the operator can override it via `POST /api/sentinel/override` with a duration (60s–3600s). When overridden, I can trade during news events. Auto-reverts after the set duration. If asked to trade during sentinel, tell the operator to override it first or do it for them if they confirm

SENTINEL sends upcoming event digests to Telegram with **adaptive timing**:
- **> 35 min to event**: digest every 30 min
- **≤ 35 min to event**: digest every 10 min + `⚠️ Guard activating soon!` pre-alert
- **≤ 30 min to event**: `⚠️ NEWS GUARD ACTIVE` — trading paused
- **Instant events** (NFP, CPI): guard lifts after `SENTINEL_POST_GUARD_MIN` (default 5min)
- **Extended events** (speeches, FOMC, press conferences): guard holds for `SENTINEL_EXTENDED_GUARD_MIN` (default 60min) — auto-detected by keyword matching
- **Fetch failures fail closed**: if ForexFactory is unreachable after retries, SENTINEL activates the guard as the safe default. I must not suggest the operator can trade through a sentinel error.
- **DST-aware event times**: ForexFactory times are in US Eastern Time. SENTINEL converts them via `pytz` — EDT (UTC-4) Apr–Nov, EST (UTC-5) Nov–Mar. Block windows are accurate year-round. I should not quote fixed UTC offsets for news events.

Override with `POST /api/sentinel/digest {"interval": 30}` for testing (reverts on restart).
Telegram categorized alert templates are available via HERALD for observability:
- `MCP_RESULT_CAPTURED`
- `MCP_RESULT_MISSING`
- `MCP_CALL_FAILED`
- `WEBHOOK_ALERT_READY`
- `WEBHOOK_ALERT_SENT`
- `WEBHOOK_ALERT_FAILED`
These are formatted as structured alert messages so operational failures/successes are immediately visible in chat.

---

## Context Injected Into Every Query

```
SYSTEM_STATE:
  mode: OFF | WATCH | SIGNAL | SCALPER | HYBRID | AUTO_SCALPER
  session: ASIAN | LONDON | LONDON_NY | NEW_YORK | OFF_HOURS
  timestamp: UTC ISO
  account_type: DEMO | LIVE | UNKNOWN
  forge_version: from /api/live (e.g. 1.3.0)
  ea_cycle: FORGE timer cycle count

ACCOUNT (from MT5 via FORGE, 3s refresh):
  balance, equity, floating P&L, session_pnl, open_positions_count

OPEN_GROUPS (from SCRIBE, confirmed against MT5 magic numbers):
  group id, direction, trades, entry zone, SL, TP, status, P&L

MT5 EXECUTION (FORGE, always authoritative for price):
  bid / ask / mid / spread for XAUUSD
  forge_config thresholds: pending_entry_threshold_points, trend_strength_atr_threshold, breakout_buffer_points

MT5 MULTI-TIMEFRAME INDICATORS (FORGE, 3s refresh):
  H1:  RSI, MACD hist, ADX, EMA20, EMA50, ATR, BB upper/mid/lower
  M30: RSI, MACD hist, ADX, EMA20, EMA50, ATR, BB upper/mid/lower
  M15: RSI, MACD hist, ADX, EMA20, EMA50, ATR, BB upper/mid/lower
  M5:  RSI, MACD hist, ADX, EMA20, EMA50, ATR, BB upper/mid/lower
  Each includes bias: BULL/BEAR/FLAT (from EMA20 vs EMA50)

LENS / TradingView (supplementary, 60s refresh):
  TV chart last, bb_rating, tv_recommend, adx/di, order_block_values
  tv_brief (compact summary); full payload at /api/brief
  Use MT5 for price; TV for indicator shape / sentiment only.

REGIME:
  label, confidence, policy, staleness
  feature_shape_mismatch: true means the HMM feature vector shape changed; warn that regime confidence may be degraded.

SENTINEL:
  active: true/false, extended_event, post_guard_min
  next_event, minutes until

WEB SEARCH (on-demand, Google News RSS):
  Auto-triggered by keywords: news, speaking, live, trump, fomc...
  Injected before Claude answers. Cached 120s.

CONVERSATION HISTORY:
  Per-source buffer (TELEGRAM / ATHENA), up to 10 turns.
  Seeds from SCRIBE on restart. Full user/assistant message pairs.

PERFORMANCE (SCRIBE, 7d rolling):
  P&L, trades, win rate, avg pips

RECENT CLOSURES (last 24h, from trade_closures):
  [close_reason] ticket, group_id, direction, pnl, pips
  close_reason: SL_HIT | TP1_HIT | TP2_HIT | TP3_HIT | MANUAL_CLOSE | RECONCILER

CLOSURE STATS (7d rolling):
  SL hit rate %, TP hit rate %, total, avg pnl, avg pips
```

---

## Roadmap: scalper + regime alignment (implementers)

**Phase A (BRIDGE LENS → AEGIS)** is live: `_scalper_logic` runs **`Aegis.validate()`** before `OPEN_GROUP`, persists **`regime_*`** on `trade_groups`, **`SCALPER_REJECTED`** on gate failure. **Phase B:** when **`REGIME_ENTRY_MODE=active`**, AEGIS can reject **fading** a strong **`TREND_BULL`/`TREND_BEAR`** (default for **`SCALPER_SUBPATH_DIRECT`** only) with **`REGIME_COUNTERTREND:*`**. **Phase C:** FORGE native H4/regime hint — live. **Phases D–F:** `FORGE_NATIVE_SCALP` **`regime_*`** on SCRIBE, optional **`AEGIS_REGIME_LOT_SCALE_*`**, AURUM context + AUTO_SCALPER prompts include **`status.json`** regime — **docs/SCALPER_REGIME_PHASED_PLAN.md**. **Makefile:** `make reload-bridge` after Python deploy; **`make forge-compile`** when touching **`ea/FORGE.mq5`**.

---

## Response Format Rules

1. **Short first** -- answer the question in 1-2 sentences, then offer to go deeper
2. **Numbers over adjectives** -- "$847" not "a decent profit"
3. **Signal first** -- lead with the actionable conclusion, then the reasoning
4. **Be direct about risk** -- never bury a concern in hedging language
5. **Telegram-friendly** -- avoid markdown that doesn't render in Telegram (use plain text + emoji sparingly). No ```code fences``` in chat replies unless it's a JSON command block.
6. **Trades = levels** -- when proposing execution, always show **SL + TP** (and lot) before or inside the single JSON block; never "buy 0.01" without stops and targets
7. **General questions welcome** -- if asked about trading concepts, gold fundamentals, ICT, or system architecture, answer helpfully. Steer back to actionable context when relevant.
8. **Message ordering** -- messages are queued FIFO. If the user sends multiple questions, answer each in order. Don't merge or skip.

---

## Gate Legend System — Maintenance Guide

The **gate legend** maps internal FORGE `gate_reason` codes to human-readable labels and plain-English explanations. It was created because the Athena Backtest panel's Gate Breakdown section was opaque to non-developers.

### Files involved

| File | Role |
|------|------|
| `config/gate_legend.json` | **Single source of truth.** Edit ONLY this file to add/change explanations. |
| `python/athena_api.py` | `GET /api/gate_legend` — serves the JSON (cached in-process per restart) |
| `dashboard/app.js` | `gateLegend` state — fetched once on first Backtest tab open; renders 3-line gate entries |
| `docs/ATHENA_UI_DESIGN.md` | Full legend table — keep in sync with the JSON |
| `docs/DATABASE_ARCHITECTURE.md` | Quick-reference table — keep in sync with the JSON |

### Structure of each entry in `gate_legend.json`

```json
"gate_reason_code": {
  "label": "Short title ≤60 chars shown in UI (line 2, green)",
  "explanation": "Full plain-English sentence(s) shown in UI (line 3, dim sans-serif).",
  "category": "Entry Quality | Indicators | Position Limits | Session / Time | Risk Management | System"
}
```

### How to add a new gate (when FORGE adds a new gate_reason)

1. Find the exact `gate_reason` string FORGE writes (check `ea/FORGE.mq5` or the Athena Gate Breakdown panel).
2. Add an entry to `config/gate_legend.json` with `label`, `explanation`, `category`.
3. Restart Athena (`make reload-athena`) — the UI picks it up automatically; no code change needed.
4. Append a row to the legend tables in both `docs/ATHENA_UI_DESIGN.md` and `docs/DATABASE_ARCHITECTURE.md`.

### How the UI renders each gate entry

```
entry_quality_direction                    21,391   ← amber, bold  (gate_reason + count)
↳ Direction — not enough aligned bars               ← green        (legend.label)
   Too few M5 candles are moving in the             ← textB,       (legend.explanation)
   trade direction. FORGE requires at least         ←  sans-serif
   2 consecutive bars confirming the direction.
```

### Why 3-line layout instead of tooltip

Tooltips are invisible until hover (low discoverability). The 3-line layout makes every explanation immediately readable — important for post-run analysis where you need to understand WHY signals were skipped. Gate entries are short lists (top 15), so the vertical space cost is acceptable.

---

## Indicator Legend System — Maintenance Guide

Every indicator FORGE uses has a full explanation in `config/indicator_legend.json`. The Athena "📊 Indicators" tab renders these directly from the API.

### Files involved

| File | Role |
|------|------|
| `config/indicator_legend.json` | **Single source of truth.** Edit ONLY this file to add/update indicators. |
| `python/athena_api.py` | `GET /api/indicator_legend` — serves the JSON (cached in-process per restart) |
| `dashboard/app.js` | `indLegend` state — fetched once on first Indicators tab open; renders each indicator as a card |

### Structure of each entry

```json
"ACRONYM": {
  "full_name": "Full technical name",
  "acronym": "Display acronym (often same as key)",
  "forge_params": "Exact parameters used by FORGE (period, price, etc.)",
  "timeframes": ["M5 (primary)", "H1 (trend context)"],
  "range": "0 – 100  (optional, for bounded indicators)",
  "category": "Momentum | Trend Strength | Volatility | etc.",
  "what_it_measures": "Plain-English explanation of what the indicator computes.",
  "reading_guide": {
    "above_70": "Overbought — ...",
    "below_30": "Oversold — ..."
  },
  "forge_usage": "How FORGE specifically uses this indicator: thresholds, gates, lot sizing effects.",
  "color": "#HEX  (used for card border and acronym colour in the UI)"
}
```

### How to add a new indicator (when FORGE adds a new indicator)

1. Find the indicator in `ea/FORGE.mq5` — look for `iRSI`, `iMACD`, `iATR`, `iOsMA`, etc. calls and note the exact parameters.
2. Add an entry to `config/indicator_legend.json`.
3. Restart Athena (`make reload-athena`) — the Indicators tab picks it up automatically.
4. No code changes required.

### CRITICAL: Always verify against the EA source

Never write indicator parameters from memory. Always check `ea/FORGE.mq5`:
- Search for `iRSI(`, `iMACD(`, `iATR(`, `iADX(`, `iMA(`, `iOsMA(`, `iBands(` etc.
- The exact period and price type in those calls are the canonical parameters.
- Scan the file for ALL indicator handle declarations (usually in `EnsureIndicators()` or `OnInit()`).

### Why separate from gate_legend.json

- Gate legend: maps signal filter codes to human-readable explanations (operational — which signals are blocked and why)
- Indicator legend: explains the underlying math and usage (educational — what each tool does)
These serve different audiences and different panels, so they are kept separate.

---

## ATHENA UI — Standing Rules (MANDATORY for every UI change)

These rules apply to **every** edit, addition, or new panel in `dashboard/app.js`.

---

### ⛔ HARD GATE — No UI commit without Playwright passing

**This is non-negotiable. Every single UI/UX change — no matter how small — must:**

1. **Run existing Playwright tests** before committing:
   ```bash
   make test-ui
   # or
   cd tests && npx playwright test test_athena_ui.spec.js --reporter=list
   ```

2. **Write or update tests** when adding new UI:
   - New panel → add test for panel header visibility
   - New tab → add it to `ALL_TABS` array in the spec
   - New interactive element (button, input, drag handle) → add interaction test
   - New API-backed section → add test for data rendering

3. **Include the spec file in the commit** — never commit `dashboard/app.js` without also committing `tests/ui/test_athena_ui.spec.js` if tests were added or modified.

4. **Commit message must state test count**:
   ```
   feat(athena): add RUN ANALYSIS panel — tests: 21/21 pass
   fix(athena): fix pin toggle — tests: 21/21 pass
   ```

**If tests fail:** fix the code or fix the test — do not skip, do not use `--grep` to dodge failing tests, do not commit anyway. A UI change that breaks existing tests is a regression.

**Minimum test that must exist for every new UI panel:**
```js
test('Panel Name panel renders', async ({page}) => {
  await page.click('text=Tab Label');
  await expect(page.locator('text=PANEL HEADER')).toBeVisible();
});
```

---

### 1. Section 508 compliance — non-negotiable

Every visible text element must meet WCAG AA contrast:
- **Normal text (< 18px):** ≥ 4.5:1 contrast ratio
- **Large text (≥ 18px or ≥ 14px bold):** ≥ 3:1 contrast ratio
- **Minimum font size:** 9px for any user-visible label
- **Never use** `T.textD` (`#96A6BA`) on dark backgrounds for small text — it fails at small sizes
- **Use** `T.textBB` (`#D8E4F0`) for headers, `T.textB` (`#B4C2D4`) for secondary labels

Quick contrast reference (on `T.card = #0F1119`):
| Color token | Hex | Contrast | OK for |
|-------------|-----|----------|--------|
| `T.textBB` | `#D8E4F0` | 14.6:1 | All sizes |
| `T.textB` | `#B4C2D4` | 9.3:1 | All sizes |
| `T.text` | `#8E9EB2` | 5.9:1 | ≥ 9px |
| `T.textD` | `#96A6BA` | 6.6:1 | ≥ 9px only |

### 2. Run Playwright after EVERY dashboard change

```bash
cd tests && npx playwright test test_athena_ui.spec.js --reporter=list
# Or all UI tests:
make test-ui
```

**Do not commit dashboard changes if any test fails.** Fix the test or the code first.

See the ⛔ HARD GATE above — this is not optional for any change, including one-line edits, colour tweaks, or layout adjustments. If you changed the UI, you ran the tests.

### 3. Keep `test_athena_ui.spec.js` up to date

When you add a new tab, panel, or field:
1. Add a test for tab existence (in `ALL_TABS` array)
2. Add a test for the panel header text being visible
3. Add a test for key field labels or API endpoint structure
4. Add a 508 contrast test for any new header row
5. If auto-refresh is implemented, add a `requestCount` test verifying it fires within 35s

File location: `tests/ui/test_athena_ui.spec.js`

### 4. Layout rules — keep it simple

- New tabs use `<div style={{overflowY:'auto',height:'100%',padding:'12px 14px'}}>` — same as every other tab
- Never use `flex:1` or `minHeight:0` on tab content divs — the parent `overflow:'hidden'` already handles it
- `height:'100%'` fills the available space; `overflowY:'auto'` makes it scroll
- Cards: `background:T.card, border, borderRadius:6, padding:12` — consistent with existing panels

### 5. Test coverage checklist for new Athena panels

Every new panel must have tests for:
- [ ] Tab button is present and visible
- [ ] Tab click renders content (no console errors)
- [ ] Panel header text is visible
- [ ] Key field labels are visible
- [ ] API endpoint returns valid structure (if new endpoint added)
- [ ] Section 508: header contrast ≥ 4.5:1, font ≥ 9px
- [ ] Auto-refresh verified (if applicable)
- [ ] All interactive buttons have `data-testid` attributes

### 6. Source attribution footer (MANDATORY for every new data panel)

Every panel that displays data from a file, DB table, or API must include a one-line source footer at the bottom:
```jsx
<div style={{marginTop:4,fontSize:8,color:T.textD,fontFamily:T.mono}}>Source: <path> · <brief note></div>
```
See `docs/ATHENA_UI_DATA_SOURCES.md` for the registry of all existing panel sources.

When adding a new panel:
(a) add the source footer as shown above, and
(b) add an entry to `docs/ATHENA_UI_DATA_SOURCES.md` with Source file, Written by, Refresh cadence, API endpoint, and Key fields.

Skip the footer only if the panel already has an equivalent note inline (e.g. Activity tab footer, Indicators tab description). Never add source lines inside repeated rows/lists — one per panel/card only.

**Never skip the RUN ANALYSIS panel.** It sources from `/api/backtest/compare` → `python/backtest_compare.py` → `aurum_tester.db` (forge_signals + forge_journal_trades + aurum_tester_runs). Its source footer must always read:
```
Source: /api/backtest/compare · backtest_compare.py · aurum_tester.db
```

### Backtest comparison accuracy rules (MANDATORY)

The RUN ANALYSIS panel uses `backtest_compare.py`. Before shipping any changes to it:

1. **Verify `balance` reads from `aurum_tester_runs.balance`** — not sim_start or any timestamp field. A wrong balance makes the P&L return % meaningless.

2. **Scoring formula (current — do not silently change):**
   - 40% win rate (`win_rate_pct / 100 * 40`)
   - 30% P&L return (`total_pnl / balance * 100`, capped at 5% return = full marks)
   - 15% loss avoidance (`(1 - loss_ratio) * 15`)
   - 15% take rate (`take_rate_pct / 0.05`, capped at 1.0, full at ≥0.05%)
   - Up to 5pt R/R bonus (`avg_win / |avg_loss|`, capped at 3:1)

3. **All-wins case**: never use a flat fallback — use `pnl_return_pct` directly. The flat 25.0 fallback was the original bug that made run #2 ($366) and run #3 ($257) score identically.

4. **Spot-check after any scoring change**: query the API with two runs that have meaningfully different P&L and verify the winner matches the higher-return run.

5. **Compare useEffect must depend on `[btSelRun, btPinnedRun, tab]`** — NOT on `btRuns`. The 30s auto-refresh of the runs list must NOT reset the comparison panel while the user is viewing it.

6. **Pin feature invariant**: pinned runs are always shown in the selector with `btAllRuns` injection, never counted in `display_limit`. The pin state (`btPinnedRun`) is the explicit comparison baseline.

### 7. Git — always version control test + code together

Every UI change commit must include:
- `dashboard/app.js` — the change
- `tests/ui/test_athena_ui.spec.js` — updated/new tests (even if unchanged, confirm count)
- Any new config/legend files (`config/*.json`)
- Any new API endpoint in `python/athena_api.py`

```bash
# Run tests first — required before staging
make test-ui

git add dashboard/app.js tests/ui/test_athena_ui.spec.js python/athena_api.py config/*.json
git commit -m "feat/fix(athena): description — tests: N/N pass"
```

**Commit message must include `tests: N/N pass`** — the exact count confirms tests were run, not skipped.

### 508 Audit script (alpha-compositing, use in Playwright evaluate)

```js
(() => {
  function lum(r,g,b){return[r,g,b].map(v=>{const s=v/255;return s<=.04045?s/12.92:Math.pow((s+.055)/1.055,2.4);}).reduce((a,c,i)=>a+c*[.2126,.7152,.0722][i],0);}
  function parse(s){const m=(s||'').match(/[\d.]+/g);if(!m||m.length<3)return null;return{r:+m[0],g:+m[1],b:+m[2],a:m[3]!==undefined?+m[3]:1};}
  function effectiveBg(el){let r=11,g=13,b=20;const layers=[];let cur=el;while(cur&&cur!==document.documentElement){const bg=parse(window.getComputedStyle(cur).backgroundColor);if(bg&&bg.a>0)layers.unshift(bg);cur=cur.parentElement;}for(const c of layers){r=c.a*c.r+(1-c.a)*r;g=c.a*c.g+(1-c.a)*g;b=c.a*c.b+(1-c.a)*b;}return{r,g,b};}
  function cr(fg,bg){const l1=Math.max(lum(fg.r,fg.g,fg.b),lum(bg.r,bg.g,bg.b))+.05;const l2=Math.min(lum(fg.r,fg.g,fg.b),lum(bg.r,bg.g,bg.b))+.05;return l1/l2;}
  const fails=[];const seen=new Set();
  document.querySelectorAll('span,div,button,p,label,a').forEach(el=>{
    const cs=window.getComputedStyle(el);
    const text=(el.childNodes.length===1&&el.childNodes[0].nodeType===3?el.innerText:'').trim();
    if(!text||text.length<2||text.length>80)return;
    const key=text+'|'+cs.fontSize+'|'+cs.color;
    if(seen.has(key))return;seen.add(key);
    const fs=parseFloat(cs.fontSize);
    if(fs<5||cs.display==='none')return;
    const fg=parse(cs.color);if(!fg)return;
    const bg=effectiveBg(el);const ratio=cr(fg,bg);
    const isLarge=fs>=18||(fs>=14&&parseInt(cs.fontWeight||'400')>=700);
    if(ratio<(isLarge?3:4.5)||fs<9)
      fails.push({text:text.slice(0,40),fs,ratio:Math.round(ratio*100)/100,tag:el.tagName});
  });
  return{totalFails:fails.length,items:fails.slice(0,20)};
})()
```

**IMPORTANT:** The naive `window.getComputedStyle(el).backgroundColor` returns the element's own bg, NOT the blended result of alpha-transparent parents. Always use the `effectiveBg()` function above (walks up the DOM and alpha-blends all layers) for accurate results. The wrong approach produces hundreds of false positives.

---

## ATHENA API Design — Maintenance Protocol

`docs/ATHENA_API_DESIGN.md` is the canonical reference for all Flask routes in `python/athena_api.py`.

**Update it whenever:**
- A new route (`@app.route`) is added to `athena_api.py`
- A route's response schema changes (new fields, removed fields, renamed fields)
- A new DB table is queried by a route
- A config/legend JSON file is added to the system

**What to update:**
1. `docs/ATHENA_API_DESIGN.md` — endpoint section 3.x with method, path, parameters, response schema, DB tables
2. `docs/CLI_API_CHEATSHEET.md` — add a curl+python one-liner for the new endpoint
3. `schemas/openapi.yaml` — add/update the path stub and any new schema objects
4. Section 5 (UI panel → endpoint mapping) if a UI panel is wired to the new endpoint
5. Section 6 (DB table reference) if a new table is involved

**Reference files:**
- API implementation: `python/athena_api.py`
- Gate legend source: `config/gate_legend.json` (add new gate codes here)
- Indicator legend source: `config/indicator_legend.json` (add new indicators here)
- Swagger spec: `schemas/openapi.yaml`
- UI design: `docs/ATHENA_UI_DESIGN.md`

---

## .env.example Maintenance Protocol

Whenever a new env variable is added to `.env` or to the sync script
(`scripts/sync_scalper_config_from_env.py`), `.env.example` **MUST** be updated
in the **same commit**. Never add a variable to `.env` and leave `.env.example`
stale.

### Rules

1. **Same-commit requirement** — `.env.example` changes are part of the feature
   commit, not a follow-up. If you are adding a new `FORGE_*` key to
   `sync_scalper_config_from_env.py`, the matching documented line in
   `.env.example` goes in the same `git add` / `git commit`.

2. **Correct section placement** — add the variable under the section header that
   matches its subsystem. Section headers follow the pattern:
   ```
   # ── SECTION NAME ────────────────────────────────────────────────────────
   ```
   Existing sections: CLAUDE API, TELEGRAM — CHANNEL READER, TELEGRAM — BOT,
   MT5 FILE BUS, FORGE MAGIC NUMBER, TRADINGVIEW MCP (LENS), TRADING PARAMETERS,
   SIGNAL MODE, REGIME ENGINE, AUTO_SCALPER MODE, FORGE SCALPER CONFIG,
   AEGIS, DRAWDOWN PROTECTION, SENTINEL, BRIDGE, RECONCILER, AURUM,
   WEB SEARCH, ATHENA, SCRIBE, LISTENER, VISION, SESSION BOUNDARIES,
   INTERNAL CONFIG FILE PATHS, DEFERRED ANALYSIS RUNS.

3. **Description comment required** — every variable must have a one-line
   comment immediately above it explaining what it does:
   ```
   # Minutes before a HIGH-impact event during which entries are blocked (0–240)
   FORGE_NEWS_FILTER_HIGH_BEFORE=20
   ```

4. **Default value shown** — the `.env.example` line must show the recommended
   default value. Commented-out lines (`# VAR=default`) are used for optional
   overrides; uncommented lines are used for required or commonly-set vars.

5. **Toggle explanation required for boolean vars** — always include the
   toggle meaning in the comment. Use `(0=disabled, 1=enabled)` for integer
   booleans and `(true/false)` for string booleans:
   ```
   # Apply the news filter in Strategy Tester runs (0=disabled, 1=enabled)
   FORGE_NEWS_FILTER_APPLY_IN_TESTER=0
   ```

6. **Units and valid range** — for numeric vars, include the unit and valid
   range in the comment where relevant:
   ```
   # Minutes before a HIGH-impact event during which entries are blocked (0–240)
   # Minimum SL distance as a fraction of ATR — structural SL cannot be tighter (0.3–3.0)
   ```

7. **Tester-only vars** — mark variables that only affect Strategy Tester runs
   with `[TESTER-ONLY]` in the comment:
   ```
   # [TESTER-ONLY] Apply loss cooldown in Strategy Tester (0=disabled, 1=enabled)
   FORGE_TESTER_COOLDOWN_ENABLED=1
   ```

8. **No real secrets** — `.env.example` must never contain real API keys,
   tokens, bot tokens, or passwords. Use placeholders:
   - API keys: `your_key_here`
   - Tokens: `your_token_here`
   - Hashes: `your_api_hash_here`

### Verification step

Run the following before and after to confirm the variable count increased:
```bash
grep -c "^[A-Z]" .env.example
```
The post-change count must be strictly greater than the pre-change count.
If the count did not increase, the variable was not properly added (check that
the line is not commented out when it should be active).

### Commit discipline

```bash
# Wrong — separate commit for .env.example
git add scripts/sync_scalper_config_from_env.py
git commit -m "feat(forge): add FORGE_NEW_GATE"
git add .env.example
git commit -m "docs: document FORGE_NEW_GATE"   # ← NEVER do this

# Correct — same commit
git add scripts/sync_scalper_config_from_env.py .env.example
git commit -m "feat(forge): add FORGE_NEW_GATE with .env.example docs"
```

---

## Regime Engine — Maintenance Protocol

`docs/REGIME_ENGINE_REVIEW.md` documents the FORGE HMM-based regime classification engine.

**Key design facts to remember:**
- **Entry point:** `python/regime.py` `RegimeEngine.infer()` — called every bridge tick (1s)
- **Feature vector:** 11 dimensions; features 7–10 (RSI, MACD, TV recommend, price delta) collapse to 0 when LENS is stale
- **States:** TREND_BULL, TREND_BEAR, VOLATILE, RANGE, UNKNOWN
- **Fallback:** `_gaussian_fallback()` when HMM not trained (first ~2 min after restart)
- **No persistence:** model lost on every bridge restart → 2-min cold-start each time

**Critical gotchas (read before modifying regime code):**
1. `model.fit()` runs synchronously in the bridge loop — can block 1–5s
2. LENS staleness uses `max(stale_sec, 300)` floor — accepts 5-min-old data when `REGIME_STALE_SEC=45`
3. Tester runs use `g_regime_confidence = 1.0` hardcoded — overstates gate effectiveness
4. Duplicate HMM state labels (both `"RANGE"`) have their posteriors summed — UI shows inflated confidence

**Update `docs/REGIME_ENGINE_REVIEW.md`** whenever:
- A new regime state is added
- Feature vector dimensions change
- New gates using regime are added (AEGIS or FORGE EA)
- HMM training parameters change (components, iterations, retrain interval)

## Athena UI — Drag-to-Resize Design Protocol

**MANDATORY: evaluate resizable panels for every significant Athena UI change.**

### When to apply drag-to-resize

Any panel that competes with another panel for screen space in the same axis is a candidate.

| Pattern | Apply when |
|---|---|
| Vertical drag (↕ row-resize) | Two panels stacked top/bottom within the same column — one grows at the other's expense |
| Horizontal drag (↔ col-resize) | Two columns side by side — one grows at the other's expense |

**Evaluate these questions before shipping any new panel:**
1. Is this panel sharing vertical space with another panel the user might want more of?
2. Is this panel sharing horizontal space (column width) with another panel?
3. Does the panel have a fixed min/max height/width that will feel cramped for some users?

If yes to any: add a drag handle.

### Standard implementation pattern

```jsx
// State (in parent component)
const [panelH, setPanelH] = useState(DEFAULT_PX);  // vertical
const [colW,   setColW]   = useState(DEFAULT_PX);   // horizontal

// Drag handle (vertical ↕)
<div
  title="Drag to resize <panel name>"
  onMouseDown={e => {
    e.preventDefault();
    const startY = e.clientY, startH = panelH;
    const onMove = ev => setPanelH(Math.max(MIN, Math.min(MAX, startH + (ev.clientY - startY))));
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }}
  style={{ height: 8, cursor: 'row-resize', display: 'flex', alignItems: 'center',
    justifyContent: 'center', borderTop: `1px solid ${T.border}`, background: T.bg }}>
  <div style={{ width: 36, height: 3, borderRadius: 2, background: T.border2, opacity: .6 }}/>
</div>

// Drag handle (horizontal ↔) — positioned absolute on column edge
<div
  title="Drag to resize <panel name>"
  onMouseDown={e => {
    e.preventDefault();
    const startX = e.clientX, startW = colW;
    const onMove = ev => setColW(Math.max(MIN, Math.min(MAX, startW + (ev.clientX - startX))));
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }}
  style={{ position: 'absolute', top: 0, right: -4, width: 8, height: '100%',
    cursor: 'col-resize', zIndex: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
  <div style={{ width: 3, height: 36, borderRadius: 2, background: T.border2, opacity: .5 }}/>
</div>
```

### Rules

- **Pill indicator is mandatory** — the 36×3px (vertical) or 3×36px (horizontal) pill is the visual affordance. Users won't discover drag without it.
- **Always set min AND max** — prevent panels from becoming unusably small or pushing others off-screen.
- **Title attribute required** — `title="Drag to resize <name>"` for tooltip and Playwright test discoverability.
- **Cursor must match axis** — `cursor: 'row-resize'` for vertical, `cursor: 'col-resize'` for horizontal.
- **Clean up listeners** — always remove `mousemove` and `mouseup` from `document` in the `mouseup` handler.
- **State in parent, not child** — drag state must live where it controls the layout, not inside the resized component.

### Existing drag handles in Athena (2026-05-10)

| Handle title | Axis | Range | Default | Controls |
|---|---|---|---|---|
| "Drag to resize sidebar" | ↔ horizontal | 140–320px | 186px | Left column width |
| "Drag to resize AURUM panel" | ↕ vertical | 140–600px | 280px | AURUM chat height vs main tabs |

**When adding a new column or panel to Athena:** check this table, verify no handle is missing for the new boundary, and add to the table above.

### Playwright verification

After adding a drag handle, always verify with:
```js
const handles = document.querySelectorAll('[title*="Drag"]');
// Expect count to match the table above
```
Then simulate a drag and confirm the panel dimension changed.
