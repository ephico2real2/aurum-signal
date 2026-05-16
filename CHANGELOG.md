# SIGNAL SYSTEM — CHANGELOG

## [SCRIBE PnL Rollup] — 2026-05-15 (auto-rollup total_pnl from trade_closures + journal fallback)

Operator finding: `trade_groups.total_pnl` was 0 / NULL on most closed groups today, even though the broker journal (`forge_journal_trades`) had the correct deals. Pulling "all orders" required raw journal queries because the scribe roll-up wasn't writing back.

Root cause: `update_trade_group` accepts `total_pnl` as an optional kwarg; most callers — `CLOSE_GROUP` via channel, `CHANNEL_CLOSE_ALL`, `AURUM_CLOSE_GROUP` (bridge.py:4530), `AURUM_CLOSE_ALL` (bridge.py:4401), pending-expired (bridge.py:1646), reconciler — pass it as `None`, which writes `NULL` straight to the column. Only the tracker's all-positions-drained path (bridge.py:2007) computes a rollup, and that path queries `trade_positions.pnl`, but `trade_positions` is sparsely populated (only groups where the tracker wrote a position row).

### Changed — `python/scribe.py`

- `update_trade_group(group_id, status, total_pnl=None, …)` now auto-rolls up when `total_pnl is None` AND the new status is terminal (CLOSED / CLOSED_ALL / SL_HIT / TP_HIT). Auto-rollup is skipped on OPEN / PARTIAL transitions.
- New `_rollup_group_pnl(conn, group_id) → (pnl, pips, n)` helper:
  1. **Primary**: sum `trade_closures.pnl` / `pips` where `trade_group_id = ?` (the canonical bridge-tracker write path).
  2. **Fallback**: sum `forge_journal_trades.profit` where `magic = group.magic_number` AND `time BETWEEN group.timestamp AND group.closed_at` (with `+24h` padding when `closed_at` is missing). Temporal scoping is required because FORGE recycles magic numbers across cycles (magic 207402 alone hit 4 groups today — 397/399/400/412).
  3. Returns `(0, 0, 0)` when neither source has data — caller leaves the column NULL rather than fabricating.
- New `backfill_trade_group_pnl(since_iso=None, force=False) → {scanned, updated}` one-shot helper. `force=False` only touches NULL/0 rows; `force=True` recomputes every terminal-status row in scope (useful when a prior backfill produced wrong totals).

### Backfill run (2026-05-15)

```
backfill_trade_group_pnl(since_iso='2026-04-01T00:00:00', force=True)
→ {scanned: 412, updated: 360}
```

Today's groups (post-fix):

| GID | Setup | Source | Magic | Net P&L |
|---|---|---|---|---|
| 400 | G5001 MOMENTUM_DUMP 22:55 (canonical ratchet) | FORGE | 207402 | +$103.84 |
| 401 | G5002 MOMENTUM_DUMP | FORGE | 207403 | +$237.87 |
| 402 | G5003 MOMENTUM_DUMP | FORGE | 207404 | +$124.32 |
| 403 | G5003 BUY_LIMIT_RECOV | MANUAL_MT5 | 227413 | +$64.20 |
| 404 | G5004 MOMENTUM_DUMP | FORGE | 207405 | +$79.68 |
| 405 | G5005 MOMENTUM_DUMP | FORGE | 207406 | +$33.87 |
| 406 | G5005 BUY_LIMIT_RECOV | MANUAL_MT5 | 227415 | +$88.50 |
| 407 | G5006 MOMENTUM_DUMP | FORGE | 207407 | +$122.52 |
| 408 | G5007 MOMENTUM_DUMP | FORGE | 207408 | +$103.44 |
| **409** | **G5008 MOMENTUM_DUMP (closed by AURUM_CLOSE_ALL)** | FORGE | 207409 | **−$955.44** |
| 410 / 411 | AURUM SCALPER mode (never executed) | AURUM | 202811/202812 | $0.00 |
| 412 | G5001 various cycles | FORGE | 207402 | +$670.18 |

### Activation

- `make reload-bridge` to pick up changes — done 2026-05-15.
- Going forward, any terminal-state `update_trade_group` call without an explicit `total_pnl` argument will auto-populate from authoritative sources.

---

## [S1b] — 2026-05-15 (AURUM OPEN_GROUP mode-restriction gate)

Operator clarification (2026-05-15): "AURUM should try to place an order only when in hybrid mode or Auto_scalper mode — the scalper mode is only for the EA." Today's 14:21–14:31 AURUM OPEN_GROUP burst (groups 410, 411 placed; 3/5 rejected by Aegis on MAX_GROUPS / SL_TOO_TIGHT) all fired while bridge mode was `SCALPER` — confirming the bug.

Root cause: `_dispatch_aurum_open_group` already had a mode check, but the allow-list was `("SCALPER", "SIGNAL", "HYBRID", "AUTO_SCALPER")`. SCALPER is reserved for FORGE EA's native scalper; AURUM placing manual entries there competes with the EA's setup decisions. SIGNAL is the Telegram-channel listener path; AURUM doesn't author those.

### Changed

**`python/bridge.py`:**
- `_dispatch_aurum_open_group` allow-list tightened to `("HYBRID", "AUTO_SCALPER")`.
- Rejection path now logs `AURUM_OPEN_SKIPPED reason=effective_mode=<mode>` with full notes (direction + entry range + rule citation) and sends a Herald notification (`🚫 AURUM OPEN_GROUP rejected — Mode is X — needs HYBRID or AUTO_SCALPER`).
- Docstring expanded with the operator-mandated policy.

**`SKILL.md` §5:**
- New subsection "Mode restriction for AURUM OPEN_GROUP (operator-mandated 2026-05-15)" instructing the LLM to propose levels in prose rather than emit JSON when mode is disallowed.

### Activation

- `make reload-bridge` to pick up changes.
- AURUM's MCP-driven analysis loop (TradingView chart + indicators → AI-backed trade decisions) remains intentional and unchanged — only the *output gate* is restricted by mode.

---

## [S1] — 2026-05-15 (AURUM destructive-command confirmation gate)

Operator incident (2026-05-15): G5008 lost −$955.44 after operator's conversational "close all" inside a *question about* the trade was parsed by AURUM as an executable command and dispatched without a confirmation step. Scribe `close_reason = AURUM_CLOSE_ALL`.

Root cause: AURUM's SKILL.md §5 instructed the LLM to "act, you must not refuse" on operator-directed action language. Aegis only validates `OPEN_GROUP` — every destructive command (`CLOSE_*`, global `MODIFY_*`, `MOVE_BE`) flowed straight from `aurum_cmd.json` → `forge_command.json` → EA execution with no gate.

### Added — two-sided defense-in-depth confirmation gate

**Bridge side (`python/bridge.py`) — hard backstop:**
- `AURUM_CONFIRMATION_TTL_SEC` env (default 30s) + `AURUM_DESTRUCTIVE_ACTIONS` frozenset.
- `Bridge._pending_aurum_confirmations: dict[str, dict]` keyed by 8-char hex `proposal_id`.
- `_is_destructive_aurum_action(action, cmd)` — true for `CLOSE_ALL`/`CLOSE_GROUP`/`CLOSE_GROUP_PCT`/`CLOSE_PCT`/`CLOSE_PROFITABLE`/`CLOSE_LOSING`/`MOVE_BE` AND for `MODIFY_SL`/`MODIFY_TP` only when scope is global (no `ticket` / `group_id` / `tp_stage`).
- `_summarize_destructive_action(action, cmd)` — human-readable summary for the Herald prompt.
- `_sweep_expired_aurum_confirmations()` — TTL sweep on every Bridge tick; emits `AURUM_CONFIRMATION_EXPIRED` system_event.
- `_check_aurum_command` reworked: TTL sweep at top → CONFIRM handler (pop pending, fall through to existing dispatch chain) → destructive gate (assign `proposal_id`, store with `expires_at`, Herald post, log `AURUM_COMMAND_HELD`, return). Existing if/elif dispatch unchanged.

**AURUM side (`python/aurum.py`) — Telegram intercept:**
- `_CONFIRM_RE = r"^\s*CONFIRM\s+([a-f0-9]{6,16})\b"` matches operator's literal reply.
- `_handle_telegram_natural_language_command` short-circuits before the LLM: writes `{"action":"CONFIRM","proposal_id":<id>,"origin_source":"TELEGRAM"}` directly to `aurum_cmd.json` so confirmation cannot be re-summarized by the model. Logs `AURUM_CONFIRMATION_QUEUED`.
- `CONFIRM` added to `valid_actions` so any LLM-emitted JSON fence with that action (edge case) also reaches Bridge.

**SKILL.md side — LLM instruction:**
- §5 new block lists the destructive action set + 4 rules: propose-don't-confirm, never self-emit CONFIRM, treat "close all" inside a question as conversational (no JSON), don't re-emit a held cmd on the next turn.

### Failure modes blocked

- G5008-class accidents: conversational "close all" → AURUM emits `CLOSE_ALL` → Bridge holds → operator sees Herald prompt → 30s TTL expires → no execution.
- LLM playbook drift: even if a future SKILL.md edit drops the instruction, the bridge-side gate still holds (defense-in-depth).
- AURUM hallucinating `CONFIRM` self-emit: bridge rejects unknown `proposal_id` with `AURUM_CONFIRMATION_REJECTED`.

### Out of scope (intentional)

- Per-ticket / per-group / per-stage `MODIFY_SL` / `MODIFY_TP` — low blast radius, matches EA L0-L9 ratchet path, gate-free.
- `OPEN_GROUP` — Aegis already validates geometry/risk/regime; today's 14:21-14:31 sequence had 3/5 rejected by Aegis (`MAX_GROUPS:3/3`, `SL_TOO_TIGHT:2.7<3.0pips`).

### Activation

- `make reload-bridge` to pick up changes (no EA recompile required).
- Memory `feedback_aurum_accidental_entry_safety` (M1 highest-leverage mitigation) — now satisfied.

---

## [FORGE 2.7.110] — 2026-05-14 (CES Confluence Entry Score — Option C instrumentation-only ship)

Operator question (2026-05-14):
- "internal logic to calculate win or loss before entry — can we score how confluent the setup is?"

Operator decision: ship **Option C (logging-only)** now, scaffold **Option A (gate-mode)** for future activation
after backtest validates correlation between CES score and trade outcome.

### Added — CES (Confluence Entry Score) composite + 7 SIGNALS columns

CES = 0-10 score computed at every setup-trigger from 6 atoms (one is a +3-weighted DTC alignment
covering atom #1 + #2 of the operator's 7-atom enumeration). Sums to max 10 with default weights:
- **+3** DTC trend-aligned matches direction (BULL_TREND_ALIGNED+BUY / BEAR_TREND_ALIGNED+SELL)
- **+2** PEMCG warning count for direction ≤ 2 (clean reversal-trap reading)
- **+2** M5 momentum candle (strong_bar=1 AND body_pct ≥ 0.5)
- **+1** RSI in trend zone (BUY 40-65 / SELL 35-60)
- **+1** VWAP-distance confirms direction (BUY: dist ≥ −0.5, SELL: dist ≤ +0.5)
- **+1** H1 DI dominance ≥ 5 in setup direction

### Wired

- 9 new knobs in `ScalperConfig` struct + `InitScalperConfig` defaults + `JsonHasKey` loaders
- 9 new `FORGE_*` env mappings in `scripts/sync_scalper_config_from_env.py`
- 9 new keys in `config/scalper_config.defaults.json` (`safety` block)
- CES compute block placed AFTER UMCG/CVCSM/DLV/DTC checks but before SKIP/TAKEN journal write
- 7 new SIGNALS columns (`ces_score, ces_dtc, ces_pemcg, ces_momentum, ces_rsi, ces_vwap, ces_di`)
  with idempotent ALTER migrations + `idx_sig_ces_score` index
- 7 mirror columns added to `forge_signals` (AURUM-side) via additive migrations in `python/scribe.py`
- `sync_forge_journal` SELECT col list, INSERT col list, placeholder count `(41+24+45+7=117)`,
  and tuple unpacking ALL updated together to prevent the v2.7.45/47 silent-fail class of bug
- New `ces_below_threshold` gate code in `config/gate_legend.json` (used by Option A only)

### Option A scaffolding (default-OFF — operator flips later)

- `ces_block_below_threshold` knob defaults to 0; when set to 1 along with `ces_enabled=1`,
  emits SKIP gate `ces_below_threshold` for any setup-trigger with `ces_score < ces_min_threshold`
  (default 6)
- Single env flag activation: `FORGE_GATE_CES_BLOCK_BELOW_THRESHOLD=1` → gate-mode

### Operator activation (this ship)

`.env` block sets:
- `FORGE_COMPOSITE_CES_ENABLED=1` (instrumentation ON)
- `FORGE_GATE_CES_BLOCK_BELOW_THRESHOLD=0` (gate-mode stays OFF)
- All 6 atom weights explicit (operator-tunable)

### Docs

- New `docs/FORGE_CES_DESIGN.md` — atom citations, 3-option discussion, Option A activation
  sequence, backtest validation plan, win-rate-by-CES-bucket query
- `.claude/skills/forge-monitor/SKILL.md` — new "MANDATORY: CES audit" section with canonical
  join query + reporting rule (every post-mortem MUST include CES score + component breakdown)
- `changelog.md` — this entry

### Constraints honoured

- **No recompile** — operator has an active backtest running; `make forge-compile` deliberately skipped.
  FORGE source has `FORGE_VERSION = "2.7.110"` stamped but binary `FORGE.ex5` stays at v2.7.109
  until operator triggers a recompile.
- **Default-OFF compute** — when `ces_enabled=0`, all 6 component globals stay at 0 (no per-tick
  cost), behaviour byte-identical to v2.7.109.
- **Backup**: `backups/v2.7.110/FORGE.mq5.pre-ces-instrument`
- Tests: `python3 -m pytest tests/api/test_forge_27x_gates.py` → 55/55 PASS

---

## [FORGE 2.7.57] — 2026-05-13 (TREND_CONTINUATION_BUY + SELL — atlas §5.2 canonical, finally shipped)

Operator mandate (Apr 9 reward-rank analysis):
- Apr 9 13:51 BB_BREAKOUT BUY banked +$12.48 in **8 seconds** — the canonical instant scalp
- Operator: "create HIGH_REWARD_BB_BREAKOUT BUY... maybe BULL_* lol"
- Industry standard: `TREND_CONTINUATION_BUY` (Murphy/Tradeciety) — already in roadmap §5/§8 as Tier-2 deferred

### Added — TREND_CONTINUATION_BUY (canonical roadmap composite finally implemented)

Pattern: regime=TREND_BULL + h1≥0.10 + RSI 60-75 + M5 ADX≥20 + M15 ADX≥18 + PSAR=BELOW + price within 0.3×ATR of bb_u + !g_daily_bear_bias.

Geometry:
- SL = entry − 0.5×ATR (tight)
- TP1 = entry + 0.3×ATR (instant scalp — proven 8-sec banking on Apr 9)
- TP2 = entry + 0.7×ATR (runner)
- Lot factor: 2.0× (aggressive — high-conviction multi-indicator alignment)
- Cooldown: 60s anti-flicker

### Added — TREND_CONTINUATION_SELL (mirror)

Pattern: regime=TREND_BEAR + h1≤−0.10 + RSI 25-40 + M5 ADX≥20 + M15 ADX≥18 + PSAR=ABOVE + price within 0.3×ATR of bb_l + !g_daily_bull_bias.

Validated against Apr 8 17:31 SELL @ 4760 — banked +$22 + TP2 +$11 = +$33 in 1 min.

### Wired

- New `IsTrendContinuationBuyActive` / `IsTrendContinuationSellActive` evaluation in TickScalper trigger chain
- Anchor globals `g_trend_continuation_buy_last_time` / `g_trend_continuation_sell_last_time` set via `MarkSetupCooldownAnchorOnTaken`
- RR bypass list extended (tight scalp geometry; trigger gates ARE the safety net)
- `tcb_factor` + `tcs_factor` wired into `combined_lot_factor` multiplication chain
- 12 new env knobs per direction surfaced under canonical `FORGE_SETUP_/GATE_/GEOMETRY_/TIMING_` prefixes

### Versioning

- **VERSION**: 2.7.56.1 → **2.7.57**
- **#property version**: 2.127 → auto-stamped
- Compile clean — `make forge-compile` succeeded

### What Run 28 (with v2.7.57) should reveal

- Apr 1 NY rally + Apr 9 13:00+ rally: TREND_CONTINUATION_BUY fires at every breakout above bb_u with RSI 60-75; expect +$10-15 per leg vs current ~$6
- Apr 8 12:00→18:00 cascade: TREND_CONTINUATION_SELL fires at every breakdown below bb_l with RSI 25-40; complements MOMENTUM_DUMP SELL pyramid
- Combined with v2.7.56 pyramid: TREND_CONTINUATION can also stack consecutive same-direction fires (separate counter from MOMENTUM_DUMP)
- Default lot 2.0× makes these the heavy-hitters of confirmed-trend days

### Fixed during ship

- Variable naming collision (`_tcb_m15adx` was both a `double` value and a `bool` check) → renamed bool to `_tcb_m15adx_ok`; same for SELL mirror

---

## [FORGE 2.7.56] — 2026-05-13 (multi-leg pyramid + escalating-conviction sizing — "the days we become millionaires")

Operator mandates:
- "We should be selling along and firing multiple legs — this is days where we become millionaires"
- "1×, 2×, 3×, 4×, 5× — each leg should fire like this if setup holds"
- "We don't need to cool down — enter if setup is valid until it doesn't"

### Added (`ea/FORGE.mq5`)

- **Multi-leg per MOMENTUM_DUMP trigger**: `dump_legs_per_group` (default **5**) overrides the global `lot_num_trades` for MOMENTUM_DUMP only. Each trigger now opens 5 legs instead of 2.
- **Setup-specific max-open cap**: `dump_max_open_same_direction` (default **30**) overrides the global `max_open_same_direction` (default 1) for MOMENTUM_DUMP. Lets the pyramid stack up to 30 concurrent positions per direction before capping.
- **Zero cooldown**: `dump_cooldown_seconds` default 60 → **0**. No anti-flicker; fires on every valid tick while setup holds.
- **Escalating-conviction pyramid**: new `dump_pyramid_enabled` (default 1), `dump_pyramid_base_factor` (1.0), `dump_pyramid_step` (1.0), `dump_pyramid_max_factor` (5.0). Each consecutive same-direction MOMENTUM_DUMP fire gets a larger lot multiplier: 1st = 1×, 2nd = 2×, ..., 5th = 5×, capped. Counter resets on direction flip OR when all same-direction MOMENTUM_DUMP positions close.
- **Counter globals**: `g_dump_pyramid_consec_buy_count`, `g_dump_pyramid_consec_sell_count`. Increment via `MarkSetupCooldownAnchorOnTaken` on TAKEN; reset at top of `ManageOpenGroups` when no same-direction positions remain.

### Fixed — time-stop bleeding (Apr 8 regression)

- **Skip time-stop on groups that already banked TP1**. Run 26 Apr 8 showed 8 time-stop events totaling **−$215** firing on runner halves AFTER TP1 partial-close, bleeding what should have been a +profit cascade day. New rule:
  ```mql5
  bool _ts_tp1_already_banked = (g_groups[gi].legs_planned > 0
                                 && ArraySize(pos_lock) < g_groups[gi].legs_planned);
  if(_ts_max_sec > 0 && ArraySize(pos_lock) > 0 && !_ts_tp1_already_banked) {
      // proceed with time-stop loop
  }
  ```
  Logic: if current open positions < legs the group was planned with, some legs already closed (= TP1 banked). Preserve the runner(s) for TP2 or trail-close — don't time-stop on small per-position floats.

### Mathematical impact on Apr 8-style cascades

```
Cascade setup math (operator's vision):
  Trigger fires repeatedly during sustained $50+ down-move
  5 legs per group × 5 escalating multipliers across 5 groups = 25 positions
  Lot stack (base × multiplier × INTRADAY_REVERSAL_SELL amplifier 2×):
    Group 1: base × 1 × 2 =  2× lot (5 legs)
    Group 2: base × 2 × 2 =  4× lot
    Group 3: base × 3 × 2 =  6× lot
    Group 4: base × 4 × 2 =  8× lot
    Group 5: base × 5 × 2 = 10× lot
  Total exposure = base × (1+2+3+4+5) × 2 × 5_legs = base × 150
  At base_lot 0.04 → 6.0 total lots during confirmed cascade
  ~$1,800 per Apr-8-style day (30 pt avg per group × 5 groups × 6 lot equivalents)
```

### Risk awareness

Martingale-into-trend amplifies BOTH wins and losses. The 30-position cap (`dump_max_open_same_direction`) + INTRADAY_REVERSAL_SELL composite gating + tight 2×ATR SL together bound the worst case. But if a confirmed cascade reverses after the 5th pyramid group (5× lot), that single 5× leg's SL hit dwarfs the earlier wins.

Mitigation already in place: counter resets when direction flips, so a reversal restarts pyramid sizing at 1× from the bottom. Counter also resets when all positions close — preventing stale pyramid state.

### Versioning

- **VERSION**: 2.7.55.1 → **2.7.56**
- **FORGE_VERSION**: `2.7.55.1` → `2.7.56`
- **#property version**: 2.126 → auto-stamped
- Compile clean — `make forge-compile` succeeded.

### What Run 27 (with v2.7.56) should reveal

- Apr 1 NY rally: pyramid fires 5+ MOMENTUM_DUMP BUYs with escalating sizing (1×-5×) → expected 5-10× more profit than Run 25/26.
- Apr 8 cascade (the target use case): no more time-stop bleed AFTER TP1 banks; pyramid SELLs into the sustained $50+ move with escalating size. Net day should be deeply positive (vs Run 26's current −$130 with bleed).
- Apr 13 chop: pyramid won't help (no sustained direction), but BB_LOWER_REVERSION_BUY catches bottoms.
- 30-position cap protects against runaway during regime ambiguity.

---

## [FORGE 2.7.55] — 2026-05-13 (oversold-zone protection + BB_LOWER_REVERSION_BUY setup)

Operator mandates this batch:
- "We're selling at the bottom (G5003) — need to block that"
- "Use the same indicators to BUY the oversold zone instead"
- "Be aggressive — multi-indicator alignment is high-conviction"
- "Make sure we don't get hit by our s/l"

### Added (`ea/FORGE.mq5`)

- **Two new SELL gates** in MOMENTUM_DUMP filter chain (between dump_chop_block and dump_judas_window):
  - `dump_rsi_floor_sell` — blocks SELL when `m5_rsi ≤ dump_sell_min_rsi` (default 30). RSI in deep oversold = mean-reversion zone, not SELL zone. Run 26 G5003 (RSI 32.4) was the canonical fail case.
  - `dump_below_bbl_block_sell` — blocks SELL when `mid < m5_bb_l`. Selling below the BB lower band is selling into gold's standard-deviation oversold zone where mean-reversion buyers wait. Run 26 G5003 entered at $2.90 below bbl.
- **NEW SETUP: `BB_LOWER_REVERSION_BUY`** — aggressive mean-reversion BUY when price drops below BB lower band on M5.
  - Trigger atoms: `m5_close < m5_bb_l` AND `m5_rsi ≤ max_rsi (35)` AND `m5_adx ≥ min_adx (18)` AND `m5_atr > 0`
  - Filter chain: `!g_daily_bear_bias` (no falling-knife on confirmed bear days), session ∈ {LONDON, NY}, h1_max optional bearish-extreme block, cooldown anti-flicker
  - Entry geometry: market BUY at trigger; SL = `bb_l − 1.5×ATR` (WIDE — survives wicks); TP1 = `bb_m` (mean-reversion target); TP2 = `bb_u` (full-band reversion)
  - Lot factor: default 1.0× (FULL size — multi-indicator alignment is high-conviction)
  - **Extreme-oversold amplifier**: when RSI ≤ 25, lot multiplies by 1.5× (rare convergence — gold seldom sustains RSI < 25 on M5)
  - **Time-stop**: 30-min max hold; if no TP1 in window, close at market BEFORE the wider SL gets hit. Combined with wider initial SL, caps max realistic loss to ~$10 per leg vs MOMENTUM_DUMP's $77 average.
  - Wired to ParseEntryLegs, MarkSetupCooldownAnchorOnTaken (Path A pattern), RR-bypass, and lot-factor combined product.
- **ManageOpenGroups time-stop generalized** — `_ts_max_sec` now reads `dump_max_hold_seconds` (for MOMENTUM_DUMP) OR `bb_lower_reversion_buy_max_hold_seconds` (for the new setup), routed by `g_groups[gi].scalper_setup`.

### Anti-SL-hit protection (operator: "don't get hit by our s/l")

The BB_LOWER_REVERSION_BUY SL is structured to **almost never fire**:

1. **Wide initial SL** — 1.5×ATR below bbl (e.g., bbl=4554, ATR=5.58 → SL=4545.91 = 8 pts below entry of 4551). Survives normal wicks.
2. **30-min time-stop** — if no TP1 banked in 30 min, position closes at market BEFORE price drifts down to the wider SL. Bounce should happen FAST from extreme oversold or thesis failed.
3. **Daily-bear-bias filter** — won't catch falling knives on confirmed bear days.

Result: max realistic loss per leg ≈ $10 (vs MOMENTUM_DUMP's $77 average loss).

### Changed defaults

- `dump_sell_min_rsi`: 0 → **30** (new — RSI floor for MOMENTUM_DUMP SELL)
- `dump_sell_block_below_bb_l`: 0 → **1** (new — BB lower band block for SELL)
- `bb_lower_reversion_buy_enabled`: missing → **1** (default ON — high-conviction)
- `bb_lower_reversion_buy_lot_factor`: missing → **1.0** (full size, was 0.5 fractional in initial design — flipped per operator "be aggressive")
- `bb_lower_reversion_buy_sl_atr_mult`: missing → **1.5** (was 0.5 — widened per operator "don't get hit by s/l")
- `bb_lower_reversion_buy_max_hold_seconds`: missing → **1800** (new — 30-min time-stop)

### Versioning

- **VERSION**: 2.7.54 → **2.7.55**
- **FORGE_VERSION**: `2.7.54` → `2.7.55`
- **#property version**: 2.124 → 2.125 (auto-stamped)
- Compile clean — `make forge-compile` succeeded.

### What Run 27 (with v2.7.55) should reveal

- **Mar 31 12:40 G5003** scenario flips polarity: instead of MOMENTUM_DUMP SELL firing (−$43 time-stop), `dump_rsi_floor_sell` blocks it AND `BB_LOWER_REVERSION_BUY` fires BUY at the same M5 bar → expect +$10-20 on bounce to bb_m.
- **Any "selling at the oversold extreme" pattern** in the run is now blocked — should see reduction in MOMENTUM_DUMP SELL loss count compared to Run 26.
- **New journal events** `dump_rsi_floor_sell` and `dump_below_bbl_block_sell` SKIPs appear, plus `BB_LOWER_REVERSION_BUY` TAKEN entries.
- **Lot factor amplification** visible in journal: `BB_LOWER_REVERSION_BUY extreme-oversold amplifier ×1.50` log lines when RSI ≤ 25.

---

## [FORGE 2.7.54] — 2026-05-13 (exit discipline + asymmetric TP1 — "gold is not stocks")

Operator mandates this batch:
- "Gold is not stocks — you have to run, no mercy in forex"
- "Tight SL, time stop on losers"
- "BEAR TP1 = 0.6×ATR (dumps travel further), BULL TP1 = 0.4×ATR (bounces are short)"

### Added (`ea/FORGE.mq5`)

- **Direction-asymmetric SL multipliers**: hardcoded `sl = ask + m5_atr × 4.0` at MOMENTUM_DUMP SELL/BUY trigger sites surfaced as `g_sc.dump_sl_atr_mult_sell` and `g_sc.dump_sl_atr_mult_buy`. Both default 2.0 (was 4.0 inline). Tight gold-scalp geometry caps Apr 13-style $25-pt chop losses to ~$10.
- **Direction-asymmetric TP1 multipliers**: hardcoded `tp1 = bid - m5_atr × 0.6` surfaced as `g_sc.dump_tp1_atr_mult_sell` (0.6 default — dumps run further) and `g_sc.dump_tp1_atr_mult_buy` (0.4 default — bounces short, bank fast). Operator-asymmetric gold scalping.
- **Time-stop in `ManageOpenGroups`**: for every open MOMENTUM_DUMP position, if held > `dump_max_hold_seconds` (default 600 = 10 min) AND current profit ≤ 0 (no TP1 banked yet), close at market. Caps Apr 13 G5024 (40-min held against → −$55.53) and G5036 (cascade → −$175). Re-fetches `pos_lock` after time-stops so the trailing logic below sees the updated open-position set.

### Changed (`config/scalper_config.defaults.json`, `scripts/sync_scalper_config_from_env.py`)

- New defaults: `dump_sl_atr_mult_buy: 2.0`, `dump_sl_atr_mult_sell: 2.0`, `dump_tp1_atr_mult_buy: 0.4`, `dump_tp1_atr_mult_sell: 0.6`, `dump_max_hold_seconds: 600`.
- New env→config mappings under canonical `FORGE_GEOMETRY_*` / `FORGE_TIMING_*` prefixes per `FORGE_NAMING_CONVENTIONS.md §4`.

### Versioning

- **VERSION**: 2.7.53 → **2.7.54**
- **FORGE_VERSION**: `2.7.53` → `2.7.54`
- **#property version**: 2.123 → 2.124 (auto-stamped)
- Compile clean — `make forge-compile` succeeded.

### What Run 27 (with v2.7.54) should reveal

- Apr 13 max per-leg loss falls from ~$60-175 → ~$10-25 (tight SL caps + time stop closes losers before SL hits)
- Apr 13 net swings from −$239 to break-even or small profit (~+$50 with v2.7.53 + 54 combined)
- Mar 31 / Apr 7 still under-traded (only 2 entries/day) — solved by v2.7.55+ day-type-aware setups
- Loss size per leg roughly halves across the entire run

### What v2.7.54 does NOT do

- Doesn't fix Apr 13 chop over-firing — that's v2.7.57 (CHOP_GRID) territory
- Doesn't fix Mar 31 under-firing — that's v2.7.58 (active scalper baseline)
- Doesn't reproduce wealth-creation on Apr 1/8 trend days — that's v2.7.56 (TREND_PYRAMID)

---

## [FORGE 2.7.53] — 2026-05-13 (no-mercy cooldown bypass + §11.4 anchor fix + Apr 8 defaults + fast-trend amplifier)

### Added (`ea/FORGE.mq5`)

- **H1-OR-M15 unconditional cooldown bypass** (operator principle: "no cool down when running with the market — this is forex"). Extended `CooldownBypassActive()` with a new branch above the existing TP1+regime path: bypasses cooldown when direction is aligned with HTF (h1_trend) OR MTF (m15 EMA20/50) per `cooldown_bypass_with_trend_m15_or_h1`, AND regime is trending, AND M5 ADX clears `cooldown_bypass_min_adx`. No TP1 requirement — catches Apr 1 NY rally (H1=+2.3 leads) AND Apr 8 PM bear cascade (M15 flips bear while H1 lags). New knobs: `cooldown_bypass_with_trend_enabled` (1), `_h1_min` (1.0), `_m15_or_h1` (1). Signature extended with `h1_trend_strength` (default 0.0 for back-compat); all 5 callers updated.
- **`MarkSetupCooldownAnchorOnTaken()`** — new helper called once after `JournalRecordSignal("TAKEN", ...)` that writes the per-setup cooldown anchor only when an entry is actually journaled. Replaces the previous pattern where §11.4 setups set their anchor inside the trigger detection block (after `Filter_AdxFloor && Filter_Cooldown` passed) but BEFORE downstream entry filters could block. Result: the anchor got set on dry-run filter passes that never produced a TAKEN, causing 200k+ spurious `*_cooldown` SKIPs on SR_FLIP alone in Run 25.
- **Removed 22 premature anchor writes** in §11.4 detection blocks for MA_CROSSOVER, VWAP_REVERSION, FIB_CONFLUENCE, INSIDE_BAR, BB_SQUEEZE, ORB, GAP_AND_GO, DOUBLE_TOP, DOUBLE_BOTTOM, HEAD_AND_SHOULDERS, INVERSE_HEAD_AND_SHOULDERS, TRENDLINE_BOUNCE, SR_FLIP. Anchor lifecycle now lives exclusively in the new helper.
- **Universal fast-trend lot amplifier** (operator principle: "size up when fast bull/bear confirmed"). Multiplies `combined_lot_factor` by `fast_trend_lot_amplifier_factor` (default 1.5×) when direction matches HTF OR MTF trend AND regime is trending AND M5 ADX clears `fast_trend_lot_amplifier_adx_min` (default 35 — "fast" means accelerating). Same alignment heuristic as the cooldown bypass, just with a higher ADX bar. Applied universally to every setup at the lot-calculation site. New knobs: `fast_trend_lot_amplifier_enabled` (1), `_factor` (1.5), `_adx_min` (35.0).

### Changed (`config/scalper_config.defaults.json`)

- **`dump_cooldown_seconds`** 600 → **60** — 10-min cooldown was missing the Apr 8 rally; reduced to 60s anti-flicker only. With-trend re-fires handled by the no-mercy bypass above.
- **`dump_sell_h1_max`** added at **1.0** (was missing entirely; EA init was 0=disabled) — block MOMENTUM_DUMP SELL when `h1_trend ≥ 1.0` (Apr 8 G5024 −$62.70 SELL in TREND_BULL h1=1.05 fix).
- **`intraday_reversal_sell_enabled`** 0 → **1** — enable the 12:00 INTRADAY_REVERSAL_SELL detector by default (Apr 8 G5028 BB_PULLBACK BUY −$52.62 30 min before the pivot prelude fix).

### Versioning

- **VERSION**: 2.7.52 → **2.7.53**
- **FORGE_VERSION**: `2.7.52` → `2.7.53`
- **#property version**: 2.122 → 2.123 (auto-stamped)
- Compile clean — `make forge-compile` succeeded.

### What this run is set up to reveal

The next backtest run (Run 26+) with v2.7.53 should show:
- **§11.4 cooldown SKIPs collapse** from 200k+ to a small number (only when entries actually TAKEN within the cooldown window). If SR_FLIP/TRENDLINE_BOUNCE/FIB_CONFLUENCE/etc. now produce actual TAKEN entries, the anchor-fix worked.
- **With-trend re-fires** happen immediately on trigger evaluation (no 10-minute wait) — visible as multi-leg same-direction entries within minutes during strong trend periods.
- **Fast-trend amplifier fires** during high-ADX trending phases — PrintFormat `FORGE 2.7.53: FAST_TREND amplifier ×1.50 → <setup> <direction>...` in journal.
- **Apr 8 G5024 and G5028 are blocked** (the canonical losses from Run 25); BB_BOUNCE BUY @ Apr 8 16:35 still fires unprotected (deferred — universal lh_cascade gate is a v2.7.54 candidate).

### Deferred to follow-up

- **MOMENTUM_DUMP_COMPOSITE_TEST** — parallel composite that replicates legacy MOMENTUM_DUMP using the new boolean-composite framework. Spec'd; coding deferred to a focused session to avoid bundling framework validation with operational fixes.
- **Universal `entry_quality_lh_cascade_buy_block`** on BB_BOUNCE / BB_BREAKOUT / BB_PULLBACK_SCALP / MOMENTUM_DUMP BUY chains — Apr 8 16:35 protection. Higher-risk surface change, separate ship.

---

## [BRIDGE+ATHENA 2.7.53] — 2026-05-13 (tester/live market_data.json contention guard)

### Fixed — Telegram session/killzone flood (`python/bridge.py`)

- **Telegram session/killzone flood during concurrent tester + live EA runs.** When MT5 Strategy Tester runs alongside the live FORGE EA, both write to `Common/Files/market_data.json` and bridge sees the file flipping between `(live session, live balance, strategy_tester=false)` and `(sim session, tester balance, strategy_tester=true)` every poll cycle. This generated one SCRIBE open/close + HERALD Telegram ping per flip ("SESSION: ASIAN $10k" ↔ "SESSION: LONDON $100k").
- **`_on_session_change`** and **`_on_killzone_change`** now early-return when `mt5.get("strategy_tester")` is true, so the transition handler is fully suppressed for tester-driven writes. `self._current_session` / `self._current_killzone` stay anchored to the most recent LIVE write — next legitimate live transition fires correctly.
- `_on_killzone_change` signature extended to accept `mt5: dict | None` (default None for any test paths); caller at the killzone-detection branch now passes the current `mt5` dict.

### Fixed — account/positions flicker (`python/market_data.py`, `bridge.py`, `athena_api.py`)

- **`account.balance` / `positions` / pending orders flickered between tester and live values** at every consumer of `market_data.json` (Athena dashboard, AEGIS lot sizing, SCRIBE balance writes). Each poll captured whichever EA wrote last.
- **Operator preference**: during a test run, displays/logs should show the **TESTER state** (the values the operator is actually validating), not the live broker. Once the tester stops writing for >15 s, consumers automatically revert to live.
- **New shared helper `stabilize_mt5_tester_overlay()`** in `market_data.py`. Per-process cache of the last TESTER snapshot + last tester-write timestamp. Behavior: tester writes pass through and refresh the cache; live writes within the 15-second tester-grace window are SHADOWED by the cached tester snapshot; live writes after the grace window pass through unchanged.
- **`bridge.py`** invokes the helper in `_tick()` after `enrich_mt5_for_stale_check()` so all in-bridge consumers (SCRIBE, HERALD, AEGIS) see the same tester view during testing.
- **`athena_api.py`** invokes the helper at all 5 `_read_json(MARKET_FILE)` call sites (`/api/live`, `/api/status`, `/api/lens`, `/api/positions`, `/api/scribe-status`).

### Why this is the right cut

- The `strategy_tester` flag is already written by FORGE EA at `ea/FORGE.mq5:2885-2886` whenever `MQLInfoInteger(MQL_TESTER) != 0`. Bridge has consumed it for the PROFIT_RATCHET guard since v2.7.50; this fix extends the gating to HERALD session/killzone pings + balance/positions overlay across all consumers.
- SCRIBE doesn't get tester-tagged session rows in the live DB. HERALD doesn't fire spurious Telegram messages. Athena dashboard balance stays on the live broker value. Live session transitions still fire normally.
- Per-process cache (not shared between bridge/athena) — each process builds its own live snapshot from its own observed live writes. No IPC needed.
- No EA recompile needed — `make reload` only.

### Verification (operator-observed)

- Pre-patch: `/api/live` returned `balance` alternating $10,596.59 ↔ $100,530.31 every 3-second poll
- Post-patch: `/api/live` returned `balance=$100,530.31` stable across 6 consecutive polls (18 sec)
- Bridge health probe: `MT5 data Age: 1s, balance=$100,530.31` (live, not tester)

## [FORGE 2.7.41] — 2026-05-12 (cooldown bypass on TP1 + trend; max_open bypass list)

### Added (`ea/FORGE.mq5`)

- **Regime-aware cooldown bypass** — optional re-fire when a per-setup cooldown would block, if last **TP1** in the same direction was recent, **M5 ADX** clears a floor, regime aligns, and anti-flicker refire gap passes. Config: `cooldown_bypass_on_tp_with_trend`, `cooldown_bypass_window_sec`, `cooldown_bypass_min_adx`, `cooldown_bypass_min_refire_sec`, `cooldown_bypass_setups` (safety JSON + env sync).
- **`max_open_same_direction_bypass_setups`** — comma list of `setup_type` values that may exceed same-direction open cap (e.g. retest / recovery).
- Tracks **`g_scalper_last_tp1_buy_time` / `g_scalper_last_tp1_sell_time`** on TP1 hit.

### Config / tooling

- **`config/scalper_config.defaults.json`**, **`scripts/sync_scalper_config_from_env.py`**, **`.env.example`** — new keys and `FORGE_*` mappings as implemented.
- **`#property version`** → **`2.111`**, **`FORGE_VERSION`** **`2.7.41`**, **`VERSION`** file.

---

## [FORGE 2.7.40] — 2026-05-12 (lot pipeline unification: `ScalperLot` → `ScalperLotFactor`)

### Context

The v2.7.39 lot pipeline had **two absolute sources of truth**: `lot_sizing.fixed_lot`
(JSON) AND `ScalperLot` (MT5 input — when > 0, overrode JSON directly with an absolute
value). Every other knob in `combined_lot_factor` was a multiplier; `ScalperLot` was the
only outlier — same room as 10 multipliers (`adx_lot_factor`, `bounce_lot_factor`,
`dump_lot_factor`, etc.), but it was a competing absolute.

Run 24 audit revealed the consequence: MT5 input `ScalperLot=0.08` overrode `fixed_lot=0.25`,
then the `combined_lot_factor` 0.125 floor compressed it: `0.08 × 0.125 = 0.01` lot/leg.
The whole portfolio sized 12.5× smaller than configured, silently. Operators wanting
half-sizing or double-sizing had to edit `fixed_lot` directly and redeploy.

Per the design principle "one absolute base, everything else is a factor", and per the new
§4.9 scope-precision rule in `FORGE_NAMING_CONVENTIONS.md`, the MT5 input is renamed and
re-semanticized as a multiplier.

### Change

| File | Change |
|---|---|
| `ea/FORGE.mq5:110` | Input `ScalperLot=0.0` (absolute) → `ScalperLotFactor=1.0` (multiplier on `fixed_lot`). |
| `ea/FORGE.mq5:124` | Comment on `NativeScalperInputsOverrideLotSizing` updated — toggle now controls leg COUNT only. |
| `ea/FORGE.mq5:~685` | `ScalperConfig` struct gains `double scalper_lot_factor` (env-side mirror). |
| `ea/FORGE.mq5:~3122` | Seed simplified: `g_sc.lot_fixed = 0.02` (decoupled from `ScalperLot`). `scalper_lot_factor = 1.0` seeded. |
| `ea/FORGE.mq5:~3225` | Removed: `if(ScalperLot > 0.0) g_sc.lot_fixed = ScalperLot` — the absolute-override path. |
| `ea/FORGE.mq5:~3765` | New JSON parse: `lot_sizing.scalper_lot_factor` (range 0.05..10.0). |
| `ea/FORGE.mq5:~4128` | `FORGE lot sizing profile` log line shows `scalper_lot_factor_input`, `_env`, effective product. |
| `ea/FORGE.mq5:~8266` | `combined_lot_factor` chain grows 10 → 11 multipliers: `scalper_lot_factor_eff` at the top. `base_lot = g_sc.lot_fixed` always (single absolute source). MT5-input wins when != 1.0; env value wins when MT5 input stays at default 1.0. |
| `config/scalper_config.defaults.json` | `lot_sizing.scalper_lot_factor: 1.0` added. |
| `scripts/sync_scalper_config_from_env.py` | `FORGE_GLOBAL_SCALPER_LOT_FACTOR → (lot_sizing, scalper_lot_factor, float, 0.05, 10.0)` mapping added. |
| `.env.example` | New section "GLOBAL LOT SCALER (v2.7.40)" with usage scenarios (0.5/1.0/2.0/0.1). |
| `~/.../Documents/forge_tester.set` | `ScalperLot=0.0` → `ScalperLotFactor=1.0`. |
| `~/.../Profiles/Tester/FORGE.set` | `ScalperLot=0.08\|\|0.01\|\|0.001\|\|0.1\|\|N` → `ScalperLotFactor=1.0\|\|0.5\|\|0.1\|\|2.0\|\|N` (optimization range covers half→double). |
| `VERSION` | 2.7.39 → 2.7.40 (auto-stamps `#property version "2.110"` + `scalper_config.json "version"`). |

### Migration: rename = safe-default fallback (NO `LEGACY_ALIASES` needed)

MQL5 silently ignores unknown `.set` entries. Old `.set` files with `ScalperLot=0.08` no
longer load that line, so the new input `ScalperLotFactor` stays at its default `1.0` =
safe no-op. **No silent reinterpretation** of `0.08` as "8% multiplier". Operators must
explicitly set `ScalperLotFactor` in the new `.set` (or `FORGE_GLOBAL_SCALPER_LOT_FACTOR`
in `.env`) to opt in to non-default sizing.

### Effective lot scenarios

| `ScalperLotFactor` | `fixed_lot=0.25` → effective base | Use case |
|---:|:---:|---|
| **0.1** | 0.025 | Emergency halt-size (high-impact news) |
| **0.5** | 0.125 | Half-sizing / risk-off |
| **1.0** | 0.25  | Default no-op (full size) |
| **2.0** | 0.50  | Double-sizing / size-up validated day |

`fixed_lot` retains full authority as the absolute base — tune it via `FORGE_FIXED_LOT` in
`.env` for durable base changes. Use `ScalperLotFactor` for ad-hoc session-level scaling
without git/redeploy.

### Docs touched

- `docs/FORGE_LOT_SIZING_REFERENCE.md` — §0 pipeline summary rewritten; §1.1 adds `scalper_lot_factor` row; §6 explains 12.5× shrinkage; §7 Step 1 reflects auto-fix.
- `FORGE_REGIME_TAXONOMY.md` — new §10.5.1d ScalperLot→ScalperLotFactor unification; §12 changelog. Phase 2 batch 45 → 46.
- `.env.example` — new "GLOBAL LOT SCALER (v2.7.40)" section under FORGE_FIXED_LOT.

### Acceptance verified

- `make forge-compile`: clean → FORGE.ex5 built, `#property version "2.110"`, scalper_config.json `"version": "2.7.40"`, 66 env override syncs.
- New JSON key `lot_sizing.scalper_lot_factor: 1.0` confirmed in active config.
- Zero remaining `= ScalperLot[^a-zA-Z]` orphan references in `ea/FORGE.mq5` (grep clean).

---

## [FORGE 2.7.39] — 2026-05-12 (R:R bypass hotfix for v2.7.38 composites)

### Context
Codex v2.7.38 review surfaced 1 FAIL: the new setup types
**FRACTIONAL_SELL_IN_BULL** and **BULL_DAY_DIP_BUY** would never fire even
when their `FORGE_*_ENABLED` flags were set, because the `rr_too_low` gate
(`scalper_min_rr_ratio`, default floor 1.5) only bypassed `MOMENTUM_DUMP`
and `BB_PULLBACK_SCALP`. Both new composites have intrinsic single-TP1 /
no-TP2 scalp geometry per atlas §5.1 V3 and §5.3:
- FRACTIONAL_SELL_IN_BULL: SL 1.5×ATR / TP1 0.3×ATR → R:R = 0.20
- BULL_DAY_DIP_BUY: SL 1.0×ATR / TP1 0.65×ATR → R:R = 0.65

Both R:Rs are below the 1.5 floor, so the gate would always reject these
trades. Same rationale as the v2.7.31 MOMENTUM_DUMP bypass: trigger atoms
+ composite gates ARE the safety net, the geometry is intrinsically scalp.

### Change

| File | Change |
|---|---|
| `ea/FORGE.mq5:8055` | R:R bypass extended from 2 → 4 setup types via `_rr_bypass` boolean. |
| `VERSION` | 2.7.38 → 2.7.39 (auto-stamps `#property version "2.109"`). |

### Acceptance verified
- `make forge-compile`: clean → FORGE.ex5 built, `#property version "2.109"`
- Tests: 37/37 pass

### Side note
SYSTEM_VERSION stays 1.10.1 — codex's WARN was a false-positive (SYSTEM_VERSION
is a Python-only artefact, not referenced from `ea/FORGE.mq5`).

---

## [FORGE 2.7.38] — 2026-05-12 (Tier 1 Boolean Composite shipment)

### Context
Ships the 4 Tier 1 composites from `FORGE_COMPOSITE_ROADMAP.md` §4. Originally
scoped for v2.7.36 but bumped to v2.7.38 because v2.7.36 became the session/KZ
refactor and v2.7.37 the Layer-4 atom telemetry expansion. With the atom data
now in SIGNALS, the composites can be validated post-run from `forge_signals`
SELECTs without re-running tester.

**All 4 default-OFF.** Operator enables each independently via FORGE_*_ENABLED
env vars after Run 26 validates each composite against the v2.7.37 atom
telemetry.

### Composites shipped

| # | Composite | Type | Atlas spec | Env flag |
|---|---|---|---|---|
| 1 | **BLOCK_SELL_IN_CHOP** | Gate (3 SELL chains) | §5.4 | `FORGE_BLOCK_SELL_IN_CHOP_ENABLED` |
| 2 | **INTRADAY_REVERSAL_TO_SELL_V3** | Dual: gate BUY + amplify SELL lot | §5.7 + V3 OHLC | `FORGE_INTRADAY_REVERSAL_SELL_ENABLED` + `_LOT_MULT=2.0` |
| 3 | **FRACTIONAL_SELL_IN_BULL** | NEW setup_type | §5.3 | `FORGE_FRACTIONAL_SELL_IN_BULL_ENABLED` + 3 geometry knobs |
| 4 | **BULL_DAY_DIP_BUY_V3** | NEW setup_type (16 atoms) | §5.1 V3 (case study §4c) | `FORGE_BULL_DAY_DIP_BUY_ENABLED` + 4 geometry knobs |

### Changes table

| # | File | Change | Why |
|---|------|--------|-----|
| 1 | `ea/FORGE.mq5` | 12 new `ScalperConfig` fields in a logical `composites` section (struct, InitScalperConfig defaults, ReadScalperConfig readers) | Hot-reload via scalper_config.json |
| 2 | `ea/FORGE.mq5` | 4 new helpers: `IsBlockSellInChopActive`, `IsIntradayReversalSellActive`, `IsFractionalSellInBullActive`, `IsBullDayDipBuyActive` | Each composite is a single function returning the boolean spec from atlas §5 |
| 3 | `ea/FORGE.mq5` | 4 new state globals: `g_last_chop_buy_exit_time`, `g_last_fractional_sell_in_bull_time`, `g_last_intraday_reversal_log_bar`, `g_last_chop_block_sell_log_bar` | Re-entry cooldown anchors + log throttles |
| 4 | `ea/FORGE.mq5` | BLOCK_SELL_IN_CHOP gate inserted at top of BB_BOUNCE SELL + BB_BREAKOUT SELL chains (MOMENTUM_DUMP SELL has dump_chop_block already) | Composite blocks chop-regime SELL entries |
| 5 | `ea/FORGE.mq5` | INTRADAY_REVERSAL_TO_SELL_V3 gate inserted at top of BB_BOUNCE BUY, BB_BREAKOUT BUY, MOMENTUM_DUMP BUY chains | Composite blocks ALL BUY when intraday pivot detected |
| 6 | `ea/FORGE.mq5` | Lot pipeline at `combined_lot_factor`: + `intraday_reversal_factor` (MOMENTUM_DUMP SELL amplifier) + `fractional_sell_factor` + `bull_day_dip_factor` | New triggers route through existing lot pipeline; INTRADAY_REVERSAL_TO_SELL_V3 doubles MOMENTUM_DUMP SELL lot when active |
| 7 | `ea/FORGE.mq5` | FRACTIONAL_SELL_IN_BULL new trigger block: direction=SELL, setup_type=FRACTIONAL_SELL_IN_BULL, single TP1, no TP2, fractional lot | NEW setup type (atlas §5.3) |
| 8 | `ea/FORGE.mq5` | BULL_DAY_DIP_BUY new trigger block: 16-atom composite check, single TP1 (0.65×ATR), no TP2, regime amplifier lot, 300s re-entry cooldown | NEW setup type (atlas §5.1 V3) |
| 9 | `ea/FORGE.mq5` | `#property version "2.107"` → `"2.108"` (auto-stamped) | Version bump |
| 10 | `config/scalper_config.defaults.json` | New `"composites"` JSON section with 12 keys, all default-OFF | Hot-reload baseline |
| 11 | `scripts/sync_scalper_config_from_env.py` | 12 new FORGE_* → composites.* mappings | Env-driven overrides |
| 12 | `.env.example` | New "BOOLEAN COMPOSITES — Tier 1 (FORGE v2.7.38)" section with all 12 vars (commented-out hints) | Discoverability |
| 13 | `config/gate_legend.json` | 2 new gate codes: `entry_quality_chop_block_sell`, `entry_quality_intraday_reversal_buy_block` | Decoded gate codes in monitoring + tests |
| 14 | `VERSION` / `SYSTEM_VERSION` | 2.7.37 → 2.7.38 / 1.10.0 → 1.10.1 | Version bumps |

### Atom→composite trace

| Composite | Atoms (referenced via g_eval_* globals + g_regime_* + h1_trend_strength) |
|---|---|
| BLOCK_SELL_IN_CHOP | `g_regime_label=="RANGE"` ∧ `h1_trend_strength>0.5` ∧ ¬FRACTIONAL_SELL_IN_BULL |
| INTRADAY_REVERSAL_TO_SELL_V3 | `h1_trend≥0.3` ∧ `m5_close<close[6]` ∧ `close[6]<close[12]` ∧ `m5_rsi≤40` ∧ (HID_BEAR ∨ REG_BEAR ∨ price<bb_mid) ∧ `price<vwap` ∧ `m5_lh_cascade==1` |
| FRACTIONAL_SELL_IN_BULL | `regime==TREND_BULL` ∧ `h1_trend≥1.0` ∧ `psar==ABOVE` ∧ `m5_rsi∈[60,75]` ∧ `m5_adx≥30` ∧ bar-over-bar bearish ∧ price near BB upper |
| BULL_DAY_DIP_BUY_V3 | `h1_trend≥0.5` ∧ ¬daily_bear_bias ∧ `m5_rsi∈[30,50]` ∧ `m5_adx∈[12,40]` ∧ BB dip-zone ∧ POC/Fib/VWAP gaps OK ∧ no bear divergence ∧ V3 OHLC (dist_high_atr<2 ∧ ¬m5_lh_cascade ∧ long_lower_wick) ∧ session∈{LONDON,NY} ∧ 300s cooldown |

### Acceptance verified
- `make scalper-env-sync` clean (66 env overrides — unchanged since v2.7.37 because composite enabled flags default-OFF)
- `make forge-compile` clean → FORGE.ex5 built, `#property version "2.108"`
- `python -c "import trading_session, scribe, bridge, athena_api"` clean
- `tests/api/test_forge_27x_gates.py + test_bridge_tester_journal_sync + test_scribe_forge_journal`: **37/37 pass**
- New gate codes `entry_quality_chop_block_sell` + `entry_quality_intraday_reversal_buy_block` present in gate_legend (dynamic-prefix test from v2.7.37 confirms no undecoded codes)
- All 4 composites callable from EA helpers; default-OFF so no live behaviour change

### Design decisions
- **Default-OFF for all 4**: operator enables each via env vars after validating with Run 26 SIGNALS rows. The v2.7.37 atom telemetry expansion (69 cols) means every composite's input is post-mortem-readable from `SELECT ... FROM forge_signals WHERE id=?` without re-running the tester.
- **BLOCK_SELL_IN_CHOP bypasses FRACTIONAL_SELL_IN_BULL**: helper guards `if(IsFractionalSellInBullActive(...)) return false;` — the rare overbought-counter SELL is the intentional counter-regime probe, not chop-block.
- **INTRADAY_REVERSAL_TO_SELL_V3 lot amplifier scoped to MOMENTUM_DUMP SELL only**: dump SELLs are regime-aligned with the reversal direction; amplifying generic SELL setups (BB_BREAKOUT, BB_BOUNCE) wasn't validated in atlas §5.7.
- **BULL_DAY_DIP_BUY re-entry cooldown anchor set at ENTRY (not exit)**: spec says "exit time" but TP1 fires within minutes (0.65×ATR ≈ 40 pips on gold) so entry-anchored 300s effectively starts post-exit. Refinement to true exit-time hook deferred to v2.7.39 if data shows cooldown drift.
- **INTRADAY_REVERSAL gate uses else-if chain pattern (not `continue`)**: MOMENTUM_DUMP BUY trigger block is conditional, not a loop — `continue` was rejected by compiler. Switched to else-if so the cascade naturally skips downstream gates AND entry assignment.

### Open items (deferred to v2.7.39)
1. Tier 2 composites: NO_TREND_DAY, CHOP_LADDER_BUY_GRID, TREND_CONTINUATION_BUY (per roadmap §5)
2. BULL_DAY_DIP_BUY true-exit-time cooldown hook in `ManageOpenGroups` TP1-close branch
3. Composite-firing rate measurement in forge-monitor dashboard

---

## [FORGE 2.7.37] — 2026-05-12 (Layer-4 atom telemetry — closes Decision Stack §6 gap)

### Context
Decision Stack Inventory (`docs/FORGE_DECISION_STACK_INVENTORY.md`) §6 made
the spec-vs-implementation gap concrete: **Layer-4 atoms reference indicators
that aren't journaled**. The H1 DI gate, daily bias gate, M30 trend gate, H4
RSI/ADX gates, and M5 cascade composites all consume indicators that exist
live but aren't in SIGNALS — post-mortems could see WHICH gate fired but not
the indicator value that drove it.

This release adds **69 new SIGNALS columns** sourced from
`g_eval_*` globals populated once per tick by a new `ForgeEvalAtoms()`
helper at the top of `CheckScalperEntry`. Every SKIP/TAKEN INSERT carries
the full multi-TF + OHLC + bar-quality context. **Zero new computation
cost** — the values were already being computed for gate evaluation; we
were just throwing them away after the gate ran.

### Tier A (13 cols — yesterday's Logging Extension Design)
`h4_trend`, `m15_trend`, `h1_di_balance`, `day_open`, `day_high`, `day_low`,
`m5_open_1`, `m5_high_1`, `m5_low_1`, `m5_close_1`, `m5_lh_cascade`,
`m5_hl_cascade`, `m5_body_pct`

### Tier B (11 atom-driven additions from inventory §6)
`h1_di_plus`, `h1_di_minus`, `h4_rsi`, `h4_adx`, `m30_trend`, `d1_open`,
`d1_close`, `h1_atr`, `h4_atr`, `m15_atr`, `m1_atr`

### Group 3 (45 cols — full broker-available inventory)
- **Indicator components**: `h1_rsi`, `h1_adx`, `h1_bb_{u,m,l}`, `h4_bb_{u,m,l}`, `m15_rsi`, `m15_ema{20,50}`, `m30_{rsi,adx,atr,ema20,ema50}`, `m1_ema{20,50}`
- **Per-TF OHLC bar 0**: M5 (`m5_*_0`), M15 (`m15_*`), M30 (`m30_*`), H1 (`h1_*`), H4 (`h4_*`)
- **Bar-quality flags** (INTEGER 0/1): `m5_inside_bar`, `m5_outside_bar`, `m5_doji`, `m5_strong_bar`, `long_lower_wick`, `long_upper_wick`, `m5_range_expanding`

### Changes table

| # | File | Change | Why |
|---|------|--------|-----|
| 1 | `ea/FORGE.mq5` | 69 new globals `g_eval_*` + `ForgeEvalAtoms()` helper (~120 LOC) | Single point of computation per tick; idempotent via `g_eval_last_tick` guard |
| 2 | `ea/FORGE.mq5` | `ForgeEvalAtoms()` call at top of `CheckScalperEntry` | Ensures globals are populated before any `JournalRecordSignal` call |
| 3 | `ea/FORGE.mq5` | SIGNALS `CREATE TABLE` extended + 69 additive `ALTER TABLE` migrations | Schema parity for fresh + existing DBs |
| 4 | `ea/FORGE.mq5` | `JournalRecordSignal` INSERT SQL adds 69 columns + value lines | Single function update — no per-call-site changes needed (atoms flow via globals) |
| 5 | `ea/FORGE.mq5` | Indexes on `h1_di_balance`, `(m5_lh_cascade, m5_hl_cascade)`, `m5_inside_bar` | Query performance for cascade/inside-bar composites |
| 6 | `ea/FORGE.mq5` | `#property version "2.106"` → `"2.107"` (auto-stamped from VERSION) | Version bump |
| 7 | `python/scribe.py` | 69 columns in declarative + in-init `forge_signals` CREATE | Schema parity |
| 8 | `python/scribe.py` | 69 additive `ALTER TABLE forge_signals ADD COLUMN ...` migrations | Existing scribe DBs upgrade cleanly |
| 9 | `python/scribe.py` | `sync_forge_journal`: `has_v37` + `has_v37g3` detection paths in SELECT/INSERT | Forward-compat: old journal DBs sync as NULL for missing cols |
| 10 | `VERSION` / `SYSTEM_VERSION` | 2.7.36 → 2.7.37 / 1.9.9 → 1.10.0 | Version bumps |

### Acceptance verified
- `make scalper-env-sync` clean (66 env overrides, version stamped 2.7.37)
- `make forge-compile` clean → FORGE.ex5 built (388 KB, +24 KB vs 2.7.36)
- `python -c "import trading_session, scribe, bridge, athena_api"` clean
- Fresh `forge_signals` DB created with **107 total columns** (37 legacy + 24 v37 Tier A+B + 45 v37 Group 3 + 1 killzone = 107)
- `tests/api/test_forge_27x_gates.py`: 28/28 pass (no dead env vars)
- `tests/services/test_scribe_forge_journal.py`: 4/4 pass (sync tuple signature + multi-run dedup)
- `tests/api/test_bridge_tester_journal_sync.py`: 4/4 pass (tuple-mock signatures match production)

### Atom→column trace (closes inventory §6 gap)
| Atom from FORGE.mq5 Layer 4 | Composite that uses it | SKIP gate code | New column |
|---|---|---|---|
| `h1_di_plus < h1_di_minus` | BB_BREAKOUT_BUY, BB_BREAKOUT_SELL | `entry_quality_h1_di_{buy,sell}` | `h1_di_plus`, `h1_di_minus`, `h1_di_balance` |
| `h4_rsi_v` in band | BB_BREAKOUT_{BUY,SELL} | `entry_quality_h4_rsi_{buy,sell}_blocked` | `h4_rsi` |
| `h4_adx_v` in band | BB_BREAKOUT_{BUY,SELL} | `entry_quality_h4_adx_{buy,sell}_blocked` | `h4_adx` |
| `m30_trend_strength <= 0` | BB_BREAKOUT_SELL | `entry_quality_m30_not_bearish` | `m30_trend` |
| `d1_open > d1_close` (bear day) | MOMENTUM_DUMP_SELL | `dump_d1_bias_block` | `d1_open`, `d1_close` |
| `m5_lh_cascade == 1` | INTRADAY_REVERSAL_TO_SELL_V3 | (composite validation) | `m5_lh_cascade` |
| `m5_body_pct >= body_pct_min` | (pre-trigger entry quality) | `entry_quality_body` | `m5_body_pct` |

### Design decisions
- **Globals over signature expansion**: Initially considered adding 69 optional params to `JournalRecordSignal` (per Logging Extension Design §4). Switched to `g_eval_*` globals because:
  1. Avoids touching 52 call sites
  2. The atoms are semantically "this tick's context" — global state is correct
  3. `ForgeEvalAtoms()` runs once per tick, called automatically at entry-eval start
  4. Add new columns in future without touching call sites at all — just extend the helper
- **`g_eval_last_tick` guard**: prevents double-evaluation if `CheckScalperEntry` is called multiple times in a tick. Atoms cached for the entire tick.
- **`has_v37` / `has_v37g3` all-or-nothing detection**: scribe's `sync_forge_journal` treats each tier as a unit. If the source journal DB is pre-v37 (missing any col), all v37 cols sync as NULL. Forward-compatible for old journal DBs being synced after MT5 EA upgrade.
- **All atoms default to 0/NULL on first appearance**: legacy SIGNALS rows from v2.7.36 and earlier keep working — new columns are NULL.

---

## [FORGE 2.7.36] — 2026-05-12 (Cross-stack session/time/killzone refactor)

### Context
Implements `docs/prompts/FIX_FORGE_TIME_ISSUES.md` v4. Session detection moves
from hour-only UTC ranges to minute precision with optional NY anchoring
(DST-aware via manual broker GMT offsets — Approach B, works identically in
live and Strategy Tester because `TimeGMT()` is unreliable in tester per
MQL5 docs). Adds ICT killzone layer on top of the existing 3-label session
system: per-tick label computed in both MQL5 (EA) and Python (BRIDGE/ATHENA).
Defaults preserve legacy behaviour (`*_min=-1`, `sessions_ny_anchored=0`,
`killzones_enabled=0`).

### Tier 0 hotfix (ships first)
- `config/scalper_config.defaults.json`: `tester_allowed_sessions` token
  fixed `"LONDON,NEW_YORK"` → `"LONDON,NY"`. `ScalperTesterSessionOK` labels
  the NY window as `"NY"` after `StringToUpper`, so `NEW_YORK` token silently
  rejected every NY entry in tester. Defensive alias `NEW_YORK → NY` (and
  `ASIA → ASIAN`) added in `ScalperTesterSessionOK` so future operators
  don't hit the same trap.

### Changes table

| # | File | Change | Why |
|---|------|--------|-----|
| 1 | `ea/FORGE.mq5` | New `ScalperConfig` Session fields: `london/ny/asia_{start,end}_min`, `sessions_ny_anchored`, `broker_gmt_offset_winter/summer`, `kz_*_min` (4 KZ windows), `killzones_enabled`, `killzones_gate_entries` | Minute-precision windows; NY anchoring; ICT killzones |
| 2 | `ea/FORGE.mq5` | New helpers: `LastSundayOfMonth`, `FirstSundayOfMonth`, `IsEU_DST`, `IsUS_DST`, `BrokerToNY`, `GetNYTimeNow`, `GetSessionAnchorTime`, `MinuteInWindow`, `GetEffective*Window`, `ComputeCurrentSessionLabel`, `ComputeCurrentKillzoneLabel`, `ForgeBrokerGMTOffsetSec` | Approach B time conversion; works in tester (where `TimeGMT()` ≡ broker server time) |
| 3 | `ea/FORGE.mq5` | `ScalperSessionOK`, `ScalperTesterSessionOK`, `ResetScalperSessionStateIfNeeded` rewritten to use `ComputeCurrentSessionLabel` | Single source of truth for session label; supports both UTC and NY anchor |
| 4 | `ea/FORGE.mq5` | `JournalRecordSignal` writes `session = ComputeCurrentSessionLabel()` + new `killzone` column | Replaces hard-coded TimeGMT-hour-derived session string |
| 5 | `ea/FORGE.mq5` | `WriteMarketData` adds `forge_session_state{label,killzone,anchor_mode,...}` block; `WriteBrokerInfo` adds `gmt_offset_sec`, `is_us_dst`, `is_eu_dst`, `broker_gmt_offset_winter/summer` | Visibility of session/KZ state in JSON contracts |
| 6 | `ea/FORGE.mq5` | SIGNALS table: `killzone TEXT DEFAULT ''` column in CREATE + additive ALTER + `idx_sig_killzone` index | Persistent KZ trail in journal DB |
| 7 | `ea/FORGE.mq5` | `OnInit` adds `FORGE TIME CHECK` diagnostic prints (TimeCurrent vs TimeGMT vs TimeTradeServer vs BrokerToNY) | Operator verification of broker offset before shipping KZ gating |
| 8 | `ea/FORGE.mq5` | Throttle bug fixes: `g_scalper_last_dircool_log_bar`, `g_scalper_last_opengroups_log_bar`, `g_scalper_last_sesscap_log_bar` added; `ScalperDirectionCooldownOK`, `open_groups` gate, `session_trade_cap` gate now throttle once per M5 bar | Prior `ScalperDirectionCooldownOK` used the wrong global (`g_scalper_last_sesswarn_log_bar`) and never updated it; `open_groups`/`session_trade_cap` had no throttle at all → log spam every tick when at cap |
| 9 | `ea/FORGE.mq5` | `#property version "2.105"` → `"2.106"` (auto-stamped from VERSION 2.7.35→2.7.36) | Version bump |
| 10 | `python/trading_session.py` | New `_KZ_DEFAULTS` + `_minute_in_window` + `_kz_window` + `get_current_killzone_utc` + `session_clock_summary` KZ block | zoneinfo-based KZ (OS-DST-aware — no broker offset needed Python-side) |
| 11 | `python/bridge.py` | New `_killzone()` helper, `_current_killzone` / `_killzone_start_ts` attrs, tick-loop KZ transition detection, `_on_killzone_change` method (logs SCRIBE `KILLZONE_CHANGE` event, optional Herald ping via `HERALD_KILLZONE_ALERTS`), `_write_status` adds `killzone` + `killzone_start_ts` | Persists last KZ; lighter than session change (no SCRIBE row open/close) |
| 12 | `python/scribe.py` | `forge_signals.killzone TEXT` in declarative + in-init CREATE + additive ALTER + idx; `sync_forge_journal` SELECT/INSERT extended with `has_killzone` detection | Persists EA-emitted KZ label into ATHENA's `forge_signals` |
| 13 | `python/athena_api.py` | `/api/live` and `/api/health` responses add `killzone`, `killzone_utc`, `killzone_start_ts` | Dashboard + downstream consumers |
| 14 | `dashboard/app.js` | Header session span now shows KZ badge (amber) when `D.killzone_utc \|\| D.killzone` set; default `liveData` shape extended with `session_utc/killzone/killzone_utc` | UI visibility |
| 15 | `config/scalper_config.defaults.json` | `session_filter` extended with all new keys; `london_end_utc 20→12` + `ny_start_utc 7→12` to **de-overlap** windows | Prior legacy: both London and NY covered 07-20 UTC, so the `if/else-if` order made NY label unreachable in production. New: London 7-12 UTC (morning EU), NY 12-20 UTC (afternoon US). Call-out in release notes. |
| 16 | `scripts/sync_scalper_config_from_env.py` | MAPPING entries for `FORGE_SESSIONS_NY_ANCHORED`, `FORGE_BROKER_GMT_OFFSET_{WINTER,SUMMER}`, `FORGE_{LONDON,NY,ASIA}_{START,END}_MIN` (lower bound `None` so `-1` sentinel passes), `FORGE_KILLZONES_{ENABLED,GATE_ENTRIES}`, `FORGE_KZ_*_MIN` (4 KZ pairs) | Every new env var wired end-to-end per `feedback_no_dead_env_vars` memory rule |
| 17 | `.env.example` | New `# ── SESSION MINUTE-PRECISION + NY ANCHOR + KILLZONES` block documents every new `FORGE_*` var | Cheat sheet completeness |
| 18 | `schemas/files/status.schema.json` | Adds `killzone`, `killzone_start_ts` | Status contract |
| 19 | `schemas/files/market_data.schema.json` | Adds `forge_session_state` object (not nested `session` — avoids collision with existing top-level `session: string`) | Market data contract |
| 20 | `schemas/openapi.yaml` | `LiveResponse` + `HealthResponse` + `ModeReadResponse` extended with killzone fields | OpenAPI contract consistency |
| 21 | `VERSION` / `SYSTEM_VERSION` | 2.7.35 → 2.7.36 / 1.9.8 → 1.9.9 | Version bumps |
| 22 | `tests/services/test_scribe_forge_journal.py` | Updated stale tests that compared `sync_forge_journal(...) == 1` (returns `(processed, inserted)` tuple) | Test signature drift from earlier sync refactor — surfaced incidentally |

### Acceptance verified
- `make scalper-env-sync` clean (66 env overrides, killzone vars unset → defaults applied, version stamped 2.7.36)
- `make forge-compile` clean → FORGE.ex5 built
- `python -c "import trading_session, scribe, bridge, athena_api"` clean
- `tests/api/test_forge_27x_gates.py` 28/28 pass (no dead `FORGE_*` env vars)
- `get_current_killzone_utc()` returns `''` with `KILLZONES_ENABLED=0`, `'LONDON_CLOSE_KZ'` at runtime (10:00–12:00 NY) with default config
- Fresh `forge_signals` DB created with `killzone` column

### Breaking behavioural change (documented per acceptance #8)
Default London/NY UTC windows **de-overlapped** from prior degenerate
`07–20 UTC` for both → London `07–12`, NY `12–20`. Sessions previously
mislabeled `LONDON` during 12–20 UTC will now correctly read `NY`.
`tester_session_filter` with `LONDON,NY` continues to admit both. To restore
the legacy single-window behaviour set `FORGE_LONDON_END_UTC=20` and
`FORGE_NY_START_UTC=7`.

### What NOT enabled by default
- `sessions_ny_anchored=0` — session label still in UTC by default. Set
  `FORGE_SESSIONS_NY_ANCHORED=1` to switch.
- `killzones_enabled=0` — KZ label always empty (no EA effect; no journal
  write). Set `FORGE_KILLZONES_ENABLED=1` to start tracking.
- `killzones_gate_entries=0` — even with KZ enabled, EA does not gate
  entries by killzone. `FORGE_KILLZONES_GATE_ENTRIES=1` enables gating
  (use with caution — silently halves trading hours).
- `HERALD_KILLZONE_ALERTS=0` — no Telegram pings on KZ transition.

---

## [FORGE 2.7.11-run10-prep] — 2026-05-10 (Run 9 post-mortem fixes)

### Context
Run 9 analysis revealed: cascade losses from SL-hunt pattern, TP too far on continuation legs,
BB_BOUNCE in trending market, and 53% of SIGNALS had RSI=0/ADX=0 making gate precision
analysis impossible. All fixes below derived from objective quant analysis of price movement
around every loss (not indicator-only reasoning).

### Changes table

| # | File | Change | Why |
|---|------|--------|-----|
| 1 | `ea/FORGE.mq5` | `JournalImportTrades`: magic range `+9999 → +29999` | Cascade/limit orders (magic +20000–+20004) were silently dropped from TRADES. Run 7 had 0 losses recorded; actual losses were -$38.71. |
| 2 | `ea/FORGE.mq5` | `bounce_lot_factor`: new struct field + default(1.0) + JSON parse + lot calc | BB_BOUNCE G5005 lost -$175 at full lot. With 0.25 factor → -$44. Mean-reversion needs smaller position than breakout. |
| 3 | `ea/FORGE.mq5` | `CheckEntryQuality`: added `rsi`, `adx` to signature; replaced hardcoded `0,0` in all 5 `JournalRecordSignal` calls | All direction/body/ATR gate SKIPs logged RSI=0/ADX=0 — 53% of 20,924 signals unanalysable. Gate precision audit impossible. Fix: pipe m5_rsi/m5_adx through from call site. |
| 4 | `ea/FORGE.mq5` | Added block comments + CHANGELOG refs to `CheckEntryQuality` | Code documentation standard: every function gets PURPOSE, EVALUATION ORDER, PARAMETERS, CHANGELOG. Extended detail in CHANGELOG.md. |
| 5 | `scripts/sync_scalper_config_from_env.py` | Added 5 dead-variable mappings: `ADX_MIN_SELL`, `ADX_MIN_SELL_LOOKBACK_BARS`, `REQUIRE_H1_DI_BUY`, `COUNTER_BUY_ADX_THRESHOLD`, `MAX_REENTRY_ATR_EXT` | These vars existed in .env since v2.7.6 but were never wired — EA used hard-coded defaults. `REQUIRE_H1_DI_BUY=1` and `MAX_REENTRY_ATR_EXT=1.25` were silently ignored. |
| 6 | `scripts/sync_scalper_config_from_env.py` | Added `FORGE_BOUNCE_LOT_FACTOR`, `FORGE_BOUNCE_ADX_MAX`, `FORGE_SESSION_NY_SELL_CUTOFF_UTC`, `FORGE_SESSION_LONDON_SELL_CUTOFF_UTC` mappings | `FORGE_BOUNCE_ADX_MAX=40` was wired but mapped to wrong default; session cutoff vars were unmapped entirely. |
| 7 | `config/scalper_config.defaults.json` | Added `bounce_lot_factor: 1.0` and 5 new bb_breakout keys | Defaults must exist before sync overrides can be applied. |
| 8 | `.env` | `FORGE_SELL_STOP_CONT_EXPIRY_BARS`: 8 → 2 | 8 bars = 40 min — not scalping. G5008 cascade held 14h and gave back +21 pts of profit. Scalpers close in minutes. |
| 9 | `.env` | `FORGE_SESSION_NY_SELL_CUTOFF_UTC`: 17 → 20 → 18 | Extended to 20 caused G5007 loss at 17:10 UTC (-$259). 18 UTC (2PM EDT) is the correct balance. |
| 10 | `.env` | `FORGE_BREAKOUT_MAX_REENTRY_ATR_EXT`: 1.25 → 2.0 | At 1.25, May 1 rally first candle (RSI 74.9) was blocked by `entry_quality_atr_ext`. 2.0 allows re-entry up to 2×ATR from first entry. |
| 11 | `.env` | `FORGE_BOUNCE_ADX_MAX`: 40 → 35 | G5005 BB_BOUNCE had ADX=33.2 — passed at 40. Lowered to 35 (still passes 33.2, but closer). adx_max=30 needed to fully block G5005-class setups. |
| 12 | `.env` | `FORGE_BOUNCE_LOT_FACTOR=0.25` | New parameter: BB_BOUNCE position at 25% of base lot. |

| 14 | ea/FORGE.mq5 + sync | sell_stop_cont_tp_atr_mult: cascade SELL STOP TP at entry−ATR×0.8. Was tp=0 (naked). G5003/G5008 missed $64/$170 profit from naked cascades. |
| 15 | ea/FORGE.mq5 | PlaceOpenGroupLeg: local _log_rsi/_log_adx reads; 17 open_group_* SKIP logs now have real RSI/ADX instead of 0,0. |
| 16 | ea/FORGE.mq5 | TP3 live staging: TradeGroup.tp2_hit flag + tp3 computed at group registration (rr_entry_ref−m5_atr×tp3_atr_mult). ManageOpenGroups TP3 pass: when TP2 reached, promotes runners to TP3. TP4 intentionally omitted — scalpers take TP3 and re-enter. |

### Known open items (EA code — needs recompile + next iteration)
- `sell_stop_cont_tp=0` confirmed at line ~6122: SELL STOP CONT has no TP assigned. G5003 (+8pts) and G5008 (+21pts) were deeply profitable cascades that reversed because no TP was set. Fix needed: `sell_stop_cont_tp_atr_mult` config + EA logic.
- TP3/TP4 (`tp3_atr_mult=2.5`, `tp4_atr_mult=4.0`) only used in R:R gate math — never assigned as live position targets. Runners after TP2 rely only on fast-lock SL ratchet.
- `OpenGroup()` logs all `open_group_*` gates with RSI=0/ADX=0 — same pattern as CheckEntryQuality. Fix: pass rsi/adx into OpenGroup() signature.
- Pre-indicator gates (session_off, spread, warmup) also log RSI=0 — these are genuinely pre-computation so zeros are correct, but should be flagged in monitoring as "indicator-unavailable" rather than "RSI=0".

---

## [FORGE 2.7.10-day2] — 2026-05-09 (SELL STOP continuation ladder — TP1 arming)

### Changes table

| # | Location | Change | Notes |
|---|----------|--------|-------|
| 1 | `TradeGroup` struct | Added `crash_low` + `entry_atr` fields | Set at entry, consumed by `ArmPostTP1Ladder()` |
| 2 | `CheckScalperEntry()` group registration | Store `crash_low = bid` (SELL) / `ask` (BUY) and `entry_atr = m5_atr` | BRIDGE groups get current bid/ask; entry_atr=0 disables post-TP1 arming for BRIDGE |
| 3 | `ExecuteOpenGroup()` (BRIDGE path) | Init `crash_low` from current bid/ask; `entry_atr = 0` (disables arming) | Keeps struct clean; BRIDGE doesn't have ATR at registration time |
| 4 | New `ArmPostTP1Ladder(gi)` function | Places SELL STOP in slot [2] at `crash_low − ATR × 0.40` | RSI guard: skips if M5 RSI ≤ sell_stop_cont_min_rsi (exhausted); SL at crash_low + ATR × mult |
| 5 | `ManageOpenGroups()` after `tp1_hit = true` | Call `ArmPostTP1Ladder(gi)` | Fires exactly once per group; no comment parsing needed |
| 6 | Expiry loop (OnTimer) | Auto-clear filled slots: `!OrderSelect` before expiry → `active = false` | Prevents slot [2] from being stuck active after SELL STOP fills |
| 7 | `ScalperConfig` struct | Added `sell_stop_cont_enabled/atr_mult/lot_factor/expiry_bars/min_rsi` | Defaults: off, 0.40, 0.25, 8 bars, RSI 25.0 |
| 8 | Config + sync + env | Added `sell_stop_cont_*` to all three (JSON, sync script, .env) | Disabled in .env; enabled by `FORGE_SELL_STOP_CONT_ENABLED=1` |

### Key design decisions

- **crash_low in `TradeGroup`, not `SellLimitEntry`**: Group struct survives TP1 event; sell limit stack is pending-order lifecycle only.
- **Arm from `ManageOpenGroups()`, not `OnTradeTransaction`**: Direct `gi` access, no comment parsing, no magic range concerns. Fires immediately when TP1 positions are closed via `PositionClose()`.
- **BRIDGE groups disabled**: `entry_atr = 0` at BRIDGE registration → `ArmPostTP1Ladder` skips (guard: `entry_atr <= 0`). BRIDGE doesn't have M5 ATR available at the time `ExecuteOpenGroup` fires.
- **Slot [2] auto-clear on fill**: `OrderSelect(ticket)` returning false before expiry = filled externally → slot cleared. Previously the expiry loop could hold a filled slot active until its expiry timestamp.
- **SL symmetric**: SELL STOP SL = `crash_low + ATR × sell_stop_cont_atr_mult` (mirrors placement offset). At default 0.40, risk = 0.80 ATR.

### How to enable for testing
```
FORGE_SELL_STOP_CONT_ENABLED=1
```
Then `make scalper-env-sync && make forge-compile`. Reload EA in MT5.

### Day 3 stub
`ArmPostTP1Ladder()` has a commented `// Day 3 stub` block at the bottom for BUY LIMIT recovery (slot [3]). Implement Day 3 when SELL STOP validation is complete.

---

## [FORGE 2.7.10-h4] — 2026-05-09 (H4 RSI/BB/ADX supplemental gates + indicators export)

### Changes table

| # | Location | Change | Notes |
|---|----------|--------|-------|
| 1 | `ea/FORGE.mq5` globals | Added `g_h4_rsi`, `g_h4_bb`, `g_h4_adx` handles | Initialized in `EnsureIndicators()`, released in `OnDeinit()` |
| 2 | `ea/FORGE.mq5` `WriteMarketData` | Extended `indicators_h4` JSON block with `rsi_14`, `bb_upper`, `bb_lower`, `adx_14` | Always exported; BRIDGE/LENS can use for structural context |
| 3 | `ea/FORGE.mq5` `CheckScalperEntry` | Added `h4_rsi_v` and `h4_adx_v` reads in entry logic scope | Available for both SELL and BUY gate checks |
| 4 | `ea/FORGE.mq5` SELL gate | Added `h4_rsi_sell_ok` gate (blocks when H4 RSI ≥ 60 — Cardwell Bear Resistance on H4) | Disabled by default; `h4_rsi_gate_enabled=0` in defaults |
| 5 | `ea/FORGE.mq5` SELL gate | Added `h4_adx_sell_ok` gate (blocks when H4 ADX < 20 — H4 structurally ranging) | Disabled by default; `h4_adx_gate_enabled=0` in defaults |
| 6 | `ea/FORGE.mq5` BUY gate | Added `h4_rsi_buy_ok` gate (blocks when H4 RSI ≤ 40 — Cardwell Bull Support on H4) | Same flag as SELL; symmetric |
| 7 | `ea/FORGE.mq5` BUY gate | Added `h4_adx_buy_ok` gate (blocks when H4 ADX < 20) | Same flag as SELL; separate min threshold |
| 8 | `ScalperConfig` struct | Added `h4_rsi_gate_enabled`, `h4_rsi_sell_max`, `h4_rsi_buy_min`, `h4_adx_gate_enabled`, `h4_adx_min_sell`, `h4_adx_min_buy` | Defaults: gates off, RSI 60/40, ADX 20 |
| 9 | `config/scalper_config.json` | Added all 6 H4 gate keys + `sell_limit_l2_*` keys; gates enabled for testing | Revert by setting `h4_rsi_gate_enabled`:0 and `h4_adx_gate_enabled`:0 |
| 10 | `config/scalper_config.defaults.json` | Added same keys with gates disabled (production defaults) | Prevents accidental enablement in clean deploys |
| 11 | `scripts/sync_scalper_config_from_env.py` | Added `FORGE_H4_RSI_GATE_ENABLED`, `FORGE_H4_RSI_SELL_MAX`, `FORGE_H4_RSI_BUY_MIN`, `FORGE_H4_ADX_GATE_ENABLED`, `FORGE_H4_ADX_MIN_SELL`, `FORGE_H4_ADX_MIN_BUY` | Hot-reloadable via `make scalper-env-sync` |
| 12 | `.env` | Added H4 gate env vars with documentation + sell_limit_l2 vars | Enabled (=1) for testing run; set =0 to disable |

### Design rationale

H4 RSI identifies structural exhaustion zones that M5/H1 miss:
- **H4 RSI ≥ 60** (Cardwell Bear Resistance): price just spiked to a structurally significant HH level on H4. A BB_BREAKOUT SELL at this point is likely catching a reversal of the H4 spike, not a genuine crash. Gate blocks it.
- **H4 RSI ≤ 40** (Cardwell Bull Support): price is at LL on H4. A BB_BREAKOUT BUY here may be catching a falling knife before H4 turns. Gate blocks it.
- **H4 ADX < 20**: H4 is structurally ranging — no directional trend on the higher TF. Scalp entries lack multi-TF confirmation. Gate blocks until H4 trend is established.

Gates are additive to existing M5/H1 gates and placed after MACD/M30 checks. Journal gate reasons: `entry_quality_h4_rsi_sell_blocked`, `entry_quality_h4_rsi_buy_blocked`, `entry_quality_h4_adx_sell_blocked`, `entry_quality_h4_adx_buy_blocked`.

### How to disable (revert to 2.7.10 pre-H4 behaviour)

In `.env`:
```
FORGE_H4_RSI_GATE_ENABLED=0
FORGE_H4_ADX_GATE_ENABLED=0
```
Then `make scalper-env-sync && make forge-compile`.

---

## [System 1.9.9] — 2026-05-09 (ATHENA — Final UI/API review, 7 bugs fixed)

### Changes table

| # | Location | Bug | Fix | Status |
|---|----------|-----|-----|--------|
| 1 | `sentinel.py:191` | `"Nonemin"` — `next_in_min=None` rendered as `"Nonemin"` because `dict.get(key, default)` ignores default when key exists with null value | Explicit None check → `"—"` | ✅ fixed (takes effect on next bridge restart) |
| 2 | `athena_api.py` TV_KEYS | `tradingview.mode = "HYBRID"` — trading system mode leaking into TradingView indicators block | Removed `"mode"` from TV_KEYS | ✅ fixed |
| 3 | `athena_api.py` `/api/live` | `indicators_m5`, `indicators_m15`, `indicators_m30` in `market_data.json` but absent from API response | Added all three MTF blocks to response | ✅ fixed |
| 4 | `athena_api.py` self-heartbeat | ATHENA component showed April 6 timestamp — never updated its own heartbeat | Added `scribe.heartbeat("ATHENA")` on every `/api/live` poll | ✅ fixed |
| 5 | `dashboard/app.js` AUTO_SCALPER | `upperBB NO` always shown even when H1 BULL (wrong direction for BUY setup) | Direction-aware label: BULL → `lowerBB`, BEAR → `upperBB` | ✅ fixed |
| 6 | `SYSTEM_VERSION` | File said `1.7.2`, CHANGELOG at `1.9.8` | Updated to `1.9.8` | ✅ fixed (bridge version self-corrects on next restart) |
| 7 | `regime.py` / `autoscalper_condition_service.py` / `dashboard/app.js` | `STATE_N` posterior keys, SELL-only readiness, HMM ADX threshold 22, ret_1 direction noise | See [System 1.9.8] for full detail | ✅ fixed in prior commit |

### Deferred (need deeper investigation)

| Issue | Root cause | Notes |
|-------|-----------|-------|
| `lot_size: 0.0` in all closures | Bridge calls `log_position_closure(lot_size=0)` | Needs bridge.py close-path audit |
| `duration_seconds: null` | Duration not computed at close time | Same code path as lot_size |
| `session_pnl: +0.00` despite recent wins | AEGIS reads `trade_positions.close_time`; likely tester-session mapping mismatch | Needs session boundary + trade_positions audit |
| `version: 1.7.2` in header | Bridge reads SYSTEM_VERSION at import — will show 1.7.2 until restart | Self-corrects on next `make services-restart` |

### Fixed

- **`sentinel.py` "Nonemin" bug** — `report_component_status` note used `status.get('next_in_min','?')` which returns `None` (not `'?'`) when the key exists but the value is `None`. Result: "Next: None scheduled in Nonemin" in System Health panel. Fixed with explicit `None` check: `str(val) + 'min' if val is not None else '—'`.

- **`tradingview.mode` field removed** — `"mode"` was in `TV_KEYS`, causing `tradingview.mode = "HYBRID"` in every `/api/live` response. This is the trading system mode, unrelated to TradingView. Removed from TV_KEYS.

- **`indicators_m5 / m15 / m30` added to `/api/live`** — All three multi-timeframe indicator blocks (RSI, EMA, ATR, BB, ADX, OsMA) were present in `market_data.json` but not passed through the API. Autoscalper condition service read them directly from file; API consumers had no access.

- **ATHENA self-heartbeat** — `api/live` now calls `scribe.heartbeat("ATHENA")` on every request. ATHENA component in System Health was frozen at the April 6 startup swagger-verify timestamp.

- **Direction-aware BB label in AUTO_SCALPER panel** — `upperBB YES/NO` was hardcoded. When H1 is BULL the relevant check is `lowerBB` (price near lower band for BUY entry), not `upperBB`. Label and value now switch based on `h1_bias`.

- **`SYSTEM_VERSION` updated** — `1.7.2 → 1.9.8`. Bridge reads this at import so dashboard `version` field updates on next `make services-restart`.

---

## [System 2.0.3] — 2026-05-09 (FORGE 2.7.9 — M30 EMA bearish confirmation gate)

### Changes table

| # | Location | Change | Config | Status |
|---|----------|--------|--------|--------|
| 1 | `ea/FORGE.mq5` SELL gate chain | Add M30 EMA20 < EMA50 confirmation gate between OsMA Q2 and news tighten | `FORGE_BREAKOUT_REQUIRE_M30_BEAR_SELL=1` | ✅ compiled 2.7.9 |
| 2 | `ea/FORGE.mq5` config struct | New fields `breakout_require_m30_bear_sell`, `breakout_m30_bear_adx_min` | — | ✅ |
| 3 | `ea/FORGE.mq5` global | New `g_scalper_last_m30bear_log_bar` throttle to log once per M5 bar | — | ✅ |
| 4 | `config/scalper_config.defaults.json` | `require_m30_bear_sell: 1`, `m30_bear_adx_min: 25` | — | ✅ |
| 5 | `scripts/sync_scalper_config_from_env.py` | M30 gate keys added to MAPPING | — | ✅ |

### Gate execution order — SELL path (full, as of FORGE 2.7.9)

1. BB condition: `prev_close < BB_lower − buffer` + M5/M15/H1/H4 bear alignment
2. Cardwell Bear Resistance ceiling: `m5_rsi < rsi_sell_max (60)` ← 2.7.6
3. Session SELL cutoff: `hour < 17:00 UTC` ← 2.7.7
4. ADX extreme block: `m15_adx < 55` ← 2.7.7
5. ADX min SELL: `m5_adx ≥ 25` ← 2.7.3
6. H1+H4 crash bypass + RSI floor ← 2.7.6
7. ADX spike-from-flat (6-bar lookback) ← 2.7.4
8. RSI-declining gate (auto-off ADX ≥ 40) ← 2.7.4
9. OsMA Q2 gate: histogram negative AND falling ← 2.7.7c
10. **M30 EMA bearish confirmation: M30 EMA20 < EMA50 (when ADX ≥ 25)** ← **2.7.9**
11. News RSI tighten ← 2.7.6

### Design rationale

H1 EMA trend label lags — at recovery inflections, H1 may still show BEAR while M30 EMA has already crossed bullish. The M30 intermediate TF check sits between H1 (strategic bias) and M5 (entry signal), catching early-recovery entries before the trend reversal is fully confirmed. Gate uses existing `g_mtf[2].h_ma20` / `g_mtf[2].h_ma50` handles (already initialized in `EnsureMTFIndicators`) — zero new indicator handles.

Gate only activates when `m5_adx ≥ m30_bear_adx_min (25)` — in ranging conditions (ADX < 25), M30 EMA alignment is meaningless for short-term scalps and is bypassed.

Journal reason: `entry_quality_m30_not_bearish`

---

## [System 2.0.2] — 2026-05-09 (Comprehensive Python audit — 10 bugs across 6 files)

### Changes table

| # | File | Line | Sev | Bug | Fix | Status |
|---|------|------|-----|-----|-----|--------|
| 1 | `aegis.py` | 886 | HIGH | `_get_scale_factor` queried `trade_positions ORDER BY close_time DESC` — NULL close_times sort incorrectly, returning stale rows; wrong streak count → wrong lot sizing | Switch to `trade_closures ORDER BY timestamp DESC` | ✅ scale_factor now reads real recent closes; 3-win streak detected correctly |
| 2 | `aegis.py` | 625 | MEDIUM | `_get_session_pnl()` called twice (line 557 + 625) — second call can see a different DB state if a trade closes between calls | Annotated; session_pnl from line 557 reused at 625 | ✅ |
| 3 | `scribe.py` | 1693 | HIGH | `get_today_pnl` queried `trade_positions.close_time` (often NULL) → always returned $0 | Switch to `trade_closures WHERE timestamp LIKE '{today}%'` | ✅ |
| 4 | `autoscalper_condition_service.py` | 147 | HIGH | Loss cooldown queried `trade_positions.close_time` (NULL) → `last_loss_close_time` always None → cooldown gate permanently disabled after losses | Switch to `trade_closures WHERE pnl < 0 ORDER BY timestamp DESC` | ✅ |
| 5 | `bridge.py` | 1033 | HIGH | Indentation bug: `_known_pendings[t]` dict assignment was OUTSIDE the `if t not in self._known_pendings` guard — ran unconditionally, using stale `magic` from previous loop iteration for known tickets | Indented dict assignment inside the `if` block | ✅ |
| 6 | `bridge.py` | 2775 | LOW | `_now = time.time()` inside `_tick()` shadowed module-level `_now()` function — any future call to `_now()` within `_tick()` would get float not string | Renamed to `_journal_now` | ✅ |
| 7 | `bridge.py` | 3482 | MEDIUM | `_scalper_logic`: `adx > 20` raised `TypeError` when `lens_snap.adx` is `None` (MCP timeout) | Added `adx is not None and price is not None` guard | ✅ |
| 8 | `reconciler.py` | 176 | MEDIUM | PNL_MISMATCH check compared MT5 floating P&L against `trade_groups.total_pnl` — always 0 for open groups → mismatch fire on every live trading cycle | Removed the check (logically broken; position-count checks are sufficient) | ✅ |
| 9 | `reconciler.py` | 192 | MEDIUM | `forge_version >= FORGE_MIN_PENDING_VERSION` used string comparison — `"1.2.10" < "1.2.4"` lexicographically | Replaced with `_ver()` tuple comparison | ✅ |
| 10 | `sentinel.py` | 320 | MEDIUM | Year rollover: ForexFactory dates parsed with `now.year` — January events in late December appear 365 days in the past, breaking upcoming-event detection | After parse, if date is >7 days in the past, add 1 year | ✅ |

---

## [System 2.0.1] — 2026-05-09 (SCRIBE + ATHENA — Performance panel wired to trade_closures)

### Changes table

| # | Location | Bug | Root cause | Fix | Status |
|---|----------|-----|-----------|-----|--------|
| 1 | `scribe.py` `get_performance()` | Performance panel showed 164 trades, -$1,022 P&L — inconsistent with `closure_stats` (3,454 trades, -$2,427) | Queried `trade_positions WHERE close_time >= ? AND status='CLOSED'` — `close_time` only written when `close_trade_position()` is called, which some close paths skip | Changed to `FROM trade_closures WHERE timestamp >= ?` | ✅ total 164→3,454 · P&L -$1,022→-$2,427 (matches closure_stats) |
| 2 | `athena_api.py` `api_pnl_curve()` | P&L sparkline was sparse/stale — wrong cumulative | Same root cause: `FROM trade_positions WHERE close_time >= ?` | Changed to `FROM trade_closures WHERE timestamp >= ?` with `timestamp AS close_time` alias | ✅ curve now shows 3,454 points across full 7-day window |

### Wiring audit — Performance panel data sources

| UI element | API field | Source | Table | Status |
|------------|-----------|--------|-------|--------|
| Win Rate / Trades / Wins / Losses / Total P&L / Avg Pips | `performance` | `scribe.get_performance(days=7)` | `trade_closures` | ✅ fixed |
| SL Hits / TP Rate / Manual / Total P&L (7d) | `closure_stats` | `scribe.get_closure_stats(days=7)` | `trade_closures` | ✅ was already correct |
| Cumulative P&L sparkline | `/api/pnl_curve?days=N` | `api_pnl_curve()` | `trade_closures` | ✅ fixed |
| Recent closures list | `recent_closures` | `scribe.get_recent_closures()` | `trade_closures` | ✅ was already correct |
| Session P&L | `aegis.session_pnl` | `aegis._get_session_pnl()` | `trade_closures` | ✅ fixed in [2.0.0] |
| Regime performance (30d) | `regime.performance_30d` | `scribe.get_regime_performance(days=30)` | `trade_groups` JOIN `trade_positions` | Unchanged — regime labels on positions |

All six performance data sources now consistently read from `trade_closures`. `trade_positions` is retained for regime label joins only.

---

## [System 2.0.0] — 2026-05-09 (BRIDGE + AEGIS — lot_size, duration_seconds, session_pnl data fixes)

### Changes table

| # | Location | Bug | Root cause | Fix | Status |
|---|----------|-----|-----------|-----|--------|
| 1 | `bridge.py` `_seed_tracker_from_scribe` | `lot_size: 0.0` for all closures after bridge restart | SELECT query omitted `lot_size` column; hardcoded `0` on seed | Added `lot_size, timestamp` to SELECT; use `float(r.get("lot_size") or 0)` from SCRIBE | ✅ fixed (new closures only) |
| 2 | `bridge.py` dedup path (line ~1238) | `lot_size: 0.0` for existing-SCRIBE positions on restart | `lot_size` key missing entirely from `_known_positions` dict in dedup branch | Added `"lot_size": p.get("lots", 0)` to the dict | ✅ fixed |
| 3 | `bridge.py` both `log_trade_closure` call sites | `duration_seconds: null` always | `open_time` never cached in `_known_positions`; never computed at close | Cache `"open_time"` at all 4 `_known_positions` write paths; compute `(close_time - open_time).total_seconds()` at close; pass `duration_seconds` to both `log_trade_closure` calls | ✅ fixed (new closures only) |
| 4 | `aegis.py` `_get_session_pnl` | `session_pnl: +0.00` despite recent wins | Queried `trade_positions WHERE status='CLOSED' AND close_time >= ?` — `close_time` is only written when `close_trade_position()` is called, which some close paths skip; `trade_positions` had no rows since yesterday | Switch to `trade_closures WHERE timestamp >= ?` — always populated at close | ✅ verified: was $0.00, now $488.65 |

### Note on historical records

`lot_size` and `duration_seconds` remain `0.0` / `null` in closures recorded **before** this fix. New closures going forward will populate both fields. No migration needed — existing analytics that tolerate these nulls are unaffected.

### Fixed

- **`lot_size: 0.0` in all `trade_closures`** — Three-location fix in `bridge.py`. (1) `_seed_tracker_from_scribe`: the SELECT that re-hydrates `_known_positions` on restart omitted `lot_size`, so the field was hardcoded to `0` for all seeded positions. (2) Dedup path: when a position already has a SCRIBE row, the `_known_positions` dict was built without a `lot_size` key, so `snap.get("lot_size", 0)` returned `0` at close. (3) Normal new-position and fresh-position paths were already reading `p.get("lots", 0)` correctly. Also added `open_time: timestamp` from SCRIBE for seeded positions.

- **`duration_seconds: null` in all `trade_closures`** — `open_time` was never stored in `_known_positions`, so there was nothing to subtract from `close_time` at close. Fix: cache `"open_time": datetime.now(UTC).isoformat()` at all 4 positions write paths (seeded positions use `r.get("timestamp")` from SCRIBE). At close, compute `int((close_time - open_time).total_seconds())` with a try/except guard and pass `duration_seconds` to both `log_trade_closure` call sites.

- **`session_pnl: +0.00` despite recent wins** — `_get_session_pnl()` in `aegis.py` queried `trade_positions WHERE status='CLOSED' AND close_time >= session_start`. `close_time` on `trade_positions` is only updated by `close_trade_position()`, which some close paths bypass. `trade_positions` had no rows closed since yesterday. `trade_closures` is the correct canonical source — its `timestamp` is always set at insert time. Fix: `FROM trade_closures WHERE timestamp >= session_start`. Verified immediately: session P&L changed from $0.00 to $488.65.

---

## [System 1.9.8] — 2026-05-09 (ATHENA — Regime Engine + AUTO_SCALPER readiness overhaul)

### Fixed

- **AUTO_SCALPER `g47_g48_sell_pattern_match` SELL-only logic** — The readiness condition previously required `h1_bias == "BEAR"`, making AUTO_SCALPER permanently BLOCKED in any bull market regardless of how good BUY conditions were. Root cause: G47/G48 is a SELL-only pattern; no BUY counterpart existed. Fix: added symmetric BUY readiness (`h1_bias == "BULL"` + price near lower BB), unified under `pattern_ready`. Tag now shows `READY·SELL` or `READY·BUY` when triggered.

- **BB proximity `failed_checks` direction-aware** — Previously always reported `m15_not_near_upper_bb` even when H1 was BULL (where you'd want price near the LOWER BB for a BUY). Now: BEAR bias → `m15_not_near_upper_bb`, BULL bias → `m15_not_near_lower_bb`. Actionable failure reason instead of misleading one.

- **HMM ADX trend threshold 22 → 25** — `_build_hmm_state_labels` used `mean_adx >= 22.0` to classify HMM states as trending. Wilder's published threshold for confirmed trend is 25. States at ADX 22–25 are often still ranging — the old threshold was mislabeling RANGE states as TREND_BULL or TREND_BEAR, producing unreliable regime labels.

- **HMM direction from `ema_spread` not `ret_1`** — State direction was determined by `mean_ret` (mean 5-second price return). At 5s intervals this is extremely noisy — a state with ADX=35 could have `mean_ret≈0` from oscillation and get labeled RANGE instead of TREND. Fix: use `ema_spread` (EMA20−EMA50) as the primary direction signal, confirmed by `ret_1` (both must agree: `is_bull = ema_spread > 0 AND ret ≥ 0`). EMA spread is structurally stable across a state's lifetime.

- **Ambiguous strong-trend states → VOLATILE** — Previously, an HMM state with ADX≥25 but conflicting `ema_spread`/`ret_1` direction fell through to RANGE. It's more accurate to label these VOLATILE (strong momentum, unclear direction) than RANGE (calm market). Added explicit branch: `ADX≥25 and not (is_bull or is_bear) → VOLATILE`.

- **`STATE_N` posterior keys in regime panel** — Unlabeled HMM states appeared as `STATE_2 0%` in the dashboard posterior display. Fix: unlabeled states default to `"RANGE"` in the posterior dict; probability sums merge with legitimate RANGE states. Clean posterior, no raw HMM state indices shown to user.

- **TV MACD always `0.00000` in dashboard** — `lens.py` used `find_study("MACD", "Histogram")` which searched for `"macd"` as a substring in study names. TradingView returns the full name `"Moving Average Convergence Divergence"` — `"macd"` is not a substring of that string, so the lookup always returned 0. Fix: `find_study_by_fragments(["MACD", "convergence divergence"])` with `find_value_from_study(..., ["hist", "Histogram"])` covering both `"Histogram"` and `"Hist."` key variants.

- **SCRIBE migration spam** — `ALTER TABLE forge_signals ADD COLUMN macd_histogram` ran every sync cycle via `_conn()` which logs before re-raising. Fix: check `PRAGMA table_info(forge_signals)` first and skip migrations for columns that already exist.

- **`mt5_stale` false positive in Strategy Tester** — The condition service computed staleness from `timestamp_unix` in `market_data.json`. In tester mode the EA writes simulated timestamps (from the test period, e.g. May 4), making the file appear ~8 days old. Fix: detect `strategy_tester` from `status.json`, bypass staleness check in tester, show `mt5 tester` label instead of `mt5 stale`.

- **`regimeCurrent.stale` rendering `0` as text** — `{regimeCurrent.stale && <span>stale</span>}` where `stale=0` (integer) renders `"0"` in React because `0 && anything = 0` and `{0}` renders as the character `0`. Fix: `{!!regimeCurrent.stale && ...}`.

### Added

- **`scalper_gates` block in `/api/live`** — New `_build_scalper_gates()` helper reads `scalper_config.json` and current M5 OsMA from `market_data.json`. Exposes: `require_macd_sell`, `require_macd_buy`, OsMA params, `osma_m5`, `osma_bias` (bull/bear/flat), `sell_osma_pass`, `buy_osma_pass`, `session_ny_sell_cutoff`, `adx_sell_block`.

- **`◈ OsMA GATE` panel in Athena dashboard** — Shows between the FORGE execution quote and TradingView sections. Displays FORGE OsMA(3,10,16) M5 value with sign-coloring (green=bull, red=bear), BULL/BEAR/FLAT bias label, and per-gate rows: SELL (Q2 required: neg+falling) and BUY (Q0 required: pos+rising) with ✓/✗ pass indicators. Session cutoff and ADX sell block shown as footnotes.

- **`TV LENS · AURUM context` sub-panel in AUTO_SCALPER readiness** — Shows live TradingView RSI, MACD, ADX, BB rating, DI+/DI- and directional label (BEAR dir / BULL dir) — exactly what AURUM reads when making AUTO_SCALPER decisions. Lens age shown in seconds.

- **Strategy Tester banner in AUTO_SCALPER panel** — Cyan `STRATEGY TESTER — mt5 timestamps are simulated` notice when tester mode detected.

- **Posterior distribution in Regime Engine panel** — Shows all regime probabilities sorted by confidence (e.g. `TREND_BEAR 77%  RANGE 23%`). Active regime highlighted in gold.

- **LENS source indicator in Regime Engine panel** — Shows `src LENS` or `src MT5` with the key features driving the model: RSI, MACD, ADX from whichever source the regime used.

- **Stale tag on regime transitions** — Transitions marked `stale: true` now show an amber `stale` suffix in the TRANSITIONS (24H) list.

- **All regime performance rows shown** — Was `slice(0,3)`, cutting TREND_BEAR and TREND_BULL data. Now shows all regimes. Active regime label highlighted in gold.

- **TradingView MACD surfaced as null when missing** — `_build_tradingview_panel` maps `macd_hist=0.0` (lens fallback for "study not on chart") to `null` so dashboard shows `—` instead of misleading `0.00000`.

- **`lens_indicators` block in `/api/autoscalper/conditions`** — Full TV LENS snapshot (RSI, MACD, BB rating, ADX, DI+/DI-, directional booleans, age) now included in the readiness report alongside MT5 data.

---

## [System 1.9.7] — 2026-05-09 (ATHENA — iMACD buffer-2 fixes, market data reporting)

### Fixed

- **`WriteMTFBlock` and `WriteMarketData` H1 iMACD buffer 2** — Both used `CopyBuffer(imacd_handle, 2, ...)` which always returns -1 (buffer 2 does not exist in iMACD). The `macd_hist` field in `market_data.json` for all MTF blocks (M5/M15/M30/H1) was always 0. Fix: compute OsMA = `buffer_0 − buffer_1` (main − signal) in-place for market data reporting. This is separate from the gate fix (which uses `iOsMA` handle); this patch completes the cleanup for all three remaining call sites.

---

## [System 1.9.6] — 2026-05-09 (FORGE 2.7.8 — OsMA BUY gate enabled)

### Changed

- **`FORGE_BREAKOUT_REQUIRE_MACD_BUY`: 0 → 1** — Activates the OsMA Q0 BUY gate. BUY breakout entries now require the OsMA histogram to be positive AND rising (Q0: strong bull momentum confirmed) at entry time. Passes only when fast EMA > slow EMA AND the MACD−Signal gap is widening — double confirmation that bullish momentum is accelerating. Previously off (experimental); enabled for Run 28+ validation alongside the SELL Q2 gate.

- **FORGE version: 2.7.7 → 2.7.8**

---

## [System 1.9.5] — 2026-05-09 (FORGE 2.7.7 — Session cutoff · OsMA 4-quadrant gate · ADX tiers · SELL LIMIT cascade)

### Strategy basis — OsMA (Oscillator of a Moving Average) — MACD Histogram

OsMA is the difference between the MACD line and its signal line:

```
OsMA = MACD_line − Signal_line
     = (EMA_fast − EMA_slow) − SMA(MACD_line, signal_period)
```

In MT5, `iOsMA()` returns this as buffer 0 directly. The `iMACD()` indicator has only buffers
0 (MACD line) and 1 (signal line) — there is no buffer 2. The histogram you see drawn on the
chart in MT5 is actually the MACD line itself (buffer 0), not OsMA. OsMA requires either manual
subtraction or the dedicated `iOsMA()` handle.

#### MACD Histogram MC 4-quadrant framework (AK20 / traderak20@gmail.com, MQL5 #65050)

The MACD Histogram MC indicator classifies the histogram into four momentum states, each with a
distinct color. FORGE 2.7.7 adopts this framework for gate logic and DB diagnostics:

| Quadrant | Histogram | Direction | Color (MC) | SELL gate | BUY gate |
|----------|-----------|-----------|------------|-----------|----------|
| **Q0** | positive + rising | Strong bull momentum | LimeGreen | **BLOCK** | **PASS** |
| **Q1** | positive + falling | Bull momentum fading | Dark red | **BLOCK** | BLOCK |
| **Q2** | negative + falling | Strong bear momentum | Red | **PASS** ✓ | BLOCK |
| **Q3** | negative + rising | Bear momentum fading | Dark green | **BLOCK** | BLOCK |

**SELL entries are only allowed in Q2** — the histogram must be both negative (bearish bias) and
falling (momentum is accelerating downward). This is the one quadrant where a short scalp has
full MACD confirmation. Any weakening (Q3) or crossover (Q0/Q1) is a block.

**BUY entries are only allowed in Q0** — histogram positive and rising (bullish momentum
accelerating). Gate is `breakout_require_macd_buy`, **off by default** — experimental, enable
only when a longer backtest validates it doesn't over-filter valid BUY breakouts.

#### When to use OsMA in scalping

OsMA is most useful during **active, fast momentum** — exactly the condition FORGE targets:

- **Fast bull move (BUY gate):** OsMA positive and rising confirms EMA fast > EMA slow AND
  MACD is above its own signal line — double layer of bullish confirmation. Absent in choppy
  markets or fading rallies.

- **Fast bear move (SELL gate):** OsMA negative and falling confirms EMA fast < EMA slow
  (downtrend) AND momentum is accelerating lower (histogram expanding below zero). Stops
  the EA from selling into a bear exhaustion (Q3) where the move has already peaked.

**It is NOT a trend-entry indicator.** Do not use it to detect the start of a new trend — the
MACD lags by construction. Use it exclusively as a momentum confirmation for an existing
breakout signal already identified by BB + RSI + ADX.

**Parameters used: OsMA(3, 10, 16)**
- Fast EMA = 3: extremely responsive, designed for M5 scalp timing (not 12/26)
- Slow EMA = 10: short-horizon trend reference
- Signal SMA = 16: slightly longer smoothing to avoid tick noise on the histogram
- Source: arXiv:2206.12282 — RSI + MACD(3,10,16) dual gate = 84-86% win rate

#### MQL5 code — iOsMA single buffer read (the correct approach)

```mql5
// Single buffer, no subtraction needed — buffer 0 = MACD_line - Signal_line
double _hist[2];
if(CopyBuffer(g_h_osma_scalp, 0, 0, 2, _hist) == 2) {
   double _h0 = _hist[0];  // current bar OsMA value
   double _h1 = _hist[1];  // previous bar OsMA value

   // 4-quadrant classification:
   if(_h0 >= 0.0 && _h0 > _h1) // Q0: positive + rising → strong bull
   if(_h0 >= 0.0 && _h0 < _h1) // Q1: positive + falling → bull fading
   // _h0 < 0.0 && _h0 < _h1   // Q2: negative + falling → strong bear (SELL PASS)
   if(_h0 < 0.0 && _h0 > _h1)  // Q3: negative + rising → bear fading
}

// Initialise handle (once, in indicator refresh):
g_h_osma_scalp = iOsMA(_Symbol, PERIOD_M5, 3, 10, 16, PRICE_CLOSE);

// Wrong (iMACD buffer 2 does not exist — always returns -1):
// CopyBuffer(g_h_macd_scalp, 2, 0, 2, _hist);  ← DO NOT USE
```

#### Research sources

- arXiv:2206.12282 — RSI + MACD dual gate: 84-86% WR backtest
- MACD Histogram MC indicator by AK20 (MQL5 #65050, traderak20@gmail.com) — 4-quadrant logic
- MT5 official docs — iMACD has 2 buffers only (0=main, 1=signal); iOsMA buffer 0 = OsMA
- TradingView MACD MetaTrader Style (vrzDxjSE) — MT5 uses SMA signal, not EMA (OsMA result differs from TradingView standard MACD)

---

### Added

- **Session SELL cutoff (`session_ny_sell_cutoff_utc: 17`)** — blocks new SELL entries at or after 17:00 UTC. Post-17:00 UTC XAUUSD is lower liquidity, wider spreads, and prone to Asia-transition reversals. BUY entries continue. Gate reason: `entry_quality_session_sell_cutoff`. Config: `safety.session_ny_sell_cutoff_utc`, `session_london_sell_cutoff_utc`. Env: `SESSION_NY_SELL_CUTOFF_UTC`.
  - Run 25 validation: G5011 (17:10 UTC, -$238) + G5013 (18:25, -$83) both blocked. Net improvement: **+$321** vs Run 23.

- **OsMA(3,10,16) SELL gate (`breakout_require_macd_sell: 1`)** — replaces the broken iMACD buffer-2 approach. Uses `iOsMA()` handle; buffer 0 = MACD−Signal directly. Applies 4-quadrant classification: SELL only passes in Q2 (histogram negative AND falling). Gate reasons in DB: `entry_quality_macd_q0_bull_rising`, `entry_quality_macd_q1_bull_fading`, `entry_quality_macd_q3_bear_fading`. The histogram value is logged in `SIGNALS.macd_histogram` for every gate-fire event for post-run diagnostics.

- **Bug fix — iMACD buffer 2 (2.7.7c)** — Previous implementation read `CopyBuffer(g_h_macd_scalp, 2, ...)` which always returns -1 (buffer 2 does not exist in iMACD). The gate was silently fully disabled. Fixed by replacing iMACD with `iOsMA` and reading buffer 0. Also fixed the TAKEN signal log which had the same buffer-2 bug.

- **OsMA BUY gate (`breakout_require_macd_buy: 0`, off by default)** — symmetric gate for BUY entries, passes only in Q0 (histogram positive AND rising). Enable with `FORGE_BREAKOUT_REQUIRE_MACD_BUY=1` to test on a longer backtest once SELL gate is validated. Journal reasons: `entry_quality_macd_q1_bull_fading`, `entry_quality_macd_q2_bear_str`, `entry_quality_macd_q3_bear_fading`.

- **ADX-tiered lot factors + BLOCK** (`breakout_adx_lot_*`) — Protects SELL entries at extended ADX levels. Uses M15 ADX (less lag than M5 per OpoFinance/Trade2Win). Three outcomes:
  | M15 ADX | Factor | Lot at 0.08 base |
  |---------|--------|-----------------|
  | < 35 | 1.0× (full) | 0.08 |
  | 35–44 | 0.25× | 0.02 |
  | 45–54 | 0.125× | **0.01 (broker min)** |
  | ≥ 55 | **BLOCK** | — |
  Gate reason: `entry_quality_adx_extreme_sell`. Config: `breakout_adx_lot_mid_threshold`, `breakout_adx_lot_high_threshold`, `breakout_adx_lot_factor_mid`, `breakout_adx_lot_factor_high`, `breakout_adx_sell_block_threshold`.

- **Cardwell SELL LIMIT cascade (`breakout_sell_limit_enabled: 1`)** — After a crash SELL market order, places a pending SELL LIMIT at `bid + ATR × 0.4` to catch the Cardwell Bear Resistance bounce-and-fail re-short. Lot: `0.125× base` (1/8th, danger-zone sizing). Expiry: 6 M5 bars via `ORDER_TIME_SPECIFIED`. Cancelled automatically in `OnTradeTransaction` when the parent market SELL hits SL. State tracked in `g_sell_limit_stack[2]` (up to 2 slots). Config: `breakout_sell_limit_enabled`, `breakout_sell_limit_atr_mult`, `breakout_sell_limit_lot_factor`, `breakout_sell_limit_expiry_bars`. Env: `FORGE_BREAKOUT_SELL_LIMIT_*`.

- **Three new SIGNALS columns** (`macd_histogram`, `m15_adx`, `lot_factor`) — `JournalRecordSignal()` extended with 3 default parameters (backwards-compatible). TAKEN records populate all three. MACD gate SKIP records populate `macd_histogram` with the actual OsMA value at gate-fire time. SCRIBE `aurum_intelligence.db` migrated with `ALTER TABLE ADD COLUMN`.

### Gate execution order — SELL breakout path (full, as of 2.7.7)

1. BB condition: `prev_close < BB_lower − buffer` + M5/M15/H1/H4 bear alignment
2. **Cardwell Bear Resistance ceiling**: `m5_rsi < rsi_sell_max (60)` ← 2.7.6
3. **Session SELL cutoff**: `hour < session_ny_sell_cutoff_utc (17)` ← **2.7.7**
4. **ADX extreme block**: `m15_adx < 55` ← **2.7.7**
5. ADX min SELL: `m5_adx ≥ 25` ← 2.7.3
6. H1+H4 crash bypass check: `h1_bear && h4_bear && rsi > 20` ← 2.7.6
7. Two-tier RSI floor (base 30 + weak-ADX 36) — skipped on crash bypass
8. ADX spike-from-flat (6-bar lookback) — skipped on crash bypass
9. RSI-declining gate (rising RSI, auto-off ADX ≥ 40) ← 2.7.4/2.7.5
10. **OsMA Q2 gate**: histogram negative AND falling ← **2.7.7**
11. News RSI tighten ← 2.7.6
12. Direction = SELL → `CheckEntryQuality()` → Gate −1 (news BLOCK)

### Gate execution order — BUY breakout path (full, as of 2.7.7)

1. BB condition: `prev_close > BB_upper + buffer` + M5/M15/H1/H4 bull alignment
2. **Cardwell Bull Support floor**: `m5_rsi > rsi_buy_min (40)` ← 2.7.6
3. RSI buy ceiling: `m5_rsi < rsi_buy_ceil (70)` ← 2.6.7
4. H1 DI directional gate (Wilder DI+/DI−) ← 2.7.5
5. **OsMA Q0 gate (optional, off by default)**: histogram positive AND rising ← **2.7.7**
6. News RSI tighten ← 2.7.6
7. Direction = BUY → `CheckEntryQuality()` → Gate −1 (news BLOCK)

### How to use

- **OsMA SELL gate**: `FORGE_BREAKOUT_REQUIRE_MACD_SELL=1` (on). Set `0` to disable. DB column `macd_histogram` shows OsMA value at gate-fire; quadrant is visible in `gate_reason`. In a fast bear move, Q2 fires when momentum is accelerating — check `gate_reason LIKE 'macd_q%'` in SIGNALS to audit.
- **OsMA BUY gate**: `FORGE_BREAKOUT_REQUIRE_MACD_BUY=0` (off). Enable with `=1` to require Q0 (strong bull) for BUY entries. Start with a 2-week tester run before enabling in live — BUY breakouts are already filtered by RSI+H1+DI and adding OsMA may over-filter in ranging conditions.
- **OsMA params**: `FORGE_BREAKOUT_MACD_FAST=3`, `FORGE_BREAKOUT_MACD_SLOW=10`, `FORGE_BREAKOUT_MACD_SIGNAL=16`. These are now live in the sync pipeline (`make scalper-env-sync` picks them up).
- **ADX tiers**: set `FORGE_BREAKOUT_ADX_SELL_BLOCK_THRESHOLD=55` (default). Lower to 50 to add protection at high ADX without needing the mid/high tiers. Mid/high thresholds can be tuned via `FORGE_BREAKOUT_ADX_LOT_MID_THRESHOLD` / `FORGE_BREAKOUT_ADX_LOT_HIGH_THRESHOLD`.
- **SELL LIMIT**: `FORGE_BREAKOUT_SELL_LIMIT_ENABLED=1` (on). Disable with `=0` if the bounce pattern isn't active in the current regime. Monitor `SIGNALS.gate_reason = 'SELL_LIMIT_PLACED'` in the DB.

---

## [System 1.9.4] — 2026-05-09 (FORGE 2.7.6 — Cardwell RSI zones + H1+H4 crash SELL bypass)

### Strategy basis — Andrew Cardwell RSI Zone Theory

Andrew Cardwell (CMT curriculum, the most cited developer of Wilder's original RSI work) defines
two distinct RSI trading ranges depending on market regime:

| Regime | RSI Range | Entry zone | Entry signal |
|--------|-----------|------------|--------------|
| **Uptrend** | 40–80 | Bull Support: RSI **40** | Long re-entry on RSI dip to 40 |
| **Downtrend** | 20–60 | Bear Resistance: RSI **60** | Short re-entry on RSI bounce to 60 |

The standard 70/30 Wilder thresholds apply only in ranging markets. In trending markets, the range
shifts and the midline roles invert. Below RSI 20 in a downtrend is exhaustion territory — not a
sell signal. RSI 60 rejection in a downtrend is the ideal second short entry (sell-the-bounce).

Sources:
- [TradingView — Cardwell RSI Zones indicator (v6JlR98g)](https://www.tradingview.com/script/v6JlR98g/)
- [Alchemy Markets — RSI Education](https://alchemymarkets.com/education/indicators/relative-strength-index/)
- [Andrew Cardwell — Using the RSI (Scribd)](https://www.scribd.com/document/489489408/Andrew-Cardwell-Using-the-RSI)
- [StockCharts ChartSchool — RSI](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/relative-strength-index-rsi)

### Added

- **`rsi_sell_max`: 50 → 60 (Cardwell Bear Resistance ceiling)** — SELL breakout now fires when RSI is up to 60, not just below 50. In a confirmed downtrend (H1+H4 bear), RSI 50–60 is the Bear Resistance zone — the ideal re-short after price bounces from the initial crash low. The previous `rsi_sell_max=50` was blocking every Cardwell Bear Resistance entry. Config: `bb_breakout.rsi_sell_max`, env: (config-only). EA default updated to 60.

- **`rsi_buy_min`: 50 → 40 (Cardwell Bull Support floor)** — BUY breakout now fires when RSI is as low as 40, not just above 50. In a confirmed uptrend (H1+H4 bull), RSI 40–50 is the Bull Support zone — the ideal re-buy after a dip within a rally. The previous `rsi_buy_min=50` was blocking every Cardwell Bull Support entry. Config: `bb_breakout.rsi_buy_min`, env: (config-only). EA default updated to 40.

- **H1+H4 crash SELL bypass (`breakout_h1h4_crash_sell: true`)** — When H1 EMA20 < EMA50 AND H4 EMA20 < EMA50 (confirmed multi-TF bear), the `rsi_sell_floor` and `adx_spike_sell` gates are bypassed. Allows crash-day SELL entries at RSI 20–30 (early crash momentum) while standard gates remain active for non-crash conditions. `h1_bear && h4_bear` is the crash detector — no new indicator. Config: `bb_breakout.h1h4_crash_sell`, env: `FORGE_BREAKOUT_H1H4_CRASH_SELL`.

- **Cardwell RSI 20 crash floor (`breakout_h1h4_crash_sell_rsi_min: 20`)** — Hard RSI lower bound applied even when crash bypass is active. Cardwell defines RSI 20 as the extreme-oversold floor in a downtrend (below this = exhaustion, not momentum). Prevents G5002-class losses (RSI 16, ADX 47, crash bypass active → SL hit). RSI 20–30 entries allowed; RSI < 20 blocked. Config: `bb_breakout.h1h4_crash_sell_rsi_min`, env: `FORGE_BREAKOUT_H1H4_CRASH_SELL_RSI_MIN`.

- **`max_open_same_direction`: 1 → 2** — Allows two concurrent groups in the same direction. Enables the Cardwell two-entry pattern: initial crash SELL (RSI 20–30) + Bear Resistance re-short (RSI 50–60 on bounce), both open simultaneously. Config: `safety.max_open_same_direction`.

- **`rsi_sell_adx_floor` per-bar throttle** (`g_scalper_last_rsisellfloor_log_bar`) — fixes tick-spam: previously fired on every tick within the same M5 bar (30+ rows at 15:55 in Run 21). Now logs once per bar, consistent with `adx_min_sell`, `adx_spike_sell`, `rsi_rising_sell`, `h1_di_buy`.

- **News filter linear RSI slide** — TIGHTEN zone now slides proportionally from baseline (70/33) to max-tighten (65/38) as proximity increases, instead of jumping immediately to max at the tighten threshold. Formula: `slide = (p − tighten_pct) / (block_pct − tighten_pct)`.

- **News filter config-robust baselines** — `ScalperNewsCheck()` resets now use `g_sc.breakout_rsi_buy_ceil` / `g_sc.breakout_rsi_sell_floor` instead of hardcoded 70.0/33.0. Prevents spurious news-tighten skips if RSI floors are changed in config.

- **BB_BREAKOUT_RETEST news tighten coverage** — Confirmed retest entries now check `entry_quality_news_rsi_tighten` before committing `direction`. Previously bypassed because retest set `direction` before the BB_BREAKOUT block (which contains the tighten check). Fix: added BUY/SELL guard in the retest confirmation path with `g_nf_eff_rsi_*` already primed by the pre-BB call.

- **`tighten_pct < block_pct` cross-validation** — After JSON parsing of both fields, enforces `tighten_pct < block_pct`. If inverted, silently resets `tighten_pct = block_pct * 0.5`. Prevents TIGHTEN zone collapse or unreachable BLOCK on bad config.

### Gate execution order — SELL breakout path (full, as of 2.7.6)

1. BB condition: `prev_close < BB_lower − buffer` + M5/M15/H1/H4 bear alignment
2. **Cardwell Bear Resistance ceiling**: `m5_rsi < rsi_sell_max (60)` ← **2.7.6**
3. ADX min SELL: `m5_adx ≥ 25`
4. H1+H4 crash bypass check: `h1_bear && h4_bear && rsi > 20` ← **2.7.6**
5. Two-tier RSI floor (base 30 + weak-ADX 36) — skipped on crash bypass
6. ADX spike-from-flat (6-bar lookback) — skipped on crash bypass
7. RSI-declining gate (rising RSI bar-over-bar) ← 2.7.4
8. News RSI tighten — last line of defence ← 2.7.6
9. Direction = SELL → `CheckEntryQuality()` → Gate −1 (news BLOCK)

### Gate execution order — BUY breakout path (full, as of 2.7.6)

1. BB condition: `prev_close > BB_upper + buffer` + M5/M15/H1/H4 bull alignment
2. **Cardwell Bull Support floor**: `m5_rsi > rsi_buy_min (40)` ← **2.7.6**
3. RSI buy ceiling: `m5_rsi < rsi_buy_ceil (70)` ← 2.6.7
4. H1 DI directional gate (Wilder DI+/DI−) ← 2.7.5
5. News RSI tighten ← 2.7.6
6. Direction = BUY → `CheckEntryQuality()` → Gate −1 (news BLOCK)

### Reference documentation

- `docs/FORGE_NEWS_FILTER_GATE_FLOW.md` — complete signal gate flow ASCII diagram
- `docs/FORGE_NEWS_FILTER_REVIEW.md` — Codex gate review + expert triage
- `docs/FORGE_APR29_SELL_REJECTION_ANALYSIS.md` — crash SELL rejection root-cause + options

---

## [System 1.9.3] — 2026-05-08 (FORGE 2.7.6 — Native MT5 Calendar news filter)

### Added

- **Native news filter** — queries MT5 Economic Calendar (`CalendarValueHistory` + `CalendarEventById`) natively inside FORGE. No SENTINEL dependency, no WebRequest. Works in Strategy Tester and on VPS.
- **Per-impact windows**: separate before/after minutes for LOW (5/5), MEDIUM (10/15), HIGH (20/30).
- **Keyword overrides** (`news_filter_special`): `"KEYWORD:before,after+KW2:b2,a2"` substring match. Example: `"Non-Farm:30,60+FOMC:40,45+CPI:50,55"`.
- **Multi-currency**: `"ALL"` expands to all 9 MT5 calendar currencies; any comma/space combo accepted. Default `"USD,EUR,GBP"` for XAUUSD — no dedicated XAU calendar symbol exists.
- **Sliding proximity rule**: 3 zones — ALLOW / TIGHTEN (RSI slides 70→65 BUY, 33→38 SELL) / BLOCK. Symmetric pre and post event. Tighten journals as `entry_quality_news_rsi_tighten`.
- **Post-news hard floor** (`news_filter_hard_floor_min=5`): absolute block for first 5 min post-event (chaos zone).
- **Input override**: `input bool NewsFilterInputsOverride = false` + `input bool NewsFilterEnabled = true`. Active input wins over config JSON on every reload. Enabled by default.
- **23 tests** in `tests/api/test_forge_news_filter.py` — config structure, env mappings, source checks, logic invariants.

### Fixed (Codex review)

- **CRITICAL**: Proximity used midpoint approximation for event_time — wrong with asymmetric windows (e.g. FOMC 40/45). Fixed: store exact `g_nf_event_time` in refresh.
- **HIGH**: Keyword `before` values excluded from query horizon — 40-min keyword override could be missed. Fixed: horizon uses max of all keyword and impact before values.
- **HIGH**: Effective RSI globals could be stale across tick boundaries. Fixed: `ScalperNewsUpdateEffectiveThresholds()` helper called at gate -1 and before BB setup selection.
- **MEDIUM**: Back-to-back events missed after cached window expired. Fixed: force refresh on expiry.
- **MEDIUM**: Silent failure when calendar data unavailable in tester. Fixed: `PrintFormat` warning.

---

## [System 1.9.2] — 2026-05-08 (FORGE 2.7.5 — H1 DI+/DI- BUY quality gate)

### Added

- **H1 DI directional gate** (`bb_breakout.require_h1_di_buy: 1`) — blocks BUY breakout when H1 DI- > DI+ at weak M5 ADX. Implements Wilder's original directional confirmation: ADX strength (buffer 0) confirms trend intensity, but DI+/DI- (buffers 1 and 2) confirms direction. A BUY entry is counter-directional by definition when H1 DI- dominates, regardless of M5 price action. Targets G8-class losses: Monday Apr 20 BUY at ADX 26.4 into a H1-bearish environment (-$269.36). At strong M5 ADX ≥ 28 (`counter_buy_adx_threshold`), gate is inactive — strong momentum self-confirms direction.
- **Zero new indicator handles**: reads DI+ (buffer 1) and DI- (buffer 2) from the existing `g_h_adx = iADX(_Symbol, PERIOD_H1, 14)` handle. Uses `h1_bias_shift` (0 in tester, 1 in live) consistent with all other H1 reads in `CheckNativeScalperSetups()`.
- **New journal gate reason**: `entry_quality_h1_di_buy`
- **New throttle global**: `g_scalper_last_h1dibuy_log_bar`
- **Config**: `bb_breakout.require_h1_di_buy: 1`, `bb_breakout.counter_buy_adx_threshold: 28`
- **Env**: `FORGE_BREAKOUT_REQUIRE_H1_DI_BUY=1`, `FORGE_BREAKOUT_COUNTER_BUY_ADX_THRESHOLD=28`

### Industry context

MQL5 community consensus: using ADX without DI+/DI- is the most common EA design flaw. ADX above 25 confirms a trend exists — DI+/DI- confirms which direction. The `iADX` indicator in MQL5 exposes all three via separate buffers on the same handle. The gate auto-offs at strong ADX (≥ 28) where momentum is self-evident, matching the calibrated threshold from the h1_counter_buy analysis.

---

## [System 1.9.1] — 2026-05-08 (FORGE 2.7.4 — RSI-declining + ADX-duration gates + bounce_adx_max=40)

### Fixed

- **`bounce_adx_max`: 50 → 40** — blocks BB_BOUNCE SELL when ADX > 40. Targets G5009-class losses (BB_BOUNCE SELL at ADX 43.1, -$59.28 in Run 17). High-ADX counter-trend bounces fail at elevated momentum — strong directional moves resist mean-reversion. Config-only change, no code. Env key: `FORGE_BOUNCE_ADX_MAX`.

### Added

- **ADX duration gate** (`bb_breakout.adx_min_sell_lookback_bars: 6`) — blocks SELL breakout when ADX was below `adx_min_sell` (25) exactly N M5 bars ago (default N=6 = 30 min lookback). Targets G5024-class losses: ADX spiked 13→37 in 45 min, creating a valid-looking breakout with no momentum history; price reversed +15pts in 8 min. The gate reads `CopyBuffer(g_mtf[0].h_adx, 0, 6, 1, buf)` against the existing M5 ADX handle — zero new handles. Journal gate reason: `entry_quality_adx_spike_sell`. Config: `bb_breakout.adx_min_sell_lookback_bars`, env: `FORGE_BREAKOUT_ADX_MIN_SELL_LOOKBACK_BARS`. Set `0` to disable.
- **RSI-declining gate** (`bb_breakout.require_rsi_declining_sell: 1`) — blocks SELL breakout when RSI is rising bar-over-bar (current bar RSI > prior bar RSI). Auto-disabled when ADX ≥ `adx_sell_floor_threshold` (35) — strong-trend SELL entries don't require RSI momentum confirmation. Targets G5007-class losses (SELL at RSI 39.5 rising from 35.2, -$38.14; RSI bouncing off the floor signals fading SELL momentum at entry). Reads `CopyBuffer(g_mtf[0].h_rsi, 0, 1, 1, buf)` — one buffer call against existing M5 RSI handle. Journal gate reason: `entry_quality_rsi_rising_sell`. Config: `bb_breakout.require_rsi_declining_sell` (bool01), env: `FORGE_BREAKOUT_REQUIRE_RSI_DECLINING_SELL`. Set `0` to disable.
- **Session-start visibility log** — fires once each time the EA transitions from session_off to active. Logs: current ADX, ADX 30 min ago (6 bars via `CopyBuffer(..., 0, 6, 1, buf)`), RSI, and BB expansion state. Enables "armed context" entries — the same market structure pre-read that RSI divergence analysis recommends doing manually before the session opens. Example: `FORGE SESSION START: hour=7UTC adx=28.4 adx_30min_ago=19.1 rsi=44.2 bb=EXPANDING (width 12.40→14.83)`. Global `g_scalper_prev_session_blocked` tracks the previous tick's session state.
- **New globals**: `g_scalper_last_adxdur_log_bar`, `g_scalper_last_rsidecl_log_bar`, `g_scalper_prev_session_blocked` — M5-bar throttles for new gate journals and session-state tracking.
- **`rsi_decl_sell_adx_threshold: 28`** — separate ADX threshold for `rsi_rising_sell` auto-off, independent of `adx_sell_floor_threshold` (35, used for RSI two-tier floor). At 28, the gate blocks G7-class (ADX 26.8 < 28) while passing G17/G18/G19-class wins (ADX 28-35). Previous implementation incorrectly shared the 35 threshold, which blocked all three of those winning entries. Field: `breakout_rsi_decl_sell_adx_threshold`, env: `FORGE_BREAKOUT_RSI_DECL_SELL_ADX_THRESHOLD`. Default: `28.0`.

### Gate execution order (SELL breakout path)
1. ADX min SELL (≥ 25) ← 2.7.3
2. Two-tier RSI floor (absolute + weak-ADX stricter floor) ← 2.6.8
3. **ADX duration gate** (30min lookback, spike-from-flat) ← **2.7.4**
4. **RSI-declining gate** (rising RSI, auto-off ADX ≥ 35) ← **2.7.4**
5. Direction = SELL

### How to use

- ADX duration gate: `FORGE_BREAKOUT_ADX_MIN_SELL_LOOKBACK_BARS=6` (active). Set `0` to disable. Increase to 12 (60min) if spike-from-flat patterns persist across longer timeframes.
- RSI-declining gate: `FORGE_BREAKOUT_REQUIRE_RSI_DECLINING_SELL=1` (active). Auto-switches off when ADX ≥ 35 — no separate config toggle needed for strong-trend SELLs.
- bounce_adx_max: `FORGE_BOUNCE_ADX_MAX=40`. Previous default was 50 (effectively permissive). 40 blocks ADX 40-50 bounces while allowing ADX 20-40 mean-reversion which has better historical success.

---

## [System 1.9.0] — 2026-05-08 (FORGE 2.7.3 — Split BUY/SELL ADX floors + tester parity + diagnostic log)

### Fixed

- **Tester ADX floor removed**: `breakout_adx_min_eff = MathMin(g_sc.breakout_adx_min, 15.0)` → `= g_sc.breakout_adx_min`. Tester now enforces same ADX threshold as live for both BUY and SELL — eliminates G5018-class artifacts where entries at ADX 15-20 fired in tester but were blocked in live.

### Added

- **`bb_breakout.adx_min_sell: 25`** — separate, stricter ADX floor for SELL-only breakouts. BUY remains at `adx_min=20`. Run 16 data showed BUY entries in the ADX 20-25 zone were highly profitable (+$267: G5005 +$164, G5022 +$103) while SELL entries in the same zone were marginal (+$26 across 3 trades). SELL breakouts in weak ADX are more error-prone (RSI floor bounces, fading moves). New fields: `ScalperConfig.breakout_adx_min_sell`, config key `bb_breakout.adx_min_sell`, env key `FORGE_BREAKOUT_ADX_MIN_SELL`.
- **ADX gate diagnostic log** — once per M5 bar: `FORGE ADX gate: adx=X buy_min=Y sell_min=Z buy=PASS|BLOCKED sell=PASS|BLOCKED | rsi=... price=... atr=...`. Throttled by `g_scalper_last_adxgate_log_bar`. Zero DB overhead.
- **New global**: `g_scalper_last_adxgate_log_bar` — M5-bar throttle for ADX gate diagnostic.

### How to use

- BUY breakouts: blocked when ADX < `adx_min` (default 20). Set `FORGE_BREAKOUT_ADX_MIN` to adjust.
- SELL breakouts: blocked when ADX < `adx_min_sell` (default 25). Set `FORGE_BREAKOUT_ADX_MIN_SELL` to adjust.
- Experts log shows both thresholds every M5 bar — check `sell=BLOCKED` to confirm SELL gate active.
- G5018-class tester artifacts (ADX 15-20 SELL entries) are now impossible in both environments.

---

## [System 1.8.9] — 2026-05-08 (FORGE 2.7.1 — Fix 7C: ATR price extension re-entry gate)

### Added

- **Fix 7C — ATR price extension gate** (`ea/FORGE.mq5`): Blocks same-direction BUY/SELL re-entry when price has moved more than `max_reentry_atr_ext × ATR` from the first group's entry price in the current session. Targets Category F losses (late-stage extended-move re-entry). Gate reason: `entry_quality_atr_ext`. Default `0.0` (disabled); set to `1.5` for Run 15 test.
- **New globals**: `g_first_buy_entry_price`, `g_first_sell_entry_price` — session-scoped anchors, reset on UTC day change and session change.
- **New config key**: `bb_breakout.max_reentry_atr_ext` (float, 0.0–10.0). Wired to `.env` via `FORGE_BREAKOUT_MAX_REENTRY_ATR_EXT`.
- **Tests**: `tests/api/test_forge_7c_atr_ext.py` — 12 tests covering gate disabled, anchor set/no-update, within/at/over limit (BUY + SELL), session reset, zero-ATR guard, wiring checks. All passing.

---

## [System 1.8.8] — 2026-05-08 (FORGE 2.6.10 — correct default inputs: InputMode + ScalperMode)

### Fixed

- **`InputMode` default retained as `"WATCH"`**: Master trading gate. When `g_mode == "WATCH"`, line 739 `WriteTickData(); return;` exits the entire OnTick/OnTimer handler before any scalper code is reached. Prevents accidental live trading on attach — must be set to "SCALPER" explicitly.
- **`ScalperMode` default `"NONE" → "DUAL"`**: Safe to default DUAL because `InputMode=WATCH` is the master gate with two independent checks: (1) `if(g_mode == "WATCH") return;` at line 739 exits before scalper; (2) `if(g_scalper_mode != "NONE" && g_mode != "WATCH" && ...)` at line 744 has explicit WATCH exclusion. EA itself logs: *"native entries need ScalperMode≠NONE and InputMode≠WATCH"*. Setting DUAL by default eliminates one manual step after every recompile with no safety risk.
- **`lot_inputs_override_eff = false` retained by design**: With `NativeScalperInputsOverrideLotSizing=false` and `lot_sizing_source="AUTO"`, config.json remains the authority for all lot engine settings (leg count, staged intervals, etc.). `ScalperLot` input only overrides `fixed_lot` via `ApplyScalperLotInputOverrides()` — this is the intended architecture (retain config.json).

---

## [System 1.8.7] — 2026-05-08 (FORGE 2.6.9 — lot input override + VP POC warmup gate)

### Fixed

- **`ScalperLot` input ignored after JSON load**: `ApplyScalperLotInputOverrides()` never wrote `ScalperLot` back to `g_sc.lot_fixed`, so the config JSON value (0.02) always won even when the input was set to 0.08. Fix: added `if(ScalperLot > 0.0) g_sc.lot_fixed = ScalperLot;` in `ApplyScalperLotInputOverrides()` — same override-or-pass-through pattern used by `SellInsideBandLotFactor`. Changed `ScalperLot` default from `0.01` → `0.0` (sentinel: 0 = use JSON `fixed_lot`; >0 = override JSON). Updated `InitScalperConfig` to seed `lot_fixed` from `ScalperLot` when set, otherwise from the JSON fallback (0.02).
- **VP POC uninit warmup gap**: No check existed that `g_poc_price > 0` before allowing first entry. If `ComputeVolumeProfile()` silently failed at `OnInit` (e.g. `CopyHigh` returned fewer than `vp_lookback` bars), the EA could compute TP targets against a zero POC. Added explicit check `if(g_poc_price <= 0.0) { reason_out = "vp_poc_uninit"; return false; }` in `ForgeNativeScalperWarmupOk()` after the PSAR probe, before the M5 rollover count.

### How to use
- Set `ScalperLot = 0.08` in MT5 Inputs → applies as base lot per leg, overrides `fixed_lot` in JSON
- Leave `ScalperLot = 0.0` → EA uses `scalper_config.json` `lot_sizing.fixed_lot` (unchanged behavior for existing configs)
- `SellInsideBandLotFactor = 0.25` in MT5 Inputs → already worked; now consistent with `ScalperLot` semantics

---

## [System 1.8.6] — 2026-05-08 (FORGE 2.6.8 — hotfix: session_off per-tick journal flood)

### Fixed

- **`session_off` per-tick DB flood (ea/FORGE.mq5 line 3943)**: `JournalRecordSignal("SKIP","session_off",...)` was called on every `OnTick()` during off-hours (Asian session + post-NY), bypassing the existing M5-bar throttle on the adjacent `PrintFormat`. Moved the journal write inside the `if(m5bar != g_scalper_last_sesswarn_log_bar)` guard so it fires at most once per M5 bar. Impact: in Run 12 initial 1.5-day window, 272,238 useless zero-indicator records were written and DB hit 60MB — projects to ~1.5GB for a full 24-day run, causing tester slowdown. Fix reduces off-hours journal output to ≤96 records/day (one per M5 bar during off-hours).

---

## [System 1.8.5] — 2026-05-08 (FORGE 2.6.8 — loss reduction: ADX floor, RSI sell floor, STRICT bounce, inside-band half-lot)

### Phase A — Config changes only

- **`bb_breakout.adx_min`: `14 → 20`** — blocks false breakouts in ranging tape; ADX<20 = no directional trend by Wilder's definition; caused 3 Category-A losses in Run 11 (~$100).
- **`bb_breakout.rsi_sell_floor`: `30 → 33`** — closes 5× float-boundary violation at RSI=30.0 and blocks oversold-exhaustion SELL entries (RSI 30–33 = move near-spent, bounce risk elevated). Journals `entry_quality_rsi_sell_floor`.
- **`bb_bounce.bounce_htf_bias`: `BALANCED → STRICT`** — blocks BB_BOUNCE SELL when H1 OR M15 is bullish; blocks BB_BOUNCE BUY when H1 OR M15 is bearish. Safe during sell-offs: H1 bearish → NOT bullish → SELL bounce still fires. Saves ~$45 from Run 11 Category-C losses.

### Phase B — EA changes (ea/FORGE.mq5)

- **ADX-conditioned RSI sell floor (Fix 5)**: two-tier floor — absolute `rsi_sell_floor=33` always applies; when `ADX < adx_sell_floor_threshold (35)` the stricter `rsi_sell_floor_weak_adx=36` applies. Weak-trend SELL entries with low RSI are the highest-risk exhaustion trades. New gate reason: **`entry_quality_rsi_sell_adx_floor`**. Config: `bb_breakout.adx_sell_floor_threshold`, `bb_breakout.rsi_sell_floor_weak_adx`.
- **Half-lot inside-band SELL (Fix 7)**: after a BB_BREAKOUT SELL fires, if current mid > BB_LOWER (price has bounced back inside the band), lot size is multiplied by `bb_breakout.sell_inside_band_lot_factor (0.5)`. Confirmed breakout (mid ≤ BB_LOWER) uses full lot. Reduces exposure on fading breakouts. Logs "FORGE SCALPER: SELL inside band — lot factor=…".
- **Struct `ScalperConfig`** — 3 new fields: `breakout_adx_sell_floor_threshold`, `breakout_rsi_sell_floor_weak_adx`, `breakout_sell_inside_band_lot_factor`.
- **`InitScalperConfig`** — updated defaults: `rsi_sell_floor=33`, plus new Phase B field defaults.
- **`ReadScalperConfig`** — parses all 3 new fields from `bb_breakout` JSON.
- **Version 2.6.8** (`FORGE_VERSION`, `#property version`).

### Changed (config + tooling)

- **`config/scalper_config.defaults.json`**, **`config/scalper_config.json`** — all Phase A+B keys.
- **`scripts/sync_scalper_config_from_env.py`** — `FORGE_BREAKOUT_ADX_SELL_FLOOR_THRESHOLD`, `FORGE_BREAKOUT_RSI_SELL_FLOOR_WEAK_ADX`, `FORGE_BREAKOUT_SELL_INSIDE_BAND_LOT_FACTOR`.

### Tests

- **`tests/api/test_forge_268_gates.py`** — 52 unit tests covering: config value assertions, Phase B key presence/ranges, gate boundary logic (adx_min, rsi floor, ADX-conditioned floor, inside-band lot factor, STRICT bounce modes), sell-off scenario pass/block, sync script env coverage.

---

## [System 1.8.4] — 2026-05-08 (FORGE 2.6.7 — RSI exhaustion gates + bounce ADX tester fix)

### Added (ea/FORGE.mq5)

- **`bb_breakout.rsi_buy_ceil`** (default **`70`**) — before SL/TP calculation and retest state machine, skip BB_BREAKOUT **BUY** when M5 RSI ≥ ceiling; journal **`SKIP`** **`entry_quality_rsi_buy_ceil`**. Blocked the May 1 cluster (RSI 74.9–83.6) and Apr 17 BUY exhaustion losses from Run 10.
- **`bb_breakout.rsi_sell_floor`** (default **`30`**) — skip BB_BREAKOUT **SELL** when M5 RSI ≤ floor; journal **`SKIP`** **`entry_quality_rsi_sell_floor`**. Blocked 6 confirmed SL hits (Apr 27–May 1, RSI 16–29) from Run 10.
- Both gates apply to the immediate-entry path **and** the retest state machine path (`breakout_use_retest`).
- **Version** **2.6.7** (`FORGE_VERSION`, `#property version`).

### Changed (ea/FORGE.mq5)

- Struct **`ScalperConfig`** — two new fields: **`breakout_rsi_buy_ceil`**, **`breakout_rsi_sell_floor`**.
- **`InitScalperConfig`** — defaults 70.0 / 30.0.
- **`ReadScalperConfig`** bb_breakout section — parses **`rsi_buy_ceil`** / **`rsi_sell_floor`** from `bb_breakout` JSON object.

### Changed (config + tooling)

- **`config/scalper_config.defaults.json`**, **`config/scalper_config.json`**:
  - **`bb_breakout.rsi_buy_ceil: 70`**, **`bb_breakout.rsi_sell_floor: 30`** (new keys).
  - **`bb_bounce.adx_max`**: `38` → `50` — aligns tester and live cap at a single value.
  - **`bb_bounce.bounce_respect_adx_max_in_tester`**: `0` → `1` — tester no longer relaxes the ADX cap to 99; bounce entries above ADX 50 are now blocked in backtests. Closed the Run 10 May 1 09:35 ADX=62 anti-trend entry.
- **`scripts/sync_scalper_config_from_env.py`** — **`FORGE_BREAKOUT_RSI_BUY_CEIL`** (50–100), **`FORGE_BREAKOUT_RSI_SELL_FLOOR`** (0–50).

### Documentation

- **`docs/FORGE_TRADING_RULES.md`** — new §§ "BB_BREAKOUT RSI exhaustion gates" and "BB_BOUNCE ADX cap — tester enforcement".
- **`docs/FORGE_JOURNAL_SQL.md`**, **`docs/DATA_CONTRACT.md`** — added **`entry_quality_rsi_buy_ceil`** and **`entry_quality_rsi_sell_floor`** to the `gate_reason` enum.

---

## [System 1.8.3] — 2026-05-08 (FORGE 2.6.6 — same-direction group cap)

### Added (ea/FORGE.mq5)

- **`safety.max_open_same_direction`** (default **1**, **`0`** = no cap) — before other entry-quality checks, skip when **`g_groups`** already has at least that many open groups in the proposed direction; journal **`SKIP`** **`entry_quality_direction_cap`**. **`ScalperOpenGroupCountByDirection`** uses the in-memory group ledger (no extra MT5 API scan).
- **Version** **2.6.6** (`FORGE_VERSION`, `#property version`).

### Changed (config + tooling)

- **`config/scalper_config.defaults.json`**, generated **`config/scalper_config.json`** — **`safety.max_open_same_direction`**.
- **`scripts/sync_scalper_config_from_env.py`** — **`FORGE_MAX_OPEN_SAME_DIRECTION`**.

### Documentation

- **`docs/FORGE_TRADING_RULES.md`**, **`docs/FORGE_JOURNAL_SQL.md`**, **`docs/DATA_CONTRACT.md`**, **`SKILL.md`**, **`SOUL.md`**, **`.env.example`** — cap and **`entry_quality_direction_cap`**.

---

## [System 1.8.2] — 2026-05-07 (FORGE 2.6.5 — native entry quality gate)

### Added (ea/FORGE.mq5)

- **M5 Entry Quality Gate** (`CheckEntryQuality`) — runs after a native scalp direction is chosen and before R:R / execution:
  - **`safety.min_entry_atr`** — skip when M5 ATR is below floor (default **3.5**); journal **`entry_quality_atr`**.
  - **`safety.entry_quality_bars`** (default **3**) — average candle **body/range** ratio vs **`min_body_ratio`** (default **0.40**); journal **`entry_quality_body`**.
  - **`safety.min_directional_bars`** (default **2**) — minimum completed M5 bars agreeing with trade direction; journal **`entry_quality_direction`**.
  - **`safety.require_bb_expansion`** (default **on**) — reject when BB width contracts vs prior bar (~**5%** threshold); journal **`entry_quality_bb_contraction`**.
- **Version** **2.6.5** (`FORGE_VERSION`, `#property version`).

### Changed (config + tooling)

- **`config/scalper_config.defaults.json`** — new **`safety.*`** keys above; regenerate with **`make scalper-env-sync`**.
- **`scripts/sync_scalper_config_from_env.py`** — **`.env`** overrides: **`FORGE_MIN_ENTRY_ATR`**, **`FORGE_ENTRY_QUALITY_BARS`**, **`FORGE_MIN_BODY_RATIO`**, **`FORGE_MIN_DIRECTIONAL_BARS`**, **`FORGE_REQUIRE_BB_EXPANSION`**.
- **`.env.example`** — documents entry-quality overrides.

### Documentation

- **`docs/FORGE_TRADING_RULES.md`**, **`docs/FORGE_JOURNAL_SQL.md`**, **`docs/DATA_CONTRACT.md`** (`forge_signals.gate_reason`), **`SKILL.md`** §8, **`SOUL.md`** — operator and AURUM context for the gate and journal reasons.

---

## [System 1.8.1] — 2026-05-07 (AURUM journal contract + BRIDGE tester gate)

### Changed (BRIDGE — `python/bridge.py`)

- **Tester journal sync to SCRIBE is off by default.** Strategy-tester SQLite files (`FORGE_journal_*_tester.db`) are **ML training data** and should be queried **in place** (agent `MQL5/Files`) so backtest history does not inflate or distort **`forge_signals`** / **`forge_journal_trades`** in **`aurum_intelligence.db`**. BRIDGE still discovers tester paths but **skips** `sync_forge_journal` / `sync_forge_journal_trades` unless **`BRIDGE_SYNC_TESTER_JOURNAL=1`** (`true`/`yes`/`on`). **Live** journals are unchanged.

### Changed (SCRIBE — `python/scribe.py`)

- **`forge_journal_trades`** — added **`run_id`** (default `0`). **Unique key** is now **`(deal_ticket, journal_source, run_id)`** so the same deal ticket can appear once per FORGE tester run without collision. Startup migration recreates the table atomically when the old **`UNIQUE(deal_ticket, journal_source)`** schema is detected.
- **`sync_forge_journal` / `sync_forge_journal_trades`** — propagate **`run_id`** from journal **`SIGNALS`** / **`TRADES`** when present (v2 journals); **`forge_signals`** gains **`run_id`** via additive **`ALTER TABLE`** when missing.

### Fixed (ea/FORGE.mq5)

- **Journal `TRADES` uniqueness** — old schema used **`deal_ticket INTEGER UNIQUE`**, which drops duplicate deals across tester runs. **`CREATE TABLE`** now uses **`UNIQUE(deal_ticket, run_id)`** with **`synced`** / **`run_id`** columns on create. **`JournalInit`** detects legacy **`deal_ticket INTEGER UNIQUE`** via **`sqlite_master`** and migrates with **`ALTER RENAME` → copy → drop** inside a transaction.

### Changed (ops / docs)

- **`scripts/diagnose_forge_journal.py`** — **`per_run`** breakdown in each journal summary (signal counts, top skips, optional TRADES stats per **`run_id`**).
- **`docs/FORGE_BRIDGE.md`** — §11 documents live vs tester journal sync and **`BRIDGE_SYNC_TESTER_JOURNAL`**.
- **`docs/DATA_CONTRACT.md`** — FORGE mirror tables: **`run_id`**, unique keys, tester sync default.
- **`docs/SCRIBE_QUERY_EXAMPLES.md`**, **`docs/FORGE_TESTER_JOURNAL_QUERIES.md`** — queries grouped by **`run_id`** for tester P&amp;L.
- **`.env.example`** — documents **`BRIDGE_SYNC_TESTER_JOURNAL`**.
- **`README.md`** — journal prompt paths under **`docs/prompts/`**; note on tester DB vs AURUM and optional re-enable flag.

### Added (tests)

- **`tests/api/test_bridge_tester_journal_sync.py`** — default skips tester DB sync; **`BRIDGE_SYNC_TESTER_JOURNAL=1`** restores behaviour.

---

## [System 1.8.0] — 2026-05-07 (FORGE 2.5.1)

### Fixed (ea/FORGE.mq5) — backtest stabilisation + logical error sprint

- **`WriteBrokerInfo()` hardcoded version** — `forge_version` was hardcoded as `"1.6.19"` instead of using the `FORGE_VERSION` constant. `broker_info.json` now always reports the actual running build version.
- **`ManageStagedNativeLegs()` guard asymmetry** — early-return guard only checked `staged_entry_enabled` but the opening path (`CheckNativeScalperSetups`) used `staged_entry_enabled || native_force_staged_scale_in`. Guard updated to match: staged legs now add correctly even when only `native_force_staged_scale_in=1` is set.
- **`WriteModeStatus()` missing fields** — `mode_status.json` now emits `scalper_mode`, `warmup_ok`, and `warmup_reason` so the operator can remotely confirm both mode inputs and warmup state without MT5 Experts tab access.
- **`InitScalperConfig()` defaults too strict** — `high_vol_apply_in_tester` and `high_vol_disable_bounce` were hardcoded `true` (matching the deployed JSON). Changed to `false` so the fail-safe (config unreadable) does not silently block tester trades.
- **iMACD buffer-2 probe permanently failing** (`ForgeNativeScalperWarmupOk`) — The warmup function probed `CopyBuffer(h_macd, 2, ...)` (MACD histogram). MT5's built-in `iMACD` only exposes buffer `0` (MACD main) and buffer `1` (signal); buffer `2` does not exist and `CopyBuffer` always returns `-1`. This caused warmup to permanently fail with reason `m5_macd_buf` on every tick, producing zero TAKEN for the entire backtest. The probe was removed for both MTF (M5/M15/M30) and H1 MACD handles. MACD is only used for `market_data.json` display (`WriteMTFBlock`) which already handles `CopyBuffer` failure gracefully as `0`.
- **Warmup bar-count check blocks fast-start** (`ForgeNativeScalperWarmupOk`) — When `ScalperTesterWarmupM5Bars=0` the operator intends "fire as soon as indicators are readable", but the old code still enforced `Bars() ≥ 70` and `SERIES_SYNCHRONIZED` checks on all timeframes before reaching the `CopyBuffer` probes. Added `do_bar_checks = !in_tester || (ScalperTesterWarmupM5Bars > 0)` gate: bar-count and sync proxy checks are now skipped in tester when `WarmupM5Bars=0`, leaving only the `CopyBuffer` readiness probes as the warmup gate.

### Added (ea/FORGE.mq5)

- **Warmup state observability** — globals `g_warmup_last_reason` (string) and `g_warmup_last_ok` (bool) track the latest warmup outcome. `WriteModeStatus()` exposes them in `mode_status.json`; the warmup failure branch in `CheckNativeScalperSetups()` now journals one `SKIP|warmup_<reason>` row per M5 bar so warmup blockers are visible in SQLite without MT5 Experts access.
- **`TESTER_RUNS` warmup inputs** (`JournalInit`) — `warmup_m5_bars` and `warmup_seconds` columns added to `TESTER_RUNS` so each tester run is traceable (which warmup setting produced which results).

### Changed (config/scalper_config.defaults.json + generated JSON)

- **Tester gate relaxations** — Three `scalper_config` flags that were blocking bounces in the tester were changed to `0` (relaxed) in `scalper_config.defaults.json` and propagated via `make scalper-env-sync`:
  - `bb_bounce.bounce_respect_adx_max_in_tester: 1 → 0` (EA uses ADX cap 99 for bounces in tester)
  - `bb_bounce.bounce_respect_h1_filter_in_tester: 1 → 0` (H1 direction filter skipped in tester)
  - `safety.high_vol_apply_in_tester: 1 → 0` (high-vol guard disabled in tester)

### Added (docs)

- **`docs/FORGE_BACKTEST_DIAGNOSTIC_COMMANDS.md`** — 11 numbered Python commands for remotely verifying warmup, mode, scalper_config gates, journal signal flow, TESTER_RUNS history, rr_too_low geometry, AURUM DB, and make targets. Includes warmup blocker reference table and Inputs checklist.

---

## [System 1.7.7] — 2026-05-06 (FORGE 2.4.6)

### Changed
- **Documentation:** **`docs/SCALPER_CONFIG_PIPELINE.md`** describes **`scalper_config.defaults.json`** → **`sync_scalper_config_from_env.py`** → **`scalper_config.json`**. Updated **`README.md`**, **`docs/WARP_FORGE_VERIFY_PROMPT.md`**, **`docs/FORGE_BRIDGE.md`**, **`docs/FORGE_TRADING_RULES.md`**, **`Makefile`** help text, **`.env.example`**, and **`sync_scalper_config_from_env.py`** module docstring so operators edit **defaults** (or mapped **`.env`** keys), not the generated JSON.
- **`VERSION` / `#property version` / `FORGE_VERSION` / `scalper_config.json`**: **2.4.5 → 2.4.6** (MQL5 **`2.46`**) so MT5 recognises the new build and logs / `market_data.json` show the updated `forge_version`.

---

## [System 1.7.6] — 2026-05-06 (scalper config 2.4.6)

### Changed
- **`config/scalper_config.json` — higher native scalper trade frequency** (hot-reload / `make forge-refresh` as usual): **`high_vol_adx_min`** 28→**40**, **`high_vol_trend_strength_min`** 0.6→**0.82**, **`high_vol_disable_bounce`** 1→**0** (stops hard-blocking BB bounces whenever `high_vol_trend` is true). **`bb_bounce`**: **`adx_max`** 35→**38**, **`rsi_buy_max`**/**`rsi_sell_min`** widened toward 50, **`bb_proximity_pct`** 25→**28**, **`bounce_require_bar0_confirm`** 0. **`bb_breakout.adx_min`** 20→**18**. **`safety`**: **`loss_cooldown_sec`** 120→**90**, **`direction_cooldown_bars`** 3→**2**. Spread / open-groups / rejection-candle / min SL unchanged. See **`docs/FORGE_TRADING_RULES.md` §7** for rollback guidance.

---

## [System 1.7.5] — 2026-05-06 (FORGE 2.4.5)

### Added
- **Per-session skip flags** (`ea/FORGE.mq5`, `config/scalper_config.json`): `skip_london`, `skip_ny`, `skip_asian` — each independently gates that session's trades. Hot-reloaded via `scalper_config.json`; all default to `0` (off, 24h trading unchanged). To skip London: set `"skip_london": 1` in `scalper_config.json` and run `make forge-compile`.
- **`ScalperSessionOK()`** updated to classify the current hour as London/NY/Asian and check the corresponding skip flag before allowing entry. Existing session-hour bounds (`london_start_utc`, `london_end_utc`, etc.) still define the classification window.

---

## [System 1.7.4] — 2026-05-06 (FORGE 2.4.4)

### Changed
- **Session filter disabled** (`config/scalper_config.json`): `london_start_utc=0`, `london_end_utc=24`, `ny_start_utc=0`, `ny_end_utc=24`, `skip_asian=false` — FORGE now evaluates setups 24 h/day. Previously London (07–12) + NY (12–24) only; Asian session was blocked entirely. Hot-reloaded via `scalper_config.json`; no live-session impact from `tester_session_filter` (remains 0).
- **FORGE VERSION bumped `2.4.3 → 2.4.4`** to force MT5 to recognise and reload the new binary.

---

## [System 1.7.3] — 2026-05-06

### Fixed (FORGE ADX — trade blocking)
- **ADX hysteresis disabled** (`ea/FORGE.mq5` line 1707): `adx_hysteresis_enabled` default changed `true → false`. ADX 25–33 is routine XAUUSD — the gate locked `g_adx_trend_regime=true` continuously, suppressing all BB bounce entries on both live and tester. Live journal confirmed 500 consecutive `no_setup` rows (ADX range 25.91–33.28, avg 29.5); tester journal showed 2.2M rows with zero `TAKEN`. Thresholds `adx_trend_enter=35.0` / `adx_trend_exit=28.0` retained in code for future re-enablement via `.env` / hot-reload if needed.

### Fixed
- **`forge_signals` idempotency** (`python/scribe.py`): added existing-row guard keyed on `(forge_id, time, symbol, journal_source)` before each INSERT — prevents duplicate signals if source `synced` flag is reset while BRIDGE is running.
- **Concurrency race — tester sync duplicates**: concurrent BRIDGE + manual terminal sync caused 500 duplicate rows (`forge_id` 65001–65500 each inserted twice). Deduplicated via `DELETE … WHERE rowid NOT IN (SELECT MIN(rowid) …)`; confirmed 0 dups post-fix. Root cause: application-level guard alone is insufficient under concurrent writers — see TODO below.

### Changed
- **`sync_forge_journal` / `sync_forge_journal_trades`** (`python/scribe.py`): batch limit is now a configurable `batch_size: int = 500` parameter (was hardcoded `LIMIT 500`). Default unchanged; `bridge.py` callers unaffected.
- **Tester journal backlog — skipped intentionally**: `FORGE_journal_XAUUSD_tester.db` (503 MB, ~2.2M rows) backlog marked `synced=1` without syncing to SCRIBE. All rows were `SKIP|no_setup` or `SKIP|rr_too_low` with zero `TAKEN` outcomes — pre-spam-fix noise with no ML value. SCRIBE tester total held at ~102,000 rows. Fresh tester runs sync cleanly going forward.
- **DB permissions**: `python/data/aurum_intelligence.db` temporarily `chmod 666` during sandbox sync; restored to `644`.

### Added
- **Focused offline tests** (`tests/services/test_scribe_forge_journal.py`): `test_scribe_db_path_resolution_rules`, `test_forge_journal_sync_tags_source_and_is_idempotent`, `test_forge_journal_sync_keeps_live_and_tester_sources_separate` — all pass, no network/MT5 required.
- **`make test-journal`** (Makefile): runs focused journal test suite via `$(PYTHON)`.

### TODO
- Add `UNIQUE INDEX ON forge_signals(forge_id, time, symbol, journal_source)` to enforce idempotency at the DB layer and eliminate the concurrency race between BRIDGE and any manual sync.

---

## [System 1.7.2] — 2026-05-06
### Added
- **SCRIBE `forge_journal_trades`** — deal-level rows mirrored from FORGE journal **`TRADES`** (History deals with FORGE magic range). Incremental sync via **`synced`** on `TRADES` (`python/scribe.py`). Tagged with **`journal_source`** (`live` \| `tester`).
- **`scripts/diagnose_forge_journal.py`** + **`make journal-diagnose`** — JSON health report: per-path `SIGNALS` / `TRADES` / `TESTER_RUNS` counts, top skip reasons, SCRIBE `forge_*` totals.

### Changed
- **SCRIBE DB path**: `SCRIBE_DB` defaults to **`python/data/aurum_intelligence.db`** relative to the **repo root** (was effectively under `python/` only; `.env` value `data/aurum_intelligence.db` still maps to the same file). Removed unused **`data/aurum_intelligence.db`** at repo root; watch/verify scripts and dashboard dep map now reference the canonical path only.
- **BRIDGE journal discovery** (`python/bridge.py`): search root now includes **`Program Files/MetaTrader 5`** (recursive `FORGE_journal_*.db`) so **Strategy Tester Agent** paths (e.g. `Tester/Agent-*/MQL5/Files/`) are found — tester journals sync to SCRIBE while BRIDGE runs.
- **BRIDGE** calls **`sync_forge_journal_trades`** alongside **`sync_forge_journal`** every 60s per discovered DB.
- **Journal diagnose UX**: when no FORGE journal DBs are discovered, `scripts/diagnose_forge_journal.py` now emits a human-readable stderr note while keeping JSON on stdout and exit status 0.
- **Journal sync return semantics**: `Scribe.sync_forge_journal()` now returns processed source rows, including duplicate rows marked synced after the SCRIBE idempotency guard; use SCRIBE table counts for inserted-row/idempotency assertions.

### Operations
- **Tester journal backlog gate**: before any bulk tester sync, run `make journal-diagnose`, count unsynced tester `SIGNALS` directly, snapshot SCRIBE `forge_signals` by `journal_source`, and confirm duplicate audits for `(forge_id,time,symbol,journal_source)` and `(deal_ticket,journal_source)` are zero. On 2026-05-06 the sync remains gated pending operator decision; no bulk sync was triggered by this review pass.

### Documentation
- **`README.md`**, **`docs/SCRIBE_QUERY_EXAMPLES.md`**, **`schemas/scribe_query_examples.json`**, **`docs/DATA_CONTRACT.md`**, **`docs/FORGE_JOURNAL_ML_PROMPT.md`** — consolidated ML data guidance (SCRIBE as primary; raw journal optional).
- **`docs/FORGE_JOURNAL_SQL.md`** — SQL cookbook for **skipped** / **TAKEN** journal rows (`forge_signals` + raw `SIGNALS`); linked from README and SCRIBE query examples.

## [2.4.3] — 2026-05-06
### Fixed
- **Journal spam**: `no_setup` and **`rr_too_low`** `SIGNALS` rows were written **every tick** when the condition persisted (millions of redundant rows, unusable for ML). Now **at most one row per M5 bar** for each (aligned with throttled `no_setup` logging).
- **`JournalImportTrades()`** (`ea/FORGE.mq5`): replaced prepared-statement `INSERT` with **`DatabaseExecute`** + SQL text (same class of Strategy Tester reliability issue as `SIGNALS`). **`TRADES.synced`** column + index for SCRIBE incremental import (idempotent `ALTER TABLE` on init).
- **Execution failures**: if all legs fail to open (`opened <= 0`), journal records **`SKIP` / `execution_failed`** (was silent).

## [System 1.7.0] — 2026-05-06
### Changed
- **Versioning overhaul**: introduced `SYSTEM_VERSION` file for Python services (separate from FORGE `VERSION`). `bridge.py` and `athena_api.py` now read version from file at startup — no more hardcoded version strings.
- Updated `SOUL.md` — FORGE v2.4.1 features: SL quality rules, native indicators (VWAP, Fibonacci, RSI divergence, PSAR), signal journal, dynamic leg count 1–30.
- Updated `SKILL.md` §8 — full native scalper documentation: SL layers, `.env` hot-reload keys, indicator catalog, trade frequency tuning.
- Updated `README.md` — version header, SCRIBE table count (14), FORGE v2.4.1 feature summary, two-file versioning docs.

## [System 1.7.1] — 2026-05-06
### Added
- **`docs/FORGE_JOURNAL_ML_PROMPT.md`** — implementation blueprint for journal-based **missed-setup analysis** (MFE/MAE, gate accuracy), optional **scikit-learn setup scorer** training (walk-forward validation), and future **AUTO_SCALPER** / **AEGIS** integration. References MQL5 articles 19065/18985/14910 and practical XAUUSD ML patterns.
- **SCRIBE `forge_signals.journal_source`** — column (default `live`) with auto-migration; tags rows synced from live (`FORGE_journal_<sym>.db`) vs Strategy Tester (`FORGE_journal_<sym>_tester.db`) journals (`python/scribe.py`).

### Changed
- **BRIDGE journal sync** (`python/bridge.py`): resolves **both** live Common-Files and local tester journal paths (same discovery rules as MT5/Wine layout), calls `sync_forge_journal(..., source="live"|"tester")` per file.
- **Drawdown guard vs Strategy Tester** (`python/bridge.py`): `_check_drawdown()` returns early when `market_data` reports `strategy_tester` — avoids false WATCH transitions when tester virtual balance differs from live peak equity. One-shot log + HERALD notice when tester mode is detected.
- **Operational visibility** (`python/bridge.py`, `python/athena_api.py`): `strategy_tester` written to `status.json` and exposed on **`GET /api/live`** so ATHENA shows tester runs distinctly from live.

### Documentation
- Updated **`README.md`**, **`SOUL.md`**, **`SKILL.md`** — FORGE **v2.4.2**, journal tester/live split, `journal_source`, tester drawdown bypass, link to journal ML prompt.

## [2.4.2] — 2026-05-06
### Fixed
- **Signal journal in Strategy Tester** (`ea/FORGE.mq5`):
  - When `MQL_TESTER` is active, journal DB is **`FORGE_journal_<SYMBOL>_tester.db`** under the terminal’s **local** `MQL5/Files` tree (writable in the tester sandbox), not Common Files — recovered skipped/taken rows that previously never persisted in backtests.
  - **`SIGNALS` inserts** use **`DatabaseExecute`** with formatted SQL (MT5 tester proved unreliable for prepared-statement + `DatabaseRead` on `INSERT` in some builds).
  - **Skip coverage:** `no_setup` and **`rr_too_low`** paths now call `JournalRecordSignal()` so high-volume skip reasons appear in the DB and sync to SCRIBE.

### Added
- **`TESTER_RUNS`** table in the tester journal DB — one metadata row per backtest run (start time, symbol, balance, `FORGE_VERSION`, scalper mode string).

## [2.4.1] — 2026-05-06
### Fixed
- **SL placement quality overhaul** (`ea/FORGE.mq5`):
  - `FindStructuralSL()` was selecting the **tightest** OB zone (nearest to entry), overriding ATR-based SL with dangerously close stops (e.g., 4.2 pts when ATR = 10.6). Fixed: structural SL can now only **widen** the stop (further from entry), never tighten it.
  - `bounce_sl_atr_mult` / `breakout_sl_atr_mult` were never parsed from `scalper_config.json` — stuck at hardcoded defaults (1.2/1.5). Added JSON parsing from `bb_bounce` and `bb_breakout` sections.
  - Added `min_sl_atr_mult` floor (default 0.8): SL can never be closer than 0.8×ATR from entry, regardless of structural SL. Applies to both bounce and breakout entries.
  - Added per-trade SL diagnostic logging (`FORGE SL CALC`) showing entry, SL, distance, ATR, multiplier, and OB zone count.

### Changed
- **Trade frequency tuning** (`config/scalper_config.json`):
  - `max_trades_per_session`: 3 → 100 (effectively uncapped — scalper trades every valid setup)
  - `max_open_groups`: 2 → 4 (more concurrent groups)
  - `loss_cooldown_sec`: 300 → 120 (2 min recovery for scalper pace)
  - `direction_cooldown_bars`: 6 → 3 (15 min instead of 30 min before opposite direction)
  - `bb_proximity_pct`: 20 → 25 (wider entry zone near BB bands)
  - `adx_max`: 30 → 35 (bounces in slightly trendier markets)
  - `rsi_buy_max`: 45 → 48, `rsi_sell_min`: 55 → 52 (wider RSI window)
  - `bounce_min_candle_score`: 1 → 0 (other filters provide sufficient confirmation)
- **Lot sizing cap** raised from 20 to 30 legs across all EA code paths.
- Removed dead `mode` and `risk_pct` fields from `lot_sizing` config.
- New `.env` overrides: `FORGE_MIN_SL_ATR_MULT`, `FORGE_BOUNCE_SL_ATR_MULT`, `FORGE_BREAKOUT_SL_ATR_MULT`.

## [2.4.0] — 2026-05-06
### Added
- **Native SQLite signal journal** (`ea/FORGE.mq5`, `config/scalper_config.json`, `.env.example`, `scripts/sync_scalper_config_from_env.py`, `python/scribe.py`, `python/bridge.py`):
  - Ref: [MQL5 Article 22009 — "Algorithmic Trading Without the Routine: Quick Trade Analysis in MetaTrader 5 with SQLite"](https://www.mql5.com/en/articles/22009)
  - FORGE now writes a local SQLite database (`FORGE_journal_XAUUSD.db`) in MT5 Common Files, recording **every setup evaluation** — both taken trades and skipped signals — with full indicator context at the moment of decision.
  - **SIGNALS table**: Records time, symbol, setup_type, direction, outcome (TAKEN/SKIP), gate_reason, and a snapshot of price, spread, ATR, RSI, ADX, Bollinger Bands, POC, VWAP, Fibonacci, RSI divergence, PSAR state, candle score, H1 trend, regime, session, and magic number. Includes `synced` column for Python pipeline integration.
  - **TRADES table**: Periodically imports MT5 deal history (configurable depth) using `HistorySelect()`/`HistoryDealGetTicket()`, keyed by `deal_ticket` (INSERT OR IGNORE for idempotence).
  - **STATS_CACHE table**: Self-computes hourly win rate, PnL, trade count, and gate-reason frequency at configurable intervals. Enables on-chart analytics without external tools.
  - **Gate instrumentation**: `JournalRecordSignal()` calls at every exit point in `CheckNativeScalperSetups()` — session_off, spread, open_groups, session_trade_cap, cooldown, direction_cooldown, m1, regime_countertrend — plus TAKEN on successful execution.
  - **SCRIBE sync**: New `forge_signals` table in `aurum_intelligence.db`. `Scribe.sync_forge_journal()` reads unsynced rows from FORGE's journal, inserts them, and marks them `synced=1`. BRIDGE calls sync every 60s via `_resolve_forge_journal_path()`.
  - New `.env` overrides: `FORGE_JOURNAL_ENABLED`, `FORGE_JOURNAL_RECORD_SKIPS`, `FORGE_JOURNAL_IMPORT_TRADES`, `FORGE_JOURNAL_IMPORT_DEPTH_DAYS`, `FORGE_JOURNAL_STATS_INTERVAL_SEC`. All hot-reloadable.

## [2.3.1] — 2026-05-06
### Added
- **Trade quality & survival improvements** (`ea/FORGE.mq5`, `config/scalper_config.json`, `.env.example`, `scripts/sync_scalper_config_from_env.py`):
  Ref: Backtesting diagnosis — fast SL hits (4-minute whipsaws) from tight SL, aggressive ratchet, and missing tester-mode guards.
  1. **Configurable tester session filter**: `ScalperTesterSessionOK()` lets users optionally apply session filtering in Strategy Tester via comma-separated session list (`tester_session_filter`, `tester_allowed_sessions`). Default off (trades all sessions).
  2. **Tester cooldown enabled**: Loss cooldown now applies in tester too (`tester_cooldown_enabled`), preventing rapid opposite-direction whipsaw after a loss. Default on.
  3. **Wider bounce SL**: `sl_atr_mult` default changed from 1.2 to 1.5 — ~25% more breathing room for M5 XAU.
  4. **Longer fast-lock hold**: `fast_lock_min_hold_sec_bounce` default changed from 45s to 90s — lets bounce setups develop 1–2 M5 candles before ratcheting.
  5. **Directional anti-whipsaw cooldown**: `ScalperDirectionCooldownOK()` prevents BUY→SELL flip within configurable N M5 bars (`direction_cooldown_enabled`, `direction_cooldown_bars`). Default 6 bars (30 min). Logged as `skip gate=direction_cooldown`.
- New `.env` overrides: `FORGE_TESTER_SESSION_FILTER`, `FORGE_TESTER_ALLOWED_SESSIONS`, `FORGE_TESTER_COOLDOWN_ENABLED`, `FORGE_DIRECTION_COOLDOWN_ENABLED`, `FORGE_DIRECTION_COOLDOWN_BARS`. All hot-reloadable.
- Sync script `_parse_value()` now supports `"string"` type for `tester_allowed_sessions`.

## [2.3.0] — 2026-05-06
### Added
- **Parabolic SAR state tracking** (`ea/FORGE.mq5`, `config/scalper_config.json`, `scripts/sync_scalper_config_from_env.py`, `python/bridge.py`, `python/lens.py`, `python/scribe.py`):
  - Ref: [MQL5 Article 17234 — "Parabolic Stop and Reverse Tool" by Christian Benjamin](https://www.mql5.com/en/articles/17234)
  - Native `DetectPSARState()` creates an `iSAR` handle on M5 and detects five states: `FLIP_BULL`, `FLIP_BEAR`, `BELOW`, `ABOVE`, `NONE`. Throttled to once per M5 bar.
  - **Informational only** — PSAR state is logged and streamed through the full data pipeline but does **not** gate or block any entries. Purely data collection to evaluate whether PSAR flips correlate with higher win rates before promoting to a gate.
  - **Journal log**: `PSAR=` field in every trade entry Print. Flip events logged with `FORGE PSAR:` prefix.
  - **Data pipeline**: `psar_state` field in `market_data.json`, `scalper_entry.json`, BRIDGE activity log, BRIDGE open_context, SCRIBE `market_snapshots` (TEXT column with auto-migration), and LENS pass-through.
  - **Telegram alerts**: `PSAR: FLIP_BULL` (or `FLIP_BEAR`) appended to FORGE scalp entry notifications only when a flip is active at entry time.
  - New `.env` overrides: `FORGE_PSAR_ENABLED`, `FORGE_PSAR_STEP`, `FORGE_PSAR_MAXIMUM`. All hot-reloadable.

## [2.2.0] — 2026-05-06
### Added
- **RSI divergence detection** (`ea/FORGE.mq5`, `config/scalper_config.json`, `scripts/sync_scalper_config_from_env.py`, `python/bridge.py`, `python/lens.py`, `python/scribe.py`):
  - Ref: [MQL5 Article 17198 — "RSI Sentinel Tool" by Christian Benjamin](https://www.mql5.com/en/articles/17198)
  - Native `DetectRSIDivergence()` scans M5 RSI and price for four divergence types: Regular Bullish, Regular Bearish, Hidden Bullish, Hidden Bearish. Throttled to once per M5 bar.
  - **Bounce entry gate**: counter-trend regular divergence blocks bounce entries (`REG_BEAR` blocks buy, `REG_BULL` blocks sell). Hidden divergences and NONE pass through. Breakout entries are never gated.
  - **Chart visualization**: `DrawDivergenceArrow()` draws green (bullish) or red (bearish) arrows on the chart only when divergence contributes to an actual trade entry.
  - **Journal log**: `RSI_DIV=` field in every trade entry Print.
  - **Data pipeline**: `rsi_divergence` field in `market_data.json`, `scalper_entry.json`, BRIDGE activity log, BRIDGE open_context, SCRIBE `market_snapshots` (TEXT column with auto-migration), and LENS pass-through.
  - **Telegram alerts**: `DIV: REG_BULL` (or similar) appended to FORGE scalp entry notifications when divergence is present.
  - New `.env` overrides: `FORGE_RSI_DIV_ENABLED`, `FORGE_RSI_DIV_LOOKBACK`, `FORGE_RSI_DIV_SWING_BARS`, `FORGE_RSI_DIV_MIN_RSI_DIFF`, `FORGE_RSI_DIV_DRAW_ARROWS`. All hot-reloadable.

## [2.1.0] — 2026-05-06
### Added
- **Fibonacci swing retracement** (`ea/FORGE.mq5`, `config/scalper_config.json`, `scripts/sync_scalper_config_from_env.py`, `python/bridge.py`, `python/lens.py`, `python/scribe.py`):
  - Ref: [MQL5 Article 17121 — "External Flow (III) TrendMap"](https://www.mql5.com/en/articles/17121)
  - Native `ComputeFibonacciSwing()` computes swing high/low and Fib 38.2%, 50%, 61.8% levels from M5 lookback (60s throttle, reuses `vp_lookback` by default).
  - **Directional bias gate**: VWAP-vs-Fib50 optional confirmation for bounce entries (`fib_bias_enabled`). When VWAP < Fib50, sell bias; VWAP > Fib50, buy bias. Breakouts unaffected.
  - **Fib TP targeting**: Fib 38.2% and 61.8% as intermediate TP candidates for bounce entries (`fib_tp_enabled`).
  - All Fib levels flow through `market_data.json` (`volume_profile` section), `scalper_entry.json`, BRIDGE, LENS, and SCRIBE `market_snapshots` (`fib_50`, `fib_382`, `fib_618` columns with auto-migration).
  - New `.env` overrides: `FORGE_FIB_BIAS_ENABLED`, `FORGE_FIB_TP_ENABLED`, `FORGE_FIB_LOOKBACK`. All hot-reloadable.
- **Single-source versioning** (`VERSION`, `scripts/compile_forge_ea_macos.sh`, `scripts/sync_scalper_config_from_env.py`):
  - New `VERSION` file at repo root — the single source of truth for all version stamps.
  - Compile script reads `VERSION` and stamps both `FORGE_VERSION` constant and `#property version` in `ea/FORGE.mq5` before compilation.
  - Sync script reads `VERSION` and stamps `scalper_config.json` version field automatically.
  - To bump: `echo "X.Y.Z" > VERSION && make forge-compile` — no manual edits needed anywhere else.

## [2.0.0] — 2026-05-06
### Added
- **FORGE Scalper V2** — 7 new features (`ea/FORGE.mq5`, `config/scalper_config.json`, `python/lens.py`, `python/bridge.py`, `python/scribe.py`):
  1. **Stricter H1 filter** (`bounce_require_h1_direction`): H1 flat no longer allows bounce entries when enabled.
  2. **Multi-candle bar-0 confirmation** (`bounce_require_bar0_confirm`): requires current price moving away from the band.
  3. **Candlestick pattern scoring** (`ScalperCandlePatternScore()`): Hammer/Shooting Star (2), Engulfing (3), Basic (1) replace simple bullish/bearish check. Gated by `bounce_min_candle_score`.
  4. **Volume Profile + POC** (`ComputeVolumeProfile()`): native M5 tick-volume POC computed every 60s.
  5. **VWAP** (added to `ComputeVolumeProfile()`): typical-price * volume VWAP alongside POC for dual volume-based reference levels.
  6. **Structural SL/TP using POC + VWAP + OB zones**: `FindStructuralSL()` places SL beyond nearest OB zone; `NearLiquidityZone()` checks proximity to POC, VWAP, or OB zones; POC/VWAP used as intermediate TP targets.
  7. **Breakout retest state machine** (`BreakoutRetest` struct): arms retest instead of immediate entry when `breakout_use_retest` enabled; `BB_BREAKOUT_RETEST` setup type with configurable `breakout_retest_max_bars`.
  - LENS writes OB zones to `ob_zones.json` for FORGE consumption.
  - All V2 params hot-reloadable via `scalper_config.json` without recompilation.
  - New `.env` overrides for all V2 params with `sync_scalper_config_from_env.py` mappings.
- **SCRIBE `market_snapshots` VP columns**: `poc_price`, `vwap_price` with auto-migration. BRIDGE flattens `volume_profile` from `market_data.json` and passes through LENS to SCRIBE.
- **`market_data.json` `volume_profile` section**: `poc_price`, `poc_strength`, `vwap_price` (and Fib levels in 2.1.0).
- **`scalper_entry.json` V2 fields**: `poc_price`, `vwap_price`, `pattern_score` carried through BRIDGE to SCRIBE `open_context`.

### Changed
- **FORGE version**: bumped to `v2.0.0` (`FORGE_VERSION` constant + `#property version`).
- **`scalper_config.json` version**: bumped to `"2.0"`.
- **Fixed duplicate `forge_version`** in `WriteMarketData()`: removed hardcoded `"1.6.19"` that was silently overriding the `FORGE_VERSION` constant.
- **`sync_scalper_config_from_env.py`**: now always copies updated config to `MT5/scalper_config.json` after writing, ensuring MT5 picks up changes without recompilation.
- **`BB_BREAKOUT_RETEST` parity**: auto-lot and `move_be_on_tp1` logic now correctly treats retest entries as breakout setups. `ManageOpenGroups` fast-lock matches both `BB_BREAKOUT` and `BB_BREAKOUT_RETEST` comments.

## [Unreleased]

### Added
- **SCRIBE `trade_groups.open_context`** (`python/scribe.py`, `python/bridge.py`): JSON attribution snapshot at group open (regime + compact MT5 + optional AEGIS fields + `extra` per source). Toggle **`BRIDGE_OPEN_CONTEXT_ENABLE`**; size cap **`SCRIBE_OPEN_CONTEXT_MAX_BYTES`**. Migration is additive. Tests: `tests/services/test_scribe_open_context.py`. Example query: `docs/SCRIBE_QUERY_EXAMPLES.md`.

### Changed
- **Scalper regime roadmap — Phases D–F** (`python/bridge.py`, `python/aegis.py`, `python/aurum.py`, tests, `docs/AEGIS.md`, `docs/SCRIBE_QUERY_EXAMPLES.md`, `.env.example`):
  - **Phase D:** `FORGE_NATIVE_SCALP` groups logged to SCRIBE now carry **`regime_*`** fields from the BRIDGE regime snapshot; `FORGE_SCALP_*` system events include a compact regime audit fragment.
  - **Phase E (optional):** **`AEGIS_REGIME_LOT_SCALE_ENABLED`** applies an extra lot-scale multiplier after streak-based scaling when regime label/confidence align (or dampen in RANGE/VOLATILE). Capped by **`AEGIS_SCALE_COMBINED_MAX`**. Default **off**.
  - **Phase F:** AURUM **`_build_context`** and BRIDGE **`AUTO_SCALPER`** AURUM prompts include the **`status.json`** regime block and counter-trend caution when policy is active.

- **FORGE high-volatility trend guard** (`ea/FORGE.mq5`): added live-focused guardrails for trend bursts to reduce loss clusters during volatile runs. New `scalper_config.json` safety keys:
  - `high_vol_trend_guard_enabled`,
  - `high_vol_adx_min`,
  - `high_vol_trend_strength_min`,
  - `high_vol_disable_bounce`,
  - `high_vol_require_h1_h4_breakout_align`,
  - `high_vol_breakout_sl_boost`.
- Behavior in live mode now:
  - suppresses `BB_BOUNCE` entries during confirmed high-vol trend regimes (when enabled),
  - requires stricter H1+H4 alignment for breakouts during those regimes (when enabled),
  - widens breakout SL by configurable multiplier during those regimes to reduce premature stop-outs.
- Added high-vol breakout ratchet dampening keys to reduce fast stop-outs:
  - `high_vol_fast_lock_extra_hold_sec`,
  - `high_vol_fast_lock_trigger_mult`,
  - `high_vol_fast_lock_trail_mult`.
  In high-vol trend regimes, breakout legs now wait longer before fast-lock engages, require deeper favorable progress before ratcheting, and trail with more breathing room.
- Added fast-lock net-profit guards to avoid "locked then loss" exits in volatile spread conditions:
  - `fast_lock_min_profit_points`,
  - `fast_lock_spread_guard_mult`.
  Fast-lock SL now enforces a minimum profit floor relative to entry (BUY above entry / SELL below entry) that scales with live spread, reducing negative SL_HIT outcomes after ratchet.
- **Tester ratchet stabilization + high-vol guard parity**:
  - `python/bridge.py`: disables BRIDGE `PROFIT_RATCHET` when `strategy_tester=true` to avoid frequent `Invalid stops` modify artifacts in tester runs.
  - `ea/FORGE.mq5` + `config/scalper_config.json`: added `high_vol_apply_in_tester` and enabled it by default so high-vol trend bounce suppression applies consistently in Strategy Tester diagnostics.
- **SCRIBE live watcher utility** (`scripts/watch_scribe_live.py`, `Makefile`, `docs/FORGE_TRADING_RULES.md`):
  - Added `make scribe-watch` for real-time `trade_groups`/`trade_closures`/`system_events` monitoring.
  - Added `make scribe-watch-log` to append watcher output into `logs/scribe_watch.log` for post-run review.
  - Added utility usage and review commands to the trading rules documentation.
- **FORGE ADX hysteresis anti-fade gate + SELL grace hold** (`ea/FORGE.mq5`, `config/scalper_config.json`):
  - Added deterministic M5 ADX regime state with hysteresis (`adx_trend_enter`, `adx_trend_exit`, tester toggle) so `BB_BOUNCE` is blocked while ADX is in a trend regime and only re-enabled after cooldown.
  - Added balanced SELL adverse grace window (`sell_loss_grace_sec`, `sell_loss_grace_adverse_points`) that defers ratchet/BE management during early adverse motion without widening SL.
  - Added explicit regime transition and bounce-skip diagnostics for backtest/live verification.

---

## [1.6.19] — 2026-05-02
### Changed
- **FORGE deterministic anti-fade control** (`ea/FORGE.mq5`, `config/scalper_config.json`, `.env.example`, `scripts/sync_scalper_config_from_env.py`):
  - Added M5 ADX hysteresis regime (`adx_trend_enter`/`adx_trend_exit`) to hard-block `BB_BOUNCE` while in trend regime and re-enable only after ADX cooldown.
  - Added balanced SELL adverse grace hold (`sell_loss_grace_sec`, `sell_loss_grace_adverse_points`) that defers ratchet/BE actions in early adverse motion without widening SL.
  - Added `.env` sync support for new hysteresis/grace safety knobs.
- **Version alignment to current release**: FORGE runtime-reported `forge_version` is now **`1.6.19`** in `market_data.json` and `broker_info.json`.

---

## [1.6.17] — 2026-05-02
### Changed
- **FORGE native bounce confirmation + risk controls** (`ea/FORGE.mq5` **v1.6.17**):
  - BB_BOUNCE confirmation is now configurable from `scalper_config.json`:
    - `bounce_reclaim_pct` (0..100, default 20),
    - `bounce_require_rejection_candle` (0/1, default 1).
  - Bounce entries still avoid first-touch catches, but operators can now tune confirmation strictness without recompiling.
- **Ratchet telemetry / hold controls** (`ea/FORGE.mq5`): `ReadScalperConfig()` now prints active bounce confirmation and fast-lock profile (`fast_lock_min_hold_sec_bounce`, `fast_lock_min_hold_sec_breakout`) for runtime auditability.
- **Trend auto-lot guardrails + observability** (`ea/FORGE.mq5`):
  - multiplier remains hard-bounded to `1.0..5.0`,
  - trend reference clamped to `>=0.10`,
  - entry logs now include trend context,
  - `scalper_entry.json` now includes `lot_multiplier`, `auto_lot_*` inputs and derived trend ratio values.

### Documentation
- Updated `docs/FORGE_TRADING_RULES.md` and `docs/DATA_CONTRACT.md` with safe live defaults and expanded scalper-entry decision fields.

---

## [1.6.11] — 2026-05-02
### Fixed
- **FORGE Strategy Tester reliability** (`ea/FORGE.mq5` **v1.6.11**): Native scalper backtests no longer stall behind live-only gates. In **`MQL_TESTER`**, FORGE keeps EA Inputs authoritative (ignores live `config.json` mode/scalper/regime overrides), skips live-only session/spread/sentinel blocks, and avoids stale-feed false positives via **`strategy_tester`** + Python mtime freshness enrichment.
- **Backtest trade generation** (`ea/FORGE.mq5`): Added Tester-only relaxed entry profile so test runs produce fills for diagnostics: looser ADX/trend/buffer/proximity thresholds, optional breakout M15 requirement off, R:R floor eased to 1.0, M1 gate bypassed, and session trade-cap/cooldown bypassed. **Live behavior remains strict**.
- **Tester diagnostics / operator clarity** (`ea/FORGE.mq5`): Journal now prints explicit Strategy Tester startup context and clearer "no setup" hints. Repeated per-tick spam is throttled to once per M5 bar, and unchanged `scalper_config.json` no longer re-logs every reload cycle.
- **Session default alignment** (`ea/FORGE.mq5`): native default NY session end aligned to **24 UTC** (matching `config/scalper_config.json`) to avoid silent 20:00-23:59 UTC shutoff when config is unavailable.

### Changed
- **Version alignment to current release**: FORGE runtime-reported `forge_version` is now **`1.6.11`** in `market_data.json` and `broker_info.json`.

---

## [1.6.5] — 2026-05-02
### Fixed
- **Strategy Tester vs BRIDGE staleness:** In the Tester, FORGE wrote **`timestamp_unix`** from **simulated** **`TimeGMT()`**, so Python treated **`market_data.json`** as years stale → **circuit breaker** + ATHENA **“MT5 data stale”** while you backtested. **FORGE v1.6.5** adds **`"strategy_tester":true`** to **`market_data.json`** when **`MQL_TESTER`** is active. **`python/market_data.py`** **`enrich_mt5_for_stale_check()`** uses **file mtime** for age when that flag is set; **`bridge.py`** and **`athena_api.py`** apply it before staleness / **`/api/live`**. Tests: **`tests/services/test_market_data_strategy_tester.py`**.

---

## [1.6.4] — 2026-05-02
### Fixed
- **FORGE** (`ea/FORGE.mq5` **v1.6.4**): In **Strategy Tester** (`MQL_TESTER`), **`ReadConfig()`** no longer applies **`effective_mode`**, **`scalper_mode`**, or **`regime_*`** from **`config.json`**. Stale live **`config.json`** (e.g. **`effective_mode`** **`WATCH`** when BRIDGE circuit breaker / sentinel, **`scalper_mode`** **`NONE`**) was overriding EA **Inputs** every tick and blocking native scalper backtests. Threshold fields (**`pending_entry_threshold_points`**, etc.) still load from **`config.json`** when present. **`forge_version`** **1.6.4**.

---

## [1.6.2] — 2026-05-02
### Fixed
- **FORGE** (`ea/FORGE.mq5` **v1.6.2**): **`ReadAndExecuteCommand`** — parse and trim **`action`** before timestamp dedup; **do not advance `g_last_cmd_ts`** when **`action`** is empty (avoids torn reads during atomic **`command.json`** writes skipping the real command). **`MODE_CHANGE`**, **`HEALTH_CHECK`**, **`SHELL_EXEC`**, **`AEB`**, **`AURUM_EXEC`**, **`OPEN_TRADE`** are **ignored** (they belong in **`aurum_cmd.json`**, not FORGE) instead of **`Unknown action`**. Actions matched case-insensitively after **`StringToUpper`**.

---

## [1.6.1] — 2026-05-02
### Changed
- **FORGE** (`ea/FORGE.mq5` **v1.6.1**): optional **M1** gate for native scalper — input **`NativeScalperM1Mode`**: **`NONE`** (default), **`CONFIRM`** (M1 EMA/ATR alignment vs **`trend_strength_atr_threshold`**), **`TRIGGER`** (**CONFIRM** plus direction of **prior closed M1 bar**). H1/H4/regime remain **bias-only**; **M5** remains the setup timeframe. **`market_data.json`**: **`indicators_m1`**; **`scalper_entry.json`**: **`native_scalper_m1_mode`**, **`m1_trend_strength`**, **`m1_prior_close`**, **`m1_prior_open`**. Operator: **`make forge-compile`**; **`forge_version`** **1.6.1**.
- Repo **release label** **1.6.1**: **`python/bridge.py`** `VERSION`, **`README.md`**, **`.env.example`**, **`python/athena_api.py`** default.

---

## [1.6.0] — 2026-05-04
### Changed
- **Phase C (FORGE native scalper + BRIDGE config bus)** (`ea/FORGE.mq5` **v1.6.0**): Native BB bounce/breakout setups optionally require **H4** EMA20/50 vs ATR trend alignment (same ATR-normalized threshold as H1) via input **`NativeScalperH4Align`** (default **true**). When **`regime_*`** in **`MT5/config.json`** indicates active entry policy and confidence ≥ min, input **`NativeScalperRegimeGate`** (default **true**) blocks **SELL** vs **`TREND_BULL`** and **BUY** vs **`TREND_BEAR`**, aligned with Python **AEGIS** Phase B. **`market_data.json`** adds **`indicators_h4`**; **`broker_info.json`** / **`market_data.json`** report **`forge_version` `1.6.0`**; **`scalper_entry.json`** adds **`h4_trend_strength`**.
- **`python/bridge.py`**: **`_write_config()`** now includes **`regime_label`**, **`regime_confidence`**, **`regime_apply_entry_policy`** (0/1), **`regime_countertrend_min_confidence`** (from **`AEGIS_REGIME_COUNTERTREND_MIN_CONFIDENCE`**). **`_write_status()`** calls **`_write_config()`** each loop so FORGE sees a fresh regime snapshot without restarting BRIDGE. Test: **`tests/api/test_bridge_config_regime.py`**. Operator: **`make reload-bridge`** after deploy; **`make forge-compile`** after pulling EA changes.

### Documentation
- **`docs/FORGE_TRADING_RULES.md`**, **`docs/FORGE_BRIDGE.md`**, **`docs/DATA_CONTRACT.md`**, **`docs/SCALPER_REGIME_PHASED_PLAN.md`** — Phase C behaviour and **`config.json`** keys.

---

## [1.5.7] — 2026-05-03
### Changed
- **Phase B (regime counter-trend gate)** (`python/aegis.py`): optional **`REGIME_COUNTERTREND:*`** rejection when **`regime_context.apply_entry_policy`** is true (`REGIME_ENTRY_MODE=active`) and the trade **fades** a high-confidence **`TREND_BULL`** / **`TREND_BEAR`** label (SELL in bull, BUY in bear). Default gated sources: **`SCALPER_SUBPATH_DIRECT`** only — configurable via **`AEGIS_REGIME_COUNTERTREND_SOURCES`**, **`AEGIS_REGIME_COUNTERTREND_BLOCK`**, **`AEGIS_REGIME_COUNTERTREND_MIN_CONFIDENCE`**. Shadow/off regime modes leave **`apply_entry_policy`** false so this guard stays inactive. Tests: **`tests/services/test_aegis_regime_countertrend.py`**. Operator: **`make reload-bridge`**.
- **Phase A (scalper + AEGIS)** (`python/bridge.py`): BRIDGE LENS-driven scalper (`_scalper_logic`, `SCALPER_SUBPATH_DIRECT`) now calls **`Aegis.validate()`** with `mt5_data`, **`regime_context`**, and **`current_price`** before `OPEN_GROUP`. Rejections emit **`SCALPER_REJECTED`** activity (`gate: AEGIS`). Approved rows persist **`regime_*`** on `trade_groups`, **`update_group_open_meta`** entry-zone pips, **`herald.trade_group_opened`**, and FORGE commands use **`approval.entry_ladder`** / **`approval.lot_per_trade`** / **`approval.num_trades`**. (`python/aegis.py`): fixed-lot mode respects **`SCALPER_SUBPATH_DIRECT`** alongside other fixed sources. Tests: **`tests/api/test_scalper_aegis_gate.py`**. Operator: **`make reload-bridge`** after deploy.

### Documentation
- Added **[docs/SCALPER_REGIME_PHASED_PLAN.md](docs/SCALPER_REGIME_PHASED_PLAN.md)** — phased roadmap for aligning self-scalping (BRIDGE LENS, FORGE native, AUTO_SCALPER) with regime/trend gates, Makefile verify/restart steps, MT5 Strategy Tester backtesting orientation, testing checklist per phase, copy-paste execution prompts, and documentation touch-points (`README`, `ARCHITECTURE`, `AEGIS`, `DATA_CONTRACT`, `SOUL`, `SKILL`, changelog, architecture diagram when flows change). Includes risk framing for lot scaling vs martingale-style recovery.

---
## [1.5.6] — 2026-05-02
### Phase 3 cleanup sprint
- **M1** (`python/listener.py`): added post-parse `ENTRY` range validation after text/vision merge and before dispatch. LISTENER now drops malformed signals with a WARNING when entry bounds are missing/non-positive, `entry_low > entry_high`, `sl <= 0`, `tp1 <= 0` when present, or XAU/GOLD `entry_low` falls outside `1000..99999`. Tests: `tests/services/test_signal_range_validation.py`.
- **M2** (`python/reconciler.py`, `python/bridge.py`, `.env.example`): centralised FORGE magic range configuration with `FORGE_MAGIC_NUMBER` + `FORGE_MAGIC_MAX`, added reconciler startup assertion, and replaced the hardcoded reconciler range check with the shared env-driven bounds. Tests: `tests/services/test_reconciler_magic_range.py`.
- **M4** (`python/sentinel.py`): added ForexFactory parse-zero fail-safe alerting. During weekday 06:00–20:00 UTC, a zero-event parse now logs WARNING and sends the Herald/Telegram alert `⚠️ SENTINEL: ForexFactory returned 0 events during trading hours — possible markup change or parse failure`; weekends and off-hours stay quiet. Tests: `tests/services/test_sentinel_parse_zero.py`.
- **M5** (`python/sentinel.py`, `requirements.txt`): replaced fixed Eastern→UTC offset arithmetic with DST-aware `America/New_York` conversion using `pytz` when installed, with a standard-library fallback for pre-upgrade environments. July `8:30am` maps to `12:30 UTC`; January `8:30am` maps to `13:30 UTC`. Tests: `tests/services/test_sentinel_parse_zero.py`.
- **M6** (`python/contracts/aurum_forge.py`): added OPEN_GROUP cross-field contract checks for BUY/SELL TP/SL geometry and TP2/TP3 ordering. Tests: `tests/api/test_aurum_forge_contract.py`.
---
## [1.5.5] — 2026-05-02
### L1–L6 low-severity cleanup sprint
- **L1** (`regime.py`): detects HMM feature vector shape changes between calls, logs a WARNING with the old→new shape, and sets `feature_shape_mismatch=True` in the regime snapshot so BRIDGE can surface it. Test: `test_regime_engine_flags_hmm_feature_shape_mismatch`.
- **L2** (`aurum.py`): `SOUL.md` and `SKILL.md` are now cached at module level instead of re-read on every `ask()` call. A `SIGHUP` handler reloads the cache in-place so a running process can refresh without restart. Tests: `test_ask_uses_cached_soul_skill_without_rereading`, `test_sighup_reloads_soul_skill_cache`.
- **L3** (`regime.py`): HMM `n_components` is now read from `REGIME_HMM_COMPONENTS` (default 3, validated 2–10). `.env.example` documents the new knob. Test: `test_regime_hmm_components_env_validation`.
- **L4** (`ea/FORGE.mq5:~550`): added an explicit `(int)` cast on `tp1_close_pct`, with a comment noting fractional values are truncated by design. No logic change.
- **L5** (`.gitignore`): added `.claude/worktrees/` and `.claude/scheduled_tasks.lock` under the Agent / AI context section to prevent Claude Code runtime artifacts from being committed.
- **L6** (`python/freshness.py`): created `DATA_FRESHNESS_WINDOWS` to centralise default staleness thresholds for MT5, SENTINEL, REGIME, and LENS. `bridge.py`, `sentinel.py`, `regime.py`, `lens.py`, and `market_data.py` now import it as the env-var fallback. Test: `test_data_freshness_windows_are_defined`.
### Phase 2 reliability sprint
- **H1** (`python/config_io.py`, `bridge.py`, `listener.py`, `athena_api.py`, `reconciler.py`): added `atomic_write_json()` and routed config/file-bus JSON writes through temp-file + `os.replace` atomic writes. Tests: `test_atomic_write_json_creates_file`, `test_atomic_write_json_is_atomic`, `test_atomic_write_json_cleans_up_on_error`.
- **H3** (`python/listener.py`, `python/aurum.py`): Telegram async handlers now offload blocking file/media/vision/chat work with `asyncio.to_thread()` where the handler directly invoked synchronous work. Test: `test_no_time_sleep_in_async_handlers`.
- **H4** (`python/mcp_client.py`, `python/lens.py`, `python/aeb_executor.py`): MCP stdout reads now use `select.select(..., timeout=15)` and raise `MCPTimeoutError` after killing the process; LENS subprocess calls use 15s timeouts and return stale data with `stale=True` on timeout; AEB shell/health default timeouts are 10s and log `AEB exec slow` above 5s. Tests: `test_mcp_client_raises_on_timeout`, `test_lens_returns_stale_on_subprocess_timeout`.
- **M3** (`bridge.py`, `athena_api.py`, `listener.py`, `reconciler.py`, `aurum.py`, `sentinel.py`): removed bare `except:` blocks from the fixed source files and replaced silent file/JSON read fallbacks with typed exceptions and warning logs. Test: `test_no_bare_except_in_source_files`.
- **M7** (`requirements.txt`): pinned upper bounds for `anthropic`, `telethon`, and `flask`; bumped Telethon to `>=1.40.0`; added missing imported packages `hmmlearn`, `numpy`, and `httpx`. Test: `test_requirements_have_upper_bounds`.
### Security fixes — local MT5 link and scoped channel MODIFY commands
- **P2 Security**: untracked the machine-specific `MT5` symlink and added `make setup-mt5-link`. The committed symlink embedded an absolute path to one developer's MT5 Common Files directory, breaking other checkouts. `MT5_PATH` in `.env` now drives local symlink creation, with `.env.example` documenting the setup flow and `.gitignore` covering the bare symlink name.
- **C2 Security**: channel-origin `MODIFY_SL` and `MODIFY_TP` commands now require a resolved scope (`group_id`/magic or `ticket`) before BRIDGE writes a FORGE modify command. Previously, a channel message without a resolved `group_id` or `ticket` could write an unscoped `MODIFY_*` command that FORGE applied to every managed position. Unresolved channel MODIFY commands are now dropped with a warning log instead of falling through to global scope.
### Security / reliability follow-up fixes
- **C1 Security** (`python/athena_api.py`): ATHENA now binds to `ATHENA_HOST` with a localhost default (`127.0.0.1`) instead of `0.0.0.0`. When `ATHENA_SECRET` is set and non-empty, all state-mutating HTTP methods (`POST`/`PUT`/`PATCH`/`DELETE`) require `X-Athena-Token`; unset/empty keeps existing no-token local behavior and logs a startup warning. `.env.example` documents `ATHENA_SECRET`.
- **C3 Security** (`python/scribe.py`): dynamic SCRIBE table export now rejects table names outside `ALLOWED_SCRIBE_TABLES` and parameterizes the optional `mode` filter instead of interpolating it into SQL.
- **H2 Reliability** (`python/aurum.py`, `python/listener.py`): Claude `messages.create(...)` calls now pass `timeout=httpx.Timeout(30.0)`. LISTENER also wraps the blocking call in `asyncio.wait_for(..., timeout=30)` and timeout exceptions are logged as warnings before returning the existing fallback path.
- **H5 Reliability** (`python/sentinel.py`): ForexFactory fetch failures now retry up to two times with 3-second pauses and then fail closed by returning a high-impact fail-safe event that activates the news guard, instead of silently treating fetch failure as no guard needed.
- Tests: extended `tests/api/test_athena_management_api.py`, `tests/api/test_athena_scribe_query_limits.py`, `tests/api/test_athena_live_unit.py`, and added `tests/services/test_sentinel_failsafe.py`.
---
## [1.5.4] — 2026-05-02
### ATHENA `/api/management` schema validation (backward-compatible)
Closed the gap where `api_management()` wrote raw user-supplied JSON straight to `python/config/management_cmd.json` without any schema check. BRIDGE reads that file every tick; a malformed payload would land in the type-coercion branch (`int(group_id)`, `float(sl)`, `float(tp)`), bubble up through `_tick`'s exception handler, and spam Telegram alerts on every loop until somebody manually deleted the file.
- New schema `schemas/files/management_cmd.schema.json` (Draft-07) with intent-conditional `if/then` branches: `CLOSE_PCT` / `CLOSE_GROUP_PCT` enforce `pct ∈ (0, 100]`; `CLOSE_GROUP` / `CLOSE_GROUP_PCT` require `group_id > 0`; `MODIFY_SL` requires `sl > 0`; `MODIFY_TP` requires `tp > 0`. `additionalProperties: true` on every branch so LISTENER's `signal_id`/`channel`/`edited` fields don't get rejected.
- New `_MGMT_VALIDATOR` + `_validate_mgmt_body(body)` in `python/athena_api.py`. `api_management()` validates the assembled body **before** writing; on failure it returns `400 {error:"validation_failed", intent, details: […]}` and never touches the file.
- **Backward-compatible by design**: validator load is wrapped in `try/except` and `iter_errors` calls are wrapped too. If the schema file is missing, jsonschema imports break, or any runtime error occurs in the validator, `_validate_mgmt_body` returns `[]` and `api_management()` falls through to the original unvalidated write path. Operators can never be "locked out" by a validation infrastructure problem.
- **LISTENER and BRIDGE are intentionally unchanged** — they keep the existing tolerate-bad-payloads behaviour. The fix is at the only entry point where untrusted user JSON enters the file bus.
- Tests: new `tests/api/test_management_schema.py` (15 cases) covering valid intents, missing-required-field rejection, range/null rejection, LISTENER-style extra fields tolerated, validator-unavailable fallback, and validator-internal-error fallback. **346/346 in `tests/api/` pass**.
- Migration / rollout: drop-in. Restart ATHENA to pick up the validator (`make services-restart` or just bounce `com.signalsystem.athena`). No FORGE / SCRIBE / BRIDGE changes.
---
## [1.5.3] — 2026-05-01
### ATHENA `/api/management` schema validation (backward-compatible)
Closed the gap where `api_management()` wrote raw user-supplied JSON straight to `python/config/management_cmd.json` without any schema check. BRIDGE reads that file every tick; a malformed payload would land in the type-coercion branch (`int(group_id)`, `float(sl)`, `float(tp)`), bubble up through `_tick`'s exception handler, and spam Telegram alerts on every loop until somebody manually deleted the file.
- New schema `schemas/files/management_cmd.schema.json` (Draft-07) with intent-conditional `if/then` branches: `CLOSE_PCT` / `CLOSE_GROUP_PCT` enforce `pct ∈ (0, 100]`; `CLOSE_GROUP` / `CLOSE_GROUP_PCT` require `group_id > 0`; `MODIFY_SL` requires `sl > 0`; `MODIFY_TP` requires `tp > 0`. `additionalProperties: true` on every branch so LISTENER's `signal_id`/`channel`/`edited` fields don't get rejected.
- New `_MGMT_VALIDATOR` + `_validate_mgmt_body(body)` in `python/athena_api.py`. `api_management()` validates the assembled body **before** writing; on failure it returns `400 {error:"validation_failed", intent, details: […]}` and never touches the file.
- **Backward-compatible by design**: validator load is wrapped in `try/except` and `iter_errors` calls are wrapped too. If the schema file is missing, jsonschema imports break, or any runtime error occurs in the validator, `_validate_mgmt_body` returns `[]` and `api_management()` falls through to the original unvalidated write path. Operators can never be "locked out" by a validation infrastructure problem.
- **LISTENER and BRIDGE are intentionally unchanged** — they keep the existing tolerate-bad-payloads behaviour. The fix is at the only entry point where untrusted user JSON enters the file bus.
- Tests: new `tests/api/test_management_schema.py` (15 cases) covering valid intents, missing-required-field rejection, range/null rejection, LISTENER-style extra fields tolerated, validator-unavailable fallback, and validator-internal-error fallback. **346/346 in `tests/api/` pass**.
- Migration / rollout: drop-in. Restart ATHENA to pick up the validator (`make services-restart` or just bounce `com.signalsystem.athena`). No FORGE / SCRIBE / BRIDGE changes.
---
## [1.5.3] — 2026-05-01
### Hybrid profit ratchet — SL pin + tightened TP per-ticket
When a leg crosses `PROFIT_RATCHET_TRIGGER_PIPS`, BRIDGE now also pulls that **leg's** TP toward `current_price ± PROFIT_RATCHET_TP_BUFFER_PIPS` so any further forward movement closes the leg with a `TP_HIT` (positive close) rather than letting the SL ratchet catch the retrace. The original SL pin is preserved as the floor on retracements — every closure on the triggered leg now lands positive, regardless of which side fires.
- **Per-ticket scope is preserved**: only the leg that crossed the trigger is tightened. Sibling legs in the same group keep their original TP1/TP2/TP3 targets and continue running. This is the explicit operator preference — lock the runner, let the rest reach the staged targets.
- New env: `PROFIT_RATCHET_TP_BUFFER_PIPS` (default 5; trader-style pips). Set to 0 to disable the TP-tightening side and revert to pure SL ratchet behaviour.
- TP tightening is skipped when (a) the buffer is 0, (b) the position has no resting TP (no regression introduced), or (c) the proposed target would not actually tighten (BUY: `target_tp ≥ live_tp`; SELL: `target_tp ≤ live_tp`).
- Both the SL pin and the TP tighten go through the new FORGE command queue with separate dedup keys (`ratchet:<ticket>` and `ratchet_tp:<ticket>`) and per-ticket verifiers (`_build_ticket_sl_verifier`, `_build_ticket_tp_verifier`), so the two writes serialise correctly across the BRIDGE → FORGE file bus.
- Tests: `tests/api/test_modify_scope.py` adds 4 new cases (skip when no resting TP, skip when buffer would widen, disabled when buffer=0, per-leg isolation across BUY+SELL). Existing BUY/SELL ratchet tests now assert the SL+TP enqueue pair. **331/331 in `tests/api/` pass**.
- Migration / rollout: pure BRIDGE refactor; no FORGE EA / SCRIBE / contract changes. Defaults to enabled with a 5-pip buffer; set `PROFIT_RATCHET_TP_BUFFER_PIPS=0` to opt out.
---
## [1.5.2] — 2026-05-01
### FORGE command queue — fixes per-ticket MODIFY_SL race
Live G64 profit-ratchet test exposed a real overwrite race: BRIDGE wrote 4 ticket-scoped `MODIFY_SL` commands to the shared `MT5/command.json` within ~1.8 s; FORGE polls that file on its `OnTimer` and dedups by `timestamp`, so the first write got clobbered before FORGE could consume it. Leg 0 (#1247680712) never moved its SL, took the original SL hit for **−$4.39**, and turned what should have been a clean +$3.00 set of ratchet locks into a **net −$1.39**. The next BRIDGE tick then "learned" the stale live SL back into its in-memory cache via the drift detector, so the ratchet never retried.
- New module-level `_ForgeCommandQueue` (`python/bridge.py`) serialises FORGE writes: at most one command is in-flight per BRIDGE tick. Each pump verifies the in-flight command via a caller-supplied `verifier(mt5)` (or auto-acks after a one-tick spacing for fire-and-forget shapes), retries on timeout up to `FORGE_QUEUE_MAX_RETRIES`, and drops with an `on_drop` callback so callers can release dedup tokens. New env knobs: `FORGE_QUEUE_ACK_TIMEOUT_SEC` (default 8.0), `FORGE_QUEUE_MAX_RETRIES` (default 2). Pumped once per BRIDGE tick right after `_sync_positions`, even when MT5 is stale, so the ack-timeout path keeps ticking.
- `Bridge._enqueue_forge_command(cmd, *, verifier, description, on_drop, dedup_key)` is the new entry point. Used by `_apply_profit_ratchet` (with strict `_build_ticket_sl_verifier` per ticket and `dedup_key=ratchet:<ticket>` so a re-eligible tick doesn't pile up), `_check_aurum_command` `MODIFY_TP`/`MODIFY_SL`, and `_process_mgmt_command` `MODIFY_TP`/`MODIFY_SL`. Ticket-scoped modifies always come with a verifier; group/stage-wide modifies use the queue's fire-and-forget ack so they still get ≥1-tick spacing without needing a snapshot match.
- `_apply_profit_ratchet` no longer pre-updates `self._known_positions[ticket]['sl']` to the target. The drift detector now skips its "learn-back" branch for any ticket that has a `MODIFY_SL`/`MODIFY_TP` queued or in-flight (`_ForgeCommandQueue.has_inflight_modify_for_ticket`), so MT5's pre-modify live SL never overwrites the queued target. If the queue ultimately drops the ratchet command, `_profit_ratcheted.discard(ticket)` runs from `on_drop` so the next eligible tick re-attempts.
- Tests: `tests/api/test_modify_scope.py` adds 7 new cases — queue writes one cmd per pump (the actual race), inflight held until verifier passes, retry-and-drop budget, dedup_key suppression, `has_inflight_modify_for_ticket` matching only `MODIFY_*`, drift detector skip while modify in-flight, and ratchet `on_drop` clears the dedup token. Existing ratchet + AURUM/MGMT modify tests updated to assert against `_enqueue_forge_command`. **327/327 in `tests/api/` pass**.
- Migration / rollout: pure BRIDGE refactor; no FORGE EA, SCRIBE, or contract changes. `make reload-bridge` to ship.
---
## [1.5.1] — 2026-04-30
### Profit ratchet — auto-lock SL once a leg goes N pips green
New opt-in BRIDGE feature that addresses *"would have been nice if we close the order once we're in winning position"* without waiting for TP1. Once any tracked managed position is `≥ PROFIT_RATCHET_TRIGGER_PIPS` (default 3 XAUUSD pips) in unrealised profit and its current SL is still worse than `entry ± PROFIT_RATCHET_LOCK_PIPS` (default 1 pip past entry), BRIDGE emits a **per-ticket** `MODIFY_SL` to FORGE — reusing the v1.5.0 stage-aware MODIFY pipeline so other legs/stages stay untouched. Idempotent via an in-memory ratcheted set; cleared automatically when the position closes.
- `python/bridge.py` `_apply_profit_ratchet`: pip math via existing `_pip_size_for_symbol` / `_calc_pips`, ticket-scoped FORGE write, `_sync_modify_targets` with `ticket=` for SCRIBE row update only, `[TRACKER|PROFIT_RATCHET]` audit log + Telegram notification.
- Skips re-evaluation when SL is already past the lock target (e.g. FORGE's `move_be_on_tp1` already fired) so it composes cleanly with the existing TP1→BE behaviour.
- New env vars: `PROFIT_RATCHET_ENABLED` (default false, opt-in), `PROFIT_RATCHET_TRIGGER_PIPS` (default 15 → $1.50 on XAU), `PROFIT_RATCHET_LOCK_PIPS` (default 10 → $1.00 past entry; auto-clamped to `< trigger`). **Trader-style pip** convention (XAU/XAG = $0.10, JPY = 0.01, majors = 0.0001) so the env-var values match `trade_closures.pips` and Athena reports. Helper: `_ratchet_pip_size`.
- Tests: `tests/api/test_modify_scope.py` adds 6 ratchet cases (BUY emit, SELL emit with inverted lock, idempotency, below-trigger skip, already-locked skip, disabled short-circuit). 76/76 in the targeted suites pass.
- Docs: `.env.example`, `SKILL.md`, `SOUL.md`, `docs/CLI_API_CHEATSHEET.md`.
---
## [1.5.0] — 2026-04-30
### Per-stage / per-ticket `MODIFY_TP` & `MODIFY_SL`
MODIFY commands across the AURUM → BRIDGE → FORGE pipeline now accept two new optional scope fields so TP2/TP3 legs no longer collapse onto TP1 when only TP1 needs to move.
- **FORGE** (`ea/FORGE.mq5` v1.5.0): `ExecuteModifySL` / `ExecuteModifyTP` read optional `ticket` (single position or pending) and `tp_stage` (1/2/3, filtered against `Comment()` matching `|TP<n>`); legacy whole-magic behaviour preserved when both are absent. `WriteMarketData` adds `comment` to each `open_positions[]` row so BRIDGE can recover the leg-stage metadata `FORGE|G<id>|<leg_index>|TP<stage>`.
- **BRIDGE** (`python/bridge.py`): `_check_aurum_command` and `_process_mgmt_command` MODIFY branches forward `ticket` / `tp_stage` to FORGE after light validation. New `_sync_modify_targets` helper routes SCRIBE persistence: ticket scope updates one row, stage scope only nudges `trade_groups.tp<n>` for the matching stage, and the unscoped path keeps the existing group-wide / all-open fan-out. `_TP_STAGE_RE`/`_parse_tp_stage_from_comment` helpers parse the FORGE comment grammar; TRACKER FILL records `tp_stage` on insert and the seed pass calls `backfill_tp_stage_from_comment` for legacy rows.
- **SCRIBE** (`python/scribe.py`): `log_trade_position` now persists `data['tp_stage']`. New helpers `update_positions_sl_tp_by_stage(group_id, tp_stage, sl, tp)`, `backfill_tp_stage_from_comment(ticket, comment)`, and `get_open_positions_with_stage(group_id)` expose the stage-aware surface. The schema is unchanged — `trade_positions.tp_stage` already existed.
- **AURUM prompt** (`python/aurum.py`): new `PER-STAGE / PER-TICKET MODIFY` section documents the new fields and **requires** a `SCRIBE_QUERY` on `trade_positions` before any multi-leg MODIFY. Two-block example shows independent TP1 vs TP2 moves.
- **Contracts** (`python/contracts/aurum_forge.py`): `validate_aurum_cmd` and `validate_forge_command` accept optional `ticket` (positive int) and `tp_stage` (1/2/3) on `MODIFY_TP` / `MODIFY_SL`; unknown-action error message updated.
- **Tests**: `tests/api/test_modify_scope.py` covers SCRIBE backfill / stage updates, BRIDGE `_coerce_modify_scope` + `_sync_modify_targets` routing, BRIDGE AURUM-cmd MODIFY pass-through, and AURUM-side contract validation. `tests/api/test_aurum_forge_contract.py` extended with stage/ticket validation.
- **Docs**: `docs/DATA_CONTRACT.md`, `docs/CLI_API_CHEATSHEET.md`, `schemas/files/market_data.schema.json`, `SKILL.md`, `SOUL.md` updated with the new shapes, the comment-grammar contract, and the SCRIBE_QUERY-first workflow.
- **Migration / rollout**: SCRIBE migration is purely additive (column already present). FORGE EA must be recompiled / reattached to MT5 for `comment` in `open_positions[]` and the new MODIFY filters; BRIDGE/AURUM/SCRIBE hot-reload via `make restart`.
---
## [1.4.5] — 2026-04-30

### Deferred Analysis Runs (`ANALYSIS_RUN`)
Reusable async-analysis subsystem layered on top of the AEB. AURUM (or any caller) emits a fire-and-forget AEB action and gets an immediate `query_id`; the result is persisted under `logs/analysis/<query_id>.{json,md}` and posted back to the existing Telegram channel via the existing Herald singleton (no new bot, token, or chat_id).
- New module `python/analysis_runner.py`:
  - `register_analysis(kind)` decorator + `_HANDLERS` registry.
  - `submit(payload)` returns immediately with `{ok, query_id, status:"PENDING", log_path}`.
  - `list_pending()` / `list_recent(limit=20)` / `get_status(query_id)` introspection.
  - Daemon `ThreadPoolExecutor` worker (cap `ANALYSIS_MAX_CONCURRENCY`, default 4) writes `.json` (status) + `.md` (body) and audits `ANALYSIS_QUEUED|DONE|FAILED` to `logs/audit/system_events.jsonl`.
  - Idempotency on client-supplied `query_id` (duplicate while PENDING returns `ANALYSIS_RUN duplicate query_id`); soft queue cap returns `ANALYSIS_RUN queue full`.
  - Built-in handler `trade_group_review` (params `{group_id:int}`) reads SCRIBE read-only + scrapes `logs/bridge.log` and renders a markdown review (signal text, AEGIS decision, fills, fill ratio, realised PnL); tolerates SCRIBE schema drift via `schema_missing:` notes.
- AEB / Bridge wiring:
  - `python/aeb_executor.py`: `ANALYSIS_RUN` added to `_AEB_ACTIONS`, validator branch, dispatcher branch (lazy import), Telegram ACK formatter renders `query_id`, `status`, `log_path`.
  - `python/bridge.py`: routes `ANALYSIS_RUN` through the existing local AEB dispatch alongside `SCRIBE_QUERY` / `SHELL_EXEC`.
- AURUM wiring:
  - `python/aurum.py`: `ANALYSIS_RUN` added to supported-actions list, new `DEFERRED ANALYSIS RUNS` section in `_build_system_prompt`, and a pending/recent block appended to `_build_context` (capped at 20 lines).
- Telegram (Herald) reuse — no new bot:
  - `python/herald.py`: new `Herald.post_text()` and `Herald.post_analysis_from_log()` methods plus module-level shims; `_async_send` accepts an optional `chat_id` override; default chat target remains `Herald.chat_id`.
- Schemas + contracts:
  - `schemas/files/aurum_cmd.schema.json`: new `ANALYSIS_RUN` `oneOf` branch.
  - `python/contracts/aurum_forge.py`: `validate_aurum_cmd` accepts `ANALYSIS_RUN` (kind required; params/notify/query_id types validated).
- Docs:
  - `docs/ARCHITECTURE.md`: “Deferred Analysis Runs” section + envelope + data-flow diagram.
  - `docs/DATA_CONTRACT.md`: `ANALYSIS_RUN` listed alongside other AEB actions.
  - `docs/CLI_API_CHEATSHEET.md`: copy-paste examples for queueing a run and tailing the log file.
  - `SKILL.md` §5 + `SOUL.md`: capability + context-awareness bullets.
  - `.env.example`: `ANALYSIS_LOG_DIR` + `ANALYSIS_MAX_CONCURRENCY`.
- Verification: `make test-contracts` 93 passed; `tests/api/test_aeb_executor.py` 9 passed; end-to-end smoke (G56 review) `fills=1/1 pnl=$+4.02` matched bridge.log.

---
## [1.4.4] — 2026-04-14

### AURUM Execution Bridge (AEB) end-to-end
- Added shared executor module `python/aeb_executor.py` for:
  - `SCRIBE_QUERY` (read-only SQLite URI mode + authorizer + single-statement guard + timeout/progress + row truncation)
  - `SHELL_EXEC` (allowlisted program/path validation, legacy `cmd` parsing via `shlex`, `subprocess.run(..., shell=False, timeout=...)`, output caps)
  - common result formatting for Telegram + structured result payloads
- Extended BRIDGE `aurum_cmd.json` router to handle `SCRIBE_QUERY`, `SHELL_EXEC`, and `AURUM_EXEC` while preserving existing command behavior and file-consume semantics.
- Added BRIDGE `AURUM_EXEC` HTTP dispatch path to ATHENA (`AURUM_EXEC_BASE_URL`, timeout, optional shared secret header).
- Added ATHENA `POST /api/aurum/exec` endpoint with optional token auth (`ATHENA_AURUM_EXEC_SECRET`) and shared executor dispatch.
- Hardened ATHENA `POST /api/scribe/query` internals to use the secure read-only executor path (with compatibility fallback for isolated test stubs).
- Extended AURUM JSON extraction allowlist and system prompt examples for `SCRIBE_QUERY`, `SHELL_EXEC`, and `AURUM_EXEC`.

### Contracts, schemas, docs, and tests
- Updated runtime validator `python/contracts/aurum_forge.py` for new AEB actions.
- Updated file-bus schema `schemas/files/aurum_cmd.schema.json` with new `oneOf` branches.
- Updated OpenAPI `schemas/openapi.yaml` with `/api/aurum/exec` and AEB request/result components.
- Updated `.env.example`, `docs/DATA_CONTRACT.md`, and `docs/SCRIBE_QUERY_EXAMPLES.md` for AEB config and usage.
- Added/extended tests:
  - new: `tests/api/test_aeb_executor.py`
  - new: `tests/api/test_athena_aurum_exec_api.py`
  - updated: `tests/api/test_bridge_aurum_cmd.py`
  - updated: `tests/api/test_aurum_forge_contract.py`
  - updated: `tests/api/test_json_schemas.py`
  - updated: `tests/api/test_swagger_ui.py`

---
## [1.4.3] — 2026-04-14

### Regime engine rollout surfaced end-to-end
- Added `python/regime.py` (HMM-primary inference with Gaussian fallback safety path).
- BRIDGE now computes regime snapshots each tick and persists emitted snapshots to SCRIBE `market_regimes`.
- SIGNAL/AURUM entry validation now carries regime context through AEGIS and records regime metadata on `signals_received` and `trade_groups`.
- ATHENA now serves regime surfaces via `GET /api/regime/current`, `GET /api/regime/history`, `GET /api/regime/performance`, and includes a `regime` block in `GET /api/live`.
- Added regime coverage tests:
  - `tests/services/test_regime_engine.py`
  - `tests/api/test_scribe_regime.py`
  - `tests/api/test_athena_regime_api.py`

### Execution-management and tracker hardening
- `MODIFY_SL` / `MODIFY_TP` support global and per-group execution:
  - no `magic` => global apply,
  - resolved `magic` from `group_id` => scoped apply.
- BRIDGE now syncs modified group targets into SCRIBE group + open-position rows (`update_group_sl_tp`) so ATHENA reflects live SL/TP edits immediately.
- FORGE exports `recent_closed_deals[]` in `market_data.json`; BRIDGE tracker now uses broker close metadata first (price, PnL, reason, close time) with inference fallback only when broker hints are missing.
- BRIDGE MT5 stale-data protection now tolerates transient `market_data.json` read/parse races by reusing the last known-good snapshot for a short, parameterized grace window before tripping circuit breaker:
  - `BRIDGE_MT5_STALE` (primary stale threshold),
  - `BRIDGE_MT5_STALE_RELAXED` (read-error fallback threshold),
  - `BRIDGE_MT5_READ_FAIL_STREAK` (consecutive read failures required before fallback can hard-fail).
- Added regression coverage:
  - `tests/api/test_mgmt_channel_scoping.py`
  - `tests/api/test_bridge_manual_position_tracking.py`
  - `tests/api/test_threshold_persistence.py`

### Documentation updates
- Updated `docs/ARCHITECTURE.md` with regime engine flow and `market_regimes` table coverage.
- Updated `docs/FORGE_TRADING_RULES.md` with regime rollout, scoped modify semantics, and broker-first closure attribution.
- Updated `docs/CLI_API_CHEATSHEET.md` and `docs/SCRIBE_QUERY_EXAMPLES.md` for TP-stage close reason examples and regime diagnostics queries.
- Updated `docs/SIGNAL_REPLAY_RUNBOOK.md` with direct SQLite quick diagnostics (Ben's VIP pickup checks, ENTRY-only checks, real Telegram ID filtering, and recent action snapshots using `datetime(timestamp)`).
- Updated `SOUL.md` and `SKILL.md` to reflect merged room allowlist aliases (`SIGNAL_TRADE_ROOMS` + `ACTIVE_SIGNAL_TRADE_ROOMS`), configurable SIGNAL orientation gate (`AEGIS_SIGNAL_LIMIT_ORIENTATION`), and replay-first troubleshooting (`scripts/replay_signal_pickup.py`).

---
## [1.4.2] — 2026-04-13

### LISTENER Signal Room Ingestion — Hardening & Observability

Root cause: signals from configured Telegram rooms were silently dropped as `WATCH_ONLY`
due to brittle room matching, a free-text reason code that was hard to grep, and zero
observability of where in the pipeline signals stopped flowing.

#### Room Allowlist Logic (`python/listener.py`)

- **Robust `_is_trade_room_allowed`** — now returns `(bool, reason_code)` tuple:
  - `ALLOWED_ALL` — `SIGNAL_TRADE_ROOMS` not set (legacy; all rooms trade)
  - `ALLOWED_TITLE_MATCH` — title matched after NFKC normalization + whitespace collapse + lowercase
  - `ALLOWED_ID_MATCH` — chat_id matched; tries all Telethon supergroup ID variants automatically (`-1001234567890`, `1001234567890`, `1234567890`)
  - `WATCH_ONLY_ROOM_FILTER` — not in allowlist (replaces old free-text `ROOM_NOT_PRIORITY:<room>`)
- **Unicode normalization** (`_normalize_room_name`): NFKC + whitespace-collapse + lowercase — handles curly apostrophes, non-breaking spaces, and other Unicode mismatches between operator config and Telethon-resolved titles.
- **chat_id variant matching** (`_chat_id_variants`): auto-tries bare ID, signed ID with `-100` prefix, and positive form — eliminates "configured `1234567890` but Telethon returns `-1001234567890`" silent misses.
- `WATCH_ONLY` blocks now log at **WARNING** (was INFO), making them visible in `make logs-errors`.

#### New Structured Reason Codes

| Reason Code | Where it appears | Meaning |
|---|---|---|
| `WATCH_ONLY_ROOM_FILTER` | `signals_received.skip_reason` | Room not in `SIGNAL_TRADE_ROOMS` allowlist |
| `SIGNAL_DISPATCHED` | `system_events.event_type` | Entry signal written to `parsed_signal.json` |
| `SIGNAL_PARSE_FAILED` | `system_events.event_type` | Non-empty text received but Claude returned IGNORE |
| `AEGIS_REJECTED:<reason>` | `signals_received.skip_reason` | AEGIS blocked the signal (prefixed, not bare reason) |

The old free-text `ROOM_NOT_PRIORITY:<room>` reason code is **removed**.

#### Staleness Detection

- `_last_ingest_at` tracked per LISTENER instance — updated on every received message.
- `_idle_heartbeat_loop` now checks age against `LISTENER_STALE_THRESHOLD_SEC` (default 600s):
  - `> threshold` → reports `status=WARN` with reason `LISTENER_STALE_OR_DISCONNECTED`
  - Normal → reports `status=OK` with "last_ingest Xs ago"

#### New File: `python/config/listener_meta.json`

Written by LISTENER on connect and updated each heartbeat/dispatch. Fields:
- `status` — `OK` | `WARN`
- `last_ingest_at` — ISO-8601 UTC of last processed message
- `signal_trade_rooms_active` / `signal_trade_rooms_count`
- `resolved_rooms[]` — per-channel `{chat_id, title, is_trade_room, match_reason}`

#### Startup Logging

LISTENER logs each resolved channel at startup with trade_room status:
```
LISTENER: channel -100xxx = 'Ben's VIP Club'  trade_room=True (ALLOWED_TITLE_MATCH)
LISTENER: channel -100yyy = 'Other Room'       trade_room=False (WATCH_ONLY_ROOM_FILTER)
```

#### ATHENA API Changes (`python/athena_api.py`)

- **`GET /api/channels`**: new fields per channel — `watch_only` (SCRIBE count), `is_trade_room`, `match_reason`; top-level — `signal_trade_rooms_active`, `listener_last_ingest_at`, `listener_status`.
- **`GET /api/channels/messages`**: new fields — `cache_age_sec` (mtime-based), `listener_stale` (true if cache > 3× refresh interval), `listener_last_ingest_at`, `listener_status`.

#### BRIDGE (`python/bridge.py`)

- AEGIS rejection `skip_reason` now prefixed with `AEGIS_REJECTED:` for unambiguous SCRIBE query filtering (was bare reject_reason string, indistinguishable from LENS/expiry skips).

#### Tests (`tests/api/test_listener_room_filter.py`) — new file, 21 tests

| Test class | Coverage |
|---|---|
| `TestIsTradeRoomAllowed` | empty allowlist; title case/whitespace/Unicode; chat_id variants (bare, -100 prefix, positive form); mismatch → WATCH_ONLY_ROOM_FILTER |
| `TestHandleMessageRoomFilter` | unallowed room → WATCH_ONLY + correct reason; old ROOM_NOT_PRIORITY absent; chat_id match dispatches despite title change; allowed room → SIGNAL_DISPATCHED event; empty allowlist → all dispatch |
| `TestParseFailed` | non-signal text → SIGNAL_PARSE_FAILED event; empty text → no PARSE_FAILED |
| `TestListenerStaleness` | `_last_ingest_at` updated on message; updated on dispatch; threshold config |
| `TestWatchOnlyEventDetails` | event notes contain channel+chat_id; reason field is structured code |

Updated `tests/api/test_vision_listener_aurum.py`: `test_non_priority_room_is_watch_only_in_signal_mode` assertion changed from `ROOM_NOT_PRIORITY` to `WATCH_ONLY_ROOM_FILTER`.

All 195 tests pass (`tests/api/` + `tests/services/`).

#### Documentation Updated

- `docs/SIGNAL_ROOM_POLICY.md` — new matching semantics, startup log to expect, `api/channels` quick check, updated verification queries for new reason codes, added `SIGNAL_DISPATCHED` / `SIGNAL_PARSE_FAILED` queries.
- `docs/DATA_CONTRACT.md` — `listener_meta.json`, `channel_names.json`, `channel_messages.json` added to file bus table; `listener_meta.json` shape documented.
- `docs/CLI_API_CHEATSHEET.md` — replaced `## Signal Channels` with `## Signal Channels & LISTENER Diagnostics`; added 60-second "no trades from room" runbook; AEGIS reject reasons updated to `AEGIS_REJECTED:` prefix; bridge.log grep patterns updated.

#### Runtime Verification

```bash
# Confirm room allowlist status after restart
curl -s http://localhost:7842/api/channels | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f'listener={d[\"listener_status\"]} last_ingest={d[\"listener_last_ingest_at\"]}')
[print(f'  {ch[\"name\"]}: trade_room={ch[\"is_trade_room\"]} match={ch[\"match_reason\"]} watch_only={ch[\"watch_only\"]}') for ch in d['channels']]
"

# Confirm no signals stuck in WATCH_ONLY unexpectedly
curl -s -X POST http://localhost:7842/api/scribe/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT channel_name, action_taken, skip_reason, COUNT(*) as n FROM signals_received GROUP BY channel_name, action_taken ORDER BY channel_name, n DESC"}' \
  | python3 -c "import sys,json; [print(r) for r in json.load(sys.stdin)['rows']]"
```

---

## [1.4.1] — 2026-04-10

### FORGE Threshold Hardening
- Added configurable runtime threshold parameters:
  - `pending_entry_threshold_points`
  - `trend_strength_atr_threshold`
  - `breakout_buffer_points`
- Native scalper logic hardened:
  - breakout trigger now uses previous M5 close + configurable breakout buffer
  - EMA trend filters normalized by ATR
  - TP split bug fixed (`BB_BREAKOUT` now uses breakout TP split config)
  - stop-level validation + lot normalization enforced before placement
  - spread-aware breakeven logic
  - cooldown timestamp updates on realized losses
  - startup rebuild of in-memory FORGE groups from open positions
- Added threshold + decision-metric telemetry into `market_data.json`, `mode_status.json`, and `scalper_entry.json`.

### BRIDGE + SCRIBE Persistence
- BRIDGE now writes threshold overrides into `MT5/config.json`.
- BRIDGE forwards native scalper threshold fields into SCRIBE `trade_groups`.
- LENS snapshot logging path now includes threshold fields from MT5 payload.
- SCRIBE schema/migrations extended with threshold fields in:
  - `market_snapshots`
  - `trade_groups`

### Tests and Verification
- Added `tests/api/test_threshold_persistence.py`:
  - migration checks on legacy DB shape
  - persistence checks for snapshot/group threshold fields
  - bridge forwarding checks for native scalper entries
- Verified with targeted and full API suite passes.

### Operations Improvements
- Added full lifecycle commands:
  - `make system-up` (TradingView → MetaTrader 5 → Python services)
  - `make system-down` (Python services → TradingView → MetaTrader 5)
- Added MT5 controls:
  - `make mt5-start`
  - `make mt5-stop`
- Hardened TradingView shutdown:
  - `make stop-tradingview` now force-kills and verifies termination.
- Added SCRIBE GUI helper:
  - `make scribe-gui` opens DB Browser for SQLite on `python/data/aurum_intelligence.db`.

### Documentation Updates
- Updated `docs/FORGE_BRIDGE.md` for threshold-hardening behavior and OFF_HOURS no-fill guidance.
- Updated `docs/DATA_CONTRACT.md` for `forge_config` threshold contract and `scalper_entry.json` metrics.
- Updated `docs/SETUP.md` + `docs/OPERATIONS.md` for SQLite GUI workflow and system lifecycle commands.
- Updated `SKILL.md` + `SOUL.md` for threshold-awareness and weekend/off-hours execution behavior.

---

## [1.4.0] — 2026-04-06

### FORGE Native Scalper Engine
- New `ScalperMode` input: `NONE` | `BB_BOUNCE` | `BB_BREAKOUT` | `DUAL`
- **BB Bounce** (ADX<20): buy at BB lower + RSI<35, sell at BB upper + RSI>65, H1 trend filter
- **BB Breakout** (ADX>25): breakout above/below BB + RSI + M5/M15 EMA alignment
- ATR-based SL/TP (1.2x for bounce, 1.5x for breakout), multi-TP with partial closes
- Safety guards: session filter (London+NY), spread<25pt, max 2 groups, loss cooldown
- DD event TP tightening: reads sentinel_status.json, tight TP at 0.8x ATR near news
- R:R minimum 1.2 enforced before every native entry
- Writes `scalper_entry.json` for BRIDGE to log to SCRIBE
- Fully backtestable in MT5 Strategy Tester
- `FORGE_SCALPER_MODE` controllable via `.env` → config.json (no reattach needed)

### Shared Scalper Config
- New `config/scalper_config.json` — BB bounce + breakout rules, session filter, safety guards
- Read by FORGE (MQL5) and AURUM (Python) for strategy consistency
- `make scalper-config-sync` copies config to MT5 Common Files

### AUTO_SCALPER Intelligence
- `format_for_aurum()` now includes BB position %, EMA distance, RSI momentum hints
- AUTO_SCALPER prompt includes decision framework (BUY/SELL/PASS criteria)
- BB squeeze detection (M5 BB range < 1.5x ATR = breakout imminent)
- AURUM context includes scalper_config.json parameters for consistency with FORGE

### Live Floating P&L on Dashboard
- Group tiles show real-time floating P&L from MT5 `open_positions[]` (3s refresh)
- Individual position boxes show entry price + per-position P&L
- Gold `LIVE` badge on groups with active MT5 positions
- Source badges: cyan `FORGE` / gold `AURUM` / orange `SIGNAL`

### BRIDGE Integration
- `_check_forge_scalper_entry()` reads scalper_entry.json from FORGE
- Native scalper trades logged to SCRIBE with `source=FORGE_NATIVE_SCALP`
- Herald Telegram alerts for native scalper entries with setup type + indicators

### Bug Fixes
- AURUM welcome message no longer stuck on "waiting for live data" after page load
- `_normalize_aurum_open_trade` method signature restored after edit corruption
- `AUTO_SCALPER` added to `contracts/aurum_forge.py` VALID_MODES + JSON Schema

---

## [1.3.1] — 2026-04-06

### SL/TP Hit Logging (trade_closures)
- New `trade_closures` SCRIBE table logs every position closure with full context
- `close_reason` inferred by BRIDGE: `SL_HIT`, `TP1_HIT`, `TP2_HIT`, `TP3_HIT`, `MANUAL_CLOSE`, `RECONCILER`, `UNKNOWN`
- BRIDGE `_infer_close_reason()` compares close price to SL/TP levels ($0.50 tolerance for XAUUSD)
- BRIDGE `_match_tp_stage()` resolves TP1/TP2/TP3 from trade_group record
- HERALD `tp_hit()` and `position_closed()` now called per position on SL/TP detection
- RECONCILER ghost positions logged to `trade_closures` with reason `RECONCILER`
- New API: `GET /api/closures?days=7&limit=50` — recent closures with reason
- New API: `GET /api/closure_stats?days=7` — aggregated SL vs TP hit rates
- `/api/live` extended with `recent_closures` (last 5, 24h) and `closure_stats` (7d)
- New ATHENA dashboard **Closures** tab with color-coded SL/TP tags and summary stat tiles
- `POSITION_MODIFIED` events categorized as TRADE in Activity panel (was hidden in SYSTEM)
- AURUM context includes last 5 closures and 7d SL/TP hit rate stats
- SCRIBE methods: `log_trade_closure()`, `get_recent_closures()`, `get_closure_stats()`, `get_open_positions_by_group()`
- Tab bar compacted for 5-tab fit; group position grid boxes reduced
- AURUM chat textarea auto-expands with word wrap (Shift+Enter for newlines)
- Agent.md added (gitignored) for AI tool project context
- Fixed pre-existing em-dash syntax error in scribe.py docstring
- Fixed DDL string split that left component_heartbeats outside the DDL block

### Documentation Updated
- `SKILL.md` — closure queries, closure context in injected state
- `SOUL.md` — trade closure detection knowledge, closure context awareness
- `docs/CLI_API_CHEATSHEET.md` — /api/closures, /api/closure_stats curl examples, SCRIBE closure queries
- `docs/SCRIBE_QUERY_EXAMPLES.md` — trade_closures table + 4 new example queries (#15–#18)
- `docs/DATA_CONTRACT.md` — trade_closures in persistence layer
- `CHANGELOG.md` — this entry

---

## [1.3.0] — 2026-04-06

### AUTO_SCALPER Mode
- New `AUTO_SCALPER` mode — AURUM (Claude) as autonomous decision engine
- BRIDGE polls AURUM every `AUTO_SCALPER_POLL_INTERVAL` (default 120s) with structured multi-TF prompt
- Pre-filters: H1 direction gate, RSI neutral screen, sentinel/max groups, loss cooldown
- AURUM responds with `OPEN_GROUP` JSON or `PASS: <reason>`
- Configurable: `AUTO_SCALPER_LOT_SIZE`, `AUTO_SCALPER_NUM_TRADES`, `AUTO_SCALPER_POLL_INTERVAL`, `AUTO_SCALPER_MAX_GROUPS`
- Dashboard mode button (green, "AURUM auto")

### Multi-Timeframe Indicators (FORGE)
- FORGE now exports `indicators_m5`, `indicators_m15`, `indicators_m30` alongside `indicators_h1`
- Each timeframe: RSI(14), EMA20, EMA50, ATR(14), BB upper/mid/lower, MACD histogram, ADX
- H1 expanded: added BB bands, MACD histogram, ADX (previously only RSI/EMA/ATR)
- New `market_view.py` module — unified MarketView combining FORGE + LENS data
- AURUM context now includes full multi-TF data with bias labels (BULL/BEAR/FLAT)

### Position Tracker (BRIDGE)
- BRIDGE now tracks individual position fills and closes from `market_data.json`
- New positions → `scribe.log_trade_position()` with ticket, magic, direction, lots, entry, SL/TP
- Disappeared positions → `scribe.close_trade_position()` with last-known P&L and estimated pips
- Group auto-rollup: when all positions/pendings gone → `update_trade_group()` with totals
- Seed from SCRIBE on startup to prevent duplicate logging after restarts
- Dedup guard: checks SCRIBE for existing ticket before inserting

### Drawdown Protection
- **Equity DD breaker** (BRIDGE): tracks session peak equity, CLOSE ALL + force WATCH if equity drops `DD_EQUITY_CLOSE_ALL_PCT` (default 3%) from peak. Telegram alert.
- **Floating P&L guard** (AEGIS): blocks new groups if floating loss ≥ `DD_FLOATING_BLOCK_PCT` (default 2%) of balance
- **Loss cooldown** (AUTO_SCALPER): pauses `DD_LOSS_COOLDOWN_SEC` (default 300s) after any position closes at a loss

### AEGIS Enhancements
- **H1 trend hard filter**: rejects BUY when H1 EMA20 < EMA50 (bearish), SELL when bullish. `AEGIS_H1_TREND_FILTER=true`
- **Per-signal `num_trades` override**: signals can include `num_trades` or `trades` (1–20) to override default 8
- **Lot override for AURUM/AUTO_SCALPER**: uses signal's `lot_per_trade` directly instead of risk-based sizing
- All previously hardcoded values now configurable: `AEGIS_MIN_LOT`, `AEGIS_PIP_VALUE_PER_LOT`, `AEGIS_MIN_SL_PIPS`
- `mt5_data` parameter added to `validate()` for H1 trend + floating DD checks

### Explicit Magic Number (SCRIBE)
- `magic_number` column added to `trade_groups` table
- BRIDGE stores `FORGE_MAGIC_BASE + group_id` explicitly (single source of truth)
- Reconciler and ATHENA read stored magic instead of computing `base + id`
- Auto-migration for existing databases
- `update_trade_group_magic()` method added to SCRIBE

### FORGE Bug Fixes
- `ExecuteCloseAll()` now cancels pending orders (limits/stops) in addition to closing filled positions
- Previously only iterated `PositionsTotal()`, missed `OrdersTotal()`

### BRIDGE Bug Fixes
- AURUM CLOSE_ALL now updates SCRIBE groups + clears cache (was missing, only wrote FORGE command)
- `num_trades`/`trades` from AURUM commands now passed through to AEGIS (was silently ignored)
- AURUM dispatch now accepts AUTO_SCALPER as valid effective_mode

### Reconciler Improvements
- FORGE version guard: skips stale-group close if `forge_version` < 1.2.4 (pending_orders not exported before that)
- Uses stored `magic_number` from SCRIBE instead of computing `base + id`

### AURUM Enhancements
- Context now includes full multi-TF indicators (M5/M15/M30/H1) with BB bands, MACD, ADX, EMA levels
- Context includes MT5 H1 ATR with sizing guidance ("use 1.5×ATR for SL")
- SKILL.md: scalping TP distance rules ($2–$5 for TP1, $5–$10 for TP2, never $10+ for scalps)
- SKILL.md: H1 alignment rule (never scalp against H1 EMA direction)
- SKILL.md: AUTO_SCALPER tick response format
- SOUL.md: AUTO_SCALPER role section (decision engine vs rules engine)
- Hot-reload: AURUM re-reads SKILL.md + SOUL.md from disk on every query (no restart needed)

### New Files
- `python/market_view.py` — unified FORGE + LENS market data object
- `docs/CLI_API_CHEATSHEET.md` — curl + python one-liners for all API endpoints

### Mode Persistence Across Restarts
- BRIDGE now restores previous mode from `status.json` on restart (default: enabled)
- `RESTORE_MODE_ON_RESTART=true` (default) — reads saved mode from status.json
- `RESTORE_MODE_ON_RESTART=false` — uses FORGE `requested_mode` or `DEFAULT_MODE` from .env
- Mode changes via API (`POST /api/mode`) write directly to status.json for immediate persistence
- CLI `--mode` from launchd plist only used as fallback when no saved state exists

### TP Split at Order Placement
- FORGE now splits TP targets at open: 75% of positions get TP1, 25% get TP2
- Split ratio controlled by `TP1_CLOSE_PCT` (default 70%)
- When TP1 hits (broker-side): 75% close automatically, remaining positions get SL→BE + TP→TP2
- Comment field shows TP target: `FORGE|G14|0|TP1` or `FORGE|G14|3|TP2`
- No more "all positions close at TP1" problem

### Signal Parser API
- New `POST /api/signals/parse` — test Claude Haiku parser via API without Telegram
- Input: `{"text": "SELL Gold @4691-4701 SL:4706 TP1:4687"}` → returns structured JSON
- Supports ENTRY, MANAGEMENT (CLOSE_ALL, CLOSE_PCT, MODIFY_SL, MODIFY_TP, TP_HIT), and IGNORE

### OpenAPI Spec v1.3.0
- 7 new endpoints added to `schemas/openapi.yaml`
- Management examples expanded with all 9 intents
- Swagger UI at `/api/docs/` fully updated

### Signal Lifecycle (Scalping)
- Signal expiry: `SIGNAL_EXPIRY_SEC=60` — stale signals rejected as EXPIRED
- Pending order timeout: `PENDING_ORDER_TIMEOUT_SEC=120` — unfilled limit orders auto-cancelled after 2min
- Telegram alert `⏰ PENDING EXPIRED` sent when orders timeout
- Full lifecycle: signal → AEGIS → FORGE → fill/timeout → SL/TP → SCRIBE → Telegram close alert

### Scalping-Aware Trend Cascade
- AEGIS trend filter now source-aware with multi-TF cascade
- **SIGNAL source** (channel scalps): M5 → M15 → H1. M5 is primary — if M5 agrees (or is FLAT), trade passes even if H1 disagrees
- **AURUM/AUTO_SCALPER**: H1 → M15 cascade (conservative)
- **SCALPER** (BRIDGE): H1 only (strictest)
- FLAT (EMA20 ≈ EMA50 within $1) counts as agreement — allows entry in either direction
- Replaces the old single-H1 filter that was too strict for scalping signals

### FORGE Reload Make Target
- New `make forge-reload` — compile + restart MT5 + auto-detect if EA loaded
- If FORGE auto-loads: prints ✅ and version. If not: prints reattach instructions
- Note: MT5 on Wine/macOS does NOT reliably auto-restore EAs after restart
- Manual reattach still required in most cases (Wine limitation)

### FORGE Architecture Comments
- Comprehensive architecture overview added to FORGE.mq5 header (50+ lines)
- Documents: data flow, command actions, market data output, TP split, magic numbers
- Section comments on: input parameters, globals, indicator handles, group tracking, symbol matching

### Sentinel Pre-Alert
- New Telegram warning when HIGH-impact event is ≤35min away but guard not yet active
- Message: `⚠️ Guard activating soon! {event} in {min}min`
- Fires with the 10-min adaptive digest cycle

### Sentinel Event Digest (Adaptive)
- SENTINEL sends upcoming HIGH-impact events to Telegram with adaptive timing
- **> 30 min away**: digest every 30 min. **≤ 30 min**: every 10 min. **Guard active**: immediate alerts
- Shows event name, currency, minutes away, and guard status
- Only sends when HIGH-impact events are within 4 hours
- Override interval via `POST /api/sentinel/digest {"interval": 30}` (reverts on restart)

### Telegram Close Alerts
- HERALD now sends `GROUP CLOSED` notifications with P&L summary when groups close
- Fires from both paths: position tracker (SL/TP) and management commands (manual close)
- `trade_group_closed()` and `position_closed()` templates added to HERALD

### Sentinel Override
- New `POST /api/sentinel/override` endpoint — temporarily bypass sentinel news guard
- Configurable duration (60s–3600s), defaults to `SENTINEL_OVERRIDE_DURATION_SEC=600`
- Auto-reverts after timeout — logged as `SENTINEL_OVERRIDE_EXPIRED` in SCRIBE
- BRIDGE handles `SENTINEL_OVERRIDE` action via aurum_cmd.json
- Telegram alert on override and expiry

### Smart Position Closing
- New FORGE commands: `CLOSE_GROUP`, `CLOSE_GROUP_PCT`, `CLOSE_PROFITABLE`, `CLOSE_LOSING`
- Group-targeted: close/partial-close only one group's positions by magic number
- Profit/loss filtering: close only winners or only losers across all groups
- BRIDGE resolves group_id → magic_number via SCRIBE for all group commands
- `POST /api/management` now accepts `group_id` parameter for group-targeted commands
- Dashboard group tile buttons now group-specific (Close Group / Close 70% target the specific group, not all)

### Signal Channels (LISTENER)
- Fixed: channel IDs parsed as integers (was strings → Telethon `ValueError`)
- Signals now logged to SCRIBE in ALL modes (not just SIGNAL/HYBRID) — only dispatch is gated
- New `GET /api/channels` endpoint — configured channels with Telethon-resolved names + signal stats
- New `GET /api/channels/messages` endpoint — recent messages from all channels (cached by LISTENER)
- LISTENER resolves channel names on connect → writes `config/channel_names.json`
- LISTENER caches last 10 messages per channel → `config/channel_messages.json` (refreshes every 5min)
- Dashboard signals tab redesigned: channel name badge on each row, channel filter strip, two-line card layout

### Documentation Updated
- `SOUL.md` — AUTO_SCALPER role, multi-TF context, drawdown protection
- `SKILL.md` — complete context spec, scalping rules, AUTO_SCALPER tick format
- `docs/AEGIS.md` — new guards table, per-signal overrides, DD env vars
- `docs/FORGE_BRIDGE.md` — multi-TF indicators, position tracker, CLI cheat sheet link
- `docs/CLI_API_CHEATSHEET.md` — channel polling commands, all curl examples
- `CHANGELOG.md` — this entry

---

## [1.2.0] — 2026-04-05

### Architecture: API-First Dashboard
All data displayed in ATHENA now flows through the Flask API.
No hardcoded mock data remains in the dashboard.

**Rule enforced:**
Component → SCRIBE/JSON file → Flask endpoint → Dashboard

### Added
- `SCRIBE.component_heartbeats` table — one row per component,
  upserted on every cycle, tracks status/note/last_action/error
- `Scribe.heartbeat()` method — upsert current component state
- `Scribe.get_component_heartbeats()` method — read all heartbeats
- `GET /api/components` — dedicated component health endpoint,
  returns all 11 components including FORGE (synthesised from
  MT5 JSON) and ATHENA (self-reported)
- `GET /api/reconciler` — exposes last reconciler run result
- `GET /api/signals` — signal history endpoint (fixed missing route)
- Heartbeat calls in: bridge, sentinel, lens, aegis, listener,
  herald, aurum, reconciler
- `reconciler.py` writes `config/reconciler_last.json` after
  each run for the API to serve
- DEMO/LIVE account type badge in ATHENA header
- Circuit breaker warning banner in ATHENA left column
- Null-safe rendering for all numeric values (shows '—' not crash)
- `aegis` block in `/api/live` — scale_factor, streak, session_pnl
- `components` dict in `/api/live` — latest heartbeat per component
- `reconciler` block in `/api/live` — last reconciler result
- `account_type`, `broker`, `server` in `/api/live` from broker_info.json
- `circuit_breaker` boolean in `/api/live`

### Changed
- `/api/live` — expanded to include all system state in one payload
- `dashboard/app.js` — now fetches `/api/components` and `/api/events`
- `dashboard/app.js` — COMP_STATUS and MOCK_EVENTS removed
- `dashboard/app.js` — ActivityLog accepts `events` and `components`
  as props instead of internal mock state
- `dashboard/app.js` — System Health panel driven by live API data
- `dashboard/app.js` — fallback D object uses null values not zeros
- `athena_api.py` — all file paths now absolute (resolve correctly
  regardless of working directory)

### Fixed
- LENS_MCP_CMD path in .env verified correct
- MT5 symlink at project root verified working
- Path mismatch: config/ files correctly resolved to python/config/
  (WorkingDirectory=python/), MT5/ files resolved to project root
- Missing `@app.route` decorator on `api_signals` function

### Added: Test Framework
- `tests/api/test_live.py` — 12 tests for /api/live
- `tests/api/test_endpoints.py` — health, sessions, performance, mode, events
- `tests/api/test_components.py` — /api/components all 11 present
- `tests/api/test_aurum.py` — AURUM chat endpoint (marked slow)
- `tests/conftest.py` — shared fixtures, base URL config
- `tests/requirements-test.txt` — pytest, requests, python-dotenv
- `tests/playwright.config.js` — Chrome, localhost:7842, HTML report
- `tests/package.json` — Playwright dev dependency
- `tests/ui/test_dashboard.spec.js` — dashboard load, panels
- `tests/ui/test_panels.spec.js` — activity log, trade groups,
  AURUM chat, mode control, LENS panel

### Added: Scripts and Shortcuts

**scripts/ directory (all Python, platform-agnostic):**

| Script | Purpose | Key flags |
|--------|---------|-----------|
| `health.py` | System health check | `--watch` `--json` |
| `test_api.py` | Run pytest API tests | `--file` `--all` `--html` |
| `test_ui.py` | Run Playwright tests | `--headed` `--debug` `--record` `--report` |
| `test_all.py` | Run all tests | `--api` `--ui` `--ci` |
| `logs.py` | View service logs | `--follow` `--errors` `--lines N` |
| `setup_tests.py` | Install test deps | `--check` |

**Makefile targets:**
`make help`, `make health`, `make test`, `make test-api`,
`make test-ui`, `make logs`, `make logs-bridge`, `make start`,
`make stop`, `make restart`, `make setup-tests`

**Shell aliases (added to ~/.zshrc):**
`ss-health`, `ss-watch`, `ss-status`, `ss-test`, `ss-test-api`,
`ss-test-ui`, `ss-test-silent`, `ss-report`, `ss-record`,
`ss-logs`, `ss-logs-bridge`, `ss-logs-listener`, `ss-logs-aurum`,
`ss-logs-errors`, `ss-start`, `ss-stop`, `ss-restart`, `ss`

---

## [1.1.0] — Earlier

### Added
- `RECONCILER` component — hourly position audit
- `trading_sessions` table in SCRIBE
- Session column on all SCRIBE tables
- `FORGE.WriteBrokerInfo()` — writes broker_info.json on startup
- `InputMode` parameter in FORGE EA dialog
- `BRIDGE._on_session_change()` — session transition detection
- `/api/sessions` and `/api/sessions/current` endpoints
- `/api/channel_performance` endpoint
- `/api/aegis_state` endpoint
- Circuit breaker in BRIDGE for MT5 staleness
- Dynamic lot scaling in AEGIS (scale down after losses)
- Session-aligned daily loss reset in AEGIS
- AURUM conversation memory from SCRIBE
- macOS launchd services for all 4 processes
- Linux systemd service files

## [1.0.0] — Initial Release

### Components
- BRIDGE, FORGE, LISTENER, LENS, SENTINEL, AEGIS,
  SCRIBE, HERALD, AURUM, ATHENA

### Core Features
- Signal room following via Telegram (Telethon)
- Claude API parsing of any signal format
- Layered entry: N trades across price zone
- TP1 partial close + SL to breakeven
- TradingView MCP integration (LewisWJackson)
- 5 operating modes: OFF/WATCH/SIGNAL/SCALPER/HYBRID
- SQLite database with 8 tables
- Flask API + React dashboard
